//! `plan()`: descriptor + account views → which pair and how much (DESIGN.md §3.5, §3.7, §4.5).
//!
//! 1. Every leg is checked and parsed once (DescError → ERR_SIZING_DESC), then every pair is validated (distinct
//!    pools, mint chain, one quote mint and one X across the basket).
//! 2. Per pair with no aborted leg: the locator's optima (or, where the model refuses and SEARCH allows it on a pair
//!    without a DLMM leg, a golden-section search over exact evaluations).
//! 3. Candidates — each optimum floored and clamped into [min_size, cap], the engine's amount `e` on pair 0 — are
//!    evaluated EXACTLY (DLMM legs resume from the exact swap states the locator passed). The argmax of the exact
//!    profit wins; ties go to `e`, then to the smaller size. A candidate past a capacity or the walk budget steps
//!    back to the last feasible size (gallop, then bisection).
//! 4. When `E(e)` is known, `e` is a candidate, so the chosen size makes at least what `e` would have (given exact
//!    quotes). When it is not — pair 0 aborted, or `e` lies past a DLMM leg's walk budget — `e` stays the fallback:
//!    a modeled candidate executes only if it clears `min_profit`, else pair 0 at `e` (Fallback, never NoProfit).
use crate::desc::SzFlags;
use crate::error::{Abort, DescCode, DescError, Quote, QuoteErr};
use crate::fx::Fx;
use crate::leg::{AnyLeg, Parsed};
use crate::math::sat_i64;
use crate::opt::{locate, Located, Optimum};
use crate::{Clock, LegIn, PdaFn};

/// CPI_TIP parameters (arbx-exec TipParams without the account index)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TipParams { pub bps: u16, pub floor: u64, pub cap: u64 }

/// tip = min(cap, max(floor, ⌊g·bps/1e4⌋)), exactly as arbx-exec's `cpi_tip`
pub fn cpi_tip(g: i128, p: &TipParams) -> u64 {
    let share = if g > 0 { g.saturating_mul(p.bps as i128) / 10_000 } else { 0 };
    share.max(p.floor as i128).min(p.cap as i128).max(0) as u64
}

pub struct PlanIn<'a> {
    pub clock: Clock,
    /// min(amount_in, quote balance at entry)
    pub cap: u64,
    pub min_size: u64,
    /// `e`
    pub engine_amount: u64,
    pub min_profit: u64,
    pub tip: Option<TipParams>,
    pub flags: SzFlags,
    pub max_iters: u8,
    /// the block's `lamport_offset` (0 without LAMPORTS): the guard's `g` under COUNT_LAMPORTS is the quote profit
    /// plus the executed legs' lamport delta, and the NoProfit verdict uses the same `g`
    pub lamport_offset: i64,
    pub legs: &'a [LegIn<'a>],
    /// (buy leg, sell leg); plain SELF_SIZE: [(0, 1)]
    pub pairs: &'a [(u8, u8)],
    pub pda: PdaFn,
}

#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    /// execute `pairs[pair]` at `amount`
    Sized = 0,
    /// SHADOW: the plan is logged, pair 0 at `e` executes
    Shadow = 1,
    /// pair 0 at `e`: the model refused every pair, or `E(e)` is unknown and no modeled candidate clears min_profit
    /// (STRICT: ERR_SIZING_UNSUPPORTED)
    Fallback = 2,
    /// no candidate clears min_profit (EARLY_ABORT: ERR_SIZING_NO_PROFIT before any CPI); else execute the plan
    NoProfit = 3,
}

/// AXZ1 `reason` codes besides [`Abort::code`]
pub struct Reason;
impl Reason {
    pub const OK: u16 = 0;
    /// the best exact profit (net of the CPI tip) is below min_profit
    pub const NO_PROFIT: u16 = 1;
    /// no candidate is feasible (every exact evaluation failed)
    pub const INFEASIBLE: u16 = 2;
    /// `e` lies past a DLMM leg's walk budget, so `E(e)` is unknown (the engine's `max_bins` is too small)
    pub const BUDGET: u16 = 3;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Plan {
    pub outcome: Outcome,
    pub reason: u16,
    /// index into PlanIn::pairs
    pub pair: u8,
    /// the planned input (`e` on Fallback)
    pub amount: u64,
    /// the locator's best x* for the chosen pair (0 if none)
    pub x_star: u64,
    /// exact profit at `amount`: quote out of the sell leg − quote debited by the buy leg (the guard's quote delta);
    /// 0 when not evaluated
    pub modeled_profit: i128,
    pub modeled_profit_e: Option<i128>,
    /// leg-0 exact output at `amount`
    pub modeled_y: u64,
    pub modeled_y_e: Option<u64>,
    /// exact round trips evaluated, and DLMM bins the locator read
    pub evals: u8,
    pub bins: u16,
}

const MAX_LEGS: usize = crate::desc::MAX_SIZED_LEGS;
const CACHE: usize = 24;
/// step-back after a candidate past a capacity or the walk budget (REVIEW.md F14): gallop (step ×4), then bisection;
/// at most `MAX_BACK` such evaluations per plan
const BACK_GALLOP: u32 = 8;
const BACK_BISECT: u32 = 8;
pub const MAX_BACK: u8 = 8;
/// a candidate evaluation of a DLMM leg resumes from an exact state the locator recorded and may read at most this
/// many bins past it, a step-back evaluation at most NEAR_BACK (else it counts as past the capacity): the static CU
/// bound of DESIGN.md §4.7 (`budget::cu_bound`)
pub const NEAR_BINS: u16 = 4;
pub const NEAR_BACK: u16 = 2;

/// Exact leg quotes, deduplicated per (leg, amount)
struct Quotes<'p, 'a> {
    legs: &'p [Option<Parsed<'a>>; MAX_LEGS],
    memo: [(u8, u64, Result<Quote, QuoteErr>); CACHE],
    n: usize,
    evals: u8,
    back: u8,
}

impl<'p, 'a> Quotes<'p, 'a> {
    /// leg `i` at `x`; a DLMM leg resumes from the furthest exact state of `side` in `loc` that `x` reaches. `near`:
    /// None when a DLMM leg would walk more than NEAR_BINS past that state.
    fn leg(&mut self, i: u8, x: u64, loc: Option<(&Located<'_, 'a>, usize)>, near: u16) -> Option<Result<Quote, QuoteErr>> {
        if let Some(e) = self.memo.iter().take(self.n).find(|e| e.0 == i && e.1 == x) { return Some(e.2); }
        let r = match self.legs.get(i as usize).and_then(|p| p.as_ref()).map(|p| &p.leg) {
            Some(Ok(AnyLeg::Dlmm(d))) => {
                let c = loc.and_then(|(l, side)| l.cursor(side, x));
                match (c, near) {
                    (Some(c), n) if n < u16::MAX => d.quote_near(&c, x, n)?,
                    (None, n) if n < u16::MAX => d.quote_near(&d.start(), x, n)?,
                    (Some(c), _) => d.quote_from(&c, x),
                    (None, _) => d.quote(x),
                }
            }
            Some(Ok(l)) => l.quote(x),
            Some(Err(a)) => Err(QuoteErr::Abort(*a)),
            None => Err(QuoteErr::Abort(Abort::Math)),
        };
        if let Some(slot) = self.memo.get_mut(self.n) { *slot = (i, x, r); self.n += 1; }
        Some(r)
    }
    /// (exact profit, leg-0 output) of a round trip at `x`: the sell leg's quote out minus what the buy leg debits.
    /// None: a DLMM leg would read more than `near` bins past the recorded state it resumes from.
    fn round_trip(&mut self, pair: (u8, u8), x: u64, loc: Option<&Located<'_, 'a>>, near: u16) -> Option<Result<(i128, u64), QuoteErr>> {
        self.evals = self.evals.saturating_add(1);
        let q0 = match self.leg(pair.0, x, loc.map(|l| (l, 0)), near)? { Ok(q) => q, Err(e) => return Some(Err(e)) };
        let q1 = match self.leg(pair.1, q0.out, loc.map(|l| (l, 1)), near)? { Ok(q) => q, Err(e) => return Some(Err(e)) };
        Some(Ok((q1.out as i128 - q0.spent as i128, q0.out)))
    }
    /// a full evaluation (`e`, golden section): may walk a DLMM leg from its start up to its budget
    fn full(&mut self, pair: (u8, u8), x: u64, loc: Option<&Located<'_, 'a>>) -> Result<(i128, u64), QuoteErr> {
        self.round_trip(pair, x, loc, u16::MAX).unwrap_or(Err(QuoteErr::Budget))
    }
}

#[derive(Clone, Copy, Debug)]
struct Cand { pair: u8, x: u64, profit: i128, y: u64, is_e: bool }

fn better(a: &Cand, b: &Option<Cand>) -> bool {
    match b {
        None => true,
        Some(b) => a.profit > b.profit || (a.profit == b.profit && ((a.is_e && !b.is_e) || (a.is_e == b.is_e && a.x < b.x))),
    }
}

fn desc_err(e: DescError, leg: usize) -> DescError { DescError { leg: leg as u8, ..e } }

/// Check and parse every leg, then every pair.
#[inline(never)]
fn parse_all<'a>(p: &PlanIn<'a>, out: &mut [Option<Parsed<'a>>; MAX_LEGS]) -> Result<(), DescError> {
    let n = p.legs.len();
    if !(2..=MAX_LEGS).contains(&n) || p.pairs.is_empty() || p.pairs.len() > crate::desc::MAX_PAIRS
        || p.min_size == 0 || p.min_size > p.engine_amount || p.max_iters > crate::desc::MAX_SEARCH_ITERS {
        return Err(DescError::block(DescCode::Plan));
    }
    for (i, (l, slot)) in p.legs.iter().zip(out.iter_mut()).enumerate() {
        *slot = Some(AnyLeg::parse(l, &p.clock, p.pda).map_err(|e| desc_err(e, i))?);
    }
    let mut quote_mint: Option<&[u8; 32]> = None;
    let mut x_mint: Option<&[u8; 32]> = None;
    for (k, &(b, s)) in p.pairs.iter().enumerate() {
        let pe = |c| DescError::new(c, k as u8, 0xFF);
        if b == s || b as usize >= n || s as usize >= n { return Err(pe(DescCode::PairIndex)); }
        let (Some(hb), Some(hs)) = (out.get(b as usize).and_then(|x| x.as_ref()), out.get(s as usize).and_then(|x| x.as_ref())) else {
            return Err(pe(DescCode::PairIndex));
        };
        if hb.head.pool == hs.head.pool { return Err(pe(DescCode::SamePool)); }
        if let (Some((bi, bo)), Some((si, so))) = (hb.head.mints, hs.head.mints) {
            if bo != si || so != bi { return Err(pe(DescCode::MintChain)); }
            if quote_mint.map_or(false, |q| q != bi) || x_mint.map_or(false, |x| x != bo) { return Err(pe(DescCode::BasketMint)); }
            quote_mint = Some(bi);
            x_mint = Some(bo);
        }
    }
    Ok(())
}

/// Plan the route. `Err` only for a DescError (the shell reverts with ERR_SIZING_DESC); every other situation is
/// an [`Outcome`]. Never inlined: the parsed legs (≈2 KB) live in this frame, not in the caller's (an LTO build
/// would otherwise merge them into the shell's frame and pass SBF's 4 KB frame limit; DESIGN.md §4.8).
#[inline(never)]
pub fn plan(p: &PlanIn) -> Result<Plan, DescError> {
    let mut legs: [Option<Parsed>; MAX_LEGS] = [None; MAX_LEGS];
    parse_all(p, &mut legs)?;
    decide(p, &legs)
}

/// What one pair contributes: its best exact candidate, its x*, the exact result at `e` (pair 0), DLMM bins read
struct PairOut { best: Option<Cand>, star: u64, e: Option<Result<(i128, u64), QuoteErr>>, bins: u16 }

/// The exact round trip at `xh`, or at the last feasible size below it when `xh` is past a capacity or the walk
/// budget: gallop back from 2^-24·xh (step ×4), then bisect the last gap down to that step (REVIEW.md F14). Every
/// evaluation resumes near the locator's exact states (NEAR_BINS); the step-backs share a plan-wide MAX_BACK. None:
/// nothing feasible found.
#[inline(never)]
fn eval_back<'a>(q: &mut Quotes<'_, 'a>, pair: (u8, u8), xh: u64, lo: u64, loc: Option<&Located<'_, 'a>>) -> Option<(u64, (i128, u64))> {
    // Some(true): feasible; Some(false): past a capacity, the budget or the near walk (step back); None: give up
    let try_at = |q: &mut Quotes<'_, 'a>, x: u64, near: u16| -> (Option<bool>, Option<(i128, u64)>) {
        match q.round_trip(pair, x, loc, near) {
            Some(Ok(v)) => (Some(true), Some(v)),
            None | Some(Err(QuoteErr::TooLarge)) | Some(Err(QuoteErr::Budget)) => (Some(false), None),
            Some(Err(_)) => (None, None),
        }
    };
    match try_at(q, xh, NEAR_BINS) {
        (Some(true), Some(v)) => return Some((xh, v)),
        (Some(false), _) => {}
        _ => return None,
    }
    let tol = (xh >> 24).max(1);
    let (mut bad, mut d) = (xh, tol);
    let mut good: Option<(u64, (i128, u64))> = None;
    for _ in 0..BACK_GALLOP {
        let t = xh.saturating_sub(d).max(lo);
        if t >= bad || q.back >= MAX_BACK { break; }
        q.back += 1;
        match try_at(q, t, NEAR_BACK) {
            (Some(true), Some(v)) => { good = Some((t, v)); break; }
            (Some(false), _) => bad = t,
            _ => return None,
        }
        if t == lo { break; }
        d = d.saturating_mul(4);
    }
    let (mut g, mut gv) = good?;
    for _ in 0..BACK_BISECT {
        if bad - g <= tol || q.back >= MAX_BACK { break; }
        q.back += 1;
        let mid = g + (bad - g) / 2;
        match try_at(q, mid, NEAR_BACK) {
            (Some(true), Some(v)) => { g = mid; gv = v; }
            (Some(false), _) => bad = mid,
            _ => break,
        }
    }
    Some((g, gv))
}

/// Size one pair (DESIGN.md §3.3-§3.6). Err: the model refused it (an Abort); the pair is then not live.
#[inline(never)]
fn size_pair<'a>(p: &PlanIn<'a>, q: &mut Quotes<'_, 'a>, k: u8, pair: (u8, u8), b: &AnyLeg<'a>, s: &AnyLeg<'a>, with_e: bool)
    -> Result<PairOut, Abort> {
    let basket = p.pairs.len() > 1;
    // the input cap: the route's cap, and leg 0's exact closed-form capacity
    let cap_int = b.cheap_cap().map_or(p.cap, |c| c.min(p.cap));
    let mut out = PairOut { best: None, star: 0, e: None, bins: 0 };
    let keep = |out: &mut PairOut, x: u64, (profit, y): (i128, u64)| {
        let c = Cand { pair: k, x, profit, y, is_e: false };
        if better(&c, &out.best) { out.best = Some(c); }
    };
    match (b.model(), s.model()) {
        (Ok(m0), Ok(m1)) => {
            let loc = if cap_int >= p.min_size { locate(&m0, &m1, Fx::from_u64(cap_int)) } else { Located::default() };
            out.bins = loc.bins;
            let sorted = loc.sorted();
            if let Some(Some(o)) = sorted.first() { out.star = o.x.floor_u64(); }
            // BASKET evaluates each pair's best optimum only (DESIGN.md §3.7)
            let take = if basket { 1 } else { sorted.len() };
            for o in sorted.iter().take(take).flatten() {
                let Optimum { x, .. } = *o;
                let xh = x.floor_u64().clamp(p.min_size, cap_int);
                if let Some((xb, v)) = eval_back(q, pair, xh, p.min_size, Some(&loc)) { keep(&mut out, xb, v); }
            }
            if with_e && p.engine_amount <= p.cap { out.e = Some(q.full(pair, p.engine_amount, Some(&loc))); }
        }
        // the model refused: the exact golden-section search (DESIGN.md §3.6), never over a DLMM leg (its exact
        // evaluations walk bins: REVIEW.md F4)
        (Err(a), _) | (_, Err(a)) => {
            if !(p.flags.search() && cfg!(feature = "search")) || b.walks() || s.walks() { return Err(a); }
            if cap_int >= p.min_size {
                let mut ev = |x: u64| q.full(pair, x, None).ok().map(|r| r.0);
                if let Some((x, _)) = crate::opt::golden(p.min_size, cap_int, p.max_iters, &mut ev) {
                    out.star = x;
                    if let Ok(v) = q.full(pair, x, None) { keep(&mut out, x, v); }
                }
            }
            if with_e && p.engine_amount <= p.cap { out.e = Some(q.full(pair, p.engine_amount, None)); }
        }
    }
    Ok(out)
}

#[inline(never)]
fn decide<'a>(p: &PlanIn<'a>, legs: &[Option<Parsed<'a>>; MAX_LEGS]) -> Result<Plan, DescError> {
    let e = p.engine_amount;
    let mut q = Quotes { legs, memo: [(0, 0, Err(QuoteErr::ZeroOut)); CACHE], n: 0, evals: 0, back: 0 };
    let mut first_abort: Option<Abort> = None;
    let mut any_live = false;
    let mut best: Option<Cand> = None;
    let mut best_star = [0u64; crate::desc::MAX_PAIRS];
    let mut bins = 0u16;
    // E(e) on pair 0 when known; and, when it is unknown, why and whether a modeled candidate may replace e
    let mut e_eval: Option<(i128, u64)> = None;
    let mut e_unknown: Option<(u16, bool)> = None;
    let leg_of = |i: u8| legs.get(i as usize).and_then(|x| x.as_ref()).map(|x| &x.leg);
    for (k, &(bi, si)) in p.pairs.iter().enumerate() {
        let r = match (leg_of(bi), leg_of(si)) {
            (Some(Ok(b)), Some(Ok(s))) => size_pair(p, &mut q, k as u8, (bi, si), b, s, k == 0),
            (Some(Err(a)), _) | (_, Some(Err(a))) => Err(*a),
            _ => Err(Abort::Math),
        };
        let o = match r {
            Ok(o) => o,
            Err(a) => {
                first_abort.get_or_insert(a);
                // pair 0 aborted: nothing is known about e (REVIEW.md F7)
                if k == 0 { e_unknown = Some((a.code(), true)); }
                continue;
            }
        };
        any_live = true;
        bins = bins.saturating_add(o.bins);
        if let Some(slot) = best_star.get_mut(k) { *slot = o.star; }
        if let Some(c) = o.best { if better(&c, &best) { best = Some(c); } }
        match o.e {
            Some(Ok((profit, y))) => {
                e_eval = Some((profit, y));
                let c = Cand { pair: 0, x: e, profit, y, is_e: true };
                if better(&c, &best) { best = Some(c); }
            }
            // e lies past a DLMM leg's walk budget: the venue fills it, the crate did not evaluate it. The engine
            // sizes the budget from the cap, so this means its estimate was wrong: execute e (REVIEW.md F3)
            Some(Err(QuoteErr::Budget)) => e_unknown = Some((Reason::BUDGET, false)),
            _ => {}
        }
    }
    let base = Plan {
        outcome: Outcome::Fallback, reason: Reason::OK, pair: 0, amount: e, x_star: 0, modeled_profit: 0,
        modeled_profit_e: e_eval.map(|v| v.0), modeled_y: 0, modeled_y_e: e_eval.map(|v| v.1), evals: q.evals, bins,
    };
    if !any_live {
        return Ok(Plan { reason: first_abort.map_or(Abort::Math.code(), |a| a.code()), ..base });
    }
    // g as the guard computes it (quote delta + the lamport delta under COUNT_LAMPORTS), net of the CPI tip
    let net = |profit: i128| {
        let g = profit.saturating_add(p.lamport_offset as i128);
        match &p.tip { Some(t) => g - cpi_tip(g, t) as i128, None => g }
    };
    let clears = |c: &Cand| net(c.profit) >= p.min_profit as i128;
    let sized = |c: Cand| Plan { outcome: Outcome::Sized, reason: Reason::OK, pair: c.pair, amount: c.x,
        x_star: best_star.get(c.pair as usize).copied().unwrap_or(0), modeled_profit: c.profit, modeled_y: c.y, ..base };
    let mut plan = match (e_unknown, best) {
        // E(e) unknown: e stays the fallback; after an abort of pair 0 a modeled candidate of another pair replaces it
        // when it clears min_profit; past the walk budget e always executes
        (Some((_, true)), Some(c)) if clears(&c) => sized(c),
        (Some((why, _)), _) => Plan { reason: why, ..base },
        (None, None) => Plan { outcome: Outcome::NoProfit, reason: Reason::INFEASIBLE, ..base },
        (None, Some(c)) if clears(&c) => sized(c),
        (None, Some(c)) => Plan { outcome: Outcome::NoProfit, reason: Reason::NO_PROFIT, ..sized(c) },
    };
    if p.flags.shadow() && plan.outcome != Outcome::Fallback { plan.outcome = Outcome::Shadow; }
    Ok(plan)
}

pub const AXZ1_LEN: usize = 76;
pub const AXZ1_MAGIC: [u8; 4] = *b"AXZ1";

/// The AXZ1 log record (76 bytes, LE): magic[4] outcome u8 pair u8 n_pairs u8 flags u8 reason u16 evals u8 bins u8 |
/// x u64 | e u64 | x_star u64 | cap u64 | y_x u64 | y_e u64 | profit_x i64 | profit_e i64. `y_e` is 0 and `profit_e`
/// i64::MIN when `e` was not evaluated or infeasible.
pub fn axz1_record(plan: &Plan, n_pairs: u8, flags: SzFlags, e: u64, cap: u64) -> [u8; AXZ1_LEN] {
    let mut m = [0u8; AXZ1_LEN];
    let mut put = |o: usize, b: &[u8]| { if let Some(d) = m.get_mut(o..o + b.len()) { d.copy_from_slice(b); } };
    put(0, &AXZ1_MAGIC);
    put(4, &[plan.outcome as u8, plan.pair, n_pairs, flags.0]);
    put(8, &plan.reason.to_le_bytes());
    put(10, &[plan.evals, plan.bins.min(255) as u8]);
    put(12, &plan.amount.to_le_bytes());
    put(20, &e.to_le_bytes());
    put(28, &plan.x_star.to_le_bytes());
    put(36, &cap.to_le_bytes());
    put(44, &plan.modeled_y.to_le_bytes());
    put(52, &plan.modeled_y_e.unwrap_or(0).to_le_bytes());
    put(60, &sat_i64(plan.modeled_profit).to_le_bytes());
    put(68, &plan.modeled_profit_e.map_or(i64::MIN, sat_i64).to_le_bytes());
    m
}

//! Regression tests for the findings of REVIEW.md (one test per finding; the real-binary side of each is in
//! venue-harness: tests/exactness.rs, tests/adversarial.rs, tests/route.rs).
mod common;
use arbx_sizing::error::{CpmmWhy, PumpWhy};
use arbx_sizing::layout::WSOL;
use arbx_sizing::opt::{locate, LegModel};
use arbx_sizing::venue::{dlmm, pumpswap};
use arbx_sizing::{plan, Abort, AnyLeg, Kind, Outcome, Plan, PlanIn, QuoteErr, Reason, SzFlags, TipParams};
use common::*;

const A: Pk = WSOL;

/* ------------------------------------------------------ helpers ------------------------------------------------------ */

fn cp_leg(rng: &mut Rng, amm: bool, buy: bool, ra: u64, rx: u64, x: Pk, fee: u64) -> OwnedLeg {
    if amm {
        let st = ammv4(rng, rx, ra, fee, 10_000, x, A);
        OwnedLeg::new(Kind::RayAmmV4, !buy, st, if buy { A } else { x })
    } else {
        let spec = CpmmSpec { r0: ra, r1: rx, trade: fee * 100, creator: 0, enable_creator: false, creator_on: 0, owed0: 0, owed1: 0 };
        let st = cpmm(rng, &spec, A, x, buy);
        OwnedLeg::new(Kind::RayCpmm, buy, st, if buy { A } else { x })
    }
}

/// a DLMM pair X/A: `depth` of A per bin below `active` (X priced to match above), bins active ± `span`
fn dlmm_pair(rng: &mut Rng, x: Pk, bin_step: u16, active: i32, span: i32, depth: u64, f: impl Fn(&mut DlmmSpec)) -> (Acct, Acct, Acct, Vec<Acct>) {
    let mut spec = DlmmSpec { bin_step, active, idx_ref: active, last_ts: CLOCK.unix_timestamp, vfc: 0, bins: vec![], ..Default::default() };
    for id in active - span..=active + span {
        let price = dlmm_price(bin_step, id) as f64 / 18446744073709551616.0;
        let ax = (depth as f64 / price) as u64;
        let (bx, by) = if id < active { (0, depth) } else if id > active { (ax, 0) } else { (ax / 2, depth / 2) };
        spec.bins.push((id, bx, by, (0, 0, 0)));
    }
    f(&mut spec);
    dlmm(rng, &spec, x, A)
}

fn dlmm_leg(p: &(Acct, Acct, Acct, Vec<Acct>), buy: bool) -> OwnedLeg {
    let st = dlmm_state(&p.0, &p.1, &p.2, &p.3, !buy);
    OwnedLeg::new(Kind::Dlmm, !buy, st, if buy { A } else { p.1.key })
}

struct Route { cap: u64, min_size: u64, e: u64, flags: u8, tip: Option<TipParams>, min_profit: u64, lamports: i64 }
impl Default for Route {
    fn default() -> Self { Route { cap: 1 << 40, min_size: 1, e: 1_000_000, flags: 0, tip: None, min_profit: 1, lamports: 0 } }
}

fn run(legs: &[OwnedLeg], pairs: &[(u8, u8)], r: &Route) -> Plan {
    let v = views(legs);
    let ins = leg_ins(legs, &v);
    let p = PlanIn { clock: CLOCK, cap: r.cap, min_size: r.min_size, engine_amount: r.e, min_profit: r.min_profit, tip: r.tip,
        flags: SzFlags(r.flags), max_iters: 24, lamport_offset: r.lamports, legs: &ins, pairs, pda };
    plan(&p).expect("desc error")
}

/// the guard's quote delta at x: sell-leg output minus buy-leg debit
fn exact(l0: &AnyLeg, l1: &AnyLeg, x: u64) -> Option<i128> {
    let q0 = l0.quote(x).ok()?;
    let q1 = l1.quote(q0.out).ok()?;
    Some(q1.out as i128 - q0.spent as i128)
}

/// the best exact profit on [lo, hi]: a 2048-point log/linear grid, then a shrinking local search
fn best(l0: &AnyLeg, l1: &AnyLeg, lo: u64, hi: u64) -> Option<(u64, i128)> {
    let keep = |b: &mut Option<(u64, i128)>, x: u64| { if let Some(v) = exact(l0, l1, x) { if b.map_or(true, |o| v > o.1) { *b = Some((x, v)); } } };
    let mut b: Option<(u64, i128)> = None;
    for i in 0..=1024u64 {
        let f = i as f64 / 1024.0;
        keep(&mut b, lo + ((hi - lo) as f64 * f) as u64);
        keep(&mut b, ((lo.max(1) as f64).ln() + ((hi as f64).ln() - (lo.max(1) as f64).ln()) * f).exp().clamp(lo as f64, hi as f64) as u64);
    }
    let mut w = ((hi - lo) / 1024).max(2);
    while w > 1 {
        let c = b?.0;
        for k in -24i64..=24 { keep(&mut b, (c as i128 + k as i128 * w as i128 / 8).clamp(lo as i128, hi as i128) as u64); }
        w = w * 2 / 3;
    }
    b
}

/// the largest x in [lo, hi] whose round trip is feasible (feasibility is a prefix of [lo, ∞))
fn last_feasible(l0: &AnyLeg, l1: &AnyLeg, lo: u64, hi: u64) -> u64 {
    let ok = |x: u64| exact(l0, l1, x).is_some();
    let (mut g, mut b) = (lo, hi);
    if ok(hi) { return hi; }
    while b - g > 1 { let m = g + (b - g) / 2; if ok(m) { g = m } else { b = m } }
    g
}

/* -------------------------------------------------------- F1 / F9 -------------------------------------------------------- */

/// F1: a PumpSwap sell may pay out at most Q − (held_0 + held_1) net of the LP fee (u64 @271, @279; pinned on the
/// real binary, re-checked by venue-harness tests/adversarial.rs "held quote …"). The capacity is exact with the
/// held amounts, they never move the price, and more held than Q refuses the pool in both directions.
/// F9: the pool is accepted at exactly 301 bytes, with its unidentified tail bytes clear.
#[test]
fn f1_f9_pumpswap_held_quote_and_layout_gate() {
    let mut rng = Rng(901);
    let mut checked = 0;
    for case in 0..200 {
        let quote = rng.log(1_000_000_000, 1 << 44);
        let spec = PumpSpec { base: rng.log(1 << 30, 1 << 56), quote, virt: if case % 3 == 0 { quote as i128 * 50 } else { 0 }, creator_fee_bps: [0, 200, 1000][case % 3], ..Default::default() };
        let p = pump(&mut rng, &spec);
        let held = [(0u64, 0u64), (quote / 3, 0), (0, quote / 5), (quote / 4, quote / 4), (quote / 2, quote - quote / 2), (1_469_628, 2_939_251)][case % 6];
        let mut leg = OwnedLeg::pump(&p, true);
        put_u64(&mut leg.state[0].data, 271, held.0);
        put_u64(&mut leg.state[0].data, 279, held.1);
        let refs: Vec<_> = leg.state.iter().map(|a| a.view()).collect();
        let AnyLeg::Pump(pl) = any_leg(&leg, &refs) else { panic!() };
        let avail = quote - held.0 - held.1;
        assert_eq!(pl.quote, avail, "case {case}");
        // the same leg without held amounts prices identically below its (larger) capacity
        let mut free = OwnedLeg::pump(&p, true);
        put_u64(&mut free.state[0].data, 271, 0);
        let frefs: Vec<_> = free.state.iter().map(|a| a.view()).collect();
        let AnyLeg::Pump(fl) = any_leg(&free, &frefs) else { panic!() };
        let Some(cap) = pl.cap_in() else { continue };
        // exact capacity: the rule at cap holds, at cap + 1 it fails
        let rule = |b: u64| {
            let q = (pl.qv as u128 * b as u128) / (pl.base as u128 + b as u128);
            q - (q * pl.fees.lp as u128).div_ceil(10_000) <= avail as u128
        };
        if cap > 0 && cap < u64::MAX {
            assert!(rule(cap) && !rule(cap + 1), "case {case}: cap {cap}");
            assert!(pl.quote(cap).is_ok() || pl.quote(cap) == Err(QuoteErr::ZeroOut), "case {case}");
            assert_eq!(pl.quote(cap + 1), Err(QuoteErr::TooLarge), "case {case}");
            if cap > 1 { assert_eq!(pl.quote(cap / 2), fl.quote(cap / 2), "held amounts must not move the price"); }
            checked += 1;
        }
    }
    assert!(checked > 100, "{checked}");
    // held above the vault: both instructions fail on chain (6023); the crate refuses both legs
    let p = pump(&mut rng, &PumpSpec::default());
    for sell in [true, false] {
        let mut leg = OwnedLeg::pump(&p, sell);
        put_u64(&mut leg.state[0].data, 271, p.quote_vault.data[64..72].iter().rev().fold(0u64, |a, &b| a << 8 | b as u64));
        put_u64(&mut leg.state[0].data, 279, 1);
        let refs: Vec<_> = leg.state.iter().map(|a| a.view()).collect();
        let li = arbx_sizing::LegIn { desc: leg.desc, program: leg.desc.kind.program(), state: &refs, input_mint: &leg.input_mint };
        assert_eq!(AnyLeg::parse(&li, &CLOCK, pda).unwrap().leg.unwrap_err(), Abort::Pump(PumpWhy::HeldExceedsVault));
    }
    // F9: exactly 301 bytes, unidentified tail bytes clear
    let parse_with = |f: &dyn Fn(&mut Vec<u8>)| {
        let mut leg = OwnedLeg::pump(&p, true);
        f(&mut leg.state[0].data);
        let refs: Vec<_> = leg.state.iter().map(|a| a.view()).collect();
        let li = arbx_sizing::LegIn { desc: leg.desc, program: leg.desc.kind.program(), state: &refs, input_mint: &leg.input_mint };
        AnyLeg::parse(&li, &CLOCK, pda).unwrap().leg.err()
    };
    assert_eq!(parse_with(&|_| {}), None);
    assert_eq!(parse_with(&|d| d.truncate(300)), Some(Abort::Layout));
    assert_eq!(parse_with(&|d| d.truncate(270)), Some(Abort::Layout));
    assert_eq!(parse_with(&|d| d.push(0)), Some(Abort::Layout));
    for at in [270usize, 287, 300] { assert_eq!(parse_with(&|d| d[at] = 1), Some(Abort::Pump(PumpWhy::UnknownTail)), "byte {at}"); }
    assert_eq!(pumpswap::POOL_LEN, 301);
}

/// F1 at plan level: a PumpSwap sell leg 1 whose capacity binds (BOOST-like V = 50·Q, held amounts present): the
/// planned size must execute (its exact round trip is feasible) and sits on the last feasible size.
#[test]
fn f1_plan_respects_the_held_quote_capacity() {
    let mut rng = Rng(902);
    let mut binding = 0;
    for case in 0..60 {
        let q = rng.log(10_000_000_000, 1 << 40);
        let p = pump(&mut rng, &PumpSpec { base: 1 << 50, quote: q, virt: q as i128 * 50, ..Default::default() });
        let x = p.base_key();
        let mut sell = OwnedLeg::pump(&p, true);
        put_u64(&mut sell.state[0].data, 271, q / 4);
        put_u64(&mut sell.state[0].data, 279, q / 8 + case);
        // a deep CPMM that sells X much cheaper than the pump pool prices it: the round trip rises to the capacity
        let qv = q as f64 * 51.0;
        let price = qv / (1u64 << 50) as f64;
        let buy = cp_leg(&mut rng, false, true, 1 << 46, ((1u64 << 46) as f64 / (price * 0.8)) as u64, x, 25);
        let legs = vec![buy, sell];
        let v = views(&legs);
        let (l0, l1) = (any_leg(&legs[0], &v.refs[0]), any_leg(&legs[1], &v.refs[1]));
        let r = run(&legs, &[(0, 1)], &Route { cap: 1 << 45, e: 1_000_000, ..Default::default() });
        assert_eq!(r.outcome, Outcome::Sized, "case {case}: {r:?}");
        assert_eq!(exact(&l0, &l1, r.amount), Some(r.modeled_profit), "case {case}: the planned size must execute");
        let last = last_feasible(&l0, &l1, r.amount, 1 << 45);
        if last < 1 << 45 {
            binding += 1;
            assert!(last - r.amount <= (last >> 20).max(2), "case {case}: planned {} but feasible up to {last}", r.amount);
        }
    }
    assert!(binding > 30, "{binding}");
}

/* ---------------------------------------------------------- F2 ---------------------------------------------------------- */

/// F2: buy_exact_quote_in debits min(x, eff0 + fees(eff0)) (venue-harness pins.rs; exactness.rs runs 1,000
/// consecutive sizes on 6ejg), and the plan's profit is the guard's quote delta: sell output minus that debit.
#[test]
fn f2_pumpswap_buy_debit_and_plan_profit() {
    let mut rng = Rng(903);
    let p = pump(&mut rng, &PumpSpec { creator_fee_bps: 200, ..Default::default() });
    let leg = OwnedLeg::pump(&p, false);
    let refs: Vec<_> = leg.state.iter().map(|a| a.view()).collect();
    let AnyLeg::Pump(pl) = any_leg(&leg, &refs) else { panic!() };
    let f = pl.fees;
    let fee = |e: u128| [f.lp, f.protocol, f.creator].iter().map(|&b| (e * b as u128).div_ceil(10_000)).sum::<u128>();
    let (mut below, mut short_x) = (0, None);
    for x in 10_000_000u64..10_020_000 {
        let q = pl.quote(x).unwrap();
        let eff0 = x as u128 * 10_000 / (10_000 + f.total());
        let debit = (eff0 + fee(eff0)).min(x as u128) as u64;
        assert_eq!(q.spent, debit, "x {x}");
        if debit < x { below += 1; short_x.get_or_insert(x); }
    }
    assert!(below > 0, "no size debits less than x");
    // a route whose e debits less than e: modeled_profit_e is the sell output minus the debit
    let e = short_x.unwrap();
    let x = p.base_key();
    let sell = cp_leg(&mut rng, false, false, 1 << 40, 1 << 50, x, 25);
    let legs = vec![leg.clone(), sell];
    let v = views(&legs);
    let (l0, l1) = (any_leg(&legs[0], &v.refs[0]), any_leg(&legs[1], &v.refs[1]));
    let r = run(&legs, &[(0, 1)], &Route { cap: 1 << 36, e, ..Default::default() });
    let q0 = l0.quote(e).unwrap();
    let q1 = l1.quote(q0.out).unwrap();
    assert!(q0.spent < e);
    assert_eq!(r.modeled_profit_e, Some(q1.out as i128 - q0.spent as i128));
    assert_eq!(exact(&l0, &l1, r.amount), Some(r.modeled_profit));
}

/* ---------------------------------------------------------- F3 ---------------------------------------------------------- */

/// F3: the walk budget is not a capacity. Past it a quote is Budget (never TooLarge) while the unbounded quote
/// fills; `bins_for` gives the exact budget; e past the budget falls back to e (never dropped, never NoProfit).
#[test]
fn f3_budget_is_not_a_capacity_and_keeps_e() {
    let mut rng = Rng(904);
    let x = rng.key();
    let pair = dlmm_pair(&mut rng, x, 1, 0, 300, 40_000_000, |s| { s.idx_ref = -20; s.base_factor = 5_000; });
    let mut leg = dlmm_leg(&pair, true);
    leg.desc.max_bins = 64;
    let refs: Vec<_> = leg.state.iter().map(|a| a.view()).collect();
    let AnyLeg::Dlmm(d) = any_leg(&leg, &refs) else { panic!() };
    let unb = d.with_budget(dlmm::NO_BUDGET);
    let mut seen_budget = 0;
    for xi in [1_000_000u64, 500_000_000, 2_000_000_000, 3_000_000_000, 4_000_000_000, 8_000_000_000] {
        let need = unb.bins_for(xi).unwrap();
        match d.quote(xi) {
            Ok(q) => { assert!(need <= 64); assert_eq!(Ok(q), unb.quote(xi)); }
            Err(QuoteErr::Budget) => { assert!(need > 64); assert!(unb.quote(xi).is_ok()); seen_budget += 1; }
            other => panic!("x {xi}: {other:?}"),
        }
        // the budget the engine computes is exactly enough
        assert_eq!(unb.with_budget(need).quote(xi), unb.quote(xi));
        if need > 1 { assert_eq!(unb.with_budget(need - 1).quote(xi), Err(QuoteErr::Budget)); }
    }
    assert!(seen_budget >= 2);
    // the plan: e past the budget → Fallback BUDGET at e, also with EARLY_ABORT and min_profit above everything
    let p0 = dlmm_price(1, 0) as f64 / 18446744073709551616.0;
    let sell = cp_leg(&mut rng, false, false, 400_000_000_000, (400_000_000_000f64 / (p0 * 1.03)) as u64, x, 25);
    let legs = vec![leg.clone(), sell];
    for (flags, min_profit) in [(0, 1), (SzFlags::EARLY_ABORT, 1), (SzFlags::EARLY_ABORT, u64::MAX >> 2)] {
        let r = run(&legs, &[(0, 1)], &Route { cap: 200_000_000_000, e: 4_000_000_000, flags, min_profit, ..Default::default() });
        assert_eq!((r.outcome, r.reason, r.amount, r.modeled_profit_e), (Outcome::Fallback, Reason::BUDGET, 4_000_000_000, None), "flags {flags}");
    }
    // with e inside the budget the plan sizes and compares with e (the reviewer's e = 2e9 case)
    let r = run(&legs, &[(0, 1)], &Route { cap: 200_000_000_000, e: 2_000_000_000, ..Default::default() });
    assert_eq!(r.outcome, Outcome::Sized);
    assert!(r.modeled_profit >= r.modeled_profit_e.unwrap());
}

/// F3: the locator's step bound is per leg, so a DLMM ↔ DLMM walk is not cut after ~32 bins per leg: with the
/// optimum ~50 bins into each leg the plan reaches the brute-force best (old: 64 steps shared → 1.8-44% lost).
#[test]
fn f3_dlmm_dlmm_walk_is_not_cut_short() {
    let mut rng = Rng(905);
    let mut n = 0;
    for case in 0..12 {
        let x = rng.key();
        let gap = 90 + case as i32 * 5; // bins between the two pairs' active bins (bin step 1: ~1%)
        let a = dlmm_pair(&mut rng, x, 1, -gap, 200, 20_000_000 + case * 1_000_000, |s| s.base_factor = 2_000);
        let b = dlmm_pair(&mut rng, x, 1, 0, 200, 20_000_000, |s| s.base_factor = 2_000);
        let legs = vec![dlmm_leg(&a, true), dlmm_leg(&b, false)];
        let v = views(&legs);
        let (l0, l1) = (any_leg(&legs[0], &v.refs[0]), any_leg(&legs[1], &v.refs[1]));
        let cap = 50_000_000_000;
        let r = run(&legs, &[(0, 1)], &Route { cap, e: 1_000_000, ..Default::default() });
        let (bx, bv) = best(&l0, &l1, 1, cap).unwrap();
        let loc = locate(&l0.model().unwrap(), &l1.model().unwrap(), arbx_sizing::Fx::from_u64(cap));
        assert!(loc.steps > 64, "case {case}: the walk should need more than the old 64 shared steps ({})", loc.steps);
        assert!(bv - r.modeled_profit <= bv / 100_000 + 50, "case {case}: best {bv} at {bx}, planned {} at {} ({:?})", r.modeled_profit, r.amount, r.outcome);
        n += 1;
    }
    assert_eq!(n, 12);
}

/* ---------------------------------------------------------- F6 ---------------------------------------------------------- */

/// F6: once an optimum is recorded the non-concavity guard runs on every step, so a reversion arb (fee falling
/// toward idx_ref) stops right after its optimum instead of walking to the budget (old: 64 steps / 65 bins).
#[test]
fn f6_guard_stops_the_walk_after_the_optimum() {
    for (ahead, depth, gap) in [(20, 20_000_000u64, 1.06f64), (20, 2_000_000_000, 1.06), (-20, 20_000_000, 1.06), (20, 20_000_000, 1.015)] {
        let mut rng = Rng(906);
        let x = rng.key();
        let pair = dlmm_pair(&mut rng, x, 100, 0, 175, depth, |s| { s.idx_ref = ahead; s.vfc = 7_500; s.max_va = 150_000; s.base_factor = 20_000; });
        let ra = 40_000_000_000_000u64;
        let legs = vec![dlmm_leg(&pair, true), cp_leg(&mut rng, false, false, ra, (ra as f64 / gap) as u64, x, 25)];
        let v = views(&legs);
        let (l0, l1) = (any_leg(&legs[0], &v.refs[0]), any_leg(&legs[1], &v.refs[1]));
        let loc = locate(&l0.model().unwrap(), &l1.model().unwrap(), arbx_sizing::Fx::from_u64(200_000_000_000));
        let o = loc.sorted()[0].unwrap();
        // the optimum's bin, then at most one more step
        let opt_bins = { let LegModel::Bins(d) = l0.model().unwrap() else { panic!() }; d.bins_for(o.x.floor_u64().max(1)).unwrap_or(0) as u16 };
        assert!(loc.bins <= opt_bins + 2, "ahead {ahead} depth {depth}: walked {} bins, optimum in bin {opt_bins} ({loc:?})", loc.bins);
        assert!(loc.steps <= opt_bins + 3, "steps {}", loc.steps);
    }
}

/* ---------------------------------------------------------- F7 ---------------------------------------------------------- */

/// F7: BASKET with pair 0 aborted (CPMM owed fees above the vault). E(e) is unknown: another pair executes only
/// when it clears min_profit, otherwise pair 0 at e falls back (never NoProfit, so EARLY_ABORT cannot revert a
/// route e might land). SELF_SIZE behaves the same way.
#[test]
fn f7_basket_keeps_e_when_pair_0_aborts() {
    let mut rng = Rng(907);
    let x = rng.key();
    let ra = 500_000_000_000u64;
    let mut b0 = cp_leg(&mut rng, false, true, ra, ra, x, 25);
    put_u64(&mut b0.state[0].data, 341, u64::MAX / 2);
    let s0 = cp_leg(&mut rng, false, false, ra, (ra as f64 / 1.02) as u64, x, 25);
    let b1 = cp_leg(&mut rng, true, true, ra, (ra as f64 / 1.019 * 1.03) as u64, x, 25);
    let legs = vec![b0, s0, b1];
    let abort = Abort::Cpmm(CpmmWhy::OwedExceedsVault).code();
    let low = run(&legs, &[(0, 1), (2, 1)], &Route { cap: 100_000_000_000, e: 1_000_000_000, ..Default::default() });
    assert_eq!((low.outcome, low.pair), (Outcome::Sized, 1), "{low:?}");
    assert!(low.modeled_profit > 1 && low.modeled_profit_e.is_none());
    for flags in [0, SzFlags::EARLY_ABORT] {
        let high = run(&legs, &[(0, 1), (2, 1)], &Route { cap: 100_000_000_000, e: 1_000_000_000, flags, min_profit: low.modeled_profit as u64 + 1, ..Default::default() });
        assert_eq!((high.outcome, high.reason, high.pair, high.amount), (Outcome::Fallback, abort, 0, 1_000_000_000), "flags {flags}: {high:?}");
    }
    let solo = run(&legs[..2], &[(0, 1)], &Route { cap: 100_000_000_000, e: 1_000_000_000, flags: SzFlags::EARLY_ABORT, ..Default::default() });
    assert_eq!((solo.outcome, solo.reason, solo.amount), (Outcome::Fallback, abort, 1_000_000_000));
}

/* ---------------------------------------------------------- F8 ---------------------------------------------------------- */

/// F8: the pair's own min_bin_id / max_bin_id bound the walk (advance_active_bin fails PairInsufficientLiquidity
/// past them, 6012 on the real binary): the quote ends there, and cap_in is exact at the bound.
#[test]
fn f8_pair_bin_bounds_cap_the_walk() {
    let mut rng = Rng(908);
    let x = rng.key();
    for (lo, hi) in [(-1, 1), (-3, 0), (0, 5), (-443_636, 443_636)] {
        let pair = dlmm_pair(&mut rng, x, 25, 0, 40, 1_000_000_000, |s| { s.min_bin = lo; s.max_bin = hi; });
        for buy in [true, false] {
            let leg = dlmm_leg(&pair, buy);
            let refs: Vec<_> = leg.state.iter().map(|a| a.view()).collect();
            let AnyLeg::Dlmm(d) = any_leg(&leg, &refs) else { panic!() };
            let mut w = d.walker();
            let mut ids = vec![];
            while let Some(b) = w.next_bin() { ids.push(b.id); }
            assert!(ids.iter().all(|&id| (lo..=hi).contains(&id) || id == 0), "bounds {lo}..{hi}: {ids:?}");
            let n = if buy { hi.min(40) + 1 } else { (-lo).min(40) + 1 };
            assert_eq!(ids.len() as i32, n, "bounds {lo}..{hi} buy {buy}");
            let cap = d.cap_in().unwrap();
            assert!(d.quote(cap).is_ok());
            assert_eq!(d.quote(cap + 1), Err(QuoteErr::TooLarge));
        }
    }
}

/* ---------------------------------------------------------- F10 ---------------------------------------------------------- */

/// F10: with COUNT_LAMPORTS the guard's g is the quote profit plus the executed legs' lamport delta (the block's
/// lamport_offset), and the CPI tip is taken on that g: NoProfit uses the same g.
#[test]
fn f10_lamport_offset_enters_the_no_profit_verdict() {
    let mut rng = Rng(910);
    let x = rng.key();
    let (ra, rx) = (100_000_000_000u64, 50_000_000_000_000u64);
    let legs = vec![cp_leg(&mut rng, false, true, ra, rx, x, 25), cp_leg(&mut rng, true, false, ra, rx * 95 / 100, x, 25)];
    let base = run(&legs, &[(0, 1)], &Route { cap: 10_000_000_000, e: 1_000, ..Default::default() });
    let p = base.modeled_profit as u64;
    let at = |min_profit: u64, lamports: i64, tip: Option<TipParams>| run(&legs, &[(0, 1)], &Route { cap: 10_000_000_000, e: 1_000, min_profit, lamports, tip, flags: SzFlags::EARLY_ABORT, ..Default::default() });
    assert_eq!(at(p, 0, None).outcome, Outcome::Sized);
    assert_eq!(at(p, -1, None).outcome, Outcome::NoProfit, "rent paid by the route counts against g");
    assert_eq!(at(p + 2_039_280, 2_039_280, None).outcome, Outcome::Sized, "lamports the route recovers count for g");
    assert_eq!(at(p + 2_039_281, 2_039_280, None).outcome, Outcome::NoProfit);
    // the tip is computed on g including the lamports: g = p − 1,000,000, tip 10% of g
    let t = TipParams { bps: 1_000, floor: 0, cap: u64::MAX };
    let g = p as i128 - 1_000_000;
    let net = g - g / 10;
    assert_eq!(at(net as u64, -1_000_000, Some(t)).outcome, Outcome::Sized);
    assert_eq!(at(net as u64 + 1, -1_000_000, Some(t)).outcome, Outcome::NoProfit);
    // the modeled profit stays the quote delta (what AXS1 records)
    assert_eq!(at(p, -1, None).modeled_profit, base.modeled_profit);
}

/* ---------------------------------------------------------- F14 ---------------------------------------------------------- */

/// F14: a candidate past a capacity (here the DLMM sell leg's walk budget, small sizes where one bin's rounding is
/// several units) steps back to the last feasible size, not just once by 1 ppm. The planned size executes and is
/// within the step-back tolerance of the true last feasible size; BASKET pairs keep their candidate too.
#[test]
fn f14_step_back_reaches_the_capacity() {
    let mut rng = Rng(914);
    let mut binding = 0;
    for case in 0..40 {
        let x = rng.key();
        let depth = rng.range(2_000, 60_000);
        let sellp = dlmm_pair(&mut rng, x, 100, 0, 30, depth, |s| s.base_factor = 1_000);
        let mut sell = dlmm_leg(&sellp, false);
        sell.desc.max_bins = 1 + (case % 4) as u8;
        // a constant-product buy leg far cheaper: the round trip rises through every bin the sell leg may read
        let p0 = dlmm_price(100, 0) as f64 / 18446744073709551616.0;
        let ra = rng.log(1_000_000, 1 << 30);
        let buy = cp_leg(&mut rng, case % 2 == 0, true, ra, (ra as f64 / (p0 * 0.7)) as u64, x, 25);
        let legs = vec![buy.clone(), sell.clone()];
        let v = views(&legs);
        let (l0, l1) = (any_leg(&legs[0], &v.refs[0]), any_leg(&legs[1], &v.refs[1]));
        let cap = 1 << 32;
        let r = run(&legs, &[(0, 1)], &Route { cap, e: 1, ..Default::default() });
        if r.outcome != Outcome::Sized { continue; }
        assert_eq!(exact(&l0, &l1, r.amount), Some(r.modeled_profit), "case {case}: planned size infeasible");
        let last = last_feasible(&l0, &l1, r.amount, cap);
        if last < cap {
            binding += 1;
            assert!(last - r.amount <= (last >> 24).max(1) * 2 + 2, "case {case}: planned {} but feasible up to {last}", r.amount);
        }
        // BASKET (one optimum per pair): the pair still contributes a candidate
        let bk = run(&[buy, sell.clone(), cp_leg(&mut rng, true, true, ra, ra, x, 25)], &[(0, 1), (2, 1)], &Route { cap, e: 1, ..Default::default() });
        assert!(bk.outcome == Outcome::Sized && bk.pair == 0, "case {case}: {bk:?}");
    }
    assert!(binding > 20, "{binding}");
}

/* ---------------------------------------------------- F4: the static CU bound ---------------------------------------------------- */

/// F4: `cu_bound` is defined for every block (no overflow), grows with the walk budgets and the number of pairs, and
/// is the budget-independent constant for routes without DLMM legs (the SBF measurements against it are in
/// sbf-check/cu-runner).
#[test]
fn f4_cu_bound_is_static_and_monotone() {
    use arbx_sizing::desc::{SizingBlock, LegDesc};
    let mk = |kinds: &[(Kind, u8)], pairs: &[(u8, u8)], flags: u8| {
        let mut legs = [LegDesc::placeholder(); 6];
        for (s, &(k, b)) in legs.iter_mut().zip(kinds) {
            *s = LegDesc::new(k, true);
            if k == Kind::Dlmm { s.n_bin_arrays = 5; s.max_bins = b; }
        }
        let mut p = [(0u8, 0u8); 3];
        for (s, q) in p.iter_mut().zip(pairs) { *s = *q; }
        SizingBlock { flags: SzFlags(flags), min_size: 1, engine_amount: 1, lamport_offset: 0, max_iters: 24, pairs: p, n_pairs: pairs.len() as u8,
            legs, n_legs: kinds.len() as u8, basket: pairs.len() > 1 }
    };
    let cp = arbx_sizing::cu_bound(&mk(&[(Kind::RayCpmm, 0), (Kind::RayAmmV4, 0)], &[(0, 1)], 0));
    assert!(cp < 40_000, "{cp}");
    let mut last = 0;
    for b in [1u8, 4, 16, 64, 255] {
        let v = arbx_sizing::cu_bound(&mk(&[(Kind::Dlmm, b), (Kind::RayCpmm, 0)], &[(0, 1)], 0));
        assert!(v > last);
        last = v;
    }
    let one = arbx_sizing::cu_bound(&mk(&[(Kind::Dlmm, 8), (Kind::Dlmm, 8), (Kind::Dlmm, 8), (Kind::Dlmm, 8)], &[(0, 1)], 0));
    let three = arbx_sizing::cu_bound(&mk(&[(Kind::Dlmm, 8), (Kind::Dlmm, 8), (Kind::Dlmm, 8), (Kind::Dlmm, 8)], &[(0, 1), (0, 2), (3, 1)], 0));
    assert!(three > one);
    let worst = arbx_sizing::cu_bound(&mk(&[(Kind::Dlmm, 255); 6], &[(0, 3), (1, 4), (2, 5)], SzFlags::SEARCH));
    assert!(worst < u64::MAX / 2);
}

//! SHRED FIRE (engine dip14, `--dip-shred-fire shadow|live`; ops/dip/speed/fixes/FIXES.md). The dip engine decides on the
//! EXECUTED feed; its wait behind the first shred sighting of the dump is FRA 2.2 ms median (p90 7.8), AMS 0.7, Firedancer
//! leaders 6.8 (ops/dip/speed/truth/SPEED_TRUTH.md). This module prices a dump from its shred-decoded tx and takes the same
//! IMIT1 / M2 decision the executed feed would take, so the engine can fire on the first sighting.
//!   * the sell: `classify` decodes every top-level pump sell of a followed token (dip::sell_of_ix: the 3 layouts validated on
//!     real triggers); anything else that can move the token's curve (another pump instruction, a router, an unknown program)
//!     makes the tx unpriceable for that token
//!   * the price: pump's exact integer sell (dip::pump_sell_quote) on the token's book, i.e. the executed feed's newest trade.
//!     The book is exact only while no other tx on the token, seen earlier on a shred feed, is unconfirmed (`Tracker`)
//!   * the tx index: the one input a shred feed does not give. The decision is taken for EVERY index the dump can have
//!     ([i_lo, i_hi], `index_range`): the IMIT1 / M2 features that depend on it are monotone in it and the GBDTs are scored on
//!     intervals (score_bounds). A pick for every index can fire; a no-pick for every index is a sure skip; anything else
//!     waits for the executed feed (today's path), so the index can never make a shred decision differ from the executed one.
//! Pure parts only (unit tests below; the parity replay of the raw recording is `parity::shred_parity_on_recording`); the
//! engine wiring is src/bin/snipe_engine/shredfire.rs.
use crate::dip::{self, DirectSell, MIN_SELL};
use crate::dip_imit::{self as di, Dump, Imit, TokenBook, T};
use crate::dip_model as dm;
use crate::tx::{b58, Pk, Tx};
use rustc_hash::FxHashMap;
use std::collections::{HashSet, VecDeque};
use std::sync::LazyLock;

/// --dip-shred-fire
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode { Shadow, Live }

impl Mode {
    pub fn parse(s: &str) -> Result<Mode, String> {
        match s { "shadow" => Ok(Mode::Shadow), "live" => Ok(Mode::Live), x => Err(format!("--dip-shred-fire {x}: shadow | live")) }
    }
    pub fn as_str(self) -> &'static str { match self { Mode::Shadow => "shadow", Mode::Live => "live" } }
}

/// the highest tx index the decision is checked up to when the index has no upper bound (no block holds 50,000 txs; the
/// block-position clock is then at 0.99998 of the slot, the features at their end-of-slot values)
pub const I_MAX: u32 = 50_000;
/// a tx seen on a shred feed and not confirmed by the executed feed within this long never executed (a skipped block):
/// it no longer blocks its tokens
pub const PEND_MAX_NS: u64 = 2_000_000_000;
/// signatures remembered as classified (one classification per signature, whatever feed sees it again)
pub const SEEN_MAX: usize = 200_000;
/// slots the executed feed's progress is kept for
pub const NSLOT: usize = 32;

/// programs whose instructions never move a pump curve: System, ComputeBudget, the two token programs, ATA, Memo (v1, v2),
/// Lighthouse (the slot / balance guards)
fn harmless(p: &Pk) -> bool {
    static H: LazyLock<Vec<Pk>> = LazyLock::new(|| {
        let mut v = vec![[0u8; 32], crate::tx::COMPUTE_BUDGET, *crate::pda::TOKEN_PROGRAM, *crate::pda::TOKEN_2022, *crate::pda::ATA_PROGRAM];
        for s in ["MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", "Memo1UhkJRfHyvLMcVucJwxXeuD728EqVDDwQDxFMNo", "L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"] {
            v.push(crate::tx::pk(s));
        }
        v
    });
    H.contains(p)
}

/// what a shred tx does to one followed token
#[derive(Clone, Debug, PartialEq)]
pub enum Touch {
    /// only these decodable pump sells of the token (instruction order) and harmless instructions list it; empty = it does not
    /// trade the token (e.g. an ATA create)
    Sells(Vec<DirectSell>),
    /// something that cannot be priced lists it: "pump_ix" (a pump buy / create / unknown layout), "other_program" (a router
    /// or any program not known harmless), "unresolved_program" (the program sits behind an unresolved lookup table)
    Other(&'static str),
}

impl Touch {
    /// it can move the token's curve
    pub fn trades(&self) -> bool { match self { Touch::Sells(v) => !v.is_empty(), Touch::Other(_) => true } }
}

/// the tx has lookup tables the feed did not resolve (a raw shred / entries feed): its accounts behind them are unknown
pub fn unresolved(tx: &Tx) -> bool { !tx.lookups.is_empty() && tx.loaded.is_none() }

/// the followed tokens a shred tx lists in a top-level instruction while the pump program is among its accounts, and what it
/// does to each (`Touch`). A token can only be traded through an instruction that lists its mint (pump's buys and sells all do).
pub fn classify(tx: &Tx, followed: &dyn Fn(&Pk) -> bool) -> Vec<(Pk, Touch)> {
    let mut out: Vec<(Pk, Touch)> = Vec::new();
    if tx.is_vote { return out; }
    let pump = *crate::snipe::PUMP;
    let has_pump = tx.keys.contains(&pump) || tx.loaded.as_ref().is_some_and(|(w, r)| w.contains(&pump) || r.contains(&pump));
    if !has_pump { return out; }
    let mut mints: Vec<Pk> = Vec::new();
    for ix in &tx.ixs {
        mints.clear();
        for &a in &ix.accounts {
            if let Some(k) = dip::account_at(tx, a as usize) { if followed(&k) && !mints.contains(&k) { mints.push(k); } }
        }
        if mints.is_empty() { continue; }
        let prog = dip::account_at(tx, ix.program as usize);
        let is_pump = prog == Some(pump);
        let sell = if is_pump { dip::sell_of_ix(tx, ix) } else { None };
        for &m in &mints {
            let idx = match out.iter().position(|e| e.0 == m) { Some(i) => i, None => { out.push((m, Touch::Sells(Vec::new()))); out.len() - 1 } };
            let bad: Option<&'static str> = if is_pump {
                match &sell {
                    Some(s) if s.mint == m => { if let Touch::Sells(v) = &mut out[idx].1 { v.push(s.clone()); } None }
                    _ => Some("pump_ix"),
                }
            } else {
                match prog { Some(p) if harmless(&p) => None, Some(_) => Some("other_program"), None => Some("unresolved_program") }
            };
            if let Some(w) = bad { if !matches!(out[idx].1, Touch::Other(_)) { out[idx].1 = Touch::Other(w); } }
        }
    }
    out
}

/// the signature key every engine map uses (first 8 bytes, big-endian: poh.log's sig8)
#[inline]
pub fn sig8(sig: &[u8; 64]) -> u64 { u64::from_be_bytes(sig[..8].try_into().unwrap()) }

/// The shred feeds' txs on followed tokens that the executed feed has not confirmed yet, the signatures already classified,
/// and the executed feed's progress per slot. One per engine (the event loop thread).
#[derive(Default)]
pub struct Tracker {
    /// per token: (sig8, first seen ns, slot) of each pending tx that can move its curve
    pend: FxHashMap<Pk, Vec<(u64, u64, u64)>>,
    /// per pending signature: its tokens
    sigs: FxHashMap<u64, Vec<Pk>>,
    /// classified signatures (sig8 -> first seen ns), oldest first in `seen_q`
    seen: FxHashMap<u64, u64>,
    seen_q: VecDeque<(u64, u64)>,
    /// signatures the executed feed confirmed (a late shred copy of an executed tx is never a new sighting)
    done: FxHashMap<u64, u64>,
    done_q: VecDeque<(u64, u64)>,
    /// (slot, highest tx index the executed feed delivered), newest NSLOT slots
    prog: VecDeque<(u64, u32)>,
    /// pending entries dropped because they never executed
    pub stale: u64,
}

impl Tracker {
    /// a shred sighting of `sig8` at `t`: true when it was neither classified before nor confirmed by the executed feed (then the
    /// caller classifies it now; it is remembered)
    pub fn first_sighting(&mut self, sig8: u64, t: u64) -> bool {
        if self.done.contains_key(&sig8) || self.seen.contains_key(&sig8) { return false; }
        self.seen.insert(sig8, t);
        self.seen_q.push_back((t, sig8));
        while self.seen_q.len() > SEEN_MAX { if let Some((_, k)) = self.seen_q.pop_front() { self.seen.remove(&k); } }
        true
    }

    /// `sig8` (seen at `t` in `slot`) can move these tokens' curves until the executed feed confirms it
    pub fn add_pending(&mut self, sig8: u64, t: u64, slot: u64, mints: &[Pk]) {
        if mints.is_empty() || self.done.contains_key(&sig8) { return; }
        for m in mints {
            let v = self.pend.entry(*m).or_default();
            if !v.iter().any(|x| x.0 == sig8) { v.push((sig8, t, slot)); }
        }
        self.sigs.insert(sig8, mints.to_vec());
    }

    /// the executed feed delivered `sig8` (succeeded or failed) in `slot`, at tx index `idx` when known: it is no longer pending,
    /// and the slot's progress moves on
    pub fn confirmed(&mut self, sig8: u64, slot: u64, idx: Option<u64>, t: u64) {
        if let Some(ms) = self.sigs.remove(&sig8) {
            for m in ms {
                if let Some(v) = self.pend.get_mut(&m) { v.retain(|x| x.0 != sig8); if v.is_empty() { self.pend.remove(&m); } }
            }
        }
        if self.done.insert(sig8, t).is_none() {
            self.done_q.push_back((t, sig8));
            while self.done_q.len() > SEEN_MAX { if let Some((_, k)) = self.done_q.pop_front() { self.done.remove(&k); } }
        }
        if let Some(i) = idx.and_then(|i| u32::try_from(i).ok()) {
            match self.prog.iter_mut().find(|p| p.0 == slot) {
                Some(p) => p.1 = p.1.max(i),
                None => {
                    let pos = self.prog.iter().position(|p| p.0 > slot).unwrap_or(self.prog.len());
                    // an older slot than every kept one is kept only while there is room
                    if pos > 0 || self.prog.len() < NSLOT { self.prog.insert(pos, (slot, i)); }
                    while self.prog.len() > NSLOT { self.prog.pop_front(); }
                }
            }
        }
    }

    /// the executed feed confirmed `sig8` already
    pub fn is_confirmed(&self, sig8: u64) -> bool { self.done.contains_key(&sig8) }

    /// pending txs on `mint` other than `except`
    pub fn pending_ahead(&self, mint: &Pk, except: u64) -> usize { self.pend.get(mint).map(|v| v.iter().filter(|x| x.0 != except).count()).unwrap_or(0) }

    /// the highest tx index the executed feed delivered in `slot`
    pub fn progress(&self, slot: u64) -> Option<u32> { self.prog.iter().find(|p| p.0 == slot).map(|p| p.1) }

    /// drop pending txs older than PEND_MAX_NS at `now` (never executed); -> how many
    pub fn prune(&mut self, now: u64) -> usize {
        let mut n = 0usize;
        let old: Vec<u64> = self.pend.values().flatten().filter(|x| now.saturating_sub(x.1) > PEND_MAX_NS).map(|x| x.0).collect();
        for s in old {
            if let Some(ms) = self.sigs.remove(&s) {
                n += 1;
                for m in ms { if let Some(v) = self.pend.get_mut(&m) { v.retain(|x| x.0 != s); if v.is_empty() { self.pend.remove(&m); } } }
            }
        }
        self.stale += n as u64;
        n
    }

    /// pending tokens / txs (status line)
    pub fn sizes(&self) -> (usize, usize) { (self.pend.len(), self.sigs.len()) }
}

/// the fee pair (protocol bps, creator bps) the token's next sell most likely carries: its newest trade with a nonzero protocol
/// fee (some flows' events report 0 / 0); (95, 30) when it has none. Used only for the buy's min_out (the guard)
pub fn fee_guess(book: &TokenBook) -> (u32, u32) {
    book.tr.iter().rev().filter(|t| !t.syn && t.fbps > 0).map(|t| (t.fbps, t.cbps)).next().unwrap_or((95, 30))
}

/// the trades a shred tx's sells of one token make, priced in instruction order from the book's newest post-trade state `pre`
/// (vsol, vtok) with pump's exact sell: the TradeEvent's sol / tok / vsol / vtok exactly when the book is exact and the sells
/// execute. user = the seller (its account position), fees = `fees`, at (s, i, j = order among them). None: a sell cannot be
/// priced (empty curve / overflow)
pub fn price_sells(pre: (u64, u64), sells: &[DirectSell], s: u64, i: u32, sig58: &str, fees: (u32, u32)) -> Option<Vec<T>> {
    let (mut v, mut k) = pre;
    let mut out = Vec::with_capacity(sells.len());
    for (j, x) in sells.iter().enumerate() {
        let (sol, v2, k2) = dip::pump_sell_quote(v, k, x.tokens)?;
        out.push(T { s, i, j: j as i32, sig: sig58.to_string(), user: b58(&x.seller), buy: false, sol, tok: x.tokens, vsol: v2, vtok: k2,
                     fbps: fees.0, cbps: fees.1, syn: false });
        v = v2; k = k2;
    }
    Some(out)
}

/// the seller's tokens per the book (its buys minus its sells of the token, executed trades only); a wallet can also hold tokens it
/// got by transfer, so this is a floor
pub fn seller_net(book: &TokenBook, user58: &str) -> i128 {
    book.tr.iter().filter(|t| !t.syn && t.user == user58).map(|t| if t.buy { t.tok as i128 } else { -(t.tok as i128) }).sum()
}

/// a priced sell that will fail on chain: the curve pays less than the seller's minimum (gross < min_sol: certain), or less after
/// pump's fees at `fees` (net < min_sol: likely)
pub fn slip_fail(sol: u64, min_sol: u64, fees: (u32, u32)) -> Option<&'static str> {
    if sol < min_sol { return Some("min_sol_gross"); }
    let net = sol.saturating_sub(dip::pump_fee(sol, fees.0 as u64)).saturating_sub(dip::pump_fee(sol, fees.1 as u64));
    if net < min_sol { Some("min_sol_net") } else { None }
}

/// the tx-index range [lo, hi] a dump first seen on a shred feed can have in slot `slot`:
///  * lo: after the token's newest trade when that is in the same slot (chain order); with `progress` = Some((the executed feed's
///    highest index in the slot, margin)) also >= that - margin (the executed feed delivers a slot nearly in order)
///  * hi: lo + `window` (window 0: I_MAX, i.e. anywhere up to the end of the slot)
pub fn index_range(book_last: Option<(u64, u32, i32)>, slot: u64, progress: Option<(u32, u32)>, window: u32) -> (u32, u32) {
    let mut lo = 0u32;
    if let Some((s, i, _)) = book_last { if s == slot { lo = lo.max(i.saturating_add(1)); } }
    if let Some((p, m)) = progress { lo = lo.max(p.saturating_sub(m)); }
    let hi = if window == 0 { I_MAX.max(lo) } else { lo.saturating_add(window) };
    (lo, hi)
}

/// what the decision needs besides the books (the engine's flags)
pub struct Gate<'a> {
    pub model: &'a Imit,
    pub cohort: &'a HashSet<String>,
    pub targets: &'a HashSet<String>,
    pub max_age_s: f64,
    /// the token's IMIT1 threshold (its dev-list tier or the run's)
    pub thr: f64,
    /// the token is on the dev list (IMIT1 decides it even with the M2 gate)
    pub dev: bool,
    pub m2: Option<&'a dm::Bundle>,
    pub m2_gate: bool,
    pub m2_min: f64,
    /// M2 scores the later big sells of a dump slot too (--dip-m2-extra)
    pub m2_extra: bool,
}

/// M2 at a shred dump
#[derive(Clone, Debug)]
pub struct M2Eval { pub score_lo: Option<f64>, pub bounds: Option<(f64, f64)>, pub feats: Option<[f64; dm::NF]>, pub skip: Option<&'static str> }

/// the decision on a shred dump
#[derive(Clone, Debug)]
pub struct Eval {
    /// the dump trade's index in the token's book (at the speculative push)
    pub k: usize,
    /// an M2 extra dump (a later big sell of a dump slot: no IMIT1 dump event)
    pub extra: bool,
    /// IMIT1 at i_lo (features, score, envelope, launch filter)
    pub d: Dump,
    pub i_lo: u32,
    pub i_hi: u32,
    /// IMIT1's time features at i_hi (TIME_FEATS order)
    pub tf_hi: [f64; 3],
    /// IMIT1 (lowest, highest) score over the index range; the envelope over it (Some: the same for every index)
    pub imit: (f64, f64),
    pub env: Option<bool>,
    pub m2: Option<M2Eval>,
    /// the engine's decision (envelope AND pass) at i_lo exactly
    pub pick_lo: bool,
    /// the engine's decision for EVERY index in [i_lo, i_hi]: Some(true) pick, Some(false) no pick, None it depends on the index
    pub pick: Option<bool>,
}

/// the engine's decision rule on a dump (dipmode: `if !d.env_ok { continue }`, then `pass`): the envelope, the launch filter, and
/// IMIT1's score >= the token's threshold on an IMIT1 dump event, or with the M2 gate (tokens off the dev list) M2's score
/// >= its minimum
pub fn pick_rule(env_ok: bool, launch_ok: bool, imit: f64, thr: f64, extra: bool, m2_decides: bool, m2: Option<f64>, m2_min: f64) -> bool {
    if !env_ok { return false; }
    if m2_decides { launch_ok && m2.is_some_and(|s| s >= m2_min) } else { launch_ok && imit >= thr && !extra }
}

/// The decision on the shred-priced dump trade `t` (its index set to i_lo) of a token, for every index in [t.i, i_hi]:
/// pushes `t` into the token's IMIT1 book and M2 state speculatively, takes the features / scores / bounds, and puts both back
/// exactly. None: `t` is not a dump (no IMIT1 dump event, and not an M2 extra dump) or not newer than the book's newest trade.
pub fn eval(book: &mut TokenBook, m2tok: Option<&mut dm::Tok>, t: &T, i_hi: u32, g: &Gate, mint58: &str) -> Option<Eval> {
    let none = |_s: u64| -> Option<u64> { None };
    let key = (t.s, t.i, t.j);
    if book.last_key().is_some_and(|l| l >= key) { return None; }
    let i_hi = i_hi.max(t.i);
    let ck = book.checkpoint();
    let dk = book.push(t.clone(), g.targets, g.max_age_s, &none);
    let extra_k = match dk {
        None if g.m2.is_some() && g.m2_extra && !t.buy && t.sol >= MIN_SELL => book.later_in_slot(key, g.max_age_s),
        _ => None,
    };
    let Some(k) = dk.or(extra_k) else { book.rollback(ck); return None };
    let d = book.dump(mint58, k, g.model, g.cohort, &none);
    let tf_hi = di::time_feats(&book.tr, k, i_hi, &none);
    let mut x_hi = d.feats;
    for (n, &j) in di::TIME_FEATS.iter().enumerate() { x_hi[j] = tf_hi[n]; }
    let imit = g.model.score_bounds(&d.feats, &x_hi);
    let env = g.model.envelope_bounds(&d.feats, &x_hi);
    book.rollback(ck);
    let m2 = g.m2.map(|b| {
        let Some(mt) = m2tok else { return M2Eval { score_lo: None, bounds: None, feats: None, skip: Some("no_history") } };
        let Ok(user) = bs58::decode(&t.user).into_vec().map_err(|_| ()).and_then(|v| <Pk>::try_from(v).map_err(|_| ())) else {
            return M2Eval { score_lo: None, bounds: None, feats: None, skip: Some("bad_user") };
        };
        let tr2 = dm::Tr { s: t.s, i: t.i, j: t.j, buy: t.buy, sol: t.sol, tok: t.tok, vsol: t.vsol, vtok: t.vtok, user };
        let Some(ck2) = mt.push_spec(&tr2, &b.sets) else { return M2Eval { score_lo: None, bounds: None, feats: None, skip: Some("not_newest") } };
        let r = match mt.features() {
            Ok(x) => {
                let s_lo = b.model.score(&x);
                let (sb, s2) = mt.time_feats_at(dm::arrival(t.s, i_hi));
                let mut xh = x;
                xh[dm::TIME_FEATS[0]] = sb;
                xh[dm::TIME_FEATS[1]] = s2;
                M2Eval { score_lo: Some(s_lo), bounds: Some(b.model.score_bounds(&x, &xh)), feats: Some(x), skip: None }
            }
            Err(w) => M2Eval { score_lo: None, bounds: None, feats: None, skip: Some(w.as_str()) },
        };
        mt.rollback(ck2);
        r
    });
    let extra = dk.is_none();
    let m2_decides = g.m2_gate && !g.dev && g.m2.is_some();
    let pick_lo = pick_rule(d.env_ok, d.launch_ok, d.score, g.thr, extra, m2_decides, m2.as_ref().and_then(|m| m.score_lo), g.m2_min);
    // the decision over the whole index range
    let pick = if !d.launch_ok || env == Some(false) { Some(false) }
        else if m2_decides {
            match m2.as_ref().and_then(|m| m.bounds) {
                None => Some(false),                                         // never scored: never a pick
                Some((lo, _)) if lo >= g.m2_min && env == Some(true) => Some(true),
                Some((_, hi)) if hi < g.m2_min => Some(false),
                _ => None,
            }
        } else if extra { Some(false) }
        else if imit.0 >= g.thr && env == Some(true) { Some(true) }
        else if imit.1 < g.thr { Some(false) }
        else { None };
    Some(Eval { k, extra, d, i_lo: t.i, i_hi, tf_hi, imit, env, m2, pick_lo, pick })
}

/// the guard's min tokens out on the post-dump curve (dipmode's FIRE: spend after the fee pair, the quote, divided by the guard)
pub fn guard_min_out(spend: u64, vsol: u64, vtok: u64, fees: (u32, u32), guard: f64) -> u64 {
    let fr = (fees.0 + fees.1).max(1) as f64 / 1e4;
    let xin = (spend as f64 / (1.0 + fr)) as u128;
    let q = (vtok as u128 * xin / (vsol as u128 + xin)) as f64;
    ((q / guard).floor() as u64).max(1)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tx::{Ix, Lookup};

    fn k(n: u8) -> Pk { [n; 32] }

    /// a tx: static keys, instructions (program index, account indexes, data)
    fn tx(keys: Vec<Pk>, ixs: Vec<(u8, Vec<u8>, Vec<u8>)>) -> Tx {
        Tx { keys, ixs: ixs.into_iter().map(|(p, a, d)| Ix { program: p, accounts: a, data: d }).collect(), ..Default::default() }
    }

    fn sell_data(layout: usize, tokens: u64, min_sol: u64) -> Vec<u8> {
        let mut d = dip::SELL_LAYOUTS[layout].0.to_vec();
        d.extend(tokens.to_le_bytes());
        d.extend(min_sol.to_le_bytes());
        d
    }

    /// classify: a plain sell, two sells, a buy (pump_ix), a router (other_program), harmless only (an ATA create), an unfollowed
    /// token, no pump program, a lookup-table program, and a sell's mint behind a resolved lookup table
    #[test]
    fn classify_cases() {
        let pump = *crate::snipe::PUMP;
        let (mint, mint2, seller, other) = (k(7), k(8), k(9), k(10));
        let followed = |p: &Pk| *p == mint || *p == mint2;
        // layout 0: mint at account 2, seller at 6
        let accts0 = |m: u8, s: u8| vec![0, 0, m, 0, 0, 0, s];
        let keys = vec![seller, pump, mint, *crate::pda::ATA_PROGRAM, other, mint2];
        let t1 = tx(keys.clone(), vec![(1, accts0(2, 0), sell_data(0, 5_000, 1))]);
        assert_eq!(classify(&t1, &followed), vec![(mint, Touch::Sells(vec![DirectSell { mint, seller, tokens: 5_000, min_sol: 1 }]))]);
        let t2 = tx(keys.clone(), vec![(1, accts0(2, 0), sell_data(0, 5, 1)), (1, accts0(2, 0), sell_data(0, 6, 2))]);
        match &classify(&t2, &followed)[0].1 { Touch::Sells(v) => assert_eq!(v.iter().map(|s| s.tokens).collect::<Vec<_>>(), vec![5, 6]), x => panic!("{x:?}") }
        // a pump buy listing the mint: unpriceable
        let mut buy = vec![0x66u8, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea]; buy.extend([0u8; 16]);
        let t3 = tx(keys.clone(), vec![(1, accts0(2, 0), sell_data(0, 5, 1)), (1, vec![0, 0, 2], buy)]);
        assert_eq!(classify(&t3, &followed)[0].1, Touch::Other("pump_ix"));
        // a router listing the mint
        let t4 = tx(keys.clone(), vec![(4, vec![1, 2], vec![1, 2, 3])]);
        assert_eq!(classify(&t4, &followed)[0].1, Touch::Other("other_program"));
        // harmless only: an ATA create listing the mint -> listed, no trade
        let t5 = tx(keys.clone(), vec![(3, vec![0, 2], vec![1])]);
        assert_eq!(classify(&t5, &followed), vec![(mint, Touch::Sells(vec![]))]);
        assert!(!classify(&t5, &followed)[0].1.trades());
        // other token sold, our followed token only listed by an ATA create in the same tx
        let t6 = tx(keys.clone(), vec![(1, accts0(5, 0), sell_data(0, 9, 1)), (3, vec![0, 2], vec![1])]);
        let c6 = classify(&t6, &followed);
        assert_eq!(c6.len(), 2);
        assert!(c6.iter().any(|(m, t)| *m == mint2 && t.trades()) && c6.iter().any(|(m, t)| *m == mint && !t.trades()));
        // no pump program among the accounts: nothing
        let t7 = tx(vec![seller, other, mint], vec![(1, vec![2], vec![1])]);
        assert!(classify(&t7, &followed).is_empty());
        // a sell whose mint sits behind a RESOLVED lookup table (deshred feeds resolve them)
        let mut t8 = tx(vec![seller, pump], vec![(1, vec![0, 0, 2, 0, 0, 0, 0], sell_data(0, 77, 3))]);
        t8.lookups = vec![Lookup { table: k(99), writable: vec![0], readonly: vec![] }];
        t8.loaded = Some((vec![mint], vec![]));
        assert_eq!(classify(&t8, &followed), vec![(mint, Touch::Sells(vec![DirectSell { mint, seller, tokens: 77, min_sol: 3 }]))]);
        assert!(!unresolved(&t8));
        t8.loaded = None;
        assert!(unresolved(&t8));
        assert!(classify(&t8, &followed).is_empty(), "an unresolved mint is not seen");
        // a vote: nothing
        let mut t9 = t1.clone(); t9.is_vote = true;
        assert!(classify(&t9, &followed).is_empty());
    }

    /// REAL txs (testdata/dip_sells.json: wire bytes of dip triggers incl. lookup tables and a 12-sell tx, their own instructions'
    /// sells and TradeEvents): classify finds exactly the decoded sells of every token a tx sells (or marks it unpriceable when
    /// something else lists the token), and pump's integer sell from each single-sell tx's pre-state gives the TradeEvent's sol,
    /// vsol and vtok EXACTLY
    #[test]
    fn classify_and_price_real_txs() {
        use base64::Engine as _;
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(fx) = std::fs::read_to_string(format!("{root}/testdata/dip_sells.json")).ok().and_then(|s| serde_json::from_str::<serde_json::Value>(&s).ok()) else { return; };
        let (mut n_tx, mut n_sells, mut n_other, mut n_priced) = (0, 0, 0, 0);
        for f in fx.as_array().unwrap() {
            let wire = base64::engine::general_purpose::STANDARD.decode(f["wire_b64"].as_str().unwrap()).unwrap();
            let (mut tx, _) = crate::tx::parse_wire(&wire).expect("parse_wire");
            let pks = |k: &str| -> Vec<Pk> { f["loaded"][k].as_array().map(|a| a.iter().map(|x| crate::tx::pk(x.as_str().unwrap())).collect()).unwrap_or_default() };
            let (w, r) = (pks("writable"), pks("readonly"));
            if !w.is_empty() || !r.is_empty() { tx.loaded = Some((w, r)); }
            let want = dip::direct_sells(&tx);
            let mints: Vec<Pk> = want.iter().map(|s| s.mint).collect();
            let got = classify(&tx, &|m| mints.contains(m));
            for m in &mints {
                let (_, t) = got.iter().find(|(x, _)| x == m).expect("a sold token is listed");
                match t {
                    Touch::Sells(v) => { assert_eq!(v, &want.iter().filter(|s| s.mint == *m).cloned().collect::<Vec<_>>()); n_sells += v.len(); }
                    Touch::Other(_) => n_other += 1,
                }
            }
            // exact price: one sell, one event
            let logs: Vec<String> = f["logs"].as_array().unwrap().iter().map(|x| x.as_str().unwrap().to_string()).collect();
            let ev = dip::trade_events(&logs);
            if want.len() == 1 && ev.len() == 1 && !ev[0].buy {
                let e = &ev[0];
                let pre = (e.vsol + e.sol, e.vtok - e.tok);
                let p = price_sells(pre, &want, 1, 0, "x", (95, 30)).unwrap();
                assert_eq!((p[0].sol, p[0].vsol, p[0].vtok, p[0].tok), (e.sol, e.vsol, e.vtok, e.tok), "exact pump sell on {}", f["sig"]);
                assert_eq!(p[0].user, b58(&e.user), "the seller from its account position = the event's user");
                n_priced += 1;
            }
            n_tx += 1;
        }
        eprintln!("real txs: {n_tx} classified, {n_sells} sells found as the decoder finds them, {n_other} token(s) unpriceable (something else lists them), {n_priced} priced exactly");
        assert!(n_tx >= 5 && n_priced >= 3);
    }

    /// the tracker: pending per token, cleared by the executed feed (ok or failed), no double classification, late shred copies
    /// of executed txs ignored, stale entries pruned, progress per slot
    #[test]
    fn tracker_lifecycle() {
        let (a, b) = (k(1), k(2));
        let mut tr = Tracker::default();
        assert!(tr.first_sighting(11, 100));
        assert!(!tr.first_sighting(11, 101), "a second feed's copy is not a new sighting");
        tr.add_pending(11, 100, 50, &[a, b]);
        tr.add_pending(12, 110, 50, &[a]);
        assert_eq!(tr.pending_ahead(&a, 12), 1);
        assert_eq!(tr.pending_ahead(&a, 99), 2);
        assert_eq!(tr.pending_ahead(&b, 11), 0);
        tr.confirmed(11, 50, Some(30), 120);
        assert_eq!(tr.pending_ahead(&a, 99), 1);
        assert_eq!(tr.pending_ahead(&b, 99), 0);
        assert_eq!(tr.progress(50), Some(30));
        tr.confirmed(13, 50, Some(25), 121);
        assert_eq!(tr.progress(50), Some(30), "progress is the highest index");
        tr.confirmed(14, 51, Some(3), 122);
        tr.confirmed(15, 49, Some(9), 123);
        assert_eq!((tr.progress(49), tr.progress(51)), (Some(9), Some(3)));
        // a shred copy of an executed tx is no sighting
        assert!(!tr.first_sighting(14, 130));
        tr.add_pending(14, 130, 51, &[a]);
        assert_eq!(tr.pending_ahead(&a, 99), 1, "an executed tx never becomes pending");
        // stale
        assert_eq!(tr.prune(110 + PEND_MAX_NS), 0);
        assert_eq!(tr.prune(111 + PEND_MAX_NS), 1);
        assert_eq!(tr.pending_ahead(&a, 99), 0);
        assert_eq!(tr.stale, 1);
        assert_eq!(tr.sizes(), (0, 0));
    }

    /// pricing: pump's integer sell, chained over several sells; the min_sol checks; the index range; the guard
    #[test]
    fn pricing_range_guard() {
        let s = [DirectSell { mint: k(1), seller: k(2), tokens: 1_000_000_000_000, min_sol: 0 }, DirectSell { mint: k(1), seller: k(3), tokens: 7, min_sol: 0 }];
        let p = price_sells((40_000_000_000, 800_000_000_000_000), &s, 9, 4, "x", (95, 30)).unwrap();
        let sol0 = (1_000_000_000_000u128 * 40_000_000_000u128 / 801_000_000_000_000u128) as u64;
        assert_eq!((p[0].sol, p[0].vsol, p[0].vtok), (sol0, 40_000_000_000 - sol0, 801_000_000_000_000));
        let sol1 = (7u128 * p[0].vsol as u128 / (p[0].vtok as u128 + 7)) as u64;
        assert_eq!((p[1].sol, p[1].vsol, p[1].vtok, p[1].j, p[1].user.as_str()), (sol1, p[0].vsol - sol1, p[0].vtok + 7, 1, b58(&k(3)).as_str()));
        assert!(price_sells((0, 5), &s, 9, 4, "x", (95, 30)).is_none());
        assert_eq!(slip_fail(1_000, 1_001, (95, 30)), Some("min_sol_gross"));
        assert_eq!(slip_fail(1_000_000, 990_000, (95, 30)), Some("min_sol_net"));
        assert_eq!(slip_fail(1_000_000, 980_000, (95, 30)), None);
        assert_eq!(dip::pump_fee(1_000_001, 95), 9_501);
        assert_eq!(dip::pump_fee(1_000_000, 95), 9_500);
        assert_eq!(index_range(None, 5, None, 0), (0, I_MAX));
        assert_eq!(index_range(Some((5, 40, 0)), 5, None, 0), (41, I_MAX));
        assert_eq!(index_range(Some((4, 40, 0)), 5, None, 0), (0, I_MAX));
        assert_eq!(index_range(Some((5, 40, 0)), 5, Some((100, 40)), 30), (60, 90));
        assert_eq!(index_range(Some((5, 70, 0)), 5, Some((100, 40)), 30), (71, 101));
        // the guard = dipmode's FIRE expression
        let (spend, vsol, vtok, guard) = (350_000_000u64, 33_000_000_000u64, 970_000_000_000_000u64, 1.05);
        let fr = (95u32 + 30).max(1) as f64 / 1e4;
        let xin = (spend as f64 / (1.0 + fr)) as u128;
        let q = (vtok as u128 * xin / (vsol as u128 + xin)) as f64;
        assert_eq!(guard_min_out(spend, vsol, vtok, (95, 30), guard), ((q / guard).floor() as u64).max(1));
        assert_eq!(guard_min_out(spend, vsol, vtok, (0, 0), guard), {
            let xin = (spend as f64 / (1.0 + 1.0 / 1e4)) as u128; let q = (vtok as u128 * xin / (vsol as u128 + xin)) as f64; ((q / guard).floor() as u64).max(1) });
    }

    /// pick_rule = dipmode's `env_ok` + `pass` on every combination
    #[test]
    fn pick_rule_truth_table() {
        for env in [false, true] { for lok in [false, true] { for sc in [0.1, 0.9] { for extra in [false, true] { for gate in [false, true] { for m2 in [None, Some(0.0), Some(0.02)] {
            let thr = 0.5; let m2min = 0.01;
            // dipmode: if !env_ok continue; pass = launch_ok && score >= thr; pass = match gate { true => launch_ok && m2 >= min, false => pass && !extra }
            let pass = lok && sc >= thr;
            let pass = if gate { lok && m2.is_some_and(|s: f64| s >= m2min) } else { pass && !extra };
            assert_eq!(pick_rule(env, lok, sc, thr, extra, gate, m2, m2min), env && pass);
        } } } } } }
    }
}

/// PARITY on the raw recording (the brief's acceptance test): every pump tx of the 10-24 recording in chain order, through the
/// engine's own books exactly as dipmode feeds them (IMIT1 TokenBook + M2 state per token created in the recording), and at every
/// big sell, BEFORE its executed trade enters the books, the shred path as it would run on the first sighting: price the sell
/// from the book (pump's integer sell on the token amount), guess its fee pair, decide (eval) with the index known (the plumbing
/// must give the executed decision exactly) and with the index unknown (the deployable rule: the decision must hold for every
/// index the dump can have). Run by hand (reads ~8 GB of gzip through `zcat`):
///   SHRED_PARITY_DIR=/home/moiz/sniper-data/collect/run_20261024_1425 [SHRED_PARITY_FILES=N] [SHRED_PARITY_OUT=file.json] \
///   cargo test --release --lib shred_parity_on_recording -- --ignored --nocapture
#[cfg(test)]
mod parity {
    use super::*;
    use std::collections::HashMap;
    use std::io::BufRead;

    #[derive(serde::Deserialize)]
    struct Row { s: u64, i: u64, sig: String, #[serde(default)] err: Option<serde_json::Value>, #[serde(default)] ev: Vec<String>, #[serde(default)] ixn: Vec<String>,
                 #[serde(default)] mints: Vec<String> }

    struct Tk { book: TokenBook, m2: dm::Tok, slot0: u64, dev: bool }

    #[derive(Default, Debug, serde::Serialize)]
    struct Cnt {
        files: usize, rows: u64, rows_failed: u64, slot_inversions: u64, tokens: u64, trades: u64,
        /// big sells (event sol >= 1 SOL) of followed tokens = shred candidates
        big_sells: u64,
        /// the book's newest post-state = the event's pre-state (no trade missing from the recording before it)
        continuous: u64,
        /// of the continuous ones: shred-priced sol / vsol / vtok == the event's
        priced_exact: u64, priced_wrong: u64,
        /// the fee pair guess == the event's
        fee_exact: u64, fee_wrong: u64, fee_pairs_wrong: HashMap<String, u64>,
        /// guard min_out (0.35 SOL, x1.05) shred == executed
        min_out_exact: u64, min_out_wrong: u64, min_out_rel_max: f64,
        /// executed dump events (IMIT1 dump or M2 extra) among the continuous big sells, and the shred eval found the same event
        exec_dumps: u64, shred_same_event: u64, shred_event_differs: u64,
        /// index KNOWN (i = the true index): features equal, decisions equal (IMIT1 mode, M2-gate mode)
        feats_equal: u64, feats_differ: u64, m2_feats_equal: u64, m2_feats_differ: u64,
        dec_equal_imit: u64, dec_differ_imit: u64, dec_equal_gate: u64, dec_differ_gate: u64,
        /// index UNKNOWN (deployable rule, range [after the token's newest trade of the slot, end of slot]):
        /// robust pick / robust no-pick / depends, per mode, and robust decisions that DIFFER from the executed one (must be 0)
        imit_pick: u64, imit_nopick: u64, imit_depends: u64, imit_depends_exec_pick: u64, imit_wrong: u64, imit_exec_picks: u64,
        gate_pick: u64, gate_nopick: u64, gate_depends: u64, gate_depends_exec_pick: u64, gate_wrong: u64, gate_exec_picks: u64,
        /// the same with the index known to [truth - 40, truth + W] (what an index estimate would give), W = 10, 20, 40, 80, 160:
        /// robust picks among the executed picks
        imit_pick_w: [u64; 5], gate_pick_w: [u64; 5],
        /// a trade of the same token earlier in the same slot within K txs of the dump (likely still unconfirmed when the dump is
        /// first seen on a shred feed: the shred path then waits): K = 5, 10, 20, 40, of executed dump events
        pend5: u64, pend10: u64, pend20: u64, pend40: u64,
        /// failed sell txs (ixn has a Sell) listing a followed token: what a shred feed shows that never trades
        failed_sells_followed: u64,
        /// big sells that are not the token's first trade in their tx (a multi-trade tx: the live shred path prices a tx's sells of a
        /// token together and waits on anything else; not simulated here)
        multi_trade_tx: u64,
        /// the seller holds fewer tokens than it sells per the book (a sell the shred path would skip as seller_short): among the
        /// executed dumps, and among the executed picks (IMIT1 / gate): the coverage that check costs
        seller_short_dumps: u64, seller_short_picks_imit: u64, seller_short_picks_gate: u64,
        /// time per shred eval (µs, index unknown, IMIT1 + M2): p50 / p99
        eval_us_p50: f64, eval_us_p99: f64,
    }

    fn pk_of(s: &str) -> Option<Pk> { bs58::decode(s).into_vec().ok().and_then(|v| v.try_into().ok()) }
    const WS: [u32; 5] = [10, 20, 40, 80, 160];

    #[test]
    #[ignore]
    fn shred_parity_on_recording() {
        use base64::Engine as _;
        let Ok(dir) = std::env::var("SHRED_PARITY_DIR") else { eprintln!("SHRED_PARITY_DIR not set: skipped"); return; };
        let nfiles: usize = std::env::var("SHRED_PARITY_FILES").ok().and_then(|v| v.parse().ok()).unwrap_or(usize::MAX);
        let model = Imit::load("/home/moiz/sniper/ops/overnight/sel/IMIT1.json").expect("IMIT1.json");
        let cohort: HashSet<String> = serde_json::from_str::<Vec<String>>(&std::fs::read_to_string("/home/moiz/sniper/ops/overnight/sel/cohort_train.json").unwrap()).unwrap().into_iter().collect();
        let targets: HashSet<String> = di::TARGETS.iter().map(|s| s.to_string()).collect();
        let bundle = dm::Bundle::load("/home/moiz/sniper/testdata/dip_m2_bundle.json").expect("M2 bundle");
        // the live runs' dev list (FRA run 15's run_start)
        let devs: HashSet<String> = std::fs::read_to_string("/home/moiz/sniper-data/recon/live/dip_r15.jsonl").ok()
            .and_then(|t| t.lines().next().and_then(|l| serde_json::from_str::<serde_json::Value>(l).ok()))
            .and_then(|v| v["devs"].as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(|s| s.to_string())).collect())).unwrap_or_default();
        let thr = model.thresholds["top4"];
        let (spend, guard, max_age) = (350_000_000u64, 1.05f64, 1800.0f64);
        let mut files: Vec<std::path::PathBuf> = std::fs::read_dir(format!("{dir}/txs")).unwrap().filter_map(|e| e.ok().map(|e| e.path()))
            .filter(|p| p.to_string_lossy().ends_with(".jsonl.gz")).collect();
        files.sort();
        files.truncate(nfiles);
        let none = |_s: u64| -> Option<u64> { None };
        let mut toks: HashMap<Pk, Tk> = HashMap::new();
        let mut c = Cnt::default();
        let mut eval_us: Vec<f64> = Vec::new();
        let (mut last_key, mut last_prune) = ((0u64, 0u64), 0u64);
        // the same slot's trades per token (index), for the pending-ahead estimate
        let mut slot_tr: HashMap<Pk, (u64, Vec<u64>)> = HashMap::new();
        for f in &files {
            c.files += 1;
            let mut child = std::process::Command::new("zcat").arg(f).stdout(std::process::Stdio::piped()).spawn().expect("zcat");
            let rd = std::io::BufReader::with_capacity(1 << 20, child.stdout.take().unwrap());
            for line in rd.lines() {
                let Ok(line) = line else { break };
                let Ok(r) = serde_json::from_str::<Row>(&line) else { continue };
                c.rows += 1;
                if (r.s, r.i) < last_key { c.slot_inversions += 1; }
                last_key = (r.s, r.i);
                if r.s > last_prune + 2_000 {
                    last_prune = r.s;
                    toks.retain(|_, t| r.s.saturating_sub(t.slot0) < 9_906);   // the engine keeps a token max_age + 300 s
                    slot_tr.retain(|_, v| v.0 + 2 > r.s);
                }
                if r.err.is_some() {
                    c.rows_failed += 1;
                    if r.ixn.iter().any(|x| x.starts_with("Sell")) && r.mints.iter().filter_map(|m| pk_of(m)).any(|m| toks.contains_key(&m)) { c.failed_sells_followed += 1; }
                    continue;
                }
                let mut trades: Vec<dip::TradeEvent> = Vec::new();
                let mut creates: Vec<dip::CreateEvent> = Vec::new();
                for e in &r.ev {
                    let Ok(b) = base64::engine::general_purpose::STANDARD.decode(e) else { continue };
                    if let Some(t) = dip::trade_event_raw(&b) { trades.push(t); } else if let Some(cr) = dip::create_event_raw(&b) { creates.push(cr); }
                }
                let mayhem = r.ixn.iter().any(|x| x == "InitializeMayhemState");
                for cr in &creates {
                    if toks.contains_key(&cr.mint) { continue; }
                    let (crs, us) = (b58(&cr.creator), b58(&cr.user));
                    let dev = devs.contains(&crs) || devs.contains(&us);
                    let li = di::LaunchInfo { slot: r.s, idx: Some(r.i as u32), creator: Some(crs), signer: Some(us), sig: r.sig.clone(), mayhem };
                    toks.insert(cr.mint, Tk { book: TokenBook::new(li), m2: dm::Tok::new(r.s), slot0: r.s, dev });
                    c.tokens += 1;
                }
                let mut in_tx: Vec<Pk> = Vec::new();
                for (j, e) in trades.iter().enumerate() {
                    let Some(tk) = toks.get_mut(&e.mint) else { continue };
                    c.trades += 1;
                    let first_in_tx = !in_tx.contains(&e.mint);
                    if first_in_tx { in_tx.push(e.mint); }
                    let mint58 = b58(&e.mint);
                    let user58 = b58(&e.user);
                    let texec = T { s: r.s, i: r.i as u32, j: j as i32, sig: r.sig.clone(), user: user58.clone(), buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok,
                                    fbps: e.fbps as u32, cbps: e.cbps as u32, syn: false };
                    // ---- the shred path, before the executed trade enters the books
                    let mut shred: Option<(Option<Eval>, Option<Eval>, Option<Eval>, Option<Eval>, Vec<(bool, bool)>, bool)> = None;
                    if !e.buy && e.sol >= MIN_SELL && !first_in_tx { c.multi_trade_tx += 1; }
                    if !e.buy && e.sol >= MIN_SELL && first_in_tx {
                        c.big_sells += 1;
                        if let Some(last) = tk.book.tr.last().cloned() {
                            let cont = (last.vsol, last.vtok) == (e.vsol.wrapping_add(e.sol), e.vtok.wrapping_sub(e.tok));
                            if cont {
                                c.continuous += 1;
                                let fees = fee_guess(&tk.book);
                                if fees == (e.fbps as u32, e.cbps as u32) { c.fee_exact += 1; } else { c.fee_wrong += 1; *c.fee_pairs_wrong.entry(format!("{:?}->{:?}", fees, (e.fbps, e.cbps))).or_default() += 1; }
                                let seller = e.user;
                                let sells = [DirectSell { mint: e.mint, seller, tokens: e.tok, min_sol: 0 }];
                                let p = price_sells((last.vsol, last.vtok), &sells, r.s, r.i as u32, &r.sig, fees).unwrap();
                                let exact = (p[0].sol, p[0].vsol, p[0].vtok) == (e.sol, e.vsol, e.vtok);
                                if exact { c.priced_exact += 1; } else { c.priced_wrong += 1; }
                                let (mo_s, mo_e) = (guard_min_out(spend, p[0].vsol, p[0].vtok, fees, guard), guard_min_out(spend, e.vsol, e.vtok, (e.fbps as u32, e.cbps as u32), guard));
                                if mo_s == mo_e { c.min_out_exact += 1; } else { c.min_out_wrong += 1; c.min_out_rel_max = c.min_out_rel_max.max((mo_s as f64 / mo_e as f64 - 1.0).abs()); }
                                if exact {
                                    let mut t = p[0].clone();
                                    t.j = j as i32;
                                    let thr_t = thr;
                                    let mk = |gate: bool| Gate { model: &model, cohort: &cohort, targets: &targets, max_age_s: max_age, thr: thr_t, dev: tk.dev, m2: Some(&bundle),
                                                                  m2_gate: gate, m2_min: bundle.thr_default, m2_extra: true };
                                    let (gi, gg) = (mk(false), mk(true));
                                    // index known
                                    let known_i = eval(&mut tk.book, Some(&mut tk.m2), &t, t.i, &gi, &mint58);
                                    let known_g = eval(&mut tk.book, Some(&mut tk.m2), &t, t.i, &gg, &mint58);
                                    // index unknown (deployable): [after the token's newest trade of the slot, end of slot]
                                    let (lo, hi) = index_range(tk.book.last_key(), r.s, None, 0);
                                    let tu = T { i: lo, ..t.clone() };
                                    let t0 = std::time::Instant::now();
                                    let unk_i = eval(&mut tk.book, Some(&mut tk.m2), &tu, hi, &gi, &mint58);
                                    eval_us.push(t0.elapsed().as_secs_f64() * 1e6);
                                    let unk_g = eval(&mut tk.book, Some(&mut tk.m2), &tu, hi, &gg, &mint58);
                                    // index known to [truth - 40, truth + W]
                                    let lo40 = (t.i.saturating_sub(40)).max(lo);
                                    let tw = T { i: lo40, ..t.clone() };
                                    let mut wv: Vec<(bool, bool)> = Vec::new();
                                    for w in WS {
                                        let a = eval(&mut tk.book, Some(&mut tk.m2), &tw, t.i + w, &gi, &mint58).and_then(|e| e.pick) == Some(true);
                                        let b = eval(&mut tk.book, Some(&mut tk.m2), &tw, t.i + w, &gg, &mint58).and_then(|e| e.pick) == Some(true);
                                        wv.push((a, b));
                                    }
                                    let short = seller_net(&tk.book, &user58) < e.tok as i128;
                                    shred = Some((known_i, known_g, unk_i, unk_g, wv, short));
                                }
                            }
                        }
                    }
                    // ---- the executed path (dipmode)
                    let t2 = dm::Tr { s: r.s, i: r.i as u32, j: j as i32, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok, user: e.user };
                    let dump_k = tk.book.push(texec.clone(), &targets, max_age, &none);
                    let extra_k = if dump_k.is_none() && !e.buy && e.sol >= MIN_SELL { tk.book.later_in_slot((r.s, r.i as u32, j as i32), max_age) } else { None };
                    tk.m2.push(&t2, &bundle.sets);
                    if let Some(k) = dump_k.or(extra_k) {
                        let d = tk.book.dump(&mint58, k, &model, &cohort, &none);
                        let m2x = if d.env_ok { tk.m2.features().ok() } else { None };
                        let m2s = m2x.map(|x| bundle.model.score(&x));
                        let extra = dump_k.is_none();
                        let pick_i = pick_rule(d.env_ok, d.launch_ok, d.score, thr, extra, false, m2s, bundle.thr_default);
                        let pick_g = pick_rule(d.env_ok, d.launch_ok, d.score, thr, extra, !tk.dev, m2s, bundle.thr_default);
                        // pending-ahead estimate
                        if let Some((sl, v)) = slot_tr.get(&e.mint) { if *sl == r.s {
                            let near = |kk: u64| v.iter().any(|&x| x < r.i && x + kk >= r.i);
                            c.pend5 += near(5) as u64; c.pend10 += near(10) as u64; c.pend20 += near(20) as u64; c.pend40 += near(40) as u64;
                        } }
                        if let Some((ki, kg, ui, ug, wv, short)) = shred {
                            c.exec_dumps += 1;
                            if short { c.seller_short_dumps += 1; c.seller_short_picks_imit += pick_i as u64; c.seller_short_picks_gate += pick_g as u64; }
                            c.imit_exec_picks += pick_i as u64; c.gate_exec_picks += pick_g as u64;
                            match &ki {
                                Some(ev) if ev.k == k && ev.extra == extra => {
                                    c.shred_same_event += 1;
                                    if ev.d.feats.iter().zip(d.feats.iter()).all(|(a, b)| a.to_bits() == b.to_bits()) && ev.d.score.to_bits() == d.score.to_bits() { c.feats_equal += 1; } else { c.feats_differ += 1; }
                                    let mf = ev.m2.as_ref().and_then(|m| m.feats);
                                    if d.env_ok { if mf.map(|x| x.map(f64::to_bits)) == m2x.map(|x| x.map(f64::to_bits)) { c.m2_feats_equal += 1; } else { c.m2_feats_differ += 1; } }
                                    if ev.pick_lo == pick_i { c.dec_equal_imit += 1; } else { c.dec_differ_imit += 1; }
                                    if let Some(g) = &kg { if g.pick_lo == pick_g { c.dec_equal_gate += 1; } else { c.dec_differ_gate += 1; } }
                                }
                                _ => c.shred_event_differs += 1,
                            }
                            for (ev, exec_pick, gate) in [(&ui, pick_i, false), (&ug, pick_g, true)] {
                                let r = ev.as_ref().and_then(|e| e.pick);
                                let (pk, np, dep, dep_ep, wrong) = if gate { (&mut c.gate_pick, &mut c.gate_nopick, &mut c.gate_depends, &mut c.gate_depends_exec_pick, &mut c.gate_wrong) }
                                    else { (&mut c.imit_pick, &mut c.imit_nopick, &mut c.imit_depends, &mut c.imit_depends_exec_pick, &mut c.imit_wrong) };
                                match (ev, r) {
                                    (None, _) => { if exec_pick { *wrong += 1; } else { *np += 1; } }
                                    (Some(_), Some(true)) => { *pk += 1; if !exec_pick { *wrong += 1; } }
                                    (Some(_), Some(false)) => { *np += 1; if exec_pick { *wrong += 1; } }
                                    (Some(_), None) => { *dep += 1; if exec_pick { *dep_ep += 1; } }
                                }
                            }
                            for (n, (a, b)) in wv.iter().enumerate() { if *a && pick_i { c.imit_pick_w[n] += 1; } if *b && pick_g { c.gate_pick_w[n] += 1; } }
                        }
                    }
                    let e2 = slot_tr.entry(e.mint).or_insert((r.s, Vec::new()));
                    if e2.0 != r.s { *e2 = (r.s, Vec::new()); }
                    e2.1.push(r.i);
                }
            }
            let _ = child.wait();
            eprintln!("shred parity: {} file(s), {} rows, {} big sells, {} exec dumps, priced exact {} / wrong {}, imit pick/nopick/depends {}/{}/{} wrong {}, gate {}/{}/{} wrong {}",
                c.files, c.rows, c.big_sells, c.exec_dumps, c.priced_exact, c.priced_wrong, c.imit_pick, c.imit_nopick, c.imit_depends, c.imit_wrong,
                c.gate_pick, c.gate_nopick, c.gate_depends, c.gate_wrong);
        }
        eval_us.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let q = |p: f64| eval_us.get(((eval_us.len().max(1) - 1) as f64 * p) as usize).copied().unwrap_or(0.0);
        c.eval_us_p50 = q(0.5); c.eval_us_p99 = q(0.99);
        let js = serde_json::to_string_pretty(&c).unwrap();
        eprintln!("{js}");
        if let Ok(out) = std::env::var("SHRED_PARITY_OUT") { std::fs::write(&out, &js).unwrap(); }
        // the acceptance checks
        assert_eq!(c.priced_wrong, 0, "a continuous book priced a sell wrong");
        assert_eq!(c.dec_differ_imit + c.dec_differ_gate, 0, "index known: a shred decision differs from the executed one");
        assert_eq!(c.feats_differ, 0, "index known: IMIT1 features differ");
        assert_eq!(c.m2_feats_differ, 0, "index known: M2 features differ");
        assert_eq!(c.imit_wrong + c.gate_wrong, 0, "index unknown: a robust shred decision differs from the executed one");
    }
}

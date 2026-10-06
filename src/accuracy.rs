//! Accuracy monitor (PLAN WP-04 item 13; review F5). A decoded swap T is a hint: it is never priced (item 1), but its
//! predicted effect is checked against T's committed effect, which measures the venue maths.
//!
//! arb-lab predicted from the store at hint time; any earlier write to the pool (earlier in the same slot, say) then
//! made a correct prediction look "inexact" (DAMM v2 matched 662 of 758, res-code §3). Here each hint is scored when
//! T's commit group resolves, against T's **pre-state**: every account of the pool as it was just before T's first
//! write, from the store's version rings. The prediction is recomputed on that pre-state with T's decoded input
//! (`input_src` `decoded`; an executed input from the transaction's own meta is not carried to the engine yet) and
//! compared with T's post-state. A pre-state the ring no longer holds is `pre_state_unknown`, never scored. The
//! at-hint comparison (arb-lab's measure) is kept beside it (`hint`).
//!
//! The work runs on the engine thread at idle time (the timers' `TIMER_ACC` scope), from a bounded queue whose
//! overflow is counted. No quarantine acts in Stage 0 (`[accuracy] action = "log"`, OD-8).
//!
//! PLAN-ADDENDUM WP-16: the swap's amounts are arbx-sizing's (`src/quote.rs`, the quotes proven against the real
//! programs: limit-order layers, both DLMM fee modes, the PumpSwap buy debit and its "−1", CPMM's single fee ceil);
//! what they leave in the pool is the venue's bookkeeping below, checked against real swaps on the venue binaries
//! (program/venue-harness `capture_post` → testdata/venue-parity/real-swaps.json):
//! - AMM v4: the whole input enters the input vault, the output leaves the other (PnL owed is not touched);
//! - CPMM: the protocol and fund shares of the trade fee, and the creator fee, become owed (they leave the effective
//!   reserve); with the creator fee on the input the program takes ONE ceil of x·(trade+creator) and splits it
//!   (creator = ⌊total·creator/(trade+creator)⌋); on the output the creator fee is skimmed from the gross output;
//! - PumpSwap: the protocol and creator fees leave the quote vault (the LP fee stays): a sell pays out q − lp fee, a
//!   buy adds its debit minus them;
//! - DLMM: a bin's own amounts move by its market-making layer only (input side + the input that layer took, output
//!   side − what it gave); limit-order fills are booked in the order fields; the active id ends on the last bin the
//!   swap took from;
//! - DAMM v2: the crate's full port gives the pool after the swap (sqrt price).
use crate::quote::{self, Use, Why};
use crate::store::Acct;
use crate::tx::Pk;
use crate::venues::{i32_at, u128_at, u64_at, PoolMeta, Venue};
use arbx_sizing::venue::{ammv4, cpmm, dammv2, dlmm, pumpswap};
use arbx_sizing::AnyLeg;
use serde_json::{json, Value};
use std::collections::VecDeque;

/// A pool's state after a swap: what a prediction says, or what the chain committed
#[derive(Clone, Debug, PartialEq)]
pub enum Pred {
    /// effective reserves (vault minus what is owed)
    Cp { r0: u128, r1: u128 },
    /// the active bin and every bin the swap changed (bin, amount_x, amount_y)
    Dlmm { active: i32, bins: Vec<(i32, u64, u64)> },
    Damm { sqrt_price: u128 },
}

/// One decoded hint waiting for its transaction's commit
#[derive(Clone, Debug)]
pub struct Hint {
    pub txn: [u8; 64],
    /// registry index of the pool
    pub pool: usize,
    pub venue: Venue,
    pub zfo: bool,
    /// the decoded amount (input, or output when `exact_out`)
    pub amount: u64,
    pub exact_out: bool,
    /// the prediction made from the store when the hint arrived (arb-lab's measure)
    pub at_hint: Option<Pred>,
    pub slot: u64,
    pub t: u64,
    /// the accounts T wrote, with their versions (slot, write_version): its commit group's members, set when the group
    /// resolved (an account whose T-version the ring has since evicted is then known to be written, its pre-state lost)
    pub writes: Vec<(Pk, u64, u64)>,
}

/// What a pool's quote needs, from one set of account versions
pub struct View<'a> {
    pub get: &'a dyn Fn(&Pk) -> Option<&'a Acct>,
    pub arrays: &'a [(i64, Pk)],
    /// the Clock: DLMM and DAMM v2 fees, CPMM / AMM v4 open times; the slot the DAMM v2 fee schedule is evaluated at
    pub now_unix: i64,
    pub slot: u64,
}

/// why a prediction could not be made: an account the quote needs is missing (`Snapshot`), the swap does not quote
/// (`Quote`: the venue would refuse it, or arbx-sizing does not model the state: `Refused`), or a DLMM bin array the
/// walk needs has no version in `View` (`DlmmArray`: the pre-state is unknown)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NoPred { Snapshot, Quote, DlmmArray, Refused(&'static str) }

fn no_pred(w: Why) -> NoPred {
    match w {
        Why::Missing(Venue::Dlmm) | Why::DlmmArray => NoPred::DlmmArray,
        Why::Missing(_) => NoPred::Snapshot,
        Why::Unquotable(_) => NoPred::Quote,
        // a reason of the crate's (a state it refuses, a capacity it pins: `sz_*`), carried to the line and its counter
        // (WP-16 review F10)
        w => NoPred::Refused(w.reason()),
    }
}

fn token_amount(a: &Acct) -> Option<u64> { if a.data.len() >= 72 { u64_at(&a.data, 64) } else { None } }

/// How an exact-out swap is predicted (predictions.jsonl `exact_out_model`, WP-16 review F6): `exact` where arbx-sizing
/// models the venue's exact-out instruction (PumpSwap's `buy`), `solved` elsewhere: the output of the smallest exact-in
/// size that reaches the amount, not the venue's own exact-out rounding, so such a prediction is not exact by
/// construction and stays out of the per-venue exact rate. None for an exact-in swap
pub fn exact_out_model(venue: Venue, zfo: bool, exact_out: bool) -> Option<&'static str> {
    if !exact_out { None } else if venue == Venue::PumpSwap && !zfo { Some("exact") } else { Some("solved") }
}

/// The pool's predicted state after a swap of `amount` (exact out: `amount` is the output; the input is the debit the
/// venue computes where the crate models it, else the smallest input that buys `amount`), on `v`: the venue's own
/// execution of a third party's swap (`quote::Use::Third`). Ok: the prediction and the swap's input
pub fn predict(m: &PoolMeta, v: &View, zfo: bool, amount: u64, exact_out: bool) -> Result<(Pred, u64), NoPred> {
    let src = quote::Src { get: v.get, arrays: v.arrays, usable: &|_| true, clock: quote::clock(v.slot, v.now_unix) };
    let leg = quote::leg(m, zfo, &src, Use::Third).map_err(no_pred)?;
    // a DAMM v2 exact-out swap (swap2 mode 2) is priced from its output with its own rounding: not modelled
    if exact_out && m.venue == Venue::DammV2 { return Err(NoPred::Quote); }
    let get = |k: &Pk| (v.get)(k).ok_or(NoPred::Snapshot);
    // PumpSwap's exact-out `buy`: the base out exactly, for the debit the program computes (q into the curve plus the
    // fees on q; the protocol and creator fees leave the quote vault)
    if let (true, Some(r)) = (exact_out, leg.exact_out(amount)) {
        let (q, quote) = r.map_err(no_pred)?;
        let AnyLeg::Pump(p) = &leg.any else { return Err(NoPred::Quote) };
        let (b, qv) = (token_amount(get(&m.vault0)?).ok_or(NoPred::Snapshot)?, token_amount(get(&m.vault1)?).ok_or(NoPred::Snapshot)?);
        let fee = |bps: u64| cdiv(q as u128 * bps as u128, 10_000);
        let kept = (quote.spent as u128).checked_sub(fee(p.fees.protocol).ok_or(NoPred::Quote)? + fee(p.fees.creator).ok_or(NoPred::Quote)?).ok_or(NoPred::Quote)?;
        let base_left = (b as u128).checked_sub(quote.out as u128).ok_or(NoPred::Quote)?;
        return Ok((Pred::Cp { r0: base_left, r1: qv as u128 + kept }, quote.spent));
    }
    let amount_in = if exact_out { crate::venues::solve_exact_in(amount, |x| leg.quote(x).ok().map(|q| q.out)).ok_or(NoPred::Quote)? } else { amount };
    let pred = match &leg.any {
        AnyLeg::Dlmm(_) => {
            let mut fills: Vec<(i32, u64, u64)> = Vec::new();
            let w = leg.fills(amount_in, &mut |b| fills.push((b.id, b.paid[0], b.taken[0]))).ok_or(NoPred::Quote)?.map_err(no_pred)?;
            let mut bins = Vec::with_capacity(fills.len());
            for (id, paid, taken) in fills {
                let (x, y) = bin_of(v.arrays, v.get, id).ok_or(NoPred::DlmmArray)?;
                let (nx, ny) = if zfo { (x.checked_add(paid), y.checked_sub(taken)) } else { (x.checked_sub(taken), y.checked_add(paid)) };
                bins.push((id, nx.ok_or(NoPred::Quote)?, ny.ok_or(NoPred::Quote)?));
            }
            Pred::Dlmm { active: w.end, bins }
        }
        AnyLeg::Damm(_) => {
            // the full port: the pool exactly as the next swap reads it (the mints were scanned by `quote::leg`)
            let mut p = dammv2::decode(&get(&m.pool)?.data).ok_or(NoPred::Snapshot)?;
            p.transfer_fee_known_zero = true;
            let (_, after) = dammv2::swap_exact_in(&p, zfo, amount_in, v.slot, v.now_unix).map_err(|_| NoPred::Quote)?;
            Pred::Damm { sqrt_price: after.sqrt_price }
        }
        AnyLeg::Amm(a) => {
            let q = leg.quote(amount_in).map_err(no_pred)?;
            let (r_in, r_out) = (a.r_in as u128 + q.spent as u128, a.r_out as u128 - q.out as u128);
            if zfo { Pred::Cp { r0: r_in, r1: r_out } } else { Pred::Cp { r0: r_out, r1: r_in } }
        }
        AnyLeg::Cpmm(c) => {
            let q = leg.quote(amount_in).map_err(no_pred)?;
            let pool = get(&m.pool)?;
            let cfg = get(m.extra.first().ok_or(NoPred::Snapshot)?)?;
            let (r_in, r_out) = cpmm_post(&pool.data, &cfg.data, c, amount_in, q.out).ok_or(NoPred::Quote)?;
            if zfo { Pred::Cp { r0: r_in, r1: r_out } } else { Pred::Cp { r0: r_out, r1: r_in } }
        }
        AnyLeg::Pump(p) => {
            let q = leg.quote(amount_in).map_err(no_pred)?;
            let (b, qv) = (token_amount(get(&m.vault0)?).ok_or(NoPred::Snapshot)?, token_amount(get(&m.vault1)?).ok_or(NoPred::Snapshot)?);
            let (b2, q2) = pump_post(p, b, qv, amount_in, q.out, q.spent).ok_or(NoPred::Quote)?;
            Pred::Cp { r0: b2, r1: q2 }
        }
    };
    Ok((pred, amount_in))
}

/// ⌈a/b⌉
fn cdiv(a: u128, b: u128) -> Option<u128> { if b == 0 { None } else { Some(a.div_ceil(b)) } }

/// CPMM's effective reserves (in, out) after `x` in and `out` out (raydium-cp-swap `swap_base_input`): the protocol and
/// fund shares of the trade fee and the creator fee become owed
fn cpmm_post(pool: &[u8], cfg: &[u8], c: &cpmm::CpmmLeg, x: u64, out: u64) -> Option<(u128, u128)> {
    const RATE: u128 = 1_000_000;
    let rate = |o: usize| u64_at(cfg, o).map(|v| v as u128);
    let (t, p, f) = (rate(cpmm::off::C_TRADE)?, rate(cpmm::off::C_PROTOCOL)?, rate(cpmm::off::C_FUND)?);
    let creator = if *pool.get(cpmm::off::ENABLE_CREATOR_FEE)? != 0 { rate(cpmm::off::C_CREATOR)? } else { 0 };
    let x = x as u128;
    // arbx-sizing puts the creator fee on the output side (`fee_out`) exactly when the program skims it there
    let on_input = c.fee_out == 0;
    let (trade_fee, creator_in) = if on_input && creator > 0 {
        let total = cdiv(x * (t + creator), RATE)?;
        let cr = total * creator / (t + creator);
        (total - cr, cr)
    } else { (cdiv(x * t, RATE)?, 0) };
    let owed_in = trade_fee * p / RATE + trade_fee * f / RATE + creator_in;
    let r_in = (c.r_in as u128 + x).checked_sub(owed_in)?;
    let gone_out = if on_input { out as u128 } else {
        // the creator fee skimmed from the gross output stays owed: the effective reserve loses the gross
        let net = x - trade_fee;
        net * c.r_out as u128 / (c.r_in as u128 + net)
    };
    Some((r_in, (c.r_out as u128).checked_sub(gone_out)?))
}

/// PumpSwap's vaults (base, quote) after a swap: a sell (`p.sell`, base `x` in) pays `out` and sends the protocol and
/// creator fees out of the quote vault; a buy (`buy_exact_quote_in`, quote `x` in) adds its debit minus those fees.
/// The fees are each ⌈amount·bps/1e4⌉ on the swap's quote amount (DESIGN.md §2.1)
fn pump_post(p: &pumpswap::PumpLeg, base: u64, quote: u64, x: u64, out: u64, spent: u64) -> Option<(u128, u128)> {
    let fee = |amt: u128, bps: u64| cdiv(amt * bps as u128, 10_000);
    let (b, q) = (base as u128, quote as u128);
    if p.sell {
        let qq = p.qv as u128 * x as u128 / (b + x as u128);
        let gone = out as u128 + fee(qq, p.fees.protocol)? + fee(qq, p.fees.creator)?;
        Some((b + x as u128, q.checked_sub(gone)?))
    } else {
        let eff0 = x as u128 * 10_000 / (10_000 + p.fees.total());
        let kept = (spent as u128).checked_sub(fee(eff0, p.fees.protocol)? + fee(eff0, p.fees.creator)?)?;
        Some((b.checked_sub(out as u128)?, q + kept))
    }
}

/// (amount_x, amount_y) of bin `id` in the bin arrays `get` returns (layout: docs/spec-dlmm.md: 56-byte header, then
/// 70 bins of 144 bytes, amount_x u64 @0, amount_y u64 @8, price u128 @16)
fn bin_of<'a>(arrays: &[(i64, Pk)], get: &dyn Fn(&Pk) -> Option<&'a Acct>, id: i32) -> Option<(u64, u64)> {
    let ai = dlmm::array_index(id);
    let (_, k) = arrays.iter().find(|(i, _)| *i == ai)?;
    let a = get(k)?;
    let o = 56 + (id as i64 - ai * dlmm::BINS_PER_ARRAY) as usize * 144;
    let _ = u128_at(&a.data, o + 16)?;
    Some((u64_at(&a.data, o)?, u64_at(&a.data, o + 8)?))
}

/// The pool's effective reserves (token 0, token 1) in `v`: the vaults minus what is owed (AMM v4: PnL; CPMM: protocol,
/// fund and creator fees; PumpSwap: nothing)
fn reserves(m: &PoolMeta, v: &View) -> Option<(u128, u128)> {
    let (v0, v1) = (token_amount((v.get)(&m.vault0)?)? as u128, token_amount((v.get)(&m.vault1)?)? as u128);
    let p = &(v.get)(&m.pool)?.data;
    let g = |o: usize| u64_at(p, o).map(|x| x as u128);
    Some(match m.venue {
        Venue::RayAmmV4 => (v0.saturating_sub(g(ammv4::off::PNL_COIN)?), v1.saturating_sub(g(ammv4::off::PNL_PC)?)),
        Venue::RayCpmm => {
            use cpmm::off::*;
            (v0.saturating_sub(g(PROTOCOL0)? + g(FUND0)? + g(CREATOR0)?), v1.saturating_sub(g(PROTOCOL1)? + g(FUND1)? + g(CREATOR1)?))
        }
        Venue::PumpSwap => (v0, v1),
        Venue::Dlmm | Venue::DammV2 => return None,
    })
}

/// The committed state on `v`, in the prediction's terms (`like`: for DLMM, the bins to read)
pub fn actual(m: &PoolMeta, v: &View, like: &Pred) -> Option<Pred> {
    match (m.venue, like) {
        (Venue::Dlmm, Pred::Dlmm { bins, .. }) => {
            let pair = (v.get)(&m.pool)?;
            let active = i32_at(&pair.data, 76)?;
            let got: Option<Vec<(i32, u64, u64)>> = bins.iter().map(|(b, _, _)| bin_of(v.arrays, v.get, *b).map(|(x, y)| (*b, x, y))).collect();
            Some(Pred::Dlmm { active, bins: got? })
        }
        (Venue::DammV2, _) => dammv2::decode(&(v.get)(&m.pool)?.data).map(|p| Pred::Damm { sqrt_price: p.sqrt_price }),
        (Venue::Dlmm, _) => None,
        _ => reserves(m, v).map(|(r0, r1)| Pred::Cp { r0, r1 }),
    }
}

/// A prediction against the committed state: exact, and the per-bin counts for DLMM (checked, exact)
pub fn compare(p: &Pred, a: &Pred) -> (bool, Option<(usize, usize)>) {
    match (p, a) {
        (Pred::Dlmm { active: pa, bins: pb }, Pred::Dlmm { active: aa, bins: ab }) => {
            let ok = pb.iter().zip(ab).filter(|(x, y)| x == y).count();
            (pa == aa && ok == pb.len() && pb.len() == ab.len(), Some((pb.len(), ok)))
        }
        _ => (p == a, None),
    }
}

/// predictions.jsonl's v1 fields (the at-hint comparison, arb-lab's measure): CP family r0/r1 predicted against
/// committed with their errors; DLMM the active bin; DAMM v2 the sqrt price
pub fn v1_fields(p: &Pred, a: &Pred) -> Value {
    match (p, a) {
        (Pred::Cp { r0: p0, r1: p1 }, Pred::Cp { r0, r1 }) => {
            let bps = |p: u128, a: u128| if a == 0 { 0.0 } else { (p as f64 - a as f64) / a as f64 * 1e4 };
            json!({ "r0_pred": p0.to_string(), "r0": r0.to_string(), "r1_pred": p1.to_string(), "r1": r1.to_string(), "err0_bps": bps(*p0, *r0), "err1_bps": bps(*p1, *r1),
                "err0": *p0 as i128 - *r0 as i128, "err1": *p1 as i128 - *r1 as i128 })
        }
        (Pred::Dlmm { active: pa, .. }, Pred::Dlmm { active: aa, .. }) => json!({ "pred_active": pa, "actual_active": aa, "match": pa == aa }),
        (Pred::Damm { sqrt_price: ps }, Pred::Damm { sqrt_price: s }) => json!({ "sqrt_price_pred": ps.to_string(), "sqrt_price": s.to_string(), "match": ps == s }),
        _ => json!({}),
    }
}

/// a single error figure for `hint.err`: the larger reserve error in bps (CP), bins between the active bins (DLMM), the
/// sqrt price error in bps (DAMM v2)
pub fn err_of(p: &Pred, a: &Pred) -> Option<f64> {
    match (p, a) {
        (Pred::Cp { r0: p0, r1: p1 }, Pred::Cp { r0, r1 }) => {
            let bps = |p: u128, a: u128| if a == 0 { 0.0 } else { ((p as f64 - a as f64) / a as f64 * 1e4).abs() };
            Some(bps(*p0, *r0).max(bps(*p1, *r1)))
        }
        (Pred::Dlmm { active: pa, .. }, Pred::Dlmm { active: aa, .. }) => Some((*pa as f64 - *aa as f64).abs()),
        (Pred::Damm { sqrt_price: ps }, Pred::Damm { sqrt_price: s }) => Some(if *s == 0 { 0.0 } else { ((*ps as f64 - *s as f64) / *s as f64 * 1e4).abs() }),
        _ => None,
    }
}

/// Per pool, the last `n` scores (status `window_exact_pct`)
#[derive(Default)]
pub struct Window { v: VecDeque<bool> }

impl Window {
    pub fn push(&mut self, exact: bool, n: usize) -> f64 {
        self.v.push_back(exact);
        while self.v.len() > n { self.v.pop_front(); }
        self.v.iter().filter(|x| **x).count() as f64 * 100.0 / self.v.len() as f64
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::feeds::src;
    use crate::venues::WSOL;

    fn acct(data: Vec<u8>, slot: u64) -> Acct { Acct { data: data.into(), slot, write_version: slot, txn: None, t_recv: 0, aseq: 0, src: src::GRPC, bank_id: None, lamports: 0 } }
    fn ammv4() -> Vec<u8> {
        let mut p = vec![0u8; 752];
        p[0..8].copy_from_slice(&1u64.to_le_bytes());
        p[176..184].copy_from_slice(&25u64.to_le_bytes());
        p[184..192].copy_from_slice(&10_000u64.to_le_bytes());
        p
    }
    fn vault(a: u64) -> Vec<u8> { let mut v = vec![0u8; 165]; v[64..72].copy_from_slice(&a.to_le_bytes()); v }

    /// a CP-family prediction recomputed on the pre-state is exact against the state the swap committed; on another
    /// (later) state it is not
    #[test]
    fn a_prediction_on_the_pre_state_matches_the_commit() {
        let m = PoolMeta { venue: Venue::RayAmmV4, pool: [1; 32], t0: [7; 32], t1: *WSOL, vault0: [2; 32], vault1: [3; 32], t0_prog: *crate::pda::TOKEN_PROGRAM,
            t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false };
        let pre: std::collections::HashMap<Pk, Acct> = [(m.pool, acct(ammv4(), 10)), (m.vault0, acct(vault(1_000_000_000_000), 10)), (m.vault1, acct(vault(500_000_000_000), 10))].into();
        let get = |k: &Pk| pre.get(k);
        let v = View { get: &get, arrays: &[], now_unix: 0, slot: 10 };
        let (p, amount_in) = predict(&m, &v, false, 1_000_000_000, false).unwrap();
        assert_eq!(amount_in, 1_000_000_000);
        let Pred::Cp { r0, r1 } = p.clone() else { panic!() };
        // the committed state: what the swap left in the vaults
        let post: std::collections::HashMap<Pk, Acct> = [(m.pool, acct(ammv4(), 11)), (m.vault0, acct(vault(r0 as u64), 11)), (m.vault1, acct(vault(r1 as u64), 11))].into();
        let getp = |k: &Pk| post.get(k);
        let a = actual(&m, &View { get: &getp, arrays: &[], now_unix: 0, slot: 11 }, &p).unwrap();
        assert_eq!(compare(&p, &a), (true, None));
        assert_eq!(err_of(&p, &a), Some(0.0));
        let off = Pred::Cp { r0: r0 + 1_000, r1 };
        assert_eq!(compare(&off, &a).0, false);
        assert_eq!(v1_fields(&off, &a)["err0"], json!(1_000));
        let mut w = Window::default();
        assert_eq!((w.push(true, 2), w.push(false, 2), w.push(false, 2)), (100.0, 50.0, 0.0));
    }
}

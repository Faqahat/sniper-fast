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
use crate::store::{snapshot_with, Acct, Snap};
use crate::tx::Pk;
use crate::venues::{cp, dammv2, dlmm, i32_at, u128_at, u64_at, PoolMeta, Venue};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::sync::Arc;

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

/// What a pool's snapshot and quote need, from one set of account versions
pub struct View<'a> {
    pub get: &'a dyn Fn(&Pk) -> Option<&'a Acct>,
    pub arrays: &'a [(i64, Pk)],
    pub pump_cfg: Option<&'a Arc<cp::PumpFeeCfg>>,
    pub now_unix: i64,
    /// the slot the DAMM v2 fee schedule is evaluated at
    pub slot: u64,
}

/// why a prediction could not be made
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum NoPred { Snapshot, Quote, DlmmArray }

/// The pool's predicted state after a swap of `amount` (exact out: the input that buys `amount`), on `v`
pub fn predict(m: &PoolMeta, v: &View, zfo: bool, amount: u64, exact_out: bool) -> Result<(Pred, u64), NoPred> {
    let snap = snapshot_with(m, v.get, v.arrays, &|_| true, v.pump_cfg, v.now_unix).map_err(|_| NoPred::Snapshot)?;
    match snap {
        Snap::Cp(s) => {
            let amount_in = if exact_out { crate::venues::solve_exact_in(amount, |x| cp::quote(&s, zfo, x).map(|q| q.out)).ok_or(NoPred::Quote)? } else { amount };
            let q = cp::quote(&s, zfo, amount_in).ok_or(NoPred::Quote)?;
            Ok((Pred::Cp { r0: q.r0, r1: q.r1 }, amount_in))
        }
        Snap::Dlmm { pair, arrays, .. } => {
            let view = dlmm::View { pair, arrays: &arrays, over: None };
            let run = |x: u64| dlmm::quote(&view, zfo, x, v.now_unix, true);
            let amount_in = if exact_out { crate::venues::solve_exact_in(amount, |x| run(x).ok().map(|q| q.out)).ok_or(NoPred::Quote)? } else { amount };
            match run(amount_in) {
                Ok(q) => Ok((Pred::Dlmm { active: q.end_active, bins: q.changed.iter().map(|(b, x, y)| (*b, *x, *y)).collect() }, amount_in)),
                Err(dlmm::Why::ArrayNotLoaded) => Err(NoPred::DlmmArray),
                Err(_) => Err(NoPred::Quote),
            }
        }
        Snap::Damm(p, _) => {
            if exact_out { return Err(NoPred::Quote); }
            let (_, after) = dammv2::quote_exact_in(&p, zfo, amount, v.slot, v.now_unix).ok_or(NoPred::Quote)?;
            Ok((Pred::Damm { sqrt_price: after.sqrt_price }, amount))
        }
    }
}

/// (amount_x, amount_y) of bin `id` in the bin arrays `get` returns (layout: docs/spec-dlmm.md: 56-byte header, then
/// 70 bins of 144 bytes, amount_x u64 @0, amount_y u64 @8, price u128 @16)
fn bin_of<'a>(arrays: &[(i64, Pk)], get: &dyn Fn(&Pk) -> Option<&'a Acct>, id: i32) -> Option<(u64, u64)> {
    let ai = dlmm::array_index(id);
    let (_, k) = arrays.iter().find(|(i, _)| *i == ai)?;
    let a = get(k)?;
    let o = 56 + (id as i64 - ai * dlmm::BINS_PER_ARRAY as i64) as usize * 144;
    let _ = u128_at(&a.data, o + 16)?;
    Some((u64_at(&a.data, o)?, u64_at(&a.data, o + 8)?))
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
        _ => match snapshot_with(m, v.get, v.arrays, &|_| true, v.pump_cfg, v.now_unix).ok()? {
            Snap::Cp(s) => Some(Pred::Cp { r0: s.r0, r1: s.r1 }),
            _ => None,
        },
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

    fn acct(data: Vec<u8>, slot: u64) -> Acct { Acct { data: data.into(), slot, write_version: slot, txn: None, t_recv: 0, aseq: 0, src: src::GRPC, bank_id: None } }
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
        let v = View { get: &get, arrays: &[], pump_cfg: None, now_unix: 0, slot: 10 };
        let (p, amount_in) = predict(&m, &v, false, 1_000_000_000, false).unwrap();
        assert_eq!(amount_in, 1_000_000_000);
        let Pred::Cp { r0, r1 } = p.clone() else { panic!() };
        // the committed state: what the swap left in the vaults
        let post: std::collections::HashMap<Pk, Acct> = [(m.pool, acct(ammv4(), 11)), (m.vault0, acct(vault(r0 as u64), 11)), (m.vault1, acct(vault(r1 as u64), 11))].into();
        let getp = |k: &Pk| post.get(k);
        let a = actual(&m, &View { get: &getp, arrays: &[], pump_cfg: None, now_unix: 0, slot: 11 }, &p).unwrap();
        assert_eq!(compare(&p, &a), (true, None));
        assert_eq!(err_of(&p, &a), Some(0.0));
        let off = Pred::Cp { r0: r0 + 1_000, r1 };
        assert_eq!(compare(&off, &a).0, false);
        assert_eq!(v1_fields(&off, &a)["err0"], json!(1_000));
        let mut w = Window::default();
        assert_eq!((w.push(true, 2), w.push(false, 2), w.push(false, 2)), (100.0, 50.0, 0.0));
    }
}

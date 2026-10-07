//! arbx-fast: a decoded pending swap's predicted effect as patched copies of the pool's accounts (an overlay), so a
//! route can be priced on the state the swap leaves BEFORE its account updates arrive (~13 ms after its shreds).
//!
//! This reverses arbx's WP-04 rule "a hint may veto a send, never create one" on purpose, in this separate copy only
//! (owner, 2026-10-07: cut trigger -> send toward 1 ms). Guard rails, enforced by the caller (engine `on_trigger`):
//! - only a swap whose own slippage bound our quote meets (`hint_check` passed) and whose signer is not a known failer;
//! - the overlay lives for ONE evaluation of ONE trigger: it is never written to the store and never prices another
//!   trigger's routes (the old `preds` path "poisoned" other pools for up to 1.5 s);
//! - sends priced on an overlay are bundle-only: a phantom (the trigger fails on chain) is dropped by Jito for free and
//!   our on-chain profit check reverts anything that does not pay.
//!
//! Byte layouts are the venues' own (the same offsets `scenarios::try_swap` patches in tests); amounts come from
//! arbx-sizing through `accuracy::predict`, the predictor proven exact on 1,316 real swaps.
use crate::accuracy::{self, Detail, NoPred, Pred, View};
use crate::store::Acct;
use crate::tx::Pk;
use crate::venues::{dlmm, token_amount, u64_at, PendingSwap, PoolMeta, Venue};
use arbx_sizing::venue::{ammv4, cpmm, dammv2, dlmm as sz_dlmm};
use std::collections::HashMap;

/// The pool after one pending swap: patched copies of every account a quote of this pool reads that the swap changes
/// (vaults, the pool account, DLMM bin arrays). Accounts it does not hold are read from the store unchanged.
#[derive(Clone, Debug)]
pub struct Overlay {
    /// the pending transaction (first signature)
    pub txn: [u8; 64],
    pub pool: Pk,
    pub accts: HashMap<Pk, Acct>,
}

impl Overlay {
    /// the overlay's copy of `k`, if the swap changed it
    pub fn get(&self, k: &Pk) -> Option<&Acct> { self.accts.get(k) }
}

/// Apply `s` (decoded from shreds, not yet committed) to the pool `m` as `v` holds it now. Errors are the predictor's:
/// a pool or swap the venue maths does not model is never guessed. Also refused: an exact-out swap the crate only
/// solves (`overlay_exact_out_solved`: every venue's but PumpSwap's `buy`; the venue rounds its own exact out), a DLMM
/// swap ending inside a limit-order layer (`overlay_dlmm_order_partial`: that bookkeeping is not pinned on real swaps),
/// and the CLMM venues (`overlay_venue`)
pub fn post_swap(m: &PoolMeta, v: &View, s: &PendingSwap, txn: [u8; 64]) -> Result<Overlay, NoPred> {
    if s.pool != m.pool || s.venue != m.venue { return Err(NoPred::Refused("overlay_wrong_pool")); }
    if m.venue.is_clmm() { return Err(NoPred::Refused("overlay_venue")); }
    if s.exact_out && accuracy::exact_out_model(m.venue, s.zero_for_one, true) != Some("exact") { return Err(NoPred::Refused("overlay_exact_out_solved")); }
    let p = accuracy::predict_full(m, v, s.zero_for_one, s.amount, s.exact_out)?;
    let mut w = Writes { v, bufs: Vec::with_capacity(4) };
    let bad = NoPred::Quote;
    match (m.venue, &p.pred, &p.detail) {
        // the effective reserves are the vaults
        (Venue::PumpSwap, Pred::Cp { r0, r1 }, _) => {
            w.u64(&m.vault0, 64, fit(*r0)?)?;
            w.u64(&m.vault1, 64, fit(*r1)?)?;
        }
        // the vaults minus the PnL owed, which a swap does not touch
        (Venue::RayAmmV4, Pred::Cp { r0, r1 }, _) => {
            let pool = w.get(&m.pool)?;
            let (pnl0, pnl1) = (u64_at(&pool.data, ammv4::off::PNL_COIN).ok_or(NoPred::Snapshot)?, u64_at(&pool.data, ammv4::off::PNL_PC).ok_or(NoPred::Snapshot)?);
            w.u64(&m.vault0, 64, fit(r0 + pnl0 as u128)?)?;
            w.u64(&m.vault1, 64, fit(r1 + pnl1 as u128)?)?;
        }
        // the whole input enters its vault and the user's output leaves the other; the fees the swap leaves owed are
        // booked in the pool, so vault minus owed is the predicted reserve
        (Venue::RayCpmm, Pred::Cp { .. }, Detail::Cpmm(b)) => {
            use cpmm::off::*;
            let ((vin, vout), (pin, fin, cin), cout) = if s.zero_for_one { ((&m.vault0, &m.vault1), (PROTOCOL0, FUND0, CREATOR0), CREATOR1) }
                else { ((&m.vault1, &m.vault0), (PROTOCOL1, FUND1, CREATOR1), CREATOR0) };
            let (a, o) = (amount(w.get(vin)?)?, amount(w.get(vout)?)?);
            w.u64(vin, 64, a.checked_add(p.amount_in).ok_or(bad)?)?;
            w.u64(vout, 64, o.checked_sub(p.out).ok_or(bad)?)?;
            for (off, add) in [(pin, b.protocol), (fin, b.fund), (cin, b.creator_in), (cout, b.creator_out)] {
                if add == 0 { continue; }
                let was = u64_at(&w.get(&m.pool)?.data, off).ok_or(NoPred::Snapshot)?;
                w.u64(&m.pool, off, was.checked_add(add).ok_or(bad)?)?;
            }
        }
        // every pool field the swap writes that a quote reads (the fee and reward accounting it also writes is not read)
        (Venue::DammV2, _, Detail::Damm(a)) => {
            use dammv2::off::*;
            w.u128(&m.pool, SQRT_PRICE, a.sqrt_price)?;
            w.u64(&m.pool, TOKEN_A_AMOUNT, a.token_a_amount)?;
            w.u64(&m.pool, TOKEN_B_AMOUNT, a.token_b_amount)?;
            w.bytes(&m.pool, LAYOUT_VERSION, &[a.layout_version])?;
            let d = &a.dynamic_fee;
            w.u64(&m.pool, DYN + 24, d.last_update_timestamp)?;
            w.u128(&m.pool, DYN + 48, d.sqrt_price_reference)?;
            w.u128(&m.pool, DYN + 64, d.volatility_accumulator)?;
            w.u128(&m.pool, DYN + 80, d.volatility_reference)?;
        }
        (Venue::Dlmm, Pred::Dlmm { active, bins }, Detail::Dlmm { p: dp, va, fills }) => {
            use sz_dlmm::off::*;
            // the pair: the references `update_references` set, the accumulator of the bin the swap ends on, and the
            // Clock only when the active bin moved (as the program does: 108 of 108 real swaps that moved it, none of
            // the 108 that did not)
            let va = u32::try_from(*va).map_err(|_| bad)?;
            let v_ref = u32::try_from(dp.v_ref).map_err(|_| bad)?;
            w.bytes(&m.pool, VA, &va.to_le_bytes())?;
            w.bytes(&m.pool, V_REF, &v_ref.to_le_bytes())?;
            w.bytes(&m.pool, IDX_REF, &dp.idx_ref.to_le_bytes())?;
            if *active != dp.active {
                w.bytes(&m.pool, LAST_TS, &v.now_unix.to_le_bytes())?;
                w.bytes(&m.pool, ACTIVE_ID, &active.to_le_bytes())?;
            }
            // the bins: the market-making amounts as predicted; a limit-order layer the swap drained is emptied
            for ((id, x, y), f) in bins.iter().zip(fills) {
                debug_assert_eq!(*id, f.id);
                let ai = dlmm::array_index(*id);
                let k = v.arrays.iter().find(|(i, _)| *i == ai).map(|a| a.1).ok_or(NoPred::DlmmArray)?;
                let o = A_BINS + (*id as i64 - ai * dlmm::BINS_PER_ARRAY as i64) as usize * BIN_SIZE;
                w.u64(&k, o + B_AMOUNT_X, *x)?;
                w.u64(&k, o + B_AMOUNT_Y, *y)?;
                for (layer, off) in [(1, B_PROCESSED_REMAINING), (2, B_OPEN_ORDER)] {
                    if f.taken[layer] == 0 { continue; }
                    if f.taken[layer] != f.layers[layer] { return Err(NoPred::Refused("overlay_dlmm_order_partial")); }
                    w.u64(&k, o + off, 0)?;
                }
            }
        }
        _ => return Err(NoPred::Refused("overlay_venue")),
    }
    Ok(Overlay { txn, pool: m.pool, accts: w.finish() })
}

fn fit(x: u128) -> Result<u64, NoPred> { u64::try_from(x).map_err(|_| NoPred::Quote) }

fn amount(a: &Acct) -> Result<u64, NoPred> { token_amount(&a.data).ok_or(NoPred::Snapshot) }

/// The overlay's copies while it is built: one buffer per account, however many fields of it change
struct Writes<'v, 'a> {
    v: &'v View<'a>,
    bufs: Vec<(Pk, &'a Acct, Vec<u8>)>,
}

impl<'a> Writes<'_, 'a> {
    fn get(&self, k: &Pk) -> Result<&'a Acct, NoPred> { (self.v.get)(k).ok_or(NoPred::Snapshot) }

    fn buf(&mut self, k: &Pk) -> Result<&mut Vec<u8>, NoPred> {
        let i = match self.bufs.iter().position(|b| b.0 == *k) {
            Some(i) => i,
            None => {
                let a = self.get(k)?;
                self.bufs.push((*k, a, a.data.to_vec()));
                self.bufs.len() - 1
            }
        };
        Ok(&mut self.bufs[i].2)
    }

    fn bytes(&mut self, k: &Pk, o: usize, b: &[u8]) -> Result<(), NoPred> {
        self.buf(k)?.get_mut(o..o + b.len()).ok_or(NoPred::Snapshot)?.copy_from_slice(b);
        Ok(())
    }
    fn u64(&mut self, k: &Pk, o: usize, x: u64) -> Result<(), NoPred> { self.bytes(k, o, &x.to_le_bytes()) }
    fn u128(&mut self, k: &Pk, o: usize, x: u128) -> Result<(), NoPred> { self.bytes(k, o, &x.to_le_bytes()) }

    fn finish(self) -> HashMap<Pk, Acct> {
        self.bufs.into_iter().map(|(k, a, d)| (k, Acct { data: d.into(), ..a.clone() })).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::quote::{self, tests as qt, Use};
    use std::collections::BTreeMap;

    fn pending(m: &PoolMeta, zfo: bool, amount: u64, exact_out: bool) -> PendingSwap {
        PendingSwap { pool: m.pool, venue: m.venue, zero_for_one: zfo, amount, exact_out, user: [9; 32], limit: 0 }
    }

    /// a quote, an exact-out quote and the walk of `x` on `get`, as text (refusals included)
    fn quotes<'a>(m: &PoolMeta, arrays: &[(i64, Pk)], get: &dyn Fn(&Pk) -> Option<&'a Acct>, fx: &qt::Fx, zfo: bool, u: Use, x: u64) -> String {
        let src = quote::Src { get, arrays, usable: &|_| true, clock: quote::clock(fx.slot, fx.unix) };
        match quote::leg(m, zfo, &src, u) {
            Err(w) => format!("leg {w:?}"),
            Ok(l) => format!("{:?} {:?} {:?}", l.quote(x), l.exact_out(x), l.walk(x)),
        }
    }

    #[derive(Default, Debug)]
    struct T { n: usize, built: usize, actual_exact: usize, quotes_exact: usize, refused: BTreeMap<String, usize> }

    /// Every real swap of testdata/venue-parity (the venue binaries' own post-states): the overlay built from the
    /// pre-state reads back as the committed state (`accuracy::actual`), every word it writes is the word the program
    /// wrote, and every quote of the pool on it (both directions, our route's leg and a third party's, sizes around
    /// the swap's own) equals the quote on the real post-state. Only the transfer-fee pools' swaps (refused by the
    /// predictor) and DLMM swaps ending inside a limit-order layer are not overlaid
    #[test]
    fn overlays_equal_the_real_post_states() {
        let mut tally: BTreeMap<&str, T> = BTreeMap::new();
        let mut unwritten: BTreeMap<String, usize> = BTreeMap::new();
        let mut problems = vec![];
        for s in qt::swaps() {
            if !s["ok"].as_bool().unwrap() { continue; }
            let c = qt::case(s);
            let post = qt::post_of(&c.pre, &s["post"]);
            let arrays: Vec<(i64, Pk)> = c.arrays.iter().filter(|(i, _)| c.passed.contains(i)).copied().collect();
            let getpre = |k: &Pk| c.pre.get(k);
            let vpre = View { get: &getpre, arrays: &arrays, now_unix: c.fx.unix, slot: c.fx.slot };
            let exact_out = s["exact_out"].as_bool().unwrap_or(false);
            let t = tally.entry(s["venue"].as_str().unwrap()).or_default();
            t.n += 1;
            let tag = format!("{} {} x={} out {exact_out}", qt::label(s), s["dir"], c.x);
            let o = match post_swap(&c.m, &vpre, &pending(&c.m, c.zfo, c.x, exact_out), [7; 64]) {
                Ok(o) => o,
                Err(e) => { *t.refused.entry(format!("{} {e:?}", &s["pool"].as_str().unwrap()[..4])).or_default() += 1; continue }
            };
            t.built += 1;
            assert_eq!((o.txn, o.pool), ([7; 64], c.m.pool));
            // the words it writes are the program's; the words the program wrote that it does not are listed
            for (k, a) in &o.accts {
                let (pre, real) = (&c.pre[k].data, &post[k].data);
                assert_eq!((a.data.len(), a.slot, a.src), (pre.len(), c.pre[k].slot, c.pre[k].src), "{tag}: a copy keeps the original's fields");
                for w in (0..pre.len() / 8).map(|i| i * 8) {
                    let (p, ov, r) = (&pre[w..w + 8], &a.data[w..w + 8], &real[w..w + 8]);
                    if ov != p && ov != r { problems.push(format!("{tag}: {} @{w} written {ov:?}, program {r:?}", crate::tx::b58(k))); }
                    if ov == p && r != p {
                        let role = if *k == c.m.pool { "pool".to_string() } else if arrays.iter().any(|x| x.1 == *k) { format!("bin+{}", (w - 56) % 144) } else { "other".into() };
                        *unwritten.entry(format!("{} {role} @{}", s["venue"].as_str().unwrap(), if role.starts_with("bin") { 0 } else { w })).or_default() += 1;
                    }
                }
            }
            let getover = |k: &Pk| o.get(k).or_else(|| c.pre.get(k));
            let getpost = |k: &Pk| post.get(k);
            let vover = View { get: &getover, arrays: &arrays, now_unix: c.fx.unix, slot: c.fx.slot };
            let vpost = View { get: &getpost, arrays: &arrays, now_unix: c.fx.unix, slot: c.fx.slot };
            let (p, _) = accuracy::predict(&c.m, &vpre, c.zfo, c.x, exact_out).unwrap();
            let (ao, ar) = (accuracy::actual(&c.m, &vover, &p).unwrap(), accuracy::actual(&c.m, &vpost, &p).unwrap());
            if ao == ar && ao == p { t.actual_exact += 1; } else { problems.push(format!("{tag}: overlay reads {ao:?}, committed {ar:?}")); }
            let out = s["out"].as_u64().unwrap();
            let sizes: Vec<u64> = [1, 1_000, 1_000_000, 1_000_000_000, c.x / 7, c.x, c.x.saturating_mul(3), out / 7, out, out.saturating_mul(3)].into_iter().filter(|x| *x > 0).collect();
            let mut same = true;
            for zfo in [true, false] {
                for u in [Use::Third, Use::Route { dlmm_budget: quote::DLMM_BUDGET_ALONE }] {
                    for &x in &sizes {
                        let (qo, qr) = (quotes(&c.m, &arrays, &getover, c.fx, zfo, u, x), quotes(&c.m, &arrays, &getpost, c.fx, zfo, u, x));
                        if qo != qr { same = false; if problems.len() < 40 { problems.push(format!("{tag}: zfo {zfo} {u:?} x={x}: overlay {qo}, real {qr}")); } }
                    }
                }
            }
            if same { t.quotes_exact += 1; }
        }
        for (v, t) in &tally { eprintln!("{v:<9} swaps {:>4} overlaid {:>4} read back exact {:>4} every quote exact {:>4} refused {:?}", t.n, t.built, t.actual_exact, t.quotes_exact, t.refused); }
        eprintln!("words the programs wrote that no quote reads (not overlaid): {unwritten:?}");
        assert!(problems.is_empty(), "{} problems:\n{}", problems.len(), problems[..problems.len().min(40)].join("\n"));
        for (v, t) in &tally {
            assert_eq!((t.actual_exact, t.quotes_exact), (t.built, t.built), "{v}");
            // refused: the transfer-fee pools (the predictor's refusal) and the DLMM swaps ending inside a limit order
            for k in t.refused.keys() { assert!(k == "Hmx1 Refused(\"sz_transfer_fee\")" || k == "2cUM Refused(\"sz_transfer_fee\")" || k.ends_with("Refused(\"overlay_dlmm_order_partial\")"), "{v}: {k}"); }
            assert!(t.built >= 160, "{v}: only {} of {} overlaid", t.built, t.n);
        }
    }

    /// The refusals of its own: a swap of another pool, an exact-out swap the crate only solves, a CLMM pool; a
    /// PumpSwap `buy` (exact out, modelled) is overlaid
    #[test]
    fn overlay_refusals() {
        let mut pump_buys = 0;
        for s in qt::swaps() {
            if !s["ok"].as_bool().unwrap() { continue; }
            let c = qt::case(s);
            let arrays: Vec<(i64, Pk)> = c.arrays.iter().filter(|(i, _)| c.passed.contains(i)).copied().collect();
            let get = |k: &Pk| c.pre.get(k);
            let v = View { get: &get, arrays: &arrays, now_unix: c.fx.unix, slot: c.fx.slot };
            let out = post_swap(&c.m, &v, &pending(&c.m, c.zfo, s["out"].as_u64().unwrap().max(1), true), [0; 64]);
            let want_ok = c.m.venue == Venue::PumpSwap && !c.zfo;
            match (&out, want_ok) {
                (Err(NoPred::Refused("overlay_exact_out_solved")), false) => {}
                (Err(NoPred::Refused("sz_transfer_fee")), _) => {}
                (Ok(_) | Err(_), true) => {}
                _ => panic!("{} exact out: {out:?}", qt::label(s)),
            }
            let mut other = pending(&c.m, c.zfo, c.x, false);
            other.pool = [3; 32];
            assert_eq!(post_swap(&c.m, &v, &other, [0; 64]).unwrap_err(), NoPred::Refused("overlay_wrong_pool"));
            pump_buys += (want_ok && out.is_ok()) as usize;
        }
        assert!(pump_buys > 300, "{pump_buys}");
        let fx = crate::quote::clmm_tests::fixtures().values().next().unwrap();
        let m = crate::quote::clmm_tests::meta(fx);
        let get = |_: &Pk| None;
        let v = View { get: &get, arrays: &[], now_unix: fx.unix, slot: fx.slot };
        assert_eq!(post_swap(&m, &v, &pending(&m, true, 1_000, false), [0; 64]).unwrap_err(), NoPred::Refused("overlay_venue"));
    }

    /// Every fixture pool, both directions, sizes from 1 unit to past its capacity: an overlay is built exactly where
    /// the predictor predicts (refusing only the DLMM swaps that end inside a limit-order layer), holds only the pool's
    /// own accounts, and reads back as the prediction. On 3C6q (limit orders on the bins) both a drained order layer and
    /// a swap ending inside one occur
    #[test]
    fn overlays_read_back_as_the_prediction_at_every_size() {
        let (mut built, mut drained, mut partial) = (0, 0, 0);
        for fx in qt::fixtures().values() {
            let m = qt::meta(fx);
            let pre = qt::accounts(fx, &serde_json::Value::Null);
            let arrays = qt::bin_arrays(fx);
            let get = |k: &Pk| pre.get(k);
            let v = View { get: &get, arrays: &arrays, now_unix: fx.unix, slot: fx.slot };
            let mut sizes: Vec<u64> = (0..64).map(|k| (1.5f64.powi(k)) as u64).collect();
            if crate::tx::b58(&m.pool).starts_with("3C6q") { sizes.extend((0..4_000).map(|k| 100_000_000 + k * 10_000_000_000)); }
            for zfo in [true, false] {
                for &x in &sizes {
                    let pred = accuracy::predict_full(&m, &v, zfo, x, false);
                    match (post_swap(&m, &v, &pending(&m, zfo, x, false), [1; 64]), &pred) {
                        (Ok(o), Ok(p)) => {
                            built += 1;
                            for k in o.accts.keys() { assert!(*k == m.pool || *k == m.vault0 || *k == m.vault1 || arrays.iter().any(|a| a.1 == *k)); }
                            let g = |k: &Pk| o.get(k).or_else(|| pre.get(k));
                            let vo = View { get: &g, arrays: &arrays, now_unix: fx.unix, slot: fx.slot };
                            assert_eq!(accuracy::actual(&m, &vo, &p.pred).as_ref(), Some(&p.pred), "{} zfo {zfo} x={x}", crate::tx::b58(&m.pool));
                            if let Detail::Dlmm { fills, .. } = &p.detail { drained += fills.iter().any(|f| f.taken[2] > 0 && f.taken[2] == f.layers[2]) as usize; }
                        }
                        (Err(NoPred::Refused("overlay_dlmm_order_partial")), Ok(_)) => partial += 1,
                        (Err(e), Err(pe)) => assert_eq!(e, *pe),
                        (o, p) => panic!("{} zfo {zfo} x={x}: overlay {:?}, prediction {:?}", crate::tx::b58(&m.pool), o.map(|_| ()), p.as_ref().map(|_| ())),
                    }
                }
            }
        }
        eprintln!("{built} overlays, {drained} draining a DLMM order layer, {partial} refused inside one");
        assert!(built > 1_000 && drained > 0 && partial > 0, "{built} {drained} {partial}");
    }
}

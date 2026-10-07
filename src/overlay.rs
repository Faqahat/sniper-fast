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
//! Byte layouts are the venues' own (the same offsets `scenarios::try_swap` patches in tests); the post-state is the
//! predictor's (`accuracy::predict_full`: arbx-sizing's amounts and each venue's bookkeeping, exact on every real swap it
//! predicts), computed once. The tests hold every overlay to the venue binaries' own post-states (testdata/venue-parity:
//! the words written, the state read back, and every quote of the pool on it equal to the quote on the real
//! post-state). The swap is applied at `View`'s Clock: a fee or volatility variable that depends on the time is the
//! one the swap would leave if it landed then.
use crate::accuracy::{self, Detail, NoPred, Pred, View};
use crate::store::Acct;
use crate::tx::Pk;
use crate::venues::{dlmm, token_amount, u64_at, PendingSwap, PoolMeta, Venue};
use arbx_sizing::venue::{ammv4, cpmm, dammv2, dlmm as sz_dlmm, orca_whirlpool as orca, raydium_clmm as ray};
use std::collections::HashMap;

/// The pool after one pending swap: patched copies of every account a quote of this pool reads that the swap changes
/// (vaults, the pool account, DLMM bin arrays, Orca's oracle). Accounts it does not hold are read from the store
/// unchanged.
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
/// and a Raydium CLMM swap that fills limit orders on a tick (`overlay_clmm_limit_order`: no recorded real swap fills one,
/// so the tick's order bookkeeping, which the next quote reads, is not pinned)
pub fn post_swap(m: &PoolMeta, v: &View, s: &PendingSwap, txn: [u8; 64]) -> Result<Overlay, NoPred> {
    if s.pool != m.pool || s.venue != m.venue { return Err(NoPred::Refused("overlay_wrong_pool")); }
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
        // the pool fields the swap moves (the crate's `PostSwap`), the vaults by the swap's own amounts, Orca's oracle
        // variables and reward stamp. A tick it crosses changes only fields no quote reads (fee and reward growth outside)
        (Venue::RayClmm | Venue::Whirlpool, Pred::Clmm(c), _) => {
            if let Detail::RayClmm { limit_fills: 1.. } = p.detail { return Err(NoPred::Refused("overlay_clmm_limit_order")); }
            let (vin, vout) = if s.zero_for_one { (&m.vault0, &m.vault1) } else { (&m.vault1, &m.vault0) };
            let (a, o) = (amount(w.get(vin)?)?, amount(w.get(vout)?)?);
            w.u64(vin, 64, a.checked_add(p.amount_in).ok_or(bad)?)?;
            w.u64(vout, 64, o.checked_sub(p.out).ok_or(bad)?)?;
            let var = |i: usize| c.vars.as_ref().and_then(|v| v.get(i).copied()).ok_or(bad);
            let (u32v, u64v) = (|x: i64| u32::try_from(x).map_err(|_| bad), |x: i64| u64::try_from(x).map_err(|_| bad));
            if m.venue == Venue::RayClmm {
                use ray::off::*;
                w.u128(&m.pool, SQRT_PRICE, c.sqrt_price)?;
                w.bytes(&m.pool, TICK_CURRENT, &c.tick.to_le_bytes())?;
                w.u128(&m.pool, LIQUIDITY, c.liquidity)?;
                let (fg, pf, ff) = if c.side0 { (FEE_GROWTH0, PROTOCOL_FEES0, FUND_FEES0) } else { (FEE_GROWTH1, PROTOCOL_FEES1, FUND_FEES1) };
                w.u128(&m.pool, fg, c.fee_growth)?;
                w.u64(&m.pool, pf, c.protocol_fees)?;
                w.u64(&m.pool, ff, c.fund_fees)?;
                if c.vars.is_some() {
                    w.bytes(&m.pool, DYN + 14, &i32::try_from(var(0)?).map_err(|_| bad)?.to_le_bytes())?;
                    w.bytes(&m.pool, DYN + 18, &u32v(var(1)?)?.to_le_bytes())?;
                    w.bytes(&m.pool, DYN + 22, &u32v(var(2)?)?.to_le_bytes())?;
                    w.u64(&m.pool, DYN + 26, u64v(var(3)?)?)?;
                }
            } else {
                use orca::off::*;
                w.u128(&m.pool, SQRT_PRICE, c.sqrt_price)?;
                w.bytes(&m.pool, TICK_CURRENT, &c.tick.to_le_bytes())?;
                w.u128(&m.pool, LIQUIDITY, c.liquidity)?;
                let (fg, pf) = if c.side0 { (FEE_GROWTH_A, PROTOCOL_FEE_OWED_A) } else { (FEE_GROWTH_B, PROTOCOL_FEE_OWED_B) };
                w.u128(&m.pool, fg, c.fee_growth)?;
                w.u64(&m.pool, pf, c.protocol_fees)?;
                w.u64(&m.pool, REWARD_LAST_UPDATED, u64::try_from(v.now_unix).map_err(|_| bad)?)?;
                if c.vars.is_some() {
                    let k = *m.whirl_oracle().ok_or(NoPred::Snapshot)?;
                    let b = O_VARIABLES;
                    w.u64(&k, b, u64v(var(0)?)?)?;
                    w.u64(&k, b + 8, u64v(var(1)?)?)?;
                    w.bytes(&k, b + 16, &u32v(var(2)?)?.to_le_bytes())?;
                    w.bytes(&k, b + 20, &i32::try_from(var(3)?).map_err(|_| bad)?.to_le_bytes())?;
                    w.bytes(&k, b + 24, &u32v(var(4)?)?.to_le_bytes())?;
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
    use serde_json::Value;
    use std::collections::BTreeMap;

    fn pending(m: &PoolMeta, zfo: bool, amount: u64, exact_out: bool) -> PendingSwap {
        PendingSwap { pool: m.pool, venue: m.venue, zero_for_one: zfo, amount, exact_out, user: [9; 32], limit: 0 }
    }

    type Accts = rustc_hash::FxHashMap<Pk, Acct>;

    /// a quote, an exact-out quote and the walk of `x` on `get`, as text (refusals included)
    fn quotes<'a>(m: &PoolMeta, arrays: &[(i64, Pk)], get: &dyn Fn(&Pk) -> Option<&'a Acct>, clock: (u64, i64), zfo: bool, u: Use, x: u64) -> String {
        let src = quote::Src { get, arrays, usable: &|_| true, clock: quote::clock(clock.0, clock.1) };
        match quote::leg(m, zfo, &src, u) {
            Err(w) => format!("leg {w:?}"),
            Ok(l) => format!("{:?} {:?} {:?}", l.quote(x), l.exact_out(x), l.walk(x)),
        }
    }

    #[derive(Default, Debug)]
    struct T { n: usize, built: usize, actual_exact: usize, quotes_exact: usize, with_arrays: usize, refused: BTreeMap<String, usize> }

    /// The tallies of [`check`] over one set of real swaps
    #[derive(Default)]
    struct Run { tally: BTreeMap<String, T>, unwritten: BTreeMap<String, usize>, problems: Vec<String> }

    /// One real swap (`s`: its venue, direction, amounts and post words) on the pre-state `pre`: build the overlay, then
    /// check every word it writes against the program's, `accuracy::actual` on it against the committed state, and the
    /// pool's quotes on it (both directions, our route's leg and a third party's, sizes around the swap's own) against
    /// the quotes on the real post-state
    #[allow(clippy::too_many_arguments)]
    fn check(r: &mut Run, s: &Value, label: String, m: &PoolMeta, clock: (u64, i64), pre: &Accts, post: &Accts, arrays: &[(i64, Pk)], zfo: bool, x: u64, exact_out: bool) {
        let getpre = |k: &Pk| pre.get(k);
        let vpre = View { get: &getpre, arrays, now_unix: clock.1, slot: clock.0 };
        let venue = s["venue"].as_str().unwrap();
        let t = r.tally.entry(venue.to_string()).or_default();
        t.n += 1;
        let tag = format!("{label} {} x={x} exact_out {exact_out}", s["dir"]);
        let o = match post_swap(m, &vpre, &pending(m, zfo, x, exact_out), [7; 64]) {
            Ok(o) => o,
            Err(e) => { *t.refused.entry(format!("{} {e:?}", &s["pool"].as_str().unwrap()[..4])).or_default() += 1; return }
        };
        t.built += 1;
        t.with_arrays += o.accts.keys().any(|k| arrays.iter().any(|a| a.1 == *k)) as usize;
        assert_eq!((o.txn, o.pool), ([7; 64], m.pool));
        // the words it writes are the program's; the words the program wrote that it does not are listed
        for (k, a) in &o.accts {
            let (p0, real) = (&pre[k].data, &post[k].data);
            assert_eq!((a.data.len(), a.slot, a.src), (p0.len(), pre[k].slot, pre[k].src), "{tag}: a copy keeps the original's fields");
            for w in (0..p0.len() / 8).map(|i| i * 8) {
                let (p, ov, rw) = (&p0[w..w + 8], &a.data[w..w + 8], &real[w..w + 8]);
                if ov != p && ov != rw { r.problems.push(format!("{tag}: {} @{w} written {ov:?}, program {rw:?}", crate::tx::b58(k))); }
                if ov == p && rw != p {
                    let role = if *k == m.pool { format!("pool @{w}") } else if venue == "DLMM" && arrays.iter().any(|x| x.1 == *k) { format!("bin +{}", (w - 56) % 144) }
                        else if arrays.iter().any(|x| x.1 == *k) { "tick array".into() } else { format!("other @{w}") };
                    *r.unwritten.entry(format!("{venue} {role}")).or_default() += 1;
                }
            }
        }
        let getover = |k: &Pk| o.get(k).or_else(|| pre.get(k));
        let getpost = |k: &Pk| post.get(k);
        let vover = View { get: &getover, arrays, now_unix: clock.1, slot: clock.0 };
        let vpost = View { get: &getpost, arrays, now_unix: clock.1, slot: clock.0 };
        let (p, _) = accuracy::predict(m, &vpre, zfo, x, exact_out).unwrap();
        let (ao, ar) = (accuracy::actual(m, &vover, &p).unwrap(), accuracy::actual(m, &vpost, &p).unwrap());
        if ao == ar && ao == p { t.actual_exact += 1; } else { r.problems.push(format!("{tag}: overlay reads {ao:?}, committed {ar:?}")); }
        let out = s["out"].as_u64().unwrap();
        let sizes: Vec<u64> = [1, 1_000, 1_000_000, 1_000_000_000, x / 7, x, x.saturating_mul(3), out / 7, out, out.saturating_mul(3)].into_iter().filter(|x| *x > 0).collect();
        let mut same = true;
        for zfo in [true, false] {
            for u in [Use::Third, Use::Route { dlmm_budget: quote::DLMM_BUDGET_ALONE }] {
                for &x in &sizes {
                    let (qo, qr) = (quotes(m, arrays, &getover, clock, zfo, u, x), quotes(m, arrays, &getpost, clock, zfo, u, x));
                    if qo != qr { same = false; if r.problems.len() < 40 { r.problems.push(format!("{tag}: zfo {zfo} {u:?} x={x}: overlay {qo}, real {qr}")); } }
                }
            }
        }
        if same { t.quotes_exact += 1; }
    }

    /// the run's report; every overlay exact, and every refusal one of `allowed`
    fn report(r: &Run, allowed: &dyn Fn(&str) -> bool) {
        for (v, t) in &r.tally {
            eprintln!("{v:<9} swaps {:>4} overlaid {:>4} (bin / tick arrays patched {:>4}) read back exact {:>4} every quote exact {:>4} refused {:?}", t.n, t.built, t.with_arrays,
                t.actual_exact, t.quotes_exact, t.refused);
        }
        eprintln!("words the programs wrote that no quote reads (not overlaid): {:?}", r.unwritten);
        assert!(r.problems.is_empty(), "{} problems:\n{}", r.problems.len(), r.problems[..r.problems.len().min(40)].join("\n"));
        for (v, t) in &r.tally {
            assert_eq!((t.actual_exact, t.quotes_exact), (t.built, t.built), "{v}");
            for k in t.refused.keys() { assert!(allowed(k), "{v}: {k}"); }
            assert!(t.built >= 160, "{v}: only {} of {} overlaid", t.built, t.n);
        }
    }

    /// Every real swap of testdata/venue-parity on PumpSwap, Raydium CPMM and AMM v4, DLMM and DAMM v2 (the venue
    /// binaries' own post-states, [`check`]): every overlay exact. Not overlaid: the transfer-fee pools' swaps (the
    /// predictor's refusal) and DLMM swaps ending inside a limit-order layer
    #[test]
    fn overlays_equal_the_real_post_states() {
        let mut r = Run::default();
        for s in qt::swaps() {
            if !s["ok"].as_bool().unwrap() { continue; }
            let c = qt::case(s);
            let post = qt::post_of(&c.pre, &s["post"]);
            // the arrays the swap passed, as the monitor holds them
            let arrays: Vec<(i64, Pk)> = c.arrays.iter().filter(|(i, _)| c.passed.contains(i)).copied().collect();
            check(&mut r, s, qt::label(s), &c.m, (c.fx.slot, c.fx.unix), &c.pre, &post, &arrays, c.zfo, c.x, s["exact_out"].as_bool().unwrap_or(false));
        }
        report(&r, &|k| k == "Hmx1 Refused(\"sz_transfer_fee\")" || k == "2cUM Refused(\"sz_transfer_fee\")" || k.ends_with("Refused(\"overlay_dlmm_order_partial\")"));
        assert_eq!(r.tally.len(), 5);
    }

    /// The same on every real Raydium CLMM and Orca Whirlpool swap of testdata/venue-parity (exact in and exact out, the
    /// tick arrays as the engine follows them; none fills a limit order). Not overlaid: the transfer-fee pool's swaps
    /// (ASk8, the predictor's refusal)
    #[test]
    fn clmm_overlays_equal_the_real_post_states() {
        use crate::quote::clmm_tests as ct;
        let mut r = Run::default();
        for s in ct::swaps() {
            if !s["ok"].as_bool().unwrap() { continue; }
            let c = ct::case(s);
            let post = ct::post_of(&c.pre, &s["post"]);
            check(&mut r, s, ct::label(s), &c.m, (c.fx.slot, c.fx.unix), &c.pre, &post, &c.arrays, c.zfo, c.x, c.exact_out);
        }
        report(&r, &|k| k.starts_with("ASk8"));
        assert_eq!(r.tally.len(), 2);
    }

    /// The refusals of its own: a swap of another pool, an exact-out swap the crate only solves; a PumpSwap `buy`
    /// (exact out, modelled) is overlaid
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
    }

    /// Every fixture pool (both sets), both directions, sizes from 1 unit to past its capacity: an overlay is built
    /// exactly where the predictor predicts (refusing only a DLMM swap that ends inside a limit-order layer and a Raydium
    /// CLMM swap that fills limit orders), holds only the pool's own accounts, and reads back as the prediction. On 3C6q
    /// (DLMM, orders on the bins) a drained order layer and a swap ending inside one both occur; on 3ucN (Raydium, real
    /// orders on 7 ticks) an order fill occurs
    #[test]
    fn overlays_read_back_as_the_prediction_at_every_size() {
        use crate::quote::clmm_tests as ct;
        let (mut built, mut drained, mut refused) = (0, 0, BTreeMap::<&str, usize>::new());
        let pools = qt::fixtures().values().map(|fx| (qt::meta(fx), qt::accounts(fx, &Value::Null), qt::bin_arrays(fx), fx.slot, fx.unix))
            .chain(ct::fixtures().values().map(|fx| { let m = ct::meta(fx); let a = ct::accounts(fx, &Value::Null); let f = ct::followed(fx, &m, &a); (m, a, f, fx.slot, fx.unix) }));
        for (m, pre, arrays, slot, unix) in pools {
            let get = |k: &Pk| pre.get(k);
            let v = View { get: &get, arrays: &arrays, now_unix: unix, slot };
            let mut sizes: Vec<u64> = (0..64).map(|k| (1.5f64.powi(k)) as u64).collect();
            if crate::tx::b58(&m.pool).starts_with("3C6q") { sizes.extend((0..4_000).map(|k| 100_000_000 + k * 10_000_000_000)); }
            if m.venue == Venue::RayClmm { sizes.extend((64..92).map(|k| (1.5f64.powi(k)) as u64)); }
            for zfo in [true, false] {
                for &x in &sizes {
                    let pred = accuracy::predict_full(&m, &v, zfo, x, false);
                    match (post_swap(&m, &v, &pending(&m, zfo, x, false), [1; 64]), &pred) {
                        (Ok(o), Ok(p)) => {
                            built += 1;
                            for k in o.accts.keys() { assert!([m.pool, m.vault0, m.vault1].contains(k) || m.whirl_oracle() == Some(k) || arrays.iter().any(|a| a.1 == *k)); }
                            let g = |k: &Pk| o.get(k).or_else(|| pre.get(k));
                            let vo = View { get: &g, arrays: &arrays, now_unix: unix, slot };
                            assert_eq!(accuracy::actual(&m, &vo, &p.pred).as_ref(), Some(&p.pred), "{} zfo {zfo} x={x}", crate::tx::b58(&m.pool));
                            if let Detail::Dlmm { fills, .. } = &p.detail { drained += fills.iter().any(|f| f.taken[2] > 0 && f.taken[2] == f.layers[2]) as usize; }
                        }
                        (Err(NoPred::Refused(r @ ("overlay_dlmm_order_partial" | "overlay_clmm_limit_order"))), Ok(_)) => *refused.entry(r).or_default() += 1,
                        (Err(e), Err(pe)) => assert_eq!(e, *pe),
                        (o, p) => panic!("{} zfo {zfo} x={x}: overlay {:?}, prediction {:?}", crate::tx::b58(&m.pool), o.map(|_| ()), p.as_ref().map(|_| ())),
                    }
                }
            }
        }
        eprintln!("{built} overlays, {drained} draining a DLMM order layer, refused {refused:?}");
        assert!(built > 5_000 && drained > 0 && refused.len() == 2, "{built} {drained} {refused:?}");
    }
}

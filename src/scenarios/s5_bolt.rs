//! S5: the bolt trade (w5h2-p5#648; docs/research/wallet-synthesis.md section 5), on the bolt trade's own two pools
//! (9dSMwFfP on PumpSwap 5VbavvxS and DLMM HYWKYZ1e, real layouts: Token-2022 base vault, creator fee, virtual reserve,
//! bin step 100). AgmLJBMD's DFlow split-route sell of the token went into both pools; the old engine priced a half-updated
//! PumpSwap snapshot (its SOL vault after the trigger, its token vault before), saw a gap, and sent 1,865,446,378
//! lamports through DLMM into PumpSwap. On the true post-trigger state that round trip lost 103,451,784.
//!
//! Here: T sells the token into both pools, split so that both end at the same marginal price (what the router aims
//! for: no gap on the true state); its updates arrive in the bolt order (PumpSwap's SOL vault, the DLMM pair and arrays,
//! PumpSwap's token vault last), and the PumpSwap transaction stream delivers T (its write set W(T)) right after T's first
//! update, as measured on w5h2-p1 (p50 +0.23 ms). Expected (PLAN WP-09): no send. The torn snapshot is priced here on a
//! separate engine to show the trap is real: it quotes a profit, at small sizes only (on this fixture the best net is
//! a few hundred thousand lamports at about 0.2 SOL, and the bolt trade's own size loses on it too, where the historical
//! snapshot quoted +19,967,380 at that size; review WP-09 N2). The run's engine never prices it, and on the committed
//! state every size of the route loses.
//!
//! The 103,451,784 cannot be reproduced: the DLMM bin arrays of slot 453,069,812 are not retrievable from RPC (the same
//! limit as S16's p10#156). The fixture is the pools' state of 2026-10-04 with the same mechanism.
use super::*;

const POOLS: [&str; 2] = ["bolt.pump", "bolt.dlmm"];
/// the bolt trade's size: what its DLMM leg took in (the pair's SOL vault, pre / post balances of testdata/wallet/4bkYuxT9...)
const BOLT_SIZE: u64 = 158_273_238_196 - 156_407_791_818;

/// An offline engine whose store holds `chain` (RPC reads at `slot`, the DLMM arrays followed around each active bin),
/// with the run's strategy, tip and knobs: to price a state the run's engine never priced
fn engine_on(r: &Rig, chain: &HashMap<Pk, Vec<u8>>, slot: u64) -> Engine {
    let mut store = Store::default();
    let mut keys: Vec<&Pk> = chain.keys().collect();
    keys.sort();
    for k in keys { store.update(*k, chain[k].clone().into(), slot, 0, None); }
    engine::initial_dlmm_arrays(&r.reg, &mut store);
    let mut e = Engine::new_offline(r.reg.clone(), store, r.cfg.strategy.clone());
    e.apply_init(&r.e.init()).unwrap();
    e
}

/// the gross of buying on `buy` and selling on `sell` at `size` on `chain`
fn gross(r: &Rig, chain: &HashMap<Pk, Vec<u8>>, slot: u64, buy: &PoolMeta, sell: &PoolMeta, mint: &Pk, size: u64) -> Option<i64> {
    let e = engine_on(r, chain, slot);
    crate::replay::price(&e, &buy.pool, &sell.pool, mint, size).ok().and_then(|v| v["gross"].as_i64())
}

#[test]
fn s5_the_bolt_trades_torn_snapshot_is_never_priced_and_the_committed_route_loses() {
    let mut r = Rig::new("s5", Setup { pools: &POOLS, ..Default::default() });
    r.make_ready(T0);
    let (p, d) = (r.meta("bolt.pump"), r.meta("bolt.dlmm"));
    let token = p.t0;
    assert!(!sol_is_t0(&p), "PumpSwap: the token is the base");
    let slot = r.s0 + 2;
    r.tick(slot, T0 + 8 * MS);
    // T's PumpSwap part: 5% of the pool's token reserve (the bolt trigger sold 7.53T across both pools when PumpSwap held ~70.7T)
    let x = token_amount(&r.data(&p.vault0)) / 20;
    let (wp, _) = swap(&r.chain, &p, true, x, slot, r.unix0);
    // T's DLMM part: the amount that leaves both pools at one marginal price (a 0.01 SOL round trip is as bad both ways)
    let after = |y: u64| -> Option<HashMap<Pk, Vec<u8>>> {
        let mut c = r.chain.clone();
        for (k, v) in wp.iter().cloned() { c.insert(k, v); }
        if y > 0 { for (k, v) in try_swap(&r.chain, &d, d.t0 == token, y, slot, r.unix0)?.0 { c.insert(k, v); } }
        Some(c)
    };
    // how much better buying on DLMM and selling on PumpSwap is than the reverse, for a 0.01 SOL round trip: rises with y
    let tilt = |y: u64| -> i64 {
        let Some(c) = after(y) else { return i64::MAX };
        let g = |b: &PoolMeta, s: &PoolMeta| gross(&r, &c, slot, b, s, &token, SOL / 100);
        match (g(&d, &p), g(&p, &d)) { (Some(a), Some(b)) => a - b, _ => i64::MAX }
    };
    let (mut lo, mut hi) = (0u64, x * 4);
    assert!(tilt(lo) < 0 && tilt(hi) > 0, "the split that aligns the two pools is within [0, 4x]: {} {}", tilt(lo), tilt(hi));
    for _ in 0..40 { let mid = lo + (hi - lo) / 2; if tilt(mid) < 0 { lo = mid; } else { hi = mid; } }
    let y = hi;
    let (wd, _) = swap(&r.chain, &d, d.t0 == token, y, slot, r.unix0);
    eprintln!("S5: T sells {x} raw tokens into PumpSwap and {y} into DLMM (marginal prices aligned; tilt {})", tilt(y));
    // the torn snapshot the old engine priced: PumpSwap's SOL vault after T, its token vault before; the DLMM pair after
    let committed = after(y).unwrap();
    let mut torn = committed.clone();
    torn.insert(p.vault0, r.data(&p.vault0));
    // what the engine's size search would find on each state: the best net on the strategy's ladder (DLMM in, PumpSwap out)
    let best = |c: &HashMap<Pk, Vec<u8>>| -> (u64, i64) {
        let e = engine_on(&r, c, slot);
        r.cfg.strategy.sizes_sol.iter().map(|s| (s * 1e9) as u64)
            .filter_map(|x| crate::replay::price(&e, &d.pool, &p.pool, &token, x).ok().and_then(|v| Some((x, v["net"].as_i64()?))))
            .max_by_key(|v| v.1).expect("the route quotes")
    };
    let (torn_best, true_best) = (best(&torn), best(&committed));
    let (torn_bolt, true_bolt) = (gross(&r, &torn, slot, &d, &p, &token, BOLT_SIZE), gross(&r, &committed, slot, &d, &p, &token, BOLT_SIZE));
    eprintln!("S5: torn snapshot: best net {} at {} lamports; committed state: best net {} at {}; at the bolt size {BOLT_SIZE}: gross {torn_bolt:?} torn, {true_bolt:?} committed \
        (the bolt trade: +19,967,380 predicted, -103,451,784 on the true state)", torn_best.1, torn_best.0, true_best.1, true_best.0);
    assert!(torn_best.1 > 0, "the torn snapshot shows a gap: {torn_best:?}");
    assert!(true_best.1 < 0, "on the committed state every size loses: {true_best:?}");
    assert!(true_bolt.is_some_and(|g| g < 0), "and the bolt trade's own size loses on it: {true_bolt:?}");
    // the run: T's writes in the bolt order; the transaction stream's copy (W(T)) 0.23 ms after the first one
    let t_sig = r.sig("T");
    let sol_vault = wp.iter().find(|w| w.0 == p.vault1).cloned().unwrap();
    let tok_vault = wp.iter().find(|w| w.0 == p.vault0).cloned().unwrap();
    let wk: Vec<Pk> = [p.vault0, p.vault1].into_iter().chain(wd.iter().map(|w| w.0)).collect();
    let tx = shred_tx(t_sig, [0xa9; 32], &wk, &[*crate::venues::PUMPSWAP, *crate::venues::DLMM], vec![], slot, 0);
    let mut t = T0 + 20 * MS;
    r.write(sol_vault.0, sol_vault.1, slot, Some(t_sig), t);
    r.tx(executed_copy(&tx, true, t + 230 * US));
    t += 400 * US;
    for (k, v) in wd.iter().cloned() { r.write(k, v, slot, Some(t_sig), t); t += 100 * US; }
    assert_eq!(r.e.counter("evaluation"), 0, "T is pending: its token vault has not arrived");
    t += 1_500 * US;
    r.write(tok_vault.0, tok_vault.1, slot, Some(t_sig), t);
    let ev = r.evaluations();
    assert_eq!(ev.len(), 2, "both pools evaluated once T completed");
    let c = r.commits();
    assert_eq!((c[0]["outcome"].as_str(), c[0]["w_src"].as_str(), c[0]["w_late"].as_bool()), (Some("complete"), Some("tx-stream"), Some(true)));
    for e in &ev {
        assert!(e["opp"].is_null() && e["verdict"] == "reject", "no opportunity on the committed state: {e}");
        assert!(e["routes"].as_array().unwrap().iter().all(|x| x["net"].as_i64().is_some_and(|n| n < 0)), "every route loses: {e}");
    }
    assert_eq!(r.e.counter("state_opportunity"), 0, "nothing could be sent");
    let done = r.finish_and_replay();
    done.check_expected();
}

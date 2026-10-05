//! S2: stacked failed sells (p6#364, p11#132, w5h3-p2#662-#704). Many decoded PumpSwap sells on one pool fail on chain
//! and write nothing. arb-lab stacked their predictions into the pool's price (W §7: up to 1.68 SOL quoted on a state
//! that never existed). Expected (PLAN WP-09): no decision at all.
use super::*;

#[test]
fn s2_stacked_failed_sells_make_no_decision() {
    let mut r = Rig::new("s2", Setup { pools: &["usdc.pump", "usdc.ammv4"], ..Default::default() });
    r.make_ready(T0);
    let p = r.meta("usdc.pump");
    let slot = r.s0 + 2;
    r.tick(slot, T0 + 8 * MS);
    // 20 sells of 3k-60k USDC from 20 signers, decoded from shreds (their write set: the pool's vaults); 7 of them reported
    // failed by the executed stream right after; none ever writes an account
    let ro = [*crate::venues::PUMPSWAP, p.pool, [0x91; 32], p.t0, p.t1];
    for k in 0..20u64 {
        let signer = { let mut s = [0x50u8; 32]; s[0] = k as u8; s };
        let sig = r.sig(&format!("sell{k}"));
        let w = [p.vault0, p.vault1];
        let ix = pump_sell(&p, &signer, (k + 1) * 3_000_000_000, 0, &w, &ro);
        let t = T0 + (10 + k) * MS;
        let a = shred_tx(sig, signer, &w, &ro, vec![ix], slot, t);
        if k % 3 == 0 { let f = executed_copy(&a, false, t + 300 * US); r.tx(a); r.tx(f); } else { r.tx(a); }
    }
    r.timers(T0 + 40 * MS);
    // the hints' outcome window (5 s) ends with no write: their signers' misses counted, nothing priced
    r.slot(slot + 1, 0, Some(slot), T0 + 6_000 * MS);
    r.clock(slot + 1, T0 + 6_000 * MS + US);
    r.timers(T0 + 6_010 * MS);
    let e = &r.e;
    assert_eq!((e.counter("trigger"), e.counter("trigger_hint_only")), (20, 20), "20 decoded sells, hints only");
    assert_eq!((e.counter("evaluation"), e.counter("state_opportunity"), e.counter("commit_complete")), (0, 0, 0), "no state ever existed: no decision");
    assert_eq!(e.counter("signer_miss_tx"), 7, "the failed ones the executed stream reported: misses at once");
    assert_eq!(e.counter("pred_trigger_failed"), 7, "their accuracy checks dropped");
    assert!(r.evaluations().is_empty() && r.commits().is_empty());
    let done = r.finish_and_replay();
    done.check_expected();
}

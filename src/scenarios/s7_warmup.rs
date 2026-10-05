//! S7: the warm-up gate (PLAN WP-04 item 8; W §1: sends went out 3.0-3.8 s late at segment start). The run starts as a
//! segment does: the boot snapshot, then the state stream's first connection and the re-read of every followed account
//! (the gate is `resync` until it lands; MEASUREMENT §4.13 INPUT 11). One Tier-A pool (the CPMM pool) has a vault the node
//! does not have: Tier A is incomplete, so a real gap opened by a large USDC sale on the AMM v4 pool is an opportunity
//! that cannot be sent (reason `warmup`). The vault's first stream write completes Tier A and opens the gate (a shadow
//! run without an executor: `no_executor`); the chain tip running 3 slots past the store's newest update shuts it again.
//!
//! Expected (PLAN WP-09): no send before every Tier-A pool is complete and the lag is within 2 slots (a lag of 2 is
//! within: the boundary is tested).
use super::*;

const POOLS: [&str; 5] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4", "usdc.dlmm", "usdc.damm"];

/// Answer the account reads the engine asked for, as the fetch task does: each account of a chunk at `slot` (recorded in
/// accounts.bin first, `src` as the read's), the ones in `missing` reported missing, then the chunk's INPUT 11 `fetch`
fn answer_reads(r: &mut Rig, slot: u64, t: u64, missing: &[Pk]) -> usize {
    let reads = std::mem::take(&mut r.e.offline_reads);
    let n = reads.len();
    for (i, f) in reads.into_iter().enumerate() {
        let te = t + i as u64 * 10 * US;
        let mut gone = Vec::new();
        for k in &f.keys {
            let Some(d) = r.chain.get(k).filter(|_| !missing.contains(k)).cloned() else { gone.push(b58(k)); continue };
            let data: Arc<[u8]> = d.into();
            let fx = fixtures().get(k);
            let (lamports, owner) = (fx.map_or(1, |x| x.lamports), fx.map_or([0; 32], |x| x.owner));
            let aseq = r.ar.record(&AcctUpdate { pubkey: *k, slot, write_version: 0, t_recv: te, src: f.what.src(), is_startup: false, txn: None, lamports, owner,
                data: &data, bank_id: None });
            r.e.step(Event::Account { slot, pubkey: *k, owner, lamports, data, t: te, txn: None, write_version: 0, is_startup: false, src: f.what.src(), aseq,
                bank_id: None }, te + 100, &mut nop());
        }
        r.input(InputKind::Fetch, json!({ "job": f.job, "chunk": f.chunk, "what": f.what.as_str(), "attempt": f.attempt, "ok": true, "slot": slot,
            "n": f.keys.len(), "missing": gone }), te + 5 * US);
    }
    n
}

#[test]
fn s7_nothing_is_sendable_before_tier_a_is_complete_and_the_store_keeps_up() {
    let f = fixtures();
    let (_, cpmm) = f.pool("usdc.cpmm");
    let reg = boot_registry(&POOLS);
    let cm = reg.pools[reg.by_pool[&cpmm]].clone();
    let omit = [cm.vault1];
    let mut r = Rig::new("s7", Setup { pools: &POOLS, omit: &omit, ..Default::default() });
    let s1 = r.s0 + 1;
    // the state stream connects: the re-read of every followed account starts one slot after its resume slot
    r.input(InputKind::Health, json!({ "src": "state", "connected": true, "connects": 1, "reconnects": 0, "error": null }), T0);
    r.tick(s1, T0 + MS);
    let mut t = T0 + 2 * MS;
    let mut chunks = 0;
    while t < T0 + 2_000 * MS {
        r.timers(t);
        chunks += answer_reads(&mut r, s1, t + MS, &omit);
        t += 50 * MS;
        if t % (400 * MS) < 50 * MS { r.clock(s1, t); }
    }
    assert!(chunks >= 1, "the re-read was asked for");
    assert_eq!(r.e.counter("state_resync_done"), 1, "the re-read landed");
    assert_eq!(r.e.shut(), crate::store_health::Shut::Warmup, "the CPMM pool's vault is missing: Tier A is incomplete");
    // a large USDC sale on the AMM v4 pool opens a real gap: an opportunity, not sendable
    let a = r.meta("usdc.ammv4");
    let s2 = s1 + 1;
    r.tick(s2, t);
    let usdc_in = token_amount(&r.data(if sol_is_t0(&a) { &a.vault1 } else { &a.vault0 })) / 25;
    let w = swap(&r.chain, &a, sol_is_t0(&a) == false, usdc_in, s2, r.unix0).0;
    let dump = r.sig("dump");
    t += 10 * MS;
    for (k, d) in w { r.write(k, d, s2, Some(dump), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    let ev = r.evaluations();
    let d = ev.last().unwrap();
    assert!(d["opp"].is_u64(), "a real gap: an opportunity {d}");
    assert_eq!((d["verdict"].as_str(), d["reason"].as_str()), (Some("reject"), Some("warmup")), "not sendable during the warm-up: {d}");
    assert!(routes_through(d, &cm.pool).iter().all(|x| x["reason"] == "account_missing"));
    assert!(!r.e.health_flags().ready());
    // the missing vault's first stream write: Tier A complete, the gate opens (shadow: no executor)
    t += 20 * MS;
    let v = r.chain[&cm.vault1].clone();
    let touch = r.sig("vault-arrives");
    r.write(cm.vault1, v, s2, Some(touch), t);
    r.timers(t + 6 * MS);
    assert_eq!(r.e.shut(), crate::store_health::Shut::Ready, "Tier A complete, the store keeps up");
    assert!(r.e.health_flags().ready());
    let w2 = swap(&r.chain, &a, !sol_is_t0(&a), usdc_in / 2, s2, r.unix0).0;
    let dump2 = r.sig("dump2");
    t += 10 * MS;
    for (k, d) in w2 { r.write(k, d, s2, Some(dump2), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    let d = r.evaluations().last().cloned().unwrap();
    assert!(d["opp"].is_u64(), "{d}");
    assert_eq!(d["reason"], "no_executor", "past the gate: what a shadow run records for a sendable opportunity");
    // the lag rule: the tip 2 slots past the store's newest update is within it (review WP-09 #5: the boundary) ...
    r.slot(s2 + 2, 0, Some(s2 + 1), t + 5 * MS);
    assert_eq!(r.e.shut(), crate::store_health::Shut::Ready, "a lag of 2 slots is within the limit");
    // ... 3 slots past shuts the gate again
    r.slot(s2 + 3, 0, Some(s2 + 2), t + 10 * MS);
    assert_eq!(r.e.shut(), crate::store_health::Shut::Warmup);
    assert_eq!(r.e.counter("warmup_lost"), 1);
    let done = r.finish_and_replay();
    done.check_expected();
}

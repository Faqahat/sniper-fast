//! S8, S8b: forks (PLAN WP-04 item 9; review F4: a version written on an abandoned fork stayed in the store and was
//! priced).
//!
//! | # | Fork | Expected (PLAN WP-09) |
//! |---|---|---|
//! | S8 | a dead slot | its versions are dropped and a refetch is triggered |
//! | S8b | an abandoned sibling fork with no `dead` status | its versions are dropped when the other branch is confirmed; routes priced on it are counted `fork_priced` |
use super::*;

/// S8b: slots s0+2 and s0+3 are siblings (both children of s0+1). A trade on the AMM v4 pool lands in s0+2: while both
/// siblings are unconfirmed its routes are `fork_pending`; s0+3 is confirmed, s0+2 is abandoned, the trade's versions
/// leave the store (the canonical ones are current again) and the pool is evaluated again (kind `fork`). Then a trade on
/// the PumpSwap pool in s0+4 is priced (no sibling known yet) and s0+5, a child of s0+3, is confirmed: s0+4 was a fork
/// too, and the decision priced on it is `fork_priced`
#[test]
fn s8b_an_abandoned_sibling_fork_without_dead_status() {
    let mut r = Rig::new("s8b", Setup { pools: &["usdc.pump", "usdc.ammv4"], ..Default::default() });
    r.make_ready(T0);
    let (p, a) = (r.meta("usdc.pump"), r.meta("usdc.ammv4"));
    let (s1, s2, s3, s4, s5) = (r.s0 + 1, r.s0 + 2, r.s0 + 3, r.s0 + 4, r.s0 + 5);
    let mut t = T0 + 10 * MS;
    r.slot(s1, 1, Some(r.s0), t);
    r.slot(s2, 0, Some(s1), t + MS);
    r.slot(s3, 0, Some(s1), t + 2 * MS);
    r.clock(s3, t + 2 * MS + US);
    let canonical = r.e.store.get(&a.vault0).unwrap().slot;
    // the minority fork's trade
    let w = swap(&r.chain, &a, sol_is_t0(&a), 3 * SOL, s2, r.unix0).0;
    let tf = r.sig("fork-trade");
    t += 5 * MS;
    for (k, d) in w { r.write(k, d, s2, Some(tf), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    let ev = r.evaluations();
    assert!(reasons(&ev[0]).iter().all(|x| x == "fork_pending"), "both siblings unconfirmed: {}", ev[0]);
    // s0+3 confirmed: s0+2 abandoned, its versions dropped, the canonical state back, the pool evaluated again
    t += 10 * MS;
    r.slot(s3, 1, Some(s1), t);
    assert_eq!((r.e.counter("fork_abandoned_slot"), r.e.counter("fork_versions_dropped")), (1, 2));
    assert_eq!(r.e.store.get(&a.vault0).unwrap().slot, canonical, "the canonical version again");
    assert!(r.evaluations().iter().any(|d| d["kind"] == "fork"), "the pool evaluated again on its canonical state");
    // a trade in s0+4 priced before anyone knows it is a fork
    r.slot(s4, 0, Some(s3), t + MS);
    r.clock(s4, t + MS + US);
    let w = swap(&r.chain, &p, !sol_is_t0(&p), 3_000_000_000, s4, r.unix0).0;
    let tp = r.sig("pump-trade");
    t += 5 * MS;
    for (k, d) in w { r.write(k, d, s4, Some(tp), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    let priced = r.evaluations().iter().filter(|d| d["trigger"]["txn"] == json!(bs58::encode(tp).into_string()) && d["routes"].as_array().unwrap().iter().any(|x| x["net"].is_i64())).count();
    assert!(priced > 0, "priced on its s0+4 versions");
    let before = r.e.counter("fork_priced");
    // s0+5, a child of s0+3, is confirmed: s0+4 is not its ancestor: abandoned
    t += 10 * MS;
    r.slot(s5, 0, Some(s3), t);
    r.slot(s5, 1, Some(s3), t + MS);
    assert!(r.e.counter("fork_priced") > before, "the decision priced on s0+4 is fork_priced");
    assert!(r.decisions().iter().any(|d| d["fork_priced"] == json!(true)));
    let done = r.finish_and_replay();
    done.check_expected();
}

/// S8: two trades on the DAMM v2 pool land in slot s0+3, which is then reported dead. With 2 versions per account
/// (`[accuracy] ring_versions = 2`) the two dead-slot versions were the pool's only ones: they are dropped, the pool
/// account is fetched again (a `fork_refetch` read, answered as the fetch task answers: the account event, then INPUT 11)
/// and the pool is priced again on the fetched state
#[test]
fn s8_a_dead_slots_versions_are_dropped_and_refetched() {
    let mut r = Rig::new("s8", Setup { pools: &["usdc.damm", "usdc.ammv4"], config: &[("ring_versions = 8", "ring_versions = 2")], ..Default::default() });
    r.make_ready(T0);
    let d = r.meta("usdc.damm");
    let (s2, s3, s4) = (r.s0 + 2, r.s0 + 3, r.s0 + 4);
    let canonical = r.data(&d.pool);
    let mut t = T0 + 10 * MS;
    r.tick(s2, t);
    r.tick(s3, t + MS);
    for label in ["dead-1", "dead-2"] {
        let w = swap(&r.chain, &d, true, 2 * SOL, s3, r.unix0).0;
        let s = r.sig(label);
        t += 5 * MS;
        for (k, v) in w { r.write(k, v, s3, Some(s), t); t += 100 * US; }
        r.timers(t + 4 * MS);
    }
    assert!(r.evaluations().len() >= 2, "the pool priced on the dead slot's versions");
    // slot s0+3 is dead
    t += 10 * MS;
    r.slot(s3, 6, None, t);
    assert_eq!((r.e.counter("fork_dead_slot"), r.e.counter("fork_refetch")), (1, 1));
    assert!(r.e.store.get(&d.pool).is_none(), "its only versions were the dead slot's");
    assert!(r.e.offline_reads.iter().any(|f| f.what == crate::reads::What::ForkRefetch && f.keys == vec![d.pool]), "a fork refetch of the pool");
    // the next slot is built on s0+2 (the dead slot is no one's parent); the node answers with the canonical account there
    r.chain.insert(d.pool, canonical.clone());
    r.slot(s4, 0, Some(s2), t + MS);
    r.clock(s4, t + MS + US);
    let n = {
        let reads = std::mem::take(&mut r.e.offline_reads);
        let n = reads.len();
        for (i, f) in reads.into_iter().enumerate() {
            let te = t + 2 * MS + i as u64 * 10 * US;
            for k in &f.keys {
                let data: Arc<[u8]> = r.chain[k].clone().into();
                let fx = fixtures().get(k).unwrap();
                let aseq = r.ar.record(&AcctUpdate { pubkey: *k, slot: s4, write_version: 0, t_recv: te, src: f.what.src(), is_startup: false, txn: None, lamports: fx.lamports,
                    owner: fx.owner, data: &data, bank_id: None });
                r.e.step(Event::Account { slot: s4, pubkey: *k, owner: fx.owner, lamports: fx.lamports, data, t: te, txn: None, write_version: 0, is_startup: false,
                    src: f.what.src(), aseq, bank_id: None }, te + 100, &mut nop());
            }
            r.input(InputKind::Fetch, json!({ "job": f.job, "chunk": f.chunk, "what": f.what.as_str(), "attempt": f.attempt, "ok": true, "slot": s4, "n": f.keys.len(),
                "missing": [] }), te + 5 * US);
        }
        n
    };
    assert_eq!(n, 1);
    assert_eq!(r.e.store.get(&d.pool).map(|x| (x.slot, x.data.to_vec())), Some((s4, canonical)), "the canonical pool account, fetched again");
    // the pool is priced again on it (a small trade on the other pool evaluates the routes through it)
    let a = r.meta("usdc.ammv4");
    let w = swap(&r.chain, &a, sol_is_t0(&a), SOL / 100, s4, r.unix0).0;
    let s = r.sig("after");
    t += 20 * MS;
    for (k, v) in w { r.write(k, v, s4, Some(s), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    let last = r.evaluations().last().cloned().unwrap();
    assert!(routes_through(&last, &d.pool).iter().all(|x| x["net"].is_i64()), "priced on the refetched state: {last}");
    let done = r.finish_and_replay();
    done.check_expected();
}

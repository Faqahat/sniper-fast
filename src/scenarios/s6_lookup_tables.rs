//! S6: lookup tables (PLAN-ADDENDUM I-6; cmp2 dropped 5,001 transactions as `alt_unknown` after one failed fetch). Two v0
//! PumpSwap sells reach their pool's vaults through an address lookup table:
//! - T1's table A fails to fetch at first (an RPC error), is fetched again 50 ms later and found: T1 is processed (its
//!   write set registered, its swap decoded) and its writes form a complete group;
//! - T2's table B never resolves (the node has no such account): retried at 50 ms, 250 ms, 1 s, 5 s, then every 30 s,
//!   and given up after 600 s: T2's hint is dropped with a counted reason (`alt_gave_up`).
//!
//! Expected (PLAN WP-09): the first transaction is processed; for the second, the hint is dropped with a counted reason.
use super::*;

/// a v0 PumpSwap sell of `amount` on `m` whose two vaults come from lookup table `table` (entries 0 and 1, writable)
fn alt_sell(sig: [u8; 64], signer: Pk, m: &PoolMeta, table: Pk, amount: u64, slot: u64, t: u64) -> Arrival {
    // static keys: signer, then read-only: the program, pool, global config, base mint, quote mint; loaded writable: vault0, vault1
    let keys = vec![signer, *crate::venues::PUMPSWAP, m.pool, [0x91; 32], m.t0, m.t1];
    let mut data = vec![0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad];
    data.extend(amount.to_le_bytes());
    data.extend(0u64.to_le_bytes());
    let ix = Ix { program: 1, accounts: vec![2, 0, 3, 4, 5, 6, 7], data };
    let tx = Tx { sig, num_signers: 1, num_ro_signed: 0, num_ro_unsigned: 5, keys, ixs: vec![ix],
        lookups: vec![crate::tx::Lookup { table, writable: vec![0, 1], readonly: vec![] }], ..Default::default() };
    let w = crate::tx::to_wire(&tx).unwrap();
    let (tx, _) = crate::tx::parse_wire(&w).unwrap();
    Arrival { feed: 0, slot, t_rx: t, t_decoded: t, executed: None, tx, poh: None, raw: RawTx::Wire(w.into()) }
}

/// answer every lookup-table fetch the engine asked for since `seen`: table `a` with `a_addrs` (once `a_ok`), `b` never
fn answer_alts(r: &mut Rig, seen: &mut usize, a: Pk, a_addrs: &[Pk], a_ok: &mut bool, t: u64) -> (u32, u32) {
    let asked: Vec<Pk> = r.e.offline_fetches[*seen..].iter().filter(|f| f.0 == "alt").flat_map(|f| f.1.clone()).collect();
    *seen = r.e.offline_fetches.len();
    let (mut na, mut nb) = (0, 0);
    for table in asked {
        let ev = if table == a {
            na += 1;
            // the first fetch of A fails (an RPC error), the retry finds it
            if *a_ok { Event::Alt { table, addrs: Some(Arc::new(a_addrs.to_vec())), err: None } } else { *a_ok = true; Event::Alt { table, addrs: None, err: Some("HTTP 429".into()) } }
        } else { nb += 1; Event::Alt { table, addrs: None, err: None } };
        r.e.step(ev, t, &mut nop());
    }
    (na, nb)
}

#[test]
fn s6_a_table_fetched_by_retry_and_a_table_that_never_resolves() {
    let mut r = Rig::new("s6", Setup { pools: &["usdc.pump", "usdc.ammv4"], ..Default::default() });
    r.make_ready(T0);
    let p = r.meta("usdc.pump");
    let slot = r.s0 + 2;
    r.tick(slot, T0 + 8 * MS);
    let (ta, tb): (Pk, Pk) = ([0xa1; 32], [0xb2; 32]);
    let (s1, s2) = (r.sig("T1"), r.sig("T2"));
    r.tx(alt_sell(s1, [0x61; 32], &p, ta, 5_000_000_000, slot, T0 + 10 * MS));
    r.tx(alt_sell(s2, [0x62; 32], &p, tb, 7_000_000_000, slot, T0 + 11 * MS));
    assert_eq!((r.e.counter("alt_wait"), r.e.counter("tx_first"), r.e.counter("trigger")), (2, 2, 0), "both wait for their tables");
    let (mut seen, mut a_ok) = (0usize, false);
    let mut t = T0 + 12 * MS;
    // the first answers: A fails, B does not exist
    assert_eq!(answer_alts(&mut r, &mut seen, ta, &[p.vault0, p.vault1], &mut a_ok, t), (1, 1));
    assert_eq!(r.e.counter("trigger"), 0, "still waiting: retried, not missing for the run");
    // A's retry 50 ms later finds it: T1 is processed (its sell decoded, its write set registered)
    t += 50 * MS;
    r.timers(t);
    assert_eq!(answer_alts(&mut r, &mut seen, ta, &[p.vault0, p.vault1], &mut a_ok, t + MS).0, 1, "A retried at 50 ms");
    assert_eq!(r.e.counter("trigger"), 1, "T1 processed: its sell decoded");
    // T1 lands: its writes (the vaults) form a complete group, its write set known from the shred feed through table A
    let w = swap(&r.chain, &p, true, 5_000_000_000, slot, r.unix0).0;
    let mut tw = t + 3 * MS;
    for (k, d) in w { r.write(k, d, slot, Some(s1), tw); tw += 100 * US; }
    let c = r.commits();
    assert_eq!((c[0]["outcome"].as_str(), c[0]["w_src"].as_str()), (Some("complete"), Some("shred")), "{c:?}");
    // B is fetched again on its schedule, never found, and given up after 600 s: T2's hint dropped and counted
    let mut retries_b = 1;
    let mut tt = t + 5 * MS;
    for step in [250 * MS, 1_000 * MS, 5_000 * MS].into_iter().chain(std::iter::repeat(30_000 * MS).take(21)) {
        tt += step;
        r.slot(r.s0 + 3, 0, Some(slot), tt - MS);
        r.clock(r.s0 + 3, tt - MS + US);
        r.timers(tt);
        retries_b += answer_alts(&mut r, &mut seen, ta, &[p.vault0, p.vault1], &mut a_ok, tt + MS).1;
    }
    r.timers(tt + 30_000 * MS);
    assert!(retries_b >= 5, "B fetched again on its schedule: {retries_b}");
    assert_eq!((r.e.counter("alt_gave_up"), r.e.counter("trigger")), (1, 1), "T2 dropped with a counted reason, never decoded");
    r.rec.sync();
    let ev: Vec<String> = rec::read_jsonl(&r.dir, "alts").unwrap().iter().map(|x| x["event"].as_str().unwrap().to_string()).collect();
    assert!(ev.iter().any(|e| e == "give_up") && ev.iter().any(|e| e == "waiters_released"), "{ev:?}");
    let done = r.finish_and_replay();
    done.check_expected();
}

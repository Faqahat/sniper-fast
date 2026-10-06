//! S12 (PLAN WP-09; invariant 3: a hint may veto a send, never create one): a decoded-only trigger never produces a
//! send. In a canary run (live under `[canary]`'s caps, its bundles to a block engine in memory), decoded swaps that
//! never execute are hints only: no decision, no attempt, no bundle.
//!
//! - **Never create** (`s12`): ten rival swaps decoded from shreds, on both pools: six PumpSwap sells of up to 150,000
//!   USDC (arb-lab stacked such predictions into the pool's price: W §4 and §7.1, up to 1.68 SOL expected on a state
//!   that never existed) and four AMM v4 swaps. Five are reported failed by the executed stream right away, five are never seen
//!   again (their outcome window, 5 s, ends with no write). No account is ever written: no decision at all (no
//!   evaluation, no opportunity), no attempt, nothing reaches the block engine; every trigger is counted hint-only, the
//!   hints of the failed ones are dropped at once and the others when their window ends.
//! - **May veto** (`s12-veto`): a rival's transaction T seen in shreds names both PumpSwap vaults (its write set W(T)
//!   from the hint); its first write arrives, its second 4 ms later. Between them a real trade U opens a large gap on
//!   the AMM v4 pool and resolves; every route of U's evaluation goes through the PumpSwap pool, which T's pending group
//!   holds: all `pending_commit`, nothing sent (the hint vetoed a send on a half-written state). T's last write completes
//!   its group, and its evaluation, on the committed state, is the one send.
//!
//! Each run is replayed (whole, the digests the run's, every decision and attempt) and its projection checked against
//! `testdata/scenarios/expected/<name>.json`.
use super::*;

const POOLS: [&str; 2] = ["usdc.pump", "usdc.ammv4"];

/// a canary run on the PumpSwap and AMM v4 pools, ready, the Jito leader's slots, a fresh blockhash and the ledger's
/// start snapshot; returns it with its slot
fn rig(name: &'static str) -> (Rig, u64) { super::s13_verdicts::canary_rig(name, &POOLS, &CANARY, true) }

#[test]
fn s12_a_decoded_only_trigger_never_produces_a_send() {
    let (mut r, s2) = rig("s12");
    let (p, a) = (r.meta("usdc.pump"), r.meta("usdc.ammv4"));
    let pump_ro = [*crate::venues::PUMPSWAP, p.pool, [0x91; 32], p.t0, p.t1];
    let mut t = T0 + 10 * MS;
    for k in 0..10u64 {
        let signer = { let mut s = [0x40u8; 32]; s[0] = k as u8; s };
        let sig = r.sig(&format!("hint{k}"));
        let tx = if k < 6 {
            // a PumpSwap sell of 25,000-150,000 USDC (its write set: the pool's vaults)
            let w = [p.vault0, p.vault1];
            shred_tx(sig, signer, &w, &pump_ro, vec![pump_sell(&p, &signer, (k + 1) * 25_000_000_000, 0, &w, &pump_ro)], s2, t)
        } else {
            // an AMM v4 swap of 1-4 SOL into USDC (S3's layout)
            let w = [a.vault0, a.vault1];
            let ro = [*crate::venues::RAYAMMV4, *crate::pda::TOKEN_PROGRAM, [0x92; 32], a.pool, crate::pda::ata(&signer, &a.t0, &a.t0_prog),
                crate::pda::ata(&signer, &a.t1, &a.t1_prog)];
            shred_tx(sig, signer, &w, &ro, vec![ammv4_swap(&a, &signer, (k - 5) * SOL, sol_is_t0(&a), &w, &ro)], s2, t)
        };
        // the odd ones fail on chain (the executed stream says so 300 µs later); the even ones are never seen again
        if k % 2 == 1 { let f = executed_copy(&tx, false, t + 300 * US); r.tx(tx); r.tx(f); } else { r.tx(tx); }
        t += MS;
        r.timers(t);
    }
    assert_eq!((r.e.counter("trigger"), r.e.counter("trigger_hint_only")), (10, 10), "ten decoded swaps, hints only");
    // the hints' outcome window (5 s) ends with no write: slots go by, the timers run
    for k in 1..=15u64 { r.tick(s2 + k, t + k * 400 * MS); r.timers(t + k * 400 * MS + MS); }
    let e = &r.e;
    assert_eq!((e.counter("evaluation"), e.counter("state_opportunity"), e.counter("commit_complete")), (0, 0, 0), "no state ever changed: no decision at all");
    assert_eq!((e.counter("pred_trigger_failed"), e.counter("pred_not_committed")), (5, 5), "the failed ones' hints dropped at once, the rest when their window ended");
    assert_eq!((e.counter("signer_miss_tx"), e.counter("signer_miss")), (5, 5));
    assert!(r.decisions().is_empty() && r.attempts().is_empty() && r.bundles_sent().is_empty(), "no decision, no attempt, no bundle");
    assert_eq!(r.lines("triggers").iter().filter(|l| l["hint_only"] == json!(true) && l["opp"].is_null()).count(), 10, "triggers.jsonl: ten hints, none an opportunity");
    let x = r.e.exec.as_ref().unwrap().status();
    assert_eq!((x["decisions"].as_u64(), x["sent"].as_u64()), (Some(0), Some(0)), "the executor was never asked: {x}");
    let done = r.finish_and_replay();
    done.check_expected();
}

#[test]
fn s12_a_hint_vetoes_a_send_on_a_half_written_state() {
    let (mut r, s2) = rig("s12-veto");
    let (p, a) = (r.meta("usdc.pump"), r.meta("usdc.ammv4"));
    // T: a rival's USDC sale into the PumpSwap pool, seen in shreds (W(T): both vaults); its writes computed on the chain
    let tsig = r.sig("T");
    let usdc_in = token_amount(&r.data(if sol_is_t0(&p) { &p.vault1 } else { &p.vault0 })) / 500;
    let wt = swap(&r.chain, &p, !sol_is_t0(&p), usdc_in, s2, r.unix0).0;
    let wk: Vec<Pk> = wt.iter().map(|x| x.0).collect();
    let mut t = T0 + 10 * MS;
    r.tx(shred_tx(tsig, [0x63; 32], &wk, &[p.pool, *crate::venues::PUMPSWAP], vec![], s2, t));
    // T's first write: its group opens, the other vault pending
    t += MS;
    r.write(wt[0].0, wt[0].1.clone(), s2, Some(tsig), t);
    // U: a large USDC sale into the AMM v4 pool (its write set unknown), resolved by quiescence while T is pending
    let usig = r.sig("U");
    let usdc_u = token_amount(&r.data(if sol_is_t0(&a) { &a.vault1 } else { &a.vault0 })) / 40;
    let wu = swap(&r.chain, &a, !sol_is_t0(&a), usdc_u, s2, r.unix0).0;
    for (k, d) in wu { t += 100 * US; r.write(k, d, s2, Some(usig), t); }
    r.timers(t + 3 * MS + 100 * US);
    let ev = r.evaluations();
    assert_eq!(ev.len(), 1, "U's pool evaluated: {ev:?}");
    assert!(reasons(&ev[0]).iter().all(|x| x == "pending_commit"), "every route of U goes through T's pending pool: {}", ev[0]);
    assert!(ev[0]["opp"].is_null() && r.attempts().is_empty() && r.bundles_sent().is_empty(), "vetoed: no opportunity, no attempt, no bundle");
    // T's last write: complete; its evaluation on the committed state (T and U) is sent
    r.write(wt[1].0, wt[1].1.clone(), s2, Some(tsig), t + 3 * MS + 500 * US);
    let ev = r.evaluations();
    assert_eq!(ev.len(), 2, "{ev:?}");
    assert!(reasons(&ev[1]).iter().all(|x| x != "pending_commit"), "{}", ev[1]);
    assert_eq!((ev[1]["trigger"]["txn"].as_str(), ev[1]["kind"].as_str(), ev[1]["reason"].as_str(), ev[1]["attempt"].as_u64()),
        (Some(bs58::encode(tsig).into_string().as_str()), Some("commit"), Some("sent"), Some(0)), "{}", ev[1]);
    let fired = r.pump(1, t + 5 * MS);
    assert_eq!((fired[0]["what"].as_str(), r.bundles_sent().len()), (Some("fired"), 1));
    let done = r.finish_and_replay();
    done.check_expected();
}

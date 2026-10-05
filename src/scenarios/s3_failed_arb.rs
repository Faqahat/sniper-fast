//! S3: a failed rival arbitrage (DreMAMRc>AwmaWjsR, 54 of the 96 failures in w5h3-p2; CPD18rED's failed arbs). A rival's
//! two-leg arbitrage across two of our pools (an AMM v4 buy of USDC, a PumpSwap sell of it) is decoded from shreds, then
//! fails on chain and writes nothing. arb-lab left both legs' predictions in the pools' prices and saw a gap that never
//! existed. Expected (PLAN WP-09): no gap. The next real trade on one of the pools is decided exactly as without the
//! rival's transaction.
use super::*;

const POOLS: [&str; 2] = ["usdc.pump", "usdc.ammv4"];

/// one run: the rival's failed arbitrage (when `rival`), then a small real trade on the AMM v4 pool 400 ms later
fn run(name: &'static str, rival: bool) -> (Rig, Vec<Value>) {
    let mut r = Rig::new(name, Setup { pools: &POOLS, ..Default::default() });
    r.make_ready(T0);
    let (p, a) = (r.meta("usdc.pump"), r.meta("usdc.ammv4"));
    let slot = r.s0 + 2;
    r.tick(slot, T0 + 8 * MS);
    if rival {
        // buy 40k USDC with SOL on AMM v4, sell it on PumpSwap: both legs top-level, both decoded (hints)
        let signer: Pk = [0xd3; 32];
        let w = [a.vault0, a.vault1, p.vault0, p.vault1];
        let ro = [*crate::venues::RAYAMMV4, *crate::venues::PUMPSWAP, *crate::pda::TOKEN_PROGRAM, [0x92; 32], [0x91; 32], a.pool, p.pool, p.t0, p.t1,
            crate::pda::ata(&signer, &a.t0, &a.t0_prog), crate::pda::ata(&signer, &a.t1, &a.t1_prog)];
        let ixs = vec![ammv4_swap(&a, &signer, 330 * SOL, sol_is_t0(&a), &w, &ro), pump_sell(&p, &signer, 40_000_000_000, 0, &w, &ro)];
        let sig = r.sig("rival");
        let t = T0 + 10 * MS;
        let tx = shred_tx(sig, signer, &w, &ro, ixs, slot, t);
        let failed = executed_copy(&tx, false, t + 400 * US);
        r.tx(tx);
        r.tx(failed);
        assert_eq!(r.e.counter("trigger"), 2, "both legs decoded");
    }
    // 400 ms later, a small real trade lands on the AMM v4 pool (its write set unknown): its pool is evaluated
    let slot2 = slot + 1;
    r.tick(slot2, T0 + 405 * MS);
    let u = swap(&r.chain, &a, sol_is_t0(&a), SOL / 100, slot2, r.unix0).0;
    let s = r.sig("small");
    let mut t = T0 + 410 * MS;
    for (k, d) in u { r.write(k, d, slot2, Some(s), t); t += 200 * US; }
    r.timers(t + 4 * MS);
    let d = r.evaluations();
    (r, d)
}

#[test]
fn s3_failed_rival_arbitrage_opens_no_gap() {
    let (r, with) = run("s3", true);
    let (r0, without) = run("s3_twin", false);
    assert_eq!((r.e.counter("trigger_hint_only"), r.e.counter("signer_miss_tx"), r.e.counter("state_opportunity")), (2, 1, 0), "hints only, the rival's miss counted at once");
    assert_eq!(with.len(), 1, "only the real trade's pool is evaluated: {with:?}");
    let strip = |d: &Value| { let mut d = d.clone(); for k in ["stages", "t_ns"] { d[k] = Value::Null; } d["trigger"]["t_first_shred"] = Value::Null; d };
    assert_eq!(with.iter().map(strip).collect::<Vec<_>>(), without.iter().map(strip).collect::<Vec<_>>(), "the failed arbitrage changed no price");
    assert_eq!(r.e.decision_digest(), r0.e.decision_digest());
    assert_ne!(with[0]["reason"], "no_executor", "no opportunity: {}", with[0]);
    drop(r0);
    let done = r.finish_and_replay();
    done.check_expected();
}

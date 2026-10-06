//! S15 (PLAN WP-09; MEASUREMENT §2.2): the status counters. Every number of a status.jsonl line is `_total` (since the
//! start: monotonic, reset only by a restart; take the last), `_delta` (since the previous line: summing the lines gives
//! the segment's total) or `_now`; every line has `seq` (from 0, no gap) and `interval_ns`. arb-lab summed a running
//! total across lines (R §3.7: `failed_fees_lamports`).
//!
//! A canary run (its bundles to a block engine in memory) with its ledger, over two minutes of engine time and a status
//! line every 10 s, with something moving in most intervals: a send whose bundle is accepted then would-fail and later
//! expires; a second send that lands (its wallet record: a ledger line with fees, a tip and rent out and back); ten
//! decoded swaps that never execute; the ledger's periodic snapshot and its reconciliation; a third send that landed
//! and failed, found first by its expiry check (a provisional failed fee, `money.failed_fees_total_lamports` counts it)
//! and settled by its wallet record two status lines later; slots, the Clock, the blockhash ring. The run's final line is
//! written as `arbx run` writes it at its stop (`write_final_status`).
//!
//! Checked on every line of the run: `seq` 0..n with no gap, `interval_ns`; every `_total` monotonic (the money's signed
//! sums aside: P&L may fall); every pair `X_total` / `X_delta` (and `X_total_<unit>` / `X_delta_<unit>`, and the maps
//! `counts_total` / `counts_delta`, the executor's own, the recorder's drops) with Σ `X_delta` up to each line = that
//! line's `X_total`; the `_delta`-only sections the engine derives from its counters (commit groups, forks, accuracy,
//! lookup tables) summing to the counters' totals; the executor's verdicts (`verdicts_delta`) summing to what the block
//! engine answered. Process-wide sections (`rpc_budget`, `alerts`, `coverage`, `chainfetch`: shared by every engine of
//! a test process) are not this engine's alone and are left out. The run replays.
use super::s13_verdicts::{canary_rig, usdc_sale};
use super::s14_ledger::{wallet_record, FEE};
use super::*;
use std::collections::BTreeMap;

const POOLS: [&str; 3] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4"];
/// sections of the status line that are the process's, not this engine's (shared by every engine of a test process)
const PROCESS_WIDE: [&str; 4] = ["rpc_budget", "alerts", "coverage", "chainfetch"];
/// the money's signed sums (a loss lowers them): `_total` without monotonicity (MEASUREMENT §4.8 money)
const SIGNED: [&str; 6] = ["trade_gross_total", "trade_pnl_total", "trade_net_total", "net_spend_total", "owner_transfers_total", "round_trip_total_lamports"];

/// every number of a status line by its path (`store.updates_total`, `counts_total.trigger`), process-wide sections out
fn flat(v: &Value, path: &str, out: &mut BTreeMap<String, i128>) {
    match v {
        Value::Object(m) => for (k, x) in m {
            if path.is_empty() && PROCESS_WIDE.contains(&k.as_str()) { continue; }
            flat(x, &if path.is_empty() { k.clone() } else { format!("{path}.{k}") }, out);
        },
        Value::Number(n) => { if let Some(i) = n.as_i64().map(i128::from).or_else(|| n.as_u64().map(i128::from)) { out.insert(path.to_string(), i); } }
        _ => {}
    }
}

/// a `_total` name: `<name>_total` or `<name>_total_<unit>` (`failed_fees_total_lamports`), never a gauge (`equity_total_now`)
fn is_total(s: &str) -> bool { s.ends_with("_total") || (s.contains("_total_") && !s.ends_with("_now")) }

/// the `_delta` path of a `_total` path (the segment holding `_total` changed), if it names one
fn delta_of(p: &str) -> Option<String> {
    let segs: Vec<&str> = p.split('.').collect();
    let i = segs.iter().position(|s| is_total(s))?;
    let mut out: Vec<String> = segs.iter().map(|s| s.to_string()).collect();
    out[i] = segs[i].replacen("_total", "_delta", 1);
    Some(out.join("."))
}

/// The checks of the module doc on `lines`; returns how many total/delta pairs were checked, by path
fn check_counters(lines: &[Value]) -> Vec<String> {
    assert!(lines.len() >= 6, "status lines: {}", lines.len());
    for (k, l) in lines.iter().enumerate() {
        assert_eq!(l["seq"].as_u64(), Some(k as u64), "seq from 0, no gap: {l}");
        assert!(l["interval_ns"].is_u64(), "{l}");
    }
    let flats: Vec<BTreeMap<String, i128>> = lines.iter().map(|l| { let mut m = BTreeMap::new(); flat(l, "", &mut m); m }).collect();
    let totals: std::collections::BTreeSet<&String> = flats.iter().flat_map(|m| m.keys()).filter(|p| p.split('.').any(is_total)).collect();
    let mut pairs = Vec::new();
    for p in totals {
        // a map's key missing on a line is 0 there (counters appear when they first move)
        let series: Vec<i128> = flats.iter().map(|m| m.get(p).copied().unwrap_or(0)).collect();
        let leaf = p.rsplit('.').next().unwrap();
        if !SIGNED.contains(&leaf) {
            for w in series.windows(2) { assert!(w[1] >= w[0], "{p} is a _total: monotonic: {series:?}"); }
        }
        let Some(d) = delta_of(p) else { continue };
        // the pair exists when its delta is on a line, or (a map of counters: `counts_total.<name>`) the delta map is on
        // the last line (a counter that did not move in an interval is not in that line's map: 0)
        let segs: Vec<&str> = d.split('.').collect();
        let map = !is_total(leaf);
        let present = flats.iter().any(|m| m.contains_key(&d))
            || (map && { let mut v = lines.last().unwrap(); for s in &segs[..segs.len() - 1] { v = &v[*s]; } v.is_object() });
        if !present { continue; }
        // §2.2: the deltas up to each line sum to that line's total (the first line's delta is since the start)
        let mut sum = 0i128;
        for (k, m) in flats.iter().enumerate() {
            sum += m.get(&d).copied().unwrap_or(0);
            assert_eq!(sum, series[k], "line {k}: Σ {d} up to it = its {p} (totals {series:?})");
        }
        pairs.push(p.clone());
    }
    // the delta-only sections derived from the counters
    let last = flats.last().unwrap();
    let total = |k: &str| last.get(&format!("counts_total.{k}")).copied().unwrap_or(0);
    let sum = |p: &str| flats.iter().map(|m| m.get(p).copied().unwrap_or(0)).sum::<i128>();
    // (the delta-only sections: summed over the whole run against the last line's counter)
    for (d, c) in [("commit.complete_delta", "commit_complete"), ("commit.superseded_delta", "commit_superseded"), ("commit.timeout_unknown_delta", "commit_timeout_unknown"),
        ("commit.timeout_quiescent_delta", "commit_timeout_quiescent"), ("commit.fork_dropped_delta", "commit_fork_dropped"), ("commit.late_member_delta", "commit_late_member"),
        ("commit.torn_suspect_delta", "torn_suspect"), ("commit.by_w_src_delta.shred", "commit_w_shred"), ("commit.by_w_src_delta.unknown", "commit_w_unknown"),
        ("commit.by_w_src_delta.tx-stream", "commit_w_tx_stream"), ("forks.abandoned_slots_delta", "fork_abandoned_slot"), ("forks.refetch_delta", "fork_refetch"),
        ("accuracy.scored_delta", "pred_scored"), ("accuracy.exact_delta", "pred_exact"), ("alts.learned_delta", "alt_learned"), ("alts.retries_delta", "alt_retry")] {
        assert_eq!(sum(d), total(c), "Σ {d} = counts_total.{c}");
    }
    assert_eq!(sum("commit.groups_delta"), ["commit_complete", "commit_superseded", "commit_timeout_unknown", "commit_timeout_quiescent", "commit_fork_dropped"].iter().map(|c| total(c)).sum::<i128>());
    pairs
}

#[test]
fn s15_status_totals_are_monotonic_and_the_deltas_sum_to_them() {
    let (mut r, s2) = canary_rig("s15", &POOLS, &CANARY, false);
    r.leaders(r.s0 + 400, &[LEADER_JITO; 400], T0 + 9 * MS + 500 * US);
    let (sol0, wsol0) = (3 * SOL, 2 * SOL);
    let (a, p) = (r.meta("usdc.ammv4"), r.meta("usdc.pump"));
    let mut slot = s2;
    // a slot every 400 ms with its Clock, the ring's head every slot; the timers every 50 ms (status lines every 10 s)
    let mut clock = |r: &mut Rig, until: u64, t: &mut u64| {
        while *t < until {
            *t += 50 * MS;
            if (*t - T0) % (400 * MS) < 50 * MS { slot += 1; r.tick(slot, *t); r.blockhash(slot, *t + 100 * US); }
            r.timers(*t + 200 * US);
        }
        slot
    };
    // 1. a send: the block engine accepts it, then would-fail
    let mut t = T0 + 10 * MS;
    let s1 = r.sig("S15-1");
    usdc_sale(&mut r, &a, 40, s1, s2, &mut t);
    r.timers(t + 4 * MS);
    t += 5 * MS;
    r.pump(1, t);
    r.verdict("b0", "accepted", Some(s2 + 1), None, t + MS);
    r.verdict("b0", "would-fail", Some(s2 + 1), Some(super::s13_verdicts::PROFIT_FAIL), t + 2 * MS);
    let s = clock(&mut r, T0 + 12_000 * MS, &mut t);
    // 2. a second send (a new state of the same route), which lands: the block engine's `processed`, then its wallet record
    let mut t2 = t + MS;
    let s2b = r.sig("S15-2");
    usdc_sale(&mut r, &a, 60, s2b, s, &mut t2);
    r.timers(t2 + 4 * MS);
    t = t2 + 5 * MS;
    let att = r.attempts();
    assert_eq!((att.len(), att[1]["sent"].as_bool()), (2, Some(true)), "{att:?}");
    r.pump(1, t);
    r.verdict("b1", "processed", Some(s + 1), None, t + MS);
    let s = clock(&mut r, t + 500 * MS, &mut t);
    let rec1 = wallet_record(&r, &att[1], &r.bundles_sent()[1], s, sol0, wsol0, true);
    r.input(InputKind::WalletTx, rec1, t + MS);
    let (tip1, gross1) = (att[1]["tip"]["lamports"].as_u64().unwrap(), att[1]["expected"]["gross"].as_u64().unwrap());
    let s = clock(&mut r, T0 + 25_000 * MS, &mut t);
    // 3. ten decoded swaps on PumpSwap that never execute (hints only)
    let ro = [*crate::venues::PUMPSWAP, p.pool, [0x91; 32], p.t0, p.t1];
    for k in 0..10u64 {
        let signer = { let mut x = [0x45u8; 32]; x[0] = k as u8; x };
        let w = [p.vault0, p.vault1];
        let tx = shred_tx(r.sig(&format!("S15-hint{k}")), signer, &w, &ro, vec![pump_sell(&p, &signer, (k + 1) * 10_000_000_000, 0, &w, &ro)], s, t + k * MS);
        if k % 2 == 0 { let f = executed_copy(&tx, false, t + k * MS + 300 * US); r.tx(tx); r.tx(f); } else { r.tx(tx); }
    }
    let s = clock(&mut r, T0 + 35_000 * MS, &mut t);
    // 4. the ledger's periodic snapshot (the landing's fee, tip and gross), reconciled a minute later
    r.snapshot(s, sol0 - FEE - tip1, wsol0 + gross1, None, "periodic", t + MS);
    // 5. the first attempt's blockhash expires (the ring's head 150 blocks past it, about a minute): the expiry check,
    // its final
    clock(&mut r, T0 + 62_000 * MS, &mut t);
    let expiry = r.pump(1, t + MS);
    assert_eq!(expiry[0]["why"].as_str(), Some("expiry"), "{expiry:?}");
    // 6. a third send (more USDC into the AMM v4 pool): the block engine says `processed`; its blockhash expires a minute
    // later and the expiry check (one getSignatureStatuses) finds it landed, failed: final `landed_fail` from the status,
    // its fee counted provisional until its wallet record comes, two status lines later
    let s = clock(&mut r, T0 + 64_000 * MS, &mut t);
    let mut t3 = t + MS;
    let s3 = r.sig("S15-3");
    usdc_sale(&mut r, &a, 50, s3, s, &mut t3);
    r.timers(t3 + 4 * MS);
    t = t3 + 5 * MS;
    let att = r.attempts();
    assert_eq!((att.len(), att[2]["sent"].as_bool()), (3, Some(true)), "{att:?}");
    r.pump(1, t);
    r.verdict("b2", "processed", Some(s + 1), None, t + MS);
    clock(&mut r, T0 + 128_000 * MS, &mut t);
    // the executor asked (its expiry check, spawned by its housekeeping); the chain's answer stands in for the RPC's
    let asked = r.take_results(1);
    assert!(matches!(&asked[0], Event::Settled(x) if matches!(&**x, crate::exec::Settled::Statuses { why: "expiry", at, .. } if at[0].0 == 2)), "the expiry check of attempt 2");
    let failed = crate::rpc::SigStatus { slot: s + 1, err: Some(json!({ "InstructionError": [2, { "Custom": 1314390018u32 }] })), confirmation: Some("finalized".into()) };
    r.e.step(Event::Settled(Box::new(crate::exec::Settled::Statuses { why: "expiry", at: vec![(2, "expiry")], result: Ok(vec![Some(failed)]), t_ns: t + MS })), t + MS, &mut nop());
    let o = r.lines("outcomes");
    assert_eq!(o.iter().find(|x| x["attempt"] == 2).map(|x| (x["final"].clone(), x["final_src"].clone())), Some((json!("landed_fail"), json!("statuses"))), "{o:?}");
    let s = clock(&mut r, T0 + 150_000 * MS, &mut t);
    let rec2 = wallet_record(&r, &att[2], &r.bundles_sent()[2], s, sol0 - FEE - tip1, wsol0 + gross1, false);
    r.input(InputKind::WalletTx, rec2, t + MS);
    clock(&mut r, T0 + 170_000 * MS, &mut t);
    // the stop's final line, as `arbx run` writes it
    r.e.write_final_status(0, "scenario_end");
    let lines = r.lines("status");
    eprintln!("S15: {} status lines; the last: {}", lines.len(), serde_json::to_string(lines.last().unwrap()).unwrap());
    let pairs = check_counters(&lines);
    eprintln!("S15: {} total/delta pairs checked: {pairs:?}", pairs.len());
    for must in ["store.updates_total", "store.stale_total", "exec.decisions_total", "exec.would_send_total", "exec.attempts_total", "exec.sent_total", "exec.landed_total",
        "money.failed_fees_total_lamports", "money.rent_locked_total", "money.rent_reclaimed_total", "money.entries_total", "counts_total.trigger", "counts_total.evaluation",
        "exec.counts_total.canary_sent", "exec.counts_total.verdict_would_fail"] {
        assert!(pairs.iter().any(|p| p == must), "{must} was checked: {pairs:?}");
    }
    let last = lines.last().unwrap();
    assert_eq!(last["stop_reason"].as_str(), Some("scenario_end"));
    // what moved: the executor's and the ledger's totals are the run's
    assert_eq!((last["exec"]["sent_total"].as_u64(), last["exec"]["landed_total"].as_u64(), last["exec"]["attempts_total"].as_u64()), (Some(3), Some(2), Some(3)), "{}", last["exec"]);
    assert_eq!((last["money"]["entries_total"].as_u64(), last["money"]["rent_locked_total"].as_u64(), last["money"]["tips_total"].as_u64(), last["money"]["failed_fees_total_lamports"].as_u64()),
        (Some(2), Some(super::s14_ledger::RENT), Some(tip1), Some(FEE)), "{}", last["money"]);
    // the provisional failed fee was in the total while it waited for its record (the supervisor reads that total)
    assert!(lines.iter().any(|l| l["money"]["failed_fees_total_lamports"] == json!(FEE) && l["money"]["fees_fail_total"] == json!(0)), "a line with the fee provisional");
    assert_eq!(last["counts_total"]["trigger_hint_only"].as_u64(), Some(10));
    // the block engine's answers, by outcome, summed over the lines
    let verdicts: BTreeMap<String, u64> = lines.iter().flat_map(|l| l["exec"]["verdicts_delta"].as_object().cloned().unwrap_or_default())
        .fold(BTreeMap::new(), |mut m, (k, v)| { *m.entry(k).or_default() += v.as_u64().unwrap(); m });
    assert_eq!(verdicts, [("accepted".to_string(), 1), ("processed".into(), 2), ("would-fail".into(), 1)].into_iter().collect(), "{verdicts:?}");
    let rc = r.lines("recon");
    assert!(!rc.is_empty() && rc.iter().all(|x| x["ok"] == json!(true)), "{rc:?}");
    let done = r.finish_and_replay();
    done.check_expected();
}

//! The executor replay (review WP-09 "For the WP-05 merge"; go-live gate item 3, with S9, S11 and the hour in synth.rs).
//! A run with a shadow or dry-run executor journals its exec_init record (what the executor started with that the
//! frozen config does not hold) and, at each decision, what the send checks read from outside the journal whenever it
//! changes (the gate's mode and reason, the leader's kind, the Jito token, the recorder). The replay builds an offline
//! executor from the record, hands it the run's decision-point records and settlements, and reproduces every decision
//! (`sent`, `would_send`, `reason_ungated`, `ev`, `rank`, `crowding`, `attempt` and every verdict compared), every
//! attempt (attempts.jsonl, the real clock's stage times, the LeaderBook's snapshot and a dry run's signature aside) and
//! the state digest, which folds the executor's state.
use super::harness::rewrite_journal;
use super::*;
use crate::exec::{Mode, Settled};
use crate::rec::journal::JBody;
use std::sync::atomic::{AtomicBool, Ordering};

const POOLS3: [&str; 3] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4"];
/// these tests are about the gate and the records, not the ≥1M class's throttle (S11)
const NO_BAND_THROTTLE: [(&str, &str); 1] = [("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0")];

/// a USDC sale of 1/`frac` of pool `m`'s USDC reserve by `sig` at `slot`, resolved by quiescence at the timers 4 ms after
/// its last write; returns the time after
fn usdc_sale(r: &mut Rig, m: &PoolMeta, frac: u64, label: &str, slot: u64, mut t: u64) -> u64 {
    let usdc_in = token_amount(&r.data(if sol_is_t0(m) { &m.vault1 } else { &m.vault0 })) / frac;
    let w = swap(&r.chain, m, !sol_is_t0(m), usdc_in, slot, r.unix0).0;
    let s = r.sig(label);
    for (k, d) in w { r.write(k, d, slot, Some(s), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    t + 5 * MS
}

/// the journal's decision-point records (INPUT 3 `src` "decision"), in order
fn decision_records(dir: &Path) -> Vec<Value> {
    crate::rec::journal::read_dir(dir).unwrap().into_iter().filter(crate::rec::journal::is_gate_decision)
        .map(|x| match x.body { JBody::Input { data, .. } => data, _ => unreachable!() }).collect()
}

/// The SendGate's reason changes while its mode stays shadow (a pause from the control socket, then the lag SLO's
/// shadow over it): each executor decision's reason is the gate it read, and the run journals a record at the change of
/// reason (WP-05 journaled only a change of mode: a replay would have said `gate_shadow:paused` where the run said
/// `gate_shadow:state_slo`). The replay reproduces each one; without the reason's record it differs
#[test]
fn the_gate_reason_an_executor_decision_read_is_journaled_and_replayed() {
    let mut r = Rig::new("x-gate", Setup { pools: &POOLS3, config: &NO_BAND_THROTTLE, exec: Some(ExecSetup { sticky_shadow: false, ..Default::default() }),
        ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    let a = r.meta("usdc.ammv4");
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    let gate = r.gate.clone();
    let mut t = usdc_sale(&mut r, &a, 300, "G-live", s2, T0 + 10 * MS);
    gate.shadow("paused", "harness: pause-sending", false).unwrap();
    t = usdc_sale(&mut r, &a, 3_000, "G-paused", s2, t + 5 * MS);
    // the lag SLO's shadow over the pause: the mode stays shadow, the reason changes
    gate.shadow("state_slo", "harness: lag SLO breached", false).unwrap();
    t = usdc_sale(&mut r, &a, 3_000, "G-slo", s2, t + 5 * MS);
    gate.resume("harness").unwrap();
    usdc_sale(&mut r, &a, 3_000, "G-resumed", s2, t + 5 * MS);
    let reasons: Vec<(String, Option<String>)> = r.opportunities().iter().map(|d| (d["reason"].as_str().unwrap().to_string(), d["reason_ungated"].as_str().map(String::from))).collect();
    assert_eq!(reasons.iter().map(|x| x.0.as_str()).collect::<Vec<_>>(), ["would_send", "gate_shadow:paused", "gate_shadow:state_slo", "would_send"], "{reasons:?}");
    assert!(reasons.iter().all(|x| x.1.is_none()), "each a would-send once the gate is put aside: {reasons:?}");
    r.rec.sync();
    let recs: Vec<(String, Option<String>)> = decision_records(&r.dir).iter().map(|d| (d["mode"].as_str().unwrap().to_string(), d["reason"].as_str().map(String::from))).collect();
    assert_eq!(recs, vec![("live".into(), None), ("shadow".into(), Some("paused".into())), ("shadow".into(), Some("state_slo".into())), ("live".into(), None)],
        "one record per change, the reason's too");
    let done = r.finish_and_replay();
    assert_eq!(done.replay["executor"]["records_staged"].as_u64(), Some(4));
    // without the reason's record (WP-05's mode-only records) the replay reads the pause there, and differs
    rewrite_journal(&done.dir, |_, x| {
        let d = &x.3[21..];
        let is_it = x.0 == crate::rec::journal::J_INPUT && d[0] == InputKind::Gate as u8 && String::from_utf8_lossy(d).contains("state_slo");
        if is_it { vec![] } else { x.3.clone() }
    });
    let rp = crate::replay::replay(&done.dir, &crate::replay::Opts { compare: true, out: Some(done.dir.join("no-reason")), ..Default::default() }).unwrap();
    let diff = rp.diff.unwrap();
    assert!(!rp.ok, "{}", diff["summary"]);
    assert!(diff["diffs"].as_array().unwrap().iter().any(|x| x["field"] == "reason" && x["run"] == "gate_shadow:state_slo" && x["replay"] == "gate_shadow:paused"), "{diff}");
}

/// Review WP-09 #3 / E1 with the executor (the "For the WP-05 merge" item 9 test): the real `Engine::run` loop on the
/// real clock with a `Mode::Shadow` executor, fed by another thread (trades on three pools, a slot every 400 ms with its
/// Clock and the blockhash ring's head), the SendGate paused, its reason changed and resumed by that thread mid-run (as
/// the control socket and the lag SLO move it), a 100 ms sampler (status only). The decisions read the live gate, the
/// LeaderBook and the recorder; the replay's offline executor reads the run's records and gives every decision, every
/// attempt (`sent = false`) and the digests
#[test]
fn a_run_loop_with_a_shadow_executor_replays_identically() {
    let mut r = Rig::new("x-runloop", Setup { pools: &POOLS3, config: &NO_BAND_THROTTLE, exec: Some(ExecSetup { sticky_shadow: false, ..Default::default() }),
        ..Default::default() });
    let gate = r.gate.clone();
    std::fs::write(r.dir.join("meta.json"), serde_json::to_string(&json!({ "schema": "arbx.meta/2.0", "send_gate": gate.json() })).unwrap()).unwrap();
    r.make_ready(T0);
    let s0 = r.s0;
    // the schedule: Jito leaders, a slot of another kind every 8 (`leader_skip_kind`)
    let sched: Vec<Pk> = (0..64).map(|i| if i % 8 == 7 { LEADER_OTHER } else if i % 8 < 4 { LEADER_JITO } else { LEADER_JITO2 }).collect();
    r.leaders(s0, &sched, T0 + 7 * MS);
    r.blockhash(s0 + 1, T0 + 7 * MS + 100 * US);
    let (tx, rx) = crossbeam_channel::unbounded::<Event>();
    let stop = Arc::new(AtomicBool::new(false));
    let sampler = {
        let (gate, back, stop) = (gate.clone(), tx.clone(), stop.clone());
        std::thread::spawn(move || {
            let mut last = Value::Null;
            while !stop.load(Ordering::Relaxed) {
                let mut g = gate.json();
                if let Some(m) = g.as_object_mut() { m.remove("since_ns"); }
                if g != last {
                    let mut d = gate.json();
                    d["src"] = json!("watch");
                    let _ = back.send(Event::Input { kind: InputKind::Gate, data: Arc::new(d) });
                    last = g;
                }
                std::thread::sleep(std::time::Duration::from_millis(100));
            }
        })
    };
    let metas: Vec<PoolMeta> = POOLS3.iter().map(|n| r.meta(n)).collect();
    let (ar, mut chain, unix0) = (r.ar.clone(), r.chain.clone(), r.unix0);
    let feeder = {
        let (tx, gate) = (tx.clone(), gate.clone());
        std::thread::spawn(move || {
            let now = crate::feeds::clock::real_ns;
            let mut wv = 10_000u64;
            let send_acct = |chain: &mut HashMap<Pk, Vec<u8>>, wv: &mut u64, key: Pk, data: Vec<u8>, slot: u64, txn: Option<[u8; 64]>| {
                *wv += 1;
                let t = now();
                let d: Arc<[u8]> = data.clone().into();
                let fx = fixtures().get(&key);
                let (lamports, owner) = (fx.map_or(1, |x| x.lamports), fx.map_or([0; 32], |x| x.owner));
                let aseq = ar.record(&AcctUpdate { pubkey: key, slot, write_version: *wv, t_recv: t, src: asrc::GRPC, is_startup: false, txn, lamports, owner, data: &d, bank_id: None });
                chain.insert(key, data);
                tx.send(Event::Account { slot, pubkey: key, owner, lamports, data: d, t, txn, write_version: *wv, is_startup: false, src: asrc::GRPC, aseq, bank_id: None }).unwrap();
            };
            let t_start = now();
            let (mut slot, mut next_slot, mut n) = (s0 + 1, t_start, 0u64);
            let mut phase = 0;
            while now() < t_start + 1_400_000_000 {
                let t = now();
                if t >= next_slot {
                    slot += 1;
                    tx.send(Event::Slot { slot, status: 0, t, parent: Some(slot - 1), dead_error: None, bank_id: None }).unwrap();
                    let c = clock_at(&chain[&*CLOCK_SYSVAR], slot, unix0 + (slot.saturating_sub(s0) * 400 / 1_000) as i64);
                    send_acct(&mut chain, &mut wv, *CLOCK_SYSVAR, c, slot, None);
                    tx.send(Event::Input { kind: InputKind::BlockhashHead, data: Arc::new(json!({ "hash": b58(&[slot as u8; 32]), "slot": slot, "height": slot - 1_000_000,
                        "src": "slotidx", "commitment": "confirmed", "t_ns": t })) }).unwrap();
                    next_slot += 400_000_000;
                }
                // the operator pauses sending, the lag SLO puts its own shadow over the pause, sending resumes
                let el = t - t_start;
                if phase == 0 && el >= 300_000_000 { let _ = gate.shadow("paused", "harness", false); phase = 1; }
                if phase == 1 && el >= 600_000_000 { let _ = gate.shadow("state_slo", "harness", false); phase = 2; }
                if phase == 2 && el >= 900_000_000 { let _ = gate.resume("harness"); phase = 3; }
                n += 1;
                let m = &metas[(n % metas.len() as u64) as usize];
                // USDC into the AMM v4 pool now and then (a gap opens), small trades both ways elsewhere
                let (usdc_in, amount) = if m.venue == Venue::RayAmmV4 && n % 6 == 2 { (true, 2_000_000_000) } else if n % 2 == 0 { (false, SOL / 10) } else { (true, 12_000_000) };
                let zfo = if usdc_in { !sol_is_t0(m) } else { sol_is_t0(m) };
                if let Some((w, _)) = try_swap(&chain, m, zfo, amount, slot, unix0) {
                    let sig = { let mut s = [0u8; 64]; s[..8].copy_from_slice(&n.to_le_bytes()); s[8] = 0xe5; s };
                    let wk: Vec<Pk> = w.iter().map(|x| x.0).collect();
                    tx.send(Event::Tx(shred_tx(sig, [0x33; 32], &wk, &[m.pool], vec![], slot, now()))).unwrap();
                    for (k, d) in w { send_acct(&mut chain, &mut wv, k, d, slot, Some(sig)); }
                }
                std::thread::sleep(std::time::Duration::from_millis(3));
            }
        })
    };
    let s2 = stop.clone();
    let stopper = std::thread::spawn(move || { std::thread::sleep(std::time::Duration::from_millis(1_600)); s2.store(true, Ordering::Relaxed); });
    let end = r.e.run(&rx, &stop, u64::MAX, |_| {});
    assert_eq!(end, crate::engine::RunEnd::Stopped);
    feeder.join().unwrap();
    sampler.join().unwrap();
    stopper.join().unwrap();
    r.rec.close();
    let decisions = rec::read_jsonl(&r.dir, "decisions").unwrap();
    let opps: Vec<&Value> = decisions.iter().filter(|d| d["opp"].is_u64()).collect();
    let n_with = |p: &str| opps.iter().filter(|d| d["reason"].as_str().is_some_and(|x| x.starts_with(p))).count();
    let would = opps.iter().filter(|d| d["would_send"] == json!(true)).count();
    eprintln!("run loop with a shadow executor: {} opportunities, {would} would-sends; reasons: would_send {}, gate_shadow:paused {}, gate_shadow:state_slo {}",
        opps.len(), n_with("would_send"), n_with("gate_shadow:paused"), n_with("gate_shadow:state_slo"));
    assert!(would > 0 && n_with("gate_shadow") > 0, "would-sends, and decisions behind the closed gate: {} opportunities", opps.len());
    let att = rec::read_jsonl(&r.dir, "attempts").unwrap();
    assert!(!att.is_empty() && att.iter().all(|l| l["sent"] == json!(false) && l["kind"] == "shadow"), "would-sends only: recorded with sent = false");
    let rp = r.replay_compare("replay");
    let c = &rp.summary["compare"];
    assert!(rp.ok, "the replay reproduces every decision and attempt: {} {}", rp.summary["not_whole"], serde_json::to_string_pretty(rp.diff.as_ref().unwrap()).unwrap());
    assert_eq!((c["identical"].clone(), c["digests_same"].clone(), c["attempts_compared"].clone(), c["attempts_differ"].clone()),
        (c["compared"].clone(), json!(true), json!(att.len()), json!(0)), "{c}");
    assert_eq!((rp.summary["executor"]["replayed"].as_bool(), rp.summary["executor"]["records_mismatch"].as_u64()), (Some(true), Some(0)), "{}", rp.summary["executor"]);
}

/// A WP-05 recording made before the executor replay (engine_init `executor` true, no exec_init record): its executor
/// cannot be rebuilt, so its replay is never OK (`executor_not_replayed`), its executor's verdicts and fields counted
/// instead of compared
#[test]
fn a_recording_made_before_the_executor_replay_is_not_replayed() {
    let mut r = Rig::new("x-pre", Setup { pools: &POOLS3, exec: Some(ExecSetup::default()), ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    let a = r.meta("usdc.ammv4");
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    usdc_sale(&mut r, &a, 300, "pre", s2, T0 + 10 * MS);
    assert_eq!(r.attempts().len(), 1, "a would-send");
    r.e.finish();
    r.rec.close();
    // the boot section as a WP-05 run wrote it: no exec_init record
    let mut dropped = 0;
    rewrite_journal(&r.dir, |_, x| {
        if x.0 == crate::rec::journal::J_INPUT && x.2 == 0 && x.3[21] == InputKind::ExecInit as u8 { dropped += 1; vec![] } else { x.3.clone() }
    });
    assert_eq!(dropped, 1);
    let rp = r.replay_compare("replay");
    assert!(!rp.ok, "never a silent OK");
    assert_eq!((rp.summary["executor"]["run"].as_bool(), rp.summary["executor"]["replayed"].as_bool(), rp.summary["executor_replayed"].as_bool()), (Some(true), Some(false), Some(false)));
    assert!(rp.summary["not_whole"].as_array().unwrap().iter().any(|w| w["why"] == "executor_not_replayed" && w["detail"].as_str().unwrap().contains("no exec_init record")),
        "{}", rp.summary["not_whole"]);
    let s = &rp.diff.as_ref().unwrap()["summary"];
    assert_eq!((s["executor_replayed"].as_bool(), s["attempts_compared"].is_null()), (Some(false), true), "{s}");
    assert!(s["executor_fields_not_replayed"].as_u64().unwrap() >= 1, "the run's would-send (attempt, ev, rank, sent, would_send) counted, not compared: {s}");
}

/// A dry run (go-live gate item 4) replays too: its would-sends are signed by a new throwaway key in the replay (the
/// signature and signer are the only attempt fields not compared), and its settlements (INPUT 9 `settled` in WP-05's
/// `{what: …}` forms: a simulation's answer, a fire result, a statuses answer) reach the replay's executor as they
/// reached the run's (review WP-09 "For the WP-05 merge" item 4): the simulation's sims.jsonl line is the run's
#[test]
fn a_dry_run_replays_with_its_settlements() {
    let mut r = Rig::new("x-dry", Setup { pools: &POOLS3, config: &[("simulate = false   # true:", "simulate = true   # true:")],
        exec: Some(ExecSetup { mode: Mode::DryRun, ..Default::default() }), ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    let a = r.meta("usdc.ammv4");
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    let t = usdc_sale(&mut r, &a, 300, "dry", s2, T0 + 10 * MS);
    let att = r.attempts();
    assert_eq!(att.len(), 1);
    assert_eq!((att[0]["kind"].as_str(), att[0]["dry_run"]["checks_ok"].as_bool(), att[0]["dry_run"]["simulated"].as_bool()), (Some("dry_run"), Some(true), Some(true)), "{}", att[0]["dry_run"]);
    // the executor's tasks answer (the run's would come back from its runtime): journaled as INPUT 9 when the engine takes them
    let sent = crate::send::Sent { attempt: 7, path: "jito-bundle".into(), sig: None, tip_account: None, tip_lamports: 0, t_sent: 0, t_ack: 0, ms: 0.0, ok: false, status: None,
        reply: Some("never left".into()), bundle: None, blockhash_slot: None, queue_wait_us: None, drop: Some("rate_queue_timeout"), lambda: None, endpoint: None, leader_kind: None };
    for (k, st) in [Settled::DrySim { attempt: 0, line: json!({ "attempt": 0, "src": "dry_run", "t_ns": t, "sim_ms": 1.25, "sim_slot": s2, "err": null, "units": 91_000 }) },
        Settled::Fired { attempt: 7, fired: crate::send::Fired { id: 7, t_ns: t, copies: vec![sent] } },
        Settled::Statuses { why: "check", at: vec![(7, "+2s")], result: Ok(vec![None]), t_ns: t }].into_iter().enumerate() {
        r.e.step(Event::Settled(Box::new(st)), t + (k as u64 + 1) * MS, &mut nop());
    }
    let run_sims = { r.rec.sync(); rec::read_jsonl(&r.dir, "sims").unwrap() };
    assert_eq!(run_sims.len(), 1, "the simulation's answer");
    let done = r.finish_and_replay();
    assert_eq!(done.replay["executor"]["settled_fed"].as_u64(), Some(3), "{}", done.replay["executor"]);
    assert_eq!(done.replay["executor"]["exec_init"]["mode"], json!("dry_run"));
    let replay_sims = rec::read_jsonl(&done.dir.join("replay"), "sims").unwrap();
    assert_eq!(replay_sims, run_sims, "the run's simulation answer, through the journal");
}

/// Review WP-07 #1 (the blocker; go-live gate item 3 on the frz config): a frz-like recording replays identically with
/// the bankroll cap binding. The run's executor (a shadow one under the frz canary's bankroll: 85% of the liquid SOL +
/// WSOL less 0.03 SOL, at most the WSOL; the size cap 4.2 SOL) decides with the ledger's money view after its start
/// snapshot (INPUT 13: frz on 2026-10-05, 222,956,693 native and 191,524,924 WSOL), so every route is sized at most
/// 191,524,924 and the large ones exactly that. The decision-point records carry the money view (`money`, journaled
/// whenever it differs from the last record) and the replay, which has no ledger, applies them: every decision, attempt
/// and digest is the run's. The same journal without `money` replays at the configured cap, and differs
#[test]
fn a_frz_like_recording_with_the_bankroll_cap_replays_identically() {
    const FRZ_BANKROLL: [(&str, &str); 2] = [("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0"),
        // (merge of WP-06: `[live] max_new_token_accounts` is gone; the bankroll keys go where it was)
        ("# (WP-06: max_new_token_accounts is gone", "bankroll_share = 0.85\nbankroll_reserve_sol = 0.03\n# (WP-06: max_new_token_accounts is gone")];
    let mut r = Rig::new("x-frz-bankroll", Setup { pools: &POOLS3, config: &FRZ_BANKROLL, exec: Some(ExecSetup::default()), ..Default::default() });
    assert_eq!((r.cfg.live.bankroll_share, r.cfg.live.bankroll_reserve_sol, r.cfg.live.max_size_sol), (0.85, 0.03, 4.2));
    r.make_ready(T0);
    // the ledger, as `arbx run` assembles it (a shadow run: its stops record only)
    let wallet = crate::tx::pk(&r.cfg.wallet);
    let stopper = crate::control::Stopper::new(r.gate.clone());
    r.e.ledger = Some(crate::ledger::Ledger::for_run(&r.cfg, wallet, r.rec.clone(), "x-frz-bankroll", false, r.gate.clone(), stopper, Default::default(), None, None));
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    let a = r.meta("usdc.ammv4");
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    // a first decision before the ledger's start snapshot (the configured cap), then frz's balances
    let mut t = usdc_sale(&mut r, &a, 100, "F-before", s2, T0 + 10 * MS);
    r.input(InputKind::Snapshot, crate::ledger::test_snapshot_answer(&wallet, s2, 222_956_693, 191_524_924, 22_967_379, "start"), t + MS);
    for (k, frac) in [100u64, 60, 300, 40].into_iter().enumerate() { t = usdc_sale(&mut r, &a, frac, &format!("F-{k}"), s2, t + 5 * MS); }
    let att = r.attempts();
    let sizes: Vec<u64> = att.iter().map(|x| x["size_lamports"].as_u64().unwrap()).collect();
    eprintln!("frz-like bankroll: attempt sizes {sizes:?}");
    assert!(sizes.len() >= 3, "{sizes:?}");
    assert!(sizes[0] > 191_524_924, "before the snapshot: the configured cap (4.2 SOL) applies: {sizes:?}");
    assert!(sizes[1..].iter().all(|s| *s <= 191_524_924), "after it, the bankroll caps every size: {sizes:?}");
    assert!(sizes[1..].contains(&191_524_924), "the cap binds: {sizes:?}");
    r.rec.sync();
    let recs = decision_records(&r.dir);
    assert!(recs.iter().any(|d| d["money"]["wsol"].as_u64() == Some(191_524_924) && d["money"]["liquid"].as_u64() == Some(414_481_617)), "{recs:?}");
    let done = r.finish_and_replay();
    assert!(done.replay["executor"]["records_staged"].as_u64().unwrap() >= 2);
    // the same journal without the money view: the replay sizes at the configured cap and differs
    rewrite_journal(&done.dir, |_, x| {
        let b = &x.3;
        if x.0 != crate::rec::journal::J_INPUT || b[21] != InputKind::Gate as u8 { return b.clone(); }
        let mut v: Value = serde_json::from_slice(&b[26..]).unwrap();
        if v["src"] != json!("decision") { return b.clone(); }
        if let Some(o) = v.as_object_mut() { o.remove("money"); }
        let js = serde_json::to_vec(&v).unwrap();
        let mut body = vec![InputKind::Gate as u8];
        body.extend((js.len() as u32).to_le_bytes());
        body.extend(&js);
        let mut o = vec![b[0]];
        o.extend((body.len() as u32).to_le_bytes());
        o.extend(&b[5..21]);
        o.extend(body);
        o
    });
    let rp = crate::replay::replay(&done.dir, &crate::replay::Opts { compare: true, out: Some(done.dir.join("no-money")), ..Default::default() }).unwrap();
    let diff = rp.diff.unwrap();
    assert!(!rp.ok, "{}", diff["summary"]);
    assert!(diff["attempt_diffs"].as_array().unwrap().iter().any(|x| x["field"] == json!("size_lamports") && x["run"] == json!(191_524_924u64)
        && x["replay"] == json!(4_200_000_000u64)), "{diff}");
    assert!(diff["diffs"].as_array().unwrap().iter().any(|x| x["field"] == json!("ev")), "{diff}");
}

/// ---- WP-09 part 2. A canary run (its bundle to a block engine in memory) replays with its sends: the offline executor
/// replays the run's send as sent, with the run's signature (the decision-point `sent` record journaled right after it),
/// and the fire's result, the block engine's verdicts and the expiry check's answer come back from the journal: every
/// decision, the attempt and the digests are the run's (S13 and S9 assert it on their own runs). The same journal without
/// its `sent` record (a live or canary recording made before part 2) is never a silent OK: the send is replayed without
/// a signature and counted (`sent_records_missing`, not whole), and its signature-keyed state differs
#[test]
fn a_canary_recording_replays_its_sends_and_one_without_its_sent_records_is_not_whole() {
    let (mut r, s2) = super::s13_verdicts::canary_rig("x-canary", &POOLS3, &CANARY, true);
    let a = r.meta("usdc.ammv4");
    let t = usdc_sale(&mut r, &a, 40, "C-sale", s2, T0 + 10 * MS);
    let att = r.attempts();
    assert_eq!((att.len(), att[0]["sent"].as_bool(), att[0]["kind"].as_str()), (1, Some(true), Some("canary")), "{att:?}");
    r.pump(1, t);
    r.verdict("b0", "accepted", Some(s2 + 1), None, t + MS);
    r.rec.sync();
    let sent: Vec<Value> = crate::rec::journal::read_dir(&r.dir).unwrap().into_iter().filter(crate::rec::journal::is_gate_decision)
        .filter_map(|x| match x.body { JBody::Input { data, .. } if data.get("sent").is_some() => Some(data), _ => None }).collect();
    assert_eq!(sent.len(), 1, "{sent:?}");
    assert_eq!((sent[0]["sent"]["attempt"].as_u64(), sent[0]["sent"]["sig"].clone()), (Some(0), att[0]["tx"]["sig"].clone()), "the attempt and its signature");
    let done = r.finish_and_replay();
    assert_eq!((done.replay["executor"]["exec_init"]["mode"].as_str(), done.replay["executor"]["sent_missing"].as_u64()), (Some("canary"), Some(0)));
    // without the `sent` record
    let mut dropped = 0;
    rewrite_journal(&done.dir, |_, x| {
        let d = &x.3[21..];
        let it = x.0 == crate::rec::journal::J_INPUT && d[0] == InputKind::Gate as u8 && String::from_utf8_lossy(d).contains("\"sent\"");
        if it { dropped += 1; vec![] } else { x.3.clone() }
    });
    assert_eq!(dropped, 1);
    let rp = crate::replay::replay(&done.dir, &crate::replay::Opts { compare: true, out: Some(done.dir.join("no-sent")), ..Default::default() }).unwrap();
    assert!(!rp.ok, "never a silent OK");
    assert!(rp.summary["not_whole"].as_array().unwrap().iter().any(|w| w["why"] == "sent_records_missing" && w["n"] == json!(1)), "{}", rp.summary["not_whole"]);
    assert_eq!(rp.summary["executor"]["sent_missing"].as_u64(), Some(1));
}

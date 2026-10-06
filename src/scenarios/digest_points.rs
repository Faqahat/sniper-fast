//! FT-001 (go-live gate item 3; field test FT-001's segment p1): the run's state digests are compared with its replay's
//! at the same journaled points. The p1 replay reproduced all 55,520 decisions and the decision digest, and still had
//! another state digest: the run digested at the end of its loop (`Engine::finish`) and then journaled 0.209 s of its
//! WP-07 stop sequence (the drain's inputs and housekeeping), which the replay applied before it digested at the end of
//! the journal. The run now journals each digest point (INPUT 14 `digest_point`: `run_end` in `finish`, `stop_end` at the
//! end of `Engine::stop_sequence`) with each part's digest, and the replay digests there, doing what the run did there.
use super::harness::rewrite_journal;
use super::*;
use crate::rec::journal::JBody;

const POOLS3: [&str; 3] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4"];
/// the frz canary's bankroll (`[live]`) and no ≥1M-class throttle (these tests are about the stop, not S11's throttle)
const FRZ: [(&str, &str); 2] = [("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0"),
    ("# (WP-06: max_new_token_accounts is gone", "bankroll_share = 0.85\nbankroll_reserve_sol = 0.03\n# (WP-06: max_new_token_accounts is gone")];

/// a USDC sale of 1/`frac` of pool `m`'s USDC reserve by `label` at `slot`, resolved by quiescence at the timers 4 ms
/// after its last write; returns the time after
fn sale(r: &mut Rig, m: &PoolMeta, frac: u64, label: &str, slot: u64, mut t: u64) -> u64 {
    let usdc_in = token_amount(&r.data(if sol_is_t0(m) { &m.vault1 } else { &m.vault0 })) / frac;
    let w = swap(&r.chain, m, !sol_is_t0(m), usdc_in, slot, r.unix0).0;
    let s = r.sig(label);
    for (k, d) in w { r.write(k, d, slot, Some(s), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    t + 5 * MS
}

/// the digest-point records of a run directory's journal, in order: (seq, data)
fn digest_records(dir: &Path) -> Vec<(u64, Value)> {
    crate::rec::journal::read_dir(dir).unwrap().iter().filter_map(|r| crate::rec::journal::digest_point(r).map(|v| (r.seq, v.clone()))).collect()
}

/// A run as `arbx run` runs the frz canary config in shadow: a shadow executor, the ledger (`Ledger::for_run`, its stops
/// recording only), the start snapshot (INPUT 13), trades with would-sends; then its real end: `finish` (the `run_end`
/// digest point, as `Engine::run` ends) and WP-07's stop sequence (`Engine::stop_sequence`) with the next slot and a
/// blockhash head queued while `finish` ran (the drain journals them and its housekeeping), the stop snapshot read
/// through the ledger's RPC (a local mock holding the wallet's accounts as the start snapshot found them: the stop's
/// reconciliation passes at once), `settle_at_stop`, the `stop_end` digest point. The recorder is closed; returns the
/// rig, the stop sequence's result and the run's digests at `run_end` (before and after `finish`) and at the end
fn stopped_run(name: &'static str) -> (Rig, crate::engine::StopSeq, (crate::engine::Digests, crate::engine::Digests), crate::engine::Digests) {
    let mut r = Rig::new(name, Setup { pools: &POOLS3, config: &FRZ, exec: Some(ExecSetup::default()), ..Default::default() });
    r.make_ready(T0);
    let wallet = crate::tx::pk(&r.cfg.wallet);
    let stopper = crate::control::Stopper::new(r.gate.clone());
    r.e.ledger = Some(crate::ledger::Ledger::for_run(&r.cfg, wallet, r.rec.clone(), name, false, r.gate.clone(), stopper, Default::default(), None, None));
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    let a = r.meta("usdc.ammv4");
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    let start = crate::ledger::test_snapshot_answer(&wallet, s2, 222_956_693, 191_524_924, 0, "start");
    r.input(InputKind::Snapshot, start.clone(), T0 + 9 * MS);
    let mut t = T0 + 10 * MS;
    for (k, frac) in [100u64, 60, 300].into_iter().enumerate() { t = sale(&mut r, &a, frac, &format!("D-{k}"), s2, t + 5 * MS); }
    assert!(!r.attempts().is_empty(), "{name}: would-sends");
    // the run loop ends: `Engine::run` ends with `finish` (its `run_end` digest point)
    let fin = r.e.finish();
    // the stop sequence: the ledger's snapshots read the mock (the start snapshot's accounts, at a later slot)
    let mock = crate::rpc::mock::MockRpc::start();
    {
        use base64::Engine as _;
        let mut m = mock.accounts.lock().unwrap();
        for (k, v) in start["keys"].as_array().unwrap().iter().zip(start["answers"][0]["values"].as_array().unwrap()) {
            if v.is_null() { continue; }
            let data = base64::engine::general_purpose::STANDARD.decode(v["data"][0].as_str().unwrap()).unwrap();
            m.insert(crate::tx::pk(k.as_str().unwrap()), (data, crate::tx::pk(v["owner"].as_str().unwrap()), v["lamports"].as_u64().unwrap()));
        }
    }
    mock.slot.store(s2 + 3, std::sync::atomic::Ordering::Relaxed);
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(1).enable_all().build().unwrap();
    let (tx, rx) = crossbeam_channel::unbounded::<Event>();
    let rpc = crate::rpc::Rpc::race(vec![crate::rpc::Endpoint { name: "mock".into(), url: mock.url.clone(), bearer: None }]);
    r.e.ledger.as_mut().unwrap().set_io(rpc, rt.handle().clone(), tx.clone());
    // what reached the engine's channel while `finish` ran: the next slot, a blockhash head
    let now = crate::feeds::clock::real_ns();
    tx.send(Event::Slot { slot: s2 + 1, status: 0, t: now, parent: Some(s2), dead_error: None, bank_id: None }).unwrap();
    tx.send(Event::Input { kind: InputKind::BlockhashHead, data: Arc::new(json!({ "hash": b58(&[0x5d; 32]), "slot": s2 + 1,
        "height": (s2 + 1).saturating_sub(1_000_000), "src": "slotidx", "commitment": "confirmed", "t_ns": now })) }).unwrap();
    let st = r.e.stop_sequence(&rx, 60_000_000_000, &mut |_: &str| {});
    let end = r.e.digests();
    r.rec.close();
    drop(rt);
    (r, st, fin, end)
}

/// FT-001 p1's finding on the real Rig: a run with a shadow executor and a ledger ends as `arbx run` ends (`finish`, then
/// WP-07's stop sequence with its stop snapshot), its stop sequence journals records after the `run_end` digest point
/// (the drain's slot, blockhash head, stop snapshot and housekeeping) that change the state, and the replay gives the
/// run's state and decision digests at both of the run's points (each part's too), every decision and attempt the
/// run's. Before FT-001 the replay digested at the end of the journal and differed (as p1's did)
#[test]
fn a_stop_sequence_with_a_ledger_replays_to_the_runs_digests_at_both_points() {
    let (r, st, (before, after), end) = stopped_run("d-stop");
    assert_eq!((st.in_flight, st.settled, st.open.as_ref().map(|o| o.len())), (Some(0), true, Some(0)), "a shadow run has nothing in flight: {st:?}");
    // the run's journal: `run_end` with its digests, the stop sequence's records after it, `stop_end` last
    let recs = crate::rec::journal::read_dir(&r.dir).unwrap();
    let points = digest_records(&r.dir);
    assert_eq!(points.iter().map(|p| p.1["point"].as_str().unwrap()).collect::<Vec<_>>(), vec!["run_end", "stop_end"]);
    let (run_end, stop_end) = (&points[0].1, &points[1].1);
    assert_eq!((run_end["before_finish"]["digest"].as_str(), run_end["digest"].as_str()), (Some(format!("{:016x}", before.state).as_str()), Some(format!("{:016x}", after.state).as_str())));
    assert_eq!(stop_end["digest"].as_str(), Some(format!("{:016x}", end.state).as_str()));
    assert_eq!(recs.last().map(|x| x.seq), Some(points[1].0), "stop_end is the journal's last record");
    let tail: Vec<&JBody> = recs.iter().filter(|x| x.seq > points[0].0 && x.seq < points[1].0).map(|x| &x.body).collect();
    assert!(tail.iter().any(|b| matches!(b, JBody::Slot { .. })) && tail.iter().any(|b| matches!(b, JBody::Timer { what: crate::engine::TIMER_HK, .. }))
        && tail.iter().any(|b| matches!(b, JBody::Input { kind: 13, data } if data["why"] == "stop")), "the drain's slot, housekeeping and stop snapshot: {tail:?}");
    assert!(tail.iter().all(|b| !matches!(b, JBody::Account { .. } | JBody::TxFirst { .. } | JBody::TxCopy { .. })), "the drain prices nothing");
    // the stop sequence changed the state after `finish` digested it (the decisions did not change): a replay digesting
    // at the end of the journal compares another state
    assert_ne!(end.state, after.state, "the drain's records change the state");
    assert_eq!(end.decision, after.decision);
    let rp = r.replay_compare("replay");
    let dg = &rp.summary["digests"];
    assert!(rp.ok, "{} {}", rp.summary["not_whole"], serde_json::to_string_pretty(dg).unwrap());
    let c = &rp.summary["compare"];
    assert_eq!((c["identical"].clone(), c["attempts_differ"].as_u64(), c["attempts_compared"].clone()), (c["compared"].clone(), Some(0), c["attempts_run"].clone()), "{c}");
    assert_eq!((dg["checked"].as_bool(), dg["same"].as_bool(), dg["point"].as_str()), (Some(true), Some(true), Some("marker")), "{dg}");
    let at: Vec<(String, String, bool)> = dg["points"].as_array().unwrap().iter().map(|p| (p["point"].as_str().unwrap().into(), p["how"].as_str().unwrap().into(),
        p["same"] == json!(true))).collect();
    assert_eq!(at, vec![("run_end".into(), "marker".into(), true), ("stop_end".into(), "marker".into(), true)], "{dg}");
    for p in dg["points"].as_array().unwrap() {
        assert_eq!((p["parts_differ"].clone(), p["counts_differ"].clone()), (json!([]), json!({})), "{p}");
        assert_ne!(p["run"]["parts"], json!(null), "every part recorded");
    }
    assert_eq!(dg["points"][0]["before_finish_parts_differ"], json!([]));
    assert_eq!((rp.digest, rp.decision_digest), (end.state, end.decision), "the replay's state at the end of the journal is the run's at stop_end");
    // the replay's own events.jsonl has its digest points too
    let ev: Vec<Value> = rec::read_jsonl(&r.dir.join("replay"), "events").unwrap().into_iter().filter(|e| e["kind"] == "engine_digests").collect();
    assert_eq!(ev.iter().map(|e| e["detail"]["point"].clone()).collect::<Vec<_>>(), vec![json!("run_end"), json!("stop_end")]);
}

/// A recording made before the digest-point records (FT-001 p1: build 11e25d1) has only events.jsonl's engine_digests,
/// without `point` or parts: the replay digests (and runs `finish`) right after its last record at or before the
/// `t_engine` that `finish` recorded, the stop sequence's records coming after it (`inferred_t_engine`), and agrees. One
/// whose digests have no time to place them by is not checked ("digest point unknown"), and that is no difference
#[test]
fn a_recording_made_before_the_digest_point_records_is_checked_where_its_run_digested() {
    let (r, _, (before, after), _) = stopped_run("d-legacy");
    // the journal without INPUT 14, events.jsonl's engine_digests as 11e25d1 wrote them (run_end's, without parts)
    rewrite_journal(&r.dir, |_, x| if x.0 == crate::rec::journal::J_INPUT && x.3[21] == InputKind::DigestPoint as u8 { vec![] } else { x.3.clone() });
    assert!(digest_records(&r.dir).is_empty());
    let events = |dir: &Path, f: &dyn Fn(&mut Value) -> bool| {
        let p = rec::stream_files(dir, "events")[0].clone();
        let mut out = String::new();
        for l in std::fs::read_to_string(&p).unwrap().lines() {
            let mut v: Value = serde_json::from_str(l).unwrap();
            if v["kind"] == "engine_digests" && !f(&mut v["detail"]) { continue; }
            out.push_str(&v.to_string());
            out.push('\n');
        }
        std::fs::write(&p, out).unwrap();
    };
    events(&r.dir, &|d| {
        if d["point"] != "run_end" { return false; }
        *d = json!({ "t_engine": d["t_engine"], "decisions": d["decisions"], "opportunities": d["opportunities"],
            "before_finish": { "digest": d["before_finish"]["digest"], "decision_digest": d["before_finish"]["decision_digest"] },
            "digest": d["digest"], "decision_digest": d["decision_digest"] });
        true
    });
    let rp = crate::replay::replay(&r.dir, &crate::replay::Opts { compare: true, out: Some(r.dir.join("legacy")), ..Default::default() }).unwrap();
    let dg = &rp.summary["digests"];
    assert!(rp.ok, "{}", serde_json::to_string_pretty(dg).unwrap());
    assert_eq!((dg["checked"].as_bool(), dg["same"].as_bool(), dg["point"].as_str()), (Some(true), Some(true), Some("inferred_t_engine")), "{dg}");
    assert_eq!(dg["points"].as_array().unwrap().len(), 1, "run_end only: {dg}");
    assert_eq!((dg["replay"]["before_finish"]["digest"].as_str(), dg["replay"]["digest"].as_str()),
        (Some(format!("{:016x}", before.state).as_str()), Some(format!("{:016x}", after.state).as_str())));
    assert!(dg["points"][0]["parts_differ"].is_null(), "a record without parts: {dg}");
    // without its time the point cannot be placed: not checked, and no difference
    events(&r.dir, &|d| { if let Some(o) = d.as_object_mut() { o.remove("t_engine"); } true });
    let rp = crate::replay::replay(&r.dir, &crate::replay::Opts { compare: true, out: Some(r.dir.join("unknown")), ..Default::default() }).unwrap();
    let dg = &rp.summary["digests"];
    assert_eq!((dg["checked"].as_bool(), dg["same"].as_bool()), (Some(false), None), "{dg}");
    assert!(dg["not_checked"].as_str().unwrap().contains("digest point is unknown"), "{dg}");
    assert!(rp.ok, "an unknown digest point is no difference: {}", rp.summary["not_whole"]);
}

/// The digest's parts: folded in order they are the state digest (`digests` and `digest` agree), each has a name, and a
/// change of one part's state shows in that part only; a digest point whose recorded parts differ names them
#[test]
fn the_digest_parts_fold_to_the_state_digest_and_name_what_differs() {
    let mut r = Rig::new("d-parts", Setup { pools: &POOLS3, exec: Some(ExecSetup::default()), ..Default::default() });
    r.make_ready(T0);
    let d0 = r.e.digests();
    assert_eq!(d0.state, r.e.digest());
    let names: Vec<&str> = d0.parts.iter().map(|p| p.0).collect();
    for n in ["store.accounts", "store.dlmm_arrays", "sigs", "opps", "alts", "commit", "forks", "reads", "counts", "slots", "decision_hash", "exec.totals",
        "exec.counts", "exec.inflight", "exec.open", "exec.finals", "exec.held", "exec.tips", "crowding"] {
        assert!(names.contains(&n), "{n} in {names:?}");
    }
    assert_eq!(names.len(), names.iter().collect::<std::collections::BTreeSet<_>>().len(), "unique names");
    // the next slot: the slots, and what a slot moves (the fork tree, the state stream's messages), not the store
    r.slot(r.s0 + 2, 0, Some(r.s0 + 1), T0 + 20 * MS);
    let d1 = r.e.digests();
    assert_eq!(d1.state, r.e.digest());
    let changed: Vec<&str> = d0.parts.iter().zip(&d1.parts).filter(|(a, b)| a.1 != b.1).map(|(a, _)| a.0).collect();
    assert!(changed.contains(&"slots") && !changed.contains(&"store.accounts") && !changed.contains(&"exec.held"), "{changed:?}");
    // a recorded digest point whose parts differ in one: named
    let mut rec = d1.json();
    rec["parts"]["exec.held"] = json!("0000000000000000");
    assert_eq!(d1.parts_differ(&rec), Some(vec!["exec.held".to_string()]));
    assert_eq!(d1.parts_differ(&json!({ "digest": "x" })), None, "a record without parts (before FT-001)");
}

/// testdata/ft001-p1-tail: cut from FT-001 p1's recording (`ARBX_FT001_P1=<run dir> cargo test --release --lib
/// cut_the_ft001_p1_tail_fixture -- --ignored`): its last journal file's last `KEEP_LOOP` records at or before the run's
/// digest point and every record after it, as a journal file (the file's own header), and the run's engine_digests
fn ft001_tail_dir() -> PathBuf { Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/ft001-p1-tail") }
const KEEP_LOOP: usize = 40;

#[test]
#[ignore]
fn cut_the_ft001_p1_tail_fixture() {
    let Some(run) = std::env::var_os("ARBX_FT001_P1").map(PathBuf::from) else { eprintln!("ARBX_FT001_P1 not set"); return };
    let ev = rec::read_jsonl(&run, "events").unwrap().into_iter().filter(|e| e["kind"] == "engine_digests").last().expect("the run's engine_digests")["detail"].clone();
    let t = ev["t_engine"].as_u64().unwrap();
    let file = rec::stream_files(&run, "journal").last().unwrap().clone();
    let compressed = std::fs::read(&file).unwrap();
    let bytes = rec::decode_zst(&file).unwrap().0;
    let (head, recs) = super::harness::raw_records(&bytes);
    let split = recs.iter().position(|r| r.2 > t).unwrap_or(recs.len());
    let from = split.saturating_sub(KEEP_LOOP);
    let mut out = bytes[..head].to_vec();
    for r in &recs[from..] { out.extend(&r.3); }
    let dir = ft001_tail_dir();
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("journal.tail.bin"), &out).unwrap();
    let meta = json!({ "_doc": "FT-001 segment p1's journal tail (src/scenarios/digest_points.rs `cut_the_ft001_p1_tail_fixture`): the last records of its run loop and every record of its stop sequence, with the run's engine_digests",
        "run": "ft001-p1 (Cherry, 60 min shadow of the frz canary config, build 11e25d1)", "journal_file": file.file_name().unwrap().to_string_lossy(),
        "journal_file_sha256": crate::provenance::sha256_hex(&compressed), "records_in_file": recs.len(), "kept_from_index": from, "loop_records_kept": split - from,
        "stop_records": recs.len() - split, "first_seq": recs[from].1, "last_seq": recs.last().unwrap().1, "engine_digests": ev });
    std::fs::write(dir.join("tail.json"), serde_json::to_string_pretty(&meta).unwrap() + "\n").unwrap();
    eprintln!("{}: {} records, split at {} ({} loop records kept, {} after); {} bytes", file.display(), recs.len(), split, split - from, recs.len() - split, out.len());
    for r in crate::rec::journal::parse(&out).unwrap().1.iter().skip(KEEP_LOOP.saturating_sub(12)) {
        let what = match &r.body { JBody::Input { kind, data } => format!("INPUT {kind} {}", serde_json::to_string(data).unwrap().chars().take(160).collect::<String>()),
            b => format!("{b:?}").chars().take(160).collect() };
        eprintln!("  seq {} t {} (+{} ns) {what}", r.seq, r.t_engine, r.t_engine as i64 - t as i64);
    }
}

/// FT-001 p1's own journal tail (testdata/ft001-p1-tail, cut from the real recording by `cut_the_ft001_p1_tail_fixture`):
/// the run digested (`finish`, its engine_digests' `t_engine`) right after the last record of its loop; `finish` took
/// 207.7 ms, then its stop sequence journaled ten records the run's digests had not seen, the last 0.209 s after the
/// digest point: the drain's housekeeping and inputs, and last the stop snapshot's INPUT 13 (it failed: "no attempt
/// before the deadline"); no account update, transaction or lookup table (the drain prices nothing). The replay of p1
/// made before FT-001 digested after all of them; the replay now places p1's digest point between the two
/// (`digest_plan`'s legacy point, `past_digest_point`: what `drive` uses)
#[test]
fn the_real_p1_tail_splits_at_the_runs_digest_point() {
    const T_RUN: u64 = 1_791_273_479_256_727_634;
    let dir = ft001_tail_dir();
    let meta: Value = serde_json::from_slice(&std::fs::read(dir.join("tail.json")).expect("testdata/ft001-p1-tail/tail.json")).unwrap();
    let recs = crate::rec::journal::parse(&std::fs::read(dir.join("journal.tail.bin")).unwrap()).unwrap().1;
    assert_eq!(recs.len() as u64, meta["last_seq"].as_u64().unwrap() - meta["first_seq"].as_u64().unwrap() + 1, "consecutive records");
    // the run's engine_digests (build 11e25d1: no `point`, no parts) places the digest point by its time
    let plan = crate::replay::digest_plan(std::slice::from_ref(&meta["engine_digests"]));
    let t = plan.legacy.as_ref().map(|l| l.0);
    assert_eq!(t, Some(T_RUN));
    assert_eq!((meta["engine_digests"]["before_finish"]["digest"].as_str(), meta["engine_digests"]["digest"].as_str()), (Some("9eb9360e6daaf99c"), Some("6d674eafbf2d0209")));
    let split = recs.iter().position(|r| crate::replay::past_digest_point(r, T_RUN)).expect("records after the digest point");
    let (looped, stop) = recs.split_at(split);
    assert_eq!(split as u64, meta["loop_records_kept"].as_u64().unwrap());
    assert_eq!(looped.last().unwrap().t_engine, T_RUN, "the run digested right after the last record of its loop");
    assert!(looped.iter().all(|r| r.t_engine <= T_RUN) && stop.iter().all(|r| r.t_engine > T_RUN));
    assert!(looped.iter().any(|r| matches!(r.body, JBody::TxFirst { .. })), "the loop's last records include transactions (the drain journals none)");
    // the stop sequence: no account update, transaction or lookup table; the drain's inputs, its housekeeping, the stop
    // snapshot last
    assert!(stop.iter().all(|r| matches!(&r.body, JBody::Slot { .. } | JBody::BlockMeta { .. } | JBody::Status { .. } | JBody::Tick
        | JBody::Timer { what: crate::engine::TIMER_HK, .. } | JBody::Input { .. })), "{:?}", stop.iter().map(|r| &r.body).collect::<Vec<_>>());
    let last = stop.last().unwrap();
    assert!(matches!(&last.body, JBody::Input { kind: 13, data } if data["why"] == "stop" && data["error"].as_str().is_some_and(|e| e.contains("no attempt before the deadline"))),
        "{:?}", last.body);
    assert_eq!(last.t_engine - T_RUN, 209_378_214, "the replay's last record, 0.209 s after the run's digest point");
    // p1's: `finish` took 207.7 ms (its engine_digests record was written then), then the drain's housekeeping (what
    // moved the crowding map), a blockhash head, six slot statuses (the slots and the fork tree), a block meta (the state
    // stream's messages), the stop snapshot
    let kinds = |f: &dyn Fn(&JBody) -> bool| stop.iter().filter(|r| f(&r.body)).count();
    assert_eq!((stop.len(), kinds(&|b| matches!(b, JBody::Timer { .. })), kinds(&|b| matches!(b, JBody::Input { kind: 1, .. })), kinds(&|b| matches!(b, JBody::Slot { .. })),
        kinds(&|b| matches!(b, JBody::BlockMeta { .. })), kinds(&|b| matches!(b, JBody::Input { kind: 13, .. }))), (10, 1, 1, 6, 1, 1));
    assert!(matches!(stop[0].body, JBody::Timer { what: crate::engine::TIMER_HK, .. }) && stop[0].t_engine - T_RUN == 207_740_924, "{:?}", stop[0]);
}

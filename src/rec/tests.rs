//! The recorder's offline acceptance (PLAN WP-02): rotation, reading a file being written, a stalled writer, replay
//! GAP records, core drops, the disk ladder, the manifest, the headers, and the emit timing test (`#[ignore]`).
use super::*;
use crate::config::RecordCfg;
use crate::control::{GateMode, SendGate, StopReason, Stopper};
use std::time::{Duration, Instant};

fn tmp(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("arbx-rec-{name}-{}-{}", std::process::id(), now_ns()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn rec_in(dir: &Path, cfg: RecordCfg, feeds: &[&str]) -> Rec { rec_echo(dir, cfg, feeds, Box::new(std::io::sink())) }

/// a recorder whose echoed lines go to `echo`
fn rec_echo(dir: &Path, cfg: RecordCfg, feeds: &[&str], echo: Box<dyn Write + Send>) -> Rec {
    start(Opts { dir: dir.to_path_buf(), run: "test-seg".into(), producer: "0123456789abcdef".into(), cfg, feeds: feeds.iter().map(|s| s.to_string()).collect(),
        monitor: false, echo: Some(echo) }).unwrap()
}

/// a gate and a stopper bound to the recorder
fn session(rec: &Rec) -> (Arc<SendGate>, Arc<Stopper>) {
    let g = SendGate::new();
    let s = Stopper::new(g.clone());
    rec.bind_session(g.clone(), s.clone());
    (g, s)
}

fn manifest(dir: &Path) -> Value { serde_json::from_str(&std::fs::read_to_string(dir.join("manifest.json")).unwrap()).unwrap() }

fn mstream<'a>(m: &'a Value, name: &str) -> &'a Value { m["streams"].as_array().unwrap().iter().find(|s| s["name"] == name).unwrap() }

/// wait (at most 10 s) until `f` holds
fn wait_for(what: &str, f: impl Fn() -> bool) {
    let t0 = Instant::now();
    while !f() { assert!(t0.elapsed() < Duration::from_secs(10), "timed out waiting for {what}"); std::thread::sleep(Duration::from_millis(5)); }
}

fn lines(bytes: &[u8]) -> Vec<Value> { bytes.split(|b| *b == b'\n').filter(|l| !l.is_empty()).map(|l| serde_json::from_slice(l).unwrap()).collect() }

fn events(dir: &Path) -> Vec<Value> { read_jsonl(dir, "events").unwrap() }

/// PLAN WP-02 acceptance: rotation with a tiny `rotate_mb` makes several files, each starting with its header and each
/// decodable on its own; the manifest lists them, closed, with the sha256 of each
#[test]
fn rotation_makes_self_contained_files() {
    let d = tmp("rot");
    let rec = rec_in(&d, RecordCfg { rotate_mb: 0.05, ..Default::default() }, &[]);
    for i in 0..5_000 { rec.json(TRIGGERS, json!({ "i": i, "pad": "x".repeat(40) })); }
    rec.close();
    let files = stream_files(&d, "triggers");
    assert!(files.len() >= 4, "{} files", files.len());
    let mut all = Vec::new();
    for (k, f) in files.iter().enumerate() {
        assert_eq!(f.file_name().unwrap().to_str().unwrap(), format!("triggers.{k:03}.jsonl.zst"));
        let (bytes, tail) = decode_zst(f).unwrap();
        assert_eq!(tail, 0, "every frame complete after close");
        let v = lines(&bytes);
        assert_eq!(v[0]["schema"], "arbx.triggers/1.1", "{f:?} starts with its header");
        assert_eq!((v[0]["file_seq"].as_u64(), v[0]["run"].as_str(), v[0]["producer"].as_str()), (Some(k as u64), Some("test-seg"), Some("0123456789abcdef")));
        assert!(v[0]["started_ns"].as_u64().unwrap() > 0);
        assert!(v.len() > 1);
        all.extend(v[1..].iter().map(|x| x["i"].as_u64().unwrap()));
        // under the size limit plus one record: a file rotates as soon as it passes it
        assert!(bytes.len() as f64 <= 0.05 * 1048576.0 + 200.0, "{}", bytes.len());
    }
    assert_eq!(all, (0..5_000).collect::<Vec<u64>>(), "every record once, in order");
    let m: Value = serde_json::from_str(&std::fs::read_to_string(d.join("manifest.json")).unwrap()).unwrap();
    assert_eq!((m["schema"].as_str(), m["final"].as_bool()), (Some("arbx.manifest/1.0"), Some(true)));
    let t = m["streams"].as_array().unwrap().iter().find(|s| s["name"] == "triggers").unwrap();
    assert_eq!((t["records_total"].as_u64(), t["dropped_total"].as_u64(), t["class"].as_str()), (Some(5_000), Some(0), Some("chain")));
    let mf = t["files"].as_array().unwrap();
    assert_eq!(mf.len(), files.len());
    for (f, p) in mf.iter().zip(&files) {
        assert_eq!(f["closed"], true);
        assert_eq!(f["sha256"].as_str().unwrap(), crate::provenance::sha256_hex(&std::fs::read(p).unwrap()), "the hash of the file on disk");
        assert_eq!(f["bytes_written"].as_u64().unwrap(), std::fs::metadata(p).unwrap().len());
        assert!(f["first_t_ns"].as_u64().unwrap() <= f["last_t_ns"].as_u64().unwrap());
    }
    assert_eq!(mf.iter().map(|f| f["records"].as_u64().unwrap()).sum::<u64>(), 5_000);
    let _ = std::fs::remove_dir_all(&d);
}

/// PLAN WP-02 acceptance: a reader decodes a file that is still being written. Every flush ends a zstd frame, so the
/// records written so far are readable; a frame cut in the middle (a write in progress) is left out, not an error
#[test]
fn a_file_being_written_is_readable_up_to_its_last_frame() {
    let d = tmp("live");
    let rec = rec_in(&d, RecordCfg { flush_ms: 20, ..Default::default() }, &[]);
    for i in 0..3 { rec.json(ATTEMPTS, json!({ "attempt": i })); }
    let path = d.join("attempts.000.jsonl.zst");
    let read = |want: usize| -> Vec<Value> {
        let t0 = Instant::now();
        loop {
            if let Ok((b, _)) = decode_zst(&path) { let v = lines(&b); if v.len() >= want + 1 { return v; } }
            assert!(t0.elapsed() < Duration::from_secs(10), "no flush");
            std::thread::sleep(Duration::from_millis(5));
        }
    };
    // no sync: the writer's own 20 ms flush ends the frame while the recorder is open
    let v = read(3);
    assert_eq!(v[0]["schema"], "arbx.attempts/1.1");
    assert_eq!(v[1..].iter().map(|x| x["attempt"].as_u64().unwrap()).collect::<Vec<_>>(), vec![0, 1, 2]);
    for i in 3..6 { rec.json(ATTEMPTS, json!({ "attempt": i })); }
    assert_eq!(read(6).len(), 7, "the next frame is appended and readable too");
    // a torn tail: the complete frames decode, the partial one is reported as ignored bytes
    let mut bytes = std::fs::read(&path).unwrap();
    let frame = zstd::bulk::compress(br#"{"attempt":99}"#, 3).unwrap();
    bytes.extend_from_slice(&frame[..frame.len() / 2]);
    let (b, tail) = decode_frames(&bytes).unwrap();
    assert_eq!((lines(&b).len(), tail), (7, frame.len() / 2));
    assert!(!rec.recorder().unwrap().closed());
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
}

/// PLAN WP-02 acceptance: a stalled writer makes `emit` drop and count, never block. A chain drop is counted (and an
/// events.jsonl `recorder_drop`), but does not touch the SendGate
#[test]
fn a_stalled_writer_drops_and_counts_never_blocks() {
    let d = tmp("stall");
    let rec = rec_in(&d, RecordCfg { queue_chain: 1_000, ..Default::default() }, &[]);
    let (gate, stopper) = { let g = SendGate::new(); (g.clone(), Stopper::new(g)) };
    rec.bind_session(gate.clone(), stopper);
    let r = rec.recorder().unwrap().clone();
    r.stall(Class::Chain, true);
    std::thread::sleep(Duration::from_millis(20));
    let (mut ok, mut worst) = (0, Duration::ZERO);
    for i in 0..1_500 {
        let t = Instant::now();
        if rec.json(TRIGGERS, json!({ "i": i })) { ok += 1; }
        worst = worst.max(t.elapsed());
    }
    assert_eq!(ok, 1_000, "the queue's capacity");
    assert_eq!(r.depth(TRIGGERS), 1_000);
    let st = rec.stats().unwrap();
    assert_eq!(st.dropped.iter().find(|x| x.0 == "triggers").unwrap().1, 500);
    assert!(st.core_ok);
    assert!(worst < Duration::from_millis(50), "emit never waits for the writer ({worst:?})");
    assert_eq!(gate.mode(), GateMode::Live, "chain drops do not stop sending");
    r.stall(Class::Chain, false);
    rec.sync();
    assert_eq!(read_jsonl(&d, "triggers").unwrap().len(), 1_000);
    assert_eq!(r.depth(TRIGGERS), 0);
    let ev = events(&d);
    let drops: Vec<&Value> = ev.iter().filter(|e| e["kind"] == "recorder_drop").collect();
    assert!(!drops.is_empty() && drops.len() <= 2, "the first drop, then at most one a second: {}", drops.len());
    assert_eq!((drops[0]["detail"]["stream"].as_str(), drops[0]["detail"]["class"].as_str(), drops[0]["detail"]["dropped_total"].as_u64()),
        (Some("triggers"), Some("chain"), Some(1)));
    rec.close();
    let m: Value = serde_json::from_str(&std::fs::read_to_string(d.join("manifest.json")).unwrap()).unwrap();
    let t = m["streams"].as_array().unwrap().iter().find(|s| s["name"] == "triggers").unwrap();
    assert_eq!((t["dropped_total"].as_u64(), t["queue_cap"].as_u64(), t["queue_hwm"].as_u64()), (Some(500), Some(1_000), Some(1_000)));
    let _ = std::fs::remove_dir_all(&d);
}

/// MEASUREMENT §1.5: a core drop means the segment can no longer be reconciled: the SendGate goes to shadow
/// (`core_record_loss`) for the rest of the segment, with `gate_change` and `recorder_drop` events
#[test]
fn a_core_drop_shadows_the_segment() {
    let d = tmp("core");
    let rec = rec_in(&d, RecordCfg { queue_core: 10, ..Default::default() }, &[]);
    let (gate, stopper) = { let g = SendGate::new(); (g.clone(), Stopper::new(g)) };
    rec.bind_session(gate.clone(), stopper);
    let r = rec.recorder().unwrap().clone();
    r.stall(Class::Core, true);
    std::thread::sleep(Duration::from_millis(20));
    for i in 0..10 { assert!(rec.json(ATTEMPTS, json!({ "attempt": i }))); }
    assert_eq!(gate.mode(), GateMode::Live);
    assert!(!rec.json(OUTCOMES, json!({ "attempt": 10 })), "the core queue is full");
    assert_eq!(gate.mode(), GateMode::Shadow);
    assert_eq!(gate.reason(), "core_record_loss");
    assert!(gate.sticky(), "for the rest of the segment");
    assert!(gate.resume("operator").is_err());
    assert!(!rec.stats().unwrap().core_ok);
    r.stall(Class::Core, false);
    rec.sync();
    let ev = events(&d);
    assert!(ev.iter().any(|e| e["kind"] == "gate_change" && e["detail"]["reason"] == "core_record_loss"), "{ev:?}");
    assert!(ev.iter().any(|e| e["kind"] == "recorder_drop" && e["detail"]["stream"] == "outcomes" && e["detail"]["class"] == "core"));
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
}

/// a replay stream's record in the accounts framing, `u8 kind | u32 body_len | body` (a stand-in kind 99 with its seq)
fn acct_rec(seq: u64) -> Record { let mut b = vec![99u8]; b.extend(8u32.to_le_bytes()); b.extend(seq.to_le_bytes()); Record::Bin(b) }

/// accounts.bin's records after its header: (kind, body)
fn acct_records(bytes: &[u8]) -> Vec<(u8, Vec<u8>)> {
    assert_eq!(&bytes[..8], b"ARBXACC\0");
    assert_eq!(u16::from_le_bytes([bytes[8], bytes[9]]), 2);
    let hlen = u16::from_le_bytes([bytes[10], bytes[11]]) as usize;
    let h: Value = serde_json::from_slice(&bytes[12..12 + hlen]).unwrap();
    assert_eq!((h["schema"].as_str(), h["file_seq"].as_u64()), (Some("arbx.accounts/2.0"), Some(0)));
    let mut p = 12 + hlen;
    let mut out = Vec::new();
    while p < bytes.len() {
        let k = bytes[p];
        let n = u32::from_le_bytes(bytes[p + 1..p + 5].try_into().unwrap()) as usize;
        out.push((k, bytes[p + 5..p + 5 + n].to_vec()));
        p += 5 + n;
    }
    out
}

/// PLAN WP-02 acceptance: a replay-class drop writes a GAP mark (accounts kind 6: first lost aseq, how many) with the
/// stream's next record; trading goes on (the gate is untouched) and the drop is an event
#[test]
fn a_replay_drop_writes_a_gap_mark() {
    let d = tmp("gap");
    let rec = rec_in(&d, RecordCfg { queue_accounts: 4, queue_journal: 2, ..Default::default() }, &[]);
    let (gate, stopper) = { let g = SendGate::new(); (g.clone(), Stopper::new(g)) };
    rec.bind_session(gate.clone(), stopper);
    let r = rec.recorder().unwrap().clone();
    r.stall(Class::Replay, true);
    std::thread::sleep(Duration::from_millis(20));
    let mut taken = Vec::new();
    for _ in 0..10 {
        let seq = rec.next_seq(ACCOUNTS);
        if rec.emit_seq(ACCOUNTS, seq, acct_rec(seq)) { taken.push(seq); }
    }
    assert_eq!(taken, vec![0, 1, 2, 3], "4 fit, aseq 4..9 are lost");
    r.stall(Class::Replay, false);
    rec.sync();
    let seq = rec.next_seq(ACCOUNTS);
    assert_eq!(seq, 10);
    assert!(rec.emit_seq(ACCOUNTS, seq, acct_rec(seq)));
    rec.sync();
    let recs = acct_records(&decode_zst(&d.join("accounts.000.bin.zst")).unwrap().0);
    let kinds: Vec<u8> = recs.iter().map(|r| r.0).collect();
    assert_eq!(kinds, vec![99, 99, 99, 99, 6, 99], "the GAP comes with the next record, before it");
    let gap = &recs[4].1;
    assert_eq!((u64::from_le_bytes(gap[..8].try_into().unwrap()), u64::from_le_bytes(gap[8..16].try_into().unwrap())), (4, 6), "first lost aseq, n lost");
    assert_eq!(u64::from_le_bytes(recs[5].1[..8].try_into().unwrap()), 10);
    assert_eq!(gate.mode(), GateMode::Live, "a replay drop does not stop trading");
    // the journal's GAP is kind 12 with its seq and t_engine_ns before the body
    r.stall(Class::Replay, true);
    std::thread::sleep(Duration::from_millis(20));
    for _ in 0..4 { let s = rec.next_seq(JOURNAL); rec.emit_seq(JOURNAL, s, Record::Bin(vec![8u8, 0, 0, 0, 0])); }
    r.stall(Class::Replay, false);
    rec.sync();
    let s = rec.next_seq(JOURNAL);
    rec.emit_seq(JOURNAL, s, Record::Bin(vec![8u8, 0, 0, 0, 0]));
    rec.sync();
    let b = decode_zst(&d.join("journal.000.bin.zst")).unwrap().0;
    assert_eq!(&b[..8], b"ARBXJRN\0");
    let hlen = u16::from_le_bytes([b[10], b[11]]) as usize;
    let body = &b[12 + hlen..];
    // two kind-8 records (5 bytes each), then GAP: u8 12 | u32 16 | u64 seq | u64 t | u64 first | u64 n, then the next
    assert_eq!(body[10], 12);
    assert_eq!(u32::from_le_bytes(body[11..15].try_into().unwrap()), 16);
    assert_eq!(u64::from_le_bytes(body[31..39].try_into().unwrap()), 2, "first lost seq");
    assert_eq!(u64::from_le_bytes(body[39..47].try_into().unwrap()), 2, "n lost");
    assert_eq!(body[47], 8);
    let ev = events(&d);
    assert!(ev.iter().any(|e| e["kind"] == "recorder_drop" && e["detail"]["stream"] == "accounts" && e["detail"]["class"] == "replay" && e["detail"]["seq"] == 4));
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
}

/// A scripted filesystem: (bytes used, bytes free) per check
struct Fake(Vec<(u64, u64)>);
impl disk::FsUsage for Fake { fn usage(&mut self, _: &Path) -> (u64, u64) { if self.0.len() > 1 { self.0.remove(0) } else { self.0[0] } } }

/// PLAN WP-02 acceptance: the disk-budget ladder against a fake filesystem (review F5: two stages). Past a soft limit
/// (90% of the budget, the free floor / 0.9) one step per check, in order: entries archives, rivals, accounts keyframes
/// 4x; each an event and in the manifest; a segment that stays under the hard limits runs on. Past a hard limit: shadow
/// and stop with `disk_budget`, at once. Core and chain streams are never switched off
#[test]
fn the_disk_ladder_runs_in_order() {
    use disk::Action::*;
    const G: u64 = 1 << 30;
    let d = tmp("disk");
    let rec = rec_in(&d, RecordCfg { disk_budget_gb: 1.0, min_free_gb: 0.5, archive_feeds: vec!["ent".into()], ..Default::default() }, &["udp0", "ent"]);
    let (gate, stopper) = session(&rec);
    let r = rec.recorder().unwrap().clone();
    let ent = rec.entries(1).expect("ent (feed 1) is archived");
    assert!(rec.entries(0).is_none());
    assert_eq!(rec.accounts_keyframe_every(), 64);
    // under both soft limits; then the run dir at 95% of the budget (soft); then free space under the soft floor; then
    // a long stay over the soft limits (no hard step); then free space under the hard floor
    let soft_used = G * 95 / 100;
    let mut fs = Fake(vec![(G / 2, 10 * G), (soft_used, 10 * G), (soft_used, 10 * G), (G / 10, G / 2 + G / 50), (soft_used, 10 * G), (soft_used, 10 * G),
        (G / 10, G / 10), (G / 10, G / 10)]);
    assert_eq!(r.disk_check(&mut fs), None, "under both limits");
    assert!(rec.emit(ent, Record::Bin(vec![1])) && rec.json(RIVALS, json!({})));
    assert_eq!(r.disk_check(&mut fs), Some(StopEntries));
    assert!(!rec.emit(ent, Record::Bin(vec![2])), "the archive is off");
    assert!(rec.json(RIVALS, json!({})));
    assert_eq!(r.disk_check(&mut fs), Some(StopRivals));
    assert!(!rec.json(RIVALS, json!({})));
    assert_eq!(r.disk_check(&mut fs), Some(KeyframesX4), "free space under the soft floor (0.5 GB / 0.9) is a soft step too");
    assert_eq!(rec.accounts_keyframe_every(), 256);
    assert_eq!((r.disk_check(&mut fs), r.disk_check(&mut fs)), (None, None), "the soft steps are done; under the hard limits the segment runs on");
    assert_eq!(gate.mode(), GateMode::Live);
    assert!(!stopper.stopping());
    // free space under the floor (the run dir is small now): the last step
    assert_eq!(r.disk_check(&mut fs), Some(ShadowAndStop));
    assert!(stopper.stopping());
    assert_eq!(stopper.info().unwrap().reason, crate::control::StopReason::DiskBudget);
    assert_eq!(gate.mode(), GateMode::Stopped, "the stop request closes the gate for good (it was shadow with disk_budget first)");
    assert_eq!(r.disk_check(&mut fs), None, "the ladder is done");
    // never dropped by the budget
    for s in [ATTEMPTS, OUTCOMES, TRIGGERS, EXEC, ACCOUNTS] { assert!(rec.emit(s, Record::Line("{}".into())), "{s:?}"); }
    let st = rec.stats().unwrap();
    assert_eq!(st.suppressed.iter().filter(|x| x.1 > 0).map(|x| x.0.as_str()).collect::<Vec<_>>(), vec!["rivals", "entries-ent"]);
    rec.sync();
    let ev: Vec<Value> = events(&d).into_iter().filter(|e| e["kind"] == "disk_action").collect();
    assert_eq!(ev.iter().map(|e| e["detail"]["action"].as_str().unwrap()).collect::<Vec<_>>(),
        vec!["stop_entries_archive", "stop_rivals", "accounts_keyframe_x4", "shadow_and_stop"]);
    assert_eq!(ev[0]["detail"]["streams_off"], json!(["entries-ent"]));
    assert_eq!((ev[3]["detail"]["used_bytes"].as_u64(), ev[3]["detail"]["fs_free_bytes"].as_u64()), (Some(G / 10), Some(G / 10)));
    assert!(events(&d).iter().any(|e| e["kind"] == "gate_change" && e["detail"]["reason"] == "disk_budget"));
    rec.close();
    let m = manifest(&d);
    assert_eq!(m["disk"]["actions"].as_array().unwrap().len(), 4);
    assert_eq!((m["disk"]["budget_bytes"].as_u64(), m["disk"]["soft_budget_bytes"].as_u64()), (Some(G), Some((G as f64 * 0.9) as u64)));
    let ent_m = mstream(&m, "entries-ent");
    assert_eq!((ent_m["on"].as_bool(), ent_m["suppressed_total"].as_u64(), ent_m["records_total"].as_u64()), (Some(false), Some(1), Some(1)));
    // the archived entries file: ARBXENT format 1, the feed named in its header
    let b = decode_zst(&d.join("entries-ent.000.bin.zst")).unwrap().0;
    assert_eq!(&b[..8], b"ARBXENT\0");
    let hlen = u16::from_le_bytes([b[10], b[11]]) as usize;
    let h: Value = serde_json::from_slice(&b[12..12 + hlen]).unwrap();
    assert_eq!((h["schema"].as_str(), h["feed"].as_str(), h["feed_id"].as_str()), (Some("arbx.entries/1.0"), Some("ent"), Some("1")));
    let _ = std::fs::remove_dir_all(&d);
}

/// a hard limit crossed at once (no soft step before it) stops at once; a run (the monitor on) does not start under the
/// free-space floor (review F5)
#[test]
fn a_hard_limit_stops_at_once_and_a_run_refuses_to_start_under_the_floor() {
    const G: u64 = 1 << 30;
    let d = tmp("hard");
    let rec = rec_in(&d, RecordCfg { disk_budget_gb: 1.0, min_free_gb: 0.5, ..Default::default() }, &[]);
    let (gate, stopper) = session(&rec);
    let r = rec.recorder().unwrap().clone();
    assert_eq!(r.disk_check(&mut Fake(vec![(2 * G, 10 * G)])), Some(disk::Action::ShadowAndStop));
    assert_eq!((gate.mode(), stopper.info().map(|i| i.reason)), (GateMode::Stopped, Some(StopReason::DiskBudget)));
    rec.close();
    let e = start(Opts { dir: d.join("run"), run: "x".into(), producer: "p".into(), cfg: RecordCfg { min_free_gb: 1e9, ..Default::default() }, feeds: vec![],
        monitor: true, echo: Some(Box::new(std::io::sink())) }).err().expect("refused").to_string();
    assert!(e.contains("min_free_gb = 1000000000") && e.contains("not starting"), "{e}");
    let _ = std::fs::remove_dir_all(&d);
}

/// the real filesystem helper: a directory's bytes, and free space
#[test]
fn real_disk_usage() {
    let d = tmp("du");
    std::fs::write(d.join("a"), vec![0u8; 1000]).unwrap();
    std::fs::create_dir_all(d.join("sub")).unwrap();
    std::fs::write(d.join("sub/b"), vec![0u8; 500]).unwrap();
    let (used, free) = disk::FsUsage::usage(&mut disk::RealFs, &d);
    assert_eq!(used, 1500);
    assert!(free > 0 && free < u64::MAX);
    let _ = std::fs::remove_dir_all(&d);
}

/// MEASUREMENT §1.3: text logs start with `# arbx.<stream>/<v> key=value ...` (txarr names its feed columns), plain
/// streams are uncompressed with a JSON header (run.log has none), and a closure record is encoded on the writer
#[test]
fn headers_and_plain_streams() {
    let d = tmp("hdr");
    let rec = rec_in(&d, RecordCfg::default(), &["shredA", "grpcB"]);
    rec.emit(TXARR, Record::enc(|o| o.extend_from_slice(b"0011223344556677 5 100 0 -")));
    rec.emit(MOVES, Record::Line("sig 5 pool 100 acct - vault".into()));
    rec.json(STATUS, json!({ "seq": 0 }));
    rec.say("hello run.log");
    rec.log("send", "a diagnostic line".into());
    rec.event("warmup_ready", "engine", Some(2), json!({ "x": 1 }));
    rec.close();
    let txarr = String::from_utf8(decode_zst(&d.join("txarr.000.log.zst")).unwrap().0).unwrap();
    let first = txarr.lines().next().unwrap();
    assert!(first.starts_with("# arbx.txarr/1.1 run=test-seg file_seq=0 started_ns="), "{first}");
    assert!(first.ends_with("producer=0123456789abcdef feeds=shredA,grpcB"), "{first}");
    assert_eq!(read_text(&d, "txarr").unwrap(), vec!["0011223344556677 5 100 0 -"]);
    assert!(String::from_utf8(decode_zst(&d.join("moves.000.log.zst")).unwrap().0).unwrap().starts_with("# arbx.moves/2.0 "));
    let status = std::fs::read_to_string(d.join("status.jsonl")).unwrap();
    let l: Vec<&str> = status.lines().collect();
    assert_eq!(l.len(), 2);
    assert_eq!(serde_json::from_str::<Value>(l[0]).unwrap()["schema"], "arbx.status/2.0");
    assert_eq!(l[1], r#"{"seq":0}"#);
    let run = std::fs::read_to_string(d.join("run.log")).unwrap();
    assert!(run.lines().next().unwrap().ends_with(" hello run.log"), "{run}");
    assert!(run.split(' ').next().unwrap().parse::<u64>().is_ok(), "`<t_ns> <message>`");
    let ev = events(&d);
    assert_eq!(ev.len(), 2);
    assert_eq!((ev[0]["kind"].as_str(), ev[0]["subsystem"].as_str(), ev[0]["detail"]["msg"].as_str()), (Some("log"), Some("send"), Some("a diagnostic line")));
    assert_eq!((ev[1]["kind"].as_str(), ev[1]["feed"].as_u64()), (Some("warmup_ready"), Some(2)));
    // after close: late records are counted, not written; run.log still takes a line (directly)
    assert!(!rec.json(TRIGGERS, json!({})));
    rec.say("after close");
    assert!(std::fs::read_to_string(d.join("run.log")).unwrap().contains(" after close"));
    let m: Value = serde_json::from_str(&std::fs::read_to_string(d.join("manifest.json")).unwrap()).unwrap();
    let st = m["streams"].as_array().unwrap().iter().find(|s| s["name"] == "status").unwrap();
    assert_eq!((st["files"][0]["path"].as_str(), st["files"][0]["sha256"].as_str()), (Some("status.jsonl"), None), "plain files stay open to appends: no hash");
    // meta.json `streams`
    let s = rec.streams_json();
    assert_eq!((s["attempts"].as_str(), s["status"].as_str(), s["accounts"].as_str()), (Some("arbx.attempts/1.1"), Some("arbx.status/2.0"), Some("arbx.accounts/2.0")));
    let _ = std::fs::remove_dir_all(&d);
}

/// work handed to the slow writer runs there; `Rec::off()` runs it at once
#[test]
fn tasks_run_on_the_slow_writer() {
    let d = tmp("task");
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let (tx, rx) = std::sync::mpsc::channel();
    rec.task(move || { let _ = tx.send(std::thread::current().name().map(String::from)); });
    assert_eq!(rx.recv_timeout(Duration::from_secs(5)).unwrap().as_deref(), Some("arbx-rec-slow"));
    let (tx, rx) = std::sync::mpsc::channel();
    Rec::off().task(move || { let _ = tx.send(1); });
    assert_eq!(rx.try_recv().unwrap(), 1);
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
}

/// the writer threads are niced +5 (they never compete with the engine)
#[test]
fn writer_threads_are_niced() {
    let d = tmp("nice");
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let (tx, rx) = std::sync::mpsc::channel();
    let base = crate::runtime::this_thread_nice();
    rec.task(move || { let _ = tx.send(crate::runtime::this_thread_nice()); });
    assert_eq!(rx.recv_timeout(Duration::from_secs(5)).unwrap(), (base + 5).min(19));
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
}

/// moved from record.rs (PLAN definition of done)
#[test]
fn tx_error_decodes_custom_codes() {
    // InstructionError(3, Custom(0x4e580002))
    let mut b = 8u32.to_le_bytes().to_vec();
    b.push(3);
    b.extend(25u32.to_le_bytes());
    b.extend(0x4e58_0002u32.to_le_bytes());
    assert_eq!(tx_error(&b), "ix3:custom:0x4e580002");
    assert_eq!(tx_error(&6u32.to_le_bytes()), "tx6");
}

/// resources.jsonl: one line from the real process (CPU, RSS, threads, queues, bytes, runtimes) with `_delta` / `_now`
/// names; the /proc parsers on fixed text
#[test]
fn resources_line_and_proc_parsers() {
    let d = tmp("res");
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let r = rec.recorder().unwrap().clone();
    let rt = crate::runtime::Runtimes::new(1).unwrap();
    rec.set_runtimes(rt.hot.handle().clone(), rt.bg.handle().clone());
    rec.set_engine_tid(crate::runtime::gettid());
    rec.json(TRIGGERS, json!({}));
    rec.sync();
    let mut res = health::Resources::new(r.started_ns);
    let a = res.line(&r);
    let b = res.line(&r);
    assert_eq!((a["seq"].as_u64(), b["seq"].as_u64()), (Some(0), Some(1)));
    assert!(a["cpu_user_ms_delta"].is_null() && b["cpu_user_ms_delta"].is_u64(), "a delta needs a previous line");
    assert!(b["engine_cpu_ms_delta"].is_u64());
    assert!(a["rss_bytes_now"].as_u64().unwrap() > 1 << 20 && a["threads_now"].as_u64().unwrap() > 1);
    assert_eq!(a["recorder_queues"]["chain"]["now"].as_u64(), Some(0));
    assert!(a["recorder_bytes_delta"]["triggers"].as_u64().unwrap() > 0 && b["recorder_bytes_delta"].get("triggers").is_none());
    assert!(b["runtimes"]["hot"]["busy_ms_delta"].is_u64() && b["runtimes"]["bg"]["blocking_now"].is_i64());
    let stat = "1234 (arbx worker (x)) S 1 2 3 4 5 6 7 8 9 10 250 50 0 0 20 0 17 0 100 2000 300";
    let p = health::parse_stat(stat).unwrap();
    let tck = unsafe { libc::sysconf(libc::_SC_CLK_TCK) } as u64;
    assert_eq!((p.utime_ms, p.stime_ms, p.threads), (250 * 1000 / tck, 50 * 1000 / tck, 17));
    let udp = "  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode ref pointer drops\n\
               1: 00000000:1F41 00000000:0000 07 00000000:00000000 00:00000000 00000000  1000        0 424242 2 0000000000000000 17\n";
    assert_eq!(health::parse_proc_udp(udp), vec![(8001, 424242, 17)]);
    rt.shutdown(Duration::from_secs(1));
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
}

/// feedhealth.jsonl: per-feed deltas, the state stream as `state`, lead percentiles over the interval, slot lag
#[test]
fn feedhealth_lines() {
    use crate::feeds::FeedCounters;
    use std::sync::atomic::Ordering::Relaxed;
    let st = FeedCounters::named("state", "state-stream");
    let f0 = FeedCounters::named("shredA", "udp");
    f0.shreds.on.store(true, Relaxed);
    f0.udp_watched.store(true, Relaxed);
    let mut lead = crate::lat::Series::new("lead");
    let mut fh = health::FeedHealth::new(0);
    st.seen(100, 1_000);
    f0.seen(99, 2_000);
    f0.packets.store(50, Relaxed);
    f0.first_arrivals.store(7, Relaxed);
    f0.shreds.data.store(40, Relaxed);
    f0.udp_drops.store(3, Relaxed);
    for v in [1_000_000u64, 2_000_000, 3_000_000] { lead.push(v); }
    let l = fh.lines(10_000_000_000, 100, vec![health::FeedRow { id: None, c: &st, lead: None }, health::FeedRow { id: Some(0), c: &f0, lead: Some(&mut lead) }]);
    assert_eq!(l.len(), 2);
    assert_eq!((l[0]["name"].as_str(), l[0]["feed"].is_null(), l[0]["connected_now"].as_bool(), l[0]["slot_lag_now"].as_i64()), (Some("state"), true, Some(true), Some(0)));
    assert!(l[0]["shreds"].is_null() && l[0]["udp_drops_delta"].is_null());
    assert_eq!((l[1]["feed"].as_u64(), l[1]["packets_delta"].as_u64(), l[1]["first_arrivals_delta"].as_u64(), l[1]["slot_lag_now"].as_i64()), (Some(0), Some(50), Some(7), Some(1)));
    assert_eq!(l[1]["lead_ms"], json!({ "window": "interval", "n": 3, "p50": 2.0, "p90": 3.0, "p99": 3.0 }));
    assert_eq!((l[1]["shreds"]["data_delta"].as_u64(), l[1]["udp_drops_delta"].as_u64()), (Some(40), Some(3)));
    assert_eq!((l[0]["seq"].as_u64(), l[1]["seq"].as_u64()), (Some(0), Some(1)));
    f0.packets.store(80, Relaxed);
    let l = fh.lines(20_000_000_000, 100, vec![health::FeedRow { id: None, c: &st, lead: None }, health::FeedRow { id: Some(0), c: &f0, lead: Some(&mut lead) }]);
    assert_eq!((l[1]["packets_delta"].as_u64(), l[1]["first_arrivals_delta"].as_u64(), l[1]["udp_drops_delta"].as_u64()), (Some(30), Some(0), Some(0)));
    assert_eq!((l[1]["interval_ns"].as_u64(), l[1]["lead_ms"]["n"].as_u64()), (Some(10_000_000_000), Some(0)));
}

/// PLAN WP-02 acceptance (ignored: timing): `emit` p99 under 1 µs at 100k records/s, the writer running
#[test]
#[ignore]
fn emit_p99_under_1us_at_100k_per_s() {
    let d = tmp("emit");
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let n = 200_000;
    let mut took = Vec::with_capacity(n);
    let t0 = Instant::now();
    for i in 0..n as u64 {
        // paced at 100k/s
        let due = t0 + Duration::from_nanos(i * 10_000);
        while Instant::now() < due { std::hint::spin_loop(); }
        let t = Instant::now();
        rec.emit(MOVES, Record::enc(move |o| { let _ = std::io::Write::write_fmt(o, format_args!("sig {i} pool 1 acct - vault")); }));
        took.push(t.elapsed().as_nanos() as u64);
    }
    took.sort_unstable();
    let (p50, p99) = (took[n / 2], took[n * 99 / 100]);
    eprintln!("emit p50 {p50} ns, p99 {p99} ns, max {} ns", took[n - 1]);
    rec.close();
    assert_eq!(read_text(&d, "moves").unwrap().len(), n);
    assert!(p99 < 1_000, "emit p99 {p99} ns");
    let _ = std::fs::remove_dir_all(&d);
}

// ------------------------------------------------------------------ faults (review F1, F2, F4, F6, F15, F16, F17)

/// review F1: a core stream whose writes fail (its file is /dev/full: ENOSPC) loses its records. They are counted as
/// I/O losses, never as written; the loss is a core loss (shadow for the rest of the segment) with a `recorder_io_error`
/// event. A chain stream's write errors are counted and leave the gate alone
#[test]
fn write_errors_are_losses_never_records() {
    let d = tmp("ioerr");
    std::os::unix::fs::symlink("/dev/full", d.join("attempts.000.jsonl.zst")).unwrap();
    std::os::unix::fs::symlink("/dev/full", d.join("triggers.000.jsonl.zst")).unwrap();
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let (gate, stopper) = session(&rec);
    for i in 0..10 { assert!(rec.json(TRIGGERS, json!({ "i": i }))); }
    rec.sync();
    assert_eq!(gate.mode(), GateMode::Live, "a chain stream's write errors do not stop sending");
    for i in 0..100 { assert!(rec.json(ATTEMPTS, json!({ "attempt": i })), "emit takes it: the writer finds out"); }
    rec.sync();
    assert_eq!((gate.mode(), gate.reason().as_str(), gate.sticky()), (GateMode::Shadow, "core_record_loss", true));
    assert!(!stopper.stopping(), "a core loss is a shadow, not a stop");
    let st = rec.stats().unwrap();
    assert!(!st.core_ok);
    let get = |v: &[(String, u64)], k: &str| v.iter().find(|x| x.0 == k).unwrap().1;
    assert_eq!((get(&st.io_lost, "attempts"), get(&st.io_lost, "triggers")), (100, 10));
    assert!(get(&st.io_errors, "attempts") >= 1);
    let ev = events(&d);
    assert!(ev.iter().any(|e| e["kind"] == "recorder_io_error" && e["detail"]["stream"] == "attempts" && e["detail"]["op"] == "write"), "{ev:?}");
    assert!(ev.iter().any(|e| e["kind"] == "gate_change" && e["detail"]["reason"] == "core_record_loss"));
    // the files work again: the next frames reach the disk (and only those records count)
    std::fs::remove_file(d.join("triggers.000.jsonl.zst")).unwrap();
    rec.close();
    let m = manifest(&d);
    let a = mstream(&m, "attempts");
    assert_eq!((a["records_total"].as_u64(), a["io_lost_total"].as_u64(), a["dropped_total"].as_u64()), (Some(0), Some(100), Some(0)));
    assert_eq!(a["files"][0]["bytes_written"].as_u64(), Some(0));
    assert!(a["io_errors_total"].as_u64().unwrap() >= 1);
    assert_eq!(m["core_record_loss"], true);
    let _ = std::fs::remove_dir_all(&d);
}

/// review F1: status.jsonl (the supervisor's failed-fee budget source) that cannot be written stops the segment
/// (reason `error`), with a run.log line; `open_now` reports a file that cannot be opened
#[test]
fn a_status_write_error_stops_the_segment() {
    let d = tmp("statusfail");
    std::os::unix::fs::symlink("/dev/full", d.join("status.jsonl")).unwrap();
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let (gate, stopper) = session(&rec);
    // the open works (/dev/full opens); the header's write fails at once
    let _ = rec.open_now(STATUS);
    rec.json(STATUS, json!({ "seq": 0 }));
    rec.sync();
    assert!(stopper.stopping());
    let info = stopper.info().unwrap();
    assert_eq!(info.reason, StopReason::Error);
    assert!(info.detail.contains("status.jsonl not written"), "{}", info.detail);
    assert_eq!(gate.mode(), GateMode::Stopped);
    assert!(!rec.stats().unwrap().core_ok, "health.recorder_ok is false");
    assert!(rec.recorder().unwrap().fatal_reason().is_some());
    rec.close();
    assert!(std::fs::read_to_string(d.join("run.log")).unwrap().contains("recorder: status.jsonl not written"));
    assert!(manifest(&d)["fatal"].as_str().unwrap().contains("status.jsonl"));
    // a status.jsonl that cannot be opened at all (a directory in its place): open_now says so
    let d2 = tmp("statusdir");
    std::fs::create_dir_all(d2.join("status.jsonl")).unwrap();
    let rec = rec_in(&d2, RecordCfg::default(), &[]);
    let (_, stopper) = session(&rec);
    let e = rec.open_now(STATUS).err().expect("not opened").to_string();
    assert!(e.contains("status.jsonl"), "{e}");
    assert!(stopper.stopping(), "and the segment stops");
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
    let _ = std::fs::remove_dir_all(&d2);
}

/// review F1: a file that cannot be opened is tried again (at most once a second); once it opens it starts with its
/// header, and only the records written after that count
#[test]
fn a_file_that_could_not_be_opened_is_tried_again() {
    let d = tmp("reopen");
    std::fs::create_dir_all(d.join("caps.000.jsonl.zst")).unwrap();
    let rec = rec_in(&d, RecordCfg { flush_ms: 20, ..Default::default() }, &[]);
    for i in 0..5 { rec.json(CAPS, json!({ "i": i })); }
    rec.sync();
    std::fs::remove_dir(d.join("caps.000.jsonl.zst")).unwrap();
    std::thread::sleep(Duration::from_millis(1_100));
    for i in 5..8 { rec.json(CAPS, json!({ "i": i })); }
    rec.close();
    let (b, _) = decode_zst(&d.join("caps.000.jsonl.zst")).unwrap();
    let v = lines(&b);
    assert_eq!(v[0]["schema"], "arbx.caps/1.1", "the header comes first");
    assert_eq!(v[1..].iter().map(|x| x["i"].as_u64().unwrap()).collect::<Vec<_>>(), vec![5, 6, 7]);
    let m = manifest(&d);
    let c = mstream(&m, "caps");
    assert_eq!((c["records_total"].as_u64(), c["io_lost_total"].as_u64()), (Some(3), Some(5)));
    let _ = std::fs::remove_dir_all(&d);
}

/// review F2: an encoder (or a task) that panics loses its record only: counted, an event, and the writer goes on; on
/// a core stream it is a core loss
#[test]
fn an_encoder_that_panics_loses_its_record_only() {
    let d = tmp("encpanic");
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let (gate, _) = session(&rec);
    rec.emit(TRIGGERS, Record::enc(|_| panic!("test: a broken encoder")));
    rec.json(TRIGGERS, json!({ "after": 1 }));
    rec.task(|| panic!("test: a broken task"));
    rec.emit(TRIGGERS, Record::stateful::<u32>(|_, o| o.extend_from_slice(b"{}")));
    rec.sync();
    assert_eq!(gate.mode(), GateMode::Live, "chain and slow losses do not stop sending");
    assert_eq!(read_jsonl(&d, "triggers").unwrap(), vec![json!({ "after": 1 })]);
    let st = rec.stats().unwrap();
    let get = |v: &[(String, u64)], k: &str| v.iter().find(|x| x.0 == k).unwrap().1;
    assert_eq!((get(&st.encode_errors, "triggers"), get(&st.encode_errors, "run")), (2, 1), "the panic, and a stateful record with no state");
    assert!(st.writers_dead.is_empty());
    rec.emit(OUTCOMES, Record::enc(|_| panic!("test: a broken core encoder")));
    rec.sync();
    assert_eq!((gate.mode(), gate.reason().as_str()), (GateMode::Shadow, "core_record_loss"));
    assert!(events(&d).iter().any(|e| e["kind"] == "recorder_encode_error" && e["detail"]["stream"] == "triggers"));
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
}

/// review F2: a writer thread that dies is noticed. A chain writer: an event, its records dropped from then on, the
/// gate untouched. The core or the slow writer (status.jsonl's): the segment stops (reason `error`), with a run.log
/// line written directly
#[test]
fn a_dead_writer_is_noticed() {
    let d = tmp("dead");
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let (gate, stopper) = session(&rec);
    let r = rec.recorder().unwrap().clone();
    r.crash_writer(Class::Chain);
    rec.json(TRIGGERS, json!({ "i": 0 }));
    wait_for("the chain writer's death", || rec.stats().unwrap().writers_dead == vec!["chain"]);
    assert!(!rec.json(TRIGGERS, json!({ "i": 1 })), "nobody writes it: dropped");
    assert_eq!(gate.mode(), GateMode::Live);
    assert!(!stopper.stopping());
    rec.sync();
    assert!(events(&d).iter().any(|e| e["kind"] == "recorder_writer_dead" && e["detail"]["class"] == "chain"));
    // the monitor's check finds nothing new (the writer reported itself)
    let mut seen = [(0u64, Instant::now(), false); 5];
    r.check_writers(&mut seen);
    r.crash_writer(Class::Slow);
    rec.say("wakes the slow writer");
    wait_for("the stop", || stopper.stopping());
    assert_eq!(stopper.info().unwrap().reason, StopReason::Error);
    assert!(stopper.info().unwrap().detail.contains("writer arbx-rec-slow stopped"), "{}", stopper.info().unwrap().detail);
    assert!(!rec.json(STATUS, json!({ "seq": 1 })), "status lines are dropped now");
    assert!(std::fs::read_to_string(d.join("run.log")).unwrap().contains("writer arbx-rec-slow stopped"));
    rec.close();
    let m = manifest(&d);
    assert_eq!(m["writers_dead"], json!(["chain", "slow"]));
    assert_eq!(mstream(&m, "triggers")["dropped_total"].as_u64(), Some(1));
    // the core writer: a core loss and a stop
    let d2 = tmp("deadcore");
    let rec = rec_in(&d2, RecordCfg::default(), &[]);
    let (gate, stopper) = session(&rec);
    rec.recorder().unwrap().crash_writer(Class::Core);
    rec.json(ATTEMPTS, json!({ "attempt": 0 }));
    wait_for("the stop", || stopper.stopping());
    assert!(gate.mode() == GateMode::Stopped && !rec.stats().unwrap().core_ok);
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
    let _ = std::fs::remove_dir_all(&d2);
}

/// review F2: the monitor's stall check: a core writer with records queued and no progress for `STALL_LIMIT` stops the
/// segment; a stalled chain writer is an event only
#[test]
fn a_stalled_core_writer_stops_the_segment() {
    let d = tmp("stuck");
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let (gate, stopper) = session(&rec);
    let r = rec.recorder().unwrap().clone();
    r.stall(Class::Chain, true);
    r.stall(Class::Core, true);
    std::thread::sleep(Duration::from_millis(20));
    rec.json(TRIGGERS, json!({}));
    rec.json(ATTEMPTS, json!({}));
    let long_ago = Instant::now() - STALL_LIMIT - Duration::from_secs(1);
    let mut seen = [(0u64, long_ago, false); 5];
    for c in Class::ALL { seen[c as usize].0 = r.progress[c as usize].load(Relaxed); }
    r.check_writers(&mut seen);
    assert_eq!((stopper.info().map(|i| i.reason), gate.mode()), (Some(StopReason::Error), GateMode::Stopped));
    assert!(stopper.info().unwrap().detail.contains("arbx-rec-core made no progress"));
    r.stall(Class::Chain, false);
    r.stall(Class::Core, false);
    rec.sync();
    assert!(events(&d).iter().any(|e| e["kind"] == "recorder_writer_stalled" && e["detail"]["class"] == "chain"));
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
}

/// a sink whose writes fail (stdout on a full disk) or block forever (a pipe nobody reads)
struct BadOut { block: bool }
impl Write for BadOut {
    fn write(&mut self, _: &[u8]) -> std::io::Result<usize> {
        if self.block { loop { std::thread::sleep(Duration::from_secs(3600)); } }
        Err(std::io::Error::from_raw_os_error(libc::ENOSPC))
    }
    fn flush(&mut self) -> std::io::Result<()> { Ok(()) }
}

/// review F2: stdout that fails, or blocks, stops nothing: run.log, status.jsonl and events.jsonl are written, `say`
/// never waits, and the lines the echo could not take are counted
#[test]
fn a_failing_or_blocked_stdout_stops_nothing() {
    for block in [false, true] {
        let d = tmp(if block { "echoblock" } else { "echofail" });
        let rec = rec_echo(&d, RecordCfg::default(), &[], Box::new(BadOut { block }));
        let (gate, stopper) = session(&rec);
        let t0 = Instant::now();
        for i in 0..(ECHO_QUEUE + 500) { rec.say(format!("line {i}")); if i % 1000 == 0 { rec.json(STATUS, json!({ "seq": i })); } }
        rec.log("test", "a diagnostic".into());
        assert!(t0.elapsed() < Duration::from_secs(5), "say never waits for stdout");
        rec.sync();
        assert_eq!(read_text(&d, "run").unwrap().len(), ECHO_QUEUE + 500);
        assert_eq!(read_jsonl(&d, "status").unwrap().len(), 5);
        assert!(events(&d).iter().any(|e| e["kind"] == "log"));
        assert!(rec.stats().unwrap().writers_dead.is_empty());
        if block { assert!(rec.stats().unwrap().echo_dropped > 0, "the echo queue filled: counted"); }
        assert!(gate.mode() == GateMode::Live && !stopper.stopping());
        rec.close();
        let _ = std::fs::remove_dir_all(&d);
    }
}

/// review F4: the plain streams exist from the start, with their headers (events.jsonl's stamped no later than its
/// first event); status.jsonl only once `open_now` asks (the engine's start); a core record reaches the disk at once,
/// whatever `flush_ms`
#[test]
fn plain_files_at_start_and_core_records_at_once() {
    let d = tmp("eager");
    let rec = rec_in(&d, RecordCfg { flush_ms: 600_000, ..Default::default() }, &[]);
    rec.event("warmup_ready", "engine", None, json!({}));
    rec.sync();
    for f in ["events.jsonl", "feedhealth.jsonl", "resources.jsonl", "keepalive.jsonl", "run.log"] { assert!(d.join(f).exists(), "{f}"); }
    assert!(!d.join("status.jsonl").exists(), "status.jsonl waits for the engine");
    let ev = std::fs::read_to_string(d.join("events.jsonl")).unwrap();
    let ev: Vec<Value> = ev.lines().map(|l| serde_json::from_str(l).unwrap()).collect();
    assert_eq!(ev[0]["schema"], "arbx.events/1.0");
    assert!(ev[0]["started_ns"].as_u64().unwrap() <= ev[1]["t_ns"].as_u64().unwrap(), "review N2");
    assert_eq!(std::fs::read_to_string(d.join("feedhealth.jsonl")).unwrap().lines().count(), 1, "the header only");
    rec.open_now(STATUS).unwrap();
    let s = std::fs::read_to_string(d.join("status.jsonl")).unwrap();
    assert_eq!(serde_json::from_str::<Value>(s.lines().next().unwrap()).unwrap()["schema"], "arbx.status/2.0");
    assert_eq!(s.lines().count(), 1);
    rec.json(ATTEMPTS, json!({ "attempt": 7 }));
    let path = d.join("attempts.000.jsonl.zst");
    wait_for("the attempt on disk (no flush for 10 minutes)", || decode_zst(&path).map(|x| lines(&x.0).len() == 2).unwrap_or(false));
    rec.close();
    let _ = std::fs::remove_dir_all(&d);
}

/// review F6: `close` waits a bounded time; a writer that does not finish (stuck in a task) is named in the manifest
#[test]
fn close_is_bounded() {
    let d = tmp("closewait");
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    let r = rec.recorder().unwrap().clone();
    r.set_close_wait(Duration::from_millis(300));
    rec.json(TRIGGERS, json!({ "i": 1 }));
    rec.task(|| std::thread::sleep(Duration::from_secs(5)));
    std::thread::sleep(Duration::from_millis(50));
    let t0 = Instant::now();
    rec.close();
    assert!(t0.elapsed() < Duration::from_secs(3), "{:?}", t0.elapsed());
    let m = manifest(&d);
    assert_eq!(m["close_timeout"], json!(["slow"]));
    assert_eq!(mstream(&m, "triggers")["records_total"].as_u64(), Some(1), "the other writers closed their files");
    assert!(m["queues"]["core"]["lost_at_close"].as_u64() == Some(0));
    let _ = std::fs::remove_dir_all(&d);
}

/// review F16: a stream's per-file state restarts with every file (a dictionary here): each rotated file decodes on
/// its own
#[test]
fn per_file_state_restarts_with_each_file() {
    #[derive(Default)]
    struct Dict { file: Option<u32>, ids: std::collections::HashMap<u64, u32> }
    impl FileState for Dict {
        fn on_new_file(&mut self, file_seq: u32, out: &mut Vec<u8>) { self.file = Some(file_seq); self.ids.clear(); out.extend_from_slice(b"R"); }
        fn as_any(&mut self) -> &mut dyn std::any::Any { self }
    }
    let d = tmp("state");
    let rec = rec_in(&d, RecordCfg { rotate_mb: 0.0005, ..Default::default() }, &[]);
    rec.set_file_state(JOURNAL, Box::new(Dict::default()));
    for i in 0..300u64 {
        let key = i % 3;
        rec.emit(JOURNAL, Record::stateful::<Dict>(move |dict, o| {
            let n = dict.ids.len() as u32;
            match dict.ids.get(&key) {
                Some(id) => o.extend_from_slice(format!("U{id};").as_bytes()),
                None => { dict.ids.insert(key, n); o.extend_from_slice(format!("D{key}={n};").as_bytes()); }
            }
        }));
    }
    rec.close();
    let files = stream_files(&d, "journal");
    assert!(files.len() >= 3, "{} files", files.len());
    for f in &files {
        let b = decode_zst(f).unwrap().0;
        let hlen = u16::from_le_bytes([b[10], b[11]]) as usize;
        let body = std::str::from_utf8(&b[12 + hlen..]).unwrap();
        assert!(body.starts_with('R'), "the state's preamble right after the header: {body}");
        // every id is defined in this file before it is used
        let mut defined = std::collections::HashSet::new();
        for rec in body[1..].split(';').filter(|x| !x.is_empty()) {
            if let Some(def) = rec.strip_prefix('D') { defined.insert(def.split('=').nth(1).unwrap().to_string()); }
            else { assert!(defined.contains(&rec[1..]), "{f:?}: {rec} used before its definition"); }
        }
    }
    let _ = std::fs::remove_dir_all(&d);
}

/// review F17: a queue's byte cap: a stalled replay writer holds at most `queue_max_mb` of declared payload; past it
/// records drop as from a full queue (a GAP follows)
#[test]
fn a_queue_byte_cap_drops_past_it() {
    let d = tmp("bytecap");
    let rec = rec_in(&d, RecordCfg { queue_max_mb: 1_000.0 / MB, ..Default::default() }, &[]);
    let r = rec.recorder().unwrap().clone();
    r.stall(Class::Replay, true);
    std::thread::sleep(Duration::from_millis(20));
    let mut taken = 0;
    for _ in 0..10 {
        let seq = rec.next_seq(ACCOUNTS);
        let mut b = vec![99u8];
        b.extend(295u32.to_le_bytes());
        b.extend(vec![0u8; 295]);
        if rec.emit_seq(ACCOUNTS, seq, Record::Bin(b)) { taken += 1; }
    }
    assert_eq!(taken, 3, "3 x 300 bytes fit in 1,000");
    assert!(rec.emit_sized(RIVALS, 10, Record::Line("{}".into())), "other queues have their own cap");
    r.stall(Class::Replay, false);
    rec.sync();
    assert!(events(&d).iter().any(|e| e["kind"] == "recorder_drop" && e["detail"]["why"] == "queue byte cap"));
    rec.close();
    let m = manifest(&d);
    assert_eq!((m["queues"]["accounts"]["bytes_cap"].as_u64(), m["queues"]["accounts"]["bytes_hwm"].as_u64()), (Some(1_000), Some(900)));
    assert_eq!(mstream(&m, "accounts")["dropped_total"].as_u64(), Some(7));
    let _ = std::fs::remove_dir_all(&d);
}

/// review F11: one record holding several lines counts as that many records
#[test]
fn multi_line_records_count_their_lines() {
    let d = tmp("lines");
    let rec = rec_in(&d, RecordCfg::default(), &[]);
    rec.emit(POH, Record::enc_lines(3, |o| o.extend_from_slice(b"a 1 0.5 0 -\nb 1 0.6 0 -\nc 1 0.7 0 -")));
    rec.close();
    assert_eq!(read_text(&d, "poh").unwrap(), vec!["a 1 0.5 0 -", "b 1 0.6 0 -", "c 1 0.7 0 -"]);
    assert_eq!(mstream(&manifest(&d), "poh")["records_total"].as_u64(), Some(3));
    let _ = std::fs::remove_dir_all(&d);
}

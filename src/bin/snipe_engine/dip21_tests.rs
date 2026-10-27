// ===================================================================================================================
// dip21 tests (10-27 PKT; owner: a restart without the raw recorder must not cost a 60-min warm-up): the QUIET STATE JOURNAL in the
// probe (open_state at the start, the writer thread, the ingest hand-off, close_journal at the run's end, the journal-aware preload
// merge), its flags, and the recorded-chain restarts harness. Declared inside pslive.rs (the probe's state is private to it).
//  * flags: off by default (dip20's config record), the owner's line with the state accepted, the refusals
//  * three sessions on one journal file: A (no file: the warm-up) saves its whale history; B restarts 2 min later: the history is
//    there at once, the arm rule ON at once (A covered 70 min, gap 2 min); C restarts 45 min after B: the history is there but the
//    arm rule warms up (the gap > 30 min)
//  * the preload with a journal: the recording and the journal merged by identity (a dump in both counted once, the journal's own
//    dumps kept), the coverage of both joined, journaling going on after the merge
//  * RECORDED RESTARTS (by hand): the run's real sessions or a simulated restart, each session a fresh probe on the same journal
// ===================================================================================================================
use super::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;
const MIN: u64 = 60 * S;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn all_out(orx: &crossbeam_channel::Receiver<Out>) -> (Vec<serde_json::Value>, Vec<String>) {
    let (mut r, mut l) = (Vec::new(), Vec::new());
    for o in orx.try_iter() { match o { Out::Rec(v) => r.push(v), Out::Line(x) => l.push(x) } }
    (r, l)
}

struct Tk { mint: Pk, v: u64, t: u64, launch: Launch }
impl Tk {
    fn new(k: u8) -> Tk { let mint = [k; 32]; Tk { mint, v: 30 * S, t: 1_073_000_000_000_000, launch: snipe_build::launch_from_target(mint, CREATOR) } }
    fn buy(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v + sol) as u128) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn sell_sol(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v - sol) as u128) as u64;
        self.v -= sol; self.t += q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: false, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn create(&self) -> CreateEvent { CreateEvent { mint: self.mint, bonding_curve: self.launch.bonding_curve, user: CREATOR, creator: CREATOR } }
}

/// one executed tx at a given arrival time (unix ns) through on_arrival + on_exec
#[allow(clippy::too_many_arguments)]
fn txt(p: &mut PsLive, slot: u64, idx: u64, t_rx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>, launches: &[&Launch]) {
    let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0xD3;
    let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
    let a = arbx::feeds::Arrival { feed: 0, slot, t_rx, t_decoded: t_rx, executed: Some(true), tx: arbx::tx::Tx { sig, keys: vec![[0x77; 32]], ..Default::default() },
        poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
    let ls: Vec<Launch> = launches.iter().map(|l| (*l).clone()).collect();
    p.on_arrival(&a, slot);
    p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
}

/// a probe with the arm rule and the journal at `path`, started at `start_ns` (60-min warm-up), its journal opened and its writer
/// running: (probe, its records)
fn session(path: &str, start_ns: u64, extra: &[&str]) -> (PsLive, crossbeam_channel::Receiver<Out>, String) {
    let mut a = vec!["--presend-live-quiet-state", path];
    a.extend_from_slice(extra);
    session_with(start_ns, &a)
}

/// a probe with the arm rule started at `start_ns` (60-min warm-up), its history opened as the engine's start does (the book and / or
/// the journal named in `extra`; the journal's writer running when it is on): (probe, its records, the start line)
fn session_with(start_ns: u64, extra: &[&str]) -> (PsLive, crossbeam_channel::Receiver<Out>, String) {
    let mut a = vec!["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/unused.json"];
    a.extend_from_slice(extra);
    let (mut p, _atx, orx) = PsLive::for_test(cfg(&a).unwrap().unwrap(), USER);
    let line = {
        let q = p.qt.as_mut().unwrap();
        q.start_ns = start_ns;
        q.warm_ns = 60 * MIN;
        let (line, rec, compacted) = q.open_state(start_ns).expect("the state / book flag is on");
        if let Some(c) = compacted { assert!(q.spawn_journal(c).is_none()); }
        p.rec(rec);
        line
    };
    (p, orx, line)
}

/// the whale's market: from `from` to `to`, a filler trade every 10 slots (the slot clock), a dump by `whale` every 2000 slots on its
/// own token, 3 distinct buyers in the next slot. -> dumps
fn whale_market(p: &mut PsLive, from: u64, to: u64, t_of: &dyn Fn(u64) -> u64, whale: Pk, k0: u8) -> u64 {
    let mut n = 0u64;
    let mut filler = Tk::new(250);
    for s in (from..to).step_by(10) {
        let e = filler.buy([0x50; 32], 1_000_000);
        txt(p, s, 900, t_of(s), vec![e], vec![], &[]);
        if (s - from) % 2000 == 0 {
            let mut t = Tk::new(k0.wrapping_add(n as u8));
            let _ = t.buy(whale, 3 * S);
            let d = t.sell_sol(whale, 4 * S);
            txt(p, s + 1, 5, t_of(s + 1), vec![d], vec![], &[]);
            for (q, u) in [0x41u8, 0x42, 0x43].iter().enumerate() { let e = t.buy([*u; 32], S / 10); txt(p, s + 2, 5 + q as u64, t_of(s + 2), vec![e], vec![], &[]); }
            n += 1;
        }
    }
    n
}

/// a new token with its dev buy at `s0`, a buy by another wallet at s0 + 2, the whale's 2 SOL buy (the trigger) at `s_trig`
fn trigger_at(p: &mut PsLive, k: u8, s0: u64, s_trig: u64, whale: Pk, t_of: &dyn Fn(u64) -> u64) -> Pk {
    let mut tk = Tk::new(k);
    let dev = tk.buy(CREATOR, S / 2);
    txt(p, s0, 3, t_of(s0), vec![dev], vec![tk.create()], &[&tk.launch]);
    let e = tk.buy([0x33; 32], S / 10);
    txt(p, s0 + 2, 10, t_of(s0 + 2), vec![e], vec![], &[&tk.launch]);
    let e = tk.buy(whale, 2 * S);
    txt(p, s_trig, 50, t_of(s_trig), vec![e], vec![], &[&tk.launch]);
    tk.mint
}

#[test]
fn dip21_state_flags() {
    // off by default: dip20's config record (no state key)
    let c = cfg(&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x.json"]).unwrap().unwrap();
    assert!(c.quiet.state.is_none() && c.quiet.state_max_gap_min == 30.0);
    assert!(c.json()["quiet"].get("state").is_none() && c.json()["quiet"].get("state_max_gap_min").is_none());
    // the owner's line with the journal
    let owner = ["--presend-live-quiet-stop", "6:2", "--presend-live-quiet-skip", "on", "--presend-live-quiet-hist-h", "24", "--presend-live-quiet-fol", "2.24",
        "--presend-live-quiet-warmup-min", "60", "--presend-live-fbots", "/root/dip/fbots_frozen.json", "--presend-live-quiet-state", "/root/dip/quiet_state_ams.jsonl"];
    let c = cfg(&owner).unwrap().unwrap();
    assert_eq!((c.quiet.state.as_deref(), c.quiet.state_max_gap_min), (Some("/root/dip/quiet_state_ams.jsonl"), 30.0));
    assert_eq!(c.json()["quiet"]["state"], "/root/dip/quiet_state_ams.jsonl");
    assert!(check_flags(&args(&owner)).is_ok(), "{:?}", check_flags(&args(&owner)));
    let mut with_gap = owner.to_vec(); with_gap.extend(["--presend-live-quiet-state-max-gap-min", "15"]);
    assert_eq!(cfg(&with_gap).unwrap().unwrap().quiet.state_max_gap_min, 15.0);
    assert!(check_flags(&args(&with_gap)).is_ok());
    // refusals: the journal needs the arm rule; the gap needs the journal; ranges; a missing path; a number check at the start
    for (bad, why) in [(&["--presend-live-quiet-state", "/x"][..], "needs --presend-live-quiet-skip on"),
                       (&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-state-max-gap-min", "5"], "needs --presend-live-quiet-state"),
                       (&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-state", "/s", "--presend-live-quiet-state-max-gap-min", "1441"], "0..1440"),
                       (&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-state", "--presend-live-k"], "needs a path")] {
        let e = cfg(bad).unwrap_err().to_string();
        assert!(e.contains(why), "{bad:?}: {e}");
    }
    assert!(check_flags(&args(&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-state", "/s", "--presend-live-quiet-state-max-gap-min", "x"])).is_err());
    let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", "--presend-live-quiet-state", "/s"].iter().map(|s| s.to_string()).collect::<Vec<_>>(),
        &arbx::presend::Params::default(), true, 1_000_000_000).unwrap_err().to_string();
    assert!(e.contains("needs --presend-live"), "{e}");
}

/// THREE SESSIONS ON ONE JOURNAL (no recorder): A starts without a file (the warm-up), the whale dumps 10 times (3 buyers each) over
/// 70 min, A ends (the stop marker). B restarts 2 min later: the 10 dumps are history at once, the arm rule ON at once (70 min
/// continuous, gap 2 min): a fresh whale's quiet trigger is skipped right away, the dumping whale's trigger arms (3.0 >= 2.24). C
/// restarts 45 min after B: the history is still there, but the arm rule warms up (the gap > 30 min)
#[test]
fn dip21_three_sessions_restart_without_recorder() {
    let dir = std::env::temp_dir().join(format!("dip21_sess_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("quiet_state_test.jsonl").display().to_string();
    let t0 = 1_793_000_000 * S;
    let t_of = |s: u64| t0 + (s - 1_000) * 212_000_000;
    let whale = [0x15u8; 32];
    // ---- A
    let (mut a, orx_a, line_a) = session(&path, t_of(1_000) - S, &[]);
    assert!(line_a.contains("merged 0 dumps") && line_a.contains("no file yet") && line_a.contains("warming up until"), "{line_a}");
    let n = whale_market(&mut a, 1_000, 21_000, &t_of, whale, 100);
    assert_eq!(n, 10);
    let want = a.qt.as_ref().unwrap().book.as_ref().unwrap().whale(&whale, 30_000, t_of(30_000));
    assert_eq!(want, (3.0, 10));
    let end_a = a.finish(21_000, None);
    let st = &end_a["quiet"]["state"]["end"];
    assert!(st["dumps"].as_u64().unwrap() >= 10 && st["writer_done"] == true && st["errors"] == 0, "{st}");
    let (_, lines) = all_out(&orx_a);
    assert!(lines.iter().any(|l| l.starts_with("  QUIET state:") && l.contains("dumps saved this run")), "{lines:?}");
    let l = arbx::presend_quiet::load_state(std::path::Path::new(&path), t_of(21_000), 24 * 60 * MIN);
    assert_eq!((l.sessions.len(), l.bad, l.truncated_tail), (1, 0, false));
    let a_end_t = l.sessions[0].t1;
    // ---- B: 2 min after A's end
    let b_start = a_end_t + 2 * MIN;
    let b_slot = 21_000 + (2 * MIN / 212_000_000) + 1;
    let (mut b, orx_b, line_b) = session(&path, b_start, &[]);
    assert!(line_b.contains("merged 10 dumps / 1 sellers") && line_b.contains("arm rule ON now") && line_b.contains("gap 2.0 min"), "{line_b}");
    {
        let q = b.qt.as_ref().unwrap();
        assert!(q.arm_on(b_start), "on at once");
        assert_eq!(q.book.as_ref().unwrap().whale(&whale, 30_000, t_of(30_000)), want, "the loaded history = A's");
        assert!((q.covered_ns as f64 / MIN as f64 - 70.6).abs() < 0.5, "{}", q.covered_ns as f64 / MIN as f64);
    }
    let fresh = trigger_at(&mut b, 1, b_slot, b_slot + 5, [0x16; 32], &t_of);
    let w_tok = trigger_at(&mut b, 2, b_slot + 10, b_slot + 15, whale, &t_of);
    let (rb, _) = all_out(&orx_b);
    let sk = rb.iter().find(|r| r["ev"] == "presend_live_skip" && r["trig"]["mint"] == b58(&fresh)).expect("the fresh whale's trigger skipped");
    assert_eq!((sk["why"].as_str(), sk["quiet"]["rule_on"].as_bool()), (Some("quiet"), Some(true)));
    let ar = rb.iter().find(|r| r["ev"] == "presend_live_arm" && r["trig"]["mint"] == b58(&w_tok)).expect("the dumping whale's trigger armed");
    assert_eq!((ar["quiet"]["wh_fol"].as_f64(), ar["quiet"]["wh_dumps"].as_u64()), (Some(3.0), Some(10)));
    let st = rb.iter().find(|r| r["ev"] == "presend_live_quiet_state").unwrap();
    assert_eq!((st["dumps"].as_u64(), st["arm_on"].as_bool(), st["sessions"].as_u64()), (Some(10), Some(true), Some(1)));
    let b_end = b.finish(b_slot + 100, None);
    assert_eq!(b_end["quiet"]["state"]["end"]["compacted"], true);
    let l = arbx::presend_quiet::load_state(std::path::Path::new(&path), t_of(b_slot + 100), 24 * 60 * MIN);
    assert_eq!(l.sessions.len(), 2);
    let b_end_t = l.sessions[1].t1;
    // ---- C: 45 min after B's end: the history kept, the arm rule warms up
    let c_start = b_end_t + 45 * MIN;
    let c_slot = b_slot + 100 + 45 * MIN / 212_000_000;
    let (mut c, orx_c, line_c) = session(&path, c_start, &[]);
    assert!(line_c.contains("merged 10 dumps") && line_c.contains("warming up until") && line_c.contains("gap 45.0 min"), "{line_c}");
    let fresh2 = trigger_at(&mut c, 3, c_slot, c_slot + 5, [0x17; 32], &t_of);
    let w_tok2 = trigger_at(&mut c, 4, c_slot + 10, c_slot + 15, whale, &t_of);
    let (rc, _) = all_out(&orx_c);
    let ar = rc.iter().find(|r| r["ev"] == "presend_live_arm" && r["trig"]["mint"] == b58(&fresh2)).expect("armed during the warm-up");
    assert_eq!((ar["quiet"]["rule_on"].as_bool(), ar["quiet"]["would_skip"].as_bool()), (Some(false), Some(true)));
    let ar = rc.iter().find(|r| r["ev"] == "presend_live_arm" && r["trig"]["mint"] == b58(&w_tok2)).unwrap();
    assert_eq!(ar["quiet"]["wh_dumps"].as_u64(), Some(10), "the loaded history is used during the warm-up too");
    assert!(c.status().contains("| state: loaded 10 saved"), "{}", c.status());
    let _ = c.finish(c_slot + 100, None);
    let _ = std::fs::remove_dir_all(&dir);
}

/// a gzip chunk of collector lines (s, i, bt, err null, ev = the trade events' base64)
fn chunk(path: &std::path::Path, txs: &[(u64, u32, i64, Vec<TradeEvent>)]) {
    use base64::Engine as _;
    use std::io::Write;
    let mut text = String::new();
    for (s, i, bt, ev) in txs {
        let evs: Vec<String> = ev.iter().map(|e| {
            let mut r = vec![0u8; 225];
            r[..8].copy_from_slice(&arbx::dip::TRADE_EVENT_DISC);
            r[8..40].copy_from_slice(&e.mint); r[40..48].copy_from_slice(&e.sol.to_le_bytes()); r[48..56].copy_from_slice(&e.tok.to_le_bytes());
            r[56] = e.buy as u8; r[57..89].copy_from_slice(&e.user); r[97..105].copy_from_slice(&e.vsol.to_le_bytes()); r[105..113].copy_from_slice(&e.vtok.to_le_bytes());
            base64::engine::general_purpose::STANDARD.encode(&r)
        }).collect();
        text.push_str(&format!("{{\"s\":{s},\"i\":{i},\"bt\":{bt},\"sig\":\"x\",\"err\":null,\"ev\":{}}}\n", serde_json::to_string(&evs).unwrap()));
    }
    let mut ch = std::process::Command::new("gzip").arg("-c").stdin(std::process::Stdio::piped()).stdout(std::process::Stdio::piped()).spawn().unwrap();
    ch.stdin.take().unwrap().write_all(text.as_bytes()).unwrap();
    std::fs::write(path, ch.wait_with_output().unwrap().stdout).unwrap();
}

/// THE PRELOAD WITH A JOURNAL: a 2-hour recording (whale W: a dump every 20 slots, 3 buyers each) and a journal from an earlier session
/// (whale W2's 5 dumps the recording does not have, and 3 of W's that it has, same identities): merged in the preload thread, each
/// dump once (W 18 dumps at 3.0, W2 5 at 1.0); the journal alone was too old (gap > 30 min: the warm-up), with the recording's span
/// the history is continuous to the start: the arm rule ON when merged; this session's dumps are journaled after the merge
#[test]
fn dip21_preload_merged_with_journal() { preload_with_history("--presend-live-quiet-state") }

/// THE PRELOAD WITH THE HOST'S BOOK (FRA: the book, the recorder on the node): the same history given as the book: merged with the
/// recording in the preload thread by identity, the same counts; the book is only read (the file unchanged, nothing written)
#[test]
fn dip21_preload_merged_with_book() { preload_with_history("--presend-live-quiet-book") }

fn preload_with_history(flag: &str) {
    let book = flag == "--presend-live-quiet-book";
    let dir = std::env::temp_dir().join(format!("dip21_pre_{}_{}", std::process::id(), book as u8));
    let _ = std::fs::remove_dir_all(&dir);
    let run = dir.join("run_20261027_0000");
    std::fs::create_dir_all(run.join("txs")).unwrap();
    std::fs::write(dir.join("current_run"), "run_20261027_0000\n").unwrap();
    let now_s = (arbx::feeds::clock::now_ns() / S) as i64;
    let (w, w2, w3) = ([0x15u8; 32], [0x25u8; 32], [0x35u8; 32]);
    let bt = |s: u64| now_s - 7_200 + (s as i64 - 1_000) * 18;
    let mut all: Vec<(u64, u32, i64, Vec<TradeEvent>)> = Vec::new();
    let mut k = 0u8;
    for s in (1_000u64..1_400).step_by(20) {
        k = k.wrapping_add(1);
        let mut t = Tk::new(100u8.wrapping_add(k));
        let _ = t.buy(w, 3 * S);
        all.push((s, 1, bt(s), vec![t.sell_sol(w, 4 * S)]));
        for (n, u) in [0x41u8, 0x42, 0x43].iter().enumerate() { let e = t.buy([*u; 32], S / 10); all.push((s + 1, 1 + n as u32, bt(s + 1), vec![e])); }
    }
    let mut filler = Tk::new(200);
    for s in 1_000u64..1_400 { let e = filler.buy([0x50; 32], 1_000_000); all.push((s, 900, bt(s), vec![e])); }
    all.sort_by_key(|x| (x.0, x.1));
    for (c, part) in all.chunks(150).enumerate() { chunk(&run.join(format!("txs/txs_{}.jsonl.gz", now_s - 7_300 + 300 * c as i64)), part); }
    // the journal of an earlier session: 4 h .. 1.95 h ago
    let jpath = dir.join("state.jsonl");
    let ns = |x: i64| x as u64 * S;
    let mut recs = vec![arbx::presend_quiet::JRec::Start { t: ns(now_s - 4 * 3600), s: 500 }];
    for q in 0..5u64 { recs.push(arbx::presend_quiet::JRec::Dump(arbx::presend_quiet::JDump { s: 600 + q, i: 7, j: 0, t: ns(now_s - 3 * 3600) + q * S, seller: w2, nf: 1 })); }
    for s in [1_000u64, 1_020, 1_040] { recs.push(arbx::presend_quiet::JRec::Dump(arbx::presend_quiet::JDump { s, i: 1, j: 0, t: ns(bt(s)) + S / 2, seller: w, nf: 3 })); }
    recs.push(arbx::presend_quiet::JRec::Stop { t: ns(now_s - 7_020), s: 1_050 });
    std::fs::write(&jpath, recs.iter().map(|r| arbx::presend_quiet::encode(r) + "\n").collect::<String>()).unwrap();
    // the session: journal + preload
    let pre = dir.join("current_run").display().to_string();
    let before = std::fs::read(&jpath).unwrap();
    let (mut p, orx, line) = session_with(arbx::feeds::clock::now_ns(), &[flag, &jpath.display().to_string(), "--presend-live-quiet-preload", &pre]);
    assert!(line.contains("merged 8 dumps / 2 sellers") && line.contains("warming up"), "the history alone is too old: {line}");
    assert!(line.contains(if book { "| book " } else { "| journal " }) || line.contains(if book { ": book " } else { ": journal " }), "{line}");
    // the live feed starts at slot 1350 (the cut 1351), then the preload thread
    let mut live = Tk::new(201);
    let e = live.buy([0x51; 32], 1_000_000);
    txt(&mut p, 1_350, 5, arbx::feeds::clock::now_ns(), vec![e], vec![], &[]);
    p.qt.as_mut().unwrap().spawn_preload(Duration::from_secs(60));
    let t0 = Instant::now();
    while p.qt.as_ref().unwrap().pre == PreSt::Running && t0.elapsed() < Duration::from_secs(60) {
        std::thread::sleep(Duration::from_millis(20));
        let e = live.buy([0x51; 32], 1_000_000);
        txt(&mut p, 1_351, 6, arbx::feeds::clock::now_ns(), vec![e], vec![], &[]);
    }
    {
        let q = p.qt.as_ref().unwrap();
        assert_eq!(q.pre, PreSt::Done, "{}", q.pre_info);
        assert_eq!((q.pre_info["journal_added"].as_u64(), q.pre_info["journal_dup"].as_u64()), (Some(5), Some(3)));
        let b = q.book.as_ref().unwrap();
        let now = arbx::feeds::clock::now_ns();
        assert_eq!(b.whale(&w, 1_400, now), (3.0, 18), "the recording's 18 (slots 1000..1340), the journal's 3 copies not counted again");
        assert_eq!(b.whale(&w2, 1_400, now), (1.0, 5), "the journal's own dumps kept");
        assert!(q.arm_on(now), "the journal's session and the recording's span joined: continuous to the cut");
        assert!(q.covered_ns > 3 * 60 * MIN, "{} min", q.covered_ns / MIN);
    }
    // a dump in this session after the merge is journaled
    let mut t3 = Tk::new(202);
    let _ = t3.buy(w3, 3 * S);
    let d = t3.sell_sol(w3, 4 * S);
    let tn = arbx::feeds::clock::now_ns();
    txt(&mut p, 1_360, 1, tn, vec![d], vec![], &[]);
    for (q, u) in [0x61u8, 0x62].iter().enumerate() { let e = t3.buy([*u; 32], S / 10); txt(&mut p, 1_361, 2 + q as u64, tn + 1, vec![e], vec![], &[]); }
    let e = live.buy([0x51; 32], 1_000_000);
    txt(&mut p, 1_370, 1, tn + 2, vec![e], vec![], &[]);
    let _ = p.finish(1_371, None);
    let (r, _) = all_out(&orx);
    assert!(r.iter().any(|x| x["ev"] == "presend_live_quiet_preload" && x["ok"] == true));
    if book {
        assert_eq!(std::fs::read(&jpath).unwrap(), before, "the book is only read");
        let files: Vec<String> = std::fs::read_dir(&dir).unwrap().filter_map(|x| x.ok()).map(|x| x.file_name().to_string_lossy().to_string()).collect();
        assert_eq!(files.len(), 3, "nothing written next to it: {files:?}");
    } else {
        let l = arbx::presend_quiet::load_state(&jpath, arbx::feeds::clock::now_ns(), 24 * 60 * MIN);
        assert!(l.dumps.iter().any(|(d, _)| d.seller == w3 && d.nf == 2), "this session's dump journaled after the merge");
        assert_eq!(l.sessions.len(), 2);
    }
    let _ = std::fs::remove_dir_all(&dir);
}

// ---- the host's book (--presend-live-quiet-book) -------------------------------------------------------------------------------

/// a history file as the builder / the journal writes it: per session (first slot, last slot) its start and stop markers, the dumps
/// (slot, tx index, seller, followers) at their slots' times (`t_of`)
fn hist_file(path: &std::path::Path, sessions: &[(u64, u64)], dumps: &[(u64, u32, Pk, u32)], t_of: &dyn Fn(u64) -> u64) {
    use arbx::presend_quiet::{encode, JDump, JRec};
    let mut recs = Vec::new();
    for (a, b) in sessions {
        recs.push(JRec::Start { t: t_of(*a), s: *a });
        for (s, i, w, n) in dumps.iter().filter(|d| *a <= d.0 && d.0 <= *b) { recs.push(JRec::Dump(JDump { s: *s, i: *i, j: 0, t: t_of(*s), seller: *w, nf: *n })); }
        recs.push(JRec::Stop { t: t_of(*b), s: *b });
    }
    std::fs::write(path, recs.iter().map(|r| encode(r) + "\n").collect::<String>()).unwrap();
}

#[test]
fn dip21_book_flags() {
    // off by default (dip20's record: no book key)
    let c = cfg(&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x.json"]).unwrap().unwrap();
    assert!(c.quiet.book.is_none() && c.json()["quiet"].get("book").is_none());
    // the run script's line: the book and the journal
    let owner = ["--presend-live-quiet-stop", "6:2", "--presend-live-quiet-skip", "on", "--presend-live-quiet-hist-h", "24", "--presend-live-quiet-fol", "2.24",
        "--presend-live-quiet-warmup-min", "60", "--presend-live-fbots", "/root/dip/fbots_frozen.json", "--presend-live-quiet-state", "/root/dip/quiet_state_ams.jsonl",
        "--presend-live-quiet-book", "/root/dip/quiet_book.jsonl"];
    let c = cfg(&owner).unwrap().unwrap();
    assert_eq!((c.quiet.book.as_deref(), c.quiet.state.as_deref()), (Some("/root/dip/quiet_book.jsonl"), Some("/root/dip/quiet_state_ams.jsonl")));
    assert_eq!((c.json()["quiet"]["book"].as_str(), c.json()["quiet"]["state_max_gap_min"].as_f64()), (Some("/root/dip/quiet_book.jsonl"), Some(30.0)));
    assert!(check_flags(&args(&owner)).is_ok(), "{:?}", check_flags(&args(&owner)));
    // the book alone (no journal), with its own max gap
    let only = ["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-book", "/b", "--presend-live-quiet-state-max-gap-min", "20"];
    let c = cfg(&only).unwrap().unwrap();
    assert_eq!((c.quiet.book.as_deref(), c.quiet.state.as_deref(), c.quiet.state_max_gap_min), (Some("/b"), None, 20.0));
    assert!(check_flags(&args(&only)).is_ok());
    for (bad, why) in [(&["--presend-live-quiet-book", "/b"][..], "needs --presend-live-quiet-skip on"),
                       (&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-book", "--presend-live-k"], "needs a path"),
                       (&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-state-max-gap-min", "5"], "--presend-live-quiet-book FILE")] {
        let e = cfg(bad).unwrap_err().to_string();
        assert!(e.contains(why), "{bad:?}: {e}");
    }
}

/// THE BOOK FROM THE BUILDER (the host's quiet_book, the same code: arbx::presend_quiet::build_book + write_book) over a 70-min recording
/// (whale W: 10 dumps, 3 buyers each), given to a fresh engine (no journal, no recorder: AMS). Fresh (2 min old): the history is there
/// at once and the arm rule ON at once (source: book): a fresh whale's quiet trigger skipped, W's trigger armed (3.0 over 10 dumps);
/// the book only read (unchanged, nothing written). Stale (45 min old): the same history, the arm rule warms up
#[test]
fn dip21_book_from_the_builder_fresh_and_stale() {
    let dir = std::env::temp_dir().join(format!("dip21_book_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    let run = dir.join("rec").join("run_20261027_0000");
    std::fs::create_dir_all(run.join("txs")).unwrap();
    let t0 = 1_793_000_000 * S;
    let t_of = |s: u64| t0 + (s - 1_000) * 212_000_000;
    let bt = |s: u64| (t_of(s) / S) as i64;
    let whale = [0x15u8; 32];
    // the recording: a filler trade every 10 slots, W's dump every 2000 slots with 3 buyers in the next slot
    let mut txs: Vec<(u64, u32, i64, Vec<TradeEvent>)> = Vec::new();
    let mut filler = Tk::new(250);
    let mut n = 0u8;
    for s in (1_000u64..21_000).step_by(10) {
        txs.push((s, 900, bt(s), vec![filler.buy([0x50; 32], 1_000_000)]));
        if (s - 1_000) % 2_000 == 0 {
            let mut t = Tk::new(100 + n);
            n += 1;
            let _ = t.buy(whale, 3 * S);
            txs.push((s + 1, 5, bt(s + 1), vec![t.sell_sol(whale, 4 * S)]));
            for (q, u) in [0x41u8, 0x42, 0x43].iter().enumerate() { let e = t.buy([*u; 32], S / 10); txs.push((s + 2, 5 + q as u32, bt(s + 2), vec![e])); }
        }
    }
    txs.sort_by_key(|x| (x.0, x.1));
    let mut by: std::collections::BTreeMap<i64, Vec<(u64, u32, i64, Vec<TradeEvent>)>> = Default::default();
    for x in txs { by.entry((x.2 - bt(1_000)) / 300).or_default().push(x); }
    for (c, part) in &by { chunk(&run.join(format!("txs/txs_{}.jsonl.gz", bt(1_000) + 300 * c)), part); }
    // the host's pass
    let runs = arbx::presend_quiet::run_dirs(&dir.join("rec")).unwrap();
    let pass = arbx::presend_quiet::build_book(&runs, None, t_of(21_000), None, 24 * 60 * MIN).unwrap();
    assert_eq!((pass.book.dumps.len(), pass.book.sessions.len(), pass.active_runs), (10, 1, 1));
    let book = dir.join("quiet_book.jsonl");
    arbx::presend_quiet::write_book(&book, &pass.book).unwrap();
    let bytes = std::fs::read(&book).unwrap();
    let end = pass.book.sessions[0].t1;
    let bp = book.display().to_string();
    // ---- fresh: 2 min after the book's end
    let start = end + 2 * MIN;
    let b_slot = 21_000 + 2 * MIN / 212_000_000 + 1;
    let (mut b, orx, line) = session_with(start, &["--presend-live-quiet-book", &bp]);
    eprintln!("fresh book:{line}");
    assert!(line.contains(&format!("book {bp}: 10 dumps, 1 session(s), continuous 1.18 h")) && line.contains("gap 2.0 min") && line.contains("arm rule ON now (source: book)"), "{line}");
    assert!(!line.contains("journal"), "{line}");
    {
        let q = b.qt.as_ref().unwrap();
        assert!(q.arm_on(start));
        assert_eq!(q.book.as_ref().unwrap().whale(&whale, 30_000, t_of(30_000)), (3.0, 10));
    }
    let fresh = trigger_at(&mut b, 1, b_slot, b_slot + 5, [0x16; 32], &t_of);
    let w_tok = trigger_at(&mut b, 2, b_slot + 10, b_slot + 15, whale, &t_of);
    let (r, _) = all_out(&orx);
    let sk = r.iter().find(|x| x["ev"] == "presend_live_skip" && x["trig"]["mint"] == b58(&fresh)).expect("the fresh whale's trigger skipped at once");
    assert_eq!((sk["why"].as_str(), sk["quiet"]["rule_on"].as_bool()), (Some("quiet"), Some(true)));
    let ar = r.iter().find(|x| x["ev"] == "presend_live_arm" && x["trig"]["mint"] == b58(&w_tok)).expect("W's trigger armed");
    assert_eq!((ar["quiet"]["wh_fol"].as_f64(), ar["quiet"]["wh_dumps"].as_u64()), (Some(3.0), Some(10)));
    let st = r.iter().find(|x| x["ev"] == "presend_live_quiet_state").unwrap();
    assert_eq!((st["source"].as_str(), st["arm_on"].as_bool(), st["book"]["dumps"].as_u64(), st["journal"].is_null()), (Some("book"), Some(true), Some(10), true));
    assert!(st["load_ms"].as_f64().unwrap() < 1_000.0);
    // a dump in this session (W again): in the live book, never written anywhere
    let mut t = Tk::new(90);
    let _ = t.buy(whale, 3 * S);
    let d = t.sell_sol(whale, 4 * S);
    txt(&mut b, b_slot + 20, 1, t_of(b_slot + 20), vec![d], vec![], &[]);
    let e = filler.buy([0x50; 32], 1_000_000);
    txt(&mut b, b_slot + 30, 1, t_of(b_slot + 30), vec![e], vec![], &[]);
    b.tick(b_slot + 30, None);
    assert_eq!(b.qt.as_ref().unwrap().book.as_ref().unwrap().whale(&whale, b_slot + 40, t_of(b_slot + 40)), (30.0 / 11.0, 11));
    let end_rec = b.finish(b_slot + 40, None);
    assert!(end_rec["quiet"]["state"]["end"].is_null() || end_rec["quiet"]["state"]["end"]["dumps"].as_u64().unwrap_or(0) == 0, "{}", end_rec["quiet"]["state"]);
    assert!(b.status().contains("history: book loaded 10"), "{}", b.status());
    assert_eq!(std::fs::read(&book).unwrap(), bytes, "the book is only read");
    let files: Vec<String> = std::fs::read_dir(&dir).unwrap().filter_map(|x| x.ok()).map(|x| x.file_name().to_string_lossy().to_string()).collect();
    assert_eq!(files.len(), 2, "nothing written next to it: {files:?}");
    // ---- stale: 45 min after the book's end: the history kept, the arm rule warms up
    let start = end + 45 * MIN;
    let c_slot = 21_000 + 45 * MIN / 212_000_000 + 1;
    let (mut c, orx, line) = session_with(start, &["--presend-live-quiet-book", &bp]);
    eprintln!("stale book:{line}");
    assert!(line.contains("10 dumps") && line.contains("gap 45.0 min") && line.contains("TOO OLD") && line.contains("warming up until"), "{line}");
    let fresh2 = trigger_at(&mut c, 3, c_slot, c_slot + 5, [0x17; 32], &t_of);
    let w_tok2 = trigger_at(&mut c, 4, c_slot + 10, c_slot + 15, whale, &t_of);
    let (r, _) = all_out(&orx);
    let ar = r.iter().find(|x| x["ev"] == "presend_live_arm" && x["trig"]["mint"] == b58(&fresh2)).expect("armed during the warm-up");
    assert_eq!((ar["quiet"]["rule_on"].as_bool(), ar["quiet"]["would_skip"].as_bool()), (Some(false), Some(true)));
    let ar = r.iter().find(|x| x["ev"] == "presend_live_arm" && x["trig"]["mint"] == b58(&w_tok2)).unwrap();
    assert_eq!(ar["quiet"]["wh_dumps"].as_u64(), Some(10), "the book's history is used during the warm-up too");
    let st = r.iter().find(|x| x["ev"] == "presend_live_quiet_state").unwrap();
    assert_eq!((st["source"].as_str(), st["arm_on"].as_bool()), (Some("none"), Some(false)));
    let _ = c.finish(c_slot + 100, None);
    let _ = std::fs::remove_dir_all(&dir);
}

/// THE FALLBACKS: a missing book with a fresh journal (source: journal); a book with a damaged line and a cut last line (the rest used:
/// ON, source book, warned); a book of binary junk, an empty book, a directory, a missing book alone (each: no crash, the history
/// empty or what was readable, the warm-up, the probe working)
#[test]
fn dip21_book_missing_corrupt_fallbacks() {
    let dir = std::env::temp_dir().join(format!("dip21_bookfb_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let t0 = 1_793_000_000 * S;
    let t_of = |s: u64| t0 + (s - 1_000) * 212_000_000;
    let whale = [0x15u8; 32];
    let s_end = 1_000 + 80 * MIN / 212_000_000;
    let dumps: Vec<(u64, u32, Pk, u32)> = (0..5u64).map(|k| (2_000 + 3_000 * k, 5, whale, 3)).collect();
    let start = t_of(s_end) + 2 * MIN;
    let s0 = s_end + 2 * MIN / 212_000_000 + 1;
    let p = |n: &str| dir.join(n).display().to_string();
    // a missing book, a fresh journal: the journal
    hist_file(&dir.join("journal.jsonl"), &[(1_000, s_end)], &dumps, &t_of);
    let (mut a, _o, line) = session_with(start, &["--presend-live-quiet-book", &p("nope.jsonl"), "--presend-live-quiet-state", &p("journal.jsonl")]);
    assert!(line.contains(&format!("book {}: MISSING", p("nope.jsonl"))) && line.contains("arm rule ON now (source: journal)") && line.contains("merged 5 dumps"), "{line}");
    let _ = a.finish(s0, None);
    // a damaged line in the middle and a cut last line: the rest is used
    hist_file(&dir.join("damaged.jsonl"), &[(1_000, s_end)], &dumps, &t_of);
    let mut text = std::fs::read_to_string(dir.join("damaged.jsonl")).unwrap();
    let k = text.match_indices('\n').nth(2).unwrap().0 + 1;
    text.insert_str(k, "{\"k\":\"d\",\"s\":12,GARBAGE\n");
    text.push_str("{\"k\":\"d\",\"s\":9999,\"i\":1,\"j\":0,\"t\":1793");
    std::fs::write(dir.join("damaged.jsonl"), text).unwrap();
    let (mut b, _o, line) = session_with(start, &["--presend-live-quiet-book", &p("damaged.jsonl")]);
    eprintln!("damaged:{line}");
    assert!(line.contains("5 dumps, 1 session(s)") && line.contains("WARNING: skipped 1 bad line(s), a truncated last line") && line.contains("arm rule ON now (source: book)"), "{line}");
    assert_eq!(b.qt.as_ref().unwrap().book.as_ref().unwrap().whale(&whale, s0, start), (3.0, 5));
    let _ = b.finish(s0, None);
    // junk, empty, a directory, missing: the warm-up, the probe works
    std::fs::write(dir.join("junk.jsonl"), (0..20_000u32).map(|x| (x.wrapping_mul(2_654_435_761) >> 13) as u8).collect::<Vec<u8>>()).unwrap();
    std::fs::write(dir.join("empty.jsonl"), b"").unwrap();
    std::fs::create_dir_all(dir.join("adir")).unwrap();
    for (name, want) in [("junk.jsonl", "0 dumps, 0 session(s)"), ("empty.jsonl", "0 dumps, 0 session(s)"), ("adir", "UNREADABLE"), ("gone.jsonl", "MISSING")] {
        let (mut c, orx, line) = session_with(start, &["--presend-live-quiet-book", &p(name)]);
        eprintln!("{name}:{line}");
        assert!(line.contains(want) && line.contains("merged 0 dumps") && line.contains("warming up until"), "{name}: {line}");
        let m = trigger_at(&mut c, 7, s0, s0 + 5, [0x16; 32], &t_of);
        let (r, _) = all_out(&orx);
        let ar = r.iter().find(|x| x["ev"] == "presend_live_arm" && x["trig"]["mint"] == b58(&m)).unwrap_or_else(|| panic!("{name}: the probe works"));
        assert_eq!(ar["quiet"]["rule_on"].as_bool(), Some(false), "{name}");
        let _ = c.finish(s0 + 10, None);
    }
    let _ = std::fs::remove_dir_all(&dir);
}

/// THE BOOK AND THE JOURNAL JOINED: the book covers T-100..T-35 min (alone too old), the engine's journal T-40..T-2 min (alone 38 min
/// < the 60-min warm-up); they overlap (2 of W's dumps in both, same identities): merged, each dump once (W 7 dumps), the coverage
/// joined (98 min to T-2): ON at once, source book+journal; this session's dumps go to the journal (the book unchanged). With a
/// fresh book the source is the book
#[test]
fn dip21_book_and_journal_joined() {
    let dir = std::env::temp_dir().join(format!("dip21_bookj_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let t0 = 1_793_000_000 * S;
    let t_of = |s: u64| t0 + (s - 1_000) * 212_000_000;
    let sl = |min: u64| 1_000 + min * MIN / 212_000_000;
    let (w, w2) = ([0x15u8; 32], [0x25u8; 32]);
    let p = |n: &str| dir.join(n).display().to_string();
    // T = minute 100 (from slot 1000)
    let bk: Vec<(u64, u32, Pk, u32)> = [10u64, 30, 50, 62, 64].iter().map(|m| (sl(*m), 5, w, 3)).collect();
    hist_file(&dir.join("book.jsonl"), &[(sl(0), sl(65))], &bk, &t_of);
    let mut jd: Vec<(u64, u32, Pk, u32)> = [62u64, 64, 80].iter().map(|m| (sl(*m), 5, w, 3)).collect();
    jd.push((sl(90), 5, w, 0));
    jd.push((sl(85), 6, w2, 1));
    hist_file(&dir.join("journal.jsonl"), &[(sl(60), sl(98))], &jd, &t_of);
    let book_bytes = std::fs::read(dir.join("book.jsonl")).unwrap();
    let start = t_of(sl(100));
    let s0 = sl(100) + 1;
    let (mut a, orx, line) = session_with(start, &["--presend-live-quiet-book", &p("book.jsonl"), "--presend-live-quiet-state", &p("journal.jsonl")]);
    eprintln!("joined:{line}");
    assert!(line.contains("TOO OLD") && line.contains("continuous 0.63 h") && line.contains("merged 8 dumps / 2 sellers") && line.contains("continuous 1.63 h")
        && line.contains("arm rule ON now (source: book+journal)"), "{line}");
    assert_eq!(a.qt.as_ref().unwrap().book.as_ref().unwrap().whale(&w, s0, start), (18.0 / 7.0, 7), "each dump once");
    // this session: W2 dumps again, journaled
    let mut t = Tk::new(91);
    let _ = t.buy(w2, 3 * S);
    let d = t.sell_sol(w2, 4 * S);
    txt(&mut a, s0, 1, t_of(s0), vec![d], vec![], &[]);
    for (q, u) in [0x61u8, 0x62].iter().enumerate() { let e = t.buy([*u; 32], S / 10); txt(&mut a, s0 + 1, 2 + q as u64, t_of(s0 + 1), vec![e], vec![], &[]); }
    let mut f = Tk::new(250);
    let e = f.buy([0x50; 32], 1_000_000);
    txt(&mut a, s0 + 10, 1, t_of(s0 + 10), vec![e], vec![], &[]);
    let _ = a.finish(s0 + 11, None);
    let (r, _) = all_out(&orx);
    let st = r.iter().find(|x| x["ev"] == "presend_live_quiet_state").unwrap();
    assert_eq!((st["source"].as_str(), st["book"]["dumps"].as_u64(), st["journal"]["dumps"].as_u64(), st["dumps"].as_u64()), (Some("book+journal"), Some(5), Some(5), Some(8)));
    assert_eq!(std::fs::read(dir.join("book.jsonl")).unwrap(), book_bytes, "the book is only read");
    let l = arbx::presend_quiet::load_state(&dir.join("journal.jsonl"), t_of(s0 + 20), 24 * 60 * MIN);
    assert_eq!(l.dumps.len(), 9, "the journal: the merged history (8) + this session's dump");
    assert!(l.dumps.iter().any(|(d, _)| d.seller == w2 && d.nf == 2));
    // a fresh book (to T-2): the book alone is enough
    hist_file(&dir.join("book2.jsonl"), &[(sl(0), sl(98))], &bk, &t_of);
    let (mut b, _o, line) = session_with(start, &["--presend-live-quiet-book", &p("book2.jsonl"), "--presend-live-quiet-state", &p("journal.jsonl")]);
    assert!(line.contains("arm rule ON now (source: book)"), "{line}");
    let _ = b.finish(s0, None);
    let _ = std::fs::remove_dir_all(&dir);
}

/// a replay tx's signature from its chain position (dip20's harness's)
fn synth_sig(s: u64, i: u32) -> [u8; 64] { let mut g = [0u8; 64]; g[..8].copy_from_slice(&s.to_be_bytes()); g[8..12].copy_from_slice(&i.to_be_bytes()); g[12] = 0xEE; g }

/// RECORDED RESTARTS (by hand, real data; the input from ops/strategies/presend/filter/quiet_parity_export.py):
///   QUIET_PARITY_IN=<replay json> QUIET_PARITY_OUT=<engine json> QUIET_STATE_SESSIONS=real|restart:<stop unix s>:<start unix s>
///   [QUIET_STATE_PREHIST=1] [QUIET_BOOK_LAG_S=<s> [QUIET_BOOK_ONLY=1]] cargo test --release --bin snipe_engine dip21_recorded_restarts -- --ignored --nocapture
/// QUIET_BOOK_LAG_S: each session also gets THE HOST'S BOOK as the node would have it at its start: built by the host's code
/// (build_book, a full 24 h build) from the recording up to the session's start - the lag (the keeper's copy + build + push delay),
/// written and passed as --presend-live-quiet-book; QUIET_BOOK_ONLY=1: the book without the engine's own journal (a node's first run)
/// Each session is a FRESH probe (as a restarted engine: its own detector, its DumpBook from the journal only) on ONE journal file:
/// open_state at the session's start (the journal loaded, the arm rule's schedule from its continuity), the writer thread, the
/// session's recorded txs in chain order with the live slot clock, finish (the stop marker). QUIET_STATE_PREHIST=1: a first session
/// over the 24 h before the run (the engine ran with the journal before). Per live window inside a session: the four signals, the
/// arm rule's verdict and whether it was on -> JSON (quiet_parity_compare.py --engine-state)
#[test]
#[ignore]
fn dip21_recorded_restarts() {
    let inp = std::env::var("QUIET_PARITY_IN").expect("QUIET_PARITY_IN=<replay json>");
    let outp = std::env::var("QUIET_PARITY_OUT").expect("QUIET_PARITY_OUT=<engine json>");
    let mode = std::env::var("QUIET_STATE_SESSIONS").unwrap_or_else(|_| "real".into());
    let prehist = std::env::var("QUIET_STATE_PREHIST").is_ok();
    let ex: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&inp).unwrap()).unwrap();
    let pk = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
    let span = (ex["span"][0].as_i64().unwrap(), ex["span"][1].as_i64().unwrap());
    let recs: Vec<std::path::PathBuf> = ex["recs"].as_array().unwrap().iter().map(|x| std::path::PathBuf::from(x.as_str().unwrap())).collect();
    let own = pk(ex["own"].as_str().unwrap());
    let wins = ex["windows"].as_array().unwrap();
    let trig_t: HashMap<(u64, u64), u64> = wins.iter().map(|w| ((w["slot"].as_u64().unwrap(), w["idx"].as_u64().unwrap()), w["t"].as_u64().unwrap())).collect();
    let root = env!("CARGO_MANIFEST_DIR");
    let cohort: HashSet<String> = serde_json::from_str::<Vec<String>>(&std::fs::read_to_string(format!("{root}/ops/overnight/sel/cohort_train.json")).unwrap()).unwrap().into_iter().collect();
    let fb = load_fbots(&format!("{root}/ops/strategies/presend/filter/fbots_frozen.json")).unwrap();
    let mut segs: Vec<u64> = ex["seg_starts"].as_object().unwrap().values().map(|v| v.as_u64().unwrap() / S).collect();
    segs.sort();
    // the sessions (unix s): (from, to, evaluated)
    let mut sess: Vec<(i64, i64, bool)> = Vec::new();
    let first = segs[0] as i64;
    if prehist { sess.push((first - 24 * 3600, first - 60, false)); }
    if mode == "real" {
        for (k, s0) in segs.iter().enumerate() { sess.push((*s0 as i64, segs.get(k + 1).map(|x| *x as i64 - 5).unwrap_or(span.1), true)); }
    } else {
        let v: Vec<i64> = mode.trim_start_matches("restart:").split(':').map(|x| x.parse().unwrap()).collect();
        sess.push((first, v[0], true));
        sess.push((v[1], span.1, true));
    }
    let dir = std::env::temp_dir().join(format!("dip21_restarts_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).unwrap();
    let jpath = dir.join("quiet_state.jsonl").display().to_string();
    let bpath = dir.join("quiet_book.jsonl").display().to_string();
    let book_lag: Option<i64> = std::env::var("QUIET_BOOK_LAG_S").ok().map(|x| x.parse().expect("QUIET_BOOK_LAG_S=<seconds>"));
    let book_only = std::env::var("QUIET_BOOK_ONLY").is_ok();
    let mut out: Vec<serde_json::Value> = Vec::new();
    let mut lines: Vec<String> = Vec::new();
    for (from, to, eval) in sess {
        // the host's book as of this start - the lag (the host's code, a full 24 h build)
        let mut bdesc = String::new();
        if let Some(lag) = book_lag {
            let t = Instant::now();
            let p = arbx::presend_quiet::build_book(&recs, None, from as u64 * S, Some(from - lag), 24 * 3600 * S).unwrap();
            let (n_lines, bytes) = arbx::presend_quiet::write_book(std::path::Path::new(&bpath), &p.book).unwrap();
            bdesc = format!("\n    host book as of the start - {lag} s: {} dumps, {} session(s), ends {:.1} min before the start; {n_lines} lines, {:.2} MB; built in {:.1} s ({} chunks)",
                p.book.dumps.len(), p.book.sessions.len(), (from as u64 * S).saturating_sub(p.book.sessions.iter().map(|x| x.t1).max().unwrap_or(0)) as f64 / 6e10,
                bytes as f64 / 1e6, t.elapsed().as_secs_f64(), p.st.chunks);
        }
        let mut extra = vec!["--presend-live-quiet-stop", "6:2", "--presend-live-quiet-skip", "on", "--presend-live-quiet-hist-h", "24", "--presend-live-quiet-fol", "2.24",
            "--presend-live-quiet-warmup-min", "60", "--presend-live-fbots", "/in-test.json"];
        if !book_only { extra.extend(["--presend-live-quiet-state", jpath.as_str()]); }
        if book_lag.is_some() { extra.extend(["--presend-live-quiet-book", bpath.as_str()]); }
        let c = Cfg::from_argv(&args(&extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000).unwrap().unwrap();
        let (mut p, _atx, orx) = PsLive::for_test(c, own);
        let start_ns = from as u64 * S;
        let line = {
            let q = p.qt.as_mut().unwrap();
            q.coh = cohort.iter().filter_map(|s| bs58::decode(s).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok())).collect();
            q.fb = fb.clone(); q.start_ns = start_ns; q.warm_ns = 60 * MIN; q.keep_slots = u64::MAX / 4;
            let (line, _rec, compacted) = q.open_state(start_ns).unwrap();
            if let Some(c) = compacted { assert!(q.spawn_journal(c).is_none()); }
            line
        };
        let mut rec = arbx::presend_quiet::Recording::open(&recs, (from - 900).max(0) as u64, span.1 as u64, from, to, true, true);
        let (mut slot_now, mut n_tr, mut ns) = (0u64, 0u64, 0u128);
        let t_all = Instant::now();
        while let Some(t) = rec.next().unwrap() {
            if slot_now > 0 && t.s > slot_now + 1 && t.s <= slot_now + 64 { for k in slot_now + 1..t.s { p.tick(k, None); } }
            slot_now = slot_now.max(t.s);
            let t_rx = trig_t.get(&(t.s, t.i as u64)).copied().unwrap_or(t.bt.max(0) as u64 * S);
            n_tr += t.trades.len() as u64;
            let x = arbx::feeds::ExecInfo { index: t.i as u64, fee: 0, ok: true, trades: t.trades, creates: t.creates, mayhem: t.mayhem };
            let a = arbx::feeds::Arrival { feed: 0, slot: t.s, t_rx, t_decoded: t_rx, executed: Some(true), tx: arbx::tx::Tx { sig: synth_sig(t.s, t.i), keys: vec![[3u8; 32]], ..Default::default() },
                poh: None, raw: arbx::feeds::RawTx::None, exec: None };
            p.on_arrival(&a, slot_now);
            let t0 = Instant::now();
            p.on_exec(&a, &x, slot_now, |m: &Pk| Some(snipe_build::launch_from_target(*m, *m)), &|_| false, None);
            ns += t0.elapsed().as_nanos();
            if n_tr % 20_000 == 0 { let _ = orx.try_iter().count(); }
        }
        if eval {
            let q = p.qt.as_ref().unwrap();
            for w in wins {
                let t = w["t"].as_u64().unwrap() / S;
                if (t as i64) < from || (t as i64) > to { continue; }
                let (s, i, j) = (w["slot"].as_u64().unwrap(), w["idx"].as_u64().unwrap() as u32, w["j"].as_i64().unwrap());
                let key = (w["mint"].as_str().unwrap().to_string(), bs58::encode(synth_sig(s, i)).into_string(), j);
                out.push(match q.by_key.get(&key).and_then(|id| q.trigs.get(id)) {
                    None => serde_json::json!({"seg": w["seg"], "w": w["w"], "found": false, "session": from}),
                    Some(tg) => serde_json::json!({"seg": w["seg"], "w": w["w"], "found": true, "arm": tg.arm, "session": from}),
                });
            }
        }
        let (n_d, n_s) = p.qt.as_ref().and_then(|q| q.book.as_ref()).map(|b| (b.dumps(), b.sellers())).unwrap_or((0, 0));
        let end = p.finish(slot_now + 1, None);
        let _ = orx.try_iter().count();
        let l = format!("session {} .. {} ({:.2} h){}: {}{bdesc}\n    {} trades in {:.0} s, on_exec {:.0} ns/trade | book at the end {} dumps {} sellers | journal saved {} dumps ({} bytes, {} flushes, errors {})",
            from, to, (to - from) as f64 / 3600.0, if eval { "" } else { " [pre-history, not evaluated]" }, line.trim(), n_tr, t_all.elapsed().as_secs_f64(), ns as f64 / n_tr.max(1) as f64, n_d, n_s,
            end["quiet"]["state"]["end"]["dumps"], end["quiet"]["state"]["end"]["bytes"], end["quiet"]["state"]["end"]["flushes"], end["quiet"]["state"]["end"]["errors"]);
        eprintln!("{l}");
        lines.push(l);
    }
    let size = std::fs::metadata(&jpath).map(|m| m.len()).unwrap_or(0);
    let mode = match (book_lag, book_only) { (Some(l), true) => format!("{mode} + host book (lag {l} s), no journal"), (Some(l), false) => format!("{mode} + host book (lag {l} s) + journal"), _ => mode };
    std::fs::write(&outp, serde_json::to_string(&serde_json::json!({"mode": mode, "prehist": prehist, "sessions": lines, "journal_bytes": size, "windows": out})).unwrap()).unwrap();
    eprintln!("-> {outp} ({} windows); journal {} bytes", out.len(), size);
    let _ = std::fs::remove_dir_all(&dir);
}

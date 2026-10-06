//! campaign.rs tests: the segment sequencing with a fake segment runner on a virtual clock (a segment starts only once
//! the previous one's process has exited), the same with real child processes, the money between segments (the start
//! read from the segments' snapshots, the budget left and the floor passed on, a reconciliation miss making later
//! segments record only, a campaign-wide stop refusing the next segment), the control files, the classification
use super::*;
use crate::ledger::{entry, no_prices, Entry, Head, Raw, Snapshot};
use std::cell::{Cell, RefCell};
use std::rc::Rc;

const M: u64 = 60_000_000_000;
const T0: u64 = 1_800_000_000_000_000_000;

/// a virtual clock: sleeping moves it
struct FakeClock { t: Cell<u64> }
impl Clock for FakeClock {
    fn now_ns(&self) -> u64 { self.t.get() }
    fn sleep(&self, d: Duration) { self.t.set(self.t.get() + d.as_nanos() as u64); }
}

/// what one scripted segment does: how long it runs, how it ends, the files it writes when it starts (given its
/// directory and its start time), a control file it drops or removes at some minute of its run
/// (`stubborn`: it ignores its stop, the socket's and SIGINT, and dies only of SIGKILL or at its own end; `wait_err`:
/// waiting for it always fails)
struct Script { minutes: u64, rc: i32, reason: &'static str, files: Box<dyn Fn(&Path, u64)>, drop_file: Option<(u64, &'static str)>, remove_file: Option<(u64, &'static str)>,
    stubborn: bool, wait_err: bool }
fn script(minutes: u64, rc: i32, reason: &'static str, files: impl Fn(&Path, u64) + 'static) -> Script {
    Script { minutes, rc, reason, files: Box::new(files), drop_file: None, remove_file: None, stubborn: false, wait_err: false }
}

type Log = Rc<RefCell<Vec<(String, String, u64)>>>;

struct FakeChild { name: String, dir: PathBuf, runs: PathBuf, camp: String, start: u64, minutes: u64, rc: i32, reason: &'static str, clock: Rc<FakeClock>, log: Log,
    stopped: Rc<Cell<bool>>, drop_file: Option<(u64, &'static str)>, remove_file: Option<(u64, &'static str)>, pid: u32, stubborn: bool, wait_err: bool,
    killed: bool, signals: Rc<RefCell<Vec<(String, i32, u64)>>> }
impl Child for FakeChild {
    fn pid(&self) -> u32 { self.pid }
    fn try_wait(&mut self) -> Result<Option<i32>> {
        let now = self.clock.now_ns();
        if self.wait_err { anyhow::bail!("waitpid: ECHILD (test)"); }
        if self.killed {
            // a SIGKILL leaves no stop.json
            self.log.borrow_mut().push(("exited".into(), self.name.clone(), now));
            return Ok(Some(128 + libc::SIGKILL));
        }
        if let Some((at, ext)) = self.drop_file { if now >= self.start + at * M { std::fs::write(self.runs.join(format!("{}.{ext}", self.camp)), "owner says so").unwrap(); self.drop_file = None; } }
        if let Some((at, ext)) = self.remove_file { if now >= self.start + at * M { let _ = std::fs::remove_file(self.runs.join(format!("{}.{ext}", self.camp))); self.remove_file = None; } }
        let stopped = self.stopped.get();
        if now < self.start + self.minutes * M && !stopped { return Ok(None); }
        let (rc, reason) = if stopped { (10, "control") } else { (self.rc, self.reason) };
        std::fs::create_dir_all(&self.dir).unwrap();
        std::fs::write(self.dir.join("stop.json"), json!({ "reason": reason, "secondary": null, "unsettled": [], "drain_ms": 1.0 }).to_string()).unwrap();
        self.log.borrow_mut().push(("exited".into(), self.name.clone(), now));
        Ok(Some(rc))
    }
    fn signal(&mut self, sig: i32) {
        self.signals.borrow_mut().push((self.name.clone(), sig, self.clock.now_ns()));
        if sig == libc::SIGKILL { self.killed = true; } else if !self.stubborn { self.stopped.set(true); }
    }
}

struct FakeRunner { scripts: std::collections::VecDeque<Script>, runs: PathBuf, camp: String, clock: Rc<FakeClock>, log: Log, specs: Vec<Spec>, ctl: Vec<(String, String)>,
    stopped: Rc<Cell<bool>>, busy: Vec<Vec<String>>, stubborn: bool, signals: Rc<RefCell<Vec<(String, i32, u64)>>>,
    /// WP-22: what each pool refresh does, in order, and the refreshes started (the job, when); a flag its kill sets
    refreshes: std::collections::VecDeque<RefreshEnd>, jobs: Vec<(RefreshJob, u64)>, stop_on_kill: Option<Arc<AtomicBool>> }

/// how a fake pool refresh ends (WP-22): after `secs`, a new list (its pools), the previous list kept, no report at
/// all; or never (killed)
/// (review #4: a list whose hash is not the report's, a report for another segment, a refresh that cannot start, one
/// that crashes; one that hangs and writes its staging file after its SIGKILL)
#[derive(Clone)]
enum RefreshEnd { Ok(u64, Vec<u8>), Kept(u64), NoReport(u64), Hang, BadHash(u64), WrongSegment(u64), NoStart, Crash(u64), HangLateWriter }

struct FakeRefresh { job: RefreshJob, start: u64, end: RefreshEnd, clock: Rc<FakeClock>, killed: bool, done: bool, signals: Rc<RefCell<Vec<(String, i32, u64)>>>,
    /// set when it is killed (a stop that arrives at the segments' boundary, review #11)
    stop_on_kill: Option<Arc<AtomicBool>> }
impl Child for FakeRefresh {
    fn pid(&self) -> u32 { 9_000 }
    fn try_wait(&mut self) -> Result<Option<i32>> {
        if self.killed { return Ok(Some(128 + libc::SIGKILL)); }
        let secs = match &self.end {
            RefreshEnd::Ok(s, _) | RefreshEnd::Kept(s) | RefreshEnd::NoReport(s) | RefreshEnd::BadHash(s) | RefreshEnd::WrongSegment(s) | RefreshEnd::Crash(s) => *s,
            RefreshEnd::Hang | RefreshEnd::HangLateWriter | RefreshEnd::NoStart => return Ok(None),
        };
        if self.clock.now_ns() < self.start + secs * 1_000_000_000 { return Ok(None); }
        if !self.done {
            self.done = true;
            let rep = |status: &str, body: &[u8], extra: Value| {
                let mut r = json!({ "schema": crate::poolrefresh::SCHEMA, "segment": self.job.segment, "status": status, "reason": if status == "ok" { Value::Null } else { json!("the RPC refused (test)") },
                    "duration_ms": secs * 1000, "out": { "sha256": crate::provenance::sha256_hex(body) }, "counts": { "added": 2, "dropped": 1, "kept": 1, "kept_active": 1, "kept_idle": 0, "rows": 3 },
                    "top_tokens": [{ "token": "BQxzR4pLkDw46gzbrkRjFuUSsgvN5BhTWHh6EXUwf3F", "symbol": "BINDER", "pools": 2 }] });
                if let (Some(o), Some(e)) = (r.as_object_mut(), extra.as_object()) { for (k, v) in e { o.insert(k.clone(), v.clone()); } }
                std::fs::write(&self.job.report, r.to_string()).unwrap();
            };
            match &self.end {
                RefreshEnd::Ok(_, n) => {
                    let body: String = std::iter::once("venue,pool,source".to_string()).chain(n.iter().map(|x| format!("DLMM,{},wp22:gt:{}", crate::tx::b58(&[*x; 32]), self.job.segment)))
                        .collect::<Vec<_>>().join("\n") + "\n";
                    std::fs::write(&self.job.out, &body).unwrap();
                    rep("ok", body.as_bytes(), json!({}));
                }
                RefreshEnd::Kept(_) => {
                    let body = std::fs::read(&self.job.current).unwrap();
                    std::fs::write(&self.job.out, &body).unwrap();
                    rep("kept_previous", &body, json!({}));
                }
                RefreshEnd::BadHash(_) => {
                    std::fs::write(&self.job.out, "venue,pool,source\nDLMM,11111111111111111111111111111112,x\n").unwrap();
                    rep("ok", b"another list", json!({}));
                }
                RefreshEnd::WrongSegment(_) => {
                    let body = std::fs::read(&self.job.current).unwrap();
                    std::fs::write(&self.job.out, &body).unwrap();
                    rep("ok", &body, json!({ "segment": "c-p99" }));
                }
                // a panic halfway through writing (no rename: the staging file is a fragment, no report)
                RefreshEnd::Crash(_) => std::fs::write(&self.job.out, "venue,pool,sou").unwrap(),
                _ => {}
            }
        }
        Ok(Some(match self.end { RefreshEnd::Ok(..) | RefreshEnd::BadHash(_) | RefreshEnd::WrongSegment(_) => 0, RefreshEnd::Crash(_) => 101, _ => 3 }))
    }
    fn signal(&mut self, sig: i32) {
        self.signals.borrow_mut().push((format!("refresh {}", self.job.segment), sig, self.clock.now_ns()));
        if sig == libc::SIGKILL {
            self.killed = true;
            // review #6: a refresh whose last rename lands after its kill touches only its staging file
            if matches!(self.end, RefreshEnd::HangLateWriter) { std::fs::write(&self.job.out, "venue,pool,source\nDLMM,late,x\n").unwrap(); }
            if let Some(f) = &self.stop_on_kill { f.store(true, Ordering::Relaxed); }
        }
    }
}
impl Runner for FakeRunner {
    fn start(&mut self, spec: &Spec) -> Result<Box<dyn Child>> {
        let now = self.clock.now_ns();
        // the previous segment's process must have been reaped
        if let Some(last) = self.log.borrow().last() { assert_eq!(last.0, "exited", "{} started while {} had not exited", spec.name, last.1); }
        self.log.borrow_mut().push(("start".into(), spec.name.clone(), now));
        self.specs.push(spec.clone());
        let s = self.scripts.pop_front().expect("a script for every segment");
        std::fs::create_dir_all(&spec.dir).unwrap();
        std::fs::write(spec.dir.join("meta.json"), json!({ "run": { "started_ns": now }, "send_gate": { "mode": if spec.flag == Some("--shadow") { "shadow" } else { "live" } } }).to_string()).unwrap();
        (s.files)(&spec.dir, now);
        self.stopped = Rc::new(Cell::new(false));
        self.stubborn = s.stubborn;
        Ok(Box::new(FakeChild { name: spec.name.clone(), dir: spec.dir.clone(), runs: self.runs.clone(), camp: self.camp.clone(), start: now, minutes: s.minutes, rc: s.rc,
            reason: s.reason, clock: self.clock.clone(), log: self.log.clone(), stopped: self.stopped.clone(), drop_file: s.drop_file, remove_file: s.remove_file,
            pid: 4_000 + spec.index, stubborn: s.stubborn, wait_err: s.wait_err, killed: false, signals: self.signals.clone() }))
    }
    fn ctl(&mut self, spec: &Spec, cmd: &str, _why: &str) -> Result<Value> {
        self.ctl.push((spec.name.clone(), cmd.to_string()));
        if cmd == "stop" && !self.stubborn { self.stopped.set(true); }
        Ok(json!({ "accepted": true, "result": if cmd == "stop" { "stopping" } else { "ok" } }))
    }
    fn busy(&self) -> Vec<String> { self.busy.first().cloned().unwrap_or_default() }
    fn free_gb(&self) -> Option<f64> { Some(100.0) }
    fn refresh(&mut self, job: &RefreshJob) -> Result<Box<dyn Child>> {
        let now = self.clock.now_ns();
        self.jobs.push((job.clone(), now));
        let end = self.refreshes.pop_front().expect("a refresh script for every refresh");
        if matches!(end, RefreshEnd::NoStart) { anyhow::bail!("fork: Resource temporarily unavailable (test)"); }
        Ok(Box::new(FakeRefresh { job: job.clone(), start: now, end, clock: self.clock.clone(), killed: false, done: false, signals: self.signals.clone(),
            stop_on_kill: self.stop_on_kill.clone() }))
    }
}

fn snap(t: u64, slot: u64, sol: u64, wsol: u64) -> Snapshot { Snapshot { t_ns: t, slot, sol, wsol, rent_recoverable: 4_078_560, ..Default::default() } }
fn loss(sig: &str, slot: u64, t: u64, lost: i64) -> Entry {
    let r = Raw { kind: "route".into(), ok: false, payer: true, wallet_sol: -lost, fee: lost as u64, ..Default::default() };
    entry(&r, &Head { sig, slot, idx: None, t_ns: t, attempt: None, pre_run: false }, 0.1, &no_prices)
}
fn write_lines(dir: &Path, file: &str, schema: &str, lines: &[Value]) {
    let body: String = std::iter::once(json!({ "schema": schema, "file_seq": 0 }).to_string()).chain(lines.iter().map(|l| l.to_string())).collect::<Vec<_>>().join("\n");
    std::fs::write(dir.join(file), format!("{body}\n")).unwrap();
}

struct Rig { camp: Campaign, runner: FakeRunner, clock: Rc<FakeClock>, root: PathBuf, log: Log }
impl Drop for Rig { fn drop(&mut self) { let _ = std::fs::remove_dir_all(&self.root); } }

/// a campaign `c` of `hours` in 60-minute segments with a 34M test budget, on a virtual clock; `scripts` its segments
fn rig(tag: &str, mode: Mode, hours: f64, scripts: Vec<Script>) -> Rig {
    let root = std::env::temp_dir().join(format!("arbx-campaign-{tag}-{}-{}", std::process::id(), now_ns()));
    let runs = root.join("runs");
    let dir = runs.join("c");
    std::fs::create_dir_all(&dir).unwrap();
    let cfg = Config::parse("config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"w\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n[state]\nurl = \"http://localhost\"\n").unwrap();
    let budget = mode.sends().then_some(34_000_000);
    let mut camp = Campaign::new(dir.clone(), runs.clone(), "c", mode, hours, 60.0, budget, &cfg);
    camp.poll = Duration::from_secs(60);
    camp.backoff = Duration::from_secs(10);
    camp.echo = false;
    let clock = Rc::new(FakeClock { t: Cell::new(T0) });
    let log: Log = Default::default();
    let runner = FakeRunner { scripts: scripts.into(), runs: runs.clone(), camp: "c".into(), clock: clock.clone(), log: log.clone(), specs: vec![], ctl: vec![],
        stopped: Rc::new(Cell::new(false)), busy: vec![], stubborn: false, signals: Default::default(), refreshes: Default::default(), jobs: vec![], stop_on_kill: None };
    Rig { camp, runner, clock, root, log }
}
impl Rig {
    fn run(&mut self) -> String { let clock = self.clock.clone(); self.camp.run(&mut self.runner, clock.as_ref()) }
    fn events(&self) -> Vec<Value> {
        std::fs::read_to_string(self.camp.dir.join("events.jsonl")).unwrap_or_default().lines().map(|l| serde_json::from_str(l).unwrap()).collect()
    }
    fn json(&self, f: &str) -> Value { serde_json::from_slice(&std::fs::read(self.camp.dir.join(f)).unwrap()).unwrap() }
}

/// The campaign supervisor's sequencing and money, with a fake segment runner on a virtual clock (the brief's test):
/// - each segment starts only after the previous one's process has exited (the runner refuses otherwise, and the log
///   alternates start / exited);
/// - the start is read from the first segment's first snapshot (SOL + WSOL 414.5M; its components and the basis in
///   campaign.json); the second segment gets what is left of the budget (22M after a 12M loss) and the floor (380.5M);
/// - a reconciliation miss in the second segment makes the third record only (`--shadow` instead of `--canary`);
/// - the third ends with a safety stop (exit 20, `equity_hour`): the campaign ends, with a Critical notice
#[test]
fn segments_run_back_to_back_with_the_campaigns_money() {
    let seg1 = script(60, 0, "deadline", |d, t| {
        write_lines(d, "snapshots.jsonl", "arbx.snapshots/1.0", &[snap(t + 1_000_000_000, 1_000, 223_000_000, 191_500_000).json(), snap(t + 59 * M, 1_300, 211_000_000, 191_500_000).json()]);
        write_lines(d, "ledger.jsonl", "arbx.ledger/1.0", &[loss("a", 1_100, t + 50 * M, 6_000_000).json(), loss("b", 1_200, t + 55 * M, 6_000_000).json()]);
    });
    let seg2 = script(60, 0, "deadline", |d, t| {
        write_lines(d, "snapshots.jsonl", "arbx.snapshots/1.0", &[snap(t + 1_000_000_000, 2_000, 211_000_000, 191_500_000).json()]);
        write_lines(d, "recon.jsonl", "arbx.recon/1.0", &[json!({ "t_ns": t + 30 * M, "ok": false, "residual": -15_000 })]);
    });
    let seg3 = script(20, 20, "equity_hour", |_, _| {});
    let mut r = rig("seq", Mode::Canary, 6.0, vec![seg1, seg2, seg3]);
    let (why, notes) = notify::capture(|| r.run());
    assert_eq!(why, "safety stop in c-p3 (equity_hour)");
    let log = r.log.borrow().clone();
    assert_eq!(log.iter().map(|x| format!("{} {}", x.0, x.1)).collect::<Vec<_>>(),
        ["start c-p1", "exited c-p1", "start c-p2", "exited c-p2", "start c-p3", "exited c-p3"], "strictly one after the other");
    for w in log.windows(2) { assert!(w[0].2 <= w[1].2, "{w:?}"); }
    let s = &r.runner.specs;
    assert_eq!((s[0].flag, s[0].budget_left, s[0].equity_floor), (Some("--canary"), Some(34_000_000), None), "the first segment: the whole budget, the floor from its own start");
    assert_eq!((s[1].flag, s[1].budget_left, s[1].equity_floor), (Some("--canary"), Some(22_000_000), Some(414_500_000 - 34_000_000)));
    assert_eq!((s[2].flag, s[2].why_shadow.as_deref()), (Some("--shadow"), Some("reconciliation miss in c-p2")), "records only after a recon miss");
    let c = r.json("campaign.json");
    assert_eq!((c["schema"].as_str(), c["mode"].as_str(), c["end_reason"].as_str()), (Some(SCHEMA), Some("canary"), Some("safety stop in c-p3 (equity_hour)")));
    let st = &c["equity"]["start"];
    assert_eq!((st["basis"].as_str(), st["equity_stop"].as_i64(), st["sol"].as_u64(), st["wsol"].as_u64(), st["rent_recoverable"].as_u64(), st["segment"].as_str()),
        (Some("sol_wsol"), Some(414_500_000), Some(223_000_000), Some(191_500_000), Some(4_078_560), Some("c-p1")), "the start, read from the chain, with its components");
    assert!(c["equity"]["basis"].as_str().unwrap().starts_with("net_spend"), "review WP-07 #4: the stops measure the net spend");
    assert_eq!((c["equity"]["floor_lamports"].as_i64(), c["equity"]["net_spend"].as_i64()), (Some(380_500_000), Some(12_000_000)));
    assert_eq!(c["segments"].as_array().unwrap().iter().map(|x| x["class"].as_str().unwrap()).collect::<Vec<_>>(), ["natural", "natural", "safety"]);
    assert_eq!(c["records_only_why"].as_str(), Some("reconciliation miss in c-p2"));
    let kinds: Vec<String> = r.events().iter().map(|e| e["kind"].as_str().unwrap().to_string()).collect();
    for k in ["campaign_start", "equity_start", "segment_start", "segment_end", "campaign_shadow", "campaign_end"] { assert!(kinds.iter().any(|x| x == k), "{k}: {kinds:?}"); }
    assert_eq!(r.json("spend.json")["total"]["fees"].as_i64(), Some(12_000_000));
    assert!(notes.iter().any(|n| n.kind == "campaign_end" && n.level == Level::Critical), "{notes:?}");
    assert!(notes.iter().any(|n| n.kind == "campaign_shadow" && n.level == Level::Error));
}

/// PLAN WP-07 acceptance ("the supervisor dry run refuses a third segment"): the second segment's losses (a landing the
/// segment did not stop on) take SOL + WSOL below the campaign's floor: before the third, the campaign-wide check ends
/// the campaign (`equity_floor`), with a Critical notice. A shadow campaign has nothing at stake: the same losses stop
/// nothing, and its segments get no budget or floor
#[test]
fn a_campaign_wide_stop_refuses_the_next_segment() {
    let seg1 = script(60, 0, "deadline", |d, t| {
        write_lines(d, "snapshots.jsonl", "arbx.snapshots/1.0", &[snap(t + 1_000_000_000, 1_000, 223_000_000, 191_500_000).json()]);
        write_lines(d, "ledger.jsonl", "arbx.ledger/1.0", &[loss("a", 1_100, t + 20 * M, 12_000_000).json()]);
    });
    let seg2 = script(60, 0, "deadline", |d, t| {
        write_lines(d, "ledger.jsonl", "arbx.ledger/1.0", &[loss("b", 2_100, t + 2 * M, 25_000_000).json()]);
    });
    let mut r = rig("refuse", Mode::Canary, 6.0, vec![seg1, seg2]);
    let (why, notes) = notify::capture(|| r.run());
    assert!(why.starts_with("safety stop between segments (equity_floor"), "{why}");
    assert_eq!(r.runner.specs.len(), 2, "no third segment");
    assert!(notes.iter().any(|n| n.kind == "equity_floor" && n.level == Level::Critical));
    let seg1 = script(60, 0, "deadline", |d, t| {
        write_lines(d, "snapshots.jsonl", "arbx.snapshots/1.0", &[snap(t + 1_000_000_000, 1_000, 223_000_000, 191_500_000).json()]);
        write_lines(d, "ledger.jsonl", "arbx.ledger/1.0", &[loss("a", 1_100, t + 20 * M, 40_000_000).json()]);
    });
    let mut r = rig("shadowcamp", Mode::Shadow, 2.0, vec![seg1, script(60, 0, "deadline", |_, _| {})]);
    assert_eq!(r.run(), "time up");
    assert_eq!(r.runner.specs.iter().map(|s| (s.flag, s.budget_left, s.equity_floor)).collect::<Vec<_>>(), [(None, None, None), (None, None, None)]);
}

/// The control files: `.pause` pauses the running segment (resumed when the file goes); `.stop` mid-segment stops it
/// through its socket and ends the campaign; a segment that starts while `.pause` exists records only and is restarted
/// when it goes, so the next one sends
#[test]
fn control_files() {
    let mut s1 = script(60, 0, "deadline", |_, _| {});
    s1.drop_file = Some((10, "pause"));
    s1.remove_file = Some((20, "pause"));
    let mut s2 = script(60, 0, "deadline", |_, _| {});
    s2.drop_file = Some((5, "stop"));
    let mut r = rig("files", Mode::Canary, 6.0, vec![s1, s2]);
    let why = r.run();
    assert_eq!(why, "stop file: owner says so");
    assert_eq!(r.runner.ctl.iter().map(|(s, c)| format!("{s} {c}")).collect::<Vec<_>>(), ["c-p1 pause-sending", "c-p1 resume-sending", "c-p2 stop"]);
    let ctl: Vec<Value> = std::fs::read_to_string(r.camp.dir.join("control.jsonl")).unwrap().lines().map(|l| serde_json::from_str(l).unwrap()).collect();
    assert!(ctl.iter().any(|l| l["cmd"] == "stop" && l["src"] == "file"), "{ctl:?}");
    assert_eq!(r.json("campaign.json")["segments"][1]["class"].as_str(), Some("operator"));
    // a segment that starts while the pause file exists records only; it is restarted when the file goes
    let mut s1 = script(60, 0, "deadline", |_, _| {});
    s1.remove_file = Some((10, "pause"));
    let mut r2 = rig("paused", Mode::Canary, 3.0, vec![s1, script(60, 0, "deadline", |_, _| {}), script(60, 0, "deadline", |_, _| {})]);
    std::fs::write(r2.camp.runs.join("c.pause"), "checking").unwrap();
    r2.camp.max_segments = Some(3);
    r2.run();
    assert_eq!((r2.runner.specs[0].flag, r2.runner.specs[0].why_shadow.as_deref()), (Some("--shadow"), Some("paused")));
    assert_eq!(r2.runner.ctl.first().map(|x| x.1.as_str()), Some("stop"), "restarted once the pause was lifted");
    assert_eq!(r2.runner.specs[1].flag, Some("--canary"), "the next one sends");
}

/// The supervisor waits for the provider (I-3): a segment starts only once nothing else holds it; still busy after the
/// wait, the campaign ends without starting one
#[test]
fn the_provider_must_be_free() {
    let mut r = rig("busy", Mode::Canary, 2.0, vec![]);
    r.runner.busy = vec![vec!["pid 77: arb-lab run".into()]];
    let why = r.run();
    assert!(why.starts_with("the provider is busy: pid 77"), "{why}");
    assert!(r.runner.specs.is_empty());
}

/// How segments end (MEASUREMENT §4.1 `class`)
#[test]
fn classification() {
    let d = std::env::temp_dir().join(format!("arbx-classify-{}-{}", std::process::id(), now_ns()));
    std::fs::create_dir_all(&d).unwrap();
    let with = |reason: Option<&str>, secondary: bool| {
        let _ = std::fs::remove_file(d.join("stop.json"));
        if let Some(r) = reason { std::fs::write(d.join("stop.json"), json!({ "reason": r, "secondary": if secondary { json!({ "reason": "error" }) } else { Value::Null } }).to_string()).unwrap(); }
    };
    for (reason, secondary, rc, want) in [(Some("deadline"), false, 0, "natural"), (Some("signal"), false, 10, "operator"), (Some("control"), false, 10, "operator"),
        (Some("equity_floor"), false, 20, "safety"), (Some("equity_hour"), false, 20, "safety"), (Some("token_floor"), false, 20, "safety"), (Some("disk_budget"), false, 20, "safety"),
        (Some("equity_day"), false, 20, "safety"), (Some("error"), false, 30, "crash"), (Some("state_unavailable"), false, 30, "crash"), (Some("control"), true, 30, "crash"),
        (None, false, 0, "crash"), (Some("deadline"), false, 137, "crash"), (None, false, 20, "safety")] {
        with(reason, secondary);
        assert_eq!(classify(&d, rc).0, want, "{reason:?} {secondary} {rc}");
    }
    let _ = std::fs::remove_dir_all(&d);
}

/// a runner of real processes: each segment is `sh -c "sleep 0.3"` (its stop.json written first); at each start, the
/// previous segment's process must be gone
struct ShRunner { started: Vec<(String, u32, std::time::Instant)>, gone_at_start: Vec<bool> }
impl Runner for ShRunner {
    fn start(&mut self, spec: &Spec) -> Result<Box<dyn Child>> {
        let gone = self.started.last().map_or(true, |(_, pid, _)| unsafe { libc::kill(*pid as i32, 0) } != 0);
        self.gone_at_start.push(gone);
        std::fs::create_dir_all(&spec.dir)?;
        std::fs::write(spec.dir.join("stop.json"), json!({ "reason": "deadline", "secondary": null }).to_string())?;
        let c = std::process::Command::new("sh").args(["-c", "sleep 0.3"]).stdin(std::process::Stdio::null()).spawn()?;
        self.started.push((spec.name.clone(), c.id(), std::time::Instant::now()));
        Ok(Box::new(ProcChild(c)))
    }
    fn ctl(&mut self, _: &Spec, _: &str, _: &str) -> Result<Value> { Ok(json!({ "accepted": true })) }
    fn busy(&self) -> Vec<String> { vec![] }
    fn free_gb(&self) -> Option<f64> { None }
}

/// Waiting for process exit, with real processes: three segments, each a child process that runs 0.3 s; the next starts
/// only once the previous one has exited and been reaped (its pid no longer exists), at least 0.3 s after it started
#[test]
fn segments_wait_for_the_previous_process_to_exit() {
    let root = std::env::temp_dir().join(format!("arbx-campaign-sh-{}-{}", std::process::id(), now_ns()));
    let dir = root.join("c");
    std::fs::create_dir_all(&dir).unwrap();
    let cfg = Config::parse("config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"w\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n[state]\nurl = \"http://localhost\"\n").unwrap();
    let mut c = Campaign::new(dir, root.clone(), "c", Mode::Shadow, 1.0, 2.0, None, &cfg);
    c.poll = Duration::from_millis(20);
    c.max_segments = Some(3);
    c.echo = false;
    let mut r = ShRunner { started: vec![], gone_at_start: vec![] };
    assert_eq!(c.run(&mut r, &RealClock), "max segments (3)");
    assert_eq!(r.gone_at_start, [true, true, true], "every earlier process had exited when the next started");
    for w in r.started.windows(2) { assert!(w[1].2.duration_since(w[0].2) >= Duration::from_millis(300), "{} started {:?} after {}", w[1].0, w[1].2.duration_since(w[0].2), w[0].0); }
    let camp: Value = serde_json::from_slice(&std::fs::read(root.join("c").join("campaign.json")).unwrap()).unwrap();
    assert_eq!(camp["segments"].as_array().map(|a| a.iter().map(|s| (s["exit_code"].as_i64(), s["class"].as_str().map(String::from))).collect::<Vec<_>>()),
        Some(vec![(Some(0), Some("natural".to_string())); 3]));
    let _ = std::fs::remove_dir_all(&root);
}

/// The real runner's command line: the frozen binary's `run` with the campaign directory, the .env, the drain, what is
/// left of the budget, the floor and the mode's flag (never a secret)
#[test]
fn the_segments_command_line() {
    let p = ProcessRunner { bin: "/r/c/arbx-12345678".into(), config: "/r/c/config.frozen.toml".into(), dir: "/r/c".into(), runs: "/r".into(), env_file: "/root/arbx/deploy/.env".into(),
        drain_s: 60, pass: None, force: false };
    let s = Spec { index: 2, name: "c-p2".into(), dir: "/r/c/c-p2".into(), minutes: 60.0, flag: Some("--canary"), budget_left: Some(22_000_000), equity_floor: Some(380_500_000), why_shadow: None, pools_csv: None };
    assert_eq!(p.args(&s).join(" "), "run --config /r/c/config.frozen.toml --minutes 60 --name c-p2 --campaign-dir /r/c --env-file /root/arbx/deploy/.env --drain-s 60 \
--budget-left 22000000 --equity-floor 380500000 --canary");
    // WP-22: a segment's own list, and the refresh's command line (the frozen config and binary, the campaign's records)
    let s = Spec { pools_csv: Some("/r/c/pools-c-p2.csv".into()), ..s };
    assert!(p.args(&s).join(" ").ends_with("--equity-floor 380500000 --pools-csv /r/c/pools-c-p2.csv --canary"));
    let j = RefreshJob { segment: "c-p3".into(), current: "/r/c/pools-c-p2.csv".into(), out: "/r/c/pools-c-p3.refresh.csv".into(), report: "/r/c/pool-refresh-c-p3.json".into(),
        log: "/r/c/pool-refresh-c-p3.out".into(), deadline_s: 225, segment_min: 30.0 };
    assert_eq!(p.refresh_args(&j).join(" "), "pools refresh --config /r/c/config.frozen.toml --current /r/c/pools-c-p2.csv --runs /r/c --out /r/c/pools-c-p3.refresh.csv \
--report /r/c/pool-refresh-c-p3.json --env-file /root/arbx/deploy/.env --segment c-p3 --deadline-s 225 --segment-min 30");
    assert_eq!(Mode::parse("dry-run"), Some(Mode::DryRun));
    assert!(Mode::Canary.sends() && !Mode::DryRun.sends());
    assert_eq!(iso(T0), "2027-01-15T08:00:00Z");
}

/// Review WP-07 #2 (mutant M4): a segment that ignores its stop (the socket's and SIGINT) gets SIGINT `stop_int_s` after
/// the stop and SIGKILL `stop_kill_s` after it; the next segment starts only once it is gone (a SIGKILL leaves no
/// stop.json: a crash)
#[test]
fn a_segment_that_ignores_its_stop_is_killed() {
    let mut s1 = script(60, 0, "deadline", |_, _| {});
    s1.stubborn = true;
    s1.drop_file = Some((5, "next"));
    let mut r = rig("kill", Mode::Canary, 3.0, vec![s1, script(60, 0, "deadline", |_, _| {})]);
    r.camp.max_segments = Some(2);
    r.run();
    let start = r.log.borrow().iter().find(|x| x.0 == "start" && x.1 == "c-p1").unwrap().2;
    let sig: Vec<(i32, u64)> = r.runner.signals.borrow().iter().filter(|x| x.0 == "c-p1").map(|x| (x.1, (x.2 - start) / M)).collect();
    assert_eq!(sig, [(libc::SIGINT, 6), (libc::SIGKILL, 8)], "the stop at minute 5 (ignored), SIGINT 60 s later (ignored), SIGKILL 180 s after the stop");
    let c = r.json("campaign.json");
    assert_eq!((c["segments"][0]["exit_code"].as_i64(), c["segments"][0]["class"].as_str()), (Some(137), Some("crash")), "{}", c["segments"][0]);
    let log = r.log.borrow().clone();
    assert_eq!(log.iter().map(|x| format!("{} {}", x.0, x.1)).collect::<Vec<_>>()[..3], ["start c-p1", "exited c-p1", "start c-p2"]);
    assert!(log[1].2 < start + 10 * M, "killed, not run out to its own end");
}

/// Review WP-07 #2 (mutant M5): more than six crashes within 15 minutes end the campaign
#[test]
fn more_than_six_crashes_in_15_minutes_end_the_campaign() {
    let scripts: Vec<Script> = (0..8).map(|_| script(0, 30, "error", |_, _| {})).collect();
    let mut r = rig("crashes", Mode::Shadow, 6.0, scripts);
    let why = r.run();
    assert_eq!(why, "crash limit: 7 crashes in 15 min");
    assert_eq!(r.runner.specs.len(), 7);
    assert_eq!(r.json("campaign.json")["crash_count_15min"].as_u64(), Some(7));
}

/// Review WP-07 #14: a segment whose exit cannot be waited for is stopped and waited for as at any stop (the stop, then
/// SIGINT and SIGKILL); still not reaped, the campaign ends (a safety end): no segment ever starts beside it
#[test]
fn a_segment_that_cannot_be_reaped_ends_the_campaign() {
    let mut s1 = script(60, 0, "deadline", |_, _| {});
    s1.wait_err = true;
    let mut r = rig("unreaped", Mode::Canary, 3.0, vec![s1, script(60, 0, "deadline", |_, _| {})]);
    let (why, notes) = notify::capture(|| r.run());
    assert!(why.starts_with("safety: segment c-p1 could not be reaped"), "{why}");
    assert_eq!(r.runner.specs.len(), 1, "none beside it");
    assert_eq!(r.runner.ctl.iter().map(|(s, c)| format!("{s} {c}")).collect::<Vec<_>>(), ["c-p1 stop"]);
    assert_eq!(r.runner.signals.borrow().iter().map(|x| x.1).collect::<Vec<_>>(), [libc::SIGINT, libc::SIGKILL]);
    assert!(notes.iter().any(|n| n.kind == "segment_unreaped" && n.level == Level::Critical), "{notes:?}");
}

/// Review WP-07 #16: the data files the config names are hashed into campaign.json; one that changes mid-campaign is an
/// event and a Warn notice before the next segment
#[test]
fn a_data_file_changed_mid_campaign_is_reported() {
    let mut r = rig("datafiles", Mode::Shadow, 3.0, vec![]);
    let f = r.root.join("seed.csv");
    std::fs::write(&f, "a").unwrap();
    let g = f.clone();
    r.runner.scripts = vec![script(60, 0, "deadline", move |_, _| { std::fs::write(&g, "b").unwrap(); }), script(60, 0, "deadline", |_, _| {})].into();
    let mut m = serde_json::Map::new();
    m.insert(f.display().to_string(), json!(crate::provenance::sha256_hex(b"a")));
    r.camp.state["data_files"] = Value::Object(m);
    r.camp.max_segments = Some(2);
    let (_, notes) = notify::capture(|| r.run());
    assert!(notes.iter().any(|n| n.kind == "data_files_changed" && n.level == Level::Warn), "{notes:?}");
    assert_eq!(r.json("campaign.json")["data_files_changed"][0]["sha256_now"].as_str(), Some(crate::provenance::sha256_hex(b"b").as_str()));
}

/// Integration (WP-20 x WP-07, `arbx campaign`'s wiring): the campaign's own alerts (`CampaignAlerts`, as `main` starts
/// them after the detach) are the process's `notify` hook, so the campaign's notices reach the owner's chat: its start
/// (🟢 with the plan) and its end (⏹ with the reason), in WP-07's words; `finish` sends what is still queued (bounded)
/// before the process ends, and takes the hook away
#[test]
fn integ_the_campaign_tells_its_start_and_its_end() {
    let _hook = notify::hook_test_lock();
    let fake = crate::alerts::tests::Fake::start();
    let (a, _) = crate::alerts::Alerts::with(&crate::alerts::tests::on(20), crate::alerts::tests::quick(), &crate::alerts::tests::env_ok, &fake.base,
        crate::alerts::Ctx { label: "campaign integ-c".into(), ..Default::default() });
    assert!(a.enabled());
    let alerts = CampaignAlerts::start(a.clone(), false);
    let mut r = rig("integ-alerts", Mode::Shadow, 1.0, vec![script(60, 0, "deadline", |_, _| {})]);
    r.camp.name = "integ-c".into();
    let why = r.run();
    alerts.finish();
    assert_eq!(why, "time up");
    crate::alerts::tests::wait_for("the start and the end", 10, || {
        let t = fake.texts().join("\n");
        t.contains("🟢 <b>campaign integ-c: started: 1 h, 1 segments of 60 min, mode shadow</b>") && t.contains("⏹ <b>campaign integ-c: ended: time up</b>")
    });
    // the hook went with `finish`: a later notice reaches no chat
    let before = fake.n();
    notify::notify(notify::now(Level::Info, "campaign_start", "campaign", "integ-c-later", "after the end", json!({})));
    std::thread::sleep(Duration::from_millis(200));
    assert_eq!(fake.n(), before);
}

/// WP-22, the campaign boundary: with the pool refresh on, each segment boots on its own list in the campaign directory
/// (the first a copy of the config's seed list); the refresh for the next segment starts `lead_s` before a segment ends,
/// beside it; the next segment boots on its list once its report says ok and the file hashes as it says (p2), else on a
/// copy of the previous list with why: the refresh kept the previous list (p3), it hung and was killed at `timeout_s`
/// (p4). The last segment runs no refresh. Every list is hashed in campaign.json `pool_lists` and the segment's entry;
/// each refresh is an events.jsonl `pool_refresh` event and one notice (Info when used, Warn when not). The gap between
/// segments does not grow. The seed list is the one data file allowed to change; the others are still checked
#[test]
fn wp22_each_segment_boots_on_its_refreshed_list() {
    let scripts: Vec<Script> = (0..4).map(|_| script(30, 0, "deadline", |_, _| {})).collect();
    let mut r = rig("wp22", Mode::Canary, 2.0, scripts);
    r.camp.segment_min = 30.0;
    let seed = r.root.join("seed.csv");
    let other = r.root.join("registry.json");
    std::fs::write(&seed, format!("venue,pool,source\nDLMM,{},mriya\n", crate::tx::b58(&[1; 32]))).unwrap();
    std::fs::write(&other, "[]").unwrap();
    r.camp.seed_csv = seed.clone();
    r.camp.refresh = Some(crate::config::PoolRefreshCfg { enabled: true, lead_s: 300, timeout_s: 240, ..Default::default() });
    let mut m = serde_json::Map::new();
    for f in [&seed, &other] { m.insert(f.display().to_string(), json!(crate::provenance::sha256_hex(&std::fs::read(f).unwrap()))); }
    r.camp.state["data_files"] = Value::Object(m);
    r.runner.refreshes = vec![RefreshEnd::Ok(60, vec![1, 2, 3]), RefreshEnd::Kept(30), RefreshEnd::Hang].into();
    // mid-campaign, both data files change: only the registry's change is reported (the seed list is per segment now)
    let (s2, o2) = (seed.clone(), other.clone());
    r.runner.scripts[0].files = Box::new(move |_, _| { std::fs::write(&s2, "venue,pool,source\n").unwrap(); std::fs::write(&o2, "[1]").unwrap(); });
    let (why, notes) = notify::capture(|| r.run());
    assert_eq!(why, "time up");
    let dir = r.camp.dir.clone();
    let lists: Vec<PathBuf> = r.runner.specs.iter().map(|s| s.pools_csv.clone().unwrap()).collect();
    assert_eq!(lists, (1..=4).map(|i| dir.join(format!("pools-c-p{i}.csv"))).collect::<Vec<_>>(), "each segment its own list");
    let body = |p: &Path| std::fs::read(p).unwrap();
    assert_eq!(body(&lists[0]), format!("venue,pool,source\nDLMM,{},mriya\n", crate::tx::b58(&[1; 32])).into_bytes(), "p1: the config's list as it was at the start");
    assert!(String::from_utf8(body(&lists[1])).unwrap().contains(&format!("{},wp22:gt:c-p2", crate::tx::b58(&[3; 32]))), "p2: the refreshed list");
    assert_eq!(body(&lists[2]), body(&lists[1]), "p3: the refresh kept the previous list");
    assert_eq!(body(&lists[3]), body(&lists[2]), "p4: the refresh hung: the previous list");
    // the refreshes: during p1, p2, p3 (not p4: no next segment), each `lead_s` before its segment's end, for the next one
    let starts: Vec<u64> = r.log.borrow().iter().filter(|x| x.0 == "start").map(|x| x.2).collect();
    assert_eq!(r.runner.jobs.iter().map(|(j, _)| j.segment.as_str()).collect::<Vec<_>>(), ["c-p2", "c-p3", "c-p4"]);
    for (i, (j, t)) in r.runner.jobs.iter().enumerate() {
        assert_eq!((t - starts[i]) / M, 25, "{} started 25 min into its segment", j.segment);
        assert_eq!(j.current, lists[i]);
        assert_eq!(j.out, dir.join(format!("pools-c-p{}.refresh.csv", i + 2)), "the refresh writes a staging file, never the list a segment boots from");
        assert_eq!(j.segment_min, 30.0);
    }
    let kills: Vec<(String, i32, u64)> = r.runner.signals.borrow().iter().filter(|x| x.0.starts_with("refresh")).cloned().collect();
    assert_eq!(kills.len(), 1, "{kills:?}");
    assert_eq!((kills[0].0.as_str(), kills[0].1, (kills[0].2 - r.runner.jobs[2].1) / 1_000_000_000), ("refresh c-p4", libc::SIGKILL, 240), "killed at timeout_s");
    // no gap added: each segment starts as soon as the previous one exited
    let log = r.log.borrow().clone();
    for w in log.windows(2).filter(|w| w[0].0 == "exited") { assert!(w[1].2 - w[0].2 <= M, "{w:?}"); }
    // recorded: campaign.json `pool_lists` and each segment's list and hash
    let c = r.json("campaign.json");
    let pl = c["pool_lists"].as_array().unwrap();
    assert_eq!(pl.iter().map(|x| x["source"].as_str().unwrap()).collect::<Vec<_>>(), ["config", "refresh", "previous", "previous"]);
    for (i, x) in pl.iter().enumerate() {
        assert_eq!(x["sha256"].as_str(), Some(crate::provenance::sha256_hex(&body(&lists[i])).as_str()));
        assert_eq!(c["segments"][i]["pools_csv_sha256"], x["sha256"]);
        assert_eq!(c["segments"][i]["pools_csv"].as_str(), Some(lists[i].display().to_string().as_str()));
    }
    assert_eq!(pl[1]["counts"]["added"].as_u64(), Some(2));
    assert!(pl[2]["reason"].as_str().unwrap().contains("kept the previous list"), "{}", pl[2]);
    assert!(pl[3]["reason"].as_str().unwrap().contains("did not finish in time"), "{}", pl[3]);
    assert!(c["pool_refresh"]["policy"]["enabled"].as_bool().unwrap());
    let ev: Vec<Value> = r.events().into_iter().filter(|e| e["kind"] == "pool_refresh").collect();
    assert_eq!(ev.len(), 3);
    let pn: Vec<(Level, String)> = notes.iter().filter(|n| n.kind == "pool_refresh").map(|n| (n.level, n.subject.clone())).collect();
    assert_eq!(pn, [(Level::Info, "c-p2".to_string()), (Level::Warn, "c-p3".to_string()), (Level::Warn, "c-p4".to_string())]);
    let t = notes.iter().find(|n| n.kind == "pool_refresh").unwrap();
    assert!(t.text.contains("pool refresh for c-p2: +2 added, -1 dropped") && t.text.contains("BINDER (2)"), "{}", t.text);
    let changed: Vec<String> = c["data_files_changed"].as_array().unwrap().iter().map(|x| x["path"].as_str().unwrap().to_string()).collect();
    assert_eq!(changed, [other.display().to_string()], "the seed list may change; the registry may not");
}

/// WP-22: a refresh that wrote no report, or one whose list does not hash as its report says, is not used; a segment
/// that ends before its refresh's lead time leaves the next one on the previous list (with why); the refresh off, the
/// segments run the config's list (no --pools-csv)
#[test]
fn wp22_an_unusable_refresh_keeps_the_previous_list() {
    let mut r = rig("wp22b", Mode::Shadow, 2.0, vec![script(30, 0, "deadline", |_, _| {}), script(10, 0, "deadline", |_, _| {}), script(30, 0, "deadline", |_, _| {})]);
    r.camp.segment_min = 30.0;
    r.camp.max_segments = Some(3);
    let seed = r.root.join("seed.csv");
    std::fs::write(&seed, format!("venue,pool,source\nDLMM,{},mriya\n", crate::tx::b58(&[1; 32]))).unwrap();
    r.camp.seed_csv = seed;
    r.camp.refresh = Some(crate::config::PoolRefreshCfg { enabled: true, lead_s: 300, timeout_s: 240, ..Default::default() });
    r.runner.refreshes = vec![RefreshEnd::NoReport(20)].into();
    let _ = r.run();
    let c = r.json("campaign.json");
    let pl = c["pool_lists"].as_array().unwrap();
    assert_eq!(pl.iter().map(|x| x["source"].as_str().unwrap()).collect::<Vec<_>>(), ["config", "previous", "previous"]);
    assert!(pl[1]["reason"].as_str().unwrap().contains("wrote no report"), "{}", pl[1]);
    assert!(pl[2]["reason"].as_str().unwrap().contains("no refresh ran"), "p2 ended after 10 min, before its lead time: {}", pl[2]);
    assert_eq!(r.runner.jobs.len(), 1);
    // off: no list of its own
    let mut r = rig("wp22c", Mode::Shadow, 1.0, vec![script(60, 0, "deadline", |_, _| {})]);
    r.run();
    assert_eq!(r.runner.specs[0].pools_csv, None);
    assert!(r.json("campaign.json").get("pool_lists").is_none());
}

/// a WP-22 campaign rig: 30-minute segments, the refresh on (lead 300 s, timeout 240 s), a one-pool seed list
fn wp22_rig(tag: &str, hours: f64, scripts: Vec<Script>, refreshes: Vec<RefreshEnd>) -> Rig {
    let mut r = rig(tag, Mode::Shadow, hours, scripts);
    r.camp.segment_min = 30.0;
    let seed = r.root.join("seed.csv");
    std::fs::write(&seed, format!("venue,pool,source\nDLMM,{},mriya\n", crate::tx::b58(&[1; 32]))).unwrap();
    r.camp.seed_csv = seed;
    r.camp.refresh = Some(crate::config::PoolRefreshCfg { enabled: true, lead_s: 300, timeout_s: 240, ..Default::default() });
    r.runner.refreshes = refreshes.into();
    r
}

/// Review #4: every way a refresh can fail leaves the next segment on a checked copy of the previous list, with why: a
/// list that does not hash as its report says, a report for another segment, a refresh that cannot start, one that
/// crashes (exit 101, a fragment of a staging file, no report). The file a segment boots from is only ever the
/// campaign's copy
#[test]
fn wp22_failed_refreshes_leave_the_previous_list() {
    let scripts: Vec<Script> = (0..5).map(|_| script(30, 0, "deadline", |_, _| {})).collect();
    let mut r = wp22_rig("wp22f", 2.5, scripts, vec![RefreshEnd::BadHash(60), RefreshEnd::WrongSegment(60), RefreshEnd::NoStart, RefreshEnd::Crash(60)]);
    let (why, notes) = notify::capture(|| r.run());
    assert_eq!(why, "time up");
    assert_eq!(r.runner.specs.len(), 5);
    let c = r.json("campaign.json");
    let pl = c["pool_lists"].as_array().unwrap();
    assert_eq!(pl.iter().map(|x| x["source"].as_str().unwrap()).collect::<Vec<_>>(), ["config", "previous", "previous", "previous", "previous"]);
    let reason = |i: usize| pl[i]["reason"].as_str().unwrap().to_string();
    assert!(reason(1).contains("the refreshed list does not check") && reason(1).contains("is not the report's"), "{}", reason(1));
    assert!(reason(2).contains("the report is for c-p99"), "{}", reason(2));
    assert!(reason(3).contains("the refresh could not start: fork"), "{}", reason(3));
    assert!(reason(4).contains("the refresh wrote no report (exit Some(101)"), "{}", reason(4));
    let first = std::fs::read(r.camp.dir.join("pools-c-p1.csv")).unwrap();
    for i in 2..=5 { assert_eq!(std::fs::read(r.camp.dir.join(format!("pools-c-p{i}.csv"))).unwrap(), first, "p{i} boots on the previous list"); }
    assert_eq!(std::fs::read_to_string(r.camp.dir.join("pools-c-p5.refresh.csv")).unwrap(), "venue,pool,sou", "the crash left only its staging file");
    assert_eq!(notes.iter().filter(|n| n.kind == "pool_refresh" && n.level == Level::Warn).count(), 4);
}

/// Review #6 and #4: a refresh killed past its timeout that still writes afterwards touches only its staging file (the
/// segment boots on the campaign's copy of the previous list); a refresh still running when the campaign ends (here a
/// stop file during p2, after p3's refresh started) is killed by finish()
#[test]
fn wp22_a_killed_refresh_never_touches_the_boot_file_and_the_end_kills_one() {
    let mut s2 = script(30, 0, "deadline", |_, _| {});
    s2.drop_file = Some((26, "stop"));
    let mut r = wp22_rig("wp22k", 2.0, vec![script(30, 0, "deadline", |_, _| {}), s2], vec![RefreshEnd::HangLateWriter, RefreshEnd::Hang]);
    let why = r.run();
    assert!(why.starts_with("stop file"), "{why}");
    let dir = r.camp.dir.clone();
    assert_eq!(std::fs::read(dir.join("pools-c-p2.csv")).unwrap(), std::fs::read(dir.join("pools-c-p1.csv")).unwrap(), "p2: the previous list, not the late write");
    assert!(std::fs::read_to_string(dir.join("pools-c-p2.refresh.csv")).unwrap().contains("late"), "the late write landed in the staging file only");
    let c = r.json("campaign.json");
    assert!(c["pool_lists"][1]["reason"].as_str().unwrap().contains("did not finish in time"), "{}", c["pool_lists"][1]);
    let kills: Vec<(String, i32, u64)> = r.runner.signals.borrow().iter().filter(|x| x.0.starts_with("refresh")).cloned().collect();
    assert_eq!(kills.iter().map(|x| (x.0.as_str(), x.1)).collect::<Vec<_>>(), [("refresh c-p2", libc::SIGKILL), ("refresh c-p3", libc::SIGKILL)]);
    let p3_job = r.runner.jobs[1].1;
    assert!(kills[1].2 > p3_job && (kills[1].2 - p3_job) / 1_000_000_000 < 240, "c-p3's refresh: killed by the campaign's end, before its own timeout");
}

/// Review #11 and #5: after a crash the boundary does not wait for the refresh (it is killed at once); a segment that
/// crashed on a refreshed list sends the next one to the last list a segment ran on without crashing; and a stop that
/// arrives during the boundary (here with that kill) starts no further segment
#[test]
fn wp22_a_crash_and_a_stop_at_the_boundary() {
    let scripts = vec![script(30, 0, "deadline", |_, _| {}), script(27, 1, "panic", |_, _| {}), script(30, 0, "deadline", |_, _| {})];
    let mut r = wp22_rig("wp22c", 2.0, scripts, vec![RefreshEnd::Ok(60, vec![1, 2, 3]), RefreshEnd::Hang]);
    r.runner.stop_on_kill = Some(r.camp.stop.clone());
    let why = r.run();
    assert_eq!(why, "signal: the supervisor was asked to stop");
    assert_eq!(r.runner.specs.len(), 2, "no segment starts after a stop at the boundary");
    let log = r.log.borrow().clone();
    let crash_exit = log.iter().filter(|x| x.0 == "exited").nth(1).unwrap().2;
    let kills: Vec<(String, i32, u64)> = r.runner.signals.borrow().iter().filter(|x| x.0.starts_with("refresh")).cloned().collect();
    assert_eq!((kills[0].0.as_str(), kills[0].1), ("refresh c-p3", libc::SIGKILL));
    assert!(kills[0].2 - crash_exit <= 11_000_000_000, "killed at once after the crash (the 10 s backoff only), not after a 45 s wait");
    let c = r.json("campaign.json");
    let pl = c["pool_lists"].as_array().unwrap();
    assert_eq!(pl.iter().map(|x| x["source"].as_str().unwrap()).collect::<Vec<_>>(), ["config", "refresh", "last_good"]);
    assert!(pl[2]["reason"].as_str().unwrap().contains("crashed on its refreshed list"), "{}", pl[2]);
    assert_eq!(std::fs::read(r.camp.dir.join("pools-c-p3.csv")).unwrap(), std::fs::read(r.camp.dir.join("pools-c-p1.csv")).unwrap(), "p3's list is p1's");
}

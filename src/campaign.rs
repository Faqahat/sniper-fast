//! The campaign supervisor, `arbx campaign` (PLAN WP-07 item 8 and OD-7; the owner's rule: Cherry gets only the binary,
//! its config and its data, never scripts, so the supervisor is a subcommand of the binary). On the server it replaces
//! deploy/run-w.sh, which stays for local use.
//!
//! - **Frozen per campaign.** `<runs>/<name>/` gets a copy of this binary (`arbx-<sha8>`, mode 0555) and of the config
//!   (`config.frozen.toml`, 0444); every segment runs those copies, so a binary or config changed mid-campaign changes
//!   nothing. `check.out` and `provenance.json` are the frozen binary's `arbx check` and `arbx provenance --offline`. The
//!   data files the config names are hashed into campaign.json `data_files` (review WP-07 #16), and each segment's start
//!   checks them again: a file changed mid-campaign is an event and a Warn notice.
//! - **Segments back to back**, `<name>-p<i>`, each `arbx run --campaign-dir` for at most `--segment-min`, until
//!   `--hours` are up (or `--max-segments`). A segment starts only after the previous one's process has exited (its
//!   exit status reaped: PLAN-ADDENDUM I-3, Haan grants its streams to the first process) and nothing else holds the
//!   provider (no live segment socket, no other `arbx … run` or `arb-lab … run` process: `probe::busy`).
//! - **Money between segments** (src/ledger.rs `history`, the code the segments use): the campaign's start is read from
//!   the chain (its first segment's first balance snapshot): SOL + WSOL lamports, every token's amount and the rent apart,
//!   recorded with its components in campaign.json `equity`. The stops measure the **net spend** since the start (fees,
//!   tips, non-recoverable rent, trading loss: review WP-07 #4; the owner's transfers are recorded as `owner_transfer`
//!   and move nothing); each segment gets what is left of the test budget (`--budget-left`) and, once the start is known,
//!   the floor (`--equity-floor`, on the stop value: the start less the net spend). Before each segment the campaign-wide
//!   stops are checked again (a landing after a segment ended, a stop the segment could not see): `equity_floor`,
//!   `token_floor`, `equity_hour`, `equity_day` end the campaign. A reconciliation miss in any segment makes every later
//!   segment record only (`--shadow`). spend.json carries BUDGET.md's numbers.
//! - **The owner's cumulative budget** (review WP-07 #5, src/budget.rs): a sending campaign takes its allotment from
//!   `<runs>/budget-state.json` (refused when nothing is left of the 34,000,000-lamport hard cap; the smaller of what it
//!   asks and what is left), records its spend there after every segment, and makes it final at its end.
//! - **Ends:** time up, max segments, the stop file, the supervisor's SIGINT / SIGTERM (the running segment is stopped
//!   first), a safety stop of a segment (exit 20: an equity stop or the disk budget), more than 6 crashes within 15
//!   minutes, the disk under `[record] min_free_gb`, the test budget spent, the provider still busy.
//! - **Controls** (files in `<runs>`, a reason inside, logged in the campaign's control.jsonl): `<name>.pause` (the
//!   running segment pauses sending through its control socket; segments that start meanwhile record only; when the
//!   file goes, sending resumes, or a records-only segment is restarted), `<name>.next` (restart now), `<name>.stop` (end).
//!   A stop not obeyed gets SIGINT after 60 s and SIGKILL after 180 s.
//! - **Records:** campaign.json (`arbx.campaign/1.1`), events.jsonl (the campaign's events, each also a
//!   [`crate::notify`] notice), supervisor.jsonl and supervisor.log, control.jsonl, spend.json, `<segment>.out`.
//! - **Passphrase** (a `wallet_keystore` file and a sending mode): asked once, checked against the wallet, kept in one
//!   mlock'd page of this process (`wallet::Pass`: read with read(2), wiped when it goes, locked again after `--detach`'s
//!   fork; review WP-07 #15) and handed to each sending segment over a pipe; never argv, the environment or a file. The
//!   owner's profile keystore (`wallet_keystore = ""`, the frz wallet) needs none.
use crate::config::{self, Config};
use crate::control;
use crate::feeds::clock::now_ns;
use crate::ledger::{self, History};
use crate::notify::{self, Level};
use crate::supervisor::{self, Limits, DAY_NS, HOUR_NS};
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Duration;

pub const SCHEMA: &str = "arbx.campaign/1.1";
/// more crashes than this within 15 minutes end the campaign
pub const CRASH_LIMIT: usize = 6;
/// a segment shorter than this is not started (the time is up)
const MIN_SEGMENT_MIN: f64 = 2.0;
/// what the stop basis is, in campaign.json and the equity events (STAGE1-PLAN review F6)
pub const BASIS: &str = "net_spend: the stops measure the net spend since the campaign's start (fees + tips + non-recoverable rent - the routes' trading result; the owner's transfers are not in it) against the start's SOL + WSOL (lamports); every non-SOL token a quantity floor moved by routes only; recoverable rent apart";

/// What every segment does
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode { Shadow, DryRun, Canary, Live }

impl Mode {
    pub fn parse(s: &str) -> Option<Mode> {
        Some(match s { "shadow" => Mode::Shadow, "dry-run" | "dry_run" => Mode::DryRun, "canary" => Mode::Canary, "live" => Mode::Live, _ => return None })
    }
    pub fn as_str(self) -> &'static str { match self { Mode::Shadow => "shadow", Mode::DryRun => "dry_run", Mode::Canary => "canary", Mode::Live => "live" } }
    pub fn sends(self) -> bool { matches!(self, Mode::Canary | Mode::Live) }
    /// its `arbx run` flag
    pub fn flag(self) -> Option<&'static str> { match self { Mode::Shadow => None, Mode::DryRun => Some("--dry-run"), Mode::Canary => Some("--canary"), Mode::Live => Some("--live") } }
}

/// `arbx campaign`'s options
pub struct Opts {
    pub name: String,
    pub config: PathBuf,
    pub hours: f64,
    pub segment_min: f64,
    pub mode: String,
    pub test_budget: Option<u64>,
    pub who: Option<String>,
    pub runs: Option<PathBuf>,
    pub max_segments: Option<u32>,
    pub env_file: Option<PathBuf>,
    pub drain_s: u64,
    /// skip the provider-busy checks (I-3): the operator knows nothing else holds it
    pub force: bool,
    pub poll: Duration,
    pub backoff: Duration,
}

/// One segment to start: its name, length, flag (`--canary`, `--live`, `--dry-run`, or `--shadow` when it records
/// only), what is left of the test budget, the floor, and why it records only
#[derive(Clone, Debug, PartialEq)]
pub struct Spec { pub index: u32, pub name: String, pub dir: PathBuf, pub minutes: f64, pub flag: Option<&'static str>, pub budget_left: Option<u64>,
    pub equity_floor: Option<i64>, pub why_shadow: Option<String> }

/// A running segment's process
pub trait Child {
    fn pid(&self) -> u32;
    /// its exit code once it has exited and been reaped (128 + the signal for a signal); None while it runs
    fn try_wait(&mut self) -> Result<Option<i32>>;
    fn signal(&mut self, sig: i32);
}

/// What starts and drives segments (the real one runs the campaign's frozen binary; tests give their own)
pub trait Runner {
    fn start(&mut self, spec: &Spec) -> Result<Box<dyn Child>>;
    /// a control command to the running segment through its socket (`arbx ctl`)
    fn ctl(&mut self, spec: &Spec, cmd: &str, why: &str) -> Result<Value>;
    /// what else may hold the provider now (a live segment socket, an `arbx … run` process); empty: nothing
    fn busy(&self) -> Vec<String>;
    /// free space of the runs filesystem, GB
    fn free_gb(&self) -> Option<f64>;
}

/// time and waiting (tests advance their own)
pub trait Clock { fn now_ns(&self) -> u64; fn sleep(&self, d: Duration); }
pub struct RealClock;
impl Clock for RealClock {
    fn now_ns(&self) -> u64 { now_ns() }
    fn sleep(&self, d: Duration) { std::thread::sleep(d) }
}

/// a real process (the segments; the tests' `sh` children)
pub struct ProcChild(pub std::process::Child);
impl Child for ProcChild {
    fn pid(&self) -> u32 { self.0.id() }
    fn try_wait(&mut self) -> Result<Option<i32>> {
        use std::os::unix::process::ExitStatusExt;
        Ok(self.0.try_wait()?.map(|s| s.code().unwrap_or_else(|| 128 + s.signal().unwrap_or(0))))
    }
    fn signal(&mut self, sig: i32) { unsafe { libc::kill(self.0.id() as i32, sig); } }
}

/// The real runner: `<frozen binary> run --config <frozen config> ...`, stdout and stderr into `<campaign>/<segment>.out`
/// (`force`: the operator's `--force`, no provider-busy check). `pass`: the passphrase, held for the campaign's life in
/// one mlock'd page and wiped when it goes (`wallet::Pass`; review WP-07 #15)
pub struct ProcessRunner { pub bin: PathBuf, pub config: PathBuf, pub dir: PathBuf, pub runs: PathBuf, pub env_file: PathBuf, pub drain_s: u64,
    pub pass: Option<crate::wallet::Pass>, pub force: bool }

impl ProcessRunner {
    /// `arbx run`'s arguments for a segment
    pub fn args(&self, s: &Spec) -> Vec<String> {
        let mut a: Vec<String> = ["run", "--config"].iter().map(|x| x.to_string()).collect();
        a.push(self.config.display().to_string());
        a.extend(["--minutes".to_string(), format!("{}", s.minutes), "--name".into(), s.name.clone(), "--campaign-dir".into(), self.dir.display().to_string(),
            "--env-file".into(), self.env_file.display().to_string(), "--drain-s".into(), self.drain_s.to_string()]);
        if let Some(b) = s.budget_left { a.extend(["--budget-left".to_string(), b.to_string()]); }
        if let Some(f) = s.equity_floor { a.extend(["--equity-floor".to_string(), f.to_string()]); }
        if let Some(f) = s.flag { a.push(f.to_string()); }
        a
    }
}

impl Runner for ProcessRunner {
    fn start(&mut self, s: &Spec) -> Result<Box<dyn Child>> {
        let out = std::fs::File::create(self.dir.join(format!("{}.out", s.name))).context("the segment's .out")?;
        let mut cmd = std::process::Command::new(&self.bin);
        cmd.args(self.args(s)).stdout(out.try_clone()?).stderr(out);
        let sends = matches!(s.flag, Some("--canary") | Some("--live"));
        cmd.stdin(if sends && self.pass.is_some() { std::process::Stdio::piped() } else { std::process::Stdio::null() });
        let mut child = cmd.spawn().with_context(|| format!("starting {}", self.bin.display()))?;
        if let (true, Some(p), Some(mut stdin)) = (sends, &self.pass, child.stdin.take()) {
            use std::io::Write;
            let _ = stdin.write_all(p.as_bytes()).and_then(|_| stdin.write_all(b"\n"));
        }
        Ok(Box::new(ProcChild(child)))
    }
    fn ctl(&mut self, s: &Spec, cmd: &str, why: &str) -> Result<Value> { control::send_command(&s.dir, cmd, "supervisor", why) }
    fn busy(&self) -> Vec<String> { if self.force { Vec::new() } else { crate::probe::busy(&self.runs, true) } }
    fn free_gb(&self) -> Option<f64> { free_gb(&self.runs) }
}

/// free space of the filesystem holding `p`, GB
pub fn free_gb(p: &Path) -> Option<f64> {
    use std::os::unix::ffi::OsStrExt;
    let c = std::ffi::CString::new(p.as_os_str().as_bytes()).ok()?;
    let mut st: libc::statvfs = unsafe { std::mem::zeroed() };
    (unsafe { libc::statvfs(c.as_ptr(), &mut st) } == 0).then(|| st.f_bavail as f64 * st.f_frsize as f64 / 1e9)
}

/// How a segment ended, from its stop.json and exit code (MEASUREMENT §4.1 `class`): `natural` (deadline), `operator`
/// (signal, control), `safety` (exit 20: an equity stop, the disk budget), `crash` (anything else: an error, a panic, a
/// failure while stopping, no stop.json, a kill)
pub fn classify(seg_dir: &Path, rc: i32) -> (&'static str, Option<String>) {
    let st: Option<Value> = std::fs::read(seg_dir.join("stop.json")).ok().and_then(|b| serde_json::from_slice(&b).ok());
    let reason = st.as_ref().and_then(|s| s["reason"].as_str()).map(String::from);
    let secondary = st.as_ref().is_some_and(|s| !s["secondary"].is_null());
    let safety = reason.as_deref().and_then(control::StopReason::parse).is_some_and(|r| r.exit_code() == 20);
    let class = if rc == 20 || safety { "safety" }
        else if ![0, 10, 20, 30].contains(&rc) || reason.is_none() || secondary { "crash" }
        else { match reason.as_deref() { Some("deadline") => "natural", Some("signal" | "control") => "operator", _ => "crash" } };
    (class, reason)
}

/// `YYYY-MM-DDTHH:MM:SSZ`
pub fn iso(t_ns: u64) -> String {
    let s = t_ns / 1_000_000_000 % 86_400;
    format!("{}T{:02}:{:02}:{:02}Z", crate::ledger::utc_date(t_ns), s / 3600, s % 3600 / 60, s % 60)
}

/// the first line of a control file (its reason)
fn reason_of(p: &Path) -> String {
    let t = std::fs::read(p).ok().map(|b| String::from_utf8_lossy(&b[..b.len().min(500)]).lines().next().unwrap_or("").trim().to_string()).unwrap_or_default();
    if t.is_empty() { "(no reason given)".into() } else { t }
}
fn owner_of(p: &Path) -> String {
    use std::os::unix::fs::MetadataExt;
    std::fs::metadata(p).map(|m| format!("uid {}", m.uid())).unwrap_or_else(|_| "?".into())
}

/// The campaign: its directory, its plan, its state (campaign.json), its stop flag (the supervisor's own SIGINT and
/// SIGTERM)
pub struct Campaign {
    pub dir: PathBuf,
    pub runs: PathBuf,
    pub name: String,
    pub mode: Mode,
    /// the config's own mode is live: a records-only segment needs `--shadow` even in a shadow campaign
    pub config_live: bool,
    pub hours: f64,
    pub segment_min: f64,
    pub test_budget: Option<u64>,
    pub max_segments: Option<u32>,
    pub limits: Limits,
    pub min_free_gb: f64,
    pub poll: Duration,
    pub stop_int_s: u64,
    pub stop_kill_s: u64,
    pub backoff: Duration,
    pub busy_wait_s: u64,
    pub stop: Arc<AtomicBool>,
    pub state: Value,
    /// print the log lines too (not when detached: stdout is the log)
    pub echo: bool,
    /// a segment whose exit could not be waited for (the campaign ends: none may start beside it)
    pub unreaped: Option<String>,
}

impl Campaign {
    /// a campaign in `dir` (its state starts as campaign.json's first version)
    #[allow(clippy::too_many_arguments)]
    pub fn new(dir: PathBuf, runs: PathBuf, name: &str, mode: Mode, hours: f64, segment_min: f64, test_budget: Option<u64>, cfg: &Config) -> Campaign {
        let mut limits = Limits::from_cfg(&cfg.supervisor);
        limits.floor = None;
        let state = json!({ "schema": SCHEMA, "name": name, "started_ns": now_ns(), "ended_ns": null, "operator": null, "supervisor": "arbx campaign",
            "mode": mode.as_str(), "hours": hours, "segment_min": segment_min, "binary": null, "config": null,
            "budget": { "test_budget_lamports": test_budget, "hard_cap_lamports": config::TEST_BUDGET_HARD_CAP, "max_drop_per_hour_sol": cfg.supervisor.max_drop_per_hour_sol,
                "equity_drop_day_sol": cfg.supervisor.max_drop_per_day_sol, "token_floor_tolerance": cfg.supervisor.token_floor_tolerance, "failed_fee_budget_lamports": null },
            "equity": { "basis": BASIS, "start": null, "floor_lamports": null, "token_floors": {}, "now": null, "net_spend": null, "budget_left": test_budget },
            "segments": [], "crash_count_15min": 0, "records_only_why": null, "end_reason": null });
        Campaign { dir, runs, name: name.to_string(), mode, config_live: cfg.mode == "live", hours, segment_min, test_budget, max_segments: None, limits,
            min_free_gb: cfg.record.min_free_gb, poll: Duration::from_secs(2), stop_int_s: 60, stop_kill_s: 180, backoff: Duration::from_secs(10), busy_wait_s: 120,
            stop: Arc::new(AtomicBool::new(false)), state, echo: true, unreaped: None }
    }

    fn file(&self, ext: &str) -> PathBuf { self.runs.join(format!("{}.{ext}", self.name)) }

    /// supervisor.log (and stdout unless detached)
    pub fn say(&self, msg: &str) {
        let line = format!("{} {msg}", iso(now_ns()));
        control::append_line(&self.dir.join("supervisor.log"), &format!("{} {line}", now_ns()));
        if self.echo { println!("{line}"); }
    }

    /// the campaign's events.jsonl (`subsystem` `campaign`) and, with a level, a notice for the alert hook
    pub fn event(&self, kind: &'static str, level: Option<Level>, text: &str, detail: Value) {
        control::append_line(&self.dir.join("events.jsonl"), &json!({ "t_ns": now_ns(), "kind": kind, "subsystem": "campaign", "feed": null, "detail": detail }).to_string());
        if let Some(l) = level { notify::notify(notify::now(l, kind, "campaign", self.name.clone(), format!("campaign {}: {text}", self.name), detail)); }
    }

    /// supervisor.jsonl (MEASUREMENT §4.7; `budget_src` `ledger`)
    fn sj(&self, event: &str, segment: &str, detail: &str) {
        let left = self.state["equity"]["budget_left"].clone();
        control::append_line(&self.dir.join("supervisor.jsonl"), &json!({ "t_ns": now_ns(), "event": event, "segment": segment, "budget_left_lamports": left,
            "budget_src": "ledger", "free_gb": null, "detail": detail }).to_string());
    }

    /// the campaign's control.jsonl (`src` `file`)
    fn cj(&self, who: &str, cmd: &str, why: &str, accepted: bool, result: &str) {
        control::log_control(&self.dir, "file", who, cmd, why, accepted, result);
    }

    /// campaign.json, atomically
    pub fn save(&self) { let _ = control::write_atomic(&self.dir.join("campaign.json"), format!("{}\n", serde_json::to_string_pretty(&self.state).unwrap_or_default()).as_bytes()); }

    /// The campaign's money now (every segment's files): campaign.json `equity` (the start with its components once
    /// known, the floor, the token floors, now, the spend, what is left) and spend.json. Returns the history
    pub fn update_equity(&mut self, now: u64) -> History {
        let h = ledger::history(&self.dir, None, now, DAY_NS + HOUR_NS);
        let first = self.state["equity"]["start"].is_null() && h.start.is_some();
        let floor = h.start.as_ref().zip(self.test_budget).map(|(s, b)| s.equity_stop - b as i64);
        let mut lim = self.limits.clone();
        if let Some(s) = &h.start { lim.set_token_floors(&s.tokens); }
        // what is left of the test budget: the budget less the net spend (the owner's transfers move nothing)
        let left = self.test_budget.map(|b| (b as i64 - h.spent).max(0));
        self.state["equity"] = json!({ "basis": BASIS, "start": h.start.as_ref().map(ledger::Start::json), "floor_lamports": floor,
            "token_floors": lim.token_floors.iter().map(|(m, a)| (m.clone(), json!(a.to_string()))).collect::<serde_json::Map<_, _>>(),
            "now": { "t_ns": now, "stop_value": h.stop_value_now(), "equity_stop": h.equity_stop_now, "equity_total": h.equity_total_now,
                "tokens": h.tokens_now.iter().map(|(m, a)| (m.clone(), json!(a.to_string()))).collect::<serde_json::Map<_, _>>(),
                "stop_tokens": h.stop_tokens_now().iter().map(|(m, a)| (m.clone(), json!(a.to_string()))).collect::<serde_json::Map<_, _>>(),
                "drop_1h": h.series.drop_over(now, HOUR_NS), "drop_24h": h.series.drop_over(now, DAY_NS) },
            "net_spend": h.spent, "budget_left": left, "owner_transfers": h.owner_transfers.len(), "segments_read": h.segments_read, "recon_misses": h.recon_misses.len(),
            "recon_undecided": h.undecided.as_ref().map(|(s, t)| json!({ "segment": s, "t_ns": t })), "unreadable_lines": h.bad_lines });
        self.save();
        // the owner's cumulative budget (review WP-07 #5): this campaign's spend so far
        if self.mode.sends() && self.state["budget_state"].is_object() {
            if let Err(e) = crate::budget::update(&self.runs, &self.name, h.spent, false, now) { self.say(&format!("WARNING: the budget state was not updated: {e:#}")); }
        }
        let spend = ledger::spend_json(&self.dir, &self.name, now);
        let _ = control::write_atomic(&self.dir.join("spend.json"), format!("{}\n", serde_json::to_string_pretty(&spend).unwrap_or_default()).as_bytes());
        if first {
            let s = &self.state["equity"]["start"];
            self.say(&format!("equity: the campaign's start read from the chain (segment {}): SOL + WSOL {} lamports (sol {}, wsol {}), recoverable rent {} apart, tokens {}; floor {}",
                s["segment"].as_str().unwrap_or("?"), s["equity_stop"], s["sol"], s["wsol"], s["rent_recoverable"], s["tokens"], floor.map_or("none (no test budget)".into(), |f| f.to_string())));
            self.event("equity_start", Some(Level::Info), "starting equity read from the chain", json!({ "basis": BASIS, "start": s.clone(), "floor_lamports": floor,
                "token_floors": self.state["equity"]["token_floors"].clone() }));
        }
        h
    }

    /// the data files hashed at the start, hashed again (before each segment): one that changed is an event
    /// (`data_files_changed`) and a Warn notice, once per file
    fn check_data_files(&mut self) {
        let Some(m) = self.state["data_files"].as_object().cloned() else { return };
        for (p, h) in m {
            let now = std::fs::read(&p).ok().map(|b| json!(crate::provenance::sha256_hex(&b))).unwrap_or(Value::Null);
            let seen = self.state["data_files_changed"].as_array().is_some_and(|a| a.iter().any(|x| x["path"] == json!(p)));
            if now != h && !seen {
                let d = json!({ "path": p, "sha256_at_start": h, "sha256_now": now });
                if let Some(a) = self.state["data_files_changed"].as_array_mut() { a.push(d.clone()); } else { self.state["data_files_changed"] = json!([d.clone()]); }
                self.say(&format!("WARNING: data file {p} changed since the campaign started: the next segments read the new one"));
                self.event("data_files_changed", Some(Level::Warn), &format!("data file {p} changed mid-campaign"), d);
            }
        }
    }

    /// the campaign-wide stops on the history (between segments): the same rules the segments apply, on the same basis
    /// (the stop value: the start less the net spend; the start's tokens moved by routes)
    pub fn equity_check(&self, h: &History, now: u64) -> Option<supervisor::Hit> {
        let v = h.stop_value_now()?;
        let mut l = self.limits.clone();
        l.floor = h.start.as_ref().zip(self.test_budget).map(|(s, b)| s.equity_stop - b as i64);
        if let Some(s) = &h.start { l.set_token_floors(&s.tokens); }
        supervisor::check(&l, now, &h.series, v, &h.stop_tokens_now())
    }

    /// Run the campaign: segments back to back until it ends. Returns why it ended (campaign.json `end_reason`)
    pub fn run(&mut self, runner: &mut dyn Runner, clock: &dyn Clock) -> String {
        let t0 = clock.now_ns();
        let t_end = t0 + (self.hours * 3_600e9) as u64;
        self.state["started_ns"] = json!(t0);
        self.save();
        self.say(&format!("start {}: {} h in {}-min segments, mode {}, test budget {:?} lamports, binary {}", self.name, self.hours, self.segment_min, self.mode.as_str(),
            self.test_budget, self.state["binary"]["path"].as_str().unwrap_or("?")));
        self.sj("start", "", &format!("hours={} segment_min={} mode={}", self.hours, self.segment_min, self.mode.as_str()));
        self.event("campaign_start", Some(Level::Info), &format!("started: {} h, {} segments of {} min, mode {}", self.hours, (self.hours * 60.0 / self.segment_min).ceil(),
            self.segment_min, self.mode.as_str()), json!({ "mode": self.mode.as_str(), "hours": self.hours, "segment_min": self.segment_min, "test_budget_lamports": self.test_budget }));
        let mut i = 0u32;
        let mut crashes: Vec<u64> = Vec::new();
        let mut paused_logged = false;
        let why = loop {
            let now = clock.now_ns();
            if self.stop.load(Ordering::Relaxed) { break "signal: the supervisor was asked to stop".to_string(); }
            if now >= t_end { break "time up".into(); }
            if self.max_segments.is_some_and(|m| i >= m) { break format!("max segments ({})", i); }
            if self.file("stop").exists() {
                let w = reason_of(&self.file("stop"));
                self.cj(&owner_of(&self.file("stop")), "stop", &w, true, "campaign ends");
                break format!("stop file: {w}");
            }
            if let Some(f) = runner.free_gb().filter(|f| *f < self.min_free_gb) { break format!("disk low ({f:.1} GB < {} GB)", self.min_free_gb); }
            self.check_data_files();
            // the money so far, and the campaign-wide stops (a campaign that sends)
            let h = self.update_equity(now);
            if let Some(hit) = self.equity_check(&h, now).filter(|_| self.mode.sends()) {
                let name = hit.rule.as_str();
                self.event(name, Some(Level::Critical), &format!("{}: no further segment", hit.detail), json!({ "rule": name, "detail": hit.detail, "data": hit.data, "between_segments": true }));
                break format!("safety stop between segments ({name}: {})", hit.detail);
            }
            if self.mode.sends() && self.state["equity"]["budget_left"].as_i64().is_some_and(|l| l <= 0) { break "the test budget is spent".into(); }
            if self.state["records_only_why"].is_null() {
                if let Some((seg, _)) = h.recon_misses.first() {
                    let w = format!("reconciliation miss in {seg}");
                    self.state["records_only_why"] = json!(w);
                    self.say(&format!("{w}: every later segment records only (--shadow)"));
                    self.event("campaign_shadow", Some(Level::Error), &format!("{w}: later segments record only"), json!({ "why": w }));
                }
            }
            // the segment's flag: the mode's, or --shadow when it records only
            let pause = self.file("pause").exists();
            if pause && !paused_logged {
                paused_logged = true;
                let w = reason_of(&self.file("pause"));
                self.say(&format!("paused: {w} (segments record only while the file exists)"));
                self.cj(&owner_of(&self.file("pause")), "pause-sending", &w, true, "segments record only (--shadow) while the file exists");
            } else if !pause && paused_logged { paused_logged = false; self.cj("?", "resume-sending", "pause file removed", true, "segments send again"); }
            let records_only = if pause { Some("paused".to_string()) } else { self.state["records_only_why"].as_str().map(String::from) };
            let flag = match (&records_only, self.mode) {
                (Some(_), m) if m.sends() || self.config_live => Some("--shadow"),
                (Some(_), m) => m.flag(),
                (None, Mode::Shadow) if self.config_live => Some("--shadow"),
                (None, m) => m.flag(),
            };
            let mins = self.segment_min.min((t_end - now) as f64 / 60e9);
            if mins < MIN_SEGMENT_MIN { break "time up".into(); }
            // PLAN-ADDENDUM I-3: nothing else may hold the provider (the previous segment's process has been reaped)
            let mut busy = runner.busy();
            let t_busy = clock.now_ns();
            while !busy.is_empty() && clock.now_ns() < t_busy + self.busy_wait_s * 1_000_000_000 {
                clock.sleep(self.poll);
                busy = runner.busy();
            }
            if !busy.is_empty() { break format!("the provider is busy: {}", busy.join("; ")); }
            i += 1;
            let name = format!("{}-p{i}", self.name);
            let floor = self.state["equity"]["floor_lamports"].as_i64();
            let left = self.state["equity"]["budget_left"].as_i64().map(|l| l.max(0) as u64);
            // what is left of the test budget and the floor go to a segment that may send
            let sends = self.mode.sends();
            let spec = Spec { index: i, name: name.clone(), dir: self.dir.join(&name), minutes: (mins * 100.0).floor() / 100.0, flag,
                budget_left: left.filter(|_| sends), equity_floor: floor.filter(|_| sends), why_shadow: records_only.clone() };
            let t_start = clock.now_ns();
            self.say(&format!("segment {i} ({name}): {} min, {}, budget left {:?}, floor {:?}{}", spec.minutes, flag.unwrap_or("shadow config"), spec.budget_left, floor,
                records_only.as_ref().map(|w| format!(", records only ({w})")).unwrap_or_default()));
            self.sj("segment_start", &name, &format!("minutes={} flag={} budget_left={:?} floor={:?}", spec.minutes, flag.unwrap_or("none"), spec.budget_left, floor));
            self.event("segment_start", None, "", json!({ "segment": name, "minutes": spec.minutes, "flag": flag, "budget_left": spec.budget_left, "equity_floor": floor,
                "records_only": records_only }));
            let mut child = match runner.start(&spec) {
                Ok(c) => c,
                Err(e) => {
                    self.event("segment_start_failed", Some(Level::Error), &format!("{name} did not start: {e:#}"), json!({ "segment": name, "error": format!("{e:#}") }));
                    break format!("segment {name} could not start: {e:#}");
                }
            };
            let pid = child.pid();
            let rc = self.watch(runner, &spec, child.as_mut(), clock);
            let t_exit = clock.now_ns();
            if let Some(w) = self.unreaped.clone() {
                self.event("segment_unreaped", Some(Level::Critical), &w, json!({ "segment": name, "pid": pid }));
                break format!("safety: {w}");
            }
            let (class, reason) = classify(&spec.dir, rc);
            if class == "crash" { crashes.push(t_exit); }
            crashes.retain(|t| t_exit.saturating_sub(*t) < 900_000_000_000);
            let mut seg = json!({ "name": name, "started_ns": t_start, "ended_ns": t_exit, "exit_code": rc, "stop_reason": reason, "class": class, "pid": pid, "flag": flag,
                "budget_left": spec.budget_left, "equity_floor": floor, "records_only": records_only });
            if let Ok(st) = std::fs::read(spec.dir.join("stop.json")).map_err(anyhow::Error::from).and_then(|b| Ok(serde_json::from_slice::<Value>(&b)?)) {
                seg["unsettled"] = st["unsettled"].clone();
                seg["drain_ms"] = st["drain_ms"].clone();
            }
            if let Some(a) = self.state["segments"].as_array_mut() { a.push(seg.clone()); }
            self.state["crash_count_15min"] = json!(crashes.len());
            self.save();
            let dur = t_exit.saturating_sub(t_start) / 1_000_000_000;
            self.say(&format!("segment {i} ended after {dur} s: exit {rc}, stop reason {}, class {class} (crashes in 15 min: {})", reason.as_deref().unwrap_or("none"), crashes.len()));
            self.sj("segment_end", &name, &format!("exit={rc} reason={} class={class} duration_s={dur} crashes_15min={}", reason.as_deref().unwrap_or("none"), crashes.len()));
            let level = match class { "safety" => Some(Level::Critical), "crash" => Some(Level::Error), _ => None };
            self.event("segment_end", level, &format!("segment {name} ended: {} ({class})", reason.as_deref().unwrap_or("no stop reason")), seg);
            if class == "safety" { break format!("safety stop in {name} ({})", reason.as_deref().unwrap_or("exit 20")); }
            if self.stop.load(Ordering::Relaxed) { break "signal: the supervisor was asked to stop".into(); }
            if self.file("stop").exists() { break format!("stop file: {}", reason_of(&self.file("stop"))); }
            if crashes.len() > CRASH_LIMIT { break format!("crash limit: {} crashes in 15 min", crashes.len()); }
            if class == "crash" { clock.sleep(self.backoff); }
        };
        self.finish(&why, clock.now_ns());
        why
    }

    /// The end: campaign.json's end, spend.json, the money's last word, an event
    pub fn finish(&mut self, why: &str, now: u64) {
        let h = self.update_equity(now);
        self.state["ended_ns"] = json!(now);
        self.state["end_reason"] = json!(why);
        self.save();
        if self.mode.sends() && self.state["budget_state"].is_object() {
            match crate::budget::update(&self.runs, &self.name, h.spent, true, now) {
                Ok(()) => self.say(&format!("budget: the campaign spent {} lamports net ({})", h.spent, crate::budget::path(&self.runs).display())),
                Err(e) => self.say(&format!("WARNING: the budget state was not updated: {e:#} (the next start re-reads this campaign's ledgers)")),
            }
        }
        self.sj("stop", "", why);
        self.say(&format!("done: {why}"));
        let safety = why.starts_with("safety") || why.starts_with("crash limit") || why.starts_with("the test budget");
        self.event("campaign_end", Some(if safety { Level::Critical } else { Level::Info }), &format!("ended: {why}"), json!({ "end_reason": why,
            "segments": self.state["segments"].as_array().map_or(0, |a| a.len()), "equity": self.state["equity"].clone() }));
    }

    /// stop the running segment: its control socket, SIGINT when that fails (its stop.json then names this supervisor)
    fn stop_segment(&self, runner: &mut dyn Runner, spec: &Spec, child: &mut dyn Child, why: &str) {
        let ok = runner.ctl(spec, "stop", why).ok().is_some_and(|r| r["accepted"] == json!(true));
        if !ok { child.signal(libc::SIGINT); }
        self.say(&format!("segment {}: stop ({why}){}", spec.name, if ok { "" } else { ": the socket did not answer, SIGINT" }));
    }

    /// Follow a running segment until its process has exited (reaped): the control files, the supervisor's own stop,
    /// the escalation of a stop not obeyed. Returns its exit code
    fn watch(&mut self, runner: &mut dyn Runner, spec: &Spec, child: &mut dyn Child, clock: &dyn Clock) -> i32 {
        let (mut stop_sent, mut int_sent, mut kill_sent, mut gate_logged) = (None::<u64>, false, false, false);
        let (mut seg_paused, mut pause_fails) = (false, 0u32);
        let mut wait_failed: Option<u64> = None;
        let sends = matches!(spec.flag, Some("--canary") | Some("--live"));
        let paused_start = spec.why_shadow.as_deref() == Some("paused");
        loop {
            match child.try_wait() {
                Ok(Some(rc)) => return rc,
                Ok(None) => {}
                // review WP-07 #14: a segment whose exit cannot be waited for is stopped and waited for as at any stop (never
                // left running beside the next one); one that still cannot be reaped ends the campaign
                Err(e) => {
                    let now = clock.now_ns();
                    let t0 = *wait_failed.get_or_insert(now);
                    if now == t0 {
                        self.say(&format!("segment {}: waiting failed: {e:#}: stopping it", spec.name));
                        if stop_sent.is_none() { self.stop_segment(runner, spec, child, "the supervisor cannot wait for this segment"); stop_sent = Some(now); }
                    }
                    if now.saturating_sub(t0) >= (self.stop_kill_s + 60) * 1_000_000_000 {
                        self.unreaped = Some(format!("segment {} could not be reaped: {e:#}", spec.name));
                        return -1;
                    }
                }
            }
            let now = clock.now_ns();
            if !gate_logged {
                if let Some(g) = std::fs::read(spec.dir.join("meta.json")).ok().and_then(|b| serde_json::from_slice::<Value>(&b).ok()).filter(|m| m["partial"] != json!(true))
                    .map(|m| m["send_gate"].clone()).filter(|g| g.is_object()) {
                    gate_logged = true;
                    let (mode, reason) = (g["mode"].as_str().unwrap_or("?").to_string(), g["reason"].as_str().unwrap_or("-").to_string());
                    self.sj("gate", &spec.name, &format!("mode={mode} reason={reason} flag={}", spec.flag.unwrap_or("none")));
                    if sends && mode != "live" {
                        self.say(&format!("WARNING: segment {} runs with {} but is NOT SENDING: send gate {mode} ({reason})", spec.name, spec.flag.unwrap_or("")));
                        self.event("segment_not_sending", Some(Level::Warn), &format!("{} is not sending: gate {mode} ({reason})", spec.name), json!({ "segment": spec.name, "gate": g }));
                    }
                }
            }
            if let Some(ts) = stop_sent {
                let waited = now.saturating_sub(ts) / 1_000_000_000;
                if waited >= self.stop_kill_s && !kill_sent {
                    kill_sent = true;
                    self.say(&format!("segment {}: no exit {} s after the stop: SIGKILL", spec.name, self.stop_kill_s));
                    self.sj("kill", &spec.name, &format!("SIGKILL {}s after the stop", self.stop_kill_s));
                    child.signal(libc::SIGKILL);
                } else if waited >= self.stop_int_s && !int_sent {
                    int_sent = true;
                    self.say(&format!("segment {}: no exit {} s after the stop: SIGINT", spec.name, self.stop_int_s));
                    child.signal(libc::SIGINT);
                }
            } else if self.stop.load(Ordering::Relaxed) {
                self.stop_segment(runner, spec, child, "the campaign supervisor was asked to stop");
                stop_sent = Some(now);
            } else if self.file("stop").exists() {
                let w = reason_of(&self.file("stop"));
                self.stop_segment(runner, spec, child, &format!("campaign stop: {w}"));
                self.cj(&owner_of(&self.file("stop")), "stop", &w, true, &format!("segment {} stopped; the campaign ends", spec.name));
                stop_sent = Some(now);
            } else if self.file("next").exists() {
                let (w, who) = (reason_of(&self.file("next")), owner_of(&self.file("next")));
                let _ = std::fs::remove_file(self.file("next"));
                self.stop_segment(runner, spec, child, &format!("next: {w}"));
                self.cj(&who, "next", &w, true, &format!("segment {} stopped; the next one starts", spec.name));
                self.sj("stop", &spec.name, &format!("next: {w}"));
                stop_sent = Some(now);
            } else {
                let pause = self.file("pause").exists();
                if pause && !seg_paused && !paused_start {
                    let w = reason_of(&self.file("pause"));
                    match runner.ctl(spec, "pause-sending", &format!("pause file: {w}")) {
                        Ok(r) if r["accepted"] == json!(true) => {
                            seg_paused = true;
                            self.say(&format!("segment {}: sending paused", spec.name));
                            self.sj("pause", &spec.name, &w);
                            self.cj(&owner_of(&self.file("pause")), "pause-sending", &w, true, &format!("segment {} paused", spec.name));
                        }
                        r => {
                            pause_fails += 1;
                            let text = match r { Ok(v) => v["result"].as_str().unwrap_or("refused").to_string(), Err(e) => format!("{e:#}") };
                            if pause_fails == 1 {
                                self.say(&format!("segment {}: PAUSE NOT CONFIRMED: {text}", spec.name));
                                self.sj("pause_failed", &spec.name, &text);
                                self.cj(&owner_of(&self.file("pause")), "pause-sending", &w, false, &format!("segment {}: {text}", spec.name));
                            }
                            if !sends { seg_paused = true; }
                            else if pause_fails >= 3 {
                                self.stop_segment(runner, spec, child, "pause not confirmed: restart records-only");
                                self.cj("supervisor", "next", &format!("pause not confirmed after {pause_fails} tries"), true, &format!("segment {} stopped; the next one records only", spec.name));
                                stop_sent = Some(now);
                            }
                        }
                    }
                } else if !pause && seg_paused {
                    seg_paused = false;
                    match runner.ctl(spec, "resume-sending", "pause file removed") {
                        Ok(r) if r["accepted"] == json!(true) => { self.say(&format!("segment {}: sending resumed", spec.name)); self.cj("?", "resume-sending", "pause file removed", true, &format!("segment {} resumed", spec.name)); }
                        r => {
                            let text = match r { Ok(v) => v["result"].as_str().unwrap_or("refused").to_string(), Err(e) => format!("{e:#}") };
                            self.say(&format!("segment {}: resume refused ({text}): it stays as it is", spec.name));
                            self.cj("?", "resume-sending", "pause file removed", false, &format!("segment {}: {text}", spec.name));
                        }
                    }
                } else if !pause && paused_start {
                    // a segment that records only because of the pause: restarted so the next one sends
                    self.stop_segment(runner, spec, child, "pause lifted: restart to send");
                    self.cj("?", "resume-sending", "pause file removed", true, &format!("segment {} (records only) restarted: the next one sends", spec.name));
                    stop_sent = Some(now);
                }
            }
            clock.sleep(self.poll);
        }
    }
}

/// `arbx campaign`: check, lock, freeze, (detach), run. Returns the exit code (0 a natural end, 20 a safety end)
pub fn main(o: Opts, detach: bool) -> Result<i32> {
    if !o.name.bytes().all(|b| b.is_ascii_alphanumeric() || b"_.-".contains(&b)) || o.name.is_empty() { bail!("campaign name: letters, digits, _ . - only"); }
    if !(o.hours > 0.0) || !(o.segment_min >= MIN_SEGMENT_MIN) { bail!("--hours must be > 0 and --segment-min at least {MIN_SEGMENT_MIN}"); }
    let mode = Mode::parse(&o.mode).with_context(|| format!("--mode {}: shadow, dry-run, canary or live", o.mode))?;
    let conf = std::fs::canonicalize(&o.config).with_context(|| format!("{}", o.config.display()))?;
    let (cfg, raw) = Config::load_raw(&conf)?;
    if mode == Mode::Canary && !cfg.canary.enabled { bail!("--mode canary needs [canary] enabled = true in the config"); }
    if mode == Mode::Live && cfg.mode != "live" { bail!("--mode live needs mode = \"live\" in the config"); }
    // the stricter of the operator's allotment and the frozen config's budget (the frz config's is FT-004's allotment)
    let budget = match (o.test_budget, (cfg.supervisor.test_budget_lamports > 0).then_some(cfg.supervisor.test_budget_lamports)) {
        (Some(a), Some(b)) => Some(a.min(b)), (a, b) => a.or(b) };
    if let Some(b) = budget.filter(|b| *b > config::TEST_BUDGET_HARD_CAP) { bail!("test budget {b} is over the owner's hard cap {}", config::TEST_BUDGET_HARD_CAP); }
    if mode.sends() && budget.is_none_or(|b| b == 0) { bail!("a {} campaign needs a test budget (--test-budget-lamports, at most {})", mode.as_str(), config::TEST_BUDGET_HARD_CAP); }
    let runs = o.runs.clone().unwrap_or_else(|| PathBuf::from(&cfg.out_dir));
    std::fs::create_dir_all(&runs).with_context(|| format!("{}", runs.display()))?;
    let dir = runs.join(&o.name);
    if dir.exists() { bail!("campaign {} exists ({}): pick a new name", o.name, dir.display()); }
    // one supervisor at a time on a runs directory; nothing else may hold the provider (I-3)
    let lock = crate::probe::lock_runs(&runs)?;
    if mode.sends() && lock.is_none() { bail!("{}: the campaign lock cannot be taken: a {} campaign refuses to start", runs.display(), mode.as_str()); }
    let busy = crate::probe::busy(&runs, true);
    if !busy.is_empty() && !o.force { bail!("the provider may be in use (Haan serves the first process only, I-3): {}. Start when nothing else runs, or pass --force", busy.join("; ")); }
    // review WP-07 #5: the owner's cumulative budget (refused when nothing is left; the smaller of what is asked and what
    // is left), recorded at once
    let grant = if mode.sends() { Some(crate::budget::begin(&runs, &o.name, "campaign", &dir, mode.as_str(), budget.unwrap_or(0), now_ns())?) } else { None };
    let budget = grant.as_ref().map(|g| g.allotment).or(budget);
    // the passphrase, once (a keystore file and a sending mode; the profile keystore needs none)
    let pass = if mode.sends() && !cfg.wallet_keystore.is_empty() {
        crate::wallet::harden_process();
        let p = crate::wallet::read_pass()?;
        crate::wallet::check_pass(&cfg, p.as_bytes()).context("the passphrase does not unlock the wallet")?;
        Some(p)
    } else { None };
    // frozen: the binary and the config this campaign runs
    std::fs::create_dir_all(&dir)?;
    let exe = std::fs::read("/proc/self/exe").context("reading this binary")?;
    let sha = crate::provenance::sha256_hex(&exe);
    let bin = dir.join(format!("arbx-{}", &sha[..8]));
    std::fs::write(&bin, &exe)?;
    use std::os::unix::fs::PermissionsExt;
    std::fs::set_permissions(&bin, std::fs::Permissions::from_mode(0o555))?;
    let frozen = dir.join("config.frozen.toml");
    std::fs::write(&frozen, &raw)?;
    std::fs::set_permissions(&frozen, std::fs::Permissions::from_mode(0o444))?;
    let check = std::process::Command::new(&bin).args(["check", "--config"]).arg(&frozen).stdin(std::process::Stdio::null()).output()?;
    std::fs::write(dir.join("check.out"), [check.stdout.as_slice(), check.stderr.as_slice()].concat())?;
    if !check.status.success() { bail!("the frozen config does not pass `arbx check`: see {}", dir.join("check.out").display()); }
    let prov = std::process::Command::new(&bin).args(["provenance", "--offline", "--config"]).arg(&frozen).stdin(std::process::Stdio::null()).output()?;
    std::fs::write(dir.join("provenance.json"), &prov.stdout)?;
    let prov_v: Value = serde_json::from_slice(&prov.stdout).unwrap_or(Value::Null);
    let env_file = o.env_file.clone().unwrap_or_else(|| conf.parent().unwrap_or(Path::new(".")).join(".env"));
    let mut c = Campaign::new(dir.clone(), runs.clone(), &o.name, mode, o.hours, o.segment_min, budget, &cfg);
    c.state["budget_state"] = grant.as_ref().map_or(Value::Null, |g| json!({ "file": crate::budget::path(&runs).display().to_string(), "allotment": g.allotment,
        "remaining_before": g.remaining_before, "spent_before": g.spent_before, "hard_cap_lamports": config::TEST_BUDGET_HARD_CAP }));
    c.state["data_files"] = data_files(&cfg);
    c.max_segments = o.max_segments;
    c.poll = o.poll;
    c.backoff = o.backoff;
    c.state["forced"] = json!(o.force);
    if o.force && !busy.is_empty() { c.state["forced_over"] = json!(busy); }
    c.state["operator"] = json!(o.who.clone().or_else(|| std::env::var("SUDO_USER").ok()).or_else(|| std::env::var("USER").ok()));
    c.state["binary"] = json!({ "path": bin.display().to_string(), "sha256": sha, "source": "/proc/self/exe" });
    c.state["config"] = json!({ "path": frozen.display().to_string(), "sha256": crate::provenance::sha256_hex(&raw), "normalized_sha256": prov_v["config"]["normalized_sha256"],
        "source": conf.display().to_string(), "env_file": env_file.display().to_string() });
    c.save();
    if detach {
        daemonize(&dir.join("supervisor.log"))?;
        // a forked child does not inherit the parent's memory locks: the passphrase's page is locked again (review #15)
        if let Some(p) = &pass { p.lock().context("the detached campaign")?; }
        c.echo = false;
    } else {
        println!("campaign {}: {} (controls: touch {}.pause | .next | .stop, a reason inside)", o.name, dir.display(), runs.join(&o.name).display());
    }
    for sig in [libc::SIGINT, libc::SIGTERM] { let _ = signal_hook::flag::register(sig, c.stop.clone()); }
    let _ = signal_hook::flag::register(libc::SIGHUP, Arc::new(AtomicBool::new(false)));
    let mut runner = ProcessRunner { bin, config: frozen, dir, runs, env_file, drain_s: o.drain_s, pass, force: o.force };
    let why = c.run(&mut runner, &RealClock);
    drop(lock);
    Ok(if why.starts_with("safety") || why.starts_with("crash limit") || why.starts_with("the test budget") { 20 } else { 0 })
}

/// The data files the config names (the seed list, the registry and templates, the crowded-pools list, the leaders'
/// static fallback): path → sha256 (null: unreadable). campaign.json `data_files` (review WP-07 #16: the binary and the
/// config are frozen, the data files are hashed and checked before every segment)
pub fn data_files(cfg: &Config) -> Value {
    let mut m = serde_json::Map::new();
    let names = [Some(cfg.pools.seed_csv.as_str()), cfg.pools.registry_json.as_deref(), cfg.pools.templates_json.as_deref(), Some(cfg.send_policy.crowded_pools_file.as_str()),
        Some(cfg.leaders.static_fallback.as_str())];
    for p in names.into_iter().flatten().filter(|p| !p.is_empty()) {
        m.insert(p.to_string(), std::fs::read(p).ok().map(|b| json!(crate::provenance::sha256_hex(&b))).unwrap_or(Value::Null));
    }
    Value::Object(m)
}

/// detach: the parent prints where the campaign runs and exits; the child leaves the terminal's session, its stdin
/// /dev/null, its stdout and stderr the log. Called before any thread is started
fn daemonize(log: &Path) -> Result<()> {
    use std::os::fd::AsRawFd;
    let f = std::fs::OpenOptions::new().create(true).append(true).open(log)?;
    let null = std::fs::File::open("/dev/null")?;
    match unsafe { libc::fork() } {
        -1 => bail!("fork failed"),
        0 => {
            unsafe {
                libc::setsid();
                libc::dup2(null.as_raw_fd(), 0);
                libc::dup2(f.as_raw_fd(), 1);
                libc::dup2(f.as_raw_fd(), 2);
            }
            Ok(())
        }
        pid => {
            println!("started the campaign in the background (pid {pid}): its log is {}", log.display());
            std::process::exit(0)
        }
    }
}

/// `arbx campaign-equity`: the campaign's money from its files (MEASUREMENT §4.48)
pub fn equity_json(dir: &Path, now: u64) -> Value {
    let h = ledger::history(dir, None, now, DAY_NS + HOUR_NS);
    let camp: Value = std::fs::read(dir.join("campaign.json")).ok().and_then(|b| serde_json::from_slice(&b).ok()).unwrap_or(Value::Null);
    let floor = h.start.as_ref().zip(h.test_budget).map(|(s, b)| s.equity_stop - b as i64);
    json!({ "t_ns": now, "basis": BASIS, "stop_basis": ledger::STOP_BASIS, "start": h.start.as_ref().map(ledger::Start::json), "stop_value_now": h.stop_value_now(),
        "equity_stop_now": h.equity_stop_now, "equity_total_now": h.equity_total_now,
        "tokens_now": h.tokens_now.iter().map(|(m, a)| (m.clone(), json!(a.to_string()))).collect::<serde_json::Map<_, _>>(),
        "drop_1h": h.series.drop_over(now, HOUR_NS), "drop_24h": h.series.drop_over(now, DAY_NS), "floor_lamports": floor, "test_budget_lamports": h.test_budget,
        "net_spend": h.spent, "budget_left": h.test_budget.map(|b| b as i64 - h.spent), "totals": h.totals.json(), "segments_read": h.segments_read,
        "owner_transfers": h.owner_transfers.iter().map(|(s, sig, c, l)| json!({ "segment": s, "sig": sig, "category": c, "lamports": l })).collect::<Vec<_>>(),
        "recon_undecided": h.undecided.as_ref().map(|(s, t)| json!({ "segment": s, "t_ns": t })),
        "budget_state": crate::budget::State::load(dir.parent().unwrap_or(Path::new("."))).ok().map(|s| json!({ "spent": s.spent(), "remaining": s.remaining(), "entries": s.entries.len() })),
        "recon_misses": h.recon_misses.iter().map(|(s, t)| json!({ "segment": s, "t_ns": t })).collect::<Vec<_>>(), "unreadable_lines": h.bad_lines,
        "campaign": { "mode": camp["mode"], "end_reason": camp["end_reason"], "max_drop_per_hour_sol": camp["budget"]["max_drop_per_hour_sol"] } })
}

#[cfg(test)]
mod tests;

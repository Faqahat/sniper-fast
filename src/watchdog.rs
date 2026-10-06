//! `arbx watchdog` (PLAN-ADDENDUM WP-20): a separate, long-running process on Cherry that tells the owner whether the bot
//! runs. It shares the alerts (src/alerts.rs) and reads only the runs directory and /proc: it sends no transaction and
//! touches no segment.
//!
//! - **One per runs directory**: an exclusive `flock` on `<runs_dir>/.watchdog.lock` (a second one refuses to start).
//! - **The active segment**: every `poll_s` the live `arbx… run` processes are found in /proc (argv: the binary, then
//!   `run`) and mapped to the segment directory they write (`--campaign-dir` + `--name`, else their open `run.log` /
//!   `events.jsonl`), kept when it is under the runs directory. A segment is up when its status.jsonl is at most
//!   `stale_s` old (the engine writes one every 10 s), or while it boots (no status.jsonl yet) for at most `boot_s`.
//! - **Verdicts** ([`Machine`]): "✅ running" at the first look that finds one and every `status_min`; "❌ NOT running"
//!   when no segment process has been alive for more than `grace_s` (which covers the gap between two segments), when
//!   the running segment's status.jsonl is more than `stale_s` old, or when it boots for more than `boot_s`; a reminder
//!   every `status_min` while it stays down; "✅ back up" when it recovers. Every change and message is a line on stdout
//!   and in `<runs_dir>/watchdog.jsonl`.
//! - The daily summary of the UTC day before, when no segment sent it yet (the marker in the runs directory).
use crate::alerts::{self, format, summary, Alert, Alerts, Ctx, Level};
use crate::feeds::clock::real_ns;
use anyhow::{bail, Context, Result};
use format::Body;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering::Relaxed};
use std::sync::Arc;
use std::time::Duration;

/// `[watchdog]`
#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct WatchdogCfg {
    /// the runs directory it watches ("": the config's `out_dir`)
    #[serde(default)]
    pub runs_dir: String,
    /// no segment process for longer than this is "not running" (covers the gap between two segments), seconds
    #[serde(default = "grace_s")]
    pub grace_s: u64,
    /// "running" every this many minutes, and the "still not running" reminder (0: only the changes)
    #[serde(default = "status_min")]
    pub status_min: u64,
    /// a running segment whose status.jsonl is older than this is "not running" (it gets a line every 10 s), seconds
    #[serde(default = "stale_s")]
    pub stale_s: u64,
    /// a segment process still without status.jsonl after this long is "not running" (stuck in its boot), seconds
    #[serde(default = "boot_s")]
    pub boot_s: u64,
    /// how often it looks, seconds
    #[serde(default = "poll_s")]
    pub poll_s: u64,
}

fn grace_s() -> u64 { 120 }
fn status_min() -> u64 { 60 }
fn stale_s() -> u64 { 60 }
fn boot_s() -> u64 { 600 }
fn poll_s() -> u64 { 10 }

impl Default for WatchdogCfg {
    fn default() -> Self { WatchdogCfg { runs_dir: String::new(), grace_s: grace_s(), status_min: status_min(), stale_s: stale_s(), boot_s: boot_s(), poll_s: poll_s() } }
}

impl WatchdogCfg {
    pub fn check(&self) -> Result<()> {
        if self.grace_s < 10 || self.grace_s > 86_400 { bail!("[watchdog] grace_s must be 10..86400"); }
        if self.stale_s < 20 || self.stale_s > 86_400 { bail!("[watchdog] stale_s must be 20..86400 (status.jsonl gets a line every 10 s)"); }
        if self.boot_s < 60 || self.boot_s > 86_400 { bail!("[watchdog] boot_s must be 60..86400"); }
        if !(1..=300).contains(&self.poll_s) { bail!("[watchdog] poll_s must be 1..300"); }
        if self.status_min > 10_080 { bail!("[watchdog] status_min must be at most 10080 (a week; 0: only the changes)"); }
        Ok(())
    }
    /// the directory it watches: `runs_dir`, else `out_dir`
    pub fn dir(&self, out_dir: &str) -> PathBuf { PathBuf::from(if self.runs_dir.is_empty() { out_dir } else { &self.runs_dir }) }
}

// ------------------------------------------------------------------ what it sees

/// A live segment process and its directory
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Seg {
    pub dir: PathBuf,
    pub name: String,
    pub pid: Option<i32>,
    /// when its process started (ns)
    pub started_ns: Option<u64>,
    /// how old its status.jsonl is (None: there is none yet: it boots)
    pub status_age_ns: Option<u64>,
}

/// The segment that ended last (its stop.json)
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Ended { pub name: String, pub reason: Option<String>, pub exit_code: Option<i64>, pub ended_ns: Option<u64> }

/// One look at the runs directory
#[derive(Clone, Debug, Default)]
pub struct Obs { pub t_ns: u64, pub live: Vec<Seg>, pub last_end: Option<Ended> }

fn base(p: &str) -> &str { p.rsplit('/').next().unwrap_or(p) }

/// The position of the binary in `argv` when it is a segment process: `arbx…` (`arbx`, `arbx-<sha8>`, any path) then
/// `run`
pub fn run_index(argv: &[String]) -> Option<usize> {
    (0..argv.len().saturating_sub(1)).find(|&i| base(&argv[i]).starts_with("arbx") && argv[i + 1] == "run")
}

/// the value of `--<flag> X` or `--<flag>=X` in `args`
fn flag<'a>(args: &'a [String], name: &str) -> Option<&'a str> {
    let long = format!("--{name}");
    let eq = format!("--{name}=");
    let mut it = args.iter();
    while let Some(a) = it.next() {
        if *a == long { return it.next().map(String::as_str); }
        if let Some(v) = a.strip_prefix(&eq) { return Some(v); }
    }
    None
}

/// the segment directory from a run's arguments (`--campaign-dir C --name N`: C/N, C relative to `cwd`)
pub fn dir_from_args(args: &[String], cwd: Option<&Path>) -> Option<PathBuf> {
    let (c, n) = (flag(args, "campaign-dir")?, flag(args, "name")?);
    let c = Path::new(c);
    let c = if c.is_relative() { cwd?.join(c) } else { c.to_path_buf() };
    Some(c.join(n))
}

/// a path made absolute and clean (`canonicalize`, or as given)
fn canon(p: &Path) -> PathBuf { std::fs::canonicalize(p).unwrap_or_else(|_| p.to_path_buf()) }

/// the segment directory a process writes: one of its open files named run.log, events.jsonl or status.jsonl under `runs`
fn dir_from_fds(pid: i32, runs: &Path) -> Option<PathBuf> {
    for e in std::fs::read_dir(format!("/proc/{pid}/fd")).ok()?.flatten() {
        let Ok(t) = std::fs::read_link(e.path()) else { continue };
        let n = t.file_name().and_then(|n| n.to_str()).unwrap_or("");
        if matches!(n, "run.log" | "events.jsonl" | "status.jsonl") && t.starts_with(runs) { return t.parent().map(Path::to_path_buf); }
    }
    None
}

/// a process's start (ns since the epoch), from /proc/<pid>/stat and the boot time
pub fn proc_start_ns(pid: i32) -> Option<u64> {
    let st = std::fs::read_to_string(format!("/proc/{pid}/stat")).ok()?;
    let rest = &st[st.rfind(')')? + 1..];
    let ticks: u64 = rest.split_whitespace().nth(19)?.parse().ok()?;
    let btime: u64 = std::fs::read_to_string("/proc/stat").ok()?.lines().find_map(|l| l.strip_prefix("btime ").and_then(|v| v.trim().parse().ok()))?;
    // SAFETY: a plain query
    let hz = unsafe { libc::sysconf(libc::_SC_CLK_TCK) };
    let hz = if hz > 0 { hz as u128 } else { 100 };
    // in u128: ticks x 1e9 passes u64 after about 5.8 years of uptime at 100 Hz
    u64::try_from(btime as u128 * 1_000_000_000 + ticks as u128 * 1_000_000_000 / hz).ok()
}

/// whether a process exists and is not a zombie
pub fn alive(pid: i32) -> bool {
    let Ok(st) = std::fs::read_to_string(format!("/proc/{pid}/stat")) else { return false };
    st.rfind(')').and_then(|i| st[i + 1..].split_whitespace().next()).is_some_and(|s| s != "Z" && s != "X")
}

/// The live segment processes (`arbx… run`) whose segment directory is under `runs_dir`: (pid, dir, start)
pub fn scan_procs(runs_dir: &Path) -> Vec<(i32, PathBuf, Option<u64>)> {
    let me = std::process::id() as i32;
    let runs = canon(runs_dir);
    let mut out = Vec::new();
    for e in std::fs::read_dir("/proc").into_iter().flatten().flatten() {
        let Some(pid) = e.file_name().to_str().and_then(|s| s.parse::<i32>().ok()) else { continue };
        if pid == me { continue; }
        let Ok(raw) = std::fs::read(format!("/proc/{pid}/cmdline")) else { continue };
        if raw.is_empty() { continue; }
        let mut argv: Vec<String> = raw.split(|b| *b == 0).map(|a| String::from_utf8_lossy(a).into_owned()).collect();
        if argv.last().is_some_and(|a| a.is_empty()) { argv.pop(); }
        let Some(i) = run_index(&argv) else { continue };
        if !alive(pid) { continue; }
        let cwd = std::fs::read_link(format!("/proc/{pid}/cwd")).ok();
        let dir = dir_from_args(&argv[i + 2..], cwd.as_deref()).map(|d| canon(&d)).filter(|d| d.starts_with(&runs)).or_else(|| dir_from_fds(pid, &runs));
        if let Some(d) = dir { out.push((pid, d, proc_start_ns(pid))); }
    }
    out.sort_by(|a, b| a.1.cmp(&b.1).then(a.0.cmp(&b.0)));
    out.dedup_by(|a, b| a.1 == b.1);
    out
}

fn mtime_ns(p: &Path) -> Option<u64> {
    std::fs::metadata(p).ok()?.modified().ok()?.duration_since(std::time::UNIX_EPOCH).ok().map(|d| d.as_nanos() as u64)
}

/// the segment of `runs_dir` that ended last (the newest stop.json)
pub fn last_end(runs_dir: &Path) -> Option<Ended> {
    let (_, dir) = summary::segment_dirs(runs_dir).into_iter().filter_map(|d| mtime_ns(&d.join("stop.json")).map(|m| (m, d))).max_by_key(|x| x.0)?;
    let v: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("stop.json")).ok()?).ok()?;
    Some(Ended { name: dir.file_name()?.to_string_lossy().into_owned(), reason: v["reason"].as_str().map(str::to_string), exit_code: v["exit_code"].as_i64(),
        ended_ns: v["ended_ns"].as_u64() })
}

/// One look: the live segment processes under `runs_dir` and their status.jsonl's age; the last ended segment when none
pub fn observe(runs_dir: &Path, now_ns: u64) -> Obs {
    let live: Vec<Seg> = scan_procs(runs_dir).into_iter().map(|(pid, dir, started)| {
        let age = mtime_ns(&dir.join("status.jsonl")).map(|m| now_ns.saturating_sub(m));
        Seg { name: dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default(), dir, pid: Some(pid), started_ns: started, status_age_ns: age }
    }).collect();
    let last_end = if live.is_empty() { last_end(runs_dir) } else { None };
    Obs { t_ns: now_ns, live, last_end }
}

// ------------------------------------------------------------------ the verdicts

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum State { Starting, Running, Down }

/// What one look says
#[derive(Clone, Debug, PartialEq)]
pub enum Verdict {
    /// a segment runs (`booting`: no status.jsonl yet)
    Up { seg: usize, booting: bool },
    /// the running segment's status.jsonl is too old
    Stale { seg: usize, age_s: u64 },
    /// a segment process boots for too long
    BootStuck { seg: usize, age_s: u64 },
    /// no segment process, within the grace
    Gap { for_s: u64 },
    /// no segment process for longer than the grace
    Gone { for_s: u64 },
}

/// "no arbx segment process (for …)", and how the last segment ended
fn gone_why(for_s: Option<u64>, e: Option<&Ended>) -> String {
    let mut w = match for_s { Some(s) => format!("no arbx segment process for {}", format::dur(s)), None => "no arbx segment process".to_string() };
    if let Some(e) = e {
        w.push_str(&format!("; the last, {}, ended{}{}", e.name, e.ended_ns.map(|t| format!(" at {} UTC", format::utc_hms(t))).unwrap_or_default(),
            match (&e.reason, e.exit_code) { (Some(r), Some(c)) => format!(" ({r}, exit {c})"), (Some(r), None) => format!(" ({r})"), _ => " (no stop.json reason)".into() }));
    }
    w
}

/// What the watchdog tells
#[derive(Clone, Debug, PartialEq)]
pub enum Out {
    Running { first: bool },
    Down { why: String },
    StillDown { why: String, for_s: u64 },
    BackUp { down_s: u64 },
}

#[derive(Clone, Copy, Debug)]
pub struct Timing { pub grace_ns: u64, pub stale_ns: u64, pub boot_ns: u64, pub every_ns: u64 }

impl Timing {
    pub fn of(c: &WatchdogCfg) -> Timing {
        Timing { grace_ns: c.grace_s * 1_000_000_000, stale_ns: c.stale_s * 1_000_000_000, boot_ns: c.boot_s * 1_000_000_000, every_ns: c.status_min * 60_000_000_000 }
    }
}

/// The watchdog's state machine: one [`Machine::step`] per look
#[derive(Clone, Debug)]
pub struct Machine {
    t: Timing,
    pub state: State,
    /// when the state began, when a segment process was last seen, when the last message went
    pub since_ns: u64,
    pub last_alive_ns: u64,
    pub last_msg_ns: u64,
}

impl Machine {
    pub fn new(t: Timing, now_ns: u64) -> Machine { Machine { t, state: State::Starting, since_ns: now_ns, last_alive_ns: now_ns, last_msg_ns: 0 } }

    /// the segment the verdict is about: a live one with a fresh status.jsonl first, else the newest
    pub fn active(&self, o: &Obs) -> Option<usize> {
        let fresh = |s: &Seg| s.status_age_ns.is_some_and(|a| a <= self.t.stale_ns);
        o.live.iter().position(fresh).or_else(|| o.live.iter().enumerate().max_by_key(|(_, s)| s.started_ns.unwrap_or(0)).map(|(i, _)| i))
    }

    pub fn verdict(&self, o: &Obs) -> Verdict {
        let Some(i) = self.active(o) else {
            let gone = o.t_ns.saturating_sub(self.last_alive_ns);
            return if gone > self.t.grace_ns { Verdict::Gone { for_s: gone / 1_000_000_000 } } else { Verdict::Gap { for_s: gone / 1_000_000_000 } };
        };
        let s = &o.live[i];
        match s.status_age_ns {
            Some(a) if a <= self.t.stale_ns => Verdict::Up { seg: i, booting: false },
            Some(a) => Verdict::Stale { seg: i, age_s: a / 1_000_000_000 },
            None => {
                let booted = s.started_ns.map_or(0, |t| o.t_ns.saturating_sub(t));
                if booted > self.t.boot_ns { Verdict::BootStuck { seg: i, age_s: booted / 1_000_000_000 } } else { Verdict::Up { seg: i, booting: true } }
            }
        }
    }

    /// why a verdict is "not running" (None: it is not)
    pub fn why(&self, o: &Obs, v: &Verdict) -> Option<String> {
        let name = |i: &usize| o.live.get(*i).map_or("?".to_string(), |s| s.name.clone());
        match v {
            Verdict::Up { .. } | Verdict::Gap { .. } => None,
            Verdict::Stale { seg, age_s } => Some(format!("segment {}: status.jsonl not written for {} (the engine writes it every 10 s)", name(seg), format::dur(*age_s))),
            Verdict::BootStuck { seg, age_s } => Some(format!("segment {} has been booting for {} without status.jsonl", name(seg), format::dur(*age_s))),
            Verdict::Gone { for_s } => Some(gone_why(Some(*for_s), o.last_end.as_ref())),
        }
    }

    /// One look: the messages it calls for
    pub fn step(&mut self, o: &Obs) -> Vec<Out> {
        let now = o.t_ns;
        if !o.live.is_empty() { self.last_alive_ns = now; }
        let v = self.verdict(o);
        let up = matches!(v, Verdict::Up { .. });
        let why = self.why(o, &v);
        let due = self.t.every_ns > 0 && now.saturating_sub(self.last_msg_ns) >= self.t.every_ns;
        let mut out = Vec::new();
        match (self.state, up, why) {
            (State::Starting, true, _) => { self.state = State::Running; self.since_ns = now; self.last_msg_ns = now; out.push(Out::Running { first: true }); }
            (State::Starting | State::Running, false, Some(w)) => { self.state = State::Down; self.since_ns = now; self.last_msg_ns = now; out.push(Out::Down { why: w }); }
            (State::Running, true, _) if due => { self.last_msg_ns = now; out.push(Out::Running { first: false }); }
            (State::Down, true, _) => {
                out.push(Out::BackUp { down_s: now.saturating_sub(self.since_ns) / 1_000_000_000 });
                self.state = State::Running;
                self.since_ns = now;
                self.last_msg_ns = now;
            }
            (State::Down, false, Some(w)) if due => { self.last_msg_ns = now; out.push(Out::StillDown { why: w, for_s: now.saturating_sub(self.since_ns) / 1_000_000_000 }); }
            _ => {}
        }
        out
    }
}

/// a segment's lines for the messages: how long it has run and how fresh its status is; its gate, sends, wins, net
fn seg_body(s: &Seg, now_ns: u64, snap: Option<&summary::Snapshot>) -> Body {
    let mut b = Body::new();
    if let Some(t) = s.started_ns { b = b.kv("up", format::dur(now_ns.saturating_sub(t) / 1_000_000_000)); }
    b = match s.status_age_ns { Some(a) => b.kv("status", format!("{} ago", format::dur(a / 1_000_000_000))), None => b.txt("booting") };
    if let Some(x) = snap {
        b = b.nl();
        if let Some(g) = &x.gate_mode { b = b.kv("gate", match &x.gate_reason { Some(r) => format!("{g} ({r})"), None => g.clone() }); }
        let n = |v: Option<u64>| v.map_or("?".into(), format::int);
        b = b.nl().kv("sent", n(x.sends)).kv("wins", n(x.wins));
        if let Some(net) = x.net_lamports { b = b.kv("net", format::sol_signed(net)); }
    }
    b
}

/// The alert of a watchdog message. `host`: where the watchdog runs
pub fn render(out: &Out, o: &Obs, m: &Machine, host: &str) -> Alert {
    let active = m.active(o).and_then(|i| o.live.get(i));
    let snap = active.and_then(|s| summary::last_status(&s.dir.join("status.jsonl"))).map(|v| summary::Snapshot::of(&v));
    let seg = active.map_or("?".to_string(), |s| s.name.clone());
    match out {
        Out::Running { first } => {
            let b = active.map_or_else(Body::new, |s| seg_body(s, o.t_ns, snap.as_ref()));
            Alert::new(Level::Info, "watchdog_running", "watchdog_running", &format!("running: {seg}{}", if *first { " (watchdog started)" } else { "" })).icon("✅").once().body(b)
        }
        Out::Down { why } => Alert::new(Level::Critical, "watchdog_down", "watchdog_down", "arbx NOT running").icon("❌").once()
            .body(Body::new().txt(why).nl().kv("watchdog on", host)),
        Out::StillDown { why, for_s } => Alert::new(Level::Critical, "watchdog_down", "watchdog_still_down", &format!("arbx still NOT running ({})", format::dur(*for_s)))
            .icon("❌").once().body(Body::new().txt(why).nl().kv("watchdog on", host)),
        Out::BackUp { down_s } => {
            let b = active.map_or_else(Body::new, |s| seg_body(s, o.t_ns, snap.as_ref()));
            Alert::new(Level::Info, "watchdog_back", "watchdog_back", &format!("back up: {seg} (down {})", format::dur(*down_s))).icon("✅").once().body(b)
        }
    }
}

// ------------------------------------------------------------------ the process

/// The single-instance lock: an exclusive `flock` on `<runs_dir>/.watchdog.lock`, held while this lives. The file holds
/// the holder's pid while it runs and is emptied when it ends (still under the lock), so a pid read from it later never
/// names a process that reused the number: an empty file, or one `flock -n` can take, means no watchdog runs
pub struct Lock { f: std::fs::File, pub path: PathBuf }

impl Drop for Lock {
    fn drop(&mut self) { let _ = self.f.set_len(0); }
}

pub fn lock(runs_dir: &Path) -> Result<Lock> {
    use std::io::{Read, Seek, Write};
    use std::os::fd::AsRawFd;
    use std::os::unix::fs::OpenOptionsExt;
    let path = runs_dir.join(".watchdog.lock");
    let mut f = std::fs::OpenOptions::new().create(true).truncate(false).read(true).write(true).mode(0o600).open(&path).with_context(|| format!("opening {}", path.display()))?;
    // SAFETY: flock on an open file descriptor
    if unsafe { libc::flock(f.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        let mut who = String::new();
        let _ = f.read_to_string(&mut who);
        bail!("another arbx watchdog holds {} (pid {}): not starting", path.display(), who.trim());
    }
    let _ = f.set_len(0);
    let _ = f.rewind();
    let _ = writeln!(f, "{}", std::process::id());
    Ok(Lock { f, path })
}

fn stamp(t_ns: u64) -> String { format!("{}T{}Z", format::utc_date(t_ns), format::utc_hms(t_ns)) }

/// The `--once` verdict: JSON, and whether a segment runs
pub fn once(runs_dir: &Path, cfg: &WatchdogCfg) -> (Value, bool) {
    let now = real_ns();
    let o = observe(runs_dir, now);
    let m = Machine::new(Timing::of(cfg), now);
    let v = m.verdict(&o);
    let up = matches!(v, Verdict::Up { .. });
    let seg = m.active(&o).and_then(|i| o.live.get(i));
    let state = match &v { Verdict::Up { booting: true, .. } => "booting", Verdict::Up { .. } => "running", _ => "not running" };
    // one look has no history: no segment process is "not running" at once
    let why = if o.live.is_empty() { Some(gone_why(None, o.last_end.as_ref())) } else { m.why(&o, &v) };
    (json!({ "runs_dir": runs_dir.display().to_string(), "state": state, "segment": seg.map(|s| s.name.clone()), "pid": seg.and_then(|s| s.pid),
        "dir": seg.map(|s| s.dir.display().to_string()), "status_age_s": seg.and_then(|s| s.status_age_ns).map(|a| a / 1_000_000_000),
        "why": why, "live": o.live.len(), "last_end": o.last_end.as_ref().map(|e| json!({ "segment": e.name, "reason": e.reason, "exit_code": e.exit_code, "ended_ns": e.ended_ns })) }), up)
}

/// `arbx watchdog`: until SIGINT or SIGTERM. The alerts come from `[alerts]` (off without the token and chat id: then it
/// only writes stdout and watchdog.jsonl)
pub fn run(alerts_cfg: &alerts::AlertsCfg, cfg: &WatchdogCfg, runs_dir: &Path, env_note: Option<String>) -> Result<i32> {
    if !runs_dir.is_dir() { bail!("the runs directory {} does not exist", runs_dir.display()); }
    let _lock = lock(runs_dir)?;
    let host = crate::provenance::hostname();
    let journal = runs_dir.join("watchdog.jsonl");
    let say = |t: u64, msg: &str, line: Value| {
        crate::rec::out_line(&format!("{} watchdog: {msg}", stamp(t)));
        let mut l = line;
        l["t_ns"] = json!(t);
        crate::control::append_line(&journal, &l.to_string());
    };
    let now = real_ns();
    let (a, notes) = Alerts::new(alerts_cfg, &alerts::env_var, Ctx { label: "watchdog".into(), runs_dir: Some(runs_dir.to_path_buf()), started_ns: now, ..Default::default() });
    if let Some(n) = env_note { say(now, &n, json!({ "event": "note", "msg": n })); }
    for n in &notes { say(now, n, json!({ "event": "note", "msg": n })); }
    alerts::install(a.clone());
    alerts::install_panic_hook();
    let stop = Arc::new(AtomicBool::new(false));
    for s in [libc::SIGINT, libc::SIGTERM] { signal_hook::flag::register(s, stop.clone()).context("installing the signal handlers")?; }
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(1).thread_name("arbx-wd").enable_all().build().context("the watchdog's runtime")?;
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    let t = Timing::of(cfg);
    say(now, &format!("started (pid {}): watching {} (grace {} s, stale {} s, boot {} s, running every {} min), alerts {}", std::process::id(), runs_dir.display(),
        cfg.grace_s, cfg.stale_s, cfg.boot_s, cfg.status_min, if a.enabled() { "on" } else { "off" }),
        json!({ "event": "start", "pid": std::process::id(), "runs_dir": runs_dir.display().to_string(), "alerts": a.enabled() }));
    a.raise(Alert::new(Level::Info, "watchdog_start", "watchdog_start", &format!("watchdog started on {host}")).icon("👀").once()
        .body(Body::new().code("runs", runs_dir.display().to_string()).kv("grace", format!("{} s", cfg.grace_s)).kv("running every", format!("{} min", cfg.status_min))));
    let mut m = Machine::new(t, now);
    while !stop.load(Relaxed) {
        let now = real_ns();
        let o = observe(runs_dir, now);
        for out in m.step(&o) {
            let al = render(&out, &o, &m, &host);
            let seg = m.active(&o).and_then(|i| o.live.get(i)).map(|s| s.name.clone());
            let (ev, why) = match &out { Out::Running { .. } => ("running", None), Out::Down { why } => ("down", Some(why.clone())), Out::StillDown { why, .. } => ("still_down", Some(why.clone())),
                Out::BackUp { .. } => ("back_up", None) };
            say(now, &format!("{ev}{}{}", seg.as_ref().map(|s| format!(" ({s})")).unwrap_or_default(), why.as_ref().map(|w| format!(": {w}")).unwrap_or_default()),
                json!({ "event": ev, "segment": seg, "why": why, "sent": a.enabled() }));
            a.raise(al);
        }
        if a.enabled() && alerts_cfg.daily_summary {
            if let Some((day, start)) = summary::daily_due(runs_dir, now) {
                let d = summary::day_totals(runs_dir, start);
                if d.segments > 0 { a.raise(alerts::daily_alert(&d)); }
                say(now, &format!("daily summary {day}: {} segments", d.segments), json!({ "event": "daily", "day": day, "segments": d.segments }));
            }
        }
        let until = std::time::Instant::now() + Duration::from_secs(cfg.poll_s);
        while !stop.load(Relaxed) && std::time::Instant::now() < until { std::thread::sleep(Duration::from_millis(200)); }
    }
    let now = real_ns();
    say(now, "stopping (a signal)", json!({ "event": "stop", "alerts": a.status_json() }));
    a.flush(alerts::FLUSH_WAIT);
    let bye = Alert::new(Level::Info, "watchdog_stop", "watchdog_stop", &format!("watchdog stopped on {host} (a signal): no more running / not-running messages")).icon("⏹").once();
    let first = if bye.level >= a.min_level() { vec![bye] } else { Vec::new() };
    let _ = a.deliver_now(first, alerts::EXIT_WAIT);
    rt.shutdown_timeout(Duration::from_secs(1));
    Ok(0)
}

#[cfg(test)]
mod tests {
    use super::*;

    const S: u64 = 1_000_000_000;

    fn timing() -> Timing { Timing { grace_ns: 120 * S, stale_ns: 60 * S, boot_ns: 600 * S, every_ns: 3_600 * S } }
    fn seg(name: &str, started: u64, age: Option<u64>) -> Seg {
        Seg { dir: PathBuf::from(format!("/runs/c/{name}")), name: name.into(), pid: Some(4242), started_ns: Some(started), status_age_ns: age }
    }
    fn look(t: u64, live: Vec<Seg>) -> Obs { Obs { t_ns: t, live, last_end: None } }

    /// running → (a gap between segments within the grace: nothing) → not running after the grace → a reminder every
    /// `status_min` → back up; a stale status.jsonl and a boot that does not end are "not running" too
    #[test]
    fn running_not_running_back_up() {
        let t0 = 1_000_000 * S;
        let mut m = Machine::new(timing(), t0);
        assert_eq!(m.step(&look(t0, vec![seg("c-p1", t0 - 30 * S, Some(3 * S))])), vec![Out::Running { first: true }]);
        assert_eq!(m.state, State::Running);
        assert!(m.step(&look(t0 + 10 * S, vec![seg("c-p1", t0 - 30 * S, Some(2 * S))])).is_empty());
        assert_eq!(m.step(&look(t0 + 3_600 * S, vec![seg("c-p1", t0 - 30 * S, Some(5 * S))])), vec![Out::Running { first: false }], "every status_min");
        // the segment ends (last seen 10 s before t1); the next one boots 70 s later: within the grace, nothing is said
        let t1 = t0 + 3_700 * S;
        assert!(m.step(&look(t1 - 10 * S, vec![seg("c-p1", t0 - 30 * S, Some(2 * S))])).is_empty());
        assert!(m.step(&look(t1, vec![])).is_empty());
        assert!(m.step(&look(t1 + 60 * S, vec![])).is_empty());
        assert!(m.step(&look(t1 + 70 * S, vec![seg("c-p2", t1 + 65 * S, None)])).is_empty(), "booting is running");
        // that one dies (last seen a second before t2); nothing for longer than the grace
        let t2 = t1 + 200 * S;
        assert!(m.step(&look(t2 - S, vec![seg("c-p2", t1 + 65 * S, Some(2 * S))])).is_empty());
        assert!(m.step(&look(t2, vec![])).is_empty());
        let mut gone = look(t2 + 121 * S, vec![]);
        gone.last_end = Some(Ended { name: "c-p2".into(), reason: Some("error".into()), exit_code: Some(30), ended_ns: Some(t2) });
        let out = m.step(&gone);
        assert!(matches!(&out[..], [Out::Down { why }] if why.contains("no arbx segment process for 2m") && why.contains("c-p2") && why.contains("(error, exit 30)")), "{out:?}");
        assert_eq!(m.state, State::Down);
        assert!(m.step(&look(t2 + 200 * S, vec![])).is_empty(), "no reminder before status_min");
        let out = m.step(&look(t2 + 121 * S + 3_600 * S, vec![]));
        assert!(matches!(&out[..], [Out::StillDown { for_s: 3_600, .. }]), "{out:?}");
        // back
        let t3 = t2 + 4_000 * S;
        assert_eq!(m.step(&look(t3, vec![seg("c-p3", t3 - 5 * S, None)])), vec![Out::BackUp { down_s: 4_000 - 121 }]);
        assert_eq!(m.state, State::Running);
        // a status.jsonl more than stale_s old: not running at once
        let out = m.step(&look(t3 + 100 * S, vec![seg("c-p3", t3 - 5 * S, Some(61 * S))]));
        assert!(matches!(&out[..], [Out::Down { why }] if why.contains("status.jsonl not written for 61s")), "{out:?}");
        assert_eq!(m.step(&look(t3 + 110 * S, vec![seg("c-p3", t3 - 5 * S, Some(1 * S))])), vec![Out::BackUp { down_s: 10 }]);
        // a boot that does not end
        let mut m = Machine::new(timing(), t0);
        let out = m.step(&look(t0, vec![seg("c-p9", t0 - 601 * S, None)]));
        assert!(matches!(&out[..], [Out::Down { why }] if why.contains("booting for 10m")), "{out:?}");
        // the fresh one of two live segments decides
        let m = Machine::new(timing(), t0);
        let o = look(t0, vec![seg("old", t0 - 900 * S, Some(500 * S)), seg("new", t0 - 10 * S, Some(2 * S))]);
        assert_eq!(m.verdict(&o), Verdict::Up { seg: 1, booting: false });
    }

    /// a watchdog started while nothing runs says so once the grace is over (not before); `status_min = 0` sends only
    /// the changes
    #[test]
    fn nothing_running_at_start() {
        let t0 = 5_000 * S;
        let mut m = Machine::new(Timing { every_ns: 0, ..timing() }, t0);
        assert!(m.step(&look(t0, vec![])).is_empty());
        assert!(m.step(&look(t0 + 119 * S, vec![])).is_empty());
        assert!(matches!(&m.step(&look(t0 + 121 * S, vec![]))[..], [Out::Down { .. }]));
        assert!(m.step(&look(t0 + 100_000 * S, vec![])).is_empty(), "no reminder with status_min = 0");
        assert!(matches!(&m.step(&look(t0 + 100_010 * S, vec![seg("x", t0, Some(S))]))[..], [Out::BackUp { .. }]));
        assert!(m.step(&look(t0 + 200_000 * S, vec![seg("x", t0, Some(S))])).is_empty(), "no periodic running with status_min = 0");
    }

    #[test]
    fn segment_processes_from_their_arguments() {
        let v = |s: &str| s.split(' ').map(String::from).collect::<Vec<_>>();
        assert_eq!(run_index(&v("/root/arbx/runs/w6/arbx-1a2b3c4d run --config c --name w6-p3 --campaign-dir /root/arbx/runs/w6")), Some(0));
        assert_eq!(run_index(&v("bin/arbx run --config x")), Some(0));
        assert_eq!(run_index(&v("sh -c x arbx-fake run --name y")), Some(3));
        for no in ["arbx-1a2b3c4d watchdog --config x", "arbx ctl --run /runs/x status", "bash deploy/run-w.sh w6 5 20 1 c", "vim run arbx"] { assert_eq!(run_index(&v(no)), None, "{no}"); }
        let args = v("--config c --name w6-p3 --campaign-dir /root/arbx/runs/w6 --minutes 20");
        assert_eq!(dir_from_args(&args, None), Some(PathBuf::from("/root/arbx/runs/w6/w6-p3")));
        assert_eq!(dir_from_args(&v("--name=w6-p4 --campaign-dir=runs/w6"), Some(Path::new("/root/arbx"))), Some(PathBuf::from("/root/arbx/runs/w6/w6-p4")));
        assert_eq!(dir_from_args(&v("--name x"), None), None, "no campaign: the open files say");
        assert!(alive(std::process::id() as i32) && !alive(i32::MAX));
        let start = proc_start_ns(std::process::id() as i32).unwrap();
        assert!(start <= real_ns() && real_ns() - start < 86_400 * S, "this process started in the last day");
    }

    fn tmp(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("arbx-wd-{name}-{}-{}", std::process::id(), real_ns()));
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    /// a fake segment process (its argv: `… arbx-fake run --campaign-dir <c> --name <seg>`) found in /proc, with its
    /// status.jsonl's age; gone once it is killed, and the last stop.json named
    #[test]
    fn finds_a_fake_segment_in_a_runs_directory() {
        let runs = tmp("runs");
        let camp = runs.join("c");
        let segdir = camp.join("c-p1");
        std::fs::create_dir_all(&segdir).unwrap();
        std::fs::write(segdir.join("status.jsonl"), "{\"seq\":0}\n").unwrap();
        let mut child = std::process::Command::new("sh").args(["-c", "sleep 30; true", "arbx-fake", "run", "--campaign-dir"]).arg(&camp).args(["--name", "c-p1"])
            .spawn().unwrap();
        let pid = child.id() as i32;
        let until = std::time::Instant::now() + Duration::from_secs(10);
        let o = loop {
            let o = observe(&runs, real_ns());
            if !o.live.is_empty() || std::time::Instant::now() > until { break o; }
            std::thread::sleep(Duration::from_millis(20));
        };
        assert_eq!(o.live.len(), 1, "{o:?}");
        assert_eq!((o.live[0].pid, o.live[0].name.as_str()), (Some(pid), "c-p1"));
        assert!(o.live[0].status_age_ns.is_some_and(|a| a < 30 * S) && o.live[0].started_ns.is_some());
        let mut m = Machine::new(timing(), real_ns());
        assert_eq!(m.step(&o), vec![Out::Running { first: true }]);
        let a = render(&Out::Running { first: true }, &o, &m, "testhost");
        assert!(a.title.contains("running: c-p1") && a.body.contains("status"), "{} {}", a.title, a.body);
        // another runs directory does not see it
        assert!(observe(&tmp("other"), real_ns()).live.is_empty());
        let (v, up) = once(&runs, &WatchdogCfg::default());
        assert!(up && v["state"] == "running" && v["segment"] == "c-p1", "{v}");
        child.kill().unwrap();
        child.wait().unwrap();
        std::fs::write(segdir.join("stop.json"), json!({ "reason": "signal", "exit_code": 10, "ended_ns": real_ns() }).to_string()).unwrap();
        let o = observe(&runs, real_ns());
        assert!(o.live.is_empty(), "{o:?}");
        assert_eq!(o.last_end.as_ref().map(|e| (e.name.as_str(), e.reason.as_deref(), e.exit_code)), Some(("c-p1", Some("signal"), Some(10))));
        let (v, up) = once(&runs, &WatchdogCfg::default());
        assert!(!up && v["state"] == "not running" && v["why"].as_str().unwrap().contains("c-p1"), "{v}");
        let _ = std::fs::remove_dir_all(&runs);
    }

    /// one watchdog per runs directory
    #[test]
    fn the_lock_is_single_instance() {
        let runs = tmp("lock");
        let l = lock(&runs).unwrap();
        let file = runs.join(".watchdog.lock");
        assert_eq!(std::fs::read_to_string(&file).unwrap().trim(), std::process::id().to_string(), "the holder's pid while it runs");
        let e = lock(&runs).err().unwrap().to_string();
        assert!(e.contains("another arbx watchdog holds") && e.contains(&std::process::id().to_string()), "{e}");
        assert_eq!(std::fs::read_to_string(&file).unwrap().trim(), std::process::id().to_string(), "a refused second one leaves the pid alone");
        drop(l);
        assert_eq!(std::fs::read_to_string(&file).unwrap(), "", "emptied when it ends: a later `kill $(cat …)` names no reused pid");
        assert!(lock(&runs).is_ok(), "free again once the first ends");
        let _ = std::fs::remove_dir_all(&runs);
    }

    #[test]
    fn watchdog_config_checks() {
        let c = WatchdogCfg::default();
        assert!(c.check().is_ok());
        assert_eq!((c.grace_s, c.status_min, c.stale_s, c.boot_s, c.poll_s), (120, 60, 60, 600, 10));
        assert!(WatchdogCfg { grace_s: 5, ..c.clone() }.check().is_err() && WatchdogCfg { stale_s: 10, ..c.clone() }.check().is_err());
        assert!(WatchdogCfg { poll_s: 0, ..c.clone() }.check().is_err());
        assert_eq!(c.dir("/root/arbx/runs"), PathBuf::from("/root/arbx/runs"));
        assert_eq!(WatchdogCfg { runs_dir: "/x".into(), ..c }.dir("/root/arbx/runs"), PathBuf::from("/x"));
    }
}

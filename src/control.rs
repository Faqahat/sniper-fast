//! Stop reasons and run control (PLAN WP-01 items 5-6; MEASUREMENT §4.3 stop.json, §4.7 control.jsonl, A.5).
//!
//! - **SendGate**: an atomic mode (`live`, `shadow`, `stopped`) with a reason, read by `Exec::wants_send` on every
//!   decision. `pause-sending` puts it in shadow until `resume-sending`; `shadow` (and `--shadow`, and a route program
//!   whose hash differs from the config's) is sticky for the rest of the segment; a stop request closes it for good.
//!   Pausing a gate that is already shadow for the rest of the segment is accepted and changes nothing (review F3).
//! - **Stopper**: the stop flag every loop polls, and the `StopReason` that is set once (the first request wins).
//! - **Signals**: SIGINT and SIGTERM through signal-hook's `SignalsInfo<WithOrigin>`, which gives the sender's pid and
//!   uid; the sender's command line comes from `/proc/<pid>/cmdline`.
//! - **Control socket**: `<run dir>/control.sock` (mode 0600, and only the run's user or root: SO_PEERCRED), one JSON
//!   line in, one out (`arbx ctl`). Every command, accepted or not, goes to `control.jsonl`.
//! - **Session**: the run's stop path. `finish` writes `stop.json` (once, atomically) and the run.log line, and returns
//!   the exit code: 0 deadline, 10 operator stop, 20 safety stop, 30 error. `fail` is an error or panic: after a stop
//!   request it is kept as stop.json `secondary` and the exit code is 30 (review M5).
use crate::feeds::clock::now_ns;
use anyhow::{bail, Context, Result};
use serde::Serialize;
use serde_json::{json, Value};
use std::io::{BufRead, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering};
use std::sync::{Arc, Mutex, OnceLock};

pub const STOP_SCHEMA: &str = "arbx.stop/1.0";
pub const CONTROL_SCHEMA: &str = "arbx.control/1.0";
pub const SOCKET: &str = "control.sock";

// ------------------------------------------------------------------ SendGate

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GateMode { Live = 0, Shadow = 1, Stopped = 2 }

impl GateMode {
    pub fn as_str(self) -> &'static str { match self { GateMode::Live => "live", GateMode::Shadow => "shadow", GateMode::Stopped => "stopped" } }
    fn from_u8(x: u8) -> GateMode { match x { 0 => GateMode::Live, 1 => GateMode::Shadow, _ => GateMode::Stopped } }
}

#[derive(Debug, Clone)]
struct GateInfo { reason: String, detail: String, since_ns: u64, sticky: bool }

/// Whether this process may send now. The mode is one relaxed atomic load (`allows`); the reason sits beside it.
pub struct SendGate { mode: AtomicU8, info: Mutex<GateInfo> }

impl SendGate {
    pub fn new() -> Arc<SendGate> {
        Arc::new(SendGate { mode: AtomicU8::new(GateMode::Live as u8), info: Mutex::new(GateInfo { reason: String::new(), detail: String::new(), since_ns: now_ns(), sticky: false }) })
    }
    #[inline]
    pub fn allows(&self) -> bool { self.mode.load(Ordering::Relaxed) == GateMode::Live as u8 }
    pub fn mode(&self) -> GateMode { GateMode::from_u8(self.mode.load(Ordering::Relaxed)) }

    /// To shadow. `sticky`: for the rest of the segment (`resume-sending` refuses). Refused once stopped. Ok(true): the
    /// gate changed; Ok(false): it was already shadow for the rest of the segment, which keeps its first reason (review
    /// F3: a pause asked of a run that sends nothing is met, not refused)
    pub fn shadow(&self, reason: &str, detail: &str, sticky: bool) -> Result<bool, String> {
        let mut i = self.info.lock().unwrap_or_else(|e| e.into_inner());
        match self.mode() {
            GateMode::Stopped => return Err("stopping".into()),
            GateMode::Shadow if i.sticky => return Ok(false),
            _ => {}
        }
        *i = GateInfo { reason: reason.into(), detail: detail.into(), since_ns: now_ns(), sticky };
        self.mode.store(GateMode::Shadow as u8, Ordering::Relaxed);
        Ok(true)
    }

    /// shadow for the rest of the segment (`--shadow`, no `--live`/`--canary`, a route program hash mismatch, `shadow`)
    pub fn sticky(&self) -> bool { self.info.lock().unwrap_or_else(|e| e.into_inner()).sticky && self.mode() == GateMode::Shadow }

    /// the reason the gate is closed ("" while live)
    pub fn reason(&self) -> String { self.info.lock().unwrap_or_else(|e| e.into_inner()).reason.clone() }

    /// Back to live: only from a non-sticky shadow (a pause)
    pub fn resume(&self, detail: &str) -> Result<(), String> {
        let mut i = self.info.lock().unwrap_or_else(|e| e.into_inner());
        match self.mode() {
            GateMode::Live => Ok(()),
            GateMode::Stopped => Err("stopping".into()),
            GateMode::Shadow if i.sticky => Err(format!("shadow for the rest of the segment ({}): restart to send", i.reason)),
            GateMode::Shadow => {
                *i = GateInfo { reason: String::new(), detail: detail.into(), since_ns: now_ns(), sticky: false };
                self.mode.store(GateMode::Live as u8, Ordering::Relaxed);
                Ok(())
            }
        }
    }

    /// Closed for good (a stop was requested)
    pub fn stop(&self, reason: &str) {
        let mut i = self.info.lock().unwrap_or_else(|e| e.into_inner());
        if self.mode() == GateMode::Stopped { return; }
        *i = GateInfo { reason: reason.into(), detail: String::new(), since_ns: now_ns(), sticky: true };
        self.mode.store(GateMode::Stopped as u8, Ordering::Relaxed);
    }

    /// status.jsonl / meta.json `send_gate`: {mode, reason, detail, since_ns, sticky}
    pub fn json(&self) -> Value {
        let i = self.info.lock().unwrap_or_else(|e| e.into_inner());
        json!({ "mode": self.mode().as_str(), "reason": Some(&i.reason).filter(|r| !r.is_empty()), "detail": Some(&i.detail).filter(|r| !r.is_empty()),
            "since_ns": i.since_ns, "sticky": i.sticky })
    }
}

// ------------------------------------------------------------------ stop reasons

/// MEASUREMENT A.5 stop reasons. `StateUnavailable` (PLAN-ADDENDUM I-4): the state stream delivered nothing within
/// `[state] boot_timeout_s` of the engine's start (cmp2: a 503 for 28 minutes, priced blind, exit 0); it is a failure
/// (exit 30, a crash to the supervisor: retried after its back-off, counted toward the crash limit), not a safety stop
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum StopReason { Deadline, Signal, Control, EquityDay, DiskBudget, StateUnavailable, Error, Panic }

impl StopReason {
    pub fn as_str(self) -> &'static str {
        match self { StopReason::Deadline => "deadline", StopReason::Signal => "signal", StopReason::Control => "control", StopReason::EquityDay => "equity_day",
            StopReason::DiskBudget => "disk_budget", StopReason::StateUnavailable => "state_unavailable", StopReason::Error => "error", StopReason::Panic => "panic" }
    }
    /// 0 deadline, 10 operator stop, 20 safety stop (ends the campaign), 30 error
    pub fn exit_code(self) -> i32 {
        match self { StopReason::Deadline => 0, StopReason::Signal | StopReason::Control => 10, StopReason::EquityDay | StopReason::DiskBudget => 20,
            StopReason::StateUnavailable | StopReason::Error | StopReason::Panic => 30 }
    }
}

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct SignalInfo { pub signo: i32, pub name: String, pub sender_pid: Option<i32>, pub sender_uid: Option<u32>, pub sender_comm: Option<String>, pub sender_cmdline: Option<String> }

#[derive(Debug, Clone, Serialize, PartialEq)]
pub struct ControlInfo { pub who: String, pub why: String, pub cmd: String }

#[derive(Debug, Clone)]
pub struct StopInfo { pub reason: StopReason, pub detail: String, pub signal: Option<SignalInfo>, pub control: Option<ControlInfo>, pub t_ns: u64 }

impl StopInfo {
    pub fn new(reason: StopReason, detail: impl Into<String>) -> StopInfo { StopInfo { reason, detail: detail.into(), signal: None, control: None, t_ns: now_ns() } }
    pub fn signal(s: SignalInfo) -> StopInfo {
        // review N4: a signal from the kernel or a terminal (Ctrl-C) has no sender process
        let detail = match s.sender_pid {
            Some(p) => format!("{} from pid {p} ({})", s.name, s.sender_comm.as_deref().unwrap_or("sender gone")),
            None => format!("{} with no sender process (kernel or terminal)", s.name),
        };
        StopInfo { signal: Some(s), ..StopInfo::new(StopReason::Signal, detail) }
    }
    pub fn control(c: ControlInfo) -> StopInfo {
        let detail = format!("{} by {}: {}", c.cmd, c.who, c.why);
        StopInfo { control: Some(c), ..StopInfo::new(StopReason::Control, detail) }
    }
}

/// The stop flag every loop polls, and the reason, set once
pub struct Stopper { flag: Arc<AtomicBool>, info: OnceLock<StopInfo>, gate: Arc<SendGate> }

impl Stopper {
    pub fn new(gate: Arc<SendGate>) -> Arc<Stopper> { Arc::new(Stopper { flag: Arc::new(AtomicBool::new(false)), info: OnceLock::new(), gate }) }
    /// Ask the run to stop. The first request's reason is kept; returns whether this one was it
    pub fn request(&self, info: StopInfo) -> bool {
        let reason = info.reason.as_str();
        let first = self.info.set(info).is_ok();
        self.gate.stop(reason);
        self.flag.store(true, Ordering::Relaxed);
        first
    }
    pub fn flag(&self) -> Arc<AtomicBool> { self.flag.clone() }
    pub fn stopping(&self) -> bool { self.flag.load(Ordering::Relaxed) }
    pub fn info(&self) -> Option<&StopInfo> { self.info.get() }
    pub fn gate(&self) -> &Arc<SendGate> { &self.gate }
}

// ------------------------------------------------------------------ session (the stop path)

/// What the run knew about its open attempts when it stopped (stop.json)
#[derive(Debug, Clone, Default)]
pub struct Drain { pub in_flight_at_stop: Option<usize>, pub unsettled: Vec<u64>, pub drained: Option<bool>, pub drain_ms: Option<f64>, pub final_status_seq: Option<u64> }

/// One run's stop path: the gate, the stopper, the run directory once it exists, and stop.json written once
pub struct Session { pub gate: Arc<SendGate>, pub stopper: Arc<Stopper>, dir: OnceLock<PathBuf>, written: AtomicBool, pub drain: Mutex<Drain>, last_panic: Mutex<Option<String>>,
    meta_stub: Mutex<Option<Value>>,
    /// review M5: an error or panic after the stop reason was set (a crash during shutdown): stop.json `secondary`, exit 30
    secondary: OnceLock<(StopReason, String)> }

impl Session {
    pub fn new() -> Arc<Session> {
        let gate = SendGate::new();
        Arc::new(Session { stopper: Stopper::new(gate.clone()), gate, dir: OnceLock::new(), written: AtomicBool::new(false), drain: Mutex::new(Drain::default()),
            last_panic: Mutex::new(None), meta_stub: Mutex::new(None), secondary: OnceLock::new() })
    }
    /// what meta.json holds if the run ends before writing the full one (`partial: true`: run, build, config)
    pub fn set_meta_stub(&self, v: Value) { *self.meta_stub.lock().unwrap_or_else(|e| e.into_inner()) = Some(v); }
    pub fn set_dir(&self, dir: PathBuf) { let _ = self.dir.set(dir); }
    pub fn dir(&self) -> Option<&Path> { self.dir.get().map(|d| d.as_path()) }
    pub fn last_panic(&self) -> Option<String> { self.last_panic.lock().unwrap().clone() }

    /// The run failed (`error` or `panic`). Before any stop request this is the stop reason; after one (a crash while
    /// stopping) the first reason stands and this is kept as stop.json `secondary`, and the exit code is 30 (review M5:
    /// a shutdown crash is not an operator stop). Then as `finish`
    pub fn fail(&self, info: StopInfo) -> i32 {
        if !self.stopper.request(info.clone()) { let _ = self.secondary.set((info.reason, info.detail.clone())); }
        self.finish(info)
    }

    /// the failure after the stop reason, if any (stop.json `secondary`)
    pub fn secondary(&self) -> Option<&(StopReason, String)> { self.secondary.get() }

    /// the exit code: the stop reason's, or 30 when the run failed after it was set
    pub fn exit_code(&self) -> i32 {
        if self.secondary.get().is_some() { 30 } else { self.stopper.info().map_or(30, |i| i.reason.exit_code()) }
    }

    /// The end of the run: keep the first stop reason (`fallback` if none was set), write stop.json and the run.log line
    /// (once), and return the exit code
    pub fn finish(&self, fallback: StopInfo) -> i32 {
        self.stopper.request(fallback);
        let info = self.stopper.info().expect("set above").clone();
        let code = self.exit_code();
        if !self.written.swap(true, Ordering::SeqCst) {
            if let Some(dir) = self.dir() {
                // a boot that failed before meta.json still says which binary and config it was
                if !dir.join("meta.json").exists() {
                    if let Some(stub) = self.meta_stub.try_lock().ok().and_then(|mut m| m.take()) {
                        let _ = write_atomic(&dir.join("meta.json"), serde_json::to_string_pretty(&stub).unwrap_or_default().as_bytes());
                    }
                }
                // try_lock: the panic hook may run while this thread holds it
                let d = self.drain.try_lock().map(|d| d.clone()).unwrap_or_default();
                let mut v = stop_json(&info, &d);
                let second = self.secondary.get();
                v["secondary"] = second.map_or(Value::Null, |(r, d)| json!({ "reason": r, "detail": d }));
                v["exit_code"] = json!(code);
                if let Err(e) = write_atomic(&dir.join("stop.json"), format!("{}\n", serde_json::to_string_pretty(&v).unwrap()).as_bytes()) {
                    eprintln!("stop.json: {e:#}");
                }
                let also = second.map(|(r, d)| format!(" (then {}: {d})", r.as_str())).unwrap_or_default();
                append_line(&dir.join("run.log"), &format!("{} stop: reason {} (exit {code}): {}{also}", now_ns(), info.reason.as_str(), info.detail));
                let _ = std::fs::remove_file(dir.join(SOCKET));
            }
        }
        code
    }
}

/// stop.json (MEASUREMENT §4.3)
pub fn stop_json(info: &StopInfo, d: &Drain) -> Value {
    json!({ "schema": STOP_SCHEMA, "ended_ns": now_ns(), "requested_ns": info.t_ns, "reason": info.reason, "detail": info.detail,
        "signal": info.signal, "control": info.control, "exit_code": info.reason.exit_code(), "secondary": null,
        "in_flight_at_stop": d.in_flight_at_stop, "drained": d.drained, "drain_ms": d.drain_ms, "unsettled": d.unsettled,
        "final_status_seq": d.final_status_seq })
}

/// write via a temporary file and a rename: a reader never sees half a file
pub fn write_atomic(path: &Path, bytes: &[u8]) -> Result<()> {
    let tmp = path.with_extension(format!("tmp{}", std::process::id()));
    std::fs::write(&tmp, bytes).with_context(|| format!("writing {}", tmp.display()))?;
    std::fs::rename(&tmp, path).with_context(|| format!("renaming to {}", path.display()))?;
    Ok(())
}

/// one line appended with a single write (review N7: the signal, control, panic and main threads do not interleave
/// inside a line)
pub fn append_line(path: &Path, line: &str) {
    if let Ok(mut f) = std::fs::OpenOptions::new().create(true).append(true).open(path) { let _ = f.write_all(format!("{line}\n").as_bytes()); }
}

/// A panic on the main thread ends the run: stop.json `reason = panic` is written at once (the unwinding that follows
/// may not get far); a panic on another thread is noted in run.log. The default hook still prints it (the segment .out)
pub fn install_panic_hook(sess: Arc<Session>) {
    let prev = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |p| {
        let msg = p.payload().downcast_ref::<&str>().map(|s| s.to_string()).or_else(|| p.payload().downcast_ref::<String>().cloned()).unwrap_or_else(|| "?".into());
        let thread = std::thread::current().name().unwrap_or("unnamed").to_string();
        let text = format!("panic in thread {thread} at {}: {msg}", p.location().map(|l| l.to_string()).unwrap_or_default());
        if thread == "main" {
            *sess.last_panic.lock().unwrap_or_else(|e| e.into_inner()) = Some(text.clone());
            sess.fail(StopInfo::new(StopReason::Panic, crate::rpc::scrub(&text)));
        } else if let Some(d) = sess.dir() {
            append_line(&d.join("run.log"), &format!("{} {}", now_ns(), crate::rpc::scrub(&text)));
        }
        prev(p);
    }));
}

// ------------------------------------------------------------------ signals

pub fn signal_name(signo: i32) -> String {
    match signo { libc::SIGINT => "SIGINT".into(), libc::SIGTERM => "SIGTERM".into(), libc::SIGHUP => "SIGHUP".into(), libc::SIGQUIT => "SIGQUIT".into(), n => format!("signal {n}") }
}

/// `/proc/<pid>/cmdline` with its NUL separators as spaces, URLs cut to their host, at most 512 characters (None once
/// the sender has exited)
pub fn cmdline(pid: i32) -> Option<String> {
    let b = std::fs::read(format!("/proc/{pid}/cmdline")).ok()?;
    let s: Vec<String> = b.split(|x| *x == 0).filter(|a| !a.is_empty()).map(|a| String::from_utf8_lossy(a).into_owned()).collect();
    (!s.is_empty()).then(|| crate::rpc::scrub(&s.join(" ")).chars().take(512).collect())
}

/// `/proc/<pid>/comm`: the sender's program name (`kill`, `run-w.sh`, `bash`)
pub fn comm(pid: i32) -> Option<String> {
    std::fs::read_to_string(format!("/proc/{pid}/comm")).ok().map(|s| s.trim().to_string()).filter(|s| !s.is_empty())
}

/// SIGINT and SIGTERM stop the run with reason `signal`, the sender's pid, uid and command line (SIGHUP is not taken:
/// the supervisor ignores it for its segments, and taking it would undo that). Later signals are recorded only.
pub fn install_signals(sess: Arc<Session>) -> Result<()> {
    use signal_hook::iterator::{exfiltrator::WithOrigin, SignalsInfo};
    let mut signals = SignalsInfo::<WithOrigin>::new([libc::SIGINT, libc::SIGTERM]).context("installing the signal handlers")?;
    std::thread::Builder::new().name("arbx-signals".into()).spawn(move || {
        for o in signals.forever() {
            let (pid, uid) = o.process.map_or((None, None), |p| (Some(p.pid), Some(p.uid)));
            let s = SignalInfo { signo: o.signal, name: signal_name(o.signal), sender_pid: pid, sender_uid: uid, sender_comm: pid.and_then(comm), sender_cmdline: pid.and_then(cmdline) };
            let who = format!("{} (pid {})", s.sender_comm.as_deref().unwrap_or("?"), pid.map_or("?".into(), |p| p.to_string()));
            let info = StopInfo::signal(s);
            let why = info.detail.clone();
            let first = sess.stopper.request(info);
            if let Some(d) = sess.dir() {
                log_control(d, "signal", &who, "stop", &why, first, if first { "stopping" } else { "already stopping" });
            }
        }
    })?;
    Ok(())
}

// ------------------------------------------------------------------ control socket

/// One control.jsonl line (MEASUREMENT §4.7)
pub fn log_control(dir: &Path, src: &str, who: &str, cmd: &str, why: &str, accepted: bool, result: &str) {
    log_control_note(dir, src, who, cmd, why, accepted, result, None);
}

/// One control.jsonl line with a `note` (a command accepted without changing anything says why)
#[allow(clippy::too_many_arguments)]
pub fn log_control_note(dir: &Path, src: &str, who: &str, cmd: &str, why: &str, accepted: bool, result: &str, note: Option<&str>) {
    let mut v = json!({ "t_ns": now_ns(), "src": src, "who": who, "cmd": cmd, "why": why, "accepted": accepted, "result": result });
    if let Some(n) = note { v["note"] = json!(n); }
    append_line(&dir.join("control.jsonl"), &v.to_string());
}

pub const COMMANDS: [&str; 5] = ["status", "pause-sending", "resume-sending", "shadow", "stop"];

/// What a command did: accepted or not; `result` (the gate's mode after it, `stopping`, or why it was refused); `note`
/// when it was accepted without changing anything
#[derive(Debug, Clone, PartialEq)]
pub struct Applied { pub accepted: bool, pub result: String, pub note: Option<String> }

/// Apply one command to the gate and stopper. `who` is always required; `why` for every command but `status`.
/// `pause-sending` and `shadow` on a gate already shadow for the rest of the segment (`--shadow`, a run without `--live`
/// or `--canary`, a route program hash mismatch, an earlier `shadow`) are accepted and change nothing: the run is not
/// sending, which is what was asked (review F3)
pub fn apply(sess: &Session, cmd: &str, who: &str, why: &str) -> Applied {
    let refuse = |r: String| Applied { accepted: false, result: r, note: None };
    let who_why = format!("{who}: {why}");
    if who.trim().is_empty() { return refuse("--who is required".into()); }
    if cmd != "status" && why.trim().is_empty() { return refuse("--why is required".into()); }
    let gate = &sess.gate;
    let res: Result<bool, String> = match cmd {
        "status" => Ok(true),
        "pause-sending" => gate.shadow("control", &format!("pause-sending by {who_why}"), false),
        "resume-sending" => gate.resume(&format!("resume-sending by {who_why}")).map(|_| true),
        "shadow" => gate.shadow("control", &format!("shadow by {who_why}"), true),
        "stop" => {
            let first = sess.stopper.request(StopInfo::control(ControlInfo { who: who.into(), why: why.into(), cmd: cmd.into() }));
            if first { Ok(true) } else { Err("already stopping".into()) }
        }
        _ => return refuse(format!("unknown command {cmd:?} (one of {})", COMMANDS.join(", "))),
    };
    match res {
        Ok(changed) => Applied { accepted: true, result: if cmd == "stop" { "stopping".into() } else { gate.mode().as_str().to_string() },
            note: (!changed).then(|| format!("already shadow for the rest of the segment ({}): nothing to change", gate.reason())) },
        Err(e) => refuse(e),
    }
}

/// the uid of a Unix socket's peer (SO_PEERCRED)
fn peer_uid(c: &std::os::unix::net::UnixStream) -> Option<u32> {
    use std::os::fd::AsRawFd;
    let mut cred: libc::ucred = unsafe { std::mem::zeroed() };
    let mut len = std::mem::size_of::<libc::ucred>() as libc::socklen_t;
    let r = unsafe { libc::getsockopt(c.as_raw_fd(), libc::SOL_SOCKET, libc::SO_PEERCRED, &mut cred as *mut _ as *mut libc::c_void, &mut len) };
    (r == 0).then_some(cred.uid)
}

/// The control socket's server: one thread, one JSON line per connection
pub struct ControlServer { pub path: PathBuf }

impl Drop for ControlServer { fn drop(&mut self) { let _ = std::fs::remove_file(&self.path); } }

/// A name for `<dir>/control.sock` that fits a socket address (108 bytes): the path itself, or, for a deep directory,
/// the directory opened and named through /proc/self/fd (the returned file must stay open while the name is used)
fn sock_name(dir: &Path) -> Result<(PathBuf, Option<std::fs::File>)> {
    use std::os::fd::AsRawFd;
    let p = dir.join(SOCKET);
    if p.as_os_str().len() < 100 { return Ok((p, None)); }
    let f = std::fs::File::open(dir).with_context(|| format!("opening {}", dir.display()))?;
    Ok((PathBuf::from(format!("/proc/self/fd/{}/{SOCKET}", f.as_raw_fd())), Some(f)))
}

pub fn serve(sess: Arc<Session>, dir: &Path) -> Result<ControlServer> {
    use std::os::unix::fs::PermissionsExt;
    let path = dir.join(SOCKET);
    let _ = std::fs::remove_file(&path);
    let (name, _dir_fd) = sock_name(dir)?;
    let listener = std::os::unix::net::UnixListener::bind(&name).with_context(|| format!("binding {}", path.display()))?;
    std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o600))?;
    let dir = dir.to_path_buf();
    std::thread::Builder::new().name("arbx-control".into()).spawn(move || {
        for conn in listener.incoming() {
            let Ok(mut c) = conn else { continue };
            let _ = c.set_read_timeout(Some(std::time::Duration::from_secs(2)));
            let _ = c.set_write_timeout(Some(std::time::Duration::from_secs(2)));
            // review N5: only this run's user (or root) may drive it, whatever the socket file's mode
            let uid = unsafe { libc::getuid() };
            match peer_uid(&c) {
                Some(p) if p == uid || p == 0 => {}
                p => {
                    let who = p.map_or("uid ?".to_string(), |p| format!("uid {p}"));
                    log_control(&dir, "socket", &who, "?", "", false, "refused: not this run's user");
                    let _ = writeln!(c, "{}", json!({ "accepted": false, "result": "refused: not this run's user" }));
                    continue;
                }
            }
            let mut line = String::new();
            let _ = std::io::BufReader::new(&c).take(64 * 1024).read_line(&mut line);
            let reply = match serde_json::from_str::<Value>(&line) {
                Ok(v) => {
                    let (cmd, who, why) = (v["cmd"].as_str().unwrap_or(""), v["who"].as_str().unwrap_or(""), v["why"].as_str().unwrap_or(""));
                    let Applied { accepted: ok, result, note } = apply(&sess, cmd, who, why);
                    log_control_note(&dir, "socket", who, cmd, why, ok, &result, note.as_deref());
                    json!({ "accepted": ok, "result": result, "note": note, "send_gate": sess.gate.json(), "stopping": sess.stopper.stopping(),
                        "stop_reason": sess.stopper.info().map(|i| i.reason.as_str()), "pid": std::process::id(), "dir": dir.display().to_string(),
                        "last_status": if cmd == "status" { last_line(&dir.join("status.jsonl")) } else { Value::Null } })
                }
                Err(e) => json!({ "accepted": false, "result": format!("not a JSON command line: {e}") }),
            };
            let _ = writeln!(c, "{reply}");
        }
    })?;
    Ok(ControlServer { path })
}


/// the last line of a (possibly large) JSON-lines file, parsed
fn last_line(path: &Path) -> Value {
    use std::io::{Seek, SeekFrom};
    let Ok(mut f) = std::fs::File::open(path) else { return Value::Null };
    let len = f.metadata().map(|m| m.len()).unwrap_or(0);
    let _ = f.seek(SeekFrom::Start(len.saturating_sub(256 * 1024)));
    let mut s = String::new();
    let _ = f.read_to_string(&mut s);
    s.lines().rev().find_map(|l| serde_json::from_str(l).ok()).unwrap_or(Value::Null)
}

/// Whether a run's control socket has a live server (a running segment): a connection is accepted. A stale socket
/// file left by a killed run refuses it. Nothing is sent (the server answers an empty line and logs nothing)
pub fn socket_alive(run_dir: &Path) -> bool {
    let Ok((name, _dir_fd)) = sock_name(run_dir) else { return false };
    std::os::unix::net::UnixStream::connect(&name).is_ok()
}

/// `arbx ctl`: send one command to a run's socket, return its reply
pub fn send_command(run_dir: &Path, cmd: &str, who: &str, why: &str) -> Result<Value> {
    let path = run_dir.join(SOCKET);
    let (name, _dir_fd) = sock_name(run_dir)?;
    let mut c = std::os::unix::net::UnixStream::connect(&name).with_context(|| format!("connecting to {} (is the run alive?)", path.display()))?;
    c.set_read_timeout(Some(std::time::Duration::from_secs(5)))?;
    writeln!(c, "{}", json!({ "cmd": cmd, "who": who, "why": why }))?;
    let mut line = String::new();
    std::io::BufReader::new(&c).read_line(&mut line)?;
    if line.trim().is_empty() { bail!("no reply from {}", path.display()); }
    Ok(serde_json::from_str(&line)?)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("arbx-ctl-{name}-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    fn lines(p: &Path) -> Vec<Value> { std::fs::read_to_string(p).unwrap_or_default().lines().map(|l| serde_json::from_str(l).unwrap()).collect() }

    #[test]
    fn gate_modes() {
        let g = SendGate::new();
        assert!(g.allows());
        g.shadow("control", "pause", false).unwrap();
        assert!(!g.allows() && g.mode() == GateMode::Shadow);
        g.resume("go").unwrap();
        assert!(g.allows());
        assert_eq!(g.shadow("forced_shadow", "--shadow", true), Ok(true));
        assert!(g.sticky() && g.reason() == "forced_shadow");
        assert!(g.resume("go").is_err(), "sticky");
        assert_eq!(g.shadow("control", "pause", false), Ok(false), "review F3: a pause of a sticky shadow is met, and changes nothing");
        assert_eq!(g.shadow("control", "shadow", true), Ok(false));
        assert_eq!(g.json()["reason"], "forced_shadow", "a sticky shadow keeps its reason");
        assert!(g.sticky());
        g.stop("signal");
        assert_eq!(g.mode(), GateMode::Stopped);
        assert!(g.resume("go").is_err() && g.shadow("control", "x", false).is_err());
        assert_eq!(g.json()["mode"], "stopped");
    }

    #[test]
    fn exit_codes_and_first_reason_wins() {
        assert_eq!([StopReason::Deadline, StopReason::Signal, StopReason::Control, StopReason::EquityDay, StopReason::DiskBudget, StopReason::StateUnavailable,
            StopReason::Error, StopReason::Panic].map(StopReason::exit_code), [0, 10, 10, 20, 20, 30, 30, 30]);
        // WP-04 / PLAN-ADDENDUM I-4: its own name in stop.json (the supervisor classes it a crash: exit 30, not error)
        assert_eq!(StopReason::StateUnavailable.as_str(), "state_unavailable");
        assert_eq!(serde_json::to_value(StopReason::StateUnavailable).unwrap(), serde_json::json!("state_unavailable"));
        let s = Session::new();
        let d = tmp("first");
        s.set_dir(d.clone());
        assert!(s.stopper.request(StopInfo::control(ControlInfo { who: "moiz".into(), why: "restart for WP-02".into(), cmd: "stop".into() })));
        assert!(!s.stopper.request(StopInfo::new(StopReason::Deadline, "deadline")));
        assert_eq!(s.gate.mode(), GateMode::Stopped);
        assert_eq!(s.finish(StopInfo::new(StopReason::Error, "x")), 10);
        assert_eq!(s.finish(StopInfo::new(StopReason::Error, "x")), 10, "written once, same code");
        let v: Value = serde_json::from_str(&std::fs::read_to_string(d.join("stop.json")).unwrap()).unwrap();
        assert_eq!((v["schema"].as_str(), v["reason"].as_str(), v["exit_code"].as_i64()), (Some(STOP_SCHEMA), Some("control"), Some(10)));
        assert_eq!((v["control"]["who"].as_str(), v["control"]["why"].as_str()), (Some("moiz"), Some("restart for WP-02")));
        assert!(v["signal"].is_null());
        assert!(std::fs::read_to_string(d.join("run.log")).unwrap().contains("stop: reason control (exit 10)"));
        assert!(!d.join("meta.json").exists(), "no stub, no meta");
        // a failed boot leaves the partial meta.json; a run that wrote its meta.json keeps it
        let s = Session::new();
        let d2 = tmp("stub");
        s.set_dir(d2.clone());
        s.set_meta_stub(json!({ "schema": "arbx.meta/2.0", "partial": true }));
        s.finish(StopInfo::new(StopReason::Error, "boot failed"));
        assert_eq!(serde_json::from_str::<Value>(&std::fs::read_to_string(d2.join("meta.json")).unwrap()).unwrap()["partial"], true);
        let s = Session::new();
        std::fs::write(d2.join("meta.json"), "{\"full\":true}").unwrap();
        s.set_dir(d2.clone());
        s.set_meta_stub(json!({ "partial": true }));
        s.finish(StopInfo::new(StopReason::Deadline, "x"));
        assert_eq!(std::fs::read_to_string(d2.join("meta.json")).unwrap(), "{\"full\":true}");
        let _ = std::fs::remove_dir_all(&d);
        let _ = std::fs::remove_dir_all(&d2);
    }

    /// review M5: a failure after the stop request keeps the stop reason, is recorded as `secondary`, and exits 30; a
    /// failure with no stop before it is the reason itself
    #[test]
    fn a_crash_while_stopping_is_not_an_operator_stop() {
        let d = tmp("secondary");
        let s = Session::new();
        s.set_dir(d.clone());
        s.stopper.request(StopInfo::control(ControlInfo { who: "supervisor".into(), why: "next: x".into(), cmd: "stop".into() }));
        assert_eq!(s.fail(StopInfo::new(StopReason::Error, "writing status.jsonl: disk full")), 30);
        let v: Value = serde_json::from_str(&std::fs::read_to_string(d.join("stop.json")).unwrap()).unwrap();
        assert_eq!((v["reason"].as_str(), v["exit_code"].as_i64()), (Some("control"), Some(30)));
        assert_eq!((v["secondary"]["reason"].as_str(), v["secondary"]["detail"].as_str()), (Some("error"), Some("writing status.jsonl: disk full")));
        assert!(std::fs::read_to_string(d.join("run.log")).unwrap().contains("stop: reason control (exit 30): stop by supervisor: next: x (then error: writing status.jsonl: disk full)"));
        assert_eq!(s.finish(StopInfo::new(StopReason::Error, "x")), 30, "the same code after");
        // no stop before: the failure is the reason, no secondary
        let s = Session::new();
        let d2 = tmp("secondary2");
        s.set_dir(d2.clone());
        assert_eq!(s.fail(StopInfo::new(StopReason::Panic, "boom")), 30);
        let v: Value = serde_json::from_str(&std::fs::read_to_string(d2.join("stop.json")).unwrap()).unwrap();
        assert_eq!((v["reason"].as_str(), v["secondary"].is_null()), (Some("panic"), true));
        // a clean stop: no secondary, its own code
        let s = Session::new();
        let d3 = tmp("secondary3");
        s.set_dir(d3.clone());
        s.stopper.request(StopInfo::new(StopReason::Deadline, "--minutes reached"));
        assert_eq!(s.finish(StopInfo::new(StopReason::Error, "the run ended without a stop reason")), 0);
        let v: Value = serde_json::from_str(&std::fs::read_to_string(d3.join("stop.json")).unwrap()).unwrap();
        assert!(v["secondary"].is_null() && v["exit_code"] == 0);
        for x in [d, d2, d3] { let _ = std::fs::remove_dir_all(x); }
    }

    /// review N4: a signal with no sender process (the kernel, a terminal's Ctrl-C) says so
    #[test]
    fn signal_detail() {
        let s = |pid: Option<i32>, comm: Option<&str>| StopInfo::signal(SignalInfo { signo: libc::SIGINT, name: "SIGINT".into(), sender_pid: pid, sender_uid: None,
            sender_comm: comm.map(str::to_string), sender_cmdline: None }).detail;
        assert_eq!(s(Some(42), Some("run-w.sh")), "SIGINT from pid 42 (run-w.sh)");
        assert_eq!(s(Some(42), None), "SIGINT from pid 42 (sender gone)");
        assert_eq!(s(None, None), "SIGINT with no sender process (kernel or terminal)");
    }

    /// commands through the real socket: each is applied, answered and logged; bad ones are refused and logged too
    #[test]
    fn control_socket_commands() {
        let d = tmp("sock");
        let s = Session::new();
        s.set_dir(d.clone());
        let _srv = serve(s.clone(), &d).unwrap();
        use std::os::unix::fs::PermissionsExt;
        assert_eq!(std::fs::metadata(d.join(SOCKET)).unwrap().permissions().mode() & 0o777, 0o600);
        std::fs::write(d.join("status.jsonl"), "{\"t_ns\":1}\n{\"t_ns\":2}\n").unwrap();
        let r = send_command(&d, "status", "moiz", "").unwrap();
        assert_eq!((r["accepted"].as_bool(), r["send_gate"]["mode"].as_str(), r["last_status"]["t_ns"].as_u64()), (Some(true), Some("live"), Some(2)));
        assert_eq!(send_command(&d, "pause-sending", "moiz", "").unwrap()["accepted"], false, "why is required");
        assert_eq!(send_command(&d, "pause-sending", "", "x").unwrap()["accepted"], false, "who is required");
        assert_eq!(send_command(&d, "pause-sending", "moiz", "checking the leader list").unwrap()["result"], "shadow");
        assert!(!s.gate.allows());
        assert_eq!(send_command(&d, "resume-sending", "moiz", "checked").unwrap()["result"], "live");
        assert!(s.gate.allows());
        assert_eq!(send_command(&d, "shadow", "moiz", "odd fills").unwrap()["result"], "shadow");
        assert_eq!(send_command(&d, "resume-sending", "moiz", "try").unwrap()["accepted"], false, "shadow is for the rest of the segment");
        // review F3: pausing a run that is shadow for the rest of the segment is accepted, changes nothing, and says so
        let r = send_command(&d, "pause-sending", "supervisor", "pause file").unwrap();
        assert_eq!((r["accepted"].as_bool(), r["result"].as_str(), r["send_gate"]["sticky"].as_bool(), r["send_gate"]["reason"].as_str()),
            (Some(true), Some("shadow"), Some(true), Some("control")));
        assert!(r["note"].as_str().unwrap().contains("nothing to change"), "{r}");
        assert_eq!(send_command(&d, "reboot", "moiz", "x").unwrap()["accepted"], false);
        assert!(!s.stopper.stopping());
        assert_eq!(send_command(&d, "stop", "moiz", "next segment").unwrap()["result"], "stopping");
        assert!(s.stopper.stopping());
        assert_eq!(s.stopper.info().unwrap().reason, StopReason::Control);
        let l = lines(&d.join("control.jsonl"));
        assert_eq!(l.len(), 10, "every command is logged, accepted or not");
        assert_eq!((l[7]["cmd"].as_str(), l[7]["accepted"].as_bool()), (Some("pause-sending"), Some(true)));
        assert!(l[7]["note"].is_string() && l[3]["note"].is_null());
        assert!(l.iter().all(|x| x["src"] == "socket" && x["t_ns"].is_u64()));
        assert_eq!((l[3]["cmd"].as_str(), l[3]["who"].as_str(), l[3]["why"].as_str(), l[3]["accepted"].as_bool()),
            (Some("pause-sending"), Some("moiz"), Some("checking the leader list"), Some(true)));
        assert_eq!(l[1]["accepted"], false);
        let _ = std::fs::remove_dir_all(&d);
    }

    /// a run directory deeper than a socket address allows (108 bytes) still gets its socket
    #[test]
    fn control_socket_in_a_deep_directory() {
        let d = tmp("deep").join("a-directory-name-long-enough-to-push-the-socket-path-past-the-108-byte-limit-of-sun-path");
        std::fs::create_dir_all(&d).unwrap();
        assert!(d.join(SOCKET).as_os_str().len() > 108);
        let s = Session::new();
        let _srv = serve(s.clone(), &d).unwrap();
        assert!(d.join(SOCKET).exists());
        assert_eq!(send_command(&d, "pause-sending", "moiz", "deep").unwrap()["accepted"], true);
        assert!(!s.gate.allows());
        let _ = std::fs::remove_dir_all(d.parent().unwrap());
    }

    #[test]
    fn cmdline_of_this_process() {
        let c = cmdline(std::process::id() as i32).unwrap();
        assert!(!c.contains('\0') && !c.is_empty());
        assert!(comm(std::process::id() as i32).is_some());
        assert!(cmdline(i32::MAX).is_none());
        assert_eq!(signal_name(libc::SIGINT), "SIGINT");
    }
}

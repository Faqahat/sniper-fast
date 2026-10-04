//! PLAN WP-01 acceptance, through the real binary: the hidden `arbx wait-signal --dir <tmp>` installs the same signal
//! handler, control socket and stop path as `arbx run`, without feeds or RPC.
//! - SIGINT sent by this test process: stop.json `reason = signal`, the sender pid is this process, exit code 10;
//! - SIGTERM likewise;
//! - `arbx ctl ... stop`: `reason = control` with who and why, exit 10; a refused command exits 2;
//! - the deadline: `reason = deadline`, exit 0;
//! - a panic on the main thread: `reason = panic` (written by the panic hook), exit 30;
//! - an error after a SIGINT (a crash while stopping): the reason stays `signal`, `secondary` is the error, exit 30
//!   (review M5).
use serde_json::Value;
use std::io::BufRead;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

const BIN: &str = env!("CARGO_BIN_EXE_arbx");

fn tmp(name: &str) -> PathBuf {
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    std::env::temp_dir().join(format!("arbx-stop-{name}-{}-{t}", std::process::id()))
}

/// start `arbx wait-signal`, wait for its "ready <pid>" line
fn start(dir: &Path, extra: &[&str]) -> (Child, i32) {
    let mut c = Command::new(BIN).arg("wait-signal").arg("--dir").arg(dir).args(extra).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    let mut line = String::new();
    std::io::BufReader::new(c.stdout.take().unwrap()).read_line(&mut line).unwrap();
    let pid: i32 = line.trim().strip_prefix("ready ").unwrap_or_else(|| panic!("not ready: {line:?}")).parse().unwrap();
    assert_eq!(pid as u32, c.id());
    (c, pid)
}

fn wait(c: &mut Child) -> i32 {
    let t0 = Instant::now();
    loop {
        if let Some(st) = c.try_wait().unwrap() { return st.code().expect("exited, not killed by a signal"); }
        if t0.elapsed() > Duration::from_secs(20) { let _ = c.kill(); panic!("did not stop"); }
        std::thread::sleep(Duration::from_millis(10));
    }
}

fn json(p: &Path) -> Value { serde_json::from_str(&std::fs::read_to_string(p).unwrap()).unwrap() }

fn signal_stop(sig: i32, name: &str) {
    let dir = tmp(name);
    let (mut c, pid) = start(&dir, &[]);
    assert_eq!(unsafe { libc::kill(pid, sig) }, 0);
    assert_eq!(wait(&mut c), 10, "operator stop");
    let v = json(&dir.join("stop.json"));
    assert_eq!(v["schema"], "arbx.stop/1.0");
    assert_eq!(v["reason"], "signal");
    assert_eq!(v["exit_code"], 10);
    let s = &v["signal"];
    assert_eq!((s["signo"].as_i64(), s["name"].as_str()), (Some(sig as i64), Some(name)));
    assert_eq!(s["sender_pid"].as_u64(), Some(std::process::id() as u64), "the sender is this test process");
    assert_eq!(s["sender_uid"].as_u64(), Some(unsafe { libc::getuid() } as u64));
    let cmd = s["sender_cmdline"].as_str().expect("read from /proc while we are alive");
    assert!(cmd.contains("stop_path"), "{cmd}");
    assert!(v["detail"].as_str().unwrap().contains(&format!("from pid {}", std::process::id())));
    assert!(s["sender_comm"].as_str().is_some_and(|c| !c.is_empty()));
    assert!(v["ended_ns"].as_u64().unwrap() >= v["requested_ns"].as_u64().unwrap());
    // no executor: the drain fields are null, not "0 in flight, drained" (review M11)
    assert!(v["in_flight_at_stop"].is_null() && v["drained"].is_null() && v["secondary"].is_null(), "{v}");
    // the same stop in run.log and control.jsonl (src = signal)
    assert!(std::fs::read_to_string(dir.join("run.log")).unwrap().contains("stop: reason signal (exit 10)"));
    let ctl = json_lines(&dir.join("control.jsonl"));
    assert_eq!((ctl[0]["src"].as_str(), ctl[0]["cmd"].as_str(), ctl[0]["accepted"].as_bool()), (Some("signal"), Some("stop"), Some(true)));
    assert!(!dir.join("control.sock").exists(), "the socket is removed at exit");
    let _ = std::fs::remove_dir_all(&dir);
}

fn json_lines(p: &Path) -> Vec<Value> { std::fs::read_to_string(p).unwrap().lines().map(|l| serde_json::from_str(l).unwrap()).collect() }

#[test]
fn sigint_records_its_sender_and_exits_10() { signal_stop(libc::SIGINT, "SIGINT"); }

#[test]
fn sigterm_records_its_sender_and_exits_10() { signal_stop(libc::SIGTERM, "SIGTERM"); }

#[test]
fn control_socket_stop_exits_10_with_who_and_why() {
    let dir = tmp("ctl");
    let (mut c, _) = start(&dir, &[]);
    let ctl = |args: &[&str]| Command::new(BIN).arg("ctl").arg("--run").arg(&dir).args(args).output().unwrap();
    let st = ctl(&["status", "--who", "test"]);
    assert_eq!(st.status.code(), Some(0));
    let r: Value = serde_json::from_slice(&st.stdout).unwrap();
    assert_eq!((r["accepted"].as_bool(), r["send_gate"]["mode"].as_str()), (Some(true), Some("live")));
    assert_eq!(ctl(&["stop", "--who", "test"]).status.code(), Some(2), "refused: no --why");
    let out = ctl(&["stop", "--who", "test", "--why", "WP-01 integration test"]);
    assert_eq!(out.status.code(), Some(0), "{}", String::from_utf8_lossy(&out.stderr));
    assert_eq!(wait(&mut c), 10);
    let v = json(&dir.join("stop.json"));
    assert_eq!((v["reason"].as_str(), v["exit_code"].as_i64()), (Some("control"), Some(10)));
    assert_eq!((v["control"]["who"].as_str(), v["control"]["why"].as_str(), v["control"]["cmd"].as_str()), (Some("test"), Some("WP-01 integration test"), Some("stop")));
    assert!(v["signal"].is_null());
    let l = json_lines(&dir.join("control.jsonl"));
    assert_eq!(l.iter().map(|x| (x["cmd"].as_str().unwrap(), x["accepted"].as_bool().unwrap())).collect::<Vec<_>>(), [("status", true), ("stop", false), ("stop", true)]);
    assert!(ctl(&["status", "--who", "test"]).status.code() != Some(0), "gone");
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn deadline_exits_0() {
    let dir = tmp("deadline");
    let (mut c, _) = start(&dir, &["--minutes", "0.002"]);
    assert_eq!(wait(&mut c), 0);
    let v = json(&dir.join("stop.json"));
    assert_eq!((v["reason"].as_str(), v["exit_code"].as_i64()), (Some("deadline"), Some(0)));
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn main_thread_panic_exits_30_with_stop_json() {
    let dir = tmp("panic");
    let (mut c, _) = start(&dir, &["--panic"]);
    assert_eq!(wait(&mut c), 30);
    let v = json(&dir.join("stop.json"));
    assert_eq!((v["reason"].as_str(), v["exit_code"].as_i64()), (Some("panic"), Some(30)));
    assert!(v["detail"].as_str().unwrap().contains("wait-signal --panic: a test panic"), "{v}");
    let mut err = String::new();
    std::io::Read::read_to_string(&mut c.stderr.take().unwrap(), &mut err).unwrap();
    assert!(err.contains("a test panic"), "the default hook still prints it (the segment .out): {err}");
    let _ = std::fs::remove_dir_all(&dir);
}

/// review M5: a failure while stopping is not an operator stop: exit 30, the signal stays the reason, the error is
/// `secondary` (the supervisor classes the segment a crash)
#[test]
fn an_error_after_sigint_exits_30_with_a_secondary_reason() {
    let dir = tmp("secondary");
    let (mut c, pid) = start(&dir, &["--fail-after-stop"]);
    assert_eq!(unsafe { libc::kill(pid, libc::SIGINT) }, 0);
    assert_eq!(wait(&mut c), 30);
    let v = json(&dir.join("stop.json"));
    assert_eq!((v["reason"].as_str(), v["exit_code"].as_i64()), (Some("signal"), Some(30)));
    assert_eq!(v["secondary"]["reason"], "error");
    assert!(v["secondary"]["detail"].as_str().unwrap().contains("a test failure while stopping"), "{v}");
    assert!(std::fs::read_to_string(dir.join("run.log")).unwrap().contains("stop: reason signal (exit 30)"));
    let _ = std::fs::remove_dir_all(&dir);
}

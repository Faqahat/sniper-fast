//! PLAN-ADDENDUM WP-20, through the real binary, with an empty environment (no token, no chat id: nothing can reach
//! Telegram, and nothing here tries):
//! - `arbx check` names the alerts and the watchdog of both shipped configs;
//! - `arbx alert-test` without the variables says which are missing and exits 1, without a network call;
//! - `arbx run` with `[alerts] enabled = true` and no variables: one warning in run.log, and the run goes on to its own
//!   end (here a boot without an RPC provider, stop.json `error`): alerts are never fatal;
//! - `arbx watchdog --once` on an empty runs directory: "not running", exit 1;
//! - `arbx watchdog` holds its runs directory's lock (a second one refuses to start), writes watchdog.jsonl, and stops
//!   on SIGTERM with exit 0.
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

const BIN: &str = env!("CARGO_BIN_EXE_arbx");

fn tmp(name: &str) -> PathBuf {
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let d = std::env::temp_dir().join(format!("arbx-alerts-{name}-{}-{t}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn repo(rel: &str) -> PathBuf { Path::new(env!("CARGO_MANIFEST_DIR")).join(rel) }

/// the shipped Stage-0 config with its runs directory (and out_dir) moved to `runs`, no free-space floor, and the repo's
/// crowded list in place of the server's path (WP-05: a configured list must load before anything starts)
fn config_in(d: &Path, runs: &Path) -> PathBuf {
    let text = std::fs::read_to_string(repo("deploy/arbx-stage0.toml")).unwrap();
    let floor = text.lines().find(|l| l.starts_with("min_free_gb")).expect("min_free_gb").to_string();
    let crowded = text.lines().find(|l| l.starts_with("crowded_pools_file")).expect("crowded_pools_file").to_string();
    let r = runs.display().to_string();
    let text = text.replace(&floor, "min_free_gb = 0").replace("out_dir = \"/root/arbx/runs\"", &format!("out_dir = \"{r}\""))
        .replace("runs_dir = \"/root/arbx/runs\"", &format!("runs_dir = \"{r}\""))
        .replace(&crowded, &format!("crowded_pools_file = {:?}", repo("data/crowded-pools.json").display().to_string()));
    let p = d.join("stage0.toml");
    std::fs::write(&p, text).unwrap();
    p
}

fn out(c: &mut Command) -> (Option<i32>, String, String) {
    let o = c.env_clear().output().unwrap();
    (o.status.code(), String::from_utf8_lossy(&o.stdout).into_owned(), String::from_utf8_lossy(&o.stderr).into_owned())
}

#[test]
fn check_names_the_alerts_and_the_watchdog() {
    for f in ["deploy/arbx-stage0.toml", "deploy/arb.toml"] {
        let (code, so, se) = out(Command::new(BIN).args(["check", "--config"]).arg(repo(f)));
        assert_eq!(code, Some(0), "{f}: {so}{se}");
        assert!(so.contains("alerts: on (Telegram; token from $TELEGRAM_BOT_TOKEN, chat from $TELEGRAM_CHAT_ID): at most 20 messages a minute, dedup 600 s"), "{f}: {so}");
        assert!(so.contains("watchdog: watches /root/arbx/runs (not running after 120 s"), "{f}: {so}");
    }
}

#[test]
fn alert_test_without_the_variables_says_so() {
    let d = tmp("test");
    let conf = config_in(&d, &d);
    let (code, so, se) = out(Command::new(BIN).args(["alert-test", "--config"]).arg(&conf));
    assert_eq!(code, Some(1), "{so}{se}");
    assert!(so.contains("failed: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID not set"), "{so}{se}");
    let (code, so, se) = out(Command::new(BIN).args(["notify", "--text", "FT-001 goal", "--config"]).arg(&conf));
    assert!(code == Some(1) && so.contains("failed: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID not set"), "{so}{se}");
    let _ = std::fs::remove_dir_all(&d);
}

/// alerts on in the config, the variables missing: one warning, and the run is not stopped by it
#[test]
fn a_run_without_the_variables_warns_once_and_goes_on() {
    let d = tmp("run");
    let runs = d.join("runs");
    std::fs::create_dir_all(&runs).unwrap();
    let conf = config_in(&d, &runs);
    let (code, so, se) = out(Command::new(BIN).args(["run", "--minutes", "0.01", "--name", "seg", "--config"]).arg(&conf).arg("--env-file").arg(d.join("missing.env")));
    assert_eq!(code, Some(30), "the boot fails on its own (no RPC provider): {so}{se}");
    assert!(format!("{so}{se}").contains("no RPC provider configured"));
    let log = std::fs::read_to_string(runs.join("seg").join("run.log")).unwrap();
    assert_eq!(log.matches("WARNING: alerts off: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID not set").count(), 1, "{log}");
    let stop: Value = serde_json::from_str(&std::fs::read_to_string(runs.join("seg").join("stop.json")).unwrap()).unwrap();
    assert_eq!(stop["reason"], "error");
    assert!(!log.contains("panicked") && !se.contains("panicked"));
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn the_watchdog_once_and_its_lock() {
    let d = tmp("wd");
    let runs = d.join("runs");
    std::fs::create_dir_all(&runs).unwrap();
    let conf = config_in(&d, &runs);
    let (code, so, se) = out(Command::new(BIN).args(["watchdog", "--once", "--config"]).arg(&conf));
    assert_eq!(code, Some(1), "{so}{se}");
    let v: Value = serde_json::from_str(&so).unwrap();
    assert_eq!((v["state"].as_str(), v["live"].as_u64()), (Some("not running"), Some(0)));
    // the long-running one: its lock, its journal, a clean stop on SIGTERM
    let mut first = Command::new(BIN).args(["watchdog", "--config"]).arg(&conf).env_clear().stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    let journal = runs.join("watchdog.jsonl");
    let t0 = Instant::now();
    while !std::fs::read_to_string(&journal).unwrap_or_default().contains("\"start\"") {
        assert!(t0.elapsed() < Duration::from_secs(20), "the watchdog did not start");
        std::thread::sleep(Duration::from_millis(20));
    }
    let (code, so, se) = out(Command::new(BIN).args(["watchdog", "--config"]).arg(&conf));
    assert_ne!(code, Some(0), "{so}{se}");
    assert!(se.contains("another arbx watchdog holds") && se.contains(&first.id().to_string()), "{se}");
    let lock = runs.join(".watchdog.lock");
    assert_eq!(std::fs::read_to_string(&lock).unwrap().trim(), first.id().to_string(), "the lock file names the running watchdog");
    // SAFETY: a signal to the child this test started
    assert_eq!(unsafe { libc::kill(first.id() as i32, libc::SIGTERM) }, 0);
    let t0 = Instant::now();
    let code = loop {
        if let Some(s) = first.try_wait().unwrap() { break s.code(); }
        assert!(t0.elapsed() < Duration::from_secs(30), "the watchdog did not stop");
        std::thread::sleep(Duration::from_millis(20));
    };
    let o = first.wait_with_output().unwrap();
    let text = String::from_utf8_lossy(&o.stdout).into_owned();
    assert_eq!(code, Some(0), "{text}");
    assert!(text.contains("watchdog: started") && text.contains("WARNING: alerts off") && text.contains("watchdog: stopping"), "{text}");
    let lines: Vec<Value> = std::fs::read_to_string(&journal).unwrap().lines().map(|l| serde_json::from_str(l).unwrap()).collect();
    assert!(lines.iter().any(|l| l["event"] == "start") && lines.iter().any(|l| l["event"] == "stop"), "{lines:?}");
    // nothing running and its grace not over yet: no verdict in the journal
    assert!(!lines.iter().any(|l| l["event"] == "down"));
    // a clean stop empties the lock file: the stop command (`flock -n … || kill $(cat …)`) never names a reused pid
    assert_eq!(std::fs::read_to_string(&lock).unwrap(), "", "emptied at exit");
    let _ = std::fs::remove_dir_all(&d);
}

//! WP-07, through the real binary: `arbx campaign` freezes the binary and the config, runs its segments one after the
//! other (each `arbx run` of the frozen copies, started only once the previous one's process has exited), classifies how
//! each ended and writes campaign.json, events.jsonl and spend.json; `arbx campaign-equity` reads the campaign back; the
//! frz canary config passes `arbx check`. Each segment here is a boot that fails at once (no RPC provider: the
//! environment is empty), so nothing reaches the network.
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;

const BIN: &str = env!("CARGO_BIN_EXE_arbx");

fn tmp() -> PathBuf {
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let d = std::env::temp_dir().join(format!("arbx-campaign-it-{}-{t}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    d
}
fn json(p: &Path) -> Value { serde_json::from_str(&std::fs::read_to_string(p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))).unwrap() }
fn repo(rel: &str) -> PathBuf { Path::new(env!("CARGO_MANIFEST_DIR")).join(rel) }

/// a copy of the stage-0 config that can boot here: no free-space floor, the repo's crowded list, its runs under `d`
fn stage0_copy(d: &Path) -> PathBuf {
    let text = std::fs::read_to_string(repo("deploy/arbx-stage0.toml")).unwrap();
    let floor = text.lines().find(|l| l.starts_with("min_free_gb")).unwrap().to_string();
    let crowded = text.lines().find(|l| l.starts_with("crowded_pools_file")).unwrap().to_string();
    let out = text.lines().find(|l| l.starts_with("out_dir")).unwrap().to_string();
    let conf = d.join("stage0.toml");
    std::fs::write(&conf, text.replace(&floor, "min_free_gb = 0").replace(&crowded, &format!("crowded_pools_file = {:?}", repo("data/crowded-pools.json").display().to_string()))
        .replace(&out, &format!("out_dir = {:?}", d.join("runs").display().to_string()))).unwrap();
    conf
}

/// `stage0_copy` with `[canary] enabled = true` (a canary needs both the flag and the config)
fn canary_copy(d: &Path) -> PathBuf {
    let conf = stage0_copy(d);
    let text = std::fs::read_to_string(&conf).unwrap();
    let c = d.join("canary.toml");
    std::fs::write(&c, text.replacen("[canary]\n", "[canary]\nenabled = true\n", 1)).unwrap();
    c
}

#[test]
fn a_campaign_runs_its_segments_one_after_the_other() {
    let d = tmp();
    let conf = stage0_copy(&d);
    let runs = d.join("runs");
    // refusals before anything is made: a canary campaign without a test budget, a budget over the hard cap
    let out = Command::new(BIN).env_clear().args(["campaign", "--name", "x", "--hours", "1", "--mode", "canary", "--config"]).arg(&conf).arg("--runs").arg(&runs).output().unwrap();
    assert!(!out.status.success());
    assert!(String::from_utf8_lossy(&out.stderr).contains("[canary] enabled"), "{}", String::from_utf8_lossy(&out.stderr));
    let out = Command::new(BIN).env_clear().args(["campaign", "--name", "x", "--hours", "1", "--test-budget-lamports", "34000001", "--config"]).arg(&conf).arg("--runs").arg(&runs)
        .output().unwrap();
    assert!(String::from_utf8_lossy(&out.stderr).contains("hard cap"), "{}", String::from_utf8_lossy(&out.stderr));
    assert!(!runs.join("x").exists());
    // a shadow campaign of two segments (each fails at boot: no RPC provider), no back-off
    let out = Command::new(BIN).env_clear().args(["campaign", "--name", "t1", "--hours", "1", "--segment-min", "2", "--max-segments", "2", "--who", "test", "--force",
        "--poll-ms", "20", "--backoff-s", "0", "--config"]).arg(&conf).arg("--runs").arg(&runs).output().unwrap();
    let text = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    assert_eq!(out.status.code(), Some(0), "{text}");
    let dir = runs.join("t1");
    let c = json(&dir.join("campaign.json"));
    assert_eq!((c["schema"].as_str(), c["mode"].as_str(), c["operator"].as_str(), c["end_reason"].as_str(), c["forced"].as_bool()),
        (Some("arbx.campaign/1.1"), Some("shadow"), Some("test"), Some("max segments (2)"), Some(true)));
    let segs = c["segments"].as_array().unwrap();
    assert_eq!(segs.len(), 2);
    for s in segs { assert_eq!((s["exit_code"].as_i64(), s["stop_reason"].as_str(), s["class"].as_str()), (Some(30), Some("error"), Some("crash")), "{s}"); }
    assert!(segs[1]["started_ns"].as_u64() >= segs[0]["ended_ns"].as_u64(), "the second started after the first had exited");
    // frozen: the binary (0555) and the config (0444) the segments ran, its check and provenance
    use std::os::unix::fs::PermissionsExt;
    let bin = PathBuf::from(c["binary"]["path"].as_str().unwrap());
    assert_eq!(std::fs::metadata(&bin).unwrap().permissions().mode() & 0o777, 0o555);
    assert_eq!(std::fs::metadata(dir.join("config.frozen.toml")).unwrap().permissions().mode() & 0o777, 0o444);
    assert!(std::fs::read_to_string(dir.join("check.out")).unwrap().contains("equity stops (WP-07"));
    assert_eq!(json(&dir.join("provenance.json"))["config"]["normalized_sha256"], c["config"]["normalized_sha256"]);
    for p in ["t1-p1", "t1-p2"] {
        assert_eq!(json(&dir.join(p).join("stop.json"))["reason"].as_str(), Some("error"));
        let meta = json(&dir.join(p).join("meta.json"));
        let argv: Vec<&str> = meta["run"]["argv"].as_array().unwrap().iter().map(|a| a.as_str().unwrap()).collect();
        assert_eq!(argv[0], bin.display().to_string(), "the frozen binary");
        assert!(argv.windows(2).any(|w| w == ["--campaign-dir", dir.to_str().unwrap()]) && !argv.contains(&"--budget-left"), "{argv:?}: a shadow campaign passes no budget");
        assert!(std::fs::read_to_string(dir.join(format!("{p}.out"))).unwrap().contains("no RPC provider configured"));
    }
    let kinds: Vec<String> = std::fs::read_to_string(dir.join("events.jsonl")).unwrap().lines().map(|l| serde_json::from_str::<Value>(l).unwrap()["kind"].as_str().unwrap().to_string()).collect();
    assert_eq!(kinds.iter().filter(|k| *k == "segment_end").count(), 2);
    for k in ["campaign_start", "segment_start", "campaign_end"] { assert!(kinds.contains(&k.to_string()), "{k}: {kinds:?}"); }
    assert_eq!(json(&dir.join("spend.json"))["schema"].as_str(), Some("arbx.spend/1.1"));
    // the campaign read back
    let out = Command::new(BIN).args(["campaign-equity", "--campaign-dir"]).arg(&dir).output().unwrap();
    let eq: Value = serde_json::from_slice(&out.stdout).unwrap();
    assert!(eq["basis"].as_str().unwrap().starts_with("net_spend"));
    assert_eq!((eq["segments_read"].as_array().map(|a| a.len()), eq["campaign"]["mode"].as_str()), (Some(2), Some("shadow")));
    // a campaign name that exists is refused
    let out = Command::new(BIN).env_clear().args(["campaign", "--name", "t1", "--hours", "1", "--force", "--config"]).arg(&conf).arg("--runs").arg(&runs).output().unwrap();
    assert!(String::from_utf8_lossy(&out.stderr).contains("exists"));
    let _ = std::fs::remove_dir_all(&d);
}

/// The brief: `arbx check` passes on the frz canary config
#[test]
fn the_frz_canary_config_passes_arbx_check() {
    let out = Command::new(BIN).env_clear().args(["check", "--config"]).arg(repo("deploy/arbx-canary-frz.toml")).output().unwrap();
    let text = String::from_utf8_lossy(&out.stdout);
    assert!(out.status.success(), "{text}{}", String::from_utf8_lossy(&out.stderr));
    assert!(text.contains("wallet FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"), "{text}");
    assert!(text.contains("enabled send paths: jito-bundle (bundle-only"));
    assert!(text.contains("canary: 0.2 SOL, 100000 attempts"));
    assert!(text.contains("the net spend passes 0.02 SOL within an hour"), "{text}");
    assert!(text.contains("test budget 5000000 lamports"), "{text}");
    assert!(text.contains("bankroll (WP-07): a trade at most 85%"));
    for f in ["raiden", "corvus", "getblock", "constantk-prism", "erpc"] { assert!(text.lines().any(|l| l.contains(&format!("feed {f}")) && l.ends_with("(disabled)")), "{f}: {text}"); }
}

/// Review WP-07 #2 (mutants M3, M10), #5, #8, through the real binary, before anything reaches the network or a key: a
/// canary run without a test budget is refused for the budget; `--budget-left` above the owner's hard cap is refused; a
/// canary campaign without a budget is refused for the budget; a canary run is refused when the owner's cumulative
/// budget (`<runs>/budget-state.json`) is spent, whatever it asks for
#[test]
fn a_sending_start_needs_the_budget() {
    let d = tmp();
    let conf = canary_copy(&d);
    let run = |args: &[&str]| { let o = Command::new(BIN).env_clear().args(args).arg("--config").arg(&conf).output().unwrap(); (o.status.success(), String::from_utf8_lossy(&o.stderr).into_owned()) };
    let (ok, err) = run(&["run", "--canary", "--minutes", "1"]);
    assert!(!ok && err.contains("a live or canary run needs a test budget"), "{err}");
    let (ok, err) = run(&["run", "--canary", "--minutes", "1", "--budget-left", "34000001"]);
    assert!(!ok && err.contains("over the owner's hard cap"), "{err}");
    let (ok, err) = run(&["run", "--canary", "--minutes", "1", "--budget-left", "1000000", "--equity-floor=-1"]);
    assert!(!ok && err.contains("--equity-floor must be >= 0"), "{err}");
    let runs = d.join("runs");
    let out = Command::new(BIN).env_clear().args(["campaign", "--name", "nb", "--hours", "1", "--mode", "canary", "--config"]).arg(&conf).arg("--runs").arg(&runs).output().unwrap();
    let err = String::from_utf8_lossy(&out.stderr);
    assert!(!out.status.success() && err.contains("a canary campaign needs a test budget"), "{err}");
    // the owner's budget is spent: refused, whatever the run asks for
    std::fs::create_dir_all(&runs).unwrap();
    std::fs::write(runs.join("budget-state.json"), serde_json::json!({ "schema": "arbx.budget/1.0", "hard_cap_lamports": 34_000_000, "updated_ns": 1,
        "entries": [{ "id": "ft004", "kind": "campaign", "dir": runs.join("ft004").display().to_string(), "mode": "canary", "started_ns": 1, "ended_ns": 2,
            "allotment": 34_000_000, "spent": 34_000_000, "final": true }] }).to_string()).unwrap();
    let (ok, err) = run(&["run", "--canary", "--minutes", "1", "--budget-left", "1000000"]);
    assert!(!ok && err.contains("test budget is spent"), "{err}");
    let out = Command::new(BIN).env_clear().args(["campaign", "--name", "nb2", "--hours", "1", "--mode", "canary", "--test-budget-lamports", "1000000", "--force", "--config"])
        .arg(&conf).arg("--runs").arg(&runs).output().unwrap();
    let err = String::from_utf8_lossy(&out.stderr);
    assert!(!out.status.success() && err.contains("test budget is spent"), "{err}");
    assert!(!runs.join("nb2").join("campaign.json").exists(), "nothing started");
    let _ = std::fs::remove_dir_all(&d);
}

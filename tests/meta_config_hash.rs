//! Review F2, through the real binary: meta.json `config.normalized_sha256` is the hash of the config file as loaded,
//! whatever the command line overrides (`--budget-left`, `--no-record`, `--shadow`), and equals what
//! `arbx provenance --offline` (the supervisor's campaign.json) says. Each run here is a boot that fails at once (no RPC
//! provider: the environment is empty), which still writes the partial meta.json with the `config` section, and
//! stop.json `error`, exit 30. It also checks that a missing `--env-file` is named in run.log (review deviation 6).
use serde_json::Value;
use std::path::{Path, PathBuf};
use std::process::Command;

const BIN: &str = env!("CARGO_BIN_EXE_arbx");

fn tmp() -> PathBuf {
    let t = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap().as_nanos();
    let d = std::env::temp_dir().join(format!("arbx-metahash-{}-{t}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn json(p: &Path) -> Value { serde_json::from_str(&std::fs::read_to_string(p).unwrap_or_else(|e| panic!("{}: {e}", p.display()))).unwrap() }

#[test]
fn meta_json_hashes_the_config_before_the_command_line() {
    let d = tmp();
    // a copy, so no .env beside the shipped config is ever loaded
    let conf = d.join("stage0.toml");
    std::fs::copy(Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-stage0.toml"), &conf).unwrap();
    let prov = Command::new(BIN).env_clear().args(["provenance", "--offline", "--config"]).arg(&conf).output().unwrap();
    assert!(prov.status.success(), "{}", String::from_utf8_lossy(&prov.stderr));
    let prov: Value = serde_json::from_slice(&prov.stdout).unwrap();
    let want = prov["config"]["normalized_sha256"].as_str().unwrap().to_string();
    let camp = d.join("camp");
    std::fs::create_dir_all(&camp).unwrap();
    for (i, extra) in [vec![], vec!["--budget-left", "1000000"], vec!["--budget-left", "99999999999"], vec!["--no-record"], vec!["--shadow"],
        vec!["--shadow", "--no-record", "--budget-left", "0"]].into_iter().enumerate() {
        let name = format!("seg{i}");
        let out = Command::new(BIN).env_clear().args(["run", "--minutes", "0.01", "--name", &name, "--config"]).arg(&conf).arg("--campaign-dir").arg(&camp)
            .arg("--env-file").arg(d.join("missing.env")).args(&extra).output().unwrap();
        let text = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
        assert_eq!(out.status.code(), Some(30), "{extra:?}: a boot without RPC fails: {text}");
        assert!(text.contains("no RPC provider configured"), "{text}");
        let seg = camp.join(&name);
        let meta = json(&seg.join("meta.json"));
        assert_eq!(meta["partial"], true);
        assert_eq!(meta["config"]["normalized_sha256"].as_str(), Some(want.as_str()), "{extra:?}");
        assert_eq!(meta["config"]["file_sha256"], prov["config"]["file_sha256"]);
        assert_eq!(meta["config"]["mode"], "shadow");
        let stop = json(&seg.join("stop.json"));
        assert_eq!((stop["reason"].as_str(), stop["exit_code"].as_i64()), (Some("error"), Some(30)));
        assert!(std::fs::read_to_string(seg.join("run.log")).unwrap().contains("WARNING: --env-file"), "a missing --env-file is named");
        assert_eq!(meta["run"]["env_file_loaded"], false);
        if extra.contains(&"--budget-left") { assert!(meta["overrides"]["budget_left_lamports"].is_u64(), "{}", meta["overrides"]); }
    }
    // --shadow --canary is refused before anything starts (review M7)
    let out = Command::new(BIN).env_clear().args(["run", "--shadow", "--canary", "--name", "x", "--config"]).arg(&conf).arg("--campaign-dir").arg(&camp).output().unwrap();
    assert_eq!(out.status.code(), Some(30));
    assert!(String::from_utf8_lossy(&out.stderr).contains("--shadow and --canary"));
    assert!(!camp.join("x").exists());
    let _ = std::fs::remove_dir_all(&d);
}

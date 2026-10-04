//! PLAN WP-01 acceptance "Supervisor dry run": `tools/test-run-w.sh` runs deploy/run-w.sh with ARBX_DRY=1 against a
//! fake arbx (operator stops are not crashes, exit 20 ends the campaign, the budget is never summed across status lines,
//! the config is never edited, the control files work). Run here so `cargo test` covers it.
use std::process::Command;

#[test]
fn supervisor_dry_run() {
    if Command::new("python3").arg("--version").output().is_err() {
        eprintln!("python3 not found: the supervisor needs it; skipped");
        return;
    }
    let root = env!("CARGO_MANIFEST_DIR");
    let out = Command::new("bash").arg(format!("{root}/tools/test-run-w.sh")).output().expect("bash");
    let text = format!("{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
    assert!(out.status.success(), "tools/test-run-w.sh failed:\n{text}");
    assert!(!text.contains("FAIL"), "{text}");
}

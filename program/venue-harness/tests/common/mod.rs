//! Shared by the arbx-sizing comparisons (tests/exactness.rs, tests/adversarial.rs, tests/route.rs): the sizing
//! bridge's build and run, and the refusal-vs-venue verdict (WP-16 review F3).
#![allow(dead_code)]
use base64::Engine as _;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};

pub const MANIFEST_DIR: &str = env!("CARGO_MANIFEST_DIR");

/// PLAN-ADDENDUM WP-21's venues (Raydium CLMM, Orca Whirlpool)
pub mod clmm;
/// arbx's own bundles on the real programs (tests/arbx_bundle.rs, tests/arbx_bundle_clmm.rs)
pub mod bundle;

/// VENUE_HARNESS_REQUIRE_SIZING=1: a missing or unbuildable sizing crate fails the test instead of skipping it
pub fn required() -> bool { std::env::var("VENUE_HARNESS_REQUIRE_SIZING").is_ok_and(|v| v == "1") }

/// The sizing crate: program/arbx-sizing, or VENUE_HARNESS_SIZING_DIR (e.g. a worktree or a stub)
pub fn sizing_dir() -> PathBuf {
    std::env::var("VENUE_HARNESS_SIZING_DIR").map(PathBuf::from).unwrap_or_else(|_| Path::new(MANIFEST_DIR).join("../arbx-sizing"))
}

/// Where bridge `name` builds (WP-16 review F9: never inside the repository when a target directory is given):
/// VENUE_HARNESS_BRIDGE_TARGET, else the outer build's CARGO_TARGET_DIR, else this crate's own `target/` (gitignored)
pub fn bridge_target(name: &str) -> PathBuf {
    let base = std::env::var_os("VENUE_HARNESS_BRIDGE_TARGET").or_else(|| std::env::var_os("CARGO_TARGET_DIR")).map(PathBuf::from)
        .unwrap_or_else(|| Path::new(MANIFEST_DIR).join("target"));
    // a relative CARGO_TARGET_DIR is relative to where cargo ran: the package root for `cargo test` here
    let base = if base.is_relative() { Path::new(MANIFEST_DIR).join(base) } else { base };
    base.join(name)
}

/// Build the bridge (sizing-bridge/src/main.rs, with a manifest generated for `sizing`) in [`bridge_target`]`(name)`.
/// Err: the build's error lines
pub fn build_bridge(sizing: &Path, name: &str) -> Result<PathBuf, String> {
    let root = Path::new(MANIFEST_DIR);
    let target = bridge_target(name);
    let src = target.join("crate");
    std::fs::create_dir_all(src.join("src")).map_err(|e| format!("{}: {e}", src.display()))?;
    let manifest = std::fs::read_to_string(root.join("sizing-bridge/Cargo.toml")).unwrap()
        .replace("path = \"../../arbx-sizing\"", &format!("path = {:?}", sizing.canonicalize().map_err(|e| format!("{}: {e}", sizing.display()))?));
    std::fs::write(src.join("Cargo.toml"), manifest).unwrap();
    let _ = std::fs::remove_file(src.join("Cargo.lock")); // re-resolve: the sizing crate may have changed
    std::fs::copy(root.join("sizing-bridge/src/main.rs"), src.join("src/main.rs")).unwrap();
    let mut cmd = Command::new(std::env::var("CARGO").unwrap_or_else(|_| "cargo".into()));
    cmd.args(["build", "--release", "--manifest-path"]).arg(src.join("Cargo.toml")).arg("--target-dir").arg(&target);
    // the outer `cargo test` exports CARGO_* variables describing THIS package: keep them away from the inner build
    for (k, _) in std::env::vars() {
        if k.starts_with("CARGO_") && !matches!(k.as_str(), "CARGO_HOME" | "CARGO_BUILD_JOBS" | "CARGO_NET_OFFLINE") { cmd.env_remove(&k); }
    }
    if std::env::var("CARGO_BUILD_JOBS").is_err() { cmd.env("CARGO_BUILD_JOBS", "4"); }
    let out = cmd.output().map_err(|e| format!("running cargo: {e}"))?;
    if !out.status.success() {
        let err = String::from_utf8_lossy(&out.stderr);
        let noise = ["Compiling", "Updating", "Downloaded", "Downloading", "Locking", "Blocking", "Adding", "warning"];
        let lines: Vec<&str> = err.lines().filter(|l| !l.trim().is_empty() && !noise.iter().any(|n| l.trim_start().starts_with(n))).take(30).collect();
        return Err(lines.join("\n"));
    }
    Ok(target.join("release").join("sizing-bridge"))
}

/// One bridge run: the request in, the response out (a crash is a panic in arbx-sizing: DESIGN §5.4 "no panics")
pub fn run_bridge(bridge: &Path, req: &Value) -> Value {
    let mut child = Command::new(bridge).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    child.stdin.take().unwrap().write_all(req.to_string().as_bytes()).unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success(), "sizing-bridge crashed (a panic in arbx-sizing is a bug: DESIGN §5.4 'no panics'):\n{}", String::from_utf8_lossy(&out.stderr));
    serde_json::from_slice(&out.stdout).unwrap()
}

/// Quote `legs` (each with its own "clock") in one bridge run per distinct clock; the responses by leg id
pub fn quote_legs(bridge: &Path, legs: &[Value]) -> Vec<Value> {
    let mut resp: Vec<Value> = vec![Value::Null; legs.len()];
    let mut by_clock: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for l in legs { by_clock.entry(l["clock"].to_string()).or_default().push(l.clone()); }
    for (clock, ls) in by_clock {
        let v = run_bridge(bridge, &json!({"clock": serde_json::from_str::<Value>(&clock).unwrap(), "legs": ls}));
        for r in v["legs"].as_array().unwrap() { resp[r["id"].as_u64().unwrap() as usize] = r.clone(); }
    }
    resp
}

fn b64d(s: &str) -> Vec<u8> { base64::engine::general_purpose::STANDARD.decode(s).unwrap() }
fn b64e(b: &[u8]) -> String { base64::engine::general_purpose::STANDARD.encode(b) }

const TOKEN_2022: &str = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb";

/// A Token-2022 mint's transfer fee zeroed: TransferFeeConfig (extension 1) older and newer `transfer_fee_basis_points`
/// (value offsets 88 and 106: two authorities, the withheld amount, then {epoch, maximum_fee, bps} twice). False when
/// the mint has no such extension
fn zero_transfer_fee(d: &mut [u8]) -> bool {
    let mut o = 166;
    let mut done = false;
    while o + 4 <= d.len() {
        let (t, l) = (u16::from_le_bytes([d[o], d[o + 1]]), u16::from_le_bytes([d[o + 2], d[o + 3]]) as usize);
        if t == 0 { break; }
        if t == 1 && o + 4 + 108 <= d.len() {
            for at in [88, 106] { d[o + 4 + at] = 0; d[o + 4 + at + 1] = 0; }
            done = true;
        }
        o += 4 + l;
    }
    done
}

/// The crate-side lift of a refusal (WP-16 review F3): the leg's accounts with the refused state taken out on the
/// crate's side only (the venue keeps swapping the real accounts), for the refusals whose state the harness can take
/// out: a Token-2022 transfer fee (`abort:TransferFee`: every fee-charging mint of the leg set to 0 bps). None: no lift
/// for this refusal (a venue that swaps then makes it a FALSE REFUSAL)
pub fn lift(parse: &str, accounts: &[Value]) -> Option<Vec<Value>> {
    if parse != "abort:TransferFee" { return None; }
    let mut out = accounts.to_vec();
    let mut any = false;
    for a in out.iter_mut() {
        if a["owner"] != TOKEN_2022 { continue; }
        let mut d = b64d(a["data"].as_str().unwrap());
        if d.len() > 166 && d[165] == 1 && zero_transfer_fee(&mut d) { a["data"] = json!(b64e(&d)); any = true; }
    }
    any.then_some(out)
}

/// What the venue did at one refused size
#[derive(Clone, Debug)]
pub struct VenueAt { pub ok: bool, pub out: u64, pub spent: u64 }
impl VenueAt { pub fn swapped(&self) -> bool { self.ok && self.out > 0 } }

/// The verdict on a leg's refused sizes where the venue swapped (WP-16 review F3): "necessary refusal" when the
/// crate's maths without the refused state are off at one of them at least (the refusal keeps a misprice out), "FALSE
/// REFUSAL" when they equal the venue at every one (the refusal costs coverage for nothing) or when the refusal has no
/// lift (unverified). `lifted` holds the lifted quotes at the same sizes ({ok, out, spent}), None without a lift
pub fn refusal_verdict(venue: &[VenueAt], lifted: Option<&[Value]>) -> (&'static str, String) {
    let Some(lq) = lifted else { return ("FALSE REFUSAL", "no lift for this refusal: the venue swaps a state the crate refuses".into()) };
    let off: Vec<String> = venue.iter().zip(lq).filter(|(v, q)| !(q["ok"] == true && q["out"].as_u64() == Some(v.out) && q["spent"].as_u64() == Some(v.spent)))
        .take(2).map(|(v, q)| format!("lifted {} {} vs venue {} {}", q["out"], q["spent"], v.out, v.spent)).collect();
    if off.is_empty() { ("FALSE REFUSAL", "the crate prices every venue-swapped size exactly without the refusal".into()) }
    else { ("necessary refusal", format!("without the refusal the crate is off: {}", off.join("; "))) }
}

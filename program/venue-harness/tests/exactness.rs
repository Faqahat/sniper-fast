//! Exactness of arbx-sizing's venue quotes against the REAL venue programs (DESIGN.md §6.3).
//!
//! If `program/arbx-sizing` exists and the bridge (`sizing-bridge/`, a separate crate with a path dependency on it)
//! builds, every fixture pool (plus byte-mutated variants: CPMM creator fee on, AMM v4 pnl owed, DLMM fee side and
//! volatility reset, PumpSwap virtual reserve / creator fee cleared, DAMM v2 fee side) is quoted in both directions
//! at ~45 sizes (PumpSwap buys: +1,000 consecutive sizes) by the crate (`AnyLeg::parse` + `quote`, over the same leg
//! account list the harness swaps with) and by the dumped program in LiteSVM, and the two must agree:
//!   * `Ok(q)`              <=> the swap succeeds, with output delta == q.out and input debit == q.spent;
//!   * `TooLarge`/`ZeroOut` <=> the swap fails or delivers 0 (a `TooLarge` where the venue still swaps is a
//!     MISMATCH: TooLarge claims a venue capacity);
//!   * `Budget` (a DLMM swap past the leg's walk budget, 255 bins with liquidity here: "not evaluated") is checked
//!     twice: the same quote without a budget must equal the venue as above, and the swap must really need more
//!     bins with liquidity than the budget;
//!   * `Abort(..)` (parse or quote) is skipped and counted per venue (the skip rate is a reported metric);
//!   * a `DescError` on a leg the harness built like the engine is a failure.
//! Otherwise the test SKIPS with a message (it passes), unless VENUE_HARNESS_REQUIRE_SIZING=1.
//! Results: results/exactness.json.
//!
//!   cargo test --release --test exactness -- --nocapture
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use venue_harness::venues::pump_canonical_bump;
use venue_harness::*;

const MANIFEST_DIR: &str = env!("CARGO_MANIFEST_DIR");

fn skip(msg: &str) {
    if std::env::var("VENUE_HARNESS_REQUIRE_SIZING").is_ok_and(|v| v == "1") { panic!("{msg}"); }
    println!("SKIP exactness: {msg}");
}

/// DESIGN §1.2 / §4.3: the sizing kind and dir bit of a venue swap
fn kind_of(venue: Venue, dir: Dir) -> (u8, bool) {
    match venue {
        Venue::PumpSwap => if dir.zfo() { (2, true) } else { (1, false) },
        Venue::RayCpmm => (3, dir.zfo()),
        Venue::RayAmmV4 => (4, dir.zfo()),
        Venue::Dlmm => (5, dir.zfo()),
        Venue::DammV2 => (6, dir.zfo()),
    }
}

/// The sizing crate: program/arbx-sizing, or VENUE_HARNESS_SIZING_DIR (e.g. a worktree or a stub).
fn sizing_dir() -> PathBuf {
    std::env::var("VENUE_HARNESS_SIZING_DIR").map(PathBuf::from).unwrap_or_else(|_| Path::new(MANIFEST_DIR).join("../arbx-sizing"))
}

/// Build the bridge (sizing-bridge/src/main.rs, with a manifest generated for `sizing`) in its own target dir.
/// Err: the build's error lines.
fn build_bridge(sizing: &Path) -> Result<PathBuf, String> {
    let root = Path::new(MANIFEST_DIR);
    let target = root.join("target").join("sizing-bridge");
    let src = target.join("crate");
    std::fs::create_dir_all(src.join("src")).unwrap();
    let manifest = std::fs::read_to_string(root.join("sizing-bridge/Cargo.toml")).unwrap()
        .replace("path = \"../../arbx-sizing\"", &format!("path = {:?}", sizing.canonicalize().unwrap()));
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

#[derive(Default, serde::Serialize)]
struct Tally { exact: usize, too_large_agree: usize, budget: usize, cu_limit: usize, aborted: usize, mismatches: usize, abort_reasons: BTreeMap<String, usize> }

/// One harness state to compare on: a pool's snapshot, or the snapshot with a byte mutation (DESIGN §6.3 "state
/// mutation": the program is the oracle; a mutation it rejects must be rejected by the model too).
struct Case { label: String, h: Harness }

fn cases(fx: &Fixtures) -> Vec<Case> {
    let mut out = vec![];
    for p in fx.pools.values() {
        let pool = p.pool_key();
        let h0 = Harness::new(fx, &pool).unwrap();
        let fee_mint = venue_harness::venues::pool_has_transfer_fee(&h0.view, &h0.tokens);
        let mut variants = vec![];
        let mut m = |label: &str, patches: Vec<Patch>| match Harness::with_patches(fx, &pool, &patches) {
            Ok(h) => variants.push(Case { label: label.into(), h }),
            Err(e) => panic!("{} {label}: {e}", p.pool),
        };
        let u64b = |v: u64| v.to_le_bytes().to_vec();
        match p.venue {
            // Raydium CPMM: the creator fee on (input side by creator_fee_on and direction); DESIGN §2.7 item 3
            Venue::RayCpmm if !fee_mint => for on in 0u8..=2 {
                m(&format!("enable_creator_fee=1 creator_fee_on={on}"), vec![Patch::new(pool, 389, &[on, 1])]);
            },
            // AMM v4: pnl owed to the protocol is taken out of the reserves
            Venue::RayAmmV4 => {
                let coin = venue_harness::venues::token_amount(&h0.view[&h0.tokens.vault0].data).unwrap();
                let pc = venue_harness::venues::token_amount(&h0.view[&h0.tokens.vault1].data).unwrap();
                m("need_take_pnl 1%", vec![Patch::new(pool, 192, &u64b(coin / 100)), Patch::new(pool, 200, &u64b(pc / 100))]);
            }
            // DLMM: the fee side flips (collect_fee_mode 0 <-> 1) and the volatility state is reset
            Venue::Dlmm => {
                let cfm = h0.view[&pool].data[36];
                m(&format!("collect_fee_mode={}", 1 - cfm.min(1)), vec![Patch::new(pool, 36, &[1 - cfm.min(1)])]);
                m("va=0 vref=0", vec![Patch::new(pool, 40, &[0u8; 8])]);
            }
            // PumpSwap: no virtual quote reserve; creator fee bps cleared
            Venue::PumpSwap => {
                m("virtual_quote_reserves=0", vec![Patch::new(pool, 245, &[0u8; 16])]);
                m("creator_fee_bps=0", vec![Patch::new(pool, 261, &[0u8; 8])]);
            }
            // DAMM v2: the fee side flips (collect_fee_mode 0 <-> 1)
            Venue::DammV2 if !fee_mint => {
                let cfm = h0.view[&pool].data[484];
                if cfm <= 1 { m(&format!("collect_fee_mode={}", 1 - cfm), vec![Patch::new(pool, 484, &[1 - cfm])]); }
            }
            _ => {}
        }
        out.push(Case { label: "snapshot".into(), h: h0 });
        out.extend(variants);
    }
    out
}

#[test]
fn sizing_quotes_equal_the_real_programs() {
    let sizing = sizing_dir();
    if !sizing.join("Cargo.toml").exists() {
        return skip(&format!("{} has no Cargo.toml: arbx-sizing is not written yet", sizing.display()));
    }
    let bridge = match build_bridge(&sizing) {
        Ok(b) => b,
        Err(e) => return skip(&format!("arbx-sizing exists but sizing-bridge does not build against it (crate mid-edit, or its API \
            differs from DESIGN.md §5.3: align sizing-bridge/src/main.rs `adapter`):\n{e}")),
    };
    let fx = Fixtures::load().unwrap();
    // the engine passes at most 5 DLMM bin arrays (the descriptor's 3-bit count), so quote and swap with that list
    let opts = BuildOpts { dlmm_max_arrays: 5, ..Default::default() };
    let cases = cases(&fx);
    let mut legs = vec![];
    let mut meta = vec![];
    for (ci, c) in cases.iter().enumerate() {
        let (h, p) = (&c.h, &c.h.fixture);
        for dir in Dir::BOTH {
            let sw = h.build(dir, 1, &opts).unwrap();
            let (kind, t0_in) = kind_of(p.venue, dir);
            let mut amounts: Vec<u64> = size_ladder(h.input_reserve(dir), 40).into_iter().chain([1, 2, 10, 100, 1_000]).collect();
            // PumpSwap buy_exact_quote_in: a dense run of consecutive sizes covers every fee-rounding residue (§7.1)
            if kind == 1 && c.label == "snapshot" { amounts.extend(10_000_000..10_001_000); }
            amounts.sort();
            amounts.dedup();
            // the leg's own accounts as the program sees them before the swap (executables without their ELF)
            let accounts: Vec<Value> = sw.ix.accounts.iter().map(|m| {
                let a = h.svm().get_account(&m.pubkey).unwrap_or_default();
                let data = if a.executable { vec![] } else { a.data };
                json!({"key": m.pubkey.to_string(), "owner": a.owner.to_string(), "data": base64_encode(&data)})
            }).collect();
            let pump_bump = if p.venue == Venue::PumpSwap { pump_canonical_bump(&h.view[&h.pool].data) } else { 0 };
            legs.push(json!({"id": legs.len(), "kind": kind, "base_or_token0_in": t0_in, "n_bin_arrays": sw.dlmm_arrays.len(),
                "pump_bump": pump_bump, "program": p.venue.program().to_string(), "input_mint": sw.mint_in.to_string(),
                "accounts": accounts, "amounts": amounts, "clock": p.clock}));
            meta.push((ci, dir));
        }
    }
    // one bridge run per distinct clock (each pool snapshot carries its own)
    let mut resp: Vec<Value> = vec![Value::Null; legs.len()];
    let mut by_clock: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for l in &legs { by_clock.entry(l["clock"].to_string()).or_default().push(l.clone()); }
    for (clock, ls) in by_clock {
        let req = json!({"clock": serde_json::from_str::<Value>(&clock).unwrap(), "legs": ls});
        let mut child = Command::new(&bridge).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
        child.stdin.take().unwrap().write_all(req.to_string().as_bytes()).unwrap();
        let out = child.wait_with_output().unwrap();
        assert!(out.status.success(), "sizing-bridge crashed (a panic in arbx-sizing is a bug: DESIGN §5.4 'no panics'):\n{}",
            String::from_utf8_lossy(&out.stderr));
        let v: Value = serde_json::from_slice(&out.stdout).unwrap();
        for r in v["legs"].as_array().unwrap() { resp[r["id"].as_u64().unwrap() as usize] = r.clone(); }
    }
    // compare with the real programs
    let mut tally: BTreeMap<String, Tally> = BTreeMap::new();
    let mut problems = vec![];
    let mut rows = vec![];
    for (i, r) in resp.iter().enumerate() {
        let (ci, dir) = meta[i];
        let c = &cases[ci];
        let (h, p) = (&c.h, &c.h.fixture);
        let key = if c.label == "snapshot" { p.venue.name().to_string() } else { format!("{} [{}]", p.venue.name(), c.label) };
        let t = tally.entry(key).or_default();
        let parse = r["parse"].as_str().unwrap_or("missing").to_string();
        if parse.starts_with("desc:") { problems.push(format!("{} {} {} [{}]: DescError on an engine-built leg: {parse}", p.venue.name(), p.pool, dir.short(), c.label)); }
        let max_bins = r["max_bins"].as_u64().unwrap_or(255);
        for q0 in r["quotes"].as_array().unwrap() {
            let x = q0["amount"].as_u64().unwrap();
            // a Budget refusal: compare the same quote without a budget, and check the budget really binds
            let budget = q0["err"].as_str() == Some("Budget");
            let q = if budget { &q0["unbounded"] } else { q0 };
            let err = q["err"].as_str().unwrap_or("");
            if !q["ok"].as_bool().unwrap() && (parse != "ok" || err.starts_with("Abort")) {
                t.aborted += 1;
                *t.abort_reasons.entry(if parse != "ok" { parse.clone() } else { err.to_string() }).or_default() += 1;
                continue;
            }
            let s = h.swap_opts(dir, x, &opts);
            let mut verdict = if q["ok"].as_bool().unwrap() {
                let (o, sp) = (q["out"].as_u64().unwrap(), q["spent"].as_u64().unwrap());
                if s.ok && s.amount_out == o && s.spent == sp { "exact".to_string() } else {
                    format!("MISMATCH quote out {o} spent {sp} vs program {} out {} spent {} {}", if s.ok { "ok" } else { "FAILED" }, s.amount_out, s.spent,
                        if s.ok { String::new() } else { s.venue_error() })
                }
            } else if s.failed_or_zero() { format!("both refuse ({err})") } else {
                format!("MISMATCH quote {err} vs program out {} (cu {:?})", s.amount_out, s.cu_venue)
            };
            // the venue ran out of the transaction's 1.4M CU (a long DLMM walk): not a maths verdict. The engine's
            // max_bins keeps sized swaps far below it (DESIGN.md §4.7); the bins it took are recorded
            if !s.ok && (s.logs.iter().any(|l| l.contains("exceeded CUs meter") || l.contains("Computational budget exceeded"))
                || s.err.as_deref().is_some_and(|e| e.contains("ComputationalBudgetExceeded"))) {
                verdict = format!("venue CU limit (quote {}; {} bins)", if q["ok"].as_bool().unwrap() { "ok" } else { err }, q0["bins"]);
            }
            if budget && !verdict.starts_with("MISMATCH") {
                let need = q0["bins"].as_u64();
                verdict = if need.map_or(false, |b| b > max_bins) || !q["ok"].as_bool().unwrap() { format!("budget ({verdict}; needs {need:?} > {max_bins} bins)") }
                    else { format!("MISMATCH Budget refusal although the swap needs {need:?} <= {max_bins} bins") };
            }
            if verdict.starts_with("MISMATCH") { t.mismatches += 1; } else if verdict.starts_with("budget") { t.budget += 1; }
                else if verdict.starts_with("venue CU limit") { t.cu_limit += 1; } else if verdict == "exact" { t.exact += 1; } else { t.too_large_agree += 1; }
            if verdict.starts_with("MISMATCH") && problems.len() < 40 { problems.push(format!("{} {} {} [{}] x={x}: {verdict}", p.venue.name(), p.pool, dir.short(), c.label)); }
            rows.push(json!({"venue": p.venue.name(), "pool": p.pool, "case": c.label, "dir": dir.short(), "amount_in": x, "quote": q0, "program_ok": s.ok,
                "program_out": s.amount_out, "program_spent": s.spent, "cu": s.cu_venue, "verdict": verdict}));
        }
    }
    println!("{:<44} {:>6} {:>11} {:>7} {:>7} {:>8} {:>9}  abort reasons", "venue [mutation]", "exact", "both-refuse", "budget", "cu-lim", "aborted", "MISMATCH");
    for (v, t) in &tally {
        println!("{v:<44} {:>6} {:>11} {:>7} {:>7} {:>8} {:>9}  {:?}", t.exact, t.too_large_agree, t.budget, t.cu_limit, t.aborted, t.mismatches, t.abort_reasons);
    }
    let sum = |f: fn(&Tally) -> usize| tally.values().map(f).sum::<usize>();
    println!("{:<44} {:>6} {:>11} {:>7} {:>7} {:>8} {:>9}", "TOTAL", sum(|t| t.exact), sum(|t| t.too_large_agree), sum(|t| t.budget), sum(|t| t.cu_limit), sum(|t| t.aborted), sum(|t| t.mismatches));
    for r in rows.iter().filter(|r| { let v = r["verdict"].as_str().unwrap(); v.starts_with("budget") || v.starts_with("venue CU") }).take(8) {
        println!("  {} {} {} [{}] x={} {}", r["venue"], r["pool"], r["dir"], r["case"], r["amount_in"], r["verdict"]);
    }
    // the fewest bins at which the venue ran out of CU, and the most it swapped through
    let bins_of = |r: &Value| r["quote"]["bins"].as_u64();
    let cu_min = rows.iter().filter(|r| r["verdict"].as_str().unwrap().starts_with("venue CU")).filter_map(bins_of).min();
    let ok_max = rows.iter().filter(|r| r["program_ok"] == true).filter_map(bins_of).max();
    println!("DLMM bins read (empty bins inside visited arrays included): venue out of CU from {cu_min:?}; largest successful swap {ok_max:?}");
    let out = Path::new(MANIFEST_DIR).join("results");
    std::fs::create_dir_all(&out).unwrap();
    std::fs::write(out.join("exactness.json"), serde_json::to_string_pretty(&json!({"tally": tally, "rows": rows})).unwrap()).unwrap();
    assert!(problems.is_empty(), "{} problems:\n{}", problems.len(), problems.join("\n"));
}

fn base64_encode(b: &[u8]) -> String { use base64::Engine as _; base64::engine::general_purpose::STANDARD.encode(b) }

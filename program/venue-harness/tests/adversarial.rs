//! Adversarial exactness probes for arbx-sizing (program/arbx-sizing/REVIEW.md). Same oracle and verdicts as
//! `tests/exactness.rs` (the dumped mainnet programs in LiteSVM against `AnyLeg::parse` + `quote` through the
//! sizing bridge), but on the states and sizes DESIGN.md §6.3 asks for and the snapshot ladder misses:
//!
//! * boundary sizes the crate itself computes (bridge probe mode): every DLMM layer edge and bin drain threshold
//!   along the crate's walk, the PumpSwap sell / DAMM v2 range capacities, and fee-ceil residues, each ±1, ±2;
//! * Clock variations: DLMM and DAMM v2 Δt ∈ {0, filter−1, filter, decay−1, decay, 10·decay} after the last
//!   update, DAMM v2 scheduler period edges;
//! * state mutations: DLMM limit orders (open and processed layers, both ask sides, function_type 0/1/2, reward
//!   mints), volatility extremes, a bitmap gap and an empty active array (bitmap-order and engine-order array
//!   lists); PumpSwap negative / large virtual reserve, coin_creator 0, creator_fee_bps above the configurable
//!   maximum, market cap across fee tiers; CPMM owed fees, fee rates; AMM v4 fee fractions; DAMM v2 narrow price
//!   range, rate limiter, fee cap.
//!
//! A state the program refuses must be refused (or aborted) by the crate too; an Abort is skipped and counted.
//! Fails on any MISMATCH. Results: results/adversarial.json.
//!
//!   VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release --test adversarial -- --nocapture
use serde_json::{json, Value};
use solana_address::Address;
use std::collections::BTreeMap;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use venue_harness::fixture::ClockSnap;
use venue_harness::keys;
use venue_harness::venues::{i32_at, pump_canonical_bump, u64_at};
use venue_harness::*;

const MANIFEST_DIR: &str = env!("CARGO_MANIFEST_DIR");

fn skip(msg: &str) {
    if std::env::var("VENUE_HARNESS_REQUIRE_SIZING").is_ok_and(|v| v == "1") { panic!("{msg}"); }
    println!("SKIP adversarial: {msg}");
}

fn kind_of(venue: Venue, dir: Dir) -> (u8, bool) {
    match venue {
        Venue::PumpSwap => if dir.zfo() { (2, true) } else { (1, false) },
        Venue::RayCpmm => (3, dir.zfo()),
        Venue::RayAmmV4 => (4, dir.zfo()),
        Venue::Dlmm => (5, dir.zfo()),
        Venue::DammV2 => (6, dir.zfo()),
    }
}

fn sizing_dir() -> PathBuf {
    std::env::var("VENUE_HARNESS_SIZING_DIR").map(PathBuf::from).unwrap_or_else(|_| Path::new(MANIFEST_DIR).join("../arbx-sizing"))
}

/// The bridge (sizing-bridge/src/main.rs) built in its own target dir (not the one tests/exactness.rs uses).
fn build_bridge(sizing: &Path) -> Result<PathBuf, String> {
    let root = Path::new(MANIFEST_DIR);
    let target = root.join("target").join("sizing-bridge-adv");
    let src = target.join("crate");
    std::fs::create_dir_all(src.join("src")).unwrap();
    let manifest = std::fs::read_to_string(root.join("sizing-bridge/Cargo.toml")).unwrap()
        .replace("path = \"../../arbx-sizing\"", &format!("path = {:?}", sizing.canonicalize().unwrap()));
    std::fs::write(src.join("Cargo.toml"), manifest).unwrap();
    let _ = std::fs::remove_file(src.join("Cargo.lock"));
    std::fs::copy(root.join("sizing-bridge/src/main.rs"), src.join("src/main.rs")).unwrap();
    let mut cmd = Command::new(std::env::var("CARGO").unwrap_or_else(|_| "cargo".into()));
    cmd.args(["build", "--release", "--manifest-path"]).arg(src.join("Cargo.toml")).arg("--target-dir").arg(&target);
    for (k, _) in std::env::vars() {
        if k.starts_with("CARGO_") && !matches!(k.as_str(), "CARGO_HOME" | "CARGO_BUILD_JOBS" | "CARGO_NET_OFFLINE") { cmd.env_remove(&k); }
    }
    if std::env::var("CARGO_BUILD_JOBS").is_err() { cmd.env("CARGO_BUILD_JOBS", "4"); }
    let out = cmd.output().map_err(|e| format!("running cargo: {e}"))?;
    if !out.status.success() { return Err(String::from_utf8_lossy(&out.stderr).lines().rev().take(30).collect::<Vec<_>>().join("\n")); }
    Ok(target.join("release").join("sizing-bridge"))
}

/// One state to compare on: a (patched) snapshot, the Clock both sides see, the array list, the directions.
struct Probe { label: String, h: Harness, clock: ClockSnap, opts: BuildOpts, probe: bool, dirs: Vec<Dir> }

fn u16_at(d: &[u8], o: usize) -> u16 { u16::from_le_bytes(d[o..o + 2].try_into().unwrap()) }
fn i64_at(d: &[u8], o: usize) -> i64 { i64::from_le_bytes(d[o..o + 8].try_into().unwrap()) }
fn u128_at(d: &[u8], o: usize) -> u128 { u128::from_le_bytes(d[o..o + 16].try_into().unwrap()) }

const BIN0: usize = 56;
const BIN_SIZE: usize = 144;

/// the bin's offset in its array account
fn bin_off(id: i32) -> (i64, usize) { let a = keys::dlmm_array_index(id); (a, BIN0 + BIN_SIZE * (id as i64 - a * 70) as usize) }

/// the arrays the ENGINE's builder (src/build.rs::dlmm_leg) passes: the active array first, then the contiguous
/// arrays that exist, up to 5 (bitmap not consulted)
fn engine_arrays(h: &Harness, zfo: bool) -> Vec<i64> {
    let d = &h.view[&h.pool].data;
    let c = keys::dlmm_array_index(i32_at(d, 76).unwrap());
    let mut v = vec![c];
    let mut i = c;
    while v.len() < 5 {
        i += if zfo { -1 } else { 1 };
        if !h.view.contains_key(&keys::dlmm_bin_array(&h.pool, i)) { break; }
        v.push(i);
    }
    v
}

/// patches that empty every bin of array `idx` and clear its bitmap bit
fn empty_array(h: &Harness, idx: i64) -> Vec<Patch> {
    let pool = h.pool;
    let key = keys::dlmm_bin_array(&pool, idx);
    let mut p = vec![];
    for k in 0..70 {
        let o = BIN0 + BIN_SIZE * k;
        p.push(Patch::new(key, o, &[0u8; 16]));
        p.push(Patch::new(key, o + 112, &[0u8; 24]));
    }
    let d = &h.view[&pool].data;
    let b = (idx + 512) as usize;
    let wo = 584 + 8 * (b / 64);
    let w = u64_at(d, wo).unwrap() & !(1u64 << (b % 64));
    p.push(Patch::new(pool, wo, &w.to_le_bytes()));
    p
}

/// limit orders on bins around the active one: bids (ask 0, Y) below and on the active bin, asks (ask 1, X) above
fn limit_orders(h: &Harness, open_div: u64, processed_div: u64) -> Vec<Patch> {
    let pool = h.pool;
    let d = &h.view[&pool].data;
    let active = i32_at(d, 76).unwrap();
    let mut p = vec![];
    for (id, ask) in [(active - 2, 0u8), (active - 1, 0), (active, 0), (active + 1, 1), (active + 2, 1)] {
        let (a, o) = bin_off(id);
        let key = keys::dlmm_bin_array(&pool, a);
        let Some(acc) = h.view.get(&key) else { continue };
        let (ax, ay) = (u64_at(&acc.data, o).unwrap(), u64_at(&acc.data, o + 8).unwrap());
        let side = if ask == 0 { ay } else { ax };
        let base = side.max(1_000_000);
        p.push(Patch::new(key, o + 112, &(base / open_div + 1_001).to_le_bytes()));
        p.push(Patch::new(key, o + 128, &(base / processed_div + 777).to_le_bytes()));
        p.push(Patch::new(key, o + 140, &[ask]));
    }
    p
}

fn probes(fx: &Fixtures) -> Vec<Probe> {
    let mut out = vec![];
    for p in fx.pools.values() {
        let pool = p.pool_key();
        let h0 = Harness::new(fx, &pool).unwrap();
        let fee_mint = venues::pool_has_transfer_fee(&h0.view, &h0.tokens);
        let d = h0.view[&pool].data.clone();
        let snap = p.clock;
        let opts5 = BuildOpts { dlmm_max_arrays: 5, ..Default::default() };
        let mut add = |label: String, patches: Vec<Patch>, clock: ClockSnap, opts: BuildOpts, probe: bool, dirs: Vec<Dir>| {
            match Harness::with_patches(fx, &pool, &patches) {
                Ok(h) => out.push(Probe { label, h, clock, opts, probe, dirs }),
                Err(e) => println!("{} {label}: cannot build ({e})", p.pool),
            }
        };
        let both = Dir::BOTH.to_vec();
        if fee_mint { continue; } // Abort::TransferFee: nothing to compare
        // every pool: the crate's own boundary sizes at the snapshot
        add("probe".into(), vec![], snap, opts5.clone(), true, both.clone());
        let at = |ts: i64| ClockSnap { unix_timestamp: ts, ..snap };
        match p.venue {
            Venue::Dlmm => {
                let (filter, decay, last) = (u16_at(&d, 10) as i64, u16_at(&d, 12) as i64, i64_at(&d, 56));
                for dt in [0, filter - 1, filter, decay - 1, decay, 10 * decay] {
                    add(format!("clock last+{dt}"), vec![], at(last + dt), opts5.clone(), false, both.clone());
                }
                let active = i32_at(&d, 76).unwrap();
                let max_va = u32::from_le_bytes(d[20..24].try_into().unwrap());
                let ft = d[35];
                let lo = limit_orders(&h0, 3, 5);
                add(format!("limit orders (function_type {ft})"), lo.clone(), snap, opts5.clone(), true, both.clone());
                let lo_small = limit_orders(&h0, 50, 70);
                add(format!("small limit orders (function_type {ft})"), lo_small.clone(), snap, opts5.clone(), true, both.clone());
                let mut lo2 = lo.clone();
                lo2.push(Patch::new(pool, 35, &[2]));
                add("limit orders, function_type 2".into(), lo2, snap, opts5.clone(), true, both.clone());
                let mut lo1 = lo.clone();
                lo1.push(Patch::new(pool, 35, &[1]));
                add("limit orders, function_type 1".into(), lo1, snap, opts5.clone(), true, both.clone());
                let mut lo0 = lo.clone();
                lo0.push(Patch::new(pool, 35, &[0]));
                add("limit orders, function_type 0, no reward mints".into(), lo0.clone(), snap, opts5.clone(), true, both.clone());
                lo0.push(Patch::new(pool, 264, &[7u8; 32]));
                add("limit orders, function_type 0, reward mint set".into(), lo0, snap, opts5.clone(), true, both.clone());
                // volatility extremes; last_update = now so the references are kept
                let now = snap.unix_timestamp.to_le_bytes();
                let mut v = vec![Patch::new(pool, 40, &max_va.to_le_bytes()), Patch::new(pool, 44, &max_va.to_le_bytes()),
                                 Patch::new(pool, 48, &(active + 500).to_le_bytes()), Patch::new(pool, 56, &now)];
                add("va=vref=max_va idx_ref=active+500".into(), v.clone(), snap, opts5.clone(), true, both.clone());
                v = vec![Patch::new(pool, 40, &0u32.to_le_bytes()), Patch::new(pool, 44, &0u32.to_le_bytes()),
                         Patch::new(pool, 48, &(active - 25).to_le_bytes()), Patch::new(pool, 56, &now)];
                add("vref=0 idx_ref=active-25 (fee falls along X->Y)".into(), v.clone(), snap, opts5.clone(), true, both.clone());
                v = vec![Patch::new(pool, 40, &0u32.to_le_bytes()), Patch::new(pool, 44, &0u32.to_le_bytes()),
                         Patch::new(pool, 48, &(active + 25).to_le_bytes()), Patch::new(pool, 56, &now)];
                add("vref=0 idx_ref=active+25 (fee falls along Y->X)".into(), v, snap, opts5.clone(), true, both.clone());
                // the pair's own bin-id bounds (StaticParameters min_bin_id @24, max_bin_id @28) one bin from active
                add("min_bin_id = active-1, max_bin_id = active+1".into(),
                    vec![Patch::new(pool, 24, &(active - 1).to_le_bytes()), Patch::new(pool, 28, &(active + 1).to_le_bytes())], snap, opts5.clone(), true, both.clone());
                // a bitmap gap after the active array, and an empty active array
                for (zfo, dir) in [(true, Dir::ZeroForOne), (false, Dir::OneForZero)] {
                    let c = keys::dlmm_array_index(active);
                    let next = c + if zfo { -1 } else { 1 };
                    if h0.view.contains_key(&keys::dlmm_bin_array(&pool, next)) && h0.view.contains_key(&keys::dlmm_bin_array(&pool, next + if zfo { -1 } else { 1 })) {
                        let gap = empty_array(&h0, next);
                        add(format!("bitmap gap at array {next} (bitmap-order arrays)"), gap.clone(), snap, opts5.clone(), true, vec![dir]);
                        if let Ok(hg) = Harness::with_patches(fx, &pool, &gap) {
                            let list = engine_arrays(&hg, zfo);
                            add(format!("bitmap gap at array {next} (engine arrays {list:?})"), gap, snap,
                                BuildOpts { dlmm_arrays: Some(list), ..opts5.clone() }, true, vec![dir]);
                        }
                    }
                    let empty = empty_array(&h0, c);
                    add(format!("empty active array {c} (bitmap-order arrays)"), empty.clone(), snap, opts5.clone(), true, vec![dir]);
                    if let Ok(he) = Harness::with_patches(fx, &pool, &empty) {
                        let list = engine_arrays(&he, zfo);
                        add(format!("empty active array {c} (engine arrays {list:?})"), empty, snap,
                            BuildOpts { dlmm_arrays: Some(list), ..opts5.clone() }, true, vec![dir]);
                    }
                }
            }
            Venue::PumpSwap => {
                let q = venues::token_amount(&h0.view[&h0.tokens.vault1].data).unwrap() as i128;
                add("virtual quote = -Q/2".into(), vec![Patch::new(pool, 245, &(-q / 2).to_le_bytes())], snap, opts5.clone(), true, both.clone());
                add("virtual quote = 50 Q".into(), vec![Patch::new(pool, 245, &(q * 50).to_le_bytes())], snap, opts5.clone(), true, both.clone());
                add("coin_creator = 0".into(), vec![Patch::new(pool, 211, &[0u8; 32])], snap, opts5.clone(), true, both.clone());
                add("creator_fee_bps = 300 (the max)".into(), vec![Patch::new(pool, 261, &300u64.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                add("creator_fee_bps = 1000 (above max 300)".into(), vec![Patch::new(pool, 261, &1000u64.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                add("creator_fee_bps = 1000, can_edit 1".into(), vec![Patch::new(pool, 261, &1000u64.to_le_bytes()), Patch::new(pool, 269, &[1])], snap, opts5.clone(), true, both.clone());
                // the quote amounts the pool holds back (u64 @271, @279; REVIEW.md F1): a sell may pay out at most
                // Q − (held_0 + held_1) net of the LP fee; the probe sizes include the crate's capacity ±1, ±2
                let qu = q as u64;
                for (h0, h1) in [(qu / 3, 0), (0, qu / 5), (qu / 4, qu / 4), (qu / 2, qu / 2 - 1), (qu / 2, qu - qu / 2), (1, 1)] {
                    add(format!("held quote {h0} + {h1}"), vec![Patch::new(pool, 271, &h0.to_le_bytes()), Patch::new(pool, 279, &h1.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                }
                // more than the vault: the program fails both instructions (6023) and the crate refuses the leg
                // (HeldExceedsVault); and an unidentified tail byte (Abort)
                add("held quote > vault".into(), vec![Patch::new(pool, 271, &qu.to_le_bytes()), Patch::new(pool, 279, &1u64.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                add("tail byte 270 set".into(), vec![Patch::new(pool, 270, &[1])], snap, opts5.clone(), false, both.clone());
                let mint = h0.tokens.t0;
                let supply = u64_at(&h0.view[&mint].data, 36).unwrap();
                for (num, den) in [(1u64, 1000u64), (1, 30), (5, 1), (60, 1), (2000, 1)] {
                    let s = (supply as u128 * num as u128 / den as u128).min(u64::MAX as u128) as u64;
                    add(format!("base supply x{num}/{den} (market-cap tier)"), vec![Patch::new(mint, 36, &s.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                }
                let _ = pump_canonical_bump(&d);
            }
            Venue::RayCpmm => {
                let (v0, v1) = (venues::token_amount(&h0.view[&h0.tokens.vault0].data).unwrap(), venues::token_amount(&h0.view[&h0.tokens.vault1].data).unwrap());
                add("owed fees 25%".into(), vec![Patch::new(pool, 341, &(v0 / 4).to_le_bytes()), Patch::new(pool, 365, &(v1 / 4).to_le_bytes())], snap, opts5.clone(), true, both.clone());
                let cfg = Address::new_from_array(d[8..40].try_into().unwrap());
                add("trade fee 1%".into(), vec![Patch::new(cfg, 12, &10_000u64.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                add("trade fee 1 ppm".into(), vec![Patch::new(cfg, 12, &1u64.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                for on in 0u8..=2 {
                    add(format!("creator fee 3% on={on}"), vec![Patch::new(cfg, 108, &30_000u64.to_le_bytes()), Patch::new(pool, 389, &[on, 1])], snap, opts5.clone(), true, both.clone());
                }
            }
            Venue::RayAmmV4 => {
                add("fee 30/10000".into(), vec![Patch::new(pool, 176, &30u64.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                add("fee 1/3".into(), vec![Patch::new(pool, 176, &1u64.to_le_bytes()), Patch::new(pool, 184, &3u64.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                add("fee 0".into(), vec![Patch::new(pool, 176, &0u64.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                add("status 7, open".into(), vec![Patch::new(pool, 0, &7u64.to_le_bytes()), Patch::new(pool, 224, &((snap.unix_timestamp - 1) as u64).to_le_bytes())], snap, opts5.clone(), false, both.clone());
                add("status 7, not open".into(), vec![Patch::new(pool, 0, &7u64.to_le_bytes()), Patch::new(pool, 224, &((snap.unix_timestamp + 100) as u64).to_le_bytes())], snap, opts5.clone(), false, both.clone());
            }
            Venue::DammV2 => {
                let (filter, decay, last) = (u16_at(&d, 74) as i64, u16_at(&d, 76) as i64, u64_at(&d, 80).unwrap() as i64);
                if d[56] != 0 {
                    for dt in [0, filter - 1, filter, decay - 1, decay, 10 * decay] {
                        add(format!("clock last+{dt}"), vec![], at(last.max(snap.unix_timestamp - 100_000) + dt), opts5.clone(), false, both.clone());
                    }
                }
                let (mode, act) = (d[16], u64_at(&d, 472).unwrap() as i64);
                let nper = u16_at(&d, 22) as i64;
                if mode <= 1 {
                    let pf = u64_at(&d, 24).unwrap() as i64;
                    if pf > 0 {
                        for k in [0, 1, nper - 1, nper, nper + 10] {
                            for e in [0, pf - 1] { add(format!("scheduler period {k} (+{e}s)"), vec![], at(act + k * pf + e), opts5.clone(), false, both.clone()); }
                        }
                    }
                } else if mode == 3 || mode == 4 {
                    let exp = u32::from_le_bytes(d[28..32].try_into().unwrap()) as i64;
                    for e in [-1, 0, 1] { add(format!("market-cap scheduler expiry {e:+}"), vec![], at(act + exp + e), opts5.clone(), false, both.clone()); }
                }
                let (sp, smin, smax) = (u128_at(&d, 456), u128_at(&d, 424), u128_at(&d, 440));
                if d[484] != 2 {
                    add("narrow range: sqrt_max = P(1+2^-14)".into(), vec![Patch::new(pool, 440, &(sp + (sp >> 14)).to_le_bytes())], snap, opts5.clone(), true, vec![Dir::OneForZero]);
                    add("narrow range: sqrt_min = P(1-2^-14)".into(), vec![Patch::new(pool, 424, &(sp - (sp >> 14)).to_le_bytes())], snap, opts5.clone(), true, vec![Dir::ZeroForOne]);
                    let _ = (smin, smax);
                }
                // fee cap: a huge accumulator (variable fee above the max), both fee versions
                if d[56] != 0 {
                    for fv in [0u8, 1] {
                        add(format!("volatility_accumulator 1e9, fee_version {fv}"), vec![Patch::new(pool, 120, &1_000_000_000u128.to_le_bytes()), Patch::new(pool, 486, &[fv]), Patch::new(pool, 80, &(snap.unix_timestamp as u64).to_le_bytes())], snap, opts5.clone(), true, both.clone());
                    }
                }
                // the rate limiter (mode 2) in force for B->A
                if d[484] == 1 {
                    let rb = venues::token_amount(&h0.view[&h0.tokens.vault1].data).unwrap();
                    let mut bf = vec![0u8; 32];
                    bf[0..8].copy_from_slice(&10_000_000u64.to_le_bytes());
                    bf[8] = 2;
                    bf[14..16].copy_from_slice(&50u16.to_le_bytes());
                    bf[16..20].copy_from_slice(&3_600u32.to_le_bytes());
                    bf[20..24].copy_from_slice(&4_000u32.to_le_bytes());
                    bf[24..32].copy_from_slice(&(rb / 2_000).max(1).to_le_bytes());
                    let act = (snap.unix_timestamp - 600) as u64;
                    add("rate limiter in force".into(), vec![Patch::new(pool, 8, &bf), Patch::new(pool, 472, &act.to_le_bytes())], snap, opts5.clone(), true, both.clone());
                }
            }
        }
    }
    out
}

#[derive(Default, serde::Serialize)]
struct Tally { exact: usize, both_refuse: usize, budget: usize, cu_limit: usize, aborted: usize, mismatches: usize }

#[test]
fn adversarial_states_and_boundary_sizes() {
    let sizing = sizing_dir();
    if !sizing.join("Cargo.toml").exists() { return skip("arbx-sizing is not there"); }
    let bridge = match build_bridge(&sizing) { Ok(b) => b, Err(e) => return skip(&format!("sizing-bridge does not build:\n{e}")) };
    let fx = Fixtures::load().unwrap();
    let probes = probes(&fx);
    let mut legs = vec![];
    let mut meta = vec![];
    for (pi, pr) in probes.iter().enumerate() {
        let (h, p) = (&pr.h, &pr.h.fixture);
        for &dir in &pr.dirs {
            let Ok(sw) = h.build(dir, 1, &pr.opts) else { continue };
            if sw.dlmm_arrays.len() > 5 { continue; }
            let (kind, t0_in) = kind_of(p.venue, dir);
            let mut amounts: Vec<u64> = size_ladder(h.input_reserve(dir).max(1_000_000), 24).into_iter().chain([1, 2, 10, 100, 1_000]).collect();
            amounts.sort();
            amounts.dedup();
            let accounts: Vec<Value> = sw.ix.accounts.iter().map(|m| {
                let a = h.svm().get_account(&m.pubkey).unwrap_or_default();
                let data = if a.executable { vec![] } else { a.data };
                json!({"key": m.pubkey.to_string(), "owner": a.owner.to_string(), "data": b64(&data)})
            }).collect();
            let pump_bump = if p.venue == Venue::PumpSwap { pump_canonical_bump(&h.view[&h.pool].data) } else { 0 };
            legs.push(json!({"id": legs.len(), "kind": kind, "base_or_token0_in": t0_in, "n_bin_arrays": sw.dlmm_arrays.len(),
                "pump_bump": pump_bump, "program": p.venue.program().to_string(), "input_mint": sw.mint_in.to_string(),
                "accounts": accounts, "amounts": amounts, "probe": pr.probe,
                "clock": {"slot": pr.clock.slot, "unix_timestamp": pr.clock.unix_timestamp, "epoch": pr.clock.epoch}}));
            meta.push((pi, dir));
        }
    }
    let mut resp: Vec<Value> = vec![Value::Null; legs.len()];
    let mut by_clock: BTreeMap<String, Vec<Value>> = BTreeMap::new();
    for l in &legs { by_clock.entry(l["clock"].to_string()).or_default().push(l.clone()); }
    for (clock, ls) in by_clock {
        let req = json!({"clock": serde_json::from_str::<Value>(&clock).unwrap(), "legs": ls});
        let mut child = Command::new(&bridge).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
        child.stdin.take().unwrap().write_all(req.to_string().as_bytes()).unwrap();
        let out = child.wait_with_output().unwrap();
        assert!(out.status.success(), "sizing-bridge crashed (a panic in arbx-sizing):\n{}", String::from_utf8_lossy(&out.stderr));
        let v: Value = serde_json::from_slice(&out.stdout).unwrap();
        for r in v["legs"].as_array().unwrap() { resp[r["id"].as_u64().unwrap() as usize] = r.clone(); }
    }
    let mut tally: BTreeMap<String, Tally> = BTreeMap::new();
    let mut problems = vec![];
    let mut rows = vec![];
    for (i, r) in resp.iter().enumerate() {
        let (pi, dir) = meta[i];
        let pr = &probes[pi];
        let (h, p) = (&pr.h, &pr.h.fixture);
        let key = format!("{} {} [{}]", p.venue.name(), &p.pool[..6], pr.label);
        let t = tally.entry(key.clone()).or_default();
        let parse = r["parse"].as_str().unwrap_or("missing").to_string();
        if parse.starts_with("desc:") { problems.push(format!("{key} {}: DescError on an engine-built leg: {parse}", dir.short())); }
        // REVIEW.md F5: the limited direction cannot execute through the engine's leg, so the crate must refuse it
        if pr.label == "rate limiter in force" && !dir.zfo() && parse != "abort:Damm(RateLimiter)" {
            problems.push(format!("{key} {}: the rate limiter is in force but the leg parsed as {parse}", dir.short()));
        }
        let clock = pr.clock.to_clock();
        let max_bins = r["max_bins"].as_u64().unwrap_or(255);
        for q0 in r["quotes"].as_array().unwrap() {
            let x = q0["amount"].as_u64().unwrap();
            // a Budget refusal: compare the same quote without a budget, and check the budget really binds
            let budget = q0["err"].as_str() == Some("Budget");
            let q = if budget { &q0["unbounded"] } else { q0 };
            let err = q["err"].as_str().unwrap_or("");
            // above 2^62 the test wallet's input plus the pool vault overflow u64 in the token program (a harness
            // artifact, not a venue limit): such sizes are not compared (REVIEW.md, minor finding on vault headroom)
            if x > 1u64 << 62 { continue; }
            if !q["ok"].as_bool().unwrap() && (parse != "ok" || err.starts_with("Abort")) {
                t.aborted += 1;
                rows.push(json!({"case": key, "dir": dir.short(), "amount_in": x, "verdict": format!("aborted {parse} {err}")}));
                continue;
            }
            let s = h.swap_with(dir, x, &pr.opts, |svm| svm.set_sysvar(&clock));
            let mut verdict = if q["ok"].as_bool().unwrap() {
                let (o, sp) = (q["out"].as_u64().unwrap(), q["spent"].as_u64().unwrap());
                if s.ok && s.amount_out == o && s.spent == sp { "exact".to_string() } else {
                    format!("MISMATCH quote out {o} spent {sp} vs program {} out {} spent {} (diff out {}) {}", if s.ok { "ok" } else { "FAILED" }, s.amount_out, s.spent,
                        s.amount_out as i128 - o as i128, if s.ok { String::new() } else { s.venue_error() })
                }
            } else if s.failed_or_zero() { format!("both refuse ({err})") } else {
                // TooLarge claims a venue capacity: the venue swapping is a mismatch (no "conservative" verdict)
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
                else if verdict.starts_with("venue CU limit") { t.cu_limit += 1; } else if verdict == "exact" { t.exact += 1; } else { t.both_refuse += 1; }
            if verdict.starts_with("MISMATCH") { problems.push(format!("{key} {} x={x}: {verdict}", dir.short())); }
            rows.push(json!({"case": key, "dir": dir.short(), "amount_in": x, "quote": q0, "program_ok": s.ok, "program_out": s.amount_out,
                "program_spent": s.spent, "cu": s.cu_venue, "verdict": verdict}));
        }
    }
    println!("{:<78} {:>6} {:>8} {:>6} {:>6} {:>7} {:>8}", "case", "exact", "refuse", "budget", "cu-lim", "abort", "MISMATCH");
    for (k, t) in &tally { println!("{k:<78} {:>6} {:>8} {:>6} {:>6} {:>7} {:>8}", t.exact, t.both_refuse, t.budget, t.cu_limit, t.aborted, t.mismatches); }
    let sum = |f: fn(&Tally) -> usize| tally.values().map(f).sum::<usize>();
    println!("{:<78} {:>6} {:>8} {:>6} {:>6} {:>7} {:>8}", "TOTAL", sum(|t| t.exact), sum(|t| t.both_refuse), sum(|t| t.budget), sum(|t| t.cu_limit), sum(|t| t.aborted), sum(|t| t.mismatches));
    let mut by_venue: BTreeMap<String, [usize; 6]> = BTreeMap::new();
    for (k, t) in &tally {
        let v = by_venue.entry(k.split(' ').next().unwrap_or("?").to_string()).or_default();
        for (i, n) in [t.exact, t.both_refuse, t.budget, t.cu_limit, t.aborted, t.mismatches].into_iter().enumerate() { v[i] += n; }
    }
    for (v, n) in &by_venue { println!("VENUE {v:<10} exact {:>6} refuse {:>6} budget {:>5} cu-limit {:>4} abort {:>5} MISMATCH {:>5}", n[0], n[1], n[2], n[3], n[4], n[5]); }
    let bins_of = |r: &Value| r["quote"]["bins"].as_u64();
    let cu_min = rows.iter().filter(|r| r["verdict"].as_str().unwrap_or("").starts_with("venue CU")).filter_map(bins_of).min();
    let ok_max = rows.iter().filter(|r| r["program_ok"] == true).filter_map(bins_of).max();
    println!("DLMM bins read (empty bins inside visited arrays included): venue out of CU from {cu_min:?}; largest successful swap {ok_max:?}");
    let out = Path::new(MANIFEST_DIR).join("results");
    std::fs::create_dir_all(&out).unwrap();
    std::fs::write(out.join("adversarial.json"), serde_json::to_string_pretty(&json!({"tally": tally, "rows": rows})).unwrap()).unwrap();
    for pbl in problems.iter().take(80) { println!("{pbl}"); }
    assert!(problems.is_empty(), "{} mismatches (first 80 above)", problems.len());
}

fn b64(b: &[u8]) -> String { use base64::Engine as _; base64::engine::general_purpose::STANDARD.encode(b) }

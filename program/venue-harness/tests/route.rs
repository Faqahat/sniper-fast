//! Route-level checks of arbx-sizing's planner on the REAL venue binaries (DESIGN.md §6.3 "route level",
//! assertions 2-5, without arbx-exec): the HOTBOT pair PumpSwap GLL3 ↔ DLMM 6D4E from the snapshots, with a price
//! gap made by scaling GLL3's quote vault. `plan` runs in the sizing bridge (plan mode) with the engine's DLMM walk
//! budget (`max_bins` "auto": the bins the leg's exact swap needs at the cap); each candidate size is then executed
//! leg by leg on the dumped programs (leg 1 spends exactly what leg 0 delivered, as arbx-exec chains it):
//!   2. realized profit at the planned size == modeled_profit, realized at e == modeled_profit_e;
//!   3. realized(plan) >= realized(e);
//!   4. realized(plan) >= the best of a 64-point grid (plus a dense grid around the plan) minus 2ε;
//!   F3. whenever the venue fills e, the plan evaluated e (no walk-budget refusal at or below e);
//!   5. BASKET (both directions of the pair as two pairs over four legs): the chosen pair's realized profit is at
//!      least every pair's realized profit at its own planned size, and pair 0 at e.
//!
//!   VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release --test route -- --nocapture
mod common;
use serde_json::{json, Value};
use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};
use venue_harness::venues::pump_canonical_bump;
use venue_harness::*;

fn b64(b: &[u8]) -> String { use base64::Engine as _; base64::engine::general_purpose::STANDARD.encode(b) }

/// one leg as the engine lays it out (same encoding as tests/exactness.rs)
fn leg_json(h: &Harness, dir: Dir, opts: &BuildOpts) -> Value {
    let sw = h.build(dir, 1, opts).unwrap();
    let kind = match h.venue {
        Venue::PumpSwap => if dir.zfo() { 2 } else { 1 },
        Venue::RayCpmm => 3, Venue::RayAmmV4 => 4, Venue::Dlmm => 5, Venue::DammV2 => 6, Venue::RayClmm => 7, Venue::Whirlpool => 8,
    };
    let accounts: Vec<Value> = sw.ix.accounts.iter().map(|m| {
        let a = h.svm().get_account(&m.pubkey).unwrap_or_default();
        let data = if a.executable { vec![] } else { a.data };
        json!({"key": m.pubkey.to_string(), "owner": a.owner.to_string(), "data": b64(&data)})
    }).collect();
    let bump = if h.venue == Venue::PumpSwap { pump_canonical_bump(&h.view[&h.pool].data) } else { 0 };
    json!({"kind": kind, "base_or_token0_in": dir.zfo(), "n_bin_arrays": sw.dlmm_arrays.len(), "pump_bump": bump, "max_bins": "auto",
           "program": h.venue.program().to_string(), "input_mint": sw.mint_in.to_string(), "accounts": accounts})
}

/// run the bridge in plan mode
fn plan_req(bridge: &Path, req: &Value) -> Value {
    let mut child = Command::new(bridge).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    child.stdin.take().unwrap().write_all(req.to_string().as_bytes()).unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success(), "bridge crashed: {}", String::from_utf8_lossy(&out.stderr));
    serde_json::from_slice(&out.stdout).unwrap()
}

/// realized round trip on the real programs: (profit, leg-0 output) or None when a leg fails
fn realized(a: &Harness, da: Dir, b: &Harness, db: Dir, opts: &BuildOpts, x: u64) -> Option<(i128, u64)> {
    let s0 = a.swap_opts(da, x, opts);
    if !s0.ok || s0.amount_out == 0 { return None; }
    let s1 = b.swap_opts(db, s0.amount_out, opts);
    if !s1.ok { return None; }
    Some((s1.amount_out as i128 - s0.spent as i128, s0.amount_out))
}

#[test]
fn hotbot_routes_plan_on_the_real_programs() {
    let sizing = common::sizing_dir();
    if !sizing.join("Cargo.toml").exists() { println!("SKIP route: no arbx-sizing"); return; }
    let bridge = match common::build_bridge(&sizing, "sizing-bridge-route") {
        Ok(b) => b,
        Err(e) => { if common::required() { panic!("{e}") } println!("SKIP route: {e}"); return; }
    };
    let fx = Fixtures::load().unwrap();
    let (Some(gll3), Some(d6)) = (fx.find("GLL3"), fx.find("6D4E")) else { println!("SKIP route: HOTBOT fixtures missing"); return };
    let opts = BuildOpts { dlmm_max_arrays: 5, ..Default::default() };
    let clock = d6.clock;
    let mut problems = vec![];
    // GLL3's quote vault scaled by num/1000: below 1000 GLL3 is cheap (buy there, sell on 6D4E), above it is dear
    for (num, e) in [(880u64, 100_000_000u64), (970, 100_000_000), (995, 50_000_000), (1120, 100_000_000), (1030, 100_000_000), (1005, 50_000_000)] {
        let h0 = Harness::new(&fx, &gll3.pool_key()).unwrap();
        let qv = h0.tokens.vault1;
        let q = venues::token_amount(&h0.view[&qv].data).unwrap();
        let pump = Harness::with_patches(&fx, &gll3.pool_key(), &[Patch::new(qv, 64, &(q / 1000 * num).to_le_bytes())]).unwrap();
        let dlmm = Harness::new(&fx, &d6.pool_key()).unwrap();
        // (buy harness, buy dir, sell harness, sell dir)
        let (a, da, b, db, name) = if num < 1000 {
            (&pump, Dir::OneForZero, &dlmm, Dir::ZeroForOne, format!("GLL3 x{num}/1000 buy -> 6D4E sell"))
        } else {
            (&dlmm, Dir::OneForZero, &pump, Dir::ZeroForOne, format!("6D4E buy -> GLL3 x{num}/1000 sell"))
        };
        let cap = 50_000_000_000u64;
        let req = json!({"clock": {"slot": clock.slot, "unix_timestamp": clock.unix_timestamp, "epoch": clock.epoch},
            "legs": [leg_json(a, da, &opts), leg_json(b, db, &opts)],
            "plan": {"cap": cap, "min_size": 1_000, "engine_amount": e, "min_profit": 1, "flags": 0, "pairs": [[0, 1]]}});
        let v = plan_req(&bridge, &req);
        let Some(pl) = v.get("plan") else { problems.push(format!("{name}: {v}")); continue };
        let amount = pl["amount"].as_u64().unwrap();
        let mp: i128 = pl["modeled_profit"].as_str().unwrap().parse().unwrap();
        let mpe: Option<i128> = pl["modeled_profit_e"].as_str().map(|s| s.parse().unwrap());
        let r_plan = realized(a, da, b, db, &opts, amount);
        let r_e = realized(a, da, b, db, &opts, e);
        // grid: 64 log-spaced sizes over [1e6, cap] plus 32 around the plan
        let mut grid: Vec<u64> = (0..64).map(|i| (1e6f64 * (cap as f64 / 1e6).powf(i as f64 / 63.0)) as u64).collect();
        grid.extend((0..32).map(|i| (amount as f64 * (0.8 + 0.4 * i as f64 / 31.0)) as u64));
        let best = grid.iter().filter_map(|&x| realized(a, da, b, db, &opts, x).map(|r| (x, r.0))).max_by_key(|r| r.1);
        println!("{name:<36} plan {} x {amount} (x* {}, evals {}, bins {}, max_bins {}) modeled {mp} realized {:?} | e {e} modeled {mpe:?} realized {:?} | grid best {best:?}",
            pl["outcome"], pl["x_star"], pl["evals"], pl["bins"], v["max_bins"], r_plan.map(|r| r.0), r_e.map(|r| r.0));
        // F3: the engine's budget covers the cap, so e (≤ cap) is always evaluated when the venue fills it
        if r_e.is_some() && mpe.is_none() { problems.push(format!("{name}: the venue fills e but the plan did not evaluate it ({pl})")); }
        let eps = 10i128;
        if pl["outcome"] == "Sized" {
            match r_plan {
                None => problems.push(format!("{name}: the planned size {amount} fails on the real programs")),
                Some((r, _)) => {
                    if r != mp { problems.push(format!("{name}: realized {r} != modeled {mp} at x={amount} (diff {})", r - mp)); }
                    if let Some((re, _)) = r_e { if r < re { problems.push(format!("{name}: realized(plan) {r} < realized(e) {re}")); } }
                    if let Some((bx, bv)) = best { if r < bv - eps { problems.push(format!("{name}: realized(plan) {r} < grid best {bv} at x={bx} by {}", bv - r)); } }
                }
            }
        }
        if let (Some(m), Some((re, _))) = (mpe, r_e) { if m != re { problems.push(format!("{name}: realized(e) {re} != modeled_profit_e {m} (diff {})", re - m)); } }
    }
    for p in &problems { println!("PROBLEM {p}"); }
    assert!(problems.is_empty(), "{} route problems", problems.len());
}

/// BASKET on the real programs: the HOTBOT pair in both directions as two pairs over four legs
/// (0 GLL3 buy, 1 6D4E sell, 2 6D4E buy, 3 GLL3 sell; pairs (0,1) (2,3)). Whichever direction the gap favours,
/// the plan picks that pair, realizes its modeled profit to the unit, beats pair 0 at e and every pair at its own
/// planned size (DESIGN.md §6.3 assertion 5). With min_profit above every candidate: NoProfit (EARLY_ABORT's verdict).
#[test]
fn hotbot_basket_on_the_real_programs() {
    let sizing = common::sizing_dir();
    if !sizing.join("Cargo.toml").exists() { println!("SKIP basket: no arbx-sizing"); return; }
    let bridge = match common::build_bridge(&sizing, "sizing-bridge-route") {
        Ok(b) => b,
        Err(e) => { if common::required() { panic!("{e}") } println!("SKIP basket: {e}"); return; }
    };
    let fx = Fixtures::load().unwrap();
    let (Some(gll3), Some(d6)) = (fx.find("GLL3"), fx.find("6D4E")) else { println!("SKIP basket: HOTBOT fixtures missing"); return };
    let opts = BuildOpts { dlmm_max_arrays: 5, ..Default::default() };
    let clock = d6.clock;
    let mut problems = vec![];
    let mut sized = 0;
    for (num, e) in [(880u64, 100_000_000u64), (1120, 100_000_000), (930, 300_000_000), (1060, 50_000_000)] {
        let h0 = Harness::new(&fx, &gll3.pool_key()).unwrap();
        let qv = h0.tokens.vault1;
        let q = venues::token_amount(&h0.view[&qv].data).unwrap();
        let pump = Harness::with_patches(&fx, &gll3.pool_key(), &[Patch::new(qv, 64, &(q / 1000 * num).to_le_bytes())]).unwrap();
        let dlmm = Harness::new(&fx, &d6.pool_key()).unwrap();
        let legs: [(&Harness, Dir); 4] = [(&pump, Dir::OneForZero), (&dlmm, Dir::ZeroForOne), (&dlmm, Dir::OneForZero), (&pump, Dir::ZeroForOne)];
        let pairs = [(0usize, 1usize), (2, 3)];
        let cap = 50_000_000_000u64;
        let clock_json = json!({"slot": clock.slot, "unix_timestamp": clock.unix_timestamp, "epoch": clock.epoch});
        let legs_json: Vec<Value> = legs.iter().map(|(h, d)| leg_json(h, *d, &opts)).collect();
        let req = |pairs: &[(usize, usize)], min_profit: u64, flags: u8| json!({"clock": clock_json, "legs": legs_json,
            "plan": {"cap": cap, "min_size": 1_000, "engine_amount": e, "min_profit": min_profit, "flags": flags, "pairs": pairs.iter().map(|p| json!([p.0, p.1])).collect::<Vec<_>>()}});
        let v = plan_req(&bridge, &req(&pairs, 1, 0));
        let Some(pl) = v.get("plan") else { problems.push(format!("x{num}: {v}")); continue };
        let real = |k: usize, x: u64| { let (b, s) = pairs[k]; realized(legs[b].0, legs[b].1, legs[s].0, legs[s].1, &opts, x) };
        let (pair, amount) = (pl["pair"].as_u64().unwrap() as usize, pl["amount"].as_u64().unwrap());
        let mp: i128 = pl["modeled_profit"].as_str().unwrap().parse().unwrap();
        let r = real(pair, amount);
        // each pair alone (SELF_SIZE plan over the same legs)
        let alone: Vec<Option<i128>> = (0..2).map(|k| {
            let v = plan_req(&bridge, &req(&pairs[k..k + 1], 1, 0));
            let p = &v["plan"];
            if p["outcome"] != "Sized" { return None; }
            real(k, p["amount"].as_u64().unwrap()).map(|r| r.0)
        }).collect();
        let r_e = real(0, e).map(|r| r.0);
        println!("basket GLL3 x{num}/1000: plan {} pair {pair} x {amount} modeled {mp} realized {:?} | pair alone {alone:?} | pair 0 at e {r_e:?} (max_bins {})",
            pl["outcome"], r.map(|r| r.0), v["max_bins"]);
        if pl["outcome"] == "Sized" {
            sized += 1;
            match r {
                None => problems.push(format!("x{num}: the planned size fails on the real programs")),
                Some((rv, _)) => {
                    if rv != mp { problems.push(format!("x{num}: realized {rv} != modeled {mp}")); }
                    for (k, a) in alone.iter().enumerate() { if let Some(a) = a { if rv < *a { problems.push(format!("x{num}: chosen pair realizes {rv} < pair {k} alone {a}")); } } }
                    if let Some(re) = r_e { if rv < re { problems.push(format!("x{num}: {rv} < pair 0 at e {re}")); } }
                    // the profitable direction: GLL3 cheap (num < 1000) → pair 0, dear → pair 1
                    if (num < 1000) != (pair == 0) { problems.push(format!("x{num}: chose pair {pair}")); }
                }
            }
            // min_profit above the best: NoProfit, the verdict EARLY_ABORT reverts on
            let v = plan_req(&bridge, &req(&pairs, (mp as u64).saturating_add(1), 2));
            if v["plan"]["outcome"] != "NoProfit" { problems.push(format!("x{num}: min_profit above the plan's profit gave {}", v["plan"])); }
        }
    }
    for p in &problems { println!("PROBLEM {p}"); }
    assert!(problems.is_empty(), "{} basket problems", problems.len());
    assert!(sized >= 3, "{sized} sized baskets");
}

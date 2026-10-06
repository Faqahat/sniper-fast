//! Route-level checks of arbx-sizing's planner over Raydium CLMM and Orca Whirlpool legs on the REAL programs
//! (PLAN-ADDENDUM WP-21; DESIGN.md §6.3 assertions 2-5 without arbx-exec, as tests/route.rs for HOTBOT): the J6pQ/SOL
//! pair Raydium CLMM DCAL (dynamic fee, tick spacing 1) ↔ Orca 4uny (adaptive fee), with a price gap made by moving
//! 4uny's price by k ticks (inside its current tick array, where no initialized tick lies). `plan` runs in the sizing
//! bridge (plan mode: the locator's piecewise-Möbius model over the legs' exact swap steps, then exact evaluations);
//! each planned size, `e` and a grid are then executed leg by leg on the dumped programs (leg 1 spends what leg 0
//! delivered):
//!   2. realized profit at the planned size == modeled_profit, and at e == modeled_profit_e;
//!   3. realized(plan) >= realized(e);
//!   4. realized(plan) >= the best of a 64-point grid (plus a dense one around the plan) minus 2ε;
//!   5. BASKET (both directions as two pairs over four legs): the profitable pair is chosen, realizes its modeled
//!      profit, beats each pair alone and pair 0 at e; min_profit above the plan gives NoProfit.
//!
//!   VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release --test clmm_route -- --nocapture
mod common;
use common::clmm::{kind_of, leg_accounts, n_arrays};
use serde_json::{json, Value};
use std::io::Write;
use std::path::Path;
use std::process::{Command, Stdio};
use venue_harness::*;

fn leg_json(h: &Harness, dir: Dir, opts: &BuildOpts) -> Value {
    let sw = h.build(dir, 1, opts).unwrap();
    json!({"kind": kind_of(h.venue), "base_or_token0_in": dir.zfo(), "n_bin_arrays": n_arrays(h.venue, &sw), "pump_bump": 0,
        "program": h.venue.program().to_string(), "input_mint": sw.mint_in.to_string(), "accounts": leg_accounts(h, &sw)})
}

fn plan_req(bridge: &Path, req: &Value) -> Value {
    let mut child = Command::new(bridge).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::piped()).spawn().unwrap();
    child.stdin.take().unwrap().write_all(req.to_string().as_bytes()).unwrap();
    let out = child.wait_with_output().unwrap();
    assert!(out.status.success(), "bridge crashed: {}", String::from_utf8_lossy(&out.stderr));
    serde_json::from_slice(&out.stdout).unwrap()
}

/// the round trip on the real programs, both legs under `clock` (the plan's): (profit, leg-0 output)
fn realized(a: &Harness, da: Dir, b: &Harness, db: Dir, opts: &BuildOpts, clock: &solana_clock::Clock, x: u64) -> Option<(i128, u64)> {
    let swap = |h: &Harness, d: Dir, x: u64| { let mut s = h.session(); s.svm.set_sysvar(clock); s.swap_opts(d, x, opts) };
    let s0 = swap(a, da, x);
    if !s0.ok || s0.amount_out == 0 { return None; }
    let s1 = swap(b, db, s0.amount_out);
    if !s1.ok { return None; }
    Some((s1.amount_out as i128 - s0.spent as i128, s0.amount_out))
}

/// Orca pool `pool` with its price moved by `k` ticks: the sqrt price in the middle of tick (tick + k), the current
/// tick set to it (sqrt(1.0001^(t + 1/2)) · 2^64; f64 is exact enough at half a tick from either end)
fn moved_whirlpool(fx: &Fixtures, pool: &solana_address::Address, k: i32) -> Harness {
    let h0 = Harness::new(fx, pool).unwrap();
    let d = &h0.view[pool].data;
    let t = i32::from_le_bytes(d[81..85].try_into().unwrap()) + k;
    let sp = (1.0001f64.powf((t as f64 + 0.5) / 2.0) * 18_446_744_073_709_551_616.0) as u128;
    Harness::with_patches(fx, pool, &[Patch::new(*pool, 65, &sp.to_le_bytes()), Patch::new(*pool, 81, &t.to_le_bytes())]).unwrap()
}

#[test]
fn clmm_routes_plan_on_the_real_programs() {
    let sizing = common::sizing_dir();
    if !sizing.join("Cargo.toml").exists() { println!("SKIP clmm route: no arbx-sizing"); return; }
    let bridge = match common::build_bridge(&sizing, "sizing-bridge") {
        Ok(b) => b,
        Err(e) => { if common::required() { panic!("{e}") } println!("SKIP clmm route: {e}"); return; }
    };
    let fx = Fixtures::load_clmm().unwrap();
    let (Some(ray), Some(orca)) = (fx.find("DCALKkpd"), fx.find("4uny6Y7d")) else { panic!("the J6pQ/SOL fixtures are missing") };
    let opts = BuildOpts::default();
    // the later snapshot's Clock for both legs (the two snapshots are seconds apart; Orca refuses a Clock before its
    // last reward or reference update)
    let clock = if orca.clock.unix_timestamp >= ray.clock.unix_timestamp { orca.clock } else { ray.clock };
    let mut problems = vec![];
    let mut sized = 0;
    for (k, e) in [(250i32, 100_000_000u64), (120, 100_000_000), (60, 50_000_000), (-60, 50_000_000), (-120, 100_000_000), (-250, 100_000_000)] {
        let wp = moved_whirlpool(&fx, &orca.pool_key(), k);
        let rh = Harness::new(&fx, &ray.pool_key()).unwrap();
        // 4uny: a = WSOL, b = J6pQ; DCAL: token0 = WSOL, token1 = J6pQ. A higher Orca tick gives more J6pQ per SOL there:
        // buy J6pQ on Orca, sell it on Raydium
        let (a, da, b, db, name) = if k > 0 {
            (&wp, Dir::ZeroForOne, &rh, Dir::OneForZero, format!("4uny {k:+} ticks buy -> DCAL sell"))
        } else {
            (&rh, Dir::ZeroForOne, &wp, Dir::OneForZero, format!("DCAL buy -> 4uny {k:+} ticks sell"))
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
        let ck = clock.to_clock();
        let r_plan = realized(a, da, b, db, &opts, &ck, amount);
        let r_e = realized(a, da, b, db, &opts, &ck, e);
        let mut grid: Vec<u64> = (0..64).map(|i| (1e6f64 * (cap as f64 / 1e6).powf(i as f64 / 63.0)) as u64).collect();
        grid.extend((0..32).map(|i| (amount as f64 * (0.8 + 0.4 * i as f64 / 31.0)) as u64));
        let best = grid.iter().filter_map(|&x| realized(a, da, b, db, &opts, &ck, x).map(|r| (x, r.0))).max_by_key(|r| r.1);
        println!("{name:<34} plan {} x {amount} (x* {}, evals {}, steps {}) modeled {mp} realized {:?} | e {e} modeled {mpe:?} realized {:?} | grid best {best:?}",
            pl["outcome"], pl["x_star"], pl["evals"], pl["bins"], r_plan.map(|r| r.0), r_e.map(|r| r.0));
        if r_e.is_some() && mpe.is_none() { problems.push(format!("{name}: the venue fills e but the plan did not evaluate it ({pl})")); }
        let eps = 10i128;
        if pl["outcome"] == "Sized" {
            sized += 1;
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
    assert!(sized >= 4, "{sized} sized routes");
}

/// BASKET over both directions: legs 0 4uny buy, 1 DCAL sell, 2 DCAL buy, 3 4uny sell; pairs (0,1), (2,3)
#[test]
fn clmm_basket_on_the_real_programs() {
    let sizing = common::sizing_dir();
    if !sizing.join("Cargo.toml").exists() { println!("SKIP clmm basket: no arbx-sizing"); return; }
    let bridge = match common::build_bridge(&sizing, "sizing-bridge") {
        Ok(b) => b,
        Err(e) => { if common::required() { panic!("{e}") } println!("SKIP clmm basket: {e}"); return; }
    };
    let fx = Fixtures::load_clmm().unwrap();
    let (Some(ray), Some(orca)) = (fx.find("DCALKkpd"), fx.find("4uny6Y7d")) else { panic!("the J6pQ/SOL fixtures are missing") };
    let opts = BuildOpts::default();
    let clock = if orca.clock.unix_timestamp >= ray.clock.unix_timestamp { orca.clock } else { ray.clock };
    let mut problems = vec![];
    let mut sized = 0;
    // gaps inside the adaptive fee's reach: ±250 ticks from 4uny's reference already raise its fee past the gap (the
    // routes test shows NoProfit there, realized as modeled)
    for (k, e) in [(130i32, 100_000_000u64), (90, 50_000_000), (-90, 50_000_000), (-60, 50_000_000)] {
        let wp = moved_whirlpool(&fx, &orca.pool_key(), k);
        let rh = Harness::new(&fx, &ray.pool_key()).unwrap();
        let legs: [(&Harness, Dir); 4] = [(&wp, Dir::ZeroForOne), (&rh, Dir::OneForZero), (&rh, Dir::ZeroForOne), (&wp, Dir::OneForZero)];
        let pairs = [(0usize, 1usize), (2, 3)];
        let cap = 50_000_000_000u64;
        let clock_json = json!({"slot": clock.slot, "unix_timestamp": clock.unix_timestamp, "epoch": clock.epoch});
        let legs_json: Vec<Value> = legs.iter().map(|(h, d)| leg_json(h, *d, &opts)).collect();
        let req = |pairs: &[(usize, usize)], min_profit: u64, flags: u8| json!({"clock": clock_json, "legs": legs_json,
            "plan": {"cap": cap, "min_size": 1_000, "engine_amount": e, "min_profit": min_profit, "flags": flags, "pairs": pairs.iter().map(|p| json!([p.0, p.1])).collect::<Vec<_>>()}});
        let v = plan_req(&bridge, &req(&pairs, 1, 0));
        let Some(pl) = v.get("plan") else { problems.push(format!("{k:+}: {v}")); continue };
        let ck = clock.to_clock();
        let real = |p: usize, x: u64| { let (b, s) = pairs[p]; realized(legs[b].0, legs[b].1, legs[s].0, legs[s].1, &opts, &ck, x) };
        let (pair, amount) = (pl["pair"].as_u64().unwrap() as usize, pl["amount"].as_u64().unwrap());
        let mp: i128 = pl["modeled_profit"].as_str().unwrap().parse().unwrap();
        let r = real(pair, amount);
        let alone: Vec<Option<i128>> = (0..2).map(|q| {
            let v = plan_req(&bridge, &req(&pairs[q..q + 1], 1, 0));
            let p = &v["plan"];
            if p["outcome"] != "Sized" { return None; }
            real(q, p["amount"].as_u64().unwrap()).map(|r| r.0)
        }).collect();
        let r_e = real(0, e).map(|r| r.0);
        println!("basket 4uny {k:+} ticks: plan {} pair {pair} x {amount} modeled {mp} realized {:?} | pair alone {alone:?} | pair 0 at e {r_e:?}",
            pl["outcome"], r.map(|r| r.0));
        if pl["outcome"] == "Sized" {
            sized += 1;
            match r {
                None => problems.push(format!("{k:+}: the planned size fails on the real programs")),
                Some((rv, _)) => {
                    if rv != mp { problems.push(format!("{k:+}: realized {rv} != modeled {mp}")); }
                    for (q, a) in alone.iter().enumerate() { if let Some(a) = a { if rv < *a { problems.push(format!("{k:+}: chosen pair realizes {rv} < pair {q} alone {a}")); } } }
                    if let Some(re) = r_e { if rv < re { problems.push(format!("{k:+}: {rv} < pair 0 at e {re}")); } }
                    if (k > 0) != (pair == 0) { problems.push(format!("{k:+}: chose pair {pair}")); }
                }
            }
            let v = plan_req(&bridge, &req(&pairs, (mp as u64).saturating_add(1), 2));
            if v["plan"]["outcome"] != "NoProfit" { problems.push(format!("{k:+}: min_profit above the plan's profit gave {}", v["plan"])); }
        }
    }
    for p in &problems { println!("PROBLEM {p}"); }
    assert!(problems.is_empty(), "{} basket problems", problems.len());
    assert!(sized >= 4, "{sized} sized baskets");
}

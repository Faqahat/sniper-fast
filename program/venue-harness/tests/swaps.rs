//! Real swaps on every fetched pool, both directions, 14 sizes each (>= 10 must succeed per pool and direction; a
//! PumpSwap cashback coin must fail every one: the engine's leg cannot execute it).
//! Records exact outputs and CU in results/swap-runs.json and prints a table.
//!
//!   cargo test --release --test swaps -- --nocapture
use venue_harness::{size_ladder, Dir, Fixtures, Harness, SwapOutcome, Venue};

#[derive(serde::Serialize)]
struct Run { venue: Venue, pool: String, label: String, slot: u64, dir: &'static str, input_reserve: u64, swaps: Vec<SwapOutcome> }

#[test]
fn every_pool_swaps_at_ten_plus_sizes() {
    let fx = Fixtures::load().unwrap();
    assert!(!fx.pools.is_empty(), "no fixtures: run `cargo run --release --bin fetch-fixtures`");
    let mut runs = vec![];
    let mut problems = vec![];
    let t0 = std::time::Instant::now();
    let mut n_swaps = 0;
    println!("{:<9} {:<10} {:<5} {:>5} {:>9} {:>9}  {}", "venue", "pool", "dir", "ok", "cu min", "cu max", "failures");
    for p in fx.pools.values() {
        let h = Harness::new(&fx, &p.pool_key()).unwrap_or_else(|e| panic!("{}: {e}", p.pool));
        for dir in Dir::BOTH {
            let reserve = h.input_reserve(dir);
            let sizes = size_ladder(reserve, 14);
            let swaps: Vec<SwapOutcome> = sizes.iter().map(|&a| h.swap(dir, a)).collect();
            n_swaps += swaps.len();
            let ok: Vec<&SwapOutcome> = swaps.iter().filter(|s| s.ok).collect();
            let cus: Vec<u64> = ok.iter().filter_map(|s| s.cu_venue).collect();
            let fails: Vec<String> = swaps.iter().filter(|s| !s.ok).map(|s| format!("{}: {}", s.amount_in, short_err(s))).collect();
            println!("{:<9} {:<10} {:<5} {:>2}/{:<2} {:>9} {:>9}  {}", p.venue.name(), &p.pool[..8], dir.short(), ok.len(), swaps.len(),
                cus.iter().min().unwrap_or(&0), cus.iter().max().unwrap_or(&0), fails.first().cloned().unwrap_or_default());
            // a cashback coin: the engine's leg cannot execute it (with a pool_v2 the venue fails 6060
            // InvalidCashbackAccumulator / 6061 ...Ata at every size) and arbx-sizing refuses the pool (Pump(Cashback)):
            // that refusal of the census's class is what is checked here
            if !venue_harness::venues::engine_leg_executes(p.venue, &h.view[&h.pool].data) {
                let swapped: Vec<u64> = swaps.iter().filter(|s| s.ok || !s.logs.iter().any(|l| l.contains("Error Number: 6060") || l.contains("Error Number: 6061")))
                    .map(|s| s.amount_in).collect();
                if !swapped.is_empty() { problems.push(format!("{} {} {}: a cashback coin swapped or failed otherwise at {swapped:?}", p.venue.name(), p.pool, dir.short())); }
            } else if ok.len() < 10 { problems.push(format!("{} {} {}: only {} of {} sizes swapped: {fails:?}", p.venue.name(), p.pool, dir.short(), ok.len(), swaps.len())); }
            // the venue's own invariants: output non-decreasing in input, and the input debited exactly
            for w in ok.windows(2) {
                if w[1].amount_out < w[0].amount_out { problems.push(format!("{} {} {}: not monotone at {}", p.venue.name(), p.pool, dir.short(), w[1].amount_in)); }
            }
            for s in &ok {
                if s.spent != s.amount_in { problems.push(format!("{} {} {}: spent {} != amount_in {}", p.venue.name(), p.pool, dir.short(), s.spent, s.amount_in)); }
                if s.cu_venue.is_none() { problems.push(format!("{} {}: no CU line", p.venue.name(), p.pool)); }
            }
            runs.push(Run { venue: p.venue, pool: p.pool.clone(), label: p.label.clone(), slot: p.slot, dir: dir.short(), input_reserve: reserve, swaps });
        }
    }
    println!("{n_swaps} swaps in {:.1}s", t0.elapsed().as_secs_f64());
    let out = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("results");
    std::fs::create_dir_all(&out).unwrap();
    std::fs::write(out.join("swap-runs.json"), serde_json::to_string_pretty(&runs).unwrap()).unwrap();
    assert!(problems.is_empty(), "{}", problems.join("\n"));
}

fn short_err(s: &SwapOutcome) -> String {
    let e = s.venue_error();
    e.chars().take(140).collect()
}

/// Every venue is present in the fixtures with at least 2 pools.
#[test]
fn fixtures_cover_every_venue() {
    let fx = Fixtures::load().unwrap();
    for v in Venue::ALL {
        let n = fx.pools.values().filter(|p| p.venue == v).count();
        assert!(n >= 2, "{}: {n} pools", v.name());
    }
    for (_, id) in venue_harness::keys::PROGRAMS {
        let e = fx.manifest.get(id).unwrap_or_else(|| panic!("{id} not dumped"));
        let elf = venue_harness::fixture::program_elf(e).unwrap();
        assert_eq!(venue_harness::fixture::sha256_hex(&elf), e.sha256, "{} changed on disk", e.name);
    }
}

/// DLMM CU against bins crossed (from the program's own Swap event: start_bin_id @64, end_bin_id @68), with the
/// engine's array list (<= 5): a least-squares line, printed for the CU budget (DESIGN §4.7 used 47k + 5.45k/bin).
#[test]
fn dlmm_cu_per_bin() {
    let fx = Fixtures::load().unwrap();
    let disc = venue_harness::harness::event_disc("Swap");
    let opts = venue_harness::BuildOpts { dlmm_max_arrays: 5, ..Default::default() };
    let mut pts: Vec<(f64, f64)> = vec![];
    for p in fx.pools.values().filter(|p| p.venue == Venue::Dlmm) {
        let h = Harness::new(&fx, &p.pool_key()).unwrap();
        for dir in Dir::BOTH {
            for x in size_ladder(h.input_reserve(dir), 40) {
                let o = h.swap_opts(dir, x, &opts);
                let Some(e) = o.event(&disc) else { continue };
                let bin = |at: usize| i32::from_le_bytes(e[at..at + 4].try_into().unwrap());
                if o.ok { pts.push(((bin(64) - bin(68)).unsigned_abs() as f64, o.cu_venue.unwrap() as f64)); }
            }
        }
    }
    let n = pts.len() as f64;
    let (mx, my) = (pts.iter().map(|p| p.0).sum::<f64>() / n, pts.iter().map(|p| p.1).sum::<f64>() / n);
    let b = pts.iter().map(|p| (p.0 - mx) * (p.1 - my)).sum::<f64>() / pts.iter().map(|p| (p.0 - mx).powi(2)).sum::<f64>();
    let a = my - b * mx;
    let zero: Vec<f64> = pts.iter().filter(|p| p.0 == 0.0).map(|p| p.1).collect();
    println!("DLMM: {} swaps; CU ~= {a:.0} + {b:.0} per bin crossed (max {} bins); in-bin swaps {:.0}..{:.0} CU", pts.len(),
        pts.iter().map(|p| p.0).fold(0.0, f64::max), zero.iter().cloned().fold(f64::MAX, f64::min), zero.iter().cloned().fold(0.0, f64::max));
    assert!(pts.len() > 100 && b > 0.0);
}

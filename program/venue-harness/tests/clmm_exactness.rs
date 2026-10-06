//! Exactness of arbx-sizing's Raydium CLMM and Orca Whirlpool quotes against the REAL programs (PLAN-ADDENDUM WP-21,
//! DESIGN.md §6.3), on the WP-21 fixtures (`fixtures/pools-clmm`): every pool in both directions, exact in (~45 sizes
//! from the input reserve's ladder, plus dust) and exact out (~45 outputs), quoted by the crate (`AnyLeg::parse` +
//! `quote`, `quote_exact_out`, over the same leg account list the harness swaps with: `swap_v2` as the engine's
//! builder will lay it out) and swapped by the dumped program in LiteSVM. Verdicts as `tests/exactness.rs`:
//!   * `Ok(q)` <=> the swap succeeds with output delta == q.out and input debit == q.spent, AND the pool's post-state
//!     equals the crate's prediction (sqrt price, current tick, liquidity, the fee token's fee growth and protocol /
//!     fund fees owed, the dynamic fee's / adaptive fee's variables): a difference in any is a MISMATCH;
//!   * `TooLarge`/`ZeroOut` <=> the swap fails or delivers 0;
//!   * a refusal (`Abort` at parse or quote) is checked against the venue (both refuse, necessary refusal by the lift,
//!     else FALSE REFUSAL: a failure).
//! Byte-mutated cases: Raydium `fee_on` 1 and 2 (the fee on token 0 / token 1 only), the dynamic fee cleared, and a
//! dynamic fee written into a pool without one; Orca the oracle's volatility state reset. More states and boundary
//! sizes: `tests/clmm_adversarial.rs`. Results: results/clmm-exactness.json (gitignored).
//!
//!   VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release --test clmm_exactness -- --nocapture
mod common;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::Path;
use venue_harness::keys;
use venue_harness::*;

use common::clmm::{crate_post, kind_of, leg_accounts, n_arrays, swap_with_post};
use common::{lift, refusal_verdict, VenueAt, MANIFEST_DIR};

fn skip(msg: &str) {
    if common::required() { panic!("{msg}"); }
    println!("SKIP clmm_exactness: {msg}");
}

#[derive(Default, serde::Serialize)]
struct Tally { exact: usize, post_exact: usize, too_large_agree: usize, budget: usize, cu_limit: usize, aborted: usize, refused_venue_fails: usize,
    necessary_refusals: usize, false_refusals: usize, mismatches: usize, abort_reasons: BTreeMap<String, usize> }

struct Case { label: String, h: Harness }

fn i32_at(d: &[u8], o: usize) -> i32 { i32::from_le_bytes(d[o..o + 4].try_into().unwrap()) }

fn cases(fx: &Fixtures) -> Vec<Case> {
    let mut out = vec![];
    for p in fx.pools.values() {
        let pool = p.pool_key();
        let h0 = Harness::new(fx, &pool).unwrap();
        let d = h0.view[&pool].data.clone();
        let mut variants = vec![];
        let mut m = |label: &str, patches: Vec<Patch>| match Harness::with_patches(fx, &pool, &patches) {
            Ok(h) => variants.push(Case { label: label.into(), h }),
            Err(e) => panic!("{} {label}: {e}", p.pool),
        };
        match p.venue {
            Venue::RayClmm => {
                let fee_on = d[390];
                for f in [0u8, 1, 2] { if f != fee_on { m(&format!("fee_on={f}"), vec![Patch::new(pool, 390, &[f])]); } }
                let dynamic = d[1096..1176].iter().any(|b| *b != 0);
                if dynamic {
                    m("dynamic fee cleared", vec![Patch::new(pool, 1096, &[0u8; 80])]);
                } else {
                    // filter 10 s, decay 60 s, reduction 5000, control 20000, max_va 200000, the reference at the current tick
                    let ts = u16::from_le_bytes([d[235], d[236]]) as i32;
                    let idx = i32_at(&d, 269).div_euclid(ts);
                    let mut b = vec![];
                    b.extend(10u16.to_le_bytes()); b.extend(60u16.to_le_bytes()); b.extend(5_000u16.to_le_bytes());
                    b.extend(20_000u32.to_le_bytes()); b.extend(200_000u32.to_le_bytes()); b.extend(idx.to_le_bytes());
                    b.extend(30_000u32.to_le_bytes()); b.extend(40_000u32.to_le_bytes()); b.extend((p.clock.unix_timestamp as u64 - 5).to_le_bytes());
                    m("dynamic fee set", vec![Patch::new(pool, 1096, &b)]);
                }
            }
            Venue::Whirlpool => {
                let oracle = keys::whirl_oracle(&pool);
                if h0.view.contains_key(&oracle) {
                    // the volatility state reset (reference, accumulator) and the reference far in the past
                    m("adaptive state reset", vec![Patch::new(oracle, 82, &[0u8; 28])]);
                }
            }
            _ => {}
        }
        out.push(Case { label: "snapshot".into(), h: h0 });
        out.extend(variants);
    }
    out
}

#[test]
fn clmm_quotes_and_post_states_equal_the_real_programs() {
    let sizing = common::sizing_dir();
    if !sizing.join("Cargo.toml").exists() { return skip(&format!("{} has no Cargo.toml", sizing.display())); }
    let bridge = match common::build_bridge(&sizing, "sizing-bridge") {
        Ok(b) => b,
        Err(e) => return skip(&format!("sizing-bridge does not build against arbx-sizing:\n{e}")),
    };
    let fx = Fixtures::load_clmm().unwrap();
    assert!(fx.pools.len() >= 12, "the WP-21 fixtures are missing: run `fetch-fixtures --pools`");
    let opts = BuildOpts::default();
    let opts_out = BuildOpts { exact_out: true, ..Default::default() };
    let cases = cases(&fx);
    let mut legs = vec![];
    let mut meta = vec![];
    for (ci, c) in cases.iter().enumerate() {
        let (h, p) = (&c.h, &c.h.fixture);
        for dir in Dir::BOTH {
            for exact_out in [false, true] {
                let o = if exact_out { &opts_out } else { &opts };
                let sw = h.build(dir, 1, o).unwrap();
                let mut amounts: Vec<u64> = if exact_out { size_ladder(h.output_reserve(dir), 40).into_iter().chain([1, 2, 10, 100, 1_000]).collect() }
                    else { size_ladder(h.input_reserve(dir), 40).into_iter().chain([1, 2, 10, 100, 1_000]).collect() };
                // a dense run of consecutive sizes covers the fee-rounding residues of the snapshot
                if c.label == "snapshot" && !exact_out { amounts.extend(1_000_000..1_000_200); }
                amounts.sort();
                amounts.dedup();
                legs.push(json!({"id": legs.len(), "kind": kind_of(p.venue), "base_or_token0_in": dir.zfo(), "n_bin_arrays": n_arrays(p.venue, &sw),
                    "pump_bump": 0, "program": p.venue.program().to_string(), "input_mint": sw.mint_in.to_string(),
                    "accounts": leg_accounts(h, &sw), "amounts": amounts, "clock": p.clock, "exact_out": exact_out}));
                meta.push((ci, dir, exact_out));
            }
        }
    }
    let resp = common::quote_legs(&bridge, &legs);
    let mut tally: BTreeMap<String, Tally> = BTreeMap::new();
    let mut problems = vec![];
    let mut rows = vec![];
    let mut swapped_refusals: BTreeMap<usize, Vec<(usize, VenueAt)>> = BTreeMap::new();
    let mut cu: BTreeMap<String, Vec<(u64, u64)>> = BTreeMap::new();
    for (i, r) in resp.iter().enumerate() {
        let (ci, dir, exact_out) = meta[i];
        let c = &cases[ci];
        let (h, p) = (&c.h, &c.h.fixture);
        let key = tally_key(p, &c.label, exact_out);
        let o = if exact_out { &opts_out } else { &opts };
        let t = tally.entry(key).or_default();
        let parse = r["parse"].as_str().unwrap_or("missing").to_string();
        if parse.starts_with("desc:") { problems.push(format!("{} {} {} [{}]: DescError on a harness-built leg: {parse}", p.venue.name(), p.pool, dir.short(), c.label)); }
        for q in r["quotes"].as_array().unwrap() {
            let x = q["amount"].as_u64().unwrap();
            let err = q["err"].as_str().unwrap_or("");
            let (s, post) = swap_with_post(h, dir, x, o, None);
            if !q["ok"].as_bool().unwrap() && (parse != "ok" || err.starts_with("Abort")) {
                t.aborted += 1;
                let reason = if parse != "ok" { parse.clone() } else { err.to_string() };
                *t.abort_reasons.entry(reason.clone()).or_default() += 1;
                let v = VenueAt { ok: s.ok, out: s.amount_out, spent: s.spent };
                let verdict = if v.swapped() {
                    swapped_refusals.entry(i).or_default().push((rows.len(), v));
                    format!("refused ({reason}) while the venue swaps: pending the lift check")
                } else { t.refused_venue_fails += 1; format!("both refuse ({reason}; venue {})", if s.ok { "pays 0".into() } else { s.venue_error() }) };
                rows.push(json!({"venue": p.venue.name(), "pool": p.pool, "case": c.label, "dir": dir.short(), "exact_out": exact_out, "amount": x,
                    "quote": q, "program_ok": s.ok, "program_out": s.amount_out, "program_spent": s.spent, "cu": s.cu_venue, "verdict": verdict}));
                continue;
            }
            let mut verdict = if q["ok"].as_bool().unwrap() {
                let (qo, qs) = (q["out"].as_u64().unwrap(), q["spent"].as_u64().unwrap());
                if s.ok && s.amount_out == qo && s.spent == qs {
                    let cp = crate_post(q);
                    match &post {
                        Some(vp) if *vp == cp => { t.post_exact += 1; "exact".to_string() }
                        Some(vp) => format!("MISMATCH post-state: crate {cp} vs program {vp}"),
                        None => "MISMATCH no post-state".to_string(),
                    }
                } else {
                    format!("MISMATCH quote out {qo} spent {qs} vs program {} out {} spent {} {}", if s.ok { "ok" } else { "FAILED" }, s.amount_out, s.spent,
                        if s.ok { String::new() } else { s.venue_error() })
                }
            } else if s.failed_or_zero() { format!("both refuse ({err})") } else {
                format!("MISMATCH quote {err} vs program out {} spent {} (cu {:?})", s.amount_out, s.spent, s.cu_venue)
            };
            if !s.ok && (s.logs.iter().any(|l| l.contains("exceeded CUs meter") || l.contains("Computational budget exceeded"))
                || s.err.as_deref().is_some_and(|e| e.contains("ComputationalBudgetExceeded"))) {
                verdict = format!("venue CU limit (quote {})", if q["ok"].as_bool().unwrap() { "ok" } else { err });
            }
            if verdict.starts_with("MISMATCH") { t.mismatches += 1; } else if verdict.starts_with("venue CU limit") { t.cu_limit += 1; }
                else if verdict == "exact" { t.exact += 1; } else { t.too_large_agree += 1; }
            if verdict.starts_with("MISMATCH") && problems.len() < 60 { problems.push(format!("{} {} {} [{}] {} x={x}: {verdict}", p.venue.name(), p.pool, dir.short(), c.label,
                if exact_out { "exact-out" } else { "exact-in" })); }
            if s.ok && !exact_out && c.label == "snapshot" {
                if let Some(cv) = s.cu_venue { cu.entry(format!("{} {}", p.venue.name(), &p.pool[..8])).or_default().push((q["clmm"]["crossed"].as_u64().unwrap_or(0), cv)); }
            }
            rows.push(json!({"venue": p.venue.name(), "pool": p.pool, "case": c.label, "dir": dir.short(), "exact_out": exact_out, "amount": x, "quote": q,
                "program_ok": s.ok, "program_out": s.amount_out, "program_spent": s.spent, "cu": s.cu_venue, "post": post, "verdict": verdict}));
        }
    }
    // the lift check: a refused leg re-quoted with the refused state taken out on the crate's side only
    let lifted_legs: Vec<(usize, Value)> = swapped_refusals.keys().filter_map(|&i| {
        let parse = resp[i]["parse"].as_str().unwrap_or("");
        let accounts = lift(parse, legs[i]["accounts"].as_array().unwrap())?;
        let mut l = legs[i].clone();
        l["accounts"] = json!(accounts);
        l["amounts"] = json!(swapped_refusals[&i].iter().map(|(ri, _)| rows[*ri]["amount"].clone()).collect::<Vec<_>>());
        Some((i, l))
    }).collect();
    let relegs: Vec<Value> = lifted_legs.iter().enumerate().map(|(k, (_, l))| { let mut l = l.clone(); l["id"] = json!(k); l }).collect();
    let relifted = if relegs.is_empty() { vec![] } else { common::quote_legs(&bridge, &relegs) };
    for (i, refused) in &swapped_refusals {
        let (ci, dir, exact_out) = meta[*i];
        let c = &cases[ci];
        let p = &c.h.fixture;
        let lq = lifted_legs.iter().position(|(j, _)| j == i).map(|k| relifted[k]["quotes"].as_array().unwrap().as_slice());
        let venue: Vec<VenueAt> = refused.iter().map(|(_, v)| v.clone()).collect();
        let (verdict, why) = refusal_verdict(&venue, lq);
        let t = tally.get_mut(&tally_key(p, &c.label, exact_out)).unwrap();
        for (ri, _) in refused {
            rows[*ri]["verdict"] = json!(format!("{verdict} ({}): {why}", resp[*i]["parse"].as_str().unwrap_or("")));
            if verdict == "necessary refusal" { t.necessary_refusals += 1; } else { t.false_refusals += 1; }
        }
        if verdict != "necessary refusal" && problems.len() < 60 {
            problems.push(format!("{} {} {} [{}]: FALSE REFUSAL {} at {} venue-swapped sizes: {why}", p.venue.name(), p.pool, dir.short(), c.label, resp[*i]["parse"], refused.len()));
        }
    }
    print_tally("clmm exactness", &tally);
    // the venue's CU against the initialized ticks the swap crosses (the engine's CU table input)
    println!("venue CU by pool (exact in, snapshot): crossed ticks -> CU min/max");
    for (k, v) in &cu {
        let mut by: BTreeMap<u64, (u64, u64)> = BTreeMap::new();
        for (x, c) in v { let e = by.entry(*x).or_insert((u64::MAX, 0)); e.0 = e.0.min(*c); e.1 = e.1.max(*c); }
        println!("  {k}: {}", by.iter().map(|(x, (a, b))| format!("{x}:{a}-{b}")).collect::<Vec<_>>().join(" "));
    }
    let out = Path::new(MANIFEST_DIR).join("results");
    std::fs::create_dir_all(&out).unwrap();
    std::fs::write(out.join("clmm-exactness.json"), serde_json::to_string_pretty(&json!({"tally": tally, "rows": rows})).unwrap()).unwrap();
    assert!(problems.is_empty(), "{} problems:\n{}", problems.len(), problems.join("\n"));
}

fn print_tally(name: &str, tally: &BTreeMap<String, Tally>) {
    println!("{name}");
    println!("{:<52} {:>6} {:>6} {:>11} {:>7} {:>8} {:>9} {:>9} {:>9}  abort reasons", "venue [case] side", "exact", "post", "both-refuse", "cu-lim",
        "refused", "necessary", "FALSE-REF", "MISMATCH");
    for (v, t) in tally {
        println!("{v:<52} {:>6} {:>6} {:>11} {:>7} {:>8} {:>9} {:>9} {:>9}  {:?}", t.exact, t.post_exact, t.too_large_agree + t.refused_venue_fails, t.cu_limit,
            t.aborted, t.necessary_refusals, t.false_refusals, t.mismatches, t.abort_reasons);
    }
    let sum = |f: fn(&Tally) -> usize| tally.values().map(f).sum::<usize>();
    println!("{:<52} {:>6} {:>6} {:>11} {:>7} {:>8} {:>9} {:>9} {:>9}", "TOTAL", sum(|t| t.exact), sum(|t| t.post_exact), sum(|t| t.too_large_agree + t.refused_venue_fails),
        sum(|t| t.cu_limit), sum(|t| t.aborted), sum(|t| t.necessary_refusals), sum(|t| t.false_refusals), sum(|t| t.mismatches));
}

fn tally_key(p: &PoolFixture, label: &str, exact_out: bool) -> String {
    let side = if exact_out { "exact-out" } else { "exact-in" };
    if label == "snapshot" { format!("{} {side}", p.venue.name()) } else { format!("{} [{label}] {side}", p.venue.name()) }
}

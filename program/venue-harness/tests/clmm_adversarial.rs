//! Adversarial exactness of arbx-sizing's Raydium CLMM and Orca Whirlpool quotes (PLAN-ADDENDUM WP-21). Same oracle and
//! verdicts as `tests/clmm_exactness.rs` (quote AND post-state against the dumped programs; every refusal checked against
//! the venue), on the states and sizes the snapshot ladder misses:
//!
//! * boundary sizes the crate itself computes (bridge probe mode): the cumulative input at the end of each swap step of
//!   an unbounded swap (tick crossings, tick-spacing / tick-group boundaries, limit-order fills), the exact capacity
//!   (`cap_in`), and fee-ceil residues, each ±1, ±2;
//! * Clock variations: the pool's open time (Raydium), the dynamic / adaptive fee's filter and decay periods and the
//!   adaptive reference's maximum age, a Clock before the last reward or reference update (Orca);
//! * Raydium CLMM states: trade fee 0, 1 and 10%, protocol and fund fee rates, the dynamic fee at its maximum
//!   accumulator and with a large control (the 10% cap), limit orders injected on the ticks around the price (fresh and
//!   part-filled, on ticks with liquidity and on a limit-order-only tick), swaps disabled (status bit 4), other status
//!   bits, a paused Token-2022 mint, the pool's liquidity cut to 0;
//! * Raydium CLMM tick-array lists: only the first array (the capacity at its end), the walk order reversed, an
//!   unrelated array first, the first needed array missing, the bitmap extension left out (needed and not);
//! * Orca Whirlpool states: fee rate 0 and 6.5% (the static maximum), protocol fee rate 0 and 25%, the adaptive fee at
//!   its maximum accumulator, with control 0, its reference far from the price (outside the core range), trading not
//!   enabled yet, the pool's liquidity cut to 0;
//! * Orca Whirlpool tick-array lists: the 3 static slots all the current array (the sequence ends there), the needed
//!   arrays passed only as supplemental ones, the current array missing.
//!
//! Fails on any MISMATCH (amounts or post-state) or FALSE REFUSAL. Results: results/clmm-adversarial.json (gitignored).
//!
//!   VENUE_HARNESS_REQUIRE_SIZING=1 cargo test --release --test clmm_adversarial -- --nocapture
mod common;
use common::clmm as ex;
use serde_json::{json, Value};
use std::collections::BTreeMap;
use std::path::Path;
use common::{lift, refusal_verdict, VenueAt, MANIFEST_DIR};
use venue_harness::fixture::ClockSnap;
use venue_harness::keys;
use venue_harness::*;

fn skip(msg: &str) {
    if common::required() { panic!("{msg}"); }
    println!("SKIP clmm_adversarial: {msg}");
}

struct Probe { label: String, h: Harness, clock: ClockSnap, opts: BuildOpts, probe: bool, dirs: Vec<Dir>, exact_out: bool }

fn u16_at(d: &[u8], o: usize) -> u16 { u16::from_le_bytes(d[o..o + 2].try_into().unwrap()) }
fn u32_at(d: &[u8], o: usize) -> u32 { u32::from_le_bytes(d[o..o + 4].try_into().unwrap()) }
fn i32_at(d: &[u8], o: usize) -> i32 { i32::from_le_bytes(d[o..o + 4].try_into().unwrap()) }
fn u64_at(d: &[u8], o: usize) -> u64 { u64::from_le_bytes(d[o..o + 8].try_into().unwrap()) }

/// Raydium CLMM: the (key, tick offset) of the initialized ticks of the pool's held tick arrays, nearest the price
/// first (`below`: under the current tick)
fn ray_ticks(h: &Harness, below: bool, n: usize) -> Vec<(solana_address::Address, usize, i32)> {
    let d = &h.view[&h.pool].data;
    let tick = i32_at(d, 269);
    let mut v = vec![];
    for (k, a) in &h.view {
        if a.owner != keys::RAYCLMM || a.data.len() != 10_240 || a.data[8..40] != h.pool.as_ref()[..] { continue; }
        for slot in 0..60 {
            let o = 44 + 168 * slot;
            let gross = u128::from_le_bytes(a.data[o + 20..o + 36].try_into().unwrap());
            let t = i32_at(&a.data, o);
            if gross > 0 && ((below && t <= tick) || (!below && t > tick)) { v.push((*k, slot, t)); }
        }
    }
    v.sort_by_key(|x| (x.2 - tick).abs());
    v.truncate(n);
    v
}

/// limit orders on ticks: `orders` fresh, `part` part-filled with half the cohort left (unfilled ratio 1/2)
fn ray_orders(ticks: &[(solana_address::Address, usize, i32)], orders: u64, part: u64) -> Vec<Patch> {
    let mut p = vec![];
    for (k, slot, _) in ticks {
        let o = 44 + 168 * slot;
        p.push(Patch::new(*k, o + 116, &1u64.to_le_bytes()));
        p.push(Patch::new(*k, o + 124, &orders.to_le_bytes()));
        p.push(Patch::new(*k, o + 132, &part.to_le_bytes()));
        p.push(Patch::new(*k, o + 140, &(if part > 0 { 1u128 << 63 } else { 0 }).to_le_bytes()));
    }
    p
}

fn probes(fx: &Fixtures, p: &PoolFixture) -> Vec<Probe> {
    let mut out = vec![];
    let pool = p.pool_key();
    let h0 = Harness::new(fx, &pool).unwrap();
    let d = h0.view[&pool].data.clone();
    let snap = p.clock;
    let both = Dir::BOTH.to_vec();
    let base = BuildOpts::default();
    let mut add = |label: String, patches: Vec<Patch>, clock: ClockSnap, opts: BuildOpts, probe: bool, dirs: Vec<Dir>, exact_out: bool| {
        match Harness::with_patches(fx, &pool, &patches) {
            Ok(h) => out.push(Probe { label, h, clock, opts, probe, dirs, exact_out }),
            Err(e) => panic!("{} {label}: {e}", p.pool),
        }
    };
    let at = |ts: i64| ClockSnap { unix_timestamp: ts, ..snap };
    add("probe".into(), vec![], snap, base.clone(), true, both.clone(), false);
    add("probe exact-out".into(), vec![], snap, BuildOpts { exact_out: true, ..base.clone() }, false, both.clone(), true);
    match p.venue {
        Venue::RayClmm => {
            let cfg = venues::pk_at(&d, 9).unwrap();
            let ts = u16_at(&d, 235) as i32;
            let dynamic = d[1096..1176].iter().any(|b| *b != 0);
            // the open time: one second before the Clock swaps, at the Clock does not (require_gt)
            add("open_time = now - 1".into(), vec![Patch::new(pool, 1080, &((snap.unix_timestamp - 1) as u64).to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            add("open_time = now".into(), vec![Patch::new(pool, 1080, &(snap.unix_timestamp as u64).to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            // status: bit 4 disables swaps; the other bits do not
            add("status bit 4 (swap disabled)".into(), vec![Patch::new(pool, 389, &[0x10])], snap, base.clone(), false, both.clone(), false);
            add("status bits 0-3, 5".into(), vec![Patch::new(pool, 389, &[0x2F])], snap, base.clone(), false, both.clone(), false);
            // the trade fee (AmmConfig @47), the protocol and fund shares (@43, @53)
            for (fee, label) in [(0u32, "trade fee 0"), (1, "trade fee 1"), (100_000, "trade fee 10%")] {
                add(label.into(), vec![Patch::new(cfg, 47, &fee.to_le_bytes())], snap, base.clone(), true, both.clone(), false);
            }
            add("protocol 0, fund 0".into(), vec![Patch::new(cfg, 43, &0u32.to_le_bytes()), Patch::new(cfg, 53, &0u32.to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            add("protocol 50%, fund 30%".into(), vec![Patch::new(cfg, 43, &500_000u32.to_le_bytes()), Patch::new(cfg, 53, &300_000u32.to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            // the protocol fees owed near u64::MAX: the swap's checked addition fails (update_fee)
            add("protocol fees owed near u64::MAX".into(), vec![Patch::new(pool, 309, &(u64::MAX - 1_000).to_le_bytes()), Patch::new(pool, 317, &(u64::MAX - 1_000).to_le_bytes())],
                snap, base.clone(), false, both.clone(), false);
            // the dynamic fee: Clock edges, the accumulator at its maximum, a large control (the 10% cap)
            if dynamic {
                let (filter, decay, last) = (u16_at(&d, 1096) as i64, u16_at(&d, 1098) as i64, u64_at(&d, 1122) as i64);
                for dt in [0, filter - 1, filter, decay - 1, decay, 10 * decay] {
                    add(format!("dynamic fee clock last+{dt}"), vec![], at(last.max(snap.unix_timestamp - 100_000) + dt), base.clone(), false, both.clone(), false);
                }
                let max_va = u32_at(&d, 1106);
                add("va = v_ref = max_va".into(), vec![Patch::new(pool, 1114, &max_va.to_le_bytes()), Patch::new(pool, 1118, &max_va.to_le_bytes()),
                    Patch::new(pool, 1122, &(snap.unix_timestamp as u64).to_le_bytes())], snap, base.clone(), true, both.clone(), false);
                add("dynamic fee control 99999 (the 10% cap)".into(), vec![Patch::new(pool, 1102, &99_999u32.to_le_bytes()),
                    Patch::new(pool, 1114, &(max_va / 2).to_le_bytes()), Patch::new(pool, 1122, &(snap.unix_timestamp as u64).to_le_bytes())], snap, base.clone(), true, both.clone(), false);
                add("reference 40 groups away".into(), vec![Patch::new(pool, 1110, &(i32_at(&d, 269).div_euclid(ts) + 40).to_le_bytes()),
                    Patch::new(pool, 1122, &(snap.unix_timestamp as u64).to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            }
            // limit orders around the price: fresh orders, a part-filled cohort, on ticks with liquidity
            let below = ray_ticks(&h0, true, 3);
            let above = ray_ticks(&h0, false, 3);
            if !below.is_empty() || !above.is_empty() {
                let all: Vec<_> = below.iter().chain(above.iter()).cloned().collect();
                add("limit orders (fresh) on 6 ticks".into(), ray_orders(&all, 1_000_000_000, 0), snap, base.clone(), true, both.clone(), false);
                add("limit orders (part-filled) on 6 ticks".into(), ray_orders(&all, 0, 700_000_000), snap, base.clone(), true, both.clone(), false);
                add("limit orders (both cohorts), exact out".into(), ray_orders(&all, 300_000_000, 400_000_000), snap, BuildOpts { exact_out: true, ..base.clone() }, false, both.clone(), true);
                add("limit orders, tiny".into(), ray_orders(&all, 7, 3), snap, base.clone(), true, both.clone(), false);
            }
            // the pool's in-range liquidity cut to 0
            add("liquidity = 0".into(), vec![Patch::new(pool, 237, &0u128.to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            // Token-2022 mints: a transfer fee, paused, default-frozen accounts (refused; checked against the venue)
            for m in [venues::pk_at(&d, 73).unwrap(), venues::pk_at(&d, 105).unwrap()] {
                for (label, patches) in t22_states(&h0, &m) { add(label, patches, snap, base.clone(), false, both.clone(), false); }
            }
            // tick-array lists
            for dir in Dir::BOTH {
                let sw = h0.build(dir, 1, &base).unwrap();
                let arrays = sw.tick_arrays.clone();
                let dirs = vec![dir];
                if arrays.len() >= 2 {
                    add(format!("only the first tick array {}", dir.short()), vec![], snap, BuildOpts { tick_arrays: Some(vec![arrays[0]]), ..base.clone() }, true, dirs.clone(), false);
                    let mut rev = arrays.clone();
                    rev.reverse();
                    add(format!("tick arrays reversed {}", dir.short()), vec![], snap, BuildOpts { tick_arrays: Some(rev), ..base.clone() }, false, dirs.clone(), false);
                    add(format!("first needed tick array missing {}", dir.short()), vec![], snap, BuildOpts { tick_arrays: Some(arrays[1..].to_vec()), ..base.clone() }, false, dirs.clone(), false);
                    let other = if dir.zfo() { arrays.iter().max() } else { arrays.iter().min() };
                    let first = 60 * ts * if dir.zfo() { 1 } else { -1 } + arrays[0];
                    let mut extra = vec![first];
                    extra.extend(&arrays);
                    let _ = other;
                    add(format!("an unrelated tick array first {}", dir.short()), vec![], snap, BuildOpts { tick_arrays: Some(extra), ..base.clone() }, false, dirs.clone(), false);
                }
                add(format!("no bitmap extension {}", dir.short()), vec![], snap, BuildOpts { clmm_ext: false, ..base.clone() }, true, dirs.clone(), false);
            }
        }
        Venue::Whirlpool => {
            let oracle = keys::whirl_oracle(&pool);
            let ts = u16_at(&d, 41) as i32;
            // the static fee (u16 @45), the protocol fee rate (@47)
            for (fee, label) in [(0u16, "fee rate 0"), (65_000, "fee rate 6.5%")] {
                add(label.into(), vec![Patch::new(pool, 45, &fee.to_le_bytes())], snap, base.clone(), true, both.clone(), false);
            }
            add("protocol fee rate 0".into(), vec![Patch::new(pool, 47, &0u16.to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            add("protocol fee rate 25%".into(), vec![Patch::new(pool, 47, &2_500u16.to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            // the Clock before the last reward update fails (InvalidTimestamp)
            add("reward updated in the future".into(), vec![Patch::new(pool, 261, &((snap.unix_timestamp + 10) as u64).to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            add("pool liquidity = 0".into(), vec![Patch::new(pool, 49, &0u128.to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            if let Some(o) = h0.view.get(&oracle).map(|a| a.data.clone()) {
                let (filter, decay) = (u16_at(&o, 48) as i64, u16_at(&o, 50) as i64);
                let (last_ref, last_major) = (u64_at(&o, 82) as i64, u64_at(&o, 90) as i64);
                let base_ts = last_ref.max(last_major).max(snap.unix_timestamp - 100_000);
                for dt in [0, filter - 1, filter, decay - 1, decay, 3_600, 3_601, 10 * decay] {
                    add(format!("adaptive clock max_ts+{dt}"), vec![], at(base_ts + dt), base.clone(), false, both.clone(), false);
                }
                add("clock before the reference update".into(), vec![Patch::new(oracle, 82, &((snap.unix_timestamp + 5) as u64).to_le_bytes())], snap, base.clone(), false, both.clone(), false);
                let max_va = u32_at(&o, 58);
                add("adaptive va = v_ref = max".into(), vec![Patch::new(oracle, 98, &max_va.to_le_bytes()), Patch::new(oracle, 106, &max_va.to_le_bytes()),
                    Patch::new(oracle, 82, &(snap.unix_timestamp as u64).to_le_bytes())], snap, base.clone(), true, both.clone(), false);
                add("adaptive control 0".into(), vec![Patch::new(oracle, 54, &0u32.to_le_bytes())], snap, base.clone(), true, both.clone(), false);
                add("adaptive control 99999".into(), vec![Patch::new(oracle, 54, &99_999u32.to_le_bytes()), Patch::new(oracle, 82, &(snap.unix_timestamp as u64).to_le_bytes())],
                    snap, base.clone(), true, both.clone(), false);
                let tgs = u16_at(&o, 62).max(1) as i32;
                add("adaptive reference 100 groups below".into(), vec![Patch::new(oracle, 102, &(i32_at(&d, 81).div_euclid(tgs) - 100).to_le_bytes()),
                    Patch::new(oracle, 82, &(snap.unix_timestamp as u64).to_le_bytes())], snap, base.clone(), false, both.clone(), false);
                add("adaptive reference 100 groups above".into(), vec![Patch::new(oracle, 102, &(i32_at(&d, 81).div_euclid(tgs) + 100).to_le_bytes()),
                    Patch::new(oracle, 82, &(snap.unix_timestamp as u64).to_le_bytes())], snap, base.clone(), false, both.clone(), false);
                add("trading not enabled yet".into(), vec![Patch::new(oracle, 40, &((snap.unix_timestamp + 60) as u64).to_le_bytes())], snap, base.clone(), false, both.clone(), false);
            }
            // Token-2022 mints: a transfer fee, paused, default-frozen accounts (refused; checked against the venue)
            for m in [venues::pk_at(&d, 101).unwrap(), venues::pk_at(&d, 181).unwrap()] {
                for (label, patches) in t22_states(&h0, &m) { add(label, patches, snap, base.clone(), false, both.clone(), false); }
            }
            for dir in Dir::BOTH {
                let need = venues::whirl_arrays_for_swap(&d, dir.zfo());
                let dirs = vec![dir];
                if need.is_empty() { continue; }
                add(format!("only the current tick array {}", dir.short()), vec![], snap, BuildOpts { tick_arrays: Some(vec![need[0]]), ..base.clone() }, true, dirs.clone(), false);
                // the needed arrays only as supplemental ones, the static slots far away
                let far = need[0] + 88 * ts * if dir.zfo() { 20 } else { -20 };
                let mut supp = vec![far, far, far];
                supp.extend(&need);
                add(format!("needed arrays as supplemental {}", dir.short()), vec![], snap, BuildOpts { tick_arrays: Some(supp), ..base.clone() }, false, dirs.clone(), false);
                if need.len() >= 2 {
                    add(format!("current tick array missing {}", dir.short()), vec![], snap, BuildOpts { tick_arrays: Some(need[1..].to_vec()), ..base.clone() }, false, dirs.clone(), false);
                }
            }
        }
        _ => {}
    }
    out
}

/// a Token-2022 mint's extension `t` (TLV after the account type byte at 165): (value offset, length)
fn tlv(d: &[u8], t: u16) -> Option<(usize, usize)> {
    if d.len() <= 166 || d[165] != 1 { return None; }
    let mut o = 166;
    while o + 4 <= d.len() {
        let (tt, l) = (u16::from_le_bytes([d[o], d[o + 1]]), u16::from_le_bytes([d[o + 2], d[o + 3]]) as usize);
        if tt == 0 { return None; }
        if tt == t { return Some((o + 4, l)); }
        o += 4 + l;
    }
    None
}

/// the Token-2022 states of mint `m` to check against the venue: its transfer fee set to 1% (where it has a
/// TransferFeeConfig: a necessary refusal by the lift), paused (the Pausable flag set, or the extension appended) and
/// DefaultAccountState Frozen (set, or appended: the harness's new token account is then frozen). Nothing for an SPL mint
fn t22_states(h: &Harness, m: &solana_address::Address) -> Vec<(String, Vec<Patch>)> {
    let Some(a) = h.view.get(m) else { return vec![] };
    let d = &a.data;
    if a.owner != keys::TOKEN_2022 || d.len() <= 166 || d[165] != 1 { return vec![]; }
    let mut out = vec![];
    let append = |t: u16, v: &[u8]| { let mut b = t.to_le_bytes().to_vec(); b.extend((v.len() as u16).to_le_bytes()); b.extend(v); vec![Patch::resize(*m, d.len() + b.len()), Patch::new(*m, d.len(), &b)] };
    // TransferFeeConfig value: authorities 32 + 32, withheld u64 at 64, older {epoch u64 72, maximum_fee u64 80,
    // bps u16 88}, newer {epoch 90, maximum_fee 98, bps 106}. Token-2022 caps the fee at maximum_fee, so both caps are
    // lifted too (a mint whose maximum_fee is 0 charges nothing whatever its bps: the crate's shared extension scan
    // refuses any bps > 0, a conservative refusal: DESIGN.md §7 item 10)
    if let Some((o, _)) = tlv(d, 1) {
        let (bps, max) = (100u16.to_le_bytes(), u64::MAX.to_le_bytes());
        out.push(("mint transfer fee 1%".to_string(), vec![
            Patch::new(*m, o + 80, &max), Patch::new(*m, o + 88, &bps), Patch::new(*m, o + 98, &max), Patch::new(*m, o + 106, &bps),
        ]));
    }
    match tlv(d, 26) {
        Some((o, _)) => out.push(("mint paused".to_string(), vec![Patch::new(*m, o + 32, &[1])])),
        None => { let mut v = vec![0u8; 32]; v.push(1); out.push(("mint paused (extension appended)".to_string(), append(26, &v))); }
    }
    match tlv(d, 6) {
        Some((o, _)) => out.push(("mint default state frozen".to_string(), vec![Patch::new(*m, o, &[2])])),
        None => out.push(("mint default state frozen (extension appended)".to_string(), append(6, &[2]))),
    }
    out
}

#[derive(Default, serde::Serialize)]
struct Tally { exact: usize, both_refuse: usize, cu_limit: usize, aborted: usize, necessary: usize, false_refusals: usize, mismatches: usize }

#[test]
fn clmm_adversarial_states_and_boundary_sizes() {
    let sizing = common::sizing_dir();
    if !sizing.join("Cargo.toml").exists() { return skip("arbx-sizing is not there"); }
    let bridge = match common::build_bridge(&sizing, "sizing-bridge") { Ok(b) => b, Err(e) => return skip(&format!("sizing-bridge does not build:\n{e}")) };
    let fx = Fixtures::load_clmm().unwrap();
    let mut tally: BTreeMap<String, Tally> = BTreeMap::new();
    let mut problems = vec![];
    let mut rows = vec![];
    for pool in fx.pools.values() {
        let probes = probes(&fx, pool);
        let mut legs = vec![];
        let mut meta = vec![];
        for (pi, pr) in probes.iter().enumerate() {
            let (h, p) = (&pr.h, &pr.h.fixture);
            for &dir in &pr.dirs {
                let Ok(sw) = h.build(dir, 1, &pr.opts) else { continue };
                if p.venue == Venue::RayClmm && sw.ix.accounts.len() - 13 > 7 { continue; }
                if p.venue == Venue::Whirlpool && sw.ix.accounts.len() - 15 > 3 { continue; }
                let reserve = if pr.exact_out { h.output_reserve(dir) } else { h.input_reserve(dir) };
                let mut amounts: Vec<u64> = size_ladder(reserve.max(1_000_000), 24).into_iter().chain([1, 2, 10, 100, 1_000]).collect();
                amounts.sort();
                amounts.dedup();
                legs.push(json!({"id": legs.len(), "kind": ex::kind_of(p.venue), "base_or_token0_in": dir.zfo(), "n_bin_arrays": ex::n_arrays(p.venue, &sw),
                    "pump_bump": 0, "program": p.venue.program().to_string(), "input_mint": sw.mint_in.to_string(),
                    "accounts": ex::leg_accounts(h, &sw), "amounts": amounts, "probe": pr.probe, "exact_out": pr.exact_out,
                    "clock": {"slot": pr.clock.slot, "unix_timestamp": pr.clock.unix_timestamp, "epoch": pr.clock.epoch}}));
                meta.push((pi, dir));
            }
        }
        if legs.is_empty() { continue; }
        let resp = common::quote_legs(&bridge, &legs);
        let mut swapped_refusals: BTreeMap<usize, Vec<(usize, VenueAt)>> = BTreeMap::new();
        for (i, r) in resp.iter().enumerate() {
            let (pi, dir) = meta[i];
            let pr = &probes[pi];
            let (h, p) = (&pr.h, &pr.h.fixture);
            let key = format!("{} {} [{}]", p.venue.name(), &p.pool[..6], pr.label);
            let t = tally.entry(key.clone()).or_default();
            let parse = r["parse"].as_str().unwrap_or("missing").to_string();
            if parse.starts_with("desc:") { problems.push(format!("{key} {}: DescError on a harness-built leg: {parse}", dir.short())); }
            let clock = pr.clock.to_clock();
            for q in r["quotes"].as_array().unwrap() {
                let x = q["amount"].as_u64().unwrap();
                let err = q["err"].as_str().unwrap_or("");
                // above 2^62 the test wallet's input plus the pool vault overflow u64 in the token program (a harness
                // artifact): such sizes are not compared (as tests/adversarial.rs)
                if x > 1u64 << 62 { continue; }
                let (s, post) = ex::swap_with_post(h, dir, x, &pr.opts, Some(&clock));
                if !q["ok"].as_bool().unwrap() && (parse != "ok" || err.starts_with("Abort")) {
                    t.aborted += 1;
                    let reason = if parse != "ok" { parse.clone() } else { err.to_string() };
                    let v = VenueAt { ok: s.ok, out: s.amount_out, spent: s.spent };
                    let verdict = if v.swapped() {
                        swapped_refusals.entry(i).or_default().push((rows.len(), v));
                        format!("refused ({reason}) while the venue swaps: pending the lift check")
                    } else { t.both_refuse += 1; format!("both refuse ({reason}; venue {})", if s.ok { "pays 0".to_string() } else { s.venue_error() }) };
                    rows.push(json!({"case": key, "dir": dir.short(), "amount": x, "quote": q, "program_ok": s.ok, "program_out": s.amount_out,
                        "program_spent": s.spent, "cu": s.cu_venue, "verdict": verdict}));
                    continue;
                }
                let mut verdict = if q["ok"].as_bool().unwrap() {
                    let (qo, qs) = (q["out"].as_u64().unwrap(), q["spent"].as_u64().unwrap());
                    if s.ok && s.amount_out == qo && s.spent == qs {
                        let cp = ex::crate_post(q);
                        match &post { Some(vp) if *vp == cp => "exact".to_string(), Some(vp) => format!("MISMATCH post-state: crate {cp} vs program {vp}"), None => "MISMATCH no post".into() }
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
                    else if verdict == "exact" { t.exact += 1; } else { t.both_refuse += 1; }
                if verdict.starts_with("MISMATCH") && problems.len() < 60 { problems.push(format!("{key} {} x={x}: {verdict}", dir.short())); }
                rows.push(json!({"case": key, "dir": dir.short(), "amount": x, "quote": q, "program_ok": s.ok, "program_out": s.amount_out,
                    "program_spent": s.spent, "cu": s.cu_venue, "verdict": verdict}));
            }
        }
        // the lift check: a refused leg re-quoted with the refused state taken out on the crate's side only
        let lifted_legs: Vec<(usize, Value)> = swapped_refusals.keys().filter_map(|&i| {
            let parse = resp[i]["parse"].as_str().unwrap_or("");
            let accounts = lift(parse, legs[i]["accounts"].as_array().unwrap())?;
            let mut l = legs[i].clone();
            l["accounts"] = json!(accounts);
            l["probe"] = json!(false);
            l["amounts"] = json!(swapped_refusals[&i].iter().map(|(ri, _)| rows[*ri]["amount"].clone()).collect::<Vec<_>>());
            Some((i, l))
        }).collect();
        let relegs: Vec<Value> = lifted_legs.iter().enumerate().map(|(k, (_, l))| { let mut l = l.clone(); l["id"] = json!(k); l }).collect();
        let relifted = if relegs.is_empty() { vec![] } else { common::quote_legs(&bridge, &relegs) };
        for (i, refused) in &swapped_refusals {
            let (pi, dir) = meta[*i];
            let pr = &probes[pi];
            let key = format!("{} {} [{}]", pr.h.fixture.venue.name(), &pr.h.fixture.pool[..6], pr.label);
            let lq = lifted_legs.iter().position(|(j, _)| j == i).map(|k| relifted[k]["quotes"].as_array().unwrap().as_slice());
            let venue: Vec<VenueAt> = refused.iter().map(|(_, v)| v.clone()).collect();
            let (verdict, why) = refusal_verdict(&venue, lq);
            let t = tally.get_mut(&key).unwrap();
            for (ri, _) in refused {
                rows[*ri]["verdict"] = json!(format!("{verdict} ({}): {why}", resp[*i]["parse"].as_str().unwrap_or("")));
                if verdict == "necessary refusal" { t.necessary += 1; } else { t.false_refusals += 1; }
            }
            if verdict != "necessary refusal" && problems.len() < 60 {
                problems.push(format!("{key} {}: FALSE REFUSAL {} at {} venue-swapped sizes: {why}", dir.short(), resp[*i]["parse"], refused.len()));
            }
        }
    }
    println!("{:<70} {:>6} {:>11} {:>7} {:>8} {:>9} {:>9} {:>9}", "venue pool [state]", "exact", "both-refuse", "cu-lim", "refused", "necessary", "FALSE-REF", "MISMATCH");
    for (k, t) in &tally {
        println!("{k:<70} {:>6} {:>11} {:>7} {:>8} {:>9} {:>9} {:>9}", t.exact, t.both_refuse, t.cu_limit, t.aborted, t.necessary, t.false_refusals, t.mismatches);
    }
    let sum = |f: fn(&Tally) -> usize| tally.values().map(f).sum::<usize>();
    println!("{:<70} {:>6} {:>11} {:>7} {:>8} {:>9} {:>9} {:>9}", "TOTAL", sum(|t| t.exact), sum(|t| t.both_refuse), sum(|t| t.cu_limit), sum(|t| t.aborted),
        sum(|t| t.necessary), sum(|t| t.false_refusals), sum(|t| t.mismatches));
    let mut reasons: BTreeMap<String, usize> = BTreeMap::new();
    for r in &rows {
        let v = r["verdict"].as_str().unwrap();
        if v.starts_with("both refuse (") { *reasons.entry(v.trim_start_matches("both refuse (").split(|c| c == ';' || c == ')').next().unwrap_or("").to_string()).or_default() += 1; }
    }
    println!("refusals and capacities agreed with the venue: {reasons:?}");
    let out = Path::new(MANIFEST_DIR).join("results");
    std::fs::create_dir_all(&out).unwrap();
    std::fs::write(out.join("clmm-adversarial.json"), serde_json::to_string_pretty(&json!({"tally": tally, "rows": rows})).unwrap()).unwrap();
    assert!(problems.is_empty(), "{} problems:\n{}", problems.len(), problems.join("\n"));
}

//! PLAN-ADDENDUM WP-21: host tests of the Raydium CLMM and Orca Whirlpool legs (features `rayclmm`, `whirlpool`). The
//! exactness proof is the venue harness (program/venue-harness tests/clmm_*.rs: the real programs); these check the
//! crate's own invariants on the same in-repo snapshots (program/venue-harness/fixtures/pools-clmm):
//! * the tick maths against each venue's constants and its own inverse;
//! * the wide (512-bit) mul-div against num-bigint;
//! * on every snapshot and direction: quotes monotone in the input, `fills` summing to the quote, the exact-out quote
//!   consistent with the exact-in one, `cap_in` exact where it is finite, the locator's stream ending its steps where
//!   the exact swap does;
//! * the locator over a CLMM ↔ CLMM route against a brute-force grid of exact round trips;
//! * the walk budget: `steps_for(x)` covers `x` with the same quote, one step less is Budget, the stream ends on it;
//! * the refusals (typed aborts) and DescErrors of `AnyLeg::parse`, and the descriptor of kinds 7 and 8;
//! * byte-mutated states: parse, quote, fills and the stream never panic (overflow checks are on in tests).
#![cfg(all(feature = "rayclmm", feature = "whirlpool"))]
mod common;
use arbx_sizing::desc::{Kind, LegDesc};
use arbx_sizing::error::{ClmmWhy, WhirlWhy};
use arbx_sizing::venue::{orca_whirlpool as orca, raydium_clmm as ray};
use arbx_sizing::{layout, AcctRef, AnyLeg, Clock, Fx, LegIn, Parsed, QuoteErr};
use common::*;
use num_bigint::BigUint;
use serde_json::Value;
use std::collections::HashMap;

const FIXTURES: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/../venue-harness/fixtures/pools-clmm");

fn b58d(s: &str) -> Pk {
    const A: &[u8] = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    let mut n = [0u8; 40];
    for c in s.bytes() {
        let mut carry = A.iter().position(|&a| a == c).unwrap() as u32;
        for b in n.iter_mut().rev() { carry += *b as u32 * 58; *b = carry as u8; carry >>= 8; }
    }
    let mut out = [0u8; 32];
    out.copy_from_slice(&n[8..]);
    out
}

struct Fix { venue: String, pool: Pk, clock: Clock, accts: HashMap<Pk, Acct> }

fn fixtures() -> Vec<Fix> {
    let mut files: Vec<_> = std::fs::read_dir(FIXTURES).unwrap().map(|e| e.unwrap().path()).filter(|p| p.extension().is_some_and(|x| x == "json")).collect();
    files.sort();
    files.iter().map(|f| {
        let v: Value = serde_json::from_str(&std::fs::read_to_string(f).unwrap()).unwrap();
        let accts = v["accounts"].as_array().unwrap().iter().map(|a| {
            let key = b58d(a["pubkey"].as_str().unwrap());
            (key, Acct { key, owner: b58d(a["owner"].as_str().unwrap()), data: b64(a["data"].as_str().unwrap()) })
        }).collect();
        let c = &v["clock"];
        Fix { venue: v["venue"].as_str().unwrap().into(), pool: b58d(v["pool"].as_str().unwrap()),
            clock: Clock { slot: c["slot"].as_u64().unwrap(), unix_timestamp: c["unix_timestamp"].as_i64().unwrap(), epoch: c["epoch"].as_u64().unwrap() }, accts }
    }).collect()
}

fn key_at(d: &[u8], o: usize) -> Pk { d[o..o + 32].try_into().unwrap() }
fn i32_at(d: &[u8], o: usize) -> i32 { i32::from_le_bytes(d[o..o + 4].try_into().unwrap()) }
fn u16_at(d: &[u8], o: usize) -> u16 { u16::from_le_bytes(d[o..o + 2].try_into().unwrap()) }
fn absent(key: Pk) -> Acct { Acct { key, owner: [0u8; 32], data: vec![] } }

/// a Raydium CLMM leg's state accounts in the kind's order: pool, config, vaults and mints of the direction, then the
/// bitmap extension and the held tick arrays from the current one in the swap's direction (walk order)
fn ray_state(f: &Fix, zfo: bool) -> Vec<Acct> {
    let p = &f.accts[&f.pool];
    let d = &p.data;
    let (m0, m1, v0, v1) = (key_at(d, 73), key_at(d, 105), key_at(d, 137), key_at(d, 169));
    let (mi, mo, vi, vo) = if zfo { (m0, m1, v0, v1) } else { (m1, m0, v1, v0) };
    let ts = u16_at(d, 235);
    let cur = ray::array_start(i32_at(d, 269), ts);
    let mut arrays: Vec<&Acct> = f.accts.values().filter(|a| a.owner == layout::RAY_CLMM && a.data.len() == ray::ARRAY_LEN && a.data[8..40] == f.pool)
        .filter(|a| { let s = i32_at(&a.data, 40); if zfo { s <= cur } else { s >= cur } }).collect();
    arrays.sort_by_key(|a| { let s = i32_at(&a.data, 40); if zfo { -s } else { s } });
    arrays.truncate(6);
    let ext = f.accts.values().find(|a| a.owner == layout::RAY_CLMM && a.data.len() == ray::EXT_LEN);
    let mut st = vec![p.clone(), f.accts[&key_at(d, 9)].clone(), f.accts[&vi].clone(), f.accts[&vo].clone(), f.accts[&mi].clone(), f.accts[&mo].clone()];
    if let Some(e) = ext { st.push(e.clone()); }
    st.extend(arrays.into_iter().cloned());
    st
}

/// an Orca Whirlpool leg's state accounts: pool, mints, vaults, the 3 tick arrays the swap needs (absent ones as their
/// PDA, uninitialized), the oracle (absent: uninitialized)
fn whirl_state(f: &Fix, a_to_b: bool) -> Vec<Acct> {
    let p = &f.accts[&f.pool];
    let d = &p.data;
    let (ma, mb, va, vb) = (key_at(d, 101), key_at(d, 181), key_at(d, 133), key_at(d, 213));
    let (need, n) = orca::needed_starts(i32_at(d, 81), u16_at(d, 41), a_to_b);
    let pda_of = |st: i32| find_program_address(&[b"tick_array", &f.pool, st.to_string().as_bytes()], &layout::WHIRLPOOL).0;
    let mut arrays: Vec<Acct> = need[..n].iter().map(|&st| {
        let k = pda_of(st);
        f.accts.get(&k).cloned().unwrap_or_else(|| absent(k))
    }).collect();
    while arrays.len() < 3 { arrays.push(arrays.last().unwrap().clone()); }
    let ok = find_program_address(&[b"oracle", &f.pool], &layout::WHIRLPOOL).0;
    let mut st = vec![p.clone(), f.accts[&ma].clone(), f.accts[&mb].clone(), f.accts[&va].clone(), f.accts[&vb].clone()];
    st.extend(arrays);
    st.push(f.accts.get(&ok).cloned().unwrap_or_else(|| absent(ok)));
    st
}

struct Leg { desc: LegDesc, state: Vec<Acct>, input: Pk }

fn leg_of(f: &Fix, zfo: bool) -> Leg {
    if f.venue == "RayCLMM" {
        let state = ray_state(f, zfo);
        let mut desc = LegDesc::new(Kind::RayClmm, zfo);
        desc.n_bin_arrays = (state.len() - 6) as u8;
        desc.max_bins = 255;
        let input = state[4].key;
        Leg { desc, state, input }
    } else {
        let state = whirl_state(f, zfo);
        let mut desc = LegDesc::new(Kind::Whirlpool, zfo);
        desc.max_bins = 255;
        let input = if zfo { state[1].key } else { state[2].key };
        Leg { desc, state, input }
    }
}

fn parse_leg<'a>(l: &'a Leg, refs: &'a [AcctRef<'a>], clock: &Clock) -> Result<Parsed<'a>, arbx_sizing::DescError> {
    let li = LegIn { desc: l.desc, program: l.desc.kind.program(), state: refs, input_mint: &l.input };
    AnyLeg::parse(&li, clock, pda)
}

/// the leg without a walk budget (the engine's off-chain use)
fn unbounded(a: AnyLeg<'_>) -> AnyLeg<'_> {
    match a {
        AnyLeg::RayClmm(x) => AnyLeg::RayClmm(x.with_budget(ray::NO_BUDGET)),
        AnyLeg::Whirl(x) => AnyLeg::Whirl(x.with_budget(orca::NO_BUDGET)),
        o => o,
    }
}

#[test]
fn tick_maths_match_the_venues_constants_and_invert() {
    assert_eq!(ray::sqrt_price_at_tick(ray::MIN_TICK), Some(ray::MIN_SQRT_PRICE_X64));
    assert_eq!(ray::sqrt_price_at_tick(ray::MAX_TICK), Some(ray::MAX_SQRT_PRICE_X64));
    assert_eq!(orca::sqrt_price_at_tick(orca::MIN_TICK), Some(orca::MIN_SQRT_PRICE_X64));
    assert_eq!(orca::sqrt_price_at_tick(orca::MAX_TICK), Some(orca::MAX_SQRT_PRICE_X64));
    assert_eq!(ray::sqrt_price_at_tick(0), Some(1u128 << 64));
    assert_eq!(orca::sqrt_price_at_tick(0), Some(1u128 << 64));
    let mut rng = Rng(0x21);
    for _ in 0..20_000 {
        let t = rng.range(0, 2 * 443_636 - 2) as i32 - 443_636;
        let (r, r1) = (ray::sqrt_price_at_tick(t).unwrap(), ray::sqrt_price_at_tick(t + 1).unwrap());
        assert!(r < r1);
        assert_eq!(ray::tick_at_sqrt_price(r), Some(t), "ray tick {t}");
        assert_eq!(ray::tick_at_sqrt_price(r1 - 1), Some(t), "ray tick {t} upper");
        let (o, o1) = (orca::sqrt_price_at_tick(t).unwrap(), orca::sqrt_price_at_tick(t + 1).unwrap());
        assert!(o < o1);
        assert_eq!(orca::tick_at_sqrt_price(o), Some(t), "orca tick {t}");
        assert_eq!(orca::tick_at_sqrt_price(o1 - 1), Some(t), "orca tick {t} upper");
    }
    // the two venues' factors are not the same: they differ in the low bits at many ticks
    let differ = (-1000..1000).filter(|&t| ray::sqrt_price_at_tick(t) != orca::sqrt_price_at_tick(t)).count();
    assert!(differ > 0);
    assert_eq!(ray::tick_at_sqrt_price(ray::MAX_SQRT_PRICE_X64), None);
    assert_eq!(ray::sqrt_price_at_tick(ray::MAX_TICK + 1), None);
}

#[test]
fn wide_mul_div_matches_bigint() {
    use arbx_sizing::u256::{mul_div_wide, U256};
    let mut rng = Rng(0x512);
    let big = |x: U256| { let mut b = Vec::new(); for w in x.0.iter() { b.extend(w.to_le_bytes()); } BigUint::from_bytes_le(&b) };
    for _ in 0..20_000 {
        let mut w = || { let n = rng.range(0, 4) as usize; let mut a = [0u64; 4]; for x in a.iter_mut().take(n) { *x = rng.next(); } if rng.chance(1, 3) && n > 0 { a[n - 1] >>= rng.range(0, 63); } U256(a) };
        let (a, b, d) = (w(), w(), w());
        if d.is_zero() { assert_eq!(mul_div_wide(a, b, d, false), None); continue; }
        let (n, dd) = (big(a) * big(b), big(d));
        let fl = &n / &dd;
        let ce = if (&n % &dd) == BigUint::from(0u8) { fl.clone() } else { &fl + 1u8 };
        let to = |x: &BigUint| -> Option<U256> { let b = x.to_bytes_le(); if b.len() > 32 { return None; } let mut a = [0u64; 4]; for (i, c) in b.chunks(8).enumerate() { let mut v = [0u8; 8]; v[..c.len()].copy_from_slice(c); a[i] = u64::from_le_bytes(v); } Some(U256(a)) };
        assert_eq!(mul_div_wide(a, b, d, false), to(&fl));
        assert_eq!(mul_div_wide(a, b, d, true), to(&ce));
    }
}

#[test]
fn fixture_legs_quote_consistently() {
    let fx = fixtures();
    assert!(fx.len() >= 12);
    let mut checked = 0;
    for f in &fx {
        for zfo in [true, false] {
            let l = leg_of(f, zfo);
            let refs: Vec<AcctRef> = l.state.iter().map(|a| a.view()).collect();
            let parsed = parse_leg(&l, &refs, &f.clock).unwrap_or_else(|e| panic!("{} {zfo}: {e:?}", f.venue));
            let Ok(leg) = parsed.leg else { continue }; // a refused pool (the transfer-fee mint)
            let leg = unbounded(leg);
            // monotone exact-in quotes over a ladder
            let mut last = 0u64;
            let mut ok_sizes = vec![];
            for i in 0..48 {
                let x = (1_000f64 * 1.6f64.powi(i)) as u64;
                match leg.quote(x) {
                    Ok(q) => { assert!(q.out >= last, "{} {zfo} not monotone at {x}", f.venue); last = q.out; assert_eq!(q.spent, x); ok_sizes.push((x, q)); }
                    Err(QuoteErr::ZeroOut) => assert_eq!(last, 0, "ZeroOut after a payout at {x}"),
                    Err(QuoteErr::TooLarge) => break,
                    Err(e) => panic!("{} {zfo} {x}: {e:?}", f.venue),
                }
            }
            assert!(ok_sizes.len() >= 10, "{} {zfo}: {} sizes quote", f.venue, ok_sizes.len());
            for &(x, q) in ok_sizes.iter().step_by(4) {
                // fills sum to the quote; exact out of the same output debits at most x and pays it
                match &leg {
                    AnyLeg::RayClmm(c) => {
                        let (mut i_, mut o_) = (0u128, 0u128);
                        let w = c.fills(x, false, &mut |s| {
                            i_ += if c.fee_on_input { s.amount_in as u128 + s.fee as u128 } else { s.amount_in as u128 };
                            o_ += s.amount_out as u128;
                            if let Some((lo, _)) = s.limit { i_ += if c.fee_on_input { lo.amount_in as u128 + lo.fee as u128 } else { lo.amount_in as u128 }; o_ += lo.amount_out as u128; }
                        }).unwrap();
                        assert_eq!((i_, o_), (x as u128, q.out as u128), "ray fills {x}");
                        assert_eq!(w.quote, q);
                        let eo = c.quote_exact_out(q.out).unwrap();
                        assert!(eo.spent <= x && eo.out == q.out, "ray exact out {x}: {eo:?} vs {q:?}");
                    }
                    AnyLeg::Whirl(c) => {
                        let (mut i_, mut o_) = (0u128, 0u128);
                        let w = c.fills(x, false, &mut |s| { i_ += s.amount_in as u128 + s.fee as u128; o_ += s.amount_out as u128; }).unwrap();
                        assert_eq!((i_, o_), (x as u128, q.out as u128), "orca fills {x}");
                        assert_eq!(w.quote, q);
                        let eo = c.quote_exact_out(q.out).unwrap();
                        assert!(eo.spent <= x && eo.out == q.out, "orca exact out {x}: {eo:?} vs {q:?}");
                    }
                    _ => unreachable!(),
                }
            }
            // the exact capacity, where finite
            if let Some(cap) = leg.cap_in() {
                assert!(leg.quote(cap).is_ok() || cap == 0, "{} {zfo}: cap {cap} does not quote", f.venue);
                assert!(leg.quote(cap.saturating_add(1)).is_err(), "{} {zfo}: cap + 1 quotes", f.venue);
            }
            // the locator's stream: each range step's cumulative input is a size the exact swap ends on exactly
            let mut cum = (0u64, 0u64);
            let mut ends = vec![];
            let mut lo_seen = false;
            for _ in 0..24 {
                let mut pieces = vec![];
                let r = match &leg {
                    AnyLeg::RayClmm(c) => { let mut s = c.stream(); for _ in 0..ends.len() { let _ = s.next(&mut |_| {}); } s.next(&mut |p| pieces.push((p.used, p.out, p.mobius.is_some()))) }
                    AnyLeg::Whirl(c) => { let mut s = c.stream(); for _ in 0..ends.len() { let _ = s.next(&mut |_| {}); } s.next(&mut |p| pieces.push((p.used, p.out, true))).map_err(|_| ray::End::Cap) }
                    _ => unreachable!(),
                };
                if r.is_err() { break; }
                for (u, o, range) in pieces {
                    cum = (cum.0 + u, cum.1 + o);
                    if !range { lo_seen = true; }
                    if range && !lo_seen && u > 0 { ends.push(cum); }
                }
                if ends.len() > 12 { break; }
            }
            for &(u, o) in &ends {
                let q = leg.quote(u).unwrap_or_else(|e| panic!("{} {zfo}: step end {u}: {e:?}", f.venue));
                assert_eq!(q.out, o, "{} {zfo}: the stream's step end {u}", f.venue);
            }
            checked += 1;
        }
    }
    assert!(checked >= 36, "{checked} legs checked");
}

/// the walk budget (`max_bins` of kinds 7 and 8: swap steps): `steps_for(x)` is a budget that covers `x` with the same
/// quote, one step less answers Budget ("not evaluated", never TooLarge), and the locator's stream ends at the budget
/// with End::Budget
#[test]
fn walk_budget_is_exact_or_budget() {
    let fx = fixtures();
    let mut checked = 0;
    for f in &fx {
        for zfo in [true, false] {
            let l = leg_of(f, zfo);
            let refs: Vec<AcctRef> = l.state.iter().map(|a| a.view()).collect();
            let Ok(Parsed { leg: Ok(leg), .. }) = parse_leg(&l, &refs, &f.clock) else { continue };
            let leg = unbounded(leg);
            for i in 0..48 {
                let x = (1_000f64 * 1.6f64.powi(i)) as u64;
                let (q, steps, at, short) = match &leg {
                    AnyLeg::RayClmm(c) => {
                        let s = c.steps_for(x).unwrap_or(1);
                        (c.quote(x), c.steps_for(x), c.with_budget(s).quote(x), c.with_budget(s - 1).quote(x))
                    }
                    AnyLeg::Whirl(c) => {
                        let s = c.steps_for(x).unwrap_or(1);
                        (c.quote(x), c.steps_for(x), c.with_budget(s).quote(x), c.with_budget(s - 1).quote(x))
                    }
                    _ => unreachable!(),
                };
                let Ok(q) = q else { assert_eq!(steps, None, "{} {zfo} {x}: steps of a failing size", f.venue); continue };
                let s = steps.unwrap_or_else(|| panic!("{} {zfo} {x}: no steps for a size that quotes", f.venue));
                assert!(s >= 1);
                assert_eq!(at, Ok(q), "{} {zfo} {x}: the quote within its own steps ({s})", f.venue);
                assert_eq!(short, Err(QuoteErr::Budget), "{} {zfo} {x}: one step short of {s}", f.venue);
                checked += 1;
            }
            // the stream under a 3-step budget: at most 3 steps, then End::Budget (unless the venue's capacity ends first)
            let (n, budget_end) = match &leg {
                AnyLeg::RayClmm(c) => {
                    let b = c.with_budget(3);
                    let mut s = b.stream();
                    let mut n = 0;
                    let end = loop { match s.next(&mut |_| {}) { Ok(()) => n += 1, Err(e) => break e } };
                    (n, end == ray::End::Budget)
                }
                AnyLeg::Whirl(c) => {
                    let b = c.with_budget(3);
                    let mut s = b.stream();
                    let mut n = 0;
                    let end = loop { match s.next(&mut |_| {}) { Ok(()) => n += 1, Err(e) => break e } };
                    (n, end == orca::End::Budget)
                }
                _ => unreachable!(),
            };
            assert!(n <= 3, "{} {zfo}: {n} steps under a budget of 3", f.venue);
            if n == 3 { assert!(budget_end, "{} {zfo}: the stream did not end on its budget", f.venue); }
        }
    }
    assert!(checked > 300, "{checked} budgeted quotes checked");
}

/// the locator over DCAL (Raydium CLMM) ↔ 4uny (Orca, its price moved by k ticks): the plan's best exact candidate is
/// within 2 lamports of a brute-force grid's best exact round trip (the grid: 2,000 log-spaced sizes)
#[test]
fn locator_over_clmm_legs_finds_the_optimum() {
    let fx = fixtures();
    let ray_f = fx.iter().find(|f| f.venue == "RayCLMM" && f.pool == b58d("DCALKkpdk4dHE6bg7t3LXniuZ7VyDx4U4v4wTJtoBa6J")).unwrap();
    let orca_f = fx.iter().find(|f| f.venue == "Whirlpool" && f.pool == b58d("4uny6Y7daYwY4bt8B5DLrj4yqCD4XCYDkssKCyoVpS15")).unwrap();
    let clock = if orca_f.clock.unix_timestamp > ray_f.clock.unix_timestamp { orca_f.clock } else { ray_f.clock };
    let mut sized = 0;
    for k in [120i32, 60, -60, -90] {
        let mut of = Fix { venue: orca_f.venue.clone(), pool: orca_f.pool, clock, accts: orca_f.accts.clone() };
        let pd = &mut of.accts.get_mut(&orca_f.pool).unwrap().data;
        let t = i32_at(pd, 81) + k;
        let sp = (1.0001f64.powf((t as f64 + 0.5) / 2.0) * 18_446_744_073_709_551_616.0) as u128;
        pd[65..81].copy_from_slice(&sp.to_le_bytes());
        pd[81..85].copy_from_slice(&t.to_le_bytes());
        // k > 0: SOL buys more J6pQ on Orca: buy there (a→b), sell on Raydium (token 1 in)
        let (lb, ls) = if k > 0 { (leg_of(&of, true), leg_of(ray_f, false)) } else { (leg_of(ray_f, true), leg_of(&of, false)) };
        let (rb, rs): (Vec<AcctRef>, Vec<AcctRef>) = (lb.state.iter().map(|a| a.view()).collect(), ls.state.iter().map(|a| a.view()).collect());
        let b = unbounded(parse_leg(&lb, &rb, &clock).unwrap().leg.unwrap());
        let s = unbounded(parse_leg(&ls, &rs, &clock).unwrap().leg.unwrap());
        let trip = |x: u64| -> Option<i128> { let q0 = b.quote(x).ok()?; let q1 = s.quote(q0.out).ok()?; Some(q1.out as i128 - q0.spent as i128) };
        let cap = 50_000_000_000u64;
        let loc = arbx_sizing::opt::locate(&b.model().unwrap(), &s.model().unwrap(), Fx::from_u64(cap));
        let best_loc = loc.optima.iter().flatten().filter_map(|o| { let x = o.x.floor_u64().clamp(1, cap); trip(x).map(|p| (x, p)) }).max_by_key(|p| p.1);
        let grid = (0..2_000).map(|i| (1e5f64 * (cap as f64 / 1e5).powf(i as f64 / 1999.0)) as u64).filter_map(|x| trip(x).map(|p| (x, p))).max_by_key(|p| p.1);
        eprintln!("k {k:+}: locator {best_loc:?} grid {grid:?} (steps {})", loc.bins);
        let (Some((_, pl)), Some((_, pg))) = (best_loc, grid) else { continue };
        if pg > 0 {
            sized += 1;
            assert!(pl >= pg - 2, "k {k}: the locator's best {pl} is below the grid's {pg}");
        }
    }
    assert!(sized >= 3, "{sized} profitable routes");
}

#[test]
fn parse_refuses_typed_states_and_engine_bugs() {
    let fx = fixtures();
    let get = |prefix: &str| fx.iter().find(|f| bs58_prefix(&f.pool, prefix)).unwrap();
    let clock_of = |f: &Fix| f.clock;
    // Raydium: swaps disabled, not open yet, the first tick array missing, the extension needed and missing, a
    // paused mint; a tick array of another pool (DescError Key), the wrong owner (DescError Owner)
    let f = get("3ucNos4N");
    let base = leg_of(f, true);
    let parse_abort = |l: &Leg, c: &Clock| { let r: Vec<AcctRef> = l.state.iter().map(|a| a.view()).collect(); parse_leg(l, &r, c).map(|p| p.leg.err()) };
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state[0].data[389] = 0x10;
    assert_eq!(parse_abort(&l, &clock_of(f)), Ok(Some(arbx_sizing::Abort::Clmm(ClmmWhy::Status))));
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state[0].data[1080..1088].copy_from_slice(&(f.clock.unix_timestamp as u64).to_le_bytes());
    assert_eq!(parse_abort(&l, &clock_of(f)), Ok(Some(arbx_sizing::Abort::Clmm(ClmmWhy::NotOpen))));
    // drop the current tick array (the first one after the extension)
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state.remove(7);
    l.desc.n_bin_arrays -= 1;
    assert_eq!(parse_abort(&l, &clock_of(f)), Ok(Some(arbx_sizing::Abort::Clmm(ClmmWhy::TickArrays))));
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state[8].data[8..40].copy_from_slice(&[7u8; 32]);
    assert!(matches!(parse_abort(&l, &clock_of(f)), Err(e) if e.code == arbx_sizing::DescCode::Key));
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state[0].owner = layout::RAY_CPMM;
    assert!(matches!(parse_abort(&l, &clock_of(f)), Err(e) if e.code == arbx_sizing::DescCode::Owner));
    let d = get("DCALKkpd");
    let base = leg_of(d, true);
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state.remove(6); // the extension
    l.desc.n_bin_arrays -= 1;
    assert_eq!(parse_abort(&l, &clock_of(d)), Ok(Some(arbx_sizing::Abort::Clmm(ClmmWhy::BitmapExtension))));
    let p = get("7tJVK2uE");
    let base = leg_of(p, true);
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    let m = &mut l.state[4].data;
    let off = ext_value(m, 26).unwrap() + 32; // Pausable {authority, paused}
    m[off] = 1;
    assert_eq!(parse_abort(&l, &clock_of(p)), Ok(Some(arbx_sizing::Abort::Clmm(ClmmWhy::MintPaused))));
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    let m = &mut l.state[4].data;
    let off = ext_value(m, 6).unwrap(); // DefaultAccountState {state}: 2 = Frozen
    m[off] = 2;
    assert_eq!(parse_abort(&l, &clock_of(p)), Ok(Some(arbx_sizing::Abort::Clmm(ClmmWhy::MintFrozen))));
    // Orca: trading not enabled yet, a Clock before the last reward update, the needed tick arrays all missing
    let o = get("5KqohoeG");
    let base = leg_of(o, true);
    // its Token-2022 mint paused (the Pausable extension appended), or charging a transfer fee (bps and cap set)
    let t = (1..3).find(|&i| base.state[i].owner == layout::TOKEN_2022).unwrap();
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state[t].data.extend([26u8, 0, 33, 0].iter().chain([0u8; 32].iter()).chain([1u8].iter()));
    assert_eq!(parse_abort(&l, &clock_of(o)), Ok(Some(arbx_sizing::Abort::Whirl(WhirlWhy::MintPaused))));
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    let v = ext_value(&l.state[t].data, 1).unwrap(); // TransferFeeConfig: older {max 80, bps 88}, newer {max 98, bps 106}
    for (o, b) in [(80, &u64::MAX.to_le_bytes()[..]), (88, &100u16.to_le_bytes()[..]), (98, &u64::MAX.to_le_bytes()[..]), (106, &100u16.to_le_bytes()[..])] {
        l.state[t].data[v + o..v + o + b.len()].copy_from_slice(b);
    }
    assert_eq!(parse_abort(&l, &clock_of(o)), Ok(Some(arbx_sizing::Abort::TransferFee)));
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state[8].data[40..48].copy_from_slice(&((o.clock.unix_timestamp + 60) as u64).to_le_bytes());
    assert_eq!(parse_abort(&l, &clock_of(o)), Ok(Some(arbx_sizing::Abort::Whirl(WhirlWhy::TradeNotEnabled))));
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state[0].data[261..269].copy_from_slice(&((o.clock.unix_timestamp + 60) as u64).to_le_bytes());
    assert_eq!(parse_abort(&l, &clock_of(o)), Ok(Some(arbx_sizing::Abort::Whirl(WhirlWhy::Timestamp))));
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    for i in 5..8 { l.state[i] = absent([9u8; 32]); }
    assert_eq!(parse_abort(&l, &clock_of(o)), Ok(Some(arbx_sizing::Abort::Whirl(WhirlWhy::TickArrays))));
    let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
    l.state[5].data[12..44].copy_from_slice(&[3u8; 32]); // a dynamic tick array naming another whirlpool
    assert!(matches!(parse_abort(&l, &clock_of(o)), Err(e) if e.code == arbx_sizing::DescCode::Key));
    // an absent tick array passed as the PDA of a needed start index is zeroed (G1vH: its sequence ends in absent ones)
    let g = get("G1vH3TjR");
    for zfo in [true, false] {
        let l = leg_of(g, zfo);
        let r: Vec<AcctRef> = l.state.iter().map(|a| a.view()).collect();
        let Ok(Parsed { leg: Ok(AnyLeg::Whirl(w)), .. }) = parse_leg(&l, &r, &g.clock) else { panic!("G1vH {zfo}") };
        assert!(w.sequence().1 >= 2, "G1vH {zfo}: the sequence {:?}", w.sequence());
    }
}

fn bs58_prefix(k: &Pk, prefix: &str) -> bool {
    // encode the key and compare (tests only)
    const A: &[u8] = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    let mut digits: Vec<u8> = vec![];
    for &b in k.iter() {
        let mut carry = b as u32;
        for d in digits.iter_mut() { carry += (*d as u32) << 8; *d = (carry % 58) as u8; carry /= 58; }
        while carry > 0 { digits.push((carry % 58) as u8); carry /= 58; }
    }
    let s: String = digits.iter().rev().map(|&d| A[d as usize] as char).collect();
    s.starts_with(prefix)
}

/// a Token-2022 mint's extension `t` (TLV after the account type byte at 165): its value offset
fn ext_value(d: &[u8], t: u16) -> Option<usize> {
    if d.len() <= 166 || d[165] != 1 { return None; }
    let mut o = 166;
    while o + 4 <= d.len() {
        let (tt, l) = (u16::from_le_bytes([d[o], d[o + 1]]), u16::from_le_bytes([d[o + 2], d[o + 3]]) as usize);
        if tt == 0 { return None; }
        if tt == t { return Some(o + 4); }
        o += 4 + l;
    }
    None
}

#[test]
fn mutated_states_never_panic() {
    let fx = fixtures();
    let mut rng = Rng(0xC1A);
    let mut runs = 0;
    for f in &fx {
        for zfo in [true, false] {
            let base = leg_of(f, zfo);
            for it in 0..120 {
                let mut l = Leg { desc: base.desc, state: base.state.clone(), input: base.input };
                // flip bytes in the pool, a tick array or the oracle / config
                for _ in 0..rng.range(1, 6) {
                    let ai = [0usize, 1, l.state.len() - 1, rng.range(5, l.state.len() as u64 - 1) as usize][rng.range(0, 3) as usize];
                    let d = &mut l.state[ai].data;
                    if d.len() > 8 { let i = rng.range(8, d.len() as u64 - 1) as usize; d[i] = if it % 3 == 0 { 0xFF } else { rng.next() as u8 }; }
                }
                let r: Vec<AcctRef> = l.state.iter().map(|a| a.view()).collect();
                let Ok(Parsed { leg: Ok(leg), .. }) = parse_leg(&l, &r, &f.clock) else { continue };
                let leg = unbounded(leg);
                for x in [1u64, 1_000, 1_000_000_000, rng.log(1, 1 << 50), u64::MAX] { let _ = leg.quote(x); }
                match &leg {
                    AnyLeg::RayClmm(c) => { let _ = c.fills(rng.log(1, 1 << 40), true, &mut |_| {}); let mut s = c.stream(); for _ in 0..8 { if s.next(&mut |_| {}).is_err() { break; } } }
                    AnyLeg::Whirl(c) => { let _ = c.fills(rng.log(1, 1 << 40), true, &mut |_| {}); let mut s = c.stream(); for _ in 0..8 { if s.next(&mut |_| {}).is_err() { break; } } }
                    _ => {}
                }
                runs += 1;
            }
        }
    }
    eprintln!("{runs} mutated legs parsed and quoted without a panic");
    assert!(runs > 1_000);
}

#[test]
#[cfg(feature = "encode")]
fn descriptors_of_kinds_7_and_8() {
    use arbx_sizing::desc::{encode_block, parse_block, SizingBlock, SzFlags};
    let mut legs = [LegDesc::placeholder(); 6];
    legs[0] = LegDesc { kind: Kind::RayClmm, base_or_token0_in: true, n_bin_arrays: 4, pump_bump: 0, max_bins: 90, positions: None };
    legs[1] = LegDesc { kind: Kind::Whirlpool, base_or_token0_in: false, n_bin_arrays: 2, pump_bump: 0, max_bins: 40, positions: None };
    let b = SizingBlock { flags: SzFlags(0), min_size: 1, engine_amount: 100, lamport_offset: 0, max_iters: 0, pairs: [(0, 1), (0, 0), (0, 0)], n_pairs: 1, legs, n_legs: 2, basket: false };
    let mut v = vec![];
    encode_block(&b, &mut v);
    let (p, len) = parse_block(&v, 0, 2, false, 100).unwrap();
    assert_eq!((p.legs()[0], p.legs()[1], len), (legs[0], legs[1], v.len()));
    assert_eq!(layout::positions(&legs[0]).unwrap().as_slice(), &[2, 1, 5, 6, 11, 12, 13, 14, 15, 16]);
    assert_eq!(layout::positions(&legs[1]).unwrap().as_slice(), &[4, 5, 6, 8, 10, 11, 12, 13, 14, 15, 16]);
    // the array counts: Raydium CLMM 1..=7, Orca 0..=3
    for (kd, extra, ok) in [(7u8 | (0 << 5), vec![1u8], false), (7 | (7 << 5), vec![1], true), (8 | (4 << 5), vec![1], false), (8, vec![1], true), (8 | (3 << 5), vec![0], false)] {
        let mut d = vec![0u8];
        d.extend(1u32.to_le_bytes());
        d.extend(100u64.to_le_bytes());
        d.push(kd);
        d.extend(&extra);
        d.push(Kind::RayCpmm as u8 | 0x10);
        assert_eq!(parse_block(&d, 0, 2, false, 100).is_ok(), ok, "kd {kd:#x} {extra:?}");
    }
    // the static CU bound counts every CLMM step of the budget
    assert!(arbx_sizing::cu_bound(&b) > 90 * arbx_sizing::budget::cost::EXACT_STEP);
}

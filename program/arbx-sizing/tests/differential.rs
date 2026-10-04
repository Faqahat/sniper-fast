//! Differential tests against the engine's own maths (read-only copies in tests/reference/, DESIGN.md §6.2): the
//! same account bytes go into both. Equal everywhere except the documented divergences of DESIGN.md §2.7, which are
//! asserted as differences of bounded size and sign.
mod common;
#[path = "reference/mod.rs"]
mod reference;

use arbx_sizing::venue::dammv2 as ours_damm;
use arbx_sizing::{AnyLeg, Kind, QuoteErr};
use common::*;
use reference::{cp, dammv2 as ref_damm, dlmm as ref_dlmm, PoolMeta, Venue};
use std::collections::HashMap;
use std::sync::Arc;

fn meta(venue: Venue, flag: bool) -> PoolMeta {
    PoolMeta { venue, pool: [0; 32], t0: [0; 32], t1: arbx_sizing::layout::WSOL, vault0: [0; 32], vault1: [0; 32], t0_prog: [0; 32], t1_prog: [0; 32], extra: vec![], flag }
}

fn sizes(rng: &mut Rng, hi: u64) -> Vec<u64> { (0..60).map(|_| rng.log(1, hi)).chain([1, 2, 7, hi]).collect() }

#[derive(Default, Debug)]
struct Tally { equal: u64, documented: u64, both_err: u64 }

/* ------------------------------------------------- AMM v4, CPMM ------------------------------------------------- */

#[test]
fn ammv4_identical() {
    let mut rng = Rng(101);
    let mut t = Tally::default();
    for _ in 0..400 {
        let (coin, pc) = (rng.log(1000, 1 << 62), rng.log(1000, 1 << 62));
        let den = rng.range(100, 1_000_000);
        let num = rng.range(0, den - 1);
        let (m0, m1) = ([1u8; 32], [2u8; 32]);
        let st = ammv4(&mut rng, coin, pc, num, den, m0, m1);
        let a = cp::Accounts { pool: &st[0].data, vault0: &st[1].data, vault1: &st[2].data, extra: vec![] };
        let snap = cp::snapshot(&meta(Venue::RayAmmV4, false), &a, 0, CLOCK.unix_timestamp, None).unwrap();
        for coin_in in [true, false] {
            let l = OwnedLeg::new(Kind::RayAmmV4, coin_in, st.clone(), if coin_in { m0 } else { m1 });
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let leg = any_leg(&l, &refs);
            for x in sizes(&mut rng, u64::MAX >> 2) {
                match (leg.quote(x), cp::quote(&snap, coin_in, x)) {
                    (Ok(q), Some(r)) => { assert_eq!(q.out, r.out, "ammv4 x={x}"); t.equal += 1; }
                    (Err(_), None) => t.both_err += 1,
                    (a, b) => panic!("ammv4 x={x}: ours {a:?} reference {b:?}"),
                }
            }
        }
    }
    eprintln!("ammv4 vs reference: {t:?}");
}

#[test]
fn cpmm_identical_except_the_creator_fee_ceil() {
    let mut rng = Rng(102);
    let mut t = Tally::default();
    let (m0, m1) = ([1u8; 32], [2u8; 32]);
    for _ in 0..400 {
        let spec = CpmmSpec { r0: rng.log(1000, 1 << 62), r1: rng.log(1000, 1 << 62), trade: rng.range(0, 30_000), creator: rng.range(0, 10_000),
            enable_creator: rng.chance(1, 2), creator_on: rng.range(0, 2) as u8, owed0: rng.range(0, 1 << 20), owed1: rng.range(0, 1 << 20) };
        for zfo in [true, false] {
            let st = cpmm(&mut rng, &spec, m0, m1, zfo);
            let (v0, v1) = if zfo { (&st[2], &st[3]) } else { (&st[3], &st[2]) };
            let a = cp::Accounts { pool: &st[0].data, vault0: &v0.data, vault1: &v1.data, extra: vec![&st[1].data] };
            let snap = cp::snapshot(&meta(Venue::RayCpmm, false), &a, 0, CLOCK.unix_timestamp, None).unwrap();
            let l = OwnedLeg::new(Kind::RayCpmm, zfo, st.clone(), if zfo { m0 } else { m1 });
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let AnyLeg::Cpmm(leg) = any_leg(&l, &refs) else { unreachable!() };
            let on_input_creator = leg.fee_in != spec.trade;
            let (r_in, r_out) = (leg.r_in as u128, leg.r_out as u128);
            for x in sizes(&mut rng, u64::MAX >> 2) {
                match (leg.quote(x), cp::quote(&snap, zfo, x)) {
                    (Ok(q), Some(r)) if q.out == r.out => t.equal += 1,
                    (Ok(q), Some(r)) => {
                        // DESIGN.md §2.7 #3: the program takes ONE ceil of x·(trade+creator); the engine two. Our net
                        // input is at most 1 unit larger, so our output is larger by at most one unit's worth.
                        assert!(on_input_creator, "cpmm differs without an input creator fee: x={x} {} vs {}", q.out, r.out);
                        let d = q.out as i128 - r.out as i128;
                        assert!(d > 0 && d as u128 <= r_out / r_in + 1, "cpmm x={x}: ours {} reference {}", q.out, r.out);
                        t.documented += 1;
                    }
                    // the engine's two ceils leave no net input where the program's one ceil leaves one unit
                    (Ok(q), None) if on_input_creator => {
                        assert!(q.out as u128 <= r_out / r_in + 1, "cpmm x={x}: ours {} where the reference has nothing", q.out);
                        t.documented += 1;
                    }
                    (Err(_), None) => t.both_err += 1,
                    (a, b) => panic!("cpmm x={x}: ours {a:?} reference {b:?}"),
                }
            }
        }
    }
    eprintln!("cpmm vs reference: {t:?}");
    assert!(t.documented > 0 && t.equal > 10_000);
}

/* --------------------------------------------------- PumpSwap --------------------------------------------------- */

#[test]
fn pumpswap_sell_identical_buy_bounded() {
    let mut rng = Rng(103);
    let (mut sell, mut buy) = (Tally::default(), Tally::default());
    for _ in 0..400 {
        let s = PumpSpec { base: rng.log(1_000_000, 1 << 60), quote: rng.log(1_000_000, 1 << 50), virt: if rng.chance(1, 2) { rng.log(1, 1 << 40) as i128 } else { 0 },
            supply: rng.log(1 << 30, 1 << 60), canonical: rng.chance(3, 4), ..Default::default() };
        let a = pump(&mut rng, &s);
        let cfg = Arc::new(cp::decode_pump_fee_cfg(&a.fee_cfg.data).unwrap());
        let acc = cp::Accounts { pool: &a.pool.data, vault0: &a.base_vault.data, vault1: &a.quote_vault.data, extra: vec![&a.base_mint.data] };
        let Ok(snap) = cp::snapshot(&meta(Venue::PumpSwap, s.canonical), &acc, 0, 0, Some(&cfg)) else { continue };
        for is_sell in [true, false] {
            let l = OwnedLeg::pump(&a, is_sell);
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let AnyLeg::Pump(leg) = any_leg(&l, &refs) else { unreachable!() };
            let hi = if is_sell { leg.base.saturating_mul(3) } else { leg.qv.saturating_mul(3) };
            for x in sizes(&mut rng, hi) {
                let (q, r) = (leg.quote(x), cp::quote(&snap, is_sell, x));
                if is_sell {
                    match (q, r) {
                        (Ok(q), Some(r)) => { assert_eq!(q.out, r.out, "sell x={x}"); sell.equal += 1; }
                        (Err(_), None) => sell.both_err += 1,
                        // the real-reserve check: the program needs q − lp_fee ≤ Q, the engine q ≤ Q (stricter)
                        (Ok(_), None) => {
                            let qq = leg.qv as u128 * x as u128 / (leg.base as u128 + x as u128);
                            assert!(qq > leg.quote as u128, "sell x={x}: reference refuses below the reserve edge");
                            sell.documented += 1;
                        }
                        (a, b) => panic!("sell x={x}: ours {a:?} reference {b:?}"),
                    }
                } else {
                    match (q, r) {
                        (Ok(q), Some(r)) => {
                            // DESIGN.md §2.7 #1: the engine lacks the fee-overrun adjustment and the −1 → it is above
                            // by at most ~4 units of quote input's worth of base
                            let d = r.out as i128 - q.out as i128;
                            let bound = 4 * leg.base as i128 / leg.qv as i128 + 2;
                            assert!(d >= 0 && d <= bound, "buy x={x}: ours {} reference {} bound {bound}", q.out, r.out);
                            if d == 0 { buy.equal += 1 } else { buy.documented += 1 }
                        }
                        (Err(_), None) | (Err(QuoteErr::ZeroOut), Some(_)) => buy.both_err += 1,
                        (a, b) => panic!("buy x={x}: ours {a:?} reference {b:?}"),
                    }
                }
            }
        }
    }
    eprintln!("pumpswap sell vs reference: {sell:?}; buy_exact_quote_in: {buy:?}");
    assert!(sell.equal > 5_000 && buy.documented > 1_000);
}

/* ----------------------------------------------------- DLMM ----------------------------------------------------- */

fn ref_view<'a>(st: &'a [Acct]) -> (HashMap<i64, &'a [u8]>, &'a [u8]) {
    let arrays = st[3..].iter().map(|a| (i64::from_le_bytes(a.data[8..16].try_into().unwrap()), &a.data[..])).collect();
    (arrays, &st[0].data[..])
}

/// pairs whose features the engine models (no limit orders, fee on input, every array in range passed): identical.
/// With limit orders: ours sees more liquidity per bin, so it pays at least as much (DESIGN.md §2.7 #4).
#[test]
fn dlmm_identical_where_modelled_and_bounded_with_limit_orders() {
    let mut rng = Rng(104);
    let (mut same, mut lo) = (Tally::default(), Tally::default());
    for case in 0..300 {
        let with_lo = case % 3 == 0;
        let bin_step = [1u16, 10, 25, 100, 200][rng.range(0, 4) as usize];
        let active = rng.range(0, 600) as i32 - 300;
        let mut bins = vec![];
        // dense enough that every array in ±2 of the active one has liquidity (no bitmap jumps)
        for id in active - 140..=active + 140 {
            if rng.chance(1, 4) && id != active && (id - active).abs() % 35 != 0 { continue; }
            let amt = rng.log(1, 1 << 38);
            let (ax, ay) = if id < active { (0, amt) } else if id > active { (amt, 0) } else { (amt, rng.log(1, 1 << 38)) };
            let lof = if with_lo && rng.chance(1, 3) { (rng.log(1, 1 << 34), rng.log(1, 1 << 30), rng.range(0, 1) as u8) } else { (0, 0, 0) };
            bins.push((id, ax, ay, lof));
        }
        let spec = DlmmSpec { bin_step, base_factor: rng.range(1000, 30_000) as u16, vfc: rng.range(0, 50_000) as u32, max_va: rng.range(10_000, 400_000) as u32,
            va: rng.range(0, 300_000) as u32, v_ref: rng.range(0, 100_000) as u32, idx_ref: active + rng.range(0, 40) as i32 - 20,
            last_ts: CLOCK.unix_timestamp - rng.range(0, 2000) as i64, active, function_type: if with_lo { 2 } else { 1 }, collect_fee_mode: 0, bins, ..Default::default() };
        let (p, mx, my, arrays) = dlmm(&mut rng, &spec, [3u8; 32], [4u8; 32]);
        // the same pool with every limit order merged into the bin's own amount, for the reference
        let mut merged = spec.clone();
        for b in merged.bins.iter_mut() {
            let (open, processed, ask) = b.3;
            if ask == 0 { b.2 += open + processed } else { b.1 += open + processed }
            b.3 = (0, 0, 0);
        }
        let (mp, mmx, mmy, marrays) = dlmm(&mut rng, &merged, [3u8; 32], [4u8; 32]);
        for swap_for_y in [true, false] {
            let st = dlmm_state(&p, &mx, &my, &arrays, swap_for_y);
            let mst = dlmm_state(&mp, &mmx, &mmy, &marrays, swap_for_y);
            let l = OwnedLeg::new(Kind::Dlmm, swap_for_y, st.clone(), if swap_for_y { [3u8; 32] } else { [4u8; 32] });
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let leg = any_leg(&l, &refs);
            let (amap, pair) = ref_view(&st);
            let view = ref_dlmm::View { pair, arrays: &amap, over: None };
            let (mamap, mpair) = ref_view(&mst);
            let mview = ref_dlmm::View { pair: mpair, arrays: &mamap, over: None };
            let cap = leg.cap_in().unwrap();
            for x in sizes(&mut rng, cap.max(2)) {
                let q = leg.quote(x);
                let r = ref_dlmm::quote(&view, swap_for_y, x, CLOCK.unix_timestamp, false);
                let t = if with_lo { &mut lo } else { &mut same };
                if !with_lo {
                    match (q, r) {
                        (Ok(q), Ok(r)) => { assert_eq!(q.out, r.out, "dlmm x={x} case {case}"); t.equal += 1; }
                        (Err(_), Err(_)) => t.both_err += 1,
                        // the reference stops at an array it was not given; the program (and ours) jumps over empty
                        // arrays by the bitmap (DESIGN.md §2.7 #4)
                        (Ok(_), Err(ref_dlmm::Why::ArrayNotLoaded)) => t.documented += 1,
                        (a, b) => panic!("dlmm x={x} case {case} sfy {swap_for_y}: ours {a:?} reference {b:?}"),
                    }
                    continue;
                }
                // with limit orders: the engine skips the layers (DESIGN.md §2.7 #4) ...
                if let (Ok(q), Ok(r)) = (q, r) { if q.out != r.out { t.documented += 1; } }
                // ... and equals ours, up to the per-layer ceils, once the layers are merged into the bins
                match (q, ref_dlmm::quote(&mview, swap_for_y, x, CLOCK.unix_timestamp, false)) {
                    (Ok(q), Ok(r)) => {
                        let d = (q.out as i128 - r.out as i128).unsigned_abs();
                        let bound = (q.out as u128 / x as u128 + 2) * 256 + 16;
                        assert!(d <= bound, "dlmm merged x={x}: ours {} reference {} bound {bound}", q.out, r.out);
                        if d == 0 { t.equal += 1 }
                    }
                    (Err(_), Err(_)) => t.both_err += 1,
                    (Ok(_), Err(ref_dlmm::Why::ArrayNotLoaded)) => t.documented += 1,
                    (a, b) => panic!("dlmm merged x={x} case {case}: ours {a:?} reference {b:?}"),
                }
            }
        }
    }
    eprintln!("dlmm vs reference, no limit orders: {same:?}; with limit orders (equal = equal to the merged-layer reference, documented = differs from the plain reference): {lo:?}");
    assert!(same.equal > 5_000 && lo.documented > 500);
}

/* ---------------------------------------------------- DAMM v2 ---------------------------------------------------- */

#[test]
fn dammv2_identical() {
    let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../testdata/dammv2-vectors.json")).unwrap()).unwrap();
    let mut rng = Rng(105);
    let mut t = Tally::default();
    for (_, pv) in v["pools"].as_object().unwrap() {
        let raw = b64(pv["b64"].as_str().unwrap());
        let mut rp = ref_damm::decode(&raw).unwrap();
        rp.transfer_fee_known_zero = true;
        let mut op = ours_damm::decode(&raw).unwrap();
        op.transfer_fee_known_zero = true;
        for dt in [0i64, 1, 31, 299, 601, 5_000, 1_000_000] {
            let (slot, now) = (452_967_433 + dt as u64 * 3, 1_791_039_568 + dt);
            for a_to_b in [true, false] {
                for x in sizes(&mut rng, u64::MAX) {
                    let (o, r) = (ours_damm::swap_exact_in(&op, a_to_b, x, slot, now), ref_damm::swap_exact_in(&rp, a_to_b, x, slot, now));
                    match (o, r) {
                        (Ok((oo, oa)), Ok((ro, ra))) => {
                            assert_eq!(oo, ro);
                            assert_eq!((oa.sqrt_price, oa.token_a_amount, oa.token_b_amount, oa.liquidity), (ra.sqrt_price, ra.token_a_amount, ra.token_b_amount, ra.liquidity));
                            assert_eq!((oa.dynamic_fee.volatility_accumulator, oa.dynamic_fee.last_update_timestamp, oa.dynamic_fee.sqrt_price_reference),
                                (ra.dynamic_fee.volatility_accumulator, ra.dynamic_fee.last_update_timestamp, ra.dynamic_fee.sqrt_price_reference));
                            // and the leg path (the limiter-aware parse: `parse` itself refuses a limiter in force, REVIEW.md F5)
                            let clock = arbx_sizing::Clock { slot, unix_timestamp: now, epoch: 0 };
                            let leg = ours_damm::parse_with_limiter(&raw, a_to_b, true, &clock).unwrap();
                            assert_eq!(leg.quote(x).unwrap().out, oo);
                            match ours_damm::parse(&raw, a_to_b, true, &clock) {
                                Ok(l) => assert_eq!(l.quote(x).unwrap().out, oo),
                                Err(a) => { assert!(leg.fee_fixed.is_none()); assert_eq!(a, arbx_sizing::Abort::Damm(arbx_sizing::error::DammWhy::RateLimiter)); }
                            }
                            t.equal += 1;
                        }
                        (Err(oe), Err(re)) => {
                            let same_class = matches!((oe, re), (ours_damm::Fail::ZeroOut, ref_damm::Fail::ZeroOut) | (ours_damm::Fail::TooLarge, ref_damm::Fail::TooLarge(_)) | (ours_damm::Fail::Refused(_), ref_damm::Fail::Refused(_)));
                            assert!(same_class, "x={x}: ours {oe:?} reference {re:?}");
                            t.both_err += 1;
                        }
                        (a, b) => panic!("dammv2 x={x}: ours {a:?} reference {b:?}"),
                    }
                }
            }
        }
    }
    eprintln!("dammv2 vs reference: {t:?}");
    assert!(t.equal > 5_000);
}

/* ---------------------------------------------- real mainnet states ---------------------------------------------- */

#[test]
fn mainnet_pools_vs_reference() {
    let m = Mainnet::load();
    let clock = m.clock();
    let mut rng = Rng(106);
    let wsol = arbx_sizing::layout::WSOL;
    let mut report = vec![];
    // PumpSwap GLL3 (canonical, wSOL quote): sell identical, buy within the documented bound
    {
        let st = m.state("GLL3CzybpSCLZdoACf8QUM5YrKVwyA65kQ2RcTsJxxzV");
        let bump = m.pool("GLL3CzybpSCLZdoACf8QUM5YrKVwyA65kQ2RcTsJxxzV")["bump"].as_u64().unwrap() as u8;
        let cfg = Arc::new(cp::decode_pump_fee_cfg(&st[6].data).unwrap());
        let acc = cp::Accounts { pool: &st[0].data, vault0: &st[4].data, vault1: &st[5].data, extra: vec![&st[2].data] };
        let snap = cp::snapshot(&meta(Venue::PumpSwap, true), &acc, 0, 0, Some(&cfg)).expect("engine snapshot of GLL3");
        for sell in [true, false] {
            let mut l = OwnedLeg::new(if sell { Kind::PumpSell } else { Kind::PumpBuy }, sell, st.clone(), if sell { st[2].key } else { wsol });
            l.desc.pump_bump = bump;
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
            let leg = AnyLeg::parse(&li, &clock, pda).unwrap().leg.unwrap();
            let (mut eq, mut bounded) = (0, 0);
            for x in sizes(&mut rng, 100_000_000_000) {
                if let (Ok(q), Some(r)) = (leg.quote(x), cp::quote(&snap, sell, x)) {
                    let AnyLeg::Pump(p) = leg else { unreachable!() };
                    let bound = 4 * p.base / p.qv + 2;
                    if sell { assert_eq!(q.out, r.out); eq += 1; } else { assert!(r.out >= q.out && r.out - q.out <= bound, "GLL3 buy x={x}: {} vs {} bound {bound}", q.out, r.out); if r.out == q.out { eq += 1 } else { bounded += 1 } }
                }
            }
            report.push(format!("GLL3 {}: {eq} equal, {bounded} within the documented bound", if sell { "sell" } else { "buy" }));
        }
    }
    // CPMM, AMM v4: identical
    for name in ["GfApkU62yAmUXc6FNsZrBLgcUn8vXdhW6WzSbA5ETtDa", "Hmx1eHEdm67YYZYEathc6aki2q3zjhhTmw7wZPq66BnJ"] {
        let s0: Vec<Acct> = m.pool(name)["state0"].as_array().unwrap().iter().map(|k| m.acct(k.as_str().unwrap())).collect();
        let acc = cp::Accounts { pool: &s0[0].data, vault0: &s0[2].data, vault1: &s0[3].data, extra: vec![&s0[1].data] };
        let snap = cp::snapshot(&meta(Venue::RayCpmm, false), &acc, 0, clock.unix_timestamp, None).unwrap();
        for zfo in [true, false] {
            let st = if zfo { s0.clone() } else { vec![s0[0].clone(), s0[1].clone(), s0[3].clone(), s0[2].clone(), s0[5].clone(), s0[4].clone()] };
            let l = OwnedLeg::new(Kind::RayCpmm, zfo, st.clone(), st[4].key);
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
            let parsed = AnyLeg::parse(&li, &clock, pda).unwrap().leg;
            if name.starts_with("Hmx1") {
                // its token-1 mint (8jG1myVR…, Token-2022) charges a 3% transfer fee: refused, as the engine drops it
                assert_eq!(parsed.err(), Some(arbx_sizing::Abort::TransferFee));
                report.push("CPMM Hmx1… refused: Token-2022 transfer fee 300 bps (the engine drops this pool too)".into());
                continue;
            }
            let leg = parsed.unwrap();
            let mut eq = 0;
            for x in sizes(&mut rng, 1 << 50) {
                match (leg.quote(x), cp::quote(&snap, zfo, x)) { (Ok(q), Some(r)) => { assert_eq!(q.out, r.out); eq += 1; } (Err(_), None) => {} (a, b) => panic!("{a:?} {b:?}") }
            }
            report.push(format!("CPMM {}… zfo={zfo}: {eq} equal", &name[..6]));
        }
    }
    {
        let name = "FVq2chsiAcPqwL9L3zafF8juQHb7mui6LWMuE8g5L4K4";
        let st = m.state(name);
        let acc = cp::Accounts { pool: &st[0].data, vault0: &st[1].data, vault1: &st[2].data, extra: vec![] };
        let snap = cp::snapshot(&meta(Venue::RayAmmV4, false), &acc, 0, clock.unix_timestamp, None).unwrap();
        for coin_in in [true, false] {
            let mint_in = arbx_sizing::math::key_at(&st[0].data, if coin_in { 400 } else { 432 }).copied().unwrap();
            let l = OwnedLeg::new(Kind::RayAmmV4, coin_in, st.clone(), mint_in);
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
            let leg = AnyLeg::parse(&li, &clock, pda).unwrap().leg.unwrap();
            let mut eq = 0;
            for x in sizes(&mut rng, 1 << 50) {
                match (leg.quote(x), cp::quote(&snap, coin_in, x)) { (Ok(q), Some(r)) => { assert_eq!(q.out, r.out); eq += 1; } (Err(_), None) => {} (a, b) => panic!("{a:?} {b:?}") }
            }
            report.push(format!("AMM v4 FVq2 coin_in={coin_in}: {eq} equal"));
        }
    }
    // DAMM v2: identical
    for name in ["C8jdide5evNRRVBiisJSnFeHH2k7FKbARP64iyfSrkdf", "2E8c2vnAKQ3WaSHjezHwQ6GozuXRx96JX7GoNoBeqBug", "3Bu5wTUftguy5BxhTgFrukz6wvG6d4xYRKuU43jWA3cg"] {
        let st = m.state(name);
        let mut rp = ref_damm::decode(&st[0].data).unwrap();
        rp.transfer_fee_known_zero = true;
        for a_to_b in [true, false] {
            let l = OwnedLeg::new(Kind::DammV2, a_to_b, st.clone(), if a_to_b { st[1].key } else { st[2].key });
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
            let leg = AnyLeg::parse(&li, &clock, pda).unwrap().leg.unwrap();
            let mut eq = 0;
            for x in sizes(&mut rng, 1 << 56) {
                match (leg.quote(x), ref_damm::swap_exact_in(&rp, a_to_b, x, clock.slot, clock.unix_timestamp)) {
                    (Ok(q), Ok((r, _))) => { assert_eq!(q.out, r); eq += 1; }
                    (Err(_), Err(_)) => {}
                    (a, b) => panic!("{name} {a:?} {b:?}"),
                }
            }
            report.push(format!("DAMM v2 {}… a_to_b={a_to_b}: {eq} equal", &name[..6]));
        }
    }
    // DLMM: the real HOTBOT pairs carry limit orders (function_type 2): ours ≥ reference; 7hvn's walk stays in
    // bins without limit orders for small sizes: equal there
    for name in ["6D4EWF22HfQamimKhX47tqiu9DVCkcxDMrmhnSvewKAo", "7hvn8egrNGkpQFGyziHxvGkJFWtmoCyXmYYXp4V7tszd"] {
        let mut st = m.state(name);
        let arrays: Vec<(i64, String)> = m.pool(name)["arrays"].as_object().unwrap().iter().map(|(k, v)| (k.parse().unwrap(), v.as_str().unwrap().to_string())).collect();
        for swap_for_y in [true, false] {
            let mut a: Vec<(i64, String)> = arrays.clone();
            let active = i32::from_le_bytes(st[0].data[76..80].try_into().unwrap());
            let c = (active as i64).div_euclid(70);
            a.retain(|(i, _)| if swap_for_y { *i <= c } else { *i >= c });
            a.sort_by_key(|(i, _)| if swap_for_y { -i } else { *i });
            let mut s = st[..3].to_vec();
            s.extend(a.iter().take(5).map(|(_, k)| m.acct(k)));
            let l = OwnedLeg::new(Kind::Dlmm, swap_for_y, s.clone(), if swap_for_y { s[1].key } else { s[2].key });
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
            let leg = AnyLeg::parse(&li, &clock, pda).unwrap().leg.unwrap();
            let (amap, pair) = ref_view(&s);
            let view = ref_dlmm::View { pair, arrays: &amap, over: None };
            let (mut eq, mut more) = (0, 0);
            let cap = leg.cap_in().unwrap();
            for x in sizes(&mut rng, cap) {
                if let (Ok(q), Ok(r)) = (leg.quote(x), ref_dlmm::quote(&view, swap_for_y, x, clock.unix_timestamp, false)) {
                    let d = (q.out as i128 - r.out as i128).unsigned_abs();
                    assert!(d <= q.out.max(r.out) as u128 / 8 + 2, "{name} x={x}: ours {} reference {}", q.out, r.out);
                    if q.out == r.out { eq += 1 } else { more += 1 }
                }
            }
            report.push(format!("DLMM {}… swap_for_y={swap_for_y}: cap {cap}, {eq} equal, {more} different (limit-order layers)", &name[..6]));
        }
        st.clear();
    }
    for r in &report { eprintln!("{r}"); }
}

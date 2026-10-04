//! Venue quotes: the PumpSwap program's own events, the DLMM fee vectors of docs/spec-dlmm.md, every DAMM v2 vector
//! in testdata/dammv2-vectors.json, and per-venue properties (DESIGN.md §6.1): monotone in the input, quote(0) is an
//! error, the output never exceeds the reserve, and the capacity is consistent (exact where it is closed form).
mod common;
use arbx_sizing::error::{Abort, DammWhy, PumpWhy, QuoteErr};
use arbx_sizing::venue::pumpswap::{self, PumpFees};
use arbx_sizing::venue::{dammv2, dlmm};
use arbx_sizing::{AnyLeg, Kind};
use common::*;

fn n(v: &serde_json::Value) -> u128 { v.as_str().map(|s| s.parse().unwrap()).unwrap_or_else(|| v.as_u64().unwrap() as u128) }
fn ni(v: &serde_json::Value) -> i128 { v.as_str().unwrap().parse().unwrap() }

/// Monotone where Ok; ZeroOut only below every Ok; TooLarge only above every Ok (feasibility is an interval).
fn check_monotone(q: &dyn Fn(u64) -> Result<arbx_sizing::Quote, QuoteErr>, xs: &mut Vec<u64>, out_max: u64, what: &str) {
    xs.sort();
    xs.dedup();
    let mut last_ok: Option<(u64, u64)> = None;
    let mut seen_large = None;
    for &x in xs.iter() {
        match q(x) {
            Ok(r) => {
                assert!(seen_large.is_none(), "{what}: Ok at {x} after TooLarge at {seen_large:?}");
                if let Some((px, po)) = last_ok { assert!(r.out >= po, "{what}: out({x}) = {} < out({px}) = {po}", r.out); }
                assert!(r.out <= out_max, "{what}: out {} above the reserve {out_max}", r.out);
                // only PumpSwap buy_exact_quote_in debits less than x, and then by one unit (REVIEW.md F2)
                assert!(r.spent <= x && r.spent as u128 + 1 >= x as u128, "{what}: spent {} for {x}", r.spent);
                last_ok = Some((x, r.out));
            }
            Err(QuoteErr::ZeroOut) => assert!(last_ok.is_none(), "{what}: ZeroOut at {x} after Ok at {last_ok:?}"),
            Err(QuoteErr::TooLarge) | Err(QuoteErr::Budget) => { seen_large.get_or_insert(x); }
            Err(QuoteErr::Abort(a)) => panic!("{what}: abort {a:?} at {x}"),
        }
    }
    assert_eq!(q(0), Err(QuoteErr::ZeroOut), "{what}: quote(0)");
}

fn sizes(rng: &mut Rng, hi: u64) -> Vec<u64> {
    let mut v: Vec<u64> = (0..120).map(|_| rng.log(1, hi)).collect();
    v.extend([1, 2, 3, 10, hi, hi / 2]);
    v
}

/* ------------------------------------------------ PumpSwap ------------------------------------------------ */

#[test]
fn pumpswap_matches_the_programs_events() {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/tests/data/pump-events.json");
    let ev: Vec<serde_json::Value> = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
    let (mut sells, mut bxqi, mut virt, mut skipped) = (0, 0, 0, 0);
    for e in &ev {
        let (b, q, v) = (n(&e["B"]) as u64, n(&e["Q"]) as u64, ni(&e["V"]));
        let fees = PumpFees { lp: n(&e["lp"]) as u64, protocol: n(&e["pr"]) as u64, creator: n(&e["cr"]) as u64 };
        if n(&e["cb"]) != 0 { skipped += 1; continue; } // cashback coins are aborted (DESIGN.md §2.1)
        let qv = (q as i128 + v) as u64;
        if v != 0 { virt += 1; }
        match e["kind"].as_str().unwrap() {
            "sell" => {
                let r = pumpswap::sell_quote(b, q, qv, &fees, n(&e["in"]) as u64).unwrap();
                assert_eq!(r.out as u128, n(&e["out"]), "{e}");
                sells += 1;
            }
            "buy_exact_quote_in" => {
                let r = pumpswap::buy_quote(b, qv, &fees, n(&e["in"]) as u64).unwrap();
                assert_eq!(r.out as u128, n(&e["out"]), "{e}");
                // the program's effective input: eff + fees(eff) == spendable on every recorded event
                assert_eq!(n(&e["user_in"]) + n(&e["lp_fee"]) + n(&e["pr_fee"]) + n(&e["cr_fee"]), n(&e["in"]), "{e}");
                bxqi += 1;
            }
            _ => skipped += 1, // `buy` (exact out) is not a sizing instruction
        }
    }
    eprintln!("pumpswap events: {sells} sells and {bxqi} buy_exact_quote_in exact ({virt} with virtual reserves); {skipped} skipped (exact-out buys, cashback)");
    assert!(sells >= 50 && bxqi >= 15);
}

fn pump_leg(spec: &PumpSpec, sell: bool) -> pumpswap::PumpLeg {
    let mut rng = Rng(7);
    let a = pump(&mut rng, spec);
    let l = OwnedLeg::pump(&a, sell);
    let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
    match any_leg(&l, &refs) { AnyLeg::Pump(p) => p, _ => unreachable!() }
}

#[test]
fn pumpswap_fee_selection() {
    // canonical, SOL quote: tiers by market cap = ⌊(Q+V)·supply/B⌋
    let base = PumpSpec::default();
    let mc = |s: &PumpSpec| ((s.quote as i128 + s.virt) as u128) * s.supply as u128 / s.base as u128;
    let mut s = base.clone();
    assert!(mc(&s) >= 420_000_000_000 && mc(&s) < 98_240_000_000_000);
    assert_eq!(pump_leg(&s, true).fees, PumpFees { lp: 20, protocol: 5, creator: 95 });
    s.quote = 1_000; // tiny market cap: tier 0
    assert_eq!(pump_leg(&s, true).fees, PumpFees { lp: 2, protocol: 93, creator: 30 });
    s.quote = 30_000_000_000_000; // top tier
    assert_eq!(pump_leg(&s, false).fees, PumpFees { lp: 20, protocol: 5, creator: 5 });
    // the virtual reserve counts in the market cap
    let mut s = base.clone(); s.quote = 1_000; s.virt = 300_000_000_000;
    assert_eq!(pump_leg(&s, true).fees, PumpFees { lp: 20, protocol: 5, creator: 95 });
    // not canonical: flat
    let mut s = base.clone(); s.canonical = false;
    assert_eq!(pump_leg(&s, true).fees, PumpFees { lp: 25, protocol: 5, creator: 0 });
    // configurable creator fee on the pool overrides; no coin creator zeroes it
    let mut s = base.clone(); s.creator_fee_bps = 200;
    assert_eq!(pump_leg(&s, true).fees.creator, 200);
    s.coin_creator = false;
    assert_eq!(pump_leg(&s, true).fees.creator, 0);
    // exotic quote: exotic flat fees (20, 5, 5); USDC: the stable tiers
    let mut s = base.clone(); s.quote_mint = [9u8; 32];
    assert_eq!(pump_leg(&s, true).fees, PumpFees { lp: 20, protocol: 5, creator: 5 });
    let mut s = base.clone(); s.quote_mint = arbx_sizing::layout::USDC;
    assert_eq!(pump_leg(&s, true).fees, PumpFees { lp: 20, protocol: 5, creator: 95 });
    // the real FeeConfig: tier 0 below 4.2e11, (20,5,95) just above, (20,5,5) at the top
    let m = Mainnet::load();
    let fc = m.acct("5PHirr8joyTMp9JMm6nW7hNDVyEYdkzDqazxPD7RaTjx");
    use pumpswap::{fee_config_fees, QuoteKind};
    assert_eq!(fee_config_fees(&fc.data, true, QuoteKind::SolLike, 0).unwrap(), PumpFees { lp: 2, protocol: 93, creator: 30 });
    assert_eq!(fee_config_fees(&fc.data, true, QuoteKind::SolLike, 420_000_000_000).unwrap(), PumpFees { lp: 20, protocol: 5, creator: 95 });
    assert_eq!(fee_config_fees(&fc.data, true, QuoteKind::SolLike, u128::MAX).unwrap(), PumpFees { lp: 20, protocol: 5, creator: 5 });
    assert_eq!(fee_config_fees(&fc.data, false, QuoteKind::SolLike, 0).unwrap(), PumpFees { lp: 25, protocol: 5, creator: 0 });
    assert_eq!(fee_config_fees(&fc.data, true, QuoteKind::Other, 0).unwrap(), PumpFees { lp: 20, protocol: 5, creator: 5 });
}

#[test]
fn pumpswap_aborts() {
    let mut rng = Rng(3);
    let abort = |f: &dyn Fn(&mut PumpAccts)| {
        let mut a = pump(&mut Rng(3), &PumpSpec::default());
        f(&mut a);
        let l = OwnedLeg::pump(&a, true);
        let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
        let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
        AnyLeg::parse(&li, &CLOCK, pda).unwrap().leg.err()
    };
    let _ = rng.next();
    assert_eq!(abort(&|_| {}), None);
    assert_eq!(abort(&|a| a.pool.data[243] = 1), Some(Abort::Pump(PumpWhy::Mayhem)));
    assert_eq!(abort(&|a| a.pool.data[244] = 1), Some(Abort::Pump(PumpWhy::Cashback)));
    assert_eq!(abort(&|a| a.global.data[56] = 1 << 4), Some(Abort::Pump(PumpWhy::Disabled)));
    assert_eq!(abort(&|a| a.global.data[56] = 1 << 3), None); // buy disabled, this is a sell
    assert_eq!(abort(&|a| put(&mut a.pool.data, 245, &(-400_000_000_000i128).to_le_bytes())), Some(Abort::Pump(PumpWhy::Virtual)));
    assert_eq!(abort(&|a| put(&mut a.pool.data, 245, &(u64::MAX as i128).to_le_bytes())), Some(Abort::Pump(PumpWhy::Virtual)));
    assert_eq!(abort(&|a| a.pool.data.truncate(269)), Some(Abort::Layout));
    assert_eq!(abort(&|a| a.global.data.push(0)), Some(Abort::Layout));
    assert_eq!(abort(&|a| put_u64(&mut a.pool.data, 261, 9_999)), Some(Abort::Pump(PumpWhy::FeeTotal)));
    // a Token-2022 base mint with a transfer fee
    assert_eq!(abort(&|a| { let k = a.base_mint.key; a.base_mint = mint(k, 1_000_000_000_000_000, true, Some(100)); }), Some(Abort::TransferFee));
    assert_eq!(abort(&|a| { let k = a.base_mint.key; a.base_mint = mint(k, 1_000_000_000_000_000, true, Some(0)); }), None);
}

#[test]
fn pumpswap_properties_and_exact_sell_capacity() {
    let mut rng = Rng(11);
    let mut capped = 0;
    for _ in 0..400 {
        let s = PumpSpec {
            base: rng.log(1_000, 1 << 60), quote: rng.log(1, 1 << 50), virt: if rng.chance(1, 2) { rng.log(1, 1 << 40) as i128 } else { 0 },
            supply: rng.log(1 << 20, 1 << 62), creator_fee_bps: if rng.chance(1, 4) { rng.range(1, 300) } else { 0 }, ..Default::default()
        };
        for sell in [true, false] {
            let l = pump_leg(&s, sell);
            let q = |x: u64| l.quote(x);
            let reserve = if sell { l.quote } else { l.base };
            let mut xs = sizes(&mut rng, if sell { l.base.saturating_mul(4) } else { l.qv.saturating_mul(4) });
            if let Some(c) = l.cap_in() { xs.extend([c.saturating_sub(1), c, c.saturating_add(1)]); }
            check_monotone(&q, &mut xs, reserve, if sell { "pump sell" } else { "pump buy" });
            if sell {
                if let Some(c) = l.cap_in() {
                    capped += 1;
                    assert!(!matches!(q(c), Err(QuoteErr::TooLarge)), "sell cap {c} too large");
                    if c < u64::MAX { assert_eq!(q(c + 1), Err(QuoteErr::TooLarge), "sell cap {c} not tight"); }
                }
            } else {
                assert_eq!(l.cap_in(), None);
            }
        }
    }
    assert!(capped > 100);
}

/* ------------------------------------------------- CPMM / AMM v4 ------------------------------------------------- */

#[test]
fn cpmm_and_ammv4_properties() {
    let mut rng = Rng(5);
    let (m0, m1) = ([1u8; 32], [2u8; 32]);
    for _ in 0..300 {
        let spec = arbx_sizing_spec(&mut rng);
        for zfo in [true, false] {
            let st = cpmm(&mut rng, &spec, m0, m1, zfo);
            let l = OwnedLeg::new(Kind::RayCpmm, zfo, st, if zfo { m0 } else { m1 });
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let leg = any_leg(&l, &refs);
            let r_out = if zfo { spec.r1 } else { spec.r0 };
            let mut xs = sizes(&mut rng, u64::MAX / 2);
            check_monotone(&|x| leg.quote(x), &mut xs, r_out, "cpmm");
            assert_eq!(leg.cap_in(), None);
        }
        let (coin, pc) = (rng.log(1000, 1 << 62), rng.log(1000, 1 << 62));
        let den = rng.range(100, 1_000_000);
        let num = rng.range(0, den - 1);
        let st = ammv4(&mut rng, coin, pc, num, den, m0, m1);
        for coin_in in [true, false] {
            let l = OwnedLeg::new(Kind::RayAmmV4, coin_in, st.clone(), if coin_in { m0 } else { m1 });
            let refs: Vec<_> = l.state.iter().map(|x| x.view()).collect();
            let leg = any_leg(&l, &refs);
            let mut xs = sizes(&mut rng, u64::MAX);
            check_monotone(&|x| leg.quote(x), &mut xs, if coin_in { pc } else { coin }, "ammv4");
        }
    }
}

fn arbx_sizing_spec(rng: &mut Rng) -> CpmmSpec {
    CpmmSpec { r0: rng.log(1000, 1 << 62), r1: rng.log(1000, 1 << 62), trade: rng.range(0, 30_000), creator: rng.range(0, 10_000),
        enable_creator: rng.chance(1, 2), creator_on: rng.range(0, 2) as u8, owed0: rng.range(0, 1 << 20), owed1: rng.range(0, 1 << 20) }
}

#[test]
fn cpmm_fee_rules() {
    use arbx_sizing::venue::cpmm;
    let mut rng = Rng(9);
    let (m0, m1) = ([1u8; 32], [2u8; 32]);
    let spec = CpmmSpec { r0: 1_000_000_000, r1: 5_000_000_000, trade: 2_500, creator: 500, enable_creator: true, creator_on: 0, owed0: 7, owed1: 9 };
    let st = cpmm(&mut rng, &spec, m0, m1, true);
    let p = cpmm::parse(&st[0].data, &st[1].data, spec.r0 + 7, spec.r1 + 9, true, CLOCK.unix_timestamp).unwrap();
    assert_eq!((p.r_in, p.r_out, p.fee_in, p.fee_out), (spec.r0, spec.r1, 3_000, 0), "creator fee on the input: one summed rate");
    let x = 1_000_001u64;
    let net = x as u128 - (x as u128 * 3_000).div_ceil(1_000_000);
    assert_eq!(p.quote(x).unwrap().out as u128, net * spec.r1 as u128 / (spec.r0 as u128 + net));
    // creator fee only on token1, selling token0: charged on the output
    let s2 = CpmmSpec { creator_on: 2, ..spec };
    let st = cpmm(&mut rng, &s2, m0, m1, true);
    let p = cpmm::parse(&st[0].data, &st[1].data, spec.r0 + 7, spec.r1 + 9, true, CLOCK.unix_timestamp).unwrap();
    assert_eq!((p.fee_in, p.fee_out), (2_500, 500));
    let net = x as u128 - (x as u128 * 2_500).div_ceil(1_000_000);
    let gross = net * spec.r1 as u128 / (spec.r0 as u128 + net);
    assert_eq!(p.quote(x).unwrap().out as u128, gross - (gross * 500).div_ceil(1_000_000));
    // swap disabled, not open, owed above the vault, bad creator_fee_on
    let mut d = st[0].data.clone(); d[329] = 4;
    assert_eq!(cpmm::parse(&d, &st[1].data, 1 << 40, 1 << 40, true, 0), Err(Abort::Cpmm(arbx_sizing::error::CpmmWhy::SwapDisabled)));
    let mut d = st[0].data.clone(); put_u64(&mut d, 373, CLOCK.unix_timestamp as u64 + 1);
    assert_eq!(cpmm::parse(&d, &st[1].data, 1 << 40, 1 << 40, true, CLOCK.unix_timestamp), Err(Abort::Cpmm(arbx_sizing::error::CpmmWhy::NotOpen)));
    assert!(cpmm::parse(&d, &st[1].data, 1 << 40, 1 << 40, true, CLOCK.unix_timestamp + 1).is_ok());
    assert_eq!(cpmm::parse(&st[0].data, &st[1].data, 5, 1 << 40, true, 0), Err(Abort::Cpmm(arbx_sizing::error::CpmmWhy::OwedExceedsVault)));
    let mut d = st[0].data.clone(); d[389] = 3;
    assert_eq!(cpmm::parse(&d, &st[1].data, 1 << 40, 1 << 40, true, 0), Err(Abort::Cpmm(arbx_sizing::error::CpmmWhy::CreatorFeeOn)));
}

/* ------------------------------------------------------ DLMM ------------------------------------------------------ */

fn dlmm_leg_of(spec: &DlmmSpec, swap_for_y: bool, clock: &arbx_sizing::Clock) -> (Vec<Acct>, Result<(), Abort>) {
    let mut rng = Rng(1);
    let (p, mx, my, arrays) = dlmm(&mut rng, spec, [3u8; 32], [4u8; 32]);
    let st = dlmm_state(&p, &mx, &my, &arrays, swap_for_y);
    let data: Vec<&[u8]> = st[3..].iter().map(|a| &a.data[..]).collect();
    let r = dlmm::parse(&st[0].data, &data, swap_for_y, clock).map(|_| ());
    (st, r)
}

fn with_dlmm<R>(st: &[Acct], swap_for_y: bool, clock: &arbx_sizing::Clock, f: impl FnOnce(&dlmm::DlmmLeg) -> R) -> R {
    let data: Vec<&[u8]> = st[3..].iter().map(|a| &a.data[..]).collect();
    let leg = dlmm::parse(&st[0].data, &data, swap_for_y, clock).unwrap();
    f(&leg)
}

#[test]
fn dlmm_fee_vectors_from_the_spec() {
    // vfc 40000, bin_step 10, va 350000 → variable 4,900,000; base 10000·10·10 = 1,000,000 → total 5,900,000
    let spec = DlmmSpec { bin_step: 10, base_factor: 10_000, vfc: 40_000, max_va: 10_000_000, v_ref: 350_000, idx_ref: 0, active: 0,
        last_ts: CLOCK.unix_timestamp, filter: 30, decay: 600, bins: vec![(0, 1000, 1000, (0, 0, 0))], ..Default::default() };
    let (st, r) = dlmm_leg_of(&spec, true, &CLOCK);
    r.unwrap();
    with_dlmm(&st, true, &CLOCK, |l| {
        assert_eq!(l.p.base_rate, 1_000_000);
        assert_eq!(l.rate(0), Some(5_900_000));
    });
    // update_references({va 300000, ref 123, idx 500, ts 1000, fp 30, dp 600, rf 5000}, active 510, now 1030) → {150000, 510}
    let spec = DlmmSpec { bin_step: 10, base_factor: 10_000, vfc: 0, va: 300_000, v_ref: 123, idx_ref: 500, last_ts: 1000, filter: 30, decay: 600,
        reduction: 5000, active: 510, bins: vec![(510, 1000, 1000, (0, 0, 0))], ..Default::default() };
    let clock = arbx_sizing::Clock { unix_timestamp: 1030, ..CLOCK };
    let (st, _) = dlmm_leg_of(&spec, true, &clock);
    with_dlmm(&st, true, &clock, |l| { assert_eq!((l.p.v_ref, l.p.idx_ref), (150_000, 510)); });
    // elapsed < filter: references kept; elapsed ≥ decay: reference 0
    let c2 = arbx_sizing::Clock { unix_timestamp: 1029, ..CLOCK };
    with_dlmm(&st, true, &c2, |l| { assert_eq!((l.p.v_ref, l.p.idx_ref), (123, 500)); });
    let c3 = arbx_sizing::Clock { unix_timestamp: 1600, ..CLOCK };
    with_dlmm(&st, true, &c3, |l| { assert_eq!((l.p.v_ref, l.p.idx_ref), (0, 510)); });
    // accumulator(ref 1218, idx 484, bin 486) = 21218: rate at bin 486 with vfc so the variable part is visible
    let spec = DlmmSpec { bin_step: 10, base_factor: 10_000, vfc: 40_000, max_va: 10_000_000, v_ref: 1218, idx_ref: 484, active: 486,
        last_ts: CLOCK.unix_timestamp, filter: 30, bins: vec![(486, 1, 1, (0, 0, 0))], ..Default::default() };
    let (st, _) = dlmm_leg_of(&spec, true, &CLOCK);
    with_dlmm(&st, true, &CLOCK, |l| {
        let va: u128 = 21_218;
        let var = (40_000 * (va * 10) * (va * 10)).div_ceil(100_000_000_000);
        assert_eq!(l.rate(486), Some(1_000_000 + var));
    });
}

/// a random pair: bins around the active one (with gaps, empty arrays, limit orders), random fee state
fn random_dlmm(rng: &mut Rng, lo_orders: bool) -> DlmmSpec {
    let bin_step = [1u16, 10, 25, 100, 200][rng.range(0, 4) as usize];
    let active = rng.range(0, 1000) as i32 - 500;
    let mut bins = vec![];
    for id in active - 180..=active + 180 {
        if rng.chance(1, 3) { continue; }
        // around the active bin both sides; below it Y only, above it X only (DLMM's shape)
        let amt = |rng: &mut Rng| rng.log(1, 1 << 40);
        let (ax, ay) = if id < active { (0, amt(rng)) } else if id > active { (amt(rng), 0) } else { (amt(rng), amt(rng)) };
        let lo = if lo_orders && rng.chance(1, 4) { (rng.log(1, 1 << 36), rng.log(1, 1 << 30), rng.range(0, 1) as u8) } else { (0, 0, 0) };
        bins.push((id, ax, ay, lo));
    }
    DlmmSpec {
        bin_step, base_factor: rng.range(1000, 30_000) as u16, power: 0, vfc: rng.range(0, 50_000) as u32, max_va: rng.range(10_000, 400_000) as u32,
        va: rng.range(0, 300_000) as u32, v_ref: rng.range(0, 100_000) as u32, idx_ref: active + rng.range(0, 40) as i32 - 20,
        last_ts: CLOCK.unix_timestamp - rng.range(0, 2000) as i64, filter: 300, decay: 1200, reduction: 5000, active,
        function_type: [0u8, 1, 2][rng.range(0, 2) as usize], collect_fee_mode: rng.range(0, 1) as u8,
        // the pair's own bin-id bounds, sometimes a few bins from the active one (REVIEW.md F8)
        min_bin: if rng.chance(1, 4) { active - rng.range(0, 60) as i32 } else { -443_636 },
        max_bin: if rng.chance(1, 4) { active + rng.range(0, 60) as i32 } else { 443_636 },
        bins,
    }
}

#[test]
fn dlmm_properties() {
    let mut rng = Rng(21);
    let (mut capped, mut walked_arrays) = (0, 0);
    for case in 0..300 {
        let spec = random_dlmm(&mut rng, case % 2 == 0);
        for swap_for_y in [true, false] {
            let (st, r) = dlmm_leg_of(&spec, swap_for_y, &CLOCK);
            if r.is_err() { continue; }
            with_dlmm(&st, swap_for_y, &CLOCK, |l| {
                let total: u128 = { let mut w = l.walker(); let mut t = 0; while let Some(b) = w.next_bin() { t += b.total(); } t };
                let cap = l.cap_in().unwrap();
                let mut xs = sizes(&mut rng, cap.saturating_mul(2).max(10));
                xs.extend([cap.saturating_sub(1), cap, cap.saturating_add(1), cap.saturating_add(cap / 1000 + 10)]);
                check_monotone(&|x| l.quote(x), &mut xs, total.min(u64::MAX as u128) as u64, "dlmm");
                if cap > 0 {
                    capped += 1;
                    assert!(l.quote(cap).is_ok() || l.quote(cap) == Err(QuoteErr::ZeroOut), "dlmm cap {cap}: {:?}", l.quote(cap));
                    // a few units above the drain sum can still be absorbed as fee by the last bin; far above cannot
                    assert_eq!(l.quote(cap.saturating_add(cap / 1000 + 10)), Err(QuoteErr::TooLarge));
                }
                let mut w = l.walker();
                let mut arrays = std::collections::BTreeSet::new();
                while let Some(b) = w.next_bin() { arrays.insert(dlmm::array_index(b.id)); }
                if arrays.len() > 1 { walked_arrays += 1; }
            });
        }
    }
    eprintln!("dlmm: {capped} legs with a cap, {walked_arrays} walks crossing arrays");
    assert!(capped > 200 && walked_arrays > 100);
}

#[test]
fn dlmm_bitmap_jump_and_limit_orders() {
    // active bin 5 in array 0 empty; the next array with liquidity (by the bitmap) is −2 for X→Y: the walk shifts
    // to bin −2·70 + 69 = −71 and drains from there. Array −1 is passed but empty (bit 0) and is skipped.
    let spec = DlmmSpec { bin_step: 100, base_factor: 10_000, vfc: 0, active: 5, idx_ref: 5, last_ts: CLOCK.unix_timestamp,
        bins: vec![(5, 0, 0, (0, 0, 0)), (-71, 0, 1_000_000, (0, 0, 0)), (-72, 0, 2_000_000, (0, 0, 0)), (-30, 0, 0, (0, 0, 0))], ..Default::default() };
    let (st, r) = dlmm_leg_of(&spec, true, &CLOCK);
    r.unwrap();
    with_dlmm(&st, true, &CLOCK, |l| {
        let mut w = l.walker();
        assert_eq!(w.next_bin().map(|b| b.id), Some(-71));
        assert_eq!(w.next_bin().map(|b| b.id), Some(-72));
        assert_eq!(w.next_bin(), None);
        let cap = l.cap_in().unwrap();
        assert!(l.quote(cap).is_ok());
        assert_eq!(l.quote(cap + cap / 100 + 10), Err(QuoteErr::TooLarge));
    });
    // a bid-side limit order (ask 0) adds Y capacity for X→Y only when the pair supports limit orders
    let mut spec = DlmmSpec { bin_step: 100, base_factor: 10_000, vfc: 0, active: 0, idx_ref: 0, last_ts: CLOCK.unix_timestamp,
        bins: vec![(0, 0, 1_000_000, (500_000, 250_000, 0))], ..Default::default() };
    for (ft, want) in [(2u8, 1_750_000u128), (1, 1_000_000)] {
        spec.function_type = ft;
        let (st, _) = dlmm_leg_of(&spec, true, &CLOCK);
        with_dlmm(&st, true, &CLOCK, |l| {
            let mut w = l.walker();
            assert_eq!(w.next_bin().unwrap().total(), want, "function_type {ft}");
        });
    }
    // fee on the output (collect_fee_mode 1, X→Y): the user gets out − ⌈out·rate/1e9⌉ and the input is not charged
    spec.function_type = 2;
    spec.collect_fee_mode = 1;
    let (st, _) = dlmm_leg_of(&spec, true, &CLOCK);
    with_dlmm(&st, true, &CLOCK, |l| {
        assert!(!l.p.fee_on_input);
        let rate = l.rate(0).unwrap();
        let x = 100_000u64; // price 1.0: out before fee = x
        let p = dlmm_price(100, 0);
        let gross = (x as u128 * p) >> 64;
        assert_eq!(l.quote(x).unwrap().out as u128, gross - (gross * rate).div_ceil(1_000_000_000));
    });
    // Y→X with mode 1: fee on the input
    let (st, _) = dlmm_leg_of(&spec, false, &CLOCK);
    with_dlmm(&st, false, &CLOCK, |l| assert!(l.p.fee_on_input));
}

#[test]
fn dlmm_aborts_and_caps() {
    let base = DlmmSpec { active: 0, last_ts: CLOCK.unix_timestamp, bins: vec![(0, 10, 10, (0, 0, 0))], ..Default::default() };
    let parse_with = |f: &dyn Fn(&mut Vec<u8>)| {
        let (mut st, _) = dlmm_leg_of(&base, true, &CLOCK);
        f(&mut st[0].data);
        let data: Vec<&[u8]> = st[3..].iter().map(|a| &a.data[..]).collect();
        dlmm::parse(&st[0].data, &data, true, &CLOCK).err()
    };
    use arbx_sizing::error::DlmmWhy;
    assert_eq!(parse_with(&|_| {}), None);
    assert_eq!(parse_with(&|d| d[82] = 1), Some(Abort::Dlmm(DlmmWhy::Status)));
    assert_eq!(parse_with(&|d| d[882] = 2), Some(Abort::Layout));
    assert_eq!(parse_with(&|d| d[35] = 3), Some(Abort::Dlmm(DlmmWhy::FunctionType)));
    assert_eq!(parse_with(&|d| d[36] = 2), Some(Abort::Dlmm(DlmmWhy::CollectFeeMode)));
    assert_eq!(parse_with(&|d| put_u64(d, 816, CLOCK.slot + 1)), Some(Abort::Dlmm(DlmmWhy::NotActive)));
    assert_eq!(parse_with(&|d| { put_u64(d, 816, CLOCK.slot + 1); d[86] = 1; }), None); // timestamp activation, long past
    assert_eq!(parse_with(&|d| d[86] = 2), Some(Abort::Dlmm(DlmmWhy::ActivationType)));
    // an active array index outside the pair's bitmap (extension needed) caps the domain at once
    let far = DlmmSpec { active: 600 * 70, idx_ref: 600 * 70, bins: vec![(600 * 70, 10, 10, (0, 0, 0))], ..base.clone() };
    let (st, _) = dlmm_leg_of(&far, true, &CLOCK);
    with_dlmm(&st, true, &CLOCK, |l| { assert_eq!(l.quote(1), Err(QuoteErr::TooLarge)); assert_eq!(l.cap_in(), Some(0)); });
    // a needed array not passed caps there
    let gap = DlmmSpec { bins: vec![(0, 0, 1000, (0, 0, 0)), (-140, 0, 1000, (0, 0, 0))], ..base.clone() };
    let (mut st, _) = dlmm_leg_of(&gap, true, &CLOCK);
    st.truncate(4); // only array 0
    with_dlmm(&st, true, &CLOCK, |l| {
        let cap = l.cap_in().unwrap();
        assert!(cap > 0 && l.quote(cap).is_ok());
        assert_eq!(l.quote(cap * 2), Err(QuoteErr::TooLarge));
    });
}

/* ---------------------------------------------------- DAMM v2 ---------------------------------------------------- */

fn vectors() -> serde_json::Value {
    let path = concat!(env!("CARGO_MANIFEST_DIR"), "/../../testdata/dammv2-vectors.json");
    serde_json::from_str(&std::fs::read_to_string(path).expect("testdata/dammv2-vectors.json")).unwrap()
}

/// Every TypeScript quote vector, through both the full port and the on-chain leg path
#[test]
fn dammv2_quote_vectors() {
    let v = vectors();
    let pools = v["pools"].as_object().unwrap();
    let (mut ok, mut refused, mut post) = (0, 0, 0);
    for (k, q) in v["quotes"].as_array().unwrap().iter().enumerate() {
        let name = q["pool"].as_str().unwrap();
        let raw = b64(pools[name]["b64"].as_str().unwrap());
        let mut p = dammv2::decode(&raw).unwrap();
        let t22ok = q["t22ok"].as_bool().unwrap();
        p.transfer_fee_known_zero = t22ok;
        let a_to_b = q["aToB"].as_bool().unwrap();
        let (amount, slot, now) = (n(&q["amountIn"]) as u64, n(&q["slot"]) as u64, n(&q["now"]) as i64);
        let clock = arbx_sizing::Clock { slot, unix_timestamp: now, epoch: 0 };
        let full = dammv2::swap_exact_in(&p, a_to_b, amount, slot, now);
        // the leg path that prices the limiter (`parse` itself refuses a limiter in force: REVIEW.md F5)
        let lean = dammv2::parse_with_limiter(&raw, a_to_b, t22ok, &clock).map_err(QuoteErr::Abort).and_then(|l| l.quote(amount));
        if let Ok(l) = dammv2::parse_with_limiter(&raw, a_to_b, t22ok, &clock) {
            let strict = dammv2::parse(&raw, a_to_b, t22ok, &clock);
            if l.fee_fixed.is_none() { assert_eq!(strict.unwrap_err(), Abort::Damm(arbx_sizing::error::DammWhy::RateLimiter)); } else { assert_eq!(strict, Ok(l)); }
        }
        let ctx = format!("#{k} {name} {q}");
        if q["exact"].as_bool().unwrap() {
            let (out, after) = full.unwrap_or_else(|e| panic!("refused {e:?}: {ctx}"));
            assert_eq!(out as u128, n(&q["out"]), "out {ctx}");
            assert_eq!(lean.map(|r| r.out), Ok(out), "leg path {ctx}");
            assert_eq!(dammv2::fee_numerator(&p, a_to_b, amount, slot, now).map(|f| f as u128), Some(n(&q["feeNumerator"])), "fee {ctx}");
            if p.collect_fee_mode != dammv2::COLLECT_COMPOUNDING { assert_eq!(after.sqrt_price, n(&q["nextSqrtPrice"]), "sqrt {ctx}"); }
            let ps = &q["post"];
            if !ps.is_null() {
                assert_eq!(after.sqrt_price, n(&ps["sqrtPrice"]), "post sqrt {ctx}");
                assert_eq!(after.token_a_amount as u128, n(&ps["tokenAAmount"]), "post a {ctx}");
                assert_eq!(after.token_b_amount as u128, n(&ps["tokenBAmount"]), "post b {ctx}");
                assert_eq!(after.dynamic_fee.volatility_accumulator, n(&ps["volatilityAccumulator"]), "post va {ctx}");
                assert_eq!(after.dynamic_fee.last_update_timestamp as u128, n(&ps["lastUpdateTimestamp"]), "post ts {ctx}");
                post += 1;
            }
            ok += 1;
        } else {
            assert!(full.is_err(), "full port quotes {full:?} where TS refuses: {ctx}");
            assert!(lean.is_err(), "leg path quotes {lean:?} where TS refuses: {ctx}");
            refused += 1;
        }
    }
    eprintln!("dammv2 TS vectors: {ok} exact ({post} with post-state), {refused} refusals, both paths identical");
    assert!(ok > 1000 && refused > 100);
}

/// Real swaps captured on mainnet: the pre-state, the swap's own event, and (where present) the whole post-state
#[test]
fn dammv2_chain_vectors() {
    let v = vectors();
    let (mut checked, mut with_post) = (0, 0);
    for c in v["chain"].as_array().unwrap() {
        if n(&c["swapMode"]) == 2 || n(&c["amountLeft"]) != 0 { continue; } // exact-out / partial fills: not sizing paths
        let raw = b64(c["pre"].as_str().unwrap());
        let mut pre = dammv2::decode(&raw).unwrap();
        pre.transfer_fee_known_zero = true;
        let a_to_b = n(&c["tradeDirection"]) == 0;
        let (slot, now) = (n(&c["slot"]) as u64, n(&c["currentTimestamp"]) as i64);
        let amount = n(&c["includedFeeInputAmount"]) as u64;
        let (out, after) = dammv2::swap_exact_in(&pre, a_to_b, amount, slot, now).unwrap();
        assert_eq!(out as u128, n(&c["outputAmount"]));
        assert_eq!(after.sqrt_price, n(&c["nextSqrtPrice"]));
        assert_eq!((after.token_a_amount as u128, after.token_b_amount as u128), (n(&c["reserveA"]), n(&c["reserveB"])));
        let leg = dammv2::parse(&raw, a_to_b, true, &arbx_sizing::Clock { slot, unix_timestamp: now, epoch: 0 }).unwrap();
        assert_eq!(leg.quote(amount).unwrap().out, out);
        if let Some(p) = c["post"].as_str() {
            let mut real = dammv2::decode(&b64(p)).unwrap();
            real.transfer_fee_known_zero = true;
            assert_eq!(after, real);
            with_post += 1;
        }
        checked += 1;
    }
    eprintln!("dammv2 chain vectors: {checked} exact-in swaps identical ({with_post} whole post-swap accounts)");
    assert!(checked > 50);
}

/// Monotone, quote(0), and the exact range-exit capacity on every vector pool, both directions, at several clocks
#[test]
fn dammv2_properties_and_exact_capacity() {
    let v = vectors();
    let mut rng = Rng(33);
    let (mut tight, mut pools_n) = (0, 0);
    for (name, pv) in v["pools"].as_object().unwrap() {
        let raw = b64(pv["b64"].as_str().unwrap());
        let p = dammv2::decode(&raw).unwrap();
        pools_n += 1;
        for a_to_b in [true, false] {
            for dt in [0i64, 30, 600, 100_000] {
                let clock = arbx_sizing::Clock { slot: 452_967_433 + dt as u64 * 2, unix_timestamp: 1_791_039_568 + dt, epoch: 0 };
                let Ok(leg) = dammv2::parse(&raw, a_to_b, true, &clock) else { continue };
                let out_max = if a_to_b { leg.s.token_b_amount } else { leg.s.token_a_amount };
                let mut xs = sizes(&mut rng, u64::MAX);
                let cap = leg.cap_in();
                if let Some(c) = cap { xs.extend([c.saturating_sub(1), c, c.saturating_add(1)]); }
                check_monotone(&|x| leg.quote(x), &mut xs, out_max, &format!("dammv2 {name}"));
                if let Some(c) = cap {
                    if c < u64::MAX {
                        // past the range end: always TooLarge; at it: never a range violation (a reserve can still bind)
                        assert_eq!(leg.quote(c + 1), Err(QuoteErr::TooLarge), "{name} cap {c} not tight");
                        if leg.quote(c).is_ok() { tight += 1; }
                    }
                }
                if leg.fee_fixed.is_none() { assert!(leg.model().is_none()); }
            }
        }
        let _ = p;
    }
    eprintln!("dammv2: {pools_n} pools; {tight} (pool, direction, clock) caps exactly tight");
    assert!(tight > 10);
    let _ = DammWhy::RateLimiter;
}

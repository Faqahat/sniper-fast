//! Fx against f64 / u128 references, U256 against num-bigint, the integer helpers (DESIGN.md §6.1).
use arbx_sizing::math::{isqrt_u128, isqrt_u64, mul_shr64, shl64_div};
use arbx_sizing::u256::U256;
use arbx_sizing::Fx;
use num_bigint::BigUint;
use proptest::prelude::*;

fn f(x: Fx) -> f64 { let (m, e) = x.parts(); m as f64 * 2f64.powi(e) }
fn rel(a: f64, b: f64) -> f64 { if a == b { 0.0 } else { (a - b).abs() / a.abs().max(b.abs()) } }
const TOL: f64 = 1.0 / (1u64 << 29) as f64; // 2^-29 relative

fn big(x: U256) -> BigUint { let mut v = BigUint::from(0u8); for i in (0..4).rev() { v = (v << 64u32) + BigUint::from(x.0[i]); } v }
fn from_big(v: &BigUint) -> Option<U256> {
    let d = v.to_u64_digits();
    if d.len() > 4 { return None; }
    let mut r = [0u64; 4];
    for (i, x) in d.iter().enumerate() { r[i] = *x; }
    Some(U256(r))
}
fn u256_strategy() -> impl Strategy<Value = U256> {
    (any::<[u64; 4]>(), 0u32..=256).prop_map(|(l, bits)| U256(l).shr(256 - bits))
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(4000))]

    #[test]
    fn fx_ops_match_f64(a in 1u64.., b in 1u64.., sa in -40i32..40, sb in -40i32..40) {
        let (x, y) = (Fx::from_u64(a).shl(sa), Fx::from_u64(b).shl(sb));
        let (fa, fb) = (a as f64 * 2f64.powi(sa), b as f64 * 2f64.powi(sb));
        prop_assert!(rel(f(x), fa) <= TOL);
        prop_assert!(rel(f(x.mul(y)), fa * fb) <= 2.0 * TOL);
        prop_assert!(rel(f(x.div(y)), fa / fb) <= 2.0 * TOL);
        prop_assert!(rel(f(x.add(y)), fa + fb) <= 2.0 * TOL);
        prop_assert!(rel(f(x.sqrt()), fa.sqrt()) <= 2.0 * TOL);
        // subtraction: absolute error relative to the operands
        let d = f(x.sub(y));
        let want = (fa - fb).max(0.0);
        prop_assert!((d - want).abs() <= 3.0 * TOL * fa.max(fb), "{} - {} = {} want {}", fa, fb, d, want);
        prop_assert_eq!(x < y, f(x) < f(y) || (rel(f(x), f(y)) == 0.0 && x < y));
    }

    #[test]
    fn fx_u128_conversion_and_floor(v in any::<u128>()) {
        let x = Fx::from_u128(v);
        prop_assert!(rel(f(x), v as f64) <= TOL);
        // floor is exact for values with at most 32 significant bits and never above the value
        prop_assert!(x.floor_u128() <= v);
        prop_assert!(v - x.floor_u128() <= (v >> 30).max(0));
        if v <= u32::MAX as u128 { prop_assert_eq!(x.floor_u128(), v); prop_assert_eq!(x.floor_u64() as u128, v); }
        if v > u64::MAX as u128 { prop_assert_eq!(x.floor_u64(), u64::MAX); }
    }

    #[test]
    fn fx_identities(a in 1u64.., b in 1u64..) {
        let (x, y) = (Fx::from_u64(a), Fx::from_u64(b));
        prop_assert!(rel(f(x.mul(y).div(y)), f(x)) <= 3.0 * TOL);
        prop_assert!(rel(f(x.sqrt().mul(x.sqrt())), f(x)) <= 3.0 * TOL);
        prop_assert!(rel(f(x.add(y).sub(y)), f(x)) <= 4.0 * TOL * (1.0 + b as f64 / a as f64));
        prop_assert_eq!(x.mul(Fx::ONE), x);
        prop_assert_eq!(x.div(Fx::ONE), x);
    }

    #[test]
    fn u256_matches_bigint(a in u256_strategy(), b in u256_strategy(), sh in 0u32..300) {
        let (ba, bb) = (big(a), big(b));
        prop_assert_eq!(a.checked_add(b), from_big(&(&ba + &bb)));
        prop_assert_eq!(a.checked_sub(b), if ba >= bb { from_big(&(&ba - &bb)) } else { None });
        prop_assert_eq!(a.checked_mul(b), from_big(&(&ba * &bb)));
        if !b.is_zero() {
            let (q, r) = a.div_rem(b).unwrap();
            prop_assert_eq!(big(q), &ba / &bb);
            prop_assert_eq!(big(r), &ba % &bb);
            let up = a.div_round(b, true).unwrap();
            prop_assert_eq!(big(up), (&ba + &bb - 1u8) / &bb);
        } else {
            prop_assert!(a.div_rem(b).is_none());
        }
        prop_assert_eq!(big(a.shr(sh)), &ba >> sh);
        prop_assert_eq!(a.shl(sh), if sh < 256 { from_big(&(&ba << sh)) } else if a.is_zero() { Some(a) } else { None });
        let s = a.isqrt().unwrap();
        prop_assert_eq!(big(s), ba.sqrt());
        prop_assert_eq!(a.low_bits_nonzero(sh.min(256)), (&ba % (BigUint::from(1u8) << sh.min(256))) != BigUint::from(0u8));
    }

    #[test]
    fn u256_mul128(a in any::<u128>(), b in any::<u128>()) {
        prop_assert_eq!(big(U256::mul128(a, b)), BigUint::from(a) * BigUint::from(b));
    }

    #[test]
    fn q64_helpers(a in any::<u64>(), p in 1u128..) {
        let (ba, bp) = (BigUint::from(a), BigUint::from(p));
        let prod = &ba * &bp;
        let want = &prod >> 64u32;
        let up = if (&prod % (BigUint::from(1u8) << 64u32)) != BigUint::from(0u8) { &want + 1u8 } else { want.clone() };
        prop_assert_eq!(mul_shr64(a as u128, p, false).map(BigUint::from), if want.bits() <= 128 { Some(want) } else { None });
        prop_assert_eq!(mul_shr64(a as u128, p, true).map(BigUint::from), if up.bits() <= 128 { Some(up) } else { None });
        let n = &ba << 64u32;
        prop_assert_eq!(BigUint::from(shl64_div(a as u128, p, false).unwrap()), &n / &bp);
        prop_assert_eq!(BigUint::from(shl64_div(a as u128, p, true).unwrap()), (&n + &bp - 1u8) / &bp);
        prop_assert!(mul_shr64(u64::MAX as u128 + 1, p, false).is_none());
    }

    #[test]
    fn integer_square_roots(n in any::<u64>(), m in any::<u128>()) {
        let s = isqrt_u64(n) as u128;
        prop_assert!(s * s <= n as u128 && (s + 1) * (s + 1) > n as u128);
        let t = isqrt_u128(m);
        prop_assert!(t.checked_mul(t).map_or(false, |x| x <= m));
        prop_assert!((t + 1).checked_mul(t + 1).map_or(true, |x| x > m));
    }
}

#[test]
fn fx_edges() {
    assert!(Fx::ZERO.is_zero() && Fx::from_u64(0).is_zero());
    assert_eq!(Fx::from_u64(1).floor_u64(), 1);
    assert_eq!(Fx::from_u64(u64::MAX).floor_u64() >> 32, (u64::MAX >> 32)); // top 32 bits kept
    assert!(Fx::INF > Fx::from_u128(u128::MAX));
    assert_eq!(Fx::from_u64(5).div(Fx::ZERO), Fx::INF);
    assert_eq!(Fx::from_u64(5).div(Fx::INF), Fx::ZERO);
    assert_eq!(Fx::from_u64(5).sub(Fx::from_u64(7)), Fx::ZERO);
    assert_eq!(Fx::INF.floor_u64(), u64::MAX);
    assert_eq!(Fx::from_u64(3).shl(-2).floor_u64(), 0);
    assert_eq!(Fx::from_u64(4).sqrt().floor_u64(), 2);
    assert_eq!(Fx::from_u64(1 << 40).sqrt().floor_u64(), 1 << 20);
    // u256 edge values from the reference tests
    assert_eq!(U256::mul128(u128::MAX, u128::MAX), U256([1, 0, u64::MAX - 1, u64::MAX]));
    assert_eq!(U256([u64::MAX; 4]).isqrt(), Some(U256([u64::MAX, u64::MAX, 0, 0])));
    let max = U256([u64::MAX; 4]);
    assert_eq!(max.div_rem(max).unwrap(), (U256::ONE, U256::ZERO));
}

/// Knuth D's rare add-back and qhat-correction paths (as the reference's own test)
#[test]
fn u256_division_corner_paths() {
    let mut s = 0x9E3779B97F4A7C15u64;
    let mut next = || { s ^= s >> 12; s ^= s << 25; s ^= s >> 27; s.wrapping_mul(0x2545F4914F6CDD1D) };
    let edge = [0u64, 1, (1 << 63) - 1, 1 << 63, u64::MAX];
    for _ in 0..30_000 {
        let mut limb = || { let r = next(); if r % 3 == 0 { next() } else { edge[(next() % 5) as usize] } };
        let n = U256([limb(), limb(), limb(), limb()]);
        let top = if limb() % 2 == 0 { 0 } else { limb() };
        let d = U256([limb(), limb(), limb(), top]);
        if d.is_zero() { continue; }
        let (q, r) = n.div_rem(d).unwrap();
        assert_eq!((big(q), big(r)), (big(n) / big(d), big(n) % big(d)), "n={n:?} d={d:?}");
    }
    for _ in 0..5_000 {
        let d = U256([next(), next(), u64::MAX - (next() % 3), 0]);
        let k = U256::from_u128(next() as u128);
        let n = d.checked_mul(k).unwrap().checked_sub(U256::from_u128(1 + next() as u128 % 5)).unwrap_or(d);
        let (q, r) = n.div_rem(d).unwrap();
        assert_eq!((big(q), big(r)), (big(n) / big(d), big(n) % big(d)));
    }
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(20000))]
    /// the small-divisor long division equals u128 division for every divisor width
    #[test]
    fn divrem_u64_matches_u128(a in any::<u128>(), d in 1u64.., shift in 0u32..64) {
        let d = (d >> shift).max(1);
        let (q, r) = arbx_sizing::math::divrem_u64(a, d).unwrap();
        prop_assert_eq!(q, a / d as u128);
        prop_assert_eq!(r as u128, a % d as u128);
        let b = d as u128;
        prop_assert_eq!(arbx_sizing::math::ceil_div(a, b).unwrap(), a / b + (a % b != 0) as u128);
        prop_assert_eq!(arbx_sizing::math::div(a, b).unwrap(), a / b);
        let wide = (d as u128) << (shift + 1);
        prop_assert_eq!(arbx_sizing::math::ceil_div(a, wide).unwrap(), a / wide + (a % wide != 0) as u128);
    }
}

/// DESIGN.md §4.8: the per-leg parsed state stays small (the planner keeps one per leg on its own frame)
#[test]
fn parsed_state_sizes() {
    use core::mem::size_of;
    let sizes = [
        ("AnyLeg", size_of::<arbx_sizing::AnyLeg>()), ("Parsed", size_of::<arbx_sizing::Parsed>()),
        ("PumpLeg", size_of::<arbx_sizing::venue::pumpswap::PumpLeg>()), ("CpmmLeg", size_of::<arbx_sizing::venue::cpmm::CpmmLeg>()),
        ("DlmmLeg", size_of::<arbx_sizing::venue::dlmm::DlmmLeg>()), ("DammLeg", size_of::<arbx_sizing::venue::dammv2::DammLeg>()),
        ("Plan", size_of::<arbx_sizing::Plan>()), ("Fx", size_of::<Fx>()),
    ];
    eprintln!("{sizes:?}");
    assert_eq!(size_of::<Fx>(), 8);
    assert!(size_of::<arbx_sizing::Parsed>() <= 400);
}

/// The DLMM variable-fee arithmetic: the widening fast path of `rate` equals the checked u128 formula
/// ⌈vfc·(va·bin_step)²/1e11⌉ + base, capped at 1e8, for accumulators up to u32::MAX and every bin step.
#[test]
fn dlmm_rate_fast_path_equals_the_formula() {
    use arbx_sizing::venue::dlmm;
    let mut s = 0x9e37_79b9_7f4a_7c15u64;
    let mut next = move || { s ^= s >> 12; s ^= s << 25; s ^= s >> 27; s.wrapping_mul(0x2545F4914F6CDD1D) };
    let mut checked = 0;
    for _ in 0..20_000 {
        let bin_step = (next() % 500 + 1) as u16;
        let vfc = match next() % 3 { 0 => next() as u32, 1 => (next() % 100_000) as u32, _ => u32::MAX };
        let max_va = match next() % 3 { 0 => next() as u32, 1 => (next() % 1_000_000) as u32, _ => u32::MAX };
        let base_factor = (next() % 65_536) as u16;
        let mut pair = vec![0u8; dlmm::PAIR_LEN];
        pair[..8].copy_from_slice(&arbx_sizing::layout::DISC_LB_PAIR);
        pair[8..10].copy_from_slice(&base_factor.to_le_bytes());
        pair[16..20].copy_from_slice(&vfc.to_le_bytes());
        pair[20..24].copy_from_slice(&max_va.to_le_bytes());
        pair[24..28].copy_from_slice(&(-443_636i32).to_le_bytes());
        pair[28..32].copy_from_slice(&443_636i32.to_le_bytes());
        pair[56..64].copy_from_slice(&1_000i64.to_le_bytes());
        pair[80..82].copy_from_slice(&bin_step.to_le_bytes());
        pair[882] = 1;
        let clock = arbx_sizing::Clock { slot: 1, unix_timestamp: 1_000, epoch: 0 };
        let leg = dlmm::parse(&pair, &[], true, &clock).unwrap();
        for _ in 0..4 {
            let id = (next() % 900_000) as i32 - 450_000;
            let va = ((id as i64).unsigned_abs() * 10_000).min(max_va as u64) as u128;
            let t = va * bin_step as u128;
            let want = t.checked_pow(2).and_then(|sq| (vfc as u128).checked_mul(sq)).map(|n| ((n + 99_999_999_999) / 100_000_000_000 + base_factor as u128 * bin_step as u128 * 10).min(100_000_000));
            assert_eq!(leg.rate(id), want, "vfc {vfc} va {va} bin_step {bin_step}");
            checked += 1;
        }
    }
    assert!(checked == 80_000);
}

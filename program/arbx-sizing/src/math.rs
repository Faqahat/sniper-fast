//! Checked integer helpers shared by the venues: little-endian field reads through `get` (never indexing), ceil
//! division, the split 64×128-bit Q64.64 multiply and the Q64.64 divide DLMM uses, and an integer square root.
//! Every function returns `None` instead of overflowing or panicking.

#[inline]
pub fn rd<const N: usize>(d: &[u8], o: usize) -> Option<[u8; N]> {
    let s = d.get(o..o.checked_add(N)?)?;
    let mut b = [0u8; N];
    b.copy_from_slice(s);
    Some(b)
}
#[inline] pub fn u8_at(d: &[u8], o: usize) -> Option<u8> { d.get(o).copied() }
#[inline] pub fn u16_at(d: &[u8], o: usize) -> Option<u16> { rd::<2>(d, o).map(u16::from_le_bytes) }
#[inline] pub fn u32_at(d: &[u8], o: usize) -> Option<u32> { rd::<4>(d, o).map(u32::from_le_bytes) }
#[inline] pub fn i32_at(d: &[u8], o: usize) -> Option<i32> { rd::<4>(d, o).map(i32::from_le_bytes) }
#[inline] pub fn u64_at(d: &[u8], o: usize) -> Option<u64> { rd::<8>(d, o).map(u64::from_le_bytes) }
#[inline] pub fn i64_at(d: &[u8], o: usize) -> Option<i64> { rd::<8>(d, o).map(i64::from_le_bytes) }
#[inline] pub fn u128_at(d: &[u8], o: usize) -> Option<u128> { rd::<16>(d, o).map(u128::from_le_bytes) }
#[inline] pub fn i128_at(d: &[u8], o: usize) -> Option<i128> { rd::<16>(d, o).map(i128::from_le_bytes) }
/// a 32-byte key at `o`, borrowed
#[inline]
pub fn key_at(d: &[u8], o: usize) -> Option<&[u8; 32]> { d.get(o..o.checked_add(32)?)?.try_into().ok() }

pub const ZERO_KEY: [u8; 32] = [0u8; 32];

/// (a / d, a % d) for a u128 numerator and a u64 divisor. SBF has a native 64-bit divide but no 128-bit one (the
/// compiler-builtins routine costs ~600 CU), so a divisor of at most 60 bits runs a short long division over
/// native u64 divides: c = 64 − bits(d) numerator bits per step, so the running remainder never overflows.
/// Numerators below 2^64 take one native divide. Wider divisors fall back to the builtin.
pub fn divrem_u64(a: u128, d: u64) -> Option<(u128, u64)> {
    if d == 0 { return None; }
    let (hi, lo) = ((a >> 64) as u64, a as u64);
    if hi == 0 { return Some(((lo / d) as u128, lo % d)); }
    let bits = 64 - d.leading_zeros();
    if bits > 60 { return Some((a / d as u128, (a % d as u128) as u64)); }
    let c = 64 - bits; // ≥ 4
    let (q_hi, mut r) = (hi / d, hi % d);
    let mut q_lo = 0u64;
    let mut left = 64u32;
    while left > 0 {
        let take = c.min(left);
        left -= take;
        let chunk = (lo >> left) & ((1u64 << take) - 1);
        let cur = (r << take) | chunk; // r < d < 2^bits, so cur < 2^64
        q_lo = (q_lo << take) | (cur / d);
        r = cur % d;
    }
    Some((((q_hi as u128) << 64) | q_lo as u128, r))
}

/// ⌊a/b⌋ through [`divrem_u64`] when the divisor fits u64; None for b == 0
#[inline]
pub fn div(a: u128, b: u128) -> Option<u128> {
    if b >> 64 == 0 { divrem_u64(a, b as u64).map(|r| r.0) } else { Some(a / b) }
}

/// ⌈a/b⌉; None for b == 0
#[inline]
pub fn ceil_div(a: u128, b: u128) -> Option<u128> {
    if b >> 64 == 0 {
        let (q, r) = divrem_u64(a, b as u64)?;
        return Some(if r != 0 { q + 1 } else { q });
    }
    let q = a / b;
    Some(if q * b != a { q + 1 } else { q })
}

/// ⌊a·b/d⌋ with a checked product
#[inline]
pub fn mul_div(a: u128, b: u128, d: u128) -> Option<u128> { div(a.checked_mul(b)?, d) }

/// ⌈a·b/d⌉ with a checked product
#[inline]
pub fn mul_div_ceil(a: u128, b: u128, d: u128) -> Option<u128> { ceil_div(a.checked_mul(b)?, d) }

const LO64: u128 = u64::MAX as u128;

/// (a·p) >> 64 for a < 2^64 and any Q64.64 `p`, exact (split multiply); `up` rounds up. None on overflow.
#[inline]
pub fn mul_shr64(a: u128, p: u128, up: bool) -> Option<u128> {
    if a > LO64 { return None; }
    // two widening 64×64 products: neither can overflow, so no checked u128 multiply is needed
    let (a, ph, pl) = (a as u64 as u128, (p >> 64) as u64 as u128, p as u64 as u128);
    let lo = a.wrapping_mul(pl);
    let hi = a.wrapping_mul(ph);
    let r = hi.checked_add(lo >> 64)?;
    if up && lo & LO64 != 0 { r.checked_add(1) } else { Some(r) }
}

/// (a << 64) / p for a < 2^64; `up` rounds up. None for p == 0 or a ≥ 2^64.
#[inline]
pub fn shl64_div(a: u128, p: u128, up: bool) -> Option<u128> {
    if p == 0 || a > LO64 { return None; }
    let n = a << 64;
    if up { ceil_div(n, p) } else { div(n, p) }
}

/// ⌊√n⌋ for u64, Newton from a power-of-two seed above the root (native u64 divides only).
pub fn isqrt_u64(n: u64) -> u64 {
    if n < 2 { return n; }
    let bits = 64 - n.leading_zeros();
    let mut x: u64 = 1u64 << ((bits + 1) / 2).min(32); // ≥ √n
    loop {
        let y = (x + n / x) >> 1;
        if y >= x { return x; }
        x = y;
    }
}

/// ⌊√n⌋ for u128 (Newton; host helper for tests and the engine)
pub fn isqrt_u128(n: u128) -> u128 {
    if n < 2 { return n; }
    let bits = 128 - n.leading_zeros();
    let mut x: u128 = 1u128 << ((bits + 1) / 2).min(64);
    loop {
        let y = (x + n / x) >> 1;
        if y >= x { return x; }
        x = y;
    }
}

/// `i128` → `i64`, saturating
#[inline]
pub fn sat_i64(v: i128) -> i64 { v.clamp(i64::MIN as i128, i64::MAX as i128) as i64 }

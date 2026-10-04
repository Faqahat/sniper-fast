//! `Fx`: a deterministic integer pseudo-float for the locator (DESIGN.md §3.8). Value = `m · 2^e` with the mantissa
//! normalised to [2^31, 2^32) (or 0). There are no floats, and `Fx` never decides anything: only the exact
//! evaluators do.
//!
//! Packed in ONE u64 — the biased exponent in the high 32 bits, the mantissa in the low 32 — so it travels in a
//! register on SBF and the value order is the integer order (zero is 0, every nonzero value has a biased exponent
//! ≥ 1). mul/div/add know their result's width and normalise with one bit test; only conversions and subtraction
//! (cancellation) count leading zeros, which SBF does in software. Truncation gives a relative error of at most
//! 2^-31 per operation. Values are non-negative; subtraction saturates at 0; exponents beyond ±2^20 are ∞ / 0.

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Fx(u64);

const BIAS: i64 = 1 << 31;
const EMAX: i64 = 1 << 20;
const MIN_M: u64 = 1 << 31;

#[inline(always)]
fn pack(m: u64, e: i64) -> Fx {
    if e >= EMAX { return Fx::INF; }
    if e <= -EMAX { return Fx::ZERO; }
    Fx((((e + BIAS) as u64) << 32) | m)
}

impl Fx {
    pub const ZERO: Fx = Fx(0);
    pub const ONE: Fx = Fx((((BIAS - 31) as u64) << 32) | MIN_M);
    pub const TWO: Fx = Fx((((BIAS - 30) as u64) << 32) | MIN_M);
    /// larger than every finite value; `x·∞ = ∞`, `x/∞ = 0`
    pub const INF: Fx = Fx((((BIAS + EMAX) as u64) << 32) | MIN_M);

    #[inline(always)] fn m(self) -> u64 { self.0 & 0xFFFF_FFFF }
    #[inline(always)] fn e(self) -> i64 { (self.0 >> 32) as i64 - BIAS }

    /// any nonzero m (up to 64 bits) at exponent e
    #[inline(never)]
    fn norm(m: u64, e: i64) -> Fx {
        if m == 0 { return Fx::ZERO; }
        let lz = m.leading_zeros() as i64;
        if lz > 32 { pack(m << (lz - 32), e - (lz - 32)) } else { pack(m >> (32 - lz), e + (32 - lz)) }
    }

    #[inline(never)]
    pub fn from_u64(v: u64) -> Fx { Fx::norm(v, 0) }
    #[inline(never)]
    pub fn from_u128(v: u128) -> Fx {
        if v >> 64 == 0 { return Fx::from_u64(v as u64); }
        let sh = 64 - ((v >> 64) as u64).leading_zeros() as i64; // bits above 64, 1..=64
        Fx::norm((v >> sh) as u64, sh)
    }
    /// n / d
    #[inline] pub fn ratio(n: u64, d: u64) -> Fx { Fx::from_u64(n).div(Fx::from_u64(d)) }

    #[inline] pub fn is_zero(self) -> bool { self.0 == 0 }
    #[inline] pub fn is_inf(self) -> bool { self >= Fx::INF }
    /// (mantissa, exponent): value = m · 2^e
    #[inline] pub fn parts(self) -> (u64, i32) { if self.is_zero() { (0, 0) } else { (self.m(), self.e() as i32) } }

    /// a 62..64-bit product or sum at exponent e: keep the top 32 bits
    #[inline(always)]
    fn top(p: u64, e: i64) -> Fx { if p >> 63 != 0 { pack(p >> 32, e + 32) } else { pack(p >> 31, e + 31) } }

    #[inline(never)]
    pub fn mul(self, o: Fx) -> Fx {
        if self.is_zero() || o.is_zero() { return Fx::ZERO; }
        if self.is_inf() || o.is_inf() { return Fx::INF; }
        Fx::top(self.m() * o.m(), self.e() + o.e())
    }

    #[inline(never)]
    pub fn div(self, o: Fx) -> Fx {
        if self.is_zero() { return Fx::ZERO; }
        if o.is_zero() || self.is_inf() { return Fx::INF; }
        if o.is_inf() { return Fx::ZERO; }
        // (m1 << 32) / m2 is in (2^31, 2^33)
        let q = (self.m() << 32) / o.m();
        let e = self.e() - o.e() - 32;
        if q >> 32 != 0 { pack(q >> 1, e + 1) } else { pack(q, e) }
    }

    #[inline(never)]
    pub fn add(self, o: Fx) -> Fx {
        if self.is_zero() { return o; }
        if o.is_zero() { return self; }
        if self.is_inf() || o.is_inf() { return Fx::INF; }
        let (a, b) = if self >= o { (self, o) } else { (o, self) };
        let d = a.e() - b.e();
        if d > 40 { return a; }
        // (a.m << 31) + (b.m << 31 >> d) is in [2^62, 2^64)
        Fx::top((a.m() << 31) + ((b.m() << 31) >> d), a.e() - 31)
    }

    /// self − o, saturating at 0
    #[inline(never)]
    pub fn sub(self, o: Fx) -> Fx {
        if o >= self { return Fx::ZERO; }
        if o.is_zero() || self.is_inf() { return self; }
        let d = self.e() - o.e();
        if d > 40 { return self; }
        Fx::norm((self.m() << 31) - ((o.m() << 31) >> d), self.e() - 31)
    }

    #[inline(never)]
    pub fn sqrt(self) -> Fx {
        if self.is_zero() || self.is_inf() { return self; }
        let e = self.e();
        // m << sh in [2^62, 2^64) with e − sh even; the root is in [2^31, 2^32): already normalised
        let sh = if (e - 31) % 2 == 0 { 31 } else { 32 };
        pack(crate::math::isqrt_u64(self.m() << sh), (e - sh) / 2)
    }

    /// self · 2^k
    #[inline]
    pub fn shl(self, k: i32) -> Fx {
        if self.is_zero() || self.is_inf() { return self; }
        pack(self.m(), self.e() + k as i64)
    }

    #[inline] pub fn min(self, o: Fx) -> Fx { if self <= o { self } else { o } }
    #[inline] pub fn max(self, o: Fx) -> Fx { if self >= o { self } else { o } }

    /// ⌊value⌋ as u64, saturating
    #[inline(never)]
    pub fn floor_u64(self) -> u64 {
        if self.is_zero() { return 0; }
        let e = self.e();
        if self.is_inf() || e > 32 { return u64::MAX; }
        if e >= 0 { self.m() << e } else if e <= -64 { 0 } else { self.m() >> (-e) }
    }

    /// ⌊value⌋ as u128, saturating
    #[inline(never)]
    pub fn floor_u128(self) -> u128 {
        if self.is_zero() { return 0; }
        let e = self.e();
        if self.is_inf() || e > 96 { return u128::MAX; }
        if e >= 0 { (self.m() as u128) << e } else if e <= -64 { 0 } else { (self.m() >> (-e)) as u128 }
    }
}

//! The U256 subset DAMM v2 needs (four little-endian u64 limbs), ported from `src/venues/dammv2.rs` (same semantics
//! as the ruint operations the program uses), with every panic path replaced by `None`.
use core::cmp::Ordering;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct U256(pub [u64; 4]);

impl Ord for U256 {
    fn cmp(&self, o: &Self) -> Ordering {
        for i in (0..4).rev() {
            match self.0[i].cmp(&o.0[i]) { Ordering::Equal => continue, c => return c }
        }
        Ordering::Equal
    }
}
impl PartialOrd for U256 {
    fn partial_cmp(&self, o: &Self) -> Option<Ordering> { Some(self.cmp(o)) }
}

impl U256 {
    pub const ZERO: U256 = U256([0; 4]);
    pub const ONE: U256 = U256([1, 0, 0, 0]);

    #[inline] pub fn from_u128(x: u128) -> U256 { U256([x as u64, (x >> 64) as u64, 0, 0]) }
    #[inline]
    pub fn to_u128(self) -> Option<u128> {
        if self.0[2] != 0 || self.0[3] != 0 { None } else { Some(self.0[0] as u128 | (self.0[1] as u128) << 64) }
    }
    #[inline] pub fn is_zero(self) -> bool { self.0 == [0; 4] }
    pub fn bits(self) -> u32 {
        for i in (0..4).rev() { if self.0[i] != 0 { return 64 * i as u32 + 64 - self.0[i].leading_zeros(); } }
        0
    }

    /// the full 256-bit product of two u128
    pub fn mul128(a: u128, b: u128) -> U256 {
        let (a0, a1, b0, b1) = (a as u64 as u128, a >> 64, b as u64 as u128, b >> 64);
        let (p00, p01, p10, p11) = (a0 * b0, a0 * b1, a1 * b0, a1 * b1);
        let mid = (p00 >> 64) + (p01 as u64 as u128) + (p10 as u64 as u128);
        let lo = (p00 as u64 as u128) | (mid << 64);
        let hi = p11 + (p01 >> 64) + (p10 >> 64) + (mid >> 64);
        U256([lo as u64, (lo >> 64) as u64, hi as u64, (hi >> 64) as u64])
    }

    pub fn checked_add(self, o: U256) -> Option<U256> {
        let mut r = [0u64; 4];
        let mut carry = 0u128;
        for (i, ri) in r.iter_mut().enumerate() {
            let s = self.0[i] as u128 + o.0[i] as u128 + carry;
            *ri = s as u64;
            carry = s >> 64;
        }
        if carry != 0 { None } else { Some(U256(r)) }
    }

    pub fn checked_sub(self, o: U256) -> Option<U256> {
        if self < o { return None; }
        let mut r = [0u64; 4];
        let mut borrow = 0u64;
        for (i, ri) in r.iter_mut().enumerate() {
            let (d1, b1) = self.0[i].overflowing_sub(o.0[i]);
            let (d2, b2) = d1.overflowing_sub(borrow);
            *ri = d2;
            borrow = (b1 || b2) as u64;
        }
        Some(U256(r))
    }

    pub fn checked_mul(self, o: U256) -> Option<U256> {
        let mut r = [0u64; 8];
        for i in 0..4 {
            let mut carry = 0u128;
            for j in 0..4 {
                let t = self.0[i] as u128 * o.0[j] as u128 + r[i + j] as u128 + carry;
                r[i + j] = t as u64;
                carry = t >> 64;
            }
            r[i + 4] = carry as u64;
        }
        if r[4..].iter().any(|&x| x != 0) { None } else { Some(U256([r[0], r[1], r[2], r[3]])) }
    }

    /// self << n; None when a set bit would be shifted out
    pub fn shl(self, n: u32) -> Option<U256> {
        if self.is_zero() { return Some(self); }
        if n >= 256 || self.bits() + n > 256 { return None; }
        let (w, b) = ((n / 64) as usize, n % 64);
        let mut r = [0u64; 4];
        for i in (w..4).rev() {
            let src = i - w;
            r[i] = self.0[src] << b;
            if b > 0 && src > 0 { r[i] |= self.0[src - 1] >> (64 - b); }
        }
        Some(U256(r))
    }

    pub fn shr(self, n: u32) -> U256 {
        if n >= 256 { return U256::ZERO; }
        let (w, b) = ((n / 64) as usize, n % 64);
        let mut r = [0u64; 4];
        for i in 0..4 - w {
            r[i] = self.0[i + w] >> b;
            if b > 0 && i + w + 1 < 4 { r[i] |= self.0[i + w + 1] << (64 - b); }
        }
        U256(r)
    }

    /// any of the low `n` bits set
    pub fn low_bits_nonzero(self, n: u32) -> bool {
        let mut left = n;
        for i in 0..4 {
            if left == 0 { return false; }
            let mask = if left >= 64 { u64::MAX } else { (1u64 << left) - 1 };
            if self.0[i] & mask != 0 { return true; }
            left = left.saturating_sub(64);
        }
        false
    }

    /// (quotient, remainder); None for a zero divisor. Knuth algorithm D on 64-bit limbs.
    pub fn div_rem(self, d: U256) -> Option<(U256, U256)> {
        if d.is_zero() { return None; }
        if self < d { return Some((U256::ZERO, self)); }
        if let (Some(a), Some(b)) = (self.to_u128(), d.to_u128()) {
            return Some((U256::from_u128(a / b), U256::from_u128(a % b)));
        }
        let n = ((d.bits() + 63) / 64) as usize; // divisor limbs, 1..=4
        let m = ((self.bits() + 63) / 64) as usize; // dividend limbs, n..=4
        if n == 1 {
            let dv = d.0[0] as u128;
            let mut q = [0u64; 4];
            let mut r = 0u128;
            for i in (0..m).rev() {
                let cur = (r << 64) | self.0[i] as u128;
                let (qq, rr) = crate::math::divrem_u64(cur, dv as u64)?;
                q[i] = qq as u64;
                r = rr as u128;
            }
            return Some((U256(q), U256::from_u128(r)));
        }
        let s = d.0[n - 1].leading_zeros();
        let mut vn = [0u64; 4];
        for i in (1..n).rev() { vn[i] = (d.0[i] << s) | if s > 0 { d.0[i - 1] >> (64 - s) } else { 0 }; }
        vn[0] = d.0[0] << s;
        let mut un = [0u64; 5];
        un[m] = if s > 0 { self.0[m - 1] >> (64 - s) } else { 0 };
        for i in (1..m).rev() { un[i] = (self.0[i] << s) | if s > 0 { self.0[i - 1] >> (64 - s) } else { 0 }; }
        un[0] = self.0[0] << s;
        let b: u128 = 1 << 64;
        let mut q = [0u64; 4];
        for j in (0..=m - n).rev() {
            let num = ((un[j + n] as u128) << 64) | un[j + n - 1] as u128;
            let mut qhat = num / vn[n - 1] as u128;
            let mut rhat = num % vn[n - 1] as u128;
            while qhat >= b || qhat * vn[n - 2] as u128 > ((rhat << 64) | un[j + n - 2] as u128) {
                qhat -= 1;
                rhat += vn[n - 1] as u128;
                if rhat >= b { break; }
            }
            let mut k: i128 = 0;
            for i in 0..n {
                let p = qhat * vn[i] as u128;
                let t = un[i + j] as i128 - k - (p as u64) as i128;
                un[i + j] = t as u64;
                k = (p >> 64) as i128 - (t >> 64);
            }
            let t = un[j + n] as i128 - k;
            un[j + n] = t as u64;
            if t < 0 {
                qhat -= 1;
                let mut c = 0u128;
                for i in 0..n {
                    let s2 = un[i + j] as u128 + vn[i] as u128 + c;
                    un[i + j] = s2 as u64;
                    c = s2 >> 64;
                }
                un[j + n] = un[j + n].wrapping_add(c as u64);
            }
            q[j] = qhat as u64;
        }
        let mut r = [0u64; 4];
        for i in 0..n { r[i] = (un[i] >> s) | if s > 0 { un[i + 1] << (64 - s) } else { 0 }; }
        Some((U256(q), U256(r)))
    }

    /// self / d rounded down or up; None for a zero divisor
    pub fn div_round(self, d: U256, up: bool) -> Option<U256> {
        let (q, r) = self.div_rem(d)?;
        if up && !r.is_zero() { q.checked_add(U256::ONE) } else { Some(q) }
    }

    /// ⌊√self⌋ (Newton from above); the integer square root is unique, so this equals the program's sqrt_u256
    pub fn isqrt(self) -> Option<U256> {
        if self.is_zero() { return Some(self); }
        let mut x = U256::ONE.shl((self.bits() + 1) / 2)?;
        for _ in 0..300 {
            let y = x.checked_add(self.div_rem(x)?.0)?.shr(1);
            if y >= x { return Some(x); }
            x = y;
        }
        None
    }
}

/// The full 512-bit product a·b, as 8 little-endian u64 limbs (concentrated-liquidity maths: Raydium CLMM's `U512`
/// mul-div paths, Orca's U256Muldiv products).
pub fn mul_full(a: U256, b: U256) -> [u64; 8] {
    let mut r = [0u64; 8];
    for (i, &x) in a.0.iter().enumerate() {
        let mut carry = 0u128;
        for (j, &y) in b.0.iter().enumerate() {
            let k = i + j;
            let t = x as u128 * y as u128 + r[k] as u128 + carry;
            r[k] = t as u64;
            carry = t >> 64;
        }
        r[i + 4] = carry as u64;
    }
    r
}

/// Knuth algorithm D on little-endian u64 limbs: (quotient, remainder) of the `m`-limb `u` by the `n`-limb `v`
/// (v[n−1] ≠ 0, 1 ≤ n ≤ 4, n ≤ m ≤ 8). The quotient has m − n + 1 limbs, the remainder n. None on bad input.
fn divmod_limbs(u: &[u64], v: &[u64]) -> Option<([u64; 8], [u64; 4])> {
    let (m, n) = (u.len(), v.len());
    if n == 0 || n > 4 || m < n || m > 8 || *v.last()? == 0 { return None; }
    let mut q = [0u64; 8];
    let mut r = [0u64; 4];
    if n == 1 {
        let d = *v.first()? as u128;
        let mut k = 0u128;
        for j in (0..m).rev() {
            let cur = (k << 64) | *u.get(j)? as u128;
            *q.get_mut(j)? = (cur / d) as u64;
            k = cur % d;
        }
        r[0] = k as u64;
        return Some((q, r));
    }
    let s = v.get(n - 1)?.leading_zeros();
    let shl = |hi: u64, lo: u64| if s == 0 { hi } else { (hi << s) | (lo >> (64 - s)) };
    let mut vn = [0u64; 4];
    for i in (1..n).rev() { *vn.get_mut(i)? = shl(*v.get(i)?, *v.get(i - 1)?); }
    vn[0] = v.first()? << s;
    let mut un = [0u64; 9];
    *un.get_mut(m)? = if s == 0 { 0 } else { u.get(m - 1)? >> (64 - s) };
    for i in (1..m).rev() { *un.get_mut(i)? = shl(*u.get(i)?, *u.get(i - 1)?); }
    un[0] = u.first()? << s;
    let b: u128 = 1 << 64;
    let (vt, vt2) = (*vn.get(n - 1)? as u128, *vn.get(n - 2)? as u128);
    for j in (0..=m - n).rev() {
        let num = ((*un.get(j + n)? as u128) << 64) | *un.get(j + n - 1)? as u128;
        let mut qhat = num / vt;
        let mut rhat = num % vt;
        while qhat >= b || qhat * vt2 > ((rhat << 64) | *un.get(j + n - 2)? as u128) {
            qhat -= 1;
            rhat += vt;
            if rhat >= b { break; }
        }
        // multiply and subtract
        let mut k: i128 = 0;
        for i in 0..n {
            let p = qhat * *vn.get(i)? as u128;
            let t = *un.get(i + j)? as i128 - k - (p as u64) as i128;
            *un.get_mut(i + j)? = t as u64;
            k = (p >> 64) as i128 - (t >> 64);
        }
        let t = *un.get(j + n)? as i128 - k;
        *un.get_mut(j + n)? = t as u64;
        if t < 0 {
            // add back
            qhat -= 1;
            let mut c = 0u128;
            for i in 0..n {
                let s2 = *un.get(i + j)? as u128 + *vn.get(i)? as u128 + c;
                *un.get_mut(i + j)? = s2 as u64;
                c = s2 >> 64;
            }
            let top = un.get_mut(j + n)?;
            *top = top.wrapping_add(c as u64);
        }
        *q.get_mut(j)? = qhat as u64;
    }
    for i in 0..n {
        let lo = *un.get(i)?;
        let hi = *un.get(i + 1)?;
        *r.get_mut(i)? = if s == 0 { lo } else { (lo >> s) | (hi << (64 - s)) };
    }
    Some((q, r))
}

/// ⌊n/d⌋ (`up`: ⌈n/d⌉) of a 512-bit `n` by a nonzero `d`; None when d = 0 or the quotient exceeds 256 bits (the
/// semantics of the uint crate's `U256::mul_div_floor` / `mul_div_ceil`, Raydium CLMM full_math.rs)
pub fn div_512(n: &[u64; 8], d: U256, up: bool) -> Option<U256> {
    let nd = d.0.iter().rposition(|&w| w != 0)? + 1;
    let nn = n.iter().rposition(|&w| w != 0).map_or(0, |i| i + 1);
    if nn < nd {
        // quotient 0, remainder n
        return Some(if up && nn > 0 { U256::ONE } else { U256::ZERO });
    }
    let (q, r) = divmod_limbs(n.get(..nn)?, d.0.get(..nd)?)?;
    if q.get(4..)?.iter().any(|&w| w != 0) { return None; }
    let q = U256([q[0], q[1], q[2], q[3]]);
    if up && r.iter().any(|&w| w != 0) { q.checked_add(U256::ONE) } else { Some(q) }
}

/// ⌊a·b/d⌋ or ⌈a·b/d⌉ over the full 512-bit product; None for d = 0 or a quotient beyond 256 bits
pub fn mul_div_wide(a: U256, b: U256, d: U256, up: bool) -> Option<U256> { div_512(&mul_full(a, b), d, up) }

impl U256 {
    pub fn leading_zeros(self) -> u32 { 256 - self.bits() }
    pub fn from_u64(x: u64) -> U256 { U256([x, 0, 0, 0]) }
    /// the low 64 bits (callers check the value fits)
    pub fn low_u64(self) -> u64 { self.0[0] }
    pub fn fits_u64(self) -> bool { self.0[1] == 0 && self.0[2] == 0 && self.0[3] == 0 }
}

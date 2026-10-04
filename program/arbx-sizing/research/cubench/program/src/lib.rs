//! CU micro-benchmark for the arbx-sizing design: per-operation costs of the integer primitives on SBF.
//! data: [op u8][n u32]. Logs "op n cu" via sol_log_64.
use core::hint::black_box;
use solana_program::{account_info::AccountInfo, entrypoint::ProgramResult, pubkey::Pubkey, log::sol_log_64,
    compute_units::sol_remaining_compute_units};

solana_program::entrypoint!(process);

#[derive(Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub struct U256(pub [u64; 4]);
impl U256 {
    pub const ZERO: U256 = U256([0; 4]);
    pub fn from_u128(x: u128) -> U256 { U256([x as u64, (x >> 64) as u64, 0, 0]) }
    pub fn bits(self) -> u32 { for i in (0..4).rev() { if self.0[i] != 0 { return 64 * i as u32 + 64 - self.0[i].leading_zeros(); } } 0 }
    pub fn lt(&self, o: &U256) -> bool { for i in (0..4).rev() { if self.0[i] != o.0[i] { return self.0[i] < o.0[i]; } } false }
    #[inline(never)]
    pub fn mul128(a: u128, b: u128) -> U256 {
        let (a0, a1, b0, b1) = (a as u64 as u128, a >> 64, b as u64 as u128, b >> 64);
        let (p00, p01, p10, p11) = (a0 * b0, a0 * b1, a1 * b0, a1 * b1);
        let mid = (p00 >> 64) + (p01 as u64 as u128) + (p10 as u64 as u128);
        let lo = (p00 as u64 as u128) | (mid << 64);
        let hi = p11 + (p01 >> 64) + (p10 >> 64) + (mid >> 64);
        U256([lo as u64, (lo >> 64) as u64, hi as u64, (hi >> 64) as u64])
    }
    /// Knuth D, 64-bit limbs (same as arbx src/venues/dammv2.rs)
    #[inline(never)]
    pub fn div_rem(self, d: U256) -> Option<(U256, U256)> {
        if d.0 == [0; 4] { return None; }
        if self.lt(&d) { return Some((U256::ZERO, self)); }
        let n = ((d.bits() + 63) / 64) as usize;
        let m = ((self.bits() + 63) / 64) as usize;
        if n == 1 {
            let dv = d.0[0] as u128; let mut q = [0u64; 4]; let mut r = 0u128;
            for i in (0..m).rev() { let cur = (r << 64) | self.0[i] as u128; q[i] = (cur / dv) as u64; r = cur % dv; }
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
        let b: u128 = 1 << 64; let mut q = [0u64; 4];
        for j in (0..=m - n).rev() {
            let num = ((un[j + n] as u128) << 64) | un[j + n - 1] as u128;
            let mut qhat = num / vn[n - 1] as u128; let mut rhat = num % vn[n - 1] as u128;
            while qhat >= b || qhat * vn[n - 2] as u128 > ((rhat << 64) | un[j + n - 2] as u128) {
                qhat -= 1; rhat += vn[n - 1] as u128; if rhat >= b { break; }
            }
            let mut k: i128 = 0;
            for i in 0..n {
                let p = qhat * vn[i] as u128;
                let t = un[i + j] as i128 - k - (p as u64) as i128;
                un[i + j] = t as u64; k = (p >> 64) as i128 - (t >> 64);
            }
            let t = un[j + n] as i128 - k; un[j + n] = t as u64;
            if t < 0 {
                qhat -= 1; let mut c = 0u128;
                for i in 0..n { let s2 = un[i + j] as u128 + vn[i] as u128 + c; un[i + j] = s2 as u64; c = s2 >> 64; }
                un[j + n] = un[j + n].wrapping_add(c as u64);
            }
            q[j] = qhat as u64;
        }
        let mut r = [0u64; 4];
        for i in 0..n { r[i] = (un[i] >> s) | if s > 0 { un[i + 1] << (64 - s) } else { 0 }; }
        Some((U256(q), U256(r)))
    }
}

/// floor(sqrt(x)) for u128: one hardware-free Newton from a power-of-two start
#[inline(never)]
pub fn isqrt_u128(x: u128) -> u128 {
    if x < 2 { return x; }
    let mut r = 1u128 << ((128 - x.leading_zeros() + 1) / 2);
    loop { let y = (r + x / r) >> 1; if y >= r { return r; } r = y; }
}

/// (a * p) >> 64 with a < 2^64, p a Q64.64 (arb-lab dlmm.rs mul_shr, no U256)
#[inline(never)]
pub fn mul_shr(a: u128, p: u128, up: bool) -> Option<u128> {
    let (ph, pl) = (p >> 64, p & u64::MAX as u128);
    let lo = a.checked_mul(pl)?; let hi = a.checked_mul(ph)?;
    let mut r = hi.checked_add(lo >> 64)?;
    if up && lo & u64::MAX as u128 != 0 { r += 1; }
    Some(r)
}
#[inline(never)]
pub fn shl_div(a: u128, p: u128, up: bool) -> Option<u128> {
    if p == 0 || a > u64::MAX as u128 { return None; }
    let n = a << 64; let (q, r) = (n / p, n % p);
    Some(if up && r != 0 { q + 1 } else { q })
}
fn cdiv(a: u128, b: u128) -> u128 { (a + b - 1) / b }

/// one DLMM bin of an X->Y exact-in walk (fee on input): drain test + partial fill
#[inline(never)]
pub fn dlmm_bin(remaining: u128, amount_y: u128, price: u128, rate: u128) -> Option<(u128, u128)> {
    let max_in = shl_div(amount_y, price, true)?;
    let fee = cdiv(remaining * rate, 1_000_000_000);
    let excl = remaining - fee;
    if excl >= max_in {
        let fee2 = cdiv(max_in * rate, 1_000_000_000 - rate);
        Some((max_in + fee2, amount_y))
    } else {
        Some((remaining, mul_shr(excl, price, false)?.min(amount_y)))
    }
}
/// DLMM variable fee for a bin (u128)
#[inline(never)]
pub fn dlmm_rate(vref: u128, idx_ref: i64, bin: i64, max_va: u128, vfc: u128, step: u128, base: u128) -> u128 {
    let va = (vref + (idx_ref - bin).unsigned_abs() as u128 * 10_000).min(max_va);
    let vb = va * step;
    (base + cdiv(vfc * vb * vb, 100_000_000_000)).min(100_000_000)
}
/// Raydium CPMM swap_base_input (no creator fee)
#[inline(never)]
pub fn cpmm(a: u128, rin: u128, rout: u128, trade: u128) -> u128 {
    let fee = cdiv(a * trade, 1_000_000);
    let net = a - fee;
    net * rout / (rin + net)
}
/// closed-form CPMM-CPMM optimum in Q64 fixed point (u128 only): x* = (sqrt(K R1i R2i) - R1i R2i) / M,
/// via Q = (R1o R2o g1 g2)/(R1i R2i) normalised to ~2^64 and an integer sqrt
#[inline(never)]
pub fn cpmm2_opt(r1i: u128, r1o: u128, r2i: u128, r2o: u128, g1: u128, g2: u128) -> u128 {
    // g in 1e6 units. y-units: price1 = r1o/r1i (X per A), price2 = r2o/r2i (A per X)
    // Q64 = 2^64 * (r1o * g1 / (r1i * 1e6)) * (r2o * g2 / (r2i * 1e6)), each factor in Q64 by u128 division
    let p1 = ((r1o * g1) << 20) / (r1i * 1_000_000 >> 44).max(1); // ~Q64 (scaled), 20+44=64
    let p2 = ((r2o * g2) << 20) / (r2i * 1_000_000 >> 44).max(1);
    let q = (p1 >> 32) * (p2 >> 32); // Q64
    let one = 1u128 << 64;
    if q <= one { return 0; }
    let sq = isqrt_u128(q) << 32; // sqrt in Q64
    // x* = r1i * (sq - 1) / (g1 * (1 + p1 * r1i / r2i ...)) -- representative op count: 2 more mul/div
    let num = r1i * ((sq - one) >> 32);
    num / (((g1 << 32) / 1_000_000) + 1) * ((r2i << 8) / (r2i + ((r1o * g1 / 1_000_000) >> 2)).max(1))
}

pub fn process(_p: &Pubkey, _a: &[AccountInfo], d: &[u8]) -> ProgramResult {
    let op = d[0];
    let n = u32::from_le_bytes([d[1], d[2], d[3], d[4]]);
    let mut s: u64 = 0x9E37_79B9_7F4A_7C15;
    let mut acc: u128 = 0;
    let c0 = sol_remaining_compute_units();
    for _ in 0..n {
        s = s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        let x = black_box(s);
        let y = black_box(s.rotate_left(17) | 1);
        let v: u128 = match op {
            0 => x as u128,
            1 => (x as u128) * (y as u128),
            2 => ((x as u128) << 40 | 7).wrapping_mul((y as u128) << 30 | 3),
            3 => (((x as u128) << 64) | y as u128) / (((y as u128) << 60) | x as u128 | 1),
            4 => (((x as u128) << 64) | y as u128) / (y as u128 >> 1 | 1),
            5 => { let r = U256::mul128(((x as u128) << 64) | y as u128, ((y as u128) << 50) | x as u128); r.0[1] as u128 ^ r.0[3] as u128 }
            6 => { let a = U256::mul128(((x as u128) << 64) | y as u128, ((y as u128) << 60) | 5); let (q, _) = a.div_rem(U256::from_u128(((y as u128) << 70) | x as u128 | 1)).unwrap(); q.0[0] as u128 }
            7 => isqrt_u128(((x as u128) << 63) | y as u128),
            8 => { let (a, b) = dlmm_bin((x >> 8) as u128, (y >> 10) as u128, (1u128 << 64) / 200 + (x as u128 & 0xffff), 25_000_000).unwrap(); a ^ b }
            9 => dlmm_rate(11_855, -524, -538 - (x & 63) as i64, 150_000, 7_500, 100, 20_000_000),
            10 => cpmm((x >> 20) as u128, 337_244_181_640 + (y as u128 & 0xfff), 72_969_898_903_177, 2_500),
            11 => cpmm2_opt(337_244_181_640 + (x as u128 & 0xff), 72_969_898_903_177, 70_000_000_000_000 + (y as u128 & 0xff), 340_000_000_000, 997_500, 997_000),
            12 => u128::from_le_bytes(black_box([x as u8; 16])), // 16-byte load
            _ => 0,
        };
        acc ^= black_box(v);
    }
    let c1 = sol_remaining_compute_units();
    sol_log_64(op as u64, n as u64, c0 - c1, acc as u64, 0);
    Ok(())
}

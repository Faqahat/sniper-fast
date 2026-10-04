//! Read-only copies of the engine's venue maths (/home/moiz/arbed/arbx/src/venues/{cp,dlmm,dammv2}.rs) and the
//! helpers they import from src/venues/mod.rs, for the differential tests (DESIGN.md §6.2). The arbx crate itself
//! is not a dependency.
#![allow(dead_code)]
pub mod cp;
pub mod dammv2;
pub mod dlmm;

pub type Pk = [u8; 32];

// ---- src/venues/mod.rs (copied) ----
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Venue { PumpSwap, RayCpmm, RayAmmV4, Dlmm, DammV2 }

#[derive(Debug, Clone)]
pub struct PoolMeta {
    pub venue: Venue,
    pub pool: Pk,
    pub t0: Pk,
    pub t1: Pk,
    pub vault0: Pk,
    pub vault1: Pk,
    pub t0_prog: Pk,
    pub t1_prog: Pk,
    pub extra: Vec<Pk>,
    pub flag: bool,
}

/// src/venues/mod.rs WSOL
pub static WSOL: std::sync::LazyLock<Pk> = std::sync::LazyLock::new(|| arbx_sizing::layout::WSOL);

pub fn u16_at(d: &[u8], o: usize) -> Option<u16> { d.get(o..o + 2).map(|b| u16::from_le_bytes([b[0], b[1]])) }
pub fn u32_at(d: &[u8], o: usize) -> Option<u32> { d.get(o..o + 4).map(|b| u32::from_le_bytes(b.try_into().unwrap())) }
pub fn i32_at(d: &[u8], o: usize) -> Option<i32> { d.get(o..o + 4).map(|b| i32::from_le_bytes(b.try_into().unwrap())) }
pub fn u64_at(d: &[u8], o: usize) -> Option<u64> { d.get(o..o + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap())) }
pub fn i64_at(d: &[u8], o: usize) -> Option<i64> { d.get(o..o + 8).map(|b| i64::from_le_bytes(b.try_into().unwrap())) }
pub fn u128_at(d: &[u8], o: usize) -> Option<u128> { d.get(o..o + 16).map(|b| u128::from_le_bytes(b.try_into().unwrap())) }
pub fn pk_at(d: &[u8], o: usize) -> Option<Pk> { d.get(o..o + 32).map(|b| b.try_into().unwrap()) }
pub fn token_amount(d: &[u8]) -> Option<u64> { if d.len() >= 72 { u64_at(d, 64) } else { None } }
pub fn ceil_div(a: u128, b: u128) -> u128 { if b == 0 { 0 } else { (a + b - 1) / b } }
pub fn solve_exact_in(want: u64, quote: impl Fn(u64) -> Option<u64>) -> Option<u64> {
    if want == 0 { return None; }
    let mut hi = want.max(1);
    let mut got = quote(hi)?;
    let mut n = 0;
    while got < want { hi = hi.checked_mul(2)?; got = quote(hi)?; n += 1; if n > 64 { return None; } }
    let mut lo = 0u64;
    while hi - lo > 1 {
        let mid = lo + (hi - lo) / 2;
        if quote(mid).map_or(false, |o| o >= want) { hi = mid; } else { lo = mid; }
    }
    Some(hi)
}

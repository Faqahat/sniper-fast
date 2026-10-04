//! Venues: pool metadata, live snapshots built from raw account bytes, exact-in quotes, post-trade prediction, and
//! decoding of a third party's swap instruction. All math is integer (u128, with a 192-bit product where DLMM needs
//! it). Ported from the current bot's TypeScript (docs/spec-cpmm.md, docs/spec-dlmm.md), with its known float and
//! fee-bookkeeping shortcuts replaced by the programs' integer rules; the engine checks every prediction against the
//! pool's real next state, so any remaining mismatch is measured, not assumed.
pub mod cp;
pub mod dlmm;
pub mod dammv2;

use crate::tx::{pk, Pk};
use std::sync::LazyLock;

pub static PUMPSWAP: LazyLock<Pk> = LazyLock::new(|| pk("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"));
pub static RAYCPMM: LazyLock<Pk> = LazyLock::new(|| pk("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"));
pub static RAYAMMV4: LazyLock<Pk> = LazyLock::new(|| pk("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"));
pub static DLMM: LazyLock<Pk> = LazyLock::new(|| pk("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"));
pub static DAMMV2: LazyLock<Pk> = LazyLock::new(|| pk("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"));
pub static WSOL: LazyLock<Pk> = LazyLock::new(|| pk("So11111111111111111111111111111111111111112"));

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize)]
pub enum Venue { PumpSwap, RayCpmm, RayAmmV4, Dlmm, DammV2 }

impl Venue {
    pub fn program(&self) -> Pk {
        match self { Venue::PumpSwap => *PUMPSWAP, Venue::RayCpmm => *RAYCPMM, Venue::RayAmmV4 => *RAYAMMV4, Venue::Dlmm => *DLMM, Venue::DammV2 => *DAMMV2 }
    }
    pub fn of_program(p: &Pk) -> Option<Venue> {
        if *p == *PUMPSWAP { Some(Venue::PumpSwap) } else if *p == *RAYCPMM { Some(Venue::RayCpmm) }
        else if *p == *RAYAMMV4 { Some(Venue::RayAmmV4) } else if *p == *DLMM { Some(Venue::Dlmm) } else if *p == *DAMMV2 { Some(Venue::DammV2) } else { None }
    }
    pub fn parse(s: &str) -> Option<Venue> {
        match s { "PumpSwap" => Some(Venue::PumpSwap), "RayCPMM" => Some(Venue::RayCpmm), "RayAMMv4" => Some(Venue::RayAmmV4), "DLMM" => Some(Venue::Dlmm), "DAMMv2" => Some(Venue::DammV2), _ => None }
    }
    /// compute units for one leg (current bot's measured table), before the 1.10 margin
    pub fn leg_cu(&self, crossings: u32) -> u64 {
        match self {
            Venue::PumpSwap => 100_000,
            Venue::RayCpmm => 35_000,
            Venue::RayAmmV4 => 20_000,
            Venue::Dlmm => 47_000 + 5_450 * crossings.max(1) as u64,
            // measured 16,171 by the current bot (FINDINGS B13); it asked ~55k more than used, so a margin, not that much
            Venue::DammV2 => 30_000,
        }
    }
}

/// Static facts about a pool (from the registry / seed list, completed from chain at boot).
#[derive(Debug, Clone)]
pub struct PoolMeta {
    pub venue: Venue,
    pub pool: Pk,
    /// token 0 / token 1 in the program's own order (AMMv4 coin/pc, CPMM mint0/mint1, PumpSwap base/quote, DLMM x/y)
    pub t0: Pk,
    pub t1: Pk,
    pub vault0: Pk,
    pub vault1: Pk,
    pub t0_prog: Pk,
    pub t1_prog: Pk,
    /// venue-specific extra accounts the snapshot needs (CPMM amm_config, PumpSwap fee config + base mint, ...)
    pub extra: Vec<Pk>,
    /// PumpSwap: created by the pump.fun migration (fee tiers apply); DLMM: bitmap extension exists
    pub flag: bool,
}

/// A third party's swap, decoded from its instruction.
#[derive(Debug, Clone)]
pub struct PendingSwap {
    pub pool: Pk,
    pub venue: Venue,
    /// spending token 0 for token 1
    pub zero_for_one: bool,
    /// exact input amount, or the exact output amount when `exact_out`
    pub amount: u64,
    pub exact_out: bool,
    pub user: Pk,
    /// the swap's own slippage bound: minimum output (exact in) or maximum input (exact out); 0 = none we can read.
    /// A trigger whose bound our quote can't meet will fail on chain: no pool move, no gap.
    pub limit: u64,
}

pub fn u16_at(d: &[u8], o: usize) -> Option<u16> { d.get(o..o + 2).map(|b| u16::from_le_bytes([b[0], b[1]])) }
pub fn u32_at(d: &[u8], o: usize) -> Option<u32> { d.get(o..o + 4).map(|b| u32::from_le_bytes(b.try_into().unwrap())) }
pub fn i32_at(d: &[u8], o: usize) -> Option<i32> { d.get(o..o + 4).map(|b| i32::from_le_bytes(b.try_into().unwrap())) }
pub fn u64_at(d: &[u8], o: usize) -> Option<u64> { d.get(o..o + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap())) }
pub fn i64_at(d: &[u8], o: usize) -> Option<i64> { d.get(o..o + 8).map(|b| i64::from_le_bytes(b.try_into().unwrap())) }
pub fn u128_at(d: &[u8], o: usize) -> Option<u128> { d.get(o..o + 16).map(|b| u128::from_le_bytes(b.try_into().unwrap())) }
pub fn pk_at(d: &[u8], o: usize) -> Option<Pk> { d.get(o..o + 32).map(|b| b.try_into().unwrap()) }
/// SPL token account amount
pub fn token_amount(d: &[u8]) -> Option<u64> { if d.len() >= 72 { u64_at(d, 64) } else { None } }

pub fn ceil_div(a: u128, b: u128) -> u128 { if b == 0 { 0 } else { (a + b - 1) / b } }

/// Find the smallest input whose quote reaches `want` (exact-out swaps), by doubling then bisection.
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

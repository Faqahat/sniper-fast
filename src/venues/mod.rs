//! Venues: pool metadata, the venues' program ids, and decoding of a third party's swap instruction. The venue
//! maths (exact-in quotes, capacities, the walk over DLMM bins) is arbx-sizing's, through `src/quote.rs`
//! (PLAN-ADDENDUM WP-16: one pricing implementation, the one proven against the real venue binaries, on chain and off
//! chain); the accuracy monitor checks every prediction against the pool's real next state, so any remaining mismatch
//! is measured, not assumed. The engine's own maths before WP-16 is kept, for the differential tests only, in
//! `legacy`.
pub mod clmm;
pub mod cp;
pub mod dlmm;
#[cfg(test)]
pub mod legacy;

use crate::tx::{pk, Pk};
use std::sync::LazyLock;

pub static PUMPSWAP: LazyLock<Pk> = LazyLock::new(|| pk("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"));
pub static RAYCPMM: LazyLock<Pk> = LazyLock::new(|| pk("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C"));
pub static RAYAMMV4: LazyLock<Pk> = LazyLock::new(|| pk("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8"));
pub static DLMM: LazyLock<Pk> = LazyLock::new(|| pk("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo"));
pub static DAMMV2: LazyLock<Pk> = LazyLock::new(|| pk("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"));
/// PLAN-ADDENDUM WP-21: Raydium CLMM and Orca Whirlpool (`swap_v2`, arbx-sizing kinds 7 and 8; DESIGN.md §9)
pub static RAYCLMM: LazyLock<Pk> = LazyLock::new(|| pk("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK"));
pub static WHIRLPOOL: LazyLock<Pk> = LazyLock::new(|| pk("whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc"));
pub static WSOL: LazyLock<Pk> = LazyLock::new(|| pk("So11111111111111111111111111111111111111112"));

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, serde::Serialize)]
pub enum Venue { PumpSwap, RayCpmm, RayAmmV4, Dlmm, DammV2,
    /// Raydium CLMM (PLAN-ADDENDUM WP-21; seed lists name it `RayCLMM`)
    RayClmm,
    /// Orca Whirlpool (PLAN-ADDENDUM WP-21; seed lists name it `Whirlpool`)
    Whirlpool }

impl Venue {
    pub fn program(&self) -> Pk {
        match self { Venue::PumpSwap => *PUMPSWAP, Venue::RayCpmm => *RAYCPMM, Venue::RayAmmV4 => *RAYAMMV4, Venue::Dlmm => *DLMM, Venue::DammV2 => *DAMMV2,
            Venue::RayClmm => *RAYCLMM, Venue::Whirlpool => *WHIRLPOOL }
    }
    pub fn of_program(p: &Pk) -> Option<Venue> {
        if *p == *PUMPSWAP { Some(Venue::PumpSwap) } else if *p == *RAYCPMM { Some(Venue::RayCpmm) }
        else if *p == *RAYAMMV4 { Some(Venue::RayAmmV4) } else if *p == *DLMM { Some(Venue::Dlmm) } else if *p == *DAMMV2 { Some(Venue::DammV2) }
        else if *p == *RAYCLMM { Some(Venue::RayClmm) } else if *p == *WHIRLPOOL { Some(Venue::Whirlpool) } else { None }
    }
    pub fn parse(s: &str) -> Option<Venue> {
        match s { "PumpSwap" => Some(Venue::PumpSwap), "RayCPMM" => Some(Venue::RayCpmm), "RayAMMv4" => Some(Venue::RayAmmV4), "DLMM" => Some(Venue::Dlmm), "DAMMv2" => Some(Venue::DammV2),
            "RayCLMM" => Some(Venue::RayClmm), "Whirlpool" => Some(Venue::Whirlpool), _ => None }
    }
    /// the five venues traded before WP-21, then the CLMM venues
    pub const ALL: [Venue; 7] = [Venue::PumpSwap, Venue::RayCpmm, Venue::RayAmmV4, Venue::Dlmm, Venue::DammV2, Venue::RayClmm, Venue::Whirlpool];
    /// Raydium CLMM or Orca Whirlpool (PLAN-ADDENDUM WP-21)
    pub fn is_clmm(&self) -> bool { matches!(self, Venue::RayClmm | Venue::Whirlpool) }
    /// a venue whose exact quote walks (DLMM bins, CLMM swap steps) over arrays the engine follows around the price
    pub fn walks(&self) -> bool { matches!(self, Venue::Dlmm | Venue::RayClmm | Venue::Whirlpool) }
    /// compute units for one leg (current bot's measured table), before the 1.10 margin. `crossings`: DLMM the bins with
    /// liquidity the leg takes from; Raydium CLMM and Orca Whirlpool the swap steps of its exact walk (`quote::Quoted`
    /// `crossed`; a dynamic or adaptive fee adds steps without a crossing, so steps, not crossings: DESIGN.md §9.0 item 6)
    pub fn leg_cu(&self, crossings: u32) -> u64 {
        match self {
            Venue::PumpSwap => 100_000,
            Venue::RayCpmm => 35_000,
            Venue::RayAmmV4 => 20_000,
            Venue::Dlmm => 47_000 + 5_450 * crossings.max(1) as u64,
            // measured 16,171 by the current bot (FINDINGS B13); it asked ~55k more than used, so a margin, not that much
            Venue::DammV2 => 30_000,
            // the venue harness on the deployed binaries (DESIGN.md §2.8, §2.9): every exact swap within these bounds
            // (Raydium ≈41.5k + 9.1k per tick crossed + 8.5k per other step; Orca ≈28-30k + 7.0k + 8.6k)
            Venue::RayClmm => 64_000 + 10_000 * crossings.max(1) as u64,
            Venue::Whirlpool => 48_000 + 10_000 * crossings.max(1) as u64,
        }
    }
}

/// Static facts about a pool (from the registry / seed list, completed from chain at boot).
#[derive(Debug, Clone)]
pub struct PoolMeta {
    pub venue: Venue,
    pub pool: Pk,
    /// token 0 / token 1 in the program's own order (AMMv4 coin/pc, CPMM mint0/mint1, PumpSwap base/quote, DLMM x/y,
    /// Raydium CLMM token_mint_0/1, Orca Whirlpool token_mint_a/b)
    pub t0: Pk,
    pub t1: Pk,
    pub vault0: Pk,
    pub vault1: Pk,
    pub t0_prog: Pk,
    pub t1_prog: Pk,
    /// venue-specific extra accounts the snapshot needs (CPMM amm_config, PumpSwap fee config + base mint, ...). WP-21
    /// (DESIGN.md §9.0 item 2): Raydium CLMM `[amm_config, the TickArrayBitmapExtension PDA]`, Orca Whirlpool `[the Oracle
    /// PDA]` (`clmm_config`, `clmm_ext`, `whirl_oracle`); the extension and the oracle may not exist (the store then holds
    /// them empty). The tick spacing and Raydium's observation account are read from the pool account itself
    /// (`clmm::tick_spacing`, `clmm::observation`): pools.json and every journaled registry carry `extra` unchanged, so a
    /// replay rebuilds the same metadata
    pub extra: Vec<Pk>,
    /// PumpSwap: created by the pump.fun migration (fee tiers apply); DLMM: bitmap extension exists
    pub flag: bool,
}

impl PoolMeta {
    /// Raydium CLMM: the pool's AmmConfig (`extra[0]`, the key the pool names at @9)
    pub fn clmm_config(&self) -> Option<&Pk> { (self.venue == Venue::RayClmm).then(|| self.extra.first()).flatten() }
    /// Raydium CLMM: the TickArrayBitmapExtension PDA (`extra[1]`; it may not exist)
    pub fn clmm_ext(&self) -> Option<&Pk> { (self.venue == Venue::RayClmm).then(|| self.extra.get(1)).flatten() }
    /// Orca Whirlpool: the Oracle PDA (`extra[0]`; it does not exist on a pool without the adaptive fee)
    pub fn whirl_oracle(&self) -> Option<&Pk> { (self.venue == Venue::Whirlpool).then(|| self.extra.first()).flatten() }
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

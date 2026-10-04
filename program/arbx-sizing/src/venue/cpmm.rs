//! Raydium CPMM (CPMMoo8L…) `swap_base_input` (DESIGN.md §2.2, raydium-cp-swap b3187ae).
use crate::error::{Abort, CpmmWhy, Quote, QuoteErr};
use crate::fx::Fx;
use crate::math::{ceil_div, div, u64_at, u8_at};

pub const POOL_LEN: usize = 637;
pub const CONFIG_LEN: usize = 236;
const RATE: u128 = 1_000_000;

pub mod off {
    pub const AMM_CONFIG: usize = 8;
    pub const VAULT0: usize = 72;
    pub const VAULT1: usize = 104;
    pub const MINT0: usize = 168;
    pub const MINT1: usize = 200;
    pub const STATUS: usize = 329;
    pub const PROTOCOL0: usize = 341;
    pub const PROTOCOL1: usize = 349;
    pub const FUND0: usize = 357;
    pub const FUND1: usize = 365;
    pub const OPEN_TIME: usize = 373;
    pub const CREATOR_FEE_ON: usize = 389;
    pub const ENABLE_CREATOR_FEE: usize = 390;
    pub const CREATOR0: usize = 397;
    pub const CREATOR1: usize = 405;
    // AmmConfig
    pub const C_TRADE: usize = 12;
    pub const C_PROTOCOL: usize = 20;
    pub const C_FUND: usize = 28;
    pub const C_CREATOR: usize = 108;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct CpmmLeg {
    pub r_in: u64,
    pub r_out: u64,
    /// fee rate (1e6) taken off the input: trade, plus the creator fee when it is charged on the input (ONE ceil)
    pub fee_in: u64,
    /// creator fee rate (1e6) taken off the output when it is charged on the output
    pub fee_out: u64,
}

/// `vault0`/`vault1`: the token-0/token-1 vault amounts. `now`: the Clock's unix timestamp.
pub fn parse(pool: &[u8], cfg: &[u8], vault0: u64, vault1: u64, zero_for_one: bool, now: i64) -> Result<CpmmLeg, Abort> {
    if pool.len() != POOL_LEN || cfg.len() != CONFIG_LEN { return Err(Abort::Layout); }
    let g = |o| u64_at(pool, o).ok_or(Abort::Layout);
    let status = u8_at(pool, off::STATUS).ok_or(Abort::Layout)?;
    if (status >> 2) & 1 != 0 { return Err(Abort::Cpmm(CpmmWhy::SwapDisabled)); }
    if (now as i128) < g(off::OPEN_TIME)? as i128 { return Err(Abort::Cpmm(CpmmWhy::NotOpen)); }
    let owed0 = g(off::PROTOCOL0)? as u128 + g(off::FUND0)? as u128 + g(off::CREATOR0)? as u128;
    let owed1 = g(off::PROTOCOL1)? as u128 + g(off::FUND1)? as u128 + g(off::CREATOR1)? as u128;
    let r0 = (vault0 as u128).checked_sub(owed0).ok_or(Abort::Cpmm(CpmmWhy::OwedExceedsVault))? as u64;
    let r1 = (vault1 as u128).checked_sub(owed1).ok_or(Abort::Cpmm(CpmmWhy::OwedExceedsVault))? as u64;
    let (r_in, r_out) = if zero_for_one { (r0, r1) } else { (r1, r0) };
    if r_in == 0 || r_out == 0 { return Err(Abort::Cpmm(CpmmWhy::EmptyReserves)); }
    let trade = u64_at(cfg, off::C_TRADE).ok_or(Abort::Layout)?;
    let enabled = u8_at(pool, off::ENABLE_CREATOR_FEE).ok_or(Abort::Layout)? != 0;
    let creator = if enabled { u64_at(cfg, off::C_CREATOR).ok_or(Abort::Layout)? } else { 0 };
    let on = u8_at(pool, off::CREATOR_FEE_ON).ok_or(Abort::Layout)?;
    if on > 2 { return Err(Abort::Cpmm(CpmmWhy::CreatorFeeOn)); }
    let on_input = on == 0 || (on == 1 && zero_for_one) || (on == 2 && !zero_for_one);
    let (fee_in, fee_out) = if on_input { (trade.checked_add(creator).ok_or(Abort::Math)?, 0) } else { (trade, creator) };
    if fee_in as u128 >= RATE || fee_out as u128 >= RATE { return Err(Abort::Cpmm(CpmmWhy::Fee)); }
    Ok(CpmmLeg { r_in, r_out, fee_in, fee_out })
}

impl CpmmLeg {
    pub fn quote(&self, x: u64) -> Result<Quote, QuoteErr> {
        if x == 0 { return Err(QuoteErr::ZeroOut); }
        let xx = x as u128;
        let fee = ceil_div(xx * self.fee_in as u128, RATE).ok_or(QuoteErr::Abort(Abort::Math))?;
        let net = xx - fee;
        if net == 0 { return Err(QuoteErr::ZeroOut); }
        let gross = div(net * self.r_out as u128, self.r_in as u128 + net).ok_or(QuoteErr::Abort(Abort::Math))?;
        let out = gross - ceil_div(gross * self.fee_out as u128, RATE).ok_or(QuoteErr::Abort(Abort::Math))?;
        if out == 0 { return Err(QuoteErr::ZeroOut); }
        Ok(Quote { out: out as u64, spent: x })
    }

    pub fn model(&self) -> (Fx, Fx, Fx) {
        let one = Fx::from_u64(RATE as u64);
        let g = one.sub(Fx::from_u64(self.fee_in)).div(one);
        let h = one.sub(Fx::from_u64(self.fee_out)).div(one);
        (h.mul(g).mul(Fx::from_u64(self.r_out)), Fx::from_u64(self.r_in), g)
    }
}

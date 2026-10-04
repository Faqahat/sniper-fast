//! Raydium AMM v4 (675kPX9M…) `swap_base_in_v2` (DESIGN.md §2.3).
use crate::error::{Abort, AmmWhy, Quote, QuoteErr};
use crate::fx::Fx;
use crate::math::{ceil_div, div, u64_at};

pub const AMM_LEN: usize = 752;

pub mod off {
    pub const STATUS: usize = 0;
    pub const SWAP_FEE_NUM: usize = 176;
    pub const SWAP_FEE_DEN: usize = 184;
    pub const PNL_COIN: usize = 192;
    pub const PNL_PC: usize = 200;
    pub const OPEN_TIME: usize = 224;
    pub const COIN_VAULT: usize = 336;
    pub const PC_VAULT: usize = 368;
    pub const COIN_MINT: usize = 400;
    pub const PC_MINT: usize = 432;
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AmmLeg { pub r_in: u64, pub r_out: u64, pub num: u64, pub den: u64 }

/// `coin`/`pc`: the vault amounts. `coin_in`: the coin side is the input.
pub fn parse(amm: &[u8], coin: u64, pc: u64, coin_in: bool, now: i64) -> Result<AmmLeg, Abort> {
    if amm.len() != AMM_LEN { return Err(Abort::Layout); }
    let g = |o| u64_at(amm, o).ok_or(Abort::Layout);
    let status = g(off::STATUS)?;
    let open = status == 1 || status == 6 || (status == 7 && now as i128 >= g(off::OPEN_TIME)? as i128);
    if !open { return Err(Abort::Amm(AmmWhy::Status)); }
    let (num, den) = (g(off::SWAP_FEE_NUM)?, g(off::SWAP_FEE_DEN)?);
    if den == 0 || num >= den { return Err(Abort::Amm(AmmWhy::Fee)); }
    let r_coin = coin.checked_sub(g(off::PNL_COIN)?).ok_or(Abort::Amm(AmmWhy::PnlExceedsVault))?;
    let r_pc = pc.checked_sub(g(off::PNL_PC)?).ok_or(Abort::Amm(AmmWhy::PnlExceedsVault))?;
    let (r_in, r_out) = if coin_in { (r_coin, r_pc) } else { (r_pc, r_coin) };
    if r_in == 0 || r_out == 0 { return Err(Abort::Amm(AmmWhy::EmptyReserves)); }
    Ok(AmmLeg { r_in, r_out, num, den })
}

impl AmmLeg {
    pub fn quote(&self, x: u64) -> Result<Quote, QuoteErr> {
        if x == 0 { return Err(QuoteErr::ZeroOut); }
        let xx = x as u128;
        let net = xx - ceil_div(xx * self.num as u128, self.den as u128).ok_or(QuoteErr::Abort(Abort::Math))?;
        let out = div(self.r_out as u128 * net, self.r_in as u128 + net).ok_or(QuoteErr::Abort(Abort::Math))?;
        if out == 0 { return Err(QuoteErr::ZeroOut); }
        if out >= self.r_out as u128 { return Err(QuoteErr::TooLarge); }
        Ok(Quote { out: out as u64, spent: x })
    }

    pub fn model(&self) -> (Fx, Fx, Fx) {
        let den = Fx::from_u64(self.den);
        let g = den.sub(Fx::from_u64(self.num)).div(den);
        (g.mul(Fx::from_u64(self.r_out)), Fx::from_u64(self.r_in), g)
    }
}

//! PumpSwap (pAMMBay6…): fee selection, exact `sell` and `buy_exact_quote_in`, the model and the exact sell capacity
//! (DESIGN.md §2.1). The formulas match the program's own Buy/SellEvents (112/112 in the design research; the
//! integration tests re-check them on tests/data/pump-events.json).
use crate::error::{Abort, PumpWhy, Quote, QuoteErr};
use crate::fx::Fx;
use crate::layout::{T22_NATIVE, USDC, WSOL};
use crate::math::{ceil_div, div, i128_at, key_at, u32_at, u64_at, u8_at, ZERO_KEY};

/// The Pool account's current length: the IDL's fields end at 271 (`is_holder_reward` @270, pump-public-docs
/// idl/pump_amm.json, 2026-09-12), the two held-back quote amounts at 287, then 14 unidentified bytes. A pool written
/// before a trailing field existed is shorter (mainnet: 287, 300 and 301 bytes) and the program reads each trailing
/// group it does not hold whole as zero / false (pump.fun PUMP_SWAP_README: "read the missing trailing fields as 0 /
/// false"; the groups are pinned on the dumped binary, `off`). A longer pool is an unknown layout: `Abort::Layout`, so
/// the next extension turns sizing off instead of mispricing (REVIEW.md F9; WP-16 review F1).
pub const POOL_LEN: usize = 301;
/// The shortest pool the program accepts: the original layout (bump .. lp_supply). Below it the program fails
/// InvalidAccountData (pinned on the dumped binary at 204, 208 and 210 bytes; it swaps from 211 on)
pub const POOL_MIN_LEN: usize = 211;
/// The pool lengths the crate prices: the program's minimum up to the current layout
pub fn pool_len_ok(len: usize) -> bool { (POOL_MIN_LEN..=POOL_LEN).contains(&len) }
/// The fixed base supply a mayhem pool's market cap is computed on (SDK `computeFeesBps`; pinned on the dumped
/// binary: GxqG priced on 1e15 with its mint's supply scaled ×1/1000 to ×2000)
pub const MAYHEM_SUPPLY: u64 = 1_000_000_000_000_000;
pub const GLOBAL_LEN: usize = 949;
pub const FEE_CONFIG_LEN: usize = 4097;
const BPS: u128 = 10_000;
const MAX_TIERS: usize = 64;

pub mod off {
    pub const CREATOR: usize = 11;
    pub const BASE_MINT: usize = 43;
    pub const QUOTE_MINT: usize = 75;
    pub const BASE_VAULT: usize = 139;
    pub const QUOTE_VAULT: usize = 171;
    pub const COIN_CREATOR: usize = 211;
    // Trailing fields: the program reads each one only when the pool holds all of it (pinned on the dumped binary by
    // cutting pools to every boundary ±1: a partial virtual reserve reads as 0, creator_fee_bps is read together
    // with can_edit_creator_fee, and the two held amounts together)
    pub const MAYHEM: usize = 243;
    pub const CASHBACK: usize = 244;
    pub const VIRTUAL_QUOTE: usize = 245;
    pub const CREATOR_FEE_BPS: usize = 261;
    pub const CAN_EDIT_CREATOR_FEE: usize = 269;
    /// `is_holder_reward: bool` (pump-public-docs idl/pump_amm.json): holder rewards redirect the creator fee and
    /// change no trade amount (HOLDER_REWARDS_README: "no changes to any trade instruction"); exact on the dumped
    /// binary on holder-reward pools. A byte other than 0 or 1 is no Borsh bool: the program fails to deserialize
    pub const IS_HOLDER_REWARD: usize = 270;
    /// Two u64 quote amounts the program holds back from the real quote vault (in no IDL; most likely the unswept
    /// protocol and creator fee buckets, cf. SweepProtocolFee / SweepCreatorFee). A sell must satisfy
    /// `q − ⌈q·lp/1e4⌉ ≤ Q − (held_0 + held_1)` (6063 InsufficientRealQuoteReserves otherwise), pinned by bisection on
    /// the dumped binary (REVIEW.md F1)
    pub const HELD_0: usize = 271;
    pub const HELD_1: usize = 279;
    /// unidentified tail bytes 287..301 (zero on every pool seen); a nonzero byte → Abort
    pub const TAIL_UNKNOWN: usize = 287;
    /// where the program's read groups end (a group is read only when the pool holds all of it)
    pub const END_COIN_CREATOR: usize = 243;
    pub const END_VIRTUAL_QUOTE: usize = 261;
    pub const END_CREATOR_FEE: usize = 270;
    pub const END_HELD: usize = 287;
    // GlobalConfig
    pub const G_LP: usize = 40;
    pub const G_PROTOCOL: usize = 48;
    pub const G_DISABLE: usize = 56;
    pub const G_COIN_CREATOR: usize = 313;
    pub const G_BUYBACK: usize = 899;
    pub const G_CREATOR_FEE_CONFIGURABLE: usize = 940;
    pub const G_MAX_CREATOR_FEE: usize = 941;
    // FeeConfig (Borsh, sequential)
    pub const F_FLAT: usize = 41;
    pub const F_TIERS: usize = 65;
}

/// Fee rates in basis points
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct PumpFees { pub lp: u64, pub protocol: u64, pub creator: u64 }

impl PumpFees {
    pub fn total(&self) -> u128 { self.lp as u128 + self.protocol as u128 + self.creator as u128 }
    fn read(d: &[u8], o: usize) -> Option<PumpFees> {
        Some(PumpFees { lp: u64_at(d, o)?, protocol: u64_at(d, o + 8)?, creator: u64_at(d, o + 16)? })
    }
    /// ⌈e·lp/1e4⌉ + ⌈e·protocol/1e4⌉ + ⌈e·creator/1e4⌉ (each rounded up separately)
    fn charged(&self, e: u128) -> Option<u128> {
        let f = |bps: u64| ceil_div(e.checked_mul(bps as u128)?, BPS);
        f(self.lp)?.checked_add(f(self.protocol)?)?.checked_add(f(self.creator)?)
    }
}

/// The quote mint's fee schedule
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum QuoteKind { SolLike, Usdc, Other }

pub fn quote_kind(mint: &[u8; 32]) -> QuoteKind {
    if *mint == ZERO_KEY || *mint == WSOL || *mint == T22_NATIVE { QuoteKind::SolLike } else if *mint == USDC { QuoteKind::Usdc } else { QuoteKind::Other }
}

/// One tier list of the FeeConfig: (start offset of the u32 length, count). Bounds-checked.
fn tier_list(fc: &[u8], at: usize) -> Option<(usize, usize)> {
    let n = u32_at(fc, at)? as usize;
    if n > MAX_TIERS { return None; }
    let end = at.checked_add(4)?.checked_add(n.checked_mul(40)?)?;
    if end > fc.len() { return None; }
    Some((at + 4, n))
}

/// tier 0 below the first threshold, else the last tier whose threshold ≤ mc (calculateFeeTier)
fn pick_tier(fc: &[u8], start: usize, n: usize, mc: u128) -> Option<PumpFees> {
    if n == 0 { return None; }
    let th = |i: usize| crate::math::u128_at(fc, start + 40 * i);
    if mc < th(0)? { return PumpFees::read(fc, start + 16); }
    for i in (0..n).rev() {
        if mc >= th(i)? { return PumpFees::read(fc, start + 40 * i + 16); }
    }
    PumpFees::read(fc, start + 16)
}

/// FeeConfig fees (compute_fees): flat for a non-canonical pool; for a canonical pool the market-cap tiers (SOL-like
/// quote), the stable tiers (USDC; the SOL tiers if the stable list is empty), or the exotic flat fees (any other
/// quote; the flat fees when exotic is all zero).
pub fn fee_config_fees(fc: &[u8], canonical: bool, qk: QuoteKind, mc: u128) -> Result<PumpFees, Abort> {
    let bad = Abort::Pump(PumpWhy::FeeConfig);
    let flat = PumpFees::read(fc, off::F_FLAT).ok_or(bad)?;
    if !canonical { return Ok(flat); }
    let (t_start, t_n) = tier_list(fc, off::F_TIERS).ok_or(bad)?;
    let (s_start, s_n) = tier_list(fc, t_start + 40 * t_n).ok_or(bad)?;
    match qk {
        QuoteKind::SolLike => pick_tier(fc, t_start, t_n, mc).ok_or(bad),
        QuoteKind::Usdc => {
            if s_n > 0 { pick_tier(fc, s_start, s_n, mc).ok_or(bad) } else { pick_tier(fc, t_start, t_n, mc).ok_or(bad) }
        }
        QuoteKind::Other => {
            let exotic = PumpFees::read(fc, s_start + 40 * s_n).ok_or(bad)?;
            Ok(if exotic == PumpFees::default() { flat } else { exotic })
        }
    }
}

/// A parsed PumpSwap leg
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct PumpLeg {
    /// sell (base in, quote out) or buy_exact_quote_in (quote in, base out)
    pub sell: bool,
    /// base vault amount B
    pub base: u64,
    /// the real quote a sell can pay out: the quote vault amount Q minus the amounts the pool holds back (sell legs;
    /// Q for a buy leg, where it is not read)
    pub quote: u64,
    /// Q + V (virtual quote reserve), in (0, 2^64)
    pub qv: u64,
    pub fees: PumpFees,
}

/// A pool's Borsh bool at `o`: false when the pool ends before it; a byte other than 0 or 1 fails the program's
/// deserialization (BorshIoError "Invalid bool representation"), so it is `Abort::Layout`
fn bool_at(pool: &[u8], o: usize) -> Result<bool, Abort> {
    match pool.get(o) { None | Some(0) => Ok(false), Some(1) => Ok(true), Some(_) => Err(Abort::Layout) }
}

/// The pool's trailing group `off..end` when the pool holds all of it (the program reads the group as zero / false
/// otherwise)
fn group(pool: &[u8], off: usize, end: usize) -> Option<&[u8]> { pool.get(off..end) }

/// Parse a PumpSwap leg from the account bytes (owner/key checks are the caller's). `base_supply` is the base mint's
/// supply; `canonical` = the pool's creator is pump.fun's pool-authority PDA for the base mint. A pool of any length
/// from [`POOL_MIN_LEN`] to [`POOL_LEN`] is read as the program reads it: each trailing group it holds whole, the
/// others as zero / false.
pub fn parse(pool: &[u8], global: &[u8], fee_cfg: &[u8], base_supply: u64, quote_mint: &[u8; 32], base_amount: u64, quote_amount: u64,
             sell: bool, canonical: bool) -> Result<PumpLeg, Abort> {
    if !pool_len_ok(pool.len()) || global.len() != GLOBAL_LEN || fee_cfg.len() != FEE_CONFIG_LEN { return Err(Abort::Layout); }
    let mayhem = bool_at(pool, off::MAYHEM)?;
    let cashback = bool_at(pool, off::CASHBACK)?;
    bool_at(pool, off::CAN_EDIT_CREATOR_FEE)?;
    bool_at(pool, off::IS_HOLDER_REWARD)?;
    if pool.get(off::TAIL_UNKNOWN..).is_some_and(|t| t.iter().any(|&x| x != 0)) { return Err(Abort::Pump(PumpWhy::UnknownTail)); }
    if cashback { return Err(Abort::Pump(PumpWhy::Cashback)); }
    let disable = u8_at(global, off::G_DISABLE).ok_or(Abort::Layout)?;
    if disable & if sell { 1 << 4 } else { 1 << 3 } != 0 { return Err(Abort::Pump(PumpWhy::Disabled)); }
    let v = group(pool, off::VIRTUAL_QUOTE, off::END_VIRTUAL_QUOTE).map_or(Some(0), |g| i128_at(g, 0)).ok_or(Abort::Layout)?;
    let qv = (quote_amount as i128).checked_add(v).ok_or(Abort::Pump(PumpWhy::Virtual))?;
    if qv <= 0 || qv > u64::MAX as i128 { return Err(Abort::Pump(PumpWhy::Virtual)); }
    let qv = qv as u64;
    if base_amount == 0 { return Err(Abort::Pump(PumpWhy::EmptyReserves)); }
    // a mayhem pool's market cap is on the fixed supply
    let supply = if mayhem { MAYHEM_SUPPLY } else { base_supply };
    let mc = (qv as u128).checked_mul(supply as u128).ok_or(Abort::Math)? / base_amount as u128;
    let mut fees = fee_config_fees(fee_cfg, canonical, quote_kind(quote_mint), mc)?;
    let configurable = u8_at(global, off::G_CREATOR_FEE_CONFIGURABLE).ok_or(Abort::Layout)? != 0;
    // creator_fee_bps is read with can_edit_creator_fee (one group, @261..270)
    let pool_creator_bps = group(pool, off::CREATOR_FEE_BPS, off::END_CREATOR_FEE).map_or(Some(0), |g| u64_at(g, 0)).ok_or(Abort::Layout)?;
    if configurable && pool_creator_bps > 0 { fees.creator = pool_creator_bps; }
    if group(pool, off::COIN_CREATOR, off::END_COIN_CREATOR).map_or(true, |g| g == ZERO_KEY) { fees.creator = 0; }
    if fees.total() >= BPS { return Err(Abort::Pump(PumpWhy::FeeTotal)); }
    // the program subtracts the held amounts from the vault on both instructions (a buy fails 6023 Overflow when they
    // exceed it); only a sell's payout is bounded by the difference. Both are one group (@271..287)
    let held = match group(pool, off::HELD_0, off::END_HELD) {
        Some(g) => u64_at(g, 0).ok_or(Abort::Layout)? as u128 + u64_at(g, 8).ok_or(Abort::Layout)? as u128,
        None => 0,
    };
    let avail = u64::try_from((quote_amount as u128).checked_sub(held).ok_or(Abort::Pump(PumpWhy::HeldExceedsVault))?).map_err(|_| Abort::Math)?;
    let quote = if sell { avail } else { quote_amount };
    Ok(PumpLeg { sell, base: base_amount, quote, qv, fees })
}

/// The canonical pool test: creator == create_program_address(["pool-authority", base_mint, [bump]], pump.fun).
/// A bump of 0 means "not canonical".
pub fn is_canonical(pool: &[u8], bump: u8, pda: crate::PdaFn) -> bool {
    if bump == 0 { return false; }
    let (Some(creator), Some(base)) = (key_at(pool, off::CREATOR), key_at(pool, off::BASE_MINT)) else { return false };
    pda(&[b"pool-authority", base.as_slice(), &[bump]], &crate::layout::PUMP_FUN).as_ref() == Some(creator)
}

/// sell, base in `b`: q = ⌊Qv·b/(B+b)⌋, fees ⌈q·bps/1e4⌉ each; requires q − lp_fee ≤ `quote` (the real quote
/// reserve net of the held-back amounts).
pub fn sell_quote(base: u64, quote: u64, qv: u64, f: &PumpFees, b: u64) -> Result<Quote, QuoteErr> {
    if b == 0 { return Err(QuoteErr::ZeroOut); }
    let q = div(qv as u128 * b as u128, base as u128 + b as u128).ok_or(QuoteErr::Abort(Abort::Math))?;
    let lp = ceil_div(q * f.lp as u128, BPS).ok_or(QuoteErr::Abort(Abort::Math))?;
    if q - lp.min(q) > quote as u128 { return Err(QuoteErr::TooLarge); }
    let fees = f.charged(q).ok_or(QuoteErr::Abort(Abort::Math))?;
    let out = q.checked_sub(fees).ok_or(QuoteErr::ZeroOut)?;
    if out == 0 { return Err(QuoteErr::ZeroOut); }
    Ok(Quote { out: out as u64, spent: b })
}

/// buy_exact_quote_in, quote in `x`: eff0 = ⌊x·1e4/(1e4+F)⌋, eff = eff0 − max(0, eff0 + fees(eff0) − x),
/// out = ⌊B·(eff−1)/(Qv+eff−1)⌋. The program debits eff0 + fees(eff0) when that is below `x` (it keeps the fees of
/// eff0 and lowers eff only on an overrun, where it debits exactly `x`): spent = min(x, eff0 + fees(eff0))
/// (venue-harness tests/pins.rs; REVIEW.md F2).
pub fn buy_quote(base: u64, qv: u64, f: &PumpFees, x: u64) -> Result<Quote, QuoteErr> {
    if x == 0 { return Err(QuoteErr::ZeroOut); }
    let xx = x as u128;
    let eff0 = div(xx * BPS, BPS + f.total()).ok_or(QuoteErr::Abort(Abort::Math))?;
    let debit = eff0 + f.charged(eff0).ok_or(QuoteErr::Abort(Abort::Math))?;
    let eff = eff0.saturating_sub(debit.saturating_sub(xx));
    if eff <= 1 { return Err(QuoteErr::ZeroOut); }
    let out = div(base as u128 * (eff - 1), qv as u128 + eff - 1).ok_or(QuoteErr::Abort(Abort::Math))?;
    if out == 0 { return Err(QuoteErr::ZeroOut); }
    if out >= base as u128 { return Err(QuoteErr::TooLarge); }
    Ok(Quote { out: out as u64, spent: debit.min(xx) as u64 })
}

/// `buy` (base out exact: the exact-out instruction third parties send): `out` base units for a debit of
/// `q + ⌈q·lp/1e4⌉ + ⌈q·pr/1e4⌉ + ⌈q·cr/1e4⌉`, `q = ⌈Qv·out/(B − out)⌉`; returns `q` (the quote that enters the curve)
/// and the quote. Pinned on the dumped binary (venue-harness tests/pins.rs `pumpswap_exact_out_buy_matches_its_closed_form`,
/// 11,477 buys exact to the unit). `ZeroOut` for 0 (6001 ZeroBaseAmount); `TooLarge` for the whole base reserve or more
/// and for a quote amount or debit past u64 (6024 Truncation, 6023 Overflow). Host only: on-chain sizing quotes exact
/// in; the engine prices third parties' `buy`s with it (WP-16 review F6)
pub fn buy_exact_out(base: u64, qv: u64, f: &PumpFees, out: u64) -> Result<(u64, Quote), QuoteErr> {
    if out == 0 { return Err(QuoteErr::ZeroOut); }
    if out >= base { return Err(QuoteErr::TooLarge); }
    let q = ceil_div(qv as u128 * out as u128, (base - out) as u128).ok_or(QuoteErr::Abort(Abort::Math))?;
    let q = u64::try_from(q).map_err(|_| QuoteErr::TooLarge)?;
    let debit = (q as u128).checked_add(f.charged(q as u128).ok_or(QuoteErr::Abort(Abort::Math))?).ok_or(QuoteErr::Abort(Abort::Math))?;
    let debit = u64::try_from(debit).map_err(|_| QuoteErr::TooLarge)?;
    Ok((q, Quote { out, spent: debit }))
}

impl PumpLeg {
    /// A buy leg's exact-out quote ([`buy_exact_out`]): (q, the quote); a sell leg has none (`Abort::Unsupported`)
    pub fn quote_exact_out(&self, out: u64) -> Result<(u64, Quote), QuoteErr> {
        if self.sell { return Err(QuoteErr::Abort(Abort::Unsupported)); }
        buy_exact_out(self.base, self.qv, &self.fees, out)
    }

    pub fn quote(&self, amount_in: u64) -> Result<Quote, QuoteErr> {
        if self.sell { sell_quote(self.base, self.quote, self.qv, &self.fees, amount_in) } else { buy_quote(self.base, self.qv, &self.fees, amount_in) }
    }

    /// Möbius model `out(u) = A·u/(B' + C·u)`
    pub fn model(&self) -> (Fx, Fx, Fx) {
        let ften = Fx::from_u64(10_000);
        let f = Fx::from_u128(self.fees.total());
        if self.sell {
            (ften.sub(f).div(ften).mul(Fx::from_u64(self.qv)), Fx::from_u64(self.base), Fx::ONE)
        } else {
            let psi = ften.div(ften.add(f));
            (psi.mul(Fx::from_u64(self.base)), Fx::from_u64(self.qv), psi)
        }
    }

    /// Sell: the largest base input whose quote passes the real-reserve check (exact, closed form; Q net of the
    /// held-back amounts): q − ⌈q·lp/1e4⌉ ≤ Q ⟺ q ≤ q_max = ⌈(Q+1)·1e4/(1e4−lp)⌉ − 1, and ⌊Qv·b/(B+b)⌋ ≤ q_max ⟺
    /// b ≤ ⌈(q_max+1)·B/(Qv−q_max−1)⌉ − 1 (unbounded when Qv ≤ q_max + 1). Buy: None (unbounded).
    pub fn cap_in(&self) -> Option<u64> {
        if !self.sell { return None; }
        let lp = self.fees.lp as u128;
        let q_max = ceil_div((self.quote as u128 + 1) * BPS, BPS - lp)? - 1;
        let qv = self.qv as u128;
        if qv <= q_max + 1 { return None; }
        let b = ceil_div((q_max + 1).checked_mul(self.base as u128)?, qv - q_max - 1)? - 1;
        Some(u64::try_from(b).unwrap_or(u64::MAX))
    }
}

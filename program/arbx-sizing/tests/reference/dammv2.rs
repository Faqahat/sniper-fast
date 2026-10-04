//! READ-ONLY COPY of /home/moiz/arbed/arbx/src/venues/dammv2.rs (2026-10-04) for the differential tests.
//! Adapted only where the crate context is missing: imports point at `super` (tests/reference/mod.rs), the
//! third-party-swap decoders (which need the engine's PendingSwap/PoolMeta) and the in-file tests are dropped.
//! The maths is byte-for-byte the engine's.
#![allow(dead_code, clippy::all)]
// The whole program-facing API (instruction account indices, swap2 modes, exact-out) is public for the engine; not
// every item is wired yet.
use super::{pk_at, u128_at, u16_at, u32_at, u64_at, Pk};
use std::cmp::Ordering;

pub const PROGRAM: &str = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG";
/// Pool::INIT_SPACE 1104 + the 8-byte Anchor discriminator
pub const POOL_SIZE: usize = 1112;
/// sha256("account:Pool")[..8]
pub const POOL_DISCRIMINATOR: [u8; 8] = [0xf1, 0x9a, 0x6d, 0x04, 0x11, 0xb1, 0x6d, 0xbc];
/// sha256("global:swap")[..8]: amount_in u64 @8, minimum_amount_out u64 @16
pub const SWAP_DISCRIMINATOR: [u8; 8] = [0xf8, 0xc6, 0x9e, 0x91, 0xe1, 0x75, 0x87, 0xc8];
/// sha256("global:swap2")[..8]: amount_0 u64 @8, amount_1 u64 @16, swap_mode u8 @24
pub const SWAP2_DISCRIMINATOR: [u8; 8] = [0x41, 0x4b, 0x3f, 0x4c, 0xeb, 0x5b, 0x5b, 0x88];

/// Account indices of `swap` and `swap2` (SwapCtx; both instructions take the same 14 accounts, plus the instructions
/// sysvar as a remaining account when a rate limiter is in force). The vaults and mints are always in the POOL's
/// order (a, b) whatever the direction; the direction is the mint of `IX_INPUT_TOKEN`: token a -> A->B (a_to_b), else
/// B->A. Without reading that token account, compare it with the payer's ATA of `IX_MINT_A` / `IX_MINT_B`.
/// `IX_REFERRAL` equal to the program id means "no referral" (only splits the protocol fee; the quote is unaffected).
pub const IX_POOL_AUTHORITY: usize = 0;
pub const IX_POOL: usize = 1;
pub const IX_INPUT_TOKEN: usize = 2;
pub const IX_OUTPUT_TOKEN: usize = 3;
pub const IX_VAULT_A: usize = 4;
pub const IX_VAULT_B: usize = 5;
pub const IX_MINT_A: usize = 6;
pub const IX_MINT_B: usize = 7;
pub const IX_PAYER: usize = 8;
pub const IX_TOKEN_A_PROGRAM: usize = 9;
pub const IX_TOKEN_B_PROGRAM: usize = 10;
pub const IX_REFERRAL: usize = 11;
pub const IX_EVENT_AUTHORITY: usize = 12;
pub const IX_PROGRAM: usize = 13;
pub const IX_ACCOUNTS: usize = 14;

pub const FEE_DENOMINATOR: u64 = 1_000_000_000;
const MAX_BASIS_POINT: u64 = 10_000;
const ONE_Q64: u128 = 1 << 64;

/// state/fee.rs BaseFeeMode, byte 8 of the 32-byte BaseFeeInfo
pub const BASE_FEE_TIME_LINEAR: u8 = 0;
pub const BASE_FEE_TIME_EXPONENTIAL: u8 = 1;
pub const BASE_FEE_RATE_LIMITER: u8 = 2;
pub const BASE_FEE_MARKET_CAP_LINEAR: u8 = 3;
pub const BASE_FEE_MARKET_CAP_EXPONENTIAL: u8 = 4;
/// state/pool.rs CollectFeeMode
pub const COLLECT_BOTH: u8 = 0;
pub const COLLECT_ONLY_B: u8 = 1;
pub const COLLECT_COMPOUNDING: u8 = 2;

/// Pool byte offsets (struct order of state/pool.rs + state/fee.rs; same table as arbed's DAMMV2_OFF).
mod off {
    pub const BASE_FEE_INFO: usize = 8; // [u8; 32]
    pub const PROTOCOL_FEE_PERCENT: usize = 48;
    pub const REFERRAL_FEE_PERCENT: usize = 50;
    pub const COMPOUNDING_FEE_BPS: usize = 54;
    pub const DYN: usize = 56; // DynamicFeeStruct, 96 bytes
    pub const INIT_SQRT_PRICE: usize = 152;
    pub const TOKEN_A_MINT: usize = 168;
    pub const TOKEN_B_MINT: usize = 200;
    pub const TOKEN_A_VAULT: usize = 232;
    pub const TOKEN_B_VAULT: usize = 264;
    pub const WHITELISTED_VAULT: usize = 296;
    pub const LIQUIDITY: usize = 360;
    pub const SQRT_MIN_PRICE: usize = 424;
    pub const SQRT_MAX_PRICE: usize = 440;
    pub const SQRT_PRICE: usize = 456;
    pub const ACTIVATION_POINT: usize = 472;
    pub const ACTIVATION_TYPE: usize = 480;
    pub const POOL_STATUS: usize = 481;
    pub const TOKEN_A_FLAG: usize = 482;
    pub const TOKEN_B_FLAG: usize = 483;
    pub const COLLECT_FEE_MODE: usize = 484;
    pub const POOL_TYPE: usize = 485;
    pub const FEE_VERSION: usize = 486;
    pub const TOKEN_A_AMOUNT: usize = 680;
    pub const TOKEN_B_AMOUNT: usize = 688;
    pub const LAYOUT_VERSION: usize = 696;
}

/// The 32-byte BaseFeeInfo, every scheduler's fields (unused ones 0). All three PodAligned layouts share
/// cliff_fee_numerator u64 @0 and base_fee_mode u8 @8.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct BaseFee {
    pub mode: u8,
    pub cliff_fee_numerator: u64,
    /// time and market-cap schedulers
    pub number_of_period: u16,
    pub reduction_factor: u64,
    /// time scheduler only (slots or seconds per period)
    pub period_frequency: u64,
    /// market-cap scheduler only
    pub sqrt_price_step_bps: u32,
    pub scheduler_expiration_duration: u32,
    /// rate limiter only (deprecated mode)
    pub fee_increment_bps: u16,
    pub max_limiter_duration: u32,
    pub max_fee_bps: u32,
    pub reference_amount: u64,
}

/// DynamicFeeStruct (96 bytes @56). `initialized == 0` = dynamic fee off (the other fields are then ignored).
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct DynamicFee {
    pub initialized: u8,
    pub max_volatility_accumulator: u32,
    pub variable_fee_control: u32,
    pub bin_step: u16,
    pub filter_period: u16,
    pub decay_period: u16,
    pub reduction_factor: u16,
    pub last_update_timestamp: u64,
    pub bin_step_u128: u128,
    pub sqrt_price_reference: u128,
    pub volatility_accumulator: u128,
    pub volatility_reference: u128,
}

/// Everything a swap reads from (and writes to) the pool account. `quote_exact_in` returns the same struct as the
/// next swap would find it.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct DammPool {
    pub token_a_mint: Pk,
    pub token_b_mint: Pk,
    pub token_a_vault: Pk,
    pub token_b_vault: Pk,
    pub whitelisted_vault: Pk,
    pub liquidity: u128,
    pub sqrt_min_price: u128,
    pub sqrt_max_price: u128,
    /// Q64.64 sqrt(price of a in b)
    pub sqrt_price: u128,
    /// tracked reserves (layout_version 1); the curve of a compounding pool
    pub token_a_amount: u64,
    pub token_b_amount: u64,
    /// slot (activation_type 0) or unix timestamp (1)
    pub activation_point: u64,
    pub activation_type: u8,
    /// 0 enabled
    pub pool_status: u8,
    /// 0 SPL Token, 1 Token-2022
    pub token_a_flag: u8,
    pub token_b_flag: u8,
    pub collect_fee_mode: u8,
    pub pool_type: u8,
    /// 0: fee capped at 50%, 1: at 99%
    pub fee_version: u8,
    pub layout_version: u8,
    pub init_sqrt_price: u128,
    pub protocol_fee_percent: u8,
    pub referral_fee_percent: u8,
    pub compounding_fee_bps: u16,
    pub base_fee: BaseFee,
    pub dynamic_fee: DynamicFee,
    /// Token-2022 transfer fees are NOT applied by the quote. `decode` sets this true only when both mints are plain
    /// SPL (flags 0); for a Token-2022 side the quote refuses until the caller has checked that neither mint charges
    /// a transfer fee and sets it to true (arbed: `damm2TransferFeeKnownZero`).
    pub transfer_fee_known_zero: bool,
}

fn decode_base_fee(d: &[u8]) -> Option<BaseFee> {
    let b = d.get(off::BASE_FEE_INFO..off::BASE_FEE_INFO + 32)?;
    let mode = b[8];
    let mut f = BaseFee { mode, cliff_fee_numerator: u64_at(b, 0)?, ..Default::default() };
    match mode {
        BASE_FEE_RATE_LIMITER => {
            f.fee_increment_bps = u16_at(b, 14)?;
            f.max_limiter_duration = u32_at(b, 16)?;
            f.max_fee_bps = u32_at(b, 20)?;
            f.reference_amount = u64_at(b, 24)?;
        }
        BASE_FEE_MARKET_CAP_LINEAR | BASE_FEE_MARKET_CAP_EXPONENTIAL => {
            f.number_of_period = u16_at(b, 14)?;
            f.sqrt_price_step_bps = u32_at(b, 16)?;
            f.scheduler_expiration_duration = u32_at(b, 20)?;
            f.reduction_factor = u64_at(b, 24)?;
        }
        // time schedulers, and any mode this version does not know (the quote refuses those)
        _ => {
            f.number_of_period = u16_at(b, 14)?;
            f.period_frequency = u64_at(b, 16)?;
            f.reduction_factor = u64_at(b, 24)?;
        }
    }
    Some(f)
}

fn decode_dynamic_fee(d: &[u8]) -> Option<DynamicFee> {
    let o = off::DYN;
    Some(DynamicFee {
        initialized: *d.get(o)?,
        max_volatility_accumulator: u32_at(d, o + 8)?,
        variable_fee_control: u32_at(d, o + 12)?,
        bin_step: u16_at(d, o + 16)?,
        filter_period: u16_at(d, o + 18)?,
        decay_period: u16_at(d, o + 20)?,
        reduction_factor: u16_at(d, o + 22)?,
        last_update_timestamp: u64_at(d, o + 24)?,
        bin_step_u128: u128_at(d, o + 32)?,
        sqrt_price_reference: u128_at(d, o + 48)?,
        volatility_accumulator: u128_at(d, o + 64)?,
        volatility_reference: u128_at(d, o + 80)?,
    })
}

/// Decode a Pool account (exactly 1112 bytes with the Pool discriminator; anything else is refused).
pub fn decode(d: &[u8]) -> Option<DammPool> {
    if d.len() != POOL_SIZE || d[..8] != POOL_DISCRIMINATOR { return None; }
    let token_a_flag = d[off::TOKEN_A_FLAG];
    let token_b_flag = d[off::TOKEN_B_FLAG];
    Some(DammPool {
        token_a_mint: pk_at(d, off::TOKEN_A_MINT)?,
        token_b_mint: pk_at(d, off::TOKEN_B_MINT)?,
        token_a_vault: pk_at(d, off::TOKEN_A_VAULT)?,
        token_b_vault: pk_at(d, off::TOKEN_B_VAULT)?,
        whitelisted_vault: pk_at(d, off::WHITELISTED_VAULT)?,
        liquidity: u128_at(d, off::LIQUIDITY)?,
        sqrt_min_price: u128_at(d, off::SQRT_MIN_PRICE)?,
        sqrt_max_price: u128_at(d, off::SQRT_MAX_PRICE)?,
        sqrt_price: u128_at(d, off::SQRT_PRICE)?,
        token_a_amount: u64_at(d, off::TOKEN_A_AMOUNT)?,
        token_b_amount: u64_at(d, off::TOKEN_B_AMOUNT)?,
        activation_point: u64_at(d, off::ACTIVATION_POINT)?,
        activation_type: d[off::ACTIVATION_TYPE],
        pool_status: d[off::POOL_STATUS],
        token_a_flag,
        token_b_flag,
        collect_fee_mode: d[off::COLLECT_FEE_MODE],
        pool_type: d[off::POOL_TYPE],
        fee_version: d[off::FEE_VERSION],
        layout_version: d[off::LAYOUT_VERSION],
        init_sqrt_price: u128_at(d, off::INIT_SQRT_PRICE)?,
        protocol_fee_percent: d[off::PROTOCOL_FEE_PERCENT],
        referral_fee_percent: d[off::REFERRAL_FEE_PERCENT],
        compounding_fee_bps: u16_at(d, off::COMPOUNDING_FEE_BPS)?,
        base_fee: decode_base_fee(d)?,
        dynamic_fee: decode_dynamic_fee(d)?,
        transfer_fee_known_zero: token_a_flag == 0 && token_b_flag == 0,
    })
}

/* ------------------------------------------ fee model ------------------------------------------ */

/// The clock value the fee scheduler and the activation check read: the slot for activation_type 0, the unix
/// timestamp for 1 (ActivationHandler::get_current_point). None for an unknown activation type or a negative time.
pub fn current_point(p: &DammPool, slot: u64, now_unix: i64) -> Option<u64> {
    match p.activation_type {
        0 => Some(slot),
        1 => u64::try_from(now_unix).ok(),
        _ => None,
    }
}

/// constants::fee::get_max_fee_numerator
fn max_fee_numerator(fee_version: u8) -> Option<u64> {
    match fee_version { 0 => Some(500_000_000), 1 => Some(990_000_000), _ => None }
}

/// fee_math.rs `pow`: Q64.64 base^exp with 19 exponent bits and the inversion trick, same overflow points.
fn pow_q64(base: u128, exp: u32) -> Option<u128> {
    if exp == 0 { return Some(ONE_Q64); }
    if exp >= 0x80000 { return None; }
    let mut invert = false;
    let mut squared = base;
    let mut result = ONE_Q64;
    if squared >= result {
        squared = u128::MAX.checked_div(squared)?;
        invert = true;
    }
    for bit in 0..19 {
        if bit > 0 { squared = squared.checked_mul(squared)? >> 64; }
        if exp & (1 << bit) != 0 { result = result.checked_mul(squared)? >> 64; }
    }
    if result == 0 { return None; }
    if invert { result = u128::MAX.checked_div(result)?; }
    Some(result)
}

/// fee_math.rs get_fee_in_period: cliff * (1 - reduction/1e4)^period
fn fee_in_period(cliff: u64, reduction_factor: u64, period: u16) -> Option<u64> {
    if reduction_factor == 0 { return Some(cliff); }
    let bps = ((reduction_factor as u128) << 64) / MAX_BASIS_POINT as u128;
    let base = ONE_Q64.checked_sub(bps)?;
    let r = pow_q64(base, period as u32)?;
    u64::try_from(r.checked_mul(cliff as u128)? >> 64).ok()
}

/// get_base_fee_numerator_by_period, linear or exponential (period already capped by the caller)
fn fee_by_period(b: &BaseFee, period: u64, exponential: bool) -> Option<u64> {
    let period = period.min(b.number_of_period as u64);
    if exponential {
        fee_in_period(b.cliff_fee_numerator, b.reduction_factor, u16::try_from(period).ok()?)
    } else {
        b.cliff_fee_numerator.checked_sub(b.reduction_factor.checked_mul(period)?)
    }
}

/// params::fee_parameters::to_numerator(bps, FEE_DENOMINATOR)
fn to_numerator(bps: u64) -> Option<u64> {
    u64::try_from((bps as u128).checked_mul(FEE_DENOMINATOR as u128)? / MAX_BASIS_POINT as u128).ok()
}

/// fee_rate_limiter.rs is_rate_limiter_applied
fn rate_limiter_applied(b: &BaseFee, point: u64, activation_point: u64, a_to_b: bool) -> bool {
    let zero = b.reference_amount == 0 && b.max_limiter_duration == 0 && b.max_fee_bps == 0 && b.fee_increment_bps == 0;
    if zero || a_to_b || point < activation_point { return false; }
    point as u128 <= activation_point as u128 + b.max_limiter_duration as u128
}

/// fee_rate_limiter.rs get_fee_numerator_from_included_fee_amount. The program works in U256; with an input below
/// 2^64 every term stays below 2^110, so checked u128 is exact here.
fn rate_limiter_fee(b: &BaseFee, input: u64) -> Option<u64> {
    let x0 = b.reference_amount;
    if input <= x0 { return Some(b.cliff_fee_numerator); }
    if x0 == 0 { return None; }
    let max_fee = to_numerator(b.max_fee_bps as u64)?;
    let inc = to_numerator(b.fee_increment_bps as u64)?;
    let max_index = max_fee.checked_sub(b.cliff_fee_numerator)?.checked_div(inc)? as u128;
    let (c, i, x0w) = (b.cliff_fee_numerator as u128, inc as u128, x0 as u128);
    let (a, rem) = (((input - x0) / x0) as u128, ((input - x0) % x0) as u128);
    let series = |k: u128| -> Option<u128> {
        // c + c*k + i*k*(k+1)/2
        c.checked_add(c.checked_mul(k)?)?.checked_add(i.checked_mul(k)?.checked_mul(k + 1)? / 2)
    };
    let total = if a < max_index {
        x0w.checked_mul(series(a)?)?.checked_add(rem.checked_mul(c.checked_add(i.checked_mul(a + 1)?)?)?)?
    } else {
        let left = (a - max_index).checked_mul(x0w)?.checked_add(rem)?;
        x0w.checked_mul(series(max_index)?)?.checked_add(left.checked_mul(max_fee as u128)?)?
    };
    let den = FEE_DENOMINATOR as u128;
    let trading_fee = u64::try_from(total.checked_add(den - 1)? / den).ok()?;
    let num = (trading_fee as u128 * den).checked_add(input as u128 - 1)? / input as u128;
    u64::try_from(num).ok()
}

/// base_fee/*.rs get_base_fee_numerator_from_included_fee_amount, for every mode; None = the program errors or the
/// mode is unknown.
fn base_fee_numerator(p: &DammPool, a_to_b: bool, included: u64, point: u64) -> Option<u64> {
    let b = &p.base_fee;
    match b.mode {
        BASE_FEE_TIME_LINEAR | BASE_FEE_TIME_EXPONENTIAL => {
            if b.period_frequency == 0 { return Some(b.cliff_fee_numerator); }
            let period = if point < p.activation_point { b.number_of_period as u64 }
                else { (point - p.activation_point) / b.period_frequency };
            fee_by_period(b, period, b.mode == BASE_FEE_TIME_EXPONENTIAL)
        }
        BASE_FEE_MARKET_CAP_LINEAR | BASE_FEE_MARKET_CAP_EXPONENTIAL => {
            let expiration = p.activation_point.checked_add(b.scheduler_expiration_duration as u64)?;
            let period = if point > expiration || point < p.activation_point { b.number_of_period as u64 }
                else if p.sqrt_price <= p.init_sqrt_price { 0 }
                else {
                    // (current - init) * 10_000 / init / step: the program uses U256, but (current - init) * 10_000
                    // < 2^97 * 2^14, so u128 is exact
                    let passed = (p.sqrt_price - p.init_sqrt_price).checked_mul(MAX_BASIS_POINT as u128)?
                        .checked_div(p.init_sqrt_price)?.checked_div(b.sqrt_price_step_bps as u128)?;
                    passed.min(b.number_of_period as u128) as u64
                };
            fee_by_period(b, period, b.mode == BASE_FEE_MARKET_CAP_EXPONENTIAL)
        }
        BASE_FEE_RATE_LIMITER => {
            if rate_limiter_applied(b, point, p.activation_point, a_to_b) { rate_limiter_fee(b, included) }
            else { Some(b.cliff_fee_numerator) }
        }
        _ => None,
    }
}

/// DynamicFeeStruct::get_variable_fee over the STORED volatility_accumulator (u128, checked like the program)
fn variable_fee(d: &DynamicFee) -> Option<u128> {
    if d.initialized == 0 { return Some(0); }
    let sq = d.volatility_accumulator.checked_mul(d.bin_step as u128)?.checked_pow(2)?;
    Some(sq.checked_mul(d.variable_fee_control as u128)?.checked_add(99_999_999_999)? / 100_000_000_000)
}

/// PoolFeesStruct::get_total_trading_fee_from_included_fee_amount: min(base + variable, max(fee_version)), out of
/// 1e9, for an exact-in swap of `amount_in` at `point` (see `current_point`).
fn total_fee_numerator(p: &DammPool, a_to_b: bool, amount_in: u64, point: u64) -> Option<u64> {
    let max = max_fee_numerator(p.fee_version)?;
    let base = base_fee_numerator(p, a_to_b, amount_in, point)?;
    let total = u64::try_from(variable_fee(&p.dynamic_fee)?.checked_add(base as u128)?).ok()?;
    Some(total.min(max))
}

/// The trade fee numerator (out of 1e9) an exact-in swap of `amount_in` pays now. None = the swap is refused.
pub fn fee_numerator(p: &DammPool, a_to_b: bool, amount_in: u64, slot: u64, now_unix: i64) -> Option<u64> {
    total_fee_numerator(p, a_to_b, amount_in, current_point(p, slot, now_unix)?)
}

/// FeeMode::get_fee_mode: the fee comes off the input only for (OnlyB | Compounding) and B->A
pub fn fee_on_input(collect_fee_mode: u8, a_to_b: bool) -> bool {
    !a_to_b && (collect_fee_mode == COLLECT_ONLY_B || collect_fee_mode == COLLECT_COMPOUNDING)
}

fn ceil_fee(amount: u64, fee_num: u64) -> u64 {
    // safe_mul_div_cast_u64(amount, fee, 1e9, Up); <= amount since fee_num < 1e9
    ((amount as u128 * fee_num as u128 + FEE_DENOMINATOR as u128 - 1) / FEE_DENOMINATOR as u128) as u64
}

/// The compounding share of a trading fee (PoolFeesStruct::split_fees): protocol cut first (floor, percent), then
/// compounding_fee_bps of the rest (floor). The referral only splits the protocol cut, so it never matters here.
fn compounding_share(p: &DammPool, fee: u64) -> u64 {
    if p.compounding_fee_bps == 0 { return 0; }
    let protocol = (fee as u128 * p.protocol_fee_percent as u128 / 100) as u64;
    ((fee - protocol) as u128 * p.compounding_fee_bps as u128 / MAX_BASIS_POINT as u128) as u64
}

/* ------------------------------------------ curve math ------------------------------------------ */

/// get_delta_amount_a_unsigned_unchecked: L * (upper - lower) / (lower * upper), as U256
fn delta_a(lower: u128, upper: u128, liquidity: u128, up: bool) -> Option<U256> {
    let num = U256::mul128(liquidity, upper.checked_sub(lower)?);
    let den = U256::mul128(lower, upper);
    num.div_round(den, up)
}

/// get_delta_amount_b_unsigned_unchecked: L * (upper - lower) / 2^128, as U256
fn delta_b(lower: u128, upper: u128, liquidity: u128, up: bool) -> Option<U256> {
    let prod = U256::mul128(liquidity, upper.checked_sub(lower)?);
    let q = prod.shr(128);
    Some(if up && prod.low_bits_nonzero(128) { q.checked_add(U256::ONE)? } else { q })
}

fn to_u64(x: U256) -> Option<u64> { x.to_u128().and_then(|v| u64::try_from(v).ok()) }

/// concentrated_liquidity.rs get_reserves_amount (rounded up), used to migrate a layout-0 pool
fn concentrated_reserves(p: &DammPool) -> Option<(u64, u64)> {
    let a = to_u64(delta_a(p.sqrt_price, p.sqrt_max_price, p.liquidity, true)?)?;
    let b = to_u64(delta_b(p.sqrt_min_price, p.sqrt_price, p.liquidity, true)?)?;
    Some((a, b))
}

/// DynamicFeeStruct::get_delta_bin_id: ((upper << 64) / lower - 1.0) / bin_step_u128 * 2
fn delta_bin_id(bin_step_u128: u128, a: u128, b: u128) -> Option<u128> {
    let (upper, lower) = if a > b { (a, b) } else { (b, a) };
    if lower == 0 { return None; }
    let ratio = U256::from_u128(upper).shl(64)?.div_rem(U256::from_u128(lower))?.0.to_u128()?;
    ratio.checked_sub(ONE_Q64)?.checked_div(bin_step_u128)?.checked_mul(2)
}

/// DynamicFeeStruct::update_references (update_pre_swap)
fn update_references(d: &mut DynamicFee, sqrt_price: u128, now: u64) -> Option<()> {
    let elapsed = now.saturating_sub(d.last_update_timestamp);
    if elapsed >= d.filter_period as u64 {
        d.sqrt_price_reference = sqrt_price;
        d.volatility_reference = if elapsed < d.decay_period as u64 {
            d.volatility_accumulator.checked_mul(d.reduction_factor as u128)? / MAX_BASIS_POINT as u128
        } else { 0 };
    }
    Some(())
}

/// Pool::update_post_swap: the accumulator from the new price, and the timestamp when a "bin" was crossed
fn update_post_swap(d: &mut DynamicFee, old_sqrt_price: u128, new_sqrt_price: u128, now: u64) -> Option<()> {
    let delta = delta_bin_id(d.bin_step_u128, new_sqrt_price, d.sqrt_price_reference)?;
    let va = d.volatility_reference.checked_add(delta.checked_mul(MAX_BASIS_POINT as u128)?)?;
    d.volatility_accumulator = va.min(d.max_volatility_accumulator as u128);
    if delta_bin_id(d.bin_step_u128, old_sqrt_price, new_sqrt_price)? > 0 { d.last_update_timestamp = now; }
    Some(())
}

/* -------------------------------------------- swap --------------------------------------------- */

/// Why a swap has no quote.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Fail {
    /// the pool cannot be swapped (disabled, not active, unmodelled fee / transfer fee / layout, program error)
    Refused(&'static str),
    /// the amount is too small: the swap would pay out nothing
    ZeroOut,
    /// the amount is too large: price range violation, or an output / reserve the program cannot represent
    TooLarge(&'static str),
}

/// Everything before the fee: can_swap, update_layout_version_if_needed, update_pre_swap. Returns the pool as the
/// fee and curve then read it, the scheduler's current point and the Clock's unix time.
fn prepare(p: &DammPool, slot: u64, now_unix: i64) -> Result<(DammPool, u64, u64), Fail> {
    use Fail::*;
    if p.pool_status != 0 { return Err(Refused("pool-disabled")); }
    let point = current_point(p, slot, now_unix).ok_or(Refused("activation-type"))?;
    if point < p.activation_point { return Err(Refused("not-activated")); }
    if (p.token_a_flag != 0 || p.token_b_flag != 0) && !p.transfer_fee_known_zero { return Err(Refused("token2022-transfer-fee-unknown")); }
    if p.collect_fee_mode > COLLECT_COMPOUNDING { return Err(Refused("collect-fee-mode")); }
    // the Clock's unix_timestamp, read by the dynamic fee whatever the activation type
    let now = u64::try_from(now_unix).map_err(|_| Refused("negative-time"))?;
    let mut s = p.clone();
    match s.layout_version {
        1 => {}
        0 if s.collect_fee_mode != COLLECT_COMPOUNDING => {
            let (a, b) = concentrated_reserves(&s).ok_or(Refused("layout0-reserves"))?;
            s.token_a_amount = a;
            s.token_b_amount = b;
            s.layout_version = 1;
        }
        _ => return Err(Refused("layout-version")),
    }
    if s.dynamic_fee.initialized != 0 {
        update_references(&mut s.dynamic_fee, s.sqrt_price, now).ok_or(Refused("dynamic-fee-references"))?;
    }
    if s.collect_fee_mode != COLLECT_COMPOUNDING {
        if s.liquidity == 0 { return Err(Refused("no-liquidity")); }
        if s.sqrt_price == 0 || s.sqrt_min_price == 0 || s.sqrt_max_price <= s.sqrt_min_price { return Err(Refused("bad-range")); }
    } else if s.liquidity == 0 {
        return Err(Refused("no-liquidity")); // apply_swap_result's shl_div_256(claiming_fee, liquidity) would fail
    }
    Ok((s, point, now))
}

/// apply_swap_result + update_post_swap. `excluded_in`: the input the curve took (after an input fee);
/// `included_out`: what leaves the output reserve (the user's output plus an output fee); `fee`: the whole trading fee.
fn apply(mut s: DammPool, a_to_b: bool, excluded_in: u64, included_out: u64, fee: u64, curve_sqrt: u128, now: u64) -> Result<DammPool, Fail> {
    use Fail::*;
    let compounding_fee = compounding_share(&s, fee);
    let (r_in, r_out) = if a_to_b { (&mut s.token_a_amount, &mut s.token_b_amount) } else { (&mut s.token_b_amount, &mut s.token_a_amount) };
    *r_in = r_in.checked_add(excluded_in).ok_or(TooLarge("reserve-overflow"))?;
    *r_out = r_out.checked_sub(included_out).ok_or(TooLarge("reserve-underflow"))?;
    // compounding fees always accumulate in token b
    s.token_b_amount = s.token_b_amount.checked_add(compounding_fee).ok_or(TooLarge("reserve-overflow"))?;
    let old_sqrt = s.sqrt_price;
    s.sqrt_price = if s.collect_fee_mode == COLLECT_COMPOUNDING {
        // compounding_liquidity.rs get_sqrt_price_from_amounts: isqrt((b << 128) / a), from the NEW reserves
        if s.token_a_amount == 0 { return Err(TooLarge("reserve-empty")); }
        let r = U256::from_u128(s.token_b_amount as u128).shl(128).and_then(|x| x.div_rem(U256::from_u128(s.token_a_amount as u128)));
        r.ok_or(Refused("sqrt"))?.0.isqrt().to_u128().ok_or(Refused("sqrt"))?
    } else { curve_sqrt };
    if s.dynamic_fee.initialized != 0 {
        update_post_swap(&mut s.dynamic_fee, old_sqrt, s.sqrt_price, now).ok_or(Refused("dynamic-fee-post-swap"))?;
    }
    Ok(s)
}

/// One exact-in swap (`swap`, or `swap2` with swap_mode 0; also swap_mode 1 PartialFill whenever this succeeds, as
/// the partial fill only differs once the range end is hit), integer for integer with the program: the output the
/// user receives (before any Token-2022 transfer fee) and the pool exactly as the next swap would read it.
/// `a_to_b` = input token a (token_a_mint). `slot` and `now_unix` are the Clock the swap executes under.
pub fn swap_exact_in(p: &DammPool, a_to_b: bool, amount_in: u64, slot: u64, now_unix: i64) -> Result<(u64, DammPool), Fail> {
    use Fail::*;
    if amount_in == 0 { return Err(ZeroOut); }
    let (s, point, now) = prepare(p, slot, now_unix)?;
    let fee_num = total_fee_numerator(&s, a_to_b, amount_in, point).ok_or(Refused("fee-unmodelled"))?;
    if fee_num >= FEE_DENOMINATOR { return Err(Refused("fee-100pct")); }
    let on_input = fee_on_input(s.collect_fee_mode, a_to_b);
    let in_fee = if on_input { ceil_fee(amount_in, fee_num) } else { 0 };
    let actual_in = amount_in - in_fee;
    if actual_in == 0 { return Err(ZeroOut); }

    // the curve: gross output and the next sqrt price (compounding: recomputed from the reserves in `apply`)
    let (gross_out, curve_sqrt) = if s.collect_fee_mode == COLLECT_COMPOUNDING {
        // compounding_liquidity.rs calculate_*_from_amount_in: out = r_out * in / (r_in + in)
        let (r_in, r_out) = if a_to_b { (s.token_a_amount, s.token_b_amount) } else { (s.token_b_amount, s.token_a_amount) };
        if r_in == 0 || r_out == 0 { return Err(Refused("empty-reserves")); }
        let den = r_in.checked_add(actual_in).ok_or(TooLarge("reserve-overflow"))?;
        ((r_out as u128 * actual_in as u128 / den as u128) as u64, 0)
    } else {
        let (sp, l) = (s.sqrt_price, s.liquidity);
        if a_to_b {
            // get_next_sqrt_price_from_amount_in_a_rounding_up: ceil(L * P / (L + in * P))
            let den = U256::from_u128(l).checked_add(U256::mul128(actual_in as u128, sp)).ok_or(TooLarge("overflow"))?;
            let next = U256::mul128(l, sp).div_round(den, true).and_then(U256::to_u128).ok_or(TooLarge("overflow"))?;
            if next < s.sqrt_min_price { return Err(TooLarge("price-range")); }
            let out = to_u64(delta_b(next, sp, l, false).ok_or(TooLarge("overflow"))?).ok_or(TooLarge("output-overflow"))?;
            (out, next)
        } else {
            // get_next_sqrt_price_from_amount_in_b_rounding_down: P + (in << 128) / L
            let q = U256::from_u128(actual_in as u128).shl(128).and_then(|x| x.div_rem(U256::from_u128(l))).ok_or(TooLarge("overflow"))?.0;
            let next = U256::from_u128(sp).checked_add(q).and_then(U256::to_u128).ok_or(TooLarge("price-range"))?;
            if next > s.sqrt_max_price { return Err(TooLarge("price-range")); }
            let out = to_u64(delta_a(sp, next, l, false).ok_or(TooLarge("overflow"))?).ok_or(TooLarge("output-overflow"))?;
            (out, next)
        }
    };
    let out_fee = if on_input { 0 } else { ceil_fee(gross_out, fee_num) };
    let out = gross_out - out_fee;
    if out == 0 { return Err(ZeroOut); }
    let after = apply(s, a_to_b, actual_in, gross_out, in_fee + out_fee, curve_sqrt, now)?;
    Ok((out, after))
}

/// PoolFeesStruct::get_included_fee_amount: (ceil(excluded * 1e9 / (1e9 - fee)), the fee)
fn included_fee_amount(fee_num: u64, excluded: u64) -> Option<(u64, u64)> {
    let den = (FEE_DENOMINATOR - fee_num) as u128;
    let included = u64::try_from((excluded as u128 * FEE_DENOMINATOR as u128 + den - 1) / den).ok()?;
    Some((included, included - excluded))
}

/// One exact-OUTPUT swap (`swap2` with swap_mode 2: amount_0 = the output), integer for integer with the program's
/// get_swap_result_from_exact_output, which prices it from the OUTPUT (its own rounding, so the state after differs
/// by rounding units from an exact-in swap of the same input): the input it takes (including the trading fee, before
/// any Token-2022 transfer fee) and the pool after. The deprecated rate limiter, while in force, prices an exact-out
/// swap with a different formula: refused.
pub fn swap_exact_out(p: &DammPool, a_to_b: bool, amount_out: u64, slot: u64, now_unix: i64) -> Result<(u64, DammPool), Fail> {
    use Fail::*;
    if amount_out == 0 { return Err(ZeroOut); }
    let (s, point, now) = prepare(p, slot, now_unix)?;
    if s.base_fee.mode == BASE_FEE_RATE_LIMITER && rate_limiter_applied(&s.base_fee, point, s.activation_point, a_to_b) {
        return Err(Refused("rate-limiter-exact-out"));
    }
    // outside the rate limiter the base fee does not depend on the amount: the numerator from the excluded amount
    // (get_total_trading_fee_from_excluded_fee_amount) equals this one
    let fee_num = total_fee_numerator(&s, a_to_b, amount_out, point).ok_or(Refused("fee-unmodelled"))?;
    if fee_num >= FEE_DENOMINATOR { return Err(Refused("fee-100pct")); }
    let on_input = fee_on_input(s.collect_fee_mode, a_to_b);
    let (included_out, out_fee) = if on_input { (amount_out, 0) }
        else { included_fee_amount(fee_num, amount_out).ok_or(TooLarge("output-overflow"))? };

    // the curve, from the output: the input it needs and the next sqrt price
    let (input, curve_sqrt) = if s.collect_fee_mode == COLLECT_COMPOUNDING {
        // compounding_liquidity.rs calculate_*_from_amount_out: in = ceil(r_in * out / (r_out - out))
        let (r_in, r_out) = if a_to_b { (s.token_a_amount, s.token_b_amount) } else { (s.token_b_amount, s.token_a_amount) };
        let den = r_out.checked_sub(included_out).filter(|&d| d > 0).ok_or(TooLarge("reserve"))? as u128;
        let x = (r_in as u128 * included_out as u128 + den - 1) / den;
        (u64::try_from(x).map_err(|_| TooLarge("input-overflow"))?, 0)
    } else {
        let (sp, l) = (s.sqrt_price, s.liquidity);
        if a_to_b {
            // get_next_sqrt_price_from_amount_out_b_rounding_down: P - ceil((out << 128) / L)
            let q = U256::from_u128(included_out as u128).shl(128).and_then(|x| x.div_round(U256::from_u128(l), true)).ok_or(TooLarge("overflow"))?;
            let next = U256::from_u128(sp).checked_sub(q).and_then(U256::to_u128).ok_or(TooLarge("price-range"))?;
            if next < s.sqrt_min_price { return Err(TooLarge("price-range")); }
            let x = to_u64(delta_a(next, sp, l, true).ok_or(TooLarge("overflow"))?).ok_or(TooLarge("input-overflow"))?;
            (x, next)
        } else {
            // get_next_sqrt_price_from_amount_out_a_rounding_up: ceil(L * P / (L - out * P))
            let den = U256::from_u128(l).checked_sub(U256::mul128(included_out as u128, sp)).ok_or(TooLarge("price-range"))?;
            let next = U256::mul128(l, sp).div_round(den, true).and_then(U256::to_u128).ok_or(TooLarge("price-range"))?;
            if next > s.sqrt_max_price { return Err(TooLarge("price-range")); }
            let x = to_u64(delta_b(sp, next, l, true).ok_or(TooLarge("overflow"))?).ok_or(TooLarge("input-overflow"))?;
            (x, next)
        }
    };
    let (included_in, in_fee) = if on_input { included_fee_amount(fee_num, input).ok_or(TooLarge("input-overflow"))? } else { (input, 0) };
    let after = apply(s, a_to_b, input, included_out, in_fee + out_fee, curve_sqrt, now)?;
    Ok((included_in, after))
}

/// Exact-in quote: the output and the pool after the swap. None when the program would fail (or pay out nothing).
pub fn quote_exact_in(p: &DammPool, a_to_b: bool, amount_in: u64, slot: u64, now_unix: i64) -> Option<(u64, DammPool)> {
    swap_exact_in(p, a_to_b, amount_in, slot, now_unix).ok()
}

/// The smallest exact input whose quote pays at least `want_out` (a search over `swap_exact_in`, whose output is
/// monotone in the input). None when no input can (pool refused, or `want_out` beyond the range / reserves).
/// For a pending exact-out swap (swap2 mode 2) use `swap_exact_out`, the program's own path: it prices from the
/// OUTPUT, so the state after it differs from an exact-in swap of the same input by rounding units (the input itself
/// matched this search on every real exact-out swap in the tests, but the two paths round differently).
pub fn input_for_output(p: &DammPool, a_to_b: bool, want_out: u64, slot: u64, now_unix: i64) -> Option<u64> {
    if want_out == 0 { return None; }
    // Ok(true): pays >= want; Ok(false): too small; Err(TooLarge): past the range / reserves; other Err: refused
    let probe = |x: u64| -> Result<bool, Fail> {
        match swap_exact_in(p, a_to_b, x, slot, now_unix) {
            Ok((o, _)) => Ok(o >= want_out),
            Err(Fail::ZeroOut) => Ok(false),
            Err(e) => Err(e),
        }
    };
    let mut lo = 0u64; // known too small
    let mut x = want_out;
    let mut hi: Option<u64> = None; // known good
    let mut bad: Option<u64> = None; // known too large
    for _ in 0..70 {
        match probe(x) {
            Ok(true) => { hi = Some(x); break; }
            Ok(false) => {
                lo = x;
                if x == u64::MAX { return None; }
                x = x.checked_mul(2).unwrap_or(u64::MAX);
            }
            Err(Fail::TooLarge(_)) => { bad = Some(x); break; }
            Err(_) => return None,
        }
    }
    if hi.is_none() {
        // the doubling jumped past the range end: look for a good input between `lo` and `bad`
        let mut b = bad?;
        while b - lo > 1 {
            let mid = lo + (b - lo) / 2;
            match probe(mid) {
                Ok(true) => { hi = Some(mid); break; }
                Ok(false) => lo = mid,
                Err(Fail::TooLarge(_)) => b = mid,
                Err(_) => return None,
            }
        }
    }
    let mut h = hi?;
    while h - lo > 1 {
        let mid = lo + (h - lo) / 2;
        if probe(mid) == Ok(true) { h = mid; } else { lo = mid; }
    }
    Some(h)
}

/* ------------------------------------- instruction decoding ------------------------------------- */

/// swap2 `swap_mode` (instructions/swap/ix_swap.rs SwapMode)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SwapMode {
    /// amount_0 = exact input, amount_1 = minimum output (also `swap`)
    ExactIn,
    /// amount_0 = input, amount_1 = minimum output; stops at the price range end and keeps the rest
    PartialFill,
    /// amount_0 = exact OUTPUT, amount_1 = maximum input
    ExactOut,
}

/// A decoded `swap` / `swap2` (SwapParameters2). `swap` decodes as ExactIn.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SwapIx {
    pub mode: SwapMode,
    pub amount_0: u64,
    pub amount_1: u64,
}

/// Any DAMM v2 swap instruction's parameters; None for another instruction or a swap the program would reject
/// (short data, unknown swap_mode).
pub fn decode_swap(data: &[u8]) -> Option<SwapIx> {
    let disc = data.get(..8)?;
    if disc == SWAP_DISCRIMINATOR {
        return Some(SwapIx { mode: SwapMode::ExactIn, amount_0: u64_at(data, 8)?, amount_1: u64_at(data, 16)? });
    }
    if disc == SWAP2_DISCRIMINATOR {
        let mode = match *data.get(24)? { 0 => SwapMode::ExactIn, 1 => SwapMode::PartialFill, 2 => SwapMode::ExactOut, _ => return None };
        return Some(SwapIx { mode, amount_0: u64_at(data, 8)?, amount_1: u64_at(data, 16)? });
    }
    None
}

/// (amount_in, minimum_amount_out) of an EXACT-INPUT swap: `swap`, or `swap2` with swap_mode 0. Every other
/// instruction (including swap2 partial-fill and exact-out; see `decode_swap` for those) is None.
pub fn decode_swap_ix(data: &[u8]) -> Option<(u64, u64)> {
    match decode_swap(data)? {
        SwapIx { mode: SwapMode::ExactIn, amount_0, amount_1 } => Some((amount_0, amount_1)),
        _ => None,
    }
}

/* ------------------------------------------- U256 ------------------------------------------- */

/// Minimal unsigned 256-bit integer (four little-endian u64 limbs): exactly the operations the program does in
/// ruint U256, all checked.
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

    pub fn from_u128(x: u128) -> U256 { U256([x as u64, (x >> 64) as u64, 0, 0]) }
    pub fn to_u128(self) -> Option<u128> {
        if self.0[2] != 0 || self.0[3] != 0 { None } else { Some(self.0[0] as u128 | (self.0[1] as u128) << 64) }
    }
    pub fn is_zero(self) -> bool { self.0 == [0; 4] }
    pub fn bits(self) -> u32 {
        for i in (0..4).rev() { if self.0[i] != 0 { return 64 * i as u32 + 64 - self.0[i].leading_zeros(); } }
        0
    }

    /// full 256-bit product of two u128
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
        for i in 0..4 {
            let s = self.0[i] as u128 + o.0[i] as u128 + carry;
            r[i] = s as u64;
            carry = s >> 64;
        }
        if carry != 0 { None } else { Some(U256(r)) }
    }

    pub fn checked_sub(self, o: U256) -> Option<U256> {
        if self < o { return None; }
        let mut r = [0u64; 4];
        let mut borrow = 0u64;
        for i in 0..4 {
            let (d1, b1) = self.0[i].overflowing_sub(o.0[i]);
            let (d2, b2) = d1.overflowing_sub(borrow);
            r[i] = d2;
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

    /// self << n; None when a set bit would be shifted out (or n >= 256 with a nonzero value)
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

    /// (quotient, remainder); None for a zero divisor. Knuth algorithm D on 64-bit limbs (Hacker's Delight divmnu).
    pub fn div_rem(self, d: U256) -> Option<(U256, U256)> {
        if d.is_zero() { return None; }
        if self < d { return Some((U256::ZERO, self)); }
        if let (Some(a), Some(b)) = (self.to_u128(), d.to_u128()) {
            return Some((U256::from_u128(a / b), U256::from_u128(a % b)));
        }
        let n = ((d.bits() + 63) / 64) as usize; // divisor limbs
        let m = ((self.bits() + 63) / 64) as usize; // dividend limbs
        if n == 1 {
            let dv = d.0[0] as u128;
            let mut q = [0u64; 4];
            let mut r = 0u128;
            for i in (0..m).rev() {
                let cur = (r << 64) | self.0[i] as u128;
                q[i] = (cur / dv) as u64;
                r = cur % dv;
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
            // multiply and subtract
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
                // qhat was one too large: add back
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

    /// self / d rounded down or up (ruint div_ceil); None for a zero divisor
    pub fn div_round(self, d: U256, up: bool) -> Option<U256> {
        let (q, r) = self.div_rem(d)?;
        if up && !r.is_zero() { q.checked_add(U256::ONE) } else { Some(q) }
    }

    /// floor(sqrt(self)): Newton from above. Equals utils_math.rs sqrt_u256 (the integer square root is unique).
    pub fn isqrt(self) -> U256 {
        if self.is_zero() { return self; }
        // 2^ceil(bits/2) >= sqrt(self), and <= 2^128, so x + self/x <= 2^129 never overflows
        let mut x = U256::ONE.shl((self.bits() + 1) / 2).unwrap();
        loop {
            let y = x.checked_add(self.div_rem(x).unwrap().0).unwrap().shr(1);
            if y >= x { return x; }
            x = y;
        }
    }
}


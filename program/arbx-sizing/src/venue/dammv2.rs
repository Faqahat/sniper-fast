//! Meteora DAMM v2 (cpamdpZC…) exact-in swap, ported from `src/venues/dammv2.rs` (damm-v2 a85c926; proven on chain
//! by testdata/dammv2-vectors.json) with the `String`/`Vec`/std parts removed and every panic path checked
//! (DESIGN.md §2.5). Two entry points share the fee and curve code:
//! * [`swap_exact_in`]: the full port, returning the pool exactly as the next swap would read it (tests, engine);
//! * [`DammLeg::quote`]: the on-chain path. It skips writing the post-swap state but keeps every check that can
//!   make the program fail there (reserve overflow/underflow, the dynamic-fee update), so `Ok` ⇔ the swap succeeds.
use crate::error::{Abort, DammWhy, Quote, QuoteErr};
use crate::fx::Fx;
use crate::math::{key_at, u128_at, u16_at, u32_at, u64_at, u8_at};
use crate::u256::U256;
use crate::Clock;

/// Pool::INIT_SPACE 1104 + the 8-byte discriminator
pub const POOL_SIZE: usize = 1112;
pub const FEE_DENOMINATOR: u64 = 1_000_000_000;
const MAX_BASIS_POINT: u64 = 10_000;
const ONE_Q64: u128 = 1 << 64;

pub const BASE_FEE_TIME_LINEAR: u8 = 0;
pub const BASE_FEE_TIME_EXPONENTIAL: u8 = 1;
pub const BASE_FEE_RATE_LIMITER: u8 = 2;
pub const BASE_FEE_MARKET_CAP_LINEAR: u8 = 3;
pub const BASE_FEE_MARKET_CAP_EXPONENTIAL: u8 = 4;
pub const COLLECT_BOTH: u8 = 0;
pub const COLLECT_ONLY_B: u8 = 1;
pub const COLLECT_COMPOUNDING: u8 = 2;

pub mod off {
    pub const BASE_FEE_INFO: usize = 8;
    pub const PROTOCOL_FEE_PERCENT: usize = 48;
    pub const REFERRAL_FEE_PERCENT: usize = 50;
    pub const COMPOUNDING_FEE_BPS: usize = 54;
    pub const DYN: usize = 56;
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

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct BaseFee {
    pub mode: u8,
    pub cliff_fee_numerator: u64,
    pub number_of_period: u16,
    pub reduction_factor: u64,
    pub period_frequency: u64,
    pub sqrt_price_step_bps: u32,
    pub scheduler_expiration_duration: u32,
    pub fee_increment_bps: u16,
    pub max_limiter_duration: u32,
    pub max_fee_bps: u32,
    pub reference_amount: u64,
}

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

/// Everything a swap reads from (and writes to) the pool account, keys excluded ([`DammKeys`]).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DammPool {
    pub liquidity: u128,
    pub sqrt_min_price: u128,
    pub sqrt_max_price: u128,
    pub sqrt_price: u128,
    pub token_a_amount: u64,
    pub token_b_amount: u64,
    pub activation_point: u64,
    pub activation_type: u8,
    pub pool_status: u8,
    pub token_a_flag: u8,
    pub token_b_flag: u8,
    pub collect_fee_mode: u8,
    pub pool_type: u8,
    pub fee_version: u8,
    pub layout_version: u8,
    pub init_sqrt_price: u128,
    pub protocol_fee_percent: u8,
    pub referral_fee_percent: u8,
    pub compounding_fee_bps: u16,
    pub base_fee: BaseFee,
    pub dynamic_fee: DynamicFee,
    /// set when neither mint charges a Token-2022 transfer fee (decode: both flags 0; else the caller's scan)
    pub transfer_fee_known_zero: bool,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DammKeys<'a> {
    pub token_a_mint: &'a [u8; 32],
    pub token_b_mint: &'a [u8; 32],
    pub token_a_vault: &'a [u8; 32],
    pub token_b_vault: &'a [u8; 32],
    pub whitelisted_vault: &'a [u8; 32],
}

pub fn keys(d: &[u8]) -> Option<DammKeys<'_>> {
    Some(DammKeys {
        token_a_mint: key_at(d, off::TOKEN_A_MINT)?, token_b_mint: key_at(d, off::TOKEN_B_MINT)?,
        token_a_vault: key_at(d, off::TOKEN_A_VAULT)?, token_b_vault: key_at(d, off::TOKEN_B_VAULT)?,
        whitelisted_vault: key_at(d, off::WHITELISTED_VAULT)?,
    })
}

fn decode_base_fee(d: &[u8]) -> Option<BaseFee> {
    let b = d.get(off::BASE_FEE_INFO..off::BASE_FEE_INFO + 32)?;
    let mode = u8_at(b, 8)?;
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
        initialized: u8_at(d, o)?,
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

/// Decode a Pool account (exactly 1112 bytes with the Pool discriminator; anything else is None)
pub fn decode(d: &[u8]) -> Option<DammPool> {
    if d.len() != POOL_SIZE || d.get(..8)? != &crate::layout::DISC_POOL[..] { return None; }
    let a_flag = u8_at(d, off::TOKEN_A_FLAG)?;
    let b_flag = u8_at(d, off::TOKEN_B_FLAG)?;
    Some(DammPool {
        liquidity: u128_at(d, off::LIQUIDITY)?,
        sqrt_min_price: u128_at(d, off::SQRT_MIN_PRICE)?,
        sqrt_max_price: u128_at(d, off::SQRT_MAX_PRICE)?,
        sqrt_price: u128_at(d, off::SQRT_PRICE)?,
        token_a_amount: u64_at(d, off::TOKEN_A_AMOUNT)?,
        token_b_amount: u64_at(d, off::TOKEN_B_AMOUNT)?,
        activation_point: u64_at(d, off::ACTIVATION_POINT)?,
        activation_type: u8_at(d, off::ACTIVATION_TYPE)?,
        pool_status: u8_at(d, off::POOL_STATUS)?,
        token_a_flag: a_flag,
        token_b_flag: b_flag,
        collect_fee_mode: u8_at(d, off::COLLECT_FEE_MODE)?,
        pool_type: u8_at(d, off::POOL_TYPE)?,
        fee_version: u8_at(d, off::FEE_VERSION)?,
        layout_version: u8_at(d, off::LAYOUT_VERSION)?,
        init_sqrt_price: u128_at(d, off::INIT_SQRT_PRICE)?,
        protocol_fee_percent: u8_at(d, off::PROTOCOL_FEE_PERCENT)?,
        referral_fee_percent: u8_at(d, off::REFERRAL_FEE_PERCENT)?,
        compounding_fee_bps: u16_at(d, off::COMPOUNDING_FEE_BPS)?,
        base_fee: decode_base_fee(d)?,
        dynamic_fee: decode_dynamic_fee(d)?,
        transfer_fee_known_zero: a_flag == 0 && b_flag == 0,
    })
}

/* ------------------------------------------ fee model ------------------------------------------ */

/// the slot (activation_type 0) or the unix timestamp (1)
pub fn current_point(p: &DammPool, slot: u64, now_unix: i64) -> Option<u64> {
    match p.activation_type { 0 => Some(slot), 1 => u64::try_from(now_unix).ok(), _ => None }
}

fn max_fee_numerator(fee_version: u8) -> Option<u64> {
    match fee_version { 0 => Some(500_000_000), 1 => Some(990_000_000), _ => None }
}

/// fee_math.rs `pow`: Q64.64 base^exp, 19 exponent bits, the inversion trick, same overflow points
pub fn pow_q64(base: u128, exp: u32) -> Option<u128> {
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

/// cliff · (1 − reduction/1e4)^period
pub fn fee_in_period(cliff: u64, reduction_factor: u64, period: u16) -> Option<u64> {
    if reduction_factor == 0 { return Some(cliff); }
    let bps = ((reduction_factor as u128) << 64) / MAX_BASIS_POINT as u128;
    let base = ONE_Q64.checked_sub(bps)?;
    let r = pow_q64(base, period as u32)?;
    u64::try_from(r.checked_mul(cliff as u128)? >> 64).ok()
}

fn fee_by_period(b: &BaseFee, period: u64, exponential: bool) -> Option<u64> {
    let period = period.min(b.number_of_period as u64);
    if exponential {
        fee_in_period(b.cliff_fee_numerator, b.reduction_factor, u16::try_from(period).ok()?)
    } else {
        b.cliff_fee_numerator.checked_sub(b.reduction_factor.checked_mul(period)?)
    }
}

fn to_numerator(bps: u64) -> Option<u64> {
    u64::try_from((bps as u128).checked_mul(FEE_DENOMINATOR as u128)? / MAX_BASIS_POINT as u128).ok()
}

pub fn rate_limiter_applied(b: &BaseFee, point: u64, activation_point: u64, a_to_b: bool) -> bool {
    let zero = b.reference_amount == 0 && b.max_limiter_duration == 0 && b.max_fee_bps == 0 && b.fee_increment_bps == 0;
    if zero || a_to_b || point < activation_point { return false; }
    point as u128 <= activation_point as u128 + b.max_limiter_duration as u128
}

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
        c.checked_add(c.checked_mul(k)?)?.checked_add(i.checked_mul(k)?.checked_mul(k.checked_add(1)?)? / 2)
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

fn base_fee_numerator(p: &DammPool, a_to_b: bool, included: u64, point: u64) -> Option<u64> {
    let b = &p.base_fee;
    match b.mode {
        BASE_FEE_TIME_LINEAR | BASE_FEE_TIME_EXPONENTIAL => {
            if b.period_frequency == 0 { return Some(b.cliff_fee_numerator); }
            let period = if point < p.activation_point { b.number_of_period as u64 } else { (point - p.activation_point) / b.period_frequency };
            fee_by_period(b, period, b.mode == BASE_FEE_TIME_EXPONENTIAL)
        }
        BASE_FEE_MARKET_CAP_LINEAR | BASE_FEE_MARKET_CAP_EXPONENTIAL => {
            let expiration = p.activation_point.checked_add(b.scheduler_expiration_duration as u64)?;
            let period = if point > expiration || point < p.activation_point { b.number_of_period as u64 }
                else if p.sqrt_price <= p.init_sqrt_price { 0 }
                else {
                    let passed = (p.sqrt_price - p.init_sqrt_price).checked_mul(MAX_BASIS_POINT as u128)?
                        .checked_div(p.init_sqrt_price)?.checked_div(b.sqrt_price_step_bps as u128)?;
                    passed.min(b.number_of_period as u128) as u64
                };
            fee_by_period(b, period, b.mode == BASE_FEE_MARKET_CAP_EXPONENTIAL)
        }
        BASE_FEE_RATE_LIMITER => {
            if rate_limiter_applied(b, point, p.activation_point, a_to_b) { rate_limiter_fee(b, included) } else { Some(b.cliff_fee_numerator) }
        }
        _ => None,
    }
}

fn variable_fee(d: &DynamicFee) -> Option<u128> {
    if d.initialized == 0 { return Some(0); }
    let sq = d.volatility_accumulator.checked_mul(d.bin_step as u128)?.checked_pow(2)?;
    Some(sq.checked_mul(d.variable_fee_control as u128)?.checked_add(99_999_999_999)? / 100_000_000_000)
}

/// min(base + variable, max(fee_version)), out of 1e9
pub fn total_fee_numerator(p: &DammPool, a_to_b: bool, amount_in: u64, point: u64) -> Option<u64> {
    let max = max_fee_numerator(p.fee_version)?;
    let base = base_fee_numerator(p, a_to_b, amount_in, point)?;
    let total = u64::try_from(variable_fee(&p.dynamic_fee)?.checked_add(base as u128)?).ok()?;
    Some(total.min(max))
}

pub fn fee_numerator(p: &DammPool, a_to_b: bool, amount_in: u64, slot: u64, now_unix: i64) -> Option<u64> {
    total_fee_numerator(p, a_to_b, amount_in, current_point(p, slot, now_unix)?)
}

/// the fee comes off the input only for (OnlyB | Compounding) and B→A
pub fn fee_on_input(collect_fee_mode: u8, a_to_b: bool) -> bool {
    !a_to_b && (collect_fee_mode == COLLECT_ONLY_B || collect_fee_mode == COLLECT_COMPOUNDING)
}

fn ceil_fee(amount: u64, fee_num: u64) -> u64 {
    // ⌈amount·fee/1e9⌉ ≤ amount (fee < 1e9); the small-divisor path of math::ceil_div
    crate::math::ceil_div(amount as u128 * fee_num as u128, FEE_DENOMINATOR as u128).unwrap_or(0) as u64
}

/// the compounding share of a trading fee: protocol cut first (floor, percent), then compounding_fee_bps of the
/// rest (floor); None where the program's checked arithmetic fails
fn compounding_share(p: &DammPool, fee: u64) -> Option<u64> {
    if p.compounding_fee_bps == 0 { return Some(0); }
    let protocol = crate::math::div(fee as u128 * p.protocol_fee_percent as u128, 100)? as u64;
    u64::try_from(crate::math::div(fee.checked_sub(protocol)? as u128 * p.compounding_fee_bps as u128, MAX_BASIS_POINT as u128)?).ok()
}

/* ------------------------------------------ curve math ------------------------------------------ */

fn delta_a(lower: u128, upper: u128, liquidity: u128, up: bool) -> Option<U256> {
    let num = U256::mul128(liquidity, upper.checked_sub(lower)?);
    let den = U256::mul128(lower, upper);
    num.div_round(den, up)
}

fn delta_b(lower: u128, upper: u128, liquidity: u128, up: bool) -> Option<U256> {
    let prod = U256::mul128(liquidity, upper.checked_sub(lower)?);
    let q = prod.shr(128);
    if up && prod.low_bits_nonzero(128) { q.checked_add(U256::ONE) } else { Some(q) }
}

fn to_u64(x: U256) -> Option<u64> { x.to_u128().and_then(|v| u64::try_from(v).ok()) }

fn concentrated_reserves(p: &DammPool) -> Option<(u64, u64)> {
    let a = to_u64(delta_a(p.sqrt_price, p.sqrt_max_price, p.liquidity, true)?)?;
    let b = to_u64(delta_b(p.sqrt_min_price, p.sqrt_price, p.liquidity, true)?)?;
    Some((a, b))
}

fn delta_bin_id(bin_step_u128: u128, a: u128, b: u128) -> Option<u128> {
    let (upper, lower) = if a > b { (a, b) } else { (b, a) };
    if lower == 0 { return None; }
    let ratio = U256::from_u128(upper).shl(64)?.div_rem(U256::from_u128(lower))?.0.to_u128()?;
    ratio.checked_sub(ONE_Q64)?.checked_div(bin_step_u128)?.checked_mul(2)
}

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

fn update_post_swap(d: &mut DynamicFee, old_sqrt_price: u128, new_sqrt_price: u128, now: u64) -> Option<()> {
    let delta = delta_bin_id(d.bin_step_u128, new_sqrt_price, d.sqrt_price_reference)?;
    let va = d.volatility_reference.checked_add(delta.checked_mul(MAX_BASIS_POINT as u128)?)?;
    d.volatility_accumulator = va.min(d.max_volatility_accumulator as u128);
    if delta_bin_id(d.bin_step_u128, old_sqrt_price, new_sqrt_price)? > 0 { d.last_update_timestamp = now; }
    Some(())
}

/// A cheap sufficient test that `update_post_swap` cannot fail for this move: both price pairs within a factor 2^47
/// of each other. Then (upper << 64)/lower < 2^111, delta_bin_id < 2^112, delta·1e4 < 2^126, and with
/// volatility_reference < 2^126 nothing overflows.
fn post_swap_cheap(d: &DynamicFee, old: u128, new: u128) -> bool {
    let close = |a: u128, b: u128| {
        let (hi, lo) = if a > b { (a, b) } else { (b, a) };
        lo != 0 && (lo >> 81 != 0 || hi < lo << 47)
    };
    d.bin_step_u128 != 0 && d.volatility_reference < (1u128 << 126) && close(new, d.sqrt_price_reference) && close(old, new)
}

/// Does `update_post_swap` succeed for this move? The cheap test first, the program's own arithmetic otherwise.
fn post_swap_ok(d: &DynamicFee, old: u128, new: u128) -> bool {
    if d.initialized == 0 || post_swap_cheap(d, old, new) { return true; }
    let mut copy = *d;
    update_post_swap(&mut copy, old, new, 0).is_some()
}

/* -------------------------------------------- swap --------------------------------------------- */

/// Why a swap has no quote
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Fail {
    /// the pool cannot be swapped or a state this port does not model (maps to an Abort)
    Refused(Abort),
    /// the swap would pay out nothing
    ZeroOut,
    /// price range violation, or an output / reserve the program cannot represent
    TooLarge,
}

impl From<Fail> for QuoteErr {
    fn from(f: Fail) -> QuoteErr {
        match f { Fail::Refused(a) => QuoteErr::Abort(a), Fail::ZeroOut => QuoteErr::ZeroOut, Fail::TooLarge => QuoteErr::TooLarge }
    }
}

const fn damm(w: DammWhy) -> Fail { Fail::Refused(Abort::Damm(w)) }

/// can_swap, update_layout_version_if_needed, update_pre_swap: the pool as the fee and curve read it, the scheduler
/// point and the Clock's unix time
pub fn prepare(p: &DammPool, slot: u64, now_unix: i64) -> Result<(DammPool, u64, u64), Fail> {
    if p.pool_status != 0 { return Err(damm(DammWhy::Status)); }
    let point = current_point(p, slot, now_unix).ok_or(damm(DammWhy::Mode))?;
    if point < p.activation_point { return Err(damm(DammWhy::NotActive)); }
    if (p.token_a_flag != 0 || p.token_b_flag != 0) && !p.transfer_fee_known_zero { return Err(Fail::Refused(Abort::TransferFee)); }
    if p.collect_fee_mode > COLLECT_COMPOUNDING { return Err(damm(DammWhy::Mode)); }
    let now = u64::try_from(now_unix).map_err(|_| damm(DammWhy::Time))?;
    let mut s = *p;
    match s.layout_version {
        1 => {}
        0 if s.collect_fee_mode != COLLECT_COMPOUNDING => {
            let (a, b) = concentrated_reserves(&s).ok_or(Fail::Refused(Abort::Math))?;
            s.token_a_amount = a;
            s.token_b_amount = b;
            s.layout_version = 1;
        }
        _ => return Err(damm(DammWhy::Mode)),
    }
    if s.dynamic_fee.initialized != 0 {
        update_references(&mut s.dynamic_fee, s.sqrt_price, now).ok_or(Fail::Refused(Abort::Math))?;
    }
    if s.collect_fee_mode != COLLECT_COMPOUNDING {
        if s.liquidity == 0 { return Err(damm(DammWhy::Liquidity)); }
        if s.sqrt_price == 0 || s.sqrt_min_price == 0 || s.sqrt_max_price <= s.sqrt_min_price { return Err(damm(DammWhy::Range)); }
    } else if s.liquidity == 0 {
        return Err(damm(DammWhy::Liquidity));
    }
    Ok((s, point, now))
}

/// The fee and the curve of one exact-in swap on a prepared pool
#[derive(Clone, Copy, Debug)]
struct Curve { out: u64, actual_in: u64, gross_out: u64, fee: u64, sqrt: u128 }

fn curve(s: &DammPool, a_to_b: bool, amount_in: u64, fee_num: u64) -> Result<Curve, Fail> {
    if fee_num >= FEE_DENOMINATOR { return Err(damm(DammWhy::Fee100)); }
    let on_input = fee_on_input(s.collect_fee_mode, a_to_b);
    let in_fee = if on_input { ceil_fee(amount_in, fee_num) } else { 0 };
    let actual_in = amount_in - in_fee;
    if actual_in == 0 { return Err(Fail::ZeroOut); }
    let (gross_out, sqrt) = if s.collect_fee_mode == COLLECT_COMPOUNDING {
        let (r_in, r_out) = if a_to_b { (s.token_a_amount, s.token_b_amount) } else { (s.token_b_amount, s.token_a_amount) };
        if r_in == 0 || r_out == 0 { return Err(damm(DammWhy::Liquidity)); }
        let den = r_in.checked_add(actual_in).ok_or(Fail::TooLarge)?;
        (crate::math::div(r_out as u128 * actual_in as u128, den as u128).ok_or(Fail::TooLarge)? as u64, 0)
    } else {
        let (sp, l) = (s.sqrt_price, s.liquidity);
        if a_to_b {
            let den = U256::from_u128(l).checked_add(U256::mul128(actual_in as u128, sp)).ok_or(Fail::TooLarge)?;
            let next = U256::mul128(l, sp).div_round(den, true).and_then(U256::to_u128).ok_or(Fail::TooLarge)?;
            if next < s.sqrt_min_price { return Err(Fail::TooLarge); }
            (to_u64(delta_b(next, sp, l, false).ok_or(Fail::TooLarge)?).ok_or(Fail::TooLarge)?, next)
        } else {
            let q = U256::from_u128(actual_in as u128).shl(128).and_then(|x| x.div_rem(U256::from_u128(l))).ok_or(Fail::TooLarge)?.0;
            let next = U256::from_u128(sp).checked_add(q).and_then(U256::to_u128).ok_or(Fail::TooLarge)?;
            if next > s.sqrt_max_price { return Err(Fail::TooLarge); }
            (to_u64(delta_a(sp, next, l, false).ok_or(Fail::TooLarge)?).ok_or(Fail::TooLarge)?, next)
        }
    };
    let out_fee = if on_input { 0 } else { ceil_fee(gross_out, fee_num) };
    let out = gross_out - out_fee;
    if out == 0 { return Err(Fail::ZeroOut); }
    Ok(Curve { out, actual_in, gross_out, fee: in_fee + out_fee, sqrt })
}

/// The reserves after the swap (apply_swap_result's checked updates): (a, b)
fn new_reserves(s: &DammPool, a_to_b: bool, c: &Curve) -> Result<(u64, u64), Fail> {
    let compounding_fee = compounding_share(s, c.fee).ok_or(Fail::Refused(Abort::Math))?;
    let (r_in, r_out) = if a_to_b { (s.token_a_amount, s.token_b_amount) } else { (s.token_b_amount, s.token_a_amount) };
    let new_in = r_in.checked_add(c.actual_in).ok_or(Fail::TooLarge)?;
    let new_out = r_out.checked_sub(c.gross_out).ok_or(Fail::TooLarge)?;
    let (a, b) = if a_to_b { (new_in, new_out) } else { (new_out, new_in) };
    Ok((a, b.checked_add(compounding_fee).ok_or(Fail::TooLarge)?))
}

fn compounding_sqrt(a: u64, b: u64) -> Result<u128, Fail> {
    if a == 0 { return Err(Fail::TooLarge); }
    let r = U256::from_u128(b as u128).shl(128).and_then(|x| x.div_rem(U256::from_u128(a as u128)));
    r.and_then(|(q, _)| q.isqrt()).and_then(U256::to_u128).ok_or(Fail::Refused(Abort::Math))
}

/// One exact-in swap, integer for integer with the program: the output and the pool as the next swap reads it.
pub fn swap_exact_in(p: &DammPool, a_to_b: bool, amount_in: u64, slot: u64, now_unix: i64) -> Result<(u64, DammPool), Fail> {
    if amount_in == 0 { return Err(Fail::ZeroOut); }
    let (s, point, now) = prepare(p, slot, now_unix)?;
    let fee_num = total_fee_numerator(&s, a_to_b, amount_in, point).ok_or(damm(DammWhy::Mode))?;
    let c = curve(&s, a_to_b, amount_in, fee_num)?;
    let (a, b) = new_reserves(&s, a_to_b, &c)?;
    let mut after = s;
    after.token_a_amount = a;
    after.token_b_amount = b;
    let old = s.sqrt_price;
    after.sqrt_price = if s.collect_fee_mode == COLLECT_COMPOUNDING { compounding_sqrt(a, b)? } else { c.sqrt };
    if after.dynamic_fee.initialized != 0 {
        update_post_swap(&mut after.dynamic_fee, old, after.sqrt_price, now).ok_or(Fail::Refused(Abort::Math))?;
    }
    Ok((c.out, after))
}

/* ------------------------------------------ the leg ------------------------------------------ */

/// A parsed DAMM v2 leg: the pool prepared under the Clock, and the fee numerator for this direction (None while
/// the rate limiter is in force: the fee then depends on the amount; [`parse`] refuses that state, only
/// [`parse_with_limiter`] builds such a leg, for off-chain use).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DammLeg {
    pub s: DammPool,
    pub a_to_b: bool,
    pub point: u64,
    pub fee_fixed: Option<u64>,
}

/// `transfer_fee_known_zero`: the caller scanned both mints (Token-2022) and found no transfer fee.
///
/// A rate limiter in force for this direction is `Abort::Damm(RateLimiter)`: the program then runs its single-swap
/// validation, which needs the instructions sysvar as the first remaining account, and the engine's 14-account leg
/// does not pass it, so the venue fails (6049 FailToValidateSingleSwapInstruction) at every size (REVIEW.md F5).
pub fn parse(pool: &[u8], a_to_b: bool, transfer_fee_known_zero: bool, clock: &Clock) -> Result<DammLeg, Abort> {
    let leg = parse_with_limiter(pool, a_to_b, transfer_fee_known_zero, clock)?;
    if leg.fee_fixed.is_none() { return Err(Abort::Damm(DammWhy::RateLimiter)); }
    Ok(leg)
}

/// [`parse`] without the rate-limiter refusal: the leg prices the limiter's amount-dependent fee exactly, for a
/// caller that passes the instructions sysvar (off-chain quoting; not the engine's leg layout).
pub fn parse_with_limiter(pool: &[u8], a_to_b: bool, transfer_fee_known_zero: bool, clock: &Clock) -> Result<DammLeg, Abort> {
    let mut p = decode(pool).ok_or(Abort::Layout)?;
    p.transfer_fee_known_zero = transfer_fee_known_zero;
    let (s, point, _now) = prepare(&p, clock.slot, clock.unix_timestamp).map_err(|f| match f { Fail::Refused(a) => a, _ => Abort::Math })?;
    let rl = s.base_fee.mode == BASE_FEE_RATE_LIMITER && rate_limiter_applied(&s.base_fee, point, s.activation_point, a_to_b);
    let fee_fixed = if rl { None } else {
        let f = total_fee_numerator(&s, a_to_b, 1, point).ok_or(Abort::Damm(DammWhy::Mode))?;
        if f >= FEE_DENOMINATOR { return Err(Abort::Damm(DammWhy::Fee100)); }
        Some(f)
    };
    Ok(DammLeg { s, a_to_b, point, fee_fixed })
}

impl DammLeg {
    pub fn quote(&self, x: u64) -> Result<Quote, QuoteErr> {
        if x == 0 { return Err(QuoteErr::ZeroOut); }
        let fee_num = match self.fee_fixed {
            Some(f) => f,
            None => total_fee_numerator(&self.s, self.a_to_b, x, self.point).ok_or(QuoteErr::Abort(Abort::Damm(DammWhy::RateLimiter)))?,
        };
        let c = curve(&self.s, self.a_to_b, x, fee_num)?;
        let (a, b) = new_reserves(&self.s, self.a_to_b, &c)?;
        if self.s.dynamic_fee.initialized != 0 {
            let new = if self.s.collect_fee_mode == COLLECT_COMPOUNDING {
                if a == 0 { return Err(QuoteErr::TooLarge); }
                // the new price from the reserves, bracketed with Fx (its bit length is within one of the true
                // root's); computed exactly only when the bracket does not pass the cheap test
                let approx = Fx::from_u64(b).shl(128).div(Fx::from_u64(a)).sqrt().floor_u128();
                let d = &self.s.dynamic_fee;
                if post_swap_cheap(d, self.s.sqrt_price, approx >> 1) && post_swap_cheap(d, self.s.sqrt_price, approx.saturating_mul(2)) {
                    approx
                } else { compounding_sqrt(a, b)? }
            } else { c.sqrt };
            if !post_swap_ok(&self.s.dynamic_fee, self.s.sqrt_price, new) { return Err(QuoteErr::Abort(Abort::Math)); }
        }
        Ok(Quote { out: c.out, spent: x })
    }

    /// Möbius model on virtual reserves (concentrated: R_a = L/P, R_b = L·P/2^128; compounding: the tracked
    /// amounts). None while the rate limiter is in force.
    pub fn model(&self) -> Option<(Fx, Fx, Fx)> {
        let f = self.fee_fixed?;
        let s = &self.s;
        let (ra, rb) = if s.collect_fee_mode == COLLECT_COMPOUNDING {
            (Fx::from_u64(s.token_a_amount), Fx::from_u64(s.token_b_amount))
        } else {
            let (l, p) = (Fx::from_u128(s.liquidity), Fx::from_u128(s.sqrt_price));
            (l.div(p), l.mul(p).shl(-128))
        };
        let (r_in, r_out) = if self.a_to_b { (ra, rb) } else { (rb, ra) };
        let den = Fx::from_u64(FEE_DENOMINATOR);
        let g = den.sub(Fx::from_u64(f)).div(den);
        let c = if fee_on_input(s.collect_fee_mode, self.a_to_b) { g } else { Fx::ONE };
        Some((g.mul(r_out), r_in, c))
    }

    /// The range-exit capacity (exact, closed form; DESIGN.md §2.5): the largest input whose next price stays
    /// inside [sqrt_min, sqrt_max]. None for a compounding pool (no range).
    pub fn cap_in(&self) -> Option<u64> {
        let s = &self.s;
        if s.collect_fee_mode == COLLECT_COMPOUNDING { return None; }
        let (l, p) = (s.liquidity, s.sqrt_price);
        let n_max: u128 = if self.a_to_b {
            let pmin = s.sqrt_min_price;
            if pmin <= 1 { return None; }
            if p < pmin { return Some(0); }
            let num = U256::mul128(l, (p - pmin).checked_add(1)?);
            let den = U256::mul128(pmin - 1, p);
            num.div_round(den, true)?.checked_sub(U256::ONE)?.to_u128().unwrap_or(u128::MAX)
        } else {
            if p > s.sqrt_max_price { return Some(0); }
            let prod = U256::mul128((s.sqrt_max_price - p).checked_add(1)?, l);
            let q = prod.shr(128);
            let up = if prod.low_bits_nonzero(128) { q.checked_add(U256::ONE)? } else { q };
            up.checked_sub(U256::ONE)?.to_u128().unwrap_or(u128::MAX)
        };
        // x − ⌈x·f/1e9⌉ = ⌊x·(1e9 − f)/1e9⌋, so the gross cap is ⌈(n_max + 1)·1e9/(1e9 − f)⌉ − 1
        let gross = match (fee_on_input(s.collect_fee_mode, self.a_to_b), self.fee_fixed) {
            (true, Some(f)) => n_max.checked_add(1).and_then(|v| v.checked_mul(FEE_DENOMINATOR as u128))
                .and_then(|v| crate::math::ceil_div(v, (FEE_DENOMINATOR - f) as u128)).map_or(u128::MAX, |v| v - 1),
            _ => n_max,
        };
        Some(u64::try_from(gross).unwrap_or(u64::MAX))
    }
}

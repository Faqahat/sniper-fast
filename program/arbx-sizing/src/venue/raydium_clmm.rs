//! Raydium CLMM (CAMMCzo5…) `swap_v2`, exact in and exact out (DESIGN.md §2.8; PLAN-ADDENDUM WP-21). Ported from
//! raydium-clmm ed1eb41 (2026-09-29, the commit of the deployed binary: programdata slot 451,479,902) and proven
//! against that binary in program/venue-harness (`tests/clmm_exactness.rs`, `tests/clmm_adversarial.rs`).
//!
//! The swap is the program's `swap_internal` loop, step for step and rounding for rounding:
//! * Q64.64 sqrt prices; `get_sqrt_price_at_tick` / `get_tick_at_sqrt_price` (BIT_PRECISION 16);
//! * the step maths of `swap_math::compute_swap` (fee on the input or, by the pool's `fee_on`, on the output; exact in
//!   and exact out), `liquidity_math::get_delta_amounts_for_swap` and the sqrt-price updates, over the full 512-bit
//!   products the program's U256/U512 mul-divs use;
//! * the dynamic fee (`DynamicFeeInfo`: the reference update at the swap's start, the volatility accumulator per
//!   tick-spacing group, sub-steps at every tick-spacing boundary while the accumulator is below its maximum);
//! * limit orders resting on initialized ticks (`TickState::match_limit_order_with_sqrt_price`: filled at the tick's
//!   price, the tick crossed only once they are gone);
//! * the tick arrays as the program reads them from the remaining accounts (classified by length, consumed front to
//!   back) and the pool's tick-array bitmap with the TickArrayBitmapExtension beyond its default range.
//!
//! [`RayClmmLeg::quote`] is exact or errs: `TooLarge` where the program fails (the passed tick arrays end, no liquidity
//! left in the direction, the extension is needed but not passed, an arithmetic limit, the output vault too small),
//! `ZeroOut` where it pays nothing (the program then fails TooSmallInputOrOutputAmount), `Budget` past the leg's walk
//! budget (swap steps; the venue would still fill). A state the program refuses at every size is an [`Abort`] at parse.
use crate::error::{Abort, ClmmWhy, Quote, QuoteErr};
use crate::fx::Fx;
use crate::math::{i128_at, i32_at, u128_at, u16_at, u32_at, u64_at, u8_at};
use crate::u256::{mul_div_wide, U256};
use crate::Clock;

pub const POOL_LEN: usize = 1_544;
pub const CONFIG_LEN: usize = 117;
pub const ARRAY_LEN: usize = 10_240;
pub const EXT_LEN: usize = 1_832;
pub const TICK_ARRAY_SIZE: i32 = 60;
pub const TICK_LEN: usize = 168;
/// remaining accounts a leg may pass: the bitmap extension and up to 6 tick arrays (the descriptor's 3-bit count)
pub const MAX_REMAINING: usize = 7;
/// no walk budget (off-chain use: the passed tick arrays bound the walk)
pub const NO_BUDGET: u16 = u16::MAX;
pub const MIN_TICK: i32 = -443_636;
pub const MAX_TICK: i32 = 443_636;
pub const MIN_SQRT_PRICE_X64: u128 = 4_295_048_016;
pub const MAX_SQRT_PRICE_X64: u128 = 79_226_673_521_066_979_257_578_248_091;
pub const FEE_RATE_DENOMINATOR: u32 = 1_000_000;
pub const MAX_FEE_RATE_NUMERATOR: u32 = 100_000;
const VA_SCALE: u64 = 10_000;
const REDUCTION_DEN: u64 = 10_000;
const DYN_FEE_CONTROL_DEN: u128 = 100_000;
const BITMAP_SIZE: i32 = 512;
const Q64: u128 = 1 << 64;

pub mod off {
    // PoolState (#[repr(C, packed)], after the 8-byte discriminator)
    pub const AMM_CONFIG: usize = 9;
    pub const MINT0: usize = 73;
    pub const MINT1: usize = 105;
    pub const VAULT0: usize = 137;
    pub const VAULT1: usize = 169;
    pub const OBSERVATION: usize = 201;
    pub const TICK_SPACING: usize = 235;
    pub const LIQUIDITY: usize = 237;
    pub const SQRT_PRICE: usize = 253;
    pub const TICK_CURRENT: usize = 269;
    pub const FEE_GROWTH0: usize = 277;
    pub const FEE_GROWTH1: usize = 293;
    pub const PROTOCOL_FEES0: usize = 309;
    pub const PROTOCOL_FEES1: usize = 317;
    pub const STATUS: usize = 389;
    pub const FEE_ON: usize = 390;
    pub const BITMAP: usize = 904;
    pub const FUND_FEES0: usize = 1_064;
    pub const FUND_FEES1: usize = 1_072;
    pub const OPEN_TIME: usize = 1_080;
    /// DynamicFeeInfo (80 bytes): filter u16, decay u16, reduction u16, control u32, max_va u32, idx_ref i32,
    /// v_ref u32, va u32, last_update u64, 46 bytes of padding
    pub const DYN: usize = 1_096;
    pub const DYN_LEN: usize = 80;
    // AmmConfig (Borsh)
    pub const C_PROTOCOL: usize = 43;
    pub const C_TRADE: usize = 47;
    pub const C_TICK_SPACING: usize = 51;
    pub const C_FUND: usize = 53;
    // TickArrayState
    pub const A_POOL: usize = 8;
    pub const A_START: usize = 40;
    pub const A_TICKS: usize = 44;
    pub const A_INIT_COUNT: usize = 10_124;
    // TickState (168 bytes)
    pub const T_TICK: usize = 0;
    pub const T_LIQ_NET: usize = 4;
    pub const T_LIQ_GROSS: usize = 20;
    pub const T_ORDER_PHASE: usize = 116;
    pub const T_ORDERS: usize = 124;
    pub const T_PART_FILLED: usize = 132;
    pub const T_UNFILLED_RATIO: usize = 140;
    // TickArrayBitmapExtension
    pub const E_POOL: usize = 8;
    pub const E_POSITIVE: usize = 40;
    pub const E_NEGATIVE: usize = 40 + 14 * 64;
}

type R<T> = Result<T, QuoteErr>;
const TOO_LARGE: QuoteErr = QuoteErr::TooLarge;

/// The pool's dynamic fee (DynamicFeeInfo), as the swap uses it after `update_reference`
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct DynFee {
    pub filter_period: u16,
    pub decay_period: u16,
    pub reduction_factor: u16,
    pub control: u32,
    pub max_va: u32,
    pub idx_ref: i32,
    pub v_ref: u32,
    pub va: u32,
    pub last_update: u64,
}

impl DynFee {
    fn read(p: &[u8]) -> Option<DynFee> {
        let o = off::DYN;
        Some(DynFee {
            filter_period: u16_at(p, o)?, decay_period: u16_at(p, o + 2)?, reduction_factor: u16_at(p, o + 4)?,
            control: u32_at(p, o + 6)?, max_va: u32_at(p, o + 10)?, idx_ref: i32_at(p, o + 14)?, v_ref: u32_at(p, o + 18)?,
            va: u32_at(p, o + 22)?, last_update: u64_at(p, o + 26)?,
        })
    }

    /// `update_volatility_accumulator`: va = min(v_ref + |idx_ref − idx|·1e4, max_va)
    fn update_va(&mut self, idx: i32) -> Option<()> {
        let d = self.idx_ref.checked_sub(idx)?.unsigned_abs() as u64;
        self.va = (self.v_ref as u64 + d * VA_SCALE).min(self.max_va as u64) as u32;
        Some(())
    }

    /// `update_reference` at the swap's start
    fn update_reference(&mut self, idx: i32, now: u64) {
        let elapsed = now.saturating_sub(self.last_update);
        if elapsed < self.filter_period as u64 {
        } else if elapsed < self.decay_period as u64 {
            self.idx_ref = idx;
            self.v_ref = (self.va as u64 * self.reduction_factor as u64 / REDUCTION_DEN) as u32;
            self.last_update = now;
        } else {
            self.idx_ref = idx;
            self.v_ref = 0;
            self.last_update = now;
        }
    }

    /// `compute_dynamic_fee_rate`: ⌈control·(va·tick_spacing)²/(1e5·1e4·1e4)⌉, at most 1e5. None: the u32 product
    /// overflows (the program panics)
    fn rate(&self, tick_spacing: u16) -> Option<u32> {
        let crossed = self.va.checked_mul(tick_spacing as u32)?;
        let sq = crossed as u64 as u128 * crossed as u64 as u128;
        let den = DYN_FEE_CONTROL_DEN * VA_SCALE as u128 * VA_SCALE as u128;
        let num = (self.control as u128).checked_mul(sq)?;
        let fee = num / den + (num % den != 0) as u128;
        Some(if fee > MAX_FEE_RATE_NUMERATOR as u128 { MAX_FEE_RATE_NUMERATOR } else { fee as u32 })
    }
}

/// ⌊tick / tick_spacing⌋ (`tick_spacing_index_from_tick`)
pub fn tick_spacing_index(tick: i32, ts: u16) -> i32 { tick.div_euclid(ts as i32) }

/// The tick array start index of a tick (`TickArrayState::get_array_start_index`)
pub fn array_start(tick: i32, ts: u16) -> i32 { let n = TICK_ARRAY_SIZE * ts as i32; tick.div_euclid(n) * n }

fn out_of_bounds(tick: i32) -> bool { !(MIN_TICK..=MAX_TICK).contains(&tick) }

/// `TickArrayState::check_is_valid_start_index`
pub fn valid_start(start: i32, ts: u16) -> bool {
    if out_of_bounds(start) {
        if start > MAX_TICK { return false; }
        return start == array_start(MIN_TICK, ts);
    }
    start % (TICK_ARRAY_SIZE * ts as i32) == 0
}

/// `get_sqrt_price_at_tick` (Q64.64, the program's magic factors); None out of the tick range
pub fn sqrt_price_at_tick(tick: i32) -> Option<u128> {
    if out_of_bounds(tick) { return None; }
    let a = tick.unsigned_abs();
    const F: [u128; 18] = [
        0xfff97272373d4000, 0xfff2e50f5f657000, 0xffe5caca7e10f000, 0xffcb9843d60f7000, 0xff973b41fa98e800,
        0xff2ea16466c9b000, 0xfe5dee046a9a3800, 0xfcbe86c7900bb000, 0xf987a7253ac65800, 0xf3392b0822bb6000,
        0xe7159475a2caf000, 0xd097f3bdfd2f2000, 0xa9f746462d9f8000, 0x70d869a156f31c00, 0x31be135f97ed3200,
        0x9aa508b5b85a500, 0x5d6af8dedc582c, 0x2216e584f5fa,
    ];
    let mut ratio: u128 = if a & 1 != 0 { 0xfffcb933bd6fb800 } else { Q64 };
    for (i, f) in F.iter().enumerate() {
        if a & (2 << i) != 0 { ratio = (ratio * f) >> 64; }
    }
    if tick > 0 { ratio = u128::MAX / ratio; }
    Some(ratio)
}

/// `get_tick_at_sqrt_price`: the greatest tick whose sqrt price is at most `p`; None outside [MIN, MAX)
pub fn tick_at_sqrt_price(p: u128) -> Option<i32> {
    if !(MIN_SQRT_PRICE_X64..MAX_SQRT_PRICE_X64).contains(&p) { return None; }
    let msb = 128 - p.leading_zeros() - 1;
    let log2p_integer_x32 = (msb as i128 - 64) << 32;
    let mut bit: i128 = 0x8000_0000_0000_0000;
    let mut precision = 0;
    let mut log2p_fraction_x64: i128 = 0;
    let mut r = if msb >= 64 { p >> (msb - 63) } else { p << (63 - msb) };
    while bit > 0 && precision < 16 {
        r *= r;
        let more = r >> 127;
        r >>= 63 + more;
        log2p_fraction_x64 += bit * more as i128;
        bit >>= 1;
        precision += 1;
    }
    let log2p_x32 = log2p_integer_x32 + (log2p_fraction_x64 >> 32);
    let log_sqrt_10001_x64 = log2p_x32 * 59_543_866_431_248i128;
    let tick_low = ((log_sqrt_10001_x64 - 184_467_440_737_095_516i128) >> 64) as i32;
    let tick_high = ((log_sqrt_10001_x64 + 15_793_534_762_490_258_745i128) >> 64) as i32;
    if tick_low == tick_high { return Some(tick_low); }
    Some(if sqrt_price_at_tick(tick_high)? <= p { tick_high } else { tick_low })
}

/// `get_price_from_sqrt_price` (the token-0 price, Q64.64): ⌊p²/2^64⌋, or ⌈⌉ with `up`; None past u128
fn price_from_sqrt_price(p: u128, up: bool) -> Option<u128> {
    let prod = U256::mul128(p, p);
    let prod = if up { prod.checked_add(U256::from_u128(Q64 - 1))? } else { prod };
    prod.shr(64).to_u128()
}

/// ⌊a·b/d⌋ or ⌈⌉ of u64 operands (the program's `u64::mul_div_*`, in U128): None for d = 0 or a result past u64
fn mul_div_u64(a: u64, b: u64, d: u64, up: bool) -> Option<u64> {
    if d == 0 { return None; }
    let p = a as u128 * b as u128;
    let q = p / d as u128 + (up && p % d as u128 != 0) as u128;
    u64::try_from(q).ok()
}

/// ⌊a·b/d⌋ or ⌈⌉ of u128 operands (the program's `U128::mul_div_*`, U256 on overflow): None for d = 0 or past u128
fn mul_div_u128(a: u128, b: u128, d: u128, up: bool) -> Option<u128> {
    if d == 0 { return None; }
    mul_div_wide(U256::from_u128(a), U256::from_u128(b), U256::from_u128(d), up)?.to_u128()
}

/// ⌈x·2^64/d⌉ or ⌊⌋ for U256 operands (`mul_pow2_div_*` with shift 64): None for d = 0 or past U256
fn mul_q64_div(x: U256, d: U256, up: bool) -> Option<U256> { mul_div_wide(x, U256::from_u128(Q64), d, up) }

/// Why `get_delta_amounts_for_swap` failed: an amount past u64 (`MaxTokenOverflow`, which `compute_swap` reads as "the
/// target is not reachable") or any other error
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Delta { MaxToken, Other }

/// `get_delta_amounts_for_swap`: (amount in rounded up, amount out rounded down) between two sqrt prices
fn delta_amounts(a: u128, b: u128, liq: u128, zfo: bool) -> Result<(u64, u64), Delta> {
    let (sa, sb) = if a > b { (b, a) } else { (a, b) };
    if sa == 0 { return Err(Delta::Other); }
    let x = U256::mul128(liq, sb - sa);
    let prod = U256::mul128(sa, sb);
    let (ain, aout) = if zfo {
        (mul_q64_div(x, prod, true).ok_or(Delta::Other)?, x.shr(64))
    } else {
        (x.checked_add(U256::from_u128(u64::MAX as u128)).ok_or(Delta::Other)?.shr(64), mul_q64_div(x, prod, false).ok_or(Delta::Other)?)
    };
    if !ain.fits_u64() || !aout.fits_u64() { return Err(Delta::MaxToken); }
    Ok((ain.low_u64(), aout.low_u64()))
}

/// `get_next_sqrt_price_from_amount_0_rounding_up`
fn next_from_amount0(p: u128, liq: u128, amount: u64, add: bool) -> Option<u128> {
    if amount == 0 { return Some(p); }
    let n1 = U256::from_u128(liq).shl(64)?;
    let product = U256::mul128(amount as u128, p);
    let den = if add { n1.checked_add(product)? } else { n1.checked_sub(product)? };
    if den.is_zero() { return None; }
    mul_div_wide(n1, U256::from_u128(p), den, true)?.to_u128()
}

/// `get_next_sqrt_price_from_amount_1_rounding_down`
fn next_from_amount1(p: u128, liq: u128, amount: u64, add: bool) -> Option<u128> {
    if amount == 0 { return Some(p); }
    if liq == 0 { return None; }
    let n = (amount as u128) << 64;
    if add { p.checked_add(n / liq) } else { p.checked_sub(n / liq + (n % liq != 0) as u128) }
}

fn next_from_input(p: u128, liq: u128, amount: u64, zfo: bool) -> Option<u128> {
    if !(MIN_SQRT_PRICE_X64..MAX_SQRT_PRICE_X64).contains(&p) || liq == 0 { return None; }
    if zfo { next_from_amount0(p, liq, amount, true) } else { next_from_amount1(p, liq, amount, true) }
}

fn next_from_output(p: u128, liq: u128, amount: u64, zfo: bool) -> Option<u128> {
    if !(MIN_SQRT_PRICE_X64..MAX_SQRT_PRICE_X64).contains(&p) || liq == 0 { return None; }
    if zfo { next_from_amount1(p, liq, amount, false) } else { next_from_amount0(p, liq, amount, false) }
}

/// One step of `compute_swap`
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct StepAmounts { pub next: u128, pub amount_in: u64, pub amount_out: u64, pub fee: u64 }

/// `swap_math::compute_swap`, rounding for rounding. None: the program errors
#[allow(clippy::too_many_arguments)]
fn compute_swap(cur: u128, target: u128, liq: u128, remaining: u64, fee_rate: u32, base_input: bool, zfo: bool, fee_on_input: bool) -> Option<StepAmounts> {
    let keep = FEE_RATE_DENOMINATOR.checked_sub(fee_rate)?;
    let calc = if base_input {
        if fee_on_input { mul_div_u64(remaining, keep as u64, FEE_RATE_DENOMINATOR as u64, false)? } else { remaining }
    } else if fee_on_input { remaining } else { mul_div_u64(remaining, FEE_RATE_DENOMINATOR as u64, keep as u64, true)? };
    let reach = match delta_amounts(target, cur, liq, zfo) {
        Ok((ain, aout)) => {
            let limit = if base_input { ain } else { aout };
            if calc >= limit { Some((ain, aout)) } else { None }
        }
        Err(Delta::MaxToken) => None,
        Err(Delta::Other) => return None,
    };
    let mut r = StepAmounts::default();
    if let Some((ain, aout)) = reach {
        r.next = target;
        r.amount_in = ain;
        r.amount_out = aout;
    } else {
        let next = if base_input { next_from_input(cur, liq, calc, zfo)? } else { next_from_output(cur, liq, calc, zfo)? };
        r.next = next;
        let (ain, aout) = delta_amounts(next, cur, liq, zfo).ok()?;
        r.amount_in = ain;
        r.amount_out = aout;
    }
    if zfo { if r.next < target { return None; } } else if target < r.next { return None; }
    let reached = r.next == target;
    if base_input {
        if fee_on_input {
            r.fee = if !reached { remaining.checked_sub(r.amount_in)? } else { mul_div_u64(r.amount_in, fee_rate as u64, keep as u64, true)? };
        } else {
            r.fee = mul_div_u64(r.amount_out, fee_rate as u64, FEE_RATE_DENOMINATOR as u64, true)?;
            r.amount_out = r.amount_out.checked_sub(r.fee)?;
            if !reached { r.amount_in = remaining; }
        }
    } else if fee_on_input {
        r.amount_out = r.amount_out.min(remaining);
        r.fee = mul_div_u64(r.amount_in, fee_rate as u64, keep as u64, true)?;
    } else {
        r.fee = mul_div_u64(r.amount_out, fee_rate as u64, FEE_RATE_DENOMINATOR as u64, true)?;
        let net = r.amount_out.checked_sub(r.fee)?;
        if net > remaining {
            r.fee = r.amount_out.checked_sub(remaining)?;
            r.amount_out = remaining;
        } else {
            r.amount_out = net;
        }
    }
    Some(r)
}

/// One TickState as the swap reads (and writes) it
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Tick {
    /// the stored tick index (the program uses this field, not the slot's position)
    pub tick: i32,
    pub liquidity_net: i128,
    pub liquidity_gross: u128,
    pub order_phase: u64,
    pub orders_amount: u64,
    pub part_filled_orders_remaining: u64,
    pub unfilled_ratio_x64: u128,
}

impl Tick {
    fn read(a: &[u8], slot: usize) -> Option<Tick> {
        let o = off::A_TICKS + slot * TICK_LEN;
        Some(Tick {
            tick: i32_at(a, o + off::T_TICK)?, liquidity_net: i128_at(a, o + off::T_LIQ_NET)?, liquidity_gross: u128_at(a, o + off::T_LIQ_GROSS)?,
            order_phase: u64_at(a, o + off::T_ORDER_PHASE)?, orders_amount: u64_at(a, o + off::T_ORDERS)?,
            part_filled_orders_remaining: u64_at(a, o + off::T_PART_FILLED)?, unfilled_ratio_x64: u128_at(a, o + off::T_UNFILLED_RATIO)?,
        })
    }
    pub fn has_liquidity(&self) -> bool { self.liquidity_gross > 0 }
    pub fn has_limit_orders(&self) -> bool { self.orders_amount > 0 || self.part_filled_orders_remaining > 0 }
    pub fn is_initialized(&self) -> bool { self.has_liquidity() || self.has_limit_orders() }
    fn unfilled(&self) -> Option<u64> { self.orders_amount.checked_add(self.part_filled_orders_remaining) }
}

/// What the limit orders of one tick gave a swap (`LimitOrderMatchResult`)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct LimitFill { pub amount_in: u64, pub amount_out: u64, pub fee: u64 }

/// `match_limit_order_with_sqrt_price`: fills the tick's resting orders at its price, updating `t` like the program
#[allow(clippy::too_many_arguments)]
fn match_limit_orders(t: &mut Tick, swap_amount: u64, zfo: bool, base_input: bool, fee_rate: u32, fee_on_input: bool, sqrt_price: u128) -> Option<LimitFill> {
    let mut r = LimitFill::default();
    let total = t.unfilled()?;
    if swap_amount == 0 || total == 0 { return Some(r); }
    let price = price_from_sqrt_price(sqrt_price, !zfo)?;
    let keep = FEE_RATE_DENOMINATOR.checked_sub(fee_rate)?;
    // the output of `amount_in` at the tick's price, rounded down (`get_limit_order_output_with_price`, the swap's
    // direction), and the input of `out`, rounded up (`get_limit_order_input_with_price`, called with the ORDER's
    // direction: the opposite of the swap's)
    let output_of = |a: u64| if zfo { mul_div_u128(a as u128, price, Q64, false) } else { mul_div_u128(a as u128, Q64, price, false) };
    let input_of = |o: u64| -> Option<u64> {
        let v = if zfo { mul_div_u128(o as u128, Q64, price, true)? } else { mul_div_u128(o as u128, price, Q64, true)? };
        u64::try_from(v).ok()
    };
    if base_input {
        if fee_on_input {
            r.fee = mul_div_u64(swap_amount, fee_rate as u64, FEE_RATE_DENOMINATOR as u64, true)?;
            r.amount_in = swap_amount - r.fee;
        } else {
            r.amount_in = swap_amount;
        }
        let matched = output_of(r.amount_in)?;
        if matched > total as u128 {
            r.amount_out = total;
            r.amount_in = input_of(total)?;
            if fee_on_input { r.fee = mul_div_u64(r.amount_in, fee_rate as u64, keep as u64, true)?; }
        } else {
            r.amount_out = matched as u64;
        }
    } else {
        let net = swap_amount.min(total);
        r.amount_out = if fee_on_input { net } else { mul_div_u64(net, FEE_RATE_DENOMINATOR as u64, keep as u64, true)?.min(total) };
        r.amount_in = input_of(r.amount_out)?;
        if fee_on_input { r.fee = mul_div_u64(r.amount_in, fee_rate as u64, keep as u64, true)?; }
    }
    // the orders' own bookkeeping (FIFO: the part-filled cohort first)
    let mut from_part = 0;
    if t.part_filled_orders_remaining > 0 {
        from_part = t.part_filled_orders_remaining.min(r.amount_out);
        if from_part > 0 {
            t.unfilled_ratio_x64 = mul_div_u128(t.unfilled_ratio_x64, (t.part_filled_orders_remaining - from_part) as u128, t.part_filled_orders_remaining as u128, false)?;
        }
        t.part_filled_orders_remaining = t.part_filled_orders_remaining.saturating_sub(from_part);
    }
    let more = r.amount_out.saturating_sub(from_part);
    if more > 0 {
        if t.part_filled_orders_remaining != 0 || t.orders_amount < more { return None; }
        t.order_phase = t.order_phase.saturating_add(1);
        t.unfilled_ratio_x64 = mul_div_u128(Q64, (t.orders_amount - more) as u128, t.orders_amount as u128, false)?;
        t.part_filled_orders_remaining = t.orders_amount - more;
        t.orders_amount = 0;
    }
    if !fee_on_input {
        r.fee = mul_div_u64(r.amount_out, fee_rate as u64, FEE_RATE_DENOMINATOR as u64, true)?;
        r.amount_out = r.amount_out.checked_sub(r.fee)?;
    }
    Some(r)
}

/// A parsed Raydium CLMM leg: the pool's swap fields, its bitmaps and the remaining accounts the leg passes (read in
/// place), in one direction
#[derive(Clone, Copy, Debug)]
pub struct RayClmmLeg<'a> {
    /// token 0 in (price down)
    pub zfo: bool,
    pub fee_on_input: bool,
    /// the fee token is token 0 (`is_fee_on_token0`)
    pub fee_on_token0: bool,
    pub trade_fee_rate: u32,
    pub protocol_fee_rate: u32,
    pub fund_fee_rate: u32,
    pub tick_spacing: u16,
    pub sqrt_price: u128,
    pub tick: i32,
    pub liquidity: u128,
    /// the dynamic fee after the swap's `update_reference` (None: the pool has none)
    pub dynamic: Option<DynFee>,
    /// the Clock's unix timestamp as the program reads it (u32)
    pub block_ts: u32,
    /// the output vault's balance (what the program can transfer out)
    pub vault_out: u64,
    /// the fee token's protocol and fund fees owed (the swap's checked additions) and its global fee growth
    pub fees_owed: (u64, u64),
    pub fee_growth_global: u128,
    pool: &'a [u8],
    ext: Option<&'a [u8]>,
    /// the tick arrays in the order the leg passes them
    arrays: [&'a [u8]; MAX_REMAINING],
    n_arrays: u8,
    /// the first tick array the swap reads: (start index, it holds the current tick)
    first: (i32, bool),
    /// swap steps a walk may take ([`NO_BUDGET`]: unbounded)
    budget: u16,
}

/// Parse the pool, its AmmConfig and the leg's remaining accounts (`remaining`: in the order passed; each classified by
/// its length as the program does: a 10,240-byte tick array, the 1,832-byte bitmap extension; the first account of
/// another length ends the list). Owner, discriminator and key checks are the caller's (leg.rs). `vault0`/`vault1`: the
/// pool's token-0/token-1 vault amounts.
pub fn parse<'a>(pool: &'a [u8], cfg: &[u8], remaining: &[&'a [u8]], vault0: u64, vault1: u64, zero_for_one: bool, clock: &Clock) -> Result<RayClmmLeg<'a>, Abort> {
    if pool.len() != POOL_LEN || cfg.len() != CONFIG_LEN { return Err(Abort::Layout); }
    let l = Abort::Layout;
    let status = u8_at(pool, off::STATUS).ok_or(l)?;
    if (status >> 4) & 1 != 0 { return Err(Abort::Clmm(ClmmWhy::Status)); }
    // exact_internal_v2: require_gt!(unix_timestamp as u64, open_time)
    if (clock.unix_timestamp as u64) <= u64_at(pool, off::OPEN_TIME).ok_or(l)? { return Err(Abort::Clmm(ClmmWhy::NotOpen)); }
    let fee_on = u8_at(pool, off::FEE_ON).ok_or(l)?;
    // `is_fee_on_input` / `is_fee_on_token0` read any other value as FromInput
    let (fee_on_input, fee_on_token0) = match fee_on {
        1 => (zero_for_one, true),
        2 => (!zero_for_one, false),
        _ => (true, zero_for_one),
    };
    let tick_spacing = u16_at(pool, off::TICK_SPACING).ok_or(l)?;
    if tick_spacing == 0 { return Err(Abort::Clmm(ClmmWhy::State)); }
    let trade_fee_rate = u32_at(cfg, off::C_TRADE).ok_or(l)?;
    if trade_fee_rate > FEE_RATE_DENOMINATOR { return Err(Abort::Clmm(ClmmWhy::Fee)); }
    let sqrt_price = u128_at(pool, off::SQRT_PRICE).ok_or(l)?;
    let tick = i32_at(pool, off::TICK_CURRENT).ok_or(l)?;
    // swap_internal: the default limit (MIN+1 or MAX−1) must lie strictly beyond the pool's price
    if (zero_for_one && sqrt_price <= MIN_SQRT_PRICE_X64 + 1) || (!zero_for_one && sqrt_price >= MAX_SQRT_PRICE_X64 - 1) {
        return Err(Abort::Clmm(ClmmWhy::PriceLimit));
    }
    if out_of_bounds(tick) { return Err(Abort::Clmm(ClmmWhy::State)); }
    let block_ts = clock.unix_timestamp as u32;
    // the dynamic fee: None when the whole DynamicFeeInfo is zero (its derived equality includes the padding)
    let dyn_bytes = pool.get(off::DYN..off::DYN + off::DYN_LEN).ok_or(l)?;
    let dynamic = if dyn_bytes.iter().all(|&b| b == 0) { None } else {
        let mut d = DynFee::read(pool).ok_or(l)?;
        d.update_reference(tick_spacing_index(tick, tick_spacing), block_ts as u64);
        Some(d)
    };
    // the remaining accounts, classified by length (a tick array, the extension; anything else ends the list)
    let mut arrays: [&'a [u8]; MAX_REMAINING] = [&[]; MAX_REMAINING];
    let (mut n, mut ext) = (0usize, None);
    for a in remaining.iter().take(MAX_REMAINING) {
        match a.len() {
            ARRAY_LEN => { if let Some(s) = arrays.get_mut(n) { *s = a; n += 1; } }
            EXT_LEN => ext = Some(*a),
            _ => break,
        }
    }
    let vault_out = if zero_for_one { vault1 } else { vault0 };
    let (pf, ff, fg) = if fee_on_token0 { (off::PROTOCOL_FEES0, off::FUND_FEES0, off::FEE_GROWTH0) } else { (off::PROTOCOL_FEES1, off::FUND_FEES1, off::FEE_GROWTH1) };
    let mut leg = RayClmmLeg {
        zfo: zero_for_one, fee_on_input, fee_on_token0, trade_fee_rate,
        protocol_fee_rate: u32_at(cfg, off::C_PROTOCOL).ok_or(l)?, fund_fee_rate: u32_at(cfg, off::C_FUND).ok_or(l)?,
        tick_spacing, sqrt_price, tick, liquidity: u128_at(pool, off::LIQUIDITY).ok_or(l)?, dynamic, block_ts, vault_out,
        fees_owed: (u64_at(pool, pf).ok_or(l)?, u64_at(pool, ff).ok_or(l)?), fee_growth_global: u128_at(pool, fg).ok_or(l)?,
        pool, ext, arrays, n_arrays: n as u8, first: (0, false), budget: NO_BUDGET,
    };
    // the first tick array (`first_tick_array_index_with_extension_info`): every size fails without it
    leg.first = leg.first_array().map_err(Abort::Clmm)?;
    Ok(leg)
}

/// Why a walk ended (the CAP conditions of [`RayClmmLeg`])
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum End { Cap, Budget }

/// One step of an exact swap, for [`RayClmmLeg::fills`]: the price range it covered, its liquidity and fee rate, and
/// what it took and gave; `tick` is the initialized tick it ended on (crossed when `crossed`), `limit` the limit orders
/// it filled there
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ClmmStep {
    pub sqrt_price_from: u128,
    pub sqrt_price_to: u128,
    pub liquidity: u128,
    pub fee_rate: u32,
    pub amount_in: u64,
    pub amount_out: u64,
    pub fee: u64,
    pub tick: Option<i32>,
    pub crossed: bool,
    pub limit: Option<(LimitFill, Tick)>,
    /// the start index of the tick array the step read
    pub array: i32,
}

/// An exact swap's walk ([`RayClmmLeg::fills`]): its quote, the steps taken, the initialized ticks crossed, the tick
/// arrays read (in order: the leg must pass them in this order) and the post-swap pool state
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ClmmWalk {
    pub quote: Quote,
    pub steps: u16,
    pub crossed: u16,
    pub arrays: [i32; MAX_REMAINING],
    pub n_arrays: u8,
    pub post: PostSwap,
}

/// The pool after a swap (`update_after_swap`): what the next swap reads
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct PostSwap {
    pub sqrt_price: u128,
    pub tick: i32,
    pub liquidity: u128,
    /// the fee token's global fee growth and its protocol / fund fees owed (the fee token: [`RayClmmLeg::fee_on_token0`])
    pub fee_growth_global: u128,
    pub protocol_fees: u64,
    pub fund_fees: u64,
    pub dynamic: Option<DynFee>,
}

/// The initialized tick an outer iteration of the program's loop is moving to
#[derive(Clone, Copy, Debug)]
struct Pending { next: Tick, tick_next: i32, price_next: u128, target: u128, liquidity_next: u128 }

/// The swap state machine (`SwapState` with the tick-array cursor and the outer iteration in progress). A plain value: a
/// copy resumes from the same place.
#[derive(Clone, Copy, Debug)]
struct Walker {
    /// the current tick array: its slot in the leg's list, its start index, its initialized_tick_count as the swap leaves
    /// it; the start of the last array found valid
    cur: usize,
    cur_start: i32,
    cur_count: u8,
    cur_valid: i32,
    first_contains: bool,
    remaining: u64,
    calculated: u64,
    sqrt_price: u128,
    tick: i32,
    liquidity: u128,
    fee_growth: u128,
    lp_fee: u64,
    protocol_fee: u64,
    fund_fee: u64,
    dynamic: Option<DynFee>,
    ts_index: i32,
    pending: Option<Pending>,
    steps: u16,
    crossed: u16,
    arrays_read: [i32; MAX_REMAINING],
    n_read: u8,
}

impl<'a> RayClmmLeg<'a> {
    /// the leg with a walk budget of `steps` swap steps (the descriptor's `max_bins`)
    pub fn with_budget(mut self, steps: u16) -> Self { self.budget = steps; self }
    pub fn budget(&self) -> u16 { self.budget }
    /// the tick arrays the leg passes, in order (start indexes)
    pub fn array_starts(&self) -> impl Iterator<Item = i32> + '_ {
        self.arrays.iter().take(self.n_arrays as usize).filter_map(|a| i32_at(a, off::A_START))
    }
    /// the bitmap extension is among the leg's remaining accounts
    pub fn has_extension(&self) -> bool { self.ext.is_some() }

    fn bitmap_word(&self, w: usize) -> u64 { u64_at(self.pool, off::BITMAP + 8 * w).unwrap_or(0) }

    /// (min, max) start index the default bitmap covers (`tick_array_start_index_range`)
    fn default_range(&self) -> (i32, i32) {
        let ts = self.tick_spacing;
        let mut max = ts as i32 * TICK_ARRAY_SIZE * BITMAP_SIZE;
        let mut min = -max;
        if max > MAX_TICK { max = array_start(MAX_TICK, ts) + TICK_ARRAY_SIZE * ts as i32; }
        if min < MIN_TICK { min = array_start(MIN_TICK, ts); }
        (min, max)
    }

    /// `is_overflow_default_tickarray_bitmap` of one tick
    pub fn overflows_default(&self, tick: i32) -> bool {
        let (min, max) = self.default_range();
        let s = array_start(tick, self.tick_spacing);
        s >= max || s < min
    }

    /// bit `pos` (0..1024) of the pool's default bitmap
    fn default_bit(&self, pos: i32) -> bool { (0..1024).contains(&pos) && self.bitmap_word(pos as usize / 64) >> (pos % 64) & 1 == 1 }

    /// `check_current_tick_array_is_initialized` (default bitmap)
    fn current_initialized_default(&self, tick: i32) -> Result<(bool, i32), ClmmWhy> {
        if out_of_bounds(tick) { return Err(ClmmWhy::State); }
        let m = self.tick_spacing as i32 * TICK_ARRAY_SIZE;
        let compressed = tick.div_euclid(m) + 512;
        Ok((self.default_bit(compressed.abs()), (compressed - 512) * m))
    }

    /// `next_initialized_tick_array_start_index` over the default bitmap: (found, start or the boundary reached). None:
    /// the program errors (InvalidTickArrayBoundary)
    fn next_default(&self, last: i32, zfo: bool) -> Option<(bool, i32)> {
        let ts = self.tick_spacing;
        if !valid_start(last, ts) { return None; }
        let m = ts as i32 * TICK_ARRAY_SIZE;
        let boundary = m * BITMAP_SIZE;
        let next = if zfo { last - m } else { last + m };
        if next < -boundary || next >= boundary { return Some((false, last)); }
        let pos = (next.div_euclid(m) + 512).abs();
        if zfo {
            // the highest set bit at or below `pos`
            let mut p = pos;
            while p >= 0 {
                let mask = if p % 64 == 63 { u64::MAX } else { (1u64 << (p % 64 + 1)) - 1 };
                let w = self.bitmap_word(p as usize / 64) & mask;
                if w != 0 { return Some((true, ((p / 64) * 64 + 63 - w.leading_zeros() as i32 - 512) * m)); }
                p = (p / 64) * 64 - 1;
            }
            Some((false, -boundary))
        } else {
            let mut p = pos;
            while p < 1024 {
                let w = self.bitmap_word(p as usize / 64) & (u64::MAX << (p % 64));
                if w != 0 { return Some((true, ((p / 64) * 64 + w.trailing_zeros() as i32 - 512) * m)); }
                p = (p / 64 + 1) * 64;
            }
            Some((false, boundary - m))
        }
    }

    /// the extension bitmap holding `start` and the bit within it (`get_bitmap` + `tick_array_offset_in_bitmap`). None:
    /// the program errors (a start inside the default range or invalid, tick spacing ≥ 15, no bitmap for it)
    fn ext_bitmap(&self, start: i32) -> Option<(usize, i32)> {
        let ts = self.tick_spacing;
        if !valid_start(start, ts) { return None; }
        let b = ts as i32 * TICK_ARRAY_SIZE * BITMAP_SIZE;
        if MAX_TICK <= b || -b <= MIN_TICK || (start >= -b && start < b) { return None; }
        let mut offset = start.abs() / b - 1;
        if start < 0 && start.abs() % b == 0 { offset -= 1; }
        if !(0..14).contains(&offset) { return None; }
        let base = (if start < 0 { off::E_NEGATIVE } else { off::E_POSITIVE }) + 64 * offset as usize;
        let mm = start.abs() % b;
        let mut bit = mm / (TICK_ARRAY_SIZE * ts as i32);
        if start < 0 && mm != 0 { bit = BITMAP_SIZE - bit; }
        Some((base, bit))
    }

    fn ext_word(ext: &[u8], base: usize, w: i32) -> u64 { u64_at(ext, base + 8 * w as usize).unwrap_or(0) }

    /// `TickArrayBitmapExtension::check_tick_array_is_initialized`
    fn ext_initialized(&self, ext: &[u8], start: i32) -> Option<bool> {
        let (base, bit) = self.ext_bitmap(start)?;
        if !(0..512).contains(&bit) { return Some(false); }
        Some(Self::ext_word(ext, base, bit / 64) >> (bit % 64) & 1 == 1)
    }

    /// `next_initialized_tick_array_from_one_bitmap`: (found, start or the boundary reached)
    fn next_ext(&self, ext: &[u8], last: i32, zfo: bool) -> Option<(bool, i32)> {
        let ts = self.tick_spacing;
        let m = TICK_ARRAY_SIZE * ts as i32;
        let next = if zfo { last - m } else { last + m };
        if next < array_start(MIN_TICK, ts) || next > array_start(MAX_TICK, ts) { return Some((false, next)); }
        let (base, offset) = self.ext_bitmap(next)?;
        let b = m * BITMAP_SIZE;
        let mut k = next.abs() / b;
        if next < 0 && next.abs() % b != 0 { k += 1; }
        let min_v = b * k;
        let (bmin, bmax) = if next < 0 { (-min_v, -min_v + b) } else { (min_v, min_v + b) };
        if zfo {
            // the highest set bit at or below `offset` (the program shifts the bits above it out)
            let mut p = offset.min(511);
            if offset <= 511 {
                while p >= 0 {
                    let mask = if p % 64 == 63 { u64::MAX } else { (1u64 << (p % 64 + 1)) - 1 };
                    let w = Self::ext_word(ext, base, p / 64) & mask;
                    if w != 0 { let hi = (p / 64) * 64 + 63 - w.leading_zeros() as i32; return Some((true, next - (offset - hi) * m)); }
                    p = (p / 64) * 64 - 1;
                }
            }
            Some((false, bmin))
        } else {
            let mut p = offset.max(0);
            if offset >= 0 {
                while p < 512 {
                    let w = Self::ext_word(ext, base, p / 64) & (u64::MAX << (p % 64));
                    if w != 0 { let lo = (p / 64) * 64 + w.trailing_zeros() as i32; return Some((true, next + (lo - offset) * m)); }
                    p = (p / 64 + 1) * 64;
                }
            }
            Some((false, bmax - m))
        }
    }

    /// `next_tick_array_index_with_extension_info`. Err: the program errors (the extension needed but not passed, a
    /// bitmap error); Ok(None): no initialized tick array left in the direction (LiquidityInsufficient)
    fn next_array(&self, last: i32, zfo: bool) -> Result<Option<i32>, ClmmWhy> {
        let ts = self.tick_spacing;
        let mut last = array_start(last, ts);
        // every round moves past at least one bitmap of 512 arrays: 64 rounds cover the tick range several times
        for _ in 0..64 {
            let (found, s) = self.next_default(last, zfo).ok_or(ClmmWhy::State)?;
            if found { return Ok(Some(s)); }
            if ts >= 15 { return Ok(None); }
            last = s;
            let ext = self.ext.ok_or(ClmmWhy::BitmapExtension)?;
            let (found, s) = self.next_ext(ext, last, zfo).ok_or(ClmmWhy::State)?;
            if found { return Ok(Some(s)); }
            last = s;
            if !(MIN_TICK..=MAX_TICK).contains(&last) { return Ok(None); }
        }
        Err(ClmmWhy::State)
    }

    /// `first_tick_array_index_with_extension_info`: (start, it holds the current tick); that start must be among the
    /// leg's tick arrays
    fn first_array(&self) -> Result<(i32, bool), ClmmWhy> {
        let ts = self.tick_spacing;
        let cur = array_start(self.tick, ts);
        let (init, start) = if self.overflows_default(self.tick) {
            let ext = self.ext.ok_or(ClmmWhy::BitmapExtension)?;
            (self.ext_initialized(ext, cur).ok_or(ClmmWhy::State)?, cur)
        } else {
            self.current_initialized_default(self.tick)?
        };
        let first = if init { (start, true) } else { (self.next_array(cur, self.zfo)?.ok_or(ClmmWhy::NoLiquidity)?, false) };
        if !self.array_starts().any(|s| s == first.0) { return Err(ClmmWhy::TickArrays); }
        Ok(first)
    }

    fn array(&self, slot: usize) -> Option<&'a [u8]> { if slot < self.n_arrays as usize { self.arrays.get(slot).copied() } else { None } }

    /// the walker at the swap's start: the first tick array found among the passed ones, front to back
    fn walker(&self, amount: u64) -> Option<Walker> {
        let slot = (0..self.n_arrays as usize).find(|&k| self.array(k).and_then(|a| i32_at(a, off::A_START)) == Some(self.first.0))?;
        let a = self.array(slot)?;
        let mut w = Walker {
            cur: slot, cur_start: self.first.0, cur_count: u8_at(a, off::A_INIT_COUNT)?, cur_valid: self.first.0, first_contains: self.first.1,
            remaining: amount, calculated: 0, sqrt_price: self.sqrt_price, tick: self.tick, liquidity: self.liquidity,
            fee_growth: self.fee_growth_global, lp_fee: 0, protocol_fee: 0, fund_fee: 0, dynamic: self.dynamic,
            ts_index: 0, pending: None, steps: 0, crossed: 0, arrays_read: [0; MAX_REMAINING], n_read: 1,
        };
        w.arrays_read[0] = self.first.0;
        if w.dynamic.is_some() { w.ts_index = tick_spacing_index(self.tick, self.tick_spacing); }
        Some(w)
    }

    /// the next initialized tick of the current array from the walker's tick (`next_initialized_tick`)
    fn next_in_array(&self, w: &Walker) -> Option<Option<Tick>> {
        let ts = self.tick_spacing;
        if array_start(w.tick, ts) != w.cur_start { return Some(None); }
        let a = self.array(w.cur)?;
        let offset = (w.tick - w.cur_start) / ts as i32;
        if self.zfo {
            for i in (0..=offset).rev() {
                let t = Tick::read(a, i as usize)?;
                if t.is_initialized() { return Some(Some(t)); }
            }
        } else {
            for i in offset + 1..TICK_ARRAY_SIZE {
                let t = Tick::read(a, i as usize)?;
                if t.is_initialized() { return Some(Some(t)); }
            }
        }
        Some(None)
    }

    /// `first_initialized_tick` of the current array (the highest one for zfo); None: none (the program errors)
    fn first_in_array(&self, w: &Walker) -> Option<Tick> {
        let a = self.array(w.cur)?;
        for k in 0..TICK_ARRAY_SIZE as usize {
            let t = Tick::read(a, if self.zfo { TICK_ARRAY_SIZE as usize - 1 - k } else { k })?;
            if t.is_initialized() { return Some(t); }
        }
        None
    }

    /// One inner step of the program's loop (`swap_internal`): to the next boundary (the initialized tick being
    /// approached, a tick-spacing boundary under the dynamic fee) or until the amount is used up. A new outer iteration
    /// (the next initialized tick, moving to the next tick array) starts when none is in progress. `f` sees the step
    fn inner_step(&self, w: &mut Walker, base_input: bool, f: &mut dyn FnMut(&ClmmStep)) -> R<()> {
        let zfo = self.zfo;
        let ts = self.tick_spacing;
        let limit = if zfo { MIN_SQRT_PRICE_X64 + 1 } else { MAX_SQRT_PRICE_X64 - 1 };
        let mut p = match w.pending {
            Some(p) => p,
            None => {
                // the next initialized tick: in the current array, else the first array's first one, else the next array's
                let next = match self.next_in_array(w).ok_or(TOO_LARGE)? {
                    Some(t) => t,
                    None if !w.first_contains => { w.first_contains = true; self.first_in_array(w).ok_or(TOO_LARGE)? }
                    None => {
                        let nx = match self.next_array(w.cur_valid, zfo) { Ok(Some(s)) => s, _ => return Err(TOO_LARGE) };
                        while w.cur_start != nx {
                            w.cur += 1;
                            let a = self.array(w.cur).ok_or(TOO_LARGE)?;
                            w.cur_start = i32_at(a, off::A_START).ok_or(TOO_LARGE)?;
                            w.cur_count = u8_at(a, off::A_INIT_COUNT).ok_or(TOO_LARGE)?;
                        }
                        if let Some(s) = w.arrays_read.get_mut(w.n_read as usize) { *s = nx; w.n_read += 1; }
                        w.cur_valid = nx;
                        self.first_in_array(w).ok_or(TOO_LARGE)?
                    }
                };
                if !next.is_initialized() { return Err(TOO_LARGE); }
                // get_target_price_based_on_next_tick
                let tick_next = next.tick.clamp(MIN_TICK, MAX_TICK);
                let price_next = sqrt_price_at_tick(tick_next).ok_or(TOO_LARGE)?;
                let target = if (zfo && price_next < limit) || (!zfo && price_next > limit) { limit } else { price_next };
                if zfo {
                    if w.tick < tick_next || w.sqrt_price < price_next || w.sqrt_price < target { return Err(TOO_LARGE); }
                } else if tick_next <= w.tick || price_next < w.sqrt_price || target < w.sqrt_price { return Err(TOO_LARGE); }
                Pending { next, tick_next, price_next, target, liquidity_next: w.liquidity }
            }
        };
        if w.steps >= self.budget { return Err(QuoteErr::Budget); }
        w.steps += 1;
        if let Some(d) = w.dynamic.as_mut() { d.update_va(w.ts_index).ok_or(TOO_LARGE)?; }
        let fee_rate = match &w.dynamic {
            Some(d) => self.trade_fee_rate.checked_add(d.rate(ts).ok_or(TOO_LARGE)?).ok_or(TOO_LARGE)?.min(MAX_FEE_RATE_NUMERATOR),
            None => self.trade_fee_rate,
        };
        // get_spacing_bounded_price
        let (skipped, bounded, bounded_tick) = match &w.dynamic {
            Some(d) if !(w.liquidity == 0 || d.va == d.max_va) => {
                let bt = if zfo { w.ts_index.saturating_mul(ts as i32) } else { w.ts_index.saturating_add(1).saturating_mul(ts as i32) };
                let btc = bt.clamp(MIN_TICK, MAX_TICK);
                let bp = sqrt_price_at_tick(btc).ok_or(TOO_LARGE)?;
                if (zfo && p.target > bp) || (!zfo && p.target < bp) { (false, p.target, None) } else { (false, bp, Some(btc)) }
            }
            _ => (true, p.target, None),
        };
        let from = w.sqrt_price;
        let st = if w.sqrt_price != bounded {
            let s = compute_swap(w.sqrt_price, bounded, w.liquidity, w.remaining, fee_rate, base_input, zfo, self.fee_on_input).ok_or(TOO_LARGE)?;
            self.apply(w, s.amount_in, s.amount_out, s.fee, base_input).ok_or(TOO_LARGE)?;
            s
        } else {
            StepAmounts { next: bounded, ..Default::default() }
        };
        let unfilled_before = p.next.unfilled().ok_or(TOO_LARGE)?;
        let mut step = ClmmStep { sqrt_price_from: from, sqrt_price_to: st.next, liquidity: w.liquidity, fee_rate, amount_in: st.amount_in,
            amount_out: st.amount_out, fee: st.fee, tick: None, crossed: false, limit: None, array: w.cur_start };
        if p.price_next == st.next {
            // on the initialized tick: its limit orders first (at the tick's price), the crossing once none are left
            let lo = match_limit_orders(&mut p.next, w.remaining, zfo, base_input, fee_rate, self.fee_on_input, p.price_next).ok_or(TOO_LARGE)?;
            if lo.amount_in != 0 || lo.amount_out != 0 || lo.fee != 0 {
                self.apply(w, lo.amount_in, lo.amount_out, lo.fee, base_input).ok_or(TOO_LARGE)?;
                step.limit = Some((lo, p.next));
            }
            if !p.next.is_initialized() {
                w.cur_count = w.cur_count.checked_sub(1).ok_or(TOO_LARGE)?;
                // the array's bitmap bit flips when its last initialized tick goes: beyond the default bitmap that needs
                // the extension
                if w.cur_count == 0 && self.overflows_default(w.cur_start) && self.ext.is_none() { return Err(TOO_LARGE); }
            }
            if p.next.has_liquidity() && !p.next.has_limit_orders() {
                let net = if zfo { p.next.liquidity_net.checked_neg().ok_or(TOO_LARGE)? } else { p.next.liquidity_net };
                p.liquidity_next = add_delta(w.liquidity, net).ok_or(TOO_LARGE)?;
                step.crossed = true;
                w.crossed = w.crossed.saturating_add(1);
            }
            // update_tick_state: the stored tick must lie in the current array
            if array_start(p.next.tick, ts) != w.cur_start { return Err(TOO_LARGE); }
            w.tick = if (zfo && !p.next.has_limit_orders()) || (!zfo && p.next.has_limit_orders()) { p.tick_next - 1 } else { p.tick_next };
            step.tick = Some(p.tick_next);
        } else if w.sqrt_price != st.next {
            w.tick = match bounded_tick {
                Some(t) if st.next == bounded => t,
                _ => tick_at_sqrt_price(st.next).ok_or(TOO_LARGE)?,
            };
        }
        w.sqrt_price = st.next;
        // update_dynamic_fee_index
        if w.dynamic.is_some() {
            if skipped {
                let ti = if w.sqrt_price == p.price_next { p.tick_next } else { w.tick };
                let mut idx = tick_spacing_index(ti, ts);
                if !zfo && ti % ts as i32 == 0 { idx -= 1; }
                w.ts_index = idx;
                if let Some(d) = w.dynamic.as_mut() { if d.va != d.max_va { d.update_va(w.ts_index).ok_or(TOO_LARGE)?; } }
            }
            w.ts_index += if zfo { -1 } else { 1 };
        }
        f(&step);
        if w.remaining == 0 || w.sqrt_price == p.target {
            let after = p.next.unfilled().ok_or(TOO_LARGE)?;
            if w.remaining != 0 && after != unfilled_before && after != 0 { return Err(TOO_LARGE); }
            w.liquidity = p.liquidity_next;
            w.pending = None;
        } else {
            w.pending = Some(p);
        }
        Ok(())
    }

    /// `apply_swap_amounts` + `spilt_fees`
    fn apply(&self, w: &mut Walker, amount_in: u64, amount_out: u64, fee: u64, base_input: bool) -> Option<()> {
        let consumed = if self.fee_on_input { amount_in.checked_add(fee)? } else { amount_in };
        if base_input {
            w.remaining = w.remaining.checked_sub(consumed)?;
            w.calculated = w.calculated.checked_add(amount_out)?;
        } else {
            w.remaining = w.remaining.checked_sub(amount_out)?;
            w.calculated = w.calculated.checked_add(consumed)?;
        }
        let den = FEE_RATE_DENOMINATOR as u128;
        let pd = if self.protocol_fee_rate > 0 { (fee as u128 * self.protocol_fee_rate as u128 / den) as u64 } else { 0 };
        let fd = if self.fund_fee_rate > 0 { (fee as u128 * self.fund_fee_rate as u128 / den) as u64 } else { 0 };
        if pd > 0 { w.protocol_fee = w.protocol_fee.checked_add(pd)?; }
        if fd > 0 { w.fund_fee = w.fund_fee.checked_add(fd)?; }
        let rest = fee.checked_sub(pd)?.checked_sub(fd)?;
        if w.liquidity > 0 {
            let g = mul_div_u128(rest as u128, Q64, w.liquidity, false)?;
            w.fee_growth = w.fee_growth.wrapping_add(g);
            w.lp_fee = w.lp_fee.checked_add(rest)?;
        } else {
            w.protocol_fee = w.protocol_fee.checked_add(rest)?;
        }
        Some(())
    }

    fn post(&self, w: &Walker) -> PostSwap {
        PostSwap {
            sqrt_price: w.sqrt_price, tick: w.tick, liquidity: w.liquidity,
            fee_growth_global: if w.lp_fee > 0 { w.fee_growth } else { self.fee_growth_global },
            protocol_fees: self.fees_owed.0.saturating_add(w.protocol_fee), fund_fees: self.fees_owed.1.saturating_add(w.fund_fee),
            dynamic: w.dynamic,
        }
    }

    /// The exact swap of `amount` (`exact_out`: the output wanted) with every step seen by `f`: the quote (exact in: the
    /// output and the input `amount`; exact out: `amount` and the input debited), the walk and the post-swap pool.
    pub fn fills(&self, amount: u64, exact_out: bool, f: &mut dyn FnMut(&ClmmStep)) -> R<ClmmWalk> {
        if amount == 0 { return Err(QuoteErr::ZeroOut); }
        let base_input = !exact_out;
        let limit = if self.zfo { MIN_SQRT_PRICE_X64 + 1 } else { MAX_SQRT_PRICE_X64 - 1 };
        let mut w = self.walker(amount).ok_or(TOO_LARGE)?;
        while w.remaining != 0 && w.sqrt_price != limit { self.inner_step(&mut w, base_input, f)?; }
        // update_after_swap → update_fee: the pool's owed fees grow by checked additions
        if w.protocol_fee > 0 { self.fees_owed.0.checked_add(w.protocol_fee).ok_or(TOO_LARGE)?; }
        if w.fund_fee > 0 { self.fees_owed.1.checked_add(w.fund_fee).ok_or(TOO_LARGE)?; }
        // swap_v2 without a price limit: the specified amount is met in full, and both sides are nonzero
        if w.remaining != 0 { return Err(TOO_LARGE); }
        let (spent, out) = if base_input { (amount, w.calculated) } else { (w.calculated, amount) };
        if spent == 0 || out == 0 { return Err(QuoteErr::ZeroOut); }
        if out > self.vault_out { return Err(TOO_LARGE); }
        Ok(ClmmWalk { quote: Quote { out, spent }, steps: w.steps, crossed: w.crossed, arrays: w.arrays_read, n_arrays: w.n_read, post: self.post(&w) })
    }

    /// The exact quote (swap_v2, exact in): equal to the program's output and debit to the unit, or the error
    pub fn quote(&self, x: u64) -> R<Quote> { self.fills(x, false, &mut |_| {}).map(|w| w.quote) }

    /// The exact quote of swap_v2 exact out: `out` and the input it debits
    pub fn quote_exact_out(&self, out: u64) -> R<Quote> { self.fills(out, true, &mut |_| {}).map(|w| w.quote) }

    /// Swap steps the exact swap of `x` takes (no budget): what the engine puts in the descriptor's `max_bins`
    pub fn steps_for(&self, x: u64) -> Option<u16> { self.with_budget(NO_BUDGET).fills(x, false, &mut |_| {}).ok().map(|w| w.steps) }

    /// The largest input that quotes Ok (None: every u64 does): the swap fills a larger input whenever it fills a smaller
    /// one up to its capacity, so a bisection over the exact swap finds it (sizes too small to pay out quote ZeroOut)
    pub fn cap_in(&self) -> Option<u64> {
        if self.quote(u64::MAX).is_ok() { return None; }
        let (mut lo, mut hi) = (0u64, u64::MAX);
        while hi - lo > 1 {
            let mid = lo + (hi - lo) / 2;
            match self.quote(mid) { Ok(_) | Err(QuoteErr::ZeroOut) => lo = mid, Err(_) => hi = mid }
        }
        Some(lo)
    }

    /// The locator's stream of this leg (DESIGN.md §3.4): the exact swap of an unbounded input, one step at a time
    pub fn stream(&self) -> Steps<'_, 'a> { Steps { leg: self, w: self.walker(u64::MAX), used: 0, out: 0, done: false } }

    /// The real-valued curve of a constant-liquidity range from sqrt price `p`: virtual reserves X = L·2^64/p (token 0)
    /// and Y = L·p/2^64 (token 1); with the fee on the input a = (1−f)·R_out, b = R_in, c = 1−f, on the output c = 1
    fn mobius(&self, p: u128, liq: u128, fee_rate: u32) -> (Fx, Fx, Fx) {
        let l = Fx::from_u128(liq);
        let pf = Fx::from_u128(p);
        let x = l.shl(64).div(pf);
        let y = l.mul(pf).shl(-64);
        let (r_in, r_out) = if self.zfo { (x, y) } else { (y, x) };
        let keep = fee_keep(fee_rate);
        (keep.mul(r_out), r_in, if self.fee_on_input { keep } else { Fx::ONE })
    }

    /// An upper bound on the output per input of every step after one that ended at sqrt price `p`: the marginal price
    /// there (the walk only worsens it) net of the lowest fee the walk can still charge (the trade fee: the dynamic part
    /// is never negative)
    pub fn bound_after(&self, p: u128) -> Fx {
        let pf = Fx::from_u128(p).shl(-64);
        let price = if self.zfo { pf.mul(pf) } else { Fx::ONE.div(pf.mul(pf)) };
        price.mul(fee_keep(self.trade_fee_rate))
    }
}

fn fee_keep(fee_rate: u32) -> Fx {
    Fx::from_u64((FEE_RATE_DENOMINATOR - fee_rate.min(FEE_RATE_DENOMINATOR)) as u64).div(Fx::from_u64(FEE_RATE_DENOMINATOR as u64))
}

/// `add_delta`: liquidity ± |delta| (a subtraction must leave less than before)
fn add_delta(x: u128, y: i128) -> Option<u128> {
    if y < 0 { let z = x.checked_sub(y.unsigned_abs())?; if x > z { Some(z) } else { None } } else { x.checked_add(y as u128) }
}

/// One model piece of a CLMM leg for the locator: the exact input and output of one full swap step and its real-valued
/// curve: `Some((a, b, c))` the Möbius `a·u/(b + c·u)` of a constant-liquidity range, `None` a line (a limit-order fill
/// at the tick's fixed price). `bound`: an upper bound on the output per input of every later piece
#[derive(Clone, Copy, Debug)]
pub struct StepPiece { pub used: u64, pub out: u64, pub mobius: Option<(Fx, Fx, Fx)>, pub bound: Fx }

/// The exact swap of an unbounded input (u64::MAX), step by step: the locator's pieces (DESIGN.md §3.4)
#[derive(Clone, Copy, Debug)]
pub struct Steps<'l, 'a> { leg: &'l RayClmmLeg<'a>, w: Option<Walker>, pub used: u64, pub out: u64, done: bool }

impl Steps<'_, '_> {
    /// The pieces of the next step (a range, then a limit-order fill when the step ends on a tick holding orders), each
    /// seen by `push`. Err: the walk ends here (the venue's capacity or the leg's budget)
    pub fn next(&mut self, push: &mut dyn FnMut(StepPiece)) -> Result<(), End> {
        if self.done { return Err(End::Cap); }
        let Some(mut w) = self.w else { self.done = true; return Err(End::Cap) };
        let leg = self.leg;
        let mut pieces: [Option<StepPiece>; 2] = [None, None];
        let mut cb = |s: &ClmmStep| {
            let used = if leg.fee_on_input { s.amount_in.saturating_add(s.fee) } else { s.amount_in };
            let bound = leg.bound_after(s.sqrt_price_to);
            if used > 0 || s.amount_out > 0 {
                pieces[0] = Some(StepPiece { used, out: s.amount_out, mobius: Some(leg.mobius(s.sqrt_price_from, s.liquidity, s.fee_rate)), bound });
            }
            if let Some((lo, _)) = s.limit {
                let used = if leg.fee_on_input { lo.amount_in.saturating_add(lo.fee) } else { lo.amount_in };
                pieces[1] = Some(StepPiece { used, out: lo.amount_out, mobius: None, bound });
            }
        };
        let limit = if leg.zfo { MIN_SQRT_PRICE_X64 + 1 } else { MAX_SQRT_PRICE_X64 - 1 };
        let r = if w.sqrt_price == limit { Err(TOO_LARGE) } else { leg.inner_step(&mut w, true, &mut cb) };
        if let Err(e) = r {
            self.done = true;
            return Err(if e == QuoteErr::Budget { End::Budget } else { End::Cap });
        }
        // a step that ended inside its range used the input up (with u64::MAX of input: the end of u64)
        if w.remaining == 0 { self.done = true; return Err(End::Cap); }
        for p in pieces.iter().flatten() {
            self.used = self.used.checked_add(p.used).ok_or(End::Cap)?;
            self.out = self.out.checked_add(p.out).ok_or(End::Cap)?;
            push(*p);
        }
        self.w = Some(w);
        Ok(())
    }
}

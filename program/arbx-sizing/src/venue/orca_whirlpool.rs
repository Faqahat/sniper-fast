//! Orca Whirlpool (whirLbMi…) `swap_v2`, exact in and exact out (DESIGN.md §2.9; PLAN-ADDENDUM WP-21). Ported from
//! orca-so/whirlpools 0e72771 (whirlpool program 0.9.0, the version deployed at programdata slot 440,170,207,
//! 2026-08-19) and proven against that binary in program/venue-harness (`tests/clmm_exactness.rs`,
//! `tests/clmm_adversarial.rs`).
//!
//! The program is built with `overflow-checks = false`: its plain `+ - *` wrap, and only its `checked_*` calls and its
//! index bounds fail. The port keeps that: wrapping operations where the program has plain ones. In particular its own
//! U256 division (`U256Muldiv::div`, Knuth D with a carry word) is ported as deployed, including the out-of-bounds read
//! of an add-back on the top word that the program fixed after this deploy (4aac511, 2026-10-06): the deployed binary
//! fails there, and so does the port.
//!
//! The swap is `swap_manager::swap` step for step: Q64.64 sqrt prices; the sparse tick-array sequence the program
//! builds from the 3 static and the supplemental tick arrays (`SparseSwapTickSequenceBuilder`: the current array and the
//! next two in the swap direction, an uninitialized one as zeroed); fixed (9,988 B) and dynamic tick arrays; the
//! adaptive fee (`FeeRateManager`: the reference update, the volatility accumulator per tick group, sub-steps at every
//! tick-group boundary inside the core range); exact in and exact out (`compute_swap`).
use crate::error::{Abort, Quote, QuoteErr, WhirlWhy};
use crate::fx::Fx;
use crate::math::{i128_at, i32_at, key_at, u128_at, u16_at, u32_at, u64_at, u8_at};
use crate::u256::U256;
use crate::Clock;

pub const POOL_LEN: usize = 653;
pub const FIXED_ARRAY_LEN: usize = 9_988;
/// a dynamic tick array: 60 bytes of header, 1 byte per uninitialized tick and 113 per initialized one
pub const DYNAMIC_MIN_LEN: usize = 148;
pub const DYNAMIC_MAX_LEN: usize = 10_004;
pub const ORACLE_LEN: usize = 254;
pub const TICK_ARRAY_SIZE: i32 = 88;
/// supplemental tick arrays a leg may pass (the descriptor's count)
pub const MAX_SUPPLEMENTAL: usize = 3;
/// no walk budget (off-chain use: the 3 tick arrays bound the walk)
pub const NO_BUDGET: u16 = u16::MAX;
pub const MIN_TICK: i32 = -443_636;
pub const MAX_TICK: i32 = 443_636;
pub const MIN_SQRT_PRICE_X64: u128 = 4_295_048_016;
pub const MAX_SQRT_PRICE_X64: u128 = 79_226_673_515_401_279_992_447_579_055;
pub const FEE_RATE_MUL_VALUE: u128 = 1_000_000;
pub const PROTOCOL_FEE_RATE_MUL_VALUE: u128 = 10_000;
pub const FEE_RATE_HARD_LIMIT: u32 = 100_000;
const VA_SCALE: u64 = 10_000;
const REDUCTION_DEN: u64 = 10_000;
const AF_CONTROL_DEN: u128 = 100_000;
const MAX_REFERENCE_AGE: u64 = 3_600;
const Q64_MASK: u128 = 0xFFFF_FFFF_FFFF_FFFF;

pub mod off {
    // Whirlpool (Borsh)
    pub const TICK_SPACING: usize = 41;
    pub const FEE_TIER_SEED: usize = 43;
    pub const FEE_RATE: usize = 45;
    pub const PROTOCOL_FEE_RATE: usize = 47;
    pub const LIQUIDITY: usize = 49;
    pub const SQRT_PRICE: usize = 65;
    pub const TICK_CURRENT: usize = 81;
    pub const PROTOCOL_FEE_OWED_A: usize = 85;
    pub const PROTOCOL_FEE_OWED_B: usize = 93;
    pub const MINT_A: usize = 101;
    pub const VAULT_A: usize = 133;
    pub const FEE_GROWTH_A: usize = 165;
    pub const MINT_B: usize = 181;
    pub const VAULT_B: usize = 213;
    pub const FEE_GROWTH_B: usize = 245;
    pub const REWARD_LAST_UPDATED: usize = 261;
    // tick arrays: the start index at 8 in both; fixed: ticks from 12 (113 B each), the whirlpool at 9,956; dynamic:
    // the whirlpool at 12, the tick bitmap (u128) at 44, the ticks from 60 (Borsh enum: 0, or 1 + 112 B)
    pub const A_START: usize = 8;
    pub const F_TICKS: usize = 12;
    pub const F_WHIRLPOOL: usize = 9_956;
    pub const D_WHIRLPOOL: usize = 12;
    pub const D_BITMAP: usize = 44;
    pub const D_TICKS: usize = 60;
    pub const TICK_LEN: usize = 113;
    // Oracle: whirlpool 8, trade_enable_timestamp 40, AdaptiveFeeConstants 48, AdaptiveFeeVariables 82
    pub const O_WHIRLPOOL: usize = 8;
    pub const O_TRADE_ENABLE: usize = 40;
    pub const O_CONSTANTS: usize = 48;
    pub const O_VARIABLES: usize = 82;
}

type R<T> = Result<T, QuoteErr>;
const TOO_LARGE: QuoteErr = QuoteErr::TooLarge;

// ---------------------------------------------------------------------------------------------------------------
// The program's U256Muldiv, as deployed (little-endian u64 words)
// ---------------------------------------------------------------------------------------------------------------

type W4 = [u64; 4];

fn num_words(x: &W4) -> usize { x.iter().rposition(|&w| w != 0).map_or(0, |i| i + 1) }
fn lo(x: u128) -> u64 { x as u64 }
fn hi(x: u128) -> u64 { (x >> 64) as u64 }
fn hi_lo(h: u64, l: u64) -> u128 { ((h as u128) << 64) | l as u128 }

fn shift_left(x: &W4, s: u32) -> W4 {
    if s == 0 { return *x; }
    let mut r = *x;
    for i in (1..4).rev() { r[i] = (r[i] << s) | (r[i - 1] >> (64 - s)); }
    r[0] <<= s;
    r
}

fn shift_right(x: &W4, s: u32) -> W4 {
    if s == 0 { return *x; }
    let mut r = *x;
    for i in 0..3 { r[i] = (r[i] >> s) | (r[i + 1] << (64 - s)); }
    r[3] >>= s;
    r
}

/// `div_loop` as deployed. None: the program reads past its words (the add-back of the top digit) and fails
fn div_loop(index: usize, n: usize, dividend: &mut W4, carry: &mut u64, divisor: &W4, quotient: &mut W4) -> Option<()> {
    let use_carry = index + n == 4;
    let div_hi = if use_carry { *carry } else { *dividend.get(index + n)? };
    let d0 = hi_lo(div_hi, *dividend.get(index + n - 1)?);
    let d1 = *divisor.get(n - 1)? as u128;
    let mut qhat = d0 / d1;
    let mut rhat = d0.wrapping_sub(d1.wrapping_mul(qhat));
    let d0_2 = *dividend.get(index + n - 2)?;
    let d1_2 = *divisor.get(n - 2)? as u128;
    let mut cmp1 = hi_lo(lo(rhat), d0_2);
    let mut cmp2 = qhat.wrapping_mul(d1_2);
    while hi(qhat) != 0 || cmp2 > cmp1 {
        qhat = qhat.wrapping_sub(1);
        rhat = rhat.wrapping_add(d1);
        if hi(rhat) != 0 { break; }
        cmp1 = hi_lo(lo(rhat), lo(cmp1));
        cmp2 = cmp2.wrapping_sub(d1_2);
    }
    let mut k: u128 = 0;
    let mut t: u128;
    for i in 0..n {
        let p = qhat.wrapping_mul(*divisor.get(i)? as u128);
        t = (*dividend.get(index + i)? as u128).wrapping_sub(k).wrapping_sub(p & Q64_MASK);
        *dividend.get_mut(index + i)? = lo(t);
        k = ((p >> 64) as u64).wrapping_sub((t >> 64) as u64) as u128;
    }
    let d_head = if use_carry { *carry as u128 } else { *dividend.get(index + n)? as u128 };
    t = d_head.wrapping_sub(k);
    if use_carry { *carry = lo(t); } else { *dividend.get_mut(index + n)? = lo(t); }
    if k > d_head {
        qhat = qhat.wrapping_sub(1);
        k = 0;
        for i in 0..n {
            t = (*dividend.get(index + i)? as u128).wrapping_add(*divisor.get(i)? as u128).wrapping_add(k);
            *dividend.get_mut(index + i)? = lo(t);
            k = t >> 64;
        }
        // deployed: `dividend.get_word_u128(index + n)` is read before the branch: out of bounds at the top word
        let new_carry = lo((*dividend.get(index + n)? as u128).wrapping_add(k));
        if use_carry { *carry = new_carry; } else { *dividend.get_mut(index + n)? = new_carry; }
    }
    *quotient.get_mut(index)? = lo(qhat);
    Some(())
}

/// `U256Muldiv::div` as deployed: (quotient, remainder). None: the program panics (a zero divisor, the add-back read)
fn muldiv_div(x: &W4, divisor: &W4) -> Option<(W4, W4)> {
    let mut dividend = *x;
    let mut quotient: W4 = [0; 4];
    let nd = num_words(&dividend);
    let nv = num_words(divisor);
    if nv == 0 { return None; }
    if nd == 0 { return Some(([0; 4], [0; 4])); }
    if nd < nv { return Some(([0; 4], dividend)); }
    if nd < 3 {
        let a = hi_lo(dividend[1], dividend[0]);
        let b = hi_lo(divisor[1], divisor[0]);
        let (q, r) = (a / b, a % b);
        return Some(([lo(q), hi(q), 0, 0], [lo(r), hi(r), 0, 0]));
    }
    if nv == 1 {
        let mut k: u128 = 0;
        let d2 = divisor[0] as u128;
        for j in (0..nd).rev() {
            let d1 = hi_lo(lo(k), dividend[j]);
            let q = d1 / d2;
            k = d1.wrapping_sub(d2.wrapping_mul(q));
            quotient[j] = lo(q);
        }
        return Some((quotient, [lo(k), hi(k), 0, 0]));
    }
    let s = divisor[nv - 1].leading_zeros();
    let b = dividend[nd - 1].leading_zeros();
    let mut carry: u64 = 0;
    if nd == 4 && b < s { carry = dividend[nd - 1] >> (64 - s); }
    dividend = shift_left(&dividend, s);
    let divisor = shift_left(divisor, s);
    for j in (0..nd - nv + 1).rev() { div_loop(j, nv, &mut dividend, &mut carry, &divisor, &mut quotient)?; }
    Some((quotient, shift_right(&dividend, s)))
}

fn w4(x: U256) -> W4 { x.0 }
fn w4_u128(x: &W4) -> Option<u128> { if num_words(x) > 2 { None } else { Some(hi_lo(x[1], x[0])) } }
/// `shift_word_left` (a 64-bit shift that drops the top word) and its checked form
fn shift_word_left(x: &W4) -> W4 { [0, x[0], x[1], x[2]] }
fn checked_shift_word_left(x: &W4) -> Option<W4> { if x[3] > 0 { None } else { Some(shift_word_left(x)) } }
/// U256Muldiv::add with its carries wrapping
fn add_one(x: &W4) -> W4 {
    let mut r = [0u64; 4];
    let mut carry: u128 = 1;
    for i in 0..4 { let t = x[i] as u128 + carry; r[i] = lo(t); carry = t >> 64; }
    r
}

// ---------------------------------------------------------------------------------------------------------------
// tick math (Orca's own factors)
// ---------------------------------------------------------------------------------------------------------------

/// `sqrt_price_from_tick_index` (Q64.64). None where the program's u128 conversion fails (beyond the tick range)
pub fn sqrt_price_at_tick(tick: i32) -> Option<u128> {
    if tick >= 0 {
        const F: [u128; 18] = [
            79236085330515764027303304731, 79244008939048815603706035061, 79259858533276714757314932305,
            79291567232598584799939703904, 79355022692464371645785046466, 79482085999252804386437311141,
            79736823300114093921829183326, 80248749790819932309965073892, 81282483887344747381513967011,
            83390072131320151908154831281, 87770609709833776024991924138, 97234110755111693312479820773,
            119332217159966728226237229890, 179736315981702064433883588727, 407748233172238350107850275304,
            2098478828474011932436660412517, 55581415166113811149459800483533, 38992368544603139932233054999993551,
        ];
        let mut ratio: u128 = if tick & 1 != 0 { 79232123823359799118286999567 } else { 79228162514264337593543950336 };
        for (i, f) in F.iter().enumerate() {
            if tick & (2 << i) != 0 {
                // mul_shift_96: (ratio · f) >> 96, which must fit u128
                ratio = U256::mul128(ratio, *f).shr(96).to_u128()?;
            }
        }
        Some(ratio >> 32)
    } else {
        const F: [u128; 18] = [
            18444899583751176498, 18443055278223354162, 18439367220385604838, 18431993317065449817, 18417254355718160513,
            18387811781193591352, 18329067761203520168, 18212142134806087854, 17980523815641551639, 17526086738831147013,
            16651378430235024244, 15030750278693429944, 12247334978882834399, 8131365268884726200, 3584323654723342297,
            696457651847595233, 26294789957452057, 37481735321082,
        ];
        let a = tick.wrapping_abs();
        let mut ratio: u128 = if a & 1 != 0 { 18445821805675392311 } else { 18446744073709551616 };
        for (i, f) in F.iter().enumerate() {
            if a & (2 << i) != 0 { ratio = ratio.wrapping_mul(*f) >> 64; }
        }
        Some(ratio)
    }
}

/// `tick_index_from_sqrt_price` (BIT_PRECISION 14). None: the program panics (an estimate past i32)
pub fn tick_at_sqrt_price(p: u128) -> Option<i32> {
    if p == 0 { return None; }
    let msb = 128 - p.leading_zeros() - 1;
    let log2p_integer_x32 = (msb as i128 - 64) << 32;
    let mut bit: i128 = 0x8000_0000_0000_0000;
    let mut precision = 0;
    let mut log2p_fraction_x64: i128 = 0;
    let mut r = if msb >= 64 { p >> (msb - 63) } else { p << (63 - msb) };
    while bit > 0 && precision < 14 {
        r = r.wrapping_mul(r);
        let more = r >> 127;
        r >>= 63 + more;
        log2p_fraction_x64 += bit * more as i128;
        bit >>= 1;
        precision += 1;
    }
    let logbp_x64 = (log2p_integer_x32 + (log2p_fraction_x64 >> 32)).wrapping_mul(59_543_866_431_248i128);
    let tick_low = i32::try_from((logbp_x64 - 184_467_440_737_095_516i128) >> 64).ok()?;
    let tick_high = i32::try_from((logbp_x64 + 15_793_534_762_490_258_745i128) >> 64).ok()?;
    if tick_low == tick_high { return Some(tick_low); }
    Some(if sqrt_price_at_tick(tick_high)? <= p { tick_high } else { tick_low })
}

fn floor_div(a: i32, b: i32) -> i32 { a.div_euclid(b) }

/// `Tick::check_is_valid_start_tick`
pub fn valid_start(start: i32, ts: u16) -> bool {
    let per = TICK_ARRAY_SIZE * ts as i32;
    if !(MIN_TICK..=MAX_TICK).contains(&start) {
        if start > MIN_TICK { return false; }
        return start == MIN_TICK - (MIN_TICK % per + per);
    }
    start % per == 0
}

/// The tick array start index of a tick (floor)
pub fn array_start(tick: i32, ts: u16) -> i32 { let per = TICK_ARRAY_SIZE * ts as i32; floor_div(tick, per) * per }

/// `get_start_tick_indexes`: the start indexes of the (at most 3) tick arrays a swap from `tick` uses, in order
pub fn needed_starts(tick: i32, ts: u16, a_to_b: bool) -> ([i32; 3], usize) {
    let tsi = ts as i32;
    let per = TICK_ARRAY_SIZE * tsi;
    let base = floor_div(tick, per) * per;
    let offs: [i32; 3] = if a_to_b { [0, -1, -2] } else if tick.wrapping_add(tsi) >= base + per { [1, 2, 3] } else { [0, 1, 2] };
    let mut out = [0i32; 3];
    let mut n = 0;
    for o in offs {
        let st = base + o * per;
        if valid_start(st, ts) { if let Some(s) = out.get_mut(n) { *s = st; n += 1; } }
    }
    (out, n)
}

// ---------------------------------------------------------------------------------------------------------------
// token maths (token_math.rs, swap_math.rs)
// ---------------------------------------------------------------------------------------------------------------

/// `AmountDeltaU64`: a delta within u64, or past it (the step's target is then not reachable)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Delta { Valid(u64), Exceeds }

/// `try_get_amount_delta_a`. None: the program errors (MultiplicationOverflow, its division failing)
fn try_delta_a(p0: u128, p1: u128, liq: u128, up: bool) -> Option<Delta> {
    let (pl, pu) = if p0 > p1 { (p1, p0) } else { (p0, p1) };
    let num = checked_shift_word_left(&w4(U256::mul128(liq, pu - pl)))?;
    let den = w4(U256::mul128(pu, pl));
    let (q, r) = muldiv_div(&num, &den)?;
    let res = if up && num_words(&r) != 0 { w4_u128(&add_one(&q)) } else { w4_u128(&q) };
    Some(match res { Some(v) if v <= u64::MAX as u128 => Delta::Valid(v as u64), _ => Delta::Exceeds })
}

/// `try_get_amount_delta_b`
fn try_delta_b(p0: u128, p1: u128, liq: u128, up: bool) -> Delta {
    let (pl, pu) = if p0 > p1 { (p1, p0) } else { (p0, p1) };
    let (n0, n1) = (liq, pu - pl);
    if n0 == 0 || n1 == 0 { return Delta::Valid(0); }
    let Some(p) = n0.checked_mul(n1) else { return Delta::Exceeds };
    let result = (p >> 64) as u64;
    let round = up && (p & Q64_MASK > 0);
    if round && result == u64::MAX { return Delta::Exceeds; }
    Delta::Valid(if round { result + 1 } else { result })
}

fn delta_a(p0: u128, p1: u128, liq: u128, up: bool) -> Option<u64> { match try_delta_a(p0, p1, liq, up)? { Delta::Valid(v) => Some(v), Delta::Exceeds => None } }
fn delta_b(p0: u128, p1: u128, liq: u128, up: bool) -> Option<u64> { match try_delta_b(p0, p1, liq, up) { Delta::Valid(v) => Some(v), Delta::Exceeds => None } }

/// `get_next_sqrt_price_from_a_round_up`
fn next_from_a(p: u128, liq: u128, amount: u64, input: bool) -> Option<u128> {
    if amount == 0 { return Some(p); }
    let product = w4(U256::mul128(p, amount as u128));
    let num = checked_shift_word_left(&w4(U256::mul128(liq, p)))?;
    let lsl = shift_word_left(&[lo(liq), hi(liq), 0, 0]);
    let lsl_u = U256(lsl);
    let prod_u = U256(product);
    if !input && lsl_u <= prod_u { return None; }
    let den = if input { lsl_u.checked_add(prod_u)? } else { lsl_u.checked_sub(prod_u)? };
    let (q, r) = muldiv_div(&num, &w4(den))?;
    let price = if num_words(&r) != 0 { w4_u128(&add_one(&q))? } else { w4_u128(&q)? };
    if !(MIN_SQRT_PRICE_X64..=MAX_SQRT_PRICE_X64).contains(&price) { return None; }
    Some(price)
}

/// `get_next_sqrt_price_from_b_round_down`
fn next_from_b(p: u128, liq: u128, amount: u64, input: bool) -> Option<u128> {
    if liq == 0 { return None; }
    let ax = (amount as u128) << 64;
    let delta = ax / liq + (!input && ax % liq > 0) as u128;
    if input { p.checked_add(delta) } else { p.checked_sub(delta) }
}

fn next_sqrt_price(p: u128, liq: u128, amount: u64, input: bool, a_to_b: bool) -> Option<u128> {
    if input == a_to_b { next_from_a(p, liq, amount, input) } else { next_from_b(p, liq, amount, input) }
}

/// One `compute_swap` step
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct StepAmounts { pub amount_in: u64, pub amount_out: u64, pub next: u128, pub fee: u64 }

/// `swap_math::compute_swap`. None: the program errors
fn compute_swap(remaining: u64, fee_rate: u32, liq: u128, cur: u128, target: u128, input: bool, a_to_b: bool) -> Option<StepAmounts> {
    let fixed_is_a = a_to_b == input;
    let initial = if fixed_is_a { try_delta_a(cur, target, liq, input)? } else { try_delta_b(cur, target, liq, input) };
    let calc = if input {
        let p = (remaining as u128).checked_mul(FEE_RATE_MUL_VALUE.wrapping_sub(fee_rate as u128))?;
        u64::try_from(p / FEE_RATE_MUL_VALUE).ok()?
    } else { remaining };
    let lte = matches!(initial, Delta::Valid(v) if v <= calc);
    let next = if lte { target } else { next_sqrt_price(cur, liq, calc, input, a_to_b)? };
    let is_max = next == target;
    let unfixed = if fixed_is_a { delta_b(cur, next, liq, !input)? } else { delta_a(cur, next, liq, !input)? };
    let fixed = match initial {
        Delta::Valid(v) if is_max => v,
        _ => if fixed_is_a { delta_a(cur, next, liq, input)? } else { delta_b(cur, next, liq, input)? },
    };
    let (amount_in, mut amount_out) = if input { (fixed, unfixed) } else { (unfixed, fixed) };
    if !input && amount_out > remaining { amount_out = remaining; }
    let fee = if input && !is_max { remaining.wrapping_sub(amount_in) } else {
        let d = FEE_RATE_MUL_VALUE.wrapping_sub(fee_rate as u128);
        if d == 0 { return None; }
        let p = (amount_in as u128).checked_mul(fee_rate as u128)?;
        u64::try_from(p / d + (p % d > 0) as u128).ok()?
    };
    Some(StepAmounts { amount_in, amount_out, next, fee })
}

// ---------------------------------------------------------------------------------------------------------------
// adaptive fee (oracle.rs, fee_rate_manager.rs)
// ---------------------------------------------------------------------------------------------------------------

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct AdaptiveConstants { pub filter_period: u16, pub decay_period: u16, pub reduction_factor: u16, pub control: u32, pub max_va: u32, pub tick_group_size: u16, pub major_swap_threshold_ticks: u16 }

#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct AdaptiveVariables { pub last_reference_update: u64, pub last_major_swap: u64, pub v_ref: u32, pub idx_ref: i32, pub va: u32 }

impl AdaptiveVariables {
    fn update_va(&mut self, idx: i32, c: &AdaptiveConstants) {
        let d = self.idx_ref.wrapping_sub(idx).unsigned_abs() as u64;
        self.va = (self.v_ref as u64 + d * VA_SCALE).min(c.max_va as u64) as u32;
    }

    /// `update_reference`. None: InvalidTimestamp (the Clock before the last reference update or major swap)
    fn update_reference(&mut self, idx: i32, now: u64, c: &AdaptiveConstants) -> Option<()> {
        let max_ts = self.last_reference_update.max(self.last_major_swap);
        if now < max_ts { return None; }
        if now - self.last_reference_update > MAX_REFERENCE_AGE {
            self.idx_ref = idx;
            self.v_ref = 0;
            self.last_reference_update = now;
            return Some(());
        }
        let elapsed = now - max_ts;
        if elapsed < c.filter_period as u64 {
        } else if elapsed < c.decay_period as u64 {
            self.idx_ref = idx;
            self.v_ref = (self.va as u64 * c.reduction_factor as u64 / REDUCTION_DEN) as u32;
            self.last_reference_update = now;
        } else {
            self.idx_ref = idx;
            self.v_ref = 0;
            self.last_reference_update = now;
        }
        Some(())
    }
}

/// `FeeRateManager::Adaptive`'s state (Static is `None`)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Adaptive {
    group: i32,
    c: AdaptiveConstants,
    v: AdaptiveVariables,
    /// the core tick-group range's bounds: (group index, its boundary's sqrt price)
    lower: Option<(i32, u128)>,
    upper: Option<(i32, u128)>,
}

impl Adaptive {
    fn new(tick: i32, now: u64, c: AdaptiveConstants, mut v: AdaptiveVariables) -> Result<Adaptive, WhirlWhy> {
        let tgs = c.tick_group_size as i32;
        if tgs == 0 { return Err(WhirlWhy::State); }
        let group = floor_div(tick, tgs);
        v.update_reference(group, now, &c).ok_or(WhirlWhy::Timestamp)?;
        // ceil_division_u32(max_va − v_ref, 1e4), with the program's wrapping arithmetic
        let dividend = c.max_va.wrapping_sub(v.v_ref);
        let q = dividend / VA_SCALE as u32;
        let delta = if q.wrapping_mul(VA_SCALE as u32) == dividend { q } else { q.wrapping_add(1) };
        let lower_index = v.idx_ref.wrapping_sub(delta as i32);
        let upper_index = v.idx_ref.wrapping_add(delta as i32);
        let lower_tick = lower_index.wrapping_mul(tgs);
        let upper_tick = upper_index.wrapping_mul(tgs).wrapping_add(tgs);
        let lower = if lower_tick > MIN_TICK { Some((lower_index, sqrt_price_at_tick(lower_tick).ok_or(WhirlWhy::State)?)) } else { None };
        let upper = if upper_tick < MAX_TICK { Some((upper_index, sqrt_price_at_tick(upper_tick).ok_or(WhirlWhy::State)?)) } else { None };
        Ok(Adaptive { group, c, v, lower, upper })
    }

    fn rate(&self) -> u32 {
        let crossed = self.v.va.wrapping_mul(self.c.tick_group_size as u32);
        let sq = crossed as u64 as u128 * crossed as u64 as u128;
        let num = (self.c.control as u128).wrapping_mul(sq);
        let den = AF_CONTROL_DEN * VA_SCALE as u128 * VA_SCALE as u128;
        let fee = num / den + (num % den != 0) as u128;
        if fee > FEE_RATE_HARD_LIMIT as u128 { FEE_RATE_HARD_LIMIT } else { fee as u32 }
    }

    /// `get_bounded_sqrt_price_target`: (bounded target, skip)
    fn bounded(&self, target: u128, liq: u128, a_to_b: bool) -> Option<(u128, bool)> {
        if self.c.control == 0 || liq == 0 { return Some((target, true)); }
        if let Some((li, lp)) = self.lower {
            if self.group < li { return Some(if a_to_b { (target, true) } else { (target.min(lp), true) }); }
        }
        if let Some((ui, up)) = self.upper {
            if self.group > ui { return Some(if a_to_b { (target.max(up), true) } else { (target, true) }); }
        }
        let tgs = self.c.tick_group_size as i32;
        let bt = if a_to_b { self.group.wrapping_mul(tgs) } else { self.group.wrapping_mul(tgs).wrapping_add(tgs) };
        let bp = sqrt_price_at_tick(bt.clamp(MIN_TICK, MAX_TICK))?;
        Some(if a_to_b { (target.max(bp), false) } else { (target.min(bp), false) })
    }

    /// `advance_tick_group_after_skip`
    fn advance_after_skip(&mut self, sqrt_price: u128, next_tick_price: u128, next_tick: i32, a_to_b: bool) -> Option<()> {
        let tgs = self.c.tick_group_size as i32;
        let (tick, on_boundary) = if sqrt_price == next_tick_price {
            (next_tick, next_tick % tgs == 0)
        } else {
            let t = tick_at_sqrt_price(sqrt_price)?;
            (t, t % tgs == 0 && sqrt_price == sqrt_price_at_tick(t)?)
        };
        let last = if on_boundary && !a_to_b { tick / tgs - 1 } else { floor_div(tick, tgs) };
        if (a_to_b && last < self.group) || (!a_to_b && last > self.group) {
            self.group = last;
            self.v.update_va(self.group, &self.c);
        }
        self.group = self.group.wrapping_add(if a_to_b { -1 } else { 1 });
        Some(())
    }
}

// ---------------------------------------------------------------------------------------------------------------
// tick arrays
// ---------------------------------------------------------------------------------------------------------------

/// A tick as the swap reads it
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Tick { pub initialized: bool, pub liquidity_net: i128, pub liquidity_gross: u128 }

/// One tick array of the swap's sequence
#[derive(Clone, Copy, Debug)]
pub enum TickArray<'a> {
    /// a fixed (9,988 B) or dynamic tick array's bytes
    Fixed(&'a [u8]),
    Dynamic(&'a [u8]),
    /// a tick array the leg passes that does not exist yet (ZeroedTickArray): no initialized tick
    Zeroed(i32),
}

/// A tick array the leg passes, as the engine names it: its start index and its bytes (None: the PDA is passed but
/// the account does not exist)
#[derive(Clone, Copy, Debug)]
pub struct TickArrayIn<'a> { pub start: i32, pub data: Option<&'a [u8]> }

impl<'a> TickArray<'a> {
    /// classify an initialized tick array's bytes by its discriminator (fixed `TickArray`, 9,988 B; `DynamicTickArray`,
    /// 148..=10,004 B): None for anything else (the caller checked the owner and the whirlpool)
    pub fn of(data: &'a [u8]) -> Option<TickArray<'a>> {
        match data.get(..8) {
            Some(d) if d == &crate::layout::DISC_WHIRL_TICK_ARRAY[..] && data.len() == FIXED_ARRAY_LEN => Some(TickArray::Fixed(data)),
            Some(d) if d == &crate::layout::DISC_DYNAMIC_TICK_ARRAY[..] && (DYNAMIC_MIN_LEN..=DYNAMIC_MAX_LEN).contains(&data.len()) => Some(TickArray::Dynamic(data)),
            _ => None,
        }
    }

    pub fn start(&self) -> Option<i32> {
        match self { TickArray::Fixed(d) | TickArray::Dynamic(d) => i32_at(d, off::A_START), TickArray::Zeroed(s) => Some(*s) }
    }

    /// the whirlpool the array belongs to
    pub fn whirlpool(&self) -> Option<&'a [u8; 32]> {
        match self { TickArray::Fixed(d) => key_at(d, off::F_WHIRLPOOL), TickArray::Dynamic(d) => key_at(d, off::D_WHIRLPOOL), TickArray::Zeroed(_) => None }
    }

    fn initialized_at(&self, offset: i32) -> Option<bool> {
        let o = usize::try_from(offset).ok()?;
        match self {
            TickArray::Fixed(d) => Some(u8_at(d, off::F_TICKS + o * off::TICK_LEN)? != 0),
            TickArray::Dynamic(d) => Some(u128_at(d, off::D_BITMAP)? >> o & 1 == 1),
            TickArray::Zeroed(_) => Some(false),
        }
    }

    /// `get_next_init_tick_index`. Err: the program errors (InvalidTickArraySequence: the tick is outside the array's
    /// search range)
    fn next_init_tick(&self, tick: i32, ts: u16, a_to_b: bool) -> Option<Option<i32>> {
        let start = self.start()?;
        let tsi = ts as i32;
        let (mut lo_, mut up) = (start, start + TICK_ARRAY_SIZE * tsi);
        if !a_to_b { lo_ -= tsi; up -= tsi; }
        if !(tick >= lo_ && tick < up) { return None; }
        let mut cur = floor_div(tick - start, tsi);
        if !a_to_b { cur += 1; }
        if let TickArray::Zeroed(_) = self { return Some(None); }
        while (0..TICK_ARRAY_SIZE).contains(&cur) {
            if self.initialized_at(cur)? { return Some(Some(cur * tsi + start)); }
            cur += if a_to_b { -1 } else { 1 };
        }
        Some(None)
    }

    /// `get_tick`: Err (here None) where the program's get_tick errs, which the swap reads as "not initialized"
    fn tick(&self, tick: i32, ts: u16) -> Option<Tick> {
        let start = self.start()?;
        let tsi = ts as i32;
        if !(tick >= start && tick < start + TICK_ARRAY_SIZE * tsi) || !(MIN_TICK..=MAX_TICK).contains(&tick) || tick % tsi != 0 { return None; }
        let offset = usize::try_from(floor_div(tick - start, tsi)).ok()?;
        match self {
            TickArray::Fixed(d) => {
                let o = off::F_TICKS + offset * off::TICK_LEN;
                Some(Tick { initialized: u8_at(d, o)? != 0, liquidity_net: i128_at(d, o + 1)?, liquidity_gross: u128_at(d, o + 17)? })
            }
            TickArray::Dynamic(d) => {
                // byte offset: 113 per initialized tick before it (by the bitmap), 1 per uninitialized one; bytes past
                // the account's end read as zero (the runtime's realloc padding)
                let bitmap = u128_at(d, off::D_BITMAP)?;
                let mask = if offset >= 128 { u128::MAX } else { (1u128 << offset) - 1 };
                let init = (bitmap & mask).count_ones() as usize;
                let o = off::D_TICKS + init * off::TICK_LEN + (offset - init);
                let byte = |k: usize| d.get(o + k).copied().unwrap_or(0);
                match byte(0) {
                    0 => Some(Tick::default()),
                    1 => {
                        let mut buf = [0u8; 32];
                        for (k, b) in buf.iter_mut().enumerate() { *b = byte(1 + k); }
                        Some(Tick { initialized: true, liquidity_net: i128::from_le_bytes(buf[..16].try_into().ok()?),
                            liquidity_gross: u128::from_le_bytes(buf[16..].try_into().ok()?) })
                    }
                    // a Borsh enum tag the program cannot read: its get_tick errs
                    _ => None,
                }
            }
            TickArray::Zeroed(_) => Some(Tick::default()),
        }
    }

    fn tick_offset(&self, tick: i32, ts: u16) -> Option<i32> { Some(floor_div(tick - self.start()?, ts as i32)) }
    fn is_min(&self) -> Option<bool> { Some(self.start()? <= MIN_TICK) }
    fn is_max(&self, ts: u16) -> Option<bool> { Some(self.start()? + TICK_ARRAY_SIZE * ts as i32 > MAX_TICK) }
}

// ---------------------------------------------------------------------------------------------------------------
// the leg
// ---------------------------------------------------------------------------------------------------------------

/// A parsed Orca Whirlpool leg: the pool's swap fields, its adaptive fee (after the swap's reference update) and the
/// swap's tick-array sequence, in one direction
#[derive(Clone, Copy, Debug)]
pub struct WhirlLeg<'a> {
    pub a_to_b: bool,
    pub tick_spacing: u16,
    pub fee_rate: u16,
    pub protocol_fee_rate: u16,
    pub liquidity: u128,
    pub sqrt_price: u128,
    pub tick: i32,
    /// the Clock's unix timestamp (u64)
    pub now: u64,
    pub vault_out: u64,
    /// the input token's global fee growth and its protocol fee owed
    pub fee_growth_global: u128,
    pub protocol_fee_owed: u64,
    adaptive: Option<Adaptive>,
    seq: [Option<TickArray<'a>>; 3],
    n_seq: u8,
    budget: u16,
}

/// Parse the pool, its Oracle (None: not initialized) and the tick arrays the leg passes (start index and bytes, None
/// for a passed PDA that does not exist; fixed and dynamic arrays told apart by their discriminator; owner and
/// whirlpool checks are the caller's: leg.rs). `vault_a`/`vault_b`: the pool's vault amounts.
pub fn parse<'a>(pool: &'a [u8], oracle: Option<&'a [u8]>, arrays: &[TickArrayIn<'a>], vault_a: u64, vault_b: u64, a_to_b: bool, clock: &Clock) -> Result<WhirlLeg<'a>, Abort> {
    if pool.len() != POOL_LEN { return Err(Abort::Layout); }
    let l = Abort::Layout;
    let now = u64::try_from(clock.unix_timestamp).map_err(|_| Abort::Whirl(WhirlWhy::Timestamp))?;
    let ts = u16_at(pool, off::TICK_SPACING).ok_or(l)?;
    if ts == 0 { return Err(Abort::Whirl(WhirlWhy::State)); }
    let sqrt_price = u128_at(pool, off::SQRT_PRICE).ok_or(l)?;
    let tick = i32_at(pool, off::TICK_CURRENT).ok_or(l)?;
    // swap: the default limit (MIN or MAX sqrt price) must lie strictly beyond the pool's price
    if (a_to_b && MIN_SQRT_PRICE_X64 >= sqrt_price) || (!a_to_b && MAX_SQRT_PRICE_X64 <= sqrt_price) {
        return Err(Abort::Whirl(WhirlWhy::PriceLimit));
    }
    // next_whirlpool_reward_infos: the Clock may not be before the last reward update
    if now < u64_at(pool, off::REWARD_LAST_UPDATED).ok_or(l)? { return Err(Abort::Whirl(WhirlWhy::Timestamp)); }
    let adaptive = match oracle {
        None => None,
        Some(o) => {
            if o.len() != ORACLE_LEN { return Err(l); }
            if u64_at(o, off::O_TRADE_ENABLE).ok_or(l)? > now { return Err(Abort::Whirl(WhirlWhy::TradeNotEnabled)); }
            let c0 = off::O_CONSTANTS;
            let c = AdaptiveConstants {
                filter_period: u16_at(o, c0).ok_or(l)?, decay_period: u16_at(o, c0 + 2).ok_or(l)?, reduction_factor: u16_at(o, c0 + 4).ok_or(l)?,
                control: u32_at(o, c0 + 6).ok_or(l)?, max_va: u32_at(o, c0 + 10).ok_or(l)?, tick_group_size: u16_at(o, c0 + 14).ok_or(l)?,
                major_swap_threshold_ticks: u16_at(o, c0 + 16).ok_or(l)?,
            };
            let v0 = off::O_VARIABLES;
            let v = AdaptiveVariables {
                last_reference_update: u64_at(o, v0).ok_or(l)?, last_major_swap: u64_at(o, v0 + 8).ok_or(l)?, v_ref: u32_at(o, v0 + 16).ok_or(l)?,
                idx_ref: i32_at(o, v0 + 20).ok_or(l)?, va: u32_at(o, v0 + 24).ok_or(l)?,
            };
            if c.tick_group_size == 0 { return Err(Abort::Whirl(WhirlWhy::State)); }
            Some(Adaptive::new(tick, now, c, v).map_err(Abort::Whirl)?)
        }
    };
    // the sparse sequence: each needed start index from an initialized array, else from a passed uninitialized PDA
    let (need, n_need) = needed_starts(tick, ts, a_to_b);
    let mut seq: [Option<TickArray<'a>>; 3] = [None; 3];
    let mut n = 0usize;
    for &st in need.iter().take(n_need) {
        let init = arrays.iter().find_map(|a| a.data.and_then(TickArray::of).filter(|t| t.start() == Some(st)));
        let entry = match init {
            Some(t) => Some(t),
            None if arrays.iter().any(|a| a.data.is_none() && a.start == st) => Some(TickArray::Zeroed(st)),
            None => None,
        };
        let Some(e) = entry else { break };
        if let Some(s) = seq.get_mut(n) { *s = Some(e); n += 1; }
    }
    if n == 0 { return Err(Abort::Whirl(WhirlWhy::TickArrays)); }
    let fee_rate = u16_at(pool, off::FEE_RATE).ok_or(l)?;
    let (fg, pf) = if a_to_b { (off::FEE_GROWTH_A, off::PROTOCOL_FEE_OWED_A) } else { (off::FEE_GROWTH_B, off::PROTOCOL_FEE_OWED_B) };
    Ok(WhirlLeg {
        a_to_b, tick_spacing: ts, fee_rate, protocol_fee_rate: u16_at(pool, off::PROTOCOL_FEE_RATE).ok_or(l)?,
        liquidity: u128_at(pool, off::LIQUIDITY).ok_or(l)?, sqrt_price, tick, now,
        vault_out: if a_to_b { vault_b } else { vault_a }, fee_growth_global: u128_at(pool, fg).ok_or(l)?,
        protocol_fee_owed: u64_at(pool, pf).ok_or(l)?, adaptive, seq, n_seq: n as u8, budget: NO_BUDGET,
    })
}

/// Why a walk ended
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum End { Cap, Budget }

/// One step of an exact swap ([`WhirlLeg::fills`])
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct WhirlStep {
    pub sqrt_price_from: u128,
    pub sqrt_price_to: u128,
    pub liquidity: u128,
    pub fee_rate: u32,
    pub amount_in: u64,
    pub amount_out: u64,
    pub fee: u64,
    /// the tick the step ended on (the next initialized tick, or the end of the sequence), crossed when initialized
    pub tick: Option<i32>,
    pub crossed: bool,
    /// the start index of the tick array that tick is in
    pub array: i32,
}

/// The pool after a swap (`update_after_swap`, the oracle's variables)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct PostSwap {
    pub sqrt_price: u128,
    pub tick: i32,
    pub liquidity: u128,
    /// the input token's global fee growth and its protocol fee owed
    pub fee_growth_global: u128,
    pub protocol_fee_owed: u64,
    pub adaptive: Option<AdaptiveVariables>,
}

/// An exact swap's walk: its quote, the steps, the initialized ticks crossed, the tick arrays the sequence used (the
/// leg passes these) and the post-swap pool
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct WhirlWalk { pub quote: Quote, pub steps: u16, pub crossed: u16, pub arrays: [i32; 3], pub n_arrays: u8, pub arrays_used: u8, pub post: PostSwap }

#[derive(Clone, Copy, Debug)]
struct Pending { array_index: usize, next_tick: i32, next_tick_price: u128, target: u128 }

#[derive(Clone, Copy, Debug)]
struct Walker {
    remaining: u64,
    calculated: u64,
    sqrt_price: u128,
    tick: i32,
    liquidity: u128,
    protocol_fee: u64,
    fee_growth: u128,
    array_index: usize,
    adaptive: Option<Adaptive>,
    pending: Option<Pending>,
    steps: u16,
    crossed: u16,
    max_array: usize,
}

impl<'a> WhirlLeg<'a> {
    pub fn with_budget(mut self, steps: u16) -> Self { self.budget = steps; self }
    pub fn budget(&self) -> u16 { self.budget }
    /// the start indexes of the swap's tick-array sequence (what the leg must pass: initialized or as their PDA)
    pub fn sequence(&self) -> ([i32; 3], u8) {
        let mut s = [0i32; 3];
        for (i, t) in self.seq.iter().take(self.n_seq as usize).enumerate() { if let (Some(t), Some(slot)) = (t, s.get_mut(i)) { *slot = t.start().unwrap_or(0); } }
        (s, self.n_seq)
    }
    pub fn is_adaptive(&self) -> bool { self.adaptive.is_some() }

    fn arr(&self, i: usize) -> Option<&TickArray<'a>> { if i < self.n_seq as usize { self.seq.get(i)?.as_ref() } else { None } }

    fn walker(&self, amount: u64) -> Walker {
        Walker {
            remaining: amount, calculated: 0, sqrt_price: self.sqrt_price, tick: self.tick, liquidity: self.liquidity, protocol_fee: 0,
            fee_growth: self.fee_growth_global, array_index: 0, adaptive: self.adaptive, pending: None, steps: 0, crossed: 0, max_array: 0,
        }
    }

    /// `SwapTickSequence::get_next_initialized_tick_index`. None: the program errors
    fn next_initialized(&self, tick: i32, start_index: usize) -> Option<(usize, i32)> {
        let ts = self.tick_spacing;
        let per = TICK_ARRAY_SIZE * ts as i32;
        let mut search = tick;
        let mut i = start_index;
        loop {
            let a = self.arr(i)?;
            match a.next_init_tick(search, ts, self.a_to_b)? {
                Some(t) => return Some((i, t)),
                None => {
                    if self.a_to_b && a.is_min()? { return Some((i, MIN_TICK)); }
                    if !self.a_to_b && a.is_max(ts)? { return Some((i, MAX_TICK)); }
                    let st = a.start()?;
                    if i + 1 == self.n_seq as usize { return Some((i, if self.a_to_b { st } else { st + per - 1 })); }
                    search = if self.a_to_b { st - 1 } else { st + per - 1 };
                    i += 1;
                }
            }
        }
    }

    /// One inner step of `swap_manager::swap`'s loop (a new outer iteration when none is in progress)
    fn inner_step(&self, w: &mut Walker, input: bool, f: &mut dyn FnMut(&WhirlStep)) -> R<()> {
        let a_to_b = self.a_to_b;
        let ts = self.tick_spacing;
        let limit = if a_to_b { MIN_SQRT_PRICE_X64 } else { MAX_SQRT_PRICE_X64 };
        let p = match w.pending {
            Some(p) => p,
            None => {
                let (ai, next_tick) = self.next_initialized(w.tick, w.array_index).ok_or(TOO_LARGE)?;
                let next_tick_price = sqrt_price_at_tick(next_tick).ok_or(TOO_LARGE)?;
                let target = if a_to_b { limit.max(next_tick_price) } else { limit.min(next_tick_price) };
                w.max_array = w.max_array.max(ai);
                Pending { array_index: ai, next_tick, next_tick_price, target }
            }
        };
        if w.steps >= self.budget { return Err(QuoteErr::Budget); }
        w.steps += 1;
        if let Some(ad) = w.adaptive.as_mut() { let g = ad.group; let c = ad.c; ad.v.update_va(g, &c); }
        let fee_rate = match &w.adaptive {
            Some(ad) => { let t = self.fee_rate as u32 + ad.rate(); if t > FEE_RATE_HARD_LIMIT { FEE_RATE_HARD_LIMIT } else { t } }
            None => self.fee_rate as u32,
        };
        let (bounded, skipped) = match &w.adaptive { Some(ad) => ad.bounded(p.target, w.liquidity, a_to_b).ok_or(TOO_LARGE)?, None => (p.target, false) };
        let from = w.sqrt_price;
        let st = compute_swap(w.remaining, fee_rate, w.liquidity, w.sqrt_price, bounded, input, a_to_b).ok_or(TOO_LARGE)?;
        if input {
            w.remaining = w.remaining.checked_sub(st.amount_in).ok_or(TOO_LARGE)?.checked_sub(st.fee).ok_or(TOO_LARGE)?;
            w.calculated = w.calculated.checked_add(st.amount_out).ok_or(TOO_LARGE)?;
        } else {
            w.remaining = w.remaining.checked_sub(st.amount_out).ok_or(TOO_LARGE)?;
            w.calculated = w.calculated.checked_add(st.amount_in).ok_or(TOO_LARGE)?.checked_add(st.fee).ok_or(TOO_LARGE)?;
        }
        // calculate_fees: the protocol's share, then the LPs' growth (wrapping, as deployed)
        let mut global = st.fee;
        if self.protocol_fee_rate > 0 {
            let delta = ((global as u128) * (self.protocol_fee_rate as u128) / PROTOCOL_FEE_RATE_MUL_VALUE) as u64;
            global = global.wrapping_sub(delta);
            w.protocol_fee = w.protocol_fee.wrapping_add(delta);
        }
        if w.liquidity > 0 { w.fee_growth = w.fee_growth.wrapping_add(((global as u128) << 64) / w.liquidity); }
        let mut step = WhirlStep { sqrt_price_from: from, sqrt_price_to: st.next, liquidity: w.liquidity, fee_rate, amount_in: st.amount_in,
            amount_out: st.amount_out, fee: st.fee, tick: None, crossed: false, array: 0 };
        if st.next == p.next_tick_price {
            let arr = self.arr(p.array_index).ok_or(TOO_LARGE)?;
            step.array = arr.start().ok_or(TOO_LARGE)?;
            step.tick = Some(p.next_tick);
            if let Some(t) = arr.tick(p.next_tick, ts).filter(|t| t.initialized) {
                let net = if a_to_b { t.liquidity_net.wrapping_neg() } else { t.liquidity_net };
                w.liquidity = add_liquidity_delta(w.liquidity, net).ok_or(TOO_LARGE)?;
                step.crossed = true;
                w.crossed = w.crossed.saturating_add(1);
            }
            let offset = arr.tick_offset(p.next_tick, ts).ok_or(TOO_LARGE)?;
            w.array_index = if (a_to_b && offset == 0) || (!a_to_b && offset == TICK_ARRAY_SIZE - 1) { p.array_index + 1 } else { p.array_index };
            w.tick = if a_to_b { p.next_tick - 1 } else { p.next_tick };
        } else if st.next != w.sqrt_price {
            w.tick = tick_at_sqrt_price(st.next).ok_or(TOO_LARGE)?;
        }
        w.sqrt_price = st.next;
        if let Some(ad) = w.adaptive.as_mut() {
            if !skipped { ad.group = ad.group.wrapping_add(if a_to_b { -1 } else { 1 }); }
            else { ad.advance_after_skip(w.sqrt_price, p.next_tick_price, p.next_tick, a_to_b).ok_or(TOO_LARGE)?; }
        }
        f(&step);
        if w.remaining == 0 || w.sqrt_price == p.target { w.pending = None; } else { w.pending = Some(p); }
        Ok(())
    }

    fn post(&self, w: &Walker) -> R<PostSwap> {
        let adaptive = match w.adaptive {
            Some(ad) => {
                let mut v = ad.v;
                if is_major_swap(self.sqrt_price, w.sqrt_price, ad.c.major_swap_threshold_ticks).ok_or(TOO_LARGE)? { v.last_major_swap = self.now; }
                Some(v)
            }
            None => None,
        };
        Ok(PostSwap { sqrt_price: w.sqrt_price, tick: w.tick, liquidity: w.liquidity, fee_growth_global: w.fee_growth,
            protocol_fee_owed: self.protocol_fee_owed.wrapping_add(w.protocol_fee), adaptive })
    }

    /// The exact swap of `amount` (`exact_out`: the output wanted), every step seen by `f`: the quote, the walk and the
    /// post-swap pool
    pub fn fills(&self, amount: u64, exact_out: bool, f: &mut dyn FnMut(&WhirlStep)) -> R<WhirlWalk> {
        if amount == 0 { return Err(QuoteErr::ZeroOut); }
        let input = !exact_out;
        let limit = if self.a_to_b { MIN_SQRT_PRICE_X64 } else { MAX_SQRT_PRICE_X64 };
        let mut w = self.walker(amount);
        while w.remaining > 0 && w.sqrt_price != limit { self.inner_step(&mut w, input, f)?; }
        // exact out without a price limit: a partial fill fails (PartialFillError)
        if w.remaining > 0 && !input { return Err(TOO_LARGE); }
        let (spent, out) = if input { (amount - w.remaining, w.calculated) } else { (w.calculated, amount - w.remaining) };
        // swap_v2: exact in pays at least the threshold (the leg's 1); the vault pays the output
        if out == 0 { return Err(QuoteErr::ZeroOut); }
        if out > self.vault_out { return Err(TOO_LARGE); }
        let post = self.post(&w)?;
        let (s, n) = self.sequence();
        Ok(WhirlWalk { quote: Quote { out, spent }, steps: w.steps, crossed: w.crossed, arrays: s, n_arrays: n, arrays_used: (w.max_array + 1) as u8, post })
    }

    /// The exact quote (swap_v2, exact in)
    pub fn quote(&self, x: u64) -> R<Quote> { self.fills(x, false, &mut |_| {}).map(|w| w.quote) }

    /// The exact quote of swap_v2 exact out: `out` and the input it debits
    pub fn quote_exact_out(&self, out: u64) -> R<Quote> { self.fills(out, true, &mut |_| {}).map(|w| w.quote) }

    /// Swap steps the exact swap of `x` takes (no budget): the descriptor's `max_bins`
    pub fn steps_for(&self, x: u64) -> Option<u16> { self.with_budget(NO_BUDGET).fills(x, false, &mut |_| {}).ok().map(|w| w.steps) }

    /// The largest input that quotes Ok (None: every u64 does), by bisection over the exact swap
    pub fn cap_in(&self) -> Option<u64> {
        if self.quote(u64::MAX).is_ok() { return None; }
        let (mut lo_, mut hi_) = (0u64, u64::MAX);
        while hi_ - lo_ > 1 {
            let mid = lo_ + (hi_ - lo_) / 2;
            match self.quote(mid) { Ok(_) | Err(QuoteErr::ZeroOut) => lo_ = mid, Err(_) => hi_ = mid }
        }
        Some(lo_)
    }

    /// The locator's stream of this leg: the exact swap of an unbounded input, one step at a time
    pub fn stream(&self) -> Steps<'_, 'a> { Steps { leg: self, w: Some(self.walker(u64::MAX)), used: 0, out: 0, done: false } }

    fn mobius(&self, p: u128, liq: u128, fee_rate: u32) -> (Fx, Fx, Fx) {
        let l = Fx::from_u128(liq);
        let pf = Fx::from_u128(p);
        let x = l.shl(64).div(pf);
        let y = l.mul(pf).shl(-64);
        let (r_in, r_out) = if self.a_to_b { (x, y) } else { (y, x) };
        let keep = fee_keep(fee_rate);
        // Orca charges the fee on the input only
        (keep.mul(r_out), r_in, keep)
    }

    /// An upper bound on the output per input of every step after one ending at sqrt price `p`: the marginal price there
    /// net of the static fee (the adaptive part is never negative)
    pub fn bound_after(&self, p: u128) -> Fx {
        let pf = Fx::from_u128(p).shl(-64);
        let price = if self.a_to_b { pf.mul(pf) } else { Fx::ONE.div(pf.mul(pf)) };
        price.mul(fee_keep(self.fee_rate as u32))
    }
}

fn fee_keep(fee_rate: u32) -> Fx {
    Fx::from_u64((FEE_RATE_MUL_VALUE as u64).saturating_sub(fee_rate as u64)).div(Fx::from_u64(FEE_RATE_MUL_VALUE as u64))
}

/// `add_liquidity_delta`
fn add_liquidity_delta(liq: u128, delta: i128) -> Option<u128> {
    if delta == 0 { return Some(liq); }
    if delta > 0 { liq.checked_add(delta as u128) } else { liq.checked_sub(delta.unsigned_abs()) }
}

/// `AdaptiveFeeVariables::is_major_swap`
fn is_major_swap(pre: u128, post: u128, threshold: u16) -> Option<bool> {
    let (small, large) = if pre > post { (post, pre) } else { (pre, post) };
    let factor = sqrt_price_at_tick(threshold as i32)?;
    let target = U256::mul128(small, factor).shr(64).to_u128()?;
    Some(large >= target)
}

/// One model piece: one exact swap step's input and output, and its range's curve (see raydium_clmm::StepPiece)
#[derive(Clone, Copy, Debug)]
pub struct StepPiece { pub used: u64, pub out: u64, pub mobius: Option<(Fx, Fx, Fx)>, pub bound: Fx }

/// The exact swap of an unbounded input, step by step: the locator's pieces
#[derive(Clone, Copy, Debug)]
pub struct Steps<'l, 'a> { leg: &'l WhirlLeg<'a>, w: Option<Walker>, pub used: u64, pub out: u64, done: bool }

impl Steps<'_, '_> {
    /// The next step's piece, seen by `push`. Err: the walk ends here
    pub fn next(&mut self, push: &mut dyn FnMut(StepPiece)) -> Result<(), End> {
        if self.done { return Err(End::Cap); }
        let Some(mut w) = self.w else { self.done = true; return Err(End::Cap) };
        let leg = self.leg;
        let limit = if leg.a_to_b { MIN_SQRT_PRICE_X64 } else { MAX_SQRT_PRICE_X64 };
        let mut piece: Option<StepPiece> = None;
        let mut cb = |s: &WhirlStep| {
            let used = s.amount_in.saturating_add(s.fee);
            if used > 0 || s.amount_out > 0 {
                piece = Some(StepPiece { used, out: s.amount_out, mobius: Some(leg.mobius(s.sqrt_price_from, s.liquidity, s.fee_rate)),
                    bound: leg.bound_after(s.sqrt_price_to) });
            }
        };
        let r = if w.sqrt_price == limit { Err(TOO_LARGE) } else { leg.inner_step(&mut w, true, &mut cb) };
        if let Err(e) = r { self.done = true; return Err(if e == QuoteErr::Budget { End::Budget } else { End::Cap }); }
        // a step that did not reach its boundary used the input up: with u64::MAX of it, the end of u64
        if w.remaining == 0 { self.done = true; return Err(End::Cap); }
        if let Some(p) = piece {
            self.used = self.used.checked_add(p.used).ok_or(End::Cap)?;
            self.out = self.out.checked_add(p.out).ok_or(End::Cap)?;
            push(p);
        }
        self.w = Some(w);
        Ok(())
    }
}

/// The decimal string of `start` (the tick array PDA's seed: `start_tick_index.to_string()`), in `buf`
pub fn start_seed(start: i32, buf: &mut [u8; 12]) -> &[u8] {
    let mut n = start.unsigned_abs();
    let mut tmp = [0u8; 12];
    let mut k = 0;
    loop {
        if let Some(s) = tmp.get_mut(k) { *s = b'0' + (n % 10) as u8; }
        k += 1;
        n /= 10;
        if n == 0 { break; }
    }
    let mut o = 0;
    if start < 0 { buf[0] = b'-'; o = 1; }
    for i in 0..k { if let (Some(d), Some(s)) = (buf.get_mut(o + i), tmp.get(k - 1 - i)) { *d = *s; } }
    buf.get(..o + k).unwrap_or(&[])
}

#[cfg(test)]
mod tests {
    use super::*;

    /// the deployed U256Muldiv division against an exact one: equal wherever it does not fail
    #[test]
    fn muldiv_div_matches_exact_division() {
        let mut s = 0x9e37_79b9_7f4a_7c15u64;
        let mut next = || { s ^= s << 13; s ^= s >> 7; s ^= s << 17; s };
        let mut fails = 0;
        for _ in 0..20_000 {
            let mut a = [next(), next(), next(), next()];
            let mut b = [next(), next(), next(), next()];
            let na = (next() % 5) as usize;
            let nb = 1 + (next() % 4) as usize;
            for w in a.iter_mut().skip(na) { *w = 0; }
            for w in b.iter_mut().skip(nb) { *w = 0; }
            if next() % 3 == 0 { b[nb - 1] >>= next() % 64; }
            if num_words(&b) == 0 { continue; }
            let exact = U256(a).div_rem(U256(b)).unwrap();
            match muldiv_div(&a, &b) {
                Some((q, r)) => { assert_eq!((q, r), (exact.0 .0, exact.1 .0), "{a:?} / {b:?}"); }
                None => fails += 1,
            }
        }
        assert!(fails < 50, "{fails} failures");
    }

    #[test]
    fn start_seeds_are_decimal() {
        let mut b = [0u8; 12];
        assert_eq!(start_seed(0, &mut b), b"0");
        assert_eq!(start_seed(-2_894_848, &mut b), b"-2894848");
        assert_eq!(start_seed(56_320, &mut b), b"56320");
        assert_eq!(start_seed(i32::MIN, &mut b), b"-2147483648");
    }
}

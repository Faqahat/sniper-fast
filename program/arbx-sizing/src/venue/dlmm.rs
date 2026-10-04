//! Meteora DLMM (LBUZKhRx…), lb_clmm 0.12 (DESIGN.md §2.4): the exact `swap2` exact-in evaluator with limit-order
//! layers, both fee-collection modes and the bitmap jump to the next bin array with liquidity, and the locator's
//! per-bin linear model. Both read the bins through the same [`BinWalker`], so they share every CAP condition: the
//! end of the passed arrays, a missing array, an array index outside the pair's own bitmap (the extension would be
//! needed) and the pair's own `min_bin_id` / `max_bin_id`. The leg's walk BUDGET (bins walked, empty ones inside a
//! visited array included; set by the engine per leg in the descriptor) is a separate end: past it the evaluator
//! answers [`QuoteErr::Budget`] ("not evaluated"), never TooLarge, because the venue would still fill. Since every
//! walk is bounded in bins, so is the CU of the walk (DESIGN.md §4.7).
//!
//! One walk serves both the locator and the exact evaluator: [`DlmmLeg::advance`] moves a [`Cursor`] over one bin
//! with the EXACT integer amounts that drain it (the input taken, the smallest input that also leaves some for the
//! next bin, and the output). A cursor is a resumable swap state: [`DlmmLeg::quote_from`] continues the exact swap from
//! it for any input that drains every earlier bin, so a candidate next to a cursor costs one bin instead of a walk
//! from the active bin (DESIGN.md §3.4 "Cost").
use crate::error::{Abort, DlmmWhy, Quote, QuoteErr};
use crate::fx::Fx;
use crate::math::{ceil_div, div, i32_at, i64_at, key_at, mul_shr64, shl64_div, u128_at, u16_at, u32_at, u64_at, u8_at, ZERO_KEY};
use crate::Clock;

pub const PAIR_LEN: usize = 904;
pub const ARRAY_LEN: usize = 10_136;
pub const BINS_PER_ARRAY: i64 = 70;
pub const MAX_ARRAYS: usize = 5;
/// No walk budget (off-chain use: the passed arrays bound the walk, at most 5 × 70 bins)
pub const NO_BUDGET: u16 = u16::MAX;
/// accepted version bytes (widened once the harness has seen others)
pub const PAIR_VERSIONS: [u8; 1] = [1];
pub const ARRAY_VERSIONS: [u8; 1] = [2];
const FEE_PRECISION: u128 = 1_000_000_000;
const MAX_FEE_RATE: u128 = 100_000_000;
const BPS: u64 = 10_000;

pub mod off {
    pub const BASE_FACTOR: usize = 8;
    pub const FILTER_PERIOD: usize = 10;
    pub const DECAY_PERIOD: usize = 12;
    pub const REDUCTION_FACTOR: usize = 14;
    pub const VFC: usize = 16;
    pub const MAX_VA: usize = 20;
    pub const MIN_BIN_ID: usize = 24;
    pub const MAX_BIN_ID: usize = 28;
    pub const POWER: usize = 34;
    pub const FUNCTION_TYPE: usize = 35;
    pub const COLLECT_FEE_MODE: usize = 36;
    pub const VA: usize = 40;
    pub const V_REF: usize = 44;
    pub const IDX_REF: usize = 48;
    pub const LAST_TS: usize = 56;
    pub const PAIR_TYPE: usize = 75;
    pub const ACTIVE_ID: usize = 76;
    pub const BIN_STEP: usize = 80;
    pub const STATUS: usize = 82;
    pub const ACTIVATION_TYPE: usize = 86;
    pub const MINT_X: usize = 88;
    pub const MINT_Y: usize = 120;
    pub const REWARD0_MINT: usize = 264;
    pub const REWARD1_MINT: usize = 408;
    pub const BITMAP: usize = 584;
    pub const ACTIVATION_POINT: usize = 816;
    pub const VERSION: usize = 882;
    // BinArray
    pub const A_INDEX: usize = 8;
    pub const A_VERSION: usize = 16;
    pub const A_LB_PAIR: usize = 24;
    pub const A_BINS: usize = 56;
    pub const BIN_SIZE: usize = 144;
    // Bin
    pub const B_AMOUNT_X: usize = 0;
    pub const B_AMOUNT_Y: usize = 8;
    pub const B_PRICE: usize = 16;
    pub const B_OPEN_ORDER: usize = 112;
    pub const B_PROCESSED_REMAINING: usize = 128;
    pub const B_ASK_SIDE: usize = 140;
}

/// a·b for b < 2^64: one widening 64×64 multiply when a < 2^64 too (the usual case: no checked u128 multiply), else
/// the checked product
#[inline]
fn wmul(a: u128, b: u128) -> Option<u128> {
    if (a | b) >> 64 == 0 { Some((a as u64 as u128).wrapping_mul(b as u64 as u128)) } else { a.checked_mul(b) }
}

/// ⌊bin / 70⌋ (floor, also for negative ids)
pub fn array_index(bin: i32) -> i64 { (bin as i64).div_euclid(BINS_PER_ARRAY) }

/// Everything a swap reads from the pair, after `update_references` with the Clock.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DlmmParams {
    /// X → Y (walk down)
    pub swap_for_y: bool,
    pub fee_on_input: bool,
    /// limit-order layers count
    pub support_lo: bool,
    /// base_factor · bin_step · 10 · 10^power (out of 1e9)
    pub base_rate: u128,
    pub vfc: u128,
    pub bin_step: u32,
    pub max_va: u64,
    pub v_ref: u64,
    pub idx_ref: i32,
    pub active: i32,
    /// the pair's own bin-id bounds (StaticParameters): `advance_active_bin` fails PairInsufficientLiquidity outside
    pub min_bin: i32,
    pub max_bin: i32,
}

/// A parsed DLMM leg: the pair's parameters, its bitmap (read in place), the passed bin arrays by index and the walk
/// budget.
#[derive(Clone, Copy, Debug)]
pub struct DlmmLeg<'a> {
    pub p: DlmmParams,
    pair: &'a [u8],
    arrays: [(i64, &'a [u8]); MAX_ARRAYS],
    n_arrays: u8,
    /// the locator's fee model, fixed per leg: base/1e9, vfc/(1e11·1e9), the 10% cap, and 1e4/(1e4 + bin_step)
    lf: LocatorFees,
    /// bins a walk may read ([`NO_BUDGET`]: unbounded)
    budget: u16,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct LocatorFees { base: Fx, var_k: Fx, cap: Fx, step: Fx }

/// Parse the pair and its passed bin arrays (owner/key/lb_pair checks are the caller's). `arrays` in any order. The
/// leg has no walk budget; [`DlmmLeg::with_budget`] sets the descriptor's.
pub fn parse<'a>(pair: &'a [u8], arrays: &[&'a [u8]], swap_for_y: bool, clock: &Clock) -> Result<DlmmLeg<'a>, Abort> {
    if pair.len() != PAIR_LEN || !PAIR_VERSIONS.contains(&u8_at(pair, off::VERSION).unwrap_or(0)) { return Err(Abort::Layout); }
    if arrays.len() > MAX_ARRAYS { return Err(Abort::Layout); }
    let mut set = [(0i64, &[][..]); MAX_ARRAYS];
    for (slot, a) in set.iter_mut().zip(arrays) {
        if a.len() != ARRAY_LEN || !ARRAY_VERSIONS.contains(&u8_at(a, off::A_VERSION).unwrap_or(0)) { return Err(Abort::Layout); }
        *slot = (i64_at(a, off::A_INDEX).ok_or(Abort::Layout)?, *a);
    }
    let l = |o| u16_at(pair, o).ok_or(Abort::Layout);
    if u8_at(pair, off::STATUS) != Some(0) { return Err(Abort::Dlmm(DlmmWhy::Status)); }
    let ts = clock.unix_timestamp;
    let point = match u8_at(pair, off::ACTIVATION_TYPE) {
        Some(0) => clock.slot,
        Some(1) => u64::try_from(ts).unwrap_or(0),
        _ => return Err(Abort::Dlmm(DlmmWhy::ActivationType)),
    };
    // checked for every pair type (the program checks Permission / CustomizablePermissionless pairs; the others
    // carry activation_point 0 on mainnet, so this is only stricter)
    if point < u64_at(pair, off::ACTIVATION_POINT).ok_or(Abort::Layout)? { return Err(Abort::Dlmm(DlmmWhy::NotActive)); }
    let active = i32_at(pair, off::ACTIVE_ID).ok_or(Abort::Layout)?;
    // update_references (u32 arithmetic, like the program)
    let va = u32_at(pair, off::VA).ok_or(Abort::Layout)?;
    let mut v_ref = u32_at(pair, off::V_REF).ok_or(Abort::Layout)?;
    let mut idx_ref = i32_at(pair, off::IDX_REF).ok_or(Abort::Layout)?;
    let elapsed = ts.checked_sub(i64_at(pair, off::LAST_TS).ok_or(Abort::Layout)?).ok_or(Abort::Math)?;
    if elapsed >= l(off::FILTER_PERIOD)? as i64 {
        idx_ref = active;
        v_ref = if elapsed < l(off::DECAY_PERIOD)? as i64 { va.checked_mul(l(off::REDUCTION_FACTOR)? as u32).ok_or(Abort::Math)? / BPS as u32 } else { 0 };
    }
    let support_lo = match u8_at(pair, off::FUNCTION_TYPE) {
        Some(2) => true,
        Some(0) => key_at(pair, off::REWARD0_MINT) == Some(&ZERO_KEY) && key_at(pair, off::REWARD1_MINT) == Some(&ZERO_KEY),
        Some(1) => false,
        _ => return Err(Abort::Dlmm(DlmmWhy::FunctionType)),
    };
    let fee_on_input = match u8_at(pair, off::COLLECT_FEE_MODE) {
        Some(0) => true,
        Some(1) => !swap_for_y,
        _ => return Err(Abort::Dlmm(DlmmWhy::CollectFeeMode)),
    };
    let bin_step = l(off::BIN_STEP)? as u32;
    if bin_step == 0 { return Err(Abort::Layout); }
    let power = u8_at(pair, off::POWER).ok_or(Abort::Layout)? as u32;
    let base_rate = (l(off::BASE_FACTOR)? as u128 * bin_step as u128 * 10)
        .checked_mul(10u128.checked_pow(power).ok_or(Abort::Math)?).ok_or(Abort::Math)?;
    let p = DlmmParams {
        swap_for_y, fee_on_input, support_lo, base_rate,
        vfc: u32_at(pair, off::VFC).ok_or(Abort::Layout)? as u128,
        bin_step,
        max_va: u32_at(pair, off::MAX_VA).ok_or(Abort::Layout)? as u64,
        v_ref: v_ref as u64, idx_ref, active,
        min_bin: i32_at(pair, off::MIN_BIN_ID).ok_or(Abort::Layout)?,
        max_bin: i32_at(pair, off::MAX_BIN_ID).ok_or(Abort::Layout)?,
    };
    let fee_one = Fx::from_u64(FEE_PRECISION as u64);
    let lf = LocatorFees {
        base: Fx::from_u128(p.base_rate).div(fee_one),
        var_k: Fx::from_u128(p.vfc).div(Fx::from_u64(100_000_000_000)).div(fee_one),
        cap: Fx::from_u64(MAX_FEE_RATE as u64).div(fee_one),
        step: Fx::from_u64(BPS).div(Fx::from_u64(BPS + bin_step as u64)),
    };
    Ok(DlmmLeg { p, pair, arrays: set, n_arrays: arrays.len() as u8, lf, budget: NO_BUDGET })
}

/// One bin with something to give in the swap direction: [market-making amount, processed limit orders, open
/// limit orders] (the fill order) and the stored Q64.64 price.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BinRef { pub id: i32, pub layers: [u64; 3], pub price: u128 }

impl BinRef {
    pub fn total(&self) -> u128 { self.layers.iter().map(|&l| l as u128).sum() }
}

/// Why a walk ended
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum End {
    /// the venue cannot go further: every larger input fails on chain
    Cap,
    /// the leg's walk budget: the venue would continue, the crate does not look
    Budget,
}

/// The swap's bin order: active bin, onward in the swap direction inside its array, then the next array WITH
/// LIQUIDITY by the pair's bitmap (shift_active_bin_if_empty_gap), and so on. `next` stops at the first CAP
/// condition (after which every larger input fails on chain) or when the budget is spent. A walker is a plain value:
/// a copy resumes from the same place.
#[derive(Clone, Copy, Debug)]
pub struct BinWalker<'l, 'a> {
    leg: &'l DlmmLeg<'a>,
    active: i32,
    /// the current array: (index, slot in the leg's array list)
    arr: Option<(i64, u8)>,
    advance: bool,
    end: Option<End>,
    /// bins read, and bins with liquidity yielded
    pub walked: u16,
    pub liquid: u16,
}

impl<'l, 'a> BinWalker<'l, 'a> {
    pub fn next_bin(&mut self) -> Option<BinRef> { self.next().ok() }

    /// the next bin with liquidity, or why there is none
    #[inline(never)]
    pub fn next(&mut self) -> Result<BinRef, End> {
        if let Some(e) = self.end { return Err(e); }
        let r = self.step();
        if let Err(e) = r { self.end = Some(e); }
        r
    }

    fn step(&mut self) -> Result<BinRef, End> {
        let leg = self.leg;
        let p = &leg.p;
        loop {
            if self.advance {
                // advance_active_bin: the pair's own bounds
                let next = if p.swap_for_y { self.active.checked_sub(1) } else { self.active.checked_add(1) }.ok_or(End::Cap)?;
                if next < p.min_bin || next > p.max_bin { return Err(End::Cap); }
                self.active = next;
                self.advance = false;
            }
            // the current array while the active bin is inside it (no division per bin), else the next one by the bitmap
            let inside = |i: i64| { let lo = i * BINS_PER_ARRAY; (lo..lo + BINS_PER_ARRAY).contains(&(self.active as i64)) };
            let slot = match self.arr {
                Some((i, s)) if inside(i) => s,
                _ => {
                    let ai = array_index(self.active);
                    let found = leg.bitmap_next(ai, p.swap_for_y).ok_or(End::Cap)?;
                    if found != ai {
                        self.active = i32::try_from(if p.swap_for_y { found * BINS_PER_ARRAY + 69 } else { found * BINS_PER_ARRAY }).map_err(|_| End::Cap)?;
                    }
                    let s = leg.slot(found).ok_or(End::Cap)?;
                    self.arr = Some((found, s));
                    s
                }
            };
            // the budget counts every bin read (a bin of a visited array, empty or not); a CAP condition comes first
            if self.walked >= leg.budget { return Err(End::Budget); }
            self.walked += 1;
            self.advance = true;
            let (idx, data) = leg.arrays.get(slot as usize).copied().ok_or(End::Cap)?;
            let k = usize::try_from(self.active as i64 - idx * BINS_PER_ARRAY).map_err(|_| End::Cap)?;
            let o = off::A_BINS + k * off::BIN_SIZE;
            let mm = u64_at(data, o + if p.swap_for_y { off::B_AMOUNT_Y } else { off::B_AMOUNT_X }).ok_or(End::Cap)?;
            let ask = u8_at(data, o + off::B_ASK_SIDE).ok_or(End::Cap)?;
            let (lp, lo) = if p.support_lo && ((p.swap_for_y && ask == 0) || (!p.swap_for_y && ask != 0)) {
                (u64_at(data, o + off::B_PROCESSED_REMAINING).ok_or(End::Cap)?, u64_at(data, o + off::B_OPEN_ORDER).ok_or(End::Cap)?)
            } else { (0, 0) };
            if mm != 0 || lp != 0 || lo != 0 {
                self.liquid = self.liquid.saturating_add(1);
                return Ok(BinRef { id: self.active, layers: [mm, lp, lo], price: u128_at(data, o + off::B_PRICE).ok_or(End::Cap)? });
            }
        }
    }
}

/// A resumable exact swap state: the walk before its next bin, every earlier bin drained whole. Valid for any input
/// `x ≥ reach` (exactly those inputs drain every earlier bin and still have input left for the next one).
#[derive(Clone, Copy, Debug)]
pub struct Cursor<'l, 'a> {
    w: BinWalker<'l, 'a>,
    /// input taken by the drained bins, and the user's output from them
    pub used: u64,
    pub out: u64,
    /// the smallest input this state applies to
    pub reach: u64,
}

impl Cursor<'_, '_> {
    /// bins read to get here
    pub fn bins(&self) -> u16 { self.w.walked }
}

/// One bin as the locator sees it: the exact input that drains it and the user's exact output from it; the bin's id
/// and price give [`DlmmLeg::bound_after`] (computed only when the non-concavity guard needs it).
#[derive(Clone, Copy, Debug)]
pub struct BinPiece { pub drain_in: u64, pub out: u64, pub id: i32, pub price: u128 }

/// An evaluation that would walk further than allowed from its state
#[derive(Clone, Copy, Debug)]
struct Far;

/// The last fee rate computed (the rate depends on the bin only through the accumulator, which saturates at max_va)
#[derive(Clone, Copy, Debug, Default)]
pub struct RateMemo(Option<(u64, u128)>);

/// A drained bin: the input it takes (`d`), the smallest input that drains it with input left over (`d_next`), and
/// the user's output (`out`)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Drain { d: u128, d_next: u128, out: u128 }

impl<'a> DlmmLeg<'a> {
    /// the leg with a walk budget of `bins` bins read (the descriptor's `max_bins`)
    pub fn with_budget(mut self, bins: u16) -> Self { self.budget = bins; self }
    pub fn budget(&self) -> u16 { self.budget }

    pub fn walker(&self) -> BinWalker<'_, 'a> {
        BinWalker { leg: self, active: self.p.active, arr: None, advance: false, end: None, walked: 0, liquid: 0 }
    }

    /// the swap's initial state (valid for every input)
    pub fn start(&self) -> Cursor<'_, 'a> { Cursor { w: self.walker(), used: 0, out: 0, reach: 0 } }

    fn slot(&self, index: i64) -> Option<u8> {
        self.arrays.iter().take(self.n_arrays as usize).position(|a| a.0 == index).map(|i| i as u8)
    }

    /// next array index with liquidity from `start` (inclusive) in the swap direction; None outside the pair's
    /// own bitmap (indices −512..=511) or when no bit is set
    pub fn bitmap_next(&self, start: i64, down: bool) -> Option<i64> {
        if !(-512..=511).contains(&start) { return None; }
        let pos = (start + 512) as u32;
        let (mut w, b) = (pos / 64, pos % 64);
        let word = |w: u32| u64_at(self.pair, off::BITMAP + 8 * w as usize);
        if down {
            let mut m = word(w)? & if b == 63 { u64::MAX } else { (1u64 << (b + 1)) - 1 };
            loop {
                if m != 0 { return Some((w * 64 + 63 - m.leading_zeros()) as i64 - 512); }
                if w == 0 { return None; }
                w -= 1;
                m = word(w)?;
            }
        } else {
            let mut m = word(w)? & (u64::MAX << b);
            loop {
                if m != 0 { return Some((w * 64 + m.trailing_zeros()) as i64 - 512); }
                if w == 15 { return None; }
                w += 1;
                m = word(w)?;
            }
        }
    }

    fn va(&self, id: i32) -> Option<u64> {
        let d = (self.p.idx_ref as i64 - id as i64).unsigned_abs();
        Some(self.p.v_ref.checked_add(d.checked_mul(BPS)?)?.min(self.p.max_va))
    }

    /// the bin's fee rate out of 1e9: min(base + ⌈vfc·(va·bin_step)²/1e11⌉, 1e8); None = the program errors
    pub fn rate(&self, id: i32) -> Option<u128> { self.rate_va(self.va(id)?) }

    fn rate_va(&self, va: u64) -> Option<u128> {
        let var = if self.p.vfc == 0 { 0 } else {
            // va ≤ max_va < 2^32 and bin_step < 2^16, so t < 2^48, t² < 2^96 and vfc·t² < 2^128: three widening
            // 64×64 products, no checked u128 multiply (the general path keeps the checks for any other input)
            let t = (va as u128).checked_mul(self.p.bin_step as u128)?;
            let num = if t >> 48 == 0 && self.p.vfc >> 32 == 0 {
                let sq = (t as u64 as u128).wrapping_mul(t as u64 as u128);
                let (hi, lo) = ((sq >> 64) as u64 as u128, sq as u64 as u128);
                let v = self.p.vfc as u64 as u128;
                (hi.wrapping_mul(v) << 64).checked_add(lo.wrapping_mul(v))?
            } else {
                self.p.vfc.checked_mul(t.checked_pow(2)?)?
            };
            div(num.checked_add(99_999_999_999)?, 100_000_000_000)?
        };
        Some(self.p.base_rate.checked_add(var)?.min(MAX_FEE_RATE))
    }

    fn rate_memo(&self, id: i32, m: &mut RateMemo) -> Option<u128> {
        let va = self.va(id)?;
        if let Some((v, r)) = m.0 { if v == va { return Some(r); } }
        let r = self.rate_va(va)?;
        m.0 = Some((va, r));
        Some(r)
    }

    /// the rate for an accumulator value, as a fraction (locator only): min(base + vfc·(va·bin_step)²/1e11, 1e8)/1e9
    fn rate_fx_va(&self, va: u64) -> Fx {
        let t = Fx::from_u128(va as u128 * self.p.bin_step as u128);
        self.lf.base.add(self.lf.var_k.mul(t).mul(t)).min(self.lf.cap)
    }

    /// get_amount_in: the input that takes `l` out of the bin (rounded up); None when it does not fit u64 (the
    /// program errors)
    fn amount_in(&self, l: u64, price: u128) -> Option<u128> {
        let r = if self.p.swap_for_y { shl64_div(l as u128, price, true) } else { mul_shr64(l as u128, price, true) }?;
        if r > u64::MAX as u128 { None } else { Some(r) }
    }

    /// get_amount_out for `rem` of input (rounded down)
    fn amount_out(&self, rem: u128, price: u128) -> Option<u128> {
        if self.p.swap_for_y { mul_shr64(rem, price, false) } else { shl64_div(rem, price, false) }
    }

    /// One bin, `input` left: (input used, output to the user). The layers fill in order; a layer's
    /// `get_amount_in` is computed only once the swap reaches it with input left (as the program does).
    fn bin_quote(&self, input: u128, bin: &BinRef, rate: u128) -> Result<(u128, u128), QuoteErr> {
        let math = QuoteErr::Abort(Abort::Math);
        let fee_in = if self.p.fee_on_input { ceil_div(wmul(input, rate).ok_or(math)?, FEE_PRECISION).ok_or(math)? } else { 0 };
        let excl = input.checked_sub(fee_in).ok_or(math)?;
        let mut rem = excl;
        let mut out = 0u128;
        for &l in bin.layers.iter() {
            if l == 0 { continue; }
            if rem == 0 { break; }
            let need = self.amount_in(l, bin.price).ok_or(QuoteErr::TooLarge)?;
            if rem >= need {
                out += l as u128;
                rem -= need;
            } else {
                out += self.amount_out(rem, bin.price).ok_or(QuoteErr::TooLarge)?;
                rem = 0;
                break;
            }
        }
        let used = if rem > 0 {
            // the bin is drained: only what drains it (plus its fee) is taken
            let e = excl - rem;
            if self.p.fee_on_input { e + ceil_div(wmul(e, rate).ok_or(math)?, FEE_PRECISION - rate).ok_or(math)? } else { e }
        } else { input };
        let out_user = if self.p.fee_on_input { out } else { out - ceil_div(wmul(out, rate).ok_or(math)?, FEE_PRECISION).ok_or(math)? };
        Ok((used, out_user))
    }

    /// The bin drained whole (fee on input: d = ⌈S·1e9/(1e9 − r)⌉, d_next = ⌈(S+1)·1e9/(1e9 − r)⌉; fee on output:
    /// d = S, d_next = S + 1; S = Σ ⌈get_amount_in(layer)⌉). An input ≥ d_next takes the drained path of
    /// `bin_quote` and uses exactly d; an input in [d, d_next) is used whole and still empties the bin. None when a
    /// layer's input does not fit u64 (the program errors on reaching it).
    fn drain(&self, bin: &BinRef, rate: u128) -> Option<Drain> {
        let (mut s, mut lsum) = (0u128, 0u128);
        for &l in bin.layers.iter().filter(|&&l| l > 0) {
            s += self.amount_in(l, bin.price)?;
            lsum += l as u128;
        }
        if self.p.fee_on_input {
            let k = FEE_PRECISION.checked_sub(rate)?;
            Some(Drain { d: s + ceil_div(wmul(s, rate)?, k)?, d_next: ceil_div(wmul(s + 1, FEE_PRECISION)?, k)?, out: lsum })
        } else {
            Some(Drain { d: s, d_next: s + 1, out: lsum - ceil_div(wmul(lsum, rate)?, FEE_PRECISION)? })
        }
    }

    /// Advance a cursor over its next bin with liquidity, in place: the bin as a locator piece, and whether some u64
    /// input gets past it (if not, the cursor is left before the bin). Err: the walk ends here (a CAP condition, the
    /// budget, a zero price or a layer whose input does not fit u64); the cursor is unchanged. On Ok, `at` (if given)
    /// receives the state positioned AT the bin (the empty bins before it already passed): an exact quote resumed from
    /// it reads this bin first.
    #[inline(never)]
    pub fn advance<'l>(&'l self, c: &mut Cursor<'l, 'a>, memo: &mut RateMemo, at: Option<&mut Cursor<'l, 'a>>) -> Result<(BinPiece, bool), End> {
        let mut w = c.w;
        let bin = w.next()?;
        if let Some(at) = at {
            let mut b = w;
            b.advance = false;
            b.walked = b.walked.saturating_sub(1);
            b.liquid = b.liquid.saturating_sub(1);
            *at = Cursor { w: b, ..*c };
        }
        if bin.price == 0 { return Err(End::Cap); }
        let rate = self.rate_memo(bin.id, memo).ok_or(End::Cap)?;
        let dr = self.drain(&bin, rate).ok_or(End::Cap)?;
        let fits = |v: u128| if v <= u64::MAX as u128 { Some(v as u64) } else { None };
        let used = fits(c.used as u128 + dr.d).ok_or(End::Cap)?;
        let out = fits(c.out as u128 + dr.out).ok_or(End::Cap)?;
        let piece = BinPiece { drain_in: dr.d as u64, out: dr.out as u64, id: bin.id, price: bin.price };
        match fits(c.used as u128 + dr.d_next) {
            Some(reach) => { *c = Cursor { w, used, out, reach }; Ok((piece, true)) }
            None => Ok((piece, false)),
        }
    }

    /// An upper bound on the slope (output per input) of every bin after bin `id` (stored price `price`) in the walk:
    /// the price at least one bin step worse, the fee rate at least the lowest the walk can still reach.
    #[inline(never)]
    pub fn bound_after(&self, id: i32, price: u128) -> Fx {
        let p = Fx::from_u128(price);
        let pf = if self.p.swap_for_y { p.shl(-64) } else { Fx::ONE.shl(64).div(p) };
        let nb = id.saturating_add(if self.p.swap_for_y { -1 } else { 1 });
        let ahead = if self.p.swap_for_y { self.p.idx_ref <= nb } else { self.p.idx_ref >= nb };
        let va_min = if ahead { self.p.v_ref.min(self.p.max_va) } else { self.va(nb).unwrap_or(self.p.max_va) };
        Fx::ONE.sub(self.rate_fx_va(va_min)).mul(pf).mul(self.lf.step)
    }

    /// The exact quote (swap2, exact in). TooLarge once the walk reaches a CAP condition with input left; Budget
    /// once it reaches the leg's walk budget with input left.
    pub fn quote(&self, x: u64) -> Result<Quote, QuoteErr> { self.quote_from(&self.start(), x) }

    /// The exact quote, resumed from `c` when `x` reaches it (else from the start): equal to [`quote`](Self::quote).
    pub fn quote_from(&self, c: &Cursor<'_, 'a>, x: u64) -> Result<Quote, QuoteErr> {
        match self.swap_from(c, x, u16::MAX) { Ok(r) => r.map(|r| r.0), Err(Far) => Err(QuoteErr::Budget) }
    }

    /// [`quote_from`](Self::quote_from) only when it ends within `near` bins read after the state it resumes from;
    /// None otherwise (the planner's bounded evaluations: DESIGN.md §4.7).
    pub fn quote_near(&self, c: &Cursor<'_, 'a>, x: u64, near: u16) -> Option<Result<Quote, QuoteErr>> {
        self.swap_from(c, x, near).ok().map(|r| r.map(|r| r.0))
    }

    /// The exact swap from a state: the quote and the bins it read in all; `Far` once it would read more than
    /// `max_walk` bins past the state.
    #[inline(never)]
    fn swap_from(&self, c: &Cursor<'_, 'a>, x: u64, max_walk: u16) -> Result<Result<(Quote, u16), QuoteErr>, Far> {
        if x == 0 { return Ok(Err(QuoteErr::ZeroOut)); }
        let start = self.start();
        let c = if x >= c.reach { c } else { &start };
        let mut w = c.w;
        let last = c.w.walked.saturating_add(max_walk);
        let mut left = (x - c.used) as u128;
        let mut out = c.out as u128;
        let mut memo = RateMemo::default();
        Ok(loop {
            if left == 0 { break Ok(()); }
            let bin = match w.next() {
                Ok(b) => b,
                Err(End::Cap) => break Err(QuoteErr::TooLarge),
                Err(End::Budget) => break Err(QuoteErr::Budget),
            };
            if w.walked > last { return Err(Far); }
            if bin.price == 0 { break Err(QuoteErr::Abort(Abort::Dlmm(DlmmWhy::ZeroPrice))); }
            let Some(rate) = self.rate_memo(bin.id, &mut memo) else { break Err(QuoteErr::TooLarge) };
            let (used, o) = match self.bin_quote(left, &bin, rate) { Ok(v) => v, Err(e) => break Err(e) };
            let Some(l) = left.checked_sub(used) else { break Err(QuoteErr::Abort(Abort::Math)) };
            left = l;
            out += o;
        }.and_then(|()| {
            let out = u64::try_from(out).map_err(|_| QuoteErr::TooLarge)?;
            if out == 0 { return Err(QuoteErr::ZeroOut); }
            Ok((Quote { out, spent: x }, w.walked))
        }))
    }

    /// The largest input that quotes Ok within the walk (budget included): `reach − 1` of the state after the last
    /// bin (exact; inputs from there on need a further bin). When the walk ends at a layer whose input does not fit
    /// u64 the value is a lower bound. 0: no bin with liquidity.
    pub fn cap_in(&self) -> Option<u64> {
        let mut c = self.start();
        let mut memo = RateMemo::default();
        loop {
            match self.advance(&mut c, &mut memo, None) {
                Ok((_, true)) => {}
                Ok((_, false)) => return Some(u64::MAX),
                Err(_) => return Some(c.reach.saturating_sub(1)),
            }
        }
    }

    /// Bins the exact swap of `x` reads (no budget; empty bins inside a visited array included): what the engine puts
    /// in the descriptor's `max_bins` for the leg's largest input (DESIGN.md §4.3). None when the venue cannot fill
    /// `x`.
    pub fn bins_for(&self, x: u64) -> Option<u16> {
        let leg = self.with_budget(NO_BUDGET);
        leg.swap_from(&leg.start(), x, u16::MAX).ok().and_then(|r| r.ok()).map(|r| r.1)
    }
}

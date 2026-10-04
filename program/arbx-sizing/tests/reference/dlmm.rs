//! READ-ONLY COPY of /home/moiz/arbed/arbx/src/venues/dlmm.rs (2026-10-04) for the differential tests.
//! Adapted only where the crate context is missing: imports point at `super` (tests/reference/mod.rs), the
//! third-party-swap decoders (which need the engine's PendingSwap/PoolMeta) and the in-file tests are dropped.
//! The maths is byte-for-byte the engine's.
#![allow(dead_code, clippy::all)]
use super::{ceil_div, i32_at, i64_at, u128_at, u16_at, u32_at, u64_at};
use std::collections::HashMap;

pub const BINS_PER_ARRAY: i32 = 70;
const FEE_PRECISION: u128 = 1_000_000_000;
const MAX_FEE_RATE: u128 = 100_000_000;
const BPS_MAX: u128 = 10_000;

pub fn array_index(bin: i32) -> i64 { (bin as i64).div_euclid(BINS_PER_ARRAY as i64) }


#[derive(Debug, Clone, Copy)]
pub struct FeeParams {
    pub base_factor: u128,
    pub filter_period: i64,
    pub decay_period: i64,
    pub reduction_factor: u128,
    pub variable_fee_control: u128,
    pub max_va: u128,
    pub power: u32,
    pub va: u128,
    pub v_ref: u128,
    pub idx_ref: i32,
    pub last_ts: i64,
    pub bin_step: u128,
}

pub fn fee_params(p: &[u8]) -> Option<FeeParams> {
    Some(FeeParams {
        base_factor: u16_at(p, 8)? as u128, filter_period: u16_at(p, 10)? as i64, decay_period: u16_at(p, 12)? as i64,
        reduction_factor: u16_at(p, 14)? as u128, variable_fee_control: u32_at(p, 16)? as u128, max_va: u32_at(p, 20)? as u128,
        power: *p.get(34)? as u32, va: u32_at(p, 40)? as u128, v_ref: u32_at(p, 44)? as u128, idx_ref: i32_at(p, 48)?,
        last_ts: i64_at(p, 56)?, bin_step: u16_at(p, 80)? as u128,
    })
}

impl FeeParams {
    pub fn base_rate(&self) -> u128 { self.base_factor * self.bin_step * 10 * 10u128.pow(self.power) }
    fn variable_rate(&self, va: u128) -> u128 {
        if self.variable_fee_control == 0 { return 0; }
        let vb = va * self.bin_step;
        ceil_div(self.variable_fee_control * vb * vb, 100_000_000_000)
    }
    fn total_rate(&self, va: u128) -> u128 { (self.base_rate() + self.variable_rate(va)).min(MAX_FEE_RATE) }
    /// update_references, once per swap
    fn refs(&self, active: i32, now: i64) -> (u128, i32) {
        let elapsed = now - self.last_ts;
        if elapsed >= self.filter_period {
            let r = if elapsed < self.decay_period { self.va * self.reduction_factor / BPS_MAX } else { 0 };
            (r, active)
        } else { (self.v_ref, self.idx_ref) }
    }
    fn accumulator(&self, v_ref: u128, idx_ref: i32, bin: i32) -> u128 {
        (v_ref + (idx_ref as i64 - bin as i64).unsigned_abs() as u128 * BPS_MAX).min(self.max_va)
    }
}

/// (a * p) >> 64, a: u64-sized, p: Q64.64, without overflow; `up` rounds up
fn mul_shr(a: u128, p: u128, up: bool) -> Option<u128> {
    let (ph, pl) = (p >> 64, p & u64::MAX as u128);
    let lo = a.checked_mul(pl)?;
    let hi = a.checked_mul(ph)?;
    let mut r = hi.checked_add(lo >> 64)?;
    if up && lo & u64::MAX as u128 != 0 { r += 1; }
    Some(r)
}
/// (a << 64) / p, a: u64-sized
fn shl_div(a: u128, p: u128, up: bool) -> Option<u128> {
    if p == 0 || a > u64::MAX as u128 { return None; }
    let n = a << 64;
    let (q, r) = (n / p, n % p);
    Some(if up && r != 0 { q + 1 } else { q })
}

/// A pair's live view: the lb_pair bytes, the loaded bin arrays (raw), and predicted changes on top.
pub struct View<'a> {
    pub pair: &'a [u8],
    pub arrays: &'a HashMap<i64, &'a [u8]>,
    /// predicted bins (bin id -> (amount_x, amount_y)) and active id, after earlier pending swaps
    pub over: Option<&'a Overlay>,
}

/// Predicted state after earlier pending swaps: bins they changed, where the active bin ended, and the volatility
/// state they left (the program writes the last accumulator, the references it used, and the swap time).
#[derive(Debug, Clone, Default)]
pub struct Overlay { pub active: Option<i32>, pub bins: HashMap<i32, (u64, u64)>, pub vol: Option<(u128, u128, i32, i64)> }

impl<'a> View<'a> {
    pub fn active(&self) -> Option<i32> { self.over.and_then(|o| o.active).or_else(|| i32_at(self.pair, 76)) }
    /// (amount_x, amount_y, price) of a bin, or None when its array isn't loaded
    fn bin(&self, id: i32) -> Option<(u64, u64, u128)> {
        let arr = self.arrays.get(&array_index(id))?;
        let k = (id as i64 - array_index(id) * BINS_PER_ARRAY as i64) as usize;
        let o = 56 + k * 144;
        let price = u128_at(arr, o + 16)?;
        if let Some((x, y)) = self.over.and_then(|ov| ov.bins.get(&id)) { return Some((*x, *y, price)); }
        Some((u64_at(arr, o)?, u64_at(arr, o + 8)?, price))
    }
}

#[derive(Debug, Clone)]
pub struct DlmmOut { pub out: u64, pub end_active: i32, pub crossed: u32, pub changed: Vec<(i32, u64, u64)>, pub vol: (u128, u128, i32, i64) }

/// Reasons a DLMM quote can't be trusted
#[derive(Debug, Clone, Copy, PartialEq)]
pub enum Why { ArrayNotLoaded, NoLiquidity, Math, Disabled }

/// Exact-in walk. Returns the output, where the active bin ends, how many bins with liquidity were touched, and the
/// new (x, y) of every bin it changed (for the prediction overlay).
/// `collect`: record the changed bins (the trigger's prediction); probes during sizing skip it.
pub fn quote(v: &View, zero_for_one: bool, amount_in: u64, now: i64, collect: bool) -> Result<DlmmOut, Why> {
    if v.pair.len() < 904 || v.pair[82] != 0 { return Err(Why::Disabled); }
    let mut fp = fee_params(v.pair).ok_or(Why::Math)?;
    if let Some((va, r, i, ts)) = v.over.and_then(|o| o.vol) { fp.va = va; fp.v_ref = r; fp.idx_ref = i; fp.last_ts = ts; }
    let mut bin = v.active().ok_or(Why::Math)?;
    let (v_ref, idx_ref) = fp.refs(bin, now);
    let mut last_va = fp.va;
    let mut remaining = amount_in as u128;
    let mut out: u128 = 0;
    let mut crossed = 0u32;
    let mut changed = Vec::new();
    for _ in 0..600 {
        if remaining == 0 { break; }
        let (x, y, price) = v.bin(bin).ok_or(Why::ArrayNotLoaded)?;
        let avail = if zero_for_one { y } else { x } as u128;
        if avail > 0 {
            crossed += 1;
            last_va = fp.accumulator(v_ref, idx_ref, bin);
            let rate = fp.total_rate(last_va);
            let max_in = if zero_for_one { shl_div(avail, price, true) } else { mul_shr(avail, price, true) }.ok_or(Why::Math)?;
            let max_fee = ceil_div(max_in * rate, FEE_PRECISION - rate);
            if remaining >= max_in + max_fee {
                out += avail;
                remaining -= max_in + max_fee;
                // drained: the output side empties, the input side gains the net input
                let (nx, ny) = if zero_for_one { (x as u128 + max_in, 0) } else { (0, y as u128 + max_in) };
                if collect { changed.push((bin, nx.min(u64::MAX as u128) as u64, ny.min(u64::MAX as u128) as u64)); }
            } else {
                let fee = ceil_div(remaining * rate, FEE_PRECISION);
                let in_after = remaining - fee;
                let got = if zero_for_one { mul_shr(in_after, price, false) } else { shl_div(in_after, price, false) }.ok_or(Why::Math)?.min(avail);
                out += got;
                let (nx, ny) = if zero_for_one { (x as u128 + in_after, y as u128 - got) } else { (x as u128 - got, y as u128 + in_after) };
                if collect { changed.push((bin, nx.min(u64::MAX as u128) as u64, ny.min(u64::MAX as u128) as u64)); }
                remaining = 0;
                break;
            }
        }
        bin += if zero_for_one { -1 } else { 1 };
    }
    if remaining > 0 { return Err(Why::NoLiquidity); }
    if out == 0 || out > u64::MAX as u128 { return Err(Why::Math); }
    Ok(DlmmOut { out: out as u64, end_active: bin, crossed, changed, vol: (last_va, v_ref, idx_ref, now) })
}

/// Apply a quote's changes to an overlay (prediction).
pub fn apply(over: &mut Overlay, q: &DlmmOut) {
    for (b, x, y) in &q.changed { over.bins.insert(*b, (*x, *y)); }
    over.active = Some(q.end_active);
    over.vol = Some(q.vol);
}


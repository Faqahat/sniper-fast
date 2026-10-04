//! The sizing block and the per-leg sizing descriptors (DESIGN.md §4.2, §4.3): parsing (no allocation) and, with the
//! `encode` feature, encoding.
//!
//! ```text
//! sz_flags u8 | min_size u32 | engine_amount u64 | [lamport_offset i32 if LAMPORTS] | [max_iters u8 if SEARCH]
//!   | [n_pairs u8, n × (buy u8, sell u8) if BASKET]
//! per leg: kd u8 | [bump u8 if PumpSwap] | [max_bins u8 if DLMM] | [n_pos u8, n_pos × u8 if EXPLICIT_POS]
//! kd: bits 0-3 kind (1..=6) | bit 4 dir (0 = token0 / x / a / base is the input) | bits 5-7 n_bin_arrays (DLMM 1..=5)
//! ```
use crate::error::{DescCode, DescError};
use crate::layout;

pub const MAX_PAIRS: usize = 3;
pub const MAX_SIZED_LEGS: usize = 6;
pub const MAX_SEARCH_ITERS: u8 = 24;
pub const MAX_BIN_ARRAYS: u8 = 5;

/// Leg kind = venue + instruction (DESIGN.md §1.2)
#[repr(u8)]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind {
    /// PumpSwap buy_exact_quote_in (quote in, base out)
    PumpBuy = 1,
    /// PumpSwap sell (base in, quote out)
    PumpSell = 2,
    /// Raydium CPMM swap_base_input
    RayCpmm = 3,
    /// Raydium AMM v4 swap_base_in_v2
    RayAmmV4 = 4,
    /// Meteora DLMM swap2 (exact in)
    Dlmm = 5,
    /// Meteora DAMM v2 swap (exact in)
    DammV2 = 6,
}

impl Kind {
    pub const fn from_u8(v: u8) -> Option<Kind> {
        match v {
            1 => Some(Kind::PumpBuy), 2 => Some(Kind::PumpSell), 3 => Some(Kind::RayCpmm), 4 => Some(Kind::RayAmmV4),
            5 => Some(Kind::Dlmm), 6 => Some(Kind::DammV2), _ => None,
        }
    }
    /// the venue program the leg must invoke
    pub const fn program(self) -> &'static [u8; 32] {
        match self {
            Kind::PumpBuy | Kind::PumpSell => &layout::PUMPSWAP,
            Kind::RayCpmm => &layout::RAY_CPMM,
            Kind::RayAmmV4 => &layout::RAY_AMM_V4,
            Kind::Dlmm => &layout::DLMM,
            Kind::DammV2 => &layout::DAMM_V2,
        }
    }
    /// index into arbx-exec's ALLOWLIST_B58
    pub const fn allowlist_index(self) -> u8 {
        match self {
            Kind::PumpBuy | Kind::PumpSell => layout::ALLOW_PUMPSWAP,
            Kind::RayCpmm => layout::ALLOW_CPMM,
            Kind::RayAmmV4 => layout::ALLOW_AMM_V4,
            Kind::Dlmm => layout::ALLOW_DLMM,
            Kind::DammV2 => layout::ALLOW_DAMM_V2,
        }
    }
    /// entries of an explicit position list (DLMM: lb_pair, mint_x, mint_y, first bin array)
    pub const fn n_positions(self) -> usize { layout::default_positions(self).len() }
    pub const fn has_bump(self) -> bool { matches!(self, Kind::PumpBuy | Kind::PumpSell) }
    /// DLMM legs carry their walk budget (`max_bins`)
    pub const fn has_budget(self) -> bool { matches!(self, Kind::Dlmm) }
    /// the venue program's amount offset in the leg data (for the shell's cross-check)
    pub const fn amount_offset(self) -> u8 { if matches!(self, Kind::RayAmmV4) { 1 } else { 8 } }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LegDesc {
    pub kind: Kind,
    /// dir bit 0: token0 / x / a / base is the input (PumpSell: true; PumpBuy: false)
    pub base_or_token0_in: bool,
    /// DLMM: bin arrays passed (1..=5); other kinds 0
    pub n_bin_arrays: u8,
    /// PumpSwap: the pool-authority PDA bump (0 = the pool is not canonical); other kinds 0
    pub pump_bump: u8,
    /// DLMM: the walk budget, in bins with liquidity (1..=255). The engine sets it from its own quote of the leg's
    /// largest input (the cap; `DlmmLeg::bins_for`), so the engine's amount is always inside it (DESIGN.md §4.3).
    /// Other kinds 0.
    pub max_bins: u8,
    /// EXPLICIT_POS: positions in the kind's order (first `kind.n_positions()` entries used)
    pub positions: Option<[u8; 8]>,
}

impl LegDesc {
    pub const fn new(kind: Kind, base_or_token0_in: bool) -> LegDesc {
        LegDesc { kind, base_or_token0_in, n_bin_arrays: 0, pump_bump: 0, max_bins: 0, positions: None }
    }
    pub const fn placeholder() -> LegDesc { LegDesc::new(Kind::RayAmmV4, true) }
    /// the descriptor's first byte
    pub fn kd(&self) -> u8 { self.kind as u8 | if self.base_or_token0_in { 0 } else { 0x10 } | ((self.n_bin_arrays & 0x07) << 5) }
}

/// sz_flags
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct SzFlags(pub u8);

impl SzFlags {
    /// revert (ERR_SIZING_UNSUPPORTED) instead of falling back to the engine's amount
    pub const STRICT: u8 = 0x01;
    /// revert (ERR_SIZING_NO_PROFIT) before any CPI when no candidate clears min_profit
    pub const EARLY_ABORT: u8 = 0x02;
    /// plan and log, but execute pair 0 at the engine's amount
    pub const SHADOW: u8 = 0x04;
    /// allow the golden-section fallback where the analytic model refuses
    pub const SEARCH: u8 = 0x08;
    /// each leg descriptor carries its positions
    pub const EXPLICIT_POS: u8 = 0x10;
    /// the block carries `lamport_offset` (i32): the lamport delta of the executed legs the guard counts with
    /// COUNT_LAMPORTS, for the NoProfit verdict (DESIGN.md §4.2)
    pub const LAMPORTS: u8 = 0x20;
    pub const KNOWN: u8 = 0x3F;
    pub const fn strict(self) -> bool { self.0 & Self::STRICT != 0 }
    pub const fn early_abort(self) -> bool { self.0 & Self::EARLY_ABORT != 0 }
    pub const fn shadow(self) -> bool { self.0 & Self::SHADOW != 0 }
    pub const fn search(self) -> bool { self.0 & Self::SEARCH != 0 }
    pub const fn explicit_pos(self) -> bool { self.0 & Self::EXPLICIT_POS != 0 }
    pub const fn lamports(self) -> bool { self.0 & Self::LAMPORTS != 0 }
}

/// The parsed sizing block
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct SizingBlock {
    pub flags: SzFlags,
    pub min_size: u32,
    /// `e`: the size the engine would have sent; the fallback and the "never worse" reference
    pub engine_amount: u64,
    /// LAMPORTS only (else 0): the modeled lamport delta of the executed legs (rent of accounts a venue creates is
    /// negative), added to the quote profit for the NoProfit verdict as the guard does under COUNT_LAMPORTS
    pub lamport_offset: i32,
    /// golden-section iterations (SEARCH only; else 0)
    pub max_iters: u8,
    pub pairs: [(u8, u8); MAX_PAIRS],
    pub n_pairs: u8,
    pub legs: [LegDesc; MAX_SIZED_LEGS],
    pub n_legs: u8,
    /// BASKET (pairs explicit) or plain SELF_SIZE (pair (0, 1))
    pub basket: bool,
}

impl SizingBlock {
    pub fn pairs(&self) -> &[(u8, u8)] { self.pairs.get(..self.n_pairs as usize).unwrap_or(&[]) }
    pub fn legs(&self) -> &[LegDesc] { self.legs.get(..self.n_legs as usize).unwrap_or(&[]) }
}

struct Rd<'d> { d: &'d [u8], o: usize }
impl<'d> Rd<'d> {
    fn u8(&mut self) -> Result<u8, DescError> {
        let v = *self.d.get(self.o).ok_or(DescError::block(DescCode::Truncated))?;
        self.o += 1;
        Ok(v)
    }
    fn arr<const N: usize>(&mut self) -> Result<[u8; N], DescError> {
        let v = crate::math::rd::<N>(self.d, self.o).ok_or(DescError::block(DescCode::Truncated))?;
        self.o += N;
        Ok(v)
    }
}

/// Parse the sizing block at `data[at..]` for a route of `n_legs` legs (BASKET iff `basket`) whose instruction
/// amount_in is `amount_in`. Returns the block and its length in bytes (arbx-exec adds it to the leg-data start).
/// Every rule of DESIGN.md §4.2/§4.3 is checked here; a violation is a DescError (ERR_SIZING_DESC).
pub fn parse_block(data: &[u8], at: usize, n_legs: usize, basket: bool, amount_in: u64) -> Result<(SizingBlock, usize), DescError> {
    if (!basket && n_legs != 2) || (basket && !(2..=MAX_SIZED_LEGS).contains(&n_legs)) {
        return Err(DescError::block(DescCode::NLegs));
    }
    let mut r = Rd { d: data, o: at };
    let flags = SzFlags(r.u8()?);
    if flags.0 & !SzFlags::KNOWN != 0 { return Err(DescError::block(DescCode::Flags)); }
    let min_size = u32::from_le_bytes(r.arr::<4>()?);
    let engine_amount = u64::from_le_bytes(r.arr::<8>()?);
    if min_size == 0 || min_size as u64 > engine_amount { return Err(DescError::block(DescCode::MinSize)); }
    if engine_amount > amount_in { return Err(DescError::block(DescCode::EngineAmount)); }
    let lamport_offset = if flags.lamports() { i32::from_le_bytes(r.arr::<4>()?) } else { 0 };
    let max_iters = if flags.search() {
        let m = r.u8()?;
        if m > MAX_SEARCH_ITERS { return Err(DescError::block(DescCode::MaxIters)); }
        m
    } else { 0 };
    let mut pairs = [(0u8, 0u8); MAX_PAIRS];
    let n_pairs;
    // role per leg: 0 unused, 1 buy, 2 sell
    let mut role = [0u8; MAX_SIZED_LEGS];
    if basket {
        n_pairs = r.u8()?;
        if n_pairs == 0 || n_pairs as usize > MAX_PAIRS { return Err(DescError::block(DescCode::PairCount)); }
        for i in 0..n_pairs as usize {
            let (b, s) = (r.u8()?, r.u8()?);
            if b as usize >= n_legs || s as usize >= n_legs { return Err(DescError::new(DescCode::PairIndex, i as u8, 0xFF)); }
            if b == s { return Err(DescError::new(DescCode::PairSameLeg, i as u8, 0xFF)); }
            if pairs.get(..i).unwrap_or(&[]).contains(&(b, s)) { return Err(DescError::new(DescCode::PairDuplicate, i as u8, 0xFF)); }
            if let Some(p) = pairs.get_mut(i) { *p = (b, s); }
            for (leg, want) in [(b, 1u8), (s, 2u8)] {
                let slot = role.get_mut(leg as usize).ok_or(DescError::new(DescCode::PairIndex, i as u8, 0xFF))?;
                if *slot != 0 && *slot != want { return Err(DescError::new(DescCode::LegRole, leg, 0xFF)); }
                *slot = want;
            }
        }
        if let Some(l) = role.get(..n_legs).unwrap_or(&[]).iter().position(|&x| x == 0) {
            return Err(DescError::new(DescCode::LegUnused, l as u8, 0xFF));
        }
    } else {
        n_pairs = 1;
        pairs[0] = (0, 1);
    }
    let mut legs = [LegDesc::placeholder(); MAX_SIZED_LEGS];
    for (i, leg) in legs.iter_mut().enumerate().take(n_legs) {
        let kd = r.u8()?;
        let kind = Kind::from_u8(kd & 0x0F).ok_or(DescError::new(DescCode::Kind, i as u8, 0xFF))?;
        let token0_in = kd & 0x10 == 0;
        let nba = kd >> 5;
        match kind {
            Kind::PumpBuy if token0_in => return Err(DescError::new(DescCode::Dir, i as u8, 0xFF)),
            Kind::PumpSell if !token0_in => return Err(DescError::new(DescCode::Dir, i as u8, 0xFF)),
            _ => {}
        }
        if (kind == Kind::Dlmm && !(1..=MAX_BIN_ARRAYS).contains(&nba)) || (kind != Kind::Dlmm && nba != 0) {
            return Err(DescError::new(DescCode::BinArrays, i as u8, 0xFF));
        }
        let pump_bump = if kind.has_bump() { r.u8()? } else { 0 };
        let max_bins = if kind.has_budget() {
            let b = r.u8()?;
            if b == 0 { return Err(DescError::new(DescCode::BinBudget, i as u8, 0xFF)); }
            b
        } else { 0 };
        let positions = if flags.explicit_pos() {
            let n = r.u8()? as usize;
            if n != kind.n_positions() { return Err(DescError::new(DescCode::PosCount, i as u8, 0xFF)); }
            let mut p = [0u8; 8];
            for slot in p.iter_mut().take(n) { *slot = r.u8()?; }
            Some(p)
        } else { None };
        *leg = LegDesc { kind, base_or_token0_in: token0_in, n_bin_arrays: nba, pump_bump, max_bins, positions };
        // the expanded DLMM array positions must stay within u8
        layout::positions(leg).map_err(|e| DescError::new(e.code, i as u8, 0xFF))?;
    }
    let block = SizingBlock { flags, min_size, engine_amount, lamport_offset, max_iters, pairs, n_pairs, legs, n_legs: n_legs as u8, basket };
    Ok((block, r.o - at))
}

/// Encode a block (the inverse of `parse_block` for every block it accepts).
#[cfg(feature = "encode")]
pub fn encode_block(b: &SizingBlock, out: &mut alloc::vec::Vec<u8>) {
    out.push(b.flags.0);
    out.extend_from_slice(&b.min_size.to_le_bytes());
    out.extend_from_slice(&b.engine_amount.to_le_bytes());
    if b.flags.lamports() { out.extend_from_slice(&b.lamport_offset.to_le_bytes()); }
    if b.flags.search() { out.push(b.max_iters); }
    if b.basket {
        out.push(b.n_pairs);
        for &(x, y) in b.pairs() { out.push(x); out.push(y); }
    }
    for l in b.legs() {
        out.push(l.kd());
        if l.kind.has_bump() { out.push(l.pump_bump); }
        if l.kind.has_budget() { out.push(l.max_bins); }
        if b.flags.explicit_pos() {
            let n = l.kind.n_positions();
            out.push(n as u8);
            let p = l.positions.unwrap_or_else(|| {
                let mut d = [0u8; 8];
                for (s, v) in d.iter_mut().zip(layout::default_positions(l.kind)) { *s = *v; }
                d
            });
            out.extend_from_slice(p.get(..n).unwrap_or(&[]));
        }
    }
}

/// Byte length of an encoded block (no allocation; for the builder's size budget)
pub fn block_len(b: &SizingBlock) -> usize {
    let mut n = 1 + 4 + 8;
    if b.flags.lamports() { n += 4; }
    if b.flags.search() { n += 1; }
    if b.basket { n += 1 + 2 * b.n_pairs as usize; }
    for l in b.legs() {
        n += 1;
        if l.kind.has_bump() { n += 1; }
        if l.kind.has_budget() { n += 1; }
        if b.flags.explicit_pos() { n += 1 + l.kind.n_positions(); }
    }
    n
}

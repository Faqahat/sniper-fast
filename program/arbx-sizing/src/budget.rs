//! The static CU bound of [`plan`](crate::plan) (DESIGN.md §4.7; REVIEW.md F4). `sol_remaining_compute_units` is not
//! active on mainnet, so the program cannot stop itself; instead every piece of the plan's work is bounded by the
//! sizing block alone, and the engine adds [`cu_bound`] to the transaction's CU limit:
//!
//! * each leg is parsed once;
//! * per pair the locator reads at most `max_bins` bins of each DLMM leg (the walk budget) and evaluates its model
//!   per bin;
//! * every candidate evaluation resumes from an exact state the locator recorded and reads at most
//!   `NEAR_BINS` DLMM bins past it, every step-back at most `NEAR_BACK` (at most `MAX_BACK` step-backs per plan);
//! * only the engine's amount `e` (pair 0) may walk a DLMM leg from its active bin, up to the walk budget;
//! * the golden-section search (SEARCH, never over a DLMM leg) makes at most `max_iters + 4` round trips.
//!
//! The per-unit costs are measured on SBF (sbf-check/cu-runner: platform-tools v1.57, sbpfv3, overflow checks on)
//! and rounded up; the runner checks every measured route against this bound. The bound counts the sizing work only
//! (not the shell's account borrows, nor the venue CPIs).
use crate::desc::{Kind, LegDesc, SizingBlock};
use crate::opt::MAX_OPTIMA;
use crate::plan::{MAX_BACK, NEAR_BACK, NEAR_BINS};

/// Per-unit CU costs (measured, rounded up)
pub mod cost {
    /// block parse, plan setup, the decision and the AXZ1 record
    pub const FIXED: u64 = 3_000;
    /// parsing one leg: checks, field reads, mint scans (PumpSwap: the canonical-PDA syscall and the fee tiers)
    pub const PARSE_PUMP: u64 = 5_000;
    pub const PARSE_CPMM: u64 = 1_200;
    pub const PARSE_AMM: u64 = 800;
    pub const PARSE_DLMM: u64 = 1_200;
    pub const PARSE_DLMM_ARRAY: u64 = 300;
    pub const PARSE_DAMM: u64 = 3_000;
    /// per pair: the models and the closed form, or the walk's setup
    pub const LOCATE: u64 = 3_500;
    /// per DLMM bin the locator reads (exact drain, model piece, marginal test)
    pub const LOCATE_BIN: u64 = 2_300;
    /// one exact quote of a constant-product leg
    pub const EVAL_PUMP: u64 = 1_200;
    pub const EVAL_CPMM: u64 = 800;
    pub const EVAL_AMM: u64 = 700;
    pub const EVAL_DAMM: u64 = 7_000;
    /// one exact DLMM quote: its setup, plus EXACT_BIN per bin it reads
    pub const EVAL_DLMM: u64 = 1_500;
    pub const EXACT_BIN: u64 = 1_500;
}

/// DLMM bins a walk over this leg may read (0 for the other kinds)
fn walk(l: &LegDesc) -> u64 { if l.kind == Kind::Dlmm { l.max_bins as u64 } else { 0 } }

/// CU to check and parse one leg
pub fn parse_cu(l: &LegDesc) -> u64 {
    use cost::*;
    match l.kind {
        Kind::PumpBuy | Kind::PumpSell => PARSE_PUMP,
        Kind::RayCpmm => PARSE_CPMM,
        Kind::RayAmmV4 => PARSE_AMM,
        Kind::Dlmm => PARSE_DLMM + PARSE_DLMM_ARRAY * l.n_bin_arrays as u64,
        Kind::DammV2 => PARSE_DAMM,
    }
}

/// CU of one exact quote of the leg that reads at most `bins` DLMM bins
pub fn eval_cu(l: &LegDesc, bins: u64) -> u64 {
    use cost::*;
    match l.kind {
        Kind::PumpBuy | Kind::PumpSell => EVAL_PUMP,
        Kind::RayCpmm => EVAL_CPMM,
        Kind::RayAmmV4 => EVAL_AMM,
        Kind::Dlmm => EVAL_DLMM + EXACT_BIN * bins.min(walk(l)),
        Kind::DammV2 => EVAL_DAMM,
    }
}

/// An upper bound on the CU `plan` spends for this block (any account state): what the engine adds to the
/// transaction's CU limit for sizing.
pub fn cu_bound(b: &SizingBlock) -> u64 {
    use cost::*;
    let legs = b.legs();
    let leg = |i: u8| legs.get(i as usize).copied().unwrap_or(LegDesc::placeholder());
    let n_cand = if b.basket { 1 } else { MAX_OPTIMA as u64 };
    let mut cu = FIXED + legs.iter().map(parse_cu).sum::<u64>();
    let mut back = 0u64;
    for (k, &(bi, si)) in b.pairs().iter().enumerate() {
        let (lb, ls) = (leg(bi), leg(si));
        let rt = |bins: u64| eval_cu(&lb, bins) + eval_cu(&ls, bins);
        cu += LOCATE + LOCATE_BIN * (walk(&lb) + walk(&ls));
        cu += n_cand * rt(NEAR_BINS as u64);
        // the engine's amount: a full walk of each DLMM leg, up to its budget
        if k == 0 { cu += eval_cu(&lb, walk(&lb)) + eval_cu(&ls, walk(&ls)); }
        back = back.max(rt(NEAR_BACK as u64));
        // the golden-section search where the model refuses (SEARCH; no DLMM leg)
        if b.flags.search() && lb.kind != Kind::Dlmm && ls.kind != Kind::Dlmm { cu += (b.max_iters as u64 + 4) * rt(0); }
    }
    cu + MAX_BACK as u64 * back
}

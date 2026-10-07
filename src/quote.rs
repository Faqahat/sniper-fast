//! Venue quoting (PLAN-ADDENDUM WP-16): every quote the engine makes is `arbx-sizing`'s, the exact integer maths
//! proven against the real venue binaries (program/venue-harness: 0 mismatches in 46,589 comparisons) and the same code
//! arbx-exec's on-chain sizing runs. Route pricing and sizing (`engine.rs::price_route`), the opportunity's legs
//! (`route_in`), the budget caps (`record_caps`), the hint checks and the accuracy monitor's predictions all go through
//! [`leg`] and [`Leg::quote`]; `src/venues` keeps only the account and instruction decoders (the engine's own maths
//! before WP-16 is kept, tests only, in `venues::legacy` as the differential reference).
//!
//! A leg is one pool in one direction, parsed by the crate's per-venue `parse` from the store's account bytes (the
//! keys and owners were checked at boot, `pools.rs`). Every state the crate refuses is a skip with its own reason
//! ([`Why::reason`], decisions.jsonl `routes[].reason`, MEASUREMENT A.1; counters `reject_<reason>`, A.7):
//! - a parse-time refusal (`Abort`: a layout the crate does not accept, a Token-2022 transfer fee or hook, a PumpSwap
//!   pool whose held-back quote exceeds its vault, a DAMM v2 rate limiter in force on our leg, ...) is `sz_<abort>`;
//! - a size past a DLMM leg's walk budget (`QuoteErr::Budget`) is `sz_budget`: the budget is the transaction's CU limit
//!   ([`DLMM_BUDGET_ALONE`], [`DLMM_BUDGET_SHARED`]);
//! - a PumpSwap sell past the quote the pool can pay out net of its held-back amounts is `sz_pump_held_capacity`;
//! - a size the venue cannot fill or that pays nothing keeps A.1's `unquotable_*` (DLMM: `unquotable_dlmm_array` when
//!   the walk needs a bin array we do not follow or name, else `unquotable_dlmm_liquidity`).
//!
//! Sizing ([`best`]): the configured ladder's rungs, then, where a rung makes money, the crate locator's optima (the
//! closed form for two constant-product legs, the marginal walk over DLMM bins), each evaluated exactly; the best exact
//! profit wins, never above the ladder's top rung (the size cap: 4.2 SOL in Stage 0). Where no rung makes money the
//! best rung is the route's record, as before WP-16 (it is below `min_profit` whatever its size). The ladder stops at
//! the first rung whose profit falls below the one before (the round trip's profit is concave in its size: WP-16
//! review F7).
//!
//! Assumption: the crate is built with the engine's release profile (no overflow checks), unlike its SBF and test
//! builds; it does every operation checked or bounded by construction ("no panics on any input", DESIGN.md §5.4, fuzzed
//! by its own suite), so the arithmetic is the same either way.
use crate::store::Acct;
use crate::tx::Pk;
use crate::venues::{PoolMeta, Venue, WSOL};
use arbx_sizing as sz;
use sz::error::{AmmWhy, ClmmWhy, CpmmWhy, DammWhy, DlmmWhy, PumpWhy, WhirlWhy};
use sz::venue::{ammv4, cpmm, dammv2, dlmm, orca_whirlpool, pumpswap, raydium_clmm};
use sz::{Abort, AnyLeg, Fx, Quote, QuoteErr};

/// A DLMM leg of a route may read this many bins (empty ones inside a visited array included) when the other leg is
/// not DLMM, and [`DLMM_BUDGET_SHARED`] when both are: the venue's own swap costs ≈5.45k CU per bin (`Venue::leg_cu`)
/// and the transaction is capped at 1.4M CU, so with the engine's CU estimate ((29k + legs)·1.1) a route past these
/// budgets could not execute (PumpSwap + 200 DLMM bins ≈ 1.39M; DLMM + DLMM at 100 bins each ≈ 1.33M)
pub const DLMM_BUDGET_ALONE: u16 = 200;
pub const DLMM_BUDGET_SHARED: u16 = 100;
/// the most bin arrays a DLMM leg names (the builder's rule, `build.rs::dlmm_leg`; the crate's `MAX_ARRAYS`)
pub const DLMM_MAX_ARRAYS: usize = dlmm::MAX_ARRAYS;

/// PLAN-ADDENDUM WP-21: the walk budget of a Raydium CLMM or Orca Whirlpool leg of a route, in swap steps: half its
/// route's DLMM budget (`Use::Route::dlmm_budget`: 200 alone, 100 when both legs walk). A step costs at most 10k CU on the
/// deployed binaries (Raydium 64k + 10k per step, Orca 48k + 10k: DESIGN.md §2.8, §2.9) against a DLMM bin's 5.45k, so
/// with the engine's CU estimate ((29k + legs)·1.1) a CLMM leg at 100 steps beside a CPMM-family leg asks ≈1.31M, two
/// walking legs at their shared budgets ≈1.30M: under the 1.4M transaction limit
pub fn clmm_budget(dlmm_budget: u16) -> u16 { dlmm_budget / 2 }

/// The bin arrays a route's DLMM leg may use (PLAN WP-06 item 6, the DLMM cap), the one rule the quote and the builder
/// share: the active bin's array `c`, then onward in the swap's direction while the next one is held (`have`: followed,
/// read, usable), contiguous, at most `DLMM_MAX_ARRAYS`. The quote walks only these (a size past them is
/// `unquotable_dlmm_array`, PLAN's `dlmm_cap`; the size search steps back below it, decisions `dlmm_cap_bound`), and the
/// builder names a prefix of them (`build::dlmm_arrays`: as far as the quote's end bin, plus one buffer array). Empty
/// when the active array is not held
pub fn dlmm_window(c: i64, zfo: bool, have: &dyn Fn(i64) -> bool) -> Vec<i64> {
    let step = if zfo { -1 } else { 1 };
    let mut out = Vec::with_capacity(DLMM_MAX_ARRAYS);
    let mut i = c;
    while out.len() < DLMM_MAX_ARRAYS && have(i) { out.push(i); i += step; }
    out
}

/// The Clock a quote is priced under (the chain's Clock sysvar: DLMM and DAMM v2 fees, CPMM / AMM v4 open times)
pub fn clock(slot: u64, unix_timestamp: i64) -> sz::Clock { sz::Clock { slot, unix_timestamp, epoch: 0 } }

/// Whose swap a leg prices
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Use {
    /// one leg of our route, as the builder sends it: the crate's on-chain refusals apply (a DAMM v2 rate limiter in
    /// force refuses: our 14-account leg does not pass the instructions sysvar, 6049 at every size), DLMM bin arrays
    /// as the builder names them (from the active one, contiguous, at most 5) and the walk budget of the CU limit
    /// (PLAN-ADDENDUM WP-21: a Raydium CLMM or Orca Whirlpool leg walks at most `clmm_budget(dlmm_budget)` swap steps)
    Route { dlmm_budget: u16 },
    /// a third party's decoded swap (hints, the accuracy monitor), priced as the venue executes it: a DAMM v2 rate
    /// limiter's fee is priced (that swap carries the sysvar or fails on its own), any followed DLMM bin array in the
    /// swap's direction may be used, no walk budget
    Third,
}

/// Why a leg or a size is not quoted. [`Why::reason`] is the A.1 reason
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Why {
    /// an account the leg needs is not in the store (A.1 `unquotable_cp`, `unquotable_dlmm_array`, `unquotable_damm`)
    Missing(Venue),
    /// the venue cannot fill the size or pays nothing (A.1 `unquotable_cp`, `unquotable_damm`, `unquotable_dlmm_liquidity`)
    Unquotable(Venue),
    /// DLMM: the walk needs a bin array we do not follow or would not name (A.1 `unquotable_dlmm_array`)
    DlmmArray,
    /// PLAN-ADDENDUM WP-21, Raydium CLMM and Orca Whirlpool: the walk needs a tick array we do not follow or would not
    /// name, or one of Orca's three is not known (held, or known not to exist) (`unquotable_clmm_array`)
    ClmmArray,
    /// PLAN-ADDENDUM WP-21: the venue's program was upgraded since the binary the port was proven on (the state stream
    /// delivered its programdata with another deploy slot; DESIGN.md §6.5): not priced (`venue_upgraded`)
    VenueUpgraded,
    /// arbx-sizing DESIGN.md §7 item 9 (PumpSwap, Raydium CPMM, DLMM, DAMM v2; the CLMM venues have the crate's own
    /// `sz_clmm_mint_*` / `sz_whirl_mint_*`): a Token-2022 mint of the pool is paused (Pausable: every transfer fails) or
    /// creates its accounts frozen (DefaultAccountState Frozen: the account the route creates for the mid token is frozen).
    /// Either fails the swap at every size (`mint_paused`, `mint_frozen`)
    MintPaused,
    MintFrozen,
    /// a PumpSwap sell past the quote the pool pays out net of its held-back amounts (u64 @271, @279): the program
    /// fails 6063 above it (`sz_pump_held_capacity`)
    PumpHeldCapacity,
    /// DLMM: past the leg's walk budget, the transaction's CU limit (`sz_budget`)
    Budget,
    /// PumpSwap with a quote mint other than WSOL: not traded (`pump_quote_not_sol`, as before WP-16)
    PumpQuoteNotSol,
    /// Raydium AMM v4 with a Token-2022 side: its v2 swap takes SPL Token only (`sz_ammv4_token_2022`)
    AmmV4Token2022,
    /// a state the crate does not model (`sz_<abort>`)
    Abort(Abort),
}

impl Why {
    pub fn reason(self) -> &'static str {
        match self {
            Why::Missing(v) | Why::Unquotable(v) => match (self, v) {
                (Why::Missing(_), Venue::Dlmm) => "unquotable_dlmm_array",
                (_, Venue::Dlmm) => "unquotable_dlmm_liquidity",
                (_, Venue::DammV2) => "unquotable_damm",
                (Why::Missing(_), Venue::RayClmm | Venue::Whirlpool) => "unquotable_clmm_array",
                (_, Venue::RayClmm | Venue::Whirlpool) => "unquotable_clmm",
                _ => "unquotable_cp",
            },
            Why::DlmmArray => "unquotable_dlmm_array",
            Why::ClmmArray => "unquotable_clmm_array",
            Why::VenueUpgraded => "venue_upgraded",
            Why::MintPaused => "mint_paused",
            Why::MintFrozen => "mint_frozen",
            Why::PumpHeldCapacity => "sz_pump_held_capacity",
            Why::Budget => "sz_budget",
            Why::PumpQuoteNotSol => "pump_quote_not_sol",
            Why::AmmV4Token2022 => "sz_ammv4_token_2022",
            Why::Abort(a) => abort_reason(a),
        }
    }
    /// a parse-time refusal of the whole leg (every size), as opposed to one size's
    pub fn whole_leg(self) -> bool { !matches!(self, Why::Unquotable(_) | Why::DlmmArray | Why::ClmmArray | Why::PumpHeldCapacity | Why::Budget) }
}

/// The reason of every state arbx-sizing refuses (`Abort`), prefixed `sz_` (MEASUREMENT A.1, WP-16)
pub fn abort_reason(a: Abort) -> &'static str {
    match a {
        Abort::Unsupported => "sz_unsupported",
        Abort::Layout => "sz_layout",
        Abort::TransferFee => "sz_transfer_fee",
        Abort::TransferHook => "sz_transfer_hook",
        Abort::Math => "sz_math",
        Abort::ModelRefused => "sz_model_refused",
        Abort::Pump(w) => match w {
            PumpWhy::Mayhem => "sz_pump_mayhem", PumpWhy::Cashback => "sz_pump_cashback", PumpWhy::Disabled => "sz_pump_disabled",
            PumpWhy::Virtual => "sz_pump_virtual", PumpWhy::FeeTotal => "sz_pump_fee_total", PumpWhy::FeeConfig => "sz_pump_fee_config",
            PumpWhy::EmptyReserves => "sz_pump_empty", PumpWhy::HeldExceedsVault => "sz_pump_held_exceeds_vault",
            PumpWhy::UnknownTail => "sz_pump_unknown_tail",
        },
        Abort::Cpmm(w) => match w {
            CpmmWhy::SwapDisabled => "sz_cpmm_swap_disabled", CpmmWhy::NotOpen => "sz_cpmm_not_open", CpmmWhy::OwedExceedsVault => "sz_cpmm_owed_exceeds_vault",
            CpmmWhy::CreatorFeeOn => "sz_cpmm_creator_fee_on", CpmmWhy::Fee => "sz_cpmm_fee", CpmmWhy::EmptyReserves => "sz_cpmm_empty",
        },
        Abort::Amm(w) => match w {
            AmmWhy::Status => "sz_ammv4_status", AmmWhy::PnlExceedsVault => "sz_ammv4_pnl_exceeds_vault", AmmWhy::Fee => "sz_ammv4_fee",
            AmmWhy::EmptyReserves => "sz_ammv4_empty",
        },
        Abort::Dlmm(w) => match w {
            DlmmWhy::Status => "sz_dlmm_status", DlmmWhy::NotActive => "sz_dlmm_not_active", DlmmWhy::FunctionType => "sz_dlmm_function_type",
            DlmmWhy::CollectFeeMode => "sz_dlmm_collect_fee_mode", DlmmWhy::ZeroPrice => "sz_dlmm_zero_price", DlmmWhy::ActivationType => "sz_dlmm_activation_type",
        },
        Abort::Damm(w) => match w {
            DammWhy::Status => "sz_damm_status", DammWhy::NotActive => "sz_damm_not_active", DammWhy::RateLimiter => "sz_damm_rate_limiter",
            DammWhy::Mode => "sz_damm_mode", DammWhy::Fee100 => "sz_damm_fee100", DammWhy::Liquidity => "sz_damm_liquidity", DammWhy::Range => "sz_damm_range",
            DammWhy::Time => "sz_damm_time",
        },
        // PLAN-ADDENDUM WP-21 (DESIGN.md §2.8, §2.9, §9.0 item 1): each fails the venue's swap_v2 at every size
        Abort::Clmm(w) => match w {
            ClmmWhy::Status => "sz_clmm_status", ClmmWhy::NotOpen => "sz_clmm_not_open", ClmmWhy::Fee => "sz_clmm_fee",
            ClmmWhy::BitmapExtension => "sz_clmm_bitmap_extension", ClmmWhy::NoLiquidity => "sz_clmm_no_liquidity", ClmmWhy::TickArrays => "sz_clmm_tick_arrays",
            ClmmWhy::PriceLimit => "sz_clmm_price_limit", ClmmWhy::State => "sz_clmm_state", ClmmWhy::MintPaused => "sz_clmm_mint_paused",
            ClmmWhy::MintFrozen => "sz_clmm_mint_frozen",
        },
        Abort::Whirl(w) => match w {
            WhirlWhy::TradeNotEnabled => "sz_whirl_trade_not_enabled", WhirlWhy::Timestamp => "sz_whirl_timestamp", WhirlWhy::TickArrays => "sz_whirl_tick_arrays",
            WhirlWhy::PriceLimit => "sz_whirl_price_limit", WhirlWhy::State => "sz_whirl_state", WhirlWhy::MintPaused => "sz_whirl_mint_paused",
            WhirlWhy::MintFrozen => "sz_whirl_mint_frozen",
        },
    }
}

/// One reason this module gives, with its counters (MEASUREMENT A.7): `reject_<reason>` (a route's), `trigger_<reason>`
/// (a hint's check, `Engine::hint_check`), `probe_<reason>` (`Engine::probe_routes`) and `pred_<reason>` (the accuracy
/// monitor: a swap it does not score for this reason). WP-16 review F10: every path counts the crate's own reason
#[derive(Debug)]
pub struct Reason { pub reason: &'static str, pub reject: &'static str, pub trigger: &'static str, pub probe: &'static str, pub pred: &'static str }

macro_rules! reasons {
    ($($r:literal),* $(,)?) => {
        /// Every reason this module gives, with its counters
        pub const REASONS: &[Reason] = &[$(Reason { reason: $r, reject: concat!("reject_", $r), trigger: concat!("trigger_", $r),
            probe: concat!("probe_", $r), pred: concat!("pred_", $r) }),*];
    };
}

reasons!(
    "sz_pump_held_capacity", "sz_budget", "pump_quote_not_sol", "sz_ammv4_token_2022", "venue_upgraded", "mint_paused", "mint_frozen",
    "sz_unsupported", "sz_layout", "sz_transfer_fee", "sz_transfer_hook", "sz_math", "sz_model_refused",
    "sz_pump_mayhem", "sz_pump_cashback", "sz_pump_disabled", "sz_pump_virtual", "sz_pump_fee_total", "sz_pump_fee_config", "sz_pump_empty",
    "sz_pump_held_exceeds_vault", "sz_pump_unknown_tail",
    "sz_cpmm_swap_disabled", "sz_cpmm_not_open", "sz_cpmm_owed_exceeds_vault", "sz_cpmm_creator_fee_on", "sz_cpmm_fee", "sz_cpmm_empty",
    "sz_ammv4_status", "sz_ammv4_pnl_exceeds_vault", "sz_ammv4_fee", "sz_ammv4_empty",
    "sz_dlmm_status", "sz_dlmm_not_active", "sz_dlmm_function_type", "sz_dlmm_collect_fee_mode", "sz_dlmm_zero_price", "sz_dlmm_activation_type",
    "sz_damm_status", "sz_damm_not_active", "sz_damm_rate_limiter", "sz_damm_mode", "sz_damm_fee100", "sz_damm_liquidity", "sz_damm_range",
    "sz_damm_time",
    "sz_clmm_status", "sz_clmm_not_open", "sz_clmm_fee", "sz_clmm_bitmap_extension", "sz_clmm_no_liquidity", "sz_clmm_tick_arrays",
    "sz_clmm_price_limit", "sz_clmm_state", "sz_clmm_mint_paused", "sz_clmm_mint_frozen",
    "sz_whirl_trade_not_enabled", "sz_whirl_timestamp", "sz_whirl_tick_arrays", "sz_whirl_price_limit", "sz_whirl_state", "sz_whirl_mint_paused",
    "sz_whirl_mint_frozen",
);

/// The counters of `reason` when it is one of this module's (the crate's refusal states and the routes we do not trade)
pub fn reason_row(reason: &str) -> Option<&'static Reason> { REASONS.iter().find(|x| x.reason == reason) }

impl Why {
    /// The row of a reason the crate (or our route rules) gives, None for "an account is missing" and "the venue cannot
    /// fill it" (A.1's `unquotable_*`, counted generically: `trigger_unquotable`, `probe_unquotable`, `pred_unquotable`)
    pub fn crate_reason(self) -> Option<&'static Reason> {
        match self { Why::Missing(_) | Why::Unquotable(_) | Why::DlmmArray | Why::ClmmArray => None, w => reason_row(w.reason()) }
    }
}

/// Where a leg's accounts come from: the store's current versions (pricing) or one set of versions (the accuracy
/// monitor's pre-state)
pub struct Src<'s, 'a> {
    pub get: &'s dyn Fn(&Pk) -> Option<&'a Acct>,
    /// the DLMM pool's followed bin arrays (index, key)
    pub arrays: &'s [(i64, Pk)],
    /// whether a followed bin array may be used (the engine leaves out pending ones, those on a contested slot and
    /// those not read again since a reconnection)
    pub usable: &'s dyn Fn(i64) -> bool,
    pub clock: sz::Clock,
}

/// One pool in one direction, parsed by arbx-sizing
#[derive(Clone, Copy, Debug)]
pub struct Leg<'a> {
    pub venue: Venue,
    /// spending token 0 (the program's own order: PumpSwap base, CPMM mint0, AMM v4 coin, DLMM x, DAMM v2 a)
    pub zfo: bool,
    pub any: AnyLeg<'a>,
    /// what a size the venue cannot fill means here (a TooLarge)
    too_large: Why,
}

/// What one quote is: the crate's exact amounts, and for DLMM the walk (CU: bins with liquidity taken from; the
/// builder: the bin the swap ends on, where it names bin arrays up to)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Quoted { pub out: u64, pub spent: u64, pub crossed: u32, pub end: Option<i32>, pub walked: u16 }

fn token_amount(a: &Acct) -> Option<u64> { if a.data.len() >= 72 { Some(u64::from_le_bytes(a.data[64..72].try_into().ok()?)) } else { None } }

/// The Token-2022 extension scan of a mint (DESIGN.md §2.0): a nonzero transfer fee (older or newer) or a transfer
/// hook with a program set is refused. An SPL mint (82 bytes, or a Token-2022 one without extensions) passes
fn mint_ok(d: &[u8]) -> Result<(), Why> {
    if d.len() > 82 { sz::token::scan_extensions(d).map_err(Why::Abort)?; }
    Ok(())
}

/// arbx-sizing DESIGN.md §7 item 9: a paused or default-frozen Token-2022 mint (`sz::token::mint_blocked`) fails every
/// swap of the pool's (the older five venues; the CLMM venues refuse it with the crate's own reasons)
fn mint_usable(d: &[u8]) -> Result<(), Why> {
    match sz::token::mint_blocked(d) { Some(sz::token::MintBlock::Paused) => Err(Why::MintPaused), Some(sz::token::MintBlock::DefaultFrozen) => Err(Why::MintFrozen), None => Ok(()) }
}

/// The pool's Token-2022 mints must be in `src` and scanned clean (`pools.rs` follows them as parts of the pool);
/// an SPL Token side needs no account. Not paused or default-frozen either (DESIGN.md §7 item 9; the CLMM venues check
/// it with their own reasons, `clmm_mints_blocked`)
fn mints_ok(m: &PoolMeta, src: &Src) -> Result<(), Why> {
    for (mint, prog) in [(&m.t0, &m.t0_prog), (&m.t1, &m.t1_prog)] {
        if *prog == *crate::pda::TOKEN_2022 {
            let d = &(src.get)(mint).ok_or(Why::Missing(m.venue))?.data;
            mint_ok(d)?;
            if !m.venue.is_clmm() { mint_usable(d)?; }
        }
    }
    Ok(())
}

/// PLAN-ADDENDUM WP-21: a paused (Pausable) or default-frozen (DefaultAccountState Frozen) Token-2022 mint of a CLMM
/// pool fails its swap_v2 at every size (DESIGN.md §2.0): the venue's own refusal (`sz_clmm_mint_*`, `sz_whirl_mint_*`)
fn clmm_mints_blocked(m: &PoolMeta, src: &Src) -> Result<(), Why> {
    for (mint, prog) in [(&m.t0, &m.t0_prog), (&m.t1, &m.t1_prog)] {
        if *prog != *crate::pda::TOKEN_2022 { continue; }
        let Some(b) = (src.get)(mint).and_then(|a| sz::token::mint_blocked(&a.data)) else { continue };
        let paused = b == sz::token::MintBlock::Paused;
        return Err(Why::Abort(match (m.venue, paused) {
            (Venue::RayClmm, true) => Abort::Clmm(ClmmWhy::MintPaused),
            (Venue::RayClmm, false) => Abort::Clmm(ClmmWhy::MintFrozen),
            (_, true) => Abort::Whirl(WhirlWhy::MintPaused),
            (_, false) => Abort::Whirl(WhirlWhy::MintFrozen),
        }));
    }
    Ok(())
}

/// a crate refusal of a CLMM leg: "the first tick array the swap needs is not passed" is ours (the arrays we hold and
/// name), not the pool's (`unquotable_clmm_array`); every other one is the venue's (`sz_*`)
fn clmm_abort(a: Abort) -> Why {
    match a { Abort::Clmm(ClmmWhy::TickArrays) | Abort::Whirl(WhirlWhy::TickArrays) => Why::ClmmArray, a => Why::Abort(a) }
}

/// Orca Whirlpool: the Clock a quote is priced under, never before the pool's own stamps (its reward update, the oracle's
/// reference update and major-swap stamp: the program refuses an earlier Clock, `Whirl(Timestamp)`). The slot the route
/// targets is later than the slots that wrote them; a Clock sysvar version that has not caught up with the pool's write
/// is raised to them (DESIGN.md §9.0 item 4)
fn whirl_clock(c: sz::Clock, pool: &[u8], oracle: Option<&[u8]>) -> sz::Clock {
    let stamp = |d: &[u8], o: usize| sz::math::u64_at(d, o).map_or(0, |v| v.min(i64::MAX as u64) as i64);
    let mut ts = c.unix_timestamp.max(stamp(pool, orca_whirlpool::off::REWARD_LAST_UPDATED));
    if let Some(o) = oracle { ts = ts.max(stamp(o, orca_whirlpool::off::O_VARIABLES)).max(stamp(o, orca_whirlpool::off::O_VARIABLES + 8)); }
    sz::Clock { unix_timestamp: ts, ..c }
}

/// the most tick arrays a Raydium CLMM leg is quoted with: the followed set holds at most 13 (`venues::clmm`)
const RAY_HELD_MAX: usize = 16;

/// Parse pool `m` for a swap spending its token 0 (`zfo`) or token 1, from `src`
pub fn leg<'a>(m: &PoolMeta, zfo: bool, src: &Src<'_, 'a>, use_: Use) -> Result<Leg<'a>, Why> {
    let miss = Why::Missing(m.venue);
    let get = |k: &Pk| (src.get)(k).ok_or(miss);
    let route = matches!(use_, Use::Route { .. });
    let unq = Why::Unquotable(m.venue);
    let (any, too_large) = match m.venue {
        Venue::RayAmmV4 => {
            if route && (m.t0_prog != *crate::pda::TOKEN_PROGRAM || m.t1_prog != *crate::pda::TOKEN_PROGRAM) { return Err(Why::AmmV4Token2022); }
            let pool = get(&m.pool)?;
            let (c, p) = (token_amount(get(&m.vault0)?).ok_or(miss)?, token_amount(get(&m.vault1)?).ok_or(miss)?);
            (AnyLeg::Amm(ammv4::parse(&pool.data, c, p, zfo, src.clock.unix_timestamp).map_err(Why::Abort)?), unq)
        }
        Venue::RayCpmm => {
            let pool = get(&m.pool)?;
            let cfg = get(m.extra.first().ok_or(miss)?)?;
            let (v0, v1) = (token_amount(get(&m.vault0)?).ok_or(miss)?, token_amount(get(&m.vault1)?).ok_or(miss)?);
            mints_ok(m, src)?;
            (AnyLeg::Cpmm(cpmm::parse(&pool.data, &cfg.data, v0, v1, zfo, src.clock.unix_timestamp).map_err(Why::Abort)?), unq)
        }
        Venue::PumpSwap => {
            if route && m.t1 != *WSOL { return Err(Why::PumpQuoteNotSol); }
            let pool = get(&m.pool)?;
            let global = get(&sz::layout::PUMP_GLOBAL_CONFIG)?;
            let fee_cfg = get(&sz::layout::PUMP_FEE_CONFIG)?;
            let base_mint = get(m.extra.first().ok_or(miss)?)?;
            mint_ok(&base_mint.data)?;
            mint_usable(&base_mint.data)?;
            if m.t1_prog == *crate::pda::TOKEN_2022 { mint_ok(&get(&m.t1)?.data)?; mint_usable(&get(&m.t1)?.data)?; }
            let supply = sz::math::u64_at(&base_mint.data, 36).ok_or(miss)?;
            let quote_mint = sz::math::key_at(&pool.data, pumpswap::off::QUOTE_MINT).copied().ok_or(Why::Abort(Abort::Layout))?;
            let (b, q) = (token_amount(get(&m.vault0)?).ok_or(miss)?, token_amount(get(&m.vault1)?).ok_or(miss)?);
            let leg = pumpswap::parse(&pool.data, &global.data, &fee_cfg.data, supply, &quote_mint, b, q, zfo, m.flag).map_err(Why::Abort)?;
            // a sell's capacity is the quote net of the held-back amounts (REVIEW.md F1)
            let held = zfo && leg.quote < q;
            (AnyLeg::Pump(leg), if held { Why::PumpHeldCapacity } else { unq })
        }
        Venue::Dlmm => {
            let pair = get(&m.pool)?;
            mints_ok(m, src)?;
            let active = sz::math::i32_at(&pair.data, dlmm::off::ACTIVE_ID).ok_or(Why::Abort(Abort::Layout))?;
            let c = dlmm::array_index(active);
            let step = if zfo { -1 } else { 1 };
            let have = |i: i64| src.arrays.iter().find(|(j, _)| *j == i).filter(|_| (src.usable)(i)).and_then(|(_, k)| (src.get)(k));
            // the active bin's array must be there (the program needs it passed); then, for our route, the arrays
            // the builder names (`dlmm_window`: onward from it, contiguous, at most 5); for a third party's swap, every
            // one we hold
            if have(c).is_none() { return Err(Why::Missing(Venue::Dlmm)); }
            // on the stack (WP-16 review F7): the arrays' bytes in walk order, and the last one's index
            let mut data: [&'a [u8]; DLMM_MAX_ARRAYS] = [&[]; DLMM_MAX_ARRAYS];
            let (mut n, mut last) = (0, c);
            if route {
                for i in dlmm_window(c, zfo, &|i| have(i).is_some()) {
                    if let Some(a) = have(i) { data[n] = &a.data[..]; n += 1; last = i; }
                }
            } else {
                let mut i = c;
                while n < DLMM_MAX_ARRAYS && (c - i).abs() <= 512 {
                    if let Some(a) = have(i) { data[n] = &a.data[..]; n += 1; last = i; }
                    if !src.arrays.iter().any(|(j, _)| (*j - i) * step > 0) { break; }
                    i += step;
                }
            }
            let leg = dlmm::parse(&pair.data, &data[..n], zfo, &src.clock).map_err(Why::Abort)?;
            let leg = match use_ { Use::Route { dlmm_budget } => leg.with_budget(dlmm_budget), Use::Third => leg };
            // a walk that ends with liquidity beyond our last array (by the pair's bitmap) ends on our window, not the venue's
            let beyond = leg.bitmap_next(last + step, zfo).is_some();
            (AnyLeg::Dlmm(leg), if beyond { Why::DlmmArray } else { unq })
        }
        Venue::DammV2 => {
            let pool = get(&m.pool)?;
            mints_ok(m, src)?;
            // both mints scanned (or SPL): no transfer fee, for the crate's Token-2022 flag check
            let leg = if route { dammv2::parse(&pool.data, zfo, true, &src.clock) } else { dammv2::parse_with_limiter(&pool.data, zfo, true, &src.clock) };
            (AnyLeg::Damm(leg.map_err(Why::Abort)?), unq)
        }
        // PLAN-ADDENDUM WP-21 (DESIGN.md §9.0 item 5, §9.1): the pool, its AmmConfig, the vaults' balances, the mints'
        // scans, then the remaining accounts the leg passes as the program reads them: the bitmap extension when it
        // exists, then the tick arrays in walk order (the followed ones from the current array onward in the swap's
        // direction that the bitmaps say are initialized: the program jumps over every other), at most 7 accounts
        Venue::RayClmm => {
            let pool = get(&m.pool)?;
            let p: &'a [u8] = &pool.data;
            let cfg = get(m.clmm_config().ok_or(miss)?)?;
            // the extension when it exists (the store holds one that does not exist as an empty account; a route's
            // readiness check requires it known)
            let ext: Option<&'a [u8]> = m.clmm_ext().and_then(|k| (src.get)(k)).map(|a| &a.data[..]).filter(|d| d.len() == raydium_clmm::EXT_LEN);
            let (v0, v1) = (token_amount(get(&m.vault0)?).ok_or(miss)?, token_amount(get(&m.vault1)?).ok_or(miss)?);
            mints_ok(m, src)?;
            clmm_mints_blocked(m, src)?;
            let room = raydium_clmm::MAX_REMAINING - ext.is_some() as usize;
            // the held arrays in walk order, on the stack
            let mut held: [(i32, &'a [u8]); RAY_HELD_MAX] = [(0, &[]); RAY_HELD_MAX];
            let mut n_held = 0usize;
            if let Some(cur) = crate::venues::clmm::current_array(Venue::RayClmm, p) {
                for (i, k) in src.arrays {
                    if n_held == RAY_HELD_MAX || !(src.usable)(*i) { continue; }
                    let (Ok(st), Some(a)) = (i32::try_from(*i), (src.get)(k)) else { continue };
                    if a.data.len() != raydium_clmm::ARRAY_LEN || (zfo && st > cur) || (!zfo && st < cur) { continue; }
                    if crate::venues::clmm::ray_array_bit(p, ext, st) != Some(true) { continue; }
                    held[n_held] = (st, &a.data[..]);
                    n_held += 1;
                }
            }
            let held = &mut held[..n_held];
            held.sort_unstable_by_key(|(st, _)| if zfo { -(*st as i64) } else { *st as i64 });
            let mut rem: [&'a [u8]; raydium_clmm::MAX_REMAINING] = [&[]; raydium_clmm::MAX_REMAINING];
            let mut n = 0usize;
            if let Some(e) = ext { rem[0] = e; n = 1; }
            for (_, d) in held.iter().take(room) { rem[n] = d; n += 1; }
            let passed = n - ext.is_some() as usize;
            let leg = raydium_clmm::parse(p, &cfg.data, &rem[..n], v0, v1, zfo, &src.clock).map_err(clmm_abort)?;
            let leg = match use_ { Use::Route { dlmm_budget } => leg.with_budget(clmm_budget(dlmm_budget)), Use::Third => leg };
            // a walk that ends where our arrays end, with an initialized array beyond them by the bitmaps (or one between
            // them we do not hold), ends on our window, not the venue's
            let want = crate::venues::clmm::ray_initialized_arrays(p, ext, zfo, passed + 1);
            let beyond = want.len() > passed || want.iter().zip(held.iter()).any(|(w, (h, _))| w != h);
            (AnyLeg::RayClmm(leg), if beyond { Why::ClmmArray } else { unq })
        }
        // PLAN-ADDENDUM WP-21 (DESIGN.md §9.0 item 5, §9.2): the pool, its oracle (none when it does not exist), the vaults,
        // the mints' scans and the program's own sequence of 3 tick arrays: each held and usable, initialized (its bytes)
        // or known not to exist (the store holds it empty: zeroed, as the program reads an uninitialized PDA). A needed
        // array not known is a missing account: its absence would price it as zeroed. No swap reads past the 3
        Venue::Whirlpool => {
            let pool = get(&m.pool)?;
            let p: &'a [u8] = &pool.data;
            let o = get(m.whirl_oracle().ok_or(miss)?)?;
            let oracle: Option<&'a [u8]> = Some(&o.data[..]).filter(|d| !d.is_empty());
            let (va, vb) = (token_amount(get(&m.vault0)?).ok_or(miss)?, token_amount(get(&m.vault1)?).ok_or(miss)?);
            mints_ok(m, src)?;
            clmm_mints_blocked(m, src)?;
            let mut ins = [orca_whirlpool::TickArrayIn { start: 0, data: None }; 3];
            // (a current tick outside the tick range: the program cannot hold one; refused before its starts overflow)
            let (need, nn) = match (crate::venues::clmm::tick_spacing(Venue::Whirlpool, p), crate::venues::clmm::tick_current(Venue::Whirlpool, p)) {
                (Some(ts), Some(t)) if (orca_whirlpool::MIN_TICK..=orca_whirlpool::MAX_TICK).contains(&t) => orca_whirlpool::needed_starts(t, ts, zfo),
                (Some(_), Some(_)) => return Err(Why::Abort(Abort::Whirl(WhirlWhy::State))),
                _ => ([0; 3], 0),
            };
            for (j, st) in need.iter().take(nn).enumerate() {
                let (i, k) = src.arrays.iter().find(|(i, _)| *i == *st as i64).ok_or(Why::ClmmArray)?;
                if !(src.usable)(*i) { return Err(Why::ClmmArray); }
                let a = (src.get)(k).ok_or(Why::ClmmArray)?;
                ins[j] = orca_whirlpool::TickArrayIn { start: *st, data: Some(&a.data[..]).filter(|d| !d.is_empty()) };
            }
            let clock = whirl_clock(src.clock, p, oracle);
            let leg = orca_whirlpool::parse(p, oracle, &ins[..nn], va, vb, zfo, &clock).map_err(clmm_abort)?;
            let leg = match use_ { Use::Route { dlmm_budget } => leg.with_budget(clmm_budget(dlmm_budget)), Use::Third => leg };
            (AnyLeg::Whirl(leg), unq)
        }
    };
    Ok(Leg { venue: m.venue, zfo, any, too_large })
}

impl<'a> Leg<'a> {
    pub fn is_dlmm(&self) -> bool { self.any.is_dlmm() }
    /// a leg whose quote walks (DLMM bins; PLAN-ADDENDUM WP-21: CLMM swap steps): its CU depends on the walk
    pub fn walks(&self) -> bool { self.any.walks() }

    fn why(&self, e: QuoteErr) -> Why {
        match e {
            QuoteErr::TooLarge => self.too_large,
            QuoteErr::ZeroOut => Why::Unquotable(self.venue),
            QuoteErr::Budget => Why::Budget,
            QuoteErr::Abort(a) => clmm_abort(a),
        }
    }

    /// The exact quote of `x` (the venue's output and what it debits)
    pub fn quote(&self, x: u64) -> Result<Quote, Why> { self.any.quote(x).map_err(|e| self.why(e)) }

    /// An exact-out swap's exact quote, where the crate models the venue's exact-out instruction: PumpSwap's `buy` (base
    /// `out` exact; WP-16 review F6): Some((the quote that enters the curve, the quote: `out` and the debit)). None for
    /// the other venues and directions (an exact-out swap there is solved as the smallest exact-in size reaching `out`)
    pub fn exact_out(&self, out: u64) -> Option<Result<(u64, Quote), Why>> {
        match &self.any {
            AnyLeg::Pump(p) if !p.sell => Some(p.quote_exact_out(out).map_err(|e| self.why(e))),
            // PLAN-ADDENDUM WP-21: swap_v2 exact out, as the venue rounds it (`quote_exact_out`)
            AnyLeg::RayClmm(c) => Some(c.quote_exact_out(out).map(|q| (q.spent, q)).map_err(|e| self.why(e))),
            AnyLeg::Whirl(c) => Some(c.quote_exact_out(out).map(|q| (q.spent, q)).map_err(|e| self.why(e))),
            _ => None,
        }
    }

    /// DLMM: the exact swap of `x` bin by bin (arbx-sizing `DlmmLeg::fills`): `f` sees every bin it takes from. None
    /// for the other venues
    pub fn fills(&self, x: u64, f: &mut dyn FnMut(&dlmm::BinFill)) -> Option<Result<dlmm::Walk, Why>> {
        match &self.any { AnyLeg::Dlmm(d) => Some(d.fills(x, f).map_err(|e| self.why(e))), _ => None }
    }

    /// The exact quote of `x` with the walk (DLMM: bins with liquidity taken from, the bin it ends on, bins read;
    /// PLAN-ADDENDUM WP-21, Raydium CLMM and Orca Whirlpool: `crossed` and `walked` are the swap steps, the CU table's key)
    pub fn walk(&self, x: u64) -> Result<Quoted, Why> {
        match &self.any {
            AnyLeg::Dlmm(d) => {
                let w = d.fills(x, &mut |_| {}).map_err(|e| self.why(e))?;
                Ok(Quoted { out: w.quote.out, spent: w.quote.spent, crossed: w.liquid as u32, end: Some(w.end), walked: w.walked })
            }
            AnyLeg::RayClmm(c) => {
                let w = c.fills(x, false, &mut |_| {}).map_err(|e| self.why(e))?;
                Ok(Quoted { out: w.quote.out, spent: w.quote.spent, crossed: w.steps as u32, end: None, walked: w.steps })
            }
            AnyLeg::Whirl(c) => {
                let w = c.fills(x, false, &mut |_| {}).map_err(|e| self.why(e))?;
                Ok(Quoted { out: w.quote.out, spent: w.quote.spent, crossed: w.steps as u32, end: None, walked: w.steps })
            }
            _ => { let q = self.quote(x)?; Ok(Quoted { out: q.out, spent: q.spent, crossed: 0, end: None, walked: 0 }) }
        }
    }

    /// PLAN-ADDENDUM WP-21 (DESIGN.md §9.1): the tick arrays a Raydium CLMM leg of `x` names, in walk order: every array
    /// the exact walk reads (the first one, then each it moves into), then the next one the leg holds (a buffer: a state
    /// that moved by the time the leg runs may walk one array further), within the remaining accounts' 7 (the extension
    /// counts). None for the other venues (Orca's leg names the program's own 3: `venues::clmm::whirl_leg_starts`)
    pub fn clmm_arrays(&self, x: u64) -> Option<Result<Vec<i32>, Why>> {
        let AnyLeg::RayClmm(c) = &self.any else { return None };
        let w = match c.fills(x, false, &mut |_| {}) { Ok(w) => w, Err(e) => return Some(Err(self.why(e))) };
        let mut names: Vec<i32> = w.arrays.iter().take(w.n_arrays as usize).copied().collect();
        let room = raydium_clmm::MAX_REMAINING - c.has_extension() as usize;
        if let Some(next) = c.array_starts().skip_while(|s| Some(s) != names.last()).nth(1) { if names.len() < room { names.push(next); } }
        Some(Ok(names))
    }
}

/// One route's exact round trip at `x`: buy `x` of the quote token on `b`, sell what it delivers on `s`
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Trip { pub x: u64, pub mid: u64, pub back: u64, pub spent: u64 }

impl Trip {
    /// the guard's quote delta: the sell leg's output minus what the buy leg debited
    pub fn profit(&self) -> i64 { self.back as i64 - self.spent as i64 }
}

pub fn round_trip(b: &Leg, s: &Leg, x: u64) -> Result<Trip, Why> {
    let q0 = b.quote(x)?;
    let q1 = s.quote(q0.out)?;
    Ok(Trip { x, mid: q0.out, back: q1.out, spent: q0.spent })
}

/// The route's best size in `[lo, cap]`, every candidate evaluated exactly: the ladder's rungs up to `cap`, then, where
/// a rung makes money (where the engine refined around the best rung before WP-16), the crate locator's optima (its
/// model of both legs: the Möbius closed form, the marginal walk over DLMM bins; DESIGN.md §3.3-§3.4). An optimum past a
/// capacity steps back to the last size the venues fill. Ties go to the smaller size. Err: no rung quotes (the most
/// telling reason: a refusal of a whole leg, then a capacity or the walk budget, then a size too small)
pub fn best(b: &Leg, s: &Leg, ladder: &[u64], lo: u64, cap: u64) -> Result<Trip, Why> { best_bound(b, s, ladder, lo, cap).map(|x| x.0) }

/// [`best`], with what bounded its size: the reason the smallest size tried above the chosen one failed (None: none
/// failed above it; the profit fell, or the cap). `Some(Why::DlmmArray)` is PLAN WP-06's DLMM cap: the size stopped where
/// the bin arrays the builder names end (decisions `dlmm_cap_bound`)
pub fn best_bound(b: &Leg, s: &Leg, ladder: &[u64], lo: u64, cap: u64) -> Result<(Trip, Option<Why>), Why> {
    let lo = lo.max(1).min(cap);
    // every size that failed above a size that quoted, with why (a handful: the rungs past a capacity, the optima)
    let mut fails: Vec<(u64, Why)> = Vec::new();
    let mut top: Option<Trip> = None;
    let mut why: Option<Why> = None;
    // the largest size that quotes and, past it, the smallest that does not (feasibility is an interval in x)
    let (mut good, mut bad): (Option<u64>, Option<u64>) = (None, None);
    let keep = |t: Trip, top: &mut Option<Trip>| if top.map_or(true, |p| t.profit() > p.profit()) { *top = Some(t); };
    // the rungs up to the cap, sorted: on the stack (a ladder longer than MAX_RUNGS on the heap)
    let (mut buf, mut heap) = ([0u64; MAX_RUNGS], Vec::new());
    let rungs: &mut [u64] = if ladder.len() <= MAX_RUNGS {
        let mut n = 0;
        for &x in ladder.iter().filter(|&&x| x >= 1 && x <= cap) { buf[n] = x; n += 1; }
        &mut buf[..n]
    } else {
        heap.extend(ladder.iter().copied().filter(|&x| x >= 1 && x <= cap));
        &mut heap[..]
    };
    rungs.sort_unstable();
    // the round trip's profit is concave in the size (each leg's output is concave and increasing in its input: constant
    // product curves, DLMM bins at worsening prices with fees that only grow along the walk), so once it falls from one
    // quoted rung to the next, every larger rung is worse: the rest of the ladder is not quoted (WP-16 review F7; the
    // best rung is the same, `sizing_stops_at_the_first_falling_rung` checks it against the whole ladder)
    let mut last: Option<i64> = None;
    for (i, &x) in rungs.iter().enumerate() {
        if (i > 0 && rungs[i - 1] == x) || bad.is_some_and(|b| x >= b) { continue; }
        match round_trip(b, s, x) {
            Ok(t) => {
                good = Some(x);
                keep(t, &mut top);
                if last.is_some_and(|p| t.profit() < p) { break; }
                last = Some(t.profit());
            }
            Err(e) => { why = Some(worse(why, e)); if good.is_some() { bad = Some(x); fails.push((x, e)); } }
        }
    }
    if top.is_some_and(|t| t.profit() > 0) {
        if let (Ok(m0), Ok(m1)) = (b.any.model(), s.any.model()) {
            let loc = sz::opt::locate(&m0, &m1, Fx::from_u64(cap));
            for o in loc.optima.iter().flatten() {
                // the model's "no trade" (the round trip loses from the first unit) adds nothing the rungs do not
                if o.x.is_zero() && !o.at_cap { continue; }
                let x = o.x.floor_u64().clamp(lo, cap);
                match round_trip(b, s, x) {
                    Ok(t) => keep(t, &mut top),
                    // past a capacity (or the walk budget): the last size below it that quotes
                    Err(e) => {
                        fails.push((x, e));
                        if let Some(t) = good.filter(|&g| g < x).and_then(|g| back_off(b, s, g, bad.map_or(x, |b| b.min(x)))) { keep(t, &mut top) }
                    }
                }
            }
        }
    }
    let t = top.ok_or_else(|| why.unwrap_or(Why::Unquotable(b.venue)))?;
    let bound = fails.iter().filter(|(x, _)| *x > t.x).min_by_key(|(x, _)| *x).map(|f| f.1);
    Ok((t, bound))
}

/// rungs kept on the stack (Stage 0 has 10)
const MAX_RUNGS: usize = 32;

/// the largest size in (good, bad) that quotes, by bisection (≤ 40 round trips)
fn back_off(b: &Leg, s: &Leg, good: u64, bad: u64) -> Option<Trip> {
    let (mut g, mut bad) = (good, bad);
    let mut best = None;
    for _ in 0..40 {
        if bad <= g + 1 { break; }
        let mid = g + (bad - g) / 2;
        match round_trip(b, s, mid) { Ok(t) => { g = mid; best = Some(t); } Err(_) => bad = mid }
    }
    best
}

/// the reason a route records when no size quotes: a refusal of a whole leg first, then a capacity or the budget,
/// then the first reason seen ("too small")
fn worse(have: Option<Why>, e: Why) -> Why {
    let rank = |w: Why| if w.whole_leg() { 2 } else if matches!(w, Why::Budget | Why::PumpHeldCapacity | Why::DlmmArray | Why::ClmmArray) { 1 } else { 0 };
    match have { Some(h) if rank(h) >= rank(e) => h, _ => e }
}

#[cfg(test)]
pub(crate) mod tests;
#[cfg(test)]
pub(crate) mod clmm_tests;

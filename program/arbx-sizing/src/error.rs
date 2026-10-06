//! The three failure classes of DESIGN.md §2.6 and the quote errors.
//!
//! * [`DescError`]: the descriptor or the accounts are inconsistent (an engine bug). The program always reverts with
//!   `ERR_SIZING_DESC`.
//! * [`Abort`]: a state the model does not cover. The route falls back to pair 0 at the engine's amount (STRICT turns
//!   it into `ERR_SIZING_UNSUPPORTED`).
//! * [`QuoteErr`]: one exact quote failed (the size is too large or too small for the venue, or an [`Abort`]).

/// Why a state is not modelled (DESIGN.md §2.1-§2.5 "abort"). Falls back to the engine's amount.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Abort {
    /// the kind's cargo feature is off
    Unsupported,
    /// an account length or version byte this build does not accept
    Layout,
    /// a Token-2022 mint with a nonzero transfer fee
    TransferFee,
    /// a Token-2022 mint with a transfer hook
    TransferHook,
    /// a checked operation overflowed
    Math,
    /// the analytic model refused (DAMM v2 rate limiter) and SEARCH is off
    ModelRefused,
    Pump(PumpWhy),
    Cpmm(CpmmWhy),
    Amm(AmmWhy),
    Dlmm(DlmmWhy),
    Damm(DammWhy),
    /// Raydium CLMM (PLAN-ADDENDUM WP-21; feature `rayclmm`, off by default: the engine does not trade it yet)
    #[cfg(feature = "rayclmm")]
    Clmm(ClmmWhy),
    /// Orca Whirlpool (PLAN-ADDENDUM WP-21; feature `whirlpool`, off by default)
    #[cfg(feature = "whirlpool")]
    Whirl(WhirlWhy),
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum PumpWhy {
    /// not returned any more: a mayhem pool is priced on the fixed 1e15 supply (pinned on the dumped binary). The
    /// variant stays so that the AXZ1 codes of the ones after it do not move
    Mayhem,
    /// a cashback coin: the cashback bps source is not pinned, and the engine's leg cannot execute one (it leaves out
    /// the cashback accounts in front of pool_v2: 6060 / 6061 on the dumped binary)
    Cashback,
    Disabled, Virtual, FeeTotal, FeeConfig, EmptyReserves,
    /// the quote amounts the pool holds back (bytes 271..287) exceed the quote vault (the program fails 6023 Overflow)
    HeldExceedsVault,
    /// a byte of the pool's unidentified tail (287..301) is set: its meaning is unknown, so the pool is not priced
    UnknownTail,
}
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum CpmmWhy { SwapDisabled, NotOpen, OwedExceedsVault, CreatorFeeOn, Fee, EmptyReserves }
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AmmWhy { Status, PnlExceedsVault, Fee, EmptyReserves }
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DlmmWhy { Status, NotActive, FunctionType, CollectFeeMode, ZeroPrice, ActivationType }
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DammWhy { Status, NotActive, RateLimiter, Mode, Fee100, Liquidity, Range, Time }

/// Why a Raydium CLMM leg is refused (DESIGN.md §2.8). Every one of these fails the venue's `swap_v2` at every size.
#[cfg(feature = "rayclmm")]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ClmmWhy {
    /// pool status bit 4: swaps disabled
    Status,
    /// the Clock's unix_timestamp is not after the pool's open_time
    NotOpen,
    /// a trade fee rate above 1e6 (the program's u32 `1e6 − fee_rate` fails at every size; a fee_on other than 1 or 2
    /// is read as fee on the input, as the program reads it)
    Fee,
    /// the current tick's array is beyond the pool's default bitmap and the leg does not pass the TickArrayBitmapExtension
    BitmapExtension,
    /// no initialized tick array in the swap direction (InsufficientLiquidityForDirection)
    NoLiquidity,
    /// the first tick array the swap needs is not among the leg's tick arrays (NotEnoughTickArrayAccount /
    /// InvalidFirstTickArrayAccount)
    TickArrays,
    /// the pool's sqrt price is at the end of the price range (the default limit cannot be below / above it)
    PriceLimit,
    /// the state is inconsistent where the program checks it (current tick outside the tick range, tick spacing 0)
    State,
    /// a Token-2022 mint of the pool has its Pausable extension set to paused (every transfer fails)
    MintPaused,
    /// a Token-2022 mint of the pool has DefaultAccountState Frozen: the leg's new token account is frozen
    MintFrozen,
}

/// Why an Orca Whirlpool leg is refused (DESIGN.md §2.9). Every one of these fails the venue's `swap_v2` at every size.
#[cfg(feature = "whirlpool")]
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum WhirlWhy {
    /// the adaptive-fee Oracle's trade_enable_timestamp is in the future (TradeIsNotEnabled)
    TradeNotEnabled,
    /// the Clock is before the pool's reward or the oracle's reference/major-swap timestamps (InvalidTimestamp)
    Timestamp,
    /// none of the tick arrays the swap needs first is among the leg's (InvalidTickArraySequence)
    TickArrays,
    /// the pool's sqrt price is at the end of the price range in the swap direction
    PriceLimit,
    /// the state is inconsistent where the program checks it (tick spacing 0, a tick array of another pool)
    State,
    /// a Token-2022 mint of the pool has its Pausable extension set to paused (every transfer fails)
    MintPaused,
    /// a Token-2022 mint of the pool has DefaultAccountState Frozen: the leg's new token account is frozen
    MintFrozen,
}

impl Abort {
    /// The AXZ1 `reason` code (stable; the recorder decodes it).
    pub fn code(self) -> u16 {
        use Abort::*;
        match self {
            Unsupported => 0x10,
            Layout => 0x11,
            TransferFee => 0x12,
            TransferHook => 0x13,
            Math => 0x14,
            ModelRefused => 0x15,
            Pump(w) => 0x20 + w as u16,
            Cpmm(w) => 0x30 + w as u16,
            Amm(w) => 0x40 + w as u16,
            Dlmm(w) => 0x50 + w as u16,
            Damm(w) => 0x60 + w as u16,
            #[cfg(feature = "rayclmm")]
            Clmm(w) => 0x70 + w as u16,
            #[cfg(feature = "whirlpool")]
            Whirl(w) => 0x80 + w as u16,
        }
    }
}

/// One exact quote's failure.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum QuoteErr {
    /// the state is not modelled
    Abort(Abort),
    /// the venue would fail: capacity, range end, a missing bin array, an output it cannot represent
    TooLarge,
    /// the venue would pay out nothing (or the input is 0)
    ZeroOut,
    /// the leg's walk budget (DLMM `max_bins`) ends before the input does: NOT evaluated (the venue may well fill)
    Budget,
}

impl From<Abort> for QuoteErr {
    fn from(a: Abort) -> Self { QuoteErr::Abort(a) }
}

/// An exact quote: what the user's output account gains and what its input account loses.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Quote { pub out: u64, pub spent: u64 }

/// What is wrong with a descriptor or its accounts. Always `ERR_SIZING_DESC` on chain.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum DescCode {
    /// the block ends early
    Truncated,
    /// sz_flags bits 5-7 set
    Flags,
    /// min_size is 0 or above engine_amount
    MinSize,
    /// engine_amount above amount_in
    EngineAmount,
    /// max_iters above 24
    MaxIters,
    /// SELF_SIZE needs 2 legs, BASKET 2..=6
    NLegs,
    /// n_pairs not in 1..=3
    PairCount,
    /// a pair names a leg >= n_legs
    PairIndex,
    /// a pair's buy and sell leg are the same leg
    PairSameLeg,
    /// the same pair twice
    PairDuplicate,
    /// a leg no pair uses
    LegUnused,
    /// a leg used as a buy in one pair and as a sell in another
    LegRole,
    /// kind not in 1..=6
    Kind,
    /// PumpBuy needs dir 1, PumpSell dir 0
    Dir,
    /// n_bin_arrays: DLMM 1..=5, Raydium CLMM 1..=7 (its remaining accounts), Orca Whirlpool 0..=3 (supplemental tick
    /// arrays), any other kind 0
    BinArrays,
    /// the walk budget (`max_bins`: DLMM bins, CLMM swap steps) is 0
    BinBudget,
    /// EXPLICIT_POS: n_pos is not the kind's count
    PosCount,
    /// a position is outside the leg's accounts
    Position,
    /// the leg's program is not the kind's venue
    Program,
    /// the leg's state view has the wrong number of accounts
    StateCount,
    /// a state account has the wrong owner
    Owner,
    /// a state account has the wrong discriminator
    Discriminator,
    /// an account key differs from the key the pool (or the constant) names
    Key,
    /// a vault is not a token account (or holds another mint)
    NotTokenAccount,
    /// a mint account is not a mint
    NotMint,
    /// the leg's input account holds a mint the pool does not take on this side
    InputMint,
    /// the two legs of a pair are the same pool
    SamePool,
    /// a pair's sell leg does not take what its buy leg delivers (or does not deliver the buy leg's input)
    MintChain,
    /// basket pairs disagree on the quote mint or on X
    BasketMint,
    /// PlanIn inconsistent with itself (legs/pairs counts, amounts)
    Plan,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct DescError {
    pub code: DescCode,
    /// the leg (or pair, for pair errors) it concerns; 0xFF = the block
    pub leg: u8,
    /// the state account index within the leg (0xFF = none)
    pub acct: u8,
}

impl DescError {
    pub const fn new(code: DescCode, leg: u8, acct: u8) -> Self { DescError { code, leg, acct } }
    pub const fn block(code: DescCode) -> Self { DescError { code, leg: 0xFF, acct: 0xFF } }
}

impl core::fmt::Display for DescError {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result {
        write!(f, "sizing descriptor error {:?} (leg {}, account {})", self.code, self.leg, self.acct)
    }
}
impl core::fmt::Display for Abort {
    fn fmt(&self, f: &mut core::fmt::Formatter<'_>) -> core::fmt::Result { write!(f, "sizing abort {:?}", self) }
}

#[cfg(feature = "std")]
impl std::error::Error for DescError {}
#[cfg(feature = "std")]
impl std::error::Error for Abort {}

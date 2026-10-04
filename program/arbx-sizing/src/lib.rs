//! arbx-sizing: on-chain sizing for arbx-exec (`program/arbx-sizing/DESIGN.md`).
//!
//! At execution time the program re-quotes the route's pools from the accounts its venue CPIs take anyway, picks the
//! input size (and with BASKET the best of up to 3 candidate pool pairs) that maximises the round-trip profit, and
//! then runs the legs as before. The end-of-route guard is untouched and stays the hard backstop.
//!
//! * [`desc`]: the sizing block and leg descriptors ([`parse_block`]; `encode_block` with feature `encode`).
//! * [`venue`]: exact integer quotes per venue, with the venues' own rounding, plus the locator's models.
//! * [`opt`]: the locator (Möbius closed form, the marginal walk over DLMM bins, golden section).
//! * [`plan`](fn@plan): descriptor + account views → [`Plan`].
//! * [`budget`]: the static CU bound of a plan, from the sizing block alone (the engine's CU limit).
//!
//! `no_std`, no dependencies, no allocation, no floats, no panics on any input (every operation is checked).
#![no_std]
#![forbid(unsafe_code)]
#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

#[cfg(feature = "encode")]
extern crate alloc;
#[cfg(feature = "std")]
extern crate std;

pub mod budget;
pub mod desc;
pub mod error;
pub mod fx;
pub mod layout;
pub mod leg;
pub mod math;
pub mod opt;
pub mod plan;
pub mod token;
pub mod u256;
pub mod venue;

pub use desc::{block_len, parse_block, Kind, LegDesc, SizingBlock, SzFlags};
#[cfg(feature = "encode")]
pub use desc::encode_block;
pub use error::{Abort, DescCode, DescError, Quote, QuoteErr};
pub use fx::Fx;
pub use leg::{AnyLeg, LegHead, Parsed};
pub use budget::cu_bound;
pub use plan::{axz1_record, cpi_tip, plan, Outcome, Plan, PlanIn, Reason, TipParams, AXZ1_LEN};

/// The Clock fields sizing reads (from the `sol_get_clock_sysvar` syscall; no account needed)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Default)]
pub struct Clock { pub slot: u64, pub unix_timestamp: i64, pub epoch: u64 }

/// A borrowed account view: key, owner and data. The shell builds these from its AccountInfos.
#[derive(Clone, Copy, Debug)]
pub struct AcctRef<'a> { pub key: &'a [u8; 32], pub owner: &'a [u8; 32], pub data: &'a [u8] }

/// `create_program_address(seeds, program)`: the shell passes the runtime's syscall (`Pubkey::create_program_address`);
/// the host passes its own SHA-256 + curve check. Used once per PumpSwap leg (the canonical-pool test).
pub type PdaFn = fn(seeds: &[&[u8]], program: &[u8; 32]) -> Option<[u8; 32]>;

/// One leg as the planner sees it.
#[derive(Clone, Copy, Debug)]
pub struct LegIn<'a> {
    pub desc: LegDesc,
    /// the leg's program account (`accounts[start + 1]`)
    pub program: &'a [u8; 32],
    /// the leg's STATE accounts only, in the kind's order (DESIGN.md §4.3); resolve with [`layout::positions`]
    pub state: &'a [AcctRef<'a>],
    /// the mint of the account the leg spends from (the quote account for a buy leg, the X account for a sell leg)
    pub input_mint: &'a [u8; 32],
}

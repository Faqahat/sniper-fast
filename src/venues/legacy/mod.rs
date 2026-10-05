//! LEGACY, tests only: the engine's own venue maths before PLAN-ADDENDUM WP-16, kept verbatim (minus the swap
//! decoders, which stay in `src/venues`) as the reference of the differential tests (`src/quote/tests.rs`). The bot
//! prices with arbx-sizing (`src/quote.rs`); nothing here is compiled into it. Where this code and the crate differ
//! on recorded mainnet states, the venue programs decide (program/venue-harness): the differences are the ones
//! program/arbx-sizing/DESIGN.md §2.7 documents, and the tests assert them.
pub mod cp;
pub mod dammv2;
pub mod dlmm;

//! arbx: an atomic, self-funded Solana DEX arbitrage bot (evolved from arb-lab). It never trades ahead of user orders,
//! never sandwiches and uses only its own capital.
//!   input       every feed at once (raw UDP shreds, DoubleZero multicast, ShredStream gRPC, Yellowstone deshred / tx)
//!   processing  follow watched pools' confirmed state, look for a profitable round trip
//!   output      shadow mode: record every decision with per-feed arrival times and our own stage timings
//!   send        one-transaction Jito bundles whose route reverts unless it is profitable
//!
//! The library holds every module; `main.rs` is the command line over it (PLAN WP-01 item 1), so integration tests,
//! offline subcommands and the verifier client can use the engine without the CLI.
pub mod accuracy;
pub mod alts;
pub mod build;
pub mod chainfetch;
pub mod commit;
pub mod config;
pub mod control;
pub mod engine;
pub mod exec;
pub mod feeds;
pub mod forks;
pub mod lat;
pub mod leaders;
pub mod pda;
pub mod pools;
pub mod probe;
pub mod provenance;
pub mod rec;
pub mod rpc;
pub mod runtime;
pub mod send;
pub mod store;
pub mod store_health;
pub mod tx;
pub mod venues;
pub mod wallet;

/// the build script, included so its pure helpers (the resolved ref file of `rerun-if-changed`) are unit-tested
#[cfg(test)]
#[allow(dead_code)]
#[path = "../buildinfo.rs"]
mod buildinfo_script;

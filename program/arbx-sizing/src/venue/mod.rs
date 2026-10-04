//! Per-venue account decoding, exact quotes, models and capacities. Each `parse` takes plain byte slices (the
//! owner/key checks live in `leg.rs`), so the engine can run the same code on its own snapshots.
pub mod ammv4;
pub mod cpmm;
pub mod dammv2;
pub mod dlmm;
pub mod pumpswap;

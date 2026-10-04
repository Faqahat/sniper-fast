//! venue-harness: the exactness oracle for arbx-sizing (DESIGN.md §6.3).
//!
//! The five venue programs are the REAL mainnet ELFs (dumped read-only into `fixtures/programs`), run in LiteSVM on
//! mainnet account snapshots (`fixtures/pools`, one getMultipleAccounts per pool, Clock included). A swap is a real
//! venue instruction, built exactly as the engine builds it (`src/build.rs`), executed by a funded test wallet.
//!
//! ```no_run
//! use venue_harness::{Fixtures, Dir, venue_swap_output};
//! let fx = Fixtures::load().unwrap();
//! let pool = fx.find("6D4EWF22").unwrap().pool_key();
//! let (out, cu) = venue_swap_output(&fx, &pool, Dir::ZeroForOne, 1_000_000).unwrap();
//! ```
pub mod fixture;
pub mod harness;
pub mod keys;
pub mod rpc;
pub mod venues;

pub use fixture::{Fixtures, Patch, PoolFixture};
pub use harness::{Harness, HarnessOpts, Session, SwapOutcome};
pub use venues::{BuildOpts, Dir, Venue};

use solana_address::Address;
use std::cell::RefCell;
use std::collections::HashMap;
use std::rc::Rc;

thread_local! {
    static HARNESSES: RefCell<HashMap<Address, Rc<Harness>>> = RefCell::new(HashMap::new());
}

/// The harness for `pool`, built once per thread and reused (building loads the programs and the snapshot).
pub fn harness_for(fx: &Fixtures, pool: &Address) -> Result<Rc<Harness>, String> {
    if let Some(h) = HARNESSES.with(|m| m.borrow().get(pool).cloned()) { return Ok(h); }
    let h = Rc::new(Harness::new(fx, pool)?);
    HARNESSES.with(|m| m.borrow_mut().insert(*pool, h.clone()));
    Ok(h)
}

/// Run the pool's real swap instruction on its snapshot, spending `amount_in` of the input token of `dir`.
/// Ok((amount_out, cu)): the user's output delta and the venue's own CU. Err: the swap failed (venue error, logs).
pub fn venue_swap_output(fx: &Fixtures, pool: &Address, dir: Dir, amount_in: u64) -> Result<(u64, u64), SwapOutcome> {
    let h = harness_for(fx, pool).map_err(|e| SwapOutcome { ok: false, amount_in, amount_out: 0, spent: 0, cu_venue: None, cu_tx: 0,
        err: Some(e), logs: vec![], dlmm_arrays: vec![], events: vec![] })?;
    let o = h.swap(dir, amount_in);
    if o.ok { Ok((o.amount_out, o.cu_venue.unwrap_or(o.cu_tx))) } else { Err(o) }
}

/// `n` log-spaced input sizes for a pool side holding `reserve`: from max(1_000, reserve/10^7) to reserve/2
/// (deduplicated, increasing). The test ladder for "a swap at every scale".
pub fn size_ladder(reserve: u64, n: usize) -> Vec<u64> {
    let lo = (reserve as f64 / 1e7).max(1_000.0);
    let hi = (reserve as f64 / 2.0).max(lo * 10.0);
    let mut v: Vec<u64> = (0..n).map(|i| (lo * (hi / lo).powf(i as f64 / (n - 1).max(1) as f64)) as u64).collect();
    v.dedup();
    v
}

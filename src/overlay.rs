//! arbx-fast: a decoded pending swap's predicted effect as patched copies of the pool's accounts (an overlay), so a
//! route can be priced on the state the swap leaves BEFORE its account updates arrive (~13 ms after its shreds).
//!
//! This reverses arbx's WP-04 rule "a hint may veto a send, never create one" on purpose, in this separate copy only
//! (owner, 2026-10-07: cut trigger -> send toward 1 ms). Guard rails, enforced by the caller (engine `on_trigger`):
//! - only a swap whose own slippage bound our quote meets (`hint_check` passed) and whose signer is not a known failer;
//! - the overlay lives for ONE evaluation of ONE trigger: it is never written to the store and never prices another
//!   trigger's routes (the old `preds` path "poisoned" other pools for up to 1.5 s);
//! - sends priced on an overlay are bundle-only: a phantom (the trigger fails on chain) is dropped by Jito for free and
//!   our on-chain profit check reverts anything that does not pay.
//!
//! Byte layouts are the venues' own (the same offsets `scenarios::try_swap` patches in tests); amounts come from
//! arbx-sizing through `accuracy::predict`, the predictor proven exact on 1,316 real swaps.
use crate::accuracy::{NoPred, View};
use crate::store::Acct;
use crate::tx::Pk;
use crate::venues::{PendingSwap, PoolMeta};
use std::collections::HashMap;

/// The pool after one pending swap: patched copies of every account a quote of this pool reads that the swap changes
/// (vaults, the pool account, DLMM bin arrays). Accounts it does not hold are read from the store unchanged.
#[derive(Clone, Debug)]
pub struct Overlay {
    /// the pending transaction (first signature)
    pub txn: [u8; 64],
    pub pool: Pk,
    pub accts: HashMap<Pk, Acct>,
}

impl Overlay {
    /// the overlay's copy of `k`, if the swap changed it
    pub fn get(&self, k: &Pk) -> Option<&Acct> { self.accts.get(k) }
}

/// Apply `s` (decoded from shreds, not yet committed) to the pool `m` as `v` holds it now. Errors are the predictor's:
/// a pool or swap the venue maths does not model is never guessed.
pub fn post_swap(m: &PoolMeta, v: &View, s: &PendingSwap, txn: [u8; 64]) -> Result<Overlay, NoPred> {
    let _ = (m, v, s, txn);
    Err(NoPred::Refused("overlay_not_implemented"))
}

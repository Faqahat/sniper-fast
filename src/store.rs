//! Account store: every followed account (pools, vaults, configs, mints, DLMM bin arrays, the Clock sysvar, ...) with
//! its last versions, updated by the state stream and by RPC reads, and the readiness rules a route must pass before
//! it is priced (PLAN WP-04 items 2, 4 and 6). The quotes themselves are arbx-sizing's, from these account bytes
//! (`src/quote.rs`, PLAN-ADDENDUM WP-16).
//!
//! - **Versions** (item 2). An update is applied only if its version is newer than the account's current one. The
//!   order is `(slot, write_version)` for stream updates; an RPC read has no write version, so within one slot it orders
//!   after every stream record of that slot, and RPC reads among themselves by their accounts.bin `aseq` (MEASUREMENT
//!   §4.12). Each account keeps a ring of its last `ring_versions` (8) versions, in that order: fork rollback
//!   (`drop_versions`), the accuracy monitor's pre-state (`version_before`) and replay checks read it.
//! - **Forks** (review WP-04 #2). An older version from another slot is not current, but it is kept in the ring at its
//!   place (the late-leader fork: the leader of 12 is late, 13 is built on 11 and replayed first, then 12; 12's writes
//!   arrive with a lower slot). When a fork drops the versions above it, the newest surviving version is current again:
//!   the canonical one, not the pre-fork one. Eviction takes the oldest first, so the newest surviving version is the
//!   newest one the stream delivered on the surviving branch, unless the ring lost them all (then it is fetched again).
//!   A same-slot older version (a reordering) is refused as before.
//! - **Readiness** (item 4). A pool is quoted only when every account of its consistency set (the accounts every swap
//!   of that pool writes) is present, not pending and at most `max_part_skew_slots` apart, and its other parts are
//!   present and not pending (no age rule). Slots are never compared across pools: an idle pool is fine at any age. This
//!   replaces the old snapshot skew check and its PumpSwap exemption (the PumpSwap pool account is an "other part").
//! - **Chain clock** (item 6): the Clock sysvar's `unix_timestamp`, which DLMM and DAMM v2 fees are priced on.
use crate::feeds::src as asrc;
use crate::pools::{Registry, CLOCK_SYSVAR, PUMP_FEE_CONFIG, PUMP_GLOBAL_CONFIG};
use crate::tx::Pk;
use crate::venues::{dlmm, i32_at, i64_at, u64_at, PoolMeta, Venue};
use rustc_hash::FxHashMap as HashMap;
use std::collections::VecDeque;
use std::sync::Arc;

/// how many versions of each account the store keeps by default ([accuracy] ring_versions)
pub const RING_VERSIONS: usize = 8;

/// One version of an account. `data` is shared with the recorder's accounts.bin record of the same update (WP-03: one
/// allocation per update, never copied on the engine thread)
#[derive(Clone, Debug)]
pub struct Acct {
    pub data: Arc<[u8]>,
    pub slot: u64,
    /// the update's write version (0 for an RPC read)
    pub write_version: u64,
    /// the transaction that wrote it (stream updates; None for RPC reads and startup updates)
    pub txn: Option<[u8; 64]>,
    /// when the update reached us (ns)
    pub t_recv: u64,
    /// its accounts.bin record (0: none, e.g. a store built in a test)
    pub aseq: u64,
    /// `feeds::src` (stream or one of the RPC reads)
    pub src: u8,
    /// the bank it was written in, when the provider says (`SubscribeUpdateAccount.bank_id`; WP-04 forks)
    pub bank_id: Option<u64>,
}

/// A version's place in the store's order: (slot, 1 for an RPC read, write_version for a stream update / aseq for an RPC
/// read). Larger is newer
pub type VKey = (u64, u8, u64);

/// the order key of an update (see [`VKey`])
pub fn vkey(slot: u64, src: u8, write_version: u64, aseq: u64) -> VKey {
    let rpc = src != asrc::GRPC;
    (slot, rpc as u8, if rpc { aseq } else { write_version })
}

impl Acct {
    pub fn key(&self) -> VKey { vkey(self.slot, self.src, self.write_version, self.aseq) }
    /// an RPC read of `data` at `slot` (boot snapshots, tests)
    pub fn rpc(data: Arc<[u8]>, slot: u64, t_recv: u64, aseq: u64, src: u8) -> Acct {
        Acct { data, slot, write_version: 0, txn: None, t_recv, aseq, src, bank_id: None }
    }
}

/// The Clock sysvar as the chain last said (WP-04 item 6)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct ChainClock { pub slot: u64, pub unix_timestamp: i64, pub t_recv: u64 }

/// Clock sysvar layout: slot u64 @0, epoch_start_timestamp i64 @8, epoch u64 @16, leader_schedule_epoch u64 @24,
/// unix_timestamp i64 @32
pub fn decode_clock(d: &[u8]) -> Option<(u64, i64)> { Some((u64_at(d, 0)?, i64_at(d, 32)?)) }

/// Why a pool or route is not priced (MEASUREMENT A.1, state stage)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum NotReady {
    /// a part of the pool is not in the store
    AccountMissing,
    /// a part of the pool is written by a transaction whose commit group has not resolved
    PendingCommit,
    /// the pool's consistency set spans more than `max_part_skew_slots`
    PartsSkewed,
    /// a part's version is on a slot that has an unconfirmed sibling
    ForkPending,
    /// the store is more than `max_tip_lag_slots` behind the chain tip
    StoreLagging,
    /// a DLMM or DAMM v2 leg with a Clock sysvar more than 2 slots old
    ClockStale,
    /// a route of a group resolved by timeout: an account of one of its pools was written within `quiescence_ms`
    RouteNotQuiet,
    /// the state stream is down or its newest update is too old (PLAN-ADDENDUM I-4)
    StateUnavailable,
    /// the warm-up gate is shut (StoreHealth not ready)
    Warmup,
    /// a part of the pool has not been read again since the state stream (re)connected (review WP-04 #1, I-4): its
    /// version may predate writes the stream never resent
    Resync,
}

impl NotReady {
    pub fn reason(self) -> &'static str {
        match self {
            NotReady::AccountMissing => "account_missing", NotReady::PendingCommit => "pending_commit", NotReady::PartsSkewed => "parts_skewed",
            NotReady::ForkPending => "fork_pending", NotReady::StoreLagging => "store_lagging", NotReady::ClockStale => "clock_stale",
            NotReady::RouteNotQuiet => "route_not_quiet", NotReady::StateUnavailable => "state_unavailable", NotReady::Warmup => "warmup",
            NotReady::Resync => "resync",
        }
    }
}

/// The accounts every swap of the pool writes (PLAN WP-04 item 4): their slots are compared (`max_part_skew_slots`), and
/// none may be pending. PumpSwap: the two vaults (a swap does not need to write the pool account: that was the old
/// exemption's reason); Raydium CPMM: pool and vaults (the owed fees move); Raydium AMM v4: the vaults (whether swaps
/// write the amm account is measured first, PLAN); DLMM: the lb_pair (the bin arrays a quote crosses are checked when it
/// is priced); DAMM v2: the pool
pub fn consistency_set(m: &PoolMeta) -> Vec<Pk> {
    match m.venue {
        Venue::PumpSwap | Venue::RayAmmV4 => vec![m.vault0, m.vault1],
        Venue::RayCpmm => vec![m.pool, m.vault0, m.vault1],
        Venue::Dlmm | Venue::DammV2 => vec![m.pool],
    }
}

/// The pool's other parts (present and not pending, no age rule): the PumpSwap pool account, its fee config,
/// GlobalConfig and base mint; the CPMM config; the AMM v4 amm account; the DLMM bitmap extension when it exists; and
/// every Token-2022 mint of the pool its quote scans (PLAN-ADDENDUM WP-16: arbx-sizing refuses a transfer fee or hook)
pub fn other_parts(m: &PoolMeta) -> Vec<Pk> {
    let mut v = match m.venue {
        Venue::PumpSwap => { let mut v = vec![m.pool, *PUMP_FEE_CONFIG, *PUMP_GLOBAL_CONFIG]; v.extend(m.extra.iter().copied()); v }
        Venue::RayCpmm => m.extra.clone(),
        Venue::RayAmmV4 => vec![m.pool],
        Venue::Dlmm => if m.flag { m.extra.clone() } else { vec![] },
        Venue::DammV2 => vec![],
    };
    v.extend(crate::pools::t22_mints(m));
    v
}

/// What the readiness check needs from outside the store: which accounts are pending (the CommitTracker), which slots
/// are contested (forks), which accounts are not read again yet since the state stream (re)connected (the engine's
/// re-read, review WP-04 #1), and the skew limit
pub struct ReadyCtx<'a> {
    pub pending: &'a dyn Fn(&Pk) -> bool,
    pub contested: &'a dyn Fn(u64) -> bool,
    pub unverified: &'a dyn Fn(&Pk) -> bool,
    pub max_skew: u64,
}

/// A pool that passed the readiness check: its parts' versions (consistency set, then other parts, then the DLMM bin
/// arrays held and not pending), the consistency set's slot span, and when any of them was last written
#[derive(Clone, Debug, Default)]
pub struct PoolView {
    /// (account, slot, write_version, t_recv, aseq) of every account read
    pub accts: Vec<(Pk, u64, u64, u64, u64)>,
    /// (slot, the writing transaction's first 8 signature bytes, 0 for none) of every version read: slot-index `missing`
    /// evidence marks the decisions that read one (review WP-04 #7)
    pub txns: Vec<(u64, u64)>,
    /// the consistency set's newest minus oldest slot
    pub skew: u64,
    pub min_slot: u64,
    pub max_slot: u64,
    /// the newest `t_recv` of the pool's accounts
    pub t_last_write: u64,
    /// DLMM: the followed bin arrays left out because a pending group writes them, their slot is contested or they are
    /// not read again yet since a (re)connection (a quote that needs one fails)
    pub pending_arrays: Vec<i64>,
}

/// the first 8 bytes of a version's writing transaction (0: none), as decisions remember the versions they read
pub fn txn8(a: &Acct) -> u64 { a.txn.map_or(0, |t| u64::from_le_bytes(t[..8].try_into().unwrap())) }

/// Two pools' views together (PLAN WP-04 item 4): the route's state version (MEASUREMENT §2.1 `sv`: xxh3-64 over the
/// route accounts' (pubkey, slot, write_version) in route order), its slot range, and its last write
#[derive(Clone, Debug)]
pub struct RouteView { pub h: u64, pub slot_max: u64, pub wv_max: u64, pub min_slot: u64, pub max_slot: u64, pub t_last_write: u64, pub skew: (u64, u64) }

impl RouteView {
    pub fn of(buy: &PoolView, sell: &PoolView) -> RouteView {
        let mut x = xxhash_rust::xxh3::Xxh3::new();
        let (mut slot_max, mut wv_max) = (0, 0);
        for (k, slot, wv, _, _) in buy.accts.iter().chain(&sell.accts) {
            x.update(k);
            x.update(&slot.to_le_bytes());
            x.update(&wv.to_le_bytes());
            slot_max = slot_max.max(*slot);
            wv_max = wv_max.max(*wv);
        }
        RouteView { h: x.digest(), slot_max, wv_max, min_slot: buy.min_slot.min(sell.min_slot), max_slot: buy.max_slot.max(sell.max_slot),
            t_last_write: buy.t_last_write.max(sell.t_last_write), skew: (buy.skew, sell.skew) }
    }
    /// the slots of every version read (fork_priced bookkeeping)
    pub fn slots(buy: &PoolView, sell: &PoolView) -> Vec<u64> {
        let mut v: Vec<u64> = buy.accts.iter().chain(&sell.accts).map(|a| a.1).collect();
        v.sort_unstable();
        v.dedup();
        v
    }
    /// (slot, txn8) of every version read that a transaction wrote (fork_priced on slot-index `missing` evidence)
    pub fn txns(buy: &PoolView, sell: &PoolView) -> Vec<(u64, u64)> {
        let mut v: Vec<(u64, u64)> = buy.txns.iter().chain(&sell.txns).copied().filter(|x| x.1 != 0).collect();
        v.sort_unstable();
        v.dedup();
        v
    }
}

/// one account's versions, oldest first (the back is the current one)
#[derive(Default)]
struct Hist { ring: VecDeque<Acct> }

pub struct Store {
    accts: HashMap<Pk, Hist>,
    /// versions kept per account ([accuracy] ring_versions)
    pub ring_versions: usize,
    /// DLMM pool -> bin array index -> array account (the arrays we follow)
    pub dlmm_arrays: HashMap<Pk, Vec<(i64, Pk)>>,
    pub updates: u64,
    /// versions not applied as current (older than the current one: stale, or kept below it for a fork rollback)
    pub stale_dropped: u64,
    /// of those, the older-slot versions kept in the ring below the current one (review WP-04 #2)
    pub kept_below: u64,
    /// the newest slot of a stream update applied (any account, the Clock included): the store's position (lag rule)
    pub stream_slot_max: u64,
}

impl Default for Store {
    fn default() -> Self {
        Store { accts: HashMap::default(), ring_versions: RING_VERSIONS, dlmm_arrays: HashMap::default(), updates: 0, stale_dropped: 0,
            kept_below: 0, stream_slot_max: 0 }
    }
}

impl Store {
    /// Apply one version; false (and counted) when it is not newer than the account's current one. Such a version from a
    /// slot the ring holds no version of (same bank) is kept in the ring at its place, below the current one: a fork
    /// rollback that drops the versions above it falls back to it (review WP-04 #2)
    pub fn apply(&mut self, key: Pk, v: Acct) -> bool {
        let k = v.key();
        let cap = self.ring_versions.max(1);
        if let Some(h) = self.accts.get_mut(&key) {
            if h.ring.back().is_some_and(|cur| cur.key() >= k) {
                self.stale_dropped += 1;
                let same_slot = h.ring.iter().any(|x| x.slot == v.slot && (x.bank_id.is_none() || v.bank_id.is_none() || x.bank_id == v.bank_id));
                if !same_slot {
                    let pos = h.ring.iter().position(|x| x.key() > k).unwrap_or(h.ring.len());
                    // into a full ring below its oldest version: it would be the first evicted
                    if !(h.ring.len() >= cap && pos == 0) {
                        h.ring.insert(pos, v);
                        while h.ring.len() > cap { h.ring.pop_front(); }
                        self.kept_below += 1;
                    }
                }
                return false;
            }
        }
        if v.src == asrc::GRPC && v.slot > self.stream_slot_max { self.stream_slot_max = v.slot; }
        let h = self.accts.entry(key).or_default();
        h.ring.push_back(v);
        while h.ring.len() > cap { h.ring.pop_front(); }
        self.updates += 1;
        true
    }

    /// An RPC read of `key` (boot snapshots, tools, tests): src rpc_boot, no aseq
    pub fn update(&mut self, key: Pk, data: Arc<[u8]>, slot: u64, t: u64, txn: Option<[u8; 64]>) -> bool {
        let mut v = Acct::rpc(data, slot, t, 0, asrc::RPC_BOOT);
        v.txn = txn;
        self.apply(key, v)
    }

    /// Whether `apply` would refuse this version (the journal's ACCOUNT verdict, WP-03; no change)
    pub fn is_stale(&self, key: &Pk, slot: u64, src: u8, write_version: u64, aseq: u64) -> bool { self.is_stale_key(key, vkey(slot, src, write_version, aseq)) }

    fn is_stale_key(&self, key: &Pk, k: VKey) -> bool { self.get(key).is_some_and(|a| a.key() >= k) }

    /// the account's current version
    pub fn get(&self, k: &Pk) -> Option<&Acct> { self.accts.get(k).and_then(|h| h.ring.back()) }

    /// the account's versions, oldest first
    pub fn versions(&self, k: &Pk) -> impl Iterator<Item = &Acct> { self.accts.get(k).into_iter().flat_map(|h| h.ring.iter()) }

    /// how many accounts the store holds
    pub fn len(&self) -> usize { self.accts.len() }
    pub fn is_empty(&self) -> bool { self.accts.is_empty() }
    /// every account held (unordered)
    pub fn keys(&self) -> impl Iterator<Item = &Pk> { self.accts.keys() }

    /// The account's version just before position `k` (the newest version older than it): the accuracy monitor's
    /// pre-state. None when the ring cannot tell: every version it holds is at or after `k` (older ones were evicted, or
    /// the account was never seen before then)
    pub fn version_before(&self, acct: &Pk, k: VKey) -> Option<&Acct> {
        let h = self.accts.get(acct)?;
        h.ring.iter().rev().find(|v| v.key() < k)
    }

    /// the account's version written by `txn`, if the ring still holds it
    pub fn version_by_txn(&self, acct: &Pk, txn: &[u8; 64]) -> Option<&Acct> {
        self.accts.get(acct)?.ring.iter().rev().find(|v| v.txn.as_ref() == Some(txn))
    }

    /// The account's version at position `k` or before (the newest version not after it); None as `version_before`
    pub fn version_at(&self, acct: &Pk, k: VKey) -> Option<&Acct> {
        let h = self.accts.get(acct)?;
        h.ring.iter().rev().find(|v| v.key() <= k)
    }

    /// Drop every version `abandon(slot, bank_id)` names (forks, PLAN WP-04 item 9). Returns, per account touched (in key
    /// order), how many versions went and whether the account has none left (it must be fetched again)
    pub fn drop_versions(&mut self, abandon: &dyn Fn(u64, Option<u64>) -> bool) -> Vec<(Pk, usize, bool)> {
        self.drop_where(&|v: &Acct| abandon(v.slot, v.bank_id))
    }

    /// Drop the versions written in `slot` by one of `txns` (slot-index `missing` evidence: the confirmed block of that
    /// slot does not hold them)
    pub fn drop_txn_versions(&mut self, slot: u64, txns: &[[u8; 64]]) -> Vec<(Pk, usize, bool)> {
        self.drop_where(&|v: &Acct| v.slot == slot && v.txn.is_some_and(|t| txns.contains(&t)))
    }

    fn drop_where(&mut self, gone: &dyn Fn(&Acct) -> bool) -> Vec<(Pk, usize, bool)> {
        let mut out = Vec::new();
        for (k, h) in self.accts.iter_mut() {
            let before = h.ring.len();
            h.ring.retain(|v| !gone(v));
            if h.ring.len() < before { out.push((*k, before - h.ring.len(), h.ring.is_empty())); }
        }
        out.sort_by(|a, b| a.0.cmp(&b.0));
        for (k, _, empty) in &out {
            if *empty { self.accts.remove(k); }
        }
        out
    }

    /// The Clock sysvar's current version (WP-04 item 6)
    pub fn chain_clock(&self) -> Option<ChainClock> {
        let a = self.get(&CLOCK_SYSVAR)?;
        let (slot, unix_timestamp) = decode_clock(&a.data)?;
        Some(ChainClock { slot, unix_timestamp, t_recv: a.t_recv })
    }

    /// Readiness of one pool (PLAN WP-04 item 4): every part present and not pending, the consistency set's slots at most
    /// `ctx.max_skew` apart, no version on a contested slot. The DLMM bin arrays are not part of the check: the ones held
    /// and not pending are listed for the quote (a quote that needs a missing or pending one fails), and an array off the
    /// quote's path is never checked
    pub fn pool_view(&self, m: &PoolMeta, ctx: &ReadyCtx) -> Result<PoolView, NotReady> {
        let cs = consistency_set(m);
        let other = other_parts(m);
        let mut v = PoolView { min_slot: u64::MAX, ..Default::default() };
        let mut pending = false;
        let mut contested = false;
        let mut unverified = false;
        for (n, k) in cs.iter().chain(other.iter()).enumerate() {
            let a = self.get(k).ok_or(NotReady::AccountMissing)?;
            if (ctx.pending)(k) { pending = true; }
            if (ctx.contested)(a.slot) { contested = true; }
            if (ctx.unverified)(k) { unverified = true; }
            if n < cs.len() { v.min_slot = v.min_slot.min(a.slot); v.max_slot = v.max_slot.max(a.slot); }
            v.t_last_write = v.t_last_write.max(a.t_recv);
            v.accts.push((*k, a.slot, a.write_version, a.t_recv, a.aseq));
            v.txns.push((a.slot, txn8(a)));
        }
        if unverified { return Err(NotReady::Resync); }
        if pending { return Err(NotReady::PendingCommit); }
        if contested { return Err(NotReady::ForkPending); }
        v.skew = v.max_slot - v.min_slot;
        if v.skew > ctx.max_skew { return Err(NotReady::PartsSkewed); }
        if m.venue == Venue::Dlmm {
            for (i, k) in self.dlmm_arrays.get(&m.pool).map(|l| l.as_slice()).unwrap_or(&[]) {
                let Some(a) = self.get(k) else { continue };
                if (ctx.pending)(k) || (ctx.contested)(a.slot) || (ctx.unverified)(k) { v.pending_arrays.push(*i); continue; }
                v.t_last_write = v.t_last_write.max(a.t_recv);
                v.accts.push((*k, a.slot, a.write_version, a.t_recv, a.aseq));
                v.txns.push((a.slot, txn8(a)));
            }
        }
        Ok(v)
    }

    /// the DLMM pools whose active bin left the followed span; returns (pool, new array list) to re-follow
    pub fn dlmm_drift(&self, reg: &Registry) -> Vec<(Pk, Vec<(i64, Pk)>)> {
        let mut out = Vec::new();
        for m in reg.pools.iter().filter(|m| m.venue == Venue::Dlmm) {
            let Some(p) = self.get(&m.pool) else { continue };
            let Some(active) = i32_at(&p.data, 76) else { continue };
            let c = dlmm::array_index(active);
            let held = self.dlmm_arrays.get(&m.pool);
            let ok = held.map_or(false, |l| l.iter().any(|(i, _)| *i == c - 1) && l.iter().any(|(i, _)| *i == c + 1));
            if !ok { out.push((m.pool, crate::pools::dlmm_arrays(&m.pool, active))); }
        }
        out
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::venues::WSOL;

    fn k(n: u8) -> Pk { [n; 32] }
    fn stream(slot: u64, wv: u64, data: u8, txn: Option<u8>) -> Acct {
        Acct { data: Arc::from(&[data; 8][..]), slot, write_version: wv, txn: txn.map(|t| [t; 64]), t_recv: slot * 1_000 + wv, aseq: 0, src: asrc::GRPC, bank_id: None }
    }

    /// PLAN WP-04 acceptance, store: updates are ordered by (slot, write_version); a same-slot reordering no longer
    /// overwrites newer data with older; an RPC read orders after every stream record of its slot, RPC reads by aseq
    #[test]
    fn ordering_by_slot_and_write_version() {
        let mut s = Store::default();
        assert!(s.apply(k(1), stream(10, 5, 1, Some(1))));
        assert!(!s.apply(k(1), stream(10, 4, 2, Some(2))), "same slot, older write version: refused (it used to win)");
        assert!(!s.apply(k(1), stream(10, 5, 2, Some(2))), "the same version again: refused");
        assert!(s.apply(k(1), stream(10, 6, 3, Some(3))), "same slot, newer write version");
        assert!(!s.apply(k(1), stream(9, 100, 4, Some(4))), "an older slot whatever its write version");
        assert_eq!((s.get(&k(1)).unwrap().data[0], s.stale_dropped, s.updates), (3, 3, 2));
        // an RPC read of slot 10 is after every stream record of slot 10; a later stream record of slot 10 is stale
        assert!(s.apply(k(1), Acct::rpc(Arc::from(&[7u8; 8][..]), 10, 1, 40, asrc::RPC_SNAPSHOT)));
        assert!(!s.apply(k(1), stream(10, 99, 8, Some(8))));
        assert!(s.is_stale(&k(1), 10, asrc::RPC_REFETCH, 0, 39), "RPC reads of one slot by aseq");
        assert!(!s.is_stale(&k(1), 10, asrc::RPC_REFETCH, 0, 41));
        assert!(s.apply(k(1), stream(11, 1, 9, Some(9))), "a newer slot wins over the read");
        assert_eq!(s.get(&k(1)).unwrap().data[0], 9);
        assert_eq!(s.stream_slot_max, 11);
    }

    /// the ring keeps the last `ring_versions` versions: the pre-state of a write, a version by its transaction, and
    /// None when the ring no longer reaches back far enough
    #[test]
    fn the_ring_keeps_the_last_versions() {
        let mut s = Store { ring_versions: 3, ..Store::default() };
        for wv in 1..=5u64 { assert!(s.apply(k(1), stream(10, wv, wv as u8, Some(wv as u8)))); }
        assert_eq!(s.versions(&k(1)).map(|v| v.write_version).collect::<Vec<_>>(), vec![3, 4, 5]);
        let t5 = s.version_by_txn(&k(1), &[5; 64]).unwrap().key();
        assert_eq!(s.version_before(&k(1), t5).map(|v| v.write_version), Some(4));
        let t3 = s.version_by_txn(&k(1), &[3; 64]).unwrap().key();
        assert!(s.version_before(&k(1), t3).is_none(), "the pre-state of the oldest version held is not known");
        assert!(s.version_by_txn(&k(1), &[1; 64]).is_none(), "evicted");
        assert_eq!(s.version_at(&k(1), (10, 0, 4)).map(|v| v.write_version), Some(4));
    }

    /// forks: dropping the versions of an abandoned slot falls back to the newest canonical one; an account left with
    /// none is reported (it must be fetched again) and removed
    #[test]
    fn dropping_a_slots_versions_restores_the_canonical_one() {
        let mut s = Store::default();
        s.apply(k(1), stream(10, 1, 1, Some(1)));
        s.apply(k(1), stream(11, 2, 2, Some(2)));
        s.apply(k(2), stream(11, 3, 3, Some(3)));
        let d = s.drop_versions(&|slot, _| slot == 11);
        assert_eq!(d, vec![(k(1), 1, false), (k(2), 1, true)]);
        assert_eq!(s.get(&k(1)).unwrap().data[0], 1, "the canonical version again");
        assert!(s.get(&k(2)).is_none());
        // slot-index `missing` evidence drops by (slot, txn)
        s.apply(k(1), stream(12, 4, 4, Some(4)));
        s.apply(k(1), stream(12, 5, 5, Some(5)));
        assert_eq!(s.drop_txn_versions(12, &[[5; 64]]), vec![(k(1), 1, false)]);
        assert_eq!(s.get(&k(1)).unwrap().data[0], 4);
    }

    /// review WP-04 #2 (probe 6, the late-leader fork): 13 (built on 11) is replayed first, then the late block 12; 12's
    /// writes arrive with a lower slot. They are not current, but kept below 13's in the ring; when 13 is abandoned the
    /// canonical slot-12 version is current, not the pre-fork one. A same-slot reordering is still refused, and a version
    /// below the oldest of a full ring is not kept
    #[test]
    fn a_rollback_restores_the_canonical_version_of_a_lower_slot() {
        let mut s = Store::default();
        assert!(s.apply(k(1), stream(10, 1, 10, None)));
        assert!(s.apply(k(1), stream(13, 20, 13, Some(13))));
        assert!(!s.apply(k(1), stream(12, 30, 12, Some(12))), "not current: an older slot");
        assert!(!s.apply(k(1), stream(13, 19, 99, Some(14))), "a same-slot older write version: refused");
        assert_eq!(s.versions(&k(1)).map(|v| v.slot).collect::<Vec<_>>(), vec![10, 12, 13], "kept in order, below the current one");
        assert_eq!((s.get(&k(1)).unwrap().slot, s.stale_dropped, s.kept_below, s.updates), (13, 2, 1, 2));
        let d = s.drop_versions(&|slot, _| slot == 13);
        assert_eq!(d, vec![(k(1), 1, false)]);
        assert_eq!((s.get(&k(1)).unwrap().slot, s.get(&k(1)).unwrap().data[0]), (12, 12), "the canonical slot-12 version, not the pre-fork one");
        // a later write of the surviving branch is current as usual
        assert!(s.apply(k(1), stream(14, 40, 14, Some(15))));
        // a full ring: a version older than everything it holds is not kept; one in between is, and the oldest goes
        let mut s = Store { ring_versions: 3, ..Store::default() };
        for slot in [20, 22, 24] { s.apply(k(2), stream(slot, slot, slot as u8, None)); }
        assert!(!s.apply(k(2), stream(19, 1, 19, None)));
        assert!(!s.apply(k(2), stream(23, 1, 23, None)));
        assert_eq!(s.versions(&k(2)).map(|v| v.slot).collect::<Vec<_>>(), vec![22, 23, 24]);
        assert_eq!(s.kept_below, 1);
    }

    fn pump(n: u8) -> PoolMeta {
        PoolMeta { venue: Venue::PumpSwap, pool: k(n), t0: k(200), t1: *WSOL, vault0: k(n + 1), vault1: k(n + 2), t0_prog: *crate::pda::TOKEN_PROGRAM,
            t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![k(n + 3)], flag: true }
    }

    /// PLAN WP-04 acceptance, readiness skew rule. Positive: a PumpSwap vault 3 slots older than the other is refused.
    /// Negative: a PumpSwap pool account 10,000 slots old with fresh vaults is not refused (it is not in the consistency
    /// set); slots are never compared across pools (an idle pool 500 slots old is fine); a DLMM array off the quote is not
    /// checked
    #[test]
    fn readiness_skew_rule() {
        let m = pump(10);
        let mut s = Store::default();
        let no = |_: &Pk| false;
        let none = |_: u64| false;
        let ctx = ReadyCtx { pending: &no, contested: &none, unverified: &no, max_skew: 2 };
        s.apply(m.pool, stream(1_000, 1, 1, None));
        s.apply(*PUMP_FEE_CONFIG, stream(1_000, 2, 1, None));
        s.apply(*PUMP_GLOBAL_CONFIG, stream(1_000, 2, 1, None));
        s.apply(m.extra[0], stream(1_000, 3, 1, None));
        s.apply(m.vault0, stream(11_000, 4, 1, Some(1)));
        s.apply(m.vault1, stream(11_003, 5, 1, Some(2)));
        assert_eq!(s.pool_view(&m, &ctx).err(), Some(NotReady::PartsSkewed), "vaults 3 slots apart");
        s.apply(m.vault0, stream(11_002, 6, 1, Some(3)));
        let v = s.pool_view(&m, &ctx).expect("a pool account 10,000 slots old with fresh vaults is fine");
        assert_eq!((v.skew, v.min_slot, v.max_slot), (1, 11_002, 11_003));
        // an idle pool 500 slots old: its own parts agree, it is never compared with the busy one
        let idle = pump(20);
        for (i, a) in [idle.pool, idle.vault0, idle.vault1, idle.extra[0]].into_iter().enumerate() { s.apply(a, stream(10_503, 10 + i as u64, 1, None)); }
        let vi = s.pool_view(&idle, &ctx).unwrap();
        let r = RouteView::of(&v, &vi);
        assert_eq!((r.min_slot, r.max_slot, r.skew), (10_503, 11_003, (1, 0)));
        // a missing part, a pending part, a contested slot
        let gone = pump(30);
        assert_eq!(s.pool_view(&gone, &ctx).err(), Some(NotReady::AccountMissing));
        let pend = |a: &Pk| *a == m.pool;
        assert_eq!(s.pool_view(&m, &ReadyCtx { pending: &pend, contested: &none, unverified: &no, max_skew: 2 }).err(), Some(NotReady::PendingCommit), "other parts may not be pending");
        let cont = |slot: u64| slot == 11_003;
        assert_eq!(s.pool_view(&m, &ReadyCtx { pending: &no, contested: &cont, unverified: &no, max_skew: 2 }).err(), Some(NotReady::ForkPending));
        // a part not read again since a (re)connection (review WP-04 #1): `resync`, whatever else holds
        let unv = |a: &Pk| *a == m.extra[0];
        assert_eq!(s.pool_view(&m, &ReadyCtx { pending: &pend, contested: &none, unverified: &unv, max_skew: 2 }).err(), Some(NotReady::Resync));
        // DLMM: the lb_pair is the consistency set; a held array far from the quote (ancient, or on a contested slot)
        // is not checked, only left out of the quote
        let d = PoolMeta { venue: Venue::Dlmm, pool: k(40), t0: k(201), t1: *WSOL, vault0: k(41), vault1: k(42), t0_prog: *crate::pda::TOKEN_PROGRAM,
            t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![k(43)], flag: false };
        s.apply(d.pool, stream(11_003, 20, 1, None));
        s.apply(k(44), stream(5, 21, 1, None));
        s.apply(k(45), stream(11_003, 22, 1, None));
        s.dlmm_arrays.insert(d.pool, vec![(-9, k(44)), (0, k(45))]);
        let cont = |slot: u64| slot == 5;
        let dv = s.pool_view(&d, &ReadyCtx { pending: &no, contested: &cont, unverified: &no, max_skew: 2 }).unwrap();
        assert_eq!((dv.skew, dv.pending_arrays.clone(), dv.accts.len()), (0, vec![-9], 2));
        // an unverified array is left out of the quote the same way
        let unv = |a: &Pk| *a == k(45);
        let dv = s.pool_view(&d, &ReadyCtx { pending: &no, contested: &none, unverified: &unv, max_skew: 2 }).unwrap();
        assert_eq!((dv.pending_arrays.clone(), dv.accts.len()), (vec![0], 2));
    }

    #[test]
    fn the_chain_clock() {
        let mut s = Store::default();
        assert!(s.chain_clock().is_none());
        let mut d = vec![0u8; 40];
        d[0..8].copy_from_slice(&1_234u64.to_le_bytes());
        d[32..40].copy_from_slice(&1_759_000_000i64.to_le_bytes());
        s.apply(*CLOCK_SYSVAR, Acct { data: d.into(), slot: 1_234, write_version: 1, txn: None, t_recv: 77, aseq: 0, src: asrc::GRPC, bank_id: None });
        assert_eq!(s.chain_clock(), Some(ChainClock { slot: 1_234, unix_timestamp: 1_759_000_000, t_recv: 77 }));
    }
}

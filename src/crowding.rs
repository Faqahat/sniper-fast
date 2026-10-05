//! Crowding (PLAN WP-05 item 5; review F6): how many distinct arbitrage-like signers landed transactions on a pool over
//! the last `crowding_window_h` (6) hours. 49% of arb-lab's attempts went to the 21 pools with 150 or more bots, where
//! it won 0.4% of the time (R §1); the send queue serves such pools last within their band.
//!
//! The activity map is fed by the engine: a transaction the rival test calls arbitrage-like (`engine.rs::arb_like`:
//! two venue programs, two watched pools, or a signer seen doing either; the `record_rival` rule) is a candidate when it
//! is first seen; it **landed** on a pool when a state-stream update stamped with it wrote one of the pool's accounts
//! (only executed writes reach the stream). Its signer then counts for that pool until the window passes. Buckets:
//! below `buckets[0]` (20) is 0, below `buckets[1]` (150) is 1, else 2. Until the map has seen a whole window, WP-00's
//! static list (`[send_policy] crowded_pools_file`) stands in: a listed pool is bucket 2 (`src` `static_list`); without a
//! list the partial map is used (`map_partial`).
//!
//! **Stage 0** (review WP-05 #4): the map lives in the process. A campaign's segments are shorter than the window (the
//! supervisor runs 20-minute segments), so the map never holds a whole window and the static list is the crowding that
//! ranks; the partial map is recorded beside it (`signers_6h`) for analysis. Carrying the map across segments needs a
//! journaled preload (a replay must start from the same map), which is not built.
//!
//! **A route's count** is the larger of its two pools' counts, not the union of their signers: the union needs a set
//! intersection on the decision path, and the bots of a route mostly arbitrage both of its pools. The max can put a
//! route whose two pools have disjoint crowds a bucket low; in Stage 0 only bucket 2 ranks, and the static list sets it.
//!
//! **Cost on the engine thread** (review WP-05 #1). Every (pool, signer) pair is one node of a list ordered by its last
//! landing, oldest first; a landing moves its pair to the newest end. `expire` pops pairs from the oldest end while
//! they are older than the window: its cost is the number of pairs that expire (plus one look at the oldest), never the
//! map's size. A pool's count is its signer map's length, kept by every insert and expiry, so `crowding` is two lookups.
//! Counts are as of the last `expire` (the engine's housekeeping, at most a few ms old against a 6 h window).
use crate::exec::Crowding;
use crate::tx::Pk;
use rustc_hash::{FxHashMap as HashMap, FxHashSet as HashSet};
use std::collections::VecDeque;

/// a candidate waits this long for a landing (its updates come within a few slots)
const CAND_KEEP_NS: u64 = 10_000_000_000;
/// candidates kept at most (a burst of rival traffic cannot grow the map without bound)
const CAND_MAX: usize = 200_000;
/// signers kept per pool at most
const SIGNERS_MAX: usize = 10_000;
/// (pool, signer) pairs kept at most (PATTERNS.md's all-night bins hold about 40k): past it the pair that landed least
/// recently goes first (`evicted`), as if the window were shorter
const PAIRS_MAX: usize = 1_000_000;
/// no node
const NIL: u32 = u32::MAX;

/// one (pool, signer) pair: when the signer last landed on the pool, and its neighbours in the recency list
struct Node { pool: Pk, signer: Pk, t: u64, prev: u32, next: u32 }

pub struct Activity {
    window_ns: u64,
    buckets: [u32; 2],
    /// the first time the map saw anything (engine time): the map stands alone once a whole window has passed
    started: Option<u64>,
    cand: HashMap<[u8; 64], Pk>,
    cand_order: VecDeque<(u64, [u8; 64])>,
    /// per pool, its signers within the window, each with its node; the pool's count is the map's length
    by_pool: HashMap<Pk, HashMap<Pk, u32>>,
    /// the pairs' nodes (a slab: `free` holds the unused ones), linked from `head` (the oldest landing) to `tail` (the
    /// newest)
    nodes: Vec<Node>,
    free: Vec<u32>,
    head: u32,
    tail: u32,
    pairs: usize,
    static_list: HashSet<Pk>,
    /// pairs dropped by the `PAIRS_MAX` cap before their window ended
    pub evicted: u64,
    /// nodes `expire` has looked at (the work it did: the pairs it expired, plus one look at the oldest left)
    examined: u64,
}

impl Default for Activity { fn default() -> Self { Activity::new(6, [20, 150], HashSet::default()) } }

impl Activity {
    pub fn new(window_h: u64, buckets: [u32; 2], static_list: HashSet<Pk>) -> Activity {
        Activity { window_ns: window_h.max(1) * 3_600_000_000_000, buckets, started: None, cand: HashMap::default(), cand_order: VecDeque::new(),
            by_pool: HashMap::default(), nodes: Vec::new(), free: Vec::new(), head: NIL, tail: NIL, pairs: 0, static_list, evicted: 0, examined: 0 }
    }

    fn start(&mut self, t: u64) { if self.started.is_none() { self.started = Some(t); } }

    /// an arbitrage-like transaction of `signer`, first seen at `t`
    pub fn candidate(&mut self, sig: [u8; 64], signer: Pk, t: u64) {
        self.start(t);
        if self.cand.insert(sig, signer).is_none() { self.cand_order.push_back((t, sig)); }
        while self.cand_order.len() > CAND_MAX { if let Some((_, s)) = self.cand_order.pop_front() { self.cand.remove(&s); } }
    }

    /// a state-stream update stamped with `txn` wrote an account of `pool` at `t`: a candidate's signer landed there
    pub fn landed(&mut self, txn: &[u8; 64], pool: Pk, t: u64) {
        self.start(t);
        let Some(signer) = self.cand.get(txn).copied() else { return };
        // the list stays ordered by time even if a later landing carries an earlier time
        let t = if self.tail == NIL { t } else { t.max(self.nodes[self.tail as usize].t) };
        let m = self.by_pool.entry(pool).or_default();
        if let Some(&i) = m.get(&signer) {
            if self.nodes[i as usize].t != t { self.nodes[i as usize].t = t; self.unlink(i); self.push_back(i); }
            return;
        }
        if m.len() >= SIGNERS_MAX { return; }
        let node = Node { pool, signer, t, prev: NIL, next: NIL };
        let i = match self.free.pop() { Some(i) => { self.nodes[i as usize] = node; i } None => { self.nodes.push(node); (self.nodes.len() - 1) as u32 } };
        m.insert(signer, i);
        self.push_back(i);
        self.pairs += 1;
        if self.pairs > PAIRS_MAX { self.remove_head(); self.evicted += 1; }
    }

    /// forget candidates that never landed, and pairs whose last landing is older than the window. The work is the
    /// pairs that expire, not the map
    pub fn expire(&mut self, t: u64) {
        while let Some(&(t0, s)) = self.cand_order.front() {
            if t.saturating_sub(t0) < CAND_KEEP_NS { break; }
            self.cand_order.pop_front();
            self.cand.remove(&s);
        }
        while self.head != NIL {
            self.examined += 1;
            if t.saturating_sub(self.nodes[self.head as usize].t) < self.window_ns { break; }
            self.remove_head();
        }
    }

    /// distinct signers that landed on `pool` within the window (as of the last `expire`)
    pub fn signers(&self, pool: &Pk) -> u32 { self.by_pool.get(pool).map_or(0, |m| m.len() as u32) }

    fn bucket_of(&self, n: u32) -> u8 { if n < self.buckets[0] { 0 } else if n < self.buckets[1] { 1 } else { 2 } }

    /// the route's crowding at `t`: the more crowded of its two pools (the larger count; not the union, see the module
    /// note)
    pub fn crowding(&self, buy: &Pk, sell: &Pk, t: u64) -> Crowding {
        let n = self.signers(buy).max(self.signers(sell));
        let whole = self.started.is_some_and(|s| t.saturating_sub(s) >= self.window_ns);
        if whole { return Crowding { signers_6h: Some(n), bucket: self.bucket_of(n), src: "map" }; }
        if !self.static_list.is_empty() {
            let listed = self.static_list.contains(buy) || self.static_list.contains(sell);
            return Crowding { signers_6h: Some(n), bucket: if listed { 2 } else { self.bucket_of(n).min(1) }, src: "static_list" };
        }
        Crowding { signers_6h: Some(n), bucket: self.bucket_of(n), src: "map_partial" }
    }

    /// pools with a signer in the window
    pub fn pools(&self) -> usize { self.by_pool.len() }

    /// (pool, signer) pairs in the window
    pub fn entries(&self) -> usize { self.pairs }

    // ---- the recency list

    fn push_back(&mut self, i: u32) {
        self.nodes[i as usize].prev = self.tail;
        self.nodes[i as usize].next = NIL;
        if self.tail == NIL { self.head = i; } else { self.nodes[self.tail as usize].next = i; }
        self.tail = i;
    }

    fn unlink(&mut self, i: u32) {
        let (p, n) = (self.nodes[i as usize].prev, self.nodes[i as usize].next);
        if p == NIL { self.head = n; } else { self.nodes[p as usize].next = n; }
        if n == NIL { self.tail = p; } else { self.nodes[n as usize].prev = p; }
    }

    /// the oldest pair goes: out of the list and out of its pool's map (and the pool with it when it was the last)
    fn remove_head(&mut self) {
        let i = self.head;
        if i == NIL { return; }
        self.unlink(i);
        let (pool, signer) = (self.nodes[i as usize].pool, self.nodes[i as usize].signer);
        if let Some(m) = self.by_pool.get_mut(&pool) {
            m.remove(&signer);
            if m.is_empty() { self.by_pool.remove(&pool); }
        }
        self.free.push(i);
        self.pairs -= 1;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const H: u64 = 3_600_000_000_000;

    fn sig(i: u32) -> [u8; 64] { let mut s = [0u8; 64]; s[..4].copy_from_slice(&i.to_le_bytes()); s }
    fn signer(i: u32) -> Pk { let mut k = [9u8; 32]; k[..4].copy_from_slice(&i.to_le_bytes()); k }
    fn pool(i: u64) -> Pk { let mut k = [0u8; 32]; k[..8].copy_from_slice(&i.to_le_bytes()); k }

    /// PLAN WP-05 item 5 (F6): a signer counts for a pool once a transaction of its landed there (a stamped update), only
    /// within the window; buckets at 20 and 150; until the map has seen a whole window the static list stands in (a
    /// listed pool is bucket 2); the route takes the more crowded pool
    #[test]
    fn crowding_counts_landed_arbitrage_signers() {
        let (a, b, c) = ([1u8; 32], [2u8; 32], [3u8; 32]);
        let mut m = Activity::new(6, [20, 150], [c].into_iter().collect());
        let t0 = 1_000 * H;
        // 160 signers land on pool a; 30 on pool b; a candidate that never lands counts nowhere
        for i in 0..160 { m.candidate(sig(i), signer(i), t0); m.landed(&sig(i), a, t0 + 1); }
        for i in 0..30 { m.candidate(sig(1_000 + i), signer(i), t0); m.landed(&sig(1_000 + i), b, t0 + 1); }
        m.candidate(sig(5_000), signer(5_000), t0);
        m.landed(&sig(9_999), a, t0 + 2);
        assert_eq!((m.signers(&a), m.signers(&b), m.entries()), (160, 30, 190));
        // the map has not seen 6 h: the static list stands in (c listed -> 2; a not listed -> the partial map, at most 1)
        let early = m.crowding(&a, &[7u8; 32], t0 + 10);
        assert_eq!((early.bucket, early.src, early.signers_6h), (1, "static_list", Some(160)));
        assert_eq!(m.crowding(&[7u8; 32], &c, t0 + 10).bucket, 2, "a listed pool, either side of the route");
        // a whole window later the map stands alone: a's signers landed again, b's did not (expired at the housekeeping)
        let later = t0 + 6 * H + 2;
        for i in 0..160 { m.candidate(sig(10_000 + i), signer(i), later); m.landed(&sig(10_000 + i), a, later); }
        m.expire(later);
        let x = m.crowding(&a, &b, later);
        assert_eq!((x.bucket, x.src, x.signers_6h), (2, "map", Some(160)), "the more crowded pool");
        assert_eq!(m.crowding(&b, &c, later).bucket, 0, "b's signers are older than the window; c is no longer listed-only");
        assert_eq!((m.signers(&b), m.pools(), m.entries()), (0, 1, 160), "expired");
        assert_eq!(Crowding { signers_6h: None, bucket: 2, src: "map" }.rank(), 1);
        // no static list: the partial map
        let mut p = Activity::new(6, [20, 150], HashSet::default());
        for i in 0..25 { p.candidate(sig(i), signer(i), t0); p.landed(&sig(i), a, t0); }
        let y = p.crowding(&a, &b, t0);
        assert_eq!((y.bucket, y.src), (1, "map_partial"));
    }

    /// review WP-05 #1: a pair's count follows its last landing exactly: it expires a whole window after the signer last
    /// landed on the pool (not after the first landing), each pool keeps its own count, the same signer counts once per
    /// pool, and the per-pool cap holds
    #[test]
    fn a_pair_expires_a_window_after_its_last_landing() {
        let mut m = Activity::new(1, [20, 150], HashSet::default());
        let t0 = 10 * H;
        let mut n = 0;
        let mut land = |m: &mut Activity, s: u32, p: Pk, t: u64| { n += 1; m.candidate(sig(n), signer(s), t); m.landed(&sig(n), p, t); };
        land(&mut m, 1, pool(1), t0);
        land(&mut m, 2, pool(1), t0 + 10);
        land(&mut m, 1, pool(2), t0 + 20);
        land(&mut m, 1, pool(1), t0 + H / 2);   // signer 1 again on pool 1: its pair is renewed
        land(&mut m, 1, pool(1), t0 + H / 2);   // another account of the same pool, the same time
        assert_eq!((m.signers(&pool(1)), m.signers(&pool(2)), m.entries()), (2, 1, 3));
        m.expire(t0 + H + 10);
        assert_eq!((m.signers(&pool(1)), m.signers(&pool(2))), (1, 1), "signer 2 (t0 + 10) is a window old; pool 2's pair (t0 + 20) is not yet");
        m.expire(t0 + H + 20);
        assert_eq!((m.signers(&pool(1)), m.signers(&pool(2))), (1, 0));
        m.expire(t0 + H / 2 + H - 1);
        assert_eq!(m.signers(&pool(1)), 1);
        m.expire(t0 + H / 2 + H);
        assert_eq!((m.signers(&pool(1)), m.pools(), m.entries()), (0, 0, 0), "a window after its last landing");
        // a landing stamped earlier than the newest one keeps the list in order (it counts from the newest time)
        land(&mut m, 3, pool(3), t0 + 3 * H);
        land(&mut m, 4, pool(3), t0 + 3 * H - 5);
        m.expire(t0 + 4 * H - 1);
        assert_eq!(m.signers(&pool(3)), 2);
        m.expire(t0 + 4 * H);
        assert_eq!(m.signers(&pool(3)), 0);
        // the per-pool cap
        for s in 0..(SIGNERS_MAX as u32 + 5) { land(&mut m, 100 + s, pool(9), t0 + 5 * H); }
        assert_eq!(m.signers(&pool(9)), SIGNERS_MAX as u32);
    }

    /// review WP-05 #1 (hot path): `expire` costs the pairs that expire, not the map; `crowding` is two lookups. At 105k
    /// pairs (2,000 pools × 50, and one pool of 5,000 signers): the work counter is exact, and the wall time is bounded
    /// far below what a scan costs (a scan took 91 µs per `expire` at 100k pairs and 18 µs per `crowding` on a
    /// 5,000-signer pool in a release build: 200 calls would take 18 ms and 3.6 ms; the bounds hold in a debug build too)
    #[test]
    fn expire_and_crowding_cost_what_expires_not_the_map() {
        let mut m = Activity::new(6, [20, 150], HashSet::default());
        let t0 = 100 * H;
        let mut n = 0u32;
        for p in 0..2_000u64 {
            for s in 0..50u32 { n += 1; m.candidate(sig(n), signer(s), t0 + p); m.landed(&sig(n), pool(p), t0 + p); }
        }
        for s in 0..5_000u32 { n += 1; m.candidate(sig(n), signer(s), t0 + 3_000); m.landed(&sig(n), pool(5_000), t0 + 3_000); }
        assert_eq!(m.entries(), 105_000);
        let now = t0 + 11_000_000_000;
        m.expire(now);
        // nothing due: one look at the oldest pair, whatever the map's size
        let e0 = m.examined;
        let t = std::time::Instant::now();
        for k in 0..200 { m.expire(now + k); }
        let expire_ns = t.elapsed().as_nanos();
        assert_eq!(m.examined - e0, 200, "one look per call");
        let t = std::time::Instant::now();
        let mut acc = 0u64;
        for _ in 0..200 { acc += m.crowding(&pool(5_000), &pool(1), now).signers_6h.unwrap() as u64; }
        let crowding_ns = t.elapsed().as_nanos();
        assert_eq!(acc, 200 * 5_000);
        assert!(expire_ns < 2_000_000 && crowding_ns < 2_000_000, "200 expires {expire_ns} ns, 200 crowdings {crowding_ns} ns");
        // pools 0..9's pairs fall due (their landings were t0 + 0..9): exactly those are examined and removed
        let e1 = m.examined;
        m.expire(t0 + 6 * H + 9);
        assert_eq!((m.examined - e1, m.entries(), m.pools()), (10 * 50 + 1, 105_000 - 500, 1_991));
    }
}

/// Probes (ignored; run with `cargo test --release --lib -- --ignored probe_ --nocapture --test-threads=1`): the engine
/// thread's cost of `expire` (every housekeeping, up to 200 a second) and `crowding` (every `route_in`) at map sizes from
/// PATTERNS.md's all-night bins (about 40k pairs) to the per-pool cap (review WP-05 #1)
#[cfg(test)]
mod probe {
    use super::*;
    const H: u64 = 3_600_000_000_000;

    #[test]
    #[ignore]
    fn probe_activity_costs() {
        for (pools, signers) in [(500usize, 20usize), (2_000, 50), (21, 2_000), (50, 5_000), (100, 10_000)] {
            let mut m = Activity::new(6, [20, 150], HashSet::default());
            let t0 = 1_000 * H;
            let mut n = 0u64;
            // the feed: a candidate and its landing per (pool, signer), then every signer landing again 10 s later
            let mut fill = |m: &mut Activity, t: u64| {
                let t_fill = std::time::Instant::now();
                for p in 0..pools {
                    let mut pool = [0u8; 32]; pool[..8].copy_from_slice(&(p as u64).to_le_bytes());
                    for s in 0..signers {
                        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&n.to_le_bytes()); n += 1;
                        let mut signer = [1u8; 32]; signer[..8].copy_from_slice(&(s as u64).to_le_bytes());
                        m.candidate(sig, signer, t);
                        m.landed(&sig, pool, t + 1);
                    }
                }
                t_fill.elapsed().as_secs_f64() * 1e9 / (pools * signers) as f64
            };
            let first_ns = fill(&mut m, t0);
            let again_ns = fill(&mut m, t0 + 10_000_000_000);
            let now = t0 + 21_000_000_000; // candidates older than 10 s are gone at the first expire
            m.expire(now);
            let entries = m.entries();
            let iters = 200;
            let t = std::time::Instant::now();
            for k in 0..iters { m.expire(now + k as u64); }
            let per_expire_us = t.elapsed().as_secs_f64() * 1e6 / iters as f64;
            let mut p0 = [0u8; 32]; p0[..8].copy_from_slice(&0u64.to_le_bytes());
            let mut p1 = [0u8; 32]; p1[..8].copy_from_slice(&1u64.to_le_bytes());
            let t = std::time::Instant::now();
            let mut acc = 0u32;
            for _ in 0..1_000 { acc = acc.wrapping_add(m.crowding(&p0, &p1, now).signers_6h.unwrap()); }
            let per_crowding_us = t.elapsed().as_secs_f64() * 1e6 / 1_000.0;
            // every pair falls due at once: the cost per expired pair
            let t = std::time::Instant::now();
            m.expire(now + 7 * H);
            let per_expired_ns = t.elapsed().as_secs_f64() * 1e9 / entries as f64;
            assert_eq!(m.entries(), 0);
            println!("PROBE activity pools {pools} signers/pool {signers} entries {entries}: expire {per_expire_us:.3} us/call ({:.4} ms/s at 200 calls/s); crowding {per_crowding_us:.3} us/call (acc {acc}); candidate+landed {first_ns:.0} ns new, {again_ns:.0} ns again; {per_expired_ns:.0} ns per expired pair",
                per_expire_us * 200.0 / 1e3);
        }
    }
}

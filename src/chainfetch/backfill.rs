//! The watched-transaction backfill queue (PLAN WP-03b item 2): signatures that wrote a watched account (D1), or that a
//! shred feed saw touching one and the slot index shows landed (D2), and that have no exec.jsonl record `after_ms`
//! after they were seen. One getTransaction each, at a rate that follows the demand and the capacity left:
//! - **priority**: our attempts' route accounts (0), then Tier-A pools (1: every registry pool in Stage 0), then the rest;
//!   the newest first within a priority (when the capacity is short, first-in-first-out would serve only signatures that
//!   waited longer than the 10-minute coverage window; newest-first keeps every fetched one fresh);
//! - **rate**: `rps = "auto"` targets 1.25 x `need_rps_now` (the measured rate of uncovered signatures, a 1-minute
//!   EWMA; at least 1/s), or a fixed rate; capped by `cap`: the service sets it every second to what the backfill's
//!   providers have spare after every other role's recent requests (their buckets are shared, and the slot index, the
//!   sample and the poll go first), never above their configured `max_rps` (review WP-03b #1b, #10);
//! - **backlog**: past `max_backlog` the oldest item of the lowest non-empty priority is dropped and counted;
//! - **retries**: a fetch that finds nothing (not yet at `confirmed`) or fails is retried after 1 s, 5 s, then every 30 s;
//!   a fetch refused for want of a token (nothing was sent) goes back to the queue as it was;
//! - **the give-up**: 10 minutes after the signature was seen it leaves the queue, whether it waits, waits to retry or
//!   has just failed (`expired_total`, `gave_up_total`; review WP-03b #3).
//!
//! Every signature that leaves the queue without a fetch (dropped, expired) is reported through `take_left`, so the
//! service forgets it in time. Nothing is hidden: when the cap binds, `need_rps_now` stays above `have_rps_now`, the
//! backlog grows, drops and expiries are counted, and the coverage gauges fall. Times here are the service's monotonic
//! nanoseconds (tokio's clock, so tests run on a paused clock).
use std::collections::{BTreeMap, HashSet, VecDeque};

pub const PRIO_OURS: u8 = 0;
pub const PRIO_TIER_A: u8 = 1;
pub const PRIO_REST: u8 = 2;
/// a signature is given up this long after it was seen
pub const GIVE_UP_NS: u64 = 600_000_000_000;
/// the auto rate never goes below this (a trickle is still served), unless the providers have nothing spare
pub const MIN_AUTO_RPS: f64 = 1.0;

/// An events-per-second estimate: an exponentially weighted moving average with time constant `tau_s`, folded at most
/// once a second. It starts from no history, not from zero: until `tau_s` has passed the average is divided by the
/// weight it has gathered (`1 - e^(-t/tau)`), so the first minute reads the rate seen so far instead of ramping up
/// from 0 (the auto rate would otherwise under-serve the demand for half a minute)
#[derive(Clone, Debug)]
pub struct Rate { tau_s: f64, rate: f64, count: u64, last_ns: Option<u64>, span_s: f64 }

impl Rate {
    pub fn new(tau_s: f64) -> Rate { Rate { tau_s, rate: 0.0, count: 0, last_ns: None, span_s: 0.0 } }
    pub fn add(&mut self, n: u64) { self.count += n; }
    pub fn tick(&mut self, now_ns: u64) {
        let Some(last) = self.last_ns else { self.last_ns = Some(now_ns); return };
        let dt = now_ns.saturating_sub(last) as f64 / 1e9;
        if dt < 1.0 { return; }
        let inst = self.count as f64 / dt;
        self.rate += (inst - self.rate) * (1.0 - (-dt / self.tau_s).exp());
        self.span_s += dt;
        self.count = 0;
        self.last_ns = Some(now_ns);
    }
    pub fn get(&self) -> f64 {
        let w = 1.0 - (-self.span_s / self.tau_s).exp();
        if w > 0.0 { self.rate / w } else { 0.0 }
    }
}

/// One queued signature
#[derive(Clone, Debug)]
pub struct Item {
    pub sig: [u8; 64],
    pub slot: u64,
    pub prio: u8,
    /// txfetch.jsonl `reason`: `move_without_tx` (D1), `shred_seen_landed` (D2), `attempt_route` (priority 0)
    pub reason: &'static str,
    /// when the signature was first seen (monotonic ns)
    pub t_seen: u64,
    pub tries: u32,
    /// when it was queued (wall clock, txfetch.jsonl `queued_ns`)
    pub queued_ns: u64,
}

/// What a fetch came to
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Outcome {
    Fetched,
    NotFound,
    Failed,
    /// refused for want of a token: nothing was sent, so it goes back to the queue as it was
    Refused,
    /// not needed any more (recorded elsewhere, or on an abandoned fork): no retry
    Abandoned,
}

/// Why a signature left the queue without a fetch
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Left { Dropped, Expired }

pub struct Backfill {
    pub after_ns: u64,
    max_backlog: usize,
    fixed: Option<f64>,
    /// what the rate may not exceed (INFINITY: unlimited): the providers' spare capacity, set by the service
    cap: f64,
    pub max_inflight: usize,
    q: [VecDeque<Item>; 3],
    in_q: HashSet<[u8; 64]>,
    retry: BTreeMap<(u64, [u8; 64]), Item>,
    pub need: Rate,
    pub have: Rate,
    tokens: f64,
    last_ns: Option<u64>,
    pub inflight: usize,
    left: Vec<([u8; 64], Left)>,
    pub queued_total: u64,
    pub dropped_total: u64,
    pub fetched_total: u64,
    pub gave_up_total: u64,
    pub expired_total: u64,
    pub retried_total: u64,
    pub refused_total: u64,
}

impl Backfill {
    pub fn new(after_ms: u64, max_backlog: usize, fixed: Option<f64>, cap: f64, max_inflight: usize) -> Backfill {
        let mut b = Backfill { after_ns: after_ms * 1_000_000, max_backlog: max_backlog.max(1), fixed, cap: f64::INFINITY, max_inflight: max_inflight.max(1),
            q: Default::default(), in_q: HashSet::new(), retry: BTreeMap::new(), need: Rate::new(60.0), have: Rate::new(60.0), tokens: 1.0, last_ns: None,
            inflight: 0, left: Vec::new(), queued_total: 0, dropped_total: 0, fetched_total: 0, gave_up_total: 0, expired_total: 0, retried_total: 0, refused_total: 0 };
        // no providers' figure (0) or none at all: no cap until the service sets one
        b.set_cap(if cap > 0.0 { cap } else { f64::INFINITY });
        b
    }

    /// what the rate may not exceed now (requests/s; INFINITY or a non-positive value from no cap: unlimited, except 0
    /// itself, which stops the backfill until the providers have something spare)
    pub fn set_cap(&mut self, cap: f64) { self.cap = if cap.is_nan() || cap == f64::INFINITY { f64::INFINITY } else { cap.max(0.0) }; }

    /// the rate the backfill fetches at now: `rps` fixed, or 1.25 x the uncovered rate (at least `MIN_AUTO_RPS`); capped
    pub fn target_rps(&self) -> f64 {
        let r = match self.fixed { Some(r) => r, None => (1.25 * self.need.get()).max(MIN_AUTO_RPS) };
        r.min(self.cap)
    }
    pub fn cap_rps(&self) -> Option<f64> { self.cap.is_finite().then_some(self.cap) }

    /// queued and waiting-to-retry signatures
    pub fn backlog(&self) -> usize { self.in_q.len() + self.retry.len() }
    pub fn contains(&self, sig: &[u8; 64]) -> bool { self.in_q.contains(sig) || self.retry.keys().any(|k| &k.1 == sig) }

    /// the signatures that left the queue without a fetch since the last call (dropped past `max_backlog`, expired)
    pub fn take_left(&mut self) -> Vec<([u8; 64], Left)> { std::mem::take(&mut self.left) }

    /// A signature that has gone `after_ms` without a record: queued (it counts towards `need`). Past `max_backlog` the
    /// oldest of the lowest non-empty priority is dropped (`take_left`); returns how many were dropped
    pub fn push(&mut self, it: Item) -> usize {
        if !self.in_q.insert(it.sig) { return 0; }
        self.need.add(1);
        self.queued_total += 1;
        let p = (it.prio as usize).min(2);
        self.q[p].push_back(it);
        self.trim()
    }

    fn trim(&mut self) -> usize {
        let mut n = 0;
        while self.backlog() > self.max_backlog {
            let mut done = false;
            for p in (0..3).rev() {
                while let Some(it) = self.q[p].pop_front() {
                    if self.in_q.remove(&it.sig) { self.left.push((it.sig, Left::Dropped)); n += 1; done = true; break; }
                }
                if done { break; }
            }
            if !done {
                // only retries left: the oldest due one goes
                match self.retry.keys().next().copied() { Some(k) => { self.retry.remove(&k); self.left.push((k.1, Left::Dropped)); n += 1; } None => break }
            }
        }
        self.dropped_total += n as u64;
        n
    }

    /// a signature got its record elsewhere (the stream, the wallet, a block sample): no fetch for it
    pub fn remove(&mut self, sig: &[u8; 64]) {
        self.in_q.remove(sig);
        let k: Vec<(u64, [u8; 64])> = self.retry.keys().filter(|k| &k.1 == sig).copied().collect();
        for k in k { self.retry.remove(&k); }
    }

    /// Signatures seen 10 minutes ago or more leave the queue (waiting, or waiting to retry): `expired_total`, and
    /// `take_left`. The service calls it once a second
    pub fn expire(&mut self, now_ns: u64) -> usize {
        let old = |it: &Item| now_ns.saturating_sub(it.t_seen) >= GIVE_UP_NS;
        let mut gone = Vec::new();
        for q in self.q.iter_mut() {
            q.retain(|it| {
                if !old(it) { return true; }
                gone.push(it.sig);
                false
            });
        }
        let mut n = 0;
        for sig in gone { if self.in_q.remove(&sig) { self.left.push((sig, Left::Expired)); n += 1; } }
        let late: Vec<(u64, [u8; 64])> = self.retry.iter().filter(|(_, it)| old(it)).map(|(k, _)| *k).collect();
        for k in late { self.retry.remove(&k); self.left.push((k.1, Left::Expired)); n += 1; }
        self.expired_total += n as u64;
        n
    }

    /// The items to fetch now (`now_ns` monotonic): due retries go back to their queue, then the highest priority first
    /// and the newest first within it, as the rate's tokens and the in-flight cap allow
    pub fn take(&mut self, now_ns: u64) -> Vec<Item> {
        self.need.tick(now_ns);
        self.have.tick(now_ns);
        let due: Vec<(u64, [u8; 64])> = self.retry.range(..(now_ns + 1, [0u8; 64])).map(|(k, _)| *k).collect();
        for k in due {
            if let Some(it) = self.retry.remove(&k) {
                let p = (it.prio as usize).min(2);
                self.in_q.insert(it.sig);
                self.q[p].push_back(it);
            }
        }
        let rate = self.target_rps();
        if let Some(last) = self.last_ns {
            let dt = now_ns.saturating_sub(last) as f64 / 1e9;
            self.tokens = (self.tokens + dt * rate).min(rate.max(1.0));
        }
        self.last_ns = Some(now_ns);
        let mut out = Vec::new();
        while self.tokens >= 1.0 && self.inflight < self.max_inflight {
            let Some(it) = (0..3).find_map(|p| {
                while let Some(it) = self.q[p].pop_back() { if self.in_q.remove(&it.sig) { return Some(it); } }
                None
            }) else { break };
            self.tokens -= 1.0;
            self.inflight += 1;
            out.push(it);
        }
        out
    }

    /// A fetch ended. A fetched record counts towards `have`; a refusal (no token: nothing sent) goes back to the queue as
    /// it was; nothing found or a failure is retried after 1 s, 5 s, then every 30 s, until 10 minutes after the
    /// signature was seen. Returns true when it was given up
    pub fn done(&mut self, mut it: Item, o: Outcome, now_ns: u64) -> bool {
        self.inflight = self.inflight.saturating_sub(1);
        match o {
            Outcome::Fetched => { self.fetched_total += 1; self.have.add(1); return false; }
            Outcome::Abandoned => return false,
            _ => {}
        }
        if now_ns.saturating_sub(it.t_seen) >= GIVE_UP_NS { self.gave_up_total += 1; return true; }
        if o == Outcome::Refused {
            self.refused_total += 1;
            if self.in_q.insert(it.sig) { let p = (it.prio as usize).min(2); self.q[p].push_back(it); }
        } else {
            let wait = match it.tries { 0 => 1_000_000_000, 1 => 5_000_000_000, _ => 30_000_000_000 };
            it.tries += 1;
            self.retried_total += 1;
            self.retry.insert((now_ns + wait, it.sig), it);
        }
        self.trim();
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn item(n: u32, prio: u8, t: u64) -> Item {
        let mut sig = [0u8; 64];
        sig[..4].copy_from_slice(&n.to_le_bytes());
        Item { sig, slot: 1, prio, reason: "move_without_tx", t_seen: t, tries: 0, queued_ns: 0 }
    }
    const S: u64 = 1_000_000_000;

    /// priority order (ours, then Tier A, then the rest; the newest first within one), the backlog drop of the oldest
    /// low-priority item, retries and the give-up
    #[test]
    fn priority_backlog_and_retries() {
        let mut b = Backfill::new(1_500, 4, Some(100.0), f64::INFINITY, 64);
        for (n, p) in [(1, PRIO_REST), (2, PRIO_TIER_A), (3, PRIO_REST), (4, PRIO_OURS)] { assert_eq!(b.push(item(n, p, 0)), 0); }
        // the fifth item makes 5 > 4: the oldest of the lowest priority (1) goes, and is reported
        assert_eq!(b.push(item(5, PRIO_TIER_A, 0)), 1);
        let d = b.take_left();
        assert_eq!(d.len(), 1);
        assert_eq!((&d[0].0[..4], d[0].1), (&1u32.to_le_bytes()[..], Left::Dropped));
        assert_eq!((b.backlog(), b.dropped_total), (4, 1));
        // the first call has the bucket's first token; a second later the rate's tokens
        let mut got = b.take(0);
        got.extend(b.take(S));
        let order: Vec<u32> = got.iter().map(|i| u32::from_le_bytes(i.sig[..4].try_into().unwrap())).collect();
        assert_eq!(order, vec![4, 5, 2, 3], "ours, Tier A newest first, then the rest");
        // a not-found is retried after 1 s, then 5 s; the give-up comes 10 minutes after the signature was seen
        let it = got[0].clone();
        assert!(!b.done(it.clone(), Outcome::NotFound, S));
        assert!(b.take(S + S / 2).is_empty(), "not due yet");
        let again = b.take(2 * S + 1);
        assert_eq!(again.len(), 1);
        assert_eq!(again[0].tries, 1);
        assert!(b.done(again[0].clone(), Outcome::Failed, GIVE_UP_NS + 1), "given up");
        assert_eq!(b.gave_up_total, 1);
        // a signature recorded elsewhere leaves the queue
        b.push(item(9, PRIO_REST, 0));
        b.remove(&item(9, PRIO_REST, 0).sig);
        assert!(!b.contains(&item(9, PRIO_REST, 0).sig));
    }

    /// the rate's tokens: a fixed 2/s gives 2 a second (plus the first), the in-flight cap binds, and the cap of the
    /// providers bounds the auto rate
    #[test]
    fn tokens_follow_the_rate_and_the_caps() {
        let mut b = Backfill::new(1_500, 1_000, Some(2.0), f64::INFINITY, 64);
        for n in 0..100 { b.push(item(n, PRIO_TIER_A, 0)); }
        let mut n = b.take(0).len();
        for k in 1..=10 { n += b.take(k * S).len(); }
        assert!((20..=22).contains(&n), "{n}");
        let mut c = Backfill::new(1_500, 1_000, Some(50.0), f64::INFINITY, 3);
        for n in 0..100 { c.push(item(n, PRIO_TIER_A, 0)); }
        let first = c.take(0).len();
        assert_eq!(first + c.take(S).len(), 3, "the in-flight cap");
        let auto = Backfill::new(1_500, 10, None, 4.0, 3);
        assert_eq!(auto.target_rps(), MIN_AUTO_RPS);
        let mut a = auto;
        a.need.add(600);
        a.need.tick(0);
        a.need.tick(60 * S);
        assert!(a.need.get() > 5.0);
        assert_eq!(a.target_rps(), 4.0, "1.25 x need, capped by the providers");
    }

    /// review WP-03b #3 (probe P3): a retry that overfills the backlog drops a signature inside `done`, and the drop is
    /// reported (`take_left`), so the service clears its `queued` flag; a refusal goes back to the queue untouched
    #[test]
    fn done_reports_what_it_drops_and_refusals_requeue() {
        let mut b = Backfill::new(1_500, 4, Some(100.0), f64::INFINITY, 64);
        for n in 1..=4 { assert_eq!(b.push(item(n, PRIO_REST, 0)), 0); }
        let got = b.take(0);
        assert_eq!((got.len(), u32::from_le_bytes(got[0].sig[..4].try_into().unwrap())), (1, 4));
        assert_eq!(b.push(item(5, PRIO_REST, 0)), 0);
        assert!(!b.done(got[0].clone(), Outcome::Failed, S), "retried, not given up");
        assert_eq!(b.dropped_total, 1);
        let left = b.take_left();
        assert_eq!(left.len(), 1);
        assert_eq!((&left[0].0[..4], left[0].1), (&1u32.to_le_bytes()[..], Left::Dropped), "the oldest of the queue, reported");
        // a refusal: back in the queue with its tries unchanged, not a retry
        let mut c = Backfill::new(1_500, 10, Some(100.0), f64::INFINITY, 64);
        c.push(item(7, PRIO_TIER_A, 0));
        let it = c.take(0).pop().unwrap();
        assert!(!c.done(it, Outcome::Refused, S));
        assert_eq!((c.refused_total, c.retried_total, c.backlog(), c.inflight), (1, 0, 1, 0));
        let again = c.take(S + 1);
        assert_eq!((again.len(), again[0].tries), (1, 0));
    }

    /// review WP-03b #3: queued items leave 10 minutes after they were seen, waiting or waiting to retry, and are counted
    /// and reported; the cap set by the service binds the rate (0: nothing is fetched)
    #[test]
    fn queued_items_expire_and_the_cap_binds() {
        let mut b = Backfill::new(1_500, 1_000, None, f64::INFINITY, 64);
        for n in 0..10 { b.push(item(n, PRIO_TIER_A, n as u64 * S)); }
        let it = b.take(0).pop().unwrap();
        b.done(it, Outcome::NotFound, S);
        assert_eq!(b.expire(GIVE_UP_NS + 4 * S), 5, "the five seen at 0-4 s");
        let left = b.take_left();
        assert!(left.len() == 5 && left.iter().all(|l| l.1 == Left::Expired));
        assert_eq!((b.expired_total, b.backlog()), (5, 5));
        // the one waiting to retry (seen at 9 s, the newest: taken first) expires too, with the four still queued
        assert_eq!(b.expire(GIVE_UP_NS + 9 * S), 5);
        assert_eq!((b.backlog(), b.take_left().len()), (0, 5));
        let mut c = Backfill::new(1_500, 1_000, None, f64::INFINITY, 64);
        for n in 0..100 { c.push(item(n, PRIO_TIER_A, 0)); }
        c.set_cap(0.0);
        assert_eq!(c.target_rps(), 0.0);
        let n: usize = (0..10).map(|k| c.take(k * S).len()).sum();
        assert_eq!(n, 1, "the bucket's first token only");
        c.set_cap(f64::INFINITY);
        assert_eq!(c.cap_rps(), None);
    }
}

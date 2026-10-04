//! Lookup tables (PLAN WP-04 item 7; PLAN-ADDENDUM I-6). A transaction that loads addresses from a lookup table the
//! engine does not know waits while the table is fetched (on the background runtime). arb-lab cached a failed fetch as
//! "missing" for the whole run: in cmp2 arbx dropped 5,001 transactions as `alt_unknown` against the old bot's ~610,
//! after starting with an empty cache during an RPC 429 burst. Here:
//! - a failed fetch (an RPC error, or no such account yet) is retried at `retry_ms` (50 ms, 250 ms, 1 s, 5 s) after each
//!   failure, then every `retry_every_s` (30 s), until `give_up_s` (10 minutes) after the first failure;
//! - at most `max_inflight` fetches run at once; the rest queue;
//! - transactions wait while their table's fetch or retry is pending (at most `wait_cap` of them, the oldest dropped
//!   and counted) and are dropped only when the table is given up;
//! - the previous segment's `alts-final` can be preloaded at boot: the tables a transaction used in the last
//!   `[alts] preload_max_age_h` hours, at most `preload_max_tables` (review WP-04 #11: `last_used` is kept per table and
//!   written to alts-final, so the preloaded set no longer grows across a campaign);
//! - every transition is an `alts.jsonl` event (MEASUREMENT §4.26); the full dump stays `alts-final` at stop.
//! The retry times are engine times, checked by the engine's timers: deterministic under replay (the journal holds the
//! fetch answers as ALT records).
use crate::tx::Pk;
use rustc_hash::FxHashMap as HashMap;
use std::collections::VecDeque;

/// The retry policy (`[alts]`)
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct Policy { pub retry_ms: Vec<u64>, pub retry_every_s: u64, pub give_up_s: u64, pub wait_cap: usize, pub max_inflight: usize }

impl Default for Policy {
    fn default() -> Self { Policy { retry_ms: vec![50, 250, 1_000, 5_000], retry_every_s: 30, give_up_s: 600, wait_cap: 10_000, max_inflight: 16 } }
}

impl Policy {
    /// how long after failure number `n` (1, 2, ...) the next attempt runs
    pub fn delay_ns(&self, n: u32) -> u64 {
        let ms = self.retry_ms.get(n.saturating_sub(1) as usize).copied().unwrap_or(self.retry_every_s * 1_000);
        ms * 1_000_000
    }
}

/// What a fetch said (journal ALT `found`: 1, 0, 2)
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum Answer { Found(Vec<Pk>), Missing, Error(String) }

#[derive(Clone, Debug, PartialEq, Eq)]
enum St {
    /// a fetch is running (attempt number, 1-based)
    Fetching(u32),
    /// waiting for a free fetch slot
    Queued(u32),
    /// failed `n` times; the next attempt at `at`
    Retry { n: u32, at: u64 },
}

/// One alts.jsonl event (MEASUREMENT §4.26)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Ev { pub table: Pk, pub event: &'static str, pub n_addrs: Option<usize>, pub attempt: u32, pub next_retry_ms: Option<u64>, pub waiting_txs: usize, pub err: Option<String> }

/// what `need` decided for a transaction
#[derive(Debug, PartialEq, Eq)]
pub enum Need { Wait, Drop(&'static str) }

pub struct Alts<W> {
    pub policy: Policy,
    /// tables, possibly partial: entries learned from feeds that send loaded addresses, or the whole table from a fetch
    pub tables: HashMap<Pk, Vec<Option<Pk>>>,
    /// the tables being fetched, queued or retried (with when their first attempt started); given-up ones are kept apart
    /// (`given_up`), so the per-input scans (`next_retry`) see only the work in progress (review WP-04 N6)
    st: HashMap<Pk, (St, u64)>,
    given_up: rustc_hash::FxHashSet<Pk>,
    /// tables waiting for a free fetch slot, in order
    queue: VecDeque<Pk>,
    inflight: usize,
    waiting: HashMap<Pk, Vec<(u64, W)>>,
    /// (arrival seq, table) of every waiter, oldest first (the cap drops from here)
    wait_order: VecDeque<(u64, Pk)>,
    wait_seq: u64,
    n_waiting: usize,
    pub events: Vec<Ev>,
    /// when a transaction last used each table (engine time; a preloaded table's from the previous segment's file):
    /// alts-final's `last_used_ns`, what the next segment's preload filters on
    pub last_used: HashMap<Pk, u64>,
    /// totals: waiters dropped by the cap and by a give-up
    pub dropped_cap: u64,
    pub dropped_gave_up: u64,
}

impl<W> Alts<W> {
    pub fn new(policy: Policy) -> Alts<W> {
        Alts { policy, tables: HashMap::default(), st: HashMap::default(), given_up: Default::default(), queue: VecDeque::new(), inflight: 0, waiting: HashMap::default(),
            wait_order: VecDeque::new(), wait_seq: 0, n_waiting: 0, events: Vec::new(), last_used: HashMap::default(), dropped_cap: 0, dropped_gave_up: 0 }
    }

    pub fn inflight(&self) -> usize { self.inflight }
    pub fn waiting_txs(&self) -> usize { self.n_waiting }
    pub fn pending_retries(&self) -> usize { self.st.values().filter(|s| matches!(s.0, St::Retry { .. } | St::Queued(_))).count() }
    pub fn gave_up(&self) -> usize { self.given_up.len() }

    fn ev(&mut self, table: Pk, event: &'static str, attempt: u32, next_retry_ms: Option<u64>, err: Option<String>) {
        let waiting = self.waiting.get(&table).map_or(0, |v| v.len());
        let n_addrs = self.tables.get(&table).map(|v| v.iter().filter(|a| a.is_some()).count());
        self.events.push(Ev { table, event, n_addrs, attempt, next_retry_ms, waiting_txs: waiting, err });
    }

    /// A transaction needs `missing` (the tables it lacks an entry of, in its order): it waits on the first one, and a
    /// fetch starts for every one that is not known, fetched or retried already (`fetch` collects the tables to fetch
    /// now). Dropped when one of them was given up
    pub fn need(&mut self, missing: &[Pk], w: W, t: u64, fetch: &mut Vec<Pk>) -> Need {
        if missing.iter().any(|m| self.given_up.contains(m)) { return Need::Drop("alt_gave_up"); }
        for m in missing {
            if self.st.contains_key(m) { continue; }
            self.start(*m, 1, t, fetch);
        }
        let first = missing[0];
        let seq = self.wait_seq;
        self.wait_seq += 1;
        self.waiting.entry(first).or_default().push((seq, w));
        self.wait_order.push_back((seq, first));
        self.n_waiting += 1;
        while self.n_waiting > self.policy.wait_cap {
            let Some((s, tb)) = self.wait_order.pop_front() else { break };
            let Some(v) = self.waiting.get_mut(&tb) else { continue };
            let Some(at) = v.iter().position(|x| x.0 == s) else { continue };
            v.remove(at);
            if v.is_empty() { self.waiting.remove(&tb); }
            self.n_waiting -= 1;
            self.dropped_cap += 1;
            self.ev(tb, "waiters_dropped", 0, None, Some("wait_cap".into()));
        }
        Need::Wait
    }

    fn start(&mut self, table: Pk, attempt: u32, t: u64, fetch: &mut Vec<Pk>) {
        if self.inflight < self.policy.max_inflight.max(1) {
            self.inflight += 1;
            self.st.insert(table, (St::Fetching(attempt), self.st.get(&table).map_or(t, |s| s.1)));
            self.ev(table, "fetch_start", attempt, None, None);
            fetch.push(table);
        } else {
            self.st.insert(table, (St::Queued(attempt), self.st.get(&table).map_or(t, |s| s.1)));
            if !self.queue.contains(&table) { self.queue.push_back(table); }
        }
    }

    /// A fetch's answer. Found: the table is known and its waiters are released (returned, in arrival order). Missing or
    /// an error: retried later, or given up (its waiters dropped). Queued tables start as fetch slots free up
    pub fn on_answer(&mut self, table: Pk, a: Answer, t: u64, fetch: &mut Vec<Pk>) -> Vec<W> {
        let (attempt, first_t) = match self.st.get(&table) { Some((St::Fetching(n), t0)) => (*n, *t0), _ => (1, t) };
        if matches!(self.st.get(&table), Some((St::Fetching(_), _))) { self.inflight = self.inflight.saturating_sub(1); }
        let mut released = Vec::new();
        match a {
            Answer::Found(addrs) => {
                let mut v: Vec<Option<Pk>> = addrs.iter().map(|k| Some(*k)).collect();
                v.resize(256.max(v.len()), None);
                self.tables.insert(table, v);
                self.st.remove(&table);
                self.ev(table, "fetch_ok", attempt, None, None);
                released = self.take_waiters(&table);
            }
            Answer::Missing | Answer::Error(_) => {
                let (what, err) = match &a { Answer::Missing => ("fetch_missing", None), Answer::Error(e) => ("fetch_error", Some(e.clone())), _ => unreachable!() };
                self.ev(table, what, attempt, None, err);
                if t.saturating_sub(first_t) >= self.policy.give_up_s * 1_000_000_000 {
                    self.st.remove(&table);
                    self.given_up.insert(table);
                    self.ev(table, "give_up", attempt, None, None);
                    let n = self.take_waiters(&table).len();
                    if n > 0 { self.dropped_gave_up += n as u64; self.ev(table, "waiters_dropped", attempt, None, Some("give_up".into())); }
                } else {
                    let d = self.policy.delay_ns(attempt);
                    self.st.insert(table, (St::Retry { n: attempt, at: t + d }, first_t));
                    self.ev(table, "retry_scheduled", attempt, Some(d / 1_000_000), None);
                }
            }
        }
        self.fill(t, fetch);
        released
    }

    /// the timers: retries whose time has come start (as fetch slots allow)
    pub fn due(&mut self, t: u64, fetch: &mut Vec<Pk>) {
        let mut due: Vec<(Pk, u32)> = self.st.iter().filter_map(|(k, s)| match s.0 { St::Retry { n, at } if at <= t => Some((*k, n + 1)), _ => None }).collect();
        due.sort();
        for (k, n) in due { self.start(k, n, t, fetch); }
        self.fill(t, fetch);
    }

    /// the earliest retry time (the run loop's wake-up)
    pub fn next_retry(&self) -> Option<u64> { self.st.values().filter_map(|s| match s.0 { St::Retry { at, .. } => Some(at), _ => None }).min() }

    fn fill(&mut self, t: u64, fetch: &mut Vec<Pk>) {
        while self.inflight < self.policy.max_inflight.max(1) {
            let Some(k) = self.queue.pop_front() else { break };
            if let Some((St::Queued(n), _)) = self.st.get(&k).cloned() { self.start(k, n, t, fetch); }
        }
    }

    /// The waiters of a table (its entries were learned from a feed, or fetched), in arrival order
    pub fn take_waiters(&mut self, table: &Pk) -> Vec<W> {
        let v = self.waiting.remove(table).unwrap_or_default();
        self.n_waiting -= v.len();
        let n = v.len();
        if n > 0 { self.wait_order.retain(|(_, tb)| tb != table); }
        let out: Vec<W> = v.into_iter().map(|(_, w)| w).collect();
        if n > 0 { self.ev(*table, "waiters_released", 0, None, None); }
        out
    }

    /// entries learned from a feed that sends loaded addresses: a table being retried or given up is known again
    pub fn learned(&mut self, table: Pk) {
        if matches!(self.st.get(&table), Some((St::Retry { .. } | St::Queued(_), _))) || self.given_up.contains(&table) {
            self.st.remove(&table);
            self.given_up.remove(&table);
            self.queue.retain(|k| *k != table);
        }
        self.ev(table, "learned_feed", 0, None, None);
    }

    /// a table from the previous segment's alts-final (boot), with when it was last used there
    pub fn preload(&mut self, table: Pk, addrs: Vec<Option<Pk>>, last_used: Option<u64>) {
        let mut v = addrs;
        v.resize(256.max(v.len()), None);
        self.tables.insert(table, v);
        if let Some(t) = last_used { self.last_used.insert(table, t); }
        self.ev(table, "preloaded", 0, None, None);
    }

    /// a transaction used `table` at `t` (its addresses resolved one)
    #[inline]
    pub fn used(&mut self, table: Pk, t: u64) {
        let e = self.last_used.entry(table).or_insert(t);
        if t > *e { *e = t; }
    }

    /// a digest of the state (replay determinism)
    pub fn digest(&self, x: &mut xxhash_rust::xxh3::Xxh3) {
        let mut t: Vec<(&Pk, &Vec<Option<Pk>>)> = self.tables.iter().collect();
        t.sort_by(|a, b| a.0.cmp(b.0));
        for (k, v) in t { x.update(k); for a in v { x.update(a.as_ref().map_or(&[0u8; 32][..], |a| &a[..])); } }
        let mut s: Vec<(&Pk, &(St, u64))> = self.st.iter().collect();
        s.sort_by(|a, b| a.0.cmp(b.0));
        for (k, (st, t0)) in s { x.update(k); x.update(format!("{st:?}").as_bytes()); x.update(&t0.to_le_bytes()); }
        let mut g: Vec<&Pk> = self.given_up.iter().collect();
        g.sort();
        for k in g { x.update(k); x.update(b"GaveUp"); }
        x.update(&(self.n_waiting as u64).to_le_bytes());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const MS: u64 = 1_000_000;
    fn k(n: u8) -> Pk { [n; 32] }
    fn events<W>(a: &mut Alts<W>) -> Vec<(&'static str, u32, Option<u64>)> { a.events.drain(..).map(|e| (e.event, e.attempt, e.next_retry_ms)).collect() }

    /// PLAN WP-04 acceptance, the lookup-table retry schedule (I-6): a failed fetch is retried at 50 ms, 250 ms, 1 s and
    /// 5 s, then every 30 s, and given up 10 minutes after the first failure; its waiters wait meanwhile and are released
    /// on success; a table that never resolves drops its waiters, and later transactions that need it are dropped
    #[test]
    fn retry_schedule_and_give_up() {
        let mut a: Alts<u32> = Alts::new(Policy::default());
        let mut f = Vec::new();
        assert_eq!(a.need(&[k(1)], 7, 0, &mut f), Need::Wait);
        assert_eq!((f.clone(), events(&mut a)), (vec![k(1)], vec![("fetch_start", 1, None)]));
        let mut t = 0;
        let mut seen = Vec::new();
        for _ in 0..6 {
            f.clear();
            assert!(a.on_answer(k(1), Answer::Error("429".into()), t, &mut f).is_empty());
            let e = events(&mut a);
            let next = e.iter().find(|x| x.0 == "retry_scheduled").and_then(|x| x.2).unwrap();
            seen.push(next);
            assert_eq!(a.next_retry(), Some(t + next * MS));
            a.due(t + next * MS - 1, &mut f);
            assert!(f.is_empty(), "not before its time");
            t += next * MS;
            a.due(t, &mut f);
            assert_eq!(f, vec![k(1)]);
        }
        assert_eq!(seen, vec![50, 250, 1_000, 5_000, 30_000, 30_000]);
        assert_eq!(a.waiting_txs(), 1, "the waiter waits through the retries");
        // success: the waiter is released
        f.clear();
        let w = a.on_answer(k(1), Answer::Found(vec![k(9); 3]), t, &mut f);
        assert_eq!((w, a.waiting_txs(), a.tables[&k(1)][2]), (vec![7], 0, Some(k(9))));
        // a table that never resolves: given up after 600 s
        a.need(&[k(2)], 8, t, &mut f);
        let t0 = t;
        loop {
            f.clear();
            a.on_answer(k(2), Answer::Missing, t, &mut f);
            if a.gave_up() == 1 { break; }
            t = a.next_retry().unwrap();
            a.due(t, &mut f);
        }
        assert!(t - t0 >= 600_000 * MS && t - t0 < 630_000 * MS);
        assert_eq!((a.waiting_txs(), a.dropped_gave_up), (0, 1));
        assert_eq!(a.need(&[k(2)], 9, t, &mut f), Need::Drop("alt_gave_up"));
    }

    /// I-6: at most `max_inflight` fetches at once (the rest queue and start as answers come back); the waiters are
    /// capped (`wait_cap`, the oldest dropped and counted)
    #[test]
    fn concurrency_and_wait_caps() {
        let mut a: Alts<u32> = Alts::new(Policy { max_inflight: 2, wait_cap: 3, ..Policy::default() });
        let mut f = Vec::new();
        for n in 1..=4u8 { a.need(&[k(n)], n as u32, 0, &mut f); }
        assert_eq!((f.clone(), a.inflight()), (vec![k(1), k(2)], 2));
        assert_eq!((a.waiting_txs(), a.dropped_cap), (3, 1), "the oldest waiter dropped");
        f.clear();
        a.on_answer(k(1), Answer::Found(vec![k(5)]), 1, &mut f);
        assert_eq!((f, a.inflight()), (vec![k(3)], 2), "a queued table starts when a slot frees");
        // a table learned from a feed while being retried is known again
        let mut f = Vec::new();
        a.on_answer(k(2), Answer::Error("x".into()), 2, &mut f);
        a.learned(k(2));
        assert!(a.next_retry().is_none());
    }
}

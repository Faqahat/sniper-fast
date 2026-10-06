//! Lookup tables (PLAN WP-04 item 7; PLAN-ADDENDUM I-6). A transaction that loads addresses from a lookup table the
//! engine does not know waits while the table is fetched (on the background runtime). arb-lab cached a failed fetch as
//! "missing" for the whole run: in cmp2 arbx dropped 5,001 transactions as `alt_unknown` against the old bot's ~610,
//! after starting with an empty cache during an RPC 429 burst. Here:
//! - a failed fetch (an RPC error, or no such account yet) is retried at `retry_ms` (50 ms, 250 ms, 1 s, 5 s) after each
//!   failure, then every `retry_every_s` (30 s), until `give_up_s` (10 minutes) after the first failure;
//! - at most `max_inflight` tables are fetched at once; the rest queue;
//! - transactions wait while their table's fetch or retry is pending (at most `wait_cap` of them, the oldest dropped
//!   and counted) and are dropped only when the table is given up;
//! - the previous segment's `alts-final` can be preloaded at boot: the tables a transaction used in the last
//!   `[alts] preload_max_age_h` hours, at most `preload_max_tables` (review WP-04 #11: `last_used` is kept per table and
//!   written to alts-final, so the preloaded set no longer grows across a campaign);
//! - every transition is an `alts.jsonl` event (MEASUREMENT §4.26); the full dump stays `alts-final` at stop.
//! The retry times are engine times, checked by the engine's timers: deterministic under replay (the journal holds the
//! fetch answers as ALT records).
//!
//! FT-000 (field test of 2026-10-05, S1-1 and S1-4):
//! - **Batched fetches** ([`Fetcher`]). Each fetch asked for one table (`rpc.accounts(&[table])`): 11,063 requests in 30
//!   minutes, 76% of the RPC budget Haan and Shyft share, so the chain fetch starved. The engine now hands each table to
//!   the fetcher, which sends up to `batch_max` (100) distinct tables in one getMultipleAccounts, at most
//!   `calls_inflight` (2) requests at once, through the provider buckets as role `alt`: the tables asked for while a
//!   request waits for its token ride on the next one. Each table's answer still comes back as its own `Event::Alt` (an
//!   ALT journal record), so the engine and its replay are unchanged by the batching.
//! - **A bounded cache.** It held every table ever seen: 19,143 tables after 30 minutes, 350 more a minute, the RSS
//!   growing 12 MB a minute with no plateau. Tables are now stored at their own length, not 256 slots (FT-000's set:
//!   103.6 MB instead of 162.9 MB by [`table_bytes`]; 162 slots a table on average), and past `max_tables` tables or
//!   `max_bytes` bytes (33 a slot plus 64 a table) the least recently used are evicted down to 90% of the cap: the
//!   oldest by when a transaction last used them or they were fetched or learned (a preloaded table nobody used yet
//!   first: its clock is 0), never one being fetched, waited for, or used by the input being handled. An evicted table
//!   needed again is fetched again (`fetch_start` with `refetch`). Each eviction is an alts.jsonl `evicted` event (with
//!   how long the table had been idle) and an ALT journal record (`found` 4): the cache follows only from the journaled
//!   inputs and the journaled caps (engine_init's knobs), so a replay evicts the same tables at the same inputs and
//!   checks them against the record (`ReplayStats::alt_evict_mismatches`).
use crate::feeds::Event;
use crate::tx::Pk;
use rustc_hash::{FxHashMap as HashMap, FxHashSet as HashSet};
use std::collections::VecDeque;
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::Arc;

/// The retry policy and the cache's bounds (`[alts]`)
#[derive(Clone, Debug, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
pub struct Policy {
    pub retry_ms: Vec<u64>,
    pub retry_every_s: u64,
    pub give_up_s: u64,
    pub wait_cap: usize,
    /// tables fetched at once, at most
    pub max_inflight: usize,
    /// FT-000: tables in one getMultipleAccounts, such requests at once, and at most one request every `call_every_ms`
    /// unless its batch is full (the fetcher's; nothing the engine decides depends on them)
    #[serde(default = "batch_max")]
    pub batch_max: usize,
    #[serde(default = "calls_inflight")]
    pub calls_inflight: usize,
    #[serde(default = "call_every_ms")]
    pub call_every_ms: u64,
    /// FT-000: the cache's caps, tables and bytes (0: none; an engine_init record written before them has none)
    #[serde(default)]
    pub max_tables: usize,
    #[serde(default)]
    pub max_bytes: u64,
}

fn batch_max() -> usize { 100 }
fn calls_inflight() -> usize { 2 }
fn call_every_ms() -> u64 { 500 }

impl Default for Policy {
    fn default() -> Self {
        Policy { retry_ms: vec![50, 250, 1_000, 5_000], retry_every_s: 30, give_up_s: 600, wait_cap: 10_000, max_inflight: 16, batch_max: batch_max(),
            calls_inflight: calls_inflight(), call_every_ms: call_every_ms(), max_tables: 0, max_bytes: 0 }
    }
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

/// One alts.jsonl event (MEASUREMENT §4.26). FT-000 (2.1): `idle_ms` (an `evicted` table: since a transaction last used
/// it, or since it was fetched or learned; null for a preloaded table no transaction used) and `refetch` (a `fetch_start`
/// of a table evicted before)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Ev { pub table: Pk, pub event: &'static str, pub n_addrs: Option<usize>, pub attempt: u32, pub next_retry_ms: Option<u64>, pub waiting_txs: usize,
    pub err: Option<String>, pub idle_ms: Option<u64>, pub refetch: bool }

/// what `need` decided for a transaction
#[derive(Debug, PartialEq, Eq)]
pub enum Need { Wait, Drop(&'static str) }

/// the bytes a table of `slots` entries counts for against `max_bytes` (33 a slot: an `Option<Pk>`; 64 for the table)
pub fn table_bytes(slots: usize) -> u64 { 64 + 33 * slots as u64 }

/// a table holds at most this many entries (an address lookup table's limit)
pub const MAX_ENTRIES: usize = 256;

pub struct Alts<W> {
    pub policy: Policy,
    /// tables, possibly partial: entries learned from feeds that send loaded addresses, or the whole table from a fetch;
    /// each at its own length (an index past it is not known). Changed only through `Alts` (the cache's accounting)
    tables: HashMap<Pk, Vec<Option<Pk>>>,
    /// the bytes `tables` counts for (`table_bytes` of each)
    bytes: u64,
    /// the tables being fetched, queued or retried (with when their first attempt started); given-up ones are kept apart
    /// (`given_up`), so the per-input scans (`next_retry`) see only the work in progress (review WP-04 N6)
    st: HashMap<Pk, (St, u64)>,
    given_up: HashSet<Pk>,
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
    /// FT-000: the cache's LRU clock per table: the latest of its last use and when it was fetched or learned (0 for a
    /// preloaded table until a transaction uses it)
    touch: HashMap<Pk, u64>,
    /// tables evicted lately (when), to name a later fetch of one a refetch; bounded
    evicted_at: HashMap<Pk, u64>,
    /// the tables evicted since the engine last took them (`take_evicted`: its ALT `found` 4 journal record)
    evicted_log: Vec<Pk>,
    /// totals: waiters dropped by the cap and by a give-up; tables evicted; fetches of evicted tables
    pub dropped_cap: u64,
    pub dropped_gave_up: u64,
    pub evicted_total: u64,
    pub refetch_total: u64,
    /// a running hash of every table evicted, in order (the ALT `found` 4 record carries it with `evicted_total`: a
    /// replay that evicted the same tables at the same inputs has the same pair there)
    pub evict_hash: u64,
}

impl<W> Alts<W> {
    pub fn new(policy: Policy) -> Alts<W> {
        Alts { policy, tables: HashMap::default(), bytes: 0, st: HashMap::default(), given_up: Default::default(), queue: VecDeque::new(), inflight: 0,
            waiting: HashMap::default(), wait_order: VecDeque::new(), wait_seq: 0, n_waiting: 0, events: Vec::new(), last_used: HashMap::default(),
            touch: HashMap::default(), evicted_at: HashMap::default(), evicted_log: Vec::new(), dropped_cap: 0, dropped_gave_up: 0, evicted_total: 0,
            refetch_total: 0, evict_hash: 0 }
    }

    pub fn inflight(&self) -> usize { self.inflight }
    pub fn waiting_txs(&self) -> usize { self.n_waiting }
    pub fn pending_retries(&self) -> usize { self.st.values().filter(|s| matches!(s.0, St::Retry { .. } | St::Queued(_))).count() }
    pub fn gave_up(&self) -> usize { self.given_up.len() }
    /// the tables held
    pub fn len(&self) -> usize { self.tables.len() }
    pub fn is_empty(&self) -> bool { self.tables.is_empty() }
    /// the bytes they count for (`table_bytes`)
    pub fn bytes(&self) -> u64 { self.bytes }
    /// a table's entries (None: not held)
    pub fn get(&self, table: &Pk) -> Option<&[Option<Pk>]> { self.tables.get(table).map(|v| v.as_slice()) }
    /// every table held, with its entries (any order)
    pub fn iter(&self) -> impl Iterator<Item = (&Pk, &Vec<Option<Pk>>)> { self.tables.iter() }
    /// the tables held, read-only (WP-06's size budget reads its candidates from them: `exec::AltSource`; merge of WP-06
    /// with the FT-000 fixes, whose cache changes them only through `Alts`)
    pub fn tables(&self) -> &HashMap<Pk, Vec<Option<Pk>>> { &self.tables }

    fn ev(&mut self, table: Pk, event: &'static str, attempt: u32, next_retry_ms: Option<u64>, err: Option<String>) {
        let waiting = self.waiting.get(&table).map_or(0, |v| v.len());
        let n_addrs = self.tables.get(&table).map(|v| v.iter().filter(|a| a.is_some()).count());
        self.events.push(Ev { table, event, n_addrs, attempt, next_retry_ms, waiting_txs: waiting, err, idle_ms: None, refetch: false });
    }

    /// a table's entries replaced or extended: its bytes accounted, its LRU clock set to `t`
    fn put(&mut self, table: Pk, v: Vec<Option<Pk>>, t: u64) {
        let new = table_bytes(v.len());
        if let Some(old) = self.tables.insert(table, v) { self.bytes = self.bytes.saturating_sub(table_bytes(old.len())); }
        self.bytes += new;
        self.touched(table, t);
    }

    fn touched(&mut self, table: Pk, t: u64) {
        let e = self.touch.entry(table).or_insert(t);
        if t > *e { *e = t; }
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
            // FT-000: the first fetch of a table the cache evicted is a refetch (counted, and marked on its event)
            if attempt == 1 && self.evicted_at.remove(&table).is_some() {
                self.refetch_total += 1;
                if let Some(e) = self.events.last_mut() { e.refetch = true; }
            }
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
                let v: Vec<Option<Pk>> = addrs.iter().take(MAX_ENTRIES).map(|k| Some(*k)).collect();
                self.put(table, v, t);
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
        self.enforce(t);
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

    /// Entries of `table` learned at `t` from a feed that sends loaded addresses: (index, address) pairs (an index is a
    /// u8: always within the table's limit). True when one of them was new. The table grows to exactly the length its
    /// highest index needs (no amortized slack: what `table_bytes` counts is what it holds)
    pub fn learn(&mut self, table: Pk, entries: &[(u8, Pk)], t: u64) -> bool {
        let had = self.tables.remove(&table);
        if let Some(old) = &had { self.bytes = self.bytes.saturating_sub(table_bytes(old.len())); }
        let mut v = had.unwrap_or_default();
        let need = entries.iter().map(|e| e.0 as usize + 1).max().unwrap_or(0);
        if v.len() < need {
            v.reserve_exact(need - v.len());
            v.resize(need, None);
        }
        let mut new = false;
        for &(i, k) in entries {
            let i = i as usize;
            if v[i].is_none() { v[i] = Some(k); new = true; }
        }
        self.put(table, v, t);
        self.enforce(t);
        new
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

    /// a table from the previous segment's alts-final (boot), with when it was last used there. Its LRU clock is 0, not
    /// that time: the journal's preload record does not carry it, and a replay must order the cache as the run did (a
    /// preloaded table no transaction of this segment has used goes first, by address). `last_used` still goes to
    /// alts-final
    pub fn preload(&mut self, table: Pk, addrs: Vec<Option<Pk>>, last_used: Option<u64>) {
        let mut v = addrs;
        v.truncate(MAX_ENTRIES);
        while v.last().is_some_and(|a| a.is_none()) { v.pop(); }
        v.shrink_to_fit();
        self.put(table, v, 0);
        if let Some(t) = last_used { self.last_used.insert(table, t); }
        self.ev(table, "preloaded", 0, None, None);
        self.enforce(0);
    }

    /// a transaction used `table` at `t` (its addresses resolved one)
    #[inline]
    pub fn used(&mut self, table: Pk, t: u64) {
        let e = self.last_used.entry(table).or_insert(t);
        if t > *e { *e = t; }
        self.touched(table, t);
    }

    fn capped(&self) -> bool {
        (self.policy.max_tables > 0 && self.tables.len() > self.policy.max_tables) || (self.policy.max_bytes > 0 && self.bytes > self.policy.max_bytes)
    }

    /// FT-000 (S1-4): over a cap, evict the least recently used tables (by their LRU clock, then address) down to 90% of
    /// it. Never a table being fetched, queued or retried, one transactions wait for, or one touched at `t` (the input
    /// being handled uses it)
    fn enforce(&mut self, t: u64) {
        if !self.capped() { return; }
        let keep_n = if self.policy.max_tables > 0 { self.policy.max_tables * 9 / 10 } else { usize::MAX };
        let keep_b = if self.policy.max_bytes > 0 { self.policy.max_bytes / 10 * 9 } else { u64::MAX };
        let mut cand: Vec<(u64, Pk)> = self.tables.keys().filter(|k| !self.st.contains_key(*k) && !self.waiting.contains_key(*k))
            .map(|k| (self.touch.get(k).copied().unwrap_or(0), *k)).filter(|(at, _)| *at < t || t == 0).collect();
        // the oldest first, (clock, address) being unique: only the ones the table cap needs are ordered at first (this
        // runs on the engine thread: about 2,000 of the 20,000 tables each time), the rest only if the byte cap needs
        // more (the same order as sorting them all)
        let first = self.tables.len().saturating_sub(keep_n).min(cand.len());
        if first > 0 && first < cand.len() { cand.select_nth_unstable(first - 1); }
        cand[..first].sort_unstable();
        let mut rest_sorted = first == cand.len();
        for i in 0..cand.len() {
            if self.tables.len() <= keep_n && self.bytes <= keep_b { break; }
            if i == first && !rest_sorted { cand[first..].sort_unstable(); rest_sorted = true; }
            let (at, k) = cand[i];
            let Some(v) = self.tables.remove(&k) else { continue };
            self.bytes = self.bytes.saturating_sub(table_bytes(v.len()));
            let n_addrs = v.iter().filter(|a| a.is_some()).count();
            self.touch.remove(&k);
            self.last_used.remove(&k);
            self.evicted_at.insert(k, t);
            self.evicted_log.push(k);
            self.evicted_total += 1;
            self.evict_hash = xxhash_rust::xxh3::xxh3_64_with_seed(&k, self.evict_hash);
            // idle since its LRU clock; null for a preloaded table no transaction of this segment used (clock 0)
            self.events.push(Ev { table: k, event: "evicted", n_addrs: Some(n_addrs), attempt: 0, next_retry_ms: None, waiting_txs: 0, err: None,
                idle_ms: (at > 0).then(|| t.saturating_sub(at) / 1_000_000), refetch: false });
        }
        // the refetch memory stays bounded: past twice the cap (at least 20,000), the older half is forgotten
        let limit = 2 * self.policy.max_tables.max(10_000);
        if self.evicted_at.len() > limit {
            let mut v: Vec<(u64, Pk)> = self.evicted_at.iter().map(|(k, at)| (*at, *k)).collect();
            v.sort_unstable();
            for (_, k) in v.iter().take(v.len() / 2) { self.evicted_at.remove(k); }
        }
    }

    /// the tables evicted since the last call (the engine's ALT `found` 4 journal record; a replay compares them)
    pub fn take_evicted(&mut self) -> Vec<Pk> { std::mem::take(&mut self.evicted_log) }

    /// a digest of the state (replay determinism). A table is hashed at 256 slots whatever its stored length (the digest
    /// of a run recorded before FT-000's compact tables is the same); with a cap, the LRU clocks and the eviction count too
    pub fn digest(&self, x: &mut dyn crate::engine::Fold) {
        let mut t: Vec<(&Pk, &Vec<Option<Pk>>)> = self.tables.iter().collect();
        t.sort_by(|a, b| a.0.cmp(b.0));
        for (k, v) in t {
            x.update(k);
            for i in 0..MAX_ENTRIES.max(v.len()) { x.update(v.get(i).copied().flatten().as_ref().map_or(&[0u8; 32][..], |a| &a[..])); }
        }
        let mut s: Vec<(&Pk, &(St, u64))> = self.st.iter().collect();
        s.sort_by(|a, b| a.0.cmp(b.0));
        for (k, (st, t0)) in s { x.update(k); x.update(format!("{st:?}").as_bytes()); x.update(&t0.to_le_bytes()); }
        let mut g: Vec<&Pk> = self.given_up.iter().collect();
        g.sort();
        for k in g { x.update(k); x.update(b"GaveUp"); }
        x.update(&(self.n_waiting as u64).to_le_bytes());
        if self.policy.max_tables > 0 || self.policy.max_bytes > 0 {
            let mut c: Vec<(&Pk, &u64)> = self.touch.iter().collect();
            c.sort();
            for (k, at) in c { x.update(k); x.update(&at.to_le_bytes()); }
            x.update(&self.evicted_total.to_le_bytes());
        }
    }
}

// ------------------------------------------------------------------ the batched fetcher (FT-000 S1-1)

/// A pending answer of a lookup-table source
pub type Accounts = std::pin::Pin<Box<dyn std::future::Future<Output = Result<Vec<Option<Vec<u8>>>, String>> + Send>>;

/// What fetches lookup-table accounts: the run's RPC client (role `alt`, through the provider buckets), or a test's
pub trait Source: Clone + Send + Sync + 'static {
    /// the accounts of `tables`, in order (None: no such account), or why the request failed
    fn fetch_tables(&self, tables: Vec<Pk>) -> Accounts;
}

impl Source for crate::rpc::Rpc {
    fn fetch_tables(&self, tables: Vec<Pk>) -> Accounts {
        let me = self.clone();
        Box::pin(async move {
            match me.accounts(&tables).await {
                Ok((_, v)) if v.len() == tables.len() => Ok(v.into_iter().map(|a| a.map(|a| a.data)).collect()),
                Ok((_, v)) => Err(format!("{} values for {} accounts", v.len(), tables.len())),
                Err(e) => Err(crate::rpc::scrub(&format!("{e:#}"))),
            }
        })
    }
}

/// What the fetcher did (status.jsonl `alts`): tables asked for, requests sent, tables they carried, the largest
#[derive(Default, Debug)]
pub struct FetchStats { pub requests: AtomicU64, pub calls: AtomicU64, pub tables: AtomicU64, pub max_batch: AtomicU64 }

/// The engine's lookup-table fetcher: tables asked for (`request`) are sent in batches of at most `batch_max` distinct
/// tables a getMultipleAccounts, at most `calls_inflight` requests at once and one every `every` at most (a full batch
/// goes at once); the tables asked for while a request waits, runs or is paced go on the next one. Every table's answer
/// comes back on the engine's channel as its own `Event::Alt`. FT-000's demand (about 6 new tables a second, 11,009 in 30
/// minutes) then takes about 2 requests a second instead of 6: a table waits at most `every` more before it is asked
pub struct Fetcher { tx: tokio::sync::mpsc::UnboundedSender<Pk>, pub stats: Arc<FetchStats> }

impl Fetcher {
    /// Start the fetcher on `rt`; its answers go to `back`
    pub fn start<S: Source>(src: S, rt: &tokio::runtime::Handle, back: crossbeam_channel::Sender<Event>, batch_max: usize, calls_inflight: usize,
        every: std::time::Duration) -> Fetcher {
        let (tx, rx) = tokio::sync::mpsc::unbounded_channel();
        let stats = Arc::new(FetchStats::default());
        rt.spawn(run(rx, src, back, batch_max.clamp(1, 100), calls_inflight.max(1), every, stats.clone()));
        Fetcher { tx, stats }
    }
    /// fetch `table` (its answer: an `Event::Alt`)
    pub fn request(&self, table: Pk) {
        self.stats.requests.fetch_add(1, Relaxed);
        let _ = self.tx.send(table);
    }
}

/// a fetched account as the engine's event: a lookup table's entries, no such account, or why not
pub fn answer_event(table: Pk, r: &Result<Option<Vec<u8>>, String>) -> Event {
    match r {
        Ok(Some(data)) => match crate::tx::parse_alt(data) {
            Some(addrs) => Event::Alt { table, addrs: Some(Arc::new(addrs)), err: None },
            None => Event::Alt { table, addrs: None, err: Some("not a lookup table".into()) },
        },
        Ok(None) => Event::Alt { table, addrs: None, err: None },
        Err(e) => Event::Alt { table, addrs: None, err: Some(e.clone()) },
    }
}

#[allow(clippy::too_many_arguments)]
async fn run<S: Source>(mut rx: tokio::sync::mpsc::UnboundedReceiver<Pk>, src: S, back: crossbeam_channel::Sender<Event>, batch_max: usize, calls_inflight: usize,
    every: std::time::Duration, stats: Arc<FetchStats>) {
    let slots = Arc::new(tokio::sync::Semaphore::new(calls_inflight));
    let mut queue: VecDeque<Pk> = VecDeque::new();
    let mut queued: HashSet<Pk> = HashSet::default();
    let mut next_at = tokio::time::Instant::now();
    loop {
        if queue.is_empty() {
            match rx.recv().await { Some(t) => { if queued.insert(t) { queue.push_back(t); } } None => return }
        }
        let Ok(slot) = slots.clone().acquire_owned().await else { return };
        while let Ok(t) = rx.try_recv() { if queued.insert(t) { queue.push_back(t); } }
        // the pace: one request every `every` at most, unless its batch is full
        if queue.len() < batch_max { tokio::time::sleep_until(next_at).await; }
        // everything asked for while the slot was busy, or while the request was paced, rides on it
        while let Ok(t) = rx.try_recv() { if queued.insert(t) { queue.push_back(t); } }
        next_at = tokio::time::Instant::now() + every;
        let n = queue.len().min(batch_max);
        let batch: Vec<Pk> = queue.drain(..n).collect();
        for t in &batch { queued.remove(t); }
        stats.calls.fetch_add(1, Relaxed);
        stats.tables.fetch_add(n as u64, Relaxed);
        stats.max_batch.fetch_max(n as u64, Relaxed);
        let (src, back) = (src.clone(), back.clone());
        tokio::spawn(async move {
            let r = src.fetch_tables(batch.clone()).await;
            for (i, table) in batch.iter().enumerate() {
                let one = match &r { Ok(v) => Ok(v.get(i).cloned().flatten()), Err(e) => Err(e.clone()) };
                let _ = back.send(answer_event(*table, &one));
            }
            drop(slot);
        });
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
        assert_eq!((w, a.waiting_txs(), a.get(&k(1)).unwrap()[2]), (vec![7], 0, Some(k(9))));
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

    /// FT-000 (S1-4): tables are kept at their own length (a fetched table of 3 entries counts 3 slots, not 256), learned
    /// entries extend a table as far as their index, and the bytes follow both
    #[test]
    fn tables_are_stored_compactly() {
        let mut a: Alts<u32> = Alts::new(Policy::default());
        let mut f = Vec::new();
        a.need(&[k(1)], 1, 0, &mut f);
        a.on_answer(k(1), Answer::Found(vec![k(7); 3]), 1, &mut f);
        assert_eq!((a.get(&k(1)).unwrap().len(), a.bytes()), (3, table_bytes(3)));
        assert!(a.learn(k(2), &[(5, k(8)), (1, k(9))], 2), "new entries");
        assert_eq!(a.get(&k(2)).unwrap(), &[None, Some(k(9)), None, None, None, Some(k(8))][..]);
        assert!(!a.learn(k(2), &[(1, k(9))], 3), "nothing new");
        assert!(a.learn(k(2), &[(9, k(6))], 4));
        assert_eq!((a.get(&k(2)).unwrap().len(), a.bytes()), (10, table_bytes(3) + table_bytes(10)));
        // a preloaded table drops its trailing gaps (an older file padded every table to 256)
        let mut v = vec![Some(k(3)), None, Some(k(4))];
        v.resize(256, None);
        a.preload(k(3), v, Some(5));
        assert_eq!((a.get(&k(3)).unwrap().len(), a.len()), (3, 3));
        assert_eq!(a.bytes(), table_bytes(3) + table_bytes(10) + table_bytes(3));
        // the digest of a compact table is the digest of the same table padded to 256 slots (a run recorded before)
        let pad = |a: &Alts<u32>| { let mut x = xxhash_rust::xxh3::Xxh3::new(); a.digest(&mut x); x.digest() };
        let mut b: Alts<u32> = Alts::new(Policy::default());
        b.tables.insert(k(1), { let mut v = vec![Some(k(7)); 3]; v.resize(256, None); v });
        let mut c: Alts<u32> = Alts::new(Policy::default());
        c.tables.insert(k(1), vec![Some(k(7)); 3]);
        assert_eq!(pad(&b), pad(&c));
    }

    /// FT-000 (S1-4): past `max_tables` the least recently used tables are evicted down to 90% of the cap (each an
    /// `evicted` event with its idle time, and in `take_evicted`), never one being fetched, waited for or used by the
    /// input being handled; one needed again is fetched again (`refetch`); a byte cap works the same; `last_used` keeps
    /// alts-final in step
    #[test]
    fn the_cache_is_bounded_by_lru_and_evicted_tables_are_fetched_again() {
        let mut a: Alts<u32> = Alts::new(Policy { max_tables: 10, ..Policy::default() });
        let mut f = Vec::new();
        // ten tables fetched at 1..=10 ms; table 1 used again at 20 ms
        for n in 1..=10u8 { a.need(&[k(n)], n as u32, n as u64 * MS, &mut f); a.on_answer(k(n), Answer::Found(vec![k(100 + n)]), n as u64 * MS, &mut f); }
        a.used(k(1), 20 * MS);
        assert_eq!((a.len(), a.evicted_total), (10, 0), "at the cap: nothing evicted");
        a.events.clear();
        // table 12 is being fetched (and waited for) when table 11 comes in: the cache goes to 9 tables, the least
        // recently used first (2, then 3: table 1 was used at 20 ms)
        a.need(&[k(12)], 12, 30 * MS, &mut f);
        a.on_answer(k(11), Answer::Found(vec![k(111)]), 30 * MS, &mut f);
        assert_eq!(a.len(), 9);
        let ev: Vec<(Pk, Option<u64>)> = a.events.iter().filter(|e| e.event == "evicted").map(|e| (e.table, e.idle_ms)).collect();
        assert_eq!(ev, vec![(k(2), Some(28)), (k(3), Some(27))], "the oldest by their LRU clock, with their idle time");
        assert_eq!(a.take_evicted(), vec![k(2), k(3)]);
        assert!(a.take_evicted().is_empty(), "taken once");
        assert!(a.get(&k(1)).is_some() && a.get(&k(11)).is_some() && a.last_used.get(&k(2)).is_none());
        // table 2 needed again: fetched again, marked a refetch
        a.events.clear();
        f.clear();
        a.need(&[k(2)], 2, 40 * MS, &mut f);
        assert_eq!(f, vec![k(2)]);
        let st = a.events.iter().find(|e| e.event == "fetch_start").unwrap();
        assert!(st.refetch && a.refetch_total == 1);
        // a table touched by the input being handled is never evicted, nor one being fetched or waited for
        let mut b: Alts<u32> = Alts::new(Policy { max_tables: 2, ..Policy::default() });
        let mut f = Vec::new();
        b.need(&[k(9)], 1, 0, &mut f);
        for n in 1..=4u8 { b.learn(k(n), &[(0, k(50 + n))], 100 * MS); }
        assert_eq!(b.len(), 4, "every table was touched by this input: none evicted");
        b.learn(k(5), &[(0, k(55))], 200 * MS);
        assert_eq!((b.len(), b.get(&k(5)).is_some()), (1, true), "the next input evicts down to 90% of 2 (one table): its own stays");
        // a byte cap: 3 tables of 10 slots fit in 4 * table_bytes(10)
        let mut c: Alts<u32> = Alts::new(Policy { max_bytes: 4 * table_bytes(10), ..Policy::default() });
        for n in 1..=5u8 { c.learn(k(n), &[(9, k(60 + n))], n as u64 * MS); }
        assert!(c.bytes() <= 4 * table_bytes(10) && c.evicted_total >= 1, "{} bytes, {} evicted", c.bytes(), c.evicted_total);
        assert!(c.get(&k(1)).is_none() && c.get(&k(5)).is_some(), "the oldest went first");
    }

    /// the evictions follow only from the inputs: two caches fed the same inputs evict the same tables at the same
    /// points and end with the same digest (what a replay of a journal relies on)
    #[test]
    fn evictions_are_deterministic() {
        let run = || {
            let mut a: Alts<u32> = Alts::new(Policy { max_tables: 50, ..Policy::default() });
            let mut f = Vec::new();
            let mut log = Vec::new();
            for i in 0..400u64 {
                let n = ((i * 7919) % 97) as u8;
                if i % 3 == 0 { a.learn(k(n), &[((i % 250) as u8, k(1))], i * MS); } else { a.used(k(n), i * MS); }
                if i % 5 == 0 { a.need(&[k(200)], i as u32, i * MS, &mut f); a.on_answer(k(200), Answer::Found(vec![k(2)]), i * MS, &mut f); }
                log.push(a.take_evicted());
            }
            let mut x = xxhash_rust::xxh3::Xxh3::new();
            a.digest(&mut x);
            (log, x.digest(), a.evicted_total)
        };
        let (l1, d1, n1) = run();
        let (l2, d2, n2) = run();
        assert!(n1 > 0, "the cap was reached");
        assert_eq!((l1, d1, n1), (l2, d2, n2));
    }

    #[derive(Clone)]
    struct FakeSource { calls: Arc<std::sync::Mutex<Vec<Vec<Pk>>>>, gate: Arc<tokio::sync::Semaphore> }
    impl Source for FakeSource {
        fn fetch_tables(&self, tables: Vec<Pk>) -> Accounts {
            let (calls, gate) = (self.calls.clone(), self.gate.clone());
            Box::pin(async move {
                // each request waits for a permit (a token of its bucket)
                let _p = gate.acquire().await.unwrap();
                calls.lock().unwrap().push(tables.clone());
                if tables.contains(&[0xEE; 32]) { return Err("HTTP 503".into()); }
                Ok(tables.iter().map(|t| match t[0] {
                    0xAA => None,
                    0xBB => Some(vec![1u8; 10]),
                    n => { let mut d = vec![0u8; 56]; d.extend([n; 32]); d.extend([n.wrapping_add(1); 32]); Some(d) }
                }).collect())
            })
        }
    }

    /// FT-000 (S1-1): the fetcher batches the tables asked for while its requests wait (deduplicated, at most
    /// `batch_max` a request, at most `calls_inflight` requests at once), and every table's answer comes back as its own
    /// event: found, no such account, not a lookup table, or the request's error
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn the_fetcher_batches_what_waits_and_answers_each_table() {
        let src = FakeSource { calls: Default::default(), gate: Arc::new(tokio::sync::Semaphore::new(0)) };
        let (tx, rx) = crossbeam_channel::unbounded();
        let f = Fetcher::start(src.clone(), &tokio::runtime::Handle::current(), tx, 100, 2, std::time::Duration::ZERO);
        // the first two tables leave at once (two requests, both waiting for their token); 250 more pile up meanwhile,
        // one of them twice. (Each step waits for the fetcher's request, not for a fixed time: a loaded host is slow)
        let calls_reach = |n: u64| {
            let stats = f.stats.clone();
            async move {
                let t0 = std::time::Instant::now();
                while stats.calls.load(Relaxed) < n && t0.elapsed() < std::time::Duration::from_secs(10) { tokio::time::sleep(std::time::Duration::from_millis(2)).await; }
                stats.calls.load(Relaxed)
            }
        };
        f.request(k(1));
        assert_eq!(calls_reach(1).await, 1);
        f.request(k(2));
        assert_eq!(calls_reach(2).await, 2);
        for n in 0..250u32 { let mut t = [0u8; 32]; t[0] = 3 + (n % 200) as u8; t[1] = (n / 200) as u8; f.request(t); }
        f.request([0xAA; 32]);
        f.request([0xBB; 32]);
        f.request([0xBB; 32]);
        tokio::time::sleep(std::time::Duration::from_millis(50)).await;
        assert_eq!(f.stats.calls.load(Relaxed), 2, "both slots held: the rest waits");
        src.gate.add_permits(1_000);
        let mut got = Vec::new();
        while got.len() < 254 {
            match rx.recv_timeout(std::time::Duration::from_secs(5)) { Ok(e) => got.push(e), Err(_) => break }
        }
        let calls = src.calls.lock().unwrap().clone();
        // (the order the requests got their permits in is the scheduler's: compared as a multiset)
        let mut sizes: Vec<usize> = calls.iter().map(|c| c.len()).collect();
        sizes.sort_unstable();
        assert_eq!(sizes, vec![1, 1, 52, 100, 100], "the first two alone, the rest in batches of at most 100, the repeated table once");
        assert!(calls.iter().any(|c| c == &vec![k(1)]) && calls.iter().any(|c| c == &vec![k(2)]));
        assert_eq!(f.stats.calls.load(Relaxed), 5);
        assert_eq!((f.stats.requests.load(Relaxed), f.stats.tables.load(Relaxed), f.stats.max_batch.load(Relaxed)), (255, 254, 100));
        assert_eq!(got.len(), 254, "one answer per table");
        let find = |t: Pk| got.iter().find_map(|e| match e { Event::Alt { table, addrs, err } if *table == t => Some((addrs.clone(), err.clone())), _ => None }).unwrap();
        assert_eq!(find(k(1)).0.map(|a| a.to_vec()), Some(vec![k(1), k(2)]));
        assert_eq!(find([0xAA; 32]), (None, None), "no such account");
        assert_eq!(find([0xBB; 32]).1.as_deref(), Some("not a lookup table"));
        // a failed request answers each of its tables with the error
        f.request([0xEE; 32]);
        f.request(k(3));
        let mut errs = 0;
        for _ in 0..2 { if let Ok(Event::Alt { err: Some(e), .. }) = rx.recv_timeout(std::time::Duration::from_secs(5)) { assert_eq!(e, "HTTP 503"); errs += 1; } }
        assert!(errs >= 1);
    }

    /// FT-000 (S1-4), measured on FT-000's own tables (a copy of segment 1, whose alts-final holds the 19,143 tables its
    /// cache ended with: `ARBX_FT000_RUN=<run dir>`): the heap they take as FT-000's build held them (256 slots each: a
    /// fetched table collected then padded, a learned one made at 256) and as `Alts` holds them now (their own length),
    /// from glibc's allocator statistics; then what the cap keeps of 3 such sets in a row (about 3 hours of FT-000's
    /// growth). Prints the measurement (the FT-000 fixes' commit); run alone: other tests' allocations would count
    #[test]
    #[ignore = "needs a copy of FT-000's segment 1 (ARBX_FT000_RUN)"]
    fn ft000_lookup_table_cache_memory() {
        let Ok(dir) = std::env::var("ARBX_FT000_RUN") else { return };
        let rows = crate::rec::read_jsonl(std::path::Path::new(&dir), "alts-final").unwrap();
        let tables: Vec<(Pk, Vec<Option<Pk>>)> = rows.iter().filter_map(|r| {
            let mut a: Vec<Option<Pk>> = r["addrs"].as_array()?.iter().map(|x| x.as_str().map(crate::tx::pk)).collect();
            while a.last().is_some_and(|x| x.is_none()) { a.pop(); }
            Some((crate::tx::pk(r["table"].as_str()?), a))
        }).collect();
        let heap = || { let m = unsafe { libc::mallinfo2() }; (m.uordblks + m.hblkhd) as f64 };
        let mb = |b: f64| b / 1e6;
        // FT-000's build
        let h0 = heap();
        let mut old: HashMap<Pk, Vec<Option<Pk>>> = HashMap::default();
        for (t, a) in &tables {
            let v = if a.iter().all(|x| x.is_some()) {
                let mut v: Vec<Option<Pk>> = a.iter().copied().collect();
                v.resize(256.max(v.len()), None);
                v
            } else {
                let mut v = vec![None; 256];
                for (i, x) in a.iter().enumerate() { v[i] = *x; }
                v
            };
            old.insert(*t, v);
        }
        let h_old = heap() - h0;
        drop(old);
        // now: their own length, the cap's accounting beside the heap
        let h1 = heap();
        let mut a: Alts<u32> = Alts::new(Policy { max_tables: 20_000, max_bytes: 192 << 20, ..Policy::default() });
        for (t, v) in &tables { a.preload(*t, v.clone(), None); }
        let (h_new, n, acct) = (heap() - h1, a.len(), a.bytes());
        assert_eq!((n, a.evicted_total), (tables.len(), 0), "19,143 tables: under the 20,000 cap");
        // the cap: two more sets of new tables (other addresses), each learned at a later time, as a long run keeps adding them
        for round in 1..=2u8 {
            for (i, (t, v)) in tables.iter().enumerate() {
                let mut k = *t;
                k[31] ^= round;
                k[30] ^= 0x5A;
                let e: Vec<(u8, Pk)> = v.iter().enumerate().filter_map(|(j, x)| x.map(|x| (j as u8, x))).collect();
                a.learn(k, &e, (round as u64 * 100_000 + i as u64 + 1) * 1_000_000);
            }
        }
        let h_cap = heap() - h1;
        eprintln!("FT-000 segment 1's {} lookup tables: FT-000's build {:.1} MB of heap ({:.0} B a table); now {:.1} MB ({:.0} B a table; the cap counts {:.1} MB); \
            after two more such sets under the 20,000-table cap: {} tables, {:.1} MB counted, {:.1} MB of heap, {} evicted",
            tables.len(), mb(h_old), h_old / tables.len() as f64, mb(h_new), h_new / n as f64, mb(acct as f64), a.len(), mb(a.bytes() as f64), mb(h_cap), a.evicted_total);
        assert!(a.len() <= 20_000 && a.evicted_total >= 2 * tables.len() as u64 - 2_000, "bounded");
        assert!(h_new < h_old, "smaller at their own length");
    }
}

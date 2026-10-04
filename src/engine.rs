//! The engine: one thread, one loop over every event from every feed.
//!
//!   Tx      first copy of a signature: resolve lookup tables, decode venue swaps on watched pools (the triggers),
//!           predict each pool after the swap, search the pair's other pools for a profitable round trip, record it.
//!           Later copies from other feeds: timestamp only (that is how feeds are scored).
//!   Account pool-state update: store it; check our prediction against the trigger's real effect; watch who touches
//!           the opportunity's pools next (the taker) and whether the trigger itself landed.
//!   Slot    current slot.
//!
//! Shadow mode only: nothing is signed or sent. Every trigger and opportunity is written as one JSON line with its
//! per-feed arrival times and our own stage timings (rx -> decoded -> engine -> resolved -> decided).
use crate::config::StrategyCfg;
use crate::lat::Series;
use crate::feeds::{clock::now_ns, Arrival, Event, FeedCounters, Interest};
use crate::rec::{self, Rec, Record};
use crate::pda::AtaCache;
use crate::pools::{self, pair_key, Registry};
use crate::store::{Snap, Store};
use crate::tx::{b58, Pk, Tx};
use crate::venues::{cp, dlmm, PendingSwap, PoolMeta, Venue, WSOL};
use serde_json::{json, Value};
use rustc_hash::{FxHashMap as HashMap, FxHashSet as HashSet};
use std::collections::VecDeque;
use std::io::Write as _;
use std::sync::Arc;
use crossbeam_channel::{Receiver, RecvTimeoutError, Sender, TryRecvError};

/// How long a signature's arrival record is kept (later copies from slower feeds still count)
const SIG_KEEP_NS: u64 = 10_000_000_000;
/// A prediction is used for at most this long, or until the pool shows the trigger's real effect
const PRED_KEEP_NS: u64 = 1_500_000_000;
const LAMPORTS_PER_SOL: f64 = 1e9;

/// most feeds one run can follow (arrival times are kept in a fixed array: no allocation per signature)
pub const MAX_FEEDS: usize = 24;
/// how long the engine spins on an empty queue before it blocks (wake-up latency vs. CPU)
const SPIN_NS: u64 = 50_000;

struct SigInfo { first_t: u64, first_feed: u16, arr: [u64; MAX_FEEDS], trigger: Option<(Pk, Venue, u64)>, slot: u64 }
impl SigInfo {
    fn arrivals(&self) -> impl Iterator<Item = (u16, u64)> + '_ { self.arr.iter().enumerate().filter(|(_, t)| **t != 0).map(|(f, t)| (f as u16, *t)) }
}

/// A pool's predicted state after pending (seen, not yet landed) swaps
enum Pred { Cp(cp::CpSnap), Dlmm(dlmm::Overlay), Damm(crate::venues::dammv2::DammPool) }
struct PredEntry { trig: [u8; 64], t: u64, pred: Pred }

/// Stage times (ns). Decoded hints: shred/tx receive, decoded, engine dequeue, lookups resolved, decided. State
/// triggers (WP-00, F13): rx = decoded = the receive time of the first pool update stamped with the transaction,
/// engine = that update's dequeue, resolved = the evaluation's start, decided = after the route search.
#[derive(Clone, serde::Serialize)]
struct Stages { rx: u64, decoded: u64, engine: u64, resolved: u64, decided: u64 }

/// a pool moved by transaction `txn`, waiting until every account update of `txn` has arrived (see `state_pending`):
/// the receive time and engine dequeue time of the pool's first update stamped `txn`
struct StatePending { pool: usize, txn: [u8; 64], slot: u64, t_recv: u64, t_engine: u64 }

/// `Engine::lat` series, in order: the decoded-trigger stages (v1 names, A.8: only priced triggers, decoded_sends =
/// true), the state path's (WP-00, F13), and a hint's receive-to-done (WP-00 review F9: a hint is not priced, so its
/// times would shrink the v1 series' meaning)
const LAT_SERIES: [&str; 9] = ["rx_to_decoded", "decoded_to_engine", "engine_to_resolved", "resolved_to_decided", "rx_to_decided",
    "state_recv_to_engine", "state_engine_to_decided", "state_recv_to_decided", "hint_rx_to_done"];
const LAT_STATE_RECV_TO_ENGINE: usize = 5;
const LAT_HINT_RX_TO_DONE: usize = 8;
/// how many (transaction, pool) first-update times `state_first` keeps (the oldest go first)
const STATE_FIRST_MAX: usize = 4_096;

struct Opp {
    id: u64,
    trig: [u8; 64],
    trig_feed: u16,
    slot: u64,
    st: Stages,
    trig_pool: Pk,
    buy: Pk,
    sell: Pk,
    mint: Pk,
    size: u64,
    gross: i64,
    net: i64,
    cu: u64,
    crossed: (u32, u32),
    deadline: u64,
    /// the trigger's own compute-unit price (micro-lamports per CU)
    trig_cu_price: Option<u64>,
    landed: Option<u64>,
    /// (pool, txn signature, slot, time the update reached us) of every later update to buy/sell pools
    touches: Vec<(Pk, [u8; 64], u64, u64)>,
}

/// A trigger's prediction, kept until its real effect shows up (accuracy check)
struct Check { pool: usize, trig: [u8; 64], t: u64, cp: Option<(u128, u128)>, active: Option<i32>, venue: Venue, signer: Pk }

/// Why `Engine::run` returned
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RunEnd { Stopped, Deadline, Disconnected }

/// The engine's outside world: RPC (bound to the background runtime), the background runtime it spawns fetches on,
/// the event channel their answers come back on, and the state stream's watch list. `Engine::new_offline` has none
struct Io { rpc: crate::rpc::Rpc, rt: tokio::runtime::Handle, tx_back: Sender<Event>, watch_list: tokio::sync::watch::Sender<Vec<String>> }

/// what status.jsonl v2's deltas are against (the previous line)
#[derive(Default)]
struct StatusPrev { t: u64, counts: HashMap<&'static str, u64>, updates: u64, stale: u64, dropped: HashMap<String, u64> }

pub struct Engine {
    pub reg: Arc<Registry>,
    pub store: Store,
    cfg: StrategyCfg,
    feeds: Vec<String>,
    /// tip of the cheapest enabled send path (lamports); shadow nets are computed with it
    min_tip: u64,
    interest: Arc<Interest>,
    ata: AtaCache,
    sigs: HashMap<u64, SigInfo>,
    sig_order: VecDeque<(u64, u64)>,
    preds: HashMap<usize, PredEntry>,
    /// lookup tables, possibly partial: entries learned from feeds that send resolved addresses, or the whole table
    /// from one RPC fetch
    alts: HashMap<Pk, Vec<Option<Pk>>>,
    alt_inflight: HashSet<Pk>,
    alt_missing: HashSet<Pk>,
    alt_wait: HashMap<Pk, Vec<(Arrival, u64)>>,
    acct_pool: HashMap<Pk, usize>,
    watch: HashMap<usize, Vec<u64>>,
    opps: HashMap<u64, Opp>,
    checks: HashMap<usize, Check>,
    next_id: u64,
    slot: u64,
    lat: Vec<Series>,
    counts: HashMap<&'static str, u64>,
    /// every stream the engine writes (triggers, opportunities, predictions, arrivals, txarr, moves, rivals, caps,
    /// alts-final, status, feedhealth): handed to the recorder, never written on this thread (WP-02)
    rec: Rec,
    /// status.jsonl lines written so far (`seq` of the next one; stop.json `final_status_seq` = this - 1)
    pub status_lines: u64,
    /// the run's SendGate, shown in every status line as `send_gate` (review M2: a segment that does not send says why)
    pub gate: Option<Arc<crate::control::SendGate>>,
    /// RPC, runtime, channel back, watch list (None: `new_offline`)
    io: Option<Io>,
    /// `new_offline`: the fetches the engine asked for (what, accounts), recorded instead of sent
    pub offline_fetches: Vec<(&'static str, Vec<Pk>)>,
    /// newest slot by status (processed, confirmed, finalized) and the newest slot of a stored account update
    slots: [u64; 3],
    store_slot_max: u64,
    /// the engine queue's high-water mark since the last status line
    queue_hwm: usize,
    t_start: u64,
    sp: StatusPrev,
    exec_prev: crate::exec::ExecPrev,
    /// feedhealth.jsonl: the feeds' counters (index = feed id), the state stream's, and each feed's lead over the first
    /// arrival (txarr: when a signature leaves its window)
    feed_counters: Vec<Arc<FeedCounters>>,
    state_counters: Option<Arc<FeedCounters>>,
    leads: Vec<Series>,
    fh: rec::health::FeedHealth,
    /// simulation and canaries (exec.rs); None in a plain shadow run
    pub exec: Option<crate::exec::Exec>,
    /// per trigger signer: (triggers that moved the pool, triggers that never did within 5 s). Signers whose triggers
    /// mostly fail on chain (bots spraying swaps that revert) are ignored: their "gaps" never exist.
    signer_stats: HashMap<Pk, (u32, u32)>,
    /// triggers waiting to show up in a pool update (by signature: several can be pending on one pool), with signer, seen at
    trig_pending: HashMap<[u8; 64], (Pk, u64)>,
    /// decided trades waiting for their trigger's confirmation ([strategy] confirm_trigger_ms): (opp, trigger, the
    /// trigger pool's accounts still to show it, deadline ns), oldest first
    confirm_wait: VecDeque<(u64, [u8; 64], Vec<Pk>, u64)>,
    /// (transaction, pool) pairs already checked as state triggers
    state_seen: HashSet<(u64, u32)>,
    /// state triggers waiting until every account update of their transaction has arrived (one transaction moving two
    /// of our pools comes as several updates; pricing after the first saw a half-updated pair: w5h seg 14, 34% of state
    /// opportunities came from such transactions)
    state_pending: Vec<StatePending>,
    /// (sig8(transaction), pool) -> the receive and dequeue times of the pool's first update stamped with it, kept
    /// outside `state_pending` because a flush between two parts of one transaction drops the half-done entry (review
    /// F4: `rx` was then the last part's time). Taken when the pool is complete; bounded by `state_first_order`
    state_first: HashMap<(u64, u32), (u64, u64)>,
    state_first_order: VecDeque<(u64, u32)>,
    /// state opportunities' budget tables (caps.jsonl), written once the flush has priced every pool of the
    /// transaction (review F6: not between two pools' decisions)
    caps_pending: Vec<(u64, Best, i64)>,
    /// per pool: (time, CU price) of every transaction that touched it lately (the bids we compete with)
    pool_prices: HashMap<usize, VecDeque<(u64, u64)>>,
    /// recording (rivals, moves): venue programs by name, sender tip accounts by sender, signers seen arbitraging,
    /// (transaction, pool) moves already written
    amm: HashMap<Pk, &'static str>,
    tip_names: HashMap<Pk, String>,
    arbers: HashSet<Pk>,
    moves_seen: HashSet<(u64, u32)>,
    /// where each forwarded transaction ran on its leader's PoH clock (entries feeds), kept 3 minutes: the concrete
    /// measure of how long after a trigger the taker's transaction, and ours, actually executed
    poh: HashMap<[u8; 64], crate::feeds::entries::Poh>,
    poh_order: VecDeque<(u64, [u8; 64])>,
}

/// {signer: [ok, failed]} saved by an earlier run (or seeded from chain); missing or unreadable: start empty
fn load_signer_stats(path: &str) -> HashMap<Pk, (u32, u32)> {
    let Ok(text) = std::fs::read_to_string(path) else { return HashMap::default() };
    let Ok(Value::Object(m)) = serde_json::from_str::<Value>(&text) else { return HashMap::default() };
    m.iter().filter_map(|(k, v)| {
        let key: Pk = bs58::decode(k).into_vec().ok()?.try_into().ok()?;
        Some((key, (v[0].as_u64()? as u32, v[1].as_u64()? as u32)))
    }).collect()
}

/// swap venues by program (wider than the four we trade, to recognise arbitrage elsewhere) and the Jupiter aggregator
fn amm_programs() -> HashMap<Pk, &'static str> {
    [("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "pumpswap"), ("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", "raycpmm"),
     ("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", "rayammv4"), ("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "dlmm"),
     ("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", "rayclmm"), ("whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", "whirlpool"),
     ("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", "dammv2"), ("Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB", "dammv1"),
     ("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P", "pumpfun"), ("LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj", "launchlab"),
     ("dbcij3LWUppWqq96dh6gJWwBifmcGfLSB5D4DuSMaqN", "dbc"), ("SoLFiHG9TfgtdUXUjWAxi3LtvYuFyDLVhBWxdMZxyCe", "solfi"),
     ("JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4", "jupiter")]
        .iter().filter_map(|(k, n)| Some((bs58::decode(k).into_vec().ok()?.try_into().ok()?, *n))).collect()
}

fn sig8(s: &[u8; 64]) -> u64 { u64::from_le_bytes(s[..8].try_into().unwrap()) }
fn unix_now() -> i64 { (now_ns() / 1_000_000_000) as i64 }
fn sigs58(s: &[u8; 64]) -> String { bs58::encode(s).into_string() }

impl Engine {
    /// The run's engine. `rec`: the recorder; `rpc` must be bound to the background runtime `rt_bg`, where the engine's
    /// fetches (lookup tables, DLMM bin arrays) are spawned; their answers come back on `tx_back`
    #[allow(clippy::too_many_arguments)]
    pub fn new(reg: Arc<Registry>, store: Store, cfg: StrategyCfg, feeds: Vec<String>, min_tip: u64, interest: Arc<Interest>,
        rec: Rec, rpc: crate::rpc::Rpc, rt_bg: tokio::runtime::Handle, tx_back: Sender<Event>,
        watch_list: tokio::sync::watch::Sender<Vec<String>>) -> anyhow::Result<Engine> {
        let mut e = Engine::build(reg, store, cfg, feeds, min_tip, interest, rec);
        e.io = Some(Io { rpc, rt: rt_bg, tx_back, watch_list });
        Ok(e)
    }

    /// An engine with no RPC, runtime or watch channel (PLAN WP-02 item 11): fetches are recorded in
    /// `offline_fetches` instead of sent, and it records nothing until `set_rec`. For benchmarks and replay (WP-09)
    pub fn new_offline(reg: Arc<Registry>, store: Store, cfg: StrategyCfg) -> Engine {
        Engine::build(reg, store, cfg, vec![], 0, Arc::new(Interest::default()), Rec::off())
    }

    /// record through `rec` from now on
    pub fn set_rec(&mut self, rec: Rec) { self.rec = rec; }

    /// a latency series by name (A.8; benchmarks and tests)
    pub fn series_mut(&mut self, name: &str) -> Option<&mut Series> { self.lat.iter_mut().find(|s| s.name == name) }

    /// feedhealth.jsonl: the feeds' counters (index = feed id) and the state stream's
    pub fn set_feed_counters(&mut self, feeds: Vec<Arc<FeedCounters>>, state: Option<Arc<FeedCounters>>) {
        self.leads = feeds.iter().map(|_| Series::new("lead")).collect();
        self.feed_counters = feeds;
        self.state_counters = state;
    }

    fn build(reg: Arc<Registry>, store: Store, cfg: StrategyCfg, feeds: Vec<String>, min_tip: u64, interest: Arc<Interest>, rec: Rec) -> Engine {
        let mut acct_pool = HashMap::default();
        for &i in reg.pairs.values().flatten() {
            let m = &reg.pools[i];
            acct_pool.insert(m.pool, i);
            if !matches!(m.venue, Venue::Dlmm | Venue::DammV2) { acct_pool.insert(m.vault0, i); acct_pool.insert(m.vault1, i); }
        }
        let signer_stats = load_signer_stats(&cfg.signer_stats_file);
        let t0 = now_ns();
        Engine { reg, store, cfg, feeds, min_tip, interest, ata: AtaCache::default(), sigs: HashMap::default(), sig_order: VecDeque::new(),
            preds: HashMap::default(), alts: HashMap::default(), alt_inflight: HashSet::default(), alt_missing: HashSet::default(), alt_wait: HashMap::default(), acct_pool,
            watch: HashMap::default(), opps: HashMap::default(), checks: HashMap::default(), next_id: 0, slot: 0,
            lat: LAT_SERIES.into_iter().map(Series::new).collect(),
            counts: HashMap::default(), rec, status_lines: 0, gate: None, io: None, offline_fetches: Vec::new(), slots: [0; 3], store_slot_max: 0, queue_hwm: 0,
            t_start: t0, sp: StatusPrev { t: t0, ..Default::default() }, exec_prev: Default::default(), feed_counters: Vec::new(), state_counters: None, leads: Vec::new(),
            fh: rec::health::FeedHealth::new(t0),
            exec: None, signer_stats, trig_pending: HashMap::default(), confirm_wait: VecDeque::new(), state_seen: HashSet::default(), state_pending: Vec::new(),
            state_first: HashMap::default(), state_first_order: VecDeque::new(), caps_pending: Vec::new(), pool_prices: HashMap::default(), amm: amm_programs(), tip_names: crate::send::tip_owner_names(), arbers: HashSet::default(), moves_seen: HashSet::default(), poh: HashMap::default(), poh_order: VecDeque::new() }
    }

    fn count(&mut self, k: &'static str) { *self.counts.entry(k).or_default() += 1; }

    /// a pool account showed transaction `txn`: release the trades waiting for it once every part of their trigger pool does
    fn on_confirm(&mut self, key: Pk, txn: &[u8; 64]) {
        let mut ready = Vec::new();
        for e in self.confirm_wait.iter_mut() {
            if e.1 != *txn { continue; }
            e.2.retain(|k| *k != key);
            if e.2.is_empty() { ready.push(e.0); }
        }
        if ready.is_empty() { return; }
        self.confirm_wait.retain(|e| !e.2.is_empty());
        for id in ready { self.count("confirm_released"); self.after_opportunity(id); }
    }

    /// [strategy] state_triggers: transaction `txn` moved pool `i` (every part of it now shows `txn`): if that opened a
    /// gap on the pair, act on it, priced on the live state. Triggers already decoded from shreds are left to that path.
    /// `t_recv` / `t_engine`: when the pool's first update stamped `txn` reached us and left the engine queue.
    fn state_trigger(&mut self, i: usize, txn: [u8; 64], slot: u64, t_recv: u64, t_engine: u64) {
        let m = &self.reg.pools[i];
        let parts: &[Pk] = match m.venue { Venue::Dlmm | Venue::DammV2 => std::slice::from_ref(&m.pool), Venue::RayCpmm => &[m.vault0, m.vault1, m.pool][..], _ => &[m.vault0, m.vault1][..] };
        if !parts.iter().all(|k| self.store.get(k).is_some_and(|a| a.txn == Some(txn))) { return; }
        // the first part's times, even when a flush dropped this pool's entry between its parts (review F4)
        let (t_recv, t_engine) = self.state_first.remove(&(sig8(&txn), i as u32)).unwrap_or((t_recv, t_engine));
        if !self.state_seen.insert((sig8(&txn), i as u32)) { return; }
        if self.state_seen.len() > 200_000 { self.state_seen.clear(); }
        if self.opps.values().any(|o| o.trig == txn) { return; }   // the shred path already acted on this trigger
        if self.exec.as_ref().is_some_and(|x| x.is_ours(&txn)) { return; }
        if self.preds.contains_key(&i) { return; }   // another pending trigger's prediction is on this pool
        let now = unix_now();
        let t_eval = now_ns();
        let best = self.best_cycle(i, now);
        let t_decided = now_ns();
        // every evaluation is a sample (whatever it decided): the state path's latency baseline (WP-00, F13)
        for (k, d) in [(0, t_engine.saturating_sub(t_recv)), (1, t_decided.saturating_sub(t_engine)), (2, t_decided.saturating_sub(t_recv))] {
            self.lat[LAT_STATE_RECV_TO_ENGINE + k].push(d);
        }
        let Some(b) = best else { return };
        if b.net < self.cfg.min_profit_lamports as i64 { return; }
        self.count("state_opportunity");
        let id = self.next_id; self.next_id += 1;
        let (bi, si) = (self.reg.by_pool[&b.buy], self.reg.by_pool[&b.sell]);
        self.watch.entry(bi).or_default().push(id);
        self.watch.entry(si).or_default().push(id);
        let st = Stages { rx: t_recv, decoded: t_recv, engine: t_engine, resolved: t_eval, decided: t_decided };
        self.opps.insert(id, Opp { id, trig: txn, trig_feed: u16::MAX, slot, st, trig_pool: self.reg.pools[i].pool, buy: b.buy, sell: b.sell,
            mint: b.mint, size: b.size, gross: b.gross, net: b.net, cu: b.cu, crossed: b.crossed,
            deadline: now_ns() + self.cfg.outcome_watch_ms * 1_000_000, trig_cu_price: None, landed: Some(slot), touches: Vec::new() });
        self.after_opportunity(id);
        // the budget table (caps.jsonl) after the send, and after the other pools of this transaction are priced
        // (flush_state writes it): same state, same line
        self.caps_pending.push((id, b, now));
    }

    /// trades whose trigger never showed in time: it failed on chain (a phantom gap) or its update was too slow
    fn expire_confirms(&mut self) {
        let now = now_ns();
        // the opportunity ends with its wait: if the trigger lands later, the state path prices it afresh (w5h seg 14:
        // 42 late-landing triggers were never acted on because the stale opportunity blocked the state path)
        while self.confirm_wait.front().is_some_and(|e| e.3 <= now) {
            if let Some(e) = self.confirm_wait.pop_front() { self.finish_opp(e.0); }
            self.count("confirm_timeout");
        }
    }

    /// price the state triggers whose transaction is now fully applied (`run` calls it when its queue is empty)
    pub fn flush_state(&mut self) {
        for p in std::mem::take(&mut self.state_pending) { self.state_trigger(p.pool, p.txn, p.slot, p.t_recv, p.t_engine); }
        for (id, b, now) in std::mem::take(&mut self.caps_pending) { self.record_caps(id, &b, "state", now); }
    }

    /// A signature left its 10 s window: txarr.log (when each feed delivered it: µs after the first; `-` never; the
    /// line is formatted on the recorder's writer), and feedhealth's first-arrival count and per-feed lead
    fn write_txarr(&mut self, k: u64, s: &SigInfo) {
        if let Some(c) = self.feed_counters.get(s.first_feed as usize) { c.first_arrivals.fetch_add(1, std::sync::atomic::Ordering::Relaxed); }
        for (f, t) in s.arrivals() { if let Some(l) = self.leads.get_mut(f as usize) { l.push(t.saturating_sub(s.first_t)); } }
        if !self.rec.is_on() { return; }
        let (n, slot, first, arr) = (self.feeds.len().min(MAX_FEEDS), s.slot, s.first_t, s.arr);
        self.rec.emit(rec::TXARR, Record::enc(move |o| {
            let _ = write!(o, "{:016x} {slot} {first}", k.swap_bytes());
            for &t in &arr[..n] { if t == 0 { o.extend_from_slice(b" -"); } else { let _ = write!(o, " {}", t.saturating_sub(first) / 1000); } }
        }));
    }

    /// alts-final.jsonl (MEASUREMENT §4.26; v1 `alts.jsonl`): every lookup table entry the engine learned, at stop, to
    /// decode the entries archive offline. Each table is serialized on the recorder's writer
    fn write_alts(&self) {
        if !self.rec.is_on() { return; }
        for (t, v) in &self.alts {
            let (t, v) = (*t, v.clone());
            self.rec.emit(rec::ALTS_FINAL, Record::enc(move |o| {
                let addrs: Vec<Value> = v.iter().map(|a| a.map_or(Value::Null, |k| json!(b58(&k)))).collect();
                let _ = serde_json::to_writer(o, &json!({ "table": b58(&t), "addrs": addrs }));
            }));
        }
    }

    /// rivals.jsonl: an arbitrage-like transaction's fingerprint, at shred time
    fn record_rival(&mut self, a: &Arrival, keys: &[Pk]) {
        if !self.rec.is_on() { return; }
        let tx = &a.tx;
        let Some(signer) = tx.fee_payer().copied() else { return };
        let mut venues: Vec<&'static str> = Vec::new();
        for k in keys { if let Some(n) = self.amm.get(k) { if !venues.contains(n) { venues.push(n); } } }
        let agg = venues.contains(&"jupiter");
        let n_venues = venues.len() - agg as usize;
        let pools: Vec<String> = keys.iter().filter(|k| self.reg.by_pool.contains_key(*k)).map(b58).collect();
        let why = if n_venues >= 2 { "venues" } else if pools.len() >= 2 { "pools" } else if self.arbers.contains(&signer) { "known" } else { return };
        if why != "known" && !agg && self.arbers.len() < 200_000 { self.arbers.insert(signer); }
        let sys = [0u8; 32];
        let (mut tips, mut nonce, mut progs, mut head) = (Vec::new(), Value::Null, Vec::<String>::new(), Value::Null);
        for (n, ix) in tx.ixs.iter().enumerate() {
            let Some(p) = keys.get(ix.program as usize) else { continue };
            if *p == sys {
                let d = &ix.data;
                if d.len() >= 12 && d[..4] == [2, 0, 0, 0] {
                    if let Some(dest) = ix.accounts.get(1).and_then(|&i| keys.get(i as usize)) {
                        tips.push(json!([b58(dest), u64::from_le_bytes(d[4..12].try_into().unwrap()), self.tip_names.get(dest)]));
                    }
                } else if n == 0 && d.len() >= 4 && d[..4] == [4, 0, 0, 0] {
                    nonce = ix.accounts.first().and_then(|&i| keys.get(i as usize)).map_or(Value::Null, |k| json!(b58(k)));
                }
                continue;
            }
            if *p == crate::tx::COMPUTE_BUDGET { continue; }
            let s = b58(p);
            if !progs.contains(&s) { progs.push(s); }
            if head.is_null() {
                let h: String = ix.data.iter().take(48).map(|b| format!("{b:02x}")).collect();
                head = json!([h, ix.data.len(), ix.accounts.len()]);
            }
        }
        let ver = if tx.v1 { "1" } else if tx.lookups.is_empty() { "legacy" } else { "0" };
        let line = json!({ "sig": tx.sig_b58(), "slot": a.slot, "t": a.t_rx, "feed": self.feeds.get(a.feed as usize), "why": why,
            "signer": b58(&signer), "n_sig": tx.num_signers, "v": ver, "cu_limit": tx.cu_limit, "cu_price": tx.cu_price(),
            "v1_fee": if tx.v1 { tx.cu_price_micro } else { None }, "tips": tips, "nonce": nonce, "progs": progs, "venues": venues, "agg": agg,
            "pools": pools, "alts": tx.lookups.iter().map(|l| b58(&l.table)).collect::<Vec<_>>(), "n_ix": tx.ixs.len(), "n_keys": keys.len(), "head": head });
        self.rec.json(rec::RIVALS, line);
    }

    /// signer-stats.json (a cross-run file, §4.48): a copy of the map is serialized and written by the recorder's slow
    /// writer (atomically), not on the engine thread
    fn save_signer_stats(&self) {
        if self.cfg.signer_stats_file.is_empty() { return; }
        let (stats, path) = (self.signer_stats.clone(), self.cfg.signer_stats_file.clone());
        self.rec.task(move || {
            let m: serde_json::Map<String, Value> = stats.iter().map(|(k, v)| (b58(k), json!([v.0, v.1]))).collect();
            let tmp = format!("{path}.tmp");
            if std::fs::write(&tmp, Value::Object(m).to_string()).is_ok() { let _ = std::fs::rename(&tmp, &path); }
        });
    }

    /// Run until `stop`, the deadline `until_ns` or the channel closes; says which. `status` is called every 10 s with a
    /// one-line summary. The final status.jsonl line is the caller's (`write_final_status`), once it knows the stop reason.
    pub fn run(&mut self, rx: &Receiver<Event>, stop: &std::sync::atomic::AtomicBool, until_ns: u64, mut status: impl FnMut(&str)) -> RunEnd {
        self.rec.set_engine_tid(crate::runtime::gettid());
        let mut last_status = now_ns();
        let mut last_drift = now_ns();
        let end = loop {
            if stop.load(std::sync::atomic::Ordering::Relaxed) { break RunEnd::Stopped; }
            if now_ns() >= until_ns { break RunEnd::Deadline; }
            let ev = match rx.try_recv() {
                Ok(e) => e,
                Err(TryRecvError::Disconnected) => break RunEnd::Disconnected,
                Err(TryRecvError::Empty) => {
                    // spin briefly (an event usually follows another within microseconds), then block
                    let until_spin = now_ns() + SPIN_NS;
                    let mut got = None;
                    while now_ns() < until_spin { if let Ok(e) = rx.try_recv() { got = Some(e); break; } std::hint::spin_loop(); }
                    match got {
                        Some(e) => e,
                        None => match rx.recv_timeout(std::time::Duration::from_millis(5)) {
                            Ok(e) => e,
                            Err(RecvTimeoutError::Timeout) => { self.expire_confirms(); self.housekeeping(&mut last_status, &mut last_drift, rx.len(), &mut status); continue; }
                            Err(RecvTimeoutError::Disconnected) => break RunEnd::Disconnected,
                        },
                    }
                }
            };
            let t_engine = now_ns();
            let q = rx.len();
            if q > self.queue_hwm { self.queue_hwm = q; }
            self.on_event(ev, t_engine, &mut status);
            if !self.state_pending.is_empty() && rx.is_empty() { self.flush_state(); }
            if now_ns() - last_status > 10_000_000_000 { self.housekeeping(&mut last_status, &mut last_drift, rx.len(), &mut status); }
        };
        self.finish();
        end
    }

    /// One input event, dequeued at `t_engine`: the body of `run`'s loop (`new_offline` users call it, then
    /// `flush_state` when their queue is empty, as `run` does)
    pub fn on_event(&mut self, ev: Event, t_engine: u64, status: &mut dyn FnMut(&str)) {
        match ev {
            Event::Tx(a) => self.on_tx(a, t_engine),
            Event::Account { slot, pubkey, data, t, txn, .. } => self.on_account(pubkey, data, slot, t, txn, t_engine),
            Event::Slot { slot, status: st, .. } => {
                if slot > self.slot { self.slot = slot; crate::send::tpu::SLOT.store(slot, std::sync::atomic::Ordering::Relaxed); }
                // Yellowstone SlotStatus: 0 processed, 1 confirmed, 2 finalized (status.jsonl v2 `slot`)
                if let Some(x) = usize::try_from(st).ok().and_then(|i| self.slots.get_mut(i)) { if slot > *x { *x = slot; } }
            }
            Event::Status { msg, .. } => status(&msg),
            Event::Alt { table, addrs } => self.on_alt(table, addrs),
            Event::Settled(st) => { let poh = &self.poh; if let Some(x) = self.exec.as_mut() { x.on_settled(*st, &|s| poh.get(s).copied()); } }
        }
        if !self.confirm_wait.is_empty() { self.expire_confirms(); }
    }

    /// the end of the run: open opportunities finished, the signatures still in their window written, the lookup
    /// tables dumped (alts-final), the signer statistics saved
    pub fn finish(&mut self) {
        let ids: Vec<u64> = self.opps.keys().copied().collect();
        for id in ids { self.finish_opp(id); }
        let left: Vec<u64> = self.sigs.keys().copied().collect();
        for k in left { if let Some(s) = self.sigs.remove(&k) { self.write_txarr(k, &s); if s.trigger.is_some() { self.write_arrivals(&s); } } }
        self.write_alts();
        self.save_signer_stats();
    }

    /// The last status.jsonl line, with the run's stop reason (MEASUREMENT A.5; WP-01)
    pub fn write_final_status(&mut self, queue: usize, stop_reason: &str) {
        self.write_status_line(queue, Some(stop_reason));
    }

    fn housekeeping(&mut self, last_status: &mut u64, last_drift: &mut u64, queue: usize, status: &mut impl FnMut(&str)) {
        let now = now_ns();
        // finish opportunities whose watch window ended
        let due: Vec<u64> = self.opps.values().filter(|o| o.deadline <= now).map(|o| o.id).collect();
        for id in due { self.finish_opp(id); }
        // forget old signatures, predictions and checks
        while let Some(&(t, k)) = self.sig_order.front() {
            if now - t < SIG_KEEP_NS { break; }
            self.sig_order.pop_front();
            if let Some(s) = self.sigs.remove(&k) { self.write_txarr(k, &s); if s.trigger.is_some() { self.write_arrivals(&s); } }
        }
        self.preds.retain(|_, p| now - p.t < PRED_KEEP_NS);
        while let Some(&(t, s)) = self.poh_order.front() { if now - t < 180_000_000_000 { break; } self.poh_order.pop_front(); self.poh.remove(&s); }
        // a trigger whose pool never showed it within 5 s failed on chain (or never landed): count it against its signer
        let expired: Vec<[u8; 64]> = self.trig_pending.iter().filter(|(_, v)| now - v.1 >= 5_000_000_000).map(|(k, _)| *k).collect();
        for k in expired { if let Some((sg, _)) = self.trig_pending.remove(&k) { self.signer_stats.entry(sg).or_default().1 += 1; } }
        self.checks.retain(|_, c| now - c.t < 5_000_000_000);
        if now - *last_drift > 2_000_000_000 { *last_drift = now; self.follow_dlmm(); }
        if now - *last_status > 10_000_000_000 {
            *last_status = now;
            self.save_signer_stats();
            let line = self.write_status(queue);
            status(&line);
            self.write_feedhealth(now);
        }
    }

    fn write_status(&mut self, queue: usize) -> String { self.write_status_line(queue, None) }

    /// feedhealth.jsonl (MEASUREMENT §4.9): one line per feed and one for the state stream, every 10 s
    fn write_feedhealth(&mut self, t: u64) {
        if !self.rec.is_on() || (self.feed_counters.is_empty() && self.state_counters.is_none()) { return; }
        let tip = self.slots[0].max(self.slot);
        let mut rows = Vec::new();
        if let Some(c) = &self.state_counters { rows.push(rec::health::FeedRow { id: None, c: c.as_ref(), lead: None }); }
        for ((i, c), lead) in self.feed_counters.iter().enumerate().zip(self.leads.iter_mut()) {
            rows.push(rec::health::FeedRow { id: Some(i as u16), c: c.as_ref(), lead: Some(lead) });
        }
        for l in self.fh.lines(t, tip, rows) { self.rec.json(rec::FEEDHEALTH, l); }
    }

    /// status.jsonl v2 (MEASUREMENT §4.8, §2.2): every number is `_total` (since the start), `_delta` (since the last
    /// line) or `_now`; percentiles name their window (`latency`: the interval; `latency_run`: the whole run, WP-00's
    /// series). Sections later WPs bring (commit, forks, lag_slo, accuracy, chainfetch, coverage) are absent; health
    /// fields they fill are null
    fn write_status_line(&mut self, queue: usize, stop_reason: Option<&str>) -> String {
        let t = now_ns();
        let (mut lat, mut lat_run) = (serde_json::Map::new(), serde_json::Map::new());
        // the engine's stage series, then the send's (exec: decided_to_signed, signed_to_fired, signed_to_sent). Each is
        // a bounded reservoir (lat.rs; review F7: no 200k-sample sorts on the engine thread)
        let exec_lat = self.exec.as_mut().map(|x| &mut x.lat);
        for v in self.lat.iter_mut().chain(exec_lat.into_iter().flat_map(|l| l.iter_mut())) {
            lat.insert(v.name.to_string(), v.take_interval(1e3));
            lat_run.insert(v.name.to_string(), v.run_pct(1e3));
        }
        let waiting: usize = self.alt_wait.values().map(|v| v.len()).sum();
        let p = &mut self.sp;
        let counts_delta: serde_json::Map<String, Value> = self.counts.iter().filter_map(|(k, v)| {
            let d = v - p.counts.get(k).copied().unwrap_or(0);
            (d > 0).then(|| (k.to_string(), json!(d)))
        }).collect();
        let (exec, money) = match self.exec.as_ref() { Some(x) => x.status_v2(&mut self.exec_prev), None => (Value::Null, Value::Null) };
        let st = self.rec.stats();
        let recorder = st.as_ref().map(|st| {
            let dropped_total: serde_json::Map<String, Value> = st.dropped.iter().filter(|(_, n)| *n > 0).map(|(k, n)| (k.clone(), json!(n))).collect();
            let dropped_delta: serde_json::Map<String, Value> = st.dropped.iter().filter_map(|(k, n)| {
                let d = n - p.dropped.get(k).copied().unwrap_or(0);
                (d > 0).then(|| (k.clone(), json!(d)))
            }).collect();
            let nonzero = |v: &[(String, u64)]| -> serde_json::Map<String, Value> { v.iter().filter(|(_, n)| *n > 0).map(|(k, n)| (k.clone(), json!(n))).collect() };
            // review F1, F2: records lost to I/O errors and encoders, and writers that died, beside the drops
            json!({ "dropped_total": dropped_total, "dropped_delta": dropped_delta, "suppressed_total": nonzero(&st.suppressed),
                "io_errors_total": nonzero(&st.io_errors), "io_lost_total": nonzero(&st.io_lost), "encode_errors_total": nonzero(&st.encode_errors),
                "writers_dead_now": st.writers_dead, "echo_dropped_total": st.echo_dropped,
                "queue_hwm": st.queue_hwm.iter().map(|(q, n)| (q.to_string(), json!(n))).collect::<serde_json::Map<_, _>>() })
        });
        let nz = |x: u64| (x > 0).then_some(x);
        let mut line = json!({ "seq": self.status_lines, "t_ns": t, "interval_ns": t.saturating_sub(p.t), "run_s": t.saturating_sub(self.t_start) as f64 / 1e9,
            "slot": { "processed": nz(self.slots[0].max(self.slot)), "confirmed": nz(self.slots[1]), "finalized": nz(self.slots[2]) },
            "tip_lag_slots_now": (self.slot > 0 && self.store_slot_max > 0).then(|| self.slot as i64 - self.store_slot_max as i64),
            "send_gate": self.gate.as_ref().map(|g| g.json()),
            "health": { "recorder_ok": st.as_ref().map(|s| s.core_ok), "warmup_ready": null, "lag_slo_ok": null, "leaders_ok": null,
                "blockhash_age_slots_now": null, "blockhash_src_now": null, "jito_token_age_s_now": null },
            "queue": { "engine_now": queue, "engine_hwm_delta": self.queue_hwm.max(queue) },
            "store": { "accounts_now": self.store.accts.len(), "updates_total": self.store.updates, "updates_delta": self.store.updates - p.updates,
                "stale_total": self.store.stale_dropped, "stale_delta": self.store.stale_dropped - p.stale, "pending_groups_now": self.state_pending.len() },
            "alts": { "cached_now": self.alts.len(), "waiting_txs_now": waiting, "fetching_now": self.alt_inflight.len(), "missing_now": self.alt_missing.len(),
                "learned_delta": self.counts.get("alt_learned").copied().unwrap_or(0) - p.counts.get("alt_learned").copied().unwrap_or(0) },
            "opps_open_now": self.opps.len(), "ata_misses_total": self.ata.misses.get(),
            "counts_total": self.counts, "counts_delta": counts_delta,
            "latency": lat, "latency_run": lat_run,
            "exec": exec, "money": money, "recorder": recorder });
        if let Some(r) = stop_reason { line["stop_reason"] = json!(r); }
        p.t = t;
        p.counts = self.counts.clone();
        p.updates = self.store.updates;
        p.stale = self.store.stale_dropped;
        if let Some(st) = &st { p.dropped = st.dropped.iter().cloned().collect(); }
        self.queue_hwm = queue;
        self.rec.json(rec::STATUS, line);
        self.status_lines += 1;
        let c = |k: &str| self.counts.get(k).copied().unwrap_or(0);
        format!("slot {} queue {} | txs {} triggers {} opps {} | alt: waits {} learned {} still waiting {} | preds checked {}", self.slot, queue,
            c("tx_first"), c("trigger"), c("opportunity"), c("alt_wait"), c("alt_learned"), waiting, c("pred_checked"))
    }

    // ---------------------------------------------------------------- transactions

    fn on_tx(&mut self, a: Arrival, t_engine: u64) {
        if a.tx.loaded.is_some() && !a.tx.lookups.is_empty() { self.learn_alts(&a.tx); }
        let k = sig8(&a.tx.sig);
        let f = (a.feed as usize).min(MAX_FEEDS - 1);
        if let Some(x) = self.exec.as_mut() { x.on_arrival(&a.tx.sig, a.feed, a.t_rx); }
        if let Some(p) = a.poh { if !self.poh.contains_key(&a.tx.sig) { self.poh.insert(a.tx.sig, p); self.poh_order.push_back((now_ns(), a.tx.sig)); } }
        if let Some(s) = self.sigs.get_mut(&k) {
            if s.arr[f] == 0 { s.arr[f] = a.t_rx.max(1); }
            if a.t_rx < s.first_t { s.first_t = a.t_rx; s.first_feed = a.feed; }
            return;
        }
        let mut arr = [0u64; MAX_FEEDS];
        arr[f] = a.t_rx.max(1);
        self.sigs.insert(k, SigInfo { first_t: a.t_rx, first_feed: a.feed, arr, trigger: None, slot: a.slot });
        self.sig_order.push_back((now_ns(), k));
        self.count("tx_first");
        self.process(a, t_engine);
    }

    /// resolve lookup tables, then look for triggers
    fn process(&mut self, a: Arrival, t_engine: u64) {
        let keys = if !a.tx.lookups.is_empty() && a.tx.loaded.is_none() {
            match self.resolve_lookups(&a.tx) {
                Ok(k) => k,
                Err(missing) => {
                    if missing.iter().any(|t| self.alt_missing.contains(t)) { self.count("alt_unknown"); return; }
                    self.count("alt_wait");
                    for t in &missing { if self.alt_inflight.insert(*t) { self.fetch_alt(*t); } }
                    self.alt_wait.entry(missing[0]).or_default().push((a, t_engine));
                    return;
                }
            }
        } else {
            match a.tx.resolve(|_| None) { Some(k) => k, None => { self.count("resolve_failed"); return } }
        };
        let t_resolved = now_ns();
        self.record_rival(&a, &keys);
        // the bids on our pools: every transaction touching one (users and bots alike contend for its write lock)
        if !self.exec.as_ref().is_some_and(|x| x.is_ours(&a.tx.sig)) {
            let price = a.tx.cu_price().unwrap_or(0);
            let now = now_ns();
            for k in &keys {
                if let Some(&i) = self.reg.by_pool.get(k) {
                    let q = self.pool_prices.entry(i).or_default();
                    q.push_back((now, price));
                    while q.len() > 64 || q.front().is_some_and(|x| now - x.0 > 30_000_000_000) { q.pop_front(); }
                }
            }
        }
        let swaps = self.decode_swaps(&a.tx, &keys);
        if swaps.is_empty() { return; }
        // a trigger's tables are worth forwarding from every feed from now on
        if !a.tx.lookups.is_empty() {
            let mut tables = self.interest.tables.write().unwrap();
            for l in &a.tx.lookups { tables.insert(l.table); }
        }
        for sw in swaps { self.on_trigger(&a, &sw, t_engine, t_resolved); }
    }

    /// Full account list from (possibly partial) cached tables; Err lists the tables missing an entry we need.
    fn resolve_lookups(&self, tx: &Tx) -> Result<Vec<Pk>, Vec<Pk>> {
        let mut out = tx.keys.clone();
        let mut missing = Vec::new();
        for pass in 0..2 {
            for l in &tx.lookups {
                let idx = if pass == 0 { &l.writable } else { &l.readonly };
                let t = self.alts.get(&l.table);
                for &i in idx {
                    match t.and_then(|t| t.get(i as usize).copied().flatten()) {
                        Some(k) => out.push(k),
                        None => { if !missing.contains(&l.table) { missing.push(l.table); } break; }
                    }
                }
            }
        }
        if missing.is_empty() { Ok(out) } else { Err(missing) }
    }

    /// Learn lookup-table entries from a copy that carries its resolved addresses (writable for every table in
    /// order, then readonly), and release transactions that were waiting for them.
    fn learn_alts(&mut self, tx: &Tx) {
        let Some((w, r)) = &tx.loaded else { return };
        let (nw, nr): (usize, usize) = (tx.lookups.iter().map(|l| l.writable.len()).sum(), tx.lookups.iter().map(|l| l.readonly.len()).sum());
        if nw != w.len() || nr != r.len() { return; }
        let (mut wi, mut ri) = (0, 0);
        let mut learned = Vec::new();
        for l in &tx.lookups {
            let t = self.alts.entry(l.table).or_insert_with(|| vec![None; 256]);
            let mut new = false;
            for &i in &l.writable { if t[i as usize].is_none() { t[i as usize] = Some(w[wi]); new = true; } wi += 1; }
            for &i in &l.readonly { if t[i as usize].is_none() { t[i as usize] = Some(r[ri]); new = true; } ri += 1; }
            if new { learned.push(l.table); }
        }
        for t in learned {
            if let Some(waiting) = self.alt_wait.remove(&t) {
                self.count("alt_learned");
                for (a, te) in waiting { self.process(a, te); }
            }
        }
    }

    /// a lookup table, fetched on the background runtime (its answer comes back as `Event::Alt`)
    fn fetch_alt(&mut self, table: Pk) {
        let Some(io) = &self.io else { self.offline_fetches.push(("alt", vec![table])); return };
        let (rpc, back) = (io.rpc.clone(), io.tx_back.clone());
        io.rt.spawn(async move {
            let addrs = match rpc.accounts(&[table]).await {
                Ok((_, v)) => v.into_iter().next().flatten().and_then(|a| crate::tx::parse_alt(&a.data)).map(Arc::new),
                Err(_) => None,
            };
            let _ = back.send(Event::Alt { table, addrs });
        });
    }

    fn on_alt(&mut self, table: Pk, addrs: Option<Arc<Vec<Pk>>>) {
        self.alt_inflight.remove(&table);
        match addrs {
            Some(a) => { let mut v: Vec<Option<Pk>> = a.iter().map(|k| Some(*k)).collect(); v.resize(256, None); self.alts.insert(table, v); }
            None => { self.alt_missing.insert(table); }
        }
        if let Some(waiting) = self.alt_wait.remove(&table) {
            for (a, t_engine) in waiting { self.process(a, t_engine); }
        }
    }

    /// Top-level venue swaps on watched pools. Swaps that hide behind another program (aggregators, bots) are not
    /// visible before execution and are not decoded here.
    fn decode_swaps(&self, tx: &Tx, keys: &[Pk]) -> Vec<PendingSwap> {
        let mut out = Vec::new();
        let reg = &self.reg;
        let meta = |p: &Pk| -> Option<&PoolMeta> { reg.by_pool.get(p).map(|&i| &reg.pools[i]) };
        let ata = |o: &Pk, m: &Pk, p: &Pk| self.ata.get(o, m, p);
        for ix in &tx.ixs {
            let Some(prog) = keys.get(ix.program as usize) else { continue };
            let Some(venue) = Venue::of_program(prog) else { continue };
            let acc: Option<Vec<Pk>> = ix.accounts.iter().map(|&i| keys.get(i as usize).copied()).collect();
            let Some(acc) = acc else { continue };
            let sw = match venue { Venue::Dlmm => dlmm::decode_pending(&ix.data, &acc, &meta, &ata), Venue::DammV2 => damm_pending(&ix.data, &acc, &meta, &ata),
                _ => cp::decode_pending(venue, &ix.data, &acc, &meta, &ata) };
            if let Some(sw) = sw { if self.reg.by_pool.contains_key(&sw.pool) && self.acct_pool.contains_key(&sw.pool) { out.push(sw); } }
        }
        out
    }

    // ---------------------------------------------------------------- quoting

    /// Pool `i` ready to quote: its predicted state if a pending swap changed it, else the live state. Built once
    /// per search; every size probe then quotes against it without touching the store.
    fn leg(&self, i: usize, now: i64) -> Option<Leg<'_>> {
        let m = &self.reg.pools[i];
        let pred = self.preds.get(&i);
        match m.venue {
            Venue::Dlmm => {
                let Ok(Snap::Dlmm { pair, arrays, .. }) = self.store.snapshot(m, now) else { return None };
                let over = match pred { Some(PredEntry { pred: Pred::Dlmm(o), .. }) => Some(o), _ => None };
                Some(Leg::Dlmm { pair, arrays, over })
            }
            Venue::DammV2 => match pred {
                Some(PredEntry { pred: Pred::Damm(p), .. }) => Some(Leg::Damm(p.clone(), self.slot)),
                _ => match self.store.snapshot(m, now) { Ok(Snap::Damm(p, _)) => Some(Leg::Damm(p, self.slot)), _ => None },
            },
            _ => match pred {
                Some(PredEntry { pred: Pred::Cp(s), .. }) => Some(Leg::Cp(s.clone())),
                _ => match self.store.snapshot(m, now) { Ok(Snap::Cp(s)) => Some(Leg::Cp(s)), _ => None },
            },
        }
    }

    /// Exact-in quote that also returns the pool's state after the swap (the trigger's prediction).
    fn quote(&self, i: usize, zfo: bool, amount: u64, now: i64) -> Option<(u64, u32, Pred)> {
        match self.leg(i, now)? {
            Leg::Cp(s) => { let q = cp::quote(&s, zfo, amount)?; Some((q.out, 0, Pred::Cp(cp::CpSnap { r0: q.r0, r1: q.r1, ..s }))) }
            Leg::Dlmm { pair, arrays, over } => {
                let v = dlmm::View { pair, arrays: &arrays, over };
                let q = dlmm::quote(&v, zfo, amount, now, true).ok()?;
                let mut o = over.cloned().unwrap_or_default();
                dlmm::apply(&mut o, &q);
                Some((q.out, q.crossed, Pred::Dlmm(o)))
            }
            Leg::Damm(p, slot) => { let (out, after) = crate::venues::dammv2::quote_exact_in(&p, zfo, amount, slot, now)?; Some((out, 0, Pred::Damm(after))) }
        }
    }

    /// every feed's arrival time for one trigger, written once all feeds had 10 s to deliver it
    fn write_arrivals(&mut self, s: &SigInfo) {
        let Some((pool, venue, slot)) = s.trigger else { return };
        let arr: serde_json::Map<String, serde_json::Value> = s.arrivals()
            .map(|(f, t)| (self.feeds.get(f as usize).cloned().unwrap_or_default(), json!(t))).collect();
        self.rec.json(rec::ARRIVALS, json!({ "slot": slot, "pool": b58(&pool), "venue": venue, "source": self.reg.source(&pool),
            "first_feed": self.feeds.get(s.first_feed as usize), "arrivals": arr }));
    }

    /// a decoded trigger's stage times and its triggers.jsonl line; `opp` is the best round trip's net, None for a hint
    /// (`hint_only`, WP-00) or when no round trip was found. A priced trigger feeds the v1 series; a hint (whose
    /// `decided` is the end of its bookkeeping, not a pricing decision) feeds `hint_rx_to_done` only (review F9)
    #[allow(clippy::too_many_arguments)]
    fn write_trigger(&mut self, a: &Arrival, sw: &PendingSwap, i: usize, t_engine: u64, t_resolved: u64, opp: Option<i64>, hint_only: bool) -> Stages {
        let t_decided = now_ns();
        let st = Stages { rx: a.t_rx, decoded: a.t_decoded, engine: t_engine, resolved: t_resolved, decided: t_decided };
        if hint_only { self.lat[LAT_HINT_RX_TO_DONE].push(t_decided.saturating_sub(a.t_rx)); } else {
            for (k, d) in [(0, a.t_decoded.saturating_sub(a.t_rx)), (1, t_engine.saturating_sub(a.t_decoded)), (2, t_resolved.saturating_sub(t_engine)), (3, t_decided.saturating_sub(t_resolved)), (4, t_decided.saturating_sub(a.t_rx))] {
                self.lat[k].push(d);
            }
        }
        let m = &self.reg.pools[i];
        let mut line = json!({
            "sig": sigs58(&a.tx.sig), "feed": self.feeds.get(a.feed as usize), "slot": a.slot, "pool": b58(&m.pool), "venue": m.venue,
            "source": self.reg.source(&m.pool),
            "zfo": sw.zero_for_one, "amount": sw.amount, "exact_out": sw.exact_out, "executed": a.executed,
            "st": st, "opp": opp });
        if hint_only { line["hint_only"] = json!(true); }
        self.rec.json(rec::TRIGGERS, line);
        st
    }

    fn on_trigger(&mut self, a: &Arrival, sw: &PendingSwap, t_engine: u64, t_resolved: u64) {
        self.count("trigger");
        if let Some(s) = self.sigs.get_mut(&sig8(&a.tx.sig)) { if s.trigger.is_none() { s.trigger = Some((sw.pool, sw.venue, a.slot)); } }
        let Some(&i) = self.reg.by_pool.get(&sw.pool) else { return };
        let now = unix_now();
        // exact-out swaps: find the input that produces their output
        let amount_in = if sw.exact_out {
            match self.quote_input_for_output(i, sw.zero_for_one, sw.amount, now) { Some(x) => x, None => { self.count("trigger_exact_out_unsolved"); return } }
        } else { sw.amount };
        let signer = a.tx.fee_payer().copied().unwrap_or_default();
        // a signer whose triggers mostly never move the pool: skip (at least 4 resolved, under 25% landed). Its swap is
        // still followed (`trig_pending`), so its statistics keep learning and a signer that starts landing is let back
        // in (review F10: a skipped signer's statistics used to freeze). With decoded_sends off (Stage 0) the skip only
        // drops the hint's accuracy check: hints are never priced
        if let Some(&(ok, miss)) = self.signer_stats.get(&signer).filter(|_| self.cfg.skip_failing_signers) {
            if ok + miss >= 4 && (ok as f64) < 0.25 * (ok + miss) as f64 {
                self.count("trigger_skip_signer_fails");
                self.trig_pending.insert(a.tx.sig, (signer, now_ns()));
                return;
            }
        }
        let Some((out, _, after)) = self.quote(i, sw.zero_for_one, amount_in, now) else { self.count("trigger_unquotable"); return };
        // the trigger's own slippage bound: if our quote can't meet it, the swap reverts on chain, the pool doesn't move,
        // and there is no gap. Skip it, and keep the pool's prediction as it was (0.05% tolerance for rounding).
        if sw.limit > 0 {
            let fails = if sw.exact_out { amount_in > sw.limit + sw.limit / 2000 } else { out.saturating_add(out / 2000) < sw.limit };
            if fails { self.count("trigger_skip_will_fail"); return; }
        }
        // accuracy check: remember what we expect the pool to look like once the trigger lands
        let m = &self.reg.pools[i];
        let check = match &after {
            Pred::Cp(s) => Check { pool: i, trig: a.tx.sig, t: now_ns(), cp: Some((s.r0, s.r1)), active: None, venue: m.venue, signer },
            Pred::Dlmm(o) => Check { pool: i, trig: a.tx.sig, t: now_ns(), cp: None, active: o.active, venue: m.venue, signer },
            Pred::Damm(p) => Check { pool: i, trig: a.tx.sig, t: now_ns(), cp: Some((p.sqrt_price, 0)), active: None, venue: m.venue, signer },
        };
        self.checks.insert(i, check);
        self.trig_pending.insert(a.tx.sig, (signer, now_ns()));
        // WP-00 (F16): a decoded swap is a hint only. Its checks and bookkeeping above ran (the signer skip, signer
        // statistics, predictions.jsonl's accuracy data), but nothing is predicted, priced
        // or sent from it: no `preds` entry, so no route is ever priced on a state that may never exist, and the state
        // path is never blocked by a pending prediction (state_trigger's two skips cannot fire)
        if !self.cfg.decoded_sends {
            self.count("trigger_hint_only");
            self.write_trigger(a, sw, i, t_engine, t_resolved, None, true);
            return;
        }
        self.preds.insert(i, PredEntry { trig: a.tx.sig, t: now_ns(), pred: after });
        let best = self.best_cycle(i, now);
        let st = self.write_trigger(a, sw, i, t_engine, t_resolved, best.as_ref().map(|b| b.net), false);
        let m = self.reg.pools[i].clone();
        if let Some(b) = best {
            if b.net >= self.cfg.min_profit_lamports as i64 {
                self.count("opportunity");
                let id = self.next_id; self.next_id += 1;
                self.record_caps(id, &b, "decoded", now);
                let (bi, si) = (self.reg.by_pool[&b.buy], self.reg.by_pool[&b.sell]);
                self.watch.entry(bi).or_default().push(id);
                self.watch.entry(si).or_default().push(id);
                self.opps.insert(id, Opp { id, trig: a.tx.sig, trig_feed: a.feed, slot: a.slot, st, trig_pool: m.pool, buy: b.buy, sell: b.sell,
                    mint: b.mint, size: b.size, gross: b.gross, net: b.net, cu: b.cu, crossed: b.crossed,
                    deadline: now_ns() + self.cfg.outcome_watch_ms * 1_000_000, trig_cu_price: a.tx.cu_price(), landed: None, touches: Vec::new() });
                if self.cfg.confirm_trigger_ms > 0 && self.exec.is_some() {
                    // act once every part of the trigger pool shows the trigger (the vaults hold a CP pool's reserves)
                    let parts = match m.venue { Venue::Dlmm | Venue::DammV2 => vec![m.pool], Venue::RayCpmm => vec![m.vault0, m.vault1, m.pool], _ => vec![m.vault0, m.vault1] };
                    self.confirm_wait.push_back((id, a.tx.sig, parts, now_ns() + self.cfg.confirm_trigger_ms * 1_000_000));
                } else { self.after_opportunity(id); }
            } else { self.count("below_min_profit"); }
        }
    }

    /// Steps 2 and 3 (exec.rs): simulate this decision's real transaction, and/or send a canary built on it.
    fn after_opportunity(&mut self, id: u64) {
        let Some(size) = self.opps.get(&id).map(|o| o.size) else { return };
        let Some(x) = self.exec.as_mut() else { return };
        let (sim, send) = (x.wants_sim(size), x.wants_send());
        // a live trade first (it is the one racing), then the free simulation
        if let Some(cap) = send { match self.route_in(id, size.min(cap)) { Some(r) => self.exec.as_mut().unwrap().send(r), None => self.count("send_unquotable") } }
        if let Some(sz) = sim { match self.route_in(id, sz) { Some(r) => self.exec.as_mut().unwrap().simulate(r), None => self.count("sim_unquotable") } }
    }

    /// `arb-lab simcheck`: one round trip per ordered pool pair at `size`, on the pools as they are (no trigger), spread
    /// over venue combinations, to check the builder on real pools before any decision needs it. At most `max`.
    pub fn probe_routes(&mut self, size: u64, max: usize) -> Vec<crate::exec::RouteIn> {
        let mut pairs: Vec<Vec<usize>> = self.reg.pairs.values().cloned().collect();
        // venue mix first: pairs whose pools span the most venues
        pairs.sort_by_key(|v| std::cmp::Reverse(v.iter().map(|&i| self.reg.pools[i].venue).collect::<HashSet<_>>().len()));
        let mut out = Vec::new();
        let mut combos: HashMap<(Venue, Venue), usize> = HashMap::default();
        for v in pairs {
            for &b in &v {
                for &sl in &v {
                    if b == sl || out.len() >= max { continue; }
                    let (pb, ps) = (&self.reg.pools[b], &self.reg.pools[sl]);
                    let c = combos.entry((pb.venue, ps.venue)).or_default();
                    if *c >= max / 8 + 1 { continue; }   // spread over venue combinations
                    *c += 1;
                    let mint = if pb.t0 == *WSOL { pb.t1 } else { pb.t0 };
                    // compute units as best_cycle sizes them: from the bins each leg's quote really crosses
                    let now = unix_now();
                    let q = self.leg(b, now).zip(self.leg(sl, now)).and_then(|(lb, ls)| {
                        let (mid, c1) = leg_quote(&lb, pb.t0 == *WSOL, size, now)?;
                        let (_, c2) = leg_quote(&ls, ps.t0 == mint, mid, now)?;
                        Some((c1, c2))
                    });
                    let Some((c1, c2)) = q else { self.count("probe_unquotable"); continue };
                    let cu = (((29_000 + pb.venue.leg_cu(c1) + ps.venue.leg_cu(c2)) as f64 * 1.10 / 1000.0).ceil() * 1000.0) as u64;
                    let id = self.next_id;
                    self.next_id += 1;
                    let st = Stages { rx: 0, decoded: 0, engine: 0, resolved: 0, decided: now_ns() };
                    self.opps.insert(id, Opp { id, trig: [0; 64], trig_feed: 0, slot: self.slot, st, trig_pool: pb.pool, buy: pb.pool, sell: ps.pool,
                        mint, size, gross: 0, net: 0, cu, crossed: (c1, c2), deadline: u64::MAX, trig_cu_price: None, landed: None, touches: Vec::new() });
                    if let Some(r) = self.route_in(id, size) { out.push(r); } else { self.count("probe_unquotable"); }
                    self.opps.remove(&id);
                }
            }
        }
        out
    }

    /// the same route rebuilt from the store as it is now (simcheck refreshes the pools first)
    pub fn refresh_route(&mut self, r: &crate::exec::RouteIn) -> Option<crate::exec::RouteIn> {
        let (bi, si) = (*self.reg.by_pool.get(&r.buy.pool)?, *self.reg.by_pool.get(&r.sell.pool)?);
        let now = unix_now();
        let (pb, ps) = (&self.reg.pools[bi], &self.reg.pools[si]);
        let (lb, ls) = (self.leg(bi, now)?, self.leg(si, now)?);
        let (_, c1) = leg_quote(&lb, pb.t0 == *WSOL, r.size, now)?;
        let (mid, _) = leg_quote(&lb, pb.t0 == *WSOL, r.size, now)?;
        let (_, c2) = leg_quote(&ls, ps.t0 == r.mint, mid, now)?;
        let cu = (((29_000 + pb.venue.leg_cu(c1) + ps.venue.leg_cu(c2)) as f64 * 1.10 / 1000.0).ceil() * 1000.0) as u64;
        let id = self.next_id;
        self.next_id += 1;
        let st = Stages { rx: 0, decoded: 0, engine: 0, resolved: 0, decided: now_ns() };
        self.opps.insert(id, Opp { id, trig: [0; 64], trig_feed: 0, slot: self.slot, st, trig_pool: pb.pool, buy: pb.pool, sell: ps.pool,
            mint: r.mint, size: r.size, gross: 0, net: 0, cu, crossed: (c1, c2), deadline: u64::MAX, trig_cu_price: None, landed: None, touches: Vec::new() });
        let out = self.route_in(id, r.size);
        self.opps.remove(&id);
        out
    }

    /// the accounts a route's two pools are quoted from (pool, vaults, extras, followed DLMM bin arrays)
    pub fn route_accounts(&self, r: &crate::exec::RouteIn) -> Vec<Pk> {
        let mut k = Vec::new();
        for m in [&r.buy, &r.sell] {
            k.push(m.pool);
            if m.venue == Venue::Dlmm { if let Some(l) = self.store.dlmm_arrays.get(&m.pool) { k.extend(l.iter().map(|x| x.1)); } }
            else if m.venue != Venue::DammV2 { k.push(m.vault0); k.push(m.vault1); k.extend(m.extra.iter().copied()); }
        }
        k
    }

    /// Everything a build needs for opportunity `id` at `size`: both pools as they are now, our predicted legs at that
    /// size (on the trigger-adjusted state), and for DLMM the bin arrays we hold and where the quote ends.
    fn route_in(&self, id: u64, size: u64) -> Option<crate::exec::RouteIn> {
        let o = self.opps.get(&id)?;
        let now = unix_now();
        let (bi, si) = (*self.reg.by_pool.get(&o.buy)?, *self.reg.by_pool.get(&o.sell)?);
        let (pb, ps) = (&self.reg.pools[bi], &self.reg.pools[si]);
        let (lb, ls) = (self.leg(bi, now)?, self.leg(si, now)?);
        let (mid, buy_end) = leg_quote_end(&lb, pb.t0 == *WSOL, size, now)?;
        let (back, sell_end) = leg_quote_end(&ls, ps.t0 == o.mint, mid, now)?;
        let live = |p: &crate::venues::PoolMeta| -> Vec<i64> { self.store.dlmm_arrays.get(&p.pool).map(|l| l.iter().filter(|(_, k)| self.store.get(k).is_some()).map(|(i, _)| *i).collect()).unwrap_or_default() };
        let data = |p: &crate::venues::PoolMeta| self.store.get(&p.pool).map(|a| a.data.clone());
        let trig_feed = if o.trig_feed == u16::MAX { Some("state".to_string()) } else { self.feeds.get(o.trig_feed as usize).cloned() };
        let p75 = |i: usize| -> Option<u64> {
            let q = self.pool_prices.get(&i)?;
            let mut v: Vec<u64> = q.iter().map(|x| x.1).collect();
            if v.len() < 3 { return None; }
            v.sort_unstable();
            Some(v[(v.len() * 3 / 4).min(v.len() - 1)])
        };
        let rival_cu_price = match (p75(bi), p75(si)) { (Some(a), Some(b)) => Some(a.max(b)), (a, b) => a.or(b) };
        Some(crate::exec::RouteIn { opp: id, trig: o.trig, trig_feed, slot: o.slot,
            st: [o.st.rx, o.st.decoded, o.st.engine, o.st.resolved, o.st.decided], buy: pb.clone(), sell: ps.clone(), buy_data: data(pb)?, sell_data: data(ps)?,
            buy_source: self.reg.source(&pb.pool), sell_source: self.reg.source(&ps.pool), mint: o.mint, size, mid, back,
            gross_at_opp: o.gross, net_at_opp: o.net, trig_cu_price: o.trig_cu_price, rival_cu_price, cu: o.cu,
            buy_live: live(pb), sell_live: live(ps), buy_end, sell_end })
    }

    fn quote_input_for_output(&self, i: usize, zfo: bool, want: u64, now: i64) -> Option<u64> {
        let leg = self.leg(i, now)?;
        crate::venues::solve_exact_in(want, |x| leg_quote(&leg, zfo, x, now).map(|q| q.0))
    }

    /// Best two-leg SOL round trip through pool `i` and any other pool on its pair, using `i`'s predicted state.
    fn best_cycle(&self, i: usize, now: i64) -> Option<Best> {
        let m = &self.reg.pools[i];
        let key = pair_key(&m.t0, &m.t1);
        let others = self.reg.pairs.get(&key)?;
        let mint = if m.t0 == *WSOL { m.t1 } else { m.t0 };
        let sizes: Vec<u64> = self.cfg.sizes_sol.iter().map(|s| (s * LAMPORTS_PER_SOL) as u64).collect();
        let Some(leg_i) = self.leg(i, now) else { return None };
        let mut best: Option<Best> = None;
        for &j in others {
            if j == i { continue; }
            let Some(leg_j) = self.leg(j, now) else { continue };
            for (buy, sell) in [(i, j), (j, i)] {
                let (pb, ps) = (&self.reg.pools[buy], &self.reg.pools[sell]);
                let (lb, ls) = if buy == i { (&leg_i, &leg_j) } else { (&leg_j, &leg_i) };
                let zb = pb.t0 == *WSOL;          // SOL -> mint on the buy pool
                let zs = ps.t0 == mint;           // mint -> SOL on the sell pool
                let run = |x: u64| -> Option<(i64, u32, u32)> {
                    let (mid, c1) = leg_quote(lb, zb, x, now)?;
                    let (back, c2) = leg_quote(ls, zs, mid, now)?;
                    Some((back as i64 - x as i64, c1, c2))
                };
                // ladder, then a ternary refinement around the best rung (profit is unimodal in size)
                let mut top: Option<(u64, i64, u32, u32)> = None;
                let mut idx = 0;
                for (k, &x) in sizes.iter().enumerate() {
                    if let Some((p, c1, c2)) = run(x) { if top.map_or(true, |t| p > t.1) { top = Some((x, p, c1, c2)); idx = k; } }
                }
                let Some(mut t) = top else { continue };
                if t.1 <= 0 { continue; }
                let mut lo = if idx > 0 { sizes[idx - 1] } else { sizes[0] / 4 };
                let mut hi = sizes.get(idx + 1).copied().unwrap_or(sizes[idx] * 2);
                for _ in 0..24 {
                    if hi - lo < 1_000 { break; }
                    let (m1, m2) = (lo + (hi - lo) / 3, hi - (hi - lo) / 3);
                    let (p1, p2) = (run(m1).map_or(i64::MIN, |r| r.0), run(m2).map_or(i64::MIN, |r| r.0));
                    if p1 < p2 { lo = m1; } else { hi = m2; }
                }
                let x = (lo + hi) / 2;
                if let Some((p, c1, c2)) = run(x) { if p > t.1 { t = (x, p, c1, c2); } }
                let cu = (((29_000 + pb.venue.leg_cu(t.2) + ps.venue.leg_cu(t.3)) as f64 * 1.10 / 1000.0).ceil() * 1000.0) as u64;
                let fee = 5_000 + self.cfg.cu_price_micro * cu / 1_000_000 + self.min_tip;
                let net = t.1 - fee as i64;
                // a round trip returning over 1.5x its input is a broken quote (w5h seg 4: one PumpSwap pool quoted
                // 9.9e12 lamports, 663 times): it must not win the pick over the token's real cycles
                if t.1 > t.0 as i64 { continue; }
                if best.as_ref().map_or(true, |b| net > b.net) {
                    best = Some(Best { buy: pb.pool, sell: ps.pool, mint, size: t.0, gross: t.1, net, cu, crossed: (t.2, t.3) });
                }
            }
        }
        best
    }

    /// caps.jsonl: the decided pair's best round trip at each budget in [strategy] budget_caps_sol. Profit rises with
    /// size up to the unconstrained best size, so each cap trades min(best size, cap). A size a pool can't quote (e.g.
    /// past the DLMM bin arrays we follow) is recorded as null.
    fn record_caps(&self, id: u64, b: &Best, kind: &str, now: i64) {
        if self.cfg.budget_caps_sol.is_empty() || !self.rec.is_on() { return; }
        let (Some(&bi), Some(&si)) = (self.reg.by_pool.get(&b.buy), self.reg.by_pool.get(&b.sell)) else { return };
        let (Some(lb), Some(ls)) = (self.leg(bi, now), self.leg(si, now)) else { return };
        let (pb, ps) = (&self.reg.pools[bi], &self.reg.pools[si]);
        let (zb, zs) = (pb.t0 == *WSOL, ps.t0 == b.mint);
        let run = |x: u64| -> Option<i64> { let (mid, _) = leg_quote(&lb, zb, x, now)?; let (back, _) = leg_quote(&ls, zs, mid, now)?; Some(back as i64 - x as i64) };
        let max = (self.cfg.budget_caps_sol.iter().cloned().fold(0.0, f64::max) * LAMPORTS_PER_SOL) as u64;
        // unconstrained best size in (0, max]: geometric ladder, then ternary refinement
        let mut x = b.size.max(1_000_000);
        let mut best = (b.size, run(b.size).unwrap_or(b.gross));
        while x < max { x = (x * 2).min(max); match run(x) { Some(p) if p > best.1 => best = (x, p), Some(_) => break, None => break } }
        let (mut lo, mut hi) = (best.0 / 2, (best.0 * 2).min(max));
        for _ in 0..30 {
            if hi <= lo + 1_000 { break; }
            let (m1, m2) = (lo + (hi - lo) / 3, hi - (hi - lo) / 3);
            if run(m1).unwrap_or(i64::MIN) < run(m2).unwrap_or(i64::MIN) { lo = m1; } else { hi = m2; }
        }
        let xs = (lo + hi) / 2;
        if let Some(p) = run(xs) { if p > best.1 { best = (xs, p); } }
        let fee = b.gross - b.net;
        let caps: Vec<Value> = self.cfg.budget_caps_sol.iter().map(|c| {
            let cap = (c * LAMPORTS_PER_SOL) as u64;
            let x = best.0.min(cap);
            match run(x) { Some(p) => json!([c, x, p - fee]), None => json!([c, x, Value::Null]) }
        }).collect();
        let line = json!({ "id": id, "kind": kind, "slot": self.slot, "buy": b58(&b.buy), "sell": b58(&b.sell), "buy_venue": pb.venue, "sell_venue": ps.venue,
            "mint": b58(&b.mint), "best_size": best.0, "best_net": best.1 - fee, "at_trade_size": [b.size, b.net], "caps": caps });
        self.rec.json(rec::CAPS, line);
    }

    // ---------------------------------------------------------------- pool state

    fn on_account(&mut self, key: Pk, data: Vec<u8>, slot: u64, t: u64, txn: Option<[u8; 64]>, t_engine: u64) {
        if !self.store.update(key, data, slot, t, txn) { return; }
        if slot > self.store_slot_max { self.store_slot_max = slot; }
        let Some(&i) = self.acct_pool.get(&key) else { return };
        let Some(txn) = txn else { return };
        if self.rec.is_on() {
            if self.moves_seen.len() > 500_000 { self.moves_seen.clear(); }
            if self.moves_seen.insert((sig8(&txn), i as u32)) {
                // moves.log v2: `sig slot pool t_ns acct write_version role` (the write version comes with WP-03: `-`);
                // the base58 is done on the recorder's writer
                let pool = self.reg.pools[i].pool;
                let role = if key == pool { "pool" } else { "vault" };
                self.rec.emit(rec::MOVES, Record::enc(move |o| { let _ = write!(o, "{} {slot} {} {t} {} - {role}", sigs58(&txn), b58(&pool), b58(&key)); }));
            }
        }
        if let Some((sg, _)) = self.trig_pending.remove(&txn) { self.signer_stats.entry(sg).or_default().0 += 1; }
        // the real state now includes this transaction; a prediction made for it is no longer needed
        if self.preds.get(&i).map_or(false, |p| p.trig == txn) { self.preds.remove(&i); }
        // trades waiting for this trigger go now, priced on the real state (the prediction is gone)
        if !self.confirm_wait.is_empty() { self.on_confirm(key, &txn); }
        if self.cfg.state_triggers {
            let k = (sig8(&txn), i as u32);
            if !self.state_first.contains_key(&k) {
                self.state_first.insert(k, (t, t_engine));
                self.state_first_order.push_back(k);
                while self.state_first_order.len() > STATE_FIRST_MAX { if let Some(old) = self.state_first_order.pop_front() { self.state_first.remove(&old); } }
            }
            if self.state_pending.first().is_some_and(|p| p.txn != txn) { self.flush_state(); }
            // one entry per pool, with the times of its first update stamped `txn` (later parts of the same pool add
            // nothing: the evaluation at the flush sees them all)
            if !self.state_pending.iter().any(|p| p.pool == i) { self.state_pending.push(StatePending { pool: i, txn, slot, t_recv: t, t_engine }); }
        }
        self.check_prediction(i, txn);
        let pool_key = self.reg.pools[i].pool;
        if let Some(ids) = self.watch.get(&i).cloned() {
            for id in ids {
                let Some(o) = self.opps.get_mut(&id) else { continue };
                if txn == o.trig { if o.landed.is_none() { o.landed = Some(slot); } continue; }
                if !o.touches.iter().any(|x| x.1 == txn && x.0 == pool_key) { o.touches.push((pool_key, txn, slot, t)); }
            }
        }
    }

    /// Compare the trigger's predicted effect with the pool once every part shows that transaction.
    fn check_prediction(&mut self, i: usize, txn: [u8; 64]) {
        let Some(c) = self.checks.get(&i) else { return };
        if c.trig != txn { return; }
        let m = self.reg.pools[i].clone();
        let by_trig = |k: &Pk| self.store.get(k).map_or(false, |a| a.txn == Some(txn));
        let line = match m.venue {
            Venue::Dlmm => {
                let Some(p) = self.store.get(&m.pool) else { return };
                let actual = crate::venues::i32_at(&p.data, 76);
                json!({ "sig": sigs58(&txn), "venue": m.venue, "pool": b58(&m.pool), "pred_active": c.active, "actual_active": actual,
                    "match": c.active == actual })
            }
            Venue::DammV2 => {
                if !by_trig(&m.pool) { return; }
                let Some(p) = self.store.get(&m.pool).and_then(|a| crate::venues::dammv2::decode(&a.data)) else { return };
                let pred = c.cp.map(|x| x.0).unwrap_or(0);
                json!({ "sig": sigs58(&txn), "venue": m.venue, "pool": b58(&m.pool), "sqrt_price_pred": pred.to_string(), "sqrt_price": p.sqrt_price.to_string(),
                    "match": pred == p.sqrt_price })
            }
            _ => {
                // both vaults (and the CPMM pool, whose owed fees move) must show the trigger
                if !(by_trig(&m.vault0) && by_trig(&m.vault1)) || (m.venue == Venue::RayCpmm && !by_trig(&m.pool)) { return; }
                let Ok(Snap::Cp(s)) = self.store.snapshot(&m, unix_now()) else { return };
                let Some((p0, p1)) = c.cp else { return };
                let bps = |p: u128, a: u128| if a == 0 { 0.0 } else { (p as f64 - a as f64) / a as f64 * 1e4 };
                json!({ "sig": sigs58(&txn), "venue": m.venue, "pool": b58(&m.pool), "r0_pred": p0.to_string(), "r0": s.r0.to_string(),
                    "r1_pred": p1.to_string(), "r1": s.r1.to_string(), "err0_bps": bps(p0, s.r0), "err1_bps": bps(p1, s.r1),
                    "err0": p0 as i128 - s.r0 as i128, "err1": p1 as i128 - s.r1 as i128 })
            }
        };
        self.rec.json(rec::PREDICTIONS, line);
        self.checks.remove(&i);
        self.count("pred_checked");
    }

    /// Follow DLMM bin arrays around each pool's active bin; fetch newly followed arrays once over RPC.
    fn follow_dlmm(&mut self) {
        let drift = self.store.dlmm_drift(&self.reg);
        if drift.is_empty() { return; }
        let mut fetch = Vec::new();
        for (pool, list) in drift {
            for (_, k) in &list { if self.store.get(k).is_none() { fetch.push(*k); } }
            self.store.dlmm_arrays.insert(pool, list);
        }
        self.publish_watch_list();
        if !fetch.is_empty() { self.fetch_accounts(fetch); }
    }

    pub fn publish_watch_list(&self) {
        let Some(io) = &self.io else { return };
        let mut l: Vec<String> = self.reg.static_accounts().iter().map(b58).collect();
        for list in self.store.dlmm_arrays.values() { for (_, k) in list { l.push(b58(k)); } }
        let _ = io.watch_list.send(l);
    }

    /// accounts (newly followed DLMM bin arrays), fetched on the background runtime; they come back as account events
    fn fetch_accounts(&mut self, keys: Vec<Pk>) {
        let Some(io) = &self.io else { self.offline_fetches.push(("accounts", keys)); return };
        let (rpc, back) = (io.rpc.clone(), io.tx_back.clone());
        io.rt.spawn(async move {
            if let Ok((slot, v)) = rpc.accounts(&keys).await {
                for (k, a) in keys.iter().zip(v) {
                    if let Some(a) = a { let _ = back.send(Event::Account { slot, pubkey: *k, owner: a.owner, lamports: a.lamports, data: a.data, t: now_ns(), txn: None }); }
                }
            }
        });
    }

    // ---------------------------------------------------------------- outcomes

    fn finish_opp(&mut self, id: u64) {
        let Some(o) = self.opps.remove(&id) else { return };
        for p in [&o.buy, &o.sell] {
            if let Some(&i) = self.reg.by_pool.get(p) { if let Some(v) = self.watch.get_mut(&i) { v.retain(|x| *x != id); } }
        }
        // the taker: the first transaction after the trigger that touched both pools of the round trip
        let mut by_sig: HashMap<[u8; 64], (HashSet<Pk>, u64, u64)> = HashMap::default();
        for (p, s, slot, t) in &o.touches {
            let e = by_sig.entry(*s).or_insert((HashSet::default(), *slot, *t));
            e.0.insert(*p);
        }
        let taker = by_sig.iter().filter(|(_, v)| v.0.contains(&o.buy) && v.0.contains(&o.sell)).min_by_key(|(_, v)| (v.1, v.2)).map(|(s, v)| (*s, v.1));
        let trig_info = self.sigs.get(&sig8(&o.trig));
        let arrivals: serde_json::Map<String, serde_json::Value> = trig_info.map(|s| s.arrivals()
            .map(|(f, t)| (self.feeds.get(f as usize).cloned().unwrap_or_default(), json!(t))).collect()).unwrap_or_default();
        // on the leaders' PoH clocks: when the trigger ran, and how long after it the taker ran (concrete, not network time)
        let tp = self.poh.get(&o.trig).copied();
        let poh_json = json!({ "trigger": tp.map(|p| json!({ "slot": p.slot, "ms_in_slot": p.ms(), "ticks": p.ticks })),
            "taker_ms_after_trigger": taker.and_then(|(s, _)| self.poh.get(&s).copied()).zip(tp).and_then(|(a, b)| a.ms_after(&b)) });
        let taker_json = taker.map(|(s, slot)| {
            let seen = self.sigs.get(&sig8(&s));
            json!({ "sig": sigs58(&s), "slot": slot, "first_seen_ns": seen.map(|x| x.first_t),
                "first_feed": seen.and_then(|x| self.feeds.get(x.first_feed as usize)),
                "window_ms": seen.zip(trig_info).map(|(x, tr)| (x.first_t as f64 - tr.first_t as f64) / 1e6) })
        });
        self.rec.json(rec::OPPORTUNITIES, json!({
            "id": o.id, "trigger": sigs58(&o.trig), "trigger_feed": self.feeds.get(o.trig_feed as usize), "slot": o.slot,
            "trigger_pool": b58(&o.trig_pool), "buy_pool": b58(&o.buy), "sell_pool": b58(&o.sell), "mint": b58(&o.mint),
            "buy_source": self.reg.source(&o.buy), "sell_source": self.reg.source(&o.sell),
            "size_lamports": o.size, "gross_lamports": o.gross, "net_lamports": o.net, "cu": o.cu, "bins_crossed": [o.crossed.0, o.crossed.1],
            "st": o.st, "arrivals": arrivals, "trigger_landed_slot": o.landed, "taker": taker_json, "poh": poh_json,
            "touches": o.touches.len() }));
    }
}

struct Best { buy: Pk, sell: Pk, mint: Pk, size: u64, gross: i64, net: i64, cu: u64, crossed: (u32, u32) }

/// A pool ready to quote (see `Engine::leg`)
enum Leg<'a> {
    Cp(cp::CpSnap),
    Dlmm { pair: &'a [u8], arrays: HashMap<i64, &'a [u8]>, over: Option<&'a dlmm::Overlay> },
    /// DAMM v2 pool (live or predicted) and the slot its fee schedule is evaluated at
    Damm(crate::venues::dammv2::DammPool, u64),
}

/// a leg's output and, for DLMM, the bin its quote ends in (the builder names the bin arrays up to it)
fn leg_quote_end(l: &Leg, zfo: bool, amount: u64, now: i64) -> Option<(u64, Option<i32>)> {
    match l {
        Leg::Cp(s) => cp::quote(s, zfo, amount).map(|q| (q.out, None)),
        Leg::Dlmm { pair, arrays, over } => {
            let v = dlmm::View { pair, arrays, over: *over };
            dlmm::quote(&v, zfo, amount, now, false).ok().map(|q| (q.out, Some(q.end_active)))
        }
        Leg::Damm(p, slot) => crate::venues::dammv2::quote_exact_in(p, zfo, amount, *slot, now).map(|q| (q.0, None)),
    }
}

/// size probe: output and bins crossed, no state kept
fn leg_quote(l: &Leg, zfo: bool, amount: u64, now: i64) -> Option<(u64, u32)> {
    match l {
        Leg::Cp(s) => cp::quote(s, zfo, amount).map(|q| (q.out, 0)),
        Leg::Dlmm { pair, arrays, over } => {
            let v = dlmm::View { pair, arrays, over: *over };
            dlmm::quote(&v, zfo, amount, now, false).ok().map(|q| (q.out, q.crossed))
        }
        Leg::Damm(p, slot) => crate::venues::dammv2::quote_exact_in(p, zfo, amount, *slot, now).map(|q| (q.0, 0)),
    }
}

/// A Meteora DAMM v2 `swap` (exact in: amount_in @8, minimum_amount_out @16) or `swap2` (amount_0 @8, amount_1 @16,
/// swap_mode @24: 0 exact in = (in, min out), 2 exact out = (out, max in); 1, partial fill, is not predicted).
/// accounts: [0] pool_authority [1] pool [2] user in [3] user out [4] vault a [5] vault b [6] mint a [7] mint b [8] payer.
/// The vaults are mint-ordered whatever the direction, so the direction comes from the payer's own input account.
fn damm_pending<'a>(data: &[u8], acc: &[Pk], meta: &dyn Fn(&Pk) -> Option<&'a PoolMeta>, ata: &dyn Fn(&Pk, &Pk, &Pk) -> Pk) -> Option<PendingSwap> {
    if data.len() < 24 || acc.len() < 9 { return None; }
    let disc = &data[..8];
    let (exact_out, amount, limit) = if disc == [0xf8, 0xc6, 0x9e, 0x91, 0xe1, 0x75, 0x87, 0xc8] {
        (false, crate::venues::u64_at(data, 8)?, crate::venues::u64_at(data, 16)?)
    } else if disc == [0x41, 0x4b, 0x3f, 0x4c, 0xeb, 0x5b, 0x5b, 0x88] {
        match data.get(24) { Some(0) => (false, crate::venues::u64_at(data, 8)?, crate::venues::u64_at(data, 16)?), Some(2) => (true, crate::venues::u64_at(data, 8)?, crate::venues::u64_at(data, 16)?), _ => return None }
    } else { return None };
    let pool = acc[1];
    let m = meta(&pool)?;
    let (user, user_in) = (acc[8], acc[2]);
    let zfo = if user_in == ata(&user, &m.t0, &m.t0_prog) { true } else if user_in == ata(&user, &m.t1, &m.t1_prog) { false } else { return None };
    Some(PendingSwap { pool, venue: Venue::DammV2, zero_for_one: zfo, amount, exact_out, user, limit })
}

/// Interest set: venue programs, every followed pool and vault, plus the lookup tables real traders used on them.
pub fn interest(reg: &Registry, templates: Option<&str>) -> Interest {
    let mut keys: HashSet<Pk> = [Venue::PumpSwap, Venue::RayCpmm, Venue::RayAmmV4, Venue::Dlmm, Venue::DammV2].iter().map(|v| v.program()).collect();
    for &i in reg.pairs.values().flatten() { let m = &reg.pools[i]; keys.insert(m.pool); keys.insert(m.vault0); keys.insert(m.vault1); }
    let mut tables = HashSet::default();
    if let Some(path) = templates {
        if let Ok(text) = std::fs::read_to_string(path) {
            if let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) {
                let watched: HashSet<String> = reg.pairs.values().flatten().map(|&i| b58(&reg.pools[i].pool)).collect();
                if let Some(o) = v.as_object() {
                    for (pool, t) in o {
                        if !watched.contains(pool) { continue; }
                        for a in t["alts"].as_array().into_iter().flatten() {
                            if let Some(s) = a.as_str() { if let Ok(b) = bs58::decode(s).into_vec() { if let Ok(k) = Pk::try_from(b) { tables.insert(k); } } }
                        }
                    }
                }
            }
        }
    }
    Interest { keys, tables: std::sync::RwLock::new(tables) }
}

pub fn initial_dlmm_arrays(reg: &Registry, store: &mut Store) {
    for m in reg.pools.iter().filter(|m| m.venue == Venue::Dlmm) {
        if let Some(a) = store.get(&m.pool) { if let Some(active) = crate::venues::i32_at(&a.data, 76) { store.dlmm_arrays.insert(m.pool, pools::dlmm_arrays(&m.pool, active)); } }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::venues::PoolMeta;

    const MINT: Pk = [7u8; 32];
    const SIGNER: Pk = [5u8; 32];
    const TRIG: [u8; 64] = [9u8; 64];

    /// a Raydium AMM v4 pool account: status 1 (swaps on), fee 25/10,000, no PnL owed
    fn ammv4_pool() -> Vec<u8> {
        let mut p = vec![0u8; 752];
        p[0..8].copy_from_slice(&1u64.to_le_bytes());
        p[176..184].copy_from_slice(&25u64.to_le_bytes());
        p[184..192].copy_from_slice(&10_000u64.to_le_bytes());
        p
    }
    fn vault(amount: u64) -> Vec<u8> { let mut v = vec![0u8; 165]; v[64..72].copy_from_slice(&amount.to_le_bytes()); v }
    fn meta(n: u8) -> PoolMeta {
        PoolMeta { venue: Venue::RayAmmV4, pool: [n; 32], t0: MINT, t1: *WSOL, vault0: [n + 10; 32], vault1: [n + 20; 32],
            t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false }
    }

    struct Rig { eng: Engine, dir: std::path::PathBuf, rec: Rec, _rt: tokio::runtime::Runtime }
    impl Drop for Rig { fn drop(&mut self) { self.rec.close(); let _ = std::fs::remove_dir_all(&self.dir); } }

    /// two AMM v4 pools on WSOL/MINT, 1% apart (a round trip between them pays), held at slot 10
    fn rig(name: &str, cfg: StrategyCfg) -> Rig {
        let (a, b) = (meta(1), meta(2));
        let mut reg = Registry { pools: vec![a.clone(), b.clone()], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
        reg.by_pool.insert(a.pool, 0);
        reg.by_pool.insert(b.pool, 1);
        reg.pairs.insert(pair_key(&MINT, &WSOL), vec![0, 1]);
        let mut store = Store::default();
        for (m, sol) in [(&a, 1_000u64), (&b, 1_010)] {
            store.update(m.pool, ammv4_pool(), 10, 1, None);
            store.update(m.vault0, vault(1_000_000_000_000_000), 10, 1, None);
            store.update(m.vault1, vault(sol * 1_000_000_000), 10, 1, None);
        }
        let dir = std::env::temp_dir().join(format!("arbx-engine-{name}-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&dir).unwrap();
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        let (tx, _rx) = crossbeam_channel::unbounded();
        let (wtx, _wrx) = tokio::sync::watch::channel(Vec::new());
        let interest = Arc::new(Interest { keys: Default::default(), tables: Default::default() });
        let rec = rec::start(rec::Opts { dir: dir.clone(), run: "test".into(), producer: "test".into(), cfg: Default::default(), feeds: vec!["feed0".into()], monitor: false, echo: None }).unwrap();
        let eng = Engine::new(Arc::new(reg), store, cfg, vec!["feed0".into()], 1_000, interest, rec.clone(), crate::rpc::Rpc::race(vec![]),
            rt.handle().clone(), tx, wtx).unwrap();
        Rig { eng, dir, rec, _rt: rt }
    }

    /// a decoded swap of 1 SOL into pool 1 by SIGNER
    fn hint() -> (Arrival, PendingSwap) {
        let tx = Tx { sig: TRIG, keys: vec![SIGNER], ..Default::default() };
        (Arrival { feed: 0, slot: 11, t_rx: 100, t_decoded: 200, executed: None, tx, poh: None },
         PendingSwap { pool: [1; 32], venue: Venue::RayAmmV4, zero_for_one: false, amount: 1_000_000_000, exact_out: false, user: SIGNER, limit: 0 })
    }
    fn n(e: &Engine, k: &str) -> u64 { e.counts.get(k).copied().unwrap_or(0) }
    fn lat(e: &Engine, name: &str) -> usize { e.lat.iter().find(|x| x.name == name).map_or(usize::MAX, |x| x.n() as usize) }

    /// WP-00 (F16): with decoded_sends off a decoded swap runs its checks and bookkeeping (the accuracy check, the signer's
    /// pending entry) and writes its triggers line with opp null, but nothing is predicted or priced from it
    #[test]
    fn decoded_swap_is_a_hint_only() {
        let mut r = rig("hint", StrategyCfg::default());
        let (a, sw) = hint();
        r.eng.on_trigger(&a, &sw, 300, 400);
        let e = &mut r.eng;
        assert_eq!((n(e, "trigger"), n(e, "trigger_hint_only"), n(e, "opportunity")), (1, 1, 0));
        assert!(e.preds.is_empty(), "no prediction: neither a priced route nor the state path's skip can use it");
        assert!(e.opps.is_empty());
        assert!(e.checks.contains_key(&0), "the accuracy check still runs (predictions.jsonl)");
        assert!(e.trig_pending.contains_key(&TRIG), "signer statistics keep learning");
        // review F9: a hint is not a pricing decision: its own series, the v1 ones stay for priced triggers
        assert_eq!((lat(e, "hint_rx_to_done"), lat(e, "rx_to_decided"), lat(e, "resolved_to_decided")), (1, 0, 0));
        r.rec.sync();
        let lines = rec::read_jsonl(&r.dir, "triggers").unwrap();
        let line = &lines[0];
        assert!(line["opp"].is_null());
        assert_eq!(line["hint_only"], json!(true));
        assert_eq!((line["st"]["rx"].as_u64(), line["st"]["engine"].as_u64()), (Some(100), Some(300)));
    }

    /// WP-00 (F16): skip_failing_signers works on the hint path (the check runs before the early return), and the
    /// skipped signer's statistics keep learning (review F10): its swap landing counts, and it is let back in
    #[test]
    fn failing_signer_is_skipped_before_the_hint_and_keeps_learning() {
        let mut r = rig("signer", StrategyCfg::default());
        r.eng.signer_stats.insert(SIGNER, (0, 4));
        let (a, sw) = hint();
        r.eng.on_trigger(&a, &sw, 300, 400);
        assert_eq!((n(&r.eng, "trigger_skip_signer_fails"), n(&r.eng, "trigger_hint_only")), (1, 0));
        assert!(r.eng.checks.is_empty(), "no accuracy check for a skipped signer");
        assert!(r.eng.trig_pending.contains_key(&TRIG), "but its swap is followed");
        // the swap lands (pool 1's accounts updated, stamped with it): ok + 1 -> 1 of 5 = 20%, still skipped
        let land = |e: &mut Engine, sig: [u8; 64], slot: u64| {
            e.on_account(meta(1).vault0, vault(1_000_000_000_000_000), slot, 2_000, Some(sig), 2_100);
            e.on_account(meta(1).vault1, vault(1_000 * 1_000_000_000), slot, 2_000, Some(sig), 2_100);
        };
        land(&mut r.eng, TRIG, 11);
        assert_eq!(r.eng.signer_stats[&SIGNER], (1, 4));
        // its next swap is skipped too, and lands: 2 of 6 >= 25%: let back in
        let (mut a, sw) = hint();
        a.tx.sig = [21u8; 64];
        r.eng.on_trigger(&a, &sw, 300, 400);
        land(&mut r.eng, [21u8; 64], 12);
        assert_eq!(r.eng.signer_stats[&SIGNER], (2, 4));
        let (mut a, sw) = hint();
        a.tx.sig = [23u8; 64];
        r.eng.on_trigger(&a, &sw, 300, 400);
        assert_eq!((n(&r.eng, "trigger_skip_signer_fails"), n(&r.eng, "trigger_hint_only")), (2, 1));
    }

    /// decoded_sends = true keeps arb-lab's decoded path (prediction, priced opportunity)
    #[test]
    fn decoded_sends_on_keeps_the_old_path() {
        let mut r = rig("decoded", StrategyCfg { decoded_sends: true, ..StrategyCfg::default() });
        let (a, sw) = hint();
        r.eng.on_trigger(&a, &sw, 300, 400);
        let e = &r.eng;
        assert_eq!((n(e, "trigger_hint_only"), n(e, "opportunity")), (0, 1));
        assert!(e.preds.contains_key(&0));
    }

    /// WP-00 (F13): a state trigger's stages are the pool's first update stamped with the transaction (receive time and
    /// dequeue), the evaluation's start and the decision, and every evaluation feeds the three state-path series
    #[test]
    fn state_trigger_carries_update_receive_and_dequeue_times() {
        let mut r = rig("state", StrategyCfg { state_triggers: true, ..StrategyCfg::default() });
        let b = meta(2);
        const T: [u8; 64] = [3u8; 64];
        // T moves pool 2 (both vaults, two updates); pool 2 is now 2% above pool 1
        r.eng.on_account(b.vault1, vault(1_020 * 1_000_000_000), 11, 1_000, Some(T), 1_500);
        r.eng.on_account(b.vault0, vault(990_000_000_000_000), 11, 1_100, Some(T), 1_600);
        assert_eq!(r.eng.state_pending.len(), 1, "one entry per (pool, txn)");
        assert_eq!((r.eng.state_pending[0].t_recv, r.eng.state_pending[0].t_engine), (1_000, 1_500), "the first update's times");
        r.eng.flush_state();
        let e = &r.eng;
        assert_eq!(n(e, "state_opportunity"), 1);
        for s in ["state_recv_to_engine", "state_engine_to_decided", "state_recv_to_decided"] { assert_eq!(lat(e, s), 1, "{s}"); }
        assert_eq!(e.lat.iter().find(|x| x.name == "state_recv_to_engine").unwrap().kept()[0], 500);
        assert!(e.caps_pending.is_empty(), "the caps line is written at the end of the flush");
        let o = e.opps.values().next().unwrap();
        assert_eq!((o.st.rx, o.st.decoded, o.st.engine), (1_000, 1_000, 1_500));
        assert!(o.st.resolved > o.st.engine && o.st.decided >= o.st.resolved, "evaluation start, then the decision");
        // an evaluation that finds nothing is a sample too
        const U: [u8; 64] = [4u8; 64];
        let mut r = rig("state2", StrategyCfg { state_triggers: true, min_profit_lamports: u64::MAX / 4, ..StrategyCfg::default() });
        r.eng.on_account(b.vault1, vault(1_020 * 1_000_000_000), 11, 1_000, Some(U), 1_500);
        r.eng.on_account(b.vault0, vault(990_000_000_000_000), 11, 1_100, Some(U), 1_600);
        r.eng.flush_state();
        assert_eq!((n(&r.eng, "state_opportunity"), lat(&r.eng, "state_recv_to_decided")), (0, 1));
    }

    /// review F4: the engine queue empties between the two vault updates of one transaction, so a flush runs on the
    /// half-done pool (incomplete: nothing priced) and drops its entry. The evaluation after the second part still
    /// carries the FIRST part's receive and dequeue times
    #[test]
    fn state_trigger_keeps_the_first_update_time_across_a_flush() {
        let mut r = rig("state-split", StrategyCfg { state_triggers: true, ..StrategyCfg::default() });
        let b = meta(2);
        const T: [u8; 64] = [6u8; 64];
        r.eng.on_account(b.vault1, vault(1_020 * 1_000_000_000), 11, 1_000, Some(T), 1_500);
        r.eng.flush_state();
        assert_eq!((n(&r.eng, "state_opportunity"), lat(&r.eng, "state_recv_to_decided")), (0, 0), "half a pool is not priced");
        r.eng.on_account(b.vault0, vault(990_000_000_000_000), 11, 2_000, Some(T), 2_600);
        r.eng.flush_state();
        let e = &r.eng;
        assert_eq!(n(e, "state_opportunity"), 1);
        let o = e.opps.values().next().unwrap();
        assert_eq!((o.st.rx, o.st.engine), (1_000, 1_500), "the first part's times, not the second's (2,000 / 2,600)");
        assert!(e.state_first.is_empty(), "taken once the pool was complete");
    }

    /// PLAN WP-02 acceptance (F13), the engine benchmark: 100k synthetic account updates (50k transactions, each moving
    /// both vaults of one of 40 pools) through `Engine::new_offline`, with the recorder on and off. With it on (moves.log
    /// for every update group, status and the rest through the queues) `state_recv_to_decided` p99 is within 5 µs of the
    /// run without it, both with no opportunity priced and with about 1% of updates opening one (review F9: triggers,
    /// opportunities, caps and predictions are emitted then). Each mode runs three times, alternating, and the best p99
    /// of each is compared (other tests run on the same machine meanwhile)
    #[test]
    fn engine_benchmark_recorder_on_off() {
        const POOLS: u8 = 40;
        const TXS: u64 = 50_000;
        /// `min_profit`: u64::MAX / 4 prices no opportunity (moves only); a real threshold with `gaps` (every 200th
        /// transaction moves one pool 10% off its pair: it and the pair's next update open one) prices about 1% of
        /// updates as opportunities, whose caps and opportunities records are made on the engine thread too (review F9)
        fn engine(min_profit: u64) -> Engine {
            let mut reg = Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
            let mut store = Store::default();
            for n in 0..POOLS {
                // pairs of pools on 20 mints, 1% apart
                let mut m = meta(n + 1);
                m.pool = [n + 1; 32];
                m.vault0 = { let mut k = [n + 1; 32]; k[31] = 200; k };
                m.vault1 = { let mut k = [n + 1; 32]; k[31] = 201; k };
                m.t0 = { let mut k = MINT; k[0] = n / 2; k };
                reg.by_pool.insert(m.pool, n as usize);
                reg.pairs.entry(pair_key(&m.t0, &WSOL)).or_insert_with(Vec::new).push(n as usize);
                store.update(m.pool, ammv4_pool(), 10, 1, None);
                store.update(m.vault0, vault(1_000_000_000_000_000), 10, 1, None);
                store.update(m.vault1, vault((1_000 + (n % 2) as u64 * 10) * 1_000_000_000), 10, 1, None);
                reg.pools.push(m);
            }
            // the caps table (caps.jsonl) for every opportunity, as the stage-0 config has it
            Engine::new_offline(Arc::new(reg), store, StrategyCfg { state_triggers: true, min_profit_lamports: min_profit, budget_caps_sol: vec![0.5, 2.0, 10.0],
                ..StrategyCfg::default() })
        }
        fn bench(rec: Rec, min_profit: u64, gaps: bool) -> (u64, u64, u64) {
            let mut e = engine(min_profit);
            e.set_rec(rec);
            let mut status = |_: &str| {};
            for k in 0..TXS {
                let i = (k % POOLS as u64) as usize;
                let m = e.reg.pools[i].clone();
                let mut sig = [0u8; 64];
                sig[..8].copy_from_slice(&k.to_le_bytes());
                // one slot for all: the AMM v4 snapshot refuses parts more than 2 slots apart, and only the vaults move here
                let slot = 11;
                let sol = if gaps && k % 200 == 0 { 1_100 } else { 1_000 + (k % 7) };
                let t = now_ns();
                e.on_event(Event::Account { slot, pubkey: m.vault1, owner: [0; 32], lamports: 0, data: vault(sol * 1_000_000_000), t, txn: Some(sig) }, now_ns(), &mut status);
                e.on_event(Event::Account { slot, pubkey: m.vault0, owner: [0; 32], lamports: 0, data: vault(999_000_000_000_000), t: now_ns(), txn: Some(sig) }, now_ns(), &mut status);
                e.flush_state();
                // the opportunities end (opportunities.jsonl), as their watch window would end them, outside the timed part
                if gaps && k % 1_000 == 999 { e.finish(); }
            }
            let opps = n(&e, "state_opportunity");
            e.finish();
            let s = e.series_mut("state_recv_to_decided").unwrap();
            assert_eq!(s.n(), TXS, "every transaction evaluated");
            (s.pct(0.5), s.pct(0.99), opps)
        }
        let dir = std::env::temp_dir().join(format!("arbx-engine-bench-{}-{}", std::process::id(), now_ns()));
        let best = |v: &[(u64, u64, u64)]| v.iter().map(|x| x.1).min().unwrap();
        for (what, min_profit, gaps) in [("moves only", u64::MAX / 4, false), ("1% opportunities", 100_000_000, true)] {
            let (mut off, mut on) = (Vec::new(), Vec::new());
            for _ in 0..3 {
                off.push(bench(Rec::off(), min_profit, gaps));
                let rec = rec::start(rec::Opts { dir: dir.clone(), run: "bench".into(), producer: "test".into(), cfg: Default::default(), feeds: vec![], monitor: false, echo: None }).unwrap();
                on.push(bench(rec.clone(), min_profit, gaps));
                rec.close();
                assert_eq!(rec::read_text(&dir, "moves").unwrap().len() as u64, TXS, "the recorder wrote a moves line per transaction");
                if gaps {
                    let opps = on.last().unwrap().2;
                    assert!((TXS / 200..=TXS / 50).contains(&opps), "about 1% of updates open an opportunity: {opps}");
                    // the state path's records (decoded triggers, arrivals and predictions come from the tx feeds' path)
                    for s in ["caps", "opportunities"] { assert!(rec::read_jsonl(&dir, s).unwrap().len() as u64 >= opps / 2, "{s} recorded"); }
                } else {
                    assert_eq!(on.last().unwrap().2, 0);
                }
                let _ = std::fs::remove_dir_all(&dir);
            }
            let (p99_off, p99_on) = (best(&off), best(&on));
            eprintln!("{what}: state_recv_to_decided p50/p99 ns (opportunities): recorder off {off:?}, on {on:?}; best p99 off {p99_off} on {p99_on}");
            assert!(p99_on <= p99_off + 5_000, "{what}: recorder on adds {} ns to the p99", p99_on as i64 - p99_off as i64);
        }
    }

    /// review F6: a state opportunity's caps line waits until the flush has priced every pool of the transaction
    #[test]
    fn caps_line_waits_for_the_end_of_the_flush() {
        let mut r = rig("caps", StrategyCfg { state_triggers: true, ..StrategyCfg::default() });
        let b = meta(2);
        const T: [u8; 64] = [7u8; 64];
        r.eng.on_account(b.vault1, vault(1_020 * 1_000_000_000), 11, 1_000, Some(T), 1_500);
        r.eng.on_account(b.vault0, vault(990_000_000_000_000), 11, 1_100, Some(T), 1_600);
        let p = r.eng.state_pending.pop().unwrap();
        r.eng.state_trigger(p.pool, p.txn, p.slot, p.t_recv, p.t_engine);
        assert_eq!((n(&r.eng, "state_opportunity"), r.eng.caps_pending.len()), (1, 1), "queued, not computed between two pools");
        r.eng.flush_state();
        assert!(r.eng.caps_pending.is_empty());
    }
}

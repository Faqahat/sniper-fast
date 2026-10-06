//! The engine: one thread, one loop over every event from every feed.
//!
//!   Tx      first copy of a signature: resolve lookup tables, register the watched accounts it writes (W(T)) with the
//!           CommitTracker, decode venue swaps on watched pools (hints: triggers.jsonl and the accuracy monitor, never
//!           priced). Later copies from other feeds: timestamps (feed scoring), and an executed copy's status.
//!   Account a watched-account update: the store keeps it if it is newer (slot, write_version), the CommitTracker
//!           groups it with its transaction's other writes; when a group resolves, the routes of every Tier-A pool it
//!           wrote are priced on committed, complete, canonical state (PLAN WP-04) and each evaluation is a decision.
//!   Slot    the chain tip, the fork tree (abandoned branches are rolled back), stream health.
//!
//! Nothing here sends: an opportunity goes to the executor (exec.rs) when there is one, which asks the SendGate and the
//! store's health. Every decision is recorded (decisions.jsonl), with its routes, state version and stage times.
//!
//! WP-04 removed the paths that priced what the chain never had: predictions (`preds`, read by `leg` until WP-03: a
//! failed swap's prediction priced the pair's other pools for up to 1.5 s, the cmp2 "poisoned" opportunities), the
//! decoded opportunity and its confirm wait, and the queue-empty flush heuristic (replaced by commit groups).
use crate::accuracy::{self, Hint, Pred};
use crate::alts::{Alts, Answer, Need};
use crate::commit::{CommitTracker, Late, Outcome, Resolution, TrackerCfg, WSrc};
use crate::config::StrategyCfg;
use crate::forks::{Abandoned, SlotTree, Why};
use crate::lat::Series;
use crate::feeds::{clock::now_ns, src as asrc, Arrival, Event, FeedCounters, InputKind, Interest};
use crate::rec::journal::Journal;
use crate::rec::{self, Rec, Record};
use crate::pda::AtaCache;
use crate::pools::{self, pair_key, Registry, CLOCK_SYSVAR, PUMP_FEE_CONFIG};
use crate::reads::{Failed, Fetch, Reads, What};
use crate::quote::{self, Use};
use crate::store::{consistency_set, other_parts, Acct, NotReady, PoolView, ReadyCtx, RouteView, Store};
use crate::store_health::{HealthFlags, LagSlo, Shut, SloAct, StateStream};
use crate::tx::{b58, Pk, Tx};
use crate::venues::{cp, dlmm, PendingSwap, PoolMeta, Venue, WSOL};
use serde::Serialize;
use serde_json::{json, Value};
use rustc_hash::{FxHashMap as HashMap, FxHashSet as HashSet};
use std::collections::{BTreeSet, VecDeque};
use std::io::Write as _;
use std::sync::Arc;
use crossbeam_channel::{Receiver, RecvTimeoutError, Sender, TryRecvError};

/// housekeeping runs at most this often from `timers` (arb-lab ran it on every 5 ms idle wake-up)
const HOUSEKEEPING_NS: u64 = 5_000_000;
/// What one `timers` evaluation may do (journal TIMER `what`, MEASUREMENT §4.13): the commit timers (groups and
/// deferred evaluations whose deadline passed, lookup-table retries: only when the engine's queue is empty, so no update
/// of a group can be waiting in it), housekeeping (expiries, the DLMM drift check, Tier A, the lag SLO minute, the
/// status line) and the accuracy monitor's idle work. WP-03's bit 1 was the state flush, which commit groups replaced
pub const TIMER_COMMIT: u8 = 1;
pub const TIMER_HK: u8 = 2;
pub const TIMER_ACC: u8 = 4;
pub const TIMER_ALL: u8 = TIMER_COMMIT | TIMER_HK | TIMER_ACC;
const STATUS_EVERY_NS: u64 = 10_000_000_000;
const DRIFT_EVERY_NS: u64 = 2_000_000_000;

/// How long a signature's arrival record is kept (later copies from slower feeds still count)
const SIG_KEEP_NS: u64 = 10_000_000_000;
/// a pending trigger with no outcome after this long is a miss (counted only while the state was available, I-5)
const TRIG_KEEP_NS: u64 = 5_000_000_000;
/// how long a hint waits for its transaction's commit
const HINT_KEEP_NS: u64 = 5_000_000_000;
/// how long a decision is remembered for torn_suspect / fork_priced follow-ups
const RECENT_KEEP_NS: u64 = 30_000_000_000;
const RECENT_MAX: usize = 100_000;
/// accuracy scores done per idle timer call (the rest wait for the next)
const ACC_BATCH: usize = 64;
/// scores kept per pool for `window_exact_pct`
const ACC_WINDOW: usize = 200;
const LAMPORTS_PER_SOL: f64 = 1e9;

/// the state stream's re-read (review WP-04 #1) starts this long after the stream's resume slot is known (one slot: the
/// RPC node's processed bank reaches it), its chunks this far apart (the boot snapshot's pace)
const RESYNC_DELAY_NS: u64 = 400_000_000;
const RESYNC_PACE_NS: u64 = 120_000_000;
/// a fork refetch or a new DLMM bin array still unread this long after it was asked for is given up (as a lookup table)
const READ_GIVE_UP_NS: u64 = 600_000_000_000;

/// most feeds one run can follow (arrival times are kept in a fixed array: no allocation per signature)
pub const MAX_FEEDS: usize = 24;
/// how long the engine spins on an empty queue before it blocks (wake-up latency vs. CPU)
const SPIN_NS: u64 = 50_000;

struct SigInfo {
    first_t: u64,
    first_feed: u16,
    /// the earliest arrival from an unexecuted feed (shred, deshred, entries): T's first shred (F33: executed-feed
    /// arrivals come after execution and are left out); 0 when none
    first_unexec_t: u64,
    arr: [u64; MAX_FEEDS],
    trigger: Option<(Pk, Venue, u64)>,
    slot: u64,
}
impl SigInfo {
    fn arrivals(&self) -> impl Iterator<Item = (u16, u64)> + '_ { self.arr.iter().enumerate().filter(|(_, t)| **t != 0).map(|(f, t)| (f as u16, *t)) }
}

/// Stage times (ns), opportunities.jsonl `st` (v1 names): rx = decoded = the receive time of the first update stamped
/// with the trigger transaction, engine = its dequeue, resolved = the evaluation's start, decided = after pricing
#[derive(Clone, serde::Serialize)]
struct Stages { rx: u64, decoded: u64, engine: u64, resolved: u64, decided: u64 }

/// `Engine::lat` series, in order (A.8): the WP-00 state-path series (kept: WP-02's baseline compares against them),
/// a hint's receive-to-done, and the v2 commit stages (WP-04)
const LAT_SERIES: [&str; 9] = ["state_recv_to_engine", "state_engine_to_decided", "state_recv_to_decided", "hint_rx_to_done",
    "first_shred→update_recv", "update_recv→commit", "commit→engine", "engine→priced", "priced→decided"];
const LAT_STATE_RECV_TO_ENGINE: usize = 0;
const LAT_HINT_RX_TO_DONE: usize = 3;
const LAT_V2: usize = 4;

struct Opp {
    id: u64,
    decision: u64,
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
    landed: Option<u64>,
    /// (pool, txn signature, slot, time the update reached us) of every later update to buy/sell pools
    touches: Vec<(Pk, [u8; 64], u64, u64)>,
    /// the state version it was priced on, and the time since its route's last write
    sv: u64,
    route_age_ms: Option<f64>,
    /// WP-05: the evaluation's kind and stage times (attempts `trigger`, `stages`), the pools' consistency-set skews
    kind: &'static str,
    t_first_shred: Option<u64>,
    t_commit: u64,
    t_priced: u64,
    parts_skew: Option<(u64, u64)>,
}

/// Why `Engine::run` returned
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RunEnd { Stopped, Deadline, Disconnected, StateUnavailable }

/// The engine's outside world: RPC (bound to the background runtime), the background runtime it spawns fetches on,
/// the event channel their answers come back on, and the state stream's watch list. `Engine::new_offline` has none
struct Io { rpc: crate::rpc::Rpc, rt: tokio::runtime::Handle, tx_back: Sender<Event>, watch_list: tokio::sync::watch::Sender<Vec<String>>,
    /// FT-000 (S1-1): the batched lookup-table fetcher (role `alt`), started at the first fetch with `[alts]`'s settings
    alt_fetch: std::cell::OnceCell<crate::alts::Fetcher> }

/// what status.jsonl v2's deltas are against (the previous line)
#[derive(Default)]
struct StatusPrev { t: u64, counts: HashMap<&'static str, u64>, updates: u64, stale: u64, dropped: HashMap<String, u64> }

/// PLAN WP-04's settings (`[state]` keys, `[alts]`, `[accuracy]`) as the engine runs them. They are journaled with the
/// engine_init record, so a replay runs with the run's (`apply_init`)
#[derive(Clone, Debug, PartialEq, Serialize, serde::Deserialize)]
pub struct EngineKnobs {
    pub commit_timeout_ms: u64,
    pub quiescence_ms: u64,
    pub max_part_skew_slots: u64,
    pub max_tip_lag_slots: u64,
    pub clock_max_age_slots: u64,
    pub lag_slo_p50_ms: f64,
    pub lag_slo_p90_ms: f64,
    pub lag_slo_breach_minutes: u32,
    pub slo_action: String,
    pub slo_recover_minutes: u32,
    pub tier_a_grace_s: u64,
    pub boot_timeout_s: u64,
    pub max_update_age_ms: u64,
    /// review WP-04 #10: stop (`state_unavailable`) after this long unavailable without a break, s; 0 never
    #[serde(default)]
    pub unavailable_stop_s: u64,
    pub resnapshot: bool,
    /// review WP-04 #1: a WARNING when the re-read after a (re)connection has not landed this long after it (the gate
    /// stays `resync`), s; and a chunk still unread this long after it started is given up (its accounts stay refused,
    /// one by one, until the stream writes them), s
    #[serde(default = "resync_warn_s")]
    pub resync_warn_s: u64,
    #[serde(default = "resync_give_up_s")]
    pub resync_give_up_s: u64,
    pub alts: crate::alts::Policy,
    pub ring_versions: usize,
    pub accuracy_queue: usize,
    /// FT-000 (S1-8): W(T) leaves PumpSwap pools' mints out (`write_set`). A run journaled before it has no such knob
    /// (false): its replay waits for the mints as the run did
    #[serde(default)]
    pub wt_skip_pump_mints: bool,
}
fn resync_warn_s() -> u64 { 10 }
fn resync_give_up_s() -> u64 { 300 }

impl Default for EngineKnobs {
    fn default() -> Self {
        EngineKnobs { commit_timeout_ms: 5, quiescence_ms: 3, max_part_skew_slots: 2, max_tip_lag_slots: 2, clock_max_age_slots: 2, lag_slo_p50_ms: 16.0,
            lag_slo_p90_ms: 30.0, lag_slo_breach_minutes: 5, slo_action: "log".into(), slo_recover_minutes: 10, tier_a_grace_s: 60, boot_timeout_s: 60,
            max_update_age_ms: 2_000, unavailable_stop_s: 0, resnapshot: true, resync_warn_s: resync_warn_s(), resync_give_up_s: resync_give_up_s(), alts: crate::alts::Policy::default(),
            ring_versions: crate::store::RING_VERSIONS, accuracy_queue: 10_000, wt_skip_pump_mints: true }
    }
}

impl EngineKnobs {
    pub fn from_cfg(c: &crate::config::Config) -> EngineKnobs {
        let s = &c.state;
        EngineKnobs { commit_timeout_ms: s.commit_timeout_ms, quiescence_ms: s.quiescence_ms, max_part_skew_slots: s.max_part_skew_slots, max_tip_lag_slots: s.max_tip_lag_slots,
            clock_max_age_slots: s.clock_max_age_slots, lag_slo_p50_ms: s.lag_slo_p50_ms, lag_slo_p90_ms: s.lag_slo_p90_ms, lag_slo_breach_minutes: s.lag_slo_breach_minutes,
            slo_action: s.slo_action.clone(), slo_recover_minutes: s.slo_recover_minutes, tier_a_grace_s: s.tier_a_grace_s, boot_timeout_s: s.boot_timeout_s,
            max_update_age_ms: s.max_update_age_ms, unavailable_stop_s: s.unavailable_stop_s, resnapshot: s.resnapshot, resync_warn_s: s.resync_warn_s,
            resync_give_up_s: s.resync_give_up_s,
            alts: crate::alts::Policy { retry_ms: c.alts.retry_ms.clone(), retry_every_s: c.alts.retry_every_s, give_up_s: c.alts.give_up_s, wait_cap: c.alts.wait_cap,
                max_inflight: c.alts.max_inflight, batch_max: c.alts.batch_max, calls_inflight: c.alts.calls_inflight, call_every_ms: c.alts.call_every_ms,
                max_tables: c.alts.max_tables, max_bytes: (c.alts.max_mb * 1_048_576.0) as u64 },
            ring_versions: c.accuracy.ring_versions, accuracy_queue: c.accuracy.queue, wt_skip_pump_mints: true }
    }
}

/// What one evaluation was triggered by (decisions.jsonl `kind`, `trigger`, `stages`)
#[derive(Clone, Debug)]
struct EvalCtx {
    /// `commit` (complete / superseded), `quiescent` (timeout_quiescent), `timeout` (timeout_unknown), `fork` (a rollback)
    kind: &'static str,
    txn: Option<[u8; 64]>,
    slot: u64,
    t_first_shred: Option<u64>,
    /// the receive time of the group's first update, and its engine dequeue
    t_update_recv: u64,
    t_first_engine: u64,
    /// the commit on the receive-time clock, and the engine time of the resolution
    t_commit: u64,
    t_resolved: u64,
    /// route-level quiet required (a group resolved by a timeout), judged at `now_clock`
    quiet: bool,
    now_clock: u64,
    w_src: &'static str,
    group: Option<u64>,
    /// how many times this evaluation was put off for `route_not_quiet` (at most `MAX_DEFERRALS`)
    deferrals: u8,
}

/// an evaluation put off for route-level quiet is re-run at most this many times (a pool written without a pause is
/// evaluated by its own groups anyway)
const MAX_DEFERRALS: u8 = 3;

/// A decision remembered for its follow-ups: the pools it priced, the slots of the versions it read, and (slot, txn8) of
/// those a transaction wrote (slot-index `missing` evidence, review WP-04 #7)
struct RecentDec { id: u64, t: u64, pools: Vec<usize>, slots: Vec<u64>, txns: Vec<(u64, u64)> }

/// The state stream's re-read after a (re)connection (PLAN-ADDENDUM I-4; review WP-04 #1). The gate stays `resync` until
/// every chunk has landed or was given up. The read starts once the stream's resume slot is known (its first account
/// update or processed slot after the connection): a chunk read at an older slot is read again (the RPC node is behind
/// the point the stream resumed at, and the writes in between would be missed)
struct Resync {
    why: &'static str,
    t_connect: u64,
    /// the chunks to read (each pool's accounts together), until the job starts
    chunks: Vec<Vec<Pk>>,
    n_keys: usize,
    job: Option<u64>,
    floor: Option<u64>,
    warned: bool,
    /// chunk answers read behind the resume slot, failed, and accounts the node did not have
    behind: u64,
    failed: u64,
    missing: u64,
}

/// one priced route (WP-06: the size search stopped at the DLMM window, `dlmm_cap_bound`)
#[derive(Clone, Debug)]
struct Priced { size: u64, gross: i64, net: i64, cu: u64, crossed: (u32, u32), dlmm_cap_bound: bool }

/// WP-06: what the engine prices a route's fee and CU with (PLAN WP-06 items 4, 5, 8): the tip policy by band (the fee
/// estimate is the base fee plus the tip of the gross's edge: a bundle pays CU price 0; and the band table) and the CU
/// model (the measured table, its sample floor, the fallback formula). Journaled with the engine_init record
/// (`builder`), so a replay prices as the run did without reading the table file. A journal without it (written before
/// WP-06) replays with the old rule: base fee + `cu_price_micro` × CU + `min_tip`, today's CU formula
#[derive(Clone, Debug, PartialEq, Serialize, serde::Deserialize)]
pub struct BuilderModel { pub tips: crate::tip::TipModel, pub cu: crate::cu_table::CuModel }

impl BuilderModel {
    /// from `[tips]`, `[bands]` and `[builder] cu_table` / `cu_min_samples` (the table read here, once)
    pub fn from_cfg(c: &crate::config::Config) -> Result<BuilderModel, String> {
        Ok(BuilderModel { tips: crate::tip::TipModel::from_cfg(c)?, cu: crate::cu_table::CuModel::from_cfg(&c.builder)? })
    }
}

/// one route of an evaluation
struct RouteRes { buy: usize, sell: usize, priced: Option<Priced>, reason: &'static str, sv: Option<RouteView>, slots: Vec<u64>, txns: Vec<(u64, u64)> }

pub struct Engine {
    pub reg: Arc<Registry>,
    pub store: Store,
    cfg: StrategyCfg,
    knobs: EngineKnobs,
    feeds: Vec<String>,
    /// tip of the cheapest enabled send path (lamports); shadow nets are computed with it
    min_tip: u64,
    interest: Arc<Interest>,
    ata: AtaCache,
    sigs: HashMap<u64, SigInfo>,
    sig_order: VecDeque<(u64, u64)>,
    /// lookup tables, their fetches and retries, and the transactions waiting for them (WP-04 item 7, I-6)
    alts: Alts<(Arrival, u64)>,
    /// pool and vault accounts -> their pool (moves.log, the opportunities' touches)
    acct_pool: HashMap<Pk, usize>,
    /// every account a pool is priced from (consistency set, other parts, followed DLMM bin arrays) -> its pools: the
    /// accounts commit groups are kept for, and which pools a pending group holds
    part_pools: HashMap<Pk, Vec<usize>>,
    /// the accounts whose write makes a pool's state move (its consistency set, its own account, its DLMM bin arrays) ->
    /// the pool: a resolved group evaluates these pools. Shared parts (the PumpSwap fee config, a CPMM config, a mint)
    /// are left out: a write to one would re-price hundreds of pools at once
    eval_pools: HashMap<Pk, Vec<usize>>,
    /// Tier A (PLAN WP-04 item 8): every registry pool in Stage 0, minus the ones dropped for missing parts
    tier_a: BTreeSet<usize>,
    tier_a_complete: bool,
    watch: HashMap<usize, Vec<u64>>,
    opps: HashMap<u64, Opp>,
    next_id: u64,
    next_decision: u64,
    /// the newest processed slot of the state stream, and of the unexecuted feeds (the tip while the state is down, I-4)
    slot: u64,
    shred_slot: u64,
    lat: Vec<Series>,
    counts: HashMap<&'static str, u64>,
    /// every stream the engine writes, handed to the recorder, never written on this thread (WP-02)
    rec: Rec,
    /// status.jsonl lines written so far (`seq` of the next one; stop.json `final_status_seq` = this - 1)
    pub status_lines: u64,
    /// the run's SendGate, shown in every status line as `send_gate` (review M2: a segment that does not send says why)
    pub gate: Option<Arc<crate::control::SendGate>>,
    io: Option<Io>,
    /// `new_offline`: the fetches the engine asked for (what, accounts), recorded instead of sent; account reads also in
    /// full (job, chunk, attempt) in `offline_reads`, which a test answers through INPUT 11 `fetch`
    pub offline_fetches: Vec<(&'static str, Vec<Pk>)>,
    pub offline_reads: Vec<Fetch>,
    /// newest slot by status (processed, confirmed, finalized) and the newest slot of a stored pool-account update
    slots: [u64; 3],
    store_slot_max: u64,
    queue_hwm: usize,
    t_start: u64,
    sp: StatusPrev,
    exec_prev: crate::exec::ExecPrev,
    /// the input journal (journal.bin, WP-03): every input at its dequeue point, every timer evaluation
    journal: Journal,
    /// the clock value of the input (or timer evaluation) being handled: every decision made while handling it reads this
    t_now: u64,
    last_hk_t: u64,
    last_status_t: u64,
    last_drift_t: u64,
    anchored: bool,
    /// the first journaled time (the boot timeout counts from it)
    t_anchor: u64,
    init_journaled: bool,
    gate_journaled: Option<crate::control::GateMode>,
    /// ---- WP-09 (review WP-09 #3): the SendGate as decisions without an executor read it (`gate_no_executor`)
    pub gate_seen: GateSeen,
    queue_now: usize,
    /// a running hash of every decision made: replay compares it
    decisions: u64,
    pub last_block_meta: Option<(u64, [u8; 32], Option<u64>)>,
    acct_rec: Option<Arc<crate::rec::accounts::AcctRec>>,
    base_watch: Option<Vec<Pk>>,
    feed_counters: Vec<Arc<FeedCounters>>,
    state_counters: Option<Arc<FeedCounters>>,
    leads: Vec<Series>,
    fh: rec::health::FeedHealth,
    pub exec: Option<crate::exec::Exec>,
    /// WP-07: the run's ledger (src/ledger.rs: entries, balance snapshots, reconciliation) and its supervisor's equity
    /// stops; fed by INPUT 7 `wallet_tx` and INPUT 13 `snapshot`, its timers at most once a second (`ledger_tick`)
    pub ledger: Option<crate::ledger::Ledger>,
    last_ledger_tick: u64,
    /// per trigger signer: (triggers that moved the pool or landed, triggers that failed or never showed). Loaded once
    /// (its sha256 recorded), never written back to the shared file (I-5): `signer_delta` is this segment's part, and
    /// `signer_stats` = `signer_base` (as loaded, shared with the recorder's writer) + `signer_delta`
    signer_stats: HashMap<Pk, (u32, u32)>,
    signer_base: Arc<HashMap<Pk, (u32, u32)>>,
    signer_delta: HashMap<Pk, (u32, u32)>,
    signer_stats_sha256: Option<String>,
    /// where this segment writes its copy (`<run dir>`; None: nowhere)
    signer_stats_out: Option<std::path::PathBuf>,
    /// triggers waiting for their outcome (by signature): signer, seen at
    trig_pending: HashMap<[u8; 64], (Pk, u64)>,
    caps_pending: Vec<(u64, Best, i64)>,
    amm: HashMap<Pk, &'static str>,
    tip_names: HashMap<Pk, String>,
    arbers: HashSet<Pk>,
    moves_seen: HashSet<(u64, u32)>,
    poh: HashMap<[u8; 64], crate::feeds::entries::Poh>,
    poh_order: VecDeque<(u64, [u8; 64])>,
    // ------------------------------------------------------------ WP-04
    tracker: CommitTracker,
    forks: SlotTree,
    state: StateStream,
    flags: Arc<HealthFlags>,
    shut: Shut,
    slo: LagSlo,
    /// evaluations refused `route_not_quiet`, re-run once their routes are quiet: (due on the receive clock, pool, ctx)
    deferred: Vec<(u64, usize, EvalCtx)>,
    recent: VecDeque<RecentDec>,
    /// hints waiting for their transaction's commit (accuracy), and the scores waiting for idle time
    hints: HashMap<[u8; 64], Vec<Hint>>,
    hint_order: VecDeque<(u64, [u8; 64])>,
    acc_queue: VecDeque<Hint>,
    acc_windows: HashMap<usize, accuracy::Window>,
    acc_by_venue: std::collections::BTreeMap<String, (u64, u64)>,
    /// the commit lag (first shred of T to its complete commit), overall and by w_src
    commit_lag: Series,
    commit_lag_src: [Series; 3],
    /// a stop the engine asks for (PLAN-ADDENDUM I-4: the state stream never delivered)
    pub stop_req: Option<String>,
    boot_warned: bool,
    /// RPC account reads (the re-read, fork refetches, new DLMM bin arrays): chunks, retries (review WP-04 #1, #7)
    reads: Reads,
    resync: Option<Resync>,
    /// accounts not read again since the state stream's last (re)connection: a pool with one is refused (`resync`)
    unverified: HashSet<Pk>,
    /// receive time of the newest state-stream account update (status `last_account_age_ms_now`; review WP-04 #9)
    last_account_t: u64,
    // ------------------------------------------------------------ WP-05
    /// what the send checks read of the chain, from journaled inputs only: the blockhash ring's head, block metas, the
    /// leader schedule
    pub sendview: crate::exec::SendView,
    /// crowding (F6): distinct arbitrage-like signers that landed on each pool over the window
    activity: crate::crowding::Activity,
    /// what the last journaled decision-point record said (gate mode, leader kind, token valid, recorder healthy)
    /// (WP-09: and the gate's reason)
    seen_journaled: Option<(crate::control::GateMode, String, crate::leaders::LeaderKind, bool, bool, crate::ledger::MoneyView)>,
    /// ---- WP-09: the exec_init record was journaled (`journal_exec_init`)
    exec_init_journaled: bool,
    // ------------------------------------------------------------ WP-06
    /// the fee and CU model (`BuilderModel`; None: a pre-WP-06 journal's rule)
    builder: Option<BuilderModel>,
    /// the lookup tables of the cache that name each registry pool (the size budget's index, PLAN WP-06 item 7), and the
    /// pools each table is indexed under (an evicted table leaves the index: `unindex_alts`)
    alt_by_pool: HashMap<Pk, Vec<Pk>>,
    alt_pools: HashMap<Pk, Vec<Pk>>,
    /// every account the state stream follows (`set_base_watch`): whether the store's view of the wallet's token accounts
    /// and of its PumpSwap user volume accumulator can be trusted (WP-06 item 2)
    watch_set: HashSet<Pk>,
    /// the executor's wallet's PumpSwap user volume accumulator (derived once)
    uva_key: std::cell::OnceCell<Pk>,
}

/// {signer: [ok, failed]} as a file holds it; with the sha256 of the bytes read. Missing or unreadable: empty, no hash
fn load_signer_stats(path: &str) -> (HashMap<Pk, (u32, u32)>, Option<String>) {
    let Ok(bytes) = std::fs::read(path) else { return (HashMap::default(), None) };
    let h = crate::provenance::sha256_hex(&bytes);
    let Ok(Value::Object(m)) = serde_json::from_slice::<Value>(&bytes) else { return (HashMap::default(), Some(h)) };
    (parse_signer_stats(&m), Some(h))
}

fn parse_signer_stats(m: &serde_json::Map<String, Value>) -> HashMap<Pk, (u32, u32)> {
    m.iter().filter_map(|(k, v)| {
        let key: Pk = bs58::decode(k).into_vec().ok()?.try_into().ok()?;
        Some((key, (v[0].as_u64()? as u32, v[1].as_u64()? as u32)))
    }).collect()
}

fn signer_stats_json(m: &HashMap<Pk, (u32, u32)>) -> Value {
    let mut v: Vec<(&Pk, &(u32, u32))> = m.iter().collect();
    v.sort();
    Value::Object(v.into_iter().map(|(k, x)| (b58(k), json!([x.0, x.1]))).collect())
}

/// `arbx signer-stats merge` (PLAN-ADDENDUM I-5): fold each run directory's `signer-stats-delta.json` (that segment's own
/// counts) into `into`, written atomically. A run already merged (its `signer-stats.merged.json`) is refused, and so is
/// one that has not ended (no `stop.json`: its delta is still growing; review WP-04 N7). Returns, per run, the signers
/// and counts added
pub fn merge_signer_stats(into: &std::path::Path, runs: &[std::path::PathBuf]) -> anyhow::Result<Vec<(String, usize, u64)>> {
    use anyhow::Context;
    let mut base = match std::fs::read(into) {
        Ok(b) => match serde_json::from_slice::<Value>(&b).context("the target is not JSON")? { Value::Object(m) => parse_signer_stats(&m), _ => anyhow::bail!("the target is not an object") },
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => HashMap::default(),
        Err(e) => return Err(e).with_context(|| format!("reading {}", into.display())),
    };
    let before = crate::provenance::sha256_hex(&std::fs::read(into).unwrap_or_default());
    let mut out = Vec::new();
    let mut deltas = Vec::new();
    for r in runs {
        anyhow::ensure!(!r.join("signer-stats.merged.json").exists(), "{} was merged already (signer-stats.merged.json)", r.display());
        anyhow::ensure!(r.join("stop.json").exists(), "{} has no stop.json: the segment has not ended (its delta would be partial)", r.display());
        let p = r.join("signer-stats-delta.json");
        let v: Value = serde_json::from_slice(&std::fs::read(&p).with_context(|| format!("reading {}", p.display()))?)?;
        let Value::Object(m) = v else { anyhow::bail!("{} is not an object", p.display()) };
        deltas.push((r.clone(), parse_signer_stats(&m)));
    }
    for (r, d) in &deltas {
        let mut n = 0u64;
        for (k, (ok, miss)) in d {
            let e = base.entry(*k).or_default();
            e.0 = e.0.saturating_add(*ok);
            e.1 = e.1.saturating_add(*miss);
            n += (*ok + *miss) as u64;
        }
        out.push((r.display().to_string(), d.len(), n));
    }
    let text = signer_stats_json(&base).to_string();
    let tmp = into.with_extension("merge.tmp");
    std::fs::write(&tmp, &text)?;
    std::fs::rename(&tmp, into)?;
    let after = crate::provenance::sha256_hex(text.as_bytes());
    for (r, d) in &deltas {
        let mark = json!({ "into": into.display().to_string(), "t_ns": now_ns(), "sha256_before": before, "sha256_after": after, "signers": d.len() });
        std::fs::write(r.join("signer-stats.merged.json"), mark.to_string())?;
    }
    Ok(out)
}

/// What a run's engine starts with that no journaled input carries (review WP-03 #2b, #2c): the tip its nets are
/// computed with, its strategy config, whether it has an executor, the signer statistics as loaded (their file's sha256,
/// I-5), and WP-04's knobs. Journaled once as INPUT 10 `engine_init` with `t_engine_ns` 0; a replay starts from it
#[derive(Clone, Debug, Default, PartialEq)]
pub struct EngineInit {
    pub min_tip: u64,
    /// sha256 of the `[strategy]` section as the engine runs it (JSON; `signer_stats_file` left out: a replay never reads it)
    pub strategy_sha256: String,
    pub executor: bool,
    pub signer_stats_file: String,
    pub signer_stats_sha256: Option<String>,
    pub signer_stats: HashMap<Pk, (u32, u32)>,
    /// None in a WP-03 journal (the defaults then)
    pub knobs: Option<EngineKnobs>,
    /// WP-06: the fee and CU model (None in a journal written before WP-06: the old rule)
    pub builder: Option<BuilderModel>,
}

impl EngineInit {
    pub fn json(&self) -> Value {
        json!({ "min_tip": self.min_tip, "strategy_sha256": self.strategy_sha256, "executor": self.executor,
            "signer_stats_file": self.signer_stats_file, "signer_stats_sha256": self.signer_stats_sha256, "signer_stats": signer_stats_json(&self.signer_stats),
            "knobs": self.knobs, "builder": self.builder })
    }

    pub fn from_json(v: &Value) -> Option<EngineInit> {
        let stats = parse_signer_stats(v["signer_stats"].as_object()?);
        Some(EngineInit { min_tip: v["min_tip"].as_u64()?, strategy_sha256: v["strategy_sha256"].as_str()?.to_string(), executor: v["executor"].as_bool()?,
            signer_stats_file: v["signer_stats_file"].as_str().unwrap_or("").to_string(), signer_stats_sha256: v["signer_stats_sha256"].as_str().map(String::from),
            signer_stats: stats, knobs: serde_json::from_value(v["knobs"].clone()).ok(),
            // review WP-06 #10: absent or null is a journal written before WP-06 (its replay prices with its own rule); a
            // model present but unreadable (a later schema, a corrupt record) makes the record unreadable: never the legacy
            // rule in its place
            builder: match &v["builder"] { Value::Null => None, b => Some(serde_json::from_value(b.clone()).ok()?) } })
    }
}

/// sha256 of a `[strategy]` section as an engine runs it (`signer_stats_file` left out: where the statistics came from
/// is not how decisions are made, and an offline engine never reads the file)
pub fn strategy_sha256(cfg: &StrategyCfg) -> String {
    let mut c = cfg.clone();
    c.signer_stats_file.clear();
    crate::provenance::sha256_hex(&serde_json::to_vec(&c).unwrap_or_default())
}

/// swap venues by program (wider than the four we trade, to recognise arbitrage elsewhere) and the Jupiter aggregator
pub fn amm_programs() -> HashMap<Pk, &'static str> {
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
/// the real clock in unix seconds: only for offline tools (`simcheck`'s routes), never for a run's decisions
fn unix_now() -> i64 { (now_ns() / 1_000_000_000) as i64 }
/// xxh3 of a decision's fields, folded into `Engine::decisions`
fn fold(h: u64, parts: &[&[u8]]) -> u64 {
    let mut x = xxhash_rust::xxh3::Xxh3::new();
    x.update(&h.to_le_bytes());
    for p in parts { x.update(p); }
    x.digest()
}
fn sigs58(s: &[u8; 64]) -> String { bs58::encode(s).into_string() }
/// How a route's legs are parsed (PLAN-ADDENDUM WP-16): as the builder sends them, with each DLMM leg's walk budget
/// from the transaction's CU limit (`quote::DLMM_BUDGET_*`: two DLMM legs share it)
fn route_use(pb: &PoolMeta, ps: &PoolMeta) -> Use {
    let both = pb.venue == Venue::Dlmm && ps.venue == Venue::Dlmm;
    Use::Route { dlmm_budget: if both { quote::DLMM_BUDGET_SHARED } else { quote::DLMM_BUDGET_ALONE } }
}

/// base58 at serialization time (on the recorder's writer, not the engine thread)
#[derive(Clone, Copy)]
struct B58(Pk);
impl Serialize for B58 { fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> { s.serialize_str(&b58(&self.0)) } }
#[derive(Clone, Copy)]
struct Sig58([u8; 64]);
impl Serialize for Sig58 { fn serialize<S: serde::Serializer>(&self, s: S) -> Result<S::Ok, S::Error> { s.serialize_str(&sigs58(&self.0)) } }
/// a state version as 16 hex characters (MEASUREMENT §2.1 `sv.h`)
fn hex16(h: u64) -> String { format!("{h:016x}") }

#[derive(Serialize)]
struct MemberRec { acct: B58, slot: u64, wv: u64, aseq: u64, t: u64 }
impl MemberRec { fn of(m: &crate::commit::Member) -> MemberRec { MemberRec { acct: B58(m.acct), slot: m.slot, wv: m.wv, aseq: m.aseq, t: m.t } } }

/// commits.jsonl (MEASUREMENT §4.31): one line per commit group at its resolution
#[derive(Serialize)]
struct CommitRec {
    group: u64, txn: Sig58, slot: u64, w_src: &'static str, w_late: bool, w_expected: Option<Vec<B58>>, w_seen: Vec<MemberRec>, superseded: Vec<B58>,
    t_first_shred: Option<u64>, t_first_update: u64, t_resolved: u64, t_commit: u64, spread_ms: f64, outcome: &'static str, resolved_by: &'static str,
    lag_ms: Option<f64>, late_members: Vec<MemberRec>, torn_suspect_decisions: Vec<u64>, pools: Vec<B58>, evaluated: u32, reopened_from: Option<u64>,
}

/// commits.jsonl's second line for a group a late member arrived for (F2)
#[derive(Serialize)]
struct LateRec { group: u64, txn: Sig58, late: bool, t: u64, late_members: Vec<MemberRec>, torn_suspect_decisions: Vec<u64>, reopened_group: u64 }

#[derive(Serialize)]
struct RouteRec { buy: B58, sell: B58, mint: B58, buy_venue: Venue, sell_venue: Venue, size: Option<u64>, gross: Option<i64>, net: Option<i64>, cu: Option<u64>,
    crossed: Option<[u32; 2]>, reason: &'static str,
    /// WP-06 (decisions 1.2): the size search stopped where the DLMM bin arrays the builder names end (null: not priced;
    /// absent under a pre-WP-06 journal's pricing)
    #[serde(skip_serializing_if = "Option::is_none")]
    dlmm_cap_bound: Option<Option<bool>> }

#[derive(Serialize)]
struct TriggerRef { txn: Option<Sig58>, slot: u64, t_first_shred: Option<u64>, pool: B58, group: Option<u64> }

#[derive(Serialize)]
struct SvRec { h: String, slot_max: u64, wv_max: u64 }

#[derive(Serialize)]
struct SkewRec { buy: u64, sell: u64 }

#[derive(Serialize)]
struct StagesRec { t_first_shred: Option<u64>, t_update_recv: u64, t_commit: u64, t_engine: u64, t_priced: u64, t_decided: u64 }

/// decisions.jsonl (MEASUREMENT §4.32): one line per evaluation of a pool, with every route evaluated
#[derive(Serialize)]
struct DecisionRec {
    decision: u64, t_ns: u64, kind: &'static str, trigger: TriggerRef, routes: Vec<RouteRec>, best: Option<usize>, sv: Option<SvRec>, route_age_ms: Option<f64>,
    parts_skew_slots: Option<SkewRec>, w_src: &'static str, torn_suspect: bool, fork_priced: bool,
    /// the executor's band when it reached the route checks (at the size it would trade: the queue's and the tip's),
    /// else the engine's; `band_at_opp` is always the engine's, at its priced size (review WP-05 #9)
    band: Option<u8>, band_at_opp: Option<u8>, crowding: Option<crate::exec::Crowding>,
    verdict: &'static str, reason: String, ev: Option<i64>, rank: Option<u8>, attempt: Option<u64>, opp: Option<u64>, experiments: serde_json::Map<String, Value>,
    stages: StagesRec,
    /// WP-05 (decisions 1.1): the attempt was sent (true), is a would-send recorded with `sent = false` (PLAN-ADDENDUM I-7),
    /// or none was made (null); with the gate closed, what would have refused it otherwise (null: a would-send)
    sent: Option<bool>, would_send: bool, reason_ungated: Option<String>,
}

/// the shared band table (src/bands.rs; MEASUREMENT §4.32 `band`; `[bands]`, WP-06): over the expected edge = gross −
/// base fee
fn band_of(b: &Option<BuilderModel>, gross: i64) -> u8 { b.as_ref().map_or_else(|| crate::bands::of_gross(gross), |m| m.tips.bands.of_gross(gross)) }

/// journal INPUT 9 `settled`: an executor task's result in full (WP-05: a fire result, a statuses answer, a dry run's
/// simulation)
fn settled_json(st: &crate::exec::Settled) -> Value { st.json() }

/// a transaction's PoH position: the engine's map (entries feeds' arrivals), else, in a run (`global`), the process's PoH
/// index (shred feeds' walks: WP-08). The index is not journaled, so it only ever reaches a gauge and outcome lines, never
/// a verdict, and an offline engine (a replay) never reads it (WP-09 review item 5)
fn poh_of(poh: &HashMap<[u8; 64], crate::feeds::entries::Poh>, s: &[u8; 64], global: bool) -> Option<crate::feeds::entries::Poh> {
    poh.get(s).copied().or_else(|| if global { crate::feeds::poh_index().get_sig(s).map(|x| x.0) } else { None })
}

/// What `run` evaluates after an input: the commit timers only when the queue is empty and a deadline is due (an update
/// of a group still in the queue must be handled first; stream evidence covers a backlog), housekeeping every 10 s
/// while the queue never empties (with the commit timers if it is empty then)
fn after_input_timers(queue_empty: bool, since_status_ns: u64, due: bool) -> u8 {
    let hk = since_status_ns > STATUS_EVERY_NS;
    let commit = queue_empty && (due || hk);
    (if commit { TIMER_COMMIT } else { 0 }) | (if hk { TIMER_HK } else { 0 })
}

impl Engine {
    /// The run's engine. `rec`: the recorder; `rpc` must be bound to the background runtime `rt_bg`, where the engine's
    /// fetches (lookup tables, DLMM bin arrays, re-snapshots) are spawned; their answers come back on `tx_back`
    #[allow(clippy::too_many_arguments)]
    pub fn new(reg: Arc<Registry>, store: Store, cfg: StrategyCfg, feeds: Vec<String>, min_tip: u64, interest: Arc<Interest>,
        rec: Rec, rpc: crate::rpc::Rpc, rt_bg: tokio::runtime::Handle, tx_back: Sender<Event>,
        watch_list: tokio::sync::watch::Sender<Vec<String>>) -> anyhow::Result<Engine> {
        let mut e = Engine::build(reg, store, cfg, feeds, min_tip, interest, rec);
        e.io = Some(Io { rpc, rt: rt_bg, tx_back, watch_list, alt_fetch: Default::default() });
        Ok(e)
    }

    /// accounts.bin for the engine's own RPC reads (and the roles of the DLMM bin arrays it starts following)
    pub fn set_acct_rec(&mut self, a: Arc<crate::rec::accounts::AcctRec>) { self.acct_rec = Some(a); }

    /// the state stream's fixed accounts (registry plus the extra watched accounts); the DLMM bin arrays are added to it
    /// whenever the watch list is published
    pub fn set_base_watch(&mut self, keys: Vec<Pk>) { self.watch_set = keys.iter().copied().collect(); self.base_watch = Some(keys); }

    /// WP-06: the fee and CU model (`BuilderModel::from_cfg`); before the engine_init record is journaled (`journal_init`)
    pub fn set_builder(&mut self, b: BuilderModel) { self.builder = Some(b); }
    pub fn builder(&self) -> Option<&BuilderModel> { self.builder.as_ref() }

    /// An engine with no RPC, runtime or watch channel (PLAN WP-02 item 11): fetches are recorded in `offline_fetches`
    /// instead of sent, and it records nothing until `set_rec`. For benchmarks and replay (WP-09). It never reads or
    /// writes the cross-run signer statistics file: a replay takes the run's statistics from engine_init
    pub fn new_offline(reg: Arc<Registry>, store: Store, mut cfg: StrategyCfg) -> Engine {
        cfg.signer_stats_file.clear();
        Engine::build(reg, store, cfg, vec![], 0, Arc::new(Interest::default()), Rec::off())
    }

    /// PLAN WP-04's settings (`EngineKnobs::from_cfg`); before the first input
    pub fn set_knobs(&mut self, k: EngineKnobs) {
        self.tracker = CommitTracker::new(TrackerCfg::new(k.commit_timeout_ms, k.quiescence_ms));
        self.slo = LagSlo::new(k.lag_slo_p50_ms, k.lag_slo_p90_ms, k.lag_slo_breach_minutes, k.slo_recover_minutes, &k.slo_action);
        self.alts.policy = k.alts.clone();
        self.store.ring_versions = k.ring_versions.max(2);
        self.knobs = k;
    }
    pub fn knobs(&self) -> &EngineKnobs { &self.knobs }

    /// what the executor reads before it sends (`Exec::decide`'s send checks)
    pub fn health_flags(&self) -> Arc<HealthFlags> { self.flags.clone() }

    /// WP-05: the crowding map's window, buckets and WP-00's static list (`[send_policy]`)
    pub fn set_crowding(&mut self, a: crate::crowding::Activity) { self.activity = a; }

    /// I-5: this segment's signer statistics go to `<dir>/signer-stats.json` (the whole map: usable as a next run's
    /// input) and `<dir>/signer-stats-delta.json` (this segment's counts: what `arbx signer-stats merge` folds back)
    pub fn set_signer_stats_out(&mut self, dir: &std::path::Path) { self.signer_stats_out = Some(dir.to_path_buf()); }
    /// the sha256 of the statistics file as it was read (None: not read)
    pub fn signer_stats_sha256(&self) -> Option<&str> { self.signer_stats_sha256.as_deref() }

    /// What this engine starts with that no input carries (the engine_init record)
    pub fn init(&self) -> EngineInit {
        EngineInit { min_tip: self.min_tip, strategy_sha256: strategy_sha256(&self.cfg), executor: self.exec.is_some(),
            signer_stats_file: self.cfg.signer_stats_file.clone(), signer_stats_sha256: self.signer_stats_sha256.clone(), signer_stats: self.signer_stats.clone(),
            knobs: Some(self.knobs.clone()), builder: self.builder.clone() }
    }

    /// Journal the engine_init record (INPUT 10, `t_engine_ns` 0) once, before the first input: `run` calls it first
    pub fn journal_init(&mut self) {
        if self.init_journaled || !self.journal.is_on() { return; }
        self.init_journaled = true;
        self.journal.input_sized(0, InputKind::EngineInit, Arc::new(self.init().json()), 512 + 64 * self.signer_stats.len() as u64);
    }

    /// ---- WP-09 (review WP-09 "For the WP-05 merge" item 2). What this engine's executor starts with that the frozen
    /// config does not hold (`exec::ExecInit`), with the crowding map's window, buckets and static list. None without an
    /// executor
    pub fn exec_init(&self) -> Option<crate::exec::ExecInit> {
        let mut i = self.exec.as_ref()?.init();
        (i.crowding_window_h, i.crowding_buckets, i.crowded) = self.activity.params();
        Some(i)
    }

    /// ---- WP-09. Journal the exec_init record (INPUT 12, `t_engine_ns` 0, with the boot records, after engine_init) once,
    /// before the first input: `run` calls it after `journal_init`. Nothing without an executor
    pub fn journal_exec_init(&mut self) {
        if self.exec_init_journaled || !self.journal.is_on() { return; }
        let Some(i) = self.exec_init() else { return };
        self.exec_init_journaled = true;
        let keys = i.alts.iter().map(|a| a.1.len()).sum::<usize>() + i.held.len() + i.crowded.len();
        self.journal.input_sized(0, InputKind::ExecInit, Arc::new(i.json()), 1_024 + 48 * keys as u64);
    }

    /// Start from a run's engine_init record (replay): its `min_tip`, signer statistics and knobs. An error when the
    /// replay's `[strategy]` is not the run's
    pub fn apply_init(&mut self, init: &EngineInit) -> anyhow::Result<()> {
        let mine = strategy_sha256(&self.cfg);
        if init.strategy_sha256 != mine { anyhow::bail!("the replay's [strategy] (sha256 {}) is not the run's ({})", &mine[..16], &init.strategy_sha256[..16.min(init.strategy_sha256.len())]); }
        self.min_tip = init.min_tip;
        self.signer_stats = init.signer_stats.clone();
        self.signer_base = Arc::new(init.signer_stats.clone());
        self.signer_delta.clear();
        self.signer_stats_sha256 = init.signer_stats_sha256.clone();
        if let Some(k) = &init.knobs { self.set_knobs(k.clone()); }
        // WP-06: the run's fee and CU model (none in a journal written before WP-06: the old rule)
        self.builder = init.builder.clone();
        self.init_journaled = true;
        Ok(())
    }

    /// A lookup table from a previous segment's alts-final (I-6), with when a transaction last used it there. `journal`:
    /// also into the journal's boot records (the run; a replay applies them from there)
    pub fn preload_alt(&mut self, table: Pk, addrs: Vec<Option<Pk>>, last_used: Option<u64>, journal: bool) {
        if journal { self.journal.alt_preload(table, &addrs); }
        self.alts.preload(table, addrs, last_used);
        self.index_alt(table);
        self.count("alt_preloaded");
        self.journal_evictions(0);
    }

    /// FT-000 (S1-4): the lookup tables the cache evicted while an input (or the boot's preload) was handled, as one ALT
    /// `found` 4 journal record after it, with the running count and hash a replay checks (`journal::replay`)
    fn journal_evictions(&mut self, t: u64) {
        let ev = self.alts.take_evicted();
        if ev.is_empty() { return; }
        self.count_n("alt_evicted", ev.len() as u64);
        self.journal.alt_evict(t, &ev, self.alts.evicted_total, self.alts.evict_hash);
        // WP-06's index of the cache (the size budget's candidates) drops what the cache evicted
        self.unindex_alts(&ev);
    }

    /// FT-000: what the lookup-table cache has evicted so far (count, running hash): what a replay compares with the
    /// journal's ALT `found` 4 records
    pub fn alt_evictions(&self) -> (u64, u64) { (self.alts.evicted_total, self.alts.evict_hash) }

    /// record (and journal) through `rec` from now on
    pub fn set_rec(&mut self, rec: Rec) { self.journal = Journal::new(rec.clone()); self.rec = rec; }

    /// the engine's own journal handle (`arbx run` journals the boot snapshot through it before the engine starts)
    pub fn journal(&self) -> &Journal { &self.journal }

    /// a latency series by name (A.8; benchmarks and tests)
    pub fn series_mut(&mut self, name: &str) -> Option<&mut Series> { self.lat.iter_mut().find(|s| s.name == name) }

    /// a counter (status `counts_total`)
    pub fn counter(&self, k: &str) -> u64 { self.counts.get(k).copied().unwrap_or(0) }

    /// feedhealth.jsonl: the feeds' counters (index = feed id) and the state stream's
    pub fn set_feed_counters(&mut self, feeds: Vec<Arc<FeedCounters>>, state: Option<Arc<FeedCounters>>) {
        self.leads = feeds.iter().map(|_| Series::new("lead")).collect();
        self.feed_counters = feeds;
        self.state_counters = state;
    }

    fn build(reg: Arc<Registry>, mut store: Store, cfg: StrategyCfg, feeds: Vec<String>, min_tip: u64, interest: Arc<Interest>, rec: Rec) -> Engine {
        let mut acct_pool = HashMap::default();
        let mut part_pools: HashMap<Pk, Vec<usize>> = HashMap::default();
        let mut eval_pools: HashMap<Pk, Vec<usize>> = HashMap::default();
        let mut tier_a = BTreeSet::new();
        for &i in reg.pairs.values().flatten() {
            let m = &reg.pools[i];
            acct_pool.insert(m.pool, i);
            if !matches!(m.venue, Venue::Dlmm | Venue::DammV2) { acct_pool.insert(m.vault0, i); acct_pool.insert(m.vault1, i); }
            for k in consistency_set(m).into_iter().chain(other_parts(m)) {
                let v = part_pools.entry(k).or_default();
                if !v.contains(&i) { v.push(i); }
            }
            for k in consistency_set(m).into_iter().chain([m.pool]) {
                let v = eval_pools.entry(k).or_default();
                if !v.contains(&i) { v.push(i); }
            }
            tier_a.insert(i);
        }
        for (p, l) in &store.dlmm_arrays {
            if let Some(&i) = reg.by_pool.get(p) {
                for (_, k) in l {
                    for map in [&mut part_pools, &mut eval_pools] { let v = map.entry(*k).or_default(); if !v.contains(&i) { v.push(i); } }
                }
            }
        }
        let (signer_stats, signer_stats_sha256) = if cfg.signer_stats_file.is_empty() { (HashMap::default(), None) } else { load_signer_stats(&cfg.signer_stats_file) };
        let t0 = now_ns();
        let journal = Journal::new(rec.clone());
        let knobs = EngineKnobs::default();
        store.ring_versions = knobs.ring_versions;
        Engine { journal, t_now: 0, last_hk_t: 0, last_status_t: 0, last_drift_t: 0, anchored: false, t_anchor: 0, init_journaled: false, gate_journaled: None,
            gate_seen: GateSeen::default(), queue_now: 0,
            decisions: 0, last_block_meta: None, acct_rec: None, base_watch: None, builder: None, alt_by_pool: HashMap::default(), alt_pools: HashMap::default(),
            watch_set: HashSet::default(), uva_key: std::cell::OnceCell::new(),
            reg, store, cfg, feeds, min_tip, interest, ata: AtaCache::default(), sigs: HashMap::default(), sig_order: VecDeque::new(),
            alts: Alts::new(knobs.alts.clone()), acct_pool, part_pools, eval_pools, tier_a, tier_a_complete: false,
            watch: HashMap::default(), opps: HashMap::default(), next_id: 0, next_decision: 0, slot: 0, shred_slot: 0,
            lat: LAT_SERIES.into_iter().map(Series::new).collect(),
            counts: HashMap::default(), rec, status_lines: 0, gate: None, io: None, offline_fetches: Vec::new(), offline_reads: Vec::new(), slots: [0; 3], store_slot_max: 0,
            queue_hwm: 0,
            t_start: t0, sp: StatusPrev { t: t0, ..Default::default() }, exec_prev: Default::default(), feed_counters: Vec::new(), state_counters: None, leads: Vec::new(),
            fh: rec::health::FeedHealth::new(t0),
            exec: None, ledger: None, last_ledger_tick: 0, signer_base: Arc::new(signer_stats.clone()), signer_stats, signer_delta: HashMap::default(), signer_stats_sha256,
            signer_stats_out: None,
            trig_pending: HashMap::default(),
            caps_pending: Vec::new(), amm: amm_programs(), tip_names: crate::send::tip_owner_names(), arbers: HashSet::default(),
            moves_seen: HashSet::default(), poh: HashMap::default(), poh_order: VecDeque::new(),
            tracker: CommitTracker::new(TrackerCfg::new(knobs.commit_timeout_ms, knobs.quiescence_ms)), forks: SlotTree::default(), state: StateStream::default(),
            flags: Arc::new(HealthFlags::default()), shut: Shut::Warmup,
            slo: LagSlo::new(knobs.lag_slo_p50_ms, knobs.lag_slo_p90_ms, knobs.lag_slo_breach_minutes, knobs.slo_recover_minutes, &knobs.slo_action),
            deferred: Vec::new(), recent: VecDeque::new(), hints: HashMap::default(), hint_order: VecDeque::new(), acc_queue: VecDeque::new(), acc_windows: HashMap::default(),
            acc_by_venue: Default::default(), commit_lag: Series::new("commit_lag"),
            commit_lag_src: [Series::new("commit_lag_tx"), Series::new("commit_lag_shred"), Series::new("commit_lag_unknown")], stop_req: None, boot_warned: false,
            reads: Reads::default(), resync: None, unverified: HashSet::default(), last_account_t: 0, knobs,
            sendview: Default::default(), activity: Default::default(), seen_journaled: None, exec_init_journaled: false }
    }

    fn count(&mut self, k: &'static str) { *self.counts.entry(k).or_default() += 1; }
    fn count_n(&mut self, k: &'static str, n: u64) { if n > 0 { *self.counts.entry(k).or_default() += n; } }
    fn max_age_ns(&self) -> u64 { self.knobs.max_update_age_ms * 1_000_000 }
    fn quiescence_ns(&self) -> u64 { self.knobs.quiescence_ms * 1_000_000 }

    /// The chain tip: the state stream's newest processed slot (and newest update); while the state is unavailable, the
    /// unexecuted feeds' newest slot too (PLAN-ADDENDUM I-4: the engine slot falls back to the shred feeds)
    pub fn tip_slot(&self) -> u64 {
        let tip = self.slot.max(self.store.stream_slot_max);
        if self.shut == Shut::StateUnavailable { tip.max(self.shred_slot) } else { tip }
    }

    /// the state's health right now (PLAN-ADDENDUM I-4)
    pub fn state_ok(&self) -> bool { self.state.ok(self.t_now, self.max_age_ns()) }

    /// Whether an account update would not become the account's current version: the store holds a newer one (stale), or
    /// its slot is already abandoned (review WP-04 #3b). The journal's ACCOUNT verdict, and what replay checks it against
    pub fn account_refused(&self, key: &Pk, slot: u64, src: u8, write_version: u64, aseq: u64, bank_id: Option<u64>) -> bool {
        self.forks.refuses(slot, bank_id) || self.store.is_stale(key, slot, src, write_version, aseq)
    }

    /// A state-stream message received at `t`. A silence longer than `max_update_age_ms` before it was an outage even if
    /// no timer ran meanwhile to see it: the signer statistics count no miss across it (I-5)
    fn state_message(&mut self, t: u64) {
        if self.state.msgs > 0 && t > self.state.last_msg_t.saturating_add(self.max_age_ns()) { self.state.last_down_end = self.state.last_down_end.max(t); }
        self.state.message(t);
    }

    /// what the warm-up / health gate says now
    pub fn shut(&self) -> Shut { self.shut }

    /// T's first shred: its earliest arrival from an unexecuted feed (F33)
    fn first_shred(&self, txn: &[u8; 64]) -> Option<u64> { self.sigs.get(&sig8(txn)).map(|s| s.first_unexec_t).filter(|t| *t > 0) }

    /// the Tier-A pools whose state these accounts move (sorted): the pools a group wrote
    fn pools_of(&self, accts: &[Pk]) -> Vec<usize> {
        let mut v: Vec<usize> = accts.iter().filter_map(|a| self.eval_pools.get(a)).flatten().copied().filter(|p| self.tier_a.contains(p)).collect();
        v.sort_unstable();
        v.dedup();
        v
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

    /// alts-final.jsonl (MEASUREMENT §4.26; v1 `alts.jsonl`): every lookup table entry the engine knows, at stop, with
    /// when a transaction last used the table (`last_used_ns`, null: never; review WP-04 #11: the next segment preloads
    /// only recently used tables). Each table is serialized on the recorder's writer
    fn write_alts(&self) {
        if !self.rec.is_on() { return; }
        for (t, v) in self.alts.iter() {
            let (t, v, used) = (*t, v.clone(), self.alts.last_used.get(t).copied());
            self.rec.emit(rec::ALTS_FINAL, Record::enc(move |o| {
                let addrs: Vec<Value> = v.iter().map(|a| a.map_or(Value::Null, |k| json!(b58(&k)))).collect();
                let _ = serde_json::to_writer(o, &json!({ "table": b58(&t), "addrs": addrs, "last_used_ns": used }));
            }));
        }
    }

    /// alts.jsonl events (MEASUREMENT §4.26), drained from the lookup-table state
    fn emit_alt_events(&mut self) {
        if self.alts.events.is_empty() { return; }
        let evs = std::mem::take(&mut self.alts.events);
        for e in &evs {
            match e.event {
                "retry_scheduled" => self.count("alt_retry"),
                "give_up" => self.count("alt_gave_up"),
                "fetch_start" if e.refetch => self.count("alt_refetch"),
                "fetch_error" | "fetch_missing" => self.count("alt_fetch_failed"),
                "waiters_dropped" => self.count("alt_wait_dropped"),
                _ => {}
            }
        }
        if !self.rec.is_on() { return; }
        let t = self.t_now;
        self.rec.emit(rec::ALTS, Record::enc_lines(evs.len() as u32, move |o| {
            for (k, e) in evs.iter().enumerate() {
                if k > 0 { o.push(b'\n'); }
                let _ = serde_json::to_writer(&mut *o, &json!({ "t_ns": t, "table": b58(&e.table), "event": e.event, "n_addrs": e.n_addrs, "attempt": e.attempt,
                    "next_retry_ms": e.next_retry_ms, "waiting_txs": e.waiting_txs, "err": e.err, "idle_ms": e.idle_ms, "refetch": e.refetch }));
            }
        }));
    }

    /// rivals.jsonl: an arbitrage-like transaction's fingerprint, at shred time
    /// The rival test (`record_rival`'s rule): an arbitrage-like transaction touches two venue programs besides the
    /// aggregator, or two watched pools, or comes from a signer seen doing either (who is learned here). Its signer
    fn arb_like(&mut self, a: &Arrival, keys: &[Pk]) -> Option<Pk> {
        let signer = a.tx.fee_payer().copied()?;
        let (n_venues, agg, n_pools) = {
            let mut venues: Vec<&'static str> = Vec::new();
            for k in keys { if let Some(n) = self.amm.get(k) { if !venues.contains(n) { venues.push(n); } } }
            let agg = venues.contains(&"jupiter");
            (venues.len() - agg as usize, agg, keys.iter().filter(|k| self.reg.by_pool.contains_key(*k)).count())
        };
        let known = n_venues < 2 && n_pools < 2;
        if known && !self.arbers.contains(&signer) { return None; }
        if !known && !agg && self.arbers.len() < 200_000 { self.arbers.insert(signer); }
        Some(signer)
    }

    fn record_rival(&mut self, a: &Arrival, keys: &[Pk]) {
        if !self.rec.is_on() { return; }
        let tx = &a.tx;
        let Some(signer) = tx.fee_payer().copied() else { return };
        let mut venues: Vec<&'static str> = Vec::new();
        for k in keys { if let Some(n) = self.amm.get(k) { if !venues.contains(n) { venues.push(n); } } }
        let agg = venues.contains(&"jupiter");
        let n_venues = venues.len() - agg as usize;
        let pools: Vec<String> = keys.iter().filter(|k| self.reg.by_pool.contains_key(*k)).map(b58).collect();
        // (the signer was learned by `arb_like`, which runs first, recorder or not)
        let why = if n_venues >= 2 { "venues" } else if pools.len() >= 2 { "pools" } else if self.arbers.contains(&signer) { "known" } else { return };
        // plan addendum I-9 (WP-08): 1 in `[record] rivals_venues_sample` of the `venues` rows, chosen by the signature;
        // a kept one carries the rate and the running counts (the signer was learned above either way)
        let sample = if why == "venues" { let Some(k) = self.rec.sample_rival_venues(&tx.sig) else { return }; (k.one_in > 1).then_some(k) } else { None };
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
            "pools": pools, "alts": tx.lookups.iter().map(|l| b58(&l.table)).collect::<Vec<_>>(), "n_ix": tx.ixs.len(), "n_keys": keys.len(), "head": head,
            "sample": sample });
        self.rec.json(rec::RIVALS, line);
    }

    /// I-5: this segment's signer statistics, written by the recorder's slow writer (atomically) into the run directory:
    /// the whole map, and this segment's counts. The shared, configured file is never written. Review WP-04 #4: the
    /// engine thread hands over only the statistics as loaded (shared, no copy) and a copy of this segment's counts (the
    /// few signers it saw); the writer adds them up and serializes (the real file has 30,304 signers: about 25 ms every
    /// 10 s when the engine thread serialized the whole map)
    fn save_signer_stats(&self) {
        let Some(dir) = self.signer_stats_out.clone() else { return };
        let (base, delta) = (self.signer_base.clone(), self.signer_delta.clone());
        self.rec.task(move || {
            let mut full = (*base).clone();
            for (k, (ok, miss)) in &delta { let e = full.entry(*k).or_default(); e.0 = e.0.saturating_add(*ok); e.1 = e.1.saturating_add(*miss); }
            for (name, v) in [("signer-stats.json", signer_stats_json(&full)), ("signer-stats-delta.json", signer_stats_json(&delta))] {
                let (p, tmp) = (dir.join(name), dir.join(format!("{name}.tmp")));
                if std::fs::write(&tmp, v.to_string()).is_ok() { let _ = std::fs::rename(&tmp, &p); }
            }
        });
    }

    /// a pending trigger's outcome: it landed (`ok`) or failed (from the transaction's own status, a state update, or the
    /// 5 s expiry)
    fn signer_outcome(&mut self, sig: &[u8; 64], ok: bool) {
        let Some((sg, _)) = self.trig_pending.remove(sig) else { return };
        let (s, d) = (self.signer_stats.entry(sg).or_default(), self.signer_delta.entry(sg).or_default());
        if ok { s.0 += 1; d.0 += 1; } else { s.1 += 1; d.1 += 1; }
    }

    /// Run until `stop`, the deadline `until_ns`, the channel closes or the engine asks to stop (the state stream never
    /// delivered, I-4); says which. `status` is called every 10 s with a one-line summary. The final status.jsonl line is
    /// the caller's (`write_final_status`), once it knows the stop reason.
    ///
    /// WP-03 (the input journal): the engine_init record first, then each input is handled by `step` with one clock read
    /// taken at its dequeue, and every timer by `timers_at` with its own clock read and what it may do; both are
    /// journaled, so a replay calls them at exactly the same points, times and scopes. WP-04's timer rules:
    /// - an idle wake-up (at the next commit deadline or lookup-table retry, at most 5 ms away): everything;
    /// - after an input, when the queue is empty and a commit deadline or retry is due: the commit timers. Nothing in the
    ///   queue can then be an update of a group that resolves (a backlog resolves groups by stream evidence instead);
    /// - after an input, every 10 s while the queue never empties: housekeeping (and the commit timers if it is empty).
    pub fn run(&mut self, rx: &Receiver<Event>, stop: &std::sync::atomic::AtomicBool, until_ns: u64, mut status: impl FnMut(&str)) -> RunEnd {
        self.rec.set_engine_tid(crate::runtime::gettid());
        // the executor's sends are gated on this engine's health (warm-up, state availability) and, with a ledger, on the
        // start equity being known (WP-07: the equity floor needs it)
        let with_ledger = self.ledger.is_some();
        if let Some(x) = self.exec.as_mut() { x.set_health(self.flags.clone()); x.require_equity(with_ledger); }
        self.journal_init();
        self.journal_exec_init();
        let end = loop {
            if stop.load(std::sync::atomic::Ordering::Relaxed) { break RunEnd::Stopped; }
            if self.stop_req.is_some() { break RunEnd::StateUnavailable; }
            if now_ns() >= until_ns { break RunEnd::Deadline; }
            let ev = match rx.try_recv() {
                Ok(e) => e,
                Err(TryRecvError::Disconnected) => break RunEnd::Disconnected,
                Err(TryRecvError::Empty) => {
                    // spin briefly (an event usually follows another within microseconds), then block until the next
                    // deadline (at most 5 ms)
                    let until_spin = now_ns() + SPIN_NS;
                    let mut got = None;
                    while now_ns() < until_spin { if let Ok(e) = rx.try_recv() { got = Some(e); break; } std::hint::spin_loop(); }
                    match got {
                        Some(e) => e,
                        None => {
                            let now = now_ns();
                            let wait = self.next_due().map_or(5_000_000, |d| d.saturating_sub(now).clamp(200_000, 5_000_000));
                            match rx.recv_timeout(std::time::Duration::from_nanos(wait)) {
                                Ok(e) => e,
                                Err(RecvTimeoutError::Timeout) => { self.queue_now = rx.len(); self.timers_at(now_ns(), TIMER_ALL, &mut status); continue; }
                                Err(RecvTimeoutError::Disconnected) => break RunEnd::Disconnected,
                            }
                        }
                    }
                }
            };
            let t_engine = now_ns();
            let q = rx.len();
            if q > self.queue_hwm { self.queue_hwm = q; }
            self.queue_now = q;
            self.step(ev, t_engine, &mut status);
            let t = now_ns();
            let what = after_input_timers(rx.is_empty(), t.saturating_sub(self.last_status_t), self.next_due().is_some_and(|d| d <= t));
            if what != 0 {
                self.queue_now = rx.len();
                self.timers_at(t, what, &mut status);
            }
        };
        self.finish();
        end
    }

    /// the earliest commit deadline, deferred evaluation, lookup-table retry or account read (the receive-time / engine clock)
    fn next_due(&self) -> Option<u64> {
        [self.tracker.next_deadline(), self.deferred.iter().map(|d| d.0).min(), self.alts.next_retry(), self.reads.next_due()].into_iter().flatten().min()
    }

    /// the timer anchors (housekeeping, drift check, status line, boot timeout) start at the first journaled time
    fn anchor(&mut self, t: u64) {
        if self.anchored { return; }
        self.anchored = true;
        self.last_hk_t = t;
        self.last_status_t = t;
        self.last_drift_t = t;
        self.t_anchor = t;
    }

    /// One input, dequeued at `t_engine` (WP-03 item 11): journaled, then handled. Every decision made while handling
    /// it reads `t_engine`, never the clock
    pub fn step(&mut self, ev: Event, t_engine: u64, status: &mut dyn FnMut(&str)) {
        self.t_now = t_engine;
        self.anchor(t_engine);
        if self.journal.is_on() {
            let j = &self.journal;
            match &ev {
                Event::Tx(a) => {
                    // a first copy in full; a later copy by its timing, unless it carries what the engine uses: addresses
                    // it learns lookup-table entries from, or its executed status (WP-04: signer outcomes, W(T))
                    let first = !self.sigs.contains_key(&sig8(&a.tx.sig));
                    if first || (a.tx.loaded.is_some() && !a.tx.lookups.is_empty()) || a.executed.is_some() { j.tx_first(t_engine, a) } else { j.tx_copy(t_engine, a) }
                }
                Event::Account { pubkey, slot, aseq, src, write_version, bank_id, .. } => j.account(t_engine, *aseq, self.account_refused(pubkey, *slot, *src, *write_version, *aseq, *bank_id)),
                Event::Slot { slot, status: st, t, parent, bank_id, .. } => j.slot(t_engine, *slot, *parent, *st, *t, *bank_id),
                Event::BlockMeta(b) => j.block_meta(t_engine, b),
                Event::Alt { table, addrs, err } => j.alt(t_engine, *table, addrs.clone(), err.clone()),
                Event::Input { kind, data } => j.input(t_engine, *kind, data.clone()),
                Event::Status { feed, msg } => j.status(t_engine, *feed, msg),
                Event::Settled(st) => j.input(t_engine, InputKind::Settled, Arc::new(settled_json(st))),
            }
        }
        self.on_event(ev, t_engine, status);
        self.journal_evictions(t_engine);
        self.refresh_health(t_engine);
    }

    /// The timers, evaluated at `t` with everything allowed (`TIMER_ALL`; tests and offline drivers)
    pub fn timers(&mut self, t: u64, status: &mut dyn FnMut(&str)) { self.timers_at(t, TIMER_ALL, status) }

    /// The timers, evaluated at `t` (journaled as TIMER with `what`): the commit timers (groups and deferred evaluations
    /// due at `t`, lookup-table retries), housekeeping when it is due, the accuracy monitor's idle work
    pub fn timers_at(&mut self, t: u64, what: u8, status: &mut dyn FnMut(&str)) {
        self.t_now = t;
        self.anchor(t);
        self.journal.timer(t, what);
        if what & TIMER_COMMIT != 0 {
            let rs = self.tracker.expire(t);
            self.on_resolutions(rs);
            self.run_deferred(t);
            let mut fetch = Vec::new();
            self.alts.due(t, &mut fetch);
            for f in fetch { self.fetch_alt(f); }
            self.emit_alt_events();
            self.journal_evictions(t);
            let mut reads = Vec::new();
            self.reads.due(t, &mut reads);
            for f in reads { self.spawn_read(f); }
        }
        if what & TIMER_HK != 0 && (t.saturating_sub(self.last_hk_t) >= HOUSEKEEPING_NS || t.saturating_sub(self.last_status_t) > STATUS_EVERY_NS) {
            self.housekeeping(t, status);
        }
        if what & TIMER_ACC != 0 && !self.acc_queue.is_empty() { self.score_batch(ACC_BATCH); }
        // after housekeeping (Tier A's completeness): what the next decisions and send checks see
        self.refresh_health(t);
    }

    /// One input event, dequeued at `t_engine`: the body of `step` (without the journal)
    fn on_event(&mut self, ev: Event, t_engine: u64, status: &mut dyn FnMut(&str)) {
        self.t_now = t_engine;
        match ev {
            Event::Tx(a) => self.on_tx(a, t_engine),
            Event::Account { slot, pubkey, data, t, txn, write_version, src, aseq, bank_id, lamports, .. } => {
                let v = Acct { data, slot, write_version, txn, t_recv: t, aseq, src, bank_id, lamports };
                self.on_account(pubkey, v, t_engine);
            }
            Event::Slot { slot, status: st, t, parent, bank_id, .. } => self.on_slot(slot, st, t, parent, bank_id, t_engine),
            Event::BlockMeta(b) => {
                self.state_message(b.t);
                if self.last_block_meta.map_or(true, |x| b.slot > x.0) { self.last_block_meta = Some((b.slot, b.blockhash, b.block_height)); }
                // WP-05: the processed blockhash source and the block height (attempts expire by it)
                self.sendview.on_block_meta(b.slot, b.blockhash, b.block_height, b.t);
            }
            Event::Input { kind, data } => match kind {
                InputKind::Health => self.on_health(&data),
                InputKind::SlotidxMissing => self.on_slotidx_missing(&data),
                InputKind::Fetch => self.on_fetch(&data),
                // WP-05: the blockhash ring's confirmed head and the leader schedule (what the send checks read), our
                // wallet's transactions (an attempt landed) and the block engine's results for our bundles
                InputKind::BlockhashHead => self.sendview.on_head(&data),
                InputKind::LeaderWindow => self.sendview.on_window(&data),
                InputKind::WalletTx => {
                    // WP-07: the ledger first (its line goes into the attempt's outcome), then the executor's settlement; a
                    // refused bundle the record shows landed is raised at once (review WP-07 #6)
                    let data = self.ledger_wallet_tx(data);
                    let (poh, t, global) = (&self.poh, self.t_now, self.io.is_some());
                    let refused = match self.exec.as_mut() { Some(x) => { x.on_wallet_tx(&data, t, &|s| poh_of(poh, s, global)); x.take_refused_landed() } None => Vec::new() };
                    if !refused.is_empty() { if let Some(l) = self.ledger.as_mut() { l.on_refused_landed(t, refused); } }
                    self.ledger_tick(self.t_now, true);
                }
                InputKind::Snapshot => {
                    if let Some(mut l) = self.ledger.take() { l.on_input(&data, self.t_now, &|m, a| self.sol_value(m, a)); self.ledger = Some(l); }
                    self.ledger_tick(self.t_now, true);
                }
                InputKind::InflightRelease => { let t = self.t_now; if let Some(x) = self.exec.as_mut() { x.on_release(&data, t); } }
                // gate records (the 100 ms watch: status only), quarantines (Stage 1), settlements (`Event::Settled`)
                _ => {}
            },
            Event::Status { msg, .. } => status(&msg),
            Event::Alt { table, addrs, err } => {
                let a = match (addrs, err) { (Some(v), _) => Answer::Found(v.to_vec()), (None, Some(e)) => Answer::Error(e), (None, None) => Answer::Missing };
                self.on_alt(table, a);
            }
            Event::Settled(st) => { let (poh, t, global) = (&self.poh, self.t_now, self.io.is_some()); if let Some(x) = self.exec.as_mut() { x.on_settled(*st, t, &|s| poh_of(poh, s, global)); } }
        }
    }

    // ---------------------------------------------------------------- health (I-4, item 8)

    /// The state stream's task said it connected or lost the stream (INPUT 6 `health`, journaled). Its first connection
    /// (the boot snapshot was read before the stream subscribed) and every reconnection after a loss start the re-read of
    /// every followed account (review WP-04 #1, I-4): the stream does not resend writes it did not deliver
    fn on_health(&mut self, d: &Value) {
        if d["src"].as_str() != Some("state") { return; }
        let Some(connected) = d["connected"].as_bool() else { return };
        let was = self.state.connected;
        self.state.connected = Some(connected);
        if let Some(r) = d["reconnects"].as_u64() { self.state.reconnects = r; }
        if !connected {
            self.state.last_error = d["error"].as_str().map(String::from);
            self.count("state_disconnect");
        } else if was != Some(true) && self.knobs.resnapshot {
            self.begin_resync(if was.is_none() { "boot" } else { "reconnect" });
        }
    }

    /// The re-read (review WP-04 #1): every followed account (the programdata ones aside: megabytes each, the stream
    /// reports their upgrades) is unverified until the re-read or a stream write brings it, and the gate is `resync`
    /// until the re-read has landed. A re-read still running is replaced (its answers no longer verify anything: they
    /// predate this connection's gap)
    fn begin_resync(&mut self, why: &'static str) {
        if let Some(old) = self.resync.take() { if let Some(j) = old.job { self.reads.cancel(j); } self.count("state_resync_superseded"); }
        let chunks = self.resync_chunks();
        let n_keys: usize = chunks.iter().map(|c| c.len()).sum();
        self.unverified = chunks.iter().flatten().copied().collect();
        self.state.resnapshots += 1;
        self.count("state_resnapshot");
        self.rec.event("state_resnapshot", "state", None, json!({ "why": why, "accounts": n_keys, "chunks": chunks.len(), "reconnects": self.state.reconnects }));
        self.resync = Some(Resync { why, t_connect: self.t_now, chunks, n_keys, job: None, floor: None, warned: false, behind: 0, failed: 0, missing: 0 });
    }

    /// What the re-read reads, in chunks of at most 100 accounts: each Tier-A pool's own accounts (pool, consistency set,
    /// vaults, followed DLMM bin arrays) in one chunk, so a pool's parts are read at one slot (the skew rule holds after a
    /// reconnect), then the shared parts and the other followed accounts
    fn resync_chunks(&self) -> Vec<Vec<Pk>> {
        let mut keys: Vec<Pk> = match &self.base_watch { Some(b) => b.clone(), None => self.reg.static_accounts() };
        for l in self.store.dlmm_arrays.values() { keys.extend(l.iter().map(|x| x.1)); }
        if let Some(ar) = &self.acct_rec { keys.retain(|k| ar.roles().get(k).map_or(true, |r| r.role != crate::rec::accounts::role::PROGRAMDATA)); }
        let want: HashSet<Pk> = keys.iter().copied().collect();
        let mut placed: HashSet<Pk> = HashSet::default();
        let mut groups: Vec<Vec<Pk>> = Vec::new();
        let mut pools: Vec<usize> = self.reg.pairs.values().flatten().copied().collect();
        pools.sort_unstable();
        pools.dedup();
        for i in pools {
            let m = &self.reg.pools[i];
            let mut cand = vec![m.pool];
            cand.extend(consistency_set(m));
            if !matches!(m.venue, Venue::Dlmm | Venue::DammV2) { cand.extend([m.vault0, m.vault1]); }
            if let Some(l) = self.store.dlmm_arrays.get(&m.pool) { cand.extend(l.iter().map(|x| x.1)); }
            let g: Vec<Pk> = cand.into_iter().filter(|k| want.contains(k) && placed.insert(*k)).collect();
            if !g.is_empty() { groups.push(g); }
        }
        let rest: Vec<Pk> = keys.into_iter().filter(|k| placed.insert(*k)).collect();
        groups.extend(rest.chunks(crate::reads::CHUNK).map(|c| c.to_vec()));
        crate::reads::pack(groups)
    }

    /// The stream's resume slot after a (re)connection: its first account update or processed slot. The re-read starts
    /// one slot later, its chunks paced, and a chunk read at an older slot is read again
    fn resync_floor(&mut self, slot: u64) {
        let Some(r) = self.resync.as_mut() else { return };
        if r.floor.is_some() { return; }
        r.floor = Some(slot);
        let chunks = std::mem::take(&mut r.chunks);
        let t = self.t_now;
        let mut out = Vec::new();
        let id = self.reads.start(What::Resync, chunks, t, t + RESYNC_DELAY_NS, RESYNC_PACE_NS, self.knobs.resync_give_up_s.saturating_mul(1_000_000_000), &mut out);
        if let Some(r) = self.resync.as_mut() { r.job = Some(id); }
        for f in out { self.spawn_read(f); }
        if self.reads.complete(id) { self.read_job_done(id); }
    }

    /// A read the engine needs now (a fork refetch, new DLMM bin arrays): chunks of 100, started at once, retried
    fn start_read(&mut self, what: What, keys: Vec<Pk>) {
        if keys.is_empty() { return; }
        let chunks: Vec<Vec<Pk>> = keys.chunks(crate::reads::CHUNK).map(|c| c.to_vec()).collect();
        let t = self.t_now;
        let mut out = Vec::new();
        self.reads.start(what, chunks, t, t, 0, READ_GIVE_UP_NS, &mut out);
        for f in out { self.spawn_read(f); }
    }

    /// One chunk read on the background runtime: its accounts come back as account events (each recorded in accounts.bin
    /// first, `src` rpc_snapshot or rpc_refetch, so the journal names it by its aseq), then INPUT 11 `fetch` says how the
    /// chunk ended. An offline engine records the read in `offline_fetches` instead
    fn spawn_read(&mut self, f: Fetch) {
        let Some(io) = &self.io else { self.offline_fetches.push((f.what.as_str(), f.keys.clone())); self.offline_reads.push(f); return };
        // FT-000 (S1-3): the state stream's re-read is critical (role `snapshot`): pricing waits for it, and at boot it
        // queued 51.4 s behind the lookup-table fetches; fork refetches and new bin arrays stay `engine`
        let rpc = if f.what == What::Resync { io.rpc.with_role(crate::rpc::Role::Snapshot) } else { io.rpc.clone() };
        let (back, ar) = (io.tx_back.clone(), self.acct_rec.clone());
        io.rt.spawn(async move {
            let (src, what) = (f.what.src(), f.what.as_str());
            let head = json!({ "job": f.job, "chunk": f.chunk, "what": what, "attempt": f.attempt, "n": f.keys.len() });
            let data = match rpc.accounts(&f.keys).await {
                Ok((slot, v)) if v.len() == f.keys.len() => {
                    let mut missing = Vec::new();
                    for (k, a) in f.keys.iter().zip(v) {
                        let Some(a) = a else { missing.push(b58(k)); continue };
                        let (t, data): (u64, Arc<[u8]>) = (now_ns(), Arc::from(a.data));
                        let aseq = ar.as_ref().map_or(0, |r| r.record(&crate::rec::accounts::AcctUpdate { pubkey: *k, slot, write_version: 0, t_recv: t, src,
                            is_startup: false, txn: None, lamports: a.lamports, owner: a.owner, data: &data, bank_id: None }));
                        let _ = back.send(Event::Account { slot, pubkey: *k, owner: a.owner, lamports: a.lamports, data, t, txn: None, write_version: 0, is_startup: false,
                            src, aseq, bank_id: None });
                    }
                    let mut d = head;
                    d["ok"] = json!(true);
                    d["slot"] = json!(slot);
                    d["missing"] = json!(missing);
                    d
                }
                Ok((_, v)) => { let mut d = head; let n = v.len(); d["ok"] = json!(false); d["err"] = json!(format!("{n} values for {} accounts", f.keys.len())); d }
                Err(e) => { let mut d = head; d["ok"] = json!(false); d["err"] = json!(crate::rpc::scrub(&format!("{e:#}"))); d }
            };
            let _ = back.send(Event::Input { kind: InputKind::Fetch, data: Arc::new(data) });
        });
    }

    /// INPUT 11 `fetch`: how one chunk of a read ended (its account events came first). A re-read's chunk verifies its
    /// accounts (the ones the node had) when it read at or after the stream's resume slot; one read behind it, or a
    /// failed one, is read again later (or given up past its job's time)
    fn on_fetch(&mut self, d: &Value) {
        let (Some(job), Some(chunk)) = (d["job"].as_u64(), d["chunk"].as_u64().map(|c| c as usize)) else { return };
        let Some(what) = self.reads.what_of(job) else { self.count("read_answer_dropped"); return };
        let t = self.t_now;
        let ok = d["ok"].as_bool() == Some(true);
        let slot = d["slot"].as_u64().unwrap_or(0);
        let floor = if what == What::Resync { self.resync.as_ref().filter(|r| r.job == Some(job)).and_then(|r| r.floor) } else { None };
        let behind = ok && floor.is_some_and(|f| slot < f);
        let mut out = Vec::new();
        if ok && !behind {
            let missing: HashSet<Pk> = d["missing"].as_array().into_iter().flatten().filter_map(|k| k.as_str())
                .filter_map(|k| bs58::decode(k).into_vec().ok()?.try_into().ok()).collect();
            if let Some(keys) = self.reads.landed(job, chunk, t, &mut out) {
                self.count("read_chunk_ok");
                self.count_n("read_missing", missing.len() as u64);
                if what == What::Resync {
                    // an account the node does not have stays unverified while the store holds a version of it (its pools
                    // are refused until the stream writes it); one the store never had has nothing to verify
                    for k in keys.iter().filter(|k| !missing.contains(*k) || self.store.get(k).is_none()) { self.unverified.remove(k); }
                    if let Some(r) = self.resync.as_mut() { r.missing += missing.len() as u64; }
                }
            }
        } else {
            let err = if behind { format!("read at slot {slot}, behind the stream's resume slot {}", floor.unwrap_or(0)) } else { d["err"].as_str().unwrap_or("?").to_string() };
            if behind { self.count("resync_chunk_behind"); } else { self.count("read_chunk_failed"); }
            if let Some(r) = self.resync.as_mut().filter(|r| r.job == Some(job)) { if behind { r.behind += 1; } else { r.failed += 1; } }
            match self.reads.failed(job, chunk, t, err.clone(), &mut out) {
                Failed::Retry { at, attempt } => {
                    self.count("read_retry");
                    self.rec.event("read_retry", "state", None, json!({ "what": what.as_str(), "job": job, "chunk": chunk, "attempt": attempt,
                        "in_ms": at.saturating_sub(t) / 1_000_000, "err": err }));
                }
                Failed::GaveUp => self.count("read_gave_up"),
                Failed::Unknown => {}
            }
        }
        for f in out { self.spawn_read(f); }
        if self.reads.complete(job) { self.read_job_done(job); }
    }

    /// A read job has every chunk landed or given up: the re-read's end opens the gate (an event and a run.log line; the
    /// accounts it could not read stay refused, one by one, with a WARNING); a given-up refetch is an event
    fn read_job_done(&mut self, id: u64) {
        let Some(j) = self.reads.finish(id) else { return };
        let gave_up: Vec<Pk> = j.chunks.iter().filter(|c| c.gave_up()).flat_map(|c| c.keys.iter().copied()).collect();
        if j.what == What::Resync && self.resync.as_ref().is_some_and(|r| r.job == Some(id)) {
            let r = self.resync.take().unwrap();
            let ms = self.t_now.saturating_sub(r.t_connect) / 1_000_000;
            self.count("state_resync_done");
            self.rec.event("state_resync_done", "state", None, json!({ "why": r.why, "ms": ms, "accounts": r.n_keys, "chunks": j.chunks.len(), "retries": j.retries,
                "behind": r.behind, "failed": r.failed, "missing": r.missing, "gave_up": gave_up.len(), "unverified_now": self.unverified.len(), "floor": r.floor }));
            self.rec.say(format!("state re-read ({}) done {ms} ms after the connection: {} accounts in {} chunks, {} retries ({} behind the stream, {} failed), {} not found",
                r.why, r.n_keys, j.chunks.len(), j.retries, r.behind, r.failed, r.missing));
            if !gave_up.is_empty() {
                self.rec.say(format!("WARNING: the state re-read gave up on {} accounts after {} s ({}): their pools stay refused (resync) until the stream writes them",
                    gave_up.len(), self.knobs.resync_give_up_s, j.last_err().unwrap_or("?")));
            }
        } else if !gave_up.is_empty() {
            self.rec.event("read_gave_up", "state", None, json!({ "what": j.what.as_str(), "accounts": gave_up.len(), "err": j.last_err() }));
        }
    }

    /// Recompute what the store's health says at `t` (after every input and timer): state availability (I-4), the
    /// boot timeout, the warm-up gate (item 8). Transitions are events and run.log lines
    fn refresh_health(&mut self, t: u64) {
        let ok = self.state.ok(t, self.max_age_ns());
        match (ok, self.state.down_since) {
            (false, None) => {
                // since when: the stream's word, or the moment its newest message became too old
                let stale_at = if self.state.msgs > 0 && self.state.connected != Some(false) { self.state.last_msg_t.saturating_add(self.max_age_ns()).min(t) } else { t };
                self.state.down_since = Some(stale_at);
                self.state.down_total += 1;
                self.count("state_unavailable");
                let why = if self.state.msgs == 0 { "nothing received yet" } else if self.state.connected == Some(false) { "stream down" } else { "no message within max_update_age_ms" };
                let age = self.state.age_ns(t).map(|a| a / 1_000_000);
                // the boot's first stretch (nothing received yet) is the warm-up, not an outage: an event, no WARNING
                if self.state.msgs > 0 {
                    self.rec.say(format!("WARNING: state unavailable ({why}; newest message {} ms old, {} reconnects): nothing is priced or sent until it is back",
                        age.map_or("-".into(), |a| a.to_string()), self.state.reconnects));
                }
                self.rec.event("state_unavailable", "state", None, json!({ "why": why, "age_ms": age, "connected": self.state.connected, "reconnects": self.state.reconnects,
                    "error": self.state.last_error }));
            }
            (true, Some(since)) => {
                self.state.down_since = None;
                self.state.last_down_end = t;
                let down_ms = t.saturating_sub(since) / 1_000_000;
                if self.state.down_total > 1 || since > self.t_anchor { self.rec.say(format!("state available again after {down_ms} ms")); }
                self.rec.event("state_available", "state", None, json!({ "down_ms": down_ms, "reconnects": self.state.reconnects }));
            }
            _ => {}
        }
        if self.state.msgs == 0 && !self.boot_warned && t.saturating_sub(self.t_anchor) >= 10_000_000_000 {
            self.boot_warned = true;
            self.rec.say(format!("WARNING: the state stream has delivered nothing in 10 s ({} reconnects; last error: {}): nothing is priced; the run stops after {} s",
                self.state.reconnects, self.state.last_error.as_deref().unwrap_or("none"), self.knobs.boot_timeout_s));
        }
        // review WP-04 #10 (owner decision, off by default): an outage after the stream had delivered stops the run too
        if let Some(since) = self.state.down_since.filter(|_| self.knobs.unavailable_stop_s > 0 && self.state.msgs > 0 && self.stop_req.is_none()) {
            if t.saturating_sub(since) >= self.knobs.unavailable_stop_s.saturating_mul(1_000_000_000) {
                let why = format!("the state has been unavailable for {} s ({} reconnects; last error: {})", t.saturating_sub(since) / 1_000_000_000, self.state.reconnects,
                    self.state.last_error.as_deref().unwrap_or("none"));
                self.rec.say(format!("WARNING: {why}: stopping (state_unavailable; [state] unavailable_stop_s = {})", self.knobs.unavailable_stop_s));
                self.rec.event("state_unavailable", "state", None, json!({ "why": "unavailable_stop", "detail": why }));
                self.stop_req = Some(why);
            }
        }
        if self.state.msgs == 0 && self.knobs.boot_timeout_s > 0 && self.stop_req.is_none() && t.saturating_sub(self.t_anchor) >= self.knobs.boot_timeout_s * 1_000_000_000 {
            let why = format!("the state stream delivered nothing within {} s of the engine's start ({} reconnects; last error: {})", self.knobs.boot_timeout_s,
                self.state.reconnects, self.state.last_error.as_deref().unwrap_or("none"));
            self.rec.say(format!("WARNING: {why}: stopping (state_unavailable)"));
            self.rec.event("state_unavailable", "state", None, json!({ "why": "boot_timeout", "detail": why }));
            self.stop_req = Some(why);
        }
        // the re-read after a (re)connection: a WARNING when it has not landed in `resync_warn_s` (the gate stays shut)
        if let Some(r) = self.resync.as_mut().filter(|r| !r.warned && t.saturating_sub(r.t_connect) >= self.knobs.resync_warn_s.saturating_mul(1_000_000_000)) {
            r.warned = true;
            let (why, floor, n) = (r.why, r.floor, r.n_keys);
            let job = r.job.and_then(|j| self.reads.job(j));
            let (done, chunks, err) = job.map_or((0, 0, None), |j| (j.n_done(), j.chunks.len(), j.last_err().map(String::from)));
            self.count("state_resync_slow");
            self.rec.say(format!("WARNING: the state re-read ({why}) has not landed {} s after the connection ({done} of {chunks} chunks; stream resume slot {}; last error: {}): \
                nothing is sent until it has", self.knobs.resync_warn_s, floor.map_or("not yet seen".into(), |f| f.to_string()), err.as_deref().unwrap_or("none")));
            self.rec.event("state_resync_slow", "state", None, json!({ "why": why, "accounts": n, "chunks": chunks, "chunks_done": done, "floor": floor, "err": err,
                "unverified_now": self.unverified.len() }));
        }
        let lag_ok = self.tip_slot().saturating_sub(self.store.stream_slot_max) <= self.knobs.max_tip_lag_slots;
        let shut = if !ok { Shut::StateUnavailable } else if self.resync.is_some() { Shut::Resync } else if !(self.tier_a_complete && lag_ok) { Shut::Warmup } else { Shut::Ready };
        if shut != self.shut {
            let prev = self.shut;
            self.shut = shut;
            if shut == Shut::Ready {
                self.count("warmup_ready");
                self.rec.event("warmup_ready", "state", None, json!({ "tier_a": self.tier_a.len(), "tip": self.tip_slot(), "store_slot": self.store.stream_slot_max }));
            } else if prev == Shut::Ready {
                self.count("warmup_lost");
                self.rec.event("warmup_lost", "state", None, json!({ "why": shut.as_str(), "tier_a_complete": self.tier_a_complete, "lag_ok": lag_ok }));
            }
        }
        self.flags.set(shut);
    }

    /// Tier A (item 8): every pool complete? A pool whose parts are still missing `tier_a_grace_s` after the start
    /// leaves Tier A (an event)
    fn check_tier_a(&mut self, t: u64) {
        if self.tier_a_complete { return; }
        let missing: Vec<usize> = self.tier_a.iter().copied().filter(|&i| {
            let m = &self.reg.pools[i];
            consistency_set(m).iter().chain(other_parts(m).iter()).any(|k| self.store.get(k).is_none())
        }).collect();
        if missing.is_empty() { self.tier_a_complete = true; return; }
        if t.saturating_sub(self.t_anchor) >= self.knobs.tier_a_grace_s * 1_000_000_000 {
            for i in missing {
                self.tier_a.remove(&i);
                self.count("tier_a_dropped");
                self.rec.event("tier_a_drop", "state", None, json!({ "pool": b58(&self.reg.pools[i].pool), "venue": self.reg.pools[i].venue,
                    "why": format!("parts missing {} s after the start", self.knobs.tier_a_grace_s) }));
            }
            self.tier_a_complete = true;
        }
    }

    /// A digest of the engine's decision state (WP-03: replay determinism). Two engines fed the same journal have the
    /// same digest. Stage timestamps and latency series (real clock reads) are left out, as are counters of recording.
    /// FT-001: the digest of the parts `digest_walk` names, in its order (the bytes and their order are what they were
    /// before the parts: a recording made before them checks against the same value)
    pub fn digest(&self) -> u64 {
        let mut x = xxhash_rust::xxh3::Xxh3::new();
        self.digest_walk(&mut |_, feed| feed(&mut x));
        x.digest()
    }

    /// ---- FT-001 (the p1 replay's state digest). The state digest and the decision digest with each part's own digest
    /// (`digest_walk`'s names), in one pass: what the run records at its digest points and a replay computes at the same
    /// journaled points, so a difference names the part that differs
    pub fn digests(&self) -> Digests {
        let t0 = std::time::Instant::now();
        let mut all = xxhash_rust::xxh3::Xxh3::new();
        let mut parts = Vec::new();
        self.digest_walk(&mut |name, feed| {
            let mut p = xxhash_rust::xxh3::Xxh3::new();
            feed(&mut Tee(&mut all, &mut p));
            parts.push((name, p.digest()));
        });
        Digests { state: all.digest(), decision: self.decision_digest(), parts, ms: t0.elapsed().as_secs_f64() * 1e3 }
    }

    /// ---- FT-001. The state digest's parts in order, each handed to `f` with what it folds: the store (accounts and
    /// their ring versions, the followed DLMM bin arrays, its totals), the signatures' arrival windows, the open
    /// opportunities, the signer statistics, the pending triggers, the lookup-table cache, the commit groups, the fork
    /// tree, the account reads, the re-read, the unverified accounts, the counters, the ids, the slots, the health gate,
    /// the state stream's messages, the deferred evaluations, the accuracy queue, the decision hash, and with an executor
    /// its parts (`Exec::digest_walk`) and the crowding map
    fn digest_walk(&self, f: &mut dyn FnMut(&'static str, &dyn Fn(&mut dyn Fold))) {
        f("store.accounts", &|x| {
            let mut keys: Vec<&Pk> = self.store.keys().collect();
            keys.sort();
            for k in keys {
                x.update(k);
                for a in self.store.versions(k) {
                    x.update(&a.slot.to_le_bytes()); x.update(&a.write_version.to_le_bytes()); x.update(&a.t_recv.to_le_bytes()); x.update(&a.aseq.to_le_bytes());
                    x.update(a.txn.as_ref().map_or(&[0u8; 64][..], |s| &s[..])); x.update(&a.data); x.update(&a.lamports.to_le_bytes());
                }
            }
        });
        f("store.dlmm_arrays", &|x| {
            let mut arr: Vec<(&Pk, &Vec<(i64, Pk)>)> = self.store.dlmm_arrays.iter().collect();
            arr.sort();
            for (k, l) in arr { x.update(k); for (i, a) in l { x.update(&i.to_le_bytes()); x.update(a); } }
        });
        f("store.totals", &|x| { x.update(&self.store.updates.to_le_bytes()); x.update(&self.store.stale_dropped.to_le_bytes()); });
        f("sigs", &|x| {
            let mut sigs: Vec<(&u64, &SigInfo)> = self.sigs.iter().collect();
            sigs.sort_by_key(|x| *x.0);
            for (k, v) in sigs { x.update(&k.to_le_bytes()); x.update(&v.first_t.to_le_bytes()); x.update(&v.first_feed.to_le_bytes()); x.update(&v.slot.to_le_bytes()); for a in v.arr { x.update(&a.to_le_bytes()); } }
        });
        f("opps", &|x| {
            let mut opps: Vec<&Opp> = self.opps.values().collect();
            opps.sort_by_key(|o| o.id);
            for o in opps {
                x.update(&o.id.to_le_bytes()); x.update(&o.trig); x.update(&o.buy); x.update(&o.sell); x.update(&o.size.to_le_bytes()); x.update(&o.net.to_le_bytes());
                x.update(&o.deadline.to_le_bytes()); x.update(&o.touches.len().to_le_bytes()); x.update(&o.landed.unwrap_or(u64::MAX).to_le_bytes());
            }
        });
        f("signer_stats", &|x| {
            let mut ss: Vec<(&Pk, &(u32, u32))> = self.signer_stats.iter().collect();
            ss.sort();
            for (k, v) in ss { x.update(k); x.update(&v.0.to_le_bytes()); x.update(&v.1.to_le_bytes()); }
        });
        f("trig_pending", &|x| {
            let mut tp: Vec<(&[u8; 64], &(Pk, u64))> = self.trig_pending.iter().collect();
            tp.sort();
            for (k, v) in tp { x.update(k); x.update(&v.0); x.update(&v.1.to_le_bytes()); }
        });
        f("alts", &|x| self.alts.digest(x));
        f("commit", &|x| self.tracker.digest(x));
        f("forks", &|x| self.forks.digest(x));
        // the re-read (review WP-04 #1): its job and resume slot, the reads in progress, the accounts still unverified
        f("reads", &|x| self.reads.digest(x));
        f("resync", &|x| {
            if let Some(r) = &self.resync { x.update(&r.job.unwrap_or(u64::MAX).to_le_bytes()); x.update(&r.floor.unwrap_or(u64::MAX).to_le_bytes()); x.update(&r.t_connect.to_le_bytes()); }
        });
        f("unverified", &|x| {
            let mut unv: Vec<&Pk> = self.unverified.iter().collect();
            unv.sort();
            for k in unv { x.update(k); }
        });
        f("counts", &|x| {
            let mut counts: Vec<(&&str, &u64)> = self.counts.iter().collect();
            counts.sort();
            for (k, v) in counts { x.update(k.as_bytes()); x.update(&v.to_le_bytes()); }
        });
        f("ids", &|x| { x.update(&self.next_id.to_le_bytes()); x.update(&self.next_decision.to_le_bytes()); });
        f("slots", &|x| { x.update(&self.slot.to_le_bytes()); x.update(&self.shred_slot.to_le_bytes()); for s in self.slots { x.update(&s.to_le_bytes()); } });
        f("health", &|x| x.update(&[self.shut as u8, self.tier_a_complete as u8]));
        f("state_stream", &|x| { x.update(&self.state.msgs.to_le_bytes()); x.update(&self.state.last_msg_t.to_le_bytes()); });
        f("deferred", &|x| { for (at, p, _) in &self.deferred { x.update(&at.to_le_bytes()); x.update(&p.to_le_bytes()); } });
        f("acc_queue", &|x| x.update(&(self.acc_queue.len() as u64).to_le_bytes()));
        f("decision_hash", &|x| x.update(&self.decisions.to_le_bytes()));
        // ---- WP-09 (review WP-09 "For the WP-05 merge" item 7): the executor's own state, and the crowding map it ranks
        // routes by (an engine without an executor never reads the map: its digest is what it was before WP-09's merge)
        if let Some(e) = &self.exec {
            e.digest_walk(f);
            f("crowding", &|x| self.activity.digest(x));
        }
    }

    /// the running hash of every decision made (each evaluation's best route and verdict, the routes handed to the
    /// executor)
    pub fn decision_digest(&self) -> u64 { self.decisions }

    /// the end of the run: open opportunities finished, the signatures still in their window written, the lookup
    /// tables dumped (alts-final), the signer statistics saved (into the run directory). Returns the digests before and
    /// after this bookkeeping (FT-001: journaled here as the `run_end` digest point, `digest_point`)
    pub fn finish(&mut self) -> (Digests, Digests) {
        // ---- WP-09 (review WP-09 #6): the digests as the run ends (its last journaled record handled), before this
        // bookkeeping empties the opportunities and the signature windows
        let before = self.digests();
        let ids: Vec<u64> = self.opps.keys().copied().collect();
        for id in ids { self.finish_opp(id); }
        let left: Vec<u64> = self.sigs.keys().copied().collect();
        for k in left { if let Some(s) = self.sigs.remove(&k) { self.write_txarr(k, &s); if s.trigger.is_some() { self.write_arrivals(&s); } } }
        self.write_alts();
        self.save_signer_stats();
        let after = self.digest_point(DIGEST_RUN_END, Some(&before));
        (before, after)
    }

    /// The last status.jsonl line, with the run's stop reason (MEASUREMENT A.5; WP-01)
    pub fn write_final_status(&mut self, queue: usize, stop_reason: &str) {
        self.write_status_line(queue, Some(stop_reason));
    }

    // ---------------------------------------------------------------- WP-07: the ledger

    /// INPUT 7 into the ledger (valued at the engine's pools); returns the input with the ledger's line for the attempt's
    /// outcome (`ledger_line`)
    fn ledger_wallet_tx(&mut self, data: Arc<Value>) -> Arc<Value> {
        let Some(mut l) = self.ledger.take() else { return data };
        let rt = self.exec.as_ref().and_then(|x| x.round_trip_of(data["attempt"].as_u64(), data["sig"].as_str().unwrap_or(""), &data["prog_events"]));
        let e = l.on_wallet_tx(&data, self.t_now, &|m, a| self.sol_value(m, a), rt);
        self.ledger = Some(l);
        match e {
            Some(e) => { let mut d = (*data).clone(); d["ledger_line"] = e.outcome_json(); Arc::new(d) }
            None => data,
        }
    }

    /// The ledger's timers (snapshots, reconciliations, the stop rules), at most once a second unless `now_too`; the
    /// executor then reads what the ledger knows (the start equity, the bankroll, the rent)
    fn ledger_tick(&mut self, t: u64, now_too: bool) {
        if !now_too && t.saturating_sub(self.last_ledger_tick) < 1_000_000_000 { return; }
        let Some(mut l) = self.ledger.take() else { return };
        self.last_ledger_tick = t;
        // what the money view's freshness reads (review WP-07 #3): the executor's oldest landing still without its wallet
        // record, the chain-fetch service's wallet give-ups (a run's only)
        let tin = crate::ledger::TickIn { provisional_since: self.exec.as_ref().and_then(|x| x.oldest_provisional_ns()),
            wallet_gave_up: if self.io.is_some() { crate::chainfetch::wallet_gave_up_total() } else { None } };
        let v = l.tick_with(t, &|| self.exec.as_ref().map(|x| x.landings()).unwrap_or_default(), tin);
        self.ledger = Some(l);
        if let Some(x) = self.exec.as_mut() { x.set_money(v); }
    }

    /// The run is stopping (WP-07): ask for the stop snapshot (taken at the next ledger tick)
    pub fn ledger_stop_snapshot(&mut self) {
        if let Some(l) = self.ledger.as_mut() { l.want_stop_snapshot(); }
        let t = self.t_now.max(now_ns());
        self.ledger_tick(t, true);
    }

    /// whether the stop snapshot came (or failed, or there is no ledger)
    pub fn ledger_stop_snapshot_done(&self) -> bool { self.ledger.as_ref().is_none_or(|l| l.stop_snapshot_done()) }

    /// The stop's reconciliation begins (after the stop snapshot): every pending window is due now; one that does not
    /// pass is searched and decided once more `recon_grace_s` later, while the drain keeps handling the records
    /// (review WP-07 #7). Returns how long to wait at most (ns)
    pub fn ledger_final_begin(&mut self) -> u64 {
        let t = self.t_now.max(now_ns());
        let Some(l) = self.ledger.as_mut() else { return 0 };
        l.final_begin(t);
        let grace = l.cfg.recon_grace_s * 1_000_000_000;
        self.ledger_tick(t, true);
        grace + 1_000_000_000
    }

    /// whether the stop's reconciliation has nothing left to wait for (or there is no ledger)
    pub fn ledger_final_settled(&self) -> bool { self.ledger.as_ref().is_none_or(|l| l.final_settled()) }

    /// The final reconciliation (the end of the stop): what is still pending is decided now (a residual still unexplained
    /// is written `final: false`: the next segment decides it again)
    pub fn ledger_final(&mut self) {
        let t = self.t_now.max(now_ns());
        let Some(mut l) = self.ledger.take() else { return };
        l.final_recon(t, &|| self.exec.as_ref().map(|x| x.landings()).unwrap_or_default());
        self.ledger = Some(l);
    }

    /// What `amount` of `mint` is worth in WSOL now: the best quote for selling it through a WSOL pool of the registry,
    /// on committed state (the ledger's valuation, `[ledger] mid_source = "pools"`). None: no pool quotes it
    pub fn sol_value(&self, mint: &Pk, amount: u128) -> Option<(u64, String)> {
        if *mint == *WSOL { return Some((amount.min(u64::MAX as u128) as u64, "wsol".into())); }
        let amount = u64::try_from(amount).ok()?;
        let pools = self.reg.pairs.get(&crate::pools::pair_key(mint, &WSOL))?;
        let (now, slot) = self.chain_now();
        let clk = quote::clock(slot, now);
        let mut best: Option<(u64, Pk)> = None;
        for &i in pools {
            let m = &self.reg.pools[i];
            let skip = self.skip_arrays(m);
            // selling `mint` (spending the pool's token 0 when it is `mint`) as the venue executes a third party's swap
            let Ok(leg) = self.leg_of(m, m.t0 == *mint, clk, &skip, Use::Third) else { continue };
            if let Ok(q) = leg.walk(amount) {
                if best.is_none_or(|b| q.out > b.0) { best = Some((q.out, m.pool)); }
            }
        }
        best.map(|(out, pool)| (out, b58(&pool)))
    }

    /// WP-07 (the stop's drain): after the engine loop ended, keep handling what settles the open attempts (the wallet's
    /// records, the block engine's results, the statuses, the ledger's snapshot) until `done` holds or `until_ns`; nothing
    /// is priced (account and transaction updates are left out: the SendGate is closed). True when `done` held
    pub fn drain(&mut self, rx: &Receiver<Event>, until_ns: u64, done: &dyn Fn(&Engine) -> bool, status: &mut dyn FnMut(&str)) -> bool {
        self.drain_on(rx, until_ns, done, status, &now_ns)
    }

    /// WP-07's stop sequence, after the run loop ended (`run`: `finish` journaled the `run_end` digest point), as `arbx
    /// run` stops (moved here from main.rs by FT-001, unchanged, so the scenario tests run it): the drain (at most
    /// `drain_ns`; the gate is closed, nothing new is sent): the attempts still open settle from the wallet stream, the
    /// block engine's results and their expiry checks. Then, with a ledger, the stop snapshot (at most 20 s) and the
    /// final reconciliation (review WP-07 #7: decided at once when it passes; otherwise its window is searched and decided
    /// once more within `recon_grace_s` while the records of what landed just before the stop come in; still unexplained,
    /// it is written `final: false` and the next segment decides it again). Whatever is still open gets its `unsettled`
    /// outcome line (WP-05; stop.json lists it, the next segment's ledger joins its landing by signature). FT-001: the
    /// `stop_end` digest point last, after the sequence's last journaled record (a replay digests there too). `say`: the
    /// run log. FT-001 p1: the stop snapshot is fetched within `ledger::STOP_SNAPSHOT_BUDGET` (inside the 20 s wait); a
    /// stop without it records why (`Ledger::stop_snapshot_missing`), and the next segment reconciles the window
    pub fn stop_sequence(&mut self, rx: &Receiver<Event>, drain_ns: u64, say: &mut dyn FnMut(&str)) -> StopSeq {
        let in_flight = self.exec.as_ref().map(|x| x.open_attempts().len());
        let t_drain = now_ns();
        if in_flight.is_some_and(|n| n > 0) { say(&format!("stop: waiting at most {} s for {} open attempts to settle", drain_ns / 1_000_000_000, in_flight.unwrap_or(0))); }
        let settled = self.drain(rx, t_drain + drain_ns, &|e| e.exec.as_ref().is_none_or(|x| x.open_attempts().is_empty()), say);
        let drain_ms = now_ns().saturating_sub(t_drain) as f64 / 1e6;
        if self.ledger.is_some() {
            self.ledger_stop_snapshot();
            if !self.drain(rx, now_ns() + 20_000_000_000, &|e| e.ledger_stop_snapshot_done(), say) {
                say("stop: no stop snapshot within 20 s");
                let t = self.t_now.max(now_ns());
                if let Some(l) = self.ledger.as_mut() { l.stop_snapshot_missing(t, "no stop snapshot within the stop sequence's 20 s"); }
            }
            let grace = self.ledger_final_begin();
            if !self.drain(rx, now_ns() + grace, &|e| e.ledger_final_settled(), say) { say("stop: the stop's reconciliation is decided without more records"); }
            self.ledger_final();
        }
        let open = self.exec.as_mut().map(|x| x.settle_at_stop());
        self.digest_point(DIGEST_STOP_END, None);
        StopSeq { in_flight, settled, drain_ms, open }
    }

    /// `drain` on the clock `clock` (tests: a virtual one); a wait for the next event lasts at most 50 ms of real time
    pub fn drain_on(&mut self, rx: &Receiver<Event>, until_ns: u64, done: &dyn Fn(&Engine) -> bool, status: &mut dyn FnMut(&str), clock: &dyn Fn() -> u64) -> bool {
        loop {
            if done(self) { return true; }
            let now = clock();
            if now >= until_ns { return false; }
            match rx.recv_timeout(std::time::Duration::from_nanos((until_ns - now).min(50_000_000))) {
                Ok(ev) => {
                    let keep = matches!(ev, Event::Input { .. } | Event::Settled(_) | Event::Slot { .. } | Event::BlockMeta(_) | Event::Status { .. });
                    if keep { let t = clock(); self.step(ev, t, status); }
                }
                Err(RecvTimeoutError::Timeout) => {}
                Err(RecvTimeoutError::Disconnected) => return done(self),
            }
            // housekeeping (journaled as a TIMER: the executor's expiries and statuses, the ledger's timers, status lines)
            let t = clock();
            if t.saturating_sub(self.last_hk_t) >= 100_000_000 { self.queue_now = rx.len(); self.timers_at(t, TIMER_HK, status); }
        }
    }

    fn housekeeping(&mut self, now: u64, status: &mut dyn FnMut(&str)) {
        self.last_hk_t = now;
        // WP-05: the executor's timers (in-flight expiry, the status cross-checks, the blockhash expiries) and the
        // crowding map's window
        let tip = self.tip_slot();
        if let Some(x) = self.exec.as_mut() { x.tick(now, &self.sendview, tip); }
        self.ledger_tick(now, false);
        self.activity.expire(now);
        // finish opportunities whose watch window ended
        let due: Vec<u64> = self.opps.values().filter(|o| o.deadline <= now).map(|o| o.id).collect();
        for id in due { self.finish_opp(id); }
        // forget old signatures
        while let Some(&(t, k)) = self.sig_order.front() {
            if now.saturating_sub(t) < SIG_KEEP_NS { break; }
            self.sig_order.pop_front();
            if let Some(s) = self.sigs.remove(&k) { self.write_txarr(k, &s); if s.trigger.is_some() { self.write_arrivals(&s); } }
        }
        while let Some(&(t, s)) = self.poh_order.front() { if now.saturating_sub(t) < 180_000_000_000 { break; } self.poh_order.pop_front(); self.poh.remove(&s); }
        // a trigger with no outcome after 5 s failed on chain (or never landed): a miss for its signer, but only when the
        // state was available the whole time (I-5: during an outage no update can credit it; cmp2 wrote ~3,430 false
        // misses). Its own status (an executed feed) decides it earlier when known
        self.refresh_health(now);
        let expired: Vec<([u8; 64], u64)> = self.trig_pending.iter().filter(|(_, v)| now.saturating_sub(v.1) >= TRIG_KEEP_NS).map(|(k, v)| (*k, v.1)).collect();
        let mut expired = expired;
        expired.sort();
        for (k, t0) in expired {
            if self.state.down_since_or_after(t0) { self.trig_pending.remove(&k); self.count("signer_miss_unknown"); }
            else { self.signer_outcome(&k, false); self.count("signer_miss"); }
        }
        // hints whose transaction never committed (failed, or its writes never came)
        while let Some(&(t, s)) = self.hint_order.front() {
            if now.saturating_sub(t) < HINT_KEEP_NS { break; }
            self.hint_order.pop_front();
            if let Some(h) = self.hints.remove(&s) { self.count_n("pred_not_committed", h.len() as u64); }
        }
        while self.recent.front().is_some_and(|d| now.saturating_sub(d.t) >= RECENT_KEEP_NS || self.recent.len() > RECENT_MAX) { self.recent.pop_front(); }
        if now.saturating_sub(self.last_drift_t) > DRIFT_EVERY_NS { self.last_drift_t = now; self.follow_dlmm(); }
        self.check_tier_a(now);
        // the lag SLO, once a minute
        if let Some((m, act)) = self.slo.tick(now) {
            if !m.ok {
                self.count("lag_slo_breach");
                self.rec.event("lag_slo_breach", "state", None, json!({ "p50_ms": m.p50_ms, "p90_ms": m.p90_ms, "n": m.n, "breaches_in_row": m.breaches_in_row,
                    "action": self.slo.action }));
            }
            match act {
                SloAct::Shadow => if let Some(g) = &self.gate {
                    if let Ok(true) = g.shadow("state_slo", &format!("lag SLO breached {} minutes in a row", m.breaches_in_row), false) {
                        self.rec.event("gate_change", "state", None, json!({ "to": "shadow", "reason": "state_slo" }));
                    }
                },
                SloAct::Recover => {
                    self.rec.event("lag_slo_recovered", "state", None, json!({ "good_in_row": m.good_in_row }));
                    if let Some(g) = &self.gate { if g.reason() == "state_slo" && g.resume("lag SLO recovered").is_ok() {
                        self.rec.event("gate_change", "state", None, json!({ "to": "live", "reason": "state_slo recovered" }));
                    } }
                }
                SloAct::None => {}
            }
        }
        if now.saturating_sub(self.last_status_t) > STATUS_EVERY_NS {
            self.last_status_t = now;
            self.journal.tick(now);
            self.save_signer_stats();
            let line = self.write_status(self.queue_now);
            status(&line);
            self.write_feedhealth(now_ns());
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
    /// line) or `_now`; percentiles name their window. WP-04 adds `commit`, `forks`, `lag_slo`, `accuracy`, `state`
    /// (I-4) and the health fields
    fn write_status_line(&mut self, queue: usize, stop_reason: Option<&str>) -> String {
        let t = now_ns();
        let (mut lat, mut lat_run) = (serde_json::Map::new(), serde_json::Map::new());
        let exec_lat = self.exec.as_mut().map(|x| &mut x.lat);
        for v in self.lat.iter_mut().chain(exec_lat.into_iter().flat_map(|l| l.iter_mut())) {
            lat.insert(v.name.to_string(), v.take_interval(1e3));
            lat_run.insert(v.name.to_string(), v.run_pct(1e3));
        }
        let tip = self.tip_slot();
        let commit_lag = self.commit_lag.take_interval(1e6);
        let lag_by: serde_json::Map<String, Value> = WSrc::ALL.iter().zip(self.commit_lag_src.iter_mut()).map(|(w, s)| (w.as_str().to_string(), s.take_interval(1e6))).collect();
        let p = &mut self.sp;
        let cnt = |k: &str| self.counts.get(k).copied().unwrap_or(0);
        let d = |k: &str| cnt(k).saturating_sub(p.counts.get(k).copied().unwrap_or(0));
        let counts_delta: serde_json::Map<String, Value> = self.counts.iter().filter_map(|(k, v)| {
            let x = v - p.counts.get(k).copied().unwrap_or(0);
            (x > 0).then(|| (k.to_string(), json!(x)))
        }).collect();
        let (exec, mut money) = match self.exec.as_ref() { Some(x) => x.status_v2(&mut self.exec_prev), None => (Value::Null, Value::Null) };
        // WP-07: money is the ledger's (chain truth); the executor's own counters are `money.bot`, diagnostics
        if let Some(l) = self.ledger.as_mut() {
            let prov = self.exec.as_ref().map_or(0, |x| x.provisional_failed_fees());
            money = l.money_json(self.t_now, money, prov);
        }
        let st = self.rec.stats();
        let recorder = st.as_ref().map(|st| {
            let dropped_total: serde_json::Map<String, Value> = st.dropped.iter().filter(|(_, n)| *n > 0).map(|(k, n)| (k.clone(), json!(n))).collect();
            let dropped_delta: serde_json::Map<String, Value> = st.dropped.iter().filter_map(|(k, n)| {
                let d = n - p.dropped.get(k).copied().unwrap_or(0);
                (d > 0).then(|| (k.clone(), json!(d)))
            }).collect();
            let nonzero = |v: &[(String, u64)]| -> serde_json::Map<String, Value> { v.iter().filter(|(_, n)| *n > 0).map(|(k, n)| (k.clone(), json!(n))).collect() };
            json!({ "dropped_total": dropped_total, "dropped_delta": dropped_delta, "suppressed_total": nonzero(&st.suppressed),
                "io_errors_total": nonzero(&st.io_errors), "io_lost_total": nonzero(&st.io_lost), "encode_errors_total": nonzero(&st.encode_errors),
                "writers_dead_now": st.writers_dead, "echo_dropped_total": st.echo_dropped,
                "queue_hwm": st.queue_hwm.iter().map(|(q, n)| (q.to_string(), json!(n))).collect::<serde_json::Map<_, _>>() })
        });
        let nz = |x: u64| (x > 0).then_some(x);
        let by_venue: serde_json::Map<String, Value> = self.acc_by_venue.iter().map(|(v, (s, e))| (v.clone(), json!({ "scored": s, "exact": e }))).collect();
        // WP-03b: the chain-fetch service's sections (null without the service). WP-08 (F38): the PoH gauge joins the
        // coverage section, `poh_trigger_pct` with its counts and target in `poh` (beside the service's fields, or alone
        // without the service); attempts reach it from WP-05's attempt writer (`POH_GAUGE.note_attempt`)
        let (chainfetch, mut coverage) = crate::chainfetch::status_sections();
        let poh = crate::feeds::POH_GAUGE.status(&self.feed_counters, t);
        if !coverage.is_object() { coverage = json!({}); }
        coverage["poh_trigger_pct"] = poh["poh_trigger_pct"].clone();
        coverage["poh"] = poh;
        // WP-05: the share of attempts (would-sends included) whose target leader was known (null without an attempt)
        coverage["leader_known_pct"] = self.exec.as_mut().map_or(Value::Null, |x| x.leader_known_pct());
        // WP-05: the blockhash the send checks would use, its age and source; the cached Jito token's age; the target
        // slot's leader known
        let commitment = self.exec.as_ref().map_or("confirmed".to_string(), |x| x.blockhash_commitment().to_string());
        let bh = self.sendview.blockhash(&commitment).map(|b| (tip.saturating_sub(b.slot), b.src.clone()));
        let leaders_ok = (tip > 0).then(|| self.sendview.leader(tip + 1).is_some() || crate::leaders::installed().is_some_and(|b| b.leader(tip + 1).is_some()));
        let token_age = self.exec.as_ref().and_then(|x| x.token_age_s());
        let mut line = json!({ "seq": self.status_lines, "t_ns": t, "interval_ns": t.saturating_sub(p.t), "run_s": t.saturating_sub(self.t_start) as f64 / 1e9,
            "slot": { "processed": nz(self.slots[0].max(self.slot)), "confirmed": nz(self.slots[1]), "finalized": nz(self.slots[2]), "shred": nz(self.shred_slot), "tip": nz(tip) },
            "tip_lag_slots_now": (self.slot > 0 && self.store_slot_max > 0).then(|| self.slot as i64 - self.store_slot_max as i64),
            "send_gate": self.gate.as_ref().map(|g| g.json()),
            "health": { "recorder_ok": st.as_ref().map(|s| s.core_ok), "warmup_ready": self.shut == Shut::Ready, "shut": self.shut.as_str(),
                "state_ok": self.state.ok(self.t_now, self.knobs.max_update_age_ms * 1_000_000), "lag_slo_ok": self.slo.last.as_ref().map(|m| m.ok), "leaders_ok": leaders_ok,
                "blockhash_age_slots_now": bh.as_ref().filter(|_| tip > 0).map(|b| b.0), "blockhash_src_now": bh.map(|b| b.1), "blockhash_commitment": commitment,
                "jito_token_age_s_now": token_age },
            "state": { "connected_now": self.state.connected, "last_update_age_ms_now": self.state.age_ns(self.t_now).map(|a| a / 1_000_000),
                "last_account_age_ms_now": (self.last_account_t > 0).then(|| self.t_now.saturating_sub(self.last_account_t) / 1_000_000),
                "reconnects_total": self.state.reconnects, "resnapshots_total": self.state.resnapshots, "messages_total": self.state.msgs,
                "unavailable_total": self.state.down_total, "down_since_ns": self.state.down_since, "last_error": self.state.last_error,
                "tier_a_now": self.tier_a.len(), "tier_a_complete": self.tier_a_complete, "store_slot_now": nz(self.store.stream_slot_max),
                "resync_now": self.resync.as_ref().map(|r| {
                    let j = r.job.and_then(|j| self.reads.job(j));
                    json!({ "why": r.why, "since_ns": r.t_connect, "resume_slot": r.floor, "accounts": r.n_keys, "chunks": j.map(|j| j.chunks.len()),
                        "chunks_done": j.map(|j| j.n_done()), "behind": r.behind, "failed": r.failed })
                }),
                "unverified_now": self.unverified.len(), "reads_inflight_now": self.reads.inflight(), "reads_pending_now": self.reads.pending() },
            "queue": { "engine_now": queue, "engine_hwm_delta": self.queue_hwm.max(queue) },
            "store": { "accounts_now": self.store.len(), "updates_total": self.store.updates, "updates_delta": self.store.updates - p.updates,
                "stale_total": self.store.stale_dropped, "stale_delta": self.store.stale_dropped - p.stale, "kept_below_total": self.store.kept_below,
                "pending_groups_now": self.tracker.pending_groups() },
            "commit": { "groups_delta": d("commit_complete") + d("commit_superseded") + d("commit_timeout_unknown") + d("commit_timeout_quiescent") + d("commit_fork_dropped"),
                "by_w_src_delta": { "tx-stream": d("commit_w_tx_stream"), "shred": d("commit_w_shred"), "unknown": d("commit_w_unknown") },
                "complete_delta": d("commit_complete"), "superseded_delta": d("commit_superseded"), "timeout_unknown_delta": d("commit_timeout_unknown"),
                "timeout_quiescent_delta": d("commit_timeout_quiescent"), "fork_dropped_delta": d("commit_fork_dropped"), "late_member_delta": d("commit_late_member"),
                "torn_suspect_delta": d("torn_suspect"), "w_after_resolve_total": self.tracker.w_after_resolve, "lag_ms": commit_lag, "lag_ms_by_w_src": lag_by },
            "forks": { "abandoned_slots_delta": d("fork_abandoned_slot"), "dead_slots_delta": d("fork_dead_slot"), "versions_dropped_delta": d("fork_versions_dropped"),
                "refetch_delta": d("fork_refetch"), "fork_priced_delta": d("fork_priced"), "late_version_delta": d("fork_late_version"),
                "contested_now": self.forks.contested_now(), "root_now": nz(self.forks.root) },
            "lag_slo": { "window": "minute", "p50_ms": self.slo.last.as_ref().and_then(|m| m.p50_ms), "p90_ms": self.slo.last.as_ref().and_then(|m| m.p90_ms),
                "ok": self.slo.last.as_ref().map(|m| m.ok), "breaches_in_row": self.slo.breaches_in_row, "good_in_row": self.slo.good_in_row, "action": self.slo.action },
            "accuracy": { "scored_delta": d("pred_scored"), "exact_delta": d("pred_exact"), "pre_state_unknown_delta": d("pred_pre_state_unknown"), "by_venue": by_venue,
                "queue_now": self.acc_queue.len(), "overflow_total": cnt("pred_queue_overflow"), "action": "log" },
            "alts": { "cached_now": self.alts.len(), "bytes_now": self.alts.bytes(), "evicted_delta": d("alt_evicted"), "refetch_delta": d("alt_refetch"),
                "fetch_calls_total": self.io.as_ref().and_then(|io| io.alt_fetch.get()).map(|f| f.stats.calls.load(std::sync::atomic::Ordering::Relaxed)),
                "fetch_tables_total": self.io.as_ref().and_then(|io| io.alt_fetch.get()).map(|f| f.stats.tables.load(std::sync::atomic::Ordering::Relaxed)),
                "waiting_txs_now": self.alts.waiting_txs(), "fetching_now": self.alts.inflight(),
                "pending_retries_now": self.alts.pending_retries(), "gave_up_now": self.alts.gave_up(), "retries_delta": d("alt_retry"), "gave_up_delta": d("alt_gave_up"),
                "learned_delta": d("alt_learned") },
            "opps_open_now": self.opps.len(), "ata_misses_total": self.ata.misses.get(),
            "counts_total": self.counts, "counts_delta": counts_delta,
            "latency": lat, "latency_run": lat_run,
            "exec": exec, "money": money, "recorder": recorder, "chainfetch": chainfetch, "coverage": coverage,
            // FT-000 (S1-1): each provider's budget and every role's use of it since the previous line
            "rpc_budget": crate::rpc::Registry::global().budget_json("status_budget") });
        if let Some(r) = stop_reason { line["stop_reason"] = json!(r); }
        // WP-20: the alerts' counters (atomics only; null without alerts)
        line["alerts"] = crate::alerts::status();
        p.t = t;
        p.counts = self.counts.clone();
        p.updates = self.store.updates;
        p.stale = self.store.stale_dropped;
        if let Some(st) = &st { p.dropped = st.dropped.iter().cloned().collect(); }
        self.queue_hwm = queue;
        self.rec.json(rec::STATUS, line);
        self.status_lines += 1;
        let c = |k: &str| self.counts.get(k).copied().unwrap_or(0);
        let state = match self.shut { Shut::StateUnavailable => " | STATE UNAVAILABLE", Shut::Resync => " | re-reading the state", Shut::Warmup => " | warm-up", Shut::Ready => "" };
        format!("slot {} queue {} | txs {} triggers {} groups {} decisions {} opps {} | alt: waits {} learned {} still waiting {}{state}", self.tip_slot(), queue,
            c("tx_first"), c("trigger"), self.tracker.pending_groups(), c("evaluation"), c("state_opportunity"), c("alt_wait"), c("alt_learned"), self.alts.waiting_txs())
    }

    // ---------------------------------------------------------------- transactions

    fn on_tx(&mut self, a: Arrival, t_engine: u64) {
        if a.tx.loaded.is_some() && !a.tx.lookups.is_empty() { self.learn_alts(&a.tx); }
        let k = sig8(&a.tx.sig);
        let f = (a.feed as usize).min(MAX_FEEDS - 1);
        if let Some(x) = self.exec.as_mut() { x.on_arrival(&a.tx.sig, a.feed, a.t_rx); }
        if let Some(p) = a.poh { if !self.poh.contains_key(&a.tx.sig) { self.poh.insert(a.tx.sig, p); self.poh_order.push_back((t_engine, a.tx.sig)); } }
        // the unexecuted feeds' newest slot: the tip while the state stream is down (I-4); a slot far ahead of what is
        // known is not believed
        if a.executed.is_none() && a.slot > self.shred_slot {
            let known = self.slot.max(self.store.stream_slot_max).max(self.shred_slot);
            if known == 0 || a.slot <= known + 1_000 {
                self.shred_slot = a.slot;
                if self.shut == Shut::StateUnavailable && a.slot > self.slot { crate::send::tpu::SLOT.store(a.slot, std::sync::atomic::Ordering::Relaxed); }
            }
        }
        if let Some(s) = self.sigs.get_mut(&k) {
            if s.arr[f] == 0 { s.arr[f] = a.t_rx.max(1); }
            if a.t_rx < s.first_t { s.first_t = a.t_rx; s.first_feed = a.feed; }
            if a.executed.is_none() && (s.first_unexec_t == 0 || a.t_rx < s.first_unexec_t) { s.first_unexec_t = a.t_rx; }
            // a later copy from an executed feed: the transaction's own status
            if let Some(ok) = a.executed { self.on_executed(&a, ok); }
            return;
        }
        let mut arr = [0u64; MAX_FEEDS];
        arr[f] = a.t_rx.max(1);
        let first_unexec_t = if a.executed.is_none() { a.t_rx } else { 0 };
        self.sigs.insert(k, SigInfo { first_t: a.t_rx, first_feed: a.feed, first_unexec_t, arr, trigger: None, slot: a.slot });
        self.sig_order.push_back((t_engine, k));
        self.count("tx_first");
        self.process(a, t_engine);
    }

    /// An executed feed's copy of a transaction already seen (the PumpSwap transaction stream): its status settles its
    /// signer's pending trigger (I-5: the transaction's own status, not the 5 s guess), a failed one drops its hints,
    /// and a successful one's write set is registered as authoritative (`tx-stream`)
    fn on_executed(&mut self, a: &Arrival, ok: bool) {
        if self.trig_pending.contains_key(&a.tx.sig) { self.signer_outcome(&a.tx.sig, ok); self.count(if ok { "signer_ok_tx" } else { "signer_miss_tx" }); }
        if !ok {
            if let Some(h) = self.hints.remove(&a.tx.sig) { self.count_n("pred_trigger_failed", h.len() as u64); }
            return;
        }
        // an executed copy carries the addresses its lookups loaded (the transaction's meta)
        let keys = match a.tx.resolve(|_| None) { Some(k) => k, None => match self.resolve_lookups(&a.tx) { Ok(k) => k, Err(_) => return } };
        let w = self.write_set(&a.tx, &keys);
        if !w.is_empty() {
            let rs = self.tracker.register(a.tx.sig, w, WSrc::TxStream, self.t_now);
            self.on_resolutions(rs);
        }
    }

    /// W(T): the transaction's writable accounts that are parts of watched pools. FT-000 (S1-8): not a PumpSwap pool's
    /// mint. A transaction marks a mint writable without writing it (a swap moves balances, not a mint's supply), and an
    /// account a transaction leaves unchanged sends no update: in FT-000, 628 of the 1,405 groups that waited the full
    /// `commit_timeout_ms` for a missing member missed only mints, and none of the 29,550 groups saw a mint written
    /// together with a pool account or vault (the 3,374 that saw a mint written saw nothing else; 3,245 of them the PUMP
    /// mint). A mint write still joins its transaction's group, or arrives as a late member. A run journaled before this
    /// fix replays without it (`EngineKnobs::wt_skip_pump_mints` false)
    fn write_set(&self, tx: &Tx, keys: &[Pk]) -> Vec<Pk> {
        let skip = self.knobs.wt_skip_pump_mints;
        keys.iter().enumerate().filter(|(i, k)| tx.is_writable(*i) && self.part_pools.get(*k).is_some_and(|ps| !(skip && self.pump_mint(k, ps)))).map(|(_, k)| *k).collect()
    }

    /// whether `k`, a part of the pools `ps`, is a PumpSwap pool's mint (its `extra`)
    fn pump_mint(&self, k: &Pk, ps: &[usize]) -> bool {
        ps.iter().any(|&p| { let m = &self.reg.pools[p]; m.venue == Venue::PumpSwap && m.extra.contains(k) })
    }

    /// resolve lookup tables, then register the write set and look for triggers
    fn process(&mut self, a: Arrival, t_engine: u64) {
        let keys = if !a.tx.lookups.is_empty() && a.tx.loaded.is_none() {
            match self.resolve_lookups(&a.tx) {
                Ok(k) => k,
                Err(missing) => {
                    let mut fetch = Vec::new();
                    match self.alts.need(&missing, (a, t_engine), t_engine, &mut fetch) {
                        Need::Wait => self.count("alt_wait"),
                        Need::Drop(why) => self.count(why),
                    }
                    for f in fetch { self.fetch_alt(f); }
                    self.emit_alt_events();
                    return;
                }
            }
        } else {
            match a.tx.resolve(|_| None) { Some(k) => k, None => { self.count("resolve_failed"); return } }
        };
        let t_resolved = now_ns();
        for l in &a.tx.lookups { self.alts.used(l.table, t_engine); }
        // WP-05 crowding (F6): an arbitrage-like transaction (the rival test) is a candidate until its writes land
        if let Some(signer) = self.arb_like(&a, &keys) { self.activity.candidate(a.tx.sig, signer, t_engine); }
        self.record_rival(&a, &keys);
        // WP-03b tap: an unexecuted transaction with its resolved keys (a D2 candidate when it touches a watched account)
        crate::chainfetch::note_seen(&a, &keys);
        // W(T) for the CommitTracker (item 3): every forwarded transaction, decoded swap or not. An executed feed's
        // successful copy is authoritative; a failed one writes nothing
        let w = self.write_set(&a.tx, &keys);
        if !w.is_empty() && a.executed != Some(false) {
            let src = if a.executed == Some(true) { WSrc::TxStream } else { WSrc::Shred };
            let rs = self.tracker.register(a.tx.sig, w.clone(), src, t_engine);
            self.on_resolutions(rs);
        }
        if a.executed.is_some() && self.trig_pending.contains_key(&a.tx.sig) { self.signer_outcome(&a.tx.sig, a.executed == Some(true)); }
        let swaps = self.decode_swaps(&a.tx, &keys);
        if swaps.is_empty() { return; }
        // a trigger's tables are worth forwarding from every feed from now on
        if !a.tx.lookups.is_empty() {
            let mut tables = self.interest.tables.write().unwrap();
            for l in &a.tx.lookups { tables.insert(l.table); }
        }
        for sw in swaps { self.on_trigger(&a, &sw, t_engine, t_resolved, &w); }
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
        let t_now = self.t_now;
        for l in &tx.lookups {
            let mut entries: Vec<(u8, Pk)> = Vec::with_capacity(l.writable.len() + l.readonly.len());
            for &i in &l.writable { entries.push((i, w[wi])); wi += 1; }
            for &i in &l.readonly { entries.push((i, r[ri])); ri += 1; }
            if self.alts.learn(l.table, &entries, t_now) { learned.push(l.table); }
        }
        for t in learned {
            self.alts.learned(t);
            self.index_alt(t);
            let waiting = self.alts.take_waiters(&t);
            if !waiting.is_empty() { self.count("alt_learned"); }
            for (a, te) in waiting { self.process(a, te); }
        }
        self.emit_alt_events();
    }

    /// a lookup table, fetched on the background runtime (its answer comes back as `Event::Alt`: found, no such account,
    /// or the error). FT-000 (S1-1): through the batched fetcher (`alts::Fetcher`, role `alt`): the tables asked for
    /// while a request waits for its token share the next getMultipleAccounts
    fn fetch_alt(&mut self, table: Pk) {
        let Some(io) = &self.io else { self.offline_fetches.push(("alt", vec![table])); return };
        let p = &self.knobs.alts;
        io.alt_fetch.get_or_init(|| crate::alts::Fetcher::start(io.rpc.with_role(crate::rpc::Role::Alt), &io.rt, io.tx_back.clone(), p.batch_max, p.calls_inflight,
            std::time::Duration::from_millis(p.call_every_ms))).request(table);
    }

    /// a lookup table fetch answered: found tables release their waiting transactions; a failure is retried (I-6)
    fn on_alt(&mut self, table: Pk, a: Answer) {
        let mut fetch = Vec::new();
        let released = self.alts.on_answer(table, a, self.t_now, &mut fetch);
        self.index_alt(table);
        for f in fetch { self.fetch_alt(f); }
        self.emit_alt_events();
        for (a, t_engine) in released { self.process(a, t_engine); }
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

    // ---------------------------------------------------------------- quoting (committed state only)

    /// The unix time and slot DLMM and DAMM v2 are priced at: the Clock sysvar's (item 6); tools without one: the host's
    fn chain_now(&self) -> (i64, u64) {
        match self.store.chain_clock() {
            Some(c) => (c.unix_timestamp, c.slot),
            // the engine's time; an engine that has handled no input yet (`simcheck`'s routes) has only the host's
            None => (if self.t_now > 0 { (self.t_now / 1_000_000_000) as i64 } else { unix_now() }, self.slot),
        }
    }

    /// Pool `m` ready to quote in one direction (`zfo`: spending its token 0), from the store's current versions only
    /// (PLAN WP-04 item 1: there is no other state to read: a prediction is never a priced state), parsed by
    /// arbx-sizing (PLAN-ADDENDUM WP-16, `src/quote.rs`). `skip`: DLMM bin arrays left out (pending or on a contested
    /// slot). Err: why it cannot be quoted (`Why::reason`, MEASUREMENT A.1)
    fn leg_of(&self, m: &PoolMeta, zfo: bool, clock: arbx_sizing::Clock, skip: &[i64], use_: Use) -> Result<quote::Leg<'_>, quote::Why> {
        let arrays = self.store.dlmm_arrays.get(&m.pool).map(|l| l.as_slice()).unwrap_or(&[]);
        let get = |k: &Pk| self.store.get(k);
        let usable = |i: i64| !skip.contains(&i);
        quote::leg(m, zfo, &quote::Src { get: &get, arrays, usable: &usable, clock }, use_)
    }

    /// the DLMM bin arrays of pool `m` a quote must not use now (a pending group writes them, or their slot is contested)
    fn skip_arrays(&self, m: &PoolMeta) -> Vec<i64> {
        if m.venue != Venue::Dlmm { return vec![]; }
        self.store.dlmm_arrays.get(&m.pool).map(|l| l.iter().filter(|(_, k)| {
            self.tracker.is_pending(k) || self.store.get(k).is_some_and(|a| self.forks.is_contested(a.slot)) || self.unverified.contains(k)
        }).map(|(i, _)| *i).collect()).unwrap_or_default()
    }

    /// the size ladder in lamports ([strategy] sizes_sol); its top rung is the size cap (4.2 SOL in Stage 0)
    fn ladder(&self) -> Vec<u64> { self.cfg.sizes_sol.iter().map(|s| (s * LAMPORTS_PER_SOL) as u64).collect() }

    /// One route priced on its two legs (PLAN-ADDENDUM WP-16): arbx-sizing's locator and the ladder's rungs, every
    /// candidate evaluated exactly (`quote::best`), never above the top rung (review WP-04 #5: past the size cap a
    /// decision would describe a trade the executor never sends). Gross is the guard's quote delta (sell output minus
    /// the buy leg's debit). Err: why it could not be quoted
    fn price_route(&self, lb: &quote::Leg, ls: &quote::Leg, pb: &PoolMeta, ps: &PoolMeta) -> Result<Priced, &'static str> {
        let sizes = self.ladder();
        let Some(&top) = sizes.iter().max() else { return Err("no_sizes") };
        let lo = sizes.iter().copied().min().unwrap_or(top) / 4;
        let (t, bound) = quote::best_bound(lb, ls, &sizes, lo, top).map_err(quote::Why::reason)?;
        // a round trip returning over twice its input is a broken quote (w5h seg 4: one PumpSwap pool quoted 9.9e12
        // lamports, 663 times): it must not win the pick over the token's real cycles
        if t.profit() > t.x as i64 { return Err("broken_quote"); }
        // DLMM legs: the bins with liquidity the chosen size crosses (the CU table's input); the trip already quoted the rest
        let crossed = |l: &quote::Leg, x: u64| if l.is_dlmm() { l.walk(x).map(|w| w.crossed).map_err(quote::Why::reason) } else { Ok(0) };
        let (c1, c2) = (crossed(lb, t.x)?, crossed(ls, t.mid)?);
        let cu = self.route_cu(pb.venue, c1, ps.venue, c2).0;
        let fee = self.fee_of(t.profit(), cu);
        Ok(Priced { size: t.x, gross: t.profit(), net: t.profit() - fee as i64, cu, crossed: (c1, c2), dlmm_cap_bound: bound == Some(quote::Why::DlmmArray) })
    }

    /// WP-06: a route's CU before any ATA create or close (the measured table's, else today's formula: `CuModel`), and
    /// where it came from
    fn route_cu(&self, bv: Venue, c1: u32, sv: Venue, c2: u32) -> (u64, crate::cu_table::CuSrc) {
        match &self.builder {
            Some(b) => b.cu.route(bv, c1, sv, c2),
            None => (crate::cu_table::fallback(bv, c1, sv, c2), crate::cu_table::CuSrc::Fallback),
        }
    }

    /// WP-06 item 5: the fee a route's gross pays: the base fee plus the tip of its edge (a bundle pays CU price 0). A
    /// journal written before WP-06 replays with its rule: base fee + `cu_price_micro` × CU + `min_tip`
    fn fee_of(&self, gross: i64, cu: u64) -> u64 {
        match &self.builder {
            Some(b) => b.tips.fee(gross),
            None => 5_000 + self.cfg.cu_price_micro * cu / 1_000_000 + self.min_tip,
        }
    }

    /// WP-06 item 7: index a lookup table of the cache under every registry pool it names (the size budget's candidates)
    fn index_alt(&mut self, table: Pk) {
        let Some(entries) = self.alts.get(&table) else { return };
        let pools: Vec<Pk> = entries.iter().flatten().filter(|k| self.reg.by_pool.contains_key(*k)).copied().collect();
        for p in pools {
            let v = self.alt_by_pool.entry(p).or_default();
            if !v.contains(&table) { v.push(table); self.alt_pools.entry(table).or_default().push(p); }
        }
    }

    /// (merge of WP-06 with the FT-000 fixes) the index follows the bounded cache: a table the cache evicted, and does not
    /// hold again, leaves it, so the index never outgrows the cache. Decisions do not change: a table the cache does not
    /// hold is never a candidate (`AltSource::alt` finds none)
    fn unindex_alts(&mut self, evicted: &[Pk]) {
        for t in evicted {
            if self.alts.get(t).is_some() { continue; }
            for p in self.alt_pools.remove(t).unwrap_or_default() {
                if let Some(v) = self.alt_by_pool.get_mut(&p) {
                    v.retain(|x| x != t);
                    if v.is_empty() { self.alt_by_pool.remove(&p); }
                }
            }
        }
    }

    /// every feed's arrival time for one trigger, written once all feeds had 10 s to deliver it
    fn write_arrivals(&mut self, s: &SigInfo) {
        let Some((pool, venue, slot)) = s.trigger else { return };
        let arr: serde_json::Map<String, serde_json::Value> = s.arrivals()
            .map(|(f, t)| (self.feeds.get(f as usize).cloned().unwrap_or_default(), json!(t))).collect();
        self.rec.json(rec::ARRIVALS, json!({ "slot": slot, "pool": b58(&pool), "venue": venue, "source": self.reg.source(&pool),
            "first_feed": self.feeds.get(s.first_feed as usize), "arrivals": arr, "t_first": s.first_t }));
    }

    /// A hint's checks on the store as it is now: quotable, its exact-out input solvable, its own slippage bound met
    /// (else the swap reverts on chain and the pool does not move: 0.05% tolerance for rounding). Ok: the accuracy
    /// monitor's at-hint prediction (arb-lab's measure; the pre-state score comes at T's commit). Err: (skip, counter)
    fn hint_check(&self, i: usize, sw: &PendingSwap) -> Result<Option<Pred>, (&'static str, &'static str)> {
        let m = &self.reg.pools[i];
        let (now, dslot) = self.chain_now();
        // the third party's own swap, as the venue executes it (WP-16: arbx-sizing's exact quote). A state the crate
        // refuses is the skip's reason and counter (`sz_*`, `trigger_sz_*`: review F10); a missing account or a size the
        // venue cannot fill stays `unquotable`
        let skip = |w: quote::Why| w.crate_reason().map_or(("unquotable", "trigger_unquotable"), |r| (r.reason, r.trigger));
        let leg = self.leg_of(m, sw.zero_for_one, quote::clock(dslot, now), &self.skip_arrays(m), Use::Third).map_err(skip)?;
        let fails = if sw.exact_out {
            // the input an exact-out swap spends: the venue's own debit where the crate models the instruction (PumpSwap's
            // `buy`, review F6), else the smallest exact-in size that buys the amount
            let amount_in = match leg.exact_out(sw.amount) {
                Some(r) => Some(r.map_err(skip)?.1.spent),
                None => crate::venues::solve_exact_in(sw.amount, |x| leg.quote(x).ok().map(|q| q.out)),
            };
            let amount_in = amount_in.ok_or(("exact_out_unsolved", "trigger_exact_out_unsolved"))?;
            sw.limit > 0 && amount_in > sw.limit + sw.limit / 2000
        } else {
            let out = leg.quote(sw.amount).map_err(skip)?.out;
            sw.limit > 0 && out.saturating_add(out / 2000) < sw.limit
        };
        if fails { return Err(("will_fail", "trigger_skip_will_fail")); }
        let arrays = self.store.dlmm_arrays.get(&m.pool).cloned().unwrap_or_default();
        let get = |k: &Pk| self.store.get(k);
        let v = accuracy::View { get: &get, arrays: &arrays, now_unix: now, slot: dslot };
        Ok(accuracy::predict(m, &v, sw.zero_for_one, sw.amount, sw.exact_out).ok().map(|p| p.0))
    }

    /// A decoded swap: a hint (PLAN WP-04 item 1), never priced. Its signer check, its slippage check and the accuracy
    /// monitor's shadow prediction run here; triggers.jsonl v2 records it (MEASUREMENT §4.30); its write set was
    /// registered with the CommitTracker by `process`
    fn on_trigger(&mut self, a: &Arrival, sw: &PendingSwap, t_engine: u64, _t_resolved: u64, w: &[Pk]) {
        self.count("trigger");
        if let Some(s) = self.sigs.get_mut(&sig8(&a.tx.sig)) { if s.trigger.is_none() { s.trigger = Some((sw.pool, sw.venue, a.slot)); } }
        let Some(&i) = self.reg.by_pool.get(&sw.pool) else { return };
        let signer = a.tx.fee_payer().copied().unwrap_or_default();
        let stats = self.signer_stats.get(&signer).copied().unwrap_or((0, 0));
        let mut skip: Option<&'static str> = None;
        let mut shadow_pred = false;
        // its signer's statistics follow it, whatever happens below (a failed executed copy settles it at once)
        if a.executed == Some(false) { self.trig_pending.insert(a.tx.sig, (signer, t_engine)); self.signer_outcome(&a.tx.sig, false); }
        else if a.executed == Some(true) { self.trig_pending.insert(a.tx.sig, (signer, t_engine)); self.signer_outcome(&a.tx.sig, true); }
        else { self.trig_pending.insert(a.tx.sig, (signer, t_engine)); }
        // a signer whose triggers mostly fail (at least 4 resolved, under 25% landed): its hint's accuracy check is skipped
        if self.cfg.skip_failing_signers && stats.0 + stats.1 >= 4 && (stats.0 as f64) < 0.25 * (stats.0 + stats.1) as f64 {
            self.count("trigger_skip_signer_fails");
            skip = Some("signer_fails");
        } else if a.executed == Some(false) {
            skip = Some("failed");
            self.count("trigger_failed");
        } else {
            match self.hint_check(i, sw) {
                Err((why, counter)) => { self.count(counter); skip = Some(why); }
                Ok(at_hint) => {
                    let venue = self.reg.pools[i].venue;
                    self.hints.entry(a.tx.sig).or_default().push(Hint { txn: a.tx.sig, pool: i, venue, zfo: sw.zero_for_one, amount: sw.amount,
                        exact_out: sw.exact_out, at_hint, slot: a.slot, t: t_engine, writes: vec![] });
                    self.hint_order.push_back((t_engine, a.tx.sig));
                    shadow_pred = true;
                    self.count("trigger_hint_only");
                }
            }
        }
        // triggers.jsonl v2
        let t_done = now_ns();
        self.lat[LAT_HINT_RX_TO_DONE].push(t_done.saturating_sub(a.t_rx));
        let m = &self.reg.pools[i];
        let st = Stages { rx: a.t_rx, decoded: a.t_decoded, engine: t_engine, resolved: t_engine, decided: t_done };
        let line = json!({
            "sig": sigs58(&a.tx.sig), "feed": self.feeds.get(a.feed as usize), "slot": a.slot, "pool": b58(&m.pool), "venue": m.venue,
            "source": self.reg.source(&m.pool), "zfo": sw.zero_for_one, "amount": sw.amount, "exact_out": sw.exact_out, "executed": a.executed,
            "st": st, "opp": null, "hint_only": true, "signer": b58(&signer), "signer_stats": [stats.0, stats.1], "skip": skip,
            "w_expected": w.iter().map(b58).collect::<Vec<_>>(), "shadow_pred": shadow_pred });
        self.rec.json(rec::TRIGGERS, line);
    }

    /// The executor's turn for opportunity `id` (exec.rs): the send checks on this engine's journaled view (the
    /// blockhash ring's head, block metas, the leader schedule) and its health, the route re-quoted at the size cap, then
    /// a send, a would-send (shadow, dry run, a closed gate: PLAN-ADDENDUM I-7) or a refusal, with its reason.
    ///
    /// What the check read from outside the journal (the SendGate's mode, the leader's kind, the Jito token, the
    /// recorder) is journaled here, on the engine thread, whenever it differs from the last record: an INPUT `gate` with
    /// `src` "decision" and the opportunity's id, right after the input being handled (review WP-03 #3; WP-08 review #18:
    /// the leader's kind)
    fn after_opportunity(&mut self, id: u64) -> crate::exec::Decided {
        let Some(size) = self.opps.get(&id).map(|o| o.size) else { return crate::exec::Decided::reject("no_opportunity") };
        let tip = self.tip_slot();
        let (t, slot) = (self.t_now, self.slot);
        if self.exec.is_none() {
            // no executor: nothing can send
            let why = self.gate_no_executor(id); // ---- WP-09 (review WP-09 #3): journaled at the decision, replayed from the journal
            return crate::exec::Decided::reject(why);
        }
        // ---- WP-09 (review WP-09 "For the WP-05 merge" item 3): a replay's offline executor reads what the run's decision
        // read from outside the journal: the run's records, staged ahead, the last at or before this opportunity (a run
        // stages none)
        let staged = self.staged_records(id);
        let Some(x) = self.exec.as_mut() else { return crate::exec::Decided::reject("no_executor") };
        for (opp, d) in staged { x.stage_seen(opp, id, &d); }
        let sim = x.wants_sim(size, t);
        let inputs = x.inputs(&self.sendview, tip, t);
        let token_ok = !matches!(inputs.token, crate::exec::TokenSeen::Stale);
        // ---- WP-09: the gate's reason is part of what is journaled (a reason that changes while the mode stays, a pause
        // then a lag-SLO shadow, changes every refusal's `gate_shadow:<reason>`)
        // WP-07 (review WP-07 #1): and the ledger's money view the executor decides with (the bankroll cap, the rent cap,
        // equity_unknown / equity_stale): the replay has no ledger, its offline executor applies the run's
        let seen = (inputs.gate, inputs.gate_reason.clone(), inputs.leader.kind, token_ok, inputs.recorder_ok, x.money());
        if self.seen_journaled.as_ref() != Some(&seen) {
            let mut g = x.gate_json();
            g["mode"] = json!(seen.0.as_str());
            g["money"] = seen.5.json();
            // the reason the check read (the gate may have moved on since)
            g["reason"] = json!(Some(&seen.1).filter(|r| !r.is_empty()));
            g["src"] = json!("decision");
            g["opp"] = json!(id);
            g["leader"] = json!({ "slot": inputs.leader.slot, "identity": inputs.leader.identity, "kind": inputs.leader.kind, "kind_src": inputs.leader.kind_src });
            g["jito_token_ok"] = json!(token_ok);
            g["recorder_ok"] = json!(inputs.recorder_ok);
            self.journal.input(self.t_now, InputKind::Gate, Arc::new(g));
            self.gate_journaled = Some(seen.0);
            self.seen_journaled = Some(seen.clone());
        }
        // the size cap: the canary's or `[live] max_size_sol`, under (WP-07) the bankroll's on the ledger's money view (the
        // one source of the bankroll: the view this decision's record journals, so a replay caps as the run did). The route
        // is re-quoted at it (review WP-06 #3: the executor also refuses `size_cap` above it, whoever sized the route)
        let cap = x.size_cap();
        // WP-07: a bankroll that allows nothing (no WSOL, or the liquid SOL under the reserve) is refused as such, not quoted
        let d = if cap == 0 { self.count("send_bankroll_empty"); crate::exec::Decided::reject("bankroll_empty") } else { match self.route_in(id, size.min(cap)) {
            Some(r) => {
                self.decisions = fold(self.decisions, &[b"exec", &id.to_le_bytes(), &r.size.to_le_bytes(), &r.buy.pool, &r.sell.pool, &r.back.to_le_bytes(), &[seen.0 as u8]]);
                let trig = r.trig;
                let global = self.io.is_some();
                let alts = crate::exec::AltSource { tables: self.alts.tables(), by_pool: &self.alt_by_pool };
                let x = self.exec.as_mut().unwrap();
                let d = x.decide(r, &inputs, &self.sendview, &alts, slot.max(tip), t);
                // the poh_trigger_pct gauge, after the fire (the PoH index is shared with the feed threads; review WP-05 #8)
                if d.attempt.is_some() { x.note_poh(trig != [0; 64] && poh_of(&self.poh, &trig, global).is_some()); }
                d
            }
            None => { self.count("send_unquotable"); crate::exec::Decided::reject("build_error:unquotable") }
        } };
        self.decisions = fold(self.decisions, &[b"exec_verdict", &id.to_le_bytes(), d.reason.as_bytes(), &[d.sent.map_or(2, |b| b as u8)]]);
        if let Some(sz) = sim {
            match self.route_in(id, sz) {
                Some(r) => { self.decisions = fold(self.decisions, &[b"sim", &r.size.to_le_bytes(), &r.buy.pool, &r.sell.pool, &r.back.to_le_bytes()]); self.exec.as_mut().unwrap().simulate(r) }
                None => self.count("sim_unquotable"),
            }
        }
        d
    }

    /// `arb-lab simcheck`: one round trip per ordered pool pair at `size`, on the pools as they are (no trigger), spread
    /// over venue combinations, to check the builder on real pools before any decision needs it. At most `max`.
    pub fn probe_routes(&mut self, size: u64, max: usize) -> Vec<crate::exec::RouteIn> {
        let mut pairs: Vec<Vec<usize>> = self.reg.pairs.values().cloned().collect();
        // venue mix first: pairs whose pools span the most venues
        pairs.sort_by_key(|v| std::cmp::Reverse(v.iter().map(|&i| self.reg.pools[i].venue).collect::<HashSet<_>>().len()));
        let mut out = Vec::new();
        let mut combos: HashMap<(Venue, Venue), usize> = HashMap::default();
        let now = self.store.chain_clock().map_or(unix_now(), |c| c.unix_timestamp);
        for v in pairs {
            for &b in &v {
                for &sl in &v {
                    if b == sl || out.len() >= max { continue; }
                    let (pb, ps) = (self.reg.pools[b].clone(), self.reg.pools[sl].clone());
                    let c = combos.entry((pb.venue, ps.venue)).or_default();
                    if *c >= max / 8 + 1 { continue; }   // spread over venue combinations
                    *c += 1;
                    let mint = if pb.t0 == *WSOL { pb.t1 } else { pb.t0 };
                    let (clk, u) = (quote::clock(self.slot, now), route_use(&pb, &ps));
                    let q = self.leg_of(&pb, pb.t0 == *WSOL, clk, &[], u).and_then(|lb| {
                        let ls = self.leg_of(&ps, ps.t0 == mint, clk, &[], u)?;
                        let w1 = lb.walk(size)?;
                        let w2 = ls.walk(w1.out)?;
                        Ok((w1.crossed, w2.crossed))
                    });
                    // a state the crate refuses is counted by its reason (`probe_sz_*`, WP-16 review F10)
                    let (c1, c2) = match q { Ok(c) => c, Err(w) => { self.count(w.crate_reason().map_or("probe_unquotable", |r| r.probe)); continue } };
                    let cu = self.route_cu(pb.venue, c1, ps.venue, c2).0;
                    let id = self.next_id;
                    self.next_id += 1;
                    let st = Stages { rx: 0, decoded: 0, engine: 0, resolved: 0, decided: now_ns() };
                    self.opps.insert(id, Opp { id, decision: u64::MAX, trig: [0; 64], trig_feed: 0, slot: self.slot, st, trig_pool: pb.pool, buy: pb.pool, sell: ps.pool,
                        mint, size, gross: 0, net: 0, cu, crossed: (c1, c2), deadline: u64::MAX, landed: None, touches: Vec::new(), sv: 0, route_age_ms: None,
                        kind: "probe", t_first_shred: None, t_commit: 0, t_priced: 0, parts_skew: None });
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
        let now = self.store.chain_clock().map_or(unix_now(), |c| c.unix_timestamp);
        let (pb, ps) = (self.reg.pools[bi].clone(), self.reg.pools[si].clone());
        let (c1, c2) = {
            let (clk, u) = (quote::clock(self.slot, now), route_use(&pb, &ps));
            let (lb, ls) = (self.leg_of(&pb, pb.t0 == *WSOL, clk, &[], u).ok()?, self.leg_of(&ps, ps.t0 == r.mint, clk, &[], u).ok()?);
            let w1 = lb.walk(r.size).ok()?;
            let w2 = ls.walk(w1.out).ok()?;
            (w1.crossed, w2.crossed)
        };
        let cu = self.route_cu(pb.venue, c1, ps.venue, c2).0;
        let id = self.next_id;
        self.next_id += 1;
        let st = Stages { rx: 0, decoded: 0, engine: 0, resolved: 0, decided: now_ns() };
        self.opps.insert(id, Opp { id, decision: u64::MAX, trig: [0; 64], trig_feed: 0, slot: self.slot, st, trig_pool: pb.pool, buy: pb.pool, sell: ps.pool,
            mint: r.mint, size: r.size, gross: 0, net: 0, cu, crossed: (c1, c2), deadline: u64::MAX, landed: None, touches: Vec::new(), sv: 0, route_age_ms: None,
            kind: "probe", t_first_shred: None, t_commit: 0, t_priced: 0, parts_skew: None });
        let out = self.route_in(id, r.size);
        self.opps.remove(&id);
        out
    }

    /// the accounts a route's two pools are quoted from (pool, vaults, extras, followed DLMM bin arrays)
    pub fn route_accounts(&self, r: &crate::exec::RouteIn) -> Vec<Pk> { self.route_accounts_of(&r.buy, &r.sell) }

    fn route_accounts_of(&self, buy: &crate::venues::PoolMeta, sell: &crate::venues::PoolMeta) -> Vec<Pk> {
        let mut k = Vec::new();
        for m in [buy, sell] {
            k.push(m.pool);
            if m.venue == Venue::Dlmm { if let Some(l) = self.store.dlmm_arrays.get(&m.pool) { k.extend(l.iter().map(|x| x.1)); } }
            else if m.venue != Venue::DammV2 { k.push(m.vault0); k.push(m.vault1); k.extend(m.extra.iter().copied()); }
        }
        k
    }

    /// Everything a build needs for opportunity `id` at `size`: both pools as the store holds them now (the state the
    /// decision priced: it is made in the same input), our legs at that size, and for DLMM the bin arrays the quote may use
    /// (the builder names a prefix of them: `quote::dlmm_window`) and where the quote ends. WP-06: the CU the route asks at
    /// this size (the model's) and what an ATA create and close add; whether the wallet holds the mid token's account, its
    /// PumpSwap user volume accumulator exists, each DLMM pair's bitmap extension exists (the store's view where the state
    /// stream follows them: journaled, so a replay builds the same); the store's data sizes of the route's accounts
    fn route_in(&self, id: u64, size: u64) -> Option<crate::exec::RouteIn> {
        let o = self.opps.get(&id)?;
        // the decision's clock (review WP-04 N4: without a Clock sysvar, the engine's time, as `evaluate_pool` priced it,
        // not the host's)
        let (now, dslot) = self.chain_now();
        let (bi, si) = (*self.reg.by_pool.get(&o.buy)?, *self.reg.by_pool.get(&o.sell)?);
        let (pb, ps) = (&self.reg.pools[bi], &self.reg.pools[si]);
        let (clk, u) = (quote::clock(dslot, now), route_use(pb, ps));
        let (skip_b, skip_s) = (self.skip_arrays(pb), self.skip_arrays(ps));
        let (lb, ls) = (self.leg_of(pb, pb.t0 == *WSOL, clk, &skip_b, u).ok()?, self.leg_of(ps, ps.t0 == o.mint, clk, &skip_s, u).ok()?);
        // the legs at `size` (WP-16: arbx-sizing's exact quotes; a DLMM leg's walk ends where the builder names arrays up to)
        let wb = lb.walk(size).ok()?;
        let ws = ls.walk(wb.out).ok()?;
        let (mid, buy_end, back, sell_end, spent) = (wb.out, wb.end, ws.out, ws.end, wb.spent);
        // the arrays the quote may use (followed, read, not left out): the builder's window is drawn from the same ones
        let live = |p: &crate::venues::PoolMeta, skip: &[i64]| -> Vec<i64> {
            self.store.dlmm_arrays.get(&p.pool).map(|l| l.iter().filter(|(i, k)| self.store.get(k).is_some() && !skip.contains(i)).map(|(i, _)| *i).collect()).unwrap_or_default()
        };
        let data = |p: &crate::venues::PoolMeta| self.store.get(&p.pool).map(|a| a.data.to_vec());
        let trig_feed = if o.trig_feed == u16::MAX { Some("state".to_string()) } else { self.feeds.get(o.trig_feed as usize).cloned() };
        // WP-05: the route's crowding (F6: two counts, review WP-05 #1) and the versions of its accounts it was priced on
        // (attempts `route_in`); whether its trigger has a PoH position is looked up after the decision (review #8)
        let crowding = self.activity.crowding(&pb.pool, &ps.pool, self.t_now);
        let route_keys = self.route_accounts_of(pb, ps);
        let accounts: Vec<(Pk, u64, u64)> = route_keys.iter().filter_map(|k| self.store.get(k).map(|a| (*k, a.slot, a.write_version))).collect();
        // ---- WP-06
        let (cu, cu_src) = self.route_cu(pb.venue, wb.crossed, ps.venue, ws.crossed);
        let cu_ata = self.builder.as_ref().map_or((crate::cu_table::FALLBACK_ATA_CREATE, crate::cu_table::FALLBACK_ATA_CLOSE), |b| b.cu.ata_ops());
        let mint_prog = if o.mint == pb.t0 { pb.t0_prog } else { pb.t1_prog };
        let payer = self.exec.as_ref().map(|x| x.payer());
        let followed = |k: &Pk| self.watch_set.contains(k);
        let mid_held = payer.map(|p| self.ata.get(&p, &o.mint, &mint_prog)).filter(|a| followed(a))
            .map(|a| self.store.get(&a).is_some_and(|x| crate::store::token_account_exists(&x.data)));
        let uva = payer.map(|p| *self.uva_key.get_or_init(|| crate::build::pump_uva(&p))).filter(|a| followed(a))
            .map(|a| self.store.get(&a).is_some_and(|x| !x.data.is_empty()));
        let ext = |p: &crate::venues::PoolMeta| (p.venue == Venue::Dlmm).then(|| p.extra.first().copied()).flatten()
            .filter(|e| self.store.get(e).is_some_and(|a| !a.data.is_empty()));
        let mut sizes: Vec<(Pk, u32)> = route_keys.iter().chain([&pb.t0, &pb.t1, &ps.t0, &ps.t1]).filter_map(|k| self.store.get(k).map(|a| (*k, a.data.len() as u32))).collect();
        sizes.sort();
        sizes.dedup();
        Some(crate::exec::RouteIn { opp: id, trig: o.trig, trig_feed, slot: o.slot,
            st: [o.st.rx, o.st.decoded, o.st.engine, o.st.resolved, o.st.decided], buy: pb.clone(), sell: ps.clone(), buy_data: data(pb)?, sell_data: data(ps)?,
            buy_source: self.reg.source(&pb.pool), sell_source: self.reg.source(&ps.pool), mint: o.mint, size, mid, back, spent,
            gross_at_opp: o.gross, net_at_opp: o.net, cu,
            buy_live: live(pb, &skip_b), sell_live: live(ps, &skip_s), buy_end, sell_end, state_version: o.sv, route_age_ms: o.route_age_ms, decision: o.decision,
            trig_kind: o.kind, t_first_shred: o.t_first_shred, t_commit: o.t_commit, t_priced: o.t_priced, parts_skew: o.parts_skew, crowding, accounts,
            cu_src: cu_src.as_str(), cu_ata, mint_prog, mid_held, uva, buy_ext: ext(pb), sell_ext: ext(ps), sizes })
    }

    /// caps.jsonl: the decided pair's best round trip at each budget in [strategy] budget_caps_sol. Profit rises with
    /// size up to the unconstrained best size, so each cap trades min(best size, cap). A size a pool can't quote (e.g.
    /// past the DLMM bin arrays we follow, or past a DLMM leg's walk budget) is recorded as null. WP-16: the best size is
    /// arbx-sizing's locator over (0, the largest cap], evaluated exactly with the decision's size beside it
    fn record_caps(&self, id: u64, b: &Best, kind: &str, now: i64) {
        if self.cfg.budget_caps_sol.is_empty() || !self.rec.is_on() { return; }
        let (Some(&bi), Some(&si)) = (self.reg.by_pool.get(&b.buy), self.reg.by_pool.get(&b.sell)) else { return };
        let (pb, ps) = (&self.reg.pools[bi], &self.reg.pools[si]);
        let dslot = self.store.chain_clock().map_or(self.slot, |c| c.slot);
        let (clk, u) = (quote::clock(dslot, now), route_use(pb, ps));
        let (Ok(lb), Ok(ls)) = (self.leg_of(pb, pb.t0 == *WSOL, clk, &self.skip_arrays(pb), u), self.leg_of(ps, ps.t0 == b.mint, clk, &self.skip_arrays(ps), u)) else { return };
        let run = |x: u64| -> Option<i64> { quote::round_trip(&lb, &ls, x).ok().map(|t| t.profit()) };
        let max = (self.cfg.budget_caps_sol.iter().cloned().fold(0.0, f64::max) * LAMPORTS_PER_SOL) as u64;
        let best = match quote::best(&lb, &ls, &[b.size.min(max)], 1, max.max(1)) { Ok(t) => (t.x, t.profit()), Err(_) => (b.size, run(b.size).unwrap_or(b.gross)) };
        let fee = b.gross - b.net;
        let caps: Vec<Value> = self.cfg.budget_caps_sol.iter().map(|c| {
            let cap = (c * LAMPORTS_PER_SOL) as u64;
            let x = best.0.min(cap);
            match run(x) { Some(p) => json!([c, x, p - fee]), None => json!([c, x, Value::Null]) }
        }).collect();
        let line = json!({ "id": id, "kind": kind, "slot": self.slot, "buy": b58(&b.buy), "sell": b58(&b.sell), "buy_venue": pb.venue, "sell_venue": ps.venue,
            "mint": b58(&b.mint), "best_size": best.0, "best_net": best.1 - fee, "at_trade_size": [b.size, b.net], "caps": caps, "decision": b.decision });
        self.rec.json(rec::CAPS, line);
    }

    // ---------------------------------------------------------------- pool state

    /// an account update: the store keeps it if newer; the CommitTracker groups it; moves, signer credit, touches
    fn on_account(&mut self, key: Pk, v: Acct, t_engine: u64) {
        let (slot, t, txn, wv, aseq, src) = (v.slot, v.t_recv, v.txn, v.write_version, v.aseq, v.src);
        let stream = src == asrc::GRPC;
        if stream {
            self.state_message(t);
            if t > self.last_account_t { self.last_account_t = t; }
            // the stream's resume slot after a (re)connection starts the re-read (review WP-04 #1)
            if self.resync.as_ref().is_some_and(|r| r.floor.is_none()) { self.resync_floor(slot); }
        }
        // a write of a slot already abandoned (interslot statuses abandon a slot built on an abandoned parent before its
        // writes arrive: review WP-04 #3b) is refused: it would be priced, and nothing would ever drop it
        let refused = self.forks.refuses(slot, v.bank_id);
        if refused { self.count("fork_late_version"); }
        if refused || !self.store.apply(key, v) {
            // a stale update is still stream evidence
            if stream { let rs = self.tracker.stream_time(t, t_engine); self.on_resolutions(rs); self.run_deferred(t); }
            return;
        }
        // a stream write after the (re)connection: this account's state is known again
        if stream && !self.unverified.is_empty() { self.unverified.remove(&key); }
        if let Some(&i) = self.acct_pool.get(&key) {
            // pool accounts only (review WP-03 #6): status `tip_lag_slots_now` measures pool-state staleness
            if slot > self.store_slot_max { self.store_slot_max = slot; }
            if let Some(txn) = txn {
                if self.rec.is_on() {
                    if self.moves_seen.len() > 500_000 { self.moves_seen.clear(); }
                    if self.moves_seen.insert((sig8(&txn), i as u32)) {
                        // moves.log v2: `sig slot pool t_ns acct write_version role` (`-` for an RPC read)
                        let pool = self.reg.pools[i].pool;
                        let role = if key == pool { "pool" } else { "vault" };
                        self.rec.emit(rec::MOVES, Record::enc(move |o| {
                            let _ = write!(o, "{} {slot} {} {t} {} ", sigs58(&txn), b58(&pool), b58(&key));
                            let _ = if wv > 0 { write!(o, "{wv} {role}") } else { write!(o, "- {role}") };
                        }));
                    }
                }
                let pool_key = self.reg.pools[i].pool;
                // WP-05 crowding (F6): an arbitrage-like transaction's write to the pool landed: its signer counts there
                if stream { self.activity.landed(&txn, pool_key, t_engine); }
                if let Some(ids) = self.watch.get(&i).cloned() {
                    for id in ids {
                        let Some(o) = self.opps.get_mut(&id) else { continue };
                        if txn == o.trig { if o.landed.is_none() { o.landed = Some(slot); } continue; }
                        if !o.touches.iter().any(|x| x.1 == txn && x.0 == pool_key) { o.touches.push((pool_key, txn, slot, t)); }
                    }
                }
            }
        }
        // a pending trigger whose transaction wrote a watched account landed
        if let Some(txn) = txn { if self.trig_pending.contains_key(&txn) { self.signer_outcome(&txn, true); } }
        // the CommitTracker: pricing parts are grouped by transaction; any stream message is stream evidence
        if self.part_pools.contains_key(&key) {
            let (rs, late) = self.tracker.on_update(key, txn, slot, wv, aseq, t, t_engine, stream);
            if let Some(l) = late { self.on_late(l); }
            self.on_resolutions(rs);
        } else if stream {
            let rs = self.tracker.stream_time(t, t_engine);
            self.on_resolutions(rs);
        }
        if stream { self.run_deferred(t); }
    }

    /// a slot status of the state stream: the tip, the fork tree, stream health and evidence
    fn on_slot(&mut self, slot: u64, st: i32, t: u64, parent: Option<u64>, bank_id: Option<u64>, t_engine: u64) {
        self.state_message(t);
        // Yellowstone SlotStatus: 0 processed, 1 confirmed, 2 finalized (status.jsonl v2 `slot`); the interslot ones
        // (first-shred, completed, created-bank, dead) feed the fork tree only (a first-shred slot is ahead of every
        // processed one)
        if (0..=2).contains(&st) {
            if slot > self.slot { self.slot = slot; crate::send::tpu::SLOT.store(slot, std::sync::atomic::Ordering::Relaxed); }
            if let Some(x) = usize::try_from(st).ok().and_then(|i| self.slots.get_mut(i)) { if slot > *x { *x = slot; } }
        }
        if st == 0 && self.resync.as_ref().is_some_and(|r| r.floor.is_none()) { self.resync_floor(slot); }
        let ab = self.forks.on_status(slot, parent, st, bank_id);
        if !ab.is_empty() { self.on_abandoned(ab, t_engine); }
        let rs = self.tracker.stream_time(t, t_engine);
        self.on_resolutions(rs);
        self.run_deferred(t);
    }

    // ---------------------------------------------------------------- commit groups (item 3, 5)

    fn on_resolutions(&mut self, rs: Vec<Resolution>) {
        if rs.is_empty() { return; }
        for r in rs { self.on_resolution(r); }
        // the budget tables (caps.jsonl) after every pool of the group was priced: same state, same line
        let (now, _) = self.chain_now();
        for (id, b, _) in std::mem::take(&mut self.caps_pending) { self.record_caps(id, &b, "state", now); }
    }

    /// A commit group resolved: counters, the lag SLO, the accuracy monitor's jobs, the evaluation of every Tier-A pool
    /// it wrote (item 5), and its commits.jsonl line
    fn on_resolution(&mut self, r: Resolution) {
        let g = &r.group;
        self.count(r.outcome.counter());
        self.count(match g.w_src { WSrc::TxStream => "commit_w_tx_stream", WSrc::Shred => "commit_w_shred", WSrc::Unknown => "commit_w_unknown" });
        let t_first_shred = self.first_shred(&g.txn);
        let complete = matches!(r.outcome, Outcome::Complete | Outcome::Superseded);
        let lag = t_first_shred.filter(|_| complete).map(|ts| r.t_resolved.saturating_sub(ts));
        if let Some(l) = lag {
            self.slo.push(l);
            self.commit_lag.push(l);
            self.commit_lag_src[g.w_src as usize].push(l);
        }
        let accounts = g.accounts();
        let pools = self.pools_of(&accounts);
        // the accuracy monitor: T's hints are scored on its pre-state at idle time
        if let Some(hs) = self.hints.remove(&g.txn) {
            if r.outcome == Outcome::ForkDropped { self.count_n("pred_fork_dropped", hs.len() as u64); }
            else {
                for mut h in hs {
                    if self.acc_queue.len() >= self.knobs.accuracy_queue { self.count("pred_queue_overflow"); continue; }
                    h.writes = g.seen.iter().map(|m| (m.acct, m.slot, m.wv)).collect();
                    self.acc_queue.push_back(h);
                }
            }
        }
        let mut evaluated = 0u32;
        let ours = self.exec.as_ref().is_some_and(|x| x.is_ours(&g.txn));
        if r.outcome != Outcome::ForkDropped && self.cfg.state_triggers && !ours {
            let kind = match r.outcome { Outcome::TimeoutQuiescent => "quiescent", Outcome::TimeoutUnknown => "timeout", _ => "commit" };
            let ctx = EvalCtx { kind, txn: Some(g.txn), slot: g.slot, t_first_shred, t_update_recv: g.t_first_update, t_first_engine: g.t_first_engine,
                t_commit: r.t_clock, t_resolved: r.t_resolved, quiet: r.outcome.timed_out(), now_clock: r.t_clock, w_src: g.w_src.as_str(), group: Some(g.id), deferrals: 0 };
            for &p in &pools { evaluated += self.evaluate_pool(p, &ctx); }
        }
        if self.rec.is_on() {
            let spread = g.seen.iter().map(|m| m.t).max().unwrap_or(0).saturating_sub(g.seen.iter().map(|m| m.t).min().unwrap_or(0));
            let rec = CommitRec { group: g.id, txn: Sig58(g.txn), slot: g.slot, w_src: g.w_src.as_str(), w_late: g.w_late, w_expected: g.w.as_ref().map(|w| w.iter().map(|k| B58(*k)).collect()),
                w_seen: g.seen.iter().map(MemberRec::of).collect(), superseded: g.superseded.iter().map(|k| B58(*k)).collect(), t_first_shred,
                t_first_update: g.t_first_update, t_resolved: r.t_resolved, t_commit: r.t_clock, spread_ms: spread as f64 / 1e6, outcome: r.outcome.as_str(),
                resolved_by: r.by.as_str(), lag_ms: lag.map(|l| l as f64 / 1e6), late_members: vec![], torn_suspect_decisions: vec![],
                pools: pools.iter().map(|&p| B58(self.reg.pools[p].pool)).collect(), evaluated, reopened_from: g.reopened_from };
            self.rec.emit(rec::COMMITS, Record::ser(rec));
        }
    }

    /// A late member (F2): the decisions priced on its transaction's pools since its group resolved are `torn_suspect`
    fn on_late(&mut self, l: Late) {
        self.count("commit_late_member");
        // the resolved group's pools, and the late member's own (decisions since then read its pre-T version)
        let mut accts = l.prev_accounts.clone();
        accts.push(l.member.acct);
        let pools = self.pools_of(&accts);
        let torn: Vec<u64> = self.recent.iter().filter(|d| d.t >= l.prev_t_resolved && d.pools.iter().any(|p| pools.contains(p))).map(|d| d.id).collect();
        for id in &torn {
            self.count("torn_suspect");
            self.rec.emit(rec::DECISIONS, Record::ser(json!({ "decision": id, "torn_suspect": true, "txn": sigs58(&l.txn) })));
        }
        self.rec.event("late_member", "commit", None, json!({ "txn": sigs58(&l.txn), "acct": b58(&l.member.acct), "after_ms": l.member.t.saturating_sub(l.prev_t_resolved) as f64 / 1e6,
            "torn_suspect_decisions": torn.len() }));
        let rec = LateRec { group: l.prev_id, txn: Sig58(l.txn), late: true, t: self.t_now, late_members: vec![MemberRec::of(&l.member)], torn_suspect_decisions: torn,
            reopened_group: l.reopened_id };
        self.rec.emit(rec::COMMITS, Record::ser(rec));
    }

    /// evaluations refused `route_not_quiet`, re-run once their routes are quiet (the receive clock at `t`)
    fn run_deferred(&mut self, t: u64) {
        if self.deferred.is_empty() || !self.deferred.iter().any(|d| d.0 <= t) { return; }
        let mut due = Vec::new();
        self.deferred.retain(|d| if d.0 <= t { due.push(d.clone()); false } else { true });
        for (_, p, mut ctx) in due {
            ctx.now_clock = t;
            self.count("evaluation_deferred");
            self.evaluate_pool(p, &ctx);
        }
        let (now, _) = self.chain_now();
        for (id, b, _) in std::mem::take(&mut self.caps_pending) { self.record_caps(id, &b, "state", now); }
    }

    /// Evaluate every route through pool `i` (PLAN WP-04 items 4, 5, 10): each route is checked for readiness on both
    /// pools (present, not pending, consistency-set skew, not on a contested fork), the store's lag, route-level quiet
    /// after a timeout, the chain clock, then priced on committed state. One decisions.jsonl line holds every route; the
    /// best one at or above `min_profit_lamports` is an opportunity, handed to the executor when the store is ready.
    /// Returns how many routes were evaluated
    fn evaluate_pool(&mut self, i: usize, ctx: &EvalCtx) -> u32 {
        // what the warm-up / health gate says at this very input (a first stream message may have just opened it)
        self.refresh_health(self.t_now);
        let id = self.next_decision;
        self.next_decision += 1;
        self.count("evaluation");
        let t_eval = now_ns();
        let m = self.reg.pools[i].clone();
        let others: Vec<usize> = self.reg.pairs.get(&pair_key(&m.t0, &m.t1)).cloned().unwrap_or_default();
        let mint = if m.t0 == *WSOL { m.t1 } else { m.t0 };
        let state_ok = self.state_ok();
        let tip = self.tip_slot();
        let lagging = tip.saturating_sub(self.store.stream_slot_max) > self.knobs.max_tip_lag_slots;
        let clock = self.store.chain_clock();
        let clock_ok = clock.is_some_and(|c| tip.saturating_sub(c.slot) <= self.knobs.clock_max_age_slots);
        // DLMM and DAMM v2 are priced on the chain clock (refused without a fresh one); a CP pool's open-time check reads it
        // too, or the engine's time without one
        let (now, dslot) = match clock { Some(c) => (c.unix_timestamp, c.slot), None => ((self.t_now / 1_000_000_000) as i64, self.slot) };
        let q = self.quiescence_ns();
        let mut quiet_at: Option<u64> = None;
        let mut routes: Vec<RouteRes> = Vec::new();
        {
            let pending = |a: &Pk| self.tracker.is_pending(a);
            let contested = |s: u64| self.forks.is_contested(s);
            let unverified = |a: &Pk| !self.unverified.is_empty() && self.unverified.contains(a);
            let rc = ReadyCtx { pending: &pending, contested: &contested, unverified: &unverified, max_skew: self.knobs.max_part_skew_slots };
            let mut views: HashMap<usize, Result<PoolView, NotReady>> = HashMap::default();
            for &p in std::iter::once(&i).chain(others.iter()) { views.entry(p).or_insert_with(|| self.store.pool_view(&self.reg.pools[p], &rc)); }
            // each pool's leg, per direction and DLMM walk budget, parsed once per evaluation (WP-16 review F7: pool `i` is
            // in all 2(k-1) routes of the evaluation)
            let mut legs_memo: HashMap<(usize, bool, u16), Result<quote::Leg<'_>, quote::Why>> = HashMap::default();
            for &j in &others {
                if j == i { continue; }
                for (buy, sell) in [(i, j), (j, i)] {
                    let (pb, ps) = (&self.reg.pools[buy], &self.reg.pools[sell]);
                    let mut rr = RouteRes { buy, sell, priced: None, reason: "", sv: None, slots: vec![], txns: vec![] };
                    if !state_ok { rr.reason = NotReady::StateUnavailable.reason(); routes.push(rr); continue; }
                    if lagging { rr.reason = NotReady::StoreLagging.reason(); routes.push(rr); continue; }
                    let (vb, vs) = match (&views[&buy], &views[&sell]) {
                        (Ok(a), Ok(b)) => (a, b),
                        (Err(e), _) | (_, Err(e)) => { rr.reason = e.reason(); routes.push(rr); continue; }
                    };
                    let rv = RouteView::of(vb, vs);
                    rr.slots = RouteView::slots(vb, vs);
                    rr.txns = RouteView::txns(vb, vs);
                    if ctx.quiet && rv.t_last_write.saturating_add(q) > ctx.now_clock {
                        rr.reason = NotReady::RouteNotQuiet.reason();
                        let at = rv.t_last_write + q;
                        quiet_at = Some(quiet_at.map_or(at, |x| x.max(at)));
                        rr.sv = Some(rv);
                        routes.push(rr);
                        continue;
                    }
                    rr.sv = Some(rv);
                    let needs_clock = matches!(pb.venue, Venue::Dlmm | Venue::DammV2) || matches!(ps.venue, Venue::Dlmm | Venue::DammV2);
                    if needs_clock && !clock_ok { rr.reason = NotReady::ClockStale.reason(); routes.push(rr); continue; }
                    // both legs parsed by arbx-sizing (WP-16): a state it refuses is the route's reason (`sz_*`)
                    let (clk, u) = (quote::clock(dslot, now), route_use(pb, ps));
                    let budget = match u { Use::Route { dlmm_budget } => dlmm_budget, Use::Third => 0 };
                    let (zb, zs) = (pb.t0 == *WSOL, ps.t0 == mint);
                    let lb = *legs_memo.entry((buy, zb, budget)).or_insert_with(|| self.leg_of(pb, zb, clk, &vb.pending_arrays, u));
                    let legs = lb.and_then(|lb| Ok((lb, (*legs_memo.entry((sell, zs, budget)).or_insert_with(|| self.leg_of(ps, zs, clk, &vs.pending_arrays, u)))?)));
                    match legs.map_err(quote::Why::reason).and_then(|(lb, ls)| self.price_route(&lb, &ls, pb, ps)) {
                        Ok(p) => { rr.reason = "priced"; rr.priced = Some(p); }
                        Err(e) => rr.reason = e,
                    }
                    routes.push(rr);
                }
            }
        }
        let t_priced = now_ns();
        let min_profit = self.cfg.min_profit_lamports as i64;
        // the best priced route, then every route's reason
        let best = routes.iter().enumerate().filter_map(|(k, r)| r.priced.as_ref().map(|p| (k, p.net))).max_by_key(|x| (x.1, std::cmp::Reverse(x.0))).map(|x| x.0);
        for (k, r) in routes.iter_mut().enumerate() {
            if let Some(p) = &r.priced { r.reason = if p.net < min_profit { "below_min_profit" } else if Some(k) == best { "best" } else { "not_best" }; }
        }
        let n_routes = routes.len() as u32;
        self.count_n("route_priced", routes.iter().filter(|r| r.priced.is_some()).count() as u64);
        for r in &routes { if r.priced.is_none() { self.count(reject_counter(r.reason)); } }
        if let Some(at) = quiet_at {
            if ctx.deferrals < MAX_DEFERRALS { let mut c = ctx.clone(); c.deferrals += 1; self.deferred.push((at, i, c)); } else { self.count("evaluation_not_quiet_dropped"); }
        }
        // the state-path stage series (WP-00's, and the v2 commit stages)
        let t_decided0 = now_ns();
        for (k, dv) in [(0, ctx.t_first_engine.saturating_sub(ctx.t_update_recv)), (1, t_decided0.saturating_sub(ctx.t_first_engine)), (2, t_decided0.saturating_sub(ctx.t_update_recv))] {
            self.lat[LAT_STATE_RECV_TO_ENGINE + k].push(dv);
        }
        if let Some(ts) = ctx.t_first_shred { self.lat[LAT_V2].push(ctx.t_update_recv.saturating_sub(ts)); }
        for (k, dv) in [(1, ctx.t_commit.saturating_sub(ctx.t_update_recv)), (2, ctx.t_resolved.saturating_sub(ctx.t_commit)), (3, t_priced.saturating_sub(ctx.t_resolved)),
            (4, t_decided0.saturating_sub(t_priced))] { self.lat[LAT_V2 + k].push(dv); }
        // the decision: an opportunity, the executor's verdict
        let mut opp_id = None;
        let dec: crate::exec::Decided = match best.map(|k| (k, routes[k].priced.clone().unwrap())) {
            None => crate::exec::Decided::reject(routes.first().map_or("no_route", |r| r.reason)),
            Some((_, p)) if p.net < min_profit => crate::exec::Decided::reject("below_min_profit"),
            Some((k, p)) => {
                let r = &routes[k];
                let (buy, sell) = (self.reg.pools[r.buy].pool, self.reg.pools[r.sell].pool);
                let sv = r.sv.as_ref().map_or(0, |v| v.h);
                let route_age_ms = r.sv.as_ref().map(|v| self.t_now.saturating_sub(v.t_last_write) as f64 / 1e6);
                self.count("state_opportunity");
                let oid = self.next_id;
                self.next_id += 1;
                opp_id = Some(oid);
                self.watch.entry(r.buy).or_default().push(oid);
                self.watch.entry(r.sell).or_default().push(oid);
                let st = Stages { rx: ctx.t_update_recv, decoded: ctx.t_update_recv, engine: ctx.t_first_engine, resolved: t_eval, decided: t_decided0 };
                let parts_skew = r.sv.as_ref().map(|v| v.skew);
                self.opps.insert(oid, Opp { id: oid, decision: id, trig: ctx.txn.unwrap_or([0; 64]), trig_feed: u16::MAX, slot: ctx.slot, st, trig_pool: m.pool, buy, sell,
                    mint, size: p.size, gross: p.gross, net: p.net, cu: p.cu, crossed: p.crossed, deadline: self.t_now + self.cfg.outcome_watch_ms * 1_000_000,
                    landed: Some(ctx.slot), touches: Vec::new(), sv, route_age_ms, kind: ctx.kind, t_first_shred: ctx.t_first_shred, t_commit: ctx.t_commit,
                    t_priced, parts_skew });
                self.decisions = fold(self.decisions, &[b"state", &oid.to_le_bytes(), &ctx.txn.unwrap_or([0; 64]), &buy, &sell, &p.size.to_le_bytes(), &p.net.to_le_bytes()]);
                let b = Best { buy, sell, mint, size: p.size, gross: p.gross, net: p.net, decision: id };
                self.caps_pending.push((oid, b, now));
                // the warm-up / health gate (item 8, I-4): recorded, never sent while not ready
                if self.shut != Shut::Ready { crate::exec::Decided::reject(self.shut.as_str()) } else { self.after_opportunity(oid) }
            }
        };
        let t_decided = now_ns();
        self.decisions = fold(self.decisions, &[b"decision", &id.to_le_bytes(), &i.to_le_bytes(), &best.map_or(u64::MAX, |b| b as u64).to_le_bytes(), dec.reason.as_bytes()]);
        // follow-up bookkeeping: the pools priced and the slots read (torn_suspect, fork_priced)
        let priced_pools: Vec<usize> = { let mut v: Vec<usize> = routes.iter().filter(|r| r.priced.is_some()).flat_map(|r| [r.buy, r.sell]).collect(); v.sort_unstable(); v.dedup(); v };
        if !priced_pools.is_empty() {
            let mut slots: Vec<u64> = routes.iter().filter(|r| r.priced.is_some()).flat_map(|r| r.slots.iter().copied()).collect();
            slots.sort_unstable();
            slots.dedup();
            let mut txns: Vec<(u64, u64)> = routes.iter().filter(|r| r.priced.is_some()).flat_map(|r| r.txns.iter().copied()).collect();
            txns.sort_unstable();
            txns.dedup();
            self.recent.push_back(RecentDec { id, t: self.t_now, pools: priced_pools, slots, txns });
        }
        if self.rec.is_on() {
            let bestr = best.map(|k| &routes[k]);
            let rec = DecisionRec {
                decision: id, t_ns: self.t_now, kind: ctx.kind,
                trigger: TriggerRef { txn: ctx.txn.map(Sig58), slot: ctx.slot, t_first_shred: ctx.t_first_shred, pool: B58(m.pool), group: ctx.group },
                routes: routes.iter().map(|r| {
                    let (pb, ps) = (&self.reg.pools[r.buy], &self.reg.pools[r.sell]);
                    RouteRec { buy: B58(pb.pool), sell: B58(ps.pool), mint: B58(mint), buy_venue: pb.venue, sell_venue: ps.venue, size: r.priced.as_ref().map(|p| p.size),
                        gross: r.priced.as_ref().map(|p| p.gross), net: r.priced.as_ref().map(|p| p.net), cu: r.priced.as_ref().map(|p| p.cu),
                        crossed: r.priced.as_ref().map(|p| [p.crossed.0, p.crossed.1]), reason: r.reason,
                        dlmm_cap_bound: self.builder.as_ref().map(|_| r.priced.as_ref().map(|p| p.dlmm_cap_bound)) }
                }).collect(),
                best, sv: bestr.and_then(|r| r.sv.as_ref()).map(|v| SvRec { h: hex16(v.h), slot_max: v.slot_max, wv_max: v.wv_max }),
                route_age_ms: bestr.and_then(|r| r.sv.as_ref()).map(|v| self.t_now.saturating_sub(v.t_last_write) as f64 / 1e6),
                parts_skew_slots: bestr.and_then(|r| r.sv.as_ref()).map(|v| SkewRec { buy: v.skew.0, sell: v.skew.1 }), w_src: ctx.w_src, torn_suspect: false,
                fork_priced: false, band: dec.band.or_else(|| bestr.and_then(|r| r.priced.as_ref()).map(|p| band_of(&self.builder, p.gross))),
                band_at_opp: bestr.and_then(|r| r.priced.as_ref()).map(|p| band_of(&self.builder, p.gross)), crowding: dec.crowding, verdict: dec.verdict,
                reason: dec.reason, ev: dec.ev, rank: dec.rank, attempt: dec.attempt, opp: opp_id, experiments: serde_json::Map::new(),
                stages: StagesRec { t_first_shred: ctx.t_first_shred, t_update_recv: ctx.t_update_recv, t_commit: ctx.t_commit, t_engine: ctx.t_resolved, t_priced, t_decided },
                sent: dec.sent, would_send: dec.would_send, reason_ungated: dec.reason_ungated };
            self.rec.emit(rec::DECISIONS, Record::ser(rec));
        }
        n_routes
    }

    // ---------------------------------------------------------------- forks (item 9)

    /// Slots the fork tree abandoned: their versions leave the rings (each account falls back to its newest canonical
    /// version, or is fetched again), their pending groups are `fork_dropped`, decisions that read them are
    /// `fork_priced`, and the pools they touched are evaluated again (kind `fork`)
    fn on_abandoned(&mut self, ab: Vec<Abandoned>, t_engine: u64) {
        let set: Vec<(u64, Option<u64>)> = ab.iter().map(|a| (a.slot, a.bank_id)).collect();
        let gone = |slot: u64, bank: Option<u64>| set.iter().any(|(s, b)| *s == slot && (b.is_none() || bank.is_none() || *b == bank));
        let dropped = self.store.drop_versions(&gone);
        for a in &ab {
            self.count(if a.why == Why::Dead { "fork_dead_slot" } else { "fork_abandoned_slot" });
            self.rec.event(if a.why == Why::Dead { "fork_dead_slot" } else { "fork_abandoned" }, "forks", None,
                json!({ "slot": a.slot, "why": a.why.as_str(), "by": a.by, "bank_id": a.bank_id }));
        }
        let slots: Vec<u64> = ab.iter().map(|a| a.slot).collect();
        self.on_dropped(dropped, &slots, None, t_engine);
    }

    /// versions dropped by a fork (`slots`) or slot-index `missing` evidence (`txns`: the slot and the transactions its
    /// confirmed block does not hold): refetch what has none left, drop their pending groups, mark the decisions that read
    /// them, evaluate the pools again
    fn on_dropped(&mut self, dropped: Vec<(Pk, usize, bool)>, slots: &[u64], txns: Option<(u64, &[[u8; 64]])>, t_engine: u64) {
        let n: usize = dropped.iter().map(|d| d.1).sum();
        self.count_n("fork_versions_dropped", n as u64);
        let refetch: Vec<Pk> = dropped.iter().filter(|d| d.2).map(|d| d.0).collect();
        if !refetch.is_empty() {
            self.count_n("fork_refetch", refetch.len() as u64);
            if let Some(ar) = &self.acct_rec { ar.mark(crate::rec::accounts::MARK_FORK_REFETCH, &refetch); }
            self.start_read(What::ForkRefetch, refetch);
        }
        if dropped.iter().any(|d| d.0 == *PUMP_FEE_CONFIG) { self.count("fork_pump_cfg"); }
        let mut rs = self.tracker.drop_slots(&|s| slots.contains(&s), t_engine);
        if let Some((slot, sigs)) = txns { rs.extend(self.tracker.drop_txns(slot, sigs, t_engine)); }
        self.on_resolutions(rs);
        // review WP-04 #7: a decision that read a version of a missing (slot, transaction) was priced on a phantom too
        let missing: Vec<(u64, u64)> = txns.map(|(slot, sigs)| sigs.iter().map(|s| (slot, sig8(s))).collect()).unwrap_or_default();
        let priced: Vec<u64> = self.recent.iter().filter(|d| d.slots.iter().any(|s| slots.contains(s)) || d.txns.iter().any(|x| missing.contains(x))).map(|d| d.id).collect();
        for id in priced {
            self.count("fork_priced");
            self.rec.emit(rec::DECISIONS, Record::ser(json!({ "decision": id, "fork_priced": true, "slots": slots })));
        }
        // the pools whose state rolled back: evaluated again on the canonical versions
        let accts: Vec<Pk> = dropped.iter().filter(|d| !d.2).map(|d| d.0).collect();
        let pools = self.pools_of(&accts);
        if self.cfg.state_triggers && !pools.is_empty() {
            let t = self.t_now;
            let ctx = EvalCtx { kind: "fork", txn: None, slot: self.slot, t_first_shred: None, t_update_recv: t, t_first_engine: t, t_commit: t, t_resolved: t, quiet: false,
                now_clock: t, w_src: "unknown", group: None, deferrals: 0 };
            for p in pools { self.evaluate_pool(p, &ctx); }
            let (now, _) = self.chain_now();
            for (id, b, _) in std::mem::take(&mut self.caps_pending) { self.record_caps(id, &b, "fork", now); }
        }
    }

    /// INPUT 8 `slotidx_missing` (WP-03b's slot index): signatures stamped with this slot by an account update are not in
    /// the confirmed block: their versions came from another bank and are dropped
    fn on_slotidx_missing(&mut self, d: &Value) {
        let Some(slot) = d["slot"].as_u64() else { return };
        let sigs: Vec<[u8; 64]> = d["missing"].as_array().into_iter().flatten().filter_map(|s| s.as_str()).filter_map(|s| bs58::decode(s).into_vec().ok()?.try_into().ok()).collect();
        if sigs.is_empty() { return; }
        let dropped = self.store.drop_txn_versions(slot, &sigs);
        self.count("fork_slotidx_missing");
        self.rec.event("fork_abandoned", "forks", None, json!({ "slot": slot, "why": "slotidx_missing", "txns": sigs.len(), "versions": dropped.len() }));
        // the pending groups of those transactions and the decisions that read their versions too, even when no version is
        // held any more (review WP-04 #7)
        self.on_dropped(dropped, &[], Some((slot, &sigs)), self.t_now);
    }

    // ---------------------------------------------------------------- accuracy (item 13)

    /// score up to `n` queued hints against their transaction's pre-state
    fn score_batch(&mut self, n: usize) {
        for _ in 0..n {
            let Some(h) = self.acc_queue.pop_front() else { break };
            self.score(&h);
        }
    }

    fn score(&mut self, h: &Hint) {
        let (res, line) = self.score_line(h);
        match res {
            Scored::NotWritten => { self.count("pred_not_written"); return; }
            Scored::PreStateUnknown => self.count("pred_pre_state_unknown"),
            // a swap the crate does not model is counted by its reason (`pred_sz_*`, WP-16 review F10)
            Scored::Unquotable(why) => self.count(why.and_then(quote::reason_row).map_or("pred_unquotable", |r| r.pred)),
            Scored::Done(exact) => {
                self.count("pred_scored");
                if exact { self.count("pred_exact"); }
                // an exact-out swap solved through exact-in quotes is not the venue's own rounding: scored and recorded,
                // kept out of the per-venue exact rate (WP-16 review F6)
                if accuracy::exact_out_model(h.venue, h.zfo, h.exact_out) == Some("solved") { self.count("pred_exact_out_solved"); }
                else {
                    let e = self.acc_by_venue.entry(format!("{:?}", h.venue)).or_default();
                    e.0 += 1;
                    if exact { e.1 += 1; }
                }
            }
        }
        let mut line = line;
        if let Scored::Done(exact) = res { line["window_exact_pct"] = json!(self.acc_windows.entry(h.pool).or_default().push(exact, ACC_WINDOW)); }
        self.rec.json(rec::PREDICTIONS, line);
    }

    /// The hint's predictions.jsonl v2 line (MEASUREMENT §4.34): its pre-state (each account T wrote, as it was just
    /// before T's write; the others as they were before T's first write), the prediction recomputed there against T's
    /// committed state, and the at-hint comparison (v1 fields) beside it
    fn score_line(&self, h: &Hint) -> (Scored, Value) {
        let m = &self.reg.pools[h.pool];
        let mut accts: Vec<Pk> = consistency_set(m);
        accts.extend(other_parts(m));
        let arrays: Vec<(i64, Pk)> = self.store.dlmm_arrays.get(&m.pool).cloned().unwrap_or_default();
        // what T wrote of this pool (its commit group's members), and T's place in the store's order: its first write
        let mine = |k: &Pk| accts.contains(k) || arrays.iter().any(|a| a.1 == *k);
        if !h.writes.iter().any(|(k, _, _)| mine(k)) { return (Scored::NotWritten, Value::Null); }
        let Some(tkey) = h.writes.iter().map(|(_, slot, wv)| crate::store::vkey(*slot, asrc::GRPC, *wv, 0)).min() else { return (Scored::NotWritten, Value::Null) };
        let mut pre: HashMap<Pk, &Acct> = HashMap::default();
        let mut post: HashMap<Pk, &Acct> = HashMap::default();
        let mut known = true;
        let mut versions = Vec::new();
        let mut needed: Vec<Pk> = accts.clone();
        // the Clock: DLMM and DAMM v2 fees, and (WP-16, arbx-sizing) CPMM / AMM v4 open times
        needed.push(*CLOCK_SYSVAR);
        for k in needed.iter().chain(arrays.iter().map(|a| &a.1)) {
            let wrote = h.writes.iter().any(|(w, _, _)| w == k);
            let tv = if wrote { self.store.version_by_txn(k, &h.txn) } else { None };
            let p = match (wrote, tv) {
                (true, Some(v)) => self.store.version_before(k, v.key()),
                // T wrote it, but the ring no longer holds T's version: its pre-state is lost
                (true, None) => None,
                (false, _) => self.store.version_before(k, tkey),
            };
            let is_array = arrays.iter().any(|a| a.1 == *k);
            match p {
                Some(v) => { pre.insert(*k, v); versions.push(json!({ "acct": b58(k), "aseq": v.aseq, "slot": v.slot, "wv": v.write_version })); }
                None if is_array && !wrote => {}
                None => known = false,
            }
            if let Some(q) = tv.or(p) { post.insert(*k, q); }
        }
        let clock_pre = pre.get(&*CLOCK_SYSVAR).and_then(|a| crate::store::decode_clock(&a.data));
        let (now, slot) = clock_pre.map_or((0, h.slot), |c| (c.1, c.0));
        let mut line = json!({ "sig": sigs58(&h.txn), "venue": m.venue, "pool": b58(&m.pool), "t_ns": self.t_now, "slot": h.slot, "input_src": "decoded",
            "quarantine_action": "log", "exact_out": h.exact_out, "exact_out_model": accuracy::exact_out_model(m.venue, h.zfo, h.exact_out) });
        let getpre = |k: &Pk| pre.get(k).copied();
        let getpost = |k: &Pk| post.get(k).copied();
        let vpre = accuracy::View { get: &getpre, arrays: &arrays, now_unix: now, slot };
        let vpost = accuracy::View { get: &getpost, arrays: &arrays, now_unix: now, slot };
        let mut refused: Option<&'static str> = None;
        let scored = if !known { None } else {
            match accuracy::predict(m, &vpre, h.zfo, h.amount, h.exact_out) {
                Ok((p, _)) => accuracy::actual(m, &vpost, &p).map(|a| (p, a)),
                // a bin array the quote needs has no pre-state in its ring
                Err(accuracy::NoPred::DlmmArray) => { known = false; None }
                // a state arbx-sizing does not model (WP-16): not scored, its reason recorded
                Err(accuracy::NoPred::Refused(why)) => { refused = Some(why); None }
                Err(_) => None,
            }
        };
        if let Some(why) = refused { line["refused"] = json!(why); }
        line["pre_state"] = json!({ "known": known, "versions": versions });
        // the at-hint comparison (arb-lab's measure), against the same committed state
        if let Some(ah) = &h.at_hint {
            if let Some(a) = accuracy::actual(m, &vpost, ah) {
                let (ex, _) = accuracy::compare(ah, &a);
                line["hint"] = json!({ "exact": ex, "err": accuracy::err_of(ah, &a) });
                if let (Value::Object(o), Value::Object(v1)) = (&mut line, accuracy::v1_fields(ah, &a)) { for (k, v) in v1 { o.insert(k, v); } }
            }
        }
        if line.get("hint").is_none() { line["hint"] = json!({ "exact": null, "err": null }); }
        let res = match (known, scored) {
            (false, _) => { line["exact"] = Value::Null; Scored::PreStateUnknown }
            (true, None) => { line["exact"] = Value::Null; Scored::Unquotable(refused) }
            (true, Some((p, a))) => {
                let (exact, bins) = accuracy::compare(&p, &a);
                line["exact"] = json!(exact);
                if let Some((c, x)) = bins { line["dlmm_bins"] = json!({ "checked": c, "exact": x }); }
                if !exact { line["pre_state_pred"] = pred_json(&p); line["committed"] = pred_json(&a); }
                Scored::Done(exact)
            }
        };
        (res, line)
    }

    /// Follow DLMM bin arrays around each pool's active bin; fetch newly followed arrays once over RPC.
    fn follow_dlmm(&mut self) {
        let drift = self.store.dlmm_drift(&self.reg);
        if drift.is_empty() { return; }
        let mut fetch = Vec::new();
        let mut roles = Vec::new();
        for (pool, list) in drift {
            for (_, k) in &list { if self.store.get(k).is_none() { fetch.push(*k); } }
            let pi = self.reg.by_pool.get(&pool).map_or(crate::rec::accounts::NO_POOL, |i| *i as u32);
            roles.extend(list.iter().map(|(_, k)| (*k, crate::rec::accounts::RoleOf { role: crate::rec::accounts::role::DLMM_BIN_ARRAY, pool_index: pi })));
            if let Some(&i) = self.reg.by_pool.get(&pool) {
                for (_, k) in &list {
                    for map in [&mut self.part_pools, &mut self.eval_pools] { let v = map.entry(*k).or_default(); if !v.contains(&i) { v.push(i); } }
                }
            }
            self.store.dlmm_arrays.insert(pool, list);
        }
        // the new arrays' roles (accounts.bin DICT, exec.jsonl `watched`), and a MARK naming them
        if let Some(ar) = &self.acct_rec {
            let new = ar.roles().add(roles);
            ar.mark(crate::rec::accounts::MARK_WATCH_LIST_CHANGED, &new);
        }
        self.publish_watch_list();
        self.start_read(What::DlmmArrays, fetch);
    }

    pub fn publish_watch_list(&self) {
        let Some(io) = &self.io else { return };
        let mut l: Vec<String> = match &self.base_watch { Some(b) => b.iter().map(b58).collect(), None => self.reg.static_accounts().iter().map(b58).collect() };
        for list in self.store.dlmm_arrays.values() { for (_, k) in list { l.push(b58(k)); } }
        let _ = io.watch_list.send(l);
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
            "touches": o.touches.len(), "decision": (o.decision != u64::MAX).then_some(o.decision), "sv": hex16(o.sv) }));
    }
}

// ---------------------------------------------------------------- FT-001: the digest points and the digest's parts

/// What a state digest folds bytes into (`Engine::digest_walk` and the parts' own `digest` functions): one hasher, or
/// the whole digest and one part's at once (`Tee`)
pub trait Fold { fn update(&mut self, b: &[u8]); }

impl Fold for xxhash_rust::xxh3::Xxh3 {
    #[inline]
    fn update(&mut self, b: &[u8]) { xxhash_rust::xxh3::Xxh3::update(self, b) }
}

/// the whole digest and one part's, fed the same bytes (`Engine::digests`: one pass for both)
struct Tee<'a>(&'a mut xxhash_rust::xxh3::Xxh3, &'a mut xxhash_rust::xxh3::Xxh3);

impl Fold for Tee<'_> {
    #[inline]
    fn update(&mut self, b: &[u8]) { self.0.update(b); self.1.update(b); }
}

/// The digest point at the end of the run loop (`Engine::finish`: its digests before and after finish's bookkeeping),
/// and the one at the end of the stop sequence (`arbx run`, after the drain, the stop snapshot, the final reconciliation
/// and the executor's `settle_at_stop`)
pub const DIGEST_RUN_END: &str = "run_end";
pub const DIGEST_STOP_END: &str = "stop_end";

/// What `Engine::stop_sequence` did: the attempts open when it began (None: no executor), whether the drain saw them
/// settle, how long the drain took, the attempts still open at its end (settled `unsettled`)
#[derive(Clone, Debug, PartialEq)]
pub struct StopSeq { pub in_flight: Option<usize>, pub settled: bool, pub drain_ms: f64, pub open: Option<Vec<u64>> }

/// ---- FT-001. The digests at one point: the state digest, the decision digest and each part's digest, in
/// `Engine::digest_walk`'s order; `ms`: how long they took (a real clock read, reported only: the stop waits for them)
#[derive(Clone, Debug, PartialEq)]
pub struct Digests { pub state: u64, pub decision: u64, pub parts: Vec<(&'static str, u64)>, pub ms: f64 }

impl Digests {
    /// `{digest, decision_digest, parts: {name: hex}}` (hex: 16 characters)
    pub fn json(&self) -> Value {
        json!({ "digest": hex16(self.state), "decision_digest": hex16(self.decision), "ms": (self.ms * 1e3).round() / 1e3,
            "parts": self.parts.iter().map(|(k, v)| (k.to_string(), json!(hex16(*v)))).collect::<serde_json::Map<String, Value>>() })
    }

    /// The parts whose digest differs from a recorded `{parts: {name: hex}}` (a part only one side has differs too); None
    /// when the record has no parts (written before FT-001)
    pub fn parts_differ(&self, rec: &Value) -> Option<Vec<String>> {
        let theirs = rec["parts"].as_object()?;
        let mine: std::collections::BTreeMap<&str, String> = self.parts.iter().map(|(k, v)| (*k, hex16(*v))).collect();
        let mut out: Vec<String> = mine.iter().filter(|(k, v)| theirs.get(**k).and_then(|x| x.as_str()) != Some(v.as_str())).map(|(k, _)| k.to_string()).collect();
        out.extend(theirs.keys().filter(|k| !mine.contains_key(k.as_str())).cloned());
        Some(out)
    }
}

// ---------------------------------------------------------------- WP-09: what a replay needs of the engine (src/replay.rs)

/// ---- WP-09 (review WP-09 #3). The SendGate as decisions without an executor read it. A run keeps the reason it
/// journaled last (a decision whose reason differs writes an INPUT 3 `src` "decision" record). A replay stages the run's
/// records in `script` (`journal::replay` reads them ahead of the input whose handling made the decision), and each is
/// applied at its opportunity
#[derive(Default)]
pub struct GateSeen {
    last: Option<String>,
    /// (opportunity id, the run's record: the gate a decision without an executor read, or everything an executor's
    /// decision read from outside the journal, `exec::Seen`)
    pub script: VecDeque<(u64, Arc<Value>)>,
}

/// One route priced on the store as a decision prices it (`Engine::quote_route`)
#[derive(Clone, Debug, PartialEq)]
pub struct RouteQuote {
    pub size: u64,
    pub mid: u64,
    pub back: u64,
    /// what the buy leg debits (WP-16: `gross` = `back` − `spent`, the guard's quote delta)
    pub spent: u64,
    pub gross: i64,
    pub fee: u64,
    pub net: i64,
    pub cu: u64,
    pub crossed: (u32, u32),
    pub buy_end: Option<i32>,
    pub sell_end: Option<i32>,
}

impl Engine {
    /// ---- WP-09. The run's decision-point records staged for opportunities up to `id` (a replay's; a run stages none),
    /// taken in order
    fn staged_records(&mut self, id: u64) -> Vec<(u64, Arc<Value>)> {
        let mut out = Vec::new();
        while self.gate_seen.script.front().is_some_and(|(o, _)| *o <= id) { if let Some(x) = self.gate_seen.script.pop_front() { out.push(x); } }
        out
    }

    /// ---- WP-09 (review WP-09 #3). The reason of a decision without an executor: `no_executor` while the SendGate
    /// allows sends, else `gate_<mode>:<reason>`. A run reads its live gate (a pause from the control socket closes it at
    /// once) and journals what it read, as the executor's send checks journal theirs: an INPUT 3 `src` "decision" record
    /// `{mode, reason, detail, since_ns, sticky, src, opp, executor: false, why}` with the opportunity's id, right after
    /// the input being handled, whenever the reason differs from the last one journaled. A replay applies the run's
    /// records first (`gate_seen.script`)
    fn gate_no_executor(&mut self, id: u64) -> String {
        for (_, d) in self.staged_records(id) { self.gate = crate::rec::journal::gate_of(&d); }
        let why = self.gate.as_ref().filter(|g| !g.allows()).map_or("no_executor".to_string(), |g| format!("gate_{}:{}", g.mode().as_str(), g.reason()));
        if self.gate_seen.last.as_deref() != Some(why.as_str()) {
            let mut g = self.gate.as_ref().map_or_else(|| json!({ "mode": null }), |g| g.json());
            g["src"] = json!("decision");
            g["opp"] = json!(id);
            g["executor"] = json!(false);
            g["why"] = json!(why);
            self.journal.input(self.t_now, InputKind::Gate, Arc::new(g));
            self.gate_seen.last = Some(why.clone());
        }
        why
    }

    /// ---- WP-09 (review WP-09 #6), FT-001. A digest point: the digests now, each part's too (`digests`), as an
    /// events.jsonl `engine_digests` record and journaled right here as INPUT 14 `digest_point` (at the engine time of the
    /// last record handled), so that a replay digests at exactly this point of the journal whatever the run journaled
    /// after it. FT-001 p1: the run digested at the end of its loop (`finish`), then journaled 0.209 s of its stop
    /// sequence (the drain's inputs and housekeeping), which the replay applied before it digested: the decision digests
    /// agreed and the state digests did not. `run_end` (`finish`) carries `before_finish` too, the digests once the
    /// loop's last record was handled (finish's bookkeeping then empties the opportunities and the signature windows);
    /// `stop_end` is the end of the stop sequence. The engine's and the executor's counters ride along (`counts`: a
    /// replay names the counters that differ). Returns the digests now
    pub fn digest_point(&mut self, point: &'static str, before: Option<&Digests>) -> Digests {
        let now = self.digests();
        let mut v = now.json();
        v["point"] = json!(point);
        v["t_engine"] = json!(self.t_now);
        v["decisions"] = json!(self.next_decision);
        v["opportunities"] = json!(self.next_id);
        if let Some(b) = before { v["before_finish"] = b.json(); }
        v["counts"] = self.counts_json();
        let v = Arc::new(v);
        self.journal.input_sized(self.t_now, InputKind::DigestPoint, v.clone(), 8_192);
        self.rec.event("engine_digests", "engine", None, (*v).clone());
        now
    }

    /// ---- FT-001. The engine's and the executor's counters, `{engine: {name: n}, exec: {name: n} | null}` (a digest
    /// point's `counts`)
    pub fn counts_json(&self) -> Value {
        let sorted = |m: &HashMap<&'static str, u64>| -> Value { Value::Object(m.iter().map(|(k, n)| (k.to_string(), json!(n))).collect()) };
        json!({ "engine": sorted(&self.counts), "exec": self.exec.as_ref().map(|x| sorted(&x.counts)) })
    }

    /// ---- WP-09 (review WP-09 #10). Route (buy, sell) of `mint` priced at `size` on the store as it is, as a decision
    /// prices it: `route_in`'s legs (the Clock sysvar's unix time and slot, else the engine's time; the DLMM bin arrays a
    /// decision leaves out, left out) and `price_route`'s CU estimate and fee rule (5,000 + `cu_price_micro` × CU / 10^6
    /// + the run's `min_tip`). `arbx quote` and `--reprice-sizes` price with it. Err: why it does not quote
    pub fn quote_route(&self, buy: &Pk, sell: &Pk, mint: &Pk, size: u64) -> Result<RouteQuote, &'static str> {
        let (lb, ls, pb, ps) = self.quote_legs(buy, sell, mint)?;
        // the legs at `size` as `route_in` walks them (WP-16: arbx-sizing's exact quotes; a state the crate refuses is its
        // `sz_*` reason); gross is the guard's quote delta, the sell output minus the buy leg's debit, as a decision's
        let wb = lb.walk(size).map_err(quote::Why::reason)?;
        let ws = ls.walk(wb.out).map_err(quote::Why::reason)?;
        let (c1, c2) = (wb.crossed, ws.crossed);
        let cu = self.route_cu(pb.venue, c1, ps.venue, c2).0;
        let gross = ws.out as i64 - wb.spent as i64;
        let fee = self.fee_of(gross, cu);
        Ok(RouteQuote { size, mid: wb.out, back: ws.out, spent: wb.spent, gross, fee, net: gross - fee as i64, cu, crossed: (c1, c2), buy_end: wb.end, sell_end: ws.end })
    }

    /// ---- WP-16 merge. Route (buy, sell) of `mint` at the size a decision would pick now, at most `cap`: `price_route`'s
    /// search (the ladder's rungs, then arbx-sizing's locator where a rung makes money: `quote::best`), priced as
    /// `quote_route`. `--reprice-sizes opt`
    pub fn quote_route_best(&self, buy: &Pk, sell: &Pk, mint: &Pk, cap: u64) -> Result<RouteQuote, &'static str> {
        let (lb, ls, _, _) = self.quote_legs(buy, sell, mint)?;
        let sizes = self.ladder();
        let lo = sizes.iter().copied().min().unwrap_or(cap) / 4;
        let t = quote::best(&lb, &ls, &sizes, lo, cap).map_err(quote::Why::reason)?;
        self.quote_route(buy, sell, mint, t.x)
    }

    /// both legs of route (buy, sell) of `mint` as `route_in` parses them: the decision's clock (`chain_now`), the DLMM
    /// bin arrays a decision leaves out left out, the route's DLMM walk budget
    fn quote_legs(&self, buy: &Pk, sell: &Pk, mint: &Pk) -> Result<(quote::Leg<'_>, quote::Leg<'_>, &PoolMeta, &PoolMeta), &'static str> {
        let (Some(&bi), Some(&si)) = (self.reg.by_pool.get(buy), self.reg.by_pool.get(sell)) else { return Err("not_in_registry") };
        let (pb, ps) = (&self.reg.pools[bi], &self.reg.pools[si]);
        let (now, dslot) = self.chain_now();
        let (clk, u) = (quote::clock(dslot, now), route_use(pb, ps));
        let lb = self.leg_of(pb, pb.t0 == *WSOL, clk, &self.skip_arrays(pb), u).map_err(quote::Why::reason)?;
        let ls = self.leg_of(ps, ps.t0 == *mint, clk, &self.skip_arrays(ps), u).map_err(quote::Why::reason)?;
        Ok((lb, ls, pb, ps))
    }

    /// ---- WP-09 (review WP-09 #10). Whether a decision would leave account `k` out now: (written by a pending commit
    /// group, its version on a contested slot, not read again since the state stream's last connection)
    pub fn part_flags(&self, k: &Pk) -> (bool, bool, bool) {
        (self.tracker.is_pending(k), self.store.get(k).is_some_and(|a| self.forks.is_contested(a.slot)), self.unverified.contains(k))
    }
}

/// a rejection reason's counter (MEASUREMENT A.7 `reject_<reason>`)
fn reject_counter(reason: &str) -> &'static str {
    match reason {
        "pending_commit" => "reject_pending_commit", "route_not_quiet" => "reject_route_not_quiet", "parts_skewed" => "reject_parts_skewed",
        "store_lagging" => "reject_store_lagging", "account_missing" => "reject_account_missing", "clock_stale" => "reject_clock_stale",
        "fork_pending" => "reject_fork_pending", "state_unavailable" => "reject_state_unavailable", "warmup" => "reject_warmup", "resync" => "reject_resync",
        "unquotable_dlmm_array" => "reject_unquotable_dlmm_array", "unquotable_dlmm_liquidity" => "reject_unquotable_dlmm_liquidity",
        "unquotable_damm" => "reject_unquotable_damm", "unquotable_cp" => "reject_unquotable_cp", "broken_quote" => "reject_broken_quote",
        // arbx-sizing's refusal states (PLAN-ADDENDUM WP-16, `quote::REASONS`)
        r => quote::reason_row(r).map_or("reject_other", |x| x.reject),
    }
}

/// what scoring a hint came to
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
/// A hint's score: `Unquotable` carries the crate's reason when it refused the swap (`refused`, `pred_<reason>`)
enum Scored { NotWritten, PreStateUnknown, Unquotable(Option<&'static str>), Done(bool) }

fn pred_json(p: &Pred) -> Value {
    match p {
        Pred::Cp { r0, r1 } => json!({ "r0": r0.to_string(), "r1": r1.to_string() }),
        Pred::Dlmm { active, bins } => json!({ "active": active, "bins": bins }),
        Pred::Damm { sqrt_price } => json!({ "sqrt_price": sqrt_price.to_string() }),
    }
}

#[derive(Clone, Debug)]
struct Best { buy: Pk, sell: Pk, mint: Pk, size: u64, gross: i64, net: i64, decision: u64 }

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
    const AMM_PROG: &str = "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8";
    const T0: u64 = 1_791_000_000_000_000_000;
    const MS: u64 = 1_000_000;
    /// 1 SOL
    const SOL: u64 = 1_000_000_000;

    /// a Raydium AMM v4 pool account: status 1 (swaps on), fee 25/10,000, no PnL owed
    fn ammv4_pool() -> Arc<[u8]> {
        let mut p = vec![0u8; 752];
        p[0..8].copy_from_slice(&1u64.to_le_bytes());
        p[176..184].copy_from_slice(&25u64.to_le_bytes());
        p[184..192].copy_from_slice(&10_000u64.to_le_bytes());
        p.into()
    }
    fn vault(amount: u64) -> Arc<[u8]> { let mut v = vec![0u8; 165]; v[64..72].copy_from_slice(&amount.to_le_bytes()); v.into() }
    fn clock_data(slot: u64, unix: i64) -> Arc<[u8]> { let mut d = vec![0u8; 40]; d[0..8].copy_from_slice(&slot.to_le_bytes()); d[32..40].copy_from_slice(&unix.to_le_bytes()); d.into() }
    /// an AMM v4 pool `n` on MINT / WSOL
    fn meta(n: u8) -> PoolMeta {
        PoolMeta { venue: Venue::RayAmmV4, pool: [n; 32], t0: MINT, t1: *WSOL, vault0: [n + 10; 32], vault1: [n + 20; 32],
            t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false }
    }

    struct Rig { e: Engine, dir: std::path::PathBuf, rec: Rec }
    impl Drop for Rig { fn drop(&mut self) { self.rec.close(); let _ = std::fs::remove_dir_all(&self.dir); } }

    /// AMM v4 pools on MINT / WSOL (`pools`: (n, SOL in its quote vault; every pool holds 1e15 MINT)), booted at slot 10
    /// (RPC reads), on an offline engine that records into a temp directory, `min_tip` 1,000
    fn rig_with(name: &str, cfg: StrategyCfg, pools: &[(u8, u64)]) -> Rig {
        rig_metas(name, cfg, &pools.iter().map(|(n, sol)| (meta(*n), *sol)).collect::<Vec<_>>())
    }
    /// an AMM v4 pool `n` whose vaults never collide with another pool's keys (for registries of more than 9 pools)
    fn meta_k(n: u8) -> PoolMeta {
        let mut m = meta(n);
        m.vault0 = { let mut k = [n; 32]; k[31] = 200; k };
        m.vault1 = { let mut k = [n; 32]; k[31] = 201; k };
        m
    }
    fn rig_metas(name: &str, cfg: StrategyCfg, pools: &[(PoolMeta, u64)]) -> Rig {
        let mut reg = Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
        let mut store = Store::default();
        for (i, (m, sol)) in pools.iter().enumerate() {
            let m = m.clone();
            reg.by_pool.insert(m.pool, i);
            store.update(m.pool, ammv4_pool(), 10, 1, None);
            store.update(m.vault0, vault(1_000_000_000_000_000), 10, 1, None);
            store.update(m.vault1, vault(sol * SOL), 10, 1, None);
            reg.pools.push(m);
        }
        reg.pairs.insert(pair_key(&MINT, &WSOL), (0..pools.len()).collect());
        let dir = std::env::temp_dir().join(format!("arbx-engine-{name}-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&dir).unwrap();
        let rec = rec::start(rec::Opts { dir: dir.clone(), run: "test".into(), producer: "test".into(), cfg: Default::default(), feeds: vec!["shred".into(), "tx".into()],
            monitor: false, echo: Some(Box::new(std::io::sink())) }).unwrap();
        let mut e = Engine::new_offline(Arc::new(reg), store, cfg);
        e.set_rec(rec.clone());
        e.min_tip = 1_000;
        Rig { e, dir, rec }
    }
    fn rig(name: &str) -> Rig { rig_with(name, StrategyCfg { state_triggers: true, ..StrategyCfg::default() }, &[(1, 1_000), (2, 1_000)]) }

    fn nop() -> impl FnMut(&str) { |_: &str| {} }
    /// a state-stream account update received at `t`, dequeued 10 µs later
    fn acct(e: &mut Engine, key: Pk, data: Arc<[u8]>, slot: u64, t: u64, txn: Option<[u8; 64]>, wv: u64) {
        e.step(Event::Account { slot, pubkey: key, owner: [3; 32], lamports: 1, data, t, txn, write_version: wv, is_startup: false, src: 0, aseq: 0, bank_id: None },
            t + 10_000, &mut nop());
    }
    fn slot_ev(e: &mut Engine, slot: u64, status: i32, parent: Option<u64>, t: u64) {
        e.step(Event::Slot { slot, status, t, parent, dead_error: None, bank_id: None }, t + 10_000, &mut nop());
    }
    /// the stream delivers (slot 11 processed, the Clock at slot 11), and housekeeping finds Tier A complete: ready
    fn make_ready(e: &mut Engine, t: u64) {
        slot_ev(e, 11, 0, Some(10), t);
        acct(e, *CLOCK_SYSVAR, clock_data(11, 1_759_000_000), 11, t, None, 1);
        e.timers(t + 6 * MS, &mut nop());
        assert_eq!(e.shut(), Shut::Ready, "ready after Tier A is complete and the stream delivers");
    }
    fn decisions(r: &Rig) -> Vec<Value> { r.rec.sync(); rec::read_jsonl(&r.dir, "decisions").unwrap_or_default() }
    fn commits(r: &Rig) -> Vec<Value> { r.rec.sync(); rec::read_jsonl(&r.dir, "commits").unwrap_or_default() }
    fn sig(n: u8) -> [u8; 64] { [n; 64] }

    /// a transaction from a shred feed (unexecuted) writing `writable` (a W(T) hint), with an AMM v4 swap of `amount`
    /// lamports of WSOL into pool `swap_pool` when given (a decoded swap: a hint)
    fn shred_tx(s: [u8; 64], writable: &[Pk], swap: Option<(&PoolMeta, u64, bool)>, slot: u64, t: u64) -> Arrival {
        let prog = crate::tx::pk(AMM_PROG);
        let mut keys = vec![SIGNER];
        keys.extend(writable.iter().copied());
        let mut ixs = Vec::new();
        let mut ro = vec![prog];
        if let Some((m, amount, zfo)) = swap {
            // AMM v4 swap_base_in v2 (tag 16): [0] token program [1] amm [2] authority [3] vault0 [4] vault1 [5] user in [6] user out [7] user
            let (tin, tout) = if zfo { (m.t0, m.t1) } else { (m.t1, m.t0) };
            let (uin, uout) = (crate::pda::ata(&SIGNER, &tin, &m.t0_prog), crate::pda::ata(&SIGNER, &tout, &m.t1_prog));
            for k in [uin, uout] { if !keys.contains(&k) { keys.push(k); } }
            for k in [*crate::pda::TOKEN_PROGRAM, [99u8; 32]] { ro.push(k); }
            let n_rw = keys.len();
            let idx = |k: &Pk, keys: &Vec<Pk>, ro: &Vec<Pk>| keys.iter().position(|x| x == k).or_else(|| ro.iter().position(|x| x == k).map(|p| p + n_rw)).unwrap() as u8;
            let accounts = [*crate::pda::TOKEN_PROGRAM, m.pool, [99u8; 32], m.vault0, m.vault1, uin, uout, SIGNER].iter().map(|k| idx(k, &keys, &ro)).collect();
            let mut data = vec![16u8];
            data.extend(amount.to_le_bytes());
            data.extend(0u64.to_le_bytes());
            ixs.push(crate::tx::Ix { program: idx(&prog, &keys, &ro), accounts, data });
        }
        let n_ro = ro.len() as u8;
        keys.extend(ro);
        let tx = Tx { sig: s, num_signers: 1, num_ro_signed: 0, num_ro_unsigned: n_ro, keys, ixs, ..Default::default() };
        Arrival { feed: 0, slot, t_rx: t, t_decoded: t, executed: None, tx, poh: None, raw: Default::default() }
    }
    fn tx_ev(e: &mut Engine, a: Arrival) { let t = a.t_rx; e.step(Event::Tx(a), t + 10_000, &mut nop()); }
    /// the state stream's task: connected (right before a connection's first message) or lost
    fn health(e: &mut Engine, connected: bool, t: u64) {
        e.step(crate::feeds::state_health(connected, 2, 1, (!connected).then(|| "status: 503".into())), t, &mut nop());
    }
    /// Answer the account reads the (offline) engine asked for, as the fetch task would: each account of each chunk (as
    /// `data` says, else as the store holds it; None from both: the node does not have it) at `slot`, then the chunk's
    /// INPUT 11 `fetch`. Returns how many chunks were answered
    fn answer_reads(e: &mut Engine, slot: u64, t: u64, data: &dyn Fn(&Pk) -> Option<Arc<[u8]>>) -> usize {
        let reads = std::mem::take(&mut e.offline_reads);
        let n = reads.len();
        for (i, f) in reads.into_iter().enumerate() {
            let te = t + i as u64 * 10_000;
            let mut missing = Vec::new();
            for k in &f.keys {
                match data(k).or_else(|| e.store.get(k).map(|a| a.data.clone())) {
                    Some(d) => e.step(Event::Account { slot, pubkey: *k, owner: [3; 32], lamports: 1, data: d, t: te, txn: None, write_version: 0, is_startup: false,
                        src: f.what.src(), aseq: 0, bank_id: None }, te + 100, &mut nop()),
                    None => missing.push(b58(k)),
                }
            }
            e.step(Event::Input { kind: InputKind::Fetch, data: Arc::new(json!({ "job": f.job, "chunk": f.chunk, "what": f.what.as_str(), "attempt": f.attempt,
                "ok": true, "slot": slot, "n": f.keys.len(), "missing": missing })) }, te + 5_000, &mut nop());
        }
        n
    }
    /// the account reads asked for fail (an RPC error)
    fn fail_reads(e: &mut Engine, t: u64, err: &str) {
        for f in std::mem::take(&mut e.offline_reads) {
            e.step(Event::Input { kind: InputKind::Fetch, data: Arc::new(json!({ "job": f.job, "chunk": f.chunk, "what": f.what.as_str(), "attempt": f.attempt,
                "ok": false, "err": err, "n": f.keys.len() })) }, t, &mut nop());
        }
    }

    /// PLAN WP-04 item 1 (WP-00 F16 kept): a decoded swap is a hint only: its triggers.jsonl line (opp null, hint_only,
    /// the write set it registered, its signer's statistics), an accuracy check waiting for its commit, the signer's
    /// pending outcome; nothing priced, no opportunity, no prediction anywhere the pricing can read
    #[test]
    fn decoded_swap_is_a_hint_only() {
        let mut r = rig("hint");
        make_ready(&mut r.e, T0);
        let a = meta(1);
        tx_ev(&mut r.e, shred_tx(sig(9), &[a.pool, a.vault0, a.vault1], Some((&a, SOL, false)), 11, T0 + 10 * MS));
        let e = &r.e;
        assert_eq!((e.counter("trigger"), e.counter("trigger_hint_only"), e.counter("state_opportunity"), e.counter("evaluation")), (1, 1, 0, 0));
        assert_eq!(e.hints[&sig(9)].len(), 1, "the accuracy monitor waits for T's commit");
        assert!(e.hints[&sig(9)][0].at_hint.is_some(), "with its at-hint prediction (never a priced state)");
        assert!(e.trig_pending.contains_key(&sig(9)), "signer statistics keep learning");
        assert_eq!(e.tracker.pending_groups(), 0, "registered, no update yet");
        assert_eq!(e.lat.iter().find(|x| x.name == "hint_rx_to_done").unwrap().n(), 1);
        r.rec.sync();
        let t = rec::read_jsonl(&r.dir, "triggers").unwrap();
        assert!(t[0]["opp"].is_null() && t[0]["hint_only"] == json!(true) && t[0]["shadow_pred"] == json!(true) && t[0]["skip"].is_null());
        assert_eq!(t[0]["w_expected"].as_array().unwrap().len(), 3);
        assert_eq!(t[0]["signer_stats"], json!([0, 0]));
    }

    /// skip_failing_signers works on the hint path, and the skipped signer's statistics keep learning (its swaps landing,
    /// credited by a state update stamped with them, let it back in)
    #[test]
    fn failing_signer_is_skipped_and_keeps_learning() {
        let mut r = rig("signer");
        r.e.signer_stats.insert(SIGNER, (0, 4));
        make_ready(&mut r.e, T0);
        let a = meta(1);
        let mut t = T0 + 10 * MS;
        let land = |e: &mut Engine, s: [u8; 64], t: &mut u64| {
            tx_ev(e, shred_tx(s, &[a.pool, a.vault0, a.vault1], Some((&a, SOL, false)), 11, *t));
            for (k, d) in [(a.pool, ammv4_pool()), (a.vault0, vault(999_000_000_000_000)), (a.vault1, vault(1_001 * SOL))] { *t += 100_000; acct(e, k, d, 11, *t, Some(s), *t); }
            *t += 10 * MS;
        };
        land(&mut r.e, sig(21), &mut t);
        assert_eq!((r.e.counter("trigger_skip_signer_fails"), r.e.counter("trigger_hint_only")), (1, 0));
        assert_eq!(r.e.signer_stats[&SIGNER], (1, 4), "its swap landed: credited");
        land(&mut r.e, sig(22), &mut t);
        assert_eq!(r.e.signer_stats[&SIGNER], (2, 4));
        land(&mut r.e, sig(23), &mut t);
        assert_eq!((r.e.counter("trigger_skip_signer_fails"), r.e.counter("trigger_hint_only")), (2, 1), "2 of 6 >= 25%: let back in");
        assert_eq!(r.e.signer_delta[&SIGNER], (3, 0), "this segment's own counts");
    }

    /// The cmp2 "poisoned" pattern (PLAN-ADDENDUM I-8; docs/research/cmp2-shadow-comparison.md §3). In the old bot `leg()`
    /// read `preds`: a decoded swap's prediction stayed until overwritten or 1.5 s old, so when a landed transaction then
    /// moved the pair's OTHER pool, the evaluation priced the first pool at the state the swap would have left, and the
    /// swap failed on chain. In cmp2 62 opportunities (33.76 SOL quoted) were so poisoned; on Gf7sXM (USDC/SOL) the failed
    /// A3uAHtQA (463,419,957,129 raw USDC in, Custom 3012) produced six 3.88 SOL quotes.
    ///
    /// Here the same: a swap of 463,419,957,129 MINT into pool A (decoded, then failed: its executed copy says so, and no
    /// write ever comes), then a small landed transaction on pool B within 1.5 s. The prediction the old path would have
    /// priced is real (priced on it, the route quotes several SOL), but the engine prices A only on its committed state:
    /// the decision is identical to an engine that never saw the swap, and there is no opportunity
    #[test]
    fn a_failed_swaps_prediction_never_prices_the_other_pool() {
        const USDC_IN: u64 = 463_419_957_129;
        let pools = [(1u8, 15_000u64), (2, 15_000)];
        let cfg = StrategyCfg { state_triggers: true, sizes_sol: vec![0.5, 1.0, 2.0, 4.2], ..StrategyCfg::default() };
        let run = |with_hint: bool| -> (Vec<Value>, Engine, Option<Pred>, Rig) {
            let mut r = rig_with(if with_hint { "poison-hint" } else { "poison-plain" }, cfg.clone(), &pools);
            // 3.5M "USDC" against 15,000 SOL in each pool
            for p in [meta(1), meta(2)] { assert!(r.e.store.apply(p.vault0, Acct::rpc(vault(3_500_000_000_000), 10, 1, 1, asrc::RPC_BOOT))); }
            make_ready(&mut r.e, T0);
            let (a, b) = (meta(1), meta(2));
            let mut at_hint = None;
            if with_hint {
                // the decoded swap: USDC into A (zfo: token0 for token1)
                tx_ev(&mut r.e, shred_tx(sig(0xA3), &[a.pool, a.vault0, a.vault1], Some((&a, USDC_IN, true)), 11, T0 + 10 * MS));
                at_hint = r.e.hints[&sig(0xA3)][0].at_hint.clone();
                // its executed copy: failed on chain (no account of A is ever written by it)
                let mut f = shred_tx(sig(0xA3), &[a.pool, a.vault0, a.vault1], Some((&a, USDC_IN, true)), 11, T0 + 11 * MS);
                f.feed = 1;
                f.executed = Some(false);
                tx_ev(&mut r.e, f);
            }
            // 400 ms later a small swap lands on B (its writes, W unknown): B's routes are evaluated
            let t = T0 + 410 * MS;
            acct(&mut r.e, b.vault0, vault(3_499_000_000_000), 12, t, Some(sig(0xB0)), 100);
            acct(&mut r.e, b.vault1, vault(15_004 * SOL), 12, t + 200_000, Some(sig(0xB0)), 101);
            r.e.timers(t + 4 * MS, &mut nop());
            let d = decisions(&r);
            let e = std::mem::replace(&mut r.e, Engine::new_offline(Arc::new(Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(),
                seeds: Default::default(), ours: Default::default() }), Store::default(), StrategyCfg::default()));
            (d, e, at_hint, r)
        };
        let (with, e, at_hint, _r1) = run(true);
        let (without, e0, _, _r2) = run(false);
        // the hint was taken: its signer's miss counted from the transaction's own status, its accuracy check dropped
        assert_eq!((e.counter("trigger_hint_only"), e.counter("signer_miss_tx"), e.counter("pred_trigger_failed")), (1, 1, 1));
        // the decision after B's swap is the same with or without the failed swap
        let strip = |d: &Value| { let mut d = d.clone(); d["stages"] = Value::Null; d["t_ns"] = Value::Null; d["trigger"]["t_first_shred"] = Value::Null; d };
        assert_eq!(with.len(), 1);
        assert_eq!(with.iter().map(strip).collect::<Vec<_>>(), without.iter().map(strip).collect::<Vec<_>>(), "the failed swap changed no price");
        assert_eq!(e.decision_digest(), e0.decision_digest());
        assert_eq!((e.counter("state_opportunity"), with[0]["reason"].as_str()), (0, Some("below_min_profit")), "no gap on committed state");
        let net_committed = with[0]["routes"].as_array().unwrap().iter().filter_map(|r| r["net"].as_i64()).max().unwrap();
        // what the old path priced: A at the failed swap's predicted state
        let Some(Pred::Cp { r0, r1 }) = at_hint else { panic!("an at-hint prediction") };
        let (a, b) = (e.reg.pools[0].clone(), e.reg.pools[1].clone());
        let (ck, u) = (quote::clock(0, 0), route_use(&a, &b));
        // A's buy leg (WSOL in: its token 1, the pc side) at the failed swap's predicted reserves
        let mut la = e.leg_of(&a, a.t0 == *WSOL, ck, &[], u).unwrap();
        let arbx_sizing::AnyLeg::Amm(sa) = &mut la.any else { panic!() };
        sa.r_in = r1 as u64;
        sa.r_out = r0 as u64;
        let lb = e.leg_of(&b, b.t0 == MINT, ck, &[], u).unwrap();
        // USDC into A makes A's MINT cheap: buy it on A (at the predicted state), sell it on B
        let poisoned = e.price_route(&la, &lb, &a, &b).unwrap_or_else(|why| panic!("the poisoned route prices: {why}; {la:?}"));
        eprintln!("cmp2 poisoning pattern: priced on the failed swap's prediction the route quotes {} lamports net at {} lamports; on committed state the best route nets {}",
            poisoned.net, poisoned.size, net_committed);
        assert!(poisoned.net > 1_000_000_000, "priced on the prediction the route quotes {} lamports (cmp2: 3.88 SOL)", poisoned.net);
        assert!(net_committed < 0, "on committed state it loses: {net_committed}");
    }

    /// No pricing on predictions (PLAN WP-04 acceptance): random interleavings of decoded swaps (landing or failing,
    /// before or after state updates, on either pool) never change a single decision: the decision digest and every
    /// decision line equal those of the same state stream without them
    #[test]
    fn hints_never_change_a_decision() {
        let mut rng = 0x5eed_u64;
        let mut next = move |m: u64| { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; rng % m };
        let plan: Vec<(u8, u64, u64, bool, u64)> = (0..40).map(|_| (next(2) as u8 + 1, 995 + next(30), next(3), next(2) == 0, 1 + next(50))).collect();
        let drive = |hints: bool| -> (u64, Vec<Value>) {
            let mut r = rig_with(if hints { "inv-h" } else { "inv-0" }, StrategyCfg { state_triggers: true, ..StrategyCfg::default() }, &[(1, 1_000), (2, 1_000)]);
            make_ready(&mut r.e, T0);
            let mut t = T0 + 10 * MS;
            for (k, (p, sol, wv_extra, hint_first, amount)) in plan.iter().enumerate() {
                let m = meta(*p);
                let other = meta(3 - *p);
                let s = sig(100 + k as u8);
                if hints && *hint_first { tx_ev(&mut r.e, shred_tx(sig(200 + k as u8), &[other.pool, other.vault0, other.vault1], Some((&other, amount * SOL / 10, k % 2 == 0)), 11, t)); }
                for (j, (key, d)) in [(m.vault1, vault(sol * SOL)), (m.vault0, vault(1_000_000_000_000_000 - wv_extra * 1_000))].into_iter().enumerate() {
                    t += 50_000;
                    acct(&mut r.e, key, d, 11 + k as u64 / 8, t, Some(s), 1_000 + 3 * k as u64 + j as u64);
                }
                if hints && !*hint_first { tx_ev(&mut r.e, shred_tx(sig(200 + k as u8), &[m.pool, m.vault0, m.vault1], Some((&m, amount * SOL / 10, k % 3 == 0)), 11, t)); }
                t += 5 * MS;
                r.e.timers(t, &mut nop());
            }
            let d: Vec<Value> = decisions(&r).into_iter().filter(|d| d.get("routes").is_some()).map(|mut d| { d["stages"] = Value::Null; d }).collect();
            (r.e.decision_digest(), d)
        };
        let (h, dh) = drive(true);
        let (z, dz) = drive(false);
        assert!(!dz.is_empty());
        assert_eq!(dh, dz, "hints change no decision");
        assert_eq!(h, z, "nor the decision digest");
    }

    /// S1 (PLAN WP-04 acceptance; the AgmLJBMD split-route torn read): one transaction T writes pool A's vaults and pool
    /// B's vaults, W(T) known from a shred hint; the updates arrive interleaved with another transaction's. No pool is
    /// evaluated until T's group completes: an evaluation in between (another pool's commit) refuses A and B as pending,
    /// and the half-updated state is never priced
    #[test]
    fn s1_a_split_route_is_never_priced_half_updated() {
        let mut r = rig_with("s1", StrategyCfg { state_triggers: true, ..StrategyCfg::default() }, &[(1, 1_000), (2, 1_000), (3, 1_000)]);
        make_ready(&mut r.e, T0);
        let (a, b, c) = (meta(1), meta(2), meta(3));
        let mut t = T0 + 10 * MS;
        // T's write set from a shred feed: A's and B's vaults
        tx_ev(&mut r.e, shred_tx(sig(1), &[a.vault0, a.vault1, b.vault0, b.vault1], None, 12, t));
        t += 15 * MS;
        acct(&mut r.e, a.vault1, vault(1_030 * SOL), 12, t, Some(sig(1)), 10);
        acct(&mut r.e, a.vault0, vault(970_000_000_000_000), 12, t + 1_000, Some(sig(1)), 11);
        assert_eq!(r.e.counter("evaluation"), 0, "A is written but T is not complete");
        assert!(r.e.tracker.is_pending(&b.vault0), "B is in W(T): pending before its update arrives");
        // another transaction U completes on C meanwhile (W known): its evaluation sees A and B pending
        tx_ev(&mut r.e, shred_tx(sig(2), &[c.vault0, c.vault1], None, 12, t + 2_000));
        acct(&mut r.e, c.vault1, vault(1_040 * SOL), 12, t + 3_000, Some(sig(2)), 12);
        acct(&mut r.e, c.vault0, vault(960_000_000_000_000), 12, t + 4_000, Some(sig(2)), 13);
        let d = decisions(&r);
        assert_eq!(d.len(), 1, "U's pool C evaluated");
        let reasons: Vec<&str> = d[0]["routes"].as_array().unwrap().iter().map(|r| r["reason"].as_str().unwrap()).collect();
        assert!(reasons.iter().all(|x| *x == "pending_commit"), "C's routes through A and B wait: {reasons:?}");
        // T's last members: complete, A and B evaluated on the whole state
        acct(&mut r.e, b.vault1, vault(1_010 * SOL), 12, t + 5_000, Some(sig(1)), 14);
        assert_eq!(decisions(&r).len(), 1, "still B's vault0 missing");
        acct(&mut r.e, b.vault0, vault(990_000_000_000_000), 12, t + 6_000, Some(sig(1)), 15);
        let d = decisions(&r);
        assert_eq!(d.len(), 3, "A and B evaluated once T completed");
        let c = commits(&r);
        let ct = c.iter().find(|x| x["txn"] == json!(sigs58(&sig(1)))).unwrap();
        assert_eq!((ct["outcome"].as_str(), ct["w_src"].as_str(), ct["resolved_by"].as_str(), ct["w_seen"].as_array().unwrap().len()),
            (Some("complete"), Some("shred"), Some("member"), 4));
        assert_eq!(ct["t_first_shred"].as_u64(), Some(T0 + 10 * MS), "the first shred: the unexecuted feed's arrival");
        assert!((ct["lag_ms"].as_f64().unwrap() - 15.016).abs() < 0.01, "first shred (T0+10 ms) to complete commit (T0+25.016 ms): {}", ct["lag_ms"]);
        // every route of those two decisions was priced on the complete state (no pending reason)
        for x in &d[1..] { assert!(x["routes"].as_array().unwrap().iter().all(|r| r["reason"] != "pending_commit"), "{x}"); }
    }

    /// FT-000 (S1-8): a PumpSwap pool's mint is never in W(T). A transaction marks the mint writable without changing it
    /// (no update ever comes): its group completes at its last vault, not after `commit_timeout_ms` (628 of FT-000's 1,405
    /// `timeout_unknown` groups missed only mints); the other parts and the pools' own accounts stay in it. A run
    /// journaled before the fix (no `wt_skip_pump_mints` in its knobs) waits for the mint as it did: `timeout_unknown`
    #[test]
    fn a_pumpswap_mint_is_not_waited_for() {
        let mut p = meta_k(1);
        p.venue = Venue::PumpSwap;
        let mint: Pk = [0x77; 32];
        p.extra = vec![mint];
        let mut r = rig_metas("wt-mint", StrategyCfg { state_triggers: true, ..StrategyCfg::default() }, &[(p.clone(), 1_000), (meta_k(2), 1_000)]);
        assert!(r.e.part_pools.contains_key(&mint), "the mint is one of the pool's parts (present, not pending)");
        let t = T0 + 10 * MS;
        tx_ev(&mut r.e, shred_tx(sig(7), &[p.vault0, p.vault1, mint], None, 12, t));
        acct(&mut r.e, p.vault1, vault(1_030 * SOL), 12, t + 15 * MS, Some(sig(7)), 10);
        // the group is open: it waits for vault0, not for the mint
        assert!(r.e.tracker.is_pending(&p.vault0) && !r.e.tracker.is_pending(&mint), "W(T) without the mint");
        acct(&mut r.e, p.vault0, vault(970_000_000_000_000), 12, t + 15 * MS + 1_000, Some(sig(7)), 11);
        let c = commits(&r);
        let ct = c.iter().find(|x| x["txn"] == json!(sigs58(&sig(7)))).expect("resolved without a timer");
        assert_eq!((ct["outcome"].as_str(), ct["resolved_by"].as_str()), (Some("complete"), Some("member")), "{ct}");
        let w: Vec<&str> = ct["w_expected"].as_array().unwrap().iter().map(|x| x.as_str().unwrap()).collect();
        assert!(w.contains(&b58(&p.vault0).as_str()) && !w.contains(&b58(&mint).as_str()), "{w:?}");
        // a write to the mint stamped with the transaction after its group resolved is a late member (counted, marked)
        acct(&mut r.e, mint, vault(5), 12, t + 16 * MS, Some(sig(7)), 12);
        assert_eq!(r.e.counter("commit_late_member"), 1);
        // a run journaled before the fix (its engine_init knobs lack the key) replays as it ran: the mint is waited for
        let mut old = serde_json::to_value(EngineKnobs::default()).unwrap();
        assert_eq!(old.as_object_mut().unwrap().remove("wt_skip_pump_mints"), Some(json!(true)), "on by default");
        let k: EngineKnobs = serde_json::from_value(old).unwrap();
        assert!(!k.wt_skip_pump_mints);
        let mut r2 = rig_metas("wt-mint-old", StrategyCfg { state_triggers: true, ..StrategyCfg::default() }, &[(p.clone(), 1_000), (meta_k(2), 1_000)]);
        r2.e.set_knobs(k);
        tx_ev(&mut r2.e, shred_tx(sig(8), &[p.vault0, p.vault1, mint], None, 12, t));
        acct(&mut r2.e, p.vault1, vault(1_030 * SOL), 12, t + 15 * MS, Some(sig(8)), 10);
        assert!(r2.e.tracker.is_pending(&mint), "the W(T) of a run journaled before FT-000's fix names the mint");
        acct(&mut r2.e, p.vault0, vault(970_000_000_000_000), 12, t + 15 * MS + 1_000, Some(sig(8)), 11);
        assert!(!commits(&r2).iter().any(|x| x["txn"] == json!(sigs58(&sig(8)))), "both vaults written: still waiting for the mint");
        r2.e.timers(t + 21 * MS, &mut nop());
        let c2 = commits(&r2);
        let ct2 = c2.iter().find(|x| x["txn"] == json!(sigs58(&sig(8)))).expect("resolved by the timer");
        assert_eq!((ct2["outcome"].as_str(), ct2["resolved_by"].as_str()), (Some("timeout_unknown"), Some("timer")), "{ct2}");
        assert!(ct2["w_expected"].as_array().unwrap().contains(&json!(b58(&mint))), "{ct2}");
    }

    /// S1b (F2): the same split transaction not seen in shreds (W(T) unknown): resolved by quiescence, and no route is
    /// evaluated until both pools are quiet; S1b': a member arriving after the resolution is a late member, and the
    /// decisions priced on its pools since are marked torn_suspect
    #[test]
    fn s1b_unknown_write_set_resolves_by_quiescence_and_a_late_member_marks_torn_suspect() {
        let mut r = rig("s1b");
        make_ready(&mut r.e, T0);
        let (a, b) = (meta(1), meta(2));
        let t = T0 + 20 * MS;
        acct(&mut r.e, a.vault1, vault(1_030 * SOL), 12, t, Some(sig(1)), 10);
        acct(&mut r.e, b.vault1, vault(1_010 * SOL), 12, t + 1 * MS, Some(sig(1)), 11);
        r.e.timers(t + 3 * MS + 999_999, &mut nop());
        assert_eq!(r.e.counter("evaluation"), 0, "2.999 ms after T's last update: not quiet yet");
        r.e.timers(t + 4 * MS, &mut nop());
        let d = decisions(&r);
        assert_eq!(d.len(), 2, "A and B evaluated once T was quiescent");
        assert!(d.iter().all(|x| x["kind"] == "quiescent" && x["w_src"] == "unknown"));
        let c = commits(&r);
        assert_eq!((c[0]["outcome"].as_str(), c[0]["resolved_by"].as_str()), (Some("timeout_quiescent"), Some("timer")));
        let priced: Vec<u64> = d.iter().filter(|x| x["routes"].as_array().unwrap().iter().any(|r| r["net"].is_i64())).map(|x| x["decision"].as_u64().unwrap()).collect();
        assert!(!priced.is_empty());
        // S1b': a's vault0 stamped T arrives 2 ms after the resolution
        acct(&mut r.e, a.vault0, vault(970_000_000_000_000), 12, t + 6 * MS, Some(sig(1)), 12);
        assert_eq!((r.e.counter("commit_late_member"), r.e.counter("torn_suspect") as usize), (1, priced.len()));
        let d = decisions(&r);
        let torn: Vec<u64> = d.iter().filter(|x| x["torn_suspect"] == json!(true) && x.get("routes").is_none()).map(|x| x["decision"].as_u64().unwrap()).collect();
        assert_eq!(torn, priced);
        let c = commits(&r);
        assert!(c.iter().any(|x| x["late"] == json!(true) && x["late_members"][0]["acct"] == json!(b58(&a.vault0))));
        // route-level quiet: a timeout group's routes wait for both pools to be quiet (deferred, then priced)
        let mut r = rig("s1b-quiet");
        make_ready(&mut r.e, T0);
        let t = T0 + 20 * MS;
        acct(&mut r.e, a.vault1, vault(1_030 * SOL), 12, t, Some(sig(5)), 10);
        acct(&mut r.e, a.vault0, vault(970_000_000_000_000), 12, t + 1, Some(sig(5)), 11);
        // another transaction (its write set known from shreds) completes on B 2 ms later: B is not pending, but written
        tx_ev(&mut r.e, shred_tx(sig(6), &[b.vault1], None, 12, t + MS));
        acct(&mut r.e, b.vault1, vault(1_001 * SOL), 12, t + 2 * MS, Some(sig(6)), 12);
        r.e.timers(t + 3 * MS + 1, &mut nop());
        let of5 = |d: &Vec<Value>| -> Vec<Value> { d.iter().filter(|x| x["trigger"]["txn"] == json!(sigs58(&sig(5)))).cloned().collect() };
        let d = of5(&decisions(&r));
        assert_eq!(d.len(), 1);
        assert!(d[0]["routes"].as_array().unwrap().iter().all(|r| r["reason"] == "route_not_quiet"), "B was written 1 ms ago: {}", d[0]);
        r.e.timers(t + 5 * MS, &mut nop());
        let d = of5(&decisions(&r));
        assert_eq!(d.len(), 2, "evaluated again once quiet");
        assert!(d[1]["routes"].as_array().unwrap().iter().all(|r| r["net"].is_i64()), "{}", d[1]);
        assert_eq!(r.e.counter("evaluation_deferred"), 1);
    }

    /// readiness at the engine: an AMM v4 vault 3 slots older than the other is refused (`parts_skewed`); an idle pool
    /// 500 slots old is priced (slots are not compared across pools)
    #[test]
    fn s4_skew_within_a_pool_not_across_pools() {
        let mut r = rig("s4");
        make_ready(&mut r.e, T0);
        let (a, b) = (meta(1), meta(2));
        let t = T0 + 20 * MS;
        acct(&mut r.e, a.vault1, vault(1_030 * SOL), 513, t, Some(sig(1)), 10);
        slot_ev(&mut r.e, 513, 0, Some(512), t);
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(513, 1_759_000_100), 513, t, None, 11);
        r.e.timers(t + 4 * MS, &mut nop());
        let d = decisions(&r);
        assert!(d[0]["routes"].as_array().unwrap().iter().all(|r| r["reason"] == "parts_skewed"), "A's vaults 503 slots apart: {}", d[0]);
        acct(&mut r.e, a.vault0, vault(970_000_000_000_000), 513, t + 5 * MS, Some(sig(2)), 12);
        r.e.timers(t + 9 * MS, &mut nop());
        let d = decisions(&r);
        let last = d.last().unwrap();
        assert!(last["routes"].as_array().unwrap().iter().all(|r| r["net"].is_i64()), "B is 503 slots old and idle: priced: {last}");
        assert_eq!(last["parts_skew_slots"], json!({ "buy": 0, "sell": 0 }));
        let _ = b;
    }

    /// S8b (F4): a sibling fork with no `dead` status is abandoned when the other branch is confirmed: its versions are
    /// dropped (the canonical one restored), its pending groups are fork_dropped, decisions priced on it are
    /// `fork_priced`; while both siblings are unconfirmed, routes reading either are refused `fork_pending`. S8: a dead
    /// slot drops its versions, and an account left with none is fetched again
    #[test]
    fn s8_forks_abandon_dead_and_sibling_slots() {
        let mut r = rig("s8");
        make_ready(&mut r.e, T0);
        let (a, b) = (meta(1), meta(2));
        let t = T0 + 20 * MS;
        slot_ev(&mut r.e, 11, 1, Some(10), t);
        slot_ev(&mut r.e, 12, 0, Some(11), t);
        slot_ev(&mut r.e, 13, 0, Some(11), t);
        assert!(r.e.forks.is_contested(12) && r.e.forks.is_contested(13));
        // T writes A in slot 12 (the minority fork): A's routes are fork_pending
        acct(&mut r.e, a.vault1, vault(1_030 * SOL), 12, t + 1 * MS, Some(sig(1)), 10);
        acct(&mut r.e, a.vault0, vault(970_000_000_000_000), 12, t + 1 * MS + 1, Some(sig(1)), 11);
        r.e.timers(t + 5 * MS, &mut nop());
        let d = decisions(&r);
        assert!(d[0]["routes"].as_array().unwrap().iter().all(|r| r["reason"] == "fork_pending"), "{}", d[0]);
        // slot 13 is confirmed: 12 is abandoned, A's slot-12 versions go, the canonical ones are back
        slot_ev(&mut r.e, 13, 1, Some(11), t + 6 * MS);
        assert!(r.e.forks.is_abandoned(12));
        assert_eq!((r.e.counter("fork_abandoned_slot"), r.e.counter("fork_versions_dropped")), (1, 2));
        assert_eq!(r.e.store.get(&a.vault1).unwrap().slot, 10, "the canonical version again");
        let d = decisions(&r);
        assert!(d.iter().any(|x| x["kind"] == "fork"), "A evaluated again on its canonical state");
        // a decision priced on a version later abandoned is fork_priced
        slot_ev(&mut r.e, 14, 0, Some(13), t + 7 * MS);
        acct(&mut r.e, b.vault1, vault(1_020 * SOL), 14, t + 7 * MS, Some(sig(2)), 12);
        acct(&mut r.e, b.vault0, vault(990_000_000_000_000), 14, t + 7 * MS + 1, Some(sig(2)), 13);
        r.e.timers(t + 11 * MS, &mut nop());
        let priced = decisions(&r).iter().filter(|x| x["trigger"]["txn"] == json!(sigs58(&sig(2))) && x["routes"].as_array().unwrap().iter().any(|r| r["net"].is_i64())).count();
        assert!(priced > 0, "B priced on its slot-14 versions");
        let a2 = r.e.counter("fork_priced");
        slot_ev(&mut r.e, 15, 0, Some(13), t + 12 * MS);
        slot_ev(&mut r.e, 15, 1, Some(13), t + 12 * MS);
        assert!(r.e.forks.is_abandoned(14));
        assert!(r.e.counter("fork_priced") > a2, "the slot-14 decision was priced on an abandoned version");
        assert!(decisions(&r).iter().any(|x| x["fork_priced"] == json!(true)));
        // S8: a dead slot; B's vault0 had only that version: fetched again
        let mut r = rig("s8-dead");
        make_ready(&mut r.e, T0);
        r.e.store.drop_versions(&|_, _| false);
        let k = [77u8; 32];
        r.e.part_pools.insert(k, vec![1]);
        acct(&mut r.e, k, vault(5), 20, T0 + 30 * MS, Some(sig(3)), 20);
        slot_ev(&mut r.e, 20, 0, Some(11), T0 + 30 * MS);
        slot_ev(&mut r.e, 20, 6, None, T0 + 31 * MS);
        assert!(r.e.store.get(&k).is_none());
        assert_eq!((r.e.counter("fork_dead_slot"), r.e.counter("fork_refetch")), (1, 1));
        assert!(r.e.offline_fetches.iter().any(|(w, keys)| *w == "fork_refetch" && keys == &vec![k]));
        assert!(commits(&r).iter().any(|x| x["outcome"] == "fork_dropped"), "its pending group dropped");
        // slot-index `missing` evidence (WP-03b's input) drops (slot, txn) versions too
        acct(&mut r.e, b.vault1, vault(1_005 * SOL), 21, T0 + 40 * MS, Some(sig(4)), 30);
        r.e.step(Event::Input { kind: InputKind::SlotidxMissing, data: Arc::new(json!({ "slot": 21, "missing": [sigs58(&sig(4))] })) }, T0 + 41 * MS, &mut nop());
        assert_ne!(r.e.store.get(&b.vault1).unwrap().slot, 21);
    }

    /// The warm-up gate (item 8; S7): nothing is sent and decisions say `warmup` until every Tier-A pool is complete and
    /// the store is within 2 slots of the tip; a pool whose parts never come leaves Tier A after the grace period
    #[test]
    fn s7_warmup_gate() {
        let mut r = rig_with("s7", StrategyCfg { state_triggers: true, min_profit_lamports: 1, ..StrategyCfg::default() }, &[(1, 1_000), (2, 1_030)]);
        // a third pool on the pair whose vault never comes
        let mut reg = Arc::try_unwrap(std::mem::replace(&mut r.e.reg, Arc::new(Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(),
            seeds: Default::default(), ours: Default::default() }))).ok().unwrap();
        let c = meta(3);
        reg.by_pool.insert(c.pool, 2);
        reg.pools.push(c.clone());
        reg.pairs.get_mut(&pair_key(&MINT, &WSOL)).unwrap().push(2);
        r.e.store.update(c.pool, ammv4_pool(), 10, 1, None);
        r.e = { let mut e = Engine::new_offline(Arc::new(reg), std::mem::take(&mut r.e.store), r.e.cfg.clone()); e.set_rec(r.rec.clone()); e.min_tip = 1_000; e };
        let t = T0;
        slot_ev(&mut r.e, 11, 0, Some(10), t);
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(11, 1_759_000_000), 11, t, None, 1);
        r.e.timers(t + 6 * MS, &mut nop());
        assert_eq!(r.e.shut(), Shut::Warmup, "pool 3 has no vaults");
        let (a, _b) = (meta(1), meta(2));
        acct(&mut r.e, a.vault1, vault(1_001 * SOL), 11, t + 10 * MS, Some(sig(1)), 10);
        r.e.timers(t + 14 * MS, &mut nop());
        let d = decisions(&r);
        assert_eq!((d[0]["verdict"].as_str(), d[0]["reason"].as_str()), (Some("reject"), Some("warmup")), "an opportunity, not sendable: {}", d[0]);
        assert!(!r.e.health_flags().ready());
        // the grace period ends: pool 3 leaves Tier A, the gate opens
        r.e.timers(t + 61 * 1_000 * MS, &mut nop());
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(11, 1_759_000_061), 11, t + 61 * 1_000 * MS + 1, None, 2);
        assert_eq!((r.e.counter("tier_a_dropped"), r.e.shut()), (1, Shut::Ready));
        assert!(r.e.health_flags().ready());
        // the lag rule: the tip 3 slots past the store's newest update shuts it again
        slot_ev(&mut r.e, 14, 0, Some(11), t + 62 * 1_000 * MS);
        assert_eq!(r.e.shut(), Shut::Warmup);
        assert_eq!(r.e.counter("warmup_lost"), 1);
    }

    /// PLAN-ADDENDUM I-4 and I-5, the state outage (cmp2: a 503 for 28 minutes, priced blind, ~3,430 false signer misses):
    /// while the stream is down (its task's health input) or its newest message is older than 2 s, nothing is priced, the
    /// executor's hook refuses (fail closed), a WARNING goes to run.log, the engine's slot follows the shred feeds; a
    /// trigger pending across the outage is not a miss; the reconnect reads every followed account again; and a run whose
    /// stream never delivers stops with `state_unavailable`
    #[test]
    fn a_state_outage_stops_pricing_and_writes_no_false_signer_misses() {
        let mut r = rig("outage");
        make_ready(&mut r.e, T0);
        let (a, b) = (meta(1), meta(2));
        // a trigger's swap is seen just before the stream goes down
        tx_ev(&mut r.e, shred_tx(sig(7), &[a.pool, a.vault0, a.vault1], Some((&a, SOL, false)), 11, T0 + 8 * MS));
        health(&mut r.e, false, T0 + 9 * MS);
        assert_eq!(r.e.shut(), Shut::StateUnavailable);
        assert!(!r.e.health_flags().ready() && r.e.health_flags().shut() == Shut::StateUnavailable, "the send checks fail closed");
        // the shred feeds go on: the engine's slot follows them
        tx_ev(&mut r.e, shred_tx(sig(8), &[[50u8; 32]], None, 400, T0 + 100 * MS));
        assert_eq!(r.e.tip_slot(), 400);
        // a group pending when the stream died resolves, but prices nothing
        acct(&mut r.e, b.vault1, vault(1_030 * SOL), 11, T0 + 101 * MS, Some(sig(9)), 50);
        health(&mut r.e, false, T0 + 102 * MS);
        r.e.timers(T0 + 110 * MS, &mut nop());
        let d = decisions(&r);
        assert!(!d.is_empty() && d.iter().all(|x| x["routes"].as_array().unwrap().iter().all(|r| r["reason"] == "state_unavailable")), "{d:?}");
        // 6 s later: the trigger's 5 s are over, but the state was unavailable meanwhile: not a miss
        r.e.timers(T0 + 6_000 * MS, &mut nop());
        assert_eq!((r.e.counter("signer_miss"), r.e.counter("signer_miss_unknown")), (0, 1));
        assert!(!r.e.signer_stats.contains_key(&SIGNER) || r.e.signer_stats[&SIGNER].1 == 0, "no false miss written");
        // the stream comes back: every followed account is read again (from one slot after the stream's resume slot), and
        // the gate is `resync` until the re-read has landed (review WP-04 #1)
        health(&mut r.e, true, T0 + 6_001 * MS);
        assert_eq!(r.e.counter("state_resnapshot"), 1);
        slot_ev(&mut r.e, 401, 0, Some(400), T0 + 6_002 * MS);
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(401, 1_759_000_006), 401, T0 + 6_002 * MS, None, 60);
        assert_eq!(r.e.shut(), Shut::Resync, "available again, but not re-read yet");
        r.e.timers(T0 + 6_403 * MS, &mut nop());
        let (w, keys) = r.e.offline_fetches.iter().rev().find(|(w, _)| *w == "resnapshot").unwrap().clone();
        assert!(w == "resnapshot" && keys.contains(&a.vault0) && keys.contains(&b.pool));
        assert_eq!(answer_reads(&mut r.e, 401, T0 + 6_404 * MS, &|_| None), 1);
        assert_eq!(r.e.shut(), Shut::Ready, "available again (the tip from the stream, the store at it, every account read again)");
        // with the state healthy all along (a message every second), an expired trigger is a miss
        tx_ev(&mut r.e, shred_tx(sig(10), &[a.pool, a.vault0, a.vault1], Some((&a, SOL, false)), 401, T0 + 6_410 * MS));
        for k in 1..=6u64 { acct(&mut r.e, *CLOCK_SYSVAR, clock_data(401, 1_759_000_007), 401, T0 + (6_002 + 1_000 * k) * MS, None, 60 + k); }
        r.e.timers(T0 + 11_412 * MS, &mut nop());
        assert_eq!(r.e.counter("signer_miss"), 1);
        // a silence of 3 s that no timer saw is an outage all the same (a trigger across it is not a miss)
        tx_ev(&mut r.e, shred_tx(sig(11), &[a.pool, a.vault0, a.vault1], Some((&a, SOL, false)), 401, T0 + 12_100 * MS));
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(401, 1_759_000_008), 401, T0 + 12_200 * MS, None, 70);
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(401, 1_759_000_011), 401, T0 + 15_300 * MS, None, 71);
        for k in 1..=2u64 { acct(&mut r.e, *CLOCK_SYSVAR, clock_data(401, 1_759_000_012), 401, T0 + (15_300 + 1_000 * k) * MS, None, 71 + k); }
        r.e.timers(T0 + 17_200 * MS, &mut nop());
        assert_eq!((r.e.counter("signer_miss"), r.e.counter("signer_miss_unknown")), (1, 2));
        // the newest message older than 2 s: unavailable, with a WARNING
        r.e.timers(T0 + 19_400 * MS, &mut nop());
        assert_eq!(r.e.shut(), Shut::StateUnavailable);
        r.rec.sync();
        let log = std::fs::read_to_string(r.dir.join("run.log")).unwrap();
        assert!(log.contains("WARNING: state unavailable"), "{log}");
        let ev = rec::read_jsonl(&r.dir, "events").unwrap();
        assert!(ev.iter().any(|e| e["kind"] == "state_unavailable") && ev.iter().any(|e| e["kind"] == "state_resnapshot"));
        assert!(r.e.stop_req.is_none(), "unavailable_stop_s 0: an outage after the first message never stops the run");
        // review WP-04 #10, `unavailable_stop_s` set: an outage that lasts that long stops it (state_unavailable)
        let mut r2 = rig("unavailable-stop");
        r2.e.set_knobs(EngineKnobs { unavailable_stop_s: 60, ..EngineKnobs::default() });
        make_ready(&mut r2.e, T0);
        health(&mut r2.e, false, T0 + 10 * MS);
        r2.e.timers(T0 + 60_000 * MS, &mut nop());
        assert!(r2.e.stop_req.is_none());
        r2.e.timers(T0 + 60_011 * MS, &mut nop());
        assert!(r2.e.stop_req.as_deref().is_some_and(|s| s.contains("unavailable for 60 s")), "{:?}", r2.e.stop_req);
        // the boot timeout: a stream that never delivers stops the run
        let mut r = rig("boot-timeout");
        r.e.timers(T0, &mut nop());
        r.e.timers(T0 + 59 * 1_000 * MS, &mut nop());
        assert!(r.e.stop_req.is_none());
        r.e.timers(T0 + 60 * 1_000 * MS, &mut nop());
        assert!(r.e.stop_req.as_deref().is_some_and(|s| s.contains("delivered nothing within 60 s")));
    }

    /// Review WP-04 #1 (blocker, I-4; probe 1): after a state-stream reconnection nothing is priced or sent until the
    /// re-read has landed. The probe's sequence: both pools ready, the stream drops, 30 s later it reconnects, a slot
    /// status, the Clock and a write to B arrive. Before the fix the gate opened at once and B→A priced A's pre-outage
    /// version (+106,621,773 lamports at 2 SOL). Now: the gate is `resync` (the executor's flags too) and every route
    /// through a pool not read again is refused (`resync`); the re-read starts one slot after the stream's resume slot,
    /// each pool's accounts in one chunk; an injected chunk error is retried, a read behind the resume slot too; once
    /// every chunk has landed the gate opens and A is priced at the state the re-read brought
    #[test]
    fn a_reconnect_prices_nothing_until_the_re_read_lands() {
        let mut r = rig("resync");
        make_ready(&mut r.e, T0);
        let (a, b) = (meta(1), meta(2));
        health(&mut r.e, false, T0 + 10 * MS);
        assert_eq!(r.e.shut(), Shut::StateUnavailable);
        let tr = T0 + 30_000 * MS;
        health(&mut r.e, true, tr);
        assert_eq!(r.e.counter("state_resnapshot"), 1);
        slot_ev(&mut r.e, 90, 0, Some(89), tr + 1 * MS);
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(90, 1_759_000_030), 90, tr + 1 * MS, None, 500);
        assert_eq!((r.e.shut(), r.e.health_flags().shut(), r.e.health_flags().ready()), (Shut::Resync, Shut::Resync, false), "probe 1 found Ready here");
        acct(&mut r.e, b.vault1, vault(1_031 * SOL), 90, tr + 2 * MS, Some(sig(0xB1)), 501);
        acct(&mut r.e, b.vault0, vault(970_000_000_000_000), 90, tr + 2 * MS + 1, Some(sig(0xB1)), 502);
        r.e.timers(tr + 6 * MS, &mut nop());
        let d = decisions(&r);
        let last = d.last().unwrap();
        assert!(last["routes"].as_array().unwrap().iter().all(|x| x["reason"] == "resync"), "B's own pool account and all of A are unverified: {last}");
        assert_eq!((last["reason"].as_str(), r.e.counter("state_opportunity"), r.e.counter("reject_resync")), (Some("resync"), 0, 2), "no phantom gap");
        // the re-read: one slot after the resume slot 90, 6 accounts in one chunk, each pool's together
        r.e.timers(tr + 400 * MS, &mut nop());
        assert!(r.e.offline_reads.is_empty(), "not before one slot after the resume slot");
        r.e.timers(tr + 402 * MS, &mut nop());
        assert_eq!(r.e.offline_reads.len(), 1);
        assert_eq!(r.e.offline_reads[0].keys, vec![a.pool, a.vault0, a.vault1, b.pool, b.vault0, b.vault1]);
        // an injected chunk error: retried 250 ms later
        fail_reads(&mut r.e, tr + 450 * MS, "getMultipleAccounts: rate limited");
        assert_eq!((r.e.counter("read_chunk_failed"), r.e.counter("read_retry"), r.e.shut()), (1, 1, Shut::Resync));
        r.e.timers(tr + 699 * MS, &mut nop());
        assert!(r.e.offline_reads.is_empty(), "not before its retry time");
        r.e.timers(tr + 700 * MS, &mut nop());
        assert_eq!(r.e.offline_reads[0].attempt, 2, "read again");
        // an RPC node behind the stream's resume slot: its read would miss the writes before slot 90; read again
        answer_reads(&mut r.e, 89, tr + 710 * MS, &|_| None);
        assert_eq!((r.e.counter("resync_chunk_behind"), r.e.shut(), r.e.unverified.len()), (1, Shut::Resync, 4), "B's vaults came from the stream");
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(92, 1_759_000_031), 92, tr + 1_000 * MS, None, 503);
        r.e.timers(tr + 1_711 * MS, &mut nop());
        // the third read lands, A as the chain has it now (1,060 SOL, written during the outage)
        assert_eq!(answer_reads(&mut r.e, 92, tr + 1_720 * MS, &|k| (*k == a.vault1).then(|| vault(1_060 * SOL))), 1);
        assert_eq!((r.e.counter("state_resync_done"), r.e.shut(), r.e.unverified.len()), (1, Shut::Ready, 0), "every chunk landed: the gate opens");
        assert_eq!(r.e.store.get(&a.vault1).unwrap().slot, 92);
        // B's next write: priced against A's re-read state
        acct(&mut r.e, b.vault1, vault(1_032 * SOL), 93, tr + 1_800 * MS, Some(sig(0xB2)), 504);
        acct(&mut r.e, b.vault0, vault(969_000_000_000_000), 93, tr + 1_800 * MS + 1, Some(sig(0xB2)), 505);
        r.e.timers(tr + 1_805 * MS, &mut nop());
        let last = decisions(&r).last().cloned().unwrap();
        assert!(last["routes"].as_array().unwrap().iter().all(|x| x["net"].is_i64()), "{last}");
        r.rec.sync();
        let ev = rec::read_jsonl(&r.dir, "events").unwrap();
        let done = ev.iter().find(|e| e["kind"] == "state_resync_done").unwrap();
        assert_eq!((done["detail"]["why"].as_str(), done["detail"]["retries"].as_u64(), done["detail"]["behind"].as_u64(), done["detail"]["failed"].as_u64()),
            (Some("reconnect"), Some(2), Some(1), Some(1)));
        assert!(ev.iter().any(|e| e["kind"] == "read_retry"));
        let log = std::fs::read_to_string(r.dir.join("run.log")).unwrap();
        assert!(log.contains("state re-read (reconnect) done"), "{log}");
    }

    /// Review WP-04 #1c: the boot snapshot is read before the stream subscribes, so the stream's first connection starts
    /// the same re-read (writes between the snapshot and the subscription are closed); the re-read packs each pool's
    /// accounts into one chunk of at most 100; a re-read that has not landed `resync_warn_s` after the connection is a
    /// WARNING (the gate stays shut); a chunk still failing `resync_give_up_s` after the start is given up: the gate
    /// opens, its accounts stay refused one by one until the stream writes them
    #[test]
    fn the_first_connection_re_reads_the_boot_snapshot() {
        let pools: Vec<(PoolMeta, u64)> = (1..=40u8).map(|n| (meta_k(n), 1_000)).collect();
        let mut r = rig_metas("resync-boot", StrategyCfg { state_triggers: true, ..StrategyCfg::default() }, &pools);
        r.e.set_knobs(EngineKnobs { resync_give_up_s: 30, ..EngineKnobs::default() });
        let chunks = r.e.resync_chunks();
        assert_eq!(chunks.iter().map(|c| c.len()).collect::<Vec<_>>(), vec![99, 21], "33 pools of 3, then 7");
        for p in 1..=40u8 {
            let m = meta_k(p);
            let c: Vec<usize> = [m.pool, m.vault0, m.vault1].iter().map(|k| chunks.iter().position(|c| c.contains(k)).unwrap()).collect();
            assert!(c.windows(2).all(|w| w[0] == w[1]), "pool {p}'s accounts in one chunk: {c:?}");
        }
        health(&mut r.e, true, T0);
        slot_ev(&mut r.e, 11, 0, Some(10), T0 + MS);
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(11, 1_759_000_000), 11, T0 + MS, None, 1);
        r.e.timers(T0 + 6 * MS, &mut nop());
        assert_eq!(r.e.shut(), Shut::Resync, "Tier A is complete, but the boot snapshot is not re-read yet");
        r.e.timers(T0 + 402 * MS, &mut nop());
        assert_eq!(r.e.offline_reads.len(), 1, "the second chunk 120 ms later");
        answer_reads(&mut r.e, 12, T0 + 410 * MS, &|_| None);
        r.e.timers(T0 + 522 * MS, &mut nop());
        assert_eq!(r.e.offline_reads.len(), 1);
        fail_reads(&mut r.e, T0 + 530 * MS, "status: 503");
        // keep the stream alive; the WARNING at 10 s; the retries every 10 s at most; given up 30 s after the start
        let mut t = T0 + 530 * MS;
        while t < T0 + 35_000 * MS {
            t += 500 * MS;
            acct(&mut r.e, *CLOCK_SYSVAR, clock_data(12, 1_759_000_001), 12, t, None, 2 + t / MS);
            r.e.timers(t + 1, &mut nop());
            fail_reads(&mut r.e, t + 2, "status: 503");
        }
        assert_eq!((r.e.counter("state_resync_slow"), r.e.counter("read_gave_up"), r.e.counter("state_resync_done")), (1, 1, 1));
        assert_eq!(r.e.shut(), Shut::Ready, "given up: the gate opens");
        assert_eq!(r.e.unverified.len(), 21, "the second chunk's accounts stay refused one by one");
        let m = meta_k(40);
        acct(&mut r.e, m.vault1, vault(1_010 * SOL), 13, t + 10 * MS, Some(sig(1)), 1_000_000);
        acct(&mut r.e, m.vault0, vault(990_000_000_000_000), 13, t + 10 * MS + 1, Some(sig(1)), 1_000_001);
        r.e.timers(t + 15 * MS, &mut nop());
        let last = decisions(&r).last().cloned().unwrap();
        assert_eq!(last["routes"][0]["reason"], json!("resync"), "pool 40's own account was never read again: {last}");
        r.rec.sync();
        let ev = rec::read_jsonl(&r.dir, "events").unwrap();
        assert!(ev.iter().any(|e| e["kind"] == "state_resnapshot" && e["detail"]["why"] == "boot"));
        let log = std::fs::read_to_string(r.dir.join("run.log")).unwrap();
        assert!(log.contains("WARNING: the state re-read (boot) has not landed 10 s after the connection") && log.contains("WARNING: the state re-read gave up on 21 accounts after 30 s"), "{log}");
    }

    /// Review WP-04 #3a (probe 2): siblings 12 and 13 of 11; A written in 13 is `fork_pending` while both are
    /// unconfirmed; once 12 is confirmed, 13 is abandoned at once (its versions dropped), so B's next decision reads A's
    /// canonical version, never 13's, and no decision is `fork_priced` later
    #[test]
    fn a_confirmed_slots_higher_sibling_is_never_priced() {
        let mut r = rig("fork-sibling");
        make_ready(&mut r.e, T0);
        let (a, b) = (meta(1), meta(2));
        let t = T0 + 20 * MS;
        slot_ev(&mut r.e, 11, 1, Some(10), t);
        slot_ev(&mut r.e, 12, 0, Some(11), t);
        slot_ev(&mut r.e, 13, 0, Some(11), t);
        acct(&mut r.e, a.vault1, vault(1_030 * SOL), 13, t + 1 * MS, Some(sig(1)), 10);
        acct(&mut r.e, a.vault0, vault(970_000_000_000_000), 13, t + 1 * MS + 1, Some(sig(1)), 11);
        r.e.timers(t + 5 * MS, &mut nop());
        assert!(decisions(&r)[0]["routes"].as_array().unwrap().iter().all(|x| x["reason"] == "fork_pending"));
        slot_ev(&mut r.e, 12, 1, Some(11), t + 6 * MS);
        assert!(r.e.forks.is_abandoned(13) && !r.e.forks.is_contested(13), "probe 2: neither abandoned nor contested");
        assert_eq!((r.e.store.get(&a.vault1).unwrap().slot, r.e.counter("fork_versions_dropped")), (10, 2));
        slot_ev(&mut r.e, 14, 0, Some(12), t + 7 * MS);
        acct(&mut r.e, b.vault1, vault(1_001 * SOL), 14, t + 7 * MS, Some(sig(2)), 12);
        acct(&mut r.e, b.vault0, vault(999_000_000_000_000), 14, t + 7 * MS + 1, Some(sig(2)), 13);
        r.e.timers(t + 11 * MS, &mut nop());
        let last = r.e.recent.back().unwrap();
        assert!(!last.slots.contains(&13) && last.slots.contains(&14), "B's decision read A's canonical version: {:?}", last.slots);
        slot_ev(&mut r.e, 15, 0, Some(14), t + 12 * MS);
        slot_ev(&mut r.e, 15, 1, Some(14), t + 12 * MS);
        assert_eq!(r.e.counter("fork_priced"), 0, "probe 2: 0 -> 1 at 15's confirmation");
    }

    /// Review WP-04 #3b (probe 3): with interslot statuses, a slot created on an abandoned parent is abandoned before its
    /// writes arrive; they are refused (`fork_late_version`), never stored, priced or kept
    #[test]
    fn writes_of_a_slot_already_abandoned_are_refused() {
        let mut r = rig("fork-late");
        make_ready(&mut r.e, T0);
        let (a, b) = (meta(1), meta(2));
        let t = T0 + 20 * MS;
        slot_ev(&mut r.e, 12, 0, Some(11), t);
        slot_ev(&mut r.e, 13, 0, Some(11), t);
        slot_ev(&mut r.e, 13, 1, Some(11), t + 1 * MS);
        slot_ev(&mut r.e, 14, 5, Some(12), t + 2 * MS);
        assert!(r.e.forks.is_abandoned(14));
        acct(&mut r.e, a.vault1, vault(1_030 * SOL), 14, t + 3 * MS, Some(sig(1)), 10);
        acct(&mut r.e, a.vault0, vault(970_000_000_000_000), 14, t + 3 * MS + 1, Some(sig(1)), 11);
        r.e.timers(t + 7 * MS, &mut nop());
        assert_eq!((r.e.counter("fork_late_version"), r.e.store.get(&a.vault1).unwrap().slot, r.e.tracker.pending_groups()), (2, 10, 0));
        slot_ev(&mut r.e, 14, 0, Some(12), t + 8 * MS);
        slot_ev(&mut r.e, 16, 0, Some(13), t + 9 * MS);
        acct(&mut r.e, b.vault1, vault(1_001 * SOL), 16, t + 9 * MS, Some(sig(2)), 12);
        acct(&mut r.e, b.vault0, vault(999_000_000_000_000), 16, t + 9 * MS + 1, Some(sig(2)), 13);
        r.e.timers(t + 13 * MS, &mut nop());
        assert_eq!((r.e.store.get(&a.vault1).unwrap().slot, r.e.counter("state_opportunity")), (10, 0), "probe 3: slot 14 current, 2 opportunities");
        // the journal's verdict says refused (a replay checks it against the same rule)
        assert!(r.e.account_refused(&a.vault1, 14, asrc::GRPC, 99, 0, None));
    }

    /// Review WP-04 #2 (probe 6, the late-leader fork): 13 (built on 11) is replayed first, then the late block 12, whose
    /// writes arrive with a lower slot. When 12 wins, 13's versions go and the account holds the canonical slot-12
    /// version (1,050 SOL), not the pre-fork one (1,000 SOL), with no refetch needed; its pools are evaluated again
    #[test]
    fn the_late_leader_fork_restores_the_canonical_version() {
        let mut r = rig("fork-late-leader");
        make_ready(&mut r.e, T0);
        let a = meta(1);
        let t = T0 + 20 * MS;
        slot_ev(&mut r.e, 11, 1, Some(10), t);
        slot_ev(&mut r.e, 13, 0, Some(11), t);
        acct(&mut r.e, a.vault1, vault(1_020 * SOL), 13, t + 1 * MS, Some(sig(13)), 10);
        acct(&mut r.e, a.vault0, vault(980_000_000_000_000), 13, t + 1 * MS + 1, Some(sig(13)), 11);
        slot_ev(&mut r.e, 12, 0, Some(11), t + 2 * MS);
        acct(&mut r.e, a.vault1, vault(1_050 * SOL), 12, t + 3 * MS, Some(sig(12)), 12);
        acct(&mut r.e, a.vault0, vault(952_000_000_000_000), 12, t + 3 * MS + 1, Some(sig(12)), 13);
        r.e.timers(t + 8 * MS, &mut nop());
        assert_eq!((r.e.store.get(&a.vault1).unwrap().slot, r.e.store.kept_below), (13, 2), "12's writes kept below 13's");
        let before = r.e.counter("evaluation");
        slot_ev(&mut r.e, 12, 1, Some(11), t + 9 * MS);
        slot_ev(&mut r.e, 14, 0, Some(12), t + 10 * MS);
        slot_ev(&mut r.e, 14, 1, Some(12), t + 11 * MS);
        assert!(r.e.forks.is_abandoned(13));
        let v = r.e.store.get(&a.vault1).unwrap();
        let amount = u64::from_le_bytes(v.data[64..72].try_into().unwrap()) / SOL;
        assert_eq!((v.slot, amount), (12, 1_050), "probe 6 found (10, 1,000): the pre-fork version");
        assert_eq!(r.e.counter("fork_refetch"), 0);
        assert!(r.e.counter("evaluation") > before, "A evaluated again on its canonical state");
        assert!(decisions(&r).iter().any(|x| x["kind"] == "fork"));
    }

    /// Review WP-04 #5 (probe 4): with the Stage-0 ladder (top rung 4.2 SOL), a decision never prices a size past the top
    /// rung (the refinement doubled it to 8.4 SOL: the cmp2 ladder-edge quotes)
    #[test]
    fn decisions_never_price_past_the_top_rung() {
        let cfg = StrategyCfg { state_triggers: true, sizes_sol: vec![0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 4.2], ..StrategyCfg::default() };
        let mut r = rig_with("top-rung", cfg, &[(1, 15_000), (2, 15_000)]);
        make_ready(&mut r.e, T0);
        let b = meta(2);
        let t = T0 + 20 * MS;
        acct(&mut r.e, b.vault1, vault(15_900 * SOL), 12, t, Some(sig(1)), 10);
        acct(&mut r.e, b.vault0, vault(950_000_000_000_000), 12, t + 1, Some(sig(1)), 11);
        r.e.timers(t + 4 * MS, &mut nop());
        let d = decisions(&r);
        let x = d.last().unwrap();
        let best = &x["routes"][x["best"].as_u64().unwrap() as usize];
        assert!(best["size"].as_u64().unwrap() <= 4_200_000_000 && best["net"].as_i64().unwrap() > 0, "probe 4: 8,399,809,909: {best}");
        assert!(x["routes"].as_array().unwrap().iter().filter_map(|r| r["size"].as_u64()).all(|s| s <= 4_200_000_000));
        // WP-16: the crate's locator puts the optimum past the cap here; the size sits on the cap
        assert_eq!(best["size"].as_u64(), Some(4_200_000_000), "{best}");
    }

    /// PLAN-ADDENDUM WP-16: a state arbx-sizing refuses is the route's recorded reason (decisions.jsonl `routes[].reason`)
    /// and its counter (`reject_<reason>`): a third pool on the pair whose AMM v4 status is 0 (swaps off) refuses both
    /// routes through it (`sz_ammv4_status`); the routes between the tradable pools price as before
    #[test]
    fn a_state_arbx_sizing_refuses_is_the_routes_reason() {
        let mut r = rig_with("sz-refused", StrategyCfg { state_triggers: true, ..StrategyCfg::default() }, &[(1, 1_000), (2, 1_000), (3, 1_000)]);
        let c = meta(3);
        let mut p = ammv4_pool().to_vec();
        p[0..8].copy_from_slice(&0u64.to_le_bytes());
        assert!(r.e.store.update(c.pool, p.into(), 11, 1, None));
        make_ready(&mut r.e, T0);
        let b = meta(2);
        let t = T0 + 20 * MS;
        acct(&mut r.e, b.vault1, vault(1_020 * SOL), 12, t, Some(sig(3)), 10);
        acct(&mut r.e, b.vault0, vault(990_000_000_000_000), 12, t + 1, Some(sig(3)), 11);
        r.e.timers(t + 4 * MS, &mut nop());
        let d = decisions(&r);
        let routes = d.last().unwrap()["routes"].as_array().unwrap().clone();
        let c58 = json!(b58(&c.pool));
        let through_c: Vec<&Value> = routes.iter().filter(|x| x["buy"] == c58 || x["sell"] == c58).collect();
        assert_eq!(through_c.len(), 2, "{routes:?}");
        assert!(through_c.iter().all(|x| x["reason"] == "sz_ammv4_status" && x["size"].is_null()), "{through_c:?}");
        assert!(routes.iter().any(|x| x["size"].is_u64()), "the tradable pools' routes price: {routes:?}");
        assert_eq!(r.e.counter("reject_sz_ammv4_status"), 2);
    }

    /// WP-16 review F10: the hint check, the builder probe and the accuracy monitor name the crate's refusal, like a
    /// route: a decoded swap on a pool whose AMM v4 status is 0 (swaps off) is skipped `sz_ammv4_status` (triggers.jsonl
    /// `skip`, counter `trigger_sz_ammv4_status`, not `trigger_unquotable`); `probe_routes` over that pool counts
    /// `probe_sz_ammv4_status`; the monitor's counter for a refused swap is `pred_<reason>`
    #[test]
    fn hints_probes_and_the_monitor_carry_the_crates_reason() {
        let mut r = rig("sz-hint");
        let a = meta(1);
        let mut p = ammv4_pool().to_vec();
        p[0..8].copy_from_slice(&0u64.to_le_bytes());
        assert!(r.e.store.update(a.pool, p.into(), 11, 1, None));
        make_ready(&mut r.e, T0);
        tx_ev(&mut r.e, shred_tx(sig(9), &[a.pool, a.vault0, a.vault1], Some((&a, SOL, false)), 11, T0 + 10 * MS));
        assert_eq!((r.e.counter("trigger"), r.e.counter("trigger_sz_ammv4_status"), r.e.counter("trigger_unquotable"), r.e.counter("trigger_hint_only")), (1, 1, 0, 0));
        r.rec.sync();
        let t = rec::read_jsonl(&r.dir, "triggers").unwrap();
        assert_eq!(t.last().unwrap()["skip"], "sz_ammv4_status", "{:?}", t.last());
        let _ = r.e.probe_routes(SOL / 10, 10);
        assert!(r.e.counter("probe_sz_ammv4_status") >= 1 && r.e.counter("probe_unquotable") == 0, "{} {}", r.e.counter("probe_sz_ammv4_status"), r.e.counter("probe_unquotable"));
        // the monitor's counter: the reason's own (`accuracy::predict` refuses with it)
        let v = |k: &Pk| r.e.store.get(k);
        let view = accuracy::View { get: &v, arrays: &[], now_unix: 1_759_000_000, slot: 11 };
        assert_eq!(accuracy::predict(&a, &view, false, SOL, false).unwrap_err(), accuracy::NoPred::Refused("sz_ammv4_status"));
        assert_eq!(quote::reason_row("sz_ammv4_status").unwrap().pred, "pred_sz_ammv4_status");
    }

    /// Review WP-04 #4 (probe 5): with the real file's 30,304 signers, saving the signer statistics and the 10-s status
    /// line cost the engine thread microseconds (it hands over the map as loaded and this segment's counts; the writer
    /// adds them up and serializes: about 25 ms per call when the engine thread did it); the files hold the sum
    #[test]
    fn saving_signer_stats_stays_off_the_engine_thread() {
        let mut r = rig("signer-save");
        let dir = r.dir.clone();
        r.e.set_signer_stats_out(&dir);
        let mut base: HashMap<Pk, (u32, u32)> = HashMap::default();
        let mut x = 0x9e3779b97f4a7c15u64;
        for n in 0..30_304u32 {
            let mut k = [0u8; 32];
            for c in k.chunks_mut(8) { x ^= x << 13; x ^= x >> 7; x ^= x << 17; c.copy_from_slice(&x.to_le_bytes()); }
            base.insert(k, (n % 5, n % 3));
        }
        let one = *base.keys().next().unwrap();
        r.e.signer_stats = base.clone();
        r.e.signer_base = Arc::new(base);
        r.e.trig_pending.insert(sig(1), (one, 1));
        r.e.signer_outcome(&sig(1), true);
        r.e.trig_pending.insert(sig(2), (SIGNER, 1));
        r.e.signer_outcome(&sig(2), false);
        let mut save = Vec::new();
        for _ in 0..5 { let a = std::time::Instant::now(); r.e.save_signer_stats(); save.push(a.elapsed().as_micros()); }
        let mut t = T0;
        let mut status = Vec::new();
        for _ in 0..5 { t += STATUS_EVERY_NS + 1; let a = std::time::Instant::now(); r.e.timers(t, &mut nop()); status.push(a.elapsed().as_micros()); }
        eprintln!("signer statistics (30,304 signers): save on the engine thread {save:?} µs; the 10-s timers {status:?} µs (probe 5: about 25,000 µs each)");
        // the best of five (a machine busy with other tests can preempt one call; the old path cost 25 ms every time)
        let (s_min, t_min) = (save.iter().min().copied().unwrap(), status.iter().skip(1).min().copied().unwrap());
        assert!(s_min < 2_000 && t_min < 5_000, "{save:?} µs / {status:?} µs");
        r.rec.sync();
        let full: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("signer-stats.json")).unwrap()).unwrap();
        let delta: Value = serde_json::from_str(&std::fs::read_to_string(dir.join("signer-stats-delta.json")).unwrap()).unwrap();
        let b = r.e.signer_base.get(&one).copied().unwrap();
        assert_eq!(full.as_object().unwrap().len(), 30_305);
        assert_eq!((full[b58(&one)].clone(), full[b58(&SIGNER)].clone()), (json!([b.0 + 1, b.1]), json!([0, 1])), "the map as loaded plus this segment's counts");
        assert_eq!(delta.as_object().unwrap().len(), 2);
    }

    /// Review WP-04 #7: slot-index `missing` evidence (the confirmed block of a slot does not hold a transaction) drops
    /// that transaction's versions, its pending group (`fork_dropped`), and marks the decisions that read its versions
    /// `fork_priced`, even when the account kept no version of it
    #[test]
    fn slot_index_missing_marks_decisions_and_drops_groups() {
        let mut r = rig("slotidx");
        make_ready(&mut r.e, T0);
        let (a, b) = (meta(1), meta(2));
        let t = T0 + 20 * MS;
        // X moves B in slot 21 (W(X) known): complete, B priced on X's versions
        tx_ev(&mut r.e, shred_tx(sig(4), &[b.vault0, b.vault1], None, 21, t));
        acct(&mut r.e, b.vault1, vault(1_005 * SOL), 21, t + 1 * MS, Some(sig(4)), 30);
        acct(&mut r.e, b.vault0, vault(995_000_000_000_000), 21, t + 1 * MS + 1, Some(sig(4)), 31);
        assert!(r.e.recent.back().is_some_and(|d| d.txns.contains(&(21, sig8(&sig(4))))));
        // Y writes A in slot 21, one of its two members so far: pending
        tx_ev(&mut r.e, shred_tx(sig(5), &[a.vault0, a.vault1], None, 21, t + 2 * MS));
        acct(&mut r.e, a.vault1, vault(1_010 * SOL), 21, t + 3 * MS, Some(sig(5)), 32);
        assert!(r.e.tracker.is_pending(&a.vault0));
        let priced = r.e.counter("fork_priced");
        r.e.step(Event::Input { kind: InputKind::SlotidxMissing, data: Arc::new(json!({ "slot": 21, "missing": [sigs58(&sig(4)), sigs58(&sig(5))] })) }, t + 4 * MS, &mut nop());
        assert!(r.e.counter("fork_priced") > priced, "B's decision read X's versions");
        assert_eq!((r.e.counter("commit_fork_dropped"), r.e.tracker.is_pending(&a.vault0)), (1, false), "Y's group dropped");
        assert_eq!((r.e.store.get(&b.vault1).unwrap().slot, r.e.store.get(&a.vault1).unwrap().slot), (10, 10));
    }

    /// S2 (stacked failed sells, PLAN WP-09; W §7.1: 681 of 822 decoded triggers of 0.1 SOL or more failed on chain):
    /// many decoded swaps that fail on chain, with no account writes, make no decision at all
    #[test]
    fn s2_failed_swaps_make_no_decision() {
        let mut r = rig("s2");
        make_ready(&mut r.e, T0);
        let a = meta(1);
        for k in 0..20u8 {
            let t = T0 + (10 + k as u64) * MS;
            tx_ev(&mut r.e, shred_tx(sig(100 + k), &[a.pool, a.vault0, a.vault1], Some((&a, (k as u64 + 1) * 3 * SOL, k % 2 == 0)), 11, t));
            if k % 3 == 0 {
                let mut f = shred_tx(sig(100 + k), &[a.pool, a.vault0, a.vault1], Some((&a, SOL, true)), 11, t + 1);
                f.feed = 1;
                f.executed = Some(false);
                tx_ev(&mut r.e, f);
            }
        }
        r.e.timers(T0 + 6_000 * MS, &mut nop());
        assert_eq!((r.e.counter("trigger"), r.e.counter("evaluation"), r.e.counter("state_opportunity")), (20, 0, 0), "no state ever existed: no decision");
        assert!(decisions(&r).is_empty() && commits(&r).is_empty());
        assert_eq!(r.e.counter("signer_miss_tx"), 7, "the failed ones that an executed feed reported: misses at once");
    }

    /// PLAN-ADDENDUM I-4: `Engine::run` stops by itself (`RunEnd::StateUnavailable`; `arbx run` then writes stop.json reason
    /// `state_unavailable`, exit 30) when the state stream delivers nothing within `boot_timeout_s`
    #[test]
    fn run_stops_when_the_state_stream_never_delivers() {
        let mut r = rig("boot-stop");
        r.e.set_knobs(EngineKnobs { boot_timeout_s: 1, ..EngineKnobs::default() });
        let (tx, rx) = crossbeam_channel::unbounded::<Event>();
        let stop = std::sync::atomic::AtomicBool::new(false);
        let t0 = std::time::Instant::now();
        assert_eq!(r.e.run(&rx, &stop, u64::MAX, |_| {}), RunEnd::StateUnavailable);
        assert!(t0.elapsed() >= std::time::Duration::from_millis(990) && t0.elapsed() < std::time::Duration::from_secs(5));
        drop(tx);
        r.rec.sync();
        let log = std::fs::read_to_string(r.dir.join("run.log")).unwrap();
        assert!(log.contains("WARNING: the state stream delivered nothing within 1 s"), "{log}");
    }

    /// I-5: the signer statistics are read once (sha256 recorded), never written back to the shared file; each segment
    /// writes its copy and its own counts into its run directory; `merge` folds the counts back, once
    #[test]
    fn signer_statistics_per_segment() {
        let dir = std::env::temp_dir().join(format!("arbx-signer-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&dir).unwrap();
        let shared = dir.join("signer-stats.json");
        std::fs::write(&shared, json!({ b58(&SIGNER): [3, 1] }).to_string()).unwrap();
        let before = std::fs::read(&shared).unwrap();
        let run = dir.join("seg1");
        std::fs::create_dir_all(&run).unwrap();
        let rec = rec::start(rec::Opts { dir: run.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        let reg = Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
        let (tx, _rx) = crossbeam_channel::unbounded();
        let (wtx, _wrx) = tokio::sync::watch::channel(Vec::new());
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        let mut e = Engine::new(Arc::new(reg), Store::default(), StrategyCfg { signer_stats_file: shared.display().to_string(), ..StrategyCfg::default() }, vec![], 0,
            Arc::new(Interest::default()), rec.clone(), crate::rpc::Rpc::race(vec![]), rt.handle().clone(), tx, wtx).unwrap();
        assert_eq!(e.signer_stats_sha256(), Some(crate::provenance::sha256_hex(&before).as_str()));
        assert_eq!(e.init().signer_stats_sha256, e.signer_stats_sha256().map(String::from), "journaled with engine_init");
        e.set_signer_stats_out(&run);
        e.trig_pending.insert(sig(1), (SIGNER, 1));
        e.signer_outcome(&sig(1), true);
        e.finish();
        rec.close();
        assert_eq!(std::fs::read(&shared).unwrap(), before, "the shared file is never written by a run");
        let full: Value = serde_json::from_str(&std::fs::read_to_string(run.join("signer-stats.json")).unwrap()).unwrap();
        let delta: Value = serde_json::from_str(&std::fs::read_to_string(run.join("signer-stats-delta.json")).unwrap()).unwrap();
        assert_eq!((full[b58(&SIGNER)].clone(), delta[b58(&SIGNER)].clone()), (json!([4, 1]), json!([1, 0])));
        assert!(merge_signer_stats(&shared, &[run.clone()]).unwrap_err().to_string().contains("has not ended"), "a running segment is refused");
        std::fs::write(run.join("stop.json"), "{}").unwrap();
        let out = merge_signer_stats(&shared, &[run.clone()]).unwrap();
        assert_eq!(out[0].1, 1);
        let merged: Value = serde_json::from_str(&std::fs::read_to_string(&shared).unwrap()).unwrap();
        assert_eq!(merged[b58(&SIGNER)], json!([4, 1]));
        assert!(merge_signer_stats(&shared, &[run]).unwrap_err().to_string().contains("merged already"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// The chain clock (item 6): DLMM and DAMM v2 routes are refused `clock_stale` with no Clock sysvar or one more than
    /// 2 slots behind the tip
    #[test]
    fn clock_stale_refuses_dlmm_and_damm_routes() {
        let mut r = rig("clock");
        // pool 2 becomes a DAMM v2 pool on the pair (its pool account is its consistency set)
        let mut reg = Arc::try_unwrap(std::mem::replace(&mut r.e.reg, Arc::new(Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(),
            seeds: Default::default(), ours: Default::default() }))).ok().unwrap();
        reg.pools[1].venue = Venue::DammV2;
        let store = std::mem::take(&mut r.e.store);
        r.e = { let mut e = Engine::new_offline(Arc::new(reg), store, r.e.cfg.clone()); e.set_rec(r.rec.clone()); e.min_tip = 1_000; e };
        make_ready(&mut r.e, T0);
        let a = meta(1);
        // the tip moves 3 slots past the Clock (it is still slot 11)
        slot_ev(&mut r.e, 14, 0, Some(11), T0 + 10 * MS);
        acct(&mut r.e, a.vault1, vault(1_001 * SOL), 14, T0 + 10 * MS, Some(sig(1)), 10);
        acct(&mut r.e, a.vault0, vault(999_000_000_000_000), 14, T0 + 10 * MS + 1, Some(sig(1)), 11);
        r.e.timers(T0 + 14 * MS, &mut nop());
        let d = decisions(&r);
        assert!(d[0]["routes"].as_array().unwrap().iter().all(|r| r["reason"] == "clock_stale"), "{}", d[0]);
    }

    /// S6: lookup tables (I-6) through the engine: a transaction waits while its table is fetched; a failed fetch is
    /// retried at 50 ms (not cached as missing), and the answer releases it; every transition is an alts.jsonl event
    #[test]
    fn s6_lookup_tables_are_retried() {
        let mut r = rig("s6");
        make_ready(&mut r.e, T0);
        let table = [88u8; 32];
        let mut a = shred_tx(sig(30), &[], None, 11, T0 + 10 * MS);
        a.tx.lookups = vec![crate::tx::Lookup { table, writable: vec![0], readonly: vec![] }];
        tx_ev(&mut r.e, a);
        assert_eq!((r.e.counter("alt_wait"), r.e.offline_fetches.iter().filter(|f| f.0 == "alt").count()), (1, 1));
        r.e.step(Event::Alt { table, addrs: None, err: Some("429".into()) }, T0 + 20 * MS, &mut nop());
        assert_eq!(r.e.alts.waiting_txs(), 1, "still waiting: retried, not missing for the run");
        r.e.timers(T0 + 69 * MS, &mut nop());
        assert_eq!(r.e.offline_fetches.iter().filter(|f| f.0 == "alt").count(), 1);
        r.e.timers(T0 + 70 * MS, &mut nop());
        assert_eq!(r.e.offline_fetches.iter().filter(|f| f.0 == "alt").count(), 2, "retried 50 ms after the failure");
        let m = meta(1);
        r.e.step(Event::Alt { table, addrs: Some(Arc::new(vec![m.vault0])), err: None }, T0 + 80 * MS, &mut nop());
        assert_eq!(r.e.alts.waiting_txs(), 0, "released");
        assert!(r.e.tracker.is_pending(&m.vault0) || r.e.tracker.pending_groups() == 0, "processed");
        r.rec.sync();
        let ev: Vec<String> = rec::read_jsonl(&r.dir, "alts").unwrap().iter().map(|x| x["event"].as_str().unwrap().to_string()).collect();
        assert_eq!(ev, ["fetch_start", "fetch_error", "retry_scheduled", "fetch_start", "fetch_ok", "waiters_released"]);
    }

    /// The accuracy monitor (item 13): a hint is scored against T's pre-state (the version just before T's write, from
    /// the ring), exact for a correct prediction even when the pool moved between the hint and T; `pre_state_unknown`
    /// when the ring no longer holds the pre-state
    #[test]
    fn accuracy_scores_against_the_pre_state() {
        let mut r = rig("acc");
        make_ready(&mut r.e, T0);
        let a = meta(1);
        // the hint arrives on A as it is (1,000 SOL)
        tx_ev(&mut r.e, shred_tx(sig(40), &[a.pool, a.vault0, a.vault1], Some((&a, 10 * SOL, false)), 11, T0 + 10 * MS));
        // another transaction moves A before T (the at-hint prediction is then off; the pre-state one is not)
        acct(&mut r.e, a.vault1, vault(1_005 * SOL), 11, T0 + 11 * MS, Some(sig(41)), 20);
        acct(&mut r.e, a.vault0, vault(995_000_000_000_000), 11, T0 + 11 * MS + 1, Some(sig(41)), 21);
        r.e.timers(T0 + 15 * MS, &mut nop());
        // T commits exactly what the AMM v4 maths say on its pre-state (arbx-sizing's quote; the whole input enters the pc
        // vault, the output leaves the coin vault)
        let pre = r.e.leg_of(&a, false, quote::clock(0, 0), &[], Use::Third).unwrap();
        let q = pre.quote(10 * SOL).unwrap();
        let arbx_sizing::AnyLeg::Amm(l) = pre.any else { panic!() };
        let (r0, r1) = (l.r_out - q.out, l.r_in + q.spent);
        for (k, d, wv) in [(a.pool, ammv4_pool(), 22), (a.vault0, vault(r0), 23), (a.vault1, vault(r1), 24)] {
            acct(&mut r.e, k, d, 12, T0 + 20 * MS, Some(sig(40)), wv);
        }
        r.e.timers(T0 + 25 * MS, &mut nop());
        assert_eq!((r.e.counter("pred_scored"), r.e.counter("pred_exact")), (1, 1));
        r.rec.sync();
        let p = rec::read_jsonl(&r.dir, "predictions").unwrap();
        assert_eq!((p[0]["exact"].clone(), p[0]["pre_state"]["known"].clone(), p[0]["hint"]["exact"].clone()), (json!(true), json!(true), json!(false)),
            "exact on the pre-state, off at the hint (A moved in between): {}", p[0]);
        assert_eq!(p[0]["input_src"], json!("decoded"));
        // the ring no longer holds the pre-state: not scored
        let mut r = rig_with("acc-unknown", StrategyCfg { state_triggers: true, ..StrategyCfg::default() }, &[(1, 1_000), (2, 1_000)]);
        r.e.store.ring_versions = 2;
        make_ready(&mut r.e, T0);
        tx_ev(&mut r.e, shred_tx(sig(50), &[a.pool, a.vault0, a.vault1], Some((&a, SOL, false)), 11, T0 + 10 * MS));
        for k in 0..3u64 { acct(&mut r.e, a.vault1, vault((1_001 + k) * SOL), 11, T0 + 11 * MS + k, Some(sig(60 + k as u8)), 30 + k); }
        acct(&mut r.e, a.vault1, vault(1_100 * SOL), 12, T0 + 20 * MS, Some(sig(50)), 40);
        acct(&mut r.e, a.vault1, vault(1_101 * SOL), 12, T0 + 20 * MS + 1, Some(sig(61)), 41);
        acct(&mut r.e, a.vault1, vault(1_102 * SOL), 12, T0 + 20 * MS + 2, Some(sig(62)), 42);
        for (k, d, wv) in [(a.pool, ammv4_pool(), 43), (a.vault0, vault(999_000_000_000_000), 44)] { acct(&mut r.e, k, d, 12, T0 + 20 * MS + 3, Some(sig(50)), wv); }
        r.e.timers(T0 + 30 * MS, &mut nop());
        assert_eq!((r.e.counter("pred_scored"), r.e.counter("pred_pre_state_unknown")), (0, 1));
    }

    /// review WP-03 #7, WP-04: after an input the commit timers run only on an empty queue and only when a deadline is due;
    /// housekeeping every 10 s while the queue never empties
    #[test]
    fn after_an_input_the_timers_wait_for_an_empty_queue() {
        let ten = STATUS_EVERY_NS + 1;
        for (empty, since, due, want) in [(true, 0, true, TIMER_COMMIT), (false, 0, true, 0), (true, 0, false, 0), (false, ten, true, TIMER_HK),
            (true, ten, false, TIMER_COMMIT | TIMER_HK), (false, ten, false, TIMER_HK)] {
            assert_eq!(after_input_timers(empty, since, due), want, "empty {empty} since {since} due {due}");
        }
    }

    /// review WP-03 #6: the newest stored slot (status `tip_lag_slots_now`) follows pool accounts only
    #[test]
    fn store_slot_max_follows_pool_accounts_only() {
        let mut r = rig("slotmax");
        acct(&mut r.e, *CLOCK_SYSVAR, clock_data(5_000, 1), 5_000, T0, None, 1);
        assert!(r.e.store.get(&CLOCK_SYSVAR).is_some(), "stored");
        assert_eq!((r.e.store_slot_max, r.e.store.stream_slot_max), (0, 5_000), "the store's position counts the Clock, the pool gauge does not");
        acct(&mut r.e, meta(1).vault0, vault(1_000_000_000_000_000), 5_001, T0 + 1, None, 2);
        assert_eq!(r.e.store_slot_max, 5_001);
    }

    /// a state opportunity's stage times: the first update of its transaction (receive, dequeue), the evaluation and the
    /// decision; its caps line once the group's pools are priced; the decision line holds the state version and the
    /// route's age
    #[test]
    fn a_state_opportunity_and_its_records() {
        let mut r = rig_with("opp", StrategyCfg { state_triggers: true, budget_caps_sol: vec![0.5, 2.0], ..StrategyCfg::default() }, &[(1, 1_000), (2, 1_000)]);
        make_ready(&mut r.e, T0);
        let b = meta(2);
        let t = T0 + 20 * MS;
        tx_ev(&mut r.e, shred_tx(sig(3), &[b.vault0, b.vault1], None, 12, t - 15 * MS));
        acct(&mut r.e, b.vault1, vault(1_020 * SOL), 12, t, Some(sig(3)), 10);
        acct(&mut r.e, b.vault0, vault(990_000_000_000_000), 12, t + 100_000, Some(sig(3)), 11);
        assert_eq!(r.e.counter("state_opportunity"), 1);
        let o = r.e.opps.values().next().unwrap();
        assert_eq!((o.st.rx, o.st.engine), (t, t + 10_000), "the first update's receive and dequeue");
        assert!(o.st.decided >= o.st.resolved);
        for s in ["state_recv_to_engine", "state_engine_to_decided", "state_recv_to_decided", "first_shred→update_recv", "update_recv→commit"] {
            assert_eq!(r.e.lat.iter().find(|x| x.name == s).unwrap().n(), 1, "{s}");
        }
        let d = decisions(&r);
        assert_eq!((d[0]["verdict"].as_str(), d[0]["reason"].as_str(), d[0]["kind"].as_str()), (Some("reject"), Some("no_executor"), Some("commit")));
        assert!(d[0]["sv"]["h"].as_str().is_some_and(|h| h.len() == 16) && d[0]["route_age_ms"].is_number() && d[0]["band"].is_u64());
        assert_eq!(d[0]["routes"][d[0]["best"].as_u64().unwrap() as usize]["reason"], json!("best"));
        r.rec.sync();
        assert_eq!(rec::read_jsonl(&r.dir, "caps").unwrap().len(), 1, "the caps line after the group's evaluations");
        let oid = *r.e.opps.keys().next().unwrap();
        let ri = r.e.route_in(oid, SOL).unwrap();
        assert_eq!((ri.decision, ri.state_version != 0), (0, true), "RouteIn carries the decision and its state version");
    }

    /// Review WP-04 #13, the engine benchmark on the real shape: the Stage-0 ladder (10 rungs to 4.2 SOL) and caps, 80
    /// pools at 4 and then 8 per pair, the recorder on, and the real signer file's size (30,304 signers) behind the 10-s
    /// status line (review #4). Each transaction writes both vaults of one pool (W unknown); the timers 3.5 ms later
    /// (virtual time) resolve its group and evaluate the pool. The busy time of the two updates and the timers is measured
    /// per transaction (p50, p99, p99.9 in the test output; the review measured 15 / 22 µs at 4 pools and 22 / 31 µs at 8),
    /// and the timers calls that wrote a status line separately (about 25 ms each before review #4's fix). The bounds are
    /// generous: a CI machine runs other tests meanwhile
    #[test]
    fn engine_benchmark_stage0_shapes() {
        const TXS: u64 = 20_000;
        let mut x = 0x9e3779b97f4a7c15u64;
        let signers: HashMap<Pk, (u32, u32)> = (0..30_304u32).map(|n| {
            let mut k = [0u8; 32];
            for c in k.chunks_mut(8) { x ^= x << 13; x ^= x >> 7; x ^= x << 17; c.copy_from_slice(&x.to_le_bytes()); }
            (k, (n % 5, n % 3))
        }).collect();
        let signers = Arc::new(signers);
        for per_pair in [4u8, 8] {
            let dir = std::env::temp_dir().join(format!("arbx-engine-shapes-{per_pair}-{}-{}", std::process::id(), now_ns()));
            std::fs::create_dir_all(&dir).unwrap();
            let rec = rec::start(rec::Opts { dir: dir.clone(), run: "bench".into(), producer: "test".into(), cfg: Default::default(), feeds: vec![], monitor: false, echo: None }).unwrap();
            let mut reg = Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
            let mut store = Store::default();
            for n in 0..80u8 {
                let mut m = meta_k(n + 1);
                m.t0 = { let mut k = MINT; k[0] = n / per_pair; k[1] = 99; k };
                reg.by_pool.insert(m.pool, n as usize);
                reg.pairs.entry(pair_key(&m.t0, &WSOL)).or_insert_with(Vec::new).push(n as usize);
                store.update(m.pool, ammv4_pool(), 10, 1, None);
                store.update(m.vault0, vault(1_000_000_000_000_000), 10, 1, None);
                store.update(m.vault1, vault((1_000 + (n % per_pair) as u64 * 3) * SOL), 10, 1, None);
                reg.pools.push(m);
            }
            let cfg = StrategyCfg { state_triggers: true, sizes_sol: vec![0.005, 0.01, 0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 4.2],
                budget_caps_sol: vec![0.165, 2.1, 4.2, 8.4, 21.0, 42.0, 84.0], min_profit_lamports: 1, ..StrategyCfg::default() };
            let mut e = Engine::new_offline(Arc::new(reg), store, cfg);
            e.set_rec(rec.clone());
            e.min_tip = 1_000;
            e.tier_a_complete = true;
            e.set_signer_stats_out(&dir);
            e.signer_stats = (*signers).clone();
            e.signer_base = signers.clone();
            let mut t = T0;
            slot_ev(&mut e, 11, 0, Some(10), t);
            let (mut busy, mut status) = (Vec::with_capacity(TXS as usize), Vec::new());
            for k in 0..TXS {
                t += 4 * MS;
                let m = e.reg.pools[(k % 80) as usize].clone();
                let mut s = [0u8; 64];
                s[..8].copy_from_slice(&(k + 1).to_le_bytes());
                let lines = e.status_lines;
                let a = std::time::Instant::now();
                e.step(Event::Account { slot: 11, pubkey: m.vault1, owner: [0; 32], lamports: 0, data: vault((1_000 + k % 7) * SOL), t, txn: Some(s), write_version: 2 * k + 10,
                    is_startup: false, src: 0, aseq: 0, bank_id: None }, t + 10_000, &mut nop());
                e.step(Event::Account { slot: 11, pubkey: m.vault0, owner: [0; 32], lamports: 0, data: vault(999_000_000_000_000), t: t + 1, txn: Some(s), write_version: 2 * k + 11,
                    is_startup: false, src: 0, aseq: 0, bank_id: None }, t + 20_000, &mut nop());
                e.timers(t + 3_500_000, &mut nop());
                let ns = a.elapsed().as_nanos() as u64;
                busy.push(ns);
                if e.status_lines > lines { status.push(ns); }
            }
            assert_eq!(e.counter("evaluation"), TXS, "every transaction evaluated");
            rec.close();
            busy.sort_unstable();
            let p = |q: f64| busy[((busy.len() as f64 * q) as usize).min(busy.len() - 1)] / 1_000;
            let (p50, p99, p999) = (p(0.5), p(0.99), p(0.999));
            eprintln!("Stage-0 shape, {per_pair} pools per pair, recorder on: busy per transaction p50 {p50} µs, p99 {p99} µs, p99.9 {p999} µs; {} status lines {:?} µs; \
                opportunities {}", status.len(), status.iter().map(|x| x / 1_000).collect::<Vec<_>>(), e.counter("state_opportunity"));
            assert!(status.len() >= 7 && status.iter().min().copied().unwrap() < 5_000_000, "a status line costs the engine thread under 5 ms: {status:?} ns");
            assert!(p99 < 1_000 && p999 < 10_000, "p99 {p99} µs, p99.9 {p999} µs");
            let _ = std::fs::remove_dir_all(&dir);
        }
    }

    /// The merge of WP-03b and WP-08: the status line's `coverage` section carries WP-08's PoH gauge (F38):
    /// `poh_trigger_pct` (null until WP-05's attempt writer notes attempts) and `poh` with its counts, its 90% target and
    /// the PoH-capable feeds alive (a raw shred feed that delivered just now; a transaction stream is not one). Without
    /// the chain-fetch service its own coverage fields are absent, the gauge is there alone
    #[test]
    fn the_status_lines_coverage_carries_the_poh_gauge() {
        let mut r = rig("poh-gauge");
        let shred = Arc::new(FeedCounters::named("shred", "udp"));
        let tx = Arc::new(FeedCounters::named("tx", "yellowstone-tx"));
        shred.seen(12, now_ns());
        tx.seen(12, now_ns());
        r.e.set_feed_counters(vec![shred, tx], None);
        r.rec.open_now(rec::STATUS).unwrap();
        r.e.write_status(0);
        r.rec.sync();
        let st = rec::read_jsonl(&r.dir, "status").unwrap();
        let cov = &st.last().unwrap()["coverage"];
        assert_eq!((cov["poh_trigger_pct"].clone(), cov["poh"]["poh_feeds_alive_now"].as_u64(), cov["poh"]["target_pct"].as_f64(), cov["poh"]["target_met"].clone()),
            (Value::Null, Some(1), Some(90.0), Value::Null), "no attempts yet: no share, not judged: {cov}");
        assert!(cov.get("watched_with_tx_pct").is_none(), "no chain-fetch service in this test: {cov}");
    }

    /// WP-05 with WP-04 (`health.blockhash_*` was null): the status line's `health` shows what the send checks read, from
    /// journaled inputs only: the blockhash they would use (its age against the tip, its source, the commitment) and
    /// whether the target slot's leader is known; null until the WP-03b ring has said anything. Without an executor there
    /// is no Jito token age and no leader coverage
    #[test]
    fn the_status_lines_health_shows_the_send_checks_inputs() {
        let mut r = rig("send-health");
        r.rec.open_now(rec::STATUS).unwrap();
        slot_ev(&mut r.e, 11, 0, Some(10), T0);
        r.e.write_status(0);
        let head = json!({ "hash": crate::tx::b58(&[5u8; 32]), "slot": 9, "height": 7, "src": "slotidx", "commitment": "confirmed", "t_ns": T0 });
        r.e.step(Event::Input { kind: InputKind::BlockhashHead, data: Arc::new(head) }, T0 + MS, &mut nop());
        let leaders = vec![crate::tx::b58(&[9u8; 32]); 3];
        r.e.step(Event::Input { kind: InputKind::LeaderWindow, data: Arc::new(json!({ "start": 10, "leaders": leaders })) }, T0 + MS, &mut nop());
        r.e.write_status(0);
        r.rec.sync();
        let st = rec::read_jsonl(&r.dir, "status").unwrap();
        let (h0, h1) = (&st[0]["health"], &st[1]["health"]);
        assert_eq!((h0["blockhash_age_slots_now"].clone(), h0["blockhash_src_now"].clone(), h0["blockhash_commitment"].as_str()), (Value::Null, Value::Null, Some("confirmed")),
            "no blockhash yet: {h0}");
        assert_eq!((h1["blockhash_age_slots_now"].as_u64(), h1["blockhash_src_now"].as_str(), h1["leaders_ok"].as_bool()), (Some(2), Some("slotidx"), Some(true)), "{h1}");
        assert_eq!((h1["jito_token_age_s_now"].clone(), st[1]["coverage"]["leader_known_pct"].clone()), (Value::Null, Value::Null));
        assert_eq!((r.e.sendview.head.as_ref().map(|b| b.height), r.e.sendview.leader(12)), (Some(Some(7)), Some([9u8; 32])));
        // both came as engine inputs: journaled, so a replay sees the same
        r.rec.close();
        let kinds: Vec<u8> = crate::rec::journal::read_dir(&r.dir).unwrap().iter().filter_map(|x| match &x.body {
            crate::rec::journal::JBody::Input { kind, .. } => Some(*kind), _ => None }).collect();
        assert!(kinds.contains(&(InputKind::BlockhashHead as u8)) && kinds.contains(&(InputKind::LeaderWindow as u8)), "{kinds:?}");
    }

    /// PLAN WP-02 acceptance (F13), the engine benchmark, on WP-04's path: 100k synthetic account updates (50k
    /// transactions, each moving both vaults of one of 40 pools, its write set registered first, so its group completes
    /// on its second update) through `Engine::new_offline`, with the recorder on and off. With it on (commits, decisions,
    /// moves for every group) `state_recv_to_decided` p99 is within 5 µs of the run without it, both with no opportunity
    /// and with about 1% of updates opening one. Each mode runs three times, alternating; the best p99 of each is compared
    #[test]
    fn engine_benchmark_recorder_on_off() {
        const POOLS: u8 = 40;
        const TXS: u64 = 50_000;
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
                store.update(m.vault1, vault((1_000 + (n % 2) as u64 * 10) * SOL), 10, 1, None);
                reg.pools.push(m);
            }
            let mut e = Engine::new_offline(Arc::new(reg), store, StrategyCfg { state_triggers: true, min_profit_lamports: min_profit, budget_caps_sol: vec![0.5, 2.0, 10.0],
                ..StrategyCfg::default() });
            e.tier_a_complete = true;
            e
        }
        fn bench(rec: Rec, min_profit: u64, gaps: bool) -> (u64, u64, u64) {
            let mut e = engine(min_profit);
            e.set_rec(rec);
            let mut status = |_: &str| {};
            let t0 = now_ns();
            e.step(Event::Slot { slot: 11, status: 0, t: t0, parent: Some(10), dead_error: None, bank_id: None }, t0, &mut status);
            for k in 0..TXS {
                let i = (k % POOLS as u64) as usize;
                let m = e.reg.pools[i].clone();
                let mut sig = [0u8; 64];
                sig[..8].copy_from_slice(&k.to_le_bytes());
                let sol = if gaps && k % 200 == 0 { 1_100 } else { 1_000 + (k % 7) };
                // the write set first (a shred hint), so the group completes on its second update, inside `step`
                let _ = e.tracker.register(sig, vec![m.vault0, m.vault1], WSrc::Shred, now_ns());
                let t = now_ns();
                e.step(Event::Account { slot: 11, pubkey: m.vault1, owner: [0; 32], lamports: 0, data: vault(sol * SOL), t, txn: Some(sig), write_version: 2 * k + 10,
                    is_startup: false, src: 0, aseq: 2 * k, bank_id: None }, now_ns(), &mut status);
                e.step(Event::Account { slot: 11, pubkey: m.vault0, owner: [0; 32], lamports: 0, data: vault(999_000_000_000_000), t: now_ns(), txn: Some(sig),
                    write_version: 2 * k + 11, is_startup: false, src: 0, aseq: 2 * k + 1, bank_id: None }, now_ns(), &mut status);
                if gaps && k % 1_000 == 999 { e.finish(); }
            }
            let opps = e.counter("state_opportunity");
            e.finish();
            let s = e.series_mut("state_recv_to_decided").unwrap();
            assert_eq!(s.n(), TXS, "every transaction evaluated");
            (s.pct(0.5), s.pct(0.99), opps)
        }
        let dir = std::env::temp_dir().join(format!("arbx-engine-bench-{}-{}", std::process::id(), now_ns()));
        let best = |v: &[(u64, u64, u64)]| v.iter().map(|x| x.1).min().unwrap();
        // (review WP-04 #5: a decision no longer prices past the ladder's top rung, 1 SOL here: a 10% gap nets about 0.085 SOL)
        for (what, min_profit, gaps) in [("moves only", u64::MAX / 4, false), ("1% opportunities", 50_000_000, true)] {
            let (mut off, mut on) = (Vec::new(), Vec::new());
            for _ in 0..3 {
                off.push(bench(Rec::off(), min_profit, gaps));
                let rec = rec::start(rec::Opts { dir: dir.clone(), run: "bench".into(), producer: "test".into(), cfg: Default::default(), feeds: vec![], monitor: false, echo: None }).unwrap();
                on.push(bench(rec.clone(), min_profit, gaps));
                rec.close();
                assert_eq!(rec::read_text(&dir, "moves").unwrap().len() as u64, TXS, "a moves line per transaction");
                assert_eq!(rec::read_jsonl(&dir, "commits").unwrap().len() as u64, TXS, "a commits line per group");
                if gaps {
                    let opps = on.last().unwrap().2;
                    assert!((TXS / 200..=TXS / 50).contains(&opps), "about 1% of updates open an opportunity: {opps}");
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

    /// Review WP-06 #10: engine_init's `builder` reads back; absent or null is a journal written before WP-06 (its replay
    /// prices with its own rule); present but unreadable (a later schema, a corrupt record) makes the record unreadable,
    /// never the legacy rule in its place
    #[test]
    fn engine_init_builder_reads_back_or_refuses() {
        let model = BuilderModel { tips: crate::tip::TipModel::default(), cu: crate::cu_table::CuModel::default() };
        let init = EngineInit { min_tip: 1_000, strategy_sha256: "s".into(), builder: Some(model), ..Default::default() };
        assert_eq!(EngineInit::from_json(&init.json()).unwrap(), init);
        let mut v = init.json();
        v["builder"] = Value::Null;
        assert_eq!(EngineInit::from_json(&v).unwrap().builder, None, "a journal before WP-06");
        v.as_object_mut().unwrap().remove("builder");
        assert_eq!(EngineInit::from_json(&v).unwrap().builder, None);
        v["builder"] = json!({ "tips": "a later schema" });
        assert!(EngineInit::from_json(&v).is_none(), "unreadable: refused, not the legacy rule");
    }
}

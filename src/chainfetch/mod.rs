//! Chain fetch (PLAN WP-03b): wallet transactions, the watched-transaction backfill, the slot index and the blockhash
//! sources, as one service on the background runtime (`rt_bg`). Nothing here runs on the hot path: the producers hand
//! it notes through non-blocking taps (a bounded queue, `try_send`; a full queue drops the note and counts it), and
//! every RPC call is a bounded call (`rpc::Rpc::call_bounded`) on its role's providers (`[[chainfetch.provider]]`),
//! within their shared token buckets, where the slot index, the sample and the poll go before the backfill.
//!
//! - **Taps** (one line each at the producer): the state stream's account updates (their `txn`: D1 and our wallet's
//!   source (a)), confirmed and dead slots and block metas (`feeds::forward`); the transaction stream's records with
//!   their `idx` (`feeds::grpc::tx_stream_item`: covered signatures when the recorder took the record, the idx check);
//!   the engine's first copy of every unexecuted (shred, entries, deshred) transaction with its resolved keys
//!   (`Engine::process`: D2 candidates); our attempts' copies once fired (`Exec::decide`'s fire task: source (b), and the
//!   route's pools at priority 0). `note_jito_processed` (source (c): send/jito.rs on a `processed` result of ours,
//!   WP-05) and `note_entry_hash` (the shred/entries blockhash source, WP-08).
//! - **Records**: exec.jsonl (backfilled `rpc-backfill`, ours `rpc-wallet`, sampled `rpc-block-sample`; `idx_update`
//!   lines), wallet.jsonl, slotidx.jsonl, txfetch.jsonl, events.jsonl (`wallet_update_missing`,
//!   `blockhash_source_disagree`, `chainfetch_backlog`, `chainfetch_tap_drop`, and the watchdog's `chainfetch_dead`,
//!   `chainfetch_stalled`, `chainfetch_recovered`).
//! - **Engine inputs** (journaled as INPUT): `blockhash_head` (each change of the newest fresh confirmed blockhash),
//!   `wallet_tx` (each wallet record), `slotidx_missing` (D1 signatures absent from their confirmed block).
//! - **Status**: status.jsonl `chainfetch` and `coverage` (`status_sections`, read by the engine's status line).
//! - **Memory**: every map is bounded in time: signatures 15 minutes (`KEEP_NS`; one still in the backfill is kept until it
//!   leaves it, and the backfill gives every signature up 10 minutes after it was seen), the stream's records 3
//!   minutes, the wallet's 2 hours; `known_now` in the status shows it (review WP-03b #3).
//! - **Watchdog** (`start`): the service's task is watched; if it ends while the run goes on (a panic), the run is
//!   told (events.jsonl `chainfetch_dead`, a run.log WARNING, the `on_dead` callback: `arbx run` closes the SendGate for
//!   the rest of the segment, since wallet.jsonl is the reconciliation source); a service that stops publishing for 5 s
//!   is `chainfetch_stalled` (review WP-03b #12).
pub mod backfill;
pub mod blockhash;
pub mod slotidx;
pub mod txjson;
pub mod wallet;
#[cfg(test)]
mod tests;

use crate::config::ChainfetchCfg;
use crate::feeds::clock::now_ns;
use crate::feeds::{Event, InputKind};
use crate::rec::accounts::{role, Roles};
use crate::rec::{self, Rec, Record};
use crate::rpc::{Bounds, ErrClass, Fetched, Registry, Role, Rpc, RpcFailure};
use crate::tx::{b58, Pk};
use backfill::{Backfill, Item, Outcome};
use blockhash::{Commitment, Entry, Ring, Src};
use serde_json::{json, Map, Value};
use slotidx::{Indexed, Kind, Reply, SlotIndex};
use std::cmp::Reverse;
use std::collections::{BinaryHeap, HashMap, VecDeque};
use std::future::Future;
use std::pin::Pin;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::Relaxed};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Duration;
use txjson::RpcTx;
use wallet::{Wallet, F_ACCOUNT, F_JITO, F_OURS, F_SAMPLE, F_SHRED, F_SIGS, F_STREAM};

// ------------------------------------------------------------------ the taps

/// What a producer tells the service
#[derive(Clone, Debug)]
pub enum Note {
    /// a state-stream account update that names its transaction
    Account { pubkey: Pk, slot: u64, txn: [u8; 64], t: u64 },
    /// a state-stream slot status (processed, confirmed, dead)
    Slot { slot: u64, status: i32, parent: Option<u64>, t: u64 },
    /// a block meta (blockhash source `blocks_meta`)
    BlockMeta { slot: u64, hash: [u8; 32], height: Option<u64>, t: u64 },
    /// a transaction stream's record and its block index; `recorded`: the recorder took its exec.jsonl record (else the
    /// signature is not covered, and the backfill fetches it: review WP-03b #13)
    StreamTx { sig: [u8; 64], slot: u64, idx: u64, ok: bool, recorded: bool, t: u64 },
    /// the engine's first copy of an unexecuted transaction, with its resolved account keys
    Seen { sig: [u8; 64], slot: u64, feed: u16, keys: Vec<Pk>, t: u64 },
    /// an attempt of ours, fired: the signatures of its copies handed to the send paths, its route's accounts, and the
    /// slot it was aimed at (WP-05: its signatures are watched until a few slots past it)
    Ours { attempt: u64, sigs: Vec<[u8; 64]>, accounts: Vec<Pk>, target_slot: Option<u64>, t: u64 },
    /// a Jito `processed` result for a transaction of ours
    JitoProcessed { sig: [u8; 64], slot: Option<u64>, t: u64 },
    /// WP-07: a signature of ours known to have landed whose record the wallet service may not have fetched: the
    /// executor's expiry check found it first (its record settles the provisional money), or the ledger's
    /// reconciliation found it in its window (getSignaturesForAddress). Fetched at once
    Landed { sig: [u8; 64], slot: Option<u64>, attempt: Option<u64>, t: u64 },
    /// the last entry hash of a completed slot (its blockhash) from a shred or entries assembler
    EntryHash { slot: u64, hash: [u8; 32], feed: u16, t: u64 },
}

/// the taps' queue (notes); past it a note is dropped and counted
pub const TAP_CAP: usize = 65_536;

/// What the run's service shares with its taps and with the engine's status line
pub struct Shared {
    tx: crossbeam_channel::Sender<Note>,
    pub tap_dropped: AtomicU64,
    /// the service's task ended while the run went on (the watchdog sets it)
    pub dead: AtomicBool,
    published: Mutex<Published>,
    prev: Mutex<Published>,
    reg: Arc<Registry>,
}

impl Shared {
    pub fn new(reg: Arc<Registry>) -> (Arc<Shared>, crossbeam_channel::Receiver<Note>) { Shared::with_capacity(reg, TAP_CAP) }
    /// a service with a queue of `cap` notes (tests)
    pub fn with_capacity(reg: Arc<Registry>, cap: usize) -> (Arc<Shared>, crossbeam_channel::Receiver<Note>) {
        let (tx, rx) = crossbeam_channel::bounded(cap);
        (Arc::new(Shared { tx, tap_dropped: AtomicU64::new(0), dead: AtomicBool::new(false), published: Mutex::new(Published::default()),
            prev: Mutex::new(Published::default()), reg }), rx)
    }
    /// never blocks: a full queue drops the note (counted)
    pub fn send(&self, n: Note) { if self.tx.try_send(n).is_err() { self.tap_dropped.fetch_add(1, Relaxed); } }
    /// how long ago the service last published (None: not yet)
    pub fn published_age_ms(&self) -> Option<u64> {
        let t = self.published.lock().unwrap().t_ns;
        (t > 0).then(|| now_ns().saturating_sub(t) / 1_000_000)
    }
}

static SHARED: OnceLock<Arc<Shared>> = OnceLock::new();

/// make `s` the process's service (its taps); once
pub fn install(s: Arc<Shared>) -> bool { SHARED.set(s).is_ok() }

#[cfg(test)]
thread_local! {
    /// tests: the taps of this thread go to this service instead of the process's (review WP-03b #21: the producer taps
    /// can be tested in this binary, where no service is ever installed)
    static TEST_SHARED: std::cell::RefCell<Option<Arc<Shared>>> = const { std::cell::RefCell::new(None) };
}

/// tests: run `f` with this thread's taps going to `s`
#[cfg(test)]
pub fn with_test_service<R>(s: Arc<Shared>, f: impl FnOnce() -> R) -> R {
    TEST_SHARED.with(|t| *t.borrow_mut() = Some(s));
    let r = f();
    TEST_SHARED.with(|t| *t.borrow_mut() = None);
    r
}

/// the service the taps of this thread feed, if any (one atomic load outside tests)
#[inline]
fn with_shared(f: impl FnOnce(&Shared)) {
    #[cfg(test)]
    {
        if let Some(s) = TEST_SHARED.with(|t| t.borrow().clone()) { f(&s); return; }
    }
    if let Some(s) = SHARED.get() { f(s); }
}

/// The state stream's item (`feeds::forward`, state stream only): account updates with their transaction, the
/// processed / confirmed / dead slot statuses, block metas
#[inline]
pub fn note_state(it: &crate::feeds::grpc::Item) {
    with_shared(|s| {
        use crate::feeds::grpc::Item;
        let n = match it {
            Item::Account { slot, pubkey, txn: Some(txn), t, .. } => Note::Account { pubkey: *pubkey, slot: *slot, txn: *txn, t: *t },
            Item::Slot { slot, status, parent, t, .. } if matches!(status, 0 | 1 | 6) => Note::Slot { slot: *slot, status: *status, parent: *parent, t: *t },
            Item::BlockMeta(b) => Note::BlockMeta { slot: b.slot, hash: b.blockhash, height: b.block_height, t: b.t },
            _ => return,
        };
        s.send(n);
    });
}

/// A transaction stream handed `sig`'s exec.jsonl record to the recorder (`recorded`: it was queued) at `idx` in `slot`
/// (`feeds::grpc::tx_stream_item`)
#[inline]
pub fn note_stream_tx(sig: &[u8], slot: u64, idx: u64, ok: bool, recorded: bool) {
    let Ok(sig) = <[u8; 64]>::try_from(sig) else { return };
    with_shared(|s| s.send(Note::StreamTx { sig, slot, idx, ok, recorded, t: now_ns() }));
}

/// The engine's first copy of a transaction with its resolved keys (`Engine::process`); executed copies (the
/// transaction streams) are left out: their records come from `note_stream_tx`
#[inline]
pub fn note_seen(a: &crate::feeds::Arrival, keys: &[Pk]) {
    if a.executed.is_some() { return; }
    with_shared(|s| s.send(Note::Seen { sig: a.tx.sig, slot: a.slot, feed: a.feed, keys: keys.to_vec(), t: a.t_rx }));
}

/// An attempt of ours, fired (`Exec::decide`'s fire task, after the send): the signatures of the copies that left
/// (`t_sent` set: wallet source (b)), its route's accounts (backfill priority 0) and its target slot: WP-05 narrows the
/// watch of its signatures to `wallet::WATCH_SLOTS_AFTER_TARGET` slots past it (a bundle lands in its leader's window or
/// never; the executor's own expiry check covers the rest of the blockhash's life)
pub fn note_fired(attempt: u64, copies: &[crate::send::Sent], accounts: &[Pk], target_slot: Option<u64>) {
    with_shared(|s| {
        let sigs: Vec<[u8; 64]> = copies.iter().filter(|c| c.t_sent > 0).filter_map(|c| c.sig.as_deref())
            .filter_map(|x| bs58::decode(x).into_vec().ok()).filter_map(|v| <[u8; 64]>::try_from(v).ok()).collect();
        s.send(Note::Ours { attempt, sigs, accounts: accounts.to_vec(), target_slot, t: now_ns() });
    });
}

/// A Jito `processed` result of a transaction of ours (source (c); send/jito.rs calls it, WP-05)
pub fn note_jito_processed(sig: &[u8; 64], slot: Option<u64>) { with_shared(|s| s.send(Note::JitoProcessed { sig: *sig, slot, t: now_ns() })); }

/// WP-07: a signature of ours that landed (the executor's expiry check found it before its record; the ledger's
/// reconciliation found it in its window): its record is fetched at once (`found_by` `executor_status`)
pub fn note_landed(sig: &[u8; 64], slot: Option<u64>, attempt: Option<u64>) { with_shared(|s| s.send(Note::Landed { sig: *sig, slot, attempt, t: now_ns() })); }

/// The last entry hash of a completed slot from a shred or entries assembler (blockhash source `entries`): a shred feed's
/// slot walked whole (feeds/shred.rs, at its last shred), an entries feed's slot followed from its first entry (feeds/mod.rs
/// `forward`, when the next slot starts)
pub fn note_entry_hash(slot: u64, hash: [u8; 32], feed: u16) { with_shared(|s| s.send(Note::EntryHash { slot, hash, feed, t: now_ns() })); }

/// WP-07 (review #3): how many wallet records the service gave up on so far (None: no service running); the ledger's
/// money view is stale from a new give-up until a snapshot asked for after it
pub fn wallet_gave_up_total() -> Option<u64> {
    let mut out = None;
    with_shared(|s| out = Some(s.published.lock().unwrap_or_else(|e| e.into_inner()).wallet_gave_up));
    out
}

/// status.jsonl `chainfetch` and `coverage` (MEASUREMENT §4.8): null while the service is not running
pub fn status_sections() -> (Value, Value) {
    let mut out = (Value::Null, Value::Null);
    with_shared(|s| out = s.status_json());
    out
}

// ------------------------------------------------------------------ the RPC side

pub type BoxFut = Pin<Box<dyn Future<Output = Result<Fetched, RpcFailure>> + Send>>;

/// How the service reaches the chain: one bounded call for a role (the real one: [`RoleClients`]; tests serve
/// recorded replies)
pub trait Chain: Send + Sync + 'static {
    fn call(&self, role: Role, method: &'static str, params: Value, b: Bounds) -> BoxFut;
    /// what a role's providers have spare after every other role's recent requests, requests/s (None: unknown or
    /// unlimited). The backfill's rate follows it
    fn spare_rps(&self, _role: Role) -> Option<f64> { None }
}

/// One client per chain-fetch role, on the providers `[[chainfetch.provider]]` gives it (in order)
pub struct RoleClients { by: HashMap<Role, Rpc> }

impl RoleClients {
    pub fn new(root: &Rpc, cfg: &ChainfetchCfg) -> RoleClients {
        let all = root.names();
        RoleClients { by: Role::FETCH.iter().map(|r| (*r, root.only_role(*r, &cfg.providers_for(r.as_str(), &all)))).collect() }
    }
    pub fn names(&self, r: Role) -> Vec<String> { self.by.get(&r).map(|c| c.names()).unwrap_or_default() }
    /// the summed `max_rps` of a role's providers (INFINITY: one of them has no limit)
    pub fn cap(&self, r: Role) -> f64 {
        let Some(c) = self.by.get(&r) else { return 0.0 };
        c.names().iter().map(|n| { let l = c.registry().limiter(n); if l.rate > 0.0 { l.rate } else { f64::INFINITY } }).sum()
    }
}

impl Chain for RoleClients {
    fn call(&self, role: Role, method: &'static str, params: Value, b: Bounds) -> BoxFut {
        let c = self.by.get(&role).cloned();
        Box::pin(async move {
            match c {
                Some(c) if !c.is_empty() => c.call_bounded(method, params, b).await,
                _ => Err(RpcFailure::new(ErrClass::NoProvider, None, format!("{} {method}: no provider for the role", role.as_str()))),
            }
        })
    }
    fn spare_rps(&self, role: Role) -> Option<f64> {
        let c = self.by.get(&role)?;
        let mut sum = 0.0;
        for n in c.names() { sum += c.registry().spare_rps(&n, role)?; }
        Some(sum)
    }
}

// ------------------------------------------------------------------ the service

/// What the service needs
pub struct Opts {
    pub cfg: ChainfetchCfg,
    /// our wallet (None: no wallet transactions)
    pub wallet: Option<Pk>,
    pub route_program: Pk,
    /// every watched account's role (shared with the state stream; the engine adds the DLMM bin arrays it follows)
    pub roles: Arc<Roles>,
    pub rec: Rec,
    /// the engine's channel (INPUT events); None: no engine
    pub back: Option<crossbeam_channel::Sender<Event>>,
    pub chain: Arc<dyn Chain>,
    /// the backfill providers' summed max_rps (INFINITY: unlimited): the most the backfill ever asks for
    pub backfill_cap: f64,
    /// FT-000 (S1-12): the previous segment's wallet cursor (signature, slot): source (d) lists only what is newer
    pub wallet_cursor: Option<(String, u64)>,
}

/// the gauges and totals the service publishes (once a second) for the status line
#[derive(Clone, Default, Debug)]
pub struct Published {
    pub need_rps: f64, pub have_rps: f64, pub target_rps: f64, pub cap_rps: Option<f64>, pub cap_max_rps: Option<f64>, pub backlog: usize, pub inflight: usize,
    pub queued: u64, pub dropped: u64, pub fetched: u64, pub gave_up: u64, pub expired: u64, pub refused: u64, pub deferred: u64, pub dup_records: u64,
    pub slotidx_lag: Option<u64>, pub slotidx_pending: usize, pub slot_ok: u64, pub slot_skipped: u64, pub slot_error: u64, pub slot_dropped: u64, pub slot_refused: u64,
    pub idx_n: u64, pub idx_mismatch: u64, pub idx_updates: u64, pub missing_sigs: u64, pub d2_landed: u64, pub d2_absent: u64, pub d2_unknown: u64,
    /// FT-000 (S1-2): stream comparisons listed below / above the stream's index; lines by position kind; positions given
    /// as ranks only; the providers whose lists leave votes out
    pub idx_below: u64, pub idx_above: u64, pub kind_block_index: u64, pub kind_nonvote_rank: u64, pub kind_unverified: u64, pub rank_only: u64,
    pub votes_omitted_by: Vec<String>,
    pub wallet_pending: usize, pub wallet_watch: usize, pub wallet_fetched: u64, pub wallet_gave_up: u64, pub wallet_missing: u64, pub wallet_unlanded: u64,
    pub wallet_unlanded_by_slot: u64, pub wallet_landed_by_status: u64, pub wallet_status_calls: u64,
    pub bh: Option<(String, u64, Option<u64>, u64)>, pub bh_disagree: u64, pub bh_polls: u64, pub bh_poll_skipped: u64,
    pub unseen: Option<(u64, u64, u64)>,
    pub denom: u64, pub with_tx: u64, pub with_idx: u64, pub wallet_n: u64, pub wallet_with: u64, pub slots_n: u64, pub slots_with: u64,
    pub known: usize, pub stream: usize, pub wallet_sigs: usize,
    pub tap_dropped: u64,
    /// when the service last published (a service that died shows a growing age)
    pub t_ns: u64,
}

fn r2(x: f64) -> f64 { (x * 100.0).round() / 100.0 }
fn pct(num: u64, den: u64) -> Value { if den == 0 { Value::Null } else { json!(r2(num as f64 * 100.0 / den as f64)) } }

impl Shared {
    /// status.jsonl `chainfetch` and `coverage`: gauges (`_now`) as published, deltas since the previous call, coverage
    /// over the signatures (slots) whose minute ended since then
    pub fn status_json(&self) -> (Value, Value) {
        let mut p = self.published.lock().unwrap().clone();
        p.tap_dropped = self.tap_dropped.load(Relaxed);
        let mut prev = self.prev.lock().unwrap();
        let d = |a: u64, b: u64| a.saturating_sub(b);
        let age = (p.t_ns > 0).then(|| now_ns().saturating_sub(p.t_ns) / 1_000_000);
        let cf = json!({
            "service_ok_now": !self.dead.load(Relaxed) && age.is_none_or(|a| a <= STALL_MS),
            "need_rps_now": r2(p.need_rps), "have_rps_now": r2(p.have_rps), "target_rps_now": r2(p.target_rps), "cap_rps_now": p.cap_rps.map(r2),
            "cap_max_rps_now": p.cap_max_rps.map(r2),
            "backlog_now": p.backlog, "inflight_now": p.inflight, "queued_delta": d(p.queued, prev.queued), "dropped_delta": d(p.dropped, prev.dropped),
            "fetched_delta": d(p.fetched, prev.fetched), "gave_up_delta": d(p.gave_up, prev.gave_up), "expired_delta": d(p.expired, prev.expired),
            "refused_delta": d(p.refused, prev.refused), "deferred_delta": d(p.deferred, prev.deferred), "dup_records_delta": d(p.dup_records, prev.dup_records),
            "slotidx_lag_slots_now": p.slotidx_lag, "slotidx_pending_now": p.slotidx_pending,
            "slotidx_delta": { "ok": d(p.slot_ok, prev.slot_ok), "skipped": d(p.slot_skipped, prev.slot_skipped), "error": d(p.slot_error, prev.slot_error),
                "dropped": d(p.slot_dropped, prev.slot_dropped), "refused": d(p.slot_refused, prev.slot_refused) },
            "idx_check_delta": { "n": d(p.idx_n, prev.idx_n), "mismatches": d(p.idx_mismatch, prev.idx_mismatch), "below": d(p.idx_below, prev.idx_below),
                "above": d(p.idx_above, prev.idx_above) },
            "idx_updates_delta": d(p.idx_updates, prev.idx_updates), "missing_delta": d(p.missing_sigs, prev.missing_sigs),
            "d2_landed_delta": d(p.d2_landed, prev.d2_landed), "d2_absent_delta": d(p.d2_absent, prev.d2_absent), "d2_unknown_delta": d(p.d2_unknown, prev.d2_unknown),
            "wallet_pending_now": p.wallet_pending, "wallet_watch_now": p.wallet_watch, "wallet_fetched_delta": d(p.wallet_fetched, prev.wallet_fetched),
            "wallet_gave_up_delta": d(p.wallet_gave_up, prev.wallet_gave_up), "wallet_unlanded_delta": d(p.wallet_unlanded, prev.wallet_unlanded),
            "wallet_unlanded_by_slot_delta": d(p.wallet_unlanded_by_slot, prev.wallet_unlanded_by_slot),
            "wallet_landed_by_status_delta": d(p.wallet_landed_by_status, prev.wallet_landed_by_status),
            "wallet_status_calls_delta": d(p.wallet_status_calls, prev.wallet_status_calls),
            "blockhash": { "src_now": p.bh.as_ref().map(|b| b.0.clone()), "slot_now": p.bh.as_ref().map(|b| b.1), "age_slots_now": p.bh.as_ref().and_then(|b| b.2),
                "age_ms_now": p.bh.as_ref().map(|b| b.3), "disagree_delta": d(p.bh_disagree, prev.bh_disagree), "polls_delta": d(p.bh_polls, prev.bh_polls),
                "poll_skipped_delta": d(p.bh_poll_skipped, prev.bh_poll_skipped) },
            "known_now": p.known, "stream_now": p.stream, "wallet_sigs_now": p.wallet_sigs,
            "tap_dropped_delta": d(p.tap_dropped, prev.tap_dropped),
            "published_age_ms_now": age,
            "by_role": self.reg.by_role_json("status"),
        });
        // FT-000 (S1-2): what the slot index's positions were (its lines by kind, positions kept as ranks only, the
        // providers whose lists leave the votes out)
        let mut cf = cf;
        cf["slotidx_pos_kind_delta"] = json!({ "block_index": d(p.kind_block_index, prev.kind_block_index), "nonvote_rank": d(p.kind_nonvote_rank, prev.kind_nonvote_rank),
            "unverified": d(p.kind_unverified, prev.kind_unverified) });
        cf["slotidx_rank_only_delta"] = json!(d(p.rank_only, prev.rank_only));
        cf["slotidx_votes_omitted_by_now"] = json!(p.votes_omitted_by.clone());
        let dn = d(p.denom, prev.denom);
        let wn = d(p.wallet_n, prev.wallet_n);
        let sn = d(p.slots_n, prev.slots_n);
        let cov = json!({
            "watched_with_tx_pct": pct(d(p.with_tx, prev.with_tx), dn), "watched_with_idx_pct": pct(d(p.with_idx, prev.with_idx), dn), "denominator_delta": dn,
            "wallet_with_tx_pct": pct(d(p.wallet_with, prev.wallet_with), wn), "wallet_delta": wn, "wallet_update_missing_delta": d(p.wallet_missing, prev.wallet_missing),
            "slotidx_pct": pct(d(p.slots_with, prev.slots_with), sn), "slots_delta": sn,
            "unseen_share_sample": p.unseen.and_then(|(_, w, u)| (w > 0).then(|| (u as f64 / w as f64 * 10_000.0).round() / 10_000.0)),
            "unseen_sample": p.unseen.map(|(s, w, u)| json!({ "slot": s, "watched": w, "unseen": u })),
            "poh_trigger_pct": null, "leader_known_pct": null,
        });
        *prev = p;
        (cf, cov)
    }
}

/// where a signature's exec.jsonl record came from
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum RecSrc { Stream, Backfill, Wallet, Sample }

/// What the service knows of one signature of the denominator (or a D2 candidate)
#[derive(Clone, Debug)]
struct Sig {
    /// first seen (monotonic ns; wall clock)
    first: u64,
    slot: u64,
    bits: u8,
    rec: Option<RecSrc>,
    idx: Option<u64>,
    /// its exec.jsonl record carried the idx (else the slot index's position goes out as an `idx_update`)
    rec_idx: bool,
    t_exec: Option<u64>,
    t_idx: Option<u64>,
    /// in the coverage denominator (D1, or a D2 the slot index found in its block)
    denom: bool,
    prio: u8,
    /// in the backfill (queued, in flight or waiting to retry)
    queued: bool,
    /// absent from its slot's confirmed block (or the slot was skipped): written on an abandoned fork, never landed
    forked: bool,
    /// its first fetch waited for its slot's confirmation (counted once)
    deferred: bool,
}

impl Sig {
    fn new(first: u64, slot: u64, bits: u8, prio: u8) -> Sig {
        Sig { first, slot, bits, rec: None, idx: None, rec_idx: false, t_exec: None, t_idx: None, denom: false, prio, queued: false, forked: false, deferred: false }
    }
}

/// one RPC job's result
struct Done { job: Job, queued_ns: u64, r: Result<Fetched, RpcFailure> }
enum Job { Wallet([u8; 64]), Statuses(Vec<[u8; 64]>), Backfill(Item), Sigs { page: u32, since_unix: i64 }, Block(u64), Sample(u64), Poll }

/// the roles whose accounts make a transaction "watched" for D2 and the coverage sampler (pool-specific state and the
/// wallet; mints, configs and the fee config are read by every pool of a venue)
fn touch_role(r: u8) -> bool { matches!(r, role::POOL | role::VAULT | role::DLMM_BIN_ARRAY | role::DLMM_BITMAP_EXT | role::CLMM_TICK_ARRAY | role::WALLET | role::WALLET_TOKEN_ACCOUNT) }
fn pool_role(r: u8) -> bool { matches!(r, role::POOL | role::VAULT | role::DLMM_BIN_ARRAY | role::DLMM_BITMAP_EXT | role::CLMM_TICK_ARRAY) }
/// a call refused for want of a token: nothing was sent (no txfetch.jsonl line; the registry counts it as `rate_budget`)
fn refused<T>(r: &Result<T, RpcFailure>) -> bool { matches!(r, Err(e) if e.class == ErrClass::Budget) }

/// FT-000 (S1-12): the wallet cursor's file in a run directory
pub const WALLET_CURSOR: &str = "wallet-cursor.json";

/// The newest sibling segment's wallet cursor for `wallet` (`[chainfetch] wallet_cursor`: "auto" among `dir`'s siblings,
/// a path, or "" for none): (signature, slot, the file)
pub fn read_wallet_cursor(setting: &str, dir: &std::path::Path, wallet: &str) -> Option<(String, u64, std::path::PathBuf)> {
    let file = match setting {
        "" => return None,
        "auto" => {
            let parent = dir.parent()?;
            let mut best: Option<(std::time::SystemTime, std::path::PathBuf)> = None;
            for e in std::fs::read_dir(parent).ok()?.flatten() {
                let p = e.path().join(WALLET_CURSOR);
                if e.path() == dir || !p.is_file() { continue; }
                let Ok(t) = std::fs::metadata(&p).and_then(|m| m.modified()) else { continue };
                if best.as_ref().is_none_or(|b| t > b.0) { best = Some((t, p)); }
            }
            best?.1
        }
        p => std::path::PathBuf::from(p),
    };
    let v: Value = serde_json::from_slice(&std::fs::read(&file).ok()?).ok()?;
    if v["wallet"].as_str() != Some(wallet) || !v["schema"].as_str().is_some_and(|x| x.starts_with("arbx.wallet-cursor/1.")) { return None; }
    Some((v["sig"].as_str()?.to_string(), v["slot"].as_u64()?, file))
}

/// a blockhash older than this is not offered (it expires after 150 blocks, about a minute)
const BH_MAX_AGE_NS: u64 = 60_000_000_000;
/// the poll is skipped while another source gave a confirmed blockhash this fresh, this close to the chain's tip
const POLL_SKIP_AGE_NS: u64 = 1_000_000_000;
const POLL_SKIP_SLOTS: u64 = 8;
/// signatures are kept this long (the 10-minute idx window, plus margin)
const KEEP_NS: u64 = 900_000_000_000;
/// the transaction stream's records are matched for this long
const STREAM_KEEP_NS: u64 = 180_000_000_000;
/// our attempts' route accounts keep priority 0 this long
const OURS_KEEP_NS: u64 = 120_000_000_000;
/// a backfill's first try waits at most this long after the signature was seen for its slot to be confirmed
const CONFIRM_WAIT_NS: u64 = 20_000_000_000;
/// the watched signatures' getSignatureStatuses, at most this often
const STATUS_EVERY_NS: u64 = 2_000_000_000;
/// our wallet's getTransaction calls in flight at most
const WALLET_MAX_INFLIGHT: usize = 4;
/// the backfill takes at most this share of what its providers have spare (headroom for the others' bursts)
const SPARE_SHARE: f64 = 0.9;
/// a service that has not published for this long is stalled
pub const STALL_MS: u64 = 5_000;
const SEC: u64 = 1_000_000_000;

pub struct Service {
    cfg: ChainfetchCfg,
    roles: Arc<Roles>,
    rec: Rec,
    back: Option<crossbeam_channel::Sender<Event>>,
    chain: Arc<dyn Chain>,
    shared: Arc<Shared>,
    base: tokio::time::Instant,
    wallet: Option<Wallet>,
    wallet58: Option<String>,
    known: HashMap<[u8; 64], Sig>,
    known_order: VecDeque<(u64, [u8; 64])>,
    stream: HashMap<[u8; 64], (u64, u64, u64)>,
    stream_order: VecDeque<(u64, [u8; 64])>,
    checks: BinaryHeap<Reverse<(u64, [u8; 64])>>,
    cov_q: VecDeque<(u64, [u8; 64])>,
    ours_accounts: HashMap<Pk, u64>,
    ours_pools: HashMap<u32, u64>,
    bf: Backfill,
    /// the backfill providers' configured capacity (its cap never exceeds it)
    cap_cfg: f64,
    si: SlotIndex,
    ring: Ring,
    last_head: Option<[u8; 32]>,
    /// arbx-fast: the last processed head handed to the engine (the shred entries source, newer than the confirmed head)
    last_processed: Option<[u8; 32]>,
    started: bool,
    next_sigs: u64,
    sigs_inflight: bool,
    next_status: u64,
    status_inflight: bool,
    wallet_inflight: usize,
    next_sample: u64,
    sample_inflight: bool,
    next_poll: u64,
    poll_inflight: bool,
    next_tick: u64,
    last_backlog_event: Option<u64>,
    last_tap_event: (u64, u64),
    /// FT-000 (S1-12): the newest cursor so far, (slot, signature, carried: the one this segment started from), whether
    /// `wallet-cursor.json` holds it, and when it is next looked at
    cursor: Option<(u64, String, bool)>,
    cursor_written: bool,
    next_cursor_write: u64,
    unseen: Option<(u64, u64, u64)>,
    // totals
    denom_n: u64, with_tx: u64, with_idx: u64, dup_records: u64, idx_updates: u64, missing_sigs: u64, d2_landed: u64, d2_absent: u64, d2_unknown: u64,
    deferred: u64, bh_polls: u64, bh_poll_skipped: u64, status_calls: u64,
    /// FT-000 (S1-2): tracked positions a slot index line gave as non-vote ranks (or unverified): not written as `idx`
    rank_only: u64,
}

impl Service {
    pub fn new(o: Opts, shared: Arc<Shared>) -> Service {
        let wallet = o.wallet.map(|w| Wallet::new(w, crate::build::ata_of(&w, &crate::venues::WSOL, &crate::pda::TOKEN_PROGRAM), o.route_program));
        let bf = Backfill::new(o.cfg.after_ms, o.cfg.max_backlog, o.cfg.rps.fixed(), o.backfill_cap, 16);
        let mut wallet = wallet;
        if let Some(w) = wallet.as_mut() { w.until = o.wallet_cursor.as_ref().map(|c| c.0.clone()); }
        let first_sample = o.cfg.sample_every_s.max(30) * SEC;
        Service { wallet58: o.wallet.map(|w| b58(&w)), wallet, cfg: o.cfg, roles: o.roles, rec: o.rec, back: o.back, chain: o.chain, shared, base: tokio::time::Instant::now(),
            known: HashMap::new(), known_order: VecDeque::new(), stream: HashMap::new(), stream_order: VecDeque::new(), checks: BinaryHeap::new(), cov_q: VecDeque::new(),
            ours_accounts: HashMap::new(), ours_pools: HashMap::new(), bf, cap_cfg: if o.backfill_cap > 0.0 { o.backfill_cap } else { f64::INFINITY },
            si: SlotIndex::new(4, 3_000), ring: Ring::new(512), last_head: None, last_processed: None, started: false,
            next_sigs: 30 * SEC, sigs_inflight: false, next_status: 0, status_inflight: false, wallet_inflight: 0, next_sample: first_sample, sample_inflight: false,
            next_poll: 0, poll_inflight: false, next_tick: 0, last_backlog_event: None, last_tap_event: (0, 0), cursor: o.wallet_cursor.map(|(sig, slot)| (slot, sig, true)), cursor_written: false,
            next_cursor_write: 0, unseen: None, denom_n: 0, with_tx: 0, with_idx: 0,
            dup_records: 0, idx_updates: 0, missing_sigs: 0, d2_landed: 0, d2_absent: 0, d2_unknown: 0, deferred: 0, bh_polls: 0, bh_poll_skipped: 0, status_calls: 0,
            rank_only: 0 }
    }

    /// the service's monotonic clock, ns since it started (tokio's: a paused clock in tests)
    fn mono(&self) -> u64 { self.base.elapsed().as_nanos() as u64 }

    /// Run until `stop`: notes every 10 ms, RPC results as they come
    pub async fn run(mut self, rx: crossbeam_channel::Receiver<Note>, stop: Arc<AtomicBool>) {
        let (dtx, mut drx) = tokio::sync::mpsc::unbounded_channel::<Done>();
        let mut tick = tokio::time::interval(Duration::from_millis(10));
        tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        loop {
            tokio::select! {
                _ = tick.tick() => {
                    if stop.load(Relaxed) { break; }
                    let now = self.mono();
                    for _ in 0..20_000 { match rx.try_recv() { Ok(n) => self.on_note(n, now), Err(_) => break } }
                    self.timers(now, &dtx);
                }
                Some(d) = drx.recv() => { let now = self.mono(); self.on_done(d, now, &dtx); }
            }
        }
        let now = self.mono();
        self.publish(now);
        self.write_cursor(true);
    }

    /// FT-000 (S1-12): `wallet-cursor.json` in the run directory (the next segment's (d) starts after it): this segment's
    /// cursor when it has one, else the one it started from; written when it changes (at most every 10 s) and at the end
    fn write_cursor(&mut self, last: bool) {
        let Some(w) = &self.wallet else { return };
        let Some(dir) = self.rec.dir().map(|d| d.to_path_buf()) else { return };
        // the cursor only moves forward (its signatures may be forgotten after 2 h: the newest one stays)
        if let Some((slot, sig)) = w.cursor() {
            if self.cursor.as_ref().is_none_or(|c| slot > c.0) { self.cursor = Some((slot, b58s(&sig), false)); self.cursor_written = false; }
        }
        let Some((slot, sig, carried)) = self.cursor.clone() else { return };
        if self.cursor_written || (carried && !last) { return; }
        self.cursor_written = true;
        let v = json!({ "schema": "arbx.wallet-cursor/1.0", "wallet": b58(&w.wallet), "sig": sig, "slot": slot, "carried": carried, "t_ns": now_ns() });
        self.rec.task(move || { let _ = crate::control::write_atomic(&dir.join(WALLET_CURSOR), v.to_string().as_bytes()); });
    }

    fn spawn(&self, job: Job, role: Role, method: &'static str, params: Value, b: Bounds, dtx: &tokio::sync::mpsc::UnboundedSender<Done>) {
        let fut = self.chain.call(role, method, params, b);
        let (dtx, queued_ns) = (dtx.clone(), now_ns());
        tokio::spawn(async move { let r = fut.await; let _ = dtx.send(Done { job, queued_ns, r }); });
    }

    fn input(&self, kind: InputKind, v: Value) { if let Some(b) = &self.back { let _ = b.send(Event::Input { kind, data: Arc::new(v) }); } }

    /// a known signature (new: with its order record, so it is forgotten in time)
    fn know(&mut self, sig: [u8; 64], e: Sig, now: u64) -> &mut Sig {
        if !self.known.contains_key(&sig) { self.known_order.push_back((now, sig)); }
        self.known.entry(sig).or_insert(e)
    }

    /// signatures that left the backfill without a fetch (dropped past max_backlog, given up at 10 minutes) are not
    /// queued any more: their entries are forgotten in time (review WP-03b #3)
    fn drain_left(&mut self) {
        for (sig, _) in self.bf.take_left() { if let Some(e) = self.known.get_mut(&sig) { e.queued = false; } }
    }

    // ---------------------------------------------------------------- notes

    pub fn on_note(&mut self, n: Note, now: u64) {
        match n {
            Note::Account { pubkey, slot, txn, t: _ } => self.on_account(pubkey, slot, txn, now),
            Note::Slot { slot, status, parent, t: _ } => {
                self.ring.note_slot(slot);
                self.started = true;
                match status {
                    1 => {
                        for s in self.si.confirmed(slot, parent, now) {
                            let ix = self.si.skipped_by_parent(s, now, now_ns());
                            self.apply_index(ix, now);
                        }
                    }
                    6 => self.si.dead(slot),
                    _ => {}
                }
            }
            Note::BlockMeta { slot, hash, height, t } => self.ring_insert(Entry { hash, slot, height, src: Src::BlocksMeta, commitment: Commitment::Processed, t_ns: t }),
            Note::StreamTx { sig, slot, idx, ok: _, recorded, t: _ } => {
                // the idx check either way; covered only when the recorder took the record
                self.si.stream_idx(slot, sig, idx);
                if !recorded { return; }
                self.stream.insert(sig, (slot, idx, now));
                self.stream_order.push_back((now, sig));
                if let Some(e) = self.known.get_mut(&sig) {
                    e.bits |= F_STREAM;
                    match e.rec {
                        None => {
                            e.rec = Some(RecSrc::Stream);
                            e.idx = Some(idx);
                            e.rec_idx = true;
                            e.t_exec = Some(now);
                            e.t_idx = Some(now);
                            if e.queued { e.queued = false; self.bf.remove(&sig); }
                        }
                        Some(RecSrc::Stream) => {}
                        // the stream delivered it after another source wrote its line: two lines for one signature
                        Some(_) => self.dup_records += 1,
                    }
                }
            }
            Note::Seen { sig, slot, feed: _, keys, t: _ } => {
                let mut touch = false;
                let mut prio = backfill::PRIO_REST;
                for k in &keys {
                    if self.ours_accounts.get(k).is_some_and(|u| *u > now) { touch = true; prio = backfill::PRIO_OURS; break; }
                    if let Some(r) = self.roles.get(k) {
                        if self.ours_pools.get(&r.pool_index).is_some_and(|u| *u > now) && pool_role(r.role) { touch = true; prio = backfill::PRIO_OURS; break; }
                        if touch_role(r.role) { touch = true; if pool_role(r.role) { prio = prio.min(backfill::PRIO_TIER_A); } }
                    }
                }
                if !touch { return; }
                let new = !self.known.contains_key(&sig);
                let stream = self.stream.get(&sig).copied();
                let e = self.know(sig, Sig::new(now, slot, 0, prio), now);
                e.bits |= F_SHRED;
                e.prio = e.prio.min(prio);
                if let (None, Some((_, idx, ts))) = (e.rec, stream) { e.rec = Some(RecSrc::Stream); e.idx = Some(idx); e.rec_idx = true; e.t_exec = Some(ts); e.t_idx = Some(ts); }
                if new { self.si.track(slot, sig, Kind::D2); }
            }
            Note::Ours { attempt, sigs, accounts, target_slot, t: _ } => {
                for k in &accounts {
                    self.ours_accounts.insert(*k, now + OURS_KEEP_NS);
                    if let Some(r) = self.roles.get(k).filter(|r| r.pool_index != crate::rec::accounts::NO_POOL) { self.ours_pools.insert(r.pool_index, now + OURS_KEEP_NS); }
                }
                for s in sigs {
                    if let Some(w) = &mut self.wallet {
                        w.found(s, F_OURS, None, Some(attempt), now);
                        if let Some(ts) = target_slot { w.watch_until(&s, ts + wallet::WATCH_SLOTS_AFTER_TARGET); }
                    }
                    if let Some(e) = self.known.get_mut(&s) { e.bits |= F_OURS; }
                }
            }
            Note::JitoProcessed { sig, slot, t: _ } => {
                if let Some(w) = &mut self.wallet { w.found(sig, F_JITO, slot, None, now); }
                if let Some(e) = self.known.get_mut(&sig) { e.bits |= F_JITO; }
            }
            Note::Landed { sig, slot, attempt, t: _ } => {
                if let Some(w) = &mut self.wallet { w.found(sig, wallet::F_EXEC, slot, attempt, now); }
            }
            Note::EntryHash { slot, hash, feed: _, t } => self.ring_insert(Entry { hash, slot, height: None, src: Src::Entries, commitment: Commitment::Processed, t_ns: t }),
        }
    }

    /// D1 (and our wallet's source (a)): an account update that names its transaction
    fn on_account(&mut self, pubkey: Pk, slot: u64, txn: [u8; 64], now: u64) {
        self.started = true;
        let r = self.roles.get(&pubkey);
        if let Some(w) = &mut self.wallet {
            if w.stream_first_slot.is_none() { w.stream_first_slot = Some(slot); }
            if r.is_some_and(|r| r.role == role::WALLET || r.role == role::WALLET_TOKEN_ACCOUNT) { w.found(txn, F_ACCOUNT, Some(slot), None, now); }
        }
        let prio = match r {
            _ if self.ours_accounts.get(&pubkey).is_some_and(|u| *u > now) => backfill::PRIO_OURS,
            Some(x) if pool_role(x.role) && self.ours_pools.get(&x.pool_index).is_some_and(|u| *u > now) => backfill::PRIO_OURS,
            Some(x) if pool_role(x.role) => backfill::PRIO_TIER_A,
            _ => backfill::PRIO_REST,
        };
        let new = !self.known.contains_key(&txn);
        let stream = self.stream.get(&txn).copied();
        let after = self.bf.after_ns;
        let e = self.know(txn, Sig::new(now, slot, 0, prio), now);
        e.bits |= F_ACCOUNT;
        e.prio = e.prio.min(prio);
        if let (None, Some((_, idx, ts))) = (e.rec, stream) { e.rec = Some(RecSrc::Stream); e.idx = Some(idx); e.rec_idx = true; e.t_exec = Some(ts); e.t_idx = Some(ts); }
        let enter = !e.denom;
        e.denom = true;
        // the same transaction executed again in another slot (on another fork): the slot index looks for it there too
        let moved = !new && e.slot != slot;
        if moved { e.slot = slot; e.forked = false; }
        let first = e.first;
        if new || enter || moved { self.si.track(slot, txn, Kind::D1); }
        if enter {
            self.cov_q.push_back((now, txn));
            self.checks.push(Reverse((first + after, txn)));
        }
    }

    /// a signature `after_ms` old: queued for a getTransaction when nothing has recorded it (and our wallet's fetch
    /// does not cover it). Its first try waits for its slot's confirmation (a getTransaction at `confirmed` finds nothing
    /// before it: review WP-03b #9), at most 20 s after it was seen
    fn on_check(&mut self, sig: [u8; 64], now: u64) {
        if self.wallet.as_ref().is_some_and(|w| w.get(&sig).is_some()) { return; }
        let confirmed = self.si.newest_confirmed;
        let Some(e) = self.known.get_mut(&sig) else { return };
        if e.rec.is_some() || e.queued || !e.denom || e.forked { return; }
        if confirmed > 0 && e.slot > confirmed && now.saturating_sub(e.first) < CONFIRM_WAIT_NS {
            if !e.deferred { e.deferred = true; self.deferred += 1; }
            self.checks.push(Reverse((now + 250_000_000, sig)));
            return;
        }
        e.queued = true;
        let reason = if e.prio == backfill::PRIO_OURS { "attempt_route" } else if e.bits & F_ACCOUNT != 0 { "move_without_tx" } else { "shred_seen_landed" };
        let it = Item { sig, slot: e.slot, prio: e.prio, reason, t_seen: e.first, tries: 0, queued_ns: now_ns() };
        let dropped = self.bf.push(it);
        self.drain_left();
        if dropped > 0 && self.last_backlog_event.is_none_or(|t| now.saturating_sub(t) >= 60 * SEC) {
            self.last_backlog_event = Some(now);
            self.rec.event("chainfetch_backlog", "chainfetch", None, json!({ "backlog": self.bf.backlog(), "max_backlog": self.cfg.max_backlog,
                "dropped_total": self.bf.dropped_total, "need_rps": r2(self.bf.need.get()), "have_rps": r2(self.bf.have.get()), "target_rps": r2(self.bf.target_rps()) }));
        }
    }

    // ---------------------------------------------------------------- timers

    fn timers(&mut self, now: u64, dtx: &tokio::sync::mpsc::UnboundedSender<Done>) {
        let ver = self.cfg.max_tx_version;
        // signatures whose after_ms passed
        while let Some(Reverse((t, sig))) = self.checks.peek().copied() {
            if t > now { break; }
            self.checks.pop();
            self.on_check(sig, now);
        }
        // the backfill, as its rate allows
        for it in self.bf.take(now) {
            let params = json!([b58s(&it.sig), { "encoding": "base64", "maxSupportedTransactionVersion": ver, "commitment": "confirmed" }]);
            self.spawn(Job::Backfill(it), Role::Backfill, "getTransaction", params, Bounds::fetch(Duration::from_secs(2), 1), dtx);
        }
        // our wallet's landed signatures (at most WALLET_MAX_INFLIGHT in flight)
        let room = WALLET_MAX_INFLIGHT.saturating_sub(self.wallet_inflight);
        let due = self.wallet.as_mut().map(|w| w.take_due(now, room)).unwrap_or_default();
        for sig in due {
            self.wallet_inflight += 1;
            let params = json!([b58s(&sig), { "encoding": "base64", "maxSupportedTransactionVersion": ver, "commitment": "confirmed" }]);
            self.spawn(Job::Wallet(sig), Role::Wallet, "getTransaction", params, Bounds::fetch(Duration::from_secs(2), 1), dtx);
        }
        // our attempts' signatures, watched with one batched getSignatureStatuses at most every 2 s
        if !self.status_inflight && now >= self.next_status {
            let batch = self.wallet.as_ref().map(|w| w.watch_batch(wallet::STATUS_BATCH)).unwrap_or_default();
            if !batch.is_empty() {
                self.status_inflight = true;
                self.next_status = now + STATUS_EVERY_NS;
                self.status_calls += 1;
                let params = json!([batch.iter().map(b58s).collect::<Vec<_>>(), { "searchTransactionHistory": false }]);
                self.spawn(Job::Statuses(batch), Role::Wallet, "getSignatureStatuses", params, Bounds::fetch(Duration::from_secs(2), 1), dtx);
            }
        }
        // (d): getSignaturesForAddress over the last hour, once the stream runs (or 30 s in), then every sigs_every_s
        if self.cfg.sigs_every_s > 0 && !self.sigs_inflight && now >= self.next_sigs && (self.started || now >= 30 * SEC) {
            if let Some(w58) = self.wallet58.clone() {
                self.sigs_inflight = true;
                self.next_sigs = now + self.cfg.sigs_every_s * SEC;
                let since_unix = (now_ns() / SEC) as i64 - 3_600 - 60;
                let mut opt = json!({ "limit": 1_000, "commitment": "confirmed" });
                if let Some(u) = self.wallet.as_ref().and_then(|w| w.until.clone()) { opt["until"] = json!(u); }
                self.spawn(Job::Sigs { page: 0, since_unix }, Role::Wallet, "getSignaturesForAddress", json!([w58, opt]), Bounds::fetch(Duration::from_secs(5), 1), dtx);
            }
        }
        // the slot index
        for slot in self.si.due(now) {
            let params = json!([slot, { "encoding": "json", "transactionDetails": "signatures", "rewards": false, "commitment": "confirmed",
                "maxSupportedTransactionVersion": ver }]);
            self.spawn(Job::Block(slot), Role::Slotidx, "getBlock", params, Bounds::fetch(Duration::from_secs(5), 1), dtx);
        }
        // the coverage sampler: a block the slot index indexed at least 20 s ago (every source had its chance)
        if self.cfg.sample_every_s > 0 && !self.sample_inflight && now >= self.next_sample {
            if let Some(slot) = self.si.sample_candidate(now, 20 * SEC) {
                self.sample_inflight = true;
                self.next_sample = now + self.cfg.sample_every_s * SEC;
                let params = json!([slot, { "encoding": "base64", "transactionDetails": "full", "rewards": false, "commitment": "confirmed",
                    "maxSupportedTransactionVersion": ver }]);
                self.spawn(Job::Sample(slot), Role::Sample, "getBlock", params, Bounds::fetch(Duration::from_secs(20), 0), dtx);
            }
        }
        // the blockhash poll: only while no other source gave a fresh confirmed blockhash near the tip
        if self.cfg.blockhash_poll_ms > 0 && !self.poll_inflight && now >= self.next_poll {
            self.next_poll = now + self.cfg.blockhash_poll_ms * 1_000_000;
            if self.ring.fresh_confirmed_elsewhere(now_ns(), POLL_SKIP_AGE_NS, POLL_SKIP_SLOTS) {
                self.bh_poll_skipped += 1;
            } else {
                self.poll_inflight = true;
                self.bh_polls += 1;
                self.spawn(Job::Poll, Role::Blockhash, "getLatestBlockhash", json!([{ "commitment": "confirmed" }]), Bounds::fetch(Duration::from_secs(1), 0), dtx);
            }
        }
        if now >= self.next_tick {
            self.next_tick = now + SEC;
            self.second(now);
        }
    }

    /// once a second: wallet_update_missing, coverage windows, the backfill's cap and give-ups, memory, the published
    /// gauges
    fn second(&mut self, now: u64) {
        let missing = self.wallet.as_mut().map(|w| w.missing_due(now)).unwrap_or_default();
        for (sig, slot, bits) in missing {
            self.rec.event("wallet_update_missing", "chainfetch", None, json!({ "sig": b58s(&sig), "slot": slot, "found_by": wallet::found_by(bits) }));
        }
        let tip = self.ring.tip_slot;
        if let Some(w) = &mut self.wallet { w.evaluate(now, tip); }
        self.si.evaluate(now);
        // the backfill's rate: what its providers have spare after the other roles (never above their configured
        // max_rps); signatures seen 10 minutes ago leave it
        let cap = self.chain.spare_rps(Role::Backfill).map_or(self.cap_cfg, |s| (s * SPARE_SHARE).min(self.cap_cfg));
        self.bf.set_cap(cap);
        self.bf.expire(now);
        self.drain_left();
        while let Some(&(t, sig)) = self.cov_q.front() {
            if now.saturating_sub(t) < 60 * SEC { break; }
            self.cov_q.pop_front();
            let Some(e) = self.known.get(&sig).filter(|e| !e.forked) else { continue };
            self.denom_n += 1;
            let within = |x: Option<u64>| x.is_some_and(|x| x.saturating_sub(e.first) <= 60 * SEC);
            if within(e.t_exec) { self.with_tx += 1; }
            if within(e.t_exec) && within(e.t_idx) { self.with_idx += 1; }
        }
        // signatures past KEEP_NS are forgotten; one still in the backfill is looked at again later (it leaves the backfill
        // within 10 minutes of being seen), and one seen again after it was forgotten keeps its own (newer) record
        while let Some(&(t, sig)) = self.known_order.front() {
            if now.saturating_sub(t) < KEEP_NS { break; }
            self.known_order.pop_front();
            match self.known.get(&sig) {
                Some(e) if e.queued => self.known_order.push_back((now, sig)),
                Some(e) if now.saturating_sub(e.first) >= KEEP_NS => { self.known.remove(&sig); }
                _ => {}
            }
        }
        while let Some(&(t, sig)) = self.stream_order.front() {
            if now.saturating_sub(t) < STREAM_KEEP_NS { break; }
            self.stream_order.pop_front();
            if self.stream.get(&sig).is_some_and(|x| x.2 == t) { self.stream.remove(&sig); }
        }
        self.ours_accounts.retain(|_, u| *u > now);
        self.ours_pools.retain(|_, u| *u > now);
        if now >= self.next_cursor_write { self.next_cursor_write = now + 10 * SEC; self.write_cursor(false); }
        let td = self.shared.tap_dropped.load(Relaxed);
        if td > self.last_tap_event.1 && now.saturating_sub(self.last_tap_event.0) >= 60 * SEC {
            self.last_tap_event = (now, td);
            self.rec.event("chainfetch_tap_drop", "chainfetch", None, json!({ "dropped_total": td, "queue": TAP_CAP }));
        }
        self.publish(now);
    }

    fn publish(&mut self, _now: u64) {
        let bh = self.ring.best(Commitment::Processed, now_ns(), BH_MAX_AGE_NS).map(|e| (e.src.as_str().to_string(), e.slot, self.ring.age_slots(&e),
            now_ns().saturating_sub(e.t_ns) / 1_000_000));
        let w = self.wallet.as_ref();
        let wv = |f: fn(&Wallet) -> u64| w.map_or(0, f);
        let p = Published {
            need_rps: self.bf.need.get(), have_rps: self.bf.have.get(), target_rps: self.bf.target_rps(), cap_rps: self.bf.cap_rps(),
            cap_max_rps: self.cap_cfg.is_finite().then_some(self.cap_cfg), backlog: self.bf.backlog(), inflight: self.bf.inflight,
            queued: self.bf.queued_total, dropped: self.bf.dropped_total, fetched: self.bf.fetched_total, gave_up: self.bf.gave_up_total, expired: self.bf.expired_total,
            refused: self.bf.refused_total, deferred: self.deferred, dup_records: self.dup_records,
            slotidx_lag: self.si.lag_slots(), slotidx_pending: self.si.pending_now(), slot_ok: self.si.ok_total, slot_skipped: self.si.skipped_total,
            slot_error: self.si.error_total, slot_dropped: self.si.dropped_total, slot_refused: self.si.refused_total, idx_n: self.si.idx_n_total,
            idx_mismatch: self.si.idx_mismatch_total, idx_updates: self.idx_updates, missing_sigs: self.missing_sigs, d2_landed: self.d2_landed, d2_absent: self.d2_absent,
            idx_below: self.si.idx_below_total, idx_above: self.si.idx_above_total, kind_block_index: self.si.kind_block_index_total,
            kind_nonvote_rank: self.si.kind_nonvote_rank_total, kind_unverified: self.si.kind_unverified_total, rank_only: self.rank_only,
            votes_omitted_by: { let mut v: Vec<String> = self.si.omits_votes.iter().cloned().collect(); v.sort(); v },
            d2_unknown: self.d2_unknown,
            wallet_pending: w.map_or(0, |w| w.pending_now()), wallet_watch: w.map_or(0, |w| w.watching()), wallet_fetched: wv(|w| w.fetched_total),
            wallet_gave_up: wv(|w| w.gave_up_total), wallet_missing: wv(|w| w.missing_total), wallet_unlanded: wv(|w| w.unlanded_total),
            wallet_unlanded_by_slot: wv(|w| w.unlanded_by_slot_total),
            wallet_landed_by_status: wv(|w| w.landed_by_status_total), wallet_status_calls: self.status_calls,
            bh, bh_disagree: self.ring.disagreements, bh_polls: self.bh_polls, bh_poll_skipped: self.bh_poll_skipped, unseen: self.unseen,
            denom: self.denom_n, with_tx: self.with_tx, with_idx: self.with_idx, wallet_n: wv(|w| w.cov_n_total), wallet_with: wv(|w| w.cov_with_total),
            slots_n: self.si.slots_n_total, slots_with: self.si.slots_with_line_total,
            known: self.known.len(), stream: self.stream.len(), wallet_sigs: w.map_or(0, |w| w.len()), tap_dropped: 0, t_ns: now_ns(),
        };
        *self.shared.published.lock().unwrap() = p;
    }

    // ---------------------------------------------------------------- results

    fn on_done(&mut self, d: Done, now: u64, dtx: &tokio::sync::mpsc::UnboundedSender<Done>) {
        match d.job {
            Job::Backfill(it) => self.on_backfill(it, d.r, d.queued_ns, now),
            Job::Wallet(sig) => self.on_wallet_tx(sig, d.r, d.queued_ns, now),
            Job::Statuses(sigs) => {
                self.status_inflight = false;
                if refused(&d.r) { return; }
                self.txfetch(Role::Wallet, "getSignatureStatuses", sigs.len().to_string(), "ours_status", d.queued_ns, &d.r, None, None);
                if let (Ok(f), Some(w)) = (&d.r, self.wallet.as_mut()) { w.on_statuses(&sigs, &f.value["value"], now); }
            }
            Job::Sigs { page, since_unix } => self.on_sigs(page, since_unix, d.r, d.queued_ns, now, dtx),
            Job::Block(slot) => {
                if !refused(&d.r) { self.txfetch(Role::Slotidx, "getBlock", slot.to_string(), "slot_index", d.queued_ns, &d.r, None, None); }
                match self.si.on_reply(slot, d.r, now, now_ns()) {
                    Reply::Retry => {}
                    Reply::Done(ix) => self.apply_index(*ix, now),
                }
            }
            Job::Sample(slot) => {
                self.sample_inflight = false;
                // refused for want of a token: tried again in 5 s, not a minute later
                if refused(&d.r) { self.next_sample = now + 5 * SEC; return; }
                self.on_sample(slot, d.r, d.queued_ns, now);
            }
            Job::Poll => {
                self.poll_inflight = false;
                if let Ok(f) = &d.r {
                    let v = &f.value;
                    let hash = v["value"]["blockhash"].as_str().and_then(|h| bs58::decode(h).into_vec().ok()).and_then(|h| <[u8; 32]>::try_from(h).ok());
                    if let Some(hash) = hash {
                        let height = v["value"]["lastValidBlockHeight"].as_u64().and_then(|h| h.checked_sub(150));
                        self.ring_insert(Entry { hash, slot: v["context"]["slot"].as_u64().unwrap_or(0), height, src: Src::Poll, commitment: Commitment::Confirmed, t_ns: now_ns() });
                    }
                }
            }
        }
    }

    /// a getTransaction answer: the converted transaction, or why there is none (`not_found` while the node has nothing)
    fn parse_tx(r: &Result<Fetched, RpcFailure>, want: &[u8; 64]) -> Result<RpcTx, &'static str> {
        match r {
            Ok(f) if f.value.is_null() => Err("not_found"),
            Ok(f) => match txjson::from_rpc(&f.value) {
                Ok(x) if x.meta.is_none() => Err("no_meta"),
                Ok(x) if &x.sig != want => Err("signature_mismatch"),
                Ok(x) => Ok(x),
                Err(_) => Err("unparsable"),
            },
            Err(e) if e.code == Some(-32015) => Err("unsupported_version"),
            Err(e) => Err(e.class.as_str()),
        }
    }

    fn on_backfill(&mut self, it: Item, r: Result<Fetched, RpcFailure>, queued_ns: u64, now: u64) {
        let sig = it.sig;
        let (reason, qn) = (it.reason, it.queued_ns.min(queued_ns));
        // refused for want of a token: nothing was sent; back to the queue as it was (no retry step, no txfetch line)
        if refused(&r) {
            let moot = self.known.get(&sig).is_none_or(|e| e.forked || e.rec.is_some());
            let gave_up = self.bf.done(it, if moot { Outcome::Abandoned } else { Outcome::Refused }, now);
            if gave_up || moot { if let Some(e) = self.known.get_mut(&sig) { e.queued = false; } }
            self.drain_left();
            return;
        }
        let parsed = Self::parse_tx(&r, &sig);
        match parsed {
            Ok(x) => {
                self.txfetch(Role::Backfill, "getTransaction", b58s(&sig), reason, qn, &r, None, None);
                self.bf.done(it, Outcome::Fetched, now);
                let bytes = r.as_ref().map_or(0, |f| f.bytes);
                let Some(e) = self.known.get_mut(&sig) else { return };
                e.queued = false;
                if e.rec.is_some() { self.dup_records += 1; return; }
                let idx = x.idx.or(e.idx);
                let slot = x.slot.unwrap_or(e.slot);
                e.rec = Some(RecSrc::Backfill);
                e.idx = idx;
                e.rec_idx = idx.is_some();
                e.t_exec = Some(now);
                if idx.is_some() { e.t_idx = Some(now); }
                let bits = e.bits;
                self.emit_tx(rec::EXEC, Arc::new(x), slot, idx, "rpc-backfill", bits, None, bytes);
            }
            Err(why) => {
                // recorded meanwhile by another source, or shown to be on an abandoned fork: no retry
                let moot = self.known.get(&sig).is_none_or(|e| e.forked || e.rec.is_some());
                let o = if moot { Outcome::Abandoned } else if why == "not_found" { Outcome::NotFound } else { Outcome::Failed };
                let gave_up = self.bf.done(it, o, now);
                if gave_up || moot { if let Some(e) = self.known.get_mut(&sig) { e.queued = false; } }
                self.drain_left();
                self.txfetch(Role::Backfill, "getTransaction", b58s(&sig), reason, qn, &r, Some(why), gave_up.then_some("gave_up"));
            }
        }
    }

    fn on_wallet_tx(&mut self, sig: [u8; 64], r: Result<Fetched, RpcFailure>, queued_ns: u64, now: u64) {
        self.wallet_inflight = self.wallet_inflight.saturating_sub(1);
        if refused(&r) { if let Some(w) = &mut self.wallet { w.refused(&sig, now); } return; }
        let parsed = Self::parse_tx(&r, &sig);
        let bits = self.wallet.as_ref().and_then(|w| w.get(&sig)).map_or(0, |s| s.found_by);
        let reason = if bits & F_ACCOUNT != 0 { "wallet_update" } else if bits & F_OURS != 0 { "ours" } else if bits & F_SIGS != 0 { "sigs_for_address" } else { "jito_processed" };
        let x = match parsed {
            Ok(x) => x,
            Err(why) => {
                // retried after 1 s, 5 s, then every 30 s; given up 10 minutes after it was found (noted on this line)
                let gave_up = self.wallet.as_mut().is_some_and(|w| !w.done(&sig, None, false, now));
                self.txfetch(Role::Wallet, "getTransaction", b58s(&sig), reason, queued_ns, &r, Some(why), gave_up.then_some("gave_up"));
                return;
            }
        };
        self.txfetch(Role::Wallet, "getTransaction", b58s(&sig), reason, queued_ns, &r, None, None);
        let Some(w) = &self.wallet else { return };
        let ws = w.get(&sig).cloned();
        let f = wallet::fields(&x, &w.wallet, &w.wsol, &w.route);
        let known = self.known.get(&sig).cloned();
        let idx = x.idx.or(known.as_ref().and_then(|e| e.idx));
        let slot = x.slot.or(ws.as_ref().and_then(|s| s.slot)).unwrap_or(0);
        // a transaction from before this segment's state stream (source (d) reads the last hour): the previous segment may
        // have recorded it too (review WP-03b #16)
        let pre_run = w.stream_first_slot.is_some_and(|first| slot > 0 && slot < first);
        let bits = bits | known.as_ref().map_or(0, |e| e.bits);
        let attempt = ws.as_ref().and_then(|s| s.attempt);
        let meta = x.meta.as_ref();
        let (ok, fee, err) = (meta.is_some_and(|m| m.err.is_none()), meta.map(|m| m.fee), meta.and_then(|m| m.err.as_ref()).map(|e| rec::tx_error(&e.err)));
        let mut extras = Map::new();
        extras.insert("attempt".into(), json!(attempt));
        extras.insert("ours".into(), attempt.map_or(Value::Null, |a| json!({ "attempt": a })));
        extras.insert("wallet_kind".into(), json!(f.wallet_kind));
        extras.insert("wallet_sol".into(), json!(f.wallet_sol));
        extras.insert("wallet_tok".into(), Value::Object(f.wallet_tok.clone()));
        extras.insert("created".into(), json!(f.created));
        extras.insert("closed".into(), json!(f.closed));
        extras.insert("pre_run".into(), json!(pre_run));
        // exec.jsonl too when it wrote a watched account (it is a D1 signature, or it moved the wallet) and has no record yet
        let wrote_wallet = x.keys.first() == Some(&w.wallet) || f.wallet_sol.is_some_and(|s| s != 0) || !f.wallet_tok.is_empty();
        let in_exec = known.as_ref().map_or(wrote_wallet, |e| e.rec.is_none() && (e.denom || wrote_wallet));
        // WP-05: the route program's events (each leg's delivered amount) and the CU used, for the attempt's outcome line;
        // WP-07: the ledger's raw fields (lamports, token amounts, fee, tip, rent by class), from the full transaction
        let ledger = crate::ledger::raw(&x, &w.wallet, &w.wsol, &w.route).json();
        let input = json!({ "sig": b58s(&sig), "slot": slot, "idx": idx, "ok": ok, "err": err, "fee": fee, "wallet_kind": f.wallet_kind, "wallet_sol": f.wallet_sol,
            "wallet_tok": f.wallet_tok, "attempt": attempt, "found_by": wallet::found_by(bits), "created": f.created.len(), "closed": f.closed.len(), "pre_run": pre_run,
            "prog_events": meta.map(|m| crate::proglog::events(&m.log_messages)), "cu_consumed": meta.and_then(|m| m.compute_units_consumed), "ledger": ledger });
        let bytes = r.as_ref().map_or(0, |f| f.bytes);
        let x = Arc::new(x);
        self.emit_tx(rec::WALLET, x.clone(), slot, idx, "rpc-wallet", bits, Some(extras), bytes);
        if in_exec {
            self.emit_tx(rec::EXEC, x, slot, idx, "rpc-wallet", bits, None, bytes);
            let e = self.know(sig, Sig::new(now, slot, bits, backfill::PRIO_REST), now);
            e.rec = Some(RecSrc::Wallet);
            e.idx = idx;
            e.rec_idx = idx.is_some();
            e.t_exec = Some(now);
            if idx.is_some() { e.t_idx = Some(now); }
            if e.queued { e.queued = false; self.bf.remove(&sig); }
        }
        if let Some(w) = &mut self.wallet { w.done(&sig, Some(idx), in_exec, now); }
        // the slot index gives the block index later, while the slot is not indexed yet
        if idx.is_none() && slot > self.si.newest_done { self.si.track(slot, sig, Kind::Ours); }
        self.input(InputKind::WalletTx, input);
    }

    fn on_sigs(&mut self, page: u32, since_unix: i64, r: Result<Fetched, RpcFailure>, queued_ns: u64, now: u64, dtx: &tokio::sync::mpsc::UnboundedSender<Done>) {
        let key = self.wallet58.clone().unwrap_or_default();
        if !refused(&r) { self.txfetch(Role::Wallet, "getSignaturesForAddress", key.clone(), "sigs_for_address", queued_ns, &r, None, None); }
        // a failed (or refused) page is asked again within a minute (not an hour later)
        let Ok(f) = r else { self.sigs_inflight = false; self.next_sigs = self.next_sigs.min(now + 60 * SEC); return };
        let Some(w) = &mut self.wallet else { self.sigs_inflight = false; return };
        let (_new, before, more) = w.sigs_page(&f.value, since_unix, now);
        let until = w.until.clone();
        match (more && page < 20, before) {
            (true, Some(b)) => {
                let mut opt = json!({ "limit": 1_000, "commitment": "confirmed", "before": b });
                if let Some(u) = until { opt["until"] = json!(u); }
                self.spawn(Job::Sigs { page: page + 1, since_unix }, Role::Wallet, "getSignaturesForAddress", json!([key, opt]), Bounds::fetch(Duration::from_secs(5), 1), dtx)
            }
            _ => self.sigs_inflight = false,
        }
    }

    /// what one slot index line says: positions, D2 landings, fork evidence, the blockhash. FT-000 (S1-2): only a line
    /// whose positions are block indexes (`pos_kind` `block_index`) gives a record its `idx`; a non-vote rank keeps the
    /// order within the slot (slotidx.jsonl `tracked`) but is never written as an index
    fn apply_index(&mut self, ix: Indexed, now: u64) {
        let slot = ix.slot;
        let status = ix.line["status"].clone();
        let exact = ix.pos_kind == "block_index";
        self.rec.json(rec::SLOTIDX, ix.line);
        let after = self.bf.after_ns;
        for (sig, idx, kind) in &ix.found {
            if !exact { self.rank_only += 1; }
            if let Some(e) = self.known.get_mut(sig) {
                if exact { e.idx = Some(*idx); }
                e.forked = false;
                if exact && e.rec.is_some() && e.t_idx.is_none() { e.t_idx = Some(now); }
                if exact && matches!(e.rec, Some(RecSrc::Backfill | RecSrc::Sample)) && !e.rec_idx {
                    e.rec_idx = true;
                    self.idx_updates += 1;
                    self.rec.json(rec::EXEC, json!({ "sig": b58s(sig), "idx_update": idx, "src": "slotidx" }));
                }
                if *kind == Kind::D2 && !e.denom {
                    e.denom = true;
                    self.d2_landed += 1;
                    self.cov_q.push_back((now, *sig));
                    if e.rec.is_none() && !e.queued { self.checks.push(Reverse((e.first + after, *sig))); }
                }
            }
            if let Some(w) = self.wallet.as_mut().filter(|_| exact) {
                if let Some(s) = w.get_mut(sig) {
                    if s.recorded.is_some() && s.idx.is_none() {
                        s.idx = Some(*idx);
                        self.idx_updates += 1;
                        self.rec.json(rec::WALLET, json!({ "sig": b58s(sig), "idx_update": idx, "src": "slotidx" }));
                        if s.in_exec { self.rec.json(rec::EXEC, json!({ "sig": b58s(sig), "idx_update": idx, "src": "slotidx" })); }
                    }
                }
            }
        }
        // D2 candidates: absent from a block that was read (or a skipped slot) are forgotten; those of a block that could
        // not be read are unknown, and forgotten too (nothing will ever say whether they landed)
        for sig in &ix.d2_absent {
            if self.known.get(sig).is_some_and(|e| !e.denom && e.rec.is_none()) { self.known.remove(sig); self.d2_absent += 1; }
        }
        for sig in &ix.d2_unknown {
            if self.known.get(sig).is_some_and(|e| !e.denom && e.rec.is_none()) { self.known.remove(sig); self.d2_unknown += 1; }
        }
        if !ix.missing.is_empty() {
            // written on an abandoned fork: never landed, so nothing to fetch and not in the coverage denominator
            for sig in &ix.missing {
                // (unless it was executed again in a later slot, where the slot index looks for it)
                if let Some(e) = self.known.get_mut(sig).filter(|e| e.slot == slot) {
                    e.forked = true;
                    if e.queued && e.rec.is_none() { e.queued = false; self.bf.remove(sig); }
                }
            }
            self.missing_sigs += ix.missing.len() as u64;
            self.input(InputKind::SlotidxMissing, json!({ "slot": slot, "status": status, "missing": ix.missing.iter().map(b58s).collect::<Vec<_>>() }));
        }
        if let Some((hash, height)) = ix.blockhash { self.ring_insert(Entry { hash, slot, height, src: Src::Slotidx, commitment: Commitment::Confirmed, t_ns: now_ns() }); }
    }

    fn on_sample(&mut self, slot: u64, r: Result<Fetched, RpcFailure>, queued_ns: u64, now: u64) {
        self.txfetch(Role::Sample, "getBlock", slot.to_string(), "coverage_sample", queued_ns, &r, None, None);
        let Ok(f) = r else { return };
        let Some(txs) = f.value["transactions"].as_array() else { return };
        let parsed: Vec<Option<RpcTx>> = txs.iter().map(|t| txjson::from_rpc(t).ok()).collect();
        // FT-000 (S1-2): a list without a single vote transaction left the votes out (every block has them): its positions
        // are non-vote ranks, kept as `block_rank`, never as `idx`
        let with_votes = parsed.iter().flatten().any(|x| x.keys.contains(&crate::feeds::entries::VOTE_PROGRAM));
        let (mut watched, mut unseen) = (0u64, 0u64);
        for (i, x) in parsed.into_iter().enumerate() {
            let Some(x) = x else { continue };
            if !x.keys.iter().any(|k| self.roles.get(k).is_some_and(|r| touch_role(r.role))) { continue; }
            watched += 1;
            let in_wallet = self.wallet.as_ref().is_some_and(|w| w.get(&x.sig).is_some());
            let known = self.known.contains_key(&x.sig) || self.stream.contains_key(&x.sig) || in_wallet;
            if !known { unseen += 1; }
            let has_rec = self.stream.contains_key(&x.sig) || in_wallet || self.known.get(&x.sig).is_some_and(|e| e.rec.is_some());
            if has_rec || x.meta.is_none() { continue; }
            // a watched transaction of the block with no record yet: its record from the block (saves its getTransaction)
            let idx = with_votes.then_some(i as u64);
            let mut fresh = Sig::new(now, slot, 0, backfill::PRIO_REST);
            fresh.rec_idx = with_votes;
            let e = self.know(x.sig, fresh, now);
            e.bits |= F_SAMPLE;
            e.rec = Some(RecSrc::Sample);
            if idx.is_some() { e.idx = idx; }
            e.rec_idx = e.idx.is_some();
            e.t_exec = Some(now);
            if e.idx.is_some() { e.t_idx = Some(now); }
            let (bits, idx) = (e.bits, e.idx);
            if e.queued { e.queued = false; self.bf.remove(&x.sig); }
            let extras = (!with_votes).then(|| Map::from_iter([("block_rank".to_string(), json!(i)), ("pos_kind".to_string(), json!("nonvote_rank"))]));
            self.emit_tx(rec::EXEC, Arc::new(x), slot, idx, "rpc-block-sample", bits, extras, 4_096);
        }
        self.unseen = Some((slot, watched, unseen));
    }

    fn ring_insert(&mut self, e: Entry) {
        if let Some(d) = self.ring.insert(e) {
            self.rec.event("blockhash_source_disagree", "chainfetch", None, json!({ "slot": d.slot, "height": d.height,
                "a": { "src": d.a.0.as_str(), "hash": b58(&d.a.1) }, "b": { "src": d.b.0.as_str(), "hash": b58(&d.b.1) } }));
        }
        let confirmed = self.ring.best(Commitment::Confirmed, now_ns(), BH_MAX_AGE_NS);
        if let Some(b) = &confirmed {
            if self.last_head != Some(b.hash) {
                self.last_head = Some(b.hash);
                self.input(InputKind::BlockhashHead, json!({ "hash": b58(&b.hash), "slot": b.slot, "height": b.height, "src": b.src.as_str(),
                    "commitment": b.commitment.as_str(), "t_ns": b.t_ns }));
            }
        }
        // arbx-fast: the newest processed blockhash too (the DoubleZero shreds' completed slots: `entries`), when it is newer
        // than the confirmed head: a `blockhash_commitment = "processed"` send then uses it (dryE: the confirmed slot index
        // lagged 57 slots and 112 decisions were refused stale while the shreds had every slot's blockhash)
        if let Some(p) = self.ring.best(Commitment::Processed, now_ns(), BH_MAX_AGE_NS) {
            if p.commitment == Commitment::Processed && confirmed.as_ref().map_or(true, |c| p.slot > c.slot) && self.last_processed != Some(p.hash) {
                self.last_processed = Some(p.hash);
                self.input(InputKind::BlockhashHead, json!({ "hash": b58(&p.hash), "slot": p.slot, "height": p.height, "src": p.src.as_str(),
                    "commitment": "processed", "t_ns": p.t_ns }));
            }
        }
    }

    // ---------------------------------------------------------------- records

    /// An exec.jsonl (or wallet.jsonl) record of an RPC transaction, built on the chain (core) writer with the stream's
    /// builder and WP-08's derived-field hook; `extras`: wallet.jsonl's own fields
    #[allow(clippy::too_many_arguments)]
    fn emit_tx(&self, stream: rec::S, x: Arc<RpcTx>, slot: u64, idx: Option<u64>, src: &'static str, bits: u8, extras: Option<Map<String, Value>>, bytes: usize) {
        if !self.rec.is_on() { return; }
        let roles = self.roles.clone();
        let t = now_ns();
        self.rec.emit_sized(stream, bytes as u64 + 1_024, Record::enc(move |o| {
            let Some(meta) = x.meta.as_ref() else { return };
            let fb = wallet::found_by(bits);
            let mut v = rec::exec::exec_json(&x.sig, slot, idx, t, src, &fb, &x.tx, meta, Some(roles.as_ref()));
            v["bank_id"] = Value::Null;
            v["block_time"] = json!(x.block_time);
            // WP-08's derived fields (transfers, tips, bundle, arb_like) by the hook the transaction stream's records use
            // (`rec::exec::emit_grpc`), so wallet.jsonl and every exec.jsonl record classify alike whoever produced them
            rec::exec::derive(&mut v);
            if let Some(m) = extras { for (k, val) in m { v[k] = val; } }
            let _ = serde_json::to_writer(o, &v);
        }));
    }

    /// txfetch.jsonl (MEASUREMENT §4.18): one line per fetch (the blockhash poll only in the per-role stats; a call
    /// refused for want of a token sent nothing and has no line)
    #[allow(clippy::too_many_arguments)]
    fn txfetch(&self, role: Role, method: &str, key: String, reason: &str, queued_ns: u64, r: &Result<Fetched, RpcFailure>, err: Option<&str>, note: Option<&str>) {
        let (ok, provider, latency, bytes, attempts, detail, code) = match r {
            Ok(f) => (err.is_none(), Some(f.provider.clone()), Some((f.latency_ms * 1000.0).round() / 1000.0), Some(f.bytes), f.attempts, None, None),
            Err(e) => (false, e.provider.clone(), None, None, e.attempts, Some(e.msg.chars().take(200).collect::<String>()), e.code),
        };
        let err = err.map(String::from).or_else(|| match r {
            Err(e) if matches!(e.code, Some(-32007 | -32009)) => None,
            Err(e) if e.code == Some(-32015) => Some("unsupported_version".to_string()),
            Err(e) => Some(e.class.as_str().to_string()),
            Ok(_) => None,
        });
        // a skipped slot is an answer, not a failure
        let skipped = matches!(r, Err(e) if matches!(e.code, Some(-32007 | -32009)));
        self.rec.json(rec::TXFETCH, json!({ "t_ns": now_ns(), "role": role.as_str(), "method": method, "key": key, "reason": reason, "queued_ns": queued_ns,
            "provider": provider, "ok": ok || skipped, "err": err, "note": note.or(skipped.then_some("skipped")), "rpc_code": code, "detail": detail,
            "latency_ms": latency, "bytes": bytes, "attempts": attempts }));
    }
}

fn b58s(s: &[u8; 64]) -> String { bs58::encode(s).into_string() }

/// What the run does when the service dies (`arbx run`: the SendGate closes for the rest of the segment)
pub type OnDead = Arc<dyn Fn(&str) + Send + Sync>;

/// Start the service on `rt` (the background runtime) until `stop`, make it the process's (its taps), and watch it
pub fn start(o: Opts, reg: Arc<Registry>, rt: &tokio::runtime::Handle, stop: Arc<AtomicBool>, on_dead: Option<OnDead>) -> Arc<Shared> {
    let (shared, rx) = Shared::new(reg);
    install(shared.clone());
    spawn_watched(o, shared.clone(), rx, rt, stop, on_dead);
    shared
}

/// The service on `rt`, and its watchdog: a task that ends while the run goes on (a panic) is reported (events.jsonl
/// `chainfetch_dead`, a run.log WARNING, `on_dead`) and marked dead in the status; one that stops publishing for
/// `STALL_MS` is `chainfetch_stalled` (then `chainfetch_recovered`)
pub fn spawn_watched(o: Opts, shared: Arc<Shared>, rx: crossbeam_channel::Receiver<Note>, rt: &tokio::runtime::Handle, stop: Arc<AtomicBool>,
    on_dead: Option<OnDead>) -> tokio::task::JoinHandle<()> {
    let rec = o.rec.clone();
    let svc = Service::new(o, shared.clone());
    let mut h = rt.spawn(svc.run(rx, stop.clone()));
    rt.spawn(async move {
        let mut tick = tokio::time::interval(Duration::from_secs(1));
        tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        let mut stalled = false;
        loop {
            tokio::select! {
                r = &mut h => {
                    if stop.load(Relaxed) { return; }
                    let why = match r {
                        Ok(()) => "its task ended".to_string(),
                        Err(e) if e.is_panic() => {
                            let p = e.into_panic();
                            let m = p.downcast_ref::<&str>().map(|s| s.to_string()).or_else(|| p.downcast_ref::<String>().cloned()).unwrap_or_else(|| "?".into());
                            format!("panic: {}", crate::rpc::scrub(&m))
                        }
                        Err(e) => e.to_string(),
                    };
                    shared.dead.store(true, Relaxed);
                    rec.event("chainfetch_dead", "chainfetch", None, json!({ "why": why }));
                    rec.say(format!("WARNING: the chain-fetch service stopped ({why}): wallet.jsonl, the backfill, the slot index and the blockhash ring stop with it"));
                    if let Some(f) = &on_dead { f(&why); }
                    return;
                }
                _ = tick.tick() => {
                    if stop.load(Relaxed) { continue; }
                    let Some(age) = shared.published_age_ms() else { continue };
                    if age > STALL_MS && !stalled {
                        stalled = true;
                        rec.event("chainfetch_stalled", "chainfetch", None, json!({ "published_age_ms": age }));
                        rec.say(format!("WARNING: the chain-fetch service has not published for {age} ms"));
                    } else if age <= STALL_MS && stalled {
                        stalled = false;
                        rec.event("chainfetch_recovered", "chainfetch", None, json!({}));
                    }
                }
            }
        }
    })
}

/// meta.json `chainfetch`: the effective settings, each role's providers, each provider's budget and each role's bucket
/// priority
pub fn meta_json(cfg: &ChainfetchCfg, clients: &RoleClients, reg: &Registry) -> Value {
    let roles: Map<String, Value> = Role::FETCH.iter().map(|r| (r.as_str().to_string(), json!(clients.names(*r)))).collect();
    let prio: Map<String, Value> = Role::ALL.iter().map(|r| (r.as_str().to_string(), json!(r.priority()))).collect();
    let cap = clients.cap(Role::Backfill);
    json!({ "enabled": cfg.enabled, "after_ms": cfg.after_ms, "rps": cfg.rps, "backfill_cap_rps": cap.is_finite().then_some(cap),
        "max_backlog": cfg.max_backlog, "sample_every_s": cfg.sample_every_s, "blockhash_poll_ms": cfg.blockhash_poll_ms, "sigs_every_s": cfg.sigs_every_s,
        "default_max_rps": cfg.default_max_rps, "boot_retry_s": cfg.boot_retry_s, "max_tx_version": cfg.max_tx_version, "roles": roles, "limits": reg.limits_json(),
        "priorities": prio })
}

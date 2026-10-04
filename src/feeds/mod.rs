//! Feed layer: every configured feed runs on its own (raw UDP: a thread; gRPC: a task) and pushes `Event`s into one
//! engine channel. Raw shreds are decoded by a streaming assembler, so a transaction leaves the feed the moment its
//! last shred arrived. Only transactions that can matter are forwarded (`Interest`): a static key is a watched program,
//! pool or vault, or one of its lookup tables is known to hold one. Everything else is dropped inside the feed.
pub mod clock;
pub mod entries;
#[cfg(test)]
pub(crate) mod fixture;
pub mod grpc;
pub mod shred;
pub mod udp;

use crate::config::{Feed, FeedKind};
use crate::rec::{self, Rec, Record};
use crate::tx::{self, Pk, Tx};
use clock::now_ns;
use rustc_hash::FxHashSet as HashSet;
use std::net::Ipv4Addr;
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
use std::sync::{Arc, RwLock};
use crossbeam_channel::Sender as UnboundedSender;

/// A transaction's bytes as its feed delivered them: what the input journal's TX_FIRST record holds (MEASUREMENT
/// §4.13, `enc`), so a replay decodes exactly the transaction the engine saw. Shared, never copied on the engine thread
#[derive(Clone, Default)]
pub enum RawTx {
    /// not kept (synthetic arrivals: the journal re-encodes the parsed transaction, `tx::to_wire`)
    #[default]
    None,
    /// wire bytes (raw shreds, ShredStream entries)
    Wire(Arc<[u8]>),
    /// Yellowstone's protobuf transaction (deshred, transaction streams)
    Pb(Arc<grpc::PbTransaction>),
}

/// A transaction as delivered by one feed.
pub struct Arrival {
    pub feed: u16,
    pub slot: u64,
    /// receive time of the bytes that completed the transaction (kernel timestamp for raw UDP, message time for gRPC)
    pub t_rx: u64,
    /// when our decoder handed it over (equal to t_rx for gRPC)
    pub t_decoded: u64,
    /// Some(succeeded) for executed feeds (processed commitment), None for unexecuted (shreds, deshred)
    pub executed: Option<bool>,
    pub tx: Tx,
    /// its place on the leader's PoH clock (entries feeds, slots seen from their start)
    pub poh: Option<entries::Poh>,
    /// its bytes as delivered (the input journal, WP-03)
    pub raw: RawTx,
}

/// Where an account update came from (accounts.bin `src`, MEASUREMENT §4.12)
pub mod src {
    pub const GRPC: u8 = 0;
    pub const RPC_BOOT: u8 = 1;
    pub const RPC_REFETCH: u8 = 2;
    pub const RPC_SNAPSHOT: u8 = 3;
}

/// What an `Event::Input` carries (the journal's INPUT kinds, MEASUREMENT §4.13): inputs from other subsystems that
/// change engine or send-check decisions
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum InputKind { BlockhashHead = 1, LeaderWindow = 2, Gate = 3, Quarantine = 4, InflightRelease = 5, Health = 6, WalletTx = 7, SlotidxMissing = 8,
    /// an executor settlement (exec.rs `Settled`) in full: its replay is WP-05 / WP-09's
    Settled = 9,
    /// what the engine starts with that no input carries (`engine::EngineInit`): journaled once by `Engine::run` with
    /// `t_engine_ns` 0, never an `Event`
    EngineInit = 10,
    /// how one chunk of an engine RPC read ended (`reads.rs`; review WP-04 #1, #7): `{job, chunk, what, attempt, ok,
    /// slot, n, missing: [pk]}` or `{..., ok: false, err}`, after the chunk's account events
    Fetch = 11 }

impl InputKind {
    pub fn from_u8(k: u8) -> Option<InputKind> {
        use InputKind::*;
        Some(match k { 1 => BlockhashHead, 2 => LeaderWindow, 3 => Gate, 4 => Quarantine, 5 => InflightRelease, 6 => Health, 7 => WalletTx, 8 => SlotidxMissing, 9 => Settled,
            10 => EngineInit, 11 => Fetch, _ => return None })
    }
}

pub enum Event {
    Tx(Arrival),
    /// one watched-account update. `aseq`: its record in accounts.bin (assigned when the record was emitted, WP-03;
    /// 0 without a recorder); `src`: [`src`]; `write_version` 0 for RPC reads; `bank_id`: the bank it was written in, when
    /// the provider says (WP-04 forks)
    Account { slot: u64, pubkey: Pk, owner: Pk, lamports: u64, data: Arc<[u8]>, t: u64, txn: Option<[u8; 64]>, write_version: u64, is_startup: bool, src: u8, aseq: u64,
        bank_id: Option<u64> },
    /// a slot status (Yellowstone SlotStatus 0-6), with its parent and bank when the provider sends them
    Slot { slot: u64, status: i32, t: u64, parent: Option<u64>, dead_error: Option<String>, bank_id: Option<u64> },
    /// a block's metadata (`blocks_meta`, when subscribed)
    BlockMeta(grpc::BlockMeta),
    /// an input from another subsystem (leader-schedule windows, SendGate changes, ...): journaled as INPUT (the
    /// journal shares `data`, serialized on the recorder's writer: review WP-03 N3)
    Input { kind: InputKind, data: Arc<serde_json::Value> },
    /// a feed connected, reconnected or failed (for the run log)
    Status { feed: u16, msg: String },
    /// a lookup table fetched off the hot path: `addrs` its entries; None with `err` None: no such table (yet); `err`:
    /// the fetch failed (WP-04: both are retried)
    Alt { table: Pk, addrs: Option<Arc<Vec<Pk>>>, err: Option<String> },
    /// a canary, settled from chain (exec.rs); the engine adds what its feeds saw and writes the outcome
    Settled(Box<crate::exec::Settled>),
}

/// What a transaction must touch to be forwarded. Shared and grown by the engine (new lookup tables).
#[derive(Default)]
pub struct Interest {
    /// watched venue programs, our program, pools and vaults
    pub keys: HashSet<Pk>,
    /// lookup tables known to contain a watched key
    pub tables: RwLock<HashSet<Pk>>,
}

impl Interest {
    pub fn wants(&self, t: &Tx) -> bool {
        if t.is_vote { return false; }
        if t.keys.iter().any(|k| self.keys.contains(k)) { return true; }
        if t.lookups.is_empty() { return false; }
        if let Some((w, r)) = &t.loaded { if w.iter().chain(r).any(|k| self.keys.contains(k)) { return true; } }
        let tables = self.tables.read().unwrap();
        t.lookups.iter().any(|l| tables.contains(&l.table))
    }
}

/// Per-feed counters, read by the engine's periodic status line and feedhealth.jsonl (MEASUREMENT §4.9; WP-02 adds
/// the connection state, the last message, the newest slot, the channel drops, first arrivals, UDP drops and the
/// shred assembler's numbers)
#[derive(Default)]
pub struct FeedCounters {
    pub name: String,
    pub kind: String,
    pub packets: AtomicU64,
    pub txs: AtomicU64,
    pub forwarded: AtomicU64,
    pub reconnects: AtomicU64,
    pub errors: AtomicU64,
    pub connected: AtomicBool,
    /// when the feed's last message arrived (ns)
    pub last_msg_ns: AtomicU64,
    /// the newest slot the feed delivered
    pub slot_max: AtomicU64,
    /// events the feed could not hand to the engine
    pub channel_drops: AtomicU64,
    /// signatures this feed delivered first (the engine counts them when a signature leaves its 10 s window)
    pub first_arrivals: AtomicU64,
    /// raw feeds: the kernel's receive drops of the feed's socket (the recorder's monitor stores what `/proc/net/udp`
    /// says every 10 s)
    pub udp_drops: Arc<AtomicU64>,
    pub udp_watched: AtomicBool,
    /// raw shred feeds: the assembler's totals
    pub shreds: ShredCounters,
    /// gRPC feeds whose provider stamps its messages (`created_at`): receive time minus that, ns (feedhealth.jsonl
    /// `provider_lag_ms`; a provider clock ahead of ours counts as 0)
    pub provider_lag: std::sync::Mutex<Option<crate::lat::Series>>,
}

/// A raw shred feed's assembler totals (feedhealth.jsonl `shreds`), copied from `AsmStats` every 2 s by the feed thread
#[derive(Default)]
pub struct ShredCounters {
    pub on: AtomicBool,
    pub data: AtomicU64,
    pub code: AtomicU64,
    pub dup: AtomicU64,
    pub bad: AtomicU64,
    pub sets_ok: AtomicU64,
    pub sets_failed: AtomicU64,
    pub version: AtomicU32,
}

impl FeedCounters {
    pub fn named(name: &str, kind: &str) -> FeedCounters { FeedCounters { name: name.into(), kind: kind.into(), ..Default::default() } }

    /// a message arrived at `t` for `slot` (one feed thread or task writes these: plain stores)
    #[inline]
    pub fn seen(&self, slot: u64, t: u64) {
        self.last_msg_ns.store(t, Ordering::Relaxed);
        if !self.connected.load(Ordering::Relaxed) { self.connected.store(true, Ordering::Relaxed); }
        if slot > self.slot_max.load(Ordering::Relaxed) { self.slot_max.store(slot, Ordering::Relaxed); }
    }

    /// a message stamped `created` (ns) by the provider arrived at `t`
    pub fn provider_lag(&self, t: u64, created: u64) {
        let mut g = self.provider_lag.lock().unwrap_or_else(|e| e.into_inner());
        g.get_or_insert_with(|| crate::lat::Series::new("provider_lag")).push(t.saturating_sub(created));
    }

    fn copy_asm(&self, a: &shred::AsmStats, version: Option<u16>) {
        let s = &self.shreds;
        s.on.store(true, Ordering::Relaxed);
        s.data.store(a.data_shreds, Ordering::Relaxed);
        s.code.store(a.code_shreds, Ordering::Relaxed);
        s.dup.store(a.dup_shreds, Ordering::Relaxed);
        s.bad.store(a.bad_packets + a.implausible + a.wrong_version, Ordering::Relaxed);
        s.sets_ok.store(a.sets_decoded, Ordering::Relaxed);
        s.sets_failed.store(a.sets_failed, Ordering::Relaxed);
        s.version.store(version.unwrap_or(0) as u32, Ordering::Relaxed);
    }
}

/// PoH positions of forwarded transactions, by any feed (PLAN WP-08 item 2): an entries feed's when its message is
/// walked (they also ride on the arrival), a shred feed's when its PoH walk reaches them, which can be after the
/// transaction was handed over (so they never ride on the arrival and the engine's own map lacks them). Keyed by the
/// signature's first 8 bytes (big-endian, as poh.log's `sig8`), the earliest position kept, for `POH_KEEP_NS`.
/// Settlement (outcomes `poh`) and the `poh_trigger_pct` gauge read it ([`poh_index`]; WP-05 / WP-07 call sites)
pub struct PohIndex { m: std::sync::Mutex<(rustc_hash::FxHashMap<u64, (entries::Poh, u16)>, std::collections::VecDeque<(u64, u64)>)> }

/// how long a position is kept, and at most how many (a hard cap on memory)
pub const POH_KEEP_NS: u64 = 180_000_000_000;
pub const POH_KEEP_MAX: usize = 1_000_000;

impl PohIndex {
    fn new() -> PohIndex { PohIndex { m: std::sync::Mutex::new(Default::default()) } }
    /// positions `(sig8, poh)` from feed `feed`, received at `t` (the first one of a signature wins)
    pub fn insert_many(&self, items: &[(u64, entries::Poh)], feed: u16, t: u64) {
        if items.is_empty() { return; }
        let mut g = self.m.lock().unwrap_or_else(|e| e.into_inner());
        let (map, order) = &mut *g;
        for (k, p) in items { if !map.contains_key(k) { map.insert(*k, (*p, feed)); order.push_back((t, *k)); } }
        while let Some(&(t0, k)) = order.front() {
            if t.saturating_sub(t0) < POH_KEEP_NS && order.len() <= POH_KEEP_MAX { break; }
            order.pop_front();
            map.remove(&k);
        }
    }
    /// the position of the transaction whose signature starts with `sig8`, and the feed that saw it
    pub fn get(&self, sig8: u64) -> Option<(entries::Poh, u16)> { self.m.lock().unwrap_or_else(|e| e.into_inner()).0.get(&sig8).copied() }
    /// the same by full signature
    pub fn get_sig(&self, sig: &[u8; 64]) -> Option<(entries::Poh, u16)> { self.get(u64::from_be_bytes(sig[..8].try_into().unwrap())) }
    pub fn len(&self) -> usize { self.m.lock().unwrap_or_else(|e| e.into_inner()).0.len() }
    pub fn is_empty(&self) -> bool { self.len() == 0 }
}

/// The process's PoH index
pub fn poh_index() -> &'static PohIndex {
    static I: std::sync::LazyLock<PohIndex> = std::sync::LazyLock::new(PohIndex::new);
    &I
}

/// The `poh_trigger_pct` gauge (PLAN WP-08 item 2, F38): the share of attempts whose trigger has a PoH position; the
/// target is >= 90% while at least one entries or shred feed is alive. The attempt writer (WP-05, exec.rs) notes every
/// attempt ([`PohGauge::note_attempt`]); the status line's `coverage` section (engine.rs) takes [`PohGauge::status`]
pub struct PohGauge { attempts: AtomicU64, with_poh: AtomicU64, prev: std::sync::Mutex<(u64, u64)> }

/// the process's gauge
pub static POH_GAUGE: PohGauge = PohGauge::new();

/// the gauge's target, percent
pub const POH_TRIGGER_TARGET_PCT: f64 = 90.0;

/// a feed that rebuilds a PoH clock (entries and raw shred feeds), by feedhealth `kind`
pub fn poh_capable(kind: &str) -> bool { matches!(kind, "jito-entries" | "udp" | "multicast") }

impl PohGauge {
    pub const fn new() -> PohGauge { PohGauge { attempts: AtomicU64::new(0), with_poh: AtomicU64::new(0), prev: std::sync::Mutex::new((0, 0)) } }
    /// one attempt; `has_poh`: its trigger has a PoH position (the engine's map or [`poh_index`])
    pub fn note_attempt(&self, has_poh: bool) {
        self.attempts.fetch_add(1, Ordering::Relaxed);
        if has_poh { self.with_poh.fetch_add(1, Ordering::Relaxed); }
    }
    /// `{poh_trigger_pct, attempts_delta, with_poh_delta, attempts_total, with_poh_total, poh_feeds_alive_now, target_pct,
    /// target_met}` since the previous call (`poh_trigger_pct` null without attempts; `target_met` null while no
    /// PoH-capable feed is alive, i.e. connected with a message in the last 10 s)
    pub fn status(&self, feeds: &[Arc<FeedCounters>], now: u64) -> serde_json::Value {
        let (a, w) = (self.attempts.load(Ordering::Relaxed), self.with_poh.load(Ordering::Relaxed));
        let (da, dw) = { let mut p = self.prev.lock().unwrap_or_else(|e| e.into_inner()); let d = (a - p.0, w - p.1); *p = (a, w); d };
        let alive = feeds.iter().filter(|c| poh_capable(&c.kind) && c.connected.load(Ordering::Relaxed)
            && now.saturating_sub(c.last_msg_ns.load(Ordering::Relaxed)) < 10_000_000_000).count();
        let pct = (da > 0).then(|| dw as f64 * 100.0 / da as f64);
        serde_json::json!({ "poh_trigger_pct": pct, "attempts_delta": da, "with_poh_delta": dw, "attempts_total": a, "with_poh_total": w,
            "poh_feeds_alive_now": alive, "target_pct": POH_TRIGGER_TARGET_PCT, "target_met": (alive > 0).then_some(pct.map(|p| p >= POH_TRIGGER_TARGET_PCT)).flatten() })
    }
}

/// feedhealth.jsonl `kind`
fn kind_name(k: &FeedKind) -> String { serde_json::to_value(k).ok().and_then(|v| v.as_str().map(String::from)).unwrap_or_else(|| format!("{k:?}")) }

pub struct Feeds {
    pub names: Vec<String>,
    pub counters: Vec<Arc<FeedCounters>>,
}

/// What `forward` records besides the events, for the state stream (WP-03): every account update to accounts.bin
/// (its `aseq` goes into the event), and the block metas' leaders (blocks.jsonl). The transaction feeds have none
#[derive(Clone, Default)]
pub struct Fwd {
    /// this is the state stream (slots.jsonl is its slots')
    pub state: bool,
    pub acct: Option<Arc<crate::rec::accounts::AcctRec>>,
    pub leaders: Option<Arc<crate::leaders::LeaderBook>>,
}

/// Start every enabled feed. Returns the feed names (index = `Arrival::feed`) and their counters. `rt` is the hot
/// runtime (gRPC feeds); raw feeds run on their own threads. `rec`: the recorder (poh, slots-feed, exec, entries
/// archives; raw feeds' sockets are followed for kernel drops). `roles`: the watched accounts (exec.jsonl v2 `watched`)
pub fn start(feeds: &[Feed], interest: Arc<Interest>, out: UnboundedSender<Event>, stop: Arc<AtomicBool>, rt: &tokio::runtime::Handle, rec: &Rec,
    roles: Option<Arc<crate::rec::accounts::Roles>>) -> anyhow::Result<Feeds> {
    let mut names = Vec::new();
    let mut counters = Vec::new();
    for f in feeds.iter().filter(|f| f.enabled) {
        let id = names.len() as u16;
        names.push(f.name.clone());
        let c = Arc::new(FeedCounters::named(&f.name, &kind_name(&f.kind)));
        counters.push(c.clone());
        if f.is_raw() {
            let sock = match f.kind {
                FeedKind::Udp => udp::open_unicast(f.bind.as_deref().unwrap())?,
                _ => udp::open_multicast(f.group.as_deref().unwrap(), f.port.unwrap(), f.interface.as_deref().unwrap())?,
            };
            if let Some(port) = sock.local_addr().ok().and_then(|a| a.as_socket()).map(|a| a.port()) {
                c.udp_watched.store(true, Ordering::Relaxed);
                rec.watch_udp(port, c.udp_drops.clone());
            }
            let allowed: Vec<Ipv4Addr> = f.allowed_src.iter().filter_map(|s| s.parse().ok()).collect();
            let (interest, out, stop, c, rec) = (interest.clone(), out.clone(), stop.clone(), c.clone(), rec.clone());
            let name = f.name.clone();
            std::thread::Builder::new().name(format!("feed-{name}")).spawn(move || {
                let mut asm = shred::Assembler::new();
                asm.rec = rec;
                asm.feed = id;
                let mut done = Vec::new();
                let mut last_gc = now_ns();
                let key = |k: &Pk| interest.keys.contains(k);
                let res = udp::run(&sock, 2048, || stop.load(Ordering::Relaxed), |p| {
                    c.packets.fetch_add(1, Ordering::Relaxed);
                    if !allowed.is_empty() && !allowed.contains(&p.src) { return; }
                    let h = {
                        let tables = interest.tables.read().unwrap();
                        let table = |k: &Pk| tables.contains(k);
                        let before = asm.stats.txs;
                        let h = asm.push(p.data, p.t_ns, &mut done, &shred::Want { key: &key, table: &table });
                        c.txs.fetch_add(asm.stats.txs - before, Ordering::Relaxed);
                        h
                    };
                    if let Some(h) = h { c.seen(h.slot, p.t_ns); }
                    let t_now = if done.is_empty() { p.t_ns } else { now_ns() };
                    if t_now.saturating_sub(last_gc) > 2_000_000_000 { asm.gc(t_now); last_gc = t_now; c.copy_asm(&asm.stats, asm.version()); }
                    if done.is_empty() { return; }
                    let t_decoded = t_now;
                    for d in done.drain(..) {
                        c.forwarded.fetch_add(1, Ordering::Relaxed);
                        if out.send(Event::Tx(Arrival { feed: id, slot: d.slot, t_rx: d.t, t_decoded, executed: None, tx: d.tx, poh: None, raw: RawTx::Wire(d.raw) })).is_err() {
                            c.channel_drops.fetch_add(1, Ordering::Relaxed);
                        }
                    }
                });
                c.connected.store(false, Ordering::Relaxed);
                if let Err(e) = res { c.errors.fetch_add(1, Ordering::Relaxed); let _ = out.send(Event::Status { feed: id, msg: format!("{name}: receive failed: {e}") }); }
            })?;
        } else {
            let (f, interest, out, stop, c, rec, roles) = (f.clone(), interest.clone(), out.clone(), stop.clone(), c.clone(), rec.clone(), roles.clone());
            rt.spawn(async move {
                let mut backoff = 500u64;
                let fwd = Fwd::default();
                let mut recent = crate::rec::exec::Recent::default();
                while !stop.load(Ordering::Relaxed) {
                    let clock = std::sync::Mutex::new(entries::PohClock::default());
                    let sink = |it: grpc::Item| -> bool { forward(id, &interest, &out, &c, Some(&clock), &rec, &fwd, it) };
                    let started = now_ns();
                    let res = grpc::feed_once(&f, &sink, &rec, &c, roles.as_ref(), &mut recent).await;
                    c.connected.store(false, Ordering::Relaxed);
                    if stop.load(Ordering::Relaxed) { break; }
                    c.reconnects.fetch_add(1, Ordering::Relaxed);
                    let msg = match res { Ok(()) => "stream closed".to_string(), Err(e) => { c.errors.fetch_add(1, Ordering::Relaxed); format!("{e:#}") } };
                    let _ = out.send(Event::Status { feed: id, msg: format!("{}: {msg}; reconnecting in {backoff} ms", f.name) });
                    if now_ns() - started > 30_000_000_000 { backoff = 500; }
                    tokio::time::sleep(std::time::Duration::from_millis(backoff)).await;
                    backoff = (backoff * 2).min(10_000);
                }
            });
        }
    }
    Ok(Feeds { names, counters })
}

/// gRPC item -> engine events (entries are walked here, in the feed task, not in the engine). The entries feeds' PoH
/// positions (poh.log), finished slots (slots-feed.log) and raw messages (entries-<feed>, when archived) are recorded
/// here too; for the state stream (`fwd`), every account update (accounts.bin: its `aseq` goes into the event), every
/// slot status (slots.jsonl) and block meta (blocks.jsonl)
#[allow(clippy::too_many_arguments)]
pub fn forward(id: u16, interest: &Interest, out: &UnboundedSender<Event>, c: &FeedCounters, poh: Option<&std::sync::Mutex<entries::PohClock>>, rec: &Rec, fwd: &Fwd,
    it: grpc::Item) -> bool {
    // WP-03b tap: the chain-fetch service learns the state stream's transactions (watched writes, our wallet's), confirmed
    // slots and block metas (a non-blocking try_send; a no-op without the service)
    if fwd.state { crate::chainfetch::note_state(&it); }
    let sent = |c: &FeedCounters, ok: bool| { if !ok { c.channel_drops.fetch_add(1, Ordering::Relaxed); } ok };
    match it {
        grpc::Item::Entries { slot, bytes, t } => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            c.seen(slot, t);
            // the raw message (bulk class): moved into the record once it has been walked, never copied
            let archive = |bytes: Vec<u8>| if let Some(s) = rec.entries(id) {
                rec.emit_sized(s, bytes.len() as u64 + 20, Record::enc(move |o| { o.extend(slot.to_le_bytes()); o.extend(t.to_le_bytes()); o.extend((bytes.len() as u32).to_le_bytes()); o.extend_from_slice(&bytes); }));
            };
            let Some((refs, ents)) = entries::parse_entries_poh(&bytes) else { archive(bytes); return true };
            let (pohs, first_entry) = match poh {
                Some(p) => {
                    let (pohs, done, first) = p.lock().unwrap().entries_at(slot, &ents, t);
                    if let Some(d) = done {
                        // slots-feed.log v2: the eight v1 columns; the shred columns are `-` for an entries feed, and
                        // poh_complete is whether the slot was followed from its start with all 64 ticks
                        rec.emit(rec::SLOTS_FEED, Record::enc(move |o| { let _ = std::io::Write::write_fmt(o, format_args!("{id} {} {} {} {} {} {} {} - - - - {}",
                            d.slot, d.ticks, d.entries, d.txs, d.t_first, d.t_last, d.valid as u8, (d.valid && d.ticks == 64) as u8)); }));
                    }
                    (pohs, first)
                }
                None => (vec![None; ents.len()], None),
            };
            // poh.log v2: `sig8 slot ms feed entry_idx` (WP-08: the entry's index in its slot when the slot is followed
            // from its start, as the PoH position itself; `-` otherwise). One record for the message's lines (review F11:
            // one queue slot, formatted on the writer)
            if rec.is_on() {
                let lines: Vec<(u64, f64, Option<u32>)> = refs.iter().filter(|r| !r.is_vote).filter_map(|r| {
                    let ms = pohs.get(r.entry as usize).copied().flatten().and_then(|p| p.ms())?;
                    Some((u64::from_be_bytes(r.sig[..8].try_into().unwrap()), ms, first_entry.map(|f| f + r.entry)))
                }).collect();
                if !lines.is_empty() {
                    rec.emit(rec::POH, Record::enc_lines(lines.len() as u32, move |o| {
                        for (k, (sig8, ms, e)) in lines.iter().enumerate() {
                            if k > 0 { o.push(b'\n'); }
                            let _ = match e {
                                Some(e) => std::io::Write::write_fmt(o, format_args!("{sig8:016x} {slot} {ms:.3} {id} {e}")),
                                None => std::io::Write::write_fmt(o, format_args!("{sig8:016x} {slot} {ms:.3} {id} -")),
                            };
                        }
                    }));
                }
            }
            let t_decoded = now_ns();
            let tables = interest.tables.read().unwrap();
            let (key, table) = (|k: &Pk| interest.keys.contains(k), |k: &Pk| tables.contains(k));
            let mut ok = true;
            let mut positions: Vec<(u64, entries::Poh)> = Vec::new();
            for r in refs {
                if r.is_vote { continue; }
                c.txs.fetch_add(1, Ordering::Relaxed);
                let raw = &bytes[r.start..r.end];
                if !tx::scan(raw, &key, &table).map_or(false, |s| s.hit) { continue; }
                let Some((tx, n)) = tx::parse_wire(raw) else { continue };
                c.forwarded.fetch_add(1, Ordering::Relaxed);
                let poh = pohs.get(r.entry as usize).copied().flatten();
                if let Some(p) = poh { positions.push((u64::from_be_bytes(r.sig[..8].try_into().unwrap()), p)); }
                let raw = RawTx::Wire(Arc::from(&raw[..n.min(raw.len())]));
                if !sent(c, out.send(Event::Tx(Arrival { feed: id, slot, t_rx: t, t_decoded, executed: None, tx, poh, raw })).is_ok()) { ok = false; break; }
            }
            drop(tables);
            poh_index().insert_many(&positions, id, t);
            archive(bytes);
            ok
        }
        grpc::Item::Tx { slot, tx, t, executed, raw } => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            c.txs.fetch_add(1, Ordering::Relaxed);
            c.seen(slot, t);
            if !interest.wants(&tx) { return true; }
            c.forwarded.fetch_add(1, Ordering::Relaxed);
            sent(c, out.send(Event::Tx(Arrival { feed: id, slot, t_rx: t, t_decoded: t, executed, tx, poh: None, raw })).is_ok())
        }
        grpc::Item::Account { slot, pubkey, lamports, owner, data, t, txn, write_version, is_startup, bank_id } => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            c.seen(slot, t);
            // one allocation shared by the accounts.bin record and the store (WP-03 item 1)
            let data: Arc<[u8]> = Arc::from(data);
            // every update, stale ones included (the store's verdict is the journal's), with its aseq (and bank, WP-04)
            let aseq = match &fwd.acct {
                Some(a) => a.record(&crate::rec::accounts::AcctUpdate { pubkey, slot, write_version, t_recv: t, src: src::GRPC, is_startup, txn, lamports, owner, data: &data,
                    bank_id }),
                None => 0,
            };
            sent(c, out.send(Event::Account { slot, pubkey, owner, lamports, data, t, txn, write_version, is_startup, src: src::GRPC, aseq, bank_id }).is_ok())
        }
        grpc::Item::Slot { slot, status, t, parent, dead_error, bank_id } => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            // the feed's newest slot (feedhealth `slot_max_now`, `slot_lag_now`) by commitment statuses only: interslot
            // ones (first-shred, created-bank) run ahead of every processed slot (review WP-03 #6). Slot 0 moves no maximum
            c.seen(if (0..=2).contains(&status) { slot } else { 0 }, t);
            // slots.jsonl (MEASUREMENT §4.17): every status of every slot, with its parent
            if rec.is_on() && fwd.state {
                let de = dead_error.clone();
                rec.emit(rec::SLOTS, Record::enc(move |o| {
                    let _ = serde_json::to_writer(o, &serde_json::json!({ "slot": slot, "status": slot_status_name(status), "parent": parent, "dead_error": de, "t": t,
                        "bank_id": bank_id }));
                }));
            }
            sent(c, out.send(Event::Slot { slot, status, t, parent, dead_error, bank_id }).is_ok())
        }
        grpc::Item::BlockMeta(b) => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            c.seen(b.slot, b.t);
            // blocks.jsonl (MEASUREMENT §4.16), with the slot's leader when the LeaderBook knows it
            if rec.is_on() {
                let leader = fwd.leaders.as_ref().and_then(|l| l.leader(b.slot));
                let x = b.clone();
                rec.emit(rec::BLOCKS, Record::enc(move |o| {
                    let _ = serde_json::to_writer(o, &serde_json::json!({ "slot": x.slot, "parent_slot": x.parent_slot, "blockhash": crate::tx::b58(&x.blockhash),
                        "parent_blockhash": crate::tx::b58(&x.parent_blockhash), "block_height": x.block_height, "block_time": x.block_time,
                        "executed_tx_count": x.executed_transaction_count, "entries_count": x.entries_count, "leader": leader.map(|k| crate::tx::b58(&k)),
                        "t_recv": x.t, "src": "grpc", "bank_id": x.bank_id }));
                }));
            }
            sent(c, out.send(Event::BlockMeta(b)).is_ok())
        }
    }
}

/// slots.jsonl `status` (Yellowstone SlotStatus)
pub fn slot_status_name(s: i32) -> &'static str {
    match s { 0 => "processed", 1 => "confirmed", 2 => "finalized", 3 => "first_shred", 4 => "completed", 5 => "created_bank", 6 => "dead", _ => "unknown" }
}

/// The state stream's health as an engine input (journaled INPUT kind 6 `health`; PLAN-ADDENDUM I-4): `connected` true
/// right before the first message of each (re)connection, false when the stream ends or fails (with the error). The
/// engine prices nothing while the stream is down, and reads every followed account again after a reconnect
pub fn state_health(connected: bool, connects: u64, reconnects: u64, error: Option<String>) -> Event {
    let msg = error.map(|e| crate::rpc::scrub(&e));
    Event::Input { kind: InputKind::Health, data: Arc::new(serde_json::json!({ "src": "state", "connected": connected, "connects": connects, "reconnects": reconnects,
        "error": msg })) }
}

/// Start the pool-state stream (accounts + slots, and block meta when `subs` says so) on `rt` (the hot runtime). The
/// engine changes the followed accounts through `list`. `c`: its counters (feedhealth.jsonl feed `state`); `rec` and
/// `fwd`: accounts.bin, slots.jsonl and blocks.jsonl (WP-03). Each connection's first message and each end are engine
/// inputs (`state_health`, WP-04 / I-4)
#[allow(clippy::too_many_arguments)]
pub fn start_state(url: String, token: Option<String>, list: tokio::sync::watch::Receiver<Vec<String>>, subs: grpc::StateSubs, out: UnboundedSender<Event>,
    stop: Arc<AtomicBool>, rt: &tokio::runtime::Handle, c: Arc<FeedCounters>, rec: Rec, fwd: Fwd) {
    rt.spawn(async move {
        let mut backoff = 500u64;
        let interest = Interest::default();
        let mut connects = 0u64;
        while !stop.load(Ordering::Relaxed) {
            // accounts.bin MARK stream_reconnect: updates written between the two connections were not seen
            if connects > 0 { if let Some(a) = &fwd.acct { a.mark(crate::rec::accounts::MARK_STREAM_RECONNECT, &[]); } }
            connects += 1;
            let started = now_ns();
            let reconnects = c.reconnects.load(Ordering::Relaxed);
            // review F1: the slot of the first update after each (re)connect goes to run.log (the snapshot's slot is
            // there too): writes between the two are not seen until the account's next write (WP-04: the engine reads
            // every followed account again after a reconnect)
            let first = std::sync::atomic::AtomicBool::new(true);
            let sink = |it: grpc::Item| -> bool {
                if first.swap(false, Ordering::Relaxed) {
                    let _ = out.send(state_health(true, connects, reconnects, None));
                    let (slot, what) = match &it { grpc::Item::Account { slot, .. } => (*slot, "account"), grpc::Item::Slot { slot, .. } => (*slot, "slot"), _ => (0, "other") };
                    let _ = out.send(Event::Status { feed: u16::MAX, msg: format!("state stream: first update at slot {slot} ({what}), {:.0} ms after connecting",
                        now_ns().saturating_sub(started) as f64 / 1e6) });
                }
                forward(u16::MAX, &interest, &out, &c, None, &rec, &fwd, it)
            };
            let res = grpc::accounts_once(&url, token.as_deref(), list.clone(), subs, &c, &sink).await;
            c.connected.store(false, Ordering::Relaxed);
            if stop.load(Ordering::Relaxed) { break; }
            let reconnects = c.reconnects.fetch_add(1, Ordering::Relaxed) + 1;
            let msg = match res { Ok(()) => "stream closed".to_string(), Err(e) => { c.errors.fetch_add(1, Ordering::Relaxed); format!("{e:#}") } };
            let _ = out.send(state_health(false, connects, reconnects, Some(msg.clone())));
            let _ = out.send(Event::Status { feed: u16::MAX, msg: format!("state stream: {msg}; reconnecting in {backoff} ms") });
            if now_ns() - started > 30_000_000_000 { backoff = 500; }
            tokio::time::sleep(std::time::Duration::from_millis(backoff)).await;
            backoff = (backoff * 2).min(10_000);
        }
    });
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> std::path::PathBuf {
        let d = std::env::temp_dir().join(format!("arbx-feeds-{name}-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    /// a recorder for one entries feed `ent`, archived
    fn recorder(d: &std::path::Path) -> Rec {
        rec::start(rec::Opts { dir: d.to_path_buf(), run: "t".into(), producer: "p".into(), cfg: crate::config::RecordCfg { archive_feeds: vec!["ent".into()], ..Default::default() },
            feeds: vec!["ent".into()], monitor: false, echo: Some(Box::new(std::io::sink())) }).unwrap()
    }

    /// a legacy transaction with one signature of `sig` bytes
    fn legacy_tx(sig: u8) -> Vec<u8> {
        let mut t = vec![1u8];
        t.extend([sig; 64]);
        t.extend([1, 0, 1]);
        t.push(2);
        t.extend([9u8; 32]);
        t.extend([3u8; 32]);
        t.extend([7u8; 32]);
        t.push(1);
        t.push(1);
        t.push(1); t.push(0);
        t.push(3); t.extend([1, 2, 3]);
        t
    }

    /// an entries message: (num_hashes, transactions) per entry
    fn msg(ents: &[(u64, Vec<Vec<u8>>)]) -> Vec<u8> {
        let mut b = (ents.len() as u64).to_le_bytes().to_vec();
        for (h, txs) in ents {
            b.extend(h.to_le_bytes());
            b.extend([0u8; 32]);
            b.extend((txs.len() as u64).to_le_bytes());
            for t in txs { b.extend(t); }
        }
        b
    }

    /// review F12: what an entries feed records through the recorder: poh.log v2 (`sig8 slot ms feed entry_idx`, one
    /// record per message, a line per transaction; WP-08: the entry's index in a slot followed from its start),
    /// slots-feed.log v2 (the eight v1 columns, four `-` shred columns, poh_complete) and the raw archive in its v1 frame
    /// layout (`u64 slot | u64 t | u32 len | bytes`)
    #[test]
    fn an_entries_feed_records_poh_slots_and_its_archive() {
        let d = tmp("ent");
        let rec = recorder(&d);
        let (tx, _rx) = crossbeam_channel::unbounded();
        let c = FeedCounters::named("ent", "jito-entries");
        let clock = std::sync::Mutex::new(entries::PohClock::default());
        let interest = Interest::default();
        // slot 10 joined midway (no PoH positions); slot 11 from its start: a tick of 100 hashes, then two
        // transactions 50 hashes later (1.5 ticks: 9.375 ms)
        let m10 = msg(&[(100, vec![legacy_tx(1)])]);
        let m11 = msg(&[(100, vec![]), (50, vec![legacy_tx(0x22), legacy_tx(0x33)])]);
        let fwd = Fwd::default();
        assert!(forward(0, &interest, &tx, &c, Some(&clock), &rec, &fwd, grpc::Item::Entries { slot: 10, bytes: m10.clone(), t: 1_000 }));
        assert!(forward(0, &interest, &tx, &c, Some(&clock), &rec, &fwd, grpc::Item::Entries { slot: 11, bytes: m11.clone(), t: 2_000 }));
        rec.close();
        assert_eq!(rec::read_text(&d, "poh").unwrap(), vec!["2222222222222222 11 9.375 0 1", "3333333333333333 11 9.375 0 1"]);
        assert_eq!(rec::read_text(&d, "slots-feed").unwrap(), vec!["0 10 0 1 1 1000 1000 0 - - - - 0"]);
        let m: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(d.join("manifest.json")).unwrap()).unwrap();
        let poh = m["streams"].as_array().unwrap().iter().find(|s| s["name"] == "poh").unwrap();
        assert_eq!(poh["records_total"].as_u64(), Some(2), "one queue slot, two lines");
        let b = rec::read_files(&d, "entries-ent").unwrap().remove(0);
        let hlen = u16::from_le_bytes([b[10], b[11]]) as usize;
        let mut p = 12 + hlen;
        for (slot, t, bytes) in [(10u64, 1_000u64, &m10), (11, 2_000, &m11)] {
            assert_eq!(u64::from_le_bytes(b[p..p + 8].try_into().unwrap()), slot);
            assert_eq!(u64::from_le_bytes(b[p + 8..p + 16].try_into().unwrap()), t);
            let n = u32::from_le_bytes(b[p + 16..p + 20].try_into().unwrap()) as usize;
            assert_eq!(&b[p + 20..p + 20 + n], bytes.as_slice());
            p += 20 + n;
        }
        assert_eq!(p, b.len());
        let _ = std::fs::remove_dir_all(&d);
    }

    /// PLAN WP-03 acceptance, the synthetic stream fixture (F12): testdata/grpc/stream.bin (SubscribeUpdate messages
    /// encoded from the vendored proto text: wallet and pool account updates, PumpSwap transactions, slots with a fork,
    /// block meta) through `forward` into a channel, then through the engine's `step`. Checks the events' fields, and
    /// the accounts.bin, journal.bin (with its aseq references), exec.jsonl v2, slots.jsonl and blocks.jsonl records
    #[test]
    fn grpc_stream_fixture_through_forward() {
        use crate::rec::accounts::{role, AcctRec, RoleOf, Roles};
        use crate::rec::journal::{self, JBody};
        use fixture::{k, sig, Proto};
        use prost::Message as _;
        let p = Proto::load();
        let msgs = fixture::stream(&p);
        // the committed file is what the generator makes (ARBX_WRITE_FIXTURES=1 rewrites it)
        let bytes = fixture::encode_file(&msgs);
        if std::env::var("ARBX_WRITE_FIXTURES").is_ok() { std::fs::write(fixture::file_path(), &bytes).unwrap(); }
        let file = std::fs::read(fixture::file_path()).expect("testdata/grpc/stream.bin (ARBX_WRITE_FIXTURES=1 cargo test --release grpc_stream_fixture)");
        assert!(file == bytes, "testdata/grpc/stream.bin is stale: regenerate it with ARBX_WRITE_FIXTURES=1");
        let msgs = fixture::decode_file(&file);
        let d = tmp("fixture");
        let rec = rec::start(rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec!["haan-grpc".into()], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        let ri = |role: u8, pool_index: u32| RoleOf { role, pool_index };
        let roles = Arc::new(Roles::new([(k(fixture::WALLET), ri(role::WALLET, u32::MAX)), (k(fixture::POOL), ri(role::POOL, 0)),
            (k(fixture::VAULT0), ri(role::VAULT, 0)), (k(fixture::VAULT1), ri(role::VAULT, 0))]));
        let acct = AcctRec::new(rec.clone(), roles.clone());
        let book = crate::leaders::LeaderBook::new(Rec::off());
        book.add_window(1_000, &[k(0x99)]);
        let fwd = Fwd { state: true, acct: Some(acct.clone()), leaders: Some(book) };
        let (out, rx) = crossbeam_channel::unbounded();
        let (cs, ct) = (FeedCounters::named("state", "state-stream"), FeedCounters::named("haan-grpc", "yellowstone-tx"));
        let interest = Interest { keys: [fixture::pumpswap()].into_iter().collect(), tables: Default::default() };
        let mut recent = crate::rec::exec::Recent::default();
        for (t, b) in &msgs {
            let m = grpc::SubscribeUpdate::decode(&b[..]).unwrap();
            if let Some(c) = &m.created_at { let ns = c.ns().unwrap(); if m.transaction.is_some() { ct.provider_lag(*t, ns) } else { cs.provider_lag(*t, ns) } }
            match m.transaction.clone() {
                Some(u) => { let it = grpc::tx_stream_item(u, *t, &rec, Some(&roles), &mut recent).unwrap(); assert!(forward(0, &interest, &out, &ct, None, &rec, &Fwd::default(), it)); }
                None => { let it = grpc::state_item(m, *t).unwrap(); assert!(forward(u16::MAX, &interest, &out, &cs, None, &rec, &fwd, it)); }
            }
        }
        let evs: Vec<Event> = rx.try_iter().collect();
        assert_eq!(evs.len(), 15);
        // the events: accounts carry write_version, is_startup, src and their aseq (0.. in arrival order); slots their
        // parent and dead error; the block meta; transactions their protobuf bytes and executed flag
        let accs: Vec<(Pk, u64, u64, bool, u8, u64, Option<[u8; 64]>)> = evs.iter().filter_map(|e| match e {
            Event::Account { pubkey, slot, write_version, is_startup, src, aseq, txn, .. } => Some((*pubkey, *slot, *write_version, *is_startup, *src, *aseq, *txn)), _ => None }).collect();
        assert_eq!(accs, vec![(k(fixture::WALLET), 1_000, 100, false, 0, 0, Some(sig(fixture::OURS))), (k(fixture::VAULT0), 1_000, 101, false, 0, 1, Some(sig(fixture::T1))),
            (k(fixture::VAULT1), 1_000, 102, false, 0, 2, Some(sig(fixture::T1))), (k(fixture::POOL), 1_000, 103, false, 0, 3, Some(sig(fixture::T1))),
            (k(fixture::VAULT0), 999, 90, false, 0, 4, Some(sig(fixture::OLD))), (k(fixture::VAULT1), 1_002, 104, true, 0, 5, Some(sig(fixture::T2)))]);
        let slots: Vec<(u64, i32, Option<u64>, Option<String>)> = evs.iter().filter_map(|e| match e {
            Event::Slot { slot, status, parent, dead_error, .. } => Some((*slot, *status, *parent, dead_error.clone())), _ => None }).collect();
        assert_eq!(slots[4], (1_001, 6, Some(1_000), Some("fork abandoned".into())));
        assert_eq!(slots.len(), 6);
        assert!(evs.iter().any(|e| matches!(e, Event::BlockMeta(b) if b.slot == 1_000 && b.block_height == Some(900))));
        let txs: Vec<&Arrival> = evs.iter().filter_map(|e| match e { Event::Tx(a) => Some(a), _ => None }).collect();
        assert_eq!((txs.len(), txs[0].executed, txs[1].executed), (2, Some(true), Some(false)));
        assert!(matches!(txs[0].raw, RawTx::Pb(_)));
        assert_eq!(txs[0].tx.loaded, Some((vec![k(fixture::LW)], vec![k(fixture::LR)])));
        let t1 = txs[0].tx.clone();
        // the engine journals them at its dequeue point. WP-04: its registry holds the fixture's PumpSwap pool (and a second
        // pool on its pair), so the pool's writes form commit groups
        let ps = |pool: u8, v0: u8, v1: u8| crate::venues::PoolMeta { venue: crate::venues::Venue::PumpSwap, pool: k(pool), t0: k(0x41), t1: *crate::venues::WSOL,
            vault0: k(v0), vault1: k(v1), t0_prog: fixture::token(), t1_prog: fixture::token(), extra: vec![k(0x41)], flag: true };
        let mut reg = crate::pools::Registry { pools: vec![ps(fixture::POOL, fixture::VAULT0, fixture::VAULT1), ps(0x64, 0x65, 0x66)], by_pool: Default::default(),
            pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
        reg.by_pool.insert(k(fixture::POOL), 0);
        reg.by_pool.insert(k(0x64), 1);
        reg.pairs.insert(crate::pools::pair_key(&k(0x41), &crate::venues::WSOL), vec![0, 1]);
        let mut e = crate::engine::Engine::new_offline(Arc::new(reg), crate::store::Store::default(), crate::config::StrategyCfg::default());
        e.set_rec(rec.clone());
        let mut status = |_: &str| {};
        for (i, ev) in evs.into_iter().enumerate() { e.step(ev, fixture::T0 + 100 + i as u64, &mut status); }
        e.timers(fixture::T0 + 1_000, &mut status);
        // the timers after the stream's last message (T2's lone update, W unknown, resolves by quiescence)
        e.timers(fixture::T0 + 100_000_000, &mut status);
        assert_eq!((e.store.updates, e.store.stale_dropped), (5, 1), "one stale update refused");
        assert!(cs.provider_lag.lock().unwrap().as_mut().unwrap().pct(0.5) == 2_000_000, "2 ms provider lag");
        rec.close();
        // accounts.bin: every update, the stale one too, in aseq order, with its role, write version and txn; the
        // second update of each vault is an XOR record whose data reconstructs
        let a = crate::rec::accounts::read_dir(&d).unwrap();
        assert_eq!(a.records.iter().map(|r| r.aseq).collect::<Vec<_>>(), vec![0, 1, 2, 3, 4, 5]);
        assert_eq!(a.records.iter().map(|r| r.role).collect::<Vec<_>>(), vec![role::WALLET, role::VAULT, role::VAULT, role::POOL, role::VAULT, role::VAULT]);
        assert_eq!(a.records.iter().map(|r| r.kind).collect::<Vec<_>>(), vec![2, 2, 2, 2, 3, 3]);
        assert_eq!((a.records[4].write_version, a.records[4].txn, a.records[4].data.clone()), (90, Some(sig(fixture::OLD)), fixture::vault_data(900_000)));
        assert_eq!((a.records[5].is_startup, a.records[5].data.clone(), a.records[3].pool_index), (true, fixture::vault_data(2_100_000), Some(0)));
        assert_eq!(a.header["schema"], serde_json::json!("arbx.accounts/2.1"));
        // journal.bin: the ACCOUNT records name those aseqs with the store's verdicts; TX_FIRST holds the protobuf
        // transaction and its loaded addresses (it decodes back to the same transaction); slots carry their parents
        let j = journal::read_dir(&d).unwrap();
        assert_eq!(j.iter().map(|r| r.seq).collect::<Vec<_>>(), (0..j.len() as u64).collect::<Vec<_>>(), "seq without holes");
        let acc: Vec<(u64, bool)> = j.iter().filter_map(|r| match r.body { JBody::Account { aseq, stale } => Some((aseq, stale)), _ => None }).collect();
        assert_eq!(acc, vec![(0, false), (1, false), (2, false), (3, false), (4, true), (5, false)]);
        let by_aseq: std::collections::HashMap<u64, &crate::rec::accounts::AcctRecord> = a.records.iter().map(|r| (r.aseq, r)).collect();
        for (q, _) in &acc { assert!(by_aseq.contains_key(q), "aseq {q} in accounts.bin"); }
        let first: Vec<&JBody> = j.iter().filter(|r| matches!(r.body, JBody::TxFirst { .. })).map(|r| &r.body).collect();
        assert_eq!(first.len(), 2);
        let JBody::TxFirst { feed, slot, t_rx, t_decoded, executed, enc, bytes, loaded, poh } = first[0].clone() else { unreachable!() };
        assert_eq!((feed, slot, enc, executed, loaded.clone()), (0, 1_000, journal::ENC_PB, Some(true), Some((vec![k(fixture::LW)], vec![k(fixture::LR)]))));
        let back = journal::arrival(feed, slot, t_rx, t_decoded, executed, enc, &bytes, &loaded, poh).unwrap();
        assert_eq!((back.tx.sig, back.tx.keys.clone(), back.tx.loaded.clone(), back.tx.cu_price_micro, back.tx.lookups.len()), (t1.sig, t1.keys.clone(), t1.loaded.clone(), Some(5_000), 1));
        let sl: Vec<(u64, Option<u64>, i32)> = j.iter().filter_map(|r| match r.body { JBody::Slot { slot, parent, status, .. } => Some((slot, parent, status)), _ => None }).collect();
        assert_eq!(sl[4], (1_001, Some(1_000), 6));
        assert!(j.iter().any(|r| matches!(r.body, JBody::BlockMeta { slot: 1_000, height: Some(900), .. })));
        assert!(j.iter().any(|r| matches!(r.body, JBody::Timer { t, .. } if t == fixture::T0 + 1_000)), "the timers' evaluation");
        assert!(j.iter().zip(j.iter().skip(1)).all(|(x, y)| x.t_engine <= y.t_engine), "engine times in order");
        // exec.jsonl v2: the PumpSwap transactions with their full meta
        let ex = rec::read_jsonl(&d, "exec").unwrap();
        assert_eq!(ex.len(), 2);
        let x = &ex[0];
        let b = |n: u8| bs58::encode(k(n)).into_string();
        assert_eq!((x["sig"].as_str(), x["slot"].as_u64(), x["idx"].as_u64(), x["src"].as_str(), x["found_by"].clone()),
            (Some(bs58::encode(sig(fixture::T1)).into_string().as_str()), Some(1_000), Some(17), Some("grpc-tx"), serde_json::json!(["tx_stream"])));
        assert_eq!((x["ok"].as_bool(), x["fee"].as_u64(), x["cu"].as_u64(), x["cost_units"].as_u64(), x["version"].as_str()), (Some(true), Some(6_000), Some(45_000), Some(61_000), Some("0")));
        assert_eq!((x["cu_limit"].as_u64(), x["cu_price_micro"].as_u64(), x["priority_fee"].as_u64(), x["n_static"].as_u64()), (Some(200_000), Some(5_000), Some(1_000), Some(7)));
        assert_eq!(x["keys"].as_array().unwrap().len(), 9, "static keys, then loaded writable, then loaded readonly");
        assert_eq!((x["keys"][7].as_str(), x["keys"][8].as_str()), (Some(b(fixture::LW).as_str()), Some(b(fixture::LR).as_str())));
        assert_eq!(x["recent_blockhash"].as_str(), Some(b(0x33).as_str()));
        assert_eq!(x["alts"], serde_json::json!([{ "table": b(fixture::ALT), "w": [3], "r": [9] }]));
        assert_eq!(x["inner"][0]["list"][0], serde_json::json!({ "p": 6, "a": [2, 0], "d": "AwkJ", "h": 2 }));
        assert_eq!(x["return_data"], serde_json::json!({ "program": bs58::encode(fixture::pumpswap()).into_string(), "data": "AQID" }));
        assert_eq!(x["logs"].as_array().unwrap().len(), 2);
        assert_eq!(x["post_tok"][0]["dec"].as_u64(), Some(6));
        assert_eq!((x["signer_sol"].as_i64(), x["signer_tok"].clone()), (Some(-6_000), serde_json::json!({ b(0x41): "500" })));
        assert_eq!(x["venues"], serde_json::json!(["pumpswap"]));
        assert_eq!(x["pools"], serde_json::json!([b(fixture::POOL)]));
        assert_eq!(x["watched"], serde_json::json!([{ "acct": b(fixture::POOL), "role": "pool", "pool": 0 }, { "acct": b(fixture::VAULT0), "role": "vault", "pool": 0 },
            { "acct": b(fixture::VAULT1), "role": "vault", "pool": 0 }]));
        // WP-08's derived fields are filled on the writer (src/classify.rs; `ours` waits for WP-05)
        assert!(x["transfers"].is_array() && x["arb_like"].is_object() && x["tip_total"].is_u64() && x["ours"].is_null(), "{x}");
        let y = &ex[1];
        assert_eq!((y["ok"].as_bool(), y["err"].as_str(), y["err_ix"].as_u64(), y["idx"].as_u64()), (Some(false), Some("ix2:custom:0x1771"), Some(2), Some(3)));
        assert!(y["logs"].is_null() && y["inner"].is_null() && y["return_data"].is_null(), "the provider omitted them: null, not empty");
        assert_eq!(y["watched"], serde_json::json!([]), "a failed transaction writes no watched account");
        // slots.jsonl and blocks.jsonl
        let s = rec::read_jsonl(&d, "slots").unwrap();
        assert_eq!(s.len(), 6);
        assert_eq!(s[4], serde_json::json!({ "slot": 1_001, "status": "dead", "parent": 1_000, "dead_error": "fork abandoned", "t": s[4]["t"], "bank_id": null }));
        assert_eq!((s[1]["status"].as_str(), s[0]["parent"].as_u64()), (Some("first_shred"), Some(999)));
        let bl = rec::read_jsonl(&d, "blocks").unwrap();
        assert_eq!((bl[0]["slot"].as_u64(), bl[0]["blockhash"].as_str(), bl[0]["leader"].as_str(), bl[0]["block_height"].as_u64()),
            (Some(1_000), Some(b(0x34).as_str()), Some(b(0x99).as_str()), Some(900)));
        assert!(bl[0]["bank_id"].is_null() && x["bank_id"].is_null(), "the fixture's provider sends no bank_id");
        // WP-04 through `forward`: T1's three writes form one group, whose write set the PumpSwap transaction stream
        // registered after the updates (authoritative: `tx-stream`), and it completed then; T2's lone write (W unknown: its
        // transaction failed, so nothing registered it) resolved by quiescence; the dead slot 1001 was abandoned
        let c = rec::read_jsonl(&d, "commits").unwrap();
        let t1 = c.iter().find(|x| x["txn"] == serde_json::json!(bs58::encode(sig(fixture::T1)).into_string())).expect("T1's group");
        assert_eq!((t1["outcome"].as_str(), t1["w_src"].as_str(), t1["w_late"].as_bool(), t1["resolved_by"].as_str(), t1["w_seen"].as_array().unwrap().len()),
            (Some("complete"), Some("tx-stream"), Some(true), Some("register"), 3));
        let t2 = c.iter().find(|x| x["txn"] == serde_json::json!(bs58::encode(sig(fixture::T2)).into_string())).expect("T2's group");
        assert_eq!((t2["outcome"].as_str(), t2["w_src"].as_str()), (Some("timeout_quiescent"), Some("unknown")));
        assert_eq!(e.counter("fork_dead_slot"), 1, "slot 1001 died");
        let _ = std::fs::remove_dir_all(&d);
    }

    /// Review WP-04 #6, PLAN WP-04 offline acceptance: the S1, S1b' and S8b sequences as synthetic protobuf streams
    /// (testdata/grpc/wp04.bin, regenerated with ARBX_WRITE_FIXTURES=1) through `grpc::state_item` / `tx_stream_item`,
    /// `forward` and the engine's `step`, with the timers after every message (an empty queue): the split route's group
    /// learns its write set from the transaction stream and completes only with B's vaults, C's evaluation in between
    /// refuses the routes through A and B (`pending_commit`); the unknown-W group resolves by quiescence and its late write
    /// is a late member; the minority fork's writes are `fork_pending` while both siblings are unconfirmed, and dropped
    /// when the other is confirmed (no `dead` status)
    #[test]
    fn grpc_wp04_sequences_through_forward() {
        use fixture::{k, sig, Proto};
        use prost::Message as _;
        let p = Proto::load();
        let bytes = fixture::encode_file(&fixture::wp04_stream(&p));
        if std::env::var("ARBX_WRITE_FIXTURES").is_ok() { std::fs::write(fixture::wp04_file_path(), &bytes).unwrap(); }
        let file = std::fs::read(fixture::wp04_file_path()).expect("testdata/grpc/wp04.bin (ARBX_WRITE_FIXTURES=1 cargo test --release grpc_wp04)");
        assert!(file == bytes, "testdata/grpc/wp04.bin is stale: regenerate it with ARBX_WRITE_FIXTURES=1");
        let d = tmp("wp04-fixture");
        let rec = rec::start(rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec!["haan-grpc".into()], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        // three PumpSwap pools on one pair, every part held at slot 1999
        let ps = |pool: u8, v0: u8, v1: u8| crate::venues::PoolMeta { venue: crate::venues::Venue::PumpSwap, pool: k(pool), t0: k(0x41), t1: *crate::venues::WSOL,
            vault0: k(v0), vault1: k(v1), t0_prog: fixture::token(), t1_prog: fixture::token(), extra: vec![k(0x41)], flag: true };
        let pools = [ps(fixture::POOL, fixture::VAULT0, fixture::VAULT1), ps(fixture::POOL_B, fixture::VAULT_B0, fixture::VAULT_B1), ps(fixture::POOL_C, fixture::VAULT_C0, fixture::VAULT_C1)];
        let mut reg = crate::pools::Registry { pools: pools.to_vec(), by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
        let mut store = crate::store::Store::default();
        for (i, m) in pools.iter().enumerate() {
            reg.by_pool.insert(m.pool, i);
            store.update(m.pool, Arc::from(&[8u8; 300][..]), 1_999, 1, None);
            for v in [m.vault0, m.vault1] { store.update(v, Arc::from(fixture::vault_data(1_000_000)), 1_999, 1, None); }
        }
        store.update(*crate::pools::PUMP_FEE_CONFIG, Arc::from(&[0u8; 64][..]), 1_999, 1, None);
        store.update(k(0x41), Arc::from(&[0u8; 82][..]), 1_999, 1, None);
        reg.pairs.insert(crate::pools::pair_key(&k(0x41), &crate::venues::WSOL), vec![0, 1, 2]);
        let mut e = crate::engine::Engine::new_offline(Arc::new(reg), store, crate::config::StrategyCfg { state_triggers: true, ..Default::default() });
        e.set_rec(rec.clone());
        let (out, rx) = crossbeam_channel::unbounded();
        let (cs, ct) = (FeedCounters::named("state", "state-stream"), FeedCounters::named("haan-grpc", "yellowstone-tx"));
        let interest = Interest { keys: [fixture::pumpswap()].into_iter().collect(), tables: Default::default() };
        let mut recent = crate::rec::exec::Recent::default();
        let mut status = |_: &str| {};
        for (t, b) in fixture::decode_file(&file) {
            let m = grpc::SubscribeUpdate::decode(&b[..]).unwrap();
            match m.transaction.clone() {
                Some(u) => { let it = grpc::tx_stream_item(u, t, &rec, None, &mut recent).unwrap(); assert!(forward(0, &interest, &out, &ct, None, &rec, &Fwd::default(), it)); }
                None => { let it = grpc::state_item(m, t).unwrap(); assert!(forward(u16::MAX, &interest, &out, &cs, None, &rec, &Fwd::default(), it)); }
            }
            for ev in rx.try_iter() { e.step(ev, t + 10_000, &mut status); }
            e.timers(t + 20_000, &mut status);
        }
        rec.close();
        let b58 = |n: u8| bs58::encode(sig(n)).into_string();
        let c = rec::read_jsonl(&d, "commits").unwrap();
        let group = |n: u8| c.iter().find(|x| x["txn"] == serde_json::json!(b58(n)) && x.get("outcome").is_some()).unwrap_or_else(|| panic!("{n:#x}'s group")).clone();
        // S1: T3's write set from the transaction stream (after its first two updates), complete with B's vaults
        let t3 = group(fixture::T3);
        assert_eq!((t3["outcome"].as_str(), t3["w_src"].as_str(), t3["w_late"].as_bool(), t3["resolved_by"].as_str(), t3["w_seen"].as_array().unwrap().len()),
            (Some("complete"), Some("tx-stream"), Some(true), Some("member"), 6));
        let dec = rec::read_jsonl(&d, "decisions").unwrap();
        let of = |n: u8| -> Vec<serde_json::Value> { dec.iter().filter(|x| x["trigger"]["txn"] == serde_json::json!(b58(n))).cloned().collect() };
        let u = of(fixture::U);
        assert_eq!(u.len(), 1, "C evaluated once U resolved");
        assert!(u[0]["routes"].as_array().unwrap().iter().all(|r| r["reason"] == "pending_commit"), "C's routes through A and B wait for T3: {}", u[0]);
        assert_eq!(of(fixture::T3).len(), 2, "A and B evaluated once T3 completed");
        // S1b': T4 resolved by quiescence; its write that came after is a late member
        assert_eq!(group(fixture::T4)["outcome"].as_str(), Some("timeout_quiescent"));
        assert!(c.iter().any(|x| x["txn"] == serde_json::json!(b58(fixture::T4)) && x["late"] == serde_json::json!(true)
            && x["late_members"][0]["acct"] == serde_json::json!(crate::tx::b58(&k(fixture::VAULT0)))));
        assert_eq!(e.counter("commit_late_member"), 1);
        // S8b: A written in the minority fork 2002: fork_pending while 2002 and 2003 are both unconfirmed; 2003 confirmed:
        // 2002 abandoned (no dead status), its versions dropped, A evaluated again on its canonical (slot 2001) state
        let t5 = of(fixture::T5);
        assert!(!t5.is_empty() && t5.iter().all(|x| x["routes"].as_array().unwrap().iter().filter(|r| r["buy"] == serde_json::json!(crate::tx::b58(&k(fixture::POOL)))
            || r["sell"] == serde_json::json!(crate::tx::b58(&k(fixture::POOL)))).all(|r| r["reason"] == "fork_pending")), "{t5:?}");
        assert_eq!((e.counter("fork_abandoned_slot"), e.counter("fork_dead_slot"), e.counter("fork_versions_dropped")), (1, 0, 2));
        assert_eq!((e.store.get(&k(fixture::VAULT0)).unwrap().slot, e.store.get(&k(fixture::VAULT1)).unwrap().slot), (2_001, 2_001));
        assert!(dec.iter().any(|x| x["kind"] == "fork"));
        let _ = std::fs::remove_dir_all(&d);
    }

    /// PLAN WP-08 item 2: the PoH index keeps the earliest position of a forwarded transaction per signature, by feed,
    /// for 3 minutes; an entries feed's forwarded transactions go there (the walk in `forward`)
    #[test]
    fn the_poh_index_and_an_entries_feeds_forwarded_positions() {
        let ix = PohIndex::new();
        let p = |slot: u64, h: u64| entries::Poh { slot, hashes: h, ticks: 1, hpt: 100 };
        ix.insert_many(&[(7, p(1, 150)), (8, p(1, 160))], 2, 1_000);
        ix.insert_many(&[(7, p(1, 140))], 3, 2_000);
        assert_eq!((ix.get(7), ix.get(8).map(|x| x.1), ix.get(9)), (Some((p(1, 150), 2)), Some(2), None), "the first position of a signature stays");
        ix.insert_many(&[(10, p(2, 100))], 1, 1_000 + POH_KEEP_NS);
        assert_eq!((ix.get(7), ix.get(8), ix.get(10).map(|x| x.1), ix.len()), (None, None, Some(1), 1), "kept 3 minutes");
        // through `forward`: the walked message's forwarded transactions (a watched key) are indexed with the feed id
        let (tx, _rx) = crossbeam_channel::unbounded();
        let c = FeedCounters::named("ent", "jito-entries");
        let clock = std::sync::Mutex::new(entries::PohClock::default());
        let interest = Interest { keys: [[3u8; 32]].into_iter().collect(), tables: Default::default() };
        let m = msg(&[(100, vec![])]);
        assert!(forward(6, &interest, &tx, &c, Some(&clock), &Rec::off(), &Fwd::default(), grpc::Item::Entries { slot: 20, bytes: m, t: 1 }));
        let m = msg(&[(100, vec![]), (25, vec![legacy_tx(0x6a)])]);
        assert!(forward(6, &interest, &tx, &c, Some(&clock), &Rec::off(), &Fwd::default(), grpc::Item::Entries { slot: 21, bytes: m, t: 2 }));
        let (pos, feed) = poh_index().get_sig(&[0x6a; 64]).expect("indexed");
        assert_eq!((pos.slot, pos.hashes, pos.ms(), feed), (21, 125, Some(7.8125), 6));
    }

    /// PLAN WP-08 item 2 (F38): `poh_trigger_pct` over the attempts noted since the last status line, and the target
    /// judged only while a PoH-capable feed (entries, raw shreds) is alive
    #[test]
    fn the_poh_trigger_gauge() {
        let g = PohGauge::new();
        let ent = Arc::new(FeedCounters::named("ent", "jito-entries"));
        let tx = Arc::new(FeedCounters::named("tx", "yellowstone-tx"));
        let now = 100_000_000_000;
        tx.seen(1, now);
        let s = g.status(&[ent.clone(), tx.clone()], now);
        assert_eq!((s["poh_trigger_pct"].clone(), s["poh_feeds_alive_now"].as_u64(), s["target_met"].clone()), (serde_json::Value::Null, Some(0), serde_json::Value::Null));
        for has in [true, true, true, false] { g.note_attempt(has); }
        let s = g.status(&[ent.clone(), tx.clone()], now);
        assert_eq!((s["poh_trigger_pct"].as_f64(), s["attempts_delta"].as_u64(), s["target_met"].clone()), (Some(75.0), Some(4), serde_json::Value::Null), "no PoH feed alive: not judged");
        ent.seen(1, now);
        for _ in 0..9 { g.note_attempt(true); }
        g.note_attempt(false);
        let s = g.status(&[ent.clone(), tx.clone()], now + 1_000_000_000);
        assert_eq!((s["poh_trigger_pct"].as_f64(), s["poh_feeds_alive_now"].as_u64(), s["target_met"].as_bool(), s["attempts_total"].as_u64()), (Some(90.0), Some(1), Some(true), Some(14)));
        let s = g.status(&[ent], now + 11_000_000_000);
        assert_eq!((s["attempts_delta"].as_u64(), s["poh_feeds_alive_now"].as_u64()), (Some(0), Some(0)), "silent for 10 s: not alive");
        assert!(poh_capable("udp") && poh_capable("multicast") && !poh_capable("yellowstone-deshred"));
    }

    /// review WP-03 #6: an interslot status (first-shred, created-bank: ahead of every processed slot) counts as a message
    /// of the state stream but does not move its newest slot (feedhealth `slot_max_now`, `slot_lag_now`)
    #[test]
    fn interslot_statuses_do_not_move_the_feeds_newest_slot() {
        let (out, _rx) = crossbeam_channel::unbounded();
        let c = FeedCounters::named("state", "state-stream");
        let slot = |slot: u64, status: i32, t: u64| grpc::Item::Slot { slot, status, t, parent: None, dead_error: None, bank_id: None };
        let interest = Interest::default();
        assert!(forward(u16::MAX, &interest, &out, &c, None, &Rec::off(), &Fwd::default(), slot(4_000, 0, 10)));
        assert!(forward(u16::MAX, &interest, &out, &c, None, &Rec::off(), &Fwd::default(), slot(4_003, 3, 20)));
        assert!(forward(u16::MAX, &interest, &out, &c, None, &Rec::off(), &Fwd::default(), slot(4_003, 5, 30)));
        assert_eq!((c.slot_max.load(Ordering::Relaxed), c.last_msg_ns.load(Ordering::Relaxed)), (4_000, 30));
        assert!(forward(u16::MAX, &interest, &out, &c, None, &Rec::off(), &Fwd::default(), slot(4_001, 1, 40)));
        assert_eq!(c.slot_max.load(Ordering::Relaxed), 4_001);
    }
}

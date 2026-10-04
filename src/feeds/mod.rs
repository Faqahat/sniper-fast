//! Feed layer: every configured feed runs on its own (raw UDP: a thread; gRPC: a task) and pushes `Event`s into one
//! engine channel. Raw shreds are decoded by a streaming assembler, so a transaction leaves the feed the moment its
//! last shred arrived. Only transactions that can matter are forwarded (`Interest`): a static key is a watched program,
//! pool or vault, or one of its lookup tables is known to hold one. Everything else is dropped inside the feed.
pub mod clock;
pub mod entries;
pub mod grpc;
pub mod shred;
pub mod udp;

use crate::config::{Feed, FeedKind};
use crate::tx::{self, Pk, Tx};
use clock::now_ns;
use rustc_hash::FxHashSet as HashSet;
use std::net::Ipv4Addr;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, RwLock};
use crossbeam_channel::Sender as UnboundedSender;

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
}

pub enum Event {
    Tx(Arrival),
    Account { slot: u64, pubkey: Pk, owner: Pk, lamports: u64, data: Vec<u8>, t: u64, txn: Option<[u8; 64]> },
    Slot { slot: u64, status: i32, t: u64 },
    /// a feed connected, reconnected or failed (for the run log)
    Status { feed: u16, msg: String },
    /// a lookup table fetched off the hot path (None: it doesn't exist)
    Alt { table: Pk, addrs: Option<Arc<Vec<Pk>>> },
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

/// Per-feed counters, read by the engine's periodic status line.
#[derive(Default)]
pub struct FeedCounters {
    pub packets: AtomicU64,
    pub txs: AtomicU64,
    pub forwarded: AtomicU64,
    pub reconnects: AtomicU64,
    pub errors: AtomicU64,
}

pub struct Feeds {
    pub names: Vec<String>,
    pub counters: Vec<Arc<FeedCounters>>,
}

/// Start every enabled feed. Returns the feed names (index = `Arrival::feed`) and their counters.
pub fn start(feeds: &[Feed], interest: Arc<Interest>, out: UnboundedSender<Event>, stop: Arc<AtomicBool>, rt: &tokio::runtime::Handle) -> anyhow::Result<Feeds> {
    let mut names = Vec::new();
    let mut counters = Vec::new();
    for f in feeds.iter().filter(|f| f.enabled) {
        let id = names.len() as u16;
        names.push(f.name.clone());
        let c = Arc::new(FeedCounters::default());
        counters.push(c.clone());
        if f.is_raw() {
            let sock = match f.kind {
                FeedKind::Udp => udp::open_unicast(f.bind.as_deref().unwrap())?,
                _ => udp::open_multicast(f.group.as_deref().unwrap(), f.port.unwrap(), f.interface.as_deref().unwrap())?,
            };
            let allowed: Vec<Ipv4Addr> = f.allowed_src.iter().filter_map(|s| s.parse().ok()).collect();
            let (interest, out, stop, c) = (interest.clone(), out.clone(), stop.clone(), c.clone());
            let name = f.name.clone();
            std::thread::Builder::new().name(format!("feed-{name}")).spawn(move || {
                let mut asm = shred::Assembler::new();
                let mut done = Vec::new();
                let mut last_gc = now_ns();
                let key = |k: &Pk| interest.keys.contains(k);
                let res = udp::run(&sock, 2048, || stop.load(Ordering::Relaxed), |p| {
                    c.packets.fetch_add(1, Ordering::Relaxed);
                    if !allowed.is_empty() && !allowed.contains(&p.src) { return; }
                    {
                        let tables = interest.tables.read().unwrap();
                        let table = |k: &Pk| tables.contains(k);
                        let before = asm.stats.txs;
                        asm.push(p.data, p.t_ns, &mut done, &shred::Want { key: &key, table: &table });
                        c.txs.fetch_add(asm.stats.txs - before, Ordering::Relaxed);
                    }
                    if done.is_empty() { return; }
                    let t_decoded = now_ns();
                    for d in done.drain(..) {
                        c.forwarded.fetch_add(1, Ordering::Relaxed);
                        let _ = out.send(Event::Tx(Arrival { feed: id, slot: d.slot, t_rx: d.t, t_decoded, executed: None, tx: d.tx, poh: None }));
                    }
                    if t_decoded - last_gc > 2_000_000_000 { asm.gc(t_decoded); last_gc = t_decoded; }
                });
                if let Err(e) = res { let _ = out.send(Event::Status { feed: id, msg: format!("{name}: receive failed: {e}") }); }
            })?;
        } else {
            let (f, interest, out, stop, c) = (f.clone(), interest.clone(), out.clone(), stop.clone(), c.clone());
            rt.spawn(async move {
                let mut backoff = 500u64;
                while !stop.load(Ordering::Relaxed) {
                    let clock = std::sync::Mutex::new(entries::PohClock::default());
                    let sink = |it: grpc::Item| -> bool { forward(id, &interest, &out, &c, Some(&clock), it) };
                    let started = now_ns();
                    let res = grpc::feed_once(&f, &sink).await;
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

/// Every transaction an entries feed delivers, on its leader's PoH clock: `sig8 slot ms_in_slot` per line (the first
/// 8 signature bytes in hex), for joining with block data offline (who ran how long after which trigger). Set by `run`.
pub static POH_LOG: std::sync::OnceLock<std::sync::Mutex<std::io::BufWriter<std::fs::File>>> = std::sync::OnceLock::new();

pub fn flush_poh_log() { if let Some(l) = POH_LOG.get() { use std::io::Write; let _ = l.lock().unwrap().flush(); } }

/// gRPC item -> engine events (entries are walked here, in the feed task, not in the engine)
fn forward(id: u16, interest: &Interest, out: &UnboundedSender<Event>, c: &FeedCounters, poh: Option<&std::sync::Mutex<entries::PohClock>>, it: grpc::Item) -> bool {
    match it {
        grpc::Item::Entries { slot, bytes, t } => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            let rec = crate::record::get();
            if let Some(r) = rec { r.archive(id, slot, t, &bytes); }
            let Some((refs, ents)) = entries::parse_entries_poh(&bytes) else { return true };
            let pohs = match poh {
                Some(p) => {
                    let (pohs, done) = p.lock().unwrap().entries_at(slot, &ents, t);
                    if let (Some(r), Some(d)) = (rec, done) {
                        crate::record::Recorder::line(&r.slots, &format!("{id} {} {} {} {} {} {} {}", d.slot, d.ticks, d.entries, d.txs, d.t_first, d.t_last, d.valid as u8));
                    }
                    pohs
                }
                None => vec![None; ents.len()],
            };
            if let Some(log) = POH_LOG.get() {
                use std::io::Write;
                let mut w = log.lock().unwrap();
                for r in refs.iter().filter(|r| !r.is_vote) {
                    if let Some(ms) = pohs.get(r.entry as usize).copied().flatten().and_then(|p| p.ms()) {
                        let _ = writeln!(w, "{:016x} {slot} {ms:.3}", u64::from_be_bytes(r.sig[..8].try_into().unwrap()));
                    }
                }
            }
            let t_decoded = now_ns();
            let tables = interest.tables.read().unwrap();
            let (key, table) = (|k: &Pk| interest.keys.contains(k), |k: &Pk| tables.contains(k));
            for r in refs {
                if r.is_vote { continue; }
                c.txs.fetch_add(1, Ordering::Relaxed);
                let raw = &bytes[r.start..r.end];
                if !tx::scan(raw, &key, &table).map_or(false, |s| s.hit) { continue; }
                let Some((tx, _)) = tx::parse_wire(raw) else { continue };
                c.forwarded.fetch_add(1, Ordering::Relaxed);
                let poh = pohs.get(r.entry as usize).copied().flatten();
                if out.send(Event::Tx(Arrival { feed: id, slot, t_rx: t, t_decoded, executed: None, tx, poh })).is_err() { return false; }
            }
            true
        }
        grpc::Item::Tx { slot, tx, t, executed } => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            c.txs.fetch_add(1, Ordering::Relaxed);
            if !interest.wants(&tx) { return true; }
            c.forwarded.fetch_add(1, Ordering::Relaxed);
            out.send(Event::Tx(Arrival { feed: id, slot, t_rx: t, t_decoded: t, executed, tx, poh: None })).is_ok()
        }
        grpc::Item::Account { slot, pubkey, lamports, owner, data, t, txn, .. } =>
            out.send(Event::Account { slot, pubkey, owner, lamports, data, t, txn }).is_ok(),
        grpc::Item::Slot { slot, status, t } => out.send(Event::Slot { slot, status, t }).is_ok(),
    }
}

/// Start the pool-state stream (accounts + slots). The engine changes the followed accounts through `list`.
pub fn start_state(url: String, token: Option<String>, list: tokio::sync::watch::Receiver<Vec<String>>, out: UnboundedSender<Event>, stop: Arc<AtomicBool>, rt: &tokio::runtime::Handle) {
    rt.spawn(async move {
        let mut backoff = 500u64;
        let dummy = FeedCounters::default();
        let interest = Interest::default();
        while !stop.load(Ordering::Relaxed) {
            let started = now_ns();
            // review F1: the slot of the first update after each (re)connect goes to run.log (the snapshot's slot is
            // there too): writes between the two are not seen until the account's next write
            let first = std::sync::atomic::AtomicBool::new(true);
            let sink = |it: grpc::Item| -> bool {
                if first.swap(false, Ordering::Relaxed) {
                    let (slot, what) = match &it { grpc::Item::Account { slot, .. } => (*slot, "account"), grpc::Item::Slot { slot, .. } => (*slot, "slot"), _ => (0, "other") };
                    let _ = out.send(Event::Status { feed: u16::MAX, msg: format!("state stream: first update at slot {slot} ({what}), {:.0} ms after connecting",
                        now_ns().saturating_sub(started) as f64 / 1e6) });
                }
                forward(u16::MAX, &interest, &out, &dummy, None, it)
            };
            let res = grpc::accounts_once(&url, token.as_deref(), list.clone(), &sink).await;
            if stop.load(Ordering::Relaxed) { break; }
            let msg = match res { Ok(()) => "stream closed".to_string(), Err(e) => format!("{e:#}") };
            let _ = out.send(Event::Status { feed: u16::MAX, msg: format!("state stream: {msg}; reconnecting in {backoff} ms") });
            if now_ns() - started > 30_000_000_000 { backoff = 500; }
            tokio::time::sleep(std::time::Duration::from_millis(backoff)).await;
            backoff = (backoff * 2).min(10_000);
        }
    });
}

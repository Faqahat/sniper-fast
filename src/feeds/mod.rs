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
use crate::rec::{self, Rec, Record};
use crate::tx::{self, Pk, Tx};
use clock::now_ns;
use rustc_hash::FxHashSet as HashSet;
use std::net::Ipv4Addr;
use std::sync::atomic::{AtomicBool, AtomicU32, AtomicU64, Ordering};
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

/// feedhealth.jsonl `kind`
fn kind_name(k: &FeedKind) -> String { serde_json::to_value(k).ok().and_then(|v| v.as_str().map(String::from)).unwrap_or_else(|| format!("{k:?}")) }

pub struct Feeds {
    pub names: Vec<String>,
    pub counters: Vec<Arc<FeedCounters>>,
}

/// Start every enabled feed. Returns the feed names (index = `Arrival::feed`) and their counters. `rt` is the hot
/// runtime (gRPC feeds); raw feeds run on their own threads. `rec`: the recorder (poh, slots-feed, exec, entries
/// archives; raw feeds' sockets are followed for kernel drops)
pub fn start(feeds: &[Feed], interest: Arc<Interest>, out: UnboundedSender<Event>, stop: Arc<AtomicBool>, rt: &tokio::runtime::Handle, rec: &Rec) -> anyhow::Result<Feeds> {
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
                        if out.send(Event::Tx(Arrival { feed: id, slot: d.slot, t_rx: d.t, t_decoded, executed: None, tx: d.tx, poh: None })).is_err() {
                            c.channel_drops.fetch_add(1, Ordering::Relaxed);
                        }
                    }
                });
                c.connected.store(false, Ordering::Relaxed);
                if let Err(e) = res { c.errors.fetch_add(1, Ordering::Relaxed); let _ = out.send(Event::Status { feed: id, msg: format!("{name}: receive failed: {e}") }); }
            })?;
        } else {
            let (f, interest, out, stop, c, rec) = (f.clone(), interest.clone(), out.clone(), stop.clone(), c.clone(), rec.clone());
            rt.spawn(async move {
                let mut backoff = 500u64;
                while !stop.load(Ordering::Relaxed) {
                    let clock = std::sync::Mutex::new(entries::PohClock::default());
                    let sink = |it: grpc::Item| -> bool { forward(id, &interest, &out, &c, Some(&clock), &rec, it) };
                    let started = now_ns();
                    let res = grpc::feed_once(&f, &sink, &rec).await;
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
/// here too
fn forward(id: u16, interest: &Interest, out: &UnboundedSender<Event>, c: &FeedCounters, poh: Option<&std::sync::Mutex<entries::PohClock>>, rec: &Rec, it: grpc::Item) -> bool {
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
            let pohs = match poh {
                Some(p) => {
                    let (pohs, done) = p.lock().unwrap().entries_at(slot, &ents, t);
                    if let Some(d) = done {
                        // slots-feed.log v2: the eight v1 columns; the shred columns are `-` for an entries feed, and
                        // poh_complete is whether the slot was followed from its start with all 64 ticks
                        rec.emit(rec::SLOTS_FEED, Record::enc(move |o| { let _ = std::io::Write::write_fmt(o, format_args!("{id} {} {} {} {} {} {} {} - - - - {}",
                            d.slot, d.ticks, d.entries, d.txs, d.t_first, d.t_last, d.valid as u8, (d.valid && d.ticks == 64) as u8)); }));
                    }
                    pohs
                }
                None => vec![None; ents.len()],
            };
            // poh.log v2: `sig8 slot ms feed entry_idx` (`-`: an entry's index in its slot is not known to an entries
            // feed). One record for the message's lines (review F11: one queue slot, formatted on the writer)
            if rec.is_on() {
                let lines: Vec<(u64, f64)> = refs.iter().filter(|r| !r.is_vote).filter_map(|r| {
                    let ms = pohs.get(r.entry as usize).copied().flatten().and_then(|p| p.ms())?;
                    Some((u64::from_be_bytes(r.sig[..8].try_into().unwrap()), ms))
                }).collect();
                if !lines.is_empty() {
                    rec.emit(rec::POH, Record::enc_lines(lines.len() as u32, move |o| {
                        for (k, (sig8, ms)) in lines.iter().enumerate() {
                            if k > 0 { o.push(b'\n'); }
                            let _ = std::io::Write::write_fmt(o, format_args!("{sig8:016x} {slot} {ms:.3} {id} -"));
                        }
                    }));
                }
            }
            let t_decoded = now_ns();
            let tables = interest.tables.read().unwrap();
            let (key, table) = (|k: &Pk| interest.keys.contains(k), |k: &Pk| tables.contains(k));
            let mut ok = true;
            for r in refs {
                if r.is_vote { continue; }
                c.txs.fetch_add(1, Ordering::Relaxed);
                let raw = &bytes[r.start..r.end];
                if !tx::scan(raw, &key, &table).map_or(false, |s| s.hit) { continue; }
                let Some((tx, _)) = tx::parse_wire(raw) else { continue };
                c.forwarded.fetch_add(1, Ordering::Relaxed);
                let poh = pohs.get(r.entry as usize).copied().flatten();
                if !sent(c, out.send(Event::Tx(Arrival { feed: id, slot, t_rx: t, t_decoded, executed: None, tx, poh })).is_ok()) { ok = false; break; }
            }
            drop(tables);
            archive(bytes);
            ok
        }
        grpc::Item::Tx { slot, tx, t, executed } => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            c.txs.fetch_add(1, Ordering::Relaxed);
            c.seen(slot, t);
            if !interest.wants(&tx) { return true; }
            c.forwarded.fetch_add(1, Ordering::Relaxed);
            sent(c, out.send(Event::Tx(Arrival { feed: id, slot, t_rx: t, t_decoded: t, executed, tx, poh: None })).is_ok())
        }
        grpc::Item::Account { slot, pubkey, lamports, owner, data, t, txn, .. } => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            c.seen(slot, t);
            sent(c, out.send(Event::Account { slot, pubkey, owner, lamports, data, t, txn }).is_ok())
        }
        grpc::Item::Slot { slot, status, t } => {
            c.packets.fetch_add(1, Ordering::Relaxed);
            c.seen(slot, t);
            sent(c, out.send(Event::Slot { slot, status, t }).is_ok())
        }
    }
}

/// Start the pool-state stream (accounts + slots) on `rt` (the hot runtime). The engine changes the followed accounts
/// through `list`. `c`: its counters (feedhealth.jsonl feed `state`)
#[allow(clippy::too_many_arguments)]
pub fn start_state(url: String, token: Option<String>, list: tokio::sync::watch::Receiver<Vec<String>>, out: UnboundedSender<Event>, stop: Arc<AtomicBool>,
    rt: &tokio::runtime::Handle, c: Arc<FeedCounters>) {
    rt.spawn(async move {
        let mut backoff = 500u64;
        let interest = Interest::default();
        let rec = Rec::off();
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
                forward(u16::MAX, &interest, &out, &c, None, &rec, it)
            };
            let res = grpc::accounts_once(&url, token.as_deref(), list.clone(), &sink).await;
            c.connected.store(false, Ordering::Relaxed);
            if stop.load(Ordering::Relaxed) { break; }
            c.reconnects.fetch_add(1, Ordering::Relaxed);
            let msg = match res { Ok(()) => "stream closed".to_string(), Err(e) => { c.errors.fetch_add(1, Ordering::Relaxed); format!("{e:#}") } };
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

    /// review F12: what an entries feed records through the recorder: poh.log v2 (`sig8 slot ms feed -`, one record per
    /// message, a line per transaction), slots-feed.log v2 (the eight v1 columns, four `-` shred columns, poh_complete)
    /// and the raw archive in its v1 frame layout (`u64 slot | u64 t | u32 len | bytes`)
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
        assert!(forward(0, &interest, &tx, &c, Some(&clock), &rec, grpc::Item::Entries { slot: 10, bytes: m10.clone(), t: 1_000 }));
        assert!(forward(0, &interest, &tx, &c, Some(&clock), &rec, grpc::Item::Entries { slot: 11, bytes: m11.clone(), t: 2_000 }));
        rec.close();
        assert_eq!(rec::read_text(&d, "poh").unwrap(), vec!["2222222222222222 11 9.375 0 -", "3333333333333333 11 9.375 0 -"]);
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
}

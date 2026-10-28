//! OBSERVATORY (dip24; owner request 10-29 ~01:50 PKT; ops/obs/OBSERVATORY.md): zero-cost, LOG-ONLY shadow modules that record,
//! during a live run, what our candidate strategies would have met, against what really unfolded. Nothing here sends, signs, reads
//! an RPC or changes a live decision; every module is off unless its flag is given (--observatory turns on all of them).
//!   * THE LIVE SIDE (`Feeder`, called by the dip event loop AFTER all of its own work on a tx): one small message per executed pump
//!     tx (its ExecInfo is shared by an Arc clone, never copied) into a BOUNDED channel with `try_send`: when it is full the message is
//!     dropped and counted, the event loop never waits. Two rare extras: an executed tx without pump events that names the PumpSwap
//!     program (migrations / pool trades), and a FAILED tx of a watched wallet (both only when their module is on).
//!   * THE OBSERVATORY THREAD (its own, lowest CPU priority): the shared token book (book.rs), the modules, the `.obs.jsonl` writer
//!     (buffered; rotated to .obs.jsonl.1, .2, ... every 6 h or 1 GB, never deleted), and a TAILER of the run's own --dip-log (the
//!     live pre-send records: attempts, arms, fills, exits, sell landings, closes) so nothing in the live code has to call it.
//!   * Modules: 1 REARM (rearm.rs), 2 HOLD tape of live pre-send fills (hold.rs), 3 WATCH list (watch.rs), 4 MIGRATION (migr.rs),
//!     5 BLINK causal launch-dump trigger (blink.rs), 7 BACKRUN census (backrun.rs). Records: one JSON object per line, "ev" names
//!     the module (rearm_*, hold_*, watch_*, mig_*, blink_*, backrun_*, obs_*).
//!   * Status: the observatory publishes counters in atomics (`Ctr`); the engine's 60 s status line reads them (no lock); an
//!     obs_status record every 60 s and an obs_summary record every 10 min go into the obs file.
pub mod backrun;
pub mod blink;
pub mod book;
pub mod hold;
pub mod inslot;
pub mod migr;
pub mod race;
pub mod rearm;
pub mod select;
pub mod watch;
#[cfg(test)]
mod tests;

use crate::feeds::{Arrival, ExecInfo};
use crate::tx::Pk;
use book::{Book, Tr};
use rustc_hash::{FxHashMap, FxHashSet};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::io::{BufRead, Read, Seek, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

/// the System program (tips are top-level System transfers)
const SYSTEM: Pk = [0u8; 32];

/// module ids (record counters per module)
pub const M_CORE: usize = 0;
pub const M_REARM: usize = 1;
pub const M_HOLD: usize = 2;
pub const M_WATCH: usize = 3;
pub const M_MIGR: usize = 4;
pub const M_BLINK: usize = 5;
pub const M_BACKRUN: usize = 6;
pub const M_SELECT: usize = 7;
pub const M_RACE: usize = 8;
pub const M_INSLOT: usize = 9;
pub const NM: usize = 10;
pub const MOD_NAMES: [&str; NM] = ["core", "rearm", "hold", "watch", "migration", "blink", "backrun", "select", "race", "inslot"];

/// the channel's capacity (messages; ~170 bytes each)
pub const CHAN: usize = 1 << 16;
/// rotation: every 6 h or 1 GB of the current part
pub const ROTATE_NS: u64 = 6 * 3600 * 1_000_000_000;
pub const ROTATE_BYTES: u64 = 1 << 30;

/// the observatory's configuration (from the engine's flags; pure: unit-tested)
#[derive(Clone, Debug, Default)]
pub struct Cfg {
    pub rearm: bool, pub hold: bool, pub migr: bool, pub blink: bool, pub backrun: bool, pub select: bool,
    /// module 9 (feed race) and the engine's feed names (index = Arrival.feed)
    pub race: bool, pub feed_names: Vec<String>,
    /// module 10 (INSLOT paper of 8yYMhu's same-slot backrun)
    pub inslot: bool,
    /// the watch list (empty: the watch module off); its file
    pub watch: Vec<Pk>, pub watch_file: Option<String>, pub watch_names: FxHashMap<Pk, String>,
    /// the obs file (current part)
    pub out: PathBuf,
    /// the run's --dip-log, tailed for the live pre-send records (None: no tailer; the hold module then has nothing to do)
    pub tail: Option<PathBuf>,
    /// our wallet
    pub user: Pk,
    /// pre-send live: attempts per second (the global / path cap: the shared helius-ps budget), attempts per slot, the limit drop
    pub rate_cap: u64, pub k: u64, pub drop: f64,
    /// QUIET signals for the re-arm's remaining holders: the cohort (--dip-cohort), the follower bots (--presend-live-fbots), the
    /// whale-dump history file (--presend-live-quiet-book) and the followers threshold
    pub cohort: FxHashSet<Pk>, pub fbots: FxHashSet<Pk>, pub quiet_book: Option<PathBuf>, pub quiet_fol: f64,
    pub chan: usize, pub rotate_ns: u64, pub rotate_bytes: u64,
}

impl Cfg {
    pub fn any(&self) -> bool { self.rearm || self.hold || !self.watch.is_empty() || self.migr || self.blink || self.backrun || self.select || self.race || self.inslot }
    pub fn json(&self) -> Value {
        json!({"rearm": self.rearm, "hold": self.hold, "watch": self.watch.len(), "watch_file": self.watch_file, "migration": self.migr, "blink": self.blink,
               "backrun": self.backrun, "select": self.select, "race": self.race, "inslot": self.inslot, "feeds": self.feed_names, "file": self.out.display().to_string(), "tail": self.tail.as_ref().map(|p| p.display().to_string()), "rate_cap": self.rate_cap,
               "k": self.k, "drop": self.drop, "quiet_book": self.quiet_book.as_ref().map(|p| p.display().to_string()), "cohort": self.cohort.len(), "fbots": self.fbots.len(),
               "chan": self.chan, "rotate_h": self.rotate_ns as f64 / 3.6e12, "rotate_mb": self.rotate_bytes >> 20})
    }
    /// the module names on
    pub fn names(&self) -> Vec<&'static str> {
        let mut v = Vec::new();
        if self.rearm { v.push("rearm"); }
        if self.hold { v.push("hold"); }
        if !self.watch.is_empty() { v.push("watch"); }
        if self.migr { v.push("migration"); }
        if self.blink { v.push("blink"); }
        if self.backrun { v.push("backrun"); }
        if self.select { v.push("select"); }
        if self.race { v.push("feedrace"); }
        if self.inslot { v.push("inslot"); }
        v
    }
}

/// the default obs file of a run: <dip-log stem>.obs.jsonl (/root/prod/runs/dip_ams_r35.jsonl -> /root/prod/runs/dip_ams_r35.obs.jsonl)
pub fn obs_path_for(dip_log: &str) -> PathBuf {
    let p = Path::new(dip_log);
    let stem = p.file_stem().and_then(|s| s.to_str()).unwrap_or("run");
    let stem = stem.strip_suffix(".jsonl").unwrap_or(stem);
    p.with_file_name(format!("{stem}.obs.jsonl"))
}

/// a watch list file: one wallet per line, '#' starts a comment (the rest of the line is the wallet's name in the records)
pub fn load_watch(path: &str) -> Result<(Vec<Pk>, FxHashMap<Pk, String>), String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("--obs-watch {path}: {e}"))?;
    let (mut v, mut names) = (Vec::new(), FxHashMap::default());
    for (n, l) in text.lines().enumerate() {
        let (a, c) = match l.split_once('#') { Some((a, c)) => (a.trim(), c.trim()), None => (l.trim(), "") };
        if a.is_empty() { continue; }
        let k: Pk = bs58::decode(a).into_vec().ok().and_then(|x| <[u8; 32]>::try_from(x).ok()).ok_or_else(|| format!("--obs-watch {path} line {}: '{a}' is not a wallet", n + 1))?;
        if !names.contains_key(&k) { v.push(k); }
        names.insert(k, c.chars().take(80).collect());
    }
    Ok((v, names))
}

// ---- the live side ------------------------------------------------------------------------------------------------------

/// one executed pump tx (its events shared, not copied)
pub struct TxIn {
    pub slot: u64, pub idx: u64, pub t_rx: u64, pub sig: [u8; 64], pub exec: Arc<ExecInfo>, pub cu_price: Option<u64>, pub cu_limit: Option<u32>, pub v1: bool, pub payer: Pk,
    /// a watched wallet's tx: its top-level System transfers (to, lamports): the tips
    pub xfers: Option<Box<Vec<(Pk, u64)>>>,
}
/// an executed tx without pump events naming PumpSwap (migration / pool txs): its static keys (+ feed-resolved ones)
pub struct RawIn { pub slot: u64, pub t_rx: u64, pub sig: [u8; 64], pub keys: Vec<Pk>, pub payer: Pk }
/// a watched wallet's FAILED tx (the feed carries failed txs): what the tx says (its block index and error are not kept by the feed)
pub struct FailIn { pub slot: u64, pub t_rx: u64, pub sig: [u8; 64], pub payer: Pk, pub cu_price: Option<u64>, pub cu_limit: Option<u32>, pub v1: bool, pub xfers: Vec<(Pk, u64)>,
                    pub pump_ix: Option<(u64, Option<Pk>)> }

pub enum Msg { Tx(TxIn), Raw(Box<RawIn>), Fail(Box<FailIn>), Arr { k8: u64, feed: u16, t: u64, slot: u64 }, Stop }

/// counters shared between the two sides (lock-free; the live side only adds / reads)
#[derive(Default)]
pub struct Ctr {
    pub sent: AtomicU64, pub drops: AtomicU64, pub raw: AtomicU64, pub fail: AtomicU64,
    // published by the observatory thread
    pub processed: AtomicU64, pub trades: AtomicU64, pub records: AtomicU64, pub bytes: AtomicU64, pub us_p99_x10: AtomicU64, pub mem_mb: AtomicU64,
    pub rearm_windows: AtomicU64, pub rearm_fills: AtomicU64, pub hold_tapes: AtomicU64, pub watch: AtomicU64, pub mig: AtomicU64, pub blink: AtomicU64, pub backrun: AtomicU64, pub select: AtomicU64, pub race: AtomicU64, pub inslot: AtomicU64,
    pub tail_lines: AtomicU64, pub write_err: AtomicU64, pub parts: AtomicU64,
}

/// the event loop's handle (cheap to call; never blocks)
pub struct Feeder { tx: crossbeam_channel::Sender<Msg>, pub ctr: Arc<Ctr>, watch: Arc<FxHashSet<Pk>>, raw: bool, fail: bool, pumpswap: Pk, race: bool }

impl Feeder {
    /// an executed pump tx with events (after the engine's own work on it)
    #[inline]
    pub fn exec(&self, a: &Arrival, x: &Arc<ExecInfo>) {
        let payer = a.tx.keys.first().copied().unwrap_or([0; 32]);
        let xfers = if !self.watch.is_empty() && (self.watch.contains(&payer) || x.trades.iter().any(|e| self.watch.contains(&e.user))) {
            Some(Box::new(transfers(&a.tx)))
        } else { None };
        let m = Msg::Tx(TxIn { slot: a.slot, idx: x.index, t_rx: a.t_rx, sig: a.tx.sig, exec: x.clone(), cu_price: a.tx.cu_price_micro, cu_limit: a.tx.cu_limit, v1: a.tx.v1, payer, xfers });
        self.put(m);
    }
    /// any other arrival (no pump events / not ok): a migration or pool tx (PumpSwap named, executed ok), a watched wallet's failed tx
    #[inline]
    pub fn arrival(&self, a: &Arrival) {
        match a.executed {
            Some(true) if self.raw && a.exec.is_none() => {
                if a.tx.keys.iter().any(|k| *k == self.pumpswap) {
                    let mut keys = a.tx.keys.clone();
                    if let Some((w, r)) = &a.tx.loaded { keys.extend_from_slice(w); keys.extend_from_slice(r); }
                    self.ctr.raw.fetch_add(1, Ordering::Relaxed);
                    self.put(Msg::Raw(Box::new(RawIn { slot: a.slot, t_rx: a.t_rx, sig: a.tx.sig, payer: a.tx.keys.first().copied().unwrap_or([0; 32]), keys })));
                }
            }
            Some(false) if self.fail => {
                if let Some(p) = a.tx.keys.first().filter(|p| self.watch.contains(*p)) {
                    self.ctr.fail.fetch_add(1, Ordering::Relaxed);
                    self.put(Msg::Fail(Box::new(FailIn { slot: a.slot, t_rx: a.t_rx, sig: a.tx.sig, payer: *p, cu_price: a.tx.cu_price_micro, cu_limit: a.tx.cu_limit, v1: a.tx.v1,
                        xfers: transfers(&a.tx), pump_ix: pump_ix(&a.tx) })));
                }
            }
            _ => {}
        }
    }
    /// module 9: every arrival from every feed (sig8, feed, t_rx, slot); nothing without --obs-feedrace
    #[inline]
    pub fn any(&self, a: &Arrival) {
        if !self.race { return; }
        self.put(Msg::Arr { k8: u64::from_be_bytes(a.tx.sig[..8].try_into().unwrap()), feed: a.feed, t: a.t_rx, slot: a.slot });
    }
    #[inline]
    fn put(&self, m: Msg) {
        match self.tx.try_send(m) {
            Ok(()) => { self.ctr.sent.fetch_add(1, Ordering::Relaxed); }
            Err(crossbeam_channel::TrySendError::Full(_)) => { self.ctr.drops.fetch_add(1, Ordering::Relaxed); }
            Err(crossbeam_channel::TrySendError::Disconnected(_)) => {}
        }
    }
    /// messages waiting
    pub fn queued(&self) -> usize { self.tx.len() }
    /// the engine's status-line part (atomics only)
    pub fn line(&self) -> String {
        let c = &self.ctr;
        let g = |a: &AtomicU64| a.load(Ordering::Relaxed);
        format!(" | OBS: sent {} dropped {} queued {} done {} | rearm windows {} fills {} | hold {} | watch {} | mig {} | blink {} | backrun {} | select {} | race {} | inslot {} | {} records {:.1} MB in {} part(s), p99 {:.1} us/msg, ~{} MB{}",
            g(&c.sent), g(&c.drops), self.queued(), g(&c.processed), g(&c.rearm_windows), g(&c.rearm_fills), g(&c.hold_tapes), g(&c.watch), g(&c.mig), g(&c.blink), g(&c.backrun), g(&c.select), g(&c.race), g(&c.inslot),
            g(&c.records), g(&c.bytes) as f64 / 1e6, g(&c.parts), g(&c.us_p99_x10) as f64 / 10.0, g(&c.mem_mb), if g(&c.write_err) > 0 { format!(" | WRITE ERRORS {}", g(&c.write_err)) } else { String::new() })
    }
}

/// a tx's top-level System transfers (to, lamports): tips (System program, instruction 2 = transfer, lamports u64 LE at 4..12)
pub fn transfers(tx: &crate::tx::Tx) -> Vec<(Pk, u64)> {
    let mut v = Vec::new();
    for ix in &tx.ixs {
        if tx.keys.get(ix.program as usize) != Some(&SYSTEM) || ix.data.len() < 12 || ix.data[..4] != [2, 0, 0, 0] { continue; }
        let to = ix.accounts.get(1).and_then(|&i| crate::dip::account_at(tx, i as usize));
        if let Some(to) = to { v.push((to, u64::from_le_bytes(ix.data[4..12].try_into().unwrap()))); }
    }
    v
}

/// a failed tx's first pump instruction: (its 8-byte discriminator as a u64, the mint guess = its account 2: global, fee recipient,
/// MINT, bonding curve ... in pump's buy / sell layouts)
pub fn pump_ix(tx: &crate::tx::Tx) -> Option<(u64, Option<Pk>)> {
    let pump = *crate::snipe::PUMP;
    let ix = tx.ixs.iter().find(|ix| tx.keys.get(ix.program as usize) == Some(&pump) && ix.data.len() >= 8)?;
    let d = u64::from_le_bytes(ix.data[..8].try_into().unwrap());
    Some((d, ix.accounts.get(2).and_then(|&i| crate::dip::account_at(tx, i as usize))))
}

/// the observatory: its feeder (for the event loop) and its thread
pub struct Obs { pub feeder: Feeder, thread: Option<std::thread::JoinHandle<Value>>, pub cfg_json: Value }

impl Obs {
    /// start the thread (the file is opened there; a failure to open it is reported in its records / counters, never fatal)
    pub fn start(cfg: Cfg) -> Result<Obs, String> {
        if let Some(d) = cfg.out.parent() { if !d.as_os_str().is_empty() && !d.is_dir() { return Err(format!("obs file {}: no such directory", cfg.out.display())); } }
        let cap = if cfg.chan == 0 { CHAN } else { cfg.chan };
        let (tx, rx) = crossbeam_channel::bounded(cap);
        let ctr = Arc::new(Ctr::default());
        let watch: Arc<FxHashSet<Pk>> = Arc::new(cfg.watch.iter().copied().collect());
        let feeder = Feeder { tx, ctr: ctr.clone(), watch: watch.clone(), raw: cfg.migr, fail: !cfg.watch.is_empty(), pumpswap: *crate::venues::PUMPSWAP, race: cfg.race };
        let cfg_json = cfg.json();
        let thread = std::thread::Builder::new().name("obs".into()).spawn(move || {
            // the lowest CPU priority: the live threads always win
            unsafe {
                let tid = libc::syscall(libc::SYS_gettid);
                libc::setpriority(libc::PRIO_PROCESS, tid as libc::id_t, 19);
                libc::syscall(libc::SYS_ioprio_set, 1, tid, 3 << 13);
            }
            let mut h = Hub::new(cfg, ctr, watch);
            h.run(rx)
        }).map_err(|e| format!("obs thread: {e}"))?;
        Ok(Obs { feeder, thread: Some(thread), cfg_json })
    }
    /// the run's end: the thread drains what is queued, writes its last records (summary, open windows), flushes, exits (waited
    /// for up to `wait`). -> its totals for run_end
    pub fn finish(&mut self, wait: Duration) -> Value {
        let _ = self.feeder.tx.send_timeout(Msg::Stop, wait);
        let Some(h) = self.thread.take() else { return Value::Null };
        let t = Instant::now();
        while !h.is_finished() && t.elapsed() < wait { std::thread::sleep(Duration::from_millis(5)); }
        if h.is_finished() { h.join().unwrap_or(Value::Null) } else { json!({"error": "the observatory thread did not finish in time (its last records may be missing)"}) }
    }
}

// ---- the writer ------------------------------------------------------------------------------------------------------------

/// the obs file: buffered, rotated (the current part renamed to <file>.N, N = the next free number, so .1 is the oldest), never deleted
pub struct Out {
    path: PathBuf, f: Option<std::io::BufWriter<std::fs::File>>, part: u64, part_bytes: u64, part_t0: Instant, rotate_ns: u64, rotate_bytes: u64,
    pub recs: [u64; NM], pub bytes: [u64; NM], pub errors: u64, pub total_bytes: u64, last_flush: Instant, pub err: Option<String>,
}

impl Out {
    pub fn open(path: PathBuf, rotate_ns: u64, rotate_bytes: u64) -> Out {
        let mut o = Out { path, f: None, part: 0, part_bytes: 0, part_t0: Instant::now(), rotate_ns, rotate_bytes, recs: [0; NM], bytes: [0; NM], errors: 0, total_bytes: 0,
            last_flush: Instant::now(), err: None };
        o.reopen();
        o
    }
    fn reopen(&mut self) {
        match std::fs::OpenOptions::new().create(true).append(true).open(&self.path) {
            Ok(f) => { self.part_bytes = f.metadata().map(|m| m.len()).unwrap_or(0); self.f = Some(std::io::BufWriter::with_capacity(1 << 16, f)); self.part_t0 = Instant::now(); }
            Err(e) => { self.errors += 1; self.err = Some(format!("{}: {e}", self.path.display())); self.f = None; }
        }
    }
    /// the next free part number (<file>.1, .2, ...)
    fn next_part(&self) -> u64 {
        let mut n = 1;
        loop { let p = PathBuf::from(format!("{}.{n}", self.path.display())); if !p.exists() { return n; } n += 1; }
    }
    pub fn write(&mut self, m: usize, v: &Value) {
        let mut s = v.to_string();
        s.push('\n');
        let n = s.len() as u64;
        if let Some(f) = self.f.as_mut() {
            if f.write_all(s.as_bytes()).is_err() { self.errors += 1; return; }
        } else { self.errors += 1; return; }
        self.recs[m.min(NM - 1)] += 1; self.bytes[m.min(NM - 1)] += n; self.part_bytes += n; self.total_bytes += n;
    }
    /// flush every second; rotate when the part is old or big enough. -> Some(part number) when it rotated
    pub fn maybe(&mut self) -> Option<u64> {
        if self.last_flush.elapsed() >= Duration::from_secs(1) { self.flush(); }
        if self.f.is_some() && (self.part_bytes >= self.rotate_bytes || self.part_t0.elapsed() >= Duration::from_nanos(self.rotate_ns)) { return self.rotate(); }
        if self.f.is_none() && self.last_flush.elapsed() >= Duration::from_secs(1) { self.reopen(); }
        None
    }
    pub fn flush(&mut self) { self.last_flush = Instant::now(); if let Some(f) = self.f.as_mut() { if f.flush().is_err() { self.errors += 1; } } }
    pub fn rotate(&mut self) -> Option<u64> {
        self.flush();
        let n = self.next_part();
        self.f = None;
        let to = PathBuf::from(format!("{}.{n}", self.path.display()));
        if std::fs::rename(&self.path, &to).is_err() { self.errors += 1; }
        self.part = n;
        self.reopen();
        Some(n)
    }
    pub fn parts(&self) -> u64 { self.part + 1 }
}

// ---- the tailer of the run's own log (the live pre-send records) ---------------------------------------------------------

/// the live engine's pre-send records the modules read (from the --dip-log as it is written)
#[derive(Clone, Debug)]
pub enum LiveEv {
    /// an attempt sent (its send time, path)
    Attempt { t: u64, path: String },
    Arm { w: u64, mint: Pk, t: u64, slot: u64 },
    Disarm { w: u64, mint: Pk, t: u64, why: String },
    Fill { w: u64, mint: Pk, sig: String, slot: u64, idx: u64, t: u64, tokens: u64, sol_in: u64, rec: Value },
    Exit { mint: Pk, why: String, slot: u64, t: u64, value: Option<f64>, round: u64 },
    SellLand { mint: Pk, sig: String, slot: u64, idx: u64, t: u64, sol: u64 },
    Close { mint: Pk, rec: Value },
}

pub struct Tailer { path: PathBuf, pos: u64, buf: Vec<u8>, pub lines: u64, pub parsed: u64, pub bad: u64, last: Instant }

impl Tailer {
    /// from the file's current end (the run's own records come after it)
    pub fn new(path: PathBuf) -> Tailer {
        let pos = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
        Tailer { path, pos, buf: Vec::new(), lines: 0, parsed: 0, bad: 0, last: Instant::now() - Duration::from_secs(1) }
    }
    /// from a given offset (tests / replays)
    pub fn at(path: PathBuf, pos: u64) -> Tailer { Tailer { path, pos, buf: Vec::new(), lines: 0, parsed: 0, bad: 0, last: Instant::now() - Duration::from_secs(1) } }
    /// read what was appended (at most every 50 ms, at most 8 MB per call)
    pub fn poll(&mut self, out: &mut Vec<LiveEv>, force: bool) {
        if !force && self.last.elapsed() < Duration::from_millis(50) { return; }
        self.last = Instant::now();
        let Ok(mut f) = std::fs::File::open(&self.path) else { return };
        let len = f.metadata().map(|m| m.len()).unwrap_or(0);
        if len < self.pos { self.pos = 0; self.buf.clear(); }   // the file was replaced: from its start
        if len == self.pos { return; }
        if f.seek(std::io::SeekFrom::Start(self.pos)).is_err() { return; }
        let want = (len - self.pos).min(8 << 20) as usize;
        let mut chunk = vec![0u8; want];
        let Ok(n) = f.read(&mut chunk) else { return };
        chunk.truncate(n);
        self.pos += n as u64;
        self.buf.extend_from_slice(&chunk);
        let mut start = 0;
        while let Some(k) = self.buf[start..].iter().position(|&b| b == b'\n') {
            let line = &self.buf[start..start + k];
            start += k + 1;
            self.lines += 1;
            if let Some(ev) = parse_live(line) { self.parsed += 1; out.push(ev); }
        }
        self.buf.drain(..start);
        if self.buf.len() > 4 << 20 { self.bad += 1; self.buf.clear(); }
    }
}

fn find(h: &[u8], n: &[u8]) -> bool { h.windows(n.len()).any(|w| w == n) }

/// one --dip-log line -> a live event (None: not one the modules read)
pub fn parse_live(line: &[u8]) -> Option<LiveEv> {
    // cheap pre-filter: only pre-send records
    if !find(line, b"\"presend_") { return None; }
    let kind = if find(line, b"\"ev\":\"presend_attempt\"") { 1 } else if find(line, b"\"ev\":\"presend_live_arm\"") { 2 } else if find(line, b"\"ev\":\"presend_live_disarm\"") { 3 }
        else if find(line, b"\"ev\":\"presend_live_fill\"") { 4 } else if find(line, b"\"ev\":\"presend_live_exit\"") { 5 } else if find(line, b"\"ev\":\"presend_live_sell_land\"") { 6 }
        else if find(line, b"\"ev\":\"presend_live_close\"") { 7 } else { return None };
    let v: Value = serde_json::from_slice(line).ok()?;
    let pk = |x: &Value| -> Option<Pk> { bs58::decode(x.as_str()?).into_vec().ok().and_then(|b| <[u8; 32]>::try_from(b).ok()) };
    let u = |k: &str| v[k].as_u64().unwrap_or(0);
    Some(match kind {
        1 => LiveEv::Attempt { t: u("t"), path: v["path"].as_str().unwrap_or("").to_string() },
        2 => LiveEv::Arm { w: u("w"), mint: pk(&v["trig"]["mint"])?, t: v["trig"]["t"].as_u64().unwrap_or(0), slot: v["trig"]["slot"].as_u64().unwrap_or(0) },
        3 => LiveEv::Disarm { w: u("w"), mint: pk(&v["mint"])?, t: u("t"), why: v["why"].as_str().unwrap_or("").to_string() },
        4 => LiveEv::Fill { w: u("w"), mint: pk(&v["mint"])?, sig: v["sig"].as_str().unwrap_or("").to_string(), slot: u("slot"), idx: u("idx"), t: u("t"), tokens: u("tokens"),
                            sol_in: u("sol_in"), rec: v.clone() },
        5 => LiveEv::Exit { mint: pk(&v["mint"])?, why: v["why"].as_str().unwrap_or("").to_string(), slot: u("slot"), t: u("t"), value: v["value"].as_f64(), round: u("round") },
        6 => LiveEv::SellLand { mint: pk(&v["mint"])?, sig: v["sig"].as_str().unwrap_or("").to_string(), slot: u("slot"), idx: u("idx"), t: u("t"), sol: u("sol") },
        _ => LiveEv::Close { mint: pk(&v["mint"])?, rec: v },
    })
}

/// the live pre-send state the modules read (built from the tailed records)
#[derive(Default)]
pub struct Live {
    /// attempts sent per second (unix s -> count), the last 30 min
    pub per_sec: FxHashMap<u64, u32>, sec_q: VecDeque<u64>,
    /// armed live windows: w -> (mint, armed at t_rx)
    pub armed: FxHashMap<u64, (Pk, u64)>,
    /// every live arm of the last 10 min: (mint, t) (the re-arm's "taken over" check, applied after the fact)
    pub arms: VecDeque<(Pk, u64)>,
    /// live pre-send positions open: mint -> filled at t
    pub pos: FxHashMap<Pk, u64>,
    /// closed positions of the last 10 min: (mint, filled t, closed at the data clock)
    pub closed: VecDeque<(Pk, u64, u64)>,
    pub attempts: u64, pub fills: u64,
}

impl Live {
    pub fn on(&mut self, e: &LiveEv, now: u64) {
        match e {
            LiveEv::Attempt { t, .. } => {
                let s = t / 1_000_000_000;
                let c = self.per_sec.entry(s).or_insert(0);
                if *c == 0 { self.sec_q.push_back(s); }
                *c += 1; self.attempts += 1;
                while self.sec_q.front().is_some_and(|&x| x + 1800 < s) { let x = self.sec_q.pop_front().unwrap(); self.per_sec.remove(&x); }
            }
            LiveEv::Arm { w, mint, t, .. } => { self.armed.insert(*w, (*mint, *t)); self.arms.push_back((*mint, *t)); while self.arms.front().is_some_and(|x| x.1 + 600_000_000_000 < *t) { self.arms.pop_front(); } }
            LiveEv::Disarm { w, .. } => { self.armed.remove(w); }
            LiveEv::Fill { mint, t, .. } => { self.pos.entry(*mint).or_insert(*t); self.fills += 1; }
            LiveEv::Close { mint, .. } => {
                if let Some(t0) = self.pos.remove(mint) { self.closed.push_back((*mint, t0, now)); }
                while self.closed.front().is_some_and(|x| x.2 + 600_000_000_000 < now) { self.closed.pop_front(); }
            }
            _ => {}
        }
        if self.armed.len() > 10_000 { self.armed.clear(); }
        if self.pos.len() > 10_000 { self.pos.clear(); }
    }
    /// live attempts sent in the unix second `s`
    pub fn sent_in(&self, s: u64) -> u32 { self.per_sec.get(&s).copied().unwrap_or(0) }
    /// a live window armed on `mint` at a time in [lo, hi]
    pub fn armed_between(&self, mint: &Pk, lo: u64, hi: u64) -> Option<u64> { self.arms.iter().find(|(m, t)| m == mint && *t >= lo && *t <= hi).map(|x| x.1) }
    /// a live window armed on `mint` right now
    pub fn armed_now(&self, mint: &Pk) -> bool { self.armed.values().any(|(m, _)| m == mint) }
    /// a live pre-send position open at time t (any token)
    pub fn pos_open_at(&self, t: u64) -> bool { self.pos.values().any(|&t0| t0 <= t) || self.closed.iter().any(|x| x.1 <= t && t <= x.2) }
}

// ---- the slot clock ---------------------------------------------------------------------------------------------------------

/// the feed's slot clock as the observatory sees it (arrival order): the newest slot and the time each slot was first seen
#[derive(Default)]
pub struct Clock { pub cur: u64, first: VecDeque<(u64, u64)>, pub max_t: u64 }
impl Clock {
    /// a tx of `slot` at `t`: Some(previous slot) when the clock moved
    pub fn see(&mut self, slot: u64, t: u64) -> Option<u64> {
        self.max_t = self.max_t.max(t);
        if slot <= self.cur { return None; }
        let prev = self.cur;
        self.cur = slot;
        self.first.push_back((slot, t));
        while self.first.len() > 4096 { self.first.pop_front(); }
        Some(prev)
    }
    /// when the clock first reached a slot >= s (None: not yet / too old)
    pub fn reached(&self, s: u64) -> Option<u64> { self.first.iter().find(|x| x.0 >= s).map(|x| x.1) }
}

// ---- the observatory thread ------------------------------------------------------------------------------------------------

/// per-message processing time (µs) of the last 65536 messages, per-trade too
#[derive(Default)]
pub struct Timing { v: Vec<f32>, i: usize, pub n: u64, pub max: f64, pub trades: u64, pub sum: f64, pt: Vec<f32>, pi: usize, pub pt_max: f64,
    /// the slowest messages (us, what, slot) and messages over 1 ms
    pub slow: Vec<(f64, String, u64)>, pub over1ms: u64 }
const TKEEP: usize = 1 << 16;
impl Timing {
    pub fn add(&mut self, us: f64, trades: usize) {
        if self.v.len() < TKEEP { self.v.push(us as f32); } else { self.v[self.i] = us as f32; self.i = (self.i + 1) % TKEEP; }
        self.n += 1; self.sum += us; self.max = self.max.max(us); self.trades += trades as u64;
        if trades > 0 {
            let p = us / trades as f64;
            if self.pt.len() < TKEEP { self.pt.push(p as f32); } else { self.pt[self.pi] = p as f32; self.pi = (self.pi + 1) % TKEEP; }
            self.pt_max = self.pt_max.max(p);
        }
    }
    fn q(v: &[f32], p: f64) -> f64 { let mut x = v.to_vec(); x.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal)); x.get(((x.len().max(1) - 1) as f64 * p).round() as usize).map(|&y| y as f64).unwrap_or(0.0) }
    pub fn pct(&self) -> (f64, f64) { (Self::q(&self.v, 0.5), Self::q(&self.v, 0.99)) }
    pub fn pct_trade(&self) -> (f64, f64) { (Self::q(&self.pt, 0.5), Self::q(&self.pt, 0.99)) }
    pub fn note_slow(&mut self, us: f64, what: String, slot: u64) {
        if us > 1000.0 { self.over1ms += 1; }
        if self.slow.len() < 8 || us > self.slow.last().map(|x| x.0).unwrap_or(0.0) {
            self.slow.push((us, what, slot));
            self.slow.sort_by(|a, b| b.0.partial_cmp(&a.0).unwrap_or(std::cmp::Ordering::Equal));
            self.slow.truncate(8);
        }
    }
    pub fn json(&self) -> Value {
        let (a, b) = self.pct(); let (c, d) = self.pct_trade();
        json!({"msgs": self.n, "trades": self.trades, "us_msg_p50": a, "us_msg_p99": b, "us_msg_max": self.max, "us_trade_p50": c, "us_trade_p99": d, "us_trade_max": self.pt_max,
               "us_mean_msg": self.sum / self.n.max(1) as f64, "over_1ms": self.over1ms,
               "slowest": self.slow.iter().map(|x| json!({"us": (x.0 * 10.0).round() / 10.0, "what": x.1, "slot": x.2})).collect::<Vec<_>>()})
    }
}

/// the modules and their shared state (the observatory thread owns all of it)
pub struct Hub {
    pub cfg: Cfg, pub ctr: Arc<Ctr>, pub watch: Arc<FxHashSet<Pk>>,
    pub book: Book, pub live: Live, pub clock: Clock, pub out: Out, pub tail: Option<Tailer>,
    pub qbook: Option<crate::presend_quiet::DumpBook>, pub qinfo: Value,
    pub rearm: Option<rearm::Rearm>, pub hold: Option<hold::Hold>, pub watchm: Option<watch::Watch>, pub migr: Option<migr::Migr>, pub blink: Option<blink::Blink>,
    pub backrun: Option<backrun::Backrun>, pub select: Option<select::Select>, pub race: Option<race::Race>, pub inslot: Option<inslot::Inslot>,
    pub recs: Vec<(usize, Value)>,
    pub tm: Timing,
    t_start: Instant, last_status: Instant, last_summary: Instant, pub msgs: u64, pub raw_n: u64, pub fail_n: u64, live_buf: Vec<LiveEv>,
    /// the data clock the last summary was taken at (records carry both)
    summaries: u64,
}

impl Hub {
    pub fn new(cfg: Cfg, ctr: Arc<Ctr>, watch: Arc<FxHashSet<Pk>>) -> Hub {
        let out = Out::open(cfg.out.clone(), if cfg.rotate_ns == 0 { ROTATE_NS } else { cfg.rotate_ns }, if cfg.rotate_bytes == 0 { ROTATE_BYTES } else { cfg.rotate_bytes });
        let tail = if cfg.hold || cfg.rearm { cfg.tail.clone().map(Tailer::new) } else { None };
        // the re-arm's QUIET signals: the whale-dump history (24 h), from the host's book when given (read here, on this thread)
        let (qbook, qinfo) = if cfg.rearm || cfg.select {
            let mut b = crate::presend_quiet::DumpBook::new(24 * 3_600_000_000_000);
            let info = match &cfg.quiet_book {
                Some(p) => {
                    let l = crate::presend_quiet::load_state(p, crate::feeds::clock::now_ns(), 24 * 3_600_000_000_000);
                    let dumps: Vec<crate::presend_quiet::JDump> = l.dumps.iter().map(|x| x.0).collect();
                    b.load_finalized(&dumps);
                    json!({"book": p.display().to_string(), "dumps": dumps.len(), "missing": l.missing, "err": l.err})
                }
                None => json!({"book": null, "note": "no --presend-live-quiet-book: the whale history starts empty (wh_fol -1 until it fills)"}),
            };
            (Some(b), info)
        } else { (None, Value::Null) };
        let user = cfg.user;
        let mut h = Hub {
            rearm: cfg.rearm.then(|| rearm::Rearm::new(&cfg)), hold: cfg.hold.then(hold::Hold::default), watchm: (!cfg.watch.is_empty()).then(|| watch::Watch::new(&cfg)),
            migr: cfg.migr.then(migr::Migr::default), blink: cfg.blink.then(blink::Blink::default), backrun: cfg.backrun.then(backrun::Backrun::default),
            select: cfg.select.then(|| select::Select::new(&cfg)), race: cfg.race.then(|| race::Race::new(cfg.feed_names.clone())), inslot: cfg.inslot.then(inslot::Inslot::new),
            cfg, ctr, watch, book: Book::new(user), live: Live::default(), clock: Clock::default(), out, tail, qbook, qinfo, recs: Vec::new(), tm: Timing::default(),
            t_start: Instant::now(), last_status: Instant::now(), last_summary: Instant::now(), msgs: 0, raw_n: 0, fail_n: 0, live_buf: Vec::new(), summaries: 0,
        };
        let mut start = json!({"ev": "obs_start", "t": crate::feeds::clock::now_ns(), "cfg": h.cfg.json(), "quiet": h.qinfo.clone(), "version": "dip24",
            "notes": {"clock": "t / t_rx = the executed feed's arrival time (unix ns, the engine's clock); slots from the feed",
                      "block_time": "not carried by the executed feed (its logs are not kept): slot first-seen times stand in"}});
        if let Some(e) = &h.out.err { start["open_error"] = e.clone().into(); }
        h.out.write(M_CORE, &start);
        h
    }

    /// the thread's loop: messages, the tailer, the modules' timers, the status / summary records, rotation
    pub fn run(&mut self, rx: crossbeam_channel::Receiver<Msg>) -> Value {
        loop {
            match rx.recv_timeout(Duration::from_millis(20)) {
                Ok(Msg::Stop) => break,
                Ok(m) => { self.on_msg(m); while let Ok(m) = rx.try_recv() { if matches!(m, Msg::Stop) { return self.end(); } self.on_msg(m); if self.recs.len() > 256 { self.emit(); } } }
                Err(crossbeam_channel::RecvTimeoutError::Timeout) => {}
                Err(crossbeam_channel::RecvTimeoutError::Disconnected) => break,
            }
            self.housekeeping(false);
        }
        self.end()
    }

    /// one message (timed)
    pub fn on_msg(&mut self, m: Msg) {
        let t0 = Instant::now();
        let (n, kind, slot) = match m {
            Msg::Tx(t) => { let (n, s) = (t.exec.trades.len(), t.slot); let nc = t.exec.creates.len(); self.on_tx(t); (n, if nc > 0 { "tx+create" } else { "tx" }, s) }
            Msg::Raw(r) => { self.raw_n += 1; if let Some(g) = self.migr.as_mut() { g.on_raw(&r, &self.book, &mut self.recs); } (0, "raw", r.slot) }
            Msg::Fail(f) => { self.fail_n += 1; if let Some(w) = self.watchm.as_mut() { w.on_fail(&f, &self.book, &mut self.recs); } (0, "fail", f.slot) }
            Msg::Arr { k8, feed, t, slot } => {
                let now = self.clock.max_t.max(t);
                if let Some(r) = self.race.as_mut() { r.on_arrival(k8, feed, t, slot, now, &mut self.recs); }
                (0, "arr", slot)
            }
            Msg::Stop => (0, "stop", 0),
        };
        self.msgs += 1;
        let us = t0.elapsed().as_secs_f64() * 1e6;
        self.tm.add(us, n);
        if us > 200.0 { self.tm.note_slow(us, format!("{kind} trades={n} recs_pending={}", self.recs.len()), slot); }
        if self.recs.len() >= 64 { self.emit(); }
    }

    fn on_tx(&mut self, t: TxIn) {
        let x = &t.exec;
        // the clock first (a window waiting for slot s starts on the first tx of slot >= s)
        if let Some(prev) = self.clock.see(t.slot, t.t_rx) { self.on_slot(prev, t.slot, t.t_rx); }
        for c in &x.creates {
            self.book.create(c.mint, t.slot, t.t_rx, c.creator, c.user, x.mayhem);
            if let Some(b) = self.blink.as_mut() { b.create(c.mint, t.slot, c.creator, x.mayhem, t.t_rx); }
        }
        for (j, e) in x.trades.iter().enumerate() {
            let tr = Tr { mint: e.mint, s: t.slot, i: t.idx as u32, j: j as u32, t: t.t_rx, sig: t.sig, user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok,
                fbps: e.fbps.min(u16::MAX as u64) as u16, cbps: e.cbps.min(u16::MAX as u64) as u16 };
            let watched = !self.watch.is_empty() && self.watch.contains(&e.user);
            // QUIET's dump history takes every trade (the re-arm's wh_fol)
            if let Some(q) = self.qbook.as_mut() { q.ingest(e, t.slot, t.idx as u32, j as i32, t.t_rx); }
            // BLINK reads its own book BEFORE the trade (its features are of the state before)
            if let Some(b) = self.blink.as_mut() { b.push(&tr, &self.clock, &mut self.recs); }
            let ctx = self.book.apply(&tr, watched);
            let Some(tok) = self.book.get(&e.mint) else { continue };
            if let Some(r) = self.race.as_mut() {
                let big = book::BIG;
                let tag = (if tr.buy && ctx.bal_before < big && ctx.bal_after >= big { race::T_WHALE } else { 0 })
                    | (if !tr.buy && (tr.tok as i64 >= big || self.live.armed_now(&tr.mint)) { race::T_DUMP } else { 0 })
                    | (if tr.vsol >= 100_000_000_000 && tok.normal() { race::T_MIG } else { 0 });
                r.tag(u64::from_be_bytes(t.sig[..8].try_into().unwrap()), t.idx, tag);
            }
            if let Some(r) = self.rearm.as_mut() { r.on_trade(tok, &tr, &ctx, &self.clock, &mut self.recs); }
            if let Some(h) = self.hold.as_mut() { h.on_trade(tok, &tr, &ctx, &mut self.recs); }
            if let Some(w) = self.watchm.as_mut() { if watched { w.on_trade(tok, &tr, &ctx, &t, &mut self.recs); } }
            if let Some(g) = self.migr.as_mut() { g.on_trade(tok, &tr, &ctx, &mut self.recs); }
            if let Some(sl) = self.select.as_mut() { sl.on_trade(tok, &tr, &ctx, self.qbook.as_ref(), &mut self.recs); }
            if let Some(b) = self.backrun.as_mut() { b.on_trade(tok, &tr, &ctx, &self.watch, self.select.as_ref(), &mut self.recs); }
            if let Some(x) = self.inslot.as_mut() { x.on_trade(tok, &tr, &ctx, self.race.as_ref().and_then(|r| r.earliest(u64::from_be_bytes(t.sig[..8].try_into().unwrap())))); }
        }
        if let Some(q) = self.qbook.as_mut() { if q.has_finalized() { let _ = q.take_finalized(); } }
    }

    fn on_slot(&mut self, prev: u64, slot: u64, t: u64) {
        if let Some(r) = self.rearm.as_mut() { r.on_slot(prev, slot, t, &self.book, &self.clock, self.qbook.as_ref(), &self.cfg, &self.live, &mut self.recs); }
        if let Some(b) = self.backrun.as_mut() { b.on_slot(slot, &mut self.recs); }
        if let Some(sl) = self.select.as_mut() { sl.on_slot(slot, t, &mut self.recs, false); }
        if let Some(x) = self.inslot.as_mut() { x.on_slot(slot, t, &mut self.recs, false); }
        if let Some(b) = self.blink.as_mut() { b.advance(slot); }
    }

    /// the tailer, the modules' timers, the book's sweep, the status / summary records, rotation (every loop pass: cheap when idle)
    pub fn housekeeping(&mut self, force: bool) {
        let now = self.clock.max_t;
        if let Some(tl) = self.tail.as_mut() {
            tl.poll(&mut self.live_buf, force);
            for e in std::mem::take(&mut self.live_buf) {
                self.live.on(&e, now);
                if let Some(h) = self.hold.as_mut() { h.on_live(&e, &self.book, &mut self.recs); }
                if let Some(r) = self.rearm.as_mut() { r.on_live(&e); }
            }
            self.ctr.tail_lines.store(tl.lines, Ordering::Relaxed);
        }
        if let Some(r) = self.rearm.as_mut() { r.tick(now, force, &self.book, &self.live, &self.cfg, &mut self.recs); }
        if let Some(h) = self.hold.as_mut() { h.tick(now, force, &self.book, &mut self.recs); }
        if let Some(g) = self.migr.as_mut() { g.tick(now, &self.book, &mut self.recs); }
        if let Some(b) = self.backrun.as_mut() { b.tick(now, force, &mut self.recs); }
        {
            let (r, h, g, b, sl, ins) = (self.rearm.as_ref(), self.hold.as_ref(), self.migr.as_ref(), self.backrun.as_ref(), self.select.as_ref(), self.inslot.as_ref());
            self.book.sweep(&|m| r.is_some_and(|x| x.busy(m)) || h.is_some_and(|x| x.busy(m)) || g.is_some_and(|x| x.busy(m)) || b.is_some_and(|x| x.busy(m)) || sl.is_some_and(|x| x.busy(m)) || ins.is_some_and(|x| x.busy(m)));
        }
        if let Some(q) = self.qbook.as_mut() { if q.has_finalized() { let _ = q.take_finalized(); } }
        self.emit();
        if self.last_status.elapsed() >= Duration::from_secs(60) || force { self.last_status = Instant::now(); let s = self.status_rec(); self.out.write(M_CORE, &s); }
        if self.last_summary.elapsed() >= Duration::from_secs(600) || force { self.last_summary = Instant::now(); self.summary(); }
        if let Some(n) = self.out.maybe() {
            let r = json!({"ev": "obs_part", "part": n, "t": crate::feeds::clock::now_ns(), "note": format!("previous part saved as {}.{n}", self.cfg.out.display())});
            self.out.write(M_CORE, &r);
        }
        self.publish();
    }

    /// the module records into the file
    pub fn emit(&mut self) {
        for (m, v) in std::mem::take(&mut self.recs) { self.out.write(m, &v); }
    }

    fn publish(&self) {
        let c = &self.ctr;
        c.processed.store(self.msgs, Ordering::Relaxed);
        c.trades.store(self.tm.trades, Ordering::Relaxed);
        c.records.store(self.out.recs.iter().sum(), Ordering::Relaxed);
        c.bytes.store(self.out.total_bytes, Ordering::Relaxed);
        c.write_err.store(self.out.errors, Ordering::Relaxed);
        c.parts.store(self.out.parts(), Ordering::Relaxed);
        c.us_p99_x10.store((self.tm.pct().1 * 10.0) as u64, Ordering::Relaxed);
        if let Some(r) = self.rearm.as_ref() { c.rearm_windows.store(r.st.windows, Ordering::Relaxed); c.rearm_fills.store(r.st.fills.iter().sum(), Ordering::Relaxed); }
        if let Some(h) = self.hold.as_ref() { c.hold_tapes.store(h.st.tapes, Ordering::Relaxed); }
        if let Some(w) = self.watchm.as_ref() { c.watch.store(w.st.trades + w.st.fails, Ordering::Relaxed); }
        if let Some(g) = self.migr.as_ref() { c.mig.store(g.st.records, Ordering::Relaxed); }
        if let Some(b) = self.blink.as_ref() { c.blink.store(b.st.triggers, Ordering::Relaxed); }
        if let Some(b) = self.backrun.as_ref() { c.backrun.store(b.st.records, Ordering::Relaxed); }
        if let Some(b) = self.select.as_ref() { c.select.store(b.st.written, Ordering::Relaxed); }
        if let Some(b) = self.race.as_ref() { c.race.store(b.records, Ordering::Relaxed); }
        if let Some(b) = self.inslot.as_ref() { c.inslot.store(b.records, Ordering::Relaxed); }
    }

    pub fn mem_bytes(&self) -> usize {
        self.book.mem_bytes() + self.qbook.as_ref().map(|q| q.mem_bytes()).unwrap_or(0) + self.rearm.as_ref().map(|r| r.mem_bytes()).unwrap_or(0)
            + self.hold.as_ref().map(|r| r.mem_bytes()).unwrap_or(0) + self.migr.as_ref().map(|r| r.mem_bytes()).unwrap_or(0)
            + self.blink.as_ref().map(|r| r.mem_bytes()).unwrap_or(0) + self.backrun.as_ref().map(|r| r.mem_bytes()).unwrap_or(0)
            + self.select.as_ref().map(|r| r.mem_bytes()).unwrap_or(0) + self.race.as_ref().map(|r| r.mem_bytes()).unwrap_or(0)
            + self.inslot.as_ref().map(|r| r.mem_bytes()).unwrap_or(0)
    }

    pub fn status_rec(&self) -> Value {
        let mem = self.mem_bytes();
        self.ctr.mem_mb.store((mem >> 20) as u64, Ordering::Relaxed);
        let c = &self.ctr;
        json!({"ev": "obs_status", "t": crate::feeds::clock::now_ns(), "data_t": self.clock.max_t, "slot": self.clock.cur, "up_s": self.t_start.elapsed().as_secs(),
            "sent": c.sent.load(Ordering::Relaxed), "dropped": c.drops.load(Ordering::Relaxed), "msgs": self.msgs, "raw": self.raw_n, "fail": self.fail_n,
            "timing": self.tm.json(), "mem_mb_est": (mem as f64 / 1048576.0 * 10.0).round() / 10.0, "book": {"tokens": self.book.toks.len(), "stats": format!("{:?}", self.book.st)},
            "records": self.out.recs, "bytes": self.out.bytes, "write_errors": self.out.errors, "part": self.out.parts(),
            "tail": self.tail.as_ref().map(|t| json!({"lines": t.lines, "parsed": t.parsed, "bad": t.bad, "live_attempts": self.live.attempts, "live_fills": self.live.fills})),
            "rearm": self.rearm.as_ref().map(|r| r.status()), "hold": self.hold.as_ref().map(|h| h.status()), "watch": self.watchm.as_ref().map(|w| w.status()),
            "migration": self.migr.as_ref().map(|g| g.status()), "blink": self.blink.as_ref().map(|b| b.status()), "backrun": self.backrun.as_ref().map(|b| b.status()), "select": self.select.as_ref().map(|b| b.status()), "race": self.race.as_ref().map(|b| b.status()), "inslot": self.inslot.as_ref().map(|b| b.status())})
    }

    /// the 10-min summary record (every module's totals; the re-arm's paper P&L by size / exit)
    fn summary(&mut self) {
        self.summaries += 1;
        let mut s = json!({"ev": "obs_summary", "n": self.summaries, "t": crate::feeds::clock::now_ns(), "data_t": self.clock.max_t, "slot": self.clock.cur});
        if let Some(r) = self.rearm.as_ref() { s["rearm"] = r.summary(); }
        if let Some(h) = self.hold.as_ref() { s["hold"] = h.summary(); }
        if let Some(w) = self.watchm.as_ref() { s["watch"] = w.summary(); }
        if let Some(g) = self.migr.as_ref() { s["migration"] = g.status(); }
        if let Some(b) = self.blink.as_ref() { s["blink"] = b.status(); }
        if let Some(b) = self.backrun.as_ref() { s["backrun"] = b.summary(); }
        if let Some(b) = self.select.as_ref() { s["select"] = b.summary(); }
        if let Some(b) = self.race.as_mut() { s["race"] = b.summary(); }
        if let Some(b) = self.inslot.as_ref() { s["inslot"] = b.summary(); }
        s["records"] = json!(self.out.recs); s["bytes"] = json!(self.out.bytes);
        self.out.write(M_CORE, &s);
    }

    /// the run's end: what is due is closed (open windows / tapes flagged "run_end"), the last summary, flushed
    pub fn end(&mut self) -> Value {
        if let Some(tl) = self.tail.as_mut() { tl.poll(&mut self.live_buf, true); }
        for e in std::mem::take(&mut self.live_buf) {
            self.live.on(&e, self.clock.max_t);
            if let Some(h) = self.hold.as_mut() { h.on_live(&e, &self.book, &mut self.recs); }
            if let Some(r) = self.rearm.as_mut() { r.on_live(&e); }
        }
        let now = self.clock.max_t;
        if let Some(r) = self.rearm.as_mut() { r.finish(now, &self.book, &self.live, &self.cfg, &mut self.recs); }
        if let Some(h) = self.hold.as_mut() { h.finish(&self.book, &mut self.recs); }
        if let Some(b) = self.backrun.as_mut() { b.tick(u64::MAX, true, &mut self.recs); }
        if let Some(w) = self.watchm.as_mut() { w.finish(&mut self.recs); }
        if let Some(sl) = self.select.as_mut() { sl.on_slot(u64::MAX, now, &mut self.recs, true); }
        if let Some(r) = self.race.as_mut() { r.expire(u64::MAX, true, &mut self.recs); }
        if let Some(x) = self.inslot.as_mut() { x.on_slot(u64::MAX, now, &mut self.recs, true); }
        self.emit();
        self.summary();
        let st = self.status_rec();
        self.out.write(M_CORE, &st);
        self.out.write(M_CORE, &json!({"ev": "obs_end", "t": crate::feeds::clock::now_ns()}));
        self.out.flush();
        self.publish();
        json!({"file": self.cfg.out.display().to_string(), "parts": self.out.parts(), "records": self.out.recs, "bytes": self.out.bytes, "write_errors": self.out.errors,
               "sent": self.ctr.sent.load(Ordering::Relaxed), "dropped": self.ctr.drops.load(Ordering::Relaxed), "timing": self.tm.json(), "modules": self.cfg.names()})
    }
}

/// a JSON list of base58 wallets (the follower-bot list): empty on any error (the caller says so)
pub fn load_pk_list(path: &str) -> Result<FxHashSet<Pk>, String> {
    let v: Vec<String> = serde_json::from_str(&std::fs::read_to_string(path).map_err(|e| format!("{path}: {e}"))?).map_err(|e| format!("{path}: {e}"))?;
    Ok(v.iter().filter_map(|s| bs58::decode(s).into_vec().ok().and_then(|b| <[u8; 32]>::try_from(b).ok())).collect())
}

/// unused helper kept for readers of BufRead-based tools (tests)
#[allow(dead_code)]
fn lines_of(p: &Path) -> Vec<String> { std::fs::File::open(p).map(|f| std::io::BufReader::new(f).lines().map_while(Result::ok).collect()).unwrap_or_default() }

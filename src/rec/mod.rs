//! The recorder (PLAN WP-02 items 2-8; MEASUREMENT §0, §1, §1.3-§1.5, §4.4-§4.6). It replaces arb-lab's `record.rs`,
//! which was off by default and wrote (and flushed) on the caller's thread.
//!
//! - **Always on.** `arbx run` starts it before anything records; there is no switch (`[record] enabled` is gone).
//! - **Never on the hot path.** Producers call [`Rec::emit`]: one queue-depth check and a channel send. A full queue
//!   drops the record and counts it; nothing blocks. A record is a closure that encodes it on the class's writer
//!   thread (text and binary streams: the formatting and base58 happen there), or a `serde_json::Value` that is only
//!   serialized there (its tree, and any base58 string in it, is built by the producer: review F10).
//! - **One writer thread per class** (core, replay, chain, bulk, slow; MEASUREMENT §1.2), niced +5 and optionally pinned
//!   away from the engine (`[record] writer_cpus`). Compressed streams are zstd frames: a frame ends every `flush_ms`
//!   and every 4 MiB (and on the core writer whenever its queue is empty), so every finished frame can be read while the
//!   run goes on; files rotate at `rotate_mb` (raw) or `rotate_min`, and each starts with its schema header (§1.3). The
//!   slow class writes plain, line-buffered files. Lines echoed to stdout / stderr (the segment's `.out`) go through
//!   their own thread and bounded queue (`arbx-rec-echo`): a failing or blocked stdout never stops a writer (review F2).
//! - **Drops by class** (§1.5): a core drop sends the SendGate to shadow for the rest of the segment
//!   (`core_record_loss`); a replay drop writes a GAP record with the stream's next record; chain and bulk drops are
//!   counted. Every first drop of a stream (then at most one a second) is an `events.jsonl` `recorder_drop`.
//! - **Faults are losses too** (review F1, F2): a record the writer cannot write (open, compression or write error) or
//!   encode (its encoder panicked) is counted per stream and never as written; on a core stream it is a core loss
//!   (shadow, as a drop). status.jsonl that cannot be written, or a core or slow writer that dies or stops making
//!   progress, stops the segment (reason `error`): the supervisor's budget reads status.jsonl.
//! - **Disk budget** ([`disk`]) and **manifest** ([`manifest`]) run on a monitor thread, with `resources.jsonl`
//!   ([`health`]); the monitor also watches the writer threads.
pub mod accounts;
pub mod disk;
pub mod exec;
pub mod health;
pub mod journal;
pub mod manifest;
pub mod sample;
mod writer;

use crate::config::RecordCfg;
use crate::control::{SendGate, StopInfo, StopReason, Stopper};
use crate::feeds::clock::now_ns;
use anyhow::{Context, Result};
use serde_json::{json, Value};
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicI32, AtomicU32, AtomicU64, Ordering::Relaxed};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Duration;

// ------------------------------------------------------------------ classes, queues, streams

/// MEASUREMENT §1.2 stream classes; one writer thread each
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Class { Core, Replay, Chain, Bulk, Slow }

impl Class {
    pub const ALL: [Class; 5] = [Class::Core, Class::Replay, Class::Chain, Class::Bulk, Class::Slow];
    pub fn as_str(self) -> &'static str {
        match self { Class::Core => "core", Class::Replay => "replay", Class::Chain => "chain", Class::Bulk => "bulk", Class::Slow => "slow" }
    }
    fn idx(self) -> usize { self as usize }
    /// the queues its streams use
    fn queues(self) -> &'static [Queue] {
        match self { Class::Core => &[Queue::Core], Class::Replay => &[Queue::Accounts, Queue::Journal], Class::Chain => &[Queue::Chain], Class::Bulk => &[Queue::Bulk],
            Class::Slow => &[Queue::Slow] }
    }
}

/// The bounded queues: one per class, except the replay class, whose two streams have their own (§1.2: accounts 1M,
/// journal 512k). The slow class is unbounded (low rate)
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Queue { Core, Accounts, Journal, Chain, Bulk, Slow }

impl Queue {
    const ALL: [Queue; 6] = [Queue::Core, Queue::Accounts, Queue::Journal, Queue::Chain, Queue::Bulk, Queue::Slow];
    pub fn as_str(self) -> &'static str {
        match self { Queue::Core => "core", Queue::Accounts => "accounts", Queue::Journal => "journal", Queue::Chain => "chain", Queue::Bulk => "bulk", Queue::Slow => "slow" }
    }
}

/// How a stream is written (§1.3)
#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Format {
    /// JSON lines; zstd frames; rotated; a JSON header line first
    Jsonl,
    /// text lines; zstd frames; rotated; a `# arbx.<stream>/<v> key=value ...` header line first
    Text,
    /// binary records; zstd frames; rotated; `magic | u16 format | u16 hlen | JSON header` first
    Bin { magic: [u8; 8], format: u16 },
    /// plain JSON lines (uncompressed, one write per line, so `tail` works); a JSON header line first
    PlainJsonl,
    /// plain text lines for humans, no header (run.log: `<t_ns> <message>`)
    PlainText,
}

impl Format {
    fn ext(self) -> &'static str { match self { Format::Jsonl | Format::PlainJsonl => "jsonl", Format::Text | Format::PlainText => "log", Format::Bin { .. } => "bin" } }
    pub fn plain(self) -> bool { matches!(self, Format::PlainJsonl | Format::PlainText) }
    fn lines(self) -> bool { !matches!(self, Format::Bin { .. }) }
}

/// A stream id: the index in the recorder's stream table
#[derive(Clone, Copy, PartialEq, Eq, Hash, Debug)]
pub struct S(pub u16);

pub const ATTEMPTS: S = S(0);
pub const COPIES: S = S(1);
pub const BUNDLES: S = S(2);
pub const OUTCOMES: S = S(3);
pub const ACCOUNTS: S = S(4);
pub const JOURNAL: S = S(5);
pub const EXEC: S = S(6);
pub const TXARR: S = S(7);
pub const ARRIVALS: S = S(8);
pub const MOVES: S = S(9);
pub const POH: S = S(10);
pub const SLOTS_FEED: S = S(11);
pub const ALTS_FINAL: S = S(12);
pub const TRIGGERS: S = S(13);
pub const PREDICTIONS: S = S(14);
pub const CAPS: S = S(15);
pub const SIMS: S = S(16);
pub const OPPORTUNITIES: S = S(17);
pub const RIVALS: S = S(18);
pub const STATUS: S = S(19);
pub const EVENTS: S = S(20);
pub const FEEDHEALTH: S = S(21);
pub const RESOURCES: S = S(22);
pub const KEEPALIVE: S = S(23);
pub const RUN_LOG: S = S(24);
/// WP-03: the slot statuses of the state stream (§4.17), its block metas (§4.16) and the LeaderBook's schedule (§4.27)
pub const SLOTS: S = S(25);
pub const BLOCKS: S = S(26);
pub const LEADERS: S = S(27);
/// WP-04: every commit group at resolution (§4.31), every route evaluation (§4.32), lookup-table events (§4.26)
pub const COMMITS: S = S(28);
pub const DECISIONS: S = S(29);
pub const ALTS: S = S(30);
/// WP-03b: our wallet's transactions (§4.15, core), the slot index (§4.16b) and the chain fetches (§4.18)
pub const WALLET: S = S(31);
pub const SLOTIDX: S = S(32);
pub const TXFETCH: S = S(33);
/// WP-08: the LeaderBook's validator snapshots (§4.28). Its id is its row's index in the table, found by name at compile
/// time ([`id_of`]): lanes that each append streams at the same index cannot give it another stream's row when they merge
/// (review WP-08 #12; `stream_ids_name_their_rows` checks every constant)
pub const VALIDATORS: S = S(id_of("validators"));
/// WP-07: money by signature (§4.42, core: a lost line closes the SendGate), the balance snapshots (§4.43) and the
/// reconciliations (§4.44), plain
pub const LEDGER: S = S(id_of("ledger"));
pub const SNAPSHOTS: S = S(id_of("snapshots"));
pub const RECON: S = S(id_of("recon"));
/// WP-11: the experiments' configuration and block switches (§4.45), plain
pub const EXPERIMENTS: S = S(id_of("experiments"));

/// The id of the stream named `name` in the table (compile time; a name that is not in it does not compile)
pub const fn id_of(name: &str) -> u16 {
    let mut i = 0;
    while i < STATIC.len() {
        let (a, b) = (STATIC[i].0.as_bytes(), name.as_bytes());
        if a.len() == b.len() {
            let mut j = 0;
            while j < a.len() && a[j] == b[j] { j += 1; }
            if j == a.len() { return i as u16; }
        }
        i += 1;
    }
    panic!("no such stream in the recorder's table");
}

pub const ACCOUNTS_MAGIC: [u8; 8] = *b"ARBXACC\0";
pub const JOURNAL_MAGIC: [u8; 8] = *b"ARBXJRN\0";
pub const ENTRIES_MAGIC: [u8; 8] = *b"ARBXENT\0";

/// (name, class, format, schema, single file). Versions (MEASUREMENT "As WP-02 writes them"): `1.1` is arb-lab's v1
/// record with the WP-00/WP-01 fields (§7), now behind a header; `2.0` where the stream is at v2. Streams of later WPs
/// (ledger, wallet, decisions, commits, slotidx, txfetch, alts events, ...) are added here by them. `accounts` and
/// `journal` are WP-03's formats (src/rec/accounts.rs, src/rec/journal.rs); their queues and GAP records are this
/// module's. WP-03 also brings exec v2 (src/rec/exec.rs), slots, blocks and leaders; WP-04 commits, decisions and alts;
/// WP-03b wallet, slotidx and txfetch; WP-08 exec 2.1 (the derived fields), leaders 1.1 (region, endpoint, RTT, client,
/// kind updates), rivals 1.2 (the sampled `venues` rows, `sample`; plan addendum I-9) and validators; WP-05 attempts,
/// bundles and outcomes 2.0 (their v2 shapes), copies 1.2 and decisions 1.1 (fields added); WP-07 ledger (core),
/// snapshots and recon (plain), status 2.1 (`money` from the ledger), the journal (same framing, 2.2: INPUT 13
/// `snapshot`, INPUT 7's `ledger`, the decision-point record's `money`), wallet 1.1 (`found_by` `executor_status`),
/// outcomes 2.1 (`ledger` filled); the FT-000 fixes the journal 2.3 (ALT `found` 4, the cache's evictions), exec 2.2
/// (`sample`), alts 2.1, alts-final 1.2, slotidx 1.1 (`pos_kind`), status 2.1 (`rpc_budget`) and wallet 1.1 (block
/// indexes only, the hour's rows, the cursor). At their merge (integ/stage0) WP-07's and the FT-000 fixes' status 2.1
/// and wallet 1.1 were two shapes under one number each: the merged streams are status 2.2 (`money`, `rpc_budget`,
/// WP-20's `alerts`) and wallet 1.2 (both lanes' changes); the journal stays 2.3, now with WP-07's INPUT 13 and
/// `money` too (WP-07 added them within 2.2's framing; MEASUREMENT §4.13). WP-06 (merged after them, at the end of
/// Stage 0): attempts 2.1 (the bundle's layout: CU source, loaded-data limit, create/close, the size budget's fallback,
/// the tip's band share) and decisions 1.2 (`dlmm_cap_bound`); the journal 2.4 (2.3's records, with engine_init's
/// `builder` and exec_init version 2: a 2.3 journal of integ/stage0 has neither, and its executor is not replayed);
/// after it, sims 1.2 (WP-06's `closes_ata`, which its lane added under 1.1). FT-006 (the BAM landing fix): copies 1.3
/// (`endpoint`, `leader_kind`) and attempts 2.2 (`tip.bam`, `tip.policy` `bam_floor`, `copies[].endpoint` and
/// `copies[].leader_kind`). WP-11: experiments (plain, slow: one `config` line per enabled experiment at the start); decisions
/// 1.2 and attempts 2.2 keep their shapes (their `experiments` maps and `tip.arm` hold the arms)
const STATIC: [(&str, Class, Format, &str, bool); 39] = [
    ("attempts", Class::Core, Format::Jsonl, "arbx.attempts/2.2", false),
    ("copies", Class::Core, Format::Jsonl, "arbx.copies/1.3", false),
    ("bundles", Class::Core, Format::Jsonl, "arbx.bundles/2.0", false),
    ("outcomes", Class::Core, Format::Jsonl, "arbx.outcomes/2.1", false),
    ("accounts", Class::Replay, Format::Bin { magic: ACCOUNTS_MAGIC, format: 2 }, "arbx.accounts/2.1", false),
    ("journal", Class::Replay, Format::Bin { magic: JOURNAL_MAGIC, format: 2 }, "arbx.journal/2.4", false),
    ("exec", Class::Chain, Format::Jsonl, "arbx.exec/2.2", false),
    ("txarr", Class::Chain, Format::Text, "arbx.txarr/1.1", false),
    ("arrivals", Class::Chain, Format::Jsonl, "arbx.arrivals/1.1", false),
    ("moves", Class::Chain, Format::Text, "arbx.moves/2.0", false),
    ("poh", Class::Chain, Format::Text, "arbx.poh/2.0", false),
    ("slots-feed", Class::Chain, Format::Text, "arbx.slots-feed/2.0", false),
    ("alts-final", Class::Chain, Format::Jsonl, "arbx.alts-final/1.2", true),
    ("triggers", Class::Chain, Format::Jsonl, "arbx.triggers/2.0", false),
    ("predictions", Class::Chain, Format::Jsonl, "arbx.predictions/2.0", false),
    ("caps", Class::Chain, Format::Jsonl, "arbx.caps/1.2", false),
    ("sims", Class::Chain, Format::Jsonl, "arbx.sims/1.2", false),
    ("opportunities", Class::Chain, Format::Jsonl, "arbx.opportunities/1.2", false),
    ("rivals", Class::Bulk, Format::Jsonl, "arbx.rivals/1.2", false),
    ("status", Class::Slow, Format::PlainJsonl, "arbx.status/2.2", false),
    ("events", Class::Slow, Format::PlainJsonl, "arbx.events/1.0", false),
    ("feedhealth", Class::Slow, Format::PlainJsonl, "arbx.feedhealth/1.0", false),
    ("resources", Class::Slow, Format::PlainJsonl, "arbx.resources/1.0", false),
    ("keepalive", Class::Slow, Format::PlainJsonl, "arbx.keepalive/1.1", false),
    ("run", Class::Slow, Format::PlainText, "arbx.run/1.0", false),
    ("slots", Class::Chain, Format::Jsonl, "arbx.slots/1.0", false),
    ("blocks", Class::Chain, Format::Jsonl, "arbx.blocks/1.0", false),
    ("leaders", Class::Chain, Format::Jsonl, "arbx.leaders/1.1", false),
    ("commits", Class::Core, Format::Jsonl, "arbx.commits/1.0", false),
    ("decisions", Class::Core, Format::Jsonl, "arbx.decisions/1.2", false),
    ("alts", Class::Chain, Format::Jsonl, "arbx.alts/2.1", false),
    ("wallet", Class::Core, Format::Jsonl, "arbx.wallet/1.2", false),
    ("slotidx", Class::Chain, Format::Jsonl, "arbx.slotidx/1.1", false),
    ("txfetch", Class::Chain, Format::Jsonl, "arbx.txfetch/1.0", false),
    ("validators", Class::Bulk, Format::Jsonl, "arbx.validators/1.0", false),
    ("ledger", Class::Core, Format::Jsonl, "arbx.ledger/1.0", false),
    ("snapshots", Class::Slow, Format::PlainJsonl, "arbx.snapshots/1.0", false),
    ("recon", Class::Slow, Format::PlainJsonl, "arbx.recon/1.0", false),
    ("experiments", Class::Slow, Format::PlainJsonl, crate::experiments::SCHEMA, false),
];

/// a zstd frame ends at the latest when this much raw data is pending (§1.3)
pub const FRAME_MAX: usize = 4 << 20;

/// One stream's definition
#[derive(Clone, Debug)]
pub struct Spec { pub name: String, pub class: Class, pub format: Format, pub schema: &'static str, pub single: bool, pub queue: Queue }

impl Spec {
    /// the file name: `<stream>.<NNN>.<ext>.zst` (§1.3), `<stream>.<ext>.zst` for a single dump, `<stream>.<ext>` plain
    pub fn file_name(&self, seq: u32) -> String {
        if self.format.plain() { return format!("{}.{}", self.name, self.format.ext()); }
        if self.single { format!("{}.{}.zst", self.name, self.format.ext()) } else { format!("{}.{seq:03}.{}.zst", self.name, self.format.ext()) }
    }
}

/// A record handed to the recorder. Whatever it costs to turn it into bytes is paid on the writer thread
pub enum Record {
    /// a JSON object (serialized on the writer)
    Json(Value),
    /// a ready text line (no trailing newline): slow, rare streams only
    Line(String),
    /// a closure that encodes the record (a line without its newline, or a whole binary record), on the writer
    Enc(Box<dyn FnOnce(&mut Vec<u8>) + Send>),
    /// a closure that encodes `n` lines at once (newline-separated, without the last newline): one queue slot, counted
    /// as `n` records (poh.log's lines of one message or data set; review F11)
    EncN(u32, Box<dyn FnOnce(&mut Vec<u8>) + Send>),
    /// a binary record already encoded
    Bin(Vec<u8>),
    /// a record encoded against its stream's per-file state ([`FileState`], installed with [`Rec::set_file_state`]):
    /// dictionaries and keyframes that restart with every file (review F16; WP-03's accounts.bin)
    Stateful(Box<dyn FnOnce(&mut dyn std::any::Any, &mut Vec<u8>) + Send>),
    /// slow class only: work done on the slow writer (atomic file writes off the engine thread)
    Task(Box<dyn FnOnce() + Send>),
}

impl Record {
    pub fn enc(f: impl FnOnce(&mut Vec<u8>) + Send + 'static) -> Record { Record::Enc(Box::new(f)) }
    /// `n` lines encoded by one closure (see [`Record::EncN`])
    pub fn enc_lines(n: u32, f: impl FnOnce(&mut Vec<u8>) + Send + 'static) -> Record { Record::EncN(n, Box::new(f)) }
    /// a record encoded with the stream's per-file state of type `T` (see [`Record::Stateful`])
    pub fn stateful<T: 'static>(f: impl FnOnce(&mut T, &mut Vec<u8>) + Send + 'static) -> Record {
        Record::Stateful(Box::new(move |st: &mut dyn std::any::Any, o: &mut Vec<u8>| {
            match st.downcast_mut::<T>() { Some(s) => f(s, o), None => panic!("a stateful record for another state type") }
        }))
    }
    /// a typed record, serialized as JSON on the writer
    pub fn ser<T: serde::Serialize + Send + 'static>(v: T) -> Record { Record::enc(move |o| { let _ = serde_json::to_writer(o, &v); }) }
    /// the bytes a queue holds for it, as far as the producer knows them (the byte budget, review F17)
    fn size(&self) -> u64 { match self { Record::Bin(b) => b.len() as u64, Record::Line(l) => l.len() as u64, _ => 0 } }
}

/// A stream's per-file encoder state, owned by its writer (review F16). `on_new_file` runs right after each new file's
/// header (the first file and every rotation), so dictionaries and keyframes restart per file and every file decodes on
/// its own (MEASUREMENT §1.3); what it writes to `out` follows the header
pub trait FileState: Send + 'static {
    fn on_new_file(&mut self, file_seq: u32, out: &mut Vec<u8>);
    fn as_any(&mut self) -> &mut dyn std::any::Any;
}

// ------------------------------------------------------------------ state

/// one file of a stream (manifest.json `streams[].files[]`)
#[derive(Clone, Debug, Default, serde::Serialize)]
pub struct FileStat {
    pub path: String,
    pub bytes_raw: u64,
    pub bytes_written: u64,
    pub records: u64,
    pub first_t_ns: Option<u64>,
    pub last_t_ns: Option<u64>,
    pub closed: bool,
    pub sha256: Option<String>,
}

struct StreamState {
    spec: Spec,
    /// false once the disk budget switched it off (its records are then counted as `suppressed`)
    on: AtomicBool,
    dropped: AtomicU64,
    suppressed: AtomicU64,
    /// emitted after the recorder closed
    late: AtomicU64,
    /// replay streams: the next sequence number (`aseq`, journal `seq`)
    seq: AtomicU64,
    /// replay streams: sequence ranges lost to drops, written as GAP records with the next record
    lost: Mutex<Vec<(u64, u64)>>,
    lost_flag: AtomicBool,
    last_drop_event: AtomicU64,
    /// records written (counted once their bytes are on disk) and bytes on disk (writer side)
    written_records: AtomicU64,
    written_bytes: AtomicU64,
    /// failed opens, compressions and writes (review F1)
    io_errors: AtomicU64,
    /// records taken and encoded but not written because of an I/O error
    io_lost: AtomicU64,
    /// records whose encoder (or task) panicked: not written
    enc_errors: AtomicU64,
    last_err_event: AtomicU64,
    files: Mutex<Vec<FileStat>>,
    /// extra header fields (txarr: `feeds`; entries: `feed`)
    header_extra: Vec<(String, String)>,
}

impl StreamState {
    fn add_lost(&self, seq: u64) {
        let mut l = self.lost.lock().unwrap_or_else(|e| e.into_inner());
        match l.last_mut() { Some(last) if last.0 + last.1 == seq => last.1 += 1, _ => l.push((seq, 1)) }
        self.lost_flag.store(true, Relaxed);
    }
    fn take_lost(&self) -> Option<Vec<(u64, u64)>> {
        let mut l = self.lost.lock().unwrap_or_else(|e| e.into_inner());
        self.lost_flag.store(false, Relaxed);
        if l.is_empty() { None } else { Some(std::mem::take(&mut *l)) }
    }
}

/// One queue: a record cap and a byte cap (the payload bytes the producers declared: `Record::Bin`, `Record::Line`,
/// [`Rec::emit_sized`]; review F17), their high-water marks, and what was still counted in it when the recorder closed
struct QueueState { cap: u64, byte_cap: u64, depth: AtomicU64, hwm: AtomicU64, hwm_iv: AtomicU64, bytes: AtomicU64, bytes_hwm: AtomicU64, lost_at_close: AtomicU64 }

pub(crate) struct Msg { pub s: S, pub gap: Option<Vec<(u64, u64)>>, pub size: u64, pub r: Record }

pub(crate) enum Ctl {
    Rec(Msg),
    Sync(crossbeam_channel::Sender<()>),
    Close,
    /// open a stream's file now (plain streams at start; status.jsonl when the engine starts), its header stamped `t`;
    /// the answer says whether the file is open
    Open(S, u64, Option<crossbeam_channel::Sender<std::result::Result<(), String>>>),
    /// install a stream's per-file encoder state
    State(S, Box<dyn FileState>),
}

/// a line for stdout or stderr (the segment's `.out`), written by the echo thread
enum Echo { Out(String), Err(String), End }

/// lines waiting for the echo thread at most; past it they are counted (`echo_dropped`), never waited for
const ECHO_QUEUE: usize = 4_096;
/// how long `close` waits for the writers to drain and close their files
pub const CLOSE_WAIT: Duration = Duration::from_secs(20);
/// a core or slow writer with records queued and no progress this long stops the segment (the monitor's check)
pub const STALL_LIMIT: Duration = Duration::from_secs(60);
/// the bytes of the queue byte caps' unit
const MB: f64 = (1u64 << 20) as f64;

/// What a run's recorder needs to start
pub struct Opts {
    pub dir: PathBuf,
    /// the segment's name (every header's `run`)
    pub run: String,
    /// the binary's sha256, first 8 bytes in hex (every header's `producer`)
    pub producer: String,
    pub cfg: RecordCfg,
    /// the enabled feeds, in id order (txarr's columns, the entries archives)
    pub feeds: Vec<String>,
    /// start the monitor thread (disk budget every 10 s, resources.jsonl, manifest.json every 60 s, the writers' health)
    /// and refuse to start under `min_free_gb` (the run)
    pub monitor: bool,
    /// where echoed lines go (tests); None: stdout and stderr
    pub echo: Option<Box<dyn Write + Send>>,
}

pub struct Recorder {
    pub dir: PathBuf,
    run: String,
    producer: String,
    pub cfg: RecordCfg,
    streams: Vec<StreamState>,
    queues: Vec<QueueState>,
    tx: Vec<crossbeam_channel::Sender<Ctl>>,
    /// each writer thread, and a channel that disconnects when it ends (a bounded wait at close)
    threads: Mutex<Vec<(Class, std::thread::JoinHandle<()>, crossbeam_channel::Receiver<()>)>>,
    closed: AtomicBool,
    /// a writer thread ended before the close (review F2)
    dead: [AtomicBool; 5],
    /// messages each writer has taken (the monitor's stall check)
    progress: [AtomicU64; 5],
    /// why the recorder stopped the segment (status.jsonl not written, a core or slow writer gone), once
    fatal: OnceLock<String>,
    echo: crossbeam_channel::Sender<Echo>,
    echo_done: Mutex<Option<crossbeam_channel::Receiver<()>>>,
    echo_dropped: AtomicU64,
    /// the writers that had not finished when `close` stopped waiting (manifest `close_timeout`)
    close_timeout: Mutex<Vec<&'static str>>,
    /// test hook: a class's writer panics outside a record (a writer that dies)
    crash: [AtomicBool; 5],
    /// how long `close` waits for the writers, ms ([`CLOSE_WAIT`]; tests shorten it)
    close_wait_ms: AtomicU64,
    pub started_ns: u64,
    /// (feed id, its entries-<feed> stream)
    entries: Vec<(u16, S)>,
    core_lost: AtomicBool,
    gate: OnceLock<Arc<SendGate>>,
    stopper: OnceLock<Arc<Stopper>>,
    /// accounts.bin keyframe interval (WP-03 reads it; the disk budget lengthens it 4x)
    keyframe_every: AtomicU32,
    pub(crate) disk: Mutex<disk::Ladder>,
    engine_tid: AtomicI32,
    runtimes: OnceLock<(tokio::runtime::Handle, tokio::runtime::Handle)>,
    /// (local UDP port, the counter the kernel's drop count for it goes to)
    udp: Mutex<Vec<(u16, Arc<AtomicU64>)>>,
    /// test hook: a class's writer stops reading (a stalled writer)
    stall: [AtomicBool; 5],
    monitor: Mutex<Option<(Arc<AtomicBool>, std::thread::JoinHandle<()>)>>,
    /// what `start` noted (an archive feed that is not running, ...) for run.log
    pub notes: Vec<String>,
    /// plan addendum I-9 (WP-08): rivals.jsonl's `why = venues` rows, 1 in `[record] rivals_venues_sample` kept
    pub(crate) rival_venues: sample::Sampler,
    /// WP-20: every events.jsonl event is shown to the alerts (`Rec::set_alert_tap`; src/alerts.rs `classify`), on the
    /// producer's thread: the tap never waits
    alert_tap: OnceLock<AlertTap>,
    /// FT-000 (S1-5): exec.jsonl's transaction-stream records that touch no watched account, 1 in
    /// `[record] exec_unwatched_sample` kept
    pub(crate) exec_unwatched: sample::Sampler,
}

/// WP-20: what the recorder hands every events.jsonl event to (kind, subsystem, feed, detail) before it queues it
pub type AlertTap = Box<dyn Fn(&'static str, &'static str, Option<u16>, &Value) + Send + Sync>;

/// The handle every producer holds. `Rec::off()` records nothing (tools, tests, the recorder-off benchmark)
#[derive(Clone, Default)]
pub struct Rec(Option<Arc<Recorder>>);

/// Start a recorder in `opts.dir`: its writer threads, the echo thread, and the monitor thread if asked. The plain
/// streams (events, feedhealth, resources, keepalive, run.log) are created at once with their headers; status.jsonl
/// when the engine starts ([`Rec::open_now`]: the supervisor reads its existence as "the engine started"). With the
/// monitor (the run), a filesystem under `min_free_gb` is refused here (review F5): the disk ladder would stop the run
pub fn start(opts: Opts) -> Result<Rec> {
    std::fs::create_dir_all(&opts.dir).with_context(|| format!("creating {}", opts.dir.display()))?;
    let cfg = opts.cfg.clone();
    if opts.monitor {
        let floor = (cfg.min_free_gb * (1u64 << 30) as f64) as u64;
        if let Some(free) = disk::fs_free(&opts.dir).filter(|f| *f < floor) {
            anyhow::bail!("only {:.1} GB free on the filesystem of {}, under [record] min_free_gb = {}: not starting (the disk budget would stop the \
                segment; free space, or lower min_free_gb for a test run)", free as f64 / (1u64 << 30) as f64, opts.dir.display(), cfg.min_free_gb);
        }
    }
    let mut specs: Vec<(Spec, Vec<(String, String)>)> = STATIC.iter().map(|&(name, class, format, schema, single)| {
        let queue = match (class, name) { (Class::Replay, "accounts") => Queue::Accounts, (Class::Replay, _) => Queue::Journal,
            (Class::Core, _) => Queue::Core, (Class::Chain, _) => Queue::Chain, (Class::Bulk, _) => Queue::Bulk, (Class::Slow, _) => Queue::Slow };
        let extra = if name == "txarr" { vec![("feeds".to_string(), opts.feeds.join(","))] } else { vec![] };
        (Spec { name: name.to_string(), class, format, schema, single, queue }, extra)
    }).collect();
    let mut entries = Vec::new();
    let mut notes = Vec::new();
    for f in &cfg.archive_feeds {
        match opts.feeds.iter().position(|n| n == f) {
            Some(id) => {
                entries.push((id as u16, S(specs.len() as u16)));
                specs.push((Spec { name: format!("entries-{f}"), class: Class::Bulk, format: Format::Bin { magic: ENTRIES_MAGIC, format: 1 }, schema: "arbx.entries/1.0",
                    single: false, queue: Queue::Bulk }, vec![("feed".into(), f.clone()), ("feed_id".into(), id.to_string())]));
            }
            None => notes.push(format!("record: archive feed {f} is not running in this segment: not archived")),
        }
    }
    let caps = [cfg.queue_core, cfg.queue_accounts, cfg.queue_journal, cfg.queue_chain, cfg.queue_bulk, u64::MAX];
    let byte_cap = (cfg.queue_max_mb * MB) as u64;
    let queues = caps.iter().map(|&cap| QueueState { cap, byte_cap: if cap == u64::MAX { u64::MAX } else { byte_cap }, depth: AtomicU64::new(0), hwm: AtomicU64::new(0),
        hwm_iv: AtomicU64::new(0), bytes: AtomicU64::new(0), bytes_hwm: AtomicU64::new(0), lost_at_close: AtomicU64::new(0) }).collect();
    let mut tx = Vec::new();
    let mut rx = Vec::new();
    for _ in Class::ALL { let (t, r) = crossbeam_channel::unbounded::<Ctl>(); tx.push(t); rx.push(r); }
    let streams = specs.into_iter().map(|(spec, header_extra)| StreamState { spec, on: AtomicBool::new(true), dropped: AtomicU64::new(0), suppressed: AtomicU64::new(0),
        late: AtomicU64::new(0), seq: AtomicU64::new(0), lost: Mutex::new(Vec::new()), lost_flag: AtomicBool::new(false), last_drop_event: AtomicU64::new(0),
        written_records: AtomicU64::new(0), written_bytes: AtomicU64::new(0), io_errors: AtomicU64::new(0), io_lost: AtomicU64::new(0), enc_errors: AtomicU64::new(0),
        last_err_event: AtomicU64::new(0), files: Mutex::new(Vec::new()), header_extra }).collect();
    let (echo_tx, echo_rx) = crossbeam_channel::bounded::<Echo>(ECHO_QUEUE);
    let (echo_done_tx, echo_done_rx) = crossbeam_channel::bounded::<()>(1);
    let started_ns = now_ns();
    let r = Arc::new(Recorder { dir: opts.dir.clone(), run: opts.run, producer: opts.producer, keyframe_every: AtomicU32::new(cfg.accounts_keyframe_every),
        rival_venues: sample::Sampler::new(cfg.rivals_venues_sample), exec_unwatched: sample::Sampler::new(cfg.exec_unwatched_sample), disk: Mutex::new(disk::Ladder::new(&cfg)), cfg, streams, queues, tx, threads: Mutex::new(Vec::new()), closed: AtomicBool::new(false), started_ns,
        dead: Default::default(), progress: Default::default(), fatal: OnceLock::new(), echo: echo_tx, echo_done: Mutex::new(Some(echo_done_rx)),
        echo_dropped: AtomicU64::new(0), close_timeout: Mutex::new(Vec::new()), crash: Default::default(),
        close_wait_ms: AtomicU64::new(CLOSE_WAIT.as_millis() as u64),
        entries, core_lost: AtomicBool::new(false), gate: OnceLock::new(), stopper: OnceLock::new(), engine_tid: AtomicI32::new(0), runtimes: OnceLock::new(),
        udp: Mutex::new(Vec::new()), stall: Default::default(), monitor: Mutex::new(None), notes, alert_tap: OnceLock::new() });
    // the plain streams exist from the start, their headers stamped with the recorder's start (review F4, N2); WP-11's
    // experiments.jsonl only with its first line (an experiment on): a run without experiments writes the files it did
    for (i, s) in r.streams.iter().enumerate() {
        if s.spec.format.plain() && S(i as u16) != STATUS && S(i as u16) != EXPERIMENTS { let _ = r.tx[s.spec.class.idx()].send(Ctl::Open(S(i as u16), started_ns, None)); }
    }
    for (class, rx) in Class::ALL.into_iter().zip(rx) {
        let me = r.clone();
        let (done_tx, done_rx) = crossbeam_channel::bounded::<()>(1);
        let h = std::thread::Builder::new().name(format!("arbx-rec-{}", class.as_str())).spawn(move || writer::run(me, class, rx, done_tx))?;
        r.threads.lock().unwrap().push((class, h, done_rx));
    }
    let sink = opts.echo;
    std::thread::Builder::new().name("arbx-rec-echo".into()).spawn(move || echo_loop(echo_rx, sink, echo_done_tx))?;
    if opts.monitor {
        let (stop, me) = (Arc::new(AtomicBool::new(false)), r.clone());
        let s2 = stop.clone();
        let h = std::thread::Builder::new().name("arbx-rec-mon".into()).spawn(move || health::monitor(me, s2))?;
        *r.monitor.lock().unwrap() = Some((stop, h));
    }
    Ok(Rec(Some(r)))
}

impl Recorder {
    fn st(&self, s: S) -> &StreamState { &self.streams[s.0 as usize] }
    pub fn spec(&self, s: S) -> &Spec { &self.st(s).spec }
    pub fn n_streams(&self) -> usize { self.streams.len() }

    /// Hand a record to its writer: never blocks. False when it was not taken (dropped, switched off, closed). `size`:
    /// the payload bytes the queue's byte cap counts
    fn push(&self, s: S, seq: Option<u64>, size: u64, r: Record) -> bool {
        let st = self.st(s);
        if self.closed.load(Relaxed) { st.late.fetch_add(1, Relaxed); return false; }
        if !st.on.load(Relaxed) { st.suppressed.fetch_add(1, Relaxed); return false; }
        let q = &self.queues[st.spec.queue as usize];
        let d = q.depth.fetch_add(1, Relaxed) + 1;
        if d > q.cap {
            q.depth.fetch_sub(1, Relaxed);
            self.on_drop(s, seq, "queue full");
            return false;
        }
        if size > 0 {
            let b = q.bytes.fetch_add(size, Relaxed) + size;
            if b > q.byte_cap {
                q.bytes.fetch_sub(size, Relaxed);
                q.depth.fetch_sub(1, Relaxed);
                self.on_drop(s, seq, "queue byte cap");
                return false;
            }
            if b > q.bytes_hwm.load(Relaxed) { q.bytes_hwm.fetch_max(b, Relaxed); }
        }
        if d > q.hwm_iv.load(Relaxed) { q.hwm_iv.fetch_max(d, Relaxed); }
        let gap = if st.lost_flag.load(Relaxed) { st.take_lost() } else { None };
        match self.tx[st.spec.class.idx()].send(Ctl::Rec(Msg { s, gap, size, r })) {
            Ok(()) => true,
            Err(e) => {
                // the writer is gone: its thread died, or it ended at the close (review F15: then the record is late)
                q.depth.fetch_sub(1, Relaxed);
                q.bytes.fetch_sub(size, Relaxed);
                if let Ctl::Rec(m) = e.0 { if let Some(g) = m.gap { for (a, n) in g { for k in a..a + n { st.add_lost(k); } } } }
                if self.closed.load(Relaxed) { st.late.fetch_add(1, Relaxed); } else { self.on_drop(s, seq, "writer gone"); }
                false
            }
        }
    }

    fn on_drop(&self, s: S, seq: Option<u64>, why: &str) {
        let st = self.st(s);
        let n = st.dropped.fetch_add(1, Relaxed) + 1;
        if let Some(q) = seq { st.add_lost(q); }
        // the segment can no longer be reconciled: shadow for the rest of it (§1.5, F32); the next segment is live again
        if st.spec.class == Class::Core { self.core_loss(&format!("core stream {} dropped a record ({why})", st.spec.name)); }
        if s == STATUS { self.fatal(format!("a status.jsonl line was dropped ({why})")); }
        let now = now_ns();
        let last = st.last_drop_event.load(Relaxed);
        if (n == 1 || now.saturating_sub(last) >= 1_000_000_000) && st.last_drop_event.compare_exchange(last, now, Relaxed, Relaxed).is_ok() {
            let q = st.spec.queue;
            self.event("recorder_drop", "recorder", None, json!({ "stream": st.spec.name, "class": st.spec.class.as_str(), "dropped_total": n,
                "queue": q.as_str(), "queue_cap": self.queues[q as usize].cap, "seq": seq, "why": why }));
        }
    }

    /// A core stream lost a record (a drop, an I/O error, an encoder that panicked, a dead writer): the segment can no
    /// longer be reconciled, so the SendGate goes to shadow for the rest of it (`core_record_loss`, §1.5). Once
    pub(crate) fn core_loss(&self, detail: &str) {
        if self.core_lost.swap(true, Relaxed) { return; }
        let changed = self.gate.get().map(|g| g.shadow("core_record_loss", detail, true));
        if let Some(Ok(true)) = changed {
            self.event("gate_change", "recorder", None, json!({ "to": "shadow", "reason": "core_record_loss", "detail": detail }));
        }
    }

    /// The segment must not go on: status.jsonl (the supervisor's budget source) cannot be written, or the core or slow
    /// writer is gone. A stop request with reason `error` (it closes the SendGate; stop.json and the exit code 30 say
    /// so), a run.log line written directly (the slow writer may be the one gone), a stderr line and an event. Once
    pub(crate) fn fatal(&self, detail: String) {
        if self.fatal.set(detail.clone()).is_err() { return; }
        let line = format!("recorder: {detail}: stopping the segment");
        self.echo_line(true, line.clone());
        crate::control::append_line(&self.dir.join("run.log"), &format!("{} {line}", now_ns()));
        self.event("recorder_fatal", "recorder", None, json!({ "detail": detail }));
        if let Some(s) = self.stopper.get() { s.request(StopInfo::new(StopReason::Error, format!("recorder: {detail}"))); }
    }

    /// why the recorder stopped the segment, if it did
    pub fn fatal_reason(&self) -> Option<&str> { self.fatal.get().map(String::as_str) }

    /// A writer thread ended before the close (its own guard caught a panic, or the monitor found it finished): a core or
    /// slow writer stops the segment (and a core one is a core loss first); the others are an event and stay counted
    /// (their records are dropped from now on)
    pub(crate) fn writer_died(&self, class: Class, why: &str) {
        if self.closed() || self.dead[class.idx()].swap(true, Relaxed) { return; }
        let detail = format!("writer arbx-rec-{} stopped ({why})", class.as_str());
        match class {
            Class::Core => { self.core_loss(&detail); self.fatal(detail); }
            Class::Slow => self.fatal(detail),
            _ => {
                self.echo_line(true, format!("recorder: {detail}"));
                self.event("recorder_writer_dead", "recorder", None, json!({ "class": class.as_str(), "detail": detail }));
            }
        }
    }

    /// An I/O error of a writer (`op`: open, compress, write): counted per stream with the records it lost; on a core
    /// stream a core loss, on status.jsonl a stop; a `recorder_io_error` event and a stderr line (the first, then at
    /// most one a second per stream)
    pub(crate) fn io_error(&self, s: S, op: &str, err: &str, lost: u64) {
        let st = self.st(s);
        let n = st.io_errors.fetch_add(1, Relaxed) + 1;
        let lost_total = st.io_lost.fetch_add(lost, Relaxed) + lost;
        if st.spec.class == Class::Core { self.core_loss(&format!("core stream {} not written ({op}: {err})", st.spec.name)); }
        if s == STATUS { self.fatal(format!("status.jsonl not written ({op}: {err})")); }
        if self.err_event_due(st, n) {
            self.echo_line(true, format!("recorder: {} {op} failed: {err} ({n} errors, {lost_total} records lost)", st.spec.name));
            // not about events.jsonl itself: that event would be its next failure
            if s != EVENTS {
                self.event("recorder_io_error", "recorder", None, json!({ "stream": st.spec.name, "class": st.spec.class.as_str(), "op": op, "error": err,
                    "io_errors_total": n, "lost_total": lost_total }));
            }
        }
    }

    /// A record's encoder (or a task) panicked: the record is not written. Counted per stream; a core stream's is a
    /// core loss; an event and a stderr line (the first, then at most one a second per stream)
    pub(crate) fn encode_failed(&self, s: S, what: &str) {
        let st = self.st(s);
        let n = st.enc_errors.fetch_add(1, Relaxed) + 1;
        if st.spec.class == Class::Core { self.core_loss(&format!("core stream {}: a record's encoder panicked ({what})", st.spec.name)); }
        if self.err_event_due(st, n) {
            self.echo_line(true, format!("recorder: {} {what} ({n} so far)", st.spec.name));
            if s != EVENTS {
                self.event("recorder_encode_error", "recorder", None, json!({ "stream": st.spec.name, "class": st.spec.class.as_str(), "detail": what, "encode_errors_total": n }));
            }
        }
    }

    fn err_event_due(&self, st: &StreamState, n: u64) -> bool {
        let now = now_ns();
        let last = st.last_err_event.load(Relaxed);
        (n == 1 || now.saturating_sub(last) >= 1_000_000_000) && st.last_err_event.compare_exchange(last, now, Relaxed, Relaxed).is_ok()
    }

    /// a line for stdout (`err` false) or stderr, through the echo thread; never waits (a full echo queue counts it)
    pub(crate) fn echo_line(&self, err: bool, msg: String) {
        if self.echo.try_send(if err { Echo::Err(msg) } else { Echo::Out(msg) }).is_err() { self.echo_dropped.fetch_add(1, Relaxed); }
    }

    /// The writers' health (the monitor, every check): a writer thread that finished before the close died; a core or
    /// slow writer with records queued and no progress for [`STALL_LIMIT`] is stalled (a hung disk), which stops the
    /// segment (the others: an event, once). `seen`: per class, the progress count and when it last moved
    pub(crate) fn check_writers(&self, seen: &mut [(u64, std::time::Instant, bool); 5]) {
        if self.closed() { return; }
        let finished: Vec<Class> = self.threads.lock().unwrap_or_else(|e| e.into_inner()).iter().filter(|t| t.1.is_finished()).map(|t| t.0).collect();
        for c in finished { self.writer_died(c, "its thread ended"); }
        let now = std::time::Instant::now();
        for c in Class::ALL {
            let p = self.progress[c.idx()].load(Relaxed);
            let queued: u64 = c.queues().iter().map(|q| self.queues[*q as usize].depth.load(Relaxed)).sum();
            let e = &mut seen[c.idx()];
            if p != e.0 || queued == 0 { *e = (p, now, false); continue; }
            if e.2 || now.duration_since(e.1) < STALL_LIMIT { continue; }
            e.2 = true;
            let detail = format!("writer arbx-rec-{} made no progress for {} s with {queued} records queued", c.as_str(), STALL_LIMIT.as_secs());
            match c {
                Class::Core => { self.core_loss(&detail); self.fatal(detail); }
                Class::Slow => self.fatal(detail),
                _ => {
                    self.echo_line(true, format!("recorder: {detail}"));
                    self.event("recorder_writer_stalled", "recorder", None, json!({ "class": c.as_str(), "queued": queued, "detail": detail }));
                }
            }
        }
    }

    /// test hook: how long `close` waits for the writers
    pub fn set_close_wait(&self, d: Duration) { self.close_wait_ms.store(d.as_millis() as u64, Relaxed); }

    /// test hook: make a class's writer panic outside a record (a writer thread that dies)
    pub fn crash_writer(&self, class: Class) { self.crash[class.idx()].store(true, Relaxed); }
    fn crash_requested(&self, class: Class) -> bool { self.crash[class.idx()].swap(false, Relaxed) }

    /// events.jsonl (§4.6)
    pub fn event(&self, kind: &'static str, subsystem: &'static str, feed: Option<u16>, detail: Value) {
        if let Some(tap) = self.alert_tap.get() { tap(kind, subsystem, feed, &detail); }
        let t = now_ns();
        self.push(EVENTS, None, 0, Record::Json(json!({ "t_ns": t, "kind": kind, "subsystem": subsystem, "feed": feed, "detail": detail })));
    }

    pub fn closed(&self) -> bool { self.closed.load(Relaxed) }

    /// Wait until every writer has written what was queued before this call and ended its frames (tests, simcheck)
    pub fn sync(&self) {
        let mut waits = Vec::new();
        for tx in &self.tx {
            let (a, b) = crossbeam_channel::bounded(1);
            if tx.send(Ctl::Sync(a)).is_ok() { waits.push(b); }
        }
        for w in waits { let _ = w.recv_timeout(std::time::Duration::from_secs(60)); }
    }

    /// Drain every queue, end every frame, close every file, write the final manifest. Records emitted after this are
    /// counted as `late` and not written. The wait is bounded ([`CLOSE_WAIT`]; review F6): a writer stuck on a hung disk
    /// is left behind and named in the manifest (`close_timeout`). What the queues still count once the writers are
    /// done was accepted but never written (`lost_at_close`, review F15). Idempotent
    pub fn close(&self) {
        if self.closed.swap(true, Relaxed) { return; }
        if let Some((stop, h)) = self.monitor.lock().unwrap_or_else(|e| e.into_inner()).take() { stop.store(true, Relaxed); let _ = h.join(); }
        for tx in &self.tx { let _ = tx.send(Ctl::Close); }
        for c in &self.stall { c.store(false, Relaxed); }
        let threads: Vec<_> = std::mem::take(&mut *self.threads.lock().unwrap_or_else(|e| e.into_inner()));
        let deadline = std::time::Instant::now() + Duration::from_millis(self.close_wait_ms.load(Relaxed));
        for (class, h, done) in threads {
            match done.recv_deadline(deadline) {
                Err(crossbeam_channel::RecvTimeoutError::Timeout) => self.close_timeout.lock().unwrap_or_else(|e| e.into_inner()).push(class.as_str()),
                _ => { let _ = h.join(); }
            }
        }
        for q in &self.queues { q.lost_at_close.store(q.depth.load(Relaxed), Relaxed); }
        // the echo thread prints what it holds, then ends (not waited for long: stdout may be blocked)
        if self.echo.try_send(Echo::End).is_ok() {
            if let Some(d) = self.echo_done.lock().unwrap_or_else(|e| e.into_inner()).take() { let _ = d.recv_timeout(Duration::from_secs(1)); }
        }
        let _ = manifest::write(self, true);
    }

    /// test hook: stop (or restart) a class's writer reading its queue
    pub fn stall(&self, class: Class, on: bool) { self.stall[class.idx()].store(on, Relaxed); }
    fn stalled(&self, class: Class) -> bool { self.stall[class.idx()].load(Relaxed) }

    /// the stream's queue depth now (tests)
    pub fn depth(&self, s: S) -> u64 { self.queues[self.st(s).spec.queue as usize].depth.load(Relaxed) }

    /// no core record lost, the recorder did not stop the segment, and it is not closed (a record emitted after `close` is
    /// not written: an attempt could not be recorded). The send check's `recorder_ok`; three atomic loads
    pub fn core_ok(&self) -> bool { !self.core_lost.load(Relaxed) && self.fatal.get().is_none() && !self.closed() }

    /// a whole-run view for status.jsonl `recorder` and `health.recorder_ok`
    pub fn stats(&self) -> RecStats {
        let per = |f: &dyn Fn(&StreamState) -> u64| -> Vec<(String, u64)> { self.streams.iter().map(|s| (s.spec.name.clone(), f(s))).collect() };
        RecStats {
            dropped: per(&|s| s.dropped.load(Relaxed)),
            suppressed: per(&|s| s.suppressed.load(Relaxed)),
            io_errors: per(&|s| s.io_errors.load(Relaxed)),
            io_lost: per(&|s| s.io_lost.load(Relaxed)),
            encode_errors: per(&|s| s.enc_errors.load(Relaxed)),
            queue_hwm: Queue::ALL.iter().map(|q| (q.as_str(), self.queue_hwm(*q))).collect(),
            writers_dead: Class::ALL.iter().filter(|c| self.dead[c.idx()].load(Relaxed)).map(|c| c.as_str()).collect(),
            echo_dropped: self.echo_dropped.load(Relaxed),
            core_ok: !self.core_lost.load(Relaxed) && self.fatal.get().is_none(),
        }
    }

    /// the queue's high-water mark since the start (the interval mark folded in)
    fn queue_hwm(&self, q: Queue) -> u64 {
        let qs = &self.queues[q as usize];
        qs.hwm.load(Relaxed).max(qs.hwm_iv.load(Relaxed))
    }

    /// the interval high-water mark, reset to the depth now (resources.jsonl `recorder_queues.*.hwm_delta`)
    fn take_queue_hwm_iv(&self, q: Queue) -> (u64, u64) {
        let qs = &self.queues[q as usize];
        let now = qs.depth.load(Relaxed);
        let iv = qs.hwm_iv.swap(now, Relaxed);
        qs.hwm.fetch_max(iv, Relaxed);
        (now, iv)
    }

    /// Switch streams off (the disk budget): their records are counted as `suppressed`
    pub(crate) fn switch_off(&self, pred: impl Fn(&Spec) -> bool) -> Vec<String> {
        let mut v = Vec::new();
        for s in &self.streams { if pred(&s.spec) && s.on.swap(false, Relaxed) { v.push(s.spec.name.clone()); } }
        v
    }
}

/// status.jsonl `recorder` and the monitor's view. Per stream: `dropped` (queue full, byte cap, writer gone),
/// `suppressed` (the disk ladder), `io_errors` (failed opens, compressions, writes), `io_lost` (records they lost),
/// `encode_errors` (records whose encoder panicked). `core_ok`: no core record lost and the recorder did not stop the
/// segment (status.jsonl `health.recorder_ok`)
#[derive(Clone, Debug, Default)]
pub struct RecStats {
    pub dropped: Vec<(String, u64)>,
    pub suppressed: Vec<(String, u64)>,
    pub io_errors: Vec<(String, u64)>,
    pub io_lost: Vec<(String, u64)>,
    pub encode_errors: Vec<(String, u64)>,
    pub queue_hwm: Vec<(&'static str, u64)>,
    pub writers_dead: Vec<&'static str>,
    pub echo_dropped: u64,
    pub core_ok: bool,
}

/// The echo thread: echoed lines to stdout / stderr (or the test sink), write errors ignored, until `End`
fn echo_loop(rx: crossbeam_channel::Receiver<Echo>, mut sink: Option<Box<dyn Write + Send>>, done: crossbeam_channel::Sender<()>) {
    crate::runtime::nice_this_thread(crate::runtime::BG_NICE);
    for m in rx.iter() {
        let (err, line) = match m { Echo::End => break, Echo::Out(l) => (false, l), Echo::Err(l) => (true, l) };
        match sink.as_mut() {
            Some(w) => { let _ = writeln!(w, "{line}"); let _ = w.flush(); }
            None if err => { let _ = writeln!(std::io::stderr().lock(), "{line}"); }
            None => { let _ = writeln!(std::io::stdout().lock(), "{line}"); }
        }
    }
    let _ = done.send(());
}

/// a line on stdout / stderr, write errors ignored (arb-lab's `println!` / `eprintln!` panicked on them; review F2)
pub fn out_line(line: &str) { let _ = writeln!(std::io::stdout().lock(), "{line}"); }
pub fn err_line(line: &str) { let _ = writeln!(std::io::stderr().lock(), "{line}"); }

impl Rec {
    /// records nothing
    pub fn off() -> Rec { Rec(None) }
    pub fn is_on(&self) -> bool { self.0.is_some() }
    pub fn recorder(&self) -> Option<&Arc<Recorder>> { self.0.as_ref() }
    pub fn dir(&self) -> Option<&Path> { self.0.as_deref().map(|r| r.dir.as_path()) }

    /// Hand `r` to stream `s`'s writer; never blocks. False when it was not taken
    #[inline]
    pub fn emit(&self, s: S, r: Record) -> bool { match &self.0 { Some(x) => { let n = r.size(); x.push(s, None, n, r) } None => false } }

    /// `emit` for a record whose payload the queue's byte cap must count (a closure holding `bytes` of data)
    #[inline]
    pub fn emit_sized(&self, s: S, bytes: u64, r: Record) -> bool { match &self.0 { Some(x) => x.push(s, None, bytes, r), None => false } }

    #[inline]
    pub fn json(&self, s: S, v: Value) -> bool { self.emit(s, Record::Json(v)) }

    /// a replay stream's next sequence number (accounts `aseq`, journal `seq`): taken before the record is made, so the
    /// producer can carry it
    pub fn next_seq(&self, s: S) -> u64 { self.0.as_ref().map_or(0, |x| x.st(s).seq.fetch_add(1, Relaxed)) }

    /// a replay record with its sequence number: if it is dropped, the next record of the stream carries a GAP
    #[inline]
    pub fn emit_seq(&self, s: S, seq: u64, r: Record) -> bool { match &self.0 { Some(x) => { let n = r.size(); x.push(s, Some(seq), n, r) } None => false } }

    /// `emit_seq` for a record whose payload (`bytes`, held by its closure) the queue's byte cap must count (accounts.bin
    /// records carry the account's data)
    #[inline]
    pub fn emit_seq_sized(&self, s: S, seq: u64, bytes: u64, r: Record) -> bool { match &self.0 { Some(x) => x.push(s, Some(seq), bytes, r), None => false } }

    /// events.jsonl (§4.6, kinds in A.6)
    pub fn event(&self, kind: &'static str, subsystem: &'static str, feed: Option<u16>, detail: Value) {
        if let Some(x) = &self.0 { x.event(kind, subsystem, feed, detail); }
    }

    /// A diagnostic line arb-lab printed to stderr: an `events.jsonl` record of kind `log` (§4.5: reports never parse
    /// `.out`) from the slow writer, and the same text on stderr (the segment's `.out`) from the echo thread
    pub fn log(&self, subsystem: &'static str, msg: String) {
        match &self.0 {
            Some(x) if !x.closed() => {
                let t = now_ns();
                x.echo_line(true, msg.clone());
                x.push(EVENTS, None, 0, Record::enc(move |o| {
                    let _ = serde_json::to_writer(o, &json!({ "t_ns": t, "kind": "log", "subsystem": subsystem, "feed": null, "detail": { "msg": msg } }));
                }));
            }
            _ => err_line(&msg),
        }
    }

    /// A run.log line (`<t_ns> <message>`) from the slow writer, and the same text on stdout from the echo thread (the
    /// engine thread writes nothing; a failing or blocked stdout stops neither). Without a recorder: stdout only
    pub fn say(&self, msg: impl Into<String>) {
        let msg = msg.into();
        let t = now_ns();
        match &self.0 {
            Some(x) if !x.closed() => {
                x.echo_line(false, msg.clone());
                x.push(RUN_LOG, None, 0, Record::enc(move |o| { let _ = std::io::Write::write_fmt(o, format_args!("{t} {msg}")); }));
            }
            // closed (the end of the run): straight to the file, one write per line, as control.rs does
            Some(x) => { out_line(&msg); crate::control::append_line(&x.dir.join("run.log"), &format!("{t} {msg}")); }
            None => out_line(&msg),
        }
    }

    /// Work for the slow writer (file writes the engine must not do itself). Without a recorder it runs here
    pub fn task(&self, f: impl FnOnce() + Send + 'static) {
        match &self.0 {
            Some(x) if !x.closed() => { x.push(RUN_LOG, None, 0, Record::Task(Box::new(f))); }
            _ => f(),
        }
    }

    /// Open stream `s`'s file now and wait (at most 10 s) until it is: status.jsonl when the engine starts, so that the
    /// file exists (with its header) before anything can be sent (the supervisor reads that as "the engine started";
    /// deploy/run-w.sh `spent`). An error when it cannot be opened
    pub fn open_now(&self, s: S) -> Result<()> {
        let Some(x) = &self.0 else { return Ok(()) };
        let (a, b) = crossbeam_channel::bounded(1);
        x.tx[x.spec(s).class.idx()].send(Ctl::Open(s, now_ns(), Some(a))).map_err(|_| anyhow::anyhow!("the {} writer is gone", x.spec(s).class.as_str()))?;
        match b.recv_timeout(Duration::from_secs(10)) {
            Ok(Ok(())) => Ok(()),
            Ok(Err(e)) => anyhow::bail!("{}: {e}", x.spec(s).file_name(0)),
            Err(_) => anyhow::bail!("{}: the {} writer did not answer in 10 s", x.spec(s).file_name(0), x.spec(s).class.as_str()),
        }
    }

    /// Give stream `s` its per-file encoder state ([`FileState`]; review F16). Before its first `Record::Stateful`
    /// (records sent after this call, from any thread that saw it return, find it installed)
    pub fn set_file_state(&self, s: S, state: Box<dyn FileState>) {
        if let Some(x) = &self.0 { let _ = x.tx[x.spec(s).class.idx()].send(Ctl::State(s, state)); }
    }

    /// the entries-<feed> stream of an archived feed
    pub fn entries(&self, feed: u16) -> Option<S> { self.0.as_ref()?.entries.iter().find(|e| e.0 == feed).map(|e| e.1) }

    /// accounts.bin keyframe interval now (WP-03's encoder reads it per record)
    pub fn accounts_keyframe_every(&self) -> u32 { self.0.as_ref().map_or(64, |x| x.keyframe_every.load(Relaxed)) }

    /// A closed SendGate on a core drop, and the disk budget's last step (shadow, then stop with `disk_budget`)
    pub fn bind_session(&self, gate: Arc<SendGate>, stopper: Arc<Stopper>) {
        let Some(x) = &self.0 else { return };
        let _ = x.gate.set(gate.clone());
        let _ = x.stopper.set(stopper.clone());
        // a loss or a fault before the binding still closes the gate
        if x.core_lost.load(Relaxed) && gate.shadow("core_record_loss", "a core record was lost before the session was bound", true) == Ok(true) {
            x.event("gate_change", "recorder", None, json!({ "to": "shadow", "reason": "core_record_loss", "detail": "a core record was lost before the session was bound" }));
        }
        if let Some(f) = x.fatal.get() { stopper.request(StopInfo::new(StopReason::Error, format!("recorder: {f}"))); }
    }

    /// the runtimes resources.jsonl reports on
    pub fn set_runtimes(&self, hot: tokio::runtime::Handle, bg: tokio::runtime::Handle) { if let Some(x) = &self.0 { let _ = x.runtimes.set((hot, bg)); } }

    /// the engine thread (resources.jsonl `engine_cpu_ms_delta`)
    pub fn set_engine_tid(&self, tid: i32) { if let Some(x) = &self.0 { x.engine_tid.store(tid, Relaxed); } }

    /// follow the kernel's drop count of the UDP socket on `port` into `counter` (every 10 s, monitor thread)
    pub fn watch_udp(&self, port: u16, counter: Arc<AtomicU64>) { if let Some(x) = &self.0 { x.udp.lock().unwrap().push((port, counter)); } }

    pub fn stats(&self) -> Option<RecStats> { self.0.as_ref().map(|x| x.stats()) }
    /// the recorder is healthy (`Recorder::core_ok`); false without a recorder: nothing could be recorded (PLAN WP-05: a
    /// send needs a healthy recorder)
    pub fn core_ok(&self) -> bool { self.0.as_ref().is_some_and(|x| x.core_ok()) }

    /// meta.json `streams`: every stream this recorder writes, with its schema
    pub fn streams_json(&self) -> Value {
        let mut m = serde_json::Map::new();
        if let Some(x) = &self.0 { for s in &x.streams { m.insert(s.spec.name.clone(), json!(s.spec.schema)); } }
        Value::Object(m)
    }

    /// Plan addendum I-9 (WP-08): whether rivals.jsonl writes the `why = venues` row of the transaction `sig`: 1 in
    /// `[record] rivals_venues_sample`, chosen by the signature ([`sample::keep_1_in`]: a replay keeps the same rows),
    /// counted (manifest.json `sampling.rivals_venues`). Some(the counts, which the row carries as `sample`) when it is
    /// written; None when it is left out, or when nothing records
    pub fn sample_rival_venues(&self, sig: &[u8]) -> Option<sample::Kept> { self.0.as_ref()?.rival_venues.take(sig) }

    /// WP-20: show every events.jsonl event to the alerts (once; a tap must never wait)
    pub fn set_alert_tap(&self, tap: AlertTap) { if let Some(x) = &self.0 { let _ = x.alert_tap.set(tap); } }
    /// FT-000 (S1-5): whether exec.jsonl writes the record of the transaction `sig`, which touches no watched account:
    /// 1 in `[record] exec_unwatched_sample`, by the signature (I-9's rule), counted (manifest.json
    /// `sampling.exec_unwatched`). Some(the counts the record carries as `sample`), None when it is left out
    pub fn sample_exec_unwatched(&self, sig: &[u8]) -> Option<sample::Kept> { self.0.as_ref()?.exec_unwatched.take(sig) }

    pub fn sync(&self) { if let Some(x) = &self.0 { x.sync(); } }
    pub fn close(&self) { if let Some(x) = &self.0 { x.close(); } }
}

// ------------------------------------------------------------------ readers (tests, simcheck, tools)

/// Every complete zstd frame of a file, decompressed and concatenated; a trailing incomplete frame (a write in
/// progress) is left out. Returns (bytes, trailing bytes ignored)
pub fn decode_zst(path: &Path) -> Result<(Vec<u8>, usize)> {
    let data = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
    decode_frames(&data)
}

pub fn decode_frames(data: &[u8]) -> Result<(Vec<u8>, usize)> {
    let mut out = Vec::new();
    let mut pos = 0;
    while pos < data.len() {
        let rest = &data[pos..];
        let Ok(n) = zstd::zstd_safe::find_frame_compressed_size(rest) else { break };
        if n == 0 || n > rest.len() { break; }
        let size = zstd::zstd_safe::get_frame_content_size(&rest[..n]).ok().flatten().unwrap_or(64 << 20) as usize;
        out.extend(zstd::bulk::decompress(&rest[..n], size).context("a zstd frame")?);
        pos += n;
    }
    Ok((out, data.len() - pos))
}

/// The files of a stream in a directory, in rotation order (`<name>.NNN.<ext>.zst`, `<name>.<ext>.zst`, `<name>.<ext>`)
pub fn stream_files(dir: &Path, name: &str) -> Vec<PathBuf> {
    let mut v: Vec<(u32, PathBuf)> = std::fs::read_dir(dir).into_iter().flatten().flatten().filter_map(|e| {
        let f = e.file_name().to_string_lossy().into_owned();
        let rest = f.strip_prefix(name)?.strip_prefix('.')?;
        let seq = match rest.split('.').next()? { s if s.len() == 3 && s.bytes().all(|b| b.is_ascii_digit()) => s.parse().ok()?, "jsonl" | "log" | "bin" => 0, _ => return None };
        Some((seq, e.path()))
    }).collect();
    v.sort();
    v.into_iter().map(|x| x.1).collect()
}

/// A stream's bytes, every file in order (decompressed); each file starts with its header
pub fn read_files(dir: &Path, name: &str) -> Result<Vec<Vec<u8>>> {
    stream_files(dir, name).iter().map(|p| if p.extension().is_some_and(|e| e == "zst") { decode_zst(p).map(|x| x.0) } else { std::fs::read(p).map_err(Into::into) }).collect()
}

/// A JSON-lines stream's records (headers checked and skipped)
pub fn read_jsonl(dir: &Path, name: &str) -> Result<Vec<Value>> {
    let mut out = Vec::new();
    for bytes in read_files(dir, name)? {
        for (i, l) in bytes.split(|b| *b == b'\n').filter(|l| !l.is_empty()).enumerate() {
            let v: Value = serde_json::from_slice(l).with_context(|| format!("{name}: line {i}"))?;
            if i == 0 && v["schema"].as_str().is_some_and(|s| s.starts_with("arbx.")) && v.get("file_seq").is_some() { continue; }
            out.push(v);
        }
    }
    Ok(out)
}

/// A text stream's lines (the `#` header lines left out)
pub fn read_text(dir: &Path, name: &str) -> Result<Vec<String>> {
    let mut out = Vec::new();
    for bytes in read_files(dir, name)? {
        for l in String::from_utf8_lossy(&bytes).lines() { if !l.is_empty() && !l.starts_with('#') { out.push(l.to_string()); } }
    }
    Ok(out)
}

/// The error of an executed transaction from its bincode TransactionError: `ix{i}:custom:0x{code}`, `ix{i}:ie{variant}`
/// or `tx{variant}` (exec.jsonl `err`)
pub fn tx_error(b: &[u8]) -> String {
    let u32_at = |i: usize| b.get(i..i + 4).map(|s| u32::from_le_bytes(s.try_into().unwrap()));
    match u32_at(0) {
        Some(8) => {
            let ix = b.get(4).copied().unwrap_or(0);
            match u32_at(5) {
                Some(25) => format!("ix{ix}:custom:0x{:x}", u32_at(9).unwrap_or(0)),
                Some(v) => format!("ix{ix}:ie{v}"),
                None => format!("ix{ix}"),
            }
        }
        Some(v) => format!("tx{v}"),
        None => "?".into(),
    }
}

/// Review WP-08 #12: every stream constant is its own row's index, name by name, and every row has one. Lanes append
/// their streams at the same ids (WP-03b's wallet, slotidx and txfetch, WP-04's commits, decisions and alts take 28-30 as
/// WP-08's validators did): a merge that numbers two streams alike, or leaves a row without its constant in this list,
/// fails here
#[cfg(test)]
mod stream_ids {
    use super::*;

    #[test]
    fn stream_ids_name_their_rows() {
        let all = [(ATTEMPTS, "attempts"), (COPIES, "copies"), (BUNDLES, "bundles"), (OUTCOMES, "outcomes"), (ACCOUNTS, "accounts"), (JOURNAL, "journal"),
            (EXEC, "exec"), (TXARR, "txarr"), (ARRIVALS, "arrivals"), (MOVES, "moves"), (POH, "poh"), (SLOTS_FEED, "slots-feed"), (ALTS_FINAL, "alts-final"),
            (TRIGGERS, "triggers"), (PREDICTIONS, "predictions"), (CAPS, "caps"), (SIMS, "sims"), (OPPORTUNITIES, "opportunities"), (RIVALS, "rivals"),
            (STATUS, "status"), (EVENTS, "events"), (FEEDHEALTH, "feedhealth"), (RESOURCES, "resources"), (KEEPALIVE, "keepalive"), (RUN_LOG, "run"),
            (SLOTS, "slots"), (BLOCKS, "blocks"), (LEADERS, "leaders"), (COMMITS, "commits"), (DECISIONS, "decisions"), (ALTS, "alts"),
            (WALLET, "wallet"), (SLOTIDX, "slotidx"), (TXFETCH, "txfetch"), (VALIDATORS, "validators"), (LEDGER, "ledger"), (SNAPSHOTS, "snapshots"),
            (RECON, "recon"), (EXPERIMENTS, "experiments")];
        for (s, name) in all { assert_eq!(STATIC[s.0 as usize].0, name, "stream id {}", s.0); }
        let mut ids: Vec<u16> = all.iter().map(|x| x.0 .0).collect();
        ids.sort_unstable();
        ids.dedup();
        assert_eq!((ids.len(), all.len()), (STATIC.len(), STATIC.len()), "one constant per row, no two alike");
        assert_eq!((id_of("attempts"), id_of("leaders"), id_of("txfetch"), id_of("validators")), (0, 27, 33, 34));
    }
}

#[cfg(test)]
mod tests;

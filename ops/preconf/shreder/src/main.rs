//! shreder_rec — records Shreder `SubscribeBinaryTransactions` streams (preconf=true and/or the normal
//! shred-reconstructed Binary stream) to disk with a local CLOCK_REALTIME receive stamp per message.
//! Read-only measurement: it never signs or sends anything. Endpoint/token are never printed.
//!
//! Per stream it writes (in --out):
//!   <name>_<YYYYMMDD_HH>_<part>.rec.gz   every message (gzip members, one per flush) — the dataset
//!   <name>_<YYYYMMDD_HH>_<part>.idx.jsonl one line per gzip member (offsets, seq/time/slot ranges)
//!   <name>_<YYYYMMDD_HH>.jsonl            "pump view": messages whose static keys hold the pump.fun program
//!                                          (all messages for server-filtered streams), JSON per line
//!   events.jsonl, rec.log                 connection events and status every --status-secs
//! HH is the PKT (UTC+5) hour of the receive time. See README.md for the record layouts.

use shreder_rec::pb;
use shreder_rec::txparse::{self, decode_pubkey, PUMP_AMM_PROGRAM, PUMP_PROGRAM};
use shreder_rec::util::{self, now_ns, Access};

use flate2::write::GzEncoder;
use flate2::Compression;
use std::collections::HashMap;
use std::fs::{File, OpenOptions};
use std::io::{BufWriter, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicI64, AtomicU64, Ordering::Relaxed};
use std::sync::mpsc::{sync_channel, Receiver, RecvTimeoutError, SyncSender, TrySendError};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};
use tokio_stream::StreamExt;

const VERSION: &str = "shreder_rec 0.2 (2026-10-27)";

const BROAD: &[&str] = &[
    PUMP_PROGRAM,
    PUMP_AMM_PROGRAM,
    "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", // Raydium AMM v4
    "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", // Raydium CPMM
    "CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", // Raydium CLMM
    "LanMV9sAd7wArD4vJFi2qDdfnVhFxYSUg6eADduJ3uj", // Raydium LaunchLab
    "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", // Meteora DLMM
    "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", // Meteora DAMM v2
    "whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", // Orca Whirlpool
    "JUP6LkbZbjS1jKKwapdHNy74zcZ3tQUnwnUoqQhTqcR4j", // Jupiter v6
];
const JITO_TIPS: &[&str] = &[
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
];

// ------------------------------------------------------------------------------------------------
// config
// ------------------------------------------------------------------------------------------------

#[derive(Clone, Debug)]
struct FilterSpec {
    label: String,
    /// empty = no account filter (whole stream)
    accounts: Vec<String>,
}

impl FilterSpec {
    fn is_all(&self) -> bool {
        self.accounts.is_empty()
    }
}

fn resolve_filter(s: &str) -> Result<FilterSpec, String> {
    let mut acc: Vec<String> = Vec::new();
    for tok in s.split([',', '+']).map(str::trim).filter(|t| !t.is_empty()) {
        match tok {
            "all" | "none" => {}
            "pump" => acc.push(PUMP_PROGRAM.into()),
            "amm" => acc.push(PUMP_AMM_PROGRAM.into()),
            "broad" => {
                acc.extend(BROAD.iter().map(|s| s.to_string()));
                acc.extend(JITO_TIPS.iter().map(|s| s.to_string()));
            }
            "jito" => acc.extend(JITO_TIPS.iter().map(|s| s.to_string())),
            k => {
                if decode_pubkey(k).is_none() {
                    return Err(format!("unknown filter token '{k}' (all|pump|amm|broad|jito|<base58 key>)"));
                }
                acc.push(k.to_string())
            }
        }
    }
    acc.sort();
    acc.dedup();
    Ok(FilterSpec { label: s.to_string(), accounts: acc })
}

#[derive(Clone, Debug)]
struct StreamSpec {
    name: String,
    preconf: bool,
    /// one subscription carrying BOTH sources (filters "pre" preconf=true + "bin" preconf=false), routed by update.preconf
    both: bool,
    filter: FilterSpec,
}

const VOTE_PROGRAM: &str = "Vote111111111111111111111111111111111111111";

struct Cfg {
    out: PathBuf,
    streams: Vec<StreamSpec>,
    required: bool,
    exclude_votes: bool,
    fallback: Option<FilterSpec>,
    run_secs: Option<f64>,
    status_secs: u64,
    flush_ms: u64,
    raw: bool,
    gz_level: u32,
    part_max_mb: u64,
    view_amm: bool,
    jsonl_raw: bool,
    connect_timeout_ms: u64,
    stall_secs: u64,
    empty_fallback_secs: u64,
    queue: usize,
    threads: usize,
    disk_max_pct: f64,
    quiet: bool,
    key: Option<PathBuf>,
    endpoint: Option<String>,
    check_only: bool,
}

fn usage() -> ! {
    eprintln!(
        "{VERSION}
usage: shreder_rec [options]
  --out DIR               output dir (default ./data)
  --stream NAME:pre|bin|both:FILTER   repeatable; FILTER = all | pump | amm | broad | jito | <base58>[,..]
                          default: --stream pre:pre:all --stream bin:bin:all (two connections).
                          NAME:both:FILTER = ONE subscription with both sources, routed into the pre/bin files
                          (use only if the server allows a single connection; one TCP stream couples their timing)
  --exclude-votes         account_exclude=[Vote program] on unfiltered Binary (non-preconf) subscriptions
  --required              use account_required instead of account_include for list filters
  --fallback FILTER       filter to switch an 'all' stream to if the server rejects it / sends nothing (default broad; 'off' to disable)
  --minutes M | --until HH:MM (PKT)   stop condition (default: run until SIGINT/SIGTERM)
  --status-secs N         status interval (default 30)
  --flush-ms N            flush interval = gzip member length (default 1000)
  --no-raw                do not write the .rec.gz dataset (pump view + events only)
  --gz-level N            gzip level 0-9 (default 1)
  --part-mb N             rotate a .rec.gz part after N MB compressed (default 2048)
  --view-amm              pump view also includes pump AMM txs
  --jsonl-raw             pump view lines also carry the raw tx base64 (field x)
  --key FILE              access file (endpoint/token); default /root/shreder.key if present, else none
  --endpoint URL          override endpoint (never printed)
  --connect-timeout-ms N  (default 5000)   --stall-secs N (default 60)   --empty-fallback-secs N (default 45; x2 for preconf streams)
  --queue N               per-stream writer queue (default 200000 msgs; overflow is counted as dropped)
  --threads N             tokio worker threads (default 2)
  --disk-max-pct P        pause the raw dataset above this disk use% (default 80)
  --check                 connect + subscribe each stream once, print the first messages' summary, exit
  --quiet                 no stdout status (rec.log still written)"
    );
    std::process::exit(2)
}

fn parse_args() -> Cfg {
    let mut a = std::env::args().skip(1);
    let mut c = Cfg {
        out: PathBuf::from("data"),
        streams: vec![],
        required: false,
        exclude_votes: false,
        fallback: Some(resolve_filter("broad").unwrap()),
        run_secs: None,
        status_secs: 30,
        flush_ms: 1000,
        raw: true,
        gz_level: 1,
        part_max_mb: 2048,
        view_amm: false,
        jsonl_raw: false,
        connect_timeout_ms: 5000,
        stall_secs: 60,
        empty_fallback_secs: 45,
        queue: 200_000,
        threads: 2,
        disk_max_pct: 80.0,
        quiet: false,
        key: None,
        endpoint: None,
        check_only: false,
    };
    let mut until: Option<String> = None;
    let mut minutes: Option<f64> = None;
    while let Some(k) = a.next() {
        let mut v = || a.next().unwrap_or_else(|| usage());
        match k.as_str() {
            "--out" => c.out = PathBuf::from(v()),
            "--stream" => {
                let s = v();
                let parts: Vec<&str> = s.splitn(3, ':').collect();
                if parts.len() != 3 || !(parts[1] == "pre" || parts[1] == "bin" || parts[1] == "both") || parts[0].is_empty() {
                    eprintln!("bad --stream '{s}' (want NAME:pre|bin|both:FILTER)");
                    usage();
                }
                let filter = resolve_filter(parts[2]).unwrap_or_else(|e| {
                    eprintln!("{e}");
                    usage()
                });
                c.streams.push(StreamSpec { name: parts[0].to_string(), preconf: parts[1] == "pre", both: parts[1] == "both", filter });
            }
            "--required" => c.required = true,
            "--exclude-votes" => c.exclude_votes = true,
            "--fallback" => {
                let s = v();
                c.fallback = if s == "off" { None } else { Some(resolve_filter(&s).unwrap_or_else(|e| { eprintln!("{e}"); usage() })) };
            }
            "--minutes" => minutes = Some(v().parse().unwrap_or_else(|_| usage())),
            "--until" => until = Some(v()),
            "--status-secs" => c.status_secs = v().parse().unwrap_or_else(|_| usage()),
            "--flush-ms" => c.flush_ms = v().parse().unwrap_or_else(|_| usage()),
            "--no-raw" => c.raw = false,
            "--gz-level" => c.gz_level = v().parse().unwrap_or_else(|_| usage()),
            "--part-mb" => c.part_max_mb = v().parse().unwrap_or_else(|_| usage()),
            "--view-amm" => c.view_amm = true,
            "--jsonl-raw" => c.jsonl_raw = true,
            "--key" => c.key = Some(PathBuf::from(v())),
            "--endpoint" => c.endpoint = Some(v()),
            "--connect-timeout-ms" => c.connect_timeout_ms = v().parse().unwrap_or_else(|_| usage()),
            "--stall-secs" => c.stall_secs = v().parse().unwrap_or_else(|_| usage()),
            "--empty-fallback-secs" => c.empty_fallback_secs = v().parse().unwrap_or_else(|_| usage()),
            "--queue" => c.queue = v().parse().unwrap_or_else(|_| usage()),
            "--threads" => c.threads = v().parse().unwrap_or_else(|_| usage()),
            "--disk-max-pct" => c.disk_max_pct = v().parse().unwrap_or_else(|_| usage()),
            "--check" => c.check_only = true,
            "--quiet" => c.quiet = true,
            "-h" | "--help" => usage(),
            _ => {
                eprintln!("unknown arg {k}");
                usage()
            }
        }
    }
    if c.streams.is_empty() {
        c.streams.push(StreamSpec { name: "pre".into(), preconf: true, both: false, filter: resolve_filter("all").unwrap() });
        c.streams.push(StreamSpec { name: "bin".into(), preconf: false, both: false, filter: resolve_filter("all").unwrap() });
    }
    let mut names: Vec<&str> = c.streams.iter().flat_map(|s| if s.both { vec!["pre", "bin"] } else { vec![s.name.as_str()] }).collect();
    let n_names = names.len();
    names.sort();
    names.dedup();
    if names.len() != n_names {
        eprintln!("duplicate stream names (a NAME:both stream writes the files of streams pre and bin)");
        usage();
    }
    if let Some(m) = minutes {
        c.run_secs = Some(m * 60.0);
    }
    if let Some(u) = until {
        match util::secs_until_pkt(&u, now_ns()) {
            Ok(s) => c.run_secs = Some(c.run_secs.map(|x| x.min(s)).unwrap_or(s)),
            Err(e) => {
                eprintln!("{e}");
                usage()
            }
        }
    }
    if c.key.is_none() {
        let d = PathBuf::from("/root/shreder.key");
        if d.exists() {
            c.key = Some(d);
        }
    }
    c.threads = c.threads.max(1);
    c
}

// ------------------------------------------------------------------------------------------------
// shared state
// ------------------------------------------------------------------------------------------------

#[derive(Default)]
struct Stats {
    n: AtomicU64,
    n_view: AtomicU64,
    raw_bytes: AtomicU64,
    gz_bytes: AtomicU64,
    last_slot: AtomicU64,
    parse_err: AtomicU64,
    dropped: AtomicU64,
    reconnects: AtomicU64,
    connected: AtomicBool,
    epoch: AtomicU64,
    last_rx: AtomicI64,
    fallback_active: AtomicBool,
}

#[derive(Default)]
struct Matcher {
    map: HashMap<u64, (i64, bool)>,
    deltas: Vec<i64>,
}

impl Matcher {
    fn observe(&mut self, key: u64, t: i64, is_pre: bool) {
        match self.map.get(&key).copied() {
            Some((t0, was_pre)) if was_pre != is_pre => {
                self.map.remove(&key);
                let (tp, tb) = if is_pre { (t, t0) } else { (t0, t) };
                self.deltas.push(tb - tp);
            }
            Some(_) => {} // duplicate in the same stream: keep the earliest
            None => {
                self.map.insert(key, (t, is_pre));
            }
        }
    }
}

struct Shared {
    out: PathBuf,
    events: Mutex<File>,
    log: Mutex<File>,
    secrets: Vec<String>,
    raw_paused: AtomicBool,
    quiet: bool,
    /// filter label -> matcher between the pre and bin streams that share that filter
    matchers: HashMap<String, Mutex<Matcher>>,
}

impl Shared {
    fn event(&self, st: &str, ev: &str, c: u64, msg: &str, extra: &str) {
        let line = format!(
            "{{\"t\":{},\"st\":\"{}\",\"ev\":\"{}\",\"c\":{},\"msg\":\"{}\"{}}}\n",
            now_ns(),
            st,
            ev,
            c,
            util::redact(msg, &self.secrets),
            extra
        );
        if let Ok(mut f) = self.events.lock() {
            let _ = f.write_all(line.as_bytes());
        }
    }
    fn log(&self, msg: &str) {
        let line = format!("{} PKT {}\n", util::fmt_hms_pkt(now_ns()), util::redact(msg, &self.secrets));
        if !self.quiet {
            print!("{line}");
            let _ = std::io::stdout().flush();
        }
        if let Ok(mut f) = self.log.lock() {
            let _ = f.write_all(line.as_bytes());
        }
    }
}

// ------------------------------------------------------------------------------------------------
// writer thread (one per stream): dataset + pump view; keeps all disk/compress work off the rx path
// ------------------------------------------------------------------------------------------------

struct Item {
    t: i64,
    epoch: u64,
    resp: pb::SubscribeBinaryTransactionsResponse,
}

#[derive(Default, Clone, Copy)]
struct MemberStats {
    n: u64,
    ulen: u64,
    q0: u64,
    q1: u64,
    t0: i64,
    t1: i64,
    s0: u64,
    s1: u64,
}

struct Writer {
    name: String,
    dir: PathBuf,
    sh: Arc<Shared>,
    st: Arc<Stats>,
    pump: [u8; 32],
    amm: Option<[u8; 32]>,
    view_all: bool,
    jsonl_raw: bool,
    raw_on: bool,
    gz_level: u32,
    part_max: u64,
    matcher_key: Option<String>,
    is_pre: bool,
    seq: u64,
    // dataset
    bucket: i64,
    key: String,
    part: u32,
    rec: Option<File>,
    rec_off: u64,
    idx: Option<BufWriter<File>>,
    member: Option<GzEncoder<Vec<u8>>>,
    ms: MemberStats,
    member_no: u64,
    // view
    view: Option<BufWriter<File>>,
    view_bucket: i64,
    line: Vec<u8>,
    hdr: Vec<u8>,
}

fn open_append(p: &Path) -> std::io::Result<File> {
    OpenOptions::new().create(true).append(true).open(p)
}

impl Writer {
    fn finish_member(&mut self) {
        let Some(enc) = self.member.take() else { return };
        if self.ms.n == 0 {
            return;
        }
        let buf = match enc.finish() {
            Ok(b) => b,
            Err(e) => {
                self.sh.log(&format!("{}: gzip finish error {e}", self.name));
                return;
            }
        };
        if let Some(f) = self.rec.as_mut() {
            if let Err(e) = f.write_all(&buf) {
                self.sh.log(&format!("{}: dataset write error {e}", self.name));
            }
        }
        let m = self.ms;
        if let Some(ix) = self.idx.as_mut() {
            let _ = writeln!(
                ix,
                "{{\"m\":{},\"off\":{},\"clen\":{},\"ulen\":{},\"n\":{},\"q0\":{},\"q1\":{},\"t0\":{},\"t1\":{},\"s0\":{},\"s1\":{}}}",
                self.member_no,
                self.rec_off,
                buf.len(),
                m.ulen,
                m.n,
                m.q0,
                m.q1,
                m.t0,
                m.t1,
                m.s0,
                m.s1
            );
            let _ = ix.flush();
        }
        self.st.gz_bytes.fetch_add(buf.len() as u64, Relaxed);
        self.rec_off += buf.len() as u64;
        self.member_no += 1;
        self.ms = MemberStats::default();
    }

    fn close_part(&mut self) {
        self.finish_member();
        self.rec = None;
        self.idx = None;
    }

    fn open_part(&mut self) {
        let base = format!("{}_{}_{:02}", self.name, self.key, self.part);
        let rp = self.dir.join(format!("{base}.rec.gz"));
        let ip = self.dir.join(format!("{base}.idx.jsonl"));
        match (open_append(&rp), open_append(&ip)) {
            (Ok(r), Ok(i)) => {
                self.rec_off = r.metadata().map(|m| m.len()).unwrap_or(0);
                self.rec = Some(r);
                self.idx = Some(BufWriter::new(i));
            }
            (Err(e), _) | (_, Err(e)) => self.sh.log(&format!("{}: cannot open dataset part: {e}", self.name)),
        }
    }

    fn flush(&mut self) {
        self.finish_member();
        if let Some(v) = self.view.as_mut() {
            let _ = v.flush();
        }
    }

    fn handle(&mut self, it: Item) {
        let t = it.t;
        let ca = it
            .resp
            .created_at
            .as_ref()
            .map(|ts| ts.seconds.saturating_mul(1_000_000_000).saturating_add(ts.nanos as i64))
            .unwrap_or(0);
        let (slot, preconf, btx) = match it.resp.transaction {
            Some(u) => (u.slot, u.preconf, u.transaction),
            None => (0, false, None),
        };
        let (proto_sigs, bytes) = match btx {
            Some(b) => (b.signatures, b.binary_transaction),
            None => (vec![], vec![]),
        };
        self.seq += 1;
        let seq = self.seq;
        let parsed = txparse::parse_tx(&bytes);
        let mut flags: u8 = if preconf { 1 } else { 0 };
        if parsed.is_none() {
            flags |= 2;
            self.st.parse_err.fetch_add(1, Relaxed);
        }
        if bytes.is_empty() {
            flags |= 4;
        }
        self.st.n.fetch_add(1, Relaxed);
        self.st.last_slot.store(slot, Relaxed);
        self.st.last_rx.store(t, Relaxed);
        self.st.raw_bytes.fetch_add(44 + bytes.len() as u64, Relaxed);

        let sig: Option<&[u8]> = match proto_sigs.first() {
            Some(s) if s.len() == 64 => Some(s.as_slice()),
            _ => parsed.as_ref().and_then(|p| p.signatures.first().copied()),
        };

        // live pre-vs-bin lead estimate (status line only)
        if let (Some(mk), Some(s)) = (self.matcher_key.as_ref(), sig) {
            if let Some(m) = self.sh.matchers.get(mk) {
                let key = u64::from_le_bytes(s[..8].try_into().unwrap());
                if let Ok(mut m) = m.lock() {
                    m.observe(key, t, self.is_pre);
                }
            }
        }

        // ---- dataset ----
        if self.raw_on && !self.sh.raw_paused.load(Relaxed) {
            let b = util::hour_bucket(t);
            if b != self.bucket || self.rec.is_none() {
                self.close_part();
                if b != self.bucket {
                    self.part = 0;
                }
                self.bucket = b;
                self.key = util::hour_key(t);
                self.open_part();
            } else if self.rec_off >= self.part_max {
                self.close_part();
                self.part += 1;
                self.open_part();
            }
            if self.member.is_none() {
                self.member = Some(GzEncoder::new(Vec::with_capacity(1 << 20), Compression::new(self.gz_level)));
            }
            let tx_len = bytes.len() as u32;
            self.hdr.clear();
            self.hdr.extend_from_slice(&(40 + tx_len).to_le_bytes());
            self.hdr.extend_from_slice(&seq.to_le_bytes());
            self.hdr.extend_from_slice(&t.to_le_bytes());
            self.hdr.extend_from_slice(&ca.to_le_bytes());
            self.hdr.extend_from_slice(&slot.to_le_bytes());
            self.hdr.push(flags);
            self.hdr.push(proto_sigs.len().min(255) as u8);
            self.hdr.extend_from_slice(&0u16.to_le_bytes());
            self.hdr.extend_from_slice(&tx_len.to_le_bytes());
            let enc = self.member.as_mut().unwrap();
            let _ = enc.write_all(&self.hdr);
            let _ = enc.write_all(&bytes);
            let ms = &mut self.ms;
            if ms.n == 0 {
                ms.q0 = seq;
                ms.t0 = t;
                ms.s0 = slot;
                ms.s1 = slot;
            }
            ms.n += 1;
            ms.q1 = seq;
            ms.t1 = t;
            ms.s0 = ms.s0.min(slot);
            ms.s1 = ms.s1.max(slot);
            ms.ulen += 44 + bytes.len() as u64;
            if ms.ulen > (32 << 20) {
                self.finish_member();
            }
        } else if self.member.is_some() {
            self.close_part(); // paused: close cleanly
        }

        // ---- pump view ----
        let pump_ix = parsed.as_ref().map(|p| txparse::pump_summary(p, &self.pump, self.amm.as_ref()));
        let in_view = if self.view_all {
            true
        } else {
            match (&parsed, &pump_ix) {
                (Some(p), Some(ixs)) => {
                    !ixs.is_empty()
                        || p.keys.iter().any(|k| *k == &self.pump[..] || self.amm.map(|a| *k == &a[..]).unwrap_or(false))
                }
                _ => false,
            }
        };
        if !in_view {
            return;
        }
        let vb = util::hour_bucket(t);
        if vb != self.view_bucket || self.view.is_none() {
            if let Some(mut v) = self.view.take() {
                let _ = v.flush();
            }
            let p = self.dir.join(format!("{}_{}.jsonl", self.name, util::hour_key(t)));
            match open_append(&p) {
                Ok(f) => self.view = Some(BufWriter::with_capacity(256 << 10, f)),
                Err(e) => {
                    self.sh.log(&format!("{}: cannot open view file: {e}", self.name));
                    return;
                }
            }
            self.view_bucket = vb;
        }
        self.st.n_view.fetch_add(1, Relaxed);
        let l = &mut self.line;
        l.clear();
        let sig58 = sig.map(|s| bs58::encode(s).into_string()).unwrap_or_default();
        let _ = write!(l, "{{\"q\":{seq},\"t\":{t},\"ca\":{ca},\"s\":{slot},\"sig\":\"{sig58}\",\"pf\":{},\"c\":{}", preconf as u8, it.epoch);
        match &parsed {
            Some(p) => {
                let _ = write!(l, ",\"v\":{}", p.version);
            }
            None => {
                let _ = write!(l, ",\"v\":null,\"pe\":1");
            }
        }
        l.extend_from_slice(b",\"p\":[");
        if let Some(ixs) = &pump_ix {
            for (i, ix) in ixs.iter().enumerate() {
                if i > 0 {
                    l.push(b',');
                }
                let m = ix.mint.map(|k| format!("\"{}\"", bs58::encode(k).into_string())).unwrap_or_else(|| "null".into());
                let u = ix.user.map(|k| format!("\"{}\"", bs58::encode(k).into_string())).unwrap_or_else(|| "null".into());
                let _ = write!(l, "[\"{}\",{},{},{},{}]", ix.kind, m, u, ix.a1, ix.a2);
            }
        }
        l.push(b']');
        if self.jsonl_raw {
            use base64::Engine;
            let _ = write!(l, ",\"x\":\"{}\"", base64::engine::general_purpose::STANDARD.encode(&bytes));
        }
        l.extend_from_slice(b"}\n");
        if let Some(v) = self.view.as_mut() {
            let _ = v.write_all(l);
        }
    }

    fn run(mut self, rx: Receiver<Item>, flush_every: Duration) {
        let mut last_flush = Instant::now();
        loop {
            match rx.recv_timeout(Duration::from_millis(100)) {
                Ok(it) => self.handle(it),
                Err(RecvTimeoutError::Timeout) => {}
                Err(RecvTimeoutError::Disconnected) => break,
            }
            if last_flush.elapsed() >= flush_every {
                self.flush();
                last_flush = Instant::now();
            }
        }
        self.close_part();
        if let Some(mut v) = self.view.take() {
            let _ = v.flush();
        }
    }
}

// ------------------------------------------------------------------------------------------------
// gRPC receive side
// ------------------------------------------------------------------------------------------------

fn build_request(spec: &StreamSpec, filter: &FilterSpec, required: bool, exclude_votes: bool) -> pb::SubscribeBinaryTransactionsRequest {
    let (inc, req) = if required { (vec![], filter.accounts.clone()) } else { (filter.accounts.clone(), vec![]) };
    let mk = |preconf: bool| pb::SubscribeRequestFilterBinaryTransactions {
        account_include: inc.clone(),
        // account_exclude is not allowed with preconf=true
        account_exclude: if !preconf && exclude_votes && filter.is_all() { vec![VOTE_PROGRAM.to_string()] } else { vec![] },
        account_required: req.clone(),
        preconf,
    };
    let mut m = HashMap::new();
    if spec.both {
        m.insert("pre".to_string(), mk(true));
        m.insert("bin".to_string(), mk(false));
    } else {
        m.insert(spec.name.clone(), mk(spec.preconf));
    }
    pb::SubscribeBinaryTransactionsRequest { transactions: m }
}

/// where a connection delivers: one sink, or two (index 0 = preconf, 1 = Binary) for a `both` stream
struct Sink {
    tx: SyncSender<Item>,
    st: Arc<Stats>,
}

async fn connect(acc: &Access, timeout_ms: u64) -> Result<tonic::transport::Channel, String> {
    use tonic::transport::{ClientTlsConfig, Endpoint};
    let mut ep = Endpoint::from_shared(acc.endpoint.clone())
        .map_err(|e| format!("bad endpoint: {e}"))?
        .connect_timeout(Duration::from_millis(timeout_ms))
        .timeout(Duration::from_secs(365 * 24 * 3600))
        .tcp_nodelay(true)
        .tcp_keepalive(Some(Duration::from_secs(20)))
        .http2_keep_alive_interval(Duration::from_secs(15))
        .keep_alive_timeout(Duration::from_secs(10))
        .keep_alive_while_idle(true)
        .initial_stream_window_size(Some(16 << 20))
        .initial_connection_window_size(Some(32 << 20));
    if acc.endpoint.starts_with("https://") {
        ep = ep.tls_config(ClientTlsConfig::new().with_webpki_roots()).map_err(|e| format!("tls config: {e}"))?;
    }
    ep.connect().await.map_err(|e| format!("connect failed: {}", err_chain(&e)))
}

fn err_chain(e: &dyn std::error::Error) -> String {
    let mut s = e.to_string();
    let mut cur = e.source();
    while let Some(c) = cur {
        s.push_str(": ");
        s.push_str(&c.to_string());
        cur = c.source();
    }
    s
}

fn status_err(st: &tonic::Status) -> String {
    let mut s = format!("grpc {:?}: {}", st.code(), st.message());
    if let Some(src) = std::error::Error::source(st) {
        s.push_str(" | ");
        s.push_str(&err_chain(src));
    }
    s
}

enum Outcome {
    Stop,
    Retry { got_msgs: bool, filter_reject: bool, empty: bool },
}

#[allow(clippy::too_many_arguments)]
async fn one_connection(
    spec: &StreamSpec,
    filter: &FilterSpec,
    cfg: &Arc<Cfg>,
    acc: &Access,
    sh: &Arc<Shared>,
    sinks: &[Sink],
    stop: &mut tokio::sync::watch::Receiver<bool>,
    epoch: u64,
) -> Outcome {
    let name = spec.name.as_str();
    // events carry the OUTPUT stream names (a `both` connection reports under pre and bin) so analysis can find windows
    let ev_names: Vec<&str> = if spec.both { vec!["pre", "bin"] } else { vec![name] };
    let ev = |kind: &str, msg: &str, extra: &str| {
        for n in &ev_names {
            sh.event(n, kind, epoch, msg, extra);
        }
    };
    ev("connecting", &format!("filter={}", filter.label), "");
    let ch = tokio::select! {
        r = connect(acc, cfg.connect_timeout_ms) => r,
        _ = stop.changed() => return Outcome::Stop,
    };
    let ch = match ch {
        Ok(c) => c,
        Err(e) => {
            ev("error", &e, "");
            sh.log(&format!("{name}: {e}"));
            return Outcome::Retry { got_msgs: false, filter_reject: false, empty: false };
        }
    };
    let mut client = pb::shreder_binary_service_client::ShrederBinaryServiceClient::new(ch)
        .max_decoding_message_size(64 << 20);
    let (req_tx, req_rx) = tokio::sync::mpsc::channel::<pb::SubscribeBinaryTransactionsRequest>(4);
    let _ = req_tx.send(build_request(spec, filter, cfg.required, cfg.exclude_votes)).await;
    let mut request = tonic::Request::new(tokio_stream::wrappers::ReceiverStream::new(req_rx));
    if let Some(tok) = &acc.token {
        match (
            tonic::metadata::MetadataKey::<tonic::metadata::Ascii>::from_bytes(acc.header.as_bytes()),
            tonic::metadata::MetadataValue::try_from(tok.as_str()),
        ) {
            (Ok(k), Ok(v)) => {
                request.metadata_mut().insert(k, v);
            }
            _ => sh.log(&format!("{name}: token/header not valid ASCII metadata; connecting without it")),
        }
    }
    let sub = tokio::select! {
        r = tokio::time::timeout(Duration::from_secs(15), client.subscribe_binary_transactions(request)) => r,
        _ = stop.changed() => return Outcome::Stop,
    };
    let mut stream = match sub {
        Ok(Ok(r)) => r.into_inner(),
        Ok(Err(status)) => {
            let e = status_err(&status);
            let filter_reject = matches!(
                status.code(),
                tonic::Code::InvalidArgument | tonic::Code::FailedPrecondition | tonic::Code::OutOfRange
            );
            ev("error", &format!("subscribe refused: {e}"), "");
            sh.log(&format!("{name}: subscribe refused: {e}"));
            return Outcome::Retry { got_msgs: false, filter_reject, empty: false };
        }
        Err(_) => {
            ev("error", "subscribe timeout (15 s)", "");
            sh.log(&format!("{name}: subscribe timeout"));
            return Outcome::Retry { got_msgs: false, filter_reject: false, empty: false };
        }
    };
    ev("subscribed", &format!("filter={}", filter.label), "");
    sh.log(&format!("{name}: subscribed (conn #{epoch}, filter={}, preconf={})", filter.label, spec.preconf));
    for s in sinks {
        s.st.connected.store(true, Relaxed);
    }
    let t_sub = Instant::now();
    let mut n: u64 = 0;
    let mut last_msg = Instant::now();
    let mut tick = tokio::time::interval(Duration::from_secs(1));
    tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
    let outcome = loop {
        tokio::select! {
            biased;
            m = stream.next() => {
                let t = now_ns();
                match m {
                    Some(Ok(resp)) => {
                        n += 1;
                        last_msg = Instant::now();
                        if n == 1 {
                            ev("first_msg", "", &format!(",\"slot\":{}", resp.transaction.as_ref().map(|u| u.slot).unwrap_or(0)));
                            sh.log(&format!("{name}: first message after {:.0} ms", t_sub.elapsed().as_secs_f64() * 1e3));
                        }
                        let k = if sinks.len() > 1 && !resp.transaction.as_ref().map(|u| u.preconf).unwrap_or(false) { 1 } else { 0 };
                        match sinks[k].tx.try_send(Item { t, epoch, resp }) {
                            Ok(()) => {}
                            Err(TrySendError::Full(_)) => { sinks[k].st.dropped.fetch_add(1, Relaxed); }
                            Err(TrySendError::Disconnected(_)) => break Outcome::Stop,
                        }
                    }
                    Some(Err(status)) => {
                        let e = status_err(&status);
                        ev("error", &format!("stream error after {n} msgs: {e}"), "");
                        sh.log(&format!("{name}: stream error after {n} msgs: {e}"));
                        let filter_reject = n == 0 && matches!(status.code(), tonic::Code::InvalidArgument | tonic::Code::FailedPrecondition | tonic::Code::OutOfRange);
                        break Outcome::Retry { got_msgs: n > 0, filter_reject, empty: false };
                    }
                    None => {
                        ev("stream_end", &format!("server ended the stream after {n} msgs"), "");
                        sh.log(&format!("{name}: stream ended by server after {n} msgs"));
                        break Outcome::Retry { got_msgs: n > 0, filter_reject: false, empty: false };
                    }
                }
            }
            _ = stop.changed() => break Outcome::Stop,
            _ = tick.tick() => {
                // preconf only covers connected leaders, so give it twice as long before calling an unfiltered stream empty
                let empty_secs = if spec.preconf { cfg.empty_fallback_secs * 2 } else { cfg.empty_fallback_secs };
                if n == 0 && filter.is_all() && empty_secs > 0 && t_sub.elapsed().as_secs() >= empty_secs {
                    ev("error", &format!("no message {empty_secs} s after subscribe on an unfiltered stream"), "");
                    sh.log(&format!("{name}: no message {empty_secs} s after subscribing unfiltered"));
                    break Outcome::Retry { got_msgs: false, filter_reject: false, empty: true };
                }
                if cfg.stall_secs > 0 && n > 0 && last_msg.elapsed().as_secs() >= cfg.stall_secs {
                    ev("error", &format!("stall: no message for {} s, reconnecting", cfg.stall_secs), "");
                    sh.log(&format!("{name}: stall {} s, reconnecting", cfg.stall_secs));
                    break Outcome::Retry { got_msgs: true, filter_reject: false, empty: false };
                }
            }
        }
    };
    for s in sinks {
        s.st.connected.store(false, Relaxed);
    }
    drop(req_tx);
    outcome
}

async fn stream_task(
    spec: StreamSpec,
    cfg: Arc<Cfg>,
    acc: Access,
    sh: Arc<Shared>,
    sinks: Vec<Sink>,
    mut stop: tokio::sync::watch::Receiver<bool>,
) {
    let mut filter = spec.filter.clone();
    let mut backoff = Duration::from_millis(500);
    let mut epoch: u64 = 0;
    let mut filter_rejects = 0u32;
    loop {
        if *stop.borrow() {
            break;
        }
        epoch += 1;
        for s in &sinks {
            s.st.epoch.store(epoch, Relaxed);
            if epoch > 1 {
                s.st.reconnects.fetch_add(1, Relaxed);
            }
        }
        let started = Instant::now();
        match one_connection(&spec, &filter, &cfg, &acc, &sh, &sinks, &mut stop, epoch).await {
            Outcome::Stop => break,
            Outcome::Retry { got_msgs, filter_reject, empty } => {
                if filter_reject || empty {
                    filter_rejects += 1;
                } else if got_msgs {
                    filter_rejects = 0;
                }
                if filter.is_all() && (filter_rejects >= 2 || empty) {
                    if let Some(fb) = cfg.fallback.clone() {
                        for n in if spec.both { vec!["pre", "bin"] } else { vec![spec.name.as_str()] } {
                            sh.event(n, "filter_fallback", epoch, &format!("unfiltered stream not served; switching to filter={}", fb.label), "");
                        }
                        sh.log(&format!("{}: FALLBACK unfiltered -> filter={} ({} accounts)", spec.name, fb.label, fb.accounts.len()));
                        filter = fb;
                        for s in &sinks {
                            s.st.fallback_active.store(true, Relaxed);
                        }
                        filter_rejects = 0;
                        backoff = Duration::from_millis(500);
                    }
                }
                if got_msgs && started.elapsed() > Duration::from_secs(30) {
                    backoff = Duration::from_millis(500);
                }
                tokio::select! {
                    _ = tokio::time::sleep(backoff) => {}
                    _ = stop.changed() => break,
                }
                backoff = (backoff * 2).min(Duration::from_secs(10));
            }
        }
    }
}

// ------------------------------------------------------------------------------------------------
// status
// ------------------------------------------------------------------------------------------------

struct Prev {
    n: u64,
    n_view: u64,
    raw: u64,
    gz: u64,
}

fn status_line(cfg: &Cfg, sh: &Shared, stats: &[(String, Arc<Stats>)], prev: &mut Vec<Prev>, dt: f64, cpu_pct: f64, final_: bool) {
    let mut parts = Vec::new();
    for (i, (sname, st)) in stats.iter().enumerate() {
        let n = st.n.load(Relaxed);
        let nv = st.n_view.load(Relaxed);
        let raw = st.raw_bytes.load(Relaxed);
        let gz = st.gz_bytes.load(Relaxed);
        let p = &prev[i];
        let rate = (n - p.n) as f64 / dt;
        let vrate = (nv - p.n_view) as f64 / dt;
        let raw_mbs = (raw - p.raw) as f64 / dt / 1e6;
        let gz_mbs = (gz - p.gz) as f64 / dt / 1e6;
        let gb_h = gz_mbs * 3600.0 / 1e3;
        let conn = if st.connected.load(Relaxed) { "up" } else { "DOWN" };
        let fb = if st.fallback_active.load(Relaxed) { " FALLBACK" } else { "" };
        if final_ {
            parts.push(format!(
                "{} total n={} view={} rc={} drop={} perr={} raw {:.3} GB gz {:.3} GB{}",
                sname,
                n,
                nv,
                st.reconnects.load(Relaxed),
                st.dropped.load(Relaxed),
                st.parse_err.load(Relaxed),
                raw as f64 / 1e9,
                gz as f64 / 1e9,
                fb
            ));
            sh.event(&sname, "final", st.epoch.load(Relaxed), "", &format!(
                ",\"n\":{},\"n_view\":{},\"rc\":{},\"dropped\":{},\"perr\":{},\"raw_bytes\":{},\"gz_bytes\":{},\"fallback\":{}",
                n, nv, st.reconnects.load(Relaxed), st.dropped.load(Relaxed), st.parse_err.load(Relaxed), raw, gz, st.fallback_active.load(Relaxed)));
            prev[i] = Prev { n, n_view: nv, raw, gz };
            continue;
        }
        parts.push(format!(
            "{} {:.1}/s view {:.1}/s n={} slot={} rc={} drop={} perr={} raw {:.2} MB/s gz {:.2} MB/s ~{:.2} GB/h {}{}",
            sname,
            rate,
            vrate,
            n,
            st.last_slot.load(Relaxed),
            st.reconnects.load(Relaxed),
            st.dropped.load(Relaxed),
            st.parse_err.load(Relaxed),
            raw_mbs,
            gz_mbs,
            gb_h,
            conn,
            fb
        ));
        sh.event(
            &sname,
            "status",
            st.epoch.load(Relaxed),
            "",
            &format!(
                ",\"n\":{},\"rate\":{:.2},\"view_rate\":{:.2},\"slot\":{},\"rc\":{},\"dropped\":{},\"perr\":{},\"raw_mbs\":{:.4},\"gz_mbs\":{:.4},\"gb_per_h\":{:.3},\"up\":{},\"fallback\":{}",
                n,
                rate,
                vrate,
                st.last_slot.load(Relaxed),
                st.reconnects.load(Relaxed),
                st.dropped.load(Relaxed),
                st.parse_err.load(Relaxed),
                raw_mbs,
                gz_mbs,
                gb_h,
                st.connected.load(Relaxed),
                st.fallback_active.load(Relaxed)
            ),
        );
        prev[i] = Prev { n, n_view: nv, raw, gz };
    }
    // lead estimates
    let mut leads = Vec::new();
    for (label, m) in &sh.matchers {
        if let Ok(mut m) = m.lock() {
            let cutoff = now_ns() - 5_000_000_000;
            m.map.retain(|_, v| v.0 >= cutoff);
            let mut d = std::mem::take(&mut m.deltas);
            d.sort_unstable();
            if !d.is_empty() {
                let pre_first = d.iter().filter(|&&x| x > 0).count() as f64 / d.len() as f64 * 100.0;
                leads.push(format!(
                    "lead[{label}] n={} pre-first {:.0}% bin-pre P10/50/90 {:.2}/{:.2}/{:.2} ms",
                    d.len(),
                    pre_first,
                    util::pctl(&d, 0.1) as f64 / 1e6,
                    util::pctl(&d, 0.5) as f64 / 1e6,
                    util::pctl(&d, 0.9) as f64 / 1e6
                ));
                sh.event(
                    "all",
                    "lead",
                    0,
                    label,
                    &format!(
                        ",\"n\":{},\"pre_first_pct\":{:.1},\"p10_ms\":{:.3},\"p50_ms\":{:.3},\"p90_ms\":{:.3}",
                        d.len(),
                        pre_first,
                        util::pctl(&d, 0.1) as f64 / 1e6,
                        util::pctl(&d, 0.5) as f64 / 1e6,
                        util::pctl(&d, 0.9) as f64 / 1e6
                    ),
                );
            }
        }
    }
    let disk = util::disk_used_pct(&cfg.out).unwrap_or(-1.0);
    let rss = util::rss_mb();
    sh.event("all", "status", 0, "", &format!(",\"cpu_pct\":{cpu_pct:.2},\"rss_mb\":{rss:.1},\"disk_pct\":{disk:.1},\"raw_paused\":{}", sh.raw_paused.load(Relaxed)));
    if final_ {
        sh.log(&format!("FINAL {} | disk {:.1}%", parts.join(" | "), disk));
        return;
    }
    sh.log(&format!(
        "{}{} | cpu {:.1}% rss {:.0} MB disk {:.1}%{}{}",
        "",
        parts.join(" | "),
        cpu_pct,
        rss,
        disk,
        if sh.raw_paused.load(Relaxed) { " RAW-PAUSED(disk)" } else { "" },
        if leads.is_empty() { String::new() } else { format!(" | {}", leads.join(" | ")) }
    ));
}

// ------------------------------------------------------------------------------------------------
// --check: one subscribe per stream, summarise a few messages, exit
// ------------------------------------------------------------------------------------------------

async fn check(cfg: Arc<Cfg>, acc: Access, sh: Arc<Shared>) -> i32 {
    let mut rc = 0;
    for spec in &cfg.streams {
        let mut sinks = Vec::new();
        let mut rxs = Vec::new();
        for _ in 0..(if spec.both { 2 } else { 1 }) {
            let (tx, rx) = sync_channel::<Item>(50_000);
            sinks.push(Sink { tx, st: Arc::new(Stats::default()) });
            rxs.push(rx);
        }
        let (_stop_tx, mut stop_rx) = tokio::sync::watch::channel(false);
        let t0 = Instant::now();
        let fut = one_connection(spec, &spec.filter, &cfg, &acc, &sh, &sinks, &mut stop_rx, 1);
        let _ = tokio::time::timeout(Duration::from_secs(8), fut).await;
        let mut n = 0;
        let mut pf = 0;
        let mut slots = (u64::MAX, 0u64);
        let mut pumps = 0;
        let pump = decode_pubkey(PUMP_PROGRAM).unwrap();
        let items: Vec<Item> = rxs.iter().flat_map(|rx| rx.try_iter().collect::<Vec<_>>()).collect();
        for it in items {
            n += 1;
            if let Some(u) = it.resp.transaction {
                if u.preconf {
                    pf += 1;
                }
                slots = (slots.0.min(u.slot), slots.1.max(u.slot));
                if let Some(b) = u.transaction {
                    if let Some(p) = txparse::parse_tx(&b.binary_transaction) {
                        if p.keys.iter().any(|k| *k == &pump[..]) {
                            pumps += 1;
                        }
                    }
                }
            }
        }
        let msg = format!(
            "CHECK {}: {} msgs in {:.1} s (preconf flag on {}, pump {}), slots {}..{}",
            spec.name,
            n,
            t0.elapsed().as_secs_f64(),
            pf,
            pumps,
            if n > 0 { slots.0 } else { 0 },
            slots.1
        );
        sh.log(&msg);
        if n == 0 {
            rc = 1;
        }
    }
    rc
}

// ------------------------------------------------------------------------------------------------

fn main() {
    let cfg = parse_args();
    if let Err(e) = std::fs::create_dir_all(&cfg.out) {
        eprintln!("cannot create out dir: {e}");
        std::process::exit(1);
    }
    let acc = match util::load_access(cfg.key.as_deref(), cfg.endpoint.as_deref()) {
        Ok(a) => a,
        Err(e) => {
            eprintln!("{e}");
            std::process::exit(1);
        }
    };
    let events = open_append(&cfg.out.join("events.jsonl")).expect("events.jsonl");
    let log = open_append(&cfg.out.join("rec.log")).expect("rec.log");
    let mut matchers = HashMap::new();
    for s in &cfg.streams {
        let has_pre = cfg.streams.iter().any(|x| (x.both || x.preconf) && x.filter.label == s.filter.label);
        let has_bin = cfg.streams.iter().any(|x| (x.both || !x.preconf) && x.filter.label == s.filter.label);
        if has_pre && has_bin {
            matchers.entry(s.filter.label.clone()).or_insert_with(|| Mutex::new(Matcher::default()));
        }
    }
    let sh = Arc::new(Shared {
        out: cfg.out.clone(),
        events: Mutex::new(events),
        log: Mutex::new(log),
        secrets: acc.secrets(),
        raw_paused: AtomicBool::new(false),
        quiet: cfg.quiet,
        matchers,
    });
    let _ = &sh.out;
    let streams_desc: Vec<String> = cfg
        .streams
        .iter()
        .map(|s| format!("{}({},filter={},{} accts{})", s.name, if s.both { "both sources, one connection" } else if s.preconf { "preconf=true" } else { "preconf=false" }, s.filter.label, s.filter.accounts.len(), if cfg.exclude_votes && !s.preconf && s.filter.is_all() { ", votes excluded" } else { "" }))
        .collect();
    sh.log(&format!(
        "{VERSION} start: endpoint id {} ({}), auth {}, streams {}, out {}, stop {}, raw {}, gz {}, pid {}",
        acc.fingerprint(),
        acc.source,
        acc.auth_desc(),
        streams_desc.join(" "),
        cfg.out.display(),
        cfg.run_secs.map(|s| format!("after {:.1} min", s / 60.0)).unwrap_or("on signal".into()),
        cfg.raw,
        cfg.gz_level,
        std::process::id()
    ));
    sh.event(
        "all",
        "start",
        0,
        VERSION,
        &format!(
            ",\"endpoint_id\":\"{}\",\"auth\":\"{}\",\"streams\":\"{}\",\"pid\":{},\"run_secs\":{}",
            acc.fingerprint(),
            acc.auth_desc(),
            streams_desc.join(" "),
            std::process::id(),
            cfg.run_secs.unwrap_or(-1.0)
        ),
    );

    let rt = tokio::runtime::Builder::new_multi_thread()
        .worker_threads(cfg.threads)
        .enable_all()
        .thread_name("shreder-rx")
        .build()
        .expect("tokio runtime");
    let cfg = Arc::new(cfg);

    if cfg.check_only {
        let rc = rt.block_on(check(cfg.clone(), acc.clone(), sh.clone()));
        std::process::exit(rc);
    }

    let pump = decode_pubkey(PUMP_PROGRAM).unwrap();
    let amm = decode_pubkey(PUMP_AMM_PROGRAM).unwrap();
    let (stop_tx, stop_rx) = tokio::sync::watch::channel(false);
    let mut writers = Vec::new();
    let mut stats: Vec<(String, Arc<Stats>)> = Vec::new();
    let mut tasks = Vec::new();
    for spec in cfg.streams.clone() {
        let has_pair = sh.matchers.contains_key(&spec.filter.label);
        // a `both` stream feeds two writers: [0] = "pre" (preconf), [1] = "bin"
        let outs: Vec<(String, bool)> = if spec.both { vec![("pre".into(), true), ("bin".into(), false)] } else { vec![(spec.name.clone(), spec.preconf)] };
        let mut sinks = Vec::new();
        for (oname, is_pre) in outs {
            let st = Arc::new(Stats::default());
            let (tx, rx) = sync_channel::<Item>(cfg.queue);
            let w = Writer {
                name: oname.clone(),
                dir: cfg.out.clone(),
                sh: sh.clone(),
                st: st.clone(),
                pump,
                amm: if cfg.view_amm { Some(amm) } else { None },
                view_all: !spec.filter.is_all() && !spec.filter.label.contains("broad"),
                jsonl_raw: cfg.jsonl_raw,
                raw_on: cfg.raw,
                gz_level: cfg.gz_level,
                part_max: cfg.part_max_mb << 20,
                matcher_key: if has_pair { Some(spec.filter.label.clone()) } else { None },
                is_pre,
                seq: 0,
                bucket: i64::MIN,
                key: String::new(),
                part: 0,
                rec: None,
                rec_off: 0,
                idx: None,
                member: None,
                ms: MemberStats::default(),
                member_no: 0,
                view: None,
                view_bucket: i64::MIN,
                line: Vec::with_capacity(4096),
                hdr: Vec::with_capacity(64),
            };
            let flush_every = Duration::from_millis(cfg.flush_ms.max(50));
            writers.push(std::thread::Builder::new().name(format!("w-{oname}")).spawn(move || w.run(rx, flush_every)).unwrap());
            stats.push((oname, st.clone()));
            sinks.push(Sink { tx, st });
        }
        tasks.push(rt.spawn(stream_task(spec, cfg.clone(), acc.clone(), sh.clone(), sinks, stop_rx.clone())));
    }

    // stop on deadline or signal
    let sh2 = sh.clone();
    let cfg2 = cfg.clone();
    rt.spawn(async move {
        use tokio::signal::unix::{signal, SignalKind};
        let mut term = signal(SignalKind::terminate()).expect("sigterm");
        let mut int = signal(SignalKind::interrupt()).expect("sigint");
        let dl = async {
            match cfg2.run_secs {
                Some(s) => tokio::time::sleep(Duration::from_secs_f64(s.max(0.0))).await,
                None => std::future::pending::<()>().await,
            }
        };
        let why = tokio::select! {
            _ = dl => "time limit",
            _ = term.recv() => "SIGTERM",
            _ = int.recv() => "SIGINT",
        };
        sh2.log(&format!("stopping: {why}"));
        sh2.event("all", "stop", 0, why, "");
        let _ = stop_tx.send(true);
    });

    // status loop on the main thread
    let mut prev: Vec<Prev> = stats.iter().map(|_| Prev { n: 0, n_view: 0, raw: 0, gz: 0 }).collect();
    let mut last = Instant::now();
    let (mut last_cpu, _) = util::rusage();
    let t_start = Instant::now();
    let mut first_done = false;
    let mut stop_watch = stop_rx.clone();
    loop {
        let wait = if !first_done { Duration::from_secs(10) } else { Duration::from_secs(cfg.status_secs.max(1)) };
        let deadline = last + wait;
        // sleep in small steps so a stop is noticed quickly
        let mut stopped = false;
        while Instant::now() < deadline {
            std::thread::sleep(Duration::from_millis(200));
            if *stop_watch.borrow_and_update() {
                stopped = true;
                break;
            }
        }
        if stopped {
            break;
        }
        let dt = last.elapsed().as_secs_f64().max(1e-3);
        let (cpu, _) = util::rusage();
        let cpu_pct = (cpu - last_cpu) / dt * 100.0;
        last_cpu = cpu;
        last = Instant::now();
        // disk guard
        if let Some(d) = util::disk_used_pct(&cfg.out) {
            let paused = sh.raw_paused.load(Relaxed);
            if !paused && d >= cfg.disk_max_pct {
                sh.raw_paused.store(true, Relaxed);
                sh.log(&format!("DISK {d:.1}% >= {:.0}%: raw dataset PAUSED (views continue)", cfg.disk_max_pct));
                sh.event("all", "raw_paused", 0, &format!("disk {d:.1}%"), "");
            } else if paused && d < cfg.disk_max_pct - 2.0 {
                sh.raw_paused.store(false, Relaxed);
                sh.log(&format!("disk {d:.1}%: raw dataset resumed"));
                sh.event("all", "raw_resumed", 0, &format!("disk {d:.1}%"), "");
            }
        }
        status_line(&cfg, &sh, &stats, &mut prev, dt, cpu_pct, false);
        first_done = true;
    }

    // shutdown: stream tasks end on the stop signal, writers drain and close
    rt.block_on(async {
        for t in tasks {
            let _ = tokio::time::timeout(Duration::from_secs(5), t).await;
        }
    });
    rt.shutdown_timeout(Duration::from_secs(2));
    for w in writers {
        let _ = w.join();
    }
    let dt = last.elapsed().as_secs_f64().max(1e-3);
    let (cpu, maxrss) = util::rusage();
    status_line(&cfg, &sh, &stats, &mut prev, dt, (cpu - last_cpu) / dt * 100.0, true);
    let wall = t_start.elapsed().as_secs_f64();
    sh.log(&format!(
        "done: wall {:.0} s, cpu {:.1} s ({:.2}% of one core avg), max rss {:.0} MB",
        wall,
        cpu,
        cpu / wall.max(1e-3) * 100.0,
        maxrss as f64 / 1024.0
    ));
    sh.event("all", "done", 0, "", &format!(",\"wall_s\":{wall:.1},\"cpu_s\":{cpu:.2},\"maxrss_kb\":{maxrss}"));
}

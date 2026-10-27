//! QUIET (dip20; owner 10-27 ~13:30 PKT "implement QUIET in engine"): the pre-send filter of the research
//! ops/strategies/presend/filter/REPORT.md ("Engine change list"; rules.py `quiet_arm` + `c5_send`, apply_filter.py config
//! "quiet"), its PURE parts. The engine wiring (flags, records, the stop's disarm, the preload thread, the shadow annotation) is
//! src/bin/snipe_engine/pslive.rs; everything there is off unless a --presend-live-quiet-* flag is given.
//!   * `DumpBook`: every pump trade of every token, in arrival order. A DUMP = a curve sell of >= 0.3 SOL at a curve under 100 SOL
//!     whose post-trade price is <= 0.92 x its pre-trade price; its FOLLOWERS = the distinct buyers (not the seller) on that token
//!     after it (chain position), in its slot and the next 2 slots. Kept per seller for `hist_ns` (24 h). O(1) per trade (amortized:
//!     one map lookup; the closing and expiry queues pop what they pushed), memory bounded by the dumps of `hist_ns`.
//!   * `ArmSig` / `arm_signals`: the four "quiet" signals at a trigger, as apply_filter.quiet_signals: (a) slots since the token's
//!     previous trade (any wallet), (b) cohort wallets HOLDING the token before the trigger, (c) follower bots that traded it before
//!     the trigger, (d) the whale's mean followers over its dumps closed before the trigger slot (s + 2 < s0) in the last hist_ns
//!     (-1 = none). QUIET = (a) >= 1 and (b) == 0 and (c) < 2 and (d) < F (2.24).
//!   * `QStop`: the stop rule (C5): at slot >= trigger slot + N with fewer than M "other" trades (not the whale, not us) since the
//!     trigger, the window stops for good.
//!   * the PRELOAD (owner addition 10-27): the DumpBook of the last H hours rebuilt from the collector's 24/7 raw recording
//!     (`<base>/run_*/txs/txs_<unix>.jsonl.gz`, 5-minute gzip chunks, one JSON line per tx: s, i, bt, err, ev = the tx's
//!     "Program data:" strings; ops/collect/collect.py), read in a background thread with the same trade decoder and dump rules
//!     as the live feed, then merged at a cut slot so no dump is counted twice (`merge_preload`).
use crate::dip::{self, CreateEvent, TradeEvent};
use crate::presend_live::Detector;
use crate::tx::Pk;
use rustc_hash::{FxHashMap, FxHashSet};
use std::collections::VecDeque;
use std::io::BufRead;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

/// a dump is a curve SELL of at least this much SOL (lamports) ...
pub const DUMP_MIN_SOL: u64 = 300_000_000;
/// ... at a curve (post-trade virtual SOL) under 100 SOL ...
pub const DUMP_MAX_VSOL: u64 = 100_000_000_000;
/// ... whose post-trade price is at most this x the pre-trade price (a drop of >= 8% by the trade itself)
pub const DUMP_RATIO: f64 = 0.92;
/// its followers: buys after it in its own slot and the next FOL_SLOTS slots
pub const FOL_SLOTS: u64 = 2;
/// an open follower window is CLOSED this many slots after its last slot (late arrivals of its slots still count until then)
pub const CLOSE_MARGIN: u64 = 4;
/// dumps are expired this long after they leave the history (the query applies the exact window)
const EXPIRE_SLACK_NS: u64 = 120_000_000_000;
/// a seller's first dump's absolute index (abs = base + position; a merge may prepend, so it starts high)
const BASE0: u64 = 1 << 40;
/// the follower-bot / cohort test for "fewer than 2 follower bots" (REPORT: fb_n < 2)
pub const FB_MAX: u32 = 2;

/// apply_filter.ChainIx's dump rule: a sell, sol >= 0.3 SOL, curve < 100 SOL, vtok > tok, post price <= 0.92 x pre price (the
/// same float64 arithmetic as the Python: both ratios of exactly representable integers)
pub fn is_dump(buy: bool, sol: u64, tok: u64, vsol: u64, vtok: u64) -> bool {
    if buy || sol < DUMP_MIN_SOL || vsol >= DUMP_MAX_VSOL || vtok <= tok { return false; }
    let p = vsol as f64 / vtok.max(1) as f64;
    let pre = (vsol + sol) as f64 / (vtok - tok).max(1) as f64;
    !(p > DUMP_RATIO * pre)
}

/// one dump of a seller: its slot, its time (ns: the feed's arrival live, the block time in a preload), its followers so far
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Dump { pub s: u64, pub t: u64, pub nf: u32 }

/// a seller's dumps in arrival order; d[k] has the absolute index base + k
#[derive(Debug)]
struct Seller { d: VecDeque<Dump>, base: u64 }
impl Seller { fn new() -> Seller { Seller { d: VecDeque::new(), base: BASE0 } } }

/// a dump whose follower window is still open (on its token)
#[derive(Clone, Debug)]
struct Open { seller: Pk, abs: u64, s: u64, pos: (u64, u32, i32), buyers: Vec<Pk> }

#[derive(Clone, Debug, Default, PartialEq, Eq)]
pub struct BookStats {
    pub trades: u64, pub dumps: u64, pub followers: u64, pub closed: u64, pub expired: u64,
    /// merge: live dumps below the cut dropped (the preload has them), live windows of those dropped
    pub dropped_at_cut: u64, pub windows_dropped: u64,
}

/// the whale dump history (see the module doc)
pub struct DumpBook {
    sellers: FxHashMap<Pk, Seller>,
    /// mint -> its dumps whose follower window is open
    open: FxHashMap<Pk, Vec<Open>>,
    /// (dump slot, mint) in arrival order: closes the windows of tokens that stop trading
    open_q: VecDeque<(u64, Pk)>,
    /// (t, slot, seller) of every kept dump in arrival order (= each seller's own order): the expiry
    exp_q: VecDeque<(u64, u64, Pk)>,
    pub hist_ns: u64,
    max_slot: u64,
    max_t: u64,
    /// dumps are taken only at slots < cut (a preload: the live feed takes over at the cut); u64::MAX = no cut
    pub cut: u64,
    pub st: BookStats,
}

impl std::fmt::Debug for DumpBook {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "DumpBook {{ dumps {}, sellers {}, open {}, max_slot {}, cut {}, {:?} }}", self.dumps(), self.sellers(), self.open_windows(), self.max_slot, self.cut, self.st)
    }
}

impl DumpBook {
    pub fn new(hist_ns: u64) -> DumpBook {
        DumpBook { sellers: FxHashMap::default(), open: FxHashMap::default(), open_q: VecDeque::new(), exp_q: VecDeque::new(), hist_ns, max_slot: 0, max_t: 0, cut: u64::MAX,
                   st: BookStats::default() }
    }
    pub fn sellers(&self) -> usize { self.sellers.len() }
    pub fn dumps(&self) -> usize { self.exp_q.len() }
    pub fn open_windows(&self) -> usize { self.open.values().map(|v| v.len()).sum() }
    pub fn max_slot(&self) -> u64 { self.max_slot }
    /// an estimate of the heap it holds (bytes)
    pub fn mem_bytes(&self) -> usize {
        let per_seller = 32 + 40 + 16;
        self.sellers.values().map(|s| per_seller + s.d.capacity() * std::mem::size_of::<Dump>()).sum::<usize>()
            + self.exp_q.capacity() * std::mem::size_of::<(u64, u64, Pk)>() + self.open_q.capacity() * std::mem::size_of::<(u64, Pk)>()
            + self.open.values().map(|v| 64 + v.capacity() * std::mem::size_of::<Open>() + v.iter().map(|o| o.buyers.capacity() * 32).sum::<usize>()).sum::<usize>()
    }

    /// one executed trade (any token), in the feed's order: it may add a follower to the open windows of its token, and be a dump
    /// itself. `pos` = (slot, tx index, event index); `t` = its time (ns)
    pub fn ingest(&mut self, e: &TradeEvent, s: u64, i: u32, j: i32, t: u64) {
        self.st.trades += 1;
        if t > self.max_t { self.max_t = t; self.expire(); }
        if s > self.max_slot { self.max_slot = s; self.close_quiet(); }
        if !self.open.is_empty() {
            let (open, sellers, st) = (&mut self.open, &mut self.sellers, &mut self.st);
            if let Some(v) = open.get_mut(&e.mint) {
                if e.buy {
                    for o in v.iter_mut() {
                        if s <= o.s + FOL_SLOTS && e.user != o.seller && (s, i, j) > o.pos && !o.buyers.contains(&e.user) {
                            o.buyers.push(e.user);
                            if let Some(sl) = sellers.get_mut(&o.seller) {
                                if o.abs >= sl.base { if let Some(d) = sl.d.get_mut((o.abs - sl.base) as usize) { d.nf += 1; st.followers += 1; } }
                            }
                        }
                    }
                }
            }
        }
        if s < self.cut && is_dump(e.buy, e.sol, e.tok, e.vsol, e.vtok) {
            let sl = self.sellers.entry(e.user).or_insert_with(Seller::new);
            let abs = sl.base + sl.d.len() as u64;
            sl.d.push_back(Dump { s, t, nf: 0 });
            self.exp_q.push_back((t, s, e.user));
            self.open.entry(e.mint).or_default().push(Open { seller: e.user, abs, s, pos: (s, i, j), buyers: Vec::new() });
            self.open_q.push_back((s, e.mint));
            self.st.dumps += 1;
        }
    }

    /// close the windows whose last slot is CLOSE_MARGIN slots behind the newest slot (the queue is in arrival order)
    fn close_quiet(&mut self) {
        let lim = self.max_slot;
        while let Some(&(s, mint)) = self.open_q.front() {
            if s + FOL_SLOTS + CLOSE_MARGIN >= lim { break; }
            self.open_q.pop_front();
            if let Some(v) = self.open.get_mut(&mint) {
                let n0 = v.len();
                v.retain(|o| o.s + FOL_SLOTS + CLOSE_MARGIN >= lim);
                self.st.closed += (n0 - v.len()) as u64;
                if v.is_empty() { self.open.remove(&mint); }
            }
        }
    }

    /// drop the dumps that left the history (each seller's dumps are in the queue's order: its front is the one popped)
    fn expire(&mut self) {
        let lim = self.max_t.saturating_sub(self.hist_ns.saturating_add(EXPIRE_SLACK_NS));
        while let Some(&(t, _, seller)) = self.exp_q.front() {
            if t >= lim { break; }
            self.exp_q.pop_front();
            if let Some(sl) = self.sellers.get_mut(&seller) {
                if sl.d.front().is_some_and(|d| d.t < lim) { sl.d.pop_front(); sl.base += 1; self.st.expired += 1; }
                if sl.d.is_empty() { self.sellers.remove(&seller); }
            }
        }
    }

    /// the whale's history at a trigger in slot `s0` at time `t0` (apply_filter.quiet_signals): its dumps whose window closed before
    /// the trigger slot (s + 2 < s0) and with t >= t0 - hist_ns: (mean followers, count); (-1, 0) when there is none
    pub fn whale(&self, whale: &Pk, s0: u64, t0: u64) -> (f64, u32) {
        let Some(sl) = self.sellers.get(whale) else { return (-1.0, 0) };
        let lo = t0.saturating_sub(self.hist_ns);
        let (mut n, mut sum) = (0u32, 0u64);
        for d in &sl.d { if d.s + FOL_SLOTS < s0 && d.t >= lo { n += 1; sum += d.nf as u64; } }
        if n == 0 { (-1.0, 0) } else { (sum as f64 / n as f64, n) }
    }

    /// every seller's dumps (sorted by seller), and the open windows (seller, slot, buyers so far): equality in the tests / parity
    pub fn snapshot(&self) -> (Vec<(Pk, Vec<Dump>)>, Vec<(Pk, u64, u32)>) {
        let mut v: Vec<(Pk, Vec<Dump>)> = self.sellers.iter().map(|(k, s)| (*k, s.d.iter().copied().collect())).collect();
        v.sort_by(|a, b| a.0.cmp(&b.0));
        let mut o: Vec<(Pk, u64, u32)> = self.open.values().flatten().map(|x| (x.seller, x.s, x.buyers.len() as u32)).collect();
        o.sort();
        (v, o)
    }

    /// a preload's end: every window of its dumps (all below the cut) is complete (the recording was read past cut + 1)
    pub fn close_all(&mut self) {
        self.st.closed += self.open_windows() as u64;
        self.open.clear();
        self.open_q.clear();
    }
}

/// THE MERGE (main thread, once): a preload `pre` (dumps at slots < pre.cut, windows complete) takes over the live book's dumps at
/// slots >= the cut, in order, after its own; the live book's dumps below the cut (the preload has them, with their complete
/// windows) and their windows are dropped, so no dump and no follower is counted twice. Work: O(live book), never O(preload).
pub fn merge_preload(mut pre: DumpBook, mut live: DumpBook) -> DumpBook {
    let cut = pre.cut;
    pre.close_all();
    // the live windows to keep (their dumps are at or above the cut), with their new absolute indices
    let mut opens: Vec<(Pk, Open)> = Vec::new();
    for (mint, v) in live.open.drain() {
        for o in v { if o.s >= cut { opens.push((mint, o)); } else { pre.st.windows_dropped += 1; } }
    }
    let mut remap: FxHashMap<(Pk, u64), u64> = opens.iter().map(|(_, o)| ((o.seller, o.abs), 0)).collect();
    for (seller, sl) in live.sellers.drain() {
        let p = pre.sellers.entry(seller).or_insert_with(Seller::new);
        for (k, d) in sl.d.into_iter().enumerate() {
            if d.s < cut { pre.st.dropped_at_cut += 1; continue; }
            let new_abs = p.base + p.d.len() as u64;
            if let Some(x) = remap.get_mut(&(seller, sl.base + k as u64)) { *x = new_abs; }
            p.d.push_back(d);
        }
        if p.d.is_empty() { pre.sellers.remove(&seller); }
    }
    for (mint, mut o) in opens {
        if let Some(&a) = remap.get(&(o.seller, o.abs)) { o.abs = a; pre.open.entry(mint).or_default().push(o); }
    }
    pre.exp_q.extend(live.exp_q.drain(..).filter(|x| x.1 >= cut));
    pre.open_q.extend(live.open_q.drain(..).filter(|x| x.0 >= cut));
    pre.max_slot = pre.max_slot.max(live.max_slot);
    pre.max_t = pre.max_t.max(live.max_t);
    let st = &live.st;
    pre.st.trades += st.trades; pre.st.dumps += st.dumps; pre.st.followers += st.followers; pre.st.closed += st.closed; pre.st.expired += st.expired;
    pre.cut = u64::MAX;
    pre.hist_ns = live.hist_ns;
    pre.expire();
    pre
}

/// the four signals at a trigger (apply_filter.quiet_signals)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ArmSig {
    /// slots since the token's previous trade (any wallet; 9999 = none: the study's value)
    pub since_last: u64,
    /// cohort wallets holding the token before the trigger
    pub coh_hold: u32,
    /// follower bots that traded the token before the trigger
    pub fb_n: u32,
    /// the whale's mean followers over its dumps of the history (-1 = none), and how many
    pub wh_fol: f64, pub wh_dumps: u32,
}

impl ArmSig {
    /// [no other trade earlier in the trigger's slot, no cohort holder, < 2 follower bots, whale's dumps drew < F buyers (or none)]
    pub fn flags(&self, fol: f64) -> [bool; 4] { [self.since_last >= 1, self.coh_hold == 0, self.fb_n < FB_MAX, self.wh_fol < fol] }
    /// all four hold: the QUIET arm rule skips
    pub fn quiet(&self, fol: f64) -> bool { self.flags(fol).iter().all(|x| *x) }
    pub fn json(&self, fol: f64) -> serde_json::Value {
        serde_json::json!({"since_last": self.since_last, "coh_hold": self.coh_hold, "fb_n": self.fb_n, "wh_fol": self.wh_fol, "wh_dumps": self.wh_dumps,
            "q": self.flags(fol), "all4": self.quiet(fol)})
    }
}

/// the signals at a trigger, computed right after `det.trade` took the trigger trade (its `prev_tr` is that trade's): the token's
/// wallets before the trigger (the whale's own trigger buy taken out), the whale's history in `book` (None: no history kept)
#[allow(clippy::too_many_arguments)]
pub fn arm_signals(det: &Detector, book: Option<&DumpBook>, mint: &Pk, whale: &Pk, s0: u64, trig_tok: u64, t0: u64, coh: &FxHashSet<Pk>, fb: &FxHashSet<Pk>) -> Option<ArmSig> {
    let (coh_hold, fb_n) = det.holders(mint, whale, trig_tok, coh, fb)?;
    let since_last = if det.prev_tr == 0 { 9999 } else { s0.saturating_sub(det.prev_tr) };
    let (wh_fol, wh_dumps) = book.map(|b| b.whale(whale, s0, t0)).unwrap_or((-1.0, 0));
    Some(ArmSig { since_last, coh_hold, fb_n, wh_fol, wh_dumps })
}

/// the stop rule (C5): N slots, M other trades
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct QStop { pub n: u64, pub m: u32 }

impl QStop {
    /// "N:M" (owner config 6:2): N 1..=30 slots, M 1..=100 trades
    pub fn parse(s: &str) -> Result<QStop, String> {
        let (a, b) = s.split_once(':').ok_or_else(|| format!("'{s}' is not N:M (e.g. 6:2)"))?;
        let n: u64 = a.trim().parse().map_err(|_| format!("'{s}': N is not a whole number"))?;
        let m: u32 = b.trim().parse().map_err(|_| format!("'{s}': M is not a whole number"))?;
        if !(1..=30).contains(&n) || !(1..=100).contains(&m) { return Err(format!("'{s}': N must be 1..30 slots and M 1..100 trades")); }
        Ok(QStop { n, m })
    }
    /// a trade counts as "other" when it is neither the whale's nor ours
    pub fn other(user: &Pk, whale: &Pk, us: &Pk) -> bool { user != whale && user != us }
    /// None: not decided yet (slot < trigger slot + N); Some(true): stop the window now; Some(false): it never stops
    pub fn due(&self, cur_slot: u64, trig_slot: u64, others: u32) -> Option<bool> { (cur_slot >= trig_slot + self.n).then_some(others < self.m) }
}

/// the arm rule's schedule: on once the history covers `warm_ns` (the live feed's time since the start, plus what a preload
/// brought in); a failed / absent preload brings 0 (the plain warm-up)
pub fn arm_on(now_ns: u64, start_ns: u64, warm_ns: u64, covered_ns: u64) -> bool { now_ns >= start_ns.saturating_add(warm_ns.saturating_sub(covered_ns)) }

// ---- the raw recording (collector chunks) --------------------------------------------------------------------------------

/// one recorded tx with pump trade events (chain position, block time in seconds, the trades / creates decoded as the live feed
/// decodes them: `dip::trade_events` / `create_events` on the "Program data:" strings)
#[derive(Clone, Debug)]
pub struct RecTx { pub s: u64, pub i: u32, pub bt: i64, pub trades: Vec<TradeEvent>, pub creates: Vec<CreateEvent>, pub mayhem: bool }

#[derive(Clone, Debug, Default)]
pub struct ReadStats {
    pub chunks: u64, pub lines: u64, pub ok_lines: u64, pub txs: u64, pub trades: u64, pub dups: u64, pub bad_lines: u64, pub partial_tails: u64,
    /// chunks whose gzip stream ended early (normal for the one being written)
    pub truncated: Vec<String>, pub bytes_gz: u64,
}

/// the run directories under the given path: a `current_run` file (its parent holds run_* dirs), a run dir (one with txs/: its
/// parent's run_* dirs), or the base dir itself; every run_* dir with a txs/ dir, sorted by name
pub fn run_dirs(path: &Path) -> Result<Vec<PathBuf>, String> {
    let base: PathBuf = if path.is_file() {
        path.parent().map(|p| p.to_path_buf()).unwrap_or_else(|| PathBuf::from("."))
    } else if path.join("txs").is_dir() {
        path.parent().map(|p| p.to_path_buf()).ok_or("a run dir without a parent")?
    } else if path.is_dir() { path.to_path_buf() } else { return Err(format!("{} does not exist", path.display())); };
    let mut v: Vec<PathBuf> = std::fs::read_dir(&base).map_err(|e| format!("{}: {e}", base.display()))?.filter_map(|x| x.ok()).map(|x| x.path())
        .filter(|p| p.file_name().and_then(|n| n.to_str()).is_some_and(|n| n.starts_with("run_")) && p.join("txs").is_dir()).collect();
    v.sort();
    if v.is_empty() { return Err(format!("no run_*/txs directory under {}", base.display())); }
    Ok(v)
}

/// a run's chunk files with a start time in [lo, hi] (unix s, from the name txs_<unix>.jsonl.gz), oldest first
pub fn chunks(run: &Path, lo: u64, hi: u64) -> Vec<(u64, PathBuf)> {
    let mut v: Vec<(u64, PathBuf)> = std::fs::read_dir(run.join("txs")).into_iter().flatten().filter_map(|x| x.ok()).filter_map(|x| {
        let n = x.file_name().to_str()?.to_string();
        let ts: u64 = n.strip_prefix("txs_")?.strip_suffix(".jsonl.gz")?.parse().ok()?;
        (lo <= ts && ts <= hi).then(|| (ts, x.path()))
    }).collect();
    v.sort();
    v
}

#[derive(serde::Deserialize)]
struct Line { s: u64, i: u64, #[serde(default)] bt: Option<i64>, #[serde(default)] ev: serde_json::Value, #[serde(default)] ixn: Option<Vec<String>> }

/// a successful tx line (the study's read_chunk: '"err":null' in the line and not '"ev":[]') -> its pump events, decoded as the live
/// feed decodes its logs; Err: not JSON (a partial last line of a chunk being written, or damage)
fn parse_line(line: &[u8], creates: bool) -> Result<Option<RecTx>, ()> {
    let head = &line[..line.len().min(320)];
    let ok = find(head, b"\"err\":null") || (line.len() > head.len() && find(line, b"\"err\":null"));
    if !ok || find(line, b"\"ev\":[]") { return Ok(None); }
    let l: Line = serde_json::from_slice(line).map_err(|_| ())?;
    let strs: Vec<String> = match l.ev {
        serde_json::Value::Array(a) => a.into_iter().filter_map(|x| x.as_str().map(|s| s.to_string())).collect(),
        serde_json::Value::String(s) => serde_json::from_str::<Vec<String>>(&s).unwrap_or_default(),
        _ => Vec::new(),
    };
    let logs: Vec<String> = strs.into_iter().map(|s| format!("Program data: {s}")).collect();
    let trades = dip::trade_events(&logs);
    let cr = if creates { dip::create_events(&logs) } else { Vec::new() };
    if trades.is_empty() && cr.is_empty() { return Ok(None); }
    let mayhem = !cr.is_empty() && l.ixn.as_ref().is_some_and(|v| v.iter().any(|x| x == "InitializeMayhemState"));
    Ok(Some(RecTx { s: l.s, i: l.i as u32, bt: l.bt.unwrap_or(0), trades, creates: cr, mayhem }))
}

fn find(h: &[u8], n: &[u8]) -> bool { h.windows(n.len()).any(|w| w == n) }

/// one run's txs in order: its chunks one after the other (each through `gzip -dc`: no new dependency; a chunk still being written
/// ends early: what is readable is used), every tx after the last one handed out
struct RunReader {
    run: PathBuf, files: Vec<(u64, PathBuf)>, next_file: usize, cur: Option<(std::process::Child, std::io::BufReader<std::process::ChildStdout>, String)>,
    last: Option<(u64, u32)>, buf: Vec<u8>, creates: bool, lo: u64, hi: u64,
    /// the reader handed out everything it could read; `stale`: its last chunk is not written to any more (or offline)
    exhausted: bool,
}

impl RunReader {
    fn new(run: PathBuf, lo: u64, hi: u64, creates: bool) -> RunReader {
        let files = chunks(&run, lo, hi);
        RunReader { run, files, next_file: 0, cur: None, last: None, buf: Vec::with_capacity(1 << 16), creates, lo, hi, exhausted: false }
    }

    fn open(&mut self, st: &mut ReadStats) -> Result<bool, String> {
        let Some((_, p)) = self.files.get(self.next_file).cloned() else { return Ok(false) };
        self.next_file += 1;
        let mut ch = std::process::Command::new("gzip").arg("-dc").arg("--").arg(&p).stdout(std::process::Stdio::piped()).stderr(std::process::Stdio::null())
            .stdin(std::process::Stdio::null()).spawn().map_err(|e| format!("gzip -dc {}: {e}", p.display()))?;
        let out = ch.stdout.take().ok_or("gzip: no stdout")?;
        st.chunks += 1;
        st.bytes_gz += std::fs::metadata(&p).map(|m| m.len()).unwrap_or(0);
        self.cur = Some((ch, std::io::BufReader::with_capacity(1 << 20, out), p.display().to_string()));
        Ok(true)
    }

    /// the chunk ended: its exit status (an early end = truncated), its pages dropped from the page cache (a 24 h read must not
    /// evict the server's cache)
    fn close(&mut self, st: &mut ReadStats) {
        if let Some((mut ch, _, name)) = self.cur.take() {
            let ok = ch.wait().map(|s| s.success()).unwrap_or(false);
            if !ok { st.truncated.push(name.clone()); }
            if let Ok(f) = std::fs::File::open(&name) {
                use std::os::unix::io::AsRawFd;
                unsafe { libc::posix_fadvise(f.as_raw_fd(), 0, 0, libc::POSIX_FADV_DONTNEED); }
            }
        }
    }

    /// the next tx after `last`, or None when everything readable now was read
    fn next(&mut self, st: &mut ReadStats) -> Result<Option<RecTx>, String> {
        loop {
            if self.cur.is_none() && !self.open(st)? { self.exhausted = true; return Ok(None); }
            self.buf.clear();
            let n = { let (_, r, _) = self.cur.as_mut().unwrap(); r.read_until(b'\n', &mut self.buf).unwrap_or(0) };
            if n == 0 { self.close(st); continue; }
            st.lines += 1;
            let complete = self.buf.last() == Some(&b'\n');
            match parse_line(&self.buf, self.creates) {
                Ok(None) => continue,
                Ok(Some(tx)) => {
                    st.ok_lines += 1;
                    if self.last.is_some_and(|l| (tx.s, tx.i) <= l) { continue; }
                    self.last = Some((tx.s, tx.i));
                    return Ok(Some(tx));
                }
                Err(()) => { if complete { st.bad_lines += 1; } else { st.partial_tails += 1; } continue; }
            }
        }
    }

    /// more may have been written since: re-list the run's chunks from the one read last (it is read again from its start; every tx
    /// up to `last` is skipped)
    fn refresh(&mut self, st: &mut ReadStats) {
        self.close(st);
        let from = self.files.get(self.next_file.saturating_sub(1)).map(|x| x.0).unwrap_or(self.lo);
        self.files = chunks(&self.run, from, self.hi);
        self.next_file = 0;
        self.exhausted = false;
    }

    /// the run's newest chunk was last written more than `quiet` ago (the collector moved on or stopped)
    fn stale(&self, quiet: Duration) -> bool {
        let newest = chunks(&self.run, self.lo, self.hi).pop();
        newest.and_then(|(_, p)| std::fs::metadata(p).ok()?.modified().ok()?.elapsed().ok()).is_none_or(|e| e > quiet)
    }
}

/// a read stopped in the middle of a chunk: its gzip is stopped and reaped (no zombie in a long-running engine)
impl Drop for RunReader {
    fn drop(&mut self) { if let Some((mut ch, _, _)) = self.cur.take() { let _ = ch.kill(); let _ = ch.wait(); } }
}

/// every run's txs merged in chain order (each run's chunks are in slot order: the collector writes blocks in order), a tx recorded
/// by two runs (it touches tokens of both) once
pub struct Recording { rs: Vec<RunReader>, heads: Vec<Option<RecTx>>, done: Vec<bool>, last: Option<(u64, u32)>, pub st: ReadStats, offline: bool, bt_lo: i64, bt_hi: i64 }

impl Recording {
    /// `ts_lo..=ts_hi`: the chunk files (by their name's start time); `bt_lo..=bt_hi`: the txs (block time; the study's span filter);
    /// `offline`: every chunk is final (a test / replay: never wait for more)
    pub fn open(runs: &[PathBuf], ts_lo: u64, ts_hi: u64, bt_lo: i64, bt_hi: i64, creates: bool, offline: bool) -> Recording {
        let rs: Vec<RunReader> = runs.iter().map(|r| RunReader::new(r.clone(), ts_lo, ts_hi, creates)).collect();
        let n = rs.len();
        Recording { rs, heads: vec![None; n], done: vec![false; n], last: None, st: ReadStats::default(), offline, bt_lo, bt_hi }
    }
    pub fn files(&self) -> usize { self.rs.iter().map(|r| r.files.len()).sum() }

    /// the next tx in chain order. Ok(None): offline: the end; live: a run still being written has nothing more to read now (the
    /// caller waits and calls `refresh`)
    pub fn next(&mut self) -> Result<Option<RecTx>, String> {
        loop {
            let mut waiting = false;
            for k in 0..self.rs.len() {
                if self.heads[k].is_some() || self.done[k] { continue; }
                loop {
                    match self.rs[k].next(&mut self.st)? {
                        Some(tx) => { if tx.bt < self.bt_lo || tx.bt > self.bt_hi { continue; } self.heads[k] = Some(tx); }
                        None => { if self.offline || self.rs[k].stale(Duration::from_secs(600)) { self.done[k] = true; } else { waiting = true; } }
                    }
                    break;
                }
            }
            if waiting { return Ok(None); }
            let Some(k) = (0..self.rs.len()).filter(|&k| self.heads[k].is_some()).min_by_key(|&k| { let h = self.heads[k].as_ref().unwrap(); (h.s, h.i) }) else { return Ok(None) };
            let tx = self.heads[k].take().unwrap();
            if self.last.is_some_and(|l| (tx.s, tx.i) <= l) { self.st.dups += 1; continue; }
            self.last = Some((tx.s, tx.i));
            self.st.txs += 1;
            self.st.trades += tx.trades.len() as u64;
            return Ok(Some(tx));
        }
    }

    /// the runs still being written: read their newest chunk again (more of it is readable now; what was handed out is skipped)
    pub fn refresh(&mut self) {
        for k in 0..self.rs.len() { if !self.done[k] && self.heads[k].is_none() && self.rs[k].exhausted { self.rs[k].refresh(&mut self.st); } }
    }

    /// is everything read (offline end, or every run final)?
    pub fn finished(&self) -> bool { self.done.iter().all(|d| *d) && self.heads.iter().all(|h| h.is_none()) }
}

// ---- the preload ---------------------------------------------------------------------------------------------------------

/// what the preload thread needs: the recording path, the history length, the engine's start (unix ns), the cut slot set by the
/// live side (0 until the live feed's first trade: the cut is that slot + 1), the time limit
#[derive(Clone, Debug)]
pub struct PreloadCfg { pub path: PathBuf, pub hist_ns: u64, pub start_unix_ns: u64, pub timeout: Duration }

#[derive(Debug)]
pub struct PreloadOut {
    pub book: DumpBook, pub cut: u64, pub st: ReadStats, pub secs: f64,
    /// block time (s) of the first tx used and of the last one below the cut: the history it brings is the span between them
    pub bt_first: i64, pub bt_cut: i64, pub covered_ns: u64,
    /// the live book's first slot was not known when it was needed (seconds waited)
    pub waited_cut_s: f64, pub waited_tail_s: f64,
}

/// the max share of unreadable (complete, non-JSON) lines before the preload is refused
pub const PRELOAD_BAD_MAX: f64 = 0.001;

/// BUILD THE PRELOAD (a background thread; never the event loop): the last `hist_ns` of the recording through the live path's
/// DumpBook rules. Dumps are taken below the cut only (cut = the live feed's first slot + 1, from `cut_slot`), and the recording is
/// read until a tx at slot >= cut + 2 (every follower window below the cut is then complete: the recording is in slot order).
/// Err: no recording / unreadable / too many bad lines / the recording did not reach cut + 2 before the time limit (the caller falls
/// back to the plain warm-up).
pub fn preload(cfg: &PreloadCfg, cut_slot: &AtomicU64) -> Result<PreloadOut, String> {
    let t0 = Instant::now();
    let runs = run_dirs(&cfg.path)?;
    let start_s = cfg.start_unix_ns / 1_000_000_000;
    let hist_s = cfg.hist_ns / 1_000_000_000;
    // chunks that may hold txs of the history (a chunk spans 5 min of writing; the collector lags the chain)
    let ts_lo = start_s.saturating_sub(hist_s + 900);
    let bt_lo = start_s as i64 - hist_s as i64 - 60;
    let mut rec = Recording::open(&runs, ts_lo, u64::MAX, bt_lo, i64::MAX, false, false);
    if rec.files() == 0 { return Err(format!("no recording chunk of the last {} h under {}", hist_s / 3600, cfg.path.display())); }
    let mut book = DumpBook::new(cfg.hist_ns);
    let (mut cut, mut bt_first, mut bt_cut) = (0u64, 0i64, 0i64);
    let (mut waited_cut, mut waited_tail) = (Duration::ZERO, Duration::ZERO);
    loop {
        if t0.elapsed() > cfg.timeout { return Err(format!("time limit {:.0} s: the recording reached slot {} (cut {cut})", cfg.timeout.as_secs_f64(), book.max_slot())); }
        let Some(tx) = rec.next()? else {
            if rec.finished() { return Err(format!("the recording ended at slot {} before the cut + 2 ({}): is the collector running?", book.max_slot(), cut + 2)); }
            let w = Instant::now();
            std::thread::sleep(Duration::from_secs(2));
            waited_tail += w.elapsed();
            rec.refresh();
            continue;
        };
        // the cut as soon as the live side set it (its first trade); the recent part cannot go without it (the old chunks can)
        if cut == 0 { cut = cut_slot.load(Ordering::SeqCst); book.cut = if cut == 0 { u64::MAX } else { cut }; }
        if cut == 0 && tx.bt + 120 >= start_s as i64 {
            let w = Instant::now();
            while cut_slot.load(Ordering::SeqCst) == 0 {
                if t0.elapsed() > cfg.timeout { return Err("the live feed never reported its first slot".into()); }
                std::thread::sleep(Duration::from_millis(100));
            }
            waited_cut += w.elapsed();
            cut = cut_slot.load(Ordering::SeqCst);
            book.cut = cut;
        }
        if cut != 0 && tx.s >= cut + FOL_SLOTS { break; }
        if bt_first == 0 { bt_first = tx.bt; }
        if cut == 0 || tx.s < cut { bt_cut = tx.bt; }
        for (j, e) in tx.trades.iter().enumerate() { book.ingest(e, tx.s, tx.i, j as i32, tx.bt.max(0) as u64 * 1_000_000_000); }
        if rec.st.ok_lines > 10_000 && rec.st.bad_lines as f64 > PRELOAD_BAD_MAX * rec.st.ok_lines as f64 {
            return Err(format!("{} unreadable lines of {} in the recording", rec.st.bad_lines, rec.st.ok_lines));
        }
    }
    // a truncated chunk that is not a run's newest one is damage (the newest one is being written)
    let newest: FxHashSet<String> = runs.iter().filter_map(|r| chunks(r, 0, u64::MAX).pop()).map(|x| x.1.display().to_string()).collect();
    let damaged: Vec<&String> = rec.st.truncated.iter().filter(|x| !newest.contains(*x)).collect();
    if damaged.len() > 2 { return Err(format!("{} damaged chunks (first {})", damaged.len(), damaged[0])); }
    book.close_all();
    let covered_ns = ((bt_cut - bt_first).max(0) as u64 * 1_000_000_000).min(cfg.hist_ns);
    Ok(PreloadOut { book, cut, st: rec.st, secs: t0.elapsed().as_secs_f64(), bt_first, bt_cut, covered_ns, waited_cut_s: waited_cut.as_secs_f64(), waited_tail_s: waited_tail.as_secs_f64() })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::presend_live::{Det, Trade};

    fn pk(n: u8) -> Pk { [n; 32] }
    fn te(mint: u8, user: u8, buy: bool, sol: u64, tok: u64, vsol: u64, vtok: u64) -> TradeEvent { TradeEvent { mint: pk(mint), sol, tok, buy, user: pk(user), vsol, vtok, fbps: 95, cbps: 30 } }

    /// a sell of `sol` at a curve (v, t) before it: the post state as pump's constant product gives it
    fn sell(mint: u8, user: u8, v: u64, t: u64, sol: u64) -> TradeEvent {
        let tok = ((t as u128 * sol as u128) / (v as u128 - sol as u128)) as u64;
        te(mint, user, false, sol, tok, v - sol, t + tok)
    }
    fn buy(mint: u8, user: u8, v: u64, t: u64, sol: u64) -> TradeEvent {
        let tok = ((t as u128 * sol as u128) / (v as u128 + sol as u128)) as u64;
        te(mint, user, true, sol, tok, v + sol, t - tok)
    }
    const S: u64 = 1_000_000_000;

    /// the dump rule's edges: 0.3 SOL, the 100 SOL curve, the 8% drop, buys never
    #[test]
    fn dump_rule_edges() {
        let (v, t) = (30 * S, 1_000_000_000_000_000u64);
        // 3 SOL out of 30: price falls ~19%: a dump
        let d = sell(1, 2, v, t, 3 * S);
        assert!(is_dump(d.buy, d.sol, d.tok, d.vsol, d.vtok));
        // 0.29 SOL: too small even though the drop would count on a tiny curve
        let d = sell(1, 2, 3 * S, t, 290_000_000);
        assert!(!is_dump(d.buy, d.sol, d.tok, d.vsol, d.vtok));
        // a 1.2 SOL sell on 30 SOL: ~7.8% drop: not a dump; 1.3 SOL ~8.4%: a dump
        let d = sell(1, 2, v, t, 1_200_000_000);
        assert!(!is_dump(d.buy, d.sol, d.tok, d.vsol, d.vtok));
        let d = sell(1, 2, v, t, 1_300_000_000);
        assert!(is_dump(d.buy, d.sol, d.tok, d.vsol, d.vtok));
        // post curve at 100 SOL or more: not a dump
        let d = sell(1, 2, 120 * S, t, 20 * S);
        assert_eq!(d.vsol, 100 * S);
        assert!(!is_dump(d.buy, d.sol, d.tok, d.vsol, d.vtok));
        let d = sell(1, 2, 115 * S, t, 16 * S);
        assert!(is_dump(d.buy, d.sol, d.tok, d.vsol, d.vtok));
        // a buy never; vtok <= tok never
        assert!(!is_dump(true, 3 * S, 1, v, t));
        assert!(!is_dump(false, 3 * S, 5, 10 * S, 5));
        // exactly 0.92: a dump (the Python skips only p > 0.92 x pre)
        let (vs, vt, sol, tok) = (92u64 * S, 1000u64, 8 * S, 0u64);
        assert!((vs as f64 / vt as f64) <= 0.92 * ((vs + sol) as f64 / (vt - tok).max(1) as f64));
    }

    /// followers: distinct, not the seller, after the dump (chain position), its slot + 2; a later dump of the same seller; the
    /// query's s + 2 < s0 and the history window; expiry
    #[test]
    fn book_followers_window_and_query() {
        let h = 24 * 3600 * S;
        let mut b = DumpBook::new(h);
        let (v, t) = (30 * S, 1_000_000_000_000_000u64);
        let t0 = 1_800_000_000 * S;
        let w = 9u8;                 // the whale (seller)
        // a buy BEFORE the dump in the same slot (lower index): not a follower
        b.ingest(&buy(1, 20, v, t, S), 100, 5, 0, t0);
        b.ingest(&sell(1, w, v, t, 3 * S), 100, 10, 0, t0);
        assert_eq!(b.dumps(), 1);
        // same tx, later event: a follower; the seller's own buy: not; a sell: not
        b.ingest(&buy(1, 21, v, t, S), 100, 10, 1, t0);
        b.ingest(&buy(1, w, v, t, S), 100, 11, 0, t0);
        b.ingest(&sell(1, 22, v, t, S / 10), 101, 0, 0, t0);
        // the same buyer twice: once; another token: not
        b.ingest(&buy(1, 21, v, t, S), 101, 3, 0, t0);
        b.ingest(&buy(2, 23, v, t, S), 101, 4, 0, t0);
        // slot + 2: counts; slot + 3: not
        b.ingest(&buy(1, 24, v, t, S), 102, 0, 0, t0);
        b.ingest(&buy(1, 25, v, t, S), 103, 0, 0, t0);
        // a LATE arrival of slot + 1 (after slot + 3 was seen): still counted (the window closes CLOSE_MARGIN slots later)
        b.ingest(&buy(1, 26, v, t, S), 101, 9, 0, t0);
        assert_eq!(b.whale(&pk(w), 200, t0), (3.0, 1), "followers 21, 24, 26");
        // the query: the dump's window must be closed before the trigger slot (s + 2 < s0)
        assert_eq!(b.whale(&pk(w), 102, t0), (-1.0, 0));
        assert_eq!(b.whale(&pk(w), 103, t0), (3.0, 1));
        // the window closes once the newest slot passes s + 2 + margin: then nothing more counts
        b.ingest(&buy(3, 30, v, t, S), 107, 0, 0, t0);
        assert_eq!(b.open_windows(), 0);
        b.ingest(&buy(1, 27, v, t, S), 102, 50, 0, t0);
        assert_eq!(b.whale(&pk(w), 200, t0), (3.0, 1));
        // a second dump, 1 follower: mean 2.0
        b.ingest(&sell(1, w, v, t, 2 * S), 300, 1, 0, t0 + 10 * S);
        b.ingest(&buy(1, 40, v, t, S), 300, 2, 0, t0 + 10 * S);
        assert_eq!(b.whale(&pk(w), 400, t0 + 10 * S), (2.0, 2));
        // the history window: at t0 + 24 h + 5 s only the second dump is in it
        assert_eq!(b.whale(&pk(w), 400, t0 + h + 5 * S), (1.0, 1));
        // expiry: a trade 24 h + slack later drops both; the seller is forgotten
        b.ingest(&buy(5, 50, v, t, S), 900_000, 0, 0, t0 + h + 200 * S);
        assert_eq!((b.dumps(), b.sellers()), (0, 0));
        assert_eq!(b.whale(&pk(w), 900_001, t0 + h + 200 * S), (-1.0, 0));
        // the cut: no dump at or above it
        let mut c = DumpBook::new(h);
        c.cut = 500;
        c.ingest(&sell(1, w, v, t, 3 * S), 499, 0, 0, t0);
        c.ingest(&sell(1, w, v, t, 3 * S), 500, 0, 0, t0);
        assert_eq!(c.dumps(), 1);
    }

    /// bounded memory: a day of synthetic dumps (one every 2 slots, 3 buyers each) holds only the last 24 h; O(1) work per trade
    #[test]
    fn book_bounded_over_two_days() {
        let h = 24 * 3600 * S;
        let mut b = DumpBook::new(h);
        let (v, t) = (30 * S, 1_000_000_000_000_000u64);
        let t0 = 1_800_000_000 * S;
        let mut peak = 0usize;
        let n = 2 * 24 * 3600 * 1000 / 212 / 2;           // two days of slots, a dump every 2 slots
        let t1 = Instant::now();
        for k in 0..n as u64 {
            let s = 1_000 + 2 * k; let tt = t0 + 2 * k * 212_000_000;
            b.ingest(&sell((k % 200) as u8, (k % 97) as u8, v, t, 3 * S), s, 1, 0, tt);
            for f in 0..3u8 { b.ingest(&buy((k % 200) as u8, 100 + f, v, t, S / 10), s + 1, f as u32, 0, tt + 212_000_000); }
            peak = peak.max(b.dumps());
        }
        let per = t1.elapsed().as_secs_f64() * 1e9 / (4 * n) as f64;
        // 24 h of dumps every 2 slots of 212 ms = ~203,773 (+ the expiry slack)
        let day = (24 * 3600 * 1000 / 212 / 2) as usize;
        assert!(peak <= day + 2_000 && peak >= day, "peak {peak} vs a day {day}");
        assert!(b.whale(&pk(5), u64::MAX / 2, t0 + 2 * (n as u64) * 212_000_000).0 > 2.9);
        eprintln!("DumpBook: {n} dumps over 2 days, peak {peak} kept, {:.0} ns per trade, ~{:.1} MB at the end", per, b.mem_bytes() as f64 / 1e6);
    }

    fn tr(mint: u8, s: u64, i: u32, user: u8, buy_: bool, sol: u64, tok: u64, v: u64, t: u64) -> Trade {
        Trade { mint: pk(mint), s, i, j: 0, sig: [0; 64], user: pk(user), buy: buy_, sol, tok, vsol: v, vtok: t, fbps: 95, cbps: 30, t_rx: 0 }
    }

    /// the arm signals from the detector: pre-trigger balances (the whale's trigger buy taken out), cohort HOLDERS (a seller-out
    /// does not count), follower bots that ever traded it, since_last (any wallet, the trigger's own slot), the whale's history
    #[test]
    fn arm_signals_from_detector() {
        let mint = 7u8; let (cre, sgn) = (pk(1), pk(2));
        let mut d = Detector::new(5.0);
        d.create(pk(mint), 100, cre, sgn, false);
        let (mut v, mut t) = (30 * S, 1_073_000_000_000_000u64);
        let mut out = Vec::new();
        let mut step = |d: &mut Detector, s: u64, i: u32, user: u8, b_: bool, amt: u64, out: &mut Vec<Det>| -> Trade {
            let (sol, tok) = if b_ { let q = (t as u128 * amt as u128 / (v + amt) as u128) as u64; v += amt; t -= q; (amt, q) } else { let o = (v as u128 * amt as u128 / (t + amt) as u128) as u64; v -= o; t += amt; (o, amt) };
            let x = tr(mint, s, i, user, b_, sol, tok, v, t);
            out.clear();
            d.trade(&x, out);
            x
        };
        step(&mut d, 100, 1, 1, true, 2 * S, &mut out);                   // creator's dev buy
        let c1 = step(&mut d, 101, 1, 40, true, S / 2, &mut out);         // cohort wallet 40 buys ...
        step(&mut d, 102, 1, 40, false, c1.tok, &mut out);                // ... and sells out: not holding
        step(&mut d, 103, 1, 41, true, S / 2, &mut out);                  // cohort wallet 41 holds
        step(&mut d, 104, 1, 50, true, S / 5, &mut out);                  // follower bot 50
        step(&mut d, 105, 2, 9, true, S / 10, &mut out);                  // the whale's small first buy (it traded before)
        assert_eq!(d.prev_tr, 104);
        let x = step(&mut d, 110, 7, 9, true, 4 * S, &mut out);           // the whale crosses 5%: the trigger
        assert!(matches!(out.as_slice(), [Det::Trigger { .. }]), "{out:?}");
        let coh: FxHashSet<Pk> = [pk(40), pk(41), pk(9)].into_iter().collect();
        let fb: FxHashSet<Pk> = [pk(50), pk(9), pk(77)].into_iter().collect();
        let mut book = DumpBook::new(24 * 3600 * S);
        // the whale's earlier dumps on other tokens: 4 and 1 followers -> 2.5
        let t0 = 1_800_000_000 * S;
        for (k, nf) in [(0u64, 4u8), (1, 1)] {
            let s = 50 + 10 * k;
            book.ingest(&sell(3, 9, 30 * S, 1_000_000_000_000_000, 3 * S), s, 0, 0, t0);
            for f in 0..nf { book.ingest(&buy(3, 60 + f, 30 * S, 1_000_000_000_000_000, S), s + 1, f as u32, 0, t0); }
        }
        let a = arm_signals(&d, Some(&book), &pk(mint), &pk(9), x.s, x.tok, t0 + S, &coh, &fb).unwrap();
        // since_last 110 - 105 = 5; cohort holders: 41 and the whale (it held before its trigger buy); follower bots 50 + the whale
        assert_eq!(a, ArmSig { since_last: 5, coh_hold: 2, fb_n: 2, wh_fol: 2.5, wh_dumps: 2 });
        assert_eq!(a.flags(2.24), [true, false, false, false]);
        assert!(!a.quiet(2.24));
        // a whale whose ONLY trade is its trigger: neither a holder nor a trader before it; no history: -1; a trade earlier in the
        // trigger's slot: since_last 0
        let mut d2 = Detector::new(5.0);
        d2.create(pk(8), 100, cre, sgn, false);
        let (v0, t0_) = (30 * S, 1_073_000_000_000_000u64);
        let mut o2 = Vec::new();
        d2.trade(&tr(8, 100, 1, 1, true, S, 34_000_000_000_000, v0 + S, t0_ - 34_000_000_000_000), &mut o2);
        d2.trade(&tr(8, 120, 3, 33, true, S / 10, 3_000_000_000_000, v0 + S + S / 10, t0_ - 37_000_000_000_000), &mut o2);
        d2.trade(&tr(8, 120, 9, 9, true, 4 * S, 120_000_000_000_000, v0 + 5 * S, t0_ - 157_000_000_000_000), &mut o2);
        assert!(matches!(o2.as_slice(), [Det::Trigger { .. }]), "{o2:?}");
        let b = arm_signals(&d2, Some(&DumpBook::new(S)), &pk(8), &pk(9), 120, 120_000_000_000_000, t0, &coh, &fb).unwrap();
        assert_eq!(b, ArmSig { since_last: 0, coh_hold: 0, fb_n: 0, wh_fol: -1.0, wh_dumps: 0 });
        assert_eq!(b.flags(2.24), [false, true, true, true]);
        // an unfollowed token: None
        assert!(arm_signals(&d2, None, &pk(99), &pk(9), 1, 1, 1, &coh, &fb).is_none());
        // no earlier trade at all (the study's 9999)
        let mut d3 = Detector::new(5.0);
        d3.create(pk(4), 100, cre, sgn, false);
        d3.trade(&tr(4, 100, 4, 9, true, 6 * S, 160_000_000_000_000, v0 + 6 * S, t0_ - 160_000_000_000_000), &mut o2);
        assert_eq!(arm_signals(&d3, None, &pk(4), &pk(9), 100, 160_000_000_000_000, t0, &coh, &fb).unwrap().since_last, 9999);
    }

    /// the stop rule N:M and its parsing; the arm rule's schedule (warm-up, a preload's coverage)
    #[test]
    fn stop_rule_and_schedule() {
        let q = QStop::parse("6:2").unwrap();
        assert_eq!(q, QStop { n: 6, m: 2 });
        assert_eq!(q.due(105, 100, 0), None, "before trigger + 6: undecided");
        assert_eq!(q.due(106, 100, 1), Some(true), "at + 6 with 1 other trade: stop");
        assert_eq!(q.due(106, 100, 2), Some(false), "2 other trades: never");
        assert_eq!(q.due(140, 100, 0), Some(true));
        for bad in ["6", "6:", ":2", "0:2", "6:0", "31:2", "6:101", "a:b", "6.5:2"] { assert!(QStop::parse(bad).is_err(), "{bad}"); }
        assert_eq!(QStop::parse(" 4 : 3 ").unwrap(), QStop { n: 4, m: 3 });
        let (w, u, o) = (pk(1), pk(2), pk(3));
        assert!(!QStop::other(&w, &w, &u) && !QStop::other(&u, &w, &u) && QStop::other(&o, &w, &u));
        let m = 60_000_000_000u64;
        assert!(!arm_on(10 * m, 0, 60 * m, 0) && arm_on(60 * m, 0, 60 * m, 0), "plain warm-up: 60 min");
        assert!(arm_on(1, 0, 60 * m, 24 * 60 * m), "a full preload: at once");
        assert!(!arm_on(39 * m, 0, 60 * m, 20 * m) && arm_on(40 * m, 0, 60 * m, 20 * m), "a 20-min preload: 40 min more");
    }

    // ---- the recording reader and the preload, on synthetic chunks -------------------------------------------------------

    fn b64(raw: &[u8]) -> String { use base64::Engine as _; base64::engine::general_purpose::STANDARD.encode(raw) }
    /// a TradeEvent's raw bytes (the 225+ byte layout's first 225 bytes; fee fields 0)
    fn raw_trade(e: &TradeEvent) -> Vec<u8> {
        let mut r = vec![0u8; 225];
        r[..8].copy_from_slice(&dip::TRADE_EVENT_DISC);
        r[8..40].copy_from_slice(&e.mint);
        r[40..48].copy_from_slice(&e.sol.to_le_bytes()); r[48..56].copy_from_slice(&e.tok.to_le_bytes());
        r[56] = e.buy as u8; r[57..89].copy_from_slice(&e.user);
        r[97..105].copy_from_slice(&e.vsol.to_le_bytes()); r[105..113].copy_from_slice(&e.vtok.to_le_bytes());
        r
    }
    fn line(s: u64, i: u32, bt: i64, ok: bool, evs: &[&TradeEvent]) -> String {
        let ev: Vec<String> = evs.iter().map(|e| b64(&raw_trade(e))).collect();
        format!("{{\"s\":{s},\"i\":{i},\"bt\":{bt},\"sig\":\"{}\",\"err\":{},\"fee\":5000,\"ev\":{}}}\n", "x".repeat(88), if ok { "null" } else { "{\"InstructionError\":[1,{\"Custom\":6042}]}" },
                serde_json::to_string(&ev).unwrap())
    }
    fn gz(path: &Path, text: &str) {
        use std::io::Write;
        let mut ch = std::process::Command::new("gzip").arg("-c").stdin(std::process::Stdio::piped()).stdout(std::process::Stdio::piped()).spawn().unwrap();
        ch.stdin.take().unwrap().write_all(text.as_bytes()).unwrap();
        let out = ch.wait_with_output().unwrap();
        std::fs::write(path, out.stdout).unwrap();
    }

    /// a synthetic recording: two runs overlapping in slots (a tx in both), failed lines, an empty-ev line, a damaged line, a
    /// truncated newest chunk; the reader's merge = chain order, each tx once; the PRELOAD = the live path's book on the same txs;
    /// the MERGE at the cut = one live book over everything
    #[test]
    fn recording_reader_preload_and_merge() {
        let dir = std::env::temp_dir().join(format!("quiet_rec_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        let (ra, rb) = (dir.join("run_20261026_1415"), dir.join("run_20261027_1410"));
        std::fs::create_dir_all(ra.join("txs")).unwrap(); std::fs::create_dir_all(rb.join("txs")).unwrap();
        std::fs::create_dir_all(dir.join("smoke/txs")).unwrap();
        std::fs::write(dir.join("current_run"), "run_20261027_1410\n").unwrap();
        // a market: tokens 1..6, dumps by sellers 9 / 10, buyers 20.., two runs (A: tokens 1-3, B: tokens 4-6, slots overlapping)
        let (v, t) = (30 * S, 1_000_000_000_000_000u64);
        let bt0 = 1_793_000_000i64;
        let mut txs: Vec<(u64, u32, Vec<TradeEvent>, bool)> = Vec::new();     // (slot, idx, trades, in run B)
        let mut k = 0u32;
        for s in 1_000u64..1_400 {
            for m in 1..=6u8 {
                k += 1;
                let mut ev = Vec::new();
                if (s + m as u64) % 7 == 0 { ev.push(sell(m, 9 + (m % 2), v, t, 3 * S)); }
                if (s + 2 * m as u64) % 3 == 0 { ev.push(buy(m, 20 + (k % 13) as u8, v, t, S / 3)); }
                if s % 5 == 0 { ev.push(buy(m, 40 + (k % 7) as u8, v, t, S / 4)); }
                if !ev.is_empty() { txs.push((s, m as u32 * 10, ev, m >= 4)); }
            }
        }
        // one tx in BOTH runs (it touches tokens of both)
        let both = (1_200u64, 999u32, vec![sell(2, 9, v, t, 2 * S), buy(5, 31, v, t, S)]);
        let bt = |s: u64| bt0 + (s as i64 - 1_000) / 5;
        let mut chunks_a: Vec<String> = vec![String::new(); 4];
        let mut chunks_b: Vec<String> = vec![String::new(); 4];
        for (s, i, ev, in_b) in &txs {
            let c = ((*s - 1_000) / 100) as usize;
            let refs: Vec<&TradeEvent> = ev.iter().collect();
            let l = line(*s, *i, bt(*s), true, &refs);
            if *in_b { chunks_b[c].push_str(&l); } else { chunks_a[c].push_str(&l); }
            if *s == both.0 && *i == 60 {
                let r: Vec<&TradeEvent> = both.2.iter().collect();
                let lb = line(both.0, both.1, bt(both.0), true, &r);
                chunks_a[c].push_str(&lb); chunks_b[c].push_str(&lb);
            }
            // noise: a failed tx, an empty ev, a non-pump event
            if *i == 10 { chunks_a[c].push_str(&line(*s, 5, bt(*s), false, &refs)); chunks_a[c].push_str(&format!("{{\"s\":{s},\"i\":6,\"bt\":1,\"err\":null,\"ev\":[]}}\n")); }
        }
        chunks_a[1].push_str("{\"s\":1150,\"i\":1,\"err\":null,\"ev\":[\"AAAA\" BROKEN\n");
        for c in 0..4 {
            let ts = bt0 as u64 + 300 * c as u64;
            gz(&ra.join(format!("txs/txs_{ts}.jsonl.gz")), &chunks_a[c]);
            if c < 3 { gz(&rb.join(format!("txs/txs_{}.jsonl.gz", ts + 7)), &chunks_b[c]); }
        }
        // run B's newest chunk: truncated mid-stream (the collector is writing it)
        let p = rb.join(format!("txs/txs_{}.jsonl.gz", bt0 as u64 + 907));
        gz(&p, &chunks_b[3]);
        let full = std::fs::read(&p).unwrap();
        std::fs::write(&p, &full[..full.len() * 2 / 3]).unwrap();

        // (1) the reader: chain order, each tx once, the damaged line counted, the truncated chunk read as far as it goes
        assert_eq!(run_dirs(&dir.join("current_run")).unwrap(), vec![ra.clone(), rb.clone()]);
        assert_eq!(run_dirs(&rb).unwrap().len(), 2);
        let mut rec = Recording::open(&run_dirs(&dir).unwrap(), 0, u64::MAX, 0, i64::MAX, false, true);
        let mut got: Vec<RecTx> = Vec::new();
        while let Some(x) = rec.next().unwrap() { got.push(x); }
        assert!(got.windows(2).all(|w| (w[0].s, w[0].i) < (w[1].s, w[1].i)), "chain order, no duplicate");
        assert_eq!(got.iter().filter(|x| (x.s, x.i) == (both.0, both.1)).count(), 1);
        assert_eq!(rec.st.dups, 1);
        assert_eq!(rec.st.bad_lines, 1);
        assert_eq!(rec.st.truncated.len(), 1);
        let last_b = got.iter().filter(|x| x.trades.iter().any(|e| e.mint[0] >= 4)).map(|x| x.s).max().unwrap();
        assert!(last_b < 1_399 && last_b >= 1_300, "the truncated chunk read in part: {last_b}");
        let want: usize = txs.iter().filter(|x| !x.3 || x.0 <= last_b).count() + 1;
        assert!(got.len() <= want && got.len() + 3 >= want, "{} vs {want}", got.len());

        // (2) PRELOAD == the live path on the same txs (the cut set as the live side would: its first slot + 1)
        let h = 24 * 3600 * S;
        let cut = AtomicU64::new(1_251);
        let cfg = PreloadCfg { path: dir.join("current_run"), hist_ns: h, start_unix_ns: (bt0 as u64 + 400) * S, timeout: Duration::from_secs(20) };
        let pre = preload(&cfg, &cut).unwrap();
        assert_eq!(pre.cut, 1_251);
        let mut live_path = DumpBook::new(h);
        live_path.cut = 1_251;
        for x in got.iter().take_while(|x| x.s < 1_251 + FOL_SLOTS) { for (j, e) in x.trades.iter().enumerate() { live_path.ingest(e, x.s, x.i, j as i32, x.bt as u64 * S); } }
        live_path.close_all();
        assert_eq!(pre.book.snapshot(), live_path.snapshot(), "the preload's book = the live path's on the same hours");
        assert!(pre.book.dumps() > 50 && pre.st.chunks == 6, "{} dumps, {} chunks (runs A and B up to the chunk of the cut)", pre.book.dumps(), pre.st.chunks);
        assert_eq!(pre.covered_ns, ((bt(1_250) - bt(1_000)) as u64) * S);

        // (3) THE MERGE: one live book over everything = the preload below the cut + a live book that started at slot 1_250 (its first
        // slot partly seen: the cut is 1_251), nothing counted twice
        let mut whole = DumpBook::new(h);
        for x in &got { for (j, e) in x.trades.iter().enumerate() { whole.ingest(e, x.s, x.i, j as i32, x.bt as u64 * S); } }
        let mut live = DumpBook::new(h);
        let mut first = true;
        for x in got.iter().filter(|x| x.s >= 1_250) {
            for (j, e) in x.trades.iter().enumerate() {
                // the live feed joined in the middle of slot 1_250: its first txs there were missed
                if first && x.s == 1_250 && x.i < 30 { continue; }
                first = false;
                live.ingest(e, x.s, x.i, j as i32, x.bt as u64 * S);
            }
        }
        let merged = merge_preload(pre.book, live);
        let (a, b) = (merged.snapshot(), whole.snapshot());
        assert_eq!(a.0, b.0, "every seller's dumps and followers: the merged book = one book over everything");
        assert_eq!(a.1, b.1, "the open windows too");
        assert!(merged.st.dropped_at_cut > 0, "the live book's dumps below the cut were dropped");
        // the merged book keeps working as the live one: the next dumps / followers land
        let mut m2 = merged;
        let mut w2 = whole;
        for book in [&mut m2, &mut w2] {
            book.ingest(&sell(1, 9, v, t, 3 * S), 1_400, 1, 0, bt(1_400) as u64 * S);
            book.ingest(&buy(1, 77, v, t, S), 1_401, 1, 0, bt(1_401) as u64 * S);
        }
        assert_eq!(m2.snapshot(), w2.snapshot());

        // (4) failures: no recording; nothing in the window
        assert!(preload(&PreloadCfg { path: dir.join("nope"), ..cfg.clone() }, &cut).is_err());
        assert!(preload(&PreloadCfg { start_unix_ns: (bt0 as u64 + 400 + 30 * 86400) * S, ..cfg.clone() }, &cut).unwrap_err().contains("no recording chunk"));
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// RECORDED-WINDOW PARITY (run by hand, real data): QUIET_PRELOAD_DIR=<collector run dir or base> QUIET_PRELOAD_H=<hours>
    /// [QUIET_PRELOAD_END=<unix s>] cargo test --release --lib presend_quiet::tests::preload_recorded -- --ignored --nocapture
    /// The preload over the window = the live path's book over the same txs; time, RSS, book size
    #[test]
    #[ignore]
    fn preload_recorded() {
        let dir = PathBuf::from(std::env::var("QUIET_PRELOAD_DIR").expect("QUIET_PRELOAD_DIR"));
        let hours: f64 = std::env::var("QUIET_PRELOAD_H").ok().and_then(|x| x.parse().ok()).unwrap_or(24.0);
        let runs = run_dirs(&dir).unwrap();
        let newest = runs.iter().filter_map(|r| chunks(r, 0, u64::MAX).pop()).map(|x| x.0).max().unwrap();
        let end: u64 = std::env::var("QUIET_PRELOAD_END").ok().and_then(|x| x.parse().ok()).unwrap_or(newest);
        let rss = || std::fs::read_to_string("/proc/self/status").ok().and_then(|s| s.lines().find(|l| l.starts_with("VmRSS:")).and_then(|l| l.split_whitespace().nth(1)?.parse::<u64>().ok())).unwrap_or(0);
        let hwm = || std::fs::read_to_string("/proc/self/status").ok().and_then(|s| s.lines().find(|l| l.starts_with("VmHWM:")).and_then(|l| l.split_whitespace().nth(1)?.parse::<u64>().ok())).unwrap_or(0);
        let h = (hours * 3600.0) as u64 * S;
        // the cut: the slot of the window's end (as if the engine started then); found by a quick read of the last chunk
        let rss0 = rss();
        let cut = AtomicU64::new(0);
        let cfg = PreloadCfg { path: dir.clone(), hist_ns: h, start_unix_ns: end * S, timeout: Duration::from_secs(3600) };
        let mut rec = Recording::open(&runs, end.saturating_sub(600), end, 0, i64::MAX, false, true);
        let mut cut_s = 0;
        while let Some(x) = rec.next().unwrap() { if x.bt as u64 <= end { cut_s = x.s; } }
        cut.store(cut_s.saturating_sub(10), Ordering::SeqCst);
        let t = Instant::now();
        let pre = preload(&cfg, &cut).unwrap_or_else(|e| panic!("preload: {e}"));
        let secs = t.elapsed().as_secs_f64();
        let (rss1, hwm1) = (rss(), hwm());
        eprintln!("PRELOAD {hours} h: {:.1} s | {} chunks ({:.2} GB gz), {} lines, {} txs, {} trades | {} dumps, {} sellers, ~{:.1} MB (estimate) | RSS {} -> {} MB (peak {} MB) | \
                   bad {} partial {} truncated {} | covered {:.2} h | cut {}", secs, pre.st.chunks, pre.st.bytes_gz as f64 / 1e9, pre.st.lines, pre.st.txs, pre.st.trades,
                  pre.book.dumps(), pre.book.sellers(), pre.book.mem_bytes() as f64 / 1e6, rss0 / 1024, rss1 / 1024, hwm1 / 1024, pre.st.bad_lines, pre.st.partial_tails,
                  pre.st.truncated.len(), pre.covered_ns as f64 / 3.6e12, pre.cut);
        // the live path over the same txs (offline reader, the same window and cut)
        let ts_lo = (end).saturating_sub(h / S + 900);
        let bt_lo = end as i64 - (h / S) as i64 - 60;
        let mut rec = Recording::open(&runs, ts_lo, u64::MAX, bt_lo, i64::MAX, false, true);
        let mut live = DumpBook::new(h);
        live.cut = pre.cut;
        let t2 = Instant::now();
        while let Some(x) = rec.next().unwrap() {
            if x.s >= pre.cut + FOL_SLOTS { break; }
            for (j, e) in x.trades.iter().enumerate() { live.ingest(e, x.s, x.i, j as i32, x.bt.max(0) as u64 * S); }
        }
        live.close_all();
        eprintln!("live path over the same txs: {:.1} s; books equal: {}", t2.elapsed().as_secs_f64(), pre.book.snapshot() == live.snapshot());
        assert_eq!(pre.book.snapshot(), live.snapshot());
        // THE MERGE on real data: a live feed that joined in slot cut - 1 (its first txs there missed) and ran ~5 min past the cut,
        // merged into the 24 h preload = one book over everything (no dump or follower twice, none lost); its time
        let (mut whole, mut live2, mut n_live) = (DumpBook::new(h), DumpBook::new(h), 0u64);
        let mut rec = Recording::open(&runs, ts_lo, u64::MAX, bt_lo, i64::MAX, false, true);
        while let Some(x) = rec.next().unwrap() {
            if x.s > pre.cut + 1_500 { break; }
            for (j, e) in x.trades.iter().enumerate() {
                let t = x.bt.max(0) as u64 * S;
                whole.ingest(e, x.s, x.i, j as i32, t);
                if x.s >= pre.cut - 1 && !(x.s == pre.cut - 1 && x.i < 100) { live2.ingest(e, x.s, x.i, j as i32, t); n_live += 1; }
            }
        }
        let n2 = live2.dumps();
        let t3 = Instant::now();
        let merged = merge_preload(pre.book, live2);
        let us = t3.elapsed().as_secs_f64() * 1e6;
        let (a, b) = (merged.snapshot(), whole.snapshot());
        eprintln!("merge into the 24 h preload: {us:.0} us (live part: {n_live} trades, {n2} dumps, {} dropped below the cut); merged = one book over everything: {}",
                  merged.st.dropped_at_cut, a == b);
        assert_eq!(a.0, b.0);
        assert_eq!(a.1, b.1);
    }
}

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
//!   * dip21, the STATE JOURNAL (owner 10-27 PM: a restart without the recorder must not cost a 60-min warm-up): every FINALIZED dump
//!     (its follower window closed) is appended to a JSON-lines file with its identity (slot, tx index, event index), time, seller and
//!     follower count, between session start / heartbeat / stop markers (`JRec`). A start loads the last hist_ns of it (a bad or
//!     truncated line is skipped, never fatal), rewrites it compacted, and the arm rule is on at once when the loaded history is
//!     continuous (gaps <= max-gap tolerated) for the warm-up length and ends within max-gap of the start (`coverage`). With a preload,
//!     the journal and the recording are merged by identity in the preload thread (`merge_base`: the main thread moves only this
//!     session's dumps).
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

/// one dump of a seller: its slot, its time (ns: the feed's arrival live, the block time in a preload), its followers so far; its
/// tx index and event index (dip21: with the slot, its identity across the journal, the recording and the live feed)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Dump { pub s: u64, pub t: u64, pub nf: u32, pub i: u32, pub j: u32 }

/// a seller's dumps in arrival order; d[k] has the absolute index base + k
#[derive(Debug)]
struct Seller { d: VecDeque<Dump>, base: u64 }
impl Seller { fn new() -> Seller { Seller { d: VecDeque::new(), base: BASE0 } } }

/// a dump whose follower window is still open (on its token)
#[derive(Clone, Debug)]
struct Open { seller: Pk, abs: u64, s: u64, pos: (u64, u32, i32), buyers: Vec<Pk> }

#[derive(Clone, Default, PartialEq, Eq)]
pub struct BookStats {
    pub trades: u64, pub dumps: u64, pub followers: u64, pub closed: u64, pub expired: u64,
    /// merge: live dumps below the cut dropped (the preload has them), live windows of those dropped
    pub dropped_at_cut: u64, pub windows_dropped: u64,
    /// dip21: dumps loaded from the journal, finalized for it, dropped at shutdown (their window still open)
    pub loaded: u64, pub journaled: u64, pub shutdown_dropped: u64,
}

/// dip20's text exactly; dip21's counters appended only when used (the run_end record without the journal = dip20's)
impl std::fmt::Debug for BookStats {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "BookStats {{ trades: {}, dumps: {}, followers: {}, closed: {}, expired: {}, dropped_at_cut: {}, windows_dropped: {}", self.trades, self.dumps, self.followers,
               self.closed, self.expired, self.dropped_at_cut, self.windows_dropped)?;
        if self.loaded + self.journaled + self.shutdown_dropped > 0 { write!(f, ", loaded: {}, journaled: {}, shutdown_dropped: {}", self.loaded, self.journaled, self.shutdown_dropped)?; }
        write!(f, " }}")
    }
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
    /// dip21: the finalized dumps for the journal (Some: journaling on; the engine takes them each tick)
    fin: Option<Vec<JDump>>,
    /// dip21: the first n_pre entries of exp_q are loaded history (the journal), not this session's
    n_pre: usize,
}

impl std::fmt::Debug for DumpBook {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "DumpBook {{ dumps {}, sellers {}, open {}, max_slot {}, cut {}, {:?} }}", self.dumps(), self.sellers(), self.open_windows(), self.max_slot, self.cut, self.st)
    }
}

impl DumpBook {
    pub fn new(hist_ns: u64) -> DumpBook {
        DumpBook { sellers: FxHashMap::default(), open: FxHashMap::default(), open_q: VecDeque::new(), exp_q: VecDeque::new(), hist_ns, max_slot: 0, max_t: 0, cut: u64::MAX,
                   st: BookStats::default(), fin: None, n_pre: 0 }
    }
    pub fn max_t(&self) -> u64 { self.max_t }
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
            sl.d.push_back(Dump { s, t, nf: 0, i, j: j.max(0) as u32 });
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
            let (open, sellers, fin, st) = (&mut self.open, &self.sellers, &mut self.fin, &mut self.st);
            if let Some(v) = open.get_mut(&mint) {
                let n0 = v.len();
                // dip21: a closing window's dump is final: the journal gets it
                if let Some(f) = fin.as_mut() {
                    for o in v.iter().filter(|o| o.s + FOL_SLOTS + CLOSE_MARGIN < lim) {
                        if let Some(d) = dump_at(sellers, &o.seller, o.abs) { f.push(JDump { s: d.s, i: d.i, j: d.j, t: d.t, seller: o.seller, nf: d.nf }); st.journaled += 1; }
                    }
                }
                v.retain(|o| o.s + FOL_SLOTS + CLOSE_MARGIN >= lim);
                st.closed += (n0 - v.len()) as u64;
                if v.is_empty() { open.remove(&mint); }
            }
        }
    }

    /// drop the dumps that left the history (each seller's dumps are in the queue's order: its front is the one popped)
    fn expire(&mut self) {
        let lim = self.max_t.saturating_sub(self.hist_ns.saturating_add(EXPIRE_SLACK_NS));
        while let Some(&(t, _, seller)) = self.exp_q.front() {
            if t >= lim { break; }
            self.exp_q.pop_front();
            self.n_pre = self.n_pre.saturating_sub(1);
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

    /// dip21: the journal gets every finalized dump from here on
    pub fn journal_on(&mut self) { if self.fin.is_none() { self.fin = Some(Vec::new()); } }
    pub fn has_finalized(&self) -> bool { self.fin.as_ref().is_some_and(|v| !v.is_empty()) }
    /// dip21: the dumps finalized since the last call (the engine sends them to the writer)
    pub fn take_finalized(&mut self) -> Vec<JDump> { self.fin.as_mut().map(std::mem::take).unwrap_or_default() }

    /// dip21, the run's end: the journal's last dumps. A window past its 2 slots (the feed is beyond its slot + 2) but not yet closed by
    /// the margin: saved with its count; a window still inside its 2 slots: DROPPED (its count would be partial). -> (dumps, dropped)
    pub fn finalize_on_shutdown(&mut self) -> (Vec<JDump>, u64) {
        let mut out = self.take_finalized();
        let (lim, mut dropped) = (self.max_slot, 0u64);
        for o in self.open.values().flatten() {
            if o.s + FOL_SLOTS < lim {
                if let Some(d) = dump_at(&self.sellers, &o.seller, o.abs) { out.push(JDump { s: d.s, i: d.i, j: d.j, t: d.t, seller: o.seller, nf: d.nf }); }
            } else { dropped += 1; }
        }
        self.st.journaled += out.len() as u64;
        self.st.shutdown_dropped += dropped;
        (out, dropped)
    }

    /// dip21: finalized dumps from before this session (the journal; sorted by time) into a book that holds nothing newer: history at
    /// once, this session's dumps after them (`n_pre` marks where)
    pub fn load_finalized(&mut self, dumps: &[JDump]) {
        for d in dumps {
            let sl = self.sellers.entry(d.seller).or_insert_with(Seller::new);
            sl.d.push_back(Dump { s: d.s, t: d.t, nf: d.nf, i: d.i, j: d.j });
            self.exp_q.push_back((d.t, d.s, d.seller));
            self.max_t = self.max_t.max(d.t);
            self.max_slot = self.max_slot.max(d.s);
        }
        self.n_pre = self.exp_q.len();
        self.st.loaded += dumps.len() as u64;
    }

    /// dip21: every dump as a journal entry (the preload's base build)
    pub fn all_dumps(&self) -> Vec<JDump> {
        self.sellers.iter().flat_map(|(w, sl)| sl.d.iter().map(move |d| JDump { s: d.s, i: d.i, j: d.j, t: d.t, seller: *w, nf: d.nf })).collect()
    }
}

/// a seller's dump by its absolute index (None: expired)
fn dump_at(sellers: &FxHashMap<Pk, Seller>, seller: &Pk, abs: u64) -> Option<Dump> {
    let sl = sellers.get(seller)?;
    if abs < sl.base { return None; }
    sl.d.get((abs - sl.base) as usize).copied()
}

/// dip21 THE MERGE WITH A BASE (main thread, once): `base` = the preload's recording dumps and the journal's, each identity once, in
/// time order, every window closed (built in the preload thread, with `ids` = their identities). It takes over THIS SESSION's dumps of
/// the live book (exp_q after its loaded entries: s >= the session's first slot), in order, after its own; a session dump the base has
/// (same identity: the session's first, partly seen slot) is dropped with its window. The live book's loaded part (the journal, also
/// in the base) goes with the old book, returned for the caller to drop off the event loop. Work: O(session dumps), never O(base)
pub fn merge_base(mut base: DumpBook, ids: &FxHashSet<(u64, u32, u32)>, mut live: DumpBook) -> (DumpBook, DumpBook) {
    base.close_all();
    let k = live.n_pre.min(live.exp_q.len());
    // per seller, how many of its trailing dumps are this session's
    let mut per: FxHashMap<Pk, usize> = FxHashMap::default();
    for e in live.exp_q.range(k..) { *per.entry(e.2).or_default() += 1; }
    let mut remap: FxHashMap<(Pk, u64), Option<u64>> = live.open.values().flatten().map(|o| ((o.seller, o.abs), None)).collect();
    let mut cursor: FxHashMap<Pk, usize> = FxHashMap::default();
    let entries: Vec<(u64, u64, Pk)> = live.exp_q.range(k..).copied().collect();
    for (t, s, seller) in entries {
        let Some(sl) = live.sellers.get(&seller) else { continue };
        let m = per.get(&seller).copied().unwrap_or(0);
        let c = cursor.entry(seller).or_insert(sl.d.len().saturating_sub(m));
        let q = *c;
        *c += 1;
        let Some(d) = sl.d.get(q).copied() else { continue };
        if ids.contains(&(d.s, d.i, d.j)) { base.st.dropped_at_cut += 1; continue; }
        let b = base.sellers.entry(seller).or_insert_with(Seller::new);
        let new_abs = b.base + b.d.len() as u64;
        if let Some(x) = remap.get_mut(&(seller, sl.base + q as u64)) { *x = Some(new_abs); }
        b.d.push_back(d);
        base.exp_q.push_back((t, s, seller));
    }
    for (mint, v) in live.open.drain() {
        for mut o in v {
            match remap.get(&(o.seller, o.abs)).copied().flatten() { Some(a) => { o.abs = a; base.open.entry(mint).or_default().push(o); } None => base.st.windows_dropped += 1 }
        }
    }
    base.open_q.extend(live.open_q.drain(..));
    base.max_slot = base.max_slot.max(live.max_slot);
    base.max_t = base.max_t.max(live.max_t);
    let st = &live.st;
    base.st.trades += st.trades; base.st.dumps += st.dumps; base.st.followers += st.followers; base.st.closed += st.closed; base.st.expired += st.expired;
    base.st.journaled += st.journaled;
    base.cut = u64::MAX;
    base.hist_ns = live.hist_ns;
    base.fin = live.fin.take();
    base.expire();
    (base, live)
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

// ---- dip23 QUIET v2 (LOG-ONLY; ops/strategies/presend/filter/QUIET2.md §5.2, quiet2/x3_features.py arm_feats) ------------------
// The QUIET v2 study's one surviving candidate ("trades <= 6 in the last 60 s AND the price at its 120 s high"), post hoc, to be
// settled on >= 2 days of fresh arm / skip records. NEVER acted on: the engine only writes it into the records.
//   * per token, a ring of the last 120 s of (time, post-trade price) and a monotonic deque of its maxima: O(1) amortized per trade
//     (one map lookup; each entry is pushed and popped once), O(trades of the last 60 s) at a trigger (the count), memory bounded by
//     120 s of trades per token; tokens idle for 120 s are dropped by `sweep` (the engine's tick).
//   * the features at a trigger, CAUSAL (the ring holds only trades strictly before the trigger trade: the engine pushes a trade
//     after its trigger decision; an earlier trade of the same tx was pushed before):
//       n_tr_60s     = trades of the token in [t0 - 60 s, t0)        (the study: bt >= bt0 - 60 over the rows before the trigger)
//       maxdd_120s   = (max post price of [t0 - 120 s, t0) - pre_p) / max  (the study: pre_p / max - 1, in %; sign flipped)
//       at_120s_high = maxdd_120s <= 0.001 (within 0.1%)             (the study's cut was -0.2191 %: both can be read back from maxdd)
//       skip         = n_tr_60s <= 6 AND at_120s_high                 (the candidate rule; LOGGED ONLY)
//     pre_p = the trigger trade's PRE-trade price (the study's pre_p = (VS - SOL) / (VT + TOK)); no trade in 120 s: maxdd 0 (the
//     study's 0.0), so a token with no history looks "at its high" (the reader has n_120s and ring_s to tell new from unseen).
//   * the CLOCK: the study used the chain's block time (integer seconds); live, the feed's arrival time (t_rx, unix ns) is the only
//     clock there is, so the windows are 60.0 / 120.0 s of arrival time (the study's integer-second windows are up to 1 s wider).

/// the 60 s count window and the 120 s price window (ns)
pub const V2_CNT_NS: u64 = 60_000_000_000;
pub const V2_WIN_NS: u64 = 120_000_000_000;
/// the candidate rule: <= 6 trades in 60 s, the price within 0.1% of its 120 s high
pub const V2_N_MAX: u32 = 6;
pub const V2_HIGH_TOL: f64 = 0.001;

/// the v2 features at a trigger (the record's "v2")
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct V2Feat {
    pub n_tr_60s: u32, pub at_120s_high: bool, pub maxdd_120s: f64, pub skip: bool,
    /// context for the reader: trades in the 120 s window, the ring's coverage at the trigger (s since the first trade it saw)
    pub n_120s: u32, pub ring_s: f64,
}

impl V2Feat {
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"n_tr_60s": self.n_tr_60s, "at_120s_high": self.at_120s_high, "maxdd_120s": self.maxdd_120s, "skip": self.skip,
            "n_120s": self.n_120s, "ring_s": (self.ring_s * 10.0).round() / 10.0})
    }
}

/// one token's ring: (t, post price) of the last 120 s oldest first; the maxima deque (a subsequence of `q`, prices decreasing)
#[derive(Debug, Default)]
struct V2Tok { q: VecDeque<(u64, f64)>, mx: VecDeque<(u64, f64)>, last_t: u64 }

impl V2Tok {
    /// drop what is older than the 120 s window ending at `t0` (exclusive of t0 itself: see `feats`)
    fn expire(&mut self, t0: u64) {
        let lo = t0.saturating_sub(V2_WIN_NS);
        while self.q.front().is_some_and(|x| x.0 < lo) { self.q.pop_front(); }
        while self.mx.front().is_some_and(|x| x.0 < lo) { self.mx.pop_front(); }
    }
    fn push(&mut self, t: u64, p: f64) {
        self.expire(t);
        while self.mx.back().is_some_and(|x| x.1 <= p) { self.mx.pop_back(); }
        self.mx.push_back((t, p));
        self.q.push_back((t, p));
        self.last_t = self.last_t.max(t);
    }
}

/// every token's ring
#[derive(Debug, Default)]
pub struct V2Ring { toks: FxHashMap<Pk, V2Tok>, first_t: u64, max_t: u64, swept_t: u64 }

impl V2Ring {
    pub fn new() -> V2Ring { V2Ring::default() }
    pub fn tokens(&self) -> usize { self.toks.len() }
    pub fn entries(&self) -> usize { self.toks.values().map(|t| t.q.len()).sum() }
    /// a trade of `mint` at `t` (feed arrival, ns) with post-trade price `p`: AFTER the trigger decision on that trade
    pub fn push(&mut self, mint: &Pk, t: u64, p: f64) {
        if self.first_t == 0 { self.first_t = t; }
        self.max_t = self.max_t.max(t);
        self.toks.entry(*mint).or_default().push(t, p);
    }
    /// the features of a trigger at `t0` on `mint` whose pre-trade price is `pre_p`; the ring holds the trades before it
    pub fn feats(&mut self, mint: &Pk, t0: u64, pre_p: f64) -> V2Feat {
        let ring_s = if self.first_t == 0 { 0.0 } else { t0.saturating_sub(self.first_t) as f64 / 1e9 };
        let Some(tk) = self.toks.get_mut(mint) else {
            return V2Feat { n_tr_60s: 0, at_120s_high: true, maxdd_120s: 0.0, skip: true, n_120s: 0, ring_s };
        };
        tk.expire(t0);
        let lo60 = t0.saturating_sub(V2_CNT_NS);
        let n_tr_60s = tk.q.iter().rev().take_while(|x| x.0 >= lo60).count() as u32;
        let maxdd_120s = match tk.mx.front() { Some(&(_, m)) if m > 0.0 => (m - pre_p) / m, _ => 0.0 };
        let at_120s_high = maxdd_120s <= V2_HIGH_TOL;
        V2Feat { n_tr_60s, at_120s_high, maxdd_120s, skip: n_tr_60s <= V2_N_MAX && at_120s_high, n_120s: tk.q.len() as u32, ring_s }
    }
    /// drop the tokens with no trade in the last 120 s of the ring's own clock (its latest trade); at most once per 10 s of it.
    /// -> whether a sweep ran
    pub fn sweep(&mut self) -> bool {
        if self.max_t < self.swept_t.saturating_add(10_000_000_000) { return false; }
        self.swept_t = self.max_t;
        let lo = self.max_t.saturating_sub(V2_WIN_NS);
        self.toks.retain(|_, t| t.last_t >= lo);
        true
    }
}

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
pub struct Recording { rs: Vec<RunReader>, heads: Vec<Option<RecTx>>, done: Vec<bool>, last: Option<(u64, u32)>, pub st: ReadStats, offline: bool, bt_lo: i64, bt_hi: i64,
    /// dip21: per run, the slot and block time of its last tx taken from it (0: none yet): how far each run's copy goes (the book)
    pub run_last: Vec<(u64, i64)> }

impl Recording {
    /// `ts_lo..=ts_hi`: the chunk files (by their name's start time); `bt_lo..=bt_hi`: the txs (block time; the study's span filter);
    /// `offline`: every chunk is final (a test / replay: never wait for more)
    pub fn open(runs: &[PathBuf], ts_lo: u64, ts_hi: u64, bt_lo: i64, bt_hi: i64, creates: bool, offline: bool) -> Recording {
        let rs: Vec<RunReader> = runs.iter().map(|r| RunReader::new(r.clone(), ts_lo, ts_hi, creates)).collect();
        let n = rs.len();
        Recording { rs, heads: vec![None; n], done: vec![false; n], last: None, st: ReadStats::default(), offline, bt_lo, bt_hi, run_last: vec![(0, 0); n] }
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
            self.run_last[k] = (tx.s, tx.bt);
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

// ---- dip21: the state journal ----------------------------------------------------------------------------------------------

/// one finalized dump as the journal keeps it: identity (slot, tx index, event index), time (ns), seller, followers
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct JDump { pub s: u64, pub i: u32, pub j: u32, pub t: u64, pub seller: Pk, pub nf: u32 }

/// a journal line: a session's start (its first trade), heartbeat (every FLUSH_S of data time) and stop (the run's end), or a dump.
/// The sessions are the history's coverage: a crash leaves the last heartbeat as its end
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum JRec { Start { t: u64, s: u64 }, Beat { t: u64, s: u64 }, Stop { t: u64, s: u64 }, Dump(JDump) }

/// one JSON line (no newline); the dump's seller in base58
pub fn encode(r: &JRec) -> String {
    match r {
        JRec::Start { t, s } => format!("{{\"k\":\"start\",\"v\":1,\"t\":{t},\"s\":{s}}}"),
        JRec::Beat { t, s } => format!("{{\"k\":\"beat\",\"t\":{t},\"s\":{s}}}"),
        JRec::Stop { t, s } => format!("{{\"k\":\"stop\",\"t\":{t},\"s\":{s}}}"),
        JRec::Dump(d) => format!("{{\"k\":\"d\",\"s\":{},\"i\":{},\"j\":{},\"t\":{},\"w\":\"{}\",\"n\":{}}}", d.s, d.i, d.j, d.t, bs58::encode(d.seller).into_string(), d.nf),
    }
}

/// one line back (None: not a journal line: damaged, cut, foreign)
pub fn decode(line: &[u8]) -> Option<JRec> {
    let v: serde_json::Value = serde_json::from_slice(line).ok()?;
    let u = |k: &str| v.get(k).and_then(|x| x.as_u64());
    match v.get("k")?.as_str()? {
        "start" => Some(JRec::Start { t: u("t")?, s: u("s")? }),
        "beat" => Some(JRec::Beat { t: u("t")?, s: u("s")? }),
        "stop" => Some(JRec::Stop { t: u("t")?, s: u("s")? }),
        "d" => {
            let w: Pk = bs58::decode(v.get("w")?.as_str()?).into_vec().ok()?.try_into().ok()?;
            Some(JRec::Dump(JDump { s: u("s")?, i: u32::try_from(u("i")?).ok()?, j: u32::try_from(u("j")?).ok()?, t: u("t")?, seller: w, nf: u32::try_from(u("n")?).ok()? }))
        }
        _ => None,
    }
}

/// a session of the journal: from its start marker to its last record (time ns, slot)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Sess { pub t0: u64, pub t1: u64, pub s0: u64, pub s1: u64 }

/// what a start loaded
#[derive(Clone, Debug, Default)]
pub struct Loaded {
    /// the dumps inside the history window, each identity once, by time; with the session each was written in (None: none)
    pub dumps: Vec<(JDump, Option<usize>)>,
    /// the sessions overlapping the window (clipped to it), in file order
    pub sessions: Vec<Sess>,
    pub lines: u64, pub bad: u64, pub truncated_tail: bool, pub old: u64, pub future: u64, pub dups: u64, pub bytes: u64, pub skipped_bytes: u64,
    /// no file yet (a first start: not an error) / the file could not be read
    pub missing: bool, pub err: Option<String>,
}

/// a journal bigger than this is read from its last STATE_MAX_BYTES only (a wrong path must not stall the start)
pub const STATE_MAX_BYTES: u64 = 256 << 20;

/// LOAD (the engine's start, before any trade): every line of the journal, the bad ones skipped and counted (a damaged line, a cut
/// last line: never fatal), the dumps inside [now - hist, now + 10 min] kept once per identity, the sessions' spans
pub fn load_state(path: &Path, now_ns: u64, hist_ns: u64) -> Loaded {
    use std::io::{Read, Seek, SeekFrom};
    let mut l = Loaded::default();
    let mut f = match std::fs::File::open(path) {
        Ok(f) => f,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => { l.missing = true; return l; }
        Err(e) => { l.err = Some(format!("{}: {e}", path.display())); return l; }
    };
    let len = f.metadata().map(|m| m.len()).unwrap_or(0);
    if f.metadata().is_ok_and(|m| m.is_dir()) { l.err = Some(format!("{} is a directory", path.display())); return l; }
    l.bytes = len;
    let mut skip_first = false;
    if len > STATE_MAX_BYTES {
        if f.seek(SeekFrom::Start(len - STATE_MAX_BYTES)).is_ok() { l.skipped_bytes = len - STATE_MAX_BYTES; skip_first = true; }
    }
    let mut r = std::io::BufReader::with_capacity(1 << 20, f.by_ref());
    let (lo, hi) = (now_ns.saturating_sub(hist_ns), now_ns.saturating_add(600_000_000_000));
    let mut seen: FxHashSet<(u64, u32, u32)> = FxHashSet::default();
    let mut cur: Option<usize> = None;
    let mut sess: Vec<Sess> = Vec::new();
    let mut buf: Vec<u8> = Vec::with_capacity(256);
    loop {
        buf.clear();
        let n = match r.read_until(b'\n', &mut buf) { Ok(n) => n, Err(e) => { l.err = Some(format!("{}: {e}", path.display())); break; } };
        if n == 0 { break; }
        if skip_first { skip_first = false; continue; }
        l.lines += 1;
        let complete = buf.last() == Some(&b'\n');
        let body = if complete { &buf[..buf.len() - 1] } else { &buf[..] };
        let Some(rec) = decode(body) else { if complete { l.bad += 1; } else { l.truncated_tail = true; } continue };
        let ext = |sess: &mut Vec<Sess>, cur: Option<usize>, t: u64, s: u64| { if let Some(c) = cur { let x = &mut sess[c]; x.t1 = x.t1.max(t); x.s1 = x.s1.max(s); } };
        match rec {
            JRec::Start { t, s } => { sess.push(Sess { t0: t, t1: t, s0: s, s1: s }); cur = Some(sess.len() - 1); }
            JRec::Beat { t, s } => ext(&mut sess, cur, t, s),
            JRec::Stop { t, s } => { ext(&mut sess, cur, t, s); cur = None; }
            JRec::Dump(d) => {
                ext(&mut sess, cur, d.t, d.s);
                if d.t < lo { l.old += 1; continue; }
                if d.t > hi { l.future += 1; continue; }
                if !seen.insert((d.s, d.i, d.j)) { l.dups += 1; continue; }
                l.dumps.push((d, cur));
            }
        }
    }
    // the sessions still inside the window (clipped to it), the dumps' session indices renumbered
    let mut map: Vec<Option<usize>> = Vec::with_capacity(sess.len());
    for x in &sess {
        if x.t1 < lo || x.t0 > hi { map.push(None); continue; }
        map.push(Some(l.sessions.len()));
        l.sessions.push(Sess { t0: x.t0.max(lo), t1: x.t1.min(hi), ..*x });
    }
    for d in l.dumps.iter_mut() { d.1 = d.1.and_then(|k| map[k]); }
    l.dumps.sort_by_key(|(d, _)| (d.t, d.s, d.i, d.j));
    l
}

/// the history's continuity at `at_ns` (an engine's start)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Cov { pub covered_ns: u64, pub from: u64, pub to: u64, pub gap_ns: u64, pub stretches: usize }

/// THE CONTINUITY RULE: the spans the history covers (sessions, a preload's recording) joined when the gap between them is at most
/// `max_gap_ns` (a restart's gap is tolerated); the stretch that ends latest counts when it ends within `max_gap_ns` of `at_ns`: its
/// length is the history the arm rule may count (`arm_on`: on at once when >= the warm-up). Otherwise 0 (too old: the warm-up)
pub fn coverage(spans: &[(u64, u64)], at_ns: u64, max_gap_ns: u64) -> Cov {
    let mut v: Vec<(u64, u64)> = spans.iter().map(|&(a, b)| (a.min(at_ns), b.min(at_ns))).filter(|(a, b)| b >= a).collect();
    v.sort();
    let mut st: Vec<(u64, u64)> = Vec::new();
    for (a, b) in v {
        match st.last_mut() { Some(x) if a <= x.1.saturating_add(max_gap_ns) => x.1 = x.1.max(b), _ => st.push((a, b)) }
    }
    let Some(&(from, to)) = st.last() else { return Cov { gap_ns: u64::MAX, ..Default::default() } };
    let gap = at_ns.saturating_sub(to);
    Cov { covered_ns: if gap <= max_gap_ns { to - from } else { 0 }, from, to, gap_ns: gap, stretches: st.len() }
}

/// THE COMPACTED JOURNAL: what was loaded, rewritten (the dumps of no session first, then each session: start, its dumps, stop); old
/// sessions and dumps, duplicates and bad lines are gone
pub fn compact(l: &Loaded) -> Vec<JRec> {
    let mut by: Vec<Vec<JDump>> = vec![Vec::new(); l.sessions.len()];
    let mut out = Vec::with_capacity(l.dumps.len() + 2 * l.sessions.len());
    for (d, k) in &l.dumps { match k { Some(k) => by[*k].push(*d), None => out.push(JRec::Dump(*d)) } }
    for (x, ds) in l.sessions.iter().zip(by) {
        out.push(JRec::Start { t: x.t0, s: x.s0 });
        out.extend(ds.into_iter().map(JRec::Dump));
        out.push(JRec::Stop { t: x.t1, s: x.s1 });
    }
    out
}

/// what the engine sends the journal writer
#[derive(Debug)]
pub enum JMsg { Dumps(Vec<JDump>), Start { t: u64, s: u64 }, Beat { t: u64, s: u64 }, Stop { t: u64, s: u64 } }

/// the writer's counters (shared with the engine's status line and run_end)
#[derive(Clone, Debug, Default)]
pub struct JStats {
    pub compact_lines: u64, pub compact_bytes_before: u64, pub compact_bytes_after: u64, pub compact_ms: f64, pub compacted: bool,
    pub lines: u64, pub dumps: u64, pub bytes: u64, pub flushes: u64, pub syncs: u64, pub errors: u64, pub first_err: Option<String>, pub done: bool,
}

/// the writer flushes at least this often (s), and syncs at every heartbeat / stop
pub const FLUSH_S: u64 = 10;

/// THE JOURNAL WRITER (its own low-priority thread; the engine never waits for it): first the compaction (`compact`: the loaded history
/// rewritten whole: a temp file, synced, renamed over the journal), then every record appended as it comes; flushed at least every
/// FLUSH_S s, flushed and synced at every heartbeat / stop and at the end (the engine dropped its sender). An error is counted and
/// reported, never fatal: the records are then lost, the engine runs on
pub fn journal_writer(path: PathBuf, compact: Option<Vec<JRec>>, rx: crossbeam_channel::Receiver<JMsg>, st: std::sync::Arc<std::sync::Mutex<JStats>>) {
    use std::io::Write;
    let err = |st: &std::sync::Mutex<JStats>, e: String| { let mut g = st.lock().unwrap_or_else(|x| x.into_inner()); g.errors += 1; if g.first_err.is_none() { g.first_err = Some(e); } };
    if let Some(c) = compact {
        let t0 = Instant::now();
        let before = std::fs::metadata(&path).map(|m| m.len()).unwrap_or(0);
        let tmp = PathBuf::from(format!("{}.tmp", path.display()));
        let res = (|| -> std::io::Result<u64> {
            let mut w = std::io::BufWriter::with_capacity(1 << 20, std::fs::File::create(&tmp)?);
            let mut n = 0u64;
            for r in &c { let l = encode(r); w.write_all(l.as_bytes())?; w.write_all(b"\n")?; n += l.len() as u64 + 1; }
            let f = w.into_inner().map_err(|e| e.into_error())?;
            f.sync_all()?;
            std::fs::rename(&tmp, &path)?;
            Ok(n)
        })();
        let mut g = st.lock().unwrap_or_else(|x| x.into_inner());
        match res {
            Ok(n) => { g.compacted = true; g.compact_lines = c.len() as u64; g.compact_bytes_before = before; g.compact_bytes_after = n; g.compact_ms = t0.elapsed().as_secs_f64() * 1e3; }
            Err(e) => { drop(g); err(&st, format!("compaction of {}: {e}", path.display())); let _ = std::fs::remove_file(&tmp); }
        }
    }
    let mut w = match std::fs::OpenOptions::new().create(true).append(true).open(&path) {
        Ok(f) => Some(std::io::BufWriter::with_capacity(1 << 16, f)),
        Err(e) => { err(&st, format!("open {}: {e}", path.display())); None }
    };
    let (mut last_flush, mut dirty) = (Instant::now(), false);
    loop {
        let m = rx.recv_timeout(Duration::from_secs(1));
        let end = matches!(m, Err(crossbeam_channel::RecvTimeoutError::Disconnected));
        let (recs, sync): (Vec<JRec>, bool) = match m {
            Ok(JMsg::Dumps(v)) => (v.into_iter().map(JRec::Dump).collect(), false),
            Ok(JMsg::Start { t, s }) => (vec![JRec::Start { t, s }], true),
            Ok(JMsg::Beat { t, s }) => (vec![JRec::Beat { t, s }], true),
            Ok(JMsg::Stop { t, s }) => (vec![JRec::Stop { t, s }], true),
            Err(_) => (Vec::new(), end),
        };
        if let Some(f) = w.as_mut() {
            let mut n = (0u64, 0u64, 0u64);
            for r in &recs {
                let l = encode(r);
                match f.write_all(l.as_bytes()).and_then(|_| f.write_all(b"\n")) {
                    Ok(()) => { n.0 += 1; n.2 += l.len() as u64 + 1; if matches!(r, JRec::Dump(_)) { n.1 += 1; } dirty = true; }
                    Err(e) => err(&st, format!("write {}: {e}", path.display())),
                }
            }
            let mut flushed = (false, false);
            if dirty && (sync || last_flush.elapsed() >= Duration::from_secs(FLUSH_S)) {
                match f.flush() { Ok(()) => flushed.0 = true, Err(e) => err(&st, format!("flush {}: {e}", path.display())) }
                if sync && f.get_ref().sync_data().is_ok() { flushed.1 = true; }
                last_flush = Instant::now();
                dirty = false;
            }
            let mut g = st.lock().unwrap_or_else(|x| x.into_inner());
            g.lines += n.0; g.dumps += n.1; g.bytes += n.2; g.flushes += flushed.0 as u64; g.syncs += flushed.1 as u64;
        }
        if end { break; }
    }
    st.lock().unwrap_or_else(|x| x.into_inner()).done = true;
}

/// keep the history inside [lo_ns, ..): older dumps dropped, sessions ending before lo_ns dropped, the others clipped to it (their
/// start time; the start slot stays the session's first: informational, the coverage is by time), the dumps' session indices renumbered
pub fn trim_loaded(l: &mut Loaded, lo_ns: u64) {
    let mut map: Vec<Option<usize>> = Vec::with_capacity(l.sessions.len());
    let mut keep: Vec<Sess> = Vec::with_capacity(l.sessions.len());
    for x in &l.sessions {
        if x.t1 < lo_ns { map.push(None); continue; }
        map.push(Some(keep.len()));
        keep.push(Sess { t0: x.t0.max(lo_ns), ..*x });
    }
    l.sessions = keep;
    l.dumps.retain(|(d, _)| d.t >= lo_ns);
    for d in l.dumps.iter_mut() { d.1 = d.1.and_then(|k| map.get(k).copied().flatten()); }
}

/// dip21: two loaded histories as one (the host's book and the engine's own journal): `a`'s dumps first (its version of an identity
/// both have is kept), then `b`'s others; both's sessions (the coverage), `b`'s renumbered after `a`'s; by time
pub fn merge_loaded(a: Option<&Loaded>, b: Option<&Loaded>) -> Loaded {
    let mut out = Loaded::default();
    let mut seen: FxHashSet<(u64, u32, u32)> = FxHashSet::default();
    for l in [a, b].into_iter().flatten() {
        let off = out.sessions.len();
        out.sessions.extend(l.sessions.iter().copied());
        for (d, k) in &l.dumps {
            if seen.insert((d.s, d.i, d.j)) { out.dumps.push((*d, k.map(|k| k + off))); } else { out.dups += 1; }
        }
        out.lines += l.lines; out.bad += l.bad; out.old += l.old; out.future += l.future; out.bytes += l.bytes;
    }
    out.dumps.sort_by_key(|(d, _)| (d.t, d.s, d.i, d.j));
    out
}

// ---- dip21: the host's QUIET BOOK (the 24 h whale dump history from the recording, pushed to every node) --------------------------

/// the recording has no tx for this long: a break in the book's coverage (a collector / keeper outage)
pub const BOOK_GAP_S: i64 = 180;
/// a run whose last tx read is more than this behind the newest tx of any run has stopped (its tail ended, it crashed); a run within
/// it is still being copied, and the book is complete only up to the slowest of those (its copy may be a few minutes behind)
pub const BOOK_ACTIVE_S: i64 = 900;

/// one book pass
#[derive(Debug)]
pub struct BookPass {
    /// the book: its sessions (the recording's continuous spans) and final dumps, ready for `compact`
    pub book: Loaded,
    /// extended a previous book (else built from scratch); the slot it resumed at; dumps added; dumps held back (their window not
    /// complete in what was read: the next pass re-reads them); the last slot read; the coverage's end (the last complete slot of
    /// the slowest run still being written; 0: nothing new); runs still being written
    pub resumed: bool, pub resume_slot: u64, pub added: usize, pub held_back: u64, pub last_slot: u64, pub end_slot: u64, pub active_runs: usize,
    pub st: ReadStats, pub secs: f64,
}

/// BUILD OR EXTEND THE BOOK from the recording, with the live path's own rules (`DumpBook::ingest`: parity by construction).
/// `prev` = the last book (None: a full build of the last `hist_ns`). A pass reads only from the previous book's end (its last
/// session's last slot + 1: every dump below it is final), counts followers as the live path does, and keeps a dump only once its
/// 2-slot window is complete in what was read: the coverage ends at the last complete slot of the slowest run still being written
/// (its last slot - 3; a run's copy may end mid-chunk, and at the daily rotation two runs are written at once); dumps after it are
/// held back and re-read by the next pass. Coverage: one session per continuous stretch of the recording (no tx for > BOOK_GAP_S: a
/// break); the first new stretch continues the previous book's last session. Dumps older than `hist_ns` before `now_ns` dropped.
/// `until_s`: only the recording up to this block time (a book "as of" then: tests, replays)
pub fn build_book(runs: &[PathBuf], prev: Option<Loaded>, now_ns: u64, until_s: Option<i64>, hist_ns: u64) -> Result<BookPass, String> {
    let t0 = Instant::now();
    let lo_t = now_ns.saturating_sub(hist_ns);
    let last_prev = prev.as_ref().and_then(|l| l.sessions.iter().copied().max_by_key(|x| x.s1));
    let resumed = last_prev.is_some();
    let (resume_slot, resume_t) = last_prev.map(|x| (x.s1 + 1, x.t1)).unwrap_or((0, lo_t));
    // the chunks from the previous book's end (never more than the history window: a book left days behind is rebuilt, not replayed)
    let ts_lo = (resume_t.max(lo_t) / 1_000_000_000).saturating_sub(900);
    // a chunk is named by its first tx's receive time: none named after until + 10 min has a tx up to until
    let ts_hi = until_s.map(|u| u.max(0) as u64 + 600).unwrap_or(u64::MAX);
    let bt_lo = (lo_t / 1_000_000_000) as i64;
    let mut rec = Recording::open(runs, ts_lo, ts_hi, bt_lo, until_s.unwrap_or(i64::MAX), false, true);
    let mut tail = DumpBook::new(hist_ns);
    tail.journal_on();
    let mut fin: Vec<JDump> = Vec::new();
    let mut sess: Vec<Sess> = Vec::new();
    // every slot read and its time (the coverage's end is set back to a complete slot)
    let mut slots: Vec<(u64, u64)> = Vec::new();
    let mut last_bt = last_prev.map(|x| (x.t1 / 1_000_000_000) as i64).unwrap_or(0);
    let mut first = true;
    while let Some(tx) = rec.next()? {
        if tx.s < resume_slot { continue; }
        let t = tx.bt.max(0) as u64 * 1_000_000_000;
        let gap = last_bt == 0 || tx.bt - last_bt > BOOK_GAP_S;
        if first || gap {
            // the first new stretch continues the previous book's last session (no gap); otherwise a new session
            if !(first && !gap && resumed) { sess.push(Sess { t0: t, t1: t, s0: tx.s, s1: tx.s }); }
            else { sess.push(Sess { t0: u64::MAX, t1: t, s0: tx.s, s1: tx.s }); }
        }
        first = false;
        last_bt = tx.bt;
        for (j, e) in tx.trades.iter().enumerate() { tail.ingest(e, tx.s, tx.i, j as i32, t); }
        if tail.has_finalized() { fin.extend(tail.take_finalized()); }
        let x = sess.last_mut().unwrap();
        x.t1 = x.t1.max(t); x.s1 = x.s1.max(tx.s);
        if slots.last().map(|r| r.0) != Some(tx.s) { slots.push((tx.s, t)); }
    }
    let r = tail.max_slot();
    let (last, mut held_back) = tail.finalize_on_shutdown();
    fin.extend(last);
    // the runs still being written (their last tx within BOOK_ACTIVE_S of the newest): the book is complete up to the slowest
    let newest = rec.run_last.iter().map(|x| x.1).max().unwrap_or(0);
    let active: Vec<u64> = rec.run_last.iter().filter(|x| x.0 > 0 && x.1 >= newest - BOOK_ACTIVE_S).map(|x| x.0).collect();
    let r_end = active.iter().copied().min().unwrap_or(r).min(r);
    // the coverage ends at the last COMPLETE slot (r_end - 3: a dump there has its window r_end-3..r_end-1, all read in every run)
    let end = slots.partition_point(|x| x.0 + 3 <= r_end).checked_sub(1).map(|k| slots[k]);
    let s1 = end.map(|x| x.0).unwrap_or(0);
    sess.retain(|x| end.is_some() && x.s0 <= s1);
    if let (Some(x), Some((s, t))) = (sess.last_mut(), end) { if x.s1 > s { x.s1 = s; x.t1 = t; } }
    let n0 = fin.len();
    fin.retain(|d| end.is_some() && d.s <= s1);
    held_back += (n0 - fin.len()) as u64;
    let mut book = prev.unwrap_or_default();
    let mut map: Vec<Option<usize>> = Vec::with_capacity(sess.len());
    for x in &sess {
        if x.t0 == u64::MAX {
            // continues the previous book's last session
            match book.sessions.iter().enumerate().max_by_key(|(_, y)| y.s1).map(|(k, _)| k) {
                Some(k) => { let y = &mut book.sessions[k]; y.t1 = y.t1.max(x.t1); y.s1 = y.s1.max(x.s1); map.push(Some(k)); }
                None => { book.sessions.push(Sess { t0: x.t1, ..*x }); map.push(Some(book.sessions.len() - 1)); }
            }
        } else { book.sessions.push(*x); map.push(Some(book.sessions.len() - 1)); }
    }
    let have: FxHashSet<(u64, u32, u32)> = book.dumps.iter().map(|(d, _)| (d.s, d.i, d.j)).collect();
    let mut added = 0usize;
    for d in fin {
        if have.contains(&(d.s, d.i, d.j)) { continue; }
        let k = sess.iter().position(|x| x.s0 <= d.s && d.s <= x.s1).and_then(|k| map[k]);
        book.dumps.push((d, k));
        added += 1;
    }
    book.dumps.sort_by_key(|(d, _)| (d.t, d.s, d.i, d.j));
    trim_loaded(&mut book, lo_t);
    book.missing = false;
    book.err = None;
    Ok(BookPass { book, resumed, resume_slot, added, held_back, last_slot: r, end_slot: if sess.is_empty() { 0 } else { s1 }, active_runs: active.len(), st: rec.st,
        secs: t0.elapsed().as_secs_f64() })
}

/// write a history (compacted) to `path` atomically (a temp file, synced, renamed): a reader sees the old file or the new one ->
/// (lines, bytes)
pub fn write_book(path: &Path, l: &Loaded) -> std::io::Result<(usize, u64)> {
    use std::io::Write;
    let tmp = PathBuf::from(format!("{}.tmp", path.display()));
    let recs = compact(l);
    let mut w = std::io::BufWriter::with_capacity(1 << 20, std::fs::File::create(&tmp)?);
    let mut n = 0u64;
    for r in &recs { let x = encode(r); w.write_all(x.as_bytes())?; w.write_all(b"\n")?; n += x.len() as u64 + 1; }
    let f = w.into_inner().map_err(|e| e.into_error())?;
    f.sync_all()?;
    std::fs::rename(&tmp, path)?;
    Ok((recs.len(), n))
}

// ---- the preload ---------------------------------------------------------------------------------------------------------

/// what the preload thread needs: the recording path, the history length, the engine's start (unix ns), the cut slot set by the
/// live side (0 until the live feed's first trade: the cut is that slot + 1), the time limit
/// dip21: `journal` = the state journal's loaded dumps (empty: none): joined with the recording's by identity (the recording's wins)
#[derive(Clone, Debug)]
pub struct PreloadCfg { pub path: PathBuf, pub hist_ns: u64, pub start_unix_ns: u64, pub timeout: Duration, pub journal: Vec<JDump> }

#[derive(Debug)]
pub struct PreloadOut {
    pub book: DumpBook, pub cut: u64, pub st: ReadStats, pub secs: f64,
    /// block time (s) of the first tx used and of the last one below the cut: the history it brings is the span between them
    pub bt_first: i64, pub bt_cut: i64, pub covered_ns: u64,
    /// the live book's first slot was not known when it was needed (seconds waited)
    pub waited_cut_s: f64, pub waited_tail_s: f64,
    /// dip21 (a journal given): every identity of the base (the recording's dumps and the journal's), journal dumps added / already in
    /// the recording
    pub ids: Option<FxHashSet<(u64, u32, u32)>>, pub journal_added: usize, pub journal_dup: usize,
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
    // dip21: the journal's dumps join the recording's (all below the cut), each identity once (the recording's wins), in time order:
    // the base the live book's session is merged into (merge_base); without a journal: dip20's book
    let (book, ids, journal_added, journal_dup) = if cfg.journal.is_empty() { (book, None, 0, 0) } else {
        let mut all = book.all_dumps();
        let have: FxHashSet<(u64, u32, u32)> = all.iter().map(|d| (d.s, d.i, d.j)).collect();
        let (mut add, mut dup) = (0usize, 0usize);
        for d in &cfg.journal { if have.contains(&(d.s, d.i, d.j)) { dup += 1; } else { all.push(*d); add += 1; } }
        all.sort_by_key(|d| (d.t, d.s, d.i, d.j));
        let mut b = DumpBook::new(cfg.hist_ns);
        b.load_finalized(&all);
        b.cut = cut;
        let ids: FxHashSet<(u64, u32, u32)> = all.iter().map(|d| (d.s, d.i, d.j)).collect();
        (b, Some(ids), add, dup)
    };
    Ok(PreloadOut { book, cut, st: rec.st, secs: t0.elapsed().as_secs_f64(), bt_first, bt_cut, covered_ns, waited_cut_s: waited_cut.as_secs_f64(), waited_tail_s: waited_tail.as_secs_f64(),
        ids, journal_added, journal_dup })
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
        let cfg = PreloadCfg { path: dir.join("current_run"), hist_ns: h, start_unix_ns: (bt0 as u64 + 400) * S, timeout: Duration::from_secs(20), journal: Vec::new() };
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

    // ---- dip21: the state journal ------------------------------------------------------------------------------------------

    fn tmpdir(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("quiet_{tag}_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&d);
        std::fs::create_dir_all(&d).unwrap();
        d
    }
    /// a market for the journal tests: 6 tokens, sellers 9..12 dumping, buyers 20.. following within 0..3 slots
    fn market(slots: std::ops::Range<u64>, t0: u64) -> Vec<(u64, u32, u64, Vec<TradeEvent>)> {
        let (v, t) = (30 * S, 1_000_000_000_000_000u64);
        let mut out = Vec::new();
        for s in slots {
            for m in 1..=6u8 {
                let mut ev = Vec::new();
                if (s + m as u64) % 5 == 0 { ev.push(sell(m, 9 + (m % 4), v, t, 2 * S + (s % 3) * S)); }
                if (s + 2 * m as u64) % 2 == 0 { ev.push(buy(m, 20 + ((s + m as u64) % 17) as u8, v, t, S / 3)); }
                if s % 3 == 0 { ev.push(buy(m, 40 + (m % 5), v, t, S / 4)); }
                if !ev.is_empty() { out.push((s, m as u32 * 10, t0 + s * 212_000_000, ev)); }
            }
        }
        out
    }
    fn feed(b: &mut DumpBook, txs: &[(u64, u32, u64, Vec<TradeEvent>)], fin: &mut Vec<JDump>) {
        for (s, i, t, ev) in txs { for (j, e) in ev.iter().enumerate() { b.ingest(e, *s, *i, j as i32, *t); } fin.extend(b.take_finalized()); }
    }
    fn write_lines(path: &Path, recs: &[JRec]) { std::fs::write(path, recs.iter().map(|r| encode(r) + "\n").collect::<String>()).unwrap(); }
    /// every seller's dumps (s, i, j, t, nf) as a set: the history a book holds
    fn hist_of(b: &DumpBook) -> Vec<(Pk, u64, u32, u32, u64, u32)> {
        let mut v: Vec<_> = b.all_dumps().into_iter().map(|d| (d.seller, d.s, d.i, d.j, d.t, d.nf)).collect();
        v.sort();
        v
    }

    #[test]
    fn journal_line_roundtrip_and_rejects() {
        let d = JDump { s: 461_957_186, i: 1234, j: 2, t: 1_793_080_000_123_456_789, seller: pk(77), nf: 3 };
        for r in [JRec::Start { t: 5, s: 6 }, JRec::Beat { t: 7, s: 8 }, JRec::Stop { t: 9, s: 10 }, JRec::Dump(d)] { assert_eq!(decode(encode(&r).as_bytes()), Some(r)); }
        for bad in ["", "{", "{}", "{\"k\":\"d\"}", "{\"k\":\"d\",\"s\":1,\"i\":1,\"j\":1,\"t\":1,\"w\":\"0OIl\",\"n\":1}", "{\"k\":\"zz\",\"t\":1,\"s\":1}",
                    "{\"k\":\"d\",\"s\":1,\"i\":99999999999,\"j\":1,\"t\":1,\"w\":\"11111111111111111111111111111111\",\"n\":1}", "\u{0}\u{1}garbage", "{\"k\":\"start\",\"t\":-1,\"s\":1}"] {
            assert_eq!(decode(bad.as_bytes()), None, "{bad}");
        }
    }

    /// SAVE -> RESTART -> LOAD = THE LIVE-BUILT HISTORY: a book journaling a market, its finalized dumps written with the writer, the
    /// run's end (windows past their 2 slots saved, the others dropped); a new book loaded from the file holds exactly the first book's
    /// history minus the dropped ones; the whale query agrees for every seller
    #[test]
    fn journal_save_restart_load_equals_live() {
        let dir = tmpdir("jsave");
        let path = dir.join("state.jsonl");
        let h = 24 * 3600 * S;
        let t0 = 1_793_000_000 * S;
        let mut b = DumpBook::new(h);
        b.journal_on();
        let mut fin = Vec::new();
        let txs = market(1_000..1_400, t0);
        feed(&mut b, &txs, &mut fin);
        let (last, dropped) = b.finalize_on_shutdown();
        fin.extend(last);
        assert!(dropped > 0, "the last slots' windows are still open: dropped");
        assert_eq!(b.open_windows() as u64, dropped + b.snapshot().1.iter().filter(|o| o.1 + FOL_SLOTS < b.max_slot()).count() as u64);
        let (tx, rx) = crossbeam_channel::unbounded();
        let st = std::sync::Arc::new(std::sync::Mutex::new(JStats::default()));
        let w = { let (p, st) = (path.clone(), st.clone()); std::thread::spawn(move || journal_writer(p, None, rx, st)) };
        tx.send(JMsg::Start { t: t0 + 1_000 * 212_000_000, s: 1_000 }).unwrap();
        for c in fin.chunks(37) { tx.send(JMsg::Dumps(c.to_vec())).unwrap(); tx.send(JMsg::Beat { t: c[0].t, s: c[0].s }).unwrap(); }
        tx.send(JMsg::Stop { t: b.max_t(), s: b.max_slot() }).unwrap();
        drop(tx);
        w.join().unwrap();
        let g = st.lock().unwrap().clone();
        assert!(g.done && g.errors == 0 && g.dumps == fin.len() as u64 && g.syncs > 0, "{g:?}");
        // the restart, 2 minutes later
        let now = b.max_t() + 120 * S;
        let l = load_state(&path, now, h);
        assert_eq!((l.bad, l.truncated_tail, l.dups, l.old, l.missing, l.err.is_none()), (0, false, 0, 0, false, true));
        assert_eq!(l.sessions.len(), 1);
        assert_eq!((l.sessions[0].t0, l.sessions[0].t1), (t0 + 1_000 * 212_000_000, b.max_t()));
        let mut b2 = DumpBook::new(h);
        b2.load_finalized(&l.dumps.iter().map(|x| x.0).collect::<Vec<_>>());
        // the first book's history minus the windows dropped at the end
        let open_dropped: FxHashSet<(Pk, u64)> = b.snapshot().1.iter().filter(|o| o.1 + FOL_SLOTS >= b.max_slot()).map(|o| (o.0, o.1)).collect();
        let want: Vec<_> = hist_of(&b).into_iter().filter(|x| !open_dropped.contains(&(x.0, x.1))).collect();
        assert_eq!(hist_of(&b2), want);
        assert!(want.len() > 300);
        for w in 9..=12u8 { assert_eq!(b2.whale(&pk(w), 1_390, now), b.whale(&pk(w), 1_390, now), "seller {w}"); }
        // the continuity at the restart: one session of ~85 min ending 2 min before: covered
        let cov = coverage(&[(l.sessions[0].t0, l.sessions[0].t1)], now, 30 * 60 * S);
        assert_eq!((cov.covered_ns, cov.gap_ns), (l.sessions[0].t1 - l.sessions[0].t0, 120 * S));
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// THE CONTINUITY RULE: sessions joined across gaps <= max gap; the latest stretch counts if it ends within max gap of the start;
    /// the arm rule: on at once when the stretch >= the warm-up, partial credit below it, none when too old
    #[test]
    fn coverage_continuity_rule() {
        let m = 60 * S;
        let g = 30 * m;
        // nothing loaded
        assert_eq!(coverage(&[], 1000 * m, g).covered_ns, 0);
        // one 90-min session ending 5 min before the start: 90 min, on at once
        let c = coverage(&[(100 * m, 190 * m)], 195 * m, g);
        assert_eq!((c.covered_ns, c.gap_ns, c.stretches), (90 * m, 5 * m, 1));
        assert!(arm_on(195 * m, 195 * m, 60 * m, c.covered_ns));
        // r24-like restarts: 6 min, 136 min, 0.5 min, ... gaps of seconds: one stretch
        let c = coverage(&[(0, 6 * m), (6 * m + 10 * S, 142 * m), (142 * m + 20 * S, 142 * m + 50 * S)], 143 * m, g);
        assert_eq!((c.covered_ns, c.stretches), (142 * m + 50 * S, 1));
        // a 45-min gap splits; only the last stretch counts (40 min: partial credit, on 20 min after the start)
        let c = coverage(&[(0, 100 * m), (145 * m, 185 * m)], 186 * m, g);
        assert_eq!((c.covered_ns, c.from, c.stretches), (40 * m, 145 * m, 2));
        assert!(!arm_on(186 * m + 19 * m, 186 * m, 60 * m, c.covered_ns) && arm_on(186 * m + 20 * m, 186 * m, 60 * m, c.covered_ns));
        // the stretch ended 31 min before the start: too old, the full warm-up (the entries are still history)
        let c = coverage(&[(0, 100 * m)], 131 * m, g);
        assert_eq!((c.covered_ns, c.gap_ns), (0, 31 * m));
        assert!(!arm_on(131 * m + 59 * m, 131 * m, 60 * m, c.covered_ns));
        // exactly max gap: still counts; a preload span reaching the start joins the journal's sessions
        assert_eq!(coverage(&[(0, 100 * m)], 130 * m, g).covered_ns, 100 * m);
        assert_eq!(coverage(&[(0, 20 * m), (10 * m, 200 * m)], 200 * m, g).covered_ns, 200 * m);
        // spans after the start are cut at it; empty spans ignored
        assert_eq!(coverage(&[(0, 500 * m), (300 * m, 299 * m)], 200 * m, g).covered_ns, 200 * m);
    }

    /// COMPACTION: old sessions / dumps, duplicates, a bad line and an orphan dump in the file; the load keeps the window's, the compacted
    /// rewrite (the writer's first step) holds exactly that and loads back the same; the file shrinks
    #[test]
    fn journal_compaction() {
        let dir = tmpdir("jcompact");
        let path = dir.join("state.jsonl");
        let h = 24 * 3600 * S;
        let now = 1_793_100_000 * S;
        let dd = |k: u64, t: u64, nf: u32| JDump { s: 1_000 + k, i: k as u32, j: 0, t, seller: pk((k % 7) as u8), nf };
        let mut recs = vec![JRec::Dump(dd(0, now - 3 * 3600 * S, 1))];                     // an orphan, recent
        // an old session (ended 30 h ago): dropped whole
        recs.push(JRec::Start { t: now - 40 * 3600 * S, s: 10 });
        for k in 1..50 { recs.push(JRec::Dump(dd(k, now - 39 * 3600 * S + k * S, 2))); }
        recs.push(JRec::Stop { t: now - 30 * 3600 * S, s: 20 });
        // a session across the window's edge: clipped; its old dumps dropped, its recent ones kept
        recs.push(JRec::Start { t: now - 26 * 3600 * S, s: 30 });
        for k in 50..100 { recs.push(JRec::Dump(dd(k, now - 26 * 3600 * S + (k - 50) * 3600 * S / 10, 3))); }
        recs.push(JRec::Beat { t: now - 20 * 3600 * S, s: 40 });
        // a recent session, a duplicate dump, a bad line
        recs.push(JRec::Start { t: now - 2 * 3600 * S, s: 50 });
        for k in 100..140 { recs.push(JRec::Dump(dd(k, now - 2 * 3600 * S + k * S, 4))); }
        recs.push(JRec::Dump(dd(120, now - 2 * 3600 * S + 120 * S, 4)));
        write_lines(&path, &recs);
        let mut f = std::fs::OpenOptions::new().append(true).open(&path).unwrap();
        use std::io::Write;
        f.write_all(b"{\"k\":\"d\",\"s\":broken\n").unwrap();
        f.write_all(encode(&JRec::Stop { t: now - 600 * S, s: 60 }).as_bytes()).unwrap();
        f.write_all(b"\n").unwrap();
        drop(f);
        let l = load_state(&path, now, h);
        assert_eq!((l.bad, l.dups, l.truncated_tail), (1, 1, false));
        assert_eq!(l.old as usize, 49 + 20, "the old session's 49 dumps and the edge session's first 20");
        assert_eq!(l.sessions.len(), 2, "the old session is gone; the edge one clipped");
        assert_eq!(l.sessions[0].t0, now - h);
        assert_eq!(l.dumps.len(), 1 + 30 + 40);
        assert_eq!(l.dumps.iter().filter(|d| d.1.is_none()).count(), 1, "the orphan stays outside every session");
        // the writer's compaction, then a reload: the same
        let before = std::fs::metadata(&path).unwrap().len();
        let (tx, rx) = crossbeam_channel::unbounded::<JMsg>();
        let st = std::sync::Arc::new(std::sync::Mutex::new(JStats::default()));
        drop(tx);
        journal_writer(path.clone(), Some(compact(&l)), rx, st.clone());
        let g = st.lock().unwrap().clone();
        assert!(g.compacted && g.compact_bytes_after < before && g.compact_lines == (71 + 2 * 2) as u64, "{g:?}");
        let l2 = load_state(&path, now, h);
        assert_eq!((l2.bad, l2.dups, l2.old, l2.truncated_tail), (0, 0, 0, false));
        assert_eq!(l2.dumps, l.dumps);
        assert_eq!(l2.sessions, l.sessions);
        assert!(!dir.join("state.jsonl.tmp").exists());
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// DAMAGE: binary junk, damaged lines, a cut last line, an empty file, a missing file, a directory: never a panic; what is readable
    /// is kept, the rest counted
    #[test]
    fn journal_corrupt_and_truncated() {
        let dir = tmpdir("jcorrupt");
        let h = 24 * 3600 * S;
        let now = 1_793_100_000 * S;
        let good = |k: u64| JRec::Dump(JDump { s: 100 + k, i: 1, j: 0, t: now - 100 * S + k, seller: pk(3), nf: 2 });
        let p = dir.join("a.jsonl");
        let mut bytes: Vec<u8> = Vec::new();
        bytes.extend(encode(&JRec::Start { t: now - 200 * S, s: 1 }).bytes()); bytes.push(b'\n');
        bytes.extend(encode(&good(1)).bytes()); bytes.push(b'\n');
        bytes.extend([0u8, 159, 146, 150, 255, 10]);
        bytes.extend(b"not json at all\n{\"k\":\"d\",\"s\":1}\n\n");
        bytes.extend(encode(&good(2)).bytes()); bytes.push(b'\n');
        let cut = encode(&good(3));
        bytes.extend(&cut.as_bytes()[..cut.len() / 2]);
        std::fs::write(&p, &bytes).unwrap();
        let l = load_state(&p, now, h);
        assert_eq!(l.dumps.len(), 2);
        assert!(l.truncated_tail && l.bad == 4, "{l:?}");
        assert_eq!(l.sessions.len(), 1);
        // empty / missing / a directory / pure junk
        std::fs::write(dir.join("empty.jsonl"), b"").unwrap();
        let e = load_state(&dir.join("empty.jsonl"), now, h);
        assert!(e.dumps.is_empty() && !e.missing && e.err.is_none());
        let m = load_state(&dir.join("missing.jsonl"), now, h);
        assert!(m.missing && m.err.is_none() && m.dumps.is_empty());
        let d = load_state(&dir, now, h);
        assert!(d.err.is_some() && d.dumps.is_empty());
        let junk: Vec<u8> = (0..200_000u32).map(|x| (x.wrapping_mul(2_654_435_761) >> 13) as u8).collect();
        std::fs::write(dir.join("junk.bin"), &junk).unwrap();
        let j = load_state(&dir.join("junk.bin"), now, h);
        assert!(j.dumps.is_empty() && j.sessions.is_empty() && j.bad + j.truncated_tail as u64 > 0);
        // a writer that cannot write (its path is a directory): errors counted, never a panic, the engine side never blocks
        let (tx, rx) = crossbeam_channel::unbounded();
        let st = std::sync::Arc::new(std::sync::Mutex::new(JStats::default()));
        let w = { let (p, st) = (dir.clone(), st.clone()); std::thread::spawn(move || journal_writer(p, Some(vec![JRec::Start { t: 1, s: 1 }]), rx, st)) };
        for k in 0..1000 { tx.send(JMsg::Dumps(vec![JDump { s: k, i: 0, j: 0, t: k, seller: pk(1), nf: 0 }])).unwrap(); }
        drop(tx);
        w.join().unwrap();
        let g = st.lock().unwrap().clone();
        assert!(g.errors >= 1 && g.first_err.is_some() && g.done && g.lines == 0, "{g:?}");
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// THE MERGE WITH A BASE: a journal (two earlier sessions) + a recording (the same hours, partly the same dumps) built into a base;
    /// the live book (the journal loaded at its start + this session from a partly seen first slot) merged into it = one book over
    /// everything, each dump once
    #[test]
    fn merge_base_equals_one_book() {
        let h = 24 * 3600 * S;
        let t0 = 1_793_000_000 * S;
        let all = market(1_000..1_600, t0);
        // the "truth": one book over everything (journaling off)
        let mut whole = DumpBook::new(h);
        let mut sink = Vec::new();
        feed(&mut whole, &all, &mut sink);
        // the journal: earlier sessions over slots 1000..1200 (their windows closed by then)
        let mut j = DumpBook::new(h);
        j.journal_on();
        let mut jd = Vec::new();
        feed(&mut j, &all.iter().filter(|x| x.0 < 1_210).cloned().collect::<Vec<_>>(), &mut jd);
        jd.retain(|d| d.s < 1_200);
        // the recording: slots 1100..cut + 2 (its own dumps 1100..cut-1), overlapping the journal on 1100..1199
        let (c0, cut) = (1_400u64, 1_401u64);
        let mut rec = DumpBook::new(h);
        rec.cut = cut;
        feed(&mut rec, &all.iter().filter(|x| x.0 >= 1_100 && x.0 < cut + FOL_SLOTS).cloned().collect::<Vec<_>>(), &mut sink);
        rec.close_all();
        // the base: the preload's way (recording + journal by identity, the recording's wins, by time)
        let mut base_v = rec.all_dumps();
        let have: FxHashSet<(u64, u32, u32)> = base_v.iter().map(|d| (d.s, d.i, d.j)).collect();
        let n_dup = jd.iter().filter(|d| have.contains(&(d.s, d.i, d.j))).count();
        assert!(n_dup > 10, "the journal and the recording share dumps");
        base_v.extend(jd.iter().filter(|d| !have.contains(&(d.s, d.i, d.j))).copied());
        base_v.sort_by_key(|d| (d.t, d.s, d.i, d.j));
        let mut base = DumpBook::new(h);
        base.load_finalized(&base_v);
        let ids: FxHashSet<(u64, u32, u32)> = base_v.iter().map(|d| (d.s, d.i, d.j)).collect();
        // the live book: the journal at its start, then this session from slot c0 (its first txs missed)
        let mut live = DumpBook::new(h);
        live.load_finalized(&jd);
        live.journal_on();
        let mut lf = Vec::new();
        let sess: Vec<_> = all.iter().filter(|x| x.0 >= c0 && !(x.0 == c0 && x.1 < 30)).cloned().collect();
        feed(&mut live, &sess, &mut lf);
        let (merged, old) = merge_base(base, &ids, live);
        assert!(old.dumps() > merged.dumps() / 10);
        // the truth over the covered slots: dumps of 1000..1199 (journal), 1100..1400 (recording), >= 1400 (session); slot 1400 from the
        // recording (its txs < 30 the session missed are there)
        let want: Vec<_> = hist_of(&whole);
        assert_eq!(hist_of(&merged), want, "one book over everything, each dump once");
        assert_eq!(merged.snapshot().1, whole.snapshot().1, "the open windows");
        assert!(merged.has_finalized() || lf.len() > 0, "journaling carried over");
    }

    // ---- dip21: the host's book ----------------------------------------------------------------------------------------------

    /// a synthetic recording dir: one run, the market of `market` written as collector chunks (100 slots each), with no tx at all in
    /// [gap.0, gap.1) (an outage); bt = 1 s per 5 slots from bt0
    fn synth_recording(tag: &str, slots: std::ops::Range<u64>, gap: (u64, u64), bt0: i64) -> (PathBuf, Vec<(u64, u32, i64, Vec<TradeEvent>)>) {
        let dir = tmpdir(tag);
        let run = dir.join("run_20261027_0000");
        std::fs::create_dir_all(run.join("txs")).unwrap();
        let bt = |s: u64| bt0 + (s as i64 - slots.start as i64) / 5;
        let txs: Vec<(u64, u32, i64, Vec<TradeEvent>)> = market(slots.clone(), 0).into_iter().filter(|x| !(gap.0 <= x.0 && x.0 < gap.1)).map(|(s, i, _, ev)| (s, i, bt(s), ev)).collect();
        let mut by: std::collections::BTreeMap<u64, String> = Default::default();
        for (s, i, b, ev) in &txs {
            let refs: Vec<&TradeEvent> = ev.iter().collect();
            by.entry((*s - slots.start) / 100).or_default().push_str(&line(*s, *i, *b, true, &refs));
        }
        for (c, text) in by { gz(&run.join(format!("txs/txs_{}.jsonl.gz", bt0 as u64 + 20 * c)), &text); }
        (dir, txs)
    }

    /// THE BOOK = THE LIVE PATH (synthetic): a full build over the recording equals a DumpBook fed the same txs, every dump whose window is
    /// complete in what was read; one session per continuous stretch (an outage of 300 s splits it)
    #[test]
    fn book_full_equals_live_path() {
        let bt0 = 1_793_000_000i64;
        let (dir, txs) = synth_recording("bookfull", 1_000..3_000, (2_000, 3_500), bt0);
        let h = 24 * 3600 * S;
        let now = (bt0 as u64 + 1_000) * S;
        let runs = run_dirs(&dir).unwrap();
        let p = build_book(&runs, None, now, None, h).unwrap();
        assert!(!p.resumed);
        // the live path over the same txs
        let mut live = DumpBook::new(h);
        live.journal_on();
        let mut fin = Vec::new();
        for (s, i, b, ev) in &txs { for (j, e) in ev.iter().enumerate() { live.ingest(e, *s, *i, j as i32, *b as u64 * S); } fin.extend(live.take_finalized()); }
        let (last, _) = live.finalize_on_shutdown();
        fin.extend(last);
        let mut want: Vec<_> = fin.iter().map(|d| (d.seller, d.s, d.i, d.j, d.t, d.nf)).collect();
        want.sort();
        let mut got: Vec<_> = p.book.dumps.iter().map(|(d, _)| (d.seller, d.s, d.i, d.j, d.t, d.nf)).collect();
        got.sort();
        assert_eq!(got, want, "the book's dumps = the live path's final dumps");
        assert!(got.len() > 300);
        // the outage (slots 2000..3000 have no tx: the recording ends at 1999): one session, ending at the last complete slot
        assert_eq!(p.book.sessions.len(), 1);
        assert_eq!(p.book.sessions[0].s1, p.last_slot - 3);
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// INCREMENTAL = FULL: passes every 7 min of recording (each extending the last book, reading from its end), across an outage, give
    /// the book a single full build gives: the same dumps (counts too) and the same sessions; the held-back dumps reappear
    #[test]
    fn book_incremental_equals_full() {
        let bt0 = 1_793_000_000i64;
        let (dir, _txs) = synth_recording("bookincr", 1_000..9_000, (5_000, 6_000), bt0);
        let h = 24 * 3600 * S;
        let runs = run_dirs(&dir).unwrap();
        let end_bt = bt0 + 8_000 / 5;
        let now = (end_bt as u64 + 60) * S;
        let full = build_book(&runs, None, now, None, h).unwrap();
        assert_eq!(full.book.sessions.len(), 2, "the outage (slots 5000..6000 = 200 s) splits the coverage");
        let mut prev: Option<Loaded> = None;
        let mut passes = 0;
        let mut held = 0u64;
        for until in (bt0 + 30..=end_bt + 420).step_by(420) {
            let p = build_book(&runs, prev.take(), now, Some(until), h).unwrap();
            held += p.held_back;
            // the book through the file, as the bin does
            let f = dir.join("book.jsonl");
            write_book(&f, &p.book).unwrap();
            let l = load_state(&f, now, h);
            assert_eq!((l.bad, l.truncated_tail, l.dups), (0, false, 0));
            prev = Some(l);
            passes += 1;
        }
        let inc = prev.unwrap();
        let key = |l: &Loaded| { let mut v: Vec<_> = l.dumps.iter().map(|(d, _)| (d.seller, d.s, d.i, d.j, d.t, d.nf)).collect(); v.sort(); v };
        assert!(passes >= 5 && held > 0, "{passes} passes, {held} held back");
        assert_eq!(key(&inc), key(&full.book), "the incremental book = the full build");
        assert_eq!(inc.sessions, full.book.sessions, "the same coverage");
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// TWO RUNS, ONE COPY BEHIND (the daily rotation: the old run's tail and the new run written at once; the keeper copies a chunk
    /// mid-write): run A records the odd tokens (slots 1000..5000), run B the even ones (4000..12000); in each pass A's copy is 100 s
    /// behind B's. The book is complete only up to the slower run (2 runs being written: the coverage ends at A's last slot - 3; B's
    /// dumps after it held back), so the passes = a full build of the complete recording; once A stopped (> BOOK_ACTIVE_S behind) the
    /// coverage runs to B's end
    #[test]
    fn book_two_runs_lagging_copy() {
        let bt0 = 1_793_000_000i64;
        let dir = tmpdir("booklag");
        let bt = |s: u64| bt0 + (s as i64 - 1_000) / 5;
        let all = market(1_000..12_000, 0);
        let run_of = |s: u64, i: u32| -> Option<usize> { let odd = (i / 10) % 2 == 1; if odd && s < 5_000 { Some(0) } else if !odd && s >= 4_000 { Some(1) } else { None } };
        let names = ["run_20261026_1415", "run_20261027_1415"];
        // the copies as of `cut` (block time, per run): every chunk rewritten (the keeper's size-differs copy)
        let write = |cuts: [i64; 2]| {
            for (k, name) in names.iter().enumerate() {
                let txs = dir.join(name).join("txs");
                let _ = std::fs::remove_dir_all(&txs);
                std::fs::create_dir_all(&txs).unwrap();
                let mut by: std::collections::BTreeMap<u64, String> = Default::default();
                for (s, i, _, ev) in &all {
                    if run_of(*s, *i) != Some(k) || bt(*s) > cuts[k] { continue; }
                    let refs: Vec<&TradeEvent> = ev.iter().collect();
                    by.entry((*s - 1_000) / 100).or_default().push_str(&line(*s, *i, bt(*s), true, &refs));
                }
                for (c, text) in by { gz(&txs.join(format!("txs_{}.jsonl.gz", bt0 as u64 + 20 * c)), &text); }
            }
        };
        let h = 24 * 3600 * S;
        let end_bt = bt(11_999);
        let mut prev: Option<Loaded> = None;
        let (mut both, mut held) = (0, 0u64);
        for p_bt in (bt0 + 60..=end_bt + 120).step_by(60) {
            write([p_bt - 100, p_bt]);
            let runs = run_dirs(&dir).unwrap();
            let now = p_bt as u64 * S;
            let p = build_book(&runs, prev.take(), now, None, h).unwrap();
            if p.active_runs == 2 {
                both += 1;
                // complete only up to A: nothing of B's beyond A's last slot - 3 is final
                assert!(p.end_slot + 3 <= p.book.sessions.iter().map(|x| x.s1).max().unwrap() + 3 && p.end_slot < p.last_slot, "{} {}", p.end_slot, p.last_slot);
            }
            held += p.held_back;
            let f = dir.join("book.jsonl");
            write_book(&f, &p.book).unwrap();
            prev = Some(load_state(&f, now, h));
        }
        let inc = prev.unwrap();
        // the full build of the complete recording
        write([i64::MAX, i64::MAX]);
        let runs = run_dirs(&dir).unwrap();
        let now = (end_bt as u64 + 120) * S;
        let full = build_book(&runs, None, now, None, h).unwrap();
        let key = |l: &Loaded| { let mut v: Vec<_> = l.dumps.iter().map(|(d, _)| (d.seller, d.s, d.i, d.j, d.t, d.nf)).collect(); v.sort(); v };
        assert!(both >= 3 && held > 0, "{both} passes with both runs written, {held} held back");
        assert_eq!(key(&inc), key(&full.book), "the passes = the full build");
        assert_eq!(inc.sessions, full.book.sessions);
        assert_eq!(full.book.sessions.len(), 1);
        assert_eq!(full.book.sessions[0].s1, 11_996, "A stopped long before B's end: B's last complete slot");
        // the live path over the complete recording (both runs merged)
        let mut live = DumpBook::new(h);
        live.journal_on();
        let mut fin = Vec::new();
        for (s, i, _, ev) in all.iter().filter(|x| run_of(x.0, x.1).is_some()) {
            for (j, e) in ev.iter().enumerate() { live.ingest(e, *s, *i, j as i32, bt(*s) as u64 * S); }
            fin.extend(live.take_finalized());
        }
        fin.extend(live.finalize_on_shutdown().0);
        let mut want: Vec<_> = fin.iter().filter(|d| d.s + 3 <= 11_999).map(|d| (d.seller, d.s, d.i, d.j, d.t, d.nf)).collect();
        want.sort();
        assert_eq!(key(&full.book), want, "the book = the live path");
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// THE BOOK ON REAL DATA (by hand): QUIET_BOOK_REC=<recording base> [QUIET_BOOK_END=<unix s>] [QUIET_BOOK_OUT=dir]
    /// cargo test --release --lib presend_quiet::tests::book_recorded -- --ignored --nocapture
    /// A full 24 h build at END - 1 h, then 6 incremental passes of 10 min each up to END (as the keeper's rhythm) = a full 24 h build at
    /// END; the full build at END = the live path over the same txs; the times, the sizes (plain and gzip)
    #[test]
    #[ignore]
    fn book_recorded() {
        let base = PathBuf::from(std::env::var("QUIET_BOOK_REC").expect("QUIET_BOOK_REC"));
        let runs = run_dirs(&base).unwrap();
        let newest = runs.iter().filter_map(|r| chunks(r, 0, u64::MAX).pop()).map(|x| x.0).max().unwrap();
        let end: i64 = std::env::var("QUIET_BOOK_END").ok().and_then(|x| x.parse().ok()).unwrap_or(newest as i64);
        let out = PathBuf::from(std::env::var("QUIET_BOOK_OUT").unwrap_or_else(|_| std::env::temp_dir().join("quiet_book_recorded").display().to_string()));
        let _ = std::fs::create_dir_all(&out);
        let h = 24 * 3600 * S;
        let now = end as u64 * S;
        // the full build at END
        let t = Instant::now();
        let full = build_book(&runs, None, now, Some(end), h).unwrap();
        let full_s = t.elapsed().as_secs_f64();
        let fpath = out.join("full.jsonl");
        let (lines, bytes) = write_book(&fpath, &full.book).unwrap();
        // the incremental way: a full build at END - 1 h (its own 24 h window), then 10-min passes
        let t = Instant::now();
        let first = build_book(&runs, None, (end as u64 - 3_600) * S, Some(end - 3_600), h).unwrap();
        let first_s = t.elapsed().as_secs_f64();
        let ipath = out.join("incr.jsonl");
        write_book(&ipath, &first.book).unwrap();
        let mut pass_s = Vec::new();
        for k in 1..=6 {
            let until = end - 3_600 + 600 * k;
            let prev = load_state(&ipath, until as u64 * S, h);
            let t = Instant::now();
            let p = build_book(&runs, Some(prev), until as u64 * S, Some(until), h).unwrap();
            write_book(&ipath, &p.book).unwrap();
            pass_s.push((t.elapsed().as_secs_f64(), p.st.chunks, p.added, p.held_back));
        }
        let inc = load_state(&ipath, now, h);
        let key = |l: &Loaded| { let mut v: Vec<_> = l.dumps.iter().map(|(d, _)| (d.seller, d.s, d.i, d.j, d.t, d.nf)).collect(); v.sort(); v };
        let fl = load_state(&fpath, now, h);
        // the sessions: the same ends; a start clipped by the 24 h window is the window's start (the full build: its first tx, within
        // the same second) and keeps its first slot (informational: the coverage is by time)
        let sess_eq = inc.sessions.len() == fl.sessions.len()
            && inc.sessions.iter().zip(&fl.sessions).all(|(a, b)| a.t1 == b.t1 && a.s1 == b.s1 && a.t0.abs_diff(b.t0) <= S);
        let same = key(&inc) == key(&fl) && sess_eq;
        // the live path over the same txs (the full build's window)
        let mut rec = Recording::open(&runs, (end as u64).saturating_sub(24 * 3600 + 900), u64::MAX, end - 24 * 3600, end, false, true);
        let mut live = DumpBook::new(h);
        live.journal_on();
        let mut fin = Vec::new();
        while let Some(x) = rec.next().unwrap() {
            for (j, e) in x.trades.iter().enumerate() { live.ingest(e, x.s, x.i, j as i32, x.bt.max(0) as u64 * S); }
            fin.extend(live.take_finalized());
        }
        fin.extend(live.finalize_on_shutdown().0);
        let mut want: Vec<_> = fin.iter().filter(|d| d.t >= now - h).map(|d| (d.seller, d.s, d.i, d.j, d.t, d.nf)).collect();
        want.sort();
        let gz = std::process::Command::new("gzip").arg("-c").arg(&fpath).output().map(|o| o.stdout.len()).unwrap_or(0);
        eprintln!("BOOK full 24 h build: {full_s:.1} s ({} chunks, {} txs) -> {} dumps, {} sessions, {lines} lines, {:.2} MB ({:.2} MB gzip)", full.st.chunks, full.st.txs,
                  full.book.dumps.len(), full.book.sessions.len(), bytes as f64 / 1e6, gz as f64 / 1e6);
        eprintln!("BOOK incremental: first full build {first_s:.1} s, then 6 passes of 10 min: {:?} (s, chunks, added, held back) | = full build at the end: {same}", pass_s);
        eprintln!("BOOK vs the live path over the same 24 h: {} vs {} dumps, equal: {}", key(&fl).len(), want.len(), key(&fl) == want);
        assert!(same);
        assert_eq!(key(&fl), want);
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
        let cfg = PreloadCfg { path: dir.clone(), hist_ns: h, start_unix_ns: end * S, timeout: Duration::from_secs(3600), journal: Vec::new() };
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
        // dip21, the MAIN-THREAD cost of the journal-aware merge at real size: a 24 h base (the preload's dumps + a journal holding the
        // same 24 h: every identity once), a live book that loaded that 24 h journal at its start and then ran ~5 min; = one book
        let jd = merged.all_dumps();
        let mut base_v: Vec<JDump> = jd.iter().copied().filter(|d| d.s < pre.cut).collect();
        base_v.sort_by_key(|d| (d.t, d.s, d.i, d.j));
        let ids: FxHashSet<(u64, u32, u32)> = base_v.iter().map(|d| (d.s, d.i, d.j)).collect();
        let mut base = DumpBook::new(h);
        base.load_finalized(&base_v);
        let mut live3 = DumpBook::new(h);
        live3.load_finalized(&base_v);
        live3.journal_on();
        let mut rec = Recording::open(&runs, ts_lo, u64::MAX, bt_lo, i64::MAX, false, true);
        while let Some(x) = rec.next().unwrap() {
            if x.s > pre.cut + 1_500 { break; }
            if x.s < pre.cut - 1 || (x.s == pre.cut - 1 && x.i < 100) { continue; }
            for (j, e) in x.trades.iter().enumerate() { live3.ingest(e, x.s, x.i, j as i32, x.bt.max(0) as u64 * S); }
        }
        let t4 = Instant::now();
        let (m3, old) = merge_base(base, &ids, live3);
        let us3 = t4.elapsed().as_secs_f64() * 1e6;
        let t5 = Instant::now();
        drop(old);
        let drop_us = t5.elapsed().as_secs_f64() * 1e6;
        let (c, d) = (m3.snapshot(), whole.snapshot());
        eprintln!("dip21 journal-aware merge at real size (base {} dumps, live = the same 24 h journal + 5 min): {us3:.0} us on the main thread (+ {drop_us:.0} us to drop the old \
                   book: done off the event loop); = one book over everything: {}", base_v.len(), c == d);
        assert_eq!(c.0, d.0);
        assert_eq!(c.1, d.1);
    }

    // ---- dip23 QUIET v2 ring (log-only) ----

    const NS: u64 = 1_000_000_000;

    #[test]
    fn v2_ring_empty_and_unknown_token() {
        let mut r = V2Ring::new();
        let f = r.feats(&pk(1), 500 * NS, 1.0);
        assert_eq!(f, V2Feat { n_tr_60s: 0, at_120s_high: true, maxdd_120s: 0.0, skip: true, n_120s: 0, ring_s: 0.0 });
        r.push(&pk(2), 400 * NS, 2.0);
        // a token the ring never saw: no trades, "at its high" (the study's 0.0), the ring's coverage says how much it saw
        let f = r.feats(&pk(1), 500 * NS, 1.0);
        assert_eq!((f.n_tr_60s, f.n_120s, f.skip, f.ring_s), (0, 0, true, 100.0));
        assert_eq!(f.json()["ring_s"], 100.0);
        assert_eq!(f.json()["skip"], true);
    }

    #[test]
    fn v2_ring_window_expiry_and_count() {
        let mut r = V2Ring::new();
        let m = pk(7);
        // trades at 0, 50, 59.5, 60, 100, 119.9, 120, 150 s; the trigger at t0 = 180 s
        for (t, p) in [(0.0, 1.0), (50.0, 1.0), (59.5, 1.0), (60.0, 1.0), (100.0, 1.0), (119.9, 1.0), (120.0, 1.0), (150.0, 1.0)] {
            r.push(&m, (t * NS as f64) as u64, p);
        }
        let f = r.feats(&m, 180 * NS, 1.0);
        // [120 s, 180 s): the trades at 120 and 150 (the one at 119.9 is out; the 60 s boundary is inclusive at t0 - 60 = 120)
        assert_eq!((f.n_tr_60s, f.n_120s), (2, 5), "{f:?}");
        // the 120 s window [60 s, 180 s): 60, 100, 119.9, 120, 150 (the ring kept those); the one at 59.5 is out
        let tk = r.toks.get(&m).unwrap();
        assert_eq!(tk.q.front().unwrap().0, 60 * NS);
        assert_eq!(tk.q.len(), 5);
        // later: everything but the last expires
        let f = r.feats(&m, 269 * NS, 1.0);
        assert_eq!((f.n_tr_60s, f.n_120s), (0, 1));
        let f = r.feats(&m, 271 * NS, 1.0);
        assert_eq!((f.n_tr_60s, f.n_120s), (0, 0));
        assert_eq!(f.maxdd_120s, 0.0);
    }

    #[test]
    fn v2_ring_high_and_drawdown() {
        let mut r = V2Ring::new();
        let m = pk(3);
        r.push(&m, 10 * NS, 1.00);
        r.push(&m, 20 * NS, 1.25);   // the 120 s high
        r.push(&m, 30 * NS, 1.10);
        r.push(&m, 40 * NS, 0.90);
        // the trigger at 50 s whose pre-trade price is 1.00: 20% under the high -> not at the high; the count is 4 (<= 6)
        let f = r.feats(&m, 50 * NS, 1.00);
        assert!((f.maxdd_120s - 0.2).abs() < 1e-12, "{f:?}");
        assert_eq!((f.n_tr_60s, f.at_120s_high, f.skip), (4, false, false));
        // at the high (within 0.1%): 1.249 vs 1.25 -> dd 0.0008
        let f = r.feats(&m, 50 * NS, 1.249);
        assert!(f.at_120s_high && f.skip, "{f:?}");
        // above the high (a gap in the feed): negative dd, still "at the high"
        let f = r.feats(&m, 50 * NS, 1.30);
        assert!(f.maxdd_120s < 0.0 && f.at_120s_high);
        // just outside the tolerance
        let f = r.feats(&m, 50 * NS, 1.25 * (1.0 - 0.0011));
        assert!(!f.at_120s_high && !f.skip);
        // the high expires out of the window: at 141 s the max of [21 s, 141 s) is 1.10
        let f = r.feats(&m, 141 * NS, 1.10);
        assert!(f.at_120s_high && (f.maxdd_120s).abs() < 1e-12 && f.n_120s == 2, "{f:?}");
        // ties: the newest of equal maxima is kept, so the max survives as long as its latest occurrence
        r.push(&m, 150 * NS, 1.10);
        let f = r.feats(&m, 260 * NS, 1.00);
        assert!((f.maxdd_120s - (0.10 / 1.10)).abs() < 1e-12 && f.n_120s == 1, "{f:?}");
    }

    #[test]
    fn v2_ring_rule_count_threshold_and_sweep() {
        let mut r = V2Ring::new();
        let m = pk(4);
        for k in 0..6 { r.push(&m, (100 + k) * NS, 1.0); }
        let f = r.feats(&m, 110 * NS, 1.0);
        assert_eq!((f.n_tr_60s, f.skip), (6, true), "6 trades: still the candidate skip");
        r.push(&m, 107 * NS, 1.0);
        let f = r.feats(&m, 110 * NS, 1.0);
        assert_eq!((f.n_tr_60s, f.skip), (7, false), "7 trades: kept");
        // the sweep: a token idle for 120 s of the ring's clock is dropped; at most once per 10 s of it
        r.push(&pk(5), 110 * NS, 1.0);
        assert!(r.sweep());
        assert_eq!(r.tokens(), 2);
        r.push(&pk(5), 119 * NS, 1.0);
        assert!(!r.sweep(), "9 s later: no sweep yet");
        r.push(&pk(5), 231 * NS, 1.0);
        assert!(r.sweep());
        assert_eq!((r.tokens(), r.entries()), (1, 2), "token 4 (last trade 107 s) dropped at 231 s; token 5 kept with its 2 entries in the window (119, 231)");
        // a push expires the ring's own old entries (bounded memory): 1000 trades over 1000 s hold <= 121 entries
        let mut r = V2Ring::new();
        for k in 0..1000u64 { r.push(&m, k * NS, 1.0 + (k % 7) as f64); }
        assert!(r.entries() <= 121 && r.entries() >= 120, "{}", r.entries());
        let f = r.feats(&m, 1000 * NS, 1.0);
        assert_eq!((f.n_tr_60s, f.n_120s), (60, 120));
        assert!((f.maxdd_120s - 6.0 / 7.0).abs() < 1e-12);
    }
}

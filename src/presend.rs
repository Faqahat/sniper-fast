//! PRE-SENT conditional buy, trigger T2 "whale buy" (ops/strategies/presend/REPORT.md): the engine's SHADOW detector. It never
//! sends; it logs what the study's pre-sent order would have done (arm / fill / exit / disarm), so the owner can check it live
//! before any money. Flags, records and the offline evaluator: ops/strategies/presend/SHADOW.md.
//! Study code mirrored here (read it first): ops/strategies/presend/ps4_replay.py (`windows_for_token` family T2, the fill
//! search, `path`), ps5_lib.py (`run`: one armed window per token, a fill blocks the token until our sell + 300 ms, armed slots
//! charged), ps6_select.py (the chosen "T2|c" config). Parity with the study: `cargo test --release --lib presend`
//! (testdata/presend_parity.json, made by ops/strategies/presend/ps12_parity.py from the study's own outputs).
//!
//! The rules, as the study code has them (ps4 + ps5 + the ps6 filter), every float operation in the Python's order:
//!   * time = the replay's block-position clock: slot x 212 ms + tx index / max(400, index + 1) x 212 ms (`dip_model::arrival`;
//!     block sizes are unknown live, as on R3 / R4). Every ms below is on this clock.
//!   * balances = tokens bought - tokens sold on the curve per wallet, from the token's first trade (the create tx's dev buy).
//!   * TRIGGER: a buy at curve < 100 SOL by a wallet that is not yet "big" on the token makes it big when it is the creator
//!     (ht 1), a create-slot insider (ht 2: bought in the create slot and is neither the creator nor the create's signer) or
//!     holds >= 3% of supply after the buy (ht 3). Only ht 3 with a holding >= `whale_pct` (5%) at THAT buy opens a window: a
//!     wallet whose first >= 3% buy left it below 5% never triggers later. The create's signer, when it is not the creator, is
//!     not an insider, so its create-slot buy can trigger (the study code does this). Supply = 1e15 raw units (pump.fun: 1e9
//!     tokens x 10^6); the holding % is rounded to float32 as in the study's feature array.
//!   * WINDOW: from st = trigger + `live_ms` (50) to en = min(st + `window_slots` (10) x 212 ms, the whale's first sell after
//!     the trigger + 30 ms).
//!   * FILL, per queue row D = 0 / 5 / 10 ms (a / b / c): the first trade x in [st, en) whose post-trade price is <=
//!     (1 - `drop`) x the trailing reference (the post-trade price of the last trade at least `ref_ms` (50) earlier; the first
//!     trade's pre-trade price when there is none). We land at x + D, behind every trade up to then (m = the last one), and fill
//!     when the price after m is still <= that limit (else: the next crossing). A crossing whose landing is past the window's
//!     long end stops the search (ps4); no fill when the curve after m is >= 100 SOL ("untradeable") or the fill time is not
//!     before en ("late"; ps5 compares the fill time as stored, the offset float32-rounded).
//!   * ONE WINDOW PER TOKEN, per row (ps5): a window arms only if it starts at or after the previous armed window's end (filled:
//!     our sell + 300 ms; else its end); otherwise it is "blocked". Armed slots = max(ceil((end or fill - st) / 212), 1).
//!   * PATH + EXIT (ps4 `path`): `size_sol` (0.55) in after m (pump fee in), followers after us whose min-out our buy breaks are
//!     dropped (slack from the study's table by signature: the follower-slippage model), sells applied; we sell 75 ms into
//!     slot s_in + `exit_slots` (2), or one slot after a slot where the value hit +`tp` / -`sl` when that is earlier; value =
//!     SOL out after pump's fee - size (gross, no tx costs). A "naive" value (no follower dropped) is logged next to it.
//!   * Not followed: tokens not seen from their create (no history), mayhem launches, and the study's non-standard curves (any
//!     of the first 50 trades at curve < 25 or > 200 SOL, or no virtual tokens): the study's tapes exclude them too.
//!   * NOT reproducible live (the evaluator flags them): the study drops tokens with < 5 trades over the whole recording and
//!     opens no window in the tape's last 300 slots; it keys wallets by crc32 (a collision is ~1e-7 per wallet).
//! Order: a slot's trades are processed once the feed is `lag_slots` (2) slots past it, sorted by (tx index, event index) and
//! de-duplicated, so a reordered or doubled delivery inside that lag gives the study's chain order (later ones are counted as
//! "late" and dropped). Records are therefore written ~2 slots after the event; their `t` fields are the feed arrival times.
use crate::dip_model::arrival;
use crate::tx::Pk;
use rustc_hash::{FxHashMap, FxHashSet};
use serde_json::{json, Value};
use std::collections::{BTreeMap, VecDeque};

/// the replay's slot length on the block-position clock (ms)
pub const SMS: f64 = 212.0;
/// pump.fun supply in raw units (1e9 tokens x 10^6)
pub const SUPPLY: f64 = 1e15;
/// a wallet becomes "big" at 3% of supply (ps4 HX = 0.03 x 1e15, exactly 3e13); only the first crossing counts
const HX: i64 = 30_000_000_000_000;
/// no trigger and no fill at curve >= 100 SOL (ps4 UNTRADE_V)
const UNTRADE_V: f64 = 100e9;
/// the path stops at curve >= 110 SOL (ps4 GRADV)
const GRADV: f64 = 110e9;
/// our sell lands 75 ms into its slot (ps4 SELL_LAT)
const SELL_LAT: f64 = 75.0;
/// a fill blocks the token until our sell lands + 300 ms (ps5 MARGIN)
const MARGIN: f64 = 300.0;
/// the window ends 30 ms after the whale's first sell (ps4)
const WHALE_SELL_MS: f64 = 30.0;
/// ps4 WMAX["T2"]: the window's long end (the fill search stop) is 250 slots after it goes live
const WMAX_SLOTS: f64 = 250.0;
/// ps4 HMAX: the path looks 40 slots ahead at most
const HMAX: u64 = 40;
/// the queue rows: name and how many ms after the crossing trade our order is placed (ps4 DFIX)
pub const ROWS: [(&str, f64); 3] = [("a", 0.0), ("b", 5.0), ("c", 10.0)];
pub const NR: usize = 3;
/// the study's cheap cost row (ps5 FEE["cheap"], TIP; KDEF a / b / c = 20 attempts per armed slot): the status line's estimate
/// only; the evaluator computes every cost row
pub const FEE_CHEAP: f64 = (5000.0 + 60_000.0 * 1_000.0 / 1e6) / 1e9;
pub const TIP: f64 = 0.001;
pub const K_ABC: f64 = 20.0;

/// trades processed per `advance` call at most (the rest goes on at the next call): bounds one engine-loop call's time
const PER_CALL: usize = 16;

/// the no-history mint set is cleared beyond this many entries (its counter then counts some mints twice)
const NO_HIST_MAX: usize = 200_000;

/// per-trade marks from the engine (what the reactive bot did on the same trade), carried into the fill record
pub const F_DUMP: u8 = 1;
pub const F_ENV: u8 = 2;
pub const F_PICK: u8 = 4;
pub const F_FIRED: u8 = 8;
pub const F_M2: u8 = 16;

#[derive(Clone, Debug)]
pub struct Params {
    pub whale_pct: f64,
    pub window_slots: u64,
    pub drop: f64,
    pub ref_ms: f64,
    pub live_ms: f64,
    pub size_sol: f64,
    pub exit_slots: u64,
    /// take-profit / stop-loss as fractions; 0 = none
    pub tp: f64,
    pub sl: f64,
    /// a slot is processed when the feed is this many slots past it
    pub lag_slots: u64,
    /// a token with no trade for this many slots and no open window is forgotten
    pub idle_slots: u64,
}

impl Default for Params {
    /// the study's chosen config (ps6_select "T2|c")
    fn default() -> Params {
        Params { whale_pct: 5.0, window_slots: 10, drop: 0.12, ref_ms: 50.0, live_ms: 50.0, size_sol: 0.55, exit_slots: 2, tp: 0.10, sl: 0.20, lag_slots: 2,
                 idle_slots: 6 * 3600 * 1000 / 212 }
    }
}

impl Params {
    pub fn check(&self) -> Result<(), String> {
        let bad = |w: &str| Err(format!("presend: {w}"));
        if !(self.whale_pct > 0.0 && self.whale_pct <= 100.0) { return bad("whale pct must be in (0, 100]"); }
        if self.window_slots == 0 || self.window_slots > 250 { return bad("window slots must be 1..250"); }
        if !(self.drop > 0.0 && self.drop < 1.0) { return bad("drop must be in (0, 1)"); }
        if !(self.ref_ms >= 0.0 && self.ref_ms.is_finite() && self.live_ms >= 0.0 && self.live_ms.is_finite()) { return bad("ref / live ms must be >= 0"); }
        if !(self.size_sol > 0.0 && self.size_sol <= 100.0) { return bad("size must be in (0, 100] SOL"); }
        if self.exit_slots == 0 || self.exit_slots > 38 { return bad("exit slots must be 1..38"); }
        if !(self.tp >= 0.0 && self.tp.is_finite() && self.sl >= 0.0 && self.sl < 1.0) { return bad("tp must be >= 0 and sl in [0, 1) (0 = none)"); }
        if self.lag_slots == 0 { return bad("lag slots must be >= 1"); }
        Ok(())
    }
    pub fn json(&self) -> Value {
        json!({"whale_pct": self.whale_pct, "first_pct": 3.0, "window_slots": self.window_slots, "drop": self.drop, "ref_ms": self.ref_ms, "live_ms": self.live_ms,
               "size_sol": self.size_sol, "exit_slots": self.exit_slots, "tp": self.tp, "sl": self.sl, "rows_ms": ROWS.iter().map(|r| r.1).collect::<Vec<_>>(),
               "lag_slots": self.lag_slots, "idle_slots": self.idle_slots, "untradeable_sol": 100, "whale_sell_ms": WHALE_SELL_MS, "margin_ms": MARGIN})
    }
}

/// one executed curve trade as the engine sees it (one pump TradeEvent of an ok tx)
#[derive(Clone, Debug)]
pub struct In {
    pub mint: Pk, pub s: u64, pub i: u32, pub j: i32, pub sig: [u8; 64], pub user: Pk, pub buy: bool, pub sol: u64, pub tok: u64, pub vsol: u64, pub vtok: u64,
    pub fbps: u64, pub cbps: u64, pub t_rx: u64, pub flags: u8,
}

// ---------------------------------------------------------------------------------------------------------------------
// study helpers
// ---------------------------------------------------------------------------------------------------------------------

/// Python's float floor division `a // b` (CPython float_floor_div: fmod, then snap the quotient)
pub fn py_floordiv(a: f64, b: f64) -> f64 {
    let m = a % b;
    let mut div = (a - m) / b;
    if m != 0.0 && ((b < 0.0) != (m < 0.0)) { div -= 1.0; }
    if div != 0.0 {
        let mut f = div.floor();
        if div - f > 0.5 { f += 1.0; }
        f
    } else { 0.0f64.copysign(a / b) }
}

/// p1_build.slack: a follower's slippage tolerance drawn from the table by its signature (base58), capped at 1e6, float32
pub fn slack_of_sig(sig_b58: &str) -> f64 {
    use sha2::Digest;
    let mut h = sha2::Sha256::new();
    h.update(b"dip");
    h.update(sig_b58.as_bytes());
    let d = h.finalize();
    let x = u32::from_be_bytes([d[0], d[1], d[2], d[3]]) as f64 / 4294967296.0;
    let k = ((x * SLACK.len() as f64) as usize).min(SLACK.len() - 1);
    SLACK[k].min(1e6) as f32 as f64
}

/// p1_build fee rate: (fee bps or 95) + (creator fee bps or 30), / 1e4, float32
pub fn fee_rate(fbps: u64, cbps: u64) -> f64 { (((if fbps != 0 { fbps } else { 95 }) + (if cbps != 0 { cbps } else { 30 })) as f64 / 1e4) as f32 as f64 }

fn b58s(sig: &[u8; 64]) -> String { bs58::encode(sig).into_string() }
fn b58k(k: &Pk) -> String { bs58::encode(k).into_string() }

// ---------------------------------------------------------------------------------------------------------------------
// the path after a fill (ps4 `path`, incremental)
// ---------------------------------------------------------------------------------------------------------------------

#[derive(Clone, Debug)]
struct Path {
    /// drop followers whose slippage our buy breaks (the study's model); false = the naive variant
    slip: bool,
    s_in: u64, size: f64, tp: f64, sl: f64,
    q: f64, v: f64, t: f64, frs: f64, p_ref: f64, rmin: f64, cur: f64,
    poff: Vec<f64>, pmn: Vec<f64>,
    ftp: Option<u64>, fsl: Option<u64>,
    stop: bool, grad: bool,
    /// the tape index of the next trade to apply; the slot of the last one applied
    next: usize, last_s: Option<u64>,
}

/// a path's exit: sell slot, slots after s_in, gross SOL, why, the lowest price ratio held through
#[derive(Clone, Debug)]
struct Exit { so: u64, dd: u64, val: f64, why: &'static str, pmin: f64, grad: bool }

impl Path {
    /// our buy right after trade `m` (everything up to m is ahead of us), landing at `a_land`. None = untradeable
    fn new(m: &Rec, m_idx: usize, a_land: f64, size: f64, slip: bool, tp: f64, sl: f64) -> Option<Path> {
        let fr0 = m.fr; let vb = m.vsol as f64; let tb = m.vtok as f64;
        if vb >= UNTRADE_V { return None; }
        let x = size * 1e9 / (1.0 + fr0); let q = tb * x / (vb + x); let v = vb + x; let t = tb - q;
        let s_land = py_floordiv(a_land, SMS) as u64; let s_in = m.s.max(s_land);
        let frs = fr0;
        let cur = v * q / (t + q) * (1.0 - frs) / 1e9 - size;
        Some(Path { slip, s_in, size, tp, sl, q, v, t, frs, p_ref: vb / tb, rmin: 1e9, cur, poff: Vec::new(), pmn: Vec::new(), ftp: None, fsl: None, stop: false,
                    grad: false, next: m_idx + 1, last_s: None })
    }

    /// one trade after m (the ps4 `path` loop body)
    fn feed(&mut self, r: &Rec) {
        if self.stop { return; }
        let sj = r.s;
        let pos = r.a - sj as f64 * SMS;
        let kj = 2 * sj + if pos >= SELL_LAT { 1 } else { 0 };
        while self.poff.len() as u64 <= HMAX + 1 && 2 * (self.s_in + self.poff.len() as u64) + 1 <= kj { self.poff.push(self.cur); self.pmn.push(self.rmin); }
        if sj > self.s_in + HMAX + 1 || self.poff.len() as u64 > HMAX + 1 { self.stop = true; return; }
        let mut applied = true;
        if r.buy {
            let sol = r.sol as f64; let dt = self.t * sol / (self.v + sol);
            if self.slip && dt < r.tok as f64 / (1.0 + r.slack()) { applied = false; } else { self.v += sol; self.t -= dt; }
        } else {
            let tk = r.tok as f64; let so = self.v * tk / (self.t + tk); self.v -= so; self.t += tk;
        }
        if applied { self.frs = r.fr; }
        self.cur = self.v * self.q / (self.t + self.q) * (1.0 - self.frs) / 1e9 - self.size;
        self.last_s = Some(sj);
        if self.v >= GRADV { self.stop = true; self.grad = true; return; }
        if applied {
            let pr = (self.v / self.t) / self.p_ref;
            if pr < self.rmin { self.rmin = pr; }
            let val = (self.cur + self.size) / self.size;
            if self.tp > 0.0 && self.ftp.is_none() && val >= 1.0 + self.tp { self.ftp = Some(sj); }
            if self.sl > 0.0 && self.fsl.is_none() && val <= 1.0 - self.sl { self.fsl = Some(sj); }
        }
    }

    /// the exit with time limit `c` slots once it is final: every trade before the sell time applied (h: every trade with
    /// arrival < h is known and fed)
    fn exit(&self, c: u64, h: f64) -> Option<Exit> {
        let co = self.s_in + c;
        let a = self.ftp.filter(|&a| a + 1 < co);
        let b = self.fsl.filter(|&b| b + 1 < co);
        let trig = match (a, b) { (None, None) => None, (Some(a), None) => Some(a), (None, Some(b)) => Some(b), (Some(a), Some(b)) => Some(a.min(b)) };
        // "no take-profit / stop-loss before the time limit" is final once every trade of slot co - 2 is applied
        let none_final = self.stop || self.last_s.is_some_and(|s| s + 2 > co) || h >= (co - 1) as f64 * SMS;
        if trig.is_none() && !none_final { return None; }
        let so = trig.map_or(co, |t| t + 1);
        let dd = so - self.s_in;
        let (val, pmin) = if (self.poff.len() as u64) > dd { (self.poff[dd as usize], self.pmn[dd as usize]) }
            else if self.stop || h >= (so + 1) as f64 * SMS { (self.cur, self.rmin) } else { return None };
        let why = match (a, b) { (Some(a), Some(b)) if a == b => "tp_sl", (Some(a), Some(b)) => if a < b { "tp" } else { "sl" }, (Some(_), None) => "tp", (None, Some(_)) => "sl",
                                 _ => "time" };
        Some(Exit { so, dd, val, why, pmin, grad: self.grad && self.poff.len() as u64 <= dd })
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// per-token state
// ---------------------------------------------------------------------------------------------------------------------

/// one trade of a followed token (chain order)
#[derive(Clone, Debug)]
struct Rec {
    s: u64, i: u32, j: i32, a: f64, p: f64, refp: f64, buy: bool, sol: u64, tok: u64, vsol: u64, vtok: u64, fr: f64, u: u32, sig: [u8; 64], t_rx: u64,
    flags: u8,
    /// the follower slack of this buy (NaN = not computed yet) and the signature's base58 (~4 us to encode), each made once
    sk: std::cell::Cell<f64>,
    s58: std::cell::OnceCell<String>,
}

impl Rec {
    fn sig58(&self) -> &str { self.s58.get_or_init(|| b58s(&self.sig)) }
    fn slack(&self) -> f64 {
        let v = self.sk.get();
        if !v.is_nan() { return v; }
        let v = slack_of_sig(self.sig58());
        self.sk.set(v);
        v
    }
}

#[derive(Clone, Copy, Debug, Default)]
struct Wal { bal: i64, became: bool, ins: bool }

#[derive(Clone, Copy, Debug, PartialEq)]
enum Arm { Pending, Armed, Blocked }

#[derive(Clone, Copy, Debug, PartialEq)]
enum St {
    /// not armed (yet)
    Idle,
    /// looking for a crossing from this tape index
    Search(usize),
    /// a crossing at x: waiting until every trade up to the landing time is known
    Wait(usize, f64),
    /// no fill: ends at the window end
    Closing,
    /// ended without a fill (aend set)
    Ended,
    /// filled: the paths run until the exit
    Filled,
    /// filled and exited (records written)
    Done,
}

#[derive(Clone, Debug)]
struct Row {
    arm: Arm, st: St, aend: Option<f64>, hit: Option<&'static str>, filled: bool,
    paths: Option<Box<[Path; 2]>>, model_exit: Option<Exit>, xt: Option<f64>, freed: bool,
}

impl Row {
    fn new() -> Row { Row { arm: Arm::Pending, st: St::Idle, aend: None, hit: None, filled: false, paths: None, model_exit: None, xt: None, freed: false } }
    /// the row has stopped attempting (blocked, ended or filled)
    fn stopped(&self) -> bool { self.arm == Arm::Blocked || matches!(self.st, St::Ended | St::Filled | St::Done) }
    /// nothing left to do
    fn finished(&self) -> bool { self.arm == Arm::Blocked || matches!(self.st, St::Ended | St::Done) }
}

#[derive(Clone, Debug)]
struct Win {
    id: u64, j: usize, whale: u32, st: f64, en0: f64, enl0: f64,
    /// the whale's first sell after the trigger (its arrival) and its record fields
    je: Option<f64>,
    je_info: Option<Value>,
    rows: [Row; NR],
    disarmed: bool,
}

impl Win {
    /// ps5's window end: min(st + W slots, the whale's first sell + 30 ms)
    fn en(&self) -> f64 { match self.je { Some(a) => (a + WHALE_SELL_MS).min(self.en0), None => self.en0 } }
    /// ps4's window end (the fill search stops at a landing past it)
    fn enl(&self) -> f64 { match self.je { Some(a) => (a + WHALE_SELL_MS).min(self.enl0), None => self.enl0 } }
}

struct Tok {
    mint: String, s0: u64, creator: Pk, signer: Pk, t_create: u64,
    /// not followed any more ("launch_filter")
    out: Option<&'static str>,
    tape: VecDeque<Rec>, base: usize, n: usize,
    p_first: f64, rp: Option<usize>,
    uidx: FxHashMap<Pk, u32>, us: Vec<Wal>, upk: Vec<Pk>,
    /// a wallet's base58 text, made once (for the records)
    ustr: Vec<std::cell::OnceCell<String>>,
    last_post: Option<(u64, u64)>, gaps: u32,
    wins: Vec<Win>,
    free: [f64; NR], block: [Option<u64>; NR],
    last_slot: u64,
}

impl Tok {
    fn rec(&self, k: usize) -> &Rec { &self.tape[k - self.base] }
    fn user58(&self, u: u32) -> &str { self.ustr[u as usize].get_or_init(|| b58k(&self.upk[u as usize])) }
    /// the last tape index with arrival <= t, from index `from` (which must qualify)
    fn last_le(&self, from: usize, t: f64) -> usize {
        let mut m = from;
        while m + 1 < self.n && self.rec(m + 1).a <= t { m += 1; }
        m
    }
    fn tinfo(&self, k: usize) -> Value {
        let r = self.rec(k);
        json!({"sig": r.sig58(), "slot": r.s, "idx": r.i, "j": r.j, "t": r.t_rx, "a": r.a, "user": self.user58(r.u), "buy": r.buy, "sol": r.sol, "tok": r.tok,
               "vsol": r.vsol, "vtok": r.vtok})
    }
    /// drop tape records nothing will read again (before every open window's next read; the trailing reference is kept)
    fn prune(&mut self) {
        let mut keep = self.rp.unwrap_or(self.base);
        for w in &self.wins {
            keep = keep.min(w.j);
            for r in &w.rows {
                match r.st { St::Search(k) | St::Wait(k, _) => keep = keep.min(k), _ => {} }
                if let Some(ps) = &r.paths { for p in ps.iter() { keep = keep.min(p.next); } }
            }
        }
        while self.base < keep && !self.tape.is_empty() { self.tape.pop_front(); self.base += 1; }
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// counters
// ---------------------------------------------------------------------------------------------------------------------

#[derive(Clone, Debug, Default)]
pub struct Stats {
    pub creates: u64, pub mayhem: u64, pub trades: u64, pub no_hist_trades: u64, pub no_hist_mints: u64, pub late: u64, pub dups: u64, pub gaps: u64,
    pub excluded: u64, pub retired: u64,
    pub triggers: u64, pub below_pct: u64, pub armed: [u64; NR], pub blocked: [u64; NR], pub fills: [u64; NR], pub late_hits: [u64; NR], pub untradeable: [u64; NR],
    pub exits: [u64; NR], pub gross: [f64; NR], pub gross_naive: [f64; NR], pub armed_slots: [u64; NR], pub disarms: u64,
}

// ---------------------------------------------------------------------------------------------------------------------
// the shadow
// ---------------------------------------------------------------------------------------------------------------------

/// a record for the engine's log, with an optional short terminal line
pub struct Ev { pub rec: Value, pub line: Option<String> }

pub struct Shadow {
    pub p: Params,
    /// boxed: a map resize moves pointers, not token states (a resize must not stall the engine's loop)
    toks: FxHashMap<Pk, Box<Tok>>,
    /// trades of slots not processed yet
    pending: BTreeMap<u64, Vec<In>>,
    /// the slot being processed (its trades sorted and de-duplicated) and how far; `floor`: the highest slot started (later
    /// trades of it are late)
    cur: Option<(u64, Vec<In>, usize)>,
    floor: Option<u64>,
    /// every slot <= `done` is processed; `target`: the slot the processing works toward
    done: Option<u64>,
    target: u64,
    /// tokens with open windows (stepped as the clock moves)
    open: FxHashSet<Pk>,
    /// mints traded but not followed (first 8 bytes), for one skip record / count per mint; sized so it never resizes before
    /// it is cleared
    no_hist: FxHashSet<u64>,
    wid: u64,
    out: Vec<Ev>,
    pub st: Stats,
    last_retire: u64,
}

impl Shadow {
    pub fn new(p: Params) -> Shadow {
        let mut toks = FxHashMap::default(); toks.reserve(1 << 13);
        let mut no_hist = FxHashSet::default(); no_hist.reserve(NO_HIST_MAX + 1024);
        Shadow { p, toks, pending: BTreeMap::new(), cur: None, floor: None, done: None, target: 0, open: FxHashSet::default(), no_hist, wid: 0, out: Vec::new(),
                 st: Stats::default(), last_retire: 0 }
    }
    pub fn tokens(&self) -> usize { self.toks.len() }
    /// every slot <= this is processed (PRE-SEND LIVE: its trigger parity is final up to here)
    pub fn done_slot(&self) -> Option<u64> { self.done }
    pub fn open_windows(&self) -> usize { self.toks.values().map(|t| t.wins.len()).sum() }

    /// a pump create seen by the engine (its executed tx): the token is followed from here
    pub fn create(&mut self, mint: Pk, slot: u64, creator: Pk, signer: Pk, mayhem: bool, t_rx: u64) {
        if self.toks.contains_key(&mint) { return; }
        self.st.creates += 1;
        if mayhem { self.st.mayhem += 1; return; }
        self.toks.insert(mint, Box::new(Tok { mint: b58k(&mint), s0: slot, creator, signer, t_create: t_rx, out: None, tape: VecDeque::new(), base: 0, n: 0, p_first: 0.0,
            rp: None, uidx: FxHashMap::default(), us: Vec::new(), upk: Vec::new(), ustr: Vec::new(), last_post: None, gaps: 0, wins: Vec::new(), free: [f64::NEG_INFINITY; NR],
            block: [None; NR], last_slot: slot }));
    }

    /// one executed trade (any order inside the lag)
    pub fn push(&mut self, t: In) {
        if self.floor.is_some_and(|d| t.s <= d) || self.done.is_some_and(|d| t.s <= d) { self.st.late += 1; return; }
        self.pending.entry(t.s).or_default().push(t);
    }

    /// the feed's newest slot: process every slot `lag_slots` behind it (at most PER_CALL trades per call; the rest at the next
    /// calls), then move the clock of the open windows
    pub fn advance(&mut self, slot_now: u64) {
        self.target = self.target.max(slot_now.saturating_sub(self.p.lag_slots));
        if self.done.is_some_and(|d| self.target <= d) { return; }
        if !self.process_upto(self.target, PER_CALL) { return; }
        let upto = self.target;
        self.done = Some(upto);
        self.tick((upto + 1) as f64 * SMS);
        if upto >= self.last_retire + 2048 { self.last_retire = upto; self.retire(upto); }
    }

    /// TESTS / offline replays: the tape is complete (no trade will come): process everything and close every window as the
    /// study does at its tape end
    pub fn complete(&mut self) {
        let s = self.pending.last_key_value().map(|(&s, _)| s).unwrap_or(0).max(self.target);
        self.process_upto(s, usize::MAX); self.done = Some(s); self.target = s;
        self.tick(f64::INFINITY);
    }

    /// the run ends: process what is buffered; windows still open get a "run_end" disarm (their outcome is unknown)
    pub fn finish(&mut self) {
        let s = self.pending.last_key_value().map(|(&s, _)| s).unwrap_or(0).max(self.target);
        self.process_upto(s, usize::MAX); self.done = Some(s); self.target = s;
        let mints: Vec<Pk> = self.open.iter().copied().collect();
        for m in mints {
            let Some(tk) = self.toks.get_mut(&m) else { continue };
            for w in tk.wins.iter_mut() { if !w.disarmed { Self::disarm(tk.mint.as_str(), w, "run_end", &mut self.st, &mut self.out); } }
            tk.wins.clear();
        }
        self.open.clear();
    }

    pub fn drain(&mut self) -> Vec<Ev> { std::mem::take(&mut self.out) }

    /// process the buffered trades of slots <= upto in chain order, at most `budget` of them; true when none is left
    fn process_upto(&mut self, upto: u64, mut budget: usize) -> bool {
        loop {
            if self.cur.is_none() {
                let Some((&s, _)) = self.pending.first_key_value() else { return true };
                if s > upto { return true; }
                let mut v = self.pending.remove(&s).expect("first key");
                v.sort_by_key(|t| (t.i, t.j));
                let n0 = v.len();
                v.dedup_by_key(|t| (t.i, t.j));
                self.st.dups += (n0 - v.len()) as u64;
                self.floor = Some(s);
                self.cur = Some((s, v, 0));
            }
            let t = {
                let (_, v, k) = self.cur.as_mut().expect("set above");
                if *k >= v.len() { None } else { *k += 1; Some(v[*k - 1].clone()) }
            };
            match t {
                None => { self.cur = None; }
                Some(t) => {
                    if budget == 0 { if let Some((_, _, k)) = self.cur.as_mut() { *k -= 1; } return false; }
                    budget -= 1;
                    self.trade(t);
                }
            }
        }
    }

    fn tick(&mut self, h: f64) {
        if self.open.is_empty() { return; }
        let mints: Vec<Pk> = self.open.iter().copied().collect();
        for m in mints { self.step_token(&m, h); }
    }

    fn retire(&mut self, upto: u64) {
        let idle = self.p.idle_slots;
        let before = self.toks.len();
        self.toks.retain(|_, t| !t.wins.is_empty() || t.last_slot + idle >= upto);
        self.st.retired += (before - self.toks.len()) as u64;
        if self.no_hist.len() > NO_HIST_MAX { self.no_hist.clear(); }
    }

    /// one trade, in chain order
    fn trade(&mut self, t: In) {
        let p = self.p.clone();
        let Some(tk) = self.toks.get_mut(&t.mint) else {
            self.st.no_hist_trades += 1;
            if self.no_hist.insert(u64::from_le_bytes(t.mint[..8].try_into().unwrap())) {
                self.st.no_hist_mints += 1;
                // a single buy that alone is whale-sized: an arm we cannot check (the token's history is unknown)
                let pct = t.tok as f64 / SUPPLY * 100.0;
                if t.buy && pct >= p.whale_pct {
                    self.out.push(Ev { rec: json!({"ev": "presend_skip", "mint": b58k(&t.mint), "why": "no_history", "sig": b58s(&t.sig), "slot": t.s, "idx": t.i, "t": t.t_rx,
                        "pct": pct}), line: None });
                }
            }
            return;
        };
        if tk.out.is_some() { return; }
        self.st.trades += 1;
        // the study's non-standard curves (p1_build: any of the first 50 trades at curve < 25 / > 200 SOL, or no virtual tokens)
        if tk.n < 50 && (t.vsol < 25_000_000_000 || t.vsol > 200_000_000_000 || t.vtok == 0) {
            tk.out = Some("launch_filter"); self.st.excluded += 1;
            for w in tk.wins.iter_mut() { if !w.disarmed { Self::disarm(tk.mint.as_str(), w, "token_gone", &mut self.st, &mut self.out); } }
            tk.wins.clear(); tk.tape.clear(); tk.base = tk.n; tk.rp = None;
            self.open.remove(&t.mint);
            return;
        }
        // a feed gap (a trade the feed missed): the pre-state differs from the last post-state
        let (vf, tf, sf, kf) = (t.vsol as f64, t.vtok as f64, t.sol as f64, t.tok as f64);
        let pre = if t.buy { (t.vsol.wrapping_sub(t.sol), t.vtok.wrapping_add(t.tok)) } else { (t.vsol.wrapping_add(t.sol), t.vtok.wrapping_sub(t.tok)) };
        if tk.last_post.is_some_and(|l| l != pre) { tk.gaps += 1; self.st.gaps += 1; }
        tk.last_post = Some((t.vsol, t.vtok));
        if tk.n == 0 {
            let (vp, tp) = if t.buy { (vf - sf, tf + kf) } else { (vf + sf, tf - kf) };
            tk.p_first = vp / tp.max(1.0);
        }
        let u = match tk.uidx.get(&t.user) {
            Some(&u) => u,
            None => { let u = tk.us.len() as u32; tk.uidx.insert(t.user, u); tk.us.push(Wal::default()); tk.upk.push(t.user); tk.ustr.push(std::cell::OnceCell::new()); u }
        };
        let a = arrival(t.s, t.i);
        let k = tk.n;
        // the trailing reference: the last trade at least ref_ms earlier (ps4 rix)
        let mut rp = tk.rp;
        loop {
            let c = match rp { Some(r) => r + 1, None => tk.base };
            if c >= k || tk.rec(c).a > a - p.ref_ms { break; }
            rp = Some(c);
        }
        tk.rp = rp;
        let refp = match rp { Some(r) => tk.rec(r).p, None => tk.p_first };
        tk.tape.push_back(Rec { s: t.s, i: t.i, j: t.j, a, p: vf / tf, refp, buy: t.buy, sol: t.sol, tok: t.tok, vsol: t.vsol, vtok: t.vtok, fr: fee_rate(t.fbps, t.cbps), u,
                                sig: t.sig, t_rx: t.t_rx, flags: t.flags, sk: std::cell::Cell::new(f64::NAN), s58: std::cell::OnceCell::new() });
        // B: a buy on a token with an open window may be a follower of a fill: its slack now (one trade's cost), not in a burst
        // when a fill resolves and the paths catch up
        if t.buy && !tk.wins.is_empty() { tk.tape.back().expect("just pushed").slack(); }
        tk.n += 1;
        tk.last_slot = tk.last_slot.max(t.s);
        // balances; insiders = create-slot buyers other than the creator and the signer
        {
            let w = &mut tk.us[u as usize];
            if t.buy { w.bal += t.tok as i64; } else { w.bal -= t.tok as i64; }
            if t.buy && t.s == tk.s0 && t.user != tk.creator && t.user != tk.signer { w.ins = true; }
        }
        // the whale's first sell after its trigger ends its window 30 ms later
        if !t.buy {
            for w in tk.wins.iter_mut() {
                if w.whale == u && w.je.is_none() && k > w.j {
                    w.je = Some(a);
                    w.je_info = Some(json!({"sig": b58s(&t.sig), "slot": t.s, "idx": t.i, "j": t.j, "a": a, "t": t.t_rx, "tok": t.tok, "sol": t.sol}));
                }
            }
        }
        // the trigger (ps4 T2 + the ps6 filter)
        if t.buy && vf < UNTRADE_V && !tk.us[u as usize].became {
            let w = tk.us[u as usize];
            let ht = if t.user == tk.creator { 1 } else if w.ins { 2 } else if w.bal >= HX { 3 } else { 0 };
            if ht != 0 { tk.us[u as usize].became = true; }
            if ht == 3 {
                let hpct = (w.bal as f64 / SUPPLY * 100.0) as f32 as f64;
                if hpct >= p.whale_pct {
                    self.st.triggers += 1;
                    self.wid += 1;
                    let st = a + p.live_ms;
                    let mut win = Win { id: self.wid, j: k, whale: u, st, en0: st + p.window_slots as f64 * SMS, enl0: a + p.live_ms + WMAX_SLOTS * SMS, je: None,
                                        je_info: None, rows: [Row::new(), Row::new(), Row::new()], disarmed: false };
                    // per row: armed now unless an earlier window still decides the row's free time (then "pending")
                    let mut rows_s = serde_json::Map::new();
                    for (r, row) in win.rows.iter_mut().enumerate() {
                        if tk.block[r].is_none() {
                            if st >= tk.free[r] { row.arm = Arm::Armed; tk.block[r] = Some(win.id); self.st.armed[r] += 1; } else { row.arm = Arm::Blocked; self.st.blocked[r] += 1; }
                        }
                        rows_s.insert(ROWS[r].0.into(), json!(match row.arm { Arm::Armed => "armed", Arm::Blocked => "blocked", Arm::Pending => "pending" }));
                    }
                    let (wallet, tsig) = (tk.user58(u).to_string(), tk.rec(k).sig58().to_string());
                    let rec = json!({"ev": "presend_arm", "w": win.id, "mint": tk.mint, "wallet": wallet, "pct": hpct, "bal": w.bal, "sig": tsig, "slot": t.s,
                        "idx": t.i, "j": t.j, "t": t.t_rx, "a": a, "st": st, "en0": win.en0, "age_slots": t.s.saturating_sub(tk.s0),
                        "age_s": t.t_rx.saturating_sub(tk.t_create) as f64 / 1e9, "sol": t.sol, "tok": t.tok, "vsol": t.vsol, "vtok": t.vtok, "rows": Value::Object(rows_s)});
                    let line = win.rows.iter().any(|r| r.arm != Arm::Blocked).then(|| format!("  PRESEND ARM w{} {} whale {} {:.1}% ({:.2} SOL) age {} slots | {}", win.id, tk.mint,
                        &wallet[..8.min(wallet.len())], hpct, t.sol as f64 / 1e9, t.s.saturating_sub(tk.s0), win.rows.iter().enumerate().map(|(r, x)| format!("{} {}", ROWS[r].0,
                            match x.arm { Arm::Armed => "on", Arm::Blocked => "blocked", Arm::Pending => "waits" })).collect::<Vec<_>>().join(", ")));
                    self.out.push(Ev { rec, line });
                    tk.wins.push(win);
                    self.open.insert(t.mint);
                } else { self.st.below_pct += 1; }
            }
        }
        let mint = t.mint;
        if self.open.contains(&mint) { self.step_token(&mint, a); }
        if let Some(tk) = self.toks.get_mut(&mint) { if tk.wins.is_empty() || tk.tape.len() > 64 { tk.prune(); } }
    }

    /// move every open window of the token as far as the known tape allows (h: every trade with arrival < h is known)
    fn step_token(&mut self, mint: &Pk, h: f64) {
        let p = self.p.clone();
        let Some(tk) = self.toks.get_mut(mint) else { self.open.remove(mint); return };
        let mut changed = true;
        while changed {
            changed = false;
            for wi in 0..tk.wins.len() {
                for r in 0..NR { if Self::step_row(tk, wi, r, h, &p, &mut self.st, &mut self.out) { changed = true; } }
                let w = &mut tk.wins[wi];
                // written once every row has stopped AND the window end is final (the whale's first sell seen, or the time past it), so
                // "en" is the study's window end even when every armed row filled (or every row was blocked) before it
                if !w.disarmed && w.rows.iter().all(|x| x.stopped()) && (w.je.is_some() || h > w.en0 - WHALE_SELL_MS) {
                    let why = if w.rows.iter().all(|x| x.arm == Arm::Blocked) { "blocked" }
                        else if w.rows.iter().filter(|x| x.arm == Arm::Armed).all(|x| x.filled) { "filled" }
                        else if w.en() < w.en0 { "whale_sold" } else { "expired" };
                    Self::disarm(tk.mint.as_str(), w, why, &mut self.st, &mut self.out);
                }
            }
        }
        tk.wins.retain(|w| !(w.disarmed && w.rows.iter().all(|x| x.finished())));
        if tk.wins.is_empty() { self.open.remove(mint); }
    }

    fn disarm(mint: &str, w: &mut Win, why: &str, st: &mut Stats, out: &mut Vec<Ev>) {
        w.disarmed = true;
        st.disarms += 1;
        let mut rows = serde_json::Map::new();
        for (r, x) in w.rows.iter().enumerate() {
            let slots = match (x.arm, x.aend) { (Arm::Armed, Some(e)) => ((e - w.st).max(0.0) / SMS).ceil().max(1.0) as u64, _ => 0 };
            if x.arm == Arm::Armed { st.armed_slots[r] += slots; }
            rows.insert(ROWS[r].0.into(), json!({"armed": match x.arm { Arm::Armed => json!(true), Arm::Blocked => json!(false), Arm::Pending => Value::Null },
                "filled": x.filled, "hit": x.hit, "aend": x.aend, "slots": slots, "open": !x.stopped()}));
        }
        out.push(Ev { rec: json!({"ev": "presend_disarm", "w": w.id, "mint": mint, "why": why, "st": w.st, "en": w.en(), "en0": w.en0, "whale_sell": w.je_info,
                                  "rows": Value::Object(rows)}), line: None });
    }

    /// one row of one window, as far as it can go; true when its state changed
    fn step_row(tk: &mut Tok, wi: usize, r: usize, h: f64, p: &Params, st: &mut Stats, out: &mut Vec<Ev>) -> bool {
        let mut changed = false;
        loop {
            let (wid, wj, wst, en, enl, whale) = { let w = &tk.wins[wi]; (w.id, w.j, w.st, w.en(), w.enl(), w.whale) };
            let (arm, state) = { let x = &tk.wins[wi].rows[r]; (x.arm, x.st) };
            match state {
                St::Idle => match arm {
                    Arm::Blocked => return changed,
                    Arm::Armed => { tk.wins[wi].rows[r].st = St::Search(wj + 1); changed = true; }
                    Arm::Pending => {
                        // the earlier armed window's free time is final once it no longer blocks the row (ps5: windows in start order)
                        if tk.block[r].is_some() { return changed; }
                        if wst >= tk.free[r] { tk.wins[wi].rows[r].arm = Arm::Armed; tk.block[r] = Some(wid); st.armed[r] += 1; }
                        else { tk.wins[wi].rows[r].arm = Arm::Blocked; st.blocked[r] += 1; }
                        changed = true;
                    }
                },
                St::Search(next) => {
                    if next >= tk.n {
                        if h >= en { tk.wins[wi].rows[r].st = St::Closing; changed = true; continue; }
                        return changed;
                    }
                    let (xa, xp, xref) = { let x = tk.rec(next); (x.a, x.p, x.refp) };
                    tk.wins[wi].rows[r].st = if xa < wst { St::Search(next + 1) } else if xa >= en { St::Closing }
                        else if xp / xref <= 1.0 - p.drop { St::Wait(next, xa + ROWS[r].1) } else { St::Search(next + 1) };
                    changed = true;
                }
                St::Wait(x, a_land) => {
                    if !(h > a_land) { return changed; }
                    changed = true;
                    if a_land >= enl { tk.wins[wi].rows[r].st = St::Closing; continue; }
                    let m = tk.last_le(x, a_land);
                    let xr = tk.rec(x).clone(); let mr = tk.rec(m).clone();
                    let lim = xr.refp * (1.0 - p.drop);
                    if !(mr.p <= lim) { tk.wins[wi].rows[r].st = St::Search(x + 1); continue; }
                    let Some(model) = Path::new(&mr, m, a_land, p.size_sol, true, p.tp, p.sl) else {
                        let row = &mut tk.wins[wi].rows[r]; row.hit = Some("untradeable"); row.st = St::Closing; st.untradeable[r] += 1; continue;
                    };
                    let ft = xr.a + ((a_land - xr.a) as f32 as f64);
                    if !(ft < en) { let row = &mut tk.wins[wi].rows[r]; row.hit = Some("late"); row.st = St::Closing; st.late_hits[r] += 1; continue; }
                    st.fills[r] += 1;
                    let s_in = model.s_in; let fr0 = mr.fr; let xin = p.size_sol * 1e9 / (1.0 + fr0);
                    let trig_s = tk.rec(wj).s;
                    let by_whale = !xr.buy && xr.u == whale;
                    let rec = json!({"ev": "presend_fill", "w": wid, "mint": tk.mint, "row": ROWS[r].0, "d_ms": ROWS[r].1, "x": tk.tinfo(x), "ref": xr.refp, "p_x": xr.p,
                        "drop_pct": (1.0 - xr.p / xr.refp) * 100.0, "lim": lim, "m": tk.tinfo(m), "p_m": mr.p, "n_ahead": m - x, "a_land": a_land, "ft": ft, "s_in": s_in,
                        "slots_after_trigger": s_in.saturating_sub(trig_s), "seller_is_whale": by_whale,
                        "entry": {"vsol": mr.vsol, "vtok": mr.vtok, "fr": fr0, "sol_in": xin, "tokens": model.q, "p_before": model.p_ref, "p_avg": xin / model.q},
                        "imit": {"dump": xr.flags & F_DUMP != 0, "env": xr.flags & F_ENV != 0, "pick": xr.flags & F_PICK != 0, "fired": xr.flags & F_FIRED != 0,
                                 "m2": xr.flags & F_M2 != 0}});
                    let line = (r == NR - 1).then(|| format!("  PRESEND FILL w{wid} {} row {} | drop -{:.1}% vs the price 50 ms before, {} trade(s) ahead | entry slot +{} after the whale{}",
                        tk.mint, ROWS[r].0, (1.0 - xr.p / xr.refp) * 100.0, m - x, s_in.saturating_sub(trig_s), if by_whale { " | seller = the whale" } else { "" }));
                    out.push(Ev { rec, line });
                    let naive = Path { slip: false, ..model.clone() };
                    let row = &mut tk.wins[wi].rows[r];
                    row.filled = true; row.aend = Some(ft); row.paths = Some(Box::new([model, naive])); row.st = St::Filled;
                }
                St::Closing => {
                    if !(h >= en) { return changed; }
                    let row = &mut tk.wins[wi].rows[r];
                    row.aend = Some(en); row.st = St::Ended;
                    if !row.freed { row.freed = true; tk.free[r] = en; if tk.block[r] == Some(wid) { tk.block[r] = None; } }
                    return true;
                }
                St::Filled => {
                    // the paths take every known trade; then: are the exits final?
                    let (n, base) = (tk.n, tk.base);
                    let Tok { tape, wins, free, block, mint, .. } = &mut *tk;
                    let row = &mut wins[wi].rows[r];
                    let paths = row.paths.as_mut().expect("a filled row has its paths");
                    for pth in paths.iter_mut() {
                        while pth.next < n && !pth.stop { pth.feed(&tape[pth.next - base]); pth.next += 1; }
                        if pth.stop { pth.next = n; }
                    }
                    let c = p.exit_slots;
                    if row.model_exit.is_none() {
                        if let Some(e) = paths[0].exit(c, h) {
                            let xt = (paths[0].s_in + e.dd) as f64 * SMS + 75.0;
                            row.xt = Some(xt); row.model_exit = Some(e); changed = true;
                            if !row.freed { row.freed = true; free[r] = xt + MARGIN; if block[r] == Some(wid) { block[r] = None; } }
                        }
                    }
                    let (Some(e), Some(nv)) = (row.model_exit.clone(), paths[1].exit(c, h)) else { return changed };
                    st.exits[r] += 1; st.gross[r] += e.val; st.gross_naive[r] += nv.val;
                    let s_in = paths[0].s_in; let xt = row.xt.expect("set with the model exit");
                    let net = e.val - (TIP + 2.0 * FEE_CHEAP);
                    let rec = json!({"ev": "presend_exit", "w": wid, "mint": mint.as_str(), "row": ROWS[r].0, "s_in": s_in, "exit_slot": e.so, "hold_slots": e.dd, "why": e.why,
                        "grad": e.grad, "pnl": e.val, "pnl_naive": nv.val, "naive_exit_slot": nv.so, "naive_why": nv.why, "pmin": e.pmin, "xt": xt, "free_at": xt + MARGIN,
                        "net_cheap": net});
                    let line = (r == NR - 1).then(|| format!("  PRESEND EXIT w{wid} {} row {} {} after {} slot(s): {:+.4} SOL gross ({:+.4} naive), {:+.4} after the tip + 2 tx",
                        mint, ROWS[r].0, e.why, e.dd, e.val, nv.val, net));
                    out.push(Ev { rec, line });
                    row.st = St::Done; row.paths = None;
                    return true;
                }
                St::Ended | St::Done => return changed,
            }
        }
    }

    /// the counters for the engine's 60 s status line
    pub fn line(&self) -> String {
        let s = &self.st;
        let net = |r: usize| s.gross[r] - s.exits[r] as f64 * (TIP + 2.0 * FEE_CHEAP) - (K_ABC * s.armed_slots[r] as f64 - s.fills[r] as f64).max(0.0) * FEE_CHEAP;
        format!(" | PRESEND shadow: tokens {} (no-history mints {}) triggers {} armed a/b/c {}/{}/{} fills {}/{}/{} exits {}/{}/{} gross {:+.3}/{:+.3}/{:+.3} SOL \
                 net(cheap, 20/slot) {:+.3}/{:+.3}/{:+.3} | open {} late {} gaps {}",
            self.toks.len(), s.no_hist_mints, s.triggers, s.armed[0], s.armed[1], s.armed[2], s.fills[0], s.fills[1], s.fills[2], s.exits[0], s.exits[1], s.exits[2],
            s.gross[0], s.gross[1], s.gross[2], net(0), net(1), net(2), self.open.len(), s.late, s.gaps)
    }

    pub fn stats_json(&self) -> Value {
        let s = &self.st;
        json!({"tokens": self.toks.len(), "creates": s.creates, "mayhem": s.mayhem, "trades": s.trades, "no_history_trades": s.no_hist_trades, "no_history_mints": s.no_hist_mints,
               "late": s.late, "dups": s.dups, "gaps": s.gaps, "excluded": s.excluded, "retired": s.retired, "triggers": s.triggers, "below_pct": s.below_pct,
               "armed": s.armed, "blocked": s.blocked, "fills": s.fills, "late_hits": s.late_hits, "untradeable": s.untradeable, "exits": s.exits, "gross": s.gross,
               "gross_naive": s.gross_naive, "armed_slots": s.armed_slots, "disarms": s.disarms, "open_windows": self.open.len()})
    }
}

/// the follower slack table (sorted; ops/overnight/verify2/work/a8_slack.json rows, exactly as p1_build.SLACK): 711 values
#[rustfmt::skip]
const SLACK: [f64; 711] = [
    1.000000082740371e-09, 2.1249999537786834e-09, 2.1249999537786834e-09, 2.339360261061074e-09, 2.687500222364747e-09,
    2.687500222364747e-09, 2.687500222364747e-09, 2.687500222364747e-09, 3.5312501811546326e-09, 3.5312501811546326e-09,
    3.5312501811546326e-09, 4.0899406084093926e-09, 1.628272894294014e-08, 1.8517477329282883e-08, 3.7916667583459684e-08,
    3.7916667583459684e-08, 3.7916667583459684e-08, 3.7916667583459684e-08, 3.7916667583459684e-08, 4.125000097054965e-08,
    4.971966660605176e-08, 5.385954260361814e-08, 0.0008703108883434396, 0.0009876543209876854, 0.0011072315769249386,
    0.0025380001376986705, 0.002722480319998777, 0.003492519614555878, 0.003579936357107405, 0.005113688178352005, 0.007267202509265047,
    0.009021685678791691, 0.00939042412012725, 0.009486372161419787, 0.010000000000006892, 0.010000048717149435, 0.010000048717149435,
    0.01019922520463279, 0.01118297831634485, 0.01152198956567152, 0.011776358947933163, 0.012066409730331795, 0.012318357206788866,
    0.012802711966957592, 0.014291184447471128, 0.014605276637452258, 0.014988744401749798, 0.015197506692541829, 0.015651269708070625,
    0.015916659500665453, 0.016011142901294795, 0.016304438391985032, 0.017265190971253563, 0.01743908851236098, 0.017478504051186006,
    0.01814942079545201, 0.01860936436656857, 0.018662389202675822, 0.018662389215075015, 0.01985985259843437, 0.01985985259843437,
    0.01999999796000007, 0.020000000159374975, 0.02185685511536639, 0.022189945870915606, 0.022395429494099117, 0.023288373571296317,
    0.02338952087162305, 0.023639064146988575, 0.023783179848772207, 0.02570711028121897, 0.025798641328369287, 0.02585952060533314,
    0.026543464252980042, 0.026972971556283865, 0.027901623109206408, 0.02800001590001977, 0.02821681535722731, 0.028625063090626846,
    0.029031553719970127, 0.02911814709148053, 0.029693194529780698, 0.02983502629683188, 0.03036984168470025, 0.030592985470163203,
    0.030927814203795423, 0.031850843842798904, 0.03296391056596848, 0.034098172739882804, 0.03487554969502793, 0.0356320275494435,
    0.036253265851417193, 0.037100074544659245, 0.03743207282963046, 0.03822494810592336, 0.03890795041551165, 0.04000000000003756,
    0.040000000000300684, 0.040743690982814273, 0.0413939842635318, 0.04166665979328976, 0.042290463582002724, 0.04310163043832915,
    0.04310163043832915, 0.043612448480282895, 0.04621712169244163, 0.04688217836835196, 0.04698025508307313, 0.048765870824684754,
    0.04906826653828866, 0.04923573901236189, 0.04923573901236189, 0.04923573901236189, 0.04948365734010274, 0.049484102478734915,
    0.0498651258688112, 0.04999999471021943, 0.04999999479946293, 0.05108499710619685, 0.05151309546512639, 0.05152470160293232,
    0.052435067537156765, 0.05443168322051828, 0.05498938862710823, 0.055431979388611774, 0.05556885330799122, 0.05620553844712339,
    0.05673940878617678, 0.05715883342295669, 0.060223792641922236, 0.060441638813575116, 0.061851831072490704, 0.06257561314880178,
    0.06365522148554437, 0.06382978723409849, 0.06775805163137094, 0.06778595599291859, 0.06833727299105785, 0.06936614859976364,
    0.07047575510643633, 0.07101305499878907, 0.07110327951235096, 0.07154866194338316, 0.07229440509588936, 0.07459779841975056,
    0.07481654289013884, 0.07481780361644996, 0.07481916901976349, 0.07481916901976349, 0.07482128745903682, 0.0748215020413947,
    0.07482287538562105, 0.07482450817839092, 0.07482518645474134, 0.0773009932217914, 0.07828853773179945, 0.07948277771953083,
    0.07948277771953083, 0.08053333342457858, 0.08137915286289954, 0.0851960263613134, 0.08663946186769556, 0.08668431030278878,
    0.08670745888615983, 0.0869565195617974, 0.0884396401509715, 0.08913207077118646, 0.08988386670134396, 0.09289617041077758,
    0.09318887873470172, 0.09323817979966109, 0.09431049502832667, 0.09496841265528477, 0.09669198398160561, 0.0973418887514097,
    0.09739365534633126, 0.09739366640163483, 0.09739367738993643, 0.0973936783180882, 0.09739368067133758, 0.0973936823416035,
    0.09739368301471996, 0.09739368503771795, 0.09739368615071697, 0.09739368742628618, 0.0981455536420095, 0.09854815276460971,
    0.10118293662444522, 0.10177822010250459, 0.10287346986555979, 0.10519281852577289, 0.10556822845170055, 0.10585696829143854,
    0.10807404868070969, 0.10910099033998133, 0.10943145412125399, 0.11111111138888896, 0.11111111138888896, 0.11111111138888896,
    0.11111111138888896, 0.11111111138888896, 0.11111111472222235, 0.11224433262542521, 0.11395047180761897, 0.11723446935013793,
    0.11723453257276817, 0.12080746369831297, 0.1246290997137387, 0.12546110436988145, 0.12624022812414948, 0.12850176531650503,
    0.13130325444931068, 0.13252551948249325, 0.1358024691358024, 0.13589674856593348, 0.13715547464119138, 0.1376979380069927,
    0.1377810929805856, 0.1392388745263875, 0.14127623600010963, 0.1426687250409704, 0.14362244151409032, 0.14497476130085563,
    0.14552405590747308, 0.14829056621686498, 0.14942199564953773, 0.14988030506655114, 0.14997593987341884, 0.14998796583304208,
    0.14999999520328955, 0.1500000085440376, 0.1500000094651377, 0.15000037375012143, 0.15050866105520933, 0.15266488929054645,
    0.1544513644782115, 0.1598037607744951, 0.15996748065310307, 0.16126182885104456, 0.16440973900731248, 0.1684836355405468,
    0.16875292808040587, 0.16963786842017003, 0.16997395996235087, 0.17081905794543562, 0.17104109039354776, 0.17143669053762856,
    0.17647058807261207, 0.17647058807261207, 0.17647058823507744, 0.18772264368089853, 0.1883414199966964, 0.19091731624291963,
    0.1968483658606428, 0.20000000000012252, 0.20000003037020275, 0.2000016050021467, 0.20958075989073266, 0.20987643939209621,
    0.21128565722342363, 0.21135877225251587, 0.21286380899214352, 0.21298597174369527, 0.21666836646221133, 0.21956104922750685,
    0.21956106983635837, 0.2201545449315081, 0.22240286679195886, 0.22242690242153063, 0.2251561295340454, 0.22761841694567542,
    0.2288636790043399, 0.22982532327827387, 0.2321825152317769, 0.23228214557186044, 0.2329997987887027, 0.2392001039676659,
    0.24006580690030188, 0.24312272889347142, 0.2499591558019325, 0.2500000000001288, 0.25072647374807655, 0.25493636006137255,
    0.25803239169731196, 0.2583480846923283, 0.2609294814783709, 0.2690033608224416, 0.2698173084408666, 0.2704735439803365,
    0.2741888177967695, 0.2853470437013683, 0.28600224651488615, 0.2868950294022883, 0.2884139945651034, 0.2886597360790262,
    0.2953367875636588, 0.2965410103927322, 0.29882182950080494, 0.29887296142636366, 0.29927736094764623, 0.3000000063000001,
    0.3029359932525113, 0.30313329284208446, 0.30955440088912556, 0.3138431758051081, 0.3154568978526078, 0.31752304536606357,
    0.319874473063557, 0.3203463113333582, 0.3214094189190617, 0.3234804144786978, 0.32851772505547805, 0.33333331989720305,
    0.33333331989779813, 0.33333331989847625, 0.3333333198998074, 0.333333319910325, 0.3333333199113817, 0.33863561968352207,
    0.3408372093116967, 0.346490990890743, 0.3481928445914748, 0.3537176505339994, 0.35864601149876707, 0.359402241528332,
    0.36281558609454345, 0.3664478288230335, 0.36660181320697016, 0.36844405266400315, 0.36878397296614507, 0.37522627128226627,
    0.3770835420597649, 0.3777193562877543, 0.3778717338158677, 0.3778717338158677, 0.3778717338158677, 0.3778717338158677,
    0.37953032026253797, 0.38080893082958367, 0.38332562201578435, 0.38849597789892476, 0.3900706577315538, 0.39045008752005317,
    0.3952120954141374, 0.396547500045179, 0.396548566128047, 0.39654859009898313, 0.3978716386271579, 0.39956397637586516,
    0.40593731690036416, 0.4070693238256251, 0.409229097412976, 0.41327920085659153, 0.414069769205075, 0.4141733984728413,
    0.416214908939746, 0.41644439910560194, 0.4176360279440665, 0.42068832083240126, 0.4248795257991773, 0.4266122939908441,
    0.4266123130841286, 0.42857142857143926, 0.42857142857258035, 0.4287924765313258, 0.42879357335107593, 0.4287941173608154,
    0.4287942435698393, 0.42921130277996444, 0.4333056123927035, 0.43870897597986236, 0.443118712157637, 0.44551040840358236,
    0.44626725401047684, 0.44717185539059967, 0.44991212029090555, 0.454527878209638, 0.4551957446216328, 0.4553090798895456,
    0.4609000880340308, 0.4623840311517151, 0.46663304410413065, 0.4686437102771841, 0.468940287805373, 0.47312744937246265,
    0.4751978733517719, 0.47756423766660583, 0.47784415096490296, 0.48393931811105095, 0.49267742491198363, 0.49629629480000004,
    0.49646852416579024, 0.49647136077148746, 0.5000000109921876, 0.5007464205795247, 0.5037379838427123, 0.5053518897282379,
    0.512251895374148, 0.5177922678339226, 0.5293322694747509, 0.5674617356017599, 0.5721879405846599, 0.5726098876296213,
    0.5775005854620274, 0.5802272035912364, 0.5871238380691157, 0.5882175630569646, 0.6023591554373928, 0.6054294303580463,
    0.6090279934804204, 0.636434178701275, 0.6387874206853081, 0.6444774925842744, 0.646383468345896, 0.6477467623947246, 0.655451121181309,
    0.6652296605397501, 0.6666666666666667, 0.6666666666670173, 0.6666666666670173, 0.6666666666673497, 0.6666666666677068,
    0.6666666666680403, 0.6666666666683221, 0.6666666666691625, 0.6799414123018941, 0.7195509925101715, 0.7284456639145585,
    0.7604260626533217, 0.7605468830602911, 0.8090740755917827, 0.828288650339684, 0.9286466519154808, 0.9576901070484349,
    0.9999999920037657, 1.0209599163962118, 1.0434325007667984, 1.0565680640017767, 1.076852059391343, 1.0946957976808043,
    1.123200215719399, 1.5000000000007923, 1.7160346864720197, 1.7454934751593956, 1.7555065688870273, 2.0059313746286547, 2.077185790359,
    2.250538515391348, 2.380440655901163, 2.496209486662566, 2.847110918708334, 3.5444240456610103, 3.5925364267132833, 3.633073736426324,
    3.8654431598193995, 3.9077510761090073, 3.9236584417384517, 3.9439712184387634, 3.958375147928928, 4.002004891736039, 4.019698887421351,
    4.04384198175234, 4.054107281520441, 4.075269259947186, 4.166548284683973, 4.176369637458501, 4.184254687061272, 4.240417985885958,
    4.433043813219832, 5.45999885821879, 5.924486142129837, 6.006217271915421, 6.1082866902487165, 6.199621024474547, 6.765130838640663,
    7.583274976572229, 7.949335877259113, 8.999999959745148, 36.65344745398776, 48.593675405508364, 95.02868254803542, 95.99611282875614,
    99.01458877770423, 99.6628521053838, 127245779.76021121, 169470140.08018276, 227003004.64647168, 228139084.9562937, 230585848.85463622,
    18424177158.0, 19275699049.0, 36569652272.0, 54343054333.0, 162369745447.0, 201610926138.0, 238169107616.0, 361012288726.0,
    388366165539.0, 615546984615.0, 684192264290.0, 695414838777.0, 719539608085.0, 871332646700.0, 897817239618.0, 910804365086.0,
    946842606742.0, 949129044793.0, 981704858740.0, 994049101429.0, 999855368397.0, 1002336616772.0, 1057855269404.0, 1062588030780.0,
    1080397678538.0, 1092035510339.0, 1118090226365.0, 1124965431082.0, 1131521011955.0, 1134508526085.0, 1136924385871.0, 1164687530285.0,
    1167807444709.0, 1171614414496.0, 1171772208542.0, 1174920652613.0, 1175903193062.0, 1179068312391.0, 1219864058443.0, 1255329341716.0,
    1258820731794.0, 1258820731794.0, 1280078245416.0, 1287283853981.0, 1287283853981.0, 1290909494989.0, 1290909494989.0, 1294550474977.0,
    1294550474977.0, 1315975126622.0, 1324241049623.0, 1324241049623.0, 1324241049852.0, 1324769696584.0, 1328024055161.0, 1331823294261.0,
    1331823294261.0, 1339470846565.0, 1339470846565.0, 1350575243336.0, 1370729340827.0, 1377862272266.0, 1651510224650.0, 2182964738350.0,
    2199552691658.0, 2204561853300.0, 2358967867944.0, 2961901422867.0, 2999330543765.0, 3653771068444.0, 3917691508100.0, 3922273975989.0,
    3987411500447.0, 3991283591315.0, 3992330625413.0, 4182241654213.0, 4511412288045.0, 4655231412148.0, 4655856292358.0, 4894065022265.0,
    5007323958990.0, 5090112680656.0, 5108108869659.0, 5149044801041.0, 5199265517426.0, 5287728572502.0, 5431018766765.0, 5431606456613.0,
    5449270598522.0, 5492953457662.0, 5510534554664.0, 5524042698745.0, 5727865664338.0, 5737745345358.0, 5864283374062.0, 5934266658396.0,
    6030598034527.0, 6231273189114.0, 6509308014349.0, 6516519656976.0, 6865961772087.0, 6910855676155.0, 6960545029198.0, 6987274364993.0,
    7069435899525.0, 7070330896809.0, 7090716215806.0, 7772951294529.0, 7799708187069.0, 7838990836753.0, 7876042729903.0, 8306942135767.0,
    8307766246091.0, 8610613319550.0, 8654699455169.0, 9188287533967.0, 9196213095908.0, 9235526641253.0, 9686211935157.0, 9955286059210.0,
    10014296824476.0, 10258241015237.0, 10545789848514.0, 10820079015046.0, 10989729153335.0, 11060531728979.0, 11329128372484.0,
    11402973657328.0, 11501948227935.0, 11540994989742.0, 11811933270962.0, 11842039040497.0, 11977254618872.0, 12040583184948.0,
    12758109919287.0, 12820825312328.0, 12848279413784.0, 12926362823477.0, 12967949722181.0, 13095503579240.0, 13471341440089.0,
    13492590467686.0, 13694836956514.0, 13730161716268.0, 13923302033532.0, 13976222591707.0, 14281770831671.0, 14427323238838.0,
    14443418939710.0, 14815683121036.0, 14820161073233.0, 14864985554956.0, 15072502858683.0, 15141124828272.0, 15165738366820.0,
    15188668508822.0, 15439709837038.0, 15546171877963.0, 15768950925128.0, 16086520856756.0, 16088545095679.0, 16470567004979.0,
    16557764818278.0, 16596237542224.0, 16721662671390.0, 17111958170181.0, 17346437272411.0, 17603083736906.0, 18318952498299.0,
    18619441077003.0, 18780741882845.0, 18876852856752.0, 19055461708708.0, 19152454925260.0, 19446369018717.0, 19475615197582.0,
    19566051452816.0, 19606573489113.0, 19734446436356.0, 20024470409338.0, 20231692786982.0, 20436649388721.0, 20532495264597.0,
    20710105135344.0, 21301757933832.0, 21597202854612.0, 21917542325945.0, 21970860967642.0, 22063104447410.0, 22357064385656.0,
    22423617689177.0, 22455626339288.0, 22461731074415.0, 22666635371267.0, 22792233979051.0, 22890879753162.0, 23037699941982.0,
    23162947410319.0, 23277414074958.0, 23430478621981.0, 23713410935563.0, 23963082998235.0, 24032846700378.0, 24083129760505.0,
    24974658378607.0, 25782566657476.0, 28152159949134.0, 30003697780162.0, 31309385134255.0, 32502158208348.0, 32691065620321.0,
    33817611249664.0, 36721833758306.0, 36892655368666.0, 41759743556486.0, 43585674668091.0, 46150673482696.0, 50323305124771.0,
    52004015384374.0, 58659973190317.0, 64182203594927.0, 75240020235431.0,
];

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::{HashMap, HashSet};

    fn load_json(p: &str) -> Option<Value> { std::fs::read_to_string(p).ok().and_then(|s| serde_json::from_str(&s).ok()) }
    fn pk(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }
    fn sig64(s: &str) -> [u8; 64] { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }
    fn num(v: &Value) -> f64 { match v { Value::String(s) => s.parse().unwrap(), _ => v.as_f64().unwrap() } }

    /// a parity token: (mint, create slot, creator, signer, its trades as the engine pushes them)
    fn ins(tk: &Value) -> (Pk, u64, Pk, Pk, Vec<In>) {
        let mint = pk(tk["mint"].as_str().unwrap());
        let la = &tk["launch"];
        let users: Vec<Pk> = tk["users"].as_array().unwrap().iter().map(|u| pk(u.as_str().unwrap())).collect();
        let signer = pk(la["user"].as_str().unwrap());
        let creator = la["creator"].as_str().map(pk).unwrap_or(signer);
        let v = tk["trades"].as_array().unwrap().iter().map(|r| In { mint, s: r[0].as_u64().unwrap(), i: r[1].as_u64().unwrap() as u32, j: r[2].as_i64().unwrap() as i32,
            sig: sig64(r[3].as_str().unwrap()), user: users[r[4].as_u64().unwrap() as usize], buy: r[5].as_u64().unwrap() == 1, sol: r[6].as_u64().unwrap(),
            tok: r[7].as_u64().unwrap(), vsol: r[8].as_u64().unwrap(), vtok: r[9].as_u64().unwrap(), fbps: r[10].as_u64().unwrap_or(0), cbps: r[11].as_u64().unwrap_or(0),
            t_rx: 0, flags: 0 }).collect();
        (mint, la["slot"].as_u64().unwrap(), creator, signer, v)
    }

    /// feed one token's tape through the shadow: 0 = like the engine (push, advance when the slot moves), 1 = all at once,
    /// 2 = like the engine but every slot's trades reversed and some delivered twice; then the tape is complete
    fn run(tk: &Value, mode: u8) -> Vec<Value> {
        let (mint, s0, cre, sgn, v) = ins(tk);
        let mut sh = Shadow::new(Params::default());
        sh.create(mint, s0, cre, sgn, false, 0);
        match mode {
            0 => for t in v { let s = t.s; sh.push(t); sh.advance(s); },
            1 => for t in v { sh.push(t); },
            _ => {
                let mut by: BTreeMap<u64, Vec<In>> = BTreeMap::new();
                for t in v { by.entry(t.s).or_default().push(t); }
                for (s, mut ts) in by {
                    ts.reverse();
                    let dup: Vec<In> = ts.iter().step_by(3).cloned().collect();
                    for t in ts.into_iter().chain(dup) { sh.push(t); }
                    sh.advance(s + 1);
                }
            }
        }
        sh.complete();
        sh.drain().into_iter().map(|e| e.rec).collect()
    }

    #[derive(Default, Debug)]
    struct Cmp { tokens: usize, windows: usize, arm_missing: usize, arm_extra: usize, arm_excluded: usize, below_armed: usize, st_en_pct: usize,
                 rows: usize, armed: usize, armed_bad: usize, fills: usize, fill_bad: usize, exit_bad: usize, nofill_bad: usize, aend_bad: usize, slots_bad: usize,
                 late: usize, untradeable: usize, ex: Vec<String> }

    impl Cmp {
        fn bad(&self) -> usize { self.arm_missing + self.arm_extra + self.below_armed + self.st_en_pct + self.armed_bad + self.fill_bad + self.exit_bad + self.nofill_bad + self.aend_bad + self.slots_bad }
        fn note(&mut self, s: String) { if self.ex.len() < 12 { self.ex.push(s); } }
    }

    /// the shadow's records of one token vs the study's windows (ps4 + ps5) on it
    fn compare(tk: &Value, recs: &[Value], s_end: Option<u64>, c: &mut Cmp) {
        let mint = tk["mint"].as_str().unwrap();
        let trades = tk["trades"].as_array().unwrap();
        let key: HashMap<(u64, u64, i64), usize> = trades.iter().enumerate().map(|(k, r)| ((r[0].as_u64().unwrap(), r[1].as_u64().unwrap(), r[2].as_i64().unwrap()), k)).collect();
        let kof = |x: &Value| key[&(x["slot"].as_u64().unwrap(), x["idx"].as_u64().unwrap(), x["j"].as_i64().unwrap())];
        // the study opens no window on a token with < 5 trades, nor in the tape's last 300 slots
        let excluded = |slot: u64| trades.len() < 5 || s_end.is_some_and(|e| slot > e - 300);
        let mut arms: HashMap<usize, &Value> = HashMap::new();
        let (mut fills, mut exits, mut dis): (HashMap<(u64, String), &Value>, HashMap<(u64, String), &Value>, HashMap<u64, &Value>) = Default::default();
        for r in recs {
            match r["ev"].as_str().unwrap() {
                "presend_arm" => {
                    let k = kof(r);
                    if excluded(r["slot"].as_u64().unwrap()) { c.arm_excluded += 1; continue; }
                    arms.insert(k, r);
                }
                "presend_fill" => { fills.insert((r["w"].as_u64().unwrap(), r["row"].as_str().unwrap().to_string()), r); }
                "presend_exit" => { exits.insert((r["w"].as_u64().unwrap(), r["row"].as_str().unwrap().to_string()), r); }
                "presend_disarm" => { dis.insert(r["w"].as_u64().unwrap(), r); }
                _ => {}
            }
        }
        let below: HashSet<usize> = tk["ht3_below"].as_array().map(|a| a.iter().map(|x| x["j"].as_u64().unwrap() as usize).collect()).unwrap_or_default();
        c.below_armed += below.iter().filter(|j| arms.contains_key(j)).count();
        let study: HashMap<usize, &Value> = tk["windows"].as_array().unwrap().iter().map(|w| (w["j"].as_u64().unwrap() as usize, w)).collect();
        c.tokens += 1; c.windows += study.len();
        for j in arms.keys() { if !study.contains_key(j) { c.arm_extra += 1; c.note(format!("{mint}: extra arm at trade {j}")); } }
        for (j, sw) in &study {
            let Some(a) = arms.get(j) else { c.arm_missing += 1; c.note(format!("{mint}: study window at trade {j} not armed")); continue };
            let w = a["w"].as_u64().unwrap();
            let d = dis.get(&w).copied();
            if num(&a["st"]) != num(&sw["st"]) || num(&a["pct"]) != num(&sw["hpct"]) || d.map(|d| num(&d["en"])) != Some(num(&sw["en"])) {
                c.st_en_pct += 1;
                let why = d.map(|d| d["why"].clone()).unwrap_or_default();
                c.ex.insert(0, format!("{mint} w{w}: st/en/pct differ ({why}): ours {} {} {:?} | study {} {} {}", a["st"], a["pct"], d.map(|d| &d["en"]), sw["st"], sw["hpct"], sw["en"]));
            }
            for (r, _) in ROWS.iter() {
                c.rows += 1;
                let sr = &sw["rows"][r];
                let dr = d.map(|d| &d["rows"][r]);
                let armed = dr.and_then(|x| x["armed"].as_bool());
                let s_armed = sr["armed"].as_bool().unwrap();
                if armed != Some(s_armed) { c.armed_bad += 1; c.note(format!("{mint} w{w} row {r}: armed {armed:?} vs study {s_armed}")); continue; }
                if !s_armed { continue; }
                c.armed += 1;
                let dr = dr.unwrap();
                if num(&dr["aend"]) != num(&sr["aend"]) { c.aend_bad += 1; c.note(format!("{mint} w{w} row {r}: aend {} vs {}", dr["aend"], sr["aend"])); }
                if dr["slots"].as_u64() != sr["slots"].as_u64() { c.slots_bad += 1; }
                let f = fills.get(&(w, r.to_string()));
                let sf = &sr["fill"];
                let s_valid = sf.is_object() && sf["valid"].as_bool().unwrap();
                match (f, s_valid) {
                    (Some(f), true) => {
                        c.fills += 1;
                        let ok = kof(&f["x"]) as u64 == sf["x"].as_u64().unwrap() && kof(&f["m"]) as u64 == sf["m"].as_u64().unwrap() && num(&f["a_land"]) == num(&sf["a_land"])
                            && num(&f["ft"]) == num(&sf["ft"]) && f["s_in"].as_u64() == sf["s_in"].as_u64();
                        if !ok { c.fill_bad += 1; c.note(format!("{mint} w{w} row {r}: fill differs: ours x {} m {} a_land {} s_in {} | study {}", kof(&f["x"]), kof(&f["m"]), f["a_land"], f["s_in"], sf)); }
                        match exits.get(&(w, r.to_string())) {
                            Some(e) => {
                                let ok = (num(&e["pnl"]) as f32) == (num(&sf["pnl"]) as f32) && e["hold_slots"].as_u64() == sf["off"].as_u64() && num(&e["xt"]) == num(&sf["xt"]);
                                if !ok { c.exit_bad += 1; c.note(format!("{mint} w{w} row {r}: exit differs: ours {} {} {} | study pnl {} off {} xt {}", e["pnl"], e["hold_slots"], e["xt"], sf["pnl"], sf["off"], sf["xt"])); }
                            }
                            None => { c.exit_bad += 1; c.note(format!("{mint} w{w} row {r}: no exit record")); }
                        }
                    }
                    (None, false) => {
                        // the study's first hit there was late (ps5 invalid) or none; ours: no fill, the same hit kind
                        let hit = dr["hit"].as_str();
                        if sf.is_object() {
                            // ps4's first hit is past ps5's window end: a crossing after en (we stop searching there: no hit) or one inside it
                            // whose landing is not before en (ours: "late")
                            let x_a = num(&sf["a_land"]) - ROWS.iter().find(|(n, _)| n == r).unwrap().1;
                            let want = if x_a >= num(&sw["en"]) { None } else { Some("late") };
                            if hit == want { c.late += 1; } else { c.nofill_bad += 1; c.note(format!("{mint} w{w} row {r}: study late hit (crossing at {x_a}, en {}), ours {hit:?}", sw["en"])); }
                        }
                        else if hit == Some("untradeable") { c.untradeable += 1; }
                        else if hit.is_some() { c.nofill_bad += 1; c.note(format!("{mint} w{w} row {r}: ours hit {hit:?}, study none")); }
                    }
                    (Some(f), false) => { c.fill_bad += 1; c.note(format!("{mint} w{w} row {r}: we fill at trade {} (study: {})", kof(&f["x"]), sf)); }
                    (None, true) => { c.fill_bad += 1; c.note(format!("{mint} w{w} row {r}: study fills at trade {} ({}), we do not (hit {:?})", sf["x"], sf["pnl"], dr["hit"])); }
                }
            }
        }
    }

    fn parity_file(path: &str, modes: &[u8]) -> Option<Vec<Cmp>> {
        let par = load_json(path)?;
        let s_end: HashMap<String, u64> = par["s_end"].as_object().map(|o| o.iter().map(|(k, v)| (k.clone(), v.as_u64().unwrap())).collect()).unwrap_or_default();
        let mut out = Vec::new();
        for &mode in modes {
            let mut c = Cmp::default();
            for tk in par["tokens"].as_array().unwrap() {
                let recs = run(tk, mode);
                compare(tk, &recs, s_end.get(tk["day"].as_str().unwrap_or("")).copied(), &mut c);
            }
            out.push(c);
        }
        Some(out)
    }

    fn report(name: &str, c: &Cmp) {
        eprintln!("presend parity [{name}]: {} tokens, {} study windows; arms missing {} extra {} (excluded by the study's tape rules {}), below-5% triggers armed {}, \
                   st/en/pct differences {} | rows {} armed {} (armed flag differences {}) | fills {} (fill differences {}, exit differences {}), study late hits matched {}, \
                   untradeable {} (no-fill differences {}) | aend differences {} slots differences {} | TOTAL MISMATCHES {}",
            c.tokens, c.windows, c.arm_missing, c.arm_extra, c.arm_excluded, c.below_armed, c.st_en_pct, c.rows, c.armed, c.armed_bad, c.fills, c.fill_bad, c.exit_bad,
            c.late, c.untradeable, c.nofill_bad, c.aend_bad, c.slots_bad, c.bad());
        for e in &c.ex { eprintln!("  e.g. {e}"); }
    }

    /// PARITY with the study (ps4 windows / fills / paths + ps5 per-token arming, chosen config T2|c, rows a / b / c): every
    /// study window of the parity tokens, fed trade by trade the way the engine does; all at once; and reordered + doubled
    #[test]
    fn presend_parity_with_study() {
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(cs) = parity_file(&format!("{root}/testdata/presend_parity.json"), &[0, 1, 2]) else { eprintln!("presend_parity.json missing: skipped"); return; };
        for (c, name) in cs.iter().zip(["engine order", "all at once", "reordered + doubled"]) {
            report(name, c);
            assert!(c.windows > 300 && c.fills > 100, "too few parity windows / fills");
            assert_eq!(c.bad(), 0, "the shadow differs from the study ({name})");
        }
    }

    /// the same check on a whole study day (ps12_parity.py --full R4 FILE; outside the repo): PRESEND_PARITY_FULL=FILE
    #[test]
    fn presend_parity_full_day() {
        let Ok(p) = std::env::var("PRESEND_PARITY_FULL") else { eprintln!("PRESEND_PARITY_FULL not set: skipped"); return; };
        let cs = parity_file(&p, &[0]).expect("PRESEND_PARITY_FULL: unreadable");
        report("full day, engine order", &cs[0]);
        assert_eq!(cs[0].bad(), 0, "the shadow differs from the study on the full day");
    }

    /// OFFLINE REPLAY for the evaluator test (ops/strategies/presend/ps11_shadow_eval.py): a parity-format file in, the
    /// engine's presend records out (JSONL), every token fed as the engine would. PRESEND_REPLAY_IN=FILE PRESEND_REPLAY_OUT=FILE
    #[test]
    fn presend_replay_to_jsonl() {
        let (Ok(pi), Ok(po)) = (std::env::var("PRESEND_REPLAY_IN"), std::env::var("PRESEND_REPLAY_OUT")) else { eprintln!("PRESEND_REPLAY_IN / _OUT not set: skipped"); return; };
        let par = load_json(&pi).expect("PRESEND_REPLAY_IN unreadable");
        // every token's trades in one stream, in chain order, as one engine sees the feed
        let mut sh = Shadow::new(Params::default());
        let mut all: Vec<In> = Vec::new();
        let mut creates: Vec<(u64, Pk, Pk, Pk)> = Vec::new();
        for tk in par["tokens"].as_array().unwrap() {
            let (mint, s0, cre, sgn, v) = ins(tk);
            creates.push((s0, mint, cre, sgn));
            all.extend(v);
        }
        all.sort_by_key(|t| (t.s, t.i, t.j));
        creates.sort_by_key(|c| c.0);
        let mut ci = 0;
        let mut f = std::io::BufWriter::new(std::fs::File::create(&po).unwrap());
        use std::io::Write as _;
        let t0 = std::time::Instant::now();
        let n = all.len();
        for t in all {
            while ci < creates.len() && creates[ci].0 <= t.s { let (s0, m, c, g) = creates[ci]; sh.create(m, s0, c, g, false, 0); ci += 1; }
            let s = t.s; sh.push(t); sh.advance(s);
            for e in sh.drain() { writeln!(f, "{}", e.rec).unwrap(); }
        }
        sh.complete();
        for e in sh.drain() { writeln!(f, "{}", e.rec).unwrap(); }
        eprintln!("presend replay: {n} trades in {:.2} s ({:.2} us per trade) -> {po}{}", t0.elapsed().as_secs_f64(), t0.elapsed().as_secs_f64() * 1e6 / n.max(1) as f64, sh.line());
    }

    /// the follower slack (sha256 of "dip" + signature into the study's table) and the fee rate match p1_build's float32 values;
    /// Python's floor division
    #[test]
    fn slack_fee_floordiv() {
        let root = env!("CARGO_MANIFEST_DIR");
        if let Some(par) = load_json(&format!("{root}/testdata/presend_parity.json")) {
            let v = par["slack_check"].as_array().unwrap();
            for x in v { assert_eq!(slack_of_sig(x[0].as_str().unwrap()), num(&x[1]), "slack of {}", x[0]); }
            assert!(v.len() >= 100);
        }
        assert_eq!(fee_rate(0, 0), 0.0125f32 as f64);
        assert_eq!(fee_rate(95, 30), 0.0125f32 as f64);
        assert_eq!(fee_rate(93, 5), 0.0098f32 as f64);
        for (a, b, want) in [(5.0, 2.0, 2.0), (-5.0, 2.0, -3.0), (424.0, 212.0, 2.0), (423.999, 212.0, 1.0), (97_706_000_000.5, 212.0, 460_877_358.0), (0.0, 212.0, 0.0)] {
            assert_eq!(py_floordiv(a, b), want, "{a} // {b}");
        }
    }

    /// a hand-made token: a whale buy arms the rows, a 20% dump fills them, the whale's own sell ends the window; a second
    /// whale while a row is open is blocked there; a wallet whose first >= 3% buy is < 5% never arms; history-less trades
    #[test]
    fn synthetic_token() {
        let mint = [7u8; 32]; let cre = [1u8; 32];
        let mut sh = Shadow::new(Params::default());
        sh.create(mint, 100, cre, cre, false, 0);
        let (mut v, mut t): (u64, u64) = (30_000_000_000, 1_073_000_000_000_000);
        let mut n = 0u32;
        let mut tr = |s: u64, user: u8, buy: bool, amount: u64, sh: &mut Shadow| {
            // buy: amount = SOL in; sell: amount = tokens
            let (sol, tok) = if buy { let tok = (t as u128 * amount as u128 / (v + amount) as u128) as u64; v += amount; t -= tok; (amount, tok) }
                             else { let sol = (v as u128 * amount as u128 / (t + amount) as u128) as u64; v -= sol; t += amount; (sol, amount) };
            n += 1;
            let mut sig = [0u8; 64]; sig[..4].copy_from_slice(&n.to_be_bytes());
            sh.push(In { mint, s, i: 10, j: 0, sig, user: [user; 32], buy, sol, tok, vsol: v, vtok: t, fbps: 95, cbps: 30, t_rx: 0, flags: 0 });
            sh.advance(s);
            tok
        };
        tr(100, 1, true, 1_000_000_000, &mut sh);                 // the creator's dev buy
        tr(103, 2, true, 1_100_000_000, &mut sh);                 // wallet 2: 3..5% on its first big buy: never a whale
        let wt = tr(106, 3, true, 2_500_000_000, &mut sh);        // wallet 3: whale (> 5%)
        tr(107, 4, true, 300_000_000, &mut sh);
        tr(109, 3, false, wt, &mut sh);                           // the whale dumps everything: a ~-20% drop -> fills; window ends 30 ms later
        tr(112, 5, true, 400_000_000, &mut sh);
        tr(114, 6, true, 300_000_000, &mut sh);
        tr(300, 6, true, 10_000_000, &mut sh);
        sh.complete();
        let recs: Vec<Value> = sh.drain().into_iter().map(|e| e.rec).collect();
        let ev = |k: &str| recs.iter().filter(|r| r["ev"] == k).count();
        assert_eq!(ev("presend_arm"), 1, "{recs:#?}");
        assert_eq!(ev("presend_fill"), 3);
        assert_eq!(ev("presend_exit"), 3);
        let d = recs.iter().find(|r| r["ev"] == "presend_disarm").unwrap();
        assert_eq!(d["why"], "filled");
        assert!(d["whale_sell"].is_object());
        assert!(recs.iter().filter(|r| r["ev"] == "presend_fill").all(|r| r["seller_is_whale"] == true));
        assert_eq!(sh.st.below_pct, 1);
        // a token we never saw created: no arm, one skip record for a whale-sized single buy
        let mut sig = [9u8; 64]; sig[0] = 1;
        sh.push(In { mint: [8; 32], s: 400, i: 1, j: 0, sig, user: [3; 32], buy: true, sol: 3_000_000_000, tok: 90_000_000_000_000, vsol: 33_000_000_000, vtok: 975_000_000_000_000,
                     fbps: 95, cbps: 30, t_rx: 0, flags: 0 });
        sh.complete();
        let r2: Vec<Value> = sh.drain().into_iter().map(|e| e.rec).collect();
        assert_eq!(r2.len(), 1);
        assert_eq!(r2[0]["ev"], "presend_skip");
        assert_eq!(sh.st.no_hist_mints, 1);
    }
}

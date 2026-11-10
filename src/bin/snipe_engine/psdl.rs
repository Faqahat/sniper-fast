// =====================================================================================================================
// dip41 WHALE FAST-DUMP LEDGER + two arming variants on it, WIDE-DUMPER and QF2 (owner 11-06 "do it": built LOCAL, default OFF).
// Research (/home/it/sniper-4ggj2: x15_ledger.py / ledger.py / p2_4g.py "R1_WL1R1"; memory w4gg.md): the rival dip bot 4ggJqUDD arms by
// WHALE IDENTITY. Its selection = the whale's fast-dump record: the share of the wallet's earlier >= 3% buys it dumped (>= 30% of that buy's
// tokens sold within 20 slots), counted only once 25 slots have passed (AUC 0.85 on its arming). Calibrated PAPER2 on held-out days: R1 + the
// WIDE-DUMPER tier (also arm 3..6% whales with >= 3 earlier >= 3% buys and >= 80% of them dumped) +8.72 vs R1 +6.34 SOL at 0.69 (8/8 reps);
// arming every 3..6% whale without the ledger loses (-5.6). The DL7 study converged on a sibling rule (QF2, below): both run side by side.
//
//  LEDGER (--presend-live-dumper-ledger on): every BUY of >= 3% of supply (one trade's tokens >= 3e13 raw: x12_feat's `tok >= 3e13`) by ANY
//   wallet on ANY pump.fun token of the executed feed (not a mayhem curve: vtok > 1.0731e15; not in the token's create slot when the
//   detector saw the create) is kept as (wallet, mint, slot, tokens). The wallet's own SELLS of that mint after it (arrival order) are
//   followed; once the feed's slot reaches buy + 25 it is RESOLVED with TWO flags (one ledger, both variants' scores):
//     d = "dumped": it sold >= FRAC of the buy's tokens within WIN slots (WIDE-DUMPER's WIN:FRAC, default 20:0.3 = x12_feat sell30 <= 20)
//     q = "quick":  it sold (any amount) within QWIN slots (QF2's WIN, default 10)
//   Per wallet: its last DL_KEEP (50) resolved buys -> n, d, q (ledger.look(lag=25): only buys >= 25 slots before the lookup count; the
//   research kept every buy since 10-30 -- the 50 cap bounds memory, the owner's spec). A wallet with no resolved buy for 48 h is forgotten.
//   --presend-live-dumper-state PATH    preloaded at the start (a missing file: empty ledger), saved every ~10 min and at the run's end
//                                       (atomic: PATH.new + rename). FORMAT (ops/prod/dumper_seed.py writes the same):
//     {"v": 1, "kind": "dumper_ledger", "t": <ns: the clock of the newest trade seen>, "slot": <its slot>,
//      "rule": {"min_tok": 3e13, "dump_frac": 0.3, "dump_slots": 20, "quick_slots": 10, "resolve_slots": 25, "keep": 50, "idle_h": 48},
//      "w": {"<wallet base58>": {"t": <ns: its newest resolution>, "b": [[slot, d 0|1, q 0|1], ...oldest first]}}}
//   Load: refused (an EMPTY ledger, a warning) when its dump_frac / dump_slots / quick_slots differ from the flags'; wallets idle > 48 h
//   before "t" dropped; each list cut to its newest 50; unresolved buys are not saved (a restart loses <= 25 slots).
//  The TRIGGER both variants see: a whale's FIRST >= 3% crossing (the T2 trigger's shape), at age >= 1 slot (never the create slot) and >=
//   --presend-live-min-age-slots. Below --presend-whale-pct it is the detector's Below (a wide candidate); at / above it, a T2 trigger.
//  WIDE-DUMPER (on with the ledger): --presend-live-wide-dumper N:SCORE[:WIN:FRAC] (default 3:0.8:20:0.3): a Below whose whale has n >= N and
//   d / n >= SCORE; ONE window per token. Records presend_live_widedumper; the window's records "kind": "wide" + "widedumper": {n, d, score}.
//   --presend-live-wide-dumper-mode log|live (default log); control-file key "widedumper".
//  QF2 (DL7-style; on with --presend-live-qf2 N:SCORE[:QWIN], e.g. 5:0.3:10): a trigger (Below OR T2) whose whale has n >= N and q / n >= SCORE
//   and --presend-live-qf2-filters SOLMIN:SOLMAX:CURVEMIN:CURVEMAX:AGEMAX (default 2:8:36:70:300): the buy's SOL in [SOLMIN, SOLMAX], the
//   curve after it in [CURVEMIN, CURVEMAX] vSOL, the token age <= AGEMAX slots. A Below opens a window like WIDE-DUMPER (one per token; records
//   "kind": "qf2" + "qf2": {n, q, score}); a T2 trigger is only ANNOTATED (we arm T2 anyway): its presend_live_qf2 record ("t2": true, never
//   would_arm) and "qf2" on the T2 arm / skip. --presend-live-qf2-mode log|live (default log); control-file key "qf2".
//  BOTH: log = a record per trigger whose whale has n >= 1 (the values, the filters, pass / first / would_arm, the bot depth verdict), NO
//   window, nothing sent; live = the window opens through the T2 path itself (every live filter: create-slot / QUIET / blocklist / creator /
//   ledgers / skip2 / no-bot / bot-depth gate, the same limit / drop, the same exit), size --presend-live-wide-size-sol (default the T2 size;
//   <= --max-sol). Both live on one trigger: one window (the second is skipped "blocked_armed", its record says so). Every T2 arm / skip gets
//   "dumper": {n, d, score} (and "qf2" with QF2 on).
// Off (no --presend-live-dumper-ledger on): nothing of it runs; every record and decision dip39's.
// =====================================================================================================================
use super::*;

/// the wide band's floor (% of supply; the detector's first >= 3% crossing)
pub const WIDE_MIN_PCT: f64 = 3.0;
/// a ledger buy: one trade's tokens >= 3% of the 1e15 raw supply
pub const DL_MIN_TOK: u64 = 30_000_000_000_000;
/// a buy is resolved (and counts) once the feed's slot reaches buy + DL_RESOLVE_SLOTS (ledger.look lag 25); every window <= DL_WIN_MAX
pub const DL_RESOLVE_SLOTS: u64 = 25;
pub const DL_WIN_MAX: u64 = 20;
/// resolved buys kept per wallet (newest)
pub const DL_KEEP: usize = 50;
/// a wallet with no resolution for this long is forgotten (ns)
pub const DL_IDLE_NS: u64 = 48 * 3600 * 1_000_000_000;
/// a mayhem curve (x12_feat: vtok max > 1.0731e15): never a ledger buy
pub const DL_MAYHEM_VTOK: u64 = 1_073_100_000_000_000;
/// unresolved buys kept at most (a guard: ~25 slots of >= 3% buys is a few dozen)
const DL_PENDING_CAP: usize = 100_000;
/// the wallets' idle prune and the one-window-per-token books' prune, every this many slots
const DL_PRUNE_SLOTS: u64 = 1500;
/// a token's window mark is kept this many slots (~6 h: the detector forgets an idle token then)
const WD_USED_SLOTS: u64 = 6 * 3600 * 1000 / 400;
/// live windows' ledger values kept (window id -> values) at most
const WD_WINS_CAP: usize = 4096;

/// the ledger's per-buy flags: d = sold >= frac_pm / 1000 of the buy within `win` slots; q = any sell within `qwin` slots
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rule { pub win: u64, pub frac_pm: u64, pub qwin: u64 }
impl Default for Rule { fn default() -> Rule { Rule { win: 20, frac_pm: 300, qwin: 10 } } }
impl Rule {
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"min_tok": DL_MIN_TOK, "dump_frac": self.frac_pm as f64 / 1000.0, "dump_slots": self.win, "quick_slots": self.qwin,
            "resolve_slots": DL_RESOLVE_SLOTS, "keep": DL_KEEP, "idle_h": DL_IDLE_NS / 3_600_000_000_000})
    }
    /// a state file's rule is this one
    fn same(&self, j: &serde_json::Value) -> bool {
        j["dump_slots"].as_u64() == Some(self.win) && j["quick_slots"].as_u64() == Some(self.qwin)
            && j["dump_frac"].as_f64().is_some_and(|f| (f * 1000.0).round() as u64 == self.frac_pm)
    }
}

/// the two variants
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Kind { Wide, Qf2 }
impl Kind {
    /// the records' "kind" and the control-file key's / the value field's name
    pub fn key(&self) -> &'static str { match self { Kind::Wide => "wide", Kind::Qf2 => "qf2" } }
    pub fn field(&self) -> &'static str { match self { Kind::Wide => "widedumper", Kind::Qf2 => "qf2" } }
    pub fn ev(&self) -> &'static str { match self { Kind::Wide => "presend_live_widedumper", Kind::Qf2 => "presend_live_qf2" } }
    pub fn name(&self) -> &'static str { match self { Kind::Wide => "WIDE-DUMPER", Kind::Qf2 => "QF2" } }
}

/// --presend-live-wide-dumper N:SCORE[:WIN:FRAC]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct WdCfg { pub n: u32, pub score: f64, pub win: u64, pub frac: f64 }
impl Default for WdCfg { fn default() -> WdCfg { WdCfg { n: 3, score: 0.8, win: 20, frac: 0.3 } } }

/// --presend-live-qf2 N:SCORE[:WIN]
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct QfCfg { pub n: u32, pub score: f64, pub win: u64 }

/// --presend-live-qf2-filters SOLMIN:SOLMAX:CURVEMIN:CURVEMAX:AGEMAX (SOL, SOL, vSOL, vSOL, slots)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct QfFilt { pub sol: (f64, f64), pub curve: (f64, f64), pub age_max: u64 }
impl Default for QfFilt { fn default() -> QfFilt { QfFilt { sol: (2.0, 8.0), curve: (36.0, 70.0), age_max: 300 } } }
impl QfFilt {
    pub fn spec(&self) -> String { format!("{}:{}:{}:{}:{}", self.sol.0, self.sol.1, self.curve.0, self.curve.1, self.age_max) }
    /// (sol ok, curve ok, age ok) of a trigger: its SOL in, the curve after it (lamports), its age
    pub fn check(&self, sol: u64, vsol: u64, age: u64) -> (bool, bool, bool) {
        let (s, v) = (sol as f64 / 1e9, vsol as f64 / 1e9);
        (s >= self.sol.0 && s <= self.sol.1, v >= self.curve.0 && v <= self.curve.1, age <= self.age_max)
    }
}

/// the rule on a whale's (n, hits): n >= N and hits / n >= SCORE
pub fn pass(n_min: u32, score: f64, n: u32, hits: u32) -> bool { n >= n_min && n > 0 && hits as f64 >= score * n as f64 - 1e-9 }

fn nparse(x: &str) -> Option<u32> { x.trim().parse().ok().filter(|n| (1..=DL_KEEP as u32).contains(n)) }
fn sparse(x: &str) -> Option<f64> { x.trim().parse().ok().filter(|s: &f64| s.is_finite() && (0.0..=1.0).contains(s)) }
fn wparse(x: &str) -> Option<u64> { x.trim().parse().ok().filter(|w| (1..=DL_WIN_MAX).contains(w)) }

/// N:SCORE[:WIN:FRAC] (N 1..=50, SCORE in [0, 1], WIN 1..=20 slots, FRAC in (0, 1])
pub fn wd_parse(s: &str) -> Result<WdCfg> {
    let bad = || anyhow::anyhow!("--presend-live-wide-dumper N:SCORE[:WIN:FRAC] (N = resolved >= 3% buys 1..{DL_KEEP}, SCORE = dumped share 0..1, WIN 1..{DL_WIN_MAX} slots, \
        FRAC = share of the buy sold (0, 1]), e.g. 3:0.8 or 3:0.8:20:0.3; got '{s}'");
    let v: Vec<&str> = s.split(':').collect();
    if v.len() != 2 && v.len() != 4 { return Err(bad()); }
    let mut c = WdCfg { n: nparse(v[0]).ok_or_else(bad)?, score: sparse(v[1]).ok_or_else(bad)?, ..Default::default() };
    if v.len() == 4 {
        c.win = wparse(v[2]).ok_or_else(bad)?;
        c.frac = v[3].trim().parse().ok().filter(|f: &f64| f.is_finite() && *f > 0.0 && *f <= 1.0).ok_or_else(bad)?;
    }
    Ok(c)
}

/// N:SCORE[:WIN] (WIN default 10)
pub fn qf_parse(s: &str) -> Result<QfCfg> {
    let bad = || anyhow::anyhow!("--presend-live-qf2 N:SCORE[:WIN] (N = resolved >= 3% buys 1..{DL_KEEP}, SCORE = share sold within WIN slots 0..1, WIN 1..{DL_WIN_MAX}), \
        e.g. 5:0.3:10; got '{s}'");
    let v: Vec<&str> = s.split(':').collect();
    if v.len() != 2 && v.len() != 3 { return Err(bad()); }
    Ok(QfCfg { n: nparse(v[0]).ok_or_else(bad)?, score: sparse(v[1]).ok_or_else(bad)?, win: if v.len() == 3 { wparse(v[2]).ok_or_else(bad)? } else { 10 } })
}

/// SOLMIN:SOLMAX:CURVEMIN:CURVEMAX:AGEMAX
pub fn qf_filt_parse(s: &str) -> Result<QfFilt> {
    let bad = || anyhow::anyhow!("--presend-live-qf2-filters SOLMIN:SOLMAX:CURVEMIN:CURVEMAX:AGEMAX (SOL, SOL, vSOL, vSOL, slots; min <= max), e.g. 2:8:36:70:300; got '{s}'");
    let v: Vec<&str> = s.split(':').map(|x| x.trim()).collect();
    if v.len() != 5 { return Err(bad()); }
    let f: Vec<f64> = v[..4].iter().map(|x| x.parse::<f64>().ok().filter(|y| y.is_finite() && *y >= 0.0)).collect::<Option<Vec<f64>>>().ok_or_else(bad)?;
    let age: u64 = v[4].parse().map_err(|_| bad())?;
    if f[0] > f[1] || f[2] > f[3] { return Err(bad()); }
    Ok(QfFilt { sol: (f[0], f[1]), curve: (f[2], f[3]), age_max: age })
}

/// a mode flag's value: log|live -> live
pub fn mode_parse(flag: &str, s: &str) -> Result<bool> {
    match s { "log" => Ok(false), "live" => Ok(true), x => bail!("{flag} {x}: log | live") }
}
pub fn mode_str(live: bool) -> &'static str { if live { "live" } else { "log" } }

/// the control file's "widedumper" / "qf2" key: Some(live) / None (absent)
pub fn ctl_parse_key(b: &[u8], k: &str) -> std::result::Result<Option<bool>, String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    match v[k].as_str() { None if v.get(k).is_none_or(|x| x.is_null()) => Ok(None), Some("live") => Ok(Some(true)), Some("log") => Ok(Some(false)),
        _ => Err(format!("{k}: '{}' (live | log)", v[k])) }
}
pub fn ctl_parse_wd(b: &[u8]) -> std::result::Result<Option<bool>, String> { ctl_parse_key(b, "widedumper") }
pub fn ctl_parse_qf(b: &[u8]) -> std::result::Result<Option<bool>, String> { ctl_parse_key(b, "qf2") }

/// a whale's ledger values at a lookup: resolved buys, dumped, quick
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct WdV { pub n: u32, pub d: u32, pub q: u32 }
impl WdV {
    pub fn hits(&self, k: Kind) -> u32 { match k { Kind::Wide => self.d, Kind::Qf2 => self.q } }
    pub fn score(&self, k: Kind) -> Option<f64> { (self.n > 0).then(|| self.hits(k) as f64 / self.n as f64) }
    /// the variant's values: wide {n, d, score}, qf2 {n, q, score}
    pub fn json(&self, k: Kind) -> serde_json::Value {
        let sc = self.score(k).map(|x| (x * 1e4).round() / 1e4);
        match k { Kind::Wide => serde_json::json!({"n": self.n, "d": self.d, "score": sc}), Kind::Qf2 => serde_json::json!({"n": self.n, "q": self.q, "score": sc}) }
    }
}

/// an unresolved buy
#[derive(Clone, Copy, Debug)]
struct PBuy { s: u64, tok: u64, sold: u64, q: bool }

/// a wallet's resolved buys (slot, d, q), oldest first, and the clock of its newest resolution
#[derive(Clone, Debug, Default, PartialEq)]
pub struct WHist { pub b: VecDeque<(u64, bool, bool)>, pub t: u64 }
impl WHist {
    pub fn v(&self) -> WdV { WdV { n: self.b.len() as u32, d: self.b.iter().filter(|x| x.1).count() as u32, q: self.b.iter().filter(|x| x.2).count() as u32 } }
    fn push(&mut self, slot: u64, d: bool, q: bool, t: u64) {
        self.b.push_back((slot, d, q));
        while self.b.len() > DL_KEEP { self.b.pop_front(); }
        self.t = self.t.max(t);
    }
}

/// THE LEDGER (pure but for its clock: unit-tested)
#[derive(Debug, Default)]
pub struct Ledger {
    pub rule: Rule,
    pend: FxHashMap<(Pk, Pk), Vec<PBuy>>,
    order: VecDeque<(u64, Pk, Pk)>,
    pub hist: FxHashMap<Pk, WHist>,
    /// the feed's clock (ns) and slot
    pub now_t: u64, pub now_slot: u64,
    pruned: u64,
    /// counts this run: big buys taken, resolved, of them dumped / quick, wallets forgotten (idle), pending dropped (cap)
    pub buys: u64, pub resolved: u64, pub dumped: u64, pub quick: u64, pub forgot: u64, pub dropped: u64,
}

impl Ledger {
    pub fn new(rule: Rule) -> Ledger { Ledger { rule, ..Default::default() } }
    /// one executed-feed trade (arrival order). `create_slot`: the token's create slot when the detector saw it
    #[allow(clippy::too_many_arguments)]
    pub fn trade(&mut self, mint: Pk, user: Pk, buy: bool, tok: u64, vtok: u64, slot: u64, t: u64, create_slot: Option<u64>) {
        if t > self.now_t { self.now_t = t; }
        if slot > self.now_slot { self.now_slot = slot; self.resolve(); }
        if !buy {
            let r = self.rule;
            if let Some(v) = self.pend.get_mut(&(user, mint)) {
                for b in v.iter_mut() {
                    if slot < b.s { continue; }
                    if slot <= b.s + r.win { b.sold = b.sold.saturating_add(tok); }
                    if slot <= b.s + r.qwin && tok > 0 { b.q = true; }
                }
            }
            return;
        }
        if tok < DL_MIN_TOK || vtok > DL_MAYHEM_VTOK || create_slot == Some(slot) { return; }
        if self.order.len() >= DL_PENDING_CAP { self.dropped += 1; return; }
        self.pend.entry((user, mint)).or_default().push(PBuy { s: slot, tok, sold: 0, q: false });
        self.order.push_back((slot, user, mint));
        self.buys += 1;
    }
    /// every buy whose slot + 25 <= the feed's slot now: resolved into its wallet's history
    pub fn resolve(&mut self) {
        while let Some(&(s, w, m)) = self.order.front() {
            if s + DL_RESOLVE_SLOTS > self.now_slot { break; }
            self.order.pop_front();
            let k = (w, m);
            let Some(v) = self.pend.get_mut(&k) else { continue };
            if v.is_empty() { self.pend.remove(&k); continue; }
            let b = v.remove(0);
            if v.is_empty() { self.pend.remove(&k); }
            let dumped = b.sold as u128 * 1000 >= b.tok as u128 * self.rule.frac_pm as u128;
            self.hist.entry(w).or_default().push(b.s, dumped, b.q, self.now_t);
            self.resolved += 1;
            if dumped { self.dumped += 1; }
            if b.q { self.quick += 1; }
        }
    }
    /// the whale's values now (its buys resolved by the feed's slot)
    pub fn look(&self, w: &Pk) -> WdV { self.hist.get(w).map_or_else(WdV::default, |h| h.v()) }
    pub fn pending(&self) -> usize { self.order.len() }
    /// wallets idle > 48 h forgotten (every ~1500 slots)
    pub fn prune(&mut self, slot_now: u64) {
        if slot_now < self.pruned + DL_PRUNE_SLOTS { return; }
        self.pruned = slot_now;
        let lo = self.now_t.saturating_sub(DL_IDLE_NS);
        let n0 = self.hist.len();
        self.hist.retain(|_, h| h.t >= lo);
        self.forgot += (n0 - self.hist.len()) as u64;
    }
    /// the state (FORMAT in the header)
    pub fn state_json(&self) -> serde_json::Value {
        let w: serde_json::Map<String, serde_json::Value> = self.hist.iter().map(|(k, h)| {
            (b58(k), serde_json::json!({"t": h.t, "b": h.b.iter().map(|(s, d, q)| serde_json::json!([s, *d as u8, *q as u8])).collect::<Vec<_>>()}))
        }).collect();
        serde_json::json!({"v": 1, "kind": "dumper_ledger", "t": self.now_t, "slot": self.now_slot, "rule": self.rule.json(), "w": w})
    }
    /// a saved state -> the wallets loaded (refused when its rule is not this ledger's; idle > 48 h before its "t" dropped; each cut to its
    /// newest 50). The feed's clock is not moved
    pub fn state_load(&mut self, b: &[u8]) -> Result<usize> {
        let j: serde_json::Value = serde_json::from_slice(b).context("parse")?;
        if j["v"].as_u64() != Some(1) { bail!("not a v1 dumper ledger state"); }
        if !self.rule.same(&j["rule"]) { bail!("its rule {} is not the flags' {} (rebuild it: dumper_seed.py --dump-slots / --dump-frac / --quick-slots)", j["rule"], self.rule.json()); }
        let t = j["t"].as_u64().context("no \"t\"")?;
        let lo = t.saturating_sub(DL_IDLE_NS);
        let mut m: FxHashMap<Pk, WHist> = FxHashMap::default();
        for (w, v) in j["w"].as_object().context("no \"w\" object")? {
            let Some(pk) = bs58::decode(w).into_vec().ok().and_then(|x| <[u8; 32]>::try_from(x).ok()) else { bail!("bad wallet {w}") };
            let wt = v["t"].as_u64().with_context(|| format!("{w}: no \"t\""))?;
            if wt < lo { continue; }
            let mut h = WHist { b: VecDeque::new(), t: wt };
            for e in v["b"].as_array().with_context(|| format!("{w}: no \"b\""))? {
                let (Some(s), Some(d), Some(q)) = (e[0].as_u64(), e[1].as_u64(), e[2].as_u64()) else { bail!("{w}: bad entry {e} (want [slot, d, q])") };
                h.b.push_back((s, d != 0, q != 0));
            }
            while h.b.len() > DL_KEEP { h.b.pop_front(); }
            if !h.b.is_empty() { m.insert(pk, h); }
        }
        let n = m.len();
        self.hist = m;
        Ok(n)
    }
}

/// one variant's state
#[derive(Debug)]
pub struct Var {
    pub kind: Kind,
    pub n: u32, pub score: f64,
    /// live mode (the flag; the control file flips it)
    pub live: bool,
    /// one window per token: mint -> the slot of its window (would-arm)
    used: FxHashMap<Pk, u64>,
    /// counts: candidates, records written (n >= 1), would-arm, armed (live), withheld (live: a live filter skipped the would-arm window), a
    /// later whale on a token already used, T2 triggers annotated (QF2), of them passing
    pub cands: u64, pub recs: u64, pub would: u64, pub armed: u64, pub withheld: u64, pub dup: u64, pub t2: u64, pub t2_pass: u64,
    pub skips: FxHashMap<&'static str, u64>,
}
impl Var {
    fn new(kind: Kind, n: u32, score: f64, live: bool) -> Var {
        Var { kind, n, score, live, used: FxHashMap::default(), cands: 0, recs: 0, would: 0, armed: 0, withheld: 0, dup: 0, t2: 0, t2_pass: 0, skips: FxHashMap::default() }
    }
    pub fn pass(&self, v: &WdV) -> bool { pass(self.n, self.score, v.n, v.hits(self.kind)) }
    pub fn spec(&self) -> String { format!("{}:{}", self.n, self.score) }
    fn json(&self) -> serde_json::Value {
        let skips: serde_json::Map<String, serde_json::Value> = self.skips.iter().map(|(k, v)| (k.to_string(), (*v).into())).collect();
        serde_json::json!({"mode": mode_str(self.live), "n": self.n, "score": self.score, "cands": self.cands, "recs": self.recs, "would": self.would, "armed": self.armed,
            "withheld": self.withheld, "dup": self.dup, "t2": self.t2, "t2_pass": self.t2_pass, "skips": skips, "tokens_used": self.used.len()})
    }
}

/// the probe's side: the ledger, the variants (WIDE-DUMPER always with the ledger, QF2 with its flag), the windows' size, the live windows
#[derive(Debug)]
pub struct Wd {
    pub led: Ledger,
    pub wide: Var,
    pub qf: Option<Var>,
    pub filt: QfFilt,
    /// the windows' size (lamports)
    pub size: u64,
    pub state: Option<String>,
    saved: u64,
    /// the start's state load: Some(wallets) / the error
    pub loaded: Option<usize>, pub err: Option<String>,
    used_pruned: u64,
    /// live windows -> (variant, the whale's ledger values at the arm)
    pub wins: FxHashMap<u64, (Kind, WdV)>,
}

/// a trigger's view by one variant
#[derive(Clone, Copy, Debug)]
pub struct Eval { pub kind: Kind, pub v: WdV, pub pass: bool, pub filt: Option<(bool, bool, bool)>, pub first: bool, pub would: bool }

impl Wd {
    pub fn open(wd: WdCfg, wd_live: bool, qf: Option<QfCfg>, filt: QfFilt, qf_live: bool, size: u64, state: Option<&str>) -> Wd {
        let rule = Rule { win: wd.win, frac_pm: (wd.frac * 1000.0).round() as u64, qwin: qf.map_or(10, |q| q.win) };
        let mut w = Wd { led: Ledger::new(rule), wide: Var::new(Kind::Wide, wd.n, wd.score, wd_live), qf: qf.map(|q| Var::new(Kind::Qf2, q.n, q.score, qf_live)), filt, size,
            state: state.map(|s| s.to_string()), saved: 0, loaded: None, err: None, used_pruned: 0, wins: FxHashMap::default() };
        if let Some(p) = state {
            match std::fs::read(p) {
                Ok(x) => match w.led.state_load(&x) { Ok(n) => w.loaded = Some(n), Err(e) => w.err = Some(format!("state {p}: {e:#}")) },
                Err(e) if e.kind() == std::io::ErrorKind::NotFound => w.loaded = Some(0),
                Err(e) => w.err = Some(format!("state {p}: {e}")),
            }
        }
        w
    }
    pub fn var(&self, k: Kind) -> Option<&Var> { match k { Kind::Wide => Some(&self.wide), Kind::Qf2 => self.qf.as_ref() } }
    pub fn var_mut(&mut self, k: Kind) -> Option<&mut Var> { match k { Kind::Wide => Some(&mut self.wide), Kind::Qf2 => self.qf.as_mut() } }
    /// a trigger by one variant (`t2`: a T2 trigger: QF2 annotates only); would-arm marks its token used and counts
    pub fn eval(&mut self, k: Kind, mint: &Pk, whale: &Pk, t2: bool, sol: u64, vsol: u64, age: u64, slot: u64) -> Option<Eval> {
        let v = self.led.look(whale);
        let filt = (k == Kind::Qf2).then(|| self.filt.check(sol, vsol, age));
        let var = self.var_mut(k)?;
        let pass = var.pass(&v);
        let fok = filt.is_none_or(|f| f.0 && f.1 && f.2);
        let first = !var.used.contains_key(mint);
        let would = !t2 && pass && fok && first;
        if t2 { var.t2 += 1; if pass && fok { var.t2_pass += 1; } } else { var.cands += 1; }
        if !t2 && pass && fok && !first { var.dup += 1; }
        if would { var.used.insert(*mint, slot); var.would += 1; }
        if v.n > 0 { var.recs += 1; }
        Some(Eval { kind: k, v, pass, filt, first, would })
    }
    fn prune(&mut self, slot_now: u64) {
        self.led.prune(slot_now);
        if slot_now >= self.used_pruned + DL_PRUNE_SLOTS {
            self.used_pruned = slot_now;
            let lo = slot_now.saturating_sub(WD_USED_SLOTS);
            self.wide.used.retain(|_, s| *s >= lo);
            if let Some(q) = self.qf.as_mut() { q.used.retain(|_, s| *s >= lo); }
        }
        if self.wins.len() > WD_WINS_CAP {
            let mut ids: Vec<u64> = self.wins.keys().copied().collect();
            ids.sort_unstable();
            let cut = ids[ids.len() - WD_WINS_CAP / 2];
            self.wins.retain(|k, _| *k >= cut);
        }
    }
    /// save the state (a thread unless `sync`; None without the file)
    pub fn save(&self, sync: bool) -> Option<std::result::Result<usize, String>> {
        let p = self.state.clone()?;
        let j = self.led.state_json();
        let n = self.led.hist.len();
        let w = move || -> std::result::Result<usize, String> {
            let tmp = format!("{p}.new");
            std::fs::write(&tmp, j.to_string()).map_err(|e| format!("write {tmp}: {e}"))?;
            std::fs::rename(&tmp, &p).map_err(|e| format!("rename {tmp}: {e}"))?;
            Ok(n)
        };
        if sync { return Some(w()); }
        std::thread::spawn(move || { if let Err(e) = w() { eprintln!("DIP PRESEND LIVE DUMPER LEDGER: state NOT saved: {e}"); } });
        None
    }
    /// the wallets passing a variant's whale rule now
    pub fn passing(&self, k: Kind) -> usize { self.var(k).map_or(0, |x| self.led.hist.values().filter(|h| x.pass(&h.v())).count()) }
    pub fn sizes(&self) -> serde_json::Value {
        let mut j = serde_json::json!({"wallets": self.led.hist.len(), "pending": self.led.pending(), "buys": self.led.buys, "resolved": self.led.resolved, "dumped": self.led.dumped,
            "quick": self.led.quick, "forgot": self.led.forgot, "dropped": self.led.dropped, "pass": self.passing(Kind::Wide)});
        if self.qf.is_some() { j["pass_qf2"] = self.passing(Kind::Qf2).into(); }
        j
    }
}

impl PsLive {
    /// the executed feed's trade into the ledger (before the detector takes it: a trigger's lookup sees the buys resolved by its slot)
    #[inline]
    pub(super) fn wd_trade(&mut self, e: &arbx::dip::TradeEvent, slot: u64, t: u64) {
        let cs = self.det.create_slot(&e.mint);
        if let Some(w) = self.wd.as_mut() { w.led.trade(e.mint, e.user, e.buy, e.tok, e.vtok, slot, t, cs); }
    }
    /// a live window's variant and ledger values (None: not one of the tier's windows / it off)
    pub(super) fn wd_win(&self, w: u64) -> Option<(Kind, WdV)> { self.wd.as_ref().and_then(|d| d.wins.get(&w).copied()) }
    /// a T2 arm / skip record: the whale's dumper values ("dumper") and, with QF2 on, its QF2 view ("qf2"; nothing with the ledger off)
    pub(super) fn wd_t2_fields(&self, r: &mut serde_json::Value, whale: &Pk, t: &pl::Trade, age: u64) {
        let Some(w) = self.wd.as_ref() else { return };
        let v = w.led.look(whale);
        r["dumper"] = v.json(Kind::Wide);
        if let Some(q) = w.qf.as_ref() {
            let f = w.filt.check(t.sol, t.vsol, age);
            let mut j = v.json(Kind::Qf2);
            j["pass"] = q.pass(&v).into();
            j["filt"] = (f.0 && f.1 && f.2).into();
            r["qf2"] = j;
        }
    }
    /// one variant's record of a trigger (the caller writes it only for a whale with n >= 1)
    fn wd_rec(&self, e: &Eval, t: &pl::Trade, whale: &Pk, pct: f64, bal: i64, age: u64, t2: bool) -> serde_json::Value {
        let w = self.wd.as_ref().expect("on");
        let live = w.var(e.kind).is_some_and(|x| x.live);
        let mut r = serde_json::json!({"ev": e.kind.ev(), "mint": b58(&t.mint), "whale": b58(whale), "pct": pct, "bal": bal, "age_slots": age,
            "sig": bs58::encode(&t.sig).into_string(), "slot": t.s, "idx": t.i, "j": t.j, "t": t.t_rx, "sol": t.sol, "tok": t.tok, "vsol": t.vsol, "vtok": t.vtok,
            "n": e.v.n, "score": e.v.json(e.kind)["score"], "pass": e.pass, "first": e.first, "would_arm": e.would, "mode": mode_str(live), "size": w.size});
        match e.kind { Kind::Wide => { r["d"] = e.v.d.into(); } Kind::Qf2 => { r["q"] = e.v.q.into(); } }
        if let Some((s, c, a)) = e.filt { r["filt"] = serde_json::json!({"sol": s, "curve": c, "age": a}); }
        if t2 { r["t2"] = true.into(); }
        if let Some(j) = self.bd_json(&t.mint, t.s) { r["botdepth"] = j; }
        r
    }
    /// the detector's Below (a 3..whale_pct first crossing): both variants (nothing with the ledger off); a live would-arm opens a window
    #[allow(clippy::too_many_arguments)]
    pub(super) fn wd_below(&mut self, t: &pl::Trade, whale: Pk, pct: f64, bal: i64, age_slots: u64, launch_of: &impl Fn(&Pk) -> Option<Launch>, reactive_open: &dyn Fn(&Pk) -> bool) {
        let (min_age, top) = (self.cfg.min_age_slots, self.cfg.whale_pct);
        let Some(wd) = self.wd.as_mut() else { return };
        // the band and the trigger's age rules: never the create slot (whatever --presend-live-create-slot says), the T2 min age
        if !(pct >= WIDE_MIN_PCT && pct < top) || age_slots == 0 || age_slots < min_age { return; }
        let kinds: Vec<Kind> = if wd.qf.is_some() { vec![Kind::Wide, Kind::Qf2] } else { vec![Kind::Wide] };
        let mut arm: Vec<Eval> = Vec::new();
        for k in kinds {
            let Some(e) = self.wd.as_mut().and_then(|w| w.eval(k, &t.mint, &whale, false, t.sol, t.vsol, age_slots, t.s)) else { continue };
            if e.v.n == 0 { continue; }
            let r = self.wd_rec(&e, t, &whale, pct, bal, age_slots, false);
            self.rec(r);
            if !e.would { continue; }
            let live = self.wd.as_ref().and_then(|w| w.var(k)).is_some_and(|x| x.live);
            self.line(format!("  PRESEND LIVE {} {} {} whale {} {:.1}% ({:.2} SOL) age {age_slots} | {}/{} of its >= 3% buys {}{}", k.name(), if live { "ARM" } else { "WOULD ARM (log)" },
                b58(&t.mint), &b58(&whale)[..8], pct, t.sol as f64 / 1e9, e.v.hits(k), e.v.n, if k == Kind::Wide { "dumped" } else { "sold fast" }, if live { "" } else { ": nothing sent" }));
            if live { arm.push(e); }
        }
        for e in arm { self.trigger_kind(t, whale, pct, bal, age_slots, launch_of, reactive_open, Some((e.kind, e.v))); }
    }
    /// a T2 trigger: QF2's annotation record (nothing with QF2 off or an unknown whale)
    pub(super) fn wd_t2(&mut self, t: &pl::Trade, whale: Pk, pct: f64, bal: i64, age_slots: u64) {
        if self.wd.as_ref().is_none_or(|w| w.qf.is_none()) || age_slots == 0 { return; }
        let Some(e) = self.wd.as_mut().and_then(|w| w.eval(Kind::Qf2, &t.mint, &whale, true, t.sol, t.vsol, age_slots, t.s)) else { return };
        if e.v.n == 0 { return; }
        let r = self.wd_rec(&e, t, &whale, pct, bal, age_slots, true);
        self.rec(r);
    }
    /// a live window opened: its values kept for its fill / realized records
    pub(super) fn wd_armed(&mut self, id: u64, k: Kind, v: WdV) {
        if let Some(w) = self.wd.as_mut() { if let Some(x) = w.var_mut(k) { x.armed += 1; } w.wins.insert(id, (k, v)); }
    }
    /// a variant's would-arm window a live filter skipped
    pub(super) fn wd_skipped(&mut self, k: Kind, why: &'static str) {
        if let Some(x) = self.wd.as_mut().and_then(|w| w.var_mut(k)) { x.withheld += 1; *x.skips.entry(why).or_default() += 1; }
    }
    /// every tick: the prunes, the state every ~10 min
    pub(super) fn wd_tick(&mut self, slot_now: u64) {
        let Some(w) = self.wd.as_mut() else { return };
        w.prune(slot_now);
        if w.state.is_some() && slot_now >= w.saved + CR_SAVE_SLOTS {
            if w.saved > 0 { w.save(false); }
            w.saved = slot_now;
        }
    }
    /// the start's record and line (nothing with the ledger off)
    pub(super) fn wd_start(&mut self) {
        let Some(w) = self.wd.as_ref() else { return };
        let mut r = serde_json::json!({"ev": "presend_live_widedumper_config", "mode": mode_str(w.wide.live), "n": w.wide.n, "score": w.wide.score, "size": w.size,
            "band": [WIDE_MIN_PCT, self.cfg.whale_pct], "min_age_slots": self.cfg.min_age_slots.max(1), "state": w.state, "loaded": w.loaded, "err": w.err,
            "rule": w.led.rule.json(), "sizes": w.sizes(), "t": arbx::feeds::clock::now_ns()});
        if let Some(q) = &w.qf {
            r["qf2"] = serde_json::json!({"mode": mode_str(q.live), "n": q.n, "score": q.score, "win": w.led.rule.qwin, "filters": {"sol": [w.filt.sol.0, w.filt.sol.1],
                "curve": [w.filt.curve.0, w.filt.curve.1], "age_max": w.filt.age_max}});
        }
        if let Some(e) = &w.err { self.line(format!("  WARNING PRESEND LIVE DUMPER LEDGER: the state did NOT load ({e}): the ledger starts EMPTY (the variants arm nothing until whales have enough resolved buys)")); }
        self.rec(r);
    }
    /// the status line's part ("" with the ledger off)
    pub(super) fn wd_status(&self) -> String {
        let Some(w) = self.wd.as_ref() else { return String::new() };
        let v = &w.wide;
        let mut s = format!(" | WIDE DUMPER {} {}: ledger {} wallets ({} pass, {} pending), would-arm {}, armed {}, withheld {}",
            if v.live { "LIVE" } else { "LOG" }, v.spec(), w.led.hist.len(), w.passing(Kind::Wide), w.led.pending(), v.would, v.armed, v.withheld);
        if let Some(q) = &w.qf {
            s += &format!(" | QF2 {} {}: {} pass, would-arm {}, armed {}, withheld {}, T2 flagged {}/{}", if q.live { "LIVE" } else { "LOG" }, q.spec(), w.passing(Kind::Qf2),
                q.would, q.armed, q.withheld, q.t2_pass, q.t2);
        }
        s
    }
    /// run_end's part (None with the ledger off); the state saved
    pub(super) fn wd_finish(&mut self) -> Option<serde_json::Value> {
        let w = self.wd.as_ref()?;
        if let Some(r) = w.save(true) {
            let p = w.state.clone().unwrap_or_default();
            match r { Ok(n) => self.line(format!("  PRESEND LIVE DUMPER LEDGER: {n} wallets saved to {p}")),
                      Err(e) => self.line(format!("  PRESEND LIVE DUMPER LEDGER: state NOT saved to {p}: {e}")) }
        }
        let w = self.wd.as_ref()?;
        let mut j = w.wide.json();
        j["size"] = w.size.into();
        j["spec"] = w.wide.spec().into();
        j["ledger"] = w.sizes();
        j["rule"] = w.led.rule.json();
        j["state"] = w.state.clone().into();
        j["loaded"] = w.loaded.into();
        if let Some(q) = &w.qf { j["qf2"] = q.json(); }
        Some(j)
    }
}

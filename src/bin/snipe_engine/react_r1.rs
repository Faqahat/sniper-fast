// =====================================================================================================================
// dip40 REACTIVE PROBE LANE "R1" (owner 11-05: build + a live probe on FRA at 0.1 SOL; off unless --react-r1 log|live).
// The rule is the FROZEN policy "R1_hqadd" of the haqq7 study (/home/it/sniper-data/haqq7/frozen_rules.json, sha256 88e534bb...;
// features from /home/it/sniper-studies/sniper-haqq7/sim.py, mask from test.py, landing/exit from sim2.py), implemented exactly:
//   trigger : a processed pump SELL by another wallet (not us) on a token whose create we saw, sell >= 1% of supply AND >= 0.2 SOL
//             (sim.py MINPCT / MINSOL: the study's candidate set); decided right after seeing it, BEFORE it enters the book
//   pct     : 3 <= sell tokens / 1e13 < 6                (3..6% of the 1B supply, half-open as test.py)
//   age     : dump slot - create slot <= 30
//   prior   : >= 1 earlier sell >= 1% of supply (not ours) on this token in slots [s - 200, s], seen before the dump
//   dipb    : >= 2 distinct wallets (not us) that BOUGHT <= 2 slots after the latest sell >= 0.3 SOL of the token (any wallet), the
//             buy in [s - 200, s] and seen before the dump (sim.py dipflag / lastbig; dip39's organic dip-buyer counter, same window)
//   bots    : >= 5 distinct wallets of the bot list (dip39 list format: /root/dip/botdepth_wallets.json or the registry) that traded the
//             token (buy or sell, any size; not us) in slots [s - 100, s], seen before the dump
//   anchor  : the anchor wallet's (--react-r1-anchor, default haqq6qnV...) latest trade of the token in [s - 200, s] left it holding
//             > 1e10 raw tokens (sim.py hq_hold: net position from every trade seen)
// Buy: same slot only (the on-chain slot guard at the dump's slot: --buy-max-slot-delta 0), max price = --react-r1-max-price (1.10) x
// the post-dump curve price (sim.py LIM = sqrt(1.10) on the virtual SOL reserve, as a min-tokens-out), --react-r1-size-sol. Exit:
// sell when the feed reaches entry + --react-r1-exit-slots - 1 (lands at entry + N, as the regular time exit); TP / SL off unless given.
// One pick per token blocks it for exit + 1 slots (ev.py block). Not mayhem, not graduated, a create_v2 vanilla (or holder-reward
// with --dip-allow-holder) token; never on a mint we hold / have pending, nor one the pre-send lane holds or has armed.
// This file: the flags, the book, the features and the rule (pure, unit-tested in dip40_r1_tests.rs). The fire is dipmode.rs's.
// =====================================================================================================================
use super::*;
use rustc_hash::{FxHashMap, FxHashSet};
use std::sync::atomic::{AtomicI64, AtomicU64};

/// haqq6 (the study's anchor)
pub const ANCHOR_DEFAULT: &str = "haqq6qnVBCZt97amh9VUFZRFCkD6NJxoYifacCuqqqq";
/// 1% of the 1B x 1e6 supply (raw)
pub const PCT1: u64 = 10_000_000_000_000;
/// sim.py: the candidate set (sell >= 1% AND >= 0.2 SOL)
pub const MIN_SELL_SOL: u64 = 200_000_000;
/// the frozen R1 thresholds
pub const PCT_LO: u64 = 3 * PCT1;
pub const PCT_HI: u64 = 6 * PCT1;
pub const AGE_MAX: u64 = 30;
pub const PRIOR_MIN: u32 = 1;
pub const PRIOR_SLOTS: u64 = 200;
pub const DIPB_MIN: u32 = 2;
pub const DIPB_SLOTS: u64 = 200;
/// a "big" sell for the dip buyers (sim.py 3e8; dip39 psbd::ORG_SELL) and the buy's slots after it (psbd::ORG_DIP_SLOTS)
pub const DIP_SELL: u64 = 300_000_000;
pub const DIP_AFTER: i64 = 2;
pub const BOTS_MIN: u32 = 5;
pub const BOTS_SLOTS: u64 = 100;
pub const ANCHOR_SLOTS: u64 = 200;
/// sim.py hq_hold: the position after the anchor's last trade > 1e10 raw (0.001% of supply)
pub const ANCHOR_HOLD: i128 = 10_000_000_000;
/// a token stays in the book this many slots after its create (decisions at age 31..60 are logged as "age" fails); then dropped
pub const KEEP_SLOTS: u64 = 60;
/// pump's curve is complete (graduated) when the real token reserve is 0: virtual 1,073,000,000 - 793,100,000 tokens left
pub const GRAD_VTOK: u64 = 279_900_000_000_000;

pub const FLAGS: [&str; 10] = ["--react-r1", "--react-r1-size-sol", "--react-r1-exit-slots", "--react-r1-max-open", "--react-r1-max-per-min", "--react-r1-anchor",
    "--react-r1-bots", "--react-r1-tp", "--react-r1-sl", "--react-r1-max-price"];

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Mode { Log, Live }
impl Mode {
    pub fn as_str(&self) -> &'static str { match self { Mode::Log => "log", Mode::Live => "live" } }
}

/// the lane's configuration (--react-r1*)
#[derive(Clone, Debug)]
pub struct Cfg {
    pub mode: Mode,
    pub size: u64,
    pub exit_slots: u64,
    pub max_open: usize,
    pub max_per_min: usize,
    pub anchor: Pk,
    pub bots_path: String,
    pub bots: FxHashSet<Pk>,
    /// fractions; f64::INFINITY = off
    pub tp: f64, pub sl: f64,
    pub max_price: f64,
}

impl Cfg {
    pub fn from_args(live: bool, user: &Pk) -> Result<Option<Cfg>> { Cfg::from_argv(&std::env::args().collect::<Vec<_>>(), live, user, None) }

    /// the flags on a given command line (unit-tested; `bots` = the list file's bytes instead of reading it). The readers are named as the
    /// engine's own (arg_u64 / arg_f64) so check_flags types the numeric flags
    pub fn from_argv(argv: &[String], live: bool, user: &Pk, bots: Option<&[u8]>) -> Result<Option<Cfg>> {
        let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
        let arg = |f: &str| argv.iter().position(|x| x == f).and_then(|i| argv.get(i + 1)).cloned();
        let num = |f: &str, s: Option<String>| -> Result<Option<f64>> {
            match s { None => Ok(None), Some(s) => s.parse::<f64>().ok().filter(|x| x.is_finite()).map(Some).ok_or_else(|| anyhow::anyhow!("{f} {s}: not a number")) }
        };
        let arg_f64 = |f: &str, d: f64| -> Result<f64> { Ok(num(f, arg(f))?.unwrap_or(d)) };
        let arg_u64 = |f: &str, d: u64| -> Result<u64> {
            match arg(f) { None => Ok(d), Some(s) => s.parse::<u64>().map_err(|_| anyhow::anyhow!("{f} {s}: not a whole number")) }
        };
        let Some(m) = arg("--react-r1") else {
            if let Some(f) = FLAGS.iter().skip(1).find(|f| has(f)) { bail!("{f} needs --react-r1 log|live"); }
            return Ok(None);
        };
        let mode = match m.as_str() { "log" => Mode::Log, "live" => Mode::Live, x => bail!("--react-r1 {x}: log | live") };
        if mode == Mode::Live && !live { bail!("--react-r1 live sends real buys: it needs --live (--react-r1 log decides and logs only)"); }
        let size_sol = arg_f64("--react-r1-size-sol", 0.1)?;
        if !(0.05..=1.0).contains(&size_sol) { bail!("--react-r1-size-sol must be 0.05..1.0 SOL (got {size_sol})"); }
        let exit_slots = arg_u64("--react-r1-exit-slots", 4)?;
        if !(1..=25).contains(&exit_slots) { bail!("--react-r1-exit-slots must be 1..25 (the frozen R1 exit is 4)"); }
        let max_open = arg_u64("--react-r1-max-open", 1)?;
        if !(1..=3).contains(&max_open) { bail!("--react-r1-max-open must be 1..3"); }
        let max_per_min = arg_u64("--react-r1-max-per-min", 10)?;
        if !(1..=60).contains(&max_per_min) { bail!("--react-r1-max-per-min must be 1..60"); }
        let anchor_s = arg("--react-r1-anchor").unwrap_or_else(|| ANCHOR_DEFAULT.into());
        let anchor: Pk = bs58::decode(&anchor_s).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok())
            .ok_or_else(|| anyhow::anyhow!("--react-r1-anchor {anchor_s}: not a wallet address"))?;
        if anchor == *user { bail!("--react-r1-anchor is our own wallet"); }
        let Some(bots_path) = arg("--react-r1-bots") else { bail!("--react-r1 needs --react-r1-bots FILE (the bot list: a JSON array of wallets or the registry's {{\"wallets\": [..]}}, e.g. /root/dip/botdepth_wallets.json)") };
        if bots_path.starts_with("--") { bail!("--react-r1-bots needs a file"); }
        let set = match bots {
            Some(b) => pslive::psbd::list_parse(b, user),
            None => std::fs::read(&bots_path).map_err(|e| anyhow::anyhow!("read: {e}")).and_then(|b| pslive::psbd::list_parse(&b, user)),
        }.map_err(|e| anyhow::anyhow!("--react-r1-bots {bots_path}: {e:#}"))?;
        if (set.len() as u32) < BOTS_MIN { bail!("--react-r1-bots {bots_path}: {} wallet(s), fewer than the rule's {BOTS_MIN}", set.len()); }
        let frac = |f: &str, hi: f64| -> Result<f64> {
            let x = arg_f64(f, 0.0)?;
            if x == 0.0 { return Ok(f64::INFINITY); }
            if !(0.01..=hi).contains(&x) { bail!("{f} must be 0 (off) or 0.01..{hi}"); }
            Ok(x)
        };
        let tp = frac("--react-r1-tp", 1.0)?;
        let sl = frac("--react-r1-sl", 0.9)?;
        let max_price = arg_f64("--react-r1-max-price", 1.10)?;
        if !(1.0..=1.5).contains(&max_price) { bail!("--react-r1-max-price must be 1.0..1.5 (x the post-dump curve price; the frozen R1 is 1.10)"); }
        Ok(Some(Cfg { mode, size: (size_sol * 1e9).round() as u64, exit_slots, max_open: max_open as usize, max_per_min: max_per_min as usize, anchor, bots_path, bots: set,
            tp, sl, max_price }))
    }

    pub fn json(&self) -> serde_json::Value {
        let off = |x: f64| if x.is_finite() { serde_json::json!(x) } else { serde_json::Value::Null };
        serde_json::json!({"mode": self.mode.as_str(), "size": self.size, "exit_slots": self.exit_slots, "max_open": self.max_open, "max_per_min": self.max_per_min,
            "anchor": b58(&self.anchor), "bots": self.bots_path, "bots_n": self.bots.len(), "tp": off(self.tp), "sl": off(self.sl), "max_price": self.max_price,
            "rule": {"policy": "R1_hqadd", "pct": [3, 6], "min_sell_sol": MIN_SELL_SOL as f64 / 1e9, "age_max": AGE_MAX, "prior_min": PRIOR_MIN, "prior_slots": PRIOR_SLOTS,
                     "dipb_min": DIPB_MIN, "dipb_slots": DIPB_SLOTS, "dip_sell_sol": DIP_SELL as f64 / 1e9, "dip_after": DIP_AFTER, "bots_min": BOTS_MIN, "bots_slots": BOTS_SLOTS,
                     "anchor_slots": ANCHOR_SLOTS, "anchor_hold_raw": ANCHOR_HOLD as u64}})
    }

    pub fn banner(&self) -> String {
        let pct = |x: f64| if x.is_finite() { format!("{:.0}%", x * 100.0) } else { "off".into() };
        format!("DIP REACT R1 {} (dip40; frozen haqq7 R1_hqadd): a sell by another wallet of 3..6% of supply (>= 0.2 SOL) on a token <= {AGE_MAX} slots old, \
                 >= {PRIOR_MIN} earlier >= 1% sell in {PRIOR_SLOTS} slots, >= {DIPB_MIN} dip buyers ({DIPB_SLOTS} slots), >= {BOTS_MIN} listed bots in {BOTS_SLOTS} slots \
                 ({} in {}), anchor {} holding -> {} | buy {:.3} SOL same slot only, max price x{:.2} the post-dump price | exit {} slots, TP {} / SL {} | max open {}, \
                 max {}/min | records react_r1_decision / _fire / _fill / _exit / _realized",
            if self.mode == Mode::Live { "LIVE" } else { "LOG ONLY (decides, never sends)" }, self.bots.len(), self.bots_path, &b58(&self.anchor)[..8],
            if self.mode == Mode::Live { "FIRE" } else { "log" }, self.size as f64 / 1e9, self.max_price, self.exit_slots, pct(self.tp), pct(self.sl), self.max_open, self.max_per_min)
    }
}

/// one trade of a followed token, as seen (arrival order); `sol` is kept for the tests' prefix replays
#[derive(Clone, Copy, Debug)]
#[allow(dead_code)]
pub struct Tr { pub s: u64, pub i: u64, pub user: Pk, pub buy: bool, pub sol: u64, pub tok: u64, pub ours: bool, pub dip: bool }

/// one followed token: its create slot, its trades seen, the latest big sell's slot, the anchor's position
#[derive(Clone, Debug)]
pub struct MintBook {
    pub create_slot: u64, pub mayhem: bool,
    pub tr: Vec<Tr>,
    /// sim.py lastbig: the slot of the latest sell >= 0.3 SOL by ANY wallet (ours too), None = none yet
    pub lastbig: Option<u64>,
    /// the anchor's net position (raw tokens, every trade seen) and its latest trade slot
    pub anchor_pos: i128, pub anchor_last: Option<u64>,
    /// ev.py block: the latest rule pick's slot
    pub last_pick: Option<u64>,
}

/// a candidate's features (prefix only: the trades seen before the dump)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Feat {
    pub slot: u64, pub sol: u64, pub tok: u64, pub age: u64, pub prior1: u32, pub dipb: u32, pub bots: u32, pub anchor_hold: bool, pub anchor_pos: i128,
    pub anchor_last: Option<u64>, pub mayhem: bool,
}

impl Feat {
    pub fn pct(&self) -> f64 { self.tok as f64 / PCT1 as f64 }
    /// the frozen rule: the failing conditions in order (empty = pass)
    pub fn fails(&self) -> Vec<&'static str> {
        let mut v = Vec::new();
        if self.sol < MIN_SELL_SOL { v.push("sell_sol"); }
        if !(self.tok >= PCT_LO && self.tok < PCT_HI) { v.push("pct"); }
        if self.age > AGE_MAX { v.push("age"); }
        if self.prior1 < PRIOR_MIN { v.push("prior"); }
        if self.dipb < DIPB_MIN { v.push("dipb"); }
        if self.bots < BOTS_MIN { v.push("bots"); }
        if !self.anchor_hold { v.push("anchor"); }
        v
    }
    pub fn pass(&self) -> bool { self.fails().is_empty() }
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"sell_sol": self.sol, "sell_tok": self.tok, "pct": (self.pct() * 1e4).round() / 1e4, "age": self.age, "prior1": self.prior1, "dipb": self.dipb,
            "bots": self.bots, "anchor_hold": self.anchor_hold, "anchor_pos": self.anchor_pos.to_string(), "anchor_last": self.anchor_last, "mayhem": self.mayhem})
    }
}

/// the followed tokens (only those whose create was seen; each kept KEEP_SLOTS after its create)
#[derive(Debug)]
pub struct Book { pub m: FxHashMap<Pk, MintBook>, pub anchor: Pk, pub user: Pk, pruned: u64 }

impl Book {
    pub fn new(anchor: Pk, user: Pk) -> Book { Book { m: FxHashMap::default(), anchor, user, pruned: 0 } }

    /// a create seen (an existing entry is kept)
    pub fn create(&mut self, mint: Pk, slot: u64, mayhem: bool) {
        self.m.entry(mint).or_insert(MintBook { create_slot: slot, mayhem, tr: Vec::new(), lastbig: None, anchor_pos: 0, anchor_last: None, last_pick: None });
    }

    /// the features of a sell candidate `(slot, sol, tok)` on `mint` from the trades seen before it (None: not followed)
    pub fn features(&self, mint: &Pk, slot: u64, sol: u64, tok: u64, bots: &FxHashSet<Pk>) -> Option<Feat> {
        let b = self.m.get(mint)?;
        let lo = |n: u64| slot.saturating_sub(n);
        let (lo_p, lo_d, lo_b, lo_a) = (lo(PRIOR_SLOTS), lo(DIPB_SLOTS), lo(BOTS_SLOTS), lo(ANCHOR_SLOTS));
        let mut prior1 = 0u32;
        let mut dipw: Vec<Pk> = Vec::new();
        let mut botw: Vec<Pk> = Vec::new();
        for t in &b.tr {
            if !t.buy && !t.ours && t.tok >= PCT1 && t.s >= lo_p { prior1 += 1; }
            if t.dip && t.s >= lo_d && !dipw.contains(&t.user) { dipw.push(t.user); }
            if !t.ours && t.s >= lo_b && bots.contains(&t.user) && !botw.contains(&t.user) { botw.push(t.user); }
        }
        let anchor_hold = b.anchor_last.is_some_and(|s| s >= lo_a) && b.anchor_pos > ANCHOR_HOLD;
        Some(Feat { slot, sol, tok, age: slot.saturating_sub(b.create_slot), prior1, dipb: dipw.len() as u32, bots: botw.len() as u32, anchor_hold,
            anchor_pos: b.anchor_pos, anchor_last: b.anchor_last, mayhem: b.mayhem })
    }

    /// a trade enters the book (after its own decision)
    pub fn push(&mut self, mint: &Pk, user: Pk, buy: bool, sol: u64, tok: u64, s: u64, i: u64) {
        let (anchor, me) = (self.anchor, self.user);
        let Some(b) = self.m.get_mut(mint) else { return };
        let ours = user == me;
        // sim.py: dipflag[t] = (S[t] - lastbig <= 2) and not ours; lastbig from every sell >= 0.3 SOL (ours too), set after the buys' check
        let dip = buy && !ours && b.lastbig.is_some_and(|lb| s as i64 - lb as i64 <= DIP_AFTER);
        if !buy && sol >= DIP_SELL { b.lastbig = Some(s); }
        if user == anchor {
            b.anchor_pos += if buy { tok as i128 } else { -(tok as i128) };
            b.anchor_last = Some(b.anchor_last.map_or(s, |x| x.max(s)));
        }
        b.tr.push(Tr { s, i, user, buy, sol, tok, ours, dip });
    }

    /// the token trades seen between (s0, i0) and (s1, i1), exclusive, not ours: (all, buys)
    pub fn between(&self, mint: &Pk, a: (u64, u64), z: (u64, u64)) -> Option<(u32, u32)> {
        let b = self.m.get(mint)?;
        let (mut n, mut nb) = (0, 0);
        for t in &b.tr { if !t.ours && (t.s, t.i) > a && (t.s, t.i) < z { n += 1; if t.buy { nb += 1; } } }
        Some((n, nb))
    }

    /// tokens older than KEEP_SLOTS (every 10 slots)
    pub fn prune(&mut self, slot_now: u64, keep: impl Fn(&Pk) -> bool) {
        if slot_now < self.pruned + 10 { return; }
        self.pruned = slot_now;
        self.m.retain(|m, b| slot_now <= b.create_slot + KEEP_SLOTS || keep(m));
    }
}

/// the price guard: min tokens out for `spend` lamports so the buy fills only while the curve's price is <= `max_price` x the post-dump
/// price (`vsol`, `vtok`): tokens the buy gets on the curve at virtual SOL sqrt(max_price) x vsol (constant product), pump's fee `fr`
pub fn min_out_price(spend: u64, fr: f64, vsol: u64, vtok: u64, max_price: f64) -> u64 {
    let k = vsol as f64 * vtok as f64;
    let vs = vsol as f64 * max_price.sqrt();
    let vt = k / vs;
    let xin = (spend as f64 / (1.0 + fr)).floor();
    ((vt * xin / (vs + xin)).floor() as u64).max(1)
}

/// the lane's fills / no-fills and realized P&L (written by the position messages and the realized lookups' tasks)
pub static FILLED: AtomicU64 = AtomicU64::new(0);
pub static NOFILL: AtomicU64 = AtomicU64::new(0);
pub static RZ_N: AtomicU64 = AtomicU64::new(0);
pub static RZ_WINS: AtomicU64 = AtomicU64::new(0);
pub static RZ_PNL: AtomicI64 = AtomicI64::new(0);

/// a realized lookup's result: the counters + its record
pub fn realized_rec(mint: &Pk, buy_sig: &str, pnl: i64, src: &str, buy_delta: Option<i64>, spend: u64) -> serde_json::Value {
    RZ_N.fetch_add(1, Ordering::SeqCst);
    if pnl > 0 { RZ_WINS.fetch_add(1, Ordering::SeqCst); }
    let run = RZ_PNL.fetch_add(pnl, Ordering::SeqCst) + pnl;
    serde_json::json!({"ev": "react_r1_realized", "mint": b58(mint), "buy_sig": buy_sig, "pnl": pnl, "src": src, "buy_delta": buy_delta, "spend": spend, "r1_realized": run,
        "t": arbx::feeds::clock::now_ns()})
}

/// the lane's decision counters (status line, run_end)
#[derive(Debug, Default)]
pub struct Stats {
    pub cand: u64, pub pass: u64, pub fired: u64, pub logged: u64,
    pub skips: std::collections::BTreeMap<&'static str, u64>, pub fails: std::collections::BTreeMap<&'static str, u64>,
}

impl Stats {
    pub fn line(&self, mode: Mode, open: usize) -> String {
        let (n, w) = (RZ_N.load(Ordering::Relaxed), RZ_WINS.load(Ordering::Relaxed));
        format!(" | R1 {}: cand {} pass {} {} {} filled {} nofill {} open {open} realized {:+.4} SOL ({w} W / {} L) skips {:?}", mode.as_str(), self.cand, self.pass,
            if mode == Mode::Live { "fired" } else { "would-fire" }, if mode == Mode::Live { self.fired } else { self.logged }, FILLED.load(Ordering::Relaxed),
            NOFILL.load(Ordering::Relaxed), RZ_PNL.load(Ordering::Relaxed) as f64 / 1e9, n - w, self.skips)
    }
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"cand": self.cand, "pass": self.pass, "fired": self.fired, "logged": self.logged, "filled": FILLED.load(Ordering::Relaxed),
            "nofill": NOFILL.load(Ordering::Relaxed), "realized": RZ_PNL.load(Ordering::Relaxed), "realized_n": RZ_N.load(Ordering::Relaxed), "wins": RZ_WINS.load(Ordering::Relaxed),
            "skips": self.skips, "fails": self.fails})
    }
}

/// the lane: its config, book, rate window, counters
pub struct R1 { pub cfg: Cfg, pub book: Book, pub fires: std::collections::VecDeque<Instant>, pub st: Stats }

impl R1 {
    pub fn new(cfg: Cfg, user: Pk) -> R1 { let a = cfg.anchor; R1 { cfg, book: Book::new(a, user), fires: Default::default(), st: Stats::default() } }
    /// the per-minute cap: a fire allowed now
    pub fn rate_ok(&mut self, now: Instant) -> bool {
        while self.fires.front().is_some_and(|t| now.duration_since(*t) >= Duration::from_secs(60)) { self.fires.pop_front(); }
        self.fires.len() < self.cfg.max_per_min
    }
}

/// ev.py block: a token picked at `last` is blocked until its exit slot + 1 (`h` = exit slots)
pub fn blocked(last: Option<u64>, slot: u64, h: u64) -> bool { last.is_some_and(|s| slot < s + h + 1) }

/// a trade's role for the lane: a candidate sell (>= 1% of supply, not ours) on a followed token
pub fn is_candidate(buy: bool, user: &Pk, me: &Pk, tok: u64) -> bool { !buy && user != me && tok >= PCT1 }

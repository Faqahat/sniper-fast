// =====================================================================================================================
// dip39 BOT DEPTH pre-send gate (owner 11-05: built LOCAL, default OFF). 8 days of tape: our real fills where FEWER than 3 distinct
// registry dip-bot wallets traded the token in the 100 slots before the dump lost on every recorded day (-1..-34 mSOL/trip); skipping
// them turns 11-02/03/04 from +0.22/+0.84/-1.75 into +2.31/+3.42/+1.73 SOL/day. The rival pre-send bots show the same split.
// Two SOURCES of "which wallets count" (--presend-live-botdepth-source list|organic, default list):
//  LIST
//   --presend-live-botdepth MIN:SLOTS       (e.g. 3:100) depth = DISTINCT listed wallets that traded the mint (buy or sell, any size) in
//                                           slots [slot - SLOTS, slot]; depth < MIN -> block
//   --presend-live-botdepth-list PATH       (needed) a JSON array of base58 wallets, or the bot registry's {"wallets": [{"wallet": ..}]}; our
//                                           wallet never counts. Re-read when its mtime changes (~30 s); a bad / empty file keeps the last good
//                                           list. FAIL OPEN: no good list (never loaded) -> nothing withheld (a warning once)
//  ORGANIC (list-free; the coordinator's best rule on 8 days of tape): token-local, from the executed feed only (trades seen before the attempt)
//   (A) dipb = distinct wallets that BOUGHT the mint in the same slot as / the 2 slots after a SELL >= 0.3 SOL of it (the sell seen first),
//       that sell within the last 200 slots
//   (B) qt   = distinct wallets that traded the mint in the last 100 slots AND closed >= TRIPS quick round trips (first buy -> position back to
//       <= 2% of what it bought within <= 20 slots) on ANY token in the last HOURS (rolling, the feed's clock)
//   pass iff dipb >= DMIN AND qt >= QMIN, else block
//   --presend-live-botdepth-organic DMIN:QMIN[:TRIPS[:HOURS]]   (default 2:2:10:2)
//   --presend-live-botdepth-state PATH      (optional) the quick-trip history saved every ~10 min and at the end, preloaded at the start (used
//                                           when saved <= 30 min before the feed's first trade). WARM-UP: until the history covers HOURS the
//                                           gate FAILS OPEN (counts logged, "warm": false, nothing withheld)
//  BOTH
//   --presend-live-botdepth-mode log|live   (default log) live: a blocked attempt is WITHHELD (not built, not sent: skip "botdepth_withheld", a
//                                           presend_live_botdepth_withheld record once per window per slot); the window stays armed and its
//                                           later attempts are re-checked. log: nothing withheld; the verdict annotated
//   ledger control file "botdepth": "live" | "log"   overrides the mode during the run
// HOW: the main loop keeps the per-mint book and hands every armed window a fixed-size copy (Snap: the newest BD_K slots per count),
// refreshed on a counted trade of the mint, at the arm and after a list reload. The SENDER counts the copy's slots inside the window at every
// due attempt (T2 and re-arm, every path): no allocation, no lock beyond the window's own.
// Records (only with the gate on): "botdepth" on presend_live_arm / presend_live_skip (at the arm's slot), presend_attempt and
// presend_live_fill (the FILLING attempt's verdict at its send + the counts at the fill's slot); a startup presend_live_botdepth_config;
// presend_live_botdepth_list on a reload; run_end presend_live.botdepth; the status line's part.
// Off (no --presend-live-botdepth and no organic source): nothing of it runs; every record and decision dip38's.
// =====================================================================================================================
use super::*;

/// the window's copy: this many newest wallets per count (MIN / DMIN / QMIN must be <= it: the decision is then exact; counts cap at it)
pub const BD_K: usize = 16;
/// --presend-live-botdepth's ranges
pub const BD_SLOTS_MAX: u64 = 2000;
/// the list's mtime check
const BD_CHECK: Duration = Duration::from_secs(30);
/// the book is pruned this often (slots)
const BD_PRUNE_SLOTS: u64 = 25;
/// the sender's per-window record limiter is trimmed past this many windows
const BD_REC_CAP: usize = 4096;
/// organic: (A) a big sell (lamports), the buy's slots after it, the window; (B) the window, a quick trip's slots, "back" = <= 1/50 bought
pub const ORG_SELL: u64 = 300_000_000;
pub const ORG_DIP_SLOTS: u64 = 2;
pub const ORG_A_SLOTS: u64 = 200;
pub const ORG_B_SLOTS: u64 = 100;
pub const ORG_HOLD: u64 = 20;
pub const ORG_BACK_DIV: u128 = 50;
/// organic: trip times kept per wallet (only ">= TRIPS in HOURS" is asked: TRIPS <= this)
const ORG_TRIPS_CAP: usize = 64;
/// organic: a state file older than this at the feed's first trade is not used
const ORG_STATE_GAP_NS: u64 = 30 * 60 * 1_000_000_000;

/// the organic parameters
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct OrgCfg { pub dmin: u32, pub qmin: u32, pub trips: u32, pub h_ns: u64 }
impl Default for OrgCfg { fn default() -> OrgCfg { OrgCfg { dmin: 2, qmin: 2, trips: 10, h_ns: 2 * 3600 * 1_000_000_000 } } }
impl OrgCfg {
    pub fn hours(&self) -> f64 { self.h_ns as f64 / 3.6e12 }
    pub fn spec(&self) -> String { format!("{}:{}:{}:{}", self.dmin, self.qmin, self.trips, self.hours()) }
}

/// the gate: its source and thresholds
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Gate { List { min: u32, slots: u64 }, Org(OrgCfg) }
impl Gate {
    pub fn src(&self) -> &'static str { match self { Gate::List { .. } => "list", Gate::Org(_) => "organic" } }
    pub fn desc(&self) -> String {
        match self {
            Gate::List { min, slots } => format!(">= {min} listed bots in {slots} slots"),
            Gate::Org(o) => format!("organic: >= {} dip buyers (buy <= {ORG_DIP_SLOTS} slots after a sell >= {} SOL, {ORG_A_SLOTS} slots) AND >= {} quick traders \
                ({ORG_B_SLOTS} slots; >= {} round trips <= {ORG_HOLD} slots in {} h)", o.dmin, ORG_SELL as f64 / 1e9, o.qmin, o.trips, o.hours()),
        }
    }
}

/// --presend-live-botdepth MIN:SLOTS -> (MIN 1..=BD_K, SLOTS 1..=BD_SLOTS_MAX)
pub fn spec_parse(s: &str) -> Result<(u32, u64)> {
    let bad = || anyhow::anyhow!("--presend-live-botdepth MIN:SLOTS (distinct listed wallets 1..{BD_K}, slots 1..{BD_SLOTS_MAX}), e.g. 3:100; got '{s}'");
    let (m, n) = s.split_once(':').ok_or_else(bad)?;
    let (m, n): (u32, u64) = (m.trim().parse().map_err(|_| bad())?, n.trim().parse().map_err(|_| bad())?);
    if !(1..=BD_K as u32).contains(&m) || !(1..=BD_SLOTS_MAX).contains(&n) { return Err(bad()); }
    Ok((m, n))
}

/// --presend-live-botdepth-organic DMIN:QMIN[:TRIPS[:HOURS]] (DMIN / QMIN 0..=BD_K, TRIPS 1..=ORG_TRIPS_CAP, HOURS in (0, 24])
pub fn org_parse(s: &str) -> Result<OrgCfg> {
    let bad = || anyhow::anyhow!("--presend-live-botdepth-organic DMIN:QMIN[:TRIPS[:HOURS]] (DMIN / QMIN 0..{BD_K}, TRIPS 1..{ORG_TRIPS_CAP}, HOURS in (0, 24]), e.g. 2:2 or 2:2:10:2; got '{s}'");
    let v: Vec<&str> = s.split(':').map(|x| x.trim()).collect();
    if !(2..=4).contains(&v.len()) { return Err(bad()); }
    let mut o = OrgCfg::default();
    o.dmin = v[0].parse().map_err(|_| bad())?;
    o.qmin = v[1].parse().map_err(|_| bad())?;
    if let Some(t) = v.get(2) { o.trips = t.parse().map_err(|_| bad())?; }
    if let Some(h) = v.get(3) {
        let h: f64 = h.parse().map_err(|_| bad())?;
        if !(h > 0.0 && h <= 24.0) { return Err(bad()); }
        o.h_ns = (h * 3.6e12).round() as u64;
    }
    if o.dmin > BD_K as u32 || o.qmin > BD_K as u32 || !(1..=ORG_TRIPS_CAP as u32).contains(&o.trips) || (o.dmin == 0 && o.qmin == 0) { return Err(bad()); }
    Ok(o)
}

/// --presend-live-botdepth-mode log|live -> live
pub fn mode_parse(s: &str) -> Result<bool> {
    match s { "log" => Ok(false), "live" => Ok(true), x => bail!("--presend-live-botdepth-mode {x}: log | live") }
}
pub fn mode_str(live: bool) -> &'static str { if live { "live" } else { "log" } }

/// the list file -> its wallets (`user` left out). A plain array of base58 strings, or {"wallets": [{"wallet": ..} | {"w": ..} | "..."]}.
/// Refused: not JSON, no array, a wallet that is not base58 / 32 bytes, no wallet at all (an empty list would withhold everything)
pub fn list_parse(b: &[u8], user: &Pk) -> Result<FxHashSet<Pk>> {
    let j: serde_json::Value = serde_json::from_slice(b).context("parse")?;
    let arr = match &j {
        serde_json::Value::Array(a) => a,
        serde_json::Value::Object(o) => o.get("wallets").and_then(|w| w.as_array()).context("no \"wallets\" array")?,
        _ => bail!("not an array or an object with \"wallets\""),
    };
    let mut set = FxHashSet::default();
    for (i, v) in arr.iter().enumerate() {
        let s = v.as_str().or_else(|| v["wallet"].as_str()).or_else(|| v["w"].as_str()).with_context(|| format!("entry {i}: no wallet"))?;
        let pk = bs58::decode(s).into_vec().ok().and_then(|x| <[u8; 32]>::try_from(x).ok()).with_context(|| format!("entry {i}: bad wallet {s}"))?;
        if pk != *user { set.insert(pk); }
    }
    if set.is_empty() { bail!("no wallet in the list"); }
    Ok(set)
}

/// newest-first copy of up to BD_K slots
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Slots { pub n: u8, pub s: [u64; BD_K] }
impl Slots {
    pub fn from_iter(it: impl Iterator<Item = u64>) -> Slots {
        let mut x: Vec<u64> = it.collect();
        x.sort_unstable_by(|a, b| b.cmp(a));
        let mut s = Slots::default();
        for (i, y) in x.into_iter().take(BD_K).enumerate() { s.s[i] = y; s.n = i as u8 + 1; }
        s
    }
    /// the slots >= slot - span (capped at BD_K). A slot past `slot` counts too: it was seen before this check (the sender's clock can
    /// trail the feed's by a slot)
    #[inline]
    pub fn count(&self, slot: u64, span: u64) -> u32 {
        let lo = slot.saturating_sub(span);
        self.s[..self.n as usize].iter().filter(|&&x| x >= lo).count() as u32
    }
}

/// a window's copy. List: `a` = the listed wallets' latest trade slots. Organic: `a` = the dip buyers' (their big sell's slot), `b` = the quick
/// traders' latest trade slots of the mint; `warm` false = the quick-trip history does not cover HOURS yet (fail open)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct Snap { pub a: Slots, pub b: Slots, pub warm: bool }

/// per mint: each listed wallet's latest trade slot (the list source)
#[derive(Debug, Default)]
pub struct Book { m: FxHashMap<Pk, Vec<(Pk, u64)>> }
impl Book {
    pub fn add(&mut self, mint: Pk, w: Pk, slot: u64) {
        let v = self.m.entry(mint).or_default();
        match v.iter_mut().find(|e| e.0 == w) { Some(e) => e.1 = e.1.max(slot), None => v.push((w, slot)) }
    }
    /// the exact depth (no cap) at `slot`: distinct wallets with a trade in [slot - SLOTS, slot]
    pub fn depth(&self, mint: &Pk, slot: u64, slots: u64) -> u32 {
        let lo = slot.saturating_sub(slots);
        self.m.get(mint).map_or(0, |v| v.iter().filter(|e| e.1 >= lo && e.1 <= slot).count() as u32)
    }
    pub fn snap(&self, mint: &Pk) -> Slots { self.m.get(mint).map_or_else(Slots::default, |v| Slots::from_iter(v.iter().map(|e| e.1))) }
    /// trades older than SLOTS before `slot_now` can never count again
    pub fn prune(&mut self, slot_now: u64, slots: u64) {
        let lo = slot_now.saturating_sub(slots);
        self.m.retain(|_, v| { v.retain(|e| e.1 >= lo); !v.is_empty() });
    }
    /// a new list: the wallets no longer listed leave
    pub fn keep_only(&mut self, set: &FxHashSet<Pk>) { self.m.retain(|_, v| { v.retain(|e| set.contains(&e.0)); !v.is_empty() }); }
    pub fn mints(&self) -> usize { self.m.len() }
}

/// organic: a wallet's open position on a mint (the round-trip detector)
#[derive(Clone, Copy, Debug)]
struct OPos { first: u64, bought: u128, held: u128 }
/// organic: a wallet on a mint: its latest dip buy's big-sell slot (0 = none) and its latest trade slot
#[derive(Clone, Copy, Debug)]
struct OTr { w: Pk, dip: u64, tr: u64 }

/// the organic book: round trips (any token), each wallet's quick-trip times, per-mint big sells and traders
#[derive(Debug)]
pub struct Org {
    pub cfg: OrgCfg,
    user: Pk,
    pos: FxHashMap<(Pk, Pk), OPos>,
    trips: FxHashMap<Pk, VecDeque<u64>>,
    sells: FxHashMap<Pk, Vec<u64>>,
    mints: FxHashMap<Pk, Vec<OTr>>,
    /// the feed's clock (ns) and slot, the history's start (ns; the state file's when used)
    pub now_t: u64, pub now_slot: u64, pub cover_from: Option<u64>,
    pruned: u64, trips_pruned: u64,
    /// a preloaded state waiting for the first trade (saved t, from, trips)
    pending: Option<(u64, u64, FxHashMap<Pk, VecDeque<u64>>)>,
    pub trips_total: u64, pub state_used: Option<bool>,
}

impl Org {
    pub fn new(cfg: OrgCfg, user: Pk) -> Org {
        Org { cfg, user, pos: FxHashMap::default(), trips: FxHashMap::default(), sells: FxHashMap::default(), mints: FxHashMap::default(), now_t: 0, now_slot: 0,
            cover_from: None, pruned: 0, trips_pruned: 0, pending: None, trips_total: 0, state_used: None }
    }
    /// one executed-feed trade (in feed order)
    pub fn trade(&mut self, mint: Pk, user: Pk, buy: bool, sol: u64, tok: u64, slot: u64, t: u64) {
        if t > self.now_t { self.now_t = t; }
        if slot > self.now_slot { self.now_slot = slot; }
        if self.cover_from.is_none() { self.first_trade(t); }
        if user == self.user { return; }
        // the round trip: first buy opens, buys add, sells take; back to <= 2% of what it bought closes it (quick: <= ORG_HOLD slots)
        let k = (user, mint);
        if buy {
            let p = self.pos.entry(k).or_insert(OPos { first: slot, bought: 0, held: 0 });
            p.bought += tok as u128; p.held += tok as u128;
        } else if let Some(p) = self.pos.get_mut(&k) {
            p.held = p.held.saturating_sub(tok as u128);
            if p.held * ORG_BACK_DIV <= p.bought {
                let first = p.first;
                self.pos.remove(&k);
                if slot.saturating_sub(first) <= ORG_HOLD {
                    let d = self.trips.entry(user).or_default();
                    d.push_back(t);
                    if d.len() > ORG_TRIPS_CAP { d.pop_front(); }
                    self.trips_total += 1;
                }
            }
        }
        // (A) a big sell of the mint; a buy within ORG_DIP_SLOTS after one (seen before it)
        let mut dip = 0;
        if !buy && sol >= ORG_SELL { let v = self.sells.entry(mint).or_default(); v.push(slot); if v.len() > 16 { v.remove(0); } }
        else if buy { if let Some(v) = self.sells.get(&mint) { dip = v.iter().copied().filter(|&s| s <= slot && slot - s <= ORG_DIP_SLOTS).max().unwrap_or(0); } }
        let v = self.mints.entry(mint).or_default();
        match v.iter_mut().find(|e| e.w == user) {
            Some(e) => { e.tr = e.tr.max(slot); e.dip = e.dip.max(dip); }
            None => v.push(OTr { w: user, dip, tr: slot }),
        }
    }
    fn first_trade(&mut self, t: u64) {
        self.cover_from = Some(t);
        if let Some((saved, from, trips)) = self.pending.take() {
            let ok = t >= saved && t - saved <= ORG_STATE_GAP_NS;
            if ok { self.cover_from = Some(from.min(t)); self.trips = trips; }
            self.state_used = Some(ok);
        }
    }
    /// the wallet closed >= TRIPS quick round trips in the last HOURS
    pub fn quick(&self, w: &Pk) -> bool {
        let lo = self.now_t.saturating_sub(self.cfg.h_ns);
        self.trips.get(w).is_some_and(|d| d.iter().rev().take_while(|&&t| t >= lo).count() >= self.cfg.trips as usize)
    }
    /// the history covers HOURS
    pub fn warm(&self) -> bool { self.cover_from.is_some_and(|c| self.now_t >= c.saturating_add(self.cfg.h_ns)) }
    /// the exact counts at `slot` (no cap): (dipb, qt)
    pub fn counts(&self, mint: &Pk, slot: u64) -> (u32, u32) {
        let Some(v) = self.mints.get(mint) else { return (0, 0) };
        let (la, lb) = (slot.saturating_sub(ORG_A_SLOTS), slot.saturating_sub(ORG_B_SLOTS));
        let a = v.iter().filter(|e| e.dip > 0 && e.dip >= la && e.dip <= slot).count() as u32;
        let b = v.iter().filter(|e| e.tr >= lb && e.tr <= slot && self.quick(&e.w)).count() as u32;
        (a, b)
    }
    /// the window's copy (the quick status as of now)
    pub fn snap(&self, mint: &Pk) -> Snap {
        let Some(v) = self.mints.get(mint) else { return Snap { warm: self.warm(), ..Default::default() } };
        Snap { a: Slots::from_iter(v.iter().filter(|e| e.dip > 0).map(|e| e.dip)), b: Slots::from_iter(v.iter().filter(|e| self.quick(&e.w)).map(|e| e.tr)), warm: self.warm() }
    }
    pub fn prune(&mut self, slot_now: u64) {
        if slot_now < self.pruned + BD_PRUNE_SLOTS { return; }
        self.pruned = slot_now;
        let lo_pos = slot_now.saturating_sub(ORG_HOLD);
        self.pos.retain(|_, p| p.first >= lo_pos);
        let lo_s = slot_now.saturating_sub(ORG_DIP_SLOTS);
        self.sells.retain(|_, v| { v.retain(|&s| s >= lo_s); !v.is_empty() });
        let lo_m = slot_now.saturating_sub(ORG_A_SLOTS.max(ORG_B_SLOTS));
        self.mints.retain(|_, v| { v.retain(|e| e.tr >= lo_m || e.dip >= lo_m); !v.is_empty() });
        // the trip times: every ~1500 slots (only memory: quick() reads them by time)
        if slot_now >= self.trips_pruned + 1500 {
            self.trips_pruned = slot_now;
            let lo = self.now_t.saturating_sub(self.cfg.h_ns);
            self.trips.retain(|_, d| { while d.front().is_some_and(|&t| t < lo) { d.pop_front(); } !d.is_empty() });
        }
    }
    pub fn sizes(&self) -> serde_json::Value {
        serde_json::json!({"pos": self.pos.len(), "wallets": self.trips.len(), "quick": self.trips.keys().filter(|w| self.quick(w)).count(), "mints": self.mints.len()})
    }
    /// the state: {"v": 1, "t": the feed's clock, "from": the history's start, "w": {wallet: [trip times ns]}}
    pub fn state_json(&self) -> serde_json::Value {
        let w: serde_json::Map<String, serde_json::Value> = self.trips.iter().map(|(k, d)| (b58(k), d.iter().copied().collect::<Vec<u64>>().into())).collect();
        serde_json::json!({"v": 1, "t": self.now_t, "from": self.cover_from, "w": w})
    }
    /// a saved state: used at the first trade when saved <= 30 min before it -> wallets
    pub fn state_load(&mut self, b: &[u8]) -> Result<usize> {
        let j: serde_json::Value = serde_json::from_slice(b).context("parse")?;
        let (Some(t), Some(from)) = (j["t"].as_u64(), j["from"].as_u64()) else { bail!("no \"t\" / \"from\"") };
        let mut m = FxHashMap::default();
        for (w, v) in j["w"].as_object().context("no \"w\" object")? {
            let Some(pk) = bs58::decode(w).into_vec().ok().and_then(|x| <[u8; 32]>::try_from(x).ok()) else { bail!("bad wallet {w}") };
            let d: VecDeque<u64> = v.as_array().map(|a| a.iter().filter_map(|x| x.as_u64()).collect()).unwrap_or_default();
            if !d.is_empty() { m.insert(pk, d); }
        }
        let n = m.len();
        self.pending = Some((t, from, m));
        Ok(n)
    }
}

/// the sender's side: the mode and the counts [T2, re-arm]
#[derive(Debug, Default)]
pub struct BdShared {
    pub live: AtomicBool,
    /// withheld (live), would-withhold (log), passed, sent with no list / in the organic warm-up (fail open)
    pub withheld: [AtomicU64; 2], pub would: [AtomicU64; 2], pub passed: [AtomicU64; 2], pub open: [AtomicU64; 2],
    /// windows with >= 1 withheld (live) / would-withhold (log) attempt
    pub wins_held: AtomicU64, pub wins_would: AtomicU64,
}

/// one attempt's verdict: the counts (list: n = depth; organic: n = dipb, q = qt), block, the mode then; ok false = fail open (no list /
/// the organic warm-up): never withheld, block false (raw = the rule's own verdict)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct BdV { pub n: u32, pub q: u32, pub block: bool, pub raw: bool, pub live: bool, pub ok: bool }
impl BdV {
    /// withhold this attempt
    pub fn withhold(&self) -> bool { self.ok && self.live && self.block }
    /// the attempt / fill record's object
    pub fn json(&self, g: &Gate) -> serde_json::Value {
        let mut j = match g {
            Gate::List { .. } => serde_json::json!({"n": if self.ok { Some(self.n) } else { None }, "block": self.block}),
            Gate::Org(_) => serde_json::json!({"dipb": self.n, "qt": self.q, "block": self.block}),
        };
        if !self.ok { j["ok"] = false.into(); if matches!(g, Gate::Org(_)) { j["warm"] = false.into(); j["raw"] = self.raw.into(); } }
        j
    }
}

/// the rule on counts
pub fn rule(g: &Gate, n: u32, q: u32) -> bool {
    match g { Gate::List { min, .. } => n < *min, Gate::Org(o) => n < o.dmin || q < o.qmin }
}

/// THE SENDER's check of a due attempt (pure but for the counts): the window's copy (None: no good list -> fail open)
#[inline]
pub fn check(bs: &BdShared, g: &Gate, snap: Option<&Snap>, slot: u64, rearm: bool) -> BdV {
    let k = rearm as usize;
    let live = bs.live.load(Ordering::Relaxed);
    let Some(s) = snap else {
        bs.open[k].fetch_add(1, Ordering::Relaxed);
        return BdV { n: 0, q: 0, block: false, raw: false, live, ok: false };
    };
    let (n, q, ok) = match g {
        Gate::List { slots, .. } => (s.a.count(slot, *slots), 0, true),
        Gate::Org(_) => (s.a.count(slot, ORG_A_SLOTS), s.b.count(slot, ORG_B_SLOTS), s.warm),
    };
    let raw = rule(g, n, q);
    if !ok { bs.open[k].fetch_add(1, Ordering::Relaxed); return BdV { n, q, block: false, raw, live, ok }; }
    if !raw { bs.passed[k].fetch_add(1, Ordering::Relaxed); }
    else if live { bs.withheld[k].fetch_add(1, Ordering::Relaxed); }
    else { bs.would[k].fetch_add(1, Ordering::Relaxed); }
    BdV { n, q, block: raw, raw, live, ok }
}

/// the sender's per-window record limiter: Some(first) = write a record for (window, slot) (first = the window's first block); None = one
/// was written for this slot already
pub fn rec_due(last: &mut FxHashMap<u64, u64>, w: u64, slot: u64) -> Option<bool> {
    if last.len() >= BD_REC_CAP { let lo = w.saturating_sub(BD_REC_CAP as u64 / 2); last.retain(|k, _| *k >= lo); }
    match last.get(&w) {
        Some(&s) if s == slot => None,
        Some(_) => { last.insert(w, slot); Some(false) }
        None => { last.insert(w, slot); Some(true) }
    }
}

/// the main loop's side
#[derive(Debug)]
pub struct Bd {
    pub gate: Gate,
    /// the list source: its path, the listed wallets (None: no good list yet -> fail open), the book
    pub path: String,
    pub set: Option<FxHashSet<Pk>>,
    mtime: Option<std::time::SystemTime>,
    checked: Instant,
    pub book: Book,
    pruned: u64,
    pub reloads: u64, pub reload_fails: u64,
    /// the start's load error (None: loaded / organic)
    pub err: Option<String>,
    /// the organic source (None: list)
    pub org: Option<Org>,
    /// organic: the state file and its last save's slot; the warm-up's end logged
    pub state: Option<String>, saved: u64, pub warm_logged: bool,
}

impl Bd {
    /// the start: the list read (a failure is kept as `err`: fail open) / the organic book (its state preloaded when given)
    pub fn open(gate: Gate, path: Option<&str>, state: Option<&str>, user: &Pk) -> Bd {
        let path = path.unwrap_or("").to_string();
        let mut b = Bd { gate, path: path.clone(), set: None, mtime: None, checked: Instant::now(), book: Book::default(), pruned: 0, reloads: 0, reload_fails: 0, err: None,
            org: None, state: state.map(|s| s.to_string()), saved: 0, warm_logged: false };
        match gate {
            Gate::List { .. } => {
                b.mtime = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
                match std::fs::read(&path).map_err(|e| anyhow::anyhow!("read: {e}")).and_then(|x| list_parse(&x, user)) { Ok(s) => b.set = Some(s), Err(e) => b.err = Some(format!("{e:#}")) }
            }
            Gate::Org(o) => {
                let mut org = Org::new(o, *user);
                if let Some(p) = state {
                    match std::fs::read(p) {
                        Ok(x) => if let Err(e) = org.state_load(&x) { b.err = Some(format!("state {p}: {e:#}")); },
                        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {}
                        Err(e) => b.err = Some(format!("state {p}: {e}")),
                    }
                }
                b.org = Some(org);
            }
        }
        b
    }
    pub fn n_list(&self) -> usize { self.set.as_ref().map_or(0, |s| s.len()) }
    /// one executed-feed trade -> the mint's armed window needs its copy again
    #[inline]
    pub fn trade(&mut self, mint: Pk, w: &Pk, buy: bool, sol: u64, tok: u64, slot: u64, t: u64) -> bool {
        if let Some(o) = self.org.as_mut() { o.trade(mint, *w, buy, sol, tok, slot, t); return true; }
        if !self.set.as_ref().is_some_and(|s| s.contains(w)) { return false; }
        self.book.add(mint, *w, slot);
        true
    }
    /// the window's copy (None: no good list)
    pub fn snap(&self, mint: &Pk) -> Option<Snap> {
        if let Some(o) = &self.org { return Some(o.snap(mint)); }
        self.set.as_ref().map(|_| Snap { a: self.book.snap(mint), b: Slots::default(), warm: true })
    }
    /// the exact verdict at `slot` (the arm / skip / fill records)
    pub fn verdict(&self, mint: &Pk, slot: u64, live: bool) -> BdV {
        let (n, q, ok) = match (&self.org, &self.gate) {
            (Some(o), _) => { let (a, b) = o.counts(mint, slot); (a, b, o.warm()) }
            (None, Gate::List { slots, .. }) => (self.book.depth(mint, slot, *slots), 0, self.set.is_some()),
            (None, Gate::Org(_)) => (0, 0, false),
        };
        let raw = rule(&self.gate, n, q);
        BdV { n, q, block: ok && raw, raw, live, ok }
    }
    pub fn prune(&mut self, slot_now: u64) {
        if let Some(o) = self.org.as_mut() { o.prune(slot_now); return; }
        if slot_now < self.pruned + BD_PRUNE_SLOTS { return; }
        self.pruned = slot_now;
        if let Gate::List { slots, .. } = self.gate { self.book.prune(slot_now, slots); }
    }
    /// the list's reload (every ~30 s; `force`: now): Some(record) when the file changed (ok or not); never for organic
    pub fn check(&mut self, force: bool, user: &Pk) -> Option<serde_json::Value> {
        if self.org.is_some() { return None; }
        if !force && self.checked.elapsed() < BD_CHECK { return None; }
        self.checked = Instant::now();
        let mt = std::fs::metadata(&self.path).and_then(|m| m.modified()).ok();
        if !force && mt == self.mtime { return None; }
        self.mtime = mt;
        let r = std::fs::read(&self.path).map_err(|e| anyhow::anyhow!("read: {e}")).and_then(|b| list_parse(&b, user));
        Some(match r {
            Ok(s) => {
                let was = self.n_list();
                self.book.keep_only(&s);
                self.set = Some(s);
                self.err = None;
                self.reloads += 1;
                serde_json::json!({"ev": "presend_live_botdepth_list", "ok": true, "path": self.path, "n": self.n_list(), "was": was, "t": arbx::feeds::clock::now_ns()})
            }
            Err(e) => {
                self.reload_fails += 1;
                serde_json::json!({"ev": "presend_live_botdepth_list", "ok": false, "path": self.path, "err": format!("{e:#}"), "n": self.n_list(),
                    "fail_open": self.set.is_none(), "t": arbx::feeds::clock::now_ns()})
            }
        })
    }
    /// organic: save the state (a thread; nothing without the file)
    fn save(&self, sync: bool) -> Option<std::result::Result<usize, String>> {
        let (Some(p), Some(o)) = (self.state.clone(), self.org.as_ref()) else { return None };
        let j = o.state_json();
        let n = o.trips.len();
        let w = move || -> std::result::Result<usize, String> {
            let tmp = format!("{p}.tmp");
            std::fs::write(&tmp, j.to_string()).map_err(|e| format!("write {tmp}: {e}"))?;
            std::fs::rename(&tmp, &p).map_err(|e| format!("rename {tmp}: {e}"))?;
            Ok(n)
        };
        if sync { return Some(w()); }
        std::thread::spawn(move || { if let Err(e) = w() { eprintln!("DIP PRESEND LIVE BOT DEPTH: state NOT saved: {e}"); } });
        None
    }
    #[cfg(test)]
    pub fn mtime_reset_for_test(&mut self) { self.mtime = None; self.checked = Instant::now().checked_sub(BD_CHECK * 2).unwrap_or_else(Instant::now); }
}

/// the control file's "botdepth" key: Some(live) / None (absent)
pub fn ctl_parse_bd(b: &[u8]) -> std::result::Result<Option<bool>, String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    match v["botdepth"].as_str() { None if v.get("botdepth").is_none_or(|x| x.is_null()) => Ok(None), Some("live") => Ok(Some(true)), Some("log") => Ok(Some(false)),
        _ => Err(format!("botdepth: '{}' (live | log)", v["botdepth"])) }
}

/// an arm / skip / fill record's object of a verdict
fn rec_json(b: &Bd, v: &BdV) -> serde_json::Value {
    let mode = mode_str(v.live);
    match b.gate {
        Gate::List { min, slots } => {
            let mut j = serde_json::json!({"n": if v.ok { Some(v.n) } else { None }, "min": min, "slots": slots, "block": v.block, "mode": mode});
            if !v.ok { j["ok"] = false.into(); }
            j
        }
        Gate::Org(o) => {
            let mut j = serde_json::json!({"src": "organic", "dipb": v.n, "qt": v.q, "dmin": o.dmin, "qmin": o.qmin, "block": v.block, "mode": mode});
            if !v.ok { j["warm"] = false.into(); j["raw"] = v.raw.into(); }
            j
        }
    }
}

impl PsLive {
    /// the gate's object for an arm / skip record at `slot` (None: the gate off)
    pub(super) fn bd_json(&self, mint: &Pk, slot: u64) -> Option<serde_json::Value> {
        let b = self.bd.as_ref()?;
        Some(rec_json(b, &b.verdict(mint, slot, self.sh.bd.live.load(Ordering::Relaxed))))
    }
    /// a new window's copy (None: the gate off or no good list)
    pub(super) fn bd_snap(&self, mint: &Pk) -> Option<Snap> { self.bd.as_ref().and_then(|b| b.snap(mint)) }
    /// the executed feed's trade: into the book; the mint's armed window's copy when it changed (list: O(1) for an unlisted wallet)
    pub(super) fn bd_trade(&mut self, mint: &Pk, user: &Pk, buy: bool, sol: u64, tok: u64, slot: u64, t: u64) {
        let Some(b) = self.bd.as_mut() else { return };
        if !b.trade(*mint, user, buy, sol, tok, slot, t) { return; }
        if self.armed.contains_key(mint) { self.bd_refresh(mint); }
    }
    /// the armed window of `mint`: its copy again
    pub(super) fn bd_refresh(&mut self, mint: &Pk) {
        let Some(&id) = self.armed.get(mint) else { return };
        let s = self.bd_snap(mint);
        let mut g = self.sh.wins.lock().unwrap();
        if let Some(w) = g.iter_mut().find(|w| w.id == id) { w.bd = s; }
    }
    /// the fill's object: the filling attempt's verdict at its send (`v`: None = sent with no list) + the counts at the fill's slot
    pub(super) fn bd_fill_json(&self, v: Option<BdV>, mint: &Pk, slot: u64) -> Option<serde_json::Value> {
        let b = self.bd.as_ref()?;
        let live = self.sh.bd.live.load(Ordering::Relaxed);
        let mut j = rec_json(b, &v.unwrap_or(BdV { n: 0, q: 0, block: false, raw: false, live, ok: false }));
        j["at"] = "send".into();
        let f = b.verdict(mint, slot, live);
        match b.gate { Gate::List { .. } => { j["n_fill"] = if f.ok { Some(f.n) } else { None }.into(); } Gate::Org(_) => { j["dipb_fill"] = f.n.into(); j["qt_fill"] = f.q.into(); } }
        Some(j)
    }
    /// every tick: the book's prune, the list's reload (a new list: every armed window's copy again), organic: the warm-up's end, the state
    pub(super) fn bd_tick(&mut self, slot_now: u64) {
        let user = self.user;
        let Some(b) = self.bd.as_mut() else { return };
        b.prune(slot_now);
        if let Some(o) = &b.org {
            if !b.warm_logged && o.warm() {
                b.warm_logged = true;
                let r = serde_json::json!({"ev": "presend_live_botdepth_warm", "from": o.cover_from, "t": o.now_t, "slot": slot_now, "sizes": o.sizes()});
                let l = format!("  PRESEND LIVE BOT DEPTH organic: WARM (the quick-trip history covers {} h): the gate decides from now", o.cfg.hours());
                self.line(l);
                self.rec(r);
                let ms: Vec<Pk> = self.armed.keys().copied().collect();
                for m in ms { self.bd_refresh(&m); }
                return;
            }
            if b.state.is_some() && slot_now >= b.saved + CR_SAVE_SLOTS {
                if b.saved > 0 { b.save(false); }
                b.saved = slot_now;
            }
            return;
        }
        let Some(r) = b.check(false, &user) else { return };
        let ok = r["ok"] == true;
        self.line(format!("  PRESEND LIVE BOT DEPTH list {} {}", if ok { "reloaded:" } else { "NOT reloaded (the last good list stays):" }, r));
        self.rec(r);
        if ok { let ms: Vec<Pk> = self.armed.keys().copied().collect(); for m in ms { self.bd_refresh(&m); } }
    }
    /// the start's record and line (nothing with the gate off)
    pub(super) fn bd_start(&mut self) {
        let Some(b) = self.bd.as_ref() else { return };
        let live = self.sh.bd.live.load(Ordering::Relaxed);
        let mut r = serde_json::json!({"ev": "presend_live_botdepth_config", "src": b.gate.src(), "mode": mode_str(live), "k": BD_K, "err": b.err, "t": arbx::feeds::clock::now_ns()});
        match b.gate {
            Gate::List { min, slots } => { r["ok"] = b.set.is_some().into(); r["path"] = b.path.clone().into(); r["n"] = b.n_list().into(); r["min"] = min.into(); r["slots"] = slots.into(); }
            Gate::Org(o) => {
                r["ok"] = true.into();
                r["organic"] = serde_json::json!({"dmin": o.dmin, "qmin": o.qmin, "trips": o.trips, "hours": o.hours(), "sell_sol": ORG_SELL as f64 / 1e9, "dip_slots": ORG_DIP_SLOTS,
                    "a_slots": ORG_A_SLOTS, "b_slots": ORG_B_SLOTS, "hold_slots": ORG_HOLD, "back_pct": 100.0 / ORG_BACK_DIV as f64, "state": b.state});
                r["warmup"] = "fail open until the quick-trip history covers the hours (a state file saved <= 30 min before the first trade counts)".into();
            }
        }
        if let Some(e) = &b.err {
            self.line(format!("  WARNING PRESEND LIVE BOT DEPTH: {} did NOT load ({e}): FAIL OPEN (no attempt withheld) until {}", if b.org.is_some() { "the state" } else { b.path.as_str() },
                if b.org.is_some() { "the warm-up ends" } else { "a good list is read" }));
        }
        self.rec(r);
    }
    /// the status line's part ("" with the gate off)
    pub(super) fn bd_status(&self) -> String {
        let Some(b) = self.bd.as_ref() else { return String::new() };
        let s = &self.sh.bd;
        let l = |a: &[AtomicU64; 2]| format!("{}/{}", a[0].load(Ordering::Relaxed), a[1].load(Ordering::Relaxed));
        let src = match (&b.gate, &b.org) {
            (Gate::List { min, slots }, _) => format!(">= {min} in {slots} slots (list {}{})", b.n_list(), if b.set.is_none() { " NOT LOADED: fail open" } else { "" }),
            (Gate::Org(o), Some(org)) => format!("organic dipb >= {} qt >= {} ({}; quick wallets {}, trips {})", o.dmin, o.qmin, if org.warm() { "warm" } else { "WARM-UP: fail open" },
                org.trips.keys().filter(|w| org.quick(w)).count(), org.trips_total),
            _ => String::new(),
        };
        format!(" | BOT DEPTH {} {src}: withheld T2/re-arm {} (windows {}), would (log) {} (windows {}), passed {}, fail open {}",
            if s.live.load(Ordering::Relaxed) { "LIVE" } else { "LOG" }, l(&s.withheld), s.wins_held.load(Ordering::Relaxed), l(&s.would), s.wins_would.load(Ordering::Relaxed), l(&s.passed), l(&s.open))
    }
    /// run_end's part (None with the gate off); organic: the state saved
    pub(super) fn bd_finish(&mut self) -> Option<serde_json::Value> {
        let b = self.bd.as_ref()?;
        if let Some(r) = b.save(true) {
            let p = b.state.clone().unwrap_or_default();
            match r { Ok(n) => self.line(format!("  PRESEND LIVE BOT DEPTH: quick-trip history of {n} wallets saved to {p}")),
                      Err(e) => self.line(format!("  PRESEND LIVE BOT DEPTH: state NOT saved to {p}: {e}")) }
        }
        let b = self.bd.as_ref()?;
        let s = &self.sh.bd;
        let a = |x: &[AtomicU64; 2]| serde_json::json!({"t2": x[0].load(Ordering::Relaxed), "rearm": x[1].load(Ordering::Relaxed)});
        let mut j = serde_json::json!({"src": b.gate.src(), "mode": mode_str(s.live.load(Ordering::Relaxed)),
            "withheld": a(&s.withheld), "would": a(&s.would), "passed": a(&s.passed), "open": a(&s.open), "windows_held": s.wins_held.load(Ordering::Relaxed),
            "windows_would": s.wins_would.load(Ordering::Relaxed)});
        match (&b.gate, &b.org) {
            (Gate::List { min, slots }, _) => { j["min"] = (*min).into(); j["slots"] = (*slots).into(); j["list"] = b.n_list().into(); j["loaded"] = b.set.is_some().into();
                j["reloads"] = b.reloads.into(); j["reload_fails"] = b.reload_fails.into(); j["mints"] = b.book.mints().into(); }
            (Gate::Org(o), Some(org)) => { j["organic"] = serde_json::json!({"spec": o.spec(), "warm": org.warm(), "trips": org.trips_total, "state_used": org.state_used, "sizes": org.sizes()}); }
            _ => {}
        }
        Some(j)
    }
}

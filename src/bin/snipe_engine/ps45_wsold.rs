// =====================================================================================================================
// dip45 WHALE-SOLD tracker (LOG ONLY; --presend-live-whale-sold-log on, off by default = the dip45 fleet build byte for byte).
// Why: the PEMURULE replay (~/sniper-studies/pemurule, ~/sniper-data/pemurule/report.txt) found that filling only AFTER the T2 trigger
// whale has sold >= 50% of its arm-time bag beat our live T2 by ~+1.7 SOL on the filled windows r65-r82 (peMU8nX3 does it on chain).
// This measures it live: nothing is sent, armed, skipped, sized or changed; the engine reads nothing back.
//
//  1. TRACK per trigger (mint, whale, trigger position): opened by our live / dry T2 (and wide) arm (presend_live_arm with "trig") and by
//     the pre-send shadow's paper arm (presend_arm / presend_wide_arm); one track per trigger, every arm on it listed. Bag = the
//     trigger record's "bal" (the detector's whale balance AFTER the trigger buy = the replay's bag); with --presend-live-tbal on, the
//     true-balance book's value is read once after the trigger tx and logged beside it (tbal, never used for the fractions).
//  2. The whale's trades on the mint after the trigger position until the window end + TAIL_SLOTS (a fill extends it to fill + TAIL_SLOTS):
//     every SELL -> record "sell" (sold_tok, cum_sold_tok, cum_frac = cum sold / bag, net_frac = (bag - balance now) / bag = the replay's
//     rule, exec arrival time / feed, seen on a pre-exec feed first?). Trades that arrived before the arm (the shadow's records can come
//     late) are taken from a 64-slot ring of executed trades (backfill: true; pre-exec unknown).
//  3. Our fills / the shadow's would-fills: record "fill" / "shadow_fill" with the whale's fractions BEFORE the fill's position (a live
//     fill: trades strictly before (slot, idx); a would-fill: up to and including its dump trade) and sold25 / sold50 (by cum_frac and
//     by net_frac). Recomputed at the close (final, complete) in the "close" record.
//  4. "close" per track: first-sell slot, the slots where cum_frac crossed 25 / 50 / 100 %, max fractions, arms, fills.
// Status line part "WHALE SOLD LOG", run_end "whale_sold".
// =====================================================================================================================
use super::*;

/// slots tracked after the window's end (and after a fill)
pub const TAIL_SLOTS: u64 = 30;
/// a shadow arm without an end: trigger + this
pub const MIN_WIN: u64 = 11;
/// executed trades kept for the backfill (slots)
pub const RING_SLOTS: u64 = 64;
/// pre-exec sightings of tracked whales kept
const PRE_KEEP: usize = 8192;
/// closed tracks kept for late fills
const CLOSED_KEEP: usize = 512;

pub type Pos = (u64, u32, u16);

/// cum / bag (0 with no bag)
pub fn frac(x: u64, bag: u64) -> f64 { if bag == 0 { 0.0 } else { x as f64 / bag as f64 } }
/// x >= pct % of bag, exact (integers); never with no bag
pub fn at_least(x: u64, bag: u64, pct: u64) -> bool { bag > 0 && x as u128 * 100 >= bag as u128 * pct as u128 }
/// the replay's net sold: bag - (bag - sold + bought), floored at 0
pub fn net_sold(sold: u64, bought: u64) -> u64 { sold.saturating_sub(bought) }

#[derive(Clone, Copy, Debug)]
pub struct WTrade { pub user: Pk, pub buy: bool, pub tok: u64, pub pos: Pos, pub t: u64, pub feed: u16, pub pre_t: Option<u64>, pub backfill: bool }

#[derive(Clone, Debug)]
pub struct FillAnn { pub stage: &'static str, pub w: u64, pub kind: String, pub at: Pos, pub incl: bool }

#[derive(Clone, Debug)]
pub struct Track {
    pub id: u64, pub mint: Pk, pub whale: Pk, pub bag: u64, pub tbal: Option<u64>, tbal_read: bool, pub trig: Pos, pub end: u64,
    pub sold: u64, pub bought: u64, pub n_sells: u32, pub n_buys: u32,
    /// first sell, and the positions where cum_frac reached 25 / 50 / 100 % and net_frac 50 %
    pub first_sell: Option<Pos>, pub x25: Option<Pos>, pub x50: Option<Pos>, pub x100: Option<Pos>, pub n50: Option<Pos>, pub max_net: u64,
    pub trades: Vec<WTrade>,
    pub arms: Vec<(&'static str, u64, String, bool)>,
    pub fills: Vec<FillAnn>,
}

/// the whale's state before position p (incl: p itself counted)
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct At { pub sold: u64, pub bought: u64, pub n_sells: u32, pub last_sell: Option<u64> }

impl Track {
    pub fn new(id: u64, mint: Pk, whale: Pk, bag: u64, trig: Pos, end: u64) -> Track {
        Track { id, mint, whale, bag, tbal: None, tbal_read: false, trig, end, sold: 0, bought: 0, n_sells: 0, n_buys: 0, first_sell: None, x25: None, x50: None, x100: None,
            n50: None, max_net: 0, trades: Vec::new(), arms: Vec::new(), fills: Vec::new() }
    }

    /// one whale trade (after the trigger); false = not taken (before the trigger, or a duplicate)
    pub fn add(&mut self, x: WTrade) -> bool {
        if x.pos <= self.trig || self.trades.iter().any(|y| y.pos == x.pos) { return false; }
        // in chain order (a late arrival is put in place; the crossings are recomputed)
        let k = self.trades.partition_point(|y| y.pos < x.pos);
        let in_order = k == self.trades.len();
        self.trades.insert(k, x);
        if in_order {
            if x.buy { self.bought += x.tok; self.n_buys += 1; } else { self.sold += x.tok; self.n_sells += 1; self.cross(x.pos); }
        } else { self.recompute(); }
        true
    }

    fn cross(&mut self, p: Pos) {
        if self.first_sell.is_none() { self.first_sell = Some(p); }
        if self.x25.is_none() && at_least(self.sold, self.bag, 25) { self.x25 = Some(p); }
        if self.x50.is_none() && at_least(self.sold, self.bag, 50) { self.x50 = Some(p); }
        if self.x100.is_none() && at_least(self.sold, self.bag, 100) { self.x100 = Some(p); }
        let ns = net_sold(self.sold, self.bought);
        self.max_net = self.max_net.max(ns);
        if self.n50.is_none() && at_least(ns, self.bag, 50) { self.n50 = Some(p); }
    }

    fn recompute(&mut self) {
        let tr = std::mem::take(&mut self.trades);
        (self.sold, self.bought, self.n_sells, self.n_buys, self.first_sell, self.x25, self.x50, self.x100, self.n50, self.max_net) = (0, 0, 0, 0, None, None, None, None, None, 0);
        for x in &tr { if x.buy { self.bought += x.tok; self.n_buys += 1; } else { self.sold += x.tok; self.n_sells += 1; self.cross(x.pos); } }
        self.trades = tr;
    }

    pub fn at(&self, p: Pos, incl: bool) -> At {
        let mut a = At::default();
        for x in self.trades.iter().filter(|x| if incl { x.pos <= p } else { x.pos < p }) {
            if x.buy { a.bought += x.tok; } else { a.sold += x.tok; a.n_sells += 1; a.last_sell = Some(x.pos.0); }
        }
        a
    }

    pub fn ann(&self, p: Pos, incl: bool) -> serde_json::Value {
        let a = self.at(p, incl);
        let ns = net_sold(a.sold, a.bought);
        serde_json::json!({"cum_sold_tok": a.sold, "cum_frac": frac(a.sold, self.bag), "net_frac": frac(ns, self.bag), "sold25": at_least(a.sold, self.bag, 25),
            "sold50": at_least(a.sold, self.bag, 50), "net50": at_least(ns, self.bag, 50), "n_sells_before": a.n_sells, "last_sell_slot": a.last_sell,
            "dslot_trig": p.0.saturating_sub(self.trig.0)})
    }

    fn arms_json(&self) -> Vec<serde_json::Value> {
        self.arms.iter().map(|a| serde_json::json!({"src": a.0, "w": a.1, "kind": a.2, "dry": a.3})).collect()
    }

    pub fn close_rec(&self) -> serde_json::Value {
        let p = |x: Option<Pos>| x.map(|p| serde_json::json!([p.0, p.1]));
        let d = |x: Option<Pos>| x.map(|p| p.0.saturating_sub(self.trig.0));
        let fills: Vec<serde_json::Value> = self.fills.iter().map(|f| {
            let mut j = self.ann(f.at, f.incl);
            j["stage"] = f.stage.into(); j["w"] = f.w.into(); j["kind"] = f.kind.clone().into(); j["slot"] = f.at.0.into();
            if f.at.1 != u32::MAX { j["idx"] = f.at.1.into(); }
            j
        }).collect();
        serde_json::json!({"ev": "presend_live_whale_sold", "stage": "close", "track": self.id, "mint": b58(&self.mint), "whale": b58(&self.whale), "bag": self.bag,
            "tbal": self.tbal, "trig": [self.trig.0, self.trig.1], "end_slot": self.end, "n_sells": self.n_sells, "n_buys": self.n_buys, "cum_sold_tok": self.sold,
            "bought_tok": self.bought, "max_cum_frac": frac(self.sold, self.bag), "max_net_frac": frac(self.max_net, self.bag),
            "first_sell": p(self.first_sell), "first_sell_dslot": d(self.first_sell), "s25": p(self.x25), "s50": p(self.x50), "s100": p(self.x100), "net50": p(self.n50),
            "dslot25": d(self.x25), "dslot50": d(self.x50), "dslot100": d(self.x100), "arms": self.arms_json(), "fills": fills})
    }
}

#[derive(Default, Clone, Debug)]
pub struct WsStats { pub tracks: u64, pub closed: u64, pub arms: u64, pub arms_untracked: u64, pub sells: u64, pub sells_pre: u64, pub sells_backfill: u64,
    pub c25: u64, pub c50: u64, pub c100: u64, pub never: u64, pub fills: u64, pub fills50: u64, pub fills25: u64, pub sh_fills: u64, pub sh_fills50: u64, pub sh_fills25: u64,
    pub fills_untracked: u64 }

pub struct WSold {
    out: crossbeam_channel::Sender<Out>,
    pub tracks: Vec<Track>,
    closed: VecDeque<Track>,
    /// (src, w) -> track id
    by_w: FxHashMap<(&'static str, u64), u64>,
    /// tracked mints -> open track count; tracked whales -> count (the event loop's tests)
    mints: FxHashMap<Pk, u32>,
    whales: FxHashMap<Pk, u32>,
    /// executed trades of the last RING_SLOTS slots (mint, trade)
    ring: VecDeque<(Pk, WTrade)>,
    /// pre-exec sightings of tracked whales' txs: sig8 -> (t, feed)
    pre: FxHashMap<u64, (u64, u16)>,
    pre_q: VecDeque<u64>,
    next: u64,
    pub slot: u64,
    pub feeds: Vec<String>,
    pub st: WsStats,
}

fn sig8(s: &[u8; 64]) -> u64 { u64::from_be_bytes(s[..8].try_into().unwrap()) }
fn pk_of(s: &str) -> Option<Pk> { bs58::decode(s).into_vec().ok().and_then(|v| v.try_into().ok()) }

impl WSold {
    pub fn start(out: &crossbeam_channel::Sender<Out>) -> WSold {
        eprintln!("DIP WHALE-SOLD TRACKER (dip45, LOG ONLY: nothing sent, no decision changed): per T2 / shadow arm the trigger whale's sells until the window end + {TAIL_SLOTS} slots \
            | cum / net fraction of its arm-time bag at our fills and would-fills | 25 / 50 / 100 % crossings");
        let _ = out.send(Out::Rec(serde_json::json!({"ev": "presend_live_whale_sold", "stage": "config", "mode": "log", "tail_slots": TAIL_SLOTS, "min_win": MIN_WIN,
            "ring_slots": RING_SLOTS, "bag": "trigger record bal (detector balance after the trigger buy); tbal = true-balance book (only with --presend-live-tbal on)"})));
        WSold { out: out.clone(), tracks: Vec::new(), closed: VecDeque::new(), by_w: FxHashMap::default(), mints: FxHashMap::default(), whales: FxHashMap::default(),
            ring: VecDeque::new(), pre: FxHashMap::default(), pre_q: VecDeque::new(), next: 0, slot: 0, feeds: Vec::new(), st: WsStats::default() }
    }

    fn emit(&self, r: serde_json::Value) { let _ = self.out.send(Out::Rec(r)); }

    /// every arrival: a tracked whale's tx on a pre-exec feed (its first sighting)
    pub fn arrival(&mut self, a: &arbx::feeds::Arrival) {
        if a.executed.is_some() || self.whales.is_empty() { return; }
        let Some(k0) = a.tx.keys.first() else { return };
        if !self.whales.contains_key(k0) { return; }
        let s = sig8(&a.tx.sig);
        if self.pre.contains_key(&s) { return; }
        self.pre.insert(s, (a.t_rx, a.feed));
        self.pre_q.push_back(s);
        while self.pre_q.len() > PRE_KEEP { if let Some(x) = self.pre_q.pop_front() { self.pre.remove(&x); } }
    }

    /// an executed pump tx (before anything decides on it): the ring, the tracked whales' trades; the tracks past their end close
    pub fn exec(&mut self, a: &arbx::feeds::Arrival, x: &arbx::feeds::ExecInfo, slot_now: u64, book: Option<&arbx::ps43_book::TBook>) {
        self.tick(slot_now.max(a.slot), book);
        if x.trades.is_empty() { return; }
        let pre_t = if self.pre.is_empty() { None } else { self.pre.get(&sig8(&a.tx.sig)).copied() };
        for (j, e) in x.trades.iter().enumerate() {
            let w = WTrade { user: e.user, buy: e.buy, tok: e.tok, pos: (a.slot, x.index as u32, j as u16), t: a.t_rx, feed: a.feed, pre_t: pre_t.map(|p| p.0), backfill: false };
            self.ring.push_back((e.mint, w));
            if self.mints.contains_key(&e.mint) && self.whales.contains_key(&e.user) { self.whale_trade(&e.mint, w); }
        }
    }

    /// the slot clock: ring prune, the tbal read after the trigger tx, the tracks past their end
    pub fn tick(&mut self, slot: u64, book: Option<&arbx::ps43_book::TBook>) {
        if let Some(b) = book {
            for t in self.tracks.iter_mut().filter(|t| !t.tbal_read) { t.tbal_read = true; t.tbal = b.true_balance(&t.mint, &t.whale); }
        }
        if slot <= self.slot { return; }
        self.slot = slot;
        let lo = slot.saturating_sub(RING_SLOTS);
        while self.ring.front().is_some_and(|x| x.1.pos.0 < lo) { self.ring.pop_front(); }
        let done: Vec<usize> = (0..self.tracks.len()).filter(|&i| slot > self.tracks[i].end).collect();
        for i in done.into_iter().rev() { let t = self.tracks.remove(i); self.close(t); }
    }

    fn close(&mut self, t: Track) {
        self.st.closed += 1;
        if t.x25.is_some() { self.st.c25 += 1; }
        if t.x50.is_some() { self.st.c50 += 1; }
        if t.x100.is_some() { self.st.c100 += 1; }
        if t.first_sell.is_none() { self.st.never += 1; }
        for (m, c) in [(&t.mint, &mut self.mints), (&t.whale, &mut self.whales)] {
            if let Some(n) = c.get_mut(m) { *n -= 1; if *n == 0 { c.remove(m); } }
        }
        self.emit(t.close_rec());
        self.closed.push_back(t);
        while self.closed.len() > CLOSED_KEEP { self.closed.pop_front(); }
    }

    fn whale_trade(&mut self, mint: &Pk, w: WTrade) {
        let mut recs = Vec::new();
        for t in self.tracks.iter_mut().filter(|t| t.mint == *mint && t.whale == w.user && w.pos.0 <= t.end) {
            if !t.add(w) || w.buy { continue; }
            recs.push(sell_rec(t, &w, &self.feeds));
        }
        for r in recs {
            self.st.sells += 1;
            if w.pre_t.is_some() { self.st.sells_pre += 1; }
            if w.backfill { self.st.sells_backfill += 1; }
            self.emit(r);
        }
    }

    /// an arm: its track (new, or the trigger's existing one) + the arm record
    #[allow(clippy::too_many_arguments)]
    pub fn arm(&mut self, src: &'static str, w: u64, kind: String, dry: bool, mint: Pk, whale: Pk, bal: i64, trig: Pos, end: u64) {
        self.st.arms += 1;
        let bag = bal.max(0) as u64;
        let end = end.max(trig.0 + MIN_WIN) + TAIL_SLOTS;
        let i = match self.tracks.iter().position(|t| t.mint == mint && t.whale == whale && t.trig == trig) {
            Some(i) => { let t = &mut self.tracks[i]; t.end = t.end.max(end); i }
            None => {
                self.next += 1; self.st.tracks += 1;
                self.tracks.push(Track::new(self.next, mint, whale, bag, trig, end));
                *self.mints.entry(mint).or_default() += 1;
                *self.whales.entry(whale).or_default() += 1;
                // backfill: the whale's trades already in the ring (the shadow's records can come after them)
                let back: Vec<WTrade> = self.ring.iter().filter(|x| x.0 == mint && x.1.user == whale && x.1.pos > trig).map(|x| WTrade { backfill: true, ..x.1 }).collect();
                for x in back { self.whale_trade(&mint, x); }
                self.tracks.len() - 1
            }
        };
        let t = &mut self.tracks[i];
        t.arms.push((src, w, kind.clone(), dry));
        let (id, slot) = (t.id, self.slot);
        let r = serde_json::json!({"ev": "presend_live_whale_sold", "stage": "arm", "src": src, "w": w, "kind": kind, "dry": dry, "mint": b58(&mint), "whale": b58(&whale),
            "bag": t.bag, "trig": [trig.0, trig.1], "end_slot": t.end, "track": id, "slot": slot, "now": t.ann((slot, u32::MAX, u16::MAX), true)});
        self.by_w.insert((src, w), id);
        self.emit(r);
    }

    /// a fill (src "live": our live / dry fill; "shadow" / "wide_shadow": a would-fill) of window w at position `at`
    pub fn fill(&mut self, src: &'static str, stage: &'static str, w: u64, kind: String, at: Pos, incl: bool) {
        let shadow = stage == "shadow_fill";
        let Some(&id) = self.by_w.get(&(src, w)) else {
            self.st.fills_untracked += 1;
            if !shadow { self.emit(serde_json::json!({"ev": "presend_live_whale_sold", "stage": stage, "src": src, "w": w, "kind": kind, "slot": at.0, "track": null})); }
            return;
        };
        let (t, open) = match self.tracks.iter_mut().find(|t| t.id == id) { Some(t) => (t, true), None => match self.closed.iter_mut().find(|t| t.id == id) { Some(t) => (t, false), None => return } };
        if open { t.end = t.end.max(at.0 + TAIL_SLOTS); }
        t.fills.push(FillAnn { stage, w, kind: kind.clone(), at, incl });
        let mut r = t.ann(at, incl);
        let (s25, s50) = (r["sold25"] == true, r["sold50"] == true);
        r["ev"] = "presend_live_whale_sold".into(); r["stage"] = stage.into(); r["src"] = src.into(); r["w"] = w.into(); r["kind"] = kind.into(); r["track"] = id.into();
        r["mint"] = b58(&t.mint).into(); r["whale"] = b58(&t.whale).into(); r["bag"] = t.bag.into(); r["slot"] = at.0.into(); r["track_open"] = open.into();
        if at.1 != u32::MAX { r["idx"] = at.1.into(); }
        if shadow { self.st.sh_fills += 1; self.st.sh_fills25 += s25 as u64; self.st.sh_fills50 += s50 as u64; } else { self.st.fills += 1; self.st.fills25 += s25 as u64; self.st.fills50 += s50 as u64; }
        self.emit(r);
    }

    /// our record (PsLive::rec): T2 / wide arms (with "trig") open tracks; fills are annotated
    pub fn on_rec(&mut self, v: &serde_json::Value) {
        match v["ev"].as_str().unwrap_or("") {
            "presend_live_arm" => {
                let tr = &v["trig"];
                let (Some(mint), Some(whale)) = (tr["mint"].as_str().and_then(pk_of), tr["wallet"].as_str().and_then(pk_of)) else { self.st.arms_untracked += 1; return };
                let trig = (tr["slot"].as_u64().unwrap_or(0), tr["idx"].as_u64().unwrap_or(0) as u32, tr["j"].as_u64().unwrap_or(0) as u16);
                let end = v["en_slot"].as_u64().unwrap_or(trig.0 + MIN_WIN);
                self.arm("live", v["w"].as_u64().unwrap_or(0), v["kind"].as_str().unwrap_or("t2").to_string(), v["dry"].as_bool().unwrap_or(false), mint, whale,
                    tr["bal"].as_i64().unwrap_or(0), trig, end);
            }
            "presend_live_fill" => {
                let Some(s) = v["slot"].as_u64() else { return };
                let at = (s, v["idx"].as_u64().map_or(u32::MAX, |i| i as u32), 0);
                self.fill("live", "fill", v["w"].as_u64().unwrap_or(0), v["kind"].as_str().unwrap_or("t2").to_string(), at, false);
            }
            _ => {}
        }
    }

    /// the pre-send shadow's records: paper arms open tracks, would-fills are annotated (at their dump trade, inclusive)
    pub fn on_shadow(&mut self, v: &serde_json::Value) {
        let ev = v["ev"].as_str().unwrap_or("");
        let src = if ev.starts_with("presend_wide_") { "wide_shadow" } else { "shadow" };
        match ev {
            "presend_arm" | "presend_wide_arm" => {
                let (Some(mint), Some(whale)) = (v["mint"].as_str().and_then(pk_of), v["wallet"].as_str().and_then(pk_of)) else { self.st.arms_untracked += 1; return };
                let trig = (v["slot"].as_u64().unwrap_or(0), v["idx"].as_u64().unwrap_or(0) as u32, v["j"].as_u64().unwrap_or(0) as u16);
                let end = v["en0"].as_f64().map_or(trig.0 + MIN_WIN, |e| (e / pl::SMS).floor().max(0.0) as u64);
                self.arm(src, v["w"].as_u64().unwrap_or(0), src.to_string(), true, mint, whale, v["bal"].as_i64().unwrap_or(0), trig, end);
            }
            "presend_fill" | "presend_wide_fill" => {
                let x = &v["x"];
                let at = match (x["slot"].as_u64(), x["idx"].as_u64()) { (Some(s), Some(i)) => (s, i as u32, x["j"].as_u64().unwrap_or(u16::MAX as u64) as u16), _ => return };
                let row = v["row"].as_str().map(|r| format!("{src}:{r}")).unwrap_or_else(|| src.to_string());
                self.fill(src, "shadow_fill", v["w"].as_u64().unwrap_or(0), row, at, true);
            }
            _ => {}
        }
    }

    pub fn status(&self) -> String {
        let s = &self.st;
        let pct = |a: u64, b: u64| if b == 0 { "-".to_string() } else { format!("{:.0}%", a as f64 * 100.0 / b as f64) };
        format!(" | WHALE SOLD LOG: tracks {} (open {}) sells {} (pre-exec {}) closed {}: 1st sell {} >=25% {} >=50% {} 100% {} | fills {} (whale >=50% sold before {}) would-fills {} (>=50% {})",
            s.tracks, self.tracks.len(), s.sells, pct(s.sells_pre, s.sells), s.closed, pct(s.closed - s.never, s.closed), pct(s.c25, s.closed), pct(s.c50, s.closed), pct(s.c100, s.closed),
            s.fills, s.fills50, s.sh_fills, s.sh_fills50)
    }

    pub fn finish(&mut self) -> serde_json::Value {
        let open = std::mem::take(&mut self.tracks);
        let n_open = open.len();
        for t in open { self.close(t); }
        let s = &self.st;
        serde_json::json!({"mode": "log", "tracks": s.tracks, "closed_at_end": n_open, "arms": s.arms, "arms_untracked": s.arms_untracked, "sells": s.sells, "sells_pre_exec": s.sells_pre,
            "sells_backfill": s.sells_backfill, "tracks_with_sell": s.closed - s.never, "crossed25": s.c25, "crossed50": s.c50, "crossed100": s.c100,
            "fills": {"n": s.fills, "sold25": s.fills25, "sold50": s.fills50, "untracked": s.fills_untracked}, "would_fills": {"n": s.sh_fills, "sold25": s.sh_fills25, "sold50": s.sh_fills50}})
    }
}

fn sell_rec(t: &Track, w: &WTrade, feeds: &[String]) -> serde_json::Value {
    let a = t.at(w.pos, true);
    let ns = net_sold(a.sold, a.bought);
    serde_json::json!({"ev": "presend_live_whale_sold", "stage": "sell", "track": t.id, "w": t.arms.first().map(|a| a.1), "ws": t.arms_json(), "mint": b58(&t.mint),
        "whale": b58(&t.whale), "slot": w.pos.0, "idx": w.pos.1, "j": w.pos.2, "dslot": w.pos.0.saturating_sub(t.trig.0), "sold_tok": w.tok, "cum_sold_tok": a.sold,
        "cum_frac": frac(a.sold, t.bag), "net_frac": frac(ns, t.bag), "bag": t.bag, "t": w.t, "feed": w.feed, "feed_name": feeds.get(w.feed as usize),
        "pre": if w.backfill { serde_json::Value::Null } else { w.pre_t.is_some().into() }, "pre_t": w.pre_t, "pre_ms": w.pre_t.map(|p| (w.t as i64 - p as i64) as f64 / 1e6),
        "backfill": w.backfill})
}

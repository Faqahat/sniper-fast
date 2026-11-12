// =====================================================================================================================
// dip50 GRX = RIVAL-AHEAD EARLY EXIT (T2 lane; --presend-live-grx on, default off = dip49c byte for byte).
// Why (grouprisk2 m5_entrants.py / m8_exit.py, rule "G2 entrant risk", Ln_g >= 2.245): when our T2 buy lands and fast-selling holders who
// bought AFTER the trigger are already in (rival dip bots ahead of us), holding 4-6 slots loses; selling 1 slot after the fill gained
// +1.3..+1.6 SOL on 64 flagged fills in the exit sim, and the same early exit on unflagged fills loses.
// THE RULE (once per position, at the moment the main loop registers our fill: the dip30 landing annotation's holder state, the detector
// has not taken our buy yet):
//   candidates = the annotation's set: Detector::holder_clocks(mint, >= 2% of supply, ours out, at the fill slot, top 12 by holding)
//   ENTRANT MEMBER = wallet != the window's trigger whale AND risk >= 5 AND hz3 >= 0.3 (the annotation's per-holder numbers at its hold
//                    age) AND hold age <= fill slot - trigger slot (its first buy of the token at / after the trigger's slot)
//   ent_pct = the members' holdings summed (% of supply, the annotation's order); FLAG when ent_pct >= grx_pct (2.245)
//   old_pct = the same clock test on non-whale holders that held BEFORE the trigger; whale_pct / whale_member: the trigger whale's own
// LANE: flags and acts on T2 fills only (kind t2). Re-arm fills: the numbers are computed and logged, never acted on (trigger = the
// re-arm window's dumper / its trig_slot). Wide / QF2 / probe fills: nothing.
// MODES (hot keys in the dip47 control file; start values = the flags):
//   grx            log | live (log)    live: a flagged T2 position's timed exit = fill slot + grx_exit_slots ("grx" exit reason)
//   grx_pct        1..20 (2.245)       the threshold, % of supply
//   grx_exit_slots 1..5 (1)            N
// LIVE ACTION: tick() asks the regular timed exit first (time-ms / time-limit / wall), then this one: slot_now >= fill slot + N -> exit
// "grx". So it can only ADD an earlier exit; TP / SL (on the trade path) and every other exit are untouched and the earlier one wins.
// The sell is dip42's whole sell at the base price (not the cheap timer price, not lots: "grx" is not a timer reason).
// HOT PATH: computed on the main loop from the detector's in-memory holder book + hold clocks (one holder_clocks call per fill, the one
// the annotation makes). Nothing on the sender thread, no RPC, no lock. Holder state missing / stale -> fail open (no flag, "skip": why).
// RECORDS: presend_live_fill "grx" {...}; one line per flagged fill; presend_live_realized "grx" {flag, ent_pct, mode, applied, exit};
// presend_live_grx_path {w, mint, kind, flag, fill_slot, price_fill, per_slot [{dslot 0..5, price, buy_sol, sell_sol, us_sell_sol, n}]}
// for every evaluated fill (T2 + re-arm), closed when a slot > fill + 5 is seen: the price path for scoring without a tape (NOT closed
// at our exit: the path after our sell is the comparison). A separate record: presend_live_flow (dip48) is unchanged.
// LOG-ONLY EXTRAS on the fill's "grx" (coordinator 11-12; NEVER an exit in this version: only the entrant flag acts):
//   g0_pct / g0_would       the plain landing group risk WITH the trigger whale (= ann.grp_pct); t2 && g0_pct >= grx_pct
//   cas_pct / cas_members / cas_would   the dip43 A5 CASCADE set of the filling try at its signing (top 8 holders >= 0.5% by TRUE balance,
//                           ours out; needs --presend-live-cascade on, else cas_src "off"): its non-trigger members >= 1.5% at signing
//                           whose true balance fell by our landing; cas_pct = the summed fall (% of supply); t2 && cas_pct >= 5.0
//   trig_pct / small_would  the trigger's % of supply (T2: the whale's holding at its trigger; re-arm: the dump); t2 && trig_pct <= 6.25
//   whale_pct / whale_risk / whale_hz3 / whale_member   the trigger whale at our landing
//   hold_pct / hold_n / ra_hold30_would (re-arm fills only)   every holder >= 2% (ours out) at landing summed; rearm && hold_pct >= 30
// POSITION MARKS: presend_live_grx_marks {w, mint, kind, flag, fill_slot, tokens, spend, sold_at_dslot, marks [{dslot 0 | 1 | 2 | 5, out,
//   vsol, vtok, buyers, buy_sol, sell_sol}]}: at the END of slot fill + d, what selling this fill's ACTUAL tokens on the curve state then
//   returns (lamports, after the trade fee, before tx fees); buyers / buy_sol / sell_sol = outside wallets, cumulative after our buy
//   through that slot. A position sold earlier still gets the marks, as if the tokens were held: our own sell is IN that curve state
//   (sold_at_dslot = the slot offset of our first sell seen, null = none in the window). Written with the path (slot > fill + 5 seen, or
//   5 s after the fill: then only the marks whose slot has ended).
// =====================================================================================================================
use super::*;

pub const FLAG: &str = "--presend-live-grx";
pub const FLAG_MODE: &str = "--presend-live-grx-mode";
pub const FLAG_PCT: &str = "--presend-live-grx-pct";
pub const FLAG_SLOTS: &str = "--presend-live-grx-exit-slots";
pub const THR: f64 = 2.245;
pub const EXIT_SLOTS: u64 = 1;
/// the candidates: >= 2% of supply, at most 12 (the annotation's)
pub const MIN_FRAC: f64 = 0.02;
pub const TOP: usize = 12;
pub const RISK_MIN: u32 = 5;
pub const HZ_MIN: f32 = 0.3;
/// the price path: slots fill .. fill + 5
pub const PATH_SLOTS: u64 = 5;
/// the exit reason of a GRX exit
pub const WHY: &str = "grx";

pub fn pct_parse(s: &str) -> std::result::Result<f64, String> {
    s.trim().parse::<f64>().ok().filter(|x| x.is_finite() && (1.0..=20.0).contains(x)).ok_or_else(|| format!("'{s}': % of supply 1..20"))
}
pub fn slots_parse(s: &str) -> std::result::Result<u64, String> {
    s.trim().parse::<u64>().ok().filter(|n| (1..=5).contains(n)).ok_or_else(|| format!("'{s}': slots 1..5"))
}

#[derive(Clone, Debug, PartialEq)]
pub struct Member { pub w: Pk, pub pct: f64, pub age: u64, pub risk: u32, pub hz3: f32 }

/// the rule's numbers on one landing state
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Verdict {
    pub ent_pct: f64, pub members: Vec<Member>,
    /// the plain landing group risk, the trigger whale counted (= the annotation's grp_pct, bit for bit)
    pub g0_pct: f64,
    /// clock-risky non-whale holders that held before the trigger (same thresholds)
    pub old_pct: f64, pub old_n: usize,
    /// the trigger whale itself meets risk / hz3 (among the candidates)
    pub whale_member: bool,
}

/// a holder's clock test (the annotation's group test)
pub fn risky(h: &pl::HolderClock) -> bool { h.risk >= RISK_MIN && h.hz3 >= HZ_MIN }

/// THE RULE on the annotation's holders `hc` (>= 2%, ours out, top 12, largest first): `whale` = the window's trigger whale, `since` =
/// fill slot - trigger slot. The sums run in the holders' order from 0.0 (the research script's `sum()` on the logged values: bit-equal)
pub fn eval(hc: &[pl::HolderClock], whale: &Pk, since: u64) -> Verdict {
    let mut v = Verdict { g0_pct: hc.iter().filter(|h| risky(h)).map(|h| h.bal as f64 / pl::SUPPLY * 100.0).sum(), ..Default::default() };
    for h in hc {
        if !risky(h) { continue; }
        if h.w == *whale { v.whale_member = true; continue; }
        let pct = h.bal as f64 / pl::SUPPLY * 100.0;
        if h.age <= since { v.ent_pct += pct; v.members.push(Member { w: h.w, pct, age: h.age, risk: h.risk, hz3: h.hz3 }); }
        else { v.old_pct += pct; v.old_n += 1; }
    }
    v
}
pub fn flagged(ent_pct: f64, thr: f64) -> bool { ent_pct >= thr }

/// the timed exit GRX adds: Some("grx") once slot_now reached fill slot + n (asked AFTER the regular timed exit: never later than it)
pub fn due(slot_now: u64, land_slot: u64, n: u64) -> Option<&'static str> { (slot_now >= land_slot + n).then_some(WHY) }

/// log-only thresholds of the extras
pub const CAS_MIN_PCT: f64 = 1.5;
pub const CAS_WOULD: f64 = 5.0;
pub const SMALL_TRIG: f64 = 6.25;
pub const RA_HOLD: f64 = 30.0;
/// the marks' slot offsets; a path / marks tracker lives at most this long on the wall clock
pub const MARKS: [u64; 4] = [0, 1, 2, 5];
pub const PATH_MAX: Duration = Duration::from_secs(5);

/// the CASCADE extra on a signing set `(wallet, true balance at signing, is the trigger)` and the balances now: the non-trigger members
/// >= 1.5% of supply at signing whose balance fell -> (the summed fall in % of supply, [(wallet, sign %, land %)])
pub fn cascade(set: &[(Pk, u64, bool)], now: impl Fn(&Pk) -> u64) -> (f64, Vec<(Pk, f64, f64)>) {
    let pct = |x: u64| x as f64 / pl::SUPPLY * 100.0;
    let mut m = Vec::new();
    let mut tot = 0.0;
    for (w, s, trig) in set {
        if *trig || pct(*s) < CAS_MIN_PCT { continue; }
        let l = now(w);
        if l < *s { tot += pct(*s - l); m.push((*w, pct(*s), pct(l))); }
    }
    (tot, m)
}

/// what selling `tokens` on the curve (vsol, vtok) returns after the trade fee `fr` (lamports; before tx fees)
pub fn mark_out(vsol: u64, vtok: u64, tokens: u64, fr: f64) -> u64 { (arbx::dip::sell_sol_out(vsol, vtok, tokens) as f64 * (1.0 - fr)).floor() as u64 }

#[derive(Clone, Copy, Debug, Default)]
pub struct PSlot { pub buy: u64, pub sell: u64, pub us_sell: u64, pub n: u32, pub price: f64, /// the curve after the slot's last trade (0: none in it)
    pub vsol: u64, pub vtok: u64, /// outside buyers first seen in this slot
    pub new_buyers: u32 }

/// one evaluated fill's price path (slots fill .. fill + 5, the trades after our buy)
#[derive(Clone, Debug)]
pub struct Path { pub w: u64, pub mint: Pk, pub kind: &'static str, pub flag: bool, pub fill: (u64, u32, i32), pub price0: f64, pub s: [PSlot; 6],
    /// the marks: this fill's tokens and SOL in, the curve right after our buy, the fee rate, the outside buyers so far, our first sell's
    /// slot offset, the fill's wall time
    pub tokens: u64, pub spend: u64, pub v0: (u64, u64), pub fr: f64, pub buyers: Vec<Pk>, pub sold_at: Option<u64>, pub at: Instant }

impl Path {
    pub fn new(w: u64, kind: &'static str, flag: bool, t: &pl::Trade) -> Path {
        Path { w, mint: t.mint, kind, flag, fill: t.pos(), price0: t.p(), s: [PSlot::default(); 6], tokens: t.tok, spend: t.sol, v0: (t.vsol, t.vtok), fr: t.fr(), buyers: Vec::new(),
            sold_at: None, at: Instant::now() }
    }
    pub fn add_trade(&mut self, t: &pl::Trade, ours: bool) -> bool {
        if !self.add(t.pos(), ours, t.buy, t.sol, t.p()) { return false; }
        let d = t.s - self.fill.0;
        let s = &mut self.s[d as usize];
        (s.vsol, s.vtok) = (t.vsol, t.vtok);
        if ours { if !t.buy && self.sold_at.is_none() { self.sold_at = Some(d); } }
        else if t.buy && !self.buyers.contains(&t.user) && self.buyers.len() < 256 { self.buyers.push(t.user); s.new_buyers += 1; }
        true
    }
    pub fn add(&mut self, pos: (u64, u32, i32), ours: bool, buy: bool, sol: u64, price: f64) -> bool {
        if pos <= self.fill || pos.0 > self.fill.0 + PATH_SLOTS { return false; }
        let s = &mut self.s[(pos.0 - self.fill.0) as usize];
        if ours { if !buy { s.us_sell += sol; } } else if buy { s.buy += sol; } else { s.sell += sol; }
        s.n += 1;
        s.price = price;
        true
    }
    /// the marks of the slots that have ended (`slot_now` > fill + d): the curve after the last trade at or before the end of fill + d
    pub fn marks_json(&self, slot_now: u64, closed: &str) -> serde_json::Value {
        let r = |x: u64| (x as f64 / 1e9 * 1e6).round() / 1e6;
        let mut cur = self.v0;
        let (mut nb, mut buy, mut sell) = (0u32, 0u64, 0u64);
        let mut ms = Vec::new();
        for (d, s) in self.s.iter().enumerate() {
            if s.vtok > 0 { cur = (s.vsol, s.vtok); }
            nb += s.new_buyers; buy += s.buy; sell += s.sell;
            if MARKS.contains(&(d as u64)) && slot_now > self.fill.0 + d as u64 {
                ms.push(serde_json::json!({"dslot": d, "out": mark_out(cur.0, cur.1, self.tokens, self.fr), "vsol": cur.0, "vtok": cur.1, "buyers": nb, "buy_sol": r(buy), "sell_sol": r(sell)}));
            }
        }
        serde_json::json!({"ev": "presend_live_grx_marks", "w": self.w, "mint": b58(&self.mint), "kind": self.kind, "flag": self.flag, "fill_slot": self.fill.0, "tokens": self.tokens,
            "spend": self.spend, "sold_at_dslot": self.sold_at, "marks": ms, "closed": closed})
    }
    pub fn json(&self, closed: &str) -> serde_json::Value {
        let r = |x: u64| (x as f64 / 1e9 * 1e6).round() / 1e6;
        let mut last = self.price0;
        let ps: Vec<serde_json::Value> = self.s.iter().enumerate().map(|(d, s)| {
            if s.price > 0.0 { last = s.price; }
            serde_json::json!({"dslot": d, "price": last, "buy_sol": r(s.buy), "sell_sol": r(s.sell), "us_sell_sol": r(s.us_sell), "n": s.n})
        }).collect();
        serde_json::json!({"ev": "presend_live_grx_path", "w": self.w, "mint": b58(&self.mint), "kind": self.kind, "flag": self.flag, "fill_slot": self.fill.0, "fill_idx": self.fill.1,
            "price_fill": self.price0, "per_slot": ps, "closed": closed})
    }
}

/// the main loop's GRX state (PsLive::grx; None = the flag off)
#[derive(Default)]
pub struct Grx {
    /// live-flagged open positions: pid -> N (the exit at fill slot + N)
    pub px: FxHashMap<u64, u64>,
    /// per window: the realized record's compact verdict
    pub done: FxHashMap<u64, serde_json::Value>,
    done_q: VecDeque<u64>,
    pub paths: FxHashMap<Pk, Vec<Path>>,
    /// per armed window: the trigger's % of supply (the fill record's trig_pct)
    pub trig: FxHashMap<u64, f64>,
    trig_q: VecDeque<u64>,
    /// evaluated T2 fills, flagged T2 fills, live exits made ("grx" reason), live-armed positions, re-arm fills evaluated / over the
    /// threshold (log only), fail-open fills
    pub fills: u64, pub flagged: u64, pub live_exits: u64, pub armed: u64, pub ra_fills: u64, pub ra_over: u64, pub fail_open: u64,
}

impl Grx {
    pub fn note_trig(&mut self, w: u64, pct: f64) {
        if self.trig.insert(w, pct).is_none() { self.trig_q.push_back(w); }
        while self.trig_q.len() > 4096 { if let Some(o) = self.trig_q.pop_front() { self.trig.remove(&o); } }
    }
    fn keep(&mut self, w: u64, j: serde_json::Value) {
        if self.done.insert(w, j).is_none() { self.done_q.push_back(w); }
        while self.done_q.len() > 4096 { if let Some(o) = self.done_q.pop_front() { self.done.remove(&o); } }
    }
}

impl PsLive {
    /// (live, threshold, N) now (the hot keys; the start flags without a control file)
    pub(super) fn grx50_vals(&self) -> (bool, f64, u64) {
        self.f47.cur.map_or((self.cfg.grx_live, self.cfg.grx_pct, self.cfg.grx_slots), |v| (v.grx_live, v.grx_pct, v.grx_slots))
    }

    /// our fill of window `att.w` (fill_inner, before the detector takes our buy): the fill record's "grx" and, for a flagged T2 fill in
    /// live mode that opens a position, Some(N) = arm the exit at fill slot + N. None, None: not a T2 / re-arm fill (nothing logged)
    pub(super) fn grx50_fill(&mut self, att: &Att, t: &pl::Trade, opens: bool) -> (Option<serde_json::Value>, Option<u64>) {
        if self.grx.is_none() { return (None, None); }
        let kind = self.g47_kind(att.w);
        if kind != "t2" && kind != "rearm" { return (None, None); }
        let t2 = kind == "t2";
        let (live, thr, n) = self.grx50_vals();
        let mode = if live { "live" } else { "log" };
        // fail open: no window (no trigger), a fill before its trigger slot, the token not in the holder book, the feed blind (a stale book)
        let win = self.wins.get(&att.w).map(|w| (w.whale, w.trig_slot));
        let skip = match win {
            None => Some("no_window"),
            Some((_, ts)) if ts == 0 || t.s < ts => Some("no_trigger_slot"),
            _ if !self.det.followed(&t.mint) => Some("no_holder_book"),
            _ if !self.det.track => Some("no_hold_clocks"),
            _ if self.d43.blind.is_some() => Some("feed_blind"),
            _ => None,
        };
        if let Some(why) = skip {
            let g = self.grx.as_mut().unwrap();
            g.fail_open += 1;
            g.keep(att.w, serde_json::json!({"mode": mode, "flag": false, "skip": why, "applied": false}));
            self.line(format!("  PRESEND LIVE GRX ({mode}) w{} {}: NOT evaluated ({why}): no flag, the exit as usual{}", att.w, b58(&t.mint), if t2 { "" } else { " [rearm]" }));
            return (Some(serde_json::json!({"mode": mode, "thr": thr, "kind": kind, "skip": why, "would_exit": false, "exit_slots": n, "applied": false})), None);
        }
        let (whale, trig_slot) = win.unwrap();
        let since = t.s - trig_slot;
        // every holder >= 2% (ours out), largest first; the rule's candidates = the first 12 (the annotation's call, same order)
        let all = self.det.holder_clocks(&t.mint, (MIN_FRAC * pl::SUPPLY) as i64, &self.user, t.s, 256);
        let hc = &all[..all.len().min(TOP)];
        let v = eval(hc, &whale, since);
        let whale_pct = self.det.bal(&t.mint, &whale) as f64 / pl::SUPPLY * 100.0;
        // ---- log-only extras (never an exit) ----
        let wc = self.det.holder_clock(&t.mint, &whale, t.s).filter(|h| h.bal > 0);
        let trig_pct = self.grx.as_ref().and_then(|g| g.trig.get(&att.w).copied());
        let cas = self.d43.sigset.get(&att.sig).map(|(_, s)| {
            let b = self.d43.book.as_ref();
            cascade(s, |w| b.and_then(|b| b.true_balance(&t.mint, w)).unwrap_or(0))
        });
        let hold_pct: f64 = all.iter().map(|h| h.bal as f64 / pl::SUPPLY * 100.0).sum();
        let over = flagged(v.ent_pct, thr);
        // the lane: T2 only; a re-arm fill never flags / acts
        let would = t2 && over;
        let applied = would && live && opens;
        let g = self.grx.as_mut().unwrap();
        if t2 { g.fills += 1; if would { g.flagged += 1; } if applied { g.armed += 1; } } else { g.ra_fills += 1; if over { g.ra_over += 1; } }
        g.keep(att.w, serde_json::json!({"mode": mode, "flag": would, "ent_pct": v.ent_pct, "applied": applied}));
        if g.paths.len() > 4096 { g.paths.clear(); }
        g.paths.entry(t.mint).or_default().push(Path::new(att.w, kind, would, t));
        let members: Vec<serde_json::Value> = v.members.iter().map(|m| serde_json::json!({"w": b58(&m.w), "pct": m.pct, "age": m.age, "risk": m.risk, "hz3": m.hz3})).collect();
        let mut j = serde_json::json!({"mode": mode, "thr": thr, "kind": kind, "since": since, "ent_pct": v.ent_pct, "ent_n": v.members.len(), "members": members, "old_pct": v.old_pct,
            "old_n": v.old_n, "whale_pct": whale_pct, "whale_member": v.whale_member, "would_exit": would, "exit_slots": n, "applied": applied});
        if !t2 { j["over"] = over.into(); }
        j["g0_pct"] = v.g0_pct.into();
        j["g0_would"] = (t2 && v.g0_pct >= thr).into();
        match &cas {
            Some((pct, m)) => {
                j["cas_src"] = "cascade43".into();
                j["cas_pct"] = (*pct).into();
                j["cas_members"] = m.iter().map(|(w, s, l)| serde_json::json!({"w": b58(w), "sign_pct": s, "land_pct": l})).collect::<Vec<_>>().into();
                j["cas_would"] = (t2 && *pct >= CAS_WOULD).into();
            }
            None => { j["cas_src"] = (if self.cfg.c43.cascade { "no_set" } else { "off" }).into(); j["cas_pct"] = serde_json::Value::Null; j["cas_would"] = false.into(); }
        }
        j["trig_pct"] = trig_pct.map_or(serde_json::Value::Null, |p| p.into());
        j["small_would"] = (t2 && trig_pct.is_some_and(|p| p <= SMALL_TRIG)).into();
        j["whale_risk"] = wc.as_ref().map_or(serde_json::Value::Null, |h| h.risk.into());
        j["whale_hz3"] = wc.as_ref().map_or(serde_json::Value::Null, |h| h.hz3.into());
        if !t2 { j["hold_pct"] = hold_pct.into(); j["hold_n"] = all.len().into(); j["ra_hold30_would"] = (hold_pct >= RA_HOLD).into(); }
        if would && live && !opens { j["not_applied"] = "position_open".into(); }
        if would || (!t2 && over) {
            let ms = v.members.iter().map(|m| format!("{} {:.1}% age {} hz {:.2}", &b58(&m.w)[..8], m.pct, m.age, m.hz3)).collect::<Vec<_>>().join(", ");
            self.line(format!("  PRESEND LIVE GRX ({mode}) w{} {}: entrants {:.1}% ({}) [{ms}] -> {}", att.w, b58(&t.mint), v.ent_pct, v.members.len(),
                if !t2 { "re-arm: logged only".to_string() } else if applied { format!("EXIT at fill+{n}") } else if live { format!("would exit at fill+{n} (a position is open already: not applied)") }
                else { format!("would exit at fill+{n}") }));
        }
        (Some(j), applied.then_some(n))
    }

    /// the position `pid` this fill opened takes its GRX exit (live, flagged)
    pub(super) fn grx50_arm(&mut self, pid: u64, n: u64) {
        let Some(g) = self.grx.as_mut() else { return };
        if g.px.len() > 4096 { g.px.clear(); }
        g.px.insert(pid, n);
    }

    /// tick(): the GRX exit of an open position, asked after the regular timed exit said "not yet" (None: off / not flagged / not due)
    pub(super) fn grx50_due(&self, pid: u64, land_slot: u64, slot_now: u64) -> Option<&'static str> {
        let n = *self.grx.as_ref()?.px.get(&pid)?;
        due(slot_now, land_slot, n)
    }

    /// a trade the detector took (on_exec): the evaluated fills' price paths (one map lookup per trade; nothing with GRX off)
    pub(super) fn grx50_trade(&mut self, t: &pl::Trade) {
        let user = self.user;
        let Some(v) = self.grx.as_mut().and_then(|g| g.paths.get_mut(&t.mint)) else { return };
        for p in v.iter_mut() { p.add_trade(t, t.user == user); }
    }

    /// tick(): the paths whose fill + 5 passed (or 5 s on the wall clock): the path record and the marks
    pub(super) fn grx50_tick(&mut self, slot_now: u64) {
        let Some(g) = self.grx.as_mut() else { return };
        if g.paths.is_empty() { return; }
        let mut out = Vec::new();
        g.paths.retain(|_, v| {
            let mut keep = Vec::new();
            for p in v.drain(..) { if slot_now > p.fill.0 + PATH_SLOTS { out.push((p, "slot5")); } else if p.at.elapsed() >= PATH_MAX { out.push((p, "5s")); } else { keep.push(p); } }
            *v = keep;
            !v.is_empty()
        });
        out.sort_by_key(|p| p.0.w);
        for (p, why) in out { self.rec(p.json(why)); self.rec(p.marks_json(slot_now, why)); }
    }

    /// rec(): a "grx" exit is counted and leaves the open set; a realized record gets the window's compact verdict
    pub(super) fn grx50_on_rec(&mut self, v: &mut serde_json::Value) {
        let Some(g) = self.grx.as_mut() else { return };
        match v["ev"].as_str() {
            Some("presend_live_exit") => {
                let why = v["why"].as_str().unwrap_or("").to_string();
                if let Some(pid) = v["pid"].as_u64() { if g.px.remove(&pid).is_some() && why == WHY { g.live_exits += 1; } }
                if let Some(d) = v["w"].as_u64().and_then(|w| g.done.get_mut(&w)) { if d.get("exit").is_none() { d["exit"] = why.into(); } }
            }
            Some("presend_live_realized") => { if let Some(j) = v["w"].as_u64().and_then(|w| g.done.get(&w).cloned()) { v["grx"] = j; } }
            _ => {}
        }
    }

    pub(super) fn grx50_status(&self) -> String {
        self.grx.as_ref().map_or(String::new(), |g| format!(" | GRX fills {} flagged {} (live exits {}){}{}", g.fills, g.flagged, g.live_exits,
            if g.ra_fills > 0 { format!(" re-arm {} over {} (log)", g.ra_fills, g.ra_over) } else { String::new() }, if g.fail_open > 0 { format!(" fail-open {}", g.fail_open) } else { String::new() }))
    }
}

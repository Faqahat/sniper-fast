// =====================================================================================================================
// dip36 LOG-ONLY FP-NOBOT (owner OK 11-05 PKT; flatperfect study, ENGINE_SPEC.txt; the pure part: src/fpnb.rs). Behind
// --presend-fpnb-log on (OFF by default: off = nothing of it runs, no thread, no tap, no record changes). NEVER acted on: no arm, skip,
// attempt, send path or exit reads any of it.
//   * its OWN THREAD ("ps-fpnb"): the event loop only hands it messages (a channel send per trade / create / arm / attempt / fill / close /
//     shadow record; nothing is computed on the loop). The feed's failed txs come over the tap (src/feeds/mod.rs FAIL_TAP).
//   * per pre-send ARM (T2 and re-arm, after QUIET and every live check: the presend_live_arm record): the 133 arm inputs at the trigger
//     row, the send part at the arm slot -> a "presend_live_fpnb" record stage "arm" (score, seeds, thr, block, covered, warm, hist_h, the
//     bot list's version, the 153 inputs);
//   * per SEND SLOT t of the window's attempts (the attempts the sender registered): the 20 send inputs from data with slot <= t - 1 ->
//     stage "send" (score, block, the attempt numbers, the 20 inputs). Computed once the feed passed slot t (a 1-slot lag; log-only);
//     a dry run registers no attempt (no send stage);
//   * per FILL at slot F: the decided send t = F - 1 (data <= F - 2, as the study scored r55) -> stage "fill" (+ the 153 inputs): dipmon's
//     "fpnb" row counts these would-blocks with the positions' realized P&L;
//   * block = covered && warm && score >= thr[kind] (T2 0.38795783438873316, re-arm 0.5004509801610366); covered = the trigger row seen
//     and the token's history intact (no cap, no feed gap); warm = the feed up >= 30 min. Whale history (6 inputs) NaN until it covers 24 h
//     (--presend-fpnb-preload brings that in from minute one); the 1 / 5 / 30-min regime NaN until the feed covers the window.
//   * the bot list --presend-fpnb-bots FILE: re-read when its mtime changes (checked every 30 s); a failed / empty read keeps the last good
//     list (a presend_live_fpnb_bots record ok false); a file older than 36 h is logged stale (still used: it is the last good one).
//   * dip36 SKIP-2 per-send (--presend-skip2-log on, needs this log; ENGINE_SPEC_PERSEND.txt): the frozen logistic score on the same
//     records ("skip2": score, score_nf = the 4 failed-tx inputs missing, thr, skip = covered && score < thr, skip_nf; the arm stage also
//     "x2" = its 55 arm inputs). Its history (own results, arm / skip / disarm activity, the creator / whale / mint ledgers) comes from the
//     records the probe emits (PsLive::rec forwards skips and disarms) and the realized P&L; --presend-skip2-seed FILE seeds the ledgers.
//   * dip36 LIVE GATE (owner 11-05 PKT: FP-NOBOT live from run 56, both kinds; 3 h later the owner keeps it or goes back to log-only):
//     --presend-fpnb-live t2,rearm | t2 | rearm | off (default off) and --presend-fpnb-control FILE ({"live": ["t2", "rearm"]}, re-read every
//     ~10 s, overrides the flag; a bad file keeps the last good mode; every mode change is a presend_live_fpnb_mode record). For a live kind
//     each ARMED window gets a verdict (Gate) the FP thread keeps fresh: the score of the NEXT slot's send (data <= the feed's newest slot),
//     recomputed on every new slot and every trade of the token; the SENDER reads it with one atomic load per due attempt (gate_withhold):
//     block (covered && warm && score >= thr) for that slot -> the attempt is WITHHELD (not built, not sent: "fpnb_withheld"; a
//     presend_live_fpnb_withheld record); the window stays armed and its next sends are re-scored. FAIL OPEN: no verdict for the slot
//     (the FP thread behind, dead, or a scorer error), not covered, cold -> the attempt goes as normal (counted). A window's end writes
//     presend_live_fpnb_window (withheld sends, filled or not).
// =====================================================================================================================
use super::*;
use arbx::fpnb as fp;

/// the bot list's mtime check
const BOTS_CHECK: Duration = Duration::from_secs(30);
/// a bot list older than this is logged stale
const BOTS_STALE: Duration = Duration::from_secs(36 * 3600);
/// a pending send slot is scored once the feed passed it, or after this long
const SEND_WAIT: Duration = Duration::from_millis(1500);
/// windows kept for their sends / fills / closes
const WINS_CAP: usize = 4096;

pub enum FpMsg {
    Create(Pk, u64),
    Trade(Pk, fp::Row),
    Arm(Box<FpArm>),
    Send { w: u64, n: u32, slot: u64 },
    Fill { w: u64, pid: Option<u64>, mint: Pk, slot: u64 },
    Close(Box<FpClose>),
    Realized { pid: u64, pnl: i64, mint: Pk, w: u64, t: u64 },
    /// dip36 skip2: a presend_live_skip record (its time) / a presend_live_disarm record
    Skip(u64),
    Disarm { mint: Pk, w: u64, filled: bool },
    ShArm { w: u64, t: u64 },
    ShFill { w: u64, t: Option<u64> },
    ShExit { w: u64, val: Option<f64> },
    Fail(arbx::feeds::FailTx),
    /// dip36 live gate: a window ended (its presend_live_disarm record)
    End { w: u64, filled: bool, why: String },
    /// score every pending send now, then answer
    Flush(crossbeam_channel::Sender<()>),
}

pub struct FpArm { pub w: u64, pub rearm: bool, pub mint: Pk, pub s: u64, pub i: u32, pub whale: Pk, pub t0: u64, pub arm_slot: u64, pub creator: Option<Pk>, pub clk: u64,
    pub excl: Vec<Pk>, pub rec: serde_json::Value, pub en_slot: u64, pub gate: Option<Arc<Gate>> }

/// dip36 live gate: a window's verdict, written by the FP thread, read by the sender: (slot << 2) | (covered << 1) | block; 0 = none yet
#[derive(Debug, Default)]
pub struct Gate { pub v: AtomicU64, pub withheld: AtomicU64 }
impl Gate {
    pub fn set(&self, slot: u64, covered: bool, block: bool) { self.v.store((slot << 2) | ((covered as u64) << 1) | block as u64, Ordering::Release); }
}

/// dip36 live gate: the mode (bit 0 T2, bit 1 re-arm) and the counters [T2, re-arm]
#[derive(Debug, Default)]
pub struct GateShared { pub mode: AtomicU64, pub withheld: [AtomicU64; 2], pub passed: [AtomicU64; 2], pub open_stale: [AtomicU64; 2], pub open_err: AtomicU64,
    /// dip37 --presend-fpnb-stale-hold N (0 = off): with no fresh verdict, hold a send whose window's last verdict blocked and is <= N slots old
    pub stale_hold: AtomicU64,
    /// dip37: the sends held that way [T2, re-arm]
    pub withheld_stale: [AtomicU64; 2] }

/// the mode of "t2,rearm" / "t2" / "rearm" / "off" (any order; "both" = t2,rearm)
pub fn mode_parse(s: &str) -> std::result::Result<u64, String> {
    let mut m = 0;
    for p in s.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
        m |= match p { "t2" | "T2" => 1, "rearm" => 2, "both" => 3, "off" => 0, x => return Err(format!("'{x}': t2 | rearm | t2,rearm | off")) };
    }
    Ok(m)
}
pub fn mode_str(m: u64) -> &'static str { match m & 3 { 0 => "off", 1 => "t2", 2 => "rearm", _ => "t2,rearm" } }

/// the SENDER's check for a due attempt of a window at `slot` (one atomic load): true = withhold it. A kind not live: false. A verdict for
/// `slot` or `slot + 1` (data up to slot - 1 / slot): its block; none (the FP thread behind or dead): fail open, counted
#[inline]
#[cfg_attr(not(test), allow(dead_code))]
pub fn gate_withhold(g: &Gate, gs: &GateShared, slot: u64, rearm: bool) -> bool { gate_withhold_why(g, gs, slot, rearm).is_some() }

/// gate_withhold with the reason: Some(false) = withheld on a fresh blocking verdict, Some(true) = dip37's STALE HOLD (no fresh verdict,
/// --presend-fpnb-stale-hold N > 0, the window's last verdict covered + blocked and at most N slots older than `slot`), None = sent. With
/// N = 0 exactly dip36's rule (no previous verdict / an old pass / an older block: fail open, counted open_stale)
#[inline]
pub fn gate_withhold_why(g: &Gate, gs: &GateShared, slot: u64, rearm: bool) -> Option<bool> {
    let k = rearm as usize;
    if gs.mode.load(Ordering::Relaxed) & (1 << k) == 0 { return None; }
    let v = g.v.load(Ordering::Acquire);
    let vs = v >> 2;
    if v == 0 || !(vs == slot || vs == slot + 1) {
        let n = gs.stale_hold.load(Ordering::Relaxed);
        if n > 0 && v & 3 == 3 && vs < slot && slot - vs <= n {
            g.withheld.fetch_add(1, Ordering::Relaxed);
            gs.withheld_stale[k].fetch_add(1, Ordering::Relaxed);
            return Some(true);
        }
        gs.open_stale[k].fetch_add(1, Ordering::Relaxed);
        return None;
    }
    if v & 1 == 1 && v & 2 == 2 { g.withheld.fetch_add(1, Ordering::Relaxed); gs.withheld[k].fetch_add(1, Ordering::Relaxed); return Some(false); }
    gs.passed[k].fetch_add(1, Ordering::Relaxed);
    None
}
pub struct FpClose { pub w: u64, pub pid: u64, pub mint: Pk, pub first: (u64, u64), pub first_t: u64, pub end: Option<(u64, u64)>, pub sell_t: u64 }

#[derive(Clone, Debug, Default, serde::Serialize)]
pub struct FpStats { pub arms: u64, pub arm_blocks: u64, pub arm_hits: u64, pub sends: u64, pub send_blocks: u64, pub fills: u64, pub fill_blocks: u64, pub fill_hits: u64,
    pub not_covered: u64, pub cold: u64, pub closes: u64, pub own_known: u64, pub reloads: u64, pub reload_fails: u64, pub list: serde_json::Value,
    pub preload: serde_json::Value, pub store: fp::StoreStats, pub fails_tapped: u64, pub fails_dropped: u64, pub compute_us_max: f64,
    pub skip2: serde_json::Value, pub s2_arm_skips: u64, pub s2_fills: u64, pub s2_fill_skips: u64, pub s2_fill_skips_nf: u64 }

struct WinCtx { ctx: fp::ArmCtx, creator: Option<Pk>, excl: Vec<Pk>, sent: FxHashMap<u64, Vec<u32>>, x2: Option<Vec<f64>>,
    /// dip36 live gate: the window's verdict (None: the gate is not built), still armed, its last slot, the last published (slot, block)
    gate: Option<Arc<Gate>>, active: bool, en_slot: u64, last_pub: (u64, bool) }

pub struct Worker {
    store: fp::Store,
    models: fp::Models,
    bots: fp::BotList,
    bots_path: String,
    bots_mtime: Option<std::time::SystemTime>,
    bots_checked: Instant,
    stale_logged: Option<Instant>,
    book: fp::Book,
    wins: FxHashMap<u64, WinCtx>,
    worder: VecDeque<u64>,
    pend: Vec<(u64, u64, Instant)>,
    closes: FxHashMap<u64, fp::OwnPos>,
    sh: FxHashMap<u64, Option<u64>>,
    sh_arm_t: FxHashMap<u64, u64>,
    out: crossbeam_channel::Sender<Out>,
    st: Arc<Mutex<FpStats>>,
    user: Pk,
    /// dip36 skip2 (None without --presend-skip2-log on)
    s2: Option<(fp::S2Model, fp::S2Hist)>,
    /// dip36 live gate: the shared mode / counters, the control file (path, mtime, last check)
    pub gs: Arc<GateShared>,
    ctl: Option<(String, Option<std::time::SystemTime>, Instant)>,
    /// tests: a threshold instead of the frozen one (the gate's tests force a block)
    #[cfg(test)]
    pub thr_test: Option<f64>,
}

fn kind(t2: bool) -> &'static str { if t2 { "T2" } else { "rearm" } }
fn r9(x: f64) -> f64 { (x * 1e9).round() / 1e9 }

impl Worker {
    pub fn new(bots_path: &str, bots: fp::BotList, user: Pk, out: crossbeam_channel::Sender<Out>, st: Arc<Mutex<FpStats>>) -> Result<Worker> {
        let models = fp::Models::frozen().map_err(|e| anyhow::anyhow!("FP-NOBOT models: {e}"))?;
        let mut ours = fp::ours();
        if !ours.contains(&user) { ours.push(user); }
        st.lock().unwrap().list = bots.meta();
        Ok(Worker { store: fp::Store::new(ours), models, bots, bots_path: bots_path.to_string(), bots_mtime: std::fs::metadata(bots_path).and_then(|m| m.modified()).ok(),
            bots_checked: Instant::now(), stale_logged: None, book: fp::Book::default(), wins: FxHashMap::default(), worder: VecDeque::new(), pend: Vec::new(),
            closes: FxHashMap::default(), sh: FxHashMap::default(), sh_arm_t: FxHashMap::default(), out, st, user, s2: None, gs: Arc::new(GateShared::default()), ctl: None,
            #[cfg(test)]
            thr_test: None })
    }
    fn rec(&self, v: serde_json::Value) { let _ = self.out.send(Out::Rec(v)); }
    fn line(&self, l: String) { let _ = self.out.send(Out::Line(l)); }

    /// the preload file (whale history 24 h, our earlier results, the shadow's): a record either way
    pub fn preload(&mut self, path: &str) {
        let r = std::fs::read(path).map_err(|e| e.to_string()).and_then(|b| fp::preload_parse(&b));
        let j = match r {
            Ok(p) => {
                let (nw, no, ns) = (p.wh.len(), p.own.len(), p.sh.len());
                self.store.preload_wh(p.wh, p.span);
                for o in p.own { self.book.add_own(o); }
                for (k, v) in p.sh { self.book.add_sh(k, v); }
                for t in p.sh_arms { self.book.add_sh_arm(t); }
                let h = (p.span.to.saturating_sub(p.span.from)) as f64 * fp::SLOT_S / 3600.0;
                self.line(format!("  FP-NOBOT (log) preload {path}: {nw} whale-history rows over {h:.1} h (slots {}..{}), {no} own results, {ns} shadow results", p.span.from, p.span.to));
                serde_json::json!({"ok": true, "path": path, "wh_rows": nw, "own": no, "shadow": ns, "from_slot": p.span.from, "to_slot": p.span.to, "hours": (h * 100.0).round() / 100.0, "head": p.head})
            }
            Err(e) => {
                self.line(format!("  FP-NOBOT (log) preload {path} NOT loaded: {e} (whale history warms up: its inputs stay missing for 24 h)"));
                serde_json::json!({"ok": false, "path": path, "err": e})
            }
        };
        self.rec(serde_json::json!({"ev": "presend_live_fpnb_preload", "preload": j}));
        self.st.lock().unwrap().preload = j;
    }

    /// the bot list: re-read when its mtime changed (checked every BOTS_CHECK); the last good list stays on a failure
    pub fn reload_check(&mut self, force: bool) {
        if !force && self.bots_checked.elapsed() < BOTS_CHECK { return; }
        self.bots_checked = Instant::now();
        let md = std::fs::metadata(&self.bots_path).and_then(|m| m.modified());
        let mt = match md { Ok(t) => t, Err(e) => { self.reload_fail(format!("stat: {e}")); return; } };
        if let Ok(age) = mt.elapsed() {
            if age > BOTS_STALE && self.stale_logged.is_none_or(|t| t.elapsed() > Duration::from_secs(6 * 3600)) {
                self.stale_logged = Some(Instant::now());
                self.rec(serde_json::json!({"ev": "presend_live_fpnb_bots", "ok": true, "stale": true, "age_h": age.as_secs_f64() / 3600.0, "path": self.bots_path, "list": self.bots.meta()}));
                self.line(format!("  FP-NOBOT (log) bot list {} is STALE ({:.1} h old): still used (last good)", self.bots_path, age.as_secs_f64() / 3600.0));
            }
        }
        if !force && Some(mt) == self.bots_mtime { return; }
        self.bots_mtime = Some(mt);
        let r = std::fs::read(&self.bots_path).map_err(|e| e.to_string()).and_then(|b| fp::BotList::parse(&b, &self.store.ours));
        match r {
            Ok(l) => {
                let old = self.bots.meta();
                self.bots = l;
                let mut st = self.st.lock().unwrap();
                st.reloads += 1;
                st.list = self.bots.meta();
                drop(st);
                self.rec(serde_json::json!({"ev": "presend_live_fpnb_bots", "ok": true, "path": self.bots_path, "list": self.bots.meta(), "was": old}));
            }
            Err(e) => self.reload_fail(e),
        }
    }
    fn reload_fail(&mut self, e: String) {
        self.st.lock().unwrap().reload_fails += 1;
        self.rec(serde_json::json!({"ev": "presend_live_fpnb_bots", "ok": false, "err": e, "path": self.bots_path, "kept": self.bots.meta()}));
        self.line(format!("  FP-NOBOT (log) bot list {} NOT reloaded ({e}): the last good list stays", self.bots_path));
    }

    pub fn handle(&mut self, m: FpMsg) {
        match m {
            FpMsg::Create(mint, s) => self.store.create(mint, s),
            FpMsg::Trade(mint, r) => {
                let m0 = self.store.max;
                self.store.trade(mint, r);
                // dip36 live gate: a new slot re-scores every armed window; a trade of an armed token re-scores its windows
                if self.gate_on() { if self.store.max != m0 { self.publish(None); } else { self.publish(Some(mint)); } }
            }
            FpMsg::End { w, filled, why } => self.end(w, filled, &why),
            FpMsg::Fail(f) => { self.store.fail(f.slot, f.idx as u32, f.payer, f.buy, &f.keys); }
            FpMsg::Arm(a) => self.arm(*a),
            FpMsg::Send { w, n, slot } => {
                if let Some(c) = self.wins.get_mut(&w) {
                    let v = c.sent.entry(slot).or_default();
                    if v.is_empty() { self.pend.push((w, slot, Instant::now())); }
                    v.push(n);
                }
            }
            FpMsg::Fill { w, pid, mint, slot } => self.fill(w, pid, mint, slot),
            FpMsg::Close(c) => self.close(*c),
            FpMsg::Realized { pid, pnl, mint, w, t } => {
                if let Some((_, h)) = self.s2.as_mut() { h.on_real(t, &b58(&mint), Some(w), pnl as f64 / 1e9); }
                if let Some(mut o) = self.closes.remove(&pid) {
                    o.pnl = pnl as f64 / 1e9;
                    self.book.add_own(o);
                    self.st.lock().unwrap().own_known += 1;
                }
            }
            FpMsg::ShArm { w, t } => { self.book.add_sh_arm(t); self.sh_arm_t.insert(w, t); if self.sh_arm_t.len() > 50_000 { self.sh_arm_t.clear(); self.sh.clear(); } }
            FpMsg::ShFill { w, t } => { self.sh.insert(w, t); }
            FpMsg::ShExit { w, val } => {
                // an item = a shadow arm with a row-c fill and a row-c exit; known at (fill t, or the arm's t) + 2 s
                if let (Some(v), Some(ft)) = (val, self.sh.remove(&w)) {
                    if let Some(k) = ft.or_else(|| self.sh_arm_t.get(&w).copied()) { self.book.add_sh(k + 2_000_000_000, v); }
                }
            }
            FpMsg::Skip(t) => { if let Some((_, h)) = self.s2.as_mut() { h.on_skip(t); } }
            FpMsg::Disarm { mint, w, filled } => { if let Some((_, h)) = self.s2.as_mut() { h.on_disarm(&b58(&mint), w, filled); } }
            FpMsg::Flush(ack) => { self.poll(true); let _ = ack.send(()); }
        }
    }

    fn arm(&mut self, a: FpArm) {
        let t0i = Instant::now();
        let t2 = !a.rearm;
        let mut x = fp::X::default();
        let mut ctx = self.store.arm_chain(&fp::ArmIn { t2, mint: a.mint, s: a.s, i: a.i, whale: a.whale }, &self.bots, &mut x);
        fp::arm_fields(&a.rec, t2, &mut x);
        self.book.feats(a.t0, &a.mint, Some(&a.whale), a.creator.as_ref(), &mut x);
        ctx.x = x.clone();
        // the send part at the arm slot
        self.store.send(&ctx, a.arm_slot, &self.bots, &mut x);
        let s = self.models.score(t2, &x);
        let nc = self.store.covered(&ctx);
        let block = nc.is_none() && ctx.warm && s.score >= s.thr;
        // dip36 skip2: the 55 arm inputs (the record + the history before this arm), then this arm into the history
        let x2 = self.s2.as_mut().map(|(_, h)| {
            let t2r = &a.rec;
            let tr = if t2 { &t2r["trig"] } else { &t2r["dump"] };
            let whale = tr[if t2 { "wallet" } else { "seller" }].as_str().unwrap_or("").to_string();
            let creator = t2r["ann"]["creator"].as_str().filter(|c| !c.is_empty()).map(|c| c.to_string());
            let mut v = fp::s2_arm_fields(t2r, a.clk);
            v.extend(h.feats(a.clk, &b58(&a.mint), &whale, creator.as_deref()));
            h.on_arm(a.clk, &b58(&a.mint), a.w, &whale, creator.as_deref());
            v
        });
        let s2j = x2.as_ref().map(|v| self.s2_json(t2, v, &x, nc.is_none()));
        let us = t0i.elapsed().as_secs_f64() * 1e6;
        {
            let mut st = self.st.lock().unwrap();
            if s2j.as_ref().is_some_and(|j| j["skip"] == true) { st.s2_arm_skips += 1; }
            st.arms += 1;
            if block { st.arm_blocks += 1; }
            if s.score >= s.thr { st.arm_hits += 1; }
            if nc.is_some() { st.not_covered += 1; }
            if !ctx.warm { st.cold += 1; }
            st.compute_us_max = st.compute_us_max.max(us);
        }
        let mut r = serde_json::json!({"ev": "presend_live_fpnb", "stage": "arm", "w": a.w, "mint": b58(&a.mint), "kind": kind(t2), "trig_slot": a.s, "trig_idx": a.i,
            "slot": a.arm_slot, "score": r9(s.score), "seeds": s.seeds.map(r9), "thr": s.thr, "hit": s.score >= s.thr, "block": block, "covered": nc.is_none(), "nc": nc,
            "warm": ctx.warm, "hist_h": (ctx.hist_h * 100.0).round() / 100.0, "wh_ok": ctx.wh_ok, "list": self.bots.meta(), "us": us.round(), "x": x.json()});
        if let (Some(j), Some(v)) = (s2j, x2.as_ref()) { r["skip2"] = j; r["x2"] = fp::nanj(v); }
        self.rec(r);
        if block {
            self.line(format!("  FP-NOBOT (log) w{} {} {} score {:.3} >= {:.3} at the arm -> would hold the sends", a.w, kind(t2), b58(&a.mint), s.score, s.thr));
        }
        self.wins.insert(a.w, WinCtx { ctx, creator: a.creator, excl: a.excl, sent: FxHashMap::default(), x2, gate: a.gate, active: true, en_slot: a.en_slot, last_pub: (0, false) });
        // dip36 live gate: the first verdict at once (the arm slot's send: the score above)
        if self.gate_on() { self.publish_w(a.w, a.arm_slot.max(self.store.max + 1)); }
        self.worder.push_back(a.w);
        while self.worder.len() > WINS_CAP { if let Some(o) = self.worder.pop_front() { self.wins.remove(&o); } }
    }

    /// dip36 live gate: any live kind
    fn gate_on(&self) -> bool { self.gs.mode.load(Ordering::Relaxed) != 0 }

    /// the frozen threshold (tests: an override)
    fn thr(&self, s: &fp::Score) -> f64 {
        #[cfg(test)]
        if let Some(t) = self.thr_test { return t; }
        s.thr
    }

    /// dip36 live gate: re-score the armed windows (of `mint`, or all) for the next slot's send (data <= the feed's newest slot)
    fn publish(&mut self, mint: Option<Pk>) {
        let t = self.store.max + 1;
        let ws: Vec<u64> = self.wins.iter().filter(|(_, c)| c.active && c.gate.is_some() && mint.is_none_or(|m| m == c.ctx.mint)).map(|(w, _)| *w).collect();
        for w in ws {
            if self.wins.get(&w).is_some_and(|c| t > c.en_slot + 2) { self.end(w, false, "expired_fp"); continue; }
            self.publish_w(w, t);
        }
    }

    fn publish_w(&mut self, w: u64, t: u64) {
        let Some((s, _, nc, x)) = self.at_send(w, t) else { return };
        let Some(c) = self.wins.get(&w) else { return };
        let Some(g) = c.gate.clone() else { return };
        let thr = self.thr(&s);
        let covered = nc.is_none();
        let block = covered && c.ctx.warm && s.score >= thr;
        let s_ok = s.score.is_finite();
        if !s_ok { self.gs.open_err.fetch_add(1, Ordering::Relaxed); g.set(t, false, false); return; }
        g.set(t, covered, block);
        let prev = c.last_pub;
        let (mint, t2) = (c.ctx.mint, c.ctx.t2);
        if let Some(c) = self.wins.get_mut(&w) { c.last_pub = (t, block); }
        // a record when a slot's verdict blocks (or flips): its score and the 20 send inputs
        if (block && prev.0 != t) || prev.1 != block {
            self.rec(serde_json::json!({"ev": "presend_live_fpnb", "stage": "gate", "w": w, "mint": b58(&mint), "kind": kind(t2), "slot": t, "score": r9(s.score), "thr": thr,
                "block": block, "covered": covered, "nc": nc, "live": self.gs.mode.load(Ordering::Relaxed) & (1 << (!t2) as u64) != 0, "xs": x.send_json()}));
        }
    }

    /// dip36 live gate: a window ended (disarmed / expired): its withheld sends and whether it filled
    fn end(&mut self, w: u64, filled: bool, why: &str) {
        let Some(c) = self.wins.get_mut(&w) else { return };
        if !c.active { return; }
        c.active = false;
        let Some(g) = c.gate.clone() else { return };
        let (mint, t2) = (c.ctx.mint, c.ctx.t2);
        g.v.store(0, Ordering::Release);
        let n = g.withheld.load(Ordering::Relaxed);
        self.rec(serde_json::json!({"ev": "presend_live_fpnb_window", "w": w, "mint": b58(&mint), "kind": kind(t2), "withheld": n, "filled": filled, "why": why,
            "mode": mode_str(self.gs.mode.load(Ordering::Relaxed))}));
    }

    /// dip36 live gate: the control file (every ~10 s; `force`: now): {"live": ["t2", "rearm"]}; a bad file keeps the mode
    pub fn ctl_check(&mut self, force: bool) {
        let Some((path, mt0, at)) = self.ctl.clone() else { return };
        if !force && at.elapsed() < Duration::from_secs(10) { return; }
        let mt = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
        if let Some(c) = self.ctl.as_mut() { c.2 = Instant::now(); }
        if !force && mt == mt0 { return; }
        if let Some(c) = self.ctl.as_mut() { c.1 = mt; }
        let r = std::fs::read(&path).map_err(|e| e.to_string()).and_then(|b| {
            let v: serde_json::Value = serde_json::from_slice(&b).map_err(|e| format!("bad JSON: {e}"))?;
            let a = v["live"].as_array().ok_or("no \"live\" list")?;
            mode_parse(&a.iter().map(|x| x.as_str().unwrap_or("?").to_string()).collect::<Vec<_>>().join(","))
        });
        match r {
            Ok(m) => self.set_mode(m, "control"),
            Err(e) => {
                self.rec(serde_json::json!({"ev": "presend_live_fpnb_mode", "ok": false, "err": e, "path": path, "mode": mode_str(self.gs.mode.load(Ordering::Relaxed)),
                    "t": arbx::feeds::clock::now_ns()}));
                self.line(format!("  FP-NOBOT control file {path} NOT read ({e}): the mode stays {}", mode_str(self.gs.mode.load(Ordering::Relaxed))));
            }
        }
    }

    pub fn set_mode(&mut self, m: u64, src: &str) {
        let old = self.gs.mode.swap(m, Ordering::SeqCst);
        if old == m { return; }
        self.rec(serde_json::json!({"ev": "presend_live_fpnb_mode", "ok": true, "mode": mode_str(m), "was": mode_str(old), "src": src, "t": arbx::feeds::clock::now_ns()}));
        self.line(format!("  FP-NOBOT LIVE GATE {} -> {} ({src})", mode_str(old), mode_str(m)));
        if m != 0 { self.publish(None); }
    }

    /// dip36 skip2: the record's "skip2" for the arm inputs `x2` and FP-NOBOT's inputs of this send
    fn s2_json(&self, t2: bool, x2: &[f64], x: &fp::X, covered: bool) -> serde_json::Value {
        let Some((m, _)) = self.s2.as_ref() else { return serde_json::Value::Null };
        let full = m.full(x2, x);
        let (sc, nf, thr) = (m.score(&full), m.score_nf(&full), m.thr(t2));
        serde_json::json!({"score": r9(sc), "score_nf": r9(nf), "thr": thr, "skip": covered && sc < thr, "skip_nf": covered && nf < thr})
    }

    /// the score of window w's send at slot t (data <= t - 1): (score, block, x)
    fn at_send(&self, w: u64, t: u64) -> Option<(fp::Score, bool, Option<&'static str>, fp::X)> {
        let c = self.wins.get(&w)?;
        let mut x = c.ctx.x.clone();
        self.store.send(&c.ctx, t, &self.bots, &mut x);
        let s = self.models.score(c.ctx.t2, &x);
        let nc = self.store.covered(&c.ctx);
        let block = nc.is_none() && c.ctx.warm && s.score >= s.thr;
        Some((s, block, nc, x))
    }

    /// pending send slots whose data is in (the feed passed slot t), or old enough; `all`: every one
    pub fn poll(&mut self, all: bool) {
        if self.pend.is_empty() { return; }
        let max = self.store.max;
        let (due, keep): (Vec<_>, Vec<_>) = std::mem::take(&mut self.pend).into_iter().partition(|(_, t, at)| all || max > *t || at.elapsed() > SEND_WAIT);
        self.pend = keep;
        for (w, t, _) in due {
            let Some((s, block, nc, x)) = self.at_send(w, t) else { continue };
            let c = &self.wins[&w];
            let ns = c.sent.get(&t).cloned().unwrap_or_default();
            {
                let mut st = self.st.lock().unwrap();
                st.sends += 1;
                if block { st.send_blocks += 1; }
            }
            let mut r = serde_json::json!({"ev": "presend_live_fpnb", "stage": "send", "w": w, "mint": b58(&c.ctx.mint), "kind": kind(c.ctx.t2), "slot": t, "n": ns,
                "score": r9(s.score), "thr": s.thr, "hit": s.score >= s.thr, "block": block, "covered": nc.is_none(), "nc": nc, "xs": x.send_json()});
            if let Some(x2) = c.x2.as_ref() { r["skip2"] = self.s2_json(c.ctx.t2, x2, &x, nc.is_none()); }
            self.rec(r);
        }
    }

    fn fill(&mut self, w: u64, pid: Option<u64>, mint: Pk, f: u64) {
        let Some((s, block, nc, x)) = self.at_send(w, f.saturating_sub(1)) else {
            self.rec(serde_json::json!({"ev": "presend_live_fpnb", "stage": "fill", "w": w, "pid": pid, "mint": b58(&mint), "fill_slot": f, "score": null, "block": false, "nc": "no_arm"}));
            return;
        };
        let c = &self.wins[&w];
        let withheld = c.gate.as_ref().map(|g| g.withheld.load(Ordering::Relaxed));
        let s2j = c.x2.as_ref().map(|x2| self.s2_json(c.ctx.t2, x2, &x, nc.is_none()));
        {
            let mut st = self.st.lock().unwrap();
            if let Some(j) = &s2j { st.s2_fills += 1; if j["skip"] == true { st.s2_fill_skips += 1; } if j["skip_nf"] == true { st.s2_fill_skips_nf += 1; } }
            st.fills += 1;
            if block { st.fill_blocks += 1; }
            if s.score >= s.thr { st.fill_hits += 1; }
        }
        let mut r = serde_json::json!({"ev": "presend_live_fpnb", "stage": "fill", "w": w, "pid": pid, "mint": b58(&mint), "kind": kind(c.ctx.t2), "fill_slot": f, "slot": f.saturating_sub(1),
            "score": r9(s.score), "seeds": s.seeds.map(r9), "thr": s.thr, "hit": s.score >= s.thr, "block": block, "covered": nc.is_none(), "nc": nc, "warm": c.ctx.warm,
            "hist_h": (c.ctx.hist_h * 100.0).round() / 100.0, "list": self.bots.meta(), "x": x.json()});
        if let Some(j) = s2j { r["skip2"] = j; }
        if let Some(n) = withheld { r["withheld"] = n.into(); }
        self.rec(r);
        if block {
            self.line(format!("  FP-NOBOT (log) w{w} {} FILL {} slot {f}: score {:.3} >= {:.3} at the deciding send -> would have been held", kind(c.ctx.t2), b58(&mint), s.score, s.thr));
        }
    }

    /// a closed position: its follower count from the store's rows (other wallets' buys after our first buy up to our last sell; not us, the
    /// T2 whale, the re-arm's holders); known at max(first buy + 3 s, last sell landing); into the book once its P&L is known
    fn close(&mut self, c: FpClose) {
        self.st.lock().unwrap().closes += 1;
        let (t2, whale, creator, excl) = match self.wins.get(&c.w) {
            Some(x) => (x.ctx.t2, Some(x.ctx.whale), x.creator, x.excl.clone()),
            None => (true, None, None, Vec::new()),
        };
        let end = c.end.unwrap_or((c.first.0 + 3, 1 << 30));
        let fol = self.store.rows_between(&c.mint, c.first, end).iter()
            .filter(|r| r.buy && r.user != self.user && !(t2 && Some(r.user) == whale) && !excl.contains(&r.user)).count();
        let k = (c.first_t + 3_000_000_000).max(c.sell_t);
        self.closes.insert(c.pid, fp::OwnPos { k, pnl: 0.0, fol: fol as f64, mint: c.mint, whale, creator });
        if self.closes.len() > 4096 { self.closes.clear(); }
    }

    /// tests: no warm-up and a forced threshold (the gate's tests need a block / a pass at will)
    #[cfg(test)]
    pub fn test_force(&mut self, thr: Option<f64>) { self.store.warm_slots = 0; self.thr_test = thr; }
    #[cfg(test)]
    pub fn set_ctl_for_test(&mut self, path: &str) { self.ctl = Some((path.to_string(), None, Instant::now())); }

    pub fn stats(&self) {
        let mut st = self.st.lock().unwrap();
        st.store = self.store.stats();
        st.fails_tapped = arbx::feeds::FAIL_TAP_SENT.load(Ordering::Relaxed);
        st.fails_dropped = arbx::feeds::FAIL_TAP_DROPPED.load(Ordering::Relaxed);
    }
}

/// the probe's side: the worker's thread (a run) or the worker itself (the tests: every message handled at once)
pub struct Fp { pub tx: Option<crossbeam_channel::Sender<FpMsg>>, pub inline: Option<Mutex<Box<Worker>>>, pub st: Arc<Mutex<FpStats>>, thread: Option<std::thread::JoinHandle<()>>,
    /// dip36: skip2 is on (PsLive::rec forwards its skip / disarm records)
    pub skip2: bool,
    /// dip36 live gate: the mode and counters (the sender reads them)
    pub gs: Arc<GateShared> }

impl Fp {
    /// with the flag on: the bot list read now (refused when bad: the run does not start), the thread with the preload and the tap
    pub fn start(cfg: &Cfg, user: Pk, out: &crossbeam_channel::Sender<Out>, inline: bool) -> Result<Option<Fp>> {
        if !cfg.fpnb_log { return Ok(None); }
        let path = cfg.fpnb_bots.clone().context("--presend-fpnb-log on needs --presend-fpnb-bots FILE")?;
        let b = std::fs::read(&path).with_context(|| format!("--presend-fpnb-bots {path}"))?;
        let bots = fp::BotList::parse(&b, &fp::ours()).map_err(|e| anyhow::anyhow!("--presend-fpnb-bots {path}: {e}"))?;
        let st = Arc::new(Mutex::new(FpStats::default()));
        let mut w = Worker::new(&path, bots, user, out.clone(), st.clone())?;
        // dip36 live gate: the start mode (the flag), then the control file (it overrides the flag; a bad file at the start: the flag's mode)
        w.gs.mode.store(cfg.fpnb_live, Ordering::SeqCst);
        // dip37: the stale hold (0 = off: dip36's fail-open)
        w.gs.stale_hold.store(cfg.fpnb_stale_hold, Ordering::SeqCst);
        if cfg.fpnb_stale_hold > 0 { eprintln!("DIP PRESEND LIVE FP-NOBOT STALE HOLD (dip37): no fresh verdict -> the send is held when the window's last verdict blocked and is <= {} slots old", cfg.fpnb_stale_hold); }
        if let Some(p) = &cfg.fpnb_control { w.ctl = Some((p.clone(), None, Instant::now())); w.ctl_check(true); }
        let gs = w.gs.clone();
        eprintln!("DIP PRESEND LIVE FP-NOBOT LIVE GATE: {} (control file {}){}", mode_str(gs.mode.load(Ordering::SeqCst)), cfg.fpnb_control.as_deref().unwrap_or("none"),
            if gs.mode.load(Ordering::SeqCst) != 0 { ": a send whose score blocks is WITHHELD (fail open when no fresh verdict)" } else { ": log only" });
        // dip36 skip2: the frozen per-send logit and its history (the ledgers seeded from --presend-skip2-seed; a bad seed refuses the start)
        if cfg.skip2_log {
            let m = fp::S2Model::frozen().map_err(|e| anyhow::anyhow!("skip2 model: {e}"))?;
            let mut h = fp::S2Hist::default();
            let seed = match &cfg.skip2_seed {
                Some(p) => { let n = h.seed(&std::fs::read(p).with_context(|| format!("--presend-skip2-seed {p}"))?).map_err(|e| anyhow::anyhow!("--presend-skip2-seed {p}: {e}"))?; serde_json::json!({"path": p, "keys": n}) }
                None => serde_json::Value::Null,
            };
            eprintln!("DIP PRESEND LIVE SKIP-2 PER-SEND LOG (dip36): logistic score on every FP-NOBOT record (T2 skip < {}, re-arm < {}), LOG ONLY | ledger seed {}",
                m.thr_t2, m.thr_rearm, cfg.skip2_seed.as_deref().unwrap_or("none (the ledgers start empty)"));
            st.lock().unwrap().skip2 = serde_json::json!({"on": true, "seed": seed, "thr_t2": m.thr_t2, "thr_rearm": m.thr_rearm});
            w.s2 = Some((m, h));
        }
        eprintln!("DIP PRESEND LIVE FP-NOBOT LOG (dip36): every pre-send arm / send slot / fill scored (T2 >= {}, re-arm >= {}), LOG ONLY | bots {path} ({} wallets, {} CORE, sha {}) | preload {}",
            fp::THR_T2, fp::THR_REARM, w.bots.n, w.bots.core.len(), w.bots.sha8, cfg.fpnb_preload.as_deref().unwrap_or("none (whale history warms up 24 h)"));
        if inline {
            if let Some(p) = &cfg.fpnb_preload { w.preload(p); }
            return Ok(Some(Fp { tx: None, inline: Some(Mutex::new(Box::new(w))), st, thread: None, skip2: cfg.skip2_log, gs }));
        }
        let (tx, rx) = crossbeam_channel::unbounded::<FpMsg>();
        let frx = arbx::feeds::fail_tap_on();
        if frx.is_none() { eprintln!("FP-NOBOT: the failed-tx tap was already on in this process (no failed txs here)"); }
        let pre = cfg.fpnb_preload.clone();
        let thread = std::thread::Builder::new().name("ps-fpnb".into()).spawn(move || {
            if let Some(p) = pre { w.preload(&p); }
            let never = crossbeam_channel::never();
            let frx = frx.unwrap_or(never);
            let mut last_stats = Instant::now();
            loop {
                crossbeam_channel::select! {
                    recv(rx) -> m => match m {
                        // a scorer panic never stops the run: the gate fails open (no fresh verdict) and it is counted
                        Ok(m) => { if std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| w.handle(m))).is_err() { w.gs.open_err.fetch_add(1, Ordering::Relaxed); } }
                        Err(_) => break,
                    },
                    recv(frx) -> f => { if let Ok(f) = f { w.handle(FpMsg::Fail(f)); } },
                    default(Duration::from_millis(100)) => {},
                }
                w.poll(false);
                w.reload_check(false);
                w.ctl_check(false);
                if last_stats.elapsed() > Duration::from_secs(10) { w.stats(); last_stats = Instant::now(); }
            }
            w.poll(true);
            w.stats();
        }).context("ps-fpnb thread")?;
        Ok(Some(Fp { tx: Some(tx), inline: None, st, thread: Some(thread), skip2: cfg.skip2_log, gs }))
    }

    pub fn send(&self, m: FpMsg) {
        if let Some(w) = self.inline.as_ref() { let mut w = w.lock().unwrap(); w.handle(m); w.poll(false); return; }
        if let Some(tx) = &self.tx { let _ = tx.send(m); }
    }

    /// the run's end: every pending send scored (<= 2 s), the summary
    pub fn finish(&mut self) -> serde_json::Value {
        if let Some(w) = self.inline.as_ref() { let mut w = w.lock().unwrap(); w.poll(true); w.stats(); }
        if let Some(tx) = self.tx.take() {
            let (a, r) = crossbeam_channel::bounded(1);
            let _ = tx.send(FpMsg::Flush(a));
            let _ = r.recv_timeout(Duration::from_secs(2));
            drop(tx);
            if let Some(h) = self.thread.take() {
                let t = Instant::now();
                while !h.is_finished() && t.elapsed() < Duration::from_secs(2) { std::thread::sleep(Duration::from_millis(10)); }
                if h.is_finished() { let _ = h.join(); }
            }
        }
        let mut j = serde_json::to_value(&*self.st.lock().unwrap()).unwrap_or_default();
        let g = &self.gs;
        let a = |x: &[AtomicU64; 2]| serde_json::json!({"t2": x[0].load(Ordering::Relaxed), "rearm": x[1].load(Ordering::Relaxed)});
        j["gate"] = serde_json::json!({"mode": mode_str(g.mode.load(Ordering::Relaxed)), "withheld": a(&g.withheld), "passed": a(&g.passed), "open_stale": a(&g.open_stale),
            "open_err": g.open_err.load(Ordering::Relaxed)});
        // dip37: only with the stale hold on
        let n = g.stale_hold.load(Ordering::Relaxed);
        if n > 0 { j["gate"]["stale_hold"] = n.into(); j["gate"]["withheld_stale"] = a(&g.withheld_stale); }
        j
    }

    /// dip36 skip2: a record the probe emits (its skips and disarms feed the history)
    pub fn on_rec(&self, v: &serde_json::Value) {
        match v["ev"].as_str() {
            Some("presend_live_skip") if self.skip2 => self.send(FpMsg::Skip(arbx::feeds::clock::now_ns())),
            Some("presend_live_disarm") => {
                let mint = v["mint"].as_str().and_then(fp::pk);
                if let (Some(mint), Some(w)) = (mint, v["w"].as_u64()) {
                    let filled = v["filled"].as_bool().unwrap_or(false);
                    self.send(FpMsg::End { w, filled, why: v["why"].as_str().unwrap_or("").to_string() });
                    if self.skip2 { self.send(FpMsg::Disarm { mint, w, filled }); }
                }
            }
            _ => {}
        }
    }

    pub fn status(&self) -> String {
        let st = self.st.lock().unwrap();
        let g = &self.gs;
        let l = |a: &[AtomicU64; 2]| format!("{}/{}", a[0].load(Ordering::Relaxed), a[1].load(Ordering::Relaxed));
        format!(" | FP-NOBOT({}) arms {} (would hold {}), fills {} (would block {}), not covered {}, list n={} | gate T2/re-arm: withheld {} passed {} open(stale) {} open(err) {}",
            match mode_str(g.mode.load(Ordering::Relaxed)) { "off" => "log", m => m }, st.arms, st.arm_blocks, st.fills, st.fill_blocks, st.not_covered, st.list["n"],
            l(&g.withheld), l(&g.passed), l(&g.open_stale), g.open_err.load(Ordering::Relaxed))
            // dip37: only with the stale hold on
            + &if g.stale_hold.load(Ordering::Relaxed) > 0 { format!(" withheld(stale<={}) {}", g.stale_hold.load(Ordering::Relaxed), l(&g.withheld_stale)) } else { String::new() }
    }
}

impl PsLive {
    /// dip36: a presend_live_arm (T2 or re-arm) -> the FP-NOBOT thread (nothing without the flag)
    #[allow(clippy::too_many_arguments)]
    pub(super) fn fpnb_arm(&mut self, w: u64, rearm: bool, mint: Pk, trig: &pl::Trade, whale: Pk, arm_slot: u64, excl: Vec<Pk>, rec: &serde_json::Value, en_slot: u64, gate: Option<Arc<Gate>>) {
        if self.fp.is_none() { return; }
        let creator = self.det.creator_bal(&mint).map(|c| c.0);
        let a = FpArm { w, rearm, mint, s: trig.s, i: trig.i, whale, t0: trig.t_rx, arm_slot, creator, clk: arbx::feeds::clock::now_ns(), excl, rec: rec.clone(), en_slot, gate };
        if let Some(f) = self.fp.as_ref() { f.send(FpMsg::Arm(Box::new(a))); }
    }

    /// dip36: a closed position -> its follower count and known time (the P&L follows with the realized lookup)
    pub(super) fn fpnb_close(&mut self, p: &PPos) {
        let Some(f) = self.fp.as_ref() else { return };
        let b0 = p.buys.iter().min_by_key(|b| (b.slot, b.idx));
        let first = b0.map(|b| (b.slot, b.idx)).unwrap_or((p.land.0, p.land.1));
        let first_t = b0.map(|b| b.t_rx).unwrap_or(p.land.2);
        let end = p.sell_lands.iter().map(|x| (x.0, x.1)).max();
        let sell_t = p.sell_lands.iter().map(|x| x.2).max().unwrap_or(0);
        f.send(FpMsg::Close(Box::new(FpClose { w: p.w, pid: p.pid, mint: p.mint, first, first_t, end, sell_t })));
    }

    /// dip36: the shadow's arm / row-c fill / row-c exit (s_* inputs)
    pub(super) fn fpnb_shadow(&mut self, rec: &serde_json::Value) {
        let Some(f) = self.fp.as_ref() else { return };
        let Some(w) = rec["w"].as_u64() else { return };
        match rec["ev"].as_str() {
            Some("presend_arm") => { if let Some(t) = rec["t"].as_u64() { f.send(FpMsg::ShArm { w, t }); } }
            Some("presend_fill") if rec["row"].as_str().unwrap_or("c") == "c" => f.send(FpMsg::ShFill { w, t: rec["m"]["t"].as_u64() }),
            Some("presend_exit") if rec["row"] == "c" => f.send(FpMsg::ShExit { w, val: rec["net_cheap"].as_f64() }),
            _ => {}
        }
    }
}

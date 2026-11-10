// =====================================================================================================================
// dip26 LIVE RE-ARM (owner 10-29 19:35 PKT "add re-arm in the engine"). The observatory's LOG-ONLY rule R0 (src/obs/rearm.rs,
// ops/strategies/presend/REARM2.md) as live pre-send windows. OFF unless --presend-live-rearm on: then `rm` is None and nothing of it
// runs (every record, line and tx is dip25's: the golden test, dip26_tests.rs). AMS run 37's paper (row c, 0.65 SOL, TP 20% / SL 20% /
// t200): 146 fills, +3.45 SOL after try fees in 12 h, +2.71 without the top 5; about +1.2 with 20% fewer followers (estimated).
//   * CANDIDATE: a single curve SELL of >= 6% of supply (tok >= 6e13) by any wallet but ours, on a token the live detector follows (seen
//     from its create, standard curve, not mayhem). Its post-sell curve must be < 100 SOL ("rearm_untradeable") and the token <= 141
//     slots old at the dump ("rearm_age"); both are presend_live_skip records ("kind":"rearm"). Other sells are not candidates.
//   * THE CLOCK: the executed feed's slot clock, as the observatory's (the newest slot of an executed pump tx: on_exec, before that
//     tx's creates and trades). "The end of slot dump + 2" = the first executed tx of a slot >= dump + 3.
//   * HOLDERS CHECK then: every wallet but ours holding >= 6% of supply (the detector's balances, since the create, arrival order),
//     largest first. None: no window ("rearm_no_holder"). Then, each a skip: the probe stopped / no new buys (kill switch, profit lock,
//     run end: "rearm_blocked_stopped"); a T2 window armed on the token ("rearm_blocked_live_armed"); a re-arm window armed on it
//     ("rearm_blocked_rearm_armed"); the reactive bot holds it ("rearm_blocked_reactive"); no / non-vanilla launch accounts
//     ("rearm_blocked_launch", as the T2 trigger); R5 (--presend-live-rearm-r5-skip on): all four QUIET arm signals of the LARGEST
//     holder ("rearm_r5"; during the QUIET arm rule's warm-up only "would_skip").
//   * DEFERRAL (never two fills on a token, never a double fill): our position open on the token (or its 300 ms margin), our token
//     account of it still open (kept open as the attempts' guard after a sell, or an UNSOLD retry), or an attempt of an earlier window
//     on it that can still land: the window WAITS ("presend_live_rearm_defer") and arms as soon as that clears, if it is still <= its
//     last slot (the arm record's "deferred_ms"). While it waits its stops run (the next >= 6% sell, no holder left, a T2 window arming
//     on the token, its last slot passing): it is then never armed ("rearm_blocked_position" / "rearm_blocked_ata_open" /
//     "rearm_blocked_inflight", with "ended").
//   * THE WINDOW: armed at once (no +50 ms: the paper's t_arm), last slot dump + 3 + G (--presend-live-rearm-gap-slots, 20); the T2
//     machinery for everything else: the sender's k tries per slot, limit = the latest price x (1 - drop) re-read on every trade,
//     deadline + 1, the same routes, senders, 40/s caps, rolling 24 h fee budget and one-position pause; the spend is
//     --presend-live-rearm-size-sol. It ends at the earliest of: its last slot ("expired"); 30 ms after the next >= 6% sell of the token
//     by anyone ("whale_dump"); 30 ms after the trade after which no wallet but ours holds >= 6% ("no_holder"); QUIET N:M
//     (--presend-live-rearm-quiet-stop, 6:2) on the same clock: at the first slot >= its arm slot + N, fewer than M trades by anyone but
//     us since the arm ("quiet"); a T2 window arming on the token ("superseded": it takes the token over); a fill ("filled"); the
//     stop ("stopped"); the token leaving the detector ("token_gone").
//   * FILL / EXIT: the pre-send position path unchanged (TP / SL / exit-ms / the slot limit, sell rounds, the kept-open account and its
//     close, realized from the chain txs, the run's end check). Only the size differs. Its records carry "kind":"rearm" (arm, skip,
//     defer, disarm, attempt, attempt_land, fill, late_fill, exit, sell_land, close, realized, orphan); the .log's FILL / EXIT / CLOSED /
//     REALIZED lines end with " [rearm]". T2 records are unchanged (no "kind").
// =====================================================================================================================
use super::*;
use std::sync::atomic::AtomicI64;

/// a ">= 6%" holder / sell (raw tokens): 6% of the supply (the observatory's BIG)
pub const RE_BIG: i64 = 60_000_000_000_000;
/// the age gate: 30 s on the study's 0.212 s slot clock
pub const RE_MAX_AGE: u64 = 141;
/// the holders check at the end of slot dump + 2 (the first slot >= dump + 3); the window's last slot = dump + RE_WAIT + G
pub const RE_WAIT: u64 = 3;
/// no candidate at a post-sell curve of 100 SOL or more (lamports)
pub const RE_UNTRADE: u64 = 100_000_000_000;
/// re-arm window ids kept for their spend (a late fill, a window's read): weeks of re-arm windows
const RE_IDS: usize = 65_536;

/// a candidate's dump: its trade (as the feed delivered it) and the token's age then (slots since its create)
#[derive(Clone, Debug)]
pub(super) struct RDump { pub tr: pl::Trade, pub age: u64 }

impl RDump {
    pub(super) fn json(&self) -> serde_json::Value {
        let t = &self.tr;
        serde_json::json!({"sig": bs58::encode(&t.sig).into_string(), "slot": t.s, "idx": t.i, "j": t.j, "t": t.t_rx, "seller": b58(&t.user), "sol": t.sol, "tok": t.tok,
            "pct": t.tok as f64 / pl::SUPPLY * 100.0, "drop_pct": (1.0 - t.p() / t.p_pre().max(1e-30)) * 100.0, "vsol": t.vsol, "vtok": t.vtok, "age_slots": self.age})
    }
}

/// holders as the records give them: [{w, pct}]
pub(super) fn holders_json(h: &[(Pk, i64)]) -> serde_json::Value {
    serde_json::json!(h.iter().map(|(k, b)| serde_json::json!({"w": b58(k), "pct": *b as f64 / pl::SUPPLY * 100.0})).collect::<Vec<_>>())
}
fn holders_short(h: &[(Pk, i64)]) -> String { h.iter().map(|(k, b)| format!("{} {:.1}%", &b58(k)[..8], *b as f64 / pl::SUPPLY * 100.0)).collect::<Vec<_>>().join(", ") }

/// a candidate waiting for its holders check
pub(super) struct RCand { pub mint: Pk, pub dump: RDump }

/// a checked window waiting for our position / token account on its token to clear (its stops run meanwhile)
pub(super) struct RDef { pub mint: Pk, pub dump: RDump, pub holders: Vec<(Pk, i64)>, pub launch: Launch, pub chk_slot: u64, pub chk_t: u64, pub at: Instant, pub why: &'static str,
    pub r5: Option<serde_json::Value>, pub en_slot: u64,
    /// dip38 PSM12-S1's view at the holders check (None with its log off)
    pub s1: Option<super::pss1::S1V> }

/// an armed re-arm window's own state (the probe's Win / SWin hold the rest)
pub(super) struct RWin { pub mint: Pk, pub dump_slot: u64, pub arm_slot: u64, pub en_slot: u64, pub others: u32, pub qdec: Option<bool>, pub stop: Option<&'static str>,
    pub deferred_ms: f64, pub n_holders: usize }

/// the re-arm's counters (status line, run_end)
#[derive(Default, Debug)]
pub(super) struct RStats {
    /// >= 6% sells of followed tokens (not ours), candidates, holders checks, windows armed, deferred at the check, armed after waiting,
    /// R5 would-skips during the QUIET warm-up
    pub sells6: u64, pub cands: u64, pub checks: u64, pub windows: u64, pub deferred: u64, pub deferred_armed: u64, pub r5_would: u64,
    pub skips: FxHashMap<&'static str, u64>, pub ends: FxHashMap<&'static str, u64>,
    /// attempts registered, their failed-attempt fees (lamports), fills, positions closed
    pub sent: u64, pub fees: u64, pub fills: u64, pub closed: u64,
}

/// the realized P&L of the pre-send positions by kind (lamports, counts): the async realized lookups add to it (dip26: only with re-arm on)
#[derive(Default, Debug)]
pub struct RzSplit { pub t2: AtomicI64, pub rearm: AtomicI64, pub n_t2: AtomicU64, pub n_rearm: AtomicU64 }

impl RzSplit {
    pub fn add(&self, rearm: bool, pnl: i64) {
        if rearm { self.rearm.fetch_add(pnl, Ordering::SeqCst); self.n_rearm.fetch_add(1, Ordering::SeqCst); }
        else { self.t2.fetch_add(pnl, Ordering::SeqCst); self.n_t2.fetch_add(1, Ordering::SeqCst); }
    }
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"t2": {"pnl": self.t2.load(Ordering::SeqCst), "n": self.n_t2.load(Ordering::SeqCst)},
            "rearm": {"pnl": self.rearm.load(Ordering::SeqCst), "n": self.n_rearm.load(Ordering::SeqCst)}})
    }
}

/// the re-arm state of the probe
pub(super) struct Rearm {
    pub cfg: RearmCfg,
    /// the executed feed's slot clock
    pub clock: u64,
    pub cands: Vec<RCand>,
    pub defer: Vec<RDef>,
    /// armed re-arm windows: window id -> its state
    pub wins: FxHashMap<u64, RWin>,
    /// every re-arm window id (bounded): its spend
    pub ids: FxHashMap<u64, u64>, ids_q: VecDeque<u64>,
    /// the latest curve state (vsol, vtok, fee rate, position) of tokens with a candidate / a waiting window: a window's first limit
    pub cur: FxHashMap<Pk, (u64, u64, f64, (u64, u32, i32))>,
    pub st: RStats,
    pub rz: Arc<RzSplit>,
}

impl Rearm {
    pub(super) fn new(cfg: RearmCfg) -> Rearm {
        Rearm { cfg, clock: 0, cands: Vec::new(), defer: Vec::new(), wins: FxHashMap::default(), ids: FxHashMap::default(), ids_q: VecDeque::new(), cur: FxHashMap::default(),
            st: RStats::default(), rz: Arc::new(RzSplit::default()) }
    }
    pub(super) fn is_win(&self, w: u64) -> bool { self.ids.contains_key(&w) }
    fn note_id(&mut self, id: u64) {
        self.ids.insert(id, self.cfg.spend);
        self.ids_q.push_back(id);
        while self.ids_q.len() > RE_IDS { if let Some(o) = self.ids_q.pop_front() { self.ids.remove(&o); } }
    }
    /// a re-arm window ended (disarm): its counters, its record's "rearm" part. None: not a re-arm window
    pub(super) fn end(&mut self, id: u64, why: &'static str) -> Option<serde_json::Value> {
        let w = self.wins.remove(&id)?;
        *self.st.ends.entry(why).or_default() += 1;
        Some(serde_json::json!({"dump_slot": w.dump_slot, "arm_slot": w.arm_slot, "en_slot": w.en_slot, "others": w.others, "quiet_stop": w.qdec, "stop": w.stop,
            "deferred_ms": w.deferred_ms, "holders": w.n_holders, "quiet": format!("{}:{}", self.cfg.stop.n, self.cfg.stop.m)}))
    }
    /// candidates and waiting windows (the status line)
    fn pending(&self) -> usize { self.cands.len() + self.defer.len() }
}

/// a launch the attempts cannot buy (the T2 trigger's own rule, shared): the reason
pub(super) fn launch_refusal(l: Option<&Launch>, allow_holder: bool) -> Option<&'static str> {
    match l {
        None => Some("no_launch_accounts"),
        Some(l) if !l.is_create_v2 => Some("legacy_create"),
        Some(l) if l.is_mayhem => Some("mayhem"),
        Some(l) if !(l.is_vanilla() || (allow_holder && l.is_holder_reward && !l.is_cashback && l.creator_fee_bps == 0)) => Some("non_vanilla"),
        _ => None,
    }
}

fn sorted(m: &FxHashMap<&'static str, u64>) -> String {
    let mut v: Vec<(&&str, &u64)> = m.iter().collect();
    v.sort();
    v.iter().map(|(k, n)| format!("{k} {n}")).collect::<Vec<_>>().join(", ")
}

impl PsLive {
    /// dip26: window `w` is a re-arm window
    pub(super) fn rearm_w(&self, w: u64) -> bool { self.rm.as_ref().is_some_and(|r| r.is_win(w)) }
    /// dip26: what an attempt of window `w` spends (the pre-send size; a re-arm window's own size)
    pub(super) fn w_spend(&self, w: u64) -> u64 {
        // dip41: a wide window's size (the WIDE-DUMPER tier live)
        if let Some((d, k)) = self.wd.as_ref().and_then(|d| d.wins.get(&w).map(|x| (d, x.0))) { return d.size_of(k); }
        self.rm.as_ref().and_then(|r| r.ids.get(&w).copied()).unwrap_or(self.cfg.spend)
    }
    /// dip26: an armed re-arm window's 30 ms stop reason (whale_dump / no_holder)
    pub(super) fn rearm_stop_why(&self, id: u64) -> Option<&'static str> { self.rm.as_ref().and_then(|r| r.wins.get(&id)).and_then(|w| w.stop) }
    /// no new window may arm: the probe stopped (caps, run end) or the engine takes no new buys (kill switch, profit lock, run end)
    fn rearm_halted(&self) -> bool { self.stopped.is_some() || DIP_NO_FIRE.load(Ordering::Relaxed) }
    /// what keeps a window from arming on `mint` now (it waits): our position on it, its 300 ms margin, our token account of it open (kept
    /// open after a sell as the attempts' guard, or an UNSOLD retry's), an attempt of an earlier window on it that can still land (its
    /// deadline, or its window's disarm bound, not passed: its fill would hold the token while this window tries)
    fn rearm_block(&self, mint: &Pk) -> Option<&'static str> {
        if self.pos.contains_key(mint) { Some("position") }
        else if self.free_at.get(mint).is_some_and(|f| Instant::now() < *f) { Some("margin") }
        else if self.atas.contains_key(mint) { Some("ata_open") }
        else if self.quiet.get(mint).is_some_and(|&q| q >= self.sh.cur_slot()) { Some("inflight") }
        else { None }
    }

    /// a re-arm skip record (and its count)
    fn rearm_skip(&mut self, why: &'static str, mint: &Pk, dump: &RDump, extra: serde_json::Value) {
        if let Some(rm) = self.rm.as_mut() { *rm.st.skips.entry(why).or_default() += 1; }
        let mut r = serde_json::json!({"ev": "presend_live_skip", "kind": "rearm", "why": why, "mint": b58(mint), "dump": dump.json()});
        // dip39 (only with the gate on): the depth now
        if let Some(j) = self.bd_json(mint, self.sh.slot.load(Ordering::Relaxed)) { r["botdepth"] = j; }
        // dip42 (log-only; only with the flag on): the 2NUM family on the token now
        if let Some(j) = self.f2_json(true, mint, self.sh.slot.load(Ordering::Relaxed)) { r["fam2"] = j; }
        if let (Some(o), serde_json::Value::Object(x)) = (r.as_object_mut(), extra) { for (k, v) in x { o.insert(k, v); } }
        self.rec(r);
    }

    /// a waiting window that will never arm: its skip record (the block it waited on, what ended it, how long it waited)
    fn rearm_defer_drop(&mut self, d: RDef, ended: &'static str) {
        let why = match d.why { "ata_open" => "rearm_blocked_ata_open", "inflight" => "rearm_blocked_inflight", _ => "rearm_blocked_position" };
        let mut x = serde_json::json!({"check_slot": d.chk_slot, "en_slot": d.en_slot, "holders": holders_json(&d.holders), "deferred": d.why,
            "deferred_ms": d.at.elapsed().as_secs_f64() * 1e3, "ended": ended});
        if let Some(j) = d.r5 { x["r5"] = j; }
        self.rearm_skip(why, &d.mint, &d.dump, x);
    }

    /// THE CLOCK (on_exec, before the tx's creates and trades): the executed feed reached `slot` (the first executed pump tx of it, at
    /// `t_rx`): the armed windows' QUIET stop and last slot, the waiting windows' last slot, the candidates' holders checks
    pub(super) fn rearm_slot(&mut self, slot: u64, t_rx: u64, launch_of: &dyn Fn(&Pk) -> Option<Launch>, reactive_open: &dyn Fn(&Pk) -> bool) {
        let Some(rm) = self.rm.as_mut() else { return };
        if slot <= rm.clock { return; }
        rm.clock = slot;
        let (n, m) = (rm.cfg.stop.n, rm.cfg.stop.m);
        let mut ends: Vec<(u64, &'static str, u32, Pk, u64)> = Vec::new();
        for (id, w) in rm.wins.iter_mut() {
            if w.qdec.is_none() && slot >= w.arm_slot + n {
                let stop = w.others < m;
                w.qdec = Some(stop);
                if stop { ends.push((*id, "quiet", w.others, w.mint, w.arm_slot)); continue; }
            }
            if slot > w.en_slot { ends.push((*id, "expired", w.others, w.mint, w.arm_slot)); }
        }
        ends.sort_by_key(|x| x.0);
        for (id, why, others, mint, arm_slot) in ends {
            if why == "quiet" {
                self.line(format!("  PRESEND LIVE REARM QUIET STOP w{id} {}: {others} other trade(s) since the arm by slot +{} (needs {m} by +{n}): no more attempts",
                    b58(&mint), slot.saturating_sub(arm_slot)));
            }
            self.disarm(id, why);
        }
        self.rearm_defer_sweep(slot);
        // the candidates due: their holders check, in arrival order
        let due: Vec<RCand> = match self.rm.as_mut() {
            Some(rm) => { let (a, b): (Vec<RCand>, Vec<RCand>) = std::mem::take(&mut rm.cands).into_iter().partition(|c| slot >= c.dump.tr.s + RE_WAIT); rm.cands = b; a }
            None => Vec::new(),
        };
        for c in due { self.rearm_check(c, slot, t_rx, launch_of, reactive_open); }
        if let Some(rm) = self.rm.as_mut() {
            let (cands, defer) = (&rm.cands, &rm.defer);
            rm.cur.retain(|k, _| cands.iter().any(|c| c.mint == *k) || defer.iter().any(|d| d.mint == *k));
        }
    }

    /// waiting windows past their last slot (on `clock`), on a token the detector left, or the probe stopped: never armed
    fn rearm_defer_sweep(&mut self, clock: u64) {
        let halted = self.rearm_halted();
        let Some(rm) = self.rm.as_mut() else { return };
        if rm.defer.is_empty() { return; }
        let det = &self.det;
        let (gone, keep): (Vec<RDef>, Vec<RDef>) = std::mem::take(&mut rm.defer).into_iter().partition(|d| halted || clock > d.en_slot || !det.followed(&d.mint));
        rm.defer = keep;
        for d in gone {
            let ended = if halted { "stopped" } else if !self.det.followed(&d.mint) { "token_gone" } else { "expired" };
            self.rearm_defer_drop(d, ended);
        }
    }

    /// THE HOLDERS CHECK of a candidate (the clock reached its dump slot + 3): a skip, a waiting window, or a window armed now
    fn rearm_check(&mut self, c: RCand, slot: u64, t_rx: u64, launch_of: &dyn Fn(&Pk) -> Option<Launch>, reactive_open: &dyn Fn(&Pk) -> bool) {
        let mint = c.mint;
        let holders = self.det.holders_at_least(&mint, RE_BIG, &self.user);
        let halted = self.rearm_halted();
        let armed = self.armed.get(&mint).copied();
        let armed_re = armed.is_some_and(|id| self.rearm_w(id));
        let launch = launch_of(&mint);
        let lwhy = launch_refusal(launch.as_ref(), self.allow_holder);
        // dip32 the creator gate (the check's own time)
        let (crw, crj) = if self.cfg.cr_on() { cr_gate(&self.sh, &self.cfg, self.det.creator_bal(&mint).map(|c| c.0), t_rx) } else { (None, None) };
        // dip36 LIVE blocklist: the dumper / a holder >= the threshold listed (nothing without the flag)
        let blh = if self.bl.is_some() { self.bl_hit(&mint, &c.dump.tr.user, "dumper", None) } else { None };
        // dip37 the whale / dumper ledger on the dumper (LIVE; None with it off)
        let whg = pswh::wh_gate(&self.sh, &self.cfg, &c.dump.tr.user, true);
        // dip37 the holder ledger on the remaining holders (the dumper excluded); the control file's modes ("log": logged, never a skip)
        let hlg = self.hl_gate(&mint, &c.dump.tr.user);
        let (wh_live, hl_live) = (self.hls.live[0], self.hls.live[1]);
        // dip37 HYBRID-2: the mint's scored dumps strictly before the dump (its own never counted); the m2_unseen gate (LIVE with its flag)
        let h2v = self.h2.as_ref().map(|h| h.view(&mint, c.dump.tr.s, c.dump.tr.i));
        let h2skip = self.cfg.m2seen_gate && h2v.is_some_and(|v| v.0 == 0);
        // dip38 PSM12-S1 on the dumper at the check (None with its log off); a LIVE skip only after every other check (below)
        let s1v = self.s1_view(true, h2v.map(|v| v.0), c.dump.age, &c.dump.tr.user);
        // dip43 A9 "rearm_r5" / "rearm": "log" keeps the verdicts on the records (rearm: a check that would arm is skipped "rearm_log43")
        let (r5_live, re_live) = (self.d43.g.rearm_r5, self.d43.g.rearm);
        let Some(rm) = self.rm.as_mut() else { return };
        rm.st.checks += 1;
        let en_slot = c.dump.tr.s + RE_WAIT + rm.cfg.gap;
        let r5_on = rm.cfg.r5_skip;
        let hv: Vec<(Pk, i64)> = holders.clone().unwrap_or_default();
        let mut why: Option<&'static str> = match &holders {
            None => Some("rearm_gone"),
            Some(h) if h.is_empty() => Some("rearm_no_holder"),
            _ if halted => Some("rearm_blocked_stopped"),
            // dip31 the circuit breaker's pause
            _ if breaker_paused(&self.sh) => Some("rearm_breaker"),
            _ if armed.is_some() => Some(if armed_re { "rearm_blocked_rearm_armed" } else { "rearm_blocked_live_armed" }),
            _ if reactive_open(&mint) => Some("rearm_blocked_reactive"),
            _ if lwhy.is_some() => Some("rearm_blocked_launch"),
            _ if crw == Some("loss") => Some("rearm_cr_loss"),
            _ if crw.is_some() => Some("rearm_cr_unfollowed"),
            _ if whg.is_some_and(|g| g.0) && wh_live => Some("rearm_wh_loss"),
            _ if hlg.is_some() && hl_live => Some("rearm_holder_loss"),
            _ if h2skip => Some("rearm_m2_unseen"),
            _ if blh.is_some() => Some("rearm_blocklist"),
            _ => None,
        };
        // R5 (the shadow's r5_skip): the QUIET arm signals of the LARGEST holder at the check; skipped only once the QUIET arm rule is on
        let mut r5: Option<serde_json::Value> = None;
        if why.is_none() && r5_on {
            if let Some(q) = self.qt.as_ref() {
                let h0 = hv[0].0;
                let since_last = self.det.last_trade_slot(&mint).map_or(9999, |s| slot.saturating_sub(s));
                let (coh_hold, fb_n) = self.det.trade_counts(&mint, &q.coh, &q.fb).unwrap_or((0, 0));
                let (wh_fol, wh_dumps) = q.book.as_ref().map_or((-1.0, 0), |b| b.whale(&h0, slot, t_rx));
                let flags = [since_last >= 1, coh_hold == 0, fb_n < pq::FB_MAX, wh_fol < q.cfg.fol];
                let all4 = flags.iter().all(|x| *x);
                let on = q.arm_on(t_rx);
                let mut j = serde_json::json!({"holder": b58(&h0), "since_last": since_last, "coh_hold": coh_hold, "fb_n": fb_n, "wh_fol": wh_fol, "wh_dumps": wh_dumps,
                    "fol": q.cfg.fol, "q": flags, "all4": all4, "rule_on": on});
                if all4 {
                    if on && r5_live { why = Some("rearm_r5"); } else { j["would_skip"] = true.into(); rm.st.r5_would += 1; }
                }
                r5 = Some(j);
            }
        }
        // dip38 PSM12-S1 LIVE (only with its gate on for re-arms): decided last, on a check that would arm
        if why.is_none() { if let Some(w) = s1v.as_ref().and_then(|v| self.s1_skip_why(v)) { why = Some(w); } }
        if why.is_none() && !re_live { why = Some("rearm_log43"); }
        let hj = holders_json(&hv);
        if let Some(w) = why {
            let mut x = serde_json::json!({"check_slot": slot, "en_slot": en_slot, "holders": hj});
            if w == "rearm_blocked_launch" { x["launch"] = lwhy.into(); }
            if let Some(j) = r5 { x["r5"] = j; }
            if let Some(j) = crj { x["cr"] = j; }
            // dip37: the ledger's view of the dumper (only with it on)
            if let Some((_, h)) = &whg { pswh::wh_fields(&mut x, &self.cfg, &c.dump.tr.user, h); }
            if let Some((nd, mx)) = h2v { psh2::fields(&mut x, nd, mx, true, 0, self.cfg.rearm.spend); }
            if let (Some(v), true) = (&s1v, w.starts_with("rearm_s1_")) {
                x["s1"] = v.json(self.cfg.s1_parts, self.s1_live(true), self.cfg.rearm.spend, c.dump.tr.vsol, c.dump.tr.p());
                self.s1_skip_note(&mint, &c.dump.tr.user, v);
            }
            if w == "rearm_wh_loss" { if let Some((_, h)) = whg { self.wh_skip_line(&mint, &c.dump.tr.user, &h, true); } }
            if whg.is_some_and(|g| g.0) && !wh_live { x["wh_would"] = true.into(); }
            if let Some(h) = &hlg { PsLive::hl_fields(&mut x, h); if !hl_live { x["hl_would"] = true.into(); } }
            if w == "rearm_holder_loss" { if let Some(h) = &hlg { self.hl_note(&mint, h, true, true); } }
            // dip36: the blocklist's hit
            if let Some(h) = blh.as_ref().filter(|_| w == "rearm_blocklist") {
                PsLive::bl_fields(&mut x, h);
                if let Some(b) = self.bl.as_mut() { b.skips += 1; }
                self.line(format!("  PRESEND LIVE REARM BLOCKLIST SKIP {} | dumper {} | listed {} ({}, {:.2}%): {}", b58(&mint), &b58(&c.dump.tr.user)[..8], &b58(&h.0)[..8], h.1, h.2, h.3));
            }
            // dip34 (log-only, --presend-live-ann on): the holders check's skips get "ann" too (the creator's holding: cr_hold / cr_big)
            if self.cfg.ann { x["ann"] = ann_arm(&self.det, &self.user, &mint, slot); }
            self.rearm_skip(w, &mint, &c.dump, x);
            // dip34 seen (log-only): a rearm_cr_loss skip's dumper into the seen book (nothing without --presend-live-seen-log)
            self.seen_note(w, c.dump.tr.user, t_rx, mint);
            return;
        }
        let launch = launch.expect("checked: rearm_blocked_launch otherwise");
        // our position / its margin / our token account on the token: the window waits (never a second fill, never a double fill)
        if let Some(b) = self.rearm_block(&mint) {
            let mut r = serde_json::json!({"ev": "presend_live_rearm_defer", "kind": "rearm", "mint": b58(&mint), "dump": c.dump.json(), "check_slot": slot, "en_slot": en_slot,
                "holders": hj, "why": b});
            if let Some(j) = &r5 { r["r5"] = j.clone(); }
            self.rec(r);
            if let Some(rm) = self.rm.as_mut() {
                rm.st.deferred += 1;
                rm.defer.push(RDef { mint, dump: c.dump, holders: hv, launch, chk_slot: slot, chk_t: t_rx, at: Instant::now(), why: b, r5, en_slot, s1: s1v });
            }
            return;
        }
        self.rearm_arm(mint, c.dump, hv, launch, slot, t_rx, None, r5, s1v);
    }

    /// ARM a re-arm window now (at the check, or when its wait ended): the sender's window (the re-arm size), the probe's window, the
    /// record and the line. `deferred`: (ms waited, on what)
    #[allow(clippy::too_many_arguments)]
    fn rearm_arm(&mut self, mint: Pk, dump: RDump, holders: Vec<(Pk, i64)>, launch: Launch, chk_slot: u64, chk_t: u64, deferred: Option<(f64, &'static str)>,
                 r5: Option<serde_json::Value>, s1: Option<super::pss1::S1V>) {
        let (k, drop, dry) = (self.cfg.k, self.cfg.drop, self.cfg.dry);
        // the holders when a waiting window arms (the record's "holders" are the check's: the paper's)
        let holders_arm = deferred.map(|_| self.det.holders_at_least(&mint, RE_BIG, &self.user).unwrap_or_default());
        self.wid += 1;
        let id = self.wid;
        let Some(rm) = self.rm.as_mut() else { return };
        let (spend, gap) = (rm.cfg.spend, rm.cfg.gap);
        let en_slot = dump.tr.s + RE_WAIT + gap;
        let arm_slot = rm.clock;
        let (vsol, vtok, fr, pos) = rm.cur.get(&mint).copied().unwrap_or((dump.tr.vsol, dump.tr.vtok, dump.tr.fr(), dump.tr.pos()));
        let deferred_ms = deferred.map_or(0.0, |d| d.0);
        rm.wins.insert(id, RWin { mint, dump_slot: dump.tr.s, arm_slot, en_slot, others: 0, qdec: None, stop: None, deferred_ms, n_holders: holders.len() });
        rm.note_id(id);
        rm.st.windows += 1;
        if deferred.is_some() { rm.st.deferred_armed += 1; }
        // the window starts at once (the paper's t_arm: no +50 ms)
        let st_ns = arbx::fast::mono_ns();
        let slot_ns = arbx::feeds::entries::SLOT_US.load(Ordering::Relaxed) * 1_000;
        self.launches.insert(mint, launch.clone());
        // dip27 (log-only): the largest holding but the dumper's and ours at the arm (0 with the annotations off)
        let ob6 = ob6_pct(&self.det, self.cfg.ann || self.cfg.deep_drop > 0.0, &mint, &dump.tr.user, &self.user);
        // dip36 live gate: the window's verdict cell (None without the FP-NOBOT log)
        let fpg = self.fp.as_ref().map(|_| Arc::new(pslog36::Gate::default()));
        // dip37: the window's fee arm, once, now (None with the fee A/B off)
        let fab = self.fab_assign(id);
        self.sh.wins.lock().unwrap().push(SWin { id, mint, launch, st_ns, stop_ns: u64::MAX, en_slot, vsol, vtok, fr, pos, pace: pl::Pace::new(st_ns, k, slot_ns), n: 0, done: false,
            spend, rearm: true, ob6, grd: grd_set(&self.det, self.cfg.ann, &mint, &self.user, dump.tr.s), fpg: fpg.clone(), fab, blk: self.bl_send_hit(&mint), bd: self.bd_snap(&mint) });
        self.armed.insert(mint, id);
        {
            let tp = &mut self.tapes.entry(mint).or_insert_with(|| (VecDeque::new(), 0)).0;
            tp.push_back(dump.tr.clone());
            if tp.len() > 256 { tp.pop_front(); }
        }
        self.wins.insert(id, Win { id, mint, whale: dump.tr.user, trig_slot: dump.tr.s, en_slot, armed_at: Instant::now(), stop_at: None, sent: 0, resolved: 0, unseen: 0,
            last_deadline: 0, disarmed: None, filled: false, checked: false, quiet: 0, qj: None, qkey: None, q_others: None, dl: None, excl: holders.iter().map(|h| h.0).collect() });
        let lim0 = vsol as f64 / vtok.max(1) as f64 * (1.0 - drop);
        let mut r = serde_json::json!({"ev": "presend_live_arm", "kind": "rearm", "w": id, "mint": b58(&mint), "dump": dump.json(), "holders": holders_json(&holders), "gap": gap,
            "check_slot": chk_slot, "arm_slot": arm_slot, "en_slot": en_slot, "arm_ms_after_dump": (chk_t as i64 - dump.tr.t_rx as i64) as f64 / 1e6 + deferred_ms,
            "deferred_ms": deferred_ms, "deferred": deferred.map(|d| d.1), "k": k, "spend": spend, "drop": drop, "lim0": lim0, "dry": dry});
        if let Some(h) = &holders_arm { r["holders_arm"] = holders_json(h); }
        if let Some(j) = r5 { r["r5"] = j; }
        // dip27 (log-only): only with the annotations on (off: dip26's record)
        if self.cfg.ann { r["ann"] = ann_arm(&self.det, &self.user, &mint, arm_slot); }
        // dip32: only when on (off: dip31's record): the creator's history, the fresh holders (log-only)
        if self.cfg.cr_on() { if let (_, Some(j)) = cr_gate(&self.sh, &self.cfg, self.det.creator_bal(&mint).map(|c| c.0), chk_t) { r["cr"] = j; } }
        if self.cfg.f3_log {
            let (fresh, fresh_n) = f3_fresh(&self.det, &mint, &self.user, &dump.tr.user, arm_slot);
            r["f3"] = serde_json::json!({"fresh": fresh, "fresh_n": fresh_n});
            if let Some(g) = tags_json(&self.det, &mint, &self.cfg.tag_wallets) { r["tags"] = g; }
        }
        // dip37: the window's fee arm and its values (only with the A/B on); the ledger's view of the dumper (only with it on)
        self.fab_arm_rec(&mut r, fab);
        if let Some((_, h)) = pswh::wh_gate(&self.sh, &self.cfg, &dump.tr.user, true) { pswh::wh_fields(&mut r, &self.cfg, &dump.tr.user, &h); }
        self.wh_arm(id, dump.tr.user);
        // dip37 the holder ledger: the window's keys; in "log" mode the would-skip on the arm record
        self.hl_arm(id, &mint, &dump.tr.user);
        if let Some((_, h)) = pswh::wh_gate(&self.sh, &self.cfg, &dump.tr.user, true).filter(|g| g.0 && !self.hls.live[0]) { let _ = h; r["wh_would"] = true.into(); }
        if let Some(h) = self.hl_gate(&mint, &dump.tr.user) { PsLive::hl_fields(&mut r, &h); r["hl_would"] = true.into(); self.hl_note(&mint, &h, true, false); }
        // dip37 HYBRID-2 (log only): the scored dumps strictly before this window's dump
        if let Some((nd, mx)) = self.h2.as_ref().map(|h| h.view(&mint, dump.tr.s, dump.tr.i)) { psh2::fields(&mut r, nd, mx, true, 0, spend); }
        // dip38 PSM12-S1 (log only): the holders check's verdict on the arm; the window keeps it for its fill / realize
        if let Some(v) = s1 { r["s1"] = v.json(self.cfg.s1_parts, self.s1_live(true), spend, dump.tr.vsol, dump.tr.p()); self.s1_arm(id, v); }
        // dip39 (only with the gate on): the depth at the arm's slot (the first attempts' view)
        if let Some(j) = self.bd_json(&mint, arm_slot) { r["botdepth"] = j; }
        // dip42 (log-only; only with the flag on): the 2NUM family on the token at the arm's slot
        if let Some(j) = self.f2_json(false, &mint, arm_slot) { r["fam2"] = j; }
        // dip34 (log-only): seen / eqgrp / q4 keyed on the dumper (each only with its flag)
        let dumper = dump.tr.user;
        self.log34(&mut r, &mint, &dumper, chk_slot, chk_t);
        // dip36 (log-only): FP-NOBOT's copy of the arm record (only with its flag)
        let fpr = self.fp.is_some().then(|| r.clone());
        self.rec(r);
        // dip35 (log-only): the fam holders read (nothing without its flag)
        self.fam_arm(id, mint, true, arm_slot);
        // dip38 (log-only): the anti-bait stage "arm" keyed on the dumper (nothing without its flags)
        self.l38_arm(id, mint, dumper, true, arm_slot, chk_t);
        // dip36 (log-only): FP-NOBOT at the re-arm's arm (the dump is the trigger row; the holders are excluded from its follower counts)
        if let Some(r) = fpr { self.fpnb_arm(id, true, mint, &dump.tr, dump.tr.user, arm_slot, holders.iter().map(|h| h.0).collect(), &r, en_slot, fpg); }
        let t = &dump.tr;
        self.line(format!("  PRESEND LIVE REARM ARM w{id} {} | dump {} {:.1}% ({:.2} SOL) slot {} age {} | holders {} | until slot {en_slot} | {k} attempts/slot, limit {:.2}x, {:.3} SOL{}",
            b58(&mint), &b58(&t.user)[..8], t.tok as f64 / pl::SUPPLY * 100.0, t.sol as f64 / 1e9, t.s, dump.age, holders_short(&holders), 1.0 - drop, spend as f64 / 1e9,
            deferred.map(|d| format!(" | armed after waiting {:.0} ms ({})", d.0, d.1)).unwrap_or_default()));
    }

    /// ONE TRADE (on_exec, after the detector took it and its trigger was decided): the token's armed window (QUIET's count, its stops),
    /// its waiting windows (the same stops end them), the curve state; a new candidate
    pub(super) fn rearm_trade(&mut self, t: &pl::Trade) {
        if self.rm.is_none() { return; }
        let mint = t.mint;
        let ours = t.user == self.user;
        let big_sell = !t.buy && t.tok as i64 >= RE_BIG;
        let armed = self.armed.get(&mint).copied();
        let halted = self.rearm_halted();
        let user = self.user;
        let Some(rm) = self.rm.as_mut() else { return };
        if let Some(c) = rm.cur.get_mut(&mint) { *c = (t.vsol, t.vtok, t.fr(), t.pos()); }
        // the armed re-arm window: QUIET counts every trade but ours; the next >= 6% sell / no holder left stop it 30 ms later
        let mut stop: Option<u64> = None;
        if let Some(w) = armed.and_then(|id| rm.wins.get_mut(&id)) {
            if !ours { w.others += 1; }
            if w.stop.is_none() {
                let why = if big_sell { Some("whale_dump") } else if !t.buy && !self.det.any_holder(&mint, RE_BIG, &user) { Some("no_holder") } else { None };
                if why.is_some() { w.stop = why; stop = armed; }
            }
        }
        // waiting windows of the token: the same stops end them (never armed)
        let mut ended: Vec<(RDef, &'static str)> = Vec::new();
        if !t.buy && rm.defer.iter().any(|d| d.mint == mint) {
            let why = if big_sell { Some("whale_dump") } else if !self.det.any_holder(&mint, RE_BIG, &user) { Some("no_holder") } else { None };
            if let Some(why) = why {
                let (a, b): (Vec<RDef>, Vec<RDef>) = std::mem::take(&mut rm.defer).into_iter().partition(|d| d.mint == mint);
                rm.defer = b;
                ended = a.into_iter().map(|d| (d, why)).collect();
            }
        }
        // a candidate: a single sell >= 6% of supply by anyone but us, on a token the detector follows
        let mut skip: Option<(&'static str, RDump)> = None;
        if big_sell && !ours && !halted && self.det.followed(&mint) {
            rm.st.sells6 += 1;
            let age = t.s.saturating_sub(self.det.create_slot(&mint).unwrap_or(t.s));
            let d = RDump { tr: t.clone(), age };
            if t.vsol >= RE_UNTRADE { skip = Some(("rearm_untradeable", d)); }
            else if age > RE_MAX_AGE { skip = Some(("rearm_age", d)); }
            else {
                rm.st.cands += 1;
                rm.cur.insert(mint, (t.vsol, t.vtok, t.fr(), t.pos()));
                rm.cands.push(RCand { mint, dump: d });
            }
        }
        if let Some(id) = stop {
            // as the T2 whale's sell: the sender stops trying 30 ms later, tick disarms it then (whale_dump / no_holder)
            if let Some(w) = self.wins.get_mut(&id) { if w.stop_at.is_none() { w.stop_at = Some(Instant::now() + Duration::from_millis(WHALE_SELL_MS)); } }
            let stop_ns = arbx::fast::mono_ns() + WHALE_SELL_MS * 1_000_000;
            if let Some(s) = self.sh.wins.lock().unwrap().iter_mut().find(|s| s.id == id) { s.stop_ns = s.stop_ns.min(stop_ns); }
        }
        for (d, why) in ended { self.rearm_defer_drop(d, why); }
        if let Some((why, d)) = skip { self.rearm_skip(why, &mint, &d, serde_json::json!({})); }
    }

    /// tick: the waiting windows whose block cleared arm now (if still <= their last slot); the others wait or end
    pub(super) fn rearm_tick(&mut self, slot_now: u64) {
        let Some(rm) = self.rm.as_ref() else { return };
        if rm.defer.is_empty() { return; }
        let clock = rm.clock.max(slot_now);
        self.rearm_defer_sweep(clock);
        let mut i = 0;
        while let Some(mint) = self.rm.as_ref().and_then(|r| r.defer.get(i)).map(|d| d.mint) {
            let armed = self.armed.get(&mint).copied();
            if armed.is_none() {
                if let Some(b) = self.rearm_block(&mint) {
                    if let Some(d) = self.rm.as_mut().and_then(|r| r.defer.get_mut(i)) { d.why = b; }
                    i += 1;
                    continue;
                }
            }
            let Some(d) = self.rm.as_mut().map(|r| r.defer.remove(i)) else { return };
            if let Some(id) = armed {
                // a window armed on the token meanwhile (another candidate's re-arm window; a T2 one took the token over)
                let ended = if self.rearm_w(id) { "rearm_armed" } else { "superseded" };
                self.rearm_defer_drop(d, ended);
                continue;
            }
            let ms = d.at.elapsed().as_secs_f64() * 1e3;
            self.rearm_arm(d.mint, d.dump, d.holders, d.launch, d.chk_slot, d.chk_t, Some((ms, d.why)), d.r5, d.s1);
        }
    }

    /// a T2 window arms on `mint` (trigger(), before it is armed): it takes the token over: the armed re-arm window is disarmed
    /// "superseded", the waiting ones end
    pub(super) fn rearm_take_over(&mut self, mint: &Pk) {
        let Some(rm) = self.rm.as_mut() else { return };
        let (gone, keep): (Vec<RDef>, Vec<RDef>) = std::mem::take(&mut rm.defer).into_iter().partition(|d| d.mint == *mint);
        rm.defer = keep;
        for d in gone { self.rearm_defer_drop(d, "superseded"); }
        if let Some(&id) = self.armed.get(mint) { if self.rearm_w(id) { self.disarm(id, "superseded"); } }
    }

    /// the stop (caps, run end, no new buys): the candidates and the waiting windows end (the armed ones were disarmed "stopped")
    pub(super) fn rearm_stop_all(&mut self) {
        let Some(rm) = self.rm.as_mut() else { return };
        let (cands, defer) = (std::mem::take(&mut rm.cands), std::mem::take(&mut rm.defer));
        rm.cur.clear();
        for c in cands { self.rearm_skip("rearm_blocked_stopped", &c.mint, &c.dump, serde_json::json!({})); }
        for d in defer { self.rearm_defer_drop(d, "stopped"); }
    }

    /// the 60 s status line's part ("" without re-arm)
    pub(super) fn rearm_status(&self) -> String {
        let Some(rm) = self.rm.as_ref() else { return String::new() };
        let s = &rm.st;
        format!(" | rearm: windows {} armed now {} fills {} realized {:+.4} SOL (sells >= 6% {} candidates {} checks {} waited {} armed after waiting {} pending {} | attempts {} \
                 failed-try fees {:.6} SOL | closed {} | skips {{{}}} | ends {{{}}})",
            s.windows, rm.wins.len(), s.fills, rm.rz.rearm.load(Ordering::SeqCst) as f64 / 1e9, s.sells6, s.cands, s.checks, s.deferred, s.deferred_armed, rm.pending(), s.sent,
            s.fees as f64 / 1e9, s.closed, sorted(&s.skips), sorted(&s.ends))
    }

    /// run_end's totals (None without re-arm)
    pub(super) fn rearm_json(&self) -> Option<serde_json::Value> {
        let rm = self.rm.as_ref()?;
        let s = &rm.st;
        let map = |m: &FxHashMap<&'static str, u64>| serde_json::json!(m.iter().map(|(k, v)| (k.to_string(), serde_json::json!(v))).collect::<serde_json::Map<String, serde_json::Value>>());
        Some(serde_json::json!({"cfg": rm.cfg.json(), "sells6": s.sells6, "cands": s.cands, "checks": s.checks, "windows": s.windows, "deferred": s.deferred,
            "deferred_armed": s.deferred_armed, "r5_would": s.r5_would, "skips": map(&s.skips), "ends": map(&s.ends), "sent": s.sent, "fees_failed": s.fees, "fills": s.fills,
            "closed": s.closed, "pending": rm.pending(), "armed_now": rm.wins.len(), "realized": rm.rz.json()}))
    }

    /// run_end's realized P&L by kind (t2, rearm) once the realized lookups are in (None without re-arm)
    pub fn rearm_split(&self) -> Option<serde_json::Value> { self.rm.as_ref().map(|r| r.rz.json()) }
    /// the split the async realized lookups add to (None without re-arm)
    pub(super) fn rz(&self) -> Option<Arc<RzSplit>> { self.rm.as_ref().map(|r| r.rz.clone()) }
}

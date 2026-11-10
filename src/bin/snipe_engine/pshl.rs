// =====================================================================================================================
// dip37 LIVE HOLDER LEDGER (owner approved for run 57; ideas_a HOLD X2 n1 s0.1 wp0.05, /home/it/sniper-studies/sniper-ideas-a REPORT.txt / ideas.py / replay2.py)
// and the LEDGERS' HOT CONTROL FILE.
//   --presend-live-holder-loss PCT:SOL:WIN   at an arm (T2 and re-arm): skip ("holder_loss" / "rearm_holder_loss", hl_wallet / hl_pct / hl_sum)
//                                            when a holder >= PCT% of the mint now (the detector's book; the T2 whale / re-arm dumper and we
//                                            excluded; largest first) has >= 1 earlier position with us, their summed P&L <= -SOL, and NO position
//                                            >= +WIN (the win protection). E.g. 2:0.10:0.05
//   --presend-live-holder-state PATH          the ledger preloaded (seed: ops/strategies/presend/prevent/forward/holder_seed.py; missing = empty +
//                                            NOTE) and saved back every ~10 min and at the run's end: {"v": 1, "h": {wallet: [n, lamports, best
//                                            lamports(, paper n, paper lamports)]}}
//   --presend-live-holder-learn paper|off      (default off) a T2 arm skipped "holder_loss" learns from the shadow's row c on the same trigger
//                                            (the whale ledger's mechanism: the arm's holder keys each get the paper position)
//   LEARNING: a position's keys = the holders >= PCT% at its arm and at its fill (the whale / dumper and we excluded; the replay's arm holders +
//     landing holders); its realized P&L is added to every key ([n, sum], best = the largest single position)
//   --presend-live-ledger-control PATH        {"whale": "live"|"log", "holder": "live"|"log"} re-read every ~10 s (the fpnb_control pattern): in
//                                            "log" the verdict is still computed and logged (wh_would / hl_would on the arm record), nothing is
//                                            skipped; a bad / missing file keeps the last good modes; every change is a presend_live_ledger_mode
//                                            record and a line. Without the file both ledgers are live (as their flags say)
// REPLAY DIFFERENCE (measured offline vs the engine): the replay checks the holders the fill record saw at landing (age >= 1); the engine can
// only check the holders it sees at the arm. Off (no flag): nothing of it runs.
// =====================================================================================================================
use super::*;

/// one holder wallet's positions with us: count, summed P&L, the best single one (lamports); paper among them
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct HlHist { pub n: u32, pub sum: i64, pub best: i64, pub pn: u32, pub ps: i64 }
impl Default for HlHist { fn default() -> HlHist { HlHist { n: 0, sum: 0, best: i64::MIN, pn: 0, ps: 0 } } }
impl HlHist {
    pub fn add(&mut self, pnl: i64, paper: bool) {
        self.n += 1; self.sum += pnl; self.best = self.best.max(pnl);
        if paper { self.pn += 1; self.ps += pnl; }
    }
    /// >= 1 position, sum <= -loss, never a position >= +win
    pub fn blocks(&self, loss: i64, win: i64) -> bool { loss > 0 && self.n >= 1 && self.sum <= -loss && self.best < win }
}

/// --presend-live-holder-loss PCT:SOL:WIN -> (PCT in (0, 100], SOL in (0, 5] lamports, WIN in [0, 5] lamports)
pub fn hl_parse(s: &str) -> Result<(f64, i64, i64)> {
    let bad = || anyhow::anyhow!("--presend-live-holder-loss PCT:SOL:WIN (holder % in (0, 100], loss SOL in (0, 5], win SOL in [0, 5]), e.g. 2:0.10:0.05; got '{s}'");
    let v: Vec<&str> = s.split(':').collect();
    if v.len() != 3 { return Err(bad()); }
    let (p, l, w): (f64, f64, f64) = (v[0].parse().map_err(|_| bad())?, v[1].parse().map_err(|_| bad())?, v[2].parse().map_err(|_| bad())?);
    if !(p > 0.0 && p <= 100.0) || !(l > 0.0 && l <= 5.0) || !(w >= 0.0 && w <= 5.0) { return Err(bad()); }
    Ok((p, (l * 1e9).round() as i64, (w * 1e9).round() as i64))
}

pub fn hl_parse_state(b: &[u8]) -> Result<FxHashMap<Pk, HlHist>> {
    let j: serde_json::Value = serde_json::from_slice(b).context("parse")?;
    let mut m = FxHashMap::default();
    for (w, v) in j["h"].as_object().context("no \"h\" object")? {
        let Some(pk) = bs58::decode(w).into_vec().ok().and_then(|x| <[u8; 32]>::try_from(x).ok()) else { bail!("bad wallet {w}") };
        let (Some(n), Some(s), Some(b)) = (v[0].as_u64(), v[1].as_i64(), v[2].as_i64()) else { bail!("{w}: not [n, lamports, best]") };
        m.insert(pk, HlHist { n: n as u32, sum: s, best: b, pn: v[3].as_u64().unwrap_or(0) as u32, ps: v[4].as_i64().unwrap_or(0) });
    }
    Ok(m)
}
pub fn hl_load(path: &str) -> Result<FxHashMap<Pk, HlHist>> { hl_parse_state(&std::fs::read(path).with_context(|| format!("read {path}"))?).with_context(|| path.to_string()) }
pub fn hl_save(m: &FxHashMap<Pk, HlHist>, path: &str) -> Result<usize> {
    let h: serde_json::Map<String, serde_json::Value> = m.iter().map(|(k, h)| (b58(k), if h.pn > 0 { serde_json::json!([h.n, h.sum, h.best, h.pn, h.ps]) } else { serde_json::json!([h.n, h.sum, h.best]) })).collect();
    let tmp = format!("{path}.tmp");
    std::fs::write(&tmp, serde_json::json!({"v": 1, "h": h}).to_string()).with_context(|| format!("write {tmp}"))?;
    std::fs::rename(&tmp, path).with_context(|| format!("rename {tmp}"))?;
    Ok(m.len())
}

/// the ledgers' live / log modes [whale, holder] from the control file's JSON
pub fn ctl_parse(b: &[u8]) -> std::result::Result<[bool; 2], String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    let mut out = [true; 2];
    if !v.is_object() { return Err("not an object".into()); }
    for (i, k) in ["whale", "holder"].iter().enumerate() {
        match v[*k].as_str() { None => {}, Some("live") => out[i] = true, Some("log") => out[i] = false, Some(x) => return Err(format!("{k}: '{x}' (live | log)")) }
    }
    Ok(out)
}

/// dip37b: the control file's "skip2" key: Some(live) / None (absent: the start flag's mode stays)
pub fn ctl_parse_s2(b: &[u8]) -> std::result::Result<Option<bool>, String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    match v["skip2"].as_str() { None if v.get("skip2").is_none_or(|x| x.is_null()) => Ok(None), Some("live") => Ok(Some(true)), Some("log") => Ok(Some(false)),
        _ => Err(format!("skip2: '{}' (live | log)", v["skip2"])) }
}

/// dip37c: the control file's "blocklist_send" key: Some(live) / None (absent)
pub fn ctl_parse_bls(b: &[u8]) -> std::result::Result<Option<bool>, String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    match v["blocklist_send"].as_str() { None if v.get("blocklist_send").is_none_or(|x| x.is_null()) => Ok(None), Some("live") => Ok(Some(true)),
        Some("log") => Ok(Some(false)), _ => Err(format!("blocklist_send: '{}' (live | log)", v["blocklist_send"])) }
}

/// dip38: the control file's "s1" key (PSM12-S1's gate): Some(live) / None (absent: the start flag's mode stays)
pub fn ctl_parse_s1(b: &[u8]) -> std::result::Result<Option<bool>, String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    match v["s1"].as_str() { None if v.get("s1").is_none_or(|x| x.is_null()) => Ok(None), Some("live") => Ok(Some(true)), Some("log") => Ok(Some(false)),
        _ => Err(format!("s1: '{}' (live | log)", v["s1"])) }
}

/// the probe's holder-ledger side and the control file
#[derive(Debug)]
pub struct HlSt {
    /// window id -> its holder keys (arm + fill)
    pub keys: FxHashMap<u64, Vec<Pk>>,
    pub saved: u64, pub skips: [u64; 2], pub would: [u64; 2],
    /// [whale, holder] live (true) or log
    pub live: [bool; 2],
    ctl: Option<(String, Option<std::time::SystemTime>, Instant)>,
    pub ctl_changes: u64, pub ctl_errors: u64,
}
impl Default for HlSt {
    fn default() -> HlSt { HlSt { keys: FxHashMap::default(), saved: 0, skips: [0; 2], would: [0; 2], live: [true; 2], ctl: None, ctl_changes: 0, ctl_errors: 0 } }
}

impl PsLive {
    /// the holders >= PCT% of `mint` now (largest first), `not` (the whale / dumper) and we excluded
    pub(super) fn hl_holders(&self, mint: &Pk, not: &Pk) -> Vec<(Pk, i64)> {
        let min = (self.cfg.hl_pct / 100.0 * pl::SUPPLY).ceil() as i64;
        self.det.holders_at_least(mint, min, &self.user).unwrap_or_default().into_iter().filter(|h| h.0 != *not).collect()
    }

    /// the gate at an arm: Some((wallet, pct, history)) of the first blocking holder (None: the ledger off or none blocks)
    pub(super) fn hl_gate(&self, mint: &Pk, not: &Pk) -> Option<(Pk, f64, HlHist)> {
        if !self.cfg.hl_on() { return None; }
        let g = self.sh.hl.lock().unwrap();
        self.hl_holders(mint, not).into_iter().find_map(|(w, b)| g.get(&w).filter(|h| h.blocks(self.cfg.hl_loss, self.cfg.hl_win)).map(|h| (w, b as f64 / pl::SUPPLY * 100.0, *h)))
    }

    /// a record's fields (the skip's, or the arm's would-skip in log mode)
    pub fn hl_fields(r: &mut serde_json::Value, h: &(Pk, f64, HlHist)) {
        r["hl_wallet"] = b58(&h.0).into();
        r["hl_pct"] = h.1.into();
        r["hl_sum"] = (h.2.sum as f64 / 1e9).into();
        r["hl_n"] = h.2.n.into();
    }

    /// an armed window's keys: the holders now (nothing with the ledger off)
    pub(super) fn hl_arm(&mut self, id: u64, mint: &Pk, not: &Pk) {
        if !self.cfg.hl_on() { return; }
        let k: Vec<Pk> = self.hl_holders(mint, not).into_iter().map(|h| h.0).collect();
        self.hls.keys.insert(id, k);
    }
    /// the window's fill: the holders at landing join its keys
    pub(super) fn hl_fill(&mut self, id: u64, mint: &Pk, not: &Pk) {
        if !self.cfg.hl_on() { return; }
        let add: Vec<Pk> = self.hl_holders(mint, not).into_iter().map(|h| h.0).collect();
        let e = self.hls.keys.entry(id).or_default();
        for w in add { if !e.contains(&w) { e.push(w); } }
    }

    /// a skip / would-skip counted and its line (`live`: skipped)
    pub(super) fn hl_note(&mut self, mint: &Pk, h: &(Pk, f64, HlHist), rearm: bool, live: bool) {
        if live { self.hls.skips[rearm as usize] += 1; } else { self.hls.would[rearm as usize] += 1; }
        self.line(format!("  PRESEND LIVE {}HOLDER-LOSS {} {} | holder {} {:.1}% has {} positions with us, {:+.4} SOL, best {:+.4}{}", if rearm { "REARM " } else { "" },
            if live { "SKIP" } else { "WOULD SKIP (log mode)" }, b58(mint), &b58(&h.0)[..8], h.1, h.2.n, h.2.sum as f64 / 1e9, h.2.best.max(-1_000_000_000_000) as f64 / 1e9, ""));
    }

    /// the control file (every ~10 s from tick; `force`: now)
    pub(super) fn ledger_ctl_check(&mut self, force: bool) {
        let Some((path, mt0, at)) = self.hls.ctl.clone() else { return };
        if !force && at.elapsed() < Duration::from_secs(10) { return; }
        let mt = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
        if let Some(c) = self.hls.ctl.as_mut() { c.2 = Instant::now(); }
        if !force && mt == mt0 { return; }
        if let Some(c) = self.hls.ctl.as_mut() { c.1 = mt; }
        match std::fs::read(&path).map_err(|e| e.to_string()).and_then(|b| Ok((ctl_parse(&b)?, ctl_parse_s2(&b)?, ctl_parse_bls(&b)?, ctl_parse_s1(&b)?))) {
            Ok((m, s2, bls, s1)) => {
                // dip37c "blocklist_send": the per-send blocklist live / log (only with the blocklist's per-send check)
                let bl_old = self.sh.bl_send_live.load(Ordering::SeqCst);
                let bl_new = match bls { Some(x) if self.cfg.blocklist_send => x, _ => bl_old };
                let old = self.hls.live;
                // dip37b "skip2": live = the start flag's kinds (both when the flag is off), log = off; it needs --presend-skip2-log on (else ignored)
                let gs = self.fp.as_ref().filter(|_| self.cfg.skip2_log).map(|f| f.gs.clone());
                let s2_old = gs.as_ref().map(|g| g.s2_mode.load(Ordering::SeqCst));
                let s2_new = match (s2, &gs) {
                    (Some(live), Some(_)) => Some(if live { if self.cfg.skip2_live != 0 { self.cfg.skip2_live } else { 3 } } else { 0 }),
                    _ => s2_old,
                };
                // dip38 "s1": PSM12-S1's gate live = the start flag's kinds (both when the flag is off), log = off; it needs --presend-live-s1-log on
                let s1_old = self.s1.mode;
                let s1_new = match s1 { Some(live) if self.cfg.s1_log => if live { if self.cfg.s1_live != 0 { self.cfg.s1_live } else { 3 } } else { 0 }, _ => s1_old };
                if old == m && s2_new == s2_old && bl_new == bl_old && s1_new == s1_old { return; }
                self.hls.live = m;
                if s1_new != s1_old { self.s1.mode = s1_new; self.s1.ctl_changes += 1; }
                self.sh.bl_send_live.store(bl_new, Ordering::SeqCst);
                if let (Some(g), Some(n)) = (&gs, s2_new) { g.s2_mode.store(n, Ordering::SeqCst); }
                self.hls.ctl_changes += 1;
                let s = |x: bool| if x { "live" } else { "log" };
                let mut r = serde_json::json!({"ev": "presend_live_ledger_mode", "ok": true, "whale": s(m[0]), "holder": s(m[1]), "was": {"whale": s(old[0]), "holder": s(old[1])},
                    "path": path, "t": arbx::feeds::clock::now_ns()});
                if let (Some(o), Some(n)) = (s2_old, s2_new) { r["skip2"] = pslog36::mode_str(n).into(); r["was"]["skip2"] = pslog36::mode_str(o).into(); }
                if s2.is_some() && gs.is_none() { r["skip2_ignored"] = "needs --presend-skip2-log on".into(); }
                if self.cfg.blocklist_send { r["blocklist_send"] = s(bl_new).into(); r["was"]["blocklist_send"] = s(bl_old).into(); }
                if self.cfg.s1_log { r["s1"] = pslog36::mode_str(s1_new).into(); r["was"]["s1"] = pslog36::mode_str(s1_old).into(); }
                if s1.is_some() && !self.cfg.s1_log { r["s1_ignored"] = "needs --presend-live-s1-log on".into(); }
                self.rec(r);
                self.line(format!("  PRESEND LIVE LEDGER MODES: whale {} -> {}, holder {} -> {}{}{} ({path})", s(old[0]), s(m[0]), s(old[1]), s(m[1]),
                    match (s2_old, s2_new) { (Some(o), Some(n)) => format!(", skip2 gate {} -> {}", pslog36::mode_str(o), pslog36::mode_str(n)), _ => String::new() },
                    if self.cfg.blocklist_send { format!(", blocklist per-send {} -> {}", s(bl_old), s(bl_new)) } else { String::new() }) + &if self.cfg.s1_log { format!(", S1 gate {} -> {}", pslog36::mode_str(s1_old), pslog36::mode_str(s1_new)) } else { String::new() });
            }
            Err(e) => {
                self.hls.ctl_errors += 1;
                let s = |x: bool| if x { "live" } else { "log" };
                self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": false, "err": e, "path": path, "whale": s(self.hls.live[0]), "holder": s(self.hls.live[1]),
                    "t": arbx::feeds::clock::now_ns()}));
                self.line(format!("  PRESEND LIVE LEDGER control file {path} NOT read ({e}): the modes stay whale {} holder {}", s(self.hls.live[0]), s(self.hls.live[1])));
            }
        }
    }
    /// the control file at the start (its first read decides the start modes)
    pub(super) fn ledger_ctl_open(&mut self) {
        if let Some(p) = self.cfg.ledger_ctl.clone() { self.hls.ctl = Some((p, None, Instant::now())); self.ledger_ctl_check(true); }
    }

    /// the status part ("" with the holder ledger and the control file off)
    pub(super) fn hl_status(&self) -> String {
        let mut s = String::new();
        if self.cfg.hl_on() {
            s += &format!(" | HOLDER LEDGER {}: skips T2 {} re-arm {}, would (log) {}/{}", self.sh.hl.lock().unwrap().len(), self.hls.skips[0], self.hls.skips[1], self.hls.would[0], self.hls.would[1]);
        }
        if self.cfg.ledger_ctl.is_some() || self.cfg.hl_on() || self.cfg.wh_on() {
            let m = |x: bool| if x { "live" } else { "log" };
            s += &format!(" | LEDGER MODES whale {} holder {}{}", m(self.hls.live[0]), m(self.hls.live[1]), if self.hls.ctl_errors > 0 { format!(" (control errors {})", self.hls.ctl_errors) } else { String::new() });
        }
        s
    }

    /// the state every ~10 min
    pub(super) fn hl_tick(&mut self, slot_now: u64) {
        self.ledger_ctl_check(false);
        let Some(p) = self.cfg.hl_state.clone() else { return };
        if slot_now < self.hls.saved + CR_SAVE_SLOTS { return; }
        if self.hls.saved > 0 {
            let m = self.sh.hl.lock().unwrap().clone();
            std::thread::spawn(move || { if let Err(e) = hl_save(&m, &p) { eprintln!("DIP PRESEND LIVE HOLDER LEDGER: NOT saved to {p}: {e:#}"); } });
        }
        self.hls.saved = slot_now;
    }

    /// the run's end
    pub(super) fn hl_finish(&mut self) -> Option<serde_json::Value> {
        if !self.cfg.hl_on() { return None; }
        if let Some(p) = self.cfg.hl_state.clone() {
            let m = self.sh.hl.lock().unwrap().clone();
            match hl_save(&m, &p) {
                Ok(n) => self.line(format!("  PRESEND LIVE HOLDER LEDGER: {n} wallets saved to {p}")),
                Err(e) => self.line(format!("  PRESEND LIVE HOLDER LEDGER: NOT saved to {p}: {e:#}")),
            }
        }
        Some(serde_json::json!({"wallets": self.sh.hl.lock().unwrap().len(), "skips_t2": self.hls.skips[0], "skips_rearm": self.hls.skips[1], "would_t2": self.hls.would[0],
            "would_rearm": self.hls.would[1], "live": self.hls.live[1], "whale_live": self.hls.live[0], "ctl_changes": self.hls.ctl_changes}))
    }
}

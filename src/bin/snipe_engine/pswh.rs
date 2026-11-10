// =====================================================================================================================
// dip37 LIVE WHALE / DUMPER LOSS LEDGER (owner approved going live, 11-04 via the coordinator). The creator ledger's mirror
// (--presend-live-cr-loss N:SOL + --presend-live-creator-state PATH, cr_gate), keyed on the ARM's wallet instead of the creator:
//   T2: the trigger whale (trig.wallet); re-arm: the dumper (dump.seller).
//   --presend-live-wh-loss N:SOL       skip the arm ("wh_loss" T2 / "rearm_wh_loss" re-arm) when that wallet's PRIOR positions with us number
//                                      >= N and sum to <= -SOL; the arm / skip records get wh_wallet, wh_n, wh_sum (SOL), wh_sum_hit, wh_mean_hit.
//                                      Decided with the other arm-time skips (right after the creator gate), never on the sender thread
//   --presend-live-wh-loss-mode sum|mean  (default sum) the rule: sum = n >= N and sum <= -SOL; mean = n >= N and sum / n <= -SOL (SOL read as
//                                      the per-position average loss)
//   --presend-live-whale-state PATH    the ledger preloaded at the start (the seed: ops/strategies/presend/prevent/forward/whale_seed.py, or the
//                                      last run's save; a missing file = an empty ledger, a NOTE) and saved back every ~10 min and at the run's end
//   --presend-live-wh-learn paper|off  (default off) a T2 arm skipped "wh_loss" still LEARNS: the presend shadow's row c on the same trigger (joined
//                                      on the trigger signature, as --presend-live-cr-earn-log) is added to the whale's history as a position,
//                                      net_cheap scaled to the live size (live spend / row c sol_in); no row c fill: nothing. A presend_live_wh_paper
//                                      record each; counted apart (pn / ps) so the state file tells paper from real. A re-arm has no shadow
//                                      window: a rearm_wh_loss skip never learns
//   --presend-live-wh-split on|off     (default off) two ledgers, T2 whales and re-arm dumpers, the same rule; every position goes into the
//                                      combined one AND its kind's one; the gate reads the combined (off) or its kind's (on)
// The ledger takes every presend_live_realized of a position whose window's arm wallet is known (the window id -> wallet, kept at the arm).
// State file: {"v": 1, "w": {wallet: [n, lamports(, paper n, paper lamports)]}, "t2": {...}, "re": {...}} ("w" = combined; a seed may carry
// only "w": the split ledgers then start empty). Off (no --presend-live-wh-loss): nothing of it runs, every record and decision dip36's.
// =====================================================================================================================
use super::*;

/// one wallet's positions with us and their summed P&L (lamports); `pn` / `ps` = the paper ones among them (--presend-live-wh-learn)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct WhHist { pub n: u32, pub sum: i64, pub pn: u32, pub ps: i64 }

impl WhHist {
    pub fn add(&mut self, pnl: i64) { self.n += 1; self.sum += pnl; }
    pub fn add_paper(&mut self, pnl: i64) { self.add(pnl); self.pn += 1; self.ps += pnl; }
    /// the SUM rule: >= n_min positions and their sum <= -loss (loss 0 = off: never)
    pub fn blocks(&self, n_min: u32, loss: i64) -> bool { loss > 0 && self.n >= n_min && self.sum <= -loss }
    /// the MEAN rule: >= n_min positions (>= 1) and sum / n <= -loss (exact: sum <= -loss x n)
    pub fn blocks_mean(&self, n_min: u32, loss: i64) -> bool {
        loss > 0 && self.n >= n_min.max(1) && (self.sum as i128) <= -(loss as i128) * self.n as i128
    }
    /// the live rule (`mean`: --presend-live-wh-loss-mode mean)
    pub fn blocks_mode(&self, n_min: u32, loss: i64, mean: bool) -> bool { if mean { self.blocks_mean(n_min, loss) } else { self.blocks(n_min, loss) } }
}

/// the ledgers: combined, T2 whales, re-arm dumpers
#[derive(Clone, Debug, Default, PartialEq)]
pub struct WhMaps { pub all: FxHashMap<Pk, WhHist>, pub t2: FxHashMap<Pk, WhHist>, pub re: FxHashMap<Pk, WhHist> }

impl WhMaps {
    /// the history the gate reads: the combined one, or with the split the kind's one
    pub fn get(&self, split: bool, rearm: bool, w: &Pk) -> WhHist {
        let m = if !split { &self.all } else if rearm { &self.re } else { &self.t2 };
        m.get(w).copied().unwrap_or_default()
    }
    /// a position (real or paper) into the combined ledger and its kind's -> the history the gate will read next
    pub fn add(&mut self, split: bool, rearm: bool, w: Pk, pnl: i64, paper: bool) -> WhHist {
        for m in [&mut self.all, if rearm { &mut self.re } else { &mut self.t2 }] {
            let h = m.entry(w).or_default();
            if paper { h.add_paper(pnl) } else { h.add(pnl) }
        }
        self.get(split, rearm, &w)
    }
}

/// --presend-live-wh-loss N:SOL -> (N, SOL in lamports): N 1..50 positions, SOL in (0, 5]
pub fn wh_loss_parse(s: &str) -> Result<(u32, i64)> {
    let bad = || anyhow::anyhow!("--presend-live-wh-loss N:SOL (positions 1..50, realized sum SOL in (0, 5]), e.g. 2:0.05; got '{s}'");
    let (n, v) = s.split_once(':').ok_or_else(bad)?;
    let (n, v): (u32, f64) = (n.parse().map_err(|_| bad())?, v.parse().map_err(|_| bad())?);
    if !(1..=50).contains(&n) || !(v > 0.0 && v <= 5.0) { return Err(bad()); }
    Ok((n, (v * 1e9).round() as i64))
}

/// the gate at an arm: (blocks by the live rule, the wallet's history the rule read: zero when unknown). None: the ledger off
pub(super) fn wh_gate(sh: &Shared, cfg: &Cfg, w: &Pk, rearm: bool) -> Option<(bool, WhHist)> {
    if !cfg.wh_on() { return None; }
    let h = sh.wh.lock().unwrap().get(cfg.wh_split, rearm, w);
    // dip43e: --presend-live-wh-kinds: the live rule blocks only the listed kinds (the verdict fields are recorded on every arm)
    Some((cfg.wh_kind_ok(rearm) && h.blocks_mode(cfg.wh_loss_n, cfg.wh_loss, cfg.wh_mean), h))
}

/// an arm / skip record's fields (sum in SOL, as the creator ledger's "cr".sum): the wallet, its history, both rules' verdicts
pub fn wh_fields(r: &mut serde_json::Value, cfg: &Cfg, w: &Pk, h: &WhHist) {
    r["wh_wallet"] = b58(w).into();
    r["wh_n"] = h.n.into();
    r["wh_sum"] = (h.sum as f64 / 1e9).into();
    r["wh_sum_hit"] = h.blocks(cfg.wh_loss_n, cfg.wh_loss).into();
    r["wh_mean_hit"] = h.blocks_mean(cfg.wh_loss_n, cfg.wh_loss).into();
    // paper positions among them (only with --presend-live-wh-learn paper)
    if h.pn > 0 { r["wh_pn"] = h.pn.into(); r["wh_ps"] = (h.ps as f64 / 1e9).into(); }
}

fn map_parse(j: &serde_json::Value) -> Result<FxHashMap<Pk, WhHist>> {
    let mut m = FxHashMap::default();
    let Some(o) = j.as_object() else { return Ok(m) };
    for (w, v) in o {
        let Some(pk) = bs58::decode(w).into_vec().ok().and_then(|x| <[u8; 32]>::try_from(x).ok()) else { bail!("bad wallet {w}") };
        let (Some(n), Some(s)) = (v[0].as_u64(), v[1].as_i64()) else { bail!("{w}: not [positions, lamports]") };
        m.insert(pk, WhHist { n: n.min(u32::MAX as u64) as u32, sum: s, pn: v[2].as_u64().unwrap_or(0) as u32, ps: v[3].as_i64().unwrap_or(0) });
    }
    Ok(m)
}
fn map_json(m: &FxHashMap<Pk, WhHist>) -> serde_json::Value {
    m.iter().map(|(k, h)| (b58(k), if h.pn > 0 { serde_json::json!([h.n, h.sum, h.pn, h.ps]) } else { serde_json::json!([h.n, h.sum]) }))
        .collect::<serde_json::Map<String, serde_json::Value>>().into()
}

/// the state file -> the ledgers ("w" needed; "t2" / "re" optional)
pub fn wh_parse(b: &[u8]) -> Result<WhMaps> {
    let j: serde_json::Value = serde_json::from_slice(b).context("parse")?;
    if !j["w"].is_object() { bail!("no \"w\" object"); }
    Ok(WhMaps { all: map_parse(&j["w"])?, t2: map_parse(&j["t2"])?, re: map_parse(&j["re"])? })
}
pub fn wh_load(path: &str) -> Result<WhMaps> {
    let b = std::fs::read(path).with_context(|| format!("read {path}"))?;
    wh_parse(&b).with_context(|| path.to_string())
}

/// save the ledgers (PATH.tmp, then renamed) -> wallets in the combined one
pub fn wh_save(m: &WhMaps, path: &str) -> Result<usize> {
    let tmp = format!("{path}.tmp");
    std::fs::write(&tmp, serde_json::json!({"v": 1, "w": map_json(&m.all), "t2": map_json(&m.t2), "re": map_json(&m.re)}).to_string()).with_context(|| format!("write {tmp}"))?;
    std::fs::rename(&tmp, path).with_context(|| format!("rename {tmp}"))?;
    Ok(m.all.len())
}

/// --presend-live-wh-learn paper: the T2 triggers skipped "wh_loss" (signature -> whale, mint, skip time ns) and the shadow windows armed on
/// them (window id -> signature, row c sol_in once filled); credits and their lamports; full = a map at its cap took nothing
#[derive(Debug, Default)]
pub struct WhPaper { skipped: FxHashMap<String, (Pk, Pk, u64)>, w: FxHashMap<u64, (String, Option<f64>)>, pub credits: u64, pub credit_sum: i64, pub full: u64,
    /// dip37 --presend-live-holder-learn paper: the T2 triggers skipped "holder_loss" (signature -> the arm's holder keys, mint, time)
    hskipped: FxHashMap<String, (Vec<Pk>, Pk, u64)>, pub hcredits: u64, pub hcredit_sum: i64 }

/// the probe's ledger side: every window's arm wallet (window id -> whale / dumper), the last save's slot, the skips, the paper learning
#[derive(Debug, Default)]
pub struct WhSt { pub win: FxHashMap<u64, Pk>, pub saved: u64, pub skips: [u64; 2], pub paper: WhPaper }

impl PsLive {
    /// an armed window's wallet (nothing with the ledger off)
    pub(super) fn wh_arm(&mut self, id: u64, w: Pk) { if self.cfg.wh_on() { self.whs.win.insert(id, w); } }

    /// a skip by the ledger: counted, a line (T2: `rearm` false); a T2 skip waits for its shadow's row c with --presend-live-wh-learn paper
    pub(super) fn wh_skip_line(&mut self, mint: &Pk, w: &Pk, h: &WhHist, rearm: bool) {
        self.whs.skips[rearm as usize] += 1;
        self.line(format!("  PRESEND LIVE {}WHALE-LOSS SKIP {} | {} {} has {} positions with us, {:+.4} SOL (rule {})", if rearm { "REARM " } else { "" }, b58(mint),
            if rearm { "dumper" } else { "whale" }, &b58(w)[..8], h.n, h.sum as f64 / 1e9, self.cfg.wh_spec()));
    }

    /// --presend-live-wh-learn paper: remember a T2 trigger skipped "wh_loss" for the shadow's window on it
    /// --presend-live-holder-learn paper: remember a T2 trigger skipped "holder_loss" (its holder keys) for the shadow's window on it
    pub(super) fn hl_paper_note(&mut self, sig: String, keys: Vec<Pk>, mint: Pk, t: u64) {
        if !self.cfg.hl_learn || keys.is_empty() { return; }
        let p = &mut self.whs.paper;
        if p.hskipped.len() >= CE_MAX { p.hskipped.retain(|_, v| v.2.saturating_add(CE_KEEP_NS) >= t); }
        if p.hskipped.len() >= CE_MAX { p.full += 1; return; }
        p.hskipped.insert(sig, (keys, mint, t));
    }

    pub(super) fn wh_paper_note(&mut self, sig: String, whale: Pk, mint: Pk, t: u64) {
        if !self.cfg.wh_learn { return; }
        let p = &mut self.whs.paper;
        if p.skipped.len() >= CE_MAX { p.skipped.retain(|_, v| v.2.saturating_add(CE_KEEP_NS) >= t); }
        if p.skipped.len() >= CE_MAX { p.full += 1; return; }
        p.skipped.insert(sig, (whale, mint, t));
    }

    /// --presend-live-wh-learn paper (cr-earn-log's join): every SHADOW record. A presend_arm on a wh_loss-skipped trigger is followed; its row
    /// c fill gives sol_in; its row c exit adds net_cheap x (live size / sol_in) to the whale's ledger as a PAPER position; a window that ends
    /// without a row c fill adds nothing
    pub(super) fn wh_on_shadow(&mut self, rec: &serde_json::Value) {
        if !self.cfg.wh_learn && !self.cfg.hl_learn { return; }
        let Some(w) = rec["w"].as_u64() else { return };
        let p = &mut self.whs.paper;
        match rec["ev"].as_str() {
            Some("presend_arm") => {
                let Some(sig) = rec["sig"].as_str() else { return };
                if !p.skipped.contains_key(sig) && !p.hskipped.contains_key(sig) { return; }
                if p.w.len() >= CE_MAX { p.full += 1; return; }
                p.w.insert(w, (sig.to_string(), None));
            }
            Some("presend_fill") => {
                if rec["row"].as_str().unwrap_or("c") != "c" { return; }
                if let Some(e) = p.w.get_mut(&w) { if e.1.is_none() { e.1 = rec["entry"]["sol_in"].as_f64().filter(|x| *x > 0.0); } }
            }
            Some("presend_disarm") => {
                if p.w.get(&w).is_some_and(|e| e.1.is_none()) { if let Some((sig, _)) = p.w.remove(&w) { p.skipped.remove(&sig); p.hskipped.remove(&sig); } }
            }
            Some("presend_exit") => {
                if rec["row"] != "c" { return; }
                let Some((sig, sol_in)) = p.w.remove(&w) else { return };
                let net = rec["net_cheap"].as_f64().or_else(|| rec["pnl"].as_f64()).unwrap_or(0.0);
                // dip37 holder ledger: a holder_loss-skipped trigger's paper position into each of its holder keys
                if let Some((keys, mint, _)) = p.hskipped.remove(&sig) {
                    let Some(sol_in) = sol_in else { return };
                    let credit = (net * self.cfg.spend as f64 / sol_in * 1e9).round() as i64;
                    p.hcredits += 1;
                    p.hcredit_sum += credit;
                    { let mut g = self.sh.hl.lock().unwrap(); for k in &keys { g.entry(*k).or_default().add(credit, true); } }
                    self.rec(serde_json::json!({"ev": "presend_live_hl_paper", "holders": keys.iter().map(b58).collect::<Vec<_>>(), "mint": b58(&mint), "sig": sig, "w": w,
                        "net_cheap": net, "sol_in": sol_in, "credit": credit as f64 / 1e9}));
                    return;
                }
                let Some((whale, mint, _)) = p.skipped.remove(&sig) else { return };
                let Some(sol_in) = sol_in else { return };
                let credit = (net * self.cfg.spend as f64 / sol_in * 1e9).round() as i64;
                p.credits += 1;
                p.credit_sum += credit;
                let h = self.sh.wh.lock().unwrap().add(self.cfg.wh_split, false, whale, credit, true);
                self.rec(serde_json::json!({"ev": "presend_live_wh_paper", "whale": b58(&whale), "mint": b58(&mint), "sig": sig, "w": w, "net_cheap": net, "sol_in": sol_in,
                    "credit": credit as f64 / 1e9, "n": h.n, "sum": h.sum as f64 / 1e9, "pn": h.pn, "ps": h.ps as f64 / 1e9,
                    "blocks": h.blocks_mode(self.cfg.wh_loss_n, self.cfg.wh_loss, self.cfg.wh_mean)}));
                self.line(format!("  PRESEND LIVE WHALE PAPER {} whale {} | shadow {:+.4} SOL -> {:+.4} at our size | ledger {:+.4} over {} ({} paper)", b58(&mint), &b58(&whale)[..8],
                    net, credit as f64 / 1e9, h.sum as f64 / 1e9, h.n, h.pn));
            }
            _ => {}
        }
    }

    /// the status line's part ("" with the ledger off)
    pub(super) fn wh_status(&self) -> String {
        if !self.cfg.wh_on() { return String::new(); }
        let p = &self.whs.paper;
        format!(" | WHALE LEDGER {}: skips T2 {} re-arm {}{}", self.sh.wh.lock().unwrap().all.len(), self.whs.skips[0], self.whs.skips[1],
            if self.cfg.wh_learn { format!(", paper credits {} ({:+.3} SOL)", p.credits, p.credit_sum as f64 / 1e9) } else { String::new() })
    }

    /// the state, every ~10 min (written off the event loop; nothing without --presend-live-whale-state)
    pub(super) fn wh_tick(&mut self, slot_now: u64) {
        let Some(p) = self.cfg.wh_state.clone() else { return };
        if slot_now < self.whs.saved + CR_SAVE_SLOTS { return; }
        if self.whs.saved > 0 {
            let m = self.sh.wh.lock().unwrap().clone();
            std::thread::spawn(move || { if let Err(e) = wh_save(&m, &p) { eprintln!("DIP PRESEND LIVE WHALE LEDGER: NOT saved to {p}: {e:#}"); } });
        }
        self.whs.saved = slot_now;
    }

    /// the run's end: the state saved (nothing without the file)
    pub(super) fn wh_finish(&mut self) -> Option<serde_json::Value> {
        if !self.cfg.wh_on() { return None; }
        if let Some(p) = self.cfg.wh_state.clone() {
            let m = self.sh.wh.lock().unwrap().clone();
            match wh_save(&m, &p) {
                Ok(n) => self.line(format!("  PRESEND LIVE WHALE LEDGER: {n} wallets saved to {p}")),
                Err(e) => self.line(format!("  PRESEND LIVE WHALE LEDGER: NOT saved to {p}: {e:#}")),
            }
        }
        let g = self.sh.wh.lock().unwrap();
        let p = &self.whs.paper;
        Some(serde_json::json!({"wallets": g.all.len(), "wallets_t2": g.t2.len(), "wallets_re": g.re.len(), "skips_t2": self.whs.skips[0], "skips_rearm": self.whs.skips[1],
            "paper_credits": p.credits, "paper_sum": p.credit_sum, "paper_full": p.full}))
    }
}

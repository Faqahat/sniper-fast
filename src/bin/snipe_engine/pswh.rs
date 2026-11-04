// =====================================================================================================================
// dip37 LIVE WHALE / DUMPER LOSS LEDGER (owner approved going live, 11-04 via the coordinator). The creator ledger's mirror
// (--presend-live-cr-loss N:SOL + --presend-live-creator-state PATH, cr_gate), keyed on the ARM's wallet instead of the creator:
//   T2: the trigger whale (trig.wallet); re-arm: the dumper (dump.seller).
//   --presend-live-wh-loss N:SOL       skip the arm ("wh_loss" T2 / "rearm_wh_loss" re-arm) when that wallet's PRIOR realized positions with
//                                      us number >= N and sum to <= -SOL; the skip record gets wh_wallet, wh_n, wh_sum (SOL). Decided with the
//                                      other arm-time skips (right after the creator gate), never on the sender thread
//   --presend-live-wh-loss-mode sum|mean  (default sum) the rule: sum = n >= N and sum <= -SOL; mean = n >= N and sum / n <= -SOL (SOL read as
//                                      the per-position average loss). Every T2 / re-arm arm and skip record gets wh_n, wh_sum, wh_sum_hit and
//                                      wh_mean_hit (both rules' verdicts, whichever is live) while the ledger is on
//   --presend-live-whale-state PATH    the ledger preloaded at the start (the seed: ops/strategies/presend/prevent/forward/whale_seed.py, or the
//                                      last run's save; a missing file = an empty ledger, a NOTE) and saved back every ~10 min and at the run's end
// The ledger takes every presend_live_realized of a position whose window's arm wallet is known (the window id -> wallet, kept at the arm);
// a skipped arm never fills, so it never adds to it. State file: {"v": 1, "w": {wallet: [positions, realized lamports]}}.
// Off (no --presend-live-wh-loss): nothing of it runs, every record and decision dip36's.
// =====================================================================================================================
use super::*;

/// one wallet's realized positions with us and their summed P&L (lamports)
#[derive(Clone, Copy, Debug, Default, PartialEq, Eq)]
pub struct WhHist { pub n: u32, pub sum: i64 }

impl WhHist {
    pub fn add(&mut self, pnl: i64) { self.n += 1; self.sum += pnl; }
    /// the SUM rule: >= n_min positions and their sum <= -loss (loss 0 = off: never)
    pub fn blocks(&self, n_min: u32, loss: i64) -> bool { loss > 0 && self.n >= n_min && self.sum <= -loss }
    /// the MEAN rule: >= n_min positions (>= 1) and sum / n <= -loss (exact: sum <= -loss x n)
    pub fn blocks_mean(&self, n_min: u32, loss: i64) -> bool {
        loss > 0 && self.n >= n_min.max(1) && (self.sum as i128) <= -(loss as i128) * self.n as i128
    }
    /// the live rule (`mean`: --presend-live-wh-loss-mode mean)
    pub fn blocks_mode(&self, n_min: u32, loss: i64, mean: bool) -> bool { if mean { self.blocks_mean(n_min, loss) } else { self.blocks(n_min, loss) } }
}

/// --presend-live-wh-loss N:SOL -> (N, SOL in lamports): N 1..50 positions, SOL in (0, 5]
pub fn wh_loss_parse(s: &str) -> Result<(u32, i64)> {
    let bad = || anyhow::anyhow!("--presend-live-wh-loss N:SOL (positions 1..50, realized sum SOL in (0, 5]), e.g. 2:0.05; got '{s}'");
    let (n, v) = s.split_once(':').ok_or_else(bad)?;
    let (n, v): (u32, f64) = (n.parse().map_err(|_| bad())?, v.parse().map_err(|_| bad())?);
    if !(1..=50).contains(&n) || !(v > 0.0 && v <= 5.0) { return Err(bad()); }
    Ok((n, (v * 1e9).round() as i64))
}

/// the gate at an arm: (blocks by the live rule, the wallet's history: zero when unknown). None: the ledger off
pub(super) fn wh_gate(sh: &Shared, cfg: &Cfg, w: &Pk) -> Option<(bool, WhHist)> {
    if !cfg.wh_on() { return None; }
    let h = sh.wh.lock().unwrap().get(w).copied().unwrap_or_default();
    Some((h.blocks_mode(cfg.wh_loss_n, cfg.wh_loss, cfg.wh_mean), h))
}

/// an arm / skip record's fields (sum in SOL, as the creator ledger's "cr".sum): the wallet, its history, both rules' verdicts
pub fn wh_fields(r: &mut serde_json::Value, cfg: &Cfg, w: &Pk, h: &WhHist) {
    r["wh_wallet"] = b58(w).into();
    r["wh_n"] = h.n.into();
    r["wh_sum"] = (h.sum as f64 / 1e9).into();
    r["wh_sum_hit"] = h.blocks(cfg.wh_loss_n, cfg.wh_loss).into();
    r["wh_mean_hit"] = h.blocks_mean(cfg.wh_loss_n, cfg.wh_loss).into();
}

/// the state file -> the ledger
pub fn wh_parse(b: &[u8]) -> Result<FxHashMap<Pk, WhHist>> {
    let j: serde_json::Value = serde_json::from_slice(b).context("parse")?;
    let mut m = FxHashMap::default();
    for (w, v) in j["w"].as_object().context("no \"w\" object")? {
        let Some(pk) = bs58::decode(w).into_vec().ok().and_then(|x| <[u8; 32]>::try_from(x).ok()) else { bail!("bad wallet {w}") };
        let (Some(n), Some(s)) = (v[0].as_u64(), v[1].as_i64()) else { bail!("{w}: not [positions, lamports]") };
        m.insert(pk, WhHist { n: n.min(u32::MAX as u64) as u32, sum: s });
    }
    Ok(m)
}
pub fn wh_load(path: &str) -> Result<FxHashMap<Pk, WhHist>> {
    let b = std::fs::read(path).with_context(|| format!("read {path}"))?;
    wh_parse(&b).with_context(|| path.to_string())
}

/// save the ledger (PATH.tmp, then renamed) -> wallets saved
pub fn wh_save(m: &FxHashMap<Pk, WhHist>, path: &str) -> Result<usize> {
    let w: serde_json::Map<String, serde_json::Value> = m.iter().map(|(k, h)| (b58(k), serde_json::json!([h.n, h.sum]))).collect();
    let tmp = format!("{path}.tmp");
    std::fs::write(&tmp, serde_json::json!({"v": 1, "w": w}).to_string()).with_context(|| format!("write {tmp}"))?;
    std::fs::rename(&tmp, path).with_context(|| format!("rename {tmp}"))?;
    Ok(m.len())
}

/// the probe's ledger side: every window's arm wallet (window id -> whale / dumper), the last save's slot, the skips
#[derive(Debug, Default)]
pub struct WhSt { pub win: FxHashMap<u64, Pk>, pub saved: u64, pub skips: [u64; 2] }

impl PsLive {
    /// an armed window's wallet (nothing with the ledger off)
    pub(super) fn wh_arm(&mut self, id: u64, w: Pk) { if self.cfg.wh_on() { self.whs.win.insert(id, w); } }

    /// a skip by the ledger: counted, a line (T2: `rearm` false)
    pub(super) fn wh_skip_line(&mut self, mint: &Pk, w: &Pk, h: &WhHist, rearm: bool) {
        self.whs.skips[rearm as usize] += 1;
        self.line(format!("  PRESEND LIVE {}WHALE-LOSS SKIP {} | {} {} has {} positions with us, {:+.4} SOL (rule {})", if rearm { "REARM " } else { "" }, b58(mint),
            if rearm { "dumper" } else { "whale" }, &b58(w)[..8], h.n, h.sum as f64 / 1e9, self.cfg.wh_spec()));
    }

    /// the status line's part ("" with the ledger off)
    pub(super) fn wh_status(&self) -> String {
        if !self.cfg.wh_on() { return String::new(); }
        format!(" | WHALE LEDGER {}: skips T2 {} re-arm {}", self.sh.wh.lock().unwrap().len(), self.whs.skips[0], self.whs.skips[1])
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
        Some(serde_json::json!({"wallets": self.sh.wh.lock().unwrap().len(), "skips_t2": self.whs.skips[0], "skips_rearm": self.whs.skips[1]}))
    }
}

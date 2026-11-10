// =====================================================================================================================
// dip36 LIVE WALLET BLOCKLIST (owner OK 11-05 PKT via the coordinator: the ONE live decision change of dip36). Behind
// --presend-live-blocklist PATH (off when not given: nothing of it runs, every record dip35's).
//   * PATH: {"wallets": [{"w": "<full base58>", "why": "..."}], "version": N}; full 32-byte keys only; an empty list is valid (blocks
//     nothing). Read at the start (a bad / missing file refuses the start), re-read when its mtime changes (checked every ~10 s from tick(),
//     off the send path); a reload that fails keeps the last good list; every reload and every failure is a presend_live_blocklist record.
//   * at ARM time, with the other arm-time skips (after the creator gate; only a trigger that would arm): SKIP when a listed wallet is
//       T2:     the trigger whale (role "whale")                         -> presend_live_skip why "blocklist"
//       re-arm: the dumper (role "dumper")                               -> presend_live_skip kind rearm why "rearm_blocklist"
//       both:   a holder with >= --presend-live-blocklist-pct (3.0) % of supply now (the detector's book; ours never) (role "holder")
//     the skip record gets bl_wallet, bl_role, bl_pct (its holding, % of supply) and bl_why (the list's reason). One hash lookup per
//     candidate wallet; nothing on the sender thread.
// =====================================================================================================================
use super::*;

/// the reload check's period
pub const BL_CHECK: Duration = Duration::from_secs(10);
/// the holder threshold's default (% of supply)
pub const BL_PCT: f64 = 3.0;

/// the list file: wallet -> its reason; the file's "version"
pub fn bl_parse(b: &[u8]) -> std::result::Result<(FxHashMap<Pk, String>, serde_json::Value), String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    let a = v["wallets"].as_array().ok_or("no \"wallets\" array")?;
    let mut m = FxHashMap::default();
    for e in a {
        let s = e["w"].as_str().ok_or(format!("an entry without \"w\": {e}"))?;
        let k: Pk = bs58::decode(s.trim()).into_vec().ok().and_then(|x| x.try_into().ok()).ok_or(format!("bad address {s}"))?;
        m.insert(k, e["why"].as_str().unwrap_or("").to_string());
    }
    Ok((m, v["version"].clone()))
}

pub struct Blocklist {
    pub path: String,
    pub set: FxHashMap<Pk, String>,
    pub ver: serde_json::Value,
    mtime: Option<std::time::SystemTime>,
    checked: Instant,
    pub reloads: u64,
    pub fails: u64,
    pub skips: u64,
}

impl Blocklist {
    pub fn load(path: &str) -> Result<Blocklist> {
        let b = std::fs::read(path).with_context(|| format!("--presend-live-blocklist {path}"))?;
        let (set, ver) = bl_parse(&b).map_err(|e| anyhow::anyhow!("--presend-live-blocklist {path}: {e}"))?;
        Ok(Blocklist { path: path.to_string(), set, ver, mtime: std::fs::metadata(path).and_then(|m| m.modified()).ok(), checked: Instant::now(), reloads: 0, fails: 0, skips: 0 })
    }

    /// the reload check (every BL_CHECK; `force`: now): Some(record) when the file changed (reloaded or failed)
    pub fn check(&mut self, force: bool) -> Option<serde_json::Value> {
        if !force && self.checked.elapsed() < BL_CHECK { return None; }
        self.checked = Instant::now();
        let mt = std::fs::metadata(&self.path).and_then(|m| m.modified());
        let r = match mt {
            Ok(t) if !force && Some(t) == self.mtime => return None,
            Ok(t) => { self.mtime = Some(t); std::fs::read(&self.path).map_err(|e| e.to_string()).and_then(|b| bl_parse(&b)) }
            Err(e) => {
                // a missing file: logged once per change (the last good list stays)
                if self.mtime.is_none() && !force { return None; }
                self.mtime = None;
                Err(format!("stat: {e}"))
            }
        };
        Some(match r {
            Ok((set, ver)) => {
                let was = self.set.len();
                self.set = set;
                self.ver = ver;
                self.reloads += 1;
                serde_json::json!({"ev": "presend_live_blocklist", "ok": true, "path": self.path, "n": self.set.len(), "was": was, "version": self.ver})
            }
            Err(e) => {
                self.fails += 1;
                serde_json::json!({"ev": "presend_live_blocklist", "ok": false, "path": self.path, "err": e, "kept": self.set.len(), "version": self.ver})
            }
        })
    }

    /// the arm's check: the trigger whale / re-arm dumper (`who`, its role, its holding raw) first, then the holders >= `min` raw (biggest
    /// first) -> (wallet, role, % of supply, the list's reason)
    pub fn hit(&self, who: (&Pk, &'static str, i64), holders: &[(Pk, i64)], min: i64) -> Option<(Pk, &'static str, f64, String)> {
        let pct = |b: i64| b as f64 / pl::SUPPLY * 100.0;
        if let Some(why) = self.set.get(who.0) { return Some((*who.0, who.1, pct(who.2), why.clone())); }
        holders.iter().filter(|(_, b)| *b >= min).find_map(|(k, b)| self.set.get(k).map(|why| (*k, "holder", pct(*b), why.clone())))
    }

    /// tests: the next check() reads the file
    #[cfg(test)]
    pub fn mtime_reset_for_test(&mut self) { self.mtime = None; self.checked = Instant::now().checked_sub(Duration::from_secs(60)).unwrap_or_else(Instant::now); }

    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"path": self.path, "n": self.set.len(), "version": self.ver, "reloads": self.reloads, "reload_fails": self.fails, "skips": self.skips})
    }
}

/// the holder threshold in raw token units (3.0% = 30,000,000,000,000 exactly)
pub fn bl_min(pct: f64) -> i64 { (pct * 1e13).round() as i64 }

impl PsLive {
    /// dip36: the blocklist's verdict for an arm of `mint` (None: off, or nothing listed): `who` = the T2 whale / re-arm dumper
    pub(super) fn bl_hit(&self, mint: &Pk, who: &Pk, role: &'static str, who_bal: Option<i64>) -> Option<(Pk, &'static str, f64, String)> {
        let b = self.bl.as_ref()?;
        let min = bl_min(self.cfg.blocklist_pct);
        let holders = self.det.holders_at_least(mint, min, &self.user).unwrap_or_default();
        let wb = who_bal.unwrap_or_else(|| self.det.bal(mint, who));
        // dip38: the token's launcher (its create tx's fee payer) last: a whale / dumper / holder hit keeps dip37c's record
        b.hit((who, role, wb), &holders, min).or_else(|| self.bl_launcher(mint).map(|(k, p, why)| (k, "launcher", p, why)))
    }

    /// dip38 --presend-live-blocklist-launcher (LIVE, default on with the blocklist): the token's launcher is listed -> (launcher, its holding
    /// now (% of supply), the list's reason); None: off, not listed, or the create was not seen
    pub(super) fn bl_launcher(&self, mint: &Pk) -> Option<(Pk, f64, String)> {
        if !self.cfg.blocklist_launcher { return None; }
        let b = self.bl.as_ref()?;
        let l = self.l38.launch.get(mint)?;
        let why = b.set.get(&l.payer)?;
        Some((l.payer, self.det.bal(mint, &l.payer) as f64 / pl::SUPPLY * 100.0, why.clone()))
    }

    /// dip37c PER-SEND blocklist: the largest listed holder >= the threshold of `mint` now (the whale / dumper included: a listed one never
    /// arms), None: none / the flag off. Main loop only (on a listed wallet's trade of an armed mint, at the arm, after a reload)
    pub(super) fn bl_send_hit(&self, mint: &Pk) -> Option<(Pk, f32)> {
        let b = self.bl.as_ref().filter(|_| self.cfg.blocklist_send)?;
        let min = bl_min(self.cfg.blocklist_pct);
        self.det.holders_at_least(mint, min, &self.user).unwrap_or_default().into_iter().find(|(k, _)| b.set.contains_key(k)).map(|(k, v)| (k, (v as f64 / pl::SUPPLY * 100.0) as f32))
            // dip38: a listed launcher (after a reload: a listed one never arms) withholds too (its holding as the %)
            .or_else(|| self.bl_launcher(mint).map(|(k, p, _)| (k, p as f32)))
    }

    /// dip37c: the armed window of `mint`'s cached listed holder (the sender reads it with the window); `force`: whatever traded
    pub(super) fn bl_send_refresh(&mut self, mint: &Pk, trader: Option<&Pk>) {
        if !self.cfg.blocklist_send { return; }
        let Some(&id) = self.armed.get(mint) else { return };
        // only a listed wallet's trade can change a listed holding (O(1) for every other trade)
        if let Some(u) = trader { if !self.bl.as_ref().is_some_and(|b| b.set.contains_key(u)) { return; } }
        let h = self.bl_send_hit(mint);
        let mut g = self.sh.wins.lock().unwrap();
        if let Some(w) = g.iter_mut().find(|w| w.id == id) { w.blk = h; }
    }

    /// dip37c: the per-send blocklist's status part ("" without it)
    pub(super) fn bl_send_status(&self) -> String {
        if !self.cfg.blocklist_send { return String::new(); }
        let l = |a: &[AtomicU64; 2]| format!("{}/{}", a[0].load(Ordering::Relaxed), a[1].load(Ordering::Relaxed));
        format!(" | BLOCKLIST PER-SEND {} T2/re-arm: withheld {} would (log) {}", if self.sh.bl_send_live.load(Ordering::Relaxed) { "live" } else { "LOG" },
            l(&self.sh.bl_withheld), l(&self.sh.bl_would))
    }

    /// dip36: the skip record's fields
    pub(super) fn bl_fields(r: &mut serde_json::Value, h: &(Pk, &'static str, f64, String)) {
        r["bl_wallet"] = b58(&h.0).into();
        r["bl_role"] = h.1.into();
        r["bl_pct"] = ((h.2 * 1000.0).round() / 1000.0).into();
        r["bl_why"] = h.3.clone().into();
    }
}

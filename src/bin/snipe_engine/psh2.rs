// =====================================================================================================================
// dip37 HYBRID-2 inputs (owner approved; proposal /home/it/sniper-studies/sniper-hybrid2/FROZEN.md, verification sniper-data/hybrid2_verify):
//   --presend-live-m2seen-log on|off (off)   LOG ONLY: per mint, the dumps dipmode's M2 path scored (every "dump" record: the IMIT1-envelope
//                                            dumps, M2 score or none) -> on every presend_live_arm and its skip records (T2: every skip;
//                                            re-arm: the holders check's skips):
//                                              nd      = the mint's scored dumps strictly before the arm's trigger in CHAIN order (slot, in-block
//                                                        index): the re-arm's own trigger dump (the same position) is never counted
//                                              m2max   = their highest M2 score (a dump without one counts -1; -1 when none)
//                                              h2_keep = nd >= 1 AND (re-arm OR T2 token age >= 30 slots)   (HYBRID-2's arm rule, never acted on)
//                                              h2_size = 1.0 SOL when m2max >= -0.02, else the window's size (SOL)   (log only; no size-up built)
//   --presend-live-m2seen-gate on|off (off)  LIVE when on: skip an arm with nd = 0 ("m2_unseen" T2 / "rearm_m2_unseen" re-arm), with the
//                                            other arm-time skips (after the whale ledger). Turns the counter on too. The T2 age part of HYBRID-2
//                                            is the existing --presend-live-min-age-slots N (T2 only: "young_age" when trigger slot - create slot < N)
// The dump notes: M2Dump::finish / the plain dump record push (mint, slot, idx, score) into DUMPS (only while M2SEEN is set by a run's
// start); the probe drains them at the top of on_exec (every dump of a tx is recorded before pslive.on_exec of that tx). The map is
// bounded: a mint the detector no longer follows (or never did: no arm can come on it) is dropped every 2048 slots; per mint the newest
// MAX_PER_MINT dumps are kept, the older ones folded into a (count, max) prefix (all of them are before any later trigger).
// =====================================================================================================================
use super::*;

/// a run's start sets it (the M2 / dump path then notes every scored dump)
pub static M2SEEN: AtomicBool = AtomicBool::new(false);
static DUMPS: Mutex<Vec<(Pk, u64, u32, Option<f64>)>> = Mutex::new(Vec::new());

/// HYBRID-2's thresholds (FROZEN.md)
pub const H2_AGE: u64 = 30;
pub const H2_M2: f64 = -0.02;
pub const H2_BIG: u64 = 1_000_000_000;
pub const MAX_PER_MINT: usize = 256;

/// dipmode's dump record (mint base58, slot, idx) and its M2 score: noted for the probe (nothing unless a run turned it on)
pub fn note_rec(rec: &serde_json::Value, score: Option<f64>) {
    if !M2SEEN.load(Ordering::Relaxed) { return; }
    let (Some(m), Some(s), Some(i)) = (rec["mint"].as_str(), rec["slot"].as_u64(), rec["idx"].as_u64()) else { return };
    let Some(mint) = bs58::decode(m).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok()) else { return };
    DUMPS.lock().unwrap_or_else(|e| e.into_inner()).push((mint, s, i as u32, score));
}

/// one mint's scored dumps: the folded oldest (count, max) and the newest ones (slot, idx, score; -1 = none)
#[derive(Debug, Default, Clone)]
pub struct MSeen { old_n: u32, old_max: f64, v: VecDeque<(u64, u32, f64)> }

/// the probe's counter
#[derive(Debug, Default)]
pub struct H2 { pub map: FxHashMap<Pk, MSeen>, last_prune: u64, pub notes: u64 }

impl H2 {
    /// a scored dump (any order of arrival; kept sorted by chain position)
    pub fn note(&mut self, mint: Pk, s: u64, i: u32, m2: Option<f64>) {
        self.notes += 1;
        let e = self.map.entry(mint).or_insert_with(|| MSeen { old_max: -1.0, ..Default::default() });
        let x = (s, i, m2.unwrap_or(-1.0));
        let at = e.v.iter().rposition(|y| (y.0, y.1) <= (s, i)).map_or(0, |p| p + 1);
        e.v.insert(at, x);
        while e.v.len() > MAX_PER_MINT { if let Some(o) = e.v.pop_front() { e.old_n += 1; e.old_max = e.old_max.max(o.2); } }
    }
    /// (nd, m2max) of a trigger at chain position (s, i): the dumps strictly before it
    pub fn view(&self, mint: &Pk, s: u64, i: u32) -> (u32, f64) {
        let Some(e) = self.map.get(mint) else { return (0, -1.0) };
        let (mut n, mut mx) = (e.old_n, if e.old_n > 0 { e.old_max } else { -1.0 });
        for y in e.v.iter().take_while(|y| (y.0, y.1) < (s, i)) { n += 1; mx = mx.max(y.2); }
        (n, mx)
    }
    /// drop mints the detector does not follow (every 2048 slots)
    pub fn prune(&mut self, det: &pl::Detector, slot: u64) {
        if slot < self.last_prune + 2048 { return; }
        self.last_prune = slot;
        self.map.retain(|m, _| det.create_slot(m).is_some());
    }
    /// take the noted dumps (the run's queue)
    pub fn drain(&mut self) {
        let v = std::mem::take(&mut *DUMPS.lock().unwrap_or_else(|e| e.into_inner()));
        for (m, s, i, sc) in v { self.note(m, s, i, sc); }
    }
}

/// the record fields (HYBRID-2's verdict, log only): `rearm`, the T2 token age, the window's size (lamports)
pub fn fields(r: &mut serde_json::Value, nd: u32, m2max: f64, rearm: bool, age: u64, size: u64) {
    r["nd"] = nd.into();
    r["m2max"] = m2max.into();
    r["h2_keep"] = (nd >= 1 && (rearm || age >= H2_AGE)).into();
    r["h2_size"] = (if m2max >= H2_M2 { H2_BIG } else { size } as f64 / 1e9).into();
}

// =====================================================================================================================
// dip47 GRPSIGN (LOG ONLY; --presend-live-grpsign-log on, default off = dip46 byte for byte): the dip30 GROUP RISK metric (the fill
// annotation's ann.grp_pct: holders >= 2% of supply still holding, ours out, top 12 by holding, each with >= 5 holds at risk and a 3-slot
// sell hazard >= 0.3 at its hold age; their holdings summed) computed on the state the SENDER signs a try with, instead of at our landing.
//
// The state at signing: the sender signs from its window copy (SWin), whose curve / pos / landing-guard set the main loop refreshes
// after every trade of the armed mint (pos = that trade's (slot, idx, j)). The same moment, with this flag on, the main loop computes
// the group metric from the detector's holder book + hold clocks (exactly what grd_set reads for the landing guard set the try carries)
// and keeps it per window keyed by that pos (a ring of 64). A try registered by the main loop (drain_atts) is matched to its
// snapshot by its sign_pos (= the SWin pos the sender read): exact, else the newest at or before it ((slot, idx)), else the arm's.
// Nothing runs on the sender thread: no new field in SWin / Att, no lock, no read; the work is on the main loop, already-held state only
// (no RPC), and only for armed windows. Probe tries / probe windows (dip46) are never looked at.
//
// Records: "presend_live_grpsign" {w, mint, kind (t2 | rearm | wide | qf2), slot (the try's send slot), at (first_try | fill_try),
// grp_pct, n, members [{w, pct}], would_block_t2 (kind t2 && grp_pct >= 3), would_block_6 (grp_pct >= 6), sign_pos, snap_pos, match};
// presend_live_fill gets "grpsign" {pct, would_block_t2}. One line per window at its first try.
// =====================================================================================================================
use super::*;

pub const FLAG: &str = "--presend-live-grpsign-log";
/// the T2 skip threshold under study (% of supply) and the landing version's block threshold
pub const T2_PCT: f64 = 3.0;
pub const BLOCK_PCT: f64 = 6.0;
/// the landing version's holder set: >= 2% of supply, top 12
pub const MIN_FRAC: f64 = 0.02;
pub const TOP: usize = 12;
const RING: usize = 64;
const MAX_WINS: usize = 512;

pub type Pos = (u64, u32, i32);

/// one snapshot: the group at a trade of the armed mint (no allocation)
#[derive(Clone, Copy, Debug)]
pub struct Snap { pub slot: u64, pub pct: f64, pub n: u8, pub m: [(Pk, i64); TOP] }

#[derive(Default)]
pub struct G47 {
    rings: FxHashMap<u64, VecDeque<(Pos, Snap)>>,
    order: VecDeque<u64>,
    first: FxHashSet<u64>,
    /// snapshots taken, their total compute time (ns, main loop), windows with a first-try record, fill records
    pub snaps: u64,
    pub snap_ns: u64,
    pub firsts: u64,
    pub fills: u64,
}

/// the snapshot a try signed at `sp` saw: exact pos, else the newest at or before (slot, idx), else the window's first (the arm's)
pub fn find(ring: &VecDeque<(Pos, Snap)>, sp: Pos) -> Option<(&Snap, Pos, &'static str)> {
    if let Some((p, s)) = ring.iter().rev().find(|(p, _)| *p == sp) { return Some((s, *p, "exact")); }
    if let Some((p, s)) = ring.iter().rev().find(|(p, _)| (p.0, p.1) <= (sp.0, sp.1)) { return Some((s, *p, "before")); }
    ring.front().map(|(p, s)| (s, *p, "arm"))
}

/// the group metric on the detector's state now (the landing version's definition; pl::Detector::grp_now)
pub fn snap_of(det: &pl::Detector, mint: &Pk, user: &Pk, slot: u64) -> Snap {
    let mut m = [([0u8; 32], 0i64); TOP];
    let (pct, n) = det.grp_now(mint, (MIN_FRAC * pl::SUPPLY) as i64, user, slot, TOP, &mut m);
    Snap { slot, pct, n: n as u8, m }
}

impl Snap {
    /// the group without one wallet (the window's trigger whale / re-arm dumper: the wallet whose dump the window waits for), summed in the
    /// same order; whether it was a member
    pub fn without(&self, x: &Pk) -> (f64, bool) {
        let mut p = -0.0f64;
        let mut hit = false;
        for (w, b) in &self.m[..self.n as usize] { if w == x { hit = true; } else { p += *b as f64 / pl::SUPPLY * 100.0; } }
        (p, hit)
    }
    pub fn members_json(&self) -> serde_json::Value {
        self.m[..self.n as usize].iter().map(|(w, b)| serde_json::json!({"w": b58(w), "pct": *b as f64 / pl::SUPPLY * 100.0})).collect::<Vec<_>>().into()
    }
}

impl G47 {
    /// a window's snapshots kept (tests)
    pub fn rings_len(&self, w: u64) -> usize { self.rings.get(&w).map_or(0, |r| r.len()) }
}

impl PsLive {
    /// the window's group at this trade of its mint / its arm (main loop; only with the flag on)
    pub(super) fn g47_snap(&mut self, w: u64, mint: &Pk, pos: Pos, slot: u64) {
        if !self.cfg.grpsign { return; }
        let t0 = arbx::fast::mono_ns();
        let s = snap_of(&self.det, mint, &self.user, slot);
        let g = &mut self.g47;
        if !g.rings.contains_key(&w) {
            g.order.push_back(w);
            while g.order.len() > MAX_WINS { if let Some(o) = g.order.pop_front() { g.rings.remove(&o); g.first.remove(&o); } }
        }
        let r = g.rings.entry(w).or_default();
        if r.back().is_some_and(|(p, _)| *p == pos) { r.pop_back(); }
        r.push_back((pos, s));
        while r.len() > RING { r.pop_front(); }
        g.snaps += 1;
        g.snap_ns += arbx::fast::mono_ns().saturating_sub(t0);
    }

    pub(super) fn g47_kind(&self, w: u64) -> &'static str {
        if self.rearm_w(w) { return "rearm"; }
        if let Some((k, _)) = self.wd_win(w) { return k.key(); }
        "t2"
    }

    /// the record of a try's group at its signing (None: no snapshot of its window)
    fn g47_rec(&self, a: &Att, at: &str) -> Option<(serde_json::Value, f64, u8, bool, f64)> {
        let ring = self.g47.rings.get(&a.w)?;
        let (s, sp, how) = find(ring, a.sign_pos)?;
        let kind = self.g47_kind(a.w);
        let wb = kind == "t2" && s.pct >= T2_PCT;
        let wh = self.wins.get(&a.w).map_or([0u8; 32], |w| w.whale);
        let (px, whale_in) = s.without(&wh);
        let r = serde_json::json!({"ev": "presend_live_grpsign", "w": a.w, "mint": b58(&a.mint), "kind": kind, "slot": a.slot, "at": at, "try": a.n,
            "grp_pct": s.pct, "n": s.n, "members": s.members_json(), "would_block_t2": wb, "would_block_6": s.pct >= BLOCK_PCT,
            "whale_in": whale_in, "grp_pct_x": px, "would_block_t2_x": kind == "t2" && px >= T2_PCT,
            "sign_pos": [a.sign_pos.0, a.sign_pos.1, a.sign_pos.2], "snap_pos": [sp.0, sp.1, sp.2], "snap_slot": s.slot, "match": how});
        Some((r, s.pct, s.n, wb, px))
    }

    /// a real try registered (drain_atts): its window's first one -> the record and the line
    pub(super) fn g47_att(&mut self, a: &Att) {
        if !self.cfg.grpsign || self.g47.first.contains(&a.w) { return; }
        let Some((r, pct, n, wb, px)) = self.g47_rec(a, "first_try") else { return };
        self.g47.first.insert(a.w);
        self.g47.firsts += 1;
        let kind = self.g47_kind(a.w);
        self.rec(r);
        self.line(format!("  PRESEND LIVE GRPSIGN (log) w{} {} {}: {:.1}% ({}) [whale out {:.1}%] -> {}", a.w, b58(&a.mint), kind, pct, n, px, if wb { "would skip" } else { "no" }));
    }

    /// the fill's try: its record, and the fill record's "grpsign" (None with the flag off)
    pub(super) fn g47_fill(&mut self, a: &Att) -> Option<serde_json::Value> {
        if !self.cfg.grpsign { return None; }
        match self.g47_rec(a, "fill_try") {
            Some((r, pct, _, wb, px)) => {
                self.g47.fills += 1;
                let wbx = r["would_block_t2_x"].clone();
                self.rec(r);
                Some(serde_json::json!({"pct": pct, "would_block_t2": wb, "pct_x": px, "would_block_t2_x": wbx}))
            }
            None => Some(serde_json::json!({"pct": null, "would_block_t2": false, "miss": true})),
        }
    }
}

// =====================================================================================================================
// dip34 LOG-ONLY annotations (owner 11-04 ~00:00 PKT, for AMS runs 51/52). Each behind its own flag, OFF by default: with every flag
// off nothing of it runs and no record changes (`L34::default()`: no book is kept). NEVER acted on: no arm, skip, attempt or exit
// reads any of it.
//   * --presend-live-seen-log [H] (hours, default 3; (0, 48]): every T2 arm / skip record gets "seen" = was the trigger whale the whale
//     of a "cr_loss" / "quiet3_a" T2 skip or the dumper of a "rearm_cr_loss" re-arm skip in the last H hours (before this trigger):
//     {hit, n, why: [...], mints: [8-char], min_ago: [...]} (the last <= SEEN_MAX_PER per whale). r47-r50: such T2 fills realized
//     -0.61 SOL over 20 fills, mostly r50 (FfW5e8gK, 2H6DwrqA, EKMxQQAU...). Re-arm arm records get it keyed on the dumper.
//   * --presend-live-eqgrp-log: the T2 arm / skip, re-arm arm and fill records get "eqgrp" = the largest group of >= 2 non-whale
//     holders >= 2% (not us) holding EQUAL amounts (within 0.05 percentage points of supply, or the token amounts within 0.5%, of the
//     group's largest): {n, pct (mean, % of supply), sum, wallets, flag: n >= 2, n3: n >= 3, groups}; {n: 0} when none. A coordinated
//     bundle (r50 losses 79VUfAUd three x 9.0%, 8Hpobe16 two x 3.0%).
//   * --presend-live-q4-log (QUIET4, ops/strategies/presend/filters3/quiet4/FROZEN.json): the T2 arm / skip and re-arm arm records get
//     "q4" = {wh_l10: [n, mean followers | null] (the whale's / dumper's last <= 10 dumps of QUIET's DumpBook, window closed, 24 h; [0,
//     null] without the book), hs: [{w, pct, n}] (holders >= 2% at the arm, not the whale, not us, that sold >= 0.3 SOL into OUR holds
//     on >= 3 of our positions known in the last 24 h), hs_n, wh_unf1h (the whale's / dumper's last position with us, known within 1
//     h, was NOT followed: dip32's `followed`), wh_last1h (it had one)}; a T2 record with QUIET also gets "quiet"."wh_l10". The rolling
//     maps are fed at every closed position (its hold tape: first buy < (slot, idx) <= the last sell landing).
//   * (folded into --presend-live-ann on, coordinator 11-04) "ann".cr_hold / cr_big: the creator's holding now (% of supply; = cr_pct)
//     and >= 20% (r50 9rgBypb1: the creator held 33.9%, kept the re-arm window open as the ">= 6% holder", dumped 5.87 SOL into our
//     hold). The re-arm's holders-check skip records get "ann" too.
// =====================================================================================================================
use super::*;

/// seen: the most skips kept per whale
pub const SEEN_MAX_PER: usize = 16;
/// eqgrp: holders from 2% of supply; equal = within 0.05 percentage points or 0.5% of the token amount
pub const EQ_MIN: f64 = 0.02;
pub const EQ_PP: f64 = 0.05;
pub const EQ_REL: f64 = 0.005;
/// q4: a hold-sell >= 0.3 SOL; a repeat hold-seller >= 3 positions in 24 h; the whale's last position within 1 h
pub const HS_MIN_SOL: u64 = 300_000_000;
pub const HS_N: usize = 3;
pub const HS_NS: u64 = 24 * 3_600_000_000_000;
pub const UNF_NS: u64 = 3_600_000_000_000;
/// q4: the whale's last <= 10 dumps
pub const WH_L: usize = 10;
/// a map above this many wallets is pruned of stale entries
const MAP_PRUNE: usize = 4096;

/// dip34 seen: whale -> its recent cr_loss / quiet3_a / rearm_cr_loss skips (time ns, why, mint), oldest first
#[derive(Default, Debug)]
pub struct SeenBook { pub h_ns: u64, m: FxHashMap<Pk, VecDeque<(u64, &'static str, Pk)>>, pub notes: u64, pub hits: u64 }

impl SeenBook {
    pub fn new(h: f64) -> SeenBook { SeenBook { h_ns: (h * 3.6e12) as u64, ..Default::default() } }
    pub fn len(&self) -> usize { self.m.len() }
    /// a skip of `whale` at `t`
    pub fn note(&mut self, whale: Pk, t: u64, why: &'static str, mint: Pk) {
        self.notes += 1;
        let q = self.m.entry(whale).or_default();
        q.push_back((t, why, mint));
        while q.len() > SEEN_MAX_PER { q.pop_front(); }
        if self.m.len() > MAP_PRUNE {
            let lo = t.saturating_sub(self.h_ns);
            self.m.retain(|_, q| q.back().is_some_and(|e| e.0 >= lo));
        }
    }
    /// the record's "seen" at `t` (skips of the last H hours up to `t`; older ones pruned)
    pub fn seen(&mut self, whale: &Pk, t: u64) -> serde_json::Value {
        let lo = t.saturating_sub(self.h_ns);
        let v: Vec<(u64, &'static str, Pk)> = match self.m.get_mut(whale) {
            Some(q) => { while q.front().is_some_and(|e| e.0 < lo) { q.pop_front(); } q.iter().filter(|e| e.0 <= t).copied().collect() }
            None => Vec::new(),
        };
        if self.m.get(whale).is_some_and(|q| q.is_empty()) { self.m.remove(whale); }
        if !v.is_empty() { self.hits += 1; }
        serde_json::json!({"hit": !v.is_empty(), "n": v.len(), "why": v.iter().map(|e| e.1).collect::<Vec<_>>(),
            "mints": v.iter().map(|e| b58(&e.2)[..8].to_string()).collect::<Vec<_>>(),
            "min_ago": v.iter().map(|e| ((t - e.0) as f64 / 6e10 * 10.0).round() / 10.0).collect::<Vec<_>>()})
    }
}

/// eqgrp: two holdings are "equal"
pub fn eq_same(a: i64, b: i64) -> bool {
    let d = (a - b).unsigned_abs() as f64;
    d <= EQ_PP / 100.0 * pl::SUPPLY || d <= EQ_REL * a.max(b) as f64
}

/// eqgrp: the groups of >= 2 equal holdings in `h` (any order), each anchored at its largest member (every member equal to it),
/// largest group first (then the larger holdings)
pub fn eq_groups(h: &[(Pk, i64)]) -> Vec<Vec<(Pk, i64)>> {
    let mut v = h.to_vec();
    v.sort_by(|a, b| b.1.cmp(&a.1).then(a.0.cmp(&b.0)));
    let mut out = Vec::new();
    let mut i = 0;
    while i < v.len() {
        let mut j = i + 1;
        while j < v.len() && eq_same(v[i].1, v[j].1) { j += 1; }
        if j - i >= 2 { out.push(v[i..j].to_vec()); }
        i = j;
    }
    out.sort_by(|a, b| b.len().cmp(&a.len()).then(b[0].1.cmp(&a[0].1)));
    out
}

/// the holders >= `min` (fraction of supply) of a followed token now, but us and `whale`, largest first (None: not followed)
pub fn holders_but(det: &pl::Detector, mint: &Pk, user: &Pk, whale: &Pk, min: f64) -> Option<Vec<(Pk, i64)>> {
    det.holders_at_least(mint, (min * pl::SUPPLY) as i64, user).map(|v| v.into_iter().filter(|h| h.0 != *whale).collect())
}

/// the "eqgrp" field from the holders (but us and the whale) >= 2%
pub fn eqgrp_json(h: &[(Pk, i64)]) -> serde_json::Value {
    let g = eq_groups(h);
    let Some(b) = g.first() else { return serde_json::json!({"n": 0}) };
    let pct: Vec<f64> = b.iter().map(|x| x.1 as f64 / pl::SUPPLY * 100.0).collect();
    let sum: f64 = pct.iter().sum();
    serde_json::json!({"n": b.len(), "pct": sum / b.len() as f64, "sum": sum, "wallets": b.iter().map(|x| b58(&x.0)).collect::<Vec<_>>(),
        "flag": b.len() >= 2, "n3": b.len() >= 3, "groups": g.len()})
}

/// q4: the sellers on our hold tape (after our first buy, at or before our last sell landing; us never) with their SOL summed
pub fn hold_sellers(tape: &VecDeque<pl::Trade>, user: &Pk, first: (u64, u64), last: (u64, u64)) -> Vec<(Pk, u64)> {
    let mut m: Vec<(Pk, u64)> = Vec::new();
    for t in tape.iter().filter(|t| !t.buy && t.user != *user && (t.s, t.i as u64) > first && (t.s, t.i as u64) <= last) {
        match m.iter_mut().find(|x| x.0 == t.user) { Some(x) => x.1 += t.sol, None => m.push((t.user, t.sol)) }
    }
    m
}

/// q4: the repeat hold-sellers (wallet -> the known times of our positions it sold >= 0.3 SOL into) and the whales' last position
/// with us (whale / dumper -> (known ns, followed))
#[derive(Default, Debug)]
pub struct Q4Book { hs: FxHashMap<Pk, VecDeque<u64>>, wl: FxHashMap<Pk, (u64, bool)>, pub notes: u64, pub hs_hits: u64, pub unf_hits: u64 }

impl Q4Book {
    /// one closed position of ours, known at `known`: its whale / dumper, followed, its hold tape's sellers
    pub fn note_pos(&mut self, known: u64, whale: Option<Pk>, followed: bool, sellers: &[(Pk, u64)]) {
        self.notes += 1;
        for (w, sol) in sellers {
            if *sol < HS_MIN_SOL { continue; }
            let q = self.hs.entry(*w).or_default();
            q.push_back(known);
            while q.len() > 64 { q.pop_front(); }
        }
        if let Some(w) = whale { self.wl.insert(w, (known, followed)); }
        if self.hs.len() > MAP_PRUNE { self.hs.retain(|_, q| q.back().is_some_and(|k| k + HS_NS >= known)); }
        if self.wl.len() > MAP_PRUNE { self.wl.retain(|_, e| e.0 + UNF_NS >= known); }
    }
    /// a wallet's hold-sells known in the 24 h up to `t0`
    pub fn hs_count(&self, w: &Pk, t0: u64) -> usize { self.hs.get(w).map_or(0, |q| q.iter().filter(|k| **k <= t0 && **k + HS_NS >= t0).count()) }
    /// the repeat hold-sellers among `holders` at `t0`: (wallet, % of supply, hold-sells)
    pub fn hs_at(&self, holders: &[(Pk, i64)], t0: u64) -> Vec<(Pk, f64, usize)> {
        holders.iter().filter_map(|(w, b)| { let n = self.hs_count(w, t0); (n >= HS_N).then(|| (*w, *b as f64 / pl::SUPPLY * 100.0, n)) }).collect()
    }
    /// the whale's last position with us known within 1 h before `t0`: Some(not followed); None: none
    pub fn unf1h(&self, whale: &Pk, t0: u64) -> Option<bool> { self.wl.get(whale).filter(|e| e.0 <= t0 && e.0 + UNF_NS >= t0).map(|e| !e.1) }
    /// the "q4" field (`wh_l10`: the DumpBook's (n, mean) when it is kept)
    pub fn json(&mut self, holders: &[(Pk, i64)], whale: &Pk, t0: u64, wh_l10: Option<(u32, f64)>) -> serde_json::Value {
        let hs = self.hs_at(holders, t0);
        let u = self.unf1h(whale, t0);
        if !hs.is_empty() { self.hs_hits += 1; }
        if u == Some(true) { self.unf_hits += 1; }
        serde_json::json!({"wh_l10": wl10_json(wh_l10), "hs": hs.iter().map(|(w, p, n)| serde_json::json!({"w": b58(w), "pct": p, "n": n})).collect::<Vec<_>>(),
            "hs_n": hs.len(), "wh_unf1h": u == Some(true), "wh_last1h": u.is_some()})
    }
}

/// [n, mean followers | null]
pub fn wl10_json(x: Option<(u32, f64)>) -> serde_json::Value {
    match x { Some((n, m)) if n > 0 => serde_json::json!([n, m]), _ => serde_json::json!([0, null]) }
}

/// the probe's dip34 log state (all None / 0 with the flags off)
#[derive(Default, Debug)]
pub struct L34 { pub sb: Option<SeenBook>, pub q4: Option<Q4Book>, pub eq_arm: [u64; 2], pub eq_fill: [u64; 2] }

impl L34 {
    pub fn new(cfg: &Cfg) -> L34 {
        L34 { sb: (cfg.seen_h > 0.0).then(|| SeenBook::new(cfg.seen_h)), q4: cfg.q4_log.then(Q4Book::default), ..Default::default() }
    }
}

impl PsLive {
    /// dip34 (log-only): an arm / skip record's "seen" / "eqgrp" / "q4" (each only with its flag). `whale`: the trigger whale (T2) or the
    /// dumper (re-arm); `s0` / `t0`: the trigger's (check's) slot and time
    pub(super) fn log34(&mut self, r: &mut serde_json::Value, mint: &Pk, whale: &Pk, s0: u64, t0: u64) {
        if let Some(sb) = self.l34.sb.as_mut() { r["seen"] = sb.seen(whale, t0); }
        if !self.cfg.eqgrp_log && self.l34.q4.is_none() { return; }
        let h = holders_but(&self.det, mint, &self.user, whale, EQ_MIN).unwrap_or_default();
        if self.cfg.eqgrp_log {
            let j = eqgrp_json(&h);
            let n = j["n"].as_u64().unwrap_or(0);
            if n >= 2 { self.l34.eq_arm[0] += 1; }
            if n >= 3 { self.l34.eq_arm[1] += 1; }
            r["eqgrp"] = j;
        }
        if self.l34.q4.is_some() {
            let wl = self.qt.as_ref().and_then(|q| q.book.as_ref()).map(|b| b.whale_last(whale, s0, t0, WH_L));
            let j = self.l34.q4.as_mut().map(|q| q.json(&h, whale, t0, wl)).unwrap_or_default();
            if r.get("quiet").is_some_and(|q| q.is_object()) { r["quiet"]["wh_l10"] = wl10_json(wl); }
            r["q4"] = j;
        }
    }

    /// dip34 seen: a cr_loss / quiet3_a / rearm_cr_loss skip of `whale` (nothing without --presend-live-seen-log)
    pub(super) fn seen_note(&mut self, why: &'static str, whale: Pk, t: u64, mint: Pk) {
        if let Some(sb) = self.l34.sb.as_mut() { if matches!(why, "cr_loss" | "quiet3_a" | "rearm_cr_loss") { sb.note(whale, t, why, mint); } }
    }

    /// dip34 (--presend-live-eqgrp-log): the fill record's "eqgrp" at our landing (the holders just before our buy; the window's whale out)
    pub(super) fn eqgrp_fill(&mut self, rec: &mut serde_json::Value, mint: &Pk, whale: &Pk) {
        if !self.cfg.eqgrp_log { return; }
        let h = holders_but(&self.det, mint, &self.user, whale, EQ_MIN).unwrap_or_default();
        let j = eqgrp_json(&h);
        let n = j["n"].as_u64().unwrap_or(0);
        if n >= 2 { self.l34.eq_fill[0] += 1; }
        if n >= 3 { self.l34.eq_fill[1] += 1; }
        rec["eqgrp"] = j;
    }

    /// dip34 q4: a closed position into the rolling maps (nothing without --presend-live-q4-log)
    pub(super) fn q4_note(&mut self, known: u64, whale: Option<Pk>, followed: bool, sellers: &[(Pk, u64)]) {
        if let Some(q) = self.l34.q4.as_mut() { q.note_pos(known, whale, followed, sellers); }
    }

    /// dip34: the run_end summary (None with every flag off)
    pub(super) fn l34_json(&self) -> Option<serde_json::Value> {
        if self.l34.sb.is_none() && self.l34.q4.is_none() && !self.cfg.eqgrp_log { return None; }
        let mut j = serde_json::json!({});
        if let Some(s) = &self.l34.sb { j["seen"] = serde_json::json!({"h": s.h_ns as f64 / 3.6e12, "notes": s.notes, "hits": s.hits, "whales": s.len()}); }
        if self.cfg.eqgrp_log { j["eqgrp"] = serde_json::json!({"arm_n2": self.l34.eq_arm[0], "arm_n3": self.l34.eq_arm[1], "fill_n2": self.l34.eq_fill[0], "fill_n3": self.l34.eq_fill[1]}); }
        if let Some(q) = &self.l34.q4 { j["q4"] = serde_json::json!({"positions": q.notes, "hs_hits": q.hs_hits, "unf1h_hits": q.unf_hits}); }
        Some(j)
    }
}

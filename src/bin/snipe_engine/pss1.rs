// =====================================================================================================================
// dip38 PSM12-S1 ARM FILTER (owner 11-05 "ok build the log": LOG ONLY now; the live switch is built, OFF, and not used).
// Frozen spec: /home/it/sniper-studies/sniper-psmodel12/FROZEN_PSM12.json (sha256 26e769ef...8157), REPORT.md §6-§8; its base PSM11-R2
// (/home/it/sniper-studies/sniper-psmodel11/FROZEN_R2.json). The honest gate: keep an arm iff
//     nd >= 2  AND  (re-arm OR T2 token age >= 50 slots)  AND  NOT (whale n >= 1 AND sum <= -0.02 SOL)  AND  NOT (whale n == 0 AND nd < 8)
// else "S1 would skip" with the FIRST failing reason in that order: nd, age, whale, cold.
//   nd    = the mint's M2-scored dumps strictly BEFORE the trigger = psmodel10's nd_trig (dump records with an m2 score, clock < the
//           trigger's; the re-arm's own dump never counted). The engine's counter is psh2's (chain order (slot, idx), the same dump
//           records): equal to the study's nd_trig on all 920 arms of r58 / r59 / r60 (offline check, 11-05)
//   age   = T2: the trigger's age_slots (trig.age_slots); a re-arm is exempt (its dump's age is logged)
//   whale = T2: the trigger whale (trig.wallet); re-arm: the DUMPER (dump.seller) (psmodel10 s3_table.py: tr.wallet / tr.seller)
//   n/sum = the whale ledger's (pswh, the COMBINED one: the study has no split) earlier positions with us and their summed realized P&L,
//           REAL positions only: the paper ones of --presend-live-wh-learn paper are subtracted (the study's ledger = realized positions)
// Flags (each needs --presend-live):
//   --presend-live-s1-log on|off (off)    LOG ONLY: an "s1" object on every presend_live_arm (T2 and re-arm; the verdict at the arm's
//                                         decision: T2 its trigger, re-arm its holders check) and on its window's presend_live_fill and
//                                         presend_live_realized ({keep, why}); run_end presend_live.s1 counts; the status line's part.
//                                         Needs --presend-live-wh-loss (S1 reads that ledger's history); turns psh2's nd counter on
//   --presend-live-s1 off|t2|rearm|t2,rearm (off)  LIVE (NOT used now): skip an arm S1 would skip ("s1_nd" / "s1_age" / "s1_whale" /
//                                         "s1_cold"; re-arm "rearm_s1_*"), decided LAST with the arm-time skips (only a trigger that would
//                                         arm). Needs the log on
//   --presend-live-s1-parts nd,age,whale,cold (all)  the parts the LIVE gate acts on (e.g. nd,age live while whale + cold stay log-only);
//                                         the log's verdict is always all four ("pwhy" = the live parts' first reason when they differ)
//   ledger control file "s1": "live" | "log"   overrides the start mode during the run (live = the flag's kinds, both when it is off;
//                                         log = off); needs --presend-live-s1-log on (else ignored, said in the mode record)
// Off (no --presend-live-s1-log): nothing of it runs; every record and decision dip38's. Log on, live off: decisions, windows, attempt
// bytes the same; only the "s1" fields, the nd counter's fields (psh2) and the counts are added.
// =====================================================================================================================
use super::*;

pub const S1_ND: u32 = 2;
pub const S1_AGE: u64 = 50;
pub const S1_WH_LOSS: i64 = 20_000_000;
pub const S1_COLD_ND: u32 = 8;
/// the parts (bits)
pub const P_ND: u8 = 1;
pub const P_AGE: u8 = 2;
pub const P_WHALE: u8 = 4;
pub const P_COLD: u8 = 8;
pub const P_ALL: u8 = 15;
/// the reasons in rule order (index 1..4 of the counters; 0 = keep)
pub const WHY: [&str; 4] = ["nd", "age", "whale", "cold"];

/// --presend-live-s1-parts LIST -> bits
pub fn parts_parse(s: &str) -> Result<u8> {
    let mut m = 0u8;
    for p in s.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
        m |= match p { "nd" => P_ND, "age" => P_AGE, "whale" => P_WHALE, "cold" => P_COLD, "all" => P_ALL,
            x => bail!("--presend-live-s1-parts: '{x}' (nd, age, whale, cold, comma-separated; or all)") };
    }
    if m == 0 { bail!("--presend-live-s1-parts needs at least one of nd, age, whale, cold"); }
    Ok(m)
}
pub fn parts_str(p: u8) -> String {
    let v: Vec<&str> = [P_ND, P_AGE, P_WHALE, P_COLD].iter().zip(WHY).filter(|(b, _)| p & **b != 0).map(|(_, w)| w).collect();
    v.join(",")
}

/// the FIRST failing reason among `parts` (None = keep). `n` / `sum`: the whale's real positions with us and their P&L (lamports)
pub fn s1_why(rearm: bool, nd: u32, age: u64, n: u32, sum: i64, parts: u8) -> Option<&'static str> {
    if parts & P_ND != 0 && nd < S1_ND { return Some("nd"); }
    if parts & P_AGE != 0 && !rearm && age < S1_AGE { return Some("age"); }
    if parts & P_WHALE != 0 && n >= 1 && sum <= -S1_WH_LOSS { return Some("whale"); }
    if parts & P_COLD != 0 && n == 0 && nd < S1_COLD_ND { return Some("cold"); }
    None
}

/// the skip name of a LIVE S1 skip
pub fn skip_name(rearm: bool, why: &str) -> &'static str {
    match (rearm, why) {
        (false, "nd") => "s1_nd", (false, "age") => "s1_age", (false, "whale") => "s1_whale", (false, _) => "s1_cold",
        (true, "nd") => "rearm_s1_nd", (true, "age") => "rearm_s1_age", (true, "whale") => "rearm_s1_whale", (true, _) => "rearm_s1_cold",
    }
}

/// one arm's S1 view: its inputs, the full verdict (all four parts) and the live parts' verdict
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct S1V { pub rearm: bool, pub nd: u32, pub age: u64, pub n: u32, pub sum: i64, pub pn: u32, pub why: Option<&'static str>, pub pwhy: Option<&'static str> }

impl S1V {
    /// from the whale ledger's history `h` (its paper positions taken out)
    pub fn new(rearm: bool, nd: u32, age: u64, h: &pswh::WhHist, parts: u8) -> S1V {
        let (n, sum) = (h.n.saturating_sub(h.pn), h.sum - h.ps);
        S1V { rearm, nd, age, n, sum, pn: h.pn, why: s1_why(rearm, nd, age, n, sum, P_ALL), pwhy: s1_why(rearm, nd, age, n, sum, parts) }
    }
    pub fn keep(&self) -> bool { self.why.is_none() }
    /// the arm / skip record's object: the inputs, the verdict, this kind's gate live now, spend / vsol / the trigger's price
    pub fn json(&self, parts: u8, live: bool, spend: u64, vsol: u64, p: f64) -> serde_json::Value {
        let mut j = serde_json::json!({"kind": if self.rearm { "rearm" } else { "T2" }, "nd": self.nd, "age": self.age, "wh_n": self.n, "wh_s": self.sum as f64 / 1e9,
            "cold": self.n == 0, "keep": self.keep(), "why": self.why, "live": live, "spend": spend, "vsol": vsol, "p": p});
        if parts != P_ALL { j["parts"] = parts_str(parts).into(); j["pwhy"] = self.pwhy.into(); }
        if self.pn > 0 { j["wh_paper_n"] = self.pn.into(); }
        j
    }
    /// the fill's / realized record's object
    pub fn short(&self) -> serde_json::Value {
        serde_json::json!({"keep": self.keep(), "why": self.why, "kind": if self.rearm { "rearm" } else { "T2" }, "nd": self.nd, "wh_n": self.n, "wh_s": self.sum as f64 / 1e9})
    }
    fn idx(&self) -> usize { self.why.map_or(0, |w| 1 + WHY.iter().position(|x| *x == w).unwrap_or(3)) }
}

/// windows kept for their fill / realize
const S1_WINS: usize = 8192;

/// the probe's S1 state: the live mode (bit 0 T2, bit 1 re-arm), the verdicts of armed windows, the counts [T2, re-arm][keep, nd, age,
/// whale, cold] of armed windows (log) and of live skips
#[derive(Debug, Default)]
pub struct S1St { pub mode: u64, pub w: FxHashMap<u64, S1V>, pub arms: [[u64; 5]; 2], pub skips: [[u64; 5]; 2], pub fills: [[u64; 5]; 2], pub ctl_changes: u64 }

impl S1St {
    pub fn new(cfg: &Cfg) -> S1St { S1St { mode: if cfg.s1_log { cfg.s1_live } else { 0 }, ..Default::default() } }
    fn row(c: &[u64; 5]) -> String { format!("keep {} | nd {} age {} whale {} cold {}", c[0], c[1], c[2], c[3], c[4]) }
    fn obj(c: &[u64; 5]) -> serde_json::Value { serde_json::json!({"keep": c[0], "nd": c[1], "age": c[2], "whale": c[3], "cold": c[4]}) }
}

impl PsLive {
    /// the S1 view of an arm about to be decided (None: the log off). `nd`: psh2's count before the trigger
    pub(super) fn s1_view(&self, rearm: bool, nd: Option<u32>, age: u64, whale: &Pk) -> Option<S1V> {
        if !self.cfg.s1_log { return None; }
        let h = self.sh.wh.lock().unwrap().get(false, rearm, whale);
        Some(S1V::new(rearm, nd.unwrap_or(0), age, &h, self.cfg.s1_parts))
    }
    /// this kind's gate is live now
    pub(super) fn s1_live(&self, rearm: bool) -> bool { self.s1.mode & if rearm { 2 } else { 1 } != 0 }
    /// the LIVE skip (its name) of a view: only with this kind's gate live and the live parts failing
    pub(super) fn s1_skip_why(&self, v: &S1V) -> Option<&'static str> {
        if !self.s1_live(v.rearm) { return None; }
        v.pwhy.map(|w| skip_name(v.rearm, w))
    }
    /// an armed window's view: kept for its fill / realize, counted
    pub(super) fn s1_arm(&mut self, id: u64, v: S1V) {
        self.s1.arms[v.rearm as usize][v.idx()] += 1;
        if self.s1.w.len() >= S1_WINS { let lo = id.saturating_sub(S1_WINS as u64 / 2); self.s1.w.retain(|k, _| *k >= lo); }
        self.s1.w.insert(id, v);
    }
    /// a LIVE skip: counted, a line
    pub(super) fn s1_skip_note(&mut self, mint: &Pk, whale: &Pk, v: &S1V) {
        self.s1.skips[v.rearm as usize][1 + WHY.iter().position(|x| Some(*x) == v.pwhy).unwrap_or(3)] += 1;
        self.line(format!("  PRESEND LIVE {}S1 SKIP ({}) {} | {} {} nd {} age {} | ledger {} positions {:+.4} SOL", if v.rearm { "REARM " } else { "" }, v.pwhy.unwrap_or("?"),
            b58(mint), if v.rearm { "dumper" } else { "whale" }, &b58(whale)[..8], v.nd, v.age, v.n, v.sum as f64 / 1e9));
    }
    /// a window's fill / realize: its arm's verdict (None: the log off or the window unknown)
    pub(super) fn s1_fill(&mut self, w: u64, count: bool) -> Option<serde_json::Value> {
        let v = *self.s1.w.get(&w)?;
        if count { self.s1.fills[v.rearm as usize][v.idx()] += 1; }
        Some(v.short())
    }
    /// the status line's part ("" with the log off)
    pub(super) fn s1_status(&self) -> String {
        if !self.cfg.s1_log { return String::new(); }
        let s = &self.s1;
        format!(" | S1 {} (parts {}): T2 arms {} / re-arm arms {} | fills T2 {} / re-arm {}{}", if s.mode == 0 { "LOG".to_string() } else { format!("LIVE {}", pslog36::mode_str(s.mode)) },
            parts_str(self.cfg.s1_parts), S1St::row(&s.arms[0]), S1St::row(&s.arms[1]), S1St::row(&s.fills[0]), S1St::row(&s.fills[1]),
            if s.skips.iter().flatten().any(|x| *x > 0) { format!(" | live skips T2 {} / re-arm {}", S1St::row(&s.skips[0]), S1St::row(&s.skips[1])) } else { String::new() })
    }
    /// run_end's part (None with the log off)
    pub(super) fn s1_finish(&self) -> Option<serde_json::Value> {
        if !self.cfg.s1_log { return None; }
        let s = &self.s1;
        Some(serde_json::json!({"mode": pslog36::mode_str(s.mode), "parts": parts_str(self.cfg.s1_parts), "arms": {"t2": S1St::obj(&s.arms[0]), "rearm": S1St::obj(&s.arms[1])},
            "fills": {"t2": S1St::obj(&s.fills[0]), "rearm": S1St::obj(&s.fills[1])}, "skips": {"t2": S1St::obj(&s.skips[0]), "rearm": S1St::obj(&s.skips[1])}, "ctl_changes": s.ctl_changes}))
    }
}

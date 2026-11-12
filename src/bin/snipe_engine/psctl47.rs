// =====================================================================================================================
// dip47 HOT CONTROL KEYS + FILTER STATE (owner 11-11).
//
// A) NEW HOT KEYS, read from the ledger control file (--presend-live-ledger-control; every ~10 s, on its mtime, like ctl43). An ABSENT key =
//    the start flag's value; a BAD value = the old value stays + a presend_live_ledger_mode {ok:false, key, err} record; never a crash.
//    Every change: presend_live_ledger_mode {"dip47": {key: new}, "was": {"dip47": {key: old}}} + "PRESEND LIVE LEDGER MODES dip47: ..." line.
//      floors          off | t2 | all   holder floors on snipe-guard tries (needs --presend-live-guard holders; else ignored + record).
//                                       off: every window's floor set is empty (deadline + band only); t2: re-arm windows none; all: both.
//      wh_kinds        t2 | rearm | all which arms the whale ledger's live rule may block (--presend-live-wh-kinds)
//      size_t2         SOL, (0, start]  T2 window size (--presend-live-size-sol); windows armed after the change
//      size_rearm      SOL, (0, start]  re-arm window size (--presend-live-rearm-size-sol); needs the re-arm on
//      mint_ledger_sol 0.01..1.0        the mint ledger's loss (--presend-live-mint-ledger; needs it at start)
//      wh_loss         "N:SOL"          N 1..50, SOL (0, 5] (--presend-live-wh-loss; needs it at start)
//      holder_loss     "PCT:SOL:WIN"    (--presend-live-holder-loss format; needs it at start)
//      botdepth        "N:SLOTS"        the list gate's MIN 1..BD_K and SLOTS 1..BD_SLOTS_MAX (--presend-live-botdepth; list gate at start)
//      curve_deep_pct  0.05..0.95       the CURVE band's D (--presend-live-guard-curve-deep; needs it at start)
//      min_age_slots   0..50            the young-age gate (--presend-live-min-age-slots)
//      exit_ms         50..10000        the ms timer exit; positions opened after the change (needs --presend-live-exit-ms > 0 at start)
//      tp, sl          0.02..0.9        take-profit / stop-loss; positions opened after the change
//      grp_t2          log | live       dip47 GRPSIGN as an ARM-TIME T2 skip (never re-arm / wide); needs --presend-live-grpsign-log on
//      grp_t2_pct      1..20 (3.0)      its threshold (% of supply)
//      grp_t2_whale    out | in (out)   the trigger whale counted in the group (r82: the whale is a member in 48 of 105 T2 fills; "in" skips ~55% of T2)
// B) FILTER STATE: one versioned object of every hot key (old and new), the decisive start-only settings; `fv` bumps on every change,
//    `fh` = its hash. presend_live_filter_state {fv, fh, state, changed: {key: [old, new]}, src} at start (fv 0) and on every change, with a
//    "PRESEND LIVE FILTER STATE fv=N: ..." line. Records stamped: see stamp() below.
// =====================================================================================================================
use super::*;
use std::collections::BTreeMap;

pub const KEYS: [&str; 26] = ["rival_gate", "rival_gate_spec", "fresh_skip_ra_def", "fresh_skip", "fresh_skip_spec", "rearm_fleet", "rearm_fleet_spec", "rearm_max_per_mint", "pause_window", "pause_now", "floors", "wh_kinds", "size_t2", "size_rearm", "mint_ledger_sol", "wh_loss", "holder_loss", "botdepth", "curve_deep_pct",
    "min_age_slots", "exit_ms", "tp", "sl", "grp_t2", "grp_t2_pct", "grp_t2_whale"];

/// the new keys' values (Copy; the start value of each = its flag)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct Vals {
    /// None: the guard is not in holders mode (the key is ignored); 0 off, 1 t2, 2 all
    pub floors: Option<u8>,
    pub wh_kinds: u8,
    pub size_t2: u64,
    pub size_rearm: Option<u64>,
    pub ml: Option<i64>,
    pub wh_loss: (u32, i64),
    pub hl: (f64, i64, i64),
    pub bd: Option<(u32, u64)>,
    pub curve: Option<f64>,
    pub min_age: u64,
    pub exit_ms: u64,
    pub tp: f64,
    pub sl: f64,
    pub grp_live: bool,
    pub grp_pct: f64,
    /// the trigger whale in the group (false = out, the default: the wallet whose dump the window waits for)
    pub grp_whale_in: bool,
    /// --presend-live-grpsign-log on (grp_t2 "live" needs it; not a key)
    pub grp_avail: bool,
    /// re-arm FILLS per mint before no new re-arm window arms on it (0 = no cap)
    pub rearm_cap: u32,
    /// the pause windows (PKT minutes of the day, start..end; end < start crosses midnight), how many
    pub pause: [(u16, u16); 4],
    pub pause_n: u8,
    /// the manual pause (control key only; off at start)
    pub pause_now: bool,
    /// the re-arm fleet rule's spec (None: the flag not given: the keys are ignored) and mode
    pub rf: Option<(u32, u64)>,
    pub rf_live: bool,
    /// dip48 fresh-holders skip: (T2 %, re-arm %; 0 = off for the lane), live; None = the flag not given (the keys are ignored)
    pub fresh: Option<(f64, f64)>,
    pub fresh_live: bool,
    /// dip49 the T2 rival gate (None: the flag not given: the keys ignored), live, its slots; the re-arm fresh definition (true = f1)
    pub rg: Option<(u32, u32, f64)>,
    pub rg_live: bool,
    pub rg_slots: u64,
    pub fresh_ra_f1: bool,
}

/// "T2:RA" (each 0 = off, or 5..90 % of supply)
pub fn fresh_parse(s: &str) -> std::result::Result<(f64, f64), String> {
    let bad = || format!("'{s}': T2PCT:RAPCT (each 0 = off, or 5..90 % of supply), e.g. 35:20");
    let (a, b) = s.split_once(':').ok_or_else(bad)?;
    let (a, b): (f64, f64) = (a.trim().parse().map_err(|_| bad())?, b.trim().parse().map_err(|_| bad())?);
    let ok = |x: f64| x == 0.0 || (5.0..=90.0).contains(&x);
    if !ok(a) || !ok(b) || (a == 0.0 && b == 0.0) { return Err(bad()); }
    Ok((a, b))
}
/// (fresh %, n, the lane's threshold, skip now)
pub type Fr = (f64, usize, f64, bool);
pub fn fresh_json(x: &Fr) -> serde_json::Value { serde_json::json!({"pct": x.0, "n": x.1, "thr": x.2, "would_skip": x.0 >= x.2}) }

/// "HH:MM-HH:MM[,HH:MM-HH:MM]" (PKT, at most 4; "" = none)
pub fn pause_parse(s: &str) -> std::result::Result<([(u16, u16); 4], u8), String> {
    let mut v = [(0u16, 0u16); 4];
    let mut n = 0usize;
    let hm = |x: &str| -> std::result::Result<u16, String> {
        let (h, m) = x.trim().split_once(':').ok_or_else(|| format!("'{x}' is not HH:MM"))?;
        let (h, m): (u16, u16) = (h.parse().map_err(|_| format!("'{x}' is not HH:MM"))?, m.parse().map_err(|_| format!("'{x}' is not HH:MM"))?);
        if h > 23 || m > 59 { return Err(format!("'{x}' out of range (00:00..23:59)")); }
        Ok(h * 60 + m)
    };
    for w in s.split(',').map(str::trim).filter(|w| !w.is_empty()) {
        if n == 4 { return Err("at most 4 windows".into()); }
        let (a, b) = w.split_once('-').ok_or_else(|| format!("'{w}' is not HH:MM-HH:MM"))?;
        let (a, b) = (hm(a)?, hm(b)?);
        if a == b { return Err(format!("'{w}': start = end")); }
        v[n] = (a, b); n += 1;
    }
    Ok((v, n as u8))
}
pub fn pause_str(v: &[(u16, u16)]) -> String { v.iter().map(|(a, b)| format!("{:02}:{:02}-{:02}:{:02}", a / 60, a % 60, b / 60, b % 60)).collect::<Vec<_>>().join(",") }
/// the window containing PKT minute `m` (crossing midnight when end < start)
pub fn pause_hit(v: &[(u16, u16)], m: u16) -> Option<(u16, u16)> { v.iter().copied().find(|&(a, b)| if a < b { m >= a && m < b } else { m >= a || m < b }) }
/// PKT (UTC+5) minute of the day of a UTC unix time in ns
pub fn pkt_min(ns: u64) -> u16 { (((ns / 1_000_000_000 + 5 * 3600) / 60) % 1440) as u16 }

pub fn floors_s(f: Option<u8>) -> &'static str { match f { None => "n/a", Some(0) => "off", Some(1) => "t2", _ => "all" } }
pub fn kinds_s(k: u8) -> &'static str { match k { 1 => "t2", 2 => "rearm", _ => "all" } }
fn sol(l: i64) -> f64 { l as f64 / 1e9 }

impl Vals {
    pub fn from_cfg(c: &Cfg) -> Vals {
        Vals {
            floors: c.g43.as_ref().filter(|g| g.mode == ps43_guard::Mode::Holders).map(|g| if g.floor_rearm { 2 } else { 1 }),
            wh_kinds: c.wh_kinds,
            size_t2: c.spend,
            size_rearm: c.rearm.on.then_some(c.rearm.spend),
            ml: c.c43.ml,
            wh_loss: (c.wh_loss_n, c.wh_loss),
            hl: (c.hl_pct, c.hl_loss, c.hl_win),
            bd: match c.bd { Some(psbd::Gate::List { min, slots }) => Some((min, slots)), _ => None },
            curve: c.g43.as_ref().and_then(|g| g.curve_deep),
            min_age: c.min_age_slots,
            exit_ms: c.exit_ms,
            tp: c.tp,
            sl: c.sl,
            grp_live: false,
            grp_pct: psgrp47::T2_PCT,
            grp_whale_in: false,
            grp_avail: c.grpsign,
            rearm_cap: c.rearm_cap47,
            pause: c.pause47.0,
            pause_n: c.pause47.1,
            pause_now: false,
            rf: c.rearm_fleet,
            rf_live: c.rearm_fleet_live,
            fresh: c.fresh_skip,
            fresh_live: c.fresh_live,
            rg: c.rival_gate,
            rg_live: c.rival_live,
            rg_slots: c.rival_slots,
            fresh_ra_f1: c.fresh_ra_f1,
        }
    }
    /// each key's value as the records show it
    pub fn get(&self, k: &str) -> serde_json::Value {
        use serde_json::json;
        match k {
            "floors" => floors_s(self.floors).into(),
            "wh_kinds" => kinds_s(self.wh_kinds).into(),
            "size_t2" => json!(self.size_t2 as f64 / 1e9),
            "size_rearm" => self.size_rearm.map_or(serde_json::Value::Null, |s| json!(s as f64 / 1e9)),
            "mint_ledger_sol" => self.ml.map_or(serde_json::Value::Null, |l| json!(sol(l))),
            "wh_loss" => if self.wh_loss.0 == 0 { serde_json::Value::Null } else { format!("{}:{}", self.wh_loss.0, sol(self.wh_loss.1)).into() },
            "holder_loss" => if self.hl.0 == 0.0 { serde_json::Value::Null } else { format!("{}:{}:{}", self.hl.0, sol(self.hl.1), sol(self.hl.2)).into() },
            "botdepth" => self.bd.map_or(serde_json::Value::Null, |(m, s)| format!("{m}:{s}").into()),
            "curve_deep_pct" => self.curve.map_or(serde_json::Value::Null, |d| json!(d)),
            "min_age_slots" => json!(self.min_age),
            "exit_ms" => json!(self.exit_ms),
            "tp" => json!(self.tp),
            "sl" => json!(self.sl),
            "grp_t2" => (if self.grp_live { "live" } else { "log" }).into(),
            "grp_t2_pct" => json!(self.grp_pct),
            "grp_t2_whale" => (if self.grp_whale_in { "in" } else { "out" }).into(),
            "rearm_max_per_mint" => json!(self.rearm_cap),
            "pause_window" => pause_str(&self.pause[..self.pause_n as usize]).into(),
            "pause_now" => (if self.pause_now { "on" } else { "off" }).into(),
            "rearm_fleet" => if self.rf.is_none() { "off".into() } else { (if self.rf_live { "live" } else { "log" }).into() },
            "rearm_fleet_spec" => self.rf.map_or(serde_json::Value::Null, |(n, k)| format!("{n}:{k}").into()),
            "rival_gate" => if self.rg.is_none() { "off".into() } else { (if self.rg_live { "live" } else { "log" }).into() },
            "rival_gate_spec" => self.rg.map_or(serde_json::Value::Null, |(a, b, c)| format!("{a}:{b}:{c}").into()),
            "fresh_skip_ra_def" => if self.fresh.is_none() { serde_json::Value::Null } else { (if self.fresh_ra_f1 { "f1" } else { "f3" }).into() },
            "fresh_skip" => if self.fresh.is_none() { "off".into() } else { (if self.fresh_live { "live" } else { "log" }).into() },
            "fresh_skip_spec" => self.fresh.map_or(serde_json::Value::Null, |(a, b)| format!("{a}:{b}").into()),
            _ => serde_json::Value::Null,
        }
    }
}

/// the control file's new keys: per key Ok(Some(value text)) / Ok(None) absent / Err(why)
pub type Raw = BTreeMap<&'static str, std::result::Result<serde_json::Value, String>>;

/// the file's new keys (an unreadable / non-object file: Err, everything stays)
pub fn ctl47_parse(b: &[u8]) -> std::result::Result<Raw, String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    let o = v.as_object().ok_or("not an object")?;
    let mut r = Raw::new();
    for k in KEYS.iter() {
        if let Some(x) = o.get(*k).filter(|x| !x.is_null()) { r.insert(k, Ok(x.clone())); }
    }
    Ok(r)
}

fn num(x: &serde_json::Value, lo: f64, hi: f64, what: &str) -> std::result::Result<f64, String> {
    let f = x.as_f64().or_else(|| x.as_str().and_then(|s| s.trim().parse().ok())).ok_or_else(|| format!("'{x}' is not a number ({what})"))?;
    if !(f.is_finite() && f >= lo && f <= hi) { return Err(format!("{f} out of bounds [{lo}, {hi}] ({what})")); }
    Ok(f)
}
fn text(x: &serde_json::Value) -> std::result::Result<&str, String> { x.as_str().ok_or_else(|| format!("'{x}' is not a string")) }

/// one key's new value from its raw value (`start`: the start values; `cur`: the values now). Err: refused (the old value stays)
pub fn key_apply(k: &str, x: &serde_json::Value, start: &Vals, v: &mut Vals) -> std::result::Result<(), String> {
    match k {
        "floors" => {
            if start.floors.is_none() { return Err("ignored: needs --presend-live-guard holders at start".into()); }
            v.floors = Some(match text(x)? { "off" => 0, "t2" => 1, "all" => 2, s => return Err(format!("'{s}' (off | t2 | all)")) });
        }
        "wh_kinds" => v.wh_kinds = match text(x)? { "t2" => 1, "rearm" => 2, "all" => 3, s => return Err(format!("'{s}' (t2 | rearm | all)")) },
        "size_t2" => {
            let cap = start.size_t2 as f64 / 1e9;
            let s = num(x, f64::MIN_POSITIVE, cap, "SOL in (0, the start size]")?;
            v.size_t2 = ((s * 1e9).round() as u64).min(start.size_t2).max(1);
        }
        "size_rearm" => {
            let Some(st) = start.size_rearm else { return Err("ignored: needs --presend-live-rearm on".into()) };
            let s = num(x, f64::MIN_POSITIVE, st as f64 / 1e9, "SOL in (0, the start re-arm size]")?;
            v.size_rearm = Some(((s * 1e9).round() as u64).min(st).max(1));
        }
        "mint_ledger_sol" => {
            if start.ml.is_none() { return Err("ignored: needs --presend-live-mint-ledger at start".into()); }
            v.ml = Some((num(x, 0.01, 1.0, "SOL 0.01..1.0")? * 1e9).round() as i64);
        }
        "wh_loss" => {
            if start.wh_loss.0 == 0 { return Err("ignored: needs --presend-live-wh-loss at start".into()); }
            v.wh_loss = pswh::wh_loss_parse(text(x)?).map_err(|e| e.to_string())?;
        }
        "holder_loss" => {
            if start.hl.0 == 0.0 { return Err("ignored: needs --presend-live-holder-loss at start".into()); }
            v.hl = pshl::hl_parse(text(x)?).map_err(|e| e.to_string())?;
        }
        "botdepth" => {
            if start.bd.is_none() { return Err("ignored: needs --presend-live-botdepth MIN:SLOTS (the list gate) at start".into()); }
            v.bd = Some(psbd::spec_parse(text(x)?).map_err(|e| e.to_string())?);
        }
        "curve_deep_pct" => {
            if start.curve.is_none() { return Err("ignored: needs --presend-live-guard-curve-deep at start".into()); }
            v.curve = Some(num(x, 0.05, 0.95, "D 0.05..0.95")?);
        }
        "min_age_slots" => v.min_age = num(x, 0.0, 50.0, "slots 0..50")?.round() as u64,
        "exit_ms" => {
            if start.exit_ms == 0 { return Err("ignored: needs --presend-live-exit-ms > 0 at start".into()); }
            v.exit_ms = num(x, 50.0, 10_000.0, "ms 50..10000")?.round() as u64;
        }
        "tp" => v.tp = num(x, 0.02, 0.9, "0.02..0.9")?,
        "sl" => v.sl = num(x, 0.02, 0.9, "0.02..0.9")?,
        "grp_t2" => {
            let live = match text(x)? { "log" => false, "live" => true, s => return Err(format!("'{s}' (log | live)")) };
            if live && !start.grp_avail { return Err("ignored: needs --presend-live-grpsign-log on".into()); }
            v.grp_live = live;
        }
        "grp_t2_pct" => v.grp_pct = num(x, 1.0, 20.0, "% of supply 1..20")?,
        "rearm_max_per_mint" => {
            let f = num(x, 0.0, 10.0, "re-arm fills per mint 0..10 (0 = no cap)")?;
            if f.fract() != 0.0 { return Err(format!("{f}: a whole number 0..10")); }
            v.rearm_cap = f as u32;
        }
        "pause_window" => { (v.pause, v.pause_n) = pause_parse(text(x)?)?; }
        "rival_gate" => {
            if start.rg.is_none() { return Err("ignored: needs --presend-live-rival-gate R0:R2:AGE_H at start".into()); }
            v.rg_live = match text(x)? { "log" => false, "live" => true, s => return Err(format!("'{s}' (log | live)")) };
        }
        "rival_gate_spec" => {
            if start.rg.is_none() { return Err("ignored: needs --presend-live-rival-gate R0:R2:AGE_H at start".into()); }
            v.rg = Some(psrival49::spec_parse(text(x)?)?);
        }
        "fresh_skip_ra_def" => {
            if start.fresh.is_none() { return Err("ignored: needs --presend-live-fresh-skip T2PCT:RAPCT at start".into()); }
            v.fresh_ra_f1 = match text(x)? { "f1" => true, "f3" => false, s => return Err(format!("'{s}' (f1 | f3)")) };
        }
        "fresh_skip" => {
            if start.fresh.is_none() { return Err("ignored: needs --presend-live-fresh-skip T2PCT:RAPCT at start".into()); }
            v.fresh_live = match text(x)? { "log" => false, "live" => true, s => return Err(format!("'{s}' (log | live)")) };
        }
        "fresh_skip_spec" => {
            if start.fresh.is_none() { return Err("ignored: needs --presend-live-fresh-skip T2PCT:RAPCT at start".into()); }
            v.fresh = Some(fresh_parse(text(x)?)?);
        }
        "rearm_fleet" => {
            if start.rf.is_none() { return Err("ignored: needs --presend-live-rearm-fleet N:SLOTS at start".into()); }
            v.rf_live = match text(x)? { "log" => false, "live" => true, s => return Err(format!("'{s}' (log | live)")) };
        }
        "rearm_fleet_spec" => {
            if start.rf.is_none() { return Err("ignored: needs --presend-live-rearm-fleet N:SLOTS at start".into()); }
            v.rf = Some(psrfleet47::spec_parse(text(x)?)?);
        }
        "pause_now" => v.pause_now = match text(x)? { "on" => true, "off" => false, s => return Err(format!("'{s}' (on | off)")) },
        "grp_t2_whale" => v.grp_whale_in = match text(x)? { "out" => false, "in" => true, s => return Err(format!("'{s}' (out | in)")) },
        _ => return Err("unknown key".into()),
    }
    Ok(())
}

/// the new keys' values from a parsed file: absent = start, bad = the old value stays (its error returned)
pub fn resolve(raw: &Raw, start: &Vals, cur: &Vals) -> (Vals, Vec<(&'static str, String)>) {
    let mut v = *start;
    let mut errs = Vec::new();
    for k in KEYS.iter() {
        let Some(x) = raw.get(k) else { continue };
        let x = x.as_ref().expect("parse gives Ok");
        let mut t = v;
        match key_apply(k, x, start, &mut t) {
            Ok(()) => v = t,
            Err(e) => {
                // the old value stays
                let mut keep = v;
                copy_key(k, cur, &mut keep);
                v = keep;
                errs.push((*k, e));
            }
        }
    }
    (v, errs)
}
fn copy_key(k: &str, from: &Vals, to: &mut Vals) {
    match k {
        "floors" => to.floors = from.floors, "wh_kinds" => to.wh_kinds = from.wh_kinds, "size_t2" => to.size_t2 = from.size_t2,
        "size_rearm" => to.size_rearm = from.size_rearm, "mint_ledger_sol" => to.ml = from.ml, "wh_loss" => to.wh_loss = from.wh_loss,
        "holder_loss" => to.hl = from.hl, "botdepth" => to.bd = from.bd, "curve_deep_pct" => to.curve = from.curve, "min_age_slots" => to.min_age = from.min_age,
        "exit_ms" => to.exit_ms = from.exit_ms, "tp" => to.tp = from.tp, "sl" => to.sl = from.sl, "grp_t2" => to.grp_live = from.grp_live,
        "grp_t2_pct" => to.grp_pct = from.grp_pct, "grp_t2_whale" => to.grp_whale_in = from.grp_whale_in,
        "rearm_max_per_mint" => to.rearm_cap = from.rearm_cap, "pause_window" => { to.pause = from.pause; to.pause_n = from.pause_n; } "pause_now" => to.pause_now = from.pause_now,
        "rearm_fleet" => to.rf_live = from.rf_live, "fresh_skip" => to.fresh_live = from.fresh_live,
        "rival_gate" => to.rg_live = from.rg_live, "rival_gate_spec" => to.rg = from.rg, "fresh_skip_ra_def" => to.fresh_ra_f1 = from.fresh_ra_f1, "fresh_skip_spec" => to.fresh = from.fresh, "rearm_fleet_spec" => to.rf = from.rf, _ => {}
    }
}

/// the sender's view of the new keys (it applies them to its own Cfg copy when `ver` moves: one relaxed load per loop otherwise)
#[derive(Default)]
pub struct Sh47 { pub ver: AtomicU64, pub ov: Mutex<Option<(Option<psbd::Gate>, Option<f64>, bool)>> }

/// the sender's check, at the top of its loop: the botdepth gate, the CURVE band's D, floors on re-arm windows
pub fn sender_sync(sh: &Sh47, seen: &mut u64, cfg: &mut Cfg) {
    let v = sh.ver.load(Ordering::Acquire);
    if v == *seen { return; }
    *seen = v;
    if let Some((bd, curve, fr)) = *sh.ov.lock().unwrap() {
        cfg.bd = bd;
        if let Some(g) = cfg.g43.as_mut() { g.curve_deep = curve; g.floor_rearm = fr; }
    }
}

/// the published filter state (fv, fh, the compact object)
#[derive(Clone, Debug)]
pub struct Fs { pub fv: u64, pub fh: String, pub obj: Arc<serde_json::Value> }

/// the writer thread's stamp for records built off the main loop (the sender's probe / withheld records): the state now
pub static FV_NOW: AtomicU64 = AtomicU64::new(0);
pub static FH_NOW: Mutex<String> = Mutex::new(String::new());

/// records that carry fv / fh (+ "filters" for fill / realized: the window's ARM state)
pub fn stamped(ev: &str) -> bool {
    matches!(ev, "presend_live_arm" | "presend_live_skip" | "presend_live_fill" | "presend_live_realized" | "presend_live_exit" | "presend_live_filter_ab"
        | "presend_live_dump_exit" | "presend_live_close") || ev.starts_with("presend_live_probe")
}
/// the writer's stamp of a record built off the main loop (no fv yet)
pub fn writer_stamp(v: &mut serde_json::Value) {
    let Some(ev) = v["ev"].as_str() else { return };
    // the sender's tries: fv only (they are many)
    if ev == "presend_attempt" { if v.get("fv").is_none() { v["fv"] = FV_NOW.load(Ordering::Relaxed).into(); } return; }
    if !(ev.starts_with("presend_live_probe") || ev == "presend_live_filter_ab" || ev == "presend_live_rearm_fleet") || v.get("fv").is_some() { return; }
    v["fv"] = FV_NOW.load(Ordering::Relaxed).into();
    v["fh"] = FH_NOW.lock().unwrap().clone().into();
}

/// dip47's main-loop state (PsLive::f47)
#[derive(Default)]
pub struct F47 {
    pub start: Option<Vals>,
    pub cur: Option<Vals>,
    pub ctl: Option<(String, Option<std::time::SystemTime>, Instant)>,
    pub ctl_changes: u64, pub ctl_errors: u64,
    /// the filter state: the last published, its map (the diff base), the other readers' change counters seen, the last auto check
    pub fs: Option<Fs>,
    pub map: BTreeMap<String, serde_json::Value>,
    pub seen: u64,
    pub auto_at: Option<Instant>,
    /// per window: its ARM state; per position (pid): its exit values (exit_ms, tp, sl) when they differ from the start's
    pub wfs: FxHashMap<u64, Fs>,
    pub wq: VecDeque<u64>,
    pub px: BTreeMap<u64, (u64, f64, f64)>,
    pub grp_skips: u64,
    /// dip48 fresh-holders skip: per armed window its verdict at the arm (the fill record's "fresh_skip"; only with the flag)
    pub fresh_w: FxHashMap<u64, serde_json::Value>,
    /// re-arm FILLS per mint this run (the re-arm cap's count)
    pub rfills: FxHashMap<Pk, u32>,
    /// the pause under way (its text: "23:00-02:00" / "manual"), arms skipped in pauses, the test clock (UTC ns)
    pub pause_on: Option<String>,
    pub pause_skips: u64,
    pub pause_cur: u64,
    pub clock_ns: Option<u64>,
    /// the time the stamping took (ns, main loop) and how many records
    pub stamp_ns: std::cell::Cell<u64>, pub stamp_n: std::cell::Cell<u64>,
}

pub fn fh_of(obj: &serde_json::Value) -> String {
    use sha2::Digest;
    let h = sha2::Sha256::digest(obj.to_string().as_bytes());
    h[..4].iter().map(|b| format!("{b:02x}")).collect()
}

impl PsLive {
    /// the re-arm cap hit on `mint`: (its re-arm fills, the cap); None: no cap / below it
    pub(super) fn rearm_cap47(&self, mint: &Pk) -> Option<(u32, u32)> {
        let cap = self.f47.cur.map_or(self.cfg.rearm_cap47, |v| v.rearm_cap);
        if cap == 0 { return None; }
        let n = self.f47.rfills.get(mint).copied().unwrap_or(0);
        (n >= cap).then_some((n, cap))
    }
    /// the pause now (the window's text / "manual"); None: not paused
    fn pause_now47(&self) -> Option<String> {
        let v = self.f47.cur?;
        if v.pause_now { return Some("manual".into()); }
        if v.pause_n == 0 { return None; }
        let m = pkt_min(self.f47.clock_ns.unwrap_or_else(arbx::feeds::clock::real_ns));
        pause_hit(&v.pause[..v.pause_n as usize], m).map(|w| pause_str(&[w]))
    }
    /// the pause's entry / exit: one mode record + one line each (from tick and before every arm)
    pub(super) fn pause47_tick(&mut self) {
        let now = self.pause_now47();
        if now == self.f47.pause_on { return; }
        let t = arbx::feeds::clock::now_ns();
        let was = self.f47.pause_on.clone();
        match (&was, &now) {
            (_, Some(w)) => {
                self.f47.pause_cur = 0;
                self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": true, "pause_window": "on", "window": w, "tz": "PKT", "t": t}));
                self.line(format!("  PRESEND LIVE PAUSE WINDOW ON {w} PKT: no new arms (open positions exit as usual)"));
            }
            (Some(w), None) => {
                self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": true, "pause_window": "off", "window": w, "tz": "PKT", "skipped": self.f47.pause_cur, "t": t}));
                self.line(format!("  PRESEND LIVE PAUSE WINDOW OFF {w} PKT: {} arms skipped", self.f47.pause_cur));
            }
            (None, None) => {}
        }
        self.f47.pause_on = now;
    }
    /// an arm (T2 / wide / re-arm) asked during a pause: counted ("pause_window", no record per trigger) -> true = do not arm
    pub(super) fn paused47(&mut self) -> bool {
        if self.f47.cur.is_none_or(|v| v.pause_n == 0 && !v.pause_now) { return false; }
        self.pause47_tick();
        if self.f47.pause_on.is_none() { return false; }
        self.f47.pause_skips += 1;
        self.f47.pause_cur += 1;
        *self.st.skips.entry("pause_window").or_default() += 1;
        true
    }

    /// dip48 the fresh-holders verdict of a lane (`rearm`) at its arm: None = the flag off / the lane off; .3 = skip now (live and >= thr)
    pub(super) fn fresh48(&mut self, rearm: bool, pct: f64, n: usize) -> Option<Fr> {
        let v = self.f47.cur?;
        let (a, b) = v.fresh?;
        let thr = if rearm { b } else { a };
        if thr <= 0.0 { return None; }
        if self.f47.fresh_w.len() > 8192 { self.f47.fresh_w.clear(); }
        Some((pct, n, thr, v.fresh_live && pct >= thr))
    }

    fn v47(&self) -> Vals { self.f47.cur.unwrap_or_else(|| Vals::from_cfg(&self.cfg)) }
    /// the T2 window size now (the start's without a size_t2 key)
    pub(super) fn size_t2_47(&self) -> u64 { self.f47.cur.map_or(self.cfg.spend, |v| v.size_t2) }
    /// floors on this window's tries? (false: an empty floor set; the start flag's when no key)
    pub(super) fn floors_off_47(&self) -> bool { self.f47.cur.and_then(|v| v.floors) == Some(0) }
    /// grp_t2 live and its threshold
    pub(super) fn grp_t2_47(&self) -> Option<(f64, bool)> { self.f47.cur.filter(|v| v.grp_live).map(|v| (v.grp_pct, v.grp_whale_in)) }
    /// a position's exit values (exit_ms, tp, sl): the ones at its opening
    pub(super) fn exit47(&self, pid: u64) -> (u64, f64, f64) { self.f47.px.get(&pid).copied().unwrap_or((self.cfg.exit_ms, self.cfg.tp, self.cfg.sl)) }

    /// start: the start values, the control file's first read, the filter state fv 0, the banner
    pub(super) fn f47_start(&mut self) {
        let s = Vals::from_cfg(&self.cfg);
        self.f47.start = Some(s);
        self.f47.cur = Some(s);
        self.sh.rf.set(s.rf, s.rf_live);
        self.sh.rg.set(s.rg, s.rg_slots, s.rg_live);
        if let Some(p) = self.cfg.ledger_ctl.clone() {
            self.line(format!("DIP47 CONTROL KEYS ({p}): {} (absent = the start flag; bad = the old value stays)", KEYS.iter().copied().collect::<Vec<_>>().join(", ")));
            self.f47.ctl = Some((p, None, Instant::now()));
            self.ctl47_check(true);
        }
        self.fs_refresh("start");
    }

    /// the control file's new keys (every ~10 s from tick; `force`: now)
    pub(super) fn ctl47_check(&mut self, force: bool) {
        let Some((path, mt0, at)) = self.f47.ctl.clone() else { return };
        if !force && at.elapsed() < Duration::from_secs(10) { return; }
        let mt = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
        if let Some(c) = self.f47.ctl.as_mut() { c.2 = Instant::now(); }
        if !force && mt == mt0 { return; }
        if let Some(c) = self.f47.ctl.as_mut() { c.1 = mt; }
        match std::fs::read(&path).map_err(|e| e.to_string()).and_then(|b| ctl47_parse(&b)) {
            Ok(raw) => self.ctl47_apply(&raw, &path),
            Err(e) => {
                self.f47.ctl_errors += 1;
                self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": false, "err": e, "path": path, "dip47": true, "t": arbx::feeds::clock::now_ns()}));
                self.line(format!("  PRESEND LIVE LEDGER MODES dip47: control file {path} NOT read ({e}): the values stay"));
            }
        }
    }

    /// apply a parsed file (tests call it directly)
    pub(super) fn ctl47_apply(&mut self, raw: &Raw, path: &str) {
        let (Some(start), Some(cur)) = (self.f47.start, self.f47.cur) else { return };
        let (new, errs) = resolve(raw, &start, &cur);
        for (k, e) in &errs {
            self.f47.ctl_errors += 1;
            self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": false, "key": k, "err": e, "value": raw.get(k).and_then(|x| x.as_ref().ok()).cloned(), "kept": cur.get(k), "path": path, "dip47": true, "t": arbx::feeds::clock::now_ns()}));
            self.line(format!("  PRESEND LIVE LEDGER MODES dip47: \"{k}\" REFUSED ({e}): stays {}", cur.get(k)));
        }
        let ch: Vec<(&str, serde_json::Value, serde_json::Value)> = KEYS.iter().filter_map(|k| { let (o, n) = (cur.get(k), new.get(k)); (o != n).then_some((*k, o, n)) }).collect();
        if ch.is_empty() { return; }
        self.f47_set(new);
        self.f47.ctl_changes += 1;
        let mut now = serde_json::Map::new();
        let mut was = serde_json::Map::new();
        for (k, o, n) in &ch { now.insert(k.to_string(), n.clone()); was.insert(k.to_string(), o.clone()); }
        self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": true, "dip47": now, "was": {"dip47": was}, "path": path, "t": arbx::feeds::clock::now_ns()}));
        self.line(format!("  PRESEND LIVE LEDGER MODES dip47: {} ({path})", ch.iter().map(|(k, o, n)| format!("{k} {o} -> {n}")).collect::<Vec<_>>().join(", ")));
        self.fs_refresh("control");
    }

    /// the values into the engine: the main loop's Cfg, the re-arm's size, the sender's copy
    pub(super) fn f47_set(&mut self, v: Vals) {
        let old = self.f47.cur;
        self.f47.cur = Some(v);
        self.cfg.wh_kinds = v.wh_kinds;
        self.cfg.c43.ml = v.ml;
        (self.cfg.wh_loss_n, self.cfg.wh_loss) = v.wh_loss;
        (self.cfg.hl_pct, self.cfg.hl_loss, self.cfg.hl_win) = v.hl;
        self.cfg.min_age_slots = v.min_age;
        if let (Some(rm), Some(s)) = (self.rm.as_mut(), v.size_rearm) { rm.cfg.spend = s; }
        if let Some((min, slots)) = v.bd { self.cfg.bd = Some(psbd::Gate::List { min, slots }); }
        if let Some(g) = self.cfg.g43.as_mut() {
            g.curve_deep = v.curve;
            if let Some(f) = v.floors { g.floor_rearm = f == 2; }
        }
        // the re-arm fleet rule: the sender reads these atomics
        self.sh.rf.set(v.rf, v.rf_live);
        self.sh.rg.set(v.rg, v.rg_slots, v.rg_live);
        let fr = self.cfg.g43.as_ref().is_some_and(|g| g.floor_rearm);
        let sender = (self.cfg.bd, self.cfg.g43.as_ref().and_then(|g| g.curve_deep), fr);
        let was = old.map(|o| (o.bd, o.curve, o.floors));
        if was != Some((v.bd, v.curve, v.floors)) {
            *self.sh.f47.ov.lock().unwrap() = Some(sender);
            self.sh.f47.ver.fetch_add(1, Ordering::Release);
            // floors off / back on: the armed windows take their sets again
            if old.and_then(|o| o.floors) != v.floors {
                let ms: Vec<Pk> = self.armed.keys().copied().collect();
                for m in ms { self.g43_refresh(&m); }
            }
        }
    }

    /// a position opened (pid): its exit values, when they differ from the start's
    pub(super) fn f47_pos_open(&mut self, pid: u64) {
        let v = self.v47();
        let x = (v.exit_ms, v.tp, v.sl);
        if x != (self.cfg.exit_ms, self.cfg.tp, self.cfg.sl) { self.f47.px.insert(pid, x); }
        while self.f47.px.len() > 4096 { let k = *self.f47.px.keys().next().unwrap(); self.f47.px.remove(&k); }
    }

    // ---- filter state ---------------------------------------------------------------------------------------------------

    /// every hot key's mode / value now, and the start-only settings that decide
    pub(super) fn fs_map(&self) -> BTreeMap<String, serde_json::Value> {
        use serde_json::Value as V;
        let s = |x: bool| V::from(if x { "live" } else { "log" });
        let mut m: BTreeMap<String, V> = BTreeMap::new();
        let mut put = |k: &str, v: V| { m.insert(k.to_string(), v); };
        let off = || V::from("off");
        // dip37 ledgers
        put("whale", if self.cfg.wh_on() { s(self.hls.live[0]) } else { off() });
        put("holder", if self.cfg.hl_on() { s(self.hls.live[1]) } else { off() });
        put("mint_ledger", if self.cfg.c43.ml.is_some() { s(self.cfg.c43.ml_live) } else { off() });
        put("blocklist_send", if self.cfg.blocklist_send { s(self.sh.bl_send_live.load(Ordering::Relaxed)) } else { off() });
        put("botdepth", if self.cfg.bd.is_some() { s(self.sh.bd.live.load(Ordering::Relaxed)) } else { off() });
        // dip43 A9 arm-time gates
        for (i, k) in ps43::G43::KEYS.iter().enumerate() {
            let g = self.d43.g;
            let v = [g.quiet, g.quiet3a, g.create_slot, g.young_age, g.lone_whale, g.cr_loss, g.blocklist_arm, g.rearm, g.rearm_r5, g.breaker][i];
            put(k, s(v));
        }
        // FP-NOBOT / skip2 / s1
        match self.fp.as_ref() {
            Some(f) => {
                let md = f.gs.mode.load(Ordering::Relaxed);
                put("fpnb_t2", s(md & 1 != 0)); put("fpnb_rearm", s(md & 2 != 0));
                put("fpnb_strict", if self.cfg.c43.fp_strict.is_some() { s(f.gs.strict_live.load(Ordering::Relaxed)) } else { off() });
                put("skip2", if self.cfg.skip2_log { pslog36::mode_str(f.gs.s2_mode.load(Ordering::Relaxed)).into() } else { off() });
            }
            None => { for k in ["fpnb_t2", "fpnb_rearm", "fpnb_strict", "skip2"] { put(k, off()); } }
        }
        put("s1", if self.cfg.s1_log { pslog36::mode_str(self.s1.mode).into() } else { off() });
        match self.wd.as_ref() {
            Some(w) => {
                put("widedumper", s(w.wide.live));
                put("qf2", w.qf.as_ref().map_or(off(), |q| s(q.live)));
                if w.qf.is_some() { put("qf2_size", serde_json::json!(w.qf_size.unwrap_or(w.size) as f64 / 1e9)); put("qf2_min_age", w.filt.age_min.into()); }
            }
            None => { put("widedumper", off()); put("qf2", off()); }
        }
        put("stall", s(self.d43.stall_live));
        put("deadman", s(self.d43.deadman_live));
        put("fanout", if self.cfg.c43.fanout.is_some() { s(self.cfg.c43.fanout_live) } else { off() });
        put("curve_deep", if self.cfg.g43.as_ref().and_then(|g| g.curve_deep).is_some() { s(!self.sh.g43.curve_log.load(Ordering::Relaxed)) } else { off() });
        put("dump_exit", if self.cfg.dump_exit.is_some() { s(self.d43.dx_live) } else { off() });
        put("exit_lots", if self.cfg.b43.lots.is_some() { self.b43_mode().s().into() } else { off() });
        put("probe46", (if self.sh.p46.probe.load(Ordering::Relaxed) { "on" } else { "off" }).into());
        put("ab46", psprobe46::ab_names(self.sh.p46.ab.load(Ordering::Relaxed)).into());
        // dip47 new keys
        let v = self.v47();
        for k in KEYS.iter() { put(k, v.get(k)); }
        put("grpsign_log", self.cfg.grpsign.into());
        put("fleet_log", self.cfg.fleet.is_some().into());
        put("funder_log", self.cfg.funder_log.into());
        // dip48: only when on (off: dip47's state, its hash unchanged)
        if self.cfg.flow_log { put("flow_log", true.into()); }
        // start-only settings that decide
        put("guard", self.cfg.g43.as_ref().map_or(off(), |g| serde_json::json!({"mode": if g.mode == ps43_guard::Mode::Holders { "holders" } else { "deadline" },
            "holders": format!("{}:{}:{}:{}", g.n, g.theta, g.max_leavers, g.min_pct), "ab": g.ab})));
        put("fee_tier", self.cfg.b43.tier.as_ref().map_or(off(), |t| serde_json::json!({"n": t.n, "cu_price": t.cu_price})));
        put("routes", serde_json::json!({"spec_hash": fh_of(&V::from(self.cfg.routes.clone())), "classes": self.cfg.routes.split(';').filter_map(|c| c.split('=').next()).collect::<Vec<_>>()}));
        put("limits", self.cfg.limits47.clone());
        put("drop", serde_json::json!(self.cfg.drop));
        put("k", serde_json::json!(self.cfg.k));
        m
    }

    /// the filter state again; a change -> fv + 1, its record and line. `src`: start | control | auto
    pub(super) fn fs_refresh(&mut self, src: &str) {
        let m = self.fs_map();
        if self.f47.fs.is_some() && m == self.f47.map { return; }
        let fv = self.f47.fs.as_ref().map_or(0, |f| f.fv + 1);
        let changed: BTreeMap<String, serde_json::Value> = if fv == 0 { BTreeMap::new() } else {
            let keys: std::collections::BTreeSet<&String> = m.keys().chain(self.f47.map.keys()).collect();
            keys.into_iter().filter_map(|k| { let (o, n) = (self.f47.map.get(k), m.get(k)); (o != n).then(|| (k.clone(), serde_json::json!([o, n]))) }).collect()
        };
        let obj = serde_json::Value::Object(m.iter().map(|(k, v)| (k.clone(), v.clone())).collect());
        let fh = fh_of(&obj);
        let fs = Fs { fv, fh: fh.clone(), obj: Arc::new(obj.clone()) };
        FV_NOW.store(fv, Ordering::Relaxed);
        *FH_NOW.lock().unwrap() = fh.clone();
        self.f47.fs = Some(fs);
        self.f47.map = m;
        self.rec(serde_json::json!({"ev": "presend_live_filter_state", "fv": fv, "fh": fh, "src": src, "state": obj, "changed": changed, "t": arbx::feeds::clock::now_ns()}));
        if fv > 0 {
            self.line(format!("  PRESEND LIVE FILTER STATE fv={fv}: {} ({src})", changed.iter().map(|(k, v)| format!("{k} {}->{}", v[0], v[1])).collect::<Vec<_>>().join(", ")));
        }
    }

    /// the other readers' change counters (a control file change of any of them -> a refresh now); every ~1 s an auto check (FP thread's
    /// control file, anything else)
    pub(super) fn fs_tick(&mut self) {
        let seen = self.d43.ctl_changes + self.hls.ctl_changes + self.p46.ctl_changes + self.b43.n.ctl_changes + self.s1.ctl_changes + self.f47.ctl_changes;
        if seen != self.f47.seen { self.f47.seen = seen; self.fs_refresh("control"); self.f47.auto_at = Some(Instant::now()); return; }
        if self.f47.auto_at.is_none_or(|t| t.elapsed() >= Duration::from_secs(1)) { self.f47.auto_at = Some(Instant::now()); self.fs_refresh("auto"); }
    }

    /// a window armed: its ARM state (its records carry it)
    pub(super) fn f47_arm(&mut self, w: u64) {
        let Some(fs) = self.f47.fs.clone() else { return };
        self.f47.wfs.insert(w, fs);
        self.f47.wq.push_back(w);
        while self.f47.wq.len() > 4096 { if let Some(o) = self.f47.wq.pop_front() { self.f47.wfs.remove(&o); } }
    }

    /// stamp a main-loop record (rec()): fv / fh; fill / realized also "filters" (the window's ARM state) and fv_fill when it moved since
    pub(super) fn stamp47(&self, v: &mut serde_json::Value) {
        let Some(cur) = self.f47.fs.as_ref() else { return };
        let Some(ev) = v["ev"].as_str() else { return };
        if !stamped(ev) { return; }
        let t0 = arbx::fast::mono_ns();
        let full = ev == "presend_live_fill" || ev == "presend_live_realized";
        let arm = v["w"].as_u64().and_then(|w| self.f47.wfs.get(&w)).filter(|_| ev != "presend_live_skip");
        let fs = arm.unwrap_or(cur);
        v["fv"] = fs.fv.into();
        v["fh"] = fs.fh.clone().into();
        if arm.is_some() && fs.fv != cur.fv { v["fv_fill"] = cur.fv.into(); }
        if full { v["filters"] = (*fs.obj).clone(); }
        self.f47.stamp_ns.set(self.f47.stamp_ns.get() + arbx::fast::mono_ns().saturating_sub(t0));
        self.f47.stamp_n.set(self.f47.stamp_n.get() + 1);
    }
}

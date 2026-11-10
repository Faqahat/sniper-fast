// =====================================================================================================================
// dip43 BUILDER A (BUILD_DIP43.md; owner 11-10): safety, control, shadows. NO TRANSACTION CHANGE. Every feature is OFF (or LOG) unless its
// flag / control key turns it on; with no new flag the probe's sends, fees, exits and gates are dip42's (golden test dip43a_tests.rs). The
// one default-on output is the FEED-STALL watchdog's line + record (ps43_stall.rs).
//   A1 --presend-live-stall-mode log|live (log), --presend-live-stall S:L:T (1500:8:400)        key "stall"       (ps43_stall.rs)
//   A2 --presend-live-deadman log|live (log), --presend-live-deadman-ms N (1000)                key "deadman"     (ps43_stall.rs + here)
//   A3 --presend-live-tbal on|off (off; needs --presend-live-fam-log on): the true-balance book (src/ps43_book.rs; PsLive::d43.book). VERIFIER
//      11-10: the live feeds are pump-filtered (no plain transfers), so the TRUE balances come from the dip35 fam read at every arm (an RPC
//      snapshot of all the mint's token accounts, off the hot path, never awaited) merged with the pump txs' post_token_balances
//   A4 --presend-live-fanout N (off; N = 10 recipients; needs --presend-live-fam-log on), --presend-live-fanout-mode log|live (log)  key "fanout":
//      the fam read's recv_n (plain-transfer recipients still holding >= 0.05%) >= N flags the mint; live = the armed window is disarmed
//      "fanout" and later arms skip "fanout". (The tape-style 50-slot transfer count needs an unfiltered feed: not in this build)
//   A5 --presend-live-cascade on|off (off; turns the book on): the holder-floor shadow at signing / landing (onchain G-A + guards P3)
//   A6 --presend-live-mint-ledger SOL (off), --presend-live-mint-ledger-mode log|live (log)    key "mint_ledger"
//   A7 --presend-live-shadow-exit on|off (off): presend_live_shadow_exit + presend_live_stop_shadow
//   A8 --presend-live-acct on|off (off): not_sent per window on presend_live_disarm, per-slot due / sent / refused, unseen tries' fees
//   A9 the ledger control file's dip43 keys (ctl43_parse); "botdepth": "log" refused unless --presend-live-botdepth-allow-log
//   A10 --presend-live-shadows43 on|off (off): FP-NOBOT leak would_hold, T2 arm-slot send, big-holder short; --presend-live-fpnb-strict X
//       (off; FP strict on T2, log; key "fpnb_strict"); QF2 min age = the 6th field of --presend-live-qf2-filters (psdl.rs; key "qf2_min_age")
// =====================================================================================================================
use super::*;
use std::cell::Cell;

pub use super::ps43_stall as st;

// ---- config ---------------------------------------------------------------------------------------------------------

/// every dip43 Builder A option (all off / log by default)
#[derive(Clone, Debug, Default)]
pub struct Cfg43 {
    pub stall: st::StallCfg,
    pub tbal: bool,
    /// 11-10 (dip43c) --presend-live-tbal-src fam|largest (fam): where the book's arm snapshot comes from. fam = dip35's mint-wide
    /// getProgramAccounts (on --presend-live-fam-rpc; Constant-K refuses mint-scoped token scans). largest = getTokenLargestAccounts +
    /// getMultipleAccounts on the PRIMARY rpc (the top 20 token accounts, closed ones never listed): a partial snapshot of the top holders
    pub tbal_largest: bool,
    pub cascade: bool,
    /// A4: the recipients that flag a mint (None = off) and the mode
    pub fanout: Option<u32>,
    pub fanout_live: bool,
    /// A6: the loss (lamports, > 0) that blocks a mint; None = off
    pub ml: Option<i64>,
    pub ml_live: bool,
    pub shx: bool,
    pub acct: bool,
    pub bd_allow_log: bool,
    pub shadows: bool,
    /// A10: FP-NOBOT's strict threshold on T2 (log; None = off)
    pub fp_strict: Option<f64>,
}

impl Cfg43 {
    /// the flags (each needs --presend-live: checked by the caller's FLAGS refusal)
    pub fn parse(argv: &[String]) -> Result<Cfg43> {
        let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
        let arg = |f: &str| argv.iter().position(|x| x == f).and_then(|i| argv.get(i + 1)).cloned().filter(|v| !v.starts_with("--"));
        let need = |f: &str| -> Result<Option<String>> { if has(f) { Ok(Some(arg(f).with_context(|| format!("{f} needs a value"))?)) } else { Ok(None) } };
        let onoff = |f: &str| -> Result<bool> { match need(f)?.as_deref() { None | Some("off") => Ok(false), Some("on") => Ok(true), Some(x) => bail!("{f} {x}: on | off") } };
        let mode = |f: &str| -> Result<bool> { match need(f)?.as_deref() { None | Some("log") => Ok(false), Some("live") => Ok(true), Some(x) => bail!("{f} {x}: log | live") } };
        let mut c = Cfg43 { tbal: onoff("--presend-live-tbal")?, cascade: onoff("--presend-live-cascade")?, shx: onoff("--presend-live-shadow-exit")?,
            acct: onoff("--presend-live-acct")?, shadows: onoff("--presend-live-shadows43")?, bd_allow_log: has("--presend-live-botdepth-allow-log"), ..Default::default() };
        c.stall.live = mode("--presend-live-stall-mode")?;
        c.stall.deadman_live = mode("--presend-live-deadman")?;
        if let Some(s) = need("--presend-live-stall")? { let (a, b, d) = st::stall_parse(&s).map_err(|e| anyhow::anyhow!(e))?; c.stall.silent_ms = a; c.stall.lag_slots = b; c.stall.late_ms = d; }
        if let Some(s) = need("--presend-live-deadman-ms")? {
            c.stall.deadman_ms = s.parse().ok().filter(|x: &u64| *x == 0 || (200..=30_000).contains(x)).with_context(|| format!("--presend-live-deadman-ms {s}: 0 (off) or 200..30000"))?;
        }
        if let Some(s) = need("--presend-live-mint-ledger")? {
            let x: f64 = s.parse().ok().filter(|x: &f64| x.is_finite() && *x > 0.0 && *x <= 5.0).with_context(|| format!("--presend-live-mint-ledger {s}: a loss in SOL (0, 5], e.g. 0.10"))?;
            c.ml = Some((x * 1e9).round() as i64);
        }
        c.ml_live = mode("--presend-live-mint-ledger-mode")?;
        if let Some(s) = need("--presend-live-fanout")? {
            c.fanout = Some(s.parse().ok().filter(|x: &u32| (2..=1000).contains(x)).with_context(|| format!("--presend-live-fanout {s}: recipients 2..1000, e.g. 10"))?);
        }
        c.fanout_live = mode("--presend-live-fanout-mode")?;
        if has("--presend-live-fanout-mode") && c.fanout.is_none() { bail!("--presend-live-fanout-mode needs --presend-live-fanout N"); }
        if has("--presend-live-mint-ledger-mode") && c.ml.is_none() { bail!("--presend-live-mint-ledger-mode needs --presend-live-mint-ledger SOL"); }
        if let Some(s) = need("--presend-live-fpnb-strict")? {
            c.fp_strict = Some(s.parse().ok().filter(|x: &f64| x.is_finite() && *x > 0.0 && *x < 1.0).with_context(|| format!("--presend-live-fpnb-strict {s}: a score threshold in (0, 1), e.g. 0.30"))?);
        }
        // the cascade shadow reads the true balances
        if c.cascade { c.tbal = true; }
        // dip43c: the snapshot source (needs the book)
        match need("--presend-live-tbal-src")?.as_deref() {
            None | Some("fam") => {}
            Some("largest") => { if !c.tbal { bail!("--presend-live-tbal-src largest needs --presend-live-tbal on (or --presend-live-cascade on)"); } c.tbal_largest = true; }
            Some(x) => bail!("--presend-live-tbal-src {x}: fam | largest"),
        }
        Ok(c)
    }

    /// the start banner's dip43 lines (one per feature; the watchdog's always)
    pub fn banner(&self, fpnb_log: bool) -> Vec<String> {
        let mut v = vec![format!("DIP43 A1/A2 {}", self.stall.desc())];
        v.push(format!("DIP43 A3 TRUE-BALANCE BOOK: {}", if self.tbal { if self.tbal_largest { "ON (post + closed accounts decoded on the executed feed's thread; arm snapshot = getTokenLargestAccounts + getMultipleAccounts on the primary rpc, top 20)" } else { "ON (post_token_balances decoded on the executed feed's thread)" } } else { "off" }));
        v.push(format!("DIP43 A4 FANOUT: {}", match self.fanout { Some(n) => format!("ON {} (the arm's fam read: >= {n} plain-transfer recipients flag the mint)", if self.fanout_live { "LIVE: disarm + skip" } else { "LOG ONLY" }), None => "off".into() }));
        v.push(format!("DIP43 A5 CASCADE SHADOW: {}", if self.cascade { "ON (LOG ONLY): top 8 holders by true balance at signing vs just before our buy; G-A 6:0.9:2 >= 1%, guards top-5 non-trigger >= 0.5%" } else { "off" }));
        v.push(format!("DIP43 A6 MINT-LEDGER: {}", match self.ml { Some(l) => format!("ON {} (block a mint after a landing <= -{} SOL; real fills + one paper landing per T2 trigger)", if self.ml_live { "LIVE" } else { "LOG ONLY" }, l as f64 / 1e9), None => "off".into() }));
        v.push(format!("DIP43 A7 EXIT SHADOW: {}", if self.shx { "ON (presend_live_shadow_exit 12 slots after each fill + presend_live_stop_shadow)" } else { "off" }));
        v.push(format!("DIP43 A8 SEND ACCOUNTING: {}", if self.acct { "ON (not_sent per window, per-slot due/sent/refused, unseen tries' fees booked)" } else { "off" }));
        v.push(format!("DIP43 A9 CONTROL KEYS: dip43 keys read from the ledger control file; botdepth log {}", if self.bd_allow_log { "ALLOWED (--presend-live-botdepth-allow-log)" } else { "REFUSED (locked to live)" }));
        v.push(format!("DIP43 A10 SHADOWS: {}{}", if self.shadows { "ON (FP-NOBOT would_hold, T2 arm-slot send, big-holder short)" } else { "off" },
            match self.fp_strict { Some(x) => format!(" | FP strict {x} on T2 {}", if fpnb_log { "(LOG; key fpnb_strict)" } else { "(needs --presend-fpnb-log on: idle)" }), None => String::new() }));
        v
    }

    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"stall": self.stall.spec(), "stall_live": self.stall.live, "deadman_live": self.stall.deadman_live, "deadman_ms": self.stall.deadman_ms, "tbal": self.tbal,
            "cascade": self.cascade, "fanout": self.fanout, "fanout_live": self.fanout_live, "mint_ledger": self.ml.map(|l| l as f64 / 1e9), "mint_ledger_live": self.ml_live, "shadow_exit": self.shx, "acct": self.acct,
            "botdepth_allow_log": self.bd_allow_log, "shadows": self.shadows, "fpnb_strict": self.fp_strict})
    }
    /// any option given (the start record's "dip43" only then: dip42's record otherwise)
    pub fn any(&self) -> bool {
        self.tbal || self.cascade || self.fanout.is_some() || self.ml.is_some() || self.shx || self.acct || self.shadows || self.fp_strict.is_some() || self.stall != st::StallCfg::default()
    }
}

// ---- the sender's side (A1 pause, A8 accounting, A10 FP leak) -------------------------------------------------------------

/// one window's send accounting (A8)
#[derive(Clone, Debug, Default)]
pub struct NotSent { pub due: u32, pub sent: u32, pub rate_global: u32, pub rate_path: u32, pub paused_position: u32, pub paused_stall: u32, pub other: u32,
    /// per slot (slot, due, sent, refused), the window's first 16 slots
    pub slots: Vec<(u64, u32, u32, u32)> }
impl NotSent {
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"due": self.due, "sent": self.sent, "rate_global": self.rate_global, "rate_path": self.rate_path, "paused_position": self.paused_position,
            "paused_stall": self.paused_stall, "other": self.other, "slots": self.slots.iter().map(|s| [s.0, s.1 as u64, s.2 as u64, s.3 as u64]).collect::<Vec<_>>()})
    }
    fn slot(&mut self, slot: u64) -> Option<&mut (u64, u32, u32, u32)> {
        if self.slots.last().is_none_or(|x| x.0 != slot) { if self.slots.len() >= 16 { return None; } self.slots.push((slot, 0, 0, 0)); }
        self.slots.last_mut()
    }
}

/// the main loop <-> sender state of dip43 (Shared::g43; all idle by default)
#[derive(Debug, Default)]
pub struct Sh43 {
    /// A1 live: no new tries while the executed feed is blind ("paused_stall")
    pub pause_stall: AtomicBool,
    /// A9 "breaker": "log": a trip is recorded, nothing paused
    pub brk_log: AtomicBool,
    /// dip43d control key "curve_deep": "log" (true): no CURVE band on the tries (the A/B's Lighthouse arm back on Lighthouse), the bound only recorded
    pub curve_log: AtomicBool,
    /// A8 on (set at the start)
    pub acct: AtomicBool,
    pub ns: Mutex<FxHashMap<u64, NotSent>>,
    /// A10 on: tries sent while FP-NOBOT had no fresh verdict (signature -> "no_verdict" / "stale_block")
    pub leak: AtomicBool,
    pub leak_sigs: Mutex<FxHashMap<[u8; 64], &'static str>>,
}

thread_local! {
    /// the sender thread's window and slot under decision (A8: Shared::skip charges it); (0, 0) on every other thread
    static CUR43: Cell<(u64, u64)> = const { Cell::new((0, 0)) };
}

/// the sender: the due window it decides now
#[inline]
pub fn cur_set(sh: &Sh43, w: u64, slot: u64) {
    if !sh.acct.load(Ordering::Relaxed) { return; }
    CUR43.with(|c| c.set((w, slot)));
    let mut g = sh.ns.lock().unwrap();
    let n = g.entry(w).or_default();
    n.due += 1;
    if let Some(s) = n.slot(slot) { s.1 += 1; }
}
/// Shared::skip: the window under decision was not sent, why
#[inline]
pub fn acct_skip(sh: &Sh43, why: &str) {
    if !sh.acct.load(Ordering::Relaxed) { return; }
    let (w, slot) = CUR43.with(|c| c.get());
    if w == 0 { return; }
    let mut g = sh.ns.lock().unwrap();
    let n = g.entry(w).or_default();
    match why {
        "rate_global" => n.rate_global += 1,
        "rate_path" | "rate_path_config" => n.rate_path += 1,
        "paused_reactive_position" | "paused_presend_position" => n.paused_position += 1,
        "paused_stall" => n.paused_stall += 1,
        _ => n.other += 1,
    }
    if let Some(s) = n.slot(slot) { s.3 += 1; }
}
/// the sender wrote (or dry-built) the window's try
#[inline]
pub fn acct_sent(sh: &Sh43) {
    if !sh.acct.load(Ordering::Relaxed) { return; }
    let (w, slot) = CUR43.with(|c| c.get());
    if w == 0 { return; }
    let mut g = sh.ns.lock().unwrap();
    let n = g.entry(w).or_default();
    n.sent += 1;
    if let Some(s) = n.slot(slot) { s.2 += 1; }
}

/// A10: would the FP-NOBOT leak fix hold this send (the live gate passed it with no fresh verdict)? None: no / off
#[inline]
pub fn leak_why(sh: &Sh43, g: &pslog36::Gate, gs: &pslog36::GateShared, slot: u64, rearm: bool) -> Option<&'static str> {
    if !sh.leak.load(Ordering::Relaxed) || gs.mode.load(Ordering::Relaxed) & (1 << rearm as u64) == 0 { return None; }
    let v = g.v.load(Ordering::Acquire);
    let vs = v >> 2;
    if v == 0 { return Some("no_verdict"); }
    let fresh = vs == slot || vs == slot + 1;
    if !fresh && v & 3 == 3 { return Some("stale_block"); }
    // verifier 11-10: the sticky-block shadow: a fresh PASS while a block computed on the previous slot's data (or later) was superseded
    let lb = g.last_block.load(Ordering::Acquire);
    if fresh && v & 1 == 0 && lb > 0 && lb + 1 >= slot { return Some("sticky_block"); }
    None
}
pub fn leak_note(sh: &Sh43, sig: &[u8; 64], why: &'static str) {
    let mut g = sh.leak_sigs.lock().unwrap();
    if g.len() > 50_000 { g.clear(); }
    g.insert(*sig, why);
}

// ---- A9 control keys ------------------------------------------------------------------------------------------------------

/// the dip43 gates' modes (true = live: as the start flags say; false = log: the verdict is recorded, nothing skipped)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct G43 { pub quiet: bool, pub quiet3a: bool, pub create_slot: bool, pub young_age: bool, pub lone_whale: bool, pub cr_loss: bool, pub blocklist_arm: bool,
    pub rearm: bool, pub rearm_r5: bool, pub breaker: bool }
impl Default for G43 { fn default() -> G43 { G43 { quiet: true, quiet3a: true, create_slot: true, young_age: true, lone_whale: true, cr_loss: true, blocklist_arm: true, rearm: true, rearm_r5: true, breaker: true } } }
impl G43 {
    pub const KEYS: [&'static str; 10] = ["quiet", "quiet3a", "create_slot", "young_age", "lone_whale", "cr_loss", "blocklist_arm", "rearm", "rearm_r5", "breaker"];
    fn get(&self, i: usize) -> bool { [self.quiet, self.quiet3a, self.create_slot, self.young_age, self.lone_whale, self.cr_loss, self.blocklist_arm, self.rearm, self.rearm_r5, self.breaker][i] }
    fn set(&mut self, i: usize, v: bool) {
        match i { 0 => self.quiet = v, 1 => self.quiet3a = v, 2 => self.create_slot = v, 3 => self.young_age = v, 4 => self.lone_whale = v, 5 => self.cr_loss = v,
            6 => self.blocklist_arm = v, 7 => self.rearm = v, 8 => self.rearm_r5 = v, _ => self.breaker = v }
    }
}

/// the dip43 keys of the control file (None = absent: the mode stays)
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Ctl43 { pub g: [Option<bool>; 10], pub mint_ledger: Option<bool>, pub stall: Option<bool>, pub deadman: Option<bool>, pub fpnb_t2: Option<bool>,
    pub fpnb_rearm: Option<bool>, pub fpnb_strict: Option<bool>, pub qf2_size: Option<f64>, pub qf2_min_age: Option<u64>, pub fanout: Option<bool>,
    /// dip43d: the CURVE band live | log
    pub curve_deep: Option<bool> }

pub fn ctl43_parse(b: &[u8]) -> std::result::Result<Ctl43, String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    if !v.is_object() { return Err("not an object".into()); }
    let key = |k: &str| -> std::result::Result<Option<bool>, String> {
        match v.get(k) { None | Some(serde_json::Value::Null) => Ok(None), Some(x) => match x.as_str() { Some("live") => Ok(Some(true)), Some("log") => Ok(Some(false)), _ => Err(format!("{k}: '{x}' (live | log)")) } }
    };
    let mut c = Ctl43::default();
    for (i, k) in G43::KEYS.iter().enumerate() { c.g[i] = key(k)?; }
    c.mint_ledger = key("mint_ledger")?; c.stall = key("stall")?; c.deadman = key("deadman")?; c.fpnb_t2 = key("fpnb_t2")?; c.fpnb_rearm = key("fpnb_rearm")?;
    c.fpnb_strict = key("fpnb_strict")?; c.fanout = key("fanout")?; c.curve_deep = key("curve_deep")?;
    c.qf2_size = match v.get("qf2_size") { None | Some(serde_json::Value::Null) => None,
        Some(x) => Some(x.as_f64().filter(|s| s.is_finite() && *s > 0.0 && *s <= 2.0).ok_or_else(|| format!("qf2_size: '{x}' (SOL in (0, 2])"))?) };
    c.qf2_min_age = match v.get("qf2_min_age") { None | Some(serde_json::Value::Null) => None,
        Some(x) => Some(x.as_u64().filter(|a| *a <= 10_000).ok_or_else(|| format!("qf2_min_age: '{x}' (slots 0..10000)"))?) };
    Ok(c)
}

// ---- the probe's dip43 state ------------------------------------------------------------------------------------------------

/// A5: a holder set at signing: (wallet, true balance at signing, is the trigger wallet), largest first
pub type HSet = Vec<(Pk, u64, bool)>;

/// A6: one paper landing of a trigger window (the engine's own paper: entry at the first trade 12% under the trigger's price, ±20% at
/// slot ends, 6-slot timer, from the executed feed)
#[derive(Clone, Debug)]
pub struct Paper { pub mint: Pk, pub refp: f64, pub en_slot: u64, pub spend: u64, pub entry: Option<(u64, u64, f64)>, pub cur: (u64, f64) }

/// A7: one fill's exit shadow
#[derive(Clone, Debug)]
pub struct ShX { pub pid: u64, pub w: u64, pub mint: Pk, pub land: (u64, u64), pub tokens: u64, pub spend: u64, pub fr: f64, pub cur: u64, pub last_v: f64,
    pub vals: [f64; 13], pub outside: u32, pub holders: Vec<Pk>, pub top_pct: f64, pub hs1: Option<(u64, f64)>, pub exit: Option<(&'static str, u64, f64)>,
    pub sell: Option<(u64, u64)>, pub flow: (u64, u64, Option<f64>, Option<Pk>), pub stop: Option<(u64, f64, Option<f64>)>, pub closed: Option<i64> }

/// the probe's dip43 state (PsLive::d43)
#[derive(Default)]
pub struct D43 {
    pub g: G43,
    pub stall_live: bool,
    pub deadman_live: bool,
    /// A1/A2: the episode under way (its start, mono ns); 10 s after its end stale triggers are still skipped (live)
    pub blind: Option<u64>,
    pub blind_end: u64,
    pub stale_skips: u64,
    pub stale_would: u64,
    /// A2: the late tries handled (status reads asked / logged), the dead-man exits (live / would), positions opened by a status read
    pub late_seen: FxHashSet<[u8; 64]>,
    pub status_reads: u64, pub status_opened: u64, pub deadman_exits: u64, pub deadman_would: u64, pub wall_would: u64,
    pub dm_noted: FxHashSet<u64>,
    /// A3: the true-balance book
    pub book: Option<arbx::ps43_book::TBook>,
    /// A5: per armed window its holder sets by time (ns when valid, set); per sent try its set at signing
    pub wsets: FxHashMap<u64, VecDeque<(u64, std::sync::Arc<HSet>)>>,
    pub sigset: FxHashMap<[u8; 64], (u64, std::sync::Arc<HSet>)>,
    pub land_g: FxHashMap<[u8; 64], serde_json::Value>,
    pub casc_fills: u64, pub casc_ga: u64, pub casc_gd: u64,
    /// A6: mint -> (landings, worst lamports); the paper landings under way; would-blocks / blocks
    pub ml: FxHashMap<Pk, (u32, i64)>,
    pub papers: Vec<Paper>,
    pub ml_would: u64, pub ml_skips: u64, pub ml_papers: u64,
    /// A7
    pub shx: FxHashMap<u64, ShX>,
    pub shx_n: u64,
    /// A8: unseen tries' fees booked (count, lamports); per window (count, lamports)
    pub unseen: (u64, u64),
    pub w_unseen: FxHashMap<u64, (u32, u64)>,
    /// A9: the control file (path, mtime, last check) and its changes / errors
    pub ctl: Option<(String, Option<std::time::SystemTime>, Instant)>,
    pub ctl_changes: u64, pub ctl_errors: u64,
    /// A4: flagged mints (recv_n), per window its read's (recv_n, flag), would / skips / disarms
    pub fan: FxHashMap<Pk, usize>,
    pub fan_w: FxHashMap<u64, (usize, bool)>,
    pub fan_would: u64, pub fan_skips: u64, pub fan_disarms: u64,
    /// A10 counts: would-hold fills (+ sticky), T2 arm-slot fills, big-holder-short fills
    pub sticky_fills: u64,
    pub leak_fills: u64, pub armslot_fills: u64, pub bh_fills: u64,
}

/// the dip43 Cmd / PsMsg payloads (A2): a status read of a blind try
#[derive(Clone, Debug)]
pub struct StatusReq { pub sig: [u8; 64], pub w: u64, pub mint: Pk, pub first_ns: u64, pub min_out: u64 }
/// its answer: Some((landed slot, ok)) / None = unreadable; the token balance read at processed (Some(n) / None unknown)
#[derive(Clone, Debug)]
pub struct StatusRes { pub req: StatusReq, pub st: Option<(u64, bool)>, pub tokens: Option<u64>, pub ms: f64 }

pub const ML_DROP: f64 = 0.12;
pub const SHX_SLOTS: u64 = 12;
/// A10 big-holder short: a holder at landing of this % of supply -> would exit at 3 slots
pub const BH_PCT: f64 = 10.0;

fn r4(x: f64) -> f64 { (x * 1e4).round() / 1e4 }
fn jv(x: f64) -> serde_json::Value { if x.is_finite() { serde_json::json!(r4(x)) } else { serde_json::Value::Null } }

impl PsLive {
    // ---- start ----------------------------------------------------------------------------------------------------------
    /// dip43's start: the modes from the flags, the book, the accounting / leak taps, the control file (after dip37's)
    pub(super) fn d43_start(&mut self) {
        let c = self.cfg.c43.clone();
        self.d43.stall_live = c.stall.live;
        self.d43.deadman_live = c.stall.deadman_live;
        if c.tbal { arbx::feeds::tbal_on(); self.d43.book = Some(arbx::ps43_book::TBook::new()); }
        self.sh.g43.acct.store(c.acct, Ordering::SeqCst);
        self.sh.g43.leak.store(c.shadows && self.fp.is_some(), Ordering::SeqCst);
        if let (Some(x), Some(f)) = (c.fp_strict, self.fp.as_ref()) { f.gs.strict.store(x.to_bits(), Ordering::SeqCst); }
        if let Some(p) = self.cfg.ledger_ctl.clone() { self.d43.ctl = Some((p, None, Instant::now())); self.ctl43_check(true); }
        if c.any() { self.rec(serde_json::json!({"ev": "presend_live_dip43", "cfg": c.json(), "t": arbx::feeds::clock::now_ns()})); }
    }

    // ---- A9 -------------------------------------------------------------------------------------------------------------
    /// the control file's dip43 keys (every ~10 s from tick; `force`: now): applied, one presend_live_ledger_mode record ("dip43") per change
    pub(super) fn ctl43_check(&mut self, force: bool) {
        let Some((path, mt0, at)) = self.d43.ctl.clone() else { return };
        if !force && at.elapsed() < Duration::from_secs(10) { return; }
        let mt = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
        if let Some(c) = self.d43.ctl.as_mut() { c.2 = Instant::now(); }
        if !force && mt == mt0 { return; }
        if let Some(c) = self.d43.ctl.as_mut() { c.1 = mt; }
        match std::fs::read(&path).map_err(|e| e.to_string()).and_then(|b| ctl43_parse(&b)) {
            Ok(k) => { let ch = self.ctl43_apply(&k); if !ch.is_empty() { self.ctl43_rec(&path, ch); } }
            Err(e) => {
                self.d43.ctl_errors += 1;
                self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": false, "err": e, "path": path, "dip43": true, "t": arbx::feeds::clock::now_ns()}));
                self.line(format!("  PRESEND LIVE DIP43 control keys in {path} NOT read ({e}): the modes stay"));
            }
        }
    }

    /// apply the keys; -> the changes (key, was, now)
    pub(super) fn ctl43_apply(&mut self, k: &Ctl43) -> Vec<(String, serde_json::Value, serde_json::Value)> {
        let s = |x: bool| serde_json::Value::from(if x { "live" } else { "log" });
        let mut ch: Vec<(String, serde_json::Value, serde_json::Value)> = Vec::new();
        for (i, key) in G43::KEYS.iter().enumerate() {
            if let Some(v) = k.g[i] { let old = self.d43.g.get(i); if old != v { self.d43.g.set(i, v); ch.push((key.to_string(), s(old), s(v))); } }
        }
        self.sh.g43.brk_log.store(!self.d43.g.breaker, Ordering::SeqCst);
        if let Some(v) = k.stall { if v != self.d43.stall_live { ch.push(("stall".into(), s(self.d43.stall_live), s(v))); self.d43.stall_live = v; if !v { self.sh.g43.pause_stall.store(false, Ordering::SeqCst); } } }
        // dip43d: the CURVE band (only with --presend-live-guard-curve-deep D)
        if let Some(v) = k.curve_deep {
            if self.cfg.g43.as_ref().and_then(|g| g.curve_deep).is_none() { ch.push(("curve_deep_ignored".into(), serde_json::Value::Null, "needs --presend-live-guard-curve-deep D".into())); }
            else { let old = !self.sh.g43.curve_log.swap(!v, Ordering::SeqCst); if old != v { ch.push(("curve_deep".into(), s(old), s(v))); } }
        }
        if let Some(v) = k.deadman { if v != self.d43.deadman_live { ch.push(("deadman".into(), s(self.d43.deadman_live), s(v))); self.d43.deadman_live = v; } }
        if let Some(v) = k.mint_ledger {
            if self.cfg.c43.ml.is_none() { ch.push(("mint_ledger_ignored".into(), serde_json::Value::Null, "needs --presend-live-mint-ledger SOL".into())); }
            else if v != self.cfg.c43.ml_live { ch.push(("mint_ledger".into(), s(self.cfg.c43.ml_live), s(v))); self.cfg.c43.ml_live = v; }
        }
        if let Some(v) = k.fanout {
            if self.cfg.c43.fanout.is_none() { ch.push(("fanout_ignored".into(), serde_json::Value::Null, "needs --presend-live-fanout N".into())); }
            else if v != self.cfg.c43.fanout_live { ch.push(("fanout".into(), s(self.cfg.c43.fanout_live), s(v))); self.cfg.c43.fanout_live = v; }
        }
        // FP-NOBOT's live gate bits (bit 0 T2, bit 1 re-arm) and its strict variant (only with --presend-fpnb-log on)
        match self.fp.as_ref().map(|f| f.gs.clone()) {
            Some(gs) => {
                for (bit, v, name) in [(0u64, k.fpnb_t2, "fpnb_t2"), (1, k.fpnb_rearm, "fpnb_rearm")] {
                    let Some(v) = v else { continue };
                    let old = gs.mode.load(Ordering::SeqCst);
                    let new = if v { old | (1 << bit) } else { old & !(1 << bit) };
                    if new != old { gs.mode.store(new, Ordering::SeqCst); ch.push((name.into(), s(old & (1 << bit) != 0), s(v))); }
                }
                if let Some(v) = k.fpnb_strict {
                    if self.cfg.c43.fp_strict.is_none() { ch.push(("fpnb_strict_ignored".into(), serde_json::Value::Null, "needs --presend-live-fpnb-strict X".into())); }
                    else { let old = gs.strict_live.swap(v, Ordering::SeqCst); if old != v { ch.push(("fpnb_strict".into(), s(old), s(v))); } }
                }
            }
            None => if k.fpnb_t2.is_some() || k.fpnb_rearm.is_some() || k.fpnb_strict.is_some() { ch.push(("fpnb_ignored".into(), serde_json::Value::Null, "needs --presend-fpnb-log on".into())); },
        }
        // QF2's size and minimum token age (only with --presend-live-qf2): the size within the sizes the start checked against --max-sol
        if k.qf2_size.is_some() || k.qf2_min_age.is_some() {
            let cap = self.cfg.spend.max(self.cfg.wd_size);
            match self.wd.as_mut().filter(|w| w.qf.is_some()) {
                Some(w) => {
                    if let Some(x) = k.qf2_size {
                        let l = (x * 1e9).round() as u64;
                        if l > cap { ch.push(("qf2_size_refused".into(), serde_json::json!(x), format!("above the start's largest size {:.3} SOL", cap as f64 / 1e9).into())); }
                        else if w.qf_size != Some(l) { ch.push(("qf2_size".into(), serde_json::json!(w.qf_size.unwrap_or(w.size) as f64 / 1e9), serde_json::json!(x))); w.qf_size = Some(l); }
                    }
                    if let Some(a) = k.qf2_min_age { if w.filt.age_min != a { ch.push(("qf2_min_age".into(), w.filt.age_min.into(), a.into())); w.filt.age_min = a; } }
                }
                None => ch.push(("qf2_ignored".into(), serde_json::Value::Null, "needs --presend-live-qf2".into())),
            }
        }
        ch
    }

    fn ctl43_rec(&mut self, path: &str, ch: Vec<(String, serde_json::Value, serde_json::Value)>) {
        self.d43.ctl_changes += 1;
        let mut now = serde_json::Map::new();
        let mut was = serde_json::Map::new();
        for (k, o, n) in &ch { now.insert(k.clone(), n.clone()); was.insert(k.clone(), o.clone()); }
        self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": true, "dip43": now, "was": {"dip43": was}, "path": path, "t": arbx::feeds::clock::now_ns()}));
        self.line(format!("  PRESEND LIVE DIP43 KEYS ({path}): {}", ch.iter().map(|(k, o, n)| format!("{k} {o} -> {n}")).collect::<Vec<_>>().join(", ")));
    }

    // ---- A1 / A2 --------------------------------------------------------------------------------------------------------
    /// the watchdog's view of a signature: one of our tries, not resolved yet
    pub fn unresolved43(&self, sig: &[u8; 64]) -> bool { self.atts.get(sig).is_some_and(|x| !x.1) }

    /// an episode's start / end (dipmode's watchdog): the pause (live) and the blind clock
    pub fn stall43(&mut self, start: bool, now_ns: u64) {
        if start {
            self.d43.blind = Some(now_ns);
            if self.d43.stall_live { self.sh.g43.pause_stall.store(true, Ordering::SeqCst); }
        } else {
            self.d43.blind = None;
            self.d43.blind_end = now_ns;
            self.sh.g43.pause_stall.store(false, Ordering::SeqCst);
        }
    }
    pub fn stall_live43(&self) -> bool { self.d43.stall_live }
    /// A3 for Builder C (ps43_guard.rs holders_for_floor): the true-balance book (None: --presend-live-tbal off). Use
    /// `tbook()?.top_holders(mint, n)` / `tbook()?.true_balance(mint, wallet)`
    pub fn tbook(&self) -> Option<&arbx::ps43_book::TBook> { self.d43.book.as_ref() }
    /// A12: is the mint armed / held by the probe now (the react-watch record's overlap)
    pub fn overlap43(&self, m: &Pk) -> (bool, bool) { (self.armed.contains_key(m), self.pos.contains_key(m)) }
    /// open positions / tries in flight (the FEED-STALL line)
    pub fn inflight43(&self) -> (usize, usize, usize) { (self.armed.len(), self.pos.len(), self.atts.values().filter(|x| !x.1).count()) }

    /// A1 live: a trigger more than 2 slots behind the slot clock during an episode or 10 s after it (counted "would" in log)
    pub(super) fn stale43(&mut self, trig_slot: u64) -> bool {
        let recent = self.d43.blind.is_some() || (self.d43.blind_end > 0 && arbx::fast::mono_ns().saturating_sub(self.d43.blind_end) <= 10_000_000_000);
        if !recent || self.sh.cur_slot() <= trig_slot + 2 { return false; }
        if self.d43.stall_live { self.d43.stale_skips += 1; true } else { self.d43.stale_would += 1; false }
    }

    /// A2: one of our tries seen on a shred feed with no result after LATE_MS: a status read (live) or a would-record (log)
    pub fn blind_try43(&mut self, sig: [u8; 64], first_ns: u64) {
        if !self.d43.late_seen.insert(sig) { return; }
        let Some((a, _)) = self.atts.get(&sig) else { return };
        let req = StatusReq { sig, w: a.w, mint: a.mint, first_ns, min_out: a.min_out };
        let live = self.d43.deadman_live;
        self.rec(serde_json::json!({"ev": "presend_live_blind", "sig": bs58::encode(&sig).into_string(), "w": a.w, "mint": b58(&a.mint), "first_rx_mono": first_ns,
            "mode": if live { "live" } else { "log" }, "act": if live { "status_read" } else { "would_status_read" }, "t": arbx::feeds::clock::now_ns()}));
        if live { self.d43.status_reads += 1; self.exec(Cmd::Status(Box::new(req))); }
    }

    /// A2: a status read's answer: landed OK and not seen on the feed yet -> a position opened now ("status"), the hold clock from the try's
    /// first sighting; a read that failed -> a guess sell of the try's min_out (live only); a failed / not landed try -> nothing
    pub(super) fn on_status43(&mut self, r: StatusRes) {
        let sig_s = bs58::encode(&r.req.sig).into_string();
        let seen = self.atts.get(&r.req.sig).is_none_or(|x| x.1);
        let mut rec = serde_json::json!({"ev": "presend_live_blind", "sig": sig_s, "w": r.req.w, "mint": b58(&r.req.mint), "status": r.st.map(|x| serde_json::json!({"slot": x.0, "ok": x.1})),
            "tokens": r.tokens, "ms": r.ms, "feed_saw_it": seen, "t": arbx::feeds::clock::now_ns()});
        let act = match (r.st, seen) {
            (_, true) => "none_feed_first",
            (Some((_, false)), _) => "none_failed",
            (Some((slot, true)), false) => {
                if self.pos.contains_key(&r.req.mint) { "none_position_open" } else {
                    let tokens = r.tokens.filter(|t| *t > 0).unwrap_or(r.req.min_out);
                    self.open_status43(&r.req, slot, tokens, r.tokens.is_some_and(|t| t > 0));
                    "opened"
                }
            }
            (None, false) => {
                if self.d43.deadman_live && !self.pos.contains_key(&r.req.mint) {
                    // the read failed: the guess sell (EXIT-4 (3)): a position of min_out tokens, sold at once
                    let s = self.sh.cur_slot();
                    self.open_status43(&r.req, s, r.req.min_out, false);
                    let m = r.req.mint;
                    self.exit(&m, "deadman_guess", s, f64::NAN, arbx::feeds::clock::now_ns());
                    "guess_sell"
                } else { "none_unreadable" }
            }
        };
        rec["act"] = act.into();
        self.rec(rec);
    }

    /// A2: open a position from a status read (as dip19's orphan, but the try's signature known and the hold clock from its first sighting)
    fn open_status43(&mut self, req: &StatusReq, slot: u64, tokens: u64, exact: bool) {
        let Some((att, done)) = self.atts.get_mut(&req.sig) else { return };
        *done = true;
        let att = att.clone();
        self.resolve(&att, "ok");
        self.d43.status_opened += 1;
        let (rearm, spend) = (self.rearm_w(att.w), self.w_spend(att.w));
        if let Some(w) = self.wins.get_mut(&att.w) { w.filled = true; }
        self.disarm(att.w, "filled");
        let cost = spend + self.cfg.fail_fee() + att.tip + T22_ATA_RENT;
        let (launch, derived) = match self.launches.get(&req.mint).cloned() { Some(l) => (l, false), None => (snipe_build::launch_from_target(req.mint, req.mint), true) };
        let e = self.ends.entry(req.mint).or_default(); *e = (*e).max(slot);
        self.ata_held(req.mint, slot);
        self.pid += 1;
        let acct = PsAcct::open(req.mint, cost, slot);
        let sig = bs58::encode(&req.sig).into_string();
        let buy = Buy { sig: sig.clone(), w: att.w, slot, idx: 0, t_rx: arbx::feeds::clock::now_ns(), tokens, sol_in: spend, fee: 0, tip: att.tip, cost, round: 0, via: "status" };
        // the hold clock from the first sighting (mono ns -> an Instant that many ms ago)
        let ago = Duration::from_nanos(arbx::fast::mono_ns().saturating_sub(req.first_ns));
        let opened = Instant::now().checked_sub(ago).unwrap_or_else(Instant::now);
        self.pos.insert(req.mint, PPos { pid: self.pid, w: att.w, mint: req.mint, launch, derived, buys: vec![buy], land: (slot, 0, arbx::feeds::clock::now_ns()), tokens, spend,
            att: Some(att.clone()), exit: None, sell_lands: Vec::new(), sells: Vec::new(), round: 0, selling: false, opened, acct, merged: 0, late: 0, via: "status", rearm });
        self.sh.pause_pos.store(true, Ordering::Relaxed);
        self.tapes.entry(req.mint).or_insert_with(|| (VecDeque::new(), 0));
        self.rec(serde_json::json!({"ev": "presend_live_fill", "w": att.w, "n": att.n, "mint": b58(&req.mint), "sig": sig, "slot": slot, "tokens": tokens, "tokens_exact": exact,
            "via": "status", "held_ms_at_open": ago.as_secs_f64() * 1e3, "path": att.path, "client": att.client}));
        self.line(format!("  PRESEND LIVE BLIND FILL w{} {}: landed (status read) {} tokens{}, held {:.0} ms blind: position opened, exits on the wall clock",
            att.w, b58(&req.mint), tokens, if exact { "" } else { " (estimate: min_out)" }, ago.as_secs_f64() * 1e3));
        self.alert(arbx::alerts::Level::Critical, "dip_presend_blind_fill", &b58(&req.mint), "🚨", "PRESEND LIVE: a fill seen only by a status read (feed blind)",
            arbx::alerts::format::Body::new().raw(format!("mint {}", tg::mint_link(&req.mint))).kv("tokens", tokens.to_string()));
    }

    /// A2 dedupe: the feed shows a fill a status read opened already -> its buy gets the feed's values, nothing opened twice. true = handled
    pub(super) fn fill_dedupe43(&mut self, t: &pl::Trade, fee: u64) -> bool {
        if self.d43.status_opened == 0 { return false; }
        let sig = bs58::encode(&t.sig).into_string();
        let Some(p) = self.pos.get_mut(&t.mint) else { return false };
        let Some(b) = p.buys.iter_mut().find(|b| b.via == "status" && b.sig == sig) else { return false };
        b.tokens = t.tok; b.sol_in = t.sol; b.fee = fee; b.slot = t.s; b.idx = t.i as u64; b.via = "status+feed";
        if p.round == 0 { p.tokens = p.buys.iter().filter(|b| b.round == 0).map(|b| b.tokens).sum(); }
        let r = serde_json::json!({"ev": "presend_live_blind", "sig": sig, "mint": b58(&t.mint), "act": "feed_confirmed", "slot": t.s, "idx": t.i, "tokens": t.tok, "t": t.t_rx});
        self.rec(r);
        true
    }

    /// A2 (tick): the dead-man: a position open during an episode longer than DEADMAN_MS is sold at once (live) / logged once (log)
    pub(super) fn deadman43(&mut self, slot_now: u64) {
        let Some(t0) = self.d43.blind else { return };
        let ms = arbx::fast::mono_ns().saturating_sub(t0) / 1_000_000;
        let dm = self.cfg.c43.stall.deadman_ms;
        if dm == 0 || ms < dm { return; }
        let due: Vec<(Pk, u64)> = self.pos.values().filter(|p| p.exit.is_none()).map(|p| (p.mint, p.pid)).collect();
        for (m, pid) in due {
            if self.d43.deadman_live { self.d43.deadman_exits += 1; self.exit(&m, "deadman", slot_now, f64::NAN, arbx::feeds::clock::now_ns()); }
            else if self.d43.dm_noted.insert(pid) {
                self.d43.deadman_would += 1;
                self.rec(serde_json::json!({"ev": "presend_live_deadman", "mint": b58(&m), "pid": pid, "would": "deadman", "blind_ms": ms, "t": arbx::feeds::clock::now_ns()}));
            }
        }
    }
    /// A2: the wall-clock backstop for time_exit_due (dip42's unless the dead-man is live)
    pub(super) fn wall43(&self) -> u64 { st::wall_ms(self.cfg.exit_slots, self.d43.deadman_live) }
    /// A2 log: the short backstop would have sold before dip42's (once per position)
    pub(super) fn wall_would43(&mut self, pid: u64, mint: &Pk, held_ms: u64) {
        if self.d43.deadman_live || held_ms <= st::wall_ms(self.cfg.exit_slots, true) || !self.d43.dm_noted.insert(pid | (1 << 63)) { return; }
        self.d43.wall_would += 1;
        self.rec(serde_json::json!({"ev": "presend_live_deadman", "mint": b58(mint), "pid": pid, "would": "time-limit-wall43", "held_ms": held_ms, "t": arbx::feeds::clock::now_ns()}));
    }

    // ---- A8 -------------------------------------------------------------------------------------------------------------
    /// the disarm record's not_sent (A8 on): the window's accounting so far (the sender stops with the disarm)
    pub(super) fn acct_disarm43(&mut self, r: &mut serde_json::Value, id: u64) {
        if !self.cfg.c43.acct { return; }
        let n = self.sh.g43.ns.lock().unwrap().remove(&id).unwrap_or_default();
        r["not_sent"] = n.json();
    }
    /// an unseen try's fee, booked once its deadline passed (A8 on): the attempt's failed-try fee
    pub(super) fn acct_unseen43(&mut self, att: &Att) {
        if !self.cfg.c43.acct { return; }
        let f = att.fa.as_ref().map_or_else(|| self.cfg.fail_fee(), |f| f.fail_fee());
        self.d43.unseen.0 += 1; self.d43.unseen.1 += f;
        let e = self.d43.w_unseen.entry(att.w).or_default(); e.0 += 1; e.1 += f;
    }
    /// a window forgotten (every try resolved): its unseen tries' fee record (A8 on, only with one)
    pub(super) fn acct_forget43(&mut self, id: u64) {
        if let Some((n, f)) = self.d43.w_unseen.remove(&id) {
            self.rec(serde_json::json!({"ev": "presend_live_unseen_fee", "w": id, "unseen": n, "fee_est": f, "total_unseen": self.d43.unseen.0, "total_fee_est": self.d43.unseen.1}));
        }
    }

    // ---- A3 / A5: the book, the holder sets ----------------------------------------------------------------------------
    /// an executed tx's creates and post balances into the book (A3 on; after the tx's trades: a fill in it saw the state before it)
    pub(super) fn book43(&mut self, a: &arbx::feeds::Arrival, x: &arbx::feeds::ExecInfo) {
        let Some(b) = self.d43.book.as_mut() else { return };
        for c in &x.creates { b.create(c.mint, a.slot, c.bonding_curve); }
        if let Some(v) = arbx::feeds::tbal_take(&a.tx.sig) { for tb in &v { b.post(tb, a.slot); } }
        // A5: the armed windows of this tx's mints get their set as of now (the next try signs with it)
        if self.cfg.c43.cascade {
            let ms: Vec<Pk> = x.trades.iter().map(|e| e.mint).filter(|m| self.armed.contains_key(m)).collect();
            for m in ms { if let Some(&id) = self.armed.get(&m) { self.wset43(id, &m); } }
        }
    }

    /// A5: the top 8 holders >= 0.5% by true balance now (ours excluded; the window's trigger wallet marked)
    fn hset43(&self, mint: &Pk, trig: &Pk) -> HSet {
        let Some(b) = self.d43.book.as_ref() else { return Vec::new() };
        let min = (0.005 * pl::SUPPLY) as u64;
        b.top_holders(mint, 9).into_iter().filter(|h| h.0 != self.user && h.1 >= min).take(8).map(|(w, a)| (w, a, w == *trig)).collect()
    }
    /// A5: a window's set as of now (at its arm and after each trade of its mint)
    pub(super) fn wset43(&mut self, id: u64, mint: &Pk) {
        let trig = self.wins.get(&id).map_or([0u8; 32], |w| w.whale);
        let s = std::sync::Arc::new(self.hset43(mint, &trig));
        let q = self.d43.wsets.entry(id).or_default();
        if q.back().is_some_and(|x| *x.1 == *s) { return; }
        q.push_back((arbx::feeds::clock::now_ns(), s));
        while q.len() > 8 { q.pop_front(); }
    }
    /// A5: a registered try's set at its signing (the window's set valid at its send time)
    pub(super) fn sign43(&mut self, a: &Att) {
        if !self.cfg.c43.cascade { return; }
        let Some(q) = self.d43.wsets.get(&a.w) else { return };
        let s = q.iter().rev().find(|x| x.0 <= a.t_send).or(q.front()).map(|x| x.1.clone());
        if let Some(s) = s { self.d43.sigset.insert(a.sig, (a.w, s)); }
        if self.d43.sigset.len() > 50_000 { self.d43.sigset.clear(); }
    }
    /// A5: the verdicts of a set against the book now (the state at this position: the feed's chain order). G-A (onchain): top-6 >= 1%,
    /// floor 0.9 x signing, abort at >= 2 below; guards: top-5 non-trigger >= 0.5%, >= 2 below 90%
    pub(super) fn cascade43(&self, mint: &Pk, set: &HSet) -> serde_json::Value {
        let b = self.d43.book.as_ref();
        let now = |w: &Pk| b.and_then(|b| b.true_balance(mint, w)).unwrap_or(0);
        let pct = |x: u64| r4(x as f64 / pl::SUPPLY * 100.0);
        let rows: Vec<(Pk, u64, bool, u64)> = set.iter().map(|(w, s, t)| (*w, *s, *t, now(w))).collect();
        let below = |r: &&(Pk, u64, bool, u64)| (r.3 as f64) < 0.9 * r.1 as f64;
        let one = (0.01 * pl::SUPPLY) as u64;
        let ga_set: Vec<&(Pk, u64, bool, u64)> = rows.iter().filter(|r| r.1 >= one).take(6).collect();
        let ga_n = ga_set.iter().filter(|r| below(r)).count();
        let gd_set: Vec<&(Pk, u64, bool, u64)> = rows.iter().filter(|r| !r.2).take(5).collect();
        let gd_n = gd_set.iter().filter(|r| below(r)).count();
        let snap = b.and_then(|b| b.snap(mint)).map(|(s, t)| serde_json::json!({"slot": s, "age_ms": (arbx::fast::mono_ns().saturating_sub(t) as f64 / 1e6).round()}));
        serde_json::json!({"snap": snap, "set": rows.iter().map(|r| serde_json::json!({"w": b58(&r.0), "sign_pct": pct(r.1), "land_pct": pct(r.3), "trig": r.2})).collect::<Vec<_>>(),
            "ga": {"n": ga_set.len(), "below": ga_n, "abort": ga_n >= 2}, "gd": {"n": gd_set.len(), "below": gd_n, "abort": gd_n >= 2}})
    }
    /// A5: a try's verdict now (its own set; None = no set)
    pub(super) fn cascade_sig43(&self, sig: &[u8; 64], mint: &Pk) -> Option<serde_json::Value> {
        let (_, s) = self.d43.sigset.get(sig)?;
        Some(self.cascade43(mint, s))
    }
    /// A5: a later try of a window that failed ata_exists: its verdict at its own position (on_arrival: the feed's order), for its land record
    pub(super) fn land_note43(&mut self, sig: &[u8; 64], mint: &Pk, res: &str) {
        if !self.cfg.c43.cascade || res != "ata_exists" { return; }
        if let Some(j) = self.cascade_sig43(sig, mint) { self.d43.land_g.insert(*sig, j); }
    }
    pub(super) fn land_rec43(&mut self, r: &mut serde_json::Value, sig: &[u8; 64]) {
        if let Some(j) = self.d43.land_g.remove(sig) { r["cascade"] = j; }
        self.d43.sigset.remove(sig);
    }

    // ---- A3 snapshot / A4 fanout: the dip35 fam read's answer ------------------------------------------------------------
    /// the fam read answered (pslog35::fam_done): the snapshot into the book (A3 on), the fan-out verdict (A4 on: the window disarmed in live).
    /// -> the fam record's "fanout" (None with A4 off)
    pub(super) fn fam43(&mut self, req: &FamReq, slot: u64, hold: &[(Pk, u64)], recv_n: usize) -> Option<serde_json::Value> {
        if let Some(b) = self.d43.book.as_mut() {
            b.snapshot(req.mint, req.curve, hold, slot, arbx::fast::mono_ns());
            if self.cfg.c43.cascade { if let Some(&id) = self.armed.get(&req.mint) { self.wset43(id, &req.mint); } }
        }
        // dip43 merge: the guard's holder floors from this snapshot at once (holders mode only)
        self.g43_refresh(&req.mint);
        let n = self.cfg.c43.fanout? as usize;
        let flag = recv_n >= n;
        self.d43.fan_w.insert(req.w, (recv_n, flag));
        if self.d43.fan_w.len() > 20_000 { self.d43.fan_w.clear(); }
        let mut act = "none";
        if flag {
            self.d43.fan.insert(req.mint, recv_n);
            if self.cfg.c43.fanout_live {
                if self.wins.get(&req.w).is_some_and(|w| w.disarmed.is_none()) { self.d43.fan_disarms += 1; self.disarm(req.w, "fanout"); act = "disarmed"; }
            } else { self.d43.fan_would += 1; act = "would_disarm"; }
            self.line(format!("  PRESEND LIVE FANOUT {} w{} {}: {recv_n} plain-transfer recipients (>= {n}) -> {act}", if self.cfg.c43.fanout_live { "LIVE" } else { "(log)" }, req.w, b58(&req.mint)));
        }
        Some(serde_json::json!({"n": recv_n, "thr": n, "flag": flag, "act": act}))
    }
    /// A4: the mint's flag for an arm / skip / fill record (None with A4 off)
    pub(super) fn fan_json43(&self, mint: &Pk, w: Option<u64>) -> Option<serde_json::Value> {
        self.cfg.c43.fanout?;
        let wv = w.and_then(|w| self.d43.fan_w.get(&w)).copied();
        Some(serde_json::json!({"flag": self.d43.fan.contains_key(mint), "n": self.d43.fan.get(mint).copied().or(wv.map(|x| x.0)), "read": wv.is_some()}))
    }
    /// A4 at a trigger: a flagged mint is skipped "fanout" (live) / counted (log)
    pub(super) fn fan_skip43(&mut self, mint: &Pk) -> bool {
        if self.cfg.c43.fanout.is_none() || !self.d43.fan.contains_key(mint) { return false; }
        if self.cfg.c43.fanout_live { self.d43.fan_skips += 1; true } else { self.d43.fan_would += 1; false }
    }

    // ---- A6 mint ledger -------------------------------------------------------------------------------------------------
    /// the mint's view: Some((landings, worst, would block)) (A6 on)
    pub(super) fn ml_view43(&self, mint: &Pk) -> Option<(u32, i64, bool)> {
        let loss = self.cfg.c43.ml?;
        let (n, w) = self.d43.ml.get(mint).copied().unwrap_or((0, 0));
        Some((n, w, n > 0 && w <= -loss))
    }
    pub(super) fn ml_json43(v: (u32, i64, bool)) -> serde_json::Value { serde_json::json!({"n": v.0, "worst": v.1, "would_block": v.2}) }
    /// a landing's result into the ledger (real: realized estimate at the close; paper: the engine's own)
    pub(super) fn ml_add43(&mut self, mint: Pk, pnl: i64, paper: bool) {
        if self.cfg.c43.ml.is_none() { return; }
        let e = self.d43.ml.entry(mint).or_insert((0, i64::MAX));
        e.0 += 1; e.1 = e.1.min(pnl);
        let (n, worst) = *e;
        self.rec(serde_json::json!({"ev": "presend_live_mint_ledger", "mint": b58(&mint), "pnl": pnl, "paper": paper, "n": n, "worst": worst}));
        if self.d43.ml.len() > 100_000 { self.d43.ml.clear(); }
    }
    /// a T2 trigger's paper landing (non-structural triggers: not create_slot / young_age)
    pub(super) fn paper43(&mut self, t: &pl::Trade, why: Option<&str>, spend: u64) {
        if self.cfg.c43.ml.is_none() || matches!(why, Some("create_slot" | "young_age")) { return; }
        if self.d43.papers.len() >= 4_096 { return; }
        let en_slot = t.s + self.cfg.window_slots + 1;
        self.d43.papers.push(Paper { mint: t.mint, refp: t.p(), en_slot, spend, entry: None, cur: (0, f64::NAN) });
    }
    /// every trade (A6 papers, A7 shadows)
    pub(super) fn trade43(&mut self, t: &pl::Trade) {
        if self.cfg.c43.ml.is_some() && !self.d43.papers.is_empty() {
            let mut done: Vec<(Pk, i64)> = Vec::new();
            self.d43.papers.retain_mut(|p| {
                if p.mint != t.mint { return true; }
                match p.entry {
                    None => {
                        if t.s > p.en_slot { return false; }
                        if t.p() <= p.refp * (1.0 - ML_DROP) { p.entry = Some((t.s, pl::buy_out(t.vsol, t.vtok, p.spend, t.fr()), t.fr())); p.cur = (t.s, 1.0); }
                        true
                    }
                    Some((s0, tok, fr)) => {
                        // a slot ended: its last value decides (±20%, the 6-slot timer)
                        if t.s > p.cur.0 && p.cur.0 > s0 && (p.cur.1 >= 1.2 || p.cur.1 <= 0.8 || p.cur.0 >= s0 + 6) {
                            done.push((p.mint, ((p.cur.1 - 1.0) * p.spend as f64) as i64)); return false;
                        }
                        p.cur = (t.s, pl::value(t.vsol, t.vtok, tok, fr, p.spend));
                        true
                    }
                }
            });
            for (m, pnl) in done { self.d43.ml_papers += 1; self.ml_add43(m, pnl, true); }
        }
        if self.cfg.c43.shx && !self.d43.shx.is_empty() {
            let user = self.user;
            for x in self.d43.shx.values_mut().filter(|x| x.mint == t.mint) {
                if t.s > x.cur && x.cur >= x.land.0 { let k = (x.cur - x.land.0) as usize; for i in k..13.min((t.s - x.land.0) as usize) { x.vals[i] = x.last_v; } }
                x.cur = x.cur.max(t.s);
                x.last_v = pl::value(t.vsol, t.vtok, x.tokens, x.fr, x.spend);
                if t.user == user { continue; }
                if t.s <= x.land.0 + SHX_SLOTS { x.outside += 1; }
                if !t.buy && x.hs1.is_none() && x.holders.contains(&t.user) { x.hs1 = Some((t.s, x.last_v)); }
                if let Some((ss, st)) = x.sell {
                    if t.s <= ss + 3 && (t.s, t.i as u64) > (ss, 0) {
                        if t.buy { x.flow.0 += t.sol; if x.flow.2.is_none() { x.flow.2 = Some(t.t_rx.saturating_sub(st) as f64 / 1e6); x.flow.3 = Some(t.user); } } else { x.flow.1 += t.sol; }
                    }
                }
                if let Some(s) = x.stop.as_mut() { if s.2.is_none() && t.s > s.0 { s.2 = Some(x.last_v); } }
            }
        }
    }
    /// the papers / shadows of mints the probe forgot (tick)
    pub(super) fn tick43(&mut self, slot_now: u64) {
        if !self.d43.papers.is_empty() {
            let mut done: Vec<(Pk, i64)> = Vec::new();
            self.d43.papers.retain(|p| match p.entry {
                None => slot_now <= p.en_slot + 2,
                Some((s0, _, _)) => if slot_now > s0 + 8 { done.push((p.mint, ((p.cur.1 - 1.0) * p.spend as f64) as i64)); false } else { true },
            });
            for (m, pnl) in done { self.d43.ml_papers += 1; self.ml_add43(m, pnl, true); }
        }
        if !self.d43.shx.is_empty() {
            let due: Vec<u64> = self.d43.shx.values().filter(|x| x.closed.is_some() && slot_now > (x.land.0 + SHX_SLOTS).max(x.sell.map_or(0, |s| s.0 + 3)) + 1).map(|x| x.pid).collect();
            for pid in due { if let Some(x) = self.d43.shx.remove(&pid) { self.shx_rec43(x); } }
        }
        if let Some(b) = self.d43.book.as_mut() {
            if slot_now % 64 == 0 { let (armed, pos) = (&self.armed, &self.pos); b.retire(slot_now, |m| armed.contains_key(m) || pos.contains_key(m)); }
        }
        let ids: Vec<u64> = self.d43.wsets.keys().copied().filter(|id| !self.wins.get(id).is_some_and(|w| w.disarmed.is_none())).collect();
        for id in ids { self.d43.wsets.remove(&id); }
        self.ctl43_check(false);
    }

    // ---- A7 / A10 at the fill, the exit, the close ----------------------------------------------------------------------
    /// the fill record's dip43 fields and the shadows' start (each only with its flag)
    pub(super) fn fill43(&mut self, rec: &mut serde_json::Value, att: &Att, t: &pl::Trade) {
        if !self.cfg.c43.any() { return; }
        let c = self.cfg.c43.clone();
        if c.cascade {
            if let Some(j) = self.cascade_sig43(&att.sig, &t.mint) {
                self.d43.casc_fills += 1;
                if j["ga"]["abort"] == true { self.d43.casc_ga += 1; }
                if j["gd"]["abort"] == true { self.d43.casc_gd += 1; }
                rec["cascade"] = j;
            }
        }
        if let Some(v) = self.ml_view43(&t.mint) { rec["mint_ledger"] = PsLive::ml_json43(v); }
        if let Some(j) = self.fan_json43(&t.mint, Some(att.w)) { rec["fanout"] = j; }
        if !(c.shadows || c.shx) { return; }
        let holders = self.det.holders_at_least(&t.mint, (0.02 * pl::SUPPLY) as i64, &self.user).unwrap_or_default();
        let top_pct = holders.iter().map(|h| h.1).max().unwrap_or(0) as f64 / pl::SUPPLY * 100.0;
        if c.shadows {
            let trig = self.wins.get(&att.w).map(|w| w.trig_slot);
            let armslot = !self.rearm_w(att.w) && trig == Some(att.slot);
            if armslot { self.d43.armslot_fills += 1; }
            let bh = top_pct >= BH_PCT;
            if bh { self.d43.bh_fills += 1; }
            let leak = self.sh.g43.leak_sigs.lock().unwrap().remove(&att.sig);
            let sticky = leak == Some("sticky_block");
            let leak = leak.filter(|x| *x != "sticky_block");
            if leak.is_some() { self.d43.leak_fills += 1; }
            if sticky { self.d43.sticky_fills += 1; }
            rec["shadows43"] = serde_json::json!({"would_hold": leak, "would_hold_sticky": sticky, "t2_armslot": armslot, "bh_short": {"top_pct": r4(top_pct), "would": bh}});
        }
        if c.shx {
            self.d43.shx_n += 1;
            let pid = self.pos.get(&t.mint).map_or(self.pid + 1, |p| p.pid);
            let spend = self.w_spend(att.w);
            self.d43.shx.entry(pid).or_insert(ShX { pid, w: att.w, mint: t.mint, land: (t.s, t.i as u64), tokens: t.tok, spend, fr: t.fr(), cur: t.s,
                last_v: pl::value(t.vsol, t.vtok, t.tok, t.fr(), spend), vals: [f64::NAN; 13], outside: 0, holders: holders.iter().map(|h| h.0).collect(),
                top_pct, hs1: None, exit: None, sell: None, flow: (0, 0, None, None), stop: None, closed: None });
        }
    }
    /// the position's exit decision (A7: the shadow's real exit; the stop shadow on a stop / take-profit)
    pub(super) fn exit43(&mut self, mint: &Pk, why: &'static str, slot: u64, val: f64, t: u64, pid: u64) {
        if !self.cfg.c43.shx { return; }
        if let Some(x) = self.d43.shx.get_mut(&pid) {
            x.exit = Some((why, slot, val));
            if why == "stop-loss" || why == "take-profit" { x.stop = Some((slot, val, None)); }
        }
        if why == "stop-loss" || why == "take-profit" {
            self.rec(serde_json::json!({"ev": "presend_live_stop_shadow", "mint": b58(mint), "pid": pid, "why": why, "v_trigger": jv(val), "slot": slot, "t": t}));
        }
    }
    /// our sell landed (A7: the flow after it)
    pub(super) fn sell_land43(&mut self, mint: &Pk, slot: u64, t_rx: u64) {
        if !self.cfg.c43.shx { return; }
        if let Some(x) = self.d43.shx.values_mut().find(|x| x.mint == *mint && x.closed.is_none()) { if x.sell.is_none() { x.sell = Some((slot, t_rx)); } }
    }
    /// the position closed (A6: its result into the mint ledger; A7: the shadow can finish)
    pub(super) fn close43(&mut self, pid: u64, mint: Pk, curve: Option<i64>, fees: u64, tips: u64) {
        let est = curve.map(|c| c - fees as i64 - tips as i64);
        if let Some(e) = est { self.ml_add43(mint, e, false); }
        if let Some(x) = self.d43.shx.get_mut(&pid) { x.closed = Some(est.unwrap_or(i64::MIN)); }
    }
    fn shx_rec43(&mut self, x: ShX) {
        let mut vals = x.vals;
        // slots after the last trade carry its value
        if x.cur >= x.land.0 { let k = ((x.cur - x.land.0) as usize).min(13); for v in vals.iter_mut().skip(k) { if v.is_nan() { *v = x.last_v; } } }
        let v = |k: usize| jv(vals[k]);
        let adv3 = (1..=3).find(|k| vals[*k] < 0.95).map(|k| serde_json::json!([k, r4(vals[k])]));
        self.rec(serde_json::json!({"ev": "presend_live_shadow_exit", "pid": x.pid, "w": x.w, "mint": b58(&x.mint), "land": [x.land.0, x.land.1],
            "vals": vals.iter().map(|x| jv(*x)).collect::<Vec<_>>(), "outside": x.outside,
            "flow3": {"buy_sol": x.flow.0, "sell_sol": x.flow.1, "first_buy_ms": x.flow.2, "first_buyer": x.flow.3.map(|w| b58(&w))},
            "rules": {"t4": v(4), "t5": v(5), "t8": v(8), "bh3": if x.top_pct >= BH_PCT { v(3) } else { serde_json::Value::Null }, "top_pct": r4(x.top_pct), "adv3": adv3,
                "hs1": x.hs1.map(|h| serde_json::json!([h.0, r4(h.1)]))},
            "exit": x.exit.map(|e| serde_json::json!({"why": e.0, "slot": e.1, "value": jv(e.2), "lag": x.sell.map(|s| s.0 as i64 - e.1 as i64)})),
            "stop": x.stop.map(|s| serde_json::json!({"slot": s.0, "v_trigger": jv(s.1), "v_next_slot": s.2.map(r4)})),
            "realized_est": x.closed.filter(|c| *c != i64::MIN)}));
    }

    // ---- status / end ---------------------------------------------------------------------------------------------------
    pub(super) fn status43(&self) -> String {
        let d = &self.d43;
        let mut s = String::new();
        if d.status_reads + d.deadman_exits + d.deadman_would + d.wall_would + d.stale_skips + d.stale_would > 0 {
            s += &format!(" | DIP43 blind: status reads {} opened {} dead-man {} (would {}) wall-would {} stale skips {} (would {})", d.status_reads, d.status_opened,
                d.deadman_exits, d.deadman_would, d.wall_would, d.stale_skips, d.stale_would);
        }
        if let Some(b) = d.book.as_ref() { s += &format!(" | BOOK {} tokens {} posts", b.tokens(), b.posts); }
        if self.cfg.c43.cascade { s += &format!(" | CASCADE fills {} G-A {} guards {}", d.casc_fills, d.casc_ga, d.casc_gd); }
        if self.cfg.c43.ml.is_some() { s += &format!(" | MINT-LEDGER {} mints, papers {}, would {} skips {}", d.ml.len(), d.ml_papers, d.ml_would, d.ml_skips); }
        if self.cfg.c43.acct { s += &format!(" | UNSEEN FEES {} tries {:.6} SOL", d.unseen.0, d.unseen.1 as f64 / 1e9); }
        if self.cfg.c43.fanout.is_some() { s += &format!(" | FANOUT {} mints, would {} skips {} disarms {}", d.fan.len(), d.fan_would, d.fan_skips, d.fan_disarms); }
        if self.cfg.c43.shadows { s += &format!(" | SH43 would_hold {} sticky {} armslot {} bh {}", d.leak_fills, d.sticky_fills, d.armslot_fills, d.bh_fills); }
        s
    }
    pub(super) fn finish43(&mut self) -> Option<serde_json::Value> {
        let shx: Vec<ShX> = self.d43.shx.drain().map(|x| x.1).collect();
        for x in shx { self.shx_rec43(x); }
        let d = &self.d43;
        let any = self.cfg.c43.any() || d.ctl_changes > 0 || d.status_reads + d.deadman_exits + d.deadman_would + d.wall_would + d.stale_skips + d.stale_would > 0;
        any.then(|| serde_json::json!({"status_reads": d.status_reads, "status_opened": d.status_opened, "deadman_exits": d.deadman_exits, "deadman_would": d.deadman_would,
            "wall_would": d.wall_would, "stale_skips": d.stale_skips, "stale_would": d.stale_would, "cascade": [d.casc_fills, d.casc_ga, d.casc_gd],
            "mint_ledger": {"mints": d.ml.len(), "papers": d.ml_papers, "would": d.ml_would, "skips": d.ml_skips}, "unseen": {"n": d.unseen.0, "fee_est": d.unseen.1},
            "fanout": {"mints": d.fan.len(), "would": d.fan_would, "skips": d.fan_skips, "disarms": d.fan_disarms},
            "shadows": {"would_hold": d.leak_fills, "would_hold_sticky": d.sticky_fills, "armslot": d.armslot_fills, "bh": d.bh_fills, "shadow_exits": d.shx_n}, "ctl_changes": d.ctl_changes, "ctl_errors": d.ctl_errors}))
    }
}

// ---- dipmode's watchdog driver ------------------------------------------------------------------------------------------------

/// one watchdog round (dipmode's loop, at most every 20 ms): the late tries (to the probe), the detectors, the episode's line / record /
/// alert, the probe's pause. Pure apart from the log and the alert
pub fn stall_round(w: &mut st::Watch, p: Option<&mut PsLive>, log: &DipLog, now_ns: u64) {
    let tpu = send::tpu::SLOT.load(Ordering::Relaxed);
    let mut p = p;
    if let Some(p) = p.as_ref() { w.cfg.live = p.stall_live43(); }
    let late = match p.as_ref() { Some(pp) => w.late(now_ns, &|s| pp.unresolved43(s)), None => Vec::new() };
    if let Some(pp) = p.as_mut() { for (s, t) in &late { pp.blind_try43(*s, *t); } }
    let Some(ev) = w.check(now_ns, tpu, !late.is_empty()) else { return };
    let (armed, open, inflight) = p.as_ref().map_or((0, 0, 0), |p| p.inflight43());
    match &ev {
        st::Ev::Start { kind, silent_ms, feed_slot, tpu_slot } => {
            eprintln!("FEED-STALL kind={} silent_ms={silent_ms} feed_slot={feed_slot} tpu_slot={tpu_slot} lag_slots={} armed={armed} open={open} tries_in_flight={inflight} mode={}",
                kind.s(), tpu_slot.saturating_sub(*feed_slot), if w.cfg.live { "live (sender paused)" } else { "log" });
            log.w(serde_json::json!({"ev": "presend_live_feed_stall", "phase": "start", "kind": kind.s(), "silent_ms": silent_ms, "feed_slot": feed_slot, "tpu_slot": tpu_slot,
                "lag_slots": tpu_slot.saturating_sub(*feed_slot), "armed": armed, "open": open, "tries_in_flight": inflight, "live": w.cfg.live, "late_tries": late.len(),
                "t": arbx::feeds::clock::now_ns()}));
            if open > 0 || inflight > 0 {
                tg::raise(arbx::alerts::Level::Critical, "dip_feed_stall", "stall", "🚨", "FEED-STALL: the executed feed is blind", arbx::alerts::format::Body::new()
                    .kv("kind", kind.s()).kv("open positions", open.to_string()).kv("tries in flight", inflight.to_string()).kv("mode", if w.cfg.live { "live (paused)" } else { "log" }), false);
            }
            if let Some(p) = p.as_mut() { p.stall43(true, now_ns); }
        }
        st::Ev::End { dur_ms, kinds, max_silent_ms, max_lag } => {
            eprintln!("FEED-STALL END dur_ms={dur_ms} kinds={} max_silent_ms={max_silent_ms} max_lag={max_lag}", kinds.join(","));
            log.w(serde_json::json!({"ev": "presend_live_feed_stall", "phase": "end", "dur_ms": dur_ms, "kinds": kinds, "max_silent_ms": max_silent_ms, "max_lag": max_lag,
                "t": arbx::feeds::clock::now_ns()}));
            if let Some(p) = p.as_mut() { p.stall43(false, now_ns); }
        }
    }
}

// ---- dip43c: the book's arm snapshot from getTokenLargestAccounts + getMultipleAccounts (the primary rpc) ---------------------------------
/// a largest-accounts read at an arm (--presend-live-tbal-src largest; answer: PsMsg::Largest)
#[derive(Clone, Debug)]
pub struct LargestReq { pub w: u64, pub mint: Pk, pub curve: Pk, pub at: Instant }
/// its answer: (context slot of the accounts read, (owner, token account, amount) per listed account) or the error
#[derive(Clone, Debug)]
pub struct LargestRes { pub req: LargestReq, pub read: std::result::Result<(u64, Vec<(Pk, Pk, u64)>), String>, pub ms: f64 }
/// reads in flight (each one its own task; a busy arm writes a record and is skipped, never queued)
pub static LARGEST_INFLIGHT: AtomicU64 = AtomicU64::new(0);
pub const LARGEST_MAX: u64 = 6;
pub const LARGEST_TIMEOUT: Duration = Duration::from_millis(2500);

/// the read: the mint's 20 largest token accounts, then their owner + amount in one getMultipleAccounts (closed ones: absent / null)
pub async fn largest_read(rpc: &rpc::Rpc, mint: &Pk) -> std::result::Result<(u64, Vec<(Pk, Pk, u64)>), String> {
    let run = async {
        let b = rpc::Bounds::fetch(LARGEST_TIMEOUT, 1);
        let v = rpc.call_bounded("getTokenLargestAccounts", serde_json::json!([b58(mint), {"commitment": "processed"}]), b).await.map_err(|e| rpc::scrub(&e.msg))?.value;
        let list = v["value"].as_array().ok_or("largest: no value list")?;
        let accs: Vec<String> = list.iter().filter_map(|a| a["address"].as_str().map(String::from)).collect();
        if accs.is_empty() { return Ok((v["context"]["slot"].as_u64().unwrap_or(0), vec![])); }
        let b = rpc::Bounds::fetch(LARGEST_TIMEOUT, 1);
        let m = rpc.call_bounded("getMultipleAccounts", serde_json::json!([accs, {"encoding": "base64", "commitment": "processed", "dataSlice": {"offset": 32, "length": 40}}]), b)
            .await.map_err(|e| rpc::scrub(&e.msg))?.value;
        let slot = m["context"]["slot"].as_u64().ok_or("multiple: no context slot")?;
        let vals = m["value"].as_array().ok_or("multiple: no value list")?;
        let mut out = Vec::with_capacity(vals.len());
        for (addr, x) in accs.iter().zip(vals) {
            let Some(acct) = bs58::decode(addr).into_vec().ok().and_then(|b| <[u8; 32]>::try_from(b.as_slice()).ok()) else { continue };
            if x.is_null() { continue; }   // closed between the two calls: its owner's post balance (closed = 0) covers it
            let Some(s) = x["data"][0].as_str() else { continue };
            let Ok(d) = base64::engine::general_purpose::STANDARD.decode(s) else { continue };
            if let Some((owner, amount)) = pslog35::acct_parse(&d, true) { out.push((owner, acct, amount)); }
        }
        Ok((slot, out))
    };
    match tokio::time::timeout(LARGEST_TIMEOUT, run).await { Ok(r) => r, Err(_) => Err(format!("timeout {} ms", LARGEST_TIMEOUT.as_millis())) }
}

impl PsLive {
    /// dip43c: an arm (T2 or re-arm) asks for the largest-accounts read (nothing unless --presend-live-tbal-src largest)
    pub(super) fn largest_arm(&mut self, w: u64, mint: Pk) {
        if !self.cfg.c43.tbal_largest || self.d43.book.is_none() { return; }
        if LARGEST_INFLIGHT.load(Ordering::SeqCst) >= LARGEST_MAX {
            self.rec(serde_json::json!({"ev": "presend_live_tbal_snap", "w": w, "mint": b58(&mint), "err": "busy"}));
            return;
        }
        let curve = self.launches.get(&mint).map_or([0u8; 32], |l| l.bonding_curve);
        self.exec(Cmd::Largest(Box::new(LargestReq { w, mint, curve, at: Instant::now() })));
    }
    /// dip43c: the answer -> a partial snapshot into the book, then the armed window's floors / cascade set at once
    pub(super) fn largest_done(&mut self, r: LargestRes) {
        let q = &r.req;
        let mut rec = serde_json::json!({"ev": "presend_live_tbal_snap", "w": q.w, "mint": b58(&q.mint), "ms": (r.ms * 10.0).round() / 10.0});
        match &r.read {
            Err(e) => { rec["err"] = e.clone().into(); }
            Ok((slot, hold)) => {
                rec["slot"] = (*slot).into();
                rec["n"] = hold.len().into();
                if let Some(b) = self.d43.book.as_mut() { b.snapshot_top(q.mint, q.curve, hold, *slot, arbx::fast::mono_ns()); }
                if self.cfg.c43.cascade { if let Some(&id) = self.armed.get(&q.mint) { self.wset43(id, &q.mint); } }
                self.g43_refresh(&q.mint);
            }
        }
        self.rec(rec);
    }
}

// =====================================================================================================================
// dip46 (owner 11-11: "make our paper / filter numbers trustworthy"): PROBE TRIES + FILTER A/B. Both DEFAULT OFF: with none of the
// flags below nothing here runs and the engine writes dip43g's records byte for byte (dip46_tests: the golden digest).
//
// A) PROBE TRIES (--presend-live-probe on): when a LIVE filter blocks a trigger (arm-time skip) or withholds a window's send
//    (send-time), the sender builds the SAME try it would have sent (route mix, CU limit / price / fee tier, the 0.88x limit's state,
//    the guard: deadline + band (+ floors when the window has them)) but signs the pump buy with min_tokens_out = u64::MAX: the buy can
//    never fill (pump: tokens out < min -> the slippage error; any other path through the buy fails too: no curve holds u64::MAX tokens)
//    and the whole tx reverts (no ATA, no tip). Rate: one probe per window per slot, <= --presend-live-probe-max-per-sec N (default 5)
//    globally, and the real path / global rate tokens are taken as the real try would (never more than the tries they replace).
//      * arm-time: a T2 trigger skipped by a probe kind gets a PROBE WINDOW (its own id space, PW0 + n; never in `armed`, never a
//        position): one try per slot from the real window's start to its end slot (or 30 ms after the whale sells).
//      * send-time: a real window's try withheld by FP-NOBOT / skip2 / the per-send blocklist / bot depth -> that try as a probe.
//    Records: presend_live_probe_arm / presend_live_probe (each send) / presend_live_probe_land (each landing or "unseen": result, slot,
//    idx, the curve just before it (`pre`) and would_fill = the real try's min_out met at that state) / presend_live_probe_end.
//    Probes are OUT OF: the fills, the position book, P&L, the failed-fee budget and its pause, the breaker, the per-path / per-client
//    counts, the window accounting (A8), the landing stats; their fees are counted apart (probe_fees).
// B) FILTER A/B (--presend-live-filter-ab LIST; the control file's "ab46" object switches each filter hot): an A/B'd arm-time filter
//    is bypassed on ODD T2 triggers (the A/B's own trigger count; even: the filter acts as today) and logged "would"; an A/B'd send-time
//    filter (botdepth, fpnb, blocklist_send) and holder_floors are bypassed on ODD window ids. Records presend_live_filter_ab {w, filter,
//    arm: bypass | live, would_block} (arm-time: every trigger the filter would block; send-time: the window's first would-block);
//    presend_live_arm / presend_live_fill get "ab46" {arm per A/B'd filter, would: the bypassed filters that would have blocked} so the
//    realized P&L splits by arm (join presend_live_realized on w). holder_floors: odd windows carry snipe-guard deadline + band, no floors.
// =====================================================================================================================
use super::*;

pub const FLAG_PROBE: &str = "--presend-live-probe";
pub const FLAG_RATE: &str = "--presend-live-probe-max-per-sec";
pub const FLAG_KINDS: &str = "--presend-live-probe-kinds";
pub const FLAG_MAXWIN: &str = "--presend-live-probe-max-windows";
pub const FLAG_AB: &str = "--presend-live-filter-ab";
/// every dip46 flag (each needs --presend-live)
pub const P46FLAGS: [&str; 5] = ["--presend-live-probe", "--presend-live-probe-max-per-sec", "--presend-live-probe-kinds", "--presend-live-probe-max-windows",
    "--presend-live-filter-ab"];

/// the probe's min_tokens_out: no bonding curve holds u64::MAX tokens, so pump's buy can never meet it (the try fails, nothing is bought)
pub const PROBE_MIN_OUT: u64 = u64::MAX;
/// probe windows' ids start here (never a real window's id: those count from 1)
pub const PW0: u64 = 1 << 40;

/// the probe kinds (bit i = KINDS[i]): arm-time skip reasons, then "s1" (any s1_* skip), "breaker" (opt-in only), then the send-time ones
pub const KINDS: [&str; 19] = ["create_slot", "young_age", "quiet", "quiet3_a", "lone_whale", "cr_loss", "cr_unfollowed", "wh_loss", "holder_loss", "blocklist",
    "m2_unseen", "mint_ledger", "fanout", "s1", "breaker", "fpnb", "skip2", "blocklist_send", "botdepth"];
const K_BREAKER: u32 = 1 << 14;
/// "all" = every kind but the breaker's pause
pub const KINDS_ALL: u32 = ((1u32 << KINDS.len()) - 1) & !K_BREAKER;
/// the send-time kinds' bits
const K_SEND: u32 = (1 << 15) | (1 << 16) | (1 << 17) | (1 << 18);

/// a skip / withhold reason's probe kind (None: not a filter: stopped, blocked_*, a launch refusal, ...)
pub fn kind_of(why: &str) -> Option<&'static str> {
    match why {
        "fpnb_withheld" | "fpnb_withheld_stale" => Some("fpnb"),
        "skip2_withheld" | "skip2_withheld_stale" => Some("skip2"),
        "blocklist_withheld" => Some("blocklist_send"),
        "botdepth_withheld" => Some("botdepth"),
        w if w.starts_with("s1_") => Some("s1"),
        w => KINDS[..15].iter().find(|k| **k == w && **k != "s1").copied(),
    }
}
pub fn kind_bit(k: &str) -> u32 { KINDS.iter().position(|x| *x == k).map_or(0, |i| 1 << i) }

pub fn kinds_parse(s: &str) -> Result<u32> {
    let mut m = 0u32;
    for k in s.split(',').map(str::trim).filter(|k| !k.is_empty()) {
        if k == "all" { m |= KINDS_ALL; continue; }
        let b = kind_bit(k);
        if b == 0 { bail!("{FLAG_KINDS}: unknown kind '{k}' (all | {})", KINDS.join(" | ")); }
        m |= b;
    }
    if m == 0 { bail!("{FLAG_KINDS}: empty list"); }
    Ok(m)
}
pub fn kinds_str(m: u32) -> String { if m == KINDS_ALL { return "all".into(); } KINDS.iter().enumerate().filter(|(i, _)| m & (1 << i) != 0).map(|(_, k)| *k).collect::<Vec<_>>().join(",") }

/// the A/B'able filters (bit i = AB_NAMES[i])
pub const AB_NAMES: [&str; 13] = ["holder_floors", "young_age", "create_slot", "botdepth", "quiet", "quiet3a", "lone_whale", "cr_loss", "blocklist", "wh_loss",
    "holder_loss", "fpnb", "blocklist_send"];
pub const AB_FLOORS: u32 = 1 << 0;
pub const AB_YOUNG: u32 = 1 << 1;
pub const AB_CREATE: u32 = 1 << 2;
pub const AB_BD: u32 = 1 << 3;
pub const AB_QUIET: u32 = 1 << 4;
pub const AB_Q3A: u32 = 1 << 5;
pub const AB_LONE: u32 = 1 << 6;
pub const AB_CR: u32 = 1 << 7;
pub const AB_BL: u32 = 1 << 8;
pub const AB_WH: u32 = 1 << 9;
pub const AB_HL: u32 = 1 << 10;
pub const AB_FPNB: u32 = 1 << 11;
pub const AB_BLS: u32 = 1 << 12;
/// the arm-time filters (parity = the A/B's T2 trigger count)
pub const AB_ARM: u32 = AB_YOUNG | AB_CREATE | AB_QUIET | AB_Q3A | AB_LONE | AB_CR | AB_BL | AB_WH | AB_HL;
pub fn ab_bit(k: &str) -> u32 { AB_NAMES.iter().position(|x| *x == k).map_or(0, |i| 1 << i) }
pub fn ab_names(m: u32) -> Vec<&'static str> { AB_NAMES.iter().enumerate().filter(|(i, _)| m & (1 << i) != 0).map(|(_, k)| *k).collect() }
pub fn ab_parse(s: &str) -> Result<u32> {
    let mut m = 0u32;
    for k in s.split(',').map(str::trim).filter(|k| !k.is_empty()) {
        if k == "none" { continue; }
        let b = ab_bit(k);
        if b == 0 { bail!("{FLAG_AB}: unknown filter '{k}' (none | {})", AB_NAMES.join(" | ")); }
        m |= b;
    }
    Ok(m)
}
/// the arm-time A/B filter of a skip reason / a would43 name (cr_unfollowed is the creator gate's too)
pub fn ab_of_why(why: &str) -> u32 {
    match why {
        "young_age" => AB_YOUNG, "create_slot" => AB_CREATE, "quiet" => AB_QUIET, "quiet3_a" => AB_Q3A, "lone_whale" => AB_LONE,
        "cr_loss" | "cr_unfollowed" => AB_CR, "blocklist" => AB_BL, "wh_loss" => AB_WH, "holder_loss" => AB_HL, _ => 0,
    }
}

/// dip46's flags (Default = all off: dip43g)
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Cfg46 {
    pub probe: bool,
    pub rate: u32,
    pub kinds: u32,
    pub max_wins: usize,
    /// --presend-live-filter-ab given (the control file's "ab46" is read only then)
    pub ab_flag: bool,
    /// the start A/B set
    pub ab: u32,
}
impl Cfg46 {
    pub fn parse(argv: &[String]) -> Result<Cfg46> {
        let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
        let arg = |f: &str| argv.iter().position(|x| x == f).and_then(|i| argv.get(i + 1)).cloned();
        for f in P46FLAGS { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        let probe = match arg(FLAG_PROBE).as_deref() { None | Some("off") => false, Some("on") => true, Some(x) => bail!("{FLAG_PROBE} {x}: on | off") };
        if !probe { if let Some(f) = [FLAG_RATE, FLAG_KINDS, FLAG_MAXWIN].iter().find(|f| has(f)) { bail!("{f} needs {FLAG_PROBE} on"); } }
        let rate = match arg(FLAG_RATE) { None => 5, Some(s) => s.parse::<u32>().ok().filter(|r| (1..=50).contains(r)).with_context(|| format!("{FLAG_RATE} {s}: 1..50 probes per second"))? };
        let kinds = match arg(FLAG_KINDS) { None => KINDS_ALL, Some(s) => kinds_parse(&s)? };
        let max_wins = match arg(FLAG_MAXWIN) { None => 8, Some(s) => s.parse::<usize>().ok().filter(|r| (1..=64).contains(r)).with_context(|| format!("{FLAG_MAXWIN} {s}: 1..64 probe windows at once"))? };
        let (ab_flag, ab) = match arg(FLAG_AB) { None => (false, 0), Some(s) => (true, ab_parse(&s)?) };
        Ok(Cfg46 { probe, rate, kinds, max_wins, ab_flag, ab })
    }
    pub fn any(&self) -> bool { self.probe || self.ab_flag }
    pub fn json(&self) -> serde_json::Value {
        let mut j = serde_json::json!({});
        if self.probe { j["probe"] = serde_json::json!({"max_per_sec": self.rate, "kinds": kinds_str(self.kinds), "max_windows": self.max_wins, "min_out": PROBE_MIN_OUT}); }
        if self.ab_flag { j["filter_ab"] = ab_names(self.ab).into(); }
        j
    }
}

/// the A/B'd filters whose feature is on (an A/B of a filter that never acts is refused at start, ignored by the control key)
pub fn ab_avail(c: &Cfg) -> u32 {
    let mut m = 0u32;
    if c.g43.as_ref().is_some_and(|g| g.mode == ps43_guard::Mode::Holders && !g.ab) { m |= AB_FLOORS; }
    if c.min_age_slots > 0 { m |= AB_YOUNG; }
    if !c.create_slot { m |= AB_CREATE; }
    if c.bd.is_some() { m |= AB_BD; }
    if c.quiet.skip { m |= AB_QUIET; }
    if c.q3a_live { m |= AB_Q3A; }
    if c.lone_whale_slots > 0 { m |= AB_LONE; }
    if c.cr_on() { m |= AB_CR; }
    if c.blocklist.is_some() { m |= AB_BL; }
    if c.wh_on() { m |= AB_WH; }
    if c.hl_on() { m |= AB_HL; }
    if c.fpnb_log { m |= AB_FPNB; }
    if c.blocklist_send { m |= AB_BLS; }
    m
}

/// refused at start: an A/B of a filter that is off (holder_floors: needs --presend-live-guard holders and no --presend-live-guard-ab)
pub fn check(c: &Cfg) -> Result<()> {
    let bad = c.p46.ab & !ab_avail(c);
    if bad != 0 {
        bail!("{FLAG_AB}: {} not on in this run (holder_floors needs --presend-live-guard holders without --presend-live-guard-ab; each other filter its own flag)",
            ab_names(bad).join(", "));
    }
    Ok(())
}

/// the sender <-> main loop state (idle without the flags)
#[derive(Default)]
pub struct Sh46 {
    /// probes on (the start flag; the control file's "probe46" switches it)
    pub probe: AtomicBool,
    /// the A/B'd filters now (bits AB_*)
    pub ab: std::sync::atomic::AtomicU32,
    pub sent: AtomicU64,
    pub dry: AtomicU64,
    /// probes not built / not sent, why (the probe's own map: never the real tries' not-sent counts)
    pub refused: Mutex<FxHashMap<&'static str, u64>>,
    /// probes sent per kind
    pub by_kind: Mutex<FxHashMap<&'static str, u64>>,
    /// A/B: sends that went out bypassing a filter, per filter
    pub ab_bypassed: Mutex<FxHashMap<&'static str, u64>>,
}
pub fn refused(sh: &Sh46, why: &'static str) { *sh.refused.lock().unwrap().entry(why).or_default() += 1; }

/// the sender's own probe / A/B state
pub struct Send46 { bucket: send::TokenBucket, last: FxHashMap<u64, u64>, abrec: FxHashSet<(u64, u32)>, kinds: u32 }
impl Send46 {
    pub fn new(c: &Cfg46) -> Send46 { Send46 { bucket: send::TokenBucket::new(c.rate.max(1) as f64, 1), last: FxHashMap::default(), abrec: FxHashSet::default(), kinds: c.kinds } }
    /// probe this blocked try now? (probes on, its kind listed, the window's first probe in this slot, a global token)
    pub fn want(&mut self, sh: &Sh46, why: &'static str, w: u64, slot: u64, now: u64) -> Option<&'static str> {
        if !sh.probe.load(Ordering::Relaxed) { return None; }
        let k = kind_of(why)?;
        if self.kinds & kind_bit(k) == 0 { return None; }
        if self.last.get(&w) == Some(&slot) { return None; }
        if !self.bucket.try_take(now) { refused(sh, "probe_rate"); return None; }
        if self.last.len() > 4096 { self.last.retain(|_, s| *s + 64 >= slot); }
        self.last.insert(w, slot);
        Some(why)
    }
    /// an arm-time probe window's try: the window's first in this slot and a global token
    pub fn want_win(&mut self, sh: &Sh46, w: u64, slot: u64, now: u64) -> bool {
        if !sh.probe.load(Ordering::Relaxed) { refused(sh, "probe_off"); return false; }
        if self.last.get(&w) == Some(&slot) { return false; }
        if !self.bucket.try_take(now) { refused(sh, "probe_rate"); return false; }
        self.last.insert(w, slot);
        true
    }
    /// A/B: is filter `bit` bypassed for window `w` (odd ids)?
    #[inline]
    pub fn bypass(sh: &Sh46, bit: u32, w: u64) -> bool { sh.ab.load(Ordering::Relaxed) & bit != 0 && w % 2 == 1 }
    /// A/B: the window's first would-block of `bit` (one presend_live_filter_ab record per window and filter)
    pub fn ab_rec(&mut self, out: &crossbeam_channel::Sender<Out>, sh: &Sh46, bit: u32, w: &SWin, slot: u64, bypass: bool) {
        if sh.ab.load(Ordering::Relaxed) & bit == 0 { return; }
        if bypass { *sh.ab_bypassed.lock().unwrap().entry(ab_names(bit)[0]).or_default() += 1; }
        if self.abrec.len() > 8192 { self.abrec.clear(); }
        if !self.abrec.insert((w.id, bit)) { return; }
        let _ = out.send(Out::Rec(serde_json::json!({"ev": "presend_live_filter_ab", "w": w.id, "mint": b58(&w.mint), "filter": ab_names(bit)[0],
            "arm": if bypass { "bypass" } else { "live" }, "would_block": true, "kind": if w.rearm { "rearm" } else { "T2" }, "slot": slot, "t": arbx::feeds::clock::now_ns()})));
    }
    pub fn kinds_send(&self) -> bool { self.kinds & K_SEND != 0 }
}

/// what a try carries for dip46 (Default: a real try, nothing bypassed)
#[derive(Clone, Copy, Debug, Default)]
pub struct X46 {
    /// Some(the blocking filter): a PROBE (min_out = PROBE_MIN_OUT; never a fill)
    pub probe: Option<&'static str>,
    /// A/B: the filters this real try bypassed (each would have withheld it)
    pub ab: u32,
    /// the window's spend / fee rate / curve at signing (the probe landing's would-fill check)
    pub spend: u64, pub fr: f64, pub sv: u64, pub st: u64,
    /// a probe's REAL min_out (the 0.88x limit's tokens of the try it stands for)
    pub min: u64,
}

/// an arm-time probe window (main loop)
#[derive(Clone, Debug)]
pub struct PWin { pub mint: Pk, pub whale: Pk, pub en_slot: u64, pub why: &'static str, pub trig_slot: u64, pub sent: u32, pub stop_at: Option<Instant> }

/// a probe's landing waiting for its record
pub struct PLand { pub att: Att, pub res: String, pub err: String, pub fee: u64, pub slot: u64, pub idx: Option<u64>, pub t_rx: u64, pub at: Instant }

#[derive(Default, Debug, Clone)]
pub struct KindSt { pub sent: u64, pub landed: u64, pub unseen: u64, pub fees: u64, pub would_fill: u64, pub would_miss: u64, pub unknown: u64 }

/// the main loop's dip46 state (PsLive::p46; idle without the flags)
#[derive(Default)]
pub struct P46 {
    pub nw: u64,
    pub wins: FxHashMap<u64, PWin>,
    pub by_mint: FxHashMap<Pk, u64>,
    pub atts: FxHashMap<[u8; 64], (Att, bool)>,
    pub order: VecDeque<(u64, [u8; 64], Instant)>,
    pub lands: Vec<PLand>,
    /// per mint: its trades (slot, idx, j, vsol, vtok) while a probe can land on it (the would-fill state just before a landing)
    pub tape: FxHashMap<Pk, VecDeque<(u64, u32, i32, u64, u64)>>,
    /// mints with a probe in flight / waiting for its record: the last slot it matters
    pub keep: FxHashMap<Pk, u64>,
    pub windows: u64, pub win_refused: FxHashMap<&'static str, u64>,
    pub fees: u64, pub landed: u64, pub unseen: u64,
    pub res: std::collections::BTreeMap<String, u64>,
    pub by_kind: std::collections::BTreeMap<&'static str, KindSt>,
    /// a probe seen as a BUY of ours (impossible by construction): counted loudly, the tokens handed to the orphan path
    pub impossible: u64,
    /// A/B: T2 triggers counted (parity), the trigger under decision's arm (Some(bypass)), each armed window's tag, counts per filter
    /// [live would-block, bypass would-block, bypassed windows armed]
    pub ab_n: u64,
    pub ab_cur: Option<bool>,
    pub ab_wins: FxHashMap<u64, (serde_json::Value, u32)>,
    pub ab_st: std::collections::BTreeMap<&'static str, [u64; 3]>,
    pub ctl: Option<(String, Option<std::time::SystemTime>, Instant)>,
    pub ctl_changes: u64,
}
impl P46 {
    pub fn active(&self) -> bool { !self.atts.is_empty() || !self.wins.is_empty() || !self.lands.is_empty() }
}

const PROBE_TAPE: usize = 96;

impl PsLive {
    #[inline]
    pub(super) fn p46_on(&self) -> bool { self.cfg.p46.any() }

    /// start: the modes, the control file (a record only when on)
    pub(super) fn p46_start(&mut self) {
        if !self.p46_on() { return; }
        self.sh.p46.probe.store(self.cfg.p46.probe, Ordering::SeqCst);
        self.sh.p46.ab.store(self.cfg.p46.ab, Ordering::SeqCst);
        if let Some(p) = self.cfg.ledger_ctl.clone() { self.p46.ctl = Some((p, None, Instant::now())); self.p46_ctl_check(true); }
        self.rec(serde_json::json!({"ev": "presend_live_dip46", "cfg": self.cfg.p46.json(), "ab_now": ab_names(self.sh.p46.ab.load(Ordering::SeqCst)),
            "probe_now": self.sh.p46.probe.load(Ordering::SeqCst), "t": arbx::feeds::clock::now_ns()}));
    }

    /// the banner lines
    pub fn banner46(c: &Cfg) -> Vec<String> {
        let mut v = Vec::new();
        v.push(if c.p46.probe { format!("DIP46 PROBE TRIES ON: a try a live filter blocks is sent as a probe that can never fill (min_out = u64::MAX); kinds {}, <= {}/s, one per window per slot, \
            <= {} probe windows at once; probe fees counted apart (never the fee budget)", kinds_str(c.p46.kinds), c.p46.rate, c.p46.max_wins) } else { "DIP46 PROBE TRIES off".into() });
        v.push(if c.p46.ab_flag { format!("DIP46 FILTER A/B ON: {} (odd T2 triggers / odd windows bypass the filter, even ones as today; control key \"ab46\")",
            if c.p46.ab == 0 { "no filter yet".to_string() } else { ab_names(c.p46.ab).join(", ") }) } else { "DIP46 FILTER A/B off".into() });
        v
    }

    // ---- registration / landing ----------------------------------------------------------------------------------------
    /// a probe the sender registered (drain_atts): its own book, nothing of the real tries' counts
    pub(super) fn p46_reg(&mut self, a: Att) {
        let k = a.x46.probe.and_then(kind_of).unwrap_or("?");
        self.p46.by_kind.entry(k).or_default().sent += 1;
        if let Some(w) = self.p46.wins.get_mut(&a.w) { w.sent += 1; }
        let e = self.p46.keep.entry(a.mint).or_default(); *e = (*e).max(a.deadline + 8);
        self.p46.tape.entry(a.mint).or_default();
        self.p46.order.push_back((a.deadline, a.sig, Instant::now()));
        if self.p46.atts.len() > 20_000 { let lo = a.slot.saturating_sub(300); self.p46.atts.retain(|_, (x, d)| !*d || x.deadline > lo); }
        self.p46.atts.insert(a.sig, (a, false));
    }

    /// our failed tx: a probe's landing? (true: handled, the caller returns)
    pub(super) fn p46_arrival(&mut self, a: &arbx::feeds::Arrival) -> bool {
        let Some((att, done)) = self.p46.atts.get_mut(&a.tx.sig) else { return false };
        if *done { return true; }
        *done = true;
        let att = att.clone();
        let of = arbx::feeds::own_fail_take(&a.tx.sig);
        let ff = att.fa.as_ref().map_or_else(|| ps43_b::tier_fail_fee(&att.sig).unwrap_or_else(|| self.cfg.fail_fee()), |f| f.fail_fee());
        let (idx, fee, err) = match &of { Some(f) => (Some(f.index), f.fee, f.err.clone()), None => (None, ff, "?".to_string()) };
        let res = if of.is_some() { pl::classify(&err, &att.roles) } else { "failed_unknown".to_string() };
        let (res, _) = ps43_guard::reclassify_sg(self.cfg.g43.as_ref(), att.w, ps43_guard::sg_l_has(&att.sig), res, &err);
        self.p46.fees += fee;
        self.p46.landed += 1;
        let k = att.x46.probe.and_then(kind_of).unwrap_or("?");
        let ks = self.p46.by_kind.entry(k).or_default(); ks.landed += 1; ks.fees += fee;
        *self.p46.res.entry(res.clone()).or_default() += 1;
        let e = self.p46.keep.entry(att.mint).or_default(); *e = (*e).max(a.slot + 4);
        self.p46.lands.push(PLand { att, res, err, fee, slot: a.slot, idx, t_rx: a.t_rx, at: Instant::now() });
        true
    }

    /// a BUY of ours whose signature is a probe's: impossible by construction (min_out = u64::MAX). Never booked as a fill; counted, a
    /// critical line and record, the tokens to the orphan path (sold as an unexpected holding)
    pub(super) fn p46_impossible_fill(&mut self, t: &pl::Trade) -> bool {
        let Some((att, _)) = self.p46.atts.get(&t.sig) else { return false };
        let w = att.w;
        self.p46.impossible += 1;
        self.rec(serde_json::json!({"ev": "presend_live_probe_filled", "w": w, "mint": b58(&t.mint), "sig": bs58::encode(&t.sig).into_string(), "tokens": t.tok, "sol": t.sol,
            "slot": t.s, "t": t.t_rx}));
        self.line(format!("  PRESEND LIVE PROBE FILLED?! w{w} {} {} tokens: IMPOSSIBLE (min_out u64::MAX): sold as an orphan", b58(&t.mint), t.tok));
        self.orphan(t.mint, t.tok, t.s, w, "probe46");
        true
    }

    /// every trade (on_exec): the probe mints' tapes, the probe windows' curve state
    pub(super) fn p46_trade(&mut self, t: &pl::Trade) {
        if !self.p46.tape.is_empty() || self.armed.contains_key(&t.mint) {
            if let Some(tp) = self.p46.tape.get_mut(&t.mint) {
                tp.push_back((t.s, t.i, t.j, t.vsol, t.vtok));
                if tp.len() > PROBE_TAPE { tp.pop_front(); }
            } else if self.sh.p46.probe.load(Ordering::Relaxed) && self.armed.contains_key(&t.mint) {
                // a real window's mint: a send-time probe may land on it
                let mut d = VecDeque::new(); d.push_back((t.s, t.i, t.j, t.vsol, t.vtok)); self.p46.tape.insert(t.mint, d);
            }
        }
        if let Some(&id) = self.p46.by_mint.get(&t.mint) {
            let hs = self.g43_set(&t.mint);
            let mut g = self.sh.wins.lock().unwrap();
            if let Some(w) = g.iter_mut().find(|w| w.id == id) { w.vsol = t.vsol; w.vtok = t.vtok; w.fr = t.fr(); w.pos = t.pos(); w.g43 = hs; }
        }
    }

    /// the whale's sell / the token gone: the probe window stops as a real one would (30 ms later / at once)
    pub(super) fn p46_whale_sell(&mut self, mint: &Pk, whale: &Pk) {
        let Some(&id) = self.p46.by_mint.get(mint) else { return };
        let Some(w) = self.p46.wins.get_mut(&id) else { return };
        if w.whale != *whale || w.stop_at.is_some() { return; }
        w.stop_at = Some(Instant::now() + Duration::from_millis(WHALE_SELL_MS));
        let stop_ns = arbx::fast::mono_ns() + WHALE_SELL_MS * 1_000_000;
        let mut g = self.sh.wins.lock().unwrap();
        if let Some(s) = g.iter_mut().find(|s| s.id == id) { s.stop_ns = s.stop_ns.min(stop_ns); }
    }
    pub(super) fn p46_end_mint(&mut self, mint: &Pk, why: &'static str) {
        if let Some(&id) = self.p46.by_mint.get(mint) { self.p46_end(id, why); }
    }
    fn p46_end(&mut self, id: u64, why: &'static str) {
        let Some(w) = self.p46.wins.remove(&id) else { return };
        if self.p46.by_mint.get(&w.mint) == Some(&id) { self.p46.by_mint.remove(&w.mint); }
        { let mut g = self.sh.wins.lock().unwrap(); g.retain(|x| x.id != id); }
        let e = self.p46.keep.entry(w.mint).or_default(); *e = (*e).max(self.sh.cur_slot() + self.cfg.deadline_slots + 4);
        self.rec(serde_json::json!({"ev": "presend_live_probe_end", "w": id, "mint": b58(&w.mint), "why": why, "filter": w.why, "sent": w.sent, "trig_slot": w.trig_slot,
            "en_slot": w.en_slot, "slot": self.sh.cur_slot(), "t": arbx::feeds::clock::now_ns()}));
    }

    /// a T2 trigger skipped by `why` (arm-time): a PROBE WINDOW when the kind is listed and the try could be built (launch accounts,
    /// nothing of ours on the mint, not stopped); none of the real window's books
    #[allow(clippy::too_many_arguments)]
    pub(super) fn p46_skip(&mut self, why: &'static str, t: &pl::Trade, whale: Pk, launch: Option<&Launch>, spend: u64, trig: &serde_json::Value) {
        if !self.cfg.p46.probe || !self.sh.p46.probe.load(Ordering::Relaxed) { return; }
        let Some(k) = kind_of(why) else { return };
        if self.cfg.p46.kinds & kind_bit(k) == 0 || K_SEND & kind_bit(k) != 0 { return; }
        let refuse = if self.stopped.is_some() || DIP_NO_FIRE.load(Ordering::Relaxed) { Some("stopped") }
            else if self.p46.by_mint.contains_key(&t.mint) { Some("probe_window_on_mint") }
            else if self.armed.contains_key(&t.mint) || self.pos.contains_key(&t.mint) || self.atas.contains_key(&t.mint) { Some("ours_on_mint") }
            else if self.p46.wins.len() >= self.cfg.p46.max_wins { Some("max_windows") }
            else { psrearm::launch_refusal(launch, self.allow_holder) };
        if let Some(r) = refuse { *self.p46.win_refused.entry(r).or_default() += 1; return; }
        let launch = launch.cloned().expect("checked");
        self.p46.nw += 1;
        let id = PW0 + self.p46.nw;
        let en_slot = ((t.a() + self.cfg.live_ms + self.cfg.window_slots as f64 * pl::SMS) / pl::SMS).floor() as u64;
        let st_ns = arbx::fast::mono_ns() + (self.cfg.b43.start_ms.unwrap_or(self.cfg.live_ms) * 1e6) as u64;
        let slot_ns = arbx::feeds::entries::SLOT_US.load(Ordering::Relaxed) * 1_000;
        let sw = SWin { id, mint: t.mint, launch, st_ns, stop_ns: u64::MAX, en_slot, vsol: t.vsol, vtok: t.vtok, fr: t.fr(), pos: t.pos(), pace: pl::Pace::new(st_ns, 1, slot_ns),
            n: 0, done: false, spend, rearm: false, ob6: ob6_pct(&self.det, self.cfg.ann || self.cfg.deep_drop > 0.0, &t.mint, &whale, &self.user), grd: Grd::default(),
            fpg: None, fab: None, blk: None, bd: None, g43: self.g43_set(&t.mint), p46: Some(why) };
        self.sh.wins.lock().unwrap().push(sw);
        self.p46.wins.insert(id, PWin { mint: t.mint, whale, en_slot, why, trig_slot: t.s, sent: 0, stop_at: None });
        self.p46.by_mint.insert(t.mint, id);
        self.p46.windows += 1;
        let mut d = VecDeque::new(); d.push_back((t.s, t.i, t.j, t.vsol, t.vtok));
        self.p46.tape.insert(t.mint, d);
        let e = self.p46.keep.entry(t.mint).or_default(); *e = (*e).max(en_slot + self.cfg.deadline_slots + 4);
        self.rec(serde_json::json!({"ev": "presend_live_probe_arm", "w": id, "mint": b58(&t.mint), "filter": why, "kind": "T2", "trig": trig, "en_slot": en_slot, "spend": spend,
            "drop": self.cfg.drop, "lim0": t.p() * (1.0 - self.cfg.drop), "t": arbx::feeds::clock::now_ns()}));
    }

    /// a real window armed on `mint`: its probe window ends (the real tries take over)
    pub(super) fn p46_real_arm(&mut self, mint: &Pk) { if !self.p46.by_mint.is_empty() { self.p46_end_mint(mint, "superseded"); } }

    // ---- the clock -------------------------------------------------------------------------------------------------------
    pub(super) fn p46_tick(&mut self, slot_now: u64) {
        if self.p46.ctl.is_some() { self.p46_ctl_check(false); }
        if !self.p46.active() && self.p46.tape.is_empty() { return; }
        let now = Instant::now();
        let ends: Vec<(u64, &'static str)> = self.p46.wins.iter()
            .filter_map(|(id, w)| if slot_now > w.en_slot { Some((*id, "expired")) } else if w.stop_at.is_some_and(|t| now >= t) { Some((*id, "whale_sold")) } else { None }).collect();
        for (id, why) in ends { self.p46_end(id, why); }
        if self.stopped.is_some() { let ids: Vec<u64> = self.p46.wins.keys().copied().collect(); for id in ids { self.p46_end(id, "stopped"); } }
        while let Some(&(dl, sig, at)) = self.p46.order.front() {
            if !(slot_now > dl + 3 || at.elapsed() > Duration::from_secs(6)) { break; }
            self.p46.order.pop_front();
            let Some((att, done)) = self.p46.atts.get_mut(&sig) else { continue };
            if *done { continue; }
            *done = true;
            let att = att.clone();
            self.p46.unseen += 1;
            self.p46.by_kind.entry(att.x46.probe.and_then(kind_of).unwrap_or("?")).or_default().unseen += 1;
            *self.p46.res.entry("unseen".into()).or_default() += 1;
            self.p46.lands.push(PLand { att, res: "unseen".into(), err: String::new(), fee: 0, slot: 0, idx: None, t_rx: 0, at: now });
        }
        if !self.p46.lands.is_empty() {
            let mut keep = Vec::new();
            for l in std::mem::take(&mut self.p46.lands) {
                if l.res == "unseen" || slot_now >= l.slot + 2 || l.at.elapsed() > Duration::from_secs(2) { let r = self.p46_land_rec(&l); self.rec(r); } else { keep.push(l); }
            }
            self.p46.lands = keep;
        }
        // the tapes of mints no probe can land on any more
        if slot_now % 4 == 0 {
            let (keep, armed, by) = (&mut self.p46.keep, &self.armed, &self.p46.by_mint);
            keep.retain(|m, s| *s >= slot_now || by.contains_key(m));
            let keep = &self.p46.keep;
            self.p46.tape.retain(|m, _| keep.contains_key(m) || armed.contains_key(m) || by.contains_key(m));
            if self.p46.atts.len() > 2048 { self.p46.atts.retain(|_, (a, d)| !*d || a.deadline + 300 > slot_now); }
        }
    }

    /// a probe's landing record: where it landed, the curve just before it (the feed's tape of the mint), would the real try have filled
    fn p46_land_rec(&mut self, l: &PLand) -> serde_json::Value {
        let a = &l.att;
        let filter = a.x46.probe.unwrap_or("?");
        let mut j = serde_json::json!({"ev": "presend_live_probe_land", "w": a.w, "n": a.n, "mint": b58(&a.mint), "sig": bs58::encode(&a.sig).into_string(), "filter": filter,
            "kind": if a.w >= PW0 || !self.rearm_w(a.w) { "T2" } else { "rearm" }, "path": a.path, "client": a.client, "res": l.res, "err": l.err, "fee": l.fee,
            "send_slot": a.slot, "deadline": a.deadline, "t_send": a.t_send, "would_limit": a.lim, "would_min_out": a.min_out_real(), "spend": a.x46.spend,
            "sign": [a.x46.sv, a.x46.st]});
        if let Some((s, ms)) = pl::ack_of(a.tag) { j["ack"] = s.into(); j["ack_ms"] = ms.into(); }
        if matches!(l.res.as_str(), "deadline" | "guard_abort" | "guard_other") {
            if let (_, Some(x)) = ps43_guard::reclassify_sg(self.cfg.g43.as_ref(), a.w, ps43_guard::sg_l_has(&a.sig), "deadline".into(), &l.err) { j["guard_abort"] = x; }
        }
        let k = filter_kind(a);
        if l.res == "unseen" { return j; }
        j["slot"] = l.slot.into(); j["idx"] = l.idx.into(); j["t"] = l.t_rx.into();
        j["slots_after_send"] = (l.slot as i64 - a.slot as i64).into();
        j["ms_send_to_rx"] = ((l.t_rx as i64 - a.t_send as i64) as f64 / 1e6).into();
        // the curve just before our position: the last trade of the mint before (slot, idx); none since the signing: the signing state
        let Some(idx) = l.idx else { j["would_fill"] = serde_json::Value::Null; self.p46.by_kind.entry(k).or_default().unknown += 1; return j };
        let ours = (l.slot, idx as u32);
        let pre = self.p46.tape.get(&a.mint).and_then(|tp| tp.iter().filter(|x| (x.0, x.1) < ours).max_by_key(|x| (x.0, x.1, x.2)).copied());
        let (pv, pt, src) = match pre {
            Some(x) if (x.0, x.1, x.2) >= a.sign_pos => (x.3, x.4, serde_json::json!({"slot": x.0, "idx": x.1, "j": x.2})),
            _ => (a.x46.sv, a.x46.st, "sign".into()),
        };
        let tokens = pl::buy_out(pv, pt, a.x46.spend, a.x46.fr);
        let would = tokens >= a.min_out_real() && a.min_out_real() > 0;
        j["pre"] = serde_json::json!({"vsol": pv, "vtok": pt, "p": pv as f64 / pt.max(1) as f64, "at": src});
        j["would_tokens"] = tokens.into();
        j["would_fill"] = would.into();
        let ks = self.p46.by_kind.entry(k).or_default();
        if would { ks.would_fill += 1; } else { ks.would_miss += 1; }
        j
    }

    // ---- the A/B ---------------------------------------------------------------------------------------------------------
    /// the arm-time A/B's records on a T2 trigger's skip / arm record (nothing unless an arm-time filter is A/B'd): `why` the live skip
    /// reason (None: armed as window `id`), `would` the log-mode verdicts (would43 + wh / hl would) of this trigger
    pub(super) fn ab46_trig(&mut self, r: &mut serde_json::Value, why: Option<&'static str>, would: &[&'static str], id: Option<u64>, mint: &Pk) {
        let ab = self.sh.p46.ab.load(Ordering::Relaxed);
        // no arm-time A/B now (only window-parity filters): the arm record still says each window's arm; nothing on a skip
        let Some(bypass) = self.p46.ab_cur.or_else(|| (id.is_some() && ab != 0).then_some(false)) else { return };
        let arm_time = self.p46.ab_cur.is_some();
        let mut bits_would = 0u32;
        for w in would { bits_would |= ab_of_why(w) & ab; }
        let live_block = why.map_or(0, |w| ab_of_why(w) & ab);
        let mut arms = serde_json::Map::new();
        for n in ab_names(ab) {
            let b = ab_bit(n);
            let arm = if b & AB_ARM != 0 { if !arm_time { continue } else if bypass { "bypass" } else { "live" } } else if let Some(i) = id { if i % 2 == 1 { "bypass" } else { "live" } } else { continue };
            arms.insert(n.to_string(), arm.into());
        }
        let wn = if bypass { ab_names(bits_would) } else { Vec::new() };
        let tag = serde_json::json!({"n": self.p46.ab_n, "arms": arms, "would": wn});
        r["ab46"] = tag.clone();
        let emit = |p: &mut P46, bits: u32, arm: &str, armed: bool, out: &crossbeam_channel::Sender<Out>| {
            for n in ab_names(bits) {
                let s = p.ab_st.entry(n).or_default();
                if arm == "live" { s[0] += 1; } else { s[1] += 1; if armed { s[2] += 1; } }
                let _ = out.send(Out::Rec(serde_json::json!({"ev": "presend_live_filter_ab", "w": id, "n_trig": p.ab_n, "mint": b58(mint), "filter": n, "arm": arm,
                    "would_block": true, "armed": armed, "kind": "T2", "t": arbx::feeds::clock::now_ns()})));
            }
        };
        let out = self.out.clone();
        if !arm_time {} else if bypass { emit(&mut self.p46, bits_would, "bypass", id.is_some(), &out); } else { emit(&mut self.p46, live_block, "live", false, &out); }
        if let Some(i) = id { self.p46.ab_wins.insert(i, (tag, if bypass { bits_would } else { 0 })); if self.p46.ab_wins.len() > 4096 { let lo = i.saturating_sub(2048); self.p46.ab_wins.retain(|k, _| *k >= lo); } }
    }
    /// a real try that bypassed send-time filters (drain_atts): the window's tag learns them
    pub(super) fn p46_ab_send(&mut self, w: u64, bits: u32) {
        let e = self.p46.ab_wins.entry(w).or_insert_with(|| (serde_json::json!({"arms": {}, "would": []}), 0));
        let new = bits & !e.1;
        if new == 0 { return; }
        e.1 |= bits;
        for n in ab_names(new) { if let Some(a) = e.0["would"].as_array_mut() { a.push(n.into()); } e.0["arms"][n] = "bypass".into(); }
    }
    /// the fill's "ab46" (None without the A/B flag): the window's arms and the bypassed filters that would have blocked it
    pub(super) fn p46_fill_tag(&self, att: &Att) -> Option<serde_json::Value> {
        if !self.cfg.p46.ab_flag { return None; }
        let ab = self.sh.p46.ab.load(Ordering::Relaxed);
        let mut j = self.p46.ab_wins.get(&att.w).map(|x| x.0.clone()).unwrap_or_else(|| serde_json::json!({"arms": {}, "would": []}));
        // the window-parity filters' arm (send-time + floors) even when nothing was bypassed
        for n in ab_names(ab & !AB_ARM) { if j["arms"].get(n).is_none() { j["arms"][n] = if att.w % 2 == 1 { "bypass" } else { "live" }.into(); } }
        if att.x46.ab != 0 { j["try_bypassed"] = ab_names(att.x46.ab).into(); }
        Some(j)
    }

    // ---- the control file ("ab46": {filter: "ab" | "live"}, "probe46": "on" | "off") -------------------------------------
    pub(super) fn p46_ctl_check(&mut self, force: bool) {
        let Some((path, mt0, at)) = self.p46.ctl.clone() else { return };
        if !force && at.elapsed() < Duration::from_secs(10) { return; }
        let mt = std::fs::metadata(&path).and_then(|m| m.modified()).ok();
        if let Some(c) = self.p46.ctl.as_mut() { c.2 = Instant::now(); }
        if !force && mt == mt0 { return; }
        if let Some(c) = self.p46.ctl.as_mut() { c.1 = mt; }
        let parsed = std::fs::read(&path).map_err(|e| e.to_string()).and_then(|b| ctl46_parse(&b));
        match parsed {
            Ok((abk, pk)) => {
                let (ab0, p0) = (self.sh.p46.ab.load(Ordering::SeqCst), self.sh.p46.probe.load(Ordering::SeqCst));
                let avail = ab_avail(&self.cfg);
                let mut ab = ab0;
                let mut ignored = Vec::new();
                if self.cfg.p46.ab_flag {
                    for (n, on) in &abk { let b = ab_bit(n); if b & avail == 0 { ignored.push(n.clone()); continue; } if *on { ab |= b; } else { ab &= !b; } }
                } else if !abk.is_empty() { ignored.push("ab46 (needs --presend-live-filter-ab)".into()); }
                let p = match pk { Some(x) if self.cfg.p46.probe => x, Some(_) => { ignored.push("probe46 (needs --presend-live-probe on)".into()); p0 } None => p0 };
                if ab == ab0 && p == p0 && ignored.is_empty() { return; }
                self.sh.p46.ab.store(ab, Ordering::SeqCst);
                self.sh.p46.probe.store(p, Ordering::SeqCst);
                self.p46.ctl_changes += 1;
                self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": true, "dip46": {"ab46": ab_names(ab), "probe46": p}, "was": {"dip46": {"ab46": ab_names(ab0), "probe46": p0}},
                    "ignored": ignored, "path": path, "t": arbx::feeds::clock::now_ns()}));
                self.line(format!("  PRESEND LIVE DIP46 KEYS ({path}): A/B {:?} -> {:?}, probes {} -> {}{}", ab_names(ab0), ab_names(ab), p0, p,
                    if ignored.is_empty() { String::new() } else { format!(" (ignored: {})", ignored.join(", ")) }));
            }
            Err(e) => {
                self.rec(serde_json::json!({"ev": "presend_live_ledger_mode", "ok": false, "err": e, "path": path, "dip46": true, "t": arbx::feeds::clock::now_ns()}));
                self.line(format!("  PRESEND LIVE DIP46 control keys in {path} NOT read ({e}): the modes stay"));
            }
        }
    }

    /// the run's end (finish): probe windows end, probes not seen are "unseen", every landing record written
    pub(super) fn p46_flush(&mut self) {
        if !self.p46_on() { return; }
        let ids: Vec<u64> = self.p46.wins.keys().copied().collect();
        for id in ids { self.p46_end(id, "stopped"); }
        let pend: Vec<[u8; 64]> = self.p46.atts.iter().filter(|(_, (_, d))| !*d).map(|(k, _)| *k).collect();
        for sig in pend {
            if let Some((att, done)) = self.p46.atts.get_mut(&sig) {
                *done = true;
                let att = att.clone();
                self.p46.unseen += 1;
                self.p46.by_kind.entry(att.x46.probe.and_then(kind_of).unwrap_or("?")).or_default().unseen += 1;
                *self.p46.res.entry("unseen".into()).or_default() += 1;
                self.p46.lands.push(PLand { att, res: "unseen".into(), err: String::new(), fee: 0, slot: 0, idx: None, t_rx: 0, at: Instant::now() });
            }
        }
        for l in std::mem::take(&mut self.p46.lands) { let r = self.p46_land_rec(&l); self.rec(r); }
    }

    // ---- totals ----------------------------------------------------------------------------------------------------------
    pub(super) fn status46(&self) -> String {
        if !self.p46_on() { return String::new(); }
        let mut s = String::new();
        if self.cfg.p46.probe {
            let (wf, wm): (u64, u64) = self.p46.by_kind.values().fold((0, 0), |a, k| (a.0 + k.would_fill, a.1 + k.would_miss));
            s += &format!(" | PROBE: {} sent {} (dry {}) landed {} unseen {} would-fill {}/{} fees {:.6} SOL | windows {} (now {}) | refused {:?}{}",
                if self.sh.p46.probe.load(Ordering::Relaxed) { "on" } else { "OFF" }, self.sh.p46.sent.load(Ordering::Relaxed), self.sh.p46.dry.load(Ordering::Relaxed),
                self.p46.landed, self.p46.unseen, wf, wf + wm, self.p46.fees as f64 / 1e9, self.p46.windows, self.p46.wins.len(), self.sh.p46.refused.lock().unwrap(),
                if self.p46.impossible > 0 { format!(" | PROBE FILLED (impossible) {}", self.p46.impossible) } else { String::new() });
        }
        if self.cfg.p46.ab_flag {
            s += &format!(" | AB46 {:?}: triggers {} | live/bypass would-block, bypass armed {:?} | send bypasses {:?}", ab_names(self.sh.p46.ab.load(Ordering::Relaxed)), self.p46.ab_n,
                self.p46.ab_st, self.sh.p46.ab_bypassed.lock().unwrap());
        }
        s
    }
    pub(super) fn finish46(&self) -> Option<serde_json::Value> {
        if !self.p46_on() { return None; }
        let kinds: serde_json::Map<String, serde_json::Value> = self.p46.by_kind.iter().map(|(k, v)| (k.to_string(), serde_json::json!({"sent": v.sent, "landed": v.landed,
            "unseen": v.unseen, "fees": v.fees, "would_fill": v.would_fill, "would_miss": v.would_miss, "unknown": v.unknown}))).collect();
        Some(serde_json::json!({"cfg": self.cfg.p46.json(), "probe_on": self.sh.p46.probe.load(Ordering::Relaxed), "sent": self.sh.p46.sent.load(Ordering::Relaxed),
            "dry": self.sh.p46.dry.load(Ordering::Relaxed), "landed": self.p46.landed, "unseen": self.p46.unseen, "probe_fees": self.p46.fees, "results": self.p46.res,
            "by_kind": kinds, "sent_by_kind": *self.sh.p46.by_kind.lock().unwrap(), "windows": self.p46.windows, "window_refused": self.p46.win_refused,
            "refused": *self.sh.p46.refused.lock().unwrap(), "impossible_fills": self.p46.impossible,
            "ab": {"now": ab_names(self.sh.p46.ab.load(Ordering::Relaxed)), "triggers": self.p46.ab_n, "arm_time": self.p46.ab_st, "send_bypassed": *self.sh.p46.ab_bypassed.lock().unwrap(),
                "ctl_changes": self.p46.ctl_changes}}))
    }
}

fn filter_kind(a: &Att) -> &'static str { a.x46.probe.and_then(kind_of).unwrap_or("?") }

impl Att {
    /// a probe's REAL min_out (the try it stands for: the 0.88x limit's tokens); a real try's own
    pub fn min_out_real(&self) -> u64 { if self.x46.probe.is_some() { self.x46.min } else { self.min_out } }
}

/// the control file's dip46 keys: "ab46": {filter: "ab" | "live" | "off"} ("live" / "off" = no A/B: the filter as its own mode),
/// "probe46": "on" | "off"
pub fn ctl46_parse(b: &[u8]) -> std::result::Result<(Vec<(String, bool)>, Option<bool>), String> {
    let v: serde_json::Value = serde_json::from_slice(b).map_err(|e| format!("bad JSON: {e}"))?;
    if !v.is_object() { return Err("not an object".into()); }
    let mut ab = Vec::new();
    match v.get("ab46") {
        None | Some(serde_json::Value::Null) => {}
        Some(serde_json::Value::Object(m)) => for (k, x) in m {
            if ab_bit(k) == 0 { return Err(format!("ab46: unknown filter '{k}' ({})", AB_NAMES.join(" | "))); }
            match x.as_str() { Some("ab") => ab.push((k.clone(), true)), Some("live") | Some("off") => ab.push((k.clone(), false)), _ => return Err(format!("ab46.{k}: '{x}' (ab | live)")) }
        },
        Some(x) => return Err(format!("ab46: '{x}' (an object {{filter: \"ab\" | \"live\"}})")),
    }
    let p = match v.get("probe46") { None | Some(serde_json::Value::Null) => None, Some(x) => match x.as_str() { Some("on") => Some(true), Some("off") => Some(false), _ => return Err(format!("probe46: '{x}' (on | off)")) } };
    Ok((ab, p))
}

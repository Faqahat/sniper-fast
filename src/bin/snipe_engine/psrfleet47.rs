// =====================================================================================================================
// dip47 RE-ARM FLEET RULE (owner 11-11; default LOG, live by flag / the hot key "rearm_fleet"). RE-ARM windows only, never T2 / wide.
// Evidence: /home/it/sniper-data/fleet8283/rule_r65_82.txt (re-arm fills with >= 1 fleet-shape try on the mint in the 8 slots before the
// landing did well, the others lost: +1.26 SOL saved, both halves; the same rule on T2 LOSES).
//   --presend-live-rearm-fleet N:SLOTS (off by default; needs --presend-live-fleet-log on: the detector) and
//   --presend-live-rearm-fleet-mode log|live (log). Hot keys "rearm_fleet": log|live, "rearm_fleet_spec": "N:SLOTS" (N 1..50, SLOTS 1..32).
// RULE (per send, like bot depth): a re-arm window's try signed in slot s is sent only if the detector saw >= N fleet-class tries
// (ps45_fleet: pre-exec + executed feeds, de-duplicated by signature, ours never) on the mint in slots [s - SLOTS, s]. Live: the try is
// withheld, counted not-sent "rearm_fleet_withheld"; log: sent, counted would.
// FAIL OPEN (never withheld, counted with its reason): "no_data" = no fleet try seen on any mint since the start; "stale" = none for
// STALE_NS (10 min: the fleet is off or the pre-exec feeds are down); "blind" = the executed feed's blind episode (dip43 A1).
// HOW: the main loop (the detector's event-loop side: FleetTap::arrival) keeps the last 33 slots' fleet-try counts per mint and copies
// the armed re-arm window's counts into its SWin (as the bot depth copy). The sender reads the copy it already cloned + 4 relaxed
// atomic loads (spec, mode, last try, blind): no lock, no allocation. Per window one summary record + line, written by the sender
// ~2 s after the window's last try (off the try's path).
// =====================================================================================================================
use super::*;

pub const FLAG: &str = "--presend-live-rearm-fleet";
pub const FLAG_MODE: &str = "--presend-live-rearm-fleet-mode";
pub const STALE_NS: u64 = 600 * 1_000_000_000;
pub const SPAN: usize = 33;

/// N:SLOTS (N 1..50, SLOTS 1..32)
pub fn spec_parse(s: &str) -> std::result::Result<(u32, u64), String> {
    let bad = || format!("'{s}': N:SLOTS (fleet tries 1..50 within slots 1..32), e.g. 1:8");
    let (n, k) = s.split_once(':').ok_or_else(bad)?;
    let (n, k): (u32, u64) = (n.trim().parse().map_err(|_| bad())?, k.trim().parse().map_err(|_| bad())?);
    if !(1..=50).contains(&n) || !(1..=32).contains(&k) { return Err(bad()); }
    Ok((n, k))
}

/// a mint's fleet tries per slot: c[d] = tries in slot `base` - d (the window's copy in SWin; Copy, no allocation)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct FlSnap { pub base: u64, pub c: [u8; SPAN] }
impl Default for FlSnap { fn default() -> FlSnap { FlSnap { base: 0, c: [0; SPAN] } } }
impl FlSnap {
    pub fn add(&mut self, slot: u64) {
        if slot > self.base {
            let sh = (slot - self.base) as usize;
            if sh >= SPAN { self.c = [0; SPAN]; } else { self.c.copy_within(0..SPAN - sh, sh); self.c[..sh].fill(0); }
            self.base = slot;
        }
        let d = (self.base - slot) as usize;
        if d < SPAN { self.c[d] = self.c[d].saturating_add(1); }
    }
    /// tries in slots [slot - slots, slot]
    pub fn count(&self, slot: u64, slots: u64) -> u32 {
        let mut n = 0u32;
        for (d, &x) in self.c.iter().enumerate() {
            if x == 0 { continue; }
            let s = self.base - (d as u64).min(self.base);
            if s <= slot && s + slots >= slot { n += x as u32; }
        }
        n
    }
}

/// the sender's view (atomics only)
#[derive(Default)]
pub struct ShRf {
    /// 0 = off; else n << 32 | slots
    pub spec: AtomicU64,
    pub live: AtomicBool,
    /// mono ns of the newest fleet-class try on any mint (0: none yet)
    pub last: AtomicU64,
    pub blind: AtomicBool,
    /// [passed, withheld (live), would (log), open]
    pub n: [AtomicU64; 4],
}
impl ShRf {
    pub fn set(&self, spec: Option<(u32, u64)>, live: bool) {
        self.spec.store(spec.map_or(0, |(n, k)| (n as u64) << 32 | k), Ordering::Release);
        self.live.store(live, Ordering::Release);
    }
}

/// a re-arm try's verdict
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct RfV { pub n: u32, pub min: u32, pub slots: u64, pub live: bool, pub would: bool, pub open: Option<&'static str> }
impl RfV {
    pub fn withhold(&self) -> bool { self.live && self.would && self.open.is_none() }
    pub fn json(&self) -> serde_json::Value {
        let mut j = serde_json::json!({"n": self.n, "min": self.min, "slots": self.slots, "on": if self.live { "live" } else { "log" }, "would_withhold": self.would});
        if let Some(o) = self.open { j["open"] = o.into(); }
        j
    }
}

/// the sender's check of a RE-ARM window's try at `slot` (None: the rule off). Lock-free: 4 relaxed loads + the window's copy
#[inline]
pub fn check(sh: &ShRf, snap: &FlSnap, slot: u64, now: u64) -> Option<RfV> {
    let sp = sh.spec.load(Ordering::Relaxed);
    if sp == 0 { return None; }
    let (min, slots) = ((sp >> 32) as u32, sp & 0xFFFF_FFFF);
    let live = sh.live.load(Ordering::Relaxed);
    let last = sh.last.load(Ordering::Relaxed);
    let n = snap.count(slot, slots);
    let would = n < min;
    let open = if last == 0 { Some("no_data") } else if now.saturating_sub(last) > STALE_NS { Some("stale") } else if sh.blind.load(Ordering::Relaxed) { Some("blind") } else { None };
    let v = RfV { n, min, slots, live, would, open };
    let i = if !would { 0 } else if open.is_some() { 3 } else if live { 1 } else { 2 };
    sh.n[i].fetch_add(1, Ordering::Relaxed);
    Some(v)
}

/// the sender's gate: RE-ARM windows' real tries only (a T2 / wide window, a probe: None, nothing read, nothing counted)
#[inline]
pub fn gate(sh: &ShRf, rearm: bool, probe: bool, snap: &FlSnap, slot: u64, now: u64) -> Option<RfV> {
    if !rearm || probe { return None; }
    check(sh, snap, slot, now)
}

/// the sender's per-window counts (its own map: no lock) and the summary ~2 s after the window's last try
#[derive(Default)]
pub struct SendRf { w: FxHashMap<u64, (Pk, [u32; 4], u32, &'static str, u64, bool)>, at: u64 }
impl SendRf {
    pub fn note(&mut self, w: u64, mint: Pk, v: &RfV, now: u64) {
        let e = self.w.entry(w).or_insert((mint, [0; 4], u32::MAX, "", now, v.live));
        let i = if !v.would { 0 } else if v.open.is_some() { 3 } else if v.live { 1 } else { 2 };
        e.1[i] += 1; e.2 = e.2.min(v.n); e.4 = now; e.5 = v.live;
        if let Some(o) = v.open { e.3 = o; }
    }
    /// once per ~1 s from the sender's loop: the windows quiet for 2 s get their record + line
    pub fn flush(&mut self, out: &crossbeam_channel::Sender<Out>, now: u64, all: bool) {
        if self.w.is_empty() || (!all && now < self.at + 1_000_000_000) { return; }
        self.at = now;
        let done: Vec<u64> = self.w.iter().filter(|(_, e)| all || now > e.4 + 2_000_000_000).map(|(k, _)| *k).collect();
        for k in done {
            let Some((mint, c, nmin, open, _, live)) = self.w.remove(&k) else { continue };
            let mode = if live { "live" } else { "log" };
            let mut r = serde_json::json!({"ev": "presend_live_rearm_fleet", "w": k, "mint": b58(&mint), "kind": "rearm", "mode": mode, "tries": c.iter().sum::<u32>(), "passed": c[0],
                "withheld": c[1], "would": c[2], "open": c[3], "n_min": if nmin == u32::MAX { 0 } else { nmin }, "t": arbx::feeds::clock::now_ns()});
            if !open.is_empty() { r["open_why"] = open.into(); }
            let _ = out.send(Out::Rec(r));
            let _ = out.send(Out::Line(format!("  PRESEND LIVE REARM FLEET ({mode}) w{k} {}: tries {} | fleet seen {} | withheld {} | would {} | open {}{}", b58(&mint), c.iter().sum::<u32>(), c[0], c[1], c[2], c[3],
                if open.is_empty() { String::new() } else { format!(" ({open})") })));
        }
    }
}

/// the main loop's side: per mint its counts (bounded), de-duplicated by signature
#[derive(Default)]
pub struct Rf47 { pub m: FxHashMap<Pk, FlSnap>, seen: FxHashSet<u64>, seen_q: VecDeque<u64>, pub hits: u64 }

impl PsLive {
    /// a fleet-class try on any feed (FleetTap::arrival; only with the rule on): the mint's counts, the armed re-arm window's copy
    pub(super) fn rf47_hit(&mut self, mint: Pk, slot: u64, sig8: u64) {
        let r = &mut self.rf47;
        if !r.seen.insert(sig8) { return; }
        r.seen_q.push_back(sig8);
        while r.seen_q.len() > 8192 { if let Some(o) = r.seen_q.pop_front() { r.seen.remove(&o); } }
        r.hits += 1;
        if r.m.len() > 20_000 { let lo = slot.saturating_sub(SPAN as u64); r.m.retain(|_, s| s.base >= lo); }
        let s = r.m.entry(mint).or_default();
        s.add(slot);
        let s = *s;
        self.sh.rf.last.store(arbx::fast::mono_ns().max(1), Ordering::Relaxed);
        if let Some(&id) = self.armed.get(&mint) {
            if self.rearm_w(id) { let mut g = self.sh.wins.lock().unwrap(); if let Some(w) = g.iter_mut().find(|w| w.id == id) { w.rfl = s; } }
        }
    }
    /// a re-arm window's copy at its arm
    pub(super) fn rf47_snap(&self, mint: &Pk) -> FlSnap { self.rf47.m.get(mint).copied().unwrap_or_default() }
}

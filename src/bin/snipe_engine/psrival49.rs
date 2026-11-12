// =====================================================================================================================
// dip49 (owner 11-12, URGENT, LIVE by flag): RULE A = T2 RIVAL GATE (per try) and RULE B = the re-arm fresh-holders "f1" definition.
// Evidence and definitions: /home/it/sniper-data/rugdet/report.txt §A items 1-2, /home/it/sniper-studies/rugdet/s5_tape.py (slipsg20),
// s14_devcombo.py (dev_age_h), s4_feat.py (f1_pct).
//
// RULE A (--presend-live-rival-gate R0:R2:AGE_H, --presend-live-rival-gate-mode log|live, --presend-live-rival-gate-slots N (20); hot keys
// "rival_gate" log|live, "rival_gate_spec" "R0:R2:AGE_H"). T2 windows only (never re-arm, wide or probe tries). A T2 try signed in slot s
// is withheld (live; not-sent "rival_gate_withheld") / counted would (log) when
//     rivals <= R0   OR   (rivals <= R2 AND dev age < AGE_H hours)
//   rivals = rugdet slipsg20: DISTINCT fee payers (ours never; the fleet and every other bot count) of FAILED executed txs whose error is an
//            InstructionError with Custom code in {6001, 6002, 6003, 6024, 6040, 6042} (any instruction) and that name the mint, in slots
//            [s - N, s - 1] (rugdet: (cut - 20, cut], cut = fill - 2 = the signing slot - 1). The executed gRPC feed's failed txs (the
//            RIVAL TAP in src/feeds), matched to followed tokens on the main loop; per mint the 16 most recent distinct payers (last two slots).
//   dev age  = s14_devcombo.py: the creator's age at the create = create time - blockTime of its OLDEST tx before the create signature
//            (getSignaturesForAddress(creator, {before: create sig, limit 1000})); 0 when the create is its first tx; 1000 results
//            (capped) = old; an error / no answer yet = UNKNOWN = not young (only "rivals <= R0" can block). Looked up ONCE per creator
//            at the token's create (followed tokens) by background workers (the funder log's RPC setting; the URL never printed), cached.
//   FAIL OPEN (never withheld; the reason recorded): "stale" = no slippage fail seen on any mint for 60 s (the executed feed's fails are
//            missing: rivals would read 0 everywhere); "blind" = the executed feed's blind episode (dip43 A1).
//   Sender: the window's copy (kept by the main loop: payers + dev age) + 5 relaxed atomic loads; no lock, no allocation.
//   Records: presend_attempt / presend_live_fill "rival_gate" {rivals, dev_age_h, young, on, blocked (= would), open?}; presend_live_realized
//            "rival_gate" {rivals, dev_age_h, blocked}; per window presend_live_rival_gate {tries, passed, withheld, would, open, rivals_min,
//            dev_age_h, dev_age_src} + a line.
// RULE B (--presend-live-fresh-skip-ra-def f1|f3, default f3 = dip48; hot key "fresh_skip_ra_def"): the re-arm lane of
//   --presend-live-fresh-skip uses f1 = s4_feat.py's f1_pct: the holders >= 2% of supply, top 12 (the fill annotation's set), with <= 1 hold on
//   record, leaving out us, the dumper and the R5 holder (the largest holder at the check, when R5 ran), summed (% of supply). f3 (dip32):
//   top 16, us and the dumper out. Both logged in the re-arm's fresh_skip object.
// =====================================================================================================================
use super::*;

pub const FLAG: &str = "--presend-live-rival-gate";
pub const FLAG_MODE: &str = "--presend-live-rival-gate-mode";
pub const FLAG_SLOTS: &str = "--presend-live-rival-gate-slots";
pub const FLAG_RADEF: &str = "--presend-live-fresh-skip-ra-def";
pub const STALE_NS: u64 = 60 * 1_000_000_000;
pub const NPAY: usize = 16;
const TIMEOUT: Duration = Duration::from_secs(8);

/// R0:R2:AGE_H (R0 0..10, R2 0..20, AGE_H 0..720)
pub fn spec_parse(s: &str) -> std::result::Result<(u32, u32, f64), String> {
    let bad = || format!("'{s}': R0:R2:AGE_H (rivals <= R0 always; rivals <= R2 with a dev younger than AGE_H hours; R0 0..10, R2 0..20, AGE_H 0..720), e.g. 0:2:1");
    let v: Vec<&str> = s.split(':').map(str::trim).collect();
    if v.len() != 3 { return Err(bad()); }
    let (a, b, c): (u32, u32, f64) = (v[0].parse().map_err(|_| bad())?, v[1].parse().map_err(|_| bad())?, v[2].parse().map_err(|_| bad())?);
    if a > 10 || b > 20 || !(c.is_finite() && (0.0..=720.0).contains(&c)) { return Err(bad()); }
    Ok((a, b, c))
}
fn sig8(p: &Pk) -> u64 { u64::from_le_bytes(p[..8].try_into().unwrap()) }

/// a mint's recent rival payers: (payer, last slot, the previous distinct slot)
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Pay { pub p: u64, pub last: u64, pub prev: u64 }

/// the window's copy for the sender (Copy, no allocation)
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RgSnap { pub on: bool, pub age_h: f32, pub src: u8, pub n: u8, pub e: [Pay; NPAY] }
impl Default for RgSnap { fn default() -> RgSnap { RgSnap { on: false, age_h: f32::NAN, src: 0, n: 0, e: [Pay::default(); NPAY] } } }
pub const SRC: [&str; 5] = ["none", "rpc", "capped", "error", "pending"];
impl RgSnap {
    /// distinct payers with a fail in [s - slots, s - 1]
    pub fn rivals(&self, s: u64, slots: u64) -> u32 {
        let lo = s.saturating_sub(slots);
        self.e[..self.n as usize].iter().filter(|x| { let t = if x.last < s { x.last } else { x.prev }; t != 0 && t >= lo && t < s }).count() as u32
    }
    pub fn add(&mut self, p: u64, slot: u64) {
        let n = self.n as usize;
        if let Some(x) = self.e[..n].iter_mut().find(|x| x.p == p) {
            if slot > x.last { x.prev = x.last; x.last = slot; } else if slot < x.last && slot > x.prev { x.prev = slot; }
            return;
        }
        let x = Pay { p, last: slot, prev: 0 };
        if n < NPAY { self.e[n] = x; self.n += 1; return; }
        // full: the payer seen longest ago goes
        if let Some((i, _)) = self.e.iter().enumerate().min_by_key(|(_, y)| y.last) { if self.e[i].last < slot { self.e[i] = x; } }
    }
}

/// the sender's view (atomics)
#[derive(Default)]
pub struct ShRg {
    /// 0 = off; else (r0 << 48) | (r2 << 32) | slots
    pub spec: AtomicU64,
    /// AGE_H as f64 bits
    pub age: AtomicU64,
    pub live: AtomicBool,
    /// mono ns of the newest slippage fail seen (any mint; 0: none yet)
    pub last_fail: AtomicU64,
    pub blind: AtomicBool,
    /// [passed, withheld, would, open]
    pub n: [AtomicU64; 4],
}
impl ShRg {
    pub fn set(&self, spec: Option<(u32, u32, f64)>, slots: u64, live: bool) {
        self.spec.store(spec.map_or(0, |(a, b, _)| (a as u64) << 48 | (b as u64) << 32 | slots.max(1)), Ordering::Release);
        self.age.store(spec.map_or(0.0f64, |s| s.2).to_bits(), Ordering::Release);
        self.live.store(live, Ordering::Release);
    }
}

/// a T2 try's verdict
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct RgV { pub rivals: u32, pub age_h: f32, pub young: bool, pub live: bool, pub would: bool, pub open: Option<&'static str>, pub src: u8 }
impl RgV {
    pub fn withhold(&self) -> bool { self.live && self.would && self.open.is_none() }
    pub fn json(&self) -> serde_json::Value {
        let mut j = serde_json::json!({"rivals": self.rivals, "dev_age_h": if self.age_h.is_finite() { serde_json::json!((self.age_h as f64 * 1e3).round() / 1e3) } else { serde_json::Value::Null },
            "young": self.young, "dev_age_src": SRC[self.src as usize], "on": if self.live { "live" } else { "log" }, "blocked": self.would});
        if let Some(o) = self.open { j["open"] = o.into(); }
        j
    }
}

/// the sender's gate: T2 windows' real tries only (`snap.on` false: a re-arm / wide window, the rule off at its arm). Lock-free
#[inline]
pub fn gate(sh: &ShRg, snap: &RgSnap, probe: bool, slot: u64, now: u64) -> Option<RgV> {
    if !snap.on || probe { return None; }
    let sp = sh.spec.load(Ordering::Relaxed);
    if sp == 0 { return None; }
    let (r0, r2, slots) = ((sp >> 48) as u32, ((sp >> 32) & 0xFFFF) as u32, sp & 0xFFFF_FFFF);
    let age = f64::from_bits(sh.age.load(Ordering::Relaxed));
    let live = sh.live.load(Ordering::Relaxed);
    let rivals = snap.rivals(slot, slots);
    let young = snap.age_h.is_finite() && (snap.age_h as f64) < age;
    let would = rivals <= r0 || (rivals <= r2 && young);
    let lf = sh.last_fail.load(Ordering::Relaxed);
    let open = if lf == 0 || now.saturating_sub(lf) > STALE_NS { Some("stale") } else if sh.blind.load(Ordering::Relaxed) { Some("blind") } else { None };
    let v = RgV { rivals, age_h: snap.age_h, young, live, would, open, src: snap.src };
    let i = if !would { 0 } else if open.is_some() { 3 } else if live { 1 } else { 2 };
    sh.n[i].fetch_add(1, Ordering::Relaxed);
    Some(v)
}

/// the sender's per-window counts and summary (~2 s after the window's last try)
#[derive(Default)]
pub struct SendRg { w: FxHashMap<u64, (Pk, [u32; 4], u32, &'static str, u64, bool, f32, u8)>, at: u64 }
impl SendRg {
    pub fn note(&mut self, w: u64, mint: Pk, v: &RgV, now: u64) {
        let e = self.w.entry(w).or_insert((mint, [0; 4], u32::MAX, "", now, v.live, v.age_h, v.src));
        let i = if !v.would { 0 } else if v.open.is_some() { 3 } else if v.live { 1 } else { 2 };
        e.1[i] += 1; e.2 = e.2.min(v.rivals); e.4 = now; e.5 = v.live; e.6 = v.age_h; e.7 = v.src;
        if let Some(o) = v.open { e.3 = o; }
    }
    pub fn flush(&mut self, out: &crossbeam_channel::Sender<Out>, now: u64, all: bool) {
        if self.w.is_empty() || (!all && now < self.at + 1_000_000_000) { return; }
        self.at = now;
        let done: Vec<u64> = self.w.iter().filter(|(_, e)| all || now > e.4 + 2_000_000_000).map(|(k, _)| *k).collect();
        for k in done {
            let Some((mint, c, rmin, open, _, live, age, src)) = self.w.remove(&k) else { continue };
            let mode = if live { "live" } else { "log" };
            let ah = if age.is_finite() { serde_json::json!((age as f64 * 1e3).round() / 1e3) } else { serde_json::Value::Null };
            let mut r = serde_json::json!({"ev": "presend_live_rival_gate", "w": k, "mint": b58(&mint), "kind": "t2", "mode": mode, "tries": c.iter().sum::<u32>(), "passed": c[0],
                "withheld": c[1], "would": c[2], "open": c[3], "rivals_min": if rmin == u32::MAX { 0 } else { rmin }, "dev_age_h": ah, "dev_age_src": SRC[src as usize],
                "t": arbx::feeds::clock::now_ns()});
            if !open.is_empty() { r["open_why"] = open.into(); }
            let _ = out.send(Out::Rec(r));
            let _ = out.send(Out::Line(format!("  PRESEND LIVE RIVAL GATE ({mode}) w{k} {}: tries {} | passed {} | withheld {} | would {} | open {}{} | rivals min {} | dev age {}", b58(&mint),
                c.iter().sum::<u32>(), c[0], c[1], c[2], c[3], if open.is_empty() { String::new() } else { format!(" ({open})") }, if rmin == u32::MAX { 0 } else { rmin },
                if age.is_finite() { format!("{age:.2} h") } else { SRC[src as usize].to_string() })));
        }
    }
}

// ---- dev age lookups ----------------------------------------------------------------------------------------------------------

/// a creator's oldest tx before a create: Oldest(blockTime s; = the create's own time when the create was its first tx), Capped, Err
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Dev { Oldest(f64), Capped, Err }
#[derive(Clone, Debug)]
pub struct DJob { pub creator: Pk, pub sig: [u8; 64], pub t: f64 }
pub type Src<'a> = dyn Fn(&str, serde_json::Value) -> std::result::Result<serde_json::Value, String> + 'a;

/// one lookup (s14_devcombo.py: capped at 1000 = old; none before the create = age 0)
pub fn dev_lookup(src: &Src, j: &DJob) -> Dev {
    let p = serde_json::json!([b58(&j.creator), {"before": bs58::encode(&j.sig).into_string(), "limit": 1000, "commitment": "confirmed"}]);
    match src("getSignaturesForAddress", p) {
        Ok(v) => match v.as_array() {
            Some(a) if a.len() >= 1000 => Dev::Capped,
            Some(a) if a.is_empty() => Dev::Oldest(j.t),
            Some(a) => a.last().and_then(|x| x["blockTime"].as_f64()).map_or(Dev::Err, Dev::Oldest),
            None => Dev::Err,
        },
        Err(_) => Dev::Err,
    }
}

#[derive(Default)]
pub struct DevSh { pub q: Mutex<VecDeque<DJob>>, pub stop: AtomicBool, pub calls: AtomicU64, pub errs: AtomicU64, pub drops: AtomicU64, next: Mutex<Option<Instant>> }
pub fn dev_work(sh: &DevSh, src: &Src, gap: Duration, tx: &crossbeam_channel::Sender<(Pk, Dev)>) -> bool {
    let Some(j) = sh.q.lock().unwrap().pop_front() else { return false };
    let wait = { let mut n = sh.next.lock().unwrap(); let now = Instant::now(); let at = n.map_or(now, |x| x.max(now)); *n = Some(at + gap); at - now };
    if !wait.is_zero() { std::thread::sleep(wait); }
    sh.calls.fetch_add(1, Ordering::Relaxed);
    let d = dev_lookup(src, &j);
    if d == Dev::Err { sh.errs.fetch_add(1, Ordering::Relaxed); }
    let _ = tx.send((j.creator, d));
    true
}

/// the main loop's side
pub struct Rg49 {
    pub fails: crossbeam_channel::Receiver<arbx::feeds::RivalFail>,
    pub test_tx: Option<crossbeam_channel::Sender<arbx::feeds::RivalFail>>,
    pub mints: FxHashMap<Pk, RgSnap>,
    pub creates: FxHashMap<Pk, (Pk, f64)>,
    creates_q: VecDeque<Pk>,
    pub dev: FxHashMap<Pk, Dev>,
    pending: FxHashSet<Pk>,
    pub dsh: Arc<DevSh>,
    drx: crossbeam_channel::Receiver<(Pk, Dev)>,
    dtx: crossbeam_channel::Sender<(Pk, Dev)>,
    /// per window its fill's verdict (the realized record's)
    pub done: FxHashMap<u64, serde_json::Value>,
    pub n_fails: u64, pub n_matched: u64,
}
const DEV_Q: usize = 4096;
const DEV_CACHE: usize = 100_000;
impl Rg49 {
    fn base(fails: crossbeam_channel::Receiver<arbx::feeds::RivalFail>, test_tx: Option<crossbeam_channel::Sender<arbx::feeds::RivalFail>>) -> Rg49 {
        let (dtx, drx) = crossbeam_channel::unbounded();
        Rg49 { fails, test_tx, mints: FxHashMap::default(), creates: FxHashMap::default(), creates_q: VecDeque::new(), dev: FxHashMap::default(), pending: FxHashSet::default(),
            dsh: Arc::new(DevSh::default()), drx, dtx, done: FxHashMap::default(), n_fails: 0, n_matched: 0 }
    }
    /// the tests: a private fail channel, no workers
    pub fn idle() -> Rg49 { let (tx, rx) = crossbeam_channel::bounded(65_536); Rg49::base(rx, Some(tx)) }
    /// the engine: the feed's tap and the workers on `url` (never printed)
    pub fn start(url: Option<String>, rps: u32) -> Option<Rg49> {
        let rx = arbx::feeds::rival_tap_on()?;
        let r = Rg49::base(rx, None);
        if let Some(url) = url {
            let gap = Duration::from_secs_f64(1.0 / rps.clamp(1, 40) as f64);
            for i in 0..2 {
                let (sh, tx, url) = (r.dsh.clone(), r.dtx.clone(), url.clone());
                let _ = std::thread::Builder::new().name(format!("ps-devage-{i}")).spawn(move || {
                    unsafe { let tid = libc::syscall(libc::SYS_gettid); libc::setpriority(libc::PRIO_PROCESS, tid as libc::id_t, 19); }
                    let Ok(rt) = tokio::runtime::Builder::new_current_thread().enable_all().build() else { return };
                    let client = rpc::Rpc::race(vec![rpc::Endpoint { name: "devage".into(), url, bearer: None }]);
                    let src = move |m: &str, p: serde_json::Value| rt.block_on(client.call_bounded(m, p, rpc::Bounds::fetch(TIMEOUT, 0))).map(|f| f.value).map_err(|e| rpc::scrub(&e.msg));
                    while !sh.stop.load(Ordering::Relaxed) { if !dev_work(&sh, &src, gap, &tx) { std::thread::sleep(Duration::from_millis(5)); } }
                });
            }
        }
        Some(r)
    }
    pub fn pump(&mut self, src: &Src) { while dev_work(&self.dsh, src, Duration::ZERO, &self.dtx) {} }
    /// a create of a followed token: its creator's age looked up once (queued; never waited for)
    pub fn create(&mut self, mint: Pk, creator: Pk, sig: [u8; 64], t: f64) {
        self.creates.insert(mint, (creator, t));
        self.creates_q.push_back(mint);
        while self.creates_q.len() > 200_000 { if let Some(o) = self.creates_q.pop_front() { self.creates.remove(&o); self.mints.remove(&o); } }
        if self.dev.contains_key(&creator) || !self.pending.insert(creator) { return; }
        let mut q = self.dsh.q.lock().unwrap();
        if q.len() >= DEV_Q { if let Some(o) = q.pop_front() { self.pending.remove(&o.creator); } self.dsh.drops.fetch_add(1, Ordering::Relaxed); }
        q.push_back(DJob { creator, sig, t });
    }
    /// a mint's dev age (h) and its source
    pub fn age(&self, mint: &Pk) -> (f32, u8) {
        let Some((c, t)) = self.creates.get(mint) else { return (f32::NAN, 0) };
        match self.dev.get(c) {
            Some(Dev::Oldest(bt)) => ((((t - bt) / 3600.0).max(0.0)) as f32, 1),
            Some(Dev::Capped) => (1e6, 2),
            Some(Dev::Err) => (f32::NAN, 3),
            None => (f32::NAN, if self.pending.contains(c) { 4 } else { 0 }),
        }
    }
    /// the mint's copy for a window (`on`: a T2 window with the rule configured)
    pub fn snap(&self, mint: &Pk, on: bool) -> RgSnap {
        let mut s = self.mints.get(mint).copied().unwrap_or_default();
        s.on = on;
        (s.age_h, s.src) = self.age(mint);
        s
    }
}
impl Drop for Rg49 { fn drop(&mut self) { self.dsh.stop.store(true, Ordering::Relaxed); } }

impl PsLive {
    fn rg_on(&self) -> bool { self.f47.cur.is_some_and(|v| v.rg.is_some()) }
    /// a T2 window's copy at its arm (default = off: re-arm / wide windows, the rule off)
    pub(super) fn rg49_snap(&self, mint: &Pk, t2: bool) -> RgSnap {
        match self.rg49.as_ref() { Some(r) if t2 && self.rg_on() => r.snap(mint, true), _ => RgSnap::default() }
    }
    /// creates (on_exec)
    pub(super) fn rg49_create(&mut self, mint: Pk, creator: Pk, sig: [u8; 64], t_rx: u64) {
        if let Some(r) = self.rg49.as_mut() { r.create(mint, creator, sig, t_rx as f64 / 1e9); }
    }
    /// the feed's fails and the workers' answers (tick): the mints' payers, the armed T2 windows' copies
    pub(super) fn rg49_drain(&mut self) {
        let Some(r) = self.rg49.as_mut() else { return };
        let mut touched: Vec<Pk> = Vec::new();
        let mut any = false;
        while let Ok(f) = r.fails.try_recv() {
            r.n_fails += 1; any = true;
            if f.payer == self.user { continue; }
            for k in &f.keys {
                if !self.det.followed(k) { continue; }
                r.n_matched += 1;
                r.mints.entry(*k).or_default().add(sig8(&f.payer), f.slot);
                if r.mints.len() > 50_000 { let lo = f.slot.saturating_sub(64); r.mints.retain(|_, s| s.e[..s.n as usize].iter().any(|x| x.last >= lo)); }
                if self.armed.contains_key(k) { touched.push(*k); }
            }
        }
        if any { self.sh.rg.last_fail.store(arbx::fast::mono_ns().max(1), Ordering::Relaxed); }
        let r = self.rg49.as_mut().unwrap();
        while let Ok((c, d)) = r.drx.try_recv() {
            r.pending.remove(&c);
            r.dev.insert(c, d);
            if r.dev.len() > DEV_CACHE { r.dev.clear(); }
            for (m, (cr, _)) in r.creates.iter() { if *cr == c && self.armed.contains_key(m) { touched.push(*m); } }
        }
        if touched.is_empty() || !self.rg_on() { return; }
        touched.sort(); touched.dedup();
        let snaps: Vec<(u64, RgSnap)> = touched.iter().filter_map(|m| { let id = *self.armed.get(m)?; (!self.rearm_w(id) && self.wd_win(id).is_none()).then(|| (id, self.rg49_snap(m, true))) }).collect();
        let mut g = self.sh.wins.lock().unwrap();
        for (id, s) in snaps { if let Some(w) = g.iter_mut().find(|w| w.id == id) { w.rg = s; } }
    }
    /// the fill (its try's verdict): the realized record's copy
    pub(super) fn rg49_fill(&mut self, w: u64, v: &RgV) {
        if let Some(r) = self.rg49.as_mut() {
            r.done.insert(w, serde_json::json!({"rivals": v.rivals, "dev_age_h": v.json()["dev_age_h"], "blocked": v.would}));
            if r.done.len() > 8192 { r.done.clear(); }
        }
    }
    pub(super) fn rg49_status(&self) -> String {
        self.rg49.as_ref().map_or(String::new(), |r| format!(" | RIVAL GATE fails {} matched {} mints {} | dev age cache {} pending {} calls {} errs {} | tap drops {}", r.n_fails,
            r.n_matched, r.mints.len(), r.dev.len(), r.pending.len(), r.dsh.calls.load(Ordering::Relaxed), r.dsh.errs.load(Ordering::Relaxed),
            arbx::feeds::RIVAL_TAP_DROPPED.load(Ordering::Relaxed)))
    }
}

/// RULE B: f1 (s4_feat.py) from a holder list (wallet, % of supply, holds on record) already limited to >= 2%, top 12: the <= 1-hold holders
/// but the excluded wallets (us, the dumper, the R5 holder), summed -> (pct, n)
pub fn f1_of<'a>(holders: impl Iterator<Item = (&'a Pk, f64, u8)>, excl: &[Pk]) -> (f64, usize) {
    let mut p = -0.0f64; let mut n = 0;
    for (w, pct, holds) in holders { if holds <= 1 && !excl.contains(w) { p += pct; n += 1; } }
    (p, n)
}
/// f1 on the detector's state now (the re-arm arm)
pub fn f1_fresh(det: &pl::Detector, mint: &Pk, user: &Pk, excl: &[Pk], slot: u64) -> (f64, usize) {
    let hc = det.holder_clocks(mint, (0.02 * pl::SUPPLY) as i64, user, slot, 12);
    f1_of(hc.iter().map(|h| (&h.w, h.bal as f64 / pl::SUPPLY * 100.0, h.n)), excl)
}

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
/// dip49b: the dev-age lookups' own RPC (`${VAR}` expanded from the env / .env; default: the funder log's setting; never printed)
pub const FLAG_RPC: &str = "--presend-live-devage-rpc";
/// dip49b: a failed lookup is asked again after these waits (then the age stays unknown; one more try at the T2 trigger)
pub const RETRY_S: [u64; 3] = [1, 3, 8];
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
/// dev_age_src: 1 the creator's history, 5 the create's fee PAYER's (the creator never signed: a platform launch), 6 both empty (age 0)
pub const SRC: [&str; 7] = ["none", "creator", "capped", "error", "pending", "payer", "empty0"];
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
    /// dip49b: per window the dev-age lookup's error text (the summary record's dev_age_err; read at the flush only)
    pub errs: Mutex<FxHashMap<u64, String>>,
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
    pub fn flush(&mut self, out: &crossbeam_channel::Sender<Out>, now: u64, all: bool) { self.flush_e(out, now, all, None) }
    pub fn flush_e(&mut self, out: &crossbeam_channel::Sender<Out>, now: u64, all: bool, sh: Option<&ShRg>) {
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
            let err = sh.and_then(|s| s.errs.lock().unwrap().remove(&k));
            if let Some(e) = &err { r["dev_age_err"] = e.clone().into(); }
            let _ = out.send(Out::Rec(r));
            let _ = out.send(Out::Line(format!("  PRESEND LIVE RIVAL GATE ({mode}) w{k} {}: tries {} | passed {} | withheld {} | would {} | open {}{} | rivals min {} | dev age {}", b58(&mint),
                c.iter().sum::<u32>(), c[0], c[1], c[2], c[3], if open.is_empty() { String::new() } else { format!(" ({open})") }, if rmin == u32::MAX { 0 } else { rmin },
                if age.is_finite() { format!("{age:.2} h") } else { SRC[src as usize].to_string() }) + &err.map(|e| format!(" ({e})")).unwrap_or_default()));
        }
    }
}

// ---- dev age lookups ----------------------------------------------------------------------------------------------------------

/// a creator's oldest tx before a create: Oldest(blockTime s; = the create's own time when the create was its first tx), Capped, Err
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum Dev { Oldest(f64, u8), Capped, Err }
#[derive(Clone, Debug)]
pub struct DJob { pub creator: Pk, pub sig: [u8; 64], pub t: f64, pub tries: u8, pub due: Option<Instant>,
    /// dip49c: the create tx's fee payer (= the creator on a normal launch) and whether an empty creator falls back to it
    pub payer: Pk, pub fallback: bool }
pub type Src<'a> = dyn Fn(&str, serde_json::Value) -> std::result::Result<serde_json::Value, String> + 'a;

/// one lookup -> (the answer, the error text (rpc-scrubbed) when it failed). dip49b: NO `before` (dip49's `before: <create sig>` failed on
/// every lookup in r87: the brand-new signature is not indexed yet at the create); the creator's newest 1000 signatures: 1000 = capped =
/// old; else the OLDEST entry's blockTime (the newest-first list's last; txs after the create only push nothing older) -> age = create time -
/// that, >= 0 (the create itself the oldest / only txs at or after the create: ~0 = brand new); an empty list (not indexed yet) or a
/// missing blockTime = an error (retried)
/// one address's history: Ok(None) = empty, Ok(Some(Capped | Oldest(bt))) or the error text
fn hist(src: &Src, a: &Pk, t: f64, tag: u8) -> std::result::Result<Option<Dev>, String> {
    let p = serde_json::json!([b58(a), {"limit": 1000, "commitment": "confirmed"}]);
    match src("getSignaturesForAddress", p) {
        Ok(v) => match v.as_array() {
            Some(x) if x.len() >= 1000 => Ok(Some(Dev::Capped)),
            Some(x) if x.is_empty() => Ok(None),
            Some(x) => x.last().and_then(|y| y["blockTime"].as_f64()).map(|bt| Some(Dev::Oldest(bt.min(t), tag))).ok_or_else(|| "no blockTime on the oldest signature".to_string()),
            None => Err(format!("not a list: {}", v.to_string().chars().take(120).collect::<String>())),
        },
        Err(e) => Err(rpc::scrub(&e).chars().take(200).collect()),
    }
}
/// dip49c: the creator's history first; EMPTY (r88: a launch platform's creator address never signs) and the create's payer differs -> the
/// PAYER's history (`fallback`); both empty -> after the retries: age 0 ("empty0", a brand-new address). Without the fallback an empty
/// creator stays an error (= unknown: the rugdet replay's treatment of creators with no history). Errors / empties are retried (dev_work)
pub fn dev_lookup(src: &Src, j: &DJob) -> (Dev, Option<String>) {
    match hist(src, &j.creator, j.t, 1) {
        Ok(Some(d)) => (d, None),
        Err(e) => (Dev::Err, Some(e)),
        Ok(None) if j.fallback && j.payer != j.creator => match hist(src, &j.payer, j.t, 5) {
            Ok(Some(d)) => (d, None),
            Err(e) => (Dev::Err, Some(format!("creator empty; payer: {e}"))),
            Ok(None) if (j.tries as usize) >= RETRY_S.len() => (Dev::Oldest(j.t, 6), None),
            Ok(None) => (Dev::Err, Some("creator and payer: empty signature lists (not indexed yet)".into())),
        },
        Ok(None) if j.fallback && (j.tries as usize) >= RETRY_S.len() => (Dev::Oldest(j.t, 6), None),
        Ok(None) => (Dev::Err, Some("empty signature list (creator never signed / not indexed yet)".into())),
    }
}

#[derive(Default)]
pub struct DevSh { pub q: Mutex<VecDeque<DJob>>, pub stop: AtomicBool, pub calls: AtomicU64, pub errs: AtomicU64, pub drops: AtomicU64, pub retries: AtomicU64, next: Mutex<Option<Instant>> }
/// one due job (a job not due yet goes to the back): looked up; a failure is queued again after RETRY_S (its last error sent only when
/// the retries are spent). `retry_scale`: the tests' 0 (no wait). -> false: nothing due
pub fn dev_work(sh: &DevSh, src: &Src, gap: Duration, tx: &crossbeam_channel::Sender<(Pk, Dev, Option<String>)>, retry_scale: f64) -> bool {
    let j = {
        let mut q = sh.q.lock().unwrap();
        let now = Instant::now();
        let Some(i) = q.iter().position(|j| j.due.is_none_or(|d| d <= now)) else { return false };
        q.remove(i).unwrap()
    };
    let wait = { let mut n = sh.next.lock().unwrap(); let now = Instant::now(); let at = n.map_or(now, |x| x.max(now)); *n = Some(at + gap); at - now };
    if !wait.is_zero() { std::thread::sleep(wait); }
    sh.calls.fetch_add(1, Ordering::Relaxed);
    let (d, err) = dev_lookup(src, &j);
    if d == Dev::Err {
        sh.errs.fetch_add(1, Ordering::Relaxed);
        if (j.tries as usize) < RETRY_S.len() {
            let w = Duration::from_secs_f64(RETRY_S[j.tries as usize] as f64 * retry_scale);
            sh.retries.fetch_add(1, Ordering::Relaxed);
            sh.q.lock().unwrap().push_back(DJob { tries: j.tries + 1, due: Some(Instant::now() + w), ..j });
            return true;
        }
    }
    let _ = tx.send((j.creator, d, err));
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
    /// dip49b: per creator its lookup's last error (rpc-scrubbed) and whether the T2 trigger's extra try was made
    pub dev_err: FxHashMap<Pk, String>,
    pub trig_retry: FxHashSet<Pk>,
    pending: FxHashSet<Pk>,
    /// per creator the create it was asked for (the T2 trigger's extra try)
    pub create_sig: FxHashMap<Pk, ([u8; 64], f64)>,
    /// dip49c: per creator the create's fee payer and the fallback setting
    pub payers: FxHashMap<Pk, (Pk, bool)>,
    pub dsh: Arc<DevSh>,
    drx: crossbeam_channel::Receiver<(Pk, Dev, Option<String>)>,
    dtx: crossbeam_channel::Sender<(Pk, Dev, Option<String>)>,
    /// per window its fill's verdict (the realized record's)
    pub done: FxHashMap<u64, serde_json::Value>,
    pub n_fails: u64, pub n_matched: u64,
    /// dip49c: the first successful lookup was announced
    pub first_ok: bool,
}
const DEV_Q: usize = 4096;
const DEV_CACHE: usize = 100_000;
impl Rg49 {
    fn base(fails: crossbeam_channel::Receiver<arbx::feeds::RivalFail>, test_tx: Option<crossbeam_channel::Sender<arbx::feeds::RivalFail>>) -> Rg49 {
        let (dtx, drx) = crossbeam_channel::unbounded();
        Rg49 { fails, test_tx, mints: FxHashMap::default(), creates: FxHashMap::default(), creates_q: VecDeque::new(), dev: FxHashMap::default(), dev_err: FxHashMap::default(),
            trig_retry: FxHashSet::default(), create_sig: FxHashMap::default(), payers: FxHashMap::default(), pending: FxHashSet::default(),
            dsh: Arc::new(DevSh::default()), drx, dtx, done: FxHashMap::default(), n_fails: 0, n_matched: 0, first_ok: false }
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
                    while !sh.stop.load(Ordering::Relaxed) { if !dev_work(&sh, &src, gap, &tx, 1.0) { std::thread::sleep(Duration::from_millis(5)); } }
                });
            }
        }
        Some(r)
    }
    pub fn pump(&mut self, src: &Src) { while dev_work(&self.dsh, src, Duration::ZERO, &self.dtx, 0.0) {} }
    /// a create of a followed token: its creator's age looked up once (queued; never waited for)
    pub fn create(&mut self, mint: Pk, creator: Pk, sig: [u8; 64], t: f64) {
        self.create_p(mint, creator, creator, sig, t, false);
    }
    /// dip49c: with the create's fee payer and the payer fallback
    pub fn create_p(&mut self, mint: Pk, creator: Pk, payer: Pk, sig: [u8; 64], t: f64, fallback: bool) {
        self.creates.insert(mint, (creator, t));
        self.creates_q.push_back(mint);
        while self.creates_q.len() > 200_000 { if let Some(o) = self.creates_q.pop_front() { self.creates.remove(&o); self.mints.remove(&o); } }
        if self.create_sig.len() > 200_000 { self.create_sig.clear(); }
        self.create_sig.insert(creator, (sig, t));
        if self.dev.contains_key(&creator) || !self.pending.insert(creator) { return; }
        self.payers.insert(creator, (payer, fallback));
        if self.payers.len() > 200_000 { self.payers.clear(); }
        self.queue(DJob { creator, sig, t, tries: 0, due: None, payer, fallback });
    }
    fn queue(&mut self, j: DJob) {
        let mut q = self.dsh.q.lock().unwrap();
        if q.len() >= DEV_Q { if let Some(o) = q.pop_front() { self.pending.remove(&o.creator); } self.dsh.drops.fetch_add(1, Ordering::Relaxed); }
        q.push_back(j);
    }
    /// dip49b: at a T2 trigger: a creator whose lookup FAILED gets one more lookup (once)
    pub fn trigger(&mut self, mint: &Pk) {
        let Some((c, t)) = self.creates.get(mint).copied() else { return };
        if self.dev.get(&c) != Some(&Dev::Err) || !self.trig_retry.insert(c) || !self.pending.insert(c) { return; }
        let sig = self.create_sig.get(&c).map_or([0u8; 64], |x| x.0);
        let (payer, fallback) = self.payers.get(&c).copied().unwrap_or((c, false));
        self.dev.remove(&c);
        self.queue(DJob { creator: c, sig, t, tries: RETRY_S.len() as u8, due: None, payer, fallback });
    }
    /// the workers' answers into the cache (tests; the engine drains in rg49_drain)
    pub fn drain_dev(&mut self) -> Vec<Pk> {
        let mut v = Vec::new();
        while let Ok((c, d, e)) = self.drx.try_recv() { self.pending.remove(&c); self.dev.insert(c, d); if let Some(e) = e { self.dev_err.insert(c, e); } v.push(c); }
        v
    }
    /// the creator's last lookup error of a mint
    pub fn err_of(&self, mint: &Pk) -> Option<&String> { self.creates.get(mint).and_then(|(c, _)| self.dev_err.get(c)) }
    /// a mint's dev age (h) and its source
    pub fn age(&self, mint: &Pk) -> (f32, u8) {
        let Some((c, t)) = self.creates.get(mint) else { return (f32::NAN, 0) };
        match self.dev.get(c) {
            Some(Dev::Oldest(bt, src)) => ((((t - bt) / 3600.0).max(0.0)) as f32, *src),
            Some(Dev::Capped) => (1e6, 2),
            Some(Dev::Err) => (f32::NAN, 3),
            None => (f32::NAN, if self.pending.contains(c) { 4 } else { 0 }),
        }
    }
    /// dip49b: the sender's summary's error text per window (set at the T2 arm / when a lookup fails)
    pub fn note_err(sh: &ShRg, w: u64, e: &str) { let mut g = sh.errs.lock().unwrap(); if g.len() > 4096 { g.clear(); } g.insert(w, e.to_string()); }
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
        let mut errs: Vec<(Pk, String)> = Vec::new();
        let mut first: Option<(Pk, Dev)> = None;
        while let Ok((c, d, e)) = r.drx.try_recv() {
            r.pending.remove(&c);
            r.dev.insert(c, d);
            if !r.first_ok && d != Dev::Err { r.first_ok = true; first = Some((c, d)); }
            match e { Some(e) => { r.dev_err.insert(c, e.clone()); errs.push((c, e)); } None => { r.dev_err.remove(&c); } }
            if r.dev_err.len() > DEV_CACHE { r.dev_err.clear(); }
            if r.dev.len() > DEV_CACHE { r.dev.clear(); }
            for (m, (cr, _)) in r.creates.iter() { if *cr == c && self.armed.contains_key(m) { touched.push(*m); } }
        }
        // dip49c: the run's first successful lookup (verify within a minute of the start)
        if let Some((c, d)) = first {
            let ct = self.rg49.as_ref().and_then(|r| r.creates.values().find(|x| x.0 == c).map(|x| x.1)).unwrap_or(0.0);
            let (age, src) = match d { Dev::Oldest(bt, s) => (format!("{:.3} h", ((ct - bt) / 3600.0).max(0.0)), SRC[s as usize]), Dev::Capped => ("capped (old)".into(), "capped"), Dev::Err => ("-".into(), "error") };
            self.line(format!("  DEVAGE OK first lookup src={src} age={age} creator {}", &b58(&c)[..8]));
            self.rec(serde_json::json!({"ev": "presend_live_devage", "ok": true, "first": true, "creator": b58(&c), "src": src, "t": arbx::feeds::clock::now_ns()}));
        }
        // dip49b: a lookup that failed for good (retries spent): its error, recorded once per creator
        for (c, e) in errs {
            self.rec(serde_json::json!({"ev": "presend_live_devage", "creator": b58(&c), "ok": false, "dev_age_err": e, "t": arbx::feeds::clock::now_ns()}));
            self.line(format!("  PRESEND LIVE DEV AGE error {}: {e}", &b58(&c)[..8]));
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

// ---- dip49c: the production lookup path, standalone (--devage-selftest FILE) --------------------------------------------------------

/// the URL's host only (the key / path never printed)
pub fn url_host(u: &str) -> String { u.split("://").nth(1).unwrap_or(u).split(['/', '?', '@']).next().unwrap_or("").to_string() }

/// `snipe_engine --devage-selftest FILE [--presend-live-devage-rpc URL] [--presend-live-funder-rps N] [--presend-live-devage-fallback payer|none]`:
/// the EXACT production dev-age path (Rg49::start: the same workers, RPC client, pacing, retries 1 / 3 / 8 s, creator -> payer fallback,
/// `${VAR}` expansion after the engine's .env load) on rows {mint, creator, payer, create_sig | sig, create_bt | bt} (one JSON per line).
/// No wallet, keystore, feed or send. One line per row, then a summary; exits when every row is answered (or after the deadline)
pub fn selftest(file: &str, url: Option<String>, rps: u32, fallback: bool) -> Result<()> {
    let raw = url.context("--devage-selftest needs --presend-live-devage-rpc URL (${VAR} expanded from the .env)")?;
    let url = config::expand(&raw).context("--presend-live-devage-rpc: a ${VAR} in it is empty / missing (is the .env loaded? --env-file)")?;
    println!("DEVAGE SELFTEST rpc host {} | rps {rps} | fallback {} | retries after {:?} s", url_host(&url), if fallback { "payer" } else { "none" }, RETRY_S);
    let pk = |s: &str| -> Option<Pk> { bs58::decode(s).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok()) };
    let mut rows: Vec<(Pk, Pk, Pk, [u8; 64], f64, String)> = Vec::new();
    for (k, l) in std::fs::read_to_string(file).with_context(|| format!("read {file}"))?.lines().enumerate() {
        if l.trim().is_empty() { continue; }
        let v: serde_json::Value = serde_json::from_str(l).with_context(|| format!("{file}:{}: not JSON", k + 1))?;
        let g = |a: &str, b: &str| v.get(a).or_else(|| v.get(b)).cloned().unwrap_or(serde_json::Value::Null);
        let (Some(m), Some(c)) = (v["mint"].as_str().and_then(pk), v["creator"].as_str().and_then(pk)) else { println!("row {}: no mint / creator: skipped", k + 1); continue };
        let p = v["payer"].as_str().and_then(pk).or_else(|| v["user"].as_str().and_then(pk)).unwrap_or(c);
        let sig: [u8; 64] = g("create_sig", "sig").as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|x| x.try_into().ok()).unwrap_or([0u8; 64]);
        let bt = g("create_bt", "bt").as_f64().unwrap_or_else(|| std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map_or(0.0, |d| d.as_secs_f64()));
        rows.push((m, c, p, sig, bt, v["mint"].as_str().unwrap_or("").chars().take(8).collect()));
    }
    let Some(mut r) = Rg49::start(Some(url), rps) else { bail!("the dev-age workers did not start") };
    let t0 = Instant::now();
    let mut asked: FxHashMap<Pk, Instant> = FxHashMap::default();
    for (m, c, p, sig, bt, _) in &rows { asked.entry(*c).or_insert_with(Instant::now); r.create_p(*m, *c, *p, *sig, *bt, fallback); }
    let mut got: FxHashMap<Pk, f64> = FxHashMap::default();
    let deadline = Duration::from_secs_f64(30.0 + RETRY_S.iter().sum::<u64>() as f64 + asked.len() as f64 * 3.0 / rps.max(1) as f64);
    while got.len() < asked.len() && t0.elapsed() < deadline {
        for c in r.drain_dev() { got.entry(c).or_insert_with(|| asked.get(&c).map_or(0.0, |a| a.elapsed().as_secs_f64() * 1e3)); }
        std::thread::sleep(Duration::from_millis(20));
    }
    let mut by: std::collections::BTreeMap<&str, usize> = Default::default();
    let mut errs: std::collections::BTreeMap<String, usize> = Default::default();
    for (m, c, p, _, _, ms) in &rows {
        let (age, src) = r.age(m);
        let s = if got.contains_key(c) { SRC[src as usize] } else { "timeout" };
        *by.entry(s).or_default() += 1;
        let e = r.dev_err.get(c).cloned().unwrap_or_default();
        if !e.is_empty() { *errs.entry(e.chars().take(80).collect()).or_default() += 1; }
        println!("{ms} creator {} payer {}{} | age_h {} | src {s} | {} ms{}", &b58(c)[..8], &b58(p)[..8], if c == p { " (=creator)" } else { "" },
            if age.is_finite() { format!("{age:.3}") } else { "-".into() }, got.get(c).map_or("-".into(), |x| format!("{x:.0}")), if e.is_empty() { String::new() } else { format!(" | err {e}") });
    }
    let n = rows.len().max(1);
    let ok = by.iter().filter(|(k, _)| matches!(**k, "creator" | "payer" | "empty0" | "capped")).map(|(_, v)| *v).sum::<usize>();
    println!("DEVAGE SELFTEST SUMMARY: {} rows, {} creators | resolved {ok} ({:.1}%) | {} | calls {} errs {} retries {} | {:.1} s",
        rows.len(), asked.len(), ok as f64 * 100.0 / n as f64,
        by.iter().map(|(k, v)| format!("{k} {v} ({:.0}%)", *v as f64 * 100.0 / n as f64)).collect::<Vec<_>>().join(", "),
        r.dsh.calls.load(Ordering::Relaxed), r.dsh.errs.load(Ordering::Relaxed), r.dsh.retries.load(Ordering::Relaxed), t0.elapsed().as_secs_f64());
    for (e, k) in &errs { println!("  error x{k}: {e}"); }
    Ok(())
}

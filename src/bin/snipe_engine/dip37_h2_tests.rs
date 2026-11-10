// ===================================================================================================================
// dip37 HYBRID-2 inputs tests (psh2.rs: --presend-live-m2seen-log on|off, --presend-live-m2seen-gate on|off). nd / m2max in CHAIN order
// (slot, in-block index), strictly before the trigger (same-slot dumps before / after the trigger's index; the re-arm's own dump never
// counted); h2_keep / h2_size; the gate's skips; off = the same decisions and records; dipmode's dump-record hook.
// ===================================================================================================================
use super::*;
use super::psh2::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;
/// the tests that run a probe with the counter on (its on_exec drains the process-wide note queue) and the hook's test: one at a time
pub(super) static H2_TESTS: std::sync::Mutex<()> = std::sync::Mutex::new(());

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn pct(x: f64) -> u64 { (x / 100.0 * pl::SUPPLY) as u64 }
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x42; x }

struct Tk { mint: Pk, v: u64, t: u64, launch: Launch }
impl Tk {
    fn new(k: u8) -> Tk { let mint = [k; 32]; Tk { mint, v: 30 * S, t: 1_073_000_000_000_000, launch: snipe_build::launch_from_target(mint, CREATOR) } }
    fn buy(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v + sol) as u128) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn buy_tok(&mut self, user: Pk, q: u64) -> TradeEvent {
        let sol = ((self.v as u128 * q as u128).div_ceil((self.t - q) as u128)) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn sell_tok(&mut self, user: Pk, q: u64) -> TradeEvent {
        let sol = (self.v as u128 * q as u128 / (self.t + q) as u128) as u64;
        self.v -= sol; self.t += q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: false, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn create(&self) -> CreateEvent { CreateEvent { mint: self.mint, bonding_curve: self.launch.bonding_curve, user: CREATOR, creator: CREATOR } }
}

struct Ctx { p: PsLive, orx: crossbeam_channel::Receiver<Out>, launches: Vec<Launch>, recs: Vec<serde_json::Value> }
impl Ctx {
    fn new(extra: &[&str]) -> Ctx { let (p, _a, orx) = PsLive::for_test(cfg(extra).unwrap().unwrap(), USER); Ctx { p, orx, launches: Vec::new(), recs: Vec::new() } }
    fn tx(&mut self, slot: u64, idx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0x42; sig[17] = trades.first().map_or(0, |t| t.mint[0]);
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![[0x77; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let ls = self.launches.clone();
        self.p.on_arrival(&a, slot);
        self.p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
        for o in self.orx.try_iter() { if let Out::Rec(v) = o { self.recs.push(v); } }
    }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    fn note(&mut self, mint: Pk, s: u64, i: u32, m2: Option<f64>) { if let Some(h) = self.p.h2.as_mut() { h.note(mint, s, i, m2); } }
    /// T2 on token 0x61 created at `s0`; `dumps` scored (slot offset, idx, m2) noted before the trigger tx; the whale's buy at s0 + age, idx 50
    fn t2(&mut self, s0: u64, age: u64, dumps: &[(u64, u32, Option<f64>)]) -> Tk {
        let mut tk = Tk::new(0x61);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(s0, 1, vec![dev], vec![tk.create()]);
        let e = tk.buy(w(0x11), S / 10);
        self.tx(s0 + 1, 2, vec![e], vec![]);
        for &(ds, di, m) in dumps { self.note(tk.mint, s0 + ds, di, m); }
        let e = tk.buy(w(0xEE), 2 * S);
        self.tx(s0 + age, 50, vec![e], vec![]);
        tk
    }
    /// re-arm: a 7% / b 8% at 1000, a dumps at (1005, 5) (noted as scored, as dipmode would), the check at 1008; `earlier`: a scored dump
    /// noted at (1003, 9) too
    fn rearm(&mut self, earlier: bool) -> Tk {
        let (a, b) = (w(0xA1), w(0xB1));
        let mut tk = Tk::new(0x62);
        let mut z = Tk::new(0x63);
        self.launches.push(tk.launch.clone());
        self.launches.push(z.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, vec![dev], vec![tk.create()]);
        let e = tk.buy_tok(a, pct(7.0)); self.tx(1000, 2, vec![e], vec![]);
        let e = tk.buy_tok(b, pct(8.0)); self.tx(1000, 3, vec![e], vec![]);
        let dz = z.buy(CREATOR, S / 2);
        self.tx(1000, 4, vec![dz], vec![z.create()]);
        for s in 1001..=1004 { let e = tk.buy(w(0x33), S / 10); self.tx(s, 5, vec![e], vec![]); }
        if earlier { self.note(tk.mint, 1003, 9, Some(-0.05)); }
        self.note(tk.mint, 1005, 5, Some(0.03));        // the re-arm's own dump, scored in its own tx
        let d = tk.sell_tok(a, pct(7.0));
        self.tx(1005, 5, vec![d], vec![]);
        for s in 1006..=1008 { let e = z.buy(w(0x2F), 1_000_000); self.tx(s, 900, vec![e], vec![]); }
        tk
    }
}

/// chain order, strictly before; arrival order free; a dump without an M2 score counts -1; the fold keeps count and max
#[test]
fn dip37_h2_nd_chain_order() {
    let mut h = H2::default();
    let m = [1u8; 32];
    assert_eq!(h.view(&m, 100, 9), (0, -1.0), "nothing noted");
    h.note(m, 101, 2, Some(0.5));
    h.note(m, 100, 9, Some(0.2));      // the trigger's own position
    h.note(m, 99, 1, None);
    h.note(m, 100, 5, Some(-0.03));
    assert_eq!(h.view(&m, 100, 9), (2, -0.03), "(99,1) and (100,5): same-slot before the index counts, the trigger's own position does not");
    assert_eq!(h.view(&m, 100, 10), (3, 0.2), "same slot after the index");
    assert_eq!(h.view(&m, 100, 4), (1, -1.0), "the unscored one: -1");
    assert_eq!(h.view(&m, 102, 0), (4, 0.5));
    assert_eq!(h.view(&[2u8; 32], 102, 0), (0, -1.0), "another mint");
    // the fold: more than MAX_PER_MINT dumps; the oldest folded into (count, max), every later trigger still sees them
    let mut h = H2::default();
    for k in 0..(MAX_PER_MINT as u64 + 10) { h.note(m, 10 + k, 0, Some(if k == 0 { 0.9 } else { -0.5 })); }
    assert_eq!(h.view(&m, 100_000, 0), (MAX_PER_MINT as u32 + 10, 0.9));
    assert_eq!(h.view(&m, 200, 0).0, 190, "the folded ones count for every later trigger (arrival is chain order: none comes earlier)");
    // prune: mints the detector does not follow go
    let mut d = pl::Detector::new(5.0);
    d.create([3u8; 32], 5, CREATOR, CREATOR, false);
    let mut h = H2::default();
    h.note([3u8; 32], 6, 0, None); h.note([4u8; 32], 6, 0, None);
    h.prune(&d, 5_000);
    assert!(h.map.contains_key(&[3u8; 32]) && !h.map.contains_key(&[4u8; 32]));
}

/// h2_keep / h2_size
#[test]
fn dip37_h2_fields() {
    let f = |nd, mx, re, age, size| { let mut r = serde_json::json!({}); fields(&mut r, nd, mx, re, age, size); r };
    let r = f(1, -0.02, false, 30, 400_000_000);
    assert!(r["nd"] == 1 && r["m2max"] == -0.02 && r["h2_keep"] == true && r["h2_size"] == 1.0, "{r}");
    assert!(f(1, -0.0201, false, 30, 400_000_000)["h2_size"] == 0.4 && f(1, 0.1, false, 29, 400_000_000)["h2_keep"] == false);
    assert!(f(0, -1.0, true, 0, 650_000_000)["h2_keep"] == false && f(1, -1.0, true, 0, 650_000_000)["h2_keep"] == true && f(1, -1.0, true, 0, 650_000_000)["h2_size"] == 0.65);
}

/// T2 on the probe: same-slot dumps before / after the trigger index; the fields on the arm; age < 30 -> h2_keep false
#[test]
fn dip37_h2_t2_probe() {
    let _g = H2_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let mut c = Ctx::new(&["--presend-live-m2seen-log", "on"]);
    // trigger at (1040, 50): dumps (1040, 10) before, (1040, 60) after (same slot), (1003, 4) earlier
    c.t2(1000, 40, &[(3, 4, Some(-0.05)), (40, 10, Some(0.01)), (40, 60, Some(0.5))]);
    let a = c.ev("presend_live_arm").pop().expect("armed: the log never skips");
    assert!(a["nd"] == 2 && a["m2max"] == 0.01 && a["h2_keep"] == true && a["h2_size"] == 1.0, "{a}");
    let mut c = Ctx::new(&["--presend-live-m2seen-log", "on"]);
    c.t2(1000, 5, &[(3, 4, Some(-0.05))]);
    let a = c.ev("presend_live_arm").pop().unwrap();
    assert!(a["nd"] == 1 && a["h2_keep"] == false && a["h2_size"] == 0.4, "T2 age 5 < 30: {a}");
    // a skip record (create-slot... here: the token too young for --presend-live-min-age-slots) carries them too
    let mut c = Ctx::new(&["--presend-live-m2seen-log", "on", "--presend-live-min-age-slots", "10"]);
    c.t2(1000, 5, &[]);
    let s = c.ev("presend_live_skip").pop().unwrap();
    assert!(s["why"] == "young_age" && s["nd"] == 0 && s["m2max"] == -1.0 && s["h2_keep"] == false, "{s}");
}

/// re-arm: its own dump (the trigger position) is never counted; an earlier scored dump is
#[test]
fn dip37_h2_rearm_own_dump_excluded() {
    let _g = H2_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-m2seen-log", "on"]);
    c.rearm(false);
    let a = c.ev("presend_live_arm").into_iter().find(|r| r["kind"] == "rearm").expect("armed");
    assert!(a["nd"] == 0 && a["m2max"] == -1.0 && a["h2_keep"] == false, "the own dump excluded: {a}");
    let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-m2seen-log", "on"]);
    c.rearm(true);
    let a = c.ev("presend_live_arm").into_iter().find(|r| r["kind"] == "rearm").unwrap();
    assert!(a["nd"] == 1 && a["m2max"] == -0.05 && a["h2_keep"] == true && a["h2_size"] == 0.4, "{a}");
}

/// the gate: nd = 0 -> "m2_unseen" (T2) / "rearm_m2_unseen" (re-arm); nd >= 1 -> armed
#[test]
fn dip37_h2_gate() {
    let _g = H2_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let mut c = Ctx::new(&["--presend-live-m2seen-gate", "on"]);
    c.t2(1000, 40, &[(40, 60, Some(0.5))]);
    let s = c.ev("presend_live_skip").pop().expect("skipped: the only dump is after the trigger");
    assert!(s["why"] == "m2_unseen" && s["nd"] == 0 && c.ev("presend_live_arm").is_empty(), "{s}");
    let mut c = Ctx::new(&["--presend-live-m2seen-gate", "on"]);
    c.t2(1000, 40, &[(40, 49, None)]);
    assert!(c.ev("presend_live_arm").len() == 1 && c.ev("presend_live_skip").is_empty());
    let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-m2seen-gate", "on"]);
    c.rearm(false);
    let s = c.ev("presend_live_skip").into_iter().find(|r| r["why"] == "rearm_m2_unseen").expect("re-arm skipped");
    assert!(s["kind"] == "rearm" && s["nd"] == 0);
    let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-m2seen-gate", "on"]);
    c.rearm(true);
    assert!(c.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm"));
}

/// off: no field, the same decisions and records as with the log on minus its fields; the flags; dipmode's hook
#[test]
fn dip37_h2_off_flags_and_hook() {
    let _g = H2_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(!c0.m2seen_on() && c0.json().get("m2seen").is_none());
    let mut a = Ctx::new(&["--presend-live-rearm", "on"]);
    a.rearm(true);
    a.t2(2000, 40, &[]);
    assert!(a.p.h2.is_none() && a.recs.iter().all(|r| r.get("nd").is_none() && r.get("h2_keep").is_none()));
    let mut b = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-m2seen-log", "on"]);
    b.rearm(true);
    b.t2(2000, 40, &[]);
    let mut rb = b.recs.clone();
    for r in rb.iter_mut() { if let Some(o) = r.as_object_mut() { for k in ["nd", "m2max", "h2_keep", "h2_size"] { o.remove(k); } } }
    // the wall-clock fields of a disarm (armed_ms, t) differ run to run
    let s = |v: &[serde_json::Value]| v.iter().map(|r| { let mut r = r.clone(); if r["ev"] == "presend_live_disarm" { if let Some(o) = r.as_object_mut() { o.remove("armed_ms"); o.remove("t"); } } r.to_string() }).collect::<Vec<_>>();
    assert_eq!(s(&rb), s(&a.recs), "log only: the same records but its fields");
    assert!(b.recs.iter().filter(|r| r["ev"] == "presend_live_arm").all(|r| r.get("nd").is_some()));
    // the flags
    assert!(cfg(&["--presend-live-m2seen-log", "yes"]).unwrap_err().to_string().contains("on | off"));
    let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", "--presend-live-m2seen-gate", "on"].iter().map(|s| s.to_string()).collect::<Vec<_>>(),
        &arbx::presend::Params::default(), true, 1_000_000_000).unwrap_err().to_string();
    assert!(e.contains("needs --presend-live"), "{e}");
    assert!(crate::check_flags(&args(&["--presend-live-m2seen-log", "on", "--presend-live-m2seen-gate", "off"])).is_ok());
    assert!(cfg(&["--presend-live-m2seen-gate", "on"]).unwrap().unwrap().json()["m2seen"]["gate"] == true);
    // dipmode's hook: nothing while no run turned it on; a dump record's (mint, slot, idx) and score once on
    let mint = [0x4Bu8; 32];
    let rec = serde_json::json!({"ev": "dump", "mint": b58(&mint), "slot": 777u64, "idx": 12u64});
    M2SEEN.store(false, Ordering::SeqCst);
    note_rec(&rec, Some(0.2));
    let mut h = H2::default();
    h.drain();
    assert_eq!(h.view(&mint, 778, 0), (0, -1.0));
    M2SEEN.store(true, Ordering::SeqCst);
    note_rec(&rec, Some(0.2));
    note_rec(&serde_json::json!({"ev": "dump", "mint": "bad", "slot": 1, "idx": 1}), None);
    M2SEEN.store(false, Ordering::SeqCst);
    h.drain();
    assert_eq!((h.view(&mint, 777, 12), h.view(&mint, 777, 13)), ((0, -1.0), (1, 0.2)));
}

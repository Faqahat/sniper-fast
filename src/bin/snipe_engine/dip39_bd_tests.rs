// ===================================================================================================================
// dip39 BOT DEPTH gate tests (psbd.rs: --presend-live-botdepth MIN:SLOTS, --presend-live-botdepth-list PATH, --presend-live-botdepth-mode
// log|live, the ledger control file's "botdepth"). The depth counter (window pruning, distinct wallets, the MIN boundary, fail open); the
// list formats; the flags; the probe end to end: the window's copy kept fresh by listed trades, the sender's check withholding (live) or
// counting (log), the arm / skip / fill records, the reload, the control file, the status and run_end; log mode changes nothing else.
// ===================================================================================================================
use super::*;
use super::psbd::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000) }
fn pctr(x: f64) -> u64 { (x / 100.0 * pl::SUPPLY).round() as u64 }
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x39; x }
fn tmp(name: &str) -> String { std::env::temp_dir().join(format!("dip39-bd-{}-{name}", std::process::id())).to_string_lossy().to_string() }
/// a list file: the registry format (reg) or a plain array
fn list(name: &str, ws: &[Pk], reg: bool) -> String {
    let p = tmp(name);
    let j = if reg { serde_json::json!({"version": 7, "wallets": ws.iter().map(|k| serde_json::json!({"wallet": b58(k), "state": "active"})).collect::<Vec<_>>()}) }
            else { serde_json::json!(ws.iter().map(b58).collect::<Vec<_>>()) };
    std::fs::write(&p, j.to_string()).unwrap();
    p
}
fn sl(s: &[u64]) -> Slots { Slots::from_iter(s.iter().copied()) }
fn snap(s: &[u64]) -> Snap { Snap { a: sl(s), b: Slots::default(), warm: true } }
fn lg(min: u32, slots: u64) -> Gate { Gate::List { min, slots } }

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

struct Ctx { p: PsLive, atx: crossbeam_channel::Sender<Att>, orx: crossbeam_channel::Receiver<Out>, launches: Vec<Launch>, recs: Vec<serde_json::Value>, lines: Vec<String> }
impl Ctx {
    fn new(extra: &[&str]) -> Ctx {
        let (p, atx, orx) = PsLive::for_test(cfg(extra).unwrap().unwrap(), USER);
        Ctx { p, atx, orx, launches: Vec::new(), recs: Vec::new(), lines: Vec::new() }
    }
    fn pump(&mut self) { for o in self.orx.try_iter() { match o { Out::Rec(v) => self.recs.push(v), Out::Line(l) => self.lines.push(l) } } }
    fn tx_sig(&mut self, slot: u64, idx: u64, sig: [u8; 64], trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![[0x77; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let ls = self.launches.clone();
        self.p.on_arrival(&a, slot);
        self.p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
        self.pump();
    }
    fn tx(&mut self, slot: u64, idx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0x39; sig[17] = trades.first().map_or(0, |t| t.mint[0]);
        self.tx_sig(slot, idx, sig, trades, creates);
    }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    fn swin(&self, mint: &Pk) -> SWin { let id = *self.p.armed.get(mint).unwrap_or_else(|| panic!("not armed: {:?}", self.recs.iter().filter(|r| r["ev"].as_str().is_some_and(|e| e.contains("skip") || e.contains("arm"))).collect::<Vec<_>>())); self.p.sh.wins.lock().unwrap().iter().find(|w| w.id == id).cloned().unwrap() }
    /// the sender's check of the armed window of `mint` at `slot`
    fn check(&self, mint: &Pk, slot: u64) -> BdV {
        let g = self.p.cfg.bd.unwrap();
        let sw = self.swin(mint);
        check(&self.p.sh.bd, &g, sw.bd.as_ref(), slot, sw.rearm)
    }
    /// T2 on token 0x71 created at 1000; `bots` (wallet, slot) trade it before the trigger; the whale's 8% at 1010 (the trigger)
    fn t2(&mut self, bots: &[(Pk, u64)], whale: Pk) -> Tk {
        let mut tk = Tk::new(0x71);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, vec![dev], vec![tk.create()]);
        for (i, (b, s)) in bots.iter().enumerate() { let e = tk.buy(*b, S / 20); self.tx(*s, 10 + i as u64, vec![e], vec![]); }
        let e = tk.buy_tok(whale, pctr(8.0));
        self.tx(1010, 50, vec![e], vec![]);
        tk
    }
}

// ---- the pure parts --------------------------------------------------------------------------------------------------------------

#[test]
fn dip39_bd_spec_and_list() {
    assert_eq!(spec_parse("3:100").unwrap(), (3, 100));
    assert_eq!(spec_parse(" 1 : 1 ").unwrap(), (1, 1));
    assert_eq!(spec_parse("16:2000").unwrap(), (16, 2000));
    for bad in ["0:100", "17:100", "3:0", "3:2001", "3", "x:1", "3:-1", ""] { assert!(spec_parse(bad).is_err(), "{bad}"); }
    assert!(!mode_parse("log").unwrap() && mode_parse("live").unwrap() && mode_parse("on").is_err());
    // both formats; our wallet left out; "w" accepted; bad entries / empty refused
    let (a, b) = (w(1), w(2));
    let reg = format!(r#"{{"wallets": [{{"wallet": "{}"}}, {{"w": "{}"}}, {{"wallet": "{}"}}]}}"#, b58(&a), b58(&b), b58(&USER));
    let s = list_parse(reg.as_bytes(), &USER).unwrap();
    assert!(s.len() == 2 && s.contains(&a) && s.contains(&b) && !s.contains(&USER));
    let arr = format!(r#"["{}", "{}", "{}"]"#, b58(&a), b58(&a), b58(&b));
    assert_eq!(list_parse(arr.as_bytes(), &USER).unwrap().len(), 2, "duplicates once");
    assert!(list_parse(b"[]", &USER).is_err(), "empty: refused (it would withhold everything)");
    assert!(list_parse(format!(r#"["{}"]"#, b58(&USER)).as_bytes(), &USER).is_err(), "only ours: empty");
    assert!(list_parse(br#"["notbase58!!"]"#, &USER).is_err());
    assert!(list_parse(br#"{"x": 1}"#, &USER).is_err());
    assert!(list_parse(b"nope", &USER).is_err());
}

/// the window's copy: slots >= slot - SLOTS count (the window's lower edge included), older ones not; a slot past the clock counts (seen)
#[test]
fn dip39_bd_depth_window() {
    let s = sl(&[1000, 1100, 999, 1050]);
    assert_eq!(s.s[..4], [1100, 1050, 1000, 999], "newest first");
    assert_eq!(s.count(1100, 100), 3, "1000 is the edge: counted; 999 out");
    assert_eq!(s.count(1101, 100), 2, "one slot later the edge moves past 1000");
    assert_eq!(s.count(1200, 100), 1);
    assert_eq!(s.count(1201, 100), 0);
    assert_eq!(s.count(1099, 100), 4, "a trade seen at 1100 with the clock at 1099 still counts");
    assert_eq!(Slots::default().count(1000, 100), 0);
    // the book: distinct wallets (a wallet's repeat trades count once; its LATEST slot kept), exact depth, the copy newest first, prune
    let mut b = Book::default();
    let m = [9u8; 32];
    b.add(m, w(1), 900); b.add(m, w(1), 1000); b.add(m, w(1), 950);
    b.add(m, w(2), 1050);
    b.add([8u8; 32], w(3), 1050);
    assert_eq!(b.depth(&m, 1050, 100), 2, "w1 (latest 1000) + w2");
    assert_eq!(b.depth(&m, 1101, 100), 1, "w1 out of the window");
    assert_eq!(b.depth(&m, 1040, 100), 1, "no look-ahead: w2's 1050 is after 1040");
    assert_eq!(b.snap(&m), sl(&[1050, 1000]));
    b.prune(1101, 100);
    assert_eq!((b.depth(&m, 1101, 100), b.mints()), (1, 2), "w1 pruned, w2 + the other mint stay");
    b.prune(1151, 100);
    assert_eq!(b.mints(), 0, "empty mints leave");
    // the copy caps at BD_K: the newest kept
    let mut b = Book::default();
    for i in 0..(BD_K as u64 + 4) { b.add(m, w(10 + i as u8), 1000 + i); }
    let s = b.snap(&m);
    assert!(s.n as usize == BD_K && s.s[0] == 1000 + BD_K as u64 + 3 && s.s[BD_K - 1] == 1004, "{s:?}");
    assert_eq!(b.depth(&m, 1020, 100), BD_K as u32 + 4, "the book's own count is exact");
}

/// the MIN boundary, live vs log, the counts, fail open, the record limiter
#[test]
fn dip39_bd_check_boundary_and_fail_open() {
    let bs = BdShared::default();
    let s = snap(&[1000, 990, 950]);
    // live: depth 3 at MIN 3 passes, at MIN 4 blocks (withheld)
    bs.live.store(true, Ordering::SeqCst);
    let v = check(&bs, &lg(3, 100), Some(&s), 1000, false);
    assert!(v == BdV { n: 3, q: 0, block: false, raw: false, live: true, ok: true } && !v.withhold());
    let v = check(&bs, &lg(4, 100), Some(&s), 1000, false);
    assert!(v.block && v.withhold() && v.n == 3);
    // one slot later 950 is out (lo 951): depth 2 < 3 -> withheld (re-arm counted apart)
    let v = check(&bs, &lg(3, 49), Some(&s), 1000, true);
    assert!(v.n == 2 && v.withhold());
    // log: blocked but never withheld
    bs.live.store(false, Ordering::SeqCst);
    let v = check(&bs, &lg(4, 100), Some(&s), 1000, false);
    assert!(v.block && !v.withhold());
    // no list: fail open (never withheld, live or not)
    bs.live.store(true, Ordering::SeqCst);
    let v = check(&bs, &lg(3, 100), None, 1000, false);
    assert!(!v.ok && !v.block && !v.withhold());
    let c = |a: &[AtomicU64; 2]| (a[0].load(Ordering::SeqCst), a[1].load(Ordering::SeqCst));
    assert_eq!((c(&bs.passed), c(&bs.withheld), c(&bs.would), c(&bs.open)), ((1, 0), (1, 1), (1, 0), (1, 0)));
    // the limiter: once per window per slot; the window's first
    let mut last = FxHashMap::default();
    assert_eq!(rec_due(&mut last, 7, 1000), Some(true));
    assert_eq!(rec_due(&mut last, 7, 1000), None);
    assert_eq!(rec_due(&mut last, 7, 1001), Some(false));
    assert_eq!(rec_due(&mut last, 8, 1001), Some(true));
    // the control file's key
    assert_eq!(ctl_parse_bd(br#"{"botdepth": "live"}"#), Ok(Some(true)));
    assert_eq!(ctl_parse_bd(br#"{"botdepth": "log", "whale": "live"}"#), Ok(Some(false)));
    assert_eq!(ctl_parse_bd(br#"{"whale": "live"}"#), Ok(None));
    assert!(ctl_parse_bd(br#"{"botdepth": "on"}"#).is_err());
}

#[test]
fn dip39_bd_flags() {
    let l = list("flags.json", &[w(1)], true);
    let c = cfg(&["--presend-live-botdepth", "3:100", "--presend-live-botdepth-list", &l]).unwrap().unwrap();
    assert!(c.bd == Some(lg(3, 100)) && !c.bd_live && c.bd_list.as_deref() == Some(l.as_str()));
    assert!(c.json()["botdepth"] == serde_json::json!({"src": "list", "min": 3, "slots": 100, "list": l, "mode": "log"}), "{}", c.json());
    let c = cfg(&["--presend-live-botdepth", "3:100", "--presend-live-botdepth-list", &l, "--presend-live-botdepth-mode", "live"]).unwrap().unwrap();
    assert!(c.bd_live && c.json()["botdepth"]["mode"] == "live");
    // off by default: no field, nothing
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(c0.bd.is_none() && c0.json().get("botdepth").is_none());
    for (a, want) in [(&["--presend-live-botdepth", "3:100"][..], "needs --presend-live-botdepth-list"),
                      (&["--presend-live-botdepth-list", "/x"][..], "needs --presend-live-botdepth MIN:SLOTS"),
                      (&["--presend-live-botdepth-mode", "live"][..], "needs --presend-live-botdepth MIN:SLOTS"),
                      (&["--presend-live-botdepth", "0:100", "--presend-live-botdepth-list", "/x"][..], "MIN:SLOTS"),
                      (&["--presend-live-botdepth", "3:100", "--presend-live-botdepth-list", "/x", "--presend-live-botdepth-mode", "on"][..], "log | live"),
                      (&["--presend-live-botdepth"][..], "needs a value")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(want), "{a:?}: {e}");
    }
    // needs --presend-live
    let e = Cfg::from_argv(&["snipe_engine".to_string(), "--presend-live-botdepth".into(), "3:100".into()], &arbx::presend::Params::default(), true, S).unwrap_err().to_string();
    assert!(e.contains("needs --presend-live"), "{e}");
    // the control file with the gate alone
    assert!(cfg(&["--presend-live-botdepth", "3:100", "--presend-live-botdepth-list", &l, "--presend-live-ledger-control", "/y"]).is_ok());
    assert!(cfg(&["--presend-live-ledger-control", "/y"]).unwrap_err().to_string().contains("--presend-live-botdepth"));
    // the engine's start-up flag check knows them
    assert!(crate::check_flags(&args(&["--presend-live-botdepth", "3:100", "--presend-live-botdepth-list", "/x", "--presend-live-botdepth-mode", "log"])).is_ok());
}

// ---- the probe end to end ----------------------------------------------------------------------------------------------------------

/// LIVE 3:100: two listed bots before the trigger -> the arm says depth 2 / block; the window's attempts are withheld (it stays armed); a
/// third listed bot trades -> its copy refreshed, the attempts go; a wallet not listed / ours never counts; the bots age out of the window
/// -> withheld again. The records, status, run_end
#[test]
fn dip39_bd_live_window() {
    let (b1, b2, b3, other, whale) = (w(1), w(2), w(3), w(0x44), w(0xEE));
    let l = list("live.json", &[b1, b2, b3, whale], true);
    let mut c = Ctx::new(&["--presend-live-botdepth", "3:10", "--presend-live-botdepth-list", &l, "--presend-live-botdepth-mode", "live"]);
    c.p.bd_start();
    c.pump();
    let cf = &c.ev("presend_live_botdepth_config")[0];
    assert!(cf["ok"] == true && cf["n"] == 4 && cf["min"] == 3 && cf["slots"] == 10 && cf["mode"] == "live", "{cf}");
    // b1 twice (one wallet), b2 once, a wallet not listed, ours; the whale is listed but trades AT the trigger (seen before the attempts)
    let mut tk = c.t2(&[(b1, 1001), (b1, 1002), (b2, 1003), (other, 1004), (USER, 1005)], whale);
    let arm = &c.ev("presend_live_arm")[0];
    assert!(arm["botdepth"] == serde_json::json!({"n": 3, "min": 3, "slots": 10, "block": false, "mode": "live"}), "the whale counts: {}", arm["botdepth"]);
    assert!(!c.check(&tk.mint, 1010).block);
    // the window ages: at 1012 b1 (1002) is the edge (counted); at 1013 it is out -> depth 2 (b2 1003, whale 1010) -> withheld; the window stays armed
    assert_eq!(c.check(&tk.mint, 1012).n, 3);
    let v = c.check(&tk.mint, 1013);
    assert!(v.n == 2 && v.withhold(), "{v:?}");
    assert!(c.p.armed.contains_key(&tk.mint));
    // b3 trades at 1013: the copy refreshed -> 3 -> sent
    let e = tk.buy(b3, S / 20); c.tx(1013, 3, vec![e], vec![]);
    assert!(!c.check(&tk.mint, 1013).block);
    // a not-listed wallet's trade changes nothing
    let e = tk.buy(other, S / 20); c.tx(1013, 4, vec![e], vec![]);
    assert_eq!(c.check(&tk.mint, 1013).n, 3);
    assert!(c.p.status().contains("BOT DEPTH LIVE >= 3 in 10 slots (list 4): withheld T2/re-arm 1/0"), "{}", c.p.status());
    let end = c.p.finish(1015, None);
    assert!(end["botdepth"]["withheld"]["t2"] == 1 && end["botdepth"]["passed"]["t2"] == 4 && end["botdepth"]["mode"] == "live", "{}", end["botdepth"]);
}

/// a fill: "botdepth" from the FILLING attempt's verdict at its send (+ the depth at the fill's slot); a T2 skip carries the depth too
#[test]
fn dip39_bd_fill_and_skip_records() {
    let (b1, whale) = (w(1), w(0xEE));
    let l = list("fill.json", &[b1], false);
    let mut c = Ctx::new(&["--presend-live-botdepth", "2:100", "--presend-live-botdepth-list", &l]);
    let mut tk = c.t2(&[(b1, 1001)], whale);
    let arm = c.ev("presend_live_arm")[0].clone();
    assert!(arm["botdepth"]["n"] == 1 && arm["botdepth"]["block"] == true && arm["botdepth"]["mode"] == "log", "{arm}");
    let id = arm["w"].as_u64().unwrap();
    // the attempt as the sender registers it: log mode, depth 1 < 2 (would block) -> sent
    let mut sg = [0u8; 64]; sg[0] = 0xD3; sg[1] = 0x39;
    c.atx.send(Att { w: id, n: 1, mint: tk.mint, sig: sg, tag: pl::PS_TAG | 0xD39, path: "helius-ps".into(), client: "JitoLabs".into(), slot: 1011, deadline: 1012,
        lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (1011, 0, 0), t_send: 1011 * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
        tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: Some(BdV { n: 1, q: 0, block: true, raw: true, live: false, ok: true }) }).unwrap();
    c.p.drain_atts();
    let e = tk.buy(USER, 396_000_000);
    c.tx_sig(1012, 4, sg, vec![e], vec![]);
    let f = &c.ev("presend_live_fill")[0];
    assert!(f["botdepth"] == serde_json::json!({"n": 1, "min": 2, "slots": 100, "block": true, "mode": "log", "at": "send", "n_fill": 1}), "{}", f["botdepth"]);
    // a trigger on a token with our position: a skip, with the depth
    let e = tk.buy_tok(w(0xEF), pctr(7.0)); c.tx(1013, 60, vec![e], vec![]);
    let s = c.ev("presend_live_skip");
    assert!(!s.is_empty() && s.iter().all(|r| r["botdepth"]["min"] == 2), "{s:?}");
    // no list verdict (fail open) on the filling attempt: said so
    assert_eq!(c.p.bd_fill_json(None, &tk.mint, 1013).unwrap()["ok"], false);
}

/// a missing list: FAIL OPEN (a warning; never withheld, counted); a good list written later is picked up by the reload; the control file
/// flips live / log; a bad value keeps the mode
#[test]
fn dip39_bd_fail_open_reload_control() {
    let (b1, b2, whale) = (w(1), w(2), w(0xEE));
    let l = tmp("later.json");
    let _ = std::fs::remove_file(&l);
    let ctl = tmp("ctl.json");
    std::fs::write(&ctl, r#"{"botdepth": "live"}"#).unwrap();
    let mut c = Ctx::new(&["--presend-live-botdepth", "2:100", "--presend-live-botdepth-list", &l, "--presend-live-ledger-control", &ctl]);
    c.p.ledger_ctl_open();
    assert!(c.p.sh.bd.live.load(Ordering::SeqCst), "the control file at the start: live");
    c.p.bd_start();
    c.pump();
    assert!(c.ev("presend_live_botdepth_config")[0]["ok"] == false && c.lines.iter().any(|x| x.contains("WARNING") && x.contains("FAIL OPEN")));
    let mut tk = c.t2(&[(b1, 1001)], whale);
    assert_eq!(c.ev("presend_live_arm")[0]["botdepth"]["ok"], false);
    let v = c.check(&tk.mint, 1011);
    assert!(!v.ok && !v.withhold(), "no list: sent");
    assert!(c.p.status().contains("NOT LOADED: fail open"));
    // the list appears: reloaded, the armed window's copy refreshed (b1's trade before the list is not in the book: depth 0 -> withheld)
    std::fs::write(&l, serde_json::json!([b58(&b1), b58(&b2)]).to_string()).unwrap();
    c.p.bd.as_mut().unwrap().mtime_reset_for_test();
    let _ = c.p.bd.as_mut().unwrap().check(true, &USER);
    c.p.bd_refresh(&tk.mint);
    assert!(c.check(&tk.mint, 1011).withhold());
    let e = tk.buy(b1, S / 20); c.tx(1012, 3, vec![e], vec![]);
    let e = tk.buy(b2, S / 20); c.tx(1012, 4, vec![e], vec![]);
    assert!(!c.check(&tk.mint, 1012).block, "two listed now");
    // a bad list keeps the last good one
    std::fs::write(&l, "[]").unwrap();
    let r = c.p.bd.as_mut().unwrap().check(true, &USER).unwrap();
    assert!(r["ok"] == false && c.p.bd.as_ref().unwrap().n_list() == 2, "{r}");
    // the control file: log
    std::fs::write(&ctl, r#"{"botdepth": "log"}"#).unwrap();
    c.p.ledger_ctl_check(true);
    assert!(!c.p.sh.bd.live.load(Ordering::SeqCst));
    std::fs::write(&ctl, r#"{"botdepth": "maybe"}"#).unwrap();
    c.p.ledger_ctl_check(true);
    assert!(!c.p.sh.bd.live.load(Ordering::SeqCst), "a bad value keeps it");
    c.pump();
    assert!(c.ev("presend_live_ledger_mode").iter().any(|r| r["botdepth"] == "log" && r["was"]["botdepth"] == "live"));
    let _ = std::fs::remove_file(&ctl);
    let _ = std::fs::remove_file(&l);
}

/// the book pruned past SLOTS (the window's copy is the sender's view until refreshed); the list's reload through the tick refreshes every
/// armed window; a wallet newly listed counts from its next trade
#[test]
fn dip39_bd_tick_prune_reload() {
    let (b1, b2, whale) = (w(1), w(2), w(0xEE));
    let l = list("tick.json", &[b1], true);
    let mut c = Ctx::new(&["--presend-live-botdepth", "1:10", "--presend-live-botdepth-list", &l, "--presend-live-botdepth-mode", "live"]);
    let mut tk = c.t2(&[(b1, 1005)], whale);
    assert!(!c.check(&tk.mint, 1010).block);
    c.p.bd.as_mut().unwrap().book.prune(1016, 10);
    assert_eq!(c.p.bd.as_ref().unwrap().book.mints(), 0, "pruned (b1 1005 < 1016 - 10)");
    assert!(c.check(&tk.mint, 1015).n == 1 && c.check(&tk.mint, 1016).withhold(), "the copy: 1005 counts until slot 1015, then not");
    // the list now also names b2: the tick's reload, every armed window's copy again (empty now)
    std::fs::write(&l, serde_json::json!([b58(&b1), b58(&b2)]).to_string()).unwrap();
    c.p.bd.as_mut().unwrap().mtime_reset_for_test();
    c.p.tick(1016, None);
    c.pump();
    let r = c.ev("presend_live_botdepth_list");
    assert!(r.len() == 1 && r[0]["ok"] == true && r[0]["n"] == 2 && r[0]["was"] == 1, "{r:?}");
    assert_eq!(c.check(&tk.mint, 1015).n, 0, "refreshed");
    let e = tk.buy(b2, S / 20); c.tx(1017, 3, vec![e], vec![]);
    assert_eq!(c.check(&tk.mint, 1017).n, 1, "b2 1017");
}

/// LOG mode changes nothing else: every record of the same tape equal to the gate's absence once "botdepth" is taken out
#[test]
fn dip39_bd_log_changes_nothing_else() {
    let run = |extra: &[&str]| {
        let mut c = Ctx::new(extra);
        let mut tk = c.t2(&[(w(1), 1001), (w(2), 1003)], w(0xEE));
        let e = tk.sell_tok(w(0xEE), pctr(1.0)); c.tx(1011, 5, vec![e], vec![]);
        let sw = c.swin(&tk.mint);
        (c.recs, sw)
    };
    let strip = |v: &Vec<serde_json::Value>| -> Vec<String> {
        v.iter().map(|r| { let mut r = r.clone(); if let Some(o) = r.as_object_mut() { o.remove("botdepth"); o.remove("t"); } r.to_string() }).collect()
    };
    let l = list("same.json", &[w(1), w(2)], true);
    let (r0, s0) = run(&[]);
    let (r1, s1) = run(&["--presend-live-botdepth", "3:100", "--presend-live-botdepth-list", &l]);
    assert_eq!(strip(&r0), strip(&r1));
    assert!(r1.iter().any(|r| r.get("botdepth").is_some()) && r0.iter().all(|r| r.get("botdepth").is_none()));
    assert!(s0.bd.is_none() && s1.bd.is_some() && (s0.id, s0.en_slot, s0.vsol, s0.spend) == (s1.id, s1.en_slot, s1.vsol, s1.spend));
}

// ---- dip39 ORGANIC source (--presend-live-botdepth-source organic) -----------------------------------------------------------------

const MS: u64 = 1_000_000;

#[test]
fn dip39_org_parse_and_flags() {
    assert_eq!(org_parse("2:2").unwrap(), OrgCfg::default());
    let o = org_parse("3:1:5:0.5").unwrap();
    assert!(o.dmin == 3 && o.qmin == 1 && o.trips == 5 && o.h_ns == 1_800_000_000_000);
    for bad in ["2", "17:2", "2:17", "2:2:0", "2:2:65", "2:2:10:0", "2:2:10:25", "0:0", "a:b", "2:2:10:2:9"] { assert!(org_parse(bad).is_err(), "{bad}"); }
    let c = cfg(&["--presend-live-botdepth-source", "organic"]).unwrap().unwrap();
    assert!(c.bd == Some(Gate::Org(OrgCfg::default())) && c.bd_list.is_none());
    assert!(c.json()["botdepth"]["src"] == "organic" && c.json()["botdepth"]["dmin"] == 2 && c.json()["botdepth"]["hours"] == 2.0, "{}", c.json());
    let c = cfg(&["--presend-live-botdepth-source", "organic", "--presend-live-botdepth-organic", "1:3", "--presend-live-botdepth-state", "/tmp/x.json",
        "--presend-live-botdepth-mode", "live"]).unwrap().unwrap();
    assert!(c.bd_live && c.bd_state.as_deref() == Some("/tmp/x.json") && matches!(c.bd, Some(Gate::Org(o)) if o.dmin == 1 && o.qmin == 3));
    for (a, want) in [(&["--presend-live-botdepth-source", "organic", "--presend-live-botdepth", "3:100"][..], "the list source's"),
                      (&["--presend-live-botdepth-source", "organic", "--presend-live-botdepth-list", "/x"][..], "the list source's"),
                      (&["--presend-live-botdepth-organic", "2:2"][..], "needs --presend-live-botdepth-source organic"),
                      (&["--presend-live-botdepth-state", "/x"][..], "needs --presend-live-botdepth-source organic"),
                      (&["--presend-live-botdepth-source", "both"][..], "list | organic"),
                      (&["--presend-live-botdepth-source", "organic", "--presend-live-botdepth-organic", "2"][..], "DMIN:QMIN")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(want), "{a:?}: {e}");
    }
    assert!(cfg(&["--presend-live-botdepth-source", "list"]).unwrap().unwrap().bd.is_none(), "list source without MIN:SLOTS: off");
    assert!(cfg(&["--presend-live-botdepth-source", "organic", "--presend-live-ledger-control", "/y"]).is_ok());
    assert!(crate::check_flags(&args(&["--presend-live-botdepth-source", "organic", "--presend-live-botdepth-organic", "2:2", "--presend-live-botdepth-state", "/x"])).is_ok());
}

/// the round-trip detector: back to <= 2% of what it bought within <= 20 slots = a quick trip (the edges), more left = still open, slower =
/// not quick; buys add up; ours never; quick = >= TRIPS in the last HOURS (the feed's clock)
#[test]
fn dip39_org_round_trips() {
    let o = OrgCfg { dmin: 2, qmin: 2, trips: 2, h_ns: 1000 * MS };
    let mut g = Org::new(o, USER);
    let (z, y) = ([0x81u8; 32], [0x82u8; 32]);
    let (q, r, u, v) = (w(1), w(2), w(3), w(4));
    // q: 1000 bought, 980 sold 5 slots later (exactly 2% left): a trip
    g.trade(z, q, true, S, 1000, 100, 100 * MS);
    g.trade(z, q, false, S, 980, 105, 105 * MS);
    // r: 1000 bought, 970 sold (3% left: open), the last 30 at 121 (21 slots after the first buy): closed, not quick
    g.trade(z, r, true, S, 1000, 100, 100 * MS);
    g.trade(z, r, false, S, 970, 102, 102 * MS);
    g.trade(z, r, false, S, 30, 121, 121 * MS);
    // u: two buys (600 + 400), all sold at exactly 20 slots: quick
    g.trade(y, u, true, S, 600, 100, 100 * MS);
    g.trade(y, u, true, S, 400, 110, 110 * MS);
    g.trade(y, u, false, S, 1000, 120, 120 * MS);
    // v: a sell with no position (bought before the feed): nothing; ours: never
    g.trade(y, v, false, S, 5, 120, 120 * MS);
    g.trade(y, USER, true, S, 100, 120, 120 * MS);
    g.trade(y, USER, false, S, 100, 121, 121 * MS);
    assert_eq!(g.trips_total, 2, "q and u");
    assert!(!g.quick(&q) && !g.quick(&r), "one trip < 2");
    // q's second trip: quick now; ages out HOURS later
    g.trade(y, q, true, S, 10, 130, 130 * MS);
    g.trade(y, q, false, S, 10, 131, 131 * MS);
    assert!(g.quick(&q) && !g.quick(&u));
    g.trade(y, v, true, S, 1, 1105, 1105 * MS);
    assert!(g.quick(&q), "q's first trip (105 ms) is exactly 1000 ms old: still in");
    g.trade(y, v, true, S, 1, 1106, 1106 * MS);
    assert!(!g.quick(&q), "q's first trip (105 ms) is older than 1000 ms at 1106 ms");
    // the prune keeps memory bounded: old positions / trips leave
    g.trade(z, r, true, S, 1000, 1107, 1107 * MS);
    g.prune(3000);
    g.trade(z, v, true, S, 1, 3000, 3000 * MS);
    g.prune(4600);
    assert!(g.sizes()["pos"] == 0 && g.sizes()["wallets"] == 0, "{}", g.sizes());
}

/// (A) dip buyers: a buy in the same slot (after it) or the 2 slots after a sell >= 0.3 SOL; (B) quick traders of the mint in 100 slots; the
/// windows (200 / 100); the copy equals the exact counts; the warm-up
#[test]
fn dip39_org_counts_and_warm() {
    let o = OrgCfg { dmin: 2, qmin: 1, trips: 1, h_ns: 500 * MS };
    let mut g = Org::new(o, USER);
    let (m, z) = ([0x91u8; 32], [0x92u8; 32]);
    let (q, d1, d2, d3, d4, sel) = (w(1), w(2), w(3), w(4), w(5), w(6));
    g.trade(z, w(9), true, S, 1, 1000, 1000 * MS);
    assert!(!g.warm(), "the history starts now");
    // q: one quick trip on z
    g.trade(z, q, true, S, 100, 1001, 1001 * MS);
    g.trade(z, q, false, S, 100, 1002, 1002 * MS);
    // d4 buys BEFORE the sell in its slot: not a dip buy; a small sell (0.29) draws nobody
    g.trade(m, d4, true, S / 10, 10, 1010, 1010 * MS);
    g.trade(m, sel, false, 290_000_000, 10, 1010, 1010 * MS);
    g.trade(m, d4, true, S / 10, 10, 1011, 1011 * MS);
    // the big sell at 1020; d1 same slot after it, d2 2 slots after, d3 3 slots after
    g.trade(m, sel, false, ORG_SELL, 10, 1020, 1020 * MS);
    g.trade(m, d1, true, S / 10, 10, 1020, 1020 * MS);
    g.trade(m, d2, true, S / 10, 10, 1022, 1022 * MS);
    g.trade(m, d3, true, S / 10, 10, 1023, 1023 * MS);
    // q trades the mint
    g.trade(m, q, true, S / 10, 10, 1023, 1023 * MS);
    assert_eq!(g.counts(&m, 1023), (2, 1));
    let s = g.snap(&m);
    assert_eq!((s.a.count(1023, ORG_A_SLOTS), s.b.count(1023, ORG_B_SLOTS), s.warm), (2, 1, false));
    // the windows: A until the sell is 200 slots old, B until q's trade is 100 slots old
    assert_eq!(g.counts(&m, 1123), (2, 1));
    assert_eq!(g.counts(&m, 1124), (2, 0), "B: q's 1023 out (lo 1024)");
    assert_eq!(g.counts(&m, 1220), (2, 0));
    assert_eq!(g.counts(&m, 1221), (0, 0), "A: the sell at 1020 out (lo 1021)");
    assert_eq!((s.a.count(1220, ORG_A_SLOTS), s.a.count(1221, ORG_A_SLOTS), s.b.count(1123, ORG_B_SLOTS), s.b.count(1124, ORG_B_SLOTS)), (2, 0, 1, 0));
    // the sender: the warm-up fails open (counts kept, raw verdict), then the rule
    let bs = BdShared::default();
    bs.live.store(true, Ordering::SeqCst);
    let gt = Gate::Org(o);
    let v = check(&bs, &gt, Some(&Snap { warm: false, ..snap(&[]) }), 1023, false);
    assert!(!v.ok && !v.withhold() && v.raw && v.n == 0, "{v:?}");
    let v = check(&bs, &gt, Some(&s), 1023, false);
    assert!(!v.ok && !v.withhold() && !v.raw && (v.n, v.q) == (2, 1));
    g.trade(z, w(9), true, S, 1, 1500, 1500 * MS);
    assert!(g.warm(), "500 ms of history");
    let s = g.snap(&m);
    let v = check(&bs, &gt, Some(&s), 1023, false);
    assert!(v.ok && !v.block, "{v:?}");
    assert!(check(&bs, &Gate::Org(OrgCfg { dmin: 3, ..o }), Some(&s), 1023, false).withhold(), "dipb 2 < 3");
    g.trade(z, w(9), true, S, 1, 1503, 1503 * MS);
    assert!(!g.quick(&q), "q's trip at 1002 ms is older than 500 ms at 1503 ms");
    assert!(check(&bs, &gt, Some(&g.snap(&m)), 1023, false).withhold(), "qt 0 < 1 once q is no longer quick");
    assert_eq!(rule(&gt, 2, 1), false);
    assert_eq!(rule(&gt, 1, 1), true);
}

/// the state: saved trips + the history's start; used when saved <= 30 min before the first trade (warm at once), else ignored
#[test]
fn dip39_org_state() {
    let o = OrgCfg { dmin: 1, qmin: 1, trips: 1, h_ns: 2 * 3600 * 1_000_000_000 };
    let t0 = 1_800_000_000_000_000_000u64;
    let mut g = Org::new(o, USER);
    g.trade([1; 32], w(9), true, S, 1, 10, t0);
    g.trade([2; 32], w(1), true, S, 100, 11, t0 + MS);
    g.trade([2; 32], w(1), false, S, 100, 12, t0 + 2 * MS);
    let st = g.state_json().to_string();
    assert!(g.quick(&w(1)) && !g.warm());
    // 3 h later, 20 min after the save: used (the history from t0: warm)
    let p = tmp("org-state.json");
    std::fs::write(&p, &st).unwrap();
    let mut b = Bd::open(Gate::Org(o), None, Some(&p), &USER);
    assert!(b.err.is_none());
    let o2 = b.org.as_mut().unwrap();
    o2.trade([3; 32], w(8), true, S, 1, 50_000, t0 + 2 * MS + 20 * 60 * 1_000_000_000);
    assert!(o2.state_used == Some(true) && o2.quick(&w(1)) && !o2.warm(), "20 min of history only");
    let mut o3 = Org::new(o, USER);
    o3.state_load(st.as_bytes()).unwrap();
    o3.trade([3; 32], w(8), true, S, 1, 50_000, t0 + 2 * 3600 * 1_000_000_000 + 5);
    assert!(o3.state_used == Some(false) && !o3.quick(&w(1)), "saved 2 h before: not used");
    let mut o4 = Org::new(o, USER);
    o4.state_load(st.as_bytes()).unwrap();
    o4.cfg.h_ns = 10 * 60 * 1_000_000_000;
    o4.trade([3; 32], w(8), true, S, 1, 50_000, t0 + 15 * 60 * 1_000_000_000);
    assert!(o4.state_used == Some(true) && o4.warm(), "the saved history's start counts toward the warm-up");
    // a missing file: nothing (no error); a bad one: an error, fail open (warm-up)
    assert!(Bd::open(Gate::Org(o), None, Some(&tmp("org-none.json")), &USER).err.is_none());
    std::fs::write(&p, "{}").unwrap();
    assert!(Bd::open(Gate::Org(o), None, Some(&p), &USER).err.is_some());
    // the run's end saves it
    let mut c = Ctx::new(&["--presend-live-botdepth-source", "organic", "--presend-live-botdepth-state", &p]);
    let mut z = Tk::new(0x7A);
    c.launches.push(z.launch.clone());
    let dv = z.buy(CREATOR, S / 2); c.tx(1000, 1, vec![dv], vec![z.create()]);
    let e = z.buy(w(1), S / 10); c.tx(1001, 1, vec![e.clone()], vec![]);
    let e = z.sell_tok(w(1), e.tok); c.tx(1002, 1, vec![e], vec![]);
    let end = c.p.finish(1003, None);
    assert!(end["botdepth"]["organic"]["trips"] == 1, "{}", end["botdepth"]);
    let j: serde_json::Value = serde_json::from_slice(&std::fs::read(&p).unwrap()).unwrap();
    assert!(j["w"][b58(&w(1))].as_array().is_some_and(|a| a.len() == 1), "{j}");
    let _ = std::fs::remove_file(&p);
}

/// the probe end to end (LIVE, 2:2, 2 trips in 0.0001 h = 360 ms = 360 test slots): a window armed in the warm-up is never withheld (counts
/// logged); once warm, a token with 2 dip buyers + 2 quick traders passes, one with 1 dip buyer is withheld
#[test]
fn dip39_org_probe() {
    let (q1, q2, d1, d2, d3, whale) = (w(1), w(2), w(3), w(4), w(5), w(0xEE));
    let mut c = Ctx::new(&["--presend-live-botdepth-source", "organic", "--presend-live-botdepth-organic", "2:2:2:0.0001", "--presend-live-botdepth-mode", "live"]);
    c.p.bd_start();
    c.pump();
    let cf = &c.ev("presend_live_botdepth_config")[0];
    assert!(cf["src"] == "organic" && cf["organic"]["dmin"] == 2 && cf["organic"]["trips"] == 2 && cf["mode"] == "live", "{cf}");
    let mut z = Tk::new(0x7F);
    c.launches.push(z.launch.clone());
    let dv = z.buy(CREATOR, S / 2); c.tx(1000, 1, vec![dv], vec![z.create()]);
    // a token armed in the warm-up
    let mut a = Tk::new(0x71);
    c.launches.push(a.launch.clone());
    let dv = a.buy(CREATOR, S / 2); c.tx(1001, 1, vec![dv], vec![a.create()]);
    let e = a.buy_tok(whale, pctr(8.0)); c.tx(1005, 50, vec![e], vec![]);
    let arm = c.ev("presend_live_arm")[0].clone();
    assert!(arm["botdepth"]["src"] == "organic" && arm["botdepth"]["warm"] == false && arm["botdepth"]["block"] == false && arm["botdepth"]["raw"] == true, "{arm}");
    let v = c.check(&a.mint, 1005);
    assert!(!v.ok && !v.withhold(), "warm-up: fail open");
    // quick trips (2 each) at 1400..1403 on z
    for (i, q) in [q1, q2].iter().enumerate() {
        for k in 0..2u64 {
            let s = 1400 + 2 * k;
            let e = z.buy(*q, S / 10); c.tx(s, 10 + i as u64, vec![e.clone()], vec![]);
            let e = z.sell_tok(*q, e.tok); c.tx(s + 1, 10 + i as u64, vec![e], vec![]);
        }
    }
    // token b: the creator's sell >= 0.3 SOL at 1406, d1 after it, d2 two slots later, d3 three (not); q1 / q2 trade it; the whale at 1410
    let mut b = Tk::new(0x72);
    c.launches.push(b.launch.clone());
    let dv = b.buy(CREATOR, S / 2); c.tx(1405, 1, vec![dv.clone()], vec![b.create()]);
    let e = b.sell_tok(CREATOR, dv.tok); assert!(e.sol >= ORG_SELL); c.tx(1406, 2, vec![e], vec![]);
    let e = b.buy(d1, S / 20); c.tx(1406, 3, vec![e], vec![]);
    let e = b.buy(d2, S / 20); c.tx(1408, 1, vec![e], vec![]);
    let e = b.buy(d3, S / 20); c.tx(1409, 1, vec![e], vec![]);
    let e = b.buy(q1, S / 20); c.tx(1409, 2, vec![e], vec![]);
    let e = b.buy(q2, S / 20); c.tx(1409, 3, vec![e], vec![]);
    let e = b.buy_tok(whale, pctr(8.0)); c.tx(1410, 50, vec![e], vec![]);
    let arm = c.ev("presend_live_arm").last().cloned().unwrap();
    assert!(arm["botdepth"] == serde_json::json!({"src": "organic", "dipb": 2, "qt": 2, "dmin": 2, "qmin": 2, "block": false, "mode": "live"}), "{}", arm["botdepth"]);
    let v = c.check(&b.mint, 1410);
    assert!(v.ok && !v.block && (v.n, v.q) == (2, 2), "{v:?}");
    // token c: one dip buyer only -> withheld
    let mut t = Tk::new(0x73);
    c.launches.push(t.launch.clone());
    let dv = t.buy(CREATOR, S / 2); c.tx(1411, 1, vec![dv.clone()], vec![t.create()]);
    let e = t.buy(q1, S / 20); c.tx(1411, 2, vec![e], vec![]);
    let e = t.buy(q2, S / 20); c.tx(1411, 3, vec![e], vec![]);
    let e = t.sell_tok(CREATOR, dv.tok); c.tx(1412, 2, vec![e], vec![]);
    let e = t.buy(d1, S / 20); c.tx(1412, 3, vec![e], vec![]);
    let e = t.buy_tok(whale, pctr(8.0)); c.tx(1415, 50, vec![e], vec![]);
    let arm = c.ev("presend_live_arm").last().cloned().unwrap();
    // qt 3: q1, q2 and the creator (its dev buy -> full sell on b and on c = 2 quick trips)
    assert!(arm["botdepth"]["dipb"] == 1 && arm["botdepth"]["qt"] == 3 && arm["botdepth"]["block"] == true, "{}", arm["botdepth"]);
    assert!(c.check(&t.mint, 1415).withhold());
    assert!(c.p.status().contains("BOT DEPTH LIVE organic dipb >= 2 qt >= 2 (warm; quick wallets 3, trips 6)"), "{}", c.p.status());
}

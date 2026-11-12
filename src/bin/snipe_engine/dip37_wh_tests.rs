// ===================================================================================================================
// dip37 WHALE / DUMPER LOSS LEDGER tests (pswh.rs: --presend-live-wh-loss N:SOL, --presend-live-wh-loss-mode sum|mean,
// --presend-live-whale-state PATH) and the FP-NOBOT STALE HOLD (pslog36::gate_withhold_why, --presend-fpnb-stale-hold N).
// Off: no field, no skip, every record dip36's. On: T2 keyed on the trigger whale, re-arm on the dumper; the boundary of both rules;
// the realized lookup carries the window's wallet; the state round trip and the seed's format.
// ===================================================================================================================
use super::*;
use super::pslog36::*;
use super::pswh::*;
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
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn pct(x: f64) -> u64 { (x / 100.0 * pl::SUPPLY) as u64 }
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x37; x }
fn tmp(tag: &str) -> String { std::env::temp_dir().join(format!("dip37-wh-{}-{tag}.json", std::process::id())).to_string_lossy().to_string() }

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

struct Ctx { p: PsLive, atx: crossbeam_channel::Sender<Att>, orx: crossbeam_channel::Receiver<Out>, launches: Vec<Launch>, recs: Vec<serde_json::Value>, lines: Vec<String>, cmds: Vec<Cmd> }
impl Ctx {
    fn new(extra: &[&str]) -> Ctx {
        let (p, atx, orx) = PsLive::for_test(cfg(extra).unwrap().unwrap(), USER);
        Ctx { p, atx, orx, launches: Vec::new(), recs: Vec::new(), lines: Vec::new(), cmds: Vec::new() }
    }
    fn tx_sig(&mut self, slot: u64, idx: u64, sig: [u8; 64], payer: Pk, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let ls = self.launches.clone();
        self.p.on_arrival(&a, slot);
        self.p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
        for o in self.orx.try_iter() { match o { Out::Rec(v) => self.recs.push(v), Out::Line(l) => self.lines.push(l) } }
        self.cmds.extend(self.p.take_cmds());
    }
    fn tx(&mut self, slot: u64, idx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0x37; sig[17] = trades.first().map_or(0, |t| t.mint[0]);
        self.tx_sig(slot, idx, sig, [0x77; 32], trades, creates);
    }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    fn seed(&self, k: Pk, n: u32, sum: i64) { self.p.sh.wh.lock().unwrap().all.insert(k, WhHist { n, sum, ..Default::default() }); }
    /// T2: token 0x61 created at 1000, a small buy at 1003, the whale's 2 SOL buy at 1005 (a trigger)
    fn t2(&mut self, whale: Pk) -> Tk {
        let mut tk = Tk::new(0x61);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, vec![dev], vec![tk.create()]);
        let e = tk.buy(w(0x11), S / 10);
        self.tx(1003, 2, vec![e], vec![]);
        let e = tk.buy(whale, 2 * S);
        self.tx(1005, 50, vec![e], vec![]);
        tk
    }
    /// re-arm: create-slot buys of a 7% / b 8%, a dumps at 1005, the check at 1008 (a filler token moves the clock)
    fn rearm(&mut self, a: Pk, b: Pk) -> Tk {
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
        let d = tk.sell_tok(a, pct(7.0));
        self.tx(1005, 5, vec![d], vec![]);
        for s in 1006..=1008 { let e = z.buy(w(0x2F), 1_000_000); self.tx(s, 900, vec![e], vec![]); }
        tk
    }
}

fn sold(c: Option<u64>, sigs: &[&str], qty: u64) -> SellOut {
    SellOut { sold_at: c, sigs: sigs.iter().map(|s| (s.to_string(), true, 1_200_000)).collect(), last: None, attempts: sigs.len() as u32, last_qty: (qty, true), first_send_us: None }
}
fn strip(v: &[serde_json::Value]) -> Vec<String> { v.iter().cloned().filter_map(dip26_tests::strip47).map(|r| r.to_string()).collect() }

/// the flags: parse, the start record, refusals, the start-up check
#[test]
fn dip37_wh_flags() {
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(!c0.wh_on() && c0.wh_state.is_none() && c0.fpnb_stale_hold == 0 && c0.json().get("wh_loss").is_none() && c0.json().get("fpnb_stale_hold").is_none(), "off: dip36");
    let c = cfg(&["--presend-live-wh-loss", "2:0.05", "--presend-live-whale-state", "/tmp/w.json"]).unwrap().unwrap();
    assert!(c.wh_on() && (c.wh_loss_n, c.wh_loss, c.wh_mean) == (2, 50_000_000, false) && c.wh_state.as_deref() == Some("/tmp/w.json"));
    assert!(c.json()["wh_loss"] == "2:0.05 sum" && c.json()["whale_state"] == "/tmp/w.json");
    let c = cfg(&["--presend-live-wh-loss", "2:0.01", "--presend-live-wh-loss-mode", "mean"]).unwrap().unwrap();
    assert!(c.wh_mean && c.wh_loss == 10_000_000 && c.json()["wh_loss"] == "2:0.01 mean");
    for (a, needle) in [(&["--presend-live-wh-loss", "2"][..], "N:SOL"), (&["--presend-live-wh-loss", "0:0.05"][..], "N:SOL"), (&["--presend-live-wh-loss", "2:6"][..], "N:SOL"),
        (&["--presend-live-wh-loss", "2:0"][..], "N:SOL"), (&["--presend-live-wh-loss"][..], "needs a value"),
        (&["--presend-live-wh-loss-mode", "mean"][..], "needs --presend-live-wh-loss N:SOL"), (&["--presend-live-whale-state", "/x"][..], "needs --presend-live-wh-loss N:SOL"),
        (&["--presend-live-wh-loss", "2:0.05", "--presend-live-wh-loss-mode", "avg"][..], "sum | mean"),
        (&["--presend-fpnb-stale-hold", "2"][..], "needs the FP-NOBOT live gate")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    for f in ["--presend-live-wh-loss", "--presend-live-wh-loss-mode", "--presend-live-whale-state", "--presend-fpnb-stale-hold"] {
        let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", f, "1"].iter().map(|s| s.to_string()).collect::<Vec<_>>(), &arbx::presend::Params::default(), true, 1_000_000_000)
            .unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
    assert!(crate::check_flags(&args(&["--presend-live-wh-loss", "2:0.05", "--presend-live-wh-loss-mode", "mean", "--presend-live-whale-state", "/x", "--presend-fpnb-stale-hold", "2"])).is_ok());
    assert!(crate::check_flags(&args(&["--presend-fpnb-stale-hold", "x"])).is_err(), "a number");
    assert!((wh_loss_parse("13:0.91").unwrap(), wh_loss_parse("50:5").is_ok(), wh_loss_parse("51:1").is_err()) == ((13, 910_000_000), true, true));
}

/// both rules exactly at their boundary
#[test]
fn dip37_wh_rule_boundaries() {
    let (n, l) = (2u32, 50_000_000i64);
    assert!(WhHist { n: 2, sum: -50_000_000, ..Default::default() }.blocks(n, l), "sum: exactly -SOL blocks");
    assert!(!WhHist { n: 2, sum: -49_999_999, ..Default::default() }.blocks(n, l), "one lamport above: no");
    assert!(!WhHist { n: 1, sum: -900_000_000, ..Default::default() }.blocks(n, l), "too few positions: no");
    assert!(WhHist { n: 3, sum: -60_000_000, ..Default::default() }.blocks(n, l));
    assert!(!WhHist { n: 5, sum: -60_000_000, ..Default::default() }.blocks(n, 0), "loss 0: off");
    // mean 2:0.01: sum / n <= -0.01
    let m = 10_000_000i64;
    assert!(WhHist { n: 2, sum: -20_000_000, ..Default::default() }.blocks_mean(2, m), "mean exactly -0.01 blocks");
    assert!(!WhHist { n: 2, sum: -19_999_999, ..Default::default() }.blocks_mean(2, m));
    assert!(WhHist { n: 13, sum: -913_700_000, ..Default::default() }.blocks_mean(2, m) && !WhHist { n: 1, sum: -500_000_000, ..Default::default() }.blocks_mean(2, m));
    assert!(!WhHist { n: 10, sum: -60_000_000, ..Default::default() }.blocks_mean(2, m) && WhHist { n: 10, sum: -60_000_000, ..Default::default() }.blocks(2, l), "the rules differ: sum hit, mean not");
    assert!(WhHist { n: 2, sum: -30_000_000, ..Default::default() }.blocks_mean(2, m) && !WhHist { n: 2, sum: -30_000_000, ..Default::default() }.blocks(2, l), "mean hit, sum not");
    assert!(WhHist { n: 2, sum: -20_000_000, ..Default::default() }.blocks_mode(2, m, true) && !WhHist { n: 2, sum: -20_000_000, ..Default::default() }.blocks_mode(2, l, false));
}

/// T2 keyed on the trigger WHALE: at the boundary skipped "wh_loss" (fields, line, count); one lamport above / another wallet in the ledger:
/// armed with the ledger's view; the mean mode on the same ledger; the dumper is never the T2 key
#[test]
fn dip37_wh_t2_skip_and_keying() {
    let whale = w(0xEE);
    let on = ["--presend-live-wh-loss", "2:0.05"];
    let mut c = Ctx::new(&on);
    c.seed(whale, 2, -50_000_000);
    c.t2(whale);
    assert!(c.ev("presend_live_arm").is_empty() && c.p.armed.is_empty());
    let s = c.ev("presend_live_skip").pop().unwrap();
    assert!(s["why"] == "wh_loss" && s["wh_wallet"] == b58(&whale) && s["wh_n"] == 2 && s["wh_sum"] == -0.05 && s["wh_sum_hit"] == true && s["wh_mean_hit"] == false,
        "mean -0.025 > -0.05: only the sum rule hits: {s}");
    assert!(c.lines.iter().any(|l| l.contains("PRESEND LIVE WHALE-LOSS SKIP")) && c.p.whs.skips == [1, 0] && c.p.st.skips["wh_loss"] == 1);
    assert!(c.p.status().contains(" | WHALE LEDGER 1: skips T2 1 re-arm 0"), "{}", c.p.status());
    // one lamport above the boundary: armed; the arm record carries the ledger's view and both verdicts
    let mut c = Ctx::new(&on);
    c.seed(whale, 2, -49_999_999);
    c.t2(whale);
    let a = c.ev("presend_live_arm").pop().expect("armed");
    assert!(a["wh_n"] == 2 && a["wh_sum_hit"] == false && a["wh_mean_hit"] == false && a["wh_wallet"] == b58(&whale), "{a}");
    assert_eq!(c.p.whs.win.get(&a["w"].as_u64().unwrap()), Some(&whale), "the window's wallet for its realized lookup");
    // the same ledger in mean mode at 2:0.02: mean -0.025 <= -0.02 -> skipped (the sum rule would not at 2:0.05)
    let mut c = Ctx::new(&["--presend-live-wh-loss", "2:0.02", "--presend-live-wh-loss-mode", "mean"]);
    c.seed(whale, 2, -50_000_000);
    c.t2(whale);
    let s = c.ev("presend_live_skip").pop().unwrap();
    assert!(s["why"] == "wh_loss" && s["wh_mean_hit"] == true && s["wh_sum_hit"] == true, "{s}");
    let mut c = Ctx::new(&["--presend-live-wh-loss", "2:0.03", "--presend-live-wh-loss-mode", "mean"]);
    c.seed(whale, 2, -59_999_999);
    c.t2(whale);
    assert!(c.ev("presend_live_skip").is_empty(), "mean -0.0299 > -0.03: armed");
    // a bad wallet that is NOT the whale (e.g. the earlier small buyer): armed
    let mut c = Ctx::new(&on);
    c.seed(w(0x11), 9, -900_000_000);
    c.t2(whale);
    assert!(c.ev("presend_live_arm").len() == 1 && c.ev("presend_live_arm")[0]["wh_n"] == 0);
}

/// re-arm keyed on the DUMPER (a): skipped "rearm_wh_loss"; the remaining holder (b) in the ledger: armed; the arm records its dumper
#[test]
fn dip37_wh_rearm_keyed_on_dumper() {
    let (a, b) = (w(0xA1), w(0xB1));
    let run = |seed: Option<Pk>| { let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-wh-loss", "2:0.05"]); if let Some(k) = seed { c.seed(k, 3, -200_000_000); } c.rearm(a, b); c };
    let c = run(Some(a));
    assert!(!c.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm"));
    let s = c.ev("presend_live_skip").into_iter().find(|r| r["why"] == "rearm_wh_loss").expect("skipped");
    assert!(s["kind"] == "rearm" && s["wh_wallet"] == b58(&a) && s["wh_n"] == 3 && s["wh_sum"] == -0.2 && s["wh_sum_hit"] == true, "{s}");
    assert_eq!(c.p.whs.skips, [0, 1]);
    let c = run(Some(b));
    let ar = c.ev("presend_live_arm").into_iter().find(|r| r["kind"] == "rearm").expect("a holder in the ledger does not block the re-arm");
    assert!(ar["wh_wallet"] == b58(&a) && ar["wh_n"] == 0, "{ar}");
    assert_eq!(c.p.whs.win.get(&ar["w"].as_u64().unwrap()), Some(&a));
}

/// the realized lookup carries the window's wallet (the task adds the P&L to it); off: none
#[test]
fn dip37_wh_realized_carries_the_wallet() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    for on in [true, false] {
        let whale = w(0xEE);
        let mut c = Ctx::new(if on { &["--presend-live-wh-loss", "2:0.05"][..] } else { &[][..] });
        let mut tk = c.t2(whale);
        let id = *c.p.armed.get(&tk.mint).unwrap();
        let mut sg = [0u8; 64]; sg[0] = 0xD3; sg[1] = 0x77;
        c.atx.send(Att { w: id, n: 1, mint: tk.mint, sig: sg, tag: pl::PS_TAG | 0xD377, path: "helius-ps".into(), client: "JitoLabs".into(), slot: 1006, deadline: 1007,
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (1006, 0, 0), t_send: 1_006_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
            tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46: Default::default(), rf: None, rg: None }).unwrap();
        c.p.drain_atts();
        let e = tk.buy(USER, 396_000_000);
        c.tx_sig(1007, 4, sg, USER, vec![e.clone()], vec![]);
        let mut z = Tk::new(0x7F);
        c.launches.push(z.launch.clone());
        let dz = z.buy(CREATOR, S / 2);
        c.tx(1007, 900, vec![dz], vec![z.create()]);
        for s in 1008..=1009 { let e = z.buy([0x2F; 32], 1_000_000); c.tx(s, 900, vec![e], vec![]); }
        let Some(Cmd::Sell { pid, .. }) = c.cmds.iter().find(|x| matches!(x, Cmd::Sell { .. })).cloned() else { panic!("{:?}", c.cmds) };
        let es = tk.sell_tok(USER, e.tok);
        c.tx_sig(1009, 9, { let mut s = [0u8; 64]; s[0] = 0x5E; s[1] = 0x37; s }, USER, vec![es], vec![]);
        c.p.on_msg(PsMsg::Sold(tk.mint, pid, 1, sold(Some(1009), &["S37"], e.tok)), &|_| false);
        c.cmds.extend(c.p.take_cmds());
        let Some(Cmd::Realized { wh, .. }) = c.cmds.iter().find(|x| matches!(x, Cmd::Realized { .. })).cloned() else { panic!("{:?}", c.cmds) };
        assert_eq!(wh, on.then_some((whale, false)), "on {on}");
        let end = c.p.finish(1012, None);
        assert_eq!(end.get("wh_ledger").is_some(), on);
    }
}

/// flags off: the same records as with the ledger on whose wallets are unknown, minus only the ledger's own fields (and dip36 = no field)
#[test]
fn dip37_wh_off_records_unchanged() {
    let whale = w(0xEE);
    let mut c0 = Ctx::new(&[]);
    c0.t2(whale);
    let mut c1 = Ctx::new(&["--presend-live-wh-loss", "2:0.05"]);
    c1.t2(whale);
    assert!(c0.recs.iter().all(|r| r.get("wh_n").is_none() && r.get("wh_wallet").is_none()), "off: no ledger field");
    let mut r1 = c1.recs.clone();
    for r in r1.iter_mut() { if let Some(o) = r.as_object_mut() { for k in ["wh_wallet", "wh_n", "wh_sum", "wh_sum_hit", "wh_mean_hit"] { o.remove(k); } } }
    assert_eq!(strip(&r1), strip(&c0.recs), "an unknown whale: the same decision and records but the fields");
    assert!(!c0.p.status().contains("WHALE LEDGER") && c1.p.status().contains(" | WHALE LEDGER 0: skips T2 0 re-arm 0"));
}

/// the state file round trip and the seed builder's format (whale_seed.py: {"v": 1, "w": {wallet: [n, lamports]}, "built": {...}})
#[test]
fn dip37_wh_state_round_trip_and_seed() {
    let p = tmp("state");
    let mut m = WhMaps::default();
    m.all.insert(w(1), WhHist { n: 13, sum: -913_700_000, ..Default::default() });
    m.all.insert(w(2), WhHist { n: 2, sum: 4_000_000, pn: 1, ps: 3_000_000 });
    m.t2.insert(w(1), WhHist { n: 12, sum: -900_000_000, ..Default::default() });
    m.re.insert(w(2), WhHist { n: 1, sum: 1_000_000, ..Default::default() });
    assert_eq!(wh_save(&m, &p).unwrap(), 2);
    assert_eq!(wh_load(&p).unwrap(), m);
    let seed = br#"{"v": 1, "w": {"BujUx1wzxo6iPvueULzqXvn7WVrRNz9uGqvDRThb4SEY": [13, -913700000]}, "built": {"runs": ["AMS55"]}}"#;
    let s = wh_parse(seed).unwrap();
    let buj: Pk = bs58::decode("BujUx1wzxo6iPvueULzqXvn7WVrRNz9uGqvDRThb4SEY").into_vec().unwrap().try_into().unwrap();
    assert_eq!(s.all[&buj], WhHist { n: 13, sum: -913_700_000, ..Default::default() });
    for bad in [&b"{}"[..], br#"{"w": {"nope": [1, 2]}}"#, br#"{"w": {"BujUx1wzxo6iPvueULzqXvn7WVrRNz9uGqvDRThb4SEY": [1]}}"#, b"["] { assert!(wh_parse(bad).is_err()); }
    // the staged seed, when this machine has it
    if let Ok(b) = std::fs::read("/home/it/sniper-data/dip37stage/whale_state_ams.json") {
        let m = wh_parse(&b).unwrap();
        assert!(m.all[&buj].n == 13 && (m.all[&buj].sum as f64 / 1e9 + 0.91).abs() < 0.01, "{:?}", m.all[&buj]);
    }
    // the probe preloads it at start through the same reader; a missing state file at start is an empty ledger
    std::fs::remove_file(&p).unwrap();
    assert!(wh_load(&p).is_err());
}

/// the FP-NOBOT stale hold: off = dip36's fail-open; on: a recent (<= N) BLOCK held, an old block / an old pass / no verdict / not covered
/// fail open; a fresh verdict decides as before; the counters
#[test]
fn dip37_fpnb_stale_hold() {
    let (g, gs) = (Gate::default(), GateShared::default());
    gs.mode.store(3, Ordering::SeqCst);
    g.set(1000, true, true);
    // off (0): a stale block fails open
    assert_eq!(gate_withhold_why(&g, &gs, 1001, false), None);
    assert_eq!(gs.open_stale[0].load(Ordering::Relaxed), 1);
    // on, N = 2: 1 and 2 slots old held (stale), 3 old open; fresh still Some(false)
    gs.stale_hold.store(2, Ordering::SeqCst);
    assert_eq!(gate_withhold_why(&g, &gs, 1000, false), Some(false), "fresh: dip36's withhold");
    assert_eq!(gate_withhold_why(&g, &gs, 1001, false), Some(true));
    assert_eq!(gate_withhold_why(&g, &gs, 1002, true), Some(true));
    assert_eq!(gate_withhold_why(&g, &gs, 1003, false), None, "older than N: fail open");
    assert_eq!((gs.withheld_stale[0].load(Ordering::Relaxed), gs.withheld_stale[1].load(Ordering::Relaxed), gs.withheld[0].load(Ordering::Relaxed)), (1, 1, 1));
    assert_eq!(gs.open_stale[0].load(Ordering::Relaxed), 2);
    // an old PASS: fail open
    g.set(1000, true, false);
    assert_eq!(gate_withhold_why(&g, &gs, 1001, false), None);
    // a block not covered: fail open
    g.set(1000, false, true);
    assert_eq!(gate_withhold_why(&g, &gs, 1001, false), None);
    // no verdict at all: fail open
    assert_eq!(gate_withhold_why(&Gate::default(), &gs, 1001, false), None);
    // a kind not live: never
    gs.mode.store(1, Ordering::SeqCst);
    g.set(1000, true, true);
    assert_eq!(gate_withhold_why(&g, &gs, 1001, true), None);
    assert!(gate_withhold(&g, &gs, 1001, false), "the bool wrapper");
    // the flag: needs the live gate; the config value reaches the gate at the start
    let e = cfg(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", "/x", "--presend-fpnb-stale-hold", "2"]).unwrap_err().to_string();
    assert!(e.contains("needs the FP-NOBOT live gate"), "{e}");
    assert!(cfg(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", "/x", "--presend-fpnb-live", "t2", "--presend-fpnb-stale-hold", "21"]).unwrap_err().to_string().contains("1..20"));
    let c = cfg(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", "/x", "--presend-fpnb-live", "t2", "--presend-fpnb-stale-hold", "2"]).unwrap().unwrap();
    assert!(c.fpnb_stale_hold == 2 && c.json()["fpnb_stale_hold"] == 2);
}

/// --presend-live-wh-learn paper: a "wh_loss"-skipped T2 trigger, the shadow's presend_arm on the same signature, its row c fill (sol_in) and
/// exit (net_cheap): the whale's ledger gets a PAPER position scaled to the live size (state file marks it); another row / another signature /
/// a window without a row c fill: nothing; off: nothing
#[test]
fn dip37_wh_learn_paper() {
    let whale = w(0xEE);
    for learn in [true, false] {
        let mut x: Vec<&str> = vec!["--presend-live-wh-loss", "2:0.05"];
        if learn { x.extend(["--presend-live-wh-learn", "paper"]); }
        let mut c = Ctx::new(&x);
        c.seed(whale, 2, -60_000_000);
        c.t2(whale);
        let s = c.ev("presend_live_skip").pop().unwrap();
        assert_eq!(s["why"], "wh_loss");
        let sig = s["trig"]["sig"].as_str().unwrap().to_string();
        // a row-a fill and an unrelated window: ignored; row c of the skipped trigger: sol_in 0.8 SOL (lamports, as the shadow writes it), net_cheap +0.06 SOL -> +0.03 at 0.4 SOL
        for r in [serde_json::json!({"ev": "presend_arm", "w": 7, "sig": sig}), serde_json::json!({"ev": "presend_arm", "w": 8, "sig": "other"}),
                  serde_json::json!({"ev": "presend_fill", "w": 7, "row": "a", "entry": {"sol_in": 100_000_000u64}}), serde_json::json!({"ev": "presend_fill", "w": 7, "row": "c", "entry": {"sol_in": 800_000_000u64}}),
                  serde_json::json!({"ev": "presend_fill", "w": 8, "row": "c", "entry": {"sol_in": 800_000_000u64}}), serde_json::json!({"ev": "presend_exit", "w": 7, "row": "a", "net_cheap": 0.5}),
                  serde_json::json!({"ev": "presend_exit", "w": 7, "row": "c", "net_cheap": 0.06}), serde_json::json!({"ev": "presend_exit", "w": 8, "row": "c", "net_cheap": 0.06})] {
            c.p.on_shadow_rec(&r);
        }
        for o in c.orx.try_iter() { if let Out::Rec(v) = o { c.recs.push(v); } }
        let h = c.p.sh.wh.lock().unwrap().all[&whale];
        if learn {
            assert_eq!(h, WhHist { n: 3, sum: -30_000_000, pn: 1, ps: 30_000_000 }, "a paper position at the live size");
            assert_eq!(c.p.sh.wh.lock().unwrap().t2[&whale], WhHist { n: 1, sum: 30_000_000, pn: 1, ps: 30_000_000 }, "the T2 ledger too");
            let r = c.ev("presend_live_wh_paper").pop().unwrap();
            assert!(r["whale"] == b58(&whale) && r["credit"] == 0.03 && r["n"] == 3 && r["pn"] == 1 && r["blocks"] == false, "{r}");
            assert!(c.p.status().contains("paper credits 1 (+0.030 SOL)"));
            // the state file marks it
            let p = tmp("paper");
            wh_save(&c.p.sh.wh.lock().unwrap(), &p).unwrap();
            let j: serde_json::Value = serde_json::from_slice(&std::fs::read(&p).unwrap()).unwrap();
            assert_eq!(j["w"][b58(&whale)], serde_json::json!([3, -30_000_000, 1, 30_000_000]));
            assert_eq!(wh_load(&p).unwrap().all[&whale], h);
            std::fs::remove_file(&p).unwrap();
            // the same trigger never credits twice
            c.p.on_shadow_rec(&serde_json::json!({"ev": "presend_exit", "w": 7, "row": "c", "net_cheap": 0.06}));
            assert_eq!(c.p.sh.wh.lock().unwrap().all[&whale].n, 3);
        } else {
            assert_eq!(h, WhHist { n: 2, sum: -60_000_000, ..Default::default() }, "off: nothing learned");
            assert!(c.ev("presend_live_wh_paper").is_empty());
        }
    }
    // no row c fill: the disarm drops it
    let mut c = Ctx::new(&["--presend-live-wh-loss", "2:0.05", "--presend-live-wh-learn", "paper"]);
    c.seed(whale, 2, -60_000_000);
    c.t2(whale);
    let sig = c.ev("presend_live_skip").pop().unwrap()["trig"]["sig"].as_str().unwrap().to_string();
    c.p.on_shadow_rec(&serde_json::json!({"ev": "presend_arm", "w": 9, "sig": sig}));
    c.p.on_shadow_rec(&serde_json::json!({"ev": "presend_disarm", "w": 9}));
    c.p.on_shadow_rec(&serde_json::json!({"ev": "presend_exit", "w": 9, "row": "c", "net_cheap": 0.2}));
    assert_eq!(c.p.sh.wh.lock().unwrap().all[&whale].n, 2, "no paper outcome: nothing");
    // the flags
    assert!(cfg(&["--presend-live-wh-learn", "paper"]).unwrap_err().to_string().contains("needs --presend-live-wh-loss"));
    assert!(cfg(&["--presend-live-wh-loss", "2:0.05", "--presend-live-wh-learn", "on"]).unwrap_err().to_string().contains("paper | off"));
    assert!(crate::check_flags(&args(&["--presend-live-wh-loss", "2:0.05", "--presend-live-wh-learn", "paper", "--presend-live-wh-split", "on"])).is_ok());
}

/// --presend-live-wh-split on: the gate reads the kind's ledger (a wallet's T2 losses do not block it as a re-arm dumper); every position goes
/// into the combined ledger and its kind's
#[test]
fn dip37_wh_split() {
    let mut m = WhMaps::default();
    let k = w(5);
    m.add(true, false, k, -60_000_000, false);
    m.add(true, false, k, -10_000_000, false);
    m.add(true, true, k, 5_000_000, false);
    assert_eq!((m.get(false, true, &k).n, m.get(true, false, &k).n, m.get(true, true, &k).n), (3, 2, 1));
    assert!(m.get(true, false, &k).blocks(2, 50_000_000) && !m.get(true, true, &k).blocks(2, 50_000_000) && !m.get(false, false, &k).blocks(2, 70_000_000));
    // on the probe: the dumper's T2 losses: split on -> the re-arm arms (its re-arm ledger is empty); split off (combined) -> skipped
    let (a, b) = (w(0xA1), w(0xB1));
    for split in [true, false] {
        let mut x = vec!["--presend-live-rearm", "on", "--presend-live-wh-loss", "2:0.05"];
        if split { x.extend(["--presend-live-wh-split", "on"]); }
        let mut c = Ctx::new(&x);
        { let mut g = c.p.sh.wh.lock().unwrap(); g.add(split, false, a, -100_000_000, false); g.add(split, false, a, -100_000_000, false); }
        c.rearm(a, b);
        let armed = c.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm");
        assert_eq!(armed, split, "split {split}");
    }
    assert!(cfg(&["--presend-live-wh-loss", "2:0.05", "--presend-live-wh-split", "on"]).unwrap().unwrap().wh_spec().contains("split"));
}

// ---- dip37 HOLDER LEDGER (pshl.rs) and the ledgers' control file ----------------------------------------------------------------------

impl Ctx {
    /// T2 on token 0x64: created at 1000, holder `h` buys `h_tok` raw at 1001, the whale's 2 SOL buy at 1005
    fn t2h(&mut self, h: Pk, h_tok: u64, whale: Pk) -> Tk {
        let mut tk = Tk::new(0x64);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, vec![dev], vec![tk.create()]);
        let e = tk.buy_tok(h, h_tok);
        self.tx(1001, 2, vec![e], vec![]);
        let e = tk.buy(whale, 2 * S);
        self.tx(1005, 50, vec![e], vec![]);
        tk
    }
    fn hseed(&self, k: Pk, n: u32, sum: i64, best: i64) { self.p.sh.hl.lock().unwrap().insert(k, pshl::HlHist { n, sum, best, pn: 0, ps: 0 }); }
}

const HL: [&str; 2] = ["--presend-live-holder-loss", "2:0.10:0.05"];

#[test]
fn dip37_hl_flags_and_rule() {
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(!c0.hl_on() && c0.ledger_ctl.is_none() && c0.json().get("holder_loss").is_none());
    let c = cfg(&["--presend-live-holder-loss", "2:0.10:0.05", "--presend-live-holder-state", "/tmp/h.json", "--presend-live-holder-learn", "paper"]).unwrap().unwrap();
    assert!(c.hl_on() && (c.hl_pct, c.hl_loss, c.hl_win) == (2.0, 100_000_000, 50_000_000) && c.hl_learn && c.json()["holder_loss"] == "2:0.1:0.05");
    for (a, needle) in [(&["--presend-live-holder-loss", "2:0.1"][..], "PCT:SOL:WIN"), (&["--presend-live-holder-loss", "0:0.1:0.05"][..], "PCT:SOL:WIN"),
        (&["--presend-live-holder-state", "/x"][..], "needs --presend-live-holder-loss"), (&["--presend-live-holder-learn", "paper"][..], "needs --presend-live-holder-loss"),
        (&["--presend-live-holder-loss", "2:0.1:0.05", "--presend-live-holder-learn", "yes"][..], "paper | off"),
        (&["--presend-live-ledger-control", "/x"][..], "needs --presend-live-wh-loss, --presend-live-holder-loss, --presend-live-botdepth or --presend-live-dumper-ledger")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    assert!(crate::check_flags(&args(&["--presend-live-holder-loss", "2:0.10:0.05", "--presend-live-holder-state", "/x", "--presend-live-holder-learn", "paper",
        "--presend-live-ledger-control", "/y"])).is_ok());
    // the rule's boundary: >= 1 position, sum <= -SOL, best < WIN
    let h = |n, sum, best| pshl::HlHist { n, sum, best, pn: 0, ps: 0 };
    assert!(h(1, -100_000_000, -100_000_000).blocks(100_000_000, 50_000_000), "exactly -0.10 blocks");
    assert!(!h(1, -99_999_999, -99_999_999).blocks(100_000_000, 50_000_000));
    assert!(!h(3, -300_000_000, 50_000_000).blocks(100_000_000, 50_000_000), "a +0.05 win protects");
    assert!(h(3, -300_000_000, 49_999_999).blocks(100_000_000, 50_000_000));
    assert!(!h(0, 0, i64::MIN).blocks(100_000_000, 50_000_000) && !pshl::HlHist::default().blocks(100_000_000, 50_000_000));
}

/// T2: a holder >= 2% in the ledger -> "holder_loss" (hl_wallet / hl_pct / hl_sum); under 2% / the whale itself / protected: armed; off = dip36
#[test]
fn dip37_hl_t2_skip() {
    let (h, whale) = (w(0x41), w(0xEE));
    let mut c = Ctx::new(&HL);
    c.hseed(h, 1, -150_000_000, -150_000_000);
    c.t2h(h, pct(3.0), whale);
    let s = c.ev("presend_live_skip").pop().expect("skipped");
    assert!(s["why"] == "holder_loss" && s["hl_wallet"] == b58(&h) && s["hl_pct"] == 3.0 && s["hl_sum"] == -0.15 && s.get("hl_would").is_none(), "{s}");
    assert!(c.p.status().contains(" | HOLDER LEDGER 1: skips T2 1 re-arm 0") && c.p.status().contains("LEDGER MODES whale live holder live"), "{}", c.p.status());
    // just under 2%: armed
    let mut c = Ctx::new(&HL);
    c.hseed(h, 1, -150_000_000, -150_000_000);
    c.t2h(h, pct(2.0) - 1, whale);
    assert!(c.ev("presend_live_arm").len() == 1 && c.ev("presend_live_skip").is_empty());
    // the whale in the holder ledger: never its own holder
    let mut c = Ctx::new(&HL);
    c.hseed(whale, 5, -900_000_000, -100_000_000);
    c.t2h(h, pct(3.0), whale);
    assert_eq!(c.ev("presend_live_arm").len(), 1);
    // protected by a win
    let mut c = Ctx::new(&HL);
    c.hseed(h, 4, -400_000_000, 60_000_000);
    c.t2h(h, pct(3.0), whale);
    assert_eq!(c.ev("presend_live_arm").len(), 1);
    // off: the same records as on with nobody in the ledger
    let mut c0 = Ctx::new(&[]);
    c0.t2h(h, pct(3.0), whale);
    let mut c1 = Ctx::new(&HL);
    c1.t2h(h, pct(3.0), whale);
    assert_eq!(strip(&c0.recs), strip(&c1.recs));
    assert!(c0.p.hls.keys.is_empty() && c1.p.hls.keys.values().next().is_some_and(|k| k == &vec![h]), "the window's keys: the holder");
}

/// re-arm: the remaining 8% holder (b) in the ledger -> "rearm_holder_loss"; the dumper (a) in the ledger: not a holder
#[test]
fn dip37_hl_rearm() {
    let (a, b) = (w(0xA1), w(0xB1));
    let run = |k: Pk| { let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-holder-loss", "2:0.10:0.05"]); c.hseed(k, 1, -200_000_000, -200_000_000); c.rearm(a, b); c };
    let c = run(b);
    let s = c.ev("presend_live_skip").into_iter().find(|r| r["why"] == "rearm_holder_loss").expect("skipped");
    assert!(s["kind"] == "rearm" && s["hl_wallet"] == b58(&b) && s["hl_pct"] == 8.0, "{s}");
    assert_eq!(c.p.hls.skips, [0, 1]);
    let c = run(a);
    assert!(c.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm"), "the dumper sold out and is excluded");
}

/// the control file: log mode = the verdict logged (hl_would / wh_would), nothing skipped; a change is re-read and logged; a bad file keeps
/// the last good modes
#[test]
fn dip37_ledger_control() {
    let (h, whale) = (w(0x41), w(0xEE));
    let p = tmp("ctl");
    std::fs::write(&p, r#"{"whale": "log", "holder": "log"}"#).unwrap();
    let mut c = Ctx::new(&["--presend-live-holder-loss", "2:0.10:0.05", "--presend-live-wh-loss", "2:0.05", "--presend-live-ledger-control", &p]);
    c.p.ledger_ctl_open();
    assert_eq!(c.p.hls.live, [false, false]);
    c.hseed(h, 1, -150_000_000, -150_000_000);
    c.seed(whale, 2, -60_000_000);
    c.t2h(h, pct(3.0), whale);
    let a = c.ev("presend_live_arm").pop().expect("log mode: armed");
    assert!(a["hl_would"] == true && a["wh_would"] == true && a["hl_wallet"] == b58(&h) && a["wh_sum_hit"] == true, "{a}");
    assert_eq!(c.p.hls.would, [1, 0]);
    let m = c.ev("presend_live_ledger_mode");
    assert!(m.len() == 1 && m[0]["whale"] == "log" && m[0]["holder"] == "log" && m[0]["was"]["holder"] == "live", "{m:?}");
    // to live (forced re-read): the next trigger is skipped
    std::fs::write(&p, r#"{"whale": "log", "holder": "live"}"#).unwrap();
    c.p.ledger_ctl_check(true);
    assert_eq!(c.p.hls.live, [false, true]);
    // a bad file: the modes stay, an error record
    std::fs::write(&p, r#"{"holder": "maybe"}"#).unwrap();
    c.p.ledger_ctl_check(true);
    assert_eq!(c.p.hls.live, [false, true]);
    for o in c.orx.try_iter() { if let Out::Rec(v) = o { c.recs.push(v); } }
    assert!(c.ev("presend_live_ledger_mode").iter().any(|r| r["ok"] == false));
    std::fs::remove_file(&p).unwrap();
    c.p.ledger_ctl_check(true);
    assert_eq!(c.p.hls.live, [false, true], "a missing file keeps them");
    assert!(pshl::ctl_parse(br#"{"whale": "live"}"#).unwrap() == [true, true] && pshl::ctl_parse(b"[]").is_err());
    // the shipped r57 control file: whale LOG, holder LIVE
    let shipped = std::fs::read(concat!(env!("CARGO_MANIFEST_DIR"), "/ops/prod/ledger_control.json")).unwrap();
    assert_eq!(pshl::ctl_parse(&shipped).unwrap(), [false, true]);
}

/// learning: the realized lookup carries the window's holder keys; the state round trip; the holder paper learning
#[test]
fn dip37_hl_learn_state_paper() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let (h, whale) = (w(0x41), w(0xEE));
    let mut c = Ctx::new(&HL);
    let mut tk = c.t2h(h, pct(3.0), whale);
    let id = *c.p.armed.get(&tk.mint).unwrap();
    let mut sg = [0u8; 64]; sg[0] = 0xD3; sg[1] = 0x78;
    c.atx.send(Att { w: id, n: 1, mint: tk.mint, sig: sg, tag: pl::PS_TAG | 0xD378, path: "helius-ps".into(), client: "JitoLabs".into(), slot: 1006, deadline: 1007,
        lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (1006, 0, 0), t_send: 1_006_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
        tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46: Default::default(), rf: None, rg: None }).unwrap();
    c.p.drain_atts();
    let h2 = w(0x42);
    let e = tk.buy_tok(h2, pct(2.5)); c.tx(1006, 3, vec![e], vec![]);          // a new 2.5% holder before our landing
    let e = tk.buy(USER, 396_000_000);
    c.tx_sig(1007, 4, sg, USER, vec![e.clone()], vec![]);
    assert_eq!(c.p.hls.keys[&id], vec![h, h2], "the arm's holder and the one at our landing");
    let mut z = Tk::new(0x7E);
    c.launches.push(z.launch.clone());
    let dz = z.buy(CREATOR, S / 2);
    c.tx(1007, 900, vec![dz], vec![z.create()]);
    for s in 1008..=1009 { let e = z.buy([0x2F; 32], 1_000_000); c.tx(s, 900, vec![e], vec![]); }
    let Some(Cmd::Sell { pid, .. }) = c.cmds.iter().find(|x| matches!(x, Cmd::Sell { .. })).cloned() else { panic!("{:?}", c.cmds) };
    let es = tk.sell_tok(USER, e.tok);
    c.tx_sig(1009, 9, { let mut s = [0u8; 64]; s[0] = 0x5E; s[1] = 0x38; s }, USER, vec![es], vec![]);
    c.p.on_msg(PsMsg::Sold(tk.mint, pid, 1, sold(Some(1009), &["S38"], e.tok)), &|_| false);
    c.cmds.extend(c.p.take_cmds());
    let Some(Cmd::Realized { hl, .. }) = c.cmds.iter().find(|x| matches!(x, Cmd::Realized { .. })).cloned() else { panic!("{:?}", c.cmds) };
    assert_eq!(hl, vec![h, h2]);
    // the state round trip (paper marked)
    let p = tmp("hstate");
    let mut m = FxHashMap::default();
    m.insert(h, pshl::HlHist { n: 2, sum: -120_000_000, best: -20_000_000, pn: 1, ps: -20_000_000 });
    m.insert(h2, pshl::HlHist { n: 1, sum: 70_000_000, best: 70_000_000, pn: 0, ps: 0 });
    assert_eq!(pshl::hl_save(&m, &p).unwrap(), 2);
    assert_eq!(pshl::hl_load(&p).unwrap(), m);
    std::fs::remove_file(&p).unwrap();
    if let Ok(b) = std::fs::read("/home/it/sniper-data/dip37stage/holder_state_ams.json") { assert!(pshl::hl_parse_state(&b).unwrap().len() > 1000, "the staged seed parses"); }
    // paper: a holder_loss-skipped trigger's row c into the holder's ledger
    let mut c = Ctx::new(&["--presend-live-holder-loss", "2:0.10:0.05", "--presend-live-holder-learn", "paper"]);
    c.hseed(h, 1, -150_000_000, -150_000_000);
    c.t2h(h, pct(3.0), whale);
    let sig = c.ev("presend_live_skip").pop().unwrap()["trig"]["sig"].as_str().unwrap().to_string();
    for r in [serde_json::json!({"ev": "presend_arm", "w": 5, "sig": sig}), serde_json::json!({"ev": "presend_fill", "w": 5, "row": "c", "entry": {"sol_in": 400_000_000u64}}),
              serde_json::json!({"ev": "presend_exit", "w": 5, "row": "c", "net_cheap": 0.2})] { c.p.on_shadow_rec(&r); }
    let g = c.p.sh.hl.lock().unwrap()[&h];
    assert_eq!(g, pshl::HlHist { n: 2, sum: 50_000_000, best: 200_000_000, pn: 1, ps: 200_000_000 }, "the paper win protects it now");
}

// ===================================================================================================================
// dip38 PSM12-S1 tests (pss1.rs: --presend-live-s1-log on|off, --presend-live-s1 off|t2|rearm|t2,rearm, --presend-live-s1-parts, the ledger
// control file's "s1"). The rule's reasons and their order at every boundary; the whale history = real positions only; the flags; the LOG
// changes nothing else (records but its fields, the chain work, the sender's window and the signed attempt bytes); "s1" on the arm, the fill
// and the realized; the re-arm (dumper, age exempt, its own dump never counted); the live gate OFF by default, ON per kind / per parts;
// the control file's override.
// ===================================================================================================================
use super::*;
use super::pss1::*;
use super::pswh::WhHist;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;
/// a whale ledger whose own rule never blocks in these tests (n >= 5 and sum <= -1 SOL)
const WH: [&str; 2] = ["--presend-live-wh-loss", "5:1.0"];

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000) }
fn with_wh(extra: &[&str]) -> Vec<&'static str> {
    let mut v: Vec<&'static str> = WH.to_vec();
    v.extend(extra.iter().map(|s| &*Box::leak(s.to_string().into_boxed_str())));
    v
}
fn pctr(x: f64) -> u64 { (x / 100.0 * pl::SUPPLY).round() as u64 }
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x51; x }
fn tmp(name: &str) -> String { std::env::temp_dir().join(format!("dip38-s1-{}-{name}", std::process::id())).to_string_lossy().to_string() }
fn sold(c: Option<u64>, sigs: &[&str], qty: u64) -> SellOut {
    SellOut { sold_at: c, sigs: sigs.iter().map(|s| (s.to_string(), true, 1_200_000)).collect(), last: None, attempts: sigs.len() as u32, last_qty: (qty, true), first_send_us: None }
}
fn hist(n: u32, sum: i64) -> WhHist { WhHist { n, sum, ..Default::default() } }

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
    fn pump(&mut self) {
        for o in self.orx.try_iter() { match o { Out::Rec(v) => self.recs.push(v), Out::Line(l) => self.lines.push(l) } }
        self.cmds.extend(self.p.take_cmds());
    }
    fn tx_sig(&mut self, slot: u64, idx: u64, sig: [u8; 64], payer: Pk, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let ls = self.launches.clone();
        self.p.on_arrival(&a, slot);
        self.p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
        self.pump();
    }
    fn tx(&mut self, slot: u64, idx: u64, payer: Pk, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0x51; sig[17] = trades.first().map_or(0, |t| t.mint[0]);
        self.tx_sig(slot, idx, sig, payer, trades, creates);
    }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    fn seed(&self, k: Pk, h: WhHist) { self.p.sh.wh.lock().unwrap().all.insert(k, h); }
    /// a scored dump of `mint` at (slot, idx) into the nd counter (as dipmode's dump record would; nothing with the counter off)
    fn note(&mut self, mint: Pk, s: u64, i: u32) { if let Some(h) = self.p.h2.as_mut() { h.note(mint, s, i, Some(0.01)); } }
    /// T2 on token `k` created at 1000; `nd` scored dumps noted at (1001, i) before the trigger, one after it; the whale's 8% at
    /// 1000 + age, idx 50 (the trigger)
    fn t2(&mut self, k: u8, age: u64, nd: u32, whale: Pk) -> Tk {
        let mut tk = Tk::new(k);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, CREATOR, vec![dev], vec![tk.create()]);
        let e = tk.buy(w(0x11), S / 10);
        self.tx(1001, 2, w(0x11), vec![e], vec![]);
        for i in 0..nd { self.note(tk.mint, 1001, 10 + i); }
        self.note(tk.mint, 1000 + age, 60);          // same slot, after the trigger's index: never counted
        let e = tk.buy_tok(whale, pctr(8.0));
        self.tx(1000 + age, 50, whale, vec![e], vec![]);
        tk
    }
    /// an attempt of window `id` at `slot` (the sender's registration) -> drain_atts
    fn att(&mut self, id: u64, mint: Pk, slot: u64, tag: u8) -> [u8; 64] {
        let mut sg = [0u8; 64]; sg[0] = 0xD3; sg[1] = 0x51; sg[2] = tag; sg[3] = slot as u8;
        self.atx.send(Att { w: id, n: 1, mint, sig: sg, tag: pl::PS_TAG | (tag as u64), path: "helius-ps".into(), client: "JitoLabs".into(), slot, deadline: slot + 1,
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (slot, 0, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
            tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None }).unwrap();
        self.p.drain_atts();
        self.pump();
        sg
    }
    /// fill with attempt `sg` at slot `b`, a filler token moves the clock to the exit, the sell lands, the round ends -> the Cmd::Realized
    fn fill_close(&mut self, tk: &mut Tk, sg: [u8; 64], b: u64, filler: u8) -> Cmd {
        let e = tk.buy(USER, 396_000_000);
        self.tx_sig(b, 4, sg, USER, vec![e.clone()], vec![]);
        let mut z = Tk::new(filler);
        self.launches.push(z.launch.clone());
        let dz = z.buy(CREATOR, S / 2);
        self.tx(b, 900, CREATOR, vec![dz], vec![z.create()]);
        for s in b + 1..=b + 2 { let e = z.buy([0x2F; 32], 1_000_000); self.tx(s, 900, [0x2F; 32], vec![e], vec![]); }
        let Some(Cmd::Sell { pid, .. }) = self.cmds.iter().rev().find(|x| matches!(x, Cmd::Sell { .. })).cloned() else { panic!("no sell: {:?}", self.cmds) };
        let es = tk.sell_tok(USER, e.tok);
        self.tx_sig(b + 2, 9, { let mut s = [0u8; 64]; s[0] = 0x5E; s[1] = 0x51; s[2] = filler; s }, USER, vec![es], vec![]);
        self.p.on_msg(PsMsg::Sold(tk.mint, pid, 1, sold(Some(b + 2), &["S51"], e.tok)), &|_| false);
        self.pump();
        self.cmds.iter().rev().find(|x| matches!(x, Cmd::Realized { .. })).cloned().expect("realized")
    }
    /// re-arm on token 0x62: a 7% / b 8% at 1000 (token age 0), `nd` scored dumps noted at (1002, i), a's dump at (1005, 5) noted too (its own,
    /// never counted), the check at 1008 (a filler token's slots)
    fn rearm(&mut self, nd: u32, a: Pk) -> Tk {
        let b = w(0xB1);
        let mut tk = Tk::new(0x62);
        let mut z = Tk::new(0x63);
        self.launches.push(tk.launch.clone());
        self.launches.push(z.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, CREATOR, vec![dev], vec![tk.create()]);
        let e = tk.buy_tok(a, pctr(7.0)); self.tx(1000, 2, a, vec![e], vec![]);
        let e = tk.buy_tok(b, pctr(8.0)); self.tx(1000, 3, b, vec![e], vec![]);
        let dz = z.buy(CREATOR, S / 2);
        self.tx(1000, 4, CREATOR, vec![dz], vec![z.create()]);
        for s in 1001..=1004 { let e = tk.buy(w(0x33), S / 10); self.tx(s, 5, w(0x33), vec![e], vec![]); }
        for i in 0..nd { self.note(tk.mint, 1002, 20 + i); }
        self.note(tk.mint, 1005, 5);
        let d = tk.sell_tok(a, pctr(7.0));
        self.tx(1005, 5, a, vec![d], vec![]);
        for s in 1006..=1008 { let e = z.buy(w(0x2F), 1_000_000); self.tx(s, 900, w(0x2F), vec![e], vec![]); }
        tk
    }
}

/// the records with S1's and the nd counter's fields out (the counter runs with the S1 log), the wall-clock fields out
fn recs_wo_s1(v: &[serde_json::Value]) -> Vec<String> {
    v.iter().map(|r| {
        let mut r = r.clone();
        if let Some(o) = r.as_object_mut() {
            for k in ["s1", "nd", "m2max", "h2_keep", "h2_size"] { o.remove(k); }
            match o.get("ev").and_then(|e| e.as_str()) {
                Some("presend_live_disarm") => { o.remove("armed_ms"); o.remove("t"); }
                Some("presend_live_exit") => { o.remove("t"); }
                Some("presend_live_close") => { o.remove("held_s"); }
                _ => {}
            }
        }
        r.to_string()
    }).collect()
}
fn cmds_wo_s1(v: &[Cmd]) -> Vec<String> {
    v.iter().map(|c| match c.clone() {
        Cmd::Realized { pid, w, mint, buys, sells, rearm, cr, ab, wh, hl, l38, .. } => format!("{:?}", Cmd::Realized { pid, w, mint, buys, sells, rearm, cr, ab, wh, hl, l38, s1: None, wd: None }),
        x => format!("{x:?}"),
    }).collect()
}
fn signed(ixs: &[build::Ix]) -> Vec<u8> { build::sign(&build::compile_v0(USER, ixs, [9u8; 32], &[], &[]).unwrap(), &SigningKey::from_bytes(&[7u8; 32])) }
/// the sender's view of a window that the attempt bytes depend on, and those bytes
fn swin_view(c: &Ctx, id: u64) -> (String, Vec<u8>) {
    let sw = c.p.sh.wins.lock().unwrap().iter().find(|x| x.id == id).cloned().expect("window");
    let v = format!("{} {:?} {:?} {} {} {} {} {:?} {} {} {} {:?} {:?} {}", sw.id, sw.mint, sw.launch, sw.en_slot, sw.vsol, sw.vtok, sw.fr, sw.pos, sw.spend, sw.rearm, sw.ob6, sw.blk, sw.fab, sw.done);
    let (min_out, _, _) = att_limit(&sw, c.p.cfg.drop).unwrap();
    let (ixs, _) = att_ixs(USER, &sw, min_out, &c.p.cfg, guard_ix_enc(GuardEnc { disc: 15, op: 4, acct: true }, 1006), Some(([0x71; 32], 200_000)));
    (v, signed(&ixs))
}

/// every reason, its boundary and the rule order (nd, age, whale, cold); the re-arm's age exemption; the parts; real positions only
#[test]
fn dip38_s1_rule_order() {
    let (l2, l20) = (-20_000_000i64, -19_999_999i64);
    // keep: nd 2, T2 age 50, a known whale above the loss line
    assert_eq!(s1_why(false, 2, 50, 1, l20, P_ALL), None);
    assert_eq!(s1_why(false, 2, 50, 3, 100_000_000, P_ALL), None);
    // nd: < 2 fails first, whatever else fails too
    assert_eq!(s1_why(false, 1, 0, 1, l2, P_ALL), Some("nd"));
    assert_eq!(s1_why(true, 0, 0, 0, 0, P_ALL), Some("nd"));
    // age: T2 only, 49 fails, 50 passes; before the whale
    assert_eq!(s1_why(false, 2, 49, 1, l2, P_ALL), Some("age"));
    assert_eq!(s1_why(true, 2, 0, 1, l20, P_ALL), None, "a re-arm is exempt from the age");
    // whale: n >= 1 and sum <= -0.02 (exactly -0.02 fails); before cold
    assert_eq!(s1_why(false, 2, 50, 1, l2, P_ALL), Some("whale"));
    assert_eq!(s1_why(true, 9, 0, 4, -500_000_000, P_ALL), Some("whale"));
    assert_eq!(s1_why(false, 2, 50, 1, l20, P_ALL), None, "-0.019999999 passes");
    // cold: n == 0 and nd < 8 fails; nd 8 passes
    assert_eq!(s1_why(false, 7, 50, 0, 0, P_ALL), Some("cold"));
    assert_eq!(s1_why(false, 8, 50, 0, 0, P_ALL), None);
    assert_eq!(s1_why(true, 2, 0, 0, 0, P_ALL), Some("cold"));
    // the parts: only the given ones act, in the same order
    assert_eq!(s1_why(false, 1, 10, 0, 0, P_AGE | P_COLD), Some("age"));
    assert_eq!(s1_why(false, 2, 50, 1, l2, P_ND | P_AGE), None, "whale not a live part");
    assert_eq!(s1_why(false, 3, 50, 0, 0, P_ND | P_AGE | P_WHALE), None, "cold not a live part");
    assert_eq!(s1_why(false, 3, 50, 0, 0, P_COLD), Some("cold"));
    // S1V: paper positions of --presend-live-wh-learn paper are taken out (the study's ledger is realized positions only)
    let v = S1V::new(false, 3, 60, &WhHist { n: 3, sum: -40_000_000, pn: 2, ps: -50_000_000 }, P_ALL);
    assert!(v.n == 1 && v.sum == 10_000_000 && v.why.is_none() && v.pn == 2, "{v:?}");
    let v = S1V::new(false, 3, 60, &WhHist { n: 1, sum: -40_000_000, pn: 1, ps: -40_000_000 }, P_ND | P_AGE);
    assert!(v.n == 0 && v.why == Some("cold") && v.pwhy.is_none(), "only paper: cold for the log, kept by the nd,age live parts: {v:?}");
    let j = v.json(P_ND | P_AGE, false, 400_000_000, 31 * S, 2.5e-8);
    assert!(j["kind"] == "T2" && j["keep"] == false && j["why"] == "cold" && j["cold"] == true && j["parts"] == "nd,age" && j["pwhy"].is_null() && j["wh_paper_n"] == 1
        && j["spend"] == 400_000_000u64 && j["vsol"] == 31 * S && j["live"] == false, "{j}");
    assert!(S1V::new(true, 2, 0, &hist(2, 5), P_ALL).json(P_ALL, true, 1, 1, 1.0).get("parts").is_none());
    // names, parts parse / print
    assert_eq!((skip_name(false, "nd"), skip_name(true, "cold"), skip_name(false, "whale"), skip_name(true, "age")), ("s1_nd", "rearm_s1_cold", "s1_whale", "rearm_s1_age"));
    assert_eq!(parts_parse("nd,age").unwrap(), P_ND | P_AGE);
    assert_eq!(parts_parse("all").unwrap(), P_ALL);
    assert_eq!(parts_str(P_ALL), "nd,age,whale,cold");
    assert!(parts_parse("nd,size").is_err() && parts_parse("").is_err() && parts_parse(",").is_err());
}

/// off by default; the log needs the whale ledger; the live gate and the parts need the log; values; the start record
#[test]
fn dip38_s1_flags() {
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(!c0.s1_log && c0.s1_live == 0 && c0.s1_parts == P_ALL && !c0.m2seen_on() && c0.json().get("s1").is_none(), "off by default");
    let c = cfg(&with_wh(&["--presend-live-s1-log", "on"])).unwrap().unwrap();
    assert!(c.s1_log && c.s1_live == 0 && c.m2seen_on(), "the log turns the nd counter on");
    let j = c.json();
    assert!(j["s1"]["log"] == true && j["s1"]["live"] == "off" && j["s1"]["parts"] == "nd,age,whale,cold" && j["s1"]["nd"] == 2 && j["s1"]["age"] == 50 && j["s1"]["wh_loss"] == 0.02
        && j["s1"]["cold_nd"] == 8, "{j}");
    let c = cfg(&with_wh(&["--presend-live-s1-log", "on", "--presend-live-s1", "t2,rearm", "--presend-live-s1-parts", "nd,age"])).unwrap().unwrap();
    assert!(c.s1_live == 3 && c.s1_parts == P_ND | P_AGE && c.json()["s1"]["live"] == "t2,rearm");
    assert_eq!(cfg(&with_wh(&["--presend-live-s1-log", "on", "--presend-live-s1", "rearm"])).unwrap().unwrap().s1_live, 2);
    assert_eq!(cfg(&with_wh(&["--presend-live-s1-log", "on", "--presend-live-s1", "off"])).unwrap().unwrap().s1_live, 0);
    for (a, needle) in [(vec!["--presend-live-s1-log", "on"], "needs --presend-live-wh-loss"),
        (with_wh(&["--presend-live-s1-log", "yes"]), "on | off"),
        (with_wh(&["--presend-live-s1", "t2"]), "needs --presend-live-s1-log on"),
        (with_wh(&["--presend-live-s1-log", "off", "--presend-live-s1", "t2"]), "needs --presend-live-s1-log on"),
        (with_wh(&["--presend-live-s1-parts", "nd"]), "needs --presend-live-s1-log on"),
        (with_wh(&["--presend-live-s1-log", "on", "--presend-live-s1", "both2"]), "t2 | rearm"),
        (with_wh(&["--presend-live-s1-log", "on", "--presend-live-s1-parts", "nd,size"]), "--presend-live-s1-parts"),
        (with_wh(&["--presend-live-s1-log", "on", "--presend-live-s1"]), "needs a value"),
        (with_wh(&["--presend-live-s1-log", "on", "--presend-live-s1-parts", "--presend-live-k"]), "needs a value")] {
        let e = cfg(&a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    for f in ["--presend-live-s1-log", "--presend-live-s1", "--presend-live-s1-parts"] {
        let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", f, "on"].iter().map(|s| s.to_string()).collect::<Vec<_>>(), &arbx::presend::Params::default(), true, 1_000_000_000)
            .unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
    assert!(crate::check_flags(&args(&with_wh(&["--presend-live-s1-log", "on", "--presend-live-s1", "off", "--presend-live-s1-parts", "nd,age,whale,cold"]))).is_ok());
}

/// LOG ON = only its fields: every other record, the chain work, the sender's window and the SIGNED ATTEMPT BYTES equal the log-off run;
/// "s1" on the arm (the verdict and its inputs), on the fill and on the realized; off: no "s1" anywhere, no nd counter
#[test]
fn dip38_s1_log_changes_nothing_else() {
    let _g = super::dip37_h2_tests::H2_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let _a = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let whale = w(0xEE);
    let run = |extra: &[&str]| {
        let mut c = Ctx::new(&with_wh(extra));
        // the whale: one earlier position -0.03 SOL (the live ledger 5:1.0 lets it through; S1 says "whale")
        c.seed(whale, hist(1, -30_000_000));
        let mut tk = c.t2(0x61, 60, 3, whale);
        let id = c.p.armed[&tk.mint];
        let view = swin_view(&c, id);
        let sg = c.att(id, tk.mint, 1061, 1);
        c.att(id, tk.mint, 1062, 2);
        let rz = c.fill_close(&mut tk, sg, 1062, 0x7F);
        let end = c.p.finish(1070, None);
        (c, view, rz, end)
    };
    let (mut c0, v0, rz0, end0) = run(&[]);
    let (mut c1, v1, rz1, end1) = run(&["--presend-live-s1-log", "on"]);
    assert!(c0.ev("presend_live_arm").len() == 1 && c0.ev("presend_live_fill").len() == 1 && c0.ev("presend_live_close").len() == 1, "armed, filled, closed: {:?}", c0.recs);
    assert_eq!(v0, v1, "the sender's window and the signed attempt bytes: the same");
    assert_eq!(recs_wo_s1(&c0.recs), recs_wo_s1(&c1.recs), "every record the same but S1's fields");
    assert_eq!(cmds_wo_s1(&c0.cmds), cmds_wo_s1(&c1.cmds), "the same chain work");
    // off: nothing of it
    assert!(c0.recs.iter().all(|r| r.get("s1").is_none() && r.get("nd").is_none()) && c0.p.h2.is_none() && c0.p.s1.w.is_empty());
    assert!(matches!(rz0, Cmd::Realized { s1: None, .. }) && end0.get("s1").is_none() && !c0.p.status().contains(" S1 "));
    // on: the arm's verdict (nd 3: the dump after the trigger not counted; age 60; whale 1 position -0.03 -> "whale")
    let a = c1.ev("presend_live_arm").pop().unwrap();
    let s = &a["s1"];
    assert!(s["kind"] == "T2" && s["nd"] == 3 && s["age"] == 60 && s["wh_n"] == 1 && s["wh_s"] == -0.03 && s["cold"] == false && s["keep"] == false && s["why"] == "whale"
        && s["live"] == false && s["spend"] == 400_000_000u64 && s["vsol"].as_u64().unwrap() > 30 * S && s["p"].as_f64().unwrap() > 0.0, "{a}");
    assert!(a["nd"] == 3, "the counter's own field agrees: {a}");
    let f = c1.ev("presend_live_fill").pop().unwrap();
    assert!(f["s1"]["keep"] == false && f["s1"]["why"] == "whale" && f["s1"]["kind"] == "T2", "{f}");
    let Cmd::Realized { s1: Some(z), .. } = rz1 else { panic!("no s1 on the realized: {rz1:?}") };
    assert!(z["keep"] == false && z["why"] == "whale" && z["nd"] == 3, "{z}");
    assert!(end1["s1"]["mode"] == "off" && end1["s1"]["arms"]["t2"]["whale"] == 1 && end1["s1"]["fills"]["t2"]["whale"] == 1 && end1["s1"]["skips"]["t2"]["whale"] == 0, "{}", end1["s1"]);
    assert!(c1.p.status().contains(" | S1 LOG (parts nd,age,whale,cold): T2 arms keep 0 | nd 0 age 0 whale 1 cold 0"), "{}", c1.p.status());
}

/// T2 on the probe, each reason (log only: always armed); default off = never a skip
#[test]
fn dip38_s1_t2_reasons_log() {
    let _g = super::dip37_h2_tests::H2_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    // (age, nd, whale history, expected why)
    for (age, nd, h, why) in [(60u64, 1u32, hist(3, 50_000_000), Some("nd")), (20, 4, hist(3, 50_000_000), Some("age")), (60, 2, hist(2, -20_000_000), Some("whale")),
        (60, 7, hist(0, 0), Some("cold")), (60, 8, hist(0, 0), None), (60, 2, hist(1, 1), None), (50, 2, hist(1, -19_999_999), None)] {
        let whale = w(0xE0);
        let mut c = Ctx::new(&with_wh(&["--presend-live-s1-log", "on"]));
        if h.n > 0 { c.seed(whale, h); }
        c.t2(0x61, age, nd, whale);
        let a = c.ev("presend_live_arm").pop().unwrap_or_else(|| panic!("log only: armed ({age} {nd} {h:?}): {:?}", c.recs));
        assert!(a["s1"]["why"] == serde_json::json!(why) && a["s1"]["keep"] == why.is_none() && a["s1"]["nd"] == nd && a["s1"]["age"] == age, "{age} {nd} {h:?}: {a}");
        assert!(c.ev("presend_live_skip").is_empty());
    }
}

/// the re-arm: keyed on the DUMPER, age exempt (token age 5), its own dump never counted; the verdict on the arm; the live gate's re-arm skip
#[test]
fn dip38_s1_rearm() {
    let _g = super::dip37_h2_tests::H2_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let dumper = w(0xA1);
    let mut c = Ctx::new(&with_wh(&["--presend-live-rearm", "on", "--presend-live-s1-log", "on"]));
    c.seed(dumper, hist(2, 30_000_000));
    c.rearm(2, dumper);
    let a = c.ev("presend_live_arm").into_iter().find(|r| r["kind"] == "rearm").expect("armed");
    let s = &a["s1"];
    assert!(s["kind"] == "rearm" && s["nd"] == 2 && s["age"] == 5 && s["wh_n"] == 2 && s["keep"] == true && s["why"].is_null() && s["spend"] == 400_000_000u64, "{a}");
    assert_eq!(c.p.s1.arms[1], [1, 0, 0, 0, 0]);
    // the own dump only: nd 1 -> "nd" (log: armed)
    let mut c = Ctx::new(&with_wh(&["--presend-live-rearm", "on", "--presend-live-s1-log", "on"]));
    c.seed(dumper, hist(2, 30_000_000));
    c.rearm(1, dumper);
    let a = c.ev("presend_live_arm").into_iter().find(|r| r["kind"] == "rearm").expect("log only: armed");
    assert!(a["s1"]["nd"] == 1 && a["s1"]["why"] == "nd", "{a}");
    // a cold dumper (no history), nd 3 -> "cold"; the live gate on re-arms skips it "rearm_s1_cold"
    let mut c = Ctx::new(&with_wh(&["--presend-live-rearm", "on", "--presend-live-s1-log", "on", "--presend-live-s1", "rearm"]));
    c.rearm(3, dumper);
    assert!(!c.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm"), "{:?}", c.recs);
    let s = c.ev("presend_live_skip").into_iter().find(|r| r["why"] == "rearm_s1_cold").expect("re-arm skipped");
    assert!(s["kind"] == "rearm" && s["s1"]["why"] == "cold" && s["s1"]["live"] == true && s["s1"]["wh_n"] == 0, "{s}");
    assert!(c.lines.iter().any(|l| l.contains("PRESEND LIVE REARM S1 SKIP (cold)")));
    assert_eq!(c.p.s1.skips[1], [0, 0, 0, 0, 1]);
    // the gate on T2 only: the re-arm is armed (log)
    let mut c = Ctx::new(&with_wh(&["--presend-live-rearm", "on", "--presend-live-s1-log", "on", "--presend-live-s1", "t2"]));
    c.rearm(3, dumper);
    assert!(c.ev("presend_live_arm").iter().any(|r| r["kind"] == "rearm" && r["s1"]["why"] == "cold" && r["s1"]["live"] == false));
}

/// the LIVE gate: off by default (armed); on for T2: skipped "s1_<reason>" with the record and a line; only the given parts act; a kept arm
/// arms as before
#[test]
fn dip38_s1_live_gate() {
    let _g = super::dip37_h2_tests::H2_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let whale = w(0xE1);
    for (live, parts, age, nd, h, skip) in [
        (None, None, 20u64, 1u32, hist(0, 0), None),
        (Some("t2"), None, 60, 1, hist(1, 5), Some("s1_nd")),
        (Some("t2"), None, 20, 3, hist(1, 5), Some("s1_age")),
        (Some("t2,rearm"), None, 60, 3, hist(1, -20_000_000), Some("s1_whale")),
        (Some("t2"), None, 60, 3, hist(0, 0), Some("s1_cold")),
        (Some("t2"), None, 60, 9, hist(0, 0), None),
        (Some("rearm"), None, 60, 1, hist(0, 0), None),
        (Some("t2"), Some("nd,age"), 60, 3, hist(1, -20_000_000), None),
        (Some("t2"), Some("nd,age"), 60, 3, hist(0, 0), None),
        (Some("t2"), Some("nd,age"), 20, 3, hist(0, 0), Some("s1_age")),
        (Some("t2"), Some("whale,cold"), 20, 1, hist(0, 0), Some("s1_cold")),
    ] {
        let mut x = vec!["--presend-live-s1-log", "on"];
        if let Some(l) = live { x.extend(["--presend-live-s1", l]); }
        if let Some(p) = parts { x.extend(["--presend-live-s1-parts", p]); }
        let mut c = Ctx::new(&with_wh(&x));
        if h.n > 0 { c.seed(whale, h); }
        c.t2(0x61, age, nd, whale);
        let tag = format!("{live:?} {parts:?} age {age} nd {nd} {h:?}");
        match skip {
            None => {
                let a = c.ev("presend_live_arm").pop().unwrap_or_else(|| panic!("{tag}: armed expected: {:?}", c.recs));
                assert!(a["s1"].is_object() && c.ev("presend_live_skip").is_empty(), "{tag}: {a}");
            }
            Some(why) => {
                assert!(c.ev("presend_live_arm").is_empty() && c.p.armed.is_empty(), "{tag}: {:?}", c.recs);
                let s = c.ev("presend_live_skip").pop().unwrap();
                assert!(s["why"] == why && s["s1"]["live"] == true && c.p.st.skips[why] == 1, "{tag}: {s}");
                if parts.is_some() { assert_eq!(s["s1"]["pwhy"], why.trim_start_matches("s1_"), "{tag}"); }
                assert!(c.lines.iter().any(|l| l.contains("PRESEND LIVE S1 SKIP")), "{tag}");
            }
        }
    }
}

/// the control file's "s1": live = the flag's kinds (both when the flag is off), log = off; a bad value keeps the mode; without the log it is
/// ignored (said on the mode record)
#[test]
fn dip38_s1_control_file() {
    let _g = super::dip37_h2_tests::H2_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    assert_eq!(pshl::ctl_parse_s1(br#"{"whale": "log"}"#).unwrap(), None);
    assert_eq!(pshl::ctl_parse_s1(br#"{"s1": "live"}"#).unwrap(), Some(true));
    assert_eq!(pshl::ctl_parse_s1(br#"{"s1": "log"}"#).unwrap(), Some(false));
    assert!(pshl::ctl_parse_s1(br#"{"s1": "on"}"#).is_err() && pshl::ctl_parse_s1(br#"{"s1": null}"#).unwrap().is_none());
    let whale = w(0xE2);
    let p = tmp("ctl.json");
    std::fs::write(&p, r#"{"whale": "live", "holder": "live", "s1": "live"}"#).unwrap();
    let mut c = Ctx::new(&with_wh(&["--presend-live-s1-log", "on", "--presend-live-ledger-control", &p]));
    assert_eq!(c.p.s1.mode, 0, "the flag: off");
    c.p.ledger_ctl_open();
    assert_eq!(c.p.s1.mode, 3, "live without the flag: both kinds");
    c.pump();
    let m = c.ev("presend_live_ledger_mode");
    assert!(m.len() == 1 && m[0]["s1"] == "t2,rearm" && m[0]["was"]["s1"] == "off", "{m:?}");
    c.t2(0x61, 60, 1, whale);
    assert!(c.ev("presend_live_skip").iter().any(|r| r["why"] == "s1_nd"), "{:?}", c.recs);
    // back to log: the next token arms
    std::fs::write(&p, r#"{"s1": "log"}"#).unwrap();
    c.p.ledger_ctl_check(true);
    assert_eq!(c.p.s1.mode, 0);
    c.t2(0x64, 60, 1, whale);
    assert!(c.ev("presend_live_arm").iter().any(|r| r["s1"]["why"] == "nd" && r["s1"]["live"] == false));
    // a bad value: the mode stays, an error record
    std::fs::write(&p, r#"{"s1": "maybe"}"#).unwrap();
    c.p.ledger_ctl_check(true);
    c.pump();
    assert!(c.p.s1.mode == 0 && c.ev("presend_live_ledger_mode").iter().any(|r| r["ok"] == false));
    // the flag t2: "live" means T2 only
    std::fs::write(&p, r#"{"s1": "live"}"#).unwrap();
    let mut c = Ctx::new(&with_wh(&["--presend-live-s1-log", "on", "--presend-live-s1", "t2", "--presend-live-ledger-control", &p]));
    c.p.ledger_ctl_open();
    assert_eq!(c.p.s1.mode, 1);
    // without the log: ignored, said on the record; the S1 state never moves
    std::fs::write(&p, r#"{"whale": "log", "s1": "live"}"#).unwrap();
    let mut c = Ctx::new(&with_wh(&["--presend-live-ledger-control", &p]));
    c.p.ledger_ctl_open();
    c.pump();
    let m = c.ev("presend_live_ledger_mode");
    assert!(c.p.s1.mode == 0 && m.len() == 1 && m[0]["s1_ignored"] == "needs --presend-live-s1-log on" && m[0].get("s1").is_none(), "{m:?}");
    std::fs::remove_file(&p).ok();
}

/// OFFLINE (ignored; read-only): the engine's S1 functions on a run's arm records (nd / age / wh_n / wh_sum as logged) joined to its real
/// fills (presend_live_fill) and positions (presend_live_realized) by (w, mint). S1_RUNS="a.jsonl b.jsonl" cargo test ... -- --ignored --nocapture
#[test]
#[ignore]
fn dip38_s1_rescore_runs() {
    use std::io::BufRead;
    let runs = std::env::var("S1_RUNS").expect("S1_RUNS=paths");
    for path in runs.split_whitespace() {
        let mut arms: Vec<((u64, String), S1V)> = Vec::new();
        let mut fills: FxHashMap<(u64, String), u64> = FxHashMap::default();
        let mut pnl: FxHashMap<(u64, String), i64> = FxHashMap::default();
        for l in std::io::BufReader::new(std::fs::File::open(path).unwrap()).lines() {
            let l = l.unwrap();
            if !(l.contains("\"ev\":\"presend_live_arm\"") || l.contains("\"ev\":\"presend_live_fill\"") || l.contains("\"ev\":\"presend_live_realized\"")) { continue; }
            let Ok(d) = serde_json::from_str::<serde_json::Value>(&l) else { continue };
            let w = d["w"].as_u64().unwrap_or(u64::MAX);
            match d["ev"].as_str() {
                Some("presend_live_arm") => {
                    if d["dry"] == true { continue; }
                    let rearm = d["kind"] == "rearm";
                    let mint = if rearm { d["mint"].as_str() } else { d["trig"]["mint"].as_str() }.unwrap().to_string();
                    let age = if rearm { d["dump"]["age_slots"].as_u64().unwrap_or(0) } else { d["trig"]["age_slots"].as_u64().unwrap_or(0) };
                    let h = WhHist { n: d["wh_n"].as_u64().unwrap_or(0) as u32, sum: (d["wh_sum"].as_f64().unwrap_or(0.0) * 1e9).round() as i64,
                        pn: d["wh_pn"].as_u64().unwrap_or(0) as u32, ps: (d["wh_ps"].as_f64().unwrap_or(0.0) * 1e9).round() as i64 };
                    arms.push(((w, mint), S1V::new(rearm, d["nd"].as_u64().expect("nd logged") as u32, age, &h, P_ALL)));
                }
                Some("presend_live_fill") => { *fills.entry((w, d["mint"].as_str().unwrap().to_string())).or_default() += 1; }
                Some(_) => { *pnl.entry((w, d["mint"].as_str().unwrap().to_string())).or_default() += d["pnl"].as_i64().unwrap_or(0); }
                None => {}
            }
        }
        let mut t: std::collections::BTreeMap<String, (u64, u64, i64)> = Default::default();
        for (k, v) in &arms {
            let key = match v.why { None => format!("keep {}", if v.rearm { "rearm" } else { "T2" }), Some(w) => format!("skip {w}") };
            for key in [key, if v.keep() { "keep all".into() } else { "skip all".into() }] {
                let e = t.entry(key).or_default();
                e.0 += 1; e.1 += fills.get(k).copied().unwrap_or(0); e.2 += pnl.get(k).copied().unwrap_or(0);
            }
        }
        println!("== {path}: {} arms", arms.len());
        for (k, (a, f, p)) in &t { println!("  {k:12} arms {a:4} fills {f:3} realized {:+.3}", *p as f64 / 1e9); }
    }
}

// ===================================================================================================================
// dip42 tests: FAM2 (psfam2.rs: --presend-live-fam2 on, -wallets, -slots) and the Q1 shadow log (psq1.rs: --q1-log on, --q1-bots,
// --q1-fresh-state and the thresholds). FAM2: the window's edges, distinct counting, no look-ahead, the fill's "pre" cut at the dump,
// the records (T2 arm / skip / fill / realized, re-arm arm / skip), the flags. Q1: every condition at its boundary, the fresh-wallet
// count + the state / seed round trip, the outcome records at +1 / +4 / +9 and the paper net, one trigger per token per 30 slots, the
// warm-up. Both: LOG ONLY = nothing sent and no other record changed; off = dip41.
// ===================================================================================================================
use super::*;
use super::psfam2::*;
use super::psq1::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;
/// the feed's clock in the pure tests: T0 + slot * 400 ms
const T0: u64 = 1_793_000_000_000_000_000;
const SLOT_NS: u64 = 400_000_000;
const H: u64 = 3_600_000_000_000;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000) }
fn pctr(x: f64) -> u64 { (x / 100.0 * pl::SUPPLY).round() as u64 }
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x42; x }
fn fam(i: usize) -> Pk { default_wallets()[i] }
fn tmp(name: &str) -> String { std::env::temp_dir().join(format!("dip42-{}-{name}", std::process::id())).to_string_lossy().to_string() }
fn sold(c: Option<u64>, sigs: &[&str], qty: u64) -> SellOut {
    SellOut { sold_at: c, sigs: sigs.iter().map(|s| (s.to_string(), true, 1_200_000)).collect(), last: None, attempts: sigs.len() as u32, last_qty: (qty, true), first_send_us: None }
}
fn strip(v: &[serde_json::Value]) -> Vec<String> { v.iter().map(|r| r.to_string()).collect() }
fn bots_file(name: &str, bots: &[Pk]) -> String {
    let p = tmp(name);
    std::fs::write(&p, serde_json::json!(bots.iter().map(b58).collect::<Vec<_>>()).to_string()).unwrap();
    p
}

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
    /// a sell returning `sol` lamports (within a lamport)
    fn sell_sol(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = ((self.t as u128 * sol as u128).div_ceil((self.v - sol) as u128)) as u64;
        self.sell_tok(user, q)
    }
    fn create(&self) -> CreateEvent { CreateEvent { mint: self.mint, bonding_curve: self.launch.bonding_curve, user: CREATOR, creator: CREATOR } }
}

struct Ctx { p: PsLive, atx: crossbeam_channel::Sender<Att>, orx: crossbeam_channel::Receiver<Out>, launches: Vec<Launch>, recs: Vec<serde_json::Value>, lines: Vec<String>, cmds: Vec<Cmd> }
impl Ctx {
    fn new(extra: &[&str]) -> Ctx {
        let (p, atx, orx) = PsLive::for_test(cfg(extra).unwrap().unwrap(), USER);
        let mut c = Ctx { p, atx, orx, launches: Vec::new(), recs: Vec::new(), lines: Vec::new(), cmds: Vec::new() };
        // the start's records as a run writes them
        c.p.f2_start();
        c.pump();
        c
    }
    fn pump(&mut self) {
        for o in self.orx.try_iter() { match o { Out::Rec(v) => self.recs.push(v), Out::Line(l) => self.lines.push(l) } }
        self.cmds.extend(self.p.take_cmds());
    }
    fn tx_sig(&mut self, slot: u64, idx: u64, sig: [u8; 64], trades: Vec<TradeEvent>, creates: Vec<CreateEvent>, mayhem: bool) {
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem };
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: T0 + slot * SLOT_NS + idx, t_decoded: T0 + slot * SLOT_NS + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![[0x77; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let ls = self.launches.clone();
        self.p.on_arrival(&a, slot);
        self.p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
        self.pump();
    }
    fn tx(&mut self, slot: u64, idx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0x42; sig[17] = trades.first().map_or(0, |t| t.mint[0]);
        self.tx_sig(slot, idx, sig, trades, creates, false);
    }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    /// token `k` created at 1000 (a dev buy); the caller trades it
    fn token(&mut self, k: u8) -> Tk {
        let mut tk = Tk::new(k);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, vec![dev], vec![tk.create()]);
        tk
    }
    /// an attempt of window `id` at `slot` (the sender's registration)
    fn att(&mut self, id: u64, mint: Pk, slot: u64) -> [u8; 64] {
        let mut sg = [0u8; 64]; sg[0] = 0xD4; sg[1] = 0x42; sg[3] = slot as u8;
        self.atx.send(Att { w: id, n: 1, mint, sig: sg, tag: pl::PS_TAG | 0x42, path: "helius-ps".into(), client: "JitoLabs".into(), slot, deadline: slot + 1,
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (slot, 0, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
            tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46: Default::default(), rf: None }).unwrap();
        self.p.drain_atts();
        self.pump();
        sg
    }
    /// fill with `sg` at slot `b` (index 40), a filler token moves the clock to the exit, the sell lands -> the Cmd::Realized
    fn fill_close(&mut self, tk: &mut Tk, sg: [u8; 64], b: u64) -> Cmd {
        let e = tk.buy(USER, 296_000_000);
        self.tx_sig(b, 40, sg, vec![e.clone()], vec![], false);
        let mut z = Tk::new(0x7F);
        self.launches.push(z.launch.clone());
        let dz = z.buy(CREATOR, S / 2);
        self.tx(b, 900, vec![dz], vec![z.create()]);
        for s in b + 1..=b + 2 { let e = z.buy([0x2F; 32], 1_000_000); self.tx(s, 900, vec![e], vec![]); }
        let Some(Cmd::Sell { pid, .. }) = self.cmds.iter().rev().find(|x| matches!(x, Cmd::Sell { .. })).cloned() else { panic!("no sell: {:?}", self.cmds) };
        let es = tk.sell_tok(USER, e.tok);
        self.tx_sig(b + 2, 9, { let mut s = [0u8; 64]; s[0] = 0x5E; s[1] = 0x42; s }, vec![es], vec![], false);
        self.p.on_msg(PsMsg::Sold(tk.mint, pid, 1, sold(Some(b + 2), &["S42"], e.tok)), &|_| false);
        self.pump();
        self.cmds.iter().rev().find(|x| matches!(x, Cmd::Realized { .. })).cloned().expect("realized")
    }
    /// THE scenario of the record tests: token 0x71 (create 1000), family 0 buys at 1001, the whale's 8% at 1010 (T2 arm), family 1 buys
    /// right after it (1010), a second whale's 8% at 1011 (a T2 skip: the token is armed), the whale dumps at 1012 (index 2), family 2 buys in
    /// the dump's slot (index 3), our fill at 1012 (index 40), the exit -> the realized
    fn scenario(&mut self) -> (Tk, u64, Cmd) {
        let whale = w(0xEE);
        let mut tk = self.token(0x71);
        let e = tk.buy(fam(0), S / 10); self.tx(1001, 2, vec![e], vec![]);
        let wb = tk.buy_tok(whale, pctr(8.0)); self.tx(1010, 50, vec![wb.clone()], vec![]);
        let e = tk.buy(fam(1), S / 10); self.tx(1010, 60, vec![e], vec![]);
        let e = tk.buy_tok(w(0xDD), pctr(8.0)); self.tx(1011, 5, vec![e], vec![]);
        let id = self.ev("presend_live_arm")[0]["w"].as_u64().unwrap();
        let sg = self.att(id, tk.mint, 1011);
        let d = tk.sell_tok(whale, wb.tok); self.tx(1012, 2, vec![d], vec![]);
        let e = tk.buy(fam(2), S / 10); self.tx(1012, 3, vec![e], vec![]);
        let rz = self.fill_close(&mut tk, sg, 1012);
        (tk, id, rz)
    }
}

// ---- FAM2: the book (pure) ---------------------------------------------------------------------------------------------------------

const M: Pk = [0x91u8; 32];
const M2: Pk = [0x92u8; 32];

/// the window's edges: a trade exactly N slots back counts, N + 1 does not; the strict cut ([ref - N, ref)) leaves the ref slot out
#[test]
fn dip42_f2_window_edges() {
    let mut b = F2Book::default();
    b.add(M, 0, 700);
    assert_eq!(b.view(&M, 1000, 300, false), F2V { n: 1, newest: Some(700), who: vec![0] }, "slot - 300: in");
    assert_eq!(b.view(&M, 1001, 300, false), F2V::default(), "slot - 301: out");
    assert_eq!(b.view(&M, 1000, 299, false).n, 0, "a 299-slot window");
    // strict: [ref - N, ref)
    assert_eq!(b.view(&M, 1000, 300, true).n, 1, "ref - 300: in");
    assert_eq!(b.view(&M, 1001, 300, true).n, 0);
    b.add(M, 1, 1000);
    assert_eq!(b.view(&M, 1000, 300, false), F2V { n: 2, newest: Some(1000), who: vec![0, 1] }, "the record's own slot counts (seen before it)");
    assert_eq!(b.view(&M, 1000, 300, true), F2V { n: 1, newest: Some(700), who: vec![0] }, "strictly before the ref slot");
    assert_eq!(b.view(&M, 1001, 300, true), F2V { n: 1, newest: Some(1000), who: vec![1] }, "ref - 1: in; 700 is now 301 back");
    // the JSON: "last" = slots since the newest counted trade
    let mut f = Fam2::new(F2Cfg { wallets: default_wallets(), slots: 300 });
    f.trade(&M, &fam(2), 990);
    assert_eq!(f.json(&M, 1000).0, serde_json::json!({"n": 1, "last": 10, "who": ["5UipEgoi"]}));
    assert_eq!(f.json(&M, 1291).0, serde_json::json!({"n": 0, "last": null, "who": []}));
    assert_eq!(f.json(&M2, 1000), (serde_json::json!({"n": 0, "last": null, "who": []}), false), "another mint");
    // the prune keeps what can still count
    f.book.prune(1290, 300);
    assert_eq!(f.book.mints(), 1);
    f.book.prune(1296, 300);
    assert_eq!(f.book.mints(), 0);
}

/// DISTINCT wallets: one wallet's many trades count once; a wallet that is not family never; per mint; the newest 8 distinct slots are
/// kept in order (an out-of-order older slot lands in its place)
#[test]
fn dip42_f2_distinct_counting() {
    let mut f = Fam2::new(F2Cfg { wallets: default_wallets(), slots: 300 });
    for s in [900u64, 901, 901, 905, 950] { f.trade(&M, &fam(0), s); }
    f.trade(&M, &w(0x33), 951);
    assert_eq!(f.json(&M, 1000).0, serde_json::json!({"n": 1, "last": 50, "who": ["2NUMEzNh"]}));
    assert_eq!(f.trades, 5, "only the family's trades are kept");
    f.trade(&M, &fam(3), 960);
    f.trade(&M, &fam(1), 999);
    f.trade(&M2, &fam(2), 999);
    assert_eq!(f.json(&M, 1000).0, serde_json::json!({"n": 3, "last": 1, "who": ["2NUMEzNh", "7anesLRr", "4MUFHfy6"]}), "who in the list's order");
    assert_eq!(f.json(&M2, 1000).0["n"], 1);
    // the newest 8 distinct slots of a wallet: a count a few slots back stays exact after a burst
    let mut b = F2Book::default();
    for s in 100..=120u64 { b.add(M, 0, s); }
    b.add(M, 0, 115);                                   // a repeat
    b.add(M, 0, 50);                                    // older than everything kept: dropped
    assert_eq!(b.view(&M, 113, 0, false).n, 1, "113 is among the newest 8 (113..=120)");
    assert_eq!(b.view(&M, 112, 5, true).n, 0, "107..111 fell out of the 8 kept (the cut is only read a few slots back)");
    let mut b = F2Book::default();
    for s in [10u64, 30, 20] { b.add(M, 0, s); }
    assert!(b.view(&M, 20, 0, false).n == 1 && b.view(&M, 31, 0, true).n == 0 && b.view(&M, 31, 1, true).n == 1);
    // custom wallets / slots
    let (a, bb) = (w(1), w(2));
    let mut f = Fam2::new(F2Cfg { wallets: vec![a, bb], slots: 5 });
    f.trade(&M, &fam(0), 100); f.trade(&M, &bb, 100);
    assert_eq!(f.json(&M, 105).0, serde_json::json!({"n": 1, "last": 5, "who": [b58(&bb)[..8]]}));
    assert_eq!(f.json(&M, 106).0["n"], 0);
}

/// the fill's dump on the tape: the newest sell >= 0.3 SOL by another wallet in the 3 slots up to the fill
#[test]
fn dip42_f2_dump_slot() {
    let t = |s: u64, buy: bool, sol: u64, user: Pk| pl::Trade { mint: M, s, i: 1, j: 0, sig: [0; 64], user, buy, sol, tok: 1, vsol: 40 * S, vtok: 800_000_000_000_000, fbps: 95, cbps: 30, t_rx: 0 };
    let a = w(1);
    let tape = vec![t(990, false, S, a), t(997, false, 300_000_000, a), t(998, false, 299_999_999, a), t(999, true, S, a), t(1000, false, S, USER)];
    assert_eq!(dump_slot(tape.iter(), &USER, 1000), Some(997), "0.3 SOL exactly, 3 slots back; a smaller sell, a buy and our own sell are not it");
    assert_eq!(dump_slot(tape.iter(), &USER, 1001), None, "4 slots back: none");
    assert_eq!(dump_slot(tape[..1].iter(), &USER, 1000), None);
    let tape = vec![t(999, false, S, a), t(1000, false, 2 * S, a)];
    assert_eq!(dump_slot(tape.iter(), &USER, 1000), Some(1000), "the newest one");
}

// ---- FAM2: the flags -----------------------------------------------------------------------------------------------------------------

#[test]
fn dip42_f2_flags() {
    let c = cfg(&[]).unwrap().unwrap();
    assert!(c.f2.is_none() && c.q1.is_none() && c.json().get("fam2").is_none() && c.json().get("q1").is_none(), "off by default: dip41's run_start");
    let c = cfg(&["--presend-live-fam2", "on"]).unwrap().unwrap();
    let f = c.f2.clone().unwrap();
    assert!(f.slots == 300 && f.wallets == default_wallets() && f.wallets.len() == 4);
    assert_eq!(c.json()["fam2"], serde_json::json!({"wallets": F2_DEFAULT, "slots": 300}));
    let (a, b) = (b58(&w(1)), b58(&w(2)));
    let c = cfg(&["--presend-live-fam2", "on", "--presend-live-fam2-wallets", &format!("{a},{b},{a}"), "--presend-live-fam2-slots", "120"]).unwrap().unwrap();
    assert_eq!(c.f2, Some(F2Cfg { wallets: vec![w(1), w(2)], slots: 120 }));
    assert!(cfg(&["--presend-live-fam2", "off"]).unwrap().unwrap().f2.is_none());
    for (x, want) in [(&["--presend-live-fam2-slots", "100"][..], "needs --presend-live-fam2 on"),
                      (&["--presend-live-fam2-wallets", &a][..], "needs --presend-live-fam2 on"),
                      (&["--presend-live-fam2", "yes"][..], "on | off"),
                      (&["--presend-live-fam2"][..], "needs a value"),
                      (&["--presend-live-fam2", "on", "--presend-live-fam2-slots", "0"][..], "1..2000"),
                      (&["--presend-live-fam2", "on", "--presend-live-fam2-slots", "2001"][..], "1..2000"),
                      (&["--presend-live-fam2", "on", "--presend-live-fam2-slots", "x"][..], "whole number"),
                      (&["--presend-live-fam2", "on", "--presend-live-fam2-wallets", "notawallet"][..], "not a base58 wallet")] {
        let e = format!("{:#}", cfg(x).unwrap_err());
        assert!(e.contains(want), "{x:?}: {e}");
    }
    assert!(crate::check_flags(&args(&["--presend-live-fam2", "on", "--presend-live-fam2-wallets", &a, "--presend-live-fam2-slots", "300"])).is_ok());
    assert!(crate::check_flags(&args(&["--presend-live-fam2", "on", "--presend-live-fam2-slots", "3.5"])).is_err(), "the start-up check knows it is a whole number");
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-live-fam2", "on"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, S).unwrap_err().to_string().contains("needs --presend-live"));
    let a: Vec<String> = ["snipe_engine", "--dip", "--q1-log", "on"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, S).unwrap_err().to_string().contains("needs --presend-live"));
}

// ---- FAM2: the records -------------------------------------------------------------------------------------------------------------

/// T2 arm / skip / fill / realized carry "fam2"; NO LOOK-AHEAD: the arm does not see the family trade that arrives right after it, the
/// fill sees only what the feed delivered before it; the fill's "pre" = strictly before the dump's slot (the research's cut)
#[test]
fn dip42_f2_records_no_look_ahead() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let mut c = Ctx::new(&["--presend-live-fam2", "on"]);
    let cfgr = c.ev("presend_live_fam2_config");
    assert!(cfgr.len() == 1 && cfgr[0]["slots"] == 300 && cfgr[0]["mode"] == "log" && cfgr[0]["wallets"].as_array().unwrap().len() == 4, "{cfgr:?}");
    let (_, id, rz) = c.scenario();
    let a = c.ev("presend_live_arm");
    assert_eq!(a.len(), 1, "{:?}", c.recs);
    assert_eq!(a[0]["fam2"], serde_json::json!({"n": 1, "last": 9, "who": ["2NUMEzNh"]}), "the arm at 1010: family 0's buy at 1001; family 1's buy came AFTER the arm");
    let s = c.ev("presend_live_skip");
    assert!(!s.is_empty(), "the second whale on an armed token is skipped");
    assert_eq!(s[0]["fam2"], serde_json::json!({"n": 2, "last": 1, "who": ["2NUMEzNh", "7anesLRr"]}), "the skip at 1011 sees family 1's 1010 buy");
    let f = c.ev("presend_live_fill");
    assert_eq!(f.len(), 1);
    assert_eq!(f[0]["fam2"], serde_json::json!({"n": 3, "last": 0, "who": ["2NUMEzNh", "7anesLRr", "5UipEgoi"], "pre": 2, "pre_who": ["2NUMEzNh", "7anesLRr"], "ref": 1012, "dump": true}),
        "at the fill: all three seen before it; before the dump's slot (1012): the two earlier ones");
    let Cmd::Realized { f2: Some(z), w: rw, .. } = rz else { panic!("no fam2 on the realized") };
    assert!(rw == id && z["at"] == "fill" && z["pre"] == 2 && z["n"] == 3 && z["ref"] == 1012, "{z}");
    // no "fam2" on any other record
    assert!(c.recs.iter().all(|r| r.get("fam2").is_none() || ["presend_live_arm", "presend_live_skip", "presend_live_fill"].contains(&r["ev"].as_str().unwrap())));
    let st = c.p.status();
    assert!(st.contains(" | FAM2 LOG (4 wallets, 300 slots): family present on arms 1/1, skips 1/1, fills 1/1 (family trades seen 3)"), "{st}");
    let end = c.p.finish(1100, None);
    assert_eq!(end["fam2"], serde_json::json!({"mode": "log", "wallets": 4, "slots": 300, "arms": {"n": 1, "present": 1}, "skips": {"n": 1, "present": 1},
        "fills": {"n": 1, "present": 1}, "trades": 3, "mints": 1}));
}

/// family absent: n 0 everywhere, "pre" 0; without a dump on the tape the fill's ref is its own slot; a family trade only in the fill's
/// slot is seen ("n") but is not "present" ("pre": strictly before)
#[test]
fn dip42_f2_absent_and_no_dump() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let mut c = Ctx::new(&["--presend-live-fam2", "on", "--presend-live-fam2-slots", "8"]);
    let whale = w(0xEE);
    let mut tk = c.token(0x71);
    let e = tk.buy(fam(0), S / 10); c.tx(1001, 2, vec![e], vec![]);           // 9 slots before the arm: outside an 8-slot window
    let e = tk.buy_tok(whale, pctr(8.0)); c.tx(1010, 50, vec![e], vec![]);
    let a = c.ev("presend_live_arm");
    assert_eq!(a[0]["fam2"], serde_json::json!({"n": 0, "last": null, "who": []}));
    let id = a[0]["w"].as_u64().unwrap();
    let sg = c.att(id, tk.mint, 1011);
    let e = tk.buy(fam(1), S / 10); c.tx(1012, 3, vec![e], vec![]);
    let rz = c.fill_close(&mut tk, sg, 1012);
    let f = c.ev("presend_live_fill");
    assert_eq!(f[0]["fam2"], serde_json::json!({"n": 1, "last": 0, "who": ["7anesLRr"], "pre": 0, "pre_who": [], "ref": 1012, "dump": false}));
    let Cmd::Realized { f2: Some(z), .. } = rz else { panic!() };
    assert!(z["pre"] == 0 && z["at"] == "fill");
    assert!(c.p.status().contains("family present on arms 0/1, skips 0/0, fills 0/1"), "{}", c.p.status());
}

/// the re-arm's arm and skip records carry it too
#[test]
fn dip42_f2_rearm_records() {
    let (a, b) = (w(0xA1), w(0xB1));
    let run = |seed: bool| {
        let mut c = Ctx::new(&["--presend-live-rearm", "on", "--presend-live-wh-loss", "2:0.05", "--presend-live-fam2", "on"]);
        if seed { c.p.sh.wh.lock().unwrap().all.insert(a, pswh::WhHist { n: 3, sum: -200_000_000, ..Default::default() }); }
        // create-slot buys of a 7% / b 8%, the family at 1002, a dumps at 1005, the check at 1008 (a filler token moves the clock)
        let mut tk = Tk::new(0x62);
        let mut z = Tk::new(0x63);
        c.launches.push(tk.launch.clone());
        c.launches.push(z.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        c.tx(1000, 1, vec![dev], vec![tk.create()]);
        let e = tk.buy_tok(a, pctr(7.0)); c.tx(1000, 2, vec![e], vec![]);
        let e = tk.buy_tok(b, pctr(8.0)); c.tx(1000, 3, vec![e], vec![]);
        let dz = z.buy(CREATOR, S / 2);
        c.tx(1000, 4, vec![dz], vec![z.create()]);
        for s in 1001..=1004 { let e = tk.buy(if s == 1002 { fam(3) } else { w(0x33) }, S / 10); c.tx(s, 5, vec![e], vec![]); }
        let d = tk.sell_tok(a, pctr(7.0));
        c.tx(1005, 5, vec![d], vec![]);
        for s in 1006..=1008 { let e = z.buy(w(0x2F), 1_000_000); c.tx(s, 900, vec![e], vec![]); }
        c
    };
    let c = run(false);
    let ar = c.ev("presend_live_arm").into_iter().find(|r| r["kind"] == "rearm").unwrap_or_else(|| panic!("no re-arm: {:?}", c.recs));
    assert!(ar["fam2"]["n"] == 1 && ar["fam2"]["who"] == serde_json::json!(["4MUFHfy6"]) && ar["fam2"]["last"].as_u64().is_some_and(|l| (3..=6).contains(&l)), "{}", ar["fam2"]);
    let c = run(true);
    let sk = c.ev("presend_live_skip").into_iter().find(|r| r["kind"] == "rearm").unwrap_or_else(|| panic!("no re-arm skip: {:?}", c.recs));
    assert!(sk["fam2"]["n"] == 1 && sk["fam2"]["who"] == serde_json::json!(["4MUFHfy6"]), "{sk}");
}

// ---- Q1: the rule (pure) -------------------------------------------------------------------------------------------------------------

const BOT: Pk = [0xB0u8; 32];

fn q1cfg(bots: &str) -> Q1Cfg {
    Q1Cfg { min_sol: S / 2, age: (3, 80), bot_slots: 100, dip_slots: 200, fresh_max: 2, gap: 30, size: S / 2, fresh_ns: 48 * H, bots: bots.to_string(), state: None, fam: default_wallets() }
}
struct Q { q: Q1, out: Vec<serde_json::Value>, n: u32 }
impl Q {
    fn with(c: Q1Cfg) -> Q { Q { q: Q1::open(c, USER), out: Vec::new(), n: 0 } }
    fn new(name: &str) -> Q { Q::with(q1cfg(&bots_file(name, &[BOT]))) }
    fn at(&mut self, e: &TradeEvent, slot: u64, t: u64) {
        self.n += 1;
        let mut sig = [0u8; 64]; sig[..4].copy_from_slice(&self.n.to_be_bytes());
        self.q.trade(&Q1Trade { mint: e.mint, user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok, slot, idx: self.n, j: 0, sig, t }, &mut self.out);
    }
    fn tr(&mut self, e: &TradeEvent, slot: u64) { self.at(e, slot, T0 + slot * SLOT_NS); }
    /// token `k` created at `cs` (a dev buy in its create slot)
    fn token(&mut self, k: u8, cs: u64) -> Tk {
        let mut tk = Tk::new(k);
        self.q.create(tk.mint, cs, false);
        let e = tk.buy(CREATOR, S / 2); self.tr(&e, cs);
        tk
    }
    fn trig(&self) -> Vec<serde_json::Value> { self.out.iter().filter(|r| r["ev"] == "q1_trigger").cloned().collect() }
    fn outc(&self) -> Vec<serde_json::Value> { self.out.iter().filter(|r| r["ev"] == "q1_outcome").cloned().collect() }
    fn l(&self, a: &AtomicU64) -> u64 { a.load(Ordering::Relaxed) }
    /// one fresh buyer's buy of `sol` on a new token `k` at age `age` -> triggered
    fn one(&mut self, k: u8, age: u64, sol: u64) -> bool {
        let n = self.trig().len();
        let mut tk = self.token(k, 1000);
        let e = tk.buy(w(k), sol); self.tr(&e, 1000 + age);
        self.trig().len() == n + 1
    }
}

/// every condition at its boundary: the buy's SOL, the age band, a BUY (not a sell), the curve reserve, family / our wallet, mayhem / a
/// token not seen from its create, no bot list
#[test]
fn dip42_q1_size_age_token_boundaries() {
    let mut q = Q::new("b1.json");
    assert!(q.one(0x10, 10, S / 2), "0.5 SOL exactly, a fresh wallet, a quiet token: a trigger");
    let r = &q.trig()[0];
    assert!(r["sol"] == S / 2 && r["age"] == 10 && r["bots"] == 0 && r["dipb"] == 0 && r["prior"] == 0 && r["buyer"] == b58(&w(0x10)) && r["slot"] == 1010 && r["size"] == S / 2
        && r["id"] == 1 && r["warm"] == true && r["vsol"] == 31 * S && (r["pct"].as_f64().unwrap() - r["tok"].as_u64().unwrap() as f64 / 1e13).abs() < 1e-9
        && (r["pct"].as_f64().unwrap() - 1.70).abs() < 0.01, "{r}");
    assert!((r["p"].as_f64().unwrap() / r["p_pre"].as_f64().unwrap() - (31.0f64 / 30.5).powi(2)).abs() < 1e-6, "the post-trigger price: {r}");
    assert!(!q.one(0x11, 10, S / 2 - 1), "one lamport short of 0.5 SOL");
    assert!(!q.one(0x12, 2, S), "age 2 < 3");
    assert!(q.one(0x13, 3, S), "age 3");
    assert!(q.one(0x14, 80, S), "age 80");
    assert!(!q.one(0x15, 81, S), "age 81 > 80");
    assert_eq!(q.l(&q.q.st.cands), 3, "candidates = big buys in the band");
    // a sell is never a trigger
    let mut tk = q.token(0x16, 1000);
    let b = tk.buy(w(0x16), S / 4); q.tr(&b, 1005);
    let e = tk.sell_tok(w(0x16), b.tok); q.tr(&e, 1006);
    // the curve reserve after it: 1073e12 exactly is in, one more is out (build.py's row filter)
    let mut tk = q.token(0x17, 1000);
    let mut e = tk.buy(w(0x17), S); e.vtok = Q1_VTOK_MAX + 1; q.tr(&e, 1010);
    let mut e = tk.buy(w(0x18), S); e.vtok = 0; q.tr(&e, 1011);
    assert_eq!(q.trig().len(), 3);
    let mut e = tk.buy(w(0x19), S); e.vtok = Q1_VTOK_MAX; q.tr(&e, 1012);
    assert_eq!(q.trig().len(), 4);
    // a family wallet / our wallet buying is never a trigger
    let mut tk = q.token(0x1A, 1000);
    let e = tk.buy(fam(1), S); q.tr(&e, 1010);
    let mut tk = q.token(0x1B, 1000);
    let e = tk.buy(USER, S); q.tr(&e, 1010);
    // a mayhem launch, a token never seen created
    let mut tk = Tk::new(0x1C);
    q.q.create(tk.mint, 1000, true);
    let e = tk.buy(w(0x1C), S); q.tr(&e, 1010);
    let mut tk = Tk::new(0x1D);
    let e = tk.buy(w(0x1D), S); q.tr(&e, 1010);
    assert_eq!(q.trig().len(), 4, "{:?}", q.trig());
    // no bot list: nothing is written (counted)
    let mut q = Q::with(q1cfg("/nonexistent/dip42/bots.json"));
    assert!(q.q.bots.is_none() && q.q.bots_err.is_some());
    assert!(!q.one(0x10, 10, S));
    assert!(q.l(&q.q.st.no_list) == 1 && q.l(&q.q.st.cands) == 1);
}

/// QUIET: no listed bot in (s - 100, s], no dip buyer in [s - 200, s]; both count the trigger's own trade
#[test]
fn dip42_q1_quiet_boundaries() {
    // (the default windows are longer than the age band: the edges with short windows)
    let short = || { let mut c = q1cfg(&bots_file("b2.json", &[BOT])); c.bot_slots = 10; c.dip_slots = 10; c };
    // a listed bot traded 9 slots before: not quiet; 10 slots before: quiet (the window is s - 10 < slot <= s)
    for (back, want) in [(9u64, false), (10, true), (0, false)] {
        let mut q = Q::with(short());
        let mut tk = q.token(0x20, 1000);
        let e = tk.buy(BOT, S / 10); q.tr(&e, 1030 - back);
        let e = tk.buy(w(0x21), S); q.tr(&e, 1030);
        assert_eq!(q.trig().len() == 1, want, "bot {back} slots before");
        assert_eq!(q.l(&q.q.st.not_quiet), (!want) as u64);
    }
    // a bot's SELL counts as its trade; with the default 100 slots a bot anywhere in the token's life blocks
    let mut q = Q::new("b3.json");
    let mut tk = q.token(0x20, 1000);
    let b = tk.buy(BOT, S / 10); q.tr(&b, 1001);
    let e = tk.buy(w(0x21), S); q.tr(&e, 1080);
    assert!(q.trig().is_empty(), "79 slots before: inside 100");
    // the trigger's own wallet is a listed bot: not quiet
    let mut q = Q::new("b4.json");
    let mut tk = q.token(0x20, 1000);
    let e = tk.buy(BOT, S); q.tr(&e, 1010);
    assert!(q.trig().is_empty() && q.l(&q.q.st.not_quiet) == 1);
    // the bot trades AFTER the trigger (same slot): the trigger stands (no look-ahead)
    let mut q = Q::new("b5.json");
    let mut tk = q.token(0x20, 1000);
    let e = tk.buy(w(0x21), S); q.tr(&e, 1010);
    let e = tk.buy(BOT, S / 10); q.tr(&e, 1010);
    assert_eq!(q.trig().len(), 1);
    // dip buyers: a buy <= 2 slots after a sell >= 0.3 SOL (the sell seen first)
    //  (sell lamports, the dip buy's slots after the sell, the trigger's slots after the dip buy, trigger?)
    for (sell, after, gap, want, name) in [(300_000_000u64, 2u64, 5u64, false, "0.3 SOL sell, a buy 2 slots after: a dip buyer"),
                                             (300_000_000, 3, 5, true, "a buy 3 slots after the sell: not a dip buy"),
                                             (299_000_000, 0, 5, true, "a 0.299 SOL sell: not a big sell"),
                                             (300_000_000, 0, 10, false, "the dip buy 10 slots before the trigger: inside [s - 10, s]"),
                                             (300_000_000, 0, 11, true, "11 slots before: outside")] {
        let mut q = Q::with(short());
        let mut tk = q.token(0x20, 1000);
        let b = tk.buy(w(0x22), 2 * S); q.tr(&b, 1001);          // (age 1: below the band, not a trigger of its own)
        let e = tk.sell_sol(w(0x22), sell); q.tr(&e, 1010);
        assert!(e.sol >= sell && e.sol <= sell + 1, "{} vs {sell}", e.sol);
        let e = tk.buy(w(0x23), S / 100); q.tr(&e, 1010 + after);
        let e = tk.buy(w(0x24), S); q.tr(&e, 1010 + after + gap);
        assert_eq!(q.trig().iter().any(|r| r["buyer"] == b58(&w(0x24))), want, "{name}");
        assert_eq!(q.trig().len(), want as usize);
    }
    // the trigger's own buy within 2 slots after a big sell IS a dip buy: not quiet. Our own wallet's dip buy counts as a dip buyer too
    let mut q = Q::new("b6.json");
    let mut tk = q.token(0x20, 1000);
    let b = tk.buy_tok(CREATOR, pctr(2.0)); q.tr(&b, 1001);
    let e = tk.sell_sol(CREATOR, S / 2); q.tr(&e, 1010);
    let e = tk.buy(w(0x25), S); q.tr(&e, 1012);
    assert!(q.trig().is_empty(), "{:?}", q.trig());
    let mut q = Q::new("b7.json");
    let mut tk = q.token(0x20, 1000);
    let b = tk.buy_tok(CREATOR, pctr(2.0)); q.tr(&b, 1001);
    let e = tk.sell_sol(CREATOR, S / 2); q.tr(&e, 1010);
    let e = tk.buy(USER, S / 3); q.tr(&e, 1011);
    let e = tk.buy(w(0x25), S); q.tr(&e, 1020);
    assert!(q.trig().is_empty(), "our dip buy at 1011 makes the token not quiet");
    // the bot list: dip39's formats; a registry entry that is not a wallet is skipped (the study's read), our wallet never counts
    let (s, skipped) = bots_parse(serde_json::json!({"wallets": [{"wallet": b58(&BOT)}, {"wallet": "18161057311088359920"}, {"w": b58(&w(7))}, b58(&USER), 5]}).to_string().as_bytes(), &USER).unwrap();
    assert!(s.len() == 2 && s.contains(&BOT) && s.contains(&w(7)) && skipped == 2);
    assert!(bots_parse(b"[]", &USER).is_err() && bots_parse(b"{}", &USER).is_err() && bots_parse(b"x", &USER).is_err());
}

/// FRESH: the buyer's distinct tokens first traded in an EARLIER slot <= 2; counted only on launched non-mayhem tokens at age <= 400
#[test]
fn dip42_q1_fresh_counting() {
    // the book alone
    let mut f = Fresh::default();
    let a = w(1);
    let m = |k: u8| -> Pk { [k; 32] };
    assert_eq!(f.note(a, &m(1), 100, 10), 0);
    assert_eq!(f.note(a, &m(1), 100, 10), 0, "the same token, the same slot");
    assert_eq!(f.note(a, &m(2), 100, 10), 0, "two tokens first traded in THIS slot: still 0 before it");
    assert_eq!(f.prior(&a, 101), 2);
    assert_eq!(f.note(a, &m(1), 101, 11), 2, "a token traded in an earlier slot counts, once");
    assert_eq!(f.note(a, &m(3), 101, 11), 2);
    assert_eq!(f.note(a, &m(4), 102, 12), 3);
    for k in 5..=20u8 { f.note(a, &m(k), 103, 13); }
    assert_eq!(f.prior(&a, 200), Q1_K as u32, "capped at the first 8 tokens");
    assert_eq!(f.prior(&w(2), 200), 0, "an unknown wallet");
    assert!(f.w[&a].last == 13 && f.prune(13) == 0 && f.prune(14) == 1 && f.w.is_empty());
    assert_eq!(mint_id(&<[u8; 32]>::try_from(bs58::decode("2aiC75LS1dxTgTtFycSAr9oVCZKkbzjiiu9RcwxMPQnc").into_vec().unwrap()).unwrap()), 3_496_836_631, "q1_fresh_seed.py's mint_id");

    // the rule: a buyer with 2 earlier tokens triggers, with 3 it does not
    let mut q = Q::new("b8.json");
    let buyer = w(0x40);
    for k in 0..2u8 { let mut tk = q.token(0x30 + k, 900); let e = tk.buy(buyer, S / 100); q.tr(&e, 950); }
    let mut tk = q.token(0x38, 1000);
    let e = tk.buy(buyer, S); q.tr(&e, 1010);
    assert!(q.trig().len() == 1 && q.trig()[0]["prior"] == 2, "{:?}", q.trig());
    // ... the token it just bought now counts as its third (first traded at 1010 < 1050)
    let mut tk2 = q.token(0x39, 1040);
    let e = tk2.buy(buyer, S); q.tr(&e, 1050);
    assert!(q.trig().len() == 1 && q.l(&q.q.st.not_fresh) == 1);
    // a third token first traded in the SAME slot as the trigger does not count yet (strictly earlier slots)
    let mut q = Q::new("b9.json");
    for k in 0..2u8 { let mut tk = q.token(0x30 + k, 900); let e = tk.buy(buyer, S / 100); q.tr(&e, 950); }
    let mut ta = q.token(0x3A, 1000);
    let mut tb = q.token(0x3B, 1000);
    let e = ta.buy(buyer, S / 100); q.tr(&e, 1010);
    let e = tb.buy(buyer, S); q.tr(&e, 1010);
    assert!(q.trig().len() == 1 && q.trig()[0]["prior"] == 2);
    // only young launched tokens count: a trade at age 401, of a mayhem token, of a token not seen created: no history
    let mut q = Q::new("b10.json");
    let mut old = q.token(0x30, 500);
    let e = old.buy(w(0x45), S / 100); q.tr(&e, 900);          // age 400: counts
    let e = old.buy(buyer, S / 100); q.tr(&e, 901);            // age 401: does not
    let mut may = Tk::new(0x31); q.q.create(may.mint, 900, true);
    let e = may.buy(buyer, S / 100); q.tr(&e, 950);
    let mut unk = Tk::new(0x32);
    let e = unk.buy(buyer, S / 100); q.tr(&e, 950);
    assert!(q.q.fresh.prior(&buyer, 2000) == 0 && q.q.fresh.prior(&w(0x45), 2000) == 1);
    // --q1-fresh-max 0: only a wallet never seen
    let mut c = q1cfg(&bots_file("b11.json", &[BOT])); c.fresh_max = 0;
    let mut q = Q::with(c);
    let mut tk = q.token(0x30, 900); let e = tk.buy(buyer, S / 100); q.tr(&e, 950);
    let mut tk = q.token(0x38, 1000);
    let e = tk.buy(buyer, S); q.tr(&e, 1010);
    let e = tk.buy(w(0x41), S); q.tr(&e, 1011);
    assert!(q.trig().len() == 1 && q.trig()[0]["buyer"] == b58(&w(0x41)));
}

/// the wallet history's state: the round trip, the seed's format, used when <= 24 h old at the first trade, the idle drop, the warm-up
#[test]
fn dip42_q1_fresh_state_and_warm_up() {
    let buyer = w(0x40);
    let st = tmp("fresh.json");
    let _ = std::fs::remove_file(&st);
    let mut c = q1cfg(&bots_file("b12.json", &[BOT])); c.state = Some(st.clone());
    // run 1: no state file -> warm-up; the buyer trades 3 tokens; the state saved at the end
    let mut q = Q::with(c.clone());
    assert!(q.q.state_err.is_none() && q.q.state_n == 0);
    for k in 0..3u8 { let mut tk = q.token(0x30 + k, 900); let e = tk.buy(buyer, S / 100); q.tr(&e, 950 + k as u64); }
    assert!(q.q.warm() && q.q.state_used.is_none());
    let mut lines = Vec::new();
    let end = q.q.finish(&mut lines);
    assert!(lines[0].contains("saved to") && end["wallets"] == 2 && end["warm"] == true, "{lines:?} {end}");
    let j: serde_json::Value = serde_json::from_slice(&std::fs::read(&st).unwrap()).unwrap();
    assert!(j["v"] == 1 && j["kind"] == "q1_fresh" && j["k"] == 8 && j["age_max"] == 400 && j["t"] == T0 + 952 * SLOT_NS && j["slot"] == 952 && j["from"] == T0 + 900 * SLOT_NS, "{j}");
    let row = j["w"][b58(&buyer)].as_array().unwrap().clone();
    assert_eq!(row, vec![serde_json::json!((T0 + 952 * SLOT_NS) / 1_000_000_000), serde_json::json!(mint_id(&[0x30; 32])), serde_json::json!(950), serde_json::json!(mint_id(&[0x31; 32])),
        serde_json::json!(951), serde_json::json!(mint_id(&[0x32; 32])), serde_json::json!(952)], "[last unix s, mint id, first slot, ...]");
    // the round trip is exact
    let (t, from, m) = Fresh::state_parse(&std::fs::read(&st).unwrap(), 48 * H).unwrap();
    assert!(t == T0 + 952 * SLOT_NS && from == T0 + 900 * SLOT_NS && m == q.q.fresh.w);
    // run 2 an hour later: the state is used -> the buyer is NOT fresh; the history's start is the state's
    let later = |slot: u64, dt: u64| T0 + dt + slot * SLOT_NS;
    let mut q = Q::with(c.clone());
    assert_eq!(q.q.state_n, 2);
    let mut tk = Tk::new(0x50); q.q.create(tk.mint, 10_000, false);
    let e = tk.buy(CREATOR, S / 2); q.at(&e, 10_000, later(10_000, H));
    let e = tk.buy(buyer, S); q.at(&e, 10_010, later(10_010, H));
    assert!(q.q.state_used == Some(true) && q.trig().is_empty() && q.l(&q.q.st.not_fresh) == 1 && q.q.cover_from == Some(T0 + 900 * SLOT_NS));
    let e = tk.buy(w(0x41), S); q.at(&e, 10_011, later(10_011, H));
    assert!(q.trig().len() == 1 && q.trig()[0]["warm"] == true && (q.trig()[0]["cover_h"].as_f64().unwrap() - 2.01).abs() < 0.01, "{:?}", q.trig());
    // run 3: the state is 25 h old at the first trade -> NOT used: the buyer looks fresh, the record says warm
    let mut q = Q::with(c.clone());
    let mut tk = Tk::new(0x50); q.q.create(tk.mint, 10_000, false);
    let e = tk.buy(CREATOR, S / 2); q.at(&e, 10_000, later(10_000, 25 * H));
    let e = tk.buy(buyer, S); q.at(&e, 10_010, later(10_010, 25 * H));
    assert!(q.q.state_used == Some(false) && q.trig().len() == 1 && q.trig()[0]["warm"] == true && q.trig()[0]["prior"] == 0);
    // the warm-up ends once the history covers 24 h: with a 48 h seed ("from" 48 h back) the first record is already not warm
    let seed = serde_json::json!({"v": 1, "kind": "q1_fresh", "t": T0, "slot": 5_000, "from": T0 - 48 * H, "k": 8, "age_max": 400,
        "w": {b58(&buyer): [T0 / 1_000_000_000 - 100, 11, 4_000, 12, 4_100, 13, 4_200], b58(&w(0x42)): [(T0 - 49 * H) / 1_000_000_000, 11, 100]},
        "built": {"wallets": 2}});
    std::fs::write(&st, seed.to_string()).unwrap();
    let mut q = Q::with(c.clone());
    assert_eq!(q.q.state_n, 1, "a wallet idle > 48 h before the state's clock is dropped at the load");
    let mut tk = Tk::new(0x50); q.q.create(tk.mint, 10_000, false);
    let e = tk.buy(CREATOR, S / 2); q.at(&e, 10_000, later(10_000, 0));
    let e = tk.buy(buyer, S); q.at(&e, 10_010, later(10_010, 0));
    let e = tk.buy(w(0x41), S); q.at(&e, 10_050, later(10_050, 0));
    assert!(q.trig().len() == 1 && q.trig()[0]["buyer"] == b58(&w(0x41)) && q.trig()[0]["warm"] == false && q.trig()[0]["cover_h"].as_f64().unwrap() > 48.0, "{:?}", q.trig());
    // without any state: warm for the first 24 h of the feed, then not
    let mut c2 = c.clone(); c2.state = None;
    let mut q = Q::with(c2);
    let mut tk = q.token(0x50, 1000);
    let e = tk.buy(w(0x41), S); q.tr(&e, 1010);
    let mut tk = Tk::new(0x51); q.q.create(tk.mint, 300_000, false);
    let e = tk.buy(CREATOR, S / 2); q.at(&e, 300_000, T0 + 1000 * SLOT_NS + 24 * H - 1);
    let e = tk.buy(w(0x43), S); q.at(&e, 300_010, T0 + 1000 * SLOT_NS + 24 * H - 1);
    let e = tk.buy(w(0x44), S); q.at(&e, 300_050, T0 + 1000 * SLOT_NS + 24 * H);
    let t = q.trig();
    assert!(t.len() == 3 && t[0]["warm"] == true && t[1]["warm"] == true && t[2]["warm"] == false, "{t:?}");
    // a bad state file: an error kept, the warm-up
    std::fs::write(&st, "{\"v\": 2}").unwrap();
    let q = Q::with(c);
    assert!(q.q.state_err.as_deref().is_some_and(|e| e.contains("not a v1 q1_fresh state")) && q.q.state_n == 0);
    let _ = std::fs::remove_file(&st);
}

/// ONE trigger per token per 30 slots (the flag's default); the study's 10 with --q1-gap-slots 10; another token is independent
#[test]
fn dip42_q1_one_per_30_slots() {
    let mut q = Q::new("b13.json");
    let mut tk = q.token(0x20, 1000);
    let e = tk.buy(w(1), S); q.tr(&e, 1010);
    let e = tk.buy(w(2), S); q.tr(&e, 1010);
    let e = tk.buy(w(3), S); q.tr(&e, 1039);
    assert!(q.trig().len() == 1 && q.l(&q.q.st.dedup) == 2, "29 slots after: dropped");
    let mut other = q.token(0x21, 1020);
    let e = other.buy(w(4), S); q.tr(&e, 1039);
    assert_eq!(q.trig().len(), 2, "another token");
    let e = tk.buy(w(5), S); q.tr(&e, 1040);
    assert!(q.trig().len() == 3 && q.trig()[2]["slot"] == 1040 && q.trig()[2]["id"] == 3, "30 slots after: a new trigger");
    let e = tk.buy(w(6), S); q.tr(&e, 1069);
    assert_eq!(q.trig().len(), 3, "counted from the LAST trigger (1040)");
    let mut c = q1cfg(&bots_file("b14.json", &[BOT])); c.gap = 10;
    let mut q = Q::with(c);
    let mut tk = q.token(0x20, 1000);
    for (k, s) in [(1u8, 1010u64), (2, 1019), (3, 1020)] { let e = tk.buy(w(k), S); q.tr(&e, s); }
    assert_eq!(q.trig().iter().map(|r| r["slot"].as_u64().unwrap()).collect::<Vec<_>>(), vec![1010, 1020]);
}

/// the outcome records at +1 / +4 / +9: written only once the feed's slot has PASSED slot + h (the slot is complete), the curve at the end
/// of that slot, the flows since the trigger, family / us, the paper net (pump's curve with our own impact, 1.25% per side, 1.5 mSOL)
#[test]
fn dip42_q1_outcomes_and_paper() {
    let mut q = Q::new("b15.json");
    let mut tk = q.token(0x20, 1000);
    let mut z = q.token(0x21, 1000);                           // another token: only moves the feed's slot
    let e = tk.buy(w(1), S); q.tr(&e, 1010);
    let (v0, t0) = (e.vsol, e.vtok);
    assert!(q.trig().len() == 1 && q.q.open_n() == 1);
    let e1 = tk.buy(w(2), S / 5); q.tr(&e1, 1010);             // the trigger's slot, after it
    let e2 = tk.sell_tok(w(2), e1.tok / 2); q.tr(&e2, 1011);
    assert!(q.outc().is_empty(), "slot 1011 (= +1) is not complete yet");
    let e = z.buy(w(9), 1_000); q.tr(&e, 1011);
    assert!(q.outc().is_empty());
    let e = z.buy(w(9), 1_000); q.tr(&e, 1012);                 // the feed passes 1011
    let o = q.outc();
    assert_eq!(o.len(), 1);
    assert!(o[0]["h"] == 1 && o[0]["id"] == 1 && o[0]["slot"] == 1010 && o[0]["end_slot"] == 1011 && o[0]["vsol"] == e2.vsol && o[0]["vtok"] == e2.vtok && o[0]["buy_sol"] == e1.sol
        && o[0]["sell_sol"] == e2.sol && o[0]["net_sol"] == e1.sol as i64 - e2.sol as i64 && o[0]["n_buys"] == 1 && o[0]["n_sells"] == 1 && o[0]["fam"] == false && o[0]["us"] == false
        && o[0].get("paper").is_none(), "{}", o[0]);
    let p = |v: u64, t: u64| v as f64 / t as f64;
    assert!((o[0]["ret"].as_f64().unwrap() - (p(e2.vsol, e2.vtok) / p(v0, t0) - 1.0)).abs() < 1e-12);
    // a family buy at +3, our own buy at +4, a buy at +5 (after the +4 horizon)
    let e3 = tk.buy(fam(0), S / 2); q.tr(&e3, 1013);
    let e4 = tk.buy(USER, S / 4); q.tr(&e4, 1014);
    let e5 = tk.buy(w(3), S); q.tr(&e5, 1015);                  // the feed passes 1014: +4 written BEFORE this trade is applied
    let o = q.outc();
    assert_eq!(o.len(), 2);
    assert!(o[1]["h"] == 4 && o[1]["end_slot"] == 1014 && o[1]["vsol"] == e4.vsol && o[1]["vtok"] == e4.vtok && o[1]["buy_sol"] == e1.sol + e3.sol + e4.sol && o[1]["sell_sol"] == e2.sol
        && o[1]["n_buys"] == 3 && o[1]["fam"] == true && o[1]["us"] == true, "{}", o[1]);
    // the paper trade by hand: 0.5 SOL into the curve at the trigger's reserves; out on the curve at +4 with our 0.5 SOL still in it
    let size = S / 2;
    let tok = (size as u128 * t0 as u128 / (v0 + size) as u128) as u64;
    let vs = e4.vsol as u128 + size as u128;
    let vt = (e4.vsol as u128 * e4.vtok as u128).div_ceil(vs);
    let out = (tok as u128 * vs / (vt + tok as u128)) as u64;
    let fee = |x: u64| (x as u128 * 125).div_ceil(10_000) as u64;
    let net = out as i64 - fee(out) as i64 - size as i64 - fee(size) as i64 - 1_500_000;
    assert_eq!(o[1]["paper"], serde_json::json!({"label": "paper", "size": size, "tok": tok, "out": out, "net": net}));
    assert!(net > 0 && out > size, "0.75 SOL of later buys vs 0.1 sold: the paper trade is up ({net})");
    // +9: nothing after 1015 on the token; written when the feed passes 1019
    let e = z.buy(w(9), 1_000); q.tr(&e, 1019);
    assert_eq!(q.outc().len(), 2);
    let e = z.buy(w(9), 1_000); q.tr(&e, 1025);
    let o = q.outc();
    assert!(o.len() == 3 && o[2]["h"] == 9 && o[2]["end_slot"] == 1019 && o[2]["vsol"] == e5.vsol && o[2]["n_buys"] == 4 && o[2]["paper"]["net"].as_i64().unwrap() > net, "{}", o[2]);
    assert!(q.q.open_n() == 0 && q.l(&q.q.st.outcomes) == 3);
    assert!(q.l(&q.q.st.pw[0]) == 1 && q.l(&q.q.st.pw[1]) == 1 && q.q.st.pnet[0].load(Ordering::Relaxed) == net);
    // a trade of the token after +9 changes nothing
    let e = tk.buy(w(4), S / 100); q.tr(&e, 1026);
    assert_eq!(q.outc().len(), 3);

    // a token nobody touches after the trigger: all three horizons at once when the feed jumps, the price unchanged, the paper trade pays
    // its costs: -(2 x 1.25% x 0.5 SOL + 1.5 mSOL) = -14 mSOL (within rounding)
    let mut q = Q::new("b16.json");
    let mut tk = q.token(0x20, 1000);
    let mut z = q.token(0x21, 1000);
    let e = tk.buy(w(1), S); q.tr(&e, 1010);
    let e = z.buy(w(9), 1_000); q.tr(&e, 1020);
    let o = q.outc();
    assert_eq!(o.iter().map(|r| r["h"].as_u64().unwrap()).collect::<Vec<_>>(), vec![1, 4, 9]);
    assert!(o.iter().all(|r| r["ret"] == 0.0 && r["buy_sol"] == 0 && r["n_sells"] == 0));
    let n9 = o[2]["paper"]["net"].as_i64().unwrap();
    assert!(o[1]["paper"]["net"] == n9 && (n9 + 14_000_000).abs() < 5, "{n9}");
    assert!(q.l(&q.q.st.pl[0]) == 1 && q.l(&q.q.st.pl[1]) == 1);
    // the pure function: an empty curve gives nothing
    assert!(paper((0, 1), (1, 1), S).is_none() && paper((30 * S, 1_073_000_000_000_000), (30 * S, 1_073_000_000_000_000), 0).is_none());
    // a trigger still open at the run's end is counted, not written
    let e = tk.buy(w(5), S); q.tr(&e, 1050);
    let mut lines = Vec::new();
    let end = q.q.finish(&mut lines);
    assert!(end["open_at_end"] == 1 && end["triggers"] == 2 && end["outcomes"] == 3 && end["paper4"]["l"] == 1 && end["paper9"]["net"] == n9, "{end}");
}

// ---- Q1: the flags -----------------------------------------------------------------------------------------------------------------

#[test]
fn dip42_q1_flags() {
    let c = cfg(&["--q1-log", "on", "--q1-bots", "/x/registry.json"]).unwrap().unwrap();
    let q = c.q1.clone().unwrap();
    assert_eq!(q, Q1Cfg { min_sol: S / 2, age: (3, 80), bot_slots: 100, dip_slots: 200, fresh_max: 2, gap: 30, size: S / 2, fresh_ns: 48 * H, bots: "/x/registry.json".into(), state: None,
        fam: default_wallets() }, "the study's thresholds are the defaults");
    let j = &c.json()["q1"];
    assert!(j["min_sol"] == 0.5 && j["age"] == serde_json::json!([3, 80]) && j["fresh_max"] == 2 && j["gap_slots"] == 30 && j["horizons"] == serde_json::json!([1, 4, 9])
        && j["fee_bps"] == 125 && j["fixed"] == 1_500_000 && j["bot_slots"] == 100 && j["dip_slots"] == 200, "{j}");
    let fw = b58(&w(1));
    let c = cfg(&["--q1-log", "on", "--q1-bots", "/b", "--q1-fresh-state", "/s", "--q1-min-sol", "1", "--q1-age-slots", "5:60", "--q1-bot-slots", "50", "--q1-dip-slots", "150",
        "--q1-fresh-max", "5", "--q1-gap-slots", "10", "--q1-size-sol", "0.25", "--q1-fresh-hours", "24", "--presend-live-fam2", "on", "--presend-live-fam2-wallets", &fw]).unwrap().unwrap();
    assert_eq!(c.q1, Some(Q1Cfg { min_sol: S, age: (5, 60), bot_slots: 50, dip_slots: 150, fresh_max: 5, gap: 10, size: S / 4, fresh_ns: 24 * H, bots: "/b".into(), state: Some("/s".into()),
        fam: vec![w(1)] }), "Q1's family is FAM2's wallet list");
    assert!(cfg(&["--q1-log", "off"]).unwrap().unwrap().q1.is_none());
    for (x, want) in [(&["--q1-log", "on"][..], "needs --q1-bots FILE"),
                      (&["--q1-bots", "/b"][..], "needs --q1-log on"),
                      (&["--q1-min-sol", "1"][..], "needs --q1-log on"),
                      (&["--q1-fresh-state", "/s"][..], "needs --q1-log on"),
                      (&["--q1-log", "maybe"][..], "on | off"),
                      (&["--q1-log", "on", "--q1-bots"][..], "needs a value"),
                      (&["--q1-log", "on", "--q1-bots", "/b", "--q1-age-slots", "80:3"][..], "LO:HI"),
                      (&["--q1-log", "on", "--q1-bots", "/b", "--q1-age-slots", "3:401"][..], "LO:HI"),
                      (&["--q1-log", "on", "--q1-bots", "/b", "--q1-min-sol", "0"][..], "0.01..100"),
                      (&["--q1-log", "on", "--q1-bots", "/b", "--q1-size-sol", "11"][..], "0.01..10"),
                      (&["--q1-log", "on", "--q1-bots", "/b", "--q1-fresh-max", "7"][..], "0..6"),
                      (&["--q1-log", "on", "--q1-bots", "/b", "--q1-fresh-max", "x"][..], "whole number"),
                      (&["--q1-log", "on", "--q1-bots", "/b", "--q1-bot-slots", "0"][..], "1..400"),
                      (&["--q1-log", "on", "--q1-bots", "/b", "--q1-fresh-hours", "0.5"][..], "1..240")] {
        let e = format!("{:#}", cfg(x).unwrap_err());
        assert!(e.contains(want), "{x:?}: {e}");
    }
    assert!(crate::check_flags(&args(&["--q1-log", "on", "--q1-bots", "/b", "--q1-fresh-state", "/s", "--q1-min-sol", "0.5", "--q1-age-slots", "3:80", "--q1-bot-slots", "100",
        "--q1-dip-slots", "200", "--q1-fresh-max", "2", "--q1-gap-slots", "30", "--q1-size-sol", "0.5", "--q1-fresh-hours", "48"])).is_ok(), "every flag known to the start-up check");
    assert!(crate::check_flags(&args(&["--q1-log", "on", "--q1-bots", "/b", "--q1-gap-slots", "ten"])).is_err());
    assert!(crate::check_flags(&args(&["--q1-logs", "on"])).is_err(), "a misspelled flag is refused");
    assert_eq!(age_parse("3:80").unwrap(), (3, 80));
    assert!(age_parse("3").is_err() && age_parse("a:b").is_err());
}

// ---- both in the engine: LOG ONLY ----------------------------------------------------------------------------------------------------

/// Q1 through the probe's feed hook (inline): the creates and trades of on_exec reach it, its records land in the log, the status line and
/// run_end carry it; a mayhem create is never followed
#[test]
fn dip42_q1_in_the_engine() {
    let bots = bots_file("b17.json", &[BOT]);
    let mut c = Ctx::new(&["--q1-log", "on", "--q1-bots", &bots]);
    let cr = c.ev("q1_config");
    assert!(cr.len() == 1 && cr[0]["mode"] == "log" && cr[0]["bots_n"] == 1 && cr[0]["fresh_max"] == 2, "{cr:?}");
    let mut tk = c.token(0x71);
    let e = tk.buy(w(0x21), S / 2); c.tx(1010, 7, vec![e.clone()], vec![]);
    let t = c.ev("q1_trigger");
    assert!(t.len() == 1 && t[0]["mint"] == b58(&tk.mint) && t[0]["slot"] == 1010 && t[0]["idx"] == 7 && t[0]["j"] == 0 && t[0]["buyer"] == b58(&w(0x21)) && t[0]["sol"] == S / 2
        && t[0]["age"] == 10 && t[0]["t"] == T0 + 1010 * SLOT_NS + 7 && t[0]["sig"].as_str().is_some_and(|s| s.len() > 60), "{t:?}");
    // a mayhem launch: its big fresh buy is not a trigger
    let mut may = Tk::new(0x72);
    let dev = may.buy(CREATOR, S / 2);
    let mut sig = [0u8; 64]; sig[0] = 0x4D;
    c.tx_sig(1010, 20, sig, vec![dev], vec![may.create()], true);
    let e = may.buy(w(0x22), S); c.tx(1015, 3, vec![e], vec![]);
    assert_eq!(c.ev("q1_trigger").len(), 1);
    // the feed moves on: the three outcomes
    let e = may.buy(w(0x23), 1_000); c.tx(1020, 3, vec![e], vec![]);
    let o = c.ev("q1_outcome");
    assert!(o.len() == 3 && o[1]["h"] == 4 && o[1]["paper"]["label"] == "paper" && o[2]["h"] == 9, "{o:?}");
    let st = c.p.status();
    assert!(st.contains(" | Q1 LOG WARM-UP: triggers 1 (1 in warm-up) of 1 big buys (not quiet 0, not fresh 0, repeat 0) | paper 0.5 SOL +4 0W/1L -0.014 SOL, +9 0W/1L -0.014 SOL"), "{st}");
    let end = c.p.finish(1100, None);
    assert!(end["q1"]["triggers"] == 1 && end["q1"]["outcomes"] == 3 && end["q1"]["mode"] == "log" && end["cfg"]["q1"]["bots"] == bots, "{}", end["q1"]);
    // nothing was armed, sent or queued
    assert!(c.ev("presend_live_arm").is_empty() && c.p.sh.wins.lock().unwrap().is_empty() && c.p.sh.sent.load(Ordering::Relaxed) == 0 && c.cmds.is_empty());
}

/// LOG ONLY: with FAM2 and Q1 on, the same feed gives the same decisions (windows, attempts, sells, realized), the same records but the
/// "fam2" fields and Q1's own records, and nothing is sent; with them off no trace of them (dip41's records)
#[test]
fn dip42_log_only_changes_no_other_record() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let bots = bots_file("b18.json", &[BOT]);
    let run = |extra: &[&str]| {
        let mut c = Ctx::new(extra);
        let (_, _, rz) = c.scenario();
        // a quiet token with a fresh wallet's big buy and what follows (a Q1 trigger with the log on)
        let mut tk = c.token(0x75);
        let e = tk.buy(w(0x21), S); c.tx(1020, 7, vec![e], vec![]);
        let e = tk.buy(w(0x22), S / 5); c.tx(1022, 8, vec![e], vec![]);
        let e = tk.buy(w(0x23), S / 5); c.tx(1040, 9, vec![e], vec![]);
        let wins: Vec<(u64, Pk, u64)> = c.p.sh.wins.lock().unwrap().iter().map(|x| (x.id, x.mint, x.spend)).collect();
        let st = c.p.status();
        let end = c.p.finish(1100, None);
        c.pump();
        (c, rz, wins, st, end)
    };
    let (c0, rz0, wins0, st0, end0) = run(&[]);
    let (c1, rz1, wins1, st1, end1) = run(&["--presend-live-fam2", "on", "--q1-log", "on", "--q1-bots", &bots]);
    // off: no trace
    assert!(c0.recs.iter().all(|r| r.get("fam2").is_none() && !r["ev"].as_str().unwrap_or("").starts_with("q1_") && r["ev"] != "presend_live_fam2_config"));
    assert!(!st0.contains("FAM2") && !st0.contains("Q1 LOG") && end0.get("fam2").is_none() && end0.get("q1").is_none() && end0["cfg"].get("fam2").is_none() && end0["cfg"].get("q1").is_none());
    assert!(matches!(rz0, Cmd::Realized { f2: None, .. }));
    // on: the records but "fam2" and Q1's own are dip41's, in the same order
    assert!(c1.ev("q1_trigger").len() >= 1 && c1.ev("q1_outcome").len() >= 3 && c1.recs.iter().any(|r| r.get("fam2").is_some()), "the logs did write");
    // (the wall-clock fields of a record differ between any two runs: left out on both sides)
    let norm = |v: &[serde_json::Value]| -> Vec<serde_json::Value> { v.iter().cloned().map(|mut r| { if let Some(o) = r.as_object_mut() {
        o.remove("armed_ms"); o.remove("held_s");
        if o.get("t").and_then(|t| t.as_u64()).is_some_and(|t| t > T0 + 100_000 * S) { o.remove("t"); } } r }).collect() };
    let mut r1: Vec<serde_json::Value> = c1.recs.iter().filter(|r| !r["ev"].as_str().unwrap_or("").starts_with("q1_") && r["ev"] != "presend_live_fam2_config").cloned().collect();
    for r in r1.iter_mut() { if let Some(o) = r.as_object_mut() { o.remove("fam2"); } }
    let (n0, n1) = (strip(&norm(&c0.recs)), strip(&norm(&r1)));
    assert_eq!(n0.len(), n1.len());
    for (a, b) in n0.iter().zip(&n1) { assert_eq!(a, b, "every other record unchanged"); }
    // the same windows, the same chain work (the realized's own fam2 aside), the same lines but the logs' own, nothing sent
    assert_eq!(wins0, wins1);
    let dbg = |v: &[Cmd]| v.iter().map(|x| match x.clone() {
        Cmd::Realized { pid, w, mint, buys, sells, rearm, cr, ab, wh, hl, l38, s1, wd, .. } => format!("{:?}", Cmd::Realized { pid, w, mint, buys, sells, rearm, cr, ab, wh, hl, l38, s1, wd, f2: None }),
        o => format!("{o:?}") }).collect::<Vec<_>>();
    assert_eq!(dbg(&c0.cmds), dbg(&c1.cmds));
    assert!(matches!(rz1, Cmd::Realized { f2: Some(_), .. }));
    let l1: Vec<&String> = c1.lines.iter().filter(|l| !l.contains("Q1 LOG")).collect();
    assert_eq!(l1, c0.lines.iter().collect::<Vec<_>>());
    assert!(c0.p.sh.sent.load(Ordering::Relaxed) == 0 && c1.p.sh.sent.load(Ordering::Relaxed) == 0);
    // run_end: the same but the two parts and the config's
    let mut e1 = end1.clone();
    for k in ["fam2", "q1"] { e1.as_object_mut().unwrap().remove(k); e1["cfg"].as_object_mut().unwrap().remove(k); }
    assert_eq!(e1.to_string(), end0.to_string());
    assert!(st1.contains(" | FAM2 LOG (4 wallets, 300 slots)") && st1.contains(" | Q1 LOG WARM-UP: triggers 2 (2 in warm-up) of 3 big buys"), "the status line carries the two parts\n{st0}\n{st1}");
}

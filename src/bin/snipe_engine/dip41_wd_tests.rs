// ===================================================================================================================
// dip41 DUMPER LEDGER + WIDE-DUMPER tier tests (psdl.rs: --presend-live-dumper-ledger on, --presend-live-dumper-state PATH,
// --presend-live-wide-dumper N:SCORE, --presend-live-wide-dumper-mode log|live, --presend-live-wide-size-sol X, the control file's
// "widedumper"). The ledger: >= 3% buys only, resolution at buy + 25 slots, dumped = >= 30% sold within 20 slots (the edges), the per-wallet
// cap, mayhem / create-slot buys left out, the idle prune; the rule's N / SCORE edges; the state round trip (and the seed format); the tier:
// the 3..6% band, the age rules, one window per token, LOG sends nothing, LIVE = a T2-path window "kind":"wide" (size, fill, realized),
// the T2 arm's "dumper" annotation, the flags, the control file, off = dip39.
// ===================================================================================================================
use super::*;
use super::psdl::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;
const LED: [&str; 2] = ["--presend-live-dumper-ledger", "on"];

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000) }
fn with_led(extra: &[&str]) -> Vec<String> { LED.iter().chain(extra.iter()).map(|s| s.to_string()).collect() }
fn pctr(x: f64) -> u64 { (x / 100.0 * pl::SUPPLY).round() as u64 }
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x41; x }
fn tmp(name: &str) -> String { std::env::temp_dir().join(format!("dip41-wd-{}-{name}", std::process::id())).to_string_lossy().to_string() }
fn sold(c: Option<u64>, sigs: &[&str], qty: u64) -> SellOut {
    SellOut { sold_at: c, sigs: sigs.iter().map(|s| (s.to_string(), true, 1_200_000)).collect(), last: None, attempts: sigs.len() as u32, last_qty: (qty, true), first_send_us: None }
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
    fn create(&self) -> CreateEvent { CreateEvent { mint: self.mint, bonding_curve: self.launch.bonding_curve, user: CREATOR, creator: CREATOR } }
}

struct Ctx { p: PsLive, atx: crossbeam_channel::Sender<Att>, orx: crossbeam_channel::Receiver<Out>, launches: Vec<Launch>, recs: Vec<serde_json::Value>, lines: Vec<String>, cmds: Vec<Cmd> }
impl Ctx {
    fn new(extra: &[&str]) -> Ctx {
        let (p, atx, orx) = PsLive::for_test(cfg(extra).unwrap().unwrap(), USER);
        Ctx { p, atx, orx, launches: Vec::new(), recs: Vec::new(), lines: Vec::new(), cmds: Vec::new() }
    }
    fn led(extra: &[&str]) -> Ctx { let a = with_led(extra); Ctx::new(&a.iter().map(|s| s.as_str()).collect::<Vec<_>>()) }
    fn pump(&mut self) {
        for o in self.orx.try_iter() { match o { Out::Rec(v) => self.recs.push(v), Out::Line(l) => self.lines.push(l) } }
        self.cmds.extend(self.p.take_cmds());
    }
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
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0x41; sig[17] = trades.first().map_or(0, |t| t.mint[0]);
        self.tx_sig(slot, idx, sig, trades, creates);
    }
    fn ev(&self, k: &str) -> Vec<serde_json::Value> { self.recs.iter().filter(|r| r["ev"] == k).cloned().collect() }
    /// the whale's history on tokens the detector never saw created (no Below there): `dumps` buys of 4% sold 50% 5 slots later, then
    /// `holds` buys kept; one token each, from slot `s0`, 10 slots apart (all resolved long before slot 1000)
    fn history(&mut self, whale: Pk, dumps: u32, holds: u32, k0: u8, s0: u64) {
        for i in 0..dumps + holds {
            let mut tk = Tk::new(k0 + i as u8);
            let s = s0 + 10 * i as u64;
            let e = tk.buy_tok(whale, pctr(4.0)); self.tx(s, 1, vec![e.clone()], vec![]);
            if i < dumps { let x = tk.sell_tok(whale, e.tok / 2); self.tx(s + 5, 2, vec![x], vec![]); }
        }
    }
    /// QF2's history: `quick` buys of 4% with 10% sold 5 slots later (quick, not dumped), then `holds` kept
    fn history_q(&mut self, whale: Pk, quick: u32, holds: u32, k0: u8, s0: u64) {
        for i in 0..quick + holds {
            let mut tk = Tk::new(k0 + i as u8);
            let s = s0 + 10 * i as u64;
            let e = tk.buy_tok(whale, pctr(4.0)); self.tx(s, 1, vec![e.clone()], vec![]);
            if i < quick { let x = tk.sell_tok(whale, e.tok / 10); self.tx(s + 5, 2, vec![x], vec![]); }
        }
    }
    /// token `k` created at 1000, 7 buyers of 0.8 SOL at 1001 (each < 3%: the curve ~36 SOL), the whale's `pct`% at 1000 + age (QF2's filters:
    /// a 5% buy ~2.1 SOL, the curve after it ~38 vSOL)
    fn qf_token(&mut self, k: u8, whale: Pk, pct: f64, age: u64) -> Tk {
        let mut tk = Tk::new(k);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, vec![dev], vec![tk.create()]);
        for i in 0..7u8 { let e = tk.buy(w(0x20 + i), 800_000_000); self.tx(1001, 2 + i as u64, vec![e], vec![]); }
        let e = tk.buy_tok(whale, pctr(pct)); self.tx(1000 + age, 50, vec![e], vec![]);
        tk
    }
    /// token `k` created at 1000 (a dev buy, another buyer at 1001); the whale buys `pct`% at 1000 + age
    fn wide(&mut self, k: u8, whale: Pk, pct: f64, age: u64) -> Tk {
        let mut tk = Tk::new(k);
        self.launches.push(tk.launch.clone());
        let dev = tk.buy(CREATOR, S / 2);
        self.tx(1000, 1, vec![dev], vec![tk.create()]);
        let e = tk.buy(w(0x11), S / 10); self.tx(1001, 2, vec![e], vec![]);
        let e = tk.buy_tok(whale, pctr(pct)); self.tx(1000 + age, 50, vec![e], vec![]);
        tk
    }
    /// an attempt of window `id` at `slot` (the sender's registration)
    fn att(&mut self, id: u64, mint: Pk, slot: u64) -> [u8; 64] {
        let mut sg = [0u8; 64]; sg[0] = 0xD4; sg[1] = 0x41; sg[3] = slot as u8;
        self.atx.send(Att { w: id, n: 1, mint, sig: sg, tag: pl::PS_TAG | 0x41, path: "helius-ps".into(), client: "JitoLabs".into(), slot, deadline: slot + 1,
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (slot, 0, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
            tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46: Default::default() }).unwrap();
        self.p.drain_atts();
        self.pump();
        sg
    }
    /// fill with `sg` at slot `b`, a filler token moves the clock to the exit, the sell lands -> the Cmd::Realized
    fn fill_close(&mut self, tk: &mut Tk, sg: [u8; 64], b: u64) -> Cmd {
        let e = tk.buy(USER, 296_000_000);
        self.tx_sig(b, 4, sg, vec![e.clone()], vec![]);
        let mut z = Tk::new(0x7F);
        self.launches.push(z.launch.clone());
        let dz = z.buy(CREATOR, S / 2);
        self.tx(b, 900, vec![dz], vec![z.create()]);
        for s in b + 1..=b + 2 { let e = z.buy([0x2F; 32], 1_000_000); self.tx(s, 900, vec![e], vec![]); }
        let Some(Cmd::Sell { pid, .. }) = self.cmds.iter().rev().find(|x| matches!(x, Cmd::Sell { .. })).cloned() else { panic!("no sell: {:?}", self.cmds) };
        let es = tk.sell_tok(USER, e.tok);
        self.tx_sig(b + 2, 9, { let mut s = [0u8; 64]; s[0] = 0x5E; s[1] = 0x41; s }, vec![es], vec![]);
        self.p.on_msg(PsMsg::Sold(tk.mint, pid, 1, sold(Some(b + 2), &["S41"], e.tok)), &|_| false);
        self.pump();
        self.cmds.iter().rev().find(|x| matches!(x, Cmd::Realized { .. })).cloned().expect("realized")
    }
}

// ---- the ledger (pure) -------------------------------------------------------------------------------------------------------------

const M: Pk = [0x91u8; 32];
const M2: Pk = [0x92u8; 32];
const T0: u64 = 1_000_000_000_000_000_000;
fn tk(p: f64) -> u64 { pctr(p) }
fn buy(l: &mut Ledger, m: Pk, u: Pk, tok: u64, s: u64) { l.trade(m, u, true, tok, 900_000_000_000_000, s, T0 + s * 400_000_000, None); }
fn sell(l: &mut Ledger, m: Pk, u: Pk, tok: u64, s: u64) { l.trade(m, u, false, tok, 900_000_000_000_000, s, T0 + s * 400_000_000, None); }
fn tick(l: &mut Ledger, s: u64) { l.trade([0x99; 32], w(0x99), true, 1, 900_000_000_000_000, s, T0 + s * 400_000_000, None); }

/// a buy counts only once 25 slots have passed (ledger.look lag 25: buys at <= S - 25); only >= 3% buys
#[test]
fn dip41_ledger_resolution_at_25_slots() {
    let a = w(1);
    let mut l = Ledger::default();
    buy(&mut l, M, a, tk(3.0), 100);
    buy(&mut l, M2, a, tk(2.99), 100);               // < 3%: never a ledger buy
    assert_eq!(l.pending(), 1);
    tick(&mut l, 124);
    assert_eq!(l.look(&a), WdV::default(), "slot 124: not yet (100 + 25 > 124)");
    tick(&mut l, 125);
    assert_eq!(l.look(&a), WdV { n: 1, d: 0, q: 0 }, "slot 125: resolved, not dumped");
    assert!(l.pending() == 0 && l.resolved == 1 && l.buys == 1);
    // the same wallet's two buys of one mint resolve one by one, in order
    buy(&mut l, M, a, tk(4.0), 200);
    buy(&mut l, M, a, tk(4.0), 210);
    sell(&mut l, M, a, tk(2.4), 215);                // 60% of one buy: both windows see it (each >= 30%: both dumped)
    tick(&mut l, 225);
    assert_eq!(l.look(&a), WdV { n: 2, d: 1, q: 0 }, "the 200 buy: sold at 215 = +15 > 10: not quick");
    tick(&mut l, 234);
    assert_eq!(l.look(&a), WdV { n: 2, d: 1, q: 0 }, "210 + 25 = 235");
    tick(&mut l, 235);
    assert_eq!(l.look(&a), WdV { n: 3, d: 2, q: 1 }, "the 210 buy: sold at +5: quick");
}

/// dumped = the wallet's own sells of that mint after the buy, slots <= buy + 20, summed >= 30% of the buy's tokens (exact edges)
#[test]
fn dip41_ledger_dump_30pct_20_slots() {
    let (a, b) = (w(1), w(2));
    let t = tk(4.0);
    // (d = >= 30% within 20 slots, q = any sell within 10 slots: the default rule 20:0.3 / 10)
    let cases: Vec<(&str, Vec<(Pk, Pk, u64, u64)>, bool, bool)> = vec![
        ("exactly 30% at +20", vec![(a, M, t * 3 / 10, 120)], true, false),
        ("30% at +21", vec![(a, M, t * 3 / 10, 121)], false, false),
        ("one token short of 30%", vec![(a, M, t * 3 / 10 - 1, 105)], false, true),
        ("two sells summing 30%", vec![(a, M, t / 10, 101), (a, M, t / 5, 119)], true, true),
        ("the same slot as the buy (after it)", vec![(a, M, t / 2, 100)], true, true),
        ("1 token at +10 (quick edge)", vec![(a, M, 1, 110)], false, true),
        ("1 token at +11", vec![(a, M, 1, 111)], false, false),
        ("another wallet's sell", vec![(b, M, t, 101)], false, false),
        ("its sell of another mint", vec![(a, M2, t, 101)], false, false),
    ];
    for (name, sells, want, quick) in cases {
        let mut l = Ledger::default();
        buy(&mut l, M, a, t, 100);
        for (u, m, q, s) in sells { sell(&mut l, m, u, q, s); }
        tick(&mut l, 125);
        assert_eq!(l.look(&a), WdV { n: 1, d: want as u32, q: quick as u32 }, "{name}");
    }
    // another rule (--presend-live-wide-dumper ..:..:5:0.5, QF2 WIN 3): the same sells, other flags
    let mut l = Ledger::new(Rule { win: 5, frac_pm: 500, qwin: 3 });
    buy(&mut l, M, a, t, 100);
    sell(&mut l, M, a, t * 4 / 10, 104);
    sell(&mut l, M, a, t / 10, 105);
    sell(&mut l, M, a, t, 106);
    tick(&mut l, 125);
    assert_eq!(l.look(&a), WdV { n: 1, d: 1, q: 0 }, "50% by +5 (the +6 sell out), nothing by +3");
    // mayhem curves and create-slot buys are not ledger buys
    let mut l = Ledger::default();
    l.trade(M, a, true, t, DL_MAYHEM_VTOK + 1, 100, T0, None);
    l.trade(M2, a, true, t, 900_000_000_000_000, 100, T0, Some(100));
    l.trade(M2, b, true, t, 900_000_000_000_000, 101, T0, Some(100));
    tick(&mut l, 200);
    assert!(l.look(&a).n == 0 && l.look(&b).n == 1);
}

/// the newest 50 per wallet; a wallet idle 48 h is forgotten
#[test]
fn dip41_ledger_cap_and_idle() {
    let a = w(1);
    let mut l = Ledger::default();
    for i in 0..60u64 { buy(&mut l, [i as u8; 32], a, tk(3.5), 100 + i); if i < 10 { sell(&mut l, [i as u8; 32], a, tk(3.5), 101 + i); } }
    tick(&mut l, 200);
    let h = &l.hist[&a];
    assert_eq!(h.b.len(), DL_KEEP);
    assert_eq!(h.b.front().unwrap().0, 110, "the 10 oldest (the dumped ones) dropped");
    assert_eq!(l.look(&a), WdV { n: 50, d: 0, q: 0 });
    // 48 h later (the feed's clock) the prune forgets it
    let s = 200 + 1500;
    l.trade([0x99; 32], w(0x98), true, 1, 900_000_000_000_000, s, l.hist[&a].t + DL_IDLE_NS + 1, None);
    l.prune(s);
    assert!(!l.hist.contains_key(&a) && l.forgot == 1);
}

/// N:SCORE: n >= N and d / n >= SCORE (the 0.8 edge exact); the parser's ranges
#[test]
fn dip41_rule_thresholds() {
    let c = WdCfg::default();
    assert_eq!((c.n, c.score, c.win, c.frac), (3, 0.8, 20, 0.3));
    let p = |n, h| pass(c.n, c.score, n, h);
    assert!(!p(2, 2), "n 2 < 3");
    assert!(p(3, 3) && !p(3, 2), "3/3 yes, 2/3 = 0.67 no");
    assert!(p(5, 4), "4/5 = 0.8: the edge passes");
    assert!(!p(5, 3));
    assert!(p(10, 8) && !p(10, 7));
    assert!(!pass(1, 0.0, 0, 0), "never with no history");
    // QF2 5:0.3: n >= 5 and >= 30% quick
    assert!(!pass(5, 0.3, 4, 4) && pass(5, 0.3, 10, 3) && !pass(5, 0.3, 10, 2));
    assert_eq!(wd_parse("5:0.9").unwrap(), WdCfg { n: 5, score: 0.9, ..Default::default() });
    assert_eq!(wd_parse(" 3 : 1 ").unwrap(), WdCfg { n: 3, score: 1.0, ..Default::default() });
    assert_eq!(wd_parse("3:0.8:10:0.5").unwrap(), WdCfg { n: 3, score: 0.8, win: 10, frac: 0.5 });
    for bad in ["0:0.8", "51:0.8", "3:1.1", "3:-0.1", "3", "x:0.8", "3:nan", "", "3:0.8:20", "3:0.8:21:0.3", "3:0.8:0:0.3", "3:0.8:20:0", "3:0.8:20:1.5"] {
        assert!(wd_parse(bad).is_err(), "{bad}");
    }
    assert_eq!(qf_parse("5:0.3").unwrap(), QfCfg { n: 5, score: 0.3, win: 10 });
    assert_eq!(qf_parse("5:0.3:8").unwrap(), QfCfg { n: 5, score: 0.3, win: 8 });
    for bad in ["5", "5:0.3:21", "0:0.3", "5:2", "5:0.3:10:1"] { assert!(qf_parse(bad).is_err(), "{bad}"); }
    assert_eq!(qf_filt_parse("2:8:36:70:300").unwrap(), QfFilt::default());
    for bad in ["2:8:36:70", "8:2:36:70:300", "2:8:70:36:300", "2:8:36:70:x", "-1:8:36:70:300"] { assert!(qf_filt_parse(bad).is_err(), "{bad}"); }
    let f = QfFilt::default();
    assert_eq!(f.check(2_000_000_000, 36_000_000_000, 300), (true, true, true), "the edges pass");
    assert_eq!(f.check(1_999_999_999, 70_000_000_001, 301), (false, false, false));
    assert!(!mode_parse("-x", "log").unwrap() && mode_parse("-x", "live").unwrap() && mode_parse("-x", "on").is_err());
    assert_eq!(WdV { n: 5, d: 4, q: 1 }.json(Kind::Wide), serde_json::json!({"n": 5, "d": 4, "score": 0.8}));
    assert_eq!(WdV { n: 5, d: 4, q: 1 }.json(Kind::Qf2), serde_json::json!({"n": 5, "q": 1, "score": 0.2}));
    assert_eq!(WdV::default().json(Kind::Wide)["score"], serde_json::Value::Null);
}

/// the state: JSON round trip (the seed's format), idle wallets dropped at load, a list cut to 50, the atomic save (.new renamed)
#[test]
fn dip41_state_round_trip() {
    let (a, b) = (w(1), w(2));
    let mut l = Ledger::default();
    for i in 0..4u64 { buy(&mut l, [i as u8 + 1; 32], a, tk(4.0), 100 + 10 * i); if i != 2 { sell(&mut l, [i as u8 + 1; 32], a, tk(2.0), 102 + 10 * i); } }
    buy(&mut l, M, b, tk(5.0), 150);
    tick(&mut l, 300);
    let j = l.state_json();
    assert!(j["v"] == 1 && j["kind"] == "dumper_ledger" && j["rule"]["resolve_slots"] == 25 && j["rule"]["dump_slots"] == 20 && j["rule"]["keep"] == 50, "{j}");
    assert_eq!(j["w"][b58(&a)]["b"], serde_json::json!([[100, 1, 1], [110, 1, 1], [120, 0, 0], [130, 1, 1]]));
    let mut l2 = Ledger::default();
    assert_eq!(l2.state_load(j.to_string().as_bytes()).unwrap(), 2);
    assert_eq!(l2.hist, l.hist);
    assert!(l2.look(&a) == WdV { n: 4, d: 3, q: 3 } && l2.look(&b) == WdV { n: 1, d: 0, q: 0 });
    // idle > 48 h before the state's clock: dropped; a long list cut to the newest 50; bad files refused
    let t = 10 * DL_IDLE_NS;
    let long: Vec<serde_json::Value> = (0..60).map(|i| serde_json::json!([i, (i >= 10) as u8, 0])).collect();
    let s = serde_json::json!({"v": 1, "kind": "dumper_ledger", "t": t, "slot": 5, "rule": Rule::default().json(),
        "w": {b58(&a): {"t": t - DL_IDLE_NS - 1, "b": [[1, 1, 1]]}, b58(&b): {"t": t, "b": long}}});
    let mut l3 = Ledger::default();
    assert_eq!(l3.state_load(s.to_string().as_bytes()).unwrap(), 1);
    assert!(l3.look(&a).n == 0 && l3.look(&b) == WdV { n: 50, d: 50, q: 0 });
    for bad in [&b"nope"[..], br#"{"v": 2, "t": 1, "w": {}}"#, br#"{"v": 1, "w": {}}"#, br#"{"v": 1, "t": 1, "w": {"xx!": {"t": 1, "b": []}}}"#] {
        assert!(Ledger::default().state_load(bad).is_err());
    }
    // a state of another rule is refused (its flags would mean other things); an old 2-field entry too
    let other = serde_json::json!({"v": 1, "t": 1, "rule": Rule { win: 10, ..Default::default() }.json(), "w": {}}).to_string();
    let e = Ledger::default().state_load(other.as_bytes()).unwrap_err().to_string();
    assert!(e.contains("is not the flags'"), "{e}");
    let two = serde_json::json!({"v": 1, "t": 1, "rule": Rule::default().json(), "w": {b58(&a): {"t": 1, "b": [[1, 1]]}}}).to_string();
    for bad in [two.as_bytes()] {
        assert!(Ledger::default().state_load(bad).is_err());
    }
    // Wd: a missing file = empty, saved atomically, preloaded again
    let p = tmp("state.json");
    let _ = std::fs::remove_file(&p);
    let mut d = Wd::open(WdCfg::default(), false, None, QfFilt::default(), false, 1, Some(&p));
    assert!(d.loaded == Some(0) && d.err.is_none());
    d.led = l;
    assert_eq!(d.save(true), Some(Ok(2)));
    assert!(std::path::Path::new(&p).exists() && !std::path::Path::new(&format!("{p}.new")).exists());
    let d2 = Wd::open(WdCfg::default(), false, None, QfFilt::default(), false, 1, Some(&p));
    assert!(d2.loaded == Some(2) && d2.led.look(&a) == WdV { n: 4, d: 3, q: 3 });
    std::fs::write(&p, "garbage").unwrap();
    let d3 = Wd::open(WdCfg::default(), false, None, QfFilt::default(), false, 1, Some(&p));
    assert!(d3.err.is_some() && d3.led.hist.is_empty(), "a bad state: an empty ledger, the error kept");
    let _ = std::fs::remove_file(&p);
}

// ---- the flags -------------------------------------------------------------------------------------------------------------------

#[test]
fn dip41_flags() {
    let c = cfg(&[]).unwrap().unwrap();
    assert!(!c.dl_on && c.json().get("widedumper").is_none(), "off by default: dip39's run_start");
    let c = cfg(&["--presend-live-dumper-ledger", "on"]).unwrap().unwrap();
    assert!(c.dl_on && c.wd == WdCfg::default() && !c.wd_live && c.wd_size == 400_000_000 && c.dl_state.is_none());
    assert_eq!(c.json()["widedumper"], serde_json::json!({"ledger": true, "state": null, "n": 3, "score": 0.8, "win": 20, "frac": 0.3, "mode": "log", "size": 400_000_000u64}));
    let c = cfg(&["--presend-live-dumper-ledger", "on", "--presend-live-dumper-state", "/x/s.json", "--presend-live-wide-dumper", "5:0.9", "--presend-live-wide-dumper-mode", "live",
        "--presend-live-wide-size-sol", "0.25"]).unwrap().unwrap();
    assert!(c.wd == WdCfg { n: 5, score: 0.9, ..Default::default() } && c.wd_live && c.wd_size == 250_000_000 && c.dl_state.as_deref() == Some("/x/s.json"));
    for (a, want) in [(&["--presend-live-dumper-state", "/x"][..], "needs --presend-live-dumper-ledger on"),
                      (&["--presend-live-wide-dumper", "3:0.8"][..], "needs --presend-live-dumper-ledger on"),
                      (&["--presend-live-wide-dumper-mode", "live"][..], "needs --presend-live-dumper-ledger on"),
                      (&["--presend-live-wide-size-sol", "0.3"][..], "needs --presend-live-dumper-ledger on"),
                      (&["--presend-live-dumper-ledger", "yes"][..], "on | off"),
                      (&["--presend-live-dumper-ledger", "on", "--presend-live-wide-dumper", "0:0.8"][..], "N:SCORE"),
                      (&["--presend-live-dumper-ledger", "on", "--presend-live-wide-dumper-mode", "maybe"][..], "log | live"),
                      (&["--presend-live-dumper-ledger", "on", "--presend-live-wide-size-sol", "x"][..], "not a number"),
                      (&["--presend-live-dumper-ledger", "on", "--presend-live-wide-size-sol", "0"][..], "(0, 2]"),
                      (&["--presend-live-dumper-ledger", "on", "--presend-live-wide-size-sol", "1.5"][..], "exceeds --max-sol")] {
        let e = format!("{:#}", cfg(a).unwrap_err());
        assert!(e.contains(want), "{a:?}: {e}");
    }
    // the control file with the ledger alone; every flag known to the start-up check (numbers / strings)
    assert!(cfg(&["--presend-live-dumper-ledger", "on", "--presend-live-ledger-control", "/y"]).is_ok());
    assert!(crate::check_flags(&args(&["--presend-live-dumper-ledger", "on", "--presend-live-dumper-state", "/x", "--presend-live-wide-dumper", "3:0.8",
        "--presend-live-wide-dumper-mode", "log", "--presend-live-wide-size-sol", "0.3"])).is_ok());
    // without --presend-live: refused
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-live-dumper-ledger", "on"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, S).unwrap_err().to_string().contains("needs --presend-live"));
}

// ---- the tier end to end ---------------------------------------------------------------------------------------------------------

/// LOG mode: a 3..6% whale with a dumper record -> a presend_live_widedumper record (values, would_arm, the bot depth verdict), a line,
/// NO window / arm / attempt; a 6%+ whale is T2 (with its "dumper" annotation), never the tier
#[test]
fn dip41_log_mode_sends_nothing() {
    let (wa, wb) = (w(0xA1), w(0xB1));
    let mut c = Ctx::led(&["--presend-live-botdepth", "3:100", "--presend-live-botdepth-list", &{
        let p = tmp("bots.json"); std::fs::write(&p, serde_json::json!([b58(&w(0x11))]).to_string()).unwrap(); p }]);
    c.history(wa, 4, 0, 0x80, 100);
    c.history(wb, 3, 1, 0xA0, 400);
    let tk = c.wide(0x71, wa, 4.0, 10);
    let r = c.ev("presend_live_widedumper");
    assert_eq!(r.len(), 1, "{r:?}");
    let r = &r[0];
    assert!(r["whale"] == b58(&wa) && r["n"] == 4 && r["d"] == 4 && r["score"] == 1.0 && r["pass"] == true && r["would_arm"] == true && r["first"] == true
        && r["mode"] == "log" && r["age_slots"] == 10 && r["size"] == 400_000_000u64, "{r}");
    assert!(r["pct"].as_f64().unwrap() >= 3.99 && r["pct"].as_f64().unwrap() < 4.01);
    assert!(r["botdepth"]["n"] == 1 && r["botdepth"]["block"] == true, "the bot depth verdict at the trigger: {r}");
    assert!(c.lines.iter().any(|l| l.contains("WIDE-DUMPER WOULD ARM (log)") && l.contains("4/4")), "{:?}", c.lines);
    assert!(c.ev("presend_live_arm").is_empty() && c.ev("presend_live_skip").is_empty() && c.p.armed.is_empty() && c.p.sh.wins.lock().unwrap().is_empty(), "log: nothing armed");
    assert!(c.p.wd.as_ref().unwrap().wide.would == 1 && c.p.wd.as_ref().unwrap().wide.armed == 0);
    // wb: 3/4 dumped = 0.75 < 0.8 -> recorded, not would-arm; a 6%+ whale -> T2 with "dumper"
    let _ = tk;
    c.wide(0x72, wb, 4.5, 12);
    let r = c.ev("presend_live_widedumper");
    assert!(r.len() == 2 && r[1]["n"] == 4 && r[1]["d"] == 3 && r[1]["pass"] == false && r[1]["would_arm"] == false, "{r:?}");
    c.wide(0x73, wb, 8.0, 12);
    let a = c.ev("presend_live_arm");
    assert!(a.len() == 1 && a[0].get("kind").is_none() && a[0]["dumper"] == serde_json::json!({"n": 4, "d": 3, "score": 0.75}), "{a:?}");
    assert_eq!(c.ev("presend_live_widedumper").len(), 2, "a T2 whale is never the tier's");
    assert!(c.p.status().contains(" | WIDE DUMPER LOG 3:0.8: ledger 2 wallets (1 pass, 3 pending), would-arm 1, armed 0, withheld 0"), "{}", c.p.status());
    let end = c.p.finish(1100, None);
    assert!(end["widedumper"]["would"] == 1 && end["widedumper"]["recs"] == 2 && end["widedumper"]["mode"] == "log", "{}", end["widedumper"]);
}

/// the band and the age rules: the create slot never (even with --presend-live-create-slot on), --presend-live-min-age-slots; an unknown
/// whale (n 0) gets no record; ONE window per token (a second qualifying whale on it: recorded, first false, not would-arm)
#[test]
fn dip41_band_age_one_per_token() {
    let (wa, wb) = (w(0xA1), w(0xB1));
    let mut c = Ctx::led(&["--presend-live-create-slot", "on", "--presend-live-min-age-slots", "3"]);
    c.history(wa, 3, 0, 0x80, 100);
    c.history(wb, 3, 0, 0xA0, 400);
    // the create slot: the whale's 4% in the create tx's slot
    let mut t0 = Tk::new(0x60);
    c.launches.push(t0.launch.clone());
    let dev = t0.buy(CREATOR, S / 2);
    c.tx(1000, 1, vec![dev], vec![t0.create()]);
    let e = t0.buy_tok(wa, pctr(4.0)); c.tx(1000, 2, vec![e], vec![]);
    // too young (age 2 < 3); an unknown whale
    c.wide(0x61, wa, 4.0, 2);
    c.wide(0x62, w(0xC1), 4.0, 10);
    assert!(c.ev("presend_live_widedumper").is_empty(), "{:?}", c.ev("presend_live_widedumper"));
    assert_eq!(c.p.wd.as_ref().unwrap().wide.cands, 1, "only the unknown whale's crossing was a candidate");
    // one window per token: wa then wb on 0x63
    let mut tk = c.wide(0x63, wa, 4.0, 5);
    let e = tk.buy_tok(wb, pctr(3.5)); c.tx(1007, 3, vec![e], vec![]);
    let r = c.ev("presend_live_widedumper");
    assert!(r.len() == 2 && r[0]["would_arm"] == true && r[1]["whale"] == b58(&wb) && r[1]["pass"] == true && r[1]["first"] == false && r[1]["would_arm"] == false, "{r:?}");
    assert!(c.p.wd.as_ref().unwrap().wide.would == 1 && c.p.wd.as_ref().unwrap().wide.dup == 1);
}

/// LIVE mode: the window opens through the T2 path ("kind":"wide", its size, the ledger values), the sender's window has the wide size,
/// the fill and the realized say so; a live filter's skip is "kind":"wide" (withheld counted, no T2 count)
#[test]
fn dip41_live_mode_wide_window() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let wa = w(0xA1);
    let mut c = Ctx::led(&["--presend-live-wide-dumper-mode", "live", "--presend-live-wide-size-sol", "0.3"]);
    c.history(wa, 3, 0, 0x80, 100);
    let mut tk = c.wide(0x71, wa, 4.0, 10);
    let a = c.ev("presend_live_arm");
    assert_eq!(a.len(), 1, "{:?}", c.recs);
    let a = &a[0];
    assert!(a["kind"] == "wide" && a["spend"] == 300_000_000u64 && a["widedumper"] == serde_json::json!({"n": 3, "d": 3, "score": 1.0}) && a["trig"]["wallet"] == b58(&wa), "{a}");
    assert!(a.get("dumper").is_none());
    let id = a["w"].as_u64().unwrap();
    let sw = c.p.sh.wins.lock().unwrap().iter().find(|x| x.id == id).cloned().unwrap();
    assert!(sw.spend == 300_000_000 && !sw.rearm);
    assert!(c.lines.iter().any(|l| l.contains("[wide: 3/3 dumped, 0.300 SOL]")));
    assert!(c.p.st.armed == 0 && c.p.st.triggers == 0 && c.p.wd.as_ref().unwrap().wide.armed == 1, "not in T2's counts");
    assert!(c.ev("presend_live_parity").is_empty());
    let sg = c.att(id, tk.mint, 1011);
    let rz = c.fill_close(&mut tk, sg, 1012);
    let f = c.ev("presend_live_fill");
    assert!(f.len() == 1 && f[0]["kind"] == "wide" && f[0]["spend"] == 300_000_000u64 && f[0]["widedumper"]["n"] == 3, "{f:?}");
    assert!(c.ev("presend_live_disarm").iter().any(|r| r["w"] == id && r["kind"] == "wide"));
    let Cmd::Realized { wd, rearm, w: rw, .. } = rz else { panic!() };
    assert!(rw == id && !rearm && wd == Some(("wide", "widedumper", serde_json::json!({"n": 3, "d": 3, "score": 1.0}))), "{wd:?}");
    assert!(c.p.wd.as_ref().unwrap().wins.is_empty(), "let go at the realized");
    // a second token: a live filter (a T2 window of it armed first) withholds the wide window
    let wb = w(0xB1);
    c.history(wb, 3, 0, 0xA0, 1100);
    let mut t2 = Tk::new(0x75);
    c.launches.push(t2.launch.clone());
    let dev = t2.buy(CREATOR, S / 2); c.tx(1500, 1, vec![dev], vec![t2.create()]);
    let e = t2.buy(w(0x11), S / 10); c.tx(1501, 2, vec![e], vec![]);
    let e = t2.buy_tok(w(0xEE), pctr(8.0)); c.tx(1505, 3, vec![e], vec![]);
    let e = t2.buy_tok(wb, pctr(4.0)); c.tx(1506, 4, vec![e], vec![]);
    let s = c.ev("presend_live_skip");
    assert!(s.len() == 1 && s[0]["kind"] == "wide" && s[0]["why"] == "blocked_armed" && s[0]["widedumper"]["n"] == 3, "{s:?}");
    assert!(c.p.wd.as_ref().unwrap().wide.withheld == 1 && c.p.st.skips.is_empty());
    assert!(c.lines.iter().any(|l| l.contains("WIDE-DUMPER SKIP (blocked_armed)")));
}

/// the control file's "widedumper" flips the mode (a bad value keeps it; ignored without the ledger)
#[test]
fn dip41_control_file() {
    let ctl = tmp("ctl.json");
    std::fs::write(&ctl, r#"{"widedumper": "live"}"#).unwrap();
    let wa = w(0xA1);
    let mut c = Ctx::led(&["--presend-live-ledger-control", &ctl]);
    c.p.ledger_ctl_open();
    c.pump();
    assert!(c.p.wd.as_ref().unwrap().wide.live, "the file's start mode");
    c.history(wa, 3, 0, 0x80, 100);
    c.wide(0x71, wa, 4.0, 10);
    assert!(c.ev("presend_live_arm").iter().any(|r| r["kind"] == "wide"), "live from the file");
    std::fs::write(&ctl, r#"{"widedumper": "log"}"#).unwrap();
    c.p.ledger_ctl_check(true);
    c.pump();
    assert!(!c.p.wd.as_ref().unwrap().wide.live);
    assert!(c.ev("presend_live_ledger_mode").iter().any(|r| r["widedumper"] == "log" && r["was"]["widedumper"] == "live"), "{:?}", c.ev("presend_live_ledger_mode"));
    std::fs::write(&ctl, r#"{"widedumper": "maybe"}"#).unwrap();
    c.p.ledger_ctl_check(true);
    assert!(!c.p.wd.as_ref().unwrap().wide.live, "a bad value keeps it");
    assert_eq!(ctl_parse_wd(br#"{"x": 1}"#), Ok(None));
    assert!(ctl_parse_wd(br#"{"widedumper": 1}"#).is_err());
    let _ = std::fs::remove_file(&ctl);
}

/// OFF = dip39: the same tape gives the same records with the ledger off as on (log mode) once the tier's own records and the T2 arm's
/// "dumper" are taken out; nothing of it with it off
#[test]
fn dip41_off_and_log_change_nothing_else() {
    let run = |extra: &[&str]| {
        let mut c = Ctx::new(extra);
        c.history(w(0xA1), 3, 0, 0x80, 100);
        let mut tk = c.wide(0x71, w(0xA1), 4.0, 10);
        let e = tk.buy_tok(w(0xA2), pctr(7.0)); c.tx(1012, 3, vec![e], vec![]);
        let e = tk.sell_tok(w(0xA2), pctr(1.0)); c.tx(1013, 5, vec![e], vec![]);
        (c.recs, c.p.status())
    };
    let strip = |v: &Vec<serde_json::Value>| -> Vec<String> {
        v.iter().filter(|r| r["ev"] != "presend_live_widedumper").map(|r| { let mut r = r.clone(); if let Some(o) = r.as_object_mut() { o.remove("dumper"); o.remove("t"); } r.to_string() }).collect()
    };
    let (r0, s0) = run(&[]);
    let (r1, s1) = run(&LED);
    assert!(r0.iter().all(|r| r.get("dumper").is_none() && r["ev"] != "presend_live_widedumper") && !s0.contains("WIDE DUMPER"));
    assert!(r1.iter().any(|r| r["ev"] == "presend_live_widedumper") && r1.iter().any(|r| r.get("dumper").is_some()) && s1.contains("WIDE DUMPER"));
    assert_eq!(strip(&r0), strip(&r1));
}

/// the seeder's file (ops/prod/dumper_seed.py; built locally at /home/it/sniper-data/dumper/dumper_state_seed.json) loads as the engine's
/// state with every wallet it wrote and the same pass count (skipped when the file is not on this machine)
#[test]
fn dip41_seed_file_loads() {
    let p = "/home/it/sniper-data/dumper/dumper_state_seed.json";
    let Ok(b) = std::fs::read(p) else { eprintln!("dip41_seed_file_loads: {p} not here: skipped"); return };
    let j: serde_json::Value = serde_json::from_slice(&b).unwrap();
    let mut l = Ledger::default();
    let n = l.state_load(&b).unwrap();
    assert_eq!(n as u64, j["built"]["wallets"].as_u64().unwrap(), "every wallet the seeder wrote");
    let pass = l.hist.values().filter(|h| { let v = h.v(); super::psdl::pass(3, 0.8, v.n, v.d) }).count();
    if j["built"]["spec"] == "3:0.8" { assert_eq!(pass as u64, j["built"]["pass"].as_u64().unwrap(), "the same 3:0.8 pass count"); }
    let pq = l.hist.values().filter(|h| { let v = h.v(); super::psdl::pass(5, 0.3, v.n, v.q) }).count();
    if j["built"]["spec_qf2"] == "5:0.3" { assert_eq!(pq as u64, j["built"]["pass_qf2"].as_u64().unwrap(), "the same QF2 5:0.3 pass count"); }
    assert!(l.hist.values().all(|h| !h.b.is_empty() && h.b.len() <= DL_KEEP));
    eprintln!("dip41_seed_file_loads: {n} wallets, {pass} pass 3:0.8");
}

// ---- QF2 (DL7-style; --presend-live-qf2 N:SCORE[:WIN]) -------------------------------------------------------------------------------

const QF: [&str; 4] = ["--presend-live-dumper-ledger", "on", "--presend-live-qf2", "5:0.3"];
fn with_qf(extra: &[&str]) -> Vec<String> { QF.iter().chain(extra.iter()).map(|s| s.to_string()).collect() }
fn qf_ctx(extra: &[&str]) -> Ctx { let a = with_qf(extra); Ctx::new(&a.iter().map(|s| s.as_str()).collect::<Vec<_>>()) }

#[test]
fn dip41_qf2_flags() {
    let c = cfg(&with_qf(&[]).iter().map(|s| s.as_str()).collect::<Vec<_>>()).unwrap().unwrap();
    assert!(c.qf == Some(QfCfg { n: 5, score: 0.3, win: 10 }) && c.qf_filt == QfFilt::default() && !c.qf_live);
    assert_eq!(c.json()["widedumper"]["qf2"], serde_json::json!({"n": 5, "score": 0.3, "win": 10, "filters": "2:8:36:70:300", "mode": "log"}));
    let c = cfg(&with_qf(&["--presend-live-qf2-filters", "1:9:30:80:200", "--presend-live-qf2-mode", "live"]).iter().map(|s| s.as_str()).collect::<Vec<_>>()).unwrap().unwrap();
    assert!(c.qf_live && c.qf_filt == QfFilt { sol: (1.0, 9.0), curve: (30.0, 80.0), age_max: 200, age_min: 0 });
    for (a, want) in [(&["--presend-live-qf2", "5:0.3"][..], "needs --presend-live-dumper-ledger on"),
                      (&["--presend-live-dumper-ledger", "on", "--presend-live-qf2-filters", "2:8:36:70:300"][..], "needs --presend-live-qf2"),
                      (&["--presend-live-dumper-ledger", "on", "--presend-live-qf2-mode", "live"][..], "needs --presend-live-qf2"),
                      (&["--presend-live-dumper-ledger", "on", "--presend-live-qf2", "5:0.3", "--presend-live-qf2-mode", "on"][..], "log | live")] {
        let e = format!("{:#}", cfg(a).unwrap_err());
        assert!(e.contains(want), "{a:?}: {e}");
    }
    assert!(crate::check_flags(&args(&["--presend-live-dumper-ledger", "on", "--presend-live-qf2", "5:0.3:10", "--presend-live-qf2-filters", "2:8:36:70:300",
        "--presend-live-qf2-mode", "log"])).is_ok());
}

/// LOG: a 3..6% whale that sells fast (q) but never dumps (d): QF2 would arm, WIDE-DUMPER not (both records); the filters (a small buy: no);
/// a T2 whale: only annotated (its record "t2", never would-arm; "qf2" on the T2 arm); nothing sent
#[test]
fn dip41_qf2_log_and_t2_annotation() {
    let wa = w(0xA1);
    let mut c = qf_ctx(&[]);
    c.history_q(wa, 2, 4, 0x80, 100);                  // n 6, d 0, q 2 = 0.33
    c.qf_token(0x71, wa, 5.0, 10);
    let q = c.ev("presend_live_qf2");
    assert_eq!(q.len(), 1, "{q:?}");
    let r = &q[0];
    assert!(r["n"] == 6 && r["q"] == 2 && r["pass"] == true && r["would_arm"] == true && r["filt"] == serde_json::json!({"sol": true, "curve": true, "age": true})
        && r.get("t2").is_none() && r["mode"] == "log", "{r} sol {} vsol {}", r["sol"], r["vsol"]);
    let wd = c.ev("presend_live_widedumper");
    assert!(wd.len() == 1 && wd[0]["pass"] == false && wd[0]["d"] == 0, "{wd:?}");
    assert!(c.lines.iter().any(|l| l.contains("QF2 WOULD ARM (log)") && l.contains("2/6 of its >= 3% buys sold fast")), "{:?}", c.lines);
    assert!(c.ev("presend_live_arm").is_empty() && c.p.sh.wins.lock().unwrap().is_empty());
    // the filters: the same whale's 4% on a small curve (~1.4 SOL in, ~32 vSOL): recorded, not would-arm
    c.wide(0x72, wa, 4.0, 10);
    let q = c.ev("presend_live_qf2");
    assert!(q.len() == 2 && q[1]["pass"] == true && q[1]["would_arm"] == false && q[1]["filt"]["sol"] == false && q[1]["filt"]["curve"] == false, "{:?}", q[1]);
    // a T2 whale (8%): annotated only
    c.qf_token(0x73, wa, 8.0, 12);
    let q = c.ev("presend_live_qf2");
    assert!(q.len() == 3 && q[2]["t2"] == true && q[2]["pass"] == true && q[2]["would_arm"] == false, "{:?}", q[2]);
    let a = c.ev("presend_live_arm");
    assert!(a.len() == 1 && a[0].get("kind").is_none() && a[0]["qf2"] == serde_json::json!({"n": 6, "q": 2, "score": 0.3333, "pass": true, "filt": true}), "{a:?}");
    let qv = c.p.wd.as_ref().unwrap().qf.as_ref().unwrap();
    assert!(qv.would == 1 && qv.t2 == 1 && qv.t2_pass == 1 && qv.armed == 0);
    assert!(c.p.status().contains(" | QF2 LOG 5:0.3: 1 pass, would-arm 1, armed 0, withheld 0, T2 flagged 1/1"), "{}", c.p.status());
    let end = c.p.finish(1100, None);
    assert!(end["widedumper"]["qf2"]["would"] == 1 && end["widedumper"]["qf2"]["t2"] == 1, "{}", end["widedumper"]);
}

/// LIVE QF2: a "kind":"qf2" window through the T2 path, its fill and realized say so; both variants live on one trigger: one window (the
/// second is skipped blocked_armed with its kind)
#[test]
fn dip41_qf2_live() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let wa = w(0xA1);
    let mut c = qf_ctx(&["--presend-live-qf2-mode", "live"]);
    c.history_q(wa, 2, 4, 0x80, 100);
    let mut tk = c.qf_token(0x71, wa, 5.0, 10);
    let a = c.ev("presend_live_arm");
    assert!(a.len() == 1 && a[0]["kind"] == "qf2" && a[0]["qf2"] == serde_json::json!({"n": 6, "q": 2, "score": 0.3333}) && a[0].get("widedumper").is_none(), "{a:?}");
    let id = a[0]["w"].as_u64().unwrap();
    let sg = c.att(id, tk.mint, 1011);
    let rz = c.fill_close(&mut tk, sg, 1012);
    assert!(c.ev("presend_live_fill").iter().any(|f| f["kind"] == "qf2" && f["qf2"]["q"] == 2));
    let Cmd::Realized { wd, .. } = rz else { panic!() };
    assert_eq!(wd, Some(("qf2", "qf2", serde_json::json!({"n": 6, "q": 2, "score": 0.3333}))));
    // both live: a whale that dumps fast (d 5, q 5 of 5)
    let wb = w(0xB1);
    let mut c = qf_ctx(&["--presend-live-qf2-mode", "live", "--presend-live-wide-dumper-mode", "live"]);
    c.history(wb, 5, 0, 0x80, 100);
    c.qf_token(0x71, wb, 5.0, 10);
    let a = c.ev("presend_live_arm");
    assert!(a.len() == 1 && a[0]["kind"] == "wide", "{a:?}");
    let sk = c.ev("presend_live_skip");
    assert!(sk.len() == 1 && sk[0]["kind"] == "qf2" && sk[0]["why"] == "blocked_armed", "{sk:?}");
    let d = c.p.wd.as_ref().unwrap();
    assert!(d.wide.armed == 1 && d.qf.as_ref().unwrap().withheld == 1);
}

/// the control file's "qf2" flips QF2 alone
#[test]
fn dip41_qf2_control_file() {
    let ctl = tmp("ctl-qf.json");
    std::fs::write(&ctl, r#"{"qf2": "live"}"#).unwrap();
    let mut c = qf_ctx(&["--presend-live-ledger-control", &ctl]);
    c.p.ledger_ctl_open();
    c.pump();
    let d = c.p.wd.as_ref().unwrap();
    assert!(d.qf.as_ref().unwrap().live && !d.wide.live);
    assert!(c.ev("presend_live_ledger_mode").iter().any(|r| r["qf2"] == "live" && r["was"]["qf2"] == "log"));
    let _ = std::fs::remove_file(&ctl);
    // without QF2: ignored, said so
    let ctl = tmp("ctl-qf2.json");
    std::fs::write(&ctl, r#"{"qf2": "live", "widedumper": "live"}"#).unwrap();
    let mut c = Ctx::led(&["--presend-live-ledger-control", &ctl]);
    c.p.ledger_ctl_open();
    c.pump();
    assert!(c.p.wd.as_ref().unwrap().wide.live && c.ev("presend_live_ledger_mode").iter().any(|r| r["qf2_ignored"].is_string()));
    let _ = std::fs::remove_file(&ctl);
}

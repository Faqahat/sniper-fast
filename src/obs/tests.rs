//! OBSERVATORY unit tests (dip24): the book, every module on hand-made tokens (pump's constant product), the writer's rotation, the
//! tailer, the bounded channel (drops, never blocks), the hub end to end.
use super::*;
use crate::dip::{CreateEvent, TradeEvent};

const S: u64 = 1_000_000_000;
const MS: u64 = 1_000_000;
const CREATOR: Pk = [0xC1; 32];
const US: Pk = [0x5A; 32];

/// a token on pump's curve
struct Tk { mint: Pk, v: u64, t: u64 }
impl Tk {
    fn new(k: u8) -> Tk { Tk { mint: [k; 32], v: 30 * S, t: 1_073_000_000_000_000 } }
    fn buy(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v + sol) as u128) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn buy_tok(&mut self, user: Pk, tok: u64) -> TradeEvent {
        let sol = ((self.v as u128 * tok as u128) / (self.t - tok) as u128) as u64 + 1;
        self.buy(user, sol)
    }
    fn sell_tok(&mut self, user: Pk, tok: u64) -> TradeEvent {
        let sol = (self.v as u128 * tok as u128 / (self.t + tok) as u128) as u64;
        self.v -= sol; self.t += tok;
        TradeEvent { mint: self.mint, sol, tok, buy: false, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn sell_sol(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v - sol) as u128) as u64;
        self.v -= sol; self.t += q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: false, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn create(&self) -> CreateEvent { CreateEvent { mint: self.mint, bonding_curve: [0; 32], user: CREATOR, creator: CREATOR } }
}

fn tmpdir(name: &str) -> PathBuf {
    let d = std::env::temp_dir().join(format!("obs_test_{name}_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&d);
    std::fs::create_dir_all(&d).unwrap();
    d
}

fn cfg_all(dir: &Path) -> Cfg {
    Cfg { rearm: true, hold: true, migr: true, blink: true, backrun: true, select: true, race: true, inslot: true, feed_names: vec!["kaldera".into(), "kaldera-tx".into()], watch: vec![[0x77; 32]], watch_file: None, watch_names: Default::default(), out: dir.join("run.obs.jsonl"),
          tail: Some(dir.join("run.jsonl")), user: US, rate_cap: 40, k: 8, drop: 0.12, cohort: Default::default(), fbots: Default::default(), quiet_book: None, quiet_fol: 2.24,
          chan: 0, rotate_ns: 0, rotate_bytes: 0 }
}

/// one tx into a hub (the feeder's message, built as the engine's)
struct Feed { slot: u64, idx: u64 }
impl Feed {
    fn tx(&mut self, h: &mut Hub, slot: u64, t: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>) {
        if slot != self.slot { self.slot = slot; self.idx = 0; }
        self.idx += 1;
        let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&self.idx.to_be_bytes());
        let x = Arc::new(ExecInfo { index: self.idx, fee: 5_000, ok: true, trades, creates, mayhem: false });
        h.on_msg(Msg::Tx(TxIn { slot, idx: self.idx, t_rx: t, sig, exec: x, cu_price: Some(1_000_123), cu_limit: Some(120_000), v1: false, payer: [1; 32], xfers: None }));
    }
}
fn hub(c: Cfg) -> Hub { let w: Arc<FxHashSet<Pk>> = Arc::new(c.watch.iter().copied().collect()); Hub::new(c, Arc::new(Ctr::default()), w) }
fn recs_of(p: &Path) -> Vec<Value> { std::fs::read_to_string(p).unwrap_or_default().lines().filter_map(|l| serde_json::from_str(l).ok()).collect() }

#[test]
fn obs_paths_and_watch_list() {
    assert_eq!(obs_path_for("/root/prod/runs/dip_ams_r35.jsonl"), PathBuf::from("/root/prod/runs/dip_ams_r35.obs.jsonl"));
    assert_eq!(obs_path_for("x.log"), PathBuf::from("x.obs.jsonl"));
    let d = tmpdir("watch");
    let f = d.join("w.txt");
    std::fs::write(&f, "# a comment\nE2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb   # e2x1: near-graduation\n\n haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq\n").unwrap();
    let (v, n) = load_watch(f.to_str().unwrap()).unwrap();
    assert_eq!(v.len(), 2);
    assert_eq!(n.get(&v[0]).map(|s| s.as_str()), Some("e2x1: near-graduation"));
    std::fs::write(&f, "notawallet\n").unwrap();
    assert!(load_watch(f.to_str().unwrap()).is_err());
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn book_balances_holders_complete() {
    let mut b = Book::new(US);
    let mut tk = Tk::new(1);
    b.create(tk.mint, 100, 1, CREATOR, CREATOR, false);
    let w = [0x11u8; 32];
    let tr = |e: &TradeEvent, s: u64, t: u64| Tr { mint: e.mint, s, i: 1, j: 0, t, sig: [0; 64], user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok, fbps: 95, cbps: 30 };
    let e = tk.buy(CREATOR, S); let c = b.apply(&tr(&e, 100, 1), false);
    assert!(c.hist && c.normal && c.fl & book::F_CREATOR != 0);
    let e = tk.buy_tok(w, 70_000_000_000_000); let c = b.apply(&tr(&e, 101, 2), false);
    assert_eq!((c.nbig_before, c.nbig_after), (0, 1));
    assert!(c.fl & book::F_BIG != 0);
    assert_eq!(b.get(&tk.mint).unwrap().holders().len(), 1);
    let e = tk.sell_tok(w, 20_000_000_000_000); let c = b.apply(&tr(&e, 102, 3), false);
    assert_eq!(c.nbig_after, 0, "below 6% now");
    // the curve to completion: vtok = 279.9e12 after a buy
    let need = tk.t - book::COMPLETE_VTOK;
    let e = tk.buy_tok([0x22; 32], need); let mut e2 = e.clone(); e2.vtok = book::COMPLETE_VTOK;
    let c = b.apply(&tr(&e2, 103, 4), false);
    assert!(c.completes && b.get(&tk.mint).unwrap().complete.is_some());
    // a token never created: not hist
    let mut t2 = Tk::new(2);
    let e = t2.buy(w, S); let c = b.apply(&tr(&e, 200, 5), false);
    assert!(!c.hist && !c.normal);
}

#[test]
fn position_math() {
    // our buy on a fresh curve, then one follower buy: the value rises; a big sell: it falls; naive = every trade applied
    let mut p = book::Pos::open(30 * S, 1_073_000_000_000_000, 0.5e9, 0.0125, false).unwrap();
    let v0 = p.val();
    assert!(v0 < 1.0 && v0 > 0.97, "round trip at once costs the fees and impact: {v0}");
    let x = book::TapeTr { s: 1, i: 1, j: 0, t: 1, user: [9; 32], buy: true, sol: 2 * S, tok: 1, vsol: 0, vtok: 0, fr: 0.0125, sig: [0; 64], fl: 0, bal_after: 0 };
    p.feed(&x);
    assert!(p.val() > 1.0, "a 2 SOL buy after ours lifts the value: {}", p.val());
    assert!(book::Pos::open(100 * S, 1, 1e9, 0.01, false).is_none(), "untradeable at >= 100 SOL");
}

/// R0 end to end: a young token, a whale dump with another >= 6% holder left, the window at dump + 3, a -12% crossing, the paper fills,
/// the exits, the tape; then the live budget saturated: refused tries
#[test]
fn rearm_window_fill_exits_and_budget() {
    let d = tmpdir("rearm");
    let mut c = cfg_all(&d);
    c.hold = false; c.migr = false; c.blink = false; c.backrun = false; c.watch.clear();
    let mut h = hub(c.clone());
    let mut f = Feed { slot: 0, idx: 0 };
    let mut tk = Tk::new(3);
    let (whale, holder, x1) = ([0xA1u8; 32], [0xA2u8; 32], [0xA3u8; 32]);
    let t0 = 1_800_000_000 * S;
    let at = |s: u64| t0 + (s - 1000) * 213 * MS;
    let dev = tk.buy(CREATOR, S / 2);
    f.tx(&mut h, 1000, at(1000), vec![dev], vec![tk.create()]);
    let e = tk.buy_tok(whale, 100_000_000_000_000); f.tx(&mut h, 1002, at(1002), vec![e], vec![]);
    let e = tk.buy_tok(holder, 80_000_000_000_000); f.tx(&mut h, 1003, at(1003), vec![e], vec![]);
    // the whale dumps everything at slot 1010 (age 10 slots): a candidate
    let e = tk.sell_tok(whale, 100_000_000_000_000); f.tx(&mut h, 1010, at(1010), vec![e], vec![]);
    assert_eq!(h.rearm.as_ref().unwrap().st.cands, 1);
    // other tokens' txs move the clock: slot 1013 = dump + 3: the holders check -> a window
    let mut other = Tk::new(9);
    let o = other.buy([0x55; 32], S / 10); f.tx(&mut h, 1011, at(1011), vec![o], vec![]);
    let o = other.buy([0x56; 32], S / 10); f.tx(&mut h, 1013, at(1013), vec![o], vec![]);
    assert_eq!(h.rearm.as_ref().unwrap().st.windows, 1, "{:?}", h.rearm.as_ref().unwrap().status());
    // trades in the window: two small buys, then a 3 SOL sell by x1 (bought before) = a crossing of -12% vs the price 50 ms before
    let e = tk.buy(x1, 3 * S); f.tx(&mut h, 1013, at(1013) + 5 * MS, vec![e], vec![]);
    let e = tk.buy([0xB1; 32], S / 5); f.tx(&mut h, 1014, at(1014), vec![e], vec![]);
    let e = tk.sell_sol(x1, 3 * S - 1); f.tx(&mut h, 1015, at(1015), vec![e], vec![]);
    // followers right after (a buyer in the next slot), then quiet trades for 3 s on another token to move the clock
    let e = tk.buy([0xB2; 32], S); f.tx(&mut h, 1016, at(1016), vec![e], vec![]);
    for s in 1017..1050 { let o = other.buy([0x57; 32], S / 100); f.tx(&mut h, s, at(s), vec![o], vec![]); }
    h.housekeeping(true);
    h.emit(); h.out.flush();
    let r = recs_of(&c.out);
    let w = r.iter().find(|x| x["ev"] == "rearm_window").expect("the window record");
    assert_eq!(w["holders"].as_array().unwrap().len(), 1);
    assert_eq!(w["holders"][0]["w"], book::b58(&holder));
    assert_eq!(w["arm"]["slot"], 1013);
    assert_eq!(w["en_slot"], 1010 + 3 + 20);
    let fa = &w["rows"]["a"]["fill"];
    assert!(fa.is_object(), "row a fills: {}", w["rows"]);
    assert!(fa["x"]["drop_pct"].as_f64().unwrap() >= 12.0, "{}", fa["x"]);
    assert!(fa["px"]["0.65"]["t200"].is_number() && fa["px_naive"]["1.00"]["s2"].is_number());
    assert_eq!(fa["followers"]["s1"][0], 1, "one distinct buyer in the next slot");
    assert!(w["tries"]["n"].as_u64().unwrap() > 0 && w["tries"]["refused"] == 0);
    let tape = r.iter().find(|x| x["ev"] == "rearm_tape").expect("the tape");
    assert!(tape["n"].as_u64().unwrap() >= 4);
    assert!(r.iter().any(|x| x["ev"] == "rearm_cand" && x["verdict"] == "window"));
    // the same with the live budget full in every second: every try refused
    let d2 = tmpdir("rearm2");
    let mut c2 = c.clone(); c2.out = d2.join("o.jsonl");
    let mut h2 = hub(c2.clone());
    for s in (t0 / S)..(t0 / S + 60) { for _ in 0..40 { h2.live.on(&LiveEv::Attempt { t: s * S + 1, path: "helius-ps".into() }, 0); } }
    let mut f = Feed { slot: 0, idx: 0 };
    let mut tk = Tk::new(3);
    let dev = tk.buy(CREATOR, S / 2); f.tx(&mut h2, 1000, at(1000), vec![dev], vec![tk.create()]);
    let e = tk.buy_tok(whale, 100_000_000_000_000); f.tx(&mut h2, 1002, at(1002), vec![e], vec![]);
    let e = tk.buy_tok(holder, 80_000_000_000_000); f.tx(&mut h2, 1003, at(1003), vec![e], vec![]);
    let e = tk.sell_tok(whale, 100_000_000_000_000); f.tx(&mut h2, 1010, at(1010), vec![e], vec![]);
    let mut other = Tk::new(9);
    for s in 1011..1050 { let o = other.buy([0x57; 32], S / 100); f.tx(&mut h2, s, at(s), vec![o], vec![]); }
    h2.housekeeping(true); h2.emit(); h2.out.flush();
    let r = recs_of(&c2.out);
    let w = r.iter().find(|x| x["ev"] == "rearm_window").unwrap();
    assert_eq!(w["tries"]["n"], w["tries"]["refused"], "the live attempts used the whole budget: {}", w["tries"]);
    assert_eq!(w["end"]["why"], "quiet", "no other trade on the token in 6 slots: the QUIET stop");
    let _ = std::fs::remove_dir_all(&d); let _ = std::fs::remove_dir_all(&d2);
}

#[test]
fn rearm_no_holder_and_age_gate() {
    let d = tmpdir("rearm_nh");
    let mut c = cfg_all(&d); c.hold = false; c.migr = false; c.blink = false; c.backrun = false; c.watch.clear();
    let mut h = hub(c.clone());
    let mut f = Feed { slot: 0, idx: 0 };
    let mut tk = Tk::new(4);
    let whale = [0xA1u8; 32];
    let dev = tk.buy(CREATOR, S / 2); f.tx(&mut h, 1000, 1, vec![dev], vec![tk.create()]);
    let e = tk.buy_tok(whale, 100_000_000_000_000); f.tx(&mut h, 1001, 2, vec![e], vec![]);
    let e = tk.sell_tok(whale, 100_000_000_000_000); f.tx(&mut h, 1002, 3, vec![e], vec![]);
    let mut other = Tk::new(9);
    for s in 1003..1010 { let o = other.buy([0x57; 32], S / 100); f.tx(&mut h, s, s, vec![o], vec![]); }
    assert_eq!((h.rearm.as_ref().unwrap().st.cands, h.rearm.as_ref().unwrap().st.no_holder, h.rearm.as_ref().unwrap().st.windows), (1, 1, 0));
    // a dump on a token older than 30 s (141 slots): no candidate
    let e = tk.buy_tok(whale, 100_000_000_000_000); f.tx(&mut h, 1200, 4, vec![e], vec![]);
    let e = tk.sell_tok(whale, 100_000_000_000_000); f.tx(&mut h, 1201, 5, vec![e], vec![]);
    assert_eq!(h.rearm.as_ref().unwrap().st.cands, 1);
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn exits_policies_on_a_hand_tape() {
    // our buy after m; trades: +100 ms a 1 SOL buy, +250 ms a 2 SOL sell; slot + 2 at +450 ms
    let m = book::TapeTr { s: 10, i: 1, j: 0, t: 1_000 * MS, user: [1; 32], buy: false, sol: S, tok: 1, vsol: 30 * S, vtok: 1_073_000_000_000_000, fr: 0.0125, sig: [0; 64], fl: 0, bal_after: 0 };
    let mk = |dt: u64, s: u64, buy: bool, sol: u64| book::TapeTr { s, i: 1, j: 0, t: (1_000 + dt) * MS, user: [2; 32], buy, sol, tok: if buy { 1 } else { 30_000_000_000_000 }, vsol: 0, vtok: 0, fr: 0.0125,
        sig: [7; 64], fl: 0, bal_after: 0 };
    let tape = [mk(100, 10, true, S), mk(250, 11, false, 2 * S), mk(450, 12, true, S / 10)];
    let after: Vec<&book::TapeTr> = tape.iter().collect();
    let (v, why, _) = rearm::exits_for_test(&m, &after, 0.5e9, 0.0125, 1_000 * MS, 10, false);
    // t200: the state after the +100 ms buy only (decided at +200: the first trade at / after it is the +250 sell)
    let mut p = book::Pos::open(m.vsol, m.vtok, 0.5e9, 0.0125, false).unwrap(); p.feed(&tape[0]);
    assert!((v[0] - (p.pnl() / 1e6 * 100.0).round() / 100.0).abs() < 1e-9, "t200 {v:?}");
    assert_eq!(why[0], "time");
    // s2: the first trade of slot >= 12 is the +450 one: the state after the sell
    p.feed(&tape[1]);
    assert!((v[2] - (p.pnl() / 1e6 * 100.0).round() / 100.0).abs() < 1e-9, "s2 {v:?}");
    assert_eq!(why[2], "slot");
}

#[test]
fn hold_tape_from_live_records() {
    let d = tmpdir("hold");
    let mut c = cfg_all(&d); c.rearm = false; c.migr = false; c.blink = false; c.backrun = false; c.watch.clear();
    let mut h = hub(c.clone());
    let mut f = Feed { slot: 0, idx: 0 };
    let mut tk = Tk::new(5);
    let (w1, big) = ([0xD1u8; 32], [0xD2u8; 32]);
    let t0 = 1_800_000_000 * S;
    let dev = tk.buy(CREATOR, S / 2); f.tx(&mut h, 2000, t0, vec![dev], vec![tk.create()]);
    let e = tk.buy_tok(big, 90_000_000_000_000); f.tx(&mut h, 2001, t0 + 200 * MS, vec![e], vec![]);
    let e = tk.buy(w1, 2 * S); f.tx(&mut h, 2002, t0 + 400 * MS, vec![e], vec![]);
    // the dump (w1 sells), then OUR fill (buy) 30 ms later
    let e = tk.sell_sol(w1, 2 * S - 10); f.tx(&mut h, 2003, t0 + 600 * MS, vec![e], vec![]);
    let ours = tk.buy(US, S / 2);
    f.tx(&mut h, 2003, t0 + 630 * MS, vec![ours.clone()], vec![]);
    let fill_sig = { let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&2003u64.to_be_bytes()); sig[8..16].copy_from_slice(&2u64.to_be_bytes()); sig };
    // the live records arrive (as the tailer reads them)
    let fill = LiveEv::Fill { w: 7, mint: tk.mint, sig: bs58::encode(&fill_sig).into_string(), slot: 2003, idx: 2, t: t0 + 630 * MS, tokens: ours.tok, sol_in: ours.sol,
        rec: json!({"tokens": ours.tok, "sol_in": ours.sol, "path": "helius-ps"}) };
    h.hold.as_mut().unwrap().on_live(&fill, &h.book, &mut h.recs);
    // the big holder sells 1.2 SOL 100 ms later (seen before our decision at +200 ms); we sell at +200
    let e = tk.sell_sol(big, 1_200_000_000); f.tx(&mut h, 2004, t0 + 730 * MS, vec![e], vec![]);
    h.hold.as_mut().unwrap().on_live(&LiveEv::Exit { mint: tk.mint, why: "time-ms".into(), slot: 2004, t: t0 + 830 * MS, value: None, round: 1 }, &h.book, &mut h.recs);
    h.hold.as_mut().unwrap().on_live(&LiveEv::SellLand { mint: tk.mint, sig: "S".into(), slot: 2005, idx: 9, t: t0 + 950 * MS, sol: 480_000_000 }, &h.book, &mut h.recs);
    h.hold.as_mut().unwrap().on_live(&LiveEv::Close { mint: tk.mint, rec: json!({"curve_pnl": -20_000_000, "exit_why": "time-ms"}) }, &h.book, &mut h.recs);
    let mut other = Tk::new(9);
    for k in 0..30 { let o = other.buy([0x57; 32], S / 100); f.tx(&mut h, 2006 + k, t0 + (1000 + 200 * k) * MS, vec![o], vec![]); }
    h.housekeeping(true); h.emit(); h.out.flush();
    let r = recs_of(&c.out);
    let t = r.iter().find(|x| x["ev"] == "hold_tape").expect("hold_tape");
    assert_eq!(t["fill"]["in_tape"], true);
    assert_eq!(t["dump"]["w"], book::short(&w1), "{}", t["dump"]);
    let s1 = &t["first_1sol_sell"];
    assert_eq!(s1["w"], book::short(&big));
    assert_eq!(s1["big"], true);
    assert_eq!(s1["seen_before_decision"], true);
    assert!((s1["ms_before_decision"].as_f64().unwrap() - 100.0).abs() < 1e-6);
    assert!(t["trades"].as_array().unwrap().iter().any(|x| x["fl"].as_str().unwrap().contains('O')), "our fill flagged");
    assert_eq!(t["sells"].as_array().unwrap().len(), 1);
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn watch_migration_blink_backrun() {
    let d = tmpdir("mods");
    let mut c = cfg_all(&d); c.rearm = false; c.hold = false;
    let watched = [0x77u8; 32];
    let mut h = hub(c.clone());
    let mut f = Feed { slot: 0, idx: 0 };
    let t0 = 1_800_000_000 * S;
    let mut tk = Tk::new(6);
    let dev = tk.buy(CREATOR, S); f.tx(&mut h, 3000, t0, vec![dev], vec![tk.create()]);
    // a bundler in the create slot sells 0.5 SOL in slot 3001: a BLINK trigger (class bundler, drop >= 3%)
    let e = tk.buy([0x31; 32], S); f.tx(&mut h, 3000, t0 + MS, vec![e], vec![]);
    let e = tk.sell_sol([0x31; 32], 900_000_000); f.tx(&mut h, 3001, t0 + 213 * MS, vec![e], vec![]);
    // a watched wallet buys
    let e = tk.buy(watched, S / 3); f.tx(&mut h, 3002, t0 + 426 * MS, vec![e], vec![]);
    // a >= 1 SOL sell, a backrunner in the same slot, more slots after
    let e = tk.buy([0x41; 32], 3 * S); f.tx(&mut h, 3003, t0 + 600 * MS, vec![e], vec![]);
    let e = tk.sell_sol([0x41; 32], 2 * S); f.tx(&mut h, 3004, t0 + 800 * MS, vec![e], vec![]);
    let e = tk.buy([0x42; 32], S / 2); f.tx(&mut h, 3004, t0 + 801 * MS, vec![e], vec![]);
    // the curve to 100 / 105 SOL and completion
    while tk.v < 101 * S { let e = tk.buy([0x43; 32], 10 * S); let s = 3010 + (tk.v / S); f.tx(&mut h, s, t0 + s * MS, vec![e], vec![]); }
    let e = tk.buy([0x44; 32], 5 * S); f.tx(&mut h, 3200, t0 + 3_200 * MS, vec![e], vec![]);
    let need = tk.t - book::COMPLETE_VTOK;
    let mut e = tk.buy_tok([0x45; 32], need); e.vtok = book::COMPLETE_VTOK; f.tx(&mut h, 3201, t0 + 3_300 * MS, vec![e], vec![]);
    // the migration tx (PumpSwap + the mint), then a pool tx
    h.on_msg(Msg::Raw(Box::new(RawIn { slot: 3205, t_rx: t0 + 4_000 * MS, sig: [3; 64], keys: vec![[9; 32], *crate::venues::PUMPSWAP, tk.mint], payer: [9; 32] })));
    h.on_msg(Msg::Raw(Box::new(RawIn { slot: 3206, t_rx: t0 + 4_200 * MS, sig: [4; 64], keys: vec![[8; 32], *crate::venues::PUMPSWAP, tk.mint], payer: [8; 32] })));
    // a watched wallet's failed tx
    h.on_msg(Msg::Fail(Box::new(FailIn { slot: 3207, t_rx: t0 + 4_300 * MS, sig: [5; 64], payer: watched, cu_price: Some(7_000_777), cu_limit: Some(90_000), v1: false,
        xfers: vec![(crate::tx::pk("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"), 1_000_000)], pump_ix: Some((0x1234, Some(tk.mint))) })));
    let mut other = Tk::new(9);
    for k in 0..60u64 { let o = other.buy([0x57; 32], S / 100); f.tx(&mut h, 3210 + k, t0 + (4_400 + 300 * k) * MS, vec![o], vec![]); }
    h.housekeeping(true); h.emit();
    let _ = h.end();
    let r = recs_of(&c.out);
    let ev = |k: &str| r.iter().filter(|x| x["ev"] == k).collect::<Vec<_>>();
    let w = ev("watch_trade");
    assert_eq!(w.len(), 1);
    assert_eq!((w[0]["cu_price"].as_u64(), w[0]["cu_mod1000"].as_u64()), (Some(1_000_123), Some(123)));
    let wf = ev("watch_fail");
    assert_eq!(wf.len(), 1);
    assert_eq!(wf[0]["tips"][0]["whose"], "jito");
    assert_eq!(wf[0]["mint_guess"], book::b58(&tk.mint));
    let b = ev("blink_trigger");
    assert!(!b.is_empty() && b[0]["cls"] == 2 && b[0]["features"].as_array().unwrap().len() == 22, "{b:?}");
    assert_eq!(ev("mig_v100").len(), 1);
    assert_eq!(ev("mig_v105").len(), 1);
    assert_eq!(ev("mig_complete").len(), 1);
    assert_eq!(ev("mig_migrate").len(), 1);
    assert_eq!(ev("mig_pool_tx").len(), 1);
    assert!(ev("mig_follow").len() >= 2);
    let br = ev("backrun_sell");
    let x = br.iter().find(|x| x["sol"].as_u64() == Some(2 * S)).expect("the 2 SOL sell");
    assert_eq!(x["first"]["di"], 1, "the backrunner right behind the sell in its slot");
    assert!(x["v_br"][0].is_number() && x["v_sell"][4].is_number(), "{x}");
    assert!(r.iter().any(|x| x["ev"] == "obs_end"));
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn writer_rotates_and_never_deletes() {
    let d = tmpdir("rot");
    let p = d.join("a.obs.jsonl");
    let mut o = Out::open(p.clone(), ROTATE_NS, 2_000);
    for k in 0..200 { o.write(M_CORE, &json!({"ev": "x", "k": k, "pad": "0123456789012345678901234567890123456789"})); if k % 10 == 0 { o.flush(); let _ = o.maybe(); } }
    o.flush();
    let n = (1..100).filter(|k| PathBuf::from(format!("{}.{k}", p.display())).exists()).count();
    assert!(n >= 3, "parts {n}");
    let mut total = 0;
    for k in 1..=n { total += std::fs::read_to_string(format!("{}.{k}", p.display())).unwrap().lines().count(); }
    total += std::fs::read_to_string(&p).unwrap().lines().count();
    assert_eq!(total, 200, "every record in some part");
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn tailer_reads_complete_lines_only() {
    let d = tmpdir("tail");
    let p = d.join("run.jsonl");
    std::fs::write(&p, "{\"ev\":\"run_start\"}\n").unwrap();
    let mut t = Tailer::new(p.clone());
    use std::io::Write as _;
    let mut f = std::fs::OpenOptions::new().append(true).open(&p).unwrap();
    write!(f, "{{\"ev\":\"presend_attempt\",\"t\":1000000000123,\"path\":\"helius-ps\"}}\n{{\"ev\":\"presend_live_fill\",\"w\":3,\"mint\":\"{}\",\"sig\":\"x\",\"slot\":5,\"idx\":2,\"t\":9,\"tok",
        book::b58(&[4u8; 32])).unwrap();
    f.flush().unwrap();
    let mut out = Vec::new();
    t.poll(&mut out, true);
    assert_eq!(out.len(), 1, "the half-written fill waits");
    assert!(matches!(out[0], LiveEv::Attempt { t: 1000000000123, .. }));
    write!(f, "ens\":5,\"sol_in\":7}}\n").unwrap(); f.flush().unwrap();
    out.clear(); t.poll(&mut out, true);
    assert!(matches!(&out[0], LiveEv::Fill { w: 3, slot: 5, tokens: 5, .. }), "{out:?}");
    let _ = std::fs::remove_dir_all(&d);
}

#[test]
fn feeder_drops_when_full_never_blocks() {
    let d = tmpdir("feed");
    let mut c = cfg_all(&d); c.chan = 4;
    let (tx, rx) = crossbeam_channel::bounded(c.chan);
    let f = Feeder { tx, ctr: Arc::new(Ctr::default()), watch: Arc::new(FxHashSet::default()), raw: true, fail: false, pumpswap: *crate::venues::PUMPSWAP, race: false };
    let x = Arc::new(ExecInfo { index: 1, fee: 0, ok: true, trades: vec![], creates: vec![], mayhem: false });
    let a = Arrival { feed: 0, slot: 1, t_rx: 1, t_decoded: 1, executed: Some(true), tx: crate::tx::Tx::default(), poh: None, raw: crate::feeds::RawTx::None, exec: Some(x.clone()) };
    let t = Instant::now();
    for _ in 0..1000 { f.exec(&a, &x); }
    assert!(t.elapsed() < Duration::from_millis(200));
    assert_eq!(f.ctr.sent.load(Ordering::Relaxed), 4);
    assert_eq!(f.ctr.drops.load(Ordering::Relaxed), 996);
    drop(rx);
    let _ = std::fs::remove_dir_all(&d);
}

/// the thread end to end: start, messages, finish -> obs_start / records / obs_status / obs_summary / obs_end in the file
#[test]
fn obs_thread_end_to_end() {
    let d = tmpdir("e2e");
    let c = cfg_all(&d);
    std::fs::write(c.tail.as_ref().unwrap(), "").unwrap();
    let mut o = Obs::start(c.clone()).unwrap();
    let mut tk = Tk::new(8);
    let mk = |slot: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>| {
        let x = Arc::new(ExecInfo { index: 1, fee: 0, ok: true, trades, creates, mayhem: false });
        Arrival { feed: 0, slot, t_rx: 1_800_000_000 * S + slot * 213 * MS, t_decoded: 0, executed: Some(true), tx: crate::tx::Tx::default(), poh: None, raw: crate::feeds::RawTx::None, exec: Some(x) }
    };
    let a = mk(10, vec![tk.buy(CREATOR, S)], vec![tk.create()]);
    o.feeder.exec(&a, a.exec.as_ref().unwrap());
    for s in 11..40 { let a = mk(s, vec![tk.buy([0x77; 32], S / 10)], vec![]); o.feeder.exec(&a, a.exec.as_ref().unwrap()); }
    let end = o.finish(Duration::from_secs(10));
    assert_eq!(end["dropped"], 0);
    let r = recs_of(&c.out);
    for k in ["obs_start", "obs_status", "obs_summary", "obs_end", "watch_trade"] { assert!(r.iter().any(|x| x["ev"] == k), "{k} missing"); }
    let _ = std::fs::remove_dir_all(&d);
}

/// module 9: two feeds race; the tagged whale buy gets a record, the per-feed summary has wins / leads
#[test]
fn feed_race_records_and_summary() {
    let mut r = race::Race::new(vec!["kaldera".into(), "astralane".into()]);
    let mut recs = Vec::new();
    let t0 = 1_800_000_000 * S;
    for k in 0..100u64 {
        r.on_arrival(k, 1, t0 + k * MS, 10, t0 + k * MS, &mut recs);
        r.on_arrival(k, 0, t0 + k * MS + 300_000, 10, t0 + k * MS, &mut recs);
    }
    r.tag(5, 7, race::T_WHALE);
    r.expire(u64::MAX, true, &mut recs);
    let tagged: Vec<&(usize, Value)> = recs.iter().filter(|x| x.1["tag"] == 1).collect();
    assert_eq!(tagged.len(), 1);
    assert_eq!(tagged[0].1["first"], "astralane");
    assert_eq!(tagged[0].1["lag_us"]["kaldera"], 300.0);
    assert_eq!(recs.len(), 1 + 100 / race::SAMPLE as usize - 0, "{}", recs.len());
    let s = r.summary();
    assert_eq!(s["per_feed"]["astralane"]["wins"], 100);
    assert_eq!(s["per_feed"]["astralane"]["lead_us_p50"], 300.0);
}

/// module 8: a laddered 3% crossing that our rule does not arm, its holder's dump, the outcome record; the dump label
#[test]
fn selection_candidate_and_label() {
    let d = tmpdir("sel");
    let mut c = cfg_all(&d); c.rearm = false; c.hold = false; c.migr = false; c.blink = false; c.watch.clear();
    let mut h = hub(c.clone());
    let mut f = Feed { slot: 0, idx: 0 };
    let mut tk = Tk::new(11);
    let w = [0xE1u8; 32];
    let t0 = 1_800_000_000 * S;
    let dev = tk.buy(CREATOR, S / 2); f.tx(&mut h, 5000, t0, vec![dev], vec![tk.create()]);
    let e = tk.buy_tok(w, 20_000_000_000_000); f.tx(&mut h, 5001, t0 + 213 * MS, vec![e], vec![]);
    let e = tk.buy_tok(w, 20_000_000_000_000); f.tx(&mut h, 5002, t0 + 426 * MS, vec![e], vec![]);   // crosses 3% on its second buy: laddered, 4% < 6%
    let e = tk.sell_tok(w, 40_000_000_000_000); f.tx(&mut h, 5005, t0 + 1_000 * MS, vec![e], vec![]); // its dump (~1.4 SOL)
    let e = tk.buy([0xE2; 32], S / 2); f.tx(&mut h, 5005, t0 + 1_001 * MS, vec![e], vec![]);
    let mut other = Tk::new(9);
    for s in 5006..5080 { let o = other.buy([0x57; 32], S / 100); f.tx(&mut h, s, t0 + (s - 5000) * 213 * MS, vec![o], vec![]); }
    let _ = h.end();
    let r = recs_of(&c.out);
    let sc = r.iter().find(|x| x["ev"] == "select_cand" && x["w"] == book::short(&w)).expect("select_cand");
    assert_eq!(sc["class"], "laddered");
    assert_eq!(sc["live_arms"], false);
    assert_eq!(sc["why_not"], "below_6pct_at_crossing");
    assert_eq!(sc["outcome"]["dump"]["slot_gap"], 3);
    let br = r.iter().find(|x| x["ev"] == "backrun_sell" && x["seller"] == book::short(&w)).expect("backrun_sell");
    assert_eq!(br["armable"]["classes"][0], "laddered");
    let sum = r.iter().rev().find(|x| x["ev"] == "obs_summary").unwrap();
    assert_eq!(sum["select"]["per_class"]["laddered"]["dump_10"], 1);
    let _ = std::fs::remove_dir_all(&d);
}

/// module 10: a >= 1 SOL sell, the next slot seen 50 ms after it: legs landing before it fill (same slot), later ones fail_slot
#[test]
fn inslot_legs_slot_check() {
    let d = tmpdir("inslot");
    let mut c = cfg_all(&d); c.rearm = false; c.hold = false; c.migr = false; c.blink = false; c.watch.clear(); c.select = false; c.backrun = false;
    let mut h = hub(c.clone());
    let mut f = Feed { slot: 0, idx: 0 };
    let mut tk = Tk::new(12);
    let t0 = 1_800_000_000 * S;
    let dev = tk.buy(CREATOR, S); f.tx(&mut h, 6000, t0, vec![dev], vec![tk.create()]);
    let e = tk.buy([0x61; 32], 4 * S); f.tx(&mut h, 6005, t0 + 1000 * MS, vec![e], vec![]);
    let e = tk.sell_sol([0x61; 32], 2 * S); f.tx(&mut h, 6010, t0 + 2000 * MS, vec![e], vec![]);
    let mut other = Tk::new(9);
    let o = other.buy([0x57; 32], S / 100); f.tx(&mut h, 6011, t0 + 2050 * MS, vec![o], vec![]);
    for s in 6012..6080 { let o = other.buy([0x57; 32], S / 100); f.tx(&mut h, s, t0 + 2050 * MS + (s - 6011) * 213 * MS, vec![o], vec![]); }
    let _ = h.end();
    let r = recs_of(&c.out);
    let x = r.iter().find(|x| x["ev"] == "inslot").expect("inslot");
    assert_eq!(x["legs"]["15"]["res"], "fill");
    assert_eq!(x["legs"]["45"]["res"], "fill", "{}", x["legs"]);
    assert_eq!(x["legs"]["60"]["res"], "fail_slot");
    assert!(x["legs"]["15"]["v"]["0.75"][3].is_number());
    let _ = std::fs::remove_dir_all(&d);
}

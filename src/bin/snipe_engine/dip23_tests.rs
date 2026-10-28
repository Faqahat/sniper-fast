// ===================================================================================================================
// dip23 tests (10-28 PKT): the QUIET v2 LOG-ONLY annotation (--presend-live-quiet-v2-log; ops/strategies/presend/filter/QUIET2.md
// §5.2; the ring itself is unit-tested in src/presend_quiet.rs). Off by default: dip22's records, no ring.
//  * flags: off by default; a stray flag without --presend-live refused; the cfg record names it only when on
//  * the records: "v2" on presend_live_arm and presend_live_skip ONLY with the flag; its values at a trigger are the study's
//    (trades of the last 60 s before the trigger, the pre-trade price vs the 120 s high); the trigger's own trade not counted;
//    the shadow's presend_arm gets "v2" too (with QUIET on); nothing else changes (the arm itself, the skip reason)
//  * the counters: arms / skips with v2.skip true / false in the status line and run_end
// ===================================================================================================================
use super::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;
const NS: u64 = 1_000_000_000;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn probe(extra: &[&str]) -> (PsLive, crossbeam_channel::Sender<Att>, crossbeam_channel::Receiver<Out>) { PsLive::for_test(cfg(extra).unwrap().unwrap(), USER) }
fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| match o { Out::Rec(v) => Some(v), Out::Line(_) => None }).collect() }

/// a token on its curve (pump's constant product) and its launch
struct Tk { mint: Pk, v: u64, t: u64, launch: Launch }
impl Tk {
    fn new(k: u8) -> Tk { let mint = [k; 32]; Tk { mint, v: 30 * S, t: 1_073_000_000_000_000, launch: snipe_build::launch_from_target(mint, CREATOR) } }
    fn buy(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v + sol) as u128) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn sell_sol(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v - sol) as u128) as u64;
        self.v -= sol; self.t += q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: false, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn create(&self) -> CreateEvent { CreateEvent { mint: self.mint, bonding_curve: self.launch.bonding_curve, user: CREATOR, creator: CREATOR } }
    fn price(&self) -> f64 { self.v as f64 / self.t as f64 }
}

/// one executed tx through on_arrival + on_exec at feed time `t_rx` (ns)
fn tx(p: &mut PsLive, slot: u64, idx: u64, t_rx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>, launches: &[&Launch]) {
    let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0xD3;
    let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
    let a = arbx::feeds::Arrival { feed: 0, slot, t_rx, t_decoded: t_rx, executed: Some(true),
        tx: arbx::tx::Tx { sig, keys: vec![[0x77; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
    let ls: Vec<Launch> = launches.iter().map(|l| (*l).clone()).collect();
    p.on_arrival(&a, slot);
    p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
}

/// the scenario: token k created at 1000 s; the dev buy; `pre` = (seconds, user, SOL, buy?) trades; the whale's 2 SOL buy at
/// `t_trig` s (slot = seconds: one slot per second here). -> (the token, the whale's trade's pre-trade price)
fn scenario(p: &mut PsLive, k: u8, pre: &[(u64, Pk, u64, bool)], whale: Pk, t_trig: u64, launch: bool) -> (Tk, f64) {
    let mut tk = Tk::new(k);
    let dev = tk.buy(CREATOR, S / 2);
    tx(p, 1000, 3, 1000 * NS, vec![dev], vec![tk.create()], &[&tk.launch]);
    for (n, (s, u, sol, buy)) in pre.iter().enumerate() {
        let e = if *buy { tk.buy(*u, *sol) } else { tk.sell_sol(*u, *sol) };
        tx(p, *s, 10 + n as u64, *s * NS, vec![e], vec![], &[&tk.launch]);
    }
    let pre_p = tk.price();
    let e = tk.buy(whale, 2 * S);
    let ls: Vec<&Launch> = if launch { vec![&tk.launch] } else { vec![] };
    tx(p, t_trig, 50, t_trig * NS, vec![e], vec![], &ls);
    (tk, pre_p)
}

#[test]
fn dip23_flag_off_by_default_and_refused_without_presend_live() {
    let c = cfg(&[]).unwrap().unwrap();
    assert!(!c.quiet_v2_log, "off by default: dip22's run");
    assert!(c.json().get("quiet_v2_log").is_none(), "the cfg record unchanged without the flag");
    let c = cfg(&["--presend-live-quiet-v2-log"]).unwrap().unwrap();
    assert!(c.quiet_v2_log);
    assert_eq!(c.json()["quiet_v2_log"], true);
    // with QUIET's own flags or without: independent of them
    assert!(cfg(&["--presend-live-quiet-v2-log", "--presend-live-quiet-stop", "6:2"]).unwrap().unwrap().quiet_v2_log);
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-live-quiet-v2-log"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1_000_000_000).is_err(), "a stray flag without --presend-live is refused");
}

#[test]
fn dip23_v2_field_only_with_the_flag() {
    let (x, y) = ([0x33u8; 32], [0x44u8; 32]);
    let pre = [(1010, x, S / 10, true), (1020, y, S / 10, true), (1100, x, S / 20, false)];
    // OFF: no ring, no field, the arm as before
    let (mut p, _atx, orx) = probe(&[]);
    assert!(p.v2.is_none());
    let (ta, _) = scenario(&mut p, 1, &pre, [0x11; 32], 1150, true);
    assert!(p.armed.contains_key(&ta.mint));
    let r = recs(&orx);
    let arm = r.iter().find(|r| r["ev"] == "presend_live_arm").unwrap();
    assert!(arm.get("v2").is_none(), "{arm}");
    assert!(!p.status().contains("QUIET v2"));
    assert_eq!((p.st.v2_arm, p.st.v2_skip), ([0, 0], [0, 0]));
    // ON: the same scenario arms the same way, the record gains "v2"
    let (mut p, _atx, orx) = probe(&["--presend-live-quiet-v2-log"]);
    assert!(p.v2.is_some());
    let (tb, _) = scenario(&mut p, 1, &pre, [0x11; 32], 1150, true);
    assert!(p.armed.contains_key(&tb.mint));
    let r = recs(&orx);
    let arm = r.iter().find(|r| r["ev"] == "presend_live_arm").unwrap();
    assert_eq!(bare(arm.clone()), bare(recs_of_off(&pre)), "the arm record is dip22's plus \"v2\"");
    let v = &arm["v2"];
    // the trigger at 1150 s: the last 60 s [1090, 1150) hold the 1100 s sell only; the 120 s [1030, 1150) hold it too (n_120s 1);
    // the high of the 120 s window = the post price of that sell = the trigger's pre-trade price -> at the high, dd 0, skip
    assert_eq!((v["n_tr_60s"].as_u64(), v["n_120s"].as_u64(), v["at_120s_high"].as_bool(), v["skip"].as_bool()), (Some(1), Some(1), Some(true), Some(true)), "{v}");
    assert!(v["maxdd_120s"].as_f64().unwrap().abs() < 1e-9);
    assert_eq!(v["ring_s"].as_f64(), Some(150.0), "the ring saw the feed since the create at 1000 s");
    assert_eq!((p.st.v2_arm, p.st.v2_skip), ([1, 0], [0, 0]));
    assert!(p.status().contains("QUIET v2 (log-only): arms skip/keep 1/0 skips skip/keep 0/0"), "{}", p.status());
}

/// the arm record of the same scenario with the flag off (a fresh probe), for the record-for-record comparison
fn recs_of_off(pre: &[(u64, Pk, u64, bool)]) -> serde_json::Value {
    let (mut p, _atx, orx) = probe(&[]);
    scenario(&mut p, 1, pre, [0x11; 32], 1150, true);
    recs(&orx).into_iter().find(|r| r["ev"] == "presend_live_arm").unwrap()
}
/// a record without the fields that differ by construction (the v2 object)
fn bare(mut v: serde_json::Value) -> serde_json::Value { if let Some(o) = v.as_object_mut() { o.remove("v2"); } v }

#[test]
fn dip23_v2_values_are_the_studys_and_causal() {
    let (mut p, _atx, orx) = probe(&["--presend-live-quiet-v2-log"]);
    let x = [0x33u8; 32];
    // token 2: 7 buys in the last 60 s (1091..1097 s) push the price to its high at 1097; a 0.5 SOL sell at 1098 drops it; the whale
    // buys at 1100 s: n_tr_60s = 8 (7 buys + the sell), n_120s = 9 (+ the dev buy at 1000 s: the 120 s window is [980, 1100)), not
    // at the high (the sell dropped the price) -> keep
    let mut pre: Vec<(u64, Pk, u64, bool)> = (0..7).map(|k| (1091 + k, x, S / 5, true)).collect();
    pre.push((1098, x, S / 2, false));
    let (tk, pre_p) = scenario(&mut p, 2, &pre, [0x12; 32], 1100, true);
    let r = recs(&orx);
    let arm = r.iter().find(|r| r["ev"] == "presend_live_arm" && r["trig"]["mint"] == b58(&tk.mint)).unwrap();
    let v = &arm["v2"];
    assert_eq!((v["n_tr_60s"].as_u64(), v["n_120s"].as_u64(), v["at_120s_high"].as_bool(), v["skip"].as_bool()), (Some(8), Some(9), Some(false), Some(false)), "{v}");
    // the drawdown = (high - pre_p) / high with the high = the post price after the 7th buy (before the sell)
    let mut t2 = Tk::new(2); t2.buy(CREATOR, S / 2); for _ in 0..7 { t2.buy(x, S / 5); }
    let high = t2.price();
    let dd = (high - pre_p) / high;
    assert!((v["maxdd_120s"].as_f64().unwrap() - dd).abs() < 1e-9 && dd > 0.01, "{v} vs {dd}");
    // causal: the whale's own trigger buy (which lifts the price) is NOT in the ring at the trigger, but is afterwards: a second
    // trigger on the token (blocked: armed) 1 s later sees 9 trades in 60 s and the price at its (new) high
    let mut tk = tk;
    let e = tk.buy([0x13; 32], 3 * S);
    tx(&mut p, 1101, 50, 1101 * NS, vec![e], vec![], &[&tk.launch]);
    let r = recs(&orx);
    let sk = r.iter().find(|r| r["ev"] == "presend_live_skip" && r["trig"]["mint"] == b58(&tk.mint)).unwrap();
    assert_eq!(sk["why"], "blocked_armed");
    let v = &sk["v2"];
    assert_eq!((v["n_tr_60s"].as_u64(), v["at_120s_high"].as_bool(), v["skip"].as_bool()), (Some(9), Some(true), Some(false)), "{v}");
    assert_eq!((p.st.v2_arm, p.st.v2_skip), ([0, 1], [0, 1]));
    // token 3: a quiet token (2 trades in 60 s, the whale buys at the high) with no launch accounts: the skip record carries v2.skip
    let (t3, _) = scenario(&mut p, 3, &[(1200, x, S / 10, true), (1210, x, S / 10, true)], [0x14; 32], 1250, false);
    let r = recs(&orx);
    let sk = r.iter().find(|r| r["ev"] == "presend_live_skip" && r["trig"]["mint"] == b58(&t3.mint)).unwrap();
    assert_eq!(sk["why"], "no_launch_accounts");
    assert_eq!((sk["v2"]["n_tr_60s"].as_u64(), sk["v2"]["skip"].as_bool()), (Some(2), Some(true)), "{}", sk["v2"]);
    assert_eq!((p.st.v2_arm, p.st.v2_skip), ([0, 1], [1, 1]));
    assert!(p.status().contains("arms skip/keep 0/1 skips skip/keep 1/1"), "{}", p.status());
    // the sweep (tick): tokens idle for 120 s of feed time leave the ring: token 2 (last trade 1101 s) went at the tick of 1250 s;
    // token 3 (last trade 1250 s) goes at the tick of 1400 s
    assert_eq!(p.v2.as_ref().unwrap().tokens(), 1, "token 2 swept at 1250 s, token 3 in the ring");
    let mut t4 = Tk::new(4);
    let e = t4.buy(x, S / 10);
    tx(&mut p, 1400, 1, 1400 * NS, vec![e], vec![], &[&t4.launch]);
    assert_eq!(p.v2.as_ref().unwrap().tokens(), 1, "token 3 swept at 1400 s, token 4 in the ring");
    // run_end's totals carry the counters
    let j = p.v2_json().unwrap();
    assert_eq!((j["arm_keep"].as_u64(), j["skip_skip"].as_u64(), j["skip_keep"].as_u64(), j["rule"]["n_max"].as_u64()), (Some(1), Some(1), Some(1), Some(6)));
}

#[test]
fn dip23_shadow_arm_annotated_with_quiet_on() {
    // with QUIET on (the production config has it), the live trigger's v2 goes onto the shadow's presend_arm of the same trigger
    let (mut p, _atx, orx) = probe(&["--presend-live-quiet-v2-log", "--presend-live-quiet-stop", "6:2"]);
    let x = [0x33u8; 32];
    let (_tk, _) = scenario(&mut p, 5, &[(1010, x, S / 10, true)], [0x15; 32], 1100, true);
    let r = recs(&orx);
    let arm = r.iter().find(|r| r["ev"] == "presend_live_arm").unwrap();
    assert!(arm["v2"].is_object() && arm["quiet"].is_object());
    let (mint_s, sig_s, j) = (arm["trig"]["mint"].clone(), arm["trig"]["sig"].clone(), arm["trig"]["j"].clone());
    let mut evs = vec![arbx::presend::Ev { rec: serde_json::json!({"ev": "presend_arm", "mint": mint_s, "sig": sig_s, "j": j, "w": 7, "slot": 1100}), line: None },
                       arbx::presend::Ev { rec: serde_json::json!({"ev": "presend_arm", "mint": b58(&[9u8; 32]), "sig": "nope", "j": 0, "w": 8, "slot": 1100}), line: None }];
    p.annotate_shadow(&mut evs);
    assert_eq!(evs[0].rec["v2"], arm["v2"], "the shadow arm of the live trigger gets the same v2");
    assert!(evs[0].rec["quiet"].is_object());
    assert!(evs[1].rec.get("v2").is_none() && evs[1].rec["quiet"]["live_trigger"] == false, "a shadow arm with no live trigger: no v2");
    // without the v2 flag the shadow arm has no v2 even with QUIET on
    let (mut p, _atx, orx) = probe(&["--presend-live-quiet-stop", "6:2"]);
    let (_tk, _) = scenario(&mut p, 5, &[(1010, x, S / 10, true)], [0x15; 32], 1100, true);
    let r = recs(&orx);
    let arm = r.iter().find(|r| r["ev"] == "presend_live_arm").unwrap();
    let mut evs = vec![arbx::presend::Ev { rec: serde_json::json!({"ev": "presend_arm", "mint": arm["trig"]["mint"].clone(), "sig": arm["trig"]["sig"].clone(), "j": arm["trig"]["j"].clone(), "w": 7, "slot": 1100}), line: None }];
    p.annotate_shadow(&mut evs);
    assert!(evs[0].rec.get("v2").is_none() && evs[0].rec["quiet"].is_object());
}

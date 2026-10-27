// ===================================================================================================================
// dip20 tests (10-27 PKT; owner "implement QUIET in engine"; ops/strategies/presend/filter/REPORT.md). Declared inside pslive.rs
// (the probe's state machine is private to it), driven through on_arrival / on_exec / tick as the event loop calls them.
//  * flags: off by default (no state, dip19's records and status line), the owner's line accepted, every refusal
//  * the STOP (N:M): the trigger's own trade not counted, the whale's and ours not counted, a same-tx later trade counted; at
//    trigger + N with fewer than M others the window is disarmed "quiet" (no attempt any more); with M others it runs on
//  * the ARM RULE: all four signals -> skip "quiet"; each signal alone keeps the window; the warm-up arms (would_skip); the
//    whale's dump history from the live DumpBook
//  * the parity tapes: QUIET on with rules that never fire = QUIET off record for record (it only ADDS fields), the shadow's
//    records only gain "quiet" / "quiet_stop"; with the owner's rules, skips and stops happen; the per-trade cost
//  * the PRELOAD thread: merged in tick (the arm rule on at once), a failed one leaves the warm-up
// ===================================================================================================================
use super::*;
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
fn probe(extra: &[&str]) -> (PsLive, crossbeam_channel::Sender<Att>, crossbeam_channel::Receiver<Out>) { PsLive::for_test(cfg(extra).unwrap().unwrap(), USER) }
fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| match o { Out::Rec(v) => Some(v), Out::Line(_) => None }).collect() }
fn all_out(orx: &crossbeam_channel::Receiver<Out>) -> (Vec<serde_json::Value>, Vec<String>) {
    let (mut r, mut l) = (Vec::new(), Vec::new());
    for o in orx.try_iter() { match o { Out::Rec(v) => r.push(v), Out::Line(x) => l.push(x) } }
    (r, l)
}

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
}

/// one executed tx through on_arrival + on_exec (the event loop's order); `t_rx` = slot ms + idx (ns)
fn tx(p: &mut PsLive, slot: u64, idx: u64, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>, launches: &[&Launch]) {
    let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&slot.to_be_bytes()); sig[8..16].copy_from_slice(&idx.to_be_bytes()); sig[16] = 0xD2;
    let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
    let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
        tx: arbx::tx::Tx { sig, keys: vec![[0x77; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
    let ls: Vec<Launch> = launches.iter().map(|l| (*l).clone()).collect();
    p.on_arrival(&a, slot);
    p.on_exec(&a, &x, slot, move |m: &Pk| ls.iter().find(|l| l.mint == *m).cloned(), &|_| false, None);
}

/// a token created at `s0` (with the creator's dev buy), then `pre` (slot, user, SOL) buys, then the whale's 2 SOL buy (>= 5%: the
/// trigger) at `s_trig`
fn token_to_trigger(p: &mut PsLive, k: u8, s0: u64, pre: &[(u64, Pk, u64)], whale: Pk, s_trig: u64) -> Tk {
    let mut tk = Tk::new(k);
    let dev = tk.buy(CREATOR, S / 2);
    tx(p, s0, 3, vec![dev], vec![tk.create()], &[&tk.launch]);
    for (n, (s, u, sol)) in pre.iter().enumerate() { let e = tk.buy(*u, *sol); tx(p, *s, 10 + n as u64, vec![e], vec![], &[&tk.launch]); }
    let e = tk.buy(whale, 2 * S);
    tx(p, s_trig, 50, vec![e], vec![], &[&tk.launch]);
    tk
}

#[test]
fn dip20_flags_off_and_refusals() {
    // OFF by default: no QUIET state, dip19's config record, status line and totals
    let c = cfg(&[]).unwrap().unwrap();
    assert_eq!(c.quiet, QuietCfg::default());
    assert!(!c.quiet.on() && c.json().get("quiet").is_none());
    let (mut p, _atx, _orx) = PsLive::for_test(c, USER);
    assert!(p.qt.is_none());
    assert!(!p.status().contains("QUIET"));
    assert!(p.finish(10, None).get("quiet").is_none());
    // the owner's line
    let owner = ["--presend-live-quiet-stop", "6:2", "--presend-live-quiet-skip", "on", "--presend-live-quiet-hist-h", "24", "--presend-live-quiet-fol", "2.24",
        "--presend-live-quiet-warmup-min", "60", "--presend-live-fbots", "/root/dip/fbots_frozen.json", "--presend-live-quiet-preload", "/root/sniper-collect/current_run"];
    let c = cfg(&owner).unwrap().unwrap();
    assert_eq!(c.quiet, QuietCfg { stop: Some(pq::QStop { n: 6, m: 2 }), skip: true, hist_h: 24.0, fol: 2.24, warmup_min: 60.0,
        fbots: Some("/root/dip/fbots_frozen.json".into()), preload: Some("/root/sniper-collect/current_run".into()) });
    assert_eq!(c.json()["quiet"]["stop"], "6:2");
    assert!(check_flags(&args(&owner)).is_ok(), "{:?}", check_flags(&args(&owner)));
    // the stop alone; the skip alone
    assert_eq!(cfg(&["--presend-live-quiet-stop", "4:3"]).unwrap().unwrap().quiet, QuietCfg { stop: Some(pq::QStop { n: 4, m: 3 }), ..Default::default() });
    let c = cfg(&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x.json"]).unwrap().unwrap();
    assert!(c.quiet.skip && c.quiet.stop.is_none() && c.quiet.preload.is_none() && (c.quiet.hist_h, c.quiet.fol, c.quiet.warmup_min) == (24.0, 2.24, 60.0));
    assert!(!cfg(&["--presend-live-quiet-skip", "off"]).unwrap().unwrap().quiet.on());
    // every QUIET flag needs --presend-live
    let p0 = arbx::presend::Params::default();
    for f in QFLAGS {
        let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", f, "1"].iter().map(|s| s.to_string()).collect::<Vec<_>>(), &p0, true, 1_000_000_000).unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
    // the skip's parameters need the skip on; the skip needs its follower-bot list
    for (f, v) in [("--presend-live-quiet-hist-h", "24"), ("--presend-live-quiet-fol", "2"), ("--presend-live-quiet-warmup-min", "5"), ("--presend-live-fbots", "/x"),
                   ("--presend-live-quiet-preload", "/y")] {
        let e = cfg(&["--presend-live-quiet-stop", "6:2", f, v]).unwrap_err().to_string();
        assert!(e.contains("needs --presend-live-quiet-skip on"), "{f}: {e}");
    }
    assert!(cfg(&["--presend-live-quiet-skip", "on"]).unwrap_err().to_string().contains("--presend-live-fbots"));
    // bad values
    for bad in [&["--presend-live-quiet-stop", "6"][..], &["--presend-live-quiet-stop", "0:2"], &["--presend-live-quiet-stop", "6:x"], &["--presend-live-quiet-stop"],
                &["--presend-live-quiet-skip", "yes"], &["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-hist-h", "0"],
                &["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-hist-h", "49"],
                &["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-fol", "0"],
                &["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-warmup-min", "1441"],
                &["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-preload", "--presend-live-k"]] {
        assert!(cfg(bad).is_err(), "{bad:?} should be refused");
    }
    // the engine's start-up check: numbers, misspellings
    assert!(check_flags(&args(&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/x", "--presend-live-quiet-hist-h", "abc"])).is_err());
    let wrong = ["-", "-presend-live-quiet-stp"].concat();
    assert!(check_flags(&args(&[&wrong, "6:2"])).is_err());
    // the follower-bot list: refused when unreadable / empty / a bad wallet
    let d = std::env::temp_dir().join(format!("dip20_fb_{}", std::process::id()));
    std::fs::create_dir_all(&d).unwrap();
    std::fs::write(d.join("ok.json"), r#"["EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR","2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE"]"#).unwrap();
    std::fs::write(d.join("empty.json"), "[]").unwrap();
    std::fs::write(d.join("bad.json"), r#"["nope0"]"#).unwrap();
    assert_eq!(load_fbots(d.join("ok.json").to_str().unwrap()).unwrap().len(), 2);
    for f in ["empty.json", "bad.json", "missing.json"] { assert!(load_fbots(d.join(f).to_str().unwrap()).is_err(), "{f}"); }
    // the real list next to the research
    let fb = format!("{}/ops/strategies/presend/filter/fbots_frozen.json", env!("CARGO_MANIFEST_DIR"));
    if std::path::Path::new(&fb).exists() { assert_eq!(load_fbots(&fb).unwrap().len(), 297); }
    let _ = std::fs::remove_dir_all(&d);
}

/// THE STOP (6:2): token A: 1 other trade by trigger + 6 (the whale's second buy and our own wallet's trade not counted) -> disarmed
/// "quiet" at + 6, its window out of the sender's list; token B: 2 others -> runs to its end ("expired", quiet_stop false);
/// token C: a later trade IN the trigger's own tx counts (with one more: 2 -> no stop)
#[test]
fn dip20_quiet_stop_n_m() {
    let (mut p, _atx, orx) = probe(&["--presend-live-quiet-stop", "6:2"]);
    let (w, o1, o2) = ([0x11u8; 32], [0x21u8; 32], [0x22u8; 32]);
    let mut ta = token_to_trigger(&mut p, 1, 100, &[(102, o1, S / 10)], w, 110);
    assert_eq!(p.armed.get(&ta.mint), Some(&1), "{:?}", p.st.skips);
    let e = ta.buy(o2, S / 10); tx(&mut p, 111, 5, vec![e], vec![], &[&ta.launch]);
    let e = ta.buy(w, S / 10); tx(&mut p, 112, 5, vec![e], vec![], &[&ta.launch]);
    let e = ta.buy(USER, S / 10); tx(&mut p, 113, 5, vec![e], vec![], &[&ta.launch]);
    let mut tz = Tk::new(90);
    tx(&mut p, 114, 1, vec![], vec![tz.create()], &[&tz.launch]);
    let e = tz.buy(o1, S / 10); tx(&mut p, 115, 1, vec![e], vec![], &[&tz.launch]);
    assert_eq!(p.wins[&1].disarmed, None, "before trigger + 6: undecided");
    assert_eq!(p.qt.as_ref().unwrap().watch[&ta.mint][0].others, 1);
    let e = tz.buy(o1, S / 10); tx(&mut p, 116, 1, vec![e], vec![], &[&tz.launch]);
    assert_eq!(p.wins[&1].disarmed, Some("quiet"));
    assert!(!p.armed.contains_key(&ta.mint) && p.sh.wins.lock().unwrap().iter().all(|x| x.id != 1), "no attempt any more");
    let (r, lines) = all_out(&orx);
    let d = r.iter().find(|x| x["ev"] == "presend_live_disarm" && x["w"] == 1).unwrap();
    assert_eq!((d["why"].as_str(), d["quiet_stop"].as_bool(), d["quiet"]["others"].as_u64(), d["quiet"]["decided"].as_bool()), (Some("quiet"), Some(true), Some(1), Some(true)));
    assert_eq!(r.iter().find(|x| x["ev"] == "presend_live_arm" && x["w"] == 1).unwrap()["quiet"]["stop"], "6:2");
    assert!(lines.iter().any(|l| l.contains("QUIET STOP w1") && l.contains("1 other trade(s)")), "{lines:?}");
    assert_eq!(p.qt.as_ref().unwrap().stops, 1);
    // B: 2 others by + 5 -> no stop; it expires at its end
    let mut tb = token_to_trigger(&mut p, 2, 200, &[], w, 210);
    let wb = p.armed[&tb.mint];
    for (s, u) in [(211, o1), (213, o2)] { let e = tb.buy(u, S / 10); tx(&mut p, s, 5, vec![e], vec![], &[&tb.launch]); }
    for s in [216, 218, 222] { let e = tz.buy(o2, S / 10); tx(&mut p, s, 1, vec![e], vec![], &[&tz.launch]); }
    assert_eq!(p.wins[&wb].disarmed, Some("expired"));
    let r = recs(&orx);
    let d = r.iter().find(|x| x["ev"] == "presend_live_disarm" && x["w"] == wb).unwrap();
    assert_eq!((d["quiet_stop"].as_bool(), d["quiet"]["others"].as_u64(), d["quiet"]["decided"].as_bool()), (Some(false), Some(2), Some(true)));
    // C: a trade after the trigger IN ITS OWN TX counts (chain order: after it), plus one more = 2 -> no stop
    let mut tc = Tk::new(3);
    let dev = tc.buy(CREATOR, S / 2);
    tx(&mut p, 300, 3, vec![dev], vec![tc.create()], &[&tc.launch]);
    let (e1, e2) = (tc.buy(w, 2 * S), tc.buy(o1, S / 10));
    tx(&mut p, 305, 9, vec![e1, e2], vec![], &[&tc.launch]);
    let wc = p.armed[&tc.mint];
    assert_eq!(p.qt.as_ref().unwrap().watch[&tc.mint][0].others, 1, "the trigger's own trade not counted, the later one in its tx counted");
    let e = tc.buy(o2, S / 10); tx(&mut p, 307, 2, vec![e], vec![], &[&tc.launch]);
    let e = tz.buy(o2, S / 10); tx(&mut p, 311, 1, vec![e], vec![], &[&tz.launch]);
    assert_eq!(p.wins[&wc].disarmed, None);
    assert_eq!(p.wins[&wc].q_others, Some(2));
    assert_eq!(p.qt.as_ref().unwrap().stops, 1);
    assert!(p.status().contains("QUIET: skips 0 (would-skip in the warm-up 0) stops 1"), "{}", p.status());
    assert_eq!(p.finish(400, None)["quiet"]["stops"], 1);
}

/// THE ARM RULE: all four signals -> skip "quiet" (no window); a cohort holder / 2 follower bots / a trade earlier in the trigger's
/// slot / a whale whose dumps drew >= 2.24 buyers each keep it armed; during the warm-up all four -> armed, would_skip
#[test]
fn dip20_quiet_skip_four_signals() {
    let (mut p, _atx, orx) = probe(&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/unused-in-tests.json"]);
    let (coh, f1, f2, x) = ([0xC0u8; 32], [0xF1u8; 32], [0xF2u8; 32], [0x33u8; 32]);
    { let q = p.qt.as_mut().unwrap(); q.coh = [coh].into_iter().collect(); q.fb = [f1, f2].into_iter().collect(); }
    // A: one follower bot, nobody of the cohort, a new slot, a whale without dumps -> QUIET skip
    let ta = token_to_trigger(&mut p, 1, 100, &[(102, f1, S / 10), (103, x, S / 10)], [0x11; 32], 108);
    assert!(!p.armed.contains_key(&ta.mint));
    assert_eq!(p.st.skips.get("quiet"), Some(&1));
    // B: a cohort wallet holds it
    let tb = token_to_trigger(&mut p, 2, 200, &[(202, coh, S / 10)], [0x12; 32], 208);
    assert!(p.armed.contains_key(&tb.mint));
    // C: two follower bots traded it (one sold out: "ever traded")
    let mut tc = token_to_trigger(&mut p, 3, 300, &[(302, f1, S / 10), (303, f2, S / 10)], [0x13; 32], 308);
    let _ = tc.buy(x, 1);
    assert!(p.armed.contains_key(&tc.mint));
    // D: another trade earlier in the trigger's own slot (since_last 0)
    let td = token_to_trigger(&mut p, 4, 400, &[(408, x, S / 10)], [0x14; 32], 408);
    assert!(p.armed.contains_key(&td.mint));
    // E: the whale dumped earlier on token X: 3 distinct other buyers within 2 slots (one buyer twice, the seller's own buy, a buy 3
    // slots later: not counted) -> 3.0 >= 2.24
    let mut tx_ = Tk::new(60);
    let dev = tx_.buy(CREATOR, 5 * S);
    tx(&mut p, 500, 1, vec![dev], vec![tx_.create()], &[&tx_.launch]);
    let we = [0x15u8; 32];
    // (a small buy: the whale must not trigger on X itself; its sell below is a dump all the same)
    let e = tx_.buy(we, S / 2); tx(&mut p, 501, 1, vec![e], vec![], &[&tx_.launch]);
    let e = tx_.sell_sol(we, 4 * S); tx(&mut p, 502, 1, vec![e], vec![], &[&tx_.launch]);
    for (s, i, u) in [(502u64, 2u64, [0x41u8; 32]), (503, 1, [0x42; 32]), (503, 2, [0x41; 32]), (503, 3, we), (504, 1, [0x43; 32]), (505, 1, [0x44; 32])] {
        let e = tx_.buy(u, S / 10); tx(&mut p, s, i, vec![e], vec![], &[&tx_.launch]);
    }
    let te = token_to_trigger(&mut p, 5, 510, &[(512, x, S / 10)], we, 520);
    assert!(p.armed.contains_key(&te.mint), "{:?}", p.st.skips);
    let r = recs(&orx);
    let arm_e = r.iter().find(|r| r["ev"] == "presend_live_arm" && r["trig"]["mint"] == b58(&te.mint)).unwrap();
    assert_eq!((arm_e["quiet"]["wh_fol"].as_f64(), arm_e["quiet"]["wh_dumps"].as_u64(), arm_e["quiet_skip"].as_bool()), (Some(3.0), Some(1), Some(false)));
    // the records: the skip with its four signals; the arms with theirs
    let sk = r.iter().find(|r| r["ev"] == "presend_live_skip" && r["why"] == "quiet").unwrap();
    assert_eq!(sk["quiet_skip"], true);
    assert_eq!((sk["quiet"]["since_last"].as_u64(), sk["quiet"]["coh_hold"].as_u64(), sk["quiet"]["fb_n"].as_u64(), sk["quiet"]["wh_fol"].as_f64()), (Some(5), Some(0), Some(1), Some(-1.0)));
    assert_eq!(sk["quiet"]["q"], serde_json::json!([true, true, true, true]));
    let q_of = |m: &Pk| r.iter().find(|r| r["ev"] == "presend_live_arm" && r["trig"]["mint"] == b58(m)).unwrap()["quiet"]["q"].clone();
    assert_eq!(q_of(&tb.mint), serde_json::json!([true, false, true, true]));
    assert_eq!(q_of(&tc.mint), serde_json::json!([true, true, false, true]));
    assert_eq!(q_of(&td.mint), serde_json::json!([false, true, true, true]));
    assert_eq!(q_of(&te.mint), serde_json::json!([true, true, true, false]));
    // the warm-up (60 min from now; the trigger's arrival time is the schedule's clock): all four, the rule still off -> armed, would_skip
    { let q = p.qt.as_mut().unwrap(); q.start_ns = arbx::feeds::clock::now_ns(); q.warm_ns = 60 * 60_000_000_000; }
    let tf = token_to_trigger(&mut p, 7, 600, &[], [0x16; 32], 606);
    assert!(p.armed.contains_key(&tf.mint));
    let r = recs(&orx);
    let a = r.iter().find(|r| r["ev"] == "presend_live_arm" && r["trig"]["mint"] == b58(&tf.mint)).unwrap();
    assert_eq!((a["quiet"]["rule_on"].as_bool(), a["quiet"]["would_skip"].as_bool(), a["quiet"]["all4"].as_bool()), (Some(false), Some(true), Some(true)));
    let q = p.qt.as_ref().unwrap();
    assert_eq!((q.skips, q.warm_would, q.signals), (1, 1, 6));
    assert!(p.status().contains("arm rule off (warm-up until"), "{}", p.status());
}

/// the parity tapes' executed txs (chain order) and launches (pslive's own tests' loader, duplicated: dip19's tests stay as they are)
fn tapes(n: usize) -> Option<(Vec<(u64, u64, [u8; 64], arbx::feeds::ExecInfo)>, HashMap<Pk, Launch>)> {
    let root = env!("CARGO_MANIFEST_DIR");
    let par: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(format!("{root}/testdata/presend_parity.json")).ok()?).ok()?;
    let pk = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
    let mut by: std::collections::BTreeMap<(u64, u64), ([u8; 64], Vec<(i64, TradeEvent)>, Vec<CreateEvent>)> = Default::default();
    let mut launches = HashMap::new();
    for tk in par["tokens"].as_array().unwrap().iter().take(n) {
        let mint = pk(tk["mint"].as_str().unwrap());
        let users: Vec<Pk> = tk["users"].as_array().unwrap().iter().map(|u| pk(u.as_str().unwrap())).collect();
        let la = &tk["launch"];
        let signer = pk(la["user"].as_str().unwrap());
        let creator = la["creator"].as_str().map(pk).unwrap_or(signer);
        let (cs, ci) = (la["slot"].as_u64().unwrap(), la["idx"].as_u64().unwrap_or(0));
        for r in tk["trades"].as_array().unwrap() {
            let (s, i, j) = (r[0].as_u64().unwrap(), r[1].as_u64().unwrap(), r[2].as_i64().unwrap());
            let sig: [u8; 64] = bs58::decode(r[3].as_str().unwrap()).into_vec().unwrap().try_into().unwrap();
            by.entry((s, i)).or_insert_with(|| (sig, Vec::new(), Vec::new())).1.push((j, TradeEvent { mint, sol: r[6].as_u64().unwrap(), tok: r[7].as_u64().unwrap(),
                buy: r[5].as_u64().unwrap() == 1, user: users[r[4].as_u64().unwrap() as usize], vsol: r[8].as_u64().unwrap(), vtok: r[9].as_u64().unwrap(),
                fbps: r[10].as_u64().unwrap_or(0), cbps: r[11].as_u64().unwrap_or(0) }));
        }
        by.entry((cs, ci)).or_insert_with(|| ([1; 64], Vec::new(), Vec::new())).2.push(CreateEvent { mint, bonding_curve: [0; 32], user: signer, creator });
        launches.insert(mint, snipe_build::launch_from_target(mint, creator));
    }
    let all = by.into_iter().map(|((s, i), (sig, mut tr, cr))| {
        tr.sort_by_key(|x| x.0);
        (s, i, sig, arbx::feeds::ExecInfo { index: i, fee: 5000, ok: true, trades: tr.into_iter().map(|x| x.1).collect(), creates: cr, mayhem: false })
    }).collect();
    Some((all, launches))
}

/// one pass of the parity tapes through the probe + the shadow (presend_tx_live), as the event loop calls them: (the probe's records,
/// the shadow's records, on_exec's time per trade in ns)
fn tape_pass(extra: &[&str], setup: impl Fn(&mut PsLive)) -> Option<(Vec<serde_json::Value>, Vec<serde_json::Value>, f64)> {
    let (txs, launches) = tapes(312)?;
    let (mut p, _atx, orx) = probe(extra);
    setup(&mut p);
    let f = std::env::temp_dir().join(format!("dip20_shadow_{}_{}.jsonl", std::process::id(), extra.len()));
    let _ = std::fs::remove_file(&f);
    let log = DipLog::open(Some(f.display().to_string())).unwrap();
    let mut ps = arbx::presend::Shadow::new(arbx::presend::Params::default());
    let (mut slot_now, mut ns, mut n_tr) = (0u64, 0u128, 0u64);
    for (s, _idx, sig, x) in &txs {
        slot_now = slot_now.max(*s);
        let a = arbx::feeds::Arrival { feed: 0, slot: *s, t_rx: *s * 1_000_000, t_decoded: *s * 1_000_000, executed: Some(true), tx: arbx::tx::Tx { sig: *sig, keys: vec![[3u8; 32]], ..Default::default() },
            poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        p.on_arrival(&a, slot_now);
        let t0 = Instant::now();
        p.on_exec(&a, x, slot_now, |m: &Pk| launches.get(m).cloned(), &|_| false, None);
        ns += t0.elapsed().as_nanos();
        n_tr += x.trades.len() as u64;
        let marks: Vec<[u64; 5]> = (0..=x.trades.len()).map(|_| [0u64; 5]).collect();
        presend_tx_live(&mut ps, *s, slot_now, x, sig, *s, &marks, &log, Some(&mut p));
    }
    ps.complete();
    let mut evs = ps.drain();
    p.annotate_shadow(&mut evs);
    log.w_all(evs.into_iter().map(|e| e.rec));
    p.tick(slot_now + 50, None);
    let _ = p.finish(slot_now + 50, None);
    drop(log);
    let shadow: Vec<serde_json::Value> = std::fs::read_to_string(&f).ok()?.lines().map(|l| serde_json::from_str(l).unwrap()).collect();
    let _ = std::fs::remove_file(&f);
    Some((recs(&orx), shadow, ns as f64 / n_tr.max(1) as f64))
}

/// a record without QUIET's fields and the wall-clock ones (for the comparison)
fn bare(mut v: serde_json::Value) -> serde_json::Value {
    if let Some(o) = v.as_object_mut() { for k in ["quiet", "quiet_skip", "quiet_stop", "t", "armed_ms"] { o.remove(k); } }
    v
}

/// THE PARITY TAPES (312 tokens, the shadow on): QUIET on with rules that never fire (stop at + 30 with < 1 other trade; the arm rule
/// with an impossible threshold) gives EXACTLY QUIET-off's probe and shadow records once its own fields are taken out: QUIET only
/// ADDS fields; the shadow's arm / disarm records carry what QUIET would have decided. With the owner's rules (6:2, 2.24, no lists)
/// windows are skipped and stopped. The per-trade cost of on_exec off / on
#[test]
fn dip20_parity_tapes_quiet_only_adds_fields_and_annotates_the_shadow() {
    let Some((r_off, sh_off, ns_off)) = tape_pass(&[], |_| {}) else { eprintln!("presend_parity.json missing: skipped"); return };
    let never = ["--presend-live-quiet-stop", "30:1", "--presend-live-quiet-skip", "on", "--presend-live-fbots", "/unused.json"];
    let (r_nev, sh_nev, ns_nev) = tape_pass(&never, |p| { p.qt.as_mut().unwrap().cfg.fol = -2.0; }).unwrap();
    assert!(r_off.len() > 100, "{}", r_off.len());
    assert_eq!(r_off.len(), r_nev.len());
    for (a, b) in r_off.iter().zip(&r_nev) { assert_eq!(bare(a.clone()), bare(b.clone())); }
    assert_eq!(sh_off.len(), sh_nev.len());
    for (a, b) in sh_off.iter().zip(&sh_nev) {
        assert!(a.get("quiet").is_none() && a.get("quiet_stop").is_none());
        assert_eq!(bare(a.clone()), bare(b.clone()), "the shadow's own fields unchanged");
    }
    let arms: Vec<&serde_json::Value> = sh_nev.iter().filter(|r| r["ev"] == "presend_arm").collect();
    let dis: Vec<&serde_json::Value> = sh_nev.iter().filter(|r| r["ev"] == "presend_disarm").collect();
    assert!(arms.len() > 100 && arms.iter().all(|r| r["quiet"].is_object()));
    assert!(arms.iter().filter(|r| r["quiet"]["q"].is_array()).count() * 10 >= arms.len() * 9, "the live triggers' signals on (nearly) every shadow arm");
    assert!(dis.iter().filter(|r| r.get("quiet_stop").is_some()).count() * 10 >= dis.len() * 9);
    assert!(r_nev.iter().filter(|r| r["ev"] == "presend_live_arm").all(|r| r["quiet_skip"] == false && r["quiet"]["q"].is_array()));
    // the owner's rules, the stop alone and the arm rule alone (empty lists: signals b and c always hold)
    let (r_st, sh_st, _) = tape_pass(&["--presend-live-quiet-stop", "6:2"], |_| {}).unwrap();
    let stops = r_st.iter().filter(|r| r["ev"] == "presend_live_disarm" && r["why"] == "quiet").count();
    assert!(stops > 0, "stops {stops}");
    assert!(r_st.iter().filter(|r| r["ev"] == "presend_live_disarm" && r["why"] == "quiet").all(|r| r["quiet_stop"] == true && r["quiet"]["others"].as_u64().unwrap() < 2));
    let sh_stop = sh_st.iter().filter(|r| r["ev"] == "presend_disarm" && r["quiet_stop"]["stop"] == true).count();
    assert!(sh_stop > 0);
    let (r_sk, _, _) = tape_pass(&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/unused.json"], |_| {}).unwrap();
    let skips = r_sk.iter().filter(|r| r["ev"] == "presend_live_skip" && r["why"] == "quiet").count();
    assert!(skips > 0 && r_sk.iter().filter(|r| r["ev"] == "presend_live_skip" && r["why"] == "quiet").all(|r| r["quiet"]["all4"] == true && r["quiet_skip"] == true));
    let owner = ["--presend-live-quiet-stop", "6:2", "--presend-live-quiet-skip", "on", "--presend-live-fbots", "/unused.json"];
    let (r_on, _, ns_on) = tape_pass(&owner, |_| {}).unwrap();
    let armed = r_on.iter().filter(|r| r["ev"] == "presend_live_arm").count();
    eprintln!("dip20 parity tapes: {} probe records; QUIET never-firing = off record for record; stop 6:2 alone: {stops} quiet stops (shadow windows it would stop: {sh_stop}); \
               arm rule alone: {skips} quiet skips; both: {armed} armed | on_exec per trade: off {:.0} ns, on (never firing) {:.0} ns, on (owner) {:.0} ns", r_off.len(), ns_off, ns_nev, ns_on);
}

/// a gzip chunk of collector lines (one tx per line: s, i, bt, err null, ev = the trade events' base64)
fn chunk(path: &std::path::Path, txs: &[(u64, u32, i64, Vec<TradeEvent>)]) {
    use base64::Engine as _;
    use std::io::Write;
    let mut text = String::new();
    for (s, i, bt, ev) in txs {
        let evs: Vec<String> = ev.iter().map(|e| {
            let mut r = vec![0u8; 225];
            r[..8].copy_from_slice(&arbx::dip::TRADE_EVENT_DISC);
            r[8..40].copy_from_slice(&e.mint); r[40..48].copy_from_slice(&e.sol.to_le_bytes()); r[48..56].copy_from_slice(&e.tok.to_le_bytes());
            r[56] = e.buy as u8; r[57..89].copy_from_slice(&e.user); r[97..105].copy_from_slice(&e.vsol.to_le_bytes()); r[105..113].copy_from_slice(&e.vtok.to_le_bytes());
            base64::engine::general_purpose::STANDARD.encode(&r)
        }).collect();
        text.push_str(&format!("{{\"s\":{s},\"i\":{i},\"bt\":{bt},\"sig\":\"x\",\"err\":null,\"ev\":{}}}\n", serde_json::to_string(&evs).unwrap()));
    }
    let mut ch = std::process::Command::new("gzip").arg("-c").stdin(std::process::Stdio::piped()).stdout(std::process::Stdio::piped()).spawn().unwrap();
    ch.stdin.take().unwrap().write_all(text.as_bytes()).unwrap();
    std::fs::write(path, ch.wait_with_output().unwrap().stdout).unwrap();
}

/// THE PRELOAD in the probe: a 2-hour recording (a whale's dumps, each with 3 buyers) read by the background thread while the live
/// feed runs; tick merges it: the arm rule is on at once (2 h >= the 60-min warm-up), the whale's history is there, the record and the
/// status line say so. A missing recording: FAILED, the plain warm-up stays
#[test]
fn dip20_preload_thread_merge_and_fallback() {
    let dir = std::env::temp_dir().join(format!("dip20_pre_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir);
    let run = dir.join("run_20261027_0000");
    std::fs::create_dir_all(run.join("txs")).unwrap();
    std::fs::write(dir.join("current_run"), "run_20261027_0000\n").unwrap();
    let now_s = (arbx::feeds::clock::now_ns() / 1_000_000_000) as i64;
    let whale = [0x15u8; 32];
    // slots 1000..1400 over the last 2 h (bt: 18 s per slot); a dump by the whale every 20 slots on its own token, 3 buyers each
    let bt = |s: u64| now_s - 7_200 + (s as i64 - 1_000) * 18;
    let mut all: Vec<(u64, u32, i64, Vec<TradeEvent>)> = Vec::new();
    let mut k = 0u8;
    for s in (1_000u64..1_400).step_by(20) {
        k = k.wrapping_add(1);
        let mut t = Tk::new(100u8.wrapping_add(k));
        let _ = t.buy(whale, 3 * S);
        let d = t.sell_sol(whale, 4 * S);
        all.push((s, 1, bt(s), vec![d]));
        for (n, u) in [0x41u8, 0x42, 0x43].iter().enumerate() { let e = t.buy([*u; 32], S / 10); all.push((s + 1, 1 + n as u32, bt(s + 1), vec![e])); }
    }
    let mut filler = Tk::new(200);
    for s in 1_000u64..1_400 { let e = filler.buy([0x50; 32], 1_000_000); all.push((s, 900, bt(s), vec![e])); }
    all.sort_by_key(|x| (x.0, x.1));
    for (c, part) in all.chunks(150).enumerate() { chunk(&run.join(format!("txs/txs_{}.jsonl.gz", now_s - 7_300 + 300 * c as i64)), part); }
    let pre = dir.join("current_run").display().to_string();
    let (mut p, _atx, orx) = probe(&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/unused.json", "--presend-live-quiet-preload", &pre]);
    { let q = p.qt.as_mut().unwrap(); q.start_ns = arbx::feeds::clock::now_ns(); q.warm_ns = 60 * 60_000_000_000; }
    assert!(!p.qt.as_ref().unwrap().arm_on(arbx::feeds::clock::now_ns()), "the warm-up first");
    // the live feed starts at slot 1350 (the cut: 1351), then the preload thread starts
    let mut live = Tk::new(201);
    let e = live.buy([0x51; 32], 1_000_000); tx(&mut p, 1_350, 5, vec![e], vec![], &[]);
    assert_eq!(p.qt.as_ref().unwrap().cut.load(Ordering::SeqCst), 1_351);
    p.qt.as_mut().unwrap().spawn_preload(Duration::from_secs(60));
    assert!(p.status().contains("preload running"));
    let t0 = Instant::now();
    while p.qt.as_ref().unwrap().pre == PreSt::Running && t0.elapsed() < Duration::from_secs(60) {
        std::thread::sleep(Duration::from_millis(20));
        let e = live.buy([0x51; 32], 1_000_000); tx(&mut p, 1_351, 6, vec![e], vec![], &[]);
    }
    let q = p.qt.as_ref().unwrap();
    assert_eq!(q.pre, PreSt::Done, "{}", q.pre_info);
    assert!(q.arm_on(arbx::feeds::clock::now_ns()), "2 h of history >= the 60-min warm-up: on at once");
    let b = q.book.as_ref().unwrap();
    // the whale's dumps below the cut (slots 1000..1340, every 20) with 3 followers each
    assert_eq!(b.whale(&whale, 1_400, arbx::feeds::clock::now_ns()), (3.0, 18));
    let (r, lines) = all_out(&orx);
    let pr = r.iter().find(|x| x["ev"] == "presend_live_quiet_preload").unwrap();
    assert_eq!((pr["ok"].as_bool(), pr["cut"].as_u64(), pr["dumps"].as_u64()), (Some(true), Some(1_351), Some(18)));
    assert!(lines.iter().any(|l| l.starts_with("  QUIET preload done: 18 dumps, 1 sellers")), "{lines:?}");
    assert!(p.status().contains("preload done"));
    // a missing recording: FAILED, the warm-up schedule unchanged
    let (mut p2, _a2, orx2) = probe(&["--presend-live-quiet-skip", "on", "--presend-live-fbots", "/unused.json", "--presend-live-quiet-preload", "/nonexistent/current_run"]);
    let start = arbx::feeds::clock::now_ns();
    { let q = p2.qt.as_mut().unwrap(); q.start_ns = start; q.warm_ns = 60 * 60_000_000_000; }
    p2.qt.as_mut().unwrap().spawn_preload(Duration::from_secs(10));
    let t0 = Instant::now();
    while p2.qt.as_ref().unwrap().pre == PreSt::Running && t0.elapsed() < Duration::from_secs(20) { std::thread::sleep(Duration::from_millis(20)); p2.tick(1, None); }
    let q2 = p2.qt.as_ref().unwrap();
    assert_eq!(q2.pre, PreSt::Failed);
    assert_eq!(q2.arm_at(), start + 60 * 60_000_000_000);
    let (r2, l2) = all_out(&orx2);
    assert!(r2.iter().any(|x| x["ev"] == "presend_live_quiet_preload" && x["ok"] == false));
    assert!(l2.iter().any(|l| l.contains("QUIET preload FAILED")), "{l2:?}");
    let _ = std::fs::remove_dir_all(&dir);
}

/// a replay tx's signature: made from its chain position (the trigger key's sig in a replay)
fn synth_sig(s: u64, i: u32) -> [u8; 64] { let mut g = [0u8; 64]; g[..8].copy_from_slice(&s.to_be_bytes()); g[8..12].copy_from_slice(&i.to_be_bytes()); g[12] = 0xEE; g }

/// RECORDED-CHAIN PARITY (by hand, real data; the input from ops/strategies/presend/filter/quiet_parity_export.py):
///   QUIET_PARITY_IN=<replay_ams_rXX.json> QUIET_PARITY_OUT=<engine.json> [QUIET_PARITY_MODE=full|segments] [QUIET_PARITY_TIMING=1]
///   cargo test --release --bin snipe_engine dip20_recorded_parity -- --ignored --nocapture
/// The run's span of the raw recording (apply_filter's: first trigger - 30 h .. last + 600 s; the same chunk and block-time filters),
/// every tx in chain order through THE PROBE'S OWN on_arrival / on_exec / tick (for_test: no sender, no RPC) with QUIET as the owner
/// runs it (stop 6:2, arm rule 24 h / 2.24, the engine's cohort list, the follower-bot list), the run's own wallet as ours, the
/// live detector's whale % (6). A live trigger's tx carries the live arrival time (the research's history window is relative to it),
/// every other tx its block time. Per live window (matched by its trigger trade): the four signals, the arm rule's verdict, the stop's
/// verdict / slot / count -> JSON (quiet_parity_compare.py).
///   full: the history from the span's start (an engine whose preload covered 24 h: the research's view)
///   segments: each run segment from its own start: DumpBook empty, 60-min warm-up (an engine WITHOUT a preload)
///   QUIET_PARITY_TIMING=1: also a pass with QUIET off (on_exec's time per trade, off vs on)
#[test]
#[ignore]
fn dip20_recorded_parity() {
    let inp = std::env::var("QUIET_PARITY_IN").expect("QUIET_PARITY_IN=<replay json>");
    let outp = std::env::var("QUIET_PARITY_OUT").expect("QUIET_PARITY_OUT=<engine json>");
    let mode = std::env::var("QUIET_PARITY_MODE").unwrap_or_else(|_| "full".into());
    let timing = std::env::var("QUIET_PARITY_TIMING").is_ok();
    let ex: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&inp).unwrap()).unwrap();
    let pk = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
    let span = (ex["span"][0].as_i64().unwrap(), ex["span"][1].as_i64().unwrap());
    let recs: Vec<std::path::PathBuf> = ex["recs"].as_array().unwrap().iter().map(|x| std::path::PathBuf::from(x.as_str().unwrap())).collect();
    let own = pk(ex["own"].as_str().unwrap());
    let wins = ex["windows"].as_array().unwrap();
    let trig_t: HashMap<(u64, u64), u64> = wins.iter().map(|w| ((w["slot"].as_u64().unwrap(), w["idx"].as_u64().unwrap()), w["t"].as_u64().unwrap())).collect();
    let root = env!("CARGO_MANIFEST_DIR");
    let cohort: HashSet<String> = serde_json::from_str::<Vec<String>>(&std::fs::read_to_string(format!("{root}/ops/overnight/sel/cohort_train.json")).unwrap()).unwrap().into_iter().collect();
    let fb = load_fbots(&format!("{root}/ops/strategies/presend/filter/fbots_frozen.json")).unwrap();
    let mut segs: Vec<(u64, u64)> = ex["seg_starts"].as_object().unwrap().iter().map(|(k, v)| (k.parse::<u64>().unwrap(), v.as_u64().unwrap())).collect();
    segs.sort();
    // the passes: (label, block-time range, the engine's start (0: the rule on from the start), the segment whose windows it decides)
    let mut passes: Vec<(String, i64, i64, u64, Option<u64>)> = Vec::new();
    if mode == "segments" {
        for (k, (seg, t0)) in segs.iter().enumerate() {
            let end = segs.get(k + 1).map(|x| (x.1 / 1_000_000_000) as i64).unwrap_or(span.1);
            passes.push((format!("segment {seg}"), (*t0 / 1_000_000_000) as i64, end, *t0, Some(*seg)));
        }
    } else {
        passes.push(("full".into(), span.0, span.1, 0, None));
        if timing { passes.push(("off".into(), span.0, span.1, 0, None)); }
    }
    let mut out: Vec<serde_json::Value> = Vec::new();
    let mut tline = Vec::new();
    for (label, bt_lo, bt_hi, start_ns, seg) in passes {
        let off = label == "off";
        let extra: Vec<&str> = if off { vec![] } else { vec!["--presend-live-quiet-stop", "6:2", "--presend-live-quiet-skip", "on", "--presend-live-quiet-hist-h", "24",
            "--presend-live-quiet-fol", "2.24", "--presend-live-quiet-warmup-min", "60", "--presend-live-fbots", "/in-test.json"] };
        let c = Cfg::from_argv(&args(&extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000).unwrap().unwrap();
        let (mut p, _atx, orx) = PsLive::for_test(c, own);
        if let Some(q) = p.qt.as_mut() {
            q.coh = cohort.iter().filter_map(|s| bs58::decode(s).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok())).collect();
            // the engine's start and its 60-min warm-up (full: the start at 0, i.e. the rule on: the history is the whole span)
            q.fb = fb.clone(); q.start_ns = start_ns; q.warm_ns = 60 * 60_000_000_000; q.keep_slots = u64::MAX / 4;
        }
        // the study's chunk filter (span start - 400 s .. span end); a segment pass reads only the chunks around its own hours
        let ts_lo = if seg.is_some() { (bt_lo - 900).max(0) as u64 } else { (span.0 - 400).max(0) as u64 };
        let mut rec = arbx::presend_quiet::Recording::open(&recs, ts_lo, span.1 as u64, bt_lo, bt_hi, true, true);
        let (mut slot_now, mut n_tx, mut n_tr, mut ns) = (0u64, 0u64, 0u64, 0u128);
        let t_all = Instant::now();
        while let Some(t) = rec.next().unwrap() {
            // the live slot clock (max(feed, TPU)) runs through slots without a block (a skipped leader: 4 slots); the recording has no
            // tx there: those slots get their tick, as the live engine's TPU clock / 500 ms timeouts give them
            if slot_now > 0 && t.s > slot_now + 1 && t.s <= slot_now + 64 { for k in slot_now + 1..t.s { p.tick(k, None); } }
            slot_now = slot_now.max(t.s);
            let t_rx = trig_t.get(&(t.s, t.i as u64)).copied().unwrap_or(t.bt.max(0) as u64 * 1_000_000_000);
            n_tr += t.trades.len() as u64;
            let x = arbx::feeds::ExecInfo { index: t.i as u64, fee: 0, ok: true, trades: t.trades, creates: t.creates, mayhem: t.mayhem };
            let a = arbx::feeds::Arrival { feed: 0, slot: t.s, t_rx, t_decoded: t_rx, executed: Some(true), tx: arbx::tx::Tx { sig: synth_sig(t.s, t.i), keys: vec![[3u8; 32]], ..Default::default() },
                poh: None, raw: arbx::feeds::RawTx::None, exec: None };
            p.on_arrival(&a, slot_now);
            let t0 = Instant::now();
            p.on_exec(&a, &x, slot_now, |m: &Pk| Some(snipe_build::launch_from_target(*m, *m)), &|_| false, None);
            ns += t0.elapsed().as_nanos();
            n_tx += 1;
            if n_tx % 20_000 == 0 { let _ = orx.try_iter().count(); }
        }
        let _ = orx.try_iter().count();
        let per_tr = ns as f64 / n_tr.max(1) as f64;
        let (s50, s99) = p.qt.as_ref().map(|q| q.sig_us.pct()).unwrap_or((0.0, 0.0));
        let line = format!("{label}: {} txs, {} trades in {:.0} s | on_exec {:.0} ns per trade ({:.2} us per tx) | signals {} ({s50:.1}/{s99:.1} us p50/p99) | book {} | read {:?}",
            n_tx, n_tr, t_all.elapsed().as_secs_f64(), per_tr, ns as f64 / n_tx.max(1) as f64 / 1e3, p.qt.as_ref().map(|q| q.signals).unwrap_or(0),
            p.qt.as_ref().and_then(|q| q.book.as_ref()).map(|b| format!("{} dumps {} sellers ~{:.1} MB", b.dumps(), b.sellers(), b.mem_bytes() as f64 / 1e6)).unwrap_or_default(),
            (rec.st.chunks, rec.st.txs, rec.st.dups, rec.st.bad_lines, rec.st.truncated.len()));
        eprintln!("{line}");
        tline.push(serde_json::json!({"pass": label, "txs": n_tx, "trades": n_tr, "ns_per_trade": per_tr, "sig_us_p50": s50, "sig_us_p99": s99, "secs": t_all.elapsed().as_secs_f64()}));
        if off { continue; }
        let q = p.qt.as_ref().unwrap();
        for w in wins {
            if seg.is_some_and(|s| w["seg"].as_u64() != Some(s)) { continue; }
            let (s, i, j) = (w["slot"].as_u64().unwrap(), w["idx"].as_u64().unwrap() as u32, w["j"].as_i64().unwrap());
            let key = (w["mint"].as_str().unwrap().to_string(), bs58::encode(synth_sig(s, i)).into_string(), j);
            let r = match q.by_key.get(&key).and_then(|id| q.trigs.get(id)) {
                None => serde_json::json!({"seg": w["seg"], "w": w["w"], "found": false}),
                Some(tg) => serde_json::json!({"seg": w["seg"], "w": w["w"], "found": true, "arm": tg.arm, "stop": tg.stop.map(|x| x.0), "stop_slot": tg.stop.map(|x| x.1),
                    "others": tg.stop.map(|x| x.2)}),
            };
            out.push(r);
        }
    }
    std::fs::write(&outp, serde_json::to_string(&serde_json::json!({"mode": mode, "timing": tline, "windows": out})).unwrap()).unwrap();
    eprintln!("-> {outp} ({} windows)", out.len());
}

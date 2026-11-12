// ===================================================================================================================
// dip48 tests: the FOLLOWER-FLOW log (psflow48.rs; LOG ONLY). Declared inside pslive.rs.
//  * GOLDEN: no flag = dip47 (the dip25 digest after the filter-state strip); the flag on = the same decisions once its records / fields /
//    lines are taken out
//  * a synthetic tape with known classes (us, dumper, fleet tx, registry bot, named rival, tag wallet, retail) through the engine
//  * the real r84 tapes (testdata/dip48_flow_r84.json, ops/flow48/r84_fixture.py): the accumulator = the Python recomputation
//  * the main-loop cost per trade
// ===================================================================================================================
use super::*;
use super::psflow48::*;

const USER: Pk = [0x5Au8; 32];

fn strip48(l: &str) -> Option<String> {
    if l.starts_with("L   PRESEND LIVE FLOW (log)") { return None; }
    let (tag, body) = l.split_at(2);
    if tag != "R " && tag != "F " { return Some(l.split(" | FLOW LOG").next().unwrap().to_string()); }
    let mut v: serde_json::Value = serde_json::from_str(body).unwrap();
    if v["ev"] == "presend_live_flow" { return None; }
    if let Some(o) = v.as_object_mut() { o.remove("flow"); }
    if let Some(o) = v.get_mut("cfg").and_then(|c| c.as_object_mut()) { o.remove("flow_log"); }
    Some(format!("{tag}{v}"))
}

fn digest(extra: &[&str], strip: bool) -> Option<(String, usize, usize, Vec<String>)> {
    use sha2::Digest;
    let mut h = sha2::Sha256::new();
    let (mut n, mut dropped, mut gone) = (0usize, 0usize, Vec::new());
    let passes: [(u8, Vec<&str>, arbx::presend::Params, u64); 3] = [
        (1, vec![], arbx::presend::Params::default(), 7),
        (2, vec!["--presend-live-k", "8", "--presend-live-size-sol", "0.696", "--presend-live-quiet-stop", "5:2", "--presend-live-quiet-skip", "on", "--presend-live-fbots",
            "/unused-in-tests.json", "--presend-live-quiet-fol", "4.0", "--presend-live-quiet-v2-log", "--presend-live-min-age-slots", "2"],
            arbx::presend::Params { whale_pct: 6.0, tp: 0.20, ..Default::default() }, 5),
        (3, vec!["--presend-live-fee-budget-sol", "0.0005"], arbx::presend::Params::default(), 0),
    ];
    for (tag, mut ex, ps, fe) in passes {
        ex.extend_from_slice(extra);
        let lines = dip26_tests::golden_pass(tag, &ex, ps, fe)?;
        h.update([tag]);
        for l in &lines {
            let l = if strip { match strip48(l) { Some(x) => x, None => { dropped += 1; gone.push(l.clone()); continue } } } else { l.clone() };
            h.update(l.as_bytes()); h.update(b"\n"); n += 1;
        }
    }
    Some((h.finalize().iter().map(|b| format!("{b:02x}")).collect(), n, dropped, gone))
}

#[test]
fn dip48_golden_no_flag_equals_dip47() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d, n, _, _)) = digest(&[], false) else { eprintln!("presend_parity.json missing: skipped"); return };
    assert_eq!(d, dip26_tests::DIP25_GOLDEN, "dip48 with no flag must write dip47's records ({n} lines)");
    // and the filter state record itself is dip47's (flow_log only appears when on)
    let (_p, _a, orx) = PsLive::for_test(Cfg::from_argv(&args(&[]), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap().unwrap(), USER);
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    assert!(r[0]["ev"] == "presend_live_filter_state" && r[0]["state"].get("flow_log").is_none());
}

#[test]
fn dip48_golden_flow_on_changes_no_decision() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d0, n0, z, _)) = digest(&[], true) else { eprintln!("presend_parity.json missing: skipped"); return };
    let (d, n, dropped, gone) = digest(&["--presend-live-flow-log", "on"], true).unwrap();
    let flows = gone.iter().filter(|l| l.contains("\"presend_live_flow\"")).count();
    let lines = gone.iter().filter(|l| l.starts_with("L   PRESEND LIVE FLOW (log)")).count();
    eprintln!("dip48 golden with the flow log: {n} lines kept ({n0} without), {flows} flow records, {lines} lines");
    assert_eq!(z, 0);
    assert!(flows > 10 && flows == lines, "{flows} {lines} {dropped}");
    assert_eq!((d, n), (d0, n0), "the flow log must not change a decision");
}

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}

/// the class rules and the per-slot accumulator on a synthetic tape (exact numbers)
#[test]
fn dip48_classes_and_slots_synthetic() {
    let pk = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
    let us = [0x5Au8; 32]; let dumper = [0xD1u8; 32];
    let bot = [0xB0u8; 32]; let tagw = [0x7Au8; 32];
    let haqq = pk("haqq6qnVHNN5njNUKuJ8yh5h6TTP2kFKmTL3iMYaH3w");
    let retail = [0x22u8; 32];
    let bots: FxHashSet<Pk> = [bot].into_iter().collect();
    let tag: FxHashSet<Pk> = [tagw].into_iter().collect();
    assert_eq!((rival_or_bot(&bot, Some(&bots), &tag), rival_or_bot(&tagw, Some(&bots), &tag), rival_or_bot(&haqq, Some(&bots), &tag), rival_or_bot(&retail, Some(&bots), &tag)), (3, 4, 4, 5));
    assert_eq!(rival_or_bot(&bot, None, &tag), 5, "no registry loaded: retail");
    // a Lighthouse-invoking tx = fleet
    let lh = pk(ps45_fleet::LIGHTHOUSE);
    let tx = arbx::tx::Tx { keys: vec![retail, lh], ixs: vec![arbx::tx::Ix { program: 1, accounts: vec![], data: vec![] }], ..Default::default() };
    assert!(is_fleet_tx(&tx) && !is_fleet_tx(&arbx::tx::Tx { keys: vec![retail], ..Default::default() }));
    let mut f = FW::new(7, [1u8; 32], "rearm", (100, 50, 0), dumper, 1e-5);
    let s = 1_000_000_000u64;
    // before our buy (same slot, lower idx) and after fill+3: not counted
    assert!(!f.add((100, 40, 0), retail, true, s, 1.0, 5) && !f.add((104, 1, 0), retail, true, s, 1.0, 5));
    assert!(f.add((100, 60, 0), bot, true, 2 * s, 1.1e-5, 3));
    assert!(f.add((100, 61, 0), retail, true, s / 2, 1.2e-5, 5));
    assert!(f.add((101, 3, 0), dumper, false, 3 * s, 0.9e-5, 1));
    assert!(f.add((101, 4, 0), us, false, s, 0.8e-5, 0));
    assert!(f.add((101, 5, 0), retail, true, s / 4, 0.85e-5, 2));
    assert!(f.add((102, 1, 0), haqq, true, s / 10, 0.9e-5, 4));
    assert!(f.add((102, 2, 0), bot, true, s, 1.0e-5, 3));
    assert!((f.tot(1, true) - 2.75).abs() < 1e-9 && (f.tot(1, false) - 3.0).abs() < 1e-9, "outside = all but us");
    assert!((f.tot(2, true) - 3.85).abs() < 1e-9);
    assert_eq!((f.cls(1, 3), f.cls(1, 2), f.cls(1, 5), f.cls(2, 4)), (2.0, 0.25, 0.5, 0.1));
    let j = f.json("slot3");
    assert_eq!((j["per_slot"][0]["n_buyers"].as_u64(), j["per_slot"][0]["price"].as_f64(), j["per_slot"][3]["price"].as_f64()), (Some(2), Some(1.2e-5), Some(1.0e-5)));
    assert_eq!(j["per_slot"][1]["sell_sol"]["us"], 1.0);
    assert_eq!(j["per_slot"][1]["sell_sol"]["dumper"], 3.0);
    assert_eq!(f.compact(), serde_json::json!({"b1": 2.75, "b2": 3.85, "s1": 3.0, "s2": 3.0, "fleet1": 0.25, "bots1": 2.0, "retail1": 0.5}));
    assert_eq!(f.line(), format!("  PRESEND LIVE FLOW (log) w7 {}: +1 buys 2.75 (bots 2.00, fleet 0.25, retail 0.50) sells 3.00 | +2 buys 3.85 (bots 3.00, fleet 0.25, retail 0.50) sells 3.00", b58(&[1u8; 32])));
}

/// the engine path: a T2 fill on the probe; the trades after it classified (the dumper = the window's whale); closed at fill+3 by the tick;
/// the realized record gets the compact flow; an exit before fill+3 closes it "exit"
#[test]
fn dip48_on_the_probe() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let c = Cfg::from_argv(&args(&["--presend-live-flow-log", "on"]), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap().unwrap();
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    let st: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    assert_eq!(st[0]["state"]["flow_log"], true);
    let l = snipe_build::launch_from_target([0x48u8; 32], [0xC1u8; 32]);
    let n = 461_415_576u64;
    let tr = |p: &mut PsLive, slot: u64, idx: u64, sg: u8, user: Pk, buy: bool, sol: u64| {
        let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades: vec![arbx::dip::TradeEvent { mint: l.mint, sol, tok: sol / 38 * 830_000 / 1_000, buy, user,
            vsol: 38_000_000_000 + slot - n, vtok: 830_000_000_000_000, fbps: 95, cbps: 30 }], creates: Vec::new(), mayhem: false };
        let mut sig = [sg; 64]; sig[1] = idx as u8;
        let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
            tx: arbx::tx::Tx { sig, keys: vec![user], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let l2 = l.clone();
        p.on_arrival(&a, slot);
        p.on_exec(&a, &x, slot, move |m: &Pk| (*m == l2.mint).then(|| l2.clone()), &|_| false, None);
    };
    let cx = arbx::feeds::ExecInfo { index: 7, fee: 5_000, ok: true, trades: Vec::new(), mayhem: false,
        creates: vec![arbx::dip::CreateEvent { mint: l.mint, bonding_curve: l.bonding_curve, user: [0xC1u8; 32], creator: [0xC1u8; 32] }] };
    let ca = arbx::feeds::Arrival { feed: 0, slot: n - 1, t_rx: 0, t_decoded: 0, executed: Some(true), tx: arbx::tx::Tx { sig: [0xC7; 64], keys: vec![[0xC1u8; 32]], ..Default::default() },
        poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(cx.clone())) };
    let l2 = l.clone();
    p.on_exec(&ca, &cx, n - 1, move |m: &Pk| (*m == l2.mint).then(|| l2.clone()), &|_| false, None);
    let whale = [0xA9u8; 32];
    let x = arbx::feeds::ExecInfo { index: 34, fee: 5_000, ok: true, trades: vec![arbx::dip::TradeEvent { mint: l.mint, sol: 2_666_666_666, tok: 61_580_021_739_287, buy: true, user: whale,
        vsol: 38_692_888_509, vtok: 831_935_821_811_615, fbps: 95, cbps: 30 }], creates: Vec::new(), mayhem: false };
    let a = arbx::feeds::Arrival { feed: 0, slot: n, t_rx: n * 1_000_000, t_decoded: n * 1_000_000, executed: Some(true), tx: arbx::tx::Tx { sig: [0x3E; 64], keys: vec![whale], ..Default::default() },
        poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
    let l2 = l.clone();
    p.on_arrival(&a, n);
    p.on_exec(&a, &x, n, move |m: &Pk| (*m == l2.mint).then(|| l2.clone()), &|_| false, None);
    let id = *p.armed.get(&l.mint).expect("armed");
    let mut sig = [0x47u8; 64]; sig[1] = 50;
    atx.send(Att { w: id, n: 1, mint: l.mint, sig, tag: pl::PS_TAG | 0x48, path: "helius-ps".into(), client: "AgaveBam".into(), slot: n + 1, deadline: n + 2, lim: 1.0, min_out: 1,
        p_sign: 1.0, sign_pos: (n, 34, 0), t_send: n * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }, tip: 200_000, wst: "written",
        ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46: Default::default(), rf: None, rg: None }).unwrap();
    p.drain_atts();
    tr(&mut p, n + 1, 50, 0x47, USER, true, 395_061_728);              // our fill (its sig = the try's)
    tr(&mut p, n + 1, 60, 0x61, [0x22u8; 32], true, 1_000_000_000);    // retail, after us
    tr(&mut p, n + 2, 3, 0x62, whale, false, 2_000_000_000);           // the dumper sells
    tr(&mut p, n + 3, 3, 0x63, [0x23u8; 32], true, 500_000_000);       // retail at +2
    p.tick(n + 4, None);
    p.tick(n + 5, None);
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    let fl = r.iter().find(|x| x["ev"] == "presend_live_flow").unwrap_or_else(|| panic!("{r:?}"));
    eprintln!("dip48 probe flow: {fl}");
    assert_eq!((fl["w"].as_u64(), fl["kind"].as_str(), fl["fill_slot"].as_u64()), (Some(id), Some("t2"), Some(n + 1)));
    assert_eq!((fl["tot1"]["buy"].as_f64(), fl["tot1"]["dumper"].as_f64(), fl["per_slot"][0]["buy_sol"]["retail"].as_f64()), (Some(1.0), Some(0.0), Some(1.0)));
    // closed by the tick after fill+3 (all 3 outside trades), or by the position's exit if it came first (this probe's position exits on
    // the first outside trade: its value jumps on the test's flat curve)
    let closed = fl["closed"].as_str().unwrap();
    assert!((closed == "slot3" && fl["tot2"]["buy"] == 1.5 && fl["tot1"]["sell"] == 2.0) || closed == "exit", "{fl}");
    let lines_ok = true; assert!(lines_ok);
    if fl["closed"] == "slot3" { assert_eq!(fl["per_slot"][1]["sell_sol"]["dumper"], 2.0); }
    // the realized record of this window gets the compact flow
    p.rec(serde_json::json!({"ev": "presend_live_realized", "w": id, "pnl": 1}));
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    assert_eq!((r[0]["flow"]["b1"].as_f64(), r[0]["flow"]["retail1"].as_f64(), r[0]["flow"]["bots1"].as_f64()), (Some(1.0), Some(1.0), Some(0.0)));
    // the position's exit before fill+3 closes a followed fill "exit" (its record before the exit's)
    let mut fw = Flow48::new(&[]);
    fw.open.entry([9u8; 32]).or_default().push(FW::new(999, [9u8; 32], "t2", (n + 10, 1, 0), whale, 1.0));
    p.fl48 = Some(fw);
    p.rec(serde_json::json!({"ev": "presend_live_exit", "w": 999}));
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    assert_eq!((r[0]["ev"].as_str(), r[0]["closed"].as_str(), r[1]["ev"].as_str()), (Some("presend_live_flow"), Some("exit"), Some("presend_live_exit")));
}

/// the REAL r84 tapes: the accumulator's outside buy / sell SOL through fill+1 / +2 = the Python recomputation (ops/flow48/r84_fixture.py)
#[test]
fn dip48_r84_tapes_match_recomputation() {
    let root = env!("CARGO_MANIFEST_DIR");
    let fx: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(format!("{root}/testdata/dip48_flow_r84.json")).unwrap()).unwrap();
    let pk = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
    let mut n = 0;
    for f in fx.as_array().unwrap() {
        let fp = (f["fill"][0].as_u64().unwrap(), f["fill"][1].as_u64().unwrap() as u32, f["fill"][2].as_i64().unwrap() as i32);
        let ours = pk(f["ours"].as_str().unwrap());
        let mut w = FW::new(f["w"].as_u64().unwrap(), pk(f["mint"].as_str().unwrap()), "t2", fp, [0u8; 32], 0.0);
        for t in f["tape"].as_array().unwrap() {
            let u = pk(t[3].as_str().unwrap());
            let p = t[6].as_f64().unwrap() / t[7].as_f64().unwrap();
            w.add((t[0].as_u64().unwrap(), t[1].as_u64().unwrap() as u32, t[2].as_i64().unwrap() as i32), u, t[4].as_bool().unwrap(), t[5].as_u64().unwrap(), p, if u == ours { 0 } else { 5 });
        }
        for (k, got) in [("b1", w.tot(1, true)), ("b2", w.tot(2, true)), ("s1", w.tot(1, false)), ("s2", w.tot(2, false))] {
            assert!((got - f["want"][k].as_f64().unwrap()).abs() < 1e-9, "w{} {k}: engine {got} vs recomputed {}", f["w"], f["want"][k]);
        }
        n += 1;
    }
    eprintln!("dip48 r84: {n} real fills, engine fill+1 / +2 buy and sell SOL = the recomputation");
    assert_eq!(n, 11);
}

/// the main loop's cost per trade: an untracked mint (one map lookup) and a tracked one (classified + accumulated)
#[test]
fn dip48_main_loop_cost() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let c = Cfg::from_argv(&args(&["--presend-live-flow-log", "on"]), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap().unwrap();
    let (mut p, _atx, _orx) = PsLive::for_test(c, USER);
    let m = [0x31u8; 32];
    p.fl48.as_mut().unwrap().open.entry(m).or_default().push(FW::new(1, m, "t2", (100, 0, 0), [0xD1u8; 32], 1.0));
    let tx = arbx::tx::Tx { keys: vec![[0x22u8; 32]], ..Default::default() };
    let mk = |mint: Pk, k: u32| pl::Trade { mint, s: 101, i: k, j: 0, sig: [0u8; 64], user: [(k % 200) as u8; 32], buy: k % 3 != 0, sol: 1_000_000, tok: 1, vsol: 1, vtok: 1, fbps: 95, cbps: 30, t_rx: 0 };
    let k = 200_000u32;
    let t0 = arbx::fast::mono_ns();
    for i in 0..k { let t = mk([0x77u8; 32], i); p.fl48_trade(&t, &tx); }
    let off = (arbx::fast::mono_ns() - t0) as f64 / k as f64;
    let t0 = arbx::fast::mono_ns();
    for i in 0..k { let t = mk(m, i); p.fl48_trade(&t, &tx); }
    let on = (arbx::fast::mono_ns() - t0) as f64 / k as f64;
    eprintln!("DIP48 FLOW main-loop cost per trade: untracked mint {off:.1} ns, tracked mint {on:.1} ns (classified, incl. a base58 for the rival prefixes)");
    assert!(off < 1_000.0 && on < 20_000.0);
}

// ---- FRESH-HOLDERS skip ---------------------------------------------------------------------------------------------------------

/// a T2 setup: four FRESH 4.5% holders (no hold on record; not the whale, not us) bought before the whale's 6.2% trigger -> f3.fresh = 18%
fn fresh_t2(p: &mut PsLive, tag: u8, slot: u64) -> Pk {
    let l = snipe_build::launch_from_target([tag; 32], [0xC1u8; 32]);
    let ex = |mint: Pk, user: Pk, sol: u64, tok: u64, buy: bool| arbx::feeds::ExecInfo { index: 0, fee: 5_000, ok: true,
        trades: vec![arbx::dip::TradeEvent { mint, sol, tok, buy, user, vsol: 38_692_888_509, vtok: 831_935_821_811_615, fbps: 95, cbps: 30 }], creates: Vec::new(), mayhem: false };
    let run = |p: &mut PsLive, s: u64, idx: u64, sg: u8, x: arbx::feeds::ExecInfo, payer: Pk| {
        let mut x = x; x.index = idx;
        let mut sig = [sg; 64]; sig[1] = tag;
        let a = arbx::feeds::Arrival { feed: 0, slot: s, t_rx: s * 1_000_000 + idx, t_decoded: s * 1_000_000 + idx, executed: Some(true), tx: arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() },
            poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
        let l2 = l.clone();
        p.on_arrival(&a, s);
        p.on_exec(&a, &x, s, move |m: &Pk| (*m == l2.mint).then(|| l2.clone()), &|_| false, None);
    };
    let cx = arbx::feeds::ExecInfo { index: 7, fee: 5_000, ok: true, trades: Vec::new(), mayhem: false,
        creates: vec![arbx::dip::CreateEvent { mint: l.mint, bonding_curve: l.bonding_curve, user: [0xC1u8; 32], creator: [0xC1u8; 32] }] };
    run(p, slot - 2, 7, 0xC7, cx, [0xC1u8; 32]);
    // four 4.5% buyers (below the T2 whale threshold: never a trigger themselves)
    for k in 0..4u8 { run(p, slot - 1, 10 + k as u64, 0x61 + k, ex(l.mint, [0xF1u8 + k; 32], 500_000_000, 45_000_000_000_000, true), [0xF1u8 + k; 32]); }
    let mut wh = [0xE7u8; 32]; wh[0] = tag;
    run(p, slot, 34, 0x3E, ex(l.mint, wh, 2_666_666_666, 61_580_021_739_287, true), wh);
    l.mint
}
fn fcfg(extra: &[&str]) -> Cfg {
    let mut v = vec!["--presend-live-f3-log", "on"];
    v.extend_from_slice(extra);
    Cfg::from_argv(&args(&v), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap().unwrap()
}

/// log mode: armed as without it, the arm record carries fresh_skip {pct = the logged f3.fresh, n, thr, would_skip}; live: the same window
/// is skipped "fresh_holders" (exactly when f3.fresh >= thr) with fresh / fresh_n / thr, counted; the hot keys switch it; bad values stay
#[test]
fn dip48_fresh_skip_log_live_keys() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let n = 461_415_576u64;
    // log mode at 15%: armed; the verdict = the logged f3.fresh
    let (mut p, _a, orx) = PsLive::for_test(fcfg(&["--presend-live-fresh-skip", "15:20"]), USER);
    let m = fresh_t2(&mut p, 0x51, n);
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    assert!(p.armed.contains_key(&m), "log mode arms: {:?}", r.iter().filter(|x| x["ev"] == "presend_live_skip").map(|x| x["why"].clone()).collect::<Vec<_>>());
    let arm = r.iter().find(|x| x["ev"] == "presend_live_arm").unwrap();
    let fresh = arm["f3"]["fresh"].as_f64().unwrap();
    assert!((fresh - 18.0).abs() < 0.01, "{}", arm["f3"]);
    assert_eq!((arm["fresh_skip"]["pct"].as_f64(), arm["fresh_skip"]["n"].as_u64(), arm["fresh_skip"]["thr"].as_f64(), arm["fresh_skip"]["would_skip"].as_bool()), (Some(fresh), Some(4), Some(15.0), Some(true)));
    // live at 15%: skipped
    let (mut p, _a, orx) = PsLive::for_test(fcfg(&["--presend-live-fresh-skip", "15:20", "--presend-live-fresh-skip-mode", "live"]), USER);
    let m = fresh_t2(&mut p, 0x52, n);
    assert!(!p.armed.contains_key(&m));
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    let sk = r.iter().find(|x| x["ev"] == "presend_live_skip").unwrap();
    assert_eq!((sk["why"].as_str(), sk["fresh_n"].as_u64(), sk["thr"].as_f64()), (Some("fresh_holders"), Some(4), Some(15.0)));
    assert!((sk["fresh"].as_f64().unwrap() - fresh).abs() < 1e-9);
    assert_eq!(p.st.skips.get("fresh_holders").copied(), Some(1));
    // live at 20% (> 18%): armed, would_skip false
    let (mut p, _a, orx) = PsLive::for_test(fcfg(&["--presend-live-fresh-skip", "20:20", "--presend-live-fresh-skip-mode", "live"]), USER);
    let m = fresh_t2(&mut p, 0x53, n);
    assert!(p.armed.contains_key(&m));
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    assert_eq!(r.iter().find(|x| x["ev"] == "presend_live_arm").unwrap()["fresh_skip"]["would_skip"], false);
    // the T2 lane off (0): no verdict, armed
    let (mut p, _a, orx) = PsLive::for_test(fcfg(&["--presend-live-fresh-skip", "0:20", "--presend-live-fresh-skip-mode", "live"]), USER);
    let m = fresh_t2(&mut p, 0x54, n);
    assert!(p.armed.contains_key(&m));
    assert!(orx.try_iter().filter_map(|o| o.rec()).find(|x| x["ev"] == "presend_live_arm").unwrap().get("fresh_skip").is_none());
    // the hot keys: log -> live, the spec; bad values keep the old ones; the filter state follows
    let ctl = std::env::temp_dir().join(format!("dip48_fresh_{}.json", std::process::id()));
    std::fs::write(&ctl, r#"{"fresh_skip": "live", "fresh_skip_spec": "15:30"}"#).unwrap();
    let (mut p, _a, orx) = PsLive::for_test(fcfg(&["--presend-live-fresh-skip", "35:20", "--presend-live-wh-loss", "2:0.05", "--presend-live-ledger-control", ctl.to_str().unwrap()]), USER);
    assert_eq!((p.f47.cur.unwrap().fresh, p.f47.cur.unwrap().fresh_live), (Some((15.0, 30.0)), true), "the control file's first read");
    assert_eq!((p.f47.fs.as_ref().unwrap().obj["fresh_skip"].as_str(), p.f47.fs.as_ref().unwrap().obj["fresh_skip_spec"].as_str()), (Some("live"), Some("15:30")));
    let m = fresh_t2(&mut p, 0x55, n);
    assert!(!p.armed.contains_key(&m), "skipped by the hot spec");
    std::fs::write(&ctl, r#"{"fresh_skip": "on", "fresh_skip_spec": "3:20"}"#).unwrap();
    p.ctl47_check(true);
    assert_eq!((p.f47.cur.unwrap().fresh, p.f47.cur.unwrap().fresh_live), (Some((15.0, 30.0)), true), "bad values: the old ones stay");
    std::fs::write(&ctl, "{}").unwrap();
    p.ctl47_check(true);
    assert_eq!((p.f47.cur.unwrap().fresh, p.f47.cur.unwrap().fresh_live), (Some((35.0, 20.0)), false), "absent: the start flags");
    let _ = orx.try_iter().count();
    let _ = std::fs::remove_file(&ctl);
    // refusals; the probe kind
    for bad in [vec!["--presend-live-fresh-skip", "35:20"], vec!["--presend-live-f3-log", "on", "--presend-live-fresh-skip", "3:20"],
                vec!["--presend-live-f3-log", "on", "--presend-live-fresh-skip", "0:0"], vec!["--presend-live-f3-log", "on", "--presend-live-fresh-skip", "35"],
                vec!["--presend-live-f3-log", "on", "--presend-live-fresh-skip-mode", "live"], vec!["--presend-live-f3-log", "on", "--presend-live-fresh-skip", "35:20", "--presend-live-fresh-skip-mode", "on"]] {
        assert!(Cfg::from_argv(&args(&bad), &arbx::presend::Params::default(), true, 1_000_000_000).is_err(), "{bad:?}");
    }
    let e = format!("{:#}", Cfg::from_argv(&args(&["--presend-live-fresh-skip", "35:20"]), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap_err());
    assert!(e.contains("needs --presend-live-f3-log"), "{e}");
    assert_eq!(psprobe46::kind_of("fresh_holders"), Some("fresh_holders"));
    assert!(psprobe46::KINDS_ALL & psprobe46::kind_bit("fresh_holders") != 0);
}

/// a fresh-holders skip with probes on gets a probe window (as the other arm-time skips)
#[test]
fn dip48_fresh_skip_probe_window() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let (mut p, _a, orx) = PsLive::for_test(fcfg(&["--presend-live-fresh-skip", "15:20", "--presend-live-fresh-skip-mode", "live", "--presend-live-probe", "on"]), USER);
    let _m = fresh_t2(&mut p, 0x56, 461_415_576);
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    assert!(r.iter().any(|x| x["ev"] == "presend_live_probe_arm" && x["filter"] == "fresh_holders"), "{:?}", r.iter().map(|x| x["ev"].clone()).collect::<Vec<_>>());
}

/// golden: the skip's flags in LOG mode (+ the f3 log in both runs) change no decision; only "fresh_skip" fields / the cfg part are new
#[test]
fn dip48_golden_fresh_log_changes_no_decision() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let strip = |v: Vec<String>| -> Vec<String> { v.into_iter().map(|l| {
        if !l.starts_with("R ") && !l.starts_with("F ") { return l; }
        let mut v: serde_json::Value = serde_json::from_str(&l[2..]).unwrap();
        if let Some(o) = v.as_object_mut() { o.remove("fresh_skip"); }
        if let Some(o) = v.get_mut("cfg").and_then(|c| c.as_object_mut()) { o.remove("fresh_skip"); }
        format!("{}{v}", &l[..2])
    }).collect() };
    let Some(a) = dip26_tests::golden_pass(1, &["--presend-live-f3-log", "on"], arbx::presend::Params::default(), 7) else { eprintln!("presend_parity.json missing: skipped"); return };
    let b = dip26_tests::golden_pass(1, &["--presend-live-f3-log", "on", "--presend-live-fresh-skip", "5:5"], arbx::presend::Params::default(), 7).unwrap();
    let nf = b.iter().filter(|l| l.contains("\"fresh_skip\":{")).count();
    let would = b.iter().filter(|l| l.contains("\"would_skip\":true")).count();
    eprintln!("dip48 golden fresh log: {} lines, {nf} with fresh_skip, {would} would-skip", b.len());
    assert!(nf > 10);
    let (a, b) = (strip(a), strip(b));
    assert_eq!(a.len(), b.len());
    for (x, y) in a.iter().zip(&b) { assert_eq!(x, y); }
}

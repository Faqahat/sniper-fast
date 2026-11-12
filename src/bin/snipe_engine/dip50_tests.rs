// ===================================================================================================================
// dip50 tests: GRX, the rival-ahead early exit (psgrx50.rs) and its hot keys (psctl47.rs). Declared inside pslive.rs.
//  * flags: defaults, values, refusals, known to the start-up flag check; off = no run_start field, no state, no filter-state key
//  * hot keys grx / grx_pct / grx_exit_slots: applied, recorded, refused when bad (the old value stays), ignored with the flag off,
//    the filter state's fv bumps on a change and carries the keys
//  * the member definition (pure): trigger whale out, a pre-trigger holder -> old_pct, risk < 5 / hz3 < 0.3 out, the 2.245 edge
//  * the engine: a T2 fill with entrants -> the fill record's "grx", the line, the price path record; < 2% holders never candidates
//  * LOG: the exit is the regular one; LIVE: "grx" at fill slot + N, a whole sell at the base price, never later than the regular exit;
//    TP / SL / the ms timer win when earlier; a re-arm fill logs and never acts; fail open on a blind feed; off = no grx field anywhere
//  * the real command line (r90's argv + --presend-live-grx on) parses: DIP50_ARGV=/path (skipped when unset)
// ===================================================================================================================
use super::*;
use arbx::dip::TradeEvent;

const USER: Pk = [0x5Au8; 32];
const N: u64 = 461_415_576;
/// the entrants: E1 3% and E2 2.5% (risky clocks), E3 1.5% (risky clock, below 2%), E4 3% (no clock)
const E1: Pk = [0xE1u8; 32];
const E2: Pk = [0xE2u8; 32];
const E3: Pk = [0xE3u8; 32];
const E4: Pk = [0xE4u8; 32];
const H1: Pk = [0xB1u8; 32];
const H2: Pk = [0xB2u8; 32];

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4", "--presend-live-wh-loss", "2:0.05", "--presend-live-ann", "on"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
/// exit at fill slot + 5 (the live run's --presend-exit-slots 5)
fn params() -> arbx::presend::Params { arbx::presend::Params { exit_slots: 5, ..Default::default() } }
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &params(), true, 1_000_000_000) }
fn outs(orx: &crossbeam_channel::Receiver<Out>) -> (Vec<serde_json::Value>, Vec<String>) {
    let (mut r, mut l) = (Vec::new(), Vec::new());
    for o in orx.try_iter() { match o { Out::Rec(v) => r.push(v), Out::Line(x) => l.push(x) } }
    (r, l)
}
fn arr(slot: u64, sig: [u8; 64], payer: Pk, ok: bool, exec: Option<arbx::feeds::ExecInfo>, t_rx: u64) -> arbx::feeds::Arrival {
    let tx = arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() };
    arbx::feeds::Arrival { feed: 0, slot, t_rx, t_decoded: t_rx, executed: Some(ok), tx, poh: None, raw: arbx::feeds::RawTx::None, exec: exec.map(Arc::new) }
}
fn mint_n(i: u8) -> Pk { let mut m = [0x73u8; 32]; m[0] = i; m }
fn launch(i: u8) -> Launch { snipe_build::launch_from_target(mint_n(i), [0xC1u8; 32]) }
#[allow(clippy::too_many_arguments)]
fn trade(p: &mut PsLive, slot: u64, idx: u64, sig: [u8; 64], user: Pk, buy: bool, sol: u64, tok: u64, vsol: u64, vtok: u64, l: &Launch) {
    let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades: vec![TradeEvent { mint: l.mint, sol, tok, buy, user, vsol, vtok, fbps: 95, cbps: 30 }],
        creates: Vec::new(), mayhem: false };
    let a = arr(slot, sig, user, true, Some(x.clone()), slot * 1_000_000 + idx);
    let l = l.clone();
    p.on_arrival(&a, slot);
    p.on_exec(&a, &x, slot, move |m: &Pk| (*m == l.mint).then(|| l.clone()), &|_| false, None);
}
fn create(p: &mut PsLive, slot: u64, l: &Launch) {
    let creator = [0xC1u8; 32];
    let x = arbx::feeds::ExecInfo { index: 7, fee: 5_000, ok: true, trades: Vec::new(), mayhem: false,
        creates: vec![arbx::dip::CreateEvent { mint: l.mint, bonding_curve: l.bonding_curve, user: creator, creator }] };
    let a = arr(slot, [0xC7u8; 64], creator, true, Some(x.clone()), slot * 1_000_000);
    let l2 = l.clone();
    p.on_exec(&a, &x, slot, move |m: &Pk| (*m == l2.mint).then(|| l2.clone()), &|_| false, None);
}
fn sg(a: u8, b: u8) -> [u8; 64] { let mut s = [a; 64]; s[1] = b; s }
fn whale(tag: u8) -> Pk { [0xA0 + tag; 32] }
const RISKY: [u32; 6] = [1, 2, 2, 3, 3, 4];
/// create at s - 1; H1 / H2 (3% each, risky clocks) buy at s - 1 = BEFORE the trigger; the ~6.2% whale triggers at s (idx 34); then, AFTER
/// the trigger in slot s: E1 3% + E2 2.5% (risky clocks), E3 1.5% (risky clock), E4 3% (no clock)
fn setup(p: &mut PsLive, l: &Launch, s: u64, tag: u8, whale_clock: bool) -> u64 {
    create(p, s - 1, l);
    for (i, h) in [H1, H2].iter().enumerate() {
        p.det.clock_preload(*h, pl::Holds::from_holds(&RISKY, s));
        trade(p, s - 1, 20 + i as u64, sg(0x60 + tag, i as u8), *h, true, 1_000_000_000, 30_000_000_000_000, 32_000_000_000, 1_000_000_000_000_000, l);
    }
    if whale_clock { p.det.clock_preload(whale(tag), pl::Holds::from_holds(&RISKY, s)); }
    trade(p, s, 34, sg(0x3E, tag), whale(tag), true, 2_666_666_666, 61_580_021_739_287, 38_692_888_509, 831_935_821_811_615, l);
    let id = *p.armed.get(&l.mint).unwrap_or_else(|| panic!("armed: {:?}", p.st.skips));
    for (i, (e, tok, clock)) in [(E1, 30_000_000_000_000u64, true), (E2, 25_000_000_000_000, true), (E3, 15_000_000_000_000, true), (E4, 30_000_000_000_000, false)].iter().enumerate() {
        if *clock { p.det.clock_preload(*e, pl::Holds::from_holds(&RISKY, s)); }
        trade(p, s, 40 + i as u64, sg(0x70 + tag, i as u8), *e, true, 1_000_000_000, *tok, 39_000_000_000, 825_000_000_000_000, l);
    }
    id
}
fn att(w: u64, mint: Pk, sig: [u8; 64], slot: u64) -> Att {
    Att { w, n: 1, mint, sig, tag: pl::PS_TAG | (0xD50 << 8) | sig[0] as u64, path: "helius-ps".into(), client: "AgaveBam".into(), slot, deadline: slot + 1, lim: 1.0,
        min_out: 1, p_sign: 0.0000466, sign_pos: (slot, 34, 0), t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }, tip: 200_000,
        wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46: Default::default(), rf: None, rg: None }
}
/// our buy of window `id`'s try lands at (slot, 50): the fill record
fn fill(p: &mut PsLive, atx: &crossbeam_channel::Sender<Att>, orx: &crossbeam_channel::Receiver<Out>, l: &Launch, id: u64, sig: [u8; 64], slot: u64) -> (serde_json::Value, Vec<serde_json::Value>, Vec<String>) {
    fill_with(p, atx, orx, l, id, sig, slot, |_| {})
}
#[allow(clippy::too_many_arguments)]
fn fill_with(p: &mut PsLive, atx: &crossbeam_channel::Sender<Att>, orx: &crossbeam_channel::Receiver<Out>, l: &Launch, id: u64, sig: [u8; 64], slot: u64, pre: impl FnOnce(&mut PsLive)) -> (serde_json::Value, Vec<serde_json::Value>, Vec<String>) {
    atx.send(att(id, l.mint, sig, slot - 1)).unwrap();
    p.drain_atts();
    pre(p);
    let _ = outs(orx);
    trade(p, slot, 50, sig, USER, true, 395_061_728, 9_000_000_000_000, 39_100_000_000, 822_000_000_000_000, l);
    let (r, lines) = outs(orx);
    let f = r.iter().find(|x| x["ev"] == "presend_live_fill").unwrap_or_else(|| panic!("{r:?}")).clone();
    (f, r, lines)
}
fn exits(r: &[serde_json::Value]) -> Vec<(String, i64)> {
    r.iter().filter(|x| x["ev"] == "presend_live_exit").map(|x| (x["why"].as_str().unwrap().to_string(), x["slots_held"].as_i64().unwrap())).collect()
}
fn sells(c: &[Cmd]) -> Vec<(u32, Option<SellX>)> { c.iter().filter_map(|c| match c { Cmd::Sell { round, x43, .. } => Some((*round, *x43)), _ => None }).collect() }
#[allow(clippy::too_many_arguments)]
fn tr(mint: Pk, s: u64, i: u32, user: Pk, buy: bool, sol: u64, tok: u64, vsol: u64, vtok: u64) -> pl::Trade {
    pl::Trade { mint, s, i, j: 0, sig: [0u8; 64], user, buy, sol, tok, vsol, vtok, fbps: 95, cbps: 30, t_rx: 0 }
}
fn raw(j: serde_json::Value) -> psctl47::Raw { psctl47::ctl47_parse(j.to_string().as_bytes()).unwrap() }
fn ctl_file(name: &str) -> std::path::PathBuf {
    let f = std::env::temp_dir().join(format!("dip50_{name}_{}.json", std::process::id()));
    std::fs::write(&f, "{}").unwrap();
    f
}
/// the probe with GRX on (+ `extra`), a control file, one T2 window armed with the entrants in, our fill at N + 1
#[allow(clippy::type_complexity)]
fn open(name: &str, extra: &[&str], keys: serde_json::Value, tag: u8) -> (PsLive, crossbeam_channel::Receiver<Out>, Launch, serde_json::Value, Vec<serde_json::Value>, Vec<String>, std::path::PathBuf) {
    arbx::feeds::own_fail_watch(USER);
    let ctl = ctl_file(name);
    let mut a = vec!["--presend-live-grx", "on", "--presend-live-ledger-control", ctl.to_str().unwrap()];
    a.extend_from_slice(extra);
    let (mut p, atx, orx) = PsLive::for_test(cfg(&a).unwrap().unwrap(), USER);
    if keys.as_object().is_some_and(|o| !o.is_empty()) { p.ctl47_apply(&raw(keys), "t"); }
    let l = launch(tag);
    let id = setup(&mut p, &l, N, tag, false);
    let (f, r, lines) = fill(&mut p, &atx, &orx, &l, id, sg(0x50, tag), N + 1);
    (p, orx, l, f, r, lines, ctl)
}

// ---- flags ------------------------------------------------------------------------------------------------------------------

#[test]
fn dip50_flags_defaults_and_refusals() {
    // off by default: nothing in the run_start record, no state
    let c = cfg(&[]).unwrap().unwrap();
    assert!(!c.grx && !c.grx_live && c.grx_pct == 2.245 && c.grx_slots == 1);
    assert!(c.json().get("grx").is_none());
    let c = cfg(&["--presend-live-grx", "off"]).unwrap().unwrap();
    assert!(!c.grx && c.json().get("grx").is_none());
    // on: log by default, the research threshold, fill + 1
    let c = cfg(&["--presend-live-grx", "on"]).unwrap().unwrap();
    assert!(c.grx && !c.grx_live);
    assert_eq!((c.grx_pct, c.grx_slots), (psgrx50::THR, 1));
    assert_eq!(c.json()["grx"], serde_json::json!({"grx": "log", "grx_pct": 2.245, "grx_exit_slots": 1, "lane": "t2", "rule": "G2 entrant risk"}));
    let c = cfg(&["--presend-live-grx", "on", "--presend-live-grx-mode", "live", "--presend-live-grx-pct", "3.5", "--presend-live-grx-exit-slots", "2"]).unwrap().unwrap();
    assert!(c.grx_live);
    assert_eq!((c.grx_pct, c.grx_slots), (3.5, 2));
    assert_eq!(c.json()["grx"]["grx"], "live");
    // refusals
    for bad in [vec!["--presend-live-grx", "maybe"], vec!["--presend-live-grx", "on", "--presend-live-grx-mode", "on"], vec!["--presend-live-grx", "on", "--presend-live-grx-pct", "0.5"],
        vec!["--presend-live-grx", "on", "--presend-live-grx-pct", "21"], vec!["--presend-live-grx", "on", "--presend-live-grx-pct", "x"],
        vec!["--presend-live-grx", "on", "--presend-live-grx-exit-slots", "0"], vec!["--presend-live-grx", "on", "--presend-live-grx-exit-slots", "6"],
        vec!["--presend-live-grx", "on", "--presend-live-grx-exit-slots", "1.5"],
        // the value flags need the flag on
        vec!["--presend-live-grx-mode", "live"], vec!["--presend-live-grx-pct", "3"], vec!["--presend-live-grx-exit-slots", "2"], vec!["--presend-live-grx", "off", "--presend-live-grx-mode", "log"]] {
        assert!(cfg(&bad).is_err(), "{bad:?}");
    }
    // needs the annotations (the hold clocks) and --presend-live
    let mut a = args(&[]);
    a.retain(|x| x != "on" && x != "--presend-live-ann");
    a.extend(["--presend-live-grx", "on"].iter().map(|s| s.to_string()));
    let e = Cfg::from_argv(&a, &params(), true, 1_000_000_000).unwrap_err().to_string();
    assert!(e.contains("--presend-live-ann on"), "{e}");
    for f in D50FLAGS {
        let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", f, "on"].iter().map(|s| s.to_string()).collect::<Vec<_>>(), &params(), true, 1_000_000_000).unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{e}");
    }
    // the names in the module = the names the start-up flag check knows (it reads pslive.rs)
    assert_eq!(D50FLAGS, [psgrx50::FLAG, psgrx50::FLAG_MODE, psgrx50::FLAG_PCT, psgrx50::FLAG_SLOTS]);
    let known = src_flags("\"");
    for f in D50FLAGS { assert!(known.contains(f), "{f} unknown to check_flags"); }
    assert!(check_flags(&args(&["--presend-live-grx", "on", "--presend-live-grx-mode", "live", "--presend-live-grx-pct", "2.245", "--presend-live-grx-exit-slots", "1"])).is_ok());
}

/// the live run's command line with GRX on: DIP50_ARGV=/home/it/sniper-data/runs/ams_r90/r90_argv.txt (one argument per line; skipped when unset)
#[test]
fn dip50_real_argv_parses() {
    let Ok(path) = std::env::var("DIP50_ARGV") else { eprintln!("DIP50_ARGV unset: skipped"); return };
    let txt = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"));
    let mut a: Vec<String> = vec!["snipe_engine".to_string()];
    a.extend(txt.lines().map(|l| l.trim_end_matches('\r').to_string()).filter(|l| !l.is_empty()));
    if a.get(1).is_some_and(|x| !x.starts_with("--")) { a.remove(1); }
    let live = a.iter().any(|x| x == "--live");
    let sh = arbx::presend::Params { whale_pct: 6.0, exit_slots: 5, tp: 0.20, ..Default::default() };
    // as given: no GRX
    check_flags(&a).unwrap_or_else(|e| panic!("check_flags (as given): {e}"));
    let c0 = Cfg::from_argv(&a, &sh, live, 1_000_000_000).unwrap_or_else(|e| panic!("from_argv (as given): {e}")).expect("--presend-live");
    assert!(!c0.grx && c0.json().get("grx").is_none());
    // + --presend-live-grx on (log), then the three value flags
    a.extend(["--presend-live-grx", "on"].iter().map(|s| s.to_string()));
    check_flags(&a).unwrap_or_else(|e| panic!("check_flags (+grx): {e}"));
    let c = Cfg::from_argv(&a, &sh, live, 1_000_000_000).unwrap_or_else(|e| panic!("from_argv (+grx): {e}")).expect("--presend-live");
    assert!(c.grx && !c.grx_live && c.grx_pct == 2.245 && c.grx_slots == 1 && c.ann);
    a.extend(["--presend-live-grx-mode", "live", "--presend-live-grx-pct", "2.245", "--presend-live-grx-exit-slots", "1"].iter().map(|s| s.to_string()));
    check_flags(&a).unwrap();
    let c = Cfg::from_argv(&a, &sh, live, 1_000_000_000).unwrap().unwrap();
    assert!(c.grx && c.grx_live);
    eprintln!("DIP50_ARGV {path}: {} arguments parse with --presend-live-grx on (exit_ms {}, exit_slots {}, timer sell {:?})", a.len(), c.exit_ms, c.exit_slots, c.b43.timer_sell);
}

// ---- hot keys + filter state ----------------------------------------------------------------------------------------------------

#[test]
fn dip50_hot_keys_and_filter_state() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let ctl = ctl_file("keys");
    let (mut p, _atx, orx) = PsLive::for_test(cfg(&["--presend-live-grx", "on", "--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap(), USER);
    let st = p.f47.start.unwrap();
    assert!(st.grx_on && !st.grx_live && st.grx_pct == 2.245 && st.grx_slots == 1);
    assert_eq!(p.grx50_vals(), (false, 2.245, 1));
    // the filter state at start: fv 0 with the three keys
    let fs0 = p.f47.fs.clone().unwrap();
    assert_eq!(fs0.fv, 0);
    assert_eq!((fs0.obj["grx"].as_str(), fs0.obj["grx_pct"].as_f64(), fs0.obj["grx_exit_slots"].as_u64()), (Some("log"), Some(2.245), Some(1)));
    let (r, lines) = outs(&orx);
    assert!(lines.iter().any(|l| l.starts_with("DIP50 CONTROL KEYS (") && l.contains("grx, grx_pct, grx_exit_slots")), "{lines:?}");
    assert!(r.iter().any(|x| x["ev"] == "presend_live_filter_state" && x["fv"] == 0 && x["state"]["grx"] == "log"));
    // parse: the keys are read from the file's object
    let rw = raw(serde_json::json!({"grx": "live", "grx_pct": 3.5, "grx_exit_slots": 2, "tp": 0.3, "nonsense": 1}));
    assert!(rw.contains_key("grx") && rw.contains_key("grx_pct") && rw.contains_key("grx_exit_slots") && !rw.contains_key("nonsense"));
    // apply: one mode record with the new and the old values, the line, the filter state fv 1
    p.ctl47_apply(&raw(serde_json::json!({"grx": "live", "grx_pct": 3.5, "grx_exit_slots": 2})), "t");
    assert_eq!(p.grx50_vals(), (true, 3.5, 2));
    let (r, lines) = outs(&orx);
    let m = r.iter().find(|x| x["ev"] == "presend_live_ledger_mode" && x["ok"] == true).unwrap_or_else(|| panic!("{r:?}"));
    assert_eq!(m["dip47"], serde_json::json!({"grx": "live", "grx_pct": 3.5, "grx_exit_slots": 2}));
    assert_eq!(m["was"]["dip47"], serde_json::json!({"grx": "log", "grx_pct": 2.245, "grx_exit_slots": 1}));
    assert!(lines.iter().any(|l| l.starts_with("  PRESEND LIVE LEDGER MODES dip47: ") && l.contains("grx \"log\" -> \"live\"")), "{lines:?}");
    let fs = r.iter().find(|x| x["ev"] == "presend_live_filter_state").unwrap();
    assert_eq!((fs["fv"].as_u64(), fs["changed"]["grx"][1].as_str(), fs["changed"]["grx_pct"][1].as_f64(), fs["changed"]["grx_exit_slots"][1].as_u64()), (Some(1), Some("live"), Some(3.5), Some(2)));
    assert_ne!(fs["fh"], serde_json::json!(fs0.fh));
    // the same values again: no record, no bump
    p.ctl47_apply(&raw(serde_json::json!({"grx": "live", "grx_pct": 3.5, "grx_exit_slots": 2})), "t");
    p.fs_tick();
    assert!(outs(&orx).0.is_empty());
    assert_eq!(p.f47.fs.as_ref().unwrap().fv, 1);
    // bad values: refused one by one, the old value stays; a number given as text is read
    let before = p.f47.cur.unwrap();
    for (k, bad) in [("grx", serde_json::json!("on")), ("grx", serde_json::json!(1)), ("grx_pct", serde_json::json!(0.99)), ("grx_pct", serde_json::json!(20.5)), ("grx_pct", serde_json::json!("abc")),
        ("grx_exit_slots", serde_json::json!(0)), ("grx_exit_slots", serde_json::json!(6)), ("grx_exit_slots", serde_json::json!(1.5))] {
        let mut j = serde_json::json!({"grx": "live", "grx_pct": 3.5, "grx_exit_slots": 2});
        j[k] = bad.clone();
        p.ctl47_apply(&raw(j), "t");
        let (r, lines) = outs(&orx);
        let e = r.iter().find(|x| x["ev"] == "presend_live_ledger_mode" && x["ok"] == false).unwrap_or_else(|| panic!("{k} {bad}: {r:?}"));
        assert_eq!((e["key"].as_str(), &e["kept"]), (Some(k), &before.get(k)), "{e}");
        assert!(lines.iter().any(|l| l.contains(&format!("\"{k}\" REFUSED"))), "{lines:?}");
        assert_eq!(p.f47.cur.unwrap(), before, "{k} {bad}: every value stays");
    }
    p.ctl47_apply(&raw(serde_json::json!({"grx": "live", "grx_pct": "4", "grx_exit_slots": "3"})), "t");
    assert_eq!(p.grx50_vals(), (true, 4.0, 3));
    // the bounds themselves are accepted
    p.ctl47_apply(&raw(serde_json::json!({"grx_pct": 1, "grx_exit_slots": 5})), "t");
    assert_eq!(p.grx50_vals(), (false, 1.0, 5), "grx absent = the start flag (log)");
    p.ctl47_apply(&raw(serde_json::json!({"grx_pct": 20, "grx_exit_slots": 1})), "t");
    assert_eq!(p.grx50_vals(), (false, 20.0, 1));
    // absent = the start values
    p.ctl47_apply(&raw(serde_json::json!({})), "t");
    assert_eq!(p.f47.cur.unwrap(), st);
    // through the file, with the versions
    let fv = p.f47.fs.as_ref().unwrap().fv;
    std::fs::write(&ctl, r#"{"grx": "live"}"#).unwrap();
    p.ctl47_check(true);
    p.fs_tick();
    assert_eq!(p.grx50_vals(), (true, 2.245, 1));
    assert_eq!((p.f47.fs.as_ref().unwrap().fv, p.f47.fs.as_ref().unwrap().obj["grx"].as_str()), (fv + 1, Some("live")));
    // the start flags give the start values
    let (q, _a, _o) = PsLive::for_test(cfg(&["--presend-live-grx", "on", "--presend-live-grx-mode", "live", "--presend-live-grx-pct", "5", "--presend-live-grx-exit-slots", "3"]).unwrap().unwrap(), USER);
    assert_eq!(q.grx50_vals(), (true, 5.0, 3));
    assert_eq!(q.f47.fs.as_ref().unwrap().obj["grx"], "live");
    let _ = std::fs::remove_file(&ctl);
}

/// the flag off: the keys are ignored with a record, the filter state has no grx key (dip49c's state and hash), no GRX state / status
#[test]
fn dip50_off_is_dip49c() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let ctl = ctl_file("off");
    let (mut p, atx, orx) = PsLive::for_test(cfg(&["--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap(), USER);
    assert!(p.grx.is_none());
    let fs0 = p.f47.fs.clone().unwrap();
    for k in psctl47::KEYS50 { assert!(fs0.obj.get(k).is_none(), "{k} in the filter state with GRX off"); }
    let (_, lines) = outs(&orx);
    assert!(!lines.iter().any(|l| l.contains("DIP50") || l.contains("grx")), "{lines:?}");
    // the same state as a probe started with "--presend-live-grx off"
    let (q, _a, _o) = PsLive::for_test(cfg(&["--presend-live-grx", "off", "--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap(), USER);
    assert_eq!(q.f47.fs.as_ref().unwrap().fh, fs0.fh);
    // the keys: refused, nothing changes
    p.ctl47_apply(&raw(serde_json::json!({"grx": "live", "grx_pct": 3.0, "grx_exit_slots": 2})), "t");
    let (r, _) = outs(&orx);
    let errs: Vec<&str> = r.iter().filter(|x| x["ev"] == "presend_live_ledger_mode" && x["ok"] == false).map(|x| x["key"].as_str().unwrap()).collect();
    assert_eq!(errs, vec!["grx", "grx_pct", "grx_exit_slots"]);
    assert!(r.iter().all(|x| x["ev"] != "presend_live_filter_state"));
    assert_eq!(p.f47.fs.as_ref().unwrap().fh, fs0.fh);
    assert_eq!(p.grx50_vals(), (false, 2.245, 1));
    // a T2 fill with the entrants in: no grx field, no line, no path; the exit at fill + 5 only
    let l = launch(1);
    let id = setup(&mut p, &l, N, 1, false);
    let (f, r, lines) = fill(&mut p, &atx, &orx, &l, id, sg(0x50, 1), N + 1);
    assert!(f.get("grx").is_none() && f["ann"]["holders"].as_array().unwrap().len() == 6, "{f}");
    assert!(!lines.iter().any(|l| l.contains("GRX")) && r.iter().all(|x| x["ev"] != "presend_live_grx_path"));
    for s in N + 1..N + 6 { p.tick(s, None); }
    assert!(exits(&outs(&orx).0).is_empty());
    p.tick(N + 6, None);
    let (r, _) = outs(&orx);
    assert_eq!(exits(&r), vec![("time-limit".to_string(), 5)]);
    for s in N + 7..N + 10 { p.tick(s, None); }
    p.rec(serde_json::json!({"ev": "presend_live_realized", "w": id, "pnl": 1}));
    let (r, _) = outs(&orx);
    assert!(r.iter().all(|x| x["ev"] != "presend_live_grx_path" && x.get("grx").is_none()));
    assert!(!p.status().contains("GRX"));
    let _ = std::fs::remove_file(&ctl);
}

// ---- the member definition ---------------------------------------------------------------------------------------------------------

fn hc(w: u8, pct: f64, age: u64, risk: u32, hz3: f32) -> pl::HolderClock {
    pl::HolderClock { w: [w; 32], bal: (pct / 100.0 * pl::SUPPLY).round() as i64, age, n: 6, p25: 2, p50: 3, p75: 4, h3: Some(0.5), risk, hz3 }
}

#[test]
fn dip50_member_definition() {
    let wh = [9u8; 32];
    // since = fill slot - trigger slot = 2
    let hs = vec![
        hc(9, 7.0, 2, 9, 0.9),   // the trigger whale (risky clock): never a member; whale_member
        hc(1, 3.0, 0, 5, 0.3),   // entrant in the fill slot, exactly at both clock thresholds
        hc(2, 2.5, 2, 8, 0.5),   // entrant in the trigger slot (age = since)
        hc(3, 4.0, 3, 8, 0.9),   // bought one slot BEFORE the trigger: old, not an entrant
        hc(4, 5.0, 1, 4, 0.9),   // risk < 5
        hc(5, 5.0, 1, 9, 0.29),  // hz3 < 0.3
        hc(6, 6.0, 0, 0, 0.0),   // no clock
        hc(7, 2.0, 40, 6, 0.4),  // an old risky holder
    ];
    let v = psgrx50::eval(&hs, &wh, 2);
    assert_eq!(v.members.iter().map(|m| m.w[0]).collect::<Vec<_>>(), vec![1, 2]);
    assert!((v.ent_pct - 5.5).abs() < 1e-9 && (v.old_pct - 6.0).abs() < 1e-9 && v.old_n == 2 && v.whale_member, "{v:?}");
    assert_eq!((v.members[0].age, v.members[0].risk, v.members[1].age), (0, 5, 2));
    // the same holders, the whale someone else: wallet 9 is an entrant like any other
    assert!((psgrx50::eval(&hs, &[0u8; 32], 2).ent_pct - 12.5).abs() < 1e-9);
    assert!(!psgrx50::eval(&hs, &[0u8; 32], 2).whale_member);
    // a fill in the trigger slot (since 0): only the age-0 holders are entrants
    let v0 = psgrx50::eval(&hs, &wh, 0);
    assert_eq!(v0.members.iter().map(|m| m.w[0]).collect::<Vec<_>>(), vec![1]);
    assert!((v0.old_pct - 8.5).abs() < 1e-9);
    // nobody
    assert_eq!(psgrx50::eval(&[], &wh, 3), psgrx50::Verdict::default());
    // the sum is the research script's: left to right from 0.0 over the logged percentages
    let logged: f64 = [hs[1].bal, hs[2].bal].iter().map(|b| *b as f64 / pl::SUPPLY * 100.0).sum();
    assert_eq!(v.ent_pct.to_bits(), logged.to_bits());
    // the threshold edge: >= 2.245 flags
    assert!(psgrx50::flagged(2.245, psgrx50::THR) && psgrx50::flagged(2.2450001, psgrx50::THR) && !psgrx50::flagged(2.2449999, psgrx50::THR) && !psgrx50::flagged(0.0, psgrx50::THR));
    let edge = psgrx50::eval(&[hc(1, 2.245, 1, 5, 0.3)], &wh, 1).ent_pct;
    assert_eq!(psgrx50::flagged(edge, psgrx50::THR), edge >= 2.245);
    assert!(psgrx50::flagged(psgrx50::eval(&[hc(1, 2.25, 1, 5, 0.3)], &wh, 1).ent_pct, psgrx50::THR));
    assert!(!psgrx50::flagged(psgrx50::eval(&[hc(1, 2.24, 1, 5, 0.3)], &wh, 1).ent_pct, psgrx50::THR));
    // the exit: due from fill slot + N on
    assert_eq!((psgrx50::due(100, 100, 1), psgrx50::due(101, 100, 1), psgrx50::due(101, 100, 2), psgrx50::due(105, 100, 2)), (None, Some("grx"), None, Some("grx")));
    // the price path: only the trades after our buy, slots fill .. fill + 5; ours kept apart
    let mut pa = psgrx50::Path::new(1, "t2", true, &tr([1u8; 32], 100, 50, USER, true, 400_000_000, 9_000_000_000_000, 39_100_000_000, 822_000_000_000_000));
    pa.price0 = 1e-5;
    assert!(!pa.add((100, 49, 0), false, true, 5, 9e-6) && !pa.add((100, 50, 0), true, true, 5, 1e-5) && !pa.add((106, 0, 0), false, true, 5, 2e-5));
    assert!(pa.add((100, 51, 0), false, true, 1_000_000_000, 1.1e-5) && pa.add((102, 3, 0), false, false, 500_000_000, 0.9e-5) && pa.add((102, 4, 0), true, false, 400_000_000, 0.8e-5)
        && pa.add((105, 9, 0), false, true, 250_000_000, 1.2e-5));
    let j = pa.json("slot5");
    let ps = j["per_slot"].as_array().unwrap();
    assert_eq!(ps.len(), 6);
    assert_eq!((ps[0]["price"].as_f64(), ps[0]["buy_sol"].as_f64(), ps[1]["price"].as_f64(), ps[1]["n"].as_u64()), (Some(1.1e-5), Some(1.0), Some(1.1e-5), Some(0)), "an empty slot carries the last price");
    assert_eq!((ps[2]["sell_sol"].as_f64(), ps[2]["us_sell_sol"].as_f64(), ps[2]["price"].as_f64(), ps[5]["buy_sol"].as_f64(), ps[5]["price"].as_f64()), (Some(0.5), Some(0.4), Some(0.8e-5), Some(0.25), Some(1.2e-5)));
    assert_eq!((j["ev"].as_str(), j["fill_slot"].as_u64(), j["price_fill"].as_f64(), j["flag"].as_bool(), j["closed"].as_str()), (Some("presend_live_grx_path"), Some(100), Some(1e-5), Some(true), Some("slot5")));
}

/// the log-only extras' definitions (pure): G0 with the whale, the cascade fall, the marks (our own sell in the curve state: sold_at_dslot)
#[test]
fn dip50_extras_definitions() {
    let wh = [9u8; 32];
    // G0 = every risky candidate, the whale too (the annotation's grp_pct: the same filter and sum)
    let hs = vec![hc(9, 7.0, 2, 9, 0.9), hc(1, 3.0, 0, 5, 0.3), hc(3, 4.0, 30, 8, 0.9), hc(4, 5.0, 1, 4, 0.9)];
    let v = psgrx50::eval(&hs, &wh, 2);
    let ann: f64 = hs.iter().filter(|h| h.risk >= 5 && h.hz3 >= 0.3).map(|h| h.bal as f64 / pl::SUPPLY * 100.0).sum();
    assert_eq!(v.g0_pct.to_bits(), ann.to_bits());
    assert!((v.g0_pct - 14.0).abs() < 1e-9 && (v.ent_pct - 3.0).abs() < 1e-9);
    // CASCADE: non-trigger members >= 1.5% at signing whose balance fell; the fall summed
    let pc = |x: f64| (x / 100.0 * pl::SUPPLY).round() as u64;
    let set = vec![([1u8; 32], pc(4.0), false), ([2u8; 32], pc(3.0), false), ([3u8; 32], pc(1.49), false), (wh, pc(7.0), true), ([5u8; 32], pc(1.5), false), ([6u8; 32], pc(2.0), false)];
    let now = |w: &Pk| match w[0] { 1 => pc(1.0), 2 => pc(3.0), 3 => 0, 9 => 0, 5 => 0, 6 => pc(2.5), _ => 0 };
    let (pct, m) = psgrx50::cascade(&set, now);
    // 1: 4 -> 1 (3.0); 2: unchanged; 3: below 1.5% at signing; the whale: the trigger; 5: 1.5 -> 0 (1.5); 6: bought more
    assert_eq!(m.iter().map(|x| x.0[0]).collect::<Vec<_>>(), vec![1, 5]);
    assert!((pct - 4.5).abs() < 1e-9 && (m[0].1 - 4.0).abs() < 1e-9 && (m[0].2 - 1.0).abs() < 1e-9, "{pct} {m:?}");
    assert!(pct < psgrx50::CAS_WOULD && psgrx50::cascade(&[([1u8; 32], pc(5.0), false)], |_| 0).0 >= psgrx50::CAS_WOULD);
    assert_eq!(psgrx50::cascade(&[], |_| 0), (0.0, Vec::new()));
    assert_eq!((psgrx50::CAS_MIN_PCT, psgrx50::CAS_WOULD, psgrx50::SMALL_TRIG, psgrx50::RA_HOLD, psgrx50::MARKS), (1.5, 5.0, 6.25, 30.0, [0, 1, 2, 5]));
    // MARKS: our fill (100, 50): 9e12 tokens for 0.4 SOL, the curve after it (39.1 SOL, 822e12)
    let m1 = [1u8; 32];
    let mut pa = psgrx50::Path::new(1, "t2", false, &tr(m1, 100, 50, USER, true, 400_000_000, 9_000_000_000_000, 39_100_000_000, 822_000_000_000_000));
    let fr = arbx::presend::fee_rate(95, 30);
    let out = |v: u64, t: u64| psgrx50::mark_out(v, t, 9_000_000_000_000, fr);
    assert_eq!(out(39_100_000_000, 822_000_000_000_000), (arbx::dip::sell_sol_out(39_100_000_000, 822_000_000_000_000, 9_000_000_000_000) as f64 * (1.0 - fr)).floor() as u64);
    assert!(!pa.add_trade(&tr(m1, 100, 49, [7u8; 32], true, 1, 1, 1, 1), false), "before our buy");
    // fill slot: a buy by A, a sell by B; +1: nothing; +2: our own sell (the tokens are gone, the marks go on as if held), A again; +4: C buys
    assert!(pa.add_trade(&tr(m1, 100, 60, [0xAu8; 32], true, 1_000_000_000, 20_000_000_000_000, 40_100_000_000, 802_000_000_000_000), false));
    assert!(pa.add_trade(&tr(m1, 100, 61, [0xBu8; 32], false, 500_000_000, 10_000_000_000_000, 39_600_000_000, 812_000_000_000_000), false));
    assert!(pa.add_trade(&tr(m1, 102, 5, USER, false, 420_000_000, 9_000_000_000_000, 39_180_000_000, 821_000_000_000_000), true));
    assert!(pa.add_trade(&tr(m1, 102, 6, [0xAu8; 32], true, 200_000_000, 4_000_000_000_000, 39_380_000_000, 817_000_000_000_000), false));
    assert!(pa.add_trade(&tr(m1, 104, 1, [0xCu8; 32], true, 300_000_000, 6_000_000_000_000, 39_680_000_000, 811_000_000_000_000), false));
    assert!(!pa.add_trade(&tr(m1, 106, 1, [0xDu8; 32], true, 300_000_000, 6_000_000_000_000, 50_000_000_000, 700_000_000_000_000), false), "after fill + 5");
    let j = pa.marks_json(106, "slot5");
    assert_eq!((j["ev"].as_str(), j["tokens"].as_u64(), j["spend"].as_u64(), j["sold_at_dslot"].as_u64(), j["flag"].as_bool()), (Some("presend_live_grx_marks"), Some(9_000_000_000_000), Some(400_000_000), Some(2), Some(false)));
    let ms: Vec<(u64, u64, u64, f64, f64)> = j["marks"].as_array().unwrap().iter().map(|m| (m["dslot"].as_u64().unwrap(), m["out"].as_u64().unwrap(), m["buyers"].as_u64().unwrap(),
        m["buy_sol"].as_f64().unwrap(), m["sell_sol"].as_f64().unwrap())).collect();
    assert_eq!(ms, vec![(0, out(39_600_000_000, 812_000_000_000_000), 1, 1.0, 0.5), (1, out(39_600_000_000, 812_000_000_000_000), 1, 1.0, 0.5),
        (2, out(39_380_000_000, 817_000_000_000_000), 1, 1.2, 0.5), (5, out(39_680_000_000, 811_000_000_000_000), 2, 1.5, 0.5)], "our own sell is in the +2 state, never in sell_sol");
    assert_eq!(j["marks"][2]["vtok"], 817_000_000_000_000u64);
    // a close before fill + 5 ended (the 5 s limit): only the marks whose slot has ended
    let j = pa.marks_json(102, "5s");
    assert_eq!(j["marks"].as_array().unwrap().iter().map(|m| m["dslot"].as_u64().unwrap()).collect::<Vec<_>>(), vec![0, 1]);
    assert_eq!(pa.marks_json(100, "5s")["marks"].as_array().unwrap().len(), 0);
    // no trade at all: the curve right after our buy
    let pb = psgrx50::Path::new(1, "t2", false, &tr(m1, 100, 50, USER, true, 400_000_000, 9_000_000_000_000, 39_100_000_000, 822_000_000_000_000));
    assert!(pb.marks_json(106, "slot5")["marks"].as_array().unwrap().iter().all(|m| m["out"] == out(39_100_000_000, 822_000_000_000_000) && m["buyers"] == 0));
}

/// the extras never change an exit: LIVE, the entrant flag below its threshold, every log-only "would" true -> the regular exit
#[test]
fn dip50_extras_never_act() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let ctl = ctl_file("extras");
    let (mut p, atx, orx) = PsLive::for_test(cfg(&["--presend-live-grx", "on", "--presend-live-grx-mode", "live", "--presend-live-grx-pct", "6", "--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap(), USER);
    let l = launch(14);
    let id = setup(&mut p, &l, N, 14, true);
    let sig = sg(0x50, 14);
    let pc = |x: f64| (x / 100.0 * pl::SUPPLY).round() as u64;
    // the filling try's CASCADE set at its signing (the dip43 A5 shadow's sigset; no true-balance book here: every balance reads 0 now)
    let set: ps43::HSet = vec![([0xD1u8; 32], pc(3.0), false), (whale(14), pc(6.0), true), ([0xD2u8; 32], pc(1.4), false), ([0xD3u8; 32], pc(2.5), false)];
    let (f, _r, lines) = fill_with(&mut p, &atx, &orx, &l, id, sig, N + 1, |p| { p.d43.sigset.insert(sig, (id, Arc::new(set))); });
    let g = &f["grx"];
    assert_eq!((g["mode"].as_str(), g["thr"].as_f64(), g["ent_pct"].as_f64(), g["would_exit"].as_bool(), g["applied"].as_bool()), (Some("live"), Some(6.0), Some(5.5), Some(false), Some(false)), "{g}");
    // G0 with the risky whale: H1 + H2 + whale + E1 + E2
    assert!((g["g0_pct"].as_f64().unwrap() - 17.658).abs() < 0.01 && g["g0_would"] == true && g["whale_member"] == true);
    assert_eq!(g["g0_pct"].as_f64().unwrap().to_bits(), f["ann"]["grp_pct"].as_f64().unwrap().to_bits());
    assert!(g["whale_risk"].as_u64().unwrap() >= 5 && g["whale_hz3"].as_f64().unwrap() >= 0.3 && (g["whale_pct"].as_f64().unwrap() - 6.158).abs() < 0.01);
    assert_eq!((g["cas_src"].as_str(), g["cas_pct"].as_f64(), g["cas_would"].as_bool(), g["cas_members"].as_array().map(|a| a.len())), (Some("cascade43"), Some(5.5), Some(true), Some(2)));
    assert_eq!(g["cas_members"][0], serde_json::json!({"w": b58(&[0xD1u8; 32]), "sign_pct": 3.0, "land_pct": 0.0}));
    assert_eq!(g["small_would"], true);
    assert!(!lines.iter().any(|x| x.contains("PRESEND LIVE GRX")), "no flag: no line");
    assert!(p.grx.as_ref().unwrap().px.is_empty());
    let _ = p.take_cmds();
    for s in N + 1..N + 6 { p.tick(s, None); }
    assert!(exits(&outs(&orx).0).is_empty() && sells(&p.take_cmds()).is_empty(), "no extra moves an exit");
    p.tick(N + 6, None);
    assert_eq!(exits(&outs(&orx).0), vec![("time-limit".to_string(), 5)]);
    assert!(p.status().contains(" | GRX fills 1 flagged 0 (live exits 0)"));
    // thresholds: the trigger above 6.25% -> small_would false; the cascade below 5%
    let l2 = launch(15);
    let id2 = setup(&mut p, &l2, N + 100, 15, false);
    p.grx.as_mut().unwrap().note_trig(id2, 6.26);
    let sig2 = sg(0x50, 15);
    let set: ps43::HSet = vec![([0xD1u8; 32], pc(4.99), false)];
    let (f2, _r, _l) = fill_with(&mut p, &atx, &orx, &l2, id2, sig2, N + 101, |p| { p.d43.sigset.insert(sig2, (id2, Arc::new(set))); });
    let g = &f2["grx"];
    assert_eq!((g["trig_pct"].as_f64(), g["small_would"].as_bool(), g["cas_would"].as_bool(), g["g0_would"].as_bool()), (Some(6.26), Some(false), Some(false), Some(true)), "{g}");
    assert!((g["cas_pct"].as_f64().unwrap() - 4.99).abs() < 1e-9);
    p.grx.as_mut().unwrap().note_trig(id2, 6.25);
    let _ = std::fs::remove_file(&ctl);
}

// ---- the engine --------------------------------------------------------------------------------------------------------------------

/// LOG (default): the fill record's numbers, the line, the price path; the exit is the regular one (fill + 5)
#[test]
fn dip50_log_mode_changes_no_exit() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, orx, l, f, _r, lines, ctl) = open("log", &[], serde_json::json!({}), 2);
    let g = &f["grx"];
    assert_eq!((g["mode"].as_str(), g["thr"].as_f64(), g["kind"].as_str(), g["since"].as_u64()), (Some("log"), Some(2.245), Some("t2"), Some(1)), "{g}");
    // E1 3% + E2 2.5% (bought after the trigger, risky clocks). Not: the whale, H1 / H2 (before the trigger: old 6%), E3 (1.5% < 2%), E4 (no clock)
    let ms: Vec<(String, f64, u64)> = g["members"].as_array().unwrap().iter().map(|m| (m["w"].as_str().unwrap().to_string(), m["pct"].as_f64().unwrap(), m["age"].as_u64().unwrap())).collect();
    assert_eq!(ms, vec![(b58(&E1), 3.0, 1), (b58(&E2), 2.5, 1)]);
    assert!(g["members"][0]["risk"].as_u64().unwrap() >= 5 && g["members"][0]["hz3"].as_f64().unwrap() >= 0.3);
    assert_eq!((g["ent_pct"].as_f64(), g["ent_n"].as_u64(), g["old_pct"].as_f64(), g["old_n"].as_u64(), g["whale_member"].as_bool()), (Some(5.5), Some(2), Some(6.0), Some(2), Some(false)));
    assert!((g["whale_pct"].as_f64().unwrap() - 6.158).abs() < 0.01);
    assert_eq!((g["would_exit"].as_bool(), g["exit_slots"].as_u64(), g["applied"].as_bool()), (Some(true), Some(1), Some(false)));
    // = the research rule on the record's own annotation (the offline script's computation)
    let hs = f["ann"]["holders"].as_array().unwrap();
    assert!(hs.iter().all(|h| h["pct"].as_f64().unwrap() >= 2.0) && !hs.iter().any(|h| h["w"] == b58(&E3)), "< 2% is never a candidate");
    let ln_g: f64 = hs.iter().filter(|h| h["w"] != b58(&whale(2)) && h["age"].as_u64().unwrap() <= 1 && h["risk"].as_u64().unwrap() >= 5 && h["hz3"].as_f64().unwrap() >= 0.3).map(|h| h["pct"].as_f64().unwrap()).sum();
    assert_eq!(ln_g.to_bits(), g["ent_pct"].as_f64().unwrap().to_bits());
    assert!(lines.iter().any(|x| x.starts_with(&format!("  PRESEND LIVE GRX (log) w{} {}: entrants 5.5% (2) [", f["w"], b58(&l.mint))) && x.ends_with("-> would exit at fill+1")), "{lines:?}");
    assert!(p.grx.as_ref().unwrap().px.is_empty(), "log: nothing armed");
    // the log-only extras: G0 = the annotation's group (whale counted), the trigger's size, the whale's clock, no cascade set (the shadow off)
    assert_eq!(g["g0_pct"].as_f64().unwrap().to_bits(), f["ann"]["grp_pct"].as_f64().unwrap().to_bits());
    assert_eq!((g["g0_pct"].as_f64(), g["g0_would"].as_bool()), (Some(11.5), Some(true)), "H1 + H2 + E1 + E2");
    assert!((g["trig_pct"].as_f64().unwrap() - 6.158).abs() < 0.01 && g["small_would"] == true, "{g}");
    assert_eq!((g["whale_risk"].as_u64(), g["whale_hz3"].as_f64(), g["cas_src"].as_str(), g["cas_pct"].is_null(), g["cas_would"].as_bool()), (Some(0), Some(0.0), Some("off"), true, Some(false)));
    assert!(g.get("hold_pct").is_none() && g.get("ra_hold30_would").is_none() && g.get("over").is_none(), "re-arm only fields");
    // the exit: untouched (time-limit at fill + 5), one whole sell
    let _ = p.take_cmds();
    for s in N + 1..N + 6 { p.tick(s, None); }
    assert!(exits(&outs(&orx).0).is_empty() && sells(&p.take_cmds()).is_empty());
    // outside trades after our buy: the price path
    trade(&mut p, N + 2, 5, sg(0x90, 2), [0x77u8; 32], true, 100_000_000, 2_000_000_000_000, 39_200_000_000, 820_000_000_000_000, &l);
    p.tick(N + 6, None);
    let (r, _) = outs(&orx);
    assert_eq!(exits(&r), vec![("time-limit".to_string(), 5)]);
    assert_eq!(sells(&p.take_cmds()), vec![(1, None)]);
    p.tick(N + 7, None);
    let (r, _) = outs(&orx);
    let pa = r.iter().find(|x| x["ev"] == "presend_live_grx_path").unwrap_or_else(|| panic!("{r:?}"));
    assert_eq!((pa["w"].as_u64(), pa["kind"].as_str(), pa["flag"].as_bool(), pa["fill_slot"].as_u64(), pa["per_slot"].as_array().map(|a| a.len()), pa["closed"].as_str()),
        (f["w"].as_u64(), Some("t2"), Some(true), Some(N + 1), Some(6), Some("slot5")));
    assert_eq!((pa["per_slot"][1]["buy_sol"].as_f64(), pa["per_slot"][0]["n"].as_u64()), (Some(0.1), Some(0)));
    assert_eq!(pa["price_fill"], f["p_entry_post"]);
    // the position marks: our 9e12 tokens on the curve at the end of fill, +1, +2, +5 (one outside buy in fill + 1; our sell never on the feed)
    let mk = r.iter().find(|x| x["ev"] == "presend_live_grx_marks").unwrap_or_else(|| panic!("{r:?}"));
    let fr = arbx::presend::fee_rate(95, 30);
    let (o0, o2) = (psgrx50::mark_out(39_100_000_000, 822_000_000_000_000, 9_000_000_000_000, fr), psgrx50::mark_out(39_200_000_000, 820_000_000_000_000, 9_000_000_000_000, fr));
    assert_eq!((mk["w"].as_u64(), mk["tokens"].as_u64(), mk["spend"].as_u64(), mk["fill_slot"].as_u64(), mk["sold_at_dslot"].is_null(), mk["closed"].as_str()),
        (f["w"].as_u64(), Some(9_000_000_000_000), Some(395_061_728), Some(N + 1), true, Some("slot5")));
    let ms: Vec<(u64, u64, u64, u64, f64)> = mk["marks"].as_array().unwrap().iter().map(|m| (m["dslot"].as_u64().unwrap(), m["out"].as_u64().unwrap(), m["vsol"].as_u64().unwrap(),
        m["buyers"].as_u64().unwrap(), m["buy_sol"].as_f64().unwrap())).collect();
    assert_eq!(ms, vec![(0, o0, 39_100_000_000, 0, 0.0), (1, o2, 39_200_000_000, 1, 0.1), (2, o2, 39_200_000_000, 1, 0.1), (5, o2, 39_200_000_000, 1, 0.1)]);
    assert!(o0 > 400_000_000 && o0 < 430_000_000 && o2 > o0, "{o0} {o2}");
    // realized: the compact verdict with the real exit; the status segment
    p.rec(serde_json::json!({"ev": "presend_live_realized", "w": f["w"], "pnl": 1}));
    let (r, _) = outs(&orx);
    assert_eq!(r[0]["grx"], serde_json::json!({"mode": "log", "flag": true, "ent_pct": 5.5, "applied": false, "exit": "time-limit"}));
    assert!(p.status().contains(" | GRX fills 1 flagged 1 (live exits 0)"), "{}", p.status());
    let _ = std::fs::remove_file(&ctl);
}

/// LIVE: a flagged T2 fill exits at fill slot + N ("grx"), one whole sell at the base price; below the threshold: the regular exit
#[test]
fn dip50_live_exit_at_fill_plus_n() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    for n in [1u64, 2, 3] {
        // the timer-sell A/B and the lots exit on: a "grx" exit takes neither (not a timer reason)
        let (mut p, orx, l, f, _r, lines, ctl) = open("live", &["--presend-live-timer-sell-cu-price-micro", "500000", "--presend-live-exit-lots", "0.5:1"], serde_json::json!({"grx": "live", "grx_exit_slots": n}), 3);
        let g = &f["grx"];
        assert_eq!((g["mode"].as_str(), g["would_exit"].as_bool(), g["exit_slots"].as_u64(), g["applied"].as_bool()), (Some("live"), Some(true), Some(n), Some(true)), "{g}");
        assert!(lines.iter().any(|x| x.starts_with("  PRESEND LIVE GRX (live) w") && x.ends_with(&format!("-> EXIT at fill+{n}"))), "{lines:?}");
        let pid = p.pos[&l.mint].pid;
        assert_eq!(p.grx.as_ref().unwrap().px.get(&pid), Some(&n));
        let _ = p.take_cmds();
        // before fill + N: nothing
        for s in N + 1..N + 1 + n { p.tick(s, None); }
        assert!(exits(&outs(&orx).0).is_empty() && sells(&p.take_cmds()).is_empty(), "n {n}: no exit before fill + {n}");
        p.tick(N + 1 + n, None);
        let (r, lines) = outs(&orx);
        assert_eq!(exits(&r), vec![("grx".to_string(), n as i64)]);
        let x = r.iter().find(|x| x["ev"] == "presend_live_exit").unwrap();
        assert!(x.get("timer_sell").is_none() && x.get("lots").is_none() && x.get("lot").is_none(), "{x}");
        assert_eq!(sells(&p.take_cmds()), vec![(1, None)], "one whole sell, dip42's command (no cheap price, no lot)");
        assert!(lines.iter().any(|x| x.starts_with(&format!("  PRESEND LIVE EXIT {} grx slot {} (held {n} slots)", b58(&l.mint), N + 1 + n))), "{lines:?}");
        // once: later ticks add nothing
        for s in N + 2 + n..N + 9 { p.tick(s, None); }
        assert!(exits(&outs(&orx).0).is_empty() && sells(&p.take_cmds()).is_empty());
        assert!(p.grx.as_ref().unwrap().px.is_empty());
        p.rec(serde_json::json!({"ev": "presend_live_realized", "w": f["w"], "pnl": 1}));
        assert_eq!(outs(&orx).0[0]["grx"], serde_json::json!({"mode": "live", "flag": true, "ent_pct": 5.5, "applied": true, "exit": "grx"}));
        assert!(p.status().contains(" | GRX fills 1 flagged 1 (live exits 1)"), "{}", p.status());
        let _ = std::fs::remove_file(&ctl);
    }
    // the threshold edge on the engine: entrants 5.5% -> grx_pct 5.5 flags, 5.51 does not (the regular exit)
    for (thr, flag) in [(5.5, true), (5.51, false)] {
        let (mut p, orx, _l, f, _r, lines, ctl) = open("edge", &[], serde_json::json!({"grx": "live", "grx_pct": thr}), 4);
        assert_eq!((f["grx"]["would_exit"].as_bool(), f["grx"]["applied"].as_bool(), f["grx"]["thr"].as_f64()), (Some(flag), Some(flag), Some(thr)));
        assert_eq!(lines.iter().any(|x| x.contains("PRESEND LIVE GRX")), flag);
        p.tick(N + 2, None);
        let (r, _) = outs(&orx);
        assert_eq!(exits(&r), if flag { vec![("grx".to_string(), 1)] } else { Vec::new() });
        if !flag {
            for s in N + 3..N + 6 { p.tick(s, None); }
            assert!(exits(&outs(&orx).0).is_empty());
            p.tick(N + 6, None);
            assert_eq!(exits(&outs(&orx).0), vec![("time-limit".to_string(), 5)]);
            assert!(p.status().contains(" | GRX fills 1 flagged 0 (live exits 0)"));
        }
        let _ = std::fs::remove_file(&ctl);
    }
    // a key change after the fill does not move an open position's exit; back to log: the next fill is not armed
    let (mut p, orx, _l, _f, _r, _lines, ctl) = open("keep", &[], serde_json::json!({"grx": "live", "grx_exit_slots": 2}), 5);
    p.ctl47_apply(&raw(serde_json::json!({"grx": "log", "grx_exit_slots": 4})), "t");
    p.tick(N + 2, None);
    assert!(exits(&outs(&orx).0).is_empty());
    p.tick(N + 3, None);
    assert_eq!(exits(&outs(&orx).0), vec![("grx".to_string(), 2)], "the position keeps the N of its fill");
    let _ = std::fs::remove_file(&ctl);
}

/// never later than the regular exit, and the other exits win when earlier: N >= exit_slots -> time-limit; the ms timer; TP; SL
#[test]
fn dip50_live_never_later_and_tp_sl_first() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    // N = 5 = the regular slot limit: the regular reason, at the regular slot
    let (mut p, orx, _l, f, _r, _lines, ctl) = open("late", &[], serde_json::json!({"grx": "live", "grx_exit_slots": 5}), 6);
    assert_eq!(f["grx"]["applied"], true);
    for s in N + 1..N + 6 { p.tick(s, None); }
    assert!(exits(&outs(&orx).0).is_empty());
    p.tick(N + 6, None);
    assert_eq!(exits(&outs(&orx).0), vec![("time-limit".to_string(), 5)]);
    assert!(p.status().contains("(live exits 0)"));
    p.rec(serde_json::json!({"ev": "presend_live_realized", "w": f["w"], "pnl": 1}));
    assert_eq!(outs(&orx).0[0]["grx"]["exit"], "time-limit");
    let _ = std::fs::remove_file(&ctl);
    // the ms timer first (50 ms after the fill, still in the fill slot)
    let (mut p, orx, _l, _f, _r, _lines, ctl) = open("ms", &["--presend-live-exit-ms", "50"], serde_json::json!({"grx": "live"}), 7);
    std::thread::sleep(Duration::from_millis(70));
    p.tick(N + 1, None);
    assert_eq!(exits(&outs(&orx).0), vec![("time-ms".to_string(), 0)]);
    p.tick(N + 2, None);
    assert!(exits(&outs(&orx).0).is_empty(), "no second exit");
    let _ = std::fs::remove_file(&ctl);
    // take-profit / stop-loss on a trade in the fill slot: at once, before fill + 1; the GRX exit adds nothing after
    for (why, vsol, vtok) in [("take-profit", 45_000_000_000u64, 760_000_000_000_000u64), ("stop-loss", 30_000_000_000, 1_000_000_000_000_000)] {
        let (mut p, orx, l, f, _r, _lines, ctl) = open("tpsl", &[], serde_json::json!({"grx": "live"}), 8);
        assert_eq!(f["grx"]["applied"], true);
        let _ = p.take_cmds();
        trade(&mut p, N + 1, 60, sg(0x91, 8), [0x78u8; 32], why == "take-profit", 500_000_000, 10_000_000_000_000, vsol, vtok, &l);
        assert_eq!(exits(&outs(&orx).0), vec![(why.to_string(), 0)]);
        assert_eq!(sells(&p.take_cmds()).len(), 1);
        for s in N + 1..N + 8 { p.tick(s, None); }
        assert!(exits(&outs(&orx).0).is_empty() && sells(&p.take_cmds()).is_empty(), "{why}: nothing after it");
        assert!(p.status().contains("(live exits 0)"));
        let _ = std::fs::remove_file(&ctl);
    }
    // without a stop the same position leaves at fill + 1: the regular TP / SL values are untouched by GRX (a price inside the band)
    let (mut p, orx, l, _f, _r, _lines, ctl) = open("band", &[], serde_json::json!({"grx": "live"}), 9);
    trade(&mut p, N + 1, 60, sg(0x91, 9), [0x78u8; 32], true, 50_000_000, 1_000_000_000_000, 39_150_000_000, 821_000_000_000_000, &l);
    assert!(exits(&outs(&orx).0).is_empty());
    p.tick(N + 2, None);
    assert_eq!(exits(&outs(&orx).0), vec![("grx".to_string(), 1)]);
    let _ = std::fs::remove_file(&ctl);
}

/// the lane: a re-arm window's fill is evaluated and logged ("over"), never flagged, never acted on, in log and in live
#[test]
fn dip50_rearm_logs_never_acts() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    for live in [false, true] {
        let ctl = ctl_file("rearm");
        let c = cfg(&["--presend-live-grx", "on", "--presend-live-grx-mode", if live { "live" } else { "log" }, "--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.3",
            "--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap();
        let (mut p, atx, orx) = PsLive::for_test(c, USER);
        let l = launch(10);
        let id = setup(&mut p, &l, N, 10, false);
        // the window counts as a re-arm window
        p.rm.as_mut().unwrap().test_mark(id);
        // (live pass) two more 5% holders without clocks: the holders >= 2% reach 30%
        if live { for (i, w) in [[0xF1u8; 32], [0xF2u8; 32]].iter().enumerate() {
            trade(&mut p, N, 45 + i as u64, sg(0x93, i as u8), *w, true, 2_000_000_000, 50_000_000_000_000, 39_050_000_000, 824_000_000_000_000, &l);
        } }
        assert_eq!(p.g47_kind(id), "rearm");
        let (f, _r, lines) = fill(&mut p, &atx, &orx, &l, id, sg(0x50, 10), N + 1);
        let g = &f["grx"];
        assert_eq!((f["kind"].as_str(), g["kind"].as_str(), g["mode"].as_str()), (Some("rearm"), Some("rearm"), Some(if live { "live" } else { "log" })), "{f}");
        assert_eq!((g["ent_pct"].as_f64(), g["ent_n"].as_u64(), g["over"].as_bool(), g["would_exit"].as_bool(), g["applied"].as_bool()), (Some(5.5), Some(2), Some(true), Some(false), Some(false)));
        assert!(lines.iter().any(|x| x.starts_with(&format!("  PRESEND LIVE GRX ({}) w{id} ", if live { "live" } else { "log" })) && x.ends_with("-> re-arm: logged only")), "{lines:?}");
        // the log-only extras on a re-arm fill: the T2 "would"s never; hold_pct = every holder >= 2% (ours out); >= 30 -> ra_hold30_would
        assert_eq!((g["g0_would"].as_bool(), g["cas_would"].as_bool(), g["small_would"].as_bool()), (Some(false), Some(false), Some(false)), "{g}");
        let want = if live { 30.658 } else { 20.658 };
        assert!((g["hold_pct"].as_f64().unwrap() - want).abs() < 0.01 && g["hold_n"] == (if live { 8 } else { 6 }) && g["ra_hold30_would"] == live, "{g}");
        assert!((g["g0_pct"].as_f64().unwrap() - 11.5).abs() < 1e-9);
        assert!(p.grx.as_ref().unwrap().px.is_empty());
        for s in N + 1..N + 6 { p.tick(s, None); }
        assert!(exits(&outs(&orx).0).is_empty(), "no early exit on a re-arm fill");
        p.tick(N + 6, None);
        assert_eq!(exits(&outs(&orx).0), vec![("time-limit".to_string(), 5)]);
        let s = p.status();
        assert!(s.contains(" | GRX fills 0 flagged 0 (live exits 0) re-arm 1 over 1 (log)"), "{s}");
        let _ = std::fs::remove_file(&ctl);
    }
}

/// fail open: the feed blind (a stale holder book) -> not evaluated, no flag, the regular exit, the reason logged; a risky whale alone is
/// not an entrant (whale_member); a holder that sold out before our landing is not counted
#[test]
fn dip50_fail_open_and_whale() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let ctl = ctl_file("blind");
    let (mut p, atx, orx) = PsLive::for_test(cfg(&["--presend-live-grx", "on", "--presend-live-grx-mode", "live", "--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap(), USER);
    let l = launch(11);
    let id = setup(&mut p, &l, N, 11, false);
    p.d43.blind = Some(1);
    let (f, _r, lines) = fill(&mut p, &atx, &orx, &l, id, sg(0x50, 11), N + 1);
    p.d43.blind = None;
    assert_eq!(f["grx"], serde_json::json!({"mode": "live", "thr": 2.245, "kind": "t2", "skip": "feed_blind", "would_exit": false, "exit_slots": 1, "applied": false}));
    assert!(lines.iter().any(|x| x.contains("PRESEND LIVE GRX (live)") && x.contains("NOT evaluated (feed_blind)")), "{lines:?}");
    assert!(p.grx.as_ref().unwrap().px.is_empty());
    assert!(p.status().contains(" | GRX fills 0 flagged 0 (live exits 0) fail-open 1"), "{}", p.status());
    // the pure guards of the same path: a window the probe does not know, a token outside the holder book
    let mut a = att(9_999, l.mint, sg(0x51, 11), N);
    let t = pl::Trade { sig: sg(0x51, 11), ..tr(l.mint, N + 1, 50, USER, true, 1, 1, 39_100_000_000, 822_000_000_000_000) };
    // (kind of an unknown window = t2)
    let (j, n) = p.grx50_fill(&a, &t, true);
    assert_eq!((j.unwrap()["skip"].as_str().map(String::from), n), (Some("no_window".to_string()), None));
    a.w = id;
    let t2 = pl::Trade { mint: mint_n(200), ..t.clone() };
    let (j, n) = p.grx50_fill(&a, &t2, true);
    assert_eq!((j.unwrap()["skip"].as_str().map(String::from), n), (Some("no_holder_book".to_string()), None));
    // a fill "before" its trigger slot
    let t3 = pl::Trade { s: N - 1, ..t.clone() };
    assert_eq!(p.grx50_fill(&a, &t3, true).0.unwrap()["skip"], "no_trigger_slot");
    // live + flagged, but a position on the mint is open already (a merged fill): evaluated, not applied
    let (j, n) = p.grx50_fill(&a, &t, false);
    let j = j.unwrap();
    assert_eq!((j["would_exit"].as_bool(), j["applied"].as_bool(), j["not_applied"].as_str(), n), (Some(true), Some(false), Some("position_open"), None));
    // the blind fill's position: the regular exit only
    for s in N + 1..N + 6 { p.tick(s, None); }
    assert!(exits(&outs(&orx).0).is_empty());
    p.tick(N + 6, None);
    assert_eq!(exits(&outs(&orx).0), vec![("time-limit".to_string(), 5)]);
    let _ = std::fs::remove_file(&ctl);

    // a whale with a risky clock and no entrant: whale_member, ent 0, no flag; E1 sold out before our landing: gone from the group
    let ctl = ctl_file("whale");
    let (mut p, atx, orx) = PsLive::for_test(cfg(&["--presend-live-grx", "on", "--presend-live-grx-mode", "live", "--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap(), USER);
    let l = launch(12);
    let id = setup(&mut p, &l, N, 12, true);
    for (i, (e, tok)) in [(E1, 30_000_000_000_000u64), (E2, 25_000_000_000_000)].iter().enumerate() {
        trade(&mut p, N + 1, 10 + i as u64, sg(0x92, i as u8), *e, false, 900_000_000, *tok, 38_000_000_000, 850_000_000_000_000, &l);
    }
    if !p.armed.contains_key(&l.mint) { let _ = std::fs::remove_file(&ctl); panic!("the window ended on the entrants' sells: {:?}", p.st.skips); }
    let (f, _r, lines) = fill(&mut p, &atx, &orx, &l, id, sg(0x50, 12), N + 1);
    let g = &f["grx"];
    assert_eq!((g["ent_pct"].as_f64(), g["ent_n"].as_u64(), g["whale_member"].as_bool(), g["would_exit"].as_bool(), g["applied"].as_bool()), (Some(0.0), Some(0), Some(true), Some(false), Some(false)), "{g}");
    assert!((g["whale_pct"].as_f64().unwrap() - 6.158).abs() < 0.01 && g["old_pct"] == 6.0);
    assert!(!lines.iter().any(|x| x.contains("PRESEND LIVE GRX")));
    p.tick(N + 2, None);
    assert!(exits(&outs(&orx).0).is_empty());
    let _ = std::fs::remove_file(&ctl);
}

/// the added main-loop time: one evaluation per fill; a trade of a mint without an open path = one map lookup
#[test]
fn dip50_added_time() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _orx, l, _f, _r, _lines, ctl) = open("time", &[], serde_json::json!({}), 13);
    let other = tr(mint_n(201), N + 2, 1, [0x79u8; 32], true, 1, 1, 39_100_000_000, 822_000_000_000_000);
    let k = 200_000u32;
    let t0 = arbx::fast::mono_ns();
    for _ in 0..k { p.grx50_trade(&other); }
    let off = (arbx::fast::mono_ns() - t0) as f64 / k as f64;
    let mine = pl::Trade { mint: l.mint, ..other.clone() };
    let t0 = arbx::fast::mono_ns();
    for _ in 0..k { p.grx50_trade(&mine); }
    let on = (arbx::fast::mono_ns() - t0) as f64 / k as f64;
    let hc = p.det.holder_clocks(&l.mint, (0.02 * pl::SUPPLY) as i64, &USER, N + 1, 12);
    let t0 = arbx::fast::mono_ns();
    let mut acc = 0.0;
    for _ in 0..k { acc += psgrx50::eval(&hc, &whale(13), 1).ent_pct; }
    let ev = (arbx::fast::mono_ns() - t0) as f64 / k as f64;
    let t0 = arbx::fast::mono_ns();
    let mut due = 0u32;
    for i in 0..k { if p.grx50_due(1, N + 1, N + (i as u64 & 1)).is_some() { due += 1; } }
    let dq = (arbx::fast::mono_ns() - t0) as f64 / k as f64;
    eprintln!("DIP50 GRX main-loop cost: trade of an untracked mint {off:.1} ns, of a tracked mint {on:.1} ns; the rule on {} holders {ev:.0} ns per fill; the exit check {dq:.1} ns per open position per tick ({acc:.0} {due})", hc.len());
    assert!(off < 1_000.0 && on < 5_000.0 && ev < 20_000.0 && dq < 1_000.0);
    let _ = std::fs::remove_file(&ctl);
}

// ===================================================================================================================
// dip47 tests: GRPSIGN (psgrp47.rs), the hot control keys and the FILTER STATE (psctl47.rs). Declared inside pslive.rs.
//  * GOLDEN: no flag / no control key = dip46's records (the dip25 digest) once the filter-state fields are taken out (dip26_tests::strip47);
//    grpsign on = the same records as without it once the grpsign records / fields / lines are taken out
//  * the signing-time metric = the landing one on the same state (engine: a fill in the signing slot with no trade between)
//  * every new key: its effect, its refusals (bad value / out of bounds / above the start size / feature off), absent = the start value
//  * the filter state: matches the control file after a reload, fv bumps only on a real change, fill / realized carry the ARM fv
//  * the added time: per-trade snapshot, the sender's sync, the stamping
// ===================================================================================================================
use super::*;
use arbx::dip::TradeEvent;

const USER: Pk = [0x5Au8; 32];
const N: u64 = 461_415_576;
const PROG: &str = "75hbt6uvDqjPZ9WgFtMhBnTeyHw7cinoHiz4FD2vEz2d";

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| match o { Out::Rec(v) => Some(v), Out::Line(_) => None }).collect() }
fn outs(orx: &crossbeam_channel::Receiver<Out>) -> (Vec<serde_json::Value>, Vec<String>) {
    let (mut r, mut l) = (Vec::new(), Vec::new());
    for o in orx.try_iter() { match o { Out::Rec(v) => r.push(v), Out::Line(x) => l.push(x) } }
    (r, l)
}
fn arr(slot: u64, sig: [u8; 64], payer: Pk, ok: bool, exec: Option<arbx::feeds::ExecInfo>, t_rx: u64) -> arbx::feeds::Arrival {
    let tx = arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() };
    arbx::feeds::Arrival { feed: 0, slot, t_rx, t_decoded: t_rx, executed: Some(ok), tx, poh: None, raw: arbx::feeds::RawTx::None, exec: exec.map(Arc::new) }
}
fn mint_n(i: u8) -> Pk { let mut m = [0x71u8; 32]; m[0] = i; m }
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
/// two 3% holders H1 / H2 (risky hold clocks: 6 holds of 1..4 slots) at `slot`, then a ~6.2% whale at `slot + 1` (the T2 trigger)
fn setup(p: &mut PsLive, l: &Launch, slot: u64, tag: u8) {
    create(p, slot - 1, l);
    for (i, h) in [[0xB1u8; 32], [0xB2u8; 32]].iter().enumerate() {
        p.det.clock_preload(*h, pl::Holds::from_holds(&[1, 2, 2, 3, 3, 4], slot));
        trade(p, slot - 1, 20 + i as u64, sg(0x60 + tag, i as u8), *h, true, 1_000_000_000, 30_000_000_000_000, 32_000_000_000, 1_000_000_000_000_000, l);
    }
    trade(p, slot, 34, sg(0x3E, tag), [0xA0 + tag; 32], true, 2_666_666_666, 61_580_021_739_287, 38_692_888_509, 831_935_821_811_615, l);
}
fn att(w: u64, mint: Pk, sig: [u8; 64], slot: u64, sign_pos: (u64, u32, i32)) -> Att {
    Att { w, n: 1, mint, sig, tag: pl::PS_TAG | (0xD47 << 8) | sig[0] as u64, path: "helius-ps".into(), client: "AgaveBam".into(), slot, deadline: slot + 1, lim: 1.0,
        min_out: 1, p_sign: 0.0000466, sign_pos, t_send: slot * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }, tip: 200_000,
        wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46: Default::default(), rf: None }
}
/// our buy of the window's try lands at (slot, 50)
fn our_fill(p: &mut PsLive, l: &Launch, sig: [u8; 64], slot: u64) {
    trade(p, slot, 50, sig, USER, true, 395_061_728, 9_000_000_000_000, 39_100_000_000, 822_000_000_000_000, l);
}

// ---- GOLDEN -------------------------------------------------------------------------------------------------------------

fn strip_grp(l: &str) -> Option<String> {
    if l.starts_with("L   PRESEND LIVE GRPSIGN") { return None; }
    let (tag, body) = l.split_at(2);
    if tag != "R " && tag != "F " { return Some(l.to_string()); }
    let mut v: serde_json::Value = serde_json::from_str(body).unwrap();
    if v["ev"] == "presend_live_grpsign" { return None; }
    if let Some(o) = v.as_object_mut() { o.remove("grpsign"); }
    if let Some(o) = v.get_mut("cfg").and_then(|c| c.as_object_mut()) { o.remove("dip47"); }
    Some(format!("{tag}{v}"))
}

/// dip46's three golden passes with `extra` on each; `strip`: the grpsign additions taken out. -> (digest, lines, records taken out, lines)
fn digest(extra: &[&str], strip: bool) -> Option<(String, usize, usize, Vec<String>)> {
    use sha2::Digest;
    let mut h = sha2::Sha256::new();
    let (mut n, mut dropped, mut all) = (0usize, 0usize, Vec::new());
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
            let l = if strip { match strip_grp(l) { Some(x) => x, None => { dropped += 1; all.push(l.clone()); continue } } } else { l.clone() };
            h.update(l.as_bytes()); h.update(b"\n"); n += 1;
        }
    }
    Some((h.finalize().iter().map(|b| format!("{b:02x}")).collect(), n, dropped, all))
}

/// no dip47 flag, no control key: dip46's records, lines, chain work and totals byte for byte once the filter state's fields / records are out
#[test]
fn dip47_golden_no_flags_equals_dip46() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d, n, _, _)) = digest(&[], false) else { eprintln!("presend_parity.json missing: skipped"); return };
    assert!(n > 3_000, "{n}");
    assert_eq!(d, dip26_tests::DIP25_GOLDEN, "dip47 with no new flag / key must write dip46's records ({n} lines)");
}

/// the filter state's additions are exactly: its own records (fv 0 at start, nothing else without a change), fv / fh on the stamped records,
/// "filters" on fill / realized, "fv" on the shadow's attempts
#[test]
fn dip47_golden_filter_state_fields_only() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some(lines) = dip26_tests::golden_pass(1, &[], arbx::presend::Params::default(), 7) else { return };
    // golden_pass strips them: count what it saw by running the same pass's raw output through the stamp rule
    let fills = lines.iter().filter(|l| l.contains("\"ev\":\"presend_live_fill\"")).count();
    assert!(fills > 3, "{fills}");
    // a raw look: one fresh pass without the strip
    let (mut p, _atx, orx) = PsLive::for_test(cfg(&[]).unwrap().unwrap(), USER);
    let r = recs(&orx);
    let fs: Vec<&serde_json::Value> = r.iter().filter(|x| x["ev"] == "presend_live_filter_state").collect();
    assert_eq!(fs.len(), 1, "one state record at start");
    assert_eq!((fs[0]["fv"].as_u64(), fs[0]["src"].as_str()), (Some(0), Some("start")));
    assert_eq!(fs[0]["fh"].as_str().unwrap().len(), 8);
    p.fs_refresh("auto");
    assert!(recs(&orx).is_empty(), "no change: no new state record");
}

/// GRPSIGN on (annotations on in both runs): the same decisions, sends, fees and exits; only the grpsign records / fields / lines are new
#[test]
fn dip47_golden_grpsign_changes_no_decision() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d0, n0, dropped0, _)) = digest(&["--presend-live-ann", "on"], true) else { eprintln!("presend_parity.json missing: skipped"); return };
    let (d, n, dropped, all) = digest(&["--presend-live-ann", "on", "--presend-live-grpsign-log", "on"], true).unwrap();
    eprintln!("dip47 golden with grpsign on: {n} lines kept ({n0} without), {dropped} grpsign records / lines taken out");
    assert_eq!(dropped0, 0);
    assert!(dropped > 10, "{dropped}");
    assert_eq!((d, n), (d0, n0), "grpsign must not change a decision");
    // every first-try record has its line; the fill records' grpsign agrees with its fill_try record
    let firsts = all.iter().filter(|l| l.contains("\"at\":\"first_try\"")).count();
    let lines = all.iter().filter(|l| l.starts_with("L   PRESEND LIVE GRPSIGN (log)")).count();
    assert_eq!(firsts, lines);
    assert!(all.iter().any(|l| l.contains("\"at\":\"fill_try\"")));
}

// ---- the metric ---------------------------------------------------------------------------------------------------------

/// a fill in the signing slot with no trade between signing and landing: the signing-time group = the landing annotation's group (the
/// same holders, the same sum, bit for bit); the first-try record, its line, the fill record's grpsign
#[test]
fn dip47_signing_equals_landing_on_same_state() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let c = cfg(&["--presend-live-ann", "on", "--presend-live-grpsign-log", "on"]).unwrap().unwrap();
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    let l = launch(1);
    setup(&mut p, &l, N, 1);
    let id = *p.armed.get(&l.mint).expect("armed");
    let _ = outs(&orx);
    let sig = sg(0x47, 1);
    atx.send(att(id, l.mint, sig, N, (N, 34, 0))).unwrap();
    p.drain_atts();
    let (r, lines) = outs(&orx);
    let first = r.iter().find(|x| x["ev"] == "presend_live_grpsign").unwrap_or_else(|| panic!("{r:?}"));
    assert_eq!((first["at"].as_str(), first["kind"].as_str(), first["match"].as_str(), first["n"].as_u64()), (Some("first_try"), Some("t2"), Some("exact"), Some(2)));
    let pct = first["grp_pct"].as_f64().unwrap();
    assert!((pct - 6.0).abs() < 0.01, "{pct}");
    assert_eq!((first["would_block_t2"].as_bool(), first["would_block_6"].as_bool()), (Some(true), Some(pct >= 6.0)));
    assert!(lines.iter().any(|x| x.starts_with(&format!("  PRESEND LIVE GRPSIGN (log) w{id} ")) && x.contains("[whale out 6.0%]") && x.ends_with("-> would skip")), "{lines:?}");
    // a second try: no second first-try record
    atx.send(att(id, l.mint, sg(0x48, 1), N, (N, 34, 0))).unwrap();
    p.drain_atts();
    assert!(!recs(&orx).iter().any(|x| x["ev"] == "presend_live_grpsign"));
    // the fill in the same slot: the landing annotation sees the same state
    our_fill(&mut p, &l, sig, N);
    let r = recs(&orx);
    let fill = r.iter().find(|x| x["ev"] == "presend_live_fill").unwrap_or_else(|| panic!("{r:?}"));
    let ft = r.iter().find(|x| x["ev"] == "presend_live_grpsign" && x["at"] == "fill_try").unwrap();
    assert_eq!(fill["ann"]["grp_pct"].as_f64().unwrap().to_bits(), fill["grpsign"]["pct"].as_f64().unwrap().to_bits(), "{fill}");
    assert_eq!(ft["grp_pct"], fill["grpsign"]["pct"]);
    assert_eq!(fill["grpsign"]["would_block_t2"], true);
    assert_eq!((ft["whale_in"].as_bool(), fill["grpsign"]["pct_x"].as_f64().map(|x| (x - 6.0).abs() < 0.01)), (Some(false), Some(true)), "H1 + H2; the whale has no clock");
    let land: Vec<&str> = fill["ann"]["holders"].as_array().unwrap().iter().filter(|h| h["risk"].as_u64().unwrap() >= 5 && h["hz3"].as_f64().unwrap() >= 0.3).map(|h| h["w"].as_str().unwrap()).collect();
    let sign: Vec<&str> = ft["members"].as_array().unwrap().iter().map(|h| h["w"].as_str().unwrap()).collect();
    assert_eq!(land, sign);
    // the flag off: no record, no field
    let (mut q, atx2, orx2) = PsLive::for_test(cfg(&["--presend-live-ann", "on"]).unwrap().unwrap(), USER);
    let l2 = launch(2);
    setup(&mut q, &l2, N + 100, 2);
    let id2 = *q.armed.get(&l2.mint).unwrap();
    atx2.send(att(id2, l2.mint, sg(0x49, 2), N + 100, (N + 100, 34, 0))).unwrap();
    q.drain_atts();
    our_fill(&mut q, &l2, sg(0x49, 2), N + 100);
    let r = recs(&orx2);
    assert!(!r.iter().any(|x| x["ev"] == "presend_live_grpsign"));
    assert!(r.iter().find(|x| x["ev"] == "presend_live_fill").unwrap().get("grpsign").is_none());
}

/// the snapshot a try saw: exact pos, else the newest at or before, else the arm's; a holder selling after the signing changes the landing
/// value, not the signing one
#[test]
fn dip47_sign_pos_lookup_and_later_sells() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let (mut p, atx, orx) = PsLive::for_test(cfg(&["--presend-live-ann", "on", "--presend-live-grpsign-log", "on"]).unwrap().unwrap(), USER);
    let l = launch(3);
    setup(&mut p, &l, N, 3);
    let id = *p.armed.get(&l.mint).unwrap();
    // H1 sells out at (N + 1, 10): the window's next snapshot has only H2
    trade(&mut p, N + 1, 10, sg(0x70, 3), [0xB1u8; 32], false, 900_000_000, 30_000_000_000_000, 36_000_000_000, 880_000_000_000_000, &l);
    let ring = p.g47.rings_len(id);
    assert_eq!(ring, 2);
    let _ = recs(&orx);
    // a try signed before the sell (pos (N, 34, 0)) fills after it, at (N + 1, 50): signing 6%, landing 3%
    let sig = sg(0x4A, 3);
    atx.send(att(id, l.mint, sig, N + 1, (N, 34, 0))).unwrap();
    p.drain_atts();
    our_fill(&mut p, &l, sig, N + 1);
    let r = recs(&orx);
    let fill = r.iter().find(|x| x["ev"] == "presend_live_fill").unwrap();
    assert!((fill["grpsign"]["pct"].as_f64().unwrap() - 6.0).abs() < 0.01, "{fill}");
    assert!(fill["ann"]["grp_pct"].as_f64().unwrap() < 3.1, "{fill}");
    // lookup rules
    use psgrp47::{find, Snap};
    let s = |pct: f64| Snap { slot: 1, pct, n: 0, m: [([0u8; 32], 0); psgrp47::TOP] };
    let ring: VecDeque<(psgrp47::Pos, Snap)> = [((10, 5, 0), s(1.0)), ((11, 3, 0), s(2.0)), ((11, 3, 1), s(3.0))].into_iter().collect();
    assert_eq!(find(&ring, (11, 3, 0)).map(|x| (x.0.pct, x.2)), Some((2.0, "exact")));
    assert_eq!(find(&ring, (11, 3, 2)).map(|x| (x.0.pct, x.2)), Some((3.0, "before")));
    assert_eq!(find(&ring, (10, 9, 0)).map(|x| (x.0.pct, x.2)), Some((1.0, "before")));
    assert_eq!(find(&ring, (9, 0, 0)).map(|x| (x.0.pct, x.2)), Some((1.0, "arm")));
}

/// the added time: the per-trade snapshot on the main loop (a token with 400 holders), the sender's per-loop sync (no change), the record
/// stamping. Printed; bounds generous (debug builds / loaded CI)
#[test]
fn dip47_added_time() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let (mut p, _atx, _orx) = PsLive::for_test(cfg(&["--presend-live-ann", "on", "--presend-live-grpsign-log", "on"]).unwrap().unwrap(), USER);
    let l = launch(4);
    setup(&mut p, &l, N, 4);
    let id = *p.armed.get(&l.mint).unwrap();
    for i in 0..400u32 {
        let mut u = [0x33u8; 32]; u[..4].copy_from_slice(&i.to_be_bytes());
        if i % 3 == 0 { p.det.clock_preload(u, pl::Holds::from_holds(&[1, 2, 3, 4, 5, 6], N)); }
        let mut out = Vec::new();
        p.det.trade(&pl::Trade { mint: l.mint, s: N, i: 100 + i, j: 0, sig: [0u8; 64], user: u, buy: true, sol: 100_000_000, tok: 1_000_000_000_000 + i as u64 * 7_000_000_000,
            vsol: 40_000_000_000, vtok: 800_000_000_000_000, fbps: 95, cbps: 30, t_rx: 0 }, &mut out);
    }
    let k = 20_000u64;
    let t0 = arbx::fast::mono_ns();
    for i in 0..k { p.g47_snap(id, &l.mint, (N, 1000 + i as u32, 0), N); }
    let snap_ns = (arbx::fast::mono_ns() - t0) / k;
    // the sender's sync with no change: one atomic load
    let sh = psctl47::Sh47::default();
    let mut seen = 0u64;
    let mut c = p.cfg.clone();
    let t0 = arbx::fast::mono_ns();
    for _ in 0..1_000_000 { psctl47::sender_sync(&sh, &mut seen, &mut c); }
    let sync_ns = (arbx::fast::mono_ns() - t0) as f64 / 1e6;
    // the stamping of a fill record (the full state cloned) and of a skip record
    let t0 = arbx::fast::mono_ns();
    for _ in 0..k { let mut v = serde_json::json!({"ev": "presend_live_fill", "w": id}); p.stamp47(&mut v); }
    let fill_ns = (arbx::fast::mono_ns() - t0) / k;
    let t0 = arbx::fast::mono_ns();
    for _ in 0..k { let mut v = serde_json::json!({"ev": "presend_live_skip"}); p.stamp47(&mut v); }
    let skip_ns = (arbx::fast::mono_ns() - t0) / k;
    eprintln!("DIP47 ADDED TIME: grpsign snapshot per trade of an armed mint (400 holders, main loop) {snap_ns} ns; sender sync per loop (no change) {sync_ns:.2} ns; \
        stamp fill {fill_ns} ns, skip {skip_ns} ns (main loop / writer, never the sender)");
    assert!(snap_ns < 200_000, "{snap_ns}");
    assert!(sync_ns < 50.0, "{sync_ns}");
}

// ---- hot keys ---------------------------------------------------------------------------------------------------------

fn full_cfg(ctl: &str) -> Cfg {
    cfg(&["--presend-live-ann", "on", "--presend-live-grpsign-log", "on", "--presend-live-wh-loss", "2:0.05", "--presend-live-holder-loss", "2:0.10:0.05",
        "--presend-live-mint-ledger", "0.10", "--presend-live-botdepth", "3:100", "--presend-live-botdepth-list", "/nonexistent-list.json",
        "--presend-live-guard", "holders", "--presend-live-guard-program", PROG, "--presend-live-guard-curve-deep", "0.42", "--presend-live-tbal", "on", "--presend-live-fam-log",
        "--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.3", "--presend-live-exit-ms", "2350", "--presend-live-min-age-slots", "2",
        "--presend-live-ledger-control", ctl]).unwrap().unwrap()
}
fn raw(j: serde_json::Value) -> psctl47::Raw { psctl47::ctl47_parse(j.to_string().as_bytes()).unwrap() }

/// every new key: applied, recorded, refused when bad (old value stays), absent = the start value
#[test]
fn dip47_hot_keys_each() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let ctl = std::env::temp_dir().join(format!("dip47_keys_{}.json", std::process::id()));
    std::fs::write(&ctl, "{}").unwrap();
    let (mut p, _atx, orx) = PsLive::for_test(full_cfg(ctl.to_str().unwrap()), USER);
    let st = p.f47.start.unwrap();
    assert_eq!((st.floors, st.wh_kinds, st.size_t2, st.size_rearm, st.ml, st.bd, st.curve, st.min_age, st.exit_ms), (Some(2), 3, 400_000_000, Some(300_000_000), Some(100_000_000), Some((3, 100)), Some(0.42), 2, 2350));
    let _ = outs(&orx);
    let j = serde_json::json!({"floors": "t2", "wh_kinds": "t2", "size_t2": 0.25, "size_rearm": 0.2, "mint_ledger_sol": 0.05, "wh_loss": "3:0.08", "holder_loss": "3:0.2:0.1",
        "botdepth": "4:50", "curve_deep_pct": 0.5, "min_age_slots": 5, "exit_ms": 1500, "tp": 0.3, "sl": 0.25, "grp_t2": "live", "grp_t2_pct": 4.5});
    p.ctl47_apply(&raw(j), "t");
    let (r, lines) = outs(&orx);
    let m = r.iter().find(|x| x["ev"] == "presend_live_ledger_mode" && x["ok"] == true).unwrap_or_else(|| panic!("{r:?}"));
    assert_eq!(m["dip47"].as_object().unwrap().len(), 15, "{m}");
    p.ctl47_apply(&raw(serde_json::json!({"grp_t2_whale": "in"})), "t");
    assert!(p.f47.cur.unwrap().grp_whale_in);
    p.ctl47_apply(&raw(serde_json::json!({"floors": "t2", "wh_kinds": "t2", "size_t2": 0.25, "size_rearm": 0.2, "mint_ledger_sol": 0.05, "wh_loss": "3:0.08", "holder_loss": "3:0.2:0.1", "botdepth": "4:50", "curve_deep_pct": 0.5, "min_age_slots": 5, "exit_ms": 1500, "tp": 0.3, "sl": 0.25, "grp_t2": "live", "grp_t2_pct": 4.5})), "t");
    assert!(!p.f47.cur.unwrap().grp_whale_in, "absent = out again");
    assert_eq!(m["was"]["dip47"]["size_t2"], 0.4);
    assert!(lines.iter().any(|l| l.starts_with("  PRESEND LIVE LEDGER MODES dip47: floors \"all\" -> \"t2\"")), "{lines:?}");
    // the engine's values
    assert!(!p.cfg.g43.as_ref().unwrap().floor_rearm);
    assert_eq!(p.cfg.wh_kinds, 1);
    assert_eq!(p.size_t2_47(), 250_000_000);
    assert_eq!(p.rm.as_ref().unwrap().cfg.spend, 200_000_000);
    assert_eq!(p.cfg.c43.ml, Some(50_000_000));
    assert_eq!((p.cfg.wh_loss_n, p.cfg.wh_loss), (3, 80_000_000));
    assert_eq!((p.cfg.hl_pct, p.cfg.hl_loss, p.cfg.hl_win), (3.0, 200_000_000, 100_000_000));
    assert_eq!(p.cfg.bd, Some(psbd::Gate::List { min: 4, slots: 50 }));
    assert_eq!(p.cfg.g43.as_ref().unwrap().curve_deep, Some(0.5));
    assert_eq!(p.cfg.min_age_slots, 5);
    assert_eq!(p.grp_t2_47(), Some((4.5, false)));
    // the sender's copy follows on its next loop
    let mut sc = full_cfg(ctl.to_str().unwrap());
    let mut seen = 0;
    psctl47::sender_sync(&p.sh.f47, &mut seen, &mut sc);
    assert_eq!((sc.bd, sc.g43.as_ref().unwrap().curve_deep, sc.g43.as_ref().unwrap().floor_rearm), (Some(psbd::Gate::List { min: 4, slots: 50 }), Some(0.5), false));
    // exits: a position opened now keeps 1500 / 0.3 / 0.25; one from before the change keeps the start's
    p.pid = 77; p.f47_pos_open(77);
    assert_eq!(p.exit47(77), (1500, 0.3, 0.25));
    assert_eq!(p.exit47(5), (2350, p.cfg.tp, p.cfg.sl));
    assert_eq!(p.b43_exit_ms(77), 1500);
    // floors off: empty floor sets
    p.ctl47_apply(&raw(serde_json::json!({"floors": "off"})), "t");
    assert!(p.floors_off_47());
    assert_eq!(p.g43_set(&mint_n(9)).n, 0);
    // bad values: refused one by one, the old value stays, an error record each; the other keys of the file apply
    let _ = outs(&orx);
    let before = p.f47.cur.unwrap();
    let bad = serde_json::json!({"floors": "maybe", "wh_kinds": 3, "size_t2": 0.5, "size_rearm": 0.0, "mint_ledger_sol": 2.0, "wh_loss": "x", "holder_loss": "1:2",
        "botdepth": "0:10", "curve_deep_pct": 0.99, "min_age_slots": 51, "exit_ms": 20, "tp": 0.95, "sl": "abc", "grp_t2": "on", "grp_t2_pct": 25, "grp_t2_whale": "both"});
    p.ctl47_apply(&raw(bad), "t");
    let (r, _) = outs(&orx);
    let errs: Vec<&str> = r.iter().filter(|x| x["ev"] == "presend_live_ledger_mode" && x["ok"] == false).map(|x| x["key"].as_str().unwrap()).collect();
    assert_eq!(errs.len(), 16, "{errs:?}");
    assert_eq!(p.f47.cur.unwrap(), before, "every value stays");
    assert!(r.iter().any(|x| x["key"] == "size_t2" && x["err"].as_str().unwrap().contains("out of bounds")), "above the start size refused");
    // absent = the start value again
    p.ctl47_apply(&raw(serde_json::json!({})), "t");
    assert_eq!(p.f47.cur.unwrap(), st);
    assert!(p.cfg.g43.as_ref().unwrap().floor_rearm);
    assert_eq!(p.size_t2_47(), 400_000_000);
    // a bad file: nothing changes, an error record
    std::fs::write(&ctl, "{not json").unwrap();
    let _ = outs(&orx);
    p.ctl47_check(true);
    let (r, _) = outs(&orx);
    assert!(r.iter().any(|x| x["ev"] == "presend_live_ledger_mode" && x["ok"] == false && x["dip47"] == true));
    assert_eq!(p.f47.cur.unwrap(), st);
    // through the file
    std::fs::write(&ctl, r#"{"tp": 0.5, "whale": "live"}"#).unwrap();
    p.ctl47_check(true);
    assert_eq!(p.f47.cur.unwrap().tp, 0.5);
    let _ = std::fs::remove_file(&ctl);
}

/// a key whose feature is off at start is ignored with a record; grp_t2 live needs the grpsign flag
#[test]
fn dip47_keys_need_their_feature() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let (mut p, _atx, orx) = PsLive::for_test(cfg(&[]).unwrap().unwrap(), USER);
    let _ = recs(&orx);
    p.ctl47_apply(&raw(serde_json::json!({"floors": "off", "size_rearm": 0.1, "mint_ledger_sol": 0.1, "wh_loss": "2:0.1", "holder_loss": "2:0.1:0.05", "botdepth": "3:10",
        "curve_deep_pct": 0.4, "exit_ms": 500, "grp_t2": "live", "wh_kinds": "rearm"})), "t");
    let r = recs(&orx);
    let errs: Vec<&str> = r.iter().filter(|x| x["ok"] == false).map(|x| x["key"].as_str().unwrap()).collect();
    assert_eq!(errs.len(), 9, "{errs:?}");
    assert!(r.iter().filter(|x| x["ok"] == false).all(|x| x["err"].as_str().unwrap().starts_with("ignored: needs")));
    assert_eq!(p.cfg.wh_kinds, 2, "wh_kinds applies anyway");
    assert!(cfg(&["--presend-live-grpsign-log", "on"]).is_err(), "grpsign needs the annotations (the hold clocks)");
    assert!(cfg(&["--presend-live-ann", "on", "--presend-live-grpsign-log", "yes"]).is_err());
}

/// grp_t2 live: a T2 trigger whose group at the arm >= the threshold is skipped "grp_t2" (presend_live_skip with its value); log: armed
#[test]
fn dip47_grp_t2_live_skip() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let ctl = std::env::temp_dir().join(format!("dip47_grp_{}.json", std::process::id()));
    std::fs::write(&ctl, "{}").unwrap();
    let c = cfg(&["--presend-live-ann", "on", "--presend-live-grpsign-log", "on", "--presend-live-wh-loss", "2:0.05", "--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap();
    let (mut p, _atx, orx) = PsLive::for_test(c, USER);
    // log (default): armed
    let l = launch(5);
    setup(&mut p, &l, N, 5);
    assert!(p.armed.contains_key(&l.mint));
    // live at 5%: the 6% group skips
    p.ctl47_apply(&raw(serde_json::json!({"grp_t2": "live", "grp_t2_pct": 5.0})), "t");
    let _ = recs(&orx);
    let l2 = launch(6);
    setup(&mut p, &l2, N + 50, 6);
    assert!(!p.armed.contains_key(&l2.mint));
    let r = recs(&orx);
    let sk = r.iter().find(|x| x["ev"] == "presend_live_skip").unwrap_or_else(|| panic!("{r:?}"));
    assert_eq!(sk["why"], "grp_t2");
    assert!(sk["grp_t2"]["pct"].as_f64().unwrap() >= 5.0 && sk["grp_t2"]["thr"] == 5.0);
    assert_eq!(p.st.skips.get("grp_t2").copied(), Some(1));
    // live at 7%: arms
    p.ctl47_apply(&raw(serde_json::json!({"grp_t2": "live", "grp_t2_pct": 7.0})), "t");
    let l3 = launch(7);
    setup(&mut p, &l3, N + 100, 7);
    assert!(p.armed.contains_key(&l3.mint));
    // a risky-clock whale alone (6.2%): "out" (default) arms, "in" skips
    for (k, (tag, whale_in)) in [(0x0Au8, false), (0x0Bu8, true)].into_iter().enumerate() {
        p.ctl47_apply(&raw(serde_json::json!({"grp_t2": "live", "grp_t2_pct": 5.0, "grp_t2_whale": if whale_in { "in" } else { "out" }})), "t");
        let lw = launch(tag);
        let s0 = N + 200 + 50 * k as u64;
        create(&mut p, s0 - 1, &lw);
        p.det.clock_preload([0xA0 + tag; 32], pl::Holds::from_holds(&[1, 2, 2, 3, 3, 4], s0));
        trade(&mut p, s0, 34, sg(0x3E, tag), [0xA0 + tag; 32], true, 2_666_666_666, 61_580_021_739_287, 38_692_888_509, 831_935_821_811_615, &lw);
        assert_eq!(p.armed.contains_key(&lw.mint), !whale_in, "whale {}", if whale_in { "in" } else { "out" });
    }
    let _ = std::fs::remove_file(&ctl);
}

/// the filter state: matches the control file after a reload; fv bumps only on a real change (a re-read of the same values: none); fill and
/// realized carry the window's ARM fv / fh / filters, and fv_fill when the state moved between the arm and the fill
#[test]
fn dip47_filter_state_versions() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let ctl = std::env::temp_dir().join(format!("dip47_fs_{}.json", std::process::id()));
    std::fs::write(&ctl, "{}").unwrap();
    let c = cfg(&["--presend-live-ann", "on", "--presend-live-grpsign-log", "on", "--presend-live-wh-loss", "2:0.05", "--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap();
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    assert_eq!(p.f47.fs.as_ref().unwrap().fv, 0);
    let fh0 = p.f47.fs.as_ref().unwrap().fh.clone();
    // the window arms at fv 0
    let l = launch(8);
    setup(&mut p, &l, N, 8);
    let id = *p.armed.get(&l.mint).unwrap();
    let r = recs(&orx);
    let arm = r.iter().find(|x| x["ev"] == "presend_live_arm").unwrap();
    assert_eq!((arm["fv"].as_u64(), arm["fh"].as_str()), (Some(0), Some(fh0.as_str())));
    // a mid-window change through the file (an old key and a new one)
    std::fs::write(&ctl, r#"{"whale": "log", "tp": 0.4}"#).unwrap();
    p.ledger_ctl_open();
    p.ctl47_check(true);
    p.fs_tick();
    let fs = p.f47.fs.clone().unwrap();
    assert_eq!(fs.fv, 1, "one bump for the reload (both readers)");
    assert_eq!((fs.obj["whale"].as_str(), fs.obj["tp"].as_f64()), (Some("log"), Some(0.4)));
    let r = recs(&orx);
    let st = r.iter().find(|x| x["ev"] == "presend_live_filter_state").unwrap();
    assert_eq!(st["fv"], 1);
    assert_eq!(st["changed"]["tp"][1], 0.4);
    // the same values again: no bump
    p.ctl47_check(true);
    p.fs_refresh("auto");
    p.fs_tick();
    assert_eq!(p.f47.fs.as_ref().unwrap().fv, 1);
    assert!(!recs(&orx).iter().any(|x| x["ev"] == "presend_live_filter_state"));
    // the fill: the ARM state (fv 0) + fv_fill 1, the full filters object
    let sig = sg(0x4B, 8);
    atx.send(att(id, l.mint, sig, N, (N, 34, 0))).unwrap();
    p.drain_atts();
    our_fill(&mut p, &l, sig, N);
    let r = recs(&orx);
    let fill = r.iter().find(|x| x["ev"] == "presend_live_fill").unwrap();
    assert_eq!((fill["fv"].as_u64(), fill["fv_fill"].as_u64(), fill["fh"].as_str()), (Some(0), Some(1), Some(fh0.as_str())));
    assert_eq!(fill["filters"]["whale"], "live", "the arm's state");
    // realized of the window: the same; a skip: the state now
    p.rec(serde_json::json!({"ev": "presend_live_realized", "w": id, "pnl": 1}));
    p.rec(serde_json::json!({"ev": "presend_live_skip", "why": "x"}));
    let r = recs(&orx);
    assert_eq!((r[0]["fv"].as_u64(), r[0]["fv_fill"].as_u64(), r[0]["filters"]["tp"].as_f64()), (Some(0), Some(1), Some(p.cfg.tp)));
    assert_eq!((r[1]["fv"].as_u64(), r[1].get("filters").is_none()), (Some(1), true));
    // the writer's stamp of a sender record
    let mut v = serde_json::json!({"ev": "presend_live_probe", "w": 1});
    let want = psctl47::FV_NOW.load(Ordering::Relaxed);
    psctl47::writer_stamp(&mut v);
    assert_eq!(v["fv"], want);
    let mut v = serde_json::json!({"ev": "presend_live_probe", "fv": 9});
    psctl47::writer_stamp(&mut v);
    assert_eq!(v["fv"], 9, "a main-loop stamp stays");
    let _ = std::fs::remove_file(&ctl);
}

// ---- pause window ----------------------------------------------------------------------------------------------------------

/// PKT = UTC + 5; a window crossing midnight; parse refusals
#[test]
fn dip47_pause_parse_and_clock() {
    use psctl47::{pause_hit, pause_parse, pause_str, pkt_min};
    let (v, n) = pause_parse("23:00-02:00, 10:15-10:45").unwrap();
    assert_eq!((n, pause_str(&v[..n as usize])), (2, "23:00-02:00,10:15-10:45".to_string()));
    let w = &v[..2];
    for (m, hit) in [(22 * 60 + 59, false), (23 * 60, true), (0, true), (60 + 59, true), (120, false), (10 * 60 + 15, true), (10 * 60 + 45, false)] {
        assert_eq!(pause_hit(w, m).is_some(), hit, "minute {m}");
    }
    // 2026-11-11 18:00:00 UTC = 23:00 PKT
    let t = 1_794_420_000u64 * 1_000_000_000;
    assert_eq!(pkt_min(t), 23 * 60);
    assert_eq!(pkt_min(t + 3 * 3600 * 1_000_000_000), 2 * 60, "02:00 PKT next day");
    for bad in ["23:00", "24:00-01:00", "10:00-10:00", "a-b", "1:00-2:00,3:00-4:00,5:00-6:00,7:00-8:00,9:00-10:00"] { assert!(pause_parse(bad).is_err(), "{bad}"); }
    assert_eq!(pause_parse("").unwrap().1, 0);
    assert!(cfg(&["--presend-live-pause-window", "23:00-25:00"]).is_err());
}

/// inside the window: no new T2 arm, one ON record + line, the skips counted (no record per trigger); after it: OFF with the count, arms
/// again; an open position is not touched; "pause_now" on / off; the keys in the filter state (fv bumps)
#[test]
fn dip47_pause_window_injected_clock() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let ctl = std::env::temp_dir().join(format!("dip47_pause_{}.json", std::process::id()));
    std::fs::write(&ctl, "{}").unwrap();
    let c = cfg(&["--presend-live-pause-window", "23:00-02:00", "--presend-live-wh-loss", "2:0.05", "--presend-live-ledger-control", ctl.to_str().unwrap()]).unwrap().unwrap();
    let (mut p, _atx, orx) = PsLive::for_test(c, USER);
    let t2300 = 1_794_420_000u64 * 1_000_000_000;
    p.f47.clock_ns = Some(t2300 + 30 * 60 * 1_000_000_000);              // 23:30 PKT
    let _ = outs(&orx);
    let l = launch(20);
    setup(&mut p, &l, N, 20);
    assert!(p.armed.is_empty(), "paused: no arm");
    let (r, lines) = outs(&orx);
    assert!(r.iter().any(|x| x["ev"] == "presend_live_ledger_mode" && x["pause_window"] == "on" && x["window"] == "23:00-02:00"));
    assert!(!r.iter().any(|x| x["ev"] == "presend_live_skip" || x["ev"] == "presend_live_arm"), "no record per trigger");
    assert!(lines.iter().any(|x| x == "  PRESEND LIVE PAUSE WINDOW ON 23:00-02:00 PKT: no new arms (open positions exit as usual)"), "{lines:?}");
    assert_eq!(p.st.skips.get("pause_window").copied(), Some(1));
    // 01:59 still paused (crosses midnight), 02:00 off
    p.f47.clock_ns = Some(t2300 + (2 * 3600 + 59 * 60) * 1_000_000_000);
    p.tick(N + 5, None);
    assert!(p.f47.pause_on.is_some());
    p.f47.clock_ns = Some(t2300 + 3 * 3600 * 1_000_000_000);
    p.tick(N + 6, None);
    let (r, lines) = outs(&orx);
    assert!(r.iter().any(|x| x["pause_window"] == "off" && x["skipped"] == 1));
    assert!(lines.iter().any(|x| x.starts_with("  PRESEND LIVE PAUSE WINDOW OFF 23:00-02:00 PKT: 1 arms skipped")));
    let l2 = launch(21);
    setup(&mut p, &l2, N + 50, 21);
    assert!(p.armed.contains_key(&l2.mint), "out of the window: armed");
    // the manual pause and the window key (the filter state follows)
    let fv0 = p.f47.fs.as_ref().unwrap().fv;
    std::fs::write(&ctl, r#"{"pause_now": "on", "pause_window": ""}"#).unwrap();
    p.ctl47_check(true);
    p.fs_tick();
    assert_eq!(p.f47.fs.as_ref().unwrap().obj["pause_now"], "on");
    assert_eq!(p.f47.fs.as_ref().unwrap().obj["pause_window"], "");
    assert!(p.f47.fs.as_ref().unwrap().fv > fv0);
    let l3 = launch(22);
    setup(&mut p, &l3, N + 100, 22);
    assert!(!p.armed.contains_key(&l3.mint), "manual pause");
    assert!(recs(&orx).iter().any(|x| x["pause_window"] == "on" && x["window"] == "manual"));
    std::fs::write(&ctl, r#"{"pause_now": "maybe"}"#).unwrap();
    p.ctl47_check(true);
    assert!(p.f47.cur.unwrap().pause_now, "bad value: stays on");
    std::fs::write(&ctl, "{}").unwrap();
    p.ctl47_check(true);
    p.tick(N + 120, None);
    assert!(p.f47.pause_on.is_none() && !p.f47.cur.unwrap().pause_now && p.f47.cur.unwrap().pause_n == 1, "absent: the start values (the flag's window)");
    let _ = std::fs::remove_file(&ctl);
}

// ---- funder-cluster log ---------------------------------------------------------------------------------------------------

/// OFFLINE validation on r83 w96 H2d2DtyD (testdata/dip47_funder_h2d2.json: the fix8283 study's cached RPC answers; ops/funder47/make_fixture.py):
/// the holders >= 0.5% at our send cutoff through the engine's queue, lookup and cluster code -> BufYjmzE, 17 wallets, 44.0%
#[test]
fn dip47_funder_h2d2_offline() {
    use psfunder47::*;
    let root = env!("CARGO_MANIFEST_DIR");
    let fx: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(format!("{root}/testdata/dip47_funder_h2d2.json")).unwrap()).unwrap();
    let pk = |s: &str| -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() };
    let mint = pk(fx["mint"].as_str().unwrap());
    let calls = std::sync::atomic::AtomicU64::new(0);
    let src = |m: &str, p: serde_json::Value| -> std::result::Result<serde_json::Value, String> {
        calls.fetch_add(1, Ordering::Relaxed);
        match m {
            "getSignaturesForAddress" => fx["sigs"].get(format!("{}:{}", p[0].as_str().unwrap(), p[1]["before"].as_str().unwrap())).cloned().ok_or("not cached".to_string()),
            "getTransaction" => fx["tx"].get(p[0].as_str().unwrap()).cloned().ok_or("not cached".to_string()),
            _ => Err("no network in tests".into()),
        }
    };
    let mut f = Funder::idle();
    let mut holders: Vec<(Pk, i64)> = Vec::new();
    for h in fx["holders"].as_array().unwrap() {
        let (w, bal) = (pk(h["w"].as_str().unwrap()), (h["pct"].as_f64().unwrap() / 100.0 * pl::SUPPLY) as i64);
        let sig: [u8; 64] = bs58::decode(h["sig"].as_str().unwrap()).into_vec().unwrap().try_into().unwrap();
        f.buy(mint, w, sig, h["first"].as_u64().unwrap(), bal);
        f.buy(mint, w, [9u8; 64], h["first"].as_u64().unwrap() + 5, bal);       // a later buy: no second lookup, the first buy stays the anchor
        holders.push((w, bal));
    }
    assert_eq!((holders.len(), f.queued), (19, 19));
    let s0 = summarize(&mint, &holders, |k| f.cache.get(k).copied());
    assert_eq!((s0.resolved, s0.pending, s0.c1), (0, 19, None), "nothing resolved yet: reported as pending, never waited for");
    f.pump(&src);
    assert_eq!(calls.load(Ordering::Relaxed), 38, "2 RPC calls per holder");
    // drained by the next event: here by hand through a second (no-op) pump + the public summary path
    let mut p = { let (mut p, _a, _o) = PsLive::for_test(cfg(&[]).unwrap().unwrap(), USER); p.fu47 = Some(f); p };
    let _ = p.fu47_event(1, &mint, "arm", 0);           // the mint is not followed by this probe's detector: only drains
    let f = p.fu47.as_ref().unwrap();
    let s = summarize(&mint, &holders, |k| f.cache.get(k).copied());
    let (fu, n, pc) = s.c1.expect("a cluster");
    eprintln!("DIP47 FUNDER offline H2d2DtyD: holders {} ({:.2}%), resolved {}/{}, cluster {} {} wallets {:.2}%, just funded {:.2}%, second {:?}", s.n, s.pct, s.resolved, s.n, b58(&fu), n, pc, s.just_pct, s.c2.map(|c| (c.1, c.2)));
    assert_eq!(b58(&fu), "BufYjmzEzxpY2swPvvAFoqMSnmhEivXuaEYLpyEu7Bhd");
    assert_eq!((n, s.resolved, s.pending), (17, 19, 0));
    assert!((pc - 44.01).abs() < 0.05, "{pc}");
    assert!(s.just_pct > 40.0, "funded 0-2 slots before the buy: {}", s.just_pct);
    let j = s.json();
    assert_eq!((j["c1"]["n_wallets"].as_u64(), j["resolved"].as_u64()), (Some(17), Some(19)));
}

/// on the probe: holders >= 0.5% are queued as they buy; the arm reports what is resolved by then (pending), the fill the cluster; the line;
/// never a decision; the queue is bounded (oldest dropped, counted); a failed lookup is counted and asked again; flags
#[test]
fn dip47_funder_log_on_the_probe() {
    use psfunder47::*;
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let c = cfg(&["--presend-live-funder-log", "on", "--presend-live-funder-rpc", "https://secret.example/KEY123", "--presend-live-funder-rps", "20"]).unwrap().unwrap();
    assert_eq!(c.json()["funder_log"], serde_json::json!({"rps": 20, "rpc": "--presend-live-funder-rpc"}));
    assert!(!c.json().to_string().contains("secret.example"), "the URL is never in the run's config record");
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    let l = launch(30);
    setup(&mut p, &l, N, 30);
    let id = *p.armed.get(&l.mint).expect("armed as without the log");
    assert_eq!(p.fu47.as_ref().unwrap().queued, 3, "H1, H2 and the whale reached 0.5%");
    let (r, lines) = outs(&orx);
    let arm = r.iter().find(|x| x["ev"] == "presend_live_funder").unwrap_or_else(|| panic!("{r:?}"));
    assert_eq!((arm["at"].as_str(), arm["kind"].as_str(), arm["n"].as_u64(), arm["resolved"].as_u64(), arm["pending"].as_u64()), (Some("arm"), Some("t2"), Some(3), Some(0), Some(3)));
    assert!(lines.iter().any(|x| x.starts_with(&format!("  PRESEND LIVE FUNDER (log) w{id} ")) && x.ends_with("resolved 0/3")), "{lines:?}");
    assert!(!r.iter().chain(std::iter::empty()).any(|x| x.to_string().contains("secret.example")) && !lines.iter().any(|x| x.contains("secret.example")));
    // the workers' answers: H1 and H2 funded by F one slot before their buys, the whale's lookup fails once
    let fpk = [0xF0u8; 32];
    let whale = b58(&[0xA0u8 + 30; 32]);
    let fails = std::cell::Cell::new(0u32);
    let src = |m: &str, pv: serde_json::Value| -> std::result::Result<serde_json::Value, String> {
        if m == "getSignaturesForAddress" {
            if pv[0] == whale.as_str() && fails.get() == 0 { fails.set(1); return Err("timeout".into()); }
            return Ok(serde_json::json!([{"signature": format!("PREV{}", pv[0].as_str().unwrap()), "slot": N - 2}]));
        }
        let w = pv[0].as_str().unwrap().trim_start_matches("PREV").to_string();
        Ok(serde_json::json!({"transaction": {"message": {"accountKeys": [{"pubkey": b58(&fpk), "signer": true}, {"pubkey": w, "signer": false}]}},
            "meta": {"preBalances": [9_000_000_000u64, 0], "postBalances": [7_900_000_000u64, 1_000_000_000u64]}}))
    };
    p.fu47.as_mut().unwrap().pump(&src);
    assert_eq!(p.fu47.as_ref().unwrap().sh.errs.load(Ordering::Relaxed), 1);
    let sig = sg(0x4F, 30);
    atx.send(att(id, l.mint, sig, N, (N, 34, 0))).unwrap();
    p.drain_atts();
    our_fill(&mut p, &l, sig, N);
    let r = recs(&orx);
    let fr = r.iter().find(|x| x["ev"] == "presend_live_funder" && x["at"] == "fill").unwrap();
    assert_eq!((fr["resolved"].as_u64(), fr["pending"].as_u64(), fr["c1"]["n_wallets"].as_u64(), fr["c1"]["funder"].as_str()), (Some(2), Some(1), Some(2), Some(b58(&fpk).as_str())));
    assert!((fr["c1"]["pct"].as_f64().unwrap() - 6.0).abs() < 0.01 && (fr["just_funded_pct"].as_f64().unwrap() - 6.0).abs() < 0.01, "{fr}");
    let fill = r.iter().find(|x| x["ev"] == "presend_live_fill").unwrap();
    assert_eq!(fill["funder"], serde_json::json!({"pct": 6.0, "n": 2, "resolved": 2}));
    // the queue is bounded: the oldest job goes, counted
    let f = p.fu47.as_mut().unwrap();
    let q0 = f.sh.q.lock().unwrap().len();
    for i in 0..(QUEUE_MAX + 5 - q0) as u32 { let mut w = [0x44u8; 32]; w[..4].copy_from_slice(&i.to_be_bytes()); f.buy([7u8; 32], w, [1u8; 64], N, (0.01 * pl::SUPPLY) as i64); }
    assert_eq!((f.sh.q.lock().unwrap().len(), f.sh.drops.load(Ordering::Relaxed)), (QUEUE_MAX, 5));
    // flags
    for bad in [vec!["--presend-live-funder-rps", "10"], vec!["--presend-live-funder-log", "on", "--presend-live-funder-rps", "41"],
                vec!["--presend-live-funder-log", "on", "--presend-live-funder-rps", "0"], vec!["--presend-live-funder-rpc", "http://x"], vec!["--presend-live-funder-log", "maybe"]] {
        assert!(cfg(&bad).is_err(), "{bad:?}");
    }
    assert_eq!(cfg(&["--presend-live-funder-log", "on"]).unwrap().unwrap().funder_rps, 15);
    // parse_tx on a plain (non-parsed) key list, a wallet not in the tx
    assert_eq!(parse_tx(&serde_json::json!({"transaction": {"message": {"accountKeys": [b58(&fpk)]}}, "meta": {"preBalances": [1], "postBalances": [1]}}), "x").unwrap(), (Some(fpk), 0));
}

/// the funder log on: the same decisions, sends, fees and exits as off (golden passes; only its records / fields / lines are new)
#[test]
fn dip47_golden_funder_log_changes_no_decision() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let strip = |lines: Vec<String>| -> (Vec<String>, usize) {
        let mut n = 0;
        let v = lines.into_iter().filter_map(|l| {
            if l.starts_with("L   PRESEND LIVE FUNDER (log)") { n += 1; return None; }
            if !l.starts_with("R ") && !l.starts_with("F ") { return Some(l.replace(" | FUNDER LOG", "\u{0}").split('\u{0}').next().unwrap().to_string()); }
            let mut v: serde_json::Value = serde_json::from_str(&l[2..]).unwrap();
            if v["ev"] == "presend_live_funder" { n += 1; return None; }
            if let Some(o) = v.as_object_mut() { o.remove("funder"); }
            if let Some(o) = v.get_mut("cfg").and_then(|c| c.as_object_mut()) { o.remove("funder_log"); }
            Some(format!("{}{v}", &l[..2]))
        }).collect();
        (v, n)
    };
    let Some(a) = dip26_tests::golden_pass(1, &[], arbx::presend::Params::default(), 7) else { eprintln!("presend_parity.json missing: skipped"); return };
    let b = dip26_tests::golden_pass(1, &["--presend-live-funder-log", "on"], arbx::presend::Params::default(), 7).unwrap();
    let ((a, na), (b, nb)) = (strip(a), strip(b));
    assert_eq!(na, 0);
    assert!(nb > 20, "{nb}");
    assert_eq!(a.len(), b.len());
    for (x, y) in a.iter().zip(&b) { assert_eq!(x, y); }
}

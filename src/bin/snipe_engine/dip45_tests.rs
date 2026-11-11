// ===================================================================================================================
// dip45 FLEET SIGNAL shadow tests (ps45_fleet.rs; LOG ONLY). Declared inside pslive.rs.
//  * GOLDEN: no new flag = dip43g's records byte for byte (the dip25 digest), also with fleet-shape tries injected into the tape;
//    the fleet log on (with the injected tries) = the same digest once its records / fields are taken out (no decision, send, fee or
//    exit changes)
//  * the detector on REAL fleet tries (testdata/dip45_fleet_fixtures.json: 6 fleet txs fetched from chain, signatures from the
//    recorder tape, 4 CU prices, one landed buy) and on look-alikes (other Lighthouse bots, our own pre-send try, edited fleet txs)
//  * the per-slot window counts; fleet arms; our arm / fill / would-fill annotations; the follower monitor; silence; the sig file
// ===================================================================================================================
use super::*;
use super::ps45_fleet::*;

const USER: Pk = [0x5Au8; 32];

fn pk(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }

fn fixtures() -> Vec<(String, arbx::tx::Tx)> {
    let root = env!("CARGO_MANIFEST_DIR");
    let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(format!("{root}/testdata/dip45_fleet_fixtures.json")).unwrap()).unwrap();
    use base64::Engine as _;
    v.as_array().unwrap().iter().map(|t| {
        let raw = base64::engine::general_purpose::STANDARD.decode(t["b64"].as_str().unwrap()).unwrap();
        let (tx, n) = arbx::tx::parse_wire(&raw).unwrap();
        assert_eq!(n, raw.len());
        (t["label"].as_str().unwrap().to_string(), tx)
    }).collect()
}

/// a real fleet try (fixture fleet_cup32000) re-pointed at `mint`, with its own signature
pub(super) fn fleet_tx(mint: Pk, n: u64) -> arbx::tx::Tx {
    let mut tx = fixtures().into_iter().find(|f| f.0 == "fleet_cup32000").unwrap().1;
    let k = tx.ixs[7].accounts[1] as usize;
    tx.keys[k] = mint;
    tx.sig = [0u8; 64]; tx.sig[..8].copy_from_slice(&n.to_be_bytes()); tx.sig[8] = 0xF1;
    tx
}

/// the golden passes' injected try: an unexecuted (shred) arrival
pub(super) fn fleet_arrival(mint: Pk, slot: u64, t: u64, n: u64) -> arbx::feeds::Arrival {
    arbx::feeds::Arrival { feed: 1, slot, t_rx: t, t_decoded: t, executed: None, tx: fleet_tx(mint, slot * 10_000 + n), poh: None, raw: arbx::feeds::RawTx::None, exec: None }
}

// ---- GOLDEN -------------------------------------------------------------------------------------------------------------

pub(super) fn strip45(l: &str) -> Option<String> {
    let (tag, body) = l.split_at(2);
    if tag != "R " && tag != "F " { return Some(l.to_string()); }
    let mut v: serde_json::Value = serde_json::from_str(body).unwrap();
    if v["ev"] == "presend_live_fleet" || v["ev"] == "presend_live_b1" { return None; }
    if let Some(o) = v.as_object_mut() { o.remove("fleet"); }
    if let Some(o) = v.get_mut("cfg").and_then(|c| c.as_object_mut()) { o.remove("fleet"); }
    Some(format!("{tag}{v}"))
}

pub(super) fn digest(extra: &[&str], inject: bool, strip: bool) -> Option<(String, usize, usize, Vec<serde_json::Value>)> {
    use sha2::Digest;
    dip26_tests::GOLDEN_FLEET.with(|c| c.set(inject));
    let mut h = sha2::Sha256::new();
    let (mut n, mut dropped, mut fl) = (0usize, 0usize, Vec::new());
    let passes: [(u8, Vec<&str>, arbx::presend::Params, u64); 3] = [
        (1, vec![], arbx::presend::Params::default(), 7),
        (2, vec!["--presend-live-k", "8", "--presend-live-size-sol", "0.696", "--presend-live-quiet-stop", "5:2", "--presend-live-quiet-skip", "on", "--presend-live-fbots",
            "/unused-in-tests.json", "--presend-live-quiet-fol", "4.0", "--presend-live-quiet-v2-log", "--presend-live-min-age-slots", "2"],
            arbx::presend::Params { whale_pct: 6.0, tp: 0.20, ..Default::default() }, 5),
        (3, vec!["--presend-live-fee-budget-sol", "0.0005"], arbx::presend::Params::default(), 0),
    ];
    for (tag, mut ex, ps, fe) in passes {
        ex.extend_from_slice(extra);
        let lines = dip26_tests::golden_pass(tag, &ex, ps, fe);
        let Some(lines) = lines else { dip26_tests::GOLDEN_FLEET.with(|c| c.set(false)); return None };
        h.update([tag]);
        for l in &lines {
            if l.starts_with("R ") && (l.contains("\"presend_live_fleet\"") || l.contains("\"presend_live_b1\"")) { fl.push(serde_json::from_str(&l[2..]).unwrap()); }
            let l = if strip { match strip45(l) { Some(x) => x, None => { dropped += 1; continue } } } else { l.clone() };
            h.update(l.as_bytes()); h.update(b"\n"); n += 1;
        }
    }
    dip26_tests::GOLDEN_FLEET.with(|c| c.set(false));
    Some((h.finalize().iter().map(|b| format!("{b:02x}")).collect(), n, dropped, fl))
}

/// no dip45 flag: dip43g's records, lines, chain work and totals byte for byte (the dip25 digest), with and without fleet tries on the tape
#[test]
fn dip45_golden_no_flags_equals_dip43g() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d, n, _, _)) = digest(&[], false, false) else { eprintln!("presend_parity.json missing: skipped"); return };
    assert!(n > 3_000, "{n}");
    assert_eq!(d, dip26_tests::DIP25_GOLDEN, "dip45 with no new flag must write dip43g's records ({n} lines)");
    let (d2, n2, _, fl) = digest(&[], true, false).unwrap();
    assert!(fl.is_empty());
    assert_eq!((d2, n2), (d, n), "fleet tries on the feed change nothing with the flag off");
}

/// the fleet log on, fleet tries on the tape: the same decisions, sends, fees and exits (its records / fields taken out = the no-flag digest)
#[test]
fn dip45_golden_fleet_log_changes_no_decision() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d0, n0, dropped0, _)) = digest(&[], false, true) else { eprintln!("presend_parity.json missing: skipped"); return };
    let (d, n, dropped, fl) = digest(&["--presend-live-fleet-log", "on"], true, true).unwrap();
    let st = |s: &str| fl.iter().filter(|r| r["stage"] == s).count();
    eprintln!("dip45 golden with the fleet log: {n} lines kept ({n0} without), {dropped} fleet records taken out: config {} fleet_arm {} arm {} fill {} follow {}",
        st("config"), st("fleet_arm"), st("arm"), st("fill"), st("follow"));
    assert_eq!(dropped0, 0);
    assert_eq!(st("config"), 3);
    assert!(st("fleet_arm") > 10 && st("arm") > 10 && st("fill") > 3 && st("follow") > 3, "the shadow saw the injected tries and our arms / fills");
    // an arm on a token with an injected try every tape tx: the flags say so
    assert!(fl.iter().any(|r| r["stage"] == "arm" && r["fleet"]["on8"] == true));
    assert_eq!((d, n), (d0, n0), "the fleet log must not change a decision");
}

// ---- flags --------------------------------------------------------------------------------------------------------------

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-size-sol", "0.4"]
        .iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }

#[test]
fn dip45_flags_and_refusals() {
    let c = cfg(&[]).unwrap().unwrap();
    assert!(c.fleet.is_none());
    assert!(c.json().get("fleet").is_none());
    let c = cfg(&["--presend-live-fleet-log", "on"]).unwrap().unwrap();
    assert!(c.fleet.as_ref().unwrap().sig.is_none());
    assert!(cfg(&["--presend-live-fleet-log", "off"]).unwrap().unwrap().fleet.is_none());
    assert!(cfg(&["--presend-live-fleet-log", "maybe"]).is_err());
    assert!(cfg(&["--presend-live-fleet-sig", "/x.json"]).is_err(), "the sig file needs the switch");
    assert!(cfg(&["--presend-live-fleet-log", "on", "--presend-live-fleet-sig", "/nonexistent/sig.json"]).is_err());
    let f = std::env::temp_dir().join(format!("dip45_sig_{}.json", std::process::id()));
    std::fs::write(&f, DEFAULT_SIG).unwrap();
    let c = cfg(&["--presend-live-fleet-log", "on", "--presend-live-fleet-sig", f.to_str().unwrap()]).unwrap().unwrap();
    assert_eq!(c.json()["fleet"]["sig"], f.to_str().unwrap());
    std::fs::write(&f, "{\"layout\": []}").unwrap();
    assert!(cfg(&["--presend-live-fleet-log", "on", "--presend-live-fleet-sig", f.to_str().unwrap()]).is_err());
    let _ = std::fs::remove_file(&f);
    // needs --presend-live
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-shadow", "--presend-live-fleet-log", "on"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1_000_000_000).is_err());
    // dry mode (no --live): accepted
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-shadow", "--presend-live", "--presend-live-dry", "--presend-live-routes", "default=helius-ps", "--presend-live-fleet-log", "on"]
        .iter().map(|s| s.to_string()).collect();
    let c = Cfg::from_argv(&a, &arbx::presend::Params::default(), false, 1_000_000_000).unwrap().unwrap();
    assert!(c.dry && c.fleet.is_some());
}

// ---- the detector -------------------------------------------------------------------------------------------------------

#[test]
fn dip45_detector_on_real_fleet_tries_and_lookalikes() {
    let s = Sig::builtin();
    let fx = fixtures();
    assert_eq!(fx.len(), 10);
    let want: &[(&str, &str, &str, u64)] = &[
        ("fleet_cup32000", "3nvifkgA4H7K8pUErt45uGSjgDjhD2cpMDrThvXv17oX", "J3ALGBijfyzjhNQFaoi3uKTmxdUf94VjsXDnouVNpump", 32000),
        ("fleet_cup12510", "3nvifkgA4H7K8pUErt45uGSjgDjhD2cpMDrThvXv17oX", "J9LwD3DgcnhKPQdKCHRuPPbbD8pwY98SeG5kQQNQv7bH", 12510),
        ("fleet_cup11298", "3nvifkgA4H7K8pUErt45uGSjgDjhD2cpMDrThvXv17oX", "6wzYWB2ZRw5dNjfR2e48nhqKVDuMGBBGGJnnKEwUpump", 11298),
        ("fleet_cup13219", "3nvifkgA4H7K8pUErt45uGSjgDjhD2cpMDrThvXv17oX", "Fb4CrM4RZRK2u6nW4ELHmAvKSVW1v9QWgzgZFKN8pump", 13219),
        ("fleet_cup32000_b", "9yjve3D5wi5uXkb8ANrz8Ym3W6qPASLCuqhSPj2r3tTU", "BAhtHKiK6QkoXHxA2GQQLd2StPWZ2N28vHKSxcimvdNT", 32000),
        ("fleet_ok", "3nvifkgA4H7K8pUErt45uGSjgDjhD2cpMDrThvXv17oX", "Fb4CrM4RZRK2u6nW4ELHmAvKSVW1v9QWgzgZFKN8pump", 32000),
    ];
    for (lab, signer, mint, cup) in want {
        let tx = &fx.iter().find(|f| f.0 == *lab).unwrap().1;
        let h = classify(tx, &s).unwrap_or_else(|| panic!("{lab} not detected"));
        assert_eq!(h.class, Class::Fleet, "{lab}");
        assert_eq!((h.signer, h.mint, h.cu_price), (pk(signer), pk(mint), *cup), "{lab}");
        assert!((40_000..=80_000).contains(&h.cu_limit), "{lab} {}", h.cu_limit);
    }
    for lab in ["other_same_programs_cup6", "other_lh_cup11200", "other_lh_cup6", "ours_r82_try"] {
        assert!(classify(&fx.iter().find(|f| f.0 == lab).unwrap().1, &s).is_none(), "{lab} is not the fleet");
    }
    // edited fleet txs: another CU price / limit = "shape" (drift); a tip transfer added, a second signer, a lookup table = not the fleet
    let base = fx.iter().find(|f| f.0 == "fleet_cup32000").unwrap().1.clone();
    let mut t = base.clone(); t.ixs[1].data[1..9].copy_from_slice(&50_000u64.to_le_bytes());
    let h = classify(&t, &s).unwrap(); assert_eq!((h.class, h.cu_price), (Class::Shape, 50_000));
    let mut t = base.clone(); t.ixs[0].data[1..5].copy_from_slice(&200_000u32.to_le_bytes());
    assert_eq!(classify(&t, &s).unwrap().class, Class::Shape);
    let mut t = base.clone(); t.ixs.push(arbx::tx::Ix { program: t.ixs[5].program, accounts: vec![0, 1], data: vec![2, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0] });
    assert!(classify(&t, &s).is_none(), "a tip transfer: 9 instructions");
    let mut t = base.clone(); t.num_signers = 2; assert!(classify(&t, &s).is_none());
    let mut t = base.clone(); t.lookups.push(arbx::tx::Lookup { table: [1u8; 32], writable: vec![], readonly: vec![] }); assert!(classify(&t, &s).is_none());
    let mut t = base.clone(); t.ixs[7].data[0] = 0x66; assert!(classify(&t, &s).is_none(), "another pump instruction");
    let mut t = base.clone(); t.ixs.swap(3, 4); assert!(classify(&t, &s).is_none(), "the Lighthouse order");
    // a wider signature file: 50,000 accepted
    let s2 = Sig::parse(DEFAULT_SIG.replace("[32000]", "[32000, 50000]").as_bytes()).unwrap();
    let mut t = base.clone(); t.ixs[1].data[1..9].copy_from_slice(&50_000u64.to_le_bytes());
    assert_eq!(classify(&t, &s2).unwrap().class, Class::Fleet);
    assert!(Sig::parse(b"{\"cu_prices\": [1], \"cu_limit\": [1, 2], \"layout\": [\"zz:00\"]}").is_err());
    assert!(Sig::parse(b"{\"cu_prices\": [1], \"cu_limit\": [1, 2], \"layout\": [\"cb:0\"]}").is_err());
    assert_eq!(Sig::parse(&serde_json::to_vec(&s.json()).unwrap()).unwrap(), s, "the json round trip");
}

// ---- the state ----------------------------------------------------------------------------------------------------------

fn hit(mint: Pk, signer: Pk) -> Hit { Hit { class: Class::Fleet, mint, signer, cu_price: 32_000, cu_limit: 55_951 } }
fn fleet() -> Fleet { Fleet::open(FleetCfg { sig: None, b1: None }).0 }
const T0: u64 = 1_800_000_000_000_000_000;
fn ts(slot: u64) -> u64 { T0 + slot * 400_000_000 }

#[test]
fn dip45_window_counts_and_arms() {
    let mut f = fleet();
    let mut out = Vec::new();
    let (m, a, b) = ([7u8; 32], [1u8; 32], [2u8; 32]);
    for s in 90..=100 { f.slot_start(s, ts(s), &mut out); }
    // tries: slot 91 (a), 95 (a x2), 99 (b), 100 (a, this slot)
    let tries = [(91u64, a, 1u64), (95, a, 2), (95, a, 3), (99, b, 4), (100, a, 5)];
    for (s, w, n) in tries { f.sighting(&hit(m, w), n, s, ts(s) + 10_000_000, 0, 1, true, &mut out); }
    // the same try again on the executed feed: not counted twice
    f.sighting(&hit(m, a), 5, 100, ts(100) + 90_000_000, 0, 4, false, &mut out);
    let fl = f.flags(&m, 100);
    assert_eq!((fl.n0, fl.n1, fl.n2, fl.n3, fl.n8, fl.signers8), (1, 1, 1, 1, 3, 2));
    assert_eq!((fl.first_slot, fl.last_slot), (Some(91), Some(100)));
    let fl = f.flags(&m, 97);
    assert_eq!((fl.n0, fl.n1, fl.n2, fl.n3, fl.n8, fl.last_slot), (0, 0, 2, 2, 3, Some(95)));
    assert_eq!(f.flags(&m, 90), Flags::default());
    assert_eq!(f.flags(&[9u8; 32], 100), Flags::default());
    assert_eq!(f.st.tries.load(Ordering::Relaxed), 5);
    assert_eq!(f.st.exec.load(Ordering::Relaxed), 1);
    // the arm closes 6 slots after its last try; its record: per slot counts, before the slot ended
    for s in 101..=105 { f.slot_start(s, ts(s), &mut out); }
    assert!(out.iter().all(|r| r["stage"] != "fleet_arm"));
    f.slot_start(106, ts(106), &mut out);
    f.slot_start(107, ts(107), &mut out);
    let r = out.iter().find(|r| r["stage"] == "fleet_arm").unwrap();
    assert_eq!((r["s0"].as_u64(), r["s1"].as_u64(), r["n"].as_u64(), r["n_slots"].as_u64(), r["slots_pre_by_end"].as_u64()), (Some(91), Some(100), Some(5), Some(4), Some(4)));
    assert_eq!(r["signers"].as_array().unwrap().len(), 2);
    assert_eq!(r["slots"][3], serde_json::json!([9, 1, 1, 1, 1]));
    // a try seen only after its slot ended (next slot started) and an exec-only try
    let mut out = Vec::new();
    f.sighting(&hit(m, a), 20, 107, ts(108) + 1, 0, 1, true, &mut out);
    f.sighting(&hit(m, a), 21, 107, ts(107) + 5, 0, 4, false, &mut out);
    for s in 108..=113 { f.slot_start(s, ts(s), &mut out); }
    let r = out.iter().find(|r| r["stage"] == "fleet_arm").unwrap();
    assert_eq!((r["n_slots"].as_u64(), r["slots_pre_by_end"].as_u64()), (Some(1), Some(0)));
    assert_eq!(r["slots"][0], serde_json::json!([0, 2, 1, 1, 0]));
    assert!(f.status().contains("FLEET LOG: tries 7"), "{}", f.status());
}

#[test]
fn dip45_ours_follow_and_silence() {
    let mut f = fleet();
    let mut out = Vec::new();
    let (m, a, d, x, y) = ([7u8; 32], [1u8; 32], [3u8; 32], [4u8; 32], [5u8; 32]);
    f.slot_start(200, ts(200), &mut out);
    f.sighting(&hit(m, a), 1, 198, ts(198), 0, 1, true, &mut out);
    let ev = |stage: &'static str, slot: u64, idx: Option<u32>, dump: Option<(u64, u32)>| OurEv { stage, w: 3, kind: "t2".into(), mint: m, slot, idx, dump, sig: None, sol_in: None, dry: false, en: None };
    f.our(ev("arm", 200, None, None), &mut out);
    let r = out.last().unwrap();
    assert_eq!((r["stage"].as_str(), r["fleet"]["n2"].as_u64(), r["fleet"]["on8"].as_bool()), (Some("arm"), Some(1), Some(true)));
    // the tape: a dump at (201, 10), a buyer at (201, 14), our fill at (201, 20), later buys / a sell
    let tr = |s, i, u, buy, sol, ours| FT { slot: s, idx: i, j: 0, user: u, buy, sol, ours };
    for t in [tr(201, 10, d, false, 3_000_000_000, false), tr(201, 14, x, true, 500_000_000, false), tr(201, 20, USER, true, 800_000_000, true),
              tr(202, 3, y, true, 700_000_000, false), tr(203, 1, x, false, 100_000_000, false), tr(204, 5, y, true, 900_000_000, false), tr(206, 1, y, true, 1, false)] { f.trade(&m, t); }
    f.our(ev("fill", 201, Some(20), None), &mut out);
    f.our(ev("shadow_fill", 201, None, Some((201, 10))), &mut out);
    for s in 201..=204 { f.slot_start(s, ts(s), &mut out); }
    assert!(out.iter().all(|r| r["stage"] != "follow"));
    f.slot_start(205, ts(205), &mut out);
    let fo: Vec<&serde_json::Value> = out.iter().filter(|r| r["stage"] == "follow").collect();
    assert_eq!(fo.len(), 2);
    let real = fo.iter().find(|r| r["of"] == "fill").unwrap();
    assert_eq!(real["dump"]["idx"], 10);
    assert_eq!((real["first_buyer"]["idx"].as_u64(), real["first_buyer"]["dpos"].as_i64(), real["first_buyer"]["ours_first"].as_bool()), (Some(14), Some(4), Some(false)));
    assert_eq!((real["later_buy_sol"].as_u64(), real["later_sell_sol"].as_u64(), real["later_buyers"].as_u64()), (Some(1_600_000_000), Some(100_000_000), Some(1)));
    let sh = fo.iter().find(|r| r["of"] == "shadow_fill").unwrap();
    assert_eq!(sh["later_buy_sol"].as_u64(), Some(2_100_000_000), "a would-fill lands just after its dump");
    assert_eq!(f.st.our_fills8.load(Ordering::Relaxed), 1);
    // silence: 30 min without a try (feed time), then back
    let mut out = Vec::new();
    f.slot_start(300, ts(200) + SILENT_NS + 1, &mut out);
    assert_eq!(out.iter().filter(|r| r["stage"] == "silent").count(), 1);
    f.slot_start(301, ts(200) + SILENT_NS + 2, &mut out);
    assert_eq!(out.iter().filter(|r| r["stage"] == "silent").count(), 1, "said once");
    assert!(f.status().contains("SILENT"));
    f.sighting(&hit(m, a), 9, 301, ts(200) + SILENT_NS + 3, 0, 1, true, &mut out);
    assert_eq!(out.last().unwrap()["stage"], "back");
    let fin = f.finish(&mut out);
    assert_eq!(fin["silent_periods"], 1);
}

/// the tap on PsLive records: our own tries are never counted; records / shadow records route to the right stage
#[test]
fn dip45_tap_routing() {
    let (otx, orx) = crossbeam_channel::unbounded::<Out>();
    let mut tap = FleetTap::start(FleetCfg { sig: None, b1: None }, USER, &otx, true);
    let m = [7u8; 32];
    let mut a = fleet_arrival(m, 500, ts(500), 1);
    tap.arrival(&a);
    a.tx.keys[0] = USER; a.tx.sig[9] = 1;
    tap.arrival(&a);
    assert_eq!(tap.inner().unwrap().st.tries.load(Ordering::Relaxed), 1, "our own wallet is not the fleet");
    tap.on_rec(&serde_json::json!({"ev": "presend_live_arm", "w": 4, "mint": b58(&m), "kind": "rearm", "dry": true, "dump": {"slot": 499, "idx": 3}}));
    tap.on_rec(&serde_json::json!({"ev": "presend_live_arm", "w": 5, "trig": {"mint": b58(&m), "slot": 498, "idx": 9}, "dry": false}));
    tap.on_rec(&serde_json::json!({"ev": "presend_live_skip", "w": 4, "mint": b58(&m)}));
    tap.on_shadow(&serde_json::json!({"ev": "presend_fill", "w": 2, "mint": b58(&m), "s_in": 501, "row": "a", "x": {"slot": 501, "idx": 7}}));
    let recs: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    let st: Vec<&str> = recs.iter().map(|r| r["stage"].as_str().unwrap()).collect();
    assert_eq!(st, ["config", "arm", "arm", "shadow_fill"]);
    assert_eq!((recs[2]["kind"].as_str(), recs[2]["dump"][0].as_u64(), recs[1]["dump"][1].as_u64()), (Some("t2"), Some(498), Some(3)));
    assert_eq!((recs[1]["kind"].as_str(), recs[1]["dry"].as_bool(), recs[1]["fleet"]["n0"].as_u64()), (Some("rearm"), Some(true), Some(1)));
    assert_eq!((recs[3]["kind"].as_str(), recs[3]["dump"][1].as_u64()), (Some("shadow:a"), Some(7)));
    assert!(tap.watch.contains_key(&m));
    assert!(tap.finish().is_some());
}

#[test]
fn dip45_sig_file_hot_reload() {
    let p = std::env::temp_dir().join(format!("dip45_hot_{}.json", std::process::id()));
    std::fs::write(&p, DEFAULT_SIG).unwrap();
    let (mut f, err) = Fleet::open(FleetCfg { sig: Some(p.display().to_string()), b1: None });
    assert!(err.is_none());
    let mut out = Vec::new();
    std::thread::sleep(Duration::from_millis(20));
    std::fs::write(&p, DEFAULT_SIG.replace("[32000]", "[32000, 41000]")).unwrap();
    // mtime granularity: force a different mtime
    let ft = std::time::SystemTime::now() + Duration::from_secs(5);
    let _ = std::fs::File::options().write(true).open(&p).and_then(|fh| fh.set_modified(ft));
    f.sig_check(true, &mut out);
    assert_eq!(out.len(), 1);
    assert!(f.sig.read().unwrap().price_ok(41_000));
    std::fs::write(&p, "garbage").unwrap();
    let _ = std::fs::File::options().write(true).open(&p).and_then(|fh| fh.set_modified(ft + Duration::from_secs(5)));
    f.sig_check(true, &mut out);
    assert!(out[1]["err"].is_string());
    assert!(f.sig.read().unwrap().price_ok(41_000), "an error keeps the signature in use");
    let _ = std::fs::remove_file(&p);
}

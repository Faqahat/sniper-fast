// ===================================================================================================================
// dip46 B1 LOG shadow tests (ps46_b1.rs; LOG ONLY). Declared inside pslive.rs.
//  * the model: the built-in json IS the frozen file (sha256), a file with another sha256 is refused
//  * PARITY: real trades of 50 tokens of the push4-audit NEW tape (testdata/dip46_b1_parity.json.zst, ops/fleet45/b1_fixture.py):
//    every token-slot query's 25 features, the decoder / regressor scores (sklearn's own predictions) and the 8-slot window outcome
//    (dump, entry, paper SOL, later-buy SOL / buyers; ops/fleet45/b1_lib.py) must match the engine's (float tolerance), 0 mismatches
//  * the rules through the fleet thread's state: B1 only where a fleet-signature try was on the token in S-2..S-1, one window per
//    token per rule, records carry what the plan asks for
//  * GOLDEN: the fleet log + the B1 log on (fleet tries injected) = the no-flag digest once their records / fields are taken out
//  * the flags and refusals
// ===================================================================================================================
use super::*;
use super::ps45_fleet::*;
use super::ps46_b1::*;

fn pk(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }

#[test]
fn dip46_model_is_the_frozen_file() {
    assert_eq!(sha256_hex(FROZEN_JSON.as_bytes()), FROZEN_SHA256);
    let root = env!("CARGO_MANIFEST_DIR");
    let p = format!("{root}/testdata/dip46_b1_model.json");
    let m = Model::load(&p).unwrap();
    assert_eq!(m.sha, FROZEN_SHA256);
    assert_eq!((m.dec.trees.len(), m.reg.trees.len()), (242, 83));
    assert_eq!((m.dec_min, m.b0_thr, m.b1_thr, m.window, m.dp, m.hold), (0.2, 0.002, 0.0, 8, 26, 3));
    // one changed byte = refused
    let f = std::env::temp_dir().join(format!("dip46_model_{}.json", std::process::id()));
    std::fs::write(&f, FROZEN_JSON.replacen("\"window\":8", "\"window\":9", 1)).unwrap();
    assert!(Model::load(f.to_str().unwrap()).err().unwrap().to_string().contains("not the frozen B0 model"));
    let _ = std::fs::remove_file(&f);
    assert!(Model::load("/nonexistent/b1.json").is_err());
}

struct Fx { mints: Vec<(Pk, Option<u64>, Option<Pk>)>, trades: Vec<(usize, u64, u32, u16, Pk, bool, u64, u64, u64, u64)>, rows: Vec<serde_json::Value> }

fn fixture() -> Fx {
    let root = env!("CARGO_MANIFEST_DIR");
    let raw = zstd::decode_all(std::fs::File::open(format!("{root}/testdata/dip46_b1_parity.json.zst")).unwrap()).unwrap();
    let v: serde_json::Value = serde_json::from_slice(&raw).unwrap();
    let users: Vec<Pk> = v["users"].as_array().unwrap().iter().map(|u| pk(u.as_str().unwrap())).collect();
    let mints = v["mints"].as_array().unwrap().iter().map(|m| (pk(m["mint"].as_str().unwrap()), m["cslot"].as_u64(), m["creator"].as_str().map(pk))).collect();
    let trades = v["trades"].as_array().unwrap().iter().map(|t| {
        let u = |k: usize| t[k].as_u64().unwrap();
        (u(0) as usize, u(1), u(2) as u32, u(3) as u16, users[u(4) as usize], u(5) == 1, u(6), u(7), u(8), u(9))
    }).collect();
    Fx { mints, trades, rows: v["rows"].as_array().unwrap().clone() }
}

/// the fixture's trades through the B1 state, tx by tx in chain order (creates first); flags by `gate`
fn replay(b: &mut B1, fx: &Fx, gate: &dyn Fn(&Pk, u64) -> Flags) -> Vec<serde_json::Value> {
    let mut out = Vec::new();
    for (m, cs, cr) in &fx.mints {
        if let (Some(cs), Some(cr)) = (cs, cr) { b.create(*cs, &arbx::dip::CreateEvent { mint: *m, bonding_curve: [0; 32], user: *cr, creator: *cr }); }
    }
    let mut k = 0;
    while k < fx.trades.len() {
        let (s, i) = (fx.trades[k].1, fx.trades[k].2);
        let mut ev = Vec::new();
        while k < fx.trades.len() && (fx.trades[k].1, fx.trades[k].2) == (s, i) {
            let t = &fx.trades[k];
            ev.push(arbx::dip::TradeEvent { mint: fx.mints[t.0].0, sol: t.6, tok: t.7, buy: t.5, user: t.4, vsol: t.8, vtok: t.9, fbps: 0, cbps: 0 });
            k += 1;
        }
        b.exec(s, i, &ev, &[], s * 1000, s, gate, &mut out);
    }
    let fin = b.finish(0, 0, gate, &mut out);
    out.push(fin);
    out
}

fn close(a: f64, b: f64, rel: f64) -> bool { a == b || (a - b).abs() <= rel * a.abs().max(b.abs()).max(1e-12) }

/// the PARITY test: the engine vs the offline Python scorer / features / paper on >= 1,000 real token-slot windows
#[test]
fn dip46_parity_with_the_offline_scorer() {
    let fx = fixture();
    let mut b = B1::new(Model::frozen());
    b.trace = Some(Vec::new());
    b.all_windows = true;
    let none = |_: &Pk, _: u64| Flags::default();
    let out = replay(&mut b, &fx, &none);
    let trace = b.trace.take().unwrap();
    let mut by: FxHashMap<(Pk, u64), &(Pk, u64, [f64; 25], f64, Option<f64>)> = FxHashMap::default();
    for t in &trace { by.insert((t.0, t.1), t); }
    let wins: FxHashMap<(String, u64), &serde_json::Value> = out.iter().filter(|r| r["stage"] == "window").map(|r| ((r["mint"].as_str().unwrap().to_string(), r["slot"].as_u64().unwrap()), r)).collect();
    let (mut n, mut feat_bad, mut score_bad, mut out_bad, mut missing, mut dec_pass, mut fills, mut max_d) = (0, 0, 0, 0, 0, 0, 0, 0.0f64);
    for r in &fx.rows {
        let (mi, qs) = (r[0].as_u64().unwrap() as usize, r[1].as_u64().unwrap());
        let m = fx.mints[mi].0;
        let Some(t) = by.get(&(m, qs)) else { missing += 1; eprintln!("missing query {} {qs}", b58(&m)); continue };
        n += 1;
        let want: Vec<f64> = r[2].as_array().unwrap().iter().map(|x| x.as_f64().unwrap()).collect();
        for (k, w) in want.iter().enumerate() {
            if !close(t.2[k], *w, 1e-9) { feat_bad += 1; if feat_bad < 10 { eprintln!("feature {} at {} {qs}: engine {} python {}", F0[k], b58(&m), t.2[k], w); } }
        }
        let (pd, pv) = (r[3].as_f64().unwrap(), r[4].as_f64());
        max_d = max_d.max((t.3 - pd).abs());
        let ok = (t.3 - pd).abs() < 1e-9 && match (t.4, pv) { (Some(a), Some(b)) => { max_d = max_d.max((a - b).abs()); (a - b).abs() < 1e-9 } (None, None) => true, _ => false };
        if !ok { score_bad += 1; eprintln!("score at {} {qs}: engine {} {:?} python {} {:?}", b58(&m), t.3, t.4, pd, pv); }
        if pv.is_some() { dec_pass += 1; }
        // the window outcome
        let w = wins.get(&(b58(&m), qs)).unwrap_or_else(|| panic!("no window record {} {qs}", b58(&m)));
        let o = &r[5];
        let ok = if o.is_null() { w["fill"] == false } else {
            fills += 1;
            let g = |k: usize| o[k].as_f64().unwrap();
            w["fill"] == true && w["dump"]["slot"].as_u64() == o[0].as_u64() && w["dump"]["i0"].as_u64() == o[1].as_u64() && w["dump"]["i1"].as_u64() == o[2].as_u64()
                && w["entry"][0].as_u64() == o[3].as_u64() && w["entry"][1].as_u64() == o[4].as_u64() && (w["paper_sol"].as_f64().unwrap() - g(5)).abs() < 1e-9
                && (w["later_buy_sol_3"].as_f64().unwrap() - g(6)).abs() < 1e-9 && w["later_buyers"].as_u64() == o[7].as_u64()
        };
        if !ok { out_bad += 1; if out_bad < 10 { eprintln!("window outcome at {} {qs}: engine {w} python {o}", b58(&m)); } }
        assert_eq!(w["feat_hash"].as_str().unwrap(), feat_hash(&t.2));
    }
    eprintln!("dip46 PARITY: {n} token-slot windows ({} rows in the fixture), decoder >= 0.2 on {dec_pass}, fills {fills} | mismatches: features {feat_bad}, scores {score_bad} \
        (max |diff| {max_d:.3e}), window outcomes {out_bad}, missing {missing} | engine queries {} late trades {}", fx.rows.len(), trace.len(), b.st.late);
    assert!(n >= 1_000 && dec_pass >= 500 && fills >= 300, "{n} {dec_pass} {fills}");
    assert_eq!((feat_bad, score_bad, out_bad, missing), (0, 0, 0, 0), "zero parity mismatch");
    assert_eq!(trace.len(), fx.rows.len(), "no extra queries");
}

/// the rules on the fleet thread's state: real fleet flags gate B1; one window per token per rule; the record's fields
#[test]
fn dip46_rules_through_the_fleet_state() {
    let fx = fixture();
    let (mut f, _) = Fleet::open(FleetCfg { sig: None, b1: Some(B1Cfg { model: None }) });
    let mut out = Vec::new();
    // fleet-signature tries on the first 25 tokens, every slot of their trades (and the one before)
    let gated: FxHashSet<Pk> = fx.mints.iter().take(25).map(|m| m.0).collect();
    let mut n = 0u64;
    let mut slots: Vec<(u64, Pk)> = fx.trades.iter().filter(|t| gated.contains(&fx.mints[t.0].0)).map(|t| (t.1, fx.mints[t.0].0)).collect();
    slots.sort(); slots.dedup();
    for (m, cs, cr) in &fx.mints {
        if let (Some(cs), Some(cr)) = (cs, cr) { f.b1.as_mut().unwrap().create(*cs, &arbx::dip::CreateEvent { mint: *m, bonding_curve: [0; 32], user: *cr, creator: *cr }); }
    }
    let mut si = 0;
    let mut k = 0;
    while k < fx.trades.len() {
        let (s, i) = (fx.trades[k].1, fx.trades[k].2);
        while si < slots.len() && slots[si].0 <= s {
            n += 1;
            let h = Hit { class: Class::Fleet, mint: slots[si].1, signer: [7; 32], cu_price: 32_000, cu_limit: 60_000 };
            f.slot_start(slots[si].0, slots[si].0 * 1000, &mut out);
            f.sighting(&h, n, slots[si].0, slots[si].0 * 1000, 0, 1, true, &mut out);
            si += 1;
        }
        let mut ev = Vec::new();
        while k < fx.trades.len() && (fx.trades[k].1, fx.trades[k].2) == (s, i) {
            let t = &fx.trades[k];
            ev.push(arbx::dip::TradeEvent { mint: fx.mints[t.0].0, sol: t.6, tok: t.7, buy: t.5, user: t.4, vsol: t.8, vtok: t.9, fbps: 0, cbps: 0 });
            k += 1;
        }
        f.b1_exec(s, i, &ev, &[], s * 1000, &mut out);
    }
    let fin = f.finish(&mut out);
    // DIP46_DUMP=FILE: the records as an engine jsonl (to try ops/fleet45/b1_report.py)
    if let Ok(p) = std::env::var("DIP46_DUMP") { std::fs::write(p, out.iter().map(|r| r.to_string() + "\n").collect::<String>()).unwrap(); }
    let w: Vec<&serde_json::Value> = out.iter().filter(|r| r["ev"] == "presend_live_b1" && r["stage"] == "window").collect();
    let b1w: Vec<_> = w.iter().filter(|r| r["opens"]["b1"] == true).collect();
    let b0w: Vec<_> = w.iter().filter(|r| r["opens"]["b0"] == true).collect();
    eprintln!("dip46 rules: windows {} (b0 {}, b1 {}), b1 fills {}, run_end b1 {}", w.len(), b0w.len(), b1w.len(), b1w.iter().filter(|r| r["fill"] == true).count(), fin["b1"]);
    assert!(b1w.len() > 20 && b0w.len() > 20);
    for r in &b1w {
        assert!(r["b1_pass"] == true && r["gate_on2"] == true && r["b0_score"].as_f64().unwrap() >= 0.0 && r["dec_score"].as_f64().unwrap() >= 0.2);
        assert!(gated.contains(&pk(r["mint"].as_str().unwrap())), "B1 only where the fleet was");
    }
    for r in &b0w { assert!(r["b0_pass"] == true && r["b0_score"].as_f64().unwrap() >= 0.002); }
    // one window per token per rule: starts more than 7 slots apart
    for rule in ["b0", "b1"] {
        let mut by: FxHashMap<&str, Vec<u64>> = FxHashMap::default();
        for r in w.iter().filter(|r| r["opens"][rule] == true) { by.entry(r["mint"].as_str().unwrap()).or_default().push(r["slot"].as_u64().unwrap()); }
        for v in by.values_mut() { v.sort(); for p in v.windows(2) { assert!(p[1] > p[0] + 7, "{rule} {p:?}"); } }
    }
    for k in ["mint", "slot", "idx", "kind", "b0_score", "b0_pass", "b1_pass", "gate_on2", "gate_on8", "gate_pre8", "live_armed", "live_filled", "overlap", "later_buy_sol_3",
              "later_buyers", "model_sha", "feat_hash", "paper_sol", "f", "end_slot"] {
        assert!(w.iter().all(|r| r.get(k).is_some()), "every window record has {k}");
    }
    assert!(w.iter().all(|r| r["overlap"] == "new" && r["model_sha"] == &FROZEN_SHA256[..16]));
    assert!(w.iter().any(|r| r["kind"] == "t2") && w.iter().any(|r| r["kind"] == "rearm"));
    assert_eq!(fin["b1"]["windows_b1"].as_u64().unwrap() as usize, b1w.len());
    // our live arm on a token: its windows are "same"
    let mut b = B1::new(Model::frozen());
    let m0 = fx.mints[0].0;
    b.live(&m0, "arm", 0, Some(u64::MAX / 2));
    let none = |_: &Pk, _: u64| Flags::default();
    let o = replay(&mut b, &fx, &none);
    let ws: Vec<_> = o.iter().filter(|r| r["stage"] == "window").collect();
    assert!(ws.iter().filter(|r| r["mint"] == b58(&m0).as_str()).all(|r| r["overlap"] == "same" && r["live_armed"] == true));
    assert!(ws.iter().filter(|r| r["mint"] != b58(&m0).as_str()).all(|r| r["overlap"] == "new"));
}

/// the fleet log and the B1 log on (fleet tries on the tape): the same decisions, sends, fees and exits
#[test]
fn dip46_golden_b1_log_changes_no_decision() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch([0x5Au8; 32]);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d0, n0, dropped0, _)) = dip45_tests::digest(&[], false, true) else { eprintln!("presend_parity.json missing: skipped"); return };
    let (d, n, dropped, fl) = dip45_tests::digest(&["--presend-live-fleet-log", "on", "--presend-live-b1-log", "on"], true, true).unwrap();
    let b1: Vec<_> = fl.iter().filter(|r| r["ev"] == "presend_live_b1").collect();
    eprintln!("dip46 golden with the fleet + B1 logs: {n} lines kept ({n0} without), {dropped} records taken out, B1 config {} windows {}",
        b1.iter().filter(|r| r["stage"] == "config").count(), b1.iter().filter(|r| r["stage"] == "window").count());
    assert_eq!(dropped0, 0);
    assert_eq!(b1.iter().filter(|r| r["stage"] == "config").count(), 3, "the B1 log ran in every pass");
    assert_eq!((d, n), (d0, n0), "the B1 log must not change a decision");
}

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-size-sol", "0.4"]
        .iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }

#[test]
fn dip46_flags_and_refusals() {
    let root = env!("CARGO_MANIFEST_DIR");
    let mp = format!("{root}/testdata/dip46_b1_model.json");
    let c = cfg(&["--presend-live-fleet-log", "on"]).unwrap().unwrap();
    assert!(c.fleet.as_ref().unwrap().b1.is_none());
    assert!(c.json()["fleet"].get("b1").is_none(), "off: dip45's record");
    let c = cfg(&["--presend-live-fleet-log", "on", "--presend-live-b1-log", "on"]).unwrap().unwrap();
    assert!(c.fleet.as_ref().unwrap().b1.as_ref().unwrap().model.is_none());
    assert_eq!(c.json()["fleet"]["b1"]["model"], "built-in");
    let c = cfg(&["--presend-live-fleet-log", "on", "--presend-live-b1-log", "on", "--presend-live-b1-model", &mp]).unwrap().unwrap();
    assert_eq!(c.json()["fleet"]["b1"]["model"], mp.as_str());
    assert!(cfg(&["--presend-live-fleet-log", "on", "--presend-live-b1-log", "off"]).unwrap().unwrap().fleet.unwrap().b1.is_none());
    assert!(cfg(&["--presend-live-b1-log", "on"]).is_err(), "needs the fleet log");
    assert!(cfg(&["--presend-live-fleet-log", "on", "--presend-live-b1-log", "maybe"]).is_err());
    assert!(cfg(&["--presend-live-fleet-log", "on", "--presend-live-b1-model", &mp]).is_err(), "the model needs the switch");
    assert!(cfg(&["--presend-live-fleet-log", "on", "--presend-live-b1-log", "on", "--presend-live-b1-model", "/nonexistent.json"]).is_err());
    assert!(cfg(&["--presend-live-fleet-log", "on", "--presend-live-b1-log", "on", "--presend-live-b1-model"]).is_err(), "a value");
    // needs --presend-live
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-shadow", "--presend-live-b1-log", "on"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1_000_000_000).is_err());
    // dry mode (no --live): accepted
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-shadow", "--presend-live", "--presend-live-dry", "--presend-live-routes", "default=helius-ps", "--presend-live-fleet-log", "on",
        "--presend-live-b1-log", "on"].iter().map(|s| s.to_string()).collect();
    let c = Cfg::from_argv(&a, &arbx::presend::Params::default(), false, 1_000_000_000).unwrap().unwrap();
    assert!(c.dry && c.fleet.unwrap().b1.is_some());
}

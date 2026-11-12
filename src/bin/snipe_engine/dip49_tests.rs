// ===================================================================================================================
// dip49 tests: the T2 RIVAL GATE and the re-arm fresh-holders f1 definition (psrival49.rs). Declared inside pslive.rs.
// ===================================================================================================================
use super::*;
use super::psrival49::*;

const USER: Pk = [0x5Au8; 32];
fn pk(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }
fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn sh(spec: (u32, u32, f64), live: bool) -> ShRg { let s = ShRg::default(); s.set(Some(spec), 20, live); s.last_fail.store(arbx::fast::mono_ns(), Ordering::Relaxed); s }
fn snap(payers: &[(u64, u64)], age_h: f32) -> RgSnap { let mut s = RgSnap { on: true, age_h, src: 1, ..Default::default() }; for (p, sl) in payers { s.add(*p, *sl); } s }

/// the rule's truth table: withheld exactly when rivals <= R0 or (rivals <= R2 and dev age < AGE_H); unknown age = not young
#[test]
fn dip49_rule_table() {
    let now = arbx::fast::mono_ns();
    let s = sh((0, 2, 1.0), true);
    for rivals in 0..5u64 {
        for age in [f32::NAN, 0.0, 0.5, 0.99, 1.0, 5.0, 1e6] {
            let p: Vec<(u64, u64)> = (0..rivals).map(|k| (100 + k, 990)).collect();
            let v = gate(&s, &snap(&p, age), false, 1000, now).unwrap();
            let young = age.is_finite() && age < 1.0;
            let want = rivals == 0 || (rivals <= 2 && young);
            assert_eq!((v.rivals as u64, v.young, v.would, v.withhold()), (rivals, young, want, want), "rivals {rivals} age {age}");
        }
    }
    // the window [s - 20, s - 1]: a fail in slot s itself or older than 20 slots is not counted; one payer counted once; ours never reaches it
    let v = gate(&s, &snap(&[(1, 1000), (2, 979), (3, 980), (3, 985), (4, 999)], 5.0), false, 1000, now).unwrap();
    assert_eq!(v.rivals, 2, "payer 3 (twice) and 4");
    // a payer whose newest fail is in slot s: its previous slot counts
    let mut x = snap(&[(7, 990)], 5.0); x.add(7, 1000);
    assert_eq!(x.rivals(1000, 20), 1);
    // log mode: never withheld; T2 only: a re-arm / wide window's copy is off; probes never gated; the rule off: nothing
    assert!(!gate(&sh((0, 2, 1.0), false), &snap(&[], 5.0), false, 1000, now).unwrap().withhold());
    assert!(gate(&s, &RgSnap::default(), false, 1000, now).is_none() && gate(&s, &snap(&[], 5.0), true, 1000, now).is_none());
    assert!(gate(&ShRg::default(), &snap(&[], 5.0), false, 1000, now).is_none());
    // fail open: no slippage fail seen for 60 s (or never), the blind feed
    let st = sh((0, 2, 1.0), true); st.last_fail.store(now - STALE_NS - 1, Ordering::Relaxed);
    let v = gate(&st, &snap(&[], 5.0), false, 1000, now).unwrap();
    assert_eq!((v.would, v.open, v.withhold()), (true, Some("stale"), false));
    let b = sh((0, 2, 1.0), true); b.blind.store(true, Ordering::Relaxed);
    assert_eq!(gate(&b, &snap(&[], 5.0), false, 1000, now).unwrap().open, Some("blind"));
    // the spec
    assert_eq!(spec_parse("0:2:1"), Ok((0, 2, 1.0)));
    for bad in ["0:2", "11:2:1", "0:21:1", "0:2:-1", "a:b:c"] { assert!(spec_parse(bad).is_err(), "{bad}"); }
}

/// r85 w34 9Ye53E65 (fill slot 468340087, a -0.78 loss): the recorded failed slippage txs on the mint (rugdet; ours out) -> rivals 1 (the
/// fleet payer GaasGwtD) at the filling try's signing slot; dev age 0.92 h -> WITHHELD (0:2:1 live)
#[test]
fn dip49_9ye53_withheld() {
    let root = env!("CARGO_MANIFEST_DIR");
    let fx: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(format!("{root}/testdata/dip49_9ye53.json")).unwrap()).unwrap();
    let s_sign = fx["sign_slot"].as_u64().unwrap();
    let mut sn = RgSnap { on: true, age_h: fx["dev_age_h"].as_f64().unwrap() as f32, src: 1, ..Default::default() };
    let mut slips = 0;
    for f in fx["fails"].as_array().unwrap() {
        let (slot, payer, err) = (f[0].as_u64().unwrap(), pk(f[1].as_str().unwrap()), f[2].as_str().unwrap());
        // the feed tap's rule on the recorded error ("<ix>:<custom>"): a slippage-type Custom code
        let code: Option<u32> = err.split(':').nth(1).and_then(|c| c.parse().ok());
        if !code.is_some_and(|c| arbx::feeds::SLIP_CODES.contains(&c)) { continue; }
        slips += 1;
        if slot >= s_sign { continue; }          // later than the try: the engine has not seen it
        sn.add(u64::from_le_bytes(payer[..8].try_into().unwrap()), slot);
    }
    assert_eq!(sn.rivals(s_sign, 20), fx["slipsg20"].as_u64().unwrap() as u32, "the engine's count = rugdet slipsg20");
    let v = gate(&sh((0, 2, 1.0), true), &sn, false, s_sign, arbx::fast::mono_ns()).unwrap();
    eprintln!("dip49 9Ye53E65: {slips} slippage fails, rivals {} dev age {} -> withheld {}", v.rivals, v.age_h, v.withhold());
    assert_eq!((v.rivals, v.young, v.withhold()), (1, true, true));
    // the feed tap's error decoding (bincode InstructionError(3, Custom(6001)))
    let mut e = vec![8u8, 0, 0, 0, 3, 25, 0, 0, 0]; e.extend(6001u32.to_le_bytes());
    assert_eq!(arbx::feeds::custom_code(&e), Some(6001));
    assert_eq!(arbx::feeds::custom_code(&[8, 0, 0, 0, 3, 7, 0, 0, 0]), None);
}

/// the engine path: fails through the tap's channel -> the followed mint's payers -> the armed T2 window's copy; the dev age from the worker
/// (queued at the create, never waited for; capped / error = unknown); a re-arm window never gets the gate; the fill record's verdict
#[test]
fn dip49_engine_path_and_worker() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let (mut p, atx, orx) = PsLive::for_test(cfg(&["--presend-live-rival-gate", "0:2:1", "--presend-live-rival-gate-mode", "live"]).unwrap().unwrap(), USER);
    let l = snipe_build::launch_from_target([0x49u8; 32], [0xC1u8; 32]);
    let n = 461_415_576u64;
    let t0 = std::time::Instant::now();
    let cx = arbx::feeds::ExecInfo { index: 7, fee: 5_000, ok: true, trades: Vec::new(), mayhem: false,
        creates: vec![arbx::dip::CreateEvent { mint: l.mint, bonding_curve: l.bonding_curve, user: [0xC1u8; 32], creator: [0xC1u8; 32] }] };
    let ca = arbx::feeds::Arrival { feed: 0, slot: n - 1, t_rx: 1_800_000_000 * 1_000_000_000, t_decoded: 0, executed: Some(true), tx: arbx::tx::Tx { sig: [0xC7; 64], keys: vec![[0xC1u8; 32]], ..Default::default() },
        poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(cx.clone())) };
    let l2 = l.clone();
    p.on_exec(&ca, &cx, n - 1, move |m: &Pk| (*m == l2.mint).then(|| l2.clone()), &|_| false, None);
    assert!(t0.elapsed() < Duration::from_millis(50), "the create never waits for the lookup");
    assert_eq!(p.rg49.as_ref().unwrap().dsh.q.lock().unwrap().len(), 1, "one lookup queued");
    // a rival fails on the mint (two of its txs), ours too (never counted), an unrelated mint
    let tx = p.rg49.as_ref().unwrap().test_tx.clone().unwrap();
    for (sl, payer) in [(n - 1, [0x77u8; 32]), (n - 1, [0x77u8; 32]), (n - 1, USER)] { tx.send(arbx::feeds::RivalFail { slot: sl, payer, keys: vec![payer, l.mint] }).unwrap(); }
    tx.send(arbx::feeds::RivalFail { slot: n - 1, payer: [0x78u8; 32], keys: vec![[0x78u8; 32], [0x99u8; 32]] }).unwrap();
    p.tick(n - 1, None);
    // the whale's trigger: armed, the window's copy has 1 rival, dev age pending
    let whale = [0xA9u8; 32];
    let x = arbx::feeds::ExecInfo { index: 34, fee: 5_000, ok: true, trades: vec![arbx::dip::TradeEvent { mint: l.mint, sol: 2_666_666_666, tok: 61_580_021_739_287, buy: true, user: whale,
        vsol: 38_692_888_509, vtok: 831_935_821_811_615, fbps: 95, cbps: 30 }], creates: Vec::new(), mayhem: false };
    let a = arbx::feeds::Arrival { feed: 0, slot: n, t_rx: n, t_decoded: n, executed: Some(true), tx: arbx::tx::Tx { sig: [0x3E; 64], keys: vec![whale], ..Default::default() },
        poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
    let l2 = l.clone();
    p.on_arrival(&a, n);
    p.on_exec(&a, &x, n, move |m: &Pk| (*m == l2.mint).then(|| l2.clone()), &|_| false, None);
    let id = *p.armed.get(&l.mint).expect("armed");
    let w = |p: &PsLive| p.sh.wins.lock().unwrap().iter().find(|x| x.id == id).map(|x| x.rg).unwrap();
    let s = w(&p);
    assert!(s.on && s.age_h.is_nan() && s.src == 4, "pending: {s:?}");
    assert_eq!(s.rivals(n + 1, 20), 1);
    let now = arbx::fast::mono_ns();
    let v = gate(&p.sh.rg, &s, false, n + 1, now).unwrap();
    assert!(!v.withhold(), "1 rival, dev age unknown (pending) = not young: sent");
    // the worker answers: the creator's oldest tx 0.5 h before the create -> young -> 1 rival withheld
    let src = |m: &str, pv: serde_json::Value| -> std::result::Result<serde_json::Value, String> {
        assert_eq!((m, pv[1]["limit"].as_u64(), pv[1]["before"].as_str()), ("getSignaturesForAddress", Some(1000), Some(bs58::encode(&[0xC7u8; 64]).into_string().as_str())));
        // newest first (the RPC's order): the oldest is the last
        Ok(serde_json::json!([{"signature": "y", "blockTime": 1_799_998_200u64}, {"signature": "x", "blockTime": 1_799_996_400u64}]))
    };
    p.rg49.as_mut().unwrap().pump(&src);
    p.tick(n + 1, None);
    let s = w(&p);
    assert!((s.age_h - 1.0).abs() < 1e-3 && s.src == 1, "{s:?}");
    // the OLDEST entry is 1 h before: not young (< 1 h is young) -> sent; with AGE_H 2 by the hot spec -> withheld
    assert!(!gate(&p.sh.rg, &s, false, n + 1, now).unwrap().withhold());
    p.ctl47_apply(&psctl47::ctl47_parse(br#"{"rival_gate_spec": "0:2:2", "rival_gate": "live"}"#).unwrap(), "t");
    let v = gate(&p.sh.rg, &s, false, n + 1, now).unwrap();
    assert!(v.withhold(), "{v:?}");
    p.ctl47_apply(&psctl47::ctl47_parse(br#"{"rival_gate_spec": "0:2", "rival_gate": "on"}"#).unwrap(), "t");
    assert_eq!((p.f47.cur.unwrap().rg, p.f47.cur.unwrap().rg_live), (Some((0, 2, 2.0)), true), "bad values: the old ones stay");
    p.ctl47_apply(&psctl47::ctl47_parse(br#"{"rival_gate": "log", "rival_gate_spec": "0:2:2"}"#).unwrap(), "t");
    assert!(!gate(&p.sh.rg, &s, false, n + 1, now).unwrap().withhold(), "log: counted, sent");
    assert_eq!(p.f47.fs.as_ref().map(|f| f.obj["rival_gate"].clone()), Some(serde_json::json!("log")));
    // capped / error answers: unknown
    let cap = |_: &str, _: serde_json::Value| -> std::result::Result<serde_json::Value, String> { Ok(serde_json::Value::Array(vec![serde_json::json!({"blockTime": 1}); 1000])) };
    let err = |_: &str, _: serde_json::Value| -> std::result::Result<serde_json::Value, String> { Err("-32020 history not available".into()) };
    let none = |_: &str, _: serde_json::Value| -> std::result::Result<serde_json::Value, String> { Ok(serde_json::json!([])) };
    let j = DJob { creator: [1u8; 32], sig: [2u8; 64], t: 100.0 };
    assert_eq!((dev_lookup(&cap, &j), dev_lookup(&err, &j), dev_lookup(&none, &j)), (Dev::Capped, Dev::Err, Dev::Oldest(100.0)));
    // the fill record carries the filling try's verdict; the realized record the compact one
    let _ = orx.try_iter().count();
    let mut sig = [0x49u8; 64]; sig[1] = 50;
    atx.send(Att { w: id, n: 1, mint: l.mint, sig, tag: pl::PS_TAG | 0x49, path: "helius-ps".into(), client: "AgaveBam".into(), slot: n + 1, deadline: n + 2, lim: 1.0, min_out: 1,
        p_sign: 1.0, sign_pos: (n, 34, 0), t_send: n, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }, tip: 200_000, wst: "written",
        ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46: Default::default(), rf: None, rg: Some(v) }).unwrap();
    p.drain_atts();
    let fx = arbx::feeds::ExecInfo { index: 50, fee: 5_000, ok: true, trades: vec![arbx::dip::TradeEvent { mint: l.mint, sol: 395_061_728, tok: 8_000_000_000_000, buy: true, user: USER,
        vsol: 39_000_000_000, vtok: 823_000_000_000_000, fbps: 95, cbps: 30 }], creates: Vec::new(), mayhem: false };
    let fa = arbx::feeds::Arrival { feed: 0, slot: n + 1, t_rx: n + 1, t_decoded: n + 1, executed: Some(true), tx: arbx::tx::Tx { sig, keys: vec![USER], ..Default::default() },
        poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(fx.clone())) };
    let l2 = l.clone();
    p.on_arrival(&fa, n + 1);
    p.on_exec(&fa, &fx, n + 1, move |m: &Pk| (*m == l2.mint).then(|| l2.clone()), &|_| false, None);
    p.rec(serde_json::json!({"ev": "presend_live_realized", "w": id, "pnl": 1}));
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    let fill = r.iter().find(|x| x["ev"] == "presend_live_fill").unwrap();
    assert_eq!((fill["rival_gate"]["rivals"].as_u64(), fill["rival_gate"]["blocked"].as_bool(), fill["rival_gate"]["on"].as_str()), (Some(1), Some(true), Some("live")));
    let rz = r.iter().find(|x| x["ev"] == "presend_live_realized").unwrap();
    assert_eq!(rz["rival_gate"], serde_json::json!({"rivals": 1, "dev_age_h": 1.0, "blocked": true}));
    // the queue is bounded (the oldest dropped), the drain never blocks on an empty tap
    let r49 = p.rg49.as_mut().unwrap();
    for i in 0..5000u32 { let mut c = [0x55u8; 32]; c[..4].copy_from_slice(&i.to_be_bytes()); r49.create([0x66u8; 32], c, [0u8; 64], 1.0); }
    assert!(r49.dsh.q.lock().unwrap().len() <= 4096 && r49.dsh.drops.load(Ordering::Relaxed) > 0);
    let t0 = std::time::Instant::now();
    p.rg49_drain();
    assert!(t0.elapsed() < Duration::from_millis(50));
}

/// the sender's cost per T2 try (rule on): the window's copy + 5 relaxed loads
#[test]
fn dip49_sender_cost() {
    let s = sh((0, 2, 1.0), true);
    let sn = snap(&(0..16u64).map(|k| (k + 1, 990 + (k % 9))).collect::<Vec<_>>(), 0.5);
    let now = arbx::fast::mono_ns();
    let k = 2_000_000u64;
    let t0 = arbx::fast::mono_ns();
    let mut acc = 0u32;
    for i in 0..k { acc = acc.wrapping_add(gate(&s, std::hint::black_box(&sn), false, 1000 + (i & 3), now).map_or(0, |v| v.rivals)); }
    let ns = (arbx::fast::mono_ns() - t0) as f64 / k as f64;
    eprintln!("DIP49 RIVAL GATE sender cost: {ns:.1} ns per T2 try (16 payers in the copy; acc {acc})");
    assert!(ns < 2_000.0);
}

/// RULE B parity: the engine's f1 selection (f1_of) on the r83-r85 fills' recorded holder sets = rugdet's f1_pct / f1_n (s4_feat.py)
#[test]
fn dip49_f1_parity_rugdet() {
    let root = env!("CARGO_MANIFEST_DIR");
    let fx: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(format!("{root}/testdata/dip49_f1_parity.json")).unwrap()).unwrap();
    let mut n = 0;
    for f in fx.as_array().unwrap() {
        let excl: Vec<Pk> = f["excl"].as_array().unwrap().iter().map(|x| pk(x.as_str().unwrap())).collect();
        let hs: Vec<(Pk, f64, u8)> = f["holders"].as_array().unwrap().iter().map(|h| (pk(h[0].as_str().unwrap()), h[1].as_f64().unwrap(), h[2].as_u64().unwrap() as u8)).collect();
        let (p, k) = f1_of(hs.iter().map(|(w, p, n)| (w, *p, *n)), &excl);
        assert!((p - f["f1_pct"].as_f64().unwrap()).abs() < 1e-9 && k as u64 == f["f1_n"].as_u64().unwrap(), "r{} w{}: engine {p} / {k} vs rugdet {} / {}", f["run"], f["w"], f["f1_pct"], f["f1_n"]);
        n += 1;
    }
    eprintln!("dip49 f1 parity: {n} r83-r85 fills, engine f1 = rugdet f1_pct");
    assert!(n >= 20);
}

/// RULE B in the engine: the re-arm lane with --presend-live-fresh-skip-ra-def f1 decides on f1 (the dumper out); f3 = dip48; both logged;
/// the hot key switches it; flags
#[test]
fn dip49_ra_def_and_flags() {
    let c = cfg(&["--presend-live-f3-log", "on", "--presend-live-fresh-skip", "0:15", "--presend-live-fresh-skip-ra-def", "f1"]).unwrap().unwrap();
    assert!(c.fresh_ra_f1 && c.json()["fresh_skip"]["ra_def"] == "f1");
    let (mut p, _a, _o) = PsLive::for_test(c, USER);
    assert!(p.f47.cur.unwrap().fresh_ra_f1);
    p.ctl47_apply(&psctl47::ctl47_parse(br#"{"fresh_skip_ra_def": "f3"}"#).unwrap(), "t");
    assert!(!p.f47.cur.unwrap().fresh_ra_f1);
    p.ctl47_apply(&psctl47::ctl47_parse(br#"{"fresh_skip_ra_def": "f9"}"#).unwrap(), "t");
    assert!(!p.f47.cur.unwrap().fresh_ra_f1, "bad value: the old (f3) stays");
    p.ctl47_apply(&psctl47::ctl47_parse(b"{}").unwrap(), "t");
    assert!(p.f47.cur.unwrap().fresh_ra_f1, "absent: the start's f1");
    for bad in [vec!["--presend-live-fresh-skip-ra-def", "f1"], vec!["--presend-live-f3-log", "on", "--presend-live-fresh-skip", "0:15", "--presend-live-fresh-skip-ra-def", "x"],
                vec!["--presend-live-rival-gate-mode", "live"], vec!["--presend-live-rival-gate", "0:2"], vec!["--presend-live-rival-gate", "0:2:1", "--presend-live-rival-gate-slots", "0"]] {
        assert!(cfg(&bad).is_err(), "{bad:?}");
    }
    let c = cfg(&["--presend-live-rival-gate", "0:2:1"]).unwrap().unwrap();
    assert_eq!((c.rival_gate, c.rival_live, c.rival_slots), (Some((0, 2, 1.0)), false, 20));
}

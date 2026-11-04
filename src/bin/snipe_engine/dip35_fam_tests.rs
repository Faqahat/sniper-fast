// ===================================================================================================================
// dip35 LOG-ONLY fam tests (11-04 PKT; pslog35.rs): --presend-live-fam-log [--presend-live-fam-thr X] [--presend-live-fam-rpc URL].
// Flag off: nothing queued / spawned, no record (dip34's); flag on: one holders read per arm, its record, never a decision.
// ===================================================================================================================
use super::*;
use super::pslog35::*;

const USER: Pk = [0x5Au8; 32];
const SUP: i64 = 1_000_000_000_000_000;

fn v(a: &[&str]) -> Vec<String> { a.iter().map(|s| s.to_string()).collect() }
fn base(extra: &[&str]) -> Vec<String> {
    let mut x = v(&["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "20",
        "--presend-live-fee-budget-sol", "0.03"]);
    x.extend(extra.iter().map(|s| s.to_string()));
    x
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&base(extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000) }
fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| o.rec()).collect() }
fn lines(orx: &crossbeam_channel::Receiver<Out>) -> Vec<String> { orx.try_iter().filter_map(|o| match o { Out::Line(l) => Some(l), _ => None }).collect() }
fn pct(p: f64) -> i64 { (p / 100.0 * SUP as f64).round() as i64 }
fn w(k: u16) -> Pk { let mut x = [0u8; 32]; x[0] = 0xF0; x[1..3].copy_from_slice(&k.to_le_bytes()); x }

#[test]
fn dip35_fam_flags() {
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(!c0.fam_log && c0.fam_rpc.is_none() && c0.fam_thr == FAM_THR, "default off");
    assert!(c0.json().get("fam_log").is_none(), "off: dip34's start record");
    let l = L35::new(&c0).unwrap();
    assert!(l.rpc.is_none(), "off: no client");
    let c = cfg(&["--presend-live-fam-log"]).unwrap().unwrap();
    assert!(c.fam_log && c.fam_thr == 26.825 && c.json()["fam_log"]["thr"] == 26.825 && c.json()["fam_log"]["rpc"] == "rpc_url", "{}", c.json());
    let c = cfg(&["--presend-live-fam-log", "--presend-live-fam-thr", "30", "--presend-live-fam-rpc", "https://x.example/?k=${FAM_TEST_UNSET_VAR}"]).unwrap().unwrap();
    assert_eq!((c.fam_thr, c.fam_rpc.as_deref()), (30.0, Some("https://x.example/?k=${FAM_TEST_UNSET_VAR}")));
    assert!(!c.json().to_string().contains("x.example"), "the URL is never written");
    // an unset ${VAR}: refused at start (no silent fallback)
    assert!(L35::new(&c).is_err());
    for (a, needle) in [(&["--presend-live-fam-thr", "30"][..], "need --presend-live-fam-log"), (&["--presend-live-fam-rpc", "https://x"][..], "need --presend-live-fam-log"),
        (&["--presend-live-fam-log", "--presend-live-fam-thr", "0"][..], "(0, 100]"), (&["--presend-live-fam-log", "--presend-live-fam-thr", "101"][..], "(0, 100]"),
        (&["--presend-live-fam-log", "--presend-live-fam-rpc"][..], "needs a URL")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    assert!(crate::check_flags(&base(&["--presend-live-fam-log", "--presend-live-fam-thr", "26.825", "--presend-live-fam-rpc", "https://x"])).is_ok());
    assert!(crate::check_flags(&base(&["--presend-live-fam-log", "--presend-live-fam-thr", "abc"])).is_err(), "a number");
    for f in ["--presend-live-fam-log", "--presend-live-fam-thr", "--presend-live-fam-rpc"] {
        let e = Cfg::from_argv(&v(&["snipe_engine", "--dip", "--presend-shadow", f]), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
}

/// create-slot owners + recipients counted; the curve, us, curve buyers, a post-arm seller (the feed ahead of the RPC) and a post-arm
/// buyer not; an owner's accounts summed
#[test]
fn dip35_fam_classify() {
    let curve = w(999);
    let (cs1, cs2, r1, r2, r3, buyer, seller, late) = (w(1), w(2), w(3), w(4), w(5), w(6), w(7), w(8));
    let hold = vec![(curve, pct(70.0) as u64), (USER, pct(1.0) as u64), (cs1, pct(5.0) as u64), (cs2, pct(3.0) as u64), (cs2, pct(2.0) as u64),
        (r1, pct(2.0) as u64), (r2, pct(2.0) as u64), (r3, pct(2.0) as u64), (buyer, pct(4.0) as u64), (seller, pct(3.0) as u64), (late, pct(2.0) as u64), (w(9), 0)];
    let arm = vec![(cs1, pct(5.0), true), (cs2, pct(5.0), true), (buyer, pct(4.0), false), (seller, pct(3.0), false), (USER, pct(1.0), false)];
    let now = vec![(cs1, pct(5.0), true), (cs2, pct(5.0), true), (buyer, pct(4.0), false), (seller, 0, false), (late, pct(2.0), false), (USER, pct(1.0), false)];
    let f = fam_classify(&hold, &arm, &now, &curve, &USER);
    assert_eq!((f.n_holders, f.recv_n), (8, 3), "{f:?}");
    assert!((f.cs_pct - 10.0).abs() < 1e-9 && (f.recv_pct - 6.0).abs() < 1e-9 && (f.fam - 16.0).abs() < 1e-9, "{f:?}");
    // a create-slot owner who later received more is counted once; a buyer who also got a transfer on top is a recipient
    let hold2 = vec![(cs1, pct(8.0) as u64), (buyer, pct(6.0) as u64)];
    let f = fam_classify(&hold2, &arm, &arm, &curve, &USER);
    assert!((f.fam - 14.0).abs() < 1e-9 && f.recv_n == 2 && (f.cs_pct - 8.0).abs() < 1e-9, "{f:?}");
    // within the tolerance: not a recipient
    let f = fam_classify(&[(buyer, (pct(4.0) + FAM_TOL) as u64)], &arm, &arm, &curve, &USER);
    assert_eq!((f.recv_n, f.fam), (0, 0.0));
    // partial history (no book): every holder is a recipient
    let f = fam_classify(&[(r1, pct(2.0) as u64), (curve, pct(80.0) as u64)], &[], &[], &curve, &USER);
    assert!(f.recv_n == 1 && (f.fam - 2.0).abs() < 1e-9);
}

/// Token-2022 (and SPL) accounts: owner 32..64, amount 64..72 (extensions after 165); the dataSlice {32, 40}; the request's filters
#[test]
fn dip35_token2022_parse_and_params() {
    let (mint, owner) = ([7u8; 32], [8u8; 32]);
    let mut d = vec![0u8; 182];
    d[..32].copy_from_slice(&mint);
    d[32..64].copy_from_slice(&owner);
    d[64..72].copy_from_slice(&123_456_789_012u64.to_le_bytes());
    d[165] = 2; // AccountType::Account, then the ImmutableOwner extension
    d[166..168].copy_from_slice(&7u16.to_le_bytes());
    assert_eq!(acct_parse(&d, false), Some((owner, 123_456_789_012)));
    assert_eq!(acct_parse(&d[32..72], true), Some((owner, 123_456_789_012)));
    assert_eq!(acct_parse(&d[32..60], true), None, "short");
    let b64 = base64::engine::general_purpose::STANDARD.encode(&d[32..72]);
    let ans = serde_json::json!({"context": {"slot": 465063800u64}, "value": [{"pubkey": "x", "account": {"data": [b64, "base64"], "owner": "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"}}]});
    assert_eq!(gpa_parse(&ans).unwrap(), (465063800, vec![(owner, 123_456_789_012)]));
    assert!(gpa_parse(&serde_json::json!([])).is_err(), "withContext needed");
    let p = gpa_params(&mint, true);
    assert!(p[0] == "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb" && p[1]["filters"].as_array().unwrap().len() == 1 && p[1]["filters"][0]["memcmp"]["offset"] == 0, "{p}");
    assert!(p[1]["withContext"] == true && p[1]["dataSlice"] == serde_json::json!({"offset": 32, "length": 40}) && p[1]["filters"][0]["memcmp"]["bytes"] == b58(&mint));
    let p = gpa_params(&mint, false);
    assert!(p[0] == "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA" && p[1]["filters"][0]["dataSize"] == 165, "{p}");
}

/// the probe: an armed T2 queues one read with the flag (busy: skipped, a record), none without; the Bnx6-like answer -> hit, its
/// record and line; an error -> a record, no hit; the summary
#[test]
fn dip35_fam_on_the_probe() {
    let (mint, cr, wh) = ([7u8; 32], [3u8; 32], [9u8; 32]);
    let t0 = 1_793_720_000_000_000_000u64;
    let launch = snipe_build::launch_from_target(mint, cr);
    // 13 create-slot buyers (1.4% each = 18.2%), then the whale's 9% trigger at age 27
    let feed = |p: &mut PsLive| {
        p.det.create(mint, 1000, cr, cr, false);
        let mut ev = Vec::new();
        for k in 0..13u16 {
            p.det.trade(&pl::Trade { mint, s: 1000, i: k as u32 + 1, j: 0, sig: [k as u8; 64], user: if k == 0 { cr } else { w(k) }, buy: true, sol: 500_000_000,
                tok: pct(1.4) as u64, vsol: 30_000_000_000, vtok: 1_000_000_000_000_000, fbps: 95, cbps: 30, t_rx: t0 }, &mut ev);
        }
    };
    let trig = pl::Trade { mint, s: 1027, i: 39, j: 0, sig: [39; 64], user: wh, buy: true, sol: 12_000_000_000, tok: pct(9.0) as u64, vsol: 72_000_000_000,
        vtok: 443_000_000_000_000, fbps: 95, cbps: 30, t_rx: t0 };
    let run = |c: Cfg| {
        let (mut p, _atx, orx) = PsLive::for_test(c, USER);
        feed(&mut p);
        let mut ev = Vec::new();
        p.det.trade(&trig, &mut ev);
        let l = launch.clone();
        p.trigger(&trig, wh, 9.0, pct(9.0), 27, &|_: &Pk| Some(l.clone()), &|_: &Pk| false);
        (p, orx)
    };
    // flag off: armed, nothing queued, no fam record, no summary
    let (mut q, orx0) = run(cfg(&[]).unwrap().unwrap());
    let r0 = recs(&orx0);
    assert!(r0.iter().any(|x| x["ev"] == "presend_live_arm"), "armed: {r0:?}");
    assert!(r0.iter().all(|x| x["ev"] != "presend_live_fam"));
    assert!(q.take_cmds().iter().all(|c| !matches!(c, Cmd::Fam(_))), "nothing spawned");
    assert_eq!(q.l35.spawned, 0);
    assert!(q.l35_json().is_none());

    // flag on: one read queued for w1 (Token-2022 for create_v2; the curve; the arm's book with the create-slot buyers)
    let (mut p, orx) = run(cfg(&["--presend-live-fam-log"]).unwrap().unwrap());
    let r = recs(&orx);
    let a = r.iter().find(|x| x["ev"] == "presend_live_arm").expect("armed");
    assert!(a.get("fam").is_none(), "the arm record is unchanged");
    let cmds = p.take_cmds();
    let req = cmds.iter().find_map(|c| match c { Cmd::Fam(q) => Some((**q).clone()), _ => None }).expect("a fam read");
    assert!(req.w == 1 && req.mint == mint && !req.rearm && req.arm_slot == 1027 && req.t22 && req.curve == launch.bonding_curve);
    let book = req.book.clone().expect("followed");
    assert_eq!(book.iter().filter(|b| b.2).count(), 13, "the create-slot buyers (the creator's included)");
    assert!(book.iter().any(|b| b.0 == wh && !b.2 && b.1 == pct(9.0)));
    // busy: FAM_INFLIGHT reads under way -> skipped, a record, counted
    p.l35.inflight.store(FAM_INFLIGHT, Ordering::SeqCst);
    p.fam_arm(2, mint, true, 1030);
    let b = recs(&orx);
    assert!(b.len() == 1 && b[0]["err"] == "busy" && b[0]["rearm"] == true && p.l35.busy == 1, "{b:?}");
    assert!(p.take_cmds().is_empty());
    p.l35.inflight.store(0, Ordering::SeqCst);

    // the answer: the 13 still hold 1.4% (18.2%), 80 transfer recipients 0.34875% (27.9%), the whale 9%, the curve, us
    let mut hold: Vec<(Pk, u64)> = (0..13u16).map(|k| (if k == 0 { cr } else { w(k) }, pct(1.4) as u64)).collect();
    hold.extend((100..180u16).map(|k| (w(k), pct(0.34875) as u64)));
    hold.extend([(wh, pct(9.0) as u64), (launch.bonding_curve, pct(55.0) as u64), (USER, pct(1.0) as u64)]);
    p.fam_done(FamRes { req: req.clone(), prog: "t22", read: Ok((1031, hold)) });
    let r = recs(&orx);
    let f = r.iter().find(|x| x["ev"] == "presend_live_fam").expect("record");
    assert!(f["w"] == 1 && f["mint"] == b58(&mint) && f["rearm"] == false && f["hit"] == true && f["hist"] == "full" && f["arm_slot"] == 1027 && f["read_slot"] == 1031, "{f}");
    assert!(f["fam"] == 46.1 && f["cs_pct"] == 18.2 && f["recv_n"] == 80 && f["recv_pct"] == 27.9 && f["n_holders"] == 94 && f["err"].is_null() && f["prog"] == "t22", "{f}");
    // the line on a hit (a fresh probe: its channel holds the line)
    let (mut p2, orx2) = run(cfg(&["--presend-live-fam-log"]).unwrap().unwrap());
    let _ = orx2.try_iter().count();
    let mut hold2: Vec<(Pk, u64)> = (0..13u16).map(|k| (if k == 0 { cr } else { w(k) }, pct(1.4) as u64)).collect();
    hold2.extend((100..180u16).map(|k| (w(k), pct(0.34875) as u64)));
    p2.fam_done(FamRes { req: req.clone(), prog: "t22", read: Ok((1031, hold2)) });
    let l2 = lines(&orx2);
    assert!(l2.len() == 1 && l2[0].contains("PRESEND LIVE FAM (log) w1") && l2[0].contains("fam 46.1% (cs 18.2%, recv 80 / 27.9%) -> would skip"), "{l2:?}");
    // below the threshold: no hit, no line
    p2.fam_done(FamRes { req: req.clone(), prog: "t22", read: Ok((1031, vec![(w(1), pct(1.4) as u64)])) });
    let o: Vec<Out> = orx2.try_iter().collect();
    assert_eq!(o.len(), 1, "a record, no line");
    assert!(o.into_iter().next().unwrap().rec().is_some_and(|x| x["hit"] == false && x["fam"] == 1.4));
    // an error: a record, hit null, counted
    p.fam_done(FamRes { req, prog: "t22", read: Err("timeout 3000 ms".into()) });
    let e = recs(&orx);
    assert!(e[0]["err"] == "timeout 3000 ms" && e[0]["hit"].is_null() && e[0].get("fam").is_none(), "{e:?}");
    let j = p.l35_json().unwrap();
    assert!(j["fam"]["asked"] == 1 && j["fam"]["reads"] == 1 && j["fam"]["hits"] == 1 && j["fam"]["busy"] == 1 && j["fam"]["errors"] == 1 && j["fam"]["lag_ms_p50"].is_number(), "{j}");
}

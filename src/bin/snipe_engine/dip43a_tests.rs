// ===================================================================================================================
// dip43 Builder A tests (BUILD_DIP43.md; ps43.rs, ps43_stall.rs, src/ps43_book.rs). Declared inside pslive.rs (the probe's state is private).
//  * GOLDEN: no new flag = dip42's records byte for byte (the dip25 digest the dip26 golden test pins); with every LOG-ONLY dip43 option on
//    (accounting, mint ledger in log, exit shadow, shadows43, the stall / dead-man modes live without an episode) the same digest once the
//    dip43 fields / records are taken out: the log options change no decision, send, fee or exit
//  * A1/A2 fault injection: a try seen on a shred feed and never on the executed feed -> one FEED-STALL episode, the sender paused (live),
//    the status read, the position opened from it, the dead-man sell after DEADMAN_MS blind, the feed's late fill NOT opened twice; log mode
//    asks nothing and records what it would do
//  * A9 every control key; botdepth locked to live; A8 the accounting; A5 the cascade verdicts; A6 the paper landing; flags and refusals
// ===================================================================================================================
use super::*;
use arbx::dip::TradeEvent;

const USER: Pk = [0x5Au8; 32];
const MINT: Pk = [0x4Du8; 32];

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-size-sol", "0.4"]
        .iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000) }
fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| match o { Out::Rec(v) => Some(v), Out::Line(_) => None }).collect() }
fn att(w: u64, sig: [u8; 64], slot: u64) -> Att {
    Att { w, n: 1, mint: MINT, sig, tag: pl::PS_TAG | 43, path: "helius-ps".into(), client: "JitoLabs".into(), slot, deadline: slot + 1, lim: 1.0, min_out: 7_000, p_sign: 1.0,
        sign_pos: (slot, 0, 0), t_send: 0, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }, tip: 200_000, wst: "written", ob6: 0.0,
        grd: Grd::default(), fa: None, bd: None, x46: Default::default() }
}

// ---- GOLDEN -------------------------------------------------------------------------------------------------------------

/// the dip43 additions taken out of a golden line (records' fields, whole records, the totals' "dip43")
fn strip43(l: &str) -> Option<String> {
    let (tag, body) = l.split_at(2);
    if tag != "R " && tag != "F " { return Some(l.to_string()); }
    let mut v: serde_json::Value = serde_json::from_str(body).unwrap();
    let ev = v["ev"].as_str().unwrap_or("");
    if ["presend_live_mint_ledger", "presend_live_shadow_exit", "presend_live_stop_shadow", "presend_live_unseen_fee", "presend_live_dip43", "presend_live_blind",
        "presend_live_deadman"].contains(&ev) { return None; }
    if let Some(o) = v.as_object_mut() { for k in ["not_sent", "cascade", "mint_ledger", "fanout", "would43", "shadows43", "dip43"] { o.remove(k); } }
    if let Some(o) = v.get_mut("cfg").and_then(|c| c.as_object_mut()) { o.remove("dip43"); }
    Some(format!("{tag}{v}"))
}

fn digest(extra43: &[&str], strip: bool) -> Option<(String, usize, usize)> {
    use sha2::Digest;
    let mut h = sha2::Sha256::new();
    let (mut n, mut dropped) = (0usize, 0usize);
    let passes: [(u8, Vec<&str>, arbx::presend::Params, u64); 3] = [
        (1, vec![], arbx::presend::Params::default(), 7),
        (2, vec!["--presend-live-k", "8", "--presend-live-size-sol", "0.696", "--presend-live-quiet-stop", "5:2", "--presend-live-quiet-skip", "on", "--presend-live-fbots",
            "/unused-in-tests.json", "--presend-live-quiet-fol", "4.0", "--presend-live-quiet-v2-log", "--presend-live-min-age-slots", "2"],
            arbx::presend::Params { whale_pct: 6.0, tp: 0.20, ..Default::default() }, 5),
        (3, vec!["--presend-live-fee-budget-sol", "0.0005"], arbx::presend::Params::default(), 0),
    ];
    for (tag, mut extra, ps, fe) in passes {
        extra.extend_from_slice(extra43);
        let lines = dip26_tests::golden_pass(tag, &extra, ps, fe)?;
        if let Ok(dir) = std::env::var("DIP43_GOLDEN_OUT") {
            let k: Vec<String> = lines.iter().filter_map(|l| if strip { strip43(l) } else { Some(l.clone()) }).collect();
            let _ = std::fs::write(format!("{dir}/g43_{tag}_{}.txt", extra43.len()), k.join("\n"));
        }
        h.update([tag]);
        for l in &lines {
            let l = if strip { match strip43(l) { Some(x) => x, None => { dropped += 1; continue } } } else { l.clone() };
            h.update(l.as_bytes()); h.update(b"\n"); n += 1;
        }
    }
    Some((h.finalize().iter().map(|b| format!("{b:02x}")).collect(), n, dropped))
}

/// no dip43 flag: dip42's records, lines, chain work and totals byte for byte (the dip25 digest: dip26..dip42 kept it with their flags off)
#[test]
fn dip43a_golden_no_flags_equals_dip42() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d, n, _)) = digest(&[], false) else { eprintln!("presend_parity.json missing: skipped"); return };
    assert!(n > 3_000, "{n}");
    assert_eq!(d, dip26_tests::DIP25_GOLDEN, "dip43 with no new flag must write dip42's records ({n} lines)");
}

/// every LOG-ONLY dip43 option on: the same decisions, sends, fees and exits (the digest with the dip43 additions taken out is dip42's)
#[test]
fn dip43a_golden_log_options_change_no_decision() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let on = ["--presend-live-acct", "on", "--presend-live-mint-ledger", "0.10", "--presend-live-shadow-exit", "on", "--presend-live-shadows43", "on",
        "--presend-live-stall-mode", "live", "--presend-live-deadman", "live", "--presend-live-stall", "2000:10:500"];
    // both sides go through the same strip (a JSON round trip re-prints some floats): no flags (= dip42 byte for byte, the test above) vs the options
    let Some((d0, n0, dropped0)) = digest(&[], true) else { eprintln!("presend_parity.json missing: skipped"); return };
    let (d, n, dropped) = digest(&on, true).unwrap();
    eprintln!("dip43 golden with the log options: {n} lines kept ({n0} without), {dropped} dip43 records taken out ({dropped0} without)");
    assert_eq!(dropped0, 0, "no flag: no dip43 record");
    assert!(dropped > 0, "the options wrote their records");
    assert_eq!((d, n), (d0, n0), "the log-only options must not change a decision");
}

// ---- A1 / A2 fault injection ----------------------------------------------------------------------------------------------

fn blind_setup(extra: &[&str]) -> (PsLive, crossbeam_channel::Sender<Att>, crossbeam_channel::Receiver<Out>, [u8; 64]) {
    let c = cfg(extra).unwrap().unwrap();
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    p.d43_start();
    let sig = [0x43u8; 64];
    atx.send(att(7, sig, 100)).unwrap();
    p.tick(100, None);
    (p, atx, orx, sig)
}

/// the feed paused with a fill in flight: one episode, the sender paused, the status read opens the position, the dead-man sells it once
/// the episode is longer than DEADMAN_MS, the feed's late delivery of the same fill opens nothing twice
#[test]
fn dip43a_blind_fill_deadman_live() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, orx, sig) = blind_setup(&["--presend-live-stall-mode", "live", "--presend-live-deadman", "live"]);
    let log = DipLog::open(None).unwrap();
    let mut w = ps43_stall::Watch::new(p.cfg.c43.stall);
    let t0 = arbx::fast::mono_ns();
    // the executed feed is alive; our try shows on a shred feed only
    w.on_arrival(true, 100, t0, None);
    w.on_arrival(false, 100, t0 + 10_000_000, Some(&sig));
    ps43::stall_round(&mut w, Some(&mut p), &log, t0 + 300_000_000);
    assert!(!w.active() && p.take_cmds().is_empty(), "not late yet");
    ps43::stall_round(&mut w, Some(&mut p), &log, t0 + 420_000_000);
    assert!(w.active(), "one episode (late try)");
    assert!(p.sh.g43.pause_stall.load(Ordering::SeqCst), "live: the sender pauses");
    let c = p.take_cmds();
    let req = match c.as_slice() { [Cmd::Status(r)] => (**r).clone(), x => panic!("{x:?}") };
    assert_eq!(req.sig, sig);
    // the status read: landed OK, 9,000 tokens at processed -> a position via "status"
    p.on_msg(PsMsg::Status(Box::new(ps43::StatusRes { req, st: Some((101, true)), tokens: Some(9_000), ms: 1.0 })), &|_| false);
    assert_eq!(p.pos.len(), 1);
    assert_eq!(p.pos[&MINT].via, "status");
    assert_eq!(p.pos[&MINT].tokens, 9_000);
    // 1.5 s blind (> DEADMAN_MS 1000): the dead-man sells at once, no RPC first (a queued Sell of the known tokens)
    p.d43.blind = Some(arbx::fast::mono_ns().saturating_sub(1_500_000_000));
    p.tick(101, None);
    let c = p.take_cmds();
    assert!(c.iter().any(|c| matches!(c, Cmd::Sell { known: Some(9_000), .. })), "{c:?}");
    assert_eq!(p.pos[&MINT].exit.map(|e| e.0), Some("deadman"));
    // the feed comes back with the same fill: the buy gets the feed's values, nothing opened or merged twice
    let ev = TradeEvent { mint: MINT, sol: 399_000_000, tok: 9_100, buy: true, user: USER, vsol: 40_000_000_000, vtok: 700_000_000_000_000, fbps: 95, cbps: 30 };
    let x = arbx::feeds::ExecInfo { index: 5, fee: 5_090, ok: true, trades: vec![ev], creates: Vec::new(), mayhem: false };
    let a = arbx::feeds::Arrival { feed: 0, slot: 101, t_rx: 1, t_decoded: 1, executed: Some(true), tx: arbx::tx::Tx { sig, keys: vec![USER], ..Default::default() },
        poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
    p.on_arrival(&a, 101);
    p.on_exec(&a, &x, 101, |_| None, &|_| false, None);
    assert_eq!(p.pos.len(), 1);
    assert_eq!(p.pos[&MINT].buys.len(), 1, "never a second buy");
    assert_eq!(p.pos[&MINT].buys[0].via, "status+feed");
    assert_eq!(p.st.fills, 0, "the feed's fill path did not run");
    let r = recs(&orx);
    assert!(r.iter().any(|r| r["ev"] == "presend_live_blind" && r["act"] == "opened"));
    assert!(r.iter().any(|r| r["ev"] == "presend_live_blind" && r["act"] == "feed_confirmed"));
    // the feed back: the episode ends, the pause lifts
    w.on_arrival(true, 101, t0 + 500_000_000, None);
    ps43::stall_round(&mut w, Some(&mut p), &log, t0 + 520_000_000);
    assert!(!w.active() && !p.sh.g43.pause_stall.load(Ordering::SeqCst));
}

/// log mode (the default): the same blind try asks nothing and changes nothing; it is recorded as what would be done
#[test]
fn dip43a_blind_log_mode_acts_on_nothing() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let (mut p, _atx, orx, sig) = blind_setup(&[]);
    let log = DipLog::open(None).unwrap();
    let mut w = ps43_stall::Watch::new(p.cfg.c43.stall);
    let t0 = arbx::fast::mono_ns();
    w.on_arrival(true, 100, t0, None);
    w.on_arrival(false, 100, t0 + 10_000_000, Some(&sig));
    ps43::stall_round(&mut w, Some(&mut p), &log, t0 + 420_000_000);
    assert!(w.active());
    assert!(!p.sh.g43.pause_stall.load(Ordering::SeqCst), "log: never paused");
    assert!(p.take_cmds().is_empty(), "log: no status read");
    let r = recs(&orx);
    assert!(r.iter().any(|r| r["ev"] == "presend_live_blind" && r["act"] == "would_status_read"), "{r:?}");
    // dip42's backstop
    assert_eq!(p.wall43(), p.cfg.exit_slots * 400 + 3_000);
    assert_eq!(time_exit_due(10, 9, 2, 3_801, 0), Some("time-limit-wall"));
    assert_eq!(time_exit_due(10, 9, 2, 3_800, 0), None);
}

// ---- A9 control keys --------------------------------------------------------------------------------------------------------

/// every dip43 key: parsed, applied (log <-> live), reported; a bad value refused (the modes stay)
#[test]
fn dip43a_ctl_every_key() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let bots = std::env::temp_dir().join(format!("dip43a-{}-bots.json", std::process::id()));
    let mut b0 = [0xB0u8; 32]; b0[31] = 0x42;
    std::fs::write(&bots, serde_json::json!({"version": "t1", "engine_view": [b58(&b0)]}).to_string()).unwrap();
    let bp = bots.display().to_string();
    let c = cfg(&["--presend-live-mint-ledger", "0.1", "--presend-fpnb-log", "on", "--presend-fpnb-bots", bp.as_str(), "--presend-live-fpnb-strict", "0.3"]).unwrap().unwrap();
    let fp_ok = true;
    let (mut p, _atx, _orx) = PsLive::for_test(c, USER);
    for (i, k) in ps43::G43::KEYS.iter().enumerate() {
        let mut ctl = ps43::Ctl43::default();
        ctl.g[i] = Some(false);
        let ch = p.ctl43_apply(&ctl);
        assert!(ch.iter().any(|x| x.0 == *k && x.2 == "log"), "{k}: {ch:?}");
        assert_eq!(ps43::ctl43_parse(format!("{{\"{k}\": \"log\"}}").as_bytes()).unwrap().g[i], Some(false), "{k}");
        ctl.g[i] = Some(true);
        assert!(p.ctl43_apply(&ctl).iter().any(|x| x.0 == *k && x.2 == "live"), "{k}");
        assert!(ps43::ctl43_parse(format!("{{\"{k}\": \"maybe\"}}").as_bytes()).is_err(), "{k}");
    }
    // breaker "log": a trip pauses nothing
    p.sh.brk_until.store(u64::MAX, Ordering::SeqCst);
    assert!(breaker_paused(&p.sh));
    p.ctl43_apply(&ps43::ctl43_parse(br#"{"breaker": "log"}"#).unwrap());
    assert!(!breaker_paused(&p.sh));
    p.ctl43_apply(&ps43::ctl43_parse(br#"{"breaker": "live"}"#).unwrap());
    assert!(breaker_paused(&p.sh));
    p.sh.brk_until.store(0, Ordering::SeqCst);
    // stall / deadman / mint_ledger
    let k = ps43::ctl43_parse(br#"{"stall": "live", "deadman": "live", "mint_ledger": "live", "fanout": "live"}"#).unwrap();
    let ch = p.ctl43_apply(&k);
    assert!(p.d43.stall_live && p.d43.deadman_live && p.cfg.c43.ml_live, "{ch:?}");
    assert!(ch.iter().any(|x| x.0 == "fanout_ignored"), "fanout needs its flag");
    // QF2's keys need --presend-live-qf2; bad values refused
    assert!(p.ctl43_apply(&ps43::ctl43_parse(br#"{"qf2_size": 0.3, "qf2_min_age": 10}"#).unwrap()).iter().any(|x| x.0 == "qf2_ignored"));
    assert!(ps43::ctl43_parse(br#"{"qf2_size": 9}"#).is_err() && ps43::ctl43_parse(br#"{"qf2_min_age": -1}"#).is_err());
    // FP-NOBOT's bits and strict (with its thread)
    if fp_ok {
        let gs = p.fp.as_ref().unwrap().gs.clone();
        p.ctl43_apply(&ps43::ctl43_parse(br#"{"fpnb_t2": "live", "fpnb_rearm": "log", "fpnb_strict": "live"}"#).unwrap());
        assert_eq!(gs.mode.load(Ordering::SeqCst), 1);
        assert!(gs.strict_live.load(Ordering::SeqCst));
    }
    assert_eq!(ps43::ctl43_parse(br#"{"fpnb_t2": "live"}"#).unwrap().fpnb_t2, Some(true));
    // an empty file changes nothing
    assert!(p.ctl43_apply(&ps43::ctl43_parse(b"{}").unwrap()).is_empty());
}

/// QF2's size and minimum age keys (with --presend-live-qf2): the size within the start's checked sizes; the age the 6th filter field
#[test]
fn dip43a_ctl_qf2_size_and_age() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let c = cfg(&["--presend-live-dumper-ledger", "on", "--presend-live-qf2", "5:0.3:10", "--presend-live-wide-size-sol", "0.5"]).unwrap().unwrap();
    let (mut p, _atx, _orx) = PsLive::for_test(c, USER);
    let ch = p.ctl43_apply(&ps43::ctl43_parse(br#"{"qf2_size": 0.3, "qf2_min_age": 10}"#).unwrap());
    assert!(ch.iter().any(|x| x.0 == "qf2_size") && ch.iter().any(|x| x.0 == "qf2_min_age"), "{ch:?}");
    let w = p.wd.as_ref().unwrap();
    assert_eq!((w.size_of(psdl::Kind::Qf2), w.size_of(psdl::Kind::Wide), w.filt.age_min), (300_000_000, 500_000_000, 10));
    assert_eq!(w.filt.check(3_000_000_000, 50_000_000_000, 9).2, false);
    assert_eq!(w.filt.check(3_000_000_000, 50_000_000_000, 10).2, true);
    // above the start's largest size: refused
    assert!(p.ctl43_apply(&ps43::ctl43_parse(br#"{"qf2_size": 0.9}"#).unwrap()).iter().any(|x| x.0 == "qf2_size_refused"));
    // the flag's 6th field; 5 fields = dip42's spec
    assert_eq!(psdl::qf_filt_parse("2:8:36:70:300").unwrap().age_min, 0);
    assert_eq!(psdl::qf_filt_parse("2:8:36:70:300").unwrap().spec(), "2:8:36:70:300");
    assert_eq!(psdl::qf_filt_parse("2:8:36:70:300:10").unwrap().age_min, 10);
    assert!(psdl::qf_filt_parse("2:8:36:70:300:400").is_err());
}

/// the control file's "botdepth": "log" is refused (the gate stays live) unless --presend-live-botdepth-allow-log
#[test]
fn dip43a_botdepth_locked_live() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let f = std::env::temp_dir().join(format!("dip43a_ctl_{}.json", std::process::id()));
    std::fs::write(&f, br#"{"botdepth": "log"}"#).unwrap();
    let fp = f.display().to_string();
    for (allow, want) in [(false, true), (true, false)] {
        let mut ex = vec!["--presend-live-botdepth", "3:100", "--presend-live-botdepth-list", "/nonexistent-list.json", "--presend-live-botdepth-mode", "live",
            "--presend-live-ledger-control", fp.as_str()];
        if allow { ex.push("--presend-live-botdepth-allow-log"); }
        let c = cfg(&ex).unwrap().unwrap();
        let (mut p, _atx, orx) = PsLive::for_test(c, USER);
        p.ledger_ctl_open();
        assert_eq!(p.sh.bd.live.load(Ordering::SeqCst), want, "allow {allow}");
        let r = recs(&orx);
        assert_eq!(r.iter().any(|r| r["botdepth_refused"].is_string()), !allow, "{r:?}");
    }
    let _ = std::fs::remove_file(&f);
}

// ---- A8 / A5 / A6 ------------------------------------------------------------------------------------------------------------

/// the sender's accounting: due / sent / refused per reason and per slot; on the disarm record as not_sent (only with the flag)
#[test]
fn dip43a_acct_not_sent() {
    let sh = ps43::Sh43::default();
    // off: nothing counted
    ps43::cur_set(&sh, 5, 100); ps43::acct_skip(&sh, "rate_global"); ps43::acct_sent(&sh);
    assert!(sh.ns.lock().unwrap().is_empty());
    sh.acct.store(true, Ordering::SeqCst);
    ps43::cur_set(&sh, 5, 100); ps43::acct_skip(&sh, "rate_global");
    ps43::cur_set(&sh, 5, 100); ps43::acct_skip(&sh, "rate_path_config");
    ps43::cur_set(&sh, 5, 100); ps43::acct_skip(&sh, "paused_presend_position");
    ps43::cur_set(&sh, 5, 101); ps43::acct_skip(&sh, "paused_stall");
    ps43::cur_set(&sh, 5, 101); ps43::acct_skip(&sh, "untradeable");
    ps43::cur_set(&sh, 5, 101); ps43::acct_sent(&sh);
    let n = sh.ns.lock().unwrap()[&5].clone();
    assert_eq!((n.due, n.sent, n.rate_global, n.rate_path, n.paused_position, n.paused_stall, n.other), (6, 1, 1, 1, 1, 1, 1));
    assert_eq!(n.slots, vec![(100, 3, 0, 3), (101, 3, 1, 2)]);
    assert_eq!(n.due, n.sent + n.rate_global + n.rate_path + n.paused_position + n.paused_stall + n.other, "window sums add up");
    // another thread (the main loop) charges nothing
    std::thread::spawn(move || { ps43::acct_skip(&sh, "rate_global"); assert_eq!(sh.ns.lock().unwrap()[&5].rate_global, 1); }).join().unwrap();
}

/// unseen tries' fees booked once their deadline passed (A8 on); off: dip42's (nothing)
#[test]
fn dip43a_acct_unseen_fee() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    for on in [false, true] {
        let c = cfg(if on { &["--presend-live-acct", "on"] } else { &[] }).unwrap().unwrap();
        let ff = c.fail_fee();
        let (mut p, atx, _orx) = PsLive::for_test(c, USER);
        p.d43_start();
        atx.send(att(3, [9u8; 64], 100)).unwrap();
        p.tick(100, None);
        p.tick(105, None);
        assert_eq!(p.d43.unseen, if on { (1, ff) } else { (0, 0) });
    }
}

/// CASCADE verdicts on a hand-made book: 2 of the top-6 holders below 90% of their signing balance -> G-A abort; 1 -> no; a closed account = 0
#[test]
fn dip43a_cascade_verdicts() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let c = cfg(&["--presend-live-fam-log", "--presend-live-cascade", "on"]).unwrap().unwrap();
    let (mut p, _atx, _orx) = PsLive::for_test(c, USER);
    let mut b = arbx::ps43_book::TBook::new();
    let s1 = (0.01 * pl::SUPPLY) as u64;
    b.create(MINT, 1, [0xCCu8; 32]);
    let h: Vec<Pk> = (1..=7u8).map(|i| [i; 32]).collect();
    for (i, w) in h.iter().enumerate() { b.post(&arbx::feeds::TokBal { mint: MINT, owner: *w, acct: *w, amount: s1 * (10 - i as u64) }, 2); }
    p.d43.book = Some(b);
    let set: ps43::HSet = p.d43.book.as_ref().unwrap().top_holders(&MINT, 8).into_iter().map(|(w, a)| (w, a, w == h[0])).collect();
    let v = p.cascade43(&MINT, &set);
    assert_eq!((v["ga"]["below"].as_u64(), v["ga"]["abort"].as_bool(), v["gd"]["abort"].as_bool()), (Some(0), Some(false), Some(false)));
    // one leaves (sold to 50%): no abort
    p.d43.book.as_mut().unwrap().post(&arbx::feeds::TokBal { mint: MINT, owner: h[1], acct: h[1], amount: s1 * 4 }, 3);
    assert_eq!(p.cascade43(&MINT, &set)["ga"]["abort"], false);
    // a second one closes its account (0): G-A aborts; the guards' rule (trigger h0 left out) too
    p.d43.book.as_mut().unwrap().post(&arbx::feeds::TokBal { mint: MINT, owner: h[2], acct: h[2], amount: 0 }, 3);
    let v = p.cascade43(&MINT, &set);
    assert_eq!((v["ga"]["below"].as_u64(), v["ga"]["abort"].as_bool(), v["gd"]["below"].as_u64(), v["gd"]["abort"].as_bool()), (Some(2), Some(true), Some(2), Some(true)));
    // the trigger wallet selling does not count for the guards' rule
    let set2: ps43::HSet = vec![(h[0], s1 * 10, true), (h[3], s1 * 7, false)];
    p.d43.book.as_mut().unwrap().post(&arbx::feeds::TokBal { mint: MINT, owner: h[0], acct: h[0], amount: 0 }, 4);
    assert_eq!(p.cascade43(&MINT, &set2)["gd"]["below"], 0);
}

/// the engine's paper landing: entry at the first trade 12% under the trigger price, out at a slot end at +-20% (or the 6-slot timer)
#[test]
fn dip43a_mint_ledger_paper() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let c = cfg(&["--presend-live-mint-ledger", "0.10"]).unwrap().unwrap();
    let (mut p, _atx, orx) = PsLive::for_test(c, USER);
    let tr = |s: u64, vsol: u64, vtok: u64| pl::Trade { mint: MINT, s, i: 1, j: 0, sig: [s as u8; 64], user: [7u8; 32], buy: false, sol: 1, tok: 1, vsol, vtok, fbps: 95, cbps: 30, t_rx: s };
    let t0 = tr(10, 50_000_000_000, 600_000_000_000_000);
    p.paper43(&t0, None, 400_000_000);
    p.paper43(&t0, Some("create_slot"), 400_000_000);
    assert_eq!(p.d43.papers.len(), 1, "structural triggers have no paper");
    // 15% under: entry; then -30% by the next slot end: out at that slot's end
    p.trade43(&tr(11, 42_000_000_000, 714_000_000_000_000));
    p.trade43(&tr(12, 30_000_000_000, 1_000_000_000_000_000));
    p.trade43(&tr(13, 30_000_000_000, 1_000_000_000_000_000));
    assert!(p.d43.papers.is_empty());
    let (n, worst, block) = p.ml_view43(&MINT).unwrap();
    assert!(n == 1 && worst < -100_000_000 && block, "{n} {worst}");
    assert!(recs(&orx).iter().any(|r| r["ev"] == "presend_live_mint_ledger" && r["paper"] == true));
}

// ---- flags -----------------------------------------------------------------------------------------------------------------

#[test]
fn dip43a_flags_and_refusals() {
    let c = cfg(&[]).unwrap().unwrap();
    assert!(!c.c43.any() && c.c43.stall == ps43_stall::StallCfg::default(), "no flag: everything off / log");
    assert!(c.json().get("dip43").is_none(), "the start record is dip42's");
    let c = cfg(&["--presend-live-stall-mode", "live", "--presend-live-stall", "2000:10:500", "--presend-live-deadman", "live", "--presend-live-deadman-ms", "800"]).unwrap().unwrap();
    assert_eq!((c.c43.stall.live, c.c43.stall.silent_ms, c.c43.stall.lag_slots, c.c43.stall.late_ms, c.c43.stall.deadman_live, c.c43.stall.deadman_ms), (true, 2000, 10, 500, true, 800));
    assert!(c.json()["dip43"].is_object());
    let c = cfg(&["--presend-live-fam-log", "--presend-live-cascade", "on", "--presend-live-fanout", "10"]).unwrap().unwrap();
    assert!(c.c43.tbal && c.c43.cascade && c.c43.fanout == Some(10) && !c.c43.fanout_live);
    for bad in [&["--presend-live-tbal", "on"][..], &["--presend-live-fanout", "10"], &["--presend-live-stall-mode", "on"], &["--presend-live-stall", "1:1:1"],
        &["--presend-live-deadman-ms", "50"], &["--presend-live-mint-ledger", "9"], &["--presend-live-mint-ledger-mode", "live"], &["--presend-live-fpnb-strict", "0.3"],
        &["--presend-live-fanout-mode", "live"], &["--presend-live-acct", "yes"]] {
        assert!(cfg(bad).is_err(), "{bad:?} must be refused");
    }
    // without --presend-live every dip43 flag is refused
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-live-acct", "on"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1).is_err());
    // the engine's flag check knows every dip43 flag
    for f in A43FLAGS { assert!(ENGINE_SRC.contains(&format!("\"{f}\"")), "{f}"); }
}

// ===================================================================================================================
// dip36 LOG-ONLY FP-NOBOT tests (11-05 PKT; pslog36.rs, src/fpnb.rs): --presend-fpnb-log on|off, --presend-fpnb-bots FILE,
// --presend-fpnb-preload FILE. Off: nothing of it exists (no records, no thread). On: arm / send / fill records through the real hooks
// (on_exec, trigger, drain_atts, fill), never a decision (the other records byte for byte the same); the bot list hot-reloads with
// membership at query time; the preload file.
// ===================================================================================================================
use super::*;
use super::pslog36::*;
use arbx::dip::{CreateEvent, TradeEvent};
use arbx::fpnb as fp;

const USER: Pk = [0x5Au8; 32];
const CREATOR: Pk = [0xC1u8; 32];
const S: u64 = 1_000_000_000;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000) }
fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| o.rec()).collect() }
fn w(k: u8) -> Pk { let mut x = [k; 32]; x[31] = 0x42; x }
fn tmp(name: &str, body: &str) -> String {
    let d = std::env::temp_dir().join(format!("dip36-{}-{name}", std::process::id()));
    std::fs::write(&d, body).unwrap();
    d.to_string_lossy().to_string()
}
fn list_of(ws: &[Pk]) -> String { serde_json::json!({"version": "t1", "engine_view": ws.iter().map(|k| fp::b58(k)).collect::<Vec<_>>()}).to_string() }

struct Tk { mint: Pk, v: u64, t: u64, launch: Launch }
impl Tk {
    fn new(k: u8) -> Tk { let mint = [k; 32]; Tk { mint, v: 30 * S, t: 1_073_000_000_000_000, launch: snipe_build::launch_from_target(mint, CREATOR) } }
    fn buy(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v + sol) as u128) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn create(&self) -> CreateEvent { CreateEvent { mint: self.mint, bonding_curve: self.launch.bonding_curve, user: CREATOR, creator: CREATOR } }
}

fn tx(p: &mut PsLive, slot: u64, idx: u64, sig: Option<[u8; 64]>, payer: Pk, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>, l: &Launch) {
    let sig = sig.unwrap_or_else(|| { let mut s = [0u8; 64]; s[..8].copy_from_slice(&slot.to_be_bytes()); s[8..16].copy_from_slice(&idx.to_be_bytes()); s[16] = 0x36; s });
    let x = arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades, creates, mayhem: false };
    let a = arbx::feeds::Arrival { feed: 0, slot, t_rx: slot * 1_000_000 + idx, t_decoded: slot * 1_000_000 + idx, executed: Some(true),
        tx: arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(Arc::new(x.clone())) };
    let l = l.clone();
    p.on_arrival(&a, slot);
    p.on_exec(&a, &x, slot, move |m: &Pk| (*m == l.mint).then(|| l.clone()), &|_| false, None);
}

#[test]
fn dip36_fpnb_flags() {
    let bots = tmp("flags.json", &list_of(&[w(0xB0)]));
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(!c0.fpnb_log && c0.fpnb_bots.is_none() && c0.fpnb_preload.is_none(), "default off");
    assert!(c0.json().get("fpnb_log").is_none(), "off: dip35's start record");
    let c = cfg(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots, "--presend-fpnb-preload", "/no/such/preload.bin"]).unwrap().unwrap();
    assert!(c.fpnb_log && c.fpnb_bots.as_deref() == Some(bots.as_str()) && c.fpnb_preload.as_deref() == Some("/no/such/preload.bin"));
    assert!(c.json()["fpnb_log"]["thr_t2"] == fp::THR_T2 && c.json()["fpnb_log"]["bots"] == bots.as_str(), "{}", c.json());
    assert!(!cfg(&["--presend-fpnb-log", "off", "--presend-fpnb-bots", &bots]).is_ok_and(|c| c.is_some_and(|c| c.fpnb_log)), "off + a path: refused or off");
    for (a, needle) in [(&["--presend-fpnb-log", "on"][..], "needs --presend-fpnb-bots"), (&["--presend-fpnb-log", "yes"][..], "on | off"),
        (&["--presend-fpnb-bots", "/x"][..], "needs --presend-fpnb-log on"), (&["--presend-fpnb-preload", "/x"][..], "needs --presend-fpnb-log on"),
        (&["--presend-fpnb-log", "on", "--presend-fpnb-bots"][..], "needs a path"), (&["--presend-fpnb-log", "on", "--presend-fpnb-bots", "--presend-live-k"][..], "needs a path"),
        (&["--presend-skip2-log", "on"][..], "needs --presend-fpnb-log on"), (&["--presend-fpnb-log", "on", "--presend-fpnb-bots", "/x", "--presend-skip2-seed", "/s"][..], "needs --presend-skip2-log on"),
        (&["--presend-fpnb-log", "on", "--presend-fpnb-bots", "/x", "--presend-skip2-log", "maybe"][..], "on | off")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    for f in ["--presend-fpnb-log", "--presend-fpnb-bots", "--presend-fpnb-preload"] {
        let e = Cfg::from_argv(&["snipe_engine", "--dip", "--presend-shadow", f, "x"].iter().map(|s| s.to_string()).collect::<Vec<_>>(), &arbx::presend::Params::default(), true, 1_000_000_000)
            .unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
    assert!(crate::check_flags(&args(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", "/root/dip/bots.json", "--presend-fpnb-preload", "/root/dip/fpnb_pre.bin"])).is_ok());
    // a bad bot list refuses the start (the probe's thread is never made)
    let bad = tmp("bad.json", "{\"engine_view\": []}");
    let cb = cfg(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bad]).unwrap().unwrap();
    let (out, _o) = crossbeam_channel::unbounded();
    assert!(Fp::start(&cb, USER, &out, true).is_err());
    assert!(Fp::start(&c0, USER, &out, true).unwrap().is_none(), "off: nothing");
}

/// the hooks end to end: create + trades + a bot's failed buy -> the T2 trigger arms -> stage "arm"; an attempt at slot t -> stage "send"
/// once the feed passed t; our fill at F -> stage "fill" (t = F - 1); every other record the same as with the flag off
#[test]
fn dip36_fpnb_end_to_end() {
    let _g = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let bot = w(0xB0);
    let bots = tmp("e2e.json", &list_of(&[bot]));
    let run = |extra: &[&str]| -> (PsLive, Vec<serde_json::Value>) {
        let (mut p, atx, orx) = PsLive::for_test(cfg(extra).unwrap().unwrap(), USER);
        let mut tk = Tk::new(0x31);
        let l = tk.launch.clone();
        let dev = tk.buy(CREATOR, S / 2);
        tx(&mut p, 1000, 3, None, CREATOR, vec![dev], vec![tk.create()], &l);
        let b1 = tk.buy(bot, S / 4);
        tx(&mut p, 1001, 5, None, bot, vec![b1], vec![], &l);
        // a failed buy of the bot on this mint (the feed's tap; inline here)
        if let Some(f) = p.fp.as_mut() { f.send(FpMsg::Fail(arbx::feeds::FailTx { slot: 1002, idx: 7, payer: bot, buy: true, keys: vec![bot, [9; 32], tk.mint] })); }
        let o1 = tk.buy(w(0xA1), S / 5);
        tx(&mut p, 1003, 2, None, w(0xA1), vec![o1], vec![], &l);
        let wh = tk.buy(w(0xEE), 2 * S);
        tx(&mut p, 1005, 50, None, w(0xEE), vec![wh], vec![], &l);
        // an attempt at slot 1006 (the sender's registration), the feed moves on, a bot buys in 1006
        let mut sg = [0u8; 64]; sg[0] = 0x36; sg[1] = 0xA7;
        atx.send(Att { w: 1, n: 1, mint: tk.mint, sig: sg, tag: pl::PS_TAG | 1, path: "helius-ps".into(), client: "JitoLabs".into(), slot: 1006, deadline: 1007,
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (1006, 0, 0), t_send: 1006 * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
            tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None }).unwrap();
        p.drain_atts();
        let b2 = tk.buy(bot, S / 4);
        tx(&mut p, 1006, 4, None, bot, vec![b2], vec![], &l);
        let o2 = tk.buy(w(0xA2), S / 5);
        tx(&mut p, 1007, 1, None, w(0xA2), vec![o2], vec![], &l);
        // our fill in 1008 (the attempt's signature)
        let me = tk.buy(USER, 4 * S / 10);
        tx(&mut p, 1008, 9, Some(sg), USER, vec![me], vec![], &l);
        let r = recs(&orx);
        (p, r)
    };
    let (p0, r0) = run(&[]);
    let (p1, r1) = run(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots]);
    assert!(p0.fp.is_none() && p1.fp.is_some());
    assert!(r0.iter().all(|r| !r["ev"].as_str().unwrap_or("").starts_with("presend_live_fpnb")), "off: no record");
    assert!(r0.iter().any(|r| r["ev"] == "presend_live_arm") && r0.iter().any(|r| r["ev"] == "presend_live_fill"), "armed and filled: {r0:?}");
    // NEVER a decision: every other record identical (the same arm, attempt bookkeeping, fill, exits)
    // (the wall-clock fields of the disarm record differ between any two runs)
    let strip = |v: &Vec<serde_json::Value>| -> Vec<String> { v.iter().filter(|r| !r["ev"].as_str().unwrap_or("").starts_with("presend_live_fpnb")).map(|r| {
        let mut r = r.clone();
        if r["ev"] == "presend_live_disarm" { if let Some(o) = r.as_object_mut() { o.remove("armed_ms"); o.remove("t"); } }
        r.to_string()
    }).collect() };
    assert_eq!(strip(&r0), strip(&r1), "the flag changes nothing else");
    let fpr: Vec<&serde_json::Value> = r1.iter().filter(|r| r["ev"] == "presend_live_fpnb").collect();
    let arm = fpr.iter().find(|r| r["stage"] == "arm").expect("arm stage");
    let x = |r: &serde_json::Value, k: &str| r["x"][fp::feat_ix(k)].clone();
    assert!(arm["w"] == 1 && arm["kind"] == "T2" && arm["trig_slot"] == 1005 && arm["trig_idx"] == 50 && arm["covered"] == true && arm["warm"] == false && arm["block"] == false, "{arm}");
    assert!(arm["score"].as_f64().is_some_and(|s| s > 0.0 && s < 1.0) && arm["list"]["n"] == 1 && arm["list"]["ver"] == "t1" && arm["x"].as_array().unwrap().len() == 153);
    assert!(x(arm, "is_T2") == 1.0 && x(arm, "n_prior") == 3.0 && x(arm, "bot_tr_n") == 1.0 && x(arm, "bfail_pre") == 1.0 && x(arm, "fail_all_pre") == 1.0 && x(arm, "age") == 5.0
        && x(arm, "age_cens") == 1.0 && x(arm, "pf_n") == 0.0 && x(arm, "pf_slots") == 1.0 && x(arm, "a_age") == 5.0 && x(arm, "g_nd_30m").is_null() && x(arm, "wh_n").is_null(), "{arm}");
    let send = fpr.iter().find(|r| r["stage"] == "send").expect("send stage");
    assert!(send["slot"] == 1006 && send["n"] == serde_json::json!([1]) && send["xs"].as_array().unwrap().len() == 20, "{send}");
    let xs = |k: &str| send["xs"][fp::SEND_IX.iter().position(|i| *i == fp::feat_ix(k)).unwrap()].clone();
    assert!(xs("pf_n") == 0.0 && xs("pf_slots") == 2.0 && xs("pf_bot_buys") == 0.0, "data <= t - 1: {send}");
    let fill = fpr.iter().find(|r| r["stage"] == "fill").expect("fill stage");
    assert!(fill["fill_slot"] == 1008 && fill["slot"] == 1007 && fill["pid"].is_u64() && fill["kind"] == "T2", "{fill}");
    assert!(x(fill, "pf_n") == 1.0 && x(fill, "pf_bot_buys") == 1.0 && x(fill, "pf_bot_w") == 1.0 && x(fill, "pf_slots") == 3.0 && x(fill, "pf_last_gap") == 0.0, "{fill}");
    let st = p1.fp.as_ref().unwrap().st.lock().unwrap().clone();
    assert!(st.arms == 1 && st.sends == 1 && st.fills == 1 && st.arm_blocks == 0, "{st:?}");
    // dip36 skip2 (log-only) on the same records: score / score_nf / thr / skip on arm, send and fill; the 55 arm inputs on the arm;
    // nothing else changes
    let (p2, r2) = run(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots, "--presend-skip2-log", "on"]);
    assert_eq!(strip(&r0), strip(&r2), "skip2 changes nothing else");
    let f2: Vec<&serde_json::Value> = r2.iter().filter(|r| r["ev"] == "presend_live_fpnb").collect();
    for stage in ["arm", "send", "fill"] {
        let r = f2.iter().find(|r| r["stage"] == stage).unwrap();
        let s = &r["skip2"];
        assert!(s["score"].is_f64() && s["score_nf"].is_f64() && s["thr"] == -0.31902030557373995 && s["skip"].is_boolean() && s["skip_nf"].is_boolean(), "{stage}: {r}");
    }
    let a2 = f2.iter().find(|r| r["stage"] == "arm").unwrap();
    assert!(a2["x2"].as_array().unwrap().len() == 55 && a2["x2"][0] == 1.0 && a2["x2"][3] == 0.4, "is_T2, spend: {}", a2["x2"]);
    assert!(fpr.iter().all(|r| r.get("skip2").is_none()), "skip2 off: no field");
    let st2 = p2.fp.as_ref().unwrap().st.lock().unwrap().clone();
    assert!(st2.s2_fills == 1 && st2.skip2["on"] == true, "{st2:?}");
}

/// the bot list: re-read on change, membership at QUERY time (a wallet added later counts for its earlier events), a bad file keeps the
/// last good list (a record), the preload file (whale history + our earlier results)
#[test]
fn dip36_fpnb_bots_reload_and_preload() {
    let (b1, b2) = (w(0xB1), w(0xB2));
    let path = tmp("reload.json", &list_of(&[b1]));
    let c = cfg(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &path]).unwrap().unwrap();
    let (out, orx) = crossbeam_channel::unbounded();
    let mut f = Fp::start(&c, USER, &out, true).unwrap().unwrap();
    let mint = [0x44u8; 32];
    let row = |s: u64, i: u32, u: Pk| fp::Row { s, i, j: 0, buy: true, user: u, sol: S / 10, tok: 1_000_000_000_000, vsol: 31 * S };
    f.send(FpMsg::Create(mint, 500));
    f.send(FpMsg::Trade(mint, row(500, 1, w(0x01))));
    f.send(FpMsg::Trade(mint, row(501, 1, b2)));   // b2 is not listed yet
    f.send(FpMsg::Trade(mint, row(502, 1, b1)));
    let arm = |f: &mut Fp, w_: u64| {
        let rec = serde_json::json!({"ev": "presend_live_arm", "trig": {"pct": 7.0, "sol": 2e9, "age_slots": 3, "vsol": 33e9, "t": 1_793_800_000_000_000_000u64}});
        f.send(FpMsg::Trade(mint, row(503, w_ as u32, w(0xEE))));
        f.send(FpMsg::Arm(Box::new(FpArm { w: w_, rearm: false, mint, s: 503, i: w_ as u32, whale: w(0xEE), t0: 1_793_800_000_000_000_000, arm_slot: 503, creator: None, clk: 1_793_800_000_000_000_000, en_slot: 520, gate: None,
            excl: Vec::new(), rec })));
    };
    let arm_x = |orx: &crossbeam_channel::Receiver<Out>| -> (Vec<serde_json::Value>, serde_json::Value) {
        let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
        let a = r.iter().find(|x| x["stage"] == "arm").cloned().unwrap();
        (r, a)
    };
    let btn = fp::feat_ix("bot_tr_n");
    arm(&mut f, 1);
    let (_, a) = arm_x(&orx);
    assert_eq!(a["x"][btn], 1.0, "only b1");
    // the list gains b2: its EARLIER trade counts at the next query
    std::fs::write(&path, list_of(&[b1, b2])).unwrap();
    f.inline.as_ref().unwrap().lock().unwrap().reload_check(true);
    arm(&mut f, 2);
    let (r, a) = arm_x(&orx);
    assert!(r.iter().any(|x| x["ev"] == "presend_live_fpnb_bots" && x["ok"] == true && x["list"]["n"] == 2), "{r:?}");
    assert!(a["x"][btn] == 2.0 && a["list"]["n"] == 2, "membership at query time: {a}");
    // a bad file: the last good list stays, a record says so
    std::fs::write(&path, "{\"engine_view\": [\"nope\"]}").unwrap();
    f.inline.as_ref().unwrap().lock().unwrap().reload_check(true);
    arm(&mut f, 3);
    let (r, a) = arm_x(&orx);
    assert!(r.iter().any(|x| x["ev"] == "presend_live_fpnb_bots" && x["ok"] == false && x["kept"]["n"] == 2), "{r:?}");
    assert_eq!(a["x"][btn], 2.0);
    // a removed wallet stops counting at once
    std::fs::write(&path, list_of(&[b2])).unwrap();
    f.inline.as_ref().unwrap().lock().unwrap().reload_check(true);
    arm(&mut f, 4);
    let (_, a) = arm_x(&orx);
    assert_eq!(a["x"][btn], 1.0);
    { let st = f.st.lock().unwrap(); assert!(st.reloads == 2 && st.reload_fails == 1, "{st:?}"); }

    // the preload: the whale's history and an earlier own result
    let whale = w(0xEE);
    let other = 0x1111_2222_3333_4444u64;
    let rows: Vec<(u32, u64, u32, u8)> = vec![(0, other, 100, 3), (0, other, 108, 0), (0, 0x55, 120, 1)];
    let own = serde_json::json!([{"k": 1_793_799_000_000_000_000u64, "pnl": 0.03, "fol": 2, "mint": fp::b58(&[0x45; 32]), "whale": fp::b58(&whale), "creator": null}]);
    let head = serde_json::json!({"fpnb_preload": 1, "from_slot": 50, "to_slot": 499, "wallets": 1, "rows": rows.len(), "own": own, "shadow": [], "shadow_arms": []});
    let mut b = Vec::new();
    b.extend_from_slice(head.to_string().as_bytes()); b.push(b'\n');
    b.extend_from_slice(&whale);
    for (wi, m, s, fl) in &rows { b.extend_from_slice(&wi.to_le_bytes()); b.extend_from_slice(&m.to_le_bytes()); b.extend_from_slice(&s.to_le_bytes()); b.push(*fl); }
    let pre = std::env::temp_dir().join(format!("dip36-{}-pre.bin", std::process::id()));
    std::fs::write(&pre, &b).unwrap();
    let p = fp::preload_parse(&b).unwrap();
    assert!(p.wh.len() == 3 && p.own.len() == 1 && p.span.from == 50 && p.wh[0].0 == whale && p.wh[0].1.m == other && p.wh[0].1.f == 3);
    assert!(fp::preload_parse(&b[..b.len() - 3]).is_err(), "a short file is refused");
    let c = cfg(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &path, "--presend-fpnb-preload", pre.to_str().unwrap()]).unwrap().unwrap();
    let (out, orx) = crossbeam_channel::unbounded();
    let mut f = Fp::start(&c, USER, &out, true).unwrap().unwrap();
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    assert!(r.iter().any(|x| x["ev"] == "presend_live_fpnb_preload" && x["preload"]["ok"] == true && x["preload"]["wh_rows"] == 3), "{r:?}");
    f.send(FpMsg::Create(mint, 500));
    arm(&mut f, 9);
    let (_, a) = arm_x(&orx);
    // 503 slots are far less than 24 h: the whale inputs stay missing (FLAG 1), the hours available are logged; own results count
    assert!(a["wh_ok"] == false && a["x"][fp::feat_ix("wh_n")].is_null() && a["hist_h"].as_f64().unwrap() > 0.0, "{a}");
    assert!(a["x"][fp::feat_ix("o_wh_n")] == 1.0 && a["x"][fp::feat_ix("o_wh_sum")] == 0.03 && a["x"][fp::feat_ix("o_n_60m")] == 1.0, "{a}");
    // with the look-back covered (a store-level check): the hold clock from the preloaded rows
    let mut st = fp::Store::new(fp::ours());
    st.preload_wh(p.wh.clone(), fp::PreSpan { from: 50, to: 499 });
    st.wh_need = 0;
    st.create(mint, 500);
    st.trade(mint, row(503, 1, whale));
    let bl = fp::BotList::parse(list_of(&[b1]).as_bytes(), &fp::ours()).unwrap();
    let mut x = fp::X::default();
    st.arm_chain(&fp::ArmIn { t2: true, mint, s: 503, i: 1, whale }, &bl, &mut x);
    assert_eq!((x.get("wh_n"), x.get("wh_mints"), x.get("wh_big"), x.get("wh_sold_frac"), x.get("wh_q10")), (3.0, 2.0, 1.0, 0.5, 1.0));
}

/// dip36 LIVE GATE: the sender's check per kind (off / T2 / re-arm), a verdict for slot or slot + 1 only, fail open on none / a stale one,
/// not covered never blocks; the counters
#[test]
fn dip36_fpnb_gate_check_per_kind_and_fail_open() {
    assert_eq!(mode_parse("t2,rearm"), Ok(3));
    assert_eq!((mode_parse("t2"), mode_parse("rearm"), mode_parse("off"), mode_parse("rearm,t2"), mode_parse("both")), (Ok(1), Ok(2), Ok(0), Ok(3), Ok(3)));
    assert!(mode_parse("on").is_err() && mode_str(3) == "t2,rearm" && mode_str(0) == "off");
    let (g, gs) = (Gate::default(), GateShared::default());
    g.set(1000, true, true);
    // off: never withheld, nothing counted
    assert!(!gate_withhold(&g, &gs, 1000, false) && !gate_withhold(&g, &gs, 1000, true));
    assert_eq!(gs.open_stale[0].load(Ordering::Relaxed) + gs.passed[0].load(Ordering::Relaxed), 0);
    // T2 live: a T2 window at the verdict's slot (or the one before) is withheld; a re-arm window is not (its kind is off)
    gs.mode.store(1, Ordering::SeqCst);
    assert!(gate_withhold(&g, &gs, 1000, false) && gate_withhold(&g, &gs, 999, false));
    assert!(!gate_withhold(&g, &gs, 1000, true));
    // a stale verdict (the FP thread behind) / none: fail open, counted
    assert!(!gate_withhold(&g, &gs, 1001, false) && !gate_withhold(&g, &gs, 998, false));
    assert!(!gate_withhold(&Gate::default(), &gs, 1000, false));
    assert_eq!((gs.withheld[0].load(Ordering::Relaxed), gs.open_stale[0].load(Ordering::Relaxed), g.withheld.load(Ordering::Relaxed)), (2, 3, 2));
    // not covered: a block bit without the covered bit never withholds; a pass is counted
    g.set(1000, false, true);
    assert!(!gate_withhold(&g, &gs, 1000, false));
    g.set(1000, true, false);
    assert!(!gate_withhold(&g, &gs, 1000, false));
    assert_eq!(gs.passed[0].load(Ordering::Relaxed), 2);
    // re-arm live too
    gs.mode.store(3, Ordering::SeqCst);
    g.set(1000, true, true);
    assert!(gate_withhold(&g, &gs, 1000, true) && gs.withheld[1].load(Ordering::Relaxed) == 1);
}

/// dip36 LIVE GATE end to end on the FP thread (inline): the flag's mode; a window's verdict published at the arm and re-scored on every new
/// slot / trade of its token; a forced block withholds the sender's attempt; the control file flips the mode (and a bad one keeps it); the
/// window's end record (withheld sends, filled or not); with the log only nothing is ever withheld
#[test]
fn dip36_fpnb_gate_live_and_control_file() {
    let _g = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let bots = tmp("gate.json", &list_of(&[w(0xB0)]));
    let ctl = tmp("ctl.json", r#"{"live": ["rearm"]}"#);
    for (a, needle) in [(&["--presend-fpnb-live", "t2"][..], "need --presend-fpnb-log on"), (&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots, "--presend-fpnb-live", "x"][..], "t2 | rearm"),
        (&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots, "--presend-fpnb-control"][..], "needs a path")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    assert!(crate::check_flags(&args(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", "/b", "--presend-fpnb-live", "t2,rearm", "--presend-fpnb-control", "/c"])).is_ok());
    let c = cfg(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots, "--presend-fpnb-live", "t2,rearm"]).unwrap().unwrap();
    assert!(c.fpnb_live == 3 && c.json()["fpnb_live"]["mode"] == "t2,rearm");
    assert_eq!(cfg(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots]).unwrap().unwrap().fpnb_live, 0, "default off");
    // the scenario: T2 armed at 1005; a forced threshold (0: always block) with no warm-up
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    p.fp.as_ref().unwrap().inline.as_ref().unwrap().lock().unwrap().test_force(Some(0.0));
    let mut tk = Tk::new(0x37);
    let l = tk.launch.clone();
    let dev = tk.buy(CREATOR, S / 2);
    tx(&mut p, 1000, 3, None, CREATOR, vec![dev], vec![tk.create()], &l);
    let o1 = tk.buy(w(0xA1), S / 5);
    tx(&mut p, 1003, 2, None, w(0xA1), vec![o1], vec![], &l);
    let wh = tk.buy(w(0xEE), 2 * S);
    tx(&mut p, 1005, 50, None, w(0xEE), vec![wh], vec![], &l);
    let g = p.sh.wins.lock().unwrap().iter().find(|s| s.id == 1).unwrap().fpg.clone().expect("the window's gate");
    let gs = p.fp.as_ref().unwrap().gs.clone();
    assert_eq!(g.v.load(Ordering::SeqCst) >> 2, 1006, "published at the arm for the next slot");
    assert!(gate_withhold(&g, &gs, 1006, false), "a forced block: the attempt at 1006 is withheld");
    // a new slot re-scores: the verdict moves on
    let o2 = tk.buy(w(0xA2), S / 5);
    tx(&mut p, 1006, 4, None, w(0xA2), vec![o2], vec![], &l);
    assert_eq!(g.v.load(Ordering::SeqCst) >> 2, 1007);
    // the threshold back to "never" (a pass), re-scored on the token's next trade
    p.fp.as_ref().unwrap().inline.as_ref().unwrap().lock().unwrap().test_force(Some(2.0));
    let o3 = tk.buy(w(0xA3), S / 5);
    tx(&mut p, 1006, 6, None, w(0xA3), vec![o3], vec![], &l);
    assert!(!gate_withhold(&g, &gs, 1007, false), "re-scored: passes");
    p.fp.as_ref().unwrap().inline.as_ref().unwrap().lock().unwrap().test_force(Some(0.0));
    // the control file: re-arm only -> the T2 window is no longer gated; a bad file keeps the mode; back to both
    std::fs::write(&ctl, r#"{"live": ["rearm"]}"#).unwrap();
    {
        let f = p.fp.as_ref().unwrap();
        let mut wk = f.inline.as_ref().unwrap().lock().unwrap();
        wk.set_ctl_for_test(&ctl);
        wk.ctl_check(true);
    }
    assert_eq!(gs.mode.load(Ordering::SeqCst), 2);
    assert!(!gate_withhold(&g, &gs, 1007, false), "T2 not live now");
    std::fs::write(&ctl, "{bad").unwrap();
    p.fp.as_ref().unwrap().inline.as_ref().unwrap().lock().unwrap().ctl_check(true);
    assert_eq!(gs.mode.load(Ordering::SeqCst), 2, "a bad file keeps the mode");
    std::fs::write(&ctl, r#"{"live": ["t2", "rearm"]}"#).unwrap();
    p.fp.as_ref().unwrap().inline.as_ref().unwrap().lock().unwrap().ctl_check(true);
    assert_eq!(gs.mode.load(Ordering::SeqCst), 3);
    let o4 = tk.buy(w(0xA4), S / 5);
    tx(&mut p, 1007, 2, None, w(0xA4), vec![o4], vec![], &l);
    assert!(gate_withhold(&g, &gs, 1008, false));
    // an attempt still goes out later (the window stays armed) and fills: the fill record says how many were withheld
    let mut sg = [0u8; 64]; sg[0] = 0x37; sg[1] = 0xA7;
    atx.send(Att { w: 1, n: 9, mint: tk.mint, sig: sg, tag: pl::PS_TAG | 9, path: "helius-ps".into(), client: "JitoLabs".into(), slot: 1008, deadline: 1009,
        lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (1008, 0, 0), t_send: 1008 * 1_000_000, roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) },
        tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None }).unwrap();
    p.drain_atts();
    let me = tk.buy(USER, 4 * S / 10);
    tx(&mut p, 1009, 9, Some(sg), USER, vec![me], vec![], &l);
    let r = recs(&orx);
    let modes: Vec<&serde_json::Value> = r.iter().filter(|x| x["ev"] == "presend_live_fpnb_mode").collect();
    assert!(modes.iter().any(|m| m["ok"] == true && m["mode"] == "rearm" && m["was"] == "t2,rearm" && m["t"].is_u64()), "{modes:?}");
    assert!(modes.iter().any(|m| m["ok"] == false && m["mode"] == "rearm"), "the bad file logged: {modes:?}");
    assert!(modes.iter().any(|m| m["ok"] == true && m["mode"] == "t2,rearm" && m["was"] == "rearm"));
    assert!(r.iter().any(|x| x["ev"] == "presend_live_fpnb" && x["stage"] == "gate" && x["block"] == true && x["slot"] == 1006 && x["xs"].as_array().is_some_and(|a| a.len() == 20)));
    let fill = r.iter().find(|x| x["ev"] == "presend_live_fpnb" && x["stage"] == "fill").expect("fill");
    assert_eq!(fill["withheld"], 2, "withheld at 1006 and 1008 (1007 passed, then T2 was off): {fill}");
    let win = r.iter().find(|x| x["ev"] == "presend_live_fpnb_window").expect("the window's end");
    assert!(win["filled"] == true && win["withheld"] == fill["withheld"] && win["kind"] == "T2", "{win}");
    assert!(p.fp.as_ref().unwrap().status().contains("gate T2/re-arm: withheld"));
}

// ---- dip37b the SKIP-2 LIVE GATE (--presend-skip2-live; the ledger control file's "skip2") ----------------------------------------------

/// the sender's check on the skip2 verdict: per kind, a fresh covered "skip" withheld, a pass / not covered / no verdict never, the stale hold
#[test]
fn dip37b_skip2_gate_check() {
    let (g, gs) = (Gate::default(), GateShared::default());
    g.set2(1000, true, true);
    assert_eq!(skip2_withhold_why(&g, &gs, 1000, false), None, "off: never");
    assert_eq!(gs.s2_open[0].load(Ordering::Relaxed), 0, "off: nothing counted");
    gs.s2_mode.store(1, Ordering::SeqCst);
    assert_eq!((skip2_withhold_why(&g, &gs, 1000, false), skip2_withhold_why(&g, &gs, 999, false)), (Some(false), Some(false)), "T2 live: slot / slot + 1");
    assert_eq!(skip2_withhold_why(&g, &gs, 1000, true), None, "re-arm not live");
    assert_eq!(skip2_withhold_why(&g, &gs, 1001, false), None, "no fresh verdict: fail open");
    assert_eq!(skip2_withhold_why(&Gate::default(), &gs, 1000, false), None, "no verdict at all: fail open");
    g.set2(1000, false, true);
    assert_eq!(skip2_withhold_why(&g, &gs, 1000, false), None, "not covered: never");
    g.set2(1000, true, false);
    assert_eq!(skip2_withhold_why(&g, &gs, 1000, false), None, "a pass");
    assert_eq!((gs.s2_withheld[0].load(Ordering::Relaxed), gs.s2_open[0].load(Ordering::Relaxed), g.withheld2.load(Ordering::Relaxed)), (2, 2, 2));
    // the stale hold (--presend-fpnb-stale-hold): a recent skip held, an older one / an old pass / not covered open
    gs.s2_mode.store(3, Ordering::SeqCst);
    gs.stale_hold.store(2, Ordering::SeqCst);
    g.set2(1000, true, true);
    assert_eq!((skip2_withhold_why(&g, &gs, 1001, true), skip2_withhold_why(&g, &gs, 1002, false), skip2_withhold_why(&g, &gs, 1003, false)), (Some(true), Some(true), None));
    g.set2(1000, true, false);
    assert_eq!(skip2_withhold_why(&g, &gs, 1001, false), None);
    g.set2(1000, false, true);
    assert_eq!(skip2_withhold_why(&g, &gs, 1001, false), None);
    assert_eq!((gs.s2_stale[0].load(Ordering::Relaxed), gs.s2_stale[1].load(Ordering::Relaxed)), (1, 1));
    // the FP-NOBOT gate never reads the skip2 verdict
    assert!(!gate_withhold(&g, &gs, 1000, false));
}

/// the flag; the probe end to end: the verdict published at the arm, withheld while live, the control file's "skip2" flips it (log / live),
/// a key absent keeps the mode; off = no skip2 verdict published, no withheld record, the window record unchanged
#[test]
fn dip37b_skip2_live_probe_and_control() {
    let _g = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let bots = tmp("s2gate.json", &list_of(&[w(0xB0)]));
    for (a, needle) in [(&["--presend-skip2-live", "t2"][..], "needs --presend-skip2-log on"),
        (&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots, "--presend-skip2-live", "t2"][..], "needs --presend-skip2-log on"),
        (&["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots, "--presend-skip2-log", "on", "--presend-skip2-live", "x"][..], "t2 | rearm")] {
        let e = cfg(a).unwrap_err().to_string();
        assert!(e.contains(needle), "{a:?}: {e}");
    }
    assert!(crate::check_flags(&args(&["--presend-fpnb-log", "on", "--presend-fpnb-bots", "/b", "--presend-skip2-log", "on", "--presend-skip2-live", "t2,rearm"])).is_ok());
    let base = ["--presend-fpnb-log", "on", "--presend-fpnb-bots", &bots, "--presend-skip2-log", "on"];
    let run = |extra: &[&str]| {
        let mut x: Vec<&str> = base.to_vec(); x.extend_from_slice(extra);
        let c = cfg(&x).unwrap().unwrap();
        let (mut p, _atx, orx) = PsLive::for_test(c, USER);
        p.ledger_ctl_open();
        { let f = p.fp.as_ref().unwrap(); let mut wk = f.inline.as_ref().unwrap().lock().unwrap(); wk.test_force(Some(2.0)); wk.test_s2_thr(Some(1e9)); }
        let mut tk = Tk::new(0x3B);
        let l = tk.launch.clone();
        let dev = tk.buy(CREATOR, S / 2);
        tx(&mut p, 1000, 3, None, CREATOR, vec![dev], vec![tk.create()], &l);
        let o1 = tk.buy(w(0xA1), S / 5);
        tx(&mut p, 1003, 2, None, w(0xA1), vec![o1], vec![], &l);
        let wh = tk.buy(w(0xEE), 2 * S);
        tx(&mut p, 1005, 50, None, w(0xEE), vec![wh], vec![], &l);
        let g = p.sh.wins.lock().unwrap().iter().find(|s| s.id == 1).unwrap().fpg.clone().expect("the window's gate");
        (p, orx, g, tk, l)
    };
    // live (T2) from the flag: the arm's verdict for 1006 says skip -> withheld; a pass on FP-NOBOT (thr 2.0) does not matter
    let c = cfg(&[&base[..], &["--presend-skip2-live", "t2"][..]].concat()).unwrap().unwrap();
    assert!(c.skip2_live == 1 && c.json()["skip2_live"] == "t2");
    let (mut p, _orx, g, mut tk, l) = run(&["--presend-skip2-live", "t2"]);
    let gs = p.fp.as_ref().unwrap().gs.clone();
    assert_eq!(g.v2.load(Ordering::SeqCst) >> 2, 1006);
    assert_eq!(skip2_withhold_why(&g, &gs, 1006, false), Some(false));
    assert!(!gate_withhold(&g, &gs, 1006, false), "FP-NOBOT itself passes");
    // a new slot re-scores (the window stays armed); the threshold back to "never skip" -> sent
    p.fp.as_ref().unwrap().inline.as_ref().unwrap().lock().unwrap().test_s2_thr(Some(-1e9));
    let o2 = tk.buy(w(0xA2), S / 5);
    tx(&mut p, 1006, 4, None, w(0xA2), vec![o2], vec![], &l);
    assert_eq!(skip2_withhold_why(&g, &gs, 1007, false), None);
    assert!(p.status().contains("SKIP-2 gate(t2) T2/re-arm: withheld 1/0"), "{}", p.status());
    // the control file: "skip2": "log" turns it off, "live" back on (the flag's kinds); no key keeps it
    let ctl = tmp("s2ctl.json", r#"{"whale": "live", "holder": "live", "skip2": "log"}"#);
    let (mut p, orx, g, _tk, _l) = run(&["--presend-skip2-live", "t2", "--presend-live-wh-loss", "2:0.05", "--presend-live-ledger-control", &ctl]);
    let gs = p.fp.as_ref().unwrap().gs.clone();
    assert_eq!(gs.s2_mode.load(Ordering::SeqCst), 0, "the control file at the start: log");
    assert_eq!(skip2_withhold_why(&g, &gs, 1006, false), None);
    let m = recs(&orx).into_iter().find(|r| r["ev"] == "presend_live_ledger_mode").expect("the change logged");
    assert!(m["skip2"] == "off" && m["was"]["skip2"] == "t2", "{m}");
    std::fs::write(&ctl, r#"{"whale": "live", "holder": "live", "skip2": "live"}"#).unwrap();
    p.ledger_ctl_check(true);
    assert_eq!(gs.s2_mode.load(Ordering::SeqCst), 1, "live = the flag's kinds");
    std::fs::write(&ctl, r#"{"whale": "live", "holder": "live"}"#).unwrap();
    p.ledger_ctl_check(true);
    assert_eq!(gs.s2_mode.load(Ordering::SeqCst), 1, "no key: unchanged");
    std::fs::write(&ctl, r#"{"skip2": "maybe"}"#).unwrap();
    p.ledger_ctl_check(true);
    assert_eq!(gs.s2_mode.load(Ordering::SeqCst), 1, "a bad value keeps it");
    // the flag off + "skip2": "live" in the file: both kinds
    let ctl2 = tmp("s2ctl2.json", r#"{"skip2": "live"}"#);
    let (p2, _o, _g, _t, _l) = run(&["--presend-live-wh-loss", "2:0.05", "--presend-live-ledger-control", &ctl2]);
    assert_eq!(p2.fp.as_ref().unwrap().gs.s2_mode.load(Ordering::SeqCst), 3);
    // OFF (no flag, no key): no skip2 verdict is published, nothing withheld, no gate record
    let (mut p, orx, g, _tk, _l) = run(&[]);
    let gs = p.fp.as_ref().unwrap().gs.clone();
    assert_eq!((gs.s2_mode.load(Ordering::SeqCst), g.v2.load(Ordering::SeqCst)), (0, 0));
    assert_eq!(skip2_withhold_why(&g, &gs, 1006, false), None);
    assert!(!p.status().contains("SKIP-2 gate"));
    let end = p.finish(1010, None);
    assert!(end["dip36_fpnb"].get("skip2_gate").is_none());
    assert!(recs(&orx).iter().all(|r| r["ev"] != "presend_live_skip2_withheld" && r.get("s2_withheld").is_none()));
}

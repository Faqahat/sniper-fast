// ===================================================================================================================
// dip46 tests (psprobe46.rs): PROBE TRIES + FILTER A/B. Declared inside pslive.rs (the probe's state is private).
//  * GOLDEN: no dip46 flag = dip43g's records byte for byte (the dip25 digest every build since dip26 pins); probes on = the same decisions,
//    sends, fees and exits once the probe records are taken out
//  * SAFETY: a probe's signed buy carries min_tokens_out = u64::MAX (decoded from the compiled tx), no curve can give that many tokens;
//    a probe landing never touches the fills, positions, fee budget, landing stats; an impossible "probe fill" is never booked
//  * arm-time probe window: a young_age skip -> a probe window (1 try / slot), its landing record with the curve before it and would_fill
//  * A/B: odd triggers bypass an A/B'd arm-time filter (armed, tagged, presend_live_filter_ab), even ones skip; fills tagged; the control key
// ===================================================================================================================
use super::*;
use arbx::dip::TradeEvent;

const USER: Pk = [0x5Au8; 32];
const N: u64 = 461_415_576;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| match o { Out::Rec(v) => Some(v), Out::Line(_) => None }).collect() }
fn arr(slot: u64, sig: [u8; 64], payer: Pk, ok: bool, exec: Option<arbx::feeds::ExecInfo>, t_rx: u64) -> arbx::feeds::Arrival {
    let tx = arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() };
    arbx::feeds::Arrival { feed: 0, slot, t_rx, t_decoded: t_rx, executed: Some(ok), tx, poh: None, raw: arbx::feeds::RawTx::None, exec: exec.map(Arc::new) }
}
fn mint_n(i: u8) -> Pk { let mut m = [0x70u8; 32]; m[0] = i; m }
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
/// a whale buy of ~7% at `slot` (the T2 trigger); w51's numbers
fn whale(p: &mut PsLive, slot: u64, l: &Launch, tag: u8) {
    let mut sg = [0x3Eu8; 64]; sg[0] = tag;
    trade(p, slot, 34, sg, [0xA0 + tag; 32], true, 2_666_666_666, 61_580_021_739_287, 38_692_888_509, 831_935_821_811_615, l);
}
/// a try as the sender registers it (`probe`: a probe's x46)
fn att(w: u64, mint: Pk, sig: [u8; 64], slot: u64, probe: Option<&'static str>) -> Att {
    let x46 = psprobe46::X46 { probe, ab: 0, spend: 400_000_000, fr: 0.0125, sv: 38_692_888_509, st: 831_935_821_811_615, min: 9_524_401_719_354 };
    Att { w, n: 1, mint, sig, tag: pl::PS_TAG | (0xD46 << 8) | sig[0] as u64, path: "helius-ps".into(), client: "AgaveBam".into(), slot, deadline: slot + 1, lim: 0.000041,
        min_out: if probe.is_some() { psprobe46::PROBE_MIN_OUT } else { 9_524_401_719_354 }, p_sign: 0.0000466, sign_pos: (slot - 1, 34, 0), t_send: slot * 1_000_000,
        roles: pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }, tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None, x46, rf: None, rg: None }
}
/// our failed try landed at (slot, idx) with pump's slippage error at the buy (ix 5, 6042)
fn fail_land(p: &mut PsLive, sig: [u8; 64], slot: u64, idx: u64, fee: u64) {
    let err6042 = [8u8, 0, 0, 0, 5, 25, 0, 0, 0, 0x9a, 0x17, 0, 0];
    arbx::feeds::own_fail_note(&sig, Some(&USER[..]), slot, idx, fee, &err6042);
    p.on_arrival(&arr(slot, sig, USER, false, None, slot * 1_000_000 + 30_000_000), slot);
}

// ---- GOLDEN -------------------------------------------------------------------------------------------------------------

/// the dip46 additions taken out of a golden line
fn strip46(l: &str) -> Option<String> {
    let (tag, body) = l.split_at(2);
    if tag != "R " && tag != "F " { return Some(l.to_string()); }
    let mut v: serde_json::Value = serde_json::from_str(body).unwrap();
    let ev = v["ev"].as_str().unwrap_or("");
    if ev.starts_with("presend_live_probe") || ev == "presend_live_dip46" || ev == "presend_live_filter_ab" { return None; }
    if let Some(o) = v.as_object_mut() { for k in ["dip46", "ab46"] { o.remove(k); } }
    if let Some(o) = v.get_mut("cfg").and_then(|c| c.as_object_mut()) { o.remove("dip46"); }
    Some(format!("{tag}{v}"))
}

fn digest(extra46: &[&str], strip: bool) -> Option<(String, usize, usize)> {
    use sha2::Digest;
    let mut h = sha2::Sha256::new();
    let (mut n, mut dropped) = (0usize, 0usize);
    // dip43a's three passes (pass 2: the young_age / QUIET skips the probe windows are made from)
    let passes: [(u8, Vec<&str>, arbx::presend::Params, u64); 3] = [
        (1, vec![], arbx::presend::Params::default(), 7),
        (2, vec!["--presend-live-k", "8", "--presend-live-size-sol", "0.696", "--presend-live-quiet-stop", "5:2", "--presend-live-quiet-skip", "on", "--presend-live-fbots",
            "/unused-in-tests.json", "--presend-live-quiet-fol", "4.0", "--presend-live-quiet-v2-log", "--presend-live-min-age-slots", "2"],
            arbx::presend::Params { whale_pct: 6.0, tp: 0.20, ..Default::default() }, 5),
        (3, vec!["--presend-live-fee-budget-sol", "0.0005"], arbx::presend::Params::default(), 0),
    ];
    for (tag, mut extra, ps, fe) in passes {
        extra.extend_from_slice(extra46);
        let lines = dip26_tests::golden_pass(tag, &extra, ps, fe)?;
        h.update([tag]);
        for l in &lines {
            let l = if strip { match strip46(l) { Some(x) => x, None => { dropped += 1; continue } } } else { l.clone() };
            h.update(l.as_bytes()); h.update(b"\n"); n += 1;
        }
    }
    Some((h.finalize().iter().map(|b| format!("{b:02x}")).collect(), n, dropped))
}

/// no dip46 flag: dip43g's records, lines, chain work and totals byte for byte (the dip25 digest)
#[test]
fn dip46_golden_no_flags_equals_dip43g() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d, n, _)) = digest(&[], false) else { eprintln!("presend_parity.json missing: skipped"); return };
    assert!(n > 3_000, "{n}");
    assert_eq!(d, dip26_tests::DIP25_GOLDEN, "dip46 with no new flag must write dip43g's records ({n} lines)");
}

/// probes on (and the A/B flag with no filter): the same decisions, sends, fees and exits; only the probe records / fields are new
#[test]
fn dip46_golden_probes_change_no_decision() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d0, n0, dropped0)) = digest(&[], true) else { eprintln!("presend_parity.json missing: skipped"); return };
    let (d, n, dropped) = digest(&["--presend-live-probe", "on", "--presend-live-filter-ab", "none"], true).unwrap();
    eprintln!("dip46 golden with probes on: {n} lines kept ({n0} without), {dropped} dip46 records taken out ({dropped0} without)");
    assert_eq!(dropped0, 0, "no flag: no dip46 record");
    assert!(dropped > 3, "the probe windows were made from the skips ({dropped})");
    assert_eq!((d, n), (d0, n0), "probes must not change a decision");
}

// ---- SAFETY ---------------------------------------------------------------------------------------------------------------

/// a probe's signed buy: min_tokens_out = u64::MAX, decoded from the COMPILED tx (the sender's own builder: try_ixs_k46 + att_ixs_fee); no
/// pump curve can give that many tokens for any spend, so the buy fails (6042) and the tx reverts
#[test]
fn dip46_probe_tx_can_never_fill() {
    let key = SigningKey::from_bytes(&[7u8; 32]);
    let user = key.verifying_key().to_bytes();
    let l = launch(1);
    let w = SWin { id: psprobe46::PW0 + 1, mint: l.mint, launch: l.clone(), st_ns: 0, stop_ns: u64::MAX, en_slot: 10, vsol: 40_000_000_000, vtok: 800_000_000_000_000, fr: 0.0125,
        pos: (1, 0, 0), pace: pl::Pace::new(0, 1, 400_000_000), n: 0, done: false, spend: 1_000_000_000, rearm: false, ob6: 0.0, grd: Grd::default(), fpg: None, fab: None, blk: None,
        bd: None, g43: Default::default(), p46: Some("young_age"), rfl: Default::default(), rg: Default::default() };
    let lh = GuardEnc { disc: 15, op: 4, acct: true };
    let bh = [9u8; 32];
    for nofloors in [false, true] {
        let gt = ps43_guard::try_ixs_k46(None, w.id, false, nofloors, &w.g43, 0, user, 461_000_123, bh, None, |d| guard_ix_enc(lh, d), |gix| {
            let (mut ixs, roles) = att_ixs_fee(user, &w, psprobe46::PROBE_MIN_OUT, 110_000, 50_000, gix, None);
            speed16::add_ll(&mut ixs, Some(16_777_216));
            (ixs, roles)
        });
        let bi = gt.roles.buy.unwrap() as usize;
        let buy = &gt.ixs[bi];
        assert_eq!(buy.program, *arbx::snipe::PUMP);
        assert_eq!(buy.data[..8], snipe_build::BUY_EXACT_QUOTE_IN_V3_DISC);
        assert_eq!(u64::from_le_bytes(buy.data[8..16].try_into().unwrap()), w.spend, "the real spend");
        assert_eq!(u64::from_le_bytes(buy.data[16..24].try_into().unwrap()), u64::MAX, "min_tokens_out = u64::MAX");
        // the compiled, signed tx carries the same instruction data
        let raw = build::sign(&build::compile_v0(user, &gt.ixs, bh, &[], &[]).unwrap(), &key);
        assert!(raw.len() <= 1232);
        let needle: Vec<u8> = buy.data.clone();
        assert!(raw.windows(needle.len()).any(|x| x == needle.as_slice()), "the signed tx holds the probe's buy data");
    }
    // no curve state / spend gives u64::MAX tokens (pump's virtual reserves are ~1.07e15; even an absurd 1e19 reserve with a 1e6 SOL spend)
    for &(v, t) in &[(30_000_000_000u64, 1_073_000_000_000_000u64), (1, 1_073_000_000_000_000), (1, u64::MAX / 2), (115_000_000_000, 279_900_000_000_000)] {
        for &spend in &[1u64, 400_000_000, 1_000_000_000, 1_000_000_000_000_000] {
            let out = pl::buy_out(v, t, spend, 0.0);
            assert!(out < t && out < psprobe46::PROBE_MIN_OUT, "{v} {t} {spend} -> {out}");
        }
    }
    // the landing's failure at the buy is pump's slippage error: classified 6042 like a real try's
    assert_eq!(pl::classify("ix5:custom:0x179a", &pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) }), "6042");
}

#[test]
fn dip46_flags_and_refusals() {
    let c = cfg(&[]).unwrap().unwrap();
    assert!(!c.p46.any() && !c.p46.probe && !c.p46.ab_flag && c.p46.ab == 0);
    assert!(c.json().get("dip46").is_none(), "off: dip43g's run_start config");
    let c = cfg(&["--presend-live-probe", "on"]).unwrap().unwrap();
    assert!(c.p46.probe && c.p46.rate == 5 && c.p46.kinds == psprobe46::KINDS_ALL && c.p46.max_wins == 8);
    assert!(c.json()["dip46"]["probe"]["max_per_sec"] == 5);
    let c = cfg(&["--presend-live-probe", "on", "--presend-live-probe-kinds", "young_age,botdepth,fpnb", "--presend-live-probe-max-per-sec", "3"]).unwrap().unwrap();
    assert_eq!(psprobe46::kinds_str(c.p46.kinds), "young_age,fpnb,botdepth");
    for bad in [vec!["--presend-live-probe-max-per-sec", "3"], vec!["--presend-live-probe", "yes"], vec!["--presend-live-probe", "on", "--presend-live-probe-kinds", "nope"],
                vec!["--presend-live-probe", "on", "--presend-live-probe-max-per-sec", "0"], vec!["--presend-live-probe", "on", "--presend-live-probe-max-per-sec", "500"],
                vec!["--presend-live-filter-ab", "young_age"], vec!["--presend-live-filter-ab", "holder_floors"], vec!["--presend-live-filter-ab", "nope"],
                vec!["--presend-live-filter-ab", "botdepth"]] {
        assert!(cfg(&bad).is_err(), "{bad:?} must be refused");
    }
    // every flag needs --presend-live
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-live-probe", "on"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1).is_err());
    // the A/B of a filter that is on
    let c = cfg(&["--presend-live-min-age-slots", "2", "--presend-live-filter-ab", "young_age,create_slot"]).unwrap().unwrap();
    assert_eq!(psprobe46::ab_names(c.p46.ab), vec!["young_age", "create_slot"]);
    // kinds
    assert_eq!(psprobe46::kind_of("young_age"), Some("young_age"));
    assert_eq!(psprobe46::kind_of("fpnb_withheld_stale"), Some("fpnb"));
    assert_eq!(psprobe46::kind_of("s1_nd"), Some("s1"));
    assert_eq!(psprobe46::kind_of("blocked_position"), None);
    assert_eq!(psprobe46::kind_of("stopped"), None);
    assert_eq!(psprobe46::kinds_parse("all").unwrap() & psprobe46::kind_bit("breaker"), 0, "the breaker is opt-in");
    // the control keys
    let (mut ab, p) = psprobe46::ctl46_parse(br#"{"ab46": {"young_age": "ab", "botdepth": "live"}, "probe46": "off", "whale": "live"}"#).unwrap();
    ab.sort();
    assert_eq!(ab, vec![("botdepth".to_string(), false), ("young_age".to_string(), true)]);
    assert_eq!(p, Some(false));
    assert!(psprobe46::ctl46_parse(br#"{"ab46": {"young_age": "log"}}"#).is_err());
    assert!(psprobe46::ctl46_parse(br#"{"ab46": {"nope": "ab"}}"#).is_err());
    assert_eq!(psprobe46::ctl46_parse(br#"{"whale": "live"}"#).unwrap(), (vec![], None), "no dip46 key: nothing");
    // the dip43 / ledger parsers ignore the dip46 keys (one control file for all)
    let b = br#"{"whale": "live", "young_age": "live", "ab46": {"young_age": "ab"}, "probe46": "on"}"#;
    assert!(ps43::ctl43_parse(b).is_ok() && pshl::ctl_parse(b).is_ok());
}

// ---- the arm-time probe window ---------------------------------------------------------------------------------------------

/// a young_age skip with probes on: a probe window (its own id, one try per slot, never armed); its probe's landing is recorded with the
/// curve before it and would_fill; the real tries' books (fees, budget, results, positions) never see it
#[test]
fn dip46_probe_window_and_landing() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let c = cfg(&["--presend-live-min-age-slots", "2", "--presend-live-probe", "on"]).unwrap().unwrap();
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    let l = launch(1);
    create(&mut p, N - 1, &l);
    whale(&mut p, N, &l, 1);
    assert!(p.armed.is_empty());
    assert_eq!(p.st.skips.get("young_age").copied(), Some(1));
    let pw = { let g = p.sh.wins.lock().unwrap(); g.iter().find(|w| w.p46.is_some()).map(|w| (w.id, w.p46, w.mint, w.pace.iv)) };
    let (pid, why, m, _) = pw.expect("a probe window");
    assert!(pid > psprobe46::PW0 && why == Some("young_age") && m == l.mint);
    let r = recs(&orx);
    assert!(r.iter().any(|x| x["ev"] == "presend_live_probe_arm" && x["filter"] == "young_age" && x["w"] == pid), "{r:?}");
    // a trade before our probe (the curve the probe's landing is judged on), then the probe lands at (N + 1, 50) and fails at the buy
    trade(&mut p, N + 1, 20, [0x21u8; 64], [0x99u8; 32], false, 1_000_000_000, 30_000_000_000_000, 36_000_000_000, 894_000_000_000_000, &l);
    let sig = [0x46u8; 64];
    atx.send(att(pid, l.mint, sig, N + 1, Some("young_age"))).unwrap();
    p.drain_atts();
    assert!(p.atts.is_empty(), "a probe is never in the real tries' book");
    let fees0 = (p.st.fees, p.fee_24h);
    fail_land(&mut p, sig, N + 1, 50, 10_500);
    assert_eq!((p.st.fees, p.fee_24h), fees0, "probe fees never in the failed-fee totals / budget");
    assert_eq!(p.p46.fees, 10_500);
    p.tick(N + 4, None);
    let r = recs(&orx);
    let land = r.iter().find(|x| x["ev"] == "presend_live_probe_land").unwrap_or_else(|| panic!("{r:?}"));
    assert_eq!(land["res"], "6042");
    assert_eq!(land["slot"], N + 1);
    assert_eq!(land["idx"], 50);
    assert_eq!(land["pre"]["vtok"], 894_000_000_000_000u64, "the trade just before our landing");
    // price there 36e9 / 8.94e14 = 4.03e-5 <= limit (min_out at the limit state): would have filled
    let tokens = pl::buy_out(36_000_000_000, 894_000_000_000_000, 400_000_000, 0.0125);
    assert_eq!(land["would_tokens"], tokens);
    assert_eq!(land["would_fill"], tokens >= 9_524_401_719_354);
    assert!(!r.iter().any(|x| x["ev"] == "presend_attempt_land"), "no real landing record");
    assert!(p.st.landed.is_empty() && p.st.per_path.is_empty() && p.pos.is_empty());
    // an impossible "fill" of a probe signature: never a position of the pre-send book
    let sig2 = [0x47u8; 64];
    atx.send(att(pid, l.mint, sig2, N + 4, Some("young_age"))).unwrap();
    p.drain_atts();
    trade(&mut p, N + 4, 60, sig2, USER, true, 395_061_727, 9_803_077_983_112, 36_215_421_019, 888_847_874_680_162, &l);
    assert_eq!(p.p46.impossible, 1);
    assert_eq!(p.st.fills, 0, "never a fill");
    // the tokens (impossible by construction) would be sold at once by the orphan path, never booked as a pre-send fill
    assert_eq!(p.pos.get(&l.mint).map(|x| x.via), Some("rpc_read"));
    // the window ends at its end slot (or earlier: tick N + 4 may be past it); the run's totals
    p.tick(N + 400, None);
    assert!(p.p46.wins.is_empty() && !p.sh.wins.lock().unwrap().iter().any(|w| w.p46.is_some()));
    let mut r2 = r.clone(); r2.extend(recs(&orx));
    assert!(r2.iter().any(|x| x["ev"] == "presend_live_probe_filled"), "{r2:?}");
    assert!(r2.iter().any(|x| x["ev"] == "presend_live_probe_end"), "{r2:?}");
    let f = p.finish46().unwrap();
    assert_eq!(f["probe_fees"], 10_500);
    assert_eq!(f["by_kind"]["young_age"]["landed"], 1);
    assert!(p.status46().contains("PROBE: on"));
}

/// a probe never seen by its deadline + 3 slots: "unseen", no fee
#[test]
fn dip46_probe_unseen() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    let c = cfg(&["--presend-live-probe", "on"]).unwrap().unwrap();
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    let l = launch(2);
    atx.send(att(5, l.mint, [0x48u8; 64], N, Some("botdepth_withheld"))).unwrap();
    p.tick(N, None);
    p.tick(N + 5, None);
    let r = recs(&orx);
    let land = r.iter().find(|x| x["ev"] == "presend_live_probe_land").unwrap();
    assert_eq!((land["res"].as_str(), land["filter"].as_str()), (Some("unseen"), Some("botdepth_withheld")));
    assert_eq!(p.p46.fees, 0);
    assert_eq!(p.p46.by_kind["botdepth"].unseen, 1);
    assert!(p.st.landed.is_empty());
}

/// the sender's limiter: one probe per window per slot, the global rate, the kinds, the switch
#[test]
fn dip46_send_limiter() {
    let c = cfg(&["--presend-live-probe", "on", "--presend-live-probe-kinds", "botdepth", "--presend-live-probe-max-per-sec", "2"]).unwrap().unwrap();
    let sh = psprobe46::Sh46::default();
    let mut s = psprobe46::Send46::new(&c.p46);
    assert_eq!(s.want(&sh, "botdepth_withheld", 1, 10, 1_000), None, "probes off in Sh46 until the start");
    sh.probe.store(true, Ordering::SeqCst);
    assert_eq!(s.want(&sh, "fpnb_withheld", 1, 10, 1_000), None, "kind not listed");
    assert_eq!(s.want(&sh, "botdepth_withheld", 1, 10, 1_000), Some("botdepth_withheld"));
    assert_eq!(s.want(&sh, "botdepth_withheld", 1, 10, 2_000), None, "one per window per slot");
    assert_eq!(s.want(&sh, "botdepth_withheld", 1, 11, 3_000), None, "the global rate (burst 1, 2/s)");
    assert_eq!(s.want(&sh, "botdepth_withheld", 1, 11, 600_000_000), Some("botdepth_withheld"));
    assert_eq!(sh.refused.lock().unwrap().get("probe_rate").copied(), Some(1));
    // the A/B parity: odd windows bypass a filter only while it is A/B'd
    assert!(!psprobe46::Send46::bypass(&sh, psprobe46::AB_BD, 7));
    sh.ab.store(psprobe46::AB_BD, Ordering::SeqCst);
    assert!(psprobe46::Send46::bypass(&sh, psprobe46::AB_BD, 7) && !psprobe46::Send46::bypass(&sh, psprobe46::AB_BD, 8));
    assert!(!psprobe46::Send46::bypass(&sh, psprobe46::AB_FPNB, 7));
}

// ---- the A/B ------------------------------------------------------------------------------------------------------------------

/// young_age A/B'd: the 1st (odd) young trigger arms (bypass, tagged), the 2nd (even) is skipped as today; records for both; the fill on the
/// bypass window carries ab46.would = [young_age]; the control key turns the A/B off hot
#[test]
fn dip46_filter_ab_young_age() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let dir = std::env::temp_dir().join(format!("dip46_ab_{}", std::process::id()));
    let _ = std::fs::create_dir_all(&dir);
    let ctl = dir.join("ctl.json");
    std::fs::write(&ctl, r#"{"whale": "live"}"#).unwrap();
    let ctl_s = ctl.display().to_string();
    let c = cfg(&["--presend-live-min-age-slots", "2", "--presend-live-filter-ab", "young_age", "--presend-live-wh-loss", "2:0.3", "--presend-live-ledger-control", &ctl_s]).unwrap().unwrap();
    let (mut p, atx, orx) = PsLive::for_test(c, USER);
    let (l1, l2) = (launch(3), launch(4));
    create(&mut p, N - 1, &l1);
    whale(&mut p, N, &l1, 3);
    assert_eq!(p.armed.get(&l1.mint), Some(&1), "odd trigger: young_age bypassed, armed");
    create(&mut p, N - 1, &l2);
    whale(&mut p, N, &l2, 4);
    assert!(!p.armed.contains_key(&l2.mint), "even trigger: skipped as today");
    assert_eq!(p.st.skips.get("young_age").copied(), Some(1));
    assert!(p.d43.g.young_age, "the mode is restored after the trigger");
    let r = recs(&orx);
    let ab: Vec<&serde_json::Value> = r.iter().filter(|x| x["ev"] == "presend_live_filter_ab").collect();
    assert_eq!(ab.len(), 2, "{ab:?}");
    assert!(ab[0]["arm"] == "bypass" && ab[0]["filter"] == "young_age" && ab[0]["w"] == 1 && ab[0]["armed"] == true);
    assert!(ab[1]["arm"] == "live" && ab[1]["would_block"] == true && ab[1]["w"].is_null());
    let arm = r.iter().find(|x| x["ev"] == "presend_live_arm").unwrap();
    assert_eq!(arm["ab46"]["arms"]["young_age"], "bypass");
    assert_eq!(arm["ab46"]["would"], serde_json::json!(["young_age"]));
    let skip = r.iter().find(|x| x["ev"] == "presend_live_skip").unwrap();
    assert_eq!(skip["ab46"]["arms"]["young_age"], "live");
    // the bypass window fills: its fill record carries the tag
    let sig = [0x49u8; 64];
    atx.send(att(1, l1.mint, sig, N + 1, None)).unwrap();
    p.drain_atts();
    trade(&mut p, N + 1, 192, sig, USER, true, 395_061_727, 9_803_077_983_112, 36_215_421_019, 888_847_874_680_162, &l1);
    let r = recs(&orx);
    let fill = r.iter().find(|x| x["ev"] == "presend_live_fill").unwrap_or_else(|| panic!("{r:?}"));
    assert_eq!(fill["ab46"]["would"], serde_json::json!(["young_age"]));
    assert_eq!(fill["ab46"]["arms"]["young_age"], "bypass");
    // the control key: young_age back to its own mode (no A/B)
    std::thread::sleep(Duration::from_millis(20));
    std::fs::write(&ctl, r#"{"whale": "live", "ab46": {"young_age": "live"}}"#).unwrap();
    p.p46_ctl_check(true);
    assert_eq!(p.sh.p46.ab.load(Ordering::SeqCst), 0);
    let r = recs(&orx);
    assert!(r.iter().any(|x| x["ev"] == "presend_live_ledger_mode" && x["dip46"]["ab46"] == serde_json::json!([])), "{r:?}");
    let _ = std::fs::remove_dir_all(&dir);
}

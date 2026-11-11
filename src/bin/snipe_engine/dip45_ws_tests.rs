// ===================================================================================================================
// dip45 WHALE-SOLD tracker tests (ps45_wsold.rs; LOG ONLY). Declared inside pslive.rs.
//  * GOLDEN: no flag = the dip25 digest byte for byte (dip45_golden_no_flags_equals_dip43g covers it too); the tracker on = the same
//    digest once its records / fields are taken out (no decision, send, fee or exit change)
//  * the fraction math and the 25 / 50 / 100 % crossings (in order, late arrivals, net of buys back)
//  * the tracker on records: arm -> track, sells (pre-exec sighting, backfill from the ring), fill / would-fill annotations, the close
// ===================================================================================================================
use super::*;
use super::ps45_wsold::*;
use arbx::dip::TradeEvent;

const USER: Pk = [0x5Au8; 32];

// ---- GOLDEN -------------------------------------------------------------------------------------------------------------

fn strip_ws(l: &str) -> Option<String> {
    let (tag, body) = l.split_at(2);
    if tag != "R " && tag != "F " { return Some(l.to_string()); }
    let mut v: serde_json::Value = serde_json::from_str(body).unwrap();
    if v["ev"] == "presend_live_whale_sold" { return None; }
    if let Some(o) = v.as_object_mut() { o.remove("whale_sold"); }
    if let Some(o) = v.get_mut("cfg").and_then(|c| c.as_object_mut()) { o.remove("whale_sold"); }
    Some(format!("{tag}{v}"))
}

fn digest(extra: &[&str], strip: bool) -> Option<(String, usize, usize, Vec<serde_json::Value>)> {
    use sha2::Digest;
    let mut h = sha2::Sha256::new();
    let (mut n, mut dropped, mut ws) = (0usize, 0usize, Vec::new());
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
            if l.starts_with("R ") && l.contains("\"presend_live_whale_sold\"") { ws.push(serde_json::from_str(&l[2..]).unwrap()); }
            let l = if strip { match strip_ws(l) { Some(x) => x, None => { dropped += 1; continue } } } else { l.clone() };
            h.update(l.as_bytes()); h.update(b"\n"); n += 1;
        }
    }
    Some((h.finalize().iter().map(|b| format!("{b:02x}")).collect(), n, dropped, ws))
}

/// the tracker on: the same decisions, sends, fees and exits (its records / fields taken out = the no-flag digest); no flag = dip25 digest
#[test]
fn dip45_ws_golden_changes_no_decision() {
    let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
    arbx::feeds::own_fail_watch(USER);
    let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
    let _g = rt.enter();
    let Some((d00, _, _, w0)) = digest(&[], false) else { eprintln!("presend_parity.json missing: skipped"); return };
    assert_eq!(d00, dip26_tests::DIP25_GOLDEN, "no flag: the dip45 records byte for byte");
    assert!(w0.is_empty());
    let (d0, n0, dropped0, _) = digest(&[], true).unwrap();
    assert_eq!(dropped0, 0);
    let (d, n, dropped, ws) = digest(&["--presend-live-whale-sold-log", "on"], true).unwrap();
    let st = |s: &str| ws.iter().filter(|r| r["stage"] == s).count();
    eprintln!("dip45 golden with the whale-sold log: {n} lines kept ({n0} without), {dropped} records taken out: config {} arm {} sell {} fill {} shadow_fill {} close {}",
        st("config"), st("arm"), st("sell"), st("fill"), st("shadow_fill"), st("close"));
    assert_eq!(st("config"), 3);
    assert!(st("arm") > 10 && st("close") > 5 && st("sell") > 0 && st("fill") > 3, "the tracker saw our arms, the whales' sells and our fills");
    // every live T2 arm opened a track (src live) and the shadow's arms joined or opened tracks
    assert!(ws.iter().any(|r| r["stage"] == "arm" && r["src"] == "live") && ws.iter().any(|r| r["stage"] == "arm" && r["src"] == "shadow"));
    // a sell's cumulative fraction never goes down within a track
    let mut last: FxHashMap<u64, f64> = FxHashMap::default();
    for r in ws.iter().filter(|r| r["stage"] == "sell" || r["stage"] == "config") {
        // track ids start again in each golden pass (its config record)
        if r["stage"] == "config" { last.clear(); continue; }
        let (t, c) = (r["track"].as_u64().unwrap(), r["cum_frac"].as_f64().unwrap());
        assert!(c >= *last.get(&t).unwrap_or(&0.0) - 1e-12, "{r}");
        last.insert(t, c);
    }
    assert_eq!((d, n), (d0, n0), "the whale-sold log must not change a decision");
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
fn dip45_ws_flags() {
    let c = cfg(&[]).unwrap().unwrap();
    assert!(!c.wsold && c.json().get("whale_sold").is_none());
    let c = cfg(&["--presend-live-whale-sold-log", "on"]).unwrap().unwrap();
    assert!(c.wsold && c.json()["whale_sold"]["mode"] == "log");
    assert!(!cfg(&["--presend-live-whale-sold-log", "off"]).unwrap().unwrap().wsold);
    assert!(cfg(&["--presend-live-whale-sold-log", "maybe"]).is_err());
    assert!(cfg(&["--presend-live-whale-sold-log"]).is_err(), "needs a value");
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-shadow", "--presend-live-whale-sold-log", "on"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1_000_000_000).is_err(), "needs --presend-live");
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-shadow", "--presend-live", "--presend-live-dry", "--presend-live-routes", "default=helius-ps", "--presend-live-whale-sold-log",
        "on", "--presend-live-fleet-log", "on"].iter().map(|s| s.to_string()).collect();
    let c = Cfg::from_argv(&a, &arbx::presend::Params::default(), false, 1_000_000_000).unwrap().unwrap();
    assert!(c.dry && c.wsold && c.fleet.is_some());
}

// ---- the math -----------------------------------------------------------------------------------------------------------

fn wt(user: Pk, buy: bool, tok: u64, s: u64, i: u32) -> WTrade { WTrade { user, buy, tok, pos: (s, i, 0), t: s * 400_000_000, feed: 0, pre_t: None, backfill: false } }

#[test]
fn dip45_ws_frac_math() {
    assert_eq!(frac(0, 0), 0.0);
    assert_eq!(frac(250, 1000), 0.25);
    assert!(!at_least(1, 0, 0), "no bag: never");
    assert!(at_least(250, 1000, 25) && !at_least(249, 1000, 25));
    assert!(at_least(500, 1000, 50) && !at_least(499, 1000, 50));
    assert!(at_least(1000, 1000, 100) && at_least(1200, 1000, 100) && !at_least(999, 1000, 100));
    // exact with big numbers (no float rounding): 3 * 333_333_333_333_333 vs 999_999_999_999_999 at 100 %
    assert!(at_least(999_999_999_999_999, 999_999_999_999_999, 100) && !at_least(999_999_999_999_998, 999_999_999_999_999, 100));
    assert!(at_least(u64::MAX / 2 + 1, u64::MAX, 50));
    assert_eq!(net_sold(600, 200), 400);
    assert_eq!(net_sold(100, 300), 0);
}

#[test]
fn dip45_ws_crossings() {
    let (m, wh, o) = ([1u8; 32], [2u8; 32], [3u8; 32]);
    let mut t = Track::new(1, m, wh, 1_000, (100, 5, 0), 200);
    assert!(!t.add(wt(wh, false, 50, 100, 5)), "the trigger position itself");
    assert!(!t.add(wt(wh, false, 50, 100, 4)), "before the trigger");
    assert!(t.add(wt(wh, false, 200, 101, 3)));
    assert_eq!((t.first_sell, t.x25), (Some((101, 3, 0)), None), "20 %: a first sell, no crossing");
    assert!(t.add(wt(wh, false, 50, 102, 0)));
    assert_eq!(t.x25, Some((102, 0, 0)), "200 + 50 = 25 % exactly");
    assert!(t.add(wt(wh, true, 300, 103, 0)));
    assert!(t.add(wt(wh, false, 250, 104, 9)));
    assert_eq!(t.x50, Some((104, 9, 0)), "cum 500 = 50 %");
    assert_eq!(t.n50, None, "net 500 - 300 = 200: not 50 % net");
    assert!(!t.add(wt(wh, false, 250, 104, 9)), "a duplicate");
    assert!(t.add(wt(wh, false, 500, 106, 1)));
    assert_eq!((t.x100, t.n50), (Some((106, 1, 0)), Some((106, 1, 0))), "cum 1000 = 100 %, net 700");
    assert_eq!((t.n_sells, t.n_buys, t.sold, t.bought), (4, 1, 1000, 300));
    // before a position: strict vs inclusive
    assert_eq!(t.at((104, 9, 0), false), At { sold: 250, bought: 300, n_sells: 2, last_sell: Some(102) });
    assert_eq!(t.at((104, 9, 0), true).sold, 500);
    let a = t.ann((104, 9, 0), false);
    assert_eq!((a["sold25"].as_bool(), a["sold50"].as_bool(), a["net50"].as_bool(), a["cum_frac"].as_f64()), (Some(true), Some(false), Some(false), Some(0.25)));
    let a = t.ann((105, 0, 0), false);
    assert_eq!((a["sold50"].as_bool(), a["net_frac"].as_f64(), a["dslot_trig"].as_u64()), (Some(true), Some(0.2), Some(5)));
    // a late arrival (earlier position) recomputes the crossings in chain order
    let mut t2 = Track::new(2, m, wh, 1_000, (100, 0, 0), 200);
    t2.add(wt(wh, false, 300, 105, 0));
    assert_eq!(t2.x25, Some((105, 0, 0)));
    t2.add(wt(wh, false, 300, 103, 0));
    assert_eq!((t2.first_sell, t2.x25, t2.x50), (Some((103, 0, 0)), Some((103, 0, 0)), Some((105, 0, 0))));
    let _ = o;
}

// ---- the tracker on records -----------------------------------------------------------------------------------------------

fn arr(slot: u64, sig: u64, signer: Pk, executed: Option<bool>, t: u64, x: Option<arbx::feeds::ExecInfo>) -> arbx::feeds::Arrival {
    let mut s = [0u8; 64]; s[..8].copy_from_slice(&sig.to_be_bytes());
    arbx::feeds::Arrival { feed: if executed.is_some() { 0 } else { 2 }, slot, t_rx: t, t_decoded: t, executed, tx: arbx::tx::Tx { sig: s, keys: vec![signer], ..Default::default() },
        poh: None, raw: arbx::feeds::RawTx::None, exec: x.map(Arc::new) }
}
fn ex(idx: u64, mint: Pk, user: Pk, buy: bool, tok: u64) -> arbx::feeds::ExecInfo {
    arbx::feeds::ExecInfo { index: idx, fee: 5_000, ok: true, trades: vec![TradeEvent { mint, sol: 1, tok, buy, user, vsol: 30_000_000_000, vtok: 1, fbps: 95, cbps: 30 }],
        creates: Vec::new(), mayhem: false }
}

#[test]
fn dip45_ws_flow() {
    let (otx, orx) = crossbeam_channel::unbounded::<Out>();
    let mut w = WSold::start(&otx);
    let (m, wh) = ([7u8; 32], [8u8; 32]);
    let feed = |w: &mut WSold, slot: u64, idx: u64, sig: u64, user: Pk, buy: bool, tok: u64| {
        let x = ex(idx, m, user, buy, tok);
        let a = arr(slot, sig, user, Some(true), slot * 400_000_000 + idx, Some(x.clone()));
        w.exec(&a, &x, slot, None);
    };
    // the trigger buy (slot 100 idx 5), then a whale sell BEFORE the arm record (the shadow's record can be late): backfilled
    feed(&mut w, 100, 5, 1, wh, true, 1_000);
    feed(&mut w, 101, 2, 2, wh, false, 100);
    w.on_shadow(&serde_json::json!({"ev": "presend_arm", "w": 3, "mint": b58(&m), "wallet": b58(&wh), "bal": 1_000, "slot": 100, "idx": 5, "j": 0, "en0": 110.4 * pl::SMS}));
    // our live T2 arm on the same trigger: the same track
    w.on_rec(&serde_json::json!({"ev": "presend_live_arm", "w": 9, "dry": true, "en_slot": 111, "trig": {"mint": b58(&m), "wallet": b58(&wh), "bal": 1_000, "slot": 100, "idx": 5, "j": 0}}));
    // a re-arm arm (no trig): not tracked
    w.on_rec(&serde_json::json!({"ev": "presend_live_arm", "w": 10, "kind": "rearm", "mint": b58(&m), "dump": {"slot": 101, "idx": 2}}));
    assert_eq!((w.tracks.len(), w.st.arms_untracked), (1, 1));
    // the whale's next sell seen first on a pre-exec feed (another wallet's pre-exec tx is ignored)
    w.arrival(&arr(102, 3, wh, None, 102 * 400_000_000 - 5_000_000, None));
    w.arrival(&arr(102, 4, [9u8; 32], None, 102 * 400_000_000, None));
    feed(&mut w, 102, 7, 3, wh, false, 300);
    // our fill after it (slot 102 idx 9): 40 % sold before it; a would-fill at the whale's sell (inclusive)
    w.on_rec(&serde_json::json!({"ev": "presend_live_fill", "w": 9, "slot": 102, "idx": 9, "mint": b58(&m)}));
    w.on_shadow(&serde_json::json!({"ev": "presend_fill", "w": 3, "mint": b58(&m), "row": "c", "x": {"slot": 102, "idx": 7}}));
    // a fill of an untracked window
    w.on_rec(&serde_json::json!({"ev": "presend_live_fill", "w": 10, "kind": "rearm", "slot": 103, "idx": 1}));
    // another wallet's sell: nothing; the whale sells the rest
    feed(&mut w, 103, 0, 5, [4u8; 32], false, 999);
    feed(&mut w, 104, 3, 6, wh, false, 600);
    // the end: window end 111 + 30 (the fill at 102 + 30 is earlier) -> open at 141, closed at 142
    feed(&mut w, 141, 0, 7, [4u8; 32], true, 1);
    assert_eq!(w.tracks.len(), 1);
    feed(&mut w, 142, 0, 8, [4u8; 32], true, 1);
    assert!(w.tracks.is_empty());
    let recs: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    let stg: Vec<&str> = recs.iter().map(|r| r["stage"].as_str().unwrap()).collect();
    assert_eq!(stg, ["config", "sell", "arm", "arm", "sell", "fill", "shadow_fill", "fill", "sell", "close"]);
    let s1 = &recs[1];
    assert_eq!((s1["backfill"].as_bool(), s1["pre"].is_null(), s1["cum_frac"].as_f64(), s1["dslot"].as_u64()), (Some(true), true, Some(0.1), Some(1)));
    assert_eq!((recs[2]["src"].as_str(), recs[2]["end_slot"].as_u64(), recs[3]["src"].as_str()), (Some("shadow"), Some(141), Some("live")));
    assert_eq!(recs[2]["track"], recs[3]["track"]);
    assert_eq!(recs[3]["end_slot"].as_u64(), Some(141));
    let s2 = &recs[4];
    assert!((s2["pre_ms"].as_f64().unwrap() - 5.0).abs() < 0.01);
    assert_eq!((s2["pre"].as_bool(), Some(5.0), s2["cum_sold_tok"].as_u64(), s2["cum_frac"].as_f64(), s2["sold_tok"].as_u64()), (Some(true), Some(5.0), Some(400), Some(0.4), Some(300)));
    assert_eq!(s2["ws"].as_array().unwrap().len(), 2);
    let f = &recs[5];
    assert_eq!((f["cum_frac"].as_f64(), f["sold25"].as_bool(), f["sold50"].as_bool(), f["idx"].as_u64(), f["w"].as_u64()), (Some(0.4), Some(true), Some(false), Some(9), Some(9)));
    let sf = &recs[6];
    assert_eq!((sf["kind"].as_str(), sf["cum_frac"].as_f64(), sf["n_sells_before"].as_u64()), (Some("shadow:c"), Some(0.4), Some(2)));
    assert!(recs[7]["track"].is_null());
    assert_eq!(recs[8]["cum_frac"].as_f64(), Some(1.0));
    let c = &recs[9];
    assert_eq!((c["n_sells"].as_u64(), c["max_cum_frac"].as_f64(), c["first_sell_dslot"].as_u64(), c["dslot25"].as_u64(), c["dslot50"].as_u64(), c["dslot100"].as_u64()),
        (Some(3), Some(1.0), Some(1), Some(2), Some(4), Some(4)));
    assert_eq!(c["fills"].as_array().unwrap().len(), 2);
    assert_eq!(c["fills"][0]["cum_frac"].as_f64(), Some(0.4));
    let fin = w.finish();
    assert_eq!((fin["sells"].as_u64(), fin["sells_pre_exec"].as_u64(), fin["sells_backfill"].as_u64(), fin["crossed50"].as_u64(), fin["fills"]["n"].as_u64(), fin["fills"]["untracked"].as_u64()),
        (Some(3), Some(1), Some(1), Some(1), Some(1), Some(1)));
    assert!(w.status().contains("WHALE SOLD LOG: tracks 1 (open 0) sells 3"));
}

// ===================================================================================================================
// dip34 LOG-ONLY annotation tests (11-04 PKT; pslog34.rs): --presend-live-seen-log [H], --presend-live-eqgrp-log, --presend-live-q4-log,
// and ann.cr_hold / cr_big (coordinator 11-04). Flags off: no book, no field (dip33's records); flags on: the fields, never a decision.
// ===================================================================================================================
use super::*;
use super::pslog34::*;

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
fn pct(p: f64) -> i64 { (p / 100.0 * SUP as f64).round() as i64 }

#[test]
fn dip34_log_flags() {
    let c = cfg(&["--presend-live-seen-log", "3", "--presend-live-eqgrp-log", "--presend-live-q4-log"]).unwrap().unwrap();
    assert!(c.seen_h == 3.0 && c.eqgrp_log && c.q4_log);
    let j = c.json();
    assert!(j["seen_log"] == 3.0 && j["eqgrp_log"] == true && j["q4_log"] == true, "{j}");
    // no value (last, or the next flag): 3 h
    assert_eq!(cfg(&["--presend-live-seen-log"]).unwrap().unwrap().seen_h, 3.0);
    let c = cfg(&["--presend-live-seen-log", "--presend-live-eqgrp-log"]).unwrap().unwrap();
    assert!(c.seen_h == 3.0 && c.eqgrp_log, "the next flag is not its value");
    assert_eq!(cfg(&["--presend-live-seen-log", "0.5"]).unwrap().unwrap().seen_h, 0.5);
    for bad in ["0", "49", "-1", "x", "NaN"] {
        let e = cfg(&["--presend-live-seen-log", bad]).unwrap_err().to_string();
        assert!(e.contains("--presend-live-seen-log"), "{bad}: {e}");
    }
    // off: dip33's start record
    let c0 = cfg(&[]).unwrap().unwrap();
    assert!(c0.seen_h == 0.0 && !c0.eqgrp_log && !c0.q4_log);
    assert!(["seen_log", "eqgrp_log", "q4_log"].iter().all(|k| c0.json().get(*k).is_none()));
    let l = L34::new(&c0);
    assert!(l.sb.is_none() && l.q4.is_none(), "off: no book");
    // the start-up check knows them; without --presend-live they are refused
    assert!(crate::check_flags(&base(&["--presend-live-seen-log", "3", "--presend-live-eqgrp-log", "--presend-live-q4-log"])).is_ok());
    for f in ["--presend-live-seen-log", "--presend-live-eqgrp-log", "--presend-live-q4-log"] {
        let e = Cfg::from_argv(&v(&["snipe_engine", "--dip", "--presend-shadow", f]), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap_err().to_string();
        assert!(e.contains("needs --presend-live"), "{f}: {e}");
    }
}

#[test]
fn dip34_seen_book() {
    let mut b = SeenBook::new(3.0);
    let h = 3 * 3_600_000_000_000u64;
    let t0 = 1_793_720_000_000_000_000u64;
    let (w, m1, m2) = ([1u8; 32], [7u8; 32], [8u8; 32]);
    let j = b.seen(&w, t0);
    assert!(j["hit"] == false && j["n"] == 0 && b.hits == 0);
    b.note(w, t0, "cr_loss", m1);
    b.note(w, t0 + 60_000_000_000, "quiet3_a", m2);
    let j = b.seen(&w, t0 + 120_000_000_000);
    assert!(j["hit"] == true && j["n"] == 2 && j["why"] == serde_json::json!(["cr_loss", "quiet3_a"]), "{j}");
    assert!(j["mints"][0] == b58(&m1)[..8] && j["min_ago"] == serde_json::json!([2.0, 1.0]), "{j}");
    // only skips up to the record's time
    assert_eq!(b.seen(&w, t0 + 30_000_000_000)["n"], 1);
    // H hours later the first is gone, then both (and the whale)
    assert_eq!(b.seen(&w, t0 + h + 1)["n"], 1);
    assert_eq!(b.seen(&w, t0 + h + 60_000_000_001)["hit"], false);
    assert_eq!(b.len(), 0);
    // another whale: nothing; at most SEEN_MAX_PER per whale
    for i in 0..40u64 { b.note(w, t0 + i, "cr_loss", m1); }
    assert_eq!(b.seen(&w, t0 + 100)["n"], SEEN_MAX_PER);
    assert_eq!(b.seen(&[2u8; 32], t0 + 100)["hit"], false);
}

#[test]
fn dip34_seen_note_reasons_only() {
    let c = cfg(&["--presend-live-seen-log", "3"]).unwrap().unwrap();
    let (mut p, _atx, _orx) = PsLive::for_test(c, USER);
    let (w, m) = ([1u8; 32], [7u8; 32]);
    for why in ["quiet", "lone_whale", "breaker", "cr_unfollowed", "no_launch_accounts", "rearm_no_holder", "rearm_r5"] { p.seen_note(why, w, 100, m); }
    assert_eq!(p.l34.sb.as_ref().unwrap().notes, 0, "other skips: never noted");
    for why in ["cr_loss", "quiet3_a", "rearm_cr_loss"] { p.seen_note(why, w, 100, m); }
    assert_eq!(p.l34.sb.as_ref().unwrap().notes, 3);
    // off: nothing
    let (mut q, _a, _o) = PsLive::for_test(cfg(&[]).unwrap().unwrap(), USER);
    q.seen_note("cr_loss", w, 100, m);
    assert!(q.l34.sb.is_none() && q.l34_json().is_none());
}

#[test]
fn dip34_eq_groups() {
    let k = |n: u8| [n; 32];
    // r50 79VUfAUd: three x 9.0% (amounts a little apart), a 4% and two x 3.0%
    let h = vec![(k(1), pct(9.0)), (k(2), pct(9.03)), (k(3), pct(8.99)), (k(4), pct(4.0)), (k(5), pct(3.0)), (k(6), pct(3.004))];
    let g = eq_groups(&h);
    assert_eq!(g.len(), 2);
    assert_eq!(g[0].iter().map(|x| x.0).collect::<Vec<_>>(), vec![k(2), k(1), k(3)], "the largest group first, anchored at its largest");
    assert_eq!(g[1].len(), 2);
    let j = eqgrp_json(&h);
    assert!(j["n"] == 3 && j["flag"] == true && j["n3"] == true && j["groups"] == 2, "{j}");
    assert!((j["pct"].as_f64().unwrap() - (9.0 + 9.03 + 8.99) / 3.0).abs() < 1e-9 && j["wallets"].as_array().unwrap().len() == 3);
    // r50 8Hpobe16: two x 3.0%
    let j = eqgrp_json(&[(k(1), pct(3.0)), (k(2), pct(3.0)), (k(3), pct(7.0))]);
    assert!(j["n"] == 2 && j["flag"] == true && j["n3"] == false);
    // not equal: 0.06 percentage points apart and > 0.5% of the amount
    assert!(!eq_same(pct(3.0), pct(3.06)));
    assert!(eq_same(pct(3.0), pct(3.049)), "within 0.05 pp: equal");
    // the relative rule: 12.0% vs 12.055% = 0.055 pp but 0.46% of the amount: equal
    assert!(eq_same(pct(12.0), pct(12.055)));
    assert!(!eq_same(pct(12.0), pct(12.07)));
    // anchored, not chained: 5.00 / 5.04 / 5.08 -> one pair, the 5.00 alone
    let g = eq_groups(&[(k(1), pct(5.0)), (k(2), pct(5.04)), (k(3), pct(5.08))]);
    assert_eq!(g.len(), 1);
    assert_eq!(g[0].iter().map(|x| x.0).collect::<Vec<_>>(), vec![k(3), k(2)]);
    assert_eq!(eqgrp_json(&[(k(1), pct(5.0)), (k(2), pct(9.0))]), serde_json::json!({"n": 0}));
    assert_eq!(eqgrp_json(&[]), serde_json::json!({"n": 0}));
}

#[test]
fn dip34_q4_book_and_hold_sellers() {
    let (a, b, wh, me) = ([1u8; 32], [2u8; 32], [9u8; 32], USER);
    let tr = |s: u64, i: u32, user: Pk, buy: bool, sol: u64| pl::Trade { mint: [7; 32], s, i, j: 0, sig: [0; 64], user, buy, sol, tok: 1, vsol: 30_000_000_000,
        vtok: 1_000_000_000_000_000, fbps: 95, cbps: 30, t_rx: 0 };
    let tape: VecDeque<pl::Trade> = [tr(100, 5, a, false, 900_000_000), tr(100, 7, me, true, 0), tr(100, 9, a, false, 200_000_000), tr(101, 0, b, false, 100_000_000),
        tr(101, 1, a, true, 500_000_000), tr(101, 2, me, false, 0), tr(101, 3, a, false, 999_000_000), tr(101, 2, b, false, 150_000_000)].into_iter().collect();
    // our first buy (100, 7), our last sell landing (101, 2): a's sell before our buy and after our sell out; ours never; buys never
    let mut s = hold_sellers(&tape, &me, (100, 7), (101, 2));
    s.sort();
    assert_eq!(s, vec![(a, 200_000_000), (b, 250_000_000)]);

    let mut q = Q4Book::default();
    let hr = 3_600_000_000_000u64;
    let t0 = 100 * hr;
    // a sells >= 0.3 SOL into 3 holds, b only 0.25 / 0.31 / 0.31
    for k in 0..3u64 { q.note_pos(t0 - (20 - k) * hr, Some(wh), true, &[(a, 300_000_000), (b, if k == 0 { 250_000_000 } else { 310_000_000 })]); }
    assert_eq!((q.hs_count(&a, t0), q.hs_count(&b, t0)), (3, 2));
    let holders = vec![(a, pct(4.0)), (b, pct(3.0))];
    assert_eq!(q.hs_at(&holders, t0).iter().map(|x| (x.0, x.2)).collect::<Vec<_>>(), vec![(a, 3)]);
    // 24 h: the first of a's falls out -> no repeat hold-seller
    assert_eq!(q.hs_count(&a, t0 + 5 * hr), 2);
    assert!(q.hs_at(&holders, t0 + 5 * hr).is_empty());
    // the whale's last position 18 h ago: not within 1 h
    assert_eq!(q.unf1h(&wh, t0), None);
    q.note_pos(t0 - hr / 2, Some(wh), false, &[]);
    assert_eq!(q.unf1h(&wh, t0), Some(true), "its last trade with us 30 min ago was not followed");
    assert_eq!(q.unf1h(&wh, t0 + hr), None, "70 min: too old");
    q.note_pos(t0 - hr / 4, Some(wh), true, &[]);
    assert_eq!(q.unf1h(&wh, t0), Some(false), "the LAST one counts");
    q.note_pos(t0 - hr / 8, Some(wh), false, &[]);
    let j = q.json(&holders, &wh, t0, Some((7, 0.5714)));
    assert!(j["wh_l10"] == serde_json::json!([7, 0.5714]) && j["hs_n"] == 1 && j["hs"][0]["w"] == b58(&a) && j["hs"][0]["n"] == 3, "{j}");
    assert!(j["wh_unf1h"] == true && j["wh_last1h"] == true && q.hs_hits == 1 && q.unf_hits == 1);
    let j = q.json(&holders, &[3u8; 32], t0, None);
    assert!(j["wh_l10"] == serde_json::json!([0, null]) && j["wh_unf1h"] == false && j["wh_last1h"] == false);
    assert_eq!(wl10_json(Some((0, -1.0))), serde_json::json!([0, null]));
}

/// the probe: a T2 trigger's skip record gets seen / eqgrp / q4 with the flags, nothing without them; the decision is the same;
/// ann.cr_hold / cr_big; the fill's eqgrp
#[test]
fn dip34_log_on_the_probe() {
    let (mint, cr, wh) = ([7u8; 32], [3u8; 32], [9u8; 32]);
    let (a, b, c, d) = ([11u8; 32], [12u8; 32], [13u8; 32], [14u8; 32]);
    let t0 = 1_793_720_000_000_000_000u64;
    let feed = |p: &mut PsLive| {
        p.det.create(mint, 1000, cr, cr, false);
        let mut ev = Vec::new();
        let mut n = 0u32;
        let mut buy = |p: &mut PsLive, s: u64, u: Pk, tok: i64| {
            n += 1;
            p.det.trade(&pl::Trade { mint, s, i: n, j: 0, sig: [n as u8; 64], user: u, buy: true, sol: 1_000_000_000, tok: tok as u64, vsol: 30_000_000_000,
                vtok: 1_000_000_000_000_000, fbps: 95, cbps: 30, t_rx: t0 }, &mut ev);
        };
        buy(p, 1000, cr, pct(25.0));
        buy(p, 1003, a, pct(9.0)); buy(p, 1003, b, pct(9.02)); buy(p, 1004, c, pct(8.99));
        buy(p, 1005, d, pct(3.0));
        buy(p, 1010, wh, pct(7.0));
    };
    let trig = pl::Trade { mint, s: 1010, i: 6, j: 0, sig: [6; 64], user: wh, buy: true, sol: 1_000_000_000, tok: pct(7.0) as u64, vsol: 30_000_000_000,
        vtok: 1_000_000_000_000_000, fbps: 95, cbps: 30, t_rx: t0 };
    let c = cfg(&["--presend-live-seen-log", "3", "--presend-live-eqgrp-log", "--presend-live-q4-log", "--presend-live-ann", "on"]).unwrap().unwrap();
    let (mut p, _atx, orx) = PsLive::for_test(c, USER);
    feed(&mut p);
    // an earlier cr_loss skip of this whale (1 h ago), and three hold-sells of `a` / the whale's last trip 10 min ago unfollowed
    p.seen_note("cr_loss", wh, t0 - 3_600_000_000_000, [8u8; 32]);
    for k in 1..=3u64 { p.q4_note(t0 - k * 600_000_000_000, None, true, &[(a, 400_000_000)]); }
    p.q4_note(t0 - 600_000_000_000, Some(wh), false, &[]);
    p.trigger(&trig, wh, 7.0, pct(7.0), 10, &|_: &Pk| None, &|_: &Pk| false);
    let r = recs(&orx);
    let s = r.iter().find(|x| x["ev"] == "presend_live_skip").expect("skip record");
    assert_eq!(s["why"], "no_launch_accounts", "the decision: the launch refusal, unchanged");
    assert!(s["seen"]["hit"] == true && s["seen"]["n"] == 1 && s["seen"]["why"][0] == "cr_loss" && s["seen"]["min_ago"][0] == 60.0, "{}", s["seen"]);
    assert!(s["eqgrp"]["n"] == 3 && s["eqgrp"]["n3"] == true && s["eqgrp"]["wallets"].as_array().unwrap().iter().all(|w| w != &b58(&cr)), "{}", s["eqgrp"]);
    assert!(s["q4"]["hs_n"] == 1 && s["q4"]["hs"][0]["w"] == b58(&a) && s["q4"]["wh_unf1h"] == true && s["q4"]["wh_l10"] == serde_json::json!([0, null]), "{}", s["q4"]);
    assert!(s.get("quiet").is_none(), "no QUIET: no quiet object made");
    assert!(s["ann"]["cr_hold"].as_f64().unwrap() > 24.9 && s["ann"]["cr_big"] == true && s["ann"]["cr_hold"] == s["ann"]["cr_pct"], "{}", s["ann"]);
    // the skip (a launch refusal) is not a seen reason: still one noted
    assert_eq!(p.l34.sb.as_ref().unwrap().notes, 1);
    // the fill's eqgrp (the window's whale out; here the creator's 25% is alone)
    let mut rec = serde_json::json!({});
    p.eqgrp_fill(&mut rec, &mint, &wh);
    assert_eq!(rec["eqgrp"]["n"], 3);
    let j = p.l34_json().unwrap();
    assert!(j["seen"]["hits"] == 1 && j["eqgrp"]["arm_n3"] == 1 && j["eqgrp"]["fill_n3"] == 1 && j["q4"]["hs_hits"] == 1 && j["q4"]["unf1h_hits"] == 1, "{j}");

    // flags off (ann too): the same skip, none of the fields
    let (mut q, _atx0, orx0) = PsLive::for_test(cfg(&[]).unwrap().unwrap(), USER);
    feed(&mut q);
    q.trigger(&trig, wh, 7.0, pct(7.0), 10, &|_: &Pk| None, &|_: &Pk| false);
    let r0 = recs(&orx0);
    let s0 = r0.iter().find(|x| x["ev"] == "presend_live_skip").unwrap();
    assert_eq!(s0["why"], "no_launch_accounts");
    assert!(["seen", "eqgrp", "q4", "ann"].iter().all(|k| s0.get(*k).is_none()), "{s0}");
    let mut rec0 = serde_json::json!({});
    q.eqgrp_fill(&mut rec0, &mint, &wh);
    assert_eq!(rec0, serde_json::json!({}));
    assert!(q.l34_json().is_none());
}

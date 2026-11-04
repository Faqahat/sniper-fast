// ===================================================================================================================
// dip34 tests (11-03 PKT; owner ~22:30 PKT "yes let them earn back"): CR-EARNBACK, --presend-live-cr-earn-log K (LOG-ONLY).
// The r39-r50 replay (ops/strategies/presend/filters3/crearn) found no earn-back variant that passes DEV, VAL and the holdout, so the
// paper credits are collected forward and never change a decision:
//  * flags: K in (0, 1], needs --presend-live-cr-loss, a value; off = no "cr_earn_log" in the start record (dip33's)
//  * the history: ps / pn never part of sum / n; earn_trade = the loss rule with the paper counted
//  * the state file: a dip32/33 file (no ps / pn) loads as 0; ps / pn saved only when a creator has credits (else dip32's entry)
//  * the gate: "earn" in the cr record only with the flag; the verdict ("loss") unchanged whatever the paper says
//  * the shadow flow: a cr_loss-skipped trigger's shadow window, its row c fill / exit -> the credit (K x net x live size / sol_in) and
//    the presend_live_cr_paper record; rows a / b, unknown triggers, a window without a row c fill and the flag off credit nothing
// ===================================================================================================================
use super::*;

const USER: Pk = [0x5Au8; 32];

fn v(a: &[&str]) -> Vec<String> { a.iter().map(|s| s.to_string()).collect() }
fn base(extra: &[&str]) -> Vec<String> {
    let mut x = v(&["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "20",
        "--presend-live-fee-budget-sol", "0.03"]);
    x.extend(extra.iter().map(|s| s.to_string()));
    x
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&base(extra), &arbx::presend::Params { whale_pct: 6.0, ..Default::default() }, true, 1_000_000_000) }
fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| o.rec()).collect() }
fn shared() -> Shared {
    Shared { wins: Mutex::new(Vec::new()), stop: AtomicBool::new(false), pause_reactive: AtomicBool::new(false), pause_pos: AtomicBool::new(false),
        pause_fee: AtomicBool::new(false), brk_until: AtomicU64::new(0), brk_losses: Mutex::new(VecDeque::new()), brk_trips: AtomicU64::new(0), cr: Mutex::new(FxHashMap::default()), wh: Mutex::new(FxHashMap::default()),
        slot: AtomicU64::new(0), seq: AtomicU64::new(0), sent: AtomicU64::new(0), dry: AtomicU64::new(0), exited: AtomicBool::new(true),
        skips: Mutex::new(FxHashMap::default()), build_us: Mutex::new(Ring::default()) }
}

#[test]
fn dip34_cr_earn_flags() {
    let c = cfg(&["--presend-live-cr-loss", "2:0.05", "--presend-live-cr-earn-log", "0.5"]).unwrap().unwrap();
    assert_eq!(c.cr_earn, 0.5);
    assert!(c.json()["cr_earn_log"] == 0.5 && c.json()["cr_loss"] == "2:0.05");
    let c1 = cfg(&["--presend-live-cr-loss", "2:0.05", "--presend-live-cr-earn-log", "1"]).unwrap().unwrap();
    assert_eq!(c1.cr_earn, 1.0);
    let c0 = cfg(&["--presend-live-cr-loss", "2:0.05"]).unwrap().unwrap();
    assert!(c0.cr_earn == 0.0 && c0.json().get("cr_earn_log").is_none(), "off: dip33's start record");
    for bad in ["0", "1.5", "-0.3", "x", "NaN"] {
        let e = cfg(&["--presend-live-cr-loss", "2:0.05", "--presend-live-cr-earn-log", bad]).unwrap_err().to_string();
        assert!(e.contains("--presend-live-cr-earn-log"), "{bad}: {e}");
    }
    assert!(cfg(&["--presend-live-cr-loss", "2:0.05", "--presend-live-cr-earn-log"]).is_err(), "a value");
    assert!(cfg(&["--presend-live-cr-loss", "2:0.05", "--presend-live-cr-earn-log", "--presend-live-f3-log"]).is_err(), "a value, not the next flag");
    let e = cfg(&["--presend-live-cr-earn-log", "0.5"]).unwrap_err().to_string();
    assert!(e.contains("needs --presend-live-cr-loss"), "{e}");
    assert!(cfg(&["--presend-live-cr-unfollowed", "3:24", "--presend-live-cr-earn-log", "0.5"]).is_err(), "the unfollowed rule alone: no loss ledger");
    // the start-up check knows it; without --presend-live it is refused
    assert!(crate::check_flags(&base(&["--presend-live-cr-loss", "2:0.05", "--presend-live-cr-earn-log", "0.5"])).is_ok());
    let e = Cfg::from_argv(&v(&["snipe_engine", "--dip", "--presend-shadow", "--presend-live-cr-earn-log", "0.5"]), &arbx::presend::Params::default(), true, 1_000_000_000)
        .unwrap_err().to_string();
    assert!(e.contains("needs --presend-live"), "{e}");
}

#[test]
fn dip34_cr_earn_history_state_and_gate() {
    // the history: paper apart from sum / n
    let mut h = CrHist::default();
    h.add(10, -60_000_000, false);
    h.add(20, -30_000_000, true);
    assert!(!h.earn_trade(2, 50_000_000), "-0.09 over 2: blocked");
    h.ps += 30_000_000; h.pn += 1;
    assert_eq!((h.n, h.sum), (2, -90_000_000), "paper never in sum / n");
    assert!(!h.earn_trade(2, 50_000_000), "-0.09 + 0.03 = -0.06: still blocked");
    h.ps += 20_000_000; h.pn += 1;
    assert!(h.earn_trade(2, 50_000_000), "-0.09 + 0.05 = -0.04: would trade");
    let mut one = CrHist::default(); one.add(1, -500_000_000, false);
    assert!(one.earn_trade(2, 50_000_000), "1 position: never the ledger's block");

    // the state file: a dip32/33 file loads (ps / pn 0); credits saved and loaded; no credits = dip32's entry
    let dir = std::env::temp_dir();
    let old = dir.join(format!("dip34-cr-old-{}.json", std::process::id()));
    let ca = "dtrzJPj7yDdvm6eRqBAgxsK2sMJeD9HhBEBB3XMedXy";
    std::fs::write(&old, format!("{{\"v\": 1, \"c\": {{\"{ca}\": {{\"sum\": -363134835, \"n\": 85, \"h\": [[1793720000000000000, -19573345, false]]}}}}}}")).unwrap();
    let m = cr_load(old.to_str().unwrap()).unwrap();
    let pk: Pk = bs58::decode(ca).into_vec().unwrap().try_into().unwrap();
    let e = &m[&pk];
    assert_eq!((e.sum, e.n, e.h.len(), e.ps, e.pn), (-363_134_835, 85, 1, 0, 0), "an old file: no paper");
    let new = dir.join(format!("dip34-cr-new-{}.json", std::process::id()));
    let mut m2 = m.clone();
    m2.insert([4u8; 32], h.clone());
    assert_eq!(cr_save(&m2, new.to_str().unwrap()).unwrap(), 2);
    let j: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(&new).unwrap()).unwrap();
    assert!(j["c"][ca].get("ps").is_none() && j["c"][ca].get("pn").is_none(), "no credits: dip32's entry");
    assert!(j["c"][b58(&[4u8; 32])]["ps"] == 50_000_000 && j["c"][b58(&[4u8; 32])]["pn"] == 2);
    assert_eq!(cr_load(new.to_str().unwrap()).unwrap(), m2, "round trip");
    let _ = std::fs::remove_file(&old);
    let _ = std::fs::remove_file(&new);

    // the gate: "earn" only with the flag; the decision is the loss rule's whatever the paper says
    let ce = cfg(&["--presend-live-cr-loss", "2:0.05", "--presend-live-cr-earn-log", "0.5"]).unwrap().unwrap();
    let c0 = cfg(&["--presend-live-cr-loss", "2:0.05"]).unwrap().unwrap();
    let sh = shared();
    sh.cr.lock().unwrap().insert([4u8; 32], h.clone());
    let (w, j) = cr_gate(&sh, &ce, Some([4u8; 32]), 30);
    assert_eq!(w, Some("loss"), "log-only: still skipped");
    let j = j.unwrap();
    assert!(j["earn"]["trade"] == true && j["earn"]["pn"] == 2 && (j["earn"]["ps"].as_f64().unwrap() - 0.05).abs() < 1e-12, "{j}");
    let (w0, j0) = cr_gate(&sh, &c0, Some([4u8; 32]), 30);
    assert_eq!(w0, Some("loss"));
    assert!(j0.unwrap().get("earn").is_none(), "off: dip32's cr record");
}

/// the shadow flow on the probe (for_test): skip noted -> the shadow's arm / fills / exits / disarms -> the credit and its record
#[test]
fn dip34_cr_earn_shadow_credit() {
    let c = cfg(&["--presend-live-cr-loss", "2:0.05", "--presend-live-cr-earn-log", "0.5"]).unwrap().unwrap();
    let spend = c.spend as f64;
    let (mut p, _atx, orx) = PsLive::for_test(c, USER);
    let (cr, mint) = ([4u8; 32], [7u8; 32]);
    {
        let mut g = p.sh.cr.lock().unwrap();
        g.entry(cr).or_default().add(10, -60_000_000, false);
        g.entry(cr).or_default().add(20, -30_000_000, true);
    }
    let t0 = 1_793_720_000_000_000_000u64;
    p.ce_note("SIG1".into(), cr, mint, t0);
    let arm = |w: u64, sig: &str| serde_json::json!({"ev": "presend_arm", "w": w, "sig": sig, "mint": b58(&mint)});
    let fill = |w: u64, row: &str, sol_in: f64| serde_json::json!({"ev": "presend_fill", "w": w, "row": row, "entry": {"sol_in": sol_in}});
    let exit = |w: u64, row: &str, net: f64| serde_json::json!({"ev": "presend_exit", "w": w, "row": row, "net_cheap": net, "pnl": net + 0.001});
    let disarm = |w: u64| serde_json::json!({"ev": "presend_disarm", "w": w, "why": "window_end"});
    p.on_shadow_rec(&arm(5, "OTHER"));
    p.on_shadow_rec(&arm(7, "SIG1"));
    assert!(p.ce.w.contains_key(&7) && !p.ce.w.contains_key(&5), "only the skipped trigger's window");
    p.on_shadow_rec(&fill(7, "a", 300_000_000.0));
    p.on_shadow_rec(&exit(7, "a", 0.5));
    p.on_shadow_rec(&exit(7, "b", 0.5));
    assert!(recs(&orx).is_empty() && p.sh.cr.lock().unwrap()[&cr].pn == 0, "rows a / b: nothing");
    p.on_shadow_rec(&fill(7, "c", 500_000_000.0));
    p.on_shadow_rec(&fill(7, "c", 900_000_000.0));
    assert_eq!(p.ce.w[&7].1, Some(500_000_000.0), "the first row c fill");
    p.on_shadow_rec(&disarm(7));
    assert!(p.ce.w.contains_key(&7), "filled: kept until its exit");
    p.on_shadow_rec(&exit(7, "c", 0.1));
    let want = (0.5 * 0.1 * spend / 500_000_000.0 * 1e9).round() as i64;
    {
        let g = p.sh.cr.lock().unwrap();
        let h = &g[&cr];
        assert_eq!((h.n, h.sum, h.ps, h.pn), (2, -90_000_000, want, 1), "credited to the paper column only");
    }
    let r = recs(&orx);
    assert_eq!(r.len(), 1);
    let r = &r[0];
    assert!(r["ev"] == "presend_live_cr_paper" && r["creator"] == b58(&cr) && r["mint"] == b58(&mint) && r["sig"] == "SIG1" && r["w"] == 7 && r["k"] == 0.5 && r["pn"] == 1, "{r}");
    assert!((r["credit"].as_f64().unwrap() - want as f64 / 1e9).abs() < 1e-12 && r["net_cheap"] == 0.1 && r["n"] == 2);
    assert_eq!(r["trade"], serde_json::json!(-90_000_000 + want > -50_000_000), "the earn-back verdict");
    assert!(p.ce.w.is_empty() && p.ce.skipped.is_empty() && p.ce.credits == 1 && p.ce.credit_sum == want);
    assert!(p.cr_status().contains("earn-log credits 1"), "{}", p.cr_status());
    // the decision never reads the paper
    assert_eq!(cr_gate(&p.sh, &p.cfg, Some(cr), t0).0, Some("loss"));
    // a window that ends without a row c fill: dropped, nothing credited; a loss credit is negative
    p.ce_note("SIG2".into(), cr, mint, t0 + 1);
    p.on_shadow_rec(&arm(8, "SIG2"));
    p.on_shadow_rec(&fill(8, "a", 500_000_000.0));
    p.on_shadow_rec(&disarm(8));
    assert!(p.ce.w.is_empty() && p.ce.skipped.is_empty() && recs(&orx).is_empty());
    p.ce_note("SIG3".into(), cr, mint, t0 + 2);
    p.on_shadow_rec(&arm(9, "SIG3"));
    p.on_shadow_rec(&serde_json::json!({"ev": "presend_fill", "w": 9, "entry": {"sol_in": 550_000_000.0}}));
    p.on_shadow_rec(&serde_json::json!({"ev": "presend_exit", "w": 9, "row": "c", "pnl": -0.04}));
    let r = recs(&orx);
    assert!(r.len() == 1 && r[0]["pn"] == 2 && r[0]["net_cheap"] == -0.04, "a fill without a row = row c; pnl when no net_cheap: {r:?}");
    assert_eq!(p.sh.cr.lock().unwrap()[&cr].ps, want + (0.5 * -0.04 * spend / 550_000_000.0 * 1e9).round() as i64);
    // old notes are pruned when the map is full
    for i in 0..CE_MAX { p.ce_note(format!("OLD{i}"), cr, mint, t0); }
    p.ce_note("NEW".into(), cr, mint, t0 + CE_KEEP_NS + 1);
    assert!(p.ce.skipped.len() == 1 && p.ce.skipped.contains_key("NEW"), "older than CE_KEEP_NS dropped");

    // the flag off: the hook does nothing
    let c0 = cfg(&["--presend-live-cr-loss", "2:0.05"]).unwrap().unwrap();
    let (mut q, _atx0, orx0) = PsLive::for_test(c0, USER);
    q.ce.skipped.insert("SIG1".into(), (cr, mint, t0));
    q.on_shadow_rec(&arm(7, "SIG1"));
    q.on_shadow_rec(&fill(7, "c", 500_000_000.0));
    q.on_shadow_rec(&exit(7, "c", 0.1));
    assert!(q.ce.w.is_empty() && recs(&orx0).is_empty() && q.sh.cr.lock().unwrap().is_empty());
    assert!(!q.cr_status().contains("earn"));
}

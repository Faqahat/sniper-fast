// ===================================================================================================================
// dip24 tests (10-29 PKT): the OBSERVATORY wiring (flags off = dip23's records), the limits (minutes 0, unlimited fills, the rolling
// 24 h fee budget's pause / resume, the profit lock's floor; the kill switch untouched), the REGULAR mode's paper tracker.
// The observatory's own modules are unit-tested in src/obs/tests.rs.
//  * flags: every new flag is known to the start-up check, a misspelling refused;
//  * profit lock: the owner's examples (M 0.5 / F 0.30 and M 1.0), never below the kill switch's floor;
//  * fee budget: the sender pauses at the rolling 24 h sum, resumes when it rolls back under; the stream is never stopped by it;
//  * regular paper: pick -> fill at the paper landing -> TP / SL / time exit with our own impact; the guard's no-fill; no send path;
//  * RECORDED HOUR (by hand, the 24/7 recording; DIP24_HOUR=<run dir>[:<from unix s>]): the probe + the shadow on one real hour with the
//    observatory OFF and ON: every dip-log / probe record byte for byte the same (the observatory only reads); DIP24_OUT=DIR writes both
//    runs' records (the dip23 build's same harness compares to them); the paper tracker on the hour's >= 1 SOL sells writes its records
//    and never reaches a send.
// ===================================================================================================================
use super::*;
use arbx::dip::{CreateEvent, TradeEvent};

const USER: Pk = [0x5Au8; 32];
const S: u64 = 1_000_000_000;

fn v(a: &[&str]) -> Vec<String> { a.iter().map(|s| s.to_string()).collect() }

#[test]
fn dip24_flags_known_to_the_start_check() {
    let a = v(&["snipe_engine", "--dip", "--observatory", "--obs-watch", "/x.txt", "--obs-rearm", "--obs-hold", "--obs-migration", "--obs-blink", "--obs-backrun",
        "--obs-file", "/y.jsonl", "--dip-regular", "paper", "--dip-regular-paper-ms", "60", "--profit-lock-min-sol", "0.5", "--profit-lock-frac", "0.3", "--minutes", "0",
        "--max-buys", "0"]);
    assert!(check_flags(&a).is_ok(), "{:?}", check_flags(&a));
    let wrong = ["-", "-obs-watchh"].concat();
    assert!(check_flags(&v(&["snipe_engine", "--dip", &wrong, "x"])).is_err());
    assert!(check_flags(&v(&["snipe_engine", "--dip", "--profit-lock-min-sol", "x"])).is_err(), "a number");
    assert!(check_flags(&v(&["snipe_engine", "--dip", "--dip-regular-paper-ms", "1.5"])).is_err(), "an integer");
}

#[test]
fn dip24_profit_lock_floor_owner_examples() {
    let sol = |x: f64| (x * 1e9).round() as i64;
    let cap = sol(0.5);
    // M = 0.5, F = 0.30: peak +0.5 -> floor start + 0.0; +1.0 -> +0.5; +2.0 -> +1.4; +5.0 -> +3.5; +0.2 -> -0.3; never below -0.5
    for (peak, floor) in [(0.5, 0.0), (1.0, 0.5), (2.0, 1.4), (5.0, 3.5), (0.2, -0.3), (0.0, -0.5)] {
        let (f, _) = lock_floor(sol(peak), sol(0.5), 0.30, cap, 0);
        assert!((f - sol(floor)).abs() <= 1, "peak {peak}: floor {} want {floor}", f as f64 / 1e9);
    }
    // M = 1.0: +1.0 -> +0; +5.0 -> +3.5; at the start the kill switch's floor (-0.5) wins over -1.0
    for (peak, floor) in [(1.0, 0.0), (5.0, 3.5), (0.0, -0.5)] {
        let (f, _) = lock_floor(sol(peak), sol(1.0), 0.30, cap, 0);
        assert!((f - sol(floor)).abs() <= 1, "M 1.0 peak {peak}: floor {} want {floor}", f as f64 / 1e9);
    }
    // below / not below
    assert!(lock_floor(sol(2.0), sol(0.5), 0.3, cap, sol(1.39)).1);
    assert!(!lock_floor(sol(2.0), sol(0.5), 0.3, cap, sol(1.41)).1);
}

#[test]
fn dip24_regular_mode_parse() {
    assert_eq!(Regular::parse(None).unwrap(), Regular::Live);
    assert_eq!(Regular::parse(Some("live")).unwrap(), Regular::Live);
    assert_eq!(Regular::parse(Some("paper")).unwrap(), Regular::Paper);
    assert_eq!(Regular::parse(Some("off")).unwrap(), Regular::Off);
    assert!(Regular::parse(Some("on")).is_err());
}

/// a token on pump's curve
struct Tk { mint: Pk, v: u64, t: u64 }
impl Tk {
    fn new(k: u8) -> Tk { Tk { mint: [k; 32], v: 30 * S, t: 1_073_000_000_000_000 } }
    fn buy(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v + sol) as u128) as u64;
        self.v += sol; self.t -= q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: true, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
    fn sell_sol(&mut self, user: Pk, sol: u64) -> TradeEvent {
        let q = (self.t as u128 * sol as u128 / (self.v - sol) as u128) as u64;
        self.v -= sol; self.t += q;
        TradeEvent { mint: self.mint, sol, tok: q, buy: false, user, vsol: self.v, vtok: self.t, fbps: 95, cbps: 30 }
    }
}

fn log_recs(p: &std::path::Path) -> Vec<serde_json::Value> { std::fs::read_to_string(p).unwrap_or_default().lines().map(|l| serde_json::from_str(l).unwrap()).collect() }

#[test]
fn dip24_regular_paper_fill_exit_and_nofill() {
    let dir = std::env::temp_dir().join(format!("dip24_paper_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir); std::fs::create_dir_all(&dir).unwrap();
    let f = dir.join("dip.jsonl");
    let log = DipLog::open(Some(f.display().to_string())).unwrap();
    let mut pp = Paper::new(60);
    let mut tk = Tk::new(1);
    let t0 = 1_800_000_000 * S;
    let _ = tk.buy([1; 32], 5 * S);
    let d = tk.sell_sol([2; 32], 2 * S);
    // the pick on the dump (min_out = the post-dump quote / 1.05, as live)
    let fr = 0.0125;
    let q = (tk.t as f64 * (0.5e9 / (1.0 + fr)) / (tk.v as f64 + 0.5e9 / (1.0 + fr))).floor();
    pp.pick(tk.mint, "DUMP", 100, 5, t0, d.vsol, d.vtok, fr, 500_000_000, (q / 1.05) as u64, 1_000_000, false, 0.9, "route:test", &log);
    assert!(pp.has(&tk.mint) && pp.open_count() == 1);
    // a trade 30 ms later is ahead of our paper landing; one 70 ms later comes after it: the fill
    let e = tk.buy([3; 32], S / 10); pp.on_trade(&e, 100, 6, t0 + 30_000_000, 0.05, 0.10, &log);
    assert_eq!(pp.fills, 0);
    let e = tk.buy([4; 32], 3 * S); pp.on_trade(&e, 101, 1, t0 + 70_000_000, 0.05, 0.10, &log);
    assert_eq!(pp.fills, 1);
    // a 3 SOL buy after us lifts the value over +5%: take-profit, sold 60 ms later at the state then
    let e = tk.buy([5; 32], 3 * S); pp.on_trade(&e, 101, 2, t0 + 90_000_000, 0.05, 0.10, &log);
    let e = tk.buy([6; 32], S / 100); pp.on_trade(&e, 101, 3, t0 + 200_000_000, 0.05, 0.10, &log);
    assert_eq!(pp.exits, 1);
    assert!(pp.gross > 0 && pp.net < pp.gross, "{} {}", pp.gross, pp.net);
    // a second pick whose guard fails (the price ran up before our landing): a no-fill, 0.5 mSOL
    let mut t2 = Tk::new(2);
    let d = t2.sell_sol([2; 32], S / 2);
    let q = (t2.t as f64 * (0.5e9 / (1.0 + fr)) / (t2.v as f64 + 0.5e9 / (1.0 + fr))).floor();
    pp.pick(t2.mint, "DUMP2", 200, 5, t0 + S, d.vsol, d.vtok, fr, 500_000_000, (q / 1.02) as u64, 0, false, 0.8, "route:test", &log);
    let e = t2.buy([7; 32], 4 * S); pp.on_trade(&e, 200, 9, t0 + S + 10_000_000, 0.05, 0.10, &log);
    let e = t2.buy([8; 32], S / 100); pp.on_trade(&e, 201, 1, t0 + S + 80_000_000, 0.05, 0.10, &log);
    assert_eq!((pp.fills, pp.nofill), (1, 1));
    // a third: filled, then nothing moves: the time exit (land slot + hold) from tick
    let mut t3 = Tk::new(3);
    let d = t3.sell_sol([2; 32], S / 2);
    pp.pick(t3.mint, "DUMP3", 300, 5, t0 + 2 * S, d.vsol, d.vtok, fr, 500_000_000, 1, 0, true, 0.7, "route:test", &log);
    let e = t3.buy([9; 32], S / 100); pp.on_trade(&e, 300, 9, t0 + 2 * S + 90_000_000, 0.05, 0.10, &log);
    pp.tick(305, t0 + 2 * S + 1_500_000_000, 6, &log);
    assert_eq!(pp.exits, 1, "not due yet (land 300 + hold 6)");
    pp.tick(306, t0 + 2 * S + 1_600_000_000, 6, &log);
    pp.tick(306, t0 + 2 * S + 2_700_000_000, 6, &log);
    assert_eq!(pp.exits, 2, "the time limit, sold a second later with no trade");
    pp.finish(&log);
    drop(log);
    let r = log_recs(&f);
    let n = |k: &str| r.iter().filter(|x| x["ev"] == k).count();
    assert_eq!((n("regular_paper_pick"), n("regular_paper_fill"), n("regular_paper_exit")), (3, 3, 2));
    assert!(r.iter().any(|x| x["ev"] == "regular_paper_fill" && x["filled"] == false && x["why"] == "guard"));
    assert!(r.iter().any(|x| x["ev"] == "regular_paper_exit" && x["why"] == "take-profit"));
    assert!(r.iter().any(|x| x["ev"] == "regular_paper_exit" && x["why"] == "time-limit"));
    assert!(pp.line().contains("REGULAR PAPER: picks 3, fills 2"));
    let _ = std::fs::remove_dir_all(&dir);
}

/// the rolling 24 h fee budget: the sender pauses at the budget, resumes when the old fees roll out (feed clock); never stopped
#[test]
fn dip24_fee_budget_rolls_pauses_resumes() {
    let a = v(&["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-fee-budget-sol", "0.001"]);
    let c = pslive::Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1_000_000_000).unwrap().unwrap();
    assert_eq!((c.max_fills, c.fee_budget), (0, 1_000_000));
    let (mut p, _atx, orx) = pslive::PsLive::test_probe(c);
    let h = 3600 * S;
    let t0 = 1_800_000_000 * S;
    // 0.0006 SOL at t0, 0.0005 SOL an hour later: 0.0011 >= 0.001 -> paused
    p.test_fee(t0, 600_000);
    assert!(!p.fee_paused());
    p.test_fee(t0 + h, 500_000);
    assert!(p.fee_paused(), "the rolling sum reached the budget");
    // 23.5 h after t0: still inside the window
    p.test_clock(t0 + 23 * h + h / 2);
    assert!(p.fee_paused());
    // 24 h + 1 s after t0: the first fee rolled out (0.0005 < 0.001) -> resumed
    p.test_clock(t0 + 24 * h + S);
    assert!(!p.fee_paused(), "resumed");
    let r: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
    assert!(r.iter().any(|x| x["ev"] == "presend_live_fee_pause"));
    assert!(r.iter().any(|x| x["ev"] == "presend_live_fee_resume"));
    assert!(r.iter().all(|x| x["ev"] != "presend_live_stop"), "the budget never stops the stream");
}

#[test]
fn dip24_minutes_zero_means_no_deadline() {
    assert!(run_deadline(0).is_none());
    let d = run_deadline(1).unwrap();
    assert!(d > Instant::now() + Duration::from_secs(59) && d <= Instant::now() + Duration::from_secs(60));
    // a week
    assert!(run_deadline(10_080).is_some());
}

/// the recorded hour (by hand): DIP24_HOUR=<run dir>[:<from unix s>] cargo test --release --bin snipe_engine dip24_recorded_hour -- --ignored --nocapture
#[test]
#[ignore]
fn dip24_recorded_hour_obs_off_on_identical() {
    let spec = std::env::var("DIP24_HOUR").expect("DIP24_HOUR=<run dir>[:<from unix s>]");
    let (run, from) = match spec.split_once(':') { Some((r, f)) => (r.to_string(), Some(f.parse::<i64>().unwrap())), None => (spec.clone(), None) };
    let runp = std::path::PathBuf::from(&run);
    let chunks = arbx::presend_quiet::chunks(&runp, 0, u64::MAX);
    assert!(!chunks.is_empty(), "no chunks in {run}");
    let from = from.unwrap_or(chunks[chunks.len() / 2].0 as i64);
    let to = from + 3600;
    let pass = |obs_on: bool, out: &std::path::Path| -> (Vec<String>, Vec<serde_json::Value>, serde_json::Value, (u64, u64), Vec<f64>, Vec<f64>) {
        let (mut per_tx, mut hook) = (Vec::new(), Vec::new());
        let _ = std::fs::remove_file(out);
        let log = DipLog::open(Some(out.display().to_string())).unwrap();
        let a = v(&["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-k", "8",
            "--presend-live-exit-ms", "200", "--presend-live-quiet-stop", "6:2", "--presend-live-quiet-v2-log"]);
        let c = pslive::Cfg::from_argv(&a, &arbx::presend::Params { whale_pct: 6.0, tp: 0.20, ..Default::default() }, true, 1_000_000_000).unwrap().unwrap();
        let (mut p, _atx, orx) = pslive::PsLive::test_probe(c);
        let mut ps = arbx::presend::Shadow::new(arbx::presend::Params { whale_pct: 6.0, tp: 0.20, ..Default::default() });
        let mut obs = obs_on.then(|| {
            let dir = out.parent().unwrap();
            let oc = arbx::obs::Cfg { rearm: true, hold: true, migr: true, blink: true, backrun: true, select: true, race: true, inslot: true, feed_names: vec!["kaldera".into(), "kaldera-tx".into()], watch: vec![arbx::tx::pk("haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq")],
                watch_file: None, watch_names: Default::default(), out: dir.join("hour.obs.jsonl"), tail: Some(out.to_path_buf()), user: USER, rate_cap: 40, k: 8, drop: 0.12,
                cohort: Default::default(), fbots: Default::default(), quiet_book: None, quiet_fol: 2.24, chan: 0, rotate_ns: 0, rotate_bytes: 0 };
            arbx::obs::Obs::start(oc).unwrap()
        });
        let mut rec = arbx::presend_quiet::Recording::open(&[runp.clone()], (from - 600) as u64, to as u64, from, to, true, true);
        let (mut slot_now, mut n) = (0u64, 0u64);
        let t_of = |bt: i64, i: u32| bt as u64 * S + i as u64 * 100_000;
        while let Some(t) = rec.next().unwrap() {
            slot_now = slot_now.max(t.s);
            let x = arbx::feeds::ExecInfo { index: t.i as u64, fee: 5_000, ok: true, trades: t.trades, creates: t.creates, mayhem: t.mayhem };
            let mut sig = [0u8; 64]; sig[..8].copy_from_slice(&t.s.to_be_bytes()); sig[8..12].copy_from_slice(&t.i.to_be_bytes()); sig[12] = 0xD4;
            let xa = Arc::new(x.clone());
            let a = arbx::feeds::Arrival { feed: 0, slot: t.s, t_rx: t_of(t.bt, t.i), t_decoded: t_of(t.bt, t.i), executed: Some(true),
                tx: arbx::tx::Tx { sig, keys: vec![[3u8; 32]], ..Default::default() }, poh: None, raw: arbx::feeds::RawTx::None, exec: Some(xa.clone()) };
            let t0 = Instant::now();
            p.on_arrival(&a, slot_now);
            p.on_exec(&a, &x, slot_now, |m: &Pk| Some(snipe_build::launch_from_target(*m, *m)), &|_| false, None);
            let marks: Vec<[u64; 5]> = (0..=x.trades.len()).map(|_| [0u64; 5]).collect();
            presend_tx_live(&mut ps, t.s, slot_now, &x, &sig, a.t_rx, &marks, &log, Some(&mut p));
            let t1 = Instant::now();
            // the engine's end-of-tx hook (dipmode.rs): a message into the bounded channel
            if let Some(o) = obs.as_ref() { o.feeder.exec(&a, &xa); }
            let t2 = Instant::now();
            per_tx.push((t2 - t0).as_secs_f64() * 1e6);
            if obs_on { hook.push((t2 - t1).as_secs_f64() * 1e6); }
            n += 1;
        }
        ps.finish();
        let mut evs = ps.drain();
        p.annotate_shadow(&mut evs);
        log.w_all(evs.into_iter().map(|e| e.rec));
        let end = p.finish(slot_now + 50, None);
        let probe: Vec<serde_json::Value> = orx.try_iter().filter_map(|o| o.rec()).collect();
        drop(log);
        let ores = obs.as_mut().map(|o| o.finish(Duration::from_secs(60))).unwrap_or(serde_json::Value::Null);
        let lines: Vec<String> = std::fs::read_to_string(out).unwrap().lines().map(|l| l.to_string()).collect();
        let mut endb = end.clone();
        if let Some(o) = endb.as_object_mut() { o.remove("loop_us"); o.remove("us"); }
        (lines, probe, ores, (n, slot_now), per_tx, hook)
    };
    let pct = |v: &mut Vec<f64>, q: f64| -> f64 { if v.is_empty() { return 0.0; } v.sort_by(|a, b| a.partial_cmp(b).unwrap()); v[((v.len() - 1) as f64 * q).round() as usize] };
    let dir = std::env::temp_dir().join(format!("dip24_hour_{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&dir); std::fs::create_dir_all(&dir).unwrap();
    let t = Instant::now();
    let (l_off, p_off, _, (n, _), mut tx_off, _) = pass(false, &dir.join("off.jsonl"));
    let t_off = t.elapsed();
    let t = Instant::now();
    let (l_on, p_on, ores, _, mut tx_on, mut hook) = pass(true, &dir.join("on.jsonl"));
    let t_on = t.elapsed();
    // the probe's records carry its own wall-clock fields (armed_ms, t of stop / disarm): compared without them
    let bare = |mut x: serde_json::Value| { if let Some(o) = x.as_object_mut() { for k in ["t", "armed_ms", "build_us", "write_us", "bh_age_ms"] { o.remove(k); } } x };
    assert_eq!(l_off.len(), l_on.len(), "the dip log's records");
    assert!(l_off == l_on, "the dip log byte for byte with the observatory on");
    assert_eq!(p_off.len(), p_on.len());
    for (a, b) in p_off.iter().zip(&p_on) { assert_eq!(bare(a.clone()), bare(b.clone())); }
    let obs_recs = std::fs::read_to_string(dir.join("hour.obs.jsonl")).unwrap_or_default().lines().count();
    eprintln!("dip24 recorded hour {from}..{to}: {n} txs | dip log {} records identical (observatory off {:.1} s, on {:.1} s) | probe {} records identical | obs {} records: {}",
        l_off.len(), t_off.as_secs_f64(), t_on.as_secs_f64(), p_off.len(), obs_recs, ores);
    assert!(l_off.len() > 100 && obs_recs > 10);
    // the live path per tx (the probe + the shadow + the hook), observatory off vs on; the hook alone
    let (a50, a99, amax) = (pct(&mut tx_off, 0.5), pct(&mut tx_off, 0.99), tx_off.iter().cloned().fold(0.0, f64::max));
    let (b50, b99, bmax) = (pct(&mut tx_on, 0.5), pct(&mut tx_on, 0.99), tx_on.iter().cloned().fold(0.0, f64::max));
    let (h50, h99, hmax) = (pct(&mut hook, 0.5), pct(&mut hook, 0.99), hook.iter().cloned().fold(0.0, f64::max));
    eprintln!("dip24 live-path timing per tx (us): observatory OFF p50 {a50:.2} p99 {a99:.2} max {amax:.0} | ON p50 {b50:.2} p99 {b99:.2} max {bmax:.0} | the hook alone p50 {h50:.3} p99 {h99:.3} max {hmax:.1}");
    if let Ok(o) = std::env::var("DIP24_OUT") {
        std::fs::write(format!("{o}/hour_shadow_off.jsonl"), l_off.join("\n")).unwrap();
        std::fs::write(format!("{o}/hour_probe_off.jsonl"), p_off.iter().map(|x| bare(x.clone()).to_string()).collect::<Vec<_>>().join("\n")).unwrap();
        let _ = std::fs::copy(dir.join("hour.obs.jsonl"), format!("{o}/hour.obs.jsonl"));
    }
    // the paper tracker on the hour's >= 1 SOL curve sells (as picks): records, never a send (it has no send path)
    let pf = dir.join("paper.jsonl");
    let log = DipLog::open(Some(pf.display().to_string())).unwrap();
    let mut pp = Paper::new(60);
    let mut rec = arbx::presend_quiet::Recording::open(&[runp.clone()], (from - 600) as u64, to as u64, from, to, true, true);
    let mut slot_now = 0;
    while let Some(t) = rec.next().unwrap() {
        slot_now = slot_now.max(t.s);
        let t_rx = t.bt as u64 * S + t.i as u64 * 100_000;
        for e in &t.trades {
            pp.on_trade(e, t.s, t.i as u64, t_rx, 0.05, 0.10, &log);
            if !e.buy && e.sol >= S && !pp.has(&e.mint) && pp.open_count() < 2 && e.vsol < 100 * S {
                let fr = (e.fbps + e.cbps).max(1) as f64 / 1e4;
                let x = 0.35e9 / (1.0 + fr);
                let q = (e.vtok as f64 * x / (e.vsol as f64 + x)).floor();
                pp.pick(e.mint, "rec", t.s, t.i as u64, t_rx, e.vsol, e.vtok, fr, 350_000_000, (q / 1.05) as u64, 1_000_000, false, 0.0, "route:paper-test", &log);
            }
        }
        pp.tick(slot_now, t_rx, 6, &log);
    }
    pp.finish(&log);
    drop(log);
    let r = log_recs(&pf);
    eprintln!("dip24 recorded hour paper: {}", pp.line());
    assert!(pp.picks > 0 && r.iter().filter(|x| x["ev"] == "regular_paper_pick").count() as u64 == pp.picks);
    assert!(r.iter().any(|x| x["ev"] == "regular_paper_exit"));
    let _ = std::fs::remove_dir_all(&dir);
}

#[allow(dead_code)]
fn _unused(_: CreateEvent) {}

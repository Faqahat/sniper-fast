//! FT-001 p1's stop snapshot (go-live gate: a live canary's stop must end with its balances read): the snapshot failed
//! in 1.7 ms with "rpc getMultipleAccounts: no attempt before the deadline", asking no provider. The run's RPC client
//! carries the run's stop flag (`Rpc::set_stop`, made for a stop during the boot), which the stop request sets before the
//! stop sequence; every bounded call then failed at once: the stop snapshot, the reconciliation's window search, the
//! executor's expiry checks. Here the run ends as `arbx run` ends at its deadline (the stop requested, `finish`, then
//! `Engine::stop_sequence`) with the ledger's client wired as main.rs wires it, on mock providers whose buckets are as busy
//! as FT-001's.
use super::*;
use crate::rpc::{Endpoint, Registry, Role, Rpc};
use std::sync::atomic::{AtomicBool, Ordering};

const POOLS3: [&str; 3] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4"];
const NO_BAND_THROTTLE: [(&str, &str); 1] = [("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0")];

/// what a provider of the stop's RPC does: answers, or answers every request HTTP 500
#[derive(Clone, Copy, PartialEq)]
enum Prov { Up, Down }

/// a USDC sale of 1/`frac` of pool `m`'s USDC reserve, resolved at the timers 4 ms after its last write
fn sale(r: &mut Rig, m: &PoolMeta, frac: u64, label: &str, slot: u64, mut t: u64) -> u64 {
    let usdc_in = token_amount(&r.data(if sol_is_t0(m) { &m.vault1 } else { &m.vault0 })) / frac;
    let w = swap(&r.chain, m, !sol_is_t0(m), usdc_in, slot, r.unix0).0;
    let s = r.sig(label);
    for (k, d) in w { r.write(k, d, slot, Some(s), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    t + 5 * MS
}

/// the stop's outcome
struct Stopped { r: Rig, st: crate::engine::StopSeq, reg: Arc<Registry>, mocks: Vec<crate::rpc::mock::MockRpc>, wallet: Pk, start: Value, s2: u64,
    /// the busy roles' callers still queued in Haan's bucket when the stop sequence began
    queued_at_stop: usize }

/// A run of the frz canary config in shadow (a shadow executor, the ledger as `Ledger::for_run` assembles it, the start
/// snapshot, would-sends) that ends as `arbx run` ends at its deadline: the stop requested (`Stopper::request`: the gate
/// stopped, the stop flag set), `finish`, then `Engine::stop_sequence`. The ledger's RPC is the run's root client as
/// main.rs makes it (its stop flag the run's, `set_stop`), role `ledger`, on `provs` (mock RPCs holding the wallet's
/// accounts as the start snapshot found them, at a later slot; `Down`: HTTP 500), with FT-001's buckets: 4 requests/s
/// each, Haan's backfill share (2/s) and Shyft's slot-index share (3.8/s) as the deploy configs reserve them, and `busy`
/// callers of those roles (and of the blockhash poll) waiting in each bucket all along. `budget`: the stop snapshot's
fn stop_run(name: &'static str, provs: &[(&str, Prov)], busy: usize, budget: std::time::Duration) -> Stopped {
    let mut r = Rig::new(name, Setup { pools: &POOLS3, config: &NO_BAND_THROTTLE, exec: Some(ExecSetup::default()), ..Default::default() });
    r.make_ready(T0);
    let wallet = crate::tx::pk(&r.cfg.wallet);
    let stopper = crate::control::Stopper::new(r.gate.clone());
    r.e.ledger = Some(crate::ledger::Ledger::for_run(&r.cfg, wallet, r.rec.clone(), name, false, r.gate.clone(), stopper.clone(), Default::default(), None, None));
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    let a = r.meta("usdc.ammv4");
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    let start = crate::ledger::test_snapshot_answer(&wallet, s2, 222_956_693, 191_524_924, 0, "start");
    r.input(InputKind::Snapshot, start.clone(), T0 + 9 * MS);
    let mut t = T0 + 10 * MS;
    for (k, frac) in [100u64, 60].into_iter().enumerate() { t = sale(&mut r, &a, frac, &format!("S-{k}"), s2, t + 5 * MS); }
    // the providers: the wallet's accounts as the start snapshot read them, at a later slot
    let mocks: Vec<crate::rpc::mock::MockRpc> = provs.iter().map(|(_, p)| {
        use base64::Engine as _;
        let m = crate::rpc::mock::MockRpc::start();
        {
            let mut acc = m.accounts.lock().unwrap();
            for (k, v) in start["keys"].as_array().unwrap().iter().zip(start["answers"][0]["values"].as_array().unwrap()) {
                if v.is_null() { continue; }
                let data = base64::engine::general_purpose::STANDARD.decode(v["data"][0].as_str().unwrap()).unwrap();
                acc.insert(crate::tx::pk(k.as_str().unwrap()), (data, crate::tx::pk(v["owner"].as_str().unwrap()), v["lamports"].as_u64().unwrap()));
            }
        }
        m.slot.store(s2 + 3, Ordering::Relaxed);
        if *p == Prov::Down { m.fail_next.store(u64::MAX / 2, Ordering::Relaxed); }
        m
    }).collect();
    // FT-001's buckets: 4/s each, the deploy configs' reserved shares
    let reg = Arc::new(Registry::default());
    for (n, _) in provs { reg.set_limit(n, 4.0, None); }
    reg.set_reserve("haan", Role::Backfill, 2.0);
    reg.set_reserve("shyft", Role::Slotidx, 3.8);
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build().unwrap();
    // the busy roles: callers that take every token they can get, all along
    let done = Arc::new(AtomicBool::new(false));
    for (n, _) in provs {
        for k in 0..busy {
            let (lim, done) = (reg.limiter(n), done.clone());
            let role = match k % 3 { 0 => Role::Backfill, 1 => Role::Slotidx, _ => Role::Blockhash };
            rt.spawn(async move { while !done.load(Ordering::Relaxed) { let _ = lim.take_role(role, None).await; } });
        }
    }
    // the root client as main.rs makes it: the run's stop flag (`set_stop`), every client made from it sharing it
    let root = Rpc::race(provs.iter().zip(&mocks).map(|((n, _), m)| Endpoint { name: n.to_string(), url: m.url.clone(), bearer: None }).collect())
        .with_registry(reg.clone());
    root.set_stop(stopper.flag());
    let (tx, rx) = crossbeam_channel::unbounded::<Event>();
    {
        let l = r.e.ledger.as_mut().unwrap();
        l.set_io(root.with_role(Role::Ledger), rt.handle().clone(), tx.clone());
        l.set_stop_budget(budget);
    }
    // the run loop ends at its deadline: the stop is requested (as main.rs does when `Engine::run` returns), the loop's
    // `finish`, then the stop sequence
    rt.block_on(async { tokio::time::sleep(std::time::Duration::from_millis(300)).await });
    let queued_at_stop = provs.first().map_or(0, |(n, _)| reg.limiter(n).queued());
    assert!(stopper.request(crate::control::StopInfo::new(crate::control::StopReason::Deadline, "--minutes reached")));
    r.e.finish();
    let st = r.e.stop_sequence(&rx, 60_000_000_000, &mut |_: &str| {});
    done.store(true, Ordering::Relaxed);
    r.rec.close();
    drop(rt);
    Stopped { r, st, reg, mocks, wallet, start, s2, queued_at_stop }
}

/// the run's INPUT 13 records (the ledger's RPC answers), in order
fn snapshot_inputs(dir: &Path) -> Vec<Value> {
    crate::rec::journal::read_dir(dir).unwrap().into_iter().filter_map(|x| match x.body {
        crate::rec::journal::JBody::Input { kind, data } if kind == InputKind::Snapshot as u8 => Some(data), _ => None }).collect()
}

/// FT-001 p1's stop, on Haan alone with its bucket as busy as in FT-001 (24 callers of the backfill, which has a
/// reserved share, the slot index and the blockhash poll waiting in it, at 4 tokens a second: six seconds of queue): the
/// stop snapshot is asked after the stop request (before FT-001 it was refused at once, no provider asked) and served
/// ahead of them (`ledger` is critical: the bucket's next token, as the state re-read), the stop's reconciliation passes,
/// nothing is recorded missing
#[test]
fn the_stop_snapshot_is_taken_after_the_stop_request_on_a_busy_bucket() {
    let s = stop_run("ss-busy", &[("haan", Prov::Up)], 24, crate::ledger::STOP_SNAPSHOT_BUDGET);
    assert!(s.queued_at_stop >= 20, "Haan's bucket was busy at the stop: {} callers queued", s.queued_at_stop);
    let snaps = snapshot_inputs(&s.r.dir);
    let stop = snaps.iter().find(|d| d["why"] == "stop").expect("the stop snapshot's answer is journaled");
    assert!(stop["error"].is_null(), "the stop snapshot: {stop}");
    assert_eq!((stop["provider"].as_str(), stop["answers"][0]["slot"].as_u64()), (Some("haan"), Some(s.s2 + 3)), "{stop}");
    // served ahead of the busy roles: its token came at once or at the bucket's next one, not after their queue
    let led = s.reg.total(Role::Ledger, "haan");
    assert!(led.ok >= 1 && led.throttle_wait_us < 1_500_000, "the ledger's token wait {} µs behind {} queued callers", led.throttle_wait_us, s.queued_at_stop);
    assert!(stop["ms"].as_f64().unwrap() < 3_000.0, "{stop}");
    // the stop's reconciliation (start to stop) passed; no missing stop snapshot, no miss
    let recon = rec::read_jsonl(&s.r.dir, "recon").unwrap();
    assert!(recon.iter().any(|l| l["at_stop"] == json!(true) && l["ok"] == json!(true) && l["to"]["slot"].as_u64() == Some(s.s2 + 3)), "{recon:?}");
    assert!(recon.iter().all(|l| l["kind"] != "stop_snapshot_failed" && l["ok"] != json!(false)), "{recon:?}");
    assert_eq!(s.r.e.ledger.as_ref().unwrap().stop_missing(), None);
    assert_eq!((s.st.in_flight, s.st.settled), (Some(0), true));
    assert!(s.mocks[0].calls.load(Ordering::Relaxed) >= 1);
}

/// Haan answers every request with an error and Shyft (its bucket as busy, its slot-index share reserved) answers: the
/// stop snapshot fails over within its budget and is Shyft's
#[test]
fn the_stop_snapshot_fails_over_to_the_provider_that_answers() {
    let s = stop_run("ss-failover", &[("haan", Prov::Down), ("shyft", Prov::Up)], 12, crate::ledger::STOP_SNAPSHOT_BUDGET);
    let snaps = snapshot_inputs(&s.r.dir);
    let stop = snaps.iter().find(|d| d["why"] == "stop").expect("the stop snapshot's answer is journaled");
    assert!(stop["error"].is_null(), "the stop snapshot: {stop}");
    assert_eq!(stop["provider"].as_str(), Some("shyft"), "{stop}");
    assert!(s.mocks[0].calls.load(Ordering::Relaxed) >= 1, "Haan was asked first");
    assert!(s.reg.total(Role::Ledger, "haan").errors >= 1 && s.reg.total(Role::Ledger, "shyft").ok >= 1);
    let recon = rec::read_jsonl(&s.r.dir, "recon").unwrap();
    assert!(recon.iter().any(|l| l["at_stop"] == json!(true) && l["ok"] == json!(true)), "{recon:?}");
    assert_eq!(s.r.e.ledger.as_ref().unwrap().stop_missing(), None);
}

/// Every provider down at the stop: the stop snapshot asks them again and again within its budget, then fails, and the
/// segment records why (recon.jsonl `stop_snapshot_failed`, `ok` null: no miss; a Warn notice). The next segment's
/// first snapshot reconciles the window from the last good snapshot, between segments, says why it spans the earlier
/// segment's end, and passes: no reconciliation miss anywhere (a miss would make every later segment of a campaign record
/// only)
#[test]
fn a_stop_with_every_provider_down_is_reconciled_by_the_next_segment_without_a_miss() {
    let s = stop_run("ss-down", &[("haan", Prov::Down), ("shyft", Prov::Down)], 6, std::time::Duration::from_millis(1_500));
    let snaps = snapshot_inputs(&s.r.dir);
    let stop = snaps.iter().find(|d| d["why"] == "stop").expect("the stop snapshot's failure is journaled");
    let err = stop["error"].as_str().unwrap_or("");
    assert!(!err.is_empty() && !err.contains("no attempt before the deadline"), "the providers were asked: {stop}");
    assert!(stop["attempts"].as_u64().unwrap() >= 2, "retried within its budget: {stop}");
    assert!(s.mocks.iter().all(|m| m.calls.load(Ordering::Relaxed) >= 1), "each provider asked");
    let why = s.r.e.ledger.as_ref().unwrap().stop_missing().map(String::from).expect("why there is no stop snapshot");
    assert!(why.contains("the stop snapshot failed"), "{why}");
    let recon = rec::read_jsonl(&s.r.dir, "recon").unwrap();
    let missing = recon.iter().find(|l| l["kind"] == "stop_snapshot_failed").unwrap_or_else(|| panic!("recorded: {recon:?}"));
    assert_eq!((missing["ok"].clone(), missing["final"].clone(), missing["from"]["slot"].as_u64(), missing["why"].as_str()), (Value::Null, json!(false), Some(s.s2), Some(why.as_str())));
    assert!(recon.iter().all(|l| l["ok"] != json!(false)), "no miss at the stop: {recon:?}");
    let ev = rec::read_jsonl(&s.r.dir, "events").unwrap();
    assert!(ev.iter().any(|e| e["kind"] == "stop_snapshot_missing"), "the owner's notice");
    // the next segment: its history of this one, its first snapshot (the balances unchanged), the window between segments
    let h = crate::ledger::history_of_run(&s.r.dir, crate::feeds::clock::real_ns());
    assert!(h.recon_misses.is_empty());
    let w = h.prev_window.clone().expect("the window the next segment reconciles");
    assert_eq!((w.from.slot, w.stop_missing.as_ref().map(|m| m["why"].clone())), (s.s2, Some(json!(why))));
    let dir2 = s.r.dir.join("next-segment");
    std::fs::create_dir_all(&dir2).unwrap();
    let rec2 = rec::start(rec::Opts { dir: dir2.clone(), run: "ss-down-2".into(), producer: "scenario".into(), cfg: Default::default(), feeds: vec![], monitor: false,
        echo: Some(Box::new(std::io::sink())) }).unwrap();
    let sess = crate::control::Session::new();
    let mut l2 = crate::ledger::Ledger::for_run(&s.r.cfg, s.wallet, rec2.clone(), "ss-down-2", false, sess.gate.clone(), sess.stopper.clone(), h, None, None);
    let t2 = crate::feeds::clock::real_ns();
    let mut first = s.start.clone();
    first["answers"][0]["slot"] = json!(s.s2 + 40);
    l2.on_input(&first, t2, &crate::ledger::no_prices);
    l2.tick(t2 + (l2.cfg.recon_grace_s + 1) * 1_000_000_000, &|| Vec::new());
    rec2.close();
    let r2 = rec::read_jsonl(&dir2, "recon").unwrap();
    let between = r2.iter().find(|l| l["between_segments"] == json!(true)).unwrap_or_else(|| panic!("{r2:?}"));
    assert_eq!((between["ok"].clone(), between["final"].clone(), between["from"]["slot"].as_u64(), between["to"]["slot"].as_u64()),
        (json!(true), json!(true), Some(s.s2), Some(s.s2 + 40)), "{between}");
    assert_eq!(between["stop_snapshot_missing"]["why"].as_str(), Some(why.as_str()), "the window says why it spans the earlier segment's end: {between}");
    assert_eq!((l2.recon_misses, sess.gate.allows()), (0, true), "no miss: {between}");
    assert!(crate::ledger::history_of_run(&dir2, crate::feeds::clock::real_ns()).recon_misses.is_empty());
}

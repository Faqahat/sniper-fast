//! S11 (PLAN WP-09, after WP-05): bands and crowding, and their replay. The ≥1M class (bands 3-4, src/bands.rs) is
//! throttled by a token bucket on the engine's time (`[send_policy] big_band_max_per_sec`, 0.5 a second, burst 1:
//! `band_throttle`) and queued behind every smaller band; a route through a crowded pool (WP-00's static list stands in
//! for the activity map in Stage 0: bucket 2) is queued behind the others of its band, and is not sent at all when it
//! expects `crowded_skip_min_expected_lamports` or more (`crowded_skip`).
//!
//! - **Ranks** (shadow, no queue): the order is the decision's `rank` (0 small, 1 small crowded, 2 big, 3 big crowded)
//!   and the attempt's `queue`.
//! - **The queue's order** (a canary against the block engine in memory, its jito-bundle path at one send a second and
//!   a 5 s queue): the first send takes the second's only slot; three more decided right after it wait, and the slots
//!   that free go to them best first (send/budget.rs): the small one (rank 0), then the big one (2), then the big
//!   crowded one (3), though they were decided big, big crowded, small. The block engine receives the bundles in that
//!   order.
//!
//! Each run is replayed: the bucket, the crowding map (its static list from the run's exec_init record) and every
//! verdict, rank and attempt are the run's; each run's executor projection is checked against
//! `testdata/scenarios/expected/<name>.json`.
use super::*;

/// a trade of `amount` into pool `m` (`usdc_in`: USDC in, else SOL in) by transaction `sig` at `slot`, resolved by
/// quiescence at the timers 4 ms after its last write; returns the engine time after it
fn trade(r: &mut Rig, m: &PoolMeta, usdc_in: bool, frac: u64, label: &str, slot: u64, t: u64) -> u64 {
    let reserve = token_amount(&r.data(match (usdc_in, sol_is_t0(m)) { (true, true) | (false, false) => &m.vault1, _ => &m.vault0 }));
    trade_of(r, m, usdc_in, reserve / frac, label, slot, t)
}

/// `trade` of `amount` (raw units of what goes in)
fn trade_of(r: &mut Rig, m: &PoolMeta, usdc_in: bool, amount: u64, label: &str, slot: u64, mut t: u64) -> u64 {
    let zfo = if usdc_in { !sol_is_t0(m) } else { sol_is_t0(m) };
    let w = swap(&r.chain, m, zfo, amount, slot, r.unix0).0;
    let s = r.sig(label);
    for (k, d) in w { r.write(k, d, slot, Some(s), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    t + 5 * MS
}

/// (decision, buy, sell, band, band_at_opp, crowding bucket, rank, reason_ungated, attempt, ev)
type Row = (u64, String, String, Option<u64>, Option<u64>, Option<u64>, Option<u64>, Option<String>, Option<u64>, Option<i64>);

fn rows(r: &Rig) -> Vec<Row> {
    r.opportunities().iter().map(|d| {
        let b = &d["routes"][d["best"].as_u64().unwrap() as usize];
        (d["decision"].as_u64().unwrap(), nm(&crate::tx::pk(b["buy"].as_str().unwrap())), nm(&crate::tx::pk(b["sell"].as_str().unwrap())), d["band"].as_u64(),
            d["band_at_opp"].as_u64(), d["crowding"]["bucket"].as_u64(), d["rank"].as_u64(), d["reason_ungated"].as_str().map(String::from), d["attempt"].as_u64(),
            d["ev"].as_i64())
    }).collect()
}

/// a run on the USDC/SOL pools of PumpSwap, CPMM and AMM v4 with CPMM on WP-00's crowded list, ready, the Jito leader's
/// slots, a fresh blockhash; returns it with its slot
fn rig(name: &'static str, config: &'static [(&'static str, &'static str)]) -> (Rig, u64) {
    let mut r = Rig::new(name, Setup { pools: &["usdc.pump", "usdc.cpmm", "usdc.ammv4"], config, exec: Some(ExecSetup { crowded: &["usdc.cpmm"], ..Default::default() }),
        ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    (r, s2)
}

/// every decision the executor ranked: `rank` = 2 × the band's rank (the ≥1M class) + the crowding's (bucket 2), and the
/// attempt's queue says the same
fn ranks_hold(r: &Rig) {
    let att = r.attempts();
    for d in r.opportunities() {
        let Some(rank) = d["rank"].as_u64() else { continue };
        let (band, bucket) = (d["band"].as_u64().unwrap(), d["crowding"]["bucket"].as_u64().unwrap());
        assert_eq!(rank, 2 * (band >= 3) as u64 + (bucket >= 2) as u64, "{d}");
        if let Some(a) = d["attempt"].as_u64() {
            let q = &att.iter().find(|l| l["attempt"].as_u64() == Some(a)).unwrap()["queue"];
            assert_eq!((q["rank"].as_u64(), q["band_rank"].as_u64(), q["crowd_rank"].as_u64()), (Some(rank), Some((band >= 3) as u64), Some((bucket >= 2) as u64)), "{q}");
        }
    }
}

/// The ≥1M class: a big gap is a would-send that takes the class's token (0.5 a second, burst 1); a new state of the same
/// route 10 ms later is refused (`band_throttle`), and one 2.5 s later goes again. Each ranks 2 (big, not crowded): behind
/// every smaller band
#[test]
fn s11_big_band_is_throttled_and_ranked_behind_smaller_bands() {
    let (mut r, s2) = rig("s11-big", &[]);
    let a = r.meta("usdc.ammv4");
    let mut t = trade(&mut r, &a, true, 60, "S11-1", s2, T0 + 10 * MS);
    t = trade(&mut r, &a, true, 300, "S11-2", s2, t + 10 * MS);
    trade(&mut r, &a, true, 300, "S11-3", s2, t + 2_500 * MS);
    let o = rows(&r);
    eprintln!("S11 big: {o:#?}");
    assert_eq!(o.len(), 3, "{o:?}");
    for x in &o { assert!((x.1.as_str(), x.2.as_str()) == ("usdc.ammv4", "usdc.pump") && x.3.unwrap() >= 3 && x.5 == Some(0), "the same big uncrowded route: {x:?}"); }
    assert_eq!((o[0].6, o[0].7.as_deref(), o[0].8), (Some(2), None, Some(0)), "a would-send, rank 2: {:?}", o[0]);
    assert_eq!((o[1].6, o[1].7.as_deref(), o[1].8), (None, Some("band_throttle"), None), "10 ms later: the class's token is spent: {:?}", o[1]);
    assert_eq!((o[2].6, o[2].7.as_deref(), o[2].8), (Some(2), None, Some(1)), "2.5 s later the bucket has refilled: {:?}", o[2]);
    ranks_hold(&r);
    r.finish_and_replay().check_expected();
}

/// Crowding: a route through CPMM (on WP-00's list: bucket 2) expecting little is a would-send ranked behind the
/// uncrowded routes of its band (rank 1); expecting `crowded_skip_min_expected_lamports` (100,000) or more it is not
/// sent at all (`crowded_skip`). With the skip off (rank only), a crowded ≥1M route ranks 3: behind every other
#[test]
fn s11_crowded_routes_rank_behind_and_skip() {
    let (mut r, s2) = rig("s11-crowded", &[]);
    let c = r.meta("usdc.cpmm");
    // SOL sold into CPMM: USDC is dear there, the route buys it on the AMM v4 pool and sells it on CPMM
    let t = trade(&mut r, &c, false, 150, "S11-c1", s2, T0 + 10 * MS);
    trade(&mut r, &c, false, 200, "S11-c2", s2, t + 10 * MS);
    let o = rows(&r);
    eprintln!("S11 crowded: {o:#?}");
    assert_eq!(o.len(), 2, "{o:?}");
    for x in &o { assert!(x.2 == "usdc.cpmm" && x.5 == Some(2), "a route through the crowded pool, bucket 2: {x:?}"); }
    assert!(o[0].3.unwrap() < 3 && o[0].6 == Some(1) && o[0].7.is_none() && o[0].8 == Some(0), "a small crowded would-send, rank 1: {:?}", o[0]);
    assert!(o[1].7.as_deref() == Some("crowded_skip") && o[1].8.is_none(), "expecting 100,000 or more: not sent: {:?}", o[1]);
    let ev = &r.opportunities()[1];
    assert!(ev["routes"][ev["best"].as_u64().unwrap() as usize]["gross"].as_i64().unwrap() >= 100_000, "{ev}");
    ranks_hold(&r);
    r.finish_and_replay().check_expected();
    // the skip off: rank only
    let (mut r, s2) = rig("s11-crowded-rank", &[("crowded_skip_min_expected_lamports = 100000", "crowded_skip_min_expected_lamports = 0")]);
    let c = r.meta("usdc.cpmm");
    trade(&mut r, &c, false, 10, "S11-c3", s2, T0 + 10 * MS);
    let o = rows(&r);
    eprintln!("S11 crowded, rank only: {o:#?}");
    assert!(o.len() == 1 && o[0].3.unwrap() >= 3 && o[0].5 == Some(2) && o[0].6 == Some(3) && o[0].8 == Some(0), "a big crowded would-send ranks 3: {o:?}");
    ranks_hold(&r);
    r.finish_and_replay().check_expected();
}

/// The queue's order on the real send path: a canary (0.2 SOL, no wait between attempts) whose jito-bundle path sends
/// one bundle a second and lets a send wait 5 s (the ≥1M throttle lifted and the crowded skip off: the queue alone
/// orders them). A big gap on the AMM v4 pool is sent at once and takes the second's slot; three gaps decided right
/// after it, in the order big (a new state of the same route), big crowded (CPMM), small (the bolt pair, a pair of its
/// own), wait in the queue and reach the block engine best first: the small one, the big one, the big crowded one
/// (bundles b1, b2, b3), a second apart
#[test]
fn s11_the_send_queue_serves_the_best_first() {
    const QUEUE: [(&str, &str); 6] = [CANARY[0], CANARY[1], ("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0"),
        ("crowded_skip_min_expected_lamports = 100000", "crowded_skip_min_expected_lamports = 0"), ("max_per_sec = 5               # Jito's limit", "max_per_sec = 1               # Jito's limit"),
        ("queue_ms = 10   # the Jito rate queue", "queue_ms = 5000   # the Jito rate queue")];
    let pools: &'static [&'static str] = &["usdc.pump", "usdc.cpmm", "usdc.ammv4", "bolt.pump", "bolt.dlmm"];
    let mut r = Rig::new("s11-queue", Setup { pools, config: &QUEUE, exec: Some(ExecSetup { mode: crate::exec::Mode::Canary, sticky_shadow: false, crowded: &["usdc.cpmm"],
        ..Default::default() }), ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 400], T0 + 7 * MS);
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    r.snapshot(s2, 3 * SOL, 2 * SOL, None, "start", T0 + 9 * MS);
    let (a, c, bp) = (r.meta("usdc.ammv4"), r.meta("usdc.cpmm"), r.meta("bolt.pump"));
    // the first: a big gap on the AMM v4 pool, sent at once (the budget's slot of this second)
    let mut t = trade(&mut r, &a, true, 40, "S11-q0", s2, T0 + 10 * MS);
    // then, while it holds the slot: big (more USDC into the AMM v4 pool), big crowded (SOL into CPMM), small (a sale
    // of the bolt token into its PumpSwap pool, 1/150 of its reserve: a band-0 gap past its round trip's fees)
    t = trade(&mut r, &a, true, 60, "S11-q1", s2, t + MS);
    t = trade(&mut r, &c, false, 10, "S11-q2", s2, t + MS);
    t = trade(&mut r, &bp, true, 150, "S11-q3", s2, t + MS);
    let o = rows(&r);
    eprintln!("S11 queue: decided {o:#?}");
    for d in r.evaluations() {
        let b = d["best"].as_u64().map(|k| d["routes"][k as usize].clone());
        eprintln!("S11 queue: evaluation {} of {} ({}): best {:?}", d["decision"], nm(&crate::tx::pk(d["trigger"]["pool"].as_str().unwrap())), d["reason"],
            b.map(|b| (nm(&crate::tx::pk(b["buy"].as_str().unwrap())), nm(&crate::tx::pk(b["sell"].as_str().unwrap())), b["size"].clone(), b["gross"].clone(), b["reason"].clone())));
    }
    let sent: Vec<&Row> = o.iter().filter(|x| x.8.is_some()).collect();
    assert_eq!(sent.len(), 4, "four sends: {o:?}");
    assert_eq!(sent.iter().map(|x| x.6).collect::<Vec<_>>(), vec![Some(2), Some(2), Some(3), Some(0)], "decided big, big, big crowded, small: {o:?}");
    // the fires' results as they come back (the queue holds three of them up to a second each)
    let fired = r.pump(4, t + MS);
    eprintln!("S11 queue: fired {fired:?}");
    let bundles = r.bundles_sent();
    let att = r.attempts();
    let order: Vec<u64> = bundles.iter().map(|raw| {
        let sig = crate::send::first_signature(raw).unwrap();
        att.iter().find(|x| x["tx"]["sig"] == json!(sig)).unwrap()["attempt"].as_u64().unwrap()
    }).collect();
    assert_eq!(order, vec![0, 3, 1, 2], "the block engine got the first, then the waiting ones best first: rank 0, 2, 3");
    let copies = r.lines("copies");
    let waited = |a: u64| copies.iter().find(|c| c["attempt"].as_u64() == Some(a)).unwrap()["queue_wait_us"].as_u64().unwrap_or(0);
    assert!(waited(0) < 500_000 && waited(3) >= 500_000 && waited(1) > waited(3) && waited(2) > waited(1), "the waits follow the order: {copies:?}");
    ranks_hold(&r);
    r.finish_and_replay().check_expected();
}

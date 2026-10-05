//! S11 (PLAN WP-09, after WP-05): bands and crowding in a run with a shadow executor, and its replay. The ≥1M class
//! (bands 3-4, src/bands.rs) is throttled by a token bucket on the engine's time (`[send_policy] big_band_max_per_sec`,
//! 0.5 a second, burst 1: `band_throttle`) and queued behind every smaller band; a route through a crowded pool (WP-00's
//! static list stands in for the activity map in Stage 0: bucket 2) is queued behind the others of its band, and is not
//! sent at all when it expects `crowded_skip_min_expected_lamports` or more (`crowded_skip`). In shadow there is no queue:
//! the order is the decision's `rank` (0 small, 1 small crowded, 2 big, 3 big crowded) and the attempt's `queue`. Each run
//! is replayed: the bucket, the crowding map (its static list from the run's exec_init record) and every verdict, rank
//! and attempt are the run's.
use super::*;

/// a trade of `amount` into pool `m` (`usdc_in`: USDC in, else SOL in) by transaction `sig` at `slot`, resolved by
/// quiescence at the timers 4 ms after its last write; returns the engine time after it
fn trade(r: &mut Rig, m: &PoolMeta, usdc_in: bool, frac: u64, label: &str, slot: u64, mut t: u64) -> u64 {
    let reserve = token_amount(&r.data(match (usdc_in, sol_is_t0(m)) { (true, true) | (false, false) => &m.vault1, _ => &m.vault0 }));
    let zfo = if usdc_in { !sol_is_t0(m) } else { sol_is_t0(m) };
    let w = swap(&r.chain, m, zfo, reserve / frac, slot, r.unix0).0;
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
    r.finish_and_replay();
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
    r.finish_and_replay();
    // the skip off: rank only
    let (mut r, s2) = rig("s11-crowded-rank", &[("crowded_skip_min_expected_lamports = 100000", "crowded_skip_min_expected_lamports = 0")]);
    let c = r.meta("usdc.cpmm");
    trade(&mut r, &c, false, 10, "S11-c3", s2, T0 + 10 * MS);
    let o = rows(&r);
    eprintln!("S11 crowded, rank only: {o:#?}");
    assert!(o.len() == 1 && o[0].3.unwrap() >= 3 && o[0].5 == Some(2) && o[0].6 == Some(3) && o[0].8 == Some(0), "a big crowded would-send ranks 3: {o:?}");
    ranks_hold(&r);
    r.finish_and_replay();
}

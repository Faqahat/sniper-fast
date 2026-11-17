// ===================================================================================================================
// dip51 tests: the DENSE FRONT (ps51.rs + Pace::with_front in presend_live.rs). Declared inside pslive.rs.
// ===================================================================================================================
use super::*;
use super::ps51::*;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }

const SLOT: u64 = 400_000_000;
/// the tries a pace fires over `slots` slots, ticked every 0.1 ms (the sender's loop is faster than any interval here)
fn fired(mut p: pl::Pace, start: u64, slots: u64) -> Vec<u64> {
    let mut v = Vec::new();
    let mut t = start;
    while t < start + slots * SLOT { if p.due(t) { v.push(t); } t += 100_000; }
    v
}

/// off = dip49c exactly: Pace::new and with_front(None) fire at the same instants
#[test]
fn dip51_off_is_dip49c() {
    for k in [1u64, 4, 8, 20] {
        let a = fired(pl::Pace::new(5_000, k, SLOT), 5_000, 10);
        let b = fired(pl::Pace::with_front(5_000, k, SLOT, None), 5_000, 10);
        assert_eq!(a, b, "k {k}");
        assert_eq!(a.len() as u64, 10 * k, "k {k}: {k} per slot over 10 slots");
    }
}

/// front 3:40 then k 10: 40 per slot in the first 3 slots (10 ms apart), 10 per slot after (40 ms apart); 190 over 10 slots
#[test]
fn dip51_front_counts_and_spacing() {
    let v = fired(pl::Pace::with_front(0, 10, SLOT, Some((3, 40))), 0, 10);
    let per_slot: Vec<usize> = (0..10).map(|s| v.iter().filter(|t| **t / SLOT == s).count()).collect();
    assert_eq!(per_slot, vec![40, 40, 40, 10, 10, 10, 10, 10, 10, 10], "{per_slot:?}");
    assert_eq!(v.len(), 190);
    let gaps_front: Vec<u64> = v.windows(2).filter(|w| w[1] < 3 * SLOT).map(|w| w[1] - w[0]).collect();
    assert!(gaps_front.iter().all(|g| *g == 10_000_000), "front tries 10 ms apart");
    let gaps_after: Vec<u64> = v.windows(2).filter(|w| w[0] >= 3 * SLOT).map(|w| w[1] - w[0]).collect();
    assert!(gaps_after.iter().all(|g| *g == 40_000_000), "later tries 40 ms apart");
    // a front equal to k changes nothing
    assert_eq!(fired(pl::Pace::with_front(0, 20, SLOT, Some((3, 20))), 0, 10), fired(pl::Pace::new(0, 20, SLOT), 0, 10));
}

/// a late tick restarts the pace from now (no burst), in the front as before
#[test]
fn dip51_no_catch_up_burst() {
    let mut p = pl::Pace::with_front(0, 10, SLOT, Some((3, 40)));
    assert!(p.due(0));
    assert!(p.due(50_000_000), "one try at the late tick");
    assert!(!p.due(50_000_001), "not a second one at once");
    assert_eq!(p.next, 60_000_000);
}

/// the flags: off by default; SLOTS:K ranges; K >= --presend-live-k; kinds; strays refused
#[test]
fn dip51_flags() {
    let c = cfg(&[]).unwrap().unwrap();
    assert_eq!((c.d51.front, c.d51.front_for(false), c.d51.front_for(true)), (None, None, None));
    assert_eq!(c.d51.desc(), "");
    let c = cfg(&["--presend-live-k", "10", "--presend-live-front", "3:40"]).unwrap().unwrap();
    assert_eq!((c.d51.front_for(false), c.d51.front_for(true)), (Some((3, 40)), None), "default kinds: T2 only");
    assert!(c.d51.desc().contains("first 3 slot(s) of each T2 window at 40 tries/slot"));
    assert_eq!(c.json()["d51"]["k"], 40);
    let c = cfg(&["--presend-live-k", "10", "--presend-live-front", "2:30", "--presend-live-front-kinds", "t2,rearm"]).unwrap().unwrap();
    assert_eq!((c.d51.front_for(false), c.d51.front_for(true)), (Some((2, 30)), Some((2, 30))));
    let c = cfg(&["--presend-live-k", "10", "--presend-live-front", "2:30", "--presend-live-front-kinds", "rearm"]).unwrap().unwrap();
    assert_eq!((c.d51.front_for(false), c.d51.front_for(true)), (None, Some((2, 30))));
    for bad in [&["--presend-live-front", "0:40"][..], &["--presend-live-front", "11:40"], &["--presend-live-front", "3:51"], &["--presend-live-front", "3:0"],
                &["--presend-live-front", "3"], &["--presend-live-front", "x:y"], &["--presend-live-front"], &["--presend-live-k", "20", "--presend-live-front", "3:10"],
                &["--presend-live-front-kinds", "t2"], &["--presend-live-front", "3:40", "--presend-live-front-kinds", "wide"],
                &["--presend-live-front", "3:40", "--presend-live-front-kinds", "t2,t2"], &["--presend-live-front", "3:40", "--presend-live-front-kinds"]] {
        assert!(cfg(bad).is_err(), "{bad:?} refused");
    }
    // a stray dip51 flag without --presend-live is refused
    let a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-live-front", "3:40"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1_000_000_000).is_err());
}

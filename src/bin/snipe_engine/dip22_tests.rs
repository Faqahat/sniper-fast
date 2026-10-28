// ===================================================================================================================
// dip22 tests (10-28 PKT): the pre-send "sell earlier" exit (--presend-live-exit-ms N). The verifier's forward test on 114 live
// FRA pre-send fills (ops/strategies/haqq_dissect/verify/REPORT.md): selling ~200 ms after the fill beat the 2-slot exit by
// +5.5 mSOL per fill. Off by default (0): the run is exactly dip21's.
//  * flags: off by default; accepted 50..2000; refused outside; refused without --presend-live
//  * the decision (time_exit_due): the ms exit first, then the slot limit and the wall-clock backstop exactly as before
// ===================================================================================================================
use super::*;

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }

#[test]
fn exit_ms_flag_off_by_default_and_checked() {
    assert_eq!(cfg(&[]).unwrap().unwrap().exit_ms, 0, "off by default: dip21's exit");
    assert_eq!(cfg(&["--presend-live-exit-ms", "200"]).unwrap().unwrap().exit_ms, 200);
    assert_eq!(cfg(&["--presend-live-exit-ms", "50"]).unwrap().unwrap().exit_ms, 50);
    assert_eq!(cfg(&["--presend-live-exit-ms", "2000"]).unwrap().unwrap().exit_ms, 2000);
    for bad in ["20", "2001", "99999"] {
        assert!(cfg(&["--presend-live-exit-ms", bad]).is_err(), "{bad} must be refused");
    }
    // a stray flag without --presend-live is refused (like every --presend-live-* flag)
    let a: Vec<String> = ["snipe_engine", "--dip", "--presend-live-exit-ms", "200"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1_000_000_000).is_err());
}

#[test]
fn time_exit_decision() {
    // off (0): exactly the old rule: the slot limit (entry + 2) and the wall-clock backstop (2 * 400 + 3000 ms)
    assert_eq!(time_exit_due(100, 100, 2, 10_000_000, 0).is_some(), true);
    assert_eq!(time_exit_due(100, 100, 2, 500, 0), None);
    assert_eq!(time_exit_due(101, 100, 2, 500, 0), None);
    assert_eq!(time_exit_due(102, 100, 2, 500, 0), Some("time-limit"));
    assert_eq!(time_exit_due(100, 100, 2, 3_801, 0), Some("time-limit-wall"));
    assert_eq!(time_exit_due(100, 100, 2, 3_800, 0), None);
    // on (200 ms): sells at 200 ms after the fill, inside the fill's slot or the next
    assert_eq!(time_exit_due(100, 100, 2, 199, 200), None);
    assert_eq!(time_exit_due(100, 100, 2, 200, 200), Some("time-ms"));
    assert_eq!(time_exit_due(101, 100, 2, 250, 200), Some("time-ms"));
    // the slot limit still applies when the ms exit has not come yet (a slow feed / a late tick)
    assert_eq!(time_exit_due(102, 100, 2, 150, 200), Some("time-limit"));
    // the wall-clock backstop still applies
    assert_eq!(time_exit_due(100, 100, 2, 3_801, 5_000), Some("time-limit-wall"));
}

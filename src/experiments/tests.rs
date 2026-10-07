//! experiments.rs's tests (PLAN WP-11 offline acceptance): the assignment is deterministic and balanced (chi-square on
//! 10^5 ids), two experiments assign independently (a factorial design), the scopes, the config's checks, and a config
//! with experiments off hashes as before
use super::*;
use crate::config::Config;

/// chi-square critical values at p = 0.001 by degrees of freedom (1..=7)
const CHI2_999: [f64; 8] = [0.0, 10.828, 13.816, 16.266, 18.467, 20.515, 22.458, 24.322];

fn chi2(obs: &[u64], weights: &[f64]) -> f64 {
    let n: u64 = obs.iter().sum();
    let w: f64 = weights.iter().sum();
    obs.iter().zip(weights).map(|(o, wi)| { let e = n as f64 * wi / w; (*o as f64 - e).powi(2) / e }).sum()
}

/// a minimal config (`Config::parse` checks it) with `extra` TOML
fn cfg(extra: &str) -> Result<Config, String> {
    Config::parse(&format!("config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n\
        [state]\nurl = \"http://localhost\"\n{extra}")).map_err(|e| format!("{e:#}"))
}

const LADDER: &str = "[strategy]\nsizes_sol = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2]\n";
const CAPS: &str = "[canary]\nenabled = true\nsize_sol = 0.2\n[live]\nmax_size_sol = 0.2\n";

/// PLAN WP-11 acceptance: the arm is a pure function of (seed, experiment, decision id): the same call gives the same
/// arm, and over 10^5 consecutive decision ids the counts match the weights (chi-square under its p = 0.001 critical
/// value), for 2 to 4 arms, equal and unequal weights, and two seeds
#[test]
fn assignment_is_deterministic_and_balanced() {
    const N: u64 = 100_000;
    for seed in [0u64, 20_261_007, u64::MAX] {
        for (name, w) in [("x4", vec![1.0, 1.0, 1.0]), ("size", vec![1.0, 1.0]), ("x2", vec![1.0; 4]), ("margin", vec![1.0, 2.0, 1.0]), ("x4", vec![0.25, 0.75])] {
            let mut obs = vec![0u64; w.len()];
            for id in 0..N {
                let a = assign(seed, name, id, &w);
                assert_eq!(a, assign(seed, name, id, &w), "deterministic");
                obs[a] += 1;
            }
            let c = chi2(&obs, &w);
            assert!(c < CHI2_999[w.len() - 1], "seed {seed} {name} {w:?}: {obs:?} chi2 {c:.2}");
        }
    }
    // another seed is another assignment (about half of a 2-arm experiment's ids change)
    let changed = (0..N).filter(|id| assign(1, "size", *id, &[1.0, 1.0]) != assign(2, "size", *id, &[1.0, 1.0])).count();
    assert!((40_000..60_000).contains(&changed), "{changed}");
    // the hash is its definition: xxh3-64 of name ++ 0xff ++ id (LE), seeded
    let mut b = b"x4".to_vec();
    b.push(0xff);
    b.extend(7u64.to_le_bytes());
    assert_eq!(unit_hash(42, "x4", 7), xxhash_rust::xxh3::xxh3_64_with_seed(&b, 42));
    // the draw: the top 53 bits over the weights' sum (the edges of the unit interval)
    assert_eq!((pick(0, &[1.0, 1.0]), pick(u64::MAX, &[1.0, 1.0]), pick(u64::MAX / 2, &[1.0, 1.0]), pick(u64::MAX / 2 + 4096, &[1.0, 1.0])), (0, 1, 0, 1));
    assert_eq!((pick(u64::MAX / 4 + 4096, &[1.0, 3.0]), pick(u64::MAX / 4, &[1.0, 3.0])), (1, 0), "a quarter of the draws on the first arm");
}

/// The assignment of decision ids is pinned: a change of the hash or the draw would give a recorded run other arms in
/// its replay (the replay checks the arms it recomputes against the run's records)
#[test]
fn assignment_is_pinned() {
    let got: Vec<usize> = (0..24).map(|id| assign(20_261_007, "x4", id, &[1.0, 1.0, 1.0])).collect();
    let got2: Vec<usize> = (0..24).map(|id| assign(20_261_007, "size", id, &[1.0, 1.0])).collect();
    assert_eq!(got, PINNED_X4.to_vec(), "x4: {got:?}");
    assert_eq!(got2, PINNED_SIZE.to_vec(), "size: {got2:?}");
}
const PINNED_X4: [usize; 24] = [0, 1, 2, 0, 0, 2, 0, 0, 1, 1, 0, 0, 2, 0, 1, 2, 0, 0, 2, 0, 1, 0, 2, 0];
const PINNED_SIZE: [usize; 24] = [1, 1, 0, 1, 0, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 0, 0, 0, 0, 0];

/// PLAN WP-11: two experiments under one seed assign independently (their names differ in the hash): over 10^5 ids
/// the 3 x 2 table of (x4 arm, size arm) passes the chi-square test of independence (df 2) and every cell holds about a
/// sixth; the same for x2 (4 arms) x margin (2 arms)
#[test]
fn two_experiments_assign_independently() {
    const N: u64 = 100_000;
    for (a, wa, b, wb) in [("x4", 3usize, "size", 2usize), ("x2", 4, "margin", 2), ("x4", 3, "margin", 2)] {
        let (va, vb) = (vec![1.0; wa], vec![1.0; wb]);
        let mut t = vec![vec![0u64; wb]; wa];
        for id in 0..N { t[assign(7, a, id, &va)][assign(7, b, id, &vb)] += 1; }
        let rows: Vec<u64> = t.iter().map(|r| r.iter().sum()).collect();
        let cols: Vec<u64> = (0..wb).map(|j| t.iter().map(|r| r[j]).sum()).collect();
        let mut c = 0.0;
        for i in 0..wa {
            for j in 0..wb {
                let e = rows[i] as f64 * cols[j] as f64 / N as f64;
                c += (t[i][j] as f64 - e).powi(2) / e;
                let share = t[i][j] as f64 / N as f64;
                assert!((share - 1.0 / (wa * wb) as f64).abs() < 0.01, "{a} x {b}: cell ({i},{j}) {share}");
            }
        }
        let df = (wa - 1) * (wb - 1);
        assert!(c < CHI2_999[df], "{a} x {b}: {t:?} chi2 {c:.2} (df {df})");
    }
}

/// The scopes: the bands up to `max_band`, the evaluation kinds, a route with a leg on a listed venue; unknown names
/// refused
#[test]
fn scopes_parse_and_cover() {
    let s = Scope::parse("x4", 2, &[], &[]).unwrap();
    assert_eq!(s, Scope { max_band: 2, ..Scope::ALL });
    assert!(s.covers(0, "commit", Venue::Dlmm, Venue::PumpSwap) && s.covers(2, "fork", Venue::Dlmm, Venue::PumpSwap) && !s.covers(3, "commit", Venue::Dlmm, Venue::Dlmm));
    let s = Scope::parse("x2", 4, &["commit".into(), "quiescent".into()], &["DLMM".into()]).unwrap();
    assert!(s.route_ok("commit", Venue::Dlmm, Venue::PumpSwap) && s.route_ok("quiescent", Venue::PumpSwap, Venue::Dlmm));
    assert!(!s.route_ok("timeout", Venue::Dlmm, Venue::Dlmm) && !s.route_ok("commit", Venue::PumpSwap, Venue::RayCpmm) && !s.kind_ok("probe"));
    assert_eq!(s.json(), json!({ "max_band": 4, "kinds": ["commit", "quiescent"], "venues": ["DLMM"] }));
    assert_eq!(Scope::ALL.json()["venues"].as_array().unwrap().len(), 7);
    assert!(Scope::parse("x2", 5, &[], &[]).is_err() && Scope::parse("x2", 4, &["state".into()], &[]).is_err() && Scope::parse("x2", 4, &[], &["Dlmm".into()]).is_err());
}

/// What a decision's arms say where: decisions record every assigned arm, attempts the ones that applied (in scope);
/// X4's share reaches the tip model with its band limit; the size cap in lamports
#[test]
fn arms_apply_in_scope_and_record() {
    let x = Experiments { seed: 1, x2: Some(Exp { arms: vec![0, 20], weights: vec![1.0, 1.0], scope: Scope { max_band: 1, ..Scope::ALL } }),
        x4: Some(Exp { arms: vec![0.1, 0.35], weights: vec![1.0, 1.0], scope: Scope { max_band: 2, ..Scope::ALL } }),
        size: Some(Exp { arms: vec![0.05, 0.2], weights: vec![1.0, 1.0], scope: Scope::ALL }),
        margin: Some(Exp { arms: vec![1, 2_000], weights: vec![1.0, 1.0], scope: Scope::ALL }), ..Default::default() };
    let a = x.assign(5);
    let m = a.assigned_json();
    assert_eq!(m.keys().map(String::as_str).collect::<Vec<_>>(), vec!["margin", "size_max_sol", "x2_delay_ms", "x4_share"]);
    let (s, v) = (a.x4.unwrap().value, a.size.unwrap().value);
    assert_eq!(a.share_arm("commit", Venue::Dlmm, Venue::Dlmm), Some(ShareArm { share: s, max_band: 2 }));
    assert_eq!(a.size_cap("commit"), Some(sol_lamports(v)));
    assert_eq!((sol_lamports(0.05), sol_lamports(0.2), sol_lamports(0.0005)), (50_000_000, 200_000_000, 500_000));
    // band 3: X4 and X2 out of scope there (the tip model sees the arm and keeps the band's share); the margin arm all bands
    let att = a.applied_json(3, "commit", Venue::Dlmm, Venue::Dlmm, None);
    assert!(att.get("x4_share").is_none() && att.get("x2_delay_ms").is_none() && att["margin"].is_u64() && att["size_max_sol"].is_f64(), "{att}");
    let att = a.applied_json(1, "commit", Venue::Dlmm, Venue::Dlmm, Some(s));
    assert_eq!((att["x4_share"].as_f64(), att["x2_delay_ms"].as_u64().is_some()), (Some(s), true));
    assert_eq!(Arms::default().assigned_json().len(), 0, "off: decisions record `experiments` empty, as before");
    assert!(Arms::default().is_empty() && Arms::default().share_arm("commit", Venue::Dlmm, Venue::Dlmm).is_none());
    // the compiled experiments read back (engine_init: a replay assigns as the run did)
    let back: Experiments = serde_json::from_value(serde_json::to_value(&x).unwrap()).unwrap();
    assert_eq!(back, x);
    assert_eq!(back.assign(5), a);
    assert!(x.valid());
    // a record read back with an arm out of bounds, or a weight missing, is not whole (engine_init refuses it)
    for bad in [Experiments { x4: Some(Exp { arms: vec![0.1, 1.5], ..x.x4.clone().unwrap() }), ..x.clone() },
        Experiments { margin: Some(Exp { arms: vec![0, 2_000], ..x.margin.clone().unwrap() }), ..x.clone() },
        Experiments { x2: Some(Exp { arms: vec![0, 25], ..x.x2.clone().unwrap() }), ..x.clone() },
        Experiments { size: Some(Exp { weights: vec![1.0], ..x.size.clone().unwrap() }), ..x.clone() }] {
        assert!(!bad.valid(), "{bad:?}");
    }
}

/// X8's block assignment: a whole block on one arm, blocks balanced (10^4 ten-minute blocks)
#[test]
fn blocks_assign_whole_blocks() {
    let block = 600_000_000_000u64;
    let (id, arm, from, to) = block_of(3, "x8", 3 * block + 5, block, &[1.0, 1.0]);
    assert_eq!((id, from, to), (3, 3 * block, 4 * block));
    assert_eq!(block_of(3, "x8", 4 * block - 1, block, &[1.0, 1.0]).1, arm, "the same block, the same arm");
    let on = (0..10_000u64).filter(|b| block_of(3, "x8", b * block, block, &[1.0, 1.0]).1 == 1).count();
    assert!((4_800..5_200).contains(&on), "{on}");
    let l = block_switch_json(9, "x8", 3, (id, arm, from, to), json!("on"));
    assert_eq!((l["event"].as_str(), l["block"]["from_ns"].as_u64(), l["block"]["arm"].as_str()), (Some("block_switch"), Some(from), Some("on")));
}

/// `Config::parse` refuses what would make an experiment meaningless or unsafe: one arm, a repeated arm, a weight per
/// arm missing or not positive, a share outside 0..1, a delay over 20 ms, a size arm above a static cap or the ladder or
/// below its smallest rung, a margin floor of 0, unknown scope names, X8 (WP-14 not built); disabled tables are not
/// checked (they change nothing)
#[test]
fn config_checks() {
    let ok = format!("{LADDER}{CAPS}[experiments]\nseed = 7\n[experiments.x4]\nenabled = true\narms = [0.1, 0.2, 0.35]\n[experiments.size]\nenabled = true\narms_max_sol = [0.05, 0.2]\n");
    let c = cfg(&ok).unwrap();
    let x = c.experiments.compile().unwrap();
    assert_eq!((x.seed, x.x4.as_ref().unwrap().weights.clone(), x.x4.as_ref().unwrap().scope.max_band, x.size.as_ref().unwrap().arms.clone()),
        (7, vec![1.0; 3], 2, vec![0.05, 0.2]));
    assert!(x.x2.is_none() && x.margin.is_none());
    let d = c.experiments.describe(&c);
    assert!(d.starts_with("experiments (WP-11): seed 7 (mixed with each segment's name); x4 tip share arms [0.1, 0.2, 0.35] (control 0.1;") && d.contains("(6 cells)")
        && d.contains("bands 0-2 (edge < 1000000)") && d.contains("size cap arms [0.05, 0.2] SOL (control 0.05;"), "{d}");
    for (bad, why) in [
        ("[experiments.x4]\nenabled = true\narms = [0.2]\n", "2 to 8"),
        ("[experiments.x4]\nenabled = true\narms = [0.2, 0.2]\n", "twice"),
        ("[experiments.x4]\nenabled = true\narms = [0.2, 1.5]\n", "0..1"),
        ("[experiments.x4]\nenabled = true\narms = [0.2, 0.3]\nweights = [1]\n", "one per arm"),
        ("[experiments.x4]\nenabled = true\narms = [0.2, 0.3]\nweights = [1, 0]\n", "each > 0"),
        ("[experiments.x4]\nenabled = true\narms = [0.2, 0.3]\nweights = [1e308, 1e308]\n", "at most 1e9"),
        ("[experiments.x4]\nenabled = true\narms = [0.2, 0.3]\nscope_max_band = 5\n", "scope_max_band"),
        ("[experiments.x2]\nenabled = true\narms_ms = [0, 25]\n", "above 20 ms"),
        ("[experiments.x2]\nenabled = true\nscope_kinds = [\"probe\"]\n", "scope_kinds"),
        ("[experiments.x2]\nenabled = true\nscope_venues = [\"Orca\"]\n", "scope_venues"),
        ("[experiments.size]\nenabled = true\narms_max_sol = [0.05, 0.3]\n", "top rung"),
        ("[experiments.size]\nenabled = true\narms_max_sol = [0.0001, 0.2]\n", "smallest rung"),
        ("[experiments.margin]\nenabled = true\narms = [0, 2000]\n", ">= 1"),
        ("[experiments.x8]\nenabled = true\n", "WP-14"),
        ("[experiments.x4]\nenabled = true\nscope = 2\n", "unknown field"),
    ] {
        let e = cfg(&format!("{LADDER}{CAPS}{bad}")).expect_err(bad);
        assert!(e.contains(why), "{bad}: {e}");
    }
    // the static caps: a size arm above [live] max_size_sol, or [canary] size_sol with the canary on
    let e = cfg(&format!("{LADDER}[canary]\nenabled = true\nsize_sol = 0.05\n[live]\nmax_size_sol = 0.2\n[experiments.size]\nenabled = true\n")).unwrap_err();
    assert!(e.contains("above [canary] size_sol 0.05"), "{e}");
    let e = cfg(&format!("{LADDER}[live]\nmax_size_sol = 0.1\n[experiments.size]\nenabled = true\n")).unwrap_err();
    assert!(e.contains("above [live] max_size_sol 0.1"), "{e}");
    assert!(cfg(&format!("{LADDER}[live]\nmax_size_sol = 0.2\n[experiments.size]\nenabled = true\n")).is_ok(), "no canary: [live]'s cap");
    // a disabled table is not checked, compiles to nothing, and an enabled-but-off seed alone is off
    let c = cfg(&format!("{LADDER}[experiments]\nseed = 9\n[experiments.x4]\narms = [5.0]\n[experiments.x8]\nblock_min = 0\n")).unwrap();
    assert!(c.experiments.off() && c.experiments.compile().is_none());
    assert!(c.experiments.describe(&c).starts_with("experiments (WP-11): off"));
}

/// With experiments off, a config hashes as before WP-11: `[experiments]` (a seed, disabled tables with values) is left
/// out of the normalized JSON (meta.json `config.normalized_sha256`), so every deploy config's hash is unchanged; an
/// enabled table changes it. The executor's config hash (exec_init `cfg_sha256`) never reads `[experiments]`: the arms
/// reach the executor with each decision, from the engine, whose engine_init journals them
#[test]
fn off_hashes_as_before() {
    let base = cfg(LADDER).unwrap();
    let off = cfg(&format!("{LADDER}[experiments]\nseed = 123\n[experiments.x4]\narms = [0.1, 0.35]\n[experiments.size]\nenabled = false\narms_max_sol = [0.05]\n")).unwrap();
    assert_eq!(base.normalized_sha256(), off.normalized_sha256());
    assert!(!base.normalized_json().contains("experiments"));
    assert_eq!(crate::exec::cfg_sha256(&base), crate::exec::cfg_sha256(&off));
    let on = cfg(&format!("{LADDER}[live]\nmax_size_sol = 0.2\n[experiments]\nseed = 123\n[experiments.x4]\nenabled = true\narms = [0.1, 0.35]\n")).unwrap();
    let on_base = cfg(&format!("{LADDER}[live]\nmax_size_sol = 0.2\n")).unwrap();
    assert_ne!(on.normalized_sha256(), on_base.normalized_sha256(), "an enabled experiment is part of the run's config");
    assert!(on.normalized_json().contains("\"x4\"") && !on.normalized_json().contains("\"x2\""), "only the enabled tables");
    assert_eq!(crate::exec::cfg_sha256(&on), crate::exec::cfg_sha256(&on_base));
    // every shipped config but the experiment example has none: its hash is the one it had before WP-11
    let dir = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy");
    let mut n = 0;
    for f in std::fs::read_dir(&dir).unwrap().flatten().filter(|f| f.path().extension().is_some_and(|e| e == "toml")) {
        let text = std::fs::read_to_string(f.path()).unwrap();
        let c = Config::parse(&text).unwrap_or_else(|e| panic!("{}: {e:#}", f.path().display()));
        let has = !c.experiments.off();
        assert_eq!(has, text.contains("[experiments"), "{}", f.path().display());
        if !has { assert!(!c.normalized_json().contains("\"experiments\""), "{}", f.path().display()); n += 1; }
    }
    assert!(n >= 9, "{n} configs without experiments");
}

/// Review #5: each segment mixes its name into the seed (decision ids restart each segment, so one id-to-arm pattern
/// would repeat in every segment of a campaign): two segments' patterns differ, one segment's is reproducible, the
/// config's seed and the name stay recorded, and mixing twice is mixing once (a replay's engine_init carries the mixed
/// seed). The first arm is the control in experiments.jsonl
#[test]
fn each_segment_mixes_its_name_into_the_seed() {
    let base = Experiments { seed: 20_261_007, x4: Some(Exp { arms: vec![0.2, 0.1, 0.35], weights: vec![1.0; 3], scope: Scope { max_band: 2, ..Scope::ALL } }),
        ..Default::default() };
    let (p1, p2) = (base.clone().for_run("ft-x4size-p1"), base.clone().for_run("ft-x4size-p2"));
    assert_ne!(p1.seed, p2.seed);
    assert_eq!((p1.config_seed, p1.run.as_deref()), (Some(20_261_007), Some("ft-x4size-p1")));
    assert_eq!(p1.clone().for_run("ft-x4size-p1"), p1, "the config's seed is mixed once");
    assert_eq!(base.clone().for_run("ft-x4size-p1"), p1, "reproducible");
    let same = (0..10_000u64).filter(|id| p1.assign(*id).x4.unwrap().idx == p2.assign(*id).x4.unwrap().idx).count();
    assert!((3_000..3_700).contains(&same), "two segments' patterns agree by chance only (1/3): {same}");
    let back: Experiments = serde_json::from_value(serde_json::to_value(&p1).unwrap()).unwrap();
    assert_eq!(back, p1);
    let l = &p1.config_lines(1)[0];
    assert_eq!((l["control"].as_f64(), l["seed"].as_u64(), l["config_seed"].as_u64(), l["run"].as_str()), (Some(0.2), Some(p1.seed), Some(20_261_007), Some("ft-x4size-p1")));
}

/// Review #2: status.jsonl's per-arm counters: every decision once per experiment under its arm; an opportunity sent,
/// a would-send, or refused by its reason (before any `:`); labels as the records print the arms
#[test]
fn arm_counters_count_each_decision_once() {
    let x = Experiments { seed: 3, x4: Some(Exp { arms: vec![0.2, 0.1], weights: vec![1.0; 2], scope: Scope::ALL }),
        size: Some(Exp { arms: vec![0.05, 0.2], weights: vec![1.0; 2], scope: Scope::ALL }), ..Default::default() };
    let mut st = ArmStats::default();
    assert!(st.json(&x).is_none());
    let mut want = std::collections::BTreeMap::new();
    for id in 0..1_000u64 {
        let a = x.assign(id);
        let (opp, sent, would, reason) = match id % 4 { 0 => (false, false, false, "below_min_profit"), 1 => (true, true, false, "sent"),
            2 => (true, false, false, "canary_wait"), _ => (true, false, true, "would_send") };
        st.note(&a, opp, sent, would, if id % 8 == 6 { "gate_shadow:paused" } else { reason });
        *want.entry(a.x4.unwrap().idx).or_insert(0u64) += 1;
    }
    let j = st.json(&x).unwrap();
    assert_eq!(j["x4_share"]["0.2"]["decisions"].as_u64(), Some(want[&0]));
    assert_eq!(j["x4_share"]["0.1"]["decisions"].as_u64(), Some(want[&1]));
    for key in ["x4_share", "size_max_sol"] {
        let arms: Vec<&Value> = j[key].as_object().unwrap().values().collect();
        assert_eq!(arms.iter().map(|a| a["decisions"].as_u64().unwrap()).sum::<u64>(), 1_000);
        assert_eq!(arms.iter().map(|a| a["opportunities"].as_u64().unwrap()).sum::<u64>(), 750);
        assert_eq!(arms.iter().map(|a| a["sent"].as_u64().unwrap()).sum::<u64>(), 250);
        assert_eq!(arms.iter().map(|a| a["would_send"].as_u64().unwrap()).sum::<u64>(), 250);
        assert_eq!(arms.iter().map(|a| a["refused"]["canary_wait"].as_u64().unwrap_or(0) + a["refused"]["gate_shadow"].as_u64().unwrap_or(0)).sum::<u64>(), 250);
    }
    assert!(j.get("x2_delay_ms").is_none() && j.get("margin").is_none(), "only the experiments on");
}

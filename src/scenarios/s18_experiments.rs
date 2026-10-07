//! S18 (PLAN WP-11 offline acceptance: arms recorded, applied where intended, replayed). A canary run on real USDC/SOL
//! pools with four experiments on at once (`[experiments.x4]` tip share, `[experiments.size]` size cap,
//! `[experiments.margin]` on-chain margin floor, `[experiments.x2]` send delay), its bundles sent to a block engine in
//! memory (nothing leaves the process):
//! - every decision records its assigned arms (decisions.jsonl `experiments`): the hash of its id, recomputed here;
//! - the engine priced each route under its size arm (the decision's size within the arm's cap) and its X4 share (the
//!   decision's net is the executor's: `ev`); the attempt sends the decision's size (the decision priced is the trade
//!   sent);
//! - every attempt records the arms that applied (attempts.jsonl `experiments`, `tip.arm`) and carries them: the tip is
//!   the arm's share of the edge within `[tips]`' floor and cap, the on-chain min_profit's margin the arm's floor, and the
//!   copy leaves the arm's delay after the fire was handed over (the delay sleeps on the send task: the engine thread
//!   returned at once);
//! - experiments.jsonl holds each experiment's configuration;
//! - the replay reproduces every decision (their arms included), every attempt and the digests.
use super::s13_verdicts::{canary_rig, usdc_sale};
use super::*;
use crate::experiments::{assign, sol_lamports};

const POOLS3: [&str; 3] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4"];
const SEED: u64 = 20_261_007;
const EXP: &str = "[experiments]\nseed = 20261007\n\
    [experiments.x4]\nenabled = true\narms = [0.1, 0.35]\nscope_max_band = 4\n\
    [experiments.size]\nenabled = true\narms_max_sol = [0.01, 0.05]\n\
    [experiments.margin]\nenabled = true\narms = [1, 2000]\n\
    [experiments.x2]\nenabled = true\narms_ms = [0, 5]\n\n[bands]\n";
const CONFIG: [(&str, &str); 4] = [CANARY[0], CANARY[1], ("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0"), ("[bands]\n", EXP)];

#[test]
fn s18_arms_are_applied_recorded_and_replayed() {
    let (mut r, s2) = canary_rig("s18", &POOLS3, &CONFIG, true);
    let metas: Vec<PoolMeta> = POOLS3.iter().map(|n| r.meta(n)).collect();
    let mut t = T0 + 10 * MS;
    let mut pumped = 0;
    for k in 0..12usize {
        let sig = r.sig(&format!("S18-{k}"));
        usdc_sale(&mut r, &metas[k % 3], [60, 80, 100][k % 3], sig, s2, &mut t);
        r.timers(t + 4 * MS);
        t += 5 * MS;
        // the fire's result of every attempt this sale made, handed back to the engine
        let n = r.attempts().len() - pumped;
        if n > 0 { r.pump(n, t); pumped += n; }
        t += MS;
    }
    let decisions = r.evaluations();
    let attempts = r.attempts();
    eprintln!("S18: {} evaluations, {} attempts", decisions.len(), attempts.len());
    assert!(attempts.len() >= 6, "the sales were sent: {}", attempts.len());
    // the seed the run assigns with: the config's mixed with the run's name (review #5), as experiments.jsonl records it
    let seed = crate::experiments::Experiments { seed: SEED, ..Default::default() }.for_run("s18").seed;
    assert_ne!(seed, SEED);
    // every decision: its arms are the hash of its id
    let arm = |name: &str, id: u64, arms: &[Value]| arms[assign(seed, name, id, &vec![1.0; arms.len()])].clone();
    let mut seen: std::collections::BTreeSet<(String, String)> = Default::default();
    for d in &decisions {
        let id = d["decision"].as_u64().unwrap();
        let want = json!({ "x4_share": arm("x4", id, &[json!(0.1), json!(0.35)]), "size_max_sol": arm("size", id, &[json!(0.01), json!(0.05)]),
            "margin": arm("margin", id, &[json!(1), json!(2000)]), "x2_delay_ms": arm("x2", id, &[json!(0), json!(5)]) });
        assert_eq!(d["experiments"], want, "decision {id}");
        // the size search under the arm: every priced route within its cap
        let cap = sol_lamports(d["experiments"]["size_max_sol"].as_f64().unwrap());
        for rt in d["routes"].as_array().unwrap() { if let Some(sz) = rt["size"].as_u64() { assert!(sz <= cap, "decision {id}: a route priced at {sz} over its arm's {cap}"); } }
    }
    let by_id: HashMap<u64, &Value> = decisions.iter().map(|d| (d["decision"].as_u64().unwrap(), d)).collect();
    let copies = r.lines("copies");
    let mut delayed = 0;
    for a in &attempts {
        let d = by_id[&a["decision"].as_u64().unwrap()];
        let x = &d["experiments"];
        let best = &d["routes"][d["best"].as_u64().unwrap() as usize];
        for (k, v) in x.as_object().unwrap() { seen.insert((k.clone(), v.to_string())); }
        // the decision priced is the trade sent, at the same net (the engine's fee read the same X4 arm as the tip)
        assert_eq!(a["size_lamports"], best["size"], "attempt {}: the decision's size", a["attempt"]);
        assert_eq!((d["ev"].as_i64(), a["expected"]["net"].as_i64()), (best["net"].as_i64(), best["net"].as_i64()), "attempt {}: one net", a["attempt"]);
        // every arm applied (x4 in every band here), the tip the arm's share of the edge within the floor and cap; the
        // assigned arms recorded beside them (review #10)
        assert_eq!(a["experiments"], *x, "attempt {}", a["attempt"]);
        assert_eq!(a["experiments_assigned"], *x, "attempt {}", a["attempt"]);
        let share = x["x4_share"].as_f64().unwrap();
        let edge = a["expected"]["gross"].as_i64().unwrap() - 5_000;
        assert_eq!((a["tip"]["arm"].as_f64(), a["tip"]["share"].as_f64(), a["tip"]["policy"].as_str()), (Some(share), Some(share), Some("share_of_edge")), "{a}");
        assert_eq!(a["tip"]["lamports"].as_u64(), Some(((edge as f64 * share) as u64).clamp(1_000, 100_000)), "attempt {}", a["attempt"]);
        // the margin arm's floor (margin_share 0): min_profit = tip + base fee + the floor
        let floor = x["margin"].as_u64().unwrap();
        assert_eq!((a["margin"].as_u64(), a["min_profit_onchain"].as_u64()), (Some(floor), Some(a["tip"]["lamports"].as_u64().unwrap() + 5_000 + floor)), "{a}");
        // the delay arm: a copy that left (the test path's 5 sends a second drops some: `t_sent` 0) left at least that long
        // after the fire was handed to the runtime
        let delay = x["x2_delay_ms"].as_u64().unwrap() * MS;
        let c = copies.iter().find(|c| c["attempt"] == a["attempt"]).expect("its copy");
        let (sent, handed) = (c["t_sent"].as_u64().unwrap(), a["stages"]["t_enqueued"].as_u64().unwrap());
        if sent > 0 {
            assert!(sent >= handed + delay, "attempt {}: sent {} ms after the fire, its arm {} ms", a["attempt"], (sent as f64 - handed as f64) / 1e6, delay / MS);
            delayed += (delay > 0) as u32;
        }
    }
    assert!(delayed >= 1, "a delayed copy left and was checked");
    for (k, arms) in [("x4_share", ["0.1", "0.35"]), ("size_max_sol", ["0.01", "0.05"]), ("margin", ["1", "2000"]), ("x2_delay_ms", ["0", "5"])] {
        for v in arms { assert!(seen.contains(&(k.to_string(), v.to_string())), "{k} = {v} among the attempts: {seen:?}"); }
    }
    // experiments.jsonl: each experiment's configuration
    let cfg_lines = r.lines("experiments");
    let names: Vec<(&str, &str)> = cfg_lines.iter().map(|l| (l["experiment"].as_str().unwrap(), l["key"].as_str().unwrap())).collect();
    assert_eq!(names, vec![("x2", "x2_delay_ms"), ("x4", "x4_share"), ("size", "size_max_sol"), ("margin", "margin")]);
    assert!(cfg_lines.iter().all(|l| l["event"] == "config" && l["seed"] == json!(seed) && l["config_seed"] == json!(SEED) && l["run"] == "s18"
        && l["unit"] == "decision" && l["control"] == l["arms"][0]), "{cfg_lines:?}");
    assert_eq!((cfg_lines[1]["arms"].clone(), cfg_lines[1]["weights"].clone(), cfg_lines[1]["scope"]["max_band"].clone(), cfg_lines[1]["control"].clone()),
        (json!([0.1, 0.35]), json!([1.0, 1.0]), json!(4), json!(0.1)));
    // status.jsonl `experiments` (review #2): each arm's decisions, opportunities, sends; the decisions per arm are the
    // decision records'
    r.timers(t + 11_000 * MS);
    let st = r.lines("status");
    let last = st.iter().rev().find(|l| l.get("experiments").is_some()).expect("a status line with the arms' counters");
    let ex = &last["experiments"];
    for (key, arms) in [("x4_share", ["0.1", "0.35"]), ("size_max_sol", ["0.01", "0.05"]), ("margin", ["1", "2000"]), ("x2_delay_ms", ["0", "5"])] {
        let n: u64 = arms.iter().map(|a| ex[key][*a]["decisions"].as_u64().unwrap_or(0)).sum();
        assert_eq!(n, decisions.len() as u64, "{key}: every decision counted once: {ex}");
        for a in arms {
            let want = decisions.iter().filter(|d| d["experiments"][key].to_string() == a).count() as u64;
            assert_eq!(ex[key][a]["decisions"].as_u64(), Some(want), "{key} = {a}: {ex}");
            let sent = attempts.iter().filter(|x| by_id[&x["decision"].as_u64().unwrap()]["experiments"][key].to_string() == a).count() as u64;
            assert_eq!(ex[key][a]["sent"].as_u64(), Some(sent), "{key} = {a}: {ex}");
        }
    }
    // the replay: every decision (its arms), every attempt, the digests
    let done = r.finish_and_replay();
    assert_eq!(done.replay["executor"]["exec_init"]["mode"].as_str(), Some("canary"));
}

/// S18b: the size arm under the bankroll. The same canary run with `[live] bankroll_share = 0.85`, a 0.03 SOL reserve and
/// a wallet holding 1 SOL and 0.012 SOL of WSOL: the bankroll allows 0.012 SOL a trade (at most the WSOL), between the
/// size arms 0.01 and 0.05. From the first decision-point record on, the engine prices a 0.05-arm decision within the
/// bankroll's 0.012 SOL (on the record's money view; these gaps peak near 0.014 SOL, so it binds) and the attempt sends
/// the size priced; a 0.01-arm decision prices within 0.01 SOL. The replay prices on the same journaled view and
/// reproduces every decision and attempt
#[test]
fn s18b_the_size_arm_prices_under_the_bankroll_and_replays() {
    use crate::exec::Mode;
    const BANKROLL: [(&str, &str); 5] = [CANARY[0], CANARY[1], ("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0"), ("[bands]\n", EXP),
        ("margin_lamports = 1000 ", "bankroll_share = 0.85\nbankroll_reserve_sol = 0.03\nmargin_lamports = 1000 ")];
    let mut r = Rig::new("s18b", Setup { pools: &POOLS3, config: &BANKROLL, exec: Some(ExecSetup { mode: Mode::Canary, sticky_shadow: false, hold_tokens: true, ..Default::default() }),
        ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 400], T0 + 7 * MS);
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    r.snapshot(s2, SOL, 12_000_000, None, "start", T0 + 9 * MS);
    let metas: Vec<PoolMeta> = POOLS3.iter().map(|n| r.meta(n)).collect();
    let mut t = T0 + 10 * MS;
    let mut pumped = 0;
    for k in 0..12usize {
        let sig = r.sig(&format!("S18b-{k}"));
        usdc_sale(&mut r, &metas[k % 3], [60, 80, 100][k % 3], sig, s2, &mut t);
        r.timers(t + 4 * MS);
        t += 5 * MS;
        let n = r.attempts().len() - pumped;
        if n > 0 { r.pump(n, t); pumped += n; }
        t += MS;
    }
    let opps = r.opportunities();
    let attempts = r.attempts();
    assert!(attempts.len() >= 6, "{} attempts", attempts.len());
    let by_id: HashMap<u64, &Value> = opps.iter().map(|d| (d["decision"].as_u64().unwrap(), d)).collect();
    let first = opps[0]["decision"].as_u64().unwrap();
    let (mut capped, mut small) = (0, 0);
    for a in &attempts {
        let d = by_id[&a["decision"].as_u64().unwrap()];
        let priced = d["routes"][d["best"].as_u64().unwrap() as usize]["size"].as_u64().unwrap();
        let size = a["size_lamports"].as_u64().unwrap();
        let arm = sol_lamports(d["experiments"]["size_max_sol"].as_f64().unwrap());
        assert!(size <= 12_000_000 && size <= arm, "attempt {}: {size} past the bankroll or its arm {arm}", a["attempt"]);
        if d["decision"].as_u64() != Some(first) {
            assert_eq!(size, priced, "attempt {}: the decision priced is the trade sent", a["attempt"]);
            for rt in d["routes"].as_array().unwrap() { if let Some(x) = rt["size"].as_u64() { assert!(x <= arm.min(12_000_000), "a route priced at {x}"); } }
            if arm > 12_000_000 { capped += (priced == 12_000_000) as u32; } else { small += 1; }
        }
    }
    eprintln!("S18b: sizes (decision, arm, priced, sent) {:?}", attempts.iter().map(|a| { let d = by_id[&a["decision"].as_u64().unwrap()];
        (d["decision"].clone(), d["experiments"]["size_max_sol"].clone(), d["routes"][d["best"].as_u64().unwrap() as usize]["size"].clone(), a["size_lamports"].clone()) }).collect::<Vec<_>>());
    assert!(capped >= 1 && small >= 1, "both arms past the first decision: {capped} priced at the bankroll's cap, {small} within 0.01 SOL");
    let done = r.finish_and_replay();
    assert_eq!(done.replay["executor"]["exec_init"]["mode"].as_str(), Some("canary"));
}

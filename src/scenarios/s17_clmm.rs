//! S17 (PLAN-ADDENDUM WP-21): a run whose registry trades Raydium CLMM and Orca Whirlpool pools replays identically. The
//! USDC/SOL pair with the scenarios' PumpSwap and CPMM pools and the venue harness's Raydium CLMM 3ucN and Orca Whirlpool
//! Czfq snapshots (`CLMM_POOLS`), the CLMM switches on as deploy/arbx-wp21-shadow.toml has them (`quote`), a shadow
//! executor:
//! - the boot follows each CLMM pool's tick arrays (`initial_dlmm_arrays`; role `clmm_tick_array` in registry-run.json
//!   and accounts.bin) and holds the accounts that do not exist empty, as `arbx run`'s boot records them;
//! - the stream delivers real swaps' post-states of both CLMM pools (testdata/venue-parity/real-swaps-clmm.json: what the
//!   deployed programs left, word for word) and a USDC sale into the PumpSwap pool; each commit group is evaluated and
//!   routes with Raydium CLMM and Orca Whirlpool legs are priced by arbx-sizing (the Whirlpool's Clock raised to its
//!   stamps: the CLMM snapshots are newer than the scenarios' Clock); the would-sends' bundles are built with their
//!   `swap_v2` legs;
//! - the replay (`finish_and_replay`) gives the run's decisions, commit groups, attempts and digests.
use super::*;

/// the CLMM venues on, as the WP-21 shadow config has them; the ≥1M class's throttle lifted (S11 tests it)
const CLMM_QUOTE: [(&str, &str); 2] = [("registry_all = true", "registry_all = true\nrayclmm = \"quote\"\nwhirlpool = \"quote\""),
    ("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0")];

/// A real swap's post-state on `pool` (real-swaps-clmm.json: the snapshot case, direction `dir`, the `rung`-th size of its
/// exact-in ladder): each account it changed, the chain's bytes with the changed words
fn real_post(r: &Rig, pool: &Pk, dir: &str, rung: usize) -> Vec<(Pk, Vec<u8>)> {
    let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata/venue-parity/real-swaps-clmm.json");
    let v: Value = serde_json::from_slice(&std::fs::read(&path).unwrap()).unwrap();
    let p58 = b58(pool);
    let s = v["swaps"].as_array().unwrap().iter()
        .filter(|s| s["pool"] == json!(p58) && s["case"] == "snapshot" && s["dir"] == dir && s["exact_out"] == json!(false) && s["ok"] == json!(true))
        .nth(rung).unwrap_or_else(|| panic!("no real swap {p58} {dir} #{rung}"));
    s["post"].as_array().unwrap().iter().map(|a| {
        let k = pk(a["key"].as_str().unwrap());
        let mut d = r.data(&k);
        for w in a["words"].as_array().unwrap() { put_u64(&mut d, w[0].as_u64().unwrap() as usize, w[1].as_u64().unwrap()); }
        (k, d)
    }).collect()
}

#[test]
fn s17_a_run_with_clmm_pools_replays_identically() {
    let names = ["usdc.pump", "usdc.cpmm", "usdc.rayclmm", "usdc.whirl"];
    let mut r = Rig::new("s17", Setup { pools: &names, config: &CLMM_QUOTE, exec: Some(ExecSetup::default()), ..Default::default() });
    let (ray, whirl, pump) = (r.meta("usdc.rayclmm"), r.meta("usdc.whirl"), r.meta("usdc.pump"));
    assert_eq!((ray.venue, whirl.venue), (Venue::RayClmm, Venue::Whirlpool));
    assert_eq!(r.reg.pairs.len(), 1, "one USDC/SOL pair of four pools");
    // the boot follows the CLMM pools' tick arrays (accounts.bin's role `clmm_tick_array`, the pool's index) and holds the
    // ones the snapshot has (Raydium's two outermost followed arrays are not in the venue harness's capture: unread, as an
    // RPC answer that never came)
    for m in [&ray, &whirl] {
        let l = r.e.store.dlmm_arrays.get(&m.pool).cloned().unwrap_or_default();
        let held: Vec<i64> = l.iter().filter(|(_, k)| r.e.store.get(k).is_some()).map(|x| x.0).collect();
        eprintln!("S17 {}: follows {:?}, the boot snapshot holds {held:?}", nm(&m.pool), l.iter().map(|x| x.0).collect::<Vec<_>>());
        assert!(held.len() + 2 >= l.len() && held.len() >= 6, "{}: the boot snapshot holds the followed arrays", nm(&m.pool));
        let idx = r.reg.by_pool[&m.pool] as u32;
        assert!(l.iter().all(|(_, k)| r.ar.roles().get(k) == Some(RoleOf { role: accounts::role::CLMM_TICK_ARRAY, pool_index: idx })), "{}: their role", nm(&m.pool));
    }
    // Czfq has no oracle (an account that does not exist): held empty, as the boot records it
    let oracle = *whirl.whirl_oracle().unwrap();
    assert!(r.e.store.get(&oracle).is_some_and(|a| a.data.is_empty()), "the Whirlpool's oracle is known not to exist");
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    let mut t = T0 + 10 * MS;
    // 1. a real swap on the Whirlpool (USDC in), then one on Raydium CLMM (SOL in), each its own transaction
    for (m, dir, rung, label) in [(&whirl, "1->0", 6, "S17-whirl"), (&ray, "0->1", 5, "S17-ray")] {
        let sig = r.sig(label);
        for (k, d) in real_post(&r, &m.pool, dir, rung) { r.write(k, d, s2, Some(sig), t); t += 100 * US; }
        r.timers(t + 4 * MS);
        t += 6 * MS;
    }
    // 2. a USDC sale into the PumpSwap pool
    let sale = r.sig("S17-pump");
    super::s13_verdicts::usdc_sale(&mut r, &pump, 40, sale, s2, &mut t);
    r.timers(t + 4 * MS);
    let ev = r.evaluations();
    assert_eq!(ev.len(), 3, "each transaction's group evaluated");
    // every ordered route of the pair through a CLMM pool is priced (a size and a gross), none refused unquotable
    for p in [&ray.pool, &whirl.pool] {
        let through: Vec<&Value> = ev.iter().flat_map(|d| routes_through(d, p)).collect();
        assert!(through.len() >= 6, "{}: {} routes", nm(p), through.len());
        for x in &through {
            assert!(x["size"].as_u64().is_some_and(|s| s > 0) && x["gross"].is_i64(), "{}: {x}", nm(p));
            assert!(!x["reason"].as_str().unwrap().starts_with("unquotable"), "{}: {x}", nm(p));
        }
    }
    // the USDC sale opens a gap: the best route buys on PumpSwap and sells on the Whirlpool, a would-send whose bundle the
    // shadow executor built with the Whirlpool's swap_v2 leg
    let sent: Vec<Value> = r.opportunities().into_iter().filter(|d| d["attempt"].is_u64()).collect();
    assert_eq!(sent.len(), 1, "one would-send");
    let b = &sent[0]["routes"][sent[0]["best"].as_u64().unwrap() as usize];
    assert_eq!((nm(&pk(b["buy"].as_str().unwrap())), nm(&pk(b["sell"].as_str().unwrap()))), ("usdc.pump".to_string(), "usdc.whirl".to_string()), "{b}");
    let attempts = r.attempts();
    assert_eq!(attempts.len(), 1);
    assert!(attempts[0]["tx"]["cu_limit"].as_u64().is_some_and(|c| c > 0), "{}", attempts[0]["tx"]);
    let done = r.finish_and_replay();
    assert_eq!(done.replay["compare"]["attempts_compared"].as_u64(), Some(attempts.len() as u64));
}

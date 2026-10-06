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

/// the canary's `[canary]` (`CANARY`: 0.2 SOL, no wait) with S17's switches
const CANARY_CLMM: [(&str, &str); 4] = [CANARY[0], CANARY[1], CLMM_QUOTE[0], CLMM_QUOTE[1]];
const POOLS4: [&str; 4] = ["usdc.pump", "usdc.cpmm", "usdc.rayclmm", "usdc.whirl"];

/// Review F3: in a run that sends, a route through a venue switched to "quote" is priced and recorded (`venue_quote_only`,
/// `route_quote_only`) but never the pick. S17's USDC sale into the PumpSwap pool, in a canary run: the shadow run's best
/// route (PumpSwap -> Whirlpool) is held back, the best route of the venues that send is decided and sent (one bundle to
/// the block engine in memory), and the replay gives the same decisions, attempt and digests
#[test]
fn s17_a_canary_sends_the_best_route_of_the_venues_that_send() {
    let (mut r, s2) = super::s13_verdicts::canary_rig("s17-canary", &POOLS4, &CANARY_CLMM, true);
    let (ray, whirl, pump) = (r.meta("usdc.rayclmm"), r.meta("usdc.whirl"), r.meta("usdc.pump"));
    let mut t = T0 + 10 * MS;
    let sale = r.sig("S17-pump");
    super::s13_verdicts::usdc_sale(&mut r, &pump, 40, sale, s2, &mut t);
    r.timers(t + 4 * MS);
    let ev = r.evaluations();
    let d = ev.last().unwrap();
    let through = |x: &Value, p: &Pk| x["buy"] == json!(b58(p)) || x["sell"] == json!(b58(p));
    let held: Vec<&Value> = d["routes"].as_array().unwrap().iter().filter(|x| through(x, &ray.pool) || through(x, &whirl.pool)).collect();
    eprintln!("S17 canary: {} routes, best {}, reason {}; the CLMM ones {:?}", d["routes"].as_array().unwrap().len(), d["best"], d["reason"],
        held.iter().map(|x| (nm(&pk(x["buy"].as_str().unwrap())), nm(&pk(x["sell"].as_str().unwrap())), x["reason"].clone(), x["gross"].clone())).collect::<Vec<_>>());
    assert!(held.len() >= 4, "{held:?}");
    for x in &held {
        assert_eq!(x["reason"].as_str(), Some("venue_quote_only"), "{x}");
        assert!(x["size"].as_u64().is_some_and(|s| s > 0) && x["gross"].is_i64(), "priced and recorded: {x}");
    }
    let b = &d["routes"][d["best"].as_u64().expect("a best route of the venues that send") as usize];
    assert!(!through(b, &ray.pool) && !through(b, &whirl.pool), "{b}");
    assert_eq!((d["reason"].as_str(), d["attempt"].as_u64()), (Some("sent"), Some(0)), "{d}");
    assert_eq!(r.bundles_sent().len(), 1, "one bundle reached the block engine");
    assert!(r.e.counter("route_quote_only") >= 4);
    let fired = r.pump(1, t + 5 * MS);
    assert_eq!(fired[0]["what"], "fired");
    let done = r.finish_and_replay();
    assert_eq!(done.replay["compare"]["attempts_compared"].as_u64(), Some(1));
}

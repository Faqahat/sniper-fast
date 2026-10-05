//! S9 (PLAN WP-09, after WP-05): the in-flight lock in a run with a shadow executor, and its replay. The lock is keyed
//! by (buy pool, sell pool, mint) and holds an attempt's state version, target slot and leader: the same state to the
//! same leader is refused (`inflight_same_state` at the same slot, `inflight_same_leader` at a later slot of the same
//! leader), a new state version or a new leader is allowed (the attempt's `inflight.why_allowed`: `new_state`,
//! `new_leader`). Each run is replayed: the replay's offline executor (built from the run's exec_init record, its send
//! checks reading the run's decision-point records) gives every verdict, every attempt and the digests the run gave.
//!
//! - **Same state blocked, new state allowed** (two pools, so that both evaluations price the same two routes): a
//!   rival's transaction writes both pools; its commit group evaluates both pools on one state, the second decision is
//!   refused by the lock; a later trade on one pool is a new state.
//! - **New leader allowed / same leader refused** (three pools): the same state is decided twice in two inputs. A trade
//!   moves the AMM v4 pool (its write set unknown: it resolves by quiescence, and its routes must be quiet); a trade on
//!   PumpSwap right after it makes the AMM v4 / PumpSwap routes not quiet, so that evaluation is deferred, while the
//!   AMM v4 / CPMM route is decided at once. The deferred evaluation runs a slot later on the same state: the same
//!   route, the same state version, the next slot's leader.
//!
//! The gate is shadow for the whole segment (`mode_shadow`, as `arbx run` without `--live` starts): every decision's
//! reason is `gate_shadow:mode_shadow`, and `reason_ungated` says what else refused it (null: a would-send).
use super::*;

/// a USDC sale of 1/`frac` of pool `m`'s USDC reserve by transaction `sig` at `slot` (its writes from `t`, 100 µs apart)
fn usdc_sale(r: &mut Rig, m: &PoolMeta, frac: u64, sig: [u8; 64], slot: u64, t: &mut u64) {
    let usdc_in = token_amount(&r.data(if sol_is_t0(m) { &m.vault1 } else { &m.vault0 })) / frac;
    let w = swap(&r.chain, m, !sol_is_t0(m), usdc_in, slot, r.unix0).0;
    for (k, d) in w { r.write(k, d, slot, Some(sig), *t); *t += 100 * US; }
}

/// S9 tests the lock, not the ≥1M class's throttle (S11): its rate is lifted
const NO_BAND_THROTTLE: [(&str, &str); 1] = [("big_band_max_per_sec = 0.5", "big_band_max_per_sec = 1000.0")];

/// the run's opportunity decisions as (decision, reason, reason_ungated, attempt, buy pool, sell pool, sv)
fn opps(r: &Rig) -> Vec<(u64, String, Option<String>, Option<u64>, String, String, String)> {
    r.opportunities().iter().map(|d| {
        let b = &d["routes"][d["best"].as_u64().unwrap() as usize];
        (d["decision"].as_u64().unwrap(), d["reason"].as_str().unwrap().to_string(), d["reason_ungated"].as_str().map(String::from), d["attempt"].as_u64(),
            nm(&crate::tx::pk(b["buy"].as_str().unwrap())), nm(&crate::tx::pk(b["sell"].as_str().unwrap())), d["sv"]["h"].as_str().unwrap_or("").to_string())
    }).collect()
}

#[test]
fn s9_same_state_blocked_new_state_allowed() {
    let mut r = Rig::new("s9", Setup { pools: &["usdc.ammv4", "usdc.cpmm"], config: &NO_BAND_THROTTLE, exec: Some(ExecSetup::default()), ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 64], T0 + 7 * MS);
    let (a, b) = (r.meta("usdc.ammv4"), r.meta("usdc.cpmm"));
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    // 1. a rival's transaction moves both pools: a large USDC sale into the AMM v4 pool, a small one into CPMM
    let both = r.sig("S9-both");
    let mut t = T0 + 10 * MS;
    usdc_sale(&mut r, &a, 40, both, s2, &mut t);
    usdc_sale(&mut r, &b, 4_000, both, s2, &mut t);
    r.timers(t + 4 * MS);
    let o = opps(&r);
    eprintln!("S9 after the two-pool transaction: {o:#?}");
    assert_eq!(o.len(), 2, "both pools evaluated, each an opportunity: {o:?}");
    let ((d1, r1, u1, a1, buy1, sell1, sv1), (_, r2, u2, a2, buy2, sell2, sv2)) = (o[0].clone(), o[1].clone());
    assert_eq!((buy1.as_str(), sell1.as_str(), &sv1), (buy2.as_str(), sell2.as_str(), &sv2), "the same route on the same state");
    assert_eq!((r1.as_str(), u1, a1), ("gate_shadow:mode_shadow", None, Some(0)), "the first is a would-send");
    assert_eq!((r2.as_str(), u2.as_deref(), a2), ("gate_shadow:mode_shadow", Some("inflight_same_state"), None), "the same state to the same leader at the same slot");
    // 2. a new state on the same route (another USDC sale into the AMM v4 pool, the same slot and leader)
    let next = r.sig("S9-next");
    t += 6 * MS;
    usdc_sale(&mut r, &a, 80, next, s2, &mut t);
    r.timers(t + 4 * MS);
    let o = opps(&r);
    let (_, r3, u3, a3, buy3, sell3, sv3) = o[2].clone();
    assert_eq!((buy3.as_str(), sell3.as_str()), (buy1.as_str(), sell1.as_str()), "{o:?}");
    assert_ne!(sv3, sv1);
    assert_eq!((r3.as_str(), u3, a3), ("gate_shadow:mode_shadow", None, Some(1)), "a new state version is allowed: {o:?}");
    let att = r.attempts();
    assert_eq!(att.len(), 2);
    assert_eq!((att[0]["decision"].as_u64(), att[0]["inflight"]["why_allowed"].as_str(), att[0]["sent"].as_bool()), (Some(d1), Some("first"), Some(false)));
    assert_eq!((att[1]["inflight"]["why_allowed"].as_str(), att[1]["inflight"]["prev_attempt"].as_u64()), (Some("new_state"), Some(0)), "{}", att[1]["inflight"]);
    assert_eq!(att[1]["inflight"]["prev_sv"].as_str(), Some(sv1.as_str()));
    let done = r.finish_and_replay();
    assert_eq!(done.replay["compare"]["attempts_compared"].as_u64(), Some(2));
}

/// S9, a new leader: the same state decided again a slot later (a deferred evaluation), to the next slot's leader
/// (another Jito validator: allowed, `new_leader`) or to the same leader (refused, `inflight_same_leader`). Returns the
/// run's opportunities on the AMM v4 / PumpSwap pair of pools, in order
fn same_state_a_slot_later(name: &'static str, next_leader: Pk) -> (Done, Vec<(u64, String, Option<String>, Option<u64>, String, String, String)>) {
    let mut r = Rig::new(name, Setup { pools: &["usdc.pump", "usdc.cpmm", "usdc.ammv4"], config: &NO_BAND_THROTTLE, exec: Some(ExecSetup::default()), ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    // the schedule: the Jito leader up to s0+3, then `next_leader`
    let mut sched = vec![LEADER_JITO; 4];
    sched.extend([next_leader; 60]);
    r.leaders(s0, &sched, T0 + 7 * MS);
    let (a, c) = (r.meta("usdc.ammv4"), r.meta("usdc.cpmm"));
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    // a large USDC sale into the AMM v4 pool, its write set unknown (no shred): it resolves by quiescence (3 ms)
    let sale = r.sig("S9-sale");
    let mut t = T0 + 10 * MS;
    usdc_sale(&mut r, &a, 40, sale, s2, &mut t);
    // 1 ms later a small USDC sale into CPMM (it makes CPMM a worse place to sell USDC), seen in shreds first (its write
    // set known: it commits at its last write); the CPMM routes of the AMM v4 pool are then not quiet when the sale's group
    // resolves
    let p = r.sig("S9-cpmm");
    t += MS;
    let usdc_in = token_amount(&r.data(if sol_is_t0(&c) { &c.vault1 } else { &c.vault0 })) / 3_000;
    let w = swap(&r.chain, &c, !sol_is_t0(&c), usdc_in, s2, r.unix0).0;
    let wk: Vec<Pk> = w.iter().map(|x| x.0).collect();
    r.tx(shred_tx(p, [0x62; 32], &wk, &[c.pool, *crate::venues::RAYCPMM], vec![], s2, t));
    for (k, d) in w { t += 50 * US; r.write(k, d, s2, Some(p), t); }
    // the sale's group resolves: the AMM v4 / PumpSwap route is decided (the Jito leader's slot), the CPMM ones deferred
    r.timers(t + 2 * MS);
    let before = opps(&r);
    // a slot later (the target slot's leader is now `next_leader`), the deferred evaluation runs on the same state
    r.tick(s0 + 3, t + 2 * MS + 200 * US);
    r.timers(t + 4 * MS + 500 * US);
    let o = opps(&r);
    eprintln!("{name}: opportunities before the slot {before:#?}\nafter it {o:#?}");
    let done = r.finish_and_replay();
    let ap: Vec<_> = o.into_iter().filter(|x| [x.4.as_str(), x.5.as_str()].contains(&"usdc.ammv4") && [x.4.as_str(), x.5.as_str()].contains(&"usdc.pump")).collect();
    (done, ap)
}

#[test]
fn s9_new_leader_allowed_same_leader_refused() {
    let route = |x: &(u64, String, Option<String>, Option<u64>, String, String, String)| (x.4.clone(), x.5.clone(), x.6.clone());
    let (done, ap) = same_state_a_slot_later("s9-new-leader", LEADER_JITO2);
    assert!(ap.len() == 2 && route(&ap[0]) == route(&ap[1]) && ap[0].0 < ap[1].0, "the AMM v4 / PumpSwap route decided twice on one state: {ap:?}");
    assert_eq!((ap[0].2.clone(), ap[1].2.clone()), (None, None), "both would-sends: the second to a new leader");
    let att = rec::read_jsonl(&done.dir, "attempts").unwrap();
    let (first, second) = (att.iter().find(|l| l["attempt"].as_u64() == ap[0].3).unwrap(), att.iter().find(|l| l["attempt"].as_u64() == ap[1].3).unwrap());
    assert_eq!((second["inflight"]["why_allowed"].as_str(), second["inflight"]["prev_attempt"].as_u64()), (Some("new_leader"), ap[0].3), "{}", second["inflight"]);
    assert_eq!((first["leader"]["leader"].as_str(), second["leader"]["leader"].as_str()), (Some(b58(&LEADER_JITO).as_str()), Some(b58(&LEADER_JITO2).as_str())));
    assert_eq!(second["blockhash"]["slot"], first["blockhash"]["slot"]);
    let (_done2, ap2) = same_state_a_slot_later("s9-same-leader", LEADER_JITO);
    assert!(ap2.len() == 2 && route(&ap2[0]) == route(&ap2[1]), "{ap2:?}");
    assert_eq!((ap2[0].2.as_deref(), ap2[1].2.as_deref()), (None, Some("inflight_same_leader")), "the same state to the same leader a slot later: {ap2:?}");
}

//! S1, S1b, S1b': the split-route torn read (AgmLJBMD pattern; p2#750, #1238, #1326, p9#12, p10#444, #596). One
//! transaction T sells USDC into two pools at once, the PumpSwap pool (its two vaults) and the DLMM pair (the lb_pair and
//! the bin arrays its walk changed), real layouts; its updates arrive interleaved with another transaction's and spread
//! out in time.
//!
//! | # | W(T) | Expected (PLAN WP-09) |
//! |---|---|---|
//! | S1 | from a shred hint | no evaluation until T's group completes: the half-updated state is never priced |
//! | S1b | unknown (not seen in shreds) | resolved by quiescence; no route evaluated until both pools are quiet |
//! | S1b' | unknown, a member arrives late | `late_member` counted, the decisions priced since marked `torn_suspect` |
use super::*;

const POOLS: [&str; 3] = ["usdc.pump", "usdc.dlmm", "usdc.ammv4"];
const SIGNER: Pk = [0x41; 32];

/// T: the split sell of `usdc_each` raw USDC into the PumpSwap pool and the DLMM pair at the chain's current state:
/// (the accounts T writes in pool order: pump vault0, vault1, then the lb_pair and its arrays; T's write set)
fn split_sell(r: &Rig, usdc_each: u64, slot: u64) -> Vec<(Pk, Vec<u8>)> {
    let (p, d) = (r.meta("usdc.pump"), r.meta("usdc.dlmm"));
    let usdc = p.t0;
    let (mut w, _) = swap(&r.chain, &p, true, usdc_each, slot, r.unix0);
    let (wd, _) = swap(&r.chain, &d, d.t0 == usdc, usdc_each, slot, r.unix0);
    w.extend(wd);
    w
}

/// U: a small buy of USDC with 0.01 SOL on the AMM v4 pool (its two vaults)
fn small_buy(r: &Rig, slot: u64) -> Vec<(Pk, Vec<u8>)> { let m = r.meta("usdc.ammv4"); swap(&r.chain, &m, sol_is_t0(&m), SOL / 100, slot, r.unix0).0 }

/// S1: T's write set from a shred hint; T's PumpSwap writes, then U complete on the AMM v4 pool (its evaluation must
/// refuse every route through T's pools as pending), then T's DLMM writes 1 ms later
#[test]
fn s1_split_route_with_a_shred_hint_is_never_priced_half_updated() {
    let mut r = Rig::new("s1", Setup { pools: &POOLS, ..Default::default() });
    r.make_ready(T0);
    let (pump, dlmm, amm) = (r.meta("usdc.pump"), r.meta("usdc.dlmm"), r.meta("usdc.ammv4"));
    let slot = r.s0 + 2;
    r.tick(slot, T0 + 8 * MS);
    let w = split_sell(&r, 25_000_000_000, slot);
    let (t_sig, u_sig) = (r.sig("T"), r.sig("U"));
    let wk: Vec<Pk> = w.iter().map(|x| x.0).collect();
    // T from a shred feed: its writable watched accounts are W(T)
    let ro = [*crate::venues::PUMPSWAP, *crate::venues::DLMM];
    r.tx(shred_tx(t_sig, SIGNER, &wk, &ro, vec![], slot, T0 + 10 * MS));
    let mut t = T0 + 25 * MS;
    // T's PumpSwap writes
    for (k, d) in w.iter().filter(|x| x.0 == pump.vault0 || x.0 == pump.vault1).cloned() { r.write(k, d, slot, Some(t_sig), t); t += US; }
    assert_eq!(r.e.counter("evaluation"), 0, "T's pump vaults are written, T is not complete");
    // U completes on the AMM v4 pool meanwhile (its write set known from shreds)
    let u = small_buy(&r, slot);
    let uk: Vec<Pk> = u.iter().map(|x| x.0).collect();
    r.tx(shred_tx(u_sig, [0x42; 32], &uk, &[*crate::venues::RAYAMMV4], vec![], slot, t));
    for (k, d) in u { t += US; r.write(k, d, slot, Some(u_sig), t); }
    let ev = r.evaluations();
    assert_eq!(ev.len(), 1, "U's pool evaluated");
    assert_eq!(ev[0]["trigger"]["pool"], json!(b58(&amm.pool)));
    for p in [&pump, &dlmm] {
        let through = routes_through(&ev[0], &p.pool);
        assert_eq!(through.len(), 2, "both directions through {}", nm(&p.pool));
        assert!(through.iter().all(|x| x["reason"] == "pending_commit" && x["net"].is_null()), "{} is pending: {}", nm(&p.pool), ev[0]);
    }
    // T's DLMM writes, 1 ms later: T complete; its two pools evaluated on the whole state
    t += MS;
    for (k, d) in w.iter().filter(|x| x.0 != pump.vault0 && x.0 != pump.vault1).cloned() { r.write(k, d, slot, Some(t_sig), t); t += US; }
    let ev = r.evaluations();
    assert_eq!(ev.len(), 3, "T's two pools evaluated once T completed");
    for d in &ev[1..] {
        assert_eq!(d["trigger"]["txn"], json!(bs58::encode(t_sig).into_string()));
        assert!(reasons(d).iter().all(|x| x != "pending_commit" && x != "route_not_quiet"), "priced on the whole state: {d}");
        assert!(d["routes"].as_array().unwrap().iter().all(|x| x["net"].is_i64()), "every route priced: {d}");
    }
    let c = r.commits();
    let ct = c.iter().find(|x| x["txn"] == json!(bs58::encode(t_sig).into_string())).unwrap();
    assert_eq!((ct["outcome"].as_str(), ct["w_src"].as_str(), ct["resolved_by"].as_str()), (Some("complete"), Some("shred"), Some("member")));
    assert_eq!(ct["w_seen"].as_array().unwrap().len(), w.len(), "every write of T in its group");
    assert_eq!(ct["t_first_shred"].as_u64(), Some(T0 + 10 * MS));
    let done = r.finish_and_replay();
    done.check_expected();
}

/// S1b: the same T not seen in shreds (W(T) unknown): its writes half a millisecond apart, within `quiescence_ms` (3):
/// nothing of T's is priced until T has been quiet for 3 ms. A small trade U (its write set from a shred feed) completes on
/// the AMM v4 pool 1 ms after T's last write: its evaluation refuses the routes through T's pools (T still pending), and
/// when T resolves the routes through the AMM v4 pool are not quiet (`route_not_quiet`: a group resolved by a timeout
/// prices a route only when both its pools are quiet); they are evaluated again once they are
#[test]
fn s1b_unknown_write_set_resolves_by_quiescence() {
    let mut r = Rig::new("s1b", Setup { pools: &POOLS, ..Default::default() });
    r.make_ready(T0);
    let q = r.cfg.state.quiescence_ms * MS;
    assert_eq!(q, 3 * MS, "the Stage-0 placeholder");
    let amm = r.meta("usdc.ammv4");
    let slot = r.s0 + 2;
    r.tick(slot, T0 + 8 * MS);
    let w = split_sell(&r, 25_000_000_000, slot);
    let (t_sig, u_sig) = (r.sig("T"), r.sig("U"));
    let mut t = T0 + 20 * MS;
    for (k, d) in w.iter().cloned() { r.write(k, d, slot, Some(t_sig), t); t += MS / 2; }
    let last = t - MS / 2;
    let u = small_buy(&r, slot);
    let uk: Vec<Pk> = u.iter().map(|x| x.0).collect();
    let mut tu = last + MS;
    r.tx(shred_tx(u_sig, [0x42; 32], &uk, &[*crate::venues::RAYAMMV4], vec![], slot, tu - 200 * US));
    for (k, d) in u { r.write(k, d, slot, Some(u_sig), tu); tu += US; }
    let u_last = tu - US;
    let ev = r.evaluations();
    assert_eq!(ev.len(), 1, "U complete: the AMM v4 pool evaluated");
    for p in [r.meta("usdc.pump"), r.meta("usdc.dlmm")] {
        assert!(routes_through(&ev[0], &p.pool).iter().all(|x| x["reason"] == "pending_commit"), "T is still pending: {}", ev[0]);
    }
    r.timers(last + q - 1);
    assert_eq!(r.e.counter("evaluation"), 1, "T not quiet yet (its last write {} ns ago)", q - 1);
    r.timers(last + q);
    let ev: Vec<Value> = r.evaluations().into_iter().skip(1).collect();
    assert_eq!(ev.len(), 2, "T's two pools, once T was quiet");
    assert!(ev.iter().all(|d| d["kind"] == "quiescent" && d["w_src"] == "unknown" && d["trigger"]["txn"] == json!(bs58::encode(t_sig).into_string())));
    for d in &ev {
        for x in d["routes"].as_array().unwrap() {
            let via_amm = x["buy"] == json!(b58(&amm.pool)) || x["sell"] == json!(b58(&amm.pool));
            if via_amm { assert_eq!(x["reason"], "route_not_quiet", "U wrote the AMM v4 pool 2 ms ago: {d}"); } else { assert!(x["net"].is_i64(), "priced on T's whole state: {d}"); }
        }
    }
    // the deferred evaluations once the AMM v4 pool is quiet: every route priced
    r.timers(u_last + q);
    assert_eq!(r.e.counter("evaluation_deferred"), 2, "T's two pools again");
    let ev = r.evaluations();
    let later: Vec<&Value> = ev.iter().skip(3).collect();
    assert_eq!(later.len(), 2);
    assert!(later.iter().all(|d| d["routes"].as_array().unwrap().iter().all(|x| x["net"].is_i64())), "{later:?}");
    let c = r.commits();
    let ct = c.iter().find(|x| x["txn"] == json!(bs58::encode(t_sig).into_string())).unwrap();
    assert_eq!((ct["outcome"].as_str(), ct["resolved_by"].as_str(), ct["w_seen"].as_array().unwrap().len()), (Some("timeout_quiescent"), Some("timer"), w.len()));
    let done = r.finish_and_replay();
    done.check_expected();
}

/// S1b': as S1b, but T's last DLMM bin array write arrives 2 ms after T's group resolved: a late member. The decisions
/// priced on T's pools in between are `torn_suspect` (a follow-up line each), and the late write opens its own group
#[test]
fn s1b_late_member_marks_torn_suspect() {
    let mut r = Rig::new("s1b_late", Setup { pools: &POOLS, ..Default::default() });
    r.make_ready(T0);
    let q = r.cfg.state.quiescence_ms * MS;
    let slot = r.s0 + 2;
    r.tick(slot, T0 + 8 * MS);
    let w = split_sell(&r, 25_000_000_000, slot);
    assert!(w.len() >= 4, "two vaults, the lb_pair and at least one bin array");
    let (late_k, late_d) = w.last().cloned().unwrap();
    let t_sig = r.sig("T");
    let mut t = T0 + 20 * MS;
    for (k, d) in w[..w.len() - 1].iter().cloned() { r.write(k, d, slot, Some(t_sig), t); t += MS / 2; }
    let last = t - MS / 2;
    r.timers(last + q);
    let priced: Vec<u64> = r.evaluations().iter().filter(|d| d["routes"].as_array().unwrap().iter().any(|x| x["net"].is_i64())).map(|d| d["decision"].as_u64().unwrap()).collect();
    assert!(!priced.is_empty(), "T's pools priced after the quiescence");
    // the late member: T's last bin array, 2 ms after the resolution
    r.write(late_k, late_d, slot, Some(t_sig), last + q + 2 * MS);
    assert_eq!(r.e.counter("commit_late_member"), 1);
    assert_eq!(r.e.counter("torn_suspect") as usize, priced.len());
    let torn: Vec<u64> = r.decisions().iter().filter(|d| d["torn_suspect"] == json!(true) && d.get("routes").is_none()).map(|d| d["decision"].as_u64().unwrap()).collect();
    assert_eq!(torn, priced, "every decision priced on T's pools since the resolution");
    let c = r.commits();
    assert!(c.iter().any(|x| x["late"] == json!(true) && x["late_members"][0]["acct"] == json!(b58(&late_k))));
    // the late write's own group resolves by quiescence and evaluates the DLMM pair again, on the whole state
    r.timers(last + 2 * q + 2 * MS);
    let ev = r.evaluations();
    assert!(ev.len() > priced.len(), "the late member's group evaluated the pair again");
    let done = r.finish_and_replay();
    done.check_expected();
}

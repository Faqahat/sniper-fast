//! S13 (PLAN WP-09; R §3.4: 130 bundles accepted, then would-fail, never landed): a verdict sequence accepted →
//! would-fail, recorded in full. A canary run (live under `[canary]`'s caps, here 0.2 SOL and no wait between attempts)
//! on real USDC/SOL pools sends a real bundle through its jito-bundle path to a block engine in memory (nothing leaves
//! the process). The block engine then answers `accepted`, then `would-fail` with the route program's profit check
//! (0x4e580002), and the attempt is final only when its blockhash expires (PLAN WP-07: a landing or the expiry; review
//! WP-05 #2), after the expiry check.
//!
//! Recorded in full: attempts.jsonl (the attempt, `sent`), copies.jsonl (the copy that left, its bundle id),
//! bundles.jsonl (both results in order, the would-fail's code), the journal (each result as INPUT 5
//! `inflight_release`, `release` false; the fire's result and the expiry check's answer as INPUT 9), outcomes.jsonl (one
//! final line, `not_landed_expired`, carrying both verdicts in order, the would-fail's code and detail), and the
//! decisions (`sent`, the attempt). Neither verdict released the in-flight entry: the same state goes neither again to
//! the same leader (a deferred evaluation of the same state is refused `inflight_same_state`). The replay's offline
//! executor (WP-09 part 2: a canary executor is replayed, its send with the run's signature) gives every decision,
//! attempt and digest the run gave.
use super::*;
use crate::exec::Mode;

const POOLS3: [&str; 3] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4"];
/// the route program's profit check, as the block engine's simulation reports it (jito.rs `error_code` reads 0x4e580002)
pub(crate) const PROFIT_FAIL: &str = "A transaction in the bundle failed to execute: [signature=x, error=Error processing Instruction 2: custom program error: 0x4e580002]";

/// a USDC sale of 1/`frac` of pool `m`'s USDC reserve by transaction `sig` at `slot` (its writes from `t`, 100 µs apart)
pub(crate) fn usdc_sale(r: &mut Rig, m: &PoolMeta, frac: u64, sig: [u8; 64], slot: u64, t: &mut u64) {
    let usdc_in = token_amount(&r.data(if sol_is_t0(m) { &m.vault1 } else { &m.vault0 })) / frac;
    let w = swap(&r.chain, m, !sol_is_t0(m), usdc_in, slot, r.unix0).0;
    for (k, d) in w { r.write(k, d, slot, Some(sig), *t); *t += 100 * US; }
}

/// A canary run on `pools` with `config` (`CANARY` and more), ready, the Jito leader's slots, a fresh blockhash and the
/// ledger's start snapshot (a live or canary run sends nothing before it: `equity_unknown`); returns it with its slot
pub(crate) fn canary_rig(name: &'static str, pools: &'static [&'static str], config: &'static [(&'static str, &'static str)], hold_tokens: bool) -> (Rig, u64) {
    let mut r = Rig::new(name, Setup { pools, config, exec: Some(ExecSetup { mode: Mode::Canary, sticky_shadow: false, hold_tokens, ..Default::default() }),
        ..Default::default() });
    r.make_ready(T0);
    let s0 = r.s0;
    r.leaders(s0, &[LEADER_JITO; 400], T0 + 7 * MS);
    let s2 = s0 + 2;
    r.tick(s2, T0 + 8 * MS);
    r.blockhash(s2, T0 + 8 * MS + 200 * US);
    r.snapshot(s2, 3 * SOL, 2 * SOL, None, "start", T0 + 9 * MS);
    (r, s2)
}

/// The same state decided twice (S9's deferral): a large USDC sale into the AMM v4 pool (its write set unknown: it
/// resolves by quiescence) and, 1 ms later, a small one into CPMM seen in shreds first; when the sale's group resolves
/// the AMM v4 / PumpSwap route is decided at once and the CPMM routes are deferred (not quiet); the deferred evaluation
/// runs at the next timers on the same state. Here the first decision is sent and the block engine's answers come
/// between the two (`between`); returns the time after the deferred evaluation
pub(crate) fn same_state_twice(r: &mut Rig, s2: u64, between: &mut dyn FnMut(&mut Rig, u64) -> u64) -> u64 {
    let (a, c) = (r.meta("usdc.ammv4"), r.meta("usdc.cpmm"));
    let sale = r.sig("S13-sale");
    let mut t = T0 + 10 * MS;
    usdc_sale(r, &a, 40, sale, s2, &mut t);
    let p = r.sig("S13-cpmm");
    t += MS;
    let usdc_in = token_amount(&r.data(if sol_is_t0(&c) { &c.vault1 } else { &c.vault0 })) / 3_000;
    let w = swap(&r.chain, &c, !sol_is_t0(&c), usdc_in, s2, r.unix0).0;
    let wk: Vec<Pk> = w.iter().map(|x| x.0).collect();
    r.tx(shred_tx(p, [0x62; 32], &wk, &[c.pool, *crate::venues::RAYCPMM], vec![], s2, t));
    for (k, d) in w { t += 50 * US; r.write(k, d, s2, Some(p), t); }
    // the sale's group resolves: the AMM v4 / PumpSwap route is decided (and sent), the CPMM routes deferred
    r.timers(t + 2 * MS);
    let t = between(r, t + 2 * MS + 100 * US);
    // the deferred evaluation, on the same state, the same slot and leader
    r.timers(t + MS);
    t + 2 * MS
}

#[test]
fn s13_an_accepted_then_would_fail_bundle_is_recorded_in_full() {
    let (mut r, s2) = canary_rig("s13", &POOLS3, &CANARY, true);
    let mut sent = Vec::new();
    let t = same_state_twice(&mut r, s2, &mut |r, t| {
        assert_eq!(r.attempts().len(), 1, "the first decision was sent");
        // the fire's result (the copy left; the block engine in memory gave it the id b0), then the block engine's two answers
        sent.push(r.pump(1, t));
        sent.push(vec![r.verdict("b0", "accepted", Some(s2 + 1), None, t + MS)]);
        sent.push(vec![r.verdict("b0", "would-fail", Some(s2 + 1), Some(PROFIT_FAIL), t + 2 * MS)]);
        t + 3 * MS
    });
    eprintln!("S13: handed to the engine {sent:?}");
    assert_eq!(sent[0][0]["what"], "fired");
    assert_eq!((sent[1][0]["outcome"].as_str(), sent[1][0]["release"].as_bool(), sent[2][0]["outcome"].as_str(), sent[2][0]["release"].as_bool()),
        (Some("accepted"), Some(false), Some("would-fail"), Some(false)), "neither result is a landing: neither releases");
    let opps = r.opportunities();
    let route = |d: &Value| { let b = &d["routes"][d["best"].as_u64().unwrap() as usize]; (b["buy"].clone(), b["sell"].clone(), d["sv"]["h"].clone()) };
    let ap: Vec<&Value> = opps.iter().filter(|d| route(d) == route(&opps[0])).collect();
    eprintln!("S13: opportunities {:?}", opps.iter().map(|d| (d["decision"].clone(), d["reason"].clone(), d["attempt"].clone(), route(d))).collect::<Vec<_>>());
    assert!(ap.len() >= 2, "the route decided twice on one state: {opps:?}");
    assert_eq!((ap[0]["reason"].as_str(), ap[0]["sent"].as_bool(), ap[0]["attempt"].as_u64()), (Some("sent"), Some(true), Some(0)), "{}", ap[0]);
    assert_eq!((ap[1]["reason"].as_str(), ap[1]["attempt"].as_u64()), (Some("inflight_same_state"), None),
        "after accepted and would-fail the entry holds: the same state to the same leader at the same slot is refused: {}", ap[1]);
    assert_eq!(r.bundles_sent().len(), 1, "one bundle reached the block engine");
    // the chain passes the blockhash's validity (150 blocks): the expiry check (one getSignatureStatuses; no provider
    // here: it fails at once, and the attempt is final, not landed), then the final line
    r.blockhash(s2 + 152, t + 400 * MS);
    r.timers(t + 410 * MS);
    let expiry = r.pump(1, t + 411 * MS);
    assert_eq!((expiry[0]["what"].as_str(), expiry[0]["why"].as_str(), expiry[0]["attempt"].as_u64()), (Some("statuses"), Some("expiry"), Some(0)), "{expiry:?}");
    // recorded in full
    let att = r.attempts();
    assert_eq!(att.len(), 1);
    let a = &att[0];
    assert_eq!((a["kind"].as_str(), a["sent"].as_bool(), a["inflight"]["why_allowed"].as_str()), (Some("canary"), Some(true), Some("first")), "{a}");
    assert!(a["size_lamports"].as_u64().unwrap() <= SOL / 5, "the canary's size cap: {a}");
    let copies = r.lines("copies");
    assert_eq!((copies.len(), copies[0]["bundle"].as_str(), copies[0]["ok"].as_bool(), copies[0]["sig"].clone()), (1, Some("b0"), Some(true), a["tx"]["sig"].clone()), "{copies:?}");
    let bundles = r.lines("bundles");
    let seq: Vec<(Option<&str>, Option<u64>, Option<&str>, Option<u64>)> = bundles.iter().map(|b| (b["outcome"].as_str(), b["seq"].as_u64(), b["code"].as_str(), b["attempt"].as_u64())).collect();
    assert_eq!(seq, vec![(Some("accepted"), Some(0), None, Some(0)), (Some("would-fail"), Some(1), Some("0x4e580002"), Some(0))], "{bundles:?}");
    assert!(bundles.iter().all(|b| b["sig"] == a["tx"]["sig"] && b["bundle"] == "b0"));
    let out = r.lines("outcomes");
    assert_eq!(out.len(), 1, "one final line: {out:?}");
    let o = &out[0];
    assert_eq!((o["attempt"].as_u64(), o["final"].as_str(), o["final_src"].as_str(), o["landed"].clone()), (Some(0), Some("not_landed_expired"), Some("expiry"), Value::Null), "{o}");
    let v: Vec<(Option<&str>, Option<&str>)> = o["verdicts"].as_array().unwrap().iter().map(|x| (x["outcome"].as_str(), x["code"].as_str())).collect();
    assert_eq!(v, vec![(Some("accepted"), None), (Some("would-fail"), Some("0x4e580002"))], "both verdicts in order on the final line: {o}");
    assert_eq!((o["accepted"]["slot"].as_u64(), o["verdicts"][1]["detail"].as_str(), o["bundle"].as_str()), (Some(s2 + 1), Some(PROFIT_FAIL), Some("b0")), "{o}");
    assert!(o["error"].as_str().is_some_and(|e| e.contains("expiry check failed")), "the expiry check's failure is on the line: {o}");
    // the journal holds each result as the run's engine took it
    r.rec.sync();
    let inputs: Vec<Value> = crate::rec::journal::read_dir(&r.dir).unwrap().into_iter().filter_map(|x| match x.body {
        crate::rec::journal::JBody::Input { kind, data } if kind == InputKind::InflightRelease as u8 => Some(data), _ => None }).collect();
    assert_eq!(inputs.iter().map(|d| (d["outcome"].as_str(), d["release"].as_bool(), d["code"].as_str(), d["attempt"].as_u64())).collect::<Vec<_>>(),
        vec![(Some("accepted"), Some(false), None, Some(0)), (Some("would-fail"), Some(false), Some("0x4e580002"), Some(0))]);
    let st = r.e.exec.as_ref().unwrap().status();
    assert_eq!((st["counts"]["verdict_accepted"].as_u64(), st["counts"]["verdict_would_fail"].as_u64(), st["counts"]["not_landed_expired"].as_u64(),
        st["counts"]["inflight_released"].as_u64(), st["in_flight"].as_u64()), (Some(1), Some(1), Some(1), None, Some(0)), "{st}");
    let done = r.finish_and_replay();
    assert_eq!((done.replay["executor"]["exec_init"]["mode"].as_str(), done.replay["executor"]["sent_missing"].as_u64()), (Some("canary"), Some(0)), "{}", done.replay["executor"]);
    done.check_expected();
}

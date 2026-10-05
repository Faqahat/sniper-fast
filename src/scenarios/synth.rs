//! PLAN WP-09 offline acceptance: a synthetic 10-minute journal and account stream (generated) replays to identical
//! decisions and runs at least 20x faster than real time.
//!
//! The run: the five USDC/SOL pools of the fixtures (real layouts), 600 s of engine time: a slot every 400 ms (processed,
//! then confirmed a slot later) with its Clock write, and about 25 trades a second at random on the five pools (small,
//! each moving its pool by the venue's own maths), half of them with their write set from a shred feed, half unknown,
//! some of their updates delayed or arriving in another order; the timers as `Engine::run` calls them (after an input
//! when a deadline is due, idle wake-ups). Then `replay::replay` with the compare: every decision and commit group the
//! same, the run's state and decision digests, and the replay's speed against the 600 s it covers.
use super::*;

const POOLS: [&str; 5] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4", "usdc.dlmm", "usdc.damm"];

/// xorshift64
struct Rng(u64);
impl Rng {
    fn next(&mut self) -> u64 { self.0 ^= self.0 << 13; self.0 ^= self.0 >> 7; self.0 ^= self.0 << 17; self.0 }
    fn below(&mut self, n: u64) -> u64 { self.next() % n.max(1) }
}

#[test]
fn a_synthetic_ten_minute_run_replays_identically_and_fast() {
    let mut r = Rig::new("synth10m", Setup { pools: &POOLS, ..Default::default() });
    r.make_ready(T0);
    let metas: Vec<PoolMeta> = POOLS.iter().map(|n| r.meta(n)).collect();
    // each pool's SOL reserve: trades are 0.05%-0.5% of it, both ways at random (a random walk around the start)
    let sol_reserve = |r: &Rig, m: &PoolMeta| -> u64 {
        match m.venue {
            Venue::Dlmm | Venue::DammV2 => 50 * SOL,
            _ => token_amount(&r.data(if sol_is_t0(m) { &m.vault0 } else { &m.vault1 })),
        }
    };
    let mut rng = Rng(0x5eed_0f_a5_9e_7e);
    let span = 600 * 1_000 * MS;
    let (mut t, mut slot, mut next_slot_t) = (T0 + 10 * MS, r.s0 + 1, T0 + 400 * MS);
    let (mut trades, mut skipped, mut n) = (0u64, 0u64, 0u64);
    // the engine's clock never runs backwards: every input after the last one handled
    let mut last_t = T0 + 10 * MS;
    while t < T0 + span {
        // the slot clock: processed (with its Clock write), the previous one confirmed
        while t >= next_slot_t {
            let ts = next_slot_t.max(last_t + 100 * US);
            slot += 1;
            r.slot(slot, 0, Some(slot - 1), ts);
            r.clock(slot, ts + 20 * US);
            r.slot(slot - 1, 1, Some(slot - 2), ts + 40 * US);
            r.e.timers_at(ts + 60 * US, engine::TIMER_COMMIT, &mut nop());
            last_t = ts + 60 * US;
            next_slot_t += 400 * MS;
        }
        t = t.max(last_t + 100 * US);
        n += 1;
        let m = &metas[rng.below(metas.len() as u64) as usize];
        let sol_in = rng.below(2) == 0;
        let frac = 5 + rng.below(45);
        let mut amount = sol_reserve(&r, m) * frac / 10_000;
        if !sol_in {
            // the token side: as much USDC as that SOL buys (about 120 USDC a SOL, 6 decimals: x 0.12)
            amount = amount * 12 / 100;
        }
        let zfo = if sol_in { sol_is_t0(m) } else { !sol_is_t0(m) };
        let Some((w, _)) = try_swap(&r.chain, m, zfo, amount.max(1_000), slot, r.unix0) else { skipped += 1; t += 40 * MS; continue };
        let sig = { let mut s = [0u8; 64]; s[..8].copy_from_slice(&n.to_le_bytes()); s[8] = 0x77; s };
        let mut tt = t;
        // half the trades are seen in shreds first (their write set a hint), a few after their first update
        let hint = rng.below(2) == 0;
        let wk: Vec<Pk> = w.iter().map(|x| x.0).collect();
        let pool = m.pool;
        let shred = |at: u64| shred_tx(sig, [0x33; 32], &wk, &[pool], vec![], slot, at);
        let late_hint = hint && rng.below(5) == 0;
        if hint && !late_hint { r.tx(shred(tt)); tt += 200 * US; }
        let mut order: Vec<(Pk, Vec<u8>)> = w;
        if order.len() > 1 && rng.below(4) == 0 { order.reverse(); }
        for (i, (k, d)) in order.into_iter().enumerate() {
            r.write(k, d, slot, Some(sig), tt);
            tt += if rng.below(10) == 0 { 1_500 * US } else { 50 * US };
            if late_hint && i == 0 { r.tx(shred(tt)); tt += 50 * US; }
        }
        // the queue empties: a commit deadline due runs the commit timers; an idle wake-up a few ms later everything
        r.e.timers_at(tt + 5 * MS + US, engine::TIMER_COMMIT, &mut nop());
        r.timers(tt + 6 * MS);
        last_t = tt + 6 * MS;
        trades += 1;
        t = tt + 10 * MS + rng.below(60) * MS;
    }
    r.timers(T0 + span + 30 * MS);
    let evaluations = r.e.counter("evaluation");
    let opportunities = r.e.counter("state_opportunity");
    eprintln!("synthetic run: {trades} trades ({skipped} refused by their venue), {} slots, {evaluations} evaluations, {opportunities} opportunities",
        slot - r.s0);
    assert!(trades > 10_000 && evaluations > 10_000, "a full 10 minutes of trading: {trades} trades, {evaluations} evaluations");
    let done = r.finish_and_replay();
    let rp = &done.replay;
    let (span_ms, wall_ms, speed) = (rp["journal"]["span_ms"].as_f64().unwrap(), rp["wall_ms"].as_f64().unwrap(), rp["speed_x"].as_f64().unwrap());
    eprintln!("synthetic run replayed: {} records over {:.0} s of engine time in {:.2} s: {speed:.1}x real time; {} decisions compared, identical",
        rp["journal"]["records"], span_ms / 1e3, wall_ms / 1e3, rp["compare"]["compared"]);
    assert!(span_ms >= 600_000.0, "a 10-minute journal: {span_ms} ms");
    assert_eq!(rp["compare"]["identical"], rp["compare"]["compared"]);
    // PLAN WP-09: at least 20x faster than real time (release builds; a debug build is far slower and only reports it)
    if !cfg!(debug_assertions) { assert!(speed >= 20.0, "the replay ran {speed:.1}x real time, under 20x"); }
}

/// Go-live gate item 3 (PLAN-ADDENDUM: "a 1 h recording that replays identically"; review WP-09 "For the WP-05 merge"),
/// on a synthetic hour: a shadow run as `arbx run` makes one, with its executor (`Mode::Shadow`, the SendGate shadow for
/// the whole segment, WP-00's crowded list naming CPMM, the Stage-0 config). An hour of engine time: a slot every 400 ms
/// (processed with its Clock, confirmed a slot later) with the blockhash ring's head (stalled for 40 s once:
/// `blockhash_stale`); the leader schedule a window of 400 slots at a time (two Jito validators and one of another
/// kind: `leader_skip_kind`; one window that never came: `leader_unknown`); trades on the five USDC/SOL pools, a few a
/// second (half of them seen in shreds first; would-sends at the bundle path's rate, in-flight refusals, the ≥1M
/// class's throttle, crowded skips); an owner's top-up in the wallet stream. The replay, with the compare: ok and
/// whole, every decision and every attempt identical, the run's state and decision digests reproduced (the state
/// digest folds the executor's state and the crowding map), at least 20x real time
#[test]
fn a_synthetic_shadow_hour_replays_identically() {
    let mut r = Rig::new("synth1h", Setup { pools: &POOLS, exec: Some(ExecSetup { crowded: &["usdc.cpmm"], ..Default::default() }), ..Default::default() });
    r.make_ready(T0);
    let metas: Vec<PoolMeta> = POOLS.iter().map(|n| r.meta(n)).collect();
    let sol_reserve = |r: &Rig, m: &PoolMeta| -> u64 {
        match m.venue {
            Venue::Dlmm | Venue::DammV2 => 50 * SOL,
            _ => token_amount(&r.data(if sol_is_t0(m) { &m.vault0 } else { &m.vault1 })),
        }
    };
    // the schedule: 4-slot leaders, mostly Jito (two validators), every tenth a leader of another kind
    let leader_of = |slot: u64| match (slot / 4) % 10 { 9 => LEADER_OTHER, 6 | 7 => LEADER_JITO2, _ => LEADER_JITO };
    let window = |start: u64| -> Vec<Pk> { (start..start + 400).map(leader_of).collect() };
    let s0 = r.s0;
    r.leaders(s0, &window(s0), T0 + 7 * MS);
    let mut rng = Rng(0x60_11_7e_16_a7_e3);
    let span = 3_600 * 1_000 * MS;
    let (mut t, mut slot, mut next_slot_t) = (T0 + 10 * MS, s0 + 1, T0 + 400 * MS);
    let (mut trades, mut skipped, mut n) = (0u64, 0u64, 0u64);
    let mut last_t = T0 + 10 * MS;
    let mut window_next = s0 + 400;
    let mut topped_up = false;
    while t < T0 + span {
        while t >= next_slot_t {
            let ts = next_slot_t.max(last_t + 100 * US);
            slot += 1;
            r.slot(slot, 0, Some(slot - 1), ts);
            r.clock(slot, ts + 20 * US);
            r.slot(slot - 1, 1, Some(slot - 2), ts + 40 * US);
            // the ring's head, except for 100 slots in the 20th minute (a stalled ring)
            let stalled = (s0 + 3_000..s0 + 3_100).contains(&slot);
            if !stalled { r.blockhash(slot, ts + 50 * US); }
            // the next window 100 slots before it is needed (the one at slot s0 + 4,400 never comes)
            if slot + 100 >= window_next {
                if window_next != s0 + 4_400 { r.leaders(window_next, &window(window_next), ts + 55 * US); }
                window_next += 400;
            }
            r.e.timers_at(ts + 60 * US, engine::TIMER_COMMIT, &mut nop());
            last_t = ts + 60 * US;
            next_slot_t += 400 * MS;
        }
        t = t.max(last_t + 100 * US);
        // an owner's top-up of the wallet (not one of our attempts: the executor ignores it)
        if !topped_up && t > T0 + 1_800 * 1_000 * MS {
            topped_up = true;
            r.input(InputKind::WalletTx, json!({ "sig": bs58::encode([0x70u8; 64]).into_string(), "slot": slot, "idx": 3, "ok": true, "err": null, "fee": 5_000 }), t);
            t += 100 * US;
        }
        n += 1;
        let m = &metas[rng.below(metas.len() as u64) as usize];
        let sol_in = rng.below(2) == 0;
        // mostly small (0.01%-0.1% of the pool), now and then large (0.5%-1%): gaps of every band
        let frac = if rng.below(20) == 0 { 50 + rng.below(50) } else { 1 + rng.below(10) };
        let mut amount = sol_reserve(&r, m) * frac / 10_000;
        if !sol_in { amount = amount * 12 / 100; }
        let zfo = if sol_in { sol_is_t0(m) } else { !sol_is_t0(m) };
        let Some((w, _)) = try_swap(&r.chain, m, zfo, amount.max(1_000), slot, r.unix0) else { skipped += 1; t += 100 * MS; continue };
        let sig = { let mut s = [0u8; 64]; s[..8].copy_from_slice(&n.to_le_bytes()); s[8] = 0x60; s };
        let mut tt = t;
        let hint = rng.below(2) == 0;
        if hint {
            let wk: Vec<Pk> = w.iter().map(|x| x.0).collect();
            r.tx(shred_tx(sig, [0x34; 32], &wk, &[m.pool], vec![], slot, tt));
            tt += 200 * US;
        }
        for (k, d) in w { r.write(k, d, slot, Some(sig), tt); tt += 50 * US; }
        r.e.timers_at(tt + 5 * MS + US, engine::TIMER_COMMIT, &mut nop());
        r.timers(tt + 6 * MS);
        last_t = tt + 6 * MS;
        trades += 1;
        t = tt + 50 * MS + rng.below(400) * MS;
    }
    r.timers(T0 + span + 30 * MS);
    let ev = r.evaluations();
    let opps: Vec<&Value> = ev.iter().filter(|d| d["opp"].is_u64()).collect();
    let mut by_reason: std::collections::BTreeMap<String, u64> = Default::default();
    for d in &opps { *by_reason.entry(d["reason_ungated"].as_str().unwrap_or(if d["would_send"] == json!(true) { "(would_send)" } else { "-" }).split(':').next().unwrap().to_string()).or_default() += 1; }
    let attempts = r.attempts().len();
    eprintln!("synthetic shadow hour: {trades} trades ({skipped} refused by their venue), {} slots, {} evaluations, {} opportunities, {attempts} would-sends; \
        the executor's verdicts behind the gate: {by_reason:?}", slot - s0, ev.len(), opps.len());
    assert!(trades > 10_000 && attempts > 100, "an hour of trading: {trades} trades, {attempts} would-sends");
    for why in ["(would_send)", "band_throttle", "blockhash_stale", "leader_skip_kind", "leader_unknown"] {
        assert!(by_reason.get(why).copied().unwrap_or(0) > 0, "the hour exercises {why}: {by_reason:?}");
    }
    let done = r.finish_and_replay();
    let rp = &done.replay;
    let (span_ms, wall_ms, speed) = (rp["journal"]["span_ms"].as_f64().unwrap(), rp["wall_ms"].as_f64().unwrap(), rp["speed_x"].as_f64().unwrap());
    eprintln!("go-live gate item 3 check: {} journal records over {:.0} s of engine time replayed in {:.2} s ({speed:.0}x real time): ok {}, whole {}, {} decisions and {} attempts \
        compared, all identical; digests same {} (run {} / {}, replay {} / {})",
        rp["journal"]["records"], span_ms / 1e3, wall_ms / 1e3, rp["ok"], rp["whole"], rp["compare"]["compared"], rp["compare"]["attempts_compared"], rp["digests"]["same"],
        rp["digests"]["run"]["digest"], rp["digests"]["run"]["decision_digest"], rp["digests"]["replay"]["digest"], rp["digests"]["replay"]["decision_digest"]);
    assert!(span_ms >= 3_600_000.0, "an hour's journal: {span_ms} ms");
    assert_eq!((rp["ok"].as_bool(), rp["whole"].as_bool(), rp["digests"]["checked"].as_bool(), rp["digests"]["same"].as_bool()), (Some(true), Some(true), Some(true), Some(true)));
    assert_eq!((rp["compare"]["identical"].clone(), rp["compare"]["attempts_compared"].as_u64()), (rp["compare"]["compared"].clone(), Some(attempts as u64)));
    assert_eq!((rp["executor"]["replayed"].as_bool(), rp["executor"]["records_mismatch"].as_u64(), rp["executor"]["records_unused"].as_u64()), (Some(true), Some(0), Some(0)));
    if !cfg!(debug_assertions) { assert!(speed >= 20.0, "the replay ran {speed:.1}x real time, under 20x"); }
}

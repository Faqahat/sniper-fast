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

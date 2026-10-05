//! S4, S4b: the PumpSwap consistency set (F3; PLAN WP-04 item 4). A PumpSwap swap writes its two vaults, not the pool
//! account, so the pool's consistency set is {vault0, vault1}: their slots must be at most `max_part_skew_slots` (2)
//! apart; the pool account is an "other part" (present, not pending, no age rule); slots are never compared across pools.
//!
//! | # | State | Expected (PLAN WP-09) |
//! |---|---|---|
//! | S4 | one PumpSwap vault 3 slots older than the other | reason `parts_skewed` |
//! | S4b | the PumpSwap pool account 10,000 slots old with fresh vaults, and an idle sell pool 500 slots old | priced normally |
use super::*;

const POOLS: [&str; 2] = ["usdc.pump", "usdc.ammv4"];

/// S4: a transfer into the PumpSwap pool's SOL vault (a donation: no swap) at s0+3, while its USDC vault is still the
/// boot snapshot's (s0): every route through the pool is `parts_skewed`, in both directions and from either pool's
/// evaluation; once the USDC vault is written at s0+3 too, the routes are priced
#[test]
fn s4_a_pumpswap_vault_three_slots_older_is_parts_skewed() {
    let mut r = Rig::new("s4", Setup { pools: &POOLS, ..Default::default() });
    r.make_ready(T0);
    let (p, a) = (r.meta("usdc.pump"), r.meta("usdc.ammv4"));
    let s3 = r.s0 + 3;
    r.tick(r.s0 + 2, T0 + 8 * MS);
    r.tick(s3, T0 + 9 * MS);
    let sol_vault = if sol_is_t0(&p) { p.vault0 } else { p.vault1 };
    let usdc_vault = if sol_is_t0(&p) { p.vault1 } else { p.vault0 };
    let donated = with_amount(&r.data(&sol_vault), token_amount(&r.data(&sol_vault)) + SOL);
    let d1 = r.sig("donation");
    r.write(sol_vault, donated, s3, Some(d1), T0 + 20 * MS);
    r.timers(T0 + 24 * MS);
    let ev = r.evaluations();
    assert_eq!(ev.len(), 1, "the pump pool evaluated");
    assert!(reasons(&ev[0]).iter().all(|x| x == "parts_skewed"), "its vaults are 3 slots apart: {}", ev[0]);
    // the other pool's evaluation refuses the routes through the skewed pool too
    let u = swap(&r.chain, &a, sol_is_t0(&a), SOL / 100, s3, r.unix0).0;
    let us = r.sig("small");
    let mut t = T0 + 30 * MS;
    for (k, d) in u { r.write(k, d, s3, Some(us), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    let ev = r.evaluations();
    assert_eq!(ev.len(), 2);
    assert!(reasons(&ev[1]).iter().all(|x| x == "parts_skewed"), "{}", ev[1]);
    // the USDC vault written at s0+3 too: the pool's consistency set is within one slot; priced
    let fresh = with_amount(&r.data(&usdc_vault), token_amount(&r.data(&usdc_vault)));
    let d2 = r.sig("touch");
    r.write(usdc_vault, fresh, s3, Some(d2), t + 10 * MS);
    r.timers(t + 15 * MS);
    let ev = r.evaluations();
    let last = ev.last().unwrap();
    assert!(last["routes"].as_array().unwrap().iter().all(|x| x["net"].is_i64()), "priced once the set is consistent: {last}");
    assert_eq!(last["parts_skew_slots"], json!({ "buy": 0, "sell": 0 }));
    let done = r.finish_and_replay();
    done.check_expected();
}

/// S4b: everything read at boot 10,000 slots ago; the AMM v4 pool last traded 500 slots ago (idle since); the PumpSwap
/// pool's vaults written now, its pool account still the boot's (10,000 slots old): priced normally
#[test]
fn s4b_an_old_pumpswap_pool_account_and_an_idle_pool_are_priced() {
    let f = fixtures();
    let sb = f.slot - 10_000;
    let mut r = Rig::new("s4b", Setup { pools: &POOLS, s0: Some(sb), ..Default::default() });
    r.make_ready(T0);
    let (p, a) = (r.meta("usdc.pump"), r.meta("usdc.ammv4"));
    let (s_idle, s_now) = (sb + 9_500, sb + 10_000);
    r.tick(s_idle, T0 + 8 * MS);
    let ua = swap(&r.chain, &a, sol_is_t0(&a), SOL, s_idle, r.unix0).0;
    let ta = r.sig("amm-trade");
    let mut t = T0 + 10 * MS;
    for (k, d) in ua { r.write(k, d, s_idle, Some(ta), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    // 500 slots later (200 s), a trade on the PumpSwap pool
    let t1 = T0 + 200_000 * MS;
    r.tick(s_now, t1);
    let up = swap(&r.chain, &p, !sol_is_t0(&p), 2_000_000_000, s_now, r.unix0).0;
    let tp = r.sig("pump-trade");
    let mut t = t1 + 10 * MS;
    for (k, d) in up { r.write(k, d, s_now, Some(tp), t); t += 100 * US; }
    r.timers(t + 4 * MS);
    let ev = r.evaluations();
    let last = ev.last().unwrap();
    assert_eq!(last["trigger"]["pool"], json!(b58(&p.pool)));
    assert!(last["routes"].as_array().unwrap().iter().all(|x| x["net"].is_i64()), "priced normally: {last}");
    assert_eq!(last["parts_skew_slots"], json!({ "buy": 0, "sell": 0 }), "slots are compared within a pool only");
    assert_eq!(r.e.store.get(&p.pool).unwrap().slot, sb, "the pool account is the boot's, 10,000 slots old");
    assert_eq!(r.e.store.get(&a.vault0).unwrap().slot, s_idle, "the sell pool is 500 slots old");
    let done = r.finish_and_replay();
    done.check_expected();
}

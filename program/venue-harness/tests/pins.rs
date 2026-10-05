//! Pins (DESIGN.md §7) and formula checks settled against the REAL venue binaries in LiteSVM.
//!
//! * `dlmm_bin_arrays_are_consumed_in_walk_order` (§7.4): which bin-array lists the program accepts.
//! * `pumpswap_matches_design_formulas_and_debit_pin` (§2.1, §7.1): PumpSwap sell / buy_exact_quote_in outputs equal
//!   DESIGN §2.1's integer formulas (fee bps read from the program's own Buy/SellEvent). Pin (§7.1): the buy debit
//!   is `min(x, eff0 + fees(eff0))`, NOT always `x`: with an overrun (eff0 + fees(eff0) > x) the program lowers eff
//!   but keeps fees(eff0), so it debits x; otherwise it debits eff0 + fees(eff0), which is below x when the
//!   separately ceiled fees leave a remainder (seen on 6ejg, creator_fee_bps 200).
//! * `cpmm_and_ammv4_match_design_formulas` (§2.2, §2.3).
//!
//!   cargo test --release --test pins -- --nocapture
use venue_harness::harness::event_disc;
use venue_harness::venues::{pk_at, token_amount, u64_at};
use venue_harness::*;

fn h(fx: &Fixtures, pool: &PoolFixture) -> Harness { Harness::new(fx, &pool.pool_key()).unwrap() }
fn acct_data<'a>(h: &'a Harness, k: &solana_address::Address) -> &'a [u8] { &h.view[k].data }
fn amt(h: &Harness, k: &solana_address::Address) -> u128 { token_amount(acct_data(h, k)).unwrap() as u128 }
fn cdiv(a: u128, b: u128) -> u128 { a.div_ceil(b) }

/// deterministic log-uniform sizes in [lo, hi]
fn sizes(lo: u64, hi: u64, n: usize, seed: u64) -> Vec<u64> {
    let mut s = seed;
    let (l, r) = ((lo.max(1) as f64).ln(), (hi.max(lo + 1) as f64).ln());
    (0..n).map(|_| {
        s = s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407);
        let u = (s >> 11) as f64 / (1u64 << 53) as f64;
        (l + u * (r - l)).exp() as u64
    }).collect()
}

// ------------------------------------------------------------------------------------------------ DLMM (§7.4)

/// Observed on the dumped lb_clmm (deploy slot 423,977,638): the program walks the passed bin arrays with a forward
/// cursor, skipping any array that is not the one it needs next. So
///   - the active bin's array must be passed (else 3005 AccountNotEnoughKeys),
///   - the arrays the swap needs must appear in walk order (reversed or swapped lists fail with 3005 once the walk
///     needs the second array),
///   - extra arrays (a duplicate, one from the other side placed first, one far away) are skipped: same output,
///     ~300-900 CU more each.
#[test]
fn dlmm_bin_arrays_are_consumed_in_walk_order() {
    let fx = Fixtures::load().unwrap();
    let mut checked = 0;
    for p in fx.pools.values().filter(|p| p.venue == Venue::Dlmm) {
        let h = h(&fx, p);
        for dir in Dir::BOTH {
            let def = h.build(dir, 1, &BuildOpts::default()).unwrap().dlmm_arrays;
            if def.len() < 3 { continue; }
            let only = |v: Vec<i64>| BuildOpts { dlmm_arrays: Some(v), ..Default::default() };
            // the smallest ladder size that needs the second array (fails with the active array alone)
            let Some(x) = size_ladder(h.input_reserve(dir), 60).into_iter()
                .find(|&a| !h.swap_opts(dir, a, &only(vec![def[0]])).ok && h.swap_opts(dir, a, &only(def[..2].to_vec())).ok) else { continue };
            let base = h.swap_opts(dir, x, &only(def[..2].to_vec()));
            let other = if dir.zfo() { def[0] + 1 } else { def[0] - 1 };
            let code = |o: &SwapOutcome| o.err.clone().unwrap_or_default();
            let cases: Vec<(&str, Vec<i64>, bool)> = vec![
                ("walk order", def[..3].to_vec(), true),
                ("duplicate active", vec![def[0], def[0], def[1]], true),
                ("other side first", vec![other, def[0], def[1]], true),
                ("far extra", vec![def[0], def[1], *def.last().unwrap()], true),
                ("reversed", vec![def[1], def[0]], false),
                ("active missing", vec![def[1], def[2]], false),
            ];
            for (name, arr, ok) in cases {
                let o = h.swap_opts(dir, x, &only(arr.clone()));
                println!("{} {} x={x} {name:<17} {arr:?} -> ok {} out {} cu {:?} {}", &p.pool[..8], dir.short(), o.ok, o.amount_out, o.cu_venue,
                    if o.ok { "" } else { "3005" });
                assert_eq!(o.ok, ok, "{} {} {name}: {}", p.pool, dir.short(), o.venue_error());
                if ok { assert_eq!(o.amount_out, base.amount_out, "{} {name}: output changed", p.pool); }
                else { assert!(code(&o).contains("Custom(3005)"), "{} {name}: {}", p.pool, o.venue_error()); }
            }
            checked += 1;
        }
    }
    assert!(checked >= 4, "only {checked} DLMM directions had a two-array size");
}

// --------------------------------------------------------------------------------------------- PumpSwap (§2.1)

/// Buy/SellEvent fields used here. `user_quote` is @104: SellEvent.user_quote_amount_out; for buy_exact_quote_in
/// the BuyEvent slot @104 carries `eff` (the quote that enters the curve) and @56 the spendable `x`.
struct PumpEv { lp: u128, pr: u128, cr: u128, bb: u128, cb: u128, user_quote: u128 }
fn pump_event(o: &SwapOutcome, buy: bool) -> PumpEv {
    let d = o.event(&event_disc(if buy { "BuyEvent" } else { "SellEvent" })).expect("Buy/SellEvent");
    let u = |at: usize| u64_at(d, at).unwrap() as u128;
    // fields after coin_creator_fee: buy has track_volume u8 + 5 u64 + ix_name string first
    let tail = if buy { let n = u32::from_le_bytes(d[393..397].try_into().unwrap()) as usize; 397 + n } else { 352 };
    PumpEv { lp: u(64), pr: u(80), cr: u(336), cb: u(tail), bb: u(tail + 16), user_quote: u(104) }
}

/// DESIGN §2.1 exact formulas, fee bps from the event. Every PumpSwap pool, both directions, 400 sizes each.
#[test]
fn pumpswap_matches_design_formulas_and_debit_pin() {
    let fx = Fixtures::load().unwrap();
    let (mut n_sell, mut n_buy, mut n_overrun, mut n_leftover, mut n_sell_zero, mut n_sell_event_diff) = (0, 0, 0, 0, 0, 0);
    let (mut n_short, mut n_eff_fees) = (0, 0);
    for p in fx.pools.values().filter(|p| p.venue == Venue::PumpSwap) {
        let h = h(&fx, p);
        let pool = acct_data(&h, &h.pool);
        // a cashback coin: the engine's leg cannot execute it (tests/swaps.rs)
        if !venue_harness::venues::engine_leg_executes(p.venue, &pool) { continue; }
        let (b_res, q_res) = (amt(&h, &h.tokens.vault0), amt(&h, &h.tokens.vault1));
        let v = i128::from_le_bytes(pool[245..261].try_into().unwrap());
        let qv = (q_res as i128 + v) as u128;
        // sell: base in
        for b in sizes(1_000, (b_res / 2) as u64, 400, 1) {
            let o = h.swap(Dir::ZeroForOne, b);
            if !o.ok {
                // only a sell too small to pay anything may fail: q - (three fee ceils) < 1 gives ExceededSlippage
                // (6004, out 0 < min_out 1) or Overflow (6023, the fee subtraction goes negative)
                let q = qv * b as u128 / (b_res + b as u128);
                let err = o.err.clone().unwrap_or_default();
                assert!(q <= 3 && (err.contains("Custom(6004)") || err.contains("Custom(6023)")), "{} sell {b} (q {q}): {}", p.pool, o.venue_error());
                n_sell_zero += 1;
                continue;
            }
            let e = pump_event(&o, false);
            // a mayhem pool carves no buyback out of its protocol fee (GxqG: 0 bps in every event); user amounts are
            // the same either way (the buyback is a share of the protocol fee)
            assert_eq!((e.cb, e.bb > 0), (0, pool.get(243) != Some(&1)), "{}: cashback / buyback bps (bb {})", p.pool, e.bb);
            let q = qv * b as u128 / (b_res + b as u128);
            let out = q - cdiv(q * e.lp, 10_000) - cdiv(q * e.pr, 10_000) - cdiv(q * e.cr, 10_000);
            assert_eq!(o.amount_out as u128, out, "{} sell {b}: model {out} vs program {}", p.pool, o.amount_out);
            if o.amount_out as u128 != e.user_quote && n_sell_event_diff == 0 {
                let d = o.event(&event_disc("SellEvent")).unwrap();
                println!("{} sell {b}: delivered {} but SellEvent.user_quote_amount_out {} (q {q}, bps lp/pr/cr {}/{}/{}, event coin_creator_fee {})",
                    p.pool, o.amount_out, e.user_quote, e.lp, e.pr, e.cr, u64_at(d, 344).unwrap());
            }
            if o.amount_out as u128 != e.user_quote { n_sell_event_diff += 1; }
            n_sell += 1;
        }
        // buy_exact_quote_in: quote in
        // log-uniform sizes plus dense runs of consecutive x (every rounding residue) at four scales
        let dense = (10_000..11_000).chain(1_000_000..1_001_000).chain(10_000_000..10_002_000).chain(1_000_000_000..1_000_001_000);
        for x in sizes(1_000, (q_res / 2) as u64, 400, 2).into_iter().chain(dense) {
            let o = h.swap(Dir::OneForZero, x);
            assert!(o.ok, "{} buy {x}: {}", p.pool, o.venue_error());
            let e = pump_event(&o, true);
            let x = x as u128;
            let f = e.lp + e.pr + e.cr;
            let fees = |a: u128| cdiv(a * e.lp, 10_000) + cdiv(a * e.pr, 10_000) + cdiv(a * e.cr, 10_000);
            let eff0 = x * 10_000 / (10_000 + f);
            let eff = eff0 - (eff0 + fees(eff0)).saturating_sub(x);
            let out = b_res * (eff - 1) / (qv + eff - 1);
            assert_eq!(o.amount_out as u128, out, "{} buy {x}: model {out} vs program {}", p.pool, o.amount_out);
            assert_eq!(e.user_quote, eff, "{} buy {x}: BuyEvent eff", p.pool);
            // the debit (§7.1): min(x, eff0 + fees(eff0)). With an overrun the program keeps fees(eff0) and lowers
            // eff, so it debits exactly x; without one it debits eff0 + fees(eff0), which can be BELOW x.
            let debit = x.min(eff0 + fees(eff0));
            assert_eq!(o.spent as u128, debit, "{} buy {x}: debit {} (model {debit}; eff+fees(eff) {})", p.pool, o.spent, eff + fees(eff));
            if (o.spent as u128) < x {
                if n_short == 0 { println!("{} buy {x}: debited {} = eff0 {eff0} + fees(eff0) {} < x (bps lp/pr/cr {}/{}/{})", p.pool, o.spent, fees(eff0), e.lp, e.pr, e.cr); }
                n_short += 1;
            }
            if eff0 + fees(eff0) > x && eff + fees(eff) != x {
                if n_eff_fees == 0 { println!("{} buy {x}: overrun, eff {eff} + fees(eff) {} != x but debited x (fees charged on eff0: {})", p.pool, fees(eff), fees(eff0)); }
                n_eff_fees += 1;
            }
            if eff0 + fees(eff0) > x { n_overrun += 1; }
            if eff + fees(eff) < x { n_leftover += 1; }
            n_buy += 1;
        }
    }
    println!("PumpSwap: {n_sell} sells and {n_buy} buy_exact_quote_in exact to the unit ({n_sell_zero} dust sells fail as the model predicts); \
              eff0 overrun-adjusted in {n_overrun} buys; debit < x in {n_short} buys (= eff0 + fees(eff0)); overrun with eff + fees(eff) != x in {n_eff_fees} buys (debit x); \
              eff + fees(eff) < x in {n_leftover} buys; SellEvent.user_quote_amount_out != delivered in {n_sell_event_diff} sells");
    assert!(n_short > 0 && n_eff_fees > 0, "the snapshot no longer exercises both debit cases: widen the scan");
    assert!(n_sell >= 1000 && n_buy >= 1000);
}

/// WP-16 review F6: the exact-out `buy` (base_amount_out, max_quote_amount_in), the instruction third parties send most:
/// the program delivers exactly the base asked for and debits `q + ⌈q·lp/1e4⌉ + ⌈q·pr/1e4⌉ + ⌈q·cr/1e4⌉` with
/// `q = ⌈Qv·out / (B − out)⌉` (fee bps from its BuyEvent): every size from 1 to below the base reserve swaps (a quote
/// amount of 1 at least); 0 fails 6001 ZeroBaseAmount and the whole reserve or more fails too. Every PumpSwap pool the
/// engine's leg executes, sizes from 1 base unit to half the base reserve plus dense runs of consecutive sizes
#[test]
fn pumpswap_exact_out_buy_matches_its_closed_form() {
    let fx = Fixtures::load().unwrap();
    let opts = BuildOpts { exact_out: true, ..Default::default() };
    let (mut n, mut n_fail) = (0, 0);
    for p in fx.pools.values().filter(|p| p.venue == Venue::PumpSwap) {
        let h = h(&fx, p);
        let pool = acct_data(&h, &h.pool);
        if !venue_harness::venues::engine_leg_executes(p.venue, pool) { continue; }
        let b_res = amt(&h, &h.tokens.vault0);
        let qv = (amt(&h, &h.tokens.vault1) as i128 + if pool.len() >= 261 { i128::from_le_bytes(pool[245..261].try_into().unwrap()) } else { 0 }) as u128;
        let dense = (1_000..1_200).chain(1_000_000..1_000_300).chain((b_res as u64 / 1_000)..(b_res as u64 / 1_000 + 300));
        for out in sizes(1, (b_res / 2) as u64, 300, 3).into_iter().chain([0, 1, 2, 3, 10, b_res as u64 - 1, b_res as u64, b_res as u64 + 1]).chain(dense) {
            let o = h.swap_opts(Dir::OneForZero, out, &opts);
            if out == 0 || out as u128 >= b_res {
                assert!(!o.ok, "{} buy out {out} of a {b_res} base reserve swapped", p.pool);
                if out == 0 { assert!(o.venue_error().contains("6001"), "{} buy out 0: {}", p.pool, o.venue_error()); }
                n_fail += 1;
                continue;
            }
            let q = cdiv(qv * out as u128, b_res - out as u128);
            // a quote amount (or debit) past u64 fails the program (6024 Truncation, 6023 Overflow)
            if q.saturating_mul(2) > u64::MAX as u128 {
                if q > u64::MAX as u128 { assert!(!o.ok, "{} buy out {out}: q {q} past u64 swapped", p.pool); n_fail += 1; continue; }
                if !o.ok { n_fail += 1; continue; }
            }
            assert!(o.ok, "{} buy out {out}: {}", p.pool, o.venue_error());
            let e = pump_event(&o, true);
            let debit = q + cdiv(q * e.lp, 10_000) + cdiv(q * e.pr, 10_000) + cdiv(q * e.cr, 10_000);
            assert_eq!(o.amount_out, out, "{} buy out {out}: delivered {}", p.pool, o.amount_out);
            assert_eq!(o.spent as u128, debit, "{} buy out {out}: debit {} vs model {debit} (q {q}, bps {}/{}/{})", p.pool, o.spent, e.lp, e.pr, e.cr);
            n += 1;
        }
    }
    println!("PumpSwap exact-out buy: {n} exact to the unit; {n_fail} sizes of 0, of the whole base reserve or with a quote past u64 refused as the model says");
    assert!(n >= 5_000, "{n}");
}

// ------------------------------------------------------------------------------------- CPMM, AMM v4 (§2.2, §2.3)

#[test]
fn cpmm_and_ammv4_match_design_formulas() {
    let fx = Fixtures::load().unwrap();
    let mut n = 0;
    let mut skipped = vec![];
    for p in fx.pools.values().filter(|p| matches!(p.venue, Venue::RayCpmm | Venue::RayAmmV4)) {
        let h = h(&fx, p);
        // a Token-2022 transfer fee changes both legs' amounts; sizing aborts those (Abort::TransferFee)
        if venues::pool_has_transfer_fee(&h.view, &h.tokens) { skipped.push(p.pool.clone()); continue; }
        let d = acct_data(&h, &h.pool).to_vec();
        let (v0, v1) = (amt(&h, &h.tokens.vault0), amt(&h, &h.tokens.vault1));
        for dir in Dir::BOTH {
            for x in size_ladder(h.input_reserve(dir), 40).into_iter().chain([1, 2, 3, 10, 99, 100, 101, 399, 400, 401]) {
                let o = h.swap(dir, x);
                let x = x as u128;
                let model: Option<u128> = if p.venue == Venue::RayAmmV4 {
                    let (num, den) = (u64_at(&d, 176).unwrap() as u128, u64_at(&d, 184).unwrap() as u128);
                    let (r0, r1) = (v0 - u64_at(&d, 192).unwrap() as u128, v1 - u64_at(&d, 200).unwrap() as u128);
                    let (ri, ro) = if dir.zfo() { (r0, r1) } else { (r1, r0) };
                    let net = x - cdiv(x * num, den);
                    let out = ro * net / (ri + net);
                    (out > 0 && out < ro).then_some(out)
                } else {
                    let cfg = acct_data(&h, &pk_at(&d, 8).unwrap()).to_vec();
                    let t = u64_at(&cfg, 12).unwrap() as u128;
                    let c = if d[390] != 0 { u64_at(&cfg, 108).unwrap() as u128 } else { 0 };
                    let owed = |a: usize, b: usize, cc: usize| (u64_at(&d, a).unwrap() + u64_at(&d, b).unwrap() + u64_at(&d, cc).unwrap()) as u128;
                    let (r0, r1) = (v0 - owed(341, 357, 397), v1 - owed(349, 365, 405));
                    let (ri, ro) = if dir.zfo() { (r0, r1) } else { (r1, r0) };
                    let on_input = d[389] == 0 || (d[389] == 1 && dir.zfo()) || (d[389] == 2 && !dir.zfo());
                    let net = if on_input { x - cdiv(x * (t + c), 1_000_000) } else { x - cdiv(x * t, 1_000_000) };
                    let gross = net * ro / (ri + net);
                    let out = if on_input { gross } else { gross - cdiv(gross * c, 1_000_000) };
                    (out > 0).then_some(out)
                };
                match model {
                    Some(m) => {
                        assert!(o.ok, "{} {} {x}: model {m}, program failed {}", p.pool, dir.short(), o.venue_error());
                        assert_eq!(o.amount_out as u128, m, "{} {} {x}", p.pool, dir.short());
                    }
                    None => assert!(o.failed_or_zero(), "{} {} {x}: model says zero, program gave {}", p.pool, dir.short(), o.amount_out),
                }
                n += 1;
            }
        }
    }
    println!("CPMM + AMM v4: {n} swaps equal DESIGN §2.2/§2.3 to the unit; skipped (transfer-fee mint) {skipped:?}");
    assert!(n >= 200);
}

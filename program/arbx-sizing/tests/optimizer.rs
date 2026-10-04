//! The optimizer and the planner (DESIGN.md §6.1 "Optimizer"): (i) never worse than the engine's amount; (ii)
//! near-optimal against brute force; (iii) the closed form against the golden-section search; (iv) DLMM walks whose
//! fee falls along the walk; (v) BASKET picks the best pair. The exact evaluators are the ground truth here (their
//! own exactness is tests/venues.rs and tests/differential.rs).
mod common;
use arbx_sizing::layout::WSOL;
use arbx_sizing::opt::golden;
use arbx_sizing::{plan, AnyLeg, Kind, Outcome, Plan, PlanIn, QuoteErr, SzFlags, TipParams};
use common::*;

const A: Pk = WSOL;

/* ------------------------------------------------- leg builders ------------------------------------------------- */

/// a constant-product leg A→X (buy) or X→A (sell) with the given reserves of A and X
fn cp_leg(rng: &mut Rng, amm: bool, buy: bool, ra: u64, rx: u64, x: Pk, fee: u64) -> OwnedLeg {
    if amm {
        // coin = X, pc = A: a buy spends pc
        let st = ammv4(rng, rx, ra, fee, 10_000, x, A);
        OwnedLeg::new(Kind::RayAmmV4, !buy, st, if buy { A } else { x })
    } else {
        // token0 = A, token1 = X: a buy is zero_for_one
        let spec = CpmmSpec { r0: ra, r1: rx, trade: fee * 100, creator: 0, enable_creator: false, creator_on: 0, owed0: 0, owed1: 0 };
        let st = cpmm(rng, &spec, A, x, buy);
        OwnedLeg::new(Kind::RayCpmm, buy, st, if buy { A } else { x })
    }
}

/// a PumpSwap pool with base X (its key is the pool's base mint) and quote A
fn pump_pair(rng: &mut Rng, ra: u64, rx: u64) -> PumpAccts {
    pump(rng, &PumpSpec { base: rx, quote: ra, supply: rx.saturating_mul(10), ..Default::default() })
}

/// a DLMM pair X/Y = X/A around `active`, `depth` of A per bin on the bid side (below) and the matching X above
fn dlmm_pair(rng: &mut Rng, x: Pk, bin_step: u16, active: i32, depth: u64, spec_f: impl Fn(&mut DlmmSpec)) -> (Acct, Acct, Acct, Vec<Acct>) {
    let mut spec = DlmmSpec { bin_step, active, idx_ref: active, last_ts: CLOCK.unix_timestamp, vfc: 0, bins: vec![], ..Default::default() };
    for id in active - 100..=active + 100 {
        let price = dlmm_price(bin_step, id) as f64 / 18446744073709551616.0;
        let ay = depth / 2 + rng.range(0, depth);
        let ax = (ay as f64 / price) as u64;
        let (bx, by) = if id < active { (0, ay) } else if id > active { (ax, 0) } else { (ax / 2, ay / 2) };
        spec.bins.push((id, bx, by, (0, 0, 0)));
    }
    spec_f(&mut spec);
    dlmm(rng, &spec, x, A)
}

fn dlmm_leg(p: &(Acct, Acct, Acct, Vec<Acct>), buy: bool) -> OwnedLeg {
    // X = token_x, A = token_y: a buy is Y→X (swap_for_y false)
    let st = dlmm_state(&p.0, &p.1, &p.2, &p.3, !buy);
    OwnedLeg::new(Kind::Dlmm, !buy, st, if buy { A } else { p.1.key })
}

/* --------------------------------------------------- harness --------------------------------------------------- */

struct Run { plan: Plan }

fn run(legs: &[OwnedLeg], pairs: &[(u8, u8)], cap: u64, min_size: u64, e: u64, flags: u8, tip: Option<TipParams>, min_profit: u64) -> Run {
    let v = views(legs);
    let ins = leg_ins(legs, &v);
    let p = PlanIn { clock: CLOCK, cap, min_size, engine_amount: e, min_profit, tip, flags: SzFlags(flags), max_iters: 24, lamport_offset: 0, legs: &ins, pairs, pda };
    Run { plan: plan(&p).expect("desc error") }
}

/// exact profit of a pair at x (the ground truth): the guard's quote delta, sell-leg output minus buy-leg debit
fn exact(l0: &AnyLeg, l1: &AnyLeg, x: u64) -> Option<i128> {
    let q0 = l0.quote(x).ok()?;
    let q1 = l1.quote(q0.out).ok()?;
    Some(q1.out as i128 - q0.spent as i128)
}

/// the best exact profit on [lo, hi]: exhaustive when small, else a 4096-point grid and an exhaustive ±4000 around
/// the three best grid points
fn oracle(l0: &AnyLeg, l1: &AnyLeg, lo: u64, hi: u64) -> Option<(u64, i128)> {
    let mut best: Option<(u64, i128)> = None;
    let keep = |x: u64, best: &mut Option<(u64, i128)>| { if let Some(v) = exact(l0, l1, x) { if best.map_or(true, |b| v > b.1) { *best = Some((x, v)); } } };
    if hi - lo <= 300_000 {
        for x in lo..=hi { keep(x, &mut best); }
        return best;
    }
    let mut grid: Vec<(i128, u64)> = (0..=4096u64).map(|i| lo + ((hi - lo) as u128 * i as u128 / 4096) as u64)
        .filter_map(|x| exact(l0, l1, x).map(|v| (v, x))).collect();
    grid.sort_by(|a, b| b.cmp(a));
    for &(_, gx) in grid.iter().take(3) {
        let step = ((hi - lo) / 4096).max(1);
        let (a, b) = (gx.saturating_sub(step).max(lo), gx.saturating_add(step).min(hi));
        // exhaustive near the grid point when the cell is small, else a fine sub-grid then exhaustive
        if b - a <= 8_000 { for x in a..=b { keep(x, &mut best); } } else {
            let mut sub: Vec<(i128, u64)> = (0..=4000u64).map(|i| a + ((b - a) as u128 * i as u128 / 4000) as u64).filter_map(|x| exact(l0, l1, x).map(|v| (v, x))).collect();
            sub.sort_by(|p, q| q.cmp(p));
            let s2 = ((b - a) / 4000).max(1);
            if let Some(&(_, sx)) = sub.first() { for x in sx.saturating_sub(s2 + 2000).max(lo)..=sx.saturating_add(s2 + 2000).min(hi) { keep(x, &mut best); } }
        }
    }
    best
}

/// DESIGN.md §3.1: the integer noise bound ε = 3 + 2·p1 + p0·p1 (p0 = X per A at the optimum, p1 = A per X)
fn eps(l0: &AnyLeg, l1: &AnyLeg, x: u64) -> f64 {
    let y = l0.quote(x).map(|q| q.out).unwrap_or(1).max(1);
    let z = l1.quote(y).map(|q| q.out).unwrap_or(1).max(1);
    let (p0, p1) = (y as f64 / x.max(1) as f64, z as f64 / y as f64);
    3.0 + 2.0 * p1 + p0 * p1
}

fn parse<'a>(l: &'a OwnedLeg, refs: &'a [arbx_sizing::AcctRef<'a>]) -> AnyLeg<'a> { any_leg(l, refs) }

#[derive(Default, Debug)]
struct Stats { cases: u32, profitable: u32, beat_e: u32, worst_ratio: f64, worst_abs: i128, sized_above_e: u32 }

/// Plan one pair and check (i) never worse and (ii) near-optimal against the oracle
fn check_pair(legs: &[OwnedLeg], cap: u64, min_size: u64, e: u64, st: &mut Stats, what: &str) {
    let v = views(legs);
    let (l0, l1) = (parse(&legs[0], &v.refs[0]), parse(&legs[1], &v.refs[1]));
    let r = run(legs, &[(0, 1)], cap, min_size, e, 0, None, 1);
    let p = r.plan;
    st.cases += 1;
    assert!(matches!(p.outcome, Outcome::Sized | Outcome::NoProfit), "{what}: {p:?}");
    let chosen = exact(&l0, &l1, p.amount);
    // the planner's own record is the exact profit of what it chose
    if p.reason != arbx_sizing::Reason::INFEASIBLE { assert_eq!(chosen, Some(p.modeled_profit), "{what}: {p:?}"); }
    assert!(p.amount >= min_size && p.amount <= cap, "{what}: amount {} outside [{min_size}, {cap}]", p.amount);
    // (i) never worse than e
    let e_val = if e <= cap { exact(&l0, &l1, e) } else { None };
    assert_eq!(p.modeled_profit_e, e_val, "{what}");
    if let Some(ev) = e_val { assert!(p.modeled_profit >= ev, "{what}: chose {} ({}) below e {e} ({ev})", p.amount, p.modeled_profit); if p.modeled_profit > ev { st.beat_e += 1; } }
    // (ii) near-optimal
    let Some((bx, bv)) = oracle(&l0, &l1, min_size, cap) else { assert_eq!(p.outcome, Outcome::NoProfit); return };
    if bv < 1 {
        // nothing clears min_profit = 1: every size fails the guard, so the verdict matters, not the size
        assert_eq!(p.outcome, Outcome::NoProfit, "{what}: best {bv} but {p:?}");
        return;
    }
    st.profitable += 1;
    let tol = 2.0 * eps(&l0, &l1, bx) + 2.0;
    let loss = bv - chosen.unwrap_or(i128::MIN / 2);
    let ratio = loss as f64 / tol;
    if ratio > st.worst_ratio { st.worst_ratio = ratio; st.worst_abs = loss; }
    assert!(loss as f64 <= tol || loss * 1_000_000 <= bv.abs(), "{what}: best {bv} at {bx}, chose {:?} at {} (loss {loss}, tol {tol:.1}); plan {p:?}", chosen, p.amount);
    if p.amount != e { st.sized_above_e += 1; }
}

/* ----------------------------------------------------- tests ----------------------------------------------------- */

/// (i)+(ii) constant-product mixes (CPMM, AMM v4, PumpSwap both ways), small pools, exhaustive oracle
#[test]
fn cp_mixes_small_pools_exhaustive() {
    let mut rng = Rng(201);
    let mut st = Stats::default();
    for case in 0..400 {
        let x: Pk = rng.key();
        let ra0 = rng.range(20_000, 1_000_000);
        let price = rng.range(1, 40) as f64 / 10.0; // A per X
        let gap = rng.range(0, 1200) as f64 / 10_000.0 - 0.02;
        let rx0 = (ra0 as f64 / price) as u64;
        let ra1 = rng.range(20_000, 1_000_000);
        let rx1 = (ra1 as f64 / (price * (1.0 + gap))) as u64;
        let kinds = (rng.range(0, 2), rng.range(0, 2));
        let mut legs = vec![];
        for (i, k) in [kinds.0, kinds.1].into_iter().enumerate() {
            let buy = i == 0;
            let (ra, rx) = if buy { (ra0, rx0) } else { (ra1, rx1) };
            legs.push(match k {
                0 => { let f = rng.range(0, 100); cp_leg(&mut rng, false, buy, ra, rx, x, f) }
                1 => { let f = rng.range(1, 100); cp_leg(&mut rng, true, buy, ra, rx, x, f) }
                _ => {
                    let p = pump_pair(&mut rng, ra, rx);
                    let mut l = OwnedLeg::pump(&p, !buy);
                    // X is the pump pool's base mint: rebuild the other leg on it after the loop
                    l.input_mint = if buy { A } else { p.base_key() };
                    l
                }
            });
        }
        // a pump leg fixes X to its own base mint: rebuild a non-pump partner on that mint
        if legs[0].desc.kind == Kind::PumpBuy && legs[1].desc.kind == Kind::PumpSell { continue; }
        for i in 0..2 {
            if matches!(legs[i].desc.kind, Kind::PumpBuy | Kind::PumpSell) {
                let xk = legs[i].state[2].key;
                let j = 1 - i;
                let (ra, rx) = if j == 0 { (ra0, rx0) } else { (ra1, rx1) };
                let f = rng.range(1, 100);
                legs[j] = cp_leg(&mut rng, kinds_amm(legs[j].desc.kind), j == 0, ra, rx, xk, f);
            }
        }
        let cap = rng.range(1_000, 2_000_000);
        let e = rng.range(1, cap);
        let min_size = rng.range(1, e.min(50));
        check_pair(&legs, cap, min_size, e, &mut st, &format!("cp case {case}"));
    }
    eprintln!("cp mixes, small pools: {st:?}");
    assert!(st.profitable > 100 && st.beat_e > 100);
}

fn kinds_amm(k: Kind) -> bool { k == Kind::RayAmmV4 }

/// (i)+(ii) large constant-product pools (realistic reserves), grid oracle
#[test]
fn cp_mixes_large_pools() {
    let mut rng = Rng(202);
    let mut st = Stats::default();
    for case in 0..200 {
        let ra0 = rng.log(1_000_000_000, 1 << 44);
        let rx0 = rng.log(1_000_000, 1 << 56);
        let price = ra0 as f64 / rx0 as f64;
        let gap = rng.range(0, 800) as f64 / 10_000.0;
        let ra1 = rng.log(1_000_000_000, 1 << 44);
        let rx1 = (ra1 as f64 / (price * (1.0 + gap))).max(1000.0) as u64;
        let p = pump_pair(&mut rng, ra1, rx1);
        let xk = p.base_key();
        let legs = vec![cp_leg(&mut rng, case % 2 == 0, true, ra0, rx0, xk, 25), OwnedLeg::pump(&p, true)];
        let cap = rng.log(1_000_000, 1 << 40);
        let e = rng.range(1, cap);
        check_pair(&legs, cap, 1, e, &mut st, &format!("large cp case {case}"));
    }
    eprintln!("cp mixes, large pools (CPMM/AMM v4 buy → PumpSwap sell): {st:?}");
    assert!(st.profitable > 50);
}

/// (i)+(ii) DLMM against constant product, both directions
#[test]
fn dlmm_mixes() {
    let mut rng = Rng(203);
    let mut st = Stats::default();
    for case in 0..160 {
        let x: Pk = rng.key();
        let bin_step = [10u16, 25, 100][rng.range(0, 2) as usize];
        let active = rng.range(0, 400) as i32 - 200;
        let price = dlmm_price(bin_step, active) as f64 / 18446744073709551616.0; // A per X
        let depth = rng.log(10_000, 10_000_000_000);
        let fee_state = rng.range(0, 2);
        let pair = dlmm_pair(&mut rng, x, bin_step, active, depth, |s| {
            s.base_factor = 10_000;
            if fee_state > 0 { s.vfc = 20_000; s.max_va = 200_000; s.v_ref = 30_000; s.idx_ref = s.active + if fee_state == 1 { 15 } else { -15 }; }
        });
        let gap = rng.range(0, 1500) as f64 / 10_000.0 - 0.02;
        let ra = rng.log(10_000, 1 << 44);
        let dlmm_buys = case % 2 == 0;
        let cp_price = if dlmm_buys { price * (1.0 + gap) } else { price / (1.0 + gap) };
        let rx = (ra as f64 / cp_price).max(100.0) as u64;
        let cp = cp_leg(&mut rng, case % 4 < 2, !dlmm_buys, ra, rx, x, 25);
        let legs = if dlmm_buys { vec![dlmm_leg(&pair, true), cp] } else { vec![cp, dlmm_leg(&pair, false)] };
        let cap = rng.log(1_000, (depth as u128 * 60).min(u64::MAX as u128) as u64);
        let e = rng.range(1, cap);
        check_pair(&legs, cap, 1, e, &mut st, &format!("dlmm case {case}"));
    }
    eprintln!("DLMM ↔ CPMM-family: {st:?}");
    assert!(st.profitable > 30);
}

/// (iv) DLMM ↔ DLMM, with the fee falling along the walk (idx_ref ahead): the non-concavity guard keeps walking
#[test]
fn dlmm_dlmm_with_fee_falling_along_the_walk() {
    let mut rng = Rng(204);
    let mut st = Stats::default();
    for case in 0..120 {
        let x: Pk = rng.key();
        let bin_step = [1u16, 10, 25][rng.range(0, 2) as usize];
        let active = rng.range(0, 200) as i32 - 100;
        let gap_bins = rng.range(0, 30) as i32;
        let depth = rng.log(100_000, 10_000_000_000);
        // the buy pair is cheaper by `gap_bins` bins; both have steep variable fees that FALL toward idx_ref ahead
        let ahead = rng.range(1, 12) as i32;
        let steep = |s: &mut DlmmSpec, toward: i32| { s.base_factor = 5_000; s.vfc = 400_000; s.max_va = 400_000; s.v_ref = 0; s.idx_ref = s.active + toward; };
        let buy = dlmm_pair(&mut rng, x, bin_step, active - gap_bins, depth, |s| steep(s, ahead));
        let sell = dlmm_pair(&mut rng, x, bin_step, active, depth, |s| steep(s, -ahead));
        let legs = vec![dlmm_leg(&buy, true), dlmm_leg(&sell, false)];
        let cap = rng.log(1_000, (depth as u128 * 40).min(u64::MAX as u128) as u64);
        let e = rng.range(1, cap);
        check_pair(&legs, cap, 1, e, &mut st, &format!("dlmm-dlmm case {case}"));
    }
    eprintln!("DLMM ↔ DLMM, fee falling along the walk: {st:?}");
    assert!(st.profitable > 20);
}

/// (i)+(ii) DAMM v2 (the real vector pools) against a constant-product pool on the same mints, both directions
#[test]
fn dammv2_mixes() {
    let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../testdata/dammv2-vectors.json")).unwrap()).unwrap();
    let mut rng = Rng(205);
    let mut st = Stats::default();
    let clock_now = arbx_sizing::Clock { slot: 452_967_433, unix_timestamp: 1_791_039_568, epoch: 0 };
    for (name, pv) in v["pools"].as_object().unwrap() {
        let raw = b64(pv["b64"].as_str().unwrap());
        let p = arbx_sizing::venue::dammv2::decode(&raw).unwrap();
        let (ma, mb) = (*arbx_sizing::math::key_at(&raw, 168).unwrap(), *arbx_sizing::math::key_at(&raw, 200).unwrap());
        let ka = Acct { key: rng.key(), owner: arbx_sizing::layout::DAMM_V2, data: raw.clone() };
        // mints as plain SPL (the vector pools' Token-2022 sides are scanned elsewhere)
        let (mint_a, mint_b) = (mint(ma, 0, false, None), mint(mb, 0, false, None));
        for a_is_x in [true, false] {
            // A = the quote side; X = the other. price of a in b = (sqrt/2^64)^2
            let pab = (p.sqrt_price as f64 / 18446744073709551616.0).powi(2);
            let (xk, ak, price_x_in_a) = if a_is_x { (ma, mb, pab) } else { (mb, ma, 1.0 / pab) };
            for damm_buys in [true, false] {
                let gap = rng.range(0, 600) as f64 / 10_000.0;
                let ra = rng.log(1_000_000, 1 << 50);
                let cp_price = if damm_buys { price_x_in_a * (1.0 + gap) } else { price_x_in_a / (1.0 + gap) };
                let rx = (ra as f64 / cp_price).clamp(1000.0, 1.8e19) as u64;
                // the CP leg on (ak, xk); token0 = A
                let spec = CpmmSpec { r0: ra, r1: rx, trade: 2_500, creator: 0, enable_creator: false, creator_on: 0, owed0: 0, owed1: 0 };
                let cp = { let st = cpmm(&mut rng, &spec, ak, xk, !damm_buys); OwnedLeg::new(Kind::RayCpmm, !damm_buys, st, if damm_buys { xk } else { ak }) };
                // damm leg: input A when it buys
                let damm_in_a_side = if damm_buys { ak } else { xk };
                let a_to_b = damm_in_a_side == ma;
                let dl = OwnedLeg::new(Kind::DammV2, a_to_b, vec![ka.clone(), mint_a.clone(), mint_b.clone()], damm_in_a_side);
                let legs = if damm_buys { vec![dl, cp] } else { vec![cp, dl] };
                // the planner under the vectors' clock
                let vv = views(&legs);
                let ins = leg_ins(&legs, &vv);
                let parsed: Vec<_> = ins.iter().map(|l| AnyLeg::parse(l, &clock_now, pda).unwrap().leg).collect();
                let (Ok(l0), Ok(l1)) = (parsed[0], parsed[1]) else { continue };
                let cap = rng.log(1_000, 1 << 44);
                let e = rng.range(1, cap);
                let pi = PlanIn { clock: clock_now, cap, min_size: 1, engine_amount: e, min_profit: 1, tip: None, flags: SzFlags(0), max_iters: 0, lamport_offset: 0, legs: &ins, pairs: &[(0, 1)], pda };
                let pl = plan(&pi).unwrap();
                st.cases += 1;
                if pl.outcome == Outcome::Fallback { continue; } // rate limiter pools: model refused
                let ev = exact(&l0, &l1, e);
                if let Some(ev) = ev { assert!(pl.modeled_profit >= ev, "{name}: {pl:?} below e {ev}"); if pl.modeled_profit > ev { st.beat_e += 1; } }
                if let Some((bx, bv)) = oracle(&l0, &l1, 1, cap) {
                    let chosen = exact(&l0, &l1, pl.amount).unwrap_or(i128::MIN / 2);
                    if bv < 1 { assert_eq!(pl.outcome, Outcome::NoProfit); continue; }
                    st.profitable += 1;
                    let tol = 2.0 * eps(&l0, &l1, bx) + 2.0;
                    let loss = bv - chosen;
                    st.worst_ratio = st.worst_ratio.max(loss as f64 / tol);
                    assert!(loss as f64 <= tol || loss * 1_000_000 <= bv.abs(), "{name} a_is_x={a_is_x} damm_buys={damm_buys}: best {bv} at {bx}, chose {chosen} at {} tol {tol}; {pl:?}", pl.amount);
                }
            }
        }
    }
    eprintln!("DAMM v2 ↔ CPMM: {st:?}");
    assert!(st.profitable > 10);
}

/// (iii) on random constant-product pairs the closed form is at least as good as a 24-iteration golden search,
/// and both are within the §3.6 bound of the optimum
#[test]
fn closed_form_vs_golden() {
    let mut rng = Rng(206);
    let (mut n, mut cf_better, mut equal, mut worst_golden_loss) = (0, 0, 0, 0i128);
    for _ in 0..300 {
        let x: Pk = rng.key();
        let ra0 = rng.log(1_000_000_000, 1 << 42);
        let rx0 = rng.log(1_000_000, 1 << 50);
        let price = ra0 as f64 / rx0 as f64;
        let ra1 = rng.log(1_000_000_000, 1 << 42);
        let rx1 = (ra1 as f64 / (price * (1.0 + rng.range(60, 800) as f64 / 10_000.0))) as u64;
        let legs = vec![cp_leg(&mut rng, false, true, ra0, rx0, x, 25), cp_leg(&mut rng, true, false, ra1, rx1, x, 25)];
        let v = views(&legs);
        let (l0, l1) = (parse(&legs[0], &v.refs[0]), parse(&legs[1], &v.refs[1]));
        let cap = ra0.min(ra1);
        let r = run(&legs, &[(0, 1)], cap, 1, 1, 0, None, 1).plan;
        let mut ev = |x: u64| exact(&l0, &l1, x);
        let (_, gv) = golden(1, cap, 24, &mut ev).unwrap();
        n += 1;
        if r.modeled_profit > gv { cf_better += 1 } else if r.modeled_profit == gv { equal += 1 }
        let (_, bv) = oracle(&l0, &l1, 1, cap).unwrap();
        assert!(bv - r.modeled_profit <= 2 * eps(&l0, &l1, r.amount) as i128 + 2, "closed form {} vs best {bv}", r.modeled_profit);
        worst_golden_loss = worst_golden_loss.max(bv - gv);
        assert!(r.modeled_profit + 2 * eps(&l0, &l1, r.amount) as i128 + 2 >= gv, "golden {gv} beats the closed form {} by more than 2ε", r.modeled_profit);
    }
    eprintln!("closed form vs golden (24 iterations): {n} pairs; closed form strictly better {cf_better}, equal {equal}; golden's worst loss to the optimum {worst_golden_loss}");
}

/// (v) BASKET: three pairs over four legs (DESIGN.md §4.4 shape: (0,1) (0,2) (3,1)); the plan's pair is the
/// brute-force best pair (up to the tolerance), and never below pair 0 at e
#[test]
fn basket_picks_the_best_pair() {
    let mut rng = Rng(207);
    let (mut n, mut agree, mut close, mut profitable) = (0, 0, 0, 0);
    for case in 0..120 {
        let x: Pk = rng.key();
        let base = 1.0 + rng.range(0, 100) as f64 / 100.0;
        // leg 0, 3: buys (A→X); legs 1, 2: sells (X→A), at random price offsets
        let mut leg = |buy: bool, off: f64, amm: bool| {
            let ra = rng.log(1_000_000_000, 1 << 40);
            let rx = (ra as f64 / (base * (1.0 + off))) as u64;
            cp_leg(&mut rng, amm, buy, ra, rx, x, 25)
        };
        let o: Vec<f64> = (0..4).map(|_| 0.0).collect::<Vec<_>>();
        let _ = o;
        let offs = [0.0, 0.01 + (case % 7) as f64 * 0.004, 0.005 + (case % 5) as f64 * 0.006, -0.01 + (case % 3) as f64 * 0.01];
        let legs = vec![leg(true, offs[3], false), leg(false, offs[1], true), leg(false, offs[2], false), leg(true, offs[3] - 0.004, true)];
        let pairs = [(0u8, 1u8), (0, 2), (3, 1)];
        let v = views(&legs);
        let parsed: Vec<AnyLeg> = (0..4).map(|i| parse(&legs[i], &v.refs[i])).collect();
        let cap = rng.log(1_000_000, 1 << 36);
        let e = rng.range(1, cap);
        let r = run(&legs, &pairs, cap, 1, e, 0, None, 1).plan;
        let bests: Vec<i128> = pairs.iter().map(|&(b, s)| oracle(&parsed[b as usize], &parsed[s as usize], 1, cap).map_or(i128::MIN, |o| o.1)).collect();
        let (bi, bv) = bests.iter().enumerate().max_by_key(|(_, v)| **v).map(|(i, v)| (i, *v)).unwrap();
        n += 1;
        let (pb, ps) = pairs[r.pair as usize];
        let got = exact(&parsed[pb as usize], &parsed[ps as usize], r.amount).unwrap();
        assert_eq!(got, r.modeled_profit);
        if let Some(ev) = exact(&parsed[0], &parsed[1], e) { assert!(got >= ev, "basket below pair 0 at e"); }
        if bv < 1 { assert_eq!(r.outcome, Outcome::NoProfit); continue; }
        let tol = 2 * eps(&parsed[pairs[bi].0 as usize], &parsed[pairs[bi].1 as usize], 1_000_000) as i128 + 2;
        assert!(bv - got <= tol || (bv - got) * 1_000_000 <= bv.abs(), "case {case}: chose pair {} ({got}) but pair {bi} reaches {bv}", r.pair);
        if r.pair as usize == bi { agree += 1 } else { close += 1 }
        profitable += 1;
        assert!(r.evals <= 4 + 3, "basket evals {}", r.evals);
    }
    eprintln!("basket: {n} cases, {profitable} profitable; same pair as brute force {agree}, a different pair within the tolerance {close}");
    assert!(profitable > 30);
}

/// Outcomes and flags: Fallback on a model abort (pair 0 at e), SHADOW, EARLY_ABORT's NoProfit verdict with a CPI
/// tip, the basket dropping an aborted pair, and DescErrors for an inconsistent route
#[test]
fn outcomes_and_desc_errors() {
    let mut rng = Rng(208);
    let x: Pk = rng.key();
    let (ra, rx) = (100_000_000_000u64, 50_000_000_000_000u64);
    let buy = cp_leg(&mut rng, false, true, ra, rx, x, 25);
    let sell = cp_leg(&mut rng, true, false, ra, rx * 95 / 100, x, 25);
    // profitable: Sized, above e
    let r = run(&[buy.clone(), sell.clone()], &[(0, 1)], 10_000_000_000, 1, 1_000, 0, None, 1).plan;
    assert_eq!(r.outcome, Outcome::Sized);
    assert!(r.amount > 1_000 && r.modeled_profit > r.modeled_profit_e.unwrap() && r.x_star > 0, "{r:?}");
    // SHADOW: planned, outcome Shadow
    let s = run(&[buy.clone(), sell.clone()], &[(0, 1)], 10_000_000_000, 1, 1_000, SzFlags::SHADOW, None, 1).plan;
    assert_eq!((s.outcome, s.amount), (Outcome::Shadow, r.amount));
    // min_profit above what is possible: NoProfit (the shell reverts under EARLY_ABORT)
    let s = run(&[buy.clone(), sell.clone()], &[(0, 1)], 10_000_000_000, 1, 1_000, SzFlags::EARLY_ABORT, None, u64::MAX >> 2).plan;
    assert_eq!((s.outcome, s.reason), (Outcome::NoProfit, arbx_sizing::Reason::NO_PROFIT));
    // a CPI tip of 100% of g: g − tip = 0 < min_profit 1
    let t = TipParams { bps: 10_000, floor: 0, cap: u64::MAX };
    let s = run(&[buy.clone(), sell.clone()], &[(0, 1)], 10_000_000_000, 1, 1_000, 0, Some(t), 1).plan;
    assert_eq!(s.outcome, Outcome::NoProfit);
    // reversed gap: nothing profitable; the best feasible candidate still planned (min_size or e)
    let s = run(&[cp_leg(&mut rng, false, true, ra, rx * 95 / 100, x, 25), cp_leg(&mut rng, true, false, ra, rx, x, 25)], &[(0, 1)], 10_000_000_000, 1, 1_000, 0, None, 1).plan;
    assert_eq!(s.outcome, Outcome::NoProfit);
    assert!(s.amount == 1 || s.amount == 1_000);
    // a model abort (CPMM swap disabled) → Fallback at e, reason Cpmm(SwapDisabled)
    let mut bad = buy.clone();
    bad.state[0].data[329] = 4;
    let f = run(&[bad.clone(), sell.clone()], &[(0, 1)], 10_000_000_000, 1, 1_000, 0, None, 1).plan;
    assert_eq!((f.outcome, f.pair, f.amount), (Outcome::Fallback, 0, 1_000));
    assert_eq!(f.reason, arbx_sizing::Abort::Cpmm(arbx_sizing::error::CpmmWhy::SwapDisabled).code());
    // basket: pair 0's buy leg aborts, pair 1 (3 → 1) still plans
    let buy2 = cp_leg(&mut rng, true, true, ra, rx, x, 25);
    let sell2 = cp_leg(&mut rng, false, false, ra, rx * 97 / 100, x, 25);
    let b = run(&[bad.clone(), sell.clone(), sell2.clone(), buy2.clone()], &[(0, 1), (0, 2), (3, 1)], 10_000_000_000, 1, 1_000, 0, None, 1).plan;
    assert_eq!((b.outcome, b.pair), (Outcome::Sized, 2));
    assert_eq!(b.modeled_profit_e, None);
    // DescErrors: same pool twice, mint chain broken, wrong owner, wrong input mint, wrong program
    let desc_err = |legs: &[OwnedLeg], pairs: &[(u8, u8)]| {
        let vv = views(legs);
        let ins = leg_ins(legs, &vv);
        plan(&PlanIn { clock: CLOCK, cap: 1 << 40, min_size: 1, engine_amount: 1000, min_profit: 1, tip: None, flags: SzFlags(0), max_iters: 0, lamport_offset: 0, legs: &ins, pairs, pda }).unwrap_err().code
    };
    use arbx_sizing::DescCode;
    let mut same_pool = sell.clone();
    same_pool.state = buy.state.clone();
    same_pool.desc = buy.desc;
    same_pool.desc.base_or_token0_in = !buy.desc.base_or_token0_in;
    let mut sp = same_pool.clone();
    sp.state.swap(2, 3); sp.state.swap(4, 5); sp.input_mint = x;
    assert_eq!(desc_err(&[buy.clone(), sp], &[(0, 1)]), DescCode::SamePool);
    let other = rng.key();
    let other_x = cp_leg(&mut rng, true, false, ra, rx, other, 25);
    assert_eq!(desc_err(&[buy.clone(), other_x], &[(0, 1)]), DescCode::MintChain);
    let mut wrong_owner = sell.clone(); wrong_owner.state[0].owner = [7u8; 32];
    assert_eq!(desc_err(&[buy.clone(), wrong_owner], &[(0, 1)]), DescCode::Owner);
    let mut wrong_in = sell.clone(); wrong_in.input_mint = A;
    assert_eq!(desc_err(&[buy.clone(), wrong_in], &[(0, 1)]), DescCode::InputMint);
    let mut wrong_vault = buy.clone(); wrong_vault.state[2].key = [5u8; 32];
    assert_eq!(desc_err(&[wrong_vault, sell.clone()], &[(0, 1)]), DescCode::Key);
    let mut wrong_kind = buy.clone(); wrong_kind.desc.kind = Kind::DammV2;
    assert_eq!(desc_err(&[wrong_kind, sell.clone()], &[(0, 1)]), DescCode::StateCount);
    let mut wrong_dir = buy.clone(); wrong_dir.desc.base_or_token0_in = false;
    assert_eq!(desc_err(&[wrong_dir, sell.clone()], &[(0, 1)]), DescCode::Key);
    assert_eq!(desc_err(&[buy.clone(), sell.clone()], &[(0, 2)]), DescCode::PairIndex);
    // e above the cap (quote balance short): e is not evaluated, the plan still sizes
    let r = run(&[buy.clone(), sell.clone()], &[(0, 1)], 500, 1, 1_000, 0, None, 1).plan;
    assert!(r.modeled_profit_e.is_none() && r.amount <= 500);
}

/// REVIEW.md F5: a DAMM v2 leg with the rate limiter in force for its direction (b→a) cannot execute through the
/// engine's 14-account leg (the program wants the instructions sysvar: 6049 at every size), so the leg aborts at
/// parse and the route falls back to `e`, with or without SEARCH (the planner never sizes a pair that cannot
/// execute). The other direction (a→b) is not limited and sizes normally.
#[test]
fn rate_limited_damm_refuses_with_and_without_search() {
    let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../testdata/dammv2-vectors.json")).unwrap()).unwrap();
    let mut rng = Rng(209);
    let mut found = 0;
    let rl = arbx_sizing::Abort::Damm(arbx_sizing::error::DammWhy::RateLimiter);
    for (_, pv) in v["pools"].as_object().unwrap() {
        let mut raw = b64(pv["b64"].as_str().unwrap());
        // force the rate limiter: base fee mode 2, in force for b→a right after activation
        raw[16] = arbx_sizing::venue::dammv2::BASE_FEE_RATE_LIMITER;
        put_u64(&mut raw, 8, 10_000_000); // cliff 1%
        put(&mut raw, 8 + 14, &100u16.to_le_bytes()); // fee_increment_bps
        put(&mut raw, 8 + 16, &1_000_000u32.to_le_bytes()); // max_limiter_duration
        put(&mut raw, 8 + 20, &5_000u32.to_le_bytes()); // max_fee_bps
        put_u64(&mut raw, 8 + 24, 1_000_000_000); // reference amount
        let p = arbx_sizing::venue::dammv2::decode(&raw).unwrap();
        let clock = arbx_sizing::Clock { slot: p.activation_point.saturating_add(10), unix_timestamp: p.activation_point as i64 + 10, epoch: 0 };
        let (ma, mb) = (*arbx_sizing::math::key_at(&raw, 168).unwrap(), *arbx_sizing::math::key_at(&raw, 200).unwrap());
        let Ok(limited) = arbx_sizing::venue::dammv2::parse_with_limiter(&raw, false, true, &clock) else { continue };
        if limited.fee_fixed.is_some() { continue; }
        assert_eq!(arbx_sizing::venue::dammv2::parse(&raw, false, true, &clock).unwrap_err(), rl);
        // a→b is not limited: it parses with a fixed fee
        if let Ok(l) = arbx_sizing::venue::dammv2::parse(&raw, true, true, &clock) { assert!(l.fee_fixed.is_some()); }
        // DAMM buys a with b (b→a, the limited direction); a CP pool sells a for b at a premium
        let pab = (p.sqrt_price as f64 / 18446744073709551616.0).powi(2);
        let ra = 1u64 << 40;
        let rx = ((ra as f64) / (pab * 1.05)).clamp(1000.0, 1.8e19) as u64;
        let spec = CpmmSpec { r0: ra, r1: rx, trade: 2_500, creator: 0, enable_creator: false, creator_on: 0, owed0: 0, owed1: 0 };
        let cp = { let st = cpmm(&mut rng, &spec, mb, ma, false); OwnedLeg::new(Kind::RayCpmm, false, st, ma) };
        let dl = OwnedLeg::new(Kind::DammV2, false, vec![Acct { key: rng.key(), owner: arbx_sizing::layout::DAMM_V2, data: raw.clone() }, mint(ma, 0, false, None), mint(mb, 0, false, None)], mb);
        let legs = vec![dl, cp];
        let vv = views(&legs);
        let ins = leg_ins(&legs, &vv);
        let mk = |flags: u8| PlanIn { clock, cap: 1 << 36, min_size: 1, engine_amount: 1_000_000, min_profit: 1, tip: None, flags: SzFlags(flags), max_iters: 24, lamport_offset: 0, legs: &ins, pairs: &[(0, 1)], pda };
        for flags in [0, SzFlags::SEARCH, SzFlags::SEARCH | SzFlags::EARLY_ABORT] {
            let r = plan(&mk(flags)).unwrap();
            assert_eq!((r.outcome, r.reason, r.amount), (Outcome::Fallback, rl.code(), 1_000_000), "flags {flags:#x}: {r:?}");
        }
        found += 1;
    }
    assert!(found > 0, "no pool exercised the rate limiter");
    let _ = QuoteErr::TooLarge;
}

/// The non-concavity guard (DESIGN.md §3.4): buying on a DLMM pair whose variable fee is 5% at the active bin and
/// falls to the base fee 8 bins ahead (idx_ref ahead of the walk). The round trip loses at the active bin (π'(0) < 1)
/// but gains further on. A walk that stopped at the first point where π' ≤ 1 would record only 0; the guard keeps
/// walking while a later marginal can still exceed 1 and finds the profitable optimum.
#[test]
fn guard_finds_the_optimum_past_a_falling_fee() {
    use arbx_sizing::opt::{locate, LegModel};
    let mut rng = Rng(210);
    let mut found = 0;
    for case in 0..20 {
        let x: Pk = rng.key();
        let (bin_step, active) = (25u16, rng.range(0, 100) as i32 - 50);
        let depth = rng.log(1_000_000_000, 100_000_000_000);
        let pair = dlmm_pair(&mut rng, x, bin_step, active, depth, |s| {
            s.base_factor = 4_000; s.vfc = 1_250_000; s.max_va = 1_000_000; s.v_ref = 0; s.va = 0; s.idx_ref = s.active + 8;
        });
        let p_a = dlmm_price(bin_step, active) as f64 / 18446744073709551616.0;
        let ra = 1u64 << 46;
        let rx = (ra as f64 / (p_a * (1.03 + case as f64 * 0.0005))) as u64;
        let legs = vec![dlmm_leg(&pair, true), cp_leg(&mut rng, false, false, ra, rx, x, 25)];
        let v = views(&legs);
        let (l0, l1) = (parse(&legs[0], &v.refs[0]), parse(&legs[1], &v.refs[1]));
        // the first bin loses, a later one gains
        assert!(exact(&l0, &l1, 1_000).map_or(true, |p| p < 0), "case {case}: the active bin should lose");
        let (m0, m1) = (l0.model().unwrap(), l1.model().unwrap());
        assert!(matches!(m0, LegModel::Bins(_)));
        let cap = 1u64 << 40;
        let loc = locate(&m0, &m1, arbx_sizing::Fx::from_u64(cap));
        let best = loc.sorted()[0].unwrap();
        let (bx, bv) = oracle(&l0, &l1, 1, cap).unwrap();
        if bv <= 0 { continue; }
        found += 1;
        assert!(loc.count() >= 2 && best.x.floor_u64() > 0, "case {case}: the guard did not walk on: {loc:?}");
        let r = run(&legs, &[(0, 1)], cap, 1, 1_000, 0, None, 1).plan;
        assert_eq!(r.outcome, Outcome::Sized);
        let tol = 2.0 * eps(&l0, &l1, bx) + 2.0;
        assert!((bv - r.modeled_profit) as f64 <= tol, "case {case}: best {bv} at {bx}, planned {} at {}", r.modeled_profit, r.amount);
    }
    eprintln!("falling-fee walks: {found} profitable cases, each found past the first local optimum");
    assert!(found > 5);
}

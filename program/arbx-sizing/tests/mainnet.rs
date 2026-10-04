//! The planner on REAL mainnet accounts (tests/data/mainnet-accounts.json, slot ~453.2M): every pool parses with
//! the offsets of DESIGN.md §2 (owners, discriminators, keys, versions), and HOTBOT routes — GLL3 (PumpSwap) and the
//! DLMM pairs 6D4E / 7hvn / C9xc — plan as SELF_SIZE and as a BASKET, at the real state and with a gap created by
//! moving one pool's reserve.
mod common;
use arbx_sizing::layout::WSOL;
use arbx_sizing::{axz1_record, plan, Abort, AnyLeg, Kind, Outcome, PlanIn, SzFlags};
use common::*;

fn dlmm_state_for(m: &Mainnet, name: &str, swap_for_y: bool) -> Vec<Acct> {
    let st = m.state(name);
    let active = i32::from_le_bytes(st[0].data[76..80].try_into().unwrap());
    let c = (active as i64).div_euclid(70);
    let mut a: Vec<(i64, String)> = m.pool(name)["arrays"].as_object().unwrap().iter().map(|(k, v)| (k.parse().unwrap(), v.as_str().unwrap().to_string())).collect();
    a.retain(|(i, _)| if swap_for_y { *i <= c } else { *i >= c });
    a.sort_by_key(|(i, _)| if swap_for_y { -i } else { *i });
    let mut s = st[..3].to_vec();
    s.extend(a.iter().take(5).map(|(_, k)| m.acct(k)));
    s
}

/// HOTBOT (8nnae…, Token-2022): legs 0 = GLL3 PumpBuy, 1 = 6D4E DLMM X→Y, 2 = C9xc DLMM X→Y, 3 = C9xc DLMM Y→X
/// (DESIGN.md §4.4), and 4 = 7hvn DLMM X→Y (a different X: BZFYNPeQ…, 6ejg's base mint; parsed alone)
fn hotbot_legs(m: &Mainnet) -> Vec<OwnedLeg> {
    let gll3 = "GLL3CzybpSCLZdoACf8QUM5YrKVwyA65kQ2RcTsJxxzV";
    let st = m.state(gll3);
    let hotbot = st[2].key;
    let mut buy = OwnedLeg::new(Kind::PumpBuy, false, st, WSOL);
    buy.desc.pump_bump = m.pool(gll3)["bump"].as_u64().unwrap() as u8;
    let sell_6d4e = OwnedLeg::new(Kind::Dlmm, true, dlmm_state_for(m, "6D4EWF22HfQamimKhX47tqiu9DVCkcxDMrmhnSvewKAo", true), hotbot);
    let sell_c9xc = OwnedLeg::new(Kind::Dlmm, true, dlmm_state_for(m, "C9xcUNdJrY45uBeJiuAEiNUZzxs1M22mDFCus3dm1QWq", true), hotbot);
    let buy_c9xc = OwnedLeg::new(Kind::Dlmm, false, dlmm_state_for(m, "C9xcUNdJrY45uBeJiuAEiNUZzxs1M22mDFCus3dm1QWq", false), WSOL);
    let s7 = dlmm_state_for(m, "7hvn8egrNGkpQFGyziHxvGkJFWtmoCyXmYYXp4V7tszd", true);
    let x7 = s7[1].key;
    let sell_7hvn = OwnedLeg::new(Kind::Dlmm, true, s7, x7);
    vec![buy, sell_6d4e, sell_c9xc, buy_c9xc, sell_7hvn]
}

#[test]
fn every_real_pool_parses() {
    let m = Mainnet::load();
    let clock = m.clock();
    let mut lines = vec![];
    let legs = hotbot_legs(&m);
    for (i, l) in legs.iter().enumerate() {
        let refs: Vec<_> = l.state.iter().map(|a| a.view()).collect();
        let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
        let p = AnyLeg::parse(&li, &clock, pda).unwrap_or_else(|e| panic!("leg {i}: {e:?}"));
        let leg = p.leg.unwrap_or_else(|a| panic!("leg {i}: {a:?}"));
        lines.push(format!("leg {i} {:?}: cap_in {:?}, quote(1e8) {:?}", l.desc.kind, leg.cap_in(), leg.quote(100_000_000)));
    }
    // the pump pool with an exotic quote (6ejg: creator_fee_bps 200, quote A7bdiY…) parses with its exotic fees
    let n = "6ejg4aYJM3Mk1t2zBKjbJ43df3s7rBMpC9mgo526K51G";
    let st = m.state(n);
    let mut l = OwnedLeg::new(Kind::PumpSell, true, st.clone(), st[2].key);
    l.desc.pump_bump = m.pool(n)["bump"].as_u64().unwrap() as u8;
    let refs: Vec<_> = l.state.iter().map(|a| a.view()).collect();
    let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
    let AnyLeg::Pump(p) = AnyLeg::parse(&li, &clock, pda).unwrap().leg.unwrap() else { unreachable!() };
    assert_eq!(p.fees.creator, 200, "the pool's configurable creator fee");
    assert_eq!((p.fees.lp, p.fees.protocol), (20, 5), "exotic flat fees");
    lines.push(format!("6ejg sell: fees {:?}, qv {}", p.fees, p.qv));
    // the canonical test is the real PDA: with a wrong bump the pool reads as non-canonical (flat fees)
    l.desc.pump_bump = l.desc.pump_bump.wrapping_sub(1);
    let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
    if let Ok(AnyLeg::Pump(p2)) = AnyLeg::parse(&li, &clock, pda).unwrap().leg { assert_eq!((p2.fees.lp, p2.fees.protocol), (25, 5)); }
    // DAMM v2 and the other venues, both directions
    for (name, kind) in [("C8jdide5evNRRVBiisJSnFeHH2k7FKbARP64iyfSrkdf", Kind::DammV2), ("2E8c2vnAKQ3WaSHjezHwQ6GozuXRx96JX7GoNoBeqBug", Kind::DammV2),
                         ("3Bu5wTUftguy5BxhTgFrukz6wvG6d4xYRKuU43jWA3cg", Kind::DammV2), ("FVq2chsiAcPqwL9L3zafF8juQHb7mui6LWMuE8g5L4K4", Kind::RayAmmV4)] {
        let st = m.state(name);
        for dir0 in [true, false] {
            let input = match kind {
                Kind::DammV2 => if dir0 { st[1].key } else { st[2].key },
                _ => *arbx_sizing::math::key_at(&st[0].data, if dir0 { 400 } else { 432 }).unwrap(),
            };
            let l = OwnedLeg::new(kind, dir0, st.clone(), input);
            let refs: Vec<_> = l.state.iter().map(|a| a.view()).collect();
            let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
            let leg = AnyLeg::parse(&li, &clock, pda).unwrap().leg.unwrap();
            lines.push(format!("{}… {kind:?} dir0={dir0}: cap_in {:?}, quote(1e9) {:?}", &name[..6], leg.cap_in(), leg.quote(1_000_000_000).map(|q| q.out)));
        }
    }
    // Hmx1 (CPMM): its Token-2022 mint charges a 3% transfer fee
    let n = "Hmx1eHEdm67YYZYEathc6aki2q3zjhhTmw7wZPq66BnJ";
    let s0: Vec<Acct> = m.pool(n)["state0"].as_array().unwrap().iter().map(|k| m.acct(k.as_str().unwrap())).collect();
    let l = OwnedLeg::new(Kind::RayCpmm, true, s0.clone(), s0[4].key);
    let refs: Vec<_> = l.state.iter().map(|a| a.view()).collect();
    let li = arbx_sizing::LegIn { desc: l.desc, program: l.desc.kind.program(), state: &refs, input_mint: &l.input_mint };
    assert_eq!(AnyLeg::parse(&li, &clock, pda).unwrap().leg.err(), Some(Abort::TransferFee));
    for l in &lines { eprintln!("{l}"); }
}

fn run<'a>(m: &Mainnet, legs: &'a [OwnedLeg], pairs: &[(u8, u8)], cap: u64, e: u64) -> arbx_sizing::Plan {
    let v = views(legs);
    let ins = leg_ins(legs, &v);
    let p = PlanIn { clock: m.clock(), cap, min_size: 1_000, engine_amount: e, min_profit: 1, tip: None, flags: SzFlags(0), max_iters: 0, lamport_offset: 0, legs: &ins, pairs, pda };
    plan(&p).unwrap()
}

fn exact(legs: &[OwnedLeg], clock: arbx_sizing::Clock, pair: (u8, u8), x: u64) -> Option<i128> {
    let v = views(legs);
    let ins = leg_ins(legs, &v);
    let l0 = AnyLeg::parse(&ins[pair.0 as usize], &clock, pda).ok()?.leg.ok()?;
    let l1 = AnyLeg::parse(&ins[pair.1 as usize], &clock, pda).ok()?.leg.ok()?;
    let q0 = l0.quote(x).ok()?;
    Some(l1.quote(q0.out).ok()?.out as i128 - x as i128)
}

/// best exact profit on a log grid then a local refinement (concave in practice)
fn best(legs: &[OwnedLeg], clock: arbx_sizing::Clock, pair: (u8, u8), cap: u64) -> (u64, i128) {
    let mut b = (0u64, i128::MIN);
    for i in 0..=400 { let x = (1_000f64 * (cap as f64 / 1_000.0).powf(i as f64 / 400.0)) as u64; if let Some(v) = exact(legs, clock, pair, x) { if v > b.1 { b = (x, v); } } }
    let mut step = (b.0 / 50).max(1);
    while step > 0 {
        for x in [b.0.saturating_sub(step), b.0 + step] { if let Some(v) = exact(legs, clock, pair, x) { if v > b.1 { b = (x, v); } } }
        step /= 2;
    }
    b
}

#[test]
fn hotbot_routes_plan() {
    let m = Mainnet::load();
    let clock = m.clock();
    let mut legs = hotbot_legs(&m);
    legs.truncate(4);
    let cap = 100_000_000_000; // 100 SOL
    let e = 100_000_000; // 0.1 SOL
    let mut report = vec![];
    // the real state: no gap, the round trip loses its fees
    let r = run(&m, &legs[..2], &[(0, 1)], cap, e);
    assert_eq!(r.outcome, Outcome::NoProfit, "{r:?}");
    report.push(format!("real state GLL3→6D4E: {:?}, best candidate {} at {} (e: {:?}), evals {} bins {}", r.outcome, r.modeled_profit, r.amount, r.modeled_profit_e, r.evals, r.bins));
    // a gap: GLL3's quote vault 12% lower → HOTBOT is cheaper on PumpSwap
    let qv = u64::from_le_bytes(legs[0].state[5].data[64..72].try_into().unwrap());
    put_u64(&mut legs[0].state[5].data, 64, qv / 100 * 88);
    // a third HOTBOT venue: a synthetic CPMM HOTBOT/wSOL pool priced 6% above 6D4E's active bin
    let mut rng = Rng(77);
    let hotbot = legs[0].state[2].key;
    let p6 = u128::from_le_bytes(legs[1].state[3].data[56 + ((-538i64 - (-8) * 70) as usize) * 144 + 16..][..16].try_into().unwrap()) as f64 / 18446744073709551616.0;
    let ra = 400_000_000_000u64;
    let rx = (ra as f64 / (p6 * 1.06)) as u64;
    let spec = CpmmSpec { r0: ra, r1: rx, trade: 2_500, creator: 0, enable_creator: false, creator_on: 0, owed0: 0, owed1: 0 };
    let cpmm_sell = OwnedLeg::new(Kind::RayCpmm, false, cpmm(&mut rng, &spec, WSOL, hotbot, false), hotbot);
    legs.push(cpmm_sell);
    for (pairs, legs_ix, what) in [
        (&[(0u8, 1u8)][..], &[0usize, 1][..], "SELF_SIZE GLL3→6D4E"),
        (&[(0, 1), (0, 2), (3, 1)][..], &[0, 1, 2, 3][..], "BASKET (GLL3→6D4E, GLL3→C9xc, C9xc→6D4E): C9xc's passed arrays are empty"),
        (&[(0, 1), (0, 2)][..], &[0, 1, 4][..], "BASKET (GLL3→6D4E, GLL3→CPMM 6% dearer)"),
    ] {
        let l: Vec<OwnedLeg> = legs_ix.iter().map(|&i| legs[i].clone()).collect();
        let r = run(&m, &l, pairs, cap, e);
        let pair = pairs[r.pair as usize];
        let (bx, bv) = best(&l, clock, pair, cap);
        let others: Vec<i128> = pairs.iter().map(|&p| best(&l, clock, p, cap).1).collect();
        assert!(matches!(r.outcome, Outcome::Sized), "{what}: {r:?}");
        assert_eq!(exact(&l, clock, pair, r.amount), Some(r.modeled_profit));
        if let Some(ev) = r.modeled_profit_e { assert!(r.modeled_profit >= ev); }
        // near the best of this pair (grid oracle: a relative tolerance), and no other pair clearly better
        assert!(bv - r.modeled_profit <= (bv / 100_000).max(1_000), "{what}: planned {} at {}, grid best {bv} at {bx}", r.modeled_profit, r.amount);
        for (k, o) in others.iter().enumerate() { assert!(o.saturating_sub(r.modeled_profit) <= (o.saturating_abs() / 100_000).max(1_000), "{what}: pair {k} reaches {o}"); }
        let rec = axz1_record(&r, pairs.len() as u8, SzFlags(0), e, cap);
        assert_eq!(&rec[..4], b"AXZ1");
        report.push(format!("{what}: pair {} amount {} (x* {}) profit {} lamports vs e = 0.1 SOL {:?}; grid best {bv} at {bx}; per-pair best {others:?}; evals {} bins {}",
            r.pair, r.amount, r.x_star, r.modeled_profit, r.modeled_profit_e, r.evals, r.bins));
    }
    for l in &report { eprintln!("{l}"); }
}

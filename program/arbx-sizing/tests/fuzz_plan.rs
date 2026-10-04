//! REVIEW.md F13: `plan` on PARSED sizing blocks. Arbitrary block bytes go through `parse_block`; every accepted
//! block gets synthetic accounts of its legs' kinds and directions (constant-product, PumpSwap, DLMM, DAMM v2 vector
//! pools), with random byte mutations of the state, and is planned. Never a panic (overflow checks are on); every
//! Sized/NoProfit plan's amount lies in [min_size, cap] and its modeled profit is the exact round trip at that
//! amount; every DescError names a leg or a pair that exists.
mod common;
use arbx_sizing::desc::{parse_block, Kind};
use arbx_sizing::layout::WSOL;
use arbx_sizing::{plan, AnyLeg, Outcome, PlanIn};
use common::*;

const A: Pk = WSOL;

/// synthetic state for a leg of `kind` spending `input` (A for a buy leg, X for a sell leg; dir: the descriptor's
/// token0/x/a/base-in bit), the other side being the other of A / X. PumpSwap and the DAMM v2 vector pools keep their
/// own mints, so a block using them in another role fails the mint chain (a DescError, also checked).
fn leg_for(rng: &mut Rng, kind: Kind, t0_in: bool, input: Pk, x: Pk, damm: &[Vec<u8>]) -> OwnedLeg {
    let other = if input == A { x } else { A };
    let ra = rng.log(1_000_000, 1 << 44);
    let rx = rng.log(1_000_000, 1 << 56);
    match kind {
        Kind::RayCpmm => {
            // token0 = A when the leg spends token0 and A is the route's input, else token0 = X
            let spec = CpmmSpec { r0: ra, r1: rx, trade: rng.range(0, 30_000), creator: rng.range(0, 30_000), enable_creator: rng.chance(1, 2),
                creator_on: rng.range(0, 2) as u8, owed0: 0, owed1: 0 };
            let (m0, m1) = if t0_in { (input, other) } else { (other, input) };
            let st = cpmm(rng, &spec, m0, m1, t0_in);
            OwnedLeg::new(kind, t0_in, st, if t0_in { m0 } else { m1 })
        }
        Kind::RayAmmV4 => {
            let (cm, pm) = if t0_in { (input, other) } else { (other, input) };
            let fee = rng.range(0, 100);
            let st = ammv4(rng, rx, ra, fee, 10_000, cm, pm);
            OwnedLeg::new(kind, t0_in, st, if t0_in { cm } else { pm })
        }
        Kind::PumpBuy | Kind::PumpSell => {
            let virt = if rng.chance(1, 3) { ra as i128 * rng.range(0, 60) as i128 } else { 0 };
            let (creator_fee_bps, canonical) = (rng.range(0, 1000), rng.chance(3, 4));
            let p = pump(rng, &PumpSpec { base: rx, quote: ra, virt, creator_fee_bps, canonical, ..Default::default() });
            OwnedLeg::pump(&p, kind == Kind::PumpSell)
        }
        Kind::Dlmm => {
            let active = rng.range(0, 400) as i32 - 200;
            let bin_step = [1u16, 10, 25, 100][rng.range(0, 3) as usize];
            let mut spec = DlmmSpec { bin_step, active, idx_ref: active + rng.range(0, 20) as i32 - 10, last_ts: CLOCK.unix_timestamp - rng.range(0, 3000) as i64,
                vfc: rng.range(0, 50_000) as u32, max_va: rng.range(10_000, 400_000) as u32, function_type: rng.range(0, 2) as u8,
                collect_fee_mode: rng.range(0, 1) as u8, bins: vec![], ..Default::default() };
            for id in active - 120..=active + 120 {
                if rng.chance(1, 4) { continue; }
                let amt = rng.log(1, 1 << 40);
                let lo = if rng.chance(1, 6) { (rng.log(1, 1 << 34), rng.log(1, 1 << 30), rng.range(0, 1) as u8) } else { (0, 0, 0) };
                spec.bins.push((id, if id >= active { amt } else { 0 }, if id <= active { amt } else { 0 }, lo));
            }
            let (mx, my) = if t0_in { (input, other) } else { (other, input) };
            let (p, a, b, arrays) = dlmm(rng, &spec, mx, my);
            let mut l = OwnedLeg::new(kind, t0_in, dlmm_state(&p, &a, &b, &arrays, t0_in), if t0_in { mx } else { my });
            l.desc.max_bins = rng.range(1, 255) as u8;
            l
        }
        Kind::DammV2 => {
            let raw = damm[rng.range(0, damm.len() as u64 - 1) as usize].clone();
            let (ma, mb) = (*arbx_sizing::math::key_at(&raw, 168).unwrap(), *arbx_sizing::math::key_at(&raw, 200).unwrap());
            OwnedLeg::new(kind, t0_in, vec![Acct { key: rng.key(), owner: arbx_sizing::layout::DAMM_V2, data: raw }, mint(ma, 0, false, None), mint(mb, 0, false, None)],
                if t0_in { ma } else { mb })
        }
    }
}

#[test]
fn plan_on_parsed_blocks_never_panics() {
    let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/../../testdata/dammv2-vectors.json")).unwrap()).unwrap();
    let damm: Vec<Vec<u8>> = v["pools"].as_object().unwrap().values().map(|p| b64(p["b64"].as_str().unwrap())).collect();
    let mut rng = Rng(0xF13);
    let (mut parsed, mut planned, mut sized, mut desc_err) = (0, 0, 0, 0);
    for it in 0..40_000 {
        // a block: random flags/amounts and a random leg list (kinds 1..=6, dir, arrays) in the encoder's layout
        let basket = rng.chance(1, 2);
        let n_legs = if basket { rng.range(2, 4) as usize } else { 2 };
        let mut data = vec![rng.next() as u8 & 0x3F];
        let min_size = rng.range(1, 1_000) as u32;
        let e = rng.log(min_size as u64, 1 << 40);
        data.extend(min_size.to_le_bytes());
        data.extend(e.to_le_bytes());
        if data[0] & 0x20 != 0 { data.extend((rng.next() as i32 / 1024).to_le_bytes()); }
        if data[0] & 0x08 != 0 { data.push(rng.range(0, 24) as u8); }
        if basket {
            let n_pairs = rng.range(1, 3) as u8;
            data.push(n_pairs);
            for _ in 0..n_pairs { data.push(rng.range(0, n_legs as u64 - 1) as u8); data.push(rng.range(0, n_legs as u64 - 1) as u8); }
        }
        for _ in 0..n_legs {
            let kind = rng.range(1, 6) as u8;
            let dir = rng.range(0, 1) as u8;
            let nba = if kind == 5 { rng.range(1, 5) as u8 } else { 0 };
            data.push(kind | dir << 4 | nba << 5);
            if kind <= 2 { data.push(rng.next() as u8); }
            if kind == 5 { data.push(rng.range(1, 255) as u8); }
            if data[0] & 0x10 != 0 {
                let n = match kind { 1 | 2 => 7, 3 => 6, 4 => 3, 5 => 4, _ => 3 };
                data.push(n);
                for _ in 0..n { data.push(rng.range(0, 30) as u8); }
            }
        }
        // random byte noise on a third of the blocks
        if it % 3 == 0 && !data.is_empty() { let i = rng.range(0, data.len() as u64 - 1) as usize; data[i] = rng.next() as u8; }
        let amount_in = e.saturating_mul(rng.range(1, 4));
        let Ok((block, _)) = parse_block(&data, 0, n_legs, basket, amount_in) else { continue };
        parsed += 1;
        let x = rng.key();
        let mut legs: Vec<OwnedLeg> = block.legs().iter().enumerate().map(|(i, d)| {
            let buy = block.pairs().iter().any(|p| p.0 as usize == i);
            let mut l = leg_for(&mut rng, d.kind, d.base_or_token0_in, if buy { A } else { x }, x, &damm);
            l.desc.n_bin_arrays = if d.kind == Kind::Dlmm { (l.state.len() - 3) as u8 } else { 0 };
            if d.kind == Kind::Dlmm { l.desc.max_bins = d.max_bins; }
            if d.kind.has_bump() && rng.chance(1, 8) { l.desc.pump_bump = d.pump_bump; }
            l
        }).collect();
        // state noise: flip bytes in a random state account of a random leg
        if it % 2 == 0 {
            let li = rng.range(0, legs.len() as u64 - 1) as usize;
            let ai = rng.range(0, legs[li].state.len() as u64 - 1) as usize;
            let d = &mut legs[li].state[ai].data;
            for _ in 0..rng.range(1, 4) { if !d.is_empty() { let i = rng.range(8, d.len() as u64 - 1) as usize; d[i] = rng.next() as u8; } }
        }
        let vv = views(&legs);
        let ins = leg_ins(&legs, &vv);
        let cap = rng.log(1, 1 << 44).max(block.engine_amount.min(amount_in) / 2);
        let p = PlanIn { clock: CLOCK, cap, min_size: block.min_size as u64, engine_amount: block.engine_amount, min_profit: rng.log(1, 1 << 30),
            tip: None, flags: block.flags, max_iters: block.max_iters, lamport_offset: block.lamport_offset as i64, legs: &ins, pairs: block.pairs(), pda };
        match plan(&p) {
            Err(e) => {
                desc_err += 1;
                assert!(e.leg == 0xFF || (e.leg as usize) < n_legs.max(block.n_pairs as usize), "it {it}: {e:?}");
            }
            Ok(r) => {
                planned += 1;
                if matches!(r.outcome, Outcome::Sized | Outcome::NoProfit) && r.reason != arbx_sizing::Reason::INFEASIBLE {
                    assert!(r.amount >= p.min_size && r.amount <= cap.max(p.engine_amount), "it {it}: {r:?}");
                    let (b, s) = block.pairs()[r.pair as usize];
                    let lb = AnyLeg::parse(&ins[b as usize], &CLOCK, pda).unwrap().leg.unwrap();
                    let ls = AnyLeg::parse(&ins[s as usize], &CLOCK, pda).unwrap().leg.unwrap();
                    let q0 = lb.quote(r.amount).unwrap();
                    let q1 = ls.quote(q0.out).unwrap();
                    assert_eq!(r.modeled_profit, q1.out as i128 - q0.spent as i128, "it {it}: {r:?}");
                    if r.outcome == Outcome::Sized { sized += 1; }
                }
            }
        }
    }
    eprintln!("plan fuzz: {parsed} blocks parsed, {planned} planned ({sized} sized), {desc_err} DescErrors; no panic");
    assert!(parsed > 8_000 && planned > 2_000 && desc_err > 1_000, "parsed {parsed} planned {planned} desc {desc_err}");
}

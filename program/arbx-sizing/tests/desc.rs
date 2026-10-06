//! The sizing block: encode → parse round trip, every rule of DESIGN.md §4.2/§4.3, and arbitrary bytes (never a
//! panic; every accepted block re-encodes to the same bytes).
use arbx_sizing::desc::{block_len, encode_block, parse_block, Kind, LegDesc, SizingBlock, SzFlags, MAX_PAIRS, MAX_SIZED_LEGS};
use arbx_sizing::layout;
use arbx_sizing::{DescCode, DescError};
use proptest::prelude::*;

const KINDS: [Kind; 6] = [Kind::PumpBuy, Kind::PumpSell, Kind::RayCpmm, Kind::RayAmmV4, Kind::Dlmm, Kind::DammV2];

fn leg_strategy(explicit: bool) -> impl Strategy<Value = LegDesc> {
    (0usize..6, any::<bool>(), 1u8..=5, any::<u8>(), any::<[u8; 8]>(), 1u8..=255).prop_map(move |(k, dir, nba, bump, pos, max_bins)| {
        let kind = KINDS[k];
        let token0_in = match kind { Kind::PumpBuy => false, Kind::PumpSell => true, _ => dir };
        let mut p = [0u8; 8];
        for (i, v) in p.iter_mut().enumerate().take(kind.n_positions()) { *v = pos[i] % 200; }
        LegDesc {
            kind, base_or_token0_in: token0_in,
            n_bin_arrays: if kind == Kind::Dlmm { nba } else { 0 },
            pump_bump: if kind.has_bump() { bump } else { 0 },
            max_bins: if kind.has_budget() { max_bins } else { 0 },
            positions: if explicit { Some(p) } else { None },
        }
    })
}

/// a valid block: random flags, amounts, legs; BASKET pairs covering every leg with consistent roles
fn block_strategy() -> impl Strategy<Value = SizingBlock> {
    (any::<u8>(), 1u32.., any::<u64>(), 0u8..=24, any::<bool>(), 2usize..=6, any::<i32>()).prop_flat_map(|(fl, min_size, e, iters, basket, n, lam)| {
        let flags = SzFlags(fl & SzFlags::KNOWN);
        let n_legs = if basket { n } else { 2 };
        let legs = proptest::collection::vec(leg_strategy(flags.explicit_pos()), n_legs);
        let split = 1..n_legs; // legs [0, split) buy, [split, n) sell
        (Just((flags, min_size, e, iters, basket, n_legs, lam)), legs, split, any::<[u8; 6]>())
    }).prop_map(|((flags, min_size, e, iters, basket, n_legs, lam), lv, split, pick)| {
        let e = e.max(min_size as u64);
        let mut legs = [LegDesc::placeholder(); MAX_SIZED_LEGS];
        for (s, l) in legs.iter_mut().zip(&lv) { *s = *l; }
        let mut pairs = [(0u8, 0u8); MAX_PAIRS];
        let n_pairs = if basket {
            // pairs that use every leg: buys [0, split), sells [split, n)
            let buys: Vec<u8> = (0..split as u8).collect();
            let sells: Vec<u8> = (split as u8..n_legs as u8).collect();
            let need = buys.len().max(sells.len());
            if need > MAX_PAIRS { return None; }
            let mut k = 0;
            for i in 0..need { pairs[k] = (buys[i % buys.len()], sells[(i + pick[i] as usize) % sells.len()]); k += 1; }
            let mut v: Vec<(u8, u8)> = pairs[..k].to_vec();
            v.sort(); v.dedup();
            // dedup may drop a leg's only pair: rebuild from the deduped set and check coverage
            let used: std::collections::BTreeSet<u8> = v.iter().flat_map(|p| [p.0, p.1]).collect();
            if used.len() != n_legs { return None; }
            for (i, p) in v.iter().enumerate() { pairs[i] = *p; }
            v.len() as u8
        } else { pairs[0] = (0, 1); 1 };
        Some(SizingBlock { flags, min_size, engine_amount: e, lamport_offset: if flags.lamports() { lam } else { 0 },
            max_iters: if flags.search() { iters } else { 0 }, pairs, n_pairs, legs, n_legs: n_legs as u8, basket })
    }).prop_filter_map("basket pairs", |b| b)
}

proptest! {
    #![proptest_config(ProptestConfig::with_cases(3000))]

    #[test]
    fn encode_parse_round_trip(b in block_strategy(), prefix in proptest::collection::vec(any::<u8>(), 0..8)) {
        let mut data = prefix.clone();
        encode_block(&b, &mut data);
        let tail = data.len();
        data.extend_from_slice(&[0xAA; 5]); // leg data follows the block
        let (got, len) = parse_block(&data, prefix.len(), b.n_legs as usize, b.basket, u64::MAX).unwrap();
        prop_assert_eq!(len, tail - prefix.len());
        prop_assert_eq!(len, block_len(&b));
        prop_assert_eq!(got, b);
    }

    #[test]
    fn arbitrary_bytes_never_panic_and_reencode(data in proptest::collection::vec(any::<u8>(), 0..64), n in 0usize..9, basket in any::<bool>(), amount_in in any::<u64>()) {
        if let Ok((b, len)) = parse_block(&data, 0, n, basket, amount_in) {
            let mut out = Vec::new();
            encode_block(&b, &mut out);
            prop_assert_eq!(&out[..], &data[..len]);
            prop_assert!(b.min_size >= 1 && b.min_size as u64 <= b.engine_amount && b.engine_amount <= amount_in);
            for l in b.legs() { prop_assert!(layout::positions(l).is_ok()); }
        }
    }
}

fn simple(flags: u8) -> Vec<u8> {
    let mut v = vec![flags];
    v.extend(10u32.to_le_bytes());
    v.extend(1000u64.to_le_bytes());
    v
}

fn err(r: Result<(SizingBlock, usize), DescError>) -> DescCode { r.unwrap_err().code }

#[test]
fn rules() {
    // SELF_SIZE 2 legs: PumpBuy (dir 1, bump) + DLMM X→Y with 3 arrays and a walk budget of 9 bins
    let mut d = simple(0);
    d.extend([Kind::PumpBuy as u8 | 0x10, 254, Kind::Dlmm as u8 | (3 << 5), 9]);
    let (b, len) = parse_block(&d, 0, 2, false, 1000).unwrap();
    assert_eq!(len, 15 + 1 + 1, "15 bytes + 1 per PumpSwap leg + 1 per DLMM leg (DESIGN.md §4.2)");
    assert_eq!(b.legs()[0].pump_bump, 254);
    assert_eq!(b.legs()[1].max_bins, 9);
    // DLMM max_bins 0 is refused (REVIEW.md F3: the budget is the engine's, per leg)
    let mut z = d.clone(); *z.last_mut().unwrap() = 0;
    assert_eq!(parse_block(&z, 0, 2, false, 1000).unwrap_err(), DescError::new(DescCode::BinBudget, 1, 0xFF));
    assert!(!b.legs()[0].base_or_token0_in && b.legs()[1].base_or_token0_in);
    assert_eq!(b.legs()[1].n_bin_arrays, 3);
    assert_eq!(b.pairs(), &[(0, 1)]);
    assert_eq!(layout::positions(&b.legs()[1]).unwrap().as_slice(), &[0, 6, 7, 16, 17, 18]);
    assert_eq!(layout::positions(&b.legs()[0]).unwrap().as_slice(), &layout::POS_PUMP_BUY);
    // amounts
    assert_eq!(err(parse_block(&d, 0, 2, false, 999)), DescCode::EngineAmount);
    let mut z = d.clone(); z[1..5].copy_from_slice(&0u32.to_le_bytes());
    assert_eq!(err(parse_block(&z, 0, 2, false, 1000)), DescCode::MinSize);
    let mut z = d.clone(); z[1..5].copy_from_slice(&1001u32.to_le_bytes());
    assert_eq!(err(parse_block(&z, 0, 2, false, 5000)), DescCode::MinSize);
    // flags
    let mut z = d.clone(); z[0] = 0x40;
    assert_eq!(err(parse_block(&z, 0, 2, false, 1000)), DescCode::Flags);
    // LAMPORTS: an i32 lamport_offset after engine_amount (REVIEW.md F10)
    let mut z = simple(SzFlags::LAMPORTS); z.extend((-2_039_280i32).to_le_bytes()); z.extend(&d[13..]);
    let (bl, len) = parse_block(&z, 0, 2, false, 1000).unwrap();
    assert_eq!((bl.lamport_offset, len), (-2_039_280, 17 + 4));
    assert_eq!(err(parse_block(&z[..16], 0, 2, false, 1000)), DescCode::Truncated);
    // leg counts
    assert_eq!(err(parse_block(&d, 0, 3, false, 1000)), DescCode::NLegs);
    assert_eq!(err(parse_block(&d, 0, 7, true, 1000)), DescCode::NLegs);
    // truncation at every length
    for cut in 0..d.len() { assert_eq!(err(parse_block(&d[..cut], 0, 2, false, 1000)), DescCode::Truncated, "cut {cut}"); }
    // kinds and directions
    let leg = |kd: u8, extra: &[u8]| { let mut v = simple(0); v.push(Kind::RayCpmm as u8); v.push(kd); v.extend_from_slice(extra); v };
    assert_eq!(err(parse_block(&leg(0, &[]), 0, 2, false, 1000)), DescCode::Kind);
    // kinds 7 (Raydium CLMM) and 8 (Orca Whirlpool) exist since PLAN-ADDENDUM WP-21: 9..=15 are invalid
    assert_eq!(err(parse_block(&leg(9, &[]), 0, 2, false, 1000)), DescCode::Kind);
    assert_eq!(err(parse_block(&leg(15, &[]), 0, 2, false, 1000)), DescCode::Kind);
    assert_eq!(err(parse_block(&leg(Kind::PumpBuy as u8, &[1]), 0, 2, false, 1000)), DescCode::Dir);
    assert_eq!(err(parse_block(&leg(Kind::PumpSell as u8 | 0x10, &[1]), 0, 2, false, 1000)), DescCode::Dir);
    assert_eq!(err(parse_block(&leg(Kind::Dlmm as u8, &[5]), 0, 2, false, 1000)), DescCode::BinArrays);
    assert_eq!(err(parse_block(&leg(Kind::Dlmm as u8 | (6 << 5), &[5]), 0, 2, false, 1000)), DescCode::BinArrays);
    assert_eq!(err(parse_block(&leg(Kind::DammV2 as u8 | (1 << 5), &[]), 0, 2, false, 1000)), DescCode::BinArrays);
    // SEARCH: max_iters ≤ 24
    let mut s = simple(SzFlags::SEARCH); s.push(25); s.extend([Kind::RayCpmm as u8, Kind::RayAmmV4 as u8 | 0x10]);
    assert_eq!(err(parse_block(&s, 0, 2, false, 1000)), DescCode::MaxIters);
    let mut s = simple(SzFlags::SEARCH); s.push(24); s.extend([Kind::RayCpmm as u8, Kind::RayAmmV4 as u8 | 0x10]);
    assert_eq!(parse_block(&s, 0, 2, false, 1000).unwrap().0.max_iters, 24);
    // EXPLICIT_POS: n_pos must be the kind's count; DLMM's arrays must stay below 256
    let mut s = simple(SzFlags::EXPLICIT_POS); s.extend([Kind::DammV2 as u8, 3, 1, 6, 7, Kind::RayAmmV4 as u8 | 0x10, 2, 1, 3]);
    assert_eq!(err(parse_block(&s, 0, 2, false, 1000)), DescCode::PosCount);
    let mut s = simple(SzFlags::EXPLICIT_POS); s.extend([Kind::DammV2 as u8, 3, 1, 6, 7, Kind::Dlmm as u8 | (5 << 5), 64, 4, 0, 6, 7, 252]);
    assert_eq!(err(parse_block(&s, 0, 2, false, 1000)), DescCode::Position);
    let mut s = simple(SzFlags::EXPLICIT_POS); s.extend([Kind::DammV2 as u8, 3, 1, 6, 7, Kind::Dlmm as u8 | (5 << 5), 64, 4, 0, 6, 7, 251]);
    let (b, _) = parse_block(&s, 0, 2, false, 1000).unwrap();
    assert_eq!(layout::positions(&b.legs()[1]).unwrap().as_slice(), &[0, 6, 7, 251, 252, 253, 254, 255]);
    assert!(layout::check_positions(&b.legs()[1], 255).is_err() && layout::check_positions(&b.legs()[1], 256).is_ok());
}

/// REVIEW.md F15: `kd()` masks n_bin_arrays to its 3 bits (no u8 shift overflow for an out-of-range count)
#[test]
fn kd_masks_the_array_count() {
    let mut l = LegDesc::new(Kind::Dlmm, true);
    for n in [0u8, 1, 5, 7, 8, 9, 200, 255] {
        l.n_bin_arrays = n;
        assert_eq!(l.kd(), Kind::Dlmm as u8 | ((n & 7) << 5), "n_bin_arrays {n}");
    }
}

#[test]
fn basket_rules() {
    let legs = [Kind::PumpBuy as u8 | 0x10, 7, Kind::Dlmm as u8 | (4 << 5), 8, Kind::Dlmm as u8 | (4 << 5), 8, Kind::Dlmm as u8 | 0x10 | (4 << 5), 8];
    let with_pairs = |pairs: &[(u8, u8)], n_pairs: u8| {
        let mut v = simple(0);
        v.push(n_pairs);
        for p in pairs { v.push(p.0); v.push(p.1); }
        v.extend(legs);
        v
    };
    // the HOTBOT example of DESIGN.md §4.4: 4 legs, pairs (0,1) (0,2) (3,1)
    let d = with_pairs(&[(0, 1), (0, 2), (3, 1)], 3);
    let (b, len) = parse_block(&d, 0, 4, true, 1000).unwrap();
    assert_eq!(b.pairs(), &[(0, 1), (0, 2), (3, 1)]);
    assert_eq!(len, 13 + 7 + 4 + 1 + 3);
    assert_eq!(err(parse_block(&with_pairs(&[], 0), 0, 4, true, 1000)), DescCode::PairCount);
    assert_eq!(err(parse_block(&with_pairs(&[(0, 1), (0, 2), (3, 1), (3, 2)], 4), 0, 4, true, 1000)), DescCode::PairCount);
    assert_eq!(err(parse_block(&with_pairs(&[(0, 4), (3, 1), (0, 2)], 3), 0, 4, true, 1000)), DescCode::PairIndex);
    assert_eq!(err(parse_block(&with_pairs(&[(0, 0), (3, 1), (0, 2)], 3), 0, 4, true, 1000)), DescCode::PairSameLeg);
    assert_eq!(err(parse_block(&with_pairs(&[(0, 1), (0, 1), (3, 2)], 3), 0, 4, true, 1000)), DescCode::PairDuplicate);
    assert_eq!(err(parse_block(&with_pairs(&[(0, 1), (1, 2), (3, 1)], 3), 0, 4, true, 1000)), DescCode::LegRole);
    assert_eq!(err(parse_block(&with_pairs(&[(0, 1), (3, 1)], 2), 0, 4, true, 1000)), DescCode::LegUnused);
}

/// Mutation fuzzing: valid blocks with random bytes overwritten, truncated or extended. Never a panic; every accepted
/// block re-encodes to exactly the bytes it was parsed from. Counts acceptances so the property is not vacuous.
#[test]
fn mutated_blocks() {
    use proptest::strategy::ValueTree;
    use proptest::test_runner::TestRunner;
    let mut runner = TestRunner::deterministic();
    let mut s = 0x1234_5678_9abc_def0u64;
    let mut next = move || { s ^= s >> 12; s ^= s << 25; s ^= s >> 27; s.wrapping_mul(0x2545F4914F6CDD1D) };
    let (mut tried, mut accepted, mut changed_ok) = (0, 0, 0);
    for _ in 0..20_000 {
        let b = block_strategy().new_tree(&mut runner).unwrap().current();
        let mut data = Vec::new();
        encode_block(&b, &mut data);
        let orig = data.clone();
        for _ in 0..1 + next() % 3 {
            match next() % 4 {
                0 | 1 if !data.is_empty() => { let i = (next() as usize) % data.len(); data[i] = next() as u8; }
                2 if !data.is_empty() => { let n = (next() as usize) % data.len(); data.truncate(n); }
                _ => data.push(next() as u8),
            }
        }
        let n_legs = if next() % 4 == 0 { (next() % 8) as usize } else { b.n_legs as usize };
        tried += 1;
        if let Ok((p, len)) = parse_block(&data, 0, n_legs, b.basket, u64::MAX) {
            accepted += 1;
            let mut out = Vec::new();
            encode_block(&p, &mut out);
            assert_eq!(&out[..], &data[..len]);
            if data[..len] != orig[..orig.len().min(len)] { changed_ok += 1; }
        }
    }
    eprintln!("mutated blocks: {tried} tried, {accepted} accepted ({changed_ok} differing from the original), all re-encode identically");
    assert!(accepted > 2_000 && changed_ok > 500);
}

//! Host unit tests and property tests for the route logic (no Solana runtime). The LiteSVM tests that run the built
//! .so are in tests/litesvm.rs.

use super::logic::*;
use super::v2_reference as v2ref;
use proptest::collection::vec;
use proptest::prelude::*;

fn hex(d: &[u8]) -> String { d.iter().map(|b| format!("{:02x}", b)).collect() }
fn unhex(s: &str) -> Vec<u8> { (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect() }

/// A minimal base58 decoder (Bitcoin alphabet), so the key tables can be checked without a dependency.
fn b58(s: &str) -> Vec<u8> {
    const ALPHA: &[u8] = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    let mut out: Vec<u8> = Vec::new(); // big-endian magnitude
    for c in s.bytes() {
        let mut carry = ALPHA.iter().position(|&a| a == c).expect("base58 char") as u32;
        for b in out.iter_mut().rev() {
            carry += (*b as u32) * 58;
            *b = (carry & 0xff) as u8;
            carry >>= 8;
        }
        while carry > 0 { out.insert(0, (carry & 0xff) as u8); carry >>= 8; }
    }
    let zeros = s.bytes().take_while(|&c| c == b'1').count();
    let mut v = vec![0u8; zeros];
    v.extend(out);
    v
}

/// Re-encode a parsed route from its fields and the original leg data. Parsing is canonical iff this reproduces the
/// input bytes exactly.
fn reencode(r: &Route, data: &[u8]) -> Vec<u8> {
    let slice = |l: &LegMeta| &data[l.data_start..l.data_start + l.data_len];
    match r.layout {
        V2 => {
            let legs: Vec<(u8, u8, &[u8])> = r.legs().iter().map(|l| {
                let b = l.n_accounts as u8 | if l.native_in { NATIVE_IN } else { 0 } | if l.native_out { NATIVE_OUT } else { 0 };
                (b, l.amount_offset as u8, slice(l))
            }).collect();
            match r.max_payer_lamport_drop {
                Some(g) => encode_guarded(r.amount_in, r.min_profit, &legs, g),
                None => encode(r.amount_in, r.min_profit, &legs),
            }
        }
        V3 => {
            let legs: Vec<LegSpec> = r.legs().iter().map(|l| LegSpec { n_accounts: l.n_accounts as u8, flags: l.flags(), amount_offset: l.amount_offset as u8, data: slice(l) }).collect();
            encode_v3(r.flags, r.amount_in, r.min_profit, r.max_payer_lamport_drop, r.tip, &legs)
        }
        _ => unreachable!(),
    }
}

/// Structural invariants of every successfully parsed route.
fn assert_route_invariants(r: &Route, data: &[u8]) {
    assert!(r.layout == V2 || r.layout == V3);
    assert!((1..=MAX_LEGS).contains(&r.n_legs));
    assert!(r.min_profit > 0);
    assert!(r.leg_slots[r.n_legs..].iter().all(|l| *l == LegMeta::default()));
    for l in r.legs() {
        assert!(l.amount_offset + 8 <= l.data_len);
        assert!(l.data_start + l.data_len <= data.len());
        if r.layout == V3 {
            assert!(l.n_accounts >= 1);
            assert!(!(l.native_in && l.native_out), "v3: one leg is never both NATIVE_IN and NATIVE_OUT (REVIEW #6)");
            assert!(!(l.auth_ro && (l.native_in || l.native_out)), "v3: LEG_AUTH_RO never on a native leg");
        } else {
            assert!(l.n_accounts < 64);
            assert!(!l.auth_ro);
        }
    }
    assert_eq!(r.required_accounts(), 2 + r.legs().iter().map(|l| 2 + l.n_accounts).sum::<usize>() + if r.tip.is_some() { 2 } else { 0 });
    if let Some(t) = r.tip {
        assert!(t.bps <= MAX_TIP_BPS && t.floor <= t.cap && (t.account_ix as usize) < 8);
    }
    if r.layout == V3 && r.has_native() { assert!(r.count_lamports()); }
    if r.layout == V3 {
        assert!(r.max_payer_lamport_drop.is_some() && r.flags & PAYER_GUARD != 0, "v3: PAYER_GUARD is mandatory (REVIEW #2)");
        assert!(r.tip.is_none() || r.count_lamports(), "v3: CPI_TIP implies COUNT_LAMPORTS (REVIEW #4)");
        assert!(r.required_accounts() <= MAX_IX_ACCOUNTS, "v3: the instruction fits the runtime's 255 accounts");
    }
    if r.layout == V2 {
        assert_eq!(r.tip, None);
        assert_eq!(r.flags & PAYER_GUARD != 0, r.max_payer_lamport_drop.is_some());
        assert_eq!(r.count_lamports(), r.has_native());
    }
    assert_eq!(reencode(r, data), data, "parsing must be canonical: re-encoding gives back the input");
}

// =================================================================================================================
// v2 layout: nexus-arb-v2's tests, carried over unchanged in meaning
// =================================================================================================================

fn route(legs: &[(u8, u8, &[u8])]) -> Result<Route, ArbError> { parse(&encode(1_000, 10, legs)) }
const D24: [u8; 24] = [0u8; 24];

#[test]
fn native_flags_parse_and_leave_the_account_count_intact() {
    let r = route(&[(NATIVE_IN | 18, 8, &D24), (21, 8, &D24)]).unwrap();
    assert!(r.legs()[0].native_in && !r.legs()[0].native_out);
    assert_eq!(r.legs()[0].n_accounts, 18);
    assert!(!r.legs()[1].native_in && !r.legs()[1].native_out);
    assert_eq!(r.legs()[1].n_accounts, 21);
    assert!(has_native(&r));
    assert!(r.count_lamports(), "a v2 route with a native leg counts lamports, as nexus-arb-v2 did");
    let r = route(&[(21, 8, &D24), (NATIVE_OUT | 16, 8, &D24)]).unwrap();
    assert!(r.legs()[1].native_out);
    assert_eq!(r.legs()[1].n_accounts, 16);
    assert_eq!(required_accounts(&r), 2 + (2 + 21) + (2 + 16));
}

#[test]
fn pre_upgrade_encodings_parse_identically() {
    for n in [1u8, 13, 24, 27, 63] {
        let r = route(&[(n, 8, &D24), (n, 8, &D24)]).unwrap();
        assert!(!has_native(&r));
        assert_eq!(r.flags, 0);
        assert!(r.legs().iter().all(|l| l.n_accounts == n as usize && !l.native_in && !l.native_out));
    }
}

#[test]
fn native_lamports_only_chain_into_native_lamports() {
    assert_eq!(route(&[(10, 8, &D24), (NATIVE_IN | 18, 8, &D24)]), Err(ArbError::BadNativeChain { leg: 1 }));
    assert_eq!(route(&[(NATIVE_OUT | 16, 8, &D24), (10, 8, &D24)]), Err(ArbError::BadNativeChain { leg: 0 }));
    assert!(route(&[(10, 8, &D24), (NATIVE_OUT | NATIVE_IN | 16, 8, &D24), (NATIVE_IN | 18, 8, &D24), (10, 8, &D24)]).is_err());
    assert!(route(&[(NATIVE_IN | 18, 8, &D24), (NATIVE_OUT | 16, 8, &D24)]).is_ok());
    assert!(route(&[(NATIVE_IN | 18, 8, &D24), (10, 8, &D24), (NATIVE_OUT | 16, 8, &D24)]).is_ok());
    assert_eq!(error_code(&ArbError::BadNativeChain { leg: 0 }), ERR_BAD_DATA);
}

#[test]
fn native_profit_counts_lamports_and_tokens_together() {
    assert_eq!(check_profit_native(5_000, 1_020_005_000, 9_000_000_000, 8_000_000_000, 1_000_000), Ok(20_000_000));
    assert_eq!(check_profit_native(2_000_000_000, 1_000_000_000, 100, 1_010_000_100, 1), Ok(10_000_000));
    assert_eq!(check_profit_native(0, 999_999_999, 1_000_000_000, 0, 1), Err(ArbError::ProfitBelowMinimum { net: -1, min: 1 }));
}

fn leg(n: u8, len: usize) -> (u8, u8, Vec<u8>) { (n, 8, vec![0xAB; len]) }

#[test]
fn parses_a_five_leg_route_exactly() {
    let ls: Vec<_> = (0..5).map(|i| leg(10 + i, 24 + i as usize)).collect();
    let refs: Vec<(u8, u8, &[u8])> = ls.iter().map(|(n, o, d)| (*n, *o, d.as_slice())).collect();
    let data = encode(201_247_735, 10_000, &refs);
    let r = parse(&data).unwrap();
    assert_eq!((r.layout, r.amount_in, r.min_profit, r.n_legs, r.max_payer_lamport_drop), (V2, 201_247_735, 10_000, 5, None));
    let mut start = HEADER_LEN + 5 * LEG_META_LEN;
    for (i, l) in r.legs().iter().enumerate() {
        assert_eq!(l.n_accounts, 10 + i);
        assert_eq!(l.data_start, start);
        assert_eq!(l.data_len, 24 + i);
        start += 24 + i;
    }
    assert_eq!(required_accounts(&r), 2 + (0..5).map(|i| 2 + 10 + i).sum::<usize>());
}

#[test]
fn every_leg_spends_exactly_what_the_previous_delivered() {
    let balances = [(0u64, 970u64), (20, 532), (5, 1_005), (1_000_000, 1_000_120)];
    let mut input = 1_000u64;
    let mut inputs = vec![input];
    for (i, (b, a)) in balances.iter().enumerate() {
        input = delivered(i, *b, *a).unwrap();
        inputs.push(input);
    }
    assert_eq!(inputs, vec![1_000, 970, 512, 1_000, 120]);
}

#[test]
fn a_leg_that_delivers_nothing_names_itself() {
    let e = delivered(3, 500, 500).unwrap_err();
    assert_eq!(e, ArbError::LegDeliveredNothing { leg: 3 });
    assert_eq!(error_code(&e), LEG_ERR_BASE + 3);
    assert_eq!(error_code(&delivered(0, 500, 400).unwrap_err()), LEG_ERR_BASE);
}

#[test]
fn profit_guard_uses_real_balances_and_rejects_break_even() {
    assert_eq!(check_profit(1_000, 1_010, 5).unwrap(), 10);
    assert!(check_profit(1_000, 1_004, 5).is_err());
    assert!(check_profit(1_000, 990, 1).is_err());
    assert_eq!(error_code(&check_profit(1_000, 990, 1).unwrap_err()), ERR_PROFIT);
    assert_eq!(parse(&encode(1_000, 0, &[(4, 8, &[0u8; 16])])), Err(ArbError::ZeroMinProfit));
    assert_eq!(parse(&encode_v3(0, 1_000, 0, Some(0), None, &[spec(4, 0, &[0u8; 16])])), Err(ArbError::ZeroMinProfit));
}

#[test]
fn malformed_data_is_rejected_before_anything_runs() {
    assert_eq!(parse(&[]), Err(ArbError::DataTooShort));
    let mut d = encode(1, 1, &[(4, 8, &[0u8; 16])]);
    d[0] = 0x01;
    assert_eq!(parse(&d), Err(ArbError::BadVersion(0x01)));
    d[0] = 0x04;
    assert_eq!(parse(&d), Err(ArbError::BadVersion(0x04)));
    assert_eq!(parse(&encode(1, 1, &[])), Err(ArbError::BadLegCount(0)));
    let nine: Vec<(u8, u8, &[u8])> = (0..9).map(|_| (4u8, 8u8, &[0u8; 16][..])).collect();
    assert_eq!(parse(&encode(1, 1, &nine)), Err(ArbError::BadLegCount(9)));
    assert_eq!(parse(&encode(1, 1, &[(4, 12, &[0u8; 16])])), Err(ArbError::AmountOffsetOutOfRange { leg: 0 }));
    let mut t = encode(1, 1, &[(4, 8, &[0u8; 16])]);
    t.push(0);
    assert!(matches!(parse(&t), Err(ArbError::DataLengthMismatch { .. })));
}

#[test]
fn amount_patching_is_bounds_checked() {
    let mut d = vec![0u8; 24];
    assert!(patch_amount(&mut d, 8, 123_456_789));
    assert_eq!(u64::from_le_bytes(d[8..16].try_into().unwrap()), 123_456_789);
    assert!(!patch_amount(&mut d, 20, 1));
    assert!(!patch_amount(&mut d, usize::MAX, 1));
}

/// nexus-arb-v2's pinned cross-language fixture (the TypeScript builder asserted the same hex).
const FIXTURE_HEX: &str = concat!(
    "0202", "0807060504030201", "1817161514131211", "03081000", "04081000",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
);
const GUARDED_FIXTURE_HEX: &str = concat!(
    "0202", "0807060504030201", "1817161514131211", "03081000", "04081000",
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", "2827262524232221"
);

#[test]
fn v2_encoding_matches_the_pinned_cross_language_fixture() {
    let data = encode(0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &[(3, 8, &[0xAA; 16]), (4, 8, &[0xBB; 16])]);
    assert_eq!(hex(&data), FIXTURE_HEX);
    assert_eq!(parse(&data).unwrap().n_legs, 2);
}

#[test]
fn v2_fixture_parses_exactly_as_nexus_arb_v2_did() {
    let r = parse(&unhex(FIXTURE_HEX)).unwrap();
    let mut slots = [LegMeta::default(); MAX_LEGS];
    slots[0] = LegMeta { n_accounts: 3, amount_offset: 8, data_start: 26, data_len: 16, native_in: false, native_out: false, auth_ro: false };
    slots[1] = LegMeta { n_accounts: 4, amount_offset: 8, data_start: 42, data_len: 16, native_in: false, native_out: false, auth_ro: false };
    assert_eq!(r, Route { layout: V2, flags: 0, amount_in: 0x0102_0304_0506_0708, min_profit: 0x1112_1314_1516_1718, max_payer_lamport_drop: None, tip: None, n_legs: 2, leg_slots: slots });
    // and the verbatim nexus-arb-v2 parser agrees field by field
    let o = v2ref::parse(&unhex(FIXTURE_HEX)).unwrap();
    assert_eq!(project_ref(&Ok(o)), project_new(&Ok(r)));
}

#[test]
fn guarded_v2_format_parses_the_trailer_and_nothing_else_changes() {
    let legs: [(u8, u8, &[u8]); 2] = [(3, 8, &[0xAA; 16]), (4, 8, &[0xBB; 16])];
    let data = encode_guarded(0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &legs, 0x2122_2324_2526_2728);
    assert_eq!(hex(&data), GUARDED_FIXTURE_HEX);
    let g = parse(&data).unwrap();
    let old = parse(&encode(0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &legs)).unwrap();
    assert_eq!(g.max_payer_lamport_drop, Some(0x2122_2324_2526_2728));
    assert_eq!(g.flags, PAYER_GUARD);
    assert_eq!((g.amount_in, g.min_profit, g.legs()), (old.amount_in, old.min_profit, old.legs()));
    assert_eq!(parse(&encode_guarded(1, 1, &legs, 0)).unwrap().max_payer_lamport_drop, Some(0));
    for extra in [1usize, 7, 9, 16] {
        let mut d = encode(1, 1, &legs);
        d.extend(std::iter::repeat(0u8).take(extra));
        assert!(matches!(parse(&d), Err(ArbError::DataLengthMismatch { .. })), "{extra} trailing bytes");
    }
    let mut short = encode_guarded(1, 1, &legs, 0);
    short.truncate(short.len() - 1);
    assert!(matches!(parse(&short), Err(ArbError::DataLengthMismatch { .. })));
}

#[test]
fn payer_guard_passes_within_the_limit_and_fails_with_its_own_code() {
    let before = PayerState { lamports: 1_000_000, owner: [0u8; 32], data_len: 0 };
    let at = |lamports| PayerState { lamports, ..before };
    assert_eq!(check_payer_guard(&before, &at(1_000_000), 0, 0), Ok(()));
    assert_eq!(check_payer_guard(&before, &at(2_000_000), 0, 0), Ok(()));
    assert_eq!(check_payer_guard(&before, &at(995_000), 5_000, 0), Ok(()));
    let e = check_payer_guard(&before, &at(994_999), 5_000, 0).unwrap_err();
    assert_eq!(e, ArbError::PayerLamportsDropped { drop: 5_001, max: 5_000 });
    assert_eq!(error_code(&e), ERR_PAYER_GUARD);
    assert_eq!(check_payer_guard(&before, &at(0), u64::MAX - 1, 0), Ok(()));
    assert_eq!(check_payer_guard(&before, &at(0), u64::MAX, 0), Ok(()));
    let e = check_payer_guard(&before, &PayerState { owner: [9u8; 32], ..before }, u64::MAX, 0).unwrap_err();
    assert_eq!((e == ArbError::PayerReassigned, error_code(&ArbError::PayerReassigned)), (true, ERR_PAYER_GUARD));
    assert_eq!(check_payer_guard(&before, &PayerState { data_len: 10, ..before }, u64::MAX, 0), Err(ArbError::PayerReassigned));
}

#[test]
fn payer_guard_allows_exactly_the_cpi_tip_on_top_of_max_drop() {
    let before = PayerState { lamports: 10_000_000, owner: [0u8; 32], data_len: 0 };
    let at = |lamports| PayerState { lamports, ..before };
    // max_drop 0: the tip itself (and nothing more) may leave
    assert_eq!(check_payer_guard(&before, &at(10_000_000 - 40_000), 0, 40_000), Ok(()));
    assert_eq!(check_payer_guard(&before, &at(10_000_000 - 40_001), 0, 40_000), Err(ArbError::PayerLamportsDropped { drop: 40_001, max: 40_000 }));
    // max_drop + tip saturates instead of overflowing: every drop is then allowed
    assert_eq!(check_payer_guard(&before, &at(0), u64::MAX, u64::MAX), Ok(()));
    assert_eq!(check_payer_guard(&before, &at(0), 1, u64::MAX), Ok(()));
    let big = PayerState { lamports: u64::MAX, owner: [0u8; 32], data_len: 0 };
    assert_eq!(check_payer_guard(&big, &PayerState { lamports: 0, ..big }, u64::MAX - 5, 4), Err(ArbError::PayerLamportsDropped { drop: u64::MAX, max: u64::MAX - 1 }));
}

fn token_account(owner: [u8; 32], amount: u64) -> Vec<u8> {
    let mut d = vec![0u8; TOKEN_ACCOUNT_LEN];
    d[..32].copy_from_slice(&[5u8; 32]);
    d[32..64].copy_from_slice(&owner);
    d[64..72].copy_from_slice(&amount.to_le_bytes());
    d[108] = 1;
    d
}

#[test]
fn token_view_only_sees_initialized_token_accounts_owned_by_the_authority() {
    let me = [7u8; 32];
    assert_eq!(payer_token_view(&token_account(me, 42), &me).unwrap().amount, 42);
    assert!(payer_token_view(&token_account([8u8; 32], 42), &me).is_none());
    let mut uninit = token_account(me, 42);
    uninit[108] = 0;
    assert!(payer_token_view(&uninit, &me).is_none());
    assert!(payer_token_view(&[0u8; 82], &me).is_none());
    assert!(payer_token_view(&vec![0u8; TOKEN_ACCOUNT_LEN], &me).is_none());
    let mut ext = token_account(me, 42);
    ext.extend_from_slice(&[2u8, 0, 0, 0]);
    assert!(payer_token_view(&ext, &me).is_some());
    ext[TOKEN_ACCOUNT_LEN] = 1;
    assert!(payer_token_view(&ext, &me).is_none());
}

#[test]
fn token_guard_allows_the_input_spend_and_nothing_more() {
    let me = [7u8; 32];
    let before = payer_token_view(&token_account(me, 1_000), &me).unwrap();
    let view = |amount| payer_token_view(&token_account(me, amount), &me).unwrap();
    assert_eq!(check_token_guard(2, &before, Some(&view(600)), 400), Ok(()));
    assert_eq!(check_token_guard(2, &before, Some(&view(700)), 400), Ok(()));
    assert_eq!(check_token_guard(2, &before, Some(&view(5_000)), 0), Ok(()));
    let e = check_token_guard(2, &before, Some(&view(599)), 400).unwrap_err();
    assert_eq!(e, ArbError::TokenAccountDrained { leg: 2, drop: 401, allowed: 400 });
    assert_eq!(error_code(&e), ERR_TOKEN_GUARD);
    assert_eq!(error_code(&check_token_guard(0, &before, Some(&view(999)), 0).unwrap_err()), ERR_TOKEN_GUARD);
    assert_eq!(check_token_guard(1, &before, None, u64::MAX), Err(ArbError::TokenAccountAuthorityChanged { leg: 1 }));
    let mut delegated = token_account(me, 1_000);
    delegated[72] = 1;
    delegated[76..108].copy_from_slice(&[9u8; 32]);
    let d = payer_token_view(&delegated, &me).unwrap();
    assert_eq!(check_token_guard(1, &before, Some(&d), u64::MAX), Err(ArbError::TokenAccountAuthorityChanged { leg: 1 }));
    let mut frozen = token_account(me, 1_000);
    frozen[108] = 2;
    let f = payer_token_view(&frozen, &me).unwrap();
    assert_eq!(error_code(&check_token_guard(1, &before, Some(&f), u64::MAX).unwrap_err()), ERR_TOKEN_GUARD);
}

#[test]
fn v2_log_markers_are_unchanged() {
    let m = delivered_log(3, 0x0102_0304_0506_0708);
    assert_eq!(&m[..7], b"NXV2OUT");
    assert_eq!(m[7], 3);
    assert_eq!(u64::from_le_bytes(m[8..16].try_into().unwrap()), 0x0102_0304_0506_0708);
    let m = leg_marker(5);
    assert_eq!(&m[..7], b"NXV2LEG");
    assert_eq!(m[7], 5);
}

#[test]
fn allowlist_compares_raw_bytes() {
    let a = [7u8; 32];
    let b = [9u8; 32];
    assert!(is_allowlisted(&a, &[b, a]));
    assert!(!is_allowlisted(&[1u8; 32], &[b, a]));
}

// =================================================================================================================
// v3 layout
// =================================================================================================================

fn spec(n_accounts: u8, flags: u8, data: &[u8]) -> LegSpec<'_> { LegSpec { n_accounts, flags, amount_offset: 8, data } }
const TIP: TipParams = TipParams { bps: 3_000, floor: 1_000, cap: 50_000_000, account_ix: 3 };

/// The v3 cross-language fixture: COUNT_LAMPORTS + PAYER_GUARD + CPI_TIP, a 70-account leg and a 3-account leg.
/// The engine's Rust builder must produce exactly these bytes.
const V3_FIXTURE_HEX: &str = concat!(
    "03", "07", "02",                       // version 3, flags PG|TIP|COUNT_LAMPORTS, 2 legs
    "0807060504030201",                     // amount_in
    "1817161514131211",                     // min_profit
    "2827262524232221",                     // max_payer_lamport_drop
    "b80b", "3837363534333231", "4847464544434241", "07", // tip: 3000 bps, floor, cap, Jito tip account #7
    "46", "00", "08", "1000",               // leg 0: 70 accounts, no leg flags, offset 8, 16 bytes
    "03", "00", "08", "1000",               // leg 1: 3 accounts
    "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
);

#[test]
fn v3_encoding_matches_the_pinned_fixture_and_parses_exactly() {
    let tip = TipParams { bps: 3_000, floor: 0x3132_3334_3536_3738, cap: 0x4142_4344_4546_4748, account_ix: 7 };
    let data = encode_v3(COUNT_LAMPORTS, 0x0102_0304_0506_0708, 0x1112_1314_1516_1718, Some(0x2122_2324_2526_2728), Some(tip),
        &[spec(70, 0, &[0xAA; 16]), spec(3, 0, &[0xBB; 16])]);
    assert_eq!(hex(&data), V3_FIXTURE_HEX);
    let r = parse(&data).unwrap();
    let meta = V3_HEADER_LEN + V3_GUARD_LEN + V3_TIP_LEN + 2 * V3_LEG_META_LEN;
    let mut slots = [LegMeta::default(); MAX_LEGS];
    slots[0] = LegMeta { n_accounts: 70, amount_offset: 8, data_start: meta, data_len: 16, native_in: false, native_out: false, auth_ro: false };
    slots[1] = LegMeta { n_accounts: 3, amount_offset: 8, data_start: meta + 16, data_len: 16, native_in: false, native_out: false, auth_ro: false };
    assert_eq!(r, Route {
        layout: V3, flags: PAYER_GUARD | CPI_TIP | COUNT_LAMPORTS, amount_in: 0x0102_0304_0506_0708, min_profit: 0x1112_1314_1516_1718,
        max_payer_lamport_drop: Some(0x2122_2324_2526_2728), tip: Some(tip), n_legs: 2, leg_slots: slots,
    });
    assert_eq!(r.required_accounts(), 2 + (2 + 70) + (2 + 3) + 2);
    assert_eq!(r.legs_end(), 2 + (2 + 70) + (2 + 3));
}

#[test]
fn v3_optional_blocks_appear_exactly_when_flagged() {
    let legs = [spec(9, 0, &D24)];
    let base = encode_v3(0, 5, 1, Some(77), None, &legs);
    assert_eq!(base.len(), V3_HEADER_LEN + V3_GUARD_LEN + V3_LEG_META_LEN + 24);
    let g = parse(&base).unwrap();
    assert_eq!((g.flags, g.max_payer_lamport_drop, g.tip), (PAYER_GUARD, Some(77), None));
    let t = parse(&encode_v3(COUNT_LAMPORTS, 5, 1, Some(0), Some(TIP), &legs)).unwrap();
    assert_eq!((t.flags, t.max_payer_lamport_drop, t.tip), (PAYER_GUARD | CPI_TIP | COUNT_LAMPORTS, Some(0), Some(TIP)));
    // a flag whose block is missing is refused (here the tip block is absent, so the leg metas are misread)
    let mut d = encode_v3(COUNT_LAMPORTS, 5, 1, Some(0), None, &legs);
    d[1] |= CPI_TIP;
    assert!(parse(&d).is_err());
    // and a guard field without the flag: the 8 bytes are read as leg metas, which cannot line up
    let mut d = base.clone();
    d[1] &= !PAYER_GUARD;
    assert!(parse(&d).is_err());
}

#[test]
fn v3_fixes_the_v2_wide_leg_bug() {
    // v3: every count parses as itself, up to what fits the runtime's 255 accounts per instruction (2 + 2 + n)
    for n in [1u8, 63, 64, 65, 70, 127, 128, 191, 192, 251] {
        let r = parse(&encode_v3(0, 1, 1, Some(0), None, &[spec(n, 0, &D24)])).unwrap();
        assert_eq!(r.legs()[0].n_accounts, n as usize, "v3 n_accounts {n}");
        assert!(!r.has_native());
    }
    for n in [252u8, 255] {
        assert_eq!(parse(&encode_v3(0, 1, 1, Some(0), None, &[spec(n, 0, &D24)])), Err(ArbError::TooManyAccounts { needed: 4 + n as usize }));
    }
    // v2: the same 70-account leg is misread as a 6-account NATIVE_OUT leg. That is the bug v3 fixes.
    let r = parse(&encode(1, 1, &[(70, 8, &D24)])).unwrap();
    assert_eq!((r.legs()[0].n_accounts, r.legs()[0].native_out), (6, true));
    // 128 accounts read as NATIVE_IN with 0 accounts
    let r = parse(&encode(1, 1, &[(128, 8, &D24)])).unwrap();
    assert_eq!((r.legs()[0].n_accounts, r.legs()[0].native_in), (0, true));
}

#[test]
fn v3_rejects_zero_accounts_unknown_leg_flags_and_bad_offsets() {
    assert_eq!(parse(&encode_v3(0, 1, 1, Some(0), None, &[spec(0, 0, &D24)])), Err(ArbError::ZeroAccounts { leg: 0 }));
    for f in [0x08u8, 0x10, 0x40, 0x80, 0xFF] {
        assert_eq!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), None, &[spec(5, f, &D24)])), Err(ArbError::BadLegFlags { leg: 0, flags: f }));
    }
    let bad = LegSpec { n_accounts: 5, flags: 0, amount_offset: 17, data: &D24 };
    assert_eq!(parse(&encode_v3(0, 1, 1, Some(0), None, &[spec(5, 0, &D24), bad])), Err(ArbError::AmountOffsetOutOfRange { leg: 1 }));
    let edge = LegSpec { n_accounts: 5, flags: 0, amount_offset: 16, data: &D24 };
    assert!(parse(&encode_v3(0, 1, 1, Some(0), None, &[edge])).is_ok());
    assert_eq!(parse(&encode_v3(0, 1, 1, Some(0), None, &[])), Err(ArbError::BadLegCount(0)));
    let nine: Vec<LegSpec> = (0..9).map(|_| spec(4, 0, &D24)).collect();
    assert_eq!(parse(&encode_v3(0, 1, 1, Some(0), None, &nine)), Err(ArbError::BadLegCount(9)));
}

#[test]
fn v3_reserved_features_are_unsupported_and_bits_6_7_are_invalid() {
    let legs = [spec(5, 0, &D24)];
    for f in [SELF_SIZE, BASKET, NOOP_ON_MISS, SELF_SIZE | BASKET] {
        let e = parse(&encode_v3(f, 1, 1, Some(0), None, &legs)).unwrap_err();
        assert_eq!(e, ArbError::UnsupportedFlags(f | PAYER_GUARD));
        assert_eq!(error_code(&e), ERR_UNSUPPORTED);
    }
    for f in [0x40u8, 0x80, 0xC0] {
        let e = parse(&encode_v3(f, 1, 1, Some(0), None, &legs)).unwrap_err();
        assert_eq!(e, ArbError::InvalidFlags(f | PAYER_GUARD));
        assert_eq!(error_code(&e), ERR_BAD_DATA);
    }
}

#[test]
fn v3_tip_parameters_are_validated() {
    let legs = [spec(5, 0, &D24)];
    let ok = |t: TipParams| parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), Some(t), &legs));
    assert!(ok(TipParams { bps: 10_000, floor: 0, cap: 0, account_ix: 0 }).is_ok());
    assert!(ok(TipParams { bps: 0, floor: u64::MAX, cap: u64::MAX, account_ix: 7 }).is_ok());
    assert_eq!(ok(TipParams { bps: 10_001, floor: 0, cap: 1, account_ix: 0 }), Err(ArbError::BadTipParams));
    assert_eq!(ok(TipParams { bps: 1, floor: 2, cap: 1, account_ix: 0 }), Err(ArbError::BadTipParams));
    assert_eq!(ok(TipParams { bps: 1, floor: 0, cap: 1, account_ix: 8 }), Err(ArbError::BadTipParams));
    assert_eq!(error_code(&ArbError::BadTipParams), ERR_BAD_DATA);
}

#[test]
fn v3_native_legs_need_count_lamports_and_a_valid_chain() {
    let native = [spec(18, LEG_NATIVE_IN, &D24), spec(21, 0, &D24)];
    assert_eq!(parse(&encode_v3(0, 1, 1, Some(0), None, &native)), Err(ArbError::NativeNeedsCountLamports { leg: 0 }));
    let r = parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), None, &native)).unwrap();
    assert!(r.legs()[0].native_in && r.count_lamports() && r.legs()[0].flags() == LEG_NATIVE_IN);
    let out = [spec(21, 0, &D24), spec(16, LEG_NATIVE_OUT, &D24)];
    assert!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), None, &out)).unwrap().legs()[1].native_out);
    assert_eq!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), None, &[spec(10, 0, &D24), spec(10, LEG_NATIVE_IN, &D24)])), Err(ArbError::BadNativeChain { leg: 1 }));
    assert_eq!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), None, &[spec(10, LEG_NATIVE_OUT, &D24), spec(10, 0, &D24)])), Err(ArbError::BadNativeChain { leg: 0 }));
    assert!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), None, &[spec(10, LEG_NATIVE_OUT, &D24), spec(10, LEG_NATIVE_IN, &D24)])).is_ok());
    // a native leg may carry 64+ accounts in v3 (pump.fun buys are 16-18 today; v2 had only 6 bits for the count)
    let wide = parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), None, &[spec(200, LEG_NATIVE_IN, &D24), spec(9, 0, &D24)])).unwrap();
    assert_eq!((wide.legs()[0].n_accounts, wide.legs()[0].native_in), (200, true));
}

#[test]
fn v3_length_must_be_exact() {
    let d = encode_v3(COUNT_LAMPORTS, 1, 1, Some(5), Some(TIP), &[spec(5, 0, &D24), spec(6, 0, &[1u8; 40])]);
    assert!(parse(&d).is_ok());
    for cut in 1..d.len() {
        assert!(parse(&d[..d.len() - cut]).is_err(), "truncated by {cut}");
    }
    for extra in [1usize, 7, 8, 9, 64] {
        let mut x = d.clone();
        x.extend(std::iter::repeat(0u8).take(extra));
        assert!(matches!(parse(&x), Err(ArbError::DataLengthMismatch { .. })), "{extra} trailing bytes (v3 has no trailer)");
    }
}

// ---- guard and tip arithmetic ----------------------------------------------------------------------------------

const M: u64 = u64::MAX;

#[test]
fn gain_is_exact_at_the_u64_extremes() {
    assert_eq!(gain(0, M, 0, M, true), 2 * (M as i128));
    assert_eq!(gain(M, 0, M, 0, true), -2 * (M as i128));
    assert_eq!(gain(M, 0, 0, M, true), 0);
    assert_eq!(gain(0, M, M, 0, false), M as i128, "lamports are ignored without COUNT_LAMPORTS");
    assert_eq!(gain(10, 15, 100, 90, true), -5);
    assert_eq!(gain(10, 15, 100, 90, false), 5);
}

#[test]
fn cpi_tip_is_the_clamped_share_of_the_gain() {
    let p = |bps, floor, cap| TipParams { bps, floor, cap, account_ix: 0 };
    assert_eq!(cpi_tip(1_000_000, &p(3_000, 1_000, 10_000_000)), 300_000); // the share
    assert_eq!(cpi_tip(1_000, &p(3_000, 1_000, 10_000_000)), 1_000); // floor
    assert_eq!(cpi_tip(1_000_000_000, &p(3_000, 1_000, 10_000_000)), 10_000_000); // cap
    assert_eq!(cpi_tip(0, &p(3_000, 1_000, 10_000_000)), 1_000); // g = 0: floor
    assert_eq!(cpi_tip(-5_000_000, &p(10_000, 7, 10_000_000)), 7); // g < 0: floor, never a negative share
    assert_eq!(cpi_tip(9_999, &p(1, 0, M)), 0); // rounds down
    assert_eq!(cpi_tip(10_000, &p(1, 0, M)), 1);
    assert_eq!(cpi_tip(12_345, &p(0, 0, M)), 0); // bps 0: floor only
    assert_eq!(cpi_tip(12_345, &p(10_000, 0, M)), 12_345); // bps 10000: the whole gain
    // i128 edges: the largest possible gain (2^65 - 2) times 10_000 bps does not overflow, and caps at u64::MAX
    let gmax = 2 * (M as i128);
    assert_eq!(cpi_tip(gmax, &p(10_000, 0, M)), M);
    assert_eq!(cpi_tip(gmax, &p(5_000, 0, M)), M); // exactly (2^65-2)/2 = 2^64-1
    assert_eq!(cpi_tip(gmax, &p(4_999, 0, M)), ((gmax * 4_999) / 10_000) as u64);
    assert_eq!(cpi_tip(-gmax, &p(10_000, M, M)), M);
    assert_eq!(cpi_tip(i128::MAX, &p(10_000, 0, M)), M, "saturating multiply even far outside the reachable range");
}

#[test]
fn guard_compares_gain_minus_tip_with_min_profit_in_i128() {
    assert_eq!(check_guard(10, 10, 0), Ok(()));
    assert_eq!(check_guard(9, 10, 0), Err(ArbError::ProfitBelowMinimum { net: 9, min: 10 }));
    assert_eq!(check_guard(1_010_000, 10_000, 1_000_000), Ok(()));
    assert_eq!(check_guard(1_009_999, 10_000, 1_000_000), Err(ArbError::ProfitBelowMinimum { net: 9_999, min: 10_000 }));
    // the extremes: no overflow, exact nets
    let gmax = 2 * (M as i128);
    assert_eq!(check_guard(gmax, M, M), Ok(()));
    assert_eq!(check_guard(gmax - 1, M, M), Err(ArbError::ProfitBelowMinimum { net: M as i128 - 1, min: M }));
    assert_eq!(check_guard(-gmax, 1, M), Err(ArbError::ProfitBelowMinimum { net: -gmax - M as i128, min: 1 }));
    assert_eq!(error_code(&check_guard(-1, 1, 0).unwrap_err()), ERR_PROFIT);
    // v2's two checks are special cases
    assert_eq!(check_profit(5, 20, 10).is_ok(), check_guard(gain(5, 20, 0, 0, false), 10, 0).is_ok());
    assert_eq!(check_profit_native(5, 20, 100, 94, 10).is_ok(), check_guard(gain(5, 20, 100, 94, true), 10, 0).is_ok());
}

#[test]
fn a_tip_above_the_gain_fails_the_guard_instead_of_paying_from_capital() {
    // gain 2_000, floor 5_000: g − tip = −3_000 < min_profit, so it reverts and never pays a tip larger than the gain
    let t = TipParams { bps: 1_000, floor: 5_000, cap: 1_000_000, account_ix: 0 };
    let g = 2_000i128;
    let tip = cpi_tip(g, &t);
    assert_eq!(tip, 5_000);
    assert!(check_guard(g, 1, tip).is_err());
}

// ---- logs --------------------------------------------------------------------------------------------------------

#[test]
fn summary_and_leg_records_round_trip() {
    let s = Summary {
        layout: V3, flags: PAYER_GUARD | CPI_TIP | COUNT_LAMPORTS, n_legs: 2, result: ERR_PROFIT,
        amount_in: 1_000_000_000, min_profit: 15_000, tip: 1_000, gain: -(2 * (M as i128)), quote_delta: -(M as i128),
        lamport_delta: -(M as i128), cu_remaining: 123_456,
    };
    let b = summary_log(&s);
    assert_eq!(b.len(), SUMMARY_LEN);
    assert_eq!(&b[..4], b"AXS1");
    assert_eq!(decode_summary(&b), Some(s));
    assert_eq!(decode_summary(&b[..91]), None);
    let l = LegLog { leg: 7, venue: 11, flags: LEG_NATIVE_IN | LEG_NATIVE_OUT, input: M, delivered: 1 };
    let b = leg_log(&l);
    assert_eq!(b.len(), LEG_LOG_LEN);
    assert_eq!(&b[..4], b"AXL1");
    assert_eq!(b[7], 0, "reserved byte");
    assert_eq!(decode_leg_log(&b), Some(l));
    // the records can never be mistaken for the v2 markers (8 and 16 bytes) or for each other
    assert!(![8, 16, SUMMARY_LEN].contains(&LEG_LOG_LEN) && ![8, 16, LEG_LOG_LEN].contains(&SUMMARY_LEN));
}

/// Pinned record bytes for the off-chain decoders (LOGS.md shows the same examples).
#[test]
fn log_records_match_the_pinned_bytes() {
    let l = leg_log(&LegLog { leg: 1, venue: 6, flags: 0, input: 1_000_000_000, delivered: 1_092_000_000 });
    assert_eq!(hex(&l), concat!("41584c31", "01", "06", "00", "00", "00ca9a3b00000000", "0099164100000000"));
    let s = summary_log(&Summary { layout: 3, flags: 6, n_legs: 2, result: 0, amount_in: 1, min_profit: 2, tip: 3, gain: -1, quote_delta: 4, lamport_delta: -5, cu_remaining: 6 });
    assert_eq!(hex(&s), concat!(
        "41585331", "03", "06", "02", "00", "00000000", "0100000000000000", "0200000000000000", "0300000000000000",
        "ffffffffffffffffffffffffffffffff", "04000000000000000000000000000000", "fbffffffffffffffffffffffffffffff",
        "0600000000000000"));
}

// ---- codes and keys ----------------------------------------------------------------------------------------------

#[test]
fn error_codes_are_pinned_unique_and_outside_token_and_anchor_ranges() {
    let all = [ERR_BAD_DATA, ERR_PROFIT, ERR_NOT_ALLOWLISTED, ERR_NOT_TOKEN_ACCOUNT, ERR_PAYER_GUARD, ERR_TOKEN_GUARD,
        ERR_FOREIGN_SIGNER, ERR_UNSUPPORTED, ERR_BAD_ACCOUNTS, ERR_TIP_ACCOUNT, ERR_TIP_FUNDS, ERR_QUOTE_NOT_WSOL,
        LEG_ERR_BASE, LEG_ERR_BASE + MAX_LEGS as u32 - 1];
    for code in all { assert!(code > 1_000_000, "code {code:#x} could be mistaken for a venue or token error"); }
    for (i, a) in all.iter().enumerate() { for b in &all[i + 1..] { assert_ne!(a, b); } }
    assert_eq!(
        [ERR_BAD_DATA, ERR_PROFIT, ERR_NOT_ALLOWLISTED, ERR_NOT_TOKEN_ACCOUNT, ERR_PAYER_GUARD, ERR_TOKEN_GUARD, ERR_FOREIGN_SIGNER],
        [0x4E58_0001, 0x4E58_0002, 0x4E58_0003, 0x4E58_0004, 0x4E58_0005, 0x4E58_0006, 0x4E58_0007],
        "nexus-arb-v2's codes keep their numbers"
    );
    assert_eq!([ERR_UNSUPPORTED, ERR_BAD_ACCOUNTS, ERR_TIP_ACCOUNT, ERR_TIP_FUNDS, ERR_QUOTE_NOT_WSOL], [0x4E58_0008, 0x4E58_0009, 0x4E58_000A, 0x4E58_000B, 0x4E58_000C]);
    assert_eq!(LEG_ERR_BASE, 0x4E58_0100);
}

#[test]
fn compiled_in_keys_decode_to_distinct_32_byte_keys() {
    let mut all: Vec<Vec<u8>> = Vec::new();
    for k in ALLOWLIST_B58.iter().chain(JITO_TIP_ACCOUNTS_B58.iter()).chain([WSOL_MINT_B58, SYSTEM_PROGRAM_B58, TOKEN_PROGRAM_B58, TOKEN_2022_PROGRAM_B58].iter()) {
        let b = b58(k);
        assert_eq!(b.len(), 32, "{k}");
        assert!(!all.contains(&b), "duplicate key {k}");
        all.push(b);
    }
    assert_eq!(b58(SYSTEM_PROGRAM_B58), vec![0u8; 32]);
    assert_eq!(ALLOWLIST_B58.len(), ALLOWLIST_NAMES.len());
}

#[test]
fn allowlist_is_nexus_arb_v2s_list_in_the_same_order() {
    // the venue id in AXL1 is the position in this list; nexus-arb-v2 has the same 12 programs in the same order
    let src = include_str!("../../nexus-arb-v2/src/lib.rs");
    let listed: Vec<&str> = src.lines().filter_map(|l| l.trim().strip_prefix("pubkey!(\"")).map(|l| &l[..l.find('"').unwrap()])
        .filter(|k| !k.starts_with("Token")).collect();
    assert_eq!(listed, ALLOWLIST_B58.to_vec());
}

// =================================================================================================================
// REVIEW.md regressions (host side). tests/litesvm.rs checks the same fixes on the built program under mainnet
// features; #1 (the remaining-CU syscall) is covered there by the ELF syscall audit and every route test.
// =================================================================================================================

/// REVIEW #2: a v3 route without PAYER_GUARD is refused before anything runs; v2 keeps the trailer optional.
#[test]
fn review_02_v3_payer_guard_is_mandatory() {
    let legs = [spec(9, 0, &D24), spec(9, 0, &D24)];
    for other in [0u8, COUNT_LAMPORTS] {
        let e = parse(&encode_v3(other, 1, 1, None, None, &legs)).unwrap_err();
        assert_eq!(e, ArbError::PayerGuardRequired);
        assert_eq!(error_code(&e), ERR_BAD_DATA);
    }
    assert_eq!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, None, Some(TIP), &legs)), Err(ArbError::PayerGuardRequired));
    // any max_drop is accepted once the field is there, including 0 and u64::MAX
    for d in [0, 1, u64::MAX] {
        assert_eq!(parse(&encode_v3(0, 1, 1, Some(d), None, &legs)).unwrap().max_payer_lamport_drop, Some(d));
    }
    // v2: nexus-arb-v2 compatibility, the trailer stays optional
    assert_eq!(parse(&encode(1, 1, &[(9, 8, &D24), (9, 8, &D24)])).unwrap().max_payer_lamport_drop, None);
}

/// REVIEW #4: CPI_TIP without COUNT_LAMPORTS is refused (the tip is paid in lamports the gain would not see).
#[test]
fn review_04_cpi_tip_requires_count_lamports() {
    let legs = [spec(9, 0, &D24), spec(9, 0, &D24)];
    let e = parse(&encode_v3(0, 1, 1, Some(0), Some(TIP), &legs)).unwrap_err();
    assert_eq!(e, ArbError::TipNeedsCountLamports);
    assert_eq!(error_code(&e), ERR_BAD_DATA);
    assert!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), Some(TIP), &legs)).is_ok());
    // without a tip, COUNT_LAMPORTS stays optional (a quote-only route, e.g. USDC)
    assert!(parse(&encode_v3(0, 1, 1, Some(0), None, &legs)).is_ok());
}

/// REVIEW #5: a tip may not leave the authority below its rent-exempt minimum.
#[test]
fn review_05_tip_must_leave_the_authority_rent_exempt() {
    const RENT0: u64 = 890_880; // the rent-exempt minimum of a 0-byte account on mainnet
    assert_eq!(check_tip_funds(0, 0, RENT0), Ok(()), "a zero tip moves nothing");
    // the reviewer's case: 1,000,000 lamports and a 500,000 tip
    let e = check_tip_funds(500_000, 1_000_000, RENT0).unwrap_err();
    assert_eq!(e, ArbError::TipExceedsBalance { tip: 500_000, lamports: 1_000_000, keep: RENT0 });
    assert_eq!(error_code(&e), ERR_TIP_FUNDS);
    assert_eq!(check_tip_funds(1_000_000 - RENT0, 1_000_000, RENT0), Ok(()), "exactly rent-exempt afterwards");
    assert!(check_tip_funds(1_000_000 - RENT0 + 1, 1_000_000, RENT0).is_err());
    assert!(check_tip_funds(2, 1, 0).is_err(), "more than the balance");
    assert_eq!(check_tip_funds(u64::MAX, u64::MAX, 0), Ok(()));
    assert!(check_tip_funds(u64::MAX, u64::MAX, 1).is_err());
}

/// REVIEW #5: the rent-exempt minimum the program computes from the Rent sysvar, integer-only.
#[test]
fn review_05_rent_exempt_minimum_matches_both_rent_representations() {
    let legacy = 2.0f64.to_le_bytes();
    let simd0194 = 1.0f64.to_le_bytes();
    assert_eq!(rent_exempt_minimum(3_480, legacy, 0), Some(890_880));
    assert_eq!(rent_exempt_minimum(6_960, simd0194, 0), Some(890_880));
    assert_eq!(rent_exempt_minimum(3_480, legacy, 165), Some(2_039_280), "a token account");
    assert_eq!(rent_exempt_minimum(6_960, simd0194, 165), Some(2_039_280));
    // a threshold below 2.0 is rounded up to 2.0 (never under-states the minimum); above 2.0 or negative: refused
    assert_eq!(rent_exempt_minimum(3_480, 1.5f64.to_le_bytes(), 0), Some(890_880));
    assert_eq!(rent_exempt_minimum(3_480, 0.5f64.to_le_bytes(), 0), Some(890_880));
    assert_eq!(rent_exempt_minimum(3_480, 2.5f64.to_le_bytes(), 0), None);
    assert_eq!(rent_exempt_minimum(3_480, (-1.0f64).to_le_bytes(), 0), None);
    assert_eq!(rent_exempt_minimum(u64::MAX, legacy, 0), None, "overflow");
    // agrees with the f64 formula wherever that formula is exact
    for (lpb, t) in [(3_480u64, 2.0f64), (6_960, 1.0), (1, 2.0), (0, 1.0)] {
        for len in [0u64, 1, 82, 165, 10 * 1024 * 1024] {
            assert_eq!(rent_exempt_minimum(lpb, t.to_le_bytes(), len), Some((((128 + len) * lpb) as f64 * t) as u64));
        }
    }
}

/// REVIEW #6: one v3 leg cannot be both NATIVE_IN and NATIVE_OUT; v2 parses it as nexus-arb-v2 did.
#[test]
fn review_06_v3_leg_cannot_be_both_native_in_and_out() {
    let both = LEG_NATIVE_IN | LEG_NATIVE_OUT;
    let e = parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), None, &[spec(7, both, &D24), spec(7, LEG_NATIVE_IN, &D24), spec(7, 0, &D24)])).unwrap_err();
    assert_eq!(e, ArbError::BadLegFlags { leg: 0, flags: both });
    assert_eq!(error_code(&e), ERR_BAD_DATA);
    let r = parse(&encode(1, 1, &[(NATIVE_IN | NATIVE_OUT | 7, 8, &D24), (NATIVE_IN | 7, 8, &D24), (7, 8, &D24)])).unwrap();
    assert!(r.legs()[0].native_in && r.legs()[0].native_out, "v2 stays byte-compatible with nexus-arb-v2");
}

/// REVIEW #7: the token-owner test the program applies to a v3 quote account and every token output.
#[test]
fn review_07_token_owner_field_must_be_the_authority() {
    let me = [7u8; 32];
    assert!(token_owner_is(&token_account(me, 1), &me));
    assert!(!token_owner_is(&token_account([8u8; 32], 1), &me));
    assert!(!token_owner_is(&[7u8; 71], &me), "too short to be a token account");
    assert_eq!(error_code(&ArbError::QuoteNotAuthoritys), ERR_BAD_ACCOUNTS);
    assert_eq!(error_code(&ArbError::OutputNotAuthoritys { leg: 1 }), ERR_BAD_ACCOUNTS);
}

/// REVIEW #11: MAX_IX_ACCOUNTS is enforced by the v3 parser (2 + Σ(2 + n_i) [+ 2] <= 255).
#[test]
fn review_11_v3_route_must_fit_255_accounts() {
    let fits: Vec<LegSpec> = (0..3).map(|_| spec(81, 0, &D24)).collect(); // 2 + 3 × 83 = 251
    assert_eq!(parse(&encode_v3(0, 1, 1, Some(0), None, &fits)).unwrap().required_accounts(), 251);
    // the same with a tip: 253
    assert_eq!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), Some(TIP), &fits)).unwrap().required_accounts(), 253);
    let edge: Vec<LegSpec> = vec![spec(81, 0, &D24), spec(81, 0, &D24), spec(85, 0, &D24)]; // 255
    assert!(parse(&encode_v3(0, 1, 1, Some(0), None, &edge)).is_ok());
    assert_eq!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), Some(TIP), &edge)), Err(ArbError::TooManyAccounts { needed: 257 }));
    let over: Vec<LegSpec> = vec![spec(81, 0, &D24), spec(81, 0, &D24), spec(86, 0, &D24)]; // 256
    let e = parse(&encode_v3(0, 1, 1, Some(0), None, &over)).unwrap_err();
    assert_eq!(error_code(&e), ERR_BAD_DATA);
    assert_eq!(e, ArbError::TooManyAccounts { needed: 256 });
}

/// REVIEW #14: LEG_AUTH_RO parses on token legs, round-trips in the leg flags, and is refused on native legs.
#[test]
fn review_14_leg_auth_ro_flag() {
    let r = parse(&encode_v3(0, 1, 1, Some(0), None, &[spec(9, LEG_AUTH_RO, &D24), spec(9, 0, &D24)])).unwrap();
    assert!(r.legs()[0].auth_ro && !r.legs()[1].auth_ro);
    assert_eq!(r.legs()[0].flags(), LEG_AUTH_RO);
    for f in [LEG_AUTH_RO | LEG_NATIVE_IN, LEG_AUTH_RO | LEG_NATIVE_OUT] {
        let legs = if f & LEG_NATIVE_IN != 0 { [spec(9, f, &D24), spec(9, 0, &D24)] } else { [spec(9, 0, &D24), spec(9, f, &D24)] };
        let leg = if f & LEG_NATIVE_IN != 0 { 0 } else { 1 };
        assert_eq!(parse(&encode_v3(COUNT_LAMPORTS, 1, 1, Some(0), None, &legs)), Err(ArbError::BadLegFlags { leg, flags: f }));
    }
    // v2 has no such flag
    assert!(parse(&encode(1, 1, &[(9, 8, &D24), (9, 8, &D24)])).unwrap().legs().iter().all(|l| !l.auth_ro));
}

// =================================================================================================================
// Property tests (proptest) and a deterministic mutation fuzzer
// =================================================================================================================

type Proj = String;
fn project_ref(r: &Result<v2ref::Route, v2ref::ArbError>) -> Proj {
    match r {
        Ok(r) => format!("ok {} {} {:?} {:?}", r.amount_in, r.min_profit,
            r.legs.iter().map(|l| (l.n_accounts, l.amount_offset, l.data_start, l.data_len, l.native_in, l.native_out)).collect::<Vec<_>>(),
            r.max_payer_lamport_drop),
        Err(e) => format!("err {:?}", e),
    }
}
fn project_new(r: &Result<Route, ArbError>) -> Proj {
    match r {
        Ok(r) => format!("ok {} {} {:?} {:?}", r.amount_in, r.min_profit,
            r.legs().iter().map(|l| (l.n_accounts, l.amount_offset, l.data_start, l.data_len, l.native_in, l.native_out)).collect::<Vec<_>>(),
            r.max_payer_lamport_drop),
        Err(e) => format!("err {:?}", e),
    }
}

/// The independent oracle for native chaining: adjacent legs must agree, native_out(a) == native_in(b).
fn chain_ok(flags: &[u8]) -> bool { flags.windows(2).all(|w| (w[0] & LEG_NATIVE_OUT != 0) == (w[1] & LEG_NATIVE_IN != 0)) }

/// The independent oracle for one v3 leg_flags byte: known bits only, at most one native flag, AUTH_RO only on a
/// token leg.
fn leg_flags_ok(f: u8) -> bool {
    let native = f & (LEG_NATIVE_IN | LEG_NATIVE_OUT);
    f & !(LEG_NATIVE_IN | LEG_NATIVE_OUT | LEG_AUTH_RO) == 0 && native != (LEG_NATIVE_IN | LEG_NATIVE_OUT) && !(native != 0 && f & LEG_AUTH_RO != 0)
}

#[derive(Debug, Clone)]
struct LegGen { n: u8, flags: u8, off: u8, data: Vec<u8> }

/// n_accounts is mostly small (so that 8-leg routes still fit 255 accounts) with a tail up to 255.
fn leg_gen(max_flags: u8) -> impl Strategy<Value = LegGen> {
    (prop_oneof![4 => 1u8..=30, 1 => 1u8..=255], 0u8..=max_flags, 0u8..=48).prop_flat_map(|(n, flags, off)| {
        vec(any::<u8>(), (off as usize + 8)..=(off as usize + 72)).prop_map(move |data| LegGen { n, flags, off, data })
    })
}

fn tip_gen() -> impl Strategy<Value = TipParams> {
    (0u16..=10_000, any::<u64>(), 0u8..8).prop_flat_map(|(bps, floor, ix)| (floor..=u64::MAX).prop_map(move |cap| TipParams { bps, floor, cap, account_ix: ix }))
}

fn encode_gen(cl: bool, amount_in: u64, min_profit: u64, guard: Option<u64>, tip: Option<TipParams>, legs: &[LegGen]) -> Vec<u8> {
    let specs: Vec<LegSpec> = legs.iter().map(|l| LegSpec { n_accounts: l.n, flags: l.flags, amount_offset: l.off, data: &l.data }).collect();
    encode_v3(if cl { COUNT_LAMPORTS } else { 0 }, amount_in, min_profit, guard, tip, &specs)
}

proptest! {
    #![proptest_config(ProptestConfig { cases: 4_000, ..ProptestConfig::default() })]

    /// Arbitrary bytes never panic the parser, for any version byte, and whatever parses satisfies the invariants
    /// (including canonical re-encoding).
    #[test]
    fn prop_parser_never_panics(mut data in vec(any::<u8>(), 0..700), v in 0u8..6, n in 0u8..10) {
        if !data.is_empty() { data[0] = v; }
        if data.len() > 2 { data[if v == V3 { 2 } else { 1 }] = n; }
        if let Ok(r) = parse(&data) { assert_route_invariants(&r, &data); }
    }

    /// v3: every valid route round-trips: encode -> parse -> the same fields -> re-encode -> the same bytes.
    #[test]
    fn prop_v3_round_trip(legs in vec(leg_gen(7), 1..=8), cl in any::<bool>(), amount_in in any::<u64>(), min_profit in 1u64.., guard in proptest::option::of(any::<u64>()), tip in proptest::option::of(tip_gen())) {
        let data = encode_gen(cl, amount_in, min_profit, guard, tip, &legs);
        let flags: Vec<u8> = legs.iter().map(|l| l.flags).collect();
        let native = flags.iter().any(|f| f & (LEG_NATIVE_IN | LEG_NATIVE_OUT) != 0);
        let accounts = 2 + legs.iter().map(|l| 2 + l.n as usize).sum::<usize>() + if tip.is_some() { 2 } else { 0 };
        let r = parse(&data);
        // the oracle: valid iff the guard is present (REVIEW #2), a tip comes with COUNT_LAMPORTS (#4), every leg's
        // flags are valid (#6, #14), the chain agrees, native legs come with COUNT_LAMPORTS, and it fits 255 accounts
        let valid = guard.is_some() && (tip.is_none() || cl) && flags.iter().all(|f| leg_flags_ok(*f))
            && chain_ok(&flags) && (!native || cl) && accounts <= MAX_IX_ACCOUNTS;
        prop_assert_eq!(r.is_ok(), valid, "{:?}", r);
        if let Ok(r) = r {
            assert_route_invariants(&r, &data);
            prop_assert_eq!(r.layout, V3);
            prop_assert_eq!((r.amount_in, r.min_profit, r.max_payer_lamport_drop, r.tip), (amount_in, min_profit, guard, tip));
            prop_assert_eq!(r.n_legs, legs.len());
            for (l, g) in r.legs().iter().zip(&legs) {
                prop_assert_eq!((l.n_accounts, l.flags(), l.amount_offset), (g.n as usize, g.flags, g.off as usize));
                prop_assert_eq!(&data[l.data_start..l.data_start + l.data_len], &g.data[..]);
            }
        }
    }

    /// v3: any truncation or extension of a valid encoding is refused.
    #[test]
    fn prop_v3_length_changes_are_refused(legs in vec((1u8..=28, 0u8..=48).prop_flat_map(|(n, off)| vec(any::<u8>(), (off as usize + 8)..=(off as usize + 72)).prop_map(move |data| LegGen { n, flags: 0, off, data })), 1..=8), guard in any::<u64>(), tip in proptest::option::of(tip_gen()), cut in 1usize..200, extra in vec(any::<u8>(), 1..20)) {
        let data = encode_gen(true, 1, 1, Some(guard), tip, &legs);
        prop_assert!(parse(&data).is_ok());
        let cut = cut.min(data.len());
        prop_assert!(parse(&data[..data.len() - cut]).is_err());
        let mut longer = data.clone();
        longer.extend(extra);
        prop_assert!(parse(&longer).is_err());
    }

    /// v2: arbx-exec's parser is indistinguishable from nexus-arb-v2's verbatim parser on arbitrary input
    /// (same fields when Ok, same error variant and fields when Err).
    #[test]
    fn prop_v2_parse_matches_nexus_arb_v2(mut data in vec(any::<u8>(), 0..400), n in 0u8..10) {
        if !data.is_empty() { data[0] = V2; }
        if data.len() > 1 { data[1] = n; }
        let ours = parse(&data);
        prop_assert_eq!(project_new(&ours), project_ref(&v2ref::parse(&data)));
        if let Ok(r) = ours { assert_route_invariants(&r, &data); }
    }

    /// v2: valid encodings (with or without the trailer, native flags included) also agree, and mutations of them.
    #[test]
    fn prop_v2_valid_and_mutated_match_nexus_arb_v2(
        legs in vec((0u8..=255, 0u8..40, 8usize..60), 1..=8), guard in proptest::option::of(any::<u64>()),
        flips in vec((any::<prop::sample::Index>(), any::<u8>()), 0..4))
    {
        let datas: Vec<Vec<u8>> = legs.iter().map(|(_, off, len)| vec![0xC3; (*off as usize).max(*len - 8) + 8]).collect();
        let specs: Vec<(u8, u8, &[u8])> = legs.iter().zip(&datas).map(|((b, off, _), d)| (*b, *off, d.as_slice())).collect();
        let mut data = match guard { Some(g) => encode_guarded(7, 9, &specs, g), None => encode(7, 9, &specs) };
        for (ix, b) in flips { let i = ix.index(data.len()); data[i] = b; }
        let ours = parse(&data);
        if data[0] == V3 {
            // a flip of the version byte to 3 makes it a v3 route: outside nexus-arb-v2's domain (it says BadVersion)
            prop_assert_eq!(project_ref(&v2ref::parse(&data)), "err BadVersion(3)".to_string());
        } else {
            prop_assert_eq!(project_new(&ours), project_ref(&v2ref::parse(&data)));
        }
        if let Ok(r) = ours { assert_route_invariants(&r, &data); }
    }

    /// Guard maths against an independent u128/sign model.
    #[test]
    fn prop_guard_model(q0 in any::<u64>(), q1 in any::<u64>(), l0 in any::<u64>(), l1 in any::<u64>(), cl in any::<bool>(), min_profit in 1u64.., tip in proptest::option::of(tip_gen())) {
        let g = gain(q0, q1, l0, l1, cl);
        // model: sums first, then one subtraction
        let (pos, neg) = if cl { (q1 as i128 + l1 as i128, q0 as i128 + l0 as i128) } else { (q1 as i128, q0 as i128) };
        prop_assert_eq!(g, pos - neg);
        let t = tip.map_or(0, |p| cpi_tip(g, &p));
        if let Some(p) = tip {
            prop_assert!(t >= p.floor.min(p.cap) && t <= p.cap);
            let share = if g > 0 { (g as u128 * p.bps as u128 / 10_000) as i128 } else { 0 };
            prop_assert_eq!(t as i128, share.clamp(p.floor as i128, p.cap as i128));
        }
        let passes = check_guard(g, min_profit, t).is_ok();
        prop_assert_eq!(passes, g - t as i128 >= min_profit as i128);
        if passes {
            // the route never pays more tip than it gained, and keeps at least min_profit
            prop_assert!(g >= t as i128 + 1);
            // monotone: one more unit of gain never turns a pass into a fail (tip grows by at most bps/10_000 <= 1)
            let t2 = tip.map_or(0, |p| cpi_tip(g + 1, &p));
            prop_assert!(check_guard(g + 1, min_profit, t2).is_ok());
        }
    }

    /// The payer guard against a u128 model.
    #[test]
    fn prop_payer_guard_model(before in any::<u64>(), after in any::<u64>(), max_drop in any::<u64>(), tip in any::<u64>()) {
        let s = |l| PayerState { lamports: l, owner: [3u8; 32], data_len: 0 };
        let ok = check_payer_guard(&s(before), &s(after), max_drop, tip).is_ok();
        let drop = before as i128 - after as i128;
        prop_assert_eq!(ok, drop <= max_drop as i128 + tip as i128);
    }

    /// Log records round-trip for every value.
    #[test]
    fn prop_log_records_round_trip(leg in 0u8..8, venue in 0u8..12, flags in 0u8..4, input in any::<u64>(), delivered in any::<u64>(),
        gain in any::<i128>(), qd in any::<i128>(), ld in any::<i128>(), result in any::<u32>(), cu in any::<u64>())
    {
        let l = LegLog { leg, venue, flags, input, delivered };
        prop_assert_eq!(decode_leg_log(&leg_log(&l)), Some(l));
        let s = Summary { layout: 3, flags: 7, n_legs: leg + 1, result, amount_in: input, min_profit: delivered, tip: cu, gain, quote_delta: qd, lamport_delta: ld, cu_remaining: cu };
        prop_assert_eq!(decode_summary(&summary_log(&s)), Some(s));
    }
}

/// A deterministic mutation fuzzer: 400k byte-level mutations (flip, set, insert, delete, truncate) of valid v2 and
/// v3 encodings. Nothing panics, everything that parses satisfies the invariants and re-encodes canonically, and
/// every v2-tagged input agrees with nexus-arb-v2's parser.
#[test]
fn fuzz_mutated_encodings() {
    let mut s: u64 = 0x9E37_79B9_7F4A_7C15;
    let mut rnd = move || { s ^= s << 13; s ^= s >> 7; s ^= s << 17; s };
    let d40 = [0x5Au8; 40];
    let seeds: Vec<Vec<u8>> = vec![
        unhex(FIXTURE_HEX), unhex(GUARDED_FIXTURE_HEX), unhex(V3_FIXTURE_HEX),
        encode_v3(COUNT_LAMPORTS, 3, 4, Some(0), Some(TIP), &[spec(18, LEG_NATIVE_IN, &d40), spec(9, LEG_NATIVE_OUT, &D24), spec(200, LEG_NATIVE_IN, &d40), spec(1, 0, &D24)]),
        encode_v3(0, 3, 4, Some(0), None, &[spec(251, LEG_AUTH_RO, &d40)]),
        encode(1, 1, &[(NATIVE_IN | 18, 8, &d40), (NATIVE_OUT | 5, 8, &D24)]),
    ];
    let (mut ok, mut v2_checked) = (0u32, 0u32);
    for i in 0..400_000u32 {
        let mut d = seeds[i as usize % seeds.len()].clone();
        for _ in 0..(1 + rnd() % 3) {
            let r = rnd();
            let pos = if d.is_empty() { 0 } else { (r >> 8) as usize % d.len() };
            match r % 5 {
                0 if !d.is_empty() => d[pos] ^= 1 << ((r >> 40) % 8),
                1 if !d.is_empty() => d[pos] = (r >> 32) as u8,
                2 => d.insert(pos.min(d.len()), (r >> 24) as u8),
                3 if !d.is_empty() => { d.remove(pos); }
                _ => d.truncate(pos),
            }
        }
        match parse(&d) {
            Ok(r) => { ok += 1; assert_route_invariants(&r, &d); }
            Err(e) => { let _ = error_code(&e); }
        }
        if d.first() == Some(&V2) {
            v2_checked += 1;
            assert_eq!(project_new(&parse(&d)), project_ref(&v2ref::parse(&d)), "input {}", hex(&d));
        }
    }
    assert!(ok > 1_000 && v2_checked > 10_000, "the fuzzer must reach both outcomes: ok {ok}, v2 {v2_checked}");
}

// =================================================================================================================
// Golden vectors shared with the engine (src/build.rs asserts the same files): one source for both sides
// =================================================================================================================

fn golden(name: &str) -> Vec<u8> {
    let path = format!("{}/tests/fixtures/golden/{name}", env!("CARGO_MANIFEST_DIR"));
    unhex(std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}")).trim())
}

/// The pinned constants above are the annotated copies of tests/fixtures/golden/*.hex; the engine's builder tests read
/// the files. A fourth vector pins the v3 leg flags (NATIVE_IN on leg 0, AUTH_RO on a 70-account leg 1).
#[test]
fn golden_vector_files_match_the_pinned_encodings() {
    assert_eq!(golden("v2_route.hex"), unhex(FIXTURE_HEX));
    assert_eq!(golden("v2_route_guarded.hex"), unhex(GUARDED_FIXTURE_HEX));
    assert_eq!(golden("v3_route.hex"), unhex(V3_FIXTURE_HEX));
    let flags = encode_v3(COUNT_LAMPORTS, 0x0102_0304_0506_0708, 0x1112_1314_1516_1718, Some(0x2122_2324_2526_2728), None,
        &[spec(18, LEG_NATIVE_IN, &[0xCC; 24]), spec(70, LEG_AUTH_RO, &[0xDD; 28])]);
    assert_eq!(golden("v3_route_leg_flags.hex"), flags);
    let r = parse(&flags).unwrap();
    assert_eq!((r.flags, r.legs()[0].flags(), r.legs()[1].flags()), (PAYER_GUARD | COUNT_LAMPORTS, LEG_NATIVE_IN, LEG_AUTH_RO));
    assert_eq!(r.required_accounts(), 2 + (2 + 18) + (2 + 70));
}

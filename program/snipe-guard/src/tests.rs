//! Host tests (`cargo test` in program/snipe-guard): AUTH first, the checks and their codes, the allowlist data ops, the private
//! code scramble (round trip, never 0, distinct, not small), golden bytes (the engine asserts the same hex), a mutation fuzzer.
use super::client::*;
use super::logic::*;

fn k(b: u8) -> [u8; 32] { [b; 32] }
const AMS: &str = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR";
const FRA: &str = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE";
const FRZ: &str = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS";

/// base58 (no crate on the host side of the program)
fn b58(k: &[u8]) -> String {
    const A: &[u8] = b"123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz";
    let mut digits: Vec<u8> = vec![];
    for &b in k {
        let mut c = b as u32;
        for d in digits.iter_mut() { c += (*d as u32) << 8; *d = (c % 58) as u8; c /= 58; }
        while c > 0 { digits.push((c % 58) as u8); c /= 58; }
    }
    let mut s: String = k.iter().take_while(|b| **b == 0).map(|_| '1').collect();
    s.extend(digits.iter().rev().map(|d| A[*d as usize] as char));
    s
}

/// run ASSERT's checks after AUTH (a compiled wallet: the balance accounts are the instruction's accounts after the wallet)
fn run(g: &Guard, slot: u64, amounts: &[u64]) -> Result<[u8; 3], Fail> {
    let n = g.accounts(COMPILED[0], None).len() - 1;
    assert_checks(&g.data(), || Some(slot), |i| amounts.get(i).copied(), n)
}

#[test]
fn compiled_allowlist_is_ours() {
    assert_eq!([b58(&COMPILED[0]), b58(&COMPILED[1]), b58(&COMPILED[2])], [AMS, FRA, FRZ]);
    assert_eq!(b58(&LOADER_V3), "BPFLoaderUpgradeab1e11111111111111111111111");
    assert_eq!(b58(&TOKEN), "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA");
    assert_eq!(b58(&TOKEN_2022), "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb");
    assert_eq!(AL_LEN, 546);
}

#[test]
fn auth_runs_first_and_alone() {
    let ok_list = || -> Result<bool, u8> { panic!("the list must not be read for a compiled wallet") };
    for w in COMPILED { assert_eq!(auth(3, true, &w, ok_list), Ok(2)); }
    // not a signer: refused before anything else (the list is not read either)
    assert_eq!(auth(3, false, &COMPILED[0], ok_list), Err(Fail::new(K_AUTH, A_NOT_SIGNER)));
    assert_eq!(auth(0, true, &COMPILED[0], ok_list), Err(Fail::new(K_AUTH, A_NO_ACCOUNTS)));
    // another signer: needs the list (last account)
    assert_eq!(auth(1, true, &k(9), || Ok(true)), Err(Fail::new(K_AUTH, A_NO_LIST)));
    assert_eq!(auth(3, true, &k(9), || Ok(true)), Ok(1));
    assert_eq!(auth(3, true, &k(9), || Ok(false)), Err(Fail::new(K_AUTH, A_NOT_LISTED)));
    assert_eq!(auth(3, true, &k(9), || Err(A_LIST_OWNER)), Err(Fail::new(K_AUTH, A_LIST_OWNER)));
    // the list account itself
    let mut l = vec![0u8; AL_LEN];
    al_init(&mut l, &k(1), 254).unwrap();
    al_edit(&mut l, OP_AL_ADD, &k(1), &k(9)).unwrap();
    assert_eq!(list_check(true, &l, |b| b == 254, &k(9)), Ok(true));
    assert_eq!(list_check(true, &l, |b| b == 254, &k(8)), Ok(false));
    assert_eq!(list_check(false, &l, |_| true, &k(9)), Err(A_LIST_OWNER), "a look-alike owned by someone else");
    assert_eq!(list_check(true, &l, |b| b == 253, &k(9)), Err(A_LIST_ADDR), "right owner, wrong seeds / address");
    assert_eq!(list_check(true, &l[..AL_LEN - 1], |_| true, &k(9)), Err(A_LIST_LEN));
}

#[test]
fn allowlist_edits() {
    let (admin, other) = (k(1), k(2));
    let mut l = vec![0u8; AL_LEN];
    assert_eq!(al_init(&mut l, &[0u8; 32], 7), Err(M_ZERO));
    al_init(&mut l, &admin, 7).unwrap();
    assert_eq!(al_init(&mut l, &admin, 7), Err(M_LIST_STATE), "init only once");
    for i in 0..AL_MAX as u8 { al_edit(&mut l, OP_AL_ADD, &admin, &k(100 + i)).unwrap(); }
    assert_eq!(al_edit(&mut l, OP_AL_ADD, &admin, &k(99)), Err(M_FULL));
    assert_eq!(al_edit(&mut l, OP_AL_ADD, &admin, &k(100)), Err(M_PRESENT));
    assert_eq!(al_edit(&mut l, OP_AL_ADD, &other, &k(99)), Err(M_NOT_ADMIN), "not the admin");
    assert_eq!(al_edit(&mut l, OP_AL_REMOVE, &other, &k(100)), Err(M_NOT_ADMIN));
    al_edit(&mut l, OP_AL_REMOVE, &admin, &k(103)).unwrap();
    assert!(!al_contains(&l, &k(103)) && al_contains(&l, &k(115)) && al_contains(&l, &k(100)));
    assert_eq!(al_edit(&mut l, OP_AL_REMOVE, &admin, &k(103)), Err(M_ABSENT));
    let (a, b, ws) = al_read(&l).unwrap();
    assert_eq!((a, b, ws.len()), (admin, 7, AL_MAX - 1));
    assert_eq!(&l[34 + 32 * (AL_MAX - 1)..], &[0u8; 32], "the freed slot is zeroed");
    // rotate the admin: the old one can no longer edit
    al_edit(&mut l, OP_AL_ADMIN, &admin, &other).unwrap();
    assert_eq!(al_edit(&mut l, OP_AL_ADD, &admin, &k(99)), Err(M_NOT_ADMIN));
    al_edit(&mut l, OP_AL_ADD, &other, &k(99)).unwrap();
    assert_eq!(al_edit(&mut l, OP_AL_ADD, &other, &[0u8; 32]), Err(M_ZERO));
    // a list whose count byte lies is clamped (never read past the end)
    let mut bad = l.clone(); bad[33] = 255;
    assert!(!al_contains(&bad, &k(250)));
}

#[test]
fn deadline_with_late_bucket() {
    let g = Guard { deadline: Some(100), ..Default::default() };
    assert_eq!(g.data(), [&[OP_ASSERT, F_DEADLINE][..], &100u64.to_le_bytes()].concat());
    assert!(run(&g, 100, &[]).is_ok());
    for (slot, gap) in [(101, 1), (102, 2), (104, 3), (108, 4), (116, 5), (164, 6), (165, 7)] {
        assert_eq!(run(&g, slot, &[]), Err(Fail { kind: K_DEADLINE, idx: 0, cnt: 0, gap }), "slot {slot}");
    }
    assert_eq!(assert_checks(&g.data(), || None, |_| None, 0), Err(Fail::new(K_ACCTS, X_CLOCK)), "no clock: refused, never passed blind");
}

#[test]
fn curve_band_buckets() {
    let g = Guard { curve: Some((k(1), 850_000_000_000_000, 950_000_000_000_000)), ..Default::default() };
    assert!(run(&g, 0, &[850_000_000_000_000]).is_ok() && run(&g, 0, &[950_000_000_000_000]).is_ok());
    assert_eq!(run(&g, 0, &[849_999_000_000_000]).unwrap_err().kind, K_CURVE_HIGH);
    assert_eq!(run(&g, 0, &[800_000_000_000_000]), Err(Fail { kind: K_CURVE_HIGH, idx: 0, cnt: 0, gap: 5 }), "5.9% short");
    assert_eq!(run(&g, 0, &[1_000_000_000_000_000]), Err(Fail { kind: K_CURVE_DEEP, idx: 0, cnt: 0, gap: 5 }), "5.26% deeper than the band");
    let bad = Guard { curve: Some((k(1), 2, 1)), ..Default::default() };
    assert_eq!(run(&bad, 0, &[1]), Err(Fail::new(K_DATA, D_BAND)));
}

#[test]
fn floors_report_worst_holder_count_and_gap() {
    let m = UNIT * 1_000_000;
    // six holders signed at 40/30/20/15/12/10 M tokens; floors at 90%; ONE may leave (G-A: 6:0.9:1)
    let floors: Vec<([u8; 32], u32)> = [36, 27, 18, 13, 10, 9].iter().enumerate().map(|(i, f)| (k(10 + i as u8), f * 1_000_000)).collect();
    let g = Guard { floors, max_viol: 1, ..Default::default() };
    let full = [40 * m, 30 * m, 20 * m, 15 * m, 12 * m, 10 * m];
    let e = run(&g, 0, &full).unwrap();
    assert_eq!(e, [F_FLOORS, 6, 2], "6 floors, 0 below, tightest margin 111% (40/36, 30/27, 20/18, 10/9) -> bucket 2");
    let mut a = full; a[0] = 0;
    assert_eq!(run(&g, 0, &a).unwrap()[1], 6 | 1 << 4, "one leaver tolerated, echo says so");
    let mut a = full; a[0] = 0; a[3] = 12 * m; // holder 3 at 12/13 = 92% of its floor
    assert_eq!(run(&g, 0, &a), Err(Fail { kind: K_FLOORS, idx: 0, cnt: 2, gap: 0 }), "worst = holder 0, sold out");
    let mut a = full; a[2] = 9 * m; a[5] = 8 * m; // 9/18 = 50%, 8/9 = 88%
    assert_eq!(run(&g, 0, &a), Err(Fail { kind: K_FLOORS, idx: 2, cnt: 2, gap: 3 }), "worst = holder 2 at 50%");
    let mut a = full; a[4] = 1 * m; a[1] = 26 * m;
    assert_eq!(run(&g, 0, &a), Err(Fail { kind: K_FLOORS, idx: 4, cnt: 2, gap: 1 }), "1/10 = 10% -> <25%");
    assert_eq!(run(&g, 0, &full[..5]), Err(Fail::new(K_ACCTS, X_COUNT)), "an account short");
    let off = Guard { max_viol: 6, ..g.clone() };
    assert_eq!(run(&off, 0, &full), Err(Fail::new(K_DATA, D_VIOL)), "a check that cannot fail is refused");
    let big = Guard { floors: (0..13).map(|i| (k(i), 1)).collect(), ..Default::default() };
    assert_eq!(run(&big, 0, &[m; 13]), Err(Fail::new(K_DATA, D_N)));
}

#[test]
fn data_refusals() {
    assert_eq!(assert_checks(&[OP_ASSERT, 0x08], || Some(0), |_| None, 0), Err(Fail::new(K_DATA, D_FLAGS)), "unknown flag");
    assert_eq!(assert_checks(&[OP_ASSERT, 0], || Some(0), |_| None, 0), Err(Fail::new(K_DATA, D_FLAGS)), "no check");
    assert_eq!(assert_checks(&[OP_ASSERT, F_ECHO], || Some(0), |_| None, 0), Err(Fail::new(K_DATA, D_FLAGS)), "echo alone");
    assert_eq!(assert_checks(&[OP_ASSERT], || Some(0), |_| None, 0), Err(Fail::new(K_DATA, D_SHORT)));
    assert_eq!(assert_checks(&[OP_ASSERT, F_DEADLINE, 1, 2], || Some(0), |_| None, 0), Err(Fail::new(K_DATA, D_SHORT)));
    let mut d = Guard { deadline: Some(5), ..Default::default() }.data(); d.push(0);
    assert_eq!(assert_checks(&d, || Some(0), |_| None, 0), Err(Fail::new(K_DATA, D_TRAILING)));
    let d = Guard { deadline: Some(5), ..Default::default() }.data();
    assert_eq!(assert_checks(&d, || Some(0), |_| Some(0), 1), Err(Fail::new(K_ACCTS, X_COUNT)), "an extra account");
}

#[test]
fn codes_roundtrip_opaque_distinct() {
    let mut seen = std::collections::HashSet::new();
    let mut small = 0;
    for kind in K_AUTH..=K_ADMIN { for idx in 0..16u8 { for cnt in 0..16u8 { for gap in 0..16u8 {
        let f = Fail { kind, idx, cnt, gap };
        let c = code(f);
        assert_ne!(c, 0, "a code of 0 is success");
        assert!(seen.insert(c), "duplicate code {c:#x}");
        assert_eq!(decode(c), Some(f), "{c:#x}");
        if c < 0x1_0000 { small += 1; }
    } } } }
    // the codes do not look like an enum (0, 1, 2 ...): almost none is a small number
    assert!(small < 8, "{small} codes below 0x10000");
    // consecutive kinds / holders do not give consecutive codes
    let (a, b) = (code(Fail::new(K_DEADLINE, 0)), code(Fail::new(K_CURVE_HIGH, 0)));
    assert!(a.abs_diff(b) > 1_000, "{a:#x} {b:#x}");
    // foreign codes (pump's 6042 = 0x179a, Anchor, Lighthouse's 0x1771...) mostly do not decode
    let foreign = (0u32..200_000).filter(|c| decode(*c).is_some()).count();
    assert!(foreign < 100, "{foreign} of 200k small codes decode");
    assert_eq!(decode(0x179a), None);
    assert_eq!(decode(0x1771), None);
    // the names the engine logs
    assert_eq!(kind_name(K_FLOORS), "floors");
    assert_eq!(sub_name(K_AUTH, A_NOT_SIGNER), Some("not_signer"));
    assert_eq!(gap_text(K_DEADLINE, 3), "3-4 slots");
    println!("deadline 1 slot late = {:#010x}, floors idx 2 cnt 2 gap 3 = {:#010x}, auth not signer = {:#010x}",
        code(Fail { kind: K_DEADLINE, idx: 0, cnt: 0, gap: 1 }), code(Fail { kind: K_FLOORS, idx: 2, cnt: 2, gap: 3 }), code(Fail::new(K_AUTH, A_NOT_SIGNER)));
}

/// golden: the engine's builder (src/bin/snipe_engine/ps43_guard.rs) must produce exactly these bytes (it asserts the same hex)
#[test]
fn golden_bytes() {
    let g = Guard { deadline: Some(467_582_218), ..Default::default() };
    let hex = |d: &[u8]| d.iter().map(|b| format!("{b:02x}")).collect::<String>();
    assert_eq!(hex(&g.data()), "54010abdde1b00000000");
    let g = Guard { deadline: Some(467_582_218), floors: vec![(k(2), 36_000_000), (k(3), 27_000_000), (k(4), 9_000)], max_viol: 1, ..Default::default() };
    assert_eq!(hex(&g.data()), "54050abdde1b000000000301" .to_owned() + "00512502" + "c0fc9b01" + "28230000");
    let g = Guard { deadline: Some(1), curve: Some((k(1), 2, 3)), floors: vec![(k(2), 5)], max_viol: 0, echo: true };
    assert_eq!(hex(&g.data()), "5487".to_owned() + "0100000000000000" + "0200000000000000" + "0300000000000000" + "0100" + "05000000");
    assert_eq!(g.accounts(COMPILED[0], Some(k(7))), vec![(COMPILED[0], true, false), (k(1), false, false), (k(2), false, false)], "compiled: no list");
    assert_eq!(g.accounts(k(9), Some(k(7))).last(), Some(&(k(7), false, false)), "listed wallet: the list last");
    assert_eq!(al_init_data(254, k(1), 5).len(), 42);
    assert_eq!(al_edit_data(OP_AL_ADD, k(1)).len(), 33);
}

/// mutation fuzz: random edits of valid instructions never panic and never pass with a bad shape
#[test]
fn fuzz_never_panics() {
    let base = Guard { deadline: Some(5), curve: Some((k(1), 10, 20)), floors: vec![(k(2), 1), (k(3), 1)], max_viol: 1, echo: true }.data();
    let mut s = 0x9E37_79B9_7F4A_7C15u64;
    let mut rnd = move || { s ^= s << 13; s ^= s >> 7; s ^= s << 17; s };
    let (mut ok, mut err) = (0u32, 0u32);
    for _ in 0..300_000 {
        let mut d = base.clone();
        for _ in 0..(rnd() % 4) {
            match rnd() % 4 {
                0 => { if !d.is_empty() { let i = (rnd() as usize) % d.len(); d[i] = rnd() as u8; } }
                1 => { let n = (rnd() as usize) % (d.len() + 1); d.truncate(n); }
                2 => d.push(rnd() as u8),
                _ => { if !d.is_empty() { let i = (rnd() as usize) % d.len(); d[i] ^= 1 << (rnd() % 8); } }
            }
        }
        let good = [15u64, 2_000_000, 2_000_000];
        let n_bal = if rnd() % 4 != 0 { 3 } else { (rnd() % 8) as usize };
        match assert_checks(&d, || Some(d.len() as u64 % 7), |i| (i < n_bal).then(|| good.get(i).copied().unwrap_or(0)), n_bal) {
            Ok(_) => ok += 1,
            Err(f) => { err += 1; assert!(decode(code(f)) == Some(f)); }
        }
        // the list ops never panic on any data either
        let mut l = d.clone(); l.resize(AL_LEN, rnd() as u8);
        let _ = al_edit(&mut l, [OP_AL_ADD, OP_AL_REMOVE, OP_AL_ADMIN, 0][(rnd() % 4) as usize], &k(1), &k(2));
        let _ = al_contains(&l, &k(2));
        let _ = programdata_authority(&d);
    }
    assert!(ok > 100 && err > 100_000, "ok {ok} err {err}");
}

// ===================================================================================================================
// dip43 C2 tests (ps43_guard.rs): the snipe-guard program on the pre-send tries. OFF (the default): the sender's try is dip42's byte
// for byte (pinned sha256 of a sample signed try); the flags and their refusals; deadline / holders tries <= 1,232 bytes with the
// largest tip / loaded-data-limit shapes, floors dropped from the tail; the CU budget; a missing / stale snapshot signs the deadline
// only; G-A semantics (6:0.9:1 = abort when MORE THAN 1 holder is below) checked against the program's own logic; every abort code
// decoded into guard_abort; the A/B parity; the golden instruction bytes shared with program/snipe-guard's tests.
// ===================================================================================================================
use super::*;
use super::ps43_guard::*;
use snipe_guard::logic as sgl;

const S: u64 = 1_000_000_000;
const PROG: &str = "75hbt6uvDqjPZ9WgFtMhBnTeyHw7cinoHiz4FD2vEz2d"; // [0x5A; 32]

fn args(extra: &[&str]) -> Vec<String> {
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "100",
        "--presend-live-fee-budget-sol", "0.1", "--presend-live-size-sol", "0.4"].iter().map(|s| s.to_string()).collect();
    a.extend(extra.iter().map(|s| s.to_string()));
    // holders mode needs the true-balance book (the merge's start check)
    if extra.contains(&"holders") { a.extend(["--presend-live-tbal", "on", "--presend-live-fam-log"].iter().map(|s| s.to_string())); }
    a
}
fn cfg(extra: &[&str]) -> Result<Option<Cfg>> { Cfg::from_argv(&args(extra), &arbx::presend::Params::default(), true, 1_000_000_000) }
fn prog() -> Pk { pk(PROG) }
fn g43(extra: &[&str]) -> G43 {
    let mut v = vec!["--presend-live-guard-program", PROG];
    v.extend_from_slice(extra);
    cfg(&v).unwrap().unwrap().g43.unwrap()
}
fn ams() -> Pk { pk("EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR") }
fn helius() -> Vec<Pk> { send::known_tip_accounts(config::SendKind::Helius).iter().map(|a| pk(a)).collect() }
fn launch() -> Launch { snipe_build::launch_from_target(pk("7oeUduY1zhUwQ3YdSP9CGDYF8nYzfRdhgqtc6wAbpump"), pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q")) }
fn swin(id: u64, h: HSet) -> SWin {
    let l = launch();
    SWin { id, mint: l.mint, launch: l, st_ns: 0, stop_ns: u64::MAX, en_slot: 10, vsol: 40 * S, vtok: 800_000_000_000_000, fr: 0.0125, pos: (1, 0, 0),
        pace: pl::Pace::new(0, 4, 400_000_000), n: 0, done: false, spend: 400_000_000, rearm: false, ob6: 0.0, grd: Grd::default(), fpg: None, fab: None, blk: None, bd: None, g43: h }
}
const LH: GuardEnc = GuardEnc { disc: 15, op: 4, acct: true };
const BH: [u8; 32] = [9u8; 32];
const DEADLINE: u64 = 461_000_123;

/// the sender's try for window `w` through ps43_guard::try_ixs, with dip42's body (attempt_ixs at the fee values, + the loaded-data limit `ll`)
fn sender_try(g: Option<&G43>, w: &SWin, user: Pk, tip: Option<(Pk, u64)>, ll: Option<u32>, now: u64) -> GTry {
    try_ixs(g, w.id, &w.g43, now, user, DEADLINE, BH, |d| guard_ix_enc(LH, d), |gix| {
        let (mut ixs, roles) = att_ixs_fee(user, w, 1_234_567, CU_DEFAULT as u32, 1_000, gix, tip);
        speed16::add_ll(&mut ixs, ll);
        (ixs, roles)
    })
}
fn signed(user_key: &SigningKey, ixs: &[build::Ix]) -> Vec<u8> {
    build::sign(&build::compile_v0(user_key.verifying_key().to_bytes(), ixs, BH, &[], &[]).unwrap(), user_key)
}
fn sha(b: &[u8]) -> String { use sha2::Digest; sha2::Sha256::digest(b).iter().map(|x| format!("{x:02x}")).collect() }

/// a snapshot of `n` holders at 4.0%, 3.5%, ... of supply (+ ours, + a dust holder), fresh
fn snap(n: usize, age: Option<u64>) -> Snap {
    let mut h: Vec<(Pk, u64)> = (0..n).map(|i| ([0x40 + i as u8; 32], (40 - 5 * i as u64).max(11) * 1_000_000_000_000)).collect();
    h.push((ams(), 90_000_000_000_000));
    h.push(([0x3F; 32], 9_000_000_000_000)); // 0.9%: below MINPCT 1.0
    Snap { holders: h, age_ms: age, accts: vec![] }
}

#[test]
fn dip43_guard_off_is_dip42_bytes() {
    // no guard flag: the parsed config carries no guard
    let c = cfg(&[]).unwrap().unwrap();
    assert!(c.g43.is_none());
    assert!(cfg(&["--presend-live-guard", "off"]).unwrap().unwrap().g43.is_none());
    let key = SigningKey::from_bytes(&[7u8; 32]);
    let user = key.verifying_key().to_bytes();
    let w = swin(7, HSet::default());
    for (tip, ll) in [(Some((helius()[3], 200_000)), None), (Some((helius()[0], 1_000_000)), Some(13_631_488u32)), (None, None)] {
        // dip42: exactly the expression the dip42 sender ran
        let (mut ref_ixs, ref_roles) = att_ixs_fee(user, &w, 1_234_567, CU_DEFAULT as u32, 1_000, guard_ix_enc(LH, DEADLINE), tip);
        speed16::add_ll(&mut ref_ixs, ll);
        let want = signed(&key, &ref_ixs);
        // dip43 off: the sender's builder
        let gt = sender_try(None, &w, user, tip, ll, 0);
        assert!(!gt.used && gt.nf == 0 && gt.dropped == 0);
        assert_eq!(gt.roles, ref_roles);
        assert_eq!(signed(&key, &gt.ixs), want, "guard off: the try must be dip42's byte for byte");
        // the A/B's Lighthouse arm (even windows) is dip42's too
        let g = g43(&["--presend-live-guard", "deadline", "--presend-live-guard-ab", "on"]);
        let gl = sender_try(Some(&g), &swin(8, HSet::default()), user, tip, ll, 0);
        assert!(!gl.used);
        assert_eq!(signed(&key, &gl.ixs), signed(&key, &{ let (mut x, _) = att_ixs_fee(user, &swin(8, HSet::default()), 1_234_567, CU_DEFAULT as u32, 1_000, guard_ix_enc(LH, DEADLINE), tip); speed16::add_ll(&mut x, ll); x }));
    }
    // the sample try pinned (sha256 of the signed bytes; computed on dip42 = sniper/main f2d41b0f's attempt_ixs): a change to the off
    // path, attempt_ixs or the Lighthouse encoding shows here
    let gt = sender_try(None, &w, user, Some((helius()[3], 200_000)), None, 0);
    let raw = signed(&key, &gt.ixs);
    assert_eq!(raw.len(), DIP42_SAMPLE_LEN);
    assert_eq!(sha(&raw), DIP42_SAMPLE_SHA256);
    assert_eq!(gt.ixs[2].program, pk("L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"));
}
/// the dip42 sample try (Lighthouse disc 15 op 4 acct, deadline 461000123, tip 200000 to Helius tip account 3, blockhash 0x09.., key 0x07..)
const DIP42_SAMPLE_LEN: usize = 894;
const DIP42_SAMPLE_SHA256: &str = "a24570a97403289b076d31dcd6cf049356d99a1a0199a234d83bca34fa404e75";

#[test]
fn dip43_guard_flags() {
    let g = g43(&["--presend-live-guard", "deadline"]);
    assert_eq!((g.mode, g.program, g.n, g.theta, g.max_leavers, g.min_pct, g.ab, g.allowlist, g.max_age_ms), (Mode::Deadline, prog(), 6, 0.9, 1, 1.0, false, None, 2_000));
    let h = g43(&["--presend-live-guard", "holders", "--presend-live-guard-holders", "8:0.8:2:0.5", "--presend-live-guard-ab", "on", "--presend-live-guard-max-age-ms", "1500",
        "--presend-live-guard-allowlist", PROG]);
    assert_eq!((h.mode, h.n, h.theta, h.max_leavers, h.min_pct, h.ab, h.allowlist, h.max_age_ms), (Mode::Holders, 8, 0.8, 2, 0.5, true, Some(prog()), 1_500));
    for (a, e) in [
        (&["--presend-live-guard", "deadline"][..], "needs --presend-live-guard-program"),
        (&["--presend-live-guard", "on", "--presend-live-guard-program", PROG][..], "off | deadline | holders"),
        (&["--presend-live-guard-program", PROG][..], "needs --presend-live-guard deadline | holders"),
        (&["--presend-live-guard", "off", "--presend-live-guard-ab", "on"][..], "needs --presend-live-guard deadline | holders"),
        (&["--presend-live-guard", "deadline", "--presend-live-guard-program", "xyz0"][..], "not a base58"),
        (&["--presend-live-guard", "deadline", "--presend-live-guard-program", PROG, "--presend-live-guard-holders", "6:0.9:1:1.0"][..], "needs --presend-live-guard holders"),
        (&["--presend-live-guard", "holders", "--presend-live-guard-program", PROG, "--presend-live-guard-holders", "6:0.9:6:1.0"][..], "MAXLEAVERS must be < N"),
        (&["--presend-live-guard", "holders", "--presend-live-guard-program", PROG, "--presend-live-guard-holders", "11:0.9:1:1.0"][..], "N must be 1..10"),
        (&["--presend-live-guard", "holders", "--presend-live-guard-program", PROG, "--presend-live-guard-holders", "6:1.5:1:1.0"][..], "THETA"),
        (&["--presend-live-guard", "holders", "--presend-live-guard-program", PROG, "--presend-live-guard-holders", "6:0.9"][..], "N:THETA:MAXLEAVERS:MINPCT"),
        (&["--presend-live-guard", "holders", "--presend-live-guard-program", PROG, "--presend-live-guard-max-age-ms", "0"][..], "1..600000"),
        (&["--presend-live-guard", "holders", "--presend-live-guard-program", PROG, "--presend-live-guard-ab", "maybe"][..], "on | off"),
        (&["--presend-live-guard", "deadline", "--presend-live-guard-program", "11111111111111111111111111111111"][..], "system program"),
    ] {
        let err = cfg(a).err().map(|e| format!("{e:#}")).unwrap_or_default();
        assert!(err.contains(e), "{a:?}: {err}");
    }
    // without --presend-live every guard flag is refused
    let mut a: Vec<String> = ["snipe_engine", "--dip", "--presend-live-guard", "deadline"].iter().map(|s| s.to_string()).collect();
    assert!(Cfg::from_argv(&a, &arbx::presend::Params::default(), true, 1).err().map(|e| e.to_string()).unwrap_or_default().contains("needs --presend-live"));
    // the start-up flag check knows every flag
    a = args(&["--presend-live-guard", "holders", "--presend-live-guard-program", PROG, "--presend-live-guard-holders", "6:0.9:1:1.0", "--presend-live-guard-ab", "on",
        "--presend-live-guard-allowlist", PROG, "--presend-live-guard-max-age-ms", "2000"]);
    assert!(crate::check_flags(&a).is_ok(), "{:?}", crate::check_flags(&a));
    // the wallet check: compiled wallets need no list, another wallet needs one
    assert!(g.check_wallet(&ams()).is_ok());
    assert!(g.check_wallet(&[1u8; 32]).unwrap_err().to_string().contains("--presend-live-guard-allowlist"));
    assert!(h.check_wallet(&[1u8; 32]).is_ok());
    assert!(g.desc().starts_with("GUARD (dip43 snipe-guard) deadline"));
    assert!(h.desc().contains("abort when more than 2 of the top 8 below 80%"), "{}", h.desc());
}

#[test]
fn dip43_guard_deadline_try() {
    let g = g43(&["--presend-live-guard", "deadline"]);
    let key = SigningKey::from_bytes(&[7u8; 32]);
    let user = ams(); // compiled in: no list account
    let w = swin(3, HSet::default());
    for (tip, ll) in [(Some((helius()[3], 200_000)), None), (Some((helius()[1], 5_000_000)), Some(13_631_488u32))] {
        let gt = sender_try(Some(&g), &w, user, tip, ll, 0);
        assert!(gt.used && gt.nf == 0);
        let gi = &gt.ixs[gt.roles.guard.unwrap() as usize];
        assert_eq!(gi.program, prog());
        assert_eq!(gi.data, [&[sgl::OP_ASSERT, sgl::F_DEADLINE][..], &DEADLINE.to_le_bytes()].concat());
        assert_eq!(gi.accounts.len(), 1);
        assert!(gi.accounts[0].key == user && gi.accounts[0].signer);
        assert_eq!(gt.roles, pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: tip.map(|_| 6) }, "the layout is dip42's");
        let (mut lh, _) = att_ixs_fee(user, &w, 1_234_567, CU_DEFAULT as u32, 1_000, guard_ix_enc(LH, DEADLINE), tip);
        speed16::add_ll(&mut lh, ll);
        let (a, b) = (signed(&key, &gt.ixs).len(), signed(&key, &lh).len());
        assert!(a <= 1232 && a <= b, "snipe-guard deadline {a} bytes vs Lighthouse {b}");
        // the wallet is the fee payer: the guard adds no key (its program replaces Lighthouse's)
        let m = build::compile_v0(user, &gt.ixs, BH, &[], &[]).unwrap();
        let ml = build::compile_v0(user, &lh, BH, &[], &[]).unwrap();
        assert_eq!(m.static_keys, ml.static_keys);
        let rec = g.rec(true, &w.g43, gt.nf, gt.dropped, gi, 0);
        assert_eq!(rec, serde_json::json!({"mode": "deadline", "n_floors": 0, "ix_bytes": 14, "keys": 0}));
    }
    // a wallet not compiled in carries the allowlist account last (+1 key)
    let gl = g43(&["--presend-live-guard", "deadline", "--presend-live-guard-allowlist", "So11111111111111111111111111111111111111112"]);
    let other = SigningKey::from_bytes(&[8u8; 32]);
    let gt = sender_try(Some(&gl), &w, other.verifying_key().to_bytes(), Some((helius()[3], 200_000)), None, 0);
    let gi = &gt.ixs[2];
    assert_eq!(gi.accounts.last().unwrap().key, pk("So11111111111111111111111111111111111111112"));
    assert!(signed(&other, &gt.ixs).len() <= 1232);
    // the A/B: odd windows the guard, even windows Lighthouse
    let gab = g43(&["--presend-live-guard", "deadline", "--presend-live-guard-ab", "on"]);
    assert!(gab.uses(1) && gab.uses(3) && !gab.uses(2) && !gab.uses(4));
    assert_eq!(gab.rec(false, &w.g43, 0, 0, gi, 0), serde_json::json!({"mode": "lighthouse", "arm": "L"}));
}

#[test]
fn dip43_guard_holders_floors_size_and_semantics() {
    let g = g43(&["--presend-live-guard", "holders"]);
    let key = SigningKey::from_bytes(&[7u8; 32]);
    let user = ams();
    let mint = launch().mint;
    let now = 10_000_000_000u64;
    // a fresh snapshot: top 6 >= 1%, ours and the 0.9% holder out, floors = 90% in whole tokens, the holders' Token-2022 ATAs
    let h = g.hset(&snap(8, Some(100)), &user, &mint, now);
    assert_eq!((h.n, h.why), (6, WHY_OK));
    assert_eq!(h.f[0].2, [0x40; 32]);
    assert_eq!(h.f[0].1, 36_000_000, "40M tokens x 0.9");
    assert_eq!(h.f[0].0, arbx::pda::ata(&[0x40; 32], &mint, &arbx::pda::TOKEN_2022));
    assert!(h.f[..6].iter().all(|x| x.2 != user && x.2 != [0x3F; 32]));
    let w = swin(5, h);
    let gt = sender_try(Some(&g), &w, user, Some((helius()[3], 200_000)), None, now);
    assert_eq!((gt.nf, gt.dropped), (6, 0));
    let raw = signed(&key, &gt.ixs);
    assert!(raw.len() <= 1232, "{} bytes", raw.len());
    let gi = &gt.ixs[2];
    assert_eq!(gi.accounts.len(), 7);
    // G-A semantics on the program's own logic: 6:0.9:1 = abort when MORE THAN 1 holder is below (1 below passes, 2 abort)
    let bal = |i: usize| (40 - 5 * i as u64) * 1_000_000_000_000;
    let n_bal = gi.accounts.len() - 1;
    let ok_all = sgl::assert_checks(&gi.data, || Some(DEADLINE), |i| (i < 6).then(|| bal(i)), n_bal);
    assert!(ok_all.is_ok());
    let one = sgl::assert_checks(&gi.data, || Some(DEADLINE), |i| (i < 6).then(|| if i == 0 { 0 } else { bal(i) }), n_bal);
    assert!(one.is_ok(), "one leaver tolerated");
    let two = sgl::assert_checks(&gi.data, || Some(DEADLINE), |i| (i < 6).then(|| if i == 0 || i == 3 { bal(i) * 8 / 10 } else { bal(i) }), n_bal);
    assert_eq!(two.map_err(|f| (f.kind, f.cnt)), Err((sgl::K_FLOORS, 2)), "two leavers abort");
    let rec = g.rec(true, &w.g43, gt.nf, gt.dropped, gi, now);
    assert_eq!((rec["mode"].as_str(), rec["n_floors"].as_u64(), rec["max_viol"].as_u64(), rec["floors"].as_array().map(|a| a.len())), (Some("holders"), Some(6), Some(1), Some(6)));
    // the biggest shape: N 10 with the largest tip and the loaded-data limit: floors dropped from the tail until the try fits
    let g10 = g43(&["--presend-live-guard", "holders", "--presend-live-guard-holders", "10:0.9:1:1.0"]);
    let h10 = g10.hset(&snap(10, Some(100)), &user, &mint, now);
    assert_eq!(h10.n, 10);
    let other = SigningKey::from_bytes(&[8u8; 32]);
    let gl = G43 { allowlist: Some([0x77; 32]), ..g10.clone() };
    for (gg, k) in [(&g10, &key), (&gl, &other)] {
        let u = k.verifying_key().to_bytes();
        let gt = sender_try(Some(gg), &swin(5, h10), u, Some((helius()[1], 5_000_000)), Some(13_631_488), now);
        let n = signed(k, &gt.ixs).len();
        assert!(n <= 1232, "{n} bytes");
        assert!(gt.dropped > 0 && gt.nf < 10 && gt.nf > 1, "nf {} dropped {}", gt.nf, gt.dropped);
        // one more floor would not have fit
        let more = { let (mut x, _) = att_ixs_fee(u, &swin(5, h10), 1_234_567, CU_DEFAULT as u32, 1_000, gg.ix(u, DEADLINE, &h10, gt.nf + 1), Some((helius()[1], 5_000_000))); speed16::add_ll(&mut x, Some(13_631_488)); x };
        assert!(signed(k, &more).len() > 1232);
        let r = gg.rec(true, &h10, gt.nf, gt.dropped, &gt.ixs[2], now);
        assert_eq!(r["dropped"].as_u64(), Some(gt.dropped as u64));
        println!("N 10, biggest shape, {}: {} floors fit ({} dropped), {n} bytes", if gg.allowlist.is_some() { "listed wallet" } else { "compiled wallet" }, gt.nf, gt.dropped);
    }
    // shrink: never leaves a check that cannot fail
    assert_eq!((g.shrink(6), g.shrink(3), g.shrink(2)), (5, 2, 0));
}

#[test]
fn dip43_guard_stale_or_missing_snapshot_signs_deadline_only() {
    let g = g43(&["--presend-live-guard", "holders"]);
    let user = ams();
    let mint = launch().mint;
    let now = 10_000_000_000u64;
    // the provider: no book / no snapshot of the mint -> no floors (age None, reason no_snapshot)
    assert!(holders_for_floor(None, &mint, now).age_ms.is_none());
    let mut book = arbx::ps43_book::TBook::new();
    assert!(holders_for_floor(Some(&book), &mint, now).age_ms.is_none());
    // a snapshot 300 ms old: its holders (the curve excluded), largest first, age 300
    let curve = [7u8; 32];
    book.snapshot(mint, curve, &[([1u8; 32], 5_000), (curve, 900_000), ([2u8; 32], 9_000)], 100, now - 300_000_000);
    let s = holders_for_floor(Some(&book), &mint, now);
    assert_eq!(s.age_ms, Some(300));
    assert_eq!(s.holders, vec![([2u8; 32], 9_000), ([1u8; 32], 5_000)]);
    for (sn, why, reason) in [(snap(6, None), WHY_NO_SNAPSHOT, "no_snapshot"), (snap(6, Some(2_001)), WHY_STALE, "stale"), (snap(1, Some(5)), WHY_FEW, "few_holders")] {
        let h = g.hset(&sn, &user, &mint, now);
        assert_eq!(h.why, why);
        let gt = sender_try(Some(&g), &swin(1, h), user, Some((helius()[3], 200_000)), None, now);
        assert_eq!(gt.nf, 0);
        assert_eq!(gt.ixs[2].data.len(), 10, "deadline only");
        assert_eq!(g.rec(true, &h, 0, 0, &gt.ixs[2], now)["reason"], reason);
    }
    // fresh when built, stale when the try signs 2.5 s later (no trade refreshed it): deadline only
    let h = g.hset(&snap(6, Some(100)), &user, &mint, now);
    assert_eq!(g.n_floors(&h, now), 6);
    assert_eq!(g.n_floors(&h, now + 1_850_000_000), 6);
    assert_eq!(g.n_floors(&h, now + 2_000_000_000), 0, "100 ms + 2 s > 2,000 ms");
    let gt = sender_try(Some(&g), &swin(1, h), user, Some((helius()[3], 200_000)), None, now + 2_500_000_000);
    assert_eq!((gt.nf, gt.ixs[2].data.len()), (0, 10));
    assert_eq!(g.rec(true, &h, 0, 0, &gt.ixs[2], now + 2_500_000_000)["reason"], "stale");
    // deadline mode never carries floors
    let gd = g43(&["--presend-live-guard", "deadline"]);
    assert_eq!(gd.n_floors(&h, now), 0);
    assert_eq!(gd.hset(&snap(6, Some(1)), &user, &mint, now).n, 0);
}

/// the guard's CU in the try's CU limit: measured on the built program under LiteSVM (program/snipe-guard-svm compute_units_table:
/// deadline 330, 6 floors 1,445, 8 floors 1,793, curve + 12 floors 2,613; a listed wallet + 1,647 for the PDA check) against the dip42
/// buys' measured max 102.2k CU incl. Lighthouse (onchain REPORT, 425 fills): the default 120,000 limit holds the worst shape
#[test]
fn dip43_guard_cu_fits_the_limit() {
    const BUY_MAX_CU: u64 = 102_200;
    const GUARD_WORST_CU: u64 = 2_613 + 1_647;
    assert!(BUY_MAX_CU + GUARD_WORST_CU < CU_DEFAULT, "{}", BUY_MAX_CU + GUARD_WORST_CU);
    let c = cfg(&["--presend-live-guard", "holders", "--presend-live-guard-program", PROG]).unwrap().unwrap();
    assert_eq!(c.cu_limit as u64, CU_DEFAULT, "the guard does not change the CU limit");
}

#[test]
fn dip43_guard_abort_codes_decoded() {
    let g = g43(&["--presend-live-guard", "holders", "--presend-live-guard-ab", "on"]);
    let code = |f: sgl::Fail| format!("ix2:custom:0x{:x}", sgl::code(f));
    // late: stays "deadline" (as Lighthouse's), decoded
    let (r, j) = reclassify(Some(&g), 1, "deadline".into(), &code(sgl::Fail { kind: sgl::K_DEADLINE, idx: 0, cnt: 0, gap: 2 }));
    assert_eq!(r, "deadline");
    let j = j.unwrap();
    assert_eq!((j["kind"].as_str(), j["gap_bucket"].as_u64(), j["gap"].as_str()), (Some("deadline"), Some(2), Some("2 slots")));
    // floors: its own result, the worst holder's index, how many below, how far
    let (r, j) = reclassify(Some(&g), 3, "deadline".into(), &code(sgl::Fail { kind: sgl::K_FLOORS, idx: 4, cnt: 2, gap: 0 }));
    assert_eq!(r, "guard_abort");
    assert_eq!(j.unwrap(), serde_json::json!({"kind": "floors", "idx": 4, "cnt": 2, "gap_bucket": 0, "gap": "0% held (sold out / closed)", "code": format!("{:#010x}", sgl::code(sgl::Fail { kind: sgl::K_FLOORS, idx: 4, cnt: 2, gap: 0 }))}));
    // auth: the sub-reason named
    let (r, j) = reclassify(Some(&g), 5, "deadline".into(), &code(sgl::Fail::new(sgl::K_AUTH, sgl::A_NOT_LISTED)));
    assert_eq!((r.as_str(), j.unwrap()["sub"].as_str()), ("guard_abort", Some("not_listed")));
    // every kind / sub-reason round-trips through the engine's decoder
    for kind in sgl::K_AUTH..=sgl::K_ADMIN { for idx in 0..16u8 {
        let f = sgl::Fail { kind, idx, cnt: idx % 3, gap: idx % 6 };
        let (r, j) = reclassify(Some(&g), 1, "deadline".into(), &code(f));
        assert_eq!(r, if kind == sgl::K_DEADLINE { "deadline" } else { "guard_abort" });
        let j = j.unwrap();
        assert_eq!((j["idx"].as_u64(), j["cnt"].as_u64(), j["gap_bucket"].as_u64()), (Some(idx as u64), Some((idx % 3) as u64), Some((idx % 6) as u64)));
    } }
    // an unknown code is logged raw; a non-custom failure at the guard is guard_other
    let (r, j) = reclassify(Some(&g), 1, "deadline".into(), "ix2:custom:0x1771");
    assert_eq!((r.as_str(), j.unwrap()["kind"].as_str()), ("guard_abort", Some("unknown")));
    let (r, _) = reclassify(Some(&g), 1, "deadline".into(), "ix2:ie26");
    assert_eq!(r, "guard_other");
    // a Lighthouse try (guard off; the A/B's even windows) is never reclassified; other results never
    assert_eq!(reclassify(None, 1, "deadline".into(), "ix2:custom:0x1771"), ("deadline".to_string(), None));
    assert_eq!(reclassify(Some(&g), 2, "deadline".into(), "ix2:custom:0x1771"), ("deadline".to_string(), None));
    assert_eq!(reclassify(Some(&g), 1, "6042".into(), "ix5:custom:0x179a"), ("6042".to_string(), None));
    // classify still reports any failure at index 2 as "deadline" first (dip42), which reclassify then splits
    let roles = pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) };
    assert_eq!(pl::classify(&code(sgl::Fail { kind: sgl::K_FLOORS, idx: 0, cnt: 2, gap: 1 }), &roles), "deadline");
}

/// the engine's instruction bytes = the program's golden vectors (program/snipe-guard/src/tests.rs golden_bytes)
#[test]
fn dip43_guard_golden_bytes() {
    let hex = |d: &[u8]| d.iter().map(|b| format!("{b:02x}")).collect::<String>();
    let user = ams();
    let gix = guard_ix(prog(), &snipe_guard::client::Guard { deadline: Some(467_582_218), ..Default::default() }, user, None);
    assert_eq!(hex(&gix.data), "54010abdde1b00000000");
    let gix = guard_ix(prog(), &snipe_guard::client::Guard { deadline: Some(467_582_218), floors: vec![([2; 32], 36_000_000), ([3; 32], 27_000_000), ([4; 32], 9_000)], max_viol: 1, ..Default::default() }, user, None);
    assert_eq!(hex(&gix.data), "54050abdde1b000000000301".to_owned() + "00512502" + "c0fc9b01" + "28230000");
    assert_eq!(gix.accounts.iter().map(|m| (m.key, m.signer, m.writable)).collect::<Vec<_>>(), vec![(user, true, false), ([2; 32], false, false), ([3; 32], false, false), ([4; 32], false, false)]);
}

/// dip43c: holders mode floors go on the holder's REAL token account when the book knows it (else its ATA)
#[test]
fn dip43c_floor_on_real_account() {
    let g = g43(&["--presend-live-guard", "holders"]);
    let (user, mint) = (ams(), launch().mint);
    let now = 10_000_000_000u64;
    let mut s = snap(6, Some(5));
    let real = [77u8; 32];
    s.accts = vec![(s.holders[0].0, real)];
    let h = g.hset(&s, &user, &mint, now);
    assert!(h.n >= 2);
    let first = h.f[..h.n as usize].iter().find(|f| f.2 == s.holders[0].0).unwrap();
    assert_eq!(first.0, real, "floor on the real account");
    let other = h.f[..h.n as usize].iter().find(|f| f.2 != s.holders[0].0).unwrap();
    assert_eq!(other.0, arbx::pda::ata(&other.2, &mint, &arbx::pda::TOKEN_2022), "unknown: the ATA");
}

/// dip43c: --presend-live-tbal-src largest needs the book; bad values refused; off by default
#[test]
fn dip43c_tbal_src_flag() {
    assert!(!cfg(&[]).unwrap().unwrap().c43.tbal_largest);
    assert!(cfg(&["--presend-live-tbal-src", "largest"]).is_err(), "needs the book");
    assert!(cfg(&["--presend-live-tbal", "on", "--presend-live-fam-log", "--presend-live-tbal-src", "largest"]).unwrap().unwrap().c43.tbal_largest);
    assert!(cfg(&["--presend-live-tbal", "on", "--presend-live-fam-log", "--presend-live-tbal-src", "maybe"]).is_err());
}

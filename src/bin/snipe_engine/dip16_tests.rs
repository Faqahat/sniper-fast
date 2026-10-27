// ===================================================================================================================
// dip16 tests (10-25 PKT; owner OK ~19:50 PKT: the free landing-speed fixes of the validator-client study,
// ops/dip/speed/clients/CLIENTS.md, action list ops/dip/speed/landing2/CLIENT_ACTIONS.md). Every dip16 flag is OFF by default.
//  * golden: with no dip16 flag, every tx shape the engine sends is byte-for-byte dip15's (digest captured on the dip15 tree)
//  * C1 measurement (#[ignore], run by hand, read-only): our buy's real loaded-accounts data size
// ===================================================================================================================
use super::*;
use arbx::config::SendKind;
use arbx::fast;

const G: GuardEnc = GuardEnc { disc: 14, op: 5, acct: false };
/// the encoding the live engines verified on chain at start (run logs: "SLOT-GUARD verified ... disc 15 op 5 acct false")
const G_LIVE: GuardEnc = GuardEnc { disc: 15, op: 5, acct: false };
fn key_of(seed: u8) -> SigningKey { SigningKey::from_bytes(&[seed; 32]) }
fn rnd(i: u64, tag: u8) -> Pk {
    use sha2::Digest;
    sha2::Sha256::digest([&i.to_le_bytes()[..], &[tag]].concat()).into()
}
fn tip_accts(k: SendKind) -> Vec<Pk> { send::known_tip_accounts(k).iter().map(|a| pk(a)).collect() }

/// the probe launch of a template (Fast::make_template / make_nonce_template)
fn probe_launch() -> Launch {
    Launch { mint: fast::probe_var(0), bonding_curve: fast::probe_var(1), assoc_bonding_curve: fast::probe_var(2), creator: fast::probe_var(9),
        dev_buy_lamports: 0, is_create_v2: true, is_mayhem: false, is_cashback: false, creator_fee_bps: 0, is_holder_reward: false, buyback_fee_recipient: fast::probe_var(5) }
}

/// GOLDEN (dip16 "no flag = dip15 on the wire"): every tx shape the engine builds, with the dip16 flags OFF, hashed in order:
///  (a) the multi-tip buy as Fast::reference / prepare_on's full compile / lat::build_tx assemble it (tips first, the buy's CU limit,
///      CU price, ATAs, the slot guard right before the pump buy; CU limit raised past 2 tips), 0..=4 tips, two sizes, a real
///      min_out and the probe's u64::MAX, guard on / off, message and signed bytes;
///  (b) the multi-tip TEMPLATE exactly as Fast::make_template builds it (probe keys), and its patch for real launches;
///  (c) every durable-nonce variant shape: make_nonce_template + its patch, and nonce_variant_ixs' full compile;
///  (d) the pre-send attempt (presend_live::attempt_ixs) with and without its tip; (e) the sell; (f) the snipe-mode build_buy.
/// -> (sha256 hex, number of byte strings hashed)
pub(super) fn golden_digest() -> (String, usize) {
    use sha2::Digest;
    let mut h = sha2::Sha256::new();
    let mut n = 0usize;
    let mut add = |b: &[u8]| { h.update((b.len() as u64).to_le_bytes()); h.update(b); n += 1; };
    let key = key_of(11);
    let user: Pk = key.verifying_key().to_bytes();
    let bh = [0x42u8; 32];
    let launches: Vec<Launch> = (0..12u64).map(|i| {
        let mut l = snipe_build::launch_from_target(rnd(i, 1), rnd(i, 2));
        if i % 3 == 0 { l.buyback_fee_recipient = rnd(i, 3); }
        l
    }).collect();
    // (a) the multi-tip buy (full compile)
    for (i, l) in launches.iter().enumerate() {
        for ntips in 0..=4usize { for spend in [350_000_000u64, 550_000_000] { for mo in [777 + i as u64, u64::MAX] { for guard in [Some(G), None] {
            let tips: Vec<(Pk, u64)> = (0..ntips).map(|k| (rnd(100 + k as u64, 7), 200_000 + 100_000 * k as u64)).collect();
            let (ixs, _) = build_buy_spend(user, l, None, spend, mo);
            let ixs = match guard { Some(g) => insert_guard(ixs, g, 458_000_001 + i as u64), None => ixs };
            let mut v: Vec<build::Ix> = tips.iter().map(|(t, a)| build::transfer_ix(user, *t, *a)).collect();
            v.extend(ixs);
            if tips.len() > 2 { lat::bump_cu_limit(&mut v, 300 * (tips.len() as u32 - 2)); }
            let m = build::compile_v0(user, &v, bh, &[], &[]).unwrap();
            add(&m.bytes);
            add(&build::sign(&m, &key));
        } } } }
    }
    // (b) the multi-tip template (as Fast::make_template) and its patch
    for ntips in 0..=4usize { for spend in [350_000_000u64, 550_000_000] { for guard in [true, false] {
        let probe = probe_launch();
        let (ixs, _) = build_buy_spend(user, &probe, None, spend, fast::PROBE_MIN_OUT);
        let mut ixs = if guard { insert_guard(ixs, G, fast::PROBE_DEADLINE) } else { ixs };
        let (p0, p1) = (probe.mint, probe.bonding_curve);
        let map = [(pda::ata(&p1, &p0, &pda::TOKEN_2022), fast::probe_var(2)), (pda::ata(&p1, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), fast::probe_var(3)),
            (pda::ata(&user, &p0, &pda::TOKEN_2022), fast::probe_var(4))];
        for ix in ixs.iter_mut() { for a in ix.accounts.iter_mut() { if let Some((_, to)) = map.iter().find(|(from, _)| *from == a.key) { a.key = *to; } } }
        let amts: Vec<u64> = (0..ntips).map(|k| 200_000 + 100_000 * k as u64).collect();
        let mut v: Vec<build::Ix> = amts.iter().enumerate().map(|(k, a)| build::transfer_ix(user, fast::probe_tip(k), *a)).collect();
        v.extend(ixs);
        if ntips > 2 { lat::bump_cu_limit(&mut v, 300 * (ntips as u32 - 2)); }
        let pm = build::compile_v0(user, &v, fast::PROBE_BH, &[], &[]).unwrap();
        let t = fast::Template::from_probe_msg_dl(pm.bytes, ntips, guard).unwrap();
        add(&t.msg);
        for (i, l) in launches.iter().enumerate().take(4) {
            let (bc, abc) = (l.bonding_curve, l.assoc_bonding_curve);
            let vars: fast::VarKeys = [l.mint, bc, abc, pda::ata(&bc, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), pda::ata(&user, &l.mint, &pda::TOKEN_2022), l.buyback_fee_recipient];
            let tk: Vec<Pk> = (0..ntips).map(|k| rnd(200 + k as u64, 8)).collect();
            let mut out = Vec::new();
            t.patch_dl(&mut out, &vars, &tk, &bh, 999 + i as u64, guard.then_some(460_000_000 + i as u64)).unwrap();
            add(&out);
        }
    } } }
    // (c) durable-nonce variants: template + patch, and the full compile
    for guard in [Some(G), None] { for tip in [None, Some(1_000_000u64), Some(200_000)] { for spend in [350_000_000u64, 550_000_000] {
        let t = fastfire::make_nonce_template(user, tip, spend, guard).unwrap();
        add(&t.msg);
        for (i, l) in launches.iter().enumerate().take(4) {
            let (nonce, value, tip_acct) = (rnd(i as u64, 4), rnd(i as u64, 5), rnd(i as u64, 6));
            let vars: fast::VarKeys = [l.mint, l.bonding_curve, l.assoc_bonding_curve, pda::ata(&l.bonding_curve, &snipe_build::WSOL, &pda::TOKEN_PROGRAM),
                pda::ata(&user, &l.mint, &pda::TOKEN_2022), l.buyback_fee_recipient];
            let tk: Vec<Pk> = tip.iter().map(|_| tip_acct).collect();
            let mut out = Vec::new();
            t.patch_nonce(&mut out, &vars, &tk, &nonce, &value, 5 + i as u64, guard.map(|_| 470_000_000 + i as u64)).unwrap();
            add(&out);
            let ixs = fastfire::nonce_variant_ixs(user, l, nonce, tip.map(|a| (tip_acct, a)), spend, u64::MAX - i as u64, guard.map(|g| (g, 470_000_000 + i as u64)));
            let m = build::compile_v0(user, &ixs, value, &[], &[]).unwrap();
            add(&m.bytes);
            add(&build::sign(&m, &key));
        }
    } } }
    // (d) the pre-send attempt; (e) the sell; (f) the snipe-mode buy (--spend-lamports default)
    for (i, l) in launches.iter().enumerate() {
        for tip in [None, Some((rnd(i as u64, 9), 200_000u64))] {
            let (ixs, _) = arbx::presend_live::attempt_ixs(user, l, 550_000_000, 12_345 + i as u64, 120_000, 1_000, guard_ix_enc(G, 480_000_000 + i as u64), tip);
            add(&build::compile_v0(user, &ixs, bh, &[], &[]).unwrap().bytes);
        }
        let s = snipe_build::sell_message_ixs(user, l, 9_000_000 + i as u64, 1, 120_000, 5_000_000, i % 2 == 0);
        add(&build::compile_v0(user, &s, bh, &[], &[]).unwrap().bytes);
        let (b, _) = build_buy(user, l, None, 2_000_000, 1 + i as u64);
        add(&build::compile_v0(user, &b, bh, &[], &[]).unwrap().bytes);
    }
    (h.finalize().iter().map(|b| format!("{b:02x}")).collect(), n)
}

/// the digest of golden_digest() on the dip15 tree (10-25 ~20:40 PKT, before any dip16 change)
pub(super) const DIP15_GOLDEN: &str = "f8897ad61e6319f67663bab0f3ace9197e42c7bf231f2d570cc987947f409b0d";

#[test]
fn dip16_golden_flags_off_equals_dip15() {
    let (d, n) = golden_digest();
    eprintln!("dip16 golden: {n} byte strings, sha256 {d}");
    assert_eq!(d, DIP15_GOLDEN, "with no dip16 flag the tx bytes must be dip15's ({n} shapes)");
}

// ---- C1: --loaded-data-limit ----------------------------------------------------------------------------------------

const LL16: u32 = 16 << 20;

fn is_ll(ix: &build::Ix, b: u32) -> bool { ix.program == arbx::tx::COMPUTE_BUDGET && ix.accounts.is_empty() && ix.data == [&[4u8][..], &b.to_le_bytes()[..]].concat() }

/// C1 ON: every buy shape gets SetLoadedAccountsDataSizeLimit as its LAST instruction and nothing else changes: the same instructions
/// before it (so no index moves: the guard, the buy, the tips, the pre-send roles), the nonce advance still FIRST, the CU limit / price
/// as parsed by the senders, every template patch == its full compile, every path's tip rule still accepts it, <= 1232 bytes with the
/// largest fan (4 tips + guard). OFF (None) = dip15's list (the golden test covers the bytes)
#[test]
fn dip16_c1_loaded_limit_on_shapes() {
    let key = key_of(12);
    let user: Pk = key.verifying_key().to_bytes();
    assert_eq!(speed16::loaded_limit(), None, "off unless --loaded-data-limit");
    let (hel, noz, jit, bolt) = (tip_accts(SendKind::Helius), tip_accts(SendKind::Nozomi), tip_accts(SendKind::JitoBundle), tip_accts(SendKind::Bolt));
    let fan4 = [(hel[0], 1_000_000u64), (noz[0], 1_000_000), (jit[0], 1_000_000), (bolt[0], 1_000_000)];
    let kinds = [(SendKind::Helius, &hel), (SendKind::Nozomi, &noz), (SendKind::JitoBundle, &jit), (SendKind::Bolt, &bolt)];
    let mut max_bytes = 0usize;
    for i in 0..40u64 {
        let mut l = snipe_build::launch_from_target(rnd(i, 31), rnd(i, 32));
        if i % 4 == 0 { l.buyback_fee_recipient = rnd(i, 33); }
        let (mo, dl) = (1 + i * 7_919, 460_000_000 + i);
        // the buy's own list
        let (off, s0) = build_buy_spend_ll(user, &l, None, 550_000_000, mo, None);
        let (on, s1) = build_buy_spend_ll(user, &l, None, 550_000_000, mo, Some(LL16));
        assert_eq!(s0, s1);
        assert_eq!(build_buy_spend(user, &l, None, 550_000_000, mo).0.len(), off.len(), "the engine's build_buy_spend is OFF in tests");
        assert_eq!(on.len(), off.len() + 1);
        assert!(is_ll(on.last().unwrap(), LL16), "the limit is the LAST instruction");
        assert!(on[..off.len()].iter().zip(&off).all(|(a, b)| a.program == b.program && a.data == b.data && a.accounts.len() == b.accounts.len()), "the rest unchanged");
        // the multi-tip tx of every fan size (as Fast::reference / prepare_on's full compile) and its template (as Fast::make_template)
        for ntips in 0..=4usize {
            let tips = &fan4[..ntips];
            let full = |ll: Option<u32>| {
                let (ixs, _) = build_buy_spend_ll(user, &l, None, 550_000_000, mo, ll);
                let mut v: Vec<build::Ix> = tips.iter().map(|(t, a)| build::transfer_ix(user, *t, *a)).collect();
                v.extend(insert_guard(ixs, G, dl));
                if ntips > 2 { lat::bump_cu_limit(&mut v, 300 * (ntips as u32 - 2)); }
                build::compile_v0(user, &v, [9u8; 32], &[], &[]).unwrap()
            };
            let (m_off, m_on) = (full(None), full(Some(LL16)));
            let raw = build::sign(&m_on, &key);
            max_bytes = max_bytes.max(raw.len());
            assert!(raw.len() <= 1232, "{ntips} tips + guard + limit: {} bytes", raw.len());
            assert_eq!(raw.len(), build::sign(&m_off, &key).len() + 8, "+8 bytes: one compute-budget ix (the program key is already in the table)");
            let (tx_on, _) = arbx::tx::parse_wire(&raw).unwrap();
            let (tx_off, _) = arbx::tx::parse_wire(&build::sign(&m_off, &key)).unwrap();
            assert_eq!((tx_on.cu_limit, tx_on.cu_price_micro), (tx_off.cu_limit, tx_off.cu_price_micro), "the senders read the same CU limit / price");
            assert_eq!(tx_on.ixs.len(), tx_off.ixs.len() + 1);
            assert_eq!(ix_roles(&raw), ix_roles(&build::sign(&m_off, &key)), "the guard / buy indices do not move");
            for (k, (t, _)) in tips.iter().enumerate() {
                let (kind, accts) = kinds.iter().find(|(_, a)| a.contains(t)).unwrap();
                send::verify_copy(&raw, *kind, accts, "x").unwrap_or_else(|e| panic!("{kind:?} (tip {k}) refuses the C1 tx: {e:#}"));
            }
            // the template path, exactly as Fast::make_template, with the limit
            let probe = probe_launch();
            let (pixs, _) = build_buy_spend_ll(user, &probe, None, 550_000_000, fast::PROBE_MIN_OUT, Some(LL16));
            let mut pixs = insert_guard(pixs, G, fast::PROBE_DEADLINE);
            let (p0, p1) = (probe.mint, probe.bonding_curve);
            let map = [(pda::ata(&p1, &p0, &pda::TOKEN_2022), fast::probe_var(2)), (pda::ata(&p1, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), fast::probe_var(3)),
                (pda::ata(&user, &p0, &pda::TOKEN_2022), fast::probe_var(4))];
            for ix in pixs.iter_mut() { for a in ix.accounts.iter_mut() { if let Some((_, to)) = map.iter().find(|(from, _)| *from == a.key) { a.key = *to; } } }
            let mut v: Vec<build::Ix> = tips.iter().enumerate().map(|(k, (_, a))| build::transfer_ix(user, fast::probe_tip(k), *a)).collect();
            v.extend(pixs);
            if ntips > 2 { lat::bump_cu_limit(&mut v, 300 * (ntips as u32 - 2)); }
            let t = fast::Template::from_probe_msg_dl(build::compile_v0(user, &v, fast::PROBE_BH, &[], &[]).unwrap().bytes, ntips, true).unwrap();
            let vars: fast::VarKeys = [l.mint, l.bonding_curve, l.assoc_bonding_curve, pda::ata(&l.bonding_curve, &snipe_build::WSOL, &pda::TOKEN_PROGRAM),
                pda::ata(&user, &l.mint, &pda::TOKEN_2022), l.buyback_fee_recipient];
            let mut out = Vec::new();
            t.patch_dl(&mut out, &vars, &tips.iter().map(|x| x.0).collect::<Vec<_>>(), &[9u8; 32], mo, Some(dl)).unwrap();
            assert_eq!(out, m_on.bytes, "template + patch == full compile with the limit ({ntips} tips)");
        }
        // the durable-nonce variant: AdvanceNonceAccount FIRST, its one tip, the limit LAST; template == full compile
        for tip in [None, Some((noz[1], 1_000_000u64))] {
            let (nonce, value) = (rnd(i, 34), rnd(i, 35));
            let off = fastfire::nonce_variant_ixs_ll(user, &l, nonce, tip, 550_000_000, mo, Some((G, dl)), None);
            let on = fastfire::nonce_variant_ixs_ll(user, &l, nonce, tip, 550_000_000, mo, Some((G, dl)), Some(LL16));
            assert_eq!(on.len(), off.len() + 1);
            assert!(is_ll(on.last().unwrap(), LL16));
            assert_eq!((on[0].program, on[0].data.clone()), ([0u8; 32], 4u32.to_le_bytes().to_vec()), "AdvanceNonceAccount stays first");
            let full = build::compile_v0(user, &on, value, &[], &[]).unwrap();
            let t = fastfire::make_nonce_template_ll(user, tip.map(|x| x.1), 550_000_000, Some(G), Some(LL16)).unwrap();
            let vars: fast::VarKeys = [l.mint, l.bonding_curve, l.assoc_bonding_curve, pda::ata(&l.bonding_curve, &snipe_build::WSOL, &pda::TOKEN_PROGRAM),
                pda::ata(&user, &l.mint, &pda::TOKEN_2022), l.buyback_fee_recipient];
            let mut out = Vec::new();
            t.patch_nonce(&mut out, &vars, &tip.iter().map(|x| x.0).collect::<Vec<_>>(), &nonce, &value, mo, Some(dl)).unwrap();
            assert_eq!(out, full.bytes, "nonce template + patch == full compile with the limit");
            let raw = build::sign(&full, &key);
            assert!(raw.len() <= 1232);
            if let Some((t, _)) = tip { send::verify_copy(&raw, SendKind::Nozomi, &noz, "nozomi").unwrap(); let _ = t; }
            assert_eq!(fastfire::make_nonce_template_ll(user, tip.map(|x| x.1), 550_000_000, Some(G), None).unwrap().msg,
                fastfire::make_nonce_template(user, tip.map(|x| x.1), 550_000_000, Some(G)).unwrap().msg, "off: the engine's nonce template");
        }
        // the pre-send attempt: the limit appended LAST, so its roles (guard / ATA / buy / tip indices) are dip15's
        let (mut ps, roles) = arbx::presend_live::attempt_ixs(user, &l, 550_000_000, mo, 120_000, 1_000, guard_ix_enc(G, dl), Some((hel[2], 200_000)));
        let n = ps.len();
        speed16::add_ll(&mut ps, Some(LL16));
        assert_eq!(ps.len(), n + 1);
        assert!(is_ll(&ps[n], LL16));
        assert_eq!((roles.guard, roles.ata, roles.buy, roles.tip), (Some(2), Some(3), Some(5), Some(6)), "roles unchanged (all before the limit)");
        let mut ps_off = ps.clone(); ps_off.pop();
        speed16::add_ll(&mut ps_off, None);
        assert_eq!(ps_off.len(), n, "off: nothing appended");
    }
    eprintln!("C1: largest buy (4 tips + guard + limit): {max_bytes} bytes (limit 1232)");
}

/// C1 flag: 13 MiB..=64 MiB bytes, an integer (check_flags), else refused; the cost model's numbers
#[test]
fn dip16_c1_flag_and_cost() {
    for bad in [0u64, 1 << 20, (13 << 20) - 1, (64 << 20) + 1, u32::MAX as u64 + 7] { assert!(speed16::ll_check(bad).is_err(), "{bad} must be refused"); }
    for ok in [13u64 << 20, 16 << 20, 64 << 20] { assert_eq!(speed16::ll_check(ok).unwrap() as u64, ok); }
    let a = |v: &[&str]| -> Vec<String> { std::iter::once("snipe_engine").chain(v.iter().copied()).map(String::from).collect() };
    check_flags(&a(&["--dip", "--loaded-data-limit", "16777216", "--log-route-headers", "--window-clock", "--dip-probe", "20", "--dip-probe-nonce", "ab"])).unwrap();
    check_flags(&a(&["--dip", "--dip-probe", "20", "--dip-probe-lock-only", "on", "--dip-probe-lock-cu", "3000"])).unwrap();
    for bad in [&["--loaded-data-limit", "16MiB"][..], &["--loaded-data-limit"], &["--dip-probe-lock-cu", "x"], &["--loaded-data-limits", "1"], &["--window-clocks"]] {
        assert!(check_flags(&a(bad)).is_err(), "{bad:?} must refuse to start");
    }
    // Agave cost_model / Firedancer fd_pack_cost: 8 units per 32 KiB page, rounded up
    assert_eq!((speed16::ll_cost(64 << 20), speed16::ll_cost(16 << 20), speed16::ll_cost(12_520_412), speed16::ll_cost(1)), (16_384, 4_096, 3_064, 8));
    // the prod buy (CU limit 100,000 + 300 for a 3-tip fan, 5,000,000 uL/CU; 11 write locks; 89 + 5 data bytes): +11.3% priority at 16 MiB
    let g3 = speed16::priority(100_300, 5_000_000, 11, 94, 16 << 20) / speed16::priority(100_300, 5_000_000, 11, 89, 64 << 20) - 1.0;
    // a nonce variant (100,000 CU, 10 write locks, 69 + 5 bytes) and the tipless one (9 locks, 57 + 5 bytes)
    let gn = speed16::priority(100_000, 5_000_000, 10, 74, 16 << 20) / speed16::priority(100_000, 5_000_000, 10, 69, 64 << 20) - 1.0;
    let gt = speed16::priority(100_000, 5_000_000, 9, 62, 16 << 20) / speed16::priority(100_000, 5_000_000, 9, 57, 64 << 20) - 1.0;
    // at the exact measured size (12,520,412 B: 383 pages) the most it could be
    let gx = speed16::priority(100_300, 5_000_000, 11, 94, 12_520_412) / speed16::priority(100_300, 5_000_000, 11, 89, 64 << 20) - 1.0;
    eprintln!("C1 priority gain at 16 MiB: 3-tip buy {:+.2}%, nonce variant {:+.2}%, tipless variant {:+.2}% (exact size: {:+.2}%)", g3 * 100.0, gn * 100.0, gt * 100.0, gx * 100.0);
    assert!((0.110..0.118).contains(&g3) && (0.110..0.118).contains(&gn) && (0.110..0.118).contains(&gt), "{g3} {gn} {gt}");
    // the start-up check's sum: 64 + space per account, the programdata of the upgradeable programs found
    use base64::Engine as _;
    let prog = |pd: Pk| serde_json::json!({"owner": "BPFLoaderUpgradeab1e11111111111111111111111", "space": 36,
        "data": [base64::engine::general_purpose::STANDARD.encode([&[2u8, 0, 0, 0][..], &pd[..]].concat()), "base64"]});
    let keys = [rnd(1, 40), rnd(2, 40), rnd(3, 40)];
    let vals = [prog(rnd(9, 41)), serde_json::json!({"owner": "11111111111111111111111111111111", "space": 1088, "data": ["", "base64"]}), serde_json::Value::Null];
    let (sum, pd, _) = speed16::ll_sum(&keys, &vals);
    assert_eq!((sum, pd), (64 + 36 + 64 + 1088, vec![(rnd(9, 41), rnd(1, 40))]));
}

// ---- C3: --log-route-headers -----------------------------------------------------------------------------------------

/// C3: off -> the FAST-ACK line is dip15's (route None) and nothing is kept; on -> ` ck_route=` in the line, every answer of a fire kept
/// by its tag until its timing record takes it (status, ms, route), bounded; the async sends' route parsed from their reply
#[test]
fn dip16_c3_route_headers() {
    assert!(!speed16::route_on(), "off unless --log-route-headers");
    let a = |route: Option<&str>| arbx::fast::Ack { path: "staked-rpc".into(), tag: 7, t_write: 0, t_ack: 0, status: Some(200), body: "{\"result\":\"5sig\"}".into(), route: route.map(String::from) };
    // dip15's format, byte for byte, when no route was read
    assert_eq!(fastfire::fast_ack_line(&a(None), 1.25), "  FAST-ACK tag=7 path=staked-rpc ack_ms=1.250 status=Some(200) reply={\"result\":\"5sig\"}");
    assert_eq!(fastfire::fast_ack_line(&a(Some("fallback-ams")), 1.25), "  FAST-ACK tag=7 path=staked-rpc ack_ms=1.250 status=Some(200) ck_route=fallback-ams reply={\"result\":\"5sig\"}");
    // off: note_ack keeps nothing
    speed16::note_ack(0xC3_0001, "staked-rpc", Some(200), 1.0, Some("x"));
    assert!(speed16::take_acks(0xC3_0001).is_none());
    // the store (on)
    speed16::keep_ack(0xC3_0002, "staked-rpc", Some(200), 1.23456, Some("staked"));
    speed16::keep_ack(0xC3_0002, "helius-swqos", Some(429), 0.5, None);
    let v = speed16::take_acks(0xC3_0002).unwrap();
    assert_eq!(v, vec![serde_json::json!({"path": "staked-rpc", "status": 200, "ms": 1.235, "ck_route": "staked"}),
                       serde_json::json!({"path": "helius-swqos", "status": 429, "ms": 0.5, "ck_route": null})]);
    assert!(speed16::take_acks(0xC3_0002).is_none(), "taken once");
    for k in 0..5000u64 { speed16::keep_ack(0xC3_1_0000 + k, "p", Some(200), 1.0, None); }
    assert!(speed16::take_acks(0xC3_1_0000).is_none(), "bounded: the oldest went");
    assert!(speed16::take_acks(0xC3_1_0000 + 4999).is_some());
    assert_eq!(speed16::reply_route("5sig route=staked-fra-1"), Some("staked-fra-1"));
    assert_eq!(speed16::reply_route("5sig"), None);
    assert_eq!(speed16::reply_route("5sig route="), None);
}

// ---- C4: --window-clock ----------------------------------------------------------------------------------------------

/// C4: the Alpenglow block deadlines; the window fields from the clocks (ms since the window's first arrival, left in the block);
/// the slot first-arrival table keeps the earliest arrival per slot and never lets an old slot clobber a newer one
#[test]
fn dip16_c4_window_clock() {
    assert!(!speed16::window_on(), "off unless --window-clock");
    assert_eq!((0..4).map(speed16::deadline_ms).collect::<Vec<_>>(), vec![144.0, 344.0, 544.0, 744.0]);
    let ms = 1_000_000u64;
    let (s, w0_rx) = (460_000_002u64, 1_800_000_000_000_000_000u64);
    // dump in window slot 2 (deadline 544 ms), first seen at 450 ms, executed feed 470 ms, decision 470.05, first write 470.10
    let j = speed16::window_core(s, Some(w0_rx), Some(w0_rx + 400 * ms), Some(w0_rx + 450 * ms), w0_rx + 470 * ms, Some(w0_rx + 470 * ms + 50_000), Some(w0_rx + 470 * ms + 100_000));
    assert_eq!((j["idx"].as_u64(), j["w0"].as_u64(), j["deadline_ms"].as_f64()), (Some(2), Some(460_000_000), Some(544.0)));
    assert_eq!((j["first_ms"].as_f64(), j["dump_ms"].as_f64(), j["dec_ms"].as_f64(), j["write_ms"].as_f64()), (Some(450.0), Some(470.0), Some(470.05), Some(470.1)));
    assert_eq!((j["left_ms_dec"].as_f64(), j["left_ms_write"].as_f64(), j["in_slot_ms"].as_f64()), (Some(73.95), Some(73.9), Some(50.0)));
    // window slot 0: 144 ms; past the deadline the time left is negative (a structural spill)
    let j0 = speed16::window_core(460_000_000, Some(w0_rx), Some(w0_rx), None, w0_rx + 150 * ms, Some(w0_rx + 151 * ms), None);
    assert_eq!((j0["idx"].as_u64(), j0["left_ms_dec"].as_f64(), j0.get("write_ms")), (Some(0), Some(-7.0), None));
    // no window start known: the slot fields only
    let jn = speed16::window_core(s, None, None, None, w0_rx, Some(w0_rx), None);
    assert!(jn.get("dump_ms").is_none() && jn["deadline_ms"].as_f64() == Some(544.0));
    // the table (arbx::feeds): slots far from any real one
    let b = 9_000_000_000u64;
    arbx::feeds::slot_first_note(b, 500, 1);
    arbx::feeds::slot_first_note(b, 450, 2);
    arbx::feeds::slot_first_note(b, 470, 0);
    assert_eq!(arbx::feeds::slot_first(b), Some((450, 2)), "the earliest arrival, its feed");
    arbx::feeds::slot_first_note(b - arbx::feeds::SLOT_FIRST_N as u64, 1, 3);
    assert_eq!(arbx::feeds::slot_first(b), Some((450, 2)), "an older slot of the same bucket never clobbers it");
    assert_eq!(arbx::feeds::slot_first(b - arbx::feeds::SLOT_FIRST_N as u64), None);
    arbx::feeds::slot_first_note(b + arbx::feeds::SLOT_FIRST_N as u64, 900, 1);
    assert_eq!((arbx::feeds::slot_first(b), arbx::feeds::slot_first(b + arbx::feeds::SLOT_FIRST_N as u64)), (None, Some((900, 1))), "a newer slot takes the bucket");
    // the first write on the feeds' realtime clock
    let now_m = arbx::fast::mono_ns();
    let w = vec![("a".to_string(), "http", now_m - 2_000, now_m - 1_000, "written"), ("b".to_string(), "jito", now_m - 3_000, now_m - 3_000, "spawned")];
    let rt = speed16::first_write_rt(&w).unwrap();
    let now_r = arbx::feeds::clock::now_ns();
    assert!(now_r >= rt && now_r - rt < 50_000_000, "first write ~1 us ago on the realtime clock: {}", now_r as i64 - rt as i64);
    assert_eq!(speed16::first_write_rt(&w[1..]), None, "no written write");
}

// ---- B4: --dip-probe-nonce ---------------------------------------------------------------------------------------------

/// B4: the flag; the arms: off never, on always, ab in blocks of the path rotation so that every path gets both arms; a nonce probe is a
/// buy's durable-nonce variant that still cannot fill (min_out = u64::MAX), the nonce advance first
#[test]
fn dip16_b4_probe_nonce() {
    use speed16::ProbeNonce as P;
    let v = |x: &[&str]| -> Vec<String> { x.iter().map(|s| s.to_string()).collect() };
    assert_eq!(P::parse(&v(&["e"])).unwrap(), P::Off);
    assert_eq!(P::parse(&v(&["e", "--dip-probe-nonce", "on"])).unwrap(), P::On);
    assert_eq!(P::parse(&v(&["e", "--dip-probe-nonce", "ab"])).unwrap(), P::Ab);
    assert_eq!(P::parse(&v(&["e", "--dip-probe-nonce", "off"])).unwrap(), P::Off);
    assert!(P::parse(&v(&["e", "--dip-probe-nonce", "yes"])).is_err() && P::parse(&v(&["e", "--dip-probe-nonce"])).is_err());
    assert!((0..50).all(|k| !P::Off.arm(k, 3) && P::On.arm(k, 3)));
    let arms: Vec<bool> = (0..12).map(|k| P::Ab.arm(k, 3)).collect();
    assert_eq!(arms, vec![false, false, false, true, true, true, false, false, false, true, true, true]);
    for path in 0..3u64 { let mine: Vec<bool> = (0..12u64).filter(|k| k % 3 == path).map(|k| P::Ab.arm(k, 3)).collect(); assert!(mine.contains(&true) && mine.contains(&false), "path {path} gets both arms"); }
    assert_eq!((0..4).map(|k| P::Ab.arm(k, 0)).collect::<Vec<_>>(), vec![false, true, false, true], "no forced paths: alternate every probe");
    // the nonce probe = a buy's variant with min_out = u64::MAX
    let key = key_of(13);
    let user: Pk = key.verifying_key().to_bytes();
    let l = snipe_build::launch_from_target(rnd(1, 50), rnd(2, 50));
    let ixs = fastfire::nonce_variant_ixs(user, &l, rnd(3, 50), Some((tip_accts(SendKind::Nozomi)[0], 1_000_000)), 550_000_000, u64::MAX, Some((G, 461_000_000)));
    let (tx, _) = arbx::tx::parse_wire(&build::sign(&build::compile_v0(user, &ixs, rnd(4, 50), &[], &[]).unwrap(), &key)).unwrap();
    assert_eq!(tx.ixs[0].data, 4u32.to_le_bytes().to_vec(), "AdvanceNonceAccount first");
    let buy = tx.ixs.iter().find(|ix| tx.keys[ix.program as usize] == *snipe::PUMP).unwrap();
    assert_eq!(&buy.data[16..24], &u64::MAX.to_le_bytes()[..], "min tokens out = u64::MAX: it can never fill");
}

// ---- C5: --dip-probe-lock-only -----------------------------------------------------------------------------------------

/// C5: the flag; the lock-only probe: tips first, the CU limit / price, ONE 0-lamport System transfer wallet -> wallet that carries the
/// curve accounts WRITABLE and the pump program read-only; no other program (nothing can move a token or SOL but the fee and the tips);
/// it write-locks exactly the buy's non-wallet writable accounts; the senders' tip rules accept it; C1's limit last when on
#[test]
fn dip16_c5_lock_only_probe() {
    let v = |x: &[&str]| -> Vec<String> { x.iter().map(|s| s.to_string()).collect() };
    assert!(!speed16::lock_only_flag(&v(&["e"])).unwrap());
    assert!(speed16::lock_only_flag(&v(&["e", "--dip-probe-lock-only", "on"])).unwrap());
    assert!(!speed16::lock_only_flag(&v(&["e", "--dip-probe-lock-only", "off"])).unwrap());
    assert!(speed16::lock_only_flag(&v(&["e", "--dip-probe-lock-only", "1"])).is_err());
    assert_eq!(speed16::lock_cu(), 3_000, "default CU limit");
    let key = key_of(14);
    let user: Pk = key.verifying_key().to_bytes();
    let (hel, noz, jit) = (tip_accts(SendKind::Helius), tip_accts(SendKind::Nozomi), tip_accts(SendKind::JitoBundle));
    for i in 0..20u64 {
        let mut l = snipe_build::launch_from_target(rnd(i, 60), rnd(i, 61));
        if i % 2 == 0 { l.buyback_fee_recipient = rnd(i, 62); }
        let tips = [(hel[0], 1_000_000u64), (noz[0], 1_000_000), (jit[0], 1_000_000)];
        for (nt, ll) in [(3usize, None), (0, None), (1, Some(LL16))] {
            let ixs = speed16::lock_probe_ixs(user, &l, &tips[..nt], 3_000, 5_000_000, ll);
            let raw = build::sign(&build::compile_v0(user, &ixs, [7u8; 32], &[], &[]).unwrap(), &key);
            assert!(raw.len() <= 1232);
            let (tx, _) = arbx::tx::parse_wire(&raw).unwrap();
            let progs: std::collections::BTreeSet<Pk> = tx.ixs.iter().map(|ix| tx.keys[ix.program as usize]).collect();
            assert_eq!(progs, [[0u8; 32], arbx::tx::COMPUTE_BUDGET].into_iter().collect(), "only the System and ComputeBudget programs run");
            assert_eq!((tx.cu_limit, tx.cu_price_micro), (Some(3_000), Some(5_000_000)));
            // the System transfers: the tips, then the one 0-lamport self-transfer
            let sys: Vec<&arbx::tx::Ix> = tx.ixs.iter().filter(|ix| tx.keys[ix.program as usize] == [0u8; 32]).collect();
            assert_eq!(sys.len(), nt + 1);
            let lock = sys[nt];
            assert_eq!(lock.data, [&2u32.to_le_bytes()[..], &0u64.to_le_bytes()[..]].concat(), "Transfer of 0 lamports");
            let at = |k: usize| tx.keys[lock.accounts[k] as usize];
            assert_eq!((at(0), at(1)), (user, user), "wallet -> wallet");
            let want = speed16::lock_accounts(&l);
            assert_eq!((2..6).map(at).collect::<Vec<_>>(), want.to_vec());
            assert_eq!(at(6), *snipe::PUMP, "the pump program rides read-only (our feeds follow it)");
            // write locks: the wallet, the tips, exactly the buy's 4 non-wallet writable accounts; pump read-only
            let w: std::collections::BTreeSet<Pk> = tx.keys.iter().enumerate().filter(|(j, _)| tx.is_writable(*j)).map(|(_, k)| *k).collect();
            let mut want_w: std::collections::BTreeSet<Pk> = want.into_iter().chain([user]).collect();
            for (t, _) in &tips[..nt] { want_w.insert(*t); }
            assert_eq!(w, want_w);
            // the buy write-locks the same 4 (plus the wallet's own accounts)
            let (b, _) = build_buy_spend_ll(user, &l, None, 550_000_000, 1, None);
            let bw: std::collections::BTreeSet<Pk> = b.iter().flat_map(|ix| ix.accounts.iter().filter(|a| a.writable).map(|a| a.key)).collect();
            assert!(want.iter().all(|k| bw.contains(k)), "the buy write-locks every account the probe locks");
            assert_eq!(send::tip_paid(&tx, &hel), if nt >= 1 { 1_000_000 } else { 0 });
            if nt == 3 {
                send::verify_copy(&raw, SendKind::Helius, &hel, "helius").unwrap();
                send::verify_copy(&raw, SendKind::Nozomi, &noz, "nozomi").unwrap();
                send::verify_copy(&raw, SendKind::JitoBundle, &jit, "jito").unwrap();
            }
            match ll { Some(b) => assert!(is_ll(ixs.last().unwrap(), b)), None => assert!(!ixs.iter().any(|ix| ix.program == arbx::tx::COMPUTE_BUDGET && ix.data[0] == 4)) }
        }
    }
}

// ---- C1 measurement + C5 proof (read-only, by hand) -------------------------------------------------------------------

/// C1 MEASUREMENT + C5 PROOF (dip16; read-only, run by hand:
///   cargo test --release --bin snipe_engine dip16_loaded_data_sim_onchain -- --ignored --nocapture --test-threads 1
/// [DIP16_SIM_MINTS=mint,mint] [DIP16_SIM_LIMIT=bytes]). Our buy txs built exactly as the engine builds them (each route fan's multi-tip
/// tx, the largest 4-tip union, a durable-nonce variant, a can't-fill probe, a pre-send attempt) on live pump tokens, simulated with
/// sigVerify off (NOTHING is sent; RPC ~/.config/sniper/ck_rpc_url, never printed; <= 4 calls a second; the slot guard in the live
/// engines' verified encoding). The node's loadedAccountsDataSize (SIMD-0186: 64 + data bytes per account key, + the programdata of
/// every upgradeable program among them), then the same tx with C1's SetLoadedAccountsDataSizeLimit appended as the engine does: at
/// exactly that size (must load), one byte less (must fail MaxLoadedAccountsDataSizeExceeded) and at DIP16_SIM_LIMIT (default 16 MiB);
/// the CU each consumed; the per-account breakdown of the first token. C5: the lock-only probe (3 tips; tipless) on the same curves:
/// err null, only System + ComputeBudget invoked, the curve accounts byte-identical after it, the wallet down by exactly fee + tips
#[test]
#[ignore]
fn dip16_loaded_data_sim_onchain() {
    let home = std::env::var("HOME").unwrap();
    let url = std::fs::read_to_string(format!("{home}/.config/sniper/ck_rpc_url")).expect("~/.config/sniper/ck_rpc_url").trim().to_string();
    let rec_limit: u32 = std::env::var("DIP16_SIM_LIMIT").ok().and_then(|x| x.parse().ok()).unwrap_or(16 << 20);
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build().unwrap();
    rt.block_on(async move {
        let rpc = rpc::Rpc::new(url);
        let last = std::sync::Mutex::new(Instant::now() - Duration::from_secs(1));
        let ncalls = std::sync::atomic::AtomicU64::new(0);
        // <= 4 calls a second (the owner's cap: 5)
        let call = |m: &'static str, p: serde_json::Value| { let (rpc, last, ncalls) = (&rpc, &last, &ncalls); async move {
            let wait = { let g = last.lock().unwrap(); Duration::from_millis(260).saturating_sub(g.elapsed()) };
            tokio::time::sleep(wait).await;
            *last.lock().unwrap() = Instant::now();
            ncalls.fetch_add(1, Ordering::Relaxed);
            rpc.call(m, p).await
        } };
        let user = pk("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE");
        let key = SigningKey::from_bytes(&[42u8; 32]); // not the wallet's key: sigVerify is off, nothing is sent
        // simulate; `post`: accounts whose state after the tx the node returns
        let sim = |ixs: Vec<build::Ix>, bh: [u8; 32], post: Vec<String>| { let (call, key) = (&call, &key); async move {
            let raw = build::sign(&build::compile_v0(user, &ixs, bh, &[], &[]).unwrap(), key);
            let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
            let mut opts = serde_json::json!({ "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed" });
            if !post.is_empty() { opts["accounts"] = serde_json::json!({ "addresses": post, "encoding": "base64" }); }
            let v = call("simulateTransaction", serde_json::json!([b64, opts])).await;
            let v = v.unwrap_or_else(|e| serde_json::json!({"value": {"err": format!("rpc: {}", redact(&format!("{e:#}")))}}));
            (v["value"].clone(), raw.len())
        } };
        let slot = call("getSlot", serde_json::json!([{ "commitment": "processed" }])).await.unwrap().as_u64().unwrap();
        println!("C1/C5 SIM as {} at slot {slot} (its signature is not checked; nothing is sent)", b58(&user));
        // live pump tokens: DIP16_SIM_MINTS, else the mints of the newest pump trades
        let mut cands: Vec<Pk> = std::env::var("DIP16_SIM_MINTS").ok().map(|s| s.split(',').filter(|x| !x.trim().is_empty()).map(|x| pk(x.trim())).collect()).unwrap_or_default();
        if cands.is_empty() {
            let sg = call("getSignaturesForAddress", serde_json::json!([b58(&snipe::PUMP), { "limit": 40, "commitment": "confirmed" }])).await.unwrap();
            for x in sg.as_array().into_iter().flatten().filter(|x| x["err"].is_null()).take(14) {
                if cands.len() >= 10 { break; }
                let Ok(t) = call("getTransaction", serde_json::json!([x["signature"], { "encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed" }])).await else { continue };
                let logs: Vec<String> = t["meta"]["logMessages"].as_array().map(|a| a.iter().filter_map(|y| y.as_str().map(String::from)).collect()).unwrap_or_default();
                for e in arbx::dip::trade_events(&logs) { if !cands.contains(&e.mint) { cands.push(e.mint); } }
            }
        }
        let (hel, noz, jit, bolt) = (tip_accts(SendKind::Helius), tip_accts(SendKind::Nozomi), tip_accts(SendKind::JitoBundle), tip_accts(SendKind::Bolt));
        let fans: Vec<(&str, Vec<(Pk, u64)>)> = vec![
            ("jito  helius+nozomi+jito", vec![(hel[0], 1_000_000), (noz[0], 1_000_000), (jit[0], 1_000_000)]),
            ("bam   nozomi+helius-swqos+bolt", vec![(noz[1], 1_000_000), (hel[1], 200_000), (bolt[0], 1_000_000)]),
            ("union helius+nozomi+jito+bolt", vec![(hel[2], 1_000_000), (noz[2], 1_000_000), (jit[2], 1_000_000), (bolt[1], 1_000_000)]),
        ];
        // one of the FRA wallet's durable nonces (create_with_seed(wallet, "dip-nonce-0", System)), when it exists
        let (nonce, _) = build::create_nonce_ixs(user, &format!("{}{}", noncefan::SEED, 0), 0);
        let na = call("getAccountInfo", serde_json::json!([b58(&nonce), { "encoding": "base64", "commitment": "confirmed" }])).await.unwrap();
        let nonce_val: Option<[u8; 32]> = na["value"]["data"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok()).filter(|d| d.len() == 80)
            .map(|d| d[40..72].try_into().unwrap());
        println!("nonce account {} {}", b58(&nonce), if nonce_val.is_some() { "found (the variant shape is simulated)" } else { "not found (no nonce shape)" });
        let spend = 100_000_000u64;
        let (mut all_l, mut n_tok, mut first, mut c5_ok) = (Vec::<u64>::new(), 0, true, 0);
        let exceeded = |e: &serde_json::Value| e.as_str() == Some("MaxLoadedAccountsDataSizeExceeded");
        for mint in &cands {
            if n_tok >= 5 { break; }
            let bc = snipe_build::bonding_curve(mint);
            let ai = call("getAccountInfo", serde_json::json!([b58(&bc), { "encoding": "base64", "commitment": "processed" }])).await.unwrap();
            let Some(d) = ai["value"]["data"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok()) else { continue };
            if d.len() < 49 || d[48] != 0 { continue; }
            let mi = call("getAccountInfo", serde_json::json!([b58(mint), { "encoding": "base64", "dataSlice": { "offset": 0, "length": 0 } }])).await.unwrap();
            if mi["value"]["owner"].as_str() != Some("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb") { continue; }
            n_tok += 1;
            let l = snipe_build::launch_from_target(*mint, *mint);
            println!("\n=== {} (mint {} B, curve {} B, {:.2} SOL)", b58(mint), mi["value"]["space"], d.len(), u64::from_le_bytes(d[16..24].try_into().unwrap()) as f64 / 1e9);
            let dl = slot + 60;
            let mut shapes: Vec<(String, Vec<build::Ix>, [u8; 32])> = Vec::new();
            for (name, tips) in &fans {
                let (ixs, _) = build_buy_spend_ll(user, &l, None, spend, 1, None);
                let mut v: Vec<build::Ix> = tips.iter().map(|(t, a)| build::transfer_ix(user, *t, *a)).collect();
                v.extend(insert_guard(ixs, G_LIVE, dl));
                if tips.len() > 2 { lat::bump_cu_limit(&mut v, 300 * (tips.len() as u32 - 2)); }
                shapes.push((format!("buy {name}"), v, [7u8; 32]));
            }
            {
                let (ixs, _) = build_buy_spend_ll(user, &l, None, spend, u64::MAX, None);
                let mut v: Vec<build::Ix> = fans[0].1.iter().map(|(t, a)| build::transfer_ix(user, *t, *a)).collect();
                v.extend(insert_guard(ixs, G_LIVE, dl));
                if fans[0].1.len() > 2 { lat::bump_cu_limit(&mut v, 300 * (fans[0].1.len() as u32 - 2)); }
                shapes.push(("probe (min_out MAX) jito fan".into(), v, [7u8; 32]));
            }
            if let Some(nv) = nonce_val {
                shapes.push(("nonce variant nozomi tip".into(), fastfire::nonce_variant_ixs_ll(user, &l, nonce, Some((noz[3], 1_000_000)), spend, 1, Some((G_LIVE, dl)), None), nv));
                shapes.push(("nonce variant tipless".into(), fastfire::nonce_variant_ixs_ll(user, &l, nonce, None, spend, 1, Some((G_LIVE, dl)), None), nv));
            }
            shapes.push(("pre-send attempt helius tip".into(), arbx::presend_live::attempt_ixs(user, &l, spend, 1, 120_000, 1_000, guard_ix_enc(G_LIVE, dl), Some((hel[3], 200_000))).0, [7u8; 32]));
            for (name, ixs, bh) in &shapes {
                let (v0, n0) = sim(ixs.clone(), *bh, vec![]).await;
                let Some(lsz) = v0["loadedAccountsDataSize"].as_u64() else { println!("  {name:34} no loadedAccountsDataSize (err {})", v0["err"]); continue };
                all_l.push(lsz);
                // C1 exactly as the engine adds it: appended LAST
                let with = |b: u32| { let mut x = ixs.clone(); speed16::add_ll(&mut x, Some(b)); x };
                let (v1, n1) = sim(with(lsz as u32), *bh, vec![]).await;
                let (v2, _) = sim(with(lsz as u32 - 1), *bh, vec![]).await;
                let (v3, _) = sim(with(rec_limit), *bh, vec![]).await;
                println!("  {name:34} loaded {lsz:>9} B ({:.3} MiB) | {n0} B tx, CU {}, err {} | limit=exact: err {}, CU {}, {n1} B tx | limit-1: {} | limit {rec_limit}: {} (CU {})",
                    lsz as f64 / 1048576.0, v0["unitsConsumed"], v0["err"], v1["err"], v1["unitsConsumed"],
                    if exceeded(&v2["err"]) { "MaxLoadedAccountsDataSizeExceeded (as expected)".to_string() } else { format!("UNEXPECTED {}", v2["err"]) },
                    if exceeded(&v3["err"]) { "EXCEEDED".to_string() } else { format!("loads, err {}", v3["err"]) }, v3["unitsConsumed"]);
                if !v0["err"].is_null() { println!("      logs: {:?}", v0["logs"].as_array().map(|a| a.iter().rev().take(3).cloned().collect::<Vec<_>>())); }
            }
            // C5 PROOF on this curve: the lock-only probe (the jito fan's 3 tips; and tipless) moves nothing but the fee and its tips
            for (name, tips) in [("lock-only probe 3 tips", fans[0].1.clone()), ("lock-only probe tipless", vec![])] {
                let ixs = speed16::lock_probe_ixs(user, &l, &tips, 3_000, 5_000_000, Some(rec_limit));
                let watch: Vec<Pk> = speed16::lock_accounts(&l).into_iter().chain([user]).collect();
                let ws: Vec<String> = watch.iter().map(b58).collect();
                let pre = call("getMultipleAccounts", serde_json::json!([ws, { "encoding": "base64", "commitment": "processed" }])).await.unwrap();
                let (v, n) = sim(ixs.clone(), [7u8; 32], ws.clone()).await;
                let post_read = call("getMultipleAccounts", serde_json::json!([ws, { "encoding": "base64", "commitment": "processed" }])).await.unwrap();
                // an account that does not exist reads null and simulates as an empty System account: the same state
                let st = |x: Option<&serde_json::Value>| -> (u64, String, String) { match x.filter(|a| !a.is_null()) {
                    Some(a) => (a["lamports"].as_u64().unwrap_or(0), a["data"][0].as_str().unwrap_or("").to_string(), a["owner"].as_str().unwrap_or("").to_string()),
                    None => (0, String::new(), "11111111111111111111111111111111".to_string()) } };
                let (pre_v, post_v, sim_v) = (pre["value"].as_array().cloned().unwrap_or_default(), post_read["value"].as_array().cloned().unwrap_or_default(),
                    v["accounts"].as_array().cloned().unwrap_or_default());
                // the token's own curve accounts (curve, its token account, its WSOL account): byte-identical before / in the simulation's post
                // state, conclusive when nobody traded the token between the two reads
                let quiet = (0..3).all(|k| st(pre_v.get(k)) == st(post_v.get(k)));
                let same = (0..3).all(|k| st(pre_v.get(k)) == st(sim_v.get(k)));
                // the buyback fee recipient is shared by every pump buy (fees only flow IN between the reads): its data and owner identical,
                // its lamports between the two reads
                let (bp, bs, bq) = (st(pre_v.get(3)), st(sim_v.get(3)), st(post_v.get(3)));
                let bb_ok = bp.1 == bs.1 && bp.2 == bs.2 && bp.0 <= bs.0 && bs.0 <= bq.0;
                let fee = 5_000 + (3_000u64 * 5_000_000).div_ceil(1_000_000);
                let tipsum: u64 = tips.iter().map(|t| t.1).sum();
                let (ub, ua) = (Some(st(pre_v.get(4)).0), Some(st(sim_v.get(4)).0));
                let progs: std::collections::BTreeSet<String> = v["logs"].as_array().into_iter().flatten().filter_map(|x| x.as_str())
                    .filter_map(|x| x.strip_prefix("Program ").and_then(|r| r.split(' ').nth(1).filter(|w| *w == "invoke").map(|_| r.split(' ').next().unwrap().to_string()))).collect();
                let ok = v["err"].is_null() && (same || !quiet) && bb_ok && ub.zip(ua).is_some_and(|(b, a)| b - a == fee + tipsum)
                    && progs.iter().all(|p| p == "11111111111111111111111111111111" || p == "ComputeBudget111111111111111111111111111111");
                if ok && quiet { c5_ok += 1; }
                println!("  {name:34} {n} B tx, err {}, CU {}, loaded {} B | programs run {progs:?} | curve accounts {} | buyback vault {} | wallet {} lamports (fee {fee} + tips {tipsum}) | {}",
                    v["err"], v["unitsConsumed"], v["loadedAccountsDataSize"],
                    if !quiet { "traded meanwhile (inconclusive)".to_string() } else if same { "byte-identical after the probe".to_string() } else { "CHANGED".to_string() },
                    if bb_ok { "same data, lamports only from others' fees" } else { "CHANGED" },
                    ub.zip(ua).map(|(b, a)| format!("-{}", b as i64 - a as i64)).unwrap_or_else(|| "?".into()), if ok { "OK" } else { "FAILED" });
            }
            // the per-account breakdown (SIMD-0186) of the first token's jito-fan buy: which accounts the size comes from
            if first {
                first = false;
                let raw = build::sign(&build::compile_v0(user, &shapes[0].1, [7u8; 32], &[], &[]).unwrap(), &key);
                let (tx, _) = arbx::tx::parse_wire(&raw).unwrap();
                let keys: Vec<String> = tx.keys.iter().map(b58).collect();
                let ma = call("getMultipleAccounts", serde_json::json!([keys, { "encoding": "base64", "dataSlice": { "offset": 0, "length": 36 } }])).await.unwrap();
                let mut parts: Vec<(u64, String)> = Vec::new();
                let mut pd: Vec<(String, String)> = Vec::new();
                for (k, a) in keys.iter().zip(ma["value"].as_array().cloned().unwrap_or_default()) {
                    let space = a["space"].as_u64().unwrap_or(0);
                    parts.push((64 + space, format!("{k} owner {} ({} B data)", a["owner"].as_str().unwrap_or("-"), space)));
                    if a["owner"].as_str() == Some("BPFLoaderUpgradeab1e11111111111111111111111") {
                        if let Some(d) = a["data"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok()).filter(|d| d.len() == 36 && d[0] == 2) {
                            pd.push((b58(&d[4..36].try_into().unwrap()), k.clone()));
                        }
                    }
                }
                if !pd.is_empty() {
                    let ks: Vec<String> = pd.iter().map(|x| x.0.clone()).collect();
                    let mp = call("getMultipleAccounts", serde_json::json!([ks, { "encoding": "base64", "dataSlice": { "offset": 0, "length": 0 } }])).await.unwrap();
                    for ((p, prog), a) in pd.iter().zip(mp["value"].as_array().cloned().unwrap_or_default()) {
                        let space = a["space"].as_u64().unwrap_or(0);
                        parts.push((64 + space, format!("{p} = programdata of {prog} ({space} B data)")));
                    }
                }
                parts.sort_by(|a, b| b.0.cmp(&a.0));
                let sum: u64 = parts.iter().map(|x| x.0).sum();
                println!("  breakdown of the jito-fan buy (64 + data per account, SIMD-0186): sum {sum} B");
                for (b, s) in parts.iter().take(8) { println!("    {b:>9}  {s}"); }
                // the engine's own start-up check on the same node
                println!("  start-up check: {}", speed16::ll_verify(&rpc, rec_limit).await.map_err(|e| format!("{e:#}")).unwrap_or_else(|e| format!("REFUSED: {e}")));
            }
        }
        all_l.sort_unstable();
        println!("\nC1 SUMMARY: {} buy sims on {n_tok} tokens; loaded bytes min {:?} max {:?} | C5: {c5_ok} conclusive lock-probe proofs | RPC calls {}", all_l.len(), all_l.first(), all_l.last(),
            ncalls.load(Ordering::Relaxed));
        assert!(!all_l.is_empty(), "nothing measured");
    });
}

// ---- Glaive (dip16, coordinator 10-25 ~20:15 PKT): a config-only send kind ------------------------------------------------

/// Glaive on the FAST path: a raw-bytes kind (fastfire::bin_kind), so our own HTTP/1.1 connection writes `POST /binary?api-key=<key>`,
/// Content-Type application/octet-stream, the signed bytes as the body (as the async path: send::tests::glaive_posts_raw_bytes_...),
/// and its keep-alive is GET /health. A local listener stands in for glaive.trade (nothing leaves the machine)
#[test]
fn dip16_glaive_fast_path_request() {
    use std::io::Read as _;
    assert!(fastfire::bin_kind(SendKind::Glaive) && !fastfire::json_kind(SendKind::Glaive));
    let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
    let port = l.local_addr().unwrap().port();
    let (atx, _arx) = crossbeam_channel::unbounded();
    let stop = Arc::new(AtomicBool::new(false));
    let c = arbx::fast::FastConn::start("glaive-test", &format!("http://127.0.0.1:{port}/binary?api-key=KEY-123"), "application/octet-stream", &[],
        Some((true, format!("http://127.0.0.1:{port}/health"))), atx, stop.clone()).unwrap();
    let (mut s, _) = l.accept().unwrap();
    let t = Instant::now();
    while !c.up.load(Ordering::Acquire) && t.elapsed() < Duration::from_secs(3) { std::thread::sleep(Duration::from_millis(5)); }
    let raw: Vec<u8> = (0..700u32).map(|i| (i * 13) as u8).collect();
    let mut req = Vec::new();
    c.frame(&raw, &mut req);
    c.write_req(&req, 9).unwrap();
    s.set_read_timeout(Some(Duration::from_secs(2))).unwrap();
    let (mut got, mut buf) = (Vec::new(), [0u8; 4096]);
    while got.len() < req.len() { let n = s.read(&mut buf).unwrap(); if n == 0 { break; } got.extend_from_slice(&buf[..n]); }
    stop.store(true, Ordering::Relaxed);
    let he = got.windows(4).position(|w| w == b"\r\n\r\n").unwrap();
    let head = String::from_utf8_lossy(&got[..he]).to_string();
    assert!(head.starts_with("POST /binary?api-key=KEY-123 HTTP/1.1\r\n"), "{head}");
    assert!(head.contains("Content-Type: application/octet-stream\r\n") && head.ends_with(&format!("Content-Length: {}", raw.len())), "{head}");
    assert_eq!(&got[he + 4..], &raw[..], "the body is the signed bytes, nothing else");
}

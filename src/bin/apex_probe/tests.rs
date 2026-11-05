//! apex_probe tests: PDAs, instruction bytes vs our REAL landed pump buy + sell (AMS PROD run 48), caps + refusals, the
//! gate, watchlist formats, guard prices, copies (multi-tip + nonce), routes, the position analysis, and a replay of
//! recorded launches (testdata sample, + the collector's full file when it is on this machine).

use super::logic::*;
use super::*;
use arbx::tx::{parse_wire, pk};

fn real(kind: &str) -> (arbx::tx::Tx, Vec<u8>) {
    let j: serde_json::Value = serde_json::from_str(include_str!("testdata/real_buy_sell.json")).unwrap();
    let wire = base64::engine::general_purpose::STANDARD.decode(j[kind]["wire_b64"].as_str().unwrap()).unwrap();
    let (tx, _) = parse_wire(&wire).expect("parse_wire");
    (tx, wire)
}

/// (keys, writable, signer, data) of the top-level ix of `program` in a parsed tx
fn ix_of(tx: &arbx::tx::Tx, program: &Pk) -> (Vec<Pk>, Vec<bool>, Vec<bool>, Vec<u8>) {
    let ix = tx.ixs.iter().find(|ix| tx.keys[ix.program as usize] == *program).expect("ix");
    let keys = ix.accounts.iter().map(|&i| tx.keys[i as usize]).collect();
    let w = ix.accounts.iter().map(|&i| tx.is_writable(i as usize)).collect();
    let s = ix.accounts.iter().map(|&i| (i as usize) < tx.num_signers as usize).collect();
    (keys, w, s, ix.data.clone())
}

fn ours(ix: &build::Ix) -> (Vec<Pk>, Vec<bool>, Vec<bool>, Vec<u8>) {
    (ix.accounts.iter().map(|m| m.key).collect(), ix.accounts.iter().map(|m| m.writable).collect(), ix.accounts.iter().map(|m| m.signer).collect(), ix.data.clone())
}

fn u64_at(d: &[u8], o: usize) -> u64 { u64::from_le_bytes(d[o..o + 8].try_into().unwrap()) }

#[test]
fn pda_constants() {
    assert_eq!(b58(&snipe_build::GLOBAL), "4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf");
    assert_eq!(b58(&snipe_build::EVENT_AUTHORITY), "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1");
    assert_eq!(b58(&snipe_build::FEE_CONFIG), "8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt");
}

#[test]
fn pda_bonding_curve_matches_250_recorded_launches() {
    let mut n = 0;
    for l in include_str!("testdata/launches_sample.jsonl").lines() {
        let r: serde_json::Value = serde_json::from_str(l).unwrap();
        let (Some(m), Some(bc)) = (r["mint"].as_str(), r["bonding_curve"].as_str()) else { continue };
        assert_eq!(b58(&snipe_build::bonding_curve(&pk(m))), bc, "mint {m}");
        n += 1;
    }
    assert!(n >= 200, "{n}");
}

/// our builder vs OUR OWN landed buy (buy_exact_quote_in_v3, AMS run 48): the 17 accounts (keys, writable, signer) and the
/// 25 data bytes are identical; the user ATA, WSOL ATA, user volume accumulator and curve ATAs are derived locally
#[test]
fn buy_ix_bytes_match_real_landed_buy() {
    let (tx, _) = real("buy");
    let (keys, w, s, data) = ix_of(&tx, &snipe::PUMP);
    assert_eq!(data[..8], snipe_build::BUY_EXACT_QUOTE_IN_V3_DISC);
    let user = tx.keys[0];
    let mut l = snipe_build::launch_from_target(keys[1], user);
    l.buyback_fee_recipient = keys[13];
    assert_eq!(l.bonding_curve, keys[5], "bonding curve derived from the mint");
    let ix = snipe_build::buy_ix(user, &l, u64_at(&data, 8), u64_at(&data, 16), true);
    assert_eq!(ours(&ix), (keys, w, s, data), "buy ix differs from the real landed one");
    // and the full list our probe sends has the same buy + ATA creates for the same accounts (T22 base, legacy WSOL). The real
    // tx is a PRE-SEND variant: its base ATA is a plain Create (0); the probe uses CreateIdempotent (1), as the reactive engine
    let mine = buy_ixs(user, &l, u64_at(&ix.data, 8), u64_at(&ix.data, 16), 100_000, 5_000_000, None, &[], Some((GUARD_DEFAULT, 1)));
    let atas: Vec<&build::Ix> = mine.iter().filter(|x| x.program == *pda::ATA_PROGRAM).collect();
    let real_atas: Vec<&arbx::tx::Ix> = tx.ixs.iter().filter(|x| tx.keys[x.program as usize] == *pda::ATA_PROGRAM).collect();
    assert_eq!(atas.len(), 2);
    assert_eq!(real_atas.len(), 2);
    for (a, b) in atas.iter().zip(&real_atas) {
        assert_eq!(a.accounts.iter().map(|m| m.key).collect::<Vec<_>>(), b.accounts.iter().map(|&i| tx.keys[i as usize]).collect::<Vec<_>>());
        assert_eq!(a.data, vec![1u8], "ours: CreateIdempotent");
        assert!(b.data == vec![0u8] || b.data == vec![1u8]);
    }
    assert_eq!(real_atas[1].data, vec![1u8], "the WSOL ATA create is idempotent in both");
}

/// the slot guard: our encoding == the guard ix in the real landed buy (Lighthouse, right before the pump buy)
#[test]
fn guard_ix_matches_real_landed_buy() {
    let (tx, _) = real("buy");
    let gi = tx.ixs.iter().position(|ix| tx.keys[ix.program as usize] == *LIGHTHOUSE).expect("guard in the real buy");
    let bi = tx.ixs.iter().position(|ix| tx.keys[ix.program as usize] == *snipe::PUMP).unwrap();
    assert!(gi < bi, "guard before the buy (the pre-send variant puts it before its ATA creates)");
    let real_ix = &tx.ixs[gi];
    let dl = u64_at(&real_ix.data, 3);
    let j: serde_json::Value = serde_json::from_str(include_str!("testdata/real_buy_sell.json")).unwrap();
    assert_eq!(dl, j["buy"]["slot"].as_u64().unwrap() + 1, "deadline = its landing slot + 1");
    let g = GuardEnc { disc: real_ix.data[0], op: *real_ix.data.last().unwrap(), acct: !real_ix.accounts.is_empty() };
    assert_eq!(g, GUARD_DEFAULT);
    assert_eq!(guard_ix(g, dl).data, real_ix.data);
    // our list puts it right before the buy too
    let l = snipe_build::launch_from_target([1u8; 32], [2u8; 32]);
    let v = buy_ixs([3u8; 32], &l, 1, 1, 100_000, 1, None, &[([4u8; 32], 5)], Some((g, dl)));
    let gp = v.iter().position(|x| x.program == *LIGHTHOUSE).unwrap();
    assert_eq!(v[gp + 1].program, *snipe::PUMP);
    assert_eq!(v[0].program, *pda::SYSTEM_PROGRAM, "tips first (no nonce)");
}

/// our builder vs OUR OWN landed sell (sell_v3, AMS run 48)
#[test]
fn sell_ix_bytes_match_real_landed_sell() {
    let (tx, _) = real("sell");
    let (keys, w, s, data) = ix_of(&tx, &snipe::PUMP);
    assert_eq!(data[..8], snipe_build::SELL_V3_DISC);
    let user = tx.keys[0];
    let mut l = snipe_build::launch_from_target(keys[1], user);
    l.buyback_fee_recipient = keys[13];
    let ix = snipe_build::sell_ix(user, &l, u64_at(&data, 8), u64_at(&data, 16));
    assert_eq!(ours(&ix), (keys, w, s, data), "sell ix differs from the real landed one");
    // our full sell: CU limit, CU price, [tips], sell, close the base ATA (T22)
    let v = sell_ixs(user, &l, 5, 0, 120_000, 5_000_000, &[([7u8; 32], 1000)]);
    assert_eq!(v.len(), 5);
    assert_eq!(v[2].program, *pda::SYSTEM_PROGRAM);
    assert_eq!(v[3].data[..8], snipe_build::SELL_V3_DISC);
    assert_eq!(v[4].program, *pda::TOKEN_2022);
    assert_eq!(v[4].accounts[0].key, snipe_build::assoc_user(&user, &l.mint));
}

/// a real create_v2 (tests/fixtures, read only) -> detect -> our signed buy parses back with the create's accounts
#[test]
fn real_create_detect_and_build() {
    let wire = base64::engine::general_purpose::STANDARD.decode(include_str!("../../../tests/fixtures/create_v2.b64").trim()).unwrap();
    let (tx, _) = parse_wire(&wire).unwrap();
    assert!(snipe::is_create_candidate(&tx));
    let l = snipe::detect_launch(&tx).unwrap();
    assert_eq!(b58(&l.mint), "7oeUduY1zhUwQ3YdSP9CGDYF8nYzfRdhgqtc6wAbpump");
    assert_eq!(skip_reason(&l, snipe::create_quote_mint(&tx).is_none(), false, false), None);
    let mut w = HashSet::new();
    w.insert(l.creator);
    assert!(!l.is_holder_reward);
    assert_eq!(event_creator(&l), l.creator);
    assert!(MatchOn::Creator.hit(&w, &event_creator(&l), &l.creator, tx.keys.first()));
    let key = SigningKey::from_bytes(&[9u8; 32]);
    let user = key.verifying_key().to_bytes();
    let exp = expected_tokens(l.dev_buy_lamports, 50_000_000);
    let c = BuyCfg { user, spend: 50_000_000, min_out: buy_min_out(exp, 0.2), cu_limit: 100_000, cu_price: 5_000_000, guard: Some((GUARD_DEFAULT, 456491125)) };
    let groups = vec![(Some(([11u8; 32], 1_000_000)), vec![0usize, 1]), (Some(([12u8; 32], 200_000)), vec![2usize]), (None, vec![3usize])];
    let cp = build_copies(&key, &c, &l, [5u8; 32], None, &groups).unwrap();
    assert_eq!(cp.len(), 1);
    assert_eq!(cp[0].paths, vec![0, 1, 2, 3]);
    assert_eq!(cp[0].tip, 1_200_000);
    let (p, _) = parse_wire(&cp[0].raw).unwrap();
    assert_eq!(p.sig, cp[0].sig);
    let (k, _, _, d) = ix_of(&p, &snipe::PUMP);
    assert_eq!(k[1], l.mint);
    assert_eq!(k[5], l.bonding_curve);
    assert_eq!(k[6], l.assoc_bonding_curve);
    assert_eq!(u64_at(&d, 8), 50_000_000);
    assert_eq!(u64_at(&d, 16), c.min_out);
    use ed25519_dalek::Verifier;
    let msg = &cp[0].raw[65..];
    assert!(key.verifying_key().verify(msg, &ed25519_dalek::Signature::from_bytes(&cp[0].sig)).is_ok());
}

#[test]
fn copies_multitip_and_nonce_variants() {
    let key = SigningKey::from_bytes(&[1u8; 32]);
    let user = key.verifying_key().to_bytes();
    let l = snipe_build::launch_from_target([0x5Au8; 32], [0x6Bu8; 32]);
    let c = BuyCfg { user, spend: 50_000_000, min_out: 7, cu_limit: 100_000, cu_price: 5_000_000, guard: Some((GUARD_DEFAULT, 100)) };
    // 8 tipped groups: the multi-tip tx must still fit (paths dropped from the end until it does)
    let groups: Vec<(Option<(Pk, u64)>, Vec<usize>)> = (0..8).map(|i| (Some(([20 + i as u8; 32], 1_000_000)), vec![i])).collect();
    let cp = build_copies(&key, &c, &l, [5u8; 32], None, &groups).unwrap();
    assert_eq!(cp.len(), 1);
    assert!(cp[0].raw.len() <= 1232);
    let (p, _) = parse_wire(&cp[0].raw).unwrap();
    let tips = p.ixs.iter().filter(|ix| p.keys[ix.program as usize] == *pda::SYSTEM_PROGRAM && ix.data[..4] == [2, 0, 0, 0]).count();
    assert_eq!(tips, cp[0].paths.len());
    // nonce: one variant per group, AdvanceNonce first, exactly one tip each, the nonce value as the blockhash, different sigs
    let nacct = [77u8; 32];
    let nv = [88u8; 32];
    let g3 = vec![(Some(([20u8; 32], 1_000_000)), vec![0usize, 1]), (Some(([21u8; 32], 200_000)), vec![2usize]), (None, vec![3usize])];
    let vs = build_copies(&key, &c, &l, [5u8; 32], Some((nacct, nv)), &g3).unwrap();
    assert_eq!(vs.len(), 3);
    let mut sigs = HashSet::new();
    for (v, (tip, idx)) in vs.iter().zip(&g3) {
        assert!(sigs.insert(v.sig));
        assert_eq!(&v.paths, idx);
        let (p, _) = parse_wire(&v.raw).unwrap();
        let first = &p.ixs[0];
        assert_eq!(p.keys[first.program as usize], *pda::SYSTEM_PROGRAM);
        assert_eq!(first.data, 4u32.to_le_bytes().to_vec(), "AdvanceNonceAccount first");
        assert_eq!(p.keys[first.accounts[0] as usize], nacct);
        let n_tips = p.ixs.iter().filter(|ix| p.keys[ix.program as usize] == *pda::SYSTEM_PROGRAM && ix.data.len() == 12 && ix.data[..4] == [2, 0, 0, 0]).count();
        assert_eq!(n_tips, tip.is_some() as usize);
        // the message's recent blockhash = the nonce value
        let m = &v.raw[65..];
        let nk = m[4] as usize; // v0 prefix byte, 3 header bytes, then the key count (< 128)
        assert_eq!(&m[5 + 32 * nk..5 + 32 * nk + 32], &nv);
        let gp = p.ixs.iter().position(|ix| p.keys[ix.program as usize] == *LIGHTHOUSE).unwrap();
        assert_eq!(p.keys[p.ixs[gp + 1].program as usize], *snipe::PUMP);
    }
}

fn args(live: bool) -> CapArgs {
    CapArgs { live, size_sol: 0.05, max_buys: 20, max_spend_sol: 1.5, kill_below_sol: Some(10.0), max_runtime_min: Some(60.0), max_open: 1, buy_guard: 0.2, sell_guard: 0.5, hold_ms: 2000 }
}

#[test]
fn caps_refusals() {
    assert!(validate_caps(&args(true)).is_ok());
    let c = validate_caps(&args(true)).unwrap();
    assert_eq!(c.size, 50_000_000);
    assert_eq!(c.max_spend, 1_500_000_000);
    assert_eq!(c.kill_below, Some(10_000_000_000));
    assert!(validate_caps(&CapArgs { size_sol: 0.26, ..args(true) }).unwrap_err().contains("0.25"));
    assert!(validate_caps(&CapArgs { size_sol: 0.0, ..args(true) }).is_err());
    assert!(validate_caps(&CapArgs { size_sol: f64::NAN, ..args(true) }).is_err());
    assert!(validate_caps(&CapArgs { max_buys: 0, ..args(true) }).is_err());
    assert!(validate_caps(&CapArgs { max_spend_sol: 6.0, ..args(true) }).is_err());
    assert!(validate_caps(&CapArgs { max_spend_sol: 0.05, ..args(true) }).unwrap_err().contains("below one buy"));
    assert!(validate_caps(&CapArgs { kill_below_sol: None, ..args(true) }).unwrap_err().contains("--kill-below"));
    assert!(validate_caps(&CapArgs { max_runtime_min: None, ..args(true) }).unwrap_err().contains("--max-runtime-min"));
    assert!(validate_caps(&CapArgs { kill_below_sol: Some(-1.0), ..args(true) }).is_err());
    assert!(validate_caps(&CapArgs { buy_guard: 1.5, ..args(true) }).is_err());
    assert!(validate_caps(&CapArgs { max_open: 4, ..args(true) }).is_err());
    assert!(validate_caps(&CapArgs { hold_ms: 10, ..args(true) }).is_err());
    // shadow: kill-below / runtime optional
    assert!(validate_caps(&CapArgs { kill_below_sol: None, max_runtime_min: None, ..args(false) }).is_ok());
}

#[test]
fn gate_logic() {
    let c = validate_caps(&args(true)).unwrap();
    let w = 60_000_000;
    let mut l = Ledger::default();
    let b = Some(12_000_000_000);
    assert_eq!(gate(&c, &l, w, true, b, 0, false), Gate::Go);
    assert_eq!(gate(&c, &l, w, true, b, 0, true), Gate::Skip("stopping"));
    assert_eq!(gate(&c, &l, w, true, b, 3600, false), Gate::Stop("max_runtime"));
    assert_eq!(gate(&c, &l, w, true, None, 0, false), Gate::Skip("balance_unknown"));
    assert_eq!(gate(&c, &l, w, true, Some(9_999_999_999), 0, false), Gate::Stop("kill_below"));
    assert_eq!(gate(&c, &l, w, true, Some(10_030_000_000), 0, false), Gate::Skip("would_cross_kill_below"));
    assert_eq!(gate(&c, &l, w, false, None, 0, false), Gate::Go, "shadow: no balance needed");
    l.open = 1; l.open_worst = w;
    assert_eq!(gate(&c, &l, w, true, b, 0, false), Gate::Skip("position_open"));
    l.open = 0; l.open_worst = 0; l.buys_fired = 20;
    assert_eq!(gate(&c, &l, w, true, b, 0, false), Gate::Stop("max_buys"));
    l.buys_fired = 3; l.realized = -1_450_000_000;
    assert_eq!(gate(&c, &l, w, true, b, 0, false), Gate::Stop("max_spend"));
    l.realized = -1_400_000_000;
    assert_eq!(gate(&c, &l, w, true, b, 0, false), Gate::Go, "1.40 + 0.06 <= 1.5");
    l.realized = 300_000_000; // profit does not raise the budget above max_spend, it just leaves the full budget
    assert_eq!(l.at_risk(), 0);
    l.open = 1; l.open_worst = 1_480_000_000;
    assert_eq!(gate(&c, &l, w, true, b, 0, false), Gate::Skip("max_spend_open"));
}

#[test]
fn worst_case_cost() {
    // 0.05 + 3 tips of 0.001 + 0.0005 prio + base + rents + 3 sells (0.001 tip + 0.0006 prio)
    let w = worst_cost(50_000_000, 3_000_000, 100_000, 5_000_000, 1_000_000, 120_000, 5_000_000, 3);
    assert_eq!(w, 50_000_000 + 3_000_000 + 500_000 + 5_000 + RENT_ALLOW + 3 * (1_000_000 + 600_000 + 5_000));
}

#[test]
fn watchlist_formats() {
    let a = "6TgN6S7q74s9zSaktKm4kqFRPTLhtQpFUXZvGib7fUmD";
    let b = "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR";
    assert_eq!(parse_watchlist(&format!("[\"{a}\", \"{b}\"]")).unwrap().len(), 2);
    assert_eq!(parse_watchlist(&format!("[{{\"creator\": \"{a}\", \"n\": 5, \"net\": 0.3}}, {{\"creator\": \"{b}\"}}]")).unwrap().len(), 2);
    assert_eq!(parse_watchlist(&format!("{{\"creators\": [\"{a}\"], \"built\": \"x\"}}")).unwrap().len(), 1);
    assert_eq!(parse_watchlist(&format!("{{\"watchlist\": [{{\"creator\": \"{a}\"}}]}}")).unwrap().len(), 1);
    assert_eq!(parse_watchlist(&format!("# list\n{a}\n\n{b}  # two\n{a}\n")).unwrap().len(), 2);
    assert_eq!(parse_watchlist("[]").unwrap().len(), 0);
    assert!(parse_watchlist("[\"notakey\"]").is_err());
    assert!(parse_watchlist(&format!("[{{\"wallet\": \"{a}\"}}]")).is_err());
    assert!(parse_watchlist("{\"x\": 1}").is_err());
    let w = parse_watchlist(&format!("[\"{a}\"]")).unwrap();
    let (ka, kb) = (pk(a), pk(b));
    // hit(watch, CreateEvent creator, args creator, signer)
    assert!(MatchOn::Creator.hit(&w, &ka, &kb, Some(&kb)));
    assert!(!MatchOn::Signer.hit(&w, &ka, &ka, Some(&kb)));
    assert!(MatchOn::Either.hit(&w, &kb, &kb, Some(&ka)));
    assert!(!MatchOn::Creator.hit(&w, &kb, &ka, Some(&ka)));
    assert!(MatchOn::Args.hit(&w, &kb, &ka, Some(&kb)));
    assert!(!MatchOn::Args.hit(&w, &ka, &kb, Some(&ka)));
    assert_eq!(MatchOn::Either.key(&w, &ka, &kb, Some(&ka)), Some(ka));
    assert!(MatchOn::parse("args").is_ok() && MatchOn::parse("event").is_err());
}

#[test]
fn guard_prices() {
    // fresh curve, no dev buy: 0.05 SOL buys ~ vt0 * net / (vq0 + net)
    let e0 = expected_tokens(0, 50_000_000);
    let net = net_of_fee(50_000_000);
    let approx = (snipe::CURVE_VT0 as f64) * net as f64 / (snipe::CURVE_VQ0 as f64 + net as f64);
    assert!((e0 as f64 - approx).abs() / approx < 1e-6, "{e0} vs {approx}");
    // a dev buy makes our tokens fewer
    let e2 = expected_tokens(2_000_000_000, 50_000_000);
    assert!(e2 < e0);
    // 20% guard: min_out = expected / 1.2 (price up to 1.2x)
    assert_eq!(buy_min_out(1_200_000, 0.2), 1_000_000);
    assert_eq!(buy_min_out(1_000, 0.0), 1_000);
    // sell: selling back what we bought on the same curve returns ~ the spend less two fees
    let vq = snipe::CURVE_VQ0 + net;
    let vt = (snipe::CURVE_VQ0 as u128 * snipe::CURVE_VT0 as u128 / vq as u128) as u64;
    let back = sell_expected(vq, vt, e0);
    let want = net_of_fee(net);
    assert!((back as f64 - want as f64).abs() / (want as f64) < 1e-4, "{back} vs {want}");
    assert_eq!(sell_min_out(1_000, 0.5), 500);
    assert_eq!(sell_expected(0, 0, 5), 0);
}

#[test]
fn skip_rules() {
    let mut l = snipe_build::launch_from_target([1u8; 32], [2u8; 32]);
    assert_eq!(skip_reason(&l, true, false, false), None);
    assert_eq!(skip_reason(&l, false, false, false), Some("non_sol_quote"));
    l.is_mayhem = true;
    assert_eq!(skip_reason(&l, true, false, false), Some("mayhem"));
    assert_eq!(skip_reason(&l, true, false, true), None);
    l.is_mayhem = false; l.creator_fee_bps = 30;
    assert_eq!(skip_reason(&l, true, false, false), Some("creator_fee"));
    l.creator_fee_bps = 0; l.is_create_v2 = false;
    assert_eq!(skip_reason(&l, true, false, false), Some("legacy_create"));
    assert_eq!(skip_reason(&l, true, true, false), None);
}

#[test]
fn routes_and_tips() {
    let m = parse_route_spec("v13").unwrap();
    assert_eq!(m["fd"][0], "0slot");
    assert_eq!(m.len(), 7);
    assert!(route_names(&m).contains(&"falcon-udp".to_string()));
    let m2 = parse_route_spec("bam=a+b+a;default=c").unwrap();
    assert_eq!(m2["bam"], vec!["a", "b"]);
    assert!(parse_route_spec("bam=a").is_err(), "needs default");
    assert!(parse_route_spec("mars=a;default=b").is_err());
    assert_eq!(class("HarmonicFiredancer"), "harmonic");
    assert_eq!(class("AgaveBam"), "bam");
    assert_eq!(class("JitoLabs"), "jito");
    assert_eq!(route_classes(Some("bam"), Some("jito"), true), vec!["bam", "jito"]);
    assert_eq!(route_classes(Some("harmonic"), Some("jito"), true), vec!["harmonic"]);
    assert_eq!(route_classes(Some("harmonic"), Some("jito"), false), vec!["harmonic", "jito"]);
    assert_eq!(route_classes(Some("bam"), None, true), vec!["bam"]);
    assert!(route_classes(None, None, true).is_empty());
    // tip groups: shared tip accounts = one family at the larger amount; tipless together
    let (a, b, c) = ([1u8; 32], [2u8; 32], [3u8; 32]);
    let fam: Vec<Pk> = vec![a, b];
    let other: Vec<Pk> = vec![c];
    let none: Vec<Pk> = vec![];
    let g = tip_groups(&[(Some((a, 1_000_000)), &fam[..]), (None, &none[..]), (Some((b, 2_000_000)), &fam[..]), (Some((c, 200_000)), &other[..]), (Some((c, 0)), &other[..])]);
    assert_eq!(g, vec![(Some((a, 2_000_000)), vec![0, 2]), (None, vec![1, 4]), (Some((c, 200_000)), vec![3])]);
}

fn rec(slot: u64, index: u64, tag: u8, create: bool, buys: &[(u8, u64)]) -> ExecRec {
    ExecRec { slot, index, sig: [tag; 64], ok: true, is_create: create, buys: buys.iter().map(|&(w, s)| ([w; 32], s, 1)).collect(), sells: 0 }
}

#[test]
fn position_analysis() {
    let us = [99u8; 32];
    let recs = vec![
        rec(100, 40, 1, true, &[(1, 2_000_000_000)]),     // create + dev buy
        rec(100, 41, 2, false, &[(2, 500_000_000)]),      // bundle
        rec(100, 45, 3, false, &[(3, 100_000_000), (4, 50_000_000)]),
        rec(100, 50, 4, false, &[(99, 50_000_000)]),      // us
        rec(101, 2, 5, false, &[(5, 1)]),
    ];
    let p = position(&recs, None, &[4u8; 64], &us).unwrap();
    assert_eq!((p.create_slot, p.create_idx, p.land_slot, p.land_idx), (100, 40, 100, 50));
    assert_eq!(p.slot_delta, 0);
    assert_eq!(p.idx_delta, Some(10));
    assert_eq!(p.dev_buys_in_create, 1);
    assert_eq!((p.txs_between, p.buy_txs_ahead, p.buyers_ahead, p.sol_ahead), (2, 2, 3, 650_000_000));
    assert_eq!(p.buy_rank, 3);
    // next slot landing; a failed tx between does not count
    let mut r2 = recs.clone();
    r2[3].slot = 101; r2[3].index = 9;
    r2[2].ok = false;
    let p2 = position(&r2, Some(&[1u8; 64]), &[4u8; 64], &us).unwrap();
    assert_eq!(p2.slot_delta, 1);
    assert_eq!(p2.idx_delta, None);
    assert_eq!((p2.txs_between, p2.buyers_ahead), (2, 2), "bundle + the slot-101 buyer");
    // unknown create / us
    assert!(position(&recs[1..], None, &[4u8; 64], &us).is_none());
    assert!(position(&recs, None, &[7u8; 64], &us).is_none());
}

/// replay: the 250 recorded launches (testdata) through detection -> watch -> build + sign -> parse back
#[test]
fn replay_recorded_launches_sample() {
    let lines: Vec<serde_json::Value> = include_str!("testdata/launches_sample.jsonl").lines().map(|l| serde_json::from_str(l).unwrap()).collect();
    let mut n: HashMap<String, usize> = HashMap::new();
    for r in &lines { *n.entry(r["creator"].as_str().unwrap().to_string()).or_default() += 1; }
    let watch: HashSet<Pk> = n.into_iter().filter(|(_, k)| *k >= 2).map(|(c, _)| pk(&c)).collect();
    let s = replay_records(&lines, &watch);
    eprintln!("replay sample: {}", serde_json::to_string(&s).unwrap());
    assert!(s.bad.is_empty(), "{:?}", s.bad);
    assert!(s.creates >= 200);
    assert_eq!(s.detected, s.creates);
    assert_eq!(s.mint_ok, s.creates);
    assert_eq!(s.creator_ok, s.creates);
    assert_eq!(s.curve_pda_ok, s.creates);
    assert!(s.watched > 20, "{}", s.watched);
    assert_eq!(s.fired, s.watched);
}

/// replay on the collector's own files when they are on this machine (first 5,000 launches of each run)
#[test]
fn replay_collector_runs_if_present() {
    let Ok(rd) = std::fs::read_dir("/home/moiz/sniper-data/collect") else { eprintln!("no collector data here: skipped"); return };
    let mut runs: Vec<_> = rd.filter_map(|e| e.ok()).map(|e| e.path().join("launches.jsonl")).filter(|p| p.exists()).collect();
    runs.sort();
    for p in runs.iter().rev().take(2) {
        use std::io::BufRead;
        let f = std::io::BufReader::new(std::fs::File::open(p).unwrap());
        let lines: Vec<serde_json::Value> = f.lines().take(5000).filter_map(|l| l.ok()).filter_map(|l| serde_json::from_str(&l).ok()).collect();
        let mut n: HashMap<String, usize> = HashMap::new();
        for r in &lines { if let Some(c) = r["creator"].as_str() { *n.entry(c.to_string()).or_default() += 1; } }
        let watch: HashSet<Pk> = n.into_iter().filter(|(_, k)| *k >= 3).map(|(c, _)| pk(&c)).collect();
        let s = replay_records(&lines, &watch);
        eprintln!("replay {}: creates {} detected {} curve_ok {} watched {} fired {} build p50 {} us p99 {} us bad {}", p.display(), s.creates, s.detected, s.curve_pda_ok, s.watched, s.fired,
            s.build_us_p50, s.build_us_p99, s.bad.len());
        assert!(s.bad.is_empty(), "{:?}", &s.bad[..s.bad.len().min(5)]);
        assert_eq!(s.curve_pda_ok, s.creates);
        assert_eq!(s.creator_ok, s.creates, "CreateEvent creator (incl. holder-reward PDAs) recovered on every create");
    }
}

#[test]
fn nonce_file_and_account_check() {
    assert_eq!(parse_nonce_file("# x\n6TgN6S7q74s9zSaktKm4kqFRPTLhtQpFUXZvGib7fUmD\n6TgN6S7q74s9zSaktKm4kqFRPTLhtQpFUXZvGib7fUmD\n").unwrap().len(), 1);
    assert!(parse_nonce_file("bad").is_err());
    assert!(parse_nonce_file("").is_err());
    let user = [5u8; 32];
    let mut d = vec![0u8; 80];
    d[0..4].copy_from_slice(&1u32.to_le_bytes());
    d[4..8].copy_from_slice(&1u32.to_le_bytes());
    d[8..40].copy_from_slice(&user);
    d[40..72].copy_from_slice(&[6u8; 32]);
    let v = |d: &[u8], owner: &str| serde_json::json!({ "owner": owner, "data": [base64::engine::general_purpose::STANDARD.encode(d), "base64"] });
    let sys = "11111111111111111111111111111111";
    assert_eq!(nonce_check(&v(&d, sys), &user), Ok([6u8; 32]));
    assert!(nonce_check(&v(&d, sys), &[4u8; 32]).is_err(), "another authority");
    assert!(nonce_check(&v(&d, "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"), &user).is_err());
    assert!(nonce_check(&serde_json::Value::Null, &user).is_err());
}

#[test]
fn records_and_cli_defaults() {
    let a = Args::try_parse_from(["apex_probe", "--config", "x.toml"]).unwrap();
    assert_eq!(a.mode, "shadow");
    assert_eq!(a.size_sol, 0.05);
    assert_eq!(a.max_buys, 20);
    assert_eq!(a.max_spend_sol, 1.5);
    assert_eq!(a.hold_ms, 2000);
    assert_eq!(a.buy_guard, 0.2);
    assert_eq!(a.routes, "v13");
    assert_eq!(a.max_open, 1);
    assert!(a.kill_below.is_none() && a.max_runtime_min.is_none());
    // live without the required caps is refused by validate_caps (main maps it to REFUSED)
    let ca = CapArgs { live: true, size_sol: a.size_sol, max_buys: a.max_buys, max_spend_sol: a.max_spend_sol, kill_below_sol: a.kill_below, max_runtime_min: a.max_runtime_min,
        max_open: a.max_open, buy_guard: a.buy_guard, sell_guard: a.sell_guard, hold_ms: a.hold_ms };
    assert!(validate_caps(&ca).is_err());
}

// ---------------------------------------------------------------------------------------------------------------- v2

#[test]
fn lanes_spec_and_default_recipe() {
    let m = parse_lanes(LANES_DEFAULT).unwrap();
    assert_eq!(m["bam"], vec![LaneSpec { path: "jito-bundle".into(), tip: Some(2_000_000), prio: None }, LaneSpec { path: "staked-rpc".into(), tip: Some(0), prio: Some(2_000_000) }]);
    assert_eq!(m["jito"], m["bam"]);
    assert_eq!(m["harmonic"], vec![LaneSpec { path: "nozomi".into(), tip: Some(2_500_000), prio: None }]);
    assert_eq!(m["fd"], vec![LaneSpec { path: "astralane".into(), tip: Some(2_500_000), prio: Some(500_000) }]);
    assert_eq!(m["agave"].iter().map(|l| l.path.as_str()).collect::<Vec<_>>(), vec!["nozomi", "helius-swqos", "bolt", "staked-rpc"]);
    // the recipe's exclusions: no 0slot anywhere, no helius on Harmonic / Firedancer
    assert!(m.values().flatten().all(|l| l.path != "0slot"));
    assert!(m["harmonic"].iter().chain(&m["fd"]).all(|l| !l.path.starts_with("helius")));
    // presets still parse (multitip recipe), bad specs refused
    assert_eq!(parse_lanes("v13").unwrap()["fd"][0], LaneSpec { path: "0slot".into(), tip: None, prio: None });
    assert!(parse_lanes("bam=jito-bundle:abc;default=x").is_err());
    assert!(parse_lanes("bam=jito-bundle:30000000;default=x").is_err(), "tip above 0.02 SOL");
    assert!(parse_lanes("bam=x").is_err(), "needs default");
    assert_eq!(cu_price_for(100_000, 100_000), 1_000_000);
    assert_eq!(cu_price_for(2_000_000, 100_000), 20_000_000);
}

#[test]
fn lane_copies_one_tip_each_shared_nonce() {
    let key = SigningKey::from_bytes(&[3u8; 32]);
    let user = key.verifying_key().to_bytes();
    let l = snipe_build::launch_from_target([0x5Au8; 32], [0x6Bu8; 32]);
    let c = BuyCfg { user, spend: 50_000_000, min_out: 77, cu_limit: 100_000, cu_price: 0, guard: Some((GUARD_DEFAULT, 500)) };
    let (na, nv) = ([71u8; 32], [72u8; 32]);
    let lanes = [LaneCopy { pi: 4, tip: Some(([9u8; 32], 2_000_000)), prio: 100_000 }, LaneCopy { pi: 7, tip: None, prio: 2_000_000 },
        LaneCopy { pi: 2, tip: Some(([8u8; 32], 2_500_000)), prio: 500_000 }];
    let v = build_lane_copies(&key, &c, &l, (na, nv), &lanes).unwrap();
    assert_eq!(v.len(), 3);
    for (cp, ln) in v.iter().zip(&lanes) {
        assert_eq!(cp.paths, vec![ln.pi]);
        let (p, _) = parse_wire(&cp.raw).unwrap();
        assert_eq!(p.ixs[0].data, 4u32.to_le_bytes().to_vec(), "AdvanceNonce first");
        assert_eq!(p.keys[p.ixs[0].accounts[0] as usize], na);
        let tips: Vec<u64> = p.ixs.iter().filter(|ix| p.keys[ix.program as usize] == *pda::SYSTEM_PROGRAM && ix.data.len() == 12 && ix.data[..4] == [2, 0, 0, 0])
            .map(|ix| u64_at(&ix.data, 4)).collect();
        assert_eq!(tips, ln.tip.map(|t| vec![t.1]).unwrap_or_default(), "ONE tip (or none) per lane");
        assert_eq!(p.cu_price().unwrap_or(0), cu_price_for(ln.prio, 100_000), "the lane's own priority");
        let (_, _, _, d) = ix_of(&p, &snipe::PUMP);
        assert_eq!(u64_at(&d, 16), 77);
        assert_eq!(ix_role(&cp.raw, p.ixs.iter().position(|ix| p.keys[ix.program as usize] == *snipe::PUMP).unwrap() as u64), "buy");
        assert_eq!(ix_role(&cp.raw, 0), "nonce");
    }
    // all three share the nonce: different signatures, same recent blockhash field (the nonce value)
    assert!(v[0].sig != v[1].sig && v[1].sig != v[2].sig);
}

#[test]
fn first_or_revert_state() {
    // fresh curve: the guard is exact at the create's state
    let vq0 = curve_after_legs(&[]).unwrap();
    assert_eq!(vq0, snipe::CURVE_VQ0);
    let (exp, mo) = first_min_out(vq0, 50_000_000, 0.005);
    assert_eq!(exp, expected_tokens(0, 50_000_000));
    assert_eq!(mo, (exp as f64 * 0.995).floor() as u64);
    // a dev buy of 1 SOL exact-in (incl. fees) moves the state by 1 SOL x 10000/10125
    let vq1 = curve_after_legs(&[(true, 1_000_000_000, 0)]).unwrap();
    assert_eq!(vq1, snipe::CURVE_VQ0 + net_of_fee(1_000_000_000));
    // a cap leg (exact tokens) prices on the curve
    let toks = snipe::curve_tokens_out(snipe::CURVE_VQ0, 500_000_000);
    let vq2 = curve_after_legs(&[(false, toks, u64::MAX)]).unwrap();
    assert!((vq2 as i64 - (snipe::CURVE_VQ0 + 500_000_000) as i64).abs() <= 2, "{vq2}");
    // our buy right at the state passes; behind a rival's 0.1 SOL it reverts (fewer tokens than min_out); 0.01 SOL slips through
    let (_, mo1) = first_min_out(vq1, 50_000_000, 0.005);
    let at = |extra: u64| snipe::curve_tokens_out(vq1 + extra, net_of_fee(50_000_000));
    assert!(at(0) >= mo1);
    assert!(at(net_of_fee(100_000_000)) < mo1, "a 0.1 SOL buyer ahead must revert us");
    assert!(at(net_of_fee(10_000_000)) >= mo1, "0.01 SOL is inside the 0.5% tolerance");
    // a leg that would fail its own slippage: no state
    assert!(curve_after_legs(&[(true, 1_000_000_000, u64::MAX)]).is_none());
}

#[test]
fn bundle_and_rivals() {
    let us = [99u8; 32];
    let recs = vec![
        rec(100, 40, 1, true, &[(1, 1_000_000_000)]),
        rec(100, 41, 2, false, &[(2, 500_000_000)]),       // creator bundle (contiguous)
        rec(100, 42, 3, false, &[(3, 400_000_000)]),       // creator bundle
        rec(100, 45, 4, false, &[(4, 100_000_000)]),       // rival (gap)
        rec(100, 50, 5, false, &[(99, 50_000_000)]),       // us
    ];
    let (n, sol, _) = bundle_after(&recs, &recs[0]);
    assert_eq!((n, sol), (2, 900_000_000));
    let r = rivals(&recs, None, &[5u8; 64], &us).unwrap();
    assert_eq!((r.bundle_txs, r.rival_buy_txs_ahead, r.rival_buyers_ahead, r.rival_sol_ahead, r.first_non_bundle), (2, 1, 1, 100_000_000, false));
    // without the rival we are the first non-bundle buyer
    let mut r2 = recs.clone();
    r2.remove(3);
    assert!(rivals(&r2, None, &[5u8; 64], &us).unwrap().first_non_bundle);
    // our reverted tx still has its place (ok false), the rival counted
    let mut r3 = recs.clone();
    r3[4].ok = false;
    assert_eq!(rivals(&r3, None, &[5u8; 64], &us).unwrap().rival_buy_txs_ahead, 1);
    // error codes
    let e = serde_json::json!({ "InstructionError": [6, { "Custom": 6002 }] });
    assert_eq!(err_code(&e), (Some(6), Some(6002)));
    assert_eq!(err_code(&serde_json::Value::Null), (None, None));
}

#[test]
fn v2_cli_defaults() {
    let a = Args::try_parse_from(["apex_probe", "--config", "x.toml"]).unwrap();
    assert_eq!(a.recipe, "lanes");
    assert_eq!(a.lanes, LANES_DEFAULT);
    assert!(!a.no_first_or_revert);
    assert_eq!(a.first_tol, 0.005);
    assert_eq!(a.bundle_wait_us, 300);
    assert_eq!(a.prio_lamports, 100_000);
    // APEX-PROBE-FIX: CreateEvent creator match; entry score logged, never gating, unless asked
    assert_eq!(a.match_on, "creator");
    assert_eq!(a.entry_filter, "log");
    assert_eq!(a.entry_model, "/root/apex/entry_model.json");
    assert_eq!(a.entry_thr, None);
}

#[test]
fn bundle_wait_plan_from_watchlist() {
    let t = r#"{"creators":[{"creator":"6TgN6S7q74s9zSaktKm4kqFRPTLhtQpFUXZvGib7fUmD","bundle_txs_median":2.0},{"creator":"EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR","bundle_txs_median":0.0},{"creator":"5AkWnkoNAU6hzEQpYTuSN9vtF1rVdpY8zUFLynq3B5y9"}]}"#;
    let h = parse_bundle_hints(t);
    assert_eq!(h.len(), 2);
    assert_eq!(h[&pk("6TgN6S7q74s9zSaktKm4kqFRPTLhtQpFUXZvGib7fUmD")], 2.0);
    assert_eq!(bundle_plan("auto", Some(2.0), 300), (300, Some(2)));
    assert_eq!(bundle_plan("auto", Some(0.0), 300), (0, None), "no bundle: fire at once");
    assert_eq!(bundle_plan("auto", None, 300), (0, None));
    assert_eq!(bundle_plan("auto", Some(1.5), 300), (300, Some(2)));
    assert_eq!(bundle_plan("always", None, 300), (300, None));
    assert_eq!(bundle_plan("never", Some(3.0), 300), (0, None));
    // the real watchlist parses (when it is on this machine)
    if let Ok(t) = std::fs::read_to_string("/home/moiz/sniper-data/apex2/watchlist.json") {
        let h = parse_bundle_hints(&t);
        assert_eq!(h.len(), parse_watchlist(&t).unwrap().len());
    }
}

/// the FRA shadow-run-1 hang: the records must be flushed (and the call return) while other holders of the writer —
/// feed / poller tasks in a run — are still alive; the old shutdown waited for the channel to close and never returned
#[test]
fn recorder_flush_returns_while_other_holders_live() {
    let dir = std::env::temp_dir().join(format!("apex_probe_test_{}", std::process::id()));
    std::fs::create_dir_all(&dir).unwrap();
    let path = dir.join("rec.jsonl");
    let (rec, _h) = Recorder::open(path.to_str().unwrap()).unwrap();
    let other = Recorder { tx: rec.tx.clone() }; // a task still holding the writer
    for i in 0..1000 { rec.ev("x", serde_json::json!({ "i": i })); }
    other.ev("y", serde_json::json!({}));
    let t = Instant::now();
    assert!(rec.flush(Duration::from_secs(5)), "flush confirmed");
    assert!(t.elapsed() < Duration::from_secs(2));
    let text = std::fs::read_to_string(&path).unwrap();
    assert_eq!(text.lines().count(), 1001, "every record on disk before the exit");
    assert!(text.lines().last().unwrap().contains("\"ev\":\"y\""));
    drop(other);
    let _ = std::fs::remove_dir_all(&dir);
}

#[test]
fn stop_signal_escalation() {
    assert_eq!(sig_action(1), SigAction::Drain);
    assert_eq!(sig_action(2), SigAction::DrainThenExit);
    assert_eq!(sig_action(3), SigAction::ExitNow);
    assert_eq!(sig_action(7), SigAction::ExitNow);
}

// ---------------------------------------------------------------------------------------------------------------- v3

/// the fast build's bytes == the lib builder's, over random launches and every shape (nonce or not, 0..4 tips, guard or
/// not, create-tx curve ATA or derived); and the presigned signatures verify
#[test]
fn fast_build_equals_lib_build() {
    use sha2::{Digest, Sha256};
    let h = |i: u64, t: u8| -> Pk { Sha256::new().chain_update(i.to_le_bytes()).chain_update([t]).finalize().into() };
    let key = SigningKey::from_bytes(&[21u8; 32]);
    let user = key.verifying_key().to_bytes();
    let stop = Arc::new(AtomicBool::new(false));
    let ps = arbx::fast::Presigner::new(&key);
    ps.start(64, stop.clone());
    let fx = fastbuild::FastCtx::new(&key, user, Some(ps));
    assert!(fastbuild::selftest(&fx, 50).is_ok());
    for i in 0..300u64 {
        let mut l = snipe_build::launch_from_target(h(i, 1), h(i, 2));
        l.buyback_fee_recipient = h(i, 3);
        if i % 3 == 0 { l.assoc_bonding_curve = [0u8; 32]; } // derived instead of taken from the create
        let k = fx.keys(&l);
        assert_eq!(k.abc, snipe_build::assoc_bonding_curve(&l.bonding_curve, &l.mint));
        assert_eq!(k.user_base, snipe_build::assoc_user(&user, &l.mint));
        let mut ls = l.clone();
        ls.assoc_bonding_curve = snipe_build::assoc_bonding_curve(&l.bonding_curve, &l.mint);
        let ntips = (i % 5) as usize;
        let tips: Vec<(Pk, u64)> = (0..ntips).map(|j| (h(i, 10 + j as u8), 1_000_000 + j as u64)).collect();
        let nonce = if i % 2 == 0 { Some(h(i, 5)) } else { None };
        let guard = if i % 4 == 1 { None } else { Some((GUARD_DEFAULT, 464_000_000 + i)) };
        let slow = buy_ixs(user, &ls, 50_000_000 + i, 777 + i, 100_000, 5_000 * i, nonce, &tips, guard);
        let fastv = fx.buy_ixs(&k, 50_000_000 + i, 777 + i, 100_000, 5_000 * i, nonce, &tips, guard);
        assert_eq!(fastv.len(), slow.len(), "launch {i}");
        for (a, b) in fastv.iter().zip(&slow) {
            assert_eq!(a.program, b.program);
            assert_eq!(a.data, b.data);
            assert_eq!(ours(a), ours(b), "launch {i}");
        }
        // lane copies: same message bytes; the fast one's (presigned) signature verifies
        let c = BuyCfg { user, spend: 50_000_000, min_out: 9, cu_limit: 100_000, cu_price: 0, guard };
        let ln = LaneCopy { pi: 3, tip: tips.first().copied(), prio: 100_000 + i };
        let a = fx.lane_copy(&c, &k, (h(i, 6), h(i, 7)), &ln).unwrap();
        let b = build_lane_copies(&key, &c, &ls, (h(i, 6), h(i, 7)), &[ln]).unwrap().remove(0);
        assert_eq!(a.raw[65..], b.raw[65..]);
        use ed25519_dalek::Verifier;
        assert!(key.verifying_key().verify_strict(&a.raw[65..], &ed25519_dalek::Signature::from_bytes(&a.sig)).is_ok());
        let _ = Verifier::verify(&key.verifying_key(), &b.raw[65..], &ed25519_dalek::Signature::from_bytes(&b.sig));
    }
    stop.store(true, Ordering::Relaxed);
}

/// the fast build against OUR OWN landed buy (AMS run 48): the 17 buy accounts + data are the real ones
#[test]
fn fast_build_matches_real_landed_buy() {
    let (tx, _) = real("buy");
    let (keys, w, s, data) = ix_of(&tx, &snipe::PUMP);
    let user = tx.keys[0];
    let key = SigningKey::from_bytes(&[1u8; 32]);
    let fx = fastbuild::FastCtx::new(&key, user, None);
    let mut l = snipe_build::launch_from_target(keys[1], user);
    l.buyback_fee_recipient = keys[13];
    let k = fx.keys(&l);
    let v = fx.buy_ixs(&k, u64_at(&data, 8), u64_at(&data, 16), 100_000, 0, None, &[], None);
    assert_eq!(ours(v.last().unwrap()), (keys, w, s, data));
}

/// v3 templates: a patched lane copy == the fast full build, byte for byte (message), for random launches and every lane
/// shape (tip or not, guard or not); the signature verifies
#[test]
fn template_copy_equals_full_build() {
    use sha2::{Digest, Sha256};
    let h = |i: u64, t: u8| -> Pk { Sha256::new().chain_update(i.to_le_bytes()).chain_update([t]).finalize().into() };
    let key = SigningKey::from_bytes(&[33u8; 32]);
    let user = key.verifying_key().to_bytes();
    let stop = Arc::new(AtomicBool::new(false));
    let ps = arbx::fast::Presigner::new(&key);
    ps.start(64, stop.clone());
    let fx = fastbuild::FastCtx::new(&key, user, Some(ps));
    let mut buf = Vec::new();
    for (tip, prio, guard) in [(Some(2_000_000u64), 100_000u64, true), (None, 2_000_000, true), (Some(2_500_000), 500_000, false), (None, 100_000, false)] {
        let g = guard.then_some(GUARD_DEFAULT);
        let t = fx.template(50_000_000, 100_000, tip, prio, g).unwrap();
        for i in 0..100u64 {
            let mut l = snipe_build::launch_from_target(h(i, 1), h(i, 2));
            l.buyback_fee_recipient = h(i, 3);
            let k = fx.keys(&l);
            let ln = LaneCopy { pi: 2, tip: tip.map(|a| (h(i, 4), a)), prio };
            let n = (h(i, 5), h(i, 6));
            let dl = guard.then_some(464_000_000 + i);
            let a = fx.lane_copy_tpl(&t, &k, n, &ln, 4242 + i, dl, &mut buf).expect("template patch");
            let c = BuyCfg { user, spend: 50_000_000, min_out: 4242 + i, cu_limit: 100_000, cu_price: 0, guard: g.map(|x| (x, 464_000_000 + i)) };
            let b = fx.lane_copy(&c, &k, n, &ln).unwrap();
            assert_eq!(a.raw[65..], b.raw[65..], "shape {tip:?}/{prio}/{guard} launch {i}");
            assert_eq!(a.tip, b.tip);
            assert!(key.verifying_key().verify_strict(&a.raw[65..], &ed25519_dalek::Signature::from_bytes(&a.sig)).is_ok());
            assert_eq!(a.sig, logic::sig_of(&a.raw));
        }
    }
    stop.store(true, Ordering::Relaxed);
}

/// v4: the bundle window's classification of shred txs (bundle leg / not plain / the create's feed moved on / other)
#[test]
fn bundle_window_steps() {
    let mint = [0x5Au8; 32];
    let other = [0x77u8; 32];
    let buy_tx = |m: Pk| {
        let mut d = snipe::BUY_EXACT_QUOTE_IN_V3_DISC.to_vec(); d.extend(1_000_000_000u64.to_le_bytes()); d.extend(5u64.to_le_bytes()); d.push(0);
        arbx::tx::Tx { keys: vec![[1u8; 32], m, *snipe::PUMP], num_signers: 1, ixs: vec![arbx::tx::Ix { program: 2, accounts: vec![0, 1, 0, 0, 0], data: d }], ..Default::default() }
    };
    let sell_tx = |m: Pk| {
        let mut d = snipe_build::SELL_V3_DISC.to_vec(); d.extend(1u64.to_le_bytes()); d.extend(0u64.to_le_bytes());
        arbx::tx::Tx { keys: vec![[1u8; 32], m, *snipe::PUMP], num_signers: 1, ixs: vec![arbx::tx::Ix { program: 2, accounts: vec![0, 1], data: d }], ..Default::default() }
    };
    assert_eq!(window_step(100, 0, &mint, 100, 1, &buy_tx(mint)), Step::Bundle(vec![(true, 1_000_000_000, 5)]), "a bundle leg from any feed");
    assert_eq!(window_step(100, 0, &mint, 100, 0, &sell_tx(mint)), Step::NotPlain);
    assert_eq!(window_step(100, 0, &mint, 100, 0, &buy_tx(other)), Step::MovedOn, "same feed, same slot, another mint: past the bundle");
    assert_eq!(window_step(100, 0, &mint, 100, 2, &buy_tx(other)), Step::Other, "another feed says nothing about the create's feed order");
    assert_eq!(window_step(100, 0, &mint, 101, 0, &buy_tx(other)), Step::MovedOn, "a later slot on the create's feed");
    assert_eq!(window_step(100, 0, &mint, 99, 0, &buy_tx(other)), Step::Other, "an older slot (late delivery)");
    assert_eq!(window_step(100, 0, &mint, 101, 0, &buy_tx(mint)), Step::MovedOn, "our mint in the next slot is not the bundle");
}


// ==================================================================================================================
// APEX-PROBE-FIX (11-04): the CreateEvent creator match + the APEX-3 entry score
// ==================================================================================================================

/// real create_v2 txs (getTransaction, 11-03) vs the collector's CreateEvent record: holder-reward (event creator = the
/// holder-rewards PDA, signer = args creator = the watched wallet the old match bought), args creator != signer, plain
#[test]
fn event_creator_real_creates() {
    let j: serde_json::Value = serde_json::from_str(include_str!("testdata/creates_ev_creator.json")).unwrap();
    let mut kinds = Vec::new();
    for c in j["creates"].as_array().unwrap() {
        let kind = c["kind"].as_str().unwrap();
        let tx = tx_from_json(&c["tx"]).expect("tx");
        let l = snipe::detect_launch(&tx).expect("detect");
        let rec = &c["rec"];
        let (ev_rec, user, signer) = (pk(rec["creator"].as_str().unwrap()), pk(rec["user"].as_str().unwrap()), tx.keys[0]);
        assert_eq!(b58(&l.mint), rec["mint"].as_str().unwrap());
        assert_eq!(event_creator(&l), ev_rec, "{kind}: event creator");
        let w_signer: HashSet<Pk> = [signer].into_iter().collect();
        let w_ev: HashSet<Pk> = [ev_rec].into_iter().collect();
        match kind {
            "holder_reward" => {
                assert!(l.is_holder_reward);
                assert_eq!(l.creator, signer);
                assert_eq!(user, signer);
                assert_ne!(ev_rec, signer);
                assert_eq!(ev_rec, holder_rewards_pda(&l.mint));
                // the old match (args creator) bought it for the watched signer; the backtest never would
                assert!(MatchOn::Args.hit(&w_signer, &event_creator(&l), &l.creator, tx.keys.first()));
                assert!(!MatchOn::Creator.hit(&w_signer, &event_creator(&l), &l.creator, tx.keys.first()));
                assert!(MatchOn::Creator.hit(&w_ev, &event_creator(&l), &l.creator, tx.keys.first()));
            }
            "args_creator_not_signer" => {
                assert!(!l.is_holder_reward);
                assert_ne!(ev_rec, signer);
                assert_eq!(l.creator, ev_rec);
                assert!(MatchOn::Creator.hit(&w_ev, &event_creator(&l), &l.creator, tx.keys.first()));
                assert!(!MatchOn::Creator.hit(&w_signer, &event_creator(&l), &l.creator, tx.keys.first()));
                assert!(MatchOn::Signer.hit(&w_signer, &event_creator(&l), &l.creator, tx.keys.first()));
            }
            _ => { assert_eq!(ev_rec, signer); assert_eq!(l.creator, signer); }
        }
        // the offline replay synthesizes the same CreateEvent creator from the record alone
        let (stx, _) = synth_create(rec).unwrap();
        let sl = snipe::detect_launch(&stx).unwrap();
        assert_eq!(event_creator(&sl), ev_rec, "{kind}: synth");
        assert_eq!(sl.is_holder_reward, kind == "holder_reward");
        kinds.push(kind.to_string());
    }
    assert_eq!(kinds.len(), 3);
}

/// the 9 r10/r11 live fills that were not backtest picks (sniper-apexcmp REPORT.md): all holder-reward launches; the
/// CreateEvent creator is the mint's holder-rewards PDA, not the watched signer
#[test]
fn live_nonpicks_were_holder_reward_launches() {
    let nine = [
        ("67n7iCWu3iXTPhK9m9GHK81weRc4w6JtAyXMnqVwpump", "75HPJgTte5iynyTUhAJwLKoBYE6AfAo57yjU3S5mAVtR", "5rKx6eaPfo2VBuD7bWXiTsnSPEfR1A5TbkgqkfZbVYN4"),
        ("DRr649c2mLcUcu24Lbt1zTgzszYHbxzP9WiKVJHexwXH", "bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa", "9YEUwGPbiAHjUmWT1GbLcaqCTLtqxU64khgguDaz1ia6"),
        ("m4J3XedUEEHYE757Wdt4vrNR1gYFr341y6eThu41rYC", "bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa", "71xPNUqR5wH7hkAMR2xWhKBivmdd2YenCeds8Uj9TiUs"),
        ("2iuuNU3RZHkTu94hqkYPe761PDg26oW7x8TNh4RHxdn7", "bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa", "CM3VamitTTaKkv1PCkRauApDXATSyWQCtTSEn8rSTMSW"),
        ("HWsg5w6EM1vZJrbKjpgUkwYbEpWtHwf8QCNWCtx3wJJz", "bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa", "4tkTz2V7BbU432wjF9hsGY6LLshu1R7H4fJ6ne5Uzask"),
        ("DPqJJviWyqwiWvthaaJVYTFseFQPk2LmFefYnYAB9pNV", "bwamJzztZsepfkteWRChggmXuiiCQvpLqPietdNfSXa", "51kKMGrXS59GujvSr3oDheucGzEKGwP98d9deqm8SoSp"),
        ("4UHPwjQYrydkMBZC57ubt1Zdr7eo4sQfxCV8LjSapump", "9KGv1vhepXtMeAxnvVf9wqEq5RbXaZioeZmPan4aDWcM", "6RDm59B4wtammRhqm7HF3oy4b2Aq5byLM63gah6Cyyw9"),
        ("2AzrXc8DNa1nkBAcnrpjL7JQRq7N1HvcPhd4Rrvjpump", "AcU7BK4Ec6WLx9nxXA4Dtx6E6S2MqCwratn1WjxsX3ae", "nsmo35egmeECEfezPipue7EQZuowPyuhMhHr72NNKHh"),
        ("2xSK9YcTgTB58kPv6rbfhMEafxKAoDL2JNsYGnAk9x8C", "dtrzJPj7yDdvm6eRqBAgxsK2sMJeD9HhBEBB3XMedXy", "B7H1HRzJSnABvwDYFctUsRSXiWRkaNDUZyc2nJawrvbx"),
    ];
    for (m, signer, ev) in nine {
        let mut l = snipe_build::launch_from_target(pk(m), pk(signer));
        l.is_holder_reward = true;
        assert_eq!(b58(&event_creator(&l)), ev, "{m}");
        let w: HashSet<Pk> = [pk(signer)].into_iter().collect();
        assert!(!MatchOn::Creator.hit(&w, &event_creator(&l), &l.creator, Some(&pk(signer))), "{m}: must not match the signer");
    }
}

#[test]
fn numpy_sums_bit_exact() {
    // np.add.reduce / np.mean references (numpy 2.2.4)
    assert_eq!(entry::np_sum(&[0.1; 10]).to_bits(), 1.0f64.to_bits());
    assert_eq!(entry::np_sum(&[0.1; 300]).to_bits(), 29.999999999999996f64.to_bits());
    let v: Vec<f64> = (1..=17).map(|i| i as f64 / 10.0).collect();
    assert_eq!(entry::np_sum(&v).to_bits(), 15.3f64.to_bits());
    assert_eq!((entry::np_mean32(&[0.1f32; 13]) as f64).to_bits(), 0.10000000894069672f64.to_bits());
}

#[test]
fn entry_mode_and_legs() {
    assert_eq!(entry::EntryMode::parse("log"), Ok(entry::EntryMode::Log));
    assert_eq!(entry::EntryMode::parse("on"), Ok(entry::EntryMode::On));
    assert_eq!(entry::EntryMode::parse("off"), Ok(entry::EntryMode::Off));
    assert!(entry::EntryMode::parse("yes").is_err());
    // a 1 SOL exact-in dev buy = TradeEvent sol 0.98765432 (the tape's dev_sol of such a launch); a bundle cap-family leg
    let (dev, bund) = entry::leg_sols(&[(true, 1_000_000_000, 0)], &[(false, 10_000_000_000_000, 0)]);
    assert_eq!(dev, 987_654_320);
    let (_, tok) = entry::pump_buy(snipe::CURVE_VQ0, snipe::CURVE_VT0, (true, 1_000_000_000, 0)).unwrap();
    assert_eq!(Some(bund), entry::pump_buy(snipe::CURVE_VQ0 + 987_654_320, snipe::CURVE_VT0 - tok, (false, 10_000_000_000_000, 0)).map(|x| x.0));
    assert_eq!(entry::leg_sols(&[], &[]), (0, 0));
    // exact-in spend -> TradeEvent sol, the 11-03 tape's dev legs (the floor(a x 1e4/10125) shortcut is 1 high on 5 of them)
    for (spend, sol) in [(5_648_000_000u64, 5_578_271_604u64), (5_641_000_000, 5_571_358_023), (5_733_000_000, 5_662_222_221), (5_437_000_000, 5_369_876_542),
        (5_528_000_000, 5_459_753_085), (5_798_000_000, 5_726_419_752), (3_000_000_000, 2_962_962_962), (12_000_000_000, 11_851_851_851)] {
        assert_eq!(entry::pump_buy(snipe::CURVE_VQ0, snipe::CURVE_VT0, (true, spend, 0)).unwrap().0, sol, "{spend}");
    }
    // a min-tokens / max-SOL limit fails the leg
    assert_eq!(entry::pump_buy(snipe::CURVE_VQ0, snipe::CURVE_VT0, (true, 1_000_000_000, u64::MAX)), None);
    assert_eq!(entry::pump_buy(snipe::CURVE_VQ0, snipe::CURVE_VT0, (false, 10_000_000_000_000, 1)), None);
    let poh = arbx::feeds::entries::Poh { slot: 1, hashes: 64 * 100, ticks: 0, hpt: 400 };
    assert_eq!(entry::u_from_poh(Some(&poh)), Some(0.25));
    assert_eq!(entry::u_from_poh(None), None);
}

/// the APEX-3 entry model (day-7 validation model, history of the sampled creators) scores 40 recorded launches
/// bit-identically to run3_lib (features and score), incl. creators without history, bundles, float32/float64 label means
#[test]
fn entry_score_matches_apex3_sample() {
    let j: serde_json::Value = serde_json::from_str(include_str!("testdata/entry_sample.json")).unwrap();
    let m = entry::EntryModel::parse(&j["model"].to_string()).expect("model");
    assert_eq!(m.n_trees(), 300);
    let f = |v: &serde_json::Value| -> f64 { v.as_str().unwrap().parse().unwrap() };
    let (mut n, mut picks) = (0, 0);
    for c in j["cases"].as_array().unwrap() {
        let o = entry::Obs { dev_sol: f(&c["dev_sol"]), bund_sol: f(&c["bund_sol"]), bund_users: c["bund_users"].as_f64().unwrap(), u: f(&c["u"]), bt: c["bt"].as_i64().unwrap() };
        let sc = m.score(&pk(c["creator"].as_str().unwrap()), &o);
        for (k, x) in c["x"].as_array().unwrap().iter().enumerate() {
            let p = f(x);
            assert!((p.is_nan() && sc.x[k].is_nan()) || p.to_bits() == sc.x[k].to_bits(), "{} feature {} {p} vs {}", c["mint"], entry::FEATURES[k], sc.x[k]);
        }
        assert_eq!(sc.score.to_bits(), f(&c["score"]).to_bits(), "{} score", c["mint"]);
        assert_eq!(sc.pass && c["sel"].as_bool().unwrap(), c["pick"].as_bool().unwrap());
        n += 1;
        if sc.pass { picks += 1; }
    }
    assert_eq!(n, 40);
    assert!(picks >= 12);
    // a bad model file is refused
    assert!(entry::EntryModel::parse("{}").is_err());
    assert!(entry::EntryModel::parse(&j["model"].to_string().replace("\"dev_sol\"", "\"devsol\"")).is_err());
}

/// real create + creator-bundle txs (getTransaction) of 7 recorded launches -> the probe's dev / bundle SOL / bundle buyers
/// equal the APEX-3 tape's (s3_sim info) to the lamport: rapidlaunch + terminal wrappers, extend_account in the create,
/// multi-wallet bundle txs (78wrUbBo: the tape counts 12 buyers, the txs have 15 signing buyers: the tape's synthetic
/// gap-fill rows copy the previous trade's user, so its count is low there)
#[test]
fn entry_inputs_from_real_txs_match_tape() {
    for l in include_str!("testdata/entry_txs_sample.jsonl").lines() {
        let t: serde_json::Value = serde_json::from_str(l).unwrap();
        let c = &t["case"];
        let m = c["mint"].as_str().unwrap();
        let create = tx_from_json(&t["create"]).unwrap();
        let bundle: Vec<arbx::tx::Tx> = t["bundle"].as_array().unwrap().iter().map(|x| tx_from_json(x).unwrap()).collect();
        let (ev, dev, bund, users, unseen) = obs_from_txs(&create, &bundle).expect("detect");
        let f = |k: &str| -> f64 { c[k].as_str().unwrap().parse().unwrap() };
        assert_eq!(b58(&ev), c["creator"].as_str().unwrap(), "{m}");
        assert_eq!((dev as f64 / 1e9).to_bits(), f("dev_sol").to_bits(), "{m} dev {dev}");
        assert_eq!((bund as f64 / 1e9).to_bits(), f("bund_sol").to_bits(), "{m} bundle {bund}");
        assert_eq!(unseen, 0, "{m}");
        if m.starts_with("78wrUbBo") { assert_eq!((users, c["bund_users"].as_u64().unwrap()), (15, 12)); } else { assert_eq!(users as u64, c["bund_users"].as_u64().unwrap(), "{m}"); }
    }
}

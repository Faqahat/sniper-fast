//! ledger.rs tests (PLAN WP-07 offline acceptance): the golden ledger cases on real wallet transactions
//! (testdata/wallet, testdata/legacy/expected.json), res-pnl's sums over the 119 landings, the wins of w5h2/w5h3, the
//! synthetic create-and-close and unwrap, snapshots, both reconciliations, the executor's recon (a refused bundle that
//! landed), the ledger's timers and stops on a virtual clock, the campaign's history across segments, spend.json
use super::*;
use crate::chainfetch::txjson;
use crate::control::{GateMode, Session, StopReason};
use crate::feeds::grpc::{PbHeader, PbInnerIx, PbInnerIxs, PbIx, PbMessage, PbMeta, PbTokenBalance, PbTransaction, PbUiAmount};
use std::path::PathBuf;

const WALLET: &str = "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE";
const ROUTE: &str = "8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg";
const FRZ: &str = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS";
const S: u64 = 1_000_000_000;
const M: u64 = 60 * S;
const T0: u64 = 1_800_000_000_000_000_000;

fn repo(rel: &str) -> PathBuf { Path::new(env!("CARGO_MANIFEST_DIR")).join(rel) }
fn json_file(p: &Path) -> Value { serde_json::from_slice(&std::fs::read(p).unwrap()).unwrap() }
fn wallet() -> Pk { crate::tx::pk(WALLET) }
fn wsol_ata(w: &Pk) -> Pk { crate::build::ata_of(w, &wsol(), &crate::pda::TOKEN_PROGRAM) }
fn tx(sig: &str) -> RpcTx { txjson::from_rpc(&json_file(&repo("testdata/wallet").join(format!("{sig}.json")))).unwrap() }
fn i(v: &Value) -> i64 { v.as_i64().unwrap_or_else(|| panic!("not an integer: {v}")) }

/// the §4.42 line of a fixture transaction (no token prices: none of the cases moves a non-SOL token)
fn line(sig: &str) -> Entry {
    let w = wallet();
    let x = tx(sig);
    let r = raw(&x, &w, &wsol_ata(&w), &crate::tx::pk(ROUTE));
    let e = entry(&r, &Head { sig, slot: x.slot.unwrap_or(0), idx: x.idx, t_ns: 1, attempt: None, pre_run: false }, 0.1, &no_prices);
    assert_eq!(e.categories.iter().map(|c| c.1).sum::<i64>(), e.equity_delta, "{sig}: the summing categories sum to equity_delta");
    assert_eq!(e.equity_delta - e.liquid_delta, e.token_value() + e.rent_locked as i64 - e.rent_reclaimed as i64, "{sig}: §4.42's identity");
    // the INPUT 7 round trip of the raw fields, and ledger.jsonl's
    assert_eq!(Raw::from_json(&r.json()).as_ref(), Some(&r), "{sig}");
    assert_eq!(Entry::from_json(&e.json()).as_ref(), Some(&e), "{sig}");
    e
}

/// PLAN WP-07 acceptance, golden ledger cases (F7): each case of testdata/legacy/expected.json, from its real
/// transaction: create only (a nonce account), wrap with the WSOL account's create, accumulator creation (p6#69:
/// rent_nonrecoverable 1,346,200, rent_locked 1,513,840), failed transactions, a bundle win with an ATA create (1,488,440
/// locked), a Token-2022 create (1,513,840), the bolt trade, a transfer in, a foreign failed transaction: every field and
/// the categories exactly
#[test]
fn golden_cases_on_real_transactions() {
    let expected = json_file(&repo("testdata/legacy/expected.json"));
    let cases = expected["cases"].as_object().unwrap();
    assert_eq!(cases.len(), 13);
    for (id, want) in cases {
        let e = line(want["sig"].as_str().unwrap());
        assert_eq!(e.kind, want["kind"].as_str().unwrap(), "{id}");
        assert_eq!(e.ok, want["ok"].as_bool().unwrap(), "{id}");
        for (k, got) in [("wallet_sol", e.wallet_sol), ("wsol", e.wsol), ("fee", e.fee as i64), ("tip", e.tip as i64), ("rent_locked", e.rent_locked as i64),
            ("rent_reclaimed", e.rent_reclaimed as i64), ("rent_nonrecoverable", e.rent_nonrecoverable as i64), ("liquid_delta", e.liquid_delta),
            ("equity_delta", e.equity_delta), ("trade_gross", e.trade_gross), ("trade_net", e.trade_net)] {
            assert_eq!(got, i(&want[k]), "{id} {k}");
        }
        let cats: Vec<(String, i64)> = want["categories"].as_array().unwrap().iter().map(|c| (c["cat"].as_str().unwrap().to_string(), i(&c["lamports"]))).collect();
        assert_eq!(e.categories.iter().map(|c| (c.0.to_string(), c.1)).collect::<Vec<_>>(), cats, "{id} categories");
        assert!(e.tokens.is_empty() && e.stranded.is_empty(), "{id}");
    }
    // the named numbers of PLAN WP-07's acceptance
    let acc = line(cases["bundle_win_accumulator_create"]["sig"].as_str().unwrap());
    assert_eq!((acc.rent_nonrecoverable, acc.rent_locked), (1_346_200, 1_513_840));
    assert_eq!(acc.created.iter().map(|c| (c.what, c.class, c.rent)).collect::<Vec<_>>(),
        vec![("token", RentClass::Recoverable, 1_513_840), ("other", RentClass::Nonrecoverable, 1_346_200)]);
    assert_eq!(acc.created[1].owner, Some(*PUMPSWAP), "the user volume accumulator");
    assert_eq!(line(cases["bundle_win_ata_create"]["sig"].as_str().unwrap()).rent_locked, 1_488_440);
    assert_eq!(line(cases["bundle_win_token2022_create"]["sig"].as_str().unwrap()).rent_locked, 1_513_840);
    let nonce = line(cases["nonce_create"]["sig"].as_str().unwrap());
    assert_eq!((nonce.created[0].what, nonce.created[0].class), ("nonce", RentClass::Recoverable));
    let bolt = line(cases["bolt_direct_win"]["sig"].as_str().unwrap());
    assert_eq!((bolt.trade_gross, bolt.trade_net, bolt.tip), (30_002_068, 28_973_467, 1_000_000));
}

/// res-pnl's p1-p10 decomposition, from the 119 landings' ledger lines: trade_net −2,337,448 (the trading net), equity
/// −3,683,648, liquid −18,720,448, rent locked 15,036,800, non-recoverable 1,346,200, gross 632,807, fees 2,632,511,
/// tips 337,744 (expected.json `ledger_sums_landings`)
#[test]
fn the_landings_reproduce_res_pnl() {
    let s = json_file(&repo("testdata/legacy/signatures.json"));
    let want = &json_file(&repo("testdata/legacy/expected.json"))["res_pnl_p1_p10"]["ledger_sums_landings"];
    let rows = s["landed"]["rows"].as_array().unwrap();
    assert_eq!(rows.len(), 119);
    let mut t = Totals::default();
    let (mut equity, mut liquid, mut fee, mut tip) = (0i64, 0i64, 0i64, 0i64);
    for r in rows {
        let e = line(r["sig"].as_str().unwrap());
        assert_eq!(e.kind, "route");
        assert_eq!(e.ok, r["ok"].as_bool().unwrap());
        t.add(&e);
        equity += e.equity_delta;
        liquid += e.liquid_delta;
        fee += e.fee as i64;
        tip += e.tip as i64;
    }
    assert_eq!((t.trade_net, equity, liquid, t.rent_locked, t.rent_nonrecoverable, t.trade_gross, fee, t.tips),
        (i(&want["trade_net"]), i(&want["equity_delta"]), i(&want["liquid_delta"]), i(&want["rent_locked"]), i(&want["rent_nonrecoverable"]), i(&want["trade_gross"]),
            i(&want["fee"]), i(&want["tip"])));
    assert_eq!((t.trade_net, fee, tip), (-2_337_448, 2_632_511, 337_744));
    assert_eq!(t.fee_win + t.fee_fail, fee, "every landing is a route: fee_win + fee_fail");
    assert_eq!((t.wins, t.landed_fail), (21, 98));
    // BUDGET.md's net spend of these landings: what they cost, the trading result included
    assert_eq!(t.net_spend(), fee + tip + 1_346_200 - 632_807);
}

/// wallet-synthesis §2: the 21 w5h2 and 2 w5h3 bundle wins and the bolt win, from their ledger lines
#[test]
fn the_wins_of_w5h2_and_w5h3() {
    let s = json_file(&repo("testdata/legacy/signatures.json"));
    let want = &json_file(&repo("testdata/legacy/expected.json"))["wallet_synthesis_s2"];
    let mut groups: BTreeMap<&str, Totals> = BTreeMap::new();
    let mut liquid: BTreeMap<&str, i64> = BTreeMap::new();
    for r in s["wins_w5h2_w5h3"]["rows"].as_array().unwrap() {
        let g = match (r["class"].as_str().unwrap(), &r["seg"].as_str().unwrap()[..4]) { ("direct_win", _) => "w5h2_bolt_win", (_, "w5h2") => "w5h2_bundle_wins", _ => "w5h3_bundle_wins" };
        let e = line(r["sig"].as_str().unwrap());
        assert!(e.ok && e.is_route());
        groups.entry(g).or_default().add(&e);
        *liquid.entry(g).or_default() += e.liquid_delta;
    }
    assert_eq!(groups.len(), 3);
    for (g, t) in &groups {
        let w = &want[*g];
        assert_eq!((t.wins as i64, t.trade_gross, t.tips, t.fee_win, t.rent_locked, liquid[g], t.trade_net),
            (i(&w["wins"]), i(&w["gross_round_trip"]), i(&w["tips"]), i(&w["fees"]), i(&w["rent_locked"]), i(&w["net_wallet_change"]), i(&w["net_ex_rent"])), "{g}");
    }
}

// ------------------------------------------------------------------ synthetic transactions

/// a transaction of `keys` (the wallet first: it pays) with `top` and `inner` instructions, its balances and token
/// balances
#[allow(clippy::too_many_arguments)]
fn synth(keys: &[Pk], top: Vec<PbIx>, inner: Vec<PbInnerIx>, pre: Vec<u64>, post: Vec<u64>, pre_tok: Vec<PbTokenBalance>, post_tok: Vec<PbTokenBalance>, fee: u64) -> RpcTx {
    let msg = PbMessage { header: Some(PbHeader { num_required_signatures: 1, num_readonly_signed_accounts: 0, num_readonly_unsigned_accounts: 0 }),
        account_keys: keys.iter().map(|k| k.to_vec()).collect(), recent_blockhash: vec![0; 32], instructions: top, versioned: false, address_table_lookups: vec![], config: None };
    let meta = PbMeta { err: None, fee, pre_balances: pre, post_balances: post, inner_instructions: vec![PbInnerIxs { index: 0, instructions: inner }], log_messages: vec![],
        pre_token_balances: pre_tok, post_token_balances: post_tok, inner_instructions_none: false, log_messages_none: false, loaded_writable_addresses: vec![],
        loaded_readonly_addresses: vec![], return_data: None, return_data_none: true, compute_units_consumed: None, cost_units: None };
    RpcTx { sig: [7; 64], slot: Some(500), idx: Some(1), block_time: None, tx: PbTransaction { signatures: vec![vec![7; 64]], message: Some(msg) }, meta: Some(meta), keys: keys.to_vec() }
}
fn tokbal(i: u32, mint: &Pk, owner: &Pk, amount: u64) -> PbTokenBalance {
    PbTokenBalance { account_index: i, mint: b58(mint), ui_token_amount: Some(PbUiAmount { decimals: 9, amount: amount.to_string() }), owner: b58(owner), program_id: b58(&crate::pda::TOKEN_PROGRAM) }
}
fn ix(program: u32, accounts: &[u8], data: Vec<u8>) -> PbIx { PbIx { program_id_index: program, accounts: accounts.to_vec(), data } }
fn inner(program: u32, accounts: &[u8], data: Vec<u8>) -> PbInnerIx { PbInnerIx { program_id_index: program, accounts: accounts.to_vec(), data, stack_height: Some(2) } }
fn create_ix(lamports: u64, space: u64, owner: &Pk) -> Vec<u8> {
    let mut d = 0u32.to_le_bytes().to_vec();
    d.extend(lamports.to_le_bytes());
    d.extend(space.to_le_bytes());
    d.extend(owner);
    d
}
fn transfer_ix(lamports: u64) -> Vec<u8> { let mut d = 2u32.to_le_bytes().to_vec(); d.extend(lamports.to_le_bytes()); d }

/// MEASUREMENT §4.42's two cases the wallet never made (testdata/legacy/README.md: built synthetically): a route win that
/// creates its mid token account and closes it in the same transaction (rent_locked = rent_reclaimed = R, equity = G −
/// F − T, the categories `trade_gross`, `tip`, `fee_win`), and an unwrap that closes the WSOL account holding A with rent R
/// (wallet +A + R − F, wsol −A, rent_reclaimed R, liquid R − F, equity −F: `fee_other`). And a route that strands a token
#[test]
fn create_and_close_and_unwrap() {
    let w = wallet();
    let wsol_acct = wsol_ata(&w);
    let (route, mid, mint, tip_acct) = (crate::tx::pk(ROUTE), [41u8; 32], [42u8; 32], crate::tx::pk("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5"));
    let (tokp, ata_p) = (*crate::pda::TOKEN_PROGRAM, *crate::pda::ATA_PROGRAM);
    let (g, f, t, r) = (50_000u64, 5_000u64, 30_000u64, 2_039_280u64);
    // keys: 0 wallet, 1 wsol account, 2 mid account (made and closed here), 3 route, 4 token program, 5 system, 6 ATA program, 7 tip account, 8 mint
    let keys = [w, wsol_acct, mid, route, tokp, SYSTEM, ata_p, tip_acct, mint];
    let x = synth(&keys,
        vec![ix(6, &[0, 2, 0, 8, 5, 4], vec![1]), ix(3, &[0, 1, 2], vec![2]), ix(4, &[2, 0, 0], vec![9]), ix(5, &[0, 7], transfer_ix(t))],
        vec![inner(5, &[0, 2], create_ix(r, 165, &tokp))],
        vec![1_000_000_000, 2_000_000_000 + 2_039_280, 0, 1, 1, 1, 1, 5_000_000, 1], vec![1_000_000_000 - f - t, 2_000_000_000 + 2_039_280 + g, 0, 1, 1, 1, 1, 5_000_000 + t, 1],
        vec![tokbal(1, &wsol(), &w, 2_000_000_000)], vec![tokbal(1, &wsol(), &w, 2_000_000_000 + g)], f);
    let rw = raw(&x, &w, &wsol_acct, &route);
    assert_eq!((rw.kind.as_str(), rw.rent_locked, rw.rent_reclaimed, rw.tip, rw.fee), ("route", r, r, t, f));
    let e = entry(&rw, &Head { sig: "cc", slot: 500, idx: None, t_ns: 1, attempt: None, pre_run: false }, 0.1, &no_prices);
    assert_eq!((e.wallet_sol, e.wsol, e.liquid_delta, e.equity_delta, e.trade_gross, e.trade_net),
        (-((f + t) as i64), g as i64, (g - f - t) as i64, (g - f - t) as i64, g as i64, (g - f - t) as i64));
    assert_eq!(e.categories, vec![("trade_gross", g as i64), ("tip", -(t as i64)), ("fee_win", -(f as i64))]);
    // the unwrap: keys 0 wallet, 1 wsol account, 2 token program
    let (a, rr) = (300_000_000u64, 2_039_280u64);
    let x = synth(&[w, wsol_acct, tokp], vec![ix(2, &[1, 0, 0], vec![9])], vec![], vec![1_000_000_000, a + rr, 1], vec![1_000_000_000 + a + rr - f, 0, 1],
        vec![tokbal(1, &wsol(), &w, a)], vec![], f);
    let rw = raw(&x, &w, &wsol_acct, &route);
    assert_eq!((rw.kind.as_str(), rw.rent_reclaimed, rw.closed[0].to), ("unwrap", rr, Some(w)));
    let e = entry(&rw, &Head { sig: "uw", slot: 500, idx: None, t_ns: 1, attempt: None, pre_run: false }, 0.1, &no_prices);
    assert_eq!((e.wallet_sol, e.wsol, e.liquid_delta, e.equity_delta), ((a + rr - f) as i64, -(a as i64), (rr - f) as i64, -(f as i64)));
    assert_eq!(e.categories, vec![("fee_other", -(f as i64))]);
    // a route that strands a token: its value (the quote less the haircut) is in trade_gross, and it is listed
    let x = synth(&[w, wsol_acct, mid, route], vec![ix(3, &[0, 1, 2], vec![2])], vec![], vec![100_000, 3_000_000, 2_039_280, 1], vec![100_000 - f, 3_000_000 - 40_000, 2_039_280, 1],
        vec![tokbal(1, &wsol(), &w, 1_000_000), tokbal(2, &mint, &w, 0)], vec![tokbal(1, &wsol(), &w, 1_000_000 - 40_000), tokbal(2, &mint, &w, 777)], f);
    let rw = raw(&x, &w, &wsol_acct, &route);
    let price = |m: &Pk, amt: u128| (*m == mint).then(|| ((amt * 50) as u64, "pool-x".to_string()));
    let e = entry(&rw, &Head { sig: "st", slot: 500, idx: None, t_ns: 1, attempt: None, pre_run: false }, 0.1, &price);
    assert_eq!((e.tokens[&b58(&mint)].value, e.stranded.clone()), ((777.0 * 50.0 * 0.9) as i64, vec![(b58(&mint), 777)]));
    assert_eq!(e.trade_gross, -40_000 + 34_965, "the WSOL spent plus the token's value");
    assert_eq!(e.stop_delta(), e.liquid_delta, "the stop basis counts no token value");
}

/// The PumpSwap user volume accumulator is the program's PDA of the payer: the arb-lab wallet's is BKPfj2Ht… (created by
/// w5h-p6#69); the frz wallet's is CUiyUSbx… (it exists: STAGE1-PLAN review F6), which the snapshots read as an owned
/// account that is not recoverable
#[test]
fn the_accumulator_is_the_payers_pda() {
    assert_eq!(b58(&accumulator_of(&wallet())), "BKPfj2HtknArpzzksCTUfpT2KRge2p4CzDe4JcKKp9HS");
    assert!(b58(&accumulator_of(&crate::tx::pk(FRZ))).starts_with("CUiyUSbx"), "{}", b58(&accumulator_of(&crate::tx::pk(FRZ))));
}

// ------------------------------------------------------------------ snapshots and reconciliation

fn acct(lamports: u64, owner: &Pk, data: &[u8]) -> Value {
    use base64::Engine as _;
    json!({ "lamports": lamports, "owner": b58(owner), "data": [base64::engine::general_purpose::STANDARD.encode(data), "base64"] })
}
fn token_data(mint: &Pk, owner: &Pk, amount: u64) -> Vec<u8> {
    let mut d = vec![0u8; 165];
    d[..32].copy_from_slice(mint);
    d[32..64].copy_from_slice(owner);
    d[64..72].copy_from_slice(&amount.to_le_bytes());
    d
}

const USDC: &str = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v";

/// a snapshot answer of the frz wallet's kind: native SOL, the WSOL account, a USDC account, the accumulator, an account
/// that does not exist
fn snap_answer(slot: u64, sol: u64, wsol_amt: u64, usdc: u64, why: &str) -> Value {
    let w = crate::tx::pk(FRZ);
    let (wa, ua, acc) = (wsol_ata(&w), crate::build::ata_of(&w, &crate::tx::pk(USDC), &crate::pda::TOKEN_PROGRAM), accumulator_of(&w));
    let tokp = *crate::pda::TOKEN_PROGRAM;
    json!({ "what": "snapshot", "why": why, "keys": [b58(&w), b58(&wa), b58(&ua), b58(&acc), b58(&[9u8; 32])],
        "answers": [{ "slot": slot, "values": [acct(sol, &SYSTEM, &[]), acct(wsol_amt + 2_039_280, &tokp, &token_data(&wsol(), &w, wsol_amt)),
            acct(2_039_280, &tokp, &token_data(&crate::tx::pk(USDC), &w, usdc)), acct(1_346_200, &PUMPSWAP, &[0u8; 137]), Value::Null] }],
        "slot_mismatch": false, "attempts": 1, "provider": "fake", "ms": 1.0, "error": null })
}
/// 1 USDC (10^6 raw) = 0.0069 SOL (USDC at $145/SOL)
fn usdc_price(m: &Pk, amt: u128) -> Option<(u64, String)> { (*m == crate::tx::pk(USDC)).then(|| ((amt * 6_900_000 / 1_000_000) as u64, "pool-usdc".into())) }

/// A snapshot from its RPC answer: SOL, the WSOL amount (its rent apart), the USDC amount and value (less the haircut),
/// the accumulator (owned, not recoverable), a missing account; the stop basis is SOL + WSOL only
#[test]
fn a_snapshot_of_the_frz_kind() {
    let w = crate::tx::pk(FRZ);
    let s = Snapshot::parse(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), &w, 0.1, &usdc_price, T0).unwrap();
    assert_eq!((s.sol, s.wsol, s.equity_stop(), s.equity_liquid()), (223_000_000, 191_500_000, 414_500_000, 414_500_000), "BUDGET.md's basis");
    assert_eq!((s.rent_recoverable, s.rent_nonrecoverable, s.missing.len(), s.other_owned.len()), (2 * 2_039_280, 1_346_200, 1, 1));
    assert_eq!(s.token_amounts(), [(USDC.to_string(), 22_970_000u128)].into_iter().collect());
    let usdc_value = (22_970_000u128 * 6_900_000 / 1_000_000) as f64 * 0.9;
    assert_eq!(s.token_value, usdc_value.floor() as u64);
    assert_eq!(s.equity_total(), 414_500_000 + 2 * 2_039_280 + s.token_value as i64);
    assert_eq!(Snapshot::from_json(&s.json()).as_ref(), Some(&s));
    assert!(Snapshot::parse(&json!({ "error": "rpc down" }), &w, 0.1, &usdc_price, T0).is_err());
}

fn snap(slot: u64, sol: u64, wsol_amt: u64, rent: u64) -> Snapshot {
    Snapshot { t_ns: T0 + slot, slot, sol, wsol: wsol_amt, rent_recoverable: rent, ..Default::default() }
}
fn e_at(sig: &str, slot: u64, wallet_sol: i64, wsol_d: i64, fee: u64) -> Entry {
    let r = Raw { kind: "route".into(), ok: wsol_d > 0, payer: true, wallet_sol, wsol: wsol_d, fee, ..Default::default() };
    entry(&r, &Head { sig, slot, idx: None, t_ns: T0 + slot, attempt: None, pre_run: false }, 0.1, &no_prices)
}

/// PLAN WP-07 acceptance (reconciliation, synthetic snapshot pairs): inside the tolerance on both bases, outside it on
/// either, a token amount that differs by one unit; the entries outside the window are left out. And on real data: the
/// 119 landings between their first pre-state and last post-state reconcile to 0 on both bases
#[test]
fn reconciliation_both_bases() {
    let a = snap(100, 1_000_000_000, 500_000_000, 2_039_280);
    let es = [e_at("x", 101, -5_000, 0, 5_000), e_at("y", 150, -15_000, 40_000, 5_000), e_at("z", 201, -5_000, 0, 5_000)];
    let refs: Vec<&Entry> = es.iter().collect();
    // within: the window holds x and y (z is past `to`)
    let b = snap(200, 1_000_000_000 - 20_000, 500_000_000 + 40_000, 2_039_280);
    let (l, ok) = reconcile(&a, &b, &refs, 10_000, T0);
    assert!(ok, "{l}");
    assert_eq!((l["entries"].as_u64(), l["residual"].as_i64(), l["liquid"]["residual"].as_i64()), (Some(2), Some(0), Some(0)));
    assert_eq!(l["by_category"]["fee_fail"].as_i64(), Some(-5_000));
    // 9,999 unexplained on the liquid basis: still in; 10,001: a miss on both bases
    let b2 = snap(200, 1_000_000_000 - 20_000 - 9_999, 500_000_000 + 40_000, 2_039_280);
    assert!(reconcile(&a, &b2, &refs, 10_000, T0).1);
    let b3 = snap(200, 1_000_000_000 - 20_000 - 10_001, 500_000_000 + 40_000, 2_039_280);
    let (l, ok) = reconcile(&a, &b3, &refs, 10_000, T0);
    assert!(!ok && l["liquid"]["residual"] == -10_001 && l["residual"] == -10_001, "{l}");
    // the total basis alone: recoverable rent that vanished (an account closed elsewhere)
    let b4 = snap(200, 1_000_000_000 - 20_000, 500_000_000 + 40_000, 2_039_280 - 20_000);
    let (l, ok) = reconcile(&a, &b4, &refs, 10_000, T0);
    assert!(!ok && l["liquid"]["residual"] == 0 && l["residual"] == -20_000, "{l}");
    // a token amount off by one unit: a miss whatever the lamports
    let mut b5 = b.clone();
    b5.tokens.push(SnapTok { mint: USDC.into(), account: [1; 32], program: *crate::pda::TOKEN_PROGRAM, amount: 1, rent: 0, value: None, mid_src: None });
    let (l, ok) = reconcile(&a, &b5, &refs, 10_000, T0);
    assert!(!ok && l["token_amounts"][0]["ok"] == false, "{l}");
    // the real landings: res-pnl's liquid start and end, the rent their creations locked
    let s = json_file(&repo("testdata/legacy/signatures.json"));
    let liq = &json_file(&repo("testdata/legacy/expected.json"))["res_pnl_p1_p10"]["liquid"]["basis_token_amount"];
    let entries: Vec<Entry> = s["landed"]["rows"].as_array().unwrap().iter().map(|r| line(r["sig"].as_str().unwrap())).collect();
    let first = entries.iter().map(|e| e.slot).min().unwrap();
    let last = entries.iter().map(|e| e.slot).max().unwrap();
    let from = snap(first - 1, i(&liq["start"]) as u64 - 4_000_000_000, 4_000_000_000, 1_488_440);
    let to = snap(last, i(&liq["end"]) as u64 - 4_000_000_000, 4_000_000_000, 1_488_440 + 15_036_800);
    let refs: Vec<&Entry> = entries.iter().collect();
    let (l, ok) = reconcile(&from, &to, &refs, 10_000, T0);
    assert!(ok, "{l}");
    assert_eq!((l["entries"].as_u64(), l["residual"].as_i64(), l["liquid"]["residual"].as_i64(), l["sum_entries"].as_i64()), (Some(119), Some(0), Some(0), Some(-3_683_648)));
}

fn landing(attempt: u64, sig: &str, fin: &'static str, landed: bool, fee: u64, tip: u64, rt: i64) -> Landing {
    Landing { attempt, sig: sig.into(), fin, landed, ok: landed && rt > 0, src: "wallet", wallet_seen: true, fee, tip, round_trip: rt, rt_unknown: false,
        refused: fin == "not_landed_refused", t_final: 0 }
}

/// The executor's money against the chain (the brief: chain truth vs the executor's accounting, within 10,000): equal
/// nets pass; a difference over the tolerance, a landing the executor counts as not landed, a route landing nobody made,
/// and above all a refused bundle that landed (this segment's or an earlier one's) are misses; a landing still without
/// its record is listed, not a miss
#[test]
fn the_executors_money_against_the_chain() {
    let mut entries = BTreeMap::new();
    let win = { let r = Raw { kind: "route".into(), ok: true, payer: true, wallet_sol: -36_499, wsol: 49_000, fee: 5_000, tip: 31_499, ..Default::default() };
        entry(&r, &Head { sig: "a", slot: 10, idx: None, t_ns: 1, attempt: Some(0), pre_run: false }, 0.1, &no_prices) };
    entries.insert("a".to_string(), win);
    entries.insert("b".to_string(), e_at("b", 10, -5_000, 0, 5_000));
    let none = HashMap::new();
    let view = vec![landing(0, "a", "landed_ok", true, 5_000, 31_499, 49_000), landing(1, "b", "landed_fail", true, 5_000, 0, 0), landing(2, "c", "not_landed_expired", false, 0, 0, 0)];
    let (l, ok) = exec_recon(&entries, &view, &none, 10_000);
    assert!(ok, "{l}");
    assert_eq!((l["landings"].as_u64(), l["diff"].as_i64()), (Some(2), Some(0)));
    // the executor counted a round trip 12,000 off
    let mut v2 = view.clone();
    v2[0].round_trip = 61_000;
    let (l, ok) = exec_recon(&entries, &v2, &none, 10_000);
    assert!(!ok && l["diff"] == 12_000, "{l}");
    // a provisional landing (the expiry check found it, no record yet): listed; the money it lacks is the snapshots' to see
    let mut v3 = view.clone();
    v3.push(Landing { src: "statuses", wallet_seen: false, ..landing(3, "d", "landed_ok", true, 5_000, 31_499, 0) });
    let (l, ok) = exec_recon(&entries, &v3, &none, 10_000);
    assert!(ok && l["provisional"].as_array().unwrap().len() == 1, "{l}");
    // a refused bundle that landed: a miss, named
    let v4 = vec![view[0].clone(), landing(1, "b", "not_landed_refused", false, 0, 0, 0)];
    let (l, ok) = exec_recon(&entries, &v4, &none, 10_000);
    assert!(!ok && l["refused_landed"][0]["sig"] == "b", "{l}");
    // the chain shows one landed that the executor counts as expired
    let v5 = vec![view[0].clone(), landing(1, "b", "not_landed_expired", false, 0, 0, 0)];
    let (l, ok) = exec_recon(&entries, &v5, &none, 10_000);
    assert!(!ok && l["not_counted"][0]["sig"] == "b", "{l}");
    // a route landing of ours that no attempt made (another process on the wallet?) is a miss; an earlier segment's open
    // attempt explains it; an earlier segment's refused one that landed is a miss
    let v6 = vec![view[0].clone()];
    let (l, ok) = exec_recon(&entries, &v6, &none, 10_000);
    assert!(!ok && l["unknown_route_landings"][0]["sig"] == "b", "{l}");
    // one the executor made (the record names its attempt) but no longer keeps: not unknown
    let mut kept = entries.clone();
    kept.get_mut("b").unwrap().attempt = Some(1);
    assert!(exec_recon(&kept, &v6, &none, 10_000).1);
    let earlier: HashMap<String, Earlier> = [("b".to_string(), Earlier { segment: "c-p1".into(), attempt: 9, fin: "unsettled".into() })].into_iter().collect();
    let (l, ok) = exec_recon(&entries, &v6, &earlier, 10_000);
    assert!(ok && l["earlier_landed"][0]["segment"] == "c-p1" && l["unknown_route_landings"].as_array().unwrap().is_empty(), "{l}");
    let refused: HashMap<String, Earlier> = [("b".to_string(), Earlier { segment: "c-p1".into(), attempt: 9, fin: "not_landed_refused".into() })].into_iter().collect();
    let (l, ok) = exec_recon(&entries, &v6, &refused, 10_000);
    assert!(!ok && l["refused_landed"][0]["segment"] == "c-p1", "{l}");
}

/// F34: one common slot. One chunk: one slot. Two chunks whose answers' slots differ: asked again (the later calls with
/// `minContextSlot` = the first answer's slot), then written `slot_mismatch`; a call that fails: asked again, then `error`
#[tokio::test(start_paused = true)]
async fn snapshot_calls_on_one_slot() {
    use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
    type Calls = Arc<std::sync::Mutex<Vec<Value>>>;
    let keys: Vec<Pk> = (0..150u8).map(|n| [n; 32]).collect();
    let calls: Calls = Default::default();
    let slot = Arc::new(AtomicU64::new(100));
    let mk = |calls: Calls, slot: Arc<AtomicU64>, step: u64, fail: bool| {
        move |p: Value| {
            let (calls, slot) = (calls.clone(), slot.clone());
            async move {
                calls.lock().unwrap().push(p.clone());
                if fail { return Err("down".to_string()); }
                let s = slot.fetch_add(step, Relaxed);
                let n = p[0].as_array().unwrap().len();
                Ok((json!({ "context": { "slot": s }, "value": vec![Value::Null; n] }), "fake".to_string()))
            }
        }
    };
    let v = fetch_with(mk(calls.clone(), slot.clone(), 0, false), keys[..80].to_vec(), 3, "start").await;
    assert_eq!((v["slot_mismatch"].as_bool(), v["attempts"].as_u64(), v["answers"].as_array().unwrap().len()), (Some(false), Some(1), 1));
    calls.lock().unwrap().clear();
    let v = fetch_with(mk(calls.clone(), slot.clone(), 0, false), keys.clone(), 3, "hourly").await;
    assert_eq!((v["slot_mismatch"].as_bool(), v["answers"].as_array().unwrap().len()), (Some(false), 2), "two chunks, one slot");
    assert_eq!(calls.lock().unwrap()[1][1]["minContextSlot"].as_u64(), Some(100), "the second chunk asks the first answer's slot");
    calls.lock().unwrap().clear();
    let v = fetch_with(mk(calls.clone(), slot.clone(), 1, false), keys.clone(), 3, "hourly").await;
    assert_eq!((v["slot_mismatch"].as_bool(), v["attempts"].as_u64()), (Some(true), Some(4)), "asked 1 + 3 times");
    assert_eq!(calls.lock().unwrap().len(), 8);
    let v = fetch_with(mk(calls.clone(), slot, 0, true), keys, 2, "stop").await;
    assert_eq!((v["error"].as_str(), v["attempts"].as_u64()), (Some("down"), Some(3)));
}

// ------------------------------------------------------------------ the ledger on a virtual clock

/// a ledger of the frz wallet in its own directory, bound to a fresh session (its gate live, as a canary's)
fn rig(name: &str, cfg_extra: impl FnOnce(&mut crate::config::SupervisorCfg)) -> (Ledger, Arc<Session>, PathBuf, Rec) {
    let dir = std::env::temp_dir().join(format!("arbx-ledger-{name}-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    rig_at(dir, name, cfg_extra)
}

/// `rig` recording into `dir` (a segment directory of a campaign)
fn rig_at(dir: PathBuf, name: &str, cfg_extra: impl FnOnce(&mut crate::config::SupervisorCfg)) -> (Ledger, Arc<Session>, PathBuf, Rec) {
    std::fs::create_dir_all(&dir).unwrap();
    let rec = rec::start(rec::Opts { dir: dir.clone(), run: name.into(), producer: "test".into(), cfg: Default::default(), feeds: vec![], monitor: false, echo: None }).unwrap();
    let mut sc = crate::config::SupervisorCfg { test_budget_lamports: 34_000_000, ..Default::default() };
    cfg_extra(&mut sc);
    let budget = sc.test_budget_lamports;
    let mut l = Ledger::new(LedgerCfg::default(), sc, crate::tx::pk(FRZ), rec.clone(), name);
    // these tests take a snapshot an hour (or fewer): the money view's freshness has tests of its own
    l.cfg.max_view_age_s = 48 * 3_600;
    let sess = Session::new();
    l.bind(sess.gate.clone(), sess.stopper.clone());
    l.set_campaign(History::default(), Some(budget), None, None);
    (l, sess, dir, rec)
}
#[allow(clippy::too_many_arguments)]
fn wtx(sig: &str, slot: u64, kind: &str, ok: bool, wallet_sol: i64, wsol_d: i64, fee: u64, tip: u64) -> Value {
    let r = Raw { kind: kind.into(), ok, payer: true, wallet_sol, wsol: wsol_d, fee, tip, ..Default::default() };
    json!({ "sig": sig, "slot": slot, "ok": ok, "attempt": null, "ledger": r.json() })
}
fn no_landings() -> Vec<Landing> { Vec::new() }

/// OD-11 through the ledger on a virtual clock: the start snapshot sets the floor (start SOL + WSOL − the test budget)
/// and the USDC floor; losses inside the hourly cap change nothing; the loss that takes the rolling hour past 0.02 SOL
/// puts the gate in shadow and stops the run with `equity_hour` (exit 20); nothing sends before the first snapshot
#[test]
fn the_hour_rule_through_the_ledger() {
    let (mut l, sess, dir, rec) = rig("hour", |_| {});
    assert_eq!(l.tick(T0, &no_landings), MoneyView::default(), "no start equity: the executor refuses equity_unknown");
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0 + S, &usdc_price);
    assert_eq!(l.sup.limits.floor, Some(414_500_000 - 34_000_000), "start SOL + WSOL − the budget");
    assert_eq!(l.sup.limits.token_floors.get(USDC), Some(&(22_970_000 - 22_970)));
    let v = l.tick(T0 + 2 * S, &no_landings);
    assert_eq!((v.equity_known, v.liquid, v.wsol), (true, Some(414_500_000), Some(191_500_000)));
    // landed tips and fees: 0.019 SOL within the hour
    let mut t = T0 + 10 * S;
    for k in 0..19u64 {
        t += M;
        l.on_wallet_tx(&wtx(&format!("f{k}"), 1_001 + k, "route", true, -1_000_000, 0, 5_000, 995_000), t, &usdc_price, None);
        l.tick(t, &no_landings);
    }
    assert!(sess.gate.allows(), "19M: under the cap");
    t += M;
    l.on_wallet_tx(&wtx("f19", 1_100, "route", true, -2_000_000, 0, 5_000, 1_995_000), t, &usdc_price, None);
    l.tick(t, &no_landings);
    assert_eq!(sess.stopper.info().map(|i| i.reason), Some(StopReason::EquityHour));
    assert_eq!(sess.gate.mode(), GateMode::Stopped, "shadow, then the stop closed it for good");
    rec.sync();
    let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
    assert!(ev.iter().any(|e| e["kind"] == "gate_change" && e["detail"]["reason"] == "equity_hour"), "{ev:?}");
    assert!(ev.iter().any(|e| e["kind"] == "equity_hour" && e["detail"]["drop"] == 21_000_000));
    assert_eq!(crate::rec::read_jsonl(&dir, "ledger").unwrap().len(), 20);
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

/// The floor through the ledger: a slow loss (under the hourly cap) that reaches start − budget stops the run with
/// `equity_floor`; a USDC decrease past its tolerance stops it with `token_floor`
#[test]
fn the_floor_and_the_token_floor_through_the_ledger() {
    let (mut l, sess, dir, rec) = rig("floor", |c| c.test_budget_lamports = 5_000_000);
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    let mut t = T0;
    for k in 0..6u64 {
        t += 20 * M;
        l.on_wallet_tx(&wtx(&format!("f{k}"), 1_001 + k, "route", false, -1_000_000, 0, 1_000_000, 0), t, &usdc_price, None);
        l.tick(t, &no_landings);
        if k < 5 { assert!(!sess.stopper.stopping(), "{k}: 5M is the budget"); }
    }
    assert_eq!(sess.stopper.info().map(|i| (i.reason, i.reason.exit_code())), Some((StopReason::EquityFloor, 20)));
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
    // the USDC floor (a route that sold the USDC holding: its quantity fell)
    let (mut l, sess, dir, rec) = rig("tokfloor", |_| {});
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    let usdc = crate::tx::pk(USDC);
    let r = Raw { kind: "route".into(), ok: true, payer: true, wallet_sol: -5_000, wsol: 150_000_000, fee: 5_000, tokens: [(usdc, -22_000_000i128)].into_iter().collect(), ..Default::default() };
    l.on_wallet_tx(&json!({ "sig": "sold", "slot": 1_001, "ok": true, "ledger": r.json() }), T0 + M, &usdc_price, None);
    l.tick(T0 + M, &no_landings);
    assert_eq!(sess.stopper.info().map(|i| i.reason), Some(StopReason::TokenFloor), "SOL + WSOL rose, the USDC holding fell: its own reason");
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

/// The hourly reconciliation through the ledger: decided `recon_grace_s` after its snapshot; a clean window passes; a
/// window whose balances moved without an entry is a miss (no RPC to search with: decided at once), which puts the gate
/// in shadow (`reconcile_miss`, sticky) without stopping the run, and is written to recon.jsonl; the executor's view is
/// read only when a reconciliation is decided
#[test]
fn the_hourly_reconciliation_through_the_ledger() {
    let (mut l, sess, dir, rec) = rig("recon", |_| {});
    let asked = std::cell::Cell::new(0);
    let land = || { asked.set(asked.get() + 1); vec![landing(0, "w1", "landed_ok", true, 5_000, 31_499, 49_000)] };
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    l.on_wallet_tx(&wtx("w1", 1_010, "route", true, -36_499, 49_000, 5_000, 31_499), T0 + M, &usdc_price, Some(49_000));
    l.tick(T0 + 2 * M, &land);
    // the hourly snapshot: balances moved by exactly the entry
    l.on_input(&snap_answer(2_000, 223_000_000 - 36_499, 191_500_000 + 49_000, 22_970_000, "hourly"), T0 + 60 * M, &usdc_price);
    l.tick(T0 + 60 * M + 30 * S, &land);
    assert_eq!(asked.get(), 0, "not decided before the grace");
    l.tick(T0 + 61 * M, &land);
    assert_eq!(asked.get(), 1);
    assert!(sess.gate.allows());
    // F34: a snapshot whose answers' slots differed is written, never reconciled (not a miss), and taken again only
    // `snapshot_retry_s` later (the hourly one waits too)
    let mut bad = snap_answer(2_500, 1, 1, 0, "hourly");
    bad["slot_mismatch"] = json!(true);
    l.on_input(&bad, T0 + 90 * M, &usdc_price);
    assert_eq!((l.retry_at, l.next_periodic >= T0 + 90 * M + 30 * S), (Some(T0 + 90 * M + 30 * S), true));
    l.tick(T0 + 95 * M, &land);
    assert!(sess.gate.allows() && l.pending.is_empty(), "no reconciliation of a mismatched snapshot");
    // the next hour: 15,000 lamports left the wallet with no entry
    l.on_input(&snap_answer(3_000, 223_000_000 - 36_499 - 15_000, 191_500_000 + 49_000, 22_970_000, "hourly"), T0 + 120 * M, &usdc_price);
    l.tick(T0 + 122 * M, &land);
    assert_eq!((sess.gate.reason().as_str(), sess.gate.sticky(), sess.stopper.stopping()), ("reconcile_miss", true, false));
    rec.sync();
    let r = crate::rec::read_jsonl(&dir, "recon").unwrap();
    assert_eq!(r.len(), 2);
    assert_eq!((r[1]["from"]["slot"].as_u64(), r[1]["to"]["slot"].as_u64()), (Some(2_000), Some(3_000)), "from the last good snapshot");
    let sn = crate::rec::read_jsonl(&dir, "snapshots").unwrap();
    assert_eq!(sn.iter().filter(|x| x["slot_mismatch"] == json!(true)).count(), 1);
    assert_eq!((r[0]["ok"].as_bool(), r[0]["executor"]["landings"].as_u64()), (Some(true), Some(1)));
    assert_eq!((r[1]["ok"].as_bool(), r[1]["liquid"]["residual"].as_i64(), r[1]["action"].as_str()), (Some(false), Some(-15_000), Some("shadow")));
    let m = l.money_json(T0 + 122 * M, json!({}), 0);
    assert_eq!((m["last_recon_ok"].as_bool(), m["recon_misses_total"].as_u64(), m["stop_basis"].as_str()), (Some(false), Some(1), Some("net_spend")));
    assert_eq!((m["trade_gross_total"].as_i64(), m["tips_total"].as_i64(), m["fees_win_total"].as_i64()), (Some(49_000), Some(31_499), Some(5_000)));
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

/// The executor's provisional money (WP-05 hand-off) settles by signature: a landing the expiry check found first is
/// listed as provisional until its record comes; its record makes it a matched landing (the money from the chain)
#[test]
fn provisional_money_settles_by_signature() {
    let (mut l, sess, dir, rec) = rig("prov", |_| {});
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    let prov = Landing { src: "statuses", wallet_seen: false, round_trip: 0, rt_unknown: true, ..landing(0, "p1", "landed_ok", true, 5_000, 31_499, 0) };
    let settled = landing(0, "p1", "landed_ok", true, 6_000, 31_499, 49_000);
    l.on_input(&snap_answer(2_000, 223_000_000, 191_500_000, 22_970_000, "hourly"), T0 + 60 * M, &usdc_price);
    l.tick(T0 + 62 * M, &|| vec![prov.clone()]);
    rec.sync();
    let r = crate::rec::read_jsonl(&dir, "recon").unwrap();
    assert_eq!((r[0]["ok"].as_bool(), r[0]["executor"]["provisional"][0]["sig"].as_str()), (Some(true), Some("p1")), "listed, not a miss");
    // its record comes: the ledger has it, and the executor (amended by the same record) agrees with the chain
    l.on_wallet_tx(&wtx("p1", 2_100, "route", true, -37_499, 49_000, 6_000, 31_499), T0 + 63 * M, &usdc_price, Some(49_000));
    l.on_input(&snap_answer(3_000, 223_000_000 - 37_499, 191_500_000 + 49_000, 22_970_000, "hourly"), T0 + 120 * M, &usdc_price);
    l.tick(T0 + 122 * M, &|| vec![settled.clone()]);
    rec.sync();
    let r = crate::rec::read_jsonl(&dir, "recon").unwrap();
    assert_eq!((r[1]["ok"].as_bool(), r[1]["executor"]["landings"].as_u64(), r[1]["executor"]["provisional"].as_array().map(|a| a.len())), (Some(true), Some(1), Some(0)));
    assert!(sess.gate.allows());
    // had the executor kept its provisional base fee and unknown round trip, the chain shows the difference
    let (x, ok) = exec_recon(&l.entries, &[Landing { wallet_seen: true, ..prov.clone() }], &HashMap::new(), 10_000);
    assert!(!ok && x["diff"].as_i64() == Some(-(5_000 + 31_499) - 11_501), "{x}");
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

// ------------------------------------------------------------------ the campaign across segments

/// a finished segment `name` of a campaign: its snapshots, ledger lines and outcomes (plain files, as a reader finds them)
fn write_segment(camp: &Path, name: &str, started: u64, snaps: &[Snapshot], entries: &[Entry], outcomes: &[Value]) {
    let d = camp.join(name);
    std::fs::create_dir_all(&d).unwrap();
    std::fs::write(d.join("meta.json"), json!({ "run": { "started_ns": started } }).to_string()).unwrap();
    let lines = |head: &str, v: Vec<Value>| format!("{}\n{}\n", json!({ "schema": head, "file_seq": 0 }), v.iter().map(|x| x.to_string()).collect::<Vec<_>>().join("\n"));
    std::fs::write(d.join("snapshots.jsonl"), lines("arbx.snapshots/1.0", snaps.iter().map(Snapshot::json).collect())).unwrap();
    std::fs::write(d.join("ledger.jsonl"), lines("arbx.ledger/1.0", entries.iter().map(Entry::json).collect())).unwrap();
    std::fs::write(d.join("outcomes.jsonl"), lines("arbx.outcomes/2.0", outcomes.to_vec())).unwrap();
}
/// a snapshot of the frz kind (`snap_answer`'s accounts) as a segment's snapshots.jsonl holds it
fn frz_snap(slot: u64, sol: u64, wsol_amt: u64, usdc: u64, t: u64) -> Snapshot {
    Snapshot::parse(&snap_answer(slot, sol, wsol_amt, usdc, "x"), &crate::tx::pk(FRZ), 0.1, &usdc_price, t).unwrap()
}
fn entry_t(sig: &str, slot: u64, t: u64, lost: i64) -> Entry {
    let r = Raw { kind: "route".into(), ok: false, payer: true, wallet_sol: -lost, fee: lost as u64, ..Default::default() };
    entry(&r, &Head { sig, slot, idx: None, t_ns: t, attempt: None, pre_run: false }, 0.1, &no_prices)
}

/// PLAN WP-07 acceptance (F8, campaign stops across two simulated segments): segment 2 boots with the campaign directory
/// holding segment 1's ledger and snapshots. A loss of 0.012 SOL at the end of segment 1 and 0.009 SOL at the start of
/// segment 2 (within an hour) fires the hour rule, which neither half does alone; a slower loss spread over both trips the
/// day rule; the campaign's start (its first snapshot, read from the chain) sets segment 2's floor
#[test]
fn campaign_stops_across_two_segments() {
    let camp = std::env::temp_dir().join(format!("arbx-camp-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    std::fs::create_dir_all(&camp).unwrap();
    std::fs::write(camp.join("campaign.json"), json!({ "budget": { "test_budget_lamports": 34_000_000 } }).to_string()).unwrap();
    let s0 = frz_snap(1_000, 223_000_000, 191_500_000, 22_970_000, T0);
    let end1 = T0 + 59 * M;
    let seg1 = [entry_t("a", 1_100, T0 + 50 * M, 6_000_000), entry_t("b", 1_200, T0 + 55 * M, 6_000_000)];
    let s1 = frz_snap(1_300, 223_000_000 - 12_000_000, 191_500_000, 22_970_000, end1);
    write_segment(&camp, "c-p1", T0, &[s0, s1], &seg1, &[json!({ "attempt": 5, "sig": "late", "final": "unsettled" })]);
    let h = history(&camp, Some("c-p2"), end1 + M, DAY_NS);
    assert_eq!((h.segments_read.clone(), h.start.as_ref().map(|s| s.equity_stop), h.test_budget), (vec!["c-p1".to_string()], Some(414_500_000), Some(34_000_000)));
    assert_eq!(h.series.value_at(end1), Some(414_500_000 - 12_000_000));
    assert_eq!(h.earlier.get("late").map(|e| (e.attempt, e.fin.as_str())), Some((5, "unsettled")));
    // segment 2 boots with the campaign: its floor is the campaign's (its own start is 12M lower)
    let (mut l, sess, dir, rec) = rig("c-p2", |_| {});
    l.set_campaign(h, Some(34_000_000), Some(22_000_000), None);
    l.on_input(&snap_answer(2_000, 211_000_000, 191_500_000, 22_970_000, "start"), end1 + 2 * M, &usdc_price);
    assert_eq!(l.sup.limits.floor, Some(414_500_000 - 34_000_000), "the campaign's start − the budget (above its own start − the budget left)");
    l.tick(end1 + 3 * M, &no_landings);
    assert!(sess.gate.allows(), "12M in the hour so far");
    l.on_wallet_tx(&wtx("c", 2_100, "route", false, -9_000_000, 0, 9_000_000, 0), end1 + 4 * M, &usdc_price, None);
    l.tick(end1 + 4 * M, &no_landings);
    assert_eq!(sess.stopper.info().map(|i| i.reason), Some(StopReason::EquityHour), "12M in segment 1 + 9M in segment 2 within the hour");
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
    // the day rule: 0.16 SOL over 20 hours across both segments, 8M an hour
    let camp2 = camp.join("day");
    std::fs::create_dir_all(&camp2).unwrap();
    let s0 = frz_snap(1_000, 300_000_000, 200_000_000, 0, T0);
    let seg1: Vec<Entry> = (1..=12u64).map(|k| entry_t(&format!("d{k}"), 1_000 + k, T0 + k * 60 * M, 8_000_000)).collect();
    write_segment(&camp2, "d-p1", T0, &[s0], &seg1, &[]);
    let h = history(&camp2, None, T0 + 13 * 60 * M, DAY_NS);
    assert_eq!(h.equity_stop_now, Some(500_000_000 - 96_000_000));
    let (mut l, sess, dir, rec) = rig("d-p2", |c| { c.test_budget_lamports = 0; });
    l.set_campaign(h, None, None, None);
    l.on_input(&snap_answer(5_000, 204_000_000, 200_000_000, 0, "start"), T0 + 13 * 60 * M, &no_prices);
    for k in 13..=20u64 {
        l.on_wallet_tx(&wtx(&format!("d{k}"), 5_000 + k, "route", false, -8_000_000, 0, 8_000_000, 0), T0 + k * 60 * M, &no_prices, None);
        l.tick(T0 + k * 60 * M, &no_landings);
        if k < 19 { assert!(!sess.stopper.stopping(), "{k}"); }
    }
    assert_eq!(sess.stopper.info().map(|i| i.reason), Some(StopReason::EquityDay), "152M within 24 h, over two segments");
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
    let _ = std::fs::remove_dir_all(&camp);
}

/// spend.json (BUDGET.md's numbers): per segment and in all, each signature once (a pre-run line written again by the
/// next segment is marked `dup` and not counted twice), the budget left
#[test]
fn spend_summary_for_budget_md() {
    let camp = std::env::temp_dir().join(format!("arbx-spend-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    std::fs::create_dir_all(&camp).unwrap();
    std::fs::write(camp.join("campaign.json"), json!({ "budget": { "test_budget_lamports": 34_000_000 } }).to_string()).unwrap();
    let win = { let r = Raw { kind: "route".into(), ok: true, payer: true, wallet_sol: -36_499, wsol: 49_000, fee: 5_000, tip: 31_499, ..Default::default() };
        entry(&r, &Head { sig: "w", slot: 10, idx: None, t_ns: T0, attempt: Some(0), pre_run: false }, 0.1, &no_prices) };
    let fail = entry_t("f", 11, T0 + 1, 7_000);
    write_segment(&camp, "s-p1", T0, &[Snapshot { t_ns: T0 - 1, ..snap(9, 100, 100, 0) }], &[win, fail.clone()], &[]);
    let mut dup_line = fail.json();
    dup_line["pre_run"] = json!(true);
    dup_line["dup"] = json!(true);
    write_segment(&camp, "s-p2", T0 + 10, &[], &[], &[]);
    std::fs::write(camp.join("s-p2").join("ledger.jsonl"), format!("{}\n{}\n", json!({ "schema": "arbx.ledger/1.0", "file_seq": 0 }), dup_line)).unwrap();
    let v = spend_json(&camp, "s", T0 + 100);
    assert_eq!((v["total"]["fees"].as_i64(), v["total"]["tips"].as_i64(), v["total"]["trade_gross"].as_i64(), v["total"]["net_spend"].as_i64()),
        (Some(12_000), Some(31_499), Some(49_000), Some(12_000 + 31_499 - 49_000)));
    assert_eq!((v["budget"]["remaining"].as_i64(), v["segments"].as_array().unwrap().len()), (Some(34_000_000 - (12_000 + 31_499 - 49_000)), 2));
    assert!(v["budget_md_row"].as_str().unwrap().starts_with(&format!("| {} | s | 12000 | 31499 |", utc_date(T0 + 100))), "{}", v["budget_md_row"]);
    assert_eq!(utc_date(1_759_622_400_000_000_000), "2025-10-05");
    let _ = std::fs::remove_dir_all(&camp);
}

// ------------------------------------------------------------------ review WP-07: the fixes

/// Review WP-07 #4: the stops measure the net spend, so the owner's transfers move nothing. A deposit of 0.1 SOL does not
/// extend a 5,000,000 budget: the second 4,500,000 loss passes it (`equity_floor`) while SOL + WSOL (505.5M) is far above
/// the start less the budget (409.5M: the raw floor the review traced would never have fired, 103.5M later). A
/// withdrawal of 25,005,000 trips nothing (on SOL + WSOL it was `equity_hour`): its fee is spend, the transfer is recorded
/// and alerted (`owner_transfer`, Warn) and the reconciliation lists it and passes
#[test]
fn owner_transfers_never_move_the_stops() {
    let (mut l, sess, dir, rec) = rig("own-dep", |c| c.test_budget_lamports = 5_000_000);
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    assert_eq!(l.sup.limits.floor, Some(414_500_000 - 5_000_000));
    let mut t = T0 + M;
    let (_, notes) = crate::notify::capture(|| { l.on_wallet_tx(&wtx("dep", 1_001, "transfer_in", true, 100_000_000, 0, 0, 0), t, &usdc_price, None); l.tick(t, &no_landings); });
    assert_eq!(notes.iter().filter(|n| n.kind == "owner_transfer").map(|n| n.level).collect::<Vec<_>>(), vec![Level::Warn]);
    assert_eq!((l.spent(), l.stop_value(), l.equity_stop()), (0, Some(414_500_000), Some(514_500_000)), "the deposit is in the balance, never in the spend");
    t += 60 * M;
    l.on_wallet_tx(&wtx("loss0", 1_100, "route", false, -4_500_000, 0, 4_500_000, 0), t, &usdc_price, None);
    l.tick(t, &no_landings);
    assert!(!sess.stopper.stopping() && sess.gate.allows(), "4.5M of the 5M budget");
    t += 60 * M;
    l.on_wallet_tx(&wtx("loss1", 1_101, "route", false, -4_500_000, 0, 4_500_000, 0), t, &usdc_price, None);
    l.tick(t, &no_landings);
    assert_eq!(sess.stopper.info().map(|i| i.reason), Some(StopReason::EquityFloor), "9M spent against a 5M budget, the 100M deposit notwithstanding");
    assert!(l.equity_stop().unwrap() > 414_500_000 - 5_000_000, "SOL + WSOL stayed above the old raw floor");
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
    // a withdrawal: no stop; recorded, alerted, reconciled
    let (mut l, sess, dir, rec) = rig("own-wd", |_| {});
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    let (_, notes) = crate::notify::capture(|| { l.on_wallet_tx(&wtx("wd", 1_001, "transfer_out", true, -25_005_000, 0, 5_000, 0), T0 + M, &usdc_price, None); l.tick(T0 + M, &no_landings); });
    assert!(!sess.stopper.stopping() && sess.gate.allows(), "the owner's withdrawal is no stop");
    assert_eq!((l.spent(), notes.iter().filter(|n| n.kind == "owner_transfer").count()), (5_000, 1), "its fee is spend; the transfer is recorded");
    l.on_input(&snap_answer(2_000, 223_000_000 - 25_005_000, 191_500_000, 22_970_000, "periodic"), T0 + 10 * M, &usdc_price);
    l.tick(T0 + 12 * M, &no_landings);
    assert!(sess.gate.allows());
    rec.sync();
    let r = crate::rec::read_jsonl(&dir, "recon").unwrap();
    assert_eq!((r[0]["ok"].as_bool(), r[0]["owner_transfers"][0]["category"].as_str(), r[0]["owner_transfers"][0]["lamports"].as_i64()),
        (Some(true), Some("transfer_out"), Some(-25_000_000)), "{}", r[0]);
    assert!(crate::rec::read_jsonl(&dir, "events").unwrap().iter().any(|e| e["kind"] == "owner_transfer" && e["detail"]["category"] == "transfer_out"));
    let m = l.money_json(T0 + 12 * M, json!({}), 0);
    assert_eq!((m["stop_basis"].as_str(), m["net_spend_now"].as_i64(), m["stop_value_now"].as_i64(), m["owner_transfers_total"].as_u64()),
        (Some("net_spend"), Some(5_000), Some(414_500_000 - 5_000), Some(1)));
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

/// Review WP-07 #3: the money view's freshness. Snapshots run inside the segment (the periodic one asked for 30 s before
/// `snapshot_min`); the view is stale (the executor's `equity_stale`, the gate in shadow with reason `equity_stale`, an
/// Error notice) once its last good snapshot is older than `max_view_age_s`, after `stale_after_failures` failed
/// snapshots in a row, while a landing found by a status check waits `max_record_wait_s` for its wallet record, and from a
/// wallet record the chain-fetch service gave up on until a snapshot asked for after it (one is asked for at once). Fresh
/// again, the gate goes back to live; an operator's resume meanwhile is closed again; a pause is never lifted by it
#[test]
fn a_stale_money_view_shadows_the_gate() {
    let (mut l, sess, dir, rec) = rig("stale", |_| {});
    l.cfg.max_view_age_s = 600;
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    let v = l.tick(T0 + S, &no_landings);
    assert!(v.equity_known && !v.stale && sess.gate.allows());
    // (no RPC here: what is wanted stays wanted; the start snapshot is in)
    assert_eq!(l.want, Some("start"));
    l.want = None;
    // inside the segment: the periodic snapshot is due 30 s before 10 minutes
    l.tick(T0 + 9 * M + 29 * S, &no_landings);
    assert_eq!(l.want, None);
    l.tick(T0 + 9 * M + 30 * S, &no_landings);
    assert_eq!(l.want, Some("periodic"), "every snapshot_min inside the segment, not only at start and stop");
    assert!(sess.gate.allows(), "10 minutes is not yet stale");
    // 10 minutes and a second: stale
    let (v, notes) = crate::notify::capture(|| l.tick(T0 + 10 * M + S, &no_landings));
    assert!(v.stale && v.equity_known);
    assert_eq!((sess.gate.mode(), sess.gate.reason().as_str(), sess.gate.sticky()), (GateMode::Shadow, "equity_stale", false));
    assert!(notes.iter().any(|n| n.kind == "equity_stale" && n.level == Level::Error), "{notes:?}");
    // an operator's resume meanwhile: closed again at the next tick
    sess.gate.resume("operator").unwrap();
    l.tick(T0 + 10 * M + 2 * S, &no_landings);
    assert_eq!(sess.gate.reason(), "equity_stale");
    // a good snapshot: fresh, live again
    let (v, notes) = crate::notify::capture(|| { l.on_input(&snap_answer(2_000, 223_000_000, 191_500_000, 22_970_000, "periodic"), T0 + 11 * M, &usdc_price); l.tick(T0 + 11 * M, &no_landings) });
    assert!(!v.stale && sess.gate.allows());
    assert!(notes.iter().any(|n| n.kind == "equity_fresh"));
    // snapshots that keep failing: the third in a row is stale, however young the last good one
    let mut t = T0 + 11 * M;
    for k in 1..=3u64 {
        t += 30 * S;
        l.on_input(&json!({ "what": "snapshot", "why": "retry", "error": "rpc down" }), t, &usdc_price);
        let v = l.tick(t, &no_landings);
        assert_eq!(v.stale, k == 3, "{k} failed");
    }
    assert_eq!(sess.gate.reason(), "equity_stale");
    l.on_input(&snap_answer(3_000, 223_000_000, 191_500_000, 22_970_000, "retry"), t + S, &usdc_price);
    assert!(!l.tick(t + S, &no_landings).stale && sess.gate.allows());
    // a landing found by a status check, its wallet record not come: stale after max_record_wait_s, fresh once it comes
    let t1 = t + 2 * S;
    let prov = TickIn { provisional_since: Some(t1), wallet_gave_up: None };
    assert!(!l.tick_with(t1 + 119 * S, &no_landings, prov).stale);
    assert!(l.tick_with(t1 + 121 * S, &no_landings, prov).stale && !sess.gate.allows());
    assert!(!l.tick_with(t1 + 122 * S, &no_landings, TickIn::default()).stale && sess.gate.allows(), "its record came");
    // a wallet record the chain-fetch service gave up on: stale until a snapshot asked for after it (asked for at once;
    // no RPC here, so what was wanted before stays wanted: cleared to see it)
    let t2 = t1 + 123 * S;
    l.want = None;
    l.tick_with(t2, &no_landings, TickIn { provisional_since: None, wallet_gave_up: Some(4) });
    assert!(!l.stale.is_some(), "the first reading is the baseline");
    let v = l.tick_with(t2 + S, &no_landings, TickIn { provisional_since: None, wallet_gave_up: Some(5) });
    assert!(v.stale && l.want == Some("refresh"), "{:?}", l.want);
    let mut early = snap_answer(4_000, 223_000_000, 191_500_000, 22_970_000, "refresh");
    early["t_req_ns"] = json!(t2);
    l.on_input(&early, t2 + 2 * S, &usdc_price);
    assert!(l.tick_with(t2 + 2 * S, &no_landings, TickIn { provisional_since: None, wallet_gave_up: Some(5) }).stale, "asked for before the give-up");
    let mut after = snap_answer(4_100, 223_000_000, 191_500_000, 22_970_000, "refresh");
    after["t_req_ns"] = json!(t2 + 3 * S);
    l.on_input(&after, t2 + 4 * S, &usdc_price);
    assert!(!l.tick_with(t2 + 4 * S, &no_landings, TickIn { provisional_since: None, wallet_gave_up: Some(5) }).stale && sess.gate.allows());
    // a pause is the operator's: a stale view over it keeps its reason, and fresh again does not lift it
    sess.gate.shadow("paused", "operator", false).unwrap();
    l.tick(t2 + 20 * M, &no_landings);
    assert_eq!((sess.gate.reason().as_str(), l.stale.is_some()), ("paused", true));
    l.on_input(&snap_answer(5_000, 223_000_000, 191_500_000, 22_970_000, "periodic"), t2 + 21 * M, &usdc_price);
    l.tick(t2 + 21 * M, &no_landings);
    assert_eq!((sess.gate.reason().as_str(), l.stale.is_some()), ("paused", false), "still paused");
    rec.sync();
    let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
    assert!(ev.iter().filter(|e| e["kind"] == "equity_stale").count() >= 4 && ev.iter().any(|e| e["kind"] == "equity_fresh"));
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
    // a run that sends nothing records it only (its gate is not touched)
    let (mut l, sess, dir, rec) = rig("stale-shadow", |_| {});
    l.cfg.max_view_age_s = 600;
    l.sup.acts = false;
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    assert!(l.tick(T0 + 11 * M, &no_landings).stale && sess.gate.allows());
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

/// Review WP-07 #2 (mutant M9) and #8: the floor is the highest of its candidates. The campaign's start (414.5M) less its
/// budget (34M) is 380.5M; this segment's own start (the stop value then: 414.5M less the 5M the campaign spent) less
/// what is left (20M) is 389.5M: the higher wins; a floor given above both wins; a budget over the hard cap is read at
/// the cap
#[test]
fn the_floor_is_the_highest_candidate() {
    let camp = std::env::temp_dir().join(format!("arbx-floor-camp-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    std::fs::create_dir_all(&camp).unwrap();
    std::fs::write(camp.join("campaign.json"), json!({ "budget": { "test_budget_lamports": 34_000_000 } }).to_string()).unwrap();
    write_segment(&camp, "c-p1", T0, &[frz_snap(1_000, 223_000_000, 191_500_000, 22_970_000, T0)], &[entry_t("a", 1_100, T0 + M, 5_000_000)], &[]);
    for (floor_arg, budget_left, want) in [(None, Some(20_000_000), 389_500_000), (Some(395_000_000), Some(20_000_000), 395_000_000), (None, None, 380_500_000),
        (None, Some(99_999_999_999), 380_500_000)] {
        let h = history(&camp, Some("c-p2"), T0 + 61 * M, DAY_NS);
        assert_eq!((h.spent, h.stop_value_now()), (5_000_000, Some(409_500_000)));
        let (mut l, _sess, dir, rec) = rig("floor2", |_| {});
        l.set_campaign(h, Some(34_000_000), budget_left, floor_arg);
        l.on_input(&snap_answer(2_000, 218_000_000, 191_500_000, 22_970_000, "start"), T0 + 62 * M, &usdc_price);
        assert_eq!(l.sup.limits.floor, Some(want), "floor {floor_arg:?}, budget left {budget_left:?}");
        rec.close();
        let _ = std::fs::remove_dir_all(&dir);
    }
    let _ = std::fs::remove_dir_all(&camp);
}

/// Review WP-07 #7, #9: the stop's reconciliation and the windows between segments. A segment stops while a win's record
/// is still on its way: its stop reconciliation is unexplained (no RPC to search with here) and is written `final:
/// false` (`recon_undecided`, Warn), not a miss (the campaign's history counts none). The next segment reconciles the
/// window from that reconciliation's first snapshot to its own first snapshot with every record of it, the late one
/// among them (a pre-run record): it passes, and decides the earlier one. Without the late record, or with money that
/// left between the segments and no record at all, that window is a miss of the next segment (shadow; the campaign's
/// later segments record only)
#[test]
fn the_stop_and_the_windows_between_segments_are_reconciled() {
    for case in ["late_record", "no_record"] {
        let camp = std::env::temp_dir().join(format!("arbx-between-{case}-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        std::fs::create_dir_all(&camp).unwrap();
        std::fs::write(camp.join("campaign.json"), json!({ "budget": { "test_budget_lamports": 34_000_000 } }).to_string()).unwrap();
        let (mut l, sess, _dir, rec) = rig_at(camp.join("c-p1"), "c-p1", |_| {});
        std::fs::write(camp.join("c-p1").join("meta.json"), json!({ "run": { "started_ns": T0 } }).to_string()).unwrap();
        l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
        // a win at slot 1,990 whose record has not come; the stop snapshot (slot 2,000) shows it
        l.want_stop_snapshot();
        l.on_input(&snap_answer(2_000, 223_000_000 - 36_499, 191_500_000 + 49_000, 22_970_000, "stop"), T0 + 30 * M, &usdc_price);
        l.final_begin(T0 + 30 * M);
        let (_, notes) = crate::notify::capture(|| l.final_recon(T0 + 30 * M + 5 * S, &no_landings));
        assert!(sess.gate.allows() && !notes.iter().any(|n| n.kind == "recon_miss"), "undecided is no miss: {notes:?}");
        assert!(notes.iter().any(|n| n.kind == "recon_undecided" && n.level == Level::Warn));
        rec.close();
        let r = crate::rec::read_jsonl(&camp.join("c-p1"), "recon").unwrap();
        assert_eq!((r[0]["ok"].as_bool(), r[0]["final"].as_bool(), r[0]["action"].as_str(), r[0]["at_stop"].as_bool()), (Some(false), Some(false), Some("undecided"), Some(true)));
        let h = history(&camp, Some("c-p2"), T0 + 31 * M, DAY_NS);
        assert_eq!((h.recon_misses.len(), h.undecided.as_ref().map(|u| u.0.as_str())), (0, Some("c-p1")), "not a miss of the campaign yet");
        assert_eq!(h.prev_window.as_ref().map(|w| (w.from.slot, w.undecided)), Some((1_000, true)), "the next segment reconciles from the undecided window's start");
        // the next segment: its wallet stream's pre-run records, then its first snapshot (after money that left between the
        // segments with no record, in the second case)
        let (mut l, sess, _dir, rec) = rig_at(camp.join("c-p2"), "c-p2", |_| {});
        std::fs::write(camp.join("c-p2").join("meta.json"), json!({ "run": { "started_ns": T0 + 31 * M } }).to_string()).unwrap();
        l.set_campaign(h, Some(34_000_000), Some(34_000_000), None);
        let mut late = wtx("late-win", 1_990, "route", true, -36_499, 49_000, 5_000, 31_499);
        late["pre_run"] = json!(true);
        if case == "late_record" { l.on_wallet_tx(&late, T0 + 32 * M, &usdc_price, None); }
        let sol = 223_000_000 - 36_499 - if case == "no_record" { 50_000 } else { 0 };
        l.on_input(&snap_answer(3_000, sol, 191_500_000 + 49_000, 22_970_000, "start"), T0 + 33 * M, &usdc_price);
        let (_, notes) = crate::notify::capture(|| l.tick(T0 + 35 * M, &no_landings));
        rec.close();
        let r = crate::rec::read_jsonl(&camp.join("c-p2"), "recon").unwrap();
        let b = r.iter().find(|x| x["between_segments"] == json!(true)).unwrap_or_else(|| panic!("{case}: no window between segments: {r:?}"));
        assert_eq!((b["from"]["slot"].as_u64(), b["from"]["segment"].as_str(), b["to"]["slot"].as_u64(), b["decides"]["segment"].as_str()), (Some(1_000), Some("c-p1"), Some(3_000), Some("c-p1")));
        let h = history(&camp, None, T0 + 40 * M, DAY_NS);
        if case == "late_record" {
            assert_eq!((b["ok"].as_bool(), b["final"].as_bool()), (Some(true), Some(true)), "{b}");
            assert!(sess.gate.allows());
            assert_eq!((h.recon_misses.len(), h.undecided.is_none()), (0, true), "the late record explained it");
        } else {
            assert_eq!((b["ok"].as_bool(), b["final"].as_bool(), b["liquid"]["residual"].as_i64()), (Some(false), Some(true), Some(-36_499 + 49_000 - 50_000)), "{b}");
            assert_eq!(sess.gate.reason(), "reconcile_miss");
            assert!(notes.iter().any(|n| n.kind == "recon_miss"));
            assert_eq!(h.recon_misses.len(), 1, "a miss of the campaign: its later segments record only");
        }
        let _ = std::fs::remove_dir_all(&camp);
    }
}

/// Review WP-07 #2 (mutant M2): the ledger as `arbx run` assembles it (`Ledger::for_run`). A run that sends (live,
/// canary) arms its stops: the frz config's allotment (5,000,000) makes the floor the start less 5M, and a loss past it
/// puts the gate in shadow and stops the run (`equity_floor`). A shadow or dry run records what would have fired and
/// stops nothing
#[test]
fn the_ledger_as_arbx_run_assembles_it_arms_the_stops() {
    let cfg = crate::config::Config::parse(&std::fs::read_to_string(repo("deploy/arbx-canary-frz.toml")).unwrap()).unwrap();
    for sends in [true, false] {
        let dir = std::env::temp_dir().join(format!("arbx-forrun-{sends}-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        std::fs::create_dir_all(&dir).unwrap();
        let rec = rec::start(rec::Opts { dir: dir.clone(), run: "x".into(), producer: "test".into(), cfg: Default::default(), feeds: vec![], monitor: false, echo: None }).unwrap();
        let sess = Session::new();
        let mut l = Ledger::for_run(&cfg, crate::tx::pk(FRZ), rec.clone(), "seg", sends, sess.gate.clone(), sess.stopper.clone(), History::default(), None, None);
        assert_eq!(l.sup.acts, sends, "the stop rules act in a run that sends");
        l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
        assert_eq!(l.sup.limits.floor, Some(414_500_000 - 5_000_000), "armed: the start less the frz config's allotment");
        l.on_wallet_tx(&wtx("loss", 1_001, "route", false, -5_000_001, 0, 5_000_001, 0), T0 + M, &usdc_price, None);
        l.tick(T0 + M, &no_landings);
        if sends {
            assert_eq!(sess.stopper.info().map(|i| (i.reason, i.reason.exit_code())), Some((StopReason::EquityFloor, 20)));
            assert_eq!(sess.gate.mode(), GateMode::Stopped);
        } else {
            assert!(!sess.stopper.stopping() && sess.gate.allows(), "a run that sends nothing stops nothing");
            rec.sync();
            assert!(crate::rec::read_jsonl(&dir, "events").unwrap().iter().any(|e| e["kind"] == "equity_floor" && e["detail"]["acted"] == json!(false)));
        }
        rec.close();
        let _ = std::fs::remove_dir_all(&dir);
    }
}

/// Review WP-07 #6: a refused bundle that landed (the executor's amend of an attempt it finalized `not_landed_refused`)
/// is raised at once: a final miss in recon.jsonl, the gate in shadow for the rest of the segment, a Critical notice;
/// the campaign's history counts it
#[test]
fn a_refused_bundle_that_landed_is_raised_at_once() {
    let camp = std::env::temp_dir().join(format!("arbx-refused-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    let (mut l, sess, dir, rec) = rig_at(camp.join("c-p1"), "c-p1", |_| {});
    std::fs::write(dir.join("meta.json"), json!({ "run": { "started_ns": T0 } }).to_string()).unwrap();
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    let (_, notes) = crate::notify::capture(|| l.on_refused_landed(T0 + M, vec![json!({ "attempt": 3, "sig": "abc", "slot": 1_010, "fee": 5_000 })]));
    assert_eq!((sess.gate.reason().as_str(), sess.gate.sticky()), ("reconcile_miss", true));
    assert!(notes.iter().any(|n| n.kind == "recon_miss" && n.level == Level::Critical), "{notes:?}");
    rec.close();
    let r = crate::rec::read_jsonl(&dir, "recon").unwrap();
    assert_eq!((r[0]["kind"].as_str(), r[0]["ok"].as_bool(), r[0]["final"].as_bool()), (Some("refused_bundle_landed"), Some(false), Some(true)));
    assert_eq!(history(&camp, None, T0 + 2 * M, DAY_NS).recon_misses.len(), 1);
    // an earlier segment's outcome line that says so (its amend) is a miss of the campaign too, and keeps the attempt refused
    let d2 = camp.join("c-p0");
    write_segment(&camp, "c-p0", T0 - 60 * M, &[], &[], &[json!({ "attempt": 1, "sig": "zz", "final": "not_landed_refused" }),
        json!({ "attempt": 1, "sig": "zz", "final": "landed_ok", "amend": true, "refused_then_landed": true, "t_ns": T0 - M })]);
    let h = history(&camp, None, T0 + 2 * M, DAY_NS);
    assert_eq!((h.recon_misses.len(), h.earlier.get("zz").map(|e| e.fin.as_str())), (2, Some("not_landed_refused")));
    let _ = std::fs::remove_dir_all(&d2);
    let _ = std::fs::remove_dir_all(&camp);
}

/// Review WP-07 #2 (mutant M6): a wallet record that reaches the ledger after a snapshot already holding its landing (its
/// slot at or below the snapshot's) moves the money view no more: the snapshot counted it
#[test]
fn a_record_the_snapshot_already_holds_is_not_counted_twice() {
    let (mut l, _sess, dir, rec) = rig("twice", |_| {});
    l.on_input(&snap_answer(1_000, 223_000_000, 191_500_000, 22_970_000, "start"), T0, &usdc_price);
    // a win at slot 1,990, already in the snapshot of slot 2,000 when its record comes
    l.on_input(&snap_answer(2_000, 223_000_000 - 36_499, 191_500_000 + 49_000, 22_970_000, "periodic"), T0 + 10 * M, &usdc_price);
    l.on_wallet_tx(&wtx("w", 1_990, "route", true, -36_499, 49_000, 5_000, 31_499), T0 + 10 * M + S, &usdc_price, None);
    let v = l.tick(T0 + 10 * M + S, &no_landings);
    assert_eq!((v.liquid, v.wsol, v.native), (Some(414_500_000 + 12_501), Some(191_549_000), Some(222_963_501)), "the snapshot's balances, once");
    // one after the snapshot moves it
    l.on_wallet_tx(&wtx("f", 2_001, "route", false, -5_000, 0, 5_000, 0), T0 + 10 * M + 2 * S, &usdc_price, None);
    assert_eq!(l.tick(T0 + 10 * M + 2 * S, &no_landings).liquid, Some(414_500_000 + 12_501 - 5_000));
    rec.close();
    let _ = std::fs::remove_dir_all(&dir);
}

/// Integration (FT-000 x WP-07: the wallet history's cursor against this ledger's window between segments). Segment 1
/// entered two wallet transactions (slots 1,100 and 1,200) and took its last good snapshot at 1,300; it recorded one
/// more at 1,400 in wallet.jsonl, which its cursor names, but was killed before its ledger entered it. Segment 2's window
/// starts at 1,300: the cursor (1,400) is moved back to the newest earlier ledger entry at or before it (1,200), so the
/// record at 1,400 is listed again and the window gets it; a cursor at or before the window's start is kept; with no
/// entry before the window the cursor is dropped (the last hour is listed); with no window (no good snapshot yet) it is
/// kept. A stop reconciliation left undecided moves the window's start back to its first snapshot, and the cursor with it
#[test]
fn the_wallet_cursor_never_passes_the_window_between_segments() {
    let camp = std::env::temp_dir().join(format!("arbx-camp-cursor-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    std::fs::create_dir_all(&camp).unwrap();
    let (s0, s1) = (frz_snap(1_000, 223_000_000, 191_500_000, 22_970_000, T0), frz_snap(1_300, 223_000_000 - 2_000, 191_500_000, 22_970_000, T0 + 50 * M));
    write_segment(&camp, "c-p1", T0, &[s0, s1], &[entry_t("a", 1_100, T0 + 10 * M, 1_000), entry_t("b", 1_200, T0 + 20 * M, 1_000)], &[]);
    let h = history(&camp, Some("c-p2"), T0 + 61 * M, DAY_NS);
    assert_eq!(h.prev_window.as_ref().map(|w| w.from.slot), Some(1_300));
    assert_eq!(h.window_cursor, Some(("b".to_string(), 1_200)), "the newest entry at or before the window's first snapshot");
    let c = |sig: &str, slot: u64| Some((sig.to_string(), slot));
    assert_eq!(bound_wallet_cursor(c("k", 1_400), &h), (c("b", 1_200), "moved_back"), "past the window: moved back");
    assert_eq!(bound_wallet_cursor(c("b", 1_200), &h), (c("b", 1_200), "kept"));
    assert_eq!(bound_wallet_cursor(c("s", 1_300), &h), (c("s", 1_300), "kept"), "at the window's first snapshot");
    assert_eq!(bound_wallet_cursor(None, &h), (None, "none"));
    let none_before = History { window_cursor: None, ..h.clone() };
    assert_eq!(bound_wallet_cursor(c("k", 1_400), &none_before), (None, "dropped"), "nothing earlier to start from: the last hour is listed");
    assert_eq!(bound_wallet_cursor(c("k", 1_400), &History::default()), (c("k", 1_400), "kept"), "no window yet: nothing before this segment's start counts");
    // segment 1's stop reconciliation (1,000 -> 1,300) left undecided: the window starts at 1,000, before every entry
    std::fs::write(camp.join("c-p1").join("recon.jsonl"), format!("{}\n{}\n", json!({ "schema": "arbx.recon/1.0", "file_seq": 0 }),
        json!({ "t_ns": T0 + 51 * M, "ok": false, "final": false, "from": { "slot": 1_000 }, "to": { "slot": 1_300 }, "residual": 20_000 }))).unwrap();
    let h = history(&camp, Some("c-p2"), T0 + 61 * M, DAY_NS);
    assert_eq!((h.prev_window.as_ref().map(|w| (w.from.slot, w.undecided)), h.window_cursor.clone()), (Some((1_000, true)), None));
    assert_eq!(bound_wallet_cursor(c("b", 1_200), &h), (None, "dropped"), "the undecided window needs every record from 1,000 on");
    let _ = std::fs::remove_dir_all(&camp);
}

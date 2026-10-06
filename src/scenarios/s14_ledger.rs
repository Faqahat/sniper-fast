//! S14 (PLAN WP-09; WP-07's golden ledger cases, here on a scenario's own landing): the ledger's categories on a real
//! route transaction of ours, and the reconciliation. A canary run (its bundles to a block engine in memory) whose wallet
//! holds no USDC account sends a create+close bundle (WP-06: the mid token's account created before the route and
//! closed to the payer after it, in the same transaction); the block engine answers `accepted`, then `processed` (it
//! landed, releasing the in-flight entry). The chain's record of that transaction (getTransaction: the very bytes the
//! block engine got, with the meta of a landing that delivered the quote: each leg's output as the route program logs
//! it, the tip, the base fee, the account's rent out and back) reaches the engine as the chain-fetch service hands it
//! over: INPUT 7 `wallet_tx` with the ledger's raw fields (`ledger::raw`) and the route program's events.
//!
//! Expected (MEASUREMENT §4.42): one ledger line, `route`, ok, whose categories sum to its equity change: `trade_gross`
//! (the round trip the chain shows: the WSOL the route made), `tip`, `fee_win`; rent locked = rent reclaimed (2,039,280:
//! a create+close locks nothing), so the liquid change is the equity change and the trading P&L is gross − tip − fee.
//! The attempt is final `landed_ok` from the wallet's record with that line. The ledger's next snapshot reconciles the
//! window within its tolerance on both bases (residual 0), every token amount exact, and the executor's money (its
//! round trip, tip and fee) matches the chain's line. The status line's money totals say the same. The run replays
//! (its canary executor offline, its send with the run's signature, the landing from the journal).
use super::s13_verdicts::{canary_rig, usdc_sale};
use super::*;
use base64::Engine as _;

const POOLS3: [&str; 3] = ["usdc.pump", "usdc.cpmm", "usdc.ammv4"];
pub(crate) const RENT: u64 = 2_039_280;
pub(crate) const FEE: u64 = 5_000;

/// one `Program data:` line of the route program (nexus-arb-v2 `sol_log_data`)
fn data_line(b: &[u8]) -> String { format!("Program data: {}", base64::engine::general_purpose::STANDARD.encode(b)) }

/// The chain's getTransaction record of our bundle transaction `raw` (signed bytes, a v0 message on the `[exec]` lookup
/// table) landed at `slot`, the base fee paid by the wallet. `ok`: the wallet also pays the tip; its WSOL account
/// holding `wsol_pre` gains `back - spent`; the mid token's account is made by the associated-token program (its System
/// create, an inner instruction) and closed to the payer by the transaction's own CloseAccount (0 lamports before and
/// after); the tip account gains the tip; the route program logs each leg's output (`mid`, `back`). Failed (the route's
/// profit check, 0x4e580002, after both legs ran): only the fee moves (everything else is reverted), while the record
/// still lists what ran before the failure, the associated-token program's inner create among them (as the chain records
/// a failed transaction: w5h3-p2#664's landing, testdata/scenarios/s16/tx, lists its own)
#[allow(clippy::too_many_arguments)]
pub(crate) fn landed_record(raw: &[u8], alt: &[Pk], payer: &Pk, wallet_sol: u64, wsol_pre: u64, a: &Value, slot: u64, ok: bool) -> (Value, Vec<String>) {
    let (tx, _) = crate::tx::parse_wire(raw).expect("our signed bytes parse");
    let mut keys: Vec<Pk> = tx.keys.clone();
    for l in &tx.lookups { keys.extend(l.writable.iter().map(|i| alt[*i as usize])); }
    for l in &tx.lookups { keys.extend(l.readonly.iter().map(|i| alt[*i as usize])); }
    let ix = |k: &Pk| keys.iter().position(|x| x == k).unwrap_or_else(|| panic!("{} is not in the transaction", b58(k)));
    let pk58 = |s: &Value| crate::tx::pk(s.as_str().unwrap());
    let (tip, tip_acct, mid_ata) = (a["tip"]["lamports"].as_u64().unwrap(), pk58(&a["tip"]["account"]), pk58(&a["tx"]["mid_account"]));
    let (mid, back, spent, size) = (a["expected"]["mid"].as_u64().unwrap(), a["expected"]["back"].as_u64().unwrap(), a["expected"]["spent"].as_u64().unwrap(),
        a["size_lamports"].as_u64().unwrap());
    let wsol_ata = crate::build::ata_of(payer, &crate::venues::WSOL, &crate::pda::TOKEN_PROGRAM);
    let gross = if ok { back - spent } else { 0 };
    let tip_paid = if ok { tip } else { 0 };
    let mut pre: Vec<u64> = vec![1_000_000_000; keys.len()];
    let mut post = pre.clone();
    let (w, wa, m, ta) = (ix(payer), ix(&wsol_ata), ix(&mid_ata), ix(&tip_acct));
    (pre[w], post[w]) = (wallet_sol, wallet_sol - FEE - tip_paid);
    (pre[wa], post[wa]) = (wsol_pre + RENT, wsol_pre + RENT + gross);
    (pre[m], post[m]) = (0, 0);
    post[ta] = pre[ta] + tip_paid;
    let tokbal = |i: usize, amount: u64| json!({ "accountIndex": i, "mint": b58(&crate::venues::WSOL), "owner": b58(payer), "programId": b58(&crate::pda::TOKEN_PROGRAM),
        "uiTokenAmount": { "amount": amount.to_string(), "decimals": 9 } });
    // the associated-token program's CPI: System CreateAccount (payer -> the mid account: rent, 165 bytes, the token program)
    let ata_ix = tx.ixs.iter().position(|x| keys[x.program as usize] == *crate::pda::ATA_PROGRAM).expect("the create+close bundle creates the account");
    let route_ix = tx.ixs.iter().position(|x| keys[x.program as usize] == crate::tx::pk("8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg")).expect("the route");
    let mut create = 0u32.to_le_bytes().to_vec();
    create.extend(RENT.to_le_bytes());
    create.extend(165u64.to_le_bytes());
    create.extend(*crate::pda::TOKEN_PROGRAM);
    let system = ix(&[0u8; 32]);
    let program = crate::tx::pk("8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg");
    let out = |leg: u8, amount: u64| { let mut v = b"NXV2OUT".to_vec(); v.push(leg); v.extend(amount.to_le_bytes()); v };
    let logs = vec![format!("Program {} invoke [1]", b58(&program)), data_line(b"NXV2LEG\x00"), data_line(&out(0, mid)), data_line(b"NXV2LEG\x01"),
        data_line(&out(1, back)), if ok { format!("Program {} success", b58(&program)) } else { format!("Program {} failed: custom program error: 0x4e580002", b58(&program)) }];
    assert_eq!(size, spent, "the buy leg (AMM v4, exact in) debits the size: the round trip the program logs is the WSOL the wallet gains");
    let n_static = tx.keys.len();
    let err = if ok { Value::Null } else { json!({ "InstructionError": [route_ix, { "Custom": 1314390018u32 }] }) };
    let rec = json!({ "slot": slot, "transactionIndex": 5, "blockTime": null, "version": 0,
        "transaction": [base64::engine::general_purpose::STANDARD.encode(raw), "base64"],
        "meta": { "err": err, "fee": FEE, "preBalances": pre, "postBalances": post,
            "preTokenBalances": [tokbal(wa, wsol_pre)], "postTokenBalances": [tokbal(wa, wsol_pre + gross)],
            "innerInstructions": [{ "index": ata_ix, "instructions": [{ "programIdIndex": system, "accounts": [w, m], "data": bs58::encode(&create).into_string(), "stackHeight": 2 }] }],
            "logMessages": logs, "computeUnitsConsumed": 150_000,
            "loadedAddresses": { "writable": keys[n_static..].iter().take(tx.lookups.iter().map(|l| l.writable.len()).sum()).map(b58).collect::<Vec<_>>(),
                "readonly": keys[n_static + tx.lookups.iter().map(|l| l.writable.len()).sum::<usize>()..].iter().map(b58).collect::<Vec<_>>() } } });
    (rec, logs)
}

/// The INPUT 7 `wallet_tx` record of our attempt `at` (its signed bytes `raw`) landed at `slot`, as the chain-fetch
/// service builds it from the chain's record (`landed_record`): the wallet's view (`wallet::fields`), the ledger's raw
/// fields (`ledger::raw`) and the route program's events, for a wallet holding `wallet_sol` and `wsol_pre` before it
pub(crate) fn wallet_record(r: &Rig, at: &Value, raw: &[u8], slot: u64, wallet_sol: u64, wsol_pre: u64, ok: bool) -> Value {
    let payer = crate::tx::pk(&r.cfg.wallet);
    let alt: Vec<Pk> = {
        r.rec.sync();
        let j = crate::rec::journal::read_dir(&r.dir).unwrap();
        let ei = crate::exec::ExecInit::from_json(crate::rec::journal::exec_init(&j).unwrap()).unwrap();
        ei.alts[0].1.clone()
    };
    let (rec, logs) = landed_record(raw, &alt, &payer, wallet_sol, wsol_pre, at, slot, ok);
    let x = crate::chainfetch::txjson::from_rpc(&rec).expect("the record reads");
    let sig58 = at["tx"]["sig"].as_str().unwrap().to_string();
    assert_eq!(bs58::encode(x.sig).into_string(), sig58, "the record is our attempt's transaction");
    let (wsol_ata, route) = (crate::build::ata_of(&payer, &crate::venues::WSOL, &crate::pda::TOKEN_PROGRAM), crate::tx::pk(&r.cfg.exec.program));
    let f = crate::chainfetch::wallet::fields(&x, &payer, &wsol_ata, &route);
    let ledger = crate::ledger::raw(&x, &payer, &wsol_ata, &route);
    let err = x.meta.as_ref().and_then(|m| m.err.as_ref()).map(|e| crate::rec::tx_error(&e.err));
    json!({ "sig": sig58, "slot": slot, "idx": 5, "ok": ok, "err": err, "fee": FEE, "wallet_kind": f.wallet_kind, "wallet_sol": f.wallet_sol,
        "wallet_tok": f.wallet_tok, "attempt": at["attempt"], "found_by": ["jito_processed"], "created": f.created.len(), "closed": f.closed.len(), "pre_run": false,
        "prog_events": crate::proglog::events(&logs), "cu_consumed": 150_000, "ledger": ledger.json() })
}

#[test]
fn s14_the_ledger_books_a_create_close_landing_and_reconciles() {
    let (mut r, s2) = canary_rig("s14", &POOLS3, &CANARY, false);
    let payer = crate::tx::pk(&r.cfg.wallet);
    let (sol0, wsol0) = (3 * SOL, 2 * SOL);
    let a = r.meta("usdc.ammv4");
    let sale = r.sig("S14-sale");
    let mut t = T0 + 10 * MS;
    usdc_sale(&mut r, &a, 40, sale, s2, &mut t);
    r.timers(t + 4 * MS);
    let att = r.attempts();
    assert_eq!(att.len(), 1, "one send");
    let at = att[0].clone();
    assert_eq!((at["sent"].as_bool(), at["tx"]["creates_ata"].as_bool(), at["tx"]["closes_ata"].as_bool()), (Some(true), Some(true), Some(true)), "create+close: {at}");
    r.pump(1, t + 5 * MS);
    r.verdict("b0", "accepted", Some(s2 + 1), None, t + 6 * MS);
    let landed = r.verdict("b0", "processed", Some(s2 + 1), None, t + 7 * MS);
    assert_eq!(landed["release"].as_bool(), Some(true));
    // the chain's record of the transaction the block engine got, as the chain-fetch service hands it to the engine
    let input = wallet_record(&r, &at, &r.bundles_sent()[0], s2 + 1, sol0, wsol0, true);
    assert_eq!((input["wallet_kind"].as_str(), input["ledger"]["rent_locked"].as_u64(), input["ledger"]["rent_reclaimed"].as_u64(), input["ledger"]["fee"].as_u64()),
        (Some("route"), Some(RENT), Some(RENT), Some(FEE)), "{input}");
    let t1 = t + 400 * MS;
    r.tick(s2 + 1, t1);
    r.input(InputKind::WalletTx, input, t1 + MS);
    let (tip, gross) = (at["tip"]["lamports"].as_i64().unwrap(), at["expected"]["gross"].as_i64().unwrap());
    let l = r.lines("ledger");
    assert_eq!(l.len(), 1, "{l:?}");
    let e = &l[0];
    let cats: Vec<(String, i64)> = e["categories"].as_array().unwrap().iter().map(|c| (c["cat"].as_str().unwrap().to_string(), c["lamports"].as_i64().unwrap())).collect();
    assert_eq!(cats, vec![("trade_gross".to_string(), gross), ("tip".into(), -tip), ("fee_win".into(), -(FEE as i64))], "the summing categories: {e}");
    assert_eq!(cats.iter().map(|c| c.1).sum::<i64>(), e["equity_delta"].as_i64().unwrap(), "they sum to the equity change");
    assert_eq!((e["kind"].as_str(), e["ok"].as_bool(), e["attempt"].as_u64(), e["fee"].as_u64(), e["tip"].as_i64()), (Some("route"), Some(true), Some(0), Some(FEE), Some(tip)));
    assert_eq!((e["rent_locked"].as_u64(), e["rent_reclaimed"].as_u64(), e["rent_nonrecoverable"].as_u64()), (Some(RENT), Some(RENT), Some(0)), "create+close: rent out and back");
    assert_eq!((e["trade_gross"].as_i64(), e["trade_net"].as_i64(), e["liquid_delta"].as_i64(), e["equity_delta"].as_i64()),
        (Some(gross), Some(gross - tip - FEE as i64), Some(gross - tip - FEE as i64), Some(gross - tip - FEE as i64)), "{e}");
    let mid = at["tx"]["mid_account"].clone();
    assert!(e["created"].as_array().unwrap().iter().any(|c| c["acct"] == mid) && e["closed"].as_array().unwrap().iter().any(|c| c["acct"] == mid && c["to"] == json!(b58(&payer))));
    let o = r.lines("outcomes");
    assert_eq!((o.len(), o[0]["final"].as_str(), o[0]["final_src"].as_str()), (1, Some("landed_ok"), Some("wallet")), "{o:?}");
    assert_eq!((o[0]["ledger"]["trade_net"].as_i64(), o[0]["round_trip_on_chain"].as_i64(), o[0]["verdicts"].as_array().map(|v| v.len())),
        (Some(gross - tip - FEE as i64), Some(gross), Some(2)), "{}", o[0]);
    // the next snapshot: the wallet's SOL down by the fee and the tip, its WSOL up by the gross; reconciled a grace later
    let t2 = t1 + 10_000 * MS;
    r.tick(s2 + 3, t2);
    r.snapshot(s2 + 3, sol0 - FEE - tip as u64, wsol0 + gross as u64, None, "periodic", t2 + MS);
    for k in 1..=7u64 { r.tick(s2 + 3 + k, t2 + k * 10_000 * MS); r.timers(t2 + k * 10_000 * MS + MS); }
    let rc = r.lines("recon");
    eprintln!("S14 recon: {rc:#?}");
    assert_eq!(rc.len(), 1, "{rc:?}");
    let c = &rc[0];
    assert_eq!((c["ok"].as_bool(), c["residual"].as_i64(), c["liquid"]["residual"].as_i64(), c["entries"].as_u64()), (Some(true), Some(0), Some(0), Some(1)), "{c}");
    assert!(c["token_amounts"].as_array().unwrap().iter().all(|x| x["ok"] == json!(true)), "{c}");
    assert_eq!((c["executor"]["landings"].as_u64(), c["executor"]["diff"].as_i64(), c["executor"]["ok"].as_bool()), (Some(1), Some(0), Some(true)), "{}", c["executor"]);
    let st = r.lines("status");
    let m = &st.last().unwrap()["money"];
    assert_eq!((m["trade_gross_total"].as_i64(), m["tips_total"].as_i64(), m["fees_win_total"].as_i64(), m["rent_locked_total"].as_u64(), m["rent_reclaimed_total"].as_u64(),
        m["trade_net_total"].as_i64()), (Some(gross), Some(tip), Some(FEE as i64), Some(RENT), Some(RENT), Some(gross - tip - FEE as i64)), "{m}");
    let done = r.finish_and_replay();
    done.check_expected();
}

/// A failed landing of the same kind of bundle (the route's profit check after both legs ran: the block engine's
/// `processed`, then the wallet's record of a failed transaction). Everything but the fee is reverted, though the record
/// lists the associated-token program's inner create (it ran before the failure) and the transaction's own CloseAccount:
/// nothing was created, closed or traded. Expected: one ledger line, `route`, not ok, one category `fee_fail` (the base
/// fee), no rent locked or reclaimed, no trade; the attempt final `landed_fail` from the wallet's record; the money's
/// failed fees are the fee
#[test]
fn s14_a_failed_create_close_landing_books_its_fee_only() {
    let (mut r, s2) = canary_rig("s14-failed", &POOLS3, &CANARY, false);
    let a = r.meta("usdc.ammv4");
    let sale = r.sig("S14-sale");
    let mut t = T0 + 10 * MS;
    usdc_sale(&mut r, &a, 40, sale, s2, &mut t);
    r.timers(t + 4 * MS);
    let at = r.attempts()[0].clone();
    assert_eq!((at["tx"]["creates_ata"].as_bool(), at["tx"]["closes_ata"].as_bool()), (Some(true), Some(true)), "{at}");
    r.pump(1, t + 5 * MS);
    r.verdict("b0", "processed", Some(s2 + 1), None, t + 6 * MS);
    let input = wallet_record(&r, &at, &r.bundles_sent()[0], s2 + 1, 3 * SOL, 2 * SOL, false);
    assert_eq!((input["ok"].as_bool(), input["wallet_sol"].as_i64()), (Some(false), Some(-(FEE as i64))), "{input}");
    let t1 = t + 400 * MS;
    r.tick(s2 + 1, t1);
    r.input(InputKind::WalletTx, input, t1 + MS);
    let l = r.lines("ledger");
    assert_eq!(l.len(), 1, "{l:?}");
    let e = &l[0];
    let cats: Vec<(String, i64)> = e["categories"].as_array().unwrap().iter().map(|c| (c["cat"].as_str().unwrap().to_string(), c["lamports"].as_i64().unwrap())).collect();
    assert_eq!(cats, vec![("fee_fail".to_string(), -(FEE as i64))], "the fee only: {e}");
    assert_eq!((e["kind"].as_str(), e["ok"].as_bool(), e["trade_gross"].as_i64(), e["tip"].as_u64()), (Some("route"), Some(false), Some(0), Some(0)), "{e}");
    assert_eq!((e["rent_locked"].as_u64(), e["rent_reclaimed"].as_u64()), (Some(0), Some(0)), "a failed transaction creates and closes nothing: {e}");
    assert!(e["created"].as_array().unwrap().is_empty() && e["closed"].as_array().unwrap().is_empty(), "{e}");
    let o = r.lines("outcomes");
    assert_eq!((o.len(), o[0]["final"].as_str(), o[0]["final_src"].as_str(), o[0]["fee_lamports"].as_u64()), (1, Some("landed_fail"), Some("wallet"), Some(FEE)), "{o:?}");
    r.timers(t1 + 10_001 * MS);
    let st = r.lines("status");
    let m = &st.last().unwrap()["money"];
    assert_eq!((m["fees_fail_total"].as_i64(), m["failed_fees_total_lamports"].as_u64(), m["rent_locked_total"].as_u64()), (Some(FEE as i64), Some(FEE), Some(0)), "{m}");
    let done = r.finish_and_replay();
    done.check_expected();
}

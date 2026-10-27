//! PLAN WP-08 offline acceptance for transfer classification: real transactions with exact kinds and amounts (a
//! Jito-tipped bundle of ours with a PumpSwap creator fee, CPI tips, wrap and unwrap: testdata/wallet/ and
//! testdata/classify/, captured by tools/capture-fixtures.py), the tip map's sources, the cmp2 rivals the old map left
//! unnamed (Glaive), and the hook through the recorder.
use super::*;
use crate::feeds::grpc::{PbHeader, PbInnerIx, PbInnerIxs, PbIx, PbLookup, PbMessage, PbMeta, PbTokenBalance, PbTransaction, PbTxConfig, PbTxError, PbUiAmount};
use std::path::{Path, PathBuf};

fn td(rel: &str) -> PathBuf { Path::new(env!("CARGO_MANIFEST_DIR")).join("testdata").join(rel) }
fn b58d(s: &str) -> Vec<u8> { bs58::decode(s).into_vec().unwrap() }
fn pkd(s: &str) -> Pk { decode_pk(s).unwrap() }

/// bincode `TransactionError` of the RPC's JSON form, as far as the fixtures need it (InstructionError with a custom
/// code, or another variant)
fn tx_err(e: &Value) -> Vec<u8> {
    let mut b = Vec::new();
    match e.get("InstructionError").and_then(Value::as_array) {
        Some(a) => {
            b.extend(8u32.to_le_bytes());
            b.push(a[0].as_u64().unwrap() as u8);
            match a[1].get("Custom").and_then(Value::as_u64) {
                Some(c) => { b.extend(25u32.to_le_bytes()); b.extend((c as u32).to_le_bytes()); }
                None => b.extend(0u32.to_le_bytes()),
            }
        }
        None => b.extend(1u32.to_le_bytes()),
    }
    b
}

/// A getTransaction result (base64 wire bytes, JSON meta) as the transaction stream delivers it: the protobuf
/// transaction and meta that `rec::exec::exec_json` reads
pub(crate) fn pb_of_rpc(r: &Value) -> ([u8; 64], PbTransaction, PbMeta) {
    let wire = B64.decode(r["transaction"][0].as_str().unwrap()).unwrap();
    let (tx, _) = crate::tx::parse_wire(&wire).expect("wire transaction");
    let msg = PbMessage {
        header: Some(PbHeader { num_required_signatures: tx.num_signers as u32, num_readonly_signed_accounts: tx.num_ro_signed as u32,
            num_readonly_unsigned_accounts: tx.num_ro_unsigned as u32 }),
        account_keys: tx.keys.iter().map(|k| k.to_vec()).collect(),
        recent_blockhash: vec![0; 32],
        instructions: tx.ixs.iter().map(|i| PbIx { program_id_index: i.program as u32, accounts: i.accounts.clone(), data: i.data.clone() }).collect(),
        versioned: r["version"] != json!("legacy"),
        address_table_lookups: tx.lookups.iter().map(|l| PbLookup { account_key: l.table.to_vec(), writable_indexes: l.writable.clone(), readonly_indexes: l.readonly.clone() }).collect(),
        config: tx.v1.then(|| PbTxConfig { priority_fee: tx.cu_price_micro, compute_unit_limit: tx.cu_limit, ..Default::default() }),
    };
    let m = &r["meta"];
    let strs = |v: &Value| -> Vec<Vec<u8>> { v.as_array().into_iter().flatten().filter_map(Value::as_str).map(b58d).collect() };
    let tok = |v: &Value| -> Vec<PbTokenBalance> { v.as_array().into_iter().flatten().map(|b| PbTokenBalance {
        account_index: b["accountIndex"].as_u64().unwrap() as u32, mint: b["mint"].as_str().unwrap().into(),
        ui_token_amount: Some(PbUiAmount { decimals: b["uiTokenAmount"]["decimals"].as_u64().unwrap() as u32, amount: b["uiTokenAmount"]["amount"].as_str().unwrap().into() }),
        owner: b["owner"].as_str().unwrap_or("").into(), program_id: b["programId"].as_str().unwrap_or("").into() }).collect() };
    let meta = PbMeta {
        err: (!m["err"].is_null()).then(|| PbTxError { err: tx_err(&m["err"]) }),
        fee: m["fee"].as_u64().unwrap(),
        pre_balances: m["preBalances"].as_array().unwrap().iter().map(|x| x.as_u64().unwrap()).collect(),
        post_balances: m["postBalances"].as_array().unwrap().iter().map(|x| x.as_u64().unwrap()).collect(),
        inner_instructions: m["innerInstructions"].as_array().into_iter().flatten().map(|g| PbInnerIxs { index: g["index"].as_u64().unwrap() as u32,
            instructions: g["instructions"].as_array().unwrap().iter().map(|x| PbInnerIx { program_id_index: x["programIdIndex"].as_u64().unwrap() as u32,
                accounts: x["accounts"].as_array().unwrap().iter().map(|a| a.as_u64().unwrap() as u8).collect(), data: b58d(x["data"].as_str().unwrap()),
                stack_height: x["stackHeight"].as_u64().map(|h| h as u32) }).collect() }).collect(),
        log_messages: m["logMessages"].as_array().into_iter().flatten().filter_map(Value::as_str).map(String::from).collect(),
        pre_token_balances: tok(&m["preTokenBalances"]), post_token_balances: tok(&m["postTokenBalances"]),
        inner_instructions_none: m["innerInstructions"].is_null(), log_messages_none: m["logMessages"].is_null(),
        loaded_writable_addresses: strs(&m["loadedAddresses"]["writable"]), loaded_readonly_addresses: strs(&m["loadedAddresses"]["readonly"]),
        return_data: None, return_data_none: true,
        compute_units_consumed: m["computeUnitsConsumed"].as_u64(), cost_units: m["costUnits"].as_u64(),
    };
    (tx.sig, PbTransaction { signatures: vec![tx.sig.to_vec()], message: Some(msg) }, meta)
}

/// a fixture as its exec.jsonl line: `exec_json`, then the derived-field hook, as `rec::exec::emit_grpc` does
fn record(rel: &str) -> Value { record_with(rel, |_| {}) }

/// the same, with `edit` applied to the record before the hook
fn record_with(rel: &str, edit: impl FnOnce(&mut Value)) -> Value {
    let r: Value = serde_json::from_str(&std::fs::read_to_string(td(rel)).unwrap()).unwrap();
    let (sig, tx, meta) = pb_of_rpc(&r);
    let mut v = crate::rec::exec::exec_json(&sig, r["slot"].as_u64().unwrap(), r["transactionIndex"].as_u64(), 1, "rpc-wallet", &["ours"], &tx, &meta, None);
    edit(&mut v);
    crate::rec::exec::derive(&mut v);
    assert_eq!(v["sig"].as_str(), Some(rel.rsplit('/').next().unwrap().trim_end_matches(".json")), "the fixture's own signature");
    v
}

/// (kind, from, to, lamports, mint, amount, sender, depth, ix) of every transfer, accounts by their first 8 characters
fn rows(v: &Value) -> Vec<(String, String, String, Option<u64>, Option<String>, Option<u64>, Option<String>, u64, u64)> {
    v["transfers"].as_array().expect("transfers filled").iter().map(|t| (t["kind"].as_str().unwrap().to_string(), t["from"].as_str().unwrap()[..8].to_string(),
        t["to"].as_str().unwrap()[..8].to_string(), t["lamports"].as_u64(), t["mint"].as_str().map(|m| m[..8].to_string()),
        t["amount"].as_str().map(|a| a.parse().unwrap()), t["sender"].as_str().map(String::from), t["depth"].as_u64().unwrap(), t["ix"].as_u64().unwrap())).collect()
}
fn r(kind: &str, from: &str, to: &str, lamports: Option<u64>, mint: Option<&str>, amount: Option<u64>, sender: Option<&str>, depth: u64, ix: u64)
    -> (String, String, String, Option<u64>, Option<String>, Option<u64>, Option<String>, u64, u64) {
    (kind.into(), from.into(), to.into(), lamports, mint.map(String::from), amount, sender.map(String::from), depth, ix)
}
const WSOL8: Option<&str> = Some("So111111");

/// Acceptance: a Jito-tipped bundle transaction of ours (w5h2/w5h3 win, testdata/wallet) whose PumpSwap
/// buy_exact_quote_in leg (inside our program, stack height 2) pays the coin creator: the tip is a top-level
/// `sender_tip` to Jito; the creator, protocol and buyback fees are `venue_fee`; the base-token ATA's rent is
/// `rent_create`; swap legs are `other`. Exact amounts from the chain (balances agree: the creator vault 9DdVkgE2 +396,412,
/// Jito's 3AVi9Tg9 +7,254; the token balances: the PumpSwap base vault CZxdssvX -91,697,818,437, the DLMM vault 688daH4T
/// +91,697,818,437)
#[test]
fn a_jito_bundle_of_ours_with_a_pumpswap_creator_fee() {
    let v = record("wallet/1WUBGeUhRymCbU8yyVqvxmbSkWEaNJwd3A98kxyAuyj2PjeN6VfcgAdJvyWxqX2fTQ4iX98UW6NocREXsNKq7q9.json");
    assert_eq!(rows(&v), vec![
        r("rent_create", "2g7rYv7y", "He6yB9Mn", Some(1_513_840), None, None, None, 1, 2),
        r("other", "CZxdssvX", "He6yB9Mn", None, Some("JCX5nDG9"), Some(91_697_818_437), None, 2, 3),
        r("other", "D3qtLfeA", "DzBBhgJN", None, WSOL8, Some(41_811_016), None, 2, 3),
        r("venue_fee", "D3qtLfeA", "DWpvfqzG", None, WSOL8, Some(10_432), None, 2, 3),
        r("venue_fee", "D3qtLfeA", "9DdVkgE2", None, WSOL8, Some(396_412), None, 2, 3),
        r("venue_fee", "D3qtLfeA", "qkYdTGRP", None, WSOL8, Some(10_432), None, 2, 3),
        r("other", "He6yB9Mn", "688daH4T", None, Some("JCX5nDG9"), Some(91_697_818_437), None, 2, 3),
        r("other", "BkAxuMTt", "D3qtLfeA", None, WSOL8, Some(42_243_647), None, 2, 3),
        r("sender_tip", "2g7rYv7y", "3AVi9Tg9", Some(7_254), None, None, Some("jito"), 0, 4),
    ]);
    assert_eq!((v["tip_total"].as_u64(), v["tip_asked"].as_u64(), v["tip_senders"].clone(), v["jito_tipped"].as_bool()), (Some(7_254), Some(7_254), json!(["jito"]), Some(true)));
    assert_eq!(v["bundle"], json!({ "known": false, "src": "heuristic", "id": null, "pos": null, "size": null }), "a Jito tip: a bundle candidate");
    // once the block engine's processed result names it, the line carries the bundle (WP-05 calls note_bundle_processed)
    note_bundle_processed(v["sig"].as_str().unwrap(), "b-uuid-1", 453_084_225, 7);
    let again = record("wallet/1WUBGeUhRymCbU8yyVqvxmbSkWEaNJwd3A98kxyAuyj2PjeN6VfcgAdJvyWxqX2fTQ4iX98UW6NocREXsNKq7q9.json");
    assert_eq!(again["bundle"], json!({ "known": true, "src": "jito-result", "id": "b-uuid-1", "pos": 0, "size": 1, "slot": 453_084_225u64, "index": 7 }));
}

/// Acceptance: a CPI tip. A legacy transaction whose program pays Jito from inside (System transfer at stack height 2:
/// `cpi_tip`, depth 1); the vault program's refund to the signer (stack height 3) is `other`. Balances: Jito's 96gYZGLn
/// +202,846
#[test]
fn a_cpi_tip() {
    let v = record("classify/3hdmTiRUBQUDTbGai4jnHMrocdjhoLVMAmqd4Rrdcg9NReC3FtJQBgZbkKY4FYTyfYCDuGzhmPkJ33tjQMaifgz8.json");
    assert_eq!(rows(&v), vec![
        r("other", "2EnUkUjG", "BVabVxQn", Some(4_078_560), None, None, None, 2, 0),
        r("cpi_tip", "BVabVxQn", "96gYZGLn", Some(202_846), None, None, Some("jito"), 1, 0),
    ]);
    assert_eq!((v["tip_total"].as_u64(), v["tip_senders"].clone(), v["jito_tipped"].as_bool()), (Some(202_846), json!(["jito"]), Some(true)));
    assert_eq!(v["bundle"]["src"].as_str(), Some("heuristic"));
}

/// Review WP-08 #5: the same Jito-tipped transaction, had it failed. A Jito bundle lands only when all of it succeeds,
/// so a failed transaction is in no bundle (`bundle` null); it paid no tip (`tip_total` 0) but its transfers and
/// `tip_asked` still name the lane it asked for (Jito)
#[test]
fn a_failed_jito_tipped_transaction_is_no_bundle_and_paid_no_tip() {
    let v = record_with("classify/3hdmTiRUBQUDTbGai4jnHMrocdjhoLVMAmqd4Rrdcg9NReC3FtJQBgZbkKY4FYTyfYCDuGzhmPkJ33tjQMaifgz8.json", |v| v["ok"] = json!(false));
    assert_eq!(rows(&v).last().map(|x| (x.0.clone(), x.3, x.6.clone())), Some(("cpi_tip".to_string(), Some(202_846), Some("jito".to_string()))), "the transfers stay");
    assert_eq!((v["tip_total"].as_u64(), v["tip_asked"].as_u64(), v["jito_tipped"].as_bool(), v["tip_senders"].clone(), v["bundle"].clone()),
        (Some(0), Some(202_846), Some(true), json!(["jito"]), Value::Null));
}

/// A CPI tip paid by a program's vault (not the signer), and a PumpSwap sell three levels down (a Jupiter route inside
/// an arbitrage program, v0 with lookup tables): the sell's protocol, creator and buyback fees come out of the pool's
/// quote vault and are `venue_fee` at depth 3
#[test]
fn a_cpi_tip_from_a_program_vault_and_pumpswap_sell_fees() {
    let v = record("classify/3SBF5po14VDjQw8MjMfructaimWuPWthh36b8cbWPqPdXF5fLKHJh5d8NBYPqzELYUdymtU1JTAQqmhFoewkvqwK.json");
    let rs = rows(&v);
    let fees: Vec<_> = rs.iter().filter(|x| x.0 == "venue_fee").cloned().collect();
    assert_eq!(fees, vec![
        r("venue_fee", "EeAL1aa1", "X5QPJcpp", None, WSOL8, Some(1_345), None, 3, 2),
        r("venue_fee", "EeAL1aa1", "2YNqvqKK", None, WSOL8, Some(32_266), None, 3, 2),
        r("venue_fee", "EeAL1aa1", "6rVkF4HS", None, WSOL8, Some(1_344), None, 3, 2),
    ]);
    assert_eq!(rs.last(), Some(&r("cpi_tip", "BpPDmeBf", "Cw8CFyM9", Some(6_255), None, None, Some("jito"), 1, 3)));
    assert!(rs.iter().filter(|x| x.0 != "venue_fee" && x.0 != "cpi_tip").all(|x| x.0 == "other"), "the swap legs: {rs:?}");
    assert_eq!((v["tip_total"].as_u64(), v["jito_tipped"].as_bool()), (Some(6_255), Some(true)));
}

/// Acceptance: wrap and unwrap, in a top-level PumpSwap buy that pays the coin creator. The WSOL ATA is created and
/// closed in the transaction (in no token balance: its mint and owner come from the ATA instruction), funded by a
/// System transfer followed by SyncNative (`wrap`), and closed back to the signer with what the buy left (`unwrap`,
/// 1,488,440 rent + 239,868,095 wrapped - 207,477,901 spent = 33,878,634; the signer's balance change agrees:
/// -210,442,942 = -105,001 fee - 1,513,840 - 1,488,440 - 239,868,095 - 1,346,200 rent and wrap + 33,878,634; the bought
/// tokens: the base vault CX3Rx7ys -438,335,123,705, the new ATA 6eQtMB4X +438,335,123,705)
#[test]
fn wrap_and_unwrap_in_a_pumpswap_buy_with_a_creator_fee() {
    let v = record("classify/Kk7Nd3EFDTs3CESR4v2bQQB83CFgUfasqPdgdfBJPvPH48EYerL8HUpne7TJjipQ7r9Ub7idqvcP9RB7BS1n9Wf.json");
    assert_eq!(rows(&v), vec![
        r("rent_create", "4vbfZM25", "6eQtMB4X", Some(1_513_840), None, None, None, 1, 2),
        r("rent_create", "4vbfZM25", "HK85xR7c", Some(1_488_440), None, None, None, 1, 3),
        r("wrap", "4vbfZM25", "HK85xR7c", Some(239_868_095), None, None, None, 0, 4),
        r("rent_create", "4vbfZM25", "AgUaM5DD", Some(1_346_200), None, None, None, 1, 6),
        r("other", "CX3Rx7ys", "6eQtMB4X", None, Some("GxGrp3RS"), Some(438_335_123_705), None, 1, 6),
        r("other", "HK85xR7c", "6txwtZaU", None, WSOL8, Some(205_427_723), None, 1, 6),
        r("venue_fee", "HK85xR7c", "94qWNrtm", None, WSOL8, Some(51_255), None, 1, 6),
        r("venue_fee", "HK85xR7c", "24VqrMhT", None, WSOL8, Some(1_947_669), None, 1, 6),
        r("venue_fee", "HK85xR7c", "CA7v8gHf", None, WSOL8, Some(51_254), None, 1, 6),
        r("unwrap", "HK85xR7c", "4vbfZM25", Some(33_878_634), WSOL8, None, None, 0, 7),
    ]);
    assert_eq!((v["tip_total"].as_u64(), v["tip_senders"].clone(), v["jito_tipped"].as_bool(), v["bundle"].clone()), (Some(0), json!([]), Some(false), Value::Null));
}

/// Acceptance: the wallet's own setup wrap (testdata/wallet): the WSOL ATA's rent, then 4.2 SOL in and SyncNative
#[test]
fn the_wallets_setup_wrap() {
    let v = record("wallet/2rw9r59fq2V3VNMEwWbienLyV98jqoitFDTsgNWwHiNMHisgESyx66f6buB85AbCZJ8TKzbX9zGpgTj6pgcWa2Hk.json");
    assert_eq!(rows(&v), vec![
        r("rent_create", "2g7rYv7y", "D3qtLfeA", Some(1_488_440), None, None, None, 1, 0),
        r("wrap", "2g7rYv7y", "D3qtLfeA", Some(4_200_000_000), None, None, None, 0, 1),
    ]);
}

/// The addendum's Glaive tips, in two failed rival transactions (v0 with a durable nonce, and v1): a failed
/// transaction moved nothing, but its transfers are the ones it asked for, so the lane it used is named; it paid no tip
/// (`tip_total` 0, `tip_asked` what it asked: review WP-08 #5)
#[test]
fn glaive_tips_in_failed_transactions_v0_and_v1() {
    let v = record("classify/3QWEcbXwCR6J7TttkwBbG46YMhAtp7GLSESVhsvVePztuqXrSXLSmiQqiQ8BxwwzavCty6GgFvAJ13QjfjHhV4Yt.json");
    assert_eq!(v["ok"].as_bool(), Some(false));
    assert_eq!(rows(&v), vec![r("sender_tip", "4DcT8f8V", "GLaivinA", Some(30_036_343), None, None, Some("glaive"), 0, 3)]);
    assert_eq!((v["tip_total"].as_u64(), v["tip_asked"].as_u64(), v["tip_senders"].clone(), v["jito_tipped"].as_bool(), v["bundle"].clone()),
        (Some(0), Some(30_036_343), json!(["glaive"]), Some(false), Value::Null));
    let w = record("classify/3kJuXhocws1GpyqXWkCwSU337oNCFbz6XRPdCqR8ysYnDyJsBb4Dh78PctAuEuVCTVgVuTdeGjUqZ43fBubGrEQX.json");
    assert_eq!((w["version"].as_str(), w["ok"].as_bool()), (Some("1"), Some(false)));
    let tips: Vec<_> = rows(&w).into_iter().filter(|x| x.0 == "sender_tip").collect();
    assert_eq!(tips.len(), 1, "{:?}", rows(&w));
    assert_eq!((tips[0].2.starts_with("GLaiv"), tips[0].6.as_deref()), (true, Some("glaive")));
}

/// The addendum: cmp2's rivals tipped Glaive 4,197 times and the old map (send/mod.rs's lists alone) named none of
/// them. The fixture holds every tip account cmp2 recorded without a sender (at least 20 rows, or listed in
/// data/sender-tip-accounts.json): the code lists name none, the full map names Glaive's 4,197 rows, Soyas' 458, the
/// bloXroute legacy accounts' 72 and Solami's, and leaves the rest unknown. rivals.jsonl's names are the same map
/// (`send::tip_owner_names`, the engine's `tip_names`: review WP-08 #1)
#[test]
fn cmp2_rival_tips_the_old_map_left_unnamed_are_named_now() {
    let f: Value = serde_json::from_str(&std::fs::read_to_string(td("classify/cmp2-rival-tips.json")).unwrap()).unwrap();
    assert_eq!(tip_map().names(), crate::send::tip_owner_names(), "exec.jsonl and rivals.jsonl name tips alike");
    let old = crate::send::code_tip_names();
    let mut by: std::collections::BTreeMap<String, u64> = Default::default();
    let mut unknown_rows = 0;
    for (a, x) in f["accounts"].as_object().unwrap() {
        let k = pkd(a);
        // dip16 (10-25): Glaive became a send kind, so the code's lists name its 6 accounts now ("glaive", as the catalogue)
        if crate::send::known_tip_accounts(crate::config::SendKind::Glaive).contains(&a.as_str()) { assert_eq!(old.get(&k).map(String::as_str), Some("glaive")); }
        // dip17 (10-25): Soyas and Solami became send kinds too (Solami: the crate's 10 "...beam" accounts)
        else if crate::send::known_tip_accounts(crate::config::SendKind::Soyas).contains(&a.as_str()) { assert_eq!(old.get(&k).map(String::as_str), Some("soyas")); }
        else if crate::send::known_tip_accounts(crate::config::SendKind::Solami).contains(&a.as_str()) { assert_eq!(old.get(&k).map(String::as_str), Some("solami")); }
        else { assert!(!old.contains_key(&k), "{a} was named by the old map"); }
        let rows = x["rows"].as_u64().unwrap();
        match tip_map().get(&k) { Some(s) => *by.entry(s.to_string()).or_default() += rows, None => unknown_rows += rows }
    }
    assert_eq!(by.get("glaive"), Some(&4_197), "{by:?}");
    assert_eq!(by.get("soyas"), Some(&458));
    assert_eq!(by.get("bloxroute"), Some(&72));
    assert_eq!(by.get("solami"), Some(&16));
    assert_eq!(by.keys().cloned().collect::<Vec<_>>(), vec!["bloxroute", "glaive", "solami", "soyas"], "only the added services");
    assert!(unknown_rows > 20_000, "the other unnamed accounts stay unknown ({unknown_rows} rows): {by:?}");
}

/// The assigned tip accounts are in data/sender-tip-accounts.json with a provider source per address: Glaive (6),
/// Soyas (10), SpeedLanding (8), AllenHark (11), Solami (15), bloXroute legacy (2: bloxroute.sol, bloxroute1.sol) and
/// SVS legacy (2), each with `source_url`, `fetched` and an `attribution`; the full map names every one
#[test]
fn the_tip_map_and_its_sources() {
    let d: Value = serde_json::from_str(include_str!("../../data/sender-tip-accounts.json")).unwrap();
    for (svc, sender, n) in [("glaive", "glaive", 6), ("soyas", "soyas", 10), ("speedlanding", "speedlanding", 8), ("allenhark_relay", "allenhark", 11),
        ("solami_beam", "solami", 15), ("bloxroute_legacy", "bloxroute", 2), ("svs_lightspeed_legacy", "svs_lightspeed", 2)] {
        let s = &d[svc];
        let accts: Vec<&str> = s["tip_accounts"].as_array().unwrap().iter().map(|a| a.as_str().unwrap()).collect();
        assert_eq!((accts.len(), s["tip_account_count"].as_u64()), (n, Some(n as u64)), "{svc}");
        let src = s["tip_account_sources"].as_array().unwrap();
        assert_eq!(src.iter().map(|x| x["address"].as_str().unwrap()).collect::<Vec<_>>(), accts, "{svc}: one source per address");
        for x in src {
            assert!(x["source_url"].as_str().is_some_and(|u| u.starts_with("https://")), "{svc}: {x}");
            assert_eq!(x["fetched"].as_str(), Some("2026-10-04"));
            assert!(["provider_docs", "provider_api", "provider_docs_archived", "unverified"].contains(&x["attribution"].as_str().unwrap()), "{svc}: {x}");
            if x["attribution"] == "unverified" { assert!(x["note"].is_string(), "an unverified address needs a note"); }
        }
        for a in accts { assert_eq!(tip_map().get(&pkd(a)), Some(sender), "{svc} {a}"); }
    }
    // the code's names come first (rivals.jsonl keeps its names); the file adds the rest, Jito's accounts stay Jito's
    assert_eq!(tip_map().get(&pkd("SpEEdz8S1KorkMZqjMUxfxrmWwofmp6ReNP2Nx6CUmq")), Some("speedlanding"));
    assert_eq!(tip_map().get(&pkd("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5")), Some("jito"));
    assert!(tip_map().is_jito(&pkd("96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5")) && !tip_map().is_jito(&pkd("GLaivinAWh21NaJMhtExtD5G2gZs1xnvaYVZmwqobWZL")));
    // 46 on 2026-10-04; dip16 (10-25) moved Glaive's 6 into the code's lists (a send kind now)
    // dip17 (10-25): Soyas' 10 and Solami's 10 "...beam" accounts moved into the code's lists too
    assert_eq!(tip_map().len(), crate::send::code_tip_names().len() + 20, "the file adds 20 accounts the code lists do not name");
    assert_eq!(TipMap::build(crate::send::TIP_CATALOGUE).names(), tip_map().names());
    assert!(platform_map().is_empty(), "no platform wallet is sourced yet (data/platform-fee-wallets.json)");
}

// ------------------------------------------------------------------------------------------------ synthetic

fn k(n: u8) -> Pk { [n; 32] }
fn sys_transfer(lamports: u64) -> Vec<u8> { let mut d = 2u32.to_le_bytes().to_vec(); d.extend(lamports.to_le_bytes()); d }
fn ix(p: usize, a: &[usize], d: &[u8]) -> Value { json!({ "p": p, "a": a, "d": B64.encode(d) }) }

/// A §4.14 record of `keys` (key 0 signs) with top-level `ixs` and inner groups
fn rec_of(keys: &[Pk], ixs: Vec<Value>, inner: Option<Vec<Value>>, pre: Vec<u64>, toks: Vec<Value>) -> Value {
    json!({ "sig": "s", "ok": true, "keys": keys.iter().map(b58).collect::<Vec<_>>(), "ixs": ixs, "inner": inner, "pre": pre, "post": [],
        "pre_tok": toks, "post_tok": [], "venues": [], "pools": [] })
}

/// The rules the fixtures do not reach: platform fees (a test map), self transfers, CreateAccountWithSeed,
/// TransferWithSeed, a close of a non-WSOL token account (`rent_close`, lamports from the running balance), an account
/// registered by InitializeAccount3, a transfer to the signer's WSOL account without SyncNative (`self`), and a record
/// without inner instructions (top level only)
#[test]
fn rules_on_synthetic_records() {
    let tok = *crate::pda::TOKEN_PROGRAM;
    let wsol = *crate::venues::WSOL;
    // keys: 0 signer, 1 system, 2 token program, 3 platform wallet, 4 signer's token account (mint 9), 5 another token
    // account of the signer (mint 9), 6 a platform's token account (mint 9), 7 the signer's WSOL account, 8 a seeded
    // account, 9 a mint, 10 a stranger, 11 a new token account (InitializeAccount3), 12 WSOL mint
    let keys: Vec<Pk> = vec![k(1), SYSTEM, tok, k(3), k(4), k(5), k(6), k(7), k(8), k(9), k(10), k(11), wsol];
    let toks = vec![json!({ "i": 4, "mint": b58(&k(9)), "owner": b58(&k(1)) }), json!({ "i": 5, "mint": b58(&k(9)), "owner": b58(&k(1)) }),
        json!({ "i": 6, "mint": b58(&k(9)), "owner": b58(&k(3)) }), json!({ "i": 7, "mint": b58(&wsol), "owner": b58(&k(1)) })];
    let tt = |amount: u64| { let mut d = vec![3u8]; d.extend(amount.to_le_bytes()); d };
    let seed_create = { let mut d = 3u32.to_le_bytes().to_vec(); d.extend([8u8; 32]); d.extend(4u64.to_le_bytes()); d.extend(b"seed"); d.extend(500u64.to_le_bytes()); d.extend(0u64.to_le_bytes()); d.extend([2u8; 32]); d };
    let seed_xfer = { let mut d = 11u32.to_le_bytes().to_vec(); d.extend(77u64.to_le_bytes()); d.extend(4u64.to_le_bytes()); d.extend(b"seed"); d.extend([1u8; 32]); d };
    let init3 = { let mut d = vec![18u8]; d.extend(k(1)); d };
    let ixs = vec![
        ix(1, &[0, 3], &sys_transfer(1_000)),     // 0: to a platform wallet
        ix(2, &[4, 6, 0], &tt(50)),               // 1: token transfer to a platform's token account
        ix(2, &[4, 5, 0], &tt(60)),               // 2: between the signer's token accounts: self
        ix(1, &[0, 7], &sys_transfer(2_000)),     // 3: into the signer's WSOL account, no SyncNative after: self
        ix(1, &[0, 8, 0], &seed_create),          // 4: CreateAccountWithSeed: rent_create 500
        ix(1, &[8, 0, 10], &seed_xfer),           // 5: TransferWithSeed from the seeded account to a stranger: other
        ix(2, &[11, 9], &init3),                  // 6: InitializeAccount3: account 11, mint 9, owner the signer
        ix(2, &[5, 0, 0], &[9]),                  // 7: CloseAccount of a non-WSOL token account: rent_close
        ix(2, &[4, 11, 0], &tt(5)),               // 8: to the new account (owner the signer): self
    ];
    let pre = vec![10_000, 1, 1, 0, 2_000_000, 2_039_280, 2_000_000, 2_039_280, 0, 0, 0, 0, 0];
    let tm = TipMap::build("{}");
    let pm = PlatformMap::build(&json!({ "platforms": { "terminal_x": { "wallets": [{ "address": b58(&k(3)) }] } } }).to_string());
    let c = classify_with(&rec_of(&keys, ixs.clone(), Some(vec![]), pre.clone(), toks.clone()), &tm, &pm).unwrap();
    let got: Vec<(&str, Option<u64>, Option<u64>, Option<&str>)> = c.transfers.iter().map(|t| (t.kind, t.lamports, t.amount, t.sender.as_deref())).collect();
    assert_eq!(got, vec![("platform_fee", Some(1_000), None, Some("terminal_x")), ("platform_fee", None, Some(50), Some("terminal_x")), ("self", None, Some(60), None),
        ("self", Some(2_000), None, None), ("rent_create", Some(500), None, None), ("other", Some(77), None, None), ("rent_close", Some(2_039_280), None, None),
        ("self", None, Some(5), None)]);
    assert_eq!(c.transfers[6].mint, Some(k(9)));
    // without platform wallets the same transfers are other / other
    let c = classify_with(&rec_of(&keys, ixs, None, pre.clone(), toks.clone()), &tm, &PlatformMap::build("{}")).unwrap();
    assert_eq!((c.transfers[0].kind, c.transfers[1].kind), ("other", "other"));
    // review WP-08 #19: a stranger paying into the signer's WSOL account (a SyncNative after it) is neither the
    // signer's wrap nor `self`: `other`; the signer's own transfer there is the wrap
    let ixs = vec![ix(1, &[10, 7], &sys_transfer(300)), ix(1, &[0, 7], &sys_transfer(400)), ix(2, &[7], &[17])];
    let c = classify_with(&rec_of(&keys, ixs, Some(vec![]), pre, toks), &tm, &PlatformMap::build("{}")).unwrap();
    assert_eq!(c.transfers.iter().map(|t| (t.kind, t.lamports)).collect::<Vec<_>>(), vec![("other", Some(300)), ("wrap", Some(400))]);
    // a record that does not decode keeps its derived fields null
    let mut bad = json!({ "keys": ["not base58 !"], "ixs": [], "transfers": null });
    annotate(&mut bad);
    assert!(bad["transfers"].is_null());
}

/// arb_like: the record_rival test (two venues besides the aggregator, two watched pools, a signer seen before) plus
/// a known arbitrage program touching one watched pool
#[test]
fn arb_like_rules() {
    let keys = |signer: u8, prog: u8| vec![k(signer), k(prog)];
    let mk = |signer: u8, prog: u8, venues: &[&str], pools: usize| {
        let mut v = rec_of(&keys(signer, prog), vec![ix(1, &[0], &[1])], Some(vec![]), vec![], vec![]);
        v["venues"] = json!(venues);
        v["pools"] = json!((0..pools).map(|i| b58(&k(200 + i as u8))).collect::<Vec<_>>());
        annotate(&mut v);
        v["arb_like"].clone()
    };
    // fresh signers (0xA1..) and programs (0xB1..) so other tests' learning does not interfere
    assert_eq!(mk(0xA1, 0xB1, &["dlmm", "pumpswap"], 0), json!({ "is": true, "why": "venues" }));
    assert_eq!(mk(0xA2, 0xB2, &["pumpswap"], 2), json!({ "is": true, "why": "pools" }));
    assert_eq!(mk(0xA1, 0xB3, &["pumpswap"], 0), json!({ "is": true, "why": "known" }), "the signer did an arbitrage before");
    assert_eq!(mk(0xA3, 0xB1, &["pumpswap"], 1), json!({ "is": true, "why": "program" }), "a known arbitrage program on a watched pool");
    assert_eq!(mk(0xA4, 0xB1, &["pumpswap"], 0), json!({ "is": false, "why": null }), "no watched pool");
    // the aggregator is not a venue, and an aggregator route teaches nothing
    assert_eq!(mk(0xA5, 0xB5, &["jupiter", "pumpswap"], 0), json!({ "is": false, "why": null }));
    assert_eq!(mk(0xA6, 0xB6, &["jupiter", "dlmm", "pumpswap"], 0), json!({ "is": true, "why": "venues" }));
    assert_eq!(mk(0xA6, 0xB7, &["pumpswap"], 0), json!({ "is": false, "why": null }), "learned nothing from an aggregator route");
}

/// The hook is wired: a transaction-stream record written through `emit_grpc` (the chain writer) carries the derived
/// fields in exec.jsonl, under the bumped schema
#[test]
fn exec_jsonl_lines_carry_the_derived_fields() {
    let d = std::env::temp_dir().join(format!("arbx-classify-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
        echo: Some(Box::new(std::io::sink())) }).unwrap();
    let r: Value = serde_json::from_str(&std::fs::read_to_string(td("classify/3hdmTiRUBQUDTbGai4jnHMrocdjhoLVMAmqd4Rrdcg9NReC3FtJQBgZbkKY4FYTyfYCDuGzhmPkJ33tjQMaifgz8.json")).unwrap()).unwrap();
    let (sig, tx, meta) = pb_of_rpc(&r);
    crate::rec::exec::emit_grpc(&rec, None, crate::rec::exec::GrpcTx { sig: sig.to_vec(), slot: 453_330_549, idx: 90, t: 1, tx: std::sync::Arc::new(tx), meta, bank_id: None, sample: None });
    rec.close();
    let ex = crate::rec::read_jsonl(&d, "exec").unwrap();
    assert_eq!(ex.len(), 1);
    assert_eq!((ex[0]["tip_total"].as_u64(), ex[0]["jito_tipped"].as_bool(), ex[0]["transfers"][1]["kind"].as_str()), (Some(202_846), Some(true), Some("cpi_tip")));
    assert!(ex[0]["arb_like"].is_object() && ex[0]["ours"].is_null());
    let head = String::from_utf8(crate::rec::read_files(&d, "exec").unwrap().remove(0)).unwrap();
    assert!(head.lines().next().unwrap().contains("\"arbx.exec/2.2\""), "{}", head.lines().next().unwrap());
    let _ = std::fs::remove_dir_all(&d);
}

/// Every kind name is MEASUREMENT A.4's
#[test]
fn kinds_are_measurements() {
    let doc = include_str!("../../docs/MEASUREMENT.md");
    let line = doc.lines().find(|l| l.starts_with("`sender_tip`, `cpi_tip`")).expect("A.4 list");
    for k in kind::ALL { assert!(line.contains(&format!("`{k}`")), "{k}"); }
}

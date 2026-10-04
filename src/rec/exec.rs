//! exec.jsonl v2 (MEASUREMENT §4.14; PLAN WP-03 item 9): one executed transaction touching a watched account, with its
//! full meta: raw instructions, inner instructions, logs, balances, loaded addresses and compute-budget parameters.
//! It replaces arb-lab's PumpSwap-only `rec_exec` (feeds/grpc.rs). The record is built and serialized on the
//! recorder's chain writer: the producer only moves the protobuf transaction and meta into the closure.
//!
//! Derived fields come later and are null here: transfer classification (`transfers`, `tip_total`, `tip_senders`,
//! `jito_tipped`), bundle membership (`bundle`), `arb_like` (WP-08), our own attempts (`ours`, `prog_events`: WP-05,
//! WP-08). wallet.jsonl (WP-03b) uses the same field builder ([`exec_json`]) with its own `src` and extras.
use super::accounts::{role, Roles};
use super::{Rec, Record, EXEC};
use crate::feeds::grpc::{PbMeta, PbTransaction};
use crate::tx::{b58, Pk, COMPUTE_BUDGET};
use base64::Engine as _;
use serde_json::{json, Map, Value};
use std::sync::{Arc, LazyLock};

/// One transaction of a gRPC transaction stream
pub struct GrpcTx { pub sig: Vec<u8>, pub slot: u64, pub idx: u64, pub t: u64, pub tx: Arc<PbTransaction>, pub meta: PbMeta, pub bank_id: Option<u64> }

/// The (signature, slot) pairs a transaction stream wrote lately (review WP-03 #10). A stream at processed commitment
/// can deliver one transaction twice (around a reconnect the provider re-sends the recent past): exec.jsonl keeps one
/// line per (signature, slot). A transaction executed on two forks (two slots) keeps both lines: a reader picks the
/// one on the canonical fork. Kept across the stream's reconnects; the oldest pairs are forgotten past `MAX`
#[derive(Default)]
pub struct Recent { set: rustc_hash::FxHashSet<(u64, u64)>, order: std::collections::VecDeque<(u64, u64)>, pub dups: u64 }

impl Recent {
    pub const MAX: usize = 200_000;
    /// true the first time (sig, slot) is seen; false (counted in `dups`) for a repeat
    pub fn first(&mut self, sig: &[u8], slot: u64) -> bool {
        let k = (sig.get(..8).map_or(0, |b| u64::from_le_bytes(b.try_into().unwrap())), slot);
        if !self.set.insert(k) { self.dups += 1; return false; }
        self.order.push_back(k);
        while self.order.len() > Self::MAX { if let Some(o) = self.order.pop_front() { self.set.remove(&o); } }
        true
    }
}

/// exec.jsonl v2 for a transaction from the stream (src `grpc-tx`, found by `tx_stream`). The record holds the whole
/// transaction and meta until the chain writer encodes it: it counts against the queue's byte cap at their encoded
/// size (review WP-03 #8). True when the recorder took the record (WP-03b: a dropped one is backfilled)
pub fn emit_grpc(rec: &Rec, roles: Option<&Arc<Roles>>, x: GrpcTx) -> bool {
    if !rec.is_on() { return false; }
    use prost::Message as _;
    let roles = roles.cloned();
    let size = (x.tx.encoded_len() + x.meta.encoded_len() + x.sig.len()) as u64;
    rec.emit_sized(EXEC, size, Record::enc(move |o| {
        let mut v = exec_json(&x.sig, x.slot, Some(x.idx), x.t, "grpc-tx", &["tx_stream"], &x.tx, &x.meta, roles.as_deref());
        // the bank it executed in, when the provider sends it (review WP-03 #12)
        v["bank_id"] = serde_json::json!(x.bank_id);
        let _ = serde_json::to_writer(o, &v);
    }))
}

/// venue programs by name (exec.jsonl `venues`; the same list as the engine's rival detection)
static VENUES: LazyLock<rustc_hash::FxHashMap<Pk, &'static str>> = LazyLock::new(|| crate::engine::amm_programs().into_iter().collect());

const B64: base64::engine::GeneralPurpose = base64::engine::general_purpose::STANDARD;

fn pk_of(b: &[u8]) -> Option<Pk> { b.try_into().ok() }
fn b58v(b: &[u8]) -> String { bs58::encode(b).into_string() }

/// The compute-budget parameters a legacy / v0 transaction sets: (unit limit, unit price in micro-lamports, loaded
/// accounts data size limit), from its ComputeBudget instructions
pub fn compute_budget(keys: &[Pk], ixs: &[(u32, &[u8])]) -> (Option<u32>, Option<u64>, Option<u32>) {
    let (mut limit, mut price, mut data) = (None, None, None);
    for (p, d) in ixs {
        if keys.get(*p as usize) != Some(&COMPUTE_BUDGET) || d.is_empty() { continue; }
        match d[0] {
            2 if d.len() >= 5 => limit = Some(u32::from_le_bytes(d[1..5].try_into().unwrap())),
            3 if d.len() >= 9 => price = Some(u64::from_le_bytes(d[1..9].try_into().unwrap())),
            4 if d.len() >= 5 => data = Some(u32::from_le_bytes(d[1..5].try_into().unwrap())),
            _ => {}
        }
    }
    (limit, price, data)
}

/// The failing top-level instruction of an `InstructionError` (bincode TransactionError variant 8)
pub fn err_ix(b: &[u8]) -> Option<u32> {
    (b.get(..4)? == 8u32.to_le_bytes()).then(|| b.get(4).map(|x| *x as u32)).flatten()
}

/// The exec.jsonl v2 record (§4.14) of one executed transaction. `idx`: its block index when known; `roles`: the
/// watched accounts (`watched`, `pools`; None: empty lists)
#[allow(clippy::too_many_arguments)]
pub fn exec_json(sig: &[u8], slot: u64, idx: Option<u64>, t: u64, src: &str, found_by: &[&str], tx: &PbTransaction, meta: &PbMeta, roles: Option<&Roles>) -> Value {
    let no_msg = crate::feeds::grpc::PbMessage::default();
    let msg = tx.message.as_ref().unwrap_or(&no_msg);
    let h = msg.header.clone().unwrap_or_default();
    let stat: Vec<Pk> = msg.account_keys.iter().filter_map(|k| pk_of(k)).collect();
    let mut keys = stat.clone();
    let lw: Vec<Pk> = meta.loaded_writable_addresses.iter().filter_map(|k| pk_of(k)).collect();
    let lr: Vec<Pk> = meta.loaded_readonly_addresses.iter().filter_map(|k| pk_of(k)).collect();
    keys.extend(&lw);
    keys.extend(&lr);
    let n_static = stat.len();
    let nreq = h.num_required_signatures as usize;
    // Solana's writability: signed writable, unsigned writable, then the loaded writable addresses
    let writable = |i: usize| -> bool {
        if i >= n_static { return i < n_static + lw.len(); }
        if i < nreq { i < nreq.saturating_sub(h.num_readonly_signed_accounts as usize) } else { i < n_static.saturating_sub(h.num_readonly_unsigned_accounts as usize) }
    };
    let ok = meta.err.is_none();
    let err = meta.err.as_ref().map(|e| super::tx_error(&e.err));
    let why = if err.is_some() {
        meta.log_messages.iter().rev().find(|l| l.contains("Error") || l.contains("error") || l.contains("failed")).map(|l| l.chars().take(160).collect::<String>())
    } else { None };
    let signer = keys.first().map(b58).unwrap_or_default();
    // compute budget: ComputeBudget instructions (legacy, v0), or the v1 transaction's inline config
    let top: Vec<(u32, &[u8])> = msg.instructions.iter().map(|i| (i.program_id_index, &i.data[..])).collect();
    let (version, cu_limit, cu_price, loaded_limit, priority_fee) = match &msg.config {
        Some(c) => ("1", c.compute_unit_limit, None, c.loaded_accounts_data_size_limit, c.priority_fee.unwrap_or(0)),
        None => {
            let (l, p, d) = compute_budget(&stat, &top);
            // the default limit: 200,000 per non-ComputeBudget instruction, at most 1.4M
            let n_other = top.iter().filter(|(p, _)| stat.get(*p as usize) != Some(&COMPUTE_BUDGET)).count() as u64;
            let lim = l.map(|x| x as u64).unwrap_or((200_000 * n_other).min(1_400_000));
            let fee = p.map_or(0, |price| (lim as u128 * price as u128).div_ceil(1_000_000) as u64);
            (if msg.versioned { "0" } else { "legacy" }, l, p, d, fee)
        }
    };
    // a durable nonce: instruction 0 is the system program's AdvanceNonceAccount (4)
    let nonce = msg.instructions.first().filter(|i| stat.get(i.program_id_index as usize) == Some(&[0u8; 32]) && i.data.get(..4) == Some(&[4, 0, 0, 0][..]))
        .and_then(|i| i.accounts.first()).and_then(|a| keys.get(*a as usize)).map(b58);
    let ixs: Vec<Value> = msg.instructions.iter().map(|i| json!({ "p": i.program_id_index, "a": i.accounts, "d": B64.encode(&i.data) })).collect();
    let inner = (!meta.inner_instructions_none).then(|| meta.inner_instructions.iter().map(|g| json!({ "ix": g.index,
        "list": g.instructions.iter().map(|x| json!({ "p": x.program_id_index, "a": x.accounts, "d": B64.encode(&x.data), "h": x.stack_height })).collect::<Vec<_>>() }))
        .collect::<Vec<_>>());
    let logs = (!meta.log_messages_none).then_some(&meta.log_messages);
    let return_data = meta.return_data.as_ref().filter(|_| !meta.return_data_none).map(|r| json!({ "program": b58v(&r.program_id), "data": B64.encode(&r.data) }));
    let tok = |list: &[crate::feeds::grpc::PbTokenBalance]| -> Vec<Value> { list.iter().map(|b| {
        let u = b.ui_token_amount.clone().unwrap_or_default();
        json!({ "i": b.account_index, "mint": b.mint, "owner": b.owner, "prog": Some(&b.program_id).filter(|p| !p.is_empty()), "amount": u.amount, "dec": u.decimals })
    }).collect() };
    let signer_sol = match (meta.pre_balances.first(), meta.post_balances.first()) { (Some(a), Some(b)) => Some(*b as i64 - *a as i64), _ => None };
    // the signer's token changes by mint (accounts it owns; one absent on a side counts as 0), nonzero only
    let mut st: std::collections::BTreeMap<&str, i128> = Default::default();
    for (side, list) in [(-1i128, &meta.pre_token_balances), (1, &meta.post_token_balances)] {
        for b in list.iter().filter(|b| b.owner == signer) {
            *st.entry(b.mint.as_str()).or_default() += side * b.ui_token_amount.as_ref().and_then(|u| u.amount.parse::<i128>().ok()).unwrap_or(0);
        }
    }
    let signer_tok: Map<String, Value> = st.into_iter().filter(|(_, v)| *v != 0).map(|(k, v)| (k.to_string(), json!(v.to_string()))).collect();
    // watched accounts it wrote (a failed transaction writes only its fee payer), the watched pools it touched, venues
    let (mut watched, mut pools) = (Vec::new(), Vec::new());
    if let Some(r) = roles {
        for (i, k) in keys.iter().enumerate() {
            let Some(x) = r.get(k) else { continue };
            if x.role == role::POOL && !pools.contains(&b58(k)) { pools.push(b58(k)); }
            if writable(i) && (ok || i == 0) {
                watched.push(json!({ "acct": b58(k), "role": role::name(x.role), "pool": (x.pool_index != super::accounts::NO_POOL).then_some(x.pool_index) }));
            }
        }
    }
    let mut venues: Vec<&str> = Vec::new();
    let progs = msg.instructions.iter().map(|i| i.program_id_index)
        .chain(meta.inner_instructions.iter().flat_map(|g| g.instructions.iter().map(|x| x.program_id_index)));
    for p in progs { if let Some(n) = keys.get(p as usize).and_then(|k| VENUES.get(k)) { if !venues.contains(n) { venues.push(n); } } }
    let mut m = Map::new();
    let mut put = |k: &str, v: Value| { m.insert(k.to_string(), v); };
    put("sig", json!(b58v(sig))); put("slot", json!(slot)); put("idx", json!(idx)); put("src", json!(src)); put("found_by", json!(found_by)); put("t", json!(t));
    put("ok", json!(ok)); put("err", json!(err)); put("err_ix", json!(meta.err.as_ref().and_then(|e| err_ix(&e.err)))); put("why", json!(why));
    put("fee", json!(meta.fee)); put("cu", json!(meta.compute_units_consumed)); put("cost_units", json!(meta.cost_units));
    put("cu_limit", json!(cu_limit)); put("cu_price_micro", json!(cu_price)); put("priority_fee", json!(priority_fee)); put("loaded_data_limit", json!(loaded_limit));
    put("version", json!(version)); put("signer", json!(signer)); put("signers", json!(keys.iter().take(nreq).map(b58).collect::<Vec<_>>()));
    put("recent_blockhash", json!(b58v(&msg.recent_blockhash))); put("nonce", json!(nonce));
    put("keys", json!(keys.iter().map(b58).collect::<Vec<_>>())); put("n_static", json!(n_static));
    put("alts", json!(msg.address_table_lookups.iter().map(|l| json!({ "table": b58v(&l.account_key), "w": l.writable_indexes, "r": l.readonly_indexes })).collect::<Vec<_>>()));
    put("ixs", json!(ixs)); put("inner", json!(inner)); put("logs", json!(logs)); put("return_data", json!(return_data));
    put("pre", json!(meta.pre_balances)); put("post", json!(meta.post_balances));
    put("pre_tok", json!(tok(&meta.pre_token_balances))); put("post_tok", json!(tok(&meta.post_token_balances)));
    put("signer_sol", json!(signer_sol)); put("signer_tok", Value::Object(signer_tok));
    put("watched", json!(watched)); put("venues", json!(venues)); put("pools", json!(pools));
    // derived fields of later WPs (WP-08: transfer classification, bundle membership, arb_like; WP-05: ours)
    for k in ["transfers", "tip_total", "tip_senders", "jito_tipped", "bundle", "arb_like", "ours", "prog_events"] { put(k, Value::Null); }
    Value::Object(m)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::feeds::grpc::{PbHeader, PbIx, PbMessage, PbTxConfig, PbTxError};
    use crate::rec::accounts::RoleOf;

    /// review WP-03 #10: one exec.jsonl line per (signature, slot): a re-delivery is dropped, a second fork is kept,
    /// and the set stays bounded
    #[test]
    fn recent_keeps_one_line_per_signature_and_slot() {
        let mut r = Recent::default();
        let (a, b) = ([1u8; 64], [2u8; 64]);
        assert!(r.first(&a, 10) && r.first(&b, 10));
        assert!(!r.first(&a, 10), "a re-delivery (reconnect)");
        assert!(r.first(&a, 11), "the same transaction on another fork");
        assert_eq!(r.dups, 1);
        for i in 0..(Recent::MAX as u64 + 10) { r.first(&i.to_le_bytes(), 1); }
        assert!(r.set.len() <= Recent::MAX && r.order.len() <= Recent::MAX);
        assert!(r.first(&a, 10), "forgotten past MAX");
    }

    fn k(n: u8) -> Vec<u8> { vec![n; 32] }
    /// keys: 0 signer (writable), 1 a watched pool (writable), 2 system program, 3 ComputeBudget, 4 a program (the last
    /// three readonly); loaded: 5 writable (a watched vault), 6 readonly (a watched vault: not written)
    fn tx(ixs: Vec<PbIx>, config: Option<PbTxConfig>) -> PbTransaction {
        PbTransaction { signatures: vec![vec![9; 64]], message: Some(PbMessage {
            header: Some(PbHeader { num_required_signatures: 1, num_readonly_signed_accounts: 0, num_readonly_unsigned_accounts: 3 }),
            account_keys: vec![k(1), k(3), vec![0; 32], COMPUTE_BUDGET.to_vec(), k(4)], recent_blockhash: vec![7; 32], instructions: ixs, versioned: true,
            address_table_lookups: vec![], config }) }
    }
    fn meta(err: Option<Vec<u8>>, logs: &[&str]) -> PbMeta {
        PbMeta { err: err.map(|e| PbTxError { err: e }), fee: 5_000, pre_balances: vec![10, 0], post_balances: vec![5, 0], log_messages: logs.iter().map(|s| s.to_string()).collect(),
            loaded_writable_addresses: vec![k(5)], loaded_readonly_addresses: vec![k(6)], ..Default::default() }
    }
    fn roles() -> Roles {
        let r = |role: u8| RoleOf { role, pool_index: 0 };
        Roles::new([([3u8; 32], r(role::POOL)), ([5u8; 32], r(role::VAULT)), ([6u8; 32], r(role::VAULT))])
    }

    /// review WP-03 #11: exec_json's branches the stream fixture does not reach
    #[test]
    fn exec_json_branches() {
        // a failed v0 transaction: no unit-limit instruction (the default limit: 200,000 per other instruction), a price,
        // a durable nonce, InstructionError in instruction 3
        let price = { let mut d = vec![3u8]; d.extend(1_000u64.to_le_bytes()); d };
        let ixs = vec![PbIx { program_id_index: 2, accounts: vec![1, 0], data: vec![4, 0, 0, 0] }, PbIx { program_id_index: 3, accounts: vec![], data: price },
            PbIx { program_id_index: 4, accounts: vec![1, 5, 6], data: vec![1] }, PbIx { program_id_index: 4, accounts: vec![1], data: vec![2] }];
        let mut e = 8u32.to_le_bytes().to_vec();
        e.push(3);
        e.extend(25u32.to_le_bytes());
        e.extend(6_001u32.to_le_bytes());
        let m = meta(Some(e), &["Program log: Instruction: Swap", "Program log: Error: slippage exceeded", "Program x failed: custom program error: 0x1771"]);
        let r = roles();
        let v = exec_json(&[9; 64], 5, None, 1, "grpc-tx", &["tx_stream"], &tx(ixs, None), &m, Some(&r));
        assert_eq!((v["ok"].as_bool(), v["err"].as_str(), v["err_ix"].as_u64()), (Some(false), Some("ix3:custom:0x1771"), Some(3)));
        assert_eq!(v["why"].as_str(), Some("Program x failed: custom program error: 0x1771"), "the last error-looking log line");
        assert_eq!((v["cu_limit"].clone(), v["cu_price_micro"].as_u64(), v["priority_fee"].as_u64()), (Value::Null, Some(1_000), Some(600)),
            "3 non-budget instructions x 200,000 units at 1,000 micro-lamports");
        assert_eq!(v["nonce"].as_str(), Some(b58(&[3u8; 32]).as_str()));
        assert_eq!(v["version"].as_str(), Some("0"));
        // a failed transaction writes only its fee payer: no watched account written, the pool still listed as touched
        assert_eq!((v["watched"].clone(), v["pools"].clone()), (json!([]), json!([b58(&[3u8; 32])])));
        // the same transaction landed: the writable pool and loaded-writable vault are written, the loaded-readonly one not
        let v = exec_json(&[9; 64], 5, Some(2), 1, "grpc-tx", &["tx_stream"], &tx(vec![PbIx { program_id_index: 4, accounts: vec![1, 5, 6], data: vec![1] }], None),
            &meta(None, &["Program log: ok"]), Some(&r));
        let w: Vec<&str> = v["watched"].as_array().unwrap().iter().map(|x| x["acct"].as_str().unwrap()).collect();
        assert_eq!(w, vec![b58(&[3u8; 32]), b58(&[5u8; 32])]);
        assert!(v["why"].is_null() && v["err_ix"].is_null() && v["nonce"].is_null());
        assert_eq!((v["cu_limit"].clone(), v["priority_fee"].as_u64()), (Value::Null, Some(0)), "no price: no priority fee");
        // a v1 transaction: the inline config, not ComputeBudget instructions
        let cfg = PbTxConfig { priority_fee: Some(7_777), compute_unit_limit: Some(300_000), loaded_accounts_data_size_limit: Some(65_536), ..Default::default() };
        let v = exec_json(&[9; 64], 5, None, 1, "grpc-tx", &[], &tx(vec![], Some(cfg)), &meta(None, &[]), None);
        assert_eq!((v["version"].as_str(), v["cu_limit"].as_u64(), v["cu_price_micro"].clone(), v["priority_fee"].as_u64(), v["loaded_data_limit"].as_u64()),
            (Some("1"), Some(300_000), Value::Null, Some(7_777), Some(65_536)));
        // err_ix of instruction 0, and not an InstructionError
        assert_eq!((err_ix(&[8, 0, 0, 0, 0, 1, 0, 0, 0]), err_ix(&[1, 0, 0, 0])), (Some(0), None));
    }
}

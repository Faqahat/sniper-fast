//! gRPC feeds with hand-written prost messages (only the fields we read; prost skips the rest), so no protoc is
//! needed. Field numbers are from yellowstone-grpc-proto (geyser.proto, solana-storage.proto) and Jito's shredstream;
//! they are pinned by tests against the vendored proto text in `testdata/proto/` (PLAN WP-03 item 4).
//!   jito-entries        /shredstream.ShredstreamProxy/SubscribeEntries  server stream of {slot, entries}
//!   yellowstone-deshred /geyser.Geyser/SubscribeDeshred                 bidi; unexecuted transactions
//!   yellowstone-tx      /geyser.Geyser/Subscribe (transactions)         bidi; executed, processed commitment
//!   accounts            /geyser.Geyser/Subscribe (accounts + slots)     bidi; pool state for the engine
use crate::config::{FeedKind, Feed};
use crate::feeds::clock::now_ns;
use crate::feeds::{FeedCounters, RawTx};
use crate::tx::{self, Ix, Lookup, Pk, Tx};
use std::sync::Arc;
use anyhow::{bail, Context, Result};
use std::collections::HashMap;
use std::time::Duration;
use tonic::codec::ProstCodec;
use tonic::transport::{Channel, ClientTlsConfig, Endpoint};

// ---------- Jito ShredStream proxy
#[derive(Clone, PartialEq, prost::Message)]
pub struct SubscribeEntriesRequest {}
#[derive(Clone, PartialEq, prost::Message)]
pub struct JitoEntry {
    #[prost(uint64, tag = "1")] pub slot: u64,
    #[prost(bytes = "vec", tag = "2")] pub entries: Vec<u8>,
}

// ---------- solana-storage.proto (ConfirmedBlock)
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbTransaction {
    #[prost(bytes = "vec", repeated, tag = "1")] pub signatures: Vec<Vec<u8>>,
    #[prost(message, optional, tag = "2")] pub message: Option<PbMessage>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbMessage {
    #[prost(message, optional, tag = "1")] pub header: Option<PbHeader>,
    #[prost(bytes = "vec", repeated, tag = "2")] pub account_keys: Vec<Vec<u8>>,
    #[prost(bytes = "vec", tag = "3")] pub recent_blockhash: Vec<u8>,
    #[prost(message, repeated, tag = "4")] pub instructions: Vec<PbIx>,
    #[prost(bool, tag = "5")] pub versioned: bool,
    #[prost(message, repeated, tag = "6")] pub address_table_lookups: Vec<PbLookup>,
    /// v1 transactions (SIMD-0385) only: the inline budget config
    #[prost(message, optional, tag = "7")] pub config: Option<PbTxConfig>,
}
/// `TransactionConfig` of a v1 transaction: what ComputeBudget instructions say in legacy / v0
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbTxConfig {
    #[prost(uint64, optional, tag = "1")] pub priority_fee: Option<u64>,
    #[prost(uint32, optional, tag = "2")] pub compute_unit_limit: Option<u32>,
    #[prost(uint32, optional, tag = "3")] pub loaded_accounts_data_size_limit: Option<u32>,
    #[prost(uint32, optional, tag = "4")] pub heap_size: Option<u32>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbHeader {
    #[prost(uint32, tag = "1")] pub num_required_signatures: u32,
    #[prost(uint32, tag = "2")] pub num_readonly_signed_accounts: u32,
    #[prost(uint32, tag = "3")] pub num_readonly_unsigned_accounts: u32,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbIx {
    #[prost(uint32, tag = "1")] pub program_id_index: u32,
    #[prost(bytes = "vec", tag = "2")] pub accounts: Vec<u8>,
    #[prost(bytes = "vec", tag = "3")] pub data: Vec<u8>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbLookup {
    #[prost(bytes = "vec", tag = "1")] pub account_key: Vec<u8>,
    #[prost(bytes = "vec", tag = "2")] pub writable_indexes: Vec<u8>,
    #[prost(bytes = "vec", tag = "3")] pub readonly_indexes: Vec<u8>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbTxError { #[prost(bytes = "vec", tag = "1")] pub err: Vec<u8> }
/// `TransactionStatusMeta` (WP-03 item 4: the full meta for exec.jsonl v2)
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbMeta {
    #[prost(message, optional, tag = "1")] pub err: Option<PbTxError>,
    #[prost(uint64, tag = "2")] pub fee: u64,
    #[prost(uint64, repeated, tag = "3")] pub pre_balances: Vec<u64>,
    #[prost(uint64, repeated, tag = "4")] pub post_balances: Vec<u64>,
    #[prost(message, repeated, tag = "5")] pub inner_instructions: Vec<PbInnerIxs>,
    #[prost(string, repeated, tag = "6")] pub log_messages: Vec<String>,
    #[prost(message, repeated, tag = "7")] pub pre_token_balances: Vec<PbTokenBalance>,
    #[prost(message, repeated, tag = "8")] pub post_token_balances: Vec<PbTokenBalance>,
    #[prost(bool, tag = "10")] pub inner_instructions_none: bool,
    #[prost(bool, tag = "11")] pub log_messages_none: bool,
    #[prost(bytes = "vec", repeated, tag = "12")] pub loaded_writable_addresses: Vec<Vec<u8>>,
    #[prost(bytes = "vec", repeated, tag = "13")] pub loaded_readonly_addresses: Vec<Vec<u8>>,
    #[prost(message, optional, tag = "14")] pub return_data: Option<PbReturnData>,
    #[prost(bool, tag = "15")] pub return_data_none: bool,
    #[prost(uint64, optional, tag = "16")] pub compute_units_consumed: Option<u64>,
    #[prost(uint64, optional, tag = "17")] pub cost_units: Option<u64>,
}
/// the inner instructions of one top-level instruction (`InnerInstructions`)
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbInnerIxs {
    #[prost(uint32, tag = "1")] pub index: u32,
    #[prost(message, repeated, tag = "2")] pub instructions: Vec<PbInnerIx>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbInnerIx {
    #[prost(uint32, tag = "1")] pub program_id_index: u32,
    #[prost(bytes = "vec", tag = "2")] pub accounts: Vec<u8>,
    #[prost(bytes = "vec", tag = "3")] pub data: Vec<u8>,
    #[prost(uint32, optional, tag = "4")] pub stack_height: Option<u32>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbReturnData {
    #[prost(bytes = "vec", tag = "1")] pub program_id: Vec<u8>,
    #[prost(bytes = "vec", tag = "2")] pub data: Vec<u8>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbTokenBalance {
    #[prost(uint32, tag = "1")] pub account_index: u32,
    #[prost(string, tag = "2")] pub mint: String,
    #[prost(message, optional, tag = "3")] pub ui_token_amount: Option<PbUiAmount>,
    #[prost(string, tag = "4")] pub owner: String,
    #[prost(string, tag = "5")] pub program_id: String,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbUiAmount {
    #[prost(uint32, tag = "2")] pub decimals: u32,
    #[prost(string, tag = "3")] pub amount: String,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbUnixTimestamp { #[prost(int64, tag = "1")] pub timestamp: i64 }
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbBlockHeight { #[prost(uint64, tag = "1")] pub block_height: u64 }
/// google.protobuf.Timestamp (`SubscribeUpdate.created_at`)
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbTimestamp {
    #[prost(int64, tag = "1")] pub seconds: i64,
    #[prost(int32, tag = "2")] pub nanos: i32,
}
impl PbTimestamp {
    /// nanoseconds since the epoch (None: before it)
    pub fn ns(&self) -> Option<u64> { u64::try_from(self.seconds).ok()?.checked_mul(1_000_000_000)?.checked_add(u64::try_from(self.nanos).ok()?) }
}
/// an empty message (pings)
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbEmpty {}

// ---------- Yellowstone common
#[derive(Clone, PartialEq, prost::Message)]
pub struct Ping { #[prost(int32, tag = "1")] pub id: i32 }
#[derive(Clone, PartialEq, prost::Message)]
pub struct FilterSlots {
    #[prost(bool, optional, tag = "1")] pub filter_by_commitment: Option<bool>,
    #[prost(bool, optional, tag = "2")] pub interslot_updates: Option<bool>,
}

// ---------- Yellowstone deshred
#[derive(Clone, PartialEq, prost::Message)]
pub struct FilterDeshredTx {
    #[prost(bool, optional, tag = "1")] pub vote: Option<bool>,
    #[prost(string, repeated, tag = "2")] pub account_include: Vec<String>,
    #[prost(string, repeated, tag = "3")] pub account_exclude: Vec<String>,
    #[prost(string, repeated, tag = "4")] pub account_required: Vec<String>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct SubscribeDeshredRequest {
    #[prost(map = "string, message", tag = "1")] pub deshred_transactions: HashMap<String, FilterDeshredTx>,
    #[prost(message, optional, tag = "2")] pub ping: Option<Ping>,
    #[prost(map = "string, message", tag = "3")] pub slots: HashMap<String, FilterSlots>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct DeshredTxInfo {
    #[prost(bytes = "vec", tag = "1")] pub signature: Vec<u8>,
    #[prost(bool, tag = "2")] pub is_vote: bool,
    #[prost(message, optional, tag = "3")] pub transaction: Option<PbTransaction>,
    #[prost(bytes = "vec", repeated, tag = "4")] pub loaded_writable_addresses: Vec<Vec<u8>>,
    #[prost(bytes = "vec", repeated, tag = "5")] pub loaded_readonly_addresses: Vec<Vec<u8>>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct DeshredTx {
    #[prost(message, optional, tag = "1")] pub transaction: Option<DeshredTxInfo>,
    #[prost(uint64, tag = "2")] pub slot: u64,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct SubscribeUpdateDeshred {
    #[prost(message, optional, tag = "2")] pub deshred_transaction: Option<DeshredTx>,
    #[prost(message, optional, tag = "3")] pub ping: Option<PbEmpty>,
    #[prost(message, optional, tag = "5")] pub created_at: Option<PbTimestamp>,
    #[prost(message, optional, tag = "6")] pub slot: Option<UpdateSlot>,
}

// ---------- Yellowstone subscribe (transactions, accounts, slots)
#[derive(Clone, PartialEq, prost::Message)]
pub struct FilterTx {
    #[prost(bool, optional, tag = "1")] pub vote: Option<bool>,
    #[prost(bool, optional, tag = "2")] pub failed: Option<bool>,
    #[prost(string, repeated, tag = "3")] pub account_include: Vec<String>,
    #[prost(string, repeated, tag = "4")] pub account_exclude: Vec<String>,
    #[prost(string, repeated, tag = "6")] pub account_required: Vec<String>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct FilterAccounts {
    #[prost(string, repeated, tag = "2")] pub account: Vec<String>,
    #[prost(string, repeated, tag = "3")] pub owner: Vec<String>,
}
/// `SubscribeRequestFilterBlocks` (the probe's `blocks_account_include`; OD-1)
#[derive(Clone, PartialEq, prost::Message)]
pub struct FilterBlocks {
    #[prost(string, repeated, tag = "1")] pub account_include: Vec<String>,
    #[prost(bool, optional, tag = "2")] pub include_transactions: Option<bool>,
    #[prost(bool, optional, tag = "3")] pub include_accounts: Option<bool>,
    #[prost(bool, optional, tag = "4")] pub include_entries: Option<bool>,
}
/// `SubscribeRequestFilterBlocksMeta` (no fields)
#[derive(Clone, PartialEq, prost::Message)]
pub struct FilterBlocksMeta {}
#[derive(Clone, PartialEq, prost::Message)]
pub struct SubscribeRequest {
    #[prost(map = "string, message", tag = "1")] pub accounts: HashMap<String, FilterAccounts>,
    #[prost(map = "string, message", tag = "2")] pub slots: HashMap<String, FilterSlots>,
    #[prost(map = "string, message", tag = "3")] pub transactions: HashMap<String, FilterTx>,
    #[prost(map = "string, message", tag = "4")] pub blocks: HashMap<String, FilterBlocks>,
    #[prost(map = "string, message", tag = "5")] pub blocks_meta: HashMap<String, FilterBlocksMeta>,
    #[prost(int32, optional, tag = "6")] pub commitment: Option<i32>,
    #[prost(message, optional, tag = "9")] pub ping: Option<Ping>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct TxInfo {
    #[prost(bytes = "vec", tag = "1")] pub signature: Vec<u8>,
    #[prost(bool, tag = "2")] pub is_vote: bool,
    #[prost(message, optional, tag = "3")] pub transaction: Option<PbTransaction>,
    #[prost(message, optional, tag = "4")] pub meta: Option<PbMeta>,
    #[prost(uint64, tag = "5")] pub index: u64,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct UpdateTx {
    #[prost(message, optional, tag = "1")] pub transaction: Option<TxInfo>,
    #[prost(uint64, tag = "2")] pub slot: u64,
    /// the bank the transaction executed in (Alpenglow-era proto; 0: not sent; review WP-03 #12)
    #[prost(uint64, tag = "3")] pub bank_id: u64,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct AccountInfo {
    #[prost(bytes = "vec", tag = "1")] pub pubkey: Vec<u8>,
    #[prost(uint64, tag = "2")] pub lamports: u64,
    #[prost(bytes = "vec", tag = "3")] pub owner: Vec<u8>,
    #[prost(bytes = "vec", tag = "6")] pub data: Vec<u8>,
    #[prost(uint64, tag = "7")] pub write_version: u64,
    #[prost(bytes = "vec", optional, tag = "8")] pub txn_signature: Option<Vec<u8>>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct UpdateAccount {
    #[prost(message, optional, tag = "1")] pub account: Option<AccountInfo>,
    #[prost(uint64, tag = "2")] pub slot: u64,
    #[prost(bool, tag = "3")] pub is_startup: bool,
    /// the bank the update was written in (review WP-03 #12; recorded in accounts.bin since WP-04, flags bit 2)
    #[prost(uint64, optional, tag = "4")] pub bank_id: Option<u64>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct UpdateSlot {
    #[prost(uint64, tag = "1")] pub slot: u64,
    #[prost(uint64, optional, tag = "2")] pub parent: Option<u64>,
    #[prost(int32, tag = "3")] pub status: i32,
    #[prost(string, optional, tag = "4")] pub dead_error: Option<String>,
    /// the slot's bank (a slot's bank can be replaced: WP-04's fork tree joins on it; review WP-03 #12)
    #[prost(uint64, optional, tag = "5")] pub bank_id: Option<u64>,
}
/// `SubscribeUpdateBlockMeta` (WP-03 item 6)
#[derive(Clone, PartialEq, prost::Message)]
pub struct UpdateBlockMeta {
    #[prost(uint64, tag = "1")] pub slot: u64,
    #[prost(string, tag = "2")] pub blockhash: String,
    #[prost(message, optional, tag = "4")] pub block_time: Option<PbUnixTimestamp>,
    #[prost(message, optional, tag = "5")] pub block_height: Option<PbBlockHeight>,
    #[prost(uint64, tag = "6")] pub parent_slot: u64,
    #[prost(string, tag = "7")] pub parent_blockhash: String,
    #[prost(uint64, tag = "8")] pub executed_transaction_count: u64,
    #[prost(uint64, tag = "9")] pub entries_count: u64,
    /// 0: not sent (review WP-03 #12)
    #[prost(uint64, tag = "10")] pub bank_id: u64,
}
/// `SubscribeUpdateBlock`: only its slot (the probe counts blocks)
#[derive(Clone, PartialEq, prost::Message)]
pub struct UpdateBlock { #[prost(uint64, tag = "1")] pub slot: u64 }
#[derive(Clone, PartialEq, prost::Message)]
pub struct SubscribeUpdate {
    #[prost(message, optional, tag = "2")] pub account: Option<UpdateAccount>,
    #[prost(message, optional, tag = "3")] pub slot: Option<UpdateSlot>,
    #[prost(message, optional, tag = "4")] pub transaction: Option<UpdateTx>,
    #[prost(message, optional, tag = "5")] pub block: Option<UpdateBlock>,
    #[prost(message, optional, tag = "6")] pub ping: Option<PbEmpty>,
    #[prost(message, optional, tag = "7")] pub block_meta: Option<UpdateBlockMeta>,
    #[prost(message, optional, tag = "9")] pub pong: Option<PbEmpty>,
    /// when the provider sent it (provider lag = receive time - this; feedhealth.jsonl `provider_lag_ms`)
    #[prost(message, optional, tag = "11")] pub created_at: Option<PbTimestamp>,
}

/// One received item.
pub enum Item {
    /// a batch of serialized entries (Jito ShredStream interface)
    Entries { slot: u64, bytes: Vec<u8>, t: u64 },
    /// one transaction; `executed` is Some(succeeded) for executed (processed) feeds, None for unexecuted ones; `raw`:
    /// its protobuf transaction (the input journal's TX_FIRST bytes, WP-03)
    Tx { slot: u64, tx: Tx, t: u64, executed: Option<bool>, raw: RawTx, exec: Option<Arc<crate::feeds::ExecInfo>> },
    /// one account update (pool state and the other watched accounts), with its bank when the provider sends it
    Account { slot: u64, pubkey: Pk, lamports: u64, owner: Pk, data: Vec<u8>, write_version: u64, t: u64, txn: Option<[u8; 64]>, is_startup: bool, bank_id: Option<u64> },
    /// a slot status update (0 processed, 1 confirmed, 2 finalized, 3 first-shred, 4 completed, 5 created-bank, 6
    /// dead), with its parent when the provider sends it
    Slot { slot: u64, status: i32, t: u64, parent: Option<u64>, dead_error: Option<String>, bank_id: Option<u64> },
    /// a block's metadata (`blocks_meta`, WP-03 item 6)
    BlockMeta(BlockMeta),
}

/// One block's metadata (`SubscribeUpdateBlockMeta`; blocks.jsonl, the engine's `Event::BlockMeta`)
#[derive(Clone, Debug, PartialEq)]
pub struct BlockMeta {
    pub slot: u64,
    pub blockhash: [u8; 32],
    pub parent_slot: u64,
    pub parent_blockhash: [u8; 32],
    pub block_height: Option<u64>,
    pub block_time: Option<i64>,
    pub executed_transaction_count: u64,
    pub entries_count: u64,
    pub t: u64,
    /// blocks.jsonl only (not journaled)
    pub bank_id: Option<u64>,
}

fn hash32(s: &str) -> Option<[u8; 32]> { bs58::decode(s).into_vec().ok()?.try_into().ok() }

/// A state-stream update as an item (account, slot or block meta); None for anything else (pings, pongs). `t`: when
/// it was received
pub fn state_item(m: SubscribeUpdate, t: u64) -> Option<Item> {
    if let Some(a) = m.account {
        let info = a.account?;
        let (pubkey, owner) = (to_pk(&info.pubkey)?, to_pk(&info.owner)?);
        let txn = info.txn_signature.as_deref().and_then(|b| <[u8; 64]>::try_from(b).ok());
        return Some(Item::Account { slot: a.slot, pubkey, lamports: info.lamports, owner, data: info.data, write_version: info.write_version, t, txn,
            is_startup: a.is_startup, bank_id: a.bank_id.filter(|b| *b != 0) });
    }
    if let Some(s) = m.slot { return Some(Item::Slot { slot: s.slot, status: s.status, t, parent: s.parent, dead_error: s.dead_error, bank_id: s.bank_id }); }
    if let Some(b) = m.block_meta {
        return Some(Item::BlockMeta(BlockMeta { slot: b.slot, blockhash: hash32(&b.blockhash)?, parent_slot: b.parent_slot,
            parent_blockhash: hash32(&b.parent_blockhash).unwrap_or([0; 32]), block_height: b.block_height.map(|h| h.block_height),
            block_time: b.block_time.map(|x| x.timestamp), executed_transaction_count: b.executed_transaction_count, entries_count: b.entries_count, t,
            bank_id: (b.bank_id != 0).then_some(b.bank_id) }));
    }
    None
}

/// The provider's own timestamp of a message: its lag behind us goes to the feed's `provider_lag_ms` (feedhealth.jsonl)
fn note_lag(c: &FeedCounters, created: Option<&PbTimestamp>, t: u64) {
    if let Some(ns) = created.and_then(|c| c.ns()) {
        c.provider_lag(t, ns);
        // ARBX_LOG_LAG=1: print provider-send -> our-receive latency per message (= network + our consumption).
        // Small => our side is fast and the ~200ms is upstream (provider gets shreds late); large => our side is slow.
        if std::env::var("ARBX_LOG_LAG").is_ok() { eprintln!("PROVLAG_us {}", t.saturating_sub(ns) / 1_000); }
    }
}

/// One executed transaction from a transaction stream: its exec.jsonl v2 record (src/rec/exec.rs, built and written on
/// the recorder's chain writer; once per (signature, slot): `recent`) and the item to forward. `roles`: the watched
/// accounts (exec `watched`, `pools`)
pub fn tx_stream_item(u: UpdateTx, t: u64, rec: &crate::rec::Rec, roles: Option<&Arc<crate::rec::accounts::Roles>>, recent: &mut crate::rec::exec::Recent) -> Option<Item> {
    let mut info = u.transaction?;
    let pb = Arc::new(info.transaction.take()?);
    let meta = info.meta.take();
    let (ok, lw, lr) = match &meta {
        Some(meta) => (meta.err.is_none(), meta.loaded_writable_addresses.clone(), meta.loaded_readonly_addresses.clone()),
        None => (true, vec![], vec![]),
    };
    let tx = tx_from_pb(&info.signature, info.is_vote, &pb, &lw, &lr);
    // dip engine: the pump events of this executed tx, decoded from its logs exactly as the collector does
    let exec = meta.as_ref().and_then(|m| {
        let trades = crate::dip::trade_events(&m.log_messages);
        let creates = crate::dip::create_events(&m.log_messages);
        if trades.is_empty() && creates.is_empty() { return None; }
        let mayhem = !creates.is_empty() && crate::dip::logs_have_mayhem(&m.log_messages);
        Some(Arc::new(crate::feeds::ExecInfo { index: info.index, fee: m.fee, ok, trades, creates, mayhem }))
    });
    if let Some(meta) = meta.filter(|_| recent.first(&info.signature, u.slot)) {
        let sig: Option<[u8; 64]> = info.signature.as_slice().try_into().ok();
        // FT-000 (S1-5): in full only when it touches a watched account; of the rest (72% of FT-000's exec.jsonl bytes:
        // PumpSwap transactions on pools we do not follow) 1 in `[record] exec_unwatched_sample`, by the signature. A
        // record left out is not "recorded": nothing needs one (the chain fetch backfills only watched transactions),
        // and its idx is still checked against the slot index
        let sample = if crate::rec::exec::touches_watched(roles.map(|r| r.as_ref()), &pb, Some(&meta)) { Ok(None) }
            else { rec.sample_exec_unwatched(&info.signature).map(Some).ok_or(()) };
        let recorded = match sample {
            Ok(sample) => crate::rec::exec::emit_grpc(rec, roles, crate::rec::exec::GrpcTx { sig: info.signature, slot: u.slot, idx: info.index, t, tx: pb.clone(), meta,
                bank_id: (u.bank_id != 0).then_some(u.bank_id), sample }),
            Err(()) => false,
        };
        // WP-03b tap: this signature has its exec.jsonl record when the recorder took it (else the backfill fetches it:
        // review WP-03b #13), and its idx is checked against the slot index
        if let Some(sig) = sig { crate::chainfetch::note_stream_tx(&sig, u.slot, info.index, ok, recorded); }
    }
    Some(Item::Tx { slot: u.slot, tx: tx?, t, executed: Some(ok), raw: RawTx::Pb(pb), exec })
}

fn to_pk(b: &[u8]) -> Option<Pk> { if b.len() == 32 { let mut k = [0u8; 32]; k.copy_from_slice(b); Some(k) } else { None } }

/// Build a `Tx` from Yellowstone's protobuf transaction (plus addresses the server already loaded, if any).
pub fn tx_from_pb(sig: &[u8], is_vote: bool, t: &PbTransaction, lw: &[Vec<u8>], lr: &[Vec<u8>]) -> Option<Tx> {
    let m = t.message.as_ref()?;
    let h = m.header.as_ref()?;
    let mut out = Tx::default();
    out.sig.copy_from_slice(sig.get(..64)?);
    out.num_signers = h.num_required_signatures as u8;
    out.num_ro_signed = h.num_readonly_signed_accounts as u8;
    out.num_ro_unsigned = h.num_readonly_unsigned_accounts as u8;
    out.keys = m.account_keys.iter().map(|k| to_pk(k)).collect::<Option<_>>()?;
    out.ixs = m.instructions.iter().map(|i| Ix { program: i.program_id_index as u8, accounts: i.accounts.clone(), data: i.data.clone() }).collect();
    out.lookups = m.address_table_lookups.iter().map(|l| Some(Lookup {
        table: to_pk(&l.account_key)?, writable: l.writable_indexes.clone(), readonly: l.readonly_indexes.clone() })).collect::<Option<_>>()?;
    if !lw.is_empty() || !lr.is_empty() {
        let w: Vec<Pk> = lw.iter().map(|k| to_pk(k)).collect::<Option<_>>()?;
        let r: Vec<Pk> = lr.iter().map(|k| to_pk(k)).collect::<Option<_>>()?;
        out.loaded = Some((w, r));
    }
    let mut out = tx::finish(out)?;
    out.is_vote |= is_vote;
    Some(out)
}

pub async fn channel(url: &str) -> Result<Channel> {
    let mut ep = Endpoint::from_shared(url.to_string())?
        .tcp_nodelay(true)
        .http2_keep_alive_interval(Duration::from_secs(10))
        .keep_alive_timeout(Duration::from_secs(20))
        .keep_alive_while_idle(true)
        .initial_stream_window_size(Some(16 * 1024 * 1024))
        .initial_connection_window_size(Some(32 * 1024 * 1024))
        .connect_timeout(Duration::from_secs(10));
    if url.starts_with("https://") { ep = ep.tls_config(ClientTlsConfig::new().with_webpki_roots())?; }
    Ok(ep.connect().await.with_context(|| format!("connect {url}"))?)
}

fn with_token<T>(req: &mut tonic::Request<T>, token: Option<&str>, header: Option<&str>) -> Result<()> {
    if let Some(tok) = token {
        let key: tonic::metadata::MetadataKey<tonic::metadata::Ascii> = header.unwrap_or("x-token").parse().context("bad token header name")?;
        req.metadata_mut().insert(key, tok.parse().context("token is not a valid header value")?);
    }
    Ok(())
}

/// DET FIX (2026-10-18): a gRPC stream that stays connected but stops delivering (HTTP/2 keep-alive still answered) used
/// to hang `st.message()` forever: the feed looked "connected" and the engine went blind (6 watcher restarts in one
/// overnight paper run; the 0-fire paper->live handoff). Any message (entries, transactions, pings) resets the timer; after
/// FEED_IDLE_MS (default 15000; the entries feed sends every slot, the pump deshred filter several times a second) the
/// stream errors and the caller reconnects. 0 disables.
pub fn idle_timeout() -> Duration {
    static T: std::sync::OnceLock<Duration> = std::sync::OnceLock::new();
    *T.get_or_init(|| {
        let ms = std::env::var("FEED_IDLE_MS").ok().and_then(|v| v.parse::<u64>().ok()).unwrap_or(15_000);
        if ms == 0 { Duration::from_secs(365 * 86_400) } else { Duration::from_millis(ms) }
    })
}

/// Run a bidi Yellowstone call: send `first`, then a ping every 10 s; hand every update to `on_msg`.
async fn bidi<Req, Resp>(
    grpc: &mut tonic::client::Grpc<Channel>, path: &'static str, first: Req, ping: Req,
    token: Option<&str>, header: Option<&str>, mut on_msg: impl FnMut(Resp) -> bool,
) -> Result<()>
where Req: prost::Message + Clone + Default + Send + 'static, Resp: prost::Message + Default + Send + 'static {
    let (out_tx, out_rx) = tokio::sync::mpsc::channel::<Req>(16);
    out_tx.send(first).await.ok();
    let ping_task = tokio::spawn(async move {
        loop {
            tokio::time::sleep(Duration::from_secs(10)).await;
            if out_tx.send(ping.clone()).await.is_err() { break; }
        }
    });
    let mut req = tonic::Request::new(tokio_stream::wrappers::ReceiverStream::new(out_rx));
    with_token(&mut req, token, header)?;
    let codec: ProstCodec<Req, Resp> = ProstCodec::default();
    let res = async {
        let mut st = grpc.streaming(req, http::uri::PathAndQuery::from_static(path), codec).await?.into_inner();
        loop {
            let m = match tokio::time::timeout(idle_timeout(), st.message()).await {
                Ok(r) => r?,
                Err(_) => bail!("stalled: no message for {:?} (stale subscription) — reconnecting", idle_timeout()),
            };
            let Some(m) = m else { break };
            if !on_msg(m) { return Ok(()); }
        }
        bail!("stream ended")
    }.await;
    ping_task.abort();
    res
}

/// Connect once and stream a feed's items into `out` until the stream ends or errors. The caller reconnects. `c`: the
/// feed's counters (provider lag); `roles`: the watched accounts (exec.jsonl `watched`, `pools`); `recent`: the
/// transaction stream's (signature, slot) pairs already written to exec.jsonl, kept across reconnects
pub async fn feed_once(f: &Feed, sink: &(dyn Fn(Item) -> bool + Send + Sync), rec: &crate::rec::Rec, c: &FeedCounters,
    roles: Option<&Arc<crate::rec::accounts::Roles>>, recent: &mut crate::rec::exec::Recent) -> Result<()> {
    let url = f.url.as_deref().context("grpc feed needs url")?;
    let token = f.token()?;
    let mut grpc = tonic::client::Grpc::new(channel(url).await?).max_decoding_message_size(256 * 1024 * 1024);
    grpc.ready().await.context("service not ready")?;
    // the sink converts, filters and forwards; false means the engine is gone
    let send = |it: Item| sink(it);
    match f.kind {
        FeedKind::JitoEntries => {
            let mut req = tonic::Request::new(SubscribeEntriesRequest {});
            with_token(&mut req, token.as_deref(), f.token_header.as_deref())?;
            let codec: ProstCodec<SubscribeEntriesRequest, JitoEntry> = ProstCodec::default();
            let path = http::uri::PathAndQuery::from_static("/shredstream.ShredstreamProxy/SubscribeEntries");
            let mut st = grpc.server_streaming(req, path, codec).await?.into_inner();
            loop {
                let m = match tokio::time::timeout(idle_timeout(), st.message()).await {
                    Ok(r) => r?,
                    Err(_) => bail!("stalled: no entries for {:?} (stale subscription) — reconnecting", idle_timeout()),
                };
                let Some(m) = m else { break };
                if !send(Item::Entries { slot: m.slot, bytes: m.entries, t: now_ns() }) { return Ok(()); }
            }
            bail!("stream ended")
        }
        FeedKind::YellowstoneDeshred => {
            let filter = FilterDeshredTx { vote: Some(false), account_include: f.account_include.clone(), ..Default::default() };
            let first = SubscribeDeshredRequest { deshred_transactions: HashMap::from([("arb".to_string(), filter)]), ..Default::default() };
            let ping = SubscribeDeshredRequest { ping: Some(Ping { id: 1 }), ..Default::default() };
            bidi(&mut grpc, "/geyser.Geyser/SubscribeDeshred", first, ping, token.as_deref(), f.token_header.as_deref(),
                |m: SubscribeUpdateDeshred| {
                    let t = now_ns();
                    note_lag(c, m.created_at.as_ref(), t);
                    let Some(d) = m.deshred_transaction else { return true };
                    let Some(mut info) = d.transaction else { return true };
                    let Some(pb) = info.transaction.take().map(Arc::new) else { return true };
                    match tx_from_pb(&info.signature, info.is_vote, &pb, &info.loaded_writable_addresses, &info.loaded_readonly_addresses) {
                        Some(tx) => send(Item::Tx { slot: d.slot, tx, t, executed: None, raw: RawTx::Pb(pb), exec: None }),
                        None => true,
                    }
                }).await
        }
        FeedKind::YellowstoneTx => {
            // `failed`: None delivers failed transactions too ([[state.tx_stream]] failed = true, the default)
            let mk = |inc: Vec<String>| FilterTx { vote: Some(false), failed: f.failed, account_include: inc, ..Default::default() };
            let transactions: HashMap<String, FilterTx> = if f.split_include {
                f.account_include.iter().enumerate().map(|(i, a)| (format!("arb{i}"), mk(vec![a.clone()]))).collect()
            } else { HashMap::from([("arb".to_string(), mk(f.account_include.clone()))]) };
            let first = SubscribeRequest { transactions, commitment: Some(0), ..Default::default() };
            let ping = SubscribeRequest { ping: Some(Ping { id: 1 }), ..Default::default() };
            bidi(&mut grpc, "/geyser.Geyser/Subscribe", first, ping, token.as_deref(), f.token_header.as_deref(),
                |m: SubscribeUpdate| {
                    let t = now_ns();
                    note_lag(c, m.created_at.as_ref(), t);
                    let Some(u) = m.transaction else { return true };
                    match tx_stream_item(u, t, rec, roles, recent) { Some(it) => send(it), None => true }
                }).await
        }
        _ => bail!("{}: not a grpc feed", f.name),
    }
}

/// What the state stream subscribes to besides the accounts (WP-03 items 6, 7)
#[derive(Clone, Copy, Debug, Default)]
pub struct StateSubs {
    /// interslot slot updates too (first-shred, completed, created-bank, dead): `[state] slot_statuses = "all"`
    pub interslot: bool,
    /// `blocks_meta` (`[state] block_meta`: on, or auto and the probe accepted it)
    pub block_meta: bool,
}

/// The state stream's subscription for `accounts` (one replacement request whenever the list changes)
pub fn state_request(accounts: Vec<String>, subs: StateSubs) -> SubscribeRequest {
    SubscribeRequest {
        accounts: HashMap::from([("pools".to_string(), FilterAccounts { account: accounts, owner: vec![] })]),
        slots: HashMap::from([("slots".to_string(), FilterSlots { filter_by_commitment: Some(false), interslot_updates: Some(subs.interslot) })]),
        blocks_meta: if subs.block_meta { HashMap::from([("blocks_meta".to_string(), FilterBlocksMeta {})]) } else { HashMap::new() },
        commitment: Some(0),
        ..Default::default()
    }
}

/// The state stream's account list as its request names it (base58) from the engine's keys, each key encoded once:
/// `cache` holds the strings of the previous lists (the sender task keeps it across replacements), so a re-follow of a
/// few arrays encodes those only (PLAN-ADDENDUM WP-21 review R2-3: 12,000 keys took 8.8 ms to encode from scratch). It
/// keeps only the listed keys once it holds twice as many. The caller runs it on a blocking thread
pub fn encode_watch(keys: Vec<crate::tx::Pk>, mut cache: HashMap<crate::tx::Pk, String>) -> (Vec<String>, HashMap<crate::tx::Pk, String>) {
    let out: Vec<String> = keys.iter().map(|k| cache.entry(*k).or_insert_with(|| crate::tx::b58(k)).clone()).collect();
    if cache.len() > 2 * keys.len() + 1_024 {
        let listed: std::collections::HashSet<&crate::tx::Pk> = keys.iter().collect();
        cache.retain(|k, _| listed.contains(k));
    }
    (out, cache)
}

/// Pool-state stream: account updates plus slot updates (and block meta when on), at processed commitment. The account
/// list comes from a watch channel: whenever the engine changes it (DLMM bin arrays following the active bin), a full
/// replacement request is sent on the same stream. `c`: the stream's counters (provider lag)
pub async fn accounts_once(url: &str, token: Option<&str>, mut list: tokio::sync::watch::Receiver<Vec<crate::tx::Pk>>, subs: StateSubs, c: &FeedCounters,
    sink: &(dyn Fn(Item) -> bool + Send + Sync)) -> Result<()> {
    let mut grpc = tonic::client::Grpc::new(channel(url).await?).max_decoding_message_size(256 * 1024 * 1024);
    grpc.ready().await.context("state service not ready")?;
    // the keys are encoded on a blocking thread, each once (`encode_watch`): never on the engine thread (WP-21 review F2)
    // nor on this hot runtime's workers (review R2-3)
    let (out_tx, out_rx) = tokio::sync::mpsc::channel::<SubscribeRequest>(16);
    let first = list.borrow_and_update().clone();
    let (strings, mut cache) = tokio::task::spawn_blocking(move || encode_watch(first, HashMap::new())).await.context("encoding the watch list")?;
    out_tx.send(state_request(strings, subs)).await.ok();
    let sender = tokio::spawn(async move {
        let mut ping = tokio::time::interval(Duration::from_secs(10));
        ping.tick().await;
        loop {
            tokio::select! {
                _ = ping.tick() => { if out_tx.send(SubscribeRequest { ping: Some(Ping { id: 1 }), ..Default::default() }).await.is_err() { break; } }
                ch = list.changed() => {
                    if ch.is_err() { break; }
                    let l: Vec<crate::tx::Pk> = list.borrow_and_update().clone();
                    let c = std::mem::take(&mut cache);
                    let Ok((strings, c)) = tokio::task::spawn_blocking(move || encode_watch(l, c)).await else { break };
                    cache = c;
                    if out_tx.send(state_request(strings, subs)).await.is_err() { break; }
                }
            }
        }
    });
    let mut req = tonic::Request::new(tokio_stream::wrappers::ReceiverStream::new(out_rx));
    with_token(&mut req, token, None)?;
    let codec: ProstCodec<SubscribeRequest, SubscribeUpdate> = ProstCodec::default();
    let res = async {
        let mut st = grpc.streaming(req, http::uri::PathAndQuery::from_static("/geyser.Geyser/Subscribe"), codec).await?.into_inner();
        while let Some(m) = st.message().await? {
            let t = now_ns();
            note_lag(c, m.created_at.as_ref(), t);
            let bm = m.block_meta.is_some();
            match state_item(m, t) {
                Some(it) => if !sink(it) { return Ok(()); },
                // a block meta whose blockhash does not decode is dropped, and counted (feedhealth `errors`; review
                // WP-03 N6)
                None if bm => { c.errors.fetch_add(1, std::sync::atomic::Ordering::Relaxed); }
                None => {}
            }
        }
        bail!("stream ended")
    }.await;
    sender.abort();
    res
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::feeds::fixture::{self, first_field, k, sig, Proto};
    use prost::Message as _;

    /// PLAN-ADDENDUM WP-21 review R2-3: the watch list's encoding, off the hot runtime and each key once. 12,000 keys from
    /// scratch (what a replacement cost a hot worker before), then the same list with 10 arrays replaced (a re-follow) on
    /// the warm cache: the strings are base58's, in the list's order
    #[test]
    fn the_watch_list_is_encoded_once_per_key() {
        let key = |i: u32| { let mut k = [0u8; 32]; k[..4].copy_from_slice(&i.to_le_bytes()); k[31] = 7; k };
        let keys: Vec<crate::tx::Pk> = (0..12_000).map(key).collect();
        let t = std::time::Instant::now();
        let (cold, cache) = encode_watch(keys.clone(), HashMap::new());
        let cold_us = t.elapsed().as_nanos() as f64 / 1e3;
        let mut next = keys.clone();
        for (j, k) in next.iter_mut().rev().take(10).enumerate() { *k = key(1_000_000 + j as u32); }
        let t = std::time::Instant::now();
        let (warm, cache) = encode_watch(next.clone(), cache);
        let warm_us = t.elapsed().as_nanos() as f64 / 1e3;
        eprintln!("watch list of 12,000 keys: encoded from scratch {cold_us:.0} µs (the hot worker's cost per replacement before); a re-follow of 10 \
            arrays on the warm cache {warm_us:.0} µs, on a blocking thread");
        assert_eq!(cold, keys.iter().map(crate::tx::b58).collect::<Vec<_>>());
        assert_eq!(warm, next.iter().map(crate::tx::b58).collect::<Vec<_>>());
        assert_eq!(cache.len(), 12_010, "the replaced keys stay until the cache doubles");
        // a list much smaller than the cache prunes it to the listed keys
        let (_, cache) = encode_watch(next[..100].to_vec(), cache);
        assert_eq!(cache.len(), 100);
    }

    /// PLAN WP-03 item 4: every field of the hand-written structs this module reads or sends has the number the vendored
    /// upstream text (testdata/proto/) gives it. Each struct is encoded with one field set and its first tag compared
    fn enc<T: prost::Message>(m: T) -> u32 { first_field(&m.encode_to_vec()) }
    #[test]
    fn field_numbers_match_the_vendored_proto() {
        let p = Proto::load();
        let s = |n: &str| n.to_string();
        let checks: Vec<(&str, &str, u32)> = vec![
            ("Transaction", "signatures", enc(PbTransaction { signatures: vec![vec![1]], ..Default::default() })),
            ("Transaction", "message", enc(PbTransaction { message: Some(Default::default()), ..Default::default() })),
            ("Message", "header", enc(PbMessage { header: Some(Default::default()), ..Default::default() })),
            ("Message", "account_keys", enc(PbMessage { account_keys: vec![vec![1]], ..Default::default() })),
            ("Message", "recent_blockhash", enc(PbMessage { recent_blockhash: vec![1], ..Default::default() })),
            ("Message", "instructions", enc(PbMessage { instructions: vec![Default::default()], ..Default::default() })),
            ("Message", "versioned", enc(PbMessage { versioned: true, ..Default::default() })),
            ("Message", "address_table_lookups", enc(PbMessage { address_table_lookups: vec![Default::default()], ..Default::default() })),
            ("Message", "config", enc(PbMessage { config: Some(Default::default()), ..Default::default() })),
            ("TransactionConfig", "priority_fee", enc(PbTxConfig { priority_fee: Some(1), ..Default::default() })),
            ("TransactionConfig", "compute_unit_limit", enc(PbTxConfig { compute_unit_limit: Some(1), ..Default::default() })),
            ("TransactionConfig", "loaded_accounts_data_size_limit", enc(PbTxConfig { loaded_accounts_data_size_limit: Some(1), ..Default::default() })),
            ("MessageHeader", "num_required_signatures", enc(PbHeader { num_required_signatures: 1, ..Default::default() })),
            ("MessageHeader", "num_readonly_signed_accounts", enc(PbHeader { num_readonly_signed_accounts: 1, ..Default::default() })),
            ("MessageHeader", "num_readonly_unsigned_accounts", enc(PbHeader { num_readonly_unsigned_accounts: 1, ..Default::default() })),
            ("CompiledInstruction", "program_id_index", enc(PbIx { program_id_index: 1, ..Default::default() })),
            ("CompiledInstruction", "accounts", enc(PbIx { accounts: vec![1], ..Default::default() })),
            ("CompiledInstruction", "data", enc(PbIx { data: vec![1], ..Default::default() })),
            ("MessageAddressTableLookup", "account_key", enc(PbLookup { account_key: vec![1], ..Default::default() })),
            ("MessageAddressTableLookup", "writable_indexes", enc(PbLookup { writable_indexes: vec![1], ..Default::default() })),
            ("MessageAddressTableLookup", "readonly_indexes", enc(PbLookup { readonly_indexes: vec![1], ..Default::default() })),
            ("TransactionError", "err", enc(PbTxError { err: vec![1] })),
            ("TransactionStatusMeta", "err", enc(PbMeta { err: Some(Default::default()), ..Default::default() })),
            ("TransactionStatusMeta", "fee", enc(PbMeta { fee: 1, ..Default::default() })),
            ("TransactionStatusMeta", "pre_balances", enc(PbMeta { pre_balances: vec![1], ..Default::default() })),
            ("TransactionStatusMeta", "post_balances", enc(PbMeta { post_balances: vec![1], ..Default::default() })),
            ("TransactionStatusMeta", "inner_instructions", enc(PbMeta { inner_instructions: vec![Default::default()], ..Default::default() })),
            ("TransactionStatusMeta", "inner_instructions_none", enc(PbMeta { inner_instructions_none: true, ..Default::default() })),
            ("TransactionStatusMeta", "log_messages", enc(PbMeta { log_messages: vec![s("x")], ..Default::default() })),
            ("TransactionStatusMeta", "log_messages_none", enc(PbMeta { log_messages_none: true, ..Default::default() })),
            ("TransactionStatusMeta", "pre_token_balances", enc(PbMeta { pre_token_balances: vec![Default::default()], ..Default::default() })),
            ("TransactionStatusMeta", "post_token_balances", enc(PbMeta { post_token_balances: vec![Default::default()], ..Default::default() })),
            ("TransactionStatusMeta", "loaded_writable_addresses", enc(PbMeta { loaded_writable_addresses: vec![vec![1]], ..Default::default() })),
            ("TransactionStatusMeta", "loaded_readonly_addresses", enc(PbMeta { loaded_readonly_addresses: vec![vec![1]], ..Default::default() })),
            ("TransactionStatusMeta", "return_data", enc(PbMeta { return_data: Some(Default::default()), ..Default::default() })),
            ("TransactionStatusMeta", "return_data_none", enc(PbMeta { return_data_none: true, ..Default::default() })),
            ("TransactionStatusMeta", "compute_units_consumed", enc(PbMeta { compute_units_consumed: Some(1), ..Default::default() })),
            ("TransactionStatusMeta", "cost_units", enc(PbMeta { cost_units: Some(1), ..Default::default() })),
            ("InnerInstructions", "index", enc(PbInnerIxs { index: 1, ..Default::default() })),
            ("InnerInstructions", "instructions", enc(PbInnerIxs { instructions: vec![Default::default()], ..Default::default() })),
            ("InnerInstruction", "program_id_index", enc(PbInnerIx { program_id_index: 1, ..Default::default() })),
            ("InnerInstruction", "accounts", enc(PbInnerIx { accounts: vec![1], ..Default::default() })),
            ("InnerInstruction", "data", enc(PbInnerIx { data: vec![1], ..Default::default() })),
            ("InnerInstruction", "stack_height", enc(PbInnerIx { stack_height: Some(1), ..Default::default() })),
            ("ReturnData", "program_id", enc(PbReturnData { program_id: vec![1], ..Default::default() })),
            ("ReturnData", "data", enc(PbReturnData { data: vec![1], ..Default::default() })),
            ("TokenBalance", "account_index", enc(PbTokenBalance { account_index: 1, ..Default::default() })),
            ("TokenBalance", "mint", enc(PbTokenBalance { mint: s("m"), ..Default::default() })),
            ("TokenBalance", "ui_token_amount", enc(PbTokenBalance { ui_token_amount: Some(Default::default()), ..Default::default() })),
            ("TokenBalance", "owner", enc(PbTokenBalance { owner: s("o"), ..Default::default() })),
            ("TokenBalance", "program_id", enc(PbTokenBalance { program_id: s("p"), ..Default::default() })),
            ("UiTokenAmount", "decimals", enc(PbUiAmount { decimals: 1, ..Default::default() })),
            ("UiTokenAmount", "amount", enc(PbUiAmount { amount: s("1"), ..Default::default() })),
            ("UnixTimestamp", "timestamp", enc(PbUnixTimestamp { timestamp: 1 })),
            ("BlockHeight", "block_height", enc(PbBlockHeight { block_height: 1 })),
            ("Timestamp", "seconds", enc(PbTimestamp { seconds: 1, nanos: 0 })),
            ("Timestamp", "nanos", enc(PbTimestamp { seconds: 0, nanos: 1 })),
            ("SubscribeRequestPing", "id", enc(Ping { id: 1 })),
            ("SubscribeRequestFilterSlots", "filter_by_commitment", enc(FilterSlots { filter_by_commitment: Some(true), ..Default::default() })),
            ("SubscribeRequestFilterSlots", "interslot_updates", enc(FilterSlots { interslot_updates: Some(true), ..Default::default() })),
            ("SubscribeRequestFilterDeshredTransactions", "vote", enc(FilterDeshredTx { vote: Some(true), ..Default::default() })),
            ("SubscribeRequestFilterDeshredTransactions", "account_include", enc(FilterDeshredTx { account_include: vec![s("a")], ..Default::default() })),
            ("SubscribeRequestFilterDeshredTransactions", "account_exclude", enc(FilterDeshredTx { account_exclude: vec![s("a")], ..Default::default() })),
            ("SubscribeRequestFilterDeshredTransactions", "account_required", enc(FilterDeshredTx { account_required: vec![s("a")], ..Default::default() })),
            ("SubscribeDeshredRequest", "deshred_transactions", enc(SubscribeDeshredRequest { deshred_transactions: HashMap::from([(s("a"), Default::default())]), ..Default::default() })),
            ("SubscribeDeshredRequest", "ping", enc(SubscribeDeshredRequest { ping: Some(Default::default()), ..Default::default() })),
            ("SubscribeDeshredRequest", "slots", enc(SubscribeDeshredRequest { slots: HashMap::from([(s("a"), Default::default())]), ..Default::default() })),
            ("SubscribeUpdateDeshredTransactionInfo", "signature", enc(DeshredTxInfo { signature: vec![1], ..Default::default() })),
            ("SubscribeUpdateDeshredTransactionInfo", "is_vote", enc(DeshredTxInfo { is_vote: true, ..Default::default() })),
            ("SubscribeUpdateDeshredTransactionInfo", "transaction", enc(DeshredTxInfo { transaction: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateDeshredTransactionInfo", "loaded_writable_addresses", enc(DeshredTxInfo { loaded_writable_addresses: vec![vec![1]], ..Default::default() })),
            ("SubscribeUpdateDeshredTransactionInfo", "loaded_readonly_addresses", enc(DeshredTxInfo { loaded_readonly_addresses: vec![vec![1]], ..Default::default() })),
            ("SubscribeUpdateDeshredTransaction", "transaction", enc(DeshredTx { transaction: Some(Default::default()), slot: 0 })),
            ("SubscribeUpdateDeshredTransaction", "slot", enc(DeshredTx { transaction: None, slot: 1 })),
            ("SubscribeUpdateDeshred", "deshred_transaction", enc(SubscribeUpdateDeshred { deshred_transaction: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateDeshred", "ping", enc(SubscribeUpdateDeshred { ping: Some(PbEmpty {}), ..Default::default() })),
            ("SubscribeUpdateDeshred", "created_at", enc(SubscribeUpdateDeshred { created_at: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateDeshred", "slot", enc(SubscribeUpdateDeshred { slot: Some(Default::default()), ..Default::default() })),
            ("SubscribeRequestFilterTransactions", "vote", enc(FilterTx { vote: Some(true), ..Default::default() })),
            ("SubscribeRequestFilterTransactions", "failed", enc(FilterTx { failed: Some(true), ..Default::default() })),
            ("SubscribeRequestFilterTransactions", "account_include", enc(FilterTx { account_include: vec![s("a")], ..Default::default() })),
            ("SubscribeRequestFilterTransactions", "account_exclude", enc(FilterTx { account_exclude: vec![s("a")], ..Default::default() })),
            ("SubscribeRequestFilterTransactions", "account_required", enc(FilterTx { account_required: vec![s("a")], ..Default::default() })),
            ("SubscribeRequestFilterAccounts", "account", enc(FilterAccounts { account: vec![s("a")], ..Default::default() })),
            ("SubscribeRequestFilterAccounts", "owner", enc(FilterAccounts { owner: vec![s("a")], ..Default::default() })),
            ("SubscribeRequestFilterBlocks", "account_include", enc(FilterBlocks { account_include: vec![s("a")], ..Default::default() })),
            ("SubscribeRequestFilterBlocks", "include_transactions", enc(FilterBlocks { include_transactions: Some(true), ..Default::default() })),
            ("SubscribeRequestFilterBlocks", "include_accounts", enc(FilterBlocks { include_accounts: Some(true), ..Default::default() })),
            ("SubscribeRequestFilterBlocks", "include_entries", enc(FilterBlocks { include_entries: Some(true), ..Default::default() })),
            ("SubscribeRequest", "accounts", enc(SubscribeRequest { accounts: HashMap::from([(s("a"), Default::default())]), ..Default::default() })),
            ("SubscribeRequest", "slots", enc(SubscribeRequest { slots: HashMap::from([(s("a"), Default::default())]), ..Default::default() })),
            ("SubscribeRequest", "transactions", enc(SubscribeRequest { transactions: HashMap::from([(s("a"), Default::default())]), ..Default::default() })),
            ("SubscribeRequest", "blocks", enc(SubscribeRequest { blocks: HashMap::from([(s("a"), Default::default())]), ..Default::default() })),
            ("SubscribeRequest", "blocks_meta", enc(SubscribeRequest { blocks_meta: HashMap::from([(s("a"), Default::default())]), ..Default::default() })),
            ("SubscribeRequest", "commitment", enc(SubscribeRequest { commitment: Some(1), ..Default::default() })),
            ("SubscribeRequest", "ping", enc(SubscribeRequest { ping: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateTransactionInfo", "signature", enc(TxInfo { signature: vec![1], ..Default::default() })),
            ("SubscribeUpdateTransactionInfo", "is_vote", enc(TxInfo { is_vote: true, ..Default::default() })),
            ("SubscribeUpdateTransactionInfo", "transaction", enc(TxInfo { transaction: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateTransactionInfo", "meta", enc(TxInfo { meta: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateTransactionInfo", "index", enc(TxInfo { index: 1, ..Default::default() })),
            ("SubscribeUpdateTransaction", "transaction", enc(UpdateTx { transaction: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateTransaction", "slot", enc(UpdateTx { transaction: None, slot: 1, bank_id: 0 })),
            ("SubscribeUpdateTransaction", "bank_id", enc(UpdateTx { bank_id: 1, ..Default::default() })),
            ("SubscribeUpdateAccountInfo", "pubkey", enc(AccountInfo { pubkey: vec![1], ..Default::default() })),
            ("SubscribeUpdateAccountInfo", "lamports", enc(AccountInfo { lamports: 1, ..Default::default() })),
            ("SubscribeUpdateAccountInfo", "owner", enc(AccountInfo { owner: vec![1], ..Default::default() })),
            ("SubscribeUpdateAccountInfo", "data", enc(AccountInfo { data: vec![1], ..Default::default() })),
            ("SubscribeUpdateAccountInfo", "write_version", enc(AccountInfo { write_version: 1, ..Default::default() })),
            ("SubscribeUpdateAccountInfo", "txn_signature", enc(AccountInfo { txn_signature: Some(vec![1]), ..Default::default() })),
            ("SubscribeUpdateAccount", "account", enc(UpdateAccount { account: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateAccount", "slot", enc(UpdateAccount { slot: 1, ..Default::default() })),
            ("SubscribeUpdateAccount", "is_startup", enc(UpdateAccount { is_startup: true, ..Default::default() })),
            ("SubscribeUpdateAccount", "bank_id", enc(UpdateAccount { bank_id: Some(1), ..Default::default() })),
            ("SubscribeUpdateSlot", "slot", enc(UpdateSlot { slot: 1, ..Default::default() })),
            ("SubscribeUpdateSlot", "parent", enc(UpdateSlot { parent: Some(1), ..Default::default() })),
            ("SubscribeUpdateSlot", "status", enc(UpdateSlot { status: 1, ..Default::default() })),
            ("SubscribeUpdateSlot", "dead_error", enc(UpdateSlot { dead_error: Some(s("x")), ..Default::default() })),
            ("SubscribeUpdateSlot", "bank_id", enc(UpdateSlot { bank_id: Some(1), ..Default::default() })),
            ("SubscribeUpdateBlockMeta", "slot", enc(UpdateBlockMeta { slot: 1, ..Default::default() })),
            ("SubscribeUpdateBlockMeta", "blockhash", enc(UpdateBlockMeta { blockhash: s("x"), ..Default::default() })),
            ("SubscribeUpdateBlockMeta", "block_time", enc(UpdateBlockMeta { block_time: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateBlockMeta", "block_height", enc(UpdateBlockMeta { block_height: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdateBlockMeta", "parent_slot", enc(UpdateBlockMeta { parent_slot: 1, ..Default::default() })),
            ("SubscribeUpdateBlockMeta", "parent_blockhash", enc(UpdateBlockMeta { parent_blockhash: s("x"), ..Default::default() })),
            ("SubscribeUpdateBlockMeta", "executed_transaction_count", enc(UpdateBlockMeta { executed_transaction_count: 1, ..Default::default() })),
            ("SubscribeUpdateBlockMeta", "entries_count", enc(UpdateBlockMeta { entries_count: 1, ..Default::default() })),
            ("SubscribeUpdateBlockMeta", "bank_id", enc(UpdateBlockMeta { bank_id: 1, ..Default::default() })),
            ("SubscribeUpdateBlock", "slot", enc(UpdateBlock { slot: 1 })),
            ("SubscribeUpdate", "account", enc(SubscribeUpdate { account: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdate", "slot", enc(SubscribeUpdate { slot: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdate", "transaction", enc(SubscribeUpdate { transaction: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdate", "block", enc(SubscribeUpdate { block: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdate", "ping", enc(SubscribeUpdate { ping: Some(PbEmpty {}), ..Default::default() })),
            ("SubscribeUpdate", "block_meta", enc(SubscribeUpdate { block_meta: Some(Default::default()), ..Default::default() })),
            ("SubscribeUpdate", "pong", enc(SubscribeUpdate { pong: Some(PbEmpty {}), ..Default::default() })),
            ("SubscribeUpdate", "created_at", enc(SubscribeUpdate { created_at: Some(Default::default()), ..Default::default() })),
        ];
        for (m, f, got) in &checks { assert_eq!(*got, p.field(m, f).0, "{m}.{f}: our tag {got}, the proto's {}", p.field(m, f).0); }
        assert!(checks.len() > 120);
    }

    /// review WP-03 #12: a slot's and a block's `bank_id` reach their items (slots.jsonl, blocks.jsonl); 0 / absent is None
    #[test]
    fn bank_id_reaches_the_items() {
        let slot = |b: Option<u64>| SubscribeUpdate { slot: Some(UpdateSlot { slot: 5, status: 3, bank_id: b, ..Default::default() }), ..Default::default() };
        let back = |u: SubscribeUpdate| SubscribeUpdate::decode(&u.encode_to_vec()[..]).unwrap();
        assert!(matches!(state_item(back(slot(Some(77))), 1), Some(Item::Slot { bank_id: Some(77), .. })));
        assert!(matches!(state_item(back(slot(None)), 1), Some(Item::Slot { bank_id: None, .. })));
        let bh = bs58::encode([3u8; 32]).into_string();
        let meta = |b: u64| SubscribeUpdate { block_meta: Some(UpdateBlockMeta { slot: 5, blockhash: bh.clone(), bank_id: b, ..Default::default() }), ..Default::default() };
        assert!(matches!(state_item(back(meta(9)), 1), Some(Item::BlockMeta(BlockMeta { bank_id: Some(9), .. }))));
        assert!(matches!(state_item(back(meta(0)), 1), Some(Item::BlockMeta(BlockMeta { bank_id: None, .. }))));
        // an undecodable blockhash: no item (accounts_once counts it in the feed's errors)
        let bad = SubscribeUpdate { block_meta: Some(UpdateBlockMeta { slot: 5, blockhash: "not-base58!".into(), ..Default::default() }), ..Default::default() };
        assert!(state_item(bad, 1).is_none());
    }

    /// PLAN WP-03 acceptance, the prost round trips (bytes encoded from the proto text's field numbers, decoded by these
    /// structs, re-encoded by prost and decoded again): an account update with write_version and txn_signature; a
    /// transaction with inner instructions, return data and loaded addresses; block meta; a slot with parent and
    /// dead_error
    #[test]
    fn prost_round_trips_against_the_vendored_proto() {
        let p = Proto::load();
        let ups: Vec<SubscribeUpdate> = fixture::stream(&p).iter().map(|(_, b)| SubscribeUpdate::decode(&b[..]).unwrap()).collect();
        let again = |u: &SubscribeUpdate| SubscribeUpdate::decode(&u.encode_to_vec()[..]).unwrap();
        for u in &ups { assert_eq!(&again(u), u, "prost round trip"); }
        // the wallet update
        let a = ups[0].account.as_ref().unwrap();
        let info = a.account.as_ref().unwrap();
        assert_eq!((a.slot, info.write_version, info.txn_signature.as_deref(), info.pubkey.as_slice()), (1_000, 100, Some(&sig(fixture::OURS)[..]), &k(fixture::WALLET)[..]));
        assert!(ups[0].created_at.as_ref().unwrap().ns().unwrap() == fixture::T0 - 2_000_000);
        assert!(ups.last().unwrap().account.as_ref().unwrap().is_startup);
        // the PumpSwap transaction
        let u = ups[5].transaction.as_ref().unwrap();
        let info = u.transaction.as_ref().unwrap();
        let (tx, meta) = (info.transaction.as_ref().unwrap(), info.meta.as_ref().unwrap());
        let msg = tx.message.as_ref().unwrap();
        assert_eq!((u.slot, info.index, msg.recent_blockhash.as_slice(), msg.versioned), (1_000, 17, &k(0x33)[..], true));
        assert_eq!(meta.inner_instructions[0].index, 2);
        assert_eq!(meta.inner_instructions[0].instructions[0], PbInnerIx { program_id_index: 6, accounts: vec![2, 0], data: vec![3, 9, 9], stack_height: Some(2) });
        assert_eq!(meta.return_data, Some(PbReturnData { program_id: fixture::pumpswap().to_vec(), data: vec![1, 2, 3] }));
        assert_eq!((meta.loaded_writable_addresses.clone(), meta.loaded_readonly_addresses.clone()), (vec![k(fixture::LW).to_vec()], vec![k(fixture::LR).to_vec()]));
        assert_eq!((meta.compute_units_consumed, meta.cost_units, meta.fee), (Some(45_000), Some(61_000), 6_000));
        let tb = &meta.post_token_balances[0];
        assert_eq!((tb.ui_token_amount.as_ref().unwrap().decimals, tb.ui_token_amount.as_ref().unwrap().amount.as_str(), tb.program_id.as_str()),
            (6, "1500", bs58::encode(fixture::token()).into_string().as_str()));
        assert!(!meta.inner_instructions_none && !meta.log_messages_none && meta.log_messages.len() == 2);
        let failed = ups[13].transaction.as_ref().unwrap().transaction.as_ref().unwrap().meta.as_ref().unwrap();
        assert!(failed.err.is_some() && failed.inner_instructions_none && failed.log_messages_none && failed.return_data.is_none());
        // the slot with a parent and a dead error, and the block meta
        let dead = ups[10].slot.as_ref().unwrap();
        assert_eq!((dead.slot, dead.parent, dead.status, dead.dead_error.as_deref()), (1_001, Some(1_000), 6, Some("fork abandoned")));
        let b = ups[12].block_meta.as_ref().unwrap();
        assert_eq!((b.slot, b.parent_slot, b.block_height.as_ref().unwrap().block_height, b.block_time.as_ref().unwrap().timestamp, b.executed_transaction_count, b.entries_count),
            (1_000, 999, 900, 1_791_000_000, 1_234, 64));
        assert_eq!(b.blockhash, bs58::encode(k(0x34)).into_string());
        // and as items
        let Some(Item::BlockMeta(bm)) = state_item(ups[12].clone(), 5) else { panic!("block meta item") };
        assert_eq!((bm.blockhash, bm.parent_blockhash, bm.block_height, bm.block_time, bm.t), (k(0x34), k(0x33), Some(900), Some(1_791_000_000), 5));
        let Some(Item::Slot { parent, dead_error, status, .. }) = state_item(ups[10].clone(), 5) else { panic!("slot item") };
        assert_eq!((parent, dead_error.as_deref(), status), (Some(1_000), Some("fork abandoned"), 6));
    }

    /// The state stream's subscription (WP-03 items 6, 7): interslot updates and blocks_meta as configured
    #[test]
    fn the_state_request_follows_its_options() {
        let r = state_request(vec!["a".into()], StateSubs { interslot: true, block_meta: true });
        assert_eq!(r.slots["slots"], FilterSlots { filter_by_commitment: Some(false), interslot_updates: Some(true) });
        assert!(r.blocks_meta.contains_key("blocks_meta") && r.accounts["pools"].account == vec!["a".to_string()]);
        let r = state_request(vec![], StateSubs::default());
        assert_eq!((r.slots["slots"].interslot_updates, r.blocks_meta.len()), (Some(false), 0));
    }
}

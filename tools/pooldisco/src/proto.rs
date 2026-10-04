//! Hand-written prost messages for Yellowstone gRPC (only the fields pooldisco reads). Field numbers follow
//! yellowstone-grpc-proto geyser.proto / solana-storage.proto, the same way arb-lab's src/feeds/grpc.rs does it.
use std::collections::HashMap;

#[derive(Clone, PartialEq, prost::Message)]
pub struct PbTransaction {
    #[prost(bytes = "vec", repeated, tag = "1")] pub signatures: Vec<Vec<u8>>,
    #[prost(message, optional, tag = "2")] pub message: Option<PbMessage>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbMessage {
    #[prost(bytes = "vec", repeated, tag = "2")] pub account_keys: Vec<Vec<u8>>,
    #[prost(message, repeated, tag = "4")] pub instructions: Vec<PbIx>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbIx {
    #[prost(uint32, tag = "1")] pub program_id_index: u32,
    #[prost(bytes = "vec", tag = "2")] pub accounts: Vec<u8>,
    #[prost(bytes = "vec", tag = "3")] pub data: Vec<u8>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbTxError { #[prost(bytes = "vec", tag = "1")] pub err: Vec<u8> }
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbInner {
    #[prost(uint32, tag = "1")] pub index: u32,
    #[prost(message, repeated, tag = "2")] pub instructions: Vec<PbIx>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbMeta {
    #[prost(message, optional, tag = "1")] pub err: Option<PbTxError>,
    #[prost(uint64, tag = "2")] pub fee: u64,
    #[prost(uint64, repeated, tag = "3")] pub pre_balances: Vec<u64>,
    #[prost(uint64, repeated, tag = "4")] pub post_balances: Vec<u64>,
    #[prost(message, repeated, tag = "5")] pub inner_instructions: Vec<PbInner>,
    #[prost(message, repeated, tag = "7")] pub pre_token_balances: Vec<PbTokenBalance>,
    #[prost(message, repeated, tag = "8")] pub post_token_balances: Vec<PbTokenBalance>,
    #[prost(bytes = "vec", repeated, tag = "12")] pub loaded_writable_addresses: Vec<Vec<u8>>,
    #[prost(bytes = "vec", repeated, tag = "13")] pub loaded_readonly_addresses: Vec<Vec<u8>>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbTokenBalance {
    #[prost(uint32, tag = "1")] pub account_index: u32,
    #[prost(string, tag = "2")] pub mint: String,
    #[prost(message, optional, tag = "3")] pub ui_token_amount: Option<PbUiAmount>,
    #[prost(string, tag = "4")] pub owner: String,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbUiAmount { #[prost(string, tag = "3")] pub amount: String }

#[derive(Clone, PartialEq, prost::Message)]
pub struct Ping { #[prost(int32, tag = "1")] pub id: i32 }
#[derive(Clone, PartialEq, prost::Message)]
pub struct FilterSlots {
    #[prost(bool, optional, tag = "1")] pub filter_by_commitment: Option<bool>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct FilterTx {
    #[prost(bool, optional, tag = "1")] pub vote: Option<bool>,
    #[prost(bool, optional, tag = "2")] pub failed: Option<bool>,
    #[prost(string, repeated, tag = "3")] pub account_include: Vec<String>,
    #[prost(string, repeated, tag = "4")] pub account_exclude: Vec<String>,
    #[prost(string, repeated, tag = "6")] pub account_required: Vec<String>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct Memcmp {
    #[prost(uint64, tag = "1")] pub offset: u64,
    #[prost(oneof = "MemData", tags = "2, 3, 4")] pub data: Option<MemData>,
}
#[derive(Clone, PartialEq, prost::Oneof)]
pub enum MemData {
    #[prost(bytes, tag = "2")] Bytes(Vec<u8>),
    #[prost(string, tag = "3")] Base58(String),
    #[prost(string, tag = "4")] Base64(String),
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct AccFilter { #[prost(oneof = "AccF", tags = "1, 2")] pub filter: Option<AccF> }
#[derive(Clone, PartialEq, prost::Oneof)]
pub enum AccF {
    #[prost(message, tag = "1")] Memcmp(Memcmp),
    #[prost(uint64, tag = "2")] Datasize(u64),
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct FilterAccounts {
    #[prost(string, repeated, tag = "2")] pub account: Vec<String>,
    #[prost(string, repeated, tag = "3")] pub owner: Vec<String>,
    #[prost(message, repeated, tag = "4")] pub filters: Vec<AccFilter>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct SubscribeRequest {
    #[prost(map = "string, message", tag = "1")] pub accounts: HashMap<String, FilterAccounts>,
    #[prost(map = "string, message", tag = "2")] pub slots: HashMap<String, FilterSlots>,
    #[prost(map = "string, message", tag = "3")] pub transactions: HashMap<String, FilterTx>,
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
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct UpdateSlot { #[prost(uint64, tag = "1")] pub slot: u64 }
#[derive(Clone, PartialEq, prost::Message)]
pub struct SubscribeUpdate {
    #[prost(message, optional, tag = "2")] pub account: Option<UpdateAccount>,
    #[prost(message, optional, tag = "3")] pub slot: Option<UpdateSlot>,
    #[prost(message, optional, tag = "4")] pub transaction: Option<UpdateTx>,
}

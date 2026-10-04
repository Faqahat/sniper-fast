//! gRPC feeds with hand-written prost messages (only the fields we read; prost skips the rest), so no protoc is
//! needed. Field numbers are from yellowstone-grpc-proto (geyser.proto, solana-storage.proto) and Jito's shredstream.
//!   jito-entries        /shredstream.ShredstreamProxy/SubscribeEntries  server stream of {slot, entries}
//!   yellowstone-deshred /geyser.Geyser/SubscribeDeshred                 bidi; unexecuted transactions
//!   yellowstone-tx      /geyser.Geyser/Subscribe (transactions)         bidi; executed, processed commitment
//!   accounts            /geyser.Geyser/Subscribe (accounts + slots)     bidi; pool state for the engine
use crate::config::{FeedKind, Feed};
use crate::feeds::clock::now_ns;
use crate::tx::{self, Ix, Lookup, Pk, Tx};
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
    #[prost(message, repeated, tag = "4")] pub instructions: Vec<PbIx>,
    #[prost(bool, tag = "5")] pub versioned: bool,
    #[prost(message, repeated, tag = "6")] pub address_table_lookups: Vec<PbLookup>,
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
#[derive(Clone, PartialEq, prost::Message)]
pub struct PbMeta {
    #[prost(message, optional, tag = "1")] pub err: Option<PbTxError>,
    #[prost(uint64, tag = "2")] pub fee: u64,
    #[prost(uint64, repeated, tag = "3")] pub pre_balances: Vec<u64>,
    #[prost(uint64, repeated, tag = "4")] pub post_balances: Vec<u64>,
    #[prost(string, repeated, tag = "6")] pub log_messages: Vec<String>,
    #[prost(message, repeated, tag = "7")] pub pre_token_balances: Vec<PbTokenBalance>,
    #[prost(message, repeated, tag = "8")] pub post_token_balances: Vec<PbTokenBalance>,
    #[prost(bytes = "vec", repeated, tag = "12")] pub loaded_writable_addresses: Vec<Vec<u8>>,
    #[prost(bytes = "vec", repeated, tag = "13")] pub loaded_readonly_addresses: Vec<Vec<u8>>,
    #[prost(uint64, optional, tag = "16")] pub compute_units_consumed: Option<u64>,
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
    #[prost(bool, tag = "3")] pub is_startup: bool,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct UpdateSlot {
    #[prost(uint64, tag = "1")] pub slot: u64,
    #[prost(int32, tag = "3")] pub status: i32,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct SubscribeUpdate {
    #[prost(message, optional, tag = "2")] pub account: Option<UpdateAccount>,
    #[prost(message, optional, tag = "3")] pub slot: Option<UpdateSlot>,
    #[prost(message, optional, tag = "4")] pub transaction: Option<UpdateTx>,
}

/// One received item.
pub enum Item {
    /// a batch of serialized entries (Jito ShredStream interface)
    Entries { slot: u64, bytes: Vec<u8>, t: u64 },
    /// one transaction; `executed` is Some(succeeded) for executed (processed) feeds, None for unexecuted ones
    Tx { slot: u64, tx: Tx, t: u64, executed: Option<bool> },
    /// one account update (pool state)
    Account { slot: u64, pubkey: Pk, lamports: u64, owner: Pk, data: Vec<u8>, write_version: u64, t: u64, txn: Option<[u8; 64]> },
    /// a slot status update (0 processed, 1 confirmed, 2 finalized, 3+ first-shred/created/completed/dead)
    Slot { slot: u64, status: i32, t: u64 },
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
        while let Some(m) = st.message().await? {
            if !on_msg(m) { return Ok(()); }
        }
        bail!("stream ended")
    }.await;
    ping_task.abort();
    res
}

/// Connect once and stream a feed's items into `out` until the stream ends or errors. The caller reconnects.
pub async fn feed_once(f: &Feed, sink: &(dyn Fn(Item) -> bool + Send + Sync)) -> Result<()> {
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
            while let Some(m) = st.message().await? {
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
                    let Some(d) = m.deshred_transaction else { return true };
                    let Some(info) = d.transaction else { return true };
                    let Some(pb) = info.transaction.as_ref() else { return true };
                    match tx_from_pb(&info.signature, info.is_vote, pb, &info.loaded_writable_addresses, &info.loaded_readonly_addresses) {
                        Some(tx) => send(Item::Tx { slot: d.slot, tx, t, executed: None }),
                        None => true,
                    }
                }).await
        }
        FeedKind::YellowstoneTx => {
            let mk = |inc: Vec<String>| FilterTx { vote: Some(false), failed: None, account_include: inc, ..Default::default() };
            let transactions: HashMap<String, FilterTx> = if f.split_include {
                f.account_include.iter().enumerate().map(|(i, a)| (format!("arb{i}"), mk(vec![a.clone()]))).collect()
            } else { HashMap::from([("arb".to_string(), mk(f.account_include.clone()))]) };
            let first = SubscribeRequest { transactions, commitment: Some(0), ..Default::default() };
            let ping = SubscribeRequest { ping: Some(Ping { id: 1 }), ..Default::default() };
            bidi(&mut grpc, "/geyser.Geyser/Subscribe", first, ping, token.as_deref(), f.token_header.as_deref(),
                |m: SubscribeUpdate| {
                    let t = now_ns();
                    let Some(u) = m.transaction else { return true };
                    let Some(info) = u.transaction else { return true };
                    let Some(pb) = info.transaction.as_ref() else { return true };
                    let (ok, lw, lr) = match &info.meta {
                        Some(meta) => (meta.err.is_none(), meta.loaded_writable_addresses.clone(), meta.loaded_readonly_addresses.clone()),
                        None => (true, vec![], vec![]),
                    };
                    if let (Some(rec), Some(meta)) = (crate::record::get(), &info.meta) { rec_exec(rec, &info, pb, meta, u.slot, t); }
                    match tx_from_pb(&info.signature, info.is_vote, pb, &lw, &lr) {
                        Some(tx) => send(Item::Tx { slot: u.slot, tx, t, executed: Some(ok) }),
                        None => true,
                    }
                }).await
        }
        _ => bail!("{}: not a grpc feed", f.name),
    }
}

/// exec.jsonl: one executed transaction's result and what it did to its signer's balances
fn rec_exec(rec: &crate::record::Recorder, info: &TxInfo, pb: &PbTransaction, meta: &PbMeta, slot: u64, t: u64) {
    let signer = pb.message.as_ref().and_then(|m| m.account_keys.first()).map(|k| bs58::encode(k).into_string()).unwrap_or_default();
    let sol = match (meta.pre_balances.first(), meta.post_balances.first()) { (Some(a), Some(b)) => *b as i64 - *a as i64, _ => 0 };
    // the signer's token changes by mint (accounts it owns; a token account absent on one side counts as 0)
    let mut tok: std::collections::BTreeMap<&str, i128> = Default::default();
    for (side, list) in [(-1i128, &meta.pre_token_balances), (1, &meta.post_token_balances)] {
        for b in list.iter().filter(|b| b.owner == signer) {
            let amt: i128 = b.ui_token_amount.as_ref().and_then(|u| u.amount.parse().ok()).unwrap_or(0);
            *tok.entry(b.mint.as_str()).or_default() += side * amt;
        }
    }
    let tok: serde_json::Map<String, serde_json::Value> = tok.into_iter().filter(|(_, v)| *v != 0).map(|(k, v)| (k.to_string(), serde_json::json!(v.to_string()))).collect();
    let err = meta.err.as_ref().map(|e| crate::record::tx_error(&e.err));
    // the failing program's own words, when it failed
    let why = if err.is_some() {
        meta.log_messages.iter().rev().find(|l| l.contains("Error") || l.contains("error") || l.contains("failed")).map(|l| l.chars().take(160).collect::<String>())
    } else { None };
    let line = serde_json::json!({ "sig": bs58::encode(&info.signature).into_string(), "slot": slot, "idx": info.index, "t": t, "ok": err.is_none(),
        "err": err, "why": why, "fee": meta.fee, "cu": meta.compute_units_consumed, "signer": signer, "sol": sol, "tok": tok });
    crate::record::Recorder::line(&rec.exec, &line.to_string());
}

/// Pool-state stream: account updates plus slot updates, at processed commitment. The account list comes from a
/// watch channel: whenever the engine changes it (DLMM bin arrays following the active bin), a full replacement
/// request is sent on the same stream.
pub async fn accounts_once(url: &str, token: Option<&str>, mut list: tokio::sync::watch::Receiver<Vec<String>>,
    sink: &(dyn Fn(Item) -> bool + Send + Sync)) -> Result<()> {
    let mut grpc = tonic::client::Grpc::new(channel(url).await?).max_decoding_message_size(256 * 1024 * 1024);
    grpc.ready().await.context("state service not ready")?;
    let request = |accounts: Vec<String>| SubscribeRequest {
        accounts: HashMap::from([("pools".to_string(), FilterAccounts { account: accounts, owner: vec![] })]),
        slots: HashMap::from([("slots".to_string(), FilterSlots { filter_by_commitment: Some(false), interslot_updates: Some(false) })]),
        commitment: Some(0),
        ..Default::default()
    };
    let (out_tx, out_rx) = tokio::sync::mpsc::channel::<SubscribeRequest>(16);
    let first = list.borrow_and_update().clone();
    out_tx.send(request(first)).await.ok();
    let sender = tokio::spawn(async move {
        let mut ping = tokio::time::interval(Duration::from_secs(10));
        ping.tick().await;
        loop {
            tokio::select! {
                _ = ping.tick() => { if out_tx.send(SubscribeRequest { ping: Some(Ping { id: 1 }), ..Default::default() }).await.is_err() { break; } }
                ch = list.changed() => {
                    if ch.is_err() { break; }
                    let l: Vec<String> = list.borrow_and_update().clone();
                    if out_tx.send(request(l)).await.is_err() { break; }
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
            if let Some(a) = m.account {
                if let Some(info) = a.account {
                    if let (Some(pubkey), Some(owner)) = (to_pk(&info.pubkey), to_pk(&info.owner)) {
                        let txn = info.txn_signature.as_deref().and_then(|b| <[u8; 64]>::try_from(b).ok());
                        let it = Item::Account { slot: a.slot, pubkey, lamports: info.lamports, owner, data: info.data, write_version: info.write_version, t, txn };
                        if !sink(it) { return Ok(()); }
                    }
                }
            } else if let Some(s) = m.slot {
                if !sink(Item::Slot { slot: s.slot, status: s.status, t }) { return Ok(()); }
            }
        }
        bail!("stream ended")
    }.await;
    sender.abort();
    res
}

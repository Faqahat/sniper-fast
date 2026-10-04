//! RPC fallback feeds (used when no Yellowstone gRPC stream is available): Helius/Solana websockets
//! programSubscribe (pool state of the state-priced venues) and logsSubscribe (arbitrage-like transactions, which
//! are then fetched with getTransaction, sampled under a rate cap, and converted into the gRPC message types).
use crate::proto::*;
use crate::{b58, to_pk, Msg, Pk};
use futures_util::{SinkExt, StreamExt};
use serde_json::{json, Value};
use std::collections::{HashSet, VecDeque};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::Arc;
use std::time::Duration;
use tokio_tungstenite::tungstenite::Message as WsMsg;

#[derive(Default)]
pub struct Counters { pub logs: AtomicU64, pub arb_like_ok: AtomicU64, pub arb_like_fail: AtomicU64, pub fetched_ok: AtomicU64, pub fetched_fail: AtomicU64, pub ws_acct: AtomicU64 }

pub async fn programs(ws: String, subs: Vec<(Pk, [u8; 8])>, sink: crossbeam_channel::Sender<Msg>, c: Arc<Counters>) {
    loop {
        let r: anyhow::Result<()> = async {
            let (mut s, _) = tokio_tungstenite::connect_async(&ws).await?;
            for (i, (prog, d)) in subs.iter().enumerate() {
                let req = json!({"jsonrpc": "2.0", "id": i + 1, "method": "programSubscribe", "params": [b58(prog),
                    {"encoding": "base64", "commitment": "processed", "filters": [{"memcmp": {"offset": 0, "bytes": bs58::encode(d).into_string()}}]}]});
                s.send(WsMsg::Text(req.to_string())).await?;
            }
            let mut ping = tokio::time::interval(Duration::from_secs(20));
            loop {
                tokio::select! {
                    _ = ping.tick() => { s.send(WsMsg::Ping(vec![])).await?; }
                    m = s.next() => {
                        let Some(m) = m else { anyhow::bail!("ws closed") };
                        let WsMsg::Text(t) = m? else { continue };
                        let v: Value = match serde_json::from_str(&t) { Ok(v) => v, Err(_) => continue };
                        if v["method"] != "programNotification" { if v.get("error").is_some() { eprintln!("ws prog: {}", t.chars().take(200).collect::<String>()); } continue; }
                        let r = &v["params"]["result"];
                        let slot = r["context"]["slot"].as_u64().unwrap_or(0);
                        let val = &r["value"];
                        let key = val["pubkey"].as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| to_pk(&v));
                        let owner = val["account"]["owner"].as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| to_pk(&v));
                        use base64::Engine;
                        let data = val["account"]["data"][0].as_str().and_then(|s| base64::engine::general_purpose::STANDARD.decode(s).ok());
                        if let (Some(k), Some(o), Some(d)) = (key, owner, data) { c.ws_acct.fetch_add(1, Relaxed); let _ = sink.try_send(Msg::Acct(slot, k, o, d, None)); }
                    }
                }
            }
        }.await;
        if let Err(e) = r { eprintln!("{} ws programs: {e:#}", crate::unix()); }
        tokio::time::sleep(Duration::from_secs(3)).await;
    }
}

/// logsSubscribe per venue program; arbitrage-like signatures go to `out` (deduplicated): (sig, ok)
pub async fn logs(ws: String, progs: Vec<Pk>, venues: HashSet<String>, aggs: HashSet<String>, out: tokio::sync::mpsc::UnboundedSender<(String, bool)>, c: Arc<Counters>) {
    let mut seen: HashSet<String> = HashSet::new();
    let mut seen_q: VecDeque<String> = VecDeque::new();
    let boring: HashSet<&str> = ["ComputeBudget111111111111111111111111111111", "11111111111111111111111111111111", "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", "ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"].into_iter().collect();
    loop {
        let r: anyhow::Result<()> = async {
            let (mut s, _) = tokio_tungstenite::connect_async(&ws).await?;
            for (i, p) in progs.iter().enumerate() {
                let req = json!({"jsonrpc": "2.0", "id": i + 1, "method": "logsSubscribe", "params": [{"mentions": [b58(p)]}, {"commitment": "processed"}]});
                s.send(WsMsg::Text(req.to_string())).await?;
            }
            let mut ping = tokio::time::interval(Duration::from_secs(20));
            loop {
                tokio::select! {
                    _ = ping.tick() => { s.send(WsMsg::Ping(vec![])).await?; }
                    m = s.next() => {
                        let Some(m) = m else { anyhow::bail!("ws closed") };
                        let WsMsg::Text(t) = m? else { continue };
                        let v: Value = match serde_json::from_str(&t) { Ok(v) => v, Err(_) => continue };
                        if v["method"] != "logsNotification" { if v.get("error").is_some() { eprintln!("ws logs: {}", t.chars().take(200).collect::<String>()); } continue; }
                        c.logs.fetch_add(1, Relaxed);
                        let val = &v["params"]["result"]["value"];
                        let Some(sig) = val["signature"].as_str() else { continue };
                        if seen.contains(sig) { continue; }
                        let ok = val["err"].is_null();
                        let mut venue_inv = 0; let mut top: Vec<&str> = vec![]; let mut agg = false;
                        let mut stack: Vec<&str> = vec![];
                        for l in val["logs"].as_array().map(|a| a.as_slice()).unwrap_or(&[]) {
                            let Some(l) = l.as_str() else { continue };
                            let Some(rest) = l.strip_prefix("Program ") else { continue };
                            let Some((p, tail)) = rest.split_once(' ') else { continue };
                            let Some(dstr) = tail.strip_prefix("invoke [") else { continue };
                            let depth: usize = dstr.trim_end_matches(']').parse().unwrap_or(1);
                            stack.truncate(depth.saturating_sub(1));
                            // a venue invoking itself is its event CPI, not a second swap
                            if venues.contains(p) && stack.last() != Some(&p) { venue_inv += 1; }
                            stack.push(p);
                            if aggs.contains(p) { agg = true; }
                            if tail == "invoke [1]" && !boring.contains(p) { top.push(p); }
                        }
                        let bot_top = top.iter().any(|p| !venues.contains(*p));
                        let arb_like = !agg && (venue_inv >= 2 || (!ok && venue_inv == 0 && bot_top));
                        if !arb_like { continue; }
                        seen.insert(sig.to_string()); seen_q.push_back(sig.to_string());
                        while seen_q.len() > 200_000 { if let Some(o) = seen_q.pop_front() { seen.remove(&o); } }
                        if ok { c.arb_like_ok.fetch_add(1, Relaxed); } else { c.arb_like_fail.fetch_add(1, Relaxed); }
                        let _ = out.send((sig.to_string(), ok));
                    }
                }
            }
        }.await;
        if let Err(e) = r { eprintln!("{} ws logs: {e:#}", crate::unix()); }
        tokio::time::sleep(Duration::from_secs(3)).await;
    }
}

/// Rate-capped getTransaction of arbitrage-like signatures (successes first, failures sampled), as `Msg::Tx`.
pub async fn gettx(rpc: String, mut rx: tokio::sync::mpsc::UnboundedReceiver<(String, bool)>, per_sec: u32, sink: crossbeam_channel::Sender<Msg>, c: Arc<Counters>) {
    let cl = reqwest::Client::builder().timeout(Duration::from_secs(20)).build().unwrap();
    let mut q_ok: VecDeque<String> = VecDeque::new();
    let mut q_fail: VecDeque<String> = VecDeque::new();
    let mut tick = tokio::time::interval(Duration::from_millis((1000 / per_sec.max(1)) as u64));
    let sem = Arc::new(tokio::sync::Semaphore::new(8));
    loop {
        tick.tick().await;
        while let Ok((s, ok)) = rx.try_recv() { if ok { q_ok.push_back(s) } else { q_fail.push_back(s) } }
        while q_ok.len() > 400 { q_ok.pop_front(); }
        while q_fail.len() > 100 { q_fail.pop_front(); }
        // wait ~2 s worth of queue so the tx is available; take the newest failures (a uniform-ish sample)
        let (sig, ok) = if let Some(s) = q_ok.pop_front() { (s, true) } else if let Some(s) = q_fail.pop_back() { (s, false) } else { continue };
        let (cl, rpc, sink, c, sem) = (cl.clone(), rpc.clone(), sink.clone(), c.clone(), sem.clone());
        tokio::spawn(async move {
            tokio::time::sleep(Duration::from_millis(3000)).await;
            let _p = sem.acquire().await;
            let body = json!({"jsonrpc": "2.0", "id": 1, "method": "getTransaction", "params": [sig, {"encoding": "json", "maxSupportedTransactionVersion": 1, "commitment": "confirmed"}]});
            for attempt in 0..3 {
                let r = async { cl.post(&rpc).json(&body).send().await?.json::<Value>().await }.await;
                if let Ok(v) = r {
                    if !v["result"].is_null() {
                        if let Some((slot, info)) = to_info(&v["result"]) {
                            if ok { c.fetched_ok.fetch_add(1, Relaxed); } else { c.fetched_fail.fetch_add(1, Relaxed); }
                            let _ = sink.send(Msg::Tx(slot, info));
                        }
                        return;
                    }
                }
                tokio::time::sleep(Duration::from_millis(2500 * (attempt + 1))).await;
            }
        });
    }
}

fn keyv(s: &Value) -> Option<Vec<u8>> { s.as_str().and_then(|s| bs58::decode(s).into_vec().ok()) }
fn ixs(a: &Value) -> Vec<PbIx> {
    a.as_array().map(|v| v.iter().map(|i| PbIx {
        program_id_index: i["programIdIndex"].as_u64().unwrap_or(0) as u32,
        accounts: i["accounts"].as_array().map(|x| x.iter().map(|n| n.as_u64().unwrap_or(0) as u8).collect()).unwrap_or_default(),
        data: i["data"].as_str().and_then(|s| bs58::decode(s).into_vec().ok()).unwrap_or_default(),
    }).collect()).unwrap_or_default()
}
fn tbs(a: &Value) -> Vec<PbTokenBalance> {
    a.as_array().map(|v| v.iter().map(|b| PbTokenBalance {
        account_index: b["accountIndex"].as_u64().unwrap_or(0) as u32, mint: b["mint"].as_str().unwrap_or("").to_string(),
        ui_token_amount: Some(PbUiAmount { amount: b["uiTokenAmount"]["amount"].as_str().unwrap_or("0").to_string() }),
        owner: b["owner"].as_str().unwrap_or("").to_string(),
    }).collect()).unwrap_or_default()
}
fn u64s(a: &Value) -> Vec<u64> { a.as_array().map(|v| v.iter().map(|n| n.as_u64().unwrap_or(0)).collect()).unwrap_or_default() }

/// getTransaction (json) -> the gRPC TxInfo shape the processor reads
pub fn to_info(r: &Value) -> Option<(u64, TxInfo)> {
    let slot = r["slot"].as_u64()?;
    let t = &r["transaction"];
    let m = &t["message"];
    let meta = &r["meta"];
    let sig = keyv(&t["signatures"][0])?;
    let keys: Vec<Vec<u8>> = m["accountKeys"].as_array()?.iter().filter_map(keyv).collect();
    let inner = meta["innerInstructions"].as_array().map(|v| v.iter().map(|i| PbInner { index: i["index"].as_u64().unwrap_or(0) as u32, instructions: ixs(&i["instructions"]) }).collect()).unwrap_or_default();
    let la = &meta["loadedAddresses"];
    let pm = PbMeta {
        err: if meta["err"].is_null() { None } else { Some(PbTxError { err: vec![1] }) },
        fee: meta["fee"].as_u64().unwrap_or(0), pre_balances: u64s(&meta["preBalances"]), post_balances: u64s(&meta["postBalances"]),
        inner_instructions: inner, pre_token_balances: tbs(&meta["preTokenBalances"]), post_token_balances: tbs(&meta["postTokenBalances"]),
        loaded_writable_addresses: la["writable"].as_array().map(|v| v.iter().filter_map(keyv).collect()).unwrap_or_default(),
        loaded_readonly_addresses: la["readonly"].as_array().map(|v| v.iter().filter_map(keyv).collect()).unwrap_or_default(),
    };
    let tx = PbTransaction { signatures: vec![sig.clone()], message: Some(PbMessage { account_keys: keys, instructions: ixs(&m["instructions"]) }) };
    Some((slot, TxInfo { signature: sig, is_vote: false, transaction: Some(tx), meta: Some(pm), index: 0 }))
}

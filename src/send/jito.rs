//! Jito block engine, searcher gRPC (ported from arbed's src/providers/sender/jito-grpc.ts). Hand-written prost
//! messages, field numbers from jito-labs/mev-protos (auth, searcher, bundle, packet), checked byte for byte against
//! jito-ts's encoder in the tests.
//!
//! AUTH: the block engine whitelists one dedicated keypair (never funded, never the trading wallet).
//!   1. GenerateAuthChallenge { role: SEARCHER, pubkey }                 -> challenge
//!   2. sign "<pubkey base58>-<challenge>" with the auth key (Ed25519)
//!   3. GenerateAuthTokens { challenge: that string, pubkey, signature } -> access + refresh token, each with expiry
//!   4. every call carries `authorization: Bearer <access>`; RefreshAccessToken renews it before it expires, and the
//!      full flow runs again once the refresh token itself is near expiry. Every failure is an Err, never a panic.
//!
//! BUNDLES: up to 5 signed transactions, executed in order and atomically. Ours is one transaction (tip inside it).
//! The result stream reports what became of every bundle this key sent; the first result per bundle is kept for the
//! Jito gate (`verdict`), and every result is written to bundles.jsonl.
use crate::feeds::clock::now_ns;
use anyhow::{bail, Context, Result};
use ed25519_dalek::{Signer, SigningKey};
use serde_json::json;
use std::collections::{HashMap, VecDeque};
use std::sync::{Arc, Mutex};
use std::time::Duration;
use tokio::sync::oneshot;
use tonic::codec::ProstCodec;
use tonic::transport::Channel;

pub const MAX_BUNDLE_TXS: usize = 5;
/// renew a token this long before it expires
const RENEW_MARGIN_MS: i64 = 30_000;
/// bundle ids remembered for verdicts and the log
const KEEP: usize = 5_000;
/// our on-chain profit check's error as Jito prints it (nexus-v2 ERR_BASE 0x4e580000 + 2)
pub const PROFIT_CHECK_CODE: &str = "0x4e580002";

// ---------- google.protobuf.Timestamp
#[derive(Clone, PartialEq, prost::Message)]
pub struct Timestamp {
    #[prost(int64, tag = "1")] pub seconds: i64,
    #[prost(int32, tag = "2")] pub nanos: i32,
}

// ---------- auth.proto
pub const ROLE_SEARCHER: i32 = 1;
#[derive(Clone, PartialEq, prost::Message)]
pub struct GenerateAuthChallengeRequest {
    #[prost(int32, tag = "1")] pub role: i32,
    #[prost(bytes = "vec", tag = "2")] pub pubkey: Vec<u8>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct GenerateAuthChallengeResponse { #[prost(string, tag = "1")] pub challenge: String }
#[derive(Clone, PartialEq, prost::Message)]
pub struct GenerateAuthTokensRequest {
    #[prost(string, tag = "1")] pub challenge: String,
    #[prost(bytes = "vec", tag = "2")] pub client_pubkey: Vec<u8>,
    #[prost(bytes = "vec", tag = "3")] pub signed_challenge: Vec<u8>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct Token {
    #[prost(string, tag = "1")] pub value: String,
    #[prost(message, optional, tag = "2")] pub expires_at_utc: Option<Timestamp>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct GenerateAuthTokensResponse {
    #[prost(message, optional, tag = "1")] pub access_token: Option<Token>,
    #[prost(message, optional, tag = "2")] pub refresh_token: Option<Token>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct RefreshAccessTokenRequest { #[prost(string, tag = "1")] pub refresh_token: String }
#[derive(Clone, PartialEq, prost::Message)]
pub struct RefreshAccessTokenResponse { #[prost(message, optional, tag = "1")] pub access_token: Option<Token> }

// ---------- packet.proto, bundle.proto, searcher.proto (only what we send and read)
#[derive(Clone, PartialEq, prost::Message)]
pub struct Meta {
    #[prost(uint64, tag = "1")] pub size: u64,
    #[prost(string, tag = "2")] pub addr: String,
    #[prost(uint32, tag = "3")] pub port: u32,
    #[prost(uint64, tag = "5")] pub sender_stake: u64,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct Packet {
    #[prost(bytes = "vec", tag = "1")] pub data: Vec<u8>,
    #[prost(message, optional, tag = "2")] pub meta: Option<Meta>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct Bundle { #[prost(message, repeated, tag = "3")] pub packets: Vec<Packet> }
#[derive(Clone, PartialEq, prost::Message)]
pub struct SendBundleRequest { #[prost(message, optional, tag = "1")] pub bundle: Option<Bundle> }
#[derive(Clone, PartialEq, prost::Message)]
pub struct SendBundleResponse { #[prost(string, tag = "1")] pub uuid: String }
#[derive(Clone, PartialEq, prost::Message)]
pub struct GetTipAccountsRequest {}
#[derive(Clone, PartialEq, prost::Message)]
pub struct GetTipAccountsResponse { #[prost(string, repeated, tag = "1")] pub accounts: Vec<String> }
#[derive(Clone, PartialEq, prost::Message)]
pub struct SubscribeBundleResultsRequest {}

// BundleResult's `oneof result` and Rejected's `oneof reason` as optional fields: one is set per message
#[derive(Clone, PartialEq, prost::Message)]
pub struct BundleResult {
    #[prost(string, tag = "1")] pub bundle_id: String,
    #[prost(message, optional, tag = "2")] pub accepted: Option<Accepted>,
    #[prost(message, optional, tag = "3")] pub rejected: Option<Rejected>,
    #[prost(message, optional, tag = "4")] pub finalized: Option<Finalized>,
    #[prost(message, optional, tag = "5")] pub processed: Option<Processed>,
    #[prost(message, optional, tag = "6")] pub dropped: Option<Dropped>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct Accepted {
    #[prost(uint64, tag = "1")] pub slot: u64,
    #[prost(string, tag = "2")] pub validator_identity: String,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct Rejected {
    #[prost(message, optional, tag = "1")] pub state_auction_bid_rejected: Option<BidRejected>,
    #[prost(message, optional, tag = "2")] pub winning_batch_bid_rejected: Option<BidRejected>,
    #[prost(message, optional, tag = "3")] pub simulation_failure: Option<SimulationFailure>,
    #[prost(message, optional, tag = "4")] pub internal_error: Option<Msg>,
    #[prost(message, optional, tag = "5")] pub dropped_bundle: Option<Msg>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct BidRejected {
    #[prost(string, tag = "1")] pub auction_id: String,
    #[prost(uint64, tag = "2")] pub simulated_bid_lamports: u64,
    #[prost(string, optional, tag = "3")] pub msg: Option<String>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct SimulationFailure {
    #[prost(string, tag = "1")] pub tx_signature: String,
    #[prost(string, optional, tag = "2")] pub msg: Option<String>,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct Msg { #[prost(string, tag = "1")] pub msg: String }
#[derive(Clone, PartialEq, prost::Message)]
pub struct Finalized {}
#[derive(Clone, PartialEq, prost::Message)]
pub struct Processed {
    #[prost(string, tag = "1")] pub validator_identity: String,
    #[prost(uint64, tag = "2")] pub slot: u64,
    #[prost(uint64, tag = "3")] pub bundle_index: u64,
}
#[derive(Clone, PartialEq, prost::Message)]
pub struct Dropped { #[prost(int32, tag = "1")] pub reason: i32 }

/// What became of one bundle (the answer to "why did we lose"):
///   processed    landed (slot, the bundle's position in the block)
///   accepted     forwarded to a Jito validator, not yet landed
///   lost-auction another bundle bid more for the same state (`bid`: what the winner's simulation paid)
///   would-fail   the block engine's simulation of our transaction failed: the edge was already gone, at no cost
///   dropped / rejected / finalized  as named
#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct Outcome {
    pub bundle: String,
    pub outcome: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")] pub slot: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")] pub index: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")] pub bid: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")] pub detail: Option<String>,
}

pub fn summarize(r: BundleResult) -> Outcome {
    let o = |outcome| Outcome { bundle: r.bundle_id.clone(), outcome, slot: None, index: None, bid: None, detail: None };
    if let Some(p) = &r.processed { return Outcome { slot: Some(p.slot), index: Some(p.bundle_index), ..o("processed") }; }
    if r.finalized.is_some() { return o("finalized"); }
    if let Some(a) = &r.accepted { return Outcome { slot: Some(a.slot), ..o("accepted") }; }
    if let Some(d) = &r.dropped {
        let why = match d.reason { 0 => "blockhash-expired", 1 => "partially-processed", 2 => "not-finalized", _ => "unknown" };
        return Outcome { detail: Some(why.into()), ..o("dropped") };
    }
    let Some(j) = &r.rejected else { return o("rejected") };
    if let Some(b) = j.state_auction_bid_rejected.as_ref().or(j.winning_batch_bid_rejected.as_ref()) {
        return Outcome { bid: Some(b.simulated_bid_lamports), detail: b.msg.clone(), ..o("lost-auction") };
    }
    if let Some(s) = &j.simulation_failure { return Outcome { detail: s.msg.clone(), ..o("would-fail") }; }
    let msg = j.internal_error.as_ref().or(j.dropped_bundle.as_ref()).map(|m| m.msg.clone());
    Outcome { detail: msg, ..o("rejected") }
}

/// The error in a simulation failure, from either of Jito's wordings:
///   "... error=Error processing Instruction 2: custom program error: 0x4e580002]"   /  "... error=Blockhash not found]"
///   "TxnErr(TransactionError { ..., err: InstructionError(2, Custom(1314390018)) })" /  "... err: BlockhashNotFound })"
/// -> the program's code as lower-case hex, "blockhash-not-found", "instruction-error" (no code given) or "other".
pub fn error_code(detail: Option<&str>) -> Option<String> {
    let d = detail?;
    if d.is_empty() { return None; }
    let lower = d.to_ascii_lowercase();
    const HEX: &str = "custom program error: 0x";
    if let Some(i) = lower.find(HEX) {
        let hex: String = lower[i + HEX.len()..].chars().take_while(|c| c.is_ascii_hexdigit()).collect();
        if !hex.is_empty() { return Some(format!("0x{hex}")); }
    }
    for pat in ["Custom(", "\"Custom\":"] {
        if let Some(i) = d.find(pat) {
            let digits: String = d[i + pat.len()..].trim_start().chars().take_while(|c| c.is_ascii_digit()).collect();
            if let Ok(n) = digits.parse::<u64>() { return Some(format!("0x{n:x}")); }
        }
    }
    if lower.contains("blockhashnotfound") || lower.contains("blockhash not found") { return Some("blockhash-not-found".into()); }
    if d.contains("InstructionError") { return Some("instruction-error".into()); }
    Some("other".into())
}

/// The auth keypair from its file: a JSON array of the 64 secret-key bytes, as `solana-keygen` writes it.
pub fn load_keypair(path: &str) -> Result<SigningKey> {
    let path = match path.strip_prefix("~/") { Some(rest) => format!("{}/{rest}", std::env::var("HOME").unwrap_or_default()), None => path.to_string() };
    let text = std::fs::read_to_string(&path).with_context(|| format!("jito auth key {path} (it lives only on the machine that sends bundles)"))?;
    let bytes: Vec<u8> = serde_json::from_str(&text).with_context(|| format!("{path}: not a JSON byte array"))?;
    if bytes.len() != 64 { bail!("{path}: {} bytes, a keypair has 64", bytes.len()); }
    let key = SigningKey::from_bytes(bytes[..32].try_into().unwrap());
    if key.verifying_key().as_bytes()[..] != bytes[32..] { bail!("{path}: the public half does not match the secret half"); }
    Ok(key)
}

#[derive(Default)]
struct Tokens { access: Option<(String, i64)>, refresh: Option<(String, i64)> }

fn token_of(t: Option<Token>) -> Option<(String, i64)> {
    let t = t?;
    let ms = t.expires_at_utc.map_or(0, |e| e.seconds * 1_000 + e.nanos as i64 / 1_000_000);
    if t.value.is_empty() { None } else { Some((t.value, ms)) }
}

fn unix_ms() -> i64 { (now_ns() / 1_000_000) as i64 }

/// First result per bundle, and who is waiting for one (the Jito gate). A result can beat the sendBundle reply.
#[derive(Default)]
struct Verdicts {
    first: HashMap<String, Outcome>,
    waiting: HashMap<String, Vec<oneshot::Sender<Outcome>>>,
    id_of_sig: HashMap<String, String>,
    sig_of_id: HashMap<String, String>,
    order: VecDeque<String>,
}

impl Verdicts {
    fn trim(&mut self) {
        while self.order.len() > KEEP {
            let Some(id) = self.order.pop_front() else { break };
            self.first.remove(&id);
            self.waiting.remove(&id);
            if let Some(sig) = self.sig_of_id.remove(&id) { self.id_of_sig.remove(&sig); }
        }
    }
}

pub struct Jito {
    channel: Channel,
    key: SigningKey,
    tokens: tokio::sync::Mutex<Tokens>,
    verdicts: Mutex<Verdicts>,
    /// bundles.jsonl (core class)
    rec: crate::rec::Rec,
    /// results received, by outcome
    pub counts: Mutex<std::collections::BTreeMap<&'static str, u64>>,
}

impl Jito {
    /// connect (not yet authenticated); `rec` records every bundle result (bundles.jsonl)
    pub async fn connect(url: &str, key: SigningKey, rec: crate::rec::Rec) -> Result<Arc<Jito>> {
        let channel = crate::feeds::grpc::channel(url).await?;
        Ok(Arc::new(Jito { channel, key, tokens: Default::default(), verdicts: Default::default(), rec, counts: Default::default() }))
    }

    pub fn pubkey(&self) -> String { bs58::encode(self.key.verifying_key().as_bytes()).into_string() }

    async fn unary<Req, Resp>(&self, path: &'static str, req: Req, bearer: Option<&str>) -> Result<Resp>
    where Req: prost::Message + Send + Sync + 'static, Resp: prost::Message + Default + Send + Sync + 'static {
        let mut grpc = tonic::client::Grpc::new(self.channel.clone());
        grpc.ready().await.context("block engine not ready")?;
        let mut r = tonic::Request::new(req);
        r.set_timeout(Duration::from_secs(5));
        if let Some(b) = bearer { r.metadata_mut().insert("authorization", format!("Bearer {b}").parse().context("token is not a header value")?); }
        let codec: ProstCodec<Req, Resp> = ProstCodec::default();
        let resp = grpc.unary(r, http::uri::PathAndQuery::from_static(path), codec).await.map_err(|s| anyhow::anyhow!("{path}: {} {}", s.code(), s.message()))?;
        Ok(resp.into_inner())
    }

    /// a valid access token, renewed (refresh, else the full challenge-response) when it nears expiry
    pub async fn token(&self) -> Result<String> {
        let mut t = self.tokens.lock().await;
        let now = unix_ms();
        if let Some((v, exp)) = &t.access { if exp - now > RENEW_MARGIN_MS { return Ok(v.clone()); } }
        if let Some((r, exp)) = t.refresh.clone() {
            if exp - now > RENEW_MARGIN_MS {
                let resp: RefreshAccessTokenResponse = self.unary("/auth.AuthService/RefreshAccessToken", RefreshAccessTokenRequest { refresh_token: r }, None).await?;
                t.access = token_of(resp.access_token);
                return t.access.as_ref().map(|a| a.0.clone()).context("jito auth: no access token in the refresh reply");
            }
        }
        let pubkey = self.key.verifying_key().to_bytes().to_vec();
        let ch: GenerateAuthChallengeResponse = self.unary("/auth.AuthService/GenerateAuthChallenge",
            GenerateAuthChallengeRequest { role: ROLE_SEARCHER, pubkey: pubkey.clone() }, None).await?;
        let signed = format!("{}-{}", self.pubkey(), ch.challenge);
        let sig = self.key.sign(signed.as_bytes()).to_bytes().to_vec();
        let resp: GenerateAuthTokensResponse = self.unary("/auth.AuthService/GenerateAuthTokens",
            GenerateAuthTokensRequest { challenge: signed, client_pubkey: pubkey, signed_challenge: sig }, None).await?;
        t.access = token_of(resp.access_token);
        t.refresh = token_of(resp.refresh_token);
        t.access.as_ref().map(|a| a.0.clone()).context("jito auth: no access token in the reply")
    }

    /// submit signed transactions (wire bytes, v0 or v1 unchanged) as one bundle; returns the block engine's bundle id.
    /// `sig` (base58, the first transaction's) joins the bundle's results to it.
    pub async fn send_bundle(&self, txs: &[&[u8]], sig: &str) -> Result<String> {
        if txs.is_empty() || txs.len() > MAX_BUNDLE_TXS { bail!("jito bundle: 1-{MAX_BUNDLE_TXS} transactions, got {}", txs.len()); }
        let packets = txs.iter().map(|d| Packet { data: d.to_vec(), meta: Some(Meta { size: d.len() as u64, addr: "0.0.0.0".into(), port: 0, sender_stake: 0 }) }).collect();
        let token = self.token().await?;
        let r: SendBundleResponse = self.unary("/searcher.SearcherService/SendBundle", SendBundleRequest { bundle: Some(Bundle { packets }) }, Some(&token)).await?;
        let mut v = self.verdicts.lock().unwrap();
        v.id_of_sig.insert(sig.to_string(), r.uuid.clone());
        v.sig_of_id.insert(r.uuid.clone(), sig.to_string());
        v.order.push_back(r.uuid.clone());
        v.trim();
        Ok(r.uuid)
    }

    /// the tip accounts this block engine accepts
    pub async fn tip_accounts(&self) -> Result<Vec<String>> {
        let token = self.token().await?;
        let r: GetTipAccountsResponse = self.unary("/searcher.SearcherService/GetTipAccounts", GetTipAccountsRequest {}, Some(&token)).await?;
        Ok(r.accounts)
    }

    /// the block engine's FIRST result for the bundle sent with transaction `sig`, or None if none came by `deadline`
    pub async fn verdict(&self, sig: &str, deadline: tokio::time::Instant) -> Option<Outcome> {
        let rx = {
            let mut v = self.verdicts.lock().unwrap();
            let id = v.id_of_sig.get(sig)?.clone();
            if let Some(o) = v.first.get(&id) { return Some(o.clone()); }
            let (tx, rx) = oneshot::channel();
            v.waiting.entry(id).or_default().push(tx);
            rx
        };
        tokio::time::timeout_at(deadline, rx).await.ok()?.ok()
    }

    fn on_result(&self, o: Outcome) {
        *self.counts.lock().unwrap().entry(o.outcome).or_default() += 1;
        let sig = {
            let mut v = self.verdicts.lock().unwrap();
            if !v.first.contains_key(&o.bundle) {
                v.first.insert(o.bundle.clone(), o.clone());
                if !v.sig_of_id.contains_key(&o.bundle) { v.order.push_back(o.bundle.clone()); v.trim(); }
                for w in v.waiting.remove(&o.bundle).unwrap_or_default() { let _ = w.send(o.clone()); }
            }
            v.sig_of_id.get(&o.bundle).cloned()
        };
        if self.rec.is_on() {
            // the line is made and serialized on the recorder's core writer, not on the result stream's task
            let t = now_ns();
            self.rec.emit(crate::rec::BUNDLES, crate::rec::Record::enc(move |w| {
                let code = if o.outcome == "would-fail" { error_code(o.detail.as_deref()) } else { None };
                let mut line = serde_json::to_value(&o).unwrap_or_default();
                line["t_ns"] = json!(t);
                line["sig"] = json!(sig);
                line["code"] = json!(code);
                let _ = serde_json::to_writer(w, &line);
            }));
        }
    }

    /// Follow the result of every bundle this key sends, until `stop`; the stream reopens by itself when it ends.
    pub async fn follow_results(self: Arc<Self>, stop: Arc<std::sync::atomic::AtomicBool>, status: impl Fn(String) + Send + Sync) {
        let mut first = true;
        while !stop.load(std::sync::atomic::Ordering::Relaxed) {
            let r = async {
                let token = self.token().await?;
                let mut grpc = tonic::client::Grpc::new(self.channel.clone());
                grpc.ready().await.context("block engine not ready")?;
                let mut req = tonic::Request::new(SubscribeBundleResultsRequest {});
                req.metadata_mut().insert("authorization", format!("Bearer {token}").parse().context("token")?);
                let codec: ProstCodec<SubscribeBundleResultsRequest, BundleResult> = ProstCodec::default();
                let path = http::uri::PathAndQuery::from_static("/searcher.SearcherService/SubscribeBundleResults");
                let mut st = grpc.server_streaming(req, path, codec).await?.into_inner();
                status(format!("jito results: stream {}", if first { "open" } else { "reopened" }));
                first = false;
                while let Some(m) = st.message().await? {
                    self.on_result(summarize(m));
                    if stop.load(std::sync::atomic::Ordering::Relaxed) { return Ok(()); }
                }
                anyhow::Ok(())
            }.await;
            if stop.load(std::sync::atomic::Ordering::Relaxed) { break; }
            if let Err(e) = r { status(format!("jito results: {e:#}; reopening")); }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use prost::Message;

    fn hex(s: &str) -> Vec<u8> { (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).unwrap()).collect() }

    // vectors from jito-ts 4.2.1's own encoder (arbed's node_modules), so the field numbers are Jito's
    #[test]
    fn encodes_like_jito_ts() {
        let d = [1u8, 2, 3, 250];
        let req = SendBundleRequest { bundle: Some(Bundle { packets: vec![Packet { data: d.to_vec(), meta: Some(Meta { size: 4, addr: "0.0.0.0".into(), port: 0, sender_stake: 0 }) }] }) };
        assert_eq!(req.encode_to_vec(), hex("0a151a130a04010203fa120b08041207302e302e302e30"));
        assert_eq!(GenerateAuthChallengeRequest { role: ROLE_SEARCHER, pubkey: vec![7; 32] }.encode_to_vec(),
            hex("080112200707070707070707070707070707070707070707070707070707070707070707"));
        let t = GenerateAuthTokensRequest { challenge: "abc-xyz".into(), client_pubkey: vec![7; 32], signed_challenge: vec![9; 64] }.encode_to_vec();
        assert_eq!(t, hex(&format!("0a076162632d78797a1220{}1a40{}", "07".repeat(32), "09".repeat(64))));
        assert_eq!(RefreshAccessTokenRequest { refresh_token: "ref".into() }.encode_to_vec(), hex("0a03726566"));
    }

    #[test]
    fn decodes_like_jito_ts() {
        let r = GenerateAuthTokensResponse::decode(&hex("0a130a03616363120c0880f7c4d5061080cab5ee01120d0a03726566120608809acad506")[..]).unwrap();
        assert_eq!(token_of(r.access_token), Some(("acc".into(), 1_790_000_000_500)));
        assert_eq!(token_of(r.refresh_token), Some(("ref".into(), 1_790_086_400_000)));
        let tips = GetTipAccountsResponse::decode(&hex("0a2c393667595a474c6e4a5956466d626a7a6f705053553651694556356647715a4e794e396e6d4e6876725a55350a2c4846715535783633565471765173733868703131693477565638624434345076777563665a32625537675265")[..]).unwrap();
        assert_eq!(tips.accounts, vec!["96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5", "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe"]);
        let s = |h: &str| summarize(BundleResult::decode(&hex(h)[..]).unwrap());
        let p = s("0a0262312a0a0a017610959aef3a1803");
        assert_eq!((p.outcome, p.slot, p.index), ("processed", Some(123_456_789), Some(3)));
        let a = s("0a0262321205082a120176");
        assert_eq!((a.outcome, a.slot), ("accepted", Some(42)));
        let f = s("0a0262331a271a250a01731220637573746f6d2070726f6772616d206572726f723a2030783465353830303032");
        assert_eq!((f.outcome, f.detail.as_deref()), ("would-fail", Some("custom program error: 0x4e580002")));
        let l = s("0a0262341a100a0e0a01611098751a066f7574626964");
        assert_eq!((l.outcome, l.bid, l.detail.as_deref()), ("lost-auction", Some(15_000), Some("outbid")));
        let b = s("0a0262351a0f120d0a016110a8461a056261746368");
        assert_eq!((b.outcome, b.bid), ("lost-auction", Some(9_000)));
        let d = s("0a02623632020801");
        assert_eq!((d.outcome, d.detail.as_deref()), ("dropped", Some("partially-processed")));
        assert_eq!(s("0a0262372200").outcome, "finalized");
        let i = s("0a0262381a0822060a04626f6f6d");
        assert_eq!((i.outcome, i.detail.as_deref(), i.bundle.as_str()), ("rejected", Some("boom"), "b8"));
    }

    // run #27's real block-engine messages (arbed test/unit/execution/jito-gate.test.ts)
    const PROFIT: &str = "A transaction in the bundle failed to execute: [signature=48W3rni7ctk5ZhLbeLJNxi1T9E4SPHKdmJceiFYymAFeYfDXVHj2bD5UMunXFRvmS5TCbwtTTWi7G8iSBZnuqrQB, error=Error processing Instruction 2: custom program error: 0x4e580002]";
    const VENUE: &str = "A transaction in the bundle failed to execute: [signature=48W3rni7ctk5ZhLbeLJNxi1T9E4SPHKdmJceiFYymAFeYfDXVHj2bD5UMunXFRvmS5TCbwtTTWi7G8iSBZnuqrQB, error=Error processing Instruction 3: custom program error: 0x1783]";

    #[test]
    fn reads_both_error_wordings() {
        assert!(PROFIT.len() > 200);
        assert_eq!(error_code(Some(PROFIT)).as_deref(), Some(PROFIT_CHECK_CODE));
        assert_eq!(error_code(Some(VENUE)).as_deref(), Some("0x1783"));
        assert_eq!(error_code(Some("TxnErr(TransactionError { err: InstructionError(2, Custom(1314390018)) })")).as_deref(), Some(PROFIT_CHECK_CODE));
        assert_eq!(error_code(Some("TxnErr(TransactionError { txn_signature: \"67Uh\", err: BlockhashNotFound })")).as_deref(), Some("blockhash-not-found"));
        assert_eq!(error_code(Some("A transaction in the bundle failed to execute: [signature=34bf, error=Blockhash not found]")).as_deref(), Some("blockhash-not-found"));
        assert_eq!(error_code(Some("TxnErr(TransactionError { txn_signature: \"2oSr\", err: InstructionError })")).as_deref(), Some("instruction-error"));
        assert_eq!(error_code(Some("something else")).as_deref(), Some("other"));
        assert_eq!(error_code(None), None);
    }

    #[test]
    fn auth_signature_verifies() {
        use ed25519_dalek::Verifier;
        let key = SigningKey::from_bytes(&[42u8; 32]);
        let msg = format!("{}-challenge", bs58::encode(key.verifying_key().as_bytes()).into_string());
        let sig = key.sign(msg.as_bytes());
        assert!(key.verifying_key().verify(msg.as_bytes(), &sig).is_ok());
    }

    #[test]
    fn loads_a_solana_keygen_file() {
        let key = SigningKey::from_bytes(&[5u8; 32]);
        let mut bytes = key.to_bytes().to_vec();
        bytes.extend_from_slice(key.verifying_key().as_bytes());
        let dir = std::env::temp_dir().join(format!("arb-lab-key-{}", std::process::id()));
        std::fs::write(&dir, serde_json::to_string(&bytes).unwrap()).unwrap();
        assert_eq!(load_keypair(dir.to_str().unwrap()).unwrap().to_bytes(), key.to_bytes());
        bytes[40] ^= 1;
        std::fs::write(&dir, serde_json::to_string(&bytes).unwrap()).unwrap();
        assert!(load_keypair(dir.to_str().unwrap()).is_err(), "mismatched public half");
        let _ = std::fs::remove_file(&dir);
    }

    #[tokio::test]
    async fn verdict_sees_a_result_that_beat_the_send_reply() {
        let v = Mutex::new(Verdicts::default());
        // the result arrives first, then the bundle id is learned
        {
            let mut g = v.lock().unwrap();
            g.first.insert("id1".into(), Outcome { bundle: "id1".into(), outcome: "would-fail", slot: None, index: None, bid: None, detail: None });
            g.id_of_sig.insert("sig1".into(), "id1".into());
        }
        let g = v.lock().unwrap();
        let id = g.id_of_sig.get("sig1").unwrap();
        assert_eq!(g.first.get(id).unwrap().outcome, "would-fail");
    }

    /// review F12: bundles.jsonl as `on_result` writes it through the recorder (the line is made on the core writer):
    /// the outcome's fields, `t_ns`, the signature when known and a would-fail's decoded error code
    #[tokio::test]
    async fn bundle_results_are_recorded() {
        let d = std::env::temp_dir().join(format!("arbx-jito-rec-{}-{}", std::process::id(), now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        let channel = tonic::transport::Endpoint::from_static("http://127.0.0.1:9").connect_lazy();
        let j = Jito { channel, key: SigningKey::from_bytes(&[1u8; 32]), tokens: Default::default(), verdicts: Default::default(), rec: rec.clone(), counts: Default::default() };
        j.verdicts.lock().unwrap().sig_of_id.insert("b1".into(), "sigA".into());
        j.on_result(Outcome { bundle: "b1".into(), outcome: "would-fail", slot: None, index: None, bid: None, detail: Some(PROFIT.into()) });
        j.on_result(Outcome { bundle: "b2".into(), outcome: "processed", slot: Some(7), index: Some(1), bid: None, detail: None });
        rec.close();
        let v = crate::rec::read_jsonl(&d, "bundles").unwrap();
        assert_eq!(v.len(), 2);
        assert_eq!((v[0]["bundle"].as_str(), v[0]["outcome"].as_str(), v[0]["sig"].as_str(), v[0]["code"].as_str()), (Some("b1"), Some("would-fail"), Some("sigA"), Some(PROFIT_CHECK_CODE)));
        assert!(v[0]["t_ns"].as_u64().unwrap() > 0 && v[0]["detail"].as_str().unwrap().starts_with("A transaction"));
        assert_eq!((v[1]["slot"].as_u64(), v[1]["index"].as_u64(), v[1]["sig"].is_null(), v[1]["code"].is_null()), (Some(7), Some(1), true, true));
        assert_eq!(*j.counts.lock().unwrap(), [("processed", 1), ("would-fail", 1)].into_iter().collect());
        let _ = std::fs::remove_dir_all(&d);
    }
}

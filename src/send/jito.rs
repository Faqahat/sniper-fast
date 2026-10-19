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
//! The result stream reports what became of every bundle this key sent. PLAN WP-05 item 7: every result is kept per
//! bundle, in order, with its time (`verdicts`), and written to bundles.jsonl (v2: its sequence number, the validator,
//! the attempt, the stream's connection number); outages of the stream are `jito_stream_down` / `jito_stream_up`
//! events, so missing verdicts are explainable. A `processed` result of ours names its bundle to the transfer
//! classification (`classify::note_bundle_processed`) and the wallet's source (c) (`chainfetch::note_jito_processed`);
//! every result of ours goes to the executor's sink (token cooling; a landing releases the in-flight entry).
//!
//! SENDBUNDLE ERRORS (review WP-05 #7): a gRPC status the block engine answers with that refuses the bundle (invalid,
//! over the rate, not authorised, ...) is `BundleError::Refused`: it cannot land. Anything else (a transport error,
//! a timeout, `unavailable`, `internal`, ...) may have reached the block engine: `BundleError::Other`, and the executor
//! keeps the attempt open until it lands or its blockhash expires.
//!
//! TOKEN (PLAN WP-05 item 2, F28): the send path never refreshes the auth token. `keep_token` (a background task)
//! renews it at half its lifetime; `send_bundle` only reads the cached token and refuses with `jito_auth_stale` when it
//! has expired. Every unary call but SendBundle counts as a network call (`netcount`).
use crate::feeds::clock::now_ns;
use anyhow::{bail, Context, Result};
use ed25519_dalek::{Signer, SigningKey};
use serde_json::json;
use std::collections::{HashMap, VecDeque};
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::Duration;
use tonic::codec::ProstCodec;
use tonic::transport::Channel;

pub const MAX_BUNDLE_TXS: usize = 5;
/// renew a token this long before it expires (a caller that may refresh: the keep-alive, the result stream)
const RENEW_MARGIN_MS: i64 = 30_000;
/// the send path uses the cached access token only while it has at least this much life left
pub const SEND_MIN_LEFT_MS: i64 = 5_000;
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
    /// the bundle's position in its block (`processed`)
    #[serde(skip_serializing_if = "Option::is_none")] pub index: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")] pub bid: Option<u64>,
    #[serde(skip_serializing_if = "Option::is_none")] pub detail: Option<String>,
    /// the validator `accepted` / `processed` name (PLAN WP-05 item 7)
    #[serde(skip_serializing_if = "Option::is_none")] pub validator: Option<String>,
}

impl Outcome {
    /// The block engine reports a landing (`processed`, `finalized`): the state the attempt priced is spent, its
    /// in-flight entry may go (review WP-05 #2). Every other result is not final: `accepted` may still land, and a
    /// `would-fail`, `lost-auction`, `dropped` or `rejected` says the state does not pay or did not get in, which keeps
    /// the entry for its hold (the same state is not sent again to the same leader). An attempt is final at its landing
    /// or its blockhash's expiry (PLAN WP-07)
    pub fn is_final(&self) -> bool { matches!(self.outcome, "processed" | "finalized") }
}

pub fn summarize(r: BundleResult) -> Outcome {
    let o = |outcome| Outcome { bundle: r.bundle_id.clone(), outcome, slot: None, index: None, bid: None, detail: None, validator: None };
    let v = |s: &str| (!s.is_empty()).then(|| s.to_string());
    if let Some(p) = &r.processed { return Outcome { slot: Some(p.slot), index: Some(p.bundle_index), validator: v(&p.validator_identity), ..o("processed") }; }
    if r.finalized.is_some() { return o("finalized"); }
    if let Some(a) = &r.accepted { return Outcome { slot: Some(a.slot), validator: v(&a.validator_identity), ..o("accepted") }; }
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

/// where the block engine's auth keypair lives unless `auth_keypair` says otherwise (never the trading wallet)
pub const DEFAULT_AUTH_KEYPAIR: &str = "~/.nexus-v2-jito-auth.json";

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

/// the access token the send path reads: its value, expiry and when it was obtained (unix ms)
#[derive(Clone, Debug, PartialEq)]
pub struct CachedToken { pub value: String, pub exp_ms: i64, pub issued_ms: i64 }

/// what the send check sees of the token (status `health.jito_token_age_s_now`)
#[derive(Clone, Copy, Debug, PartialEq)]
pub enum TokenState { Valid { age_s: u64, left_s: i64 }, Stale }

/// why `send_bundle` did not send: no valid cached token (nothing left); the block engine answered with a refusal (it
/// cannot land); anything else (it may have reached the block engine)
#[derive(Debug)]
pub enum BundleError { AuthStale, Refused(anyhow::Error), Other(anyhow::Error) }
impl std::fmt::Display for BundleError {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result {
        match self {
            BundleError::AuthStale => f.write_str("jito_auth_stale: no valid cached auth token (the send path never refreshes it)"),
            BundleError::Refused(e) | BundleError::Other(e) => write!(f, "{e:#}"),
        }
    }
}

/// a unary call's gRPC status (the block engine's answer, or tonic's own for a transport failure or a timeout)
#[derive(Debug)]
pub struct GrpcStatus { pub code: tonic::Code, pub msg: String }
impl std::fmt::Display for GrpcStatus { fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result { f.write_str(&self.msg) } }
impl std::error::Error for GrpcStatus {}

/// A status the block engine answers a SendBundle with when it does not take the bundle (review WP-05 #7). Not:
/// `cancelled` / `deadline_exceeded` (a timeout), `unavailable` / `unknown` / `internal` / `data_loss` / `aborted` (also
/// what tonic reports for a transport failure after the request may have left) and `already_exists` (the bundle is
/// in): those may land
pub fn refused_code(c: tonic::Code) -> bool {
    use tonic::Code::*;
    matches!(c, InvalidArgument | ResourceExhausted | PermissionDenied | Unauthenticated | FailedPrecondition | OutOfRange | Unimplemented | NotFound)
}

/// The result stream's outages: one `jito_stream_down` at an outage's first error, one `jito_stream_up` (with how long
/// results could not arrive) when a stream opens again (PLAN WP-05 item 7)
#[derive(Default)]
struct Outage { down_since: Option<u64> }

impl Outage {
    /// a stream opened (connection `epoch`) at `now`: the `jito_stream_up` event's body, if an outage ends
    fn opened(&mut self, epoch: u64, now: u64) -> Option<serde_json::Value> {
        self.down_since.take().map(|d| json!({ "stream_epoch": epoch, "down_ms": now.saturating_sub(d) / 1_000_000 }))
    }
    /// the stream failed or ended (`why`) at `now`: the `jito_stream_down` event's body, if an outage starts
    fn failed(&mut self, epoch: u64, why: &str, now: u64) -> Option<serde_json::Value> {
        if self.down_since.is_some() { return None; }
        self.down_since = Some(now);
        Some(json!({ "stream_epoch": epoch, "error": why }))
    }
}

/// one result of a bundle of ours, as the sink gets it
#[derive(Clone, Debug)]
pub struct ResultNote { pub sig: String, pub bundle: String, pub outcome: Outcome, pub seq: u32, pub t_ns: u64, pub attempt: Option<u64> }

pub type Sink = Box<dyn Fn(ResultNote) + Send + Sync>;

fn token_of(t: Option<Token>) -> Option<(String, i64)> {
    let t = t?;
    let ms = t.expires_at_utc.map_or(0, |e| e.seconds * 1_000 + e.nanos as i64 / 1_000_000);
    if t.value.is_empty() { None } else { Some((t.value, ms)) }
}

fn unix_ms() -> i64 { (now_ns() / 1_000_000) as i64 }

/// Every result per bundle, in order with its time (PLAN WP-05 item 7: `Verdicts.first` became `all`), and the bundle
/// of each of our transactions. A result can beat the sendBundle reply: it is kept under its bundle id and matched
/// when the reply names the bundle
#[derive(Default)]
struct Verdicts {
    all: HashMap<String, Vec<(u64, Outcome)>>,
    id_of_sig: HashMap<String, String>,
    sig_of_id: HashMap<String, String>,
    attempt_of_id: HashMap<String, u64>,
    order: VecDeque<String>,
}

impl Verdicts {
    fn trim(&mut self) {
        while self.order.len() > KEEP {
            let Some(id) = self.order.pop_front() else { break };
            self.all.remove(&id);
            self.attempt_of_id.remove(&id);
            if let Some(sig) = self.sig_of_id.remove(&id) { self.id_of_sig.remove(&sig); }
        }
    }
}

pub struct Jito {
    channel: Channel,
    key: SigningKey,
    tokens: tokio::sync::Mutex<Tokens>,
    /// the access token as the send path reads it (no await, no network)
    cached: Mutex<Option<CachedToken>>,
    verdicts: Mutex<Verdicts>,
    /// bundles.jsonl (core class)
    rec: crate::rec::Rec,
    /// results received, by outcome
    pub counts: Mutex<std::collections::BTreeMap<&'static str, u64>>,
    /// the result stream's connection number (bundles.jsonl `stream_epoch`)
    epoch: AtomicU64,
    /// the executor's sink for our bundles' results
    sink: OnceLock<Sink>,
    /// tests: a block engine in memory that takes (or refuses) the bundle (the real SendBundle call is not made)
    fake: OnceLock<Arc<FakeEngine>>,
    /// tests: the token renewal (`renew`) without the network
    #[cfg(test)]
    fake_renew: OnceLock<Arc<dyn Fn() -> Result<CachedToken> + Send + Sync>>,
}

/// tests: an in-memory block engine's answer to a bundle
pub(crate) type FakeEngine = dyn Fn(&[&[u8]]) -> std::result::Result<String, BundleError> + Send + Sync;

impl Jito {
    /// connect (not yet authenticated); `rec` records every bundle result (bundles.jsonl)
    pub async fn connect(url: &str, key: SigningKey, rec: crate::rec::Rec) -> Result<Arc<Jito>> {
        let channel = crate::feeds::grpc::channel(url).await?;
        Ok(Arc::new(Jito::with_channel(channel, key, rec)))
    }

    fn with_channel(channel: Channel, key: SigningKey, rec: crate::rec::Rec) -> Jito {
        Jito { channel, key, tokens: Default::default(), cached: Default::default(), verdicts: Default::default(), rec, counts: Default::default(),
            epoch: AtomicU64::new(0), sink: OnceLock::new(), fake: OnceLock::new(), #[cfg(test)] fake_renew: OnceLock::new() }
    }

    /// tests: a client whose channel goes nowhere (127.0.0.1:9, connected lazily)
    #[cfg(test)]
    pub fn for_test(rec: crate::rec::Rec) -> Arc<Jito> {
        let channel = tonic::transport::Endpoint::from_static("http://127.0.0.1:9").connect_lazy();
        Arc::new(Jito::with_channel(channel, SigningKey::from_bytes(&[1u8; 32]), rec))
    }

    /// tests: the cached token as given
    #[cfg(test)]
    pub fn set_cached(&self, t: Option<CachedToken>) { *self.cached.lock().unwrap() = t; }

    /// tests: bundles go to `f` (an in-memory block engine) instead of SendBundle; `f` returns the bundle id
    #[cfg(test)]
    pub fn set_fake(&self, f: Arc<dyn Fn(&[&[u8]]) -> String + Send + Sync>) { let _ = self.fake.set(Arc::new(move |t: &[&[u8]]| Ok(f(t)))); }

    /// tests: as `set_fake`, the block engine may refuse (`BundleError::Refused`) or not answer (`Other`)
    #[cfg(test)]
    pub fn set_fake_result(&self, f: Arc<FakeEngine>) { let _ = self.fake.set(f); }

    /// tests: `renew` asks `f` instead of the block engine
    #[cfg(test)]
    pub fn set_fake_renew(&self, f: Arc<dyn Fn() -> Result<CachedToken> + Send + Sync>) { let _ = self.fake_renew.set(f); }

    /// the executor's sink for every result of our bundles (once)
    pub fn set_sink(&self, f: Sink) { let _ = self.sink.set(f); }

    pub fn pubkey(&self) -> String { bs58::encode(self.key.verifying_key().as_bytes()).into_string() }
    pub fn verifying_key(&self) -> [u8; 32] { self.key.verifying_key().to_bytes() }

    async fn unary<Req, Resp>(&self, path: &'static str, req: Req, bearer: Option<&str>) -> Result<Resp>
    where Req: prost::Message + Send + Sync + 'static, Resp: prost::Message + Default + Send + Sync + 'static {
        // a network call (F28): every unary call but SendBundle, which is the send itself
        if path != SEND_BUNDLE { crate::netcount::note(); }
        let mut grpc = tonic::client::Grpc::new(self.channel.clone());
        grpc.ready().await.context("block engine not ready")?;
        let mut r = tonic::Request::new(req);
        r.set_timeout(Duration::from_secs(5));
        if let Some(b) = bearer { r.metadata_mut().insert("authorization", format!("Bearer {b}").parse().context("token is not a header value")?); }
        let codec: ProstCodec<Req, Resp> = ProstCodec::default();
        let resp = grpc.unary(r, http::uri::PathAndQuery::from_static(path), codec).await
            .map_err(|s| anyhow::Error::new(GrpcStatus { code: s.code(), msg: format!("{path}: {} {}", s.code(), s.message()) }))?;
        Ok(resp.into_inner())
    }

    /// a valid access token, renewed (refresh, else the full challenge-response) when it nears expiry. Never on the send
    /// path: the keep-alive, the result stream, the background refresher and the start use it
    pub async fn token(&self) -> Result<String> { self.renew(false).await.map(|x| x.0) }

    /// `token`, or (`force`) a new access token whatever the old one's life: (token, how: `cached`, `refresh`,
    /// `challenge`)
    async fn renew(&self, force: bool) -> Result<(String, &'static str)> {
        #[cfg(test)]
        if let Some(f) = self.fake_renew.get() {
            let c = f()?;
            *self.cached.lock().unwrap() = Some(c.clone());
            return Ok((c.value, "fake"));
        }
        let mut t = self.tokens.lock().await;
        let now = unix_ms();
        if !force { if let Some((v, exp)) = &t.access { if exp - now > RENEW_MARGIN_MS { return Ok((v.clone(), "cached")); } } }
        let (access, how) = 'got: {
            if let Some((r, exp)) = t.refresh.clone() {
                if exp - now > RENEW_MARGIN_MS {
                    let resp: RefreshAccessTokenResponse = self.unary("/auth.AuthService/RefreshAccessToken", RefreshAccessTokenRequest { refresh_token: r }, None).await?;
                    break 'got (token_of(resp.access_token), "refresh");
                }
            }
            let pubkey = self.key.verifying_key().to_bytes().to_vec();
            let ch: GenerateAuthChallengeResponse = self.unary("/auth.AuthService/GenerateAuthChallenge",
                GenerateAuthChallengeRequest { role: ROLE_SEARCHER, pubkey: pubkey.clone() }, None).await?;
            let signed = format!("{}-{}", self.pubkey(), ch.challenge);
            let sig = self.key.sign(signed.as_bytes()).to_bytes().to_vec();
            let resp: GenerateAuthTokensResponse = self.unary("/auth.AuthService/GenerateAuthTokens",
                GenerateAuthTokensRequest { challenge: signed, client_pubkey: pubkey, signed_challenge: sig }, None).await?;
            t.refresh = token_of(resp.refresh_token);
            (token_of(resp.access_token), "challenge")
        };
        t.access = access;
        let (v, exp) = t.access.clone().context("jito auth: no access token in the reply")?;
        *self.cached.lock().unwrap() = Some(CachedToken { value: v.clone(), exp_ms: exp, issued_ms: now });
        Ok((v, how))
    }

    /// the cached access token with at least `SEND_MIN_LEFT_MS` of life at `now_ms` (the send path: no network)
    pub fn cached_token(&self, now_ms: i64) -> Option<String> {
        self.cached.lock().unwrap().as_ref().filter(|c| c.exp_ms - now_ms > SEND_MIN_LEFT_MS).map(|c| c.value.clone())
    }

    /// what the send check sees of the token at `now_ms`
    pub fn token_state(&self, now_ms: i64) -> TokenState {
        match self.cached.lock().unwrap().as_ref() {
            Some(c) if c.exp_ms - now_ms > SEND_MIN_LEFT_MS => TokenState::Valid { age_s: (now_ms.saturating_sub(c.issued_ms).max(0) / 1_000) as u64, left_s: (c.exp_ms - now_ms) / 1_000 },
            _ => TokenState::Stale,
        }
    }

    /// When the cached token is due for renewal (unix ms): half its lifetime after it was obtained; now when none
    pub fn renew_due_ms(&self, now_ms: i64) -> i64 {
        self.cached.lock().unwrap().as_ref().map_or(now_ms, |c| c.issued_ms + (c.exp_ms - c.issued_ms).max(0) / 2)
    }

    /// The background refresher (PLAN WP-05 item 2, F28): renews the access token at half its lifetime, so the send path
    /// always finds a valid one cached; a failure is retried after 1 s, doubling to 30 s. Each renewal is an
    /// events.jsonl `jito_token_refresh`. Until `stop`
    pub async fn keep_token(self: Arc<Self>, stop: Arc<std::sync::atomic::AtomicBool>) {
        let mut backoff = Duration::from_secs(1);
        while !stop.load(Relaxed) {
            let now = unix_ms();
            let due = self.renew_due_ms(now);
            if now >= due {
                match self.renew(true).await {
                    Ok((_, how)) => {
                        backoff = Duration::from_secs(1);
                        let left = self.cached.lock().unwrap().as_ref().map(|c| (c.exp_ms - unix_ms()) / 1_000);
                        self.rec.event("jito_token_refresh", "jito", None, json!({ "ok": true, "via": how, "expires_in_s": left }));
                    }
                    Err(e) => {
                        self.rec.event("jito_token_refresh", "jito", None, json!({ "ok": false, "error": crate::rpc::scrub(&format!("{e:#}")),
                            "retry_s": backoff.as_secs(), "stale": self.cached_token(unix_ms()).is_none() }));
                        tokio::time::sleep(backoff).await;
                        backoff = (backoff * 2).min(Duration::from_secs(30));
                        continue;
                    }
                }
            }
            let wait = (self.renew_due_ms(unix_ms()) - unix_ms()).clamp(50, 5_000) as u64;
            tokio::time::sleep(Duration::from_millis(wait)).await;
        }
    }

    /// Submit signed transactions (wire bytes, v0 or v1 unchanged) as one bundle; returns the block engine's bundle id.
    /// `sig` (base58, the first transaction's) and `attempt` join the bundle's results to it. The cached token only
    /// (F28): an expired one refuses at once (`BundleError::AuthStale`), nothing goes over the network
    pub async fn send_bundle(&self, txs: &[&[u8]], sig: &str, attempt: Option<u64>) -> std::result::Result<String, BundleError> {
        if txs.is_empty() || txs.len() > MAX_BUNDLE_TXS { return Err(BundleError::Other(anyhow::anyhow!("jito bundle: 1-{MAX_BUNDLE_TXS} transactions, got {}", txs.len()))); }
        let token = self.cached_token(unix_ms()).ok_or(BundleError::AuthStale)?;
        let uuid = match self.fake.get() {
            Some(f) => f(txs)?,
            None => {
                let packets = txs.iter().map(|d| Packet { data: d.to_vec(), meta: Some(Meta { size: d.len() as u64, addr: "0.0.0.0".into(), port: 0, sender_stake: 0 }) }).collect();
                let r: SendBundleResponse = self.unary(SEND_BUNDLE, SendBundleRequest { bundle: Some(Bundle { packets }) }, Some(&token)).await
                    .map_err(|e| if e.downcast_ref::<GrpcStatus>().is_some_and(|s| refused_code(s.code)) { BundleError::Refused(e) } else { BundleError::Other(e) })?;
                r.uuid
            }
        };
        // results that came before this reply (kept under the id) are matched now
        let early: Vec<(u64, Outcome)> = {
            let mut v = self.verdicts.lock().unwrap();
            v.id_of_sig.insert(sig.to_string(), uuid.clone());
            v.sig_of_id.insert(uuid.clone(), sig.to_string());
            if let Some(a) = attempt { v.attempt_of_id.insert(uuid.clone(), a); }
            let early = v.all.get(&uuid).cloned().unwrap_or_default();
            if early.is_empty() { v.order.push_back(uuid.clone()); v.trim(); }
            early
        };
        for (k, (t, o)) in early.into_iter().enumerate() { self.ours(sig, &o, k as u32, t, attempt); }
        Ok(uuid)
    }

    /// FAST (snipe_engine --fast-send): a bundle written outside `send_bundle` (raw HTTP/2 on our own connection): record
    /// its id exactly as `send_bundle` does, so the result stream joins to it
    pub fn note_bundle(&self, sig: &str, uuid: &str) {
        let uuid = uuid.to_string();
        let early: Vec<(u64, Outcome)> = {
            let mut v = self.verdicts.lock().unwrap();
            v.id_of_sig.insert(sig.to_string(), uuid.clone());
            v.sig_of_id.insert(uuid.clone(), sig.to_string());
            let early = v.all.get(&uuid).cloned().unwrap_or_default();
            if early.is_empty() { v.order.push_back(uuid.clone()); v.trim(); }
            early
        };
        for (k, (t, o)) in early.into_iter().enumerate() { self.ours(sig, &o, k as u32, t, None); }
    }

    /// every result so far of the bundle sent with transaction `sig`, in order, with its receipt time
    pub fn verdicts(&self, sig: &str) -> Vec<(u64, Outcome)> {
        let v = self.verdicts.lock().unwrap();
        v.id_of_sig.get(sig).and_then(|id| v.all.get(id)).cloned().unwrap_or_default()
    }

    /// the bundle id the block engine gave the bundle with transaction `sig`
    pub fn bundle_of(&self, sig: &str) -> Option<String> { self.verdicts.lock().unwrap().id_of_sig.get(sig).cloned() }

    /// the result stream's connection number
    pub fn stream_epoch(&self) -> u64 { self.epoch.load(Relaxed) }

    /// the tip accounts this block engine accepts
    pub async fn tip_accounts(&self) -> Result<Vec<String>> {
        let token = self.token().await?;
        let r: GetTipAccountsResponse = self.unary("/searcher.SearcherService/GetTipAccounts", GetTipAccountsRequest {}, Some(&token)).await?;
        Ok(r.accounts)
    }

    /// One result from the stream: counted, kept in order under its bundle, written to bundles.jsonl (v2), and, for a
    /// bundle of ours, handed on (`ours`)
    fn on_result(&self, o: Outcome) { self.on_result_at(o, now_ns()); }

    pub(crate) fn on_result_at(&self, o: Outcome, t: u64) {
        *self.counts.lock().unwrap().entry(o.outcome).or_default() += 1;
        let (seq, sig, attempt) = {
            let mut v = self.verdicts.lock().unwrap();
            let known = v.sig_of_id.contains_key(&o.bundle);
            let list = v.all.entry(o.bundle.clone()).or_default();
            let seq = list.len() as u32;
            list.push((t, o.clone()));
            if !known && seq == 0 { v.order.push_back(o.bundle.clone()); v.trim(); }
            (seq, v.sig_of_id.get(&o.bundle).cloned(), v.attempt_of_id.get(&o.bundle).copied())
        };
        if let Some(sig) = &sig { self.ours(sig, &o, seq, t, attempt); }
        if self.rec.is_on() {
            // the line is made and serialized on the recorder's core writer, not on the result stream's task
            let epoch = self.epoch.load(Relaxed);
            self.rec.emit(crate::rec::BUNDLES, crate::rec::Record::enc(move |w| {
                let code = if o.outcome == "would-fail" { error_code(o.detail.as_deref()) } else { None };
                let mut line = serde_json::to_value(&o).unwrap_or_default();
                line["t_ns"] = json!(t);
                line["sig"] = json!(sig);
                line["code"] = json!(code);
                line["seq"] = json!(seq);
                for k in ["slot", "index", "bid", "detail", "validator"] { if line.get(k).is_none() { line[k] = serde_json::Value::Null; } }
                line["attempt"] = json!(attempt);
                line["stream_epoch"] = json!(epoch);
                let _ = serde_json::to_writer(w, &line);
            }));
        }
    }

    /// A result of a bundle of ours (`sig` its transaction): a `processed` one names the bundle to the transfer
    /// classification (exec.jsonl / wallet.jsonl `bundle`) and is the wallet's source (c); every one goes to the sink
    fn ours(&self, sig: &str, o: &Outcome, seq: u32, t: u64, attempt: Option<u64>) {
        if o.outcome == "processed" {
            crate::classify::note_bundle_processed(sig, &o.bundle, o.slot.unwrap_or(0), o.index.unwrap_or(0));
            if let Some(s64) = bs58::decode(sig).into_vec().ok().and_then(|v| <[u8; 64]>::try_from(v).ok()) { crate::chainfetch::note_jito_processed(&s64, o.slot); }
        }
        if let Some(f) = self.sink.get() { f(ResultNote { sig: sig.to_string(), bundle: o.bundle.clone(), outcome: o.clone(), seq, t_ns: t, attempt }); }
    }

    /// Follow the result of every bundle this key sends, until `stop`; the stream reopens by itself when it ends. Each
    /// opening is a new `stream_epoch`; an outage is `jito_stream_down` (with the error) then `jito_stream_up` (with how
    /// long results could not arrive)
    pub async fn follow_results(self: Arc<Self>, stop: Arc<std::sync::atomic::AtomicBool>, status: impl Fn(String) + Send + Sync) {
        let mut first = true;
        let mut outage = Outage::default();
        while !stop.load(Relaxed) {
            let r = async {
                let token = self.token().await?;
                let mut grpc = tonic::client::Grpc::new(self.channel.clone());
                grpc.ready().await.context("block engine not ready")?;
                let mut req = tonic::Request::new(SubscribeBundleResultsRequest {});
                req.metadata_mut().insert("authorization", format!("Bearer {token}").parse().context("token")?);
                let codec: ProstCodec<SubscribeBundleResultsRequest, BundleResult> = ProstCodec::default();
                let path = http::uri::PathAndQuery::from_static("/searcher.SearcherService/SubscribeBundleResults");
                crate::netcount::note();
                let mut st = grpc.server_streaming(req, path, codec).await?.into_inner();
                let epoch = self.epoch.fetch_add(1, Relaxed) + 1;
                status(format!("jito results: stream {}", if first { "open" } else { "reopened" }));
                if let Some(e) = outage.opened(epoch, now_ns()) { self.rec.event("jito_stream_up", "jito", None, e); }
                first = false;
                while let Some(m) = st.message().await? {
                    // the LeaderBook's `bundle_result` source (WP-03 item 10): the validators our bundles reached
                    if let Some(id) = m.accepted.as_ref().map(|a| &a.validator_identity).or(m.processed.as_ref().map(|p| &p.validator_identity)) {
                        crate::leaders::note_bundle_validator(id);
                    }
                    self.on_result(summarize(m));
                    if stop.load(Relaxed) { return Ok(()); }
                }
                anyhow::Ok(())
            }.await;
            if stop.load(Relaxed) { break; }
            let why = match &r { Err(e) => crate::rpc::scrub(&format!("{e:#}")), Ok(()) => "the stream ended".into() };
            if let Some(e) = outage.failed(self.epoch.load(Relaxed), &why, now_ns()) { self.rec.event("jito_stream_down", "jito", None, e); }
            if r.is_err() { status(format!("jito results: {why}; reopening")); }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
    }
}

/// the SendBundle method (the one unary call that is the send itself: not counted as a network call)
const SEND_BUNDLE: &str = "/searcher.SearcherService/SendBundle";

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
        let dir = std::env::temp_dir().join(format!("arbx-key-{}", std::process::id()));
        std::fs::write(&dir, serde_json::to_string(&bytes).unwrap()).unwrap();
        assert_eq!(load_keypair(dir.to_str().unwrap()).unwrap().to_bytes(), key.to_bytes());
        bytes[40] ^= 1;
        std::fs::write(&dir, serde_json::to_string(&bytes).unwrap()).unwrap();
        assert!(load_keypair(dir.to_str().unwrap()).is_err(), "mismatched public half");
        let _ = std::fs::remove_file(&dir);
    }

    fn out(bundle: &str, outcome: &'static str) -> Outcome { Outcome { bundle: bundle.into(), outcome, slot: None, index: None, bid: None, detail: None, validator: None } }

    /// PLAN WP-05 acceptance (verdict history): several results for one bundle are all kept, in order, with their times;
    /// a result that beat the sendBundle reply is matched when the reply names its bundle; our results reach the sink
    /// (and a `processed` one the classification and the wallet's source (c))
    #[tokio::test]
    async fn every_result_of_a_bundle_is_kept_in_order() {
        let j = Jito::for_test(crate::rec::Rec::off());
        j.set_cached(Some(CachedToken { value: "tok".into(), exp_ms: unix_ms() + 600_000, issued_ms: unix_ms() }));
        let sunk: Arc<Mutex<Vec<(String, &'static str, u32, Option<u64>)>>> = Default::default();
        let s2 = sunk.clone();
        j.set_sink(Box::new(move |n: ResultNote| s2.lock().unwrap().push((n.sig, n.outcome.outcome, n.seq, n.attempt))));
        // the block engine in memory names bundles b1, b2, ...
        let n = Arc::new(AtomicU64::new(0));
        let n2 = n.clone();
        j.set_fake(Arc::new(move |_txs: &[&[u8]]| format!("b{}", n2.fetch_add(1, Relaxed) + 1)));
        // b1: sent first, then accepted, would-fail
        let sig1 = bs58::encode([1u8; 64]).into_string();
        assert_eq!(j.send_bundle(&[&[1, 2, 3]], &sig1, Some(7)).await.unwrap(), "b1");
        j.on_result_at(Outcome { slot: Some(9), validator: Some("V1".into()), ..out("b1", "accepted") }, 100);
        j.on_result_at(Outcome { detail: Some("custom program error: 0x4e580002".into()), ..out("b1", "would-fail") }, 250);
        let v = j.verdicts(&sig1);
        assert_eq!(v.iter().map(|(t, o)| (*t, o.outcome)).collect::<Vec<_>>(), vec![(100, "accepted"), (250, "would-fail")]);
        assert_eq!(v[0].1.validator.as_deref(), Some("V1"), "the validator is kept");
        // b2's results beat its reply: kept under the id, matched (and sunk) when the reply comes
        let sig2 = bs58::encode([2u8; 64]).into_string();
        j.on_result_at(Outcome { slot: Some(11), validator: Some("V2".into()), ..out("b2", "accepted") }, 300);
        j.on_result_at(Outcome { slot: Some(11), index: Some(4), validator: Some("V2".into()), ..out("b2", "processed") }, 310);
        assert!(j.verdicts(&sig2).is_empty(), "not matched yet");
        assert_eq!(j.send_bundle(&[&[4, 5]], &sig2, Some(8)).await.unwrap(), "b2");
        assert_eq!(j.verdicts(&sig2).iter().map(|(t, o)| (*t, o.outcome)).collect::<Vec<_>>(), vec![(300, "accepted"), (310, "processed")]);
        j.on_result_at(out("b2", "finalized"), 900);
        assert_eq!(j.verdicts(&sig2).len(), 3);
        let s = sunk.lock().unwrap().clone();
        assert_eq!(s, vec![(sig1.clone(), "accepted", 0, Some(7)), (sig1, "would-fail", 1, Some(7)), (sig2.clone(), "accepted", 0, Some(8)), (sig2.clone(), "processed", 1, Some(8)),
            (sig2, "finalized", 2, Some(8))]);
        // review WP-05 #2: only a landing is final; a would-fail, a lost auction, a drop or a rejection keeps the entry
        assert!(out("x", "processed").is_final() && out("x", "finalized").is_final());
        for o in ["accepted", "would-fail", "lost-auction", "dropped", "rejected"] { assert!(!out("x", o).is_final(), "{o}"); }
    }

    /// F28: the send path reads only the cached token. An expired one refuses at once (`jito_auth_stale`) with no network
    /// call; a valid one sends; the refresh is the background's (it counts in the process total, not in the send's scope)
    #[tokio::test]
    async fn send_bundle_never_refreshes_the_token() {
        let j = Jito::for_test(crate::rec::Rec::off());
        let got: Arc<Mutex<Vec<Vec<u8>>>> = Default::default();
        let g2 = got.clone();
        j.set_fake(Arc::new(move |txs: &[&[u8]]| { g2.lock().unwrap().push(txs[0].to_vec()); "bx".into() }));
        let scope = Arc::new(AtomicU64::new(0));
        let sig = bs58::encode([3u8; 64]).into_string();
        // no token at all, then one about to expire: refused without a call
        for t in [None, Some(CachedToken { value: "t".into(), exp_ms: unix_ms() + 1_000, issued_ms: unix_ms() - 100_000 })] {
            j.set_cached(t);
            let r = crate::netcount::in_task(Some(scope.clone()), j.send_bundle(&[&[9]], &sig, None)).await;
            assert!(matches!(r, Err(BundleError::AuthStale)), "{r:?}");
        }
        assert!(got.lock().unwrap().is_empty());
        assert_eq!(j.token_state(unix_ms()), TokenState::Stale);
        j.set_cached(Some(CachedToken { value: "t".into(), exp_ms: unix_ms() + 600_000, issued_ms: unix_ms() }));
        assert!(matches!(j.token_state(unix_ms()), TokenState::Valid { age_s: 0, .. }));
        let r = crate::netcount::in_task(Some(scope.clone()), j.send_bundle(&[&[9]], &sig, None)).await;
        assert_eq!(r.unwrap(), "bx");
        assert_eq!(got.lock().unwrap().len(), 1);
        assert_eq!(scope.load(Relaxed), 0, "no network call on the send path");
        // a refresh in the background (the real one: the channel goes nowhere, so it fails) counts, outside the scope
        let t0 = crate::netcount::total();
        let j2 = j.clone();
        let _ = tokio::spawn(async move { j2.renew(true).await }).await.unwrap();
        assert!(crate::netcount::total() > t0, "the refresh's unary call is a network call");
        assert_eq!(scope.load(Relaxed), 0, "... not the send path's");
        // the refresher's schedule: half the token's life
        j.set_cached(Some(CachedToken { value: "t".into(), exp_ms: 10_000, issued_ms: 2_000 }));
        assert_eq!(j.renew_due_ms(5_000), 6_000);
    }

    /// review WP-05 #7: a status the block engine answers with when it does not take the bundle is a refusal (it cannot
    /// land); a timeout, a transport failure and what tonic reports for one are not: such a bundle may have arrived
    #[test]
    fn a_refusal_is_told_from_no_answer() {
        use tonic::Code::*;
        for c in [InvalidArgument, ResourceExhausted, PermissionDenied, Unauthenticated, FailedPrecondition, OutOfRange, Unimplemented, NotFound] { assert!(refused_code(c), "{c:?}"); }
        for c in [Ok, Cancelled, DeadlineExceeded, Unknown, Unavailable, Internal, DataLoss, Aborted, AlreadyExists] { assert!(!refused_code(c), "{c:?}"); }
        let e = anyhow::Error::new(GrpcStatus { code: ResourceExhausted, msg: "/x: rate limited".into() });
        assert_eq!(format!("{e:#}"), "/x: rate limited", "the message is the status line, as before");
    }

    /// review WP-05 #14: one `jito_stream_down` per outage (its first error) and one `jito_stream_up` when a stream opens
    /// again, with how long results could not arrive
    #[test]
    fn stream_outages_are_one_down_and_one_up() {
        let mut o = Outage::default();
        assert_eq!(o.opened(1, 100), None, "the first opening ends no outage");
        assert_eq!(o.failed(1, "boom", 1_000_000_000), Some(json!({ "stream_epoch": 1, "error": "boom" })));
        assert_eq!(o.failed(1, "again", 2_000_000_000), None, "one down per outage");
        assert_eq!(o.opened(2, 4_500_000_000), Some(json!({ "stream_epoch": 2, "down_ms": 3_500 })));
        assert_eq!(o.opened(3, 5_000_000_000), None);
        assert!(o.failed(3, "x", 6_000_000_000).is_some(), "a new outage");
    }

    /// review WP-05 #14 (PLAN WP-05 item 2, F28): the background refresher renews the cached token at half its lifetime
    /// (an events.jsonl `jito_token_refresh` each time); a failed renewal is retried after 1 s, then 2 s, each failure an
    /// event saying whether the send path is left without a valid token
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn keep_token_renews_at_half_life_and_backs_off() {
        let d = std::env::temp_dir().join(format!("arbx-jito-keep-{}-{}", std::process::id(), now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        let channel = tonic::transport::Endpoint::from_static("http://127.0.0.1:9").connect_lazy();
        let j = Arc::new(Jito::with_channel(channel, SigningKey::from_bytes(&[1u8; 32]), rec.clone()));
        let fail = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let (f2, calls) = (fail.clone(), Arc::new(AtomicU64::new(0)));
        let c2 = calls.clone();
        j.set_fake_renew(Arc::new(move || {
            c2.fetch_add(1, Relaxed);
            if f2.load(Relaxed) { anyhow::bail!("block engine unreachable") }
            Ok(CachedToken { value: "renewed".into(), exp_ms: unix_ms() + 3_600_000, issued_ms: unix_ms() })
        }));
        // a token obtained 10 s ago with 10.3 s left: due for renewal at half its life, 150 ms from now
        let t0 = unix_ms();
        j.set_cached(Some(CachedToken { value: "first".into(), exp_ms: t0 + 10_300, issued_ms: t0 - 10_000 }));
        assert_eq!(j.renew_due_ms(t0), t0 + 150);
        let stop = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let h = tokio::spawn(j.clone().keep_token(stop.clone()));
        let waited = std::time::Instant::now();
        while j.cached_token(unix_ms()).as_deref() != Some("renewed") {
            assert!(waited.elapsed() < Duration::from_secs(3), "not renewed");
            tokio::time::sleep(Duration::from_millis(5)).await;
        }
        assert!(unix_ms() >= t0 + 140, "renewed at half its life, not before");
        assert_eq!(calls.load(Relaxed), 1);
        h.abort();
        // the block engine is unreachable and no token is held: a renewal at once, then after 1 s, then after 2 s
        fail.store(true, Relaxed);
        j.set_cached(None);
        let h = tokio::spawn(j.clone().keep_token(stop.clone()));
        let wait_for = |n: u64| { let c = calls.clone(); async move {
            let w = std::time::Instant::now();
            while c.load(Relaxed) < n { assert!(w.elapsed() < Duration::from_secs(4), "no retry"); tokio::time::sleep(Duration::from_millis(5)).await; }
            std::time::Instant::now()
        } };
        let first = wait_for(2).await;
        let second = wait_for(3).await;
        assert!(second - first >= Duration::from_millis(950), "the first retry waits 1 s: {:?}", second - first);
        // (the failure's event is written right after the call returns)
        tokio::time::sleep(Duration::from_millis(50)).await;
        stop.store(true, Relaxed);
        h.abort();
        rec.close();
        let ev: Vec<serde_json::Value> = crate::rec::read_jsonl(&d, "events").unwrap().into_iter().filter(|e| e["kind"] == "jito_token_refresh").collect();
        assert_eq!(ev.len(), 3, "{ev:?}");
        assert_eq!((ev[0]["detail"]["ok"].as_bool(), ev[0]["detail"]["via"].as_str()), (Some(true), Some("fake")), "{}", ev[0]);
        assert_eq!((ev[1]["detail"]["ok"].as_bool(), ev[1]["detail"]["retry_s"].as_u64(), ev[1]["detail"]["stale"].as_bool()), (Some(false), Some(1), Some(true)), "{}", ev[1]);
        assert_eq!((ev[2]["detail"]["ok"].as_bool(), ev[2]["detail"]["retry_s"].as_u64()), (Some(false), Some(2)), "{}", ev[2]);
        assert!(ev[1]["detail"]["error"].as_str().is_some_and(|e| e.contains("unreachable")));
        let _ = std::fs::remove_dir_all(&d);
    }

    /// review F12: bundles.jsonl as `on_result` writes it through the recorder (the line is made on the core writer):
    /// the outcome's fields, `t_ns`, the signature when known and a would-fail's decoded error code
    #[tokio::test]
    async fn bundle_results_are_recorded() {
        let d = std::env::temp_dir().join(format!("arbx-jito-rec-{}-{}", std::process::id(), now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        let channel = tonic::transport::Endpoint::from_static("http://127.0.0.1:9").connect_lazy();
        let j = Jito::with_channel(channel, SigningKey::from_bytes(&[1u8; 32]), rec.clone());
        {
            let mut v = j.verdicts.lock().unwrap();
            v.sig_of_id.insert("b1".into(), "sigA".into());
            v.attempt_of_id.insert("b1".into(), 5);
        }
        j.on_result(Outcome { detail: Some(PROFIT.into()), ..out("b1", "would-fail") });
        j.on_result(Outcome { slot: Some(7), index: Some(1), validator: Some("Val".into()), ..out("b2", "processed") });
        j.on_result(Outcome { slot: Some(7), ..out("b2", "finalized") });
        rec.close();
        let v = crate::rec::read_jsonl(&d, "bundles").unwrap();
        assert_eq!(v.len(), 3);
        assert_eq!((v[0]["bundle"].as_str(), v[0]["outcome"].as_str(), v[0]["sig"].as_str(), v[0]["code"].as_str()), (Some("b1"), Some("would-fail"), Some("sigA"), Some(PROFIT_CHECK_CODE)));
        assert!(v[0]["t_ns"].as_u64().unwrap() > 0 && v[0]["detail"].as_str().unwrap().starts_with("A transaction"));
        assert_eq!((v[0]["seq"].as_u64(), v[0]["attempt"].as_u64(), v[0]["validator"].is_null(), v[0]["stream_epoch"].as_u64()), (Some(0), Some(5), true, Some(0)));
        assert_eq!((v[1]["slot"].as_u64(), v[1]["index"].as_u64(), v[1]["sig"].is_null(), v[1]["code"].is_null(), v[1]["validator"].as_str()), (Some(7), Some(1), true, true, Some("Val")));
        assert_eq!((v[2]["seq"].as_u64(), v[2]["outcome"].as_str()), (Some(1), Some("finalized")), "the second result of b2");
        assert_eq!(*j.counts.lock().unwrap(), [("finalized", 1), ("processed", 1), ("would-fail", 1)].into_iter().collect());
        let _ = std::fs::remove_dir_all(&d);
    }
}

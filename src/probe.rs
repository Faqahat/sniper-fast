//! `arbx grpc-probe --config <file>` (PLAN WP-03 item 5; MEASUREMENT §4.49; review F14): what the configured gRPC
//! provider accepts. With the configured tokens it opens, one after the other, each subscription the plan needs, for
//! `--seconds` (30) each, and reports whether it was accepted or refused, the error text, the messages it delivered and
//! when the first came:
//! - `accounts_full`: the state stream's accounts filter at the full list size (at least 3,000 keys);
//! - `slots_interslot`: slots with interslot updates;
//! - `blocks_meta`;
//! - `tx_filter_1`, `tx_filter_2`, `tx_filter_5`: the transaction filter with 1, 2 and 5 accounts (the limit);
//! - `blocks_account_include`: blocks with `account_include` of the venue programs (OD-1);
//! - `deshred_5`: the deshred filter with the 5 venue programs, on each enabled `yellowstone-deshred` feed.
//!
//! It writes `probe.json` (`[state] probe_file`, default `<out_dir>/probe.json`, read by `[state] block_meta = "auto"`
//! and `slot_statuses = "auto"`) and a dated copy beside it. No token or URL with a key appears in it: hosts only.
//!
//! Each subscription gets a verdict (review WP-03 #4; PLAN-ADDENDUM I-2, I-3):
//! - `accepted`: the stream stayed open for the window (`auto` also needs at least one message);
//! - `refused`: the provider answered with a definite refusal (PermissionDenied, InvalidArgument, Unimplemented, ...),
//!   or closed the stream early;
//! - `inconclusive` (`accepted` null): Unavailable / HTTP 503 (and 429, 502, 504), ResourceExhausted, DeadlineExceeded,
//!   or no gRPC answer at all (a transport error, not opened in time). Haan grants its streams to the first process
//!   only and answers every other one 503 (I-3), and its outages are transient (I-2): such a result says nothing about
//!   what the provider supports. Its gRPC `code` and `http_status` are recorded, `auto` treats it as off, and
//!   `arbx grpc-probe` then exits non-zero without replacing probe.json.
//!
//! The probe holds the provider for about 4 minutes (8 subscriptions one after the other), so it refuses to start while
//! anything else may hold it (`busy`: a campaign supervisor's lock, a live segment's control socket, an `arbx run` or
//! `arb-lab run` process), unless `--force`, and holds the supervisor's lock (`<out_dir>/.supervisor.lock`) while it
//! runs, so `deploy/run-w.sh` does not start a campaign meanwhile.
use crate::feeds::grpc::{channel, FilterAccounts, FilterBlocks, FilterBlocksMeta, FilterDeshredTx, FilterSlots, FilterTx, SubscribeDeshredRequest,
    SubscribeRequest, SubscribeUpdate, SubscribeUpdateDeshred};
use crate::feeds::clock::now_ns;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::time::{Duration, Instant};
use tonic::codec::ProstCodec;

pub const SCHEMA: &str = "arbx.probe/1.0";
/// the accounts filter is probed at no fewer keys than this (PLAN WP-03 item 5)
pub const MIN_ACCOUNTS: usize = 3_000;

/// One provider endpoint and its credentials
#[derive(Clone, Debug)]
pub struct Target { pub url: String, pub token: Option<String>, pub header: Option<String> }

/// What to probe
pub struct Plan {
    /// the state stream's provider (`[state] url`, token)
    pub state: Target,
    /// the accounts filter's keys (padded to at least `MIN_ACCOUNTS`)
    pub accounts: Vec<String>,
    /// the venue programs (base58), in the order the transaction filters take them
    pub venue_programs: Vec<String>,
    /// (feed name, target) of each enabled deshred feed
    pub deshred: Vec<(String, Target)>,
}

/// One subscription's result
#[derive(Clone, Debug, PartialEq, serde::Serialize)]
pub struct SubResult {
    pub sub: String,
    /// true accepted, false refused, None inconclusive (see the module doc)
    pub accepted: Option<bool>,
    /// "accepted", "refused" or "inconclusive"
    pub verdict: &'static str,
    pub error: Option<String>,
    /// the gRPC status code of an error (`Unavailable`, `PermissionDenied`, ...; None: no gRPC answer)
    pub code: Option<String>,
    /// the HTTP status a non-gRPC reply carried (503 when the provider refuses the connection itself)
    pub http_status: Option<u16>,
    pub messages_30s: u64,
    pub first_msg_ms: Option<f64>,
    pub host: String,
    #[serde(skip_serializing_if = "Option::is_none")] pub feed: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")] pub n_accounts: Option<usize>,
    pub window_s: f64,
}

/// `n` keys for the accounts filter: `real` first, then derived ones that name no account (sha256 of a counter), so
/// the request has the full list's size
pub fn pad_accounts(real: &[String], n: usize) -> Vec<String> {
    let mut out: Vec<String> = real.to_vec();
    let mut i = 0u64;
    while out.len() < n {
        use sha2::Digest;
        let h: [u8; 32] = sha2::Sha256::digest([&b"arbx-probe-pad"[..], &i.to_le_bytes()].concat()).into();
        out.push(bs58::encode(h).into_string());
        i += 1;
    }
    out
}

fn with_token<T>(req: &mut tonic::Request<T>, t: &Target) -> anyhow::Result<()> {
    if let Some(tok) = &t.token {
        let key: tonic::metadata::MetadataKey<tonic::metadata::Ascii> = t.header.as_deref().unwrap_or("x-token").parse()?;
        req.metadata_mut().insert(key, tok.parse()?);
    }
    Ok(())
}

/// Why a subscription did not stay open: its gRPC code (None: no gRPC answer) and text
#[derive(Clone, Debug, PartialEq)]
pub struct SubErr { pub code: Option<tonic::Code>, pub text: String }

impl SubErr {
    fn status(s: &tonic::Status) -> SubErr { SubErr { code: Some(s.code()), text: crate::rpc::scrub(&format!("{:?}: {}", s.code(), s.message())) } }
    fn other(text: String) -> SubErr { SubErr { code: None, text: crate::rpc::scrub(&text) } }
    /// says nothing about what the provider supports: it is busy (another process holds the stream, I-3), down (I-2) or
    /// unreachable
    pub fn inconclusive(&self) -> bool {
        use tonic::Code::*;
        match self.code { None => true, Some(c) => matches!(c, Unavailable | ResourceExhausted | DeadlineExceeded | Aborted | Cancelled) }
    }
    /// the HTTP status of a reply without gRPC status (tonic: "... mapped from HTTP status code 503")
    pub fn http_status(&self) -> Option<u16> {
        let i = self.text.find("HTTP status code ")? + "HTTP status code ".len();
        self.text[i..].chars().take_while(|c| c.is_ascii_digit()).collect::<String>().parse().ok()
    }
}

/// Open one bidi subscription (`first` as its request) and count the messages `counts` accepts for `window`.
/// Ok((messages, first message ms, closed early)) or Err(why it did not open or stay open)
async fn run_sub<Req, Resp>(t: &Target, path: &'static str, first: Req, window: Duration, counts: impl Fn(&Resp) -> bool)
    -> Result<(u64, Option<f64>, Option<String>), SubErr>
where Req: prost::Message + Default + Send + 'static, Resp: prost::Message + Default + Send + 'static {
    let start = Instant::now();
    let deadline = tokio::time::Instant::now() + window;
    let opened = async {
        let ch = channel(&t.url).await.map_err(|e| SubErr::other(format!("{e:#}")))?;
        let mut grpc = tonic::client::Grpc::new(ch).max_decoding_message_size(256 * 1024 * 1024);
        grpc.ready().await.map_err(|e| SubErr::other(format!("service not ready: {e}")))?;
        let (tx, rx) = tokio::sync::mpsc::channel::<Req>(4);
        tx.send(first).await.ok();
        let mut req = tonic::Request::new(tokio_stream::wrappers::ReceiverStream::new(rx));
        with_token(&mut req, t).map_err(|e| SubErr::other(format!("{e:#}")))?;
        let codec: ProstCodec<Req, Resp> = ProstCodec::default();
        let st = grpc.streaming(req, http::uri::PathAndQuery::from_static(path), codec).await.map_err(|s| SubErr::status(&s))?.into_inner();
        Ok((st, tx))
    };
    let (mut st, _keep) = match tokio::time::timeout_at(deadline, opened).await {
        Ok(Ok(x)) => x,
        Ok(Err(e)) => return Err(e),
        Err(_) => return Err(SubErr::other(format!("not opened within {:.0} s", window.as_secs_f64()))),
    };
    let (mut n, mut first_ms) = (0u64, None);
    loop {
        match tokio::time::timeout_at(deadline, st.message()).await {
            Err(_) => return Ok((n, first_ms, None)),
            Ok(Ok(Some(m))) => if counts(&m) { n += 1; first_ms.get_or_insert(start.elapsed().as_secs_f64() * 1e3); },
            Ok(Ok(None)) => return Ok((n, first_ms, Some(format!("stream closed by the server after {:.0} ms", start.elapsed().as_secs_f64() * 1e3)))),
            Ok(Err(s)) => return Err(SubErr::status(&s)),
        }
    }
}

fn update_counts(m: &SubscribeUpdate) -> bool { m.account.is_some() || m.slot.is_some() || m.transaction.is_some() || m.block.is_some() || m.block_meta.is_some() }

/// The probe's subscriptions (name, request) on the state provider
pub fn requests(plan: &Plan) -> Vec<(&'static str, SubscribeRequest, Option<usize>)> {
    let tx = |n: usize| SubscribeRequest { transactions: HashMap::from([("probe".to_string(), FilterTx { vote: Some(false), failed: None,
        account_include: plan.venue_programs.iter().take(n).cloned().collect(), ..Default::default() })]), commitment: Some(0), ..Default::default() };
    let accounts = pad_accounts(&plan.accounts, MIN_ACCOUNTS.max(plan.accounts.len()));
    let n_acc = accounts.len();
    vec![
        ("accounts_full", SubscribeRequest { accounts: HashMap::from([("probe".to_string(), FilterAccounts { account: accounts, owner: vec![] })]),
            commitment: Some(0), ..Default::default() }, Some(n_acc)),
        ("slots_interslot", SubscribeRequest { slots: HashMap::from([("probe".to_string(), FilterSlots { filter_by_commitment: Some(false), interslot_updates: Some(true) })]),
            ..Default::default() }, None),
        ("blocks_meta", SubscribeRequest { blocks_meta: HashMap::from([("probe".to_string(), FilterBlocksMeta {})]), ..Default::default() }, None),
        ("tx_filter_1", tx(1), None),
        ("tx_filter_2", tx(2), None),
        ("tx_filter_5", tx(5), None),
        ("blocks_account_include", SubscribeRequest { blocks: HashMap::from([("probe".to_string(), FilterBlocks { account_include: plan.venue_programs.clone(),
            include_transactions: Some(true), include_accounts: Some(false), include_entries: Some(false) })]), commitment: Some(1), ..Default::default() }, None),
    ]
}

/// Run every subscription of `plan` for `window` each, one after the other; `only`: just these names
pub async fn probe(plan: &Plan, window: Duration, only: Option<&[String]>) -> Vec<SubResult> {
    let want = |n: &str| only.map_or(true, |o| o.iter().any(|x| x == n));
    let host = crate::provenance::host_of(&plan.state.url);
    let mut out = Vec::new();
    let res = |sub: &str, r: Result<(u64, Option<f64>, Option<String>), SubErr>, host: &str, feed: Option<String>, n_accounts: Option<usize>| {
        let (accepted, error, code, http, n, first) = match r {
            Ok((n, f, None)) => (Some(true), None, None, None, n, f),
            Ok((n, f, Some(closed))) => (Some(false), Some(closed), None, None, n, f),
            Err(e) => ((!e.inconclusive()).then_some(false), Some(e.text.clone()), e.code.map(|c| format!("{c:?}")), e.http_status(), 0, None),
        };
        let verdict = match accepted { Some(true) => "accepted", Some(false) => "refused", None => "inconclusive" };
        SubResult { sub: sub.into(), accepted, verdict, error, code, http_status: http, messages_30s: n, first_msg_ms: first, host: host.into(), feed, n_accounts,
            window_s: window.as_secs_f64() }
    };
    for (name, req, n_acc) in requests(plan) {
        if !want(name) { continue; }
        let r = run_sub::<SubscribeRequest, SubscribeUpdate>(&plan.state, "/geyser.Geyser/Subscribe", req, window, update_counts).await;
        out.push(res(name, r, &host, None, n_acc));
    }
    if want("deshred_5") {
        for (feed, t) in &plan.deshred {
            let req = SubscribeDeshredRequest { deshred_transactions: HashMap::from([("probe".to_string(), FilterDeshredTx { vote: Some(false),
                account_include: plan.venue_programs.iter().take(5).cloned().collect(), ..Default::default() })]), ..Default::default() };
            let r = run_sub::<SubscribeDeshredRequest, SubscribeUpdateDeshred>(t, "/geyser.Geyser/SubscribeDeshred", req, window, |m| m.deshred_transaction.is_some()).await;
            out.push(res("deshred_5", r, &crate::provenance::host_of(&t.url), Some(feed.clone()), None));
        }
    }
    out
}

/// probe.json (§4.49)
pub fn probe_json(plan: &Plan, subs: &[SubResult]) -> Value {
    json!({ "schema": SCHEMA, "t_ns": now_ns(), "provider_host": crate::provenance::host_of(&plan.state.url), "subs": subs })
}

/// Whether a probe file accepted `sub` on `host` (`[state] block_meta = "auto"`, `slot_statuses = "auto"`): Some(true)
/// only for a stream that stayed open AND delivered at least one message (review WP-03 #4 iii); Some(false) refused.
/// None: no usable answer (no file, another provider, not probed, inconclusive, or open but silent): `auto` is off
pub fn accepted(probe: &Value, host: &str, sub: &str) -> Option<bool> {
    if probe["schema"].as_str() != Some(SCHEMA) || probe["provider_host"].as_str() != Some(host) { return None; }
    let s = probe["subs"].as_array()?.iter().find(|s| s["sub"].as_str() == Some(sub) && s.get("feed").map_or(true, |f| f.is_null()))?;
    match s["accepted"].as_bool()? {
        true => (s["messages_30s"].as_u64().unwrap_or(0) > 0).then_some(true),
        false => Some(false),
    }
}

/// The results that say nothing (503 / Unavailable and the like)
pub fn inconclusive(subs: &[SubResult]) -> Vec<&SubResult> { subs.iter().filter(|s| s.accepted.is_none()).collect() }

/// Whether a command line is a bot run that may hold the provider: `arbx … run …` (a campaign's copy `arbx-<sha8>` too)
/// or arb-lab's `arb-lab … run …`
pub fn is_bot_run(argv: &[String]) -> bool {
    let Some(a0) = argv.first() else { return false };
    let base = a0.rsplit('/').next().unwrap_or(a0);
    (base.starts_with("arbx") || base.starts_with("arb-lab")) && argv.iter().skip(1).any(|a| a == "run")
}

/// What may hold the provider now (review WP-03 #4 ii): a live control socket of a segment under `out_dir`
/// (`<out_dir>/<seg>/control.sock`, `<out_dir>/<campaign>/<seg>/control.sock`), and, with `procs`, every other
/// process running `arbx run` or `arb-lab run` on this host. Empty: nothing found
pub fn busy(out_dir: &std::path::Path, procs: bool) -> Vec<String> {
    let mut out = Vec::new();
    let subdirs = |d: &std::path::Path| -> Vec<std::path::PathBuf> {
        std::fs::read_dir(d).map(|r| r.filter_map(|e| e.ok()).map(|e| e.path()).filter(|p| p.is_dir()).collect()).unwrap_or_default()
    };
    for d in subdirs(out_dir) {
        for run in std::iter::once(d.clone()).chain(subdirs(&d)) {
            if run.join(crate::control::SOCKET).exists() && crate::control::socket_alive(&run) { out.push(format!("a live segment: {}", run.display())); }
        }
    }
    if procs {
        let me = std::process::id().to_string();
        for e in std::fs::read_dir("/proc").into_iter().flatten().filter_map(|e| e.ok()) {
            let pid = e.file_name().to_string_lossy().into_owned();
            if pid == me || !pid.bytes().all(|b| b.is_ascii_digit()) { continue; }
            let Ok(b) = std::fs::read(e.path().join("cmdline")) else { continue };
            let argv: Vec<String> = b.split(|c| *c == 0).filter(|a| !a.is_empty()).map(|a| String::from_utf8_lossy(a).into_owned()).collect();
            if is_bot_run(&argv) { out.push(format!("pid {pid}: {}", crate::control::cmdline(pid.parse().unwrap_or(0)).unwrap_or_default())); }
        }
    }
    out
}

/// The campaign supervisor's lock (`<out_dir>/.supervisor.lock`, deploy/run-w.sh), taken for the probe's duration so
/// no campaign starts meanwhile. Err: a supervisor holds it (a campaign is running, between segments too). Ok(None):
/// there is no runs directory here to guard (the lock file cannot be opened)
pub fn lock_runs(out_dir: &std::path::Path) -> anyhow::Result<Option<std::fs::File>> {
    use std::os::fd::AsRawFd;
    let path = out_dir.join(".supervisor.lock");
    let Ok(f) = std::fs::OpenOptions::new().create(true).append(true).open(&path) else { return Ok(None) };
    if unsafe { libc::flock(f.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
        anyhow::bail!("{} is held: a campaign supervisor is running", path.display());
    }
    Ok(Some(f))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::feeds::grpc::{DeshredTx, UpdateSlot};
    use std::sync::Arc;
    use tonic::codegen::{http, Body, BoxFuture, Context, Poll, Service, StdError};

    /// An in-process Yellowstone server: `Subscribe` refuses a request with `blocks_meta` (PermissionDenied) and
    /// otherwise streams a slot update every 20 ms; `SubscribeDeshred` streams deshred transactions. `mode` 1: every
    /// call is refused Unavailable (another process holds the provider, PLAN-ADDENDUM I-3); 2: every call gets a bare
    /// HTTP 503; 3: every stream opens and stays silent
    #[derive(Clone, Default)]
    struct Fake { seen: Arc<std::sync::Mutex<Vec<SubscribeRequest>>>, mode: Arc<std::sync::atomic::AtomicU8> }

    impl tonic::server::NamedService for Fake { const NAME: &'static str = "geyser.Geyser"; }

    type Out<T> = std::pin::Pin<Box<dyn tokio_stream::Stream<Item = Result<T, tonic::Status>> + Send>>;

    struct SubSvc(Fake);
    impl tonic::server::StreamingService<SubscribeRequest> for SubSvc {
        type Response = SubscribeUpdate;
        type ResponseStream = Out<SubscribeUpdate>;
        type Future = BoxFuture<tonic::Response<Self::ResponseStream>, tonic::Status>;
        fn call(&mut self, req: tonic::Request<tonic::Streaming<SubscribeRequest>>) -> Self::Future {
            let seen = self.0.seen.clone();
            let mode = self.0.mode.load(std::sync::atomic::Ordering::Relaxed);
            Box::pin(async move {
                let mut inb = req.into_inner();
                let first = inb.message().await?.ok_or_else(|| tonic::Status::invalid_argument("no request"))?;
                seen.lock().unwrap().push(first.clone());
                if mode == 1 { return Err(tonic::Status::unavailable("stream limit reached for this token")); }
                if !first.blocks_meta.is_empty() { return Err(tonic::Status::permission_denied("blocks_meta is not enabled for this token")); }
                let (tx, rx) = tokio::sync::mpsc::channel(16);
                tokio::spawn(async move {
                    if mode == 3 { tx.closed().await; return; }
                    for slot in 0u64.. {
                        let m = SubscribeUpdate { slot: Some(UpdateSlot { slot, ..Default::default() }), ..Default::default() };
                        if tx.send(Ok(m)).await.is_err() { break; }
                        tokio::time::sleep(Duration::from_millis(20)).await;
                    }
                });
                let s: Out<SubscribeUpdate> = Box::pin(tokio_stream::wrappers::ReceiverStream::new(rx));
                Ok(tonic::Response::new(s))
            })
        }
    }

    struct DeshredSvc(u8);
    impl tonic::server::StreamingService<SubscribeDeshredRequest> for DeshredSvc {
        type Response = SubscribeUpdateDeshred;
        type ResponseStream = Out<SubscribeUpdateDeshred>;
        type Future = BoxFuture<tonic::Response<Self::ResponseStream>, tonic::Status>;
        fn call(&mut self, _req: tonic::Request<tonic::Streaming<SubscribeDeshredRequest>>) -> Self::Future {
            let mode = self.0;
            Box::pin(async move {
                if mode == 1 { return Err(tonic::Status::unavailable("stream limit reached for this token")); }
                let (tx, rx) = tokio::sync::mpsc::channel(16);
                tokio::spawn(async move {
                    for slot in 0u64.. {
                        let m = SubscribeUpdateDeshred { deshred_transaction: Some(DeshredTx { transaction: None, slot }), ..Default::default() };
                        if tx.send(Ok(m)).await.is_err() { break; }
                        tokio::time::sleep(Duration::from_millis(20)).await;
                    }
                });
                let s: Out<SubscribeUpdateDeshred> = Box::pin(tokio_stream::wrappers::ReceiverStream::new(rx));
                Ok(tonic::Response::new(s))
            })
        }
    }

    impl<B> Service<http::Request<B>> for Fake where B: Body + Send + 'static, B::Error: Into<StdError> + Send + 'static {
        type Response = http::Response<tonic::body::BoxBody>;
        type Error = std::convert::Infallible;
        type Future = BoxFuture<Self::Response, Self::Error>;
        fn poll_ready(&mut self, _: &mut Context<'_>) -> Poll<Result<(), Self::Error>> { Poll::Ready(Ok(())) }
        fn call(&mut self, req: http::Request<B>) -> Self::Future {
            let me = self.clone();
            if me.mode.load(std::sync::atomic::Ordering::Relaxed) == 2 {
                return Box::pin(async move { Ok(http::Response::builder().status(503).body(tonic::body::empty_body()).unwrap()) });
            }
            match req.uri().path() {
                "/geyser.Geyser/Subscribe" => Box::pin(async move {
                    let mut g = tonic::server::Grpc::new(ProstCodec::<SubscribeUpdate, SubscribeRequest>::default());
                    Ok(g.streaming(SubSvc(me), req).await)
                }),
                "/geyser.Geyser/SubscribeDeshred" => Box::pin(async move {
                    let mut g = tonic::server::Grpc::new(ProstCodec::<SubscribeUpdateDeshred, SubscribeDeshredRequest>::default());
                    Ok(g.streaming(DeshredSvc(me.mode.load(std::sync::atomic::Ordering::Relaxed)), req).await)
                }),
                _ => Box::pin(async move { Ok(tonic::Status::unimplemented("not here").into_http()) }),
            }
        }
    }

    /// PLAN WP-03 acceptance: `grpc-probe` against an in-process fake Yellowstone server that refuses `blocks_meta` and
    /// accepts the rest: probe.json reports exactly that (and the accounts filter at its full size)
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn the_probe_reports_what_a_fake_server_refuses() {
        let l = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = l.local_addr().unwrap();
        let fake = Fake::default();
        let seen = fake.seen.clone();
        tokio::spawn(tonic::transport::Server::builder().add_service(fake).serve_with_incoming(tokio_stream::wrappers::TcpListenerStream::new(l)));
        let url = format!("http://{addr}");
        let venues: Vec<String> = ["pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", "CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", "675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8",
            "LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG"].map(String::from).to_vec();
        let t = Target { url: url.clone(), token: Some("secret-token".into()), header: None };
        let plan = Plan { state: t.clone(), accounts: vec![venues[0].clone()], venue_programs: venues.clone(), deshred: vec![("haan-deshred".into(), t)] };
        let subs = probe(&plan, Duration::from_millis(300), None).await;
        let v = probe_json(&plan, &subs);
        let by: HashMap<String, &Value> = v["subs"].as_array().unwrap().iter().map(|s| (s["sub"].as_str().unwrap().to_string(), s)).collect();
        assert_eq!(by.len(), 8, "{v:#}");
        for (name, s) in &by {
            if name == "blocks_meta" {
                assert_eq!(s["accepted"], json!(false));
                let e = s["error"].as_str().unwrap();
                assert!(e.contains("PermissionDenied") && e.contains("blocks_meta is not enabled"), "{e}");
                assert_eq!(s["messages_30s"], json!(0));
            } else {
                assert_eq!(s["accepted"], json!(true), "{name}: {s}");
                assert!(s["error"].is_null() && s["messages_30s"].as_u64().unwrap() >= 2, "{name}: {s}");
                assert!(s["first_msg_ms"].as_f64().is_some());
            }
        }
        assert_eq!(by["accounts_full"]["n_accounts"], json!(MIN_ACCOUNTS));
        assert_eq!(by["deshred_5"]["feed"], json!("haan-deshred"));
        assert_eq!(v["provider_host"].as_str(), Some(crate::provenance::host_of(&url).as_str()));
        assert!(!v.to_string().contains("secret-token"), "no token in probe.json");
        // what the server got: the full accounts list, transaction filters of 1, 2 and 5 accounts
        let reqs = seen.lock().unwrap().clone();
        assert_eq!(reqs[0].accounts["probe"].account.len(), MIN_ACCOUNTS);
        let n_tx: Vec<usize> = reqs.iter().filter_map(|r| r.transactions.get("probe").map(|f| f.account_include.len())).collect();
        assert_eq!(n_tx, vec![1, 2, 5]);
        // block_meta = "auto" reads it back
        assert_eq!(accepted(&v, &crate::provenance::host_of(&url), "blocks_meta"), Some(false));
        assert_eq!(accepted(&v, &crate::provenance::host_of(&url), "slots_interslot"), Some(true));
        assert_eq!(accepted(&v, "other.host", "blocks_meta"), None, "another provider's probe says nothing");
    }

    /// review WP-03 #4 (PLAN-ADDENDUM I-2, I-3): a provider busy with another process's streams (Unavailable, or a bare
    /// HTTP 503) makes every result inconclusive (`accepted` null, its code and HTTP status), never "refused", and
    /// `auto` reads it as no answer; a stream that opens but delivers nothing is accepted, yet not good enough for `auto`
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn a_busy_provider_is_inconclusive_and_a_silent_stream_is_not_auto() {
        let l = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let addr = l.local_addr().unwrap();
        let fake = Fake::default();
        let mode = fake.mode.clone();
        tokio::spawn(tonic::transport::Server::builder().add_service(fake).serve_with_incoming(tokio_stream::wrappers::TcpListenerStream::new(l)));
        let url = format!("http://{addr}");
        let host = crate::provenance::host_of(&url);
        let t = Target { url: url.clone(), token: None, header: None };
        let plan = Plan { state: t.clone(), accounts: vec![], venue_programs: vec!["pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA".into()], deshred: vec![("d".into(), t)] };
        let only: Vec<String> = ["slots_interslot", "blocks_meta", "deshred_5"].map(String::from).to_vec();
        for (m, code, http) in [(1u8, "Unavailable", None), (2, "Unavailable", Some(503u16))] {
            mode.store(m, std::sync::atomic::Ordering::Relaxed);
            let subs = probe(&plan, Duration::from_millis(300), Some(&only)).await;
            assert_eq!(subs.len(), 3);
            for s in &subs {
                assert_eq!((s.accepted, s.verdict, s.code.as_deref(), s.http_status), (None, "inconclusive", Some(code), http), "mode {m}: {s:?}");
            }
            assert_eq!(inconclusive(&subs).len(), 3);
            let v = probe_json(&plan, &subs);
            assert!(v["subs"][1]["accepted"].is_null() && v["subs"][1]["verdict"] == "inconclusive");
            assert_eq!(accepted(&v, &host, "blocks_meta"), None, "auto: off, and not a refusal");
            assert_eq!(accepted(&v, &host, "slots_interslot"), None);
        }
        // open and silent: accepted for the record, no answer for auto
        mode.store(3, std::sync::atomic::Ordering::Relaxed);
        let subs = probe(&plan, Duration::from_millis(300), Some(&["slots_interslot".to_string()])).await;
        assert_eq!((subs[0].accepted, subs[0].messages_30s), (Some(true), 0));
        assert_eq!(accepted(&probe_json(&plan, &subs), &host, "slots_interslot"), None);
    }

    /// review WP-03 #4 ii: what may hold the provider, and the supervisor's lock the probe takes
    #[test]
    fn busy_finds_live_segments_and_bot_processes() {
        let s = |v: &[&str]| v.iter().map(|x| x.to_string()).collect::<Vec<_>>();
        assert!(is_bot_run(&s(&["/root/arbx/target/release/arbx", "run", "--config", "x"])));
        assert!(is_bot_run(&s(&["/root/arbx/runs/c1/arbx-1a2b3c4d", "run", "--campaign-dir", "c"])));
        assert!(is_bot_run(&s(&["./arb-lab", "run", "--config", "arb.toml"])));
        assert!(!is_bot_run(&s(&["arbx", "grpc-probe", "--config", "x"])) && !is_bot_run(&s(&["vim", "run"])) && !is_bot_run(&[]));
        let out = std::env::temp_dir().join(format!("arbx-probe-busy-{}-{}", std::process::id(), now_ns()));
        let (live, stale) = (out.join("camp").join("camp-p1"), out.join("seg-old"));
        std::fs::create_dir_all(&live).unwrap();
        std::fs::create_dir_all(&stale).unwrap();
        assert!(busy(&out, false).is_empty());
        // a killed run's socket file: no server, not busy
        drop(std::os::unix::net::UnixListener::bind(stale.join(crate::control::SOCKET)).unwrap());
        assert!(busy(&out, false).is_empty(), "a stale socket is not a live segment");
        let sess = crate::control::Session::new();
        let _srv = crate::control::serve(sess, &live).unwrap();
        let b = busy(&out, false);
        assert_eq!(b.len(), 1, "{b:?}");
        assert!(b[0].contains("camp-p1"));
        // the supervisor's lock: one holder at a time
        let held = lock_runs(&out).unwrap();
        assert!(held.is_some());
        assert!(lock_runs(&out).unwrap_err().to_string().contains("campaign supervisor"));
        drop(held);
        assert!(lock_runs(&out).unwrap().is_some());
        assert!(lock_runs(&out.join("no-such-dir")).unwrap().is_none(), "no runs directory: nothing to guard");
        let _ = std::fs::remove_dir_all(&out);
    }

    #[test]
    fn padding_is_deterministic_and_keeps_the_real_keys() {
        let p = pad_accounts(&["a".into()], 4);
        assert_eq!(p.len(), 4);
        assert_eq!(p[0], "a");
        assert_eq!(p, pad_accounts(&["a".into()], 4));
        assert!(p[1..].iter().all(|k| bs58::decode(k).into_vec().unwrap().len() == 32));
    }
}

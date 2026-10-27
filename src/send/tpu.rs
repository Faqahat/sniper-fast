//! Direct to the leader: each transaction written as one QUIC uni-stream straight to the TPU of the current leader and
//! the next distinct one, with no relay in between (Agave's own client does the same: ALPN "solana-tpu", a self-signed
//! client certificate, server certificate not checked). We hold no stake, so the leader treats us as an unstaked
//! client (smaller ingestion quota); the priority fee still orders us in its scheduler.
//!   leaders   the run's LeaderBook (src/leaders.rs; WP-08: it replaced this module's own `Book`): its schedule and its
//!             nodes' TPU-QUIC addresses. Without one (`arbx senders`), or while it lacks the next slots, this path
//!             fills it itself: getSlotLeaders from the current slot, getClusterNodes (every 15 min)
//!   slot      `SLOT`, set by the engine from the state stream
//!   warm      connections to the next few leaders kept open (connect costs a handshake we must not pay on a send)
//!   [`quic_client`] is also the LeaderBook's RTT prober's endpoint (a handshake, no data)
use crate::leaders::LeaderBook;
use anyhow::{bail, Context, Result};
use serde_json::{json, Value};
use std::collections::HashMap;
use std::net::SocketAddr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use std::time::Duration;

/// the newest slot the engine has seen (processed)
pub static SLOT: AtomicU64 = AtomicU64::new(0);
const ALPN: &[u8] = b"solana-tpu";
/// leaders a transaction goes to: the current one and the next distinct one
const FANOUT: usize = 3;

/// the server's certificate is not checked (a leader's TPU, dip17's QUIC landing lanes: send/quic_lane.rs)
#[derive(Debug)]
pub(crate) struct AcceptAny(pub(crate) Arc<rustls::crypto::CryptoProvider>);
impl rustls::client::danger::ServerCertVerifier for AcceptAny {
    fn verify_server_cert(&self, _: &rustls::pki_types::CertificateDer<'_>, _: &[rustls::pki_types::CertificateDer<'_>], _: &rustls::pki_types::ServerName<'_>,
        _: &[u8], _: rustls::pki_types::UnixTime) -> Result<rustls::client::danger::ServerCertVerified, rustls::Error> {
        Ok(rustls::client::danger::ServerCertVerified::assertion())
    }
    fn verify_tls12_signature(&self, _: &[u8], _: &rustls::pki_types::CertificateDer<'_>, _: &rustls::DigitallySignedStruct) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> {
        Ok(rustls::client::danger::HandshakeSignatureValid::assertion())
    }
    fn verify_tls13_signature(&self, _: &[u8], _: &rustls::pki_types::CertificateDer<'_>, _: &rustls::DigitallySignedStruct) -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> {
        Ok(rustls::client::danger::HandshakeSignatureValid::assertion())
    }
    fn supported_verify_schemes(&self) -> Vec<rustls::SignatureScheme> { self.0.signature_verification_algorithms.supported_schemes() }
}

/// getClusterNodes is fetched again by this path only when the book's node table is older than this (the LeaderBook's
/// refresher fetches it every 10 minutes when it runs)
const NODES_STALE_NS: u64 = 900_000_000_000;

/// A QUIC client endpoint as a leader's TPU expects one: ALPN "solana-tpu", a self-signed client certificate, the
/// server's certificate not checked; 1 s keep-alives, 10 s idle timeout. Needs a tokio runtime (it spawns its driver)
pub fn quic_client() -> Result<quinn::Endpoint> {
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let key = rcgen::KeyPair::generate_for(&rcgen::PKCS_ED25519).context("client key")?;
    let cert = rcgen::CertificateParams::new(vec!["solana".to_string()])?.self_signed(&key)?;
    let mut tls = rustls::ClientConfig::builder_with_provider(provider.clone()).with_protocol_versions(&[&rustls::version::TLS13])?
        .dangerous().with_custom_certificate_verifier(Arc::new(AcceptAny(provider.clone())))
        .with_client_auth_cert(vec![cert.der().clone()], rustls::pki_types::PrivateKeyDer::Pkcs8(key.serialize_der().into()))?;
    tls.alpn_protocols = vec![ALPN.to_vec()];
    tls.enable_early_data = true;
    let mut cfg = quinn::ClientConfig::new(Arc::new(quinn::crypto::rustls::QuicClientConfig::try_from(tls)?));
    let mut transport = quinn::TransportConfig::default();
    transport.keep_alive_interval(Some(Duration::from_secs(1)));
    transport.max_idle_timeout(Some(Duration::from_secs(10).try_into()?));
    cfg.transport_config(Arc::new(transport));
    let mut endpoint = quinn::Endpoint::client("0.0.0.0:0".parse()?)?;
    endpoint.set_default_client_config(cfg);
    Ok(endpoint)
}

pub struct Tpu {
    rpc_url: String,
    /// sent as `Authorization: Bearer <key>` when the RPC wants one (Haan)
    bearer: Option<String>,
    http: reqwest::Client,
    endpoint: quinn::Endpoint,
    /// the run's LeaderBook (`leaders::installed`), else one of its own
    book: Arc<LeaderBook>,
    conns: tokio::sync::Mutex<HashMap<SocketAddr, quinn::Connection>>,
}

impl Tpu {
    /// `rpc_url` answers getSlotLeaders / getClusterNodes (any RPC; the leader schedule is public)
    pub async fn new(rpc_url: String, bearer: Option<String>) -> Result<Arc<Tpu>> {
        let endpoint = quic_client()?;
        let http = reqwest::Client::builder().timeout(Duration::from_secs(10)).build()?;
        let book = crate::leaders::installed().unwrap_or_else(|| LeaderBook::new(crate::rec::Rec::off()));
        let t = Arc::new(Tpu { rpc_url, bearer, http, endpoint, book, conns: Default::default() });
        // a refused first read (rate limit) must not drop the path for a whole run: a few tries (unless the run's book
        // already holds a fresh node table)
        let mut tries = 0;
        while t.book.nodes_age(crate::feeds::clock::now_ns()).is_none_or(|a| a > NODES_STALE_NS) {
            match t.refresh_nodes().await {
                Ok(()) => break,
                Err(e) if tries < 4 => { tries += 1; tokio::time::sleep(Duration::from_millis(700 * tries)).await; let _ = e; }
                Err(e) => return Err(e),
            }
        }
        // the current slot, until the engine's state stream takes over (and for checks run without an engine)
        if let Some(s) = t.rpc("getSlot", json!([{ "commitment": "processed" }])).await.ok().and_then(|v| v.as_u64()) {
            let _ = SLOT.compare_exchange(0, s, Ordering::Relaxed, Ordering::Relaxed);
            if t.book.leader(s + 50).is_none() { t.refresh_leaders(s).await?; }
        }
        Ok(t)
    }

    async fn rpc(&self, method: &str, params: Value) -> Result<Value> {
        let mut req = self.http.post(&self.rpc_url).json(&json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": params }));
        if let Some(b) = &self.bearer { req = req.bearer_auth(b); }
        let bytes = req.send().await.map_err(|e| anyhow::anyhow!("tpu {method}: {}", e.without_url()))?.bytes().await?;
        // review F8: getClusterNodes is megabytes of JSON; this runs on rt_hot (in `arbx run` the LeaderBook's refresher
        // keeps the book fresh from rt_bg, and this path fetches only what it lacks), so a large reply is parsed off its
        // workers
        let r: Value = if bytes.len() > crate::runtime::LARGE_REPLY {
            tokio::task::spawn_blocking(move || serde_json::from_slice::<Value>(&bytes)).await.map_err(|e| anyhow::anyhow!("tpu {method}: parse task: {e}"))??
        } else {
            serde_json::from_slice(&bytes)?
        };
        if let Some(e) = r.get("error") { bail!("tpu {method}: {e}"); }
        r.get("result").cloned().context("no result")
    }

    /// every validator's TPU QUIC address (tpuQuic, else tpu + 6), into the LeaderBook
    pub async fn refresh_nodes(&self) -> Result<()> {
        let nodes = self.rpc("getClusterNodes", json!([])).await?;
        self.book.set_nodes(crate::leaders::parse_cluster_nodes(&nodes)?, crate::feeds::clock::now_ns());
        Ok(())
    }

    /// the leaders of the next 400 slots from `slot`, into the LeaderBook (not the refresher's window: its own schedule
    /// and engine inputs stay its own)
    pub async fn refresh_leaders(&self, slot: u64) -> Result<()> {
        let r = self.rpc("getSlotLeaders", json!([slot, crate::leaders::WINDOW])).await?;
        self.book.fill_window(slot, &crate::leaders::parse_slot_leaders(&r).context("getSlotLeaders")?);
        Ok(())
    }

    /// TPU addresses of the next `n` distinct leaders from the current slot
    fn targets(&self, n: usize) -> Vec<(String, SocketAddr)> {
        self.book.next_leaders(SLOT.load(Ordering::Relaxed), n).into_iter().map(|(id, a)| (crate::tx::b58(&id), a)).collect()
    }

    async fn conn(&self, addr: SocketAddr) -> Result<quinn::Connection> {
        if let Some(c) = self.conns.lock().await.get(&addr) { if c.close_reason().is_none() { return Ok(c.clone()); } }
        let c = tokio::time::timeout(Duration::from_secs(2), self.endpoint.connect(addr, "connect")?).await.context("quic connect timed out")??;
        let mut m = self.conns.lock().await;
        if m.len() > 32 { m.retain(|_, c| c.close_reason().is_none()); }
        m.insert(addr, c.clone());
        Ok(c)
    }

    /// Write one transaction to the current leader and the next distinct one; Ok(names) of those that took the stream.
    pub async fn send(&self, raw: &[u8]) -> Result<Vec<String>> {
        let targets = self.targets(FANOUT);
        if targets.is_empty() { bail!("tpu: no leader known for slot {}", SLOT.load(Ordering::Relaxed)); }
        let mut ok = Vec::new();
        let mut errs = Vec::new();
        // both leaders at once (a slow or cold one must not hold up the other), each write capped at 300 ms
        let one = |id: &str, a: SocketAddr| { let id = id.to_string(); async move {
            let r: Result<()> = match tokio::time::timeout(Duration::from_millis(300), async {
                let c = self.conn(a).await?;
                let mut s = c.open_uni().await?;
                s.write_all(raw).await?;
                s.finish()?;
                Ok::<(), anyhow::Error>(())
            }).await { Ok(r) => r, Err(_) => Err(anyhow::anyhow!("timed out")) };
            (id, r)
        } };
        let results = match targets.as_slice() {
            [] => vec![],
            [(i0, a0)] => vec![one(i0, *a0).await],
            [(i0, a0), (i1, a1)] => { let (x, y) = tokio::join!(one(i0, *a0), one(i1, *a1)); vec![x, y] }
            // FANOUT>=3: write to the current leader and the next two distinct ones at once, so a slot roll between
            // our read and our land still finds a leader that already has the tx (and all connections are pre-warmed).
            [(i0, a0), (i1, a1), (i2, a2), ..] => { let (x, y, z) = tokio::join!(one(i0, *a0), one(i1, *a1), one(i2, *a2)); vec![x, y, z] }
        };
        for (id, r) in results {
            match r { Ok(()) => ok.push(id[..8].to_string()), Err(e) => errs.push(format!("{}: {e:#}", &id[..8])) }
        }
        if ok.is_empty() { bail!("tpu: no leader took it ({})", errs.join("; ")); }
        Ok(ok)
    }

    /// a check: open (or reuse) the QUIC connection to the next leader; how long it took and which leader
    pub async fn connect_next(&self) -> Result<(Duration, String)> {
        let (id, a) = self.targets(1).into_iter().next().context("tpu: no leader known")?;
        let t = std::time::Instant::now();
        self.conn(a).await?;
        Ok((t.elapsed(), format!("{} at {a}", &id[..8])))
    }

    /// keep the next leaders' connections open until `stop`, and the book's schedule and nodes fresh when no one else
    /// does (the slot 50 ahead unknown; the node table older than 15 minutes)
    pub async fn keep_warm(self: Arc<Self>, stop: Arc<std::sync::atomic::AtomicBool>) {
        while !stop.load(Ordering::Relaxed) {
            let slot = SLOT.load(Ordering::Relaxed);
            if slot > 0 && self.book.leader(slot + 50).is_none() { let _ = self.refresh_leaders(slot).await; }
            if self.book.nodes_age(crate::feeds::clock::now_ns()).is_none_or(|a| a > NODES_STALE_NS) { let _ = self.refresh_nodes().await; }
            // Pre-warm the next 8 leaders (up from 4): keeps QUIC open further ahead so a send never pays an 82ms
            // cold handshake when the leader window rolls (the measured cause of some +1 lands).
            for (_, a) in self.targets(8) { let _ = self.conn(a).await; }
            tokio::time::sleep(Duration::from_millis(400)).await;
        }
    }
}

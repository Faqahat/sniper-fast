//! dip17 (10-25 PKT): QUIC landing lanes, `kind = "soyas"` and `kind = "solami"` (one client, two tip lists). Each path keeps ONE
//! persistent QUIC connection to its lane (`url = "quic://host:port"`), opened and checked at start:
//!   identity  the lane's whitelisted key (`identity_env`: a base58 64-byte Solana keypair, never the payer's) as a Solana-style
//!             dummy X.509 client certificate (byte-for-byte solana_tls_utils::new_dummy_x509_certificate, Agave's own: an Ed25519
//!             SubjectPublicKeyInfo of the key and a deliberately invalid signature; the TLS 1.3 CertificateVerify proves the key)
//!   tls       ALPN `solana-tpu` (default), SNI from config (soyas-landing / solami-beam), the server's certificate not checked
//!   auth      after the handshake we wait AUTH_WAIT (300 ms): a lane that does not know the key closes the connection then
//!             (Soyas docs: "connection closed -> not whitelisted"); the close reason is logged and the path is unhealthy
//!   send      one unidirectional stream per transaction: the raw wire bytes (= bincode::serialize(VersionedTransaction)), finish.
//!             Fire-and-forget (no reply). A dead connection or a failed write: ONE reconnect (capped) and one retry
//!   alive     QUIC keep-alives (`keepalive_ms`, 25 s) below the idle timeout (`idle_ms`, 30 s); the path's keep-alive tick
//!             (Paths::start, every 2 s) reads the connection: alive = healthy (its RTT recorded), dead = reconnect (backoff
//!             2 s .. 60 s while the lane keeps refusing)
//! Sources: Soyas' docs (owner, 10-25; the catalogue's soyas entry); Solami: the `solami` crate 0.1.58 source (src/swqos.rs,
//! src/config.rs; read, not built: /home/moiz/sniper-data/solami_src/): beam `{fra.|ams.|nyc.|}beam.solami.dev:11000`, SNI
//! "solami-beam", ALPN "solana-tpu", the same dummy certificate, bincode bytes on one uni stream, keep-alive 25 s.
use anyhow::{bail, Context, Result};
use std::net::SocketAddr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, Instant};

/// the lane's auth check: a server that does not accept the key closes the connection within this
pub const AUTH_WAIT: Duration = Duration::from_millis(300);
/// a connect from the keep-alive tick (and the start)
const CONNECT_TIMEOUT: Duration = Duration::from_secs(3);
/// a reconnect on the send path: a copy later than this is worthless (and the buy's slot guard would fail it on chain)
const SEND_RECONNECT_TIMEOUT: Duration = Duration::from_millis(400);
/// one stream write (open + write + finish: buffered locally, no round trip unless the stream credit is exhausted)
const WRITE_TIMEOUT: Duration = Duration::from_millis(300);
const BACKOFF_MIN_S: u64 = 2;
const BACKOFF_MAX_S: u64 = 60;
pub const DEFAULT_ALPN: &str = "solana-tpu";
pub const DEFAULT_KEEPALIVE_MS: u64 = 25_000;
pub const DEFAULT_IDLE_MS: u64 = 30_000;

/// A lane's key: the 32-byte Ed25519 seed (wiped on drop, never printed) and its public key
pub struct Identity { seed: [u8; 32], pub pubkey: [u8; 32] }
impl Drop for Identity { fn drop(&mut self) { self.seed = [0u8; 32]; } }
impl std::fmt::Debug for Identity {
    fn fmt(&self, f: &mut std::fmt::Formatter) -> std::fmt::Result { write!(f, "Identity({})", bs58::encode(self.pubkey).into_string()) }
}
impl Identity {
    /// a base58 64-byte Solana keypair (secret then public half; the halves must agree), a base58 32-byte seed, or a
    /// solana-keygen JSON byte array of either. Errors never quote the value
    pub fn from_secret(s: &str) -> Result<Identity> {
        let t = s.trim();
        let bytes: Vec<u8> = if t.starts_with('[') { serde_json::from_str::<Vec<u8>>(t).map_err(|_| anyhow::anyhow!("not a JSON byte array"))? }
            else { bs58::decode(t).into_vec().map_err(|_| anyhow::anyhow!("not base58"))? };
        if bytes.len() != 64 && bytes.len() != 32 { bail!("a keypair is 64 bytes (or a 32-byte seed), this is {}", bytes.len()); }
        let mut seed = [0u8; 32];
        seed.copy_from_slice(&bytes[..32]);
        let pubkey = ed25519_dalek::SigningKey::from_bytes(&seed).verifying_key().to_bytes();
        if bytes.len() == 64 && bytes[32..] != pubkey { bail!("the keypair's public half does not match its secret half"); }
        Ok(Identity { seed, pubkey })
    }
    /// the keypair in the environment variable `var` (the env file: /root/sniper/deploy/.env)
    pub fn from_env(var: &str) -> Result<Identity> {
        let v = std::env::var(var).ok().filter(|v| !v.trim().is_empty()).with_context(|| format!("the environment has no {var} (the lane's keypair)"))?;
        Identity::from_secret(&v).with_context(|| format!("{var} is not a Solana keypair"))
    }
    pub fn pubkey_b58(&self) -> String { bs58::encode(self.pubkey).into_string() }
}

/// solana_tls_utils::new_dummy_x509_certificate (solana-tls-utils 4.3.2, src/tls_certificates.rs; the solami crate's client
/// certificate), byte for byte: the PKCS#8 v1 Ed25519 key of the seed, and a certificate whose only meaningful field is the
/// SubjectPublicKeyInfo (the key's public half) with a deliberately invalid signature (the lane reads the key from it; the TLS
/// 1.3 CertificateVerify proves we hold it)
pub fn dummy_x509(id: &Identity) -> (rustls::pki_types::CertificateDer<'static>, rustls::pki_types::PrivateKeyDer<'static>) {
    const PKCS8_PREFIX: [u8; 16] = [0x30, 0x2e, 0x02, 0x01, 0x00, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x04, 0x22, 0x04, 0x20];
    let mut key = Vec::with_capacity(48);
    key.extend_from_slice(&PKCS8_PREFIX);
    key.extend_from_slice(&id.seed);
    let mut cert = Vec::with_capacity(0xf9);
    cert.extend_from_slice(&[
        0x30, 0x81, 0xf6, 0x30, 0x81, 0xa9, 0xa0, 0x03, 0x02, 0x01, 0x02, 0x02, 0x08, 0x01, 0x01,
        0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x30, 0x16,
        0x31, 0x14, 0x30, 0x12, 0x06, 0x03, 0x55, 0x04, 0x03, 0x0c, 0x0b, 0x53, 0x6f, 0x6c, 0x61,
        0x6e, 0x61, 0x20, 0x6e, 0x6f, 0x64, 0x65, 0x30, 0x20, 0x17, 0x0d, 0x37, 0x30, 0x30, 0x31,
        0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x5a, 0x18, 0x0f, 0x34, 0x30, 0x39, 0x36,
        0x30, 0x31, 0x30, 0x31, 0x30, 0x30, 0x30, 0x30, 0x30, 0x30, 0x5a, 0x30, 0x00, 0x30, 0x2a,
        0x30, 0x05, 0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x21, 0x00,
    ]);
    cert.extend_from_slice(&id.pubkey);
    cert.extend_from_slice(&[
        0xa3, 0x29, 0x30, 0x27, 0x30, 0x17, 0x06, 0x03, 0x55, 0x1d, 0x11, 0x01, 0x01, 0xff, 0x04,
        0x0d, 0x30, 0x0b, 0x82, 0x09, 0x6c, 0x6f, 0x63, 0x61, 0x6c, 0x68, 0x6f, 0x73, 0x74, 0x30,
        0x0c, 0x06, 0x03, 0x55, 0x1d, 0x13, 0x01, 0x01, 0xff, 0x04, 0x02, 0x30, 0x00, 0x30, 0x05,
        0x06, 0x03, 0x2b, 0x65, 0x70, 0x03, 0x41, 0x00,
    ]);
    cert.extend_from_slice(&[0xff; 64]);
    (rustls::pki_types::CertificateDer::from(cert), rustls::pki_types::PrivateKeyDer::Pkcs8(key.into()))
}

/// `quic://host:port` -> (host, port)
pub fn parse_quic_url(url: &str) -> Result<(String, u16)> {
    let rest = url.trim().strip_prefix("quic://").context("a QUIC lane's url is quic://host:port")?.trim_end_matches('/');
    let (host, port) = rest.rsplit_once(':').context("a QUIC lane's url needs a port (quic://host:port)")?;
    if host.is_empty() || host.contains('/') || host.contains('?') { bail!("a QUIC lane's url is quic://host:port (no path, no query)"); }
    Ok((host.to_string(), port.parse().context("the QUIC lane's port is not a number")?))
}

/// One lane's settings (from the [[send]] entry, defaults per kind: config::SendPath::quic_settings)
#[derive(Clone, Debug, PartialEq)]
pub struct LaneCfg { pub host: String, pub port: u16, pub sni: String, pub alpn: String, pub keepalive_ms: u64, pub idle_ms: u64 }

/// The QUIC client config of a lane: TLS 1.3 (ring), the server's certificate not checked, `id`'s dummy certificate as the
/// client certificate (rustls checks that it carries the key's public half), ALPN; keep-alive and idle timeout
pub fn client_config(id: &Identity, alpn: &str, keepalive_ms: u64, idle_ms: u64) -> Result<quinn::ClientConfig> {
    let provider = Arc::new(rustls::crypto::ring::default_provider());
    let (cert, key) = dummy_x509(id);
    let mut tls = rustls::ClientConfig::builder_with_provider(provider.clone()).with_protocol_versions(&[&rustls::version::TLS13])?
        .dangerous().with_custom_certificate_verifier(Arc::new(super::tpu::AcceptAny(provider)))
        .with_client_auth_cert(vec![cert], key).context("client certificate")?;
    tls.alpn_protocols = vec![alpn.as_bytes().to_vec()];
    let mut cfg = quinn::ClientConfig::new(Arc::new(quinn::crypto::rustls::QuicClientConfig::try_from(tls)?));
    let mut transport = quinn::TransportConfig::default();
    transport.keep_alive_interval(Some(Duration::from_millis(keepalive_ms)));
    transport.max_idle_timeout(Some(Duration::from_millis(idle_ms).try_into().context("idle_ms")?));
    cfg.transport_config(Arc::new(transport));
    Ok(cfg)
}

/// a closed connection's reason, as the peer gave it (application / transport code and reason text)
pub fn close_text(e: &quinn::ConnectionError) -> String {
    match e {
        quinn::ConnectionError::ApplicationClosed(c) => format!("closed by the server: application code {} reason {:?}", c.error_code, String::from_utf8_lossy(&c.reason)),
        quinn::ConnectionError::ConnectionClosed(c) => format!("closed by the server: transport code {} reason {:?}", c.error_code, String::from_utf8_lossy(&c.reason)),
        e => e.to_string(),
    }
}

/// what a connect found
#[derive(Debug)]
pub enum Auth {
    /// the connection survived the auth wait: (handshake time, the server's address, the ALPN it agreed)
    Ok { handshake: Duration, addr: SocketAddr, alpn: Option<String> },
    /// the server closed it within the auth wait (or refused the handshake): not whitelisted, or a wrong SNI / ALPN
    Closed { reason: String, after: Duration },
}

pub struct QuicLane {
    pub name: String,
    pub cfg: LaneCfg,
    pub pubkey: [u8; 32],
    endpoint: quinn::Endpoint,
    client: quinn::ClientConfig,
    conn: RwLock<Option<quinn::Connection>>,
    reconnecting: tokio::sync::Mutex<()>,
    /// keep-alive tick: no reconnect before this (backoff while the lane refuses)
    next_try: Mutex<Option<Instant>>,
    backoff_s: AtomicU64,
    /// the last close / connect failure (logged once per edge)
    pub last_close: Mutex<Option<String>>,
    pub connects: AtomicU64,
    pub sent: AtomicU64,
}

impl QuicLane {
    /// the lane's endpoint (one UDP socket) and client config; no connection yet. Needs a tokio runtime
    pub fn new(name: &str, cfg: LaneCfg, id: &Identity) -> Result<Arc<QuicLane>> {
        let client = client_config(id, &cfg.alpn, cfg.keepalive_ms, cfg.idle_ms)?;
        let endpoint = quinn::Endpoint::client("0.0.0.0:0".parse()?).context("quic endpoint")?;
        Ok(Arc::new(QuicLane { name: name.to_string(), cfg, pubkey: id.pubkey, endpoint, client, conn: RwLock::new(None), reconnecting: tokio::sync::Mutex::new(()),
            next_try: Mutex::new(None), backoff_s: AtomicU64::new(0), last_close: Mutex::new(None), connects: AtomicU64::new(0), sent: AtomicU64::new(0) }))
    }

    fn short_key(&self) -> String { bs58::encode(self.pubkey).into_string().chars().take(8).collect() }

    /// the host's IPv4 address (the endpoint is bound on 0.0.0.0)
    async fn resolve(&self) -> Result<SocketAddr> {
        let hp = format!("{}:{}", self.cfg.host, self.cfg.port);
        let mut v4 = None;
        for a in tokio::net::lookup_host(hp.as_str()).await.with_context(|| format!("resolve {}", self.cfg.host))? { if a.is_ipv4() { v4 = Some(a); break; } }
        v4.with_context(|| format!("{} has no IPv4 address", self.cfg.host))
    }

    /// handshake only (no auth wait): (connection, handshake time, address)
    async fn handshake(&self, cap: Duration) -> Result<(quinn::Connection, Duration, SocketAddr), String> {
        let t = Instant::now();
        let addr = tokio::time::timeout(cap, self.resolve()).await.map_err(|_| "resolve timed out".to_string())?.map_err(|e| format!("{e:#}"))?;
        let connecting = self.endpoint.connect_with(self.client.clone(), addr, &self.cfg.sni).map_err(|e| format!("connect {addr}: {e}"))?;
        let left = cap.saturating_sub(t.elapsed());
        match tokio::time::timeout(left, connecting).await {
            Err(_) => Err(format!("handshake with {addr} timed out ({} ms)", cap.as_millis())),
            Ok(Err(e)) => Err(format!("handshake with {addr} failed: {}", close_text(&e))),
            Ok(Ok(c)) => { self.connects.fetch_add(1, Ordering::Relaxed); Ok((c, t.elapsed(), addr)) }
        }
    }

    /// Connect and check: the handshake, then `auth_wait` for the server to close it (not whitelisted). Ok(Auth::Ok): the
    /// connection is the lane's now. Err: no handshake (unreachable, timed out)
    pub async fn connect(&self, auth_wait: Duration) -> Result<Auth> {
        let _g = self.reconnecting.lock().await;
        let t = Instant::now();
        let (c, hs, addr) = match self.handshake(CONNECT_TIMEOUT).await {
            Ok(x) => x,
            // a TLS alert / close during the handshake is the lane refusing us, as a close after it is
            Err(e) if e.contains("closed by the server") || e.contains("failed:") => return Ok(Auth::Closed { reason: e, after: t.elapsed() }),
            Err(e) => bail!(e),
        };
        if !auth_wait.is_zero() {
            if let Ok(e) = tokio::time::timeout(auth_wait, c.closed()).await {
                return Ok(Auth::Closed { reason: close_text(&e), after: t.elapsed() });
            }
        }
        let alpn = c.handshake_data().and_then(|d| d.downcast::<quinn::crypto::rustls::HandshakeData>().ok()).and_then(|h| h.protocol.clone())
            .map(|p| String::from_utf8_lossy(&p).into_owned());
        *self.conn.write().unwrap_or_else(|e| e.into_inner()) = Some(c);
        Ok(Auth::Ok { handshake: hs, addr, alpn })
    }

    /// the open connection, if it is alive (a closed one is dropped and its reason kept)
    pub fn alive(&self) -> Option<quinn::Connection> {
        let c = self.conn.read().unwrap_or_else(|e| e.into_inner()).clone()?;
        match c.close_reason() {
            None => Some(c),
            Some(e) => {
                let why = close_text(&e);
                let mut g = self.conn.write().unwrap_or_else(|e| e.into_inner());
                if g.as_ref().is_some_and(|x| x.stable_id() == c.stable_id()) { *g = None; }
                drop(g);
                self.note_down(&why);
                None
            }
        }
    }

    fn note_down(&self, why: &str) {
        let mut l = self.last_close.lock().unwrap_or_else(|e| e.into_inner());
        if l.as_deref() != Some(why) {
            eprintln!("  QUIC-LANE {}: connection DOWN: {why}", self.name);
            *l = Some(why.to_string());
        }
    }

    async fn write(c: &quinn::Connection, raw: &[u8]) -> Result<(), String> {
        match tokio::time::timeout(WRITE_TIMEOUT, async {
            let mut s = c.open_uni().await.map_err(|e| format!("open stream: {}", close_text(&e)))?;
            s.write_all(raw).await.map_err(|e| format!("write: {e}"))?;
            s.finish().map_err(|e| format!("finish: {e}"))?;
            Ok::<(), String>(())
        }).await { Ok(r) => r, Err(_) => Err(format!("write timed out ({} ms)", WRITE_TIMEOUT.as_millis())) }
    }

    /// Fire-and-forget: one uni stream with the transaction's wire bytes. A dead connection or a failed write: one reconnect
    /// (no auth wait, capped at SEND_RECONNECT_TIMEOUT) and one retry. Ok: what happened ("sent" / "sent after reconnect")
    pub async fn send(&self, raw: &[u8]) -> Result<&'static str> {
        let first = match self.alive() {
            Some(c) => match Self::write(&c, raw).await { Ok(()) => { self.sent.fetch_add(1, Ordering::Relaxed); return Ok("quic stream written"); } Err(e) => e },
            None => "not connected".to_string(),
        };
        let c = {
            let _g = match tokio::time::timeout(SEND_RECONNECT_TIMEOUT, self.reconnecting.lock()).await { Ok(g) => g, Err(_) => bail!("{first}; a reconnect is under way") };
            match self.alive() {
                Some(c) => c,
                None => {
                    let (c, _, _) = self.handshake(SEND_RECONNECT_TIMEOUT).await.map_err(|e| anyhow::anyhow!("{first}; reconnect: {e}"))?;
                    *self.conn.write().unwrap_or_else(|e| e.into_inner()) = Some(c.clone());
                    c
                }
            }
        };
        Self::write(&c, raw).await.map_err(|e| anyhow::anyhow!("{first}; after reconnect: {e}"))?;
        self.sent.fetch_add(1, Ordering::Relaxed);
        Ok("quic stream written after reconnect")
    }

    /// The keep-alive tick: alive -> Some(its RTT estimate); dead -> one connect + auth check (not before the backoff
    /// allows: None = skipped). Err: the lane refused us or is unreachable (the reason; also logged on its first edge)
    pub async fn warm(&self) -> Result<Option<Duration>> {
        if let Some(c) = self.alive() { return Ok(Some(c.rtt())); }
        if self.next_try.lock().unwrap_or_else(|e| e.into_inner()).is_some_and(|t| Instant::now() < t) { return Ok(None); }
        let r = self.connect(AUTH_WAIT).await;
        match r {
            Ok(Auth::Ok { handshake, addr, alpn }) => {
                self.backoff_s.store(0, Ordering::Relaxed);
                *self.next_try.lock().unwrap_or_else(|e| e.into_inner()) = None;
                let was = self.last_close.lock().unwrap_or_else(|e| e.into_inner()).take();
                eprintln!("  QUIC-LANE {}: CONNECTED {addr} sni={} alpn={} as {} in {:.1} ms; auth check passed ({} ms){}", self.name, self.cfg.sni,
                    alpn.as_deref().unwrap_or("-"), self.short_key(), handshake.as_secs_f64() * 1e3, AUTH_WAIT.as_millis(),
                    was.map(|w| format!(" (was down: {w})")).unwrap_or_default());
                Ok(Some(handshake))
            }
            Ok(Auth::Closed { reason, after }) => {
                self.back_off();
                let why = format!("AUTH FAILED: {reason} {:.0} ms after connecting (is key {} whitelisted for sni {}?)", after.as_secs_f64() * 1e3, self.short_key(), self.cfg.sni);
                self.note_down(&why);
                bail!(why)
            }
            Err(e) => { self.back_off(); let why = format!("connect failed: {e:#}"); self.note_down(&why); Err(anyhow::anyhow!(why)) }
        }
    }

    fn back_off(&self) {
        let b = self.backoff_s.load(Ordering::Relaxed);
        let n = if b == 0 { BACKOFF_MIN_S } else { (b * 2).min(BACKOFF_MAX_S) };
        self.backoff_s.store(n, Ordering::Relaxed);
        *self.next_try.lock().unwrap_or_else(|e| e.into_inner()) = Some(Instant::now() + Duration::from_secs(n));
    }

    /// close the connection (the end of a check / run)
    pub fn close(&self) {
        if let Some(c) = self.conn.write().unwrap_or_else(|e| e.into_inner()).take() { c.close(0u32.into(), b"bye"); }
    }
}

/// CONNECT-ONLY CHECK (snipe_engine --quic-check; sends NO stream, so no transaction): connect `lane`, the auth check, then
/// hold the connection `hold` (past the idle timeout: the keep-alives must keep it), and report per step. Returns
/// (passed, lines)
pub async fn connect_check(lane: &QuicLane, hold: Duration) -> (bool, Vec<String>) {
    let mut out = vec![format!("{}: quic://{}:{} sni={} alpn={} keepalive={} ms idle={} ms identity={}", lane.name, lane.cfg.host, lane.cfg.port, lane.cfg.sni,
        lane.cfg.alpn, lane.cfg.keepalive_ms, lane.cfg.idle_ms, bs58::encode(lane.pubkey).into_string())];
    match lane.connect(AUTH_WAIT).await {
        Err(e) => { out.push(format!("  FAIL connect: {e:#}")); return (false, out); }
        Ok(Auth::Closed { reason, after }) => {
            out.push(format!("  FAIL auth: {reason} ({:.0} ms after connecting) -> the lane does not accept this key / sni / alpn", after.as_secs_f64() * 1e3));
            return (false, out);
        }
        Ok(Auth::Ok { handshake, addr, alpn }) => out.push(format!("  ok   handshake {:.1} ms to {addr}, alpn {}; still open after the {} ms auth wait",
            handshake.as_secs_f64() * 1e3, alpn.as_deref().unwrap_or("-"), AUTH_WAIT.as_millis())),
    }
    let t = Instant::now();
    let mut ok = true;
    while t.elapsed() < hold {
        tokio::time::sleep(Duration::from_secs(5).min(hold.saturating_sub(t.elapsed()))).await;
        match lane.alive() {
            Some(c) => out.push(format!("  ok   alive at {:>4.1} s, rtt {:.2} ms", t.elapsed().as_secs_f64(), c.rtt().as_secs_f64() * 1e3)),
            None => {
                let why = lane.last_close.lock().unwrap_or_else(|e| e.into_inner()).clone().unwrap_or_default();
                out.push(format!("  FAIL closed at {:.1} s: {why}", t.elapsed().as_secs_f64()));
                ok = false;
                break;
            }
        }
    }
    lane.close();
    out.push(format!("  {}: {}", if ok { "PASS" } else { "FAIL" }, lane.name));
    (ok, out)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// a fixed test keypair (seed [7; 32]) as base58 64 bytes
    fn kp58(seed: u8) -> String {
        let sk = ed25519_dalek::SigningKey::from_bytes(&[seed; 32]);
        let mut b = [seed; 32].to_vec();
        b.extend_from_slice(&sk.verifying_key().to_bytes());
        bs58::encode(b).into_string()
    }

    #[test]
    fn identity_parses_keypairs_and_never_quotes_them() {
        let id = Identity::from_secret(&kp58(7)).unwrap();
        assert_eq!(id.pubkey, ed25519_dalek::SigningKey::from_bytes(&[7; 32]).verifying_key().to_bytes());
        assert_eq!(Identity::from_secret(&bs58::encode([7u8; 32]).into_string()).unwrap().pubkey, id.pubkey, "a 32-byte seed");
        let json = serde_json::to_string(&bs58::decode(kp58(7)).into_vec().unwrap()).unwrap();
        assert_eq!(Identity::from_secret(&json).unwrap().pubkey, id.pubkey, "a solana-keygen JSON array");
        // halves that disagree, a wrong length, not base58: refused, the value never in the message
        let mut bad = bs58::decode(kp58(7)).into_vec().unwrap();
        bad[40] ^= 1;
        let s = bs58::encode(&bad).into_string();
        let e = format!("{:#}", Identity::from_secret(&s).unwrap_err());
        assert!(e.contains("does not match") && !e.contains(&s[..20]), "{e}");
        assert!(Identity::from_secret(&bs58::encode([1u8; 40]).into_string()).is_err());
        assert!(Identity::from_secret("0OIl not base58").is_err());
        assert!(!format!("{id:?}").contains(&kp58(7)[..20]), "Debug shows the public key only");
        std::env::set_var("ARB_TEST_QL_KP", kp58(7));
        assert_eq!(Identity::from_env("ARB_TEST_QL_KP").unwrap().pubkey, id.pubkey);
        assert!(format!("{:#}", Identity::from_env("ARB_TEST_QL_MISSING").unwrap_err()).contains("ARB_TEST_QL_MISSING"));
    }

    /// the certificate is solana_tls_utils' bytes with our key in it: the fixed template (249 bytes), the SPKI = the public
    /// key at offset 100, the 64 0xff signature; rustls accepts it as our key's (CertifiedKey::from_der checks the SPKI against
    /// the private key: a certificate of another key is refused), and the PKCS#8 is the seed
    #[test]
    fn dummy_certificate_is_agaves_with_our_key() {
        let id = Identity::from_secret(&kp58(9)).unwrap();
        let (cert, key) = dummy_x509(&id);
        let c = cert.as_ref();
        assert_eq!(c.len(), 0xf9, "SEQUENCE 0x81 0xf6 + 3 header bytes");
        assert_eq!(&c[..3], &[0x30, 0x81, 0xf6]);
        assert_eq!(&c[100..132], &id.pubkey, "the SubjectPublicKeyInfo's key");
        assert_eq!(&c[41..52], b"Solana node");
        assert!(c[c.len() - 64..].iter().all(|b| *b == 0xff));
        let k = match &key { rustls::pki_types::PrivateKeyDer::Pkcs8(k) => k.secret_pkcs8_der().to_vec(), _ => panic!("pkcs8") };
        assert_eq!((k.len(), &k[16..]), (48, &[9u8; 32][..]));
        let provider = rustls::crypto::ring::default_provider();
        rustls::sign::CertifiedKey::from_der(vec![cert.clone()], key.clone_key(), &provider).expect("rustls: the certificate carries the key's public half");
        let other = Identity::from_secret(&kp58(10)).unwrap();
        let (cert2, _) = dummy_x509(&other);
        assert!(rustls::sign::CertifiedKey::from_der(vec![cert2], key.clone_key(), &provider).is_err(), "another key's certificate is refused");
        assert!(client_config(&id, DEFAULT_ALPN, DEFAULT_KEEPALIVE_MS, DEFAULT_IDLE_MS).is_ok());
    }

    #[test]
    fn quic_urls() {
        assert_eq!(parse_quic_url("quic://fra.landing.soyas.xyz:9000").unwrap(), ("fra.landing.soyas.xyz".to_string(), 9000));
        assert_eq!(parse_quic_url("quic://fra.beam.solami.dev:11000/").unwrap(), ("fra.beam.solami.dev".to_string(), 11000));
        for bad in ["https://x:1", "quic://x", "quic://:9", "quic://x:port", "quic://x:9/send", "udp://x:9"] { assert!(parse_quic_url(bad).is_err(), "{bad}"); }
    }

    // ---- a local lane (nothing leaves the machine) ----------------------------------------------------------------------

    /// a client-certificate verifier that accepts any certificate but checks the CertificateVerify signature against the
    /// certificate's key (what a Solana QUIC server does) and hands the certificate to the test
    #[derive(Debug)]
    struct AnyClient(Arc<rustls::crypto::CryptoProvider>);
    impl rustls::server::danger::ClientCertVerifier for AnyClient {
        fn root_hint_subjects(&self) -> &[rustls::DistinguishedName] { &[] }
        fn verify_client_cert(&self, _: &rustls::pki_types::CertificateDer<'_>, _: &[rustls::pki_types::CertificateDer<'_>], _: rustls::pki_types::UnixTime)
            -> Result<rustls::server::danger::ClientCertVerified, rustls::Error> { Ok(rustls::server::danger::ClientCertVerified::assertion()) }
        fn verify_tls12_signature(&self, m: &[u8], c: &rustls::pki_types::CertificateDer<'_>, d: &rustls::DigitallySignedStruct)
            -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> { rustls::crypto::verify_tls12_signature(m, c, d, &self.0.signature_verification_algorithms) }
        fn verify_tls13_signature(&self, m: &[u8], c: &rustls::pki_types::CertificateDer<'_>, d: &rustls::DigitallySignedStruct)
            -> Result<rustls::client::danger::HandshakeSignatureValid, rustls::Error> { rustls::crypto::verify_tls13_signature(m, c, d, &self.0.signature_verification_algorithms) }
        fn supported_verify_schemes(&self) -> Vec<rustls::SignatureScheme> { self.0.signature_verification_algorithms.supported_schemes() }
    }

    enum Mode { Accept, CloseAfter(Duration) }

    /// a local lane on 127.0.0.1: ALPN solana-tpu; per connection: (SNI, client key from the certificate's SPKI) and every uni
    /// stream's bytes to the test; `Mode::CloseAfter`: close each connection that long after the handshake ("not whitelisted")
    async fn local_lane(mode: Mode) -> (u16, tokio::sync::mpsc::UnboundedReceiver<(String, [u8; 32])>, tokio::sync::mpsc::UnboundedReceiver<Vec<u8>>) {
        let provider = Arc::new(rustls::crypto::ring::default_provider());
        let skey = rcgen::KeyPair::generate_for(&rcgen::PKCS_ED25519).unwrap();
        let scert = rcgen::CertificateParams::new(vec!["lane".to_string()]).unwrap().self_signed(&skey).unwrap();
        let mut tls = rustls::ServerConfig::builder_with_provider(provider.clone()).with_protocol_versions(&[&rustls::version::TLS13]).unwrap()
            .with_client_cert_verifier(Arc::new(AnyClient(provider)))
            .with_single_cert(vec![scert.der().clone()], rustls::pki_types::PrivateKeyDer::Pkcs8(skey.serialize_der().into())).unwrap();
        tls.alpn_protocols = vec![b"solana-tpu".to_vec()];
        let sc = quinn::ServerConfig::with_crypto(Arc::new(quinn::crypto::rustls::QuicServerConfig::try_from(tls).unwrap()));
        let ep = quinn::Endpoint::server(sc, "127.0.0.1:0".parse().unwrap()).unwrap();
        let port = ep.local_addr().unwrap().port();
        let (ctx, crx) = tokio::sync::mpsc::unbounded_channel();
        let (stx, srx) = tokio::sync::mpsc::unbounded_channel();
        let close = match mode { Mode::Accept => None, Mode::CloseAfter(d) => Some(d) };
        tokio::spawn(async move {
            while let Some(inc) = ep.accept().await {
                let (ctx, stx) = (ctx.clone(), stx.clone());
                tokio::spawn(async move {
                    let Ok(c) = inc.await else { return };
                    let hd = c.handshake_data().unwrap().downcast::<quinn::crypto::rustls::HandshakeData>().unwrap();
                    let certs = c.peer_identity().unwrap().downcast::<Vec<rustls::pki_types::CertificateDer<'static>>>().unwrap();
                    let key: [u8; 32] = certs[0].as_ref()[100..132].try_into().unwrap();
                    let _ = ctx.send((hd.server_name.clone().unwrap_or_default(), key));
                    if let Some(d) = close { tokio::time::sleep(d).await; c.close(7u32.into(), b"not whitelisted"); return; }
                    while let Ok(mut s) = c.accept_uni().await { let _ = stx.send(s.read_to_end(4096).await.unwrap_or_default()); }
                });
            }
        });
        (port, crx, srx)
    }

    fn lane_cfg(port: u16, sni: &str) -> LaneCfg {
        LaneCfg { host: "127.0.0.1".into(), port, sni: sni.into(), alpn: DEFAULT_ALPN.into(), keepalive_ms: 1_000, idle_ms: 3_000 }
    }

    /// connect + auth check against a local lane: the server sees our SNI and our key (from the certificate, its CertificateVerify
    /// checked), the connection survives the auth wait; a send is one uni stream with exactly the transaction's bytes; a closed
    /// connection is noticed and the next send reconnects once and still delivers
    #[tokio::test(flavor = "multi_thread")]
    async fn local_lane_connect_auth_and_send() {
        let (port, mut conns, mut streams) = local_lane(Mode::Accept).await;
        let id = Identity::from_secret(&kp58(21)).unwrap();
        let lane = QuicLane::new("soyas-test", lane_cfg(port, "soyas-landing"), &id).unwrap();
        match lane.connect(AUTH_WAIT).await.unwrap() {
            Auth::Ok { alpn, .. } => assert_eq!(alpn.as_deref(), Some("solana-tpu")),
            a => panic!("{a:?}"),
        }
        let (sni, key) = conns.recv().await.unwrap();
        assert_eq!((sni.as_str(), key), ("soyas-landing", id.pubkey));
        let raw: Vec<u8> = (0..700u32).map(|i| (i * 7 + 1) as u8).collect();
        assert_eq!(lane.send(&raw).await.unwrap(), "quic stream written");
        assert_eq!(tokio::time::timeout(Duration::from_secs(2), streams.recv()).await.unwrap().unwrap(), raw, "one stream, the raw bytes");
        assert!(lane.warm().await.unwrap().is_some(), "alive: healthy");
        // the connection dies (as an idle timeout or a server restart would): the next send reconnects once and delivers
        lane.alive().unwrap().close(0u32.into(), b"test");
        tokio::time::sleep(Duration::from_millis(50)).await;
        assert!(lane.alive().is_none());
        assert_eq!(lane.send(&raw[..300]).await.unwrap(), "quic stream written after reconnect");
        assert_eq!(tokio::time::timeout(Duration::from_secs(2), streams.recv()).await.unwrap().unwrap(), raw[..300].to_vec());
        assert_eq!(lane.connects.load(Ordering::Relaxed), 2);
        // connect-only check: holds past the idle timeout (3 s) on keep-alives (1 s), no stream
        let (ok, lines) = connect_check(&lane, Duration::from_secs(4)).await;
        assert!(ok, "{lines:?}");
        assert!(tokio::time::timeout(Duration::from_millis(300), streams.recv()).await.is_err(), "the check wrote no stream");
    }

    /// a lane that closes the connection 100 ms after the handshake (not whitelisted): the auth check reports it with the
    /// server's reason, warm() is an error and then backs off (None), connect_check fails
    #[tokio::test(flavor = "multi_thread")]
    async fn local_lane_that_refuses_the_key() {
        let (port, _c, _s) = local_lane(Mode::CloseAfter(Duration::from_millis(100))).await;
        let lane = QuicLane::new("solami-test", lane_cfg(port, "solami-beam"), &Identity::from_secret(&kp58(22)).unwrap()).unwrap();
        match lane.connect(AUTH_WAIT).await.unwrap() {
            Auth::Closed { reason, after } => { assert!(reason.contains("not whitelisted") && reason.contains("code 7"), "{reason}"); assert!(after < AUTH_WAIT + Duration::from_millis(200)); }
            a => panic!("{a:?}"),
        }
        assert!(lane.alive().is_none());
        let e = format!("{:#}", lane.warm().await.unwrap_err());
        assert!(e.contains("AUTH FAILED") && e.contains("not whitelisted"), "{e}");
        assert!(lane.warm().await.unwrap().is_none(), "backing off");
        let (ok, lines) = connect_check(&lane, Duration::from_secs(1)).await;
        assert!(!ok && lines.iter().any(|l| l.contains("FAIL auth")), "{lines:?}");
    }

    /// nothing listens: connect is an error (no hang past the cap), send fails fast
    #[tokio::test(flavor = "multi_thread")]
    async fn dead_lane_fails_fast() {
        let port = std::net::UdpSocket::bind("127.0.0.1:0").unwrap().local_addr().unwrap().port();
        let lane = QuicLane::new("dead", lane_cfg(port, "x"), &Identity::from_secret(&kp58(23)).unwrap()).unwrap();
        let t = Instant::now();
        assert!(lane.send(&[1, 2, 3]).await.is_err());
        assert!(t.elapsed() < Duration::from_secs(1), "{:?}", t.elapsed());
    }
}

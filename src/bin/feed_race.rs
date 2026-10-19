//! feed_race: zero-cost feed race harness (/root/gap). Subscribes to every enabled `[[feed]]` of a TOML config in
//! parallel and logs, per feed, the local receive time of (a) every slot's first data, (b) every pump.fun transaction
//! (creates flagged), (c) every entry with its PoH position (entries feeds). Nothing is ever sent; no keys are read
//! except the feed tokens named by `token_env` (never printed or logged; URLs are never logged either).
//!
//! Kinds:
//!   jito-entries         gRPC /shredstream.ShredstreamProxy/SubscribeEntries (ShredStream-proxy style, erpc)
//!   yellowstone-deshred  gRPC /geyser.Geyser/SubscribeDeshred (Kaldera style), + slot statuses (first-shred-received)
//!   yellowstone-tx       gRPC /geyser.Geyser/Subscribe, processed transactions (executed; later by design)
//!   udp-shreds           raw shreds pushed to a local UDP port (bind = "0.0.0.0:PORT"), kernel SO_TIMESTAMPNS times
//!   udp-multicast        raw shreds on a multicast group (group, port, interface; DoubleZero Edge), kernel times
//!
//! Log lines (tab separated; t = CLOCK_REALTIME ns at receipt; kernel timestamp for udp-shreds):
//!   S feed t slot how                     first data of a slot seen by this feed (how = msg | shred | tx)
//!   U feed t slot status created_at       yellowstone slot status update (3 = first shred received at the provider)
//!   E feed t slot eidx hashes_cum ntx ticks_before   one entry (entries feeds), PoH position
//!   X feed t slot sig16 create eidx created_at       one pump transaction (eidx '-' if unknown; created_at 0 if none)
//!   R feed t slot sig16 create t_kernel_pkt t_batch t_start t_decoded   udp receive path (creates + 1/N txs)
//!   H feed t key=value ...                health every 30 s (msgs, txs, reconnects, errors, last error class)
//! Each feed task reconnects forever with backoff (1 s .. 10 s); a silent feed (FEED_IDLE_MS, default 15 s) is
//! reconnected; one feed failing never stops the others.
use anyhow::{bail, Context, Result};
use arbx::feeds::clock::now_ns;
use arbx::feeds::entries::parse_entries_poh;
use arbx::feeds::grpc::*;
use arbx::feeds::{shred, udp};
use arbx::tx::{parse_wire, Pk, Tx};
use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{mpsc, Arc, LazyLock};
use std::time::Duration;
use tonic::codec::ProstCodec;

static PUMP: LazyLock<Pk> = LazyLock::new(|| arbx::tx::pk("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"));
static MINT_AUTH: LazyLock<Pk> = LazyLock::new(|| arbx::tx::pk("TSLvdd1pWpHVjahSpsvCXUbgwsL3JAcvokwaKt1eokM"));
static STOP: AtomicBool = AtomicBool::new(false);

#[derive(serde::Deserialize)]
struct Cfg {
    #[serde(default)] env_file: Option<String>,
    #[serde(default)] feed: Vec<FeedCfg>,
}

#[derive(serde::Deserialize, Clone)]
struct FeedCfg {
    name: String,
    kind: String,
    #[serde(default = "yes")] enabled: bool,
    url: Option<String>,
    /// env var holding the token (looked up in the process env, then in env_file)
    token_env: Option<String>,
    /// literal token (discouraged; prefer token_env). Never logged.
    token: Option<String>,
    token_header: Option<String>,
    /// URL env var: the whole endpoint taken from the env (for endpoints that embed a key)
    url_env: Option<String>,
    #[serde(default)] account_include: Vec<String>,
    /// udp-shreds: local bind address, e.g. "0.0.0.0:20000"
    bind: Option<String>,
    /// udp-multicast: group, port, interface (DoubleZero Edge: 233.84.178.x, 7733, doublezero1)
    group: Option<String>,
    /// udp-multicast: several groups into ONE socket and ONE assembler (shreds of a data set may come from any group)
    #[serde(default)] groups: Vec<String>,
    port: Option<u16>,
    interface: Option<String>,
    /// yellowstone kinds: also subscribe slot statuses (default true; set false if the provider rejects it)
    slots: Option<bool>,
    /// udp-shreds: spin on non-blocking recvmmsg instead of sleeping in the kernel (costs one core while running)
    #[serde(default)] busy_poll: bool,
    /// udp-shreds: pin the receive thread to this CPU
    cpu: Option<usize>,
    /// udp-shreds: log an R (receive path) line for 1 in N non-create pump txs (creates always); 0 = creates only
    #[serde(default)] rpath_sample: u64,
}
fn yes() -> bool { true }

#[derive(Default)]
struct Health { msgs: AtomicU64, txs: AtomicU64, reconnects: AtomicU64, errors: AtomicU64, last_t: AtomicU64 }

type Out = mpsc::SyncSender<String>;

fn hex16(sig: &[u8]) -> String { sig.iter().take(8).map(|b| format!("{b:02x}")).collect() }

fn is_pump(tx: &Tx) -> bool {
    tx.keys.iter().any(|k| *k == *PUMP || *k == *MINT_AUTH)
        || tx.loaded.as_ref().is_some_and(|(w, r)| w.iter().chain(r.iter()).any(|k| *k == *PUMP))
}
fn is_create(tx: &Tx) -> bool {
    tx.keys.iter().any(|k| *k == *MINT_AUTH) || tx.loaded.as_ref().is_some_and(|(w, r)| w.iter().chain(r.iter()).any(|k| *k == *MINT_AUTH))
}

/// first-seen-slot tracker (bounded)
#[derive(Default)]
struct Seen { set: HashSet<u64>, max: u64 }
impl Seen {
    fn first(&mut self, slot: u64) -> bool {
        if slot + 2000 < self.max || !self.set.insert(slot) { return false; }
        if slot > self.max { self.max = slot; }
        if self.set.len() > 4000 { let m = self.max; self.set.retain(|s| *s + 2000 >= m); }
        true
    }
}

/// PoH clock per slot for an entries feed
#[derive(Default, Clone)]
struct SlotClk { cum: u64, ticks: u32, eidx: u32 }

struct EntriesState { slots: HashMap<u64, SlotClk>, seen: Seen }

fn handle_entries(name: &str, slot: u64, buf: &[u8], t: u64, st: &mut EntriesState, out: &Out, h: &Health) {
    if st.seen.first(slot) { let _ = out.try_send(format!("S\t{name}\t{t}\t{slot}\tmsg")); }
    let Some((txs, ents, _)) = parse_entries_poh(buf) else { return };
    if st.slots.len() > 64 { let m = slot.saturating_sub(32); st.slots.retain(|s, _| *s >= m); }
    let clk = st.slots.entry(slot).or_default();
    let base = clk.eidx;
    for &(hashes, ntx) in &ents {
        clk.cum += hashes;
        let _ = out.try_send(format!("E\t{name}\t{t}\t{slot}\t{}\t{}\t{ntx}\t{}", clk.eidx, clk.cum, clk.ticks));
        if ntx == 0 { clk.ticks += 1; }
        clk.eidx += 1;
    }
    for r in txs.iter().filter(|r| !r.is_vote) {
        let Some((tx, _)) = parse_wire(&buf[r.start..r.end]) else { continue };
        if !is_pump(&tx) { continue; }
        h.txs.fetch_add(1, Ordering::Relaxed);
        let _ = out.try_send(format!("X\t{name}\t{t}\t{slot}\t{}\t{}\t{}\t0", hex16(&r.sig), is_create(&tx) as u8, base + r.entry));
    }
}

fn token_of(f: &FeedCfg, env: &HashMap<String, String>) -> Result<Option<String>> {
    if let Some(t) = &f.token { return Ok(Some(t.clone())); }
    match &f.token_env {
        None => Ok(None),
        Some(k) => std::env::var(k).ok().or_else(|| env.get(k).cloned()).map(Some)
            .with_context(|| format!("{}: token env {k} not set (process env or env_file)", f.name)),
    }
}
fn url_of(f: &FeedCfg, env: &HashMap<String, String>) -> Result<String> {
    if let Some(k) = &f.url_env {
        return std::env::var(k).ok().or_else(|| env.get(k).cloned()).with_context(|| format!("{}: url env {k} not set", f.name));
    }
    f.url.clone().with_context(|| format!("{}: needs url or url_env", f.name))
}

fn add_token<T>(req: &mut tonic::Request<T>, token: Option<&str>, header: Option<&str>) -> Result<()> {
    if let Some(tok) = token {
        let key: tonic::metadata::MetadataKey<tonic::metadata::Ascii> = header.unwrap_or("x-token").parse().context("bad token header name")?;
        req.metadata_mut().insert(key, tok.parse().context("token is not a valid header value")?);
    }
    Ok(())
}

fn idle() -> Duration {
    Duration::from_millis(std::env::var("FEED_IDLE_MS").ok().and_then(|v| v.parse().ok()).unwrap_or(15_000))
}

async fn grpc_client(url: &str) -> Result<tonic::client::Grpc<tonic::transport::Channel>> {
    let mut g = tonic::client::Grpc::new(channel(url).await?).max_decoding_message_size(256 * 1024 * 1024);
    g.ready().await.context("service not ready")?;
    Ok(g)
}

async fn entries_once(f: &FeedCfg, url: &str, tok: Option<&str>, out: &Out, h: &Health) -> Result<()> {
    let mut grpc = grpc_client(url).await?;
    let mut req = tonic::Request::new(SubscribeEntriesRequest {});
    add_token(&mut req, tok, f.token_header.as_deref())?;
    let codec: ProstCodec<SubscribeEntriesRequest, JitoEntry> = ProstCodec::default();
    let path = http::uri::PathAndQuery::from_static("/shredstream.ShredstreamProxy/SubscribeEntries");
    let mut st = grpc.server_streaming(req, path, codec).await?.into_inner();
    let mut es = EntriesState { slots: HashMap::new(), seen: Seen::default() };
    loop {
        if STOP.load(Ordering::Relaxed) { return Ok(()); }
        let m = match tokio::time::timeout(idle(), st.message()).await { Ok(r) => r?, Err(_) => bail!("silent for {:?}", idle()) };
        let Some(m) = m else { bail!("stream ended") };
        let t = now_ns();
        h.msgs.fetch_add(1, Ordering::Relaxed);
        h.last_t.store(t, Ordering::Relaxed);
        handle_entries(&f.name, m.slot, &m.entries, t, &mut es, out, h);
    }
}

/// bidi Yellowstone call: send `first`, ping every 10 s, hand each update to `on_msg`
async fn bidi<Req, Resp>(grpc: &mut tonic::client::Grpc<tonic::transport::Channel>, path: &'static str, first: Req, ping: Req,
    tok: Option<&str>, header: Option<&str>, mut on_msg: impl FnMut(Resp)) -> Result<()>
where Req: prost::Message + Clone + Default + Send + 'static, Resp: prost::Message + Default + Send + 'static {
    let (tx, rx) = tokio::sync::mpsc::channel::<Req>(16);
    tx.send(first).await.ok();
    let pinger = tokio::spawn(async move { loop { tokio::time::sleep(Duration::from_secs(10)).await; if tx.send(ping.clone()).await.is_err() { break; } } });
    let mut req = tonic::Request::new(tokio_stream::wrappers::ReceiverStream::new(rx));
    add_token(&mut req, tok, header)?;
    let codec: ProstCodec<Req, Resp> = ProstCodec::default();
    let res = async {
        let mut st = grpc.streaming(req, http::uri::PathAndQuery::from_static(path), codec).await?.into_inner();
        loop {
            if STOP.load(Ordering::Relaxed) { return Ok(()); }
            let m = match tokio::time::timeout(idle(), st.message()).await { Ok(r) => r?, Err(_) => bail!("silent for {:?}", idle()) };
            let Some(m) = m else { bail!("stream ended") };
            on_msg(m);
        }
    }.await;
    pinger.abort();
    res
}

fn slot_filter(f: &FeedCfg) -> HashMap<String, FilterSlots> {
    if f.slots.unwrap_or(true) { HashMap::from([("s".to_string(), FilterSlots { filter_by_commitment: None, interslot_updates: Some(true) })]) } else { HashMap::new() }
}
fn include(f: &FeedCfg) -> Vec<String> {
    if f.account_include.is_empty() { vec!["6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P".to_string()] } else { f.account_include.clone() }
}

fn on_tx(name: &str, t: u64, created: u64, slot: u64, sig: &[u8], is_vote: bool, pb: &PbTransaction, lw: &[Vec<u8>], lr: &[Vec<u8>],
    seen: &mut Seen, out: &Out, h: &Health) {
    if seen.first(slot) { let _ = out.try_send(format!("S\t{name}\t{t}\t{slot}\ttx")); }
    let Some(tx) = tx_from_pb(sig, is_vote, pb, lw, lr) else { return };
    if tx.is_vote || !is_pump(&tx) { return; }
    h.txs.fetch_add(1, Ordering::Relaxed);
    let _ = out.try_send(format!("X\t{name}\t{t}\t{slot}\t{}\t{}\t-\t{created}", hex16(sig), is_create(&tx) as u8));
}

async fn deshred_once(f: &FeedCfg, url: &str, tok: Option<&str>, out: &Out, h: &Health) -> Result<()> {
    let mut grpc = grpc_client(url).await?;
    let filter = FilterDeshredTx { vote: Some(false), account_include: include(f), ..Default::default() };
    let first = SubscribeDeshredRequest { deshred_transactions: HashMap::from([("race".to_string(), filter)]), slots: slot_filter(f), ..Default::default() };
    let ping = SubscribeDeshredRequest { ping: Some(Ping { id: 1 }), ..Default::default() };
    let mut seen = Seen::default();
    let name = f.name.clone();
    bidi(&mut grpc, "/geyser.Geyser/SubscribeDeshred", first, ping, tok, f.token_header.as_deref(), |m: SubscribeUpdateDeshred| {
        let t = now_ns();
        h.msgs.fetch_add(1, Ordering::Relaxed);
        h.last_t.store(t, Ordering::Relaxed);
        let created = m.created_at.as_ref().and_then(|c| c.ns()).unwrap_or(0);
        if let Some(s) = m.slot { let _ = out.try_send(format!("U\t{name}\t{t}\t{}\t{}\t{created}", s.slot, s.status)); }
        let Some(d) = m.deshred_transaction else { return };
        let Some(info) = d.transaction else { return };
        let Some(pb) = info.transaction.as_ref() else { return };
        on_tx(&name, t, created, d.slot, &info.signature, info.is_vote, pb, &info.loaded_writable_addresses, &info.loaded_readonly_addresses, &mut seen, out, h);
    }).await
}

async fn ytx_once(f: &FeedCfg, url: &str, tok: Option<&str>, out: &Out, h: &Health) -> Result<()> {
    let mut grpc = grpc_client(url).await?;
    let filt = FilterTx { vote: Some(false), failed: None, account_include: include(f), ..Default::default() };
    let first = SubscribeRequest { transactions: HashMap::from([("race".to_string(), filt)]), slots: slot_filter(f), commitment: Some(0), ..Default::default() };
    let ping = SubscribeRequest { ping: Some(Ping { id: 1 }), ..Default::default() };
    let mut seen = Seen::default();
    let name = f.name.clone();
    bidi(&mut grpc, "/geyser.Geyser/Subscribe", first, ping, tok, f.token_header.as_deref(), |m: SubscribeUpdate| {
        let t = now_ns();
        h.msgs.fetch_add(1, Ordering::Relaxed);
        h.last_t.store(t, Ordering::Relaxed);
        let created = m.created_at.as_ref().and_then(|c| c.ns()).unwrap_or(0);
        if let Some(s) = m.slot { let _ = out.try_send(format!("U\t{name}\t{t}\t{}\t{}\t{created}", s.slot, s.status)); }
        let Some(u) = m.transaction else { return };
        let Some(info) = u.transaction else { return };
        let Some(pb) = info.transaction.as_ref() else { return };
        on_tx(&name, t, created, u.slot, &info.signature, info.is_vote, pb, &[], &[], &mut seen, out, h);
    }).await
}

/// raw shreds on a UDP port (blocking thread). Logs slot-first shreds, every completed pump tx (kernel time of the
/// shred that completed it), and the source IPs seen.
fn udp_loop(f: FeedCfg, out: Out, h: Arc<Health>) {
    let bind = f.bind.clone().unwrap_or_else(|| "0.0.0.0:20000".to_string());
    loop {
        if STOP.load(Ordering::Relaxed) { return; }
        let opened = if f.kind == "udp-multicast" && !f.groups.is_empty() {
            open_multi(&f.groups, f.port.unwrap_or(7733), f.interface.as_deref().unwrap_or("doublezero1"))
        } else if f.kind == "udp-multicast" {
            udp::open_multicast(f.group.as_deref().unwrap_or(""), f.port.unwrap_or(7733), f.interface.as_deref().unwrap_or("doublezero1"))
        } else { udp::open_unicast(&bind) };
        let bind = if !f.groups.is_empty() { format!("{}:{} on {}", f.groups.join("+"), f.port.unwrap_or(7733), f.interface.as_deref().unwrap_or("doublezero1")) } else if f.kind == "udp-multicast" { format!("{}:{} on {}", f.group.as_deref().unwrap_or("?"), f.port.unwrap_or(7733), f.interface.as_deref().unwrap_or("doublezero1")) } else { bind.clone() };
        let s = match opened {
            Ok(s) => s,
            Err(e) => { h.errors.fetch_add(1, Ordering::Relaxed); eprintln!("feed_race: {}: bind failed: {e:#}", f.name); std::thread::sleep(Duration::from_secs(5)); continue; }
        };
        eprintln!("feed_race: {}: listening udp {bind} (rcvbuf {} B)", f.name, udp::recv_buffer_bytes(&s));
        let mut asm = shred::Assembler::new();
        let mut seen = Seen::default();
        let mut decoded = Vec::new();
        let mut srcs: HashMap<std::net::Ipv4Addr, u64> = HashMap::new();
        let mut last_src_log = now_ns();
        let mut last_gc = now_ns();
        let key = |k: &Pk| *k == *PUMP || *k == *MINT_AUTH;
        let table = |_: &Pk| false;
        let want = shred::Want { key: &key, table: &table };
        let name = f.name.clone();
        if let Some(c) = f.cpu { pin(c); }
        let mut nrp = 0u64;
        let r = run_udp(&s, f.busy_poll, |p, t_user| {
            let t_start = now_ns();
            h.msgs.fetch_add(1, Ordering::Relaxed);
            h.last_t.store(p.t_ns, Ordering::Relaxed);
            *srcs.entry(p.src).or_insert(0) += 1;
            if let Some(hd) = shred::parse_header(p.data) {
                if seen.first(hd.slot) { let _ = out.try_send(format!("S\t{name}\t{}\t{}\tshred", p.t_ns, hd.slot)); }
            }
            decoded.clear();
            asm.push(p.data, p.t_ns, &mut decoded, &want);
            // drop finished/old slots (the assembler keeps a slot 20 s after its first shred); without this it grows
            if p.t_ns > last_gc + 1_000_000_000 { last_gc = p.t_ns; asm.gc(p.t_ns); }
            let t_dec = now_ns();
            for d in decoded.drain(..) {
                if d.tx.is_vote { continue; }
                h.txs.fetch_add(1, Ordering::Relaxed);
                let cr = is_create(&d.tx);
                let _ = out.try_send(format!("X\t{name}\t{}\t{}\t{}\t{}\t-\t0", d.t, d.slot, hex16(&d.tx.sig), cr as u8));
                nrp += 1;
                if cr || (f.rpath_sample > 0 && nrp % f.rpath_sample == 0) {
                    // receive path: kernel time of the shred that completed it, kernel time of this packet, user-space
                    // time this packet's handling started, time the tx came out of the assembler
                    let _ = out.try_send(format!("R\t{name}\t{}\t{}\t{}\t{}\t{}\t{}\t{}\t{}", d.t, d.slot, hex16(&d.tx.sig), cr as u8, p.t_ns, t_user, t_start, t_dec));
                }
            }
            if p.t_ns > last_src_log + 30_000_000_000 {
                last_src_log = p.t_ns;
                let mut v: Vec<_> = srcs.iter().map(|(a, n)| format!("{a}:{n}")).collect(); v.sort();
                let st = &asm.stats;
                let _ = out.try_send(format!("H\t{name}\t{}\tudp_sources={} data={} code={} dup={} bad={} sets_ok={} sets_failed={} txs={} ver={:?}",
                    p.t_ns, v.join(","), st.data_shreds, st.code_shreds, st.dup_shreds, st.bad_packets, st.sets_decoded, st.sets_failed, st.txs, asm.version()));
            }
        });
        if let Err(e) = r { h.errors.fetch_add(1, Ordering::Relaxed); eprintln!("feed_race: {}: udp error: {e:#}", f.name); std::thread::sleep(Duration::from_secs(1)); }
    }
}

/// one socket on 0.0.0.0:port joined to several groups on one interface (SO_TIMESTAMPNS, 128 MB buffer)
fn open_multi(groups: &[String], port: u16, iface: &str) -> Result<socket2::Socket> {
    use socket2::{Domain, Protocol, Socket, Type};
    use std::os::fd::AsRawFd;
    let cname = std::ffi::CString::new(iface)?;
    // SAFETY: valid NUL-terminated string
    let idx = unsafe { libc::if_nametoindex(cname.as_ptr()) };
    if idx == 0 { bail!("interface {iface} not found"); }
    let s = Socket::new(Domain::IPV4, Type::DGRAM, Some(Protocol::UDP))?;
    s.set_reuse_address(true)?; s.set_reuse_port(true)?;
    s.bind(&std::net::SocketAddrV4::new(std::net::Ipv4Addr::UNSPECIFIED, port).into())?;
    for g in groups {
        let ga: std::net::Ipv4Addr = g.parse().with_context(|| format!("bad group {g}"))?;
        s.join_multicast_v4_n(&ga, &socket2::InterfaceIndexOrAddress::Index(idx)).with_context(|| format!("join {g} on {iface}"))?;
    }
    let fd = s.as_raw_fd();
    let size: libc::c_int = 128 * 1024 * 1024; let on: libc::c_int = 1;
    // SAFETY: plain setsockopt calls with correct sizes
    unsafe {
        libc::setsockopt(fd, libc::SOL_SOCKET, libc::SO_RCVBUFFORCE, &size as *const _ as *const libc::c_void, 4);
        libc::setsockopt(fd, libc::SOL_SOCKET, libc::SO_TIMESTAMPNS, &on as *const _ as *const libc::c_void, 4);
    }
    s.set_read_timeout(Some(Duration::from_millis(200)))?;
    Ok(s)
}

fn pin(cpu: usize) {
    // SAFETY: plain sched_setaffinity on the calling thread
    unsafe {
        let mut set: libc::cpu_set_t = std::mem::zeroed();
        libc::CPU_SET(cpu, &mut set);
        libc::sched_setaffinity(0, std::mem::size_of::<libc::cpu_set_t>(), &set);
    }
}

fn kernel_ts(h: &libc::msghdr) -> Option<u64> {
    // SAFETY: walking the control buffer the kernel filled for this message
    unsafe {
        let mut c = libc::CMSG_FIRSTHDR(h);
        while !c.is_null() {
            if (*c).cmsg_level == libc::SOL_SOCKET && (*c).cmsg_type == libc::SCM_TIMESTAMPNS {
                let ts = std::ptr::read_unaligned(libc::CMSG_DATA(c) as *const libc::timespec);
                return Some(ts.tv_sec as u64 * 1_000_000_000 + ts.tv_nsec as u64);
            }
            c = libc::CMSG_NXTHDR(h, c);
        }
    }
    None
}

/// recvmmsg loop like `udp::run`, plus: the user-space time each batch came back (`t_user`), and an optional busy-poll
/// mode (MSG_DONTWAIT, spinning) that skips the sleep/wake-up in the kernel
fn run_udp(s: &socket2::Socket, busy: bool, mut on_packet: impl FnMut(udp::Packet, u64)) -> Result<()> {
    use std::os::fd::AsRawFd;
    const BATCH: usize = 64; const MAXPKT: usize = 2048; const CM: usize = 128;
    let fd = s.as_raw_fd();
    let mut bufs = vec![vec![0u8; MAXPKT]; BATCH];
    let mut ctrl = vec![[0u8; CM]; BATCH];
    let mut addrs: Vec<libc::sockaddr_in> = vec![unsafe { std::mem::zeroed() }; BATCH];
    let mut iovs: Vec<libc::iovec> = bufs.iter_mut().map(|b| libc::iovec { iov_base: b.as_mut_ptr() as *mut libc::c_void, iov_len: MAXPKT }).collect();
    let mut hdrs: Vec<libc::mmsghdr> = vec![unsafe { std::mem::zeroed() }; BATCH];
    let flags = if busy { libc::MSG_DONTWAIT } else { libc::MSG_WAITFORONE };
    let mut spins = 0u64;
    loop {
        if STOP.load(Ordering::Relaxed) { return Ok(()); }
        for i in 0..BATCH {
            let h = &mut hdrs[i].msg_hdr;
            h.msg_name = &mut addrs[i] as *mut _ as *mut libc::c_void;
            h.msg_namelen = std::mem::size_of::<libc::sockaddr_in>() as u32;
            h.msg_iov = &mut iovs[i]; h.msg_iovlen = 1;
            h.msg_control = ctrl[i].as_mut_ptr() as *mut libc::c_void; h.msg_controllen = CM as _;
            h.msg_flags = 0; hdrs[i].msg_len = 0;
        }
        // SAFETY: all pointers stay valid for the call
        let n = unsafe { libc::recvmmsg(fd, hdrs.as_mut_ptr(), BATCH as u32, flags, std::ptr::null_mut()) };
        if n < 0 {
            let e = std::io::Error::last_os_error();
            match e.raw_os_error() {
                Some(libc::EAGAIN) | Some(libc::EINTR) => { if busy { spins += 1; if spins % 1024 == 0 { std::hint::spin_loop(); } } continue; }
                _ => return Err(e.into()),
            }
        }
        let t_user = now_ns();
        for i in 0..n as usize {
            let len = hdrs[i].msg_len as usize;
            let (t_ns, kernel_ts) = kernel_ts(&hdrs[i].msg_hdr).map(|t| (t, true)).unwrap_or((t_user, false));
            let src = std::net::Ipv4Addr::from(u32::from_be(addrs[i].sin_addr.s_addr));
            let truncated = hdrs[i].msg_hdr.msg_flags & libc::MSG_TRUNC != 0;
            on_packet(udp::Packet { data: &bufs[i][..len.min(MAXPKT)], t_ns, src, kernel_ts, truncated }, t_user);
        }
    }
}

async fn grpc_loop(f: FeedCfg, env: Arc<HashMap<String, String>>, out: Out, h: Arc<Health>) {
    let mut backoff = 1u64;
    loop {
        if STOP.load(Ordering::Relaxed) { return; }
        let start = now_ns();
        let r = async {
            let url = url_of(&f, &env)?;
            let tok = token_of(&f, &env)?;
            match f.kind.as_str() {
                "jito-entries" => entries_once(&f, &url, tok.as_deref(), &out, &h).await,
                "yellowstone-deshred" => deshred_once(&f, &url, tok.as_deref(), &out, &h).await,
                "yellowstone-tx" => ytx_once(&f, &url, tok.as_deref(), &out, &h).await,
                k => bail!("unknown kind {k}"),
            }
        }.await;
        if STOP.load(Ordering::Relaxed) { return; }
        h.reconnects.fetch_add(1, Ordering::Relaxed);
        if let Err(e) = r {
            h.errors.fetch_add(1, Ordering::Relaxed);
            // error text without the URL (tonic errors can echo it): keep the first 160 chars after scrubbing "http"
            let msg = format!("{e:#}");
            let msg: String = msg.split_whitespace().filter(|w| !w.contains("://") && !w.contains('?')).collect::<Vec<_>>().join(" ");
            eprintln!("feed_race: {}: {} — reconnecting in {backoff}s", f.name, &msg[..msg.len().min(160)]);
            let _ = out.try_send(format!("H\t{}\t{}\treconnect err=\"{}\"", f.name, now_ns(), &msg[..msg.len().min(80)].replace('\t', " ")));
        }
        if now_ns() - start > 60_000_000_000 { backoff = 1; }
        tokio::time::sleep(Duration::from_secs(backoff)).await;
        backoff = (backoff * 2).min(10);
    }
}

fn main() -> Result<()> {
    let args: Vec<String> = std::env::args().collect();
    let arg = |k: &str| args.iter().position(|a| a == k).and_then(|i| args.get(i + 1).cloned());
    let cfg_path = arg("--config").unwrap_or_else(|| "/root/gap/feed_race.toml".into());
    let out_path = arg("--out").context("--out FILE required")?;
    let minutes: u64 = arg("--minutes").and_then(|v| v.parse().ok()).unwrap_or(10);
    let only: Option<Vec<String>> = arg("--feeds").map(|s| s.split(',').map(|x| x.to_string()).collect());
    let cfg: Cfg = toml::from_str(&std::fs::read_to_string(&cfg_path).with_context(|| format!("read {cfg_path}"))?).context("parse config")?;
    // tokens: only the names the feeds ask for, from env_file (never printed)
    let wanted: HashSet<String> = cfg.feed.iter().flat_map(|f| f.token_env.iter().chain(f.url_env.iter()).cloned()).collect();
    let mut env = HashMap::new();
    if let Some(p) = &cfg.env_file {
        if let Ok(it) = dotenvy::from_path_iter(p) { for (k, v) in it.filter_map(|x| x.ok()) { if wanted.contains(&k) { env.insert(k, v); } } }
    }
    let env = Arc::new(env);
    let feeds: Vec<FeedCfg> = cfg.feed.into_iter().filter(|f| f.enabled && only.as_ref().map_or(true, |o| o.contains(&f.name))).collect();
    if feeds.is_empty() { bail!("no enabled feeds"); }
    let (out, rx) = mpsc::sync_channel::<String>(1 << 20);
    let writer = std::thread::spawn(move || -> Result<()> {
        let mut w = std::io::BufWriter::with_capacity(1 << 20, std::fs::File::create(&out_path)?);
        let mut last = std::time::Instant::now();
        loop {
            match rx.recv_timeout(Duration::from_millis(500)) {
                Ok(l) => { w.write_all(l.as_bytes())?; w.write_all(b"\n")?; }
                Err(mpsc::RecvTimeoutError::Timeout) => {}
                Err(mpsc::RecvTimeoutError::Disconnected) => { w.flush()?; return Ok(()); }
            }
            if last.elapsed() > Duration::from_secs(1) { w.flush()?; last = std::time::Instant::now(); }
        }
    });
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(3).enable_all().build()?;
    let mut healths = Vec::new();
    for f in &feeds {
        let h = Arc::new(Health::default());
        healths.push((f.name.clone(), h.clone()));
        eprintln!("feed_race: feed {} kind {}", f.name, f.kind);
        if f.kind == "udp-shreds" || f.kind == "udp-multicast" {
            let (f2, o2) = (f.clone(), out.clone());
            std::thread::Builder::new().name(format!("udp-{}", f.name)).spawn(move || udp_loop(f2, o2, h))?;
        } else if f.kind == "websocket" {
            eprintln!("feed_race: {}: websocket feeds are not wired (format unknown); give the provider's message format", f.name);
        } else {
            rt.spawn(grpc_loop(f.clone(), env.clone(), out.clone(), h));
        }
    }
    let deadline = std::time::Instant::now() + Duration::from_secs(minutes * 60);
    rt.block_on(async {
        let mut sig = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()).ok();
        loop {
            let tick = tokio::time::sleep(Duration::from_secs(30));
            tokio::select! {
                _ = tick => {}
                _ = tokio::signal::ctrl_c() => break,
                _ = async { if let Some(s) = sig.as_mut() { s.recv().await; } else { std::future::pending::<()>().await } } => break,
            }
            let t = now_ns();
            for (n, h) in &healths {
                let age = (t.saturating_sub(h.last_t.load(Ordering::Relaxed))) / 1_000_000;
                let l = format!("H\t{n}\t{t}\tmsgs={} txs={} reconnects={} errors={} age_ms={age}",
                    h.msgs.load(Ordering::Relaxed), h.txs.load(Ordering::Relaxed), h.reconnects.load(Ordering::Relaxed), h.errors.load(Ordering::Relaxed));
                eprintln!("{l}");
                let _ = out.try_send(l);
            }
            if std::time::Instant::now() >= deadline { break; }
        }
    });
    STOP.store(true, Ordering::Relaxed);
    drop(out);
    rt.shutdown_timeout(Duration::from_secs(2));
    // the udp threads hold clones of `out`; give the writer a moment, then exit
    for _ in 0..40 { if writer.is_finished() { break; } std::thread::sleep(Duration::from_millis(100)); }
    if writer.is_finished() { let _ = writer.join(); }
    eprintln!("feed_race: done");
    std::process::exit(0);
}

//! FAST (2026-10-19): the sub-100 µs fire path for the pump sniper (snipe_engine `--fast-send`).
//!
//! * `Template`: the buy message compiled ONCE per tip shape with probe keys; a fire copies it and patches the
//!   mint-dependent keys, the tip accounts, the blockhash and min_tokens_out in place (no ix lists, no HashMaps, no
//!   compile). Any key collision (which would change the account dedup) falls back to the full compile.
//! * `FastConn`: one HTTP/1.1 keep-alive connection per HTTP send path (plain TCP or rustls), owned by us, so the hot
//!   thread writes the pre-framed request with ONE write() syscall itself (no task hop, no reqwest/hyper dispatch).
//!   A reader thread matches replies (FIFO) and reports acks; a keep-alive thread pings every 2 s.
//! * `mono_ns`: CLOCK_MONOTONIC ns (== bpftrace `nsecs`, == std Instant), for the stage trace.
use crate::tx::Pk;
use std::collections::VecDeque;
use std::io::{Read, Write};
use std::net::{SocketAddr, TcpStream};
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

#[inline]
pub fn mono_ns() -> u64 {
    let mut ts = libc::timespec { tv_sec: 0, tv_nsec: 0 };
    unsafe { libc::clock_gettime(libc::CLOCK_MONOTONIC, &mut ts) };
    ts.tv_sec as u64 * 1_000_000_000 + ts.tv_nsec as u64
}

/// pin the calling thread to one CPU (sched_setaffinity); false if refused
pub fn pin_to_core(core: usize) -> bool {
    unsafe {
        let mut set: libc::cpu_set_t = std::mem::zeroed();
        libc::CPU_SET(core, &mut set);
        libc::sched_setaffinity(0, std::mem::size_of::<libc::cpu_set_t>(), &set) == 0
    }
}

// ------------------------------------------------------------------------------------------------------------------
// message template
// ------------------------------------------------------------------------------------------------------------------

/// the mint-dependent keys of a buy, in template order
pub const NVAR: usize = 6;
/// [mint, bonding_curve, assoc_bonding_curve (base, T22), assoc_quote_bonding_curve (WSOL, SPL), user base ATA (T22),
/// buyback_fee_recipient]
pub type VarKeys = [Pk; NVAR];

fn probe_key(tag: u8, i: u8) -> Pk {
    let mut k = [0u8; 32];
    for (j, b) in k.iter_mut().enumerate() { *b = tag ^ (j as u8).wrapping_mul(29) ^ i.wrapping_mul(101); }
    k[0] = tag; k[1] = i; k[31] = 0xA7;
    k
}
pub fn probe_var(i: usize) -> Pk { probe_key(0xD1, i as u8) }
pub fn probe_tip(i: usize) -> Pk { probe_key(0xE3, i as u8) }
pub const PROBE_BH: [u8; 32] = [0xC5; 32];
pub const PROBE_MIN_OUT: u64 = 0x0F1E_2D3C_4B5A_6978;

fn find_once(hay: &[u8], needle: &[u8]) -> Option<usize> {
    let mut found = None;
    for i in 0..=hay.len().saturating_sub(needle.len()) {
        if &hay[i..i + needle.len()] == needle {
            if found.is_some() { return None; }
            found = Some(i);
        }
    }
    found
}

pub struct Template {
    pub msg: Vec<u8>,
    var_off: [usize; NVAR],
    tip_off: Vec<usize>,
    bh_off: usize,
    min_out_off: usize,
    /// the template's static keys that are NOT patched (a patched key equal to one of these would change the dedup)
    consts: Vec<Pk>,
}

impl Template {
    /// `msg`: a message compiled from the probe keys (`probe_var`, `probe_tip`, `PROBE_BH`, `PROBE_MIN_OUT`), with `ntips`
    /// tip transfers. Locates every patch site (each probe must appear exactly once).
    pub fn from_probe_msg(msg: Vec<u8>, ntips: usize) -> Result<Template, String> {
        let mut var_off = [0usize; NVAR];
        for (i, o) in var_off.iter_mut().enumerate() { *o = find_once(&msg, &probe_var(i)).ok_or(format!("var probe {i} not found once"))?; }
        let mut tip_off = Vec::with_capacity(ntips);
        for i in 0..ntips { tip_off.push(find_once(&msg, &probe_tip(i)).ok_or(format!("tip probe {i} not found once"))?); }
        let bh_off = find_once(&msg, &PROBE_BH).ok_or("blockhash probe not found once")?;
        let min_out_off = find_once(&msg, &PROBE_MIN_OUT.to_le_bytes()).ok_or("min_out probe not found once")?;
        // static keys: header(3) + compact count (1 byte while < 128 keys) + 32 * n
        let n = msg[4] as usize;
        if n >= 128 { return Err("too many keys for the template".into()); }
        let mut consts = Vec::with_capacity(n);
        for i in 0..n {
            let o = 5 + 32 * i;
            if var_off.contains(&o) || tip_off.contains(&o) { continue; }
            let mut k = [0u8; 32]; k.copy_from_slice(&msg[o..o + 32]); consts.push(k);
        }
        // every key patch site must be inside the static key table
        if var_off.iter().chain(tip_off.iter()).any(|o| *o < 5 || *o >= 5 + 32 * n || (*o - 5) % 32 != 0) { return Err("a key probe is outside the key table".into()); }
        Ok(Template { msg, var_off, tip_off, bh_off, min_out_off, consts })
    }

    /// patch into `out` (reused buffer, the message only). None: a key collision (use the full compile instead).
    #[inline]
    pub fn patch(&self, out: &mut Vec<u8>, vars: &VarKeys, tips: &[Pk], blockhash: &[u8; 32], min_out: u64) -> Option<()> {
        if tips.len() != self.tip_off.len() { return None; }
        // collisions: patched keys pairwise distinct and not equal to any constant key
        for (i, a) in vars.iter().enumerate() {
            if vars[i + 1..].iter().any(|b| b == a) || tips.iter().any(|b| b == a) || self.consts.iter().any(|c| c == a) { return None; }
        }
        for (i, a) in tips.iter().enumerate() {
            if tips[i + 1..].iter().any(|b| b == a) || self.consts.iter().any(|c| c == a) { return None; }
        }
        out.clear();
        out.extend_from_slice(&self.msg);
        for (i, k) in vars.iter().enumerate() { out[self.var_off[i]..self.var_off[i] + 32].copy_from_slice(k); }
        for (i, k) in tips.iter().enumerate() { out[self.tip_off[i]..self.tip_off[i] + 32].copy_from_slice(k); }
        out[self.bh_off..self.bh_off + 32].copy_from_slice(blockhash);
        out[self.min_out_off..self.min_out_off + 8].copy_from_slice(&min_out.to_le_bytes());
        Some(())
    }
}

// ------------------------------------------------------------------------------------------------------------------
// request bodies
// ------------------------------------------------------------------------------------------------------------------

/// the JSON-RPC sendTransaction body, byte-identical to serde_json's `json!` output in send::Path::deliver (keys sorted:
/// serde_json without preserve_order), base64 into the reused buffer
pub fn json_send_body(raw: &[u8], out: &mut Vec<u8>) {
    use base64::Engine as _;
    out.clear();
    out.extend_from_slice(br#"{"id":1,"jsonrpc":"2.0","method":"sendTransaction","params":[""#);
    let start = out.len();
    let n = (raw.len() + 2) / 3 * 4;
    out.resize(start + n, 0);
    let w = base64::engine::general_purpose::STANDARD.encode_slice(raw, &mut out[start..]).unwrap_or(0);
    out.truncate(start + w);
    out.extend_from_slice(br#"",{"encoding":"base64","maxRetries":0,"skipPreflight":true}]}"#);
}

// ------------------------------------------------------------------------------------------------------------------
// FastConn: our own HTTP/1.1 keep-alive connection
// ------------------------------------------------------------------------------------------------------------------

#[derive(Clone, Debug)]
pub struct Ack { pub path: String, pub tag: u64, pub t_write: u64, pub t_ack: u64, pub status: Option<u16>, pub body: String }

enum Io { Plain(TcpStream), Tls(TcpStream, Box<rustls::ClientConnection>) }

impl Io {
    fn write_all_now(&mut self, buf: &[u8]) -> std::io::Result<()> {
        match self {
            Io::Plain(s) => s.write_all(buf),
            Io::Tls(s, c) => {
                c.writer().write_all(buf)?;
                while c.wants_write() { c.write_tls(s)?; }
                Ok(())
            }
        }
    }
}

struct Pend { tag: u64, t_write: u64, ping: bool }

pub struct FastConn {
    pub name: String,
    host: String,
    addr: SocketAddr,
    tls: Option<Arc<rustls::ClientConfig>>,
    /// "POST /path?q HTTP/1.1\r\nHost: h\r\n...Content-Length: " (the hot path appends the length and the body)
    pub head: Vec<u8>,
    ping_req: Option<Vec<u8>>,
    io: Mutex<Option<Io>>,
    pend: Mutex<VecDeque<Pend>>,
    pub up: AtomicBool,
    pub writes: AtomicU64,
    pub reconnects: AtomicU64,
    acks: crossbeam_channel::Sender<Ack>,
}

fn tls_config() -> Arc<rustls::ClientConfig> {
    static CFG: std::sync::OnceLock<Arc<rustls::ClientConfig>> = std::sync::OnceLock::new();
    CFG.get_or_init(|| {
        let roots = rustls::RootCertStore { roots: webpki_roots::TLS_SERVER_ROOTS.to_vec() };
        let mut c = rustls::ClientConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider()))
            .with_safe_default_protocol_versions().expect("tls versions")
            .with_root_certificates(roots).with_no_client_auth();
        c.alpn_protocols = vec![b"http/1.1".to_vec()];
        Arc::new(c)
    }).clone()
}

impl FastConn {
    /// `url`: the path's full URL (http or https). `content_type`: of the send body. `extra`: the path's own headers
    /// (name, value). `ping`: (GET?, url) of its keep-alive.
    pub fn start(name: &str, url: &str, content_type: &str, extra: &[(String, String)], ping: Option<(bool, String)>, acks: crossbeam_channel::Sender<Ack>,
        stop: Arc<AtomicBool>) -> Result<Arc<FastConn>, String> {
        let u = reqwest::Url::parse(url).map_err(|e| format!("{name}: url: {e}"))?;
        let tls = match u.scheme() { "https" => Some(tls_config()), "http" => None, s => return Err(format!("{name}: scheme {s} not supported by the fast path")) };
        let host = u.host_str().ok_or(format!("{name}: no host"))?.to_string();
        let port = u.port_or_known_default().unwrap_or(if tls.is_some() { 443 } else { 80 });
        use std::net::ToSocketAddrs;
        let addr = (host.as_str(), port).to_socket_addrs().map_err(|e| format!("{name}: resolve: {e}"))?.next().ok_or(format!("{name}: no address"))?;
        let pq = |u: &reqwest::Url| match u.query() { Some(q) => format!("{}?{q}", u.path()), None => u.path().to_string() };
        let hosthdr = match u.port() { Some(p) => format!("{host}:{p}"), None => host.clone() };
        let mut head = format!("POST {} HTTP/1.1\r\nHost: {hosthdr}\r\nAccept: */*\r\nContent-Type: {content_type}\r\n", pq(&u));
        for (k, v) in extra { head.push_str(&format!("{k}: {v}\r\n")); }
        head.push_str("Content-Length: ");
        let ping_req = ping.and_then(|(get, pu)| {
            let p = reqwest::Url::parse(&pu).ok()?;
            let mut r = if get { format!("GET {} HTTP/1.1\r\nHost: {hosthdr}\r\nAccept: */*\r\n", pq(&p)) } else { format!("POST {} HTTP/1.1\r\nHost: {hosthdr}\r\nAccept: */*\r\nContent-Type: application/json\r\n", pq(&p)) };
            for (k, v) in extra { r.push_str(&format!("{k}: {v}\r\n")); }
            if get { r.push_str("\r\n"); } else {
                let b = r#"{"id":1,"jsonrpc":"2.0","method":"getHealth","params":[]}"#;
                r.push_str(&format!("Content-Length: {}\r\n\r\n{b}", b.len()));
            }
            Some(r.into_bytes())
        });
        let c = Arc::new(FastConn { name: name.to_string(), host, addr, tls, head: head.into_bytes(), ping_req, io: Mutex::new(None), pend: Mutex::new(VecDeque::new()),
            up: AtomicBool::new(false), writes: AtomicU64::new(0), reconnects: AtomicU64::new(0), acks });
        // reader (connects, reads, reconnects) and keep-alive threads
        { let c = c.clone(); let stop = stop.clone(); std::thread::Builder::new().name(format!("fast-rd-{name}")).spawn(move || c.reader(stop)).map_err(|e| e.to_string())?; }
        { let c = c.clone(); std::thread::Builder::new().name(format!("fast-ka-{name}")).spawn(move || c.keepalive(stop)).map_err(|e| e.to_string())?; }
        Ok(c)
    }

    fn connect(&self) -> std::io::Result<(TcpStream, Io)> {
        let s = TcpStream::connect_timeout(&self.addr, Duration::from_secs(3))?;
        s.set_nodelay(true)?;
        let sock = socket2::SockRef::from(&s);
        let _ = sock.set_keepalive(true);
        let _ = sock.set_tcp_keepalive(&socket2::TcpKeepalive::new().with_time(Duration::from_secs(15)).with_interval(Duration::from_secs(5)));
        let rd = s.try_clone()?;
        let io = match &self.tls {
            None => Io::Plain(s),
            Some(cfg) => {
                let sn = rustls::pki_types::ServerName::try_from(self.host.clone()).map_err(|e| std::io::Error::other(e.to_string()))?;
                let mut c = rustls::ClientConnection::new(cfg.clone(), sn).map_err(|e| std::io::Error::other(e.to_string()))?;
                let mut s = s;
                s.set_read_timeout(Some(Duration::from_secs(3)))?;
                while c.is_handshaking() { c.complete_io(&mut s)?; }
                s.set_read_timeout(None)?;
                Io::Tls(s, Box::new(c))
            }
        };
        Ok((rd, io))
    }

    /// HOT PATH: write one framed request (head + length + body) with one syscall (TLS: one encrypt + write). Returns the
    /// (before, after) monotonic ns of the write. Err: not connected / write failed (the caller falls back).
    #[inline]
    pub fn write_req(&self, req: &[u8], tag: u64) -> Result<(u64, u64), String> {
        if !self.up.load(Ordering::Acquire) { return Err("down".into()); }
        let mut g = self.io.lock().unwrap();
        let io = g.as_mut().ok_or("down")?;
        let t0 = mono_ns();
        self.pend.lock().unwrap().push_back(Pend { tag, t_write: t0, ping: false });
        match io.write_all_now(req) {
            Ok(()) => { let t1 = mono_ns(); self.writes.fetch_add(1, Ordering::Relaxed); Ok((t0, t1)) }
            Err(e) => { self.up.store(false, Ordering::Release); *g = None; Err(format!("write: {e}")) }
        }
    }

    /// frame a request into `out`: head + content length + CRLFCRLF + body
    #[inline]
    pub fn frame(&self, body: &[u8], out: &mut Vec<u8>) {
        out.clear();
        out.extend_from_slice(&self.head);
        let mut b = [0u8; 20];
        out.extend_from_slice(itoa(body.len(), &mut b));
        out.extend_from_slice(b"\r\n\r\n");
        out.extend_from_slice(body);
    }

    fn keepalive(self: Arc<Self>, stop: Arc<AtomicBool>) {
        while !stop.load(Ordering::Relaxed) {
            std::thread::sleep(Duration::from_secs(2));
            let Some(req) = &self.ping_req else { continue };
            if !self.up.load(Ordering::Acquire) { continue; }
            let mut g = self.io.lock().unwrap();
            if let Some(io) = g.as_mut() {
                self.pend.lock().unwrap().push_back(Pend { tag: 0, t_write: mono_ns(), ping: true });
                if io.write_all_now(req).is_err() { self.up.store(false, Ordering::Release); *g = None; }
            }
        }
    }

    fn fail_pending(&self, why: &str) {
        let mut p = self.pend.lock().unwrap();
        for x in p.drain(..) {
            if !x.ping { let _ = self.acks.send(Ack { path: self.name.clone(), tag: x.tag, t_write: x.t_write, t_ack: mono_ns(), status: None, body: why.to_string() }); }
        }
    }

    fn reader(self: Arc<Self>, stop: Arc<AtomicBool>) {
        let mut backoff = 100u64;
        while !stop.load(Ordering::Relaxed) {
            let (mut rd, io) = match self.connect() {
                Ok(x) => x,
                Err(_) => { std::thread::sleep(Duration::from_millis(backoff)); backoff = (backoff * 2).min(5_000); continue; }
            };
            backoff = 100;
            self.pend.lock().unwrap().clear();
            *self.io.lock().unwrap() = Some(io);
            self.up.store(true, Ordering::Release);
            self.reconnects.fetch_add(1, Ordering::Relaxed);
            let mut net = vec![0u8; 32 * 1024];
            let mut plain: Vec<u8> = Vec::with_capacity(64 * 1024);
            let mut tmp = vec![0u8; 32 * 1024];
            let why = loop {
                let n = match rd.read(&mut net) { Ok(0) => break "eof".to_string(), Ok(n) => n, Err(e) => break format!("read: {e}") };
                {
                    let mut g = self.io.lock().unwrap();
                    match g.as_mut() {
                        None => break "closed".into(),
                        Some(Io::Plain(_)) => plain.extend_from_slice(&net[..n]),
                        Some(Io::Tls(s, c)) => {
                            let mut src = &net[..n];
                            let mut bad = None;
                            while !src.is_empty() {
                                if let Err(e) = c.read_tls(&mut src) { bad = Some(format!("tls read: {e}")); break; }
                                if let Err(e) = c.process_new_packets() { bad = Some(format!("tls: {e}")); break; }
                            }
                            if let Some(b) = bad { break b; }
                            loop {
                                match c.reader().read(&mut tmp) { Ok(0) => break, Ok(k) => plain.extend_from_slice(&tmp[..k]), Err(_) => break }
                            }
                            if c.wants_write() { let _ = c.write_tls(s); }
                        }
                    }
                }
                // complete responses, in order
                loop {
                    match parse_response(&plain) {
                        Some((used, status, body)) => {
                            let t_ack = mono_ns();
                            let p = self.pend.lock().unwrap().pop_front();
                            if let Some(p) = p {
                                if !p.ping {
                                    let _ = self.acks.send(Ack { path: self.name.clone(), tag: p.tag, t_write: p.t_write, t_ack, status: Some(status),
                                        body: String::from_utf8_lossy(&body[..body.len().min(200)]).trim().to_string() });
                                }
                            }
                            plain.drain(..used);
                        }
                        None => break,
                    }
                }
            };
            self.up.store(false, Ordering::Release);
            *self.io.lock().unwrap() = None;
            self.fail_pending(&format!("connection lost: {why}"));
            std::thread::sleep(Duration::from_millis(50));
        }
    }

    /// warm the kernel send path of this socket without sending anything (a zero-length send on TCP sends no segment)
    pub fn prewarm(&self) {
        use std::os::fd::AsRawFd;
        if let Ok(g) = self.io.try_lock() {
            let fd = match g.as_ref() { Some(Io::Plain(s)) => s.as_raw_fd(), Some(Io::Tls(s, _)) => s.as_raw_fd(), None => return };
            unsafe { libc::send(fd, [0u8; 1].as_ptr() as *const libc::c_void, 0, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) };
        }
    }

    pub fn summary(&self) -> String {
        format!("{}: fast conn {} writes {} connects {}", self.name, if self.up.load(Ordering::Relaxed) { "up" } else { "DOWN" },
            self.writes.load(Ordering::Relaxed), self.reconnects.load(Ordering::Relaxed))
    }
}

/// a small stack integer formatter (no allocation)
fn itoa(mut n: usize, b: &mut [u8; 20]) -> &[u8] {
    let mut i = 20;
    loop { i -= 1; b[i] = b'0' + (n % 10) as u8; n /= 10; if n == 0 { break; } }
    &b[i..]
}

/// one complete HTTP/1.1 response at the start of `buf`: (bytes used, status, body). None: incomplete.
fn parse_response(buf: &[u8]) -> Option<(usize, u16, Vec<u8>)> {
    let mut hs = [httparse::EMPTY_HEADER; 48];
    let mut r = httparse::Response::new(&mut hs);
    let hlen = match r.parse(buf) { Ok(httparse::Status::Complete(n)) => n, _ => return None };
    let status = r.code.unwrap_or(0);
    let mut clen: Option<usize> = None;
    let mut chunked = false;
    for h in r.headers.iter() {
        if h.name.eq_ignore_ascii_case("content-length") { clen = std::str::from_utf8(h.value).ok().and_then(|s| s.trim().parse().ok()); }
        if h.name.eq_ignore_ascii_case("transfer-encoding") && String::from_utf8_lossy(h.value).to_ascii_lowercase().contains("chunked") { chunked = true; }
    }
    if (100..200).contains(&status) { return Some((hlen, status, Vec::new())); }
    if chunked {
        let mut p = hlen;
        let mut body = Vec::new();
        loop {
            let line_end = buf[p..].windows(2).position(|w| w == b"\r\n")? + p;
            let sz_s = std::str::from_utf8(&buf[p..line_end]).ok()?.split(';').next()?.trim().to_string();
            let sz = usize::from_str_radix(&sz_s, 16).ok()?;
            p = line_end + 2;
            if sz == 0 {
                // trailers until an empty line
                loop {
                    let e = buf[p..].windows(2).position(|w| w == b"\r\n")? + p;
                    if e == p { return Some((p + 2, status, body)); }
                    p = e + 2;
                }
            }
            if buf.len() < p + sz + 2 { return None; }
            body.extend_from_slice(&buf[p..p + sz]);
            p += sz + 2;
        }
    }
    let n = clen.unwrap_or(0);
    if buf.len() < hlen + n { return None; }
    Some((hlen + n, status, buf[hlen..hlen + n].to_vec()))
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn json_body_matches_serde() {
        use base64::Engine as _;
        let raw: Vec<u8> = (0..1000u32).map(|i| (i * 7) as u8).collect();
        let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
        let v = serde_json::json!({ "jsonrpc": "2.0", "id": 1, "method": "sendTransaction", "params": [b64, { "encoding": "base64", "skipPreflight": true, "maxRetries": 0 }] });
        let mut out = Vec::new();
        json_send_body(&raw, &mut out);
        assert_eq!(String::from_utf8(out).unwrap(), serde_json::to_string(&v).unwrap());
    }
    #[test]
    fn responses() {
        let a = b"HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\nhelloHTTP/1.1 400 Bad\r\nTransfer-Encoding: chunked\r\n\r\n3\r\nabc\r\n0\r\n\r\n";
        let (u, s, b) = parse_response(a).unwrap();
        assert_eq!((s, b.as_slice()), (200, &b"hello"[..]));
        let (u2, s2, b2) = parse_response(&a[u..]).unwrap();
        assert_eq!((s2, b2.as_slice(), u + u2), (400, &b"abc"[..], a.len()));
    }
}

// ------------------------------------------------------------------------------------------------------------------
// FastH2: one gRPC unary call (Jito SendBundle) written as raw HTTP/2 frames on our own TLS connection (ALPN h2), so
// the hot thread writes HEADERS + DATA with one encrypt + one write() (tonic: buffer task -> hyper -> h2 task hops).
// HPACK: we only ENCODE (literal fields, no dynamic table, no Huffman). Replies are matched by stream id: a DATA frame
// carries the response message (SendBundleResponse uuid, decoded here); the trailers' HPACK is not decoded, so a
// stream that ends without DATA reads as "rejected (no message)".
// ------------------------------------------------------------------------------------------------------------------

fn hpack_int(out: &mut Vec<u8>, first: u8, prefix_bits: u8, mut v: usize) {
    let max = (1usize << prefix_bits) - 1;
    if v < max { out.push(first | v as u8); return; }
    out.push(first | max as u8);
    v -= max;
    while v >= 128 { out.push((v % 128) as u8 | 0x80); v /= 128; }
    out.push(v as u8);
}
/// literal header field without indexing, new name (0x00), no Huffman
fn hpack_lit(out: &mut Vec<u8>, name: &str, value: &str) {
    out.push(0x00);
    hpack_int(out, 0, 7, name.len()); out.extend_from_slice(name.as_bytes());
    hpack_int(out, 0, 7, value.len()); out.extend_from_slice(value.as_bytes());
}
/// literal without indexing, indexed name (static table index)
fn hpack_lit_idx(out: &mut Vec<u8>, idx: usize, value: &str) {
    hpack_int(out, 0, 4, idx);
    hpack_int(out, 0, 7, value.len()); out.extend_from_slice(value.as_bytes());
}
fn frame_hdr(out: &mut Vec<u8>, len: usize, ty: u8, flags: u8, stream: u32) {
    out.extend_from_slice(&[(len >> 16) as u8, (len >> 8) as u8, len as u8, ty, flags]);
    out.extend_from_slice(&(stream & 0x7fff_ffff).to_be_bytes());
}

#[derive(Default)]
struct Hpack { tab: VecDeque<(String, String)>, size: usize, off: bool, reset: bool }
impl Hpack {
    const MAX: usize = 4096; // the decoder's (server's) table size: the default; any other SETTINGS value turns indexing off
    /// encode one field: indexed if in the dynamic table, else literal WITH incremental indexing (and remember it)
    fn field(&mut self, out: &mut Vec<u8>, static_name: usize, name: &str, value: &str) {
        if !self.off {
            if let Some(i) = self.tab.iter().position(|(n, v)| n == name && v == value) { hpack_int(out, 0x80, 7, 62 + i); return; }
            let sz = name.len() + value.len() + 32;
            if sz <= Self::MAX {
                if static_name > 0 { hpack_int(out, 0x40, 6, static_name); } else { out.push(0x40); hpack_int(out, 0, 7, name.len()); out.extend_from_slice(name.as_bytes()); }
                hpack_int(out, 0, 7, value.len()); out.extend_from_slice(value.as_bytes());
                self.tab.push_front((name.to_string(), value.to_string()));
                self.size += sz;
                while self.size > Self::MAX { if let Some((n, v)) = self.tab.pop_back() { self.size -= n.len() + v.len() + 32; } else { break; } }
                return;
            }
        }
        if static_name > 0 { hpack_lit_idx(out, static_name, value); } else { hpack_lit(out, name, value); }
    }
}
#[derive(Default)]
struct H2State { next_stream: u32, conn_window: i64, peer_init_window: i64, streams: std::collections::HashMap<u32, (u64, u64, bool)>, hp: Hpack }

pub struct FastH2 {
    pub name: String,
    host: String,
    addr: SocketAddr,
    io: Mutex<Option<(TcpStream, Box<rustls::ClientConnection>)>>,
    st: Mutex<H2State>,
    pub up: AtomicBool,
    pub writes: AtomicU64,
    pub reconnects: AtomicU64,
    /// (tag, uuid or error) per reply
    acks: crossbeam_channel::Sender<Ack>,
}

impl FastH2 {
    pub fn start(name: &str, url: &str, acks: crossbeam_channel::Sender<Ack>, stop: Arc<AtomicBool>) -> Result<Arc<FastH2>, String> {
        let u = reqwest::Url::parse(url).map_err(|e| format!("{name}: url: {e}"))?;
        if u.scheme() != "https" { return Err(format!("{name}: h2 fast path needs https")); }
        let host = u.host_str().ok_or("no host")?.to_string();
        use std::net::ToSocketAddrs;
        let addr = (host.as_str(), u.port_or_known_default().unwrap_or(443)).to_socket_addrs().map_err(|e| format!("{name}: resolve: {e}"))?.next().ok_or("no address")?;
        let c = Arc::new(FastH2 { name: name.into(), host, addr, io: Mutex::new(None), st: Mutex::new(H2State::default()), up: AtomicBool::new(false),
            writes: AtomicU64::new(0), reconnects: AtomicU64::new(0), acks });
        { let c = c.clone(); let stop = stop.clone(); std::thread::Builder::new().name(format!("fast-h2-{name}")).spawn(move || c.reader(stop)).map_err(|e| e.to_string())?; }
        { let c = c.clone(); std::thread::Builder::new().name(format!("fast-h2ka-{name}")).spawn(move || c.keepalive(stop)).map_err(|e| e.to_string())?; }
        Ok(c)
    }

    fn tls_h2() -> Arc<rustls::ClientConfig> {
        static CFG: std::sync::OnceLock<Arc<rustls::ClientConfig>> = std::sync::OnceLock::new();
        CFG.get_or_init(|| {
            let roots = rustls::RootCertStore { roots: webpki_roots::TLS_SERVER_ROOTS.to_vec() };
            let mut c = rustls::ClientConfig::builder_with_provider(Arc::new(rustls::crypto::ring::default_provider()))
                .with_safe_default_protocol_versions().expect("tls versions").with_root_certificates(roots).with_no_client_auth();
            c.alpn_protocols = vec![b"h2".to_vec()];
            Arc::new(c)
        }).clone()
    }

    fn connect(&self) -> std::io::Result<(TcpStream, (TcpStream, Box<rustls::ClientConnection>))> {
        let mut s = TcpStream::connect_timeout(&self.addr, Duration::from_secs(3))?;
        s.set_nodelay(true)?;
        let sn = rustls::pki_types::ServerName::try_from(self.host.clone()).map_err(|e| std::io::Error::other(e.to_string()))?;
        let mut c = rustls::ClientConnection::new(Self::tls_h2(), sn).map_err(|e| std::io::Error::other(e.to_string()))?;
        s.set_read_timeout(Some(Duration::from_secs(3)))?;
        while c.is_handshaking() { c.complete_io(&mut s)?; }
        if c.alpn_protocol() != Some(b"h2") { return Err(std::io::Error::other("server did not negotiate h2")); }
        // preface + SETTINGS (ENABLE_PUSH 0, INITIAL_WINDOW_SIZE 16 MiB) + connection WINDOW_UPDATE (+32 MiB)
        let mut b = b"PRI * HTTP/2.0\r\n\r\nSM\r\n\r\n".to_vec();
        frame_hdr(&mut b, 12, 0x4, 0, 0);
        b.extend_from_slice(&[0, 2, 0, 0, 0, 0]);
        b.extend_from_slice(&[0, 4]); b.extend_from_slice(&(16u32 << 20).to_be_bytes());
        frame_hdr(&mut b, 4, 0x8, 0, 0); b.extend_from_slice(&(32u32 << 20).to_be_bytes());
        c.writer().write_all(&b)?;
        while c.wants_write() { c.write_tls(&mut s)?; }
        s.set_read_timeout(None)?;
        let rd = s.try_clone()?;
        Ok((rd, (s, Box::new(c))))
    }

    /// the gRPC request's HPACK header block for `path` with `bearer`
    pub fn header_block(&self, path: &str, bearer: &str) -> Vec<u8> {
        let mut h = Vec::with_capacity(1024);
        h.push(0x83); // :method POST
        h.push(0x87); // :scheme https
        hpack_lit_idx(&mut h, 4, path);       // :path
        hpack_lit_idx(&mut h, 1, &self.host); // :authority
        hpack_lit(&mut h, "content-type", "application/grpc");
        hpack_lit(&mut h, "te", "trailers");
        hpack_lit(&mut h, "grpc-timeout", "5S");
        hpack_lit(&mut h, "authorization", &format!("Bearer {bearer}"));
        h
    }

    /// frame one unary call into `out`: HEADERS(END_HEADERS) + DATA(END_STREAM), stream id 0 (patched at write time)
    pub fn frame(hblock: &[u8], msg: &[u8], out: &mut Vec<u8>) {
        out.clear();
        frame_hdr(out, hblock.len(), 0x1, 0x4, 0);
        out.extend_from_slice(hblock);
        frame_hdr(out, msg.len() + 5, 0x0, 0x1, 0);
        out.push(0);
        out.extend_from_slice(&(msg.len() as u32).to_be_bytes());
        out.extend_from_slice(msg);
    }

    /// HOT PATH (HPACK-indexed): HEADERS encoded now against this connection's dynamic table (the token and the fixed
    /// fields go in once per connection, then cost one byte each), DATA = the gRPC message; one encrypt + one write
    pub fn write_call_idx(&self, path: &str, bearer: &str, msg: &[u8], tag: u64) -> Result<(u64, u64), String> {
        if !self.up.load(Ordering::Acquire) { return Err("down".into()); }
        let mut g = self.io.lock().unwrap();
        let (s, c) = g.as_mut().ok_or("down")?;
        let t0 = mono_ns();
        let mut req: Vec<u8> = Vec::with_capacity(9 + 64 + 9 + 5 + msg.len() + 1024);
        {
            let mut st = self.st.lock().unwrap();
            let data_len = msg.len() + 5;
            if st.conn_window < data_len as i64 || st.peer_init_window < data_len as i64 || st.next_stream > 0x7fff_0000 { return Err("h2 window/stream ids".into()); }
            let sid = st.next_stream; st.next_stream += 2; st.conn_window -= data_len as i64;
            st.streams.insert(sid, (tag, t0, false));
            req.resize(9, 0);
            if st.hp.reset { hpack_int(&mut req, 0x20, 5, 0); st.hp.reset = false; }
            req.push(0x83); req.push(0x87);
            st.hp.field(&mut req, 4, ":path", path);
            let host = self.host.clone();
            st.hp.field(&mut req, 1, ":authority", &host);
            st.hp.field(&mut req, 31, "content-type", "application/grpc");
            st.hp.field(&mut req, 0, "te", "trailers");
            st.hp.field(&mut req, 0, "grpc-timeout", "5S");
            st.hp.field(&mut req, 23, "authorization", bearer);
            let hl = req.len() - 9;
            let mut fh = Vec::with_capacity(9); frame_hdr(&mut fh, hl, 0x1, 0x4, sid); req[..9].copy_from_slice(&fh);
            frame_hdr(&mut req, data_len, 0x0, 0x1, sid);
            req.push(0); req.extend_from_slice(&(msg.len() as u32).to_be_bytes()); req.extend_from_slice(msg);
        }
        let r = c.writer().write_all(&req).and_then(|_| { while c.wants_write() { c.write_tls(s)?; } Ok(()) });
        match r {
            Ok(()) => { self.writes.fetch_add(1, Ordering::Relaxed); Ok((t0, mono_ns())) }
            Err(e) => { self.up.store(false, Ordering::Release); *g = None; Err(format!("write: {e}")) }
        }
    }

    /// HOT PATH: write a framed call (from `frame`): assign the stream id, patch it into both frames, one write
    pub fn write_call(&self, req: &mut [u8], hblock_len: usize, tag: u64) -> Result<(u64, u64), String> {
        if !self.up.load(Ordering::Acquire) { return Err("down".into()); }
        let mut g = self.io.lock().unwrap();
        let (s, c) = g.as_mut().ok_or("down")?;
        let data_len = req.len() - 9 - hblock_len - 9;
        let t0 = mono_ns();
        let sid = {
            let mut st = self.st.lock().unwrap();
            if st.conn_window < data_len as i64 || st.peer_init_window < data_len as i64 || st.next_stream > 0x7fff_0000 { return Err("h2 window/stream ids".into()); }
            let sid = st.next_stream; st.next_stream += 2; st.conn_window -= data_len as i64;
            st.streams.insert(sid, (tag, t0, false));
            sid
        };
        req[5..9].copy_from_slice(&sid.to_be_bytes());
        let d = 9 + hblock_len;
        req[d + 5..d + 9].copy_from_slice(&sid.to_be_bytes());
        let r = c.writer().write_all(req).and_then(|_| { while c.wants_write() { c.write_tls(s)?; } Ok(()) });
        match r {
            Ok(()) => { self.writes.fetch_add(1, Ordering::Relaxed); Ok((t0, mono_ns())) }
            Err(e) => { self.up.store(false, Ordering::Release); *g = None; Err(format!("write: {e}")) }
        }
    }

    fn send_raw(&self, b: &[u8]) {
        let mut g = self.io.lock().unwrap();
        if let Some((s, c)) = g.as_mut() {
            if c.writer().write_all(b).and_then(|_| { while c.wants_write() { c.write_tls(s)?; } Ok(()) }).is_err() { self.up.store(false, Ordering::Release); *g = None; }
        }
    }

    fn keepalive(self: Arc<Self>, stop: Arc<AtomicBool>) {
        while !stop.load(Ordering::Relaxed) {
            std::thread::sleep(Duration::from_secs(5));
            if !self.up.load(Ordering::Acquire) { continue; }
            let mut b = Vec::with_capacity(17);
            frame_hdr(&mut b, 8, 0x6, 0, 0); b.extend_from_slice(&[0x66, 0x61, 0x73, 0x74, 0, 0, 0, 0]);
            self.send_raw(&b);
        }
    }

    fn reply(&self, sid: u32, ok: Option<String>, why: &str) {
        let e = self.st.lock().unwrap().streams.remove(&sid);
        if let Some((tag, t_write, _)) = e {
            let _ = self.acks.send(Ack { path: self.name.clone(), tag, t_write, t_ack: mono_ns(), status: Some(if ok.is_some() { 200 } else { 0 }),
                body: ok.unwrap_or_else(|| why.to_string()) });
        }
    }

    fn reader(self: Arc<Self>, stop: Arc<AtomicBool>) {
        let mut backoff = 200u64;
        while !stop.load(Ordering::Relaxed) {
            let (mut rd, io) = match self.connect() {
                Ok(x) => x,
                Err(_) => { std::thread::sleep(Duration::from_millis(backoff)); backoff = (backoff * 2).min(10_000); continue; }
            };
            backoff = 200;
            *self.st.lock().unwrap() = H2State { next_stream: 1, conn_window: 65_535, peer_init_window: 65_535, streams: Default::default(), hp: Hpack::default() };
            *self.io.lock().unwrap() = Some(io);
            self.up.store(true, Ordering::Release);
            self.reconnects.fetch_add(1, Ordering::Relaxed);
            let mut net = vec![0u8; 64 * 1024];
            let mut tmp = vec![0u8; 64 * 1024];
            let mut plain: Vec<u8> = Vec::with_capacity(128 * 1024);
            let why = loop {
                let n = match rd.read(&mut net) { Ok(0) => break "eof".to_string(), Ok(n) => n, Err(e) => break format!("read: {e}") };
                {
                    let mut g = self.io.lock().unwrap();
                    let Some((s, c)) = g.as_mut() else { break "closed".into() };
                    let mut src = &net[..n];
                    let mut bad = None;
                    while !src.is_empty() {
                        if let Err(e) = c.read_tls(&mut src) { bad = Some(format!("tls read: {e}")); break; }
                        if let Err(e) = c.process_new_packets() { bad = Some(format!("tls: {e}")); break; }
                    }
                    if let Some(b) = bad { break b; }
                    loop { match c.reader().read(&mut tmp) { Ok(0) => break, Ok(k) => plain.extend_from_slice(&tmp[..k]), Err(_) => break } }
                    if c.wants_write() { let _ = c.write_tls(s); }
                }
                let mut out: Vec<u8> = Vec::new(); // frames we must send back (SETTINGS ACK, PING ACK, WINDOW_UPDATE)
                let mut goaway = false;
                let mut p = 0;
                while plain.len() >= p + 9 {
                    let len = ((plain[p] as usize) << 16) | ((plain[p + 1] as usize) << 8) | plain[p + 2] as usize;
                    if plain.len() < p + 9 + len { break; }
                    let (ty, fl) = (plain[p + 3], plain[p + 4]);
                    let sid = u32::from_be_bytes(plain[p + 5..p + 9].try_into().unwrap()) & 0x7fff_ffff;
                    let pl = &plain[p + 9..p + 9 + len];
                    match ty {
                        0x4 if fl & 1 == 0 => {
                            for kv in pl.chunks_exact(6) {
                                let id = u16::from_be_bytes([kv[0], kv[1]]);
                                let v = u32::from_be_bytes([kv[2], kv[3], kv[4], kv[5]]) as i64;
                                if id == 4 { self.st.lock().unwrap().peer_init_window = v; }
                                if id == 1 && v < Hpack::MAX as i64 {
                                    // the server's decoder table is smaller than the default: stop indexing, signal size 0 (RFC 7541 §4.2)
                                    let mut st = self.st.lock().unwrap();
                                    if !st.hp.off { st.hp.off = true; st.hp.reset = true; st.hp.tab.clear(); st.hp.size = 0; }
                                }
                            }
                            frame_hdr(&mut out, 0, 0x4, 1, 0);
                        }
                        0x6 if fl & 1 == 0 => { frame_hdr(&mut out, 8, 0x6, 1, 0); out.extend_from_slice(pl); }
                        0x8 if len == 4 && sid == 0 => { self.st.lock().unwrap().conn_window += (u32::from_be_bytes(pl.try_into().unwrap()) & 0x7fff_ffff) as i64; }
                        0x0 => {
                            // DATA: the response message (gRPC 5-byte prefix + protobuf; SendBundleResponse field 1 = uuid)
                            let body = if fl & 0x8 != 0 && !pl.is_empty() { &pl[1..pl.len().saturating_sub(pl[0] as usize)] } else { pl };
                            if body.len() > 5 {
                                let m = &body[5..];
                                let uuid = if m.len() > 2 && m[0] == 0x0a { let l = m[1] as usize; m.get(2..2 + l).map(|u| String::from_utf8_lossy(u).to_string()) } else { None };
                                if let Some(e) = self.st.lock().unwrap().streams.get_mut(&sid) { e.2 = true; }
                                self.reply(sid, Some(uuid.unwrap_or_else(|| "accepted (no uuid?)".into())), "");
                            }
                            if len > 0 { frame_hdr(&mut out, 4, 0x8, 0, 0); out.extend_from_slice(&(len as u32).to_be_bytes()); }
                        }
                        0x1 if fl & 0x1 != 0 => self.reply(sid, None, "rejected (stream ended without a message; grpc-status not decoded)"),
                        0x3 => self.reply(sid, None, "RST_STREAM"),
                        0x7 => goaway = true,
                        _ => {}
                    }
                    p += 9 + len;
                }
                plain.drain(..p);
                if !out.is_empty() { self.send_raw(&out); }
                if goaway { break "goaway".into(); }
            };
            self.up.store(false, Ordering::Release);
            *self.io.lock().unwrap() = None;
            let sids: Vec<u32> = self.st.lock().unwrap().streams.keys().copied().collect();
            for sid in sids { self.reply(sid, None, &format!("connection lost: {why}")); }
            std::thread::sleep(Duration::from_millis(100));
        }
    }

    pub fn prewarm(&self) {
        use std::os::fd::AsRawFd;
        if let Ok(g) = self.io.try_lock() {
            if let Some((s, _)) = g.as_ref() { unsafe { libc::send(s.as_raw_fd(), [0u8; 1].as_ptr() as *const libc::c_void, 0, libc::MSG_DONTWAIT | libc::MSG_NOSIGNAL) }; }
        }
    }

    pub fn summary(&self) -> String {
        format!("{}: fast h2 conn {} writes {} connects {}", self.name, if self.up.load(Ordering::Relaxed) { "up" } else { "DOWN" },
            self.writes.load(Ordering::Relaxed), self.reconnects.load(Ordering::Relaxed))
    }
}

// ------------------------------------------------------------------------------------------------------------------
// Presigner (--fast-presign): Ed25519 with PRE-COMPUTED nonces. A signature is (R = r·B, s = r + k·a), k = H(R‖A‖M);
// the verifier only checks s·B = R + k·A, so r may be any secret uniform scalar used ONCE (hedged/randomised Ed25519,
// as XEdDSA). r comes from getrandom(2) (64 bytes, reduced mod L), R = r·B is computed in the background, and each pair
// is POPPED (used exactly once; an empty pool falls back to the deterministic RFC 8032 signature). The sign on the hot
// path is then one SHA-512 over the message + one scalar mul-add. The signature differs from the deterministic one (the
// message bytes do not); every one is checked with verify_strict in the self-test and with --fast-verify.
// ------------------------------------------------------------------------------------------------------------------
use curve25519_dalek::{edwards::EdwardsPoint, scalar::Scalar};

pub struct Presigner { a: Scalar, pubkey: [u8; 32], pool: Mutex<Vec<(Scalar, [u8; 32])>>, pub used: AtomicU64, pub empty: AtomicU64 }

fn os_random(b: &mut [u8]) -> bool {
    let mut got = 0usize;
    while got < b.len() {
        let n = unsafe { libc::getrandom(b[got..].as_mut_ptr() as *mut libc::c_void, b.len() - got, 0) };
        if n <= 0 { return false; }
        got += n as usize;
    }
    true
}

impl Presigner {
    pub fn new(key: &ed25519_dalek::SigningKey) -> Arc<Presigner> {
        use sha2::{Digest, Sha512};
        let h = Sha512::digest(key.to_bytes());
        let mut lower = [0u8; 32];
        lower.copy_from_slice(&h[..32]);
        lower[0] &= 0b1111_1000; lower[31] &= 0b0111_1111; lower[31] |= 0b0100_0000;
        Arc::new(Presigner { a: Scalar::from_bytes_mod_order(lower), pubkey: key.verifying_key().to_bytes(), pool: Mutex::new(Vec::with_capacity(256)),
            used: AtomicU64::new(0), empty: AtomicU64::new(0) })
    }
    fn gen() -> Option<(Scalar, [u8; 32])> {
        let mut b = [0u8; 64];
        if !os_random(&mut b) { return None; }
        let r = Scalar::from_bytes_mod_order_wide(&b);
        b.iter_mut().for_each(|x| *x = 0);
        Some((r, EdwardsPoint::mul_base(&r).compress().to_bytes()))
    }
    /// keep `target` nonces ready (background thread)
    pub fn start(self: &Arc<Self>, target: usize, stop: Arc<AtomicBool>) {
        let me = self.clone();
        for _ in 0..target { if let Some(x) = Self::gen() { me.pool.lock().unwrap().push(x); } }
        std::thread::Builder::new().name("presign-pool".into()).spawn(move || {
            while !stop.load(Ordering::Relaxed) {
                let n = me.pool.lock().unwrap().len();
                if n < target { if let Some(x) = Self::gen() { me.pool.lock().unwrap().push(x); } } else { std::thread::sleep(Duration::from_millis(20)); }
            }
        }).ok();
    }
    /// HOT PATH: a signature with a fresh pre-computed nonce; None: the pool is empty (sign deterministically instead)
    #[inline]
    pub fn sign(&self, msg: &[u8]) -> Option<[u8; 64]> {
        use sha2::{Digest, Sha512};
        let Some((r, rb)) = self.pool.lock().unwrap().pop() else { self.empty.fetch_add(1, Ordering::Relaxed); return None };
        let mut h = Sha512::new();
        h.update(rb); h.update(self.pubkey); h.update(msg);
        let d: [u8; 64] = h.finalize().into();
        let k = Scalar::from_bytes_mod_order_wide(&d);
        let s = k * self.a + r;
        let mut out = [0u8; 64];
        out[..32].copy_from_slice(&rb);
        out[32..].copy_from_slice(s.as_bytes());
        self.used.fetch_add(1, Ordering::Relaxed);
        Some(out)
    }
    pub fn pool_len(&self) -> usize { self.pool.lock().unwrap().len() }
}

// ------------------------------------------------------------------------------------------------------------------
// Fast PDA / ATA derivation (--fast-derive). find_program_address = SHA-256 + "is it on the curve?" per bump; the old
// check decompresses the point (a field exponentiation, ~5 µs here). A 32-byte y (bit 255 ignored, taken mod p) is a
// valid compressed Edwards point iff u/v is a square, u = y²-1, v = d·y²+1 (v is never 0: -1/d is a non-square), i.e. iff
// the Legendre symbol of u·v is 0 or 1 — computed with a binary Jacobi symbol (shifts and subtractions). Checked against
// curve25519-dalek's decompress on random inputs at start-up (and in --fast-bench); any disagreement disables it.
// ------------------------------------------------------------------------------------------------------------------
type U256 = [u64; 4];
const FP: U256 = [0xffff_ffff_ffff_ffed, 0xffff_ffff_ffff_ffff, 0xffff_ffff_ffff_ffff, 0x7fff_ffff_ffff_ffff];
const FD: U256 = [0x75eb_4dca_1359_78a3, 0x0070_0a4d_4141_d8ab, 0x8cc7_4079_7779_e898, 0x5203_6cee_2b6f_fe73];
const ONE: U256 = [1, 0, 0, 0];

#[inline] fn geq(a: &U256, b: &U256) -> bool { for i in (0..4).rev() { if a[i] != b[i] { return a[i] > b[i]; } } true }
#[inline] fn sub_n(a: &U256, b: &U256) -> U256 {
    let mut r = [0u64; 4]; let mut br = 0u64;
    for i in 0..4 { let (x, b1) = a[i].overflowing_sub(b[i]); let (y, b2) = x.overflowing_sub(br); r[i] = y; br = (b1 | b2) as u64; }
    r
}
#[inline] fn add_n(a: &U256, b: &U256) -> (U256, bool) {
    let mut r = [0u64; 4]; let mut c = 0u64;
    for i in 0..4 { let (x, c1) = a[i].overflowing_add(b[i]); let (y, c2) = x.overflowing_add(c); r[i] = y; c = (c1 | c2) as u64; }
    (r, c != 0)
}
#[inline] fn canon(mut a: U256) -> U256 { while geq(&a, &FP) { a = sub_n(&a, &FP); } a }
/// a·b mod p (inputs < 2^256), canonical
fn mulmod(a: &U256, b: &U256) -> U256 {
    let mut r = [0u64; 8];
    for i in 0..4 {
        let mut c: u128 = 0;
        for j in 0..4 { let x = a[i] as u128 * b[j] as u128 + r[i + j] as u128 + c; r[i + j] = x as u64; c = x >> 64; }
        r[i + 4] = c as u64;
    }
    // 2^256 ≡ 38 (mod p)
    let mut o = [0u64; 4]; let mut c: u128 = 0;
    for i in 0..4 { let x = r[i] as u128 + r[i + 4] as u128 * 38 + c; o[i] = x as u64; c = x >> 64; }
    let mut c = c * 38;
    while c != 0 {
        for limb in o.iter_mut() { let x = *limb as u128 + c; *limb = x as u64; c = x >> 64; if c == 0 { break; } }
        c *= 38;
    }
    canon(o)
}
#[inline] fn addmod(a: &U256, b: &U256) -> U256 { let (s, c) = add_n(a, b); if c { canon(add_n(&s, &[38, 0, 0, 0]).0) } else { canon(s) } }
#[inline] fn submod(a: &U256, b: &U256) -> U256 { if geq(a, b) { sub_n(a, b) } else { sub_n(&add_n(a, &FP).0, b) } }
#[inline] fn is_zero(a: &U256) -> bool { a.iter().all(|x| *x == 0) }
#[inline] fn shr(a: &mut U256, z: u32) {
    let (w, b) = ((z / 64) as usize, z % 64);
    for i in 0..4 {
        let lo = if i + w < 4 { a[i + w] } else { 0 };
        let hi = if i + w + 1 < 4 { a[i + w + 1] } else { 0 };
        a[i] = if b == 0 { lo } else { (lo >> b) | (hi << (64 - b)) };
    }
}
#[inline] fn ctz(a: &U256) -> u32 { for (i, x) in a.iter().enumerate() { if *x != 0 { return i as u32 * 64 + x.trailing_zeros(); } } 256 }
/// Jacobi symbol (a / n), n odd
fn jacobi(mut a: U256, mut n: U256) -> i32 {
    let mut t = 1i32;
    loop {
        if is_zero(&a) { return if n == ONE { t } else { 0 }; }
        let z = ctz(&a);
        shr(&mut a, z);
        if z & 1 == 1 { let r = n[0] & 7; if r == 3 || r == 5 { t = -t; } }
        if !geq(&a, &n) { std::mem::swap(&mut a, &mut n); if a[0] & 3 == 3 && n[0] & 3 == 3 { t = -t; } }
        a = sub_n(&a, &n);
    }
}
/// true iff curve25519-dalek's CompressedEdwardsY(b).decompress() is Some
pub fn on_curve_fast(b: &[u8; 32]) -> bool {
    let mut y = [0u64; 4];
    for i in 0..4 { y[i] = u64::from_le_bytes(b[i * 8..i * 8 + 8].try_into().unwrap()); }
    y[3] &= 0x7fff_ffff_ffff_ffff;
    let y = canon(y);
    let yy = mulmod(&y, &y);
    let u = submod(&yy, &ONE);
    let v = addmod(&mulmod(&FD, &yy), &ONE);
    let w = mulmod(&u, &v);
    is_zero(&w) || jacobi(w, FP) == 1
}
/// find_program_address with the fast check and no allocation (seeds total <= 128 bytes)
pub fn find_pda_fast(seeds: &[&[u8]], program: &Pk) -> (Pk, u8) {
    use sha2::{Digest, Sha256};
    let mut base = Sha256::new();
    for s in seeds { base.update(s); }
    for bump in (0..=255u8).rev() {
        let mut h = base.clone();
        h.update([bump]); h.update(program); h.update(b"ProgramDerivedAddress");
        let out: [u8; 32] = h.finalize().into();
        if !on_curve_fast(&out) { return (out, bump); }
    }
    panic!("no viable bump");
}
pub fn ata_fast(owner: &Pk, mint: &Pk, token_program: &Pk) -> Pk { find_pda_fast(&[owner, token_program, mint], &crate::pda::ATA_PROGRAM).0 }

/// start-up check: the fast test agrees with dalek on `n` pseudo-random inputs and the fast ATA with pda::ata on `m`
pub fn derive_selftest(n: usize, m: usize) -> (usize, usize) {
    use sha2::{Digest, Sha256};
    let mut bad = 0;
    let mut seed = [7u8; 32];
    for i in 0..n {
        seed = Sha256::digest([&seed[..], &(i as u64).to_le_bytes()].concat()).into();
        let dalek = curve25519_dalek::edwards::CompressedEdwardsY(seed).decompress().is_some();
        if dalek != on_curve_fast(&seed) { bad += 1; }
    }
    // edge cases: y = 0, 1, p-1, p, p+1, all-ones, top bit set variants
    let mut edges: Vec<[u8; 32]> = vec![[0; 32], [0xff; 32]];
    let mut one = [0u8; 32]; one[0] = 1; edges.push(one);
    let mut pb = [0u8; 32]; for i in 0..4 { pb[i * 8..i * 8 + 8].copy_from_slice(&FP[i].to_le_bytes()); } edges.push(pb);
    let mut pm1 = pb; pm1[0] -= 1; edges.push(pm1);
    let mut pp1 = pb; pp1[0] += 1; edges.push(pp1);
    for mut e in edges.clone() { e[31] |= 0x80; edges.push(e); }
    for e in &edges { if curve25519_dalek::edwards::CompressedEdwardsY(*e).decompress().is_some() != on_curve_fast(e) { bad += 1; } }
    let mut bad_ata = 0;
    for i in 0..m {
        let o: Pk = Sha256::digest((i as u64 * 3 + 1).to_le_bytes()).into();
        let mi: Pk = Sha256::digest((i as u64 * 7 + 5).to_le_bytes()).into();
        if ata_fast(&o, &mi, &crate::pda::TOKEN_2022) != crate::pda::ata(&o, &mi, &crate::pda::TOKEN_2022) { bad_ata += 1; }
    }
    (bad, bad_ata)
}

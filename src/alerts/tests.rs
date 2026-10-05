//! WP-20 tests. No test reaches the network: every sender here posts to a fake Bot API on 127.0.0.1 ([`Fake`]), whose
//! script says how it answers (200, 429 with `retry_after`, 5xx, a refusal that names the token, a dropped connection).
//! The token is a fake one made at run time (never a literal: tools/secret-scan.py would flag one).
use super::*;
use std::io::{Read, Write};
use std::net::TcpStream;

/// a fake bot token, shaped like a real one (`<digits>:AA<secret>`), made at run time
fn token() -> String { format!("{}:AA{}", 987_654_321u64, "Zq9x".repeat(9)) }
const CHAT: &str = "-1001234567890";

fn env_ok(k: &str) -> Option<String> {
    match k { "TELEGRAM_BOT_TOKEN" => Some(token()), "TELEGRAM_CHAT_ID" => Some(CHAT.to_string()), _ => None }
}
fn env_none(_: &str) -> Option<String> { None }

/// short timings: no coalescing, no dedup, no spacing, a wide rate, quick retries
fn quick() -> Tuning {
    Tuning { window: Duration::from_secs(60), spacing: Duration::ZERO, coalesce: Duration::ZERO, dedup: Duration::ZERO, retry_base: Duration::from_millis(10),
        max_attempts: 3, retry_after_cap: Duration::from_secs(5), refused_pause: Duration::from_millis(20), http_timeout: Duration::from_secs(5), queue: 256,
        tick: Duration::from_millis(20) }
}

fn on(rate: u32) -> AlertsCfg { AlertsCfg { enabled: true, rate_per_min: rate, ..Default::default() } }

fn alerts_at(base: &str, cfg: &AlertsCfg, t: Tuning) -> Arc<Alerts> {
    let (a, _) = Alerts::with(cfg, t, &env_ok, base, Ctx { label: "seg-test".into(), ..Default::default() });
    assert!(a.enabled(), "{:?}", a.off_why());
    a
}

fn runtime() -> tokio::runtime::Runtime { tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build().unwrap() }

fn wait_for(what: &str, secs: u64, f: impl Fn() -> bool) {
    let until = Instant::now() + Duration::from_secs(secs);
    while !f() {
        assert!(Instant::now() < until, "timed out waiting for {what}");
        std::thread::sleep(Duration::from_millis(10));
    }
}

fn info(key: &str, title: &str) -> Alert { Alert::new(Level::Info, "test", key, title) }

// ------------------------------------------------------------------ the fake Bot API

#[derive(Clone, Debug)]
struct Req { path: String, body: Value, at: Instant }

#[derive(Clone, Debug)]
enum Reply { Ok, Status(u16, String), Close, Hang(Duration) }

struct Fake { base: String, reqs: Arc<Mutex<Vec<Req>>>, script: Arc<Mutex<VecDeque<Reply>>> }

impl Fake {
    fn start() -> Fake {
        let l = std::net::TcpListener::bind("127.0.0.1:0").unwrap();
        let base = format!("http://{}", l.local_addr().unwrap());
        let (reqs, script) = (Arc::new(Mutex::new(Vec::new())), Arc::new(Mutex::new(VecDeque::new())));
        let (r, s) = (reqs.clone(), script.clone());
        std::thread::spawn(move || {
            let mut n = 0u64;
            for c in l.incoming() {
                let Ok(c) = c else { continue };
                n += 1;
                let (r, s) = (r.clone(), s.clone());
                std::thread::spawn(move || serve(c, n, &r, &s));
            }
        });
        Fake { base, reqs, script }
    }
    fn push(&self, r: Reply) { self.script.lock().unwrap().push_back(r); }
    fn reqs(&self) -> Vec<Req> { self.reqs.lock().unwrap().clone() }
    fn n(&self) -> usize { self.reqs.lock().unwrap().len() }
    fn texts(&self) -> Vec<String> { self.reqs().iter().map(|r| r.body["text"].as_str().unwrap_or("").to_string()).collect() }
}

fn serve(mut c: TcpStream, n: u64, reqs: &Mutex<Vec<Req>>, script: &Mutex<VecDeque<Reply>>) {
    let _ = c.set_read_timeout(Some(Duration::from_secs(5)));
    let (mut buf, mut tmp) = (Vec::new(), [0u8; 4096]);
    let head_end = loop {
        if let Some(p) = buf.windows(4).position(|w| w == b"\r\n\r\n") { break p + 4; }
        match c.read(&mut tmp) { Ok(0) | Err(_) => return, Ok(k) => buf.extend_from_slice(&tmp[..k]) }
    };
    let head = String::from_utf8_lossy(&buf[..head_end]).to_string();
    let path = head.split_whitespace().nth(1).unwrap_or("").to_string();
    let len = head.lines().find_map(|l| l.to_ascii_lowercase().strip_prefix("content-length:").map(|v| v.trim().parse::<usize>().unwrap_or(0))).unwrap_or(0);
    while buf.len() < head_end + len { match c.read(&mut tmp) { Ok(0) | Err(_) => break, Ok(k) => buf.extend_from_slice(&tmp[..k]) } }
    let body: Value = serde_json::from_slice(&buf[head_end..(head_end + len).min(buf.len())]).unwrap_or(Value::Null);
    let reply = script.lock().unwrap().pop_front().unwrap_or(Reply::Ok);
    reqs.lock().unwrap().push(Req { path, body, at: Instant::now() });
    let (code, text) = match reply {
        Reply::Ok => (200, format!("{{\"ok\":true,\"result\":{{\"message_id\":{n}}}}}")),
        Reply::Status(code, text) => (code, text),
        Reply::Close => return,
        Reply::Hang(d) => { std::thread::sleep(d); return; }
    };
    let _ = write!(c, "HTTP/1.1 {code} X\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{text}", text.len());
}

// ------------------------------------------------------------------ rate, coalescing, dedup, retries

/// at most `rate_per_min` messages in the window: the third of two-a-window waits for the window to pass
#[test]
fn rate_limit_caps_messages_in_the_window() {
    let fake = Fake::start();
    let t = Tuning { window: Duration::from_secs(3), ..quick() };
    let a = alerts_at(&fake.base, &on(2), t);
    let rt = runtime();
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    a.raise(info("a1", "one").once());
    wait_for("the first message", 10, || fake.n() == 1);
    a.raise(info("a2", "two").once());
    wait_for("the second message", 10, || fake.n() == 2);
    a.raise(info("a3", "three").once());
    std::thread::sleep(Duration::from_millis(300));
    assert_eq!(fake.n(), 2, "the third waits: two messages already in this window");
    wait_for("the third message", 10, || fake.n() == 3);
    let r = fake.reqs();
    // (the window starts when the first message is noted, before its connection: the receipts' gap can be a little short)
    assert!(r[2].at.duration_since(r[0].at) >= Duration::from_millis(2_500), "the window passed first: {:?}", r[2].at.duration_since(r[0].at));
    let s = a.status_json();
    assert!(s["rate_waits_total"].as_u64().unwrap() >= 1, "{s}");
    assert_eq!((s["sent_total"].as_u64(), s["messages_total"].as_u64(), s["failed_total"].as_u64()), (Some(3), Some(3), Some(0)));
    // one message a `spacing` at most, too
    let mut r = Rate::new(20, Duration::from_secs(60), Duration::from_secs(1));
    let t0 = Instant::now();
    assert_eq!(r.wait(t0), None);
    r.note(t0);
    assert!(r.wait(t0 + Duration::from_millis(200)).is_some_and(|w| w <= Duration::from_millis(800)));
    assert_eq!(r.wait(t0 + Duration::from_millis(1_001)), None);
    r.block(t0 + Duration::from_secs(7));
    assert!(r.wait(t0 + Duration::from_secs(2)).is_some_and(|w| w > Duration::from_secs(4)), "a 429 holds every message");
}

/// a burst within `coalesce_ms` goes out as one message holding every alert, oldest first; a Critical one does not
/// wait for the window
#[test]
fn bursts_coalesce_into_one_message() {
    let fake = Fake::start();
    let a = alerts_at(&fake.base, &on(20), Tuning { coalesce: Duration::from_millis(400), ..quick() });
    let rt = runtime();
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    for i in 0..5 { assert!(a.raise(info(&format!("k{i}"), &format!("burst alert {i}")).once())); }
    wait_for("the message", 10, || fake.n() >= 1);
    std::thread::sleep(Duration::from_millis(600));
    assert_eq!(fake.n(), 1, "one message for the burst");
    let text = &fake.texts()[0];
    let pos: Vec<usize> = (0..5).map(|i| text.find(&format!("burst alert {i}")).unwrap_or_else(|| panic!("alert {i} in {text}"))).collect();
    assert!(pos.windows(2).all(|w| w[0] < w[1]), "in order");
    assert_eq!(fake.reqs()[0].body["parse_mode"], "HTML");
    assert_eq!(fake.reqs()[0].body["chat_id"], CHAT);
    let s = a.status_json();
    assert_eq!((s["messages_total"].as_u64(), s["sent_total"].as_u64(), s["coalesced_total"].as_u64()), (Some(1), Some(5), Some(4)));
    // a Critical alert goes at once, with what waits beside it
    let fake = Fake::start();
    let a = alerts_at(&fake.base, &on(20), Tuning { coalesce: Duration::from_secs(30), ..quick() });
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    let t0 = Instant::now();
    a.raise(info("x", "waiting info").once());
    a.raise(Alert::new(Level::Critical, "test", "c", "critical now").once());
    wait_for("the critical message", 10, || fake.n() == 1);
    assert!(t0.elapsed() < Duration::from_secs(10), "not held for the 30 s window");
    assert!(fake.texts()[0].contains("waiting info") && fake.texts()[0].contains("critical now"));
}

/// a repeat within `dedup_s` is counted, not sent; the next one sent says how many were suppressed
#[test]
fn dedup_suppresses_repeats_and_counts_them() {
    let fake = Fake::start();
    let a = alerts_at(&fake.base, &on(20), Tuning { dedup: Duration::from_millis(700), ..quick() });
    let rt = runtime();
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    let mut sent = 0;
    for _ in 0..5 { if a.raise(info("same", "recorder dropped records")) { sent += 1; } }
    assert_eq!(sent, 1);
    wait_for("the first message", 10, || fake.n() == 1);
    assert_eq!(a.status_json()["deduped_total"].as_u64(), Some(4));
    std::thread::sleep(Duration::from_millis(800));
    assert!(a.raise(info("same", "recorder dropped records")), "the window ended");
    wait_for("the second message", 10, || fake.n() == 2);
    assert!(fake.texts()[1].contains("+4 like it"), "{}", fake.texts()[1]);
    // `once` alerts (wins, lifecycle) are never deduplicated; other keys pass
    assert!(a.raise(info("same", "x").once()) && a.raise(info("other", "y")));
}

/// state transitions (one family): a change suppressed by the dedup is held and sent when its window ends, so the last
/// word is never stale for longer than `dedup_s`; a state that went back meanwhile sends nothing more
#[test]
fn held_transition_is_sent_when_its_window_ends() {
    let down = || classify("state_unavailable", &json!({ "why": "stream down", "age_ms": 3_000, "connected": false, "reconnects": 2, "error": "status: Unavailable, 503" })).unwrap();
    let up = || classify("state_available", &json!({ "down_ms": 5_000, "reconnects": 2 })).unwrap();
    let fake = Fake::start();
    let a = alerts_at(&fake.base, &on(20), Tuning { dedup: Duration::from_secs(4), ..quick() });
    let rt = runtime();
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    assert!(a.raise(down()));
    wait_for("down", 10, || fake.n() == 1);
    assert!(a.raise(up()));
    wait_for("up", 10, || fake.n() == 2);
    assert!(!a.raise(down()), "a repeat of down inside its window: held, not sent");
    std::thread::sleep(Duration::from_millis(300));
    assert_eq!(fake.n(), 2);
    wait_for("the held down", 10, || fake.n() == 3);
    assert!(fake.texts()[2].contains("state stream down"), "{}", fake.texts()[2]);
    assert!(a.status_json()["held_total"].as_u64().unwrap() >= 1);
    // down, up, down (held), up again (the last word stands): nothing more after the window
    let fake = Fake::start();
    let a = alerts_at(&fake.base, &on(20), Tuning { dedup: Duration::from_secs(4), ..quick() });
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    a.raise(down());
    a.raise(up());
    wait_for("down and up", 10, || fake.texts().join("\n").contains("state stream back"));
    let n = fake.n();
    assert!(!a.raise(down()) && !a.raise(up()));
    std::thread::sleep(Duration::from_millis(4_600));
    assert_eq!(fake.n(), n, "the state went back to what was said last");
}

/// a 429 is retried after its `retry_after`; a 5xx after a backoff, then counted failed; a refused HTML is sent again as
/// plain text; a moved group is followed to its new chat id
#[test]
fn retries_honour_retry_after_and_count_failures() {
    let fake = Fake::start();
    fake.push(Reply::Status(429, r#"{"ok":false,"error_code":429,"description":"Too Many Requests: retry after 1","parameters":{"retry_after":1}}"#.into()));
    let a = alerts_at(&fake.base, &on(20), quick());
    let rt = runtime();
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    a.raise(info("r", "after a 429").once());
    wait_for("the retry", 10, || fake.n() == 2);
    let r = fake.reqs();
    assert!(r[1].at.duration_since(r[0].at) >= Duration::from_millis(950), "retry_after honoured: {:?}", r[1].at.duration_since(r[0].at));
    wait_for("the count", 5, || a.status_json()["sent_total"] == json!(1));
    let s = a.status_json();
    assert_eq!((s["failed_total"].as_u64(), s["attempts_failed_total"].as_u64()), (Some(0), Some(1)));
    assert!(s["last_error"].as_str().unwrap().contains("429"), "{s}");
    // 5xx three times (max_attempts 3): failed, counted
    for _ in 0..3 { fake.push(Reply::Status(502, "<html>bad gateway</html>".into())); }
    a.raise(info("f", "lost to 5xx").once());
    wait_for("three tries", 10, || fake.n() == 5);
    wait_for("the failure", 5, || a.status_json()["failed_total"] == json!(1));
    assert!(a.status_json()["last_error"].as_str().unwrap().contains("502"));
    // HTML the API cannot parse: the same message again as plain text
    fake.push(Reply::Status(400, r#"{"ok":false,"error_code":400,"description":"Bad Request: can't parse entities: unsupported start tag"}"#.into()));
    a.raise(info("p", "plain <fallback> & co").once());
    wait_for("the plain retry", 10, || fake.n() == 7);
    let r = fake.reqs();
    assert_eq!(r[5].body["parse_mode"], "HTML");
    assert!(r[6].body.get("parse_mode").is_none(), "plain: {}", r[6].body);
    assert!(r[6].body["text"].as_str().unwrap().contains("plain <fallback> & co"), "unescaped in plain text");
    // a group upgraded to a supergroup: its new chat id, for the rest of the process
    fake.push(Reply::Status(400, r#"{"ok":false,"error_code":400,"description":"Bad Request: group chat was upgraded to a supergroup chat","parameters":{"migrate_to_chat_id":-1009999}}"#.into()));
    a.raise(info("m", "moved").once());
    wait_for("the move", 10, || fake.n() == 9);
    assert_eq!(fake.reqs()[8].body["chat_id"], "-1009999");
    // a dropped connection is a transport error, retried
    fake.push(Reply::Close);
    a.raise(info("c", "after a dropped connection").once());
    wait_for("the retry", 10, || fake.n() == 11);
    wait_for("delivered", 5, || a.status_json()["sent_total"] == json!(4));
    assert!(fake.reqs().iter().all(|r| r.path == format!("/bot{}/sendMessage", token())), "the token goes in the URL path, nowhere else");
}

// ------------------------------------------------------------------ never blocking

/// the producers never wait: a full queue drops (and counts) at once, with or without a sender, even one stuck on a
/// server that does not answer, and a held dedup map lets an alert through
#[test]
fn the_sink_never_blocks_when_full() {
    let a = alerts_at("http://127.0.0.1:9", &on(20), Tuning { queue: 8, ..quick() });
    let (mut worst, t0) = (Duration::ZERO, Instant::now());
    for i in 0..20_000u32 {
        let t = Instant::now();
        a.raise(info(&format!("k{i}"), "fill").once());
        worst = worst.max(t.elapsed());
    }
    let total = t0.elapsed();
    let s = a.status_json();
    assert_eq!((s["queued_now"].as_u64(), s["dropped_total"].as_u64()), (Some(8), Some(20_000 - 8)), "{s}");
    // a wait on the network would take seconds (the stuck server below holds a request 30 s); a loaded machine's
    // preemption takes a few ms
    assert!(worst < Duration::from_millis(500) && total < Duration::from_secs(5), "worst {worst:?}, total {total:?}");
    // a sender stuck on a server that never answers: still no wait
    let fake = Fake::start();
    for _ in 0..4 { fake.push(Reply::Hang(Duration::from_secs(30))); }
    let a = alerts_at(&fake.base, &on(20), Tuning { queue: 8, http_timeout: Duration::from_secs(20), ..quick() });
    let rt = runtime();
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    a.raise(info("first", "stuck").once());
    wait_for("the stuck request", 10, || fake.n() == 1);
    let (mut worst, t0) = (Duration::ZERO, Instant::now());
    for i in 0..20_000u32 {
        let t = Instant::now();
        a.raise(info(&format!("j{i}"), "fill").once());
        worst = worst.max(t.elapsed());
    }
    assert!(worst < Duration::from_millis(500) && t0.elapsed() < Duration::from_secs(5), "worst {worst:?}");
    assert!(a.status_json()["dropped_total"].as_u64().unwrap() >= 20_000 - 8);
    // the dedup state held by another thread: the alert goes through after a short spin, nothing waits
    let a = alerts_at("http://127.0.0.1:9", &on(20), Tuning { dedup: Duration::from_secs(600), ..quick() });
    let guard = a.dd.lock().unwrap();
    let t = Instant::now();
    assert!(a.raise(info("busy", "the map is held")));
    assert!(t.elapsed() < Duration::from_millis(100));
    drop(guard);
    // flush on a sender that is not running never waits either
    assert!(!a.flush(Duration::from_secs(30)) && t.elapsed() < Duration::from_secs(5));
}

// ------------------------------------------------------------------ the token

/// a writer the recorder echoes stdout / stderr lines into
#[derive(Clone, Default)]
struct Shared(Arc<Mutex<Vec<u8>>>);
impl Write for Shared {
    fn write(&mut self, b: &[u8]) -> std::io::Result<usize> { self.0.lock().unwrap().extend_from_slice(b); Ok(b.len()) }
    fn flush(&mut self) -> std::io::Result<()> { Ok(()) }
}

fn every_file(d: &std::path::Path, out: &mut Vec<(PathBuf, Vec<u8>)>) {
    for e in std::fs::read_dir(d).unwrap().flatten() {
        let p = e.path();
        if p.is_dir() { every_file(&p, out); continue; }
        let b = if p.extension().is_some_and(|x| x == "zst") { crate::rec::decode_zst(&p).unwrap().0 } else { std::fs::read(&p).unwrap() };
        out.push((p, b));
    }
}

/// A segment-like run with a fake token: events through the recorder's tap, a win, the panic path, the exit message,
/// against a server that refuses with the token in its answer and drops a connection. The token (and its secret half)
/// is in no file of the segment, no echoed line, not in the status counters, the config dump or a Debug print
#[test]
fn the_token_never_appears_in_any_record_or_log() {
    let tok = token();
    let secret = tok.split_once(':').unwrap().1.to_string();
    let dir = std::env::temp_dir().join(format!("arbx-alerts-token-{}-{}", std::process::id(), real_ns()));
    let echo = Shared::default();
    let rec = crate::rec::start(crate::rec::Opts { dir: dir.clone(), run: "seg-token".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![],
        monitor: false, echo: Some(Box::new(echo.clone())) }).unwrap();
    rec.open_now(crate::rec::STATUS).unwrap();
    rec.json(crate::rec::STATUS, json!({ "seq": 0, "t_ns": real_ns(), "exec": { "decisions_total": 7, "sent_total": 1, "ok_total": 1 },
        "money": { "round_trip_total_lamports": 9_000, "tips_paid_total_lamports": 1_000, "fees_landed_total_lamports": 5_000 } }));
    let fake = Fake::start();
    let refusal = format!(r#"{{"ok":false,"error_code":401,"description":"Unauthorized: bot{tok} is not a valid token (url https://api.telegram.org/bot{tok}/sendMessage)"}}"#);
    fake.push(Reply::Status(500, format!("<html>upstream said /bot{tok}/sendMessage failed</html>")));
    fake.push(Reply::Close);
    fake.push(Reply::Status(401, refusal.clone()));
    for _ in 0..8 { fake.push(Reply::Status(401, refusal.clone())); }
    let cfg = on(20);
    let (a, notes) = Alerts::with(&cfg, quick(), &env_ok, &fake.base, Ctx { label: "seg-token".into(), dir: Some(dir.clone()), started_ns: real_ns(), ..Default::default() });
    for n in &notes { rec.say(n.clone()); }
    a.set_rec(rec.clone());
    let w = Arc::downgrade(&a);
    rec.set_alert_tap(Box::new(move |kind, _s, _f, d| if let Some(x) = w.upgrade() { x.on_event(kind, d) }));
    let rt = runtime();
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    // health events through the recorder's tap (other subsystems never hold the bot's token: their own secrets are cut
    // by rpc::scrub, the api-key here; built at run time, as the token is, so no credential-shaped literal is in the source)
    rec.event("state_unavailable", "state", None, json!({ "why": "stream down", "error": format!("transport error for https://grpc.example/x?{}=K3YVALUE0000", "api-key") }));
    rec.event("recorder_drop", "recorder", None, json!({ "stream": "rivals", "class": "bulk", "dropped_total": 3, "why": "queue full" }));
    rec.event("jito_token_refresh", "jito", None, json!({ "ok": false, "error": "PermissionDenied", "retry_s": 2, "stale": true }));
    a.win(&Win { route: Some("PumpSwap>Dlmm".into()), mint: "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263".into(), size_lamports: 500_000_000, gross_lamports: Some(9_000),
        tip_lamports: 1_000, fee_lamports: 5_000, signature: "5".repeat(88), ..Default::default() });
    a.note_stream_error("tx-haan", &format!("status: Unavailable, message: \"503 for /bot{tok}\""));
    wait_for("the sends to fail", 20, || a.status_json()["failed_total"].as_u64().unwrap_or(0) >= 1 && a.status_json()["queued_now"] == json!(0)
        && a.status_json()["pending_now"] == json!(0));
    // the panic path (another thread: queued) and the exit message (now, refused with the token in the answer)
    a.on_panic("arbx-hot", "src/x.rs:1", &format!("bad url https://api.telegram.org/bot{tok}/sendMessage"));
    let r = a.exit(30, "error", &format!("boot failed: https://api.telegram.org/bot{tok}/getMe"), Some(("panic", &format!("again {tok}"))));
    assert!(matches!(r, Some(Err(_))), "the exit message was refused: {r:?}");
    assert!(fake.reqs().iter().any(|r| r.path.contains(&tok)), "the fake server did see the token in the URL (the test means something)");
    for r in fake.reqs() { let b = r.body.to_string(); assert!(!b.contains(&tok) && !b.contains(&secret) && !b.contains("K3YVALUE0000"), "a message carried a secret: {b}"); }
    let status = a.status_json().to_string();
    let debug = format!("{a:?} {:?}", a.creds);
    let dump = crate::provenance::section(&cfg).to_string();
    rec.close();
    let mut files = Vec::new();
    every_file(&dir, &mut files);
    assert!(files.iter().any(|(p, _)| p.ends_with("events.jsonl")) && files.iter().any(|(p, _)| p.ends_with("run.log")));
    let events = String::from_utf8_lossy(&files.iter().find(|(p, _)| p.ends_with("events.jsonl")).unwrap().1).to_string();
    assert!(events.contains("\"alert_failed\""), "the failures are events: {events}");
    let echoed = String::from_utf8_lossy(&echo.0.lock().unwrap()).to_string();
    for (what, text) in files.iter().map(|(p, b)| (p.display().to_string(), String::from_utf8_lossy(b).to_string()))
        .chain([("echo".to_string(), echoed), ("status".into(), status.clone()), ("debug".into(), debug), ("config".into(), dump)]) {
        assert!(!text.contains(&tok) && !text.contains(&secret), "the token is in {what}: {text}");
    }
    assert!(status.contains("<redacted>") || status.contains("HTTP 401"), "last_error kept, redacted: {status}");
    let _ = std::fs::remove_dir_all(&dir);
}

// ------------------------------------------------------------------ the panic hook

const PANIC_CHILD: &str = "ARBX_ALERTS_PANIC_CHILD";

/// Not a test on its own: the child process of `the_panic_hook_sends` (a no-op without its variable). It installs the
/// hook and panics on a thread named `worker`, then on one named `main` (what the engine's thread is called)
#[test]
fn panic_hook_child() {
    let Ok(base) = std::env::var(PANIC_CHILD) else { return };
    let (a, _) = Alerts::with(&on(20), quick(), &env_ok, &base, Ctx { label: "seg-panic".into(), ..Default::default() });
    assert!(install(a));
    install_panic_hook();
    let _ = std::thread::Builder::new().name("worker".into()).spawn(|| panic!("worker <b>boom</b>")).unwrap().join();
    let _ = std::thread::Builder::new().name("main".into()).spawn(|| panic!("engine <i>boom</i> & bust")).unwrap().join();
}

/// a panic on the main thread sends a Critical alert from the hook (with what was queued: a worker's panic before it)
#[test]
fn the_panic_hook_sends() {
    let fake = Fake::start();
    let out = std::process::Command::new(std::env::current_exe().unwrap()).args(["alerts::tests::panic_hook_child", "--exact", "--nocapture", "--test-threads", "1"])
        .env(PANIC_CHILD, &fake.base).output().unwrap();
    let (so, se) = (String::from_utf8_lossy(&out.stdout).to_string(), String::from_utf8_lossy(&out.stderr).to_string());
    assert!(out.status.success(), "{so}\n{se}");
    assert!(so.contains("1 passed"), "the child ran: {so}");
    wait_for("the crash alert", 10, || fake.texts().join("\n").contains("CRASH"));
    let all = fake.texts().join("\n");
    assert!(all.contains("CRASH: seg-panic panicked") && all.contains("engine &lt;i&gt;boom&lt;/i&gt; &amp; bust"), "{all}");
    assert!(all.contains("panic in thread worker") && all.contains("worker &lt;b&gt;boom&lt;/b&gt;"), "the queued alert went with it: {all}");
    assert!(!so.contains(&token()) && !se.contains(&token()));
}

// ------------------------------------------------------------------ formatting

/// outside data is escaped everywhere (mint names, errors, labels), links only for real signatures, messages cut by
/// whole alerts under Telegram's limit, text cut on character boundaries
#[test]
fn message_formatting_escapes_and_fits() {
    use format::*;
    assert_eq!(esc(r#"<b>"x" & y</b>"#), "&lt;b&gt;&quot;x&quot; &amp; y&lt;/b&gt;");
    let w = Win { route: Some("Pump<Swap>".into()), mint: "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263".into(), mint_name: Some("<script>alert(1)</script>&co".into()),
        size_lamports: 500_000_000, gross_lamports: Some(1_250_000), tip_lamports: 100_000, fee_lamports: 5_000, rent_lamports: 0, slot: Some(371_234_567),
        signature: "5VERv8NMvzbJMEkV8xnrLkEaWRtSz9CosKDYjCJjBRnbJLgp8uirBgmQpjKhoR4tjF3ZpRzrFmBV6UjKdiSZkQUW".into(), attempt: Some(4) };
    let a = win_alert(&w);
    let (text, n) = compose("seg <1>", real_ns(), std::slice::from_ref(&a), MAX_TEXT);
    assert_eq!(n, 1);
    assert!(text.contains("&lt;script&gt;alert(1)&lt;/script&gt;&amp;co") && !text.contains("<script>"), "{text}");
    assert!(text.contains("Pump&lt;Swap&gt;") && text.contains("seg &lt;1&gt;"));
    assert!(text.contains("succeeded · net +0.001145 SOL"), "F12: succeeded and the realised net: {text}");
    assert!(!text.to_lowercase().contains("profit") && !text.contains("WIN"));
    assert!(text.contains("<a href=\"https://solscan.io/tx/5VERv8"), "{text}");
    assert!(text.contains("371,234,567"));
    // a net at or below 0 after fee, tip and rent is never a win
    let lost = win_alert(&Win { rent_lamports: 2_039_280, ..w.clone() });
    assert!(lost.title.contains("succeeded but lost: net -0.00089428 SOL") && lost.level == Level::Warning, "{}", lost.title);
    assert!(lost.body.contains("rent 0.00203928"), "{}", lost.body);
    // an href takes nothing but a signature
    assert_eq!(solscan_tx("x\" onclick=\"y"), None);
    assert!(render(&win_alert(&Win { signature: "\"><b>".into(), ..w.clone() }), real_ns()).contains("&quot;&gt;&lt;b&gt;"));
    // many alerts: whole ones per message, under the limit
    let many: Vec<Alert> = (0..200).map(|i| info(&format!("k{i}"), &format!("alert {i} {}", "x".repeat(100)))).collect();
    let (text, n) = compose("seg", real_ns(), &many, MAX_TEXT);
    assert!(n > 1 && n < 200 && text.chars().count() <= MAX_TEXT, "{n} alerts, {} chars", text.chars().count());
    // one alert longer than a message: its text, cut and escaped, no tag left open
    let mut big = info("big", "big");
    big.body = format!("<code>{}</code>", esc(&"<&>é🦀".repeat(2_000)));
    let (text, n) = compose("seg", real_ns(), &[big], 500);
    assert!(n == 1 && text.chars().count() <= 500 && !text.contains("<code>") && text.contains("&lt;&amp;&gt;é🦀"), "{text}");
    assert_eq!(cut("é🦀abc", 3), "é🦀…");
    assert_eq!(cut("a\u{0}b\u{1b}c", 10), "abc", "control characters dropped");
    assert_eq!(to_plain("<b>a &lt;b&gt; &amp; c</b>"), "a <b> & c");
    assert_eq!((sol(34_000_000), sol(5_000), sol(-1_250_000_000), sol_signed(0)), ("0.0340 SOL".to_string(), "0.000005 SOL".to_string(), "-1.2500 SOL".to_string(), "+0.0000 SOL".to_string()));
    assert_eq!((int(0), int(999), int(1_000), int(12_345_678)), ("0".to_string(), "999".to_string(), "1,000".to_string(), "12,345,678".to_string()));
    assert_eq!((dur(45), dur(600), dur(7_980), dur(200_000)), ("45s".to_string(), "10m".to_string(), "2h13m".to_string(), "2d7h".to_string()));
    assert_eq!((utc_date(0), utc_date(1_791_331_200_000_000_000), utc_hms(1_791_331_200_000_000_000 + 3_723_000_000_000)),
        ("1970-01-01".to_string(), "2026-10-07".to_string(), "01:02:03".to_string()));
    assert_eq!((short_key("FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"), short_key("short")), ("FRZh…yTWS".to_string(), "short".to_string()));
    // an alert older than a minute says when it happened
    let mut old = info("old", "old");
    old.t_ns = real_ns() - 120_000_000_000;
    assert!(render(&old, real_ns()).contains(" UTC)</i>"));
    // the daily summary: the win ratio is wins ÷ bundles sent, beside its numbers, the net and the fees, tips and rent
    let d = summary::DayTotals { day: "2026-10-04".into(), segments: 24, crashes: 1, sends: 1_003, sends_known: true, wins: 12, net_lamports: 3_100_000, net_known: true,
        net_src: Some("ledger"), fees: 5_015_000, tips: 1_200_000, rent: 0, budget_left: Some(29_000_000), ..Default::default() };
    let t = compose("watchdog", real_ns(), &[daily_alert(&d)], MAX_TEXT).0;
    assert!(t.contains("win ratio = wins ÷ bundles sent: 1.2% (12 wins / 1,003 sent)") && t.contains("net +0.0031 SOL (ledger)"), "{t}");
    assert!(t.contains("fees 0.005015") && t.contains("tips 0.0012") && t.contains("rent 0.0000"), "{t}");
    let none = daily_alert(&summary::DayTotals { day: "x".into(), wins: 0, ..Default::default() });
    assert!(none.body.contains("win ratio = wins ÷ bundles sent: no sends (0 wins)") && !none.body.contains('%'), "{}", none.body);
}

/// which events alert, at which level, with which key
#[test]
fn events_classify_into_alerts() {
    let c = |k: &str, d: Value| classify(k, &d);
    let x = c("recorder_drop", json!({ "stream": "attempts", "class": "core", "dropped_total": 1 })).unwrap();
    assert_eq!((x.level, x.key.as_str()), (Level::Error, "recorder_drop:attempts"));
    assert_eq!(c("recorder_drop", json!({ "stream": "rivals", "class": "bulk" })).unwrap().level, Level::Warning);
    assert_eq!(c("disk_action", json!({ "action": "shadow_and_stop" })).unwrap().level, Level::Critical);
    assert_eq!(c("disk_action", json!({ "action": "stop_rivals" })).unwrap().key, "disk:stop_rivals");
    assert_eq!(c("recorder_fatal", json!({ "detail": "x" })).unwrap().level, Level::Critical);
    assert_eq!(c("state_unavailable", json!({ "why": "boot_timeout" })).unwrap().level, Level::Critical);
    let down = c("state_unavailable", json!({ "why": "stream down", "error": format!("https://h.example/p?{}=SECRETVALUE1234", "api-key") })).unwrap();
    assert!(down.level == Level::Error && down.family == Some("state") && !down.body.contains("SECRETVALUE1234"), "URLs cut: {}", down.body);
    assert_eq!(c("state_available", json!({ "down_ms": 1 })).unwrap().level, Level::Info);
    assert_eq!(c("state_resync_slow", json!({})).unwrap().key, "resync_slow");
    assert_eq!(c("chainfetch_dead", json!({ "why": "panic" })).unwrap().level, Level::Error);
    assert!(c("jito_token_refresh", json!({ "ok": true, "via": "refresh" })).is_none(), "a renewal that worked is no alert");
    assert!(c("jito_token_refresh", json!({ "ok": false, "error": "x", "stale": true })).unwrap().title.contains("sends are refused"));
    assert_eq!(c("jito_stream_down", json!({ "error": "x" })).unwrap().family, Some("jito_stream"));
    for quiet in ["late_member", "alts_preload", "leaders_refresh", "log", "alert_sent", "alert_failed", "gate_change", "lag_slo_breach"] { assert!(c(quiet, json!({})).is_none(), "{quiet}"); }
    // the SendGate's changes
    let live = ("live".to_string(), String::new());
    assert_eq!(gate_alert(&live, "shadow", "core_record_loss", "x", true).unwrap().level, Level::Error);
    assert_eq!(gate_alert(&live, "shadow", "control", "pause by moiz", false).unwrap().level, Level::Info);
    assert_eq!(gate_alert(&live, "shadow", "equity_floor", "", true).unwrap().level, Level::Critical);
    assert_eq!(gate_alert(&("shadow".into(), "control".into()), "live", "", "resume", false).unwrap().key, "gate:live");
    assert!(gate_alert(&live, "stopped", "deadline", "", true).is_none(), "the stop message says it");
}

/// the redaction: the token, its secret half, its URL-encoded form, any bot-token shape, URL paths
#[test]
fn redaction_removes_every_form_of_the_token() {
    let tok = token();
    let secret = tok.split_once(':').unwrap().1;
    let s = format!("a {tok} b {secret} c {} d bot{tok}/x e https://api.telegram.org/bot{tok}/sendMessage?x=1", tok.replace(':', "%3A"));
    let r = telegram::redact(&s, &tok);
    assert!(!r.contains(secret) && !r.contains("987654321:AA"), "{r}");
    let other = format!("{}:AA{}", 1_234_567_890u64, "k".repeat(35));
    assert!(!telegram::redact(&format!("x bot{other} y"), "").contains(&other), "a token shape, whoever's");
    assert_eq!(telegram::mask_token_shapes("slot 12:34 and 2026-10-05T12:34:56"), "slot 12:34 and 2026-10-05T12:34:56", "no false hit on times");
    assert!(telegram::base_ok("https://api.telegram.org") && telegram::base_ok("http://127.0.0.1:8080") && telegram::base_ok("http://localhost"));
    assert!(!telegram::base_ok("http://api.telegram.org") && !telegram::base_ok("http://127.0.0.1.evil.example") && !telegram::base_ok("ftp://x"));
}

/// missing variables turn the alerts off with one warning, never fatal; `enabled = false` says nothing; a plain-http
/// base is refused (I-10)
#[test]
fn missing_env_disables_with_one_warning() {
    let (a, notes) = Alerts::new(&on(20), &env_none, Ctx::default());
    assert!(!a.enabled());
    assert_eq!(notes.len(), 1, "{notes:?}");
    assert!(notes[0].starts_with("WARNING: alerts off: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID not set"), "{}", notes[0]);
    assert!(!a.raise(info("k", "x")) && !a.win(&Win::default()));
    assert_eq!(a.status_json()["enabled"], false);
    assert!(a.flush(Duration::from_secs(5)));
    assert!(a.exit(0, "deadline", "x", None).is_none() && a.deliver_now(vec![info("k", "x")], Duration::from_secs(1)).is_err());
    let only_chat = |k: &str| (k == "TELEGRAM_CHAT_ID").then(|| CHAT.to_string());
    let (a, notes) = Alerts::new(&on(20), &only_chat, Ctx::default());
    assert!(!a.enabled() && notes[0].contains("TELEGRAM_BOT_TOKEN not set") && !notes[0].contains("TELEGRAM_CHAT_ID not set"));
    let (a, notes) = Alerts::new(&AlertsCfg::default(), &env_ok, Ctx::default());
    assert!(!a.enabled() && notes.is_empty() && a.off_why() == Some("[alerts] enabled = false"));
    let (a, _) = Alerts::with(&on(20), quick(), &env_ok, "http://api.telegram.org", Ctx::default());
    assert!(!a.enabled(), "never the token over plain http to a remote host");
    let (a, notes) = Alerts::new(&on(20), &env_ok, Ctx::default());
    assert!(a.enabled() && notes.len() == 1 && notes[0].starts_with("alerts on") && !notes[0].contains(&token()) && !notes[0].contains(CHAT));
    let bad = |k: &str| match k { "TELEGRAM_BOT_TOKEN" => Some("not-a-token".to_string()), _ => env_ok(k) };
    let (_, notes) = Alerts::new(&on(20), &bad, Ctx::default());
    assert!(notes.iter().any(|n| n.contains("does not look like a bot token") && !n.contains("not-a-token")));
}

/// `[alerts]` checks: a variable's name, not a value (and the value is not echoed); levels, rates
#[test]
fn alerts_config_checks() {
    let base = AlertsCfg::default();
    assert!(base.check().is_ok());
    let e = AlertsCfg { token_env: token(), ..base.clone() }.check().unwrap_err().to_string();
    assert!(e.contains("token_env must name an environment variable") && !e.contains(&token()), "{e}");
    assert!(AlertsCfg { chat_env: "-100123".into(), ..base.clone() }.check().is_err());
    // a token's secret half (mixed case, no `-` or `:`) is no variable name either, and is not echoed
    let half = format!("AA{}", "hT7kQ".repeat(7));
    let e = AlertsCfg { token_env: half.clone(), ..base.clone() }.check().unwrap_err().to_string();
    assert!(!e.contains(&half), "{e}");
    assert!(AlertsCfg { token_env: "MY_BOT_TOKEN_2".into(), ..base.clone() }.check().is_ok());
    assert!(AlertsCfg { min_level: "loud".into(), ..base.clone() }.check().is_err());
    assert!(AlertsCfg { rate_per_min: 0, ..base.clone() }.check().is_err() && AlertsCfg { rate_per_min: 61, ..base.clone() }.check().is_err());
    assert!(AlertsCfg { low_balance_sol: f64::NAN, ..base.clone() }.check().is_err());
    let t: AlertsCfg = toml::from_str("enabled = true").unwrap();
    assert_eq!((t.token_env.as_str(), t.chat_env.as_str(), t.heartbeat_min, t.min_level.as_str(), t.dedup_s, t.rate_per_min), ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", 60, "info", 600, 20));
    assert!(toml::from_str::<AlertsCfg>("token = \"x\"").is_err(), "unknown keys refused");
}

// ------------------------------------------------------------------ the status line, the day, the monitor

#[test]
fn snapshot_reads_each_generation_of_the_status_line() {
    // WP-02 (before WP-05): attempts are no sends (they count would-sends: STAGE1-PLAN §1), the bot's profit no chain net
    let v2 = json!({ "t_ns": 5, "exec": { "attempts_total": 4, "landed_total": 2, "ok_total": 1 }, "counts_total": { "evaluation": 99, "state_opportunity": 3 },
        "money": { "failed_fees_total_lamports": 10_000, "bot_profit_total_lamports": 50_000, "failed_fees_cap_now_lamports": 1_000_000 } });
    let s = Snapshot::of(&v2);
    assert_eq!((s.sends, s.wins, s.decisions, s.opportunities, s.net_lamports, s.budget_left()), (None, Some(1), Some(99), Some(3), None, Some(990_000)));
    // WP-05: sent, would-send, the chain-derived round trip; rent of new token accounts subtracted (F12)
    let v5 = json!({ "t_ns": 6, "send_gate": { "mode": "live" }, "health": { "state_ok": true, "blockhash_age_slots_now": 3 }, "slot": { "processed": 10, "tip": 11 },
        "exec": { "decisions_total": 120, "would_send_total": 7, "attempts_total": 9, "sent_total": 5, "landed_total": 3, "ok_total": 2, "stopped": null },
        "money": { "round_trip_total_lamports": 3_000_000, "tips_paid_total_lamports": 200_000, "fees_landed_total_lamports": 15_000, "failed_fees_total_lamports": 5_000,
            "round_trip_unknown_total": 1, "new_token_accounts_total": 1, "failed_fees_cap_now_lamports": 34_000_000 } });
    let s = Snapshot::of(&v5);
    assert_eq!((s.sends, s.would_send, s.decisions, s.wins), (Some(5), Some(7), Some(120), Some(2)));
    assert_eq!(s.net_lamports, Some(3_000_000 - 200_000 - 15_000 - summary::ATA_RENT_LAMPORTS as i64));
    assert!(s.net_partial && s.rent_estimated && s.sender_stopped.is_none() && s.net_src == Some("wallet records"));
    assert_eq!((s.blockhash_age_slots, s.tip, s.gate_mode.as_deref()), (Some(3), Some(11), Some("live")));
    // WP-07: the ledger's net
    let v7 = json!({ "money": { "trade_net_total": -1_234, "rent_nonrecoverable_total": 10, "round_trip_total_lamports": 999 } });
    let s = Snapshot::of(&v7);
    assert_eq!((s.net_lamports, s.rent_lamports, s.rent_estimated, s.net_src), (Some(-1_234), Some(10), false, Some("ledger")));
    // the last line of a file, header and torn tail skipped
    let d = std::env::temp_dir().join(format!("arbx-alerts-last-{}-{}", std::process::id(), real_ns()));
    std::fs::create_dir_all(&d).unwrap();
    let p = d.join("status.jsonl");
    std::fs::write(&p, "{\"schema\":\"arbx.status/2.0\",\"file_seq\":0}\n{\"seq\":0,\"t_ns\":1}\n{\"seq\":1,\"t_ns\":2}\n{\"seq\":2,\"t_").unwrap();
    assert_eq!(summary::last_status(&p).unwrap()["seq"], 1);
    std::fs::write(&p, "{\"schema\":\"arbx.status/2.0\",\"file_seq\":0}\n").unwrap();
    assert!(summary::last_status(&p).is_none() && summary::last_status(&d.join("none")).is_none());
    let _ = std::fs::remove_dir_all(&d);
}

fn status_line(t: u64, sent: u64, wins: u64, rt: i64, fees: u64) -> String {
    json!({ "t_ns": t, "exec": { "sent_total": sent, "ok_total": wins, "landed_total": wins, "decisions_total": sent * 10 },
        "money": { "round_trip_total_lamports": rt, "tips_paid_total_lamports": 0, "fees_landed_total_lamports": fees, "failed_fees_total_lamports": 0,
            "failed_fees_cap_now_lamports": 1_000_000 } }).to_string()
}

/// a UTC day's totals over a runs directory: each segment's last value in the day minus its last before it; crashes
/// from stop.json; the budget left from the newest segment; one process claims each day
#[test]
fn daily_totals_and_markers() {
    let day = 20_000 * summary::DAY_NS;
    let runs = std::env::temp_dir().join(format!("arbx-alerts-day-{}-{}", std::process::id(), real_ns()));
    let (p1, p2, other) = (runs.join("c").join("c-p1"), runs.join("c").join("c-p2"), runs.join("solo"));
    for d in [&p1, &p2, &other] { std::fs::create_dir_all(d).unwrap(); }
    let h = "{\"schema\":\"arbx.status/2.0\",\"file_seq\":0}";
    // p1 spans midnight: 10 sent and 1 win before it, 30 and 3 by its end
    std::fs::write(p1.join("status.jsonl"), [h.to_string(), status_line(day - 5, 10, 1, 1_000, 50), status_line(day + 5, 30, 3, 4_000, 150)].join("\n")).unwrap();
    // p2 ran in the day and crashed
    std::fs::write(p2.join("status.jsonl"), [h.to_string(), status_line(day + 100, 5, 1, 2_000, 25)].join("\n")).unwrap();
    std::fs::write(p2.join("stop.json"), json!({ "reason": "panic", "ended_ns": day + 200 }).to_string()).unwrap();
    // a segment of the day after is not in it
    std::fs::write(other.join("status.jsonl"), [h.to_string(), status_line(day + summary::DAY_NS + 1, 99, 9, 9_000, 9)].join("\n")).unwrap();
    // a boot that failed before the engine started: no status line, still a crash of the day
    let p3 = runs.join("c").join("c-p3");
    std::fs::create_dir_all(&p3).unwrap();
    std::fs::write(p3.join("run.log"), "1 arbx …\n").unwrap();
    std::fs::write(p3.join("stop.json"), json!({ "reason": "error", "ended_ns": day + 300 }).to_string()).unwrap();
    let t = summary::day_totals(&runs, day);
    assert_eq!((t.segments, t.sends, t.sends_known, t.wins, t.crashes, t.fees), (2, 25, true, 3, 2, 125));
    // a period's totals (the heartbeat): only what changed in it
    let w = summary::totals(&runs, day + 50, day + 150);
    assert_eq!((w.segments, w.sends, w.wins), (1, 5, 1), "p2's line at day+100 only");
    let hb = heartbeat_alert("c-p2", "shadow", 4_000, &Snapshot { gate_mode: Some("shadow".into()), state_ok: Some(true), ..Default::default() }, &w, 3_600, 7);
    let text = format::compose("c-p2", real_ns(), &[hb], format::MAX_TEXT).0;
    assert!(text.contains("c-p2 up 1h06m") && text.contains("last 1h00m: decisions 50 · would-send 0") && text.contains("sent 5 · wins 1 · net"), "{text}");
    assert_eq!((t.net_lamports, t.net_known, t.net_src), ((4_000 - 150) - (1_000 - 50) + (2_000 - 25), true, Some("wallet records")));
    assert_eq!((t.budget_left, t.last_segment.as_deref()), (Some(1_000_000), Some("c-p2")));
    assert_eq!(t.day, format::utc_date(day));
    // the marker: one claim per day, for the day before; old markers removed
    std::fs::write(runs.join(".alerts-daily-1999-01-01"), "").unwrap();
    let now = day + summary::DAY_NS + 60_000_000_000;
    assert_eq!(summary::daily_due(&runs, now), Some((format::utc_date(day), day)));
    assert_eq!(summary::daily_due(&runs, now + 1), None, "claimed once");
    assert!(!runs.join(".alerts-daily-1999-01-01").exists());
    // the heartbeat: the first look starts the clock; due once older than its period
    assert!(!summary::heartbeat_due(&runs, 60_000_000_000, real_ns()));
    assert!(!summary::heartbeat_due(&runs, 60_000_000_000, real_ns()));
    let old = std::time::SystemTime::now() - Duration::from_secs(3_600);
    std::fs::File::options().write(true).open(runs.join(summary::HEARTBEAT_MARKER)).unwrap().set_modified(old).unwrap();
    assert!(summary::heartbeat_due(&runs, 60_000_000_000, real_ns()));
    assert!(!summary::heartbeat_due(&runs, 60_000_000_000, real_ns()), "rewritten when due");
    let _ = std::fs::remove_dir_all(&runs);
}

/// the monitor: a stale blockhash after two reads in a row (and its recovery), the failed-fee cap reached (the budget
/// floor, once), a low balance; a provider's 429 storm from the RPC registry's totals
#[test]
fn monitor_checks_the_status_line() {
    let mut m = Monitor::default();
    let ctx = Ctx { max_blockhash_age_slots: 20, ..Default::default() };
    let cfg = AlertsCfg { low_balance_sol: 0.05, ..Default::default() };
    let snap = |age: Option<u64>| Snapshot { state_ok: Some(true), blockhash_age_slots: age, tip: Some(100), ..Default::default() };
    let t0 = Instant::now();
    // no blockhash at all: no fault for a shadow run; for a segment that sends, after 2 minutes, twice in a row
    let mode = |m: &str| Ctx { max_blockhash_age_slots: 20, seg: Some(SegmentStart { mode: m.into(), ..Default::default() }), ..Default::default() };
    let mut sh = Monitor::default();
    for k in 0..20u64 { assert!(sh.check(&snap(None), &mode("shadow"), &cfg, t0 + Duration::from_secs(15 * k)).is_empty()); }
    let mut lv = Monitor::default();
    let mut said = Vec::new();
    for k in 0..12u64 { said.extend(lv.check(&snap(None), &mode("live"), &cfg, t0 + Duration::from_secs(15 * k))); }
    assert!(said.len() == 1 && said[0].title.contains("stale blockhash: none"), "{:?}", said.iter().map(|x| &x.title).collect::<Vec<_>>());
    assert!(m.check(&snap(Some(3)), &ctx, &cfg, t0).is_empty());
    assert!(m.check(&snap(Some(50)), &ctx, &cfg, t0).is_empty(), "one stale read is not enough");
    let a = m.check(&snap(Some(60)), &ctx, &cfg, t0);
    assert!(a.len() == 1 && a[0].kind == "blockhash_stale" && a[0].title.contains("60 slots old (max 20)"), "{:?}", a.iter().map(|x| &x.title).collect::<Vec<_>>());
    assert!(m.check(&snap(Some(70)), &ctx, &cfg, t0).is_empty(), "told once");
    let a = m.check(&snap(Some(2)), &ctx, &cfg, t0);
    assert!(a.len() == 1 && a[0].kind == "blockhash_fresh");
    let stopped = Snapshot { sender_stopped: Some("failed-fee cap reached".into()), failed_fees: Some(34_000_000), fee_cap: Some(34_000_000), ..Default::default() };
    let a = m.check(&stopped, &ctx, &cfg, t0);
    assert!(a.len() == 1 && a[0].level == Level::Critical && a[0].kind == "budget_floor");
    assert!(m.check(&stopped, &ctx, &cfg, t0).is_empty(), "told once");
    let canary = Snapshot { sender_stopped: Some("canary count reached".into()), sends: Some(3), ..Default::default() };
    let a = m.check(&canary, &ctx, &cfg, t0);
    assert!(a.len() == 1 && a[0].level == Level::Info && a[0].kind == "sender_stopped", "a canary's count is no budget floor");
    let poor = Snapshot { balance_lamports: Some(10_000_000), ..Default::default() };
    assert_eq!(m.check(&poor, &ctx, &cfg, t0)[0].kind, "low_balance");
    // 429s
    let tot = |n: u64| {
        let mut b = std::collections::BTreeMap::new();
        b.insert((crate::rpc::Role::Engine, "haan".to_string()), crate::rpc::Totals { rate_limited: n, ..Default::default() });
        b
    };
    assert!(m.rpc_storms(&tot(0), t0).is_empty());
    assert!(m.rpc_storms(&tot(10), t0 + Duration::from_secs(40)).is_empty(), "under the threshold");
    let a = m.rpc_storms(&tot(45), t0 + Duration::from_secs(60));
    assert!(a.len() == 1 && a[0].key == "storm:429:haan", "{:?}", a.iter().map(|x| &x.title).collect::<Vec<_>>());
}

/// 503-like failures of one stream, three within 5 minutes: a storm (deduplicated per stream); other errors do not count
#[test]
fn stream_storms_from_failed_connections() {
    let fake = Fake::start();
    let a = alerts_at(&fake.base, &on(20), Tuning { dedup: Duration::from_secs(600), ..quick() });
    a.note_stream_error("state", "status: Unavailable, message: \"503 Service Unavailable\"");
    a.note_stream_error("state", "connection reset");
    a.note_stream_error("state", "status: Unavailable");
    assert_eq!(a.status_json()["raised_total"], 0);
    a.note_stream_error("state", "status: Unavailable");
    assert_eq!(a.status_json()["raised_total"], 1);
    a.note_stream_error("state", "status: Unavailable");
    assert_eq!((a.status_json()["raised_total"].as_u64(), a.status_json()["deduped_total"].as_u64()), (Some(2), Some(1)));
    for _ in 0..3 { a.note_stream_error("tx-haan", "HTTP 429 Too Many Requests"); }
    let rt = runtime();
    a.start(rt.handle(), Arc::new(AtomicBool::new(false)));
    wait_for("the storms", 10, || { let t = fake.texts().join("\n"); t.contains("unavailable (503) storm on state") && t.contains("rate-limit (429) storm on tx-haan") });
}

/// the lifecycle messages: start (mode, gate, build, config, wallet, budget) and stop (reason, run time, numbers); a
/// stop sends what was still queued with it; a panic told by the crash alert is not told twice
#[test]
fn lifecycle_messages() {
    let s = SegmentStart { segment: "w6-p3".into(), mode: "shadow".into(), gate_mode: "shadow".into(), gate_reason: Some("mode_shadow".into()), build: "6760f10a".into(),
        config_sha: "1a2b3c4d5e6f".into(), wallet: "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS".into(), budget_left_lamports: Some(34_000_000), fee_cap_lamports: 34_000_000 };
    let t = format::compose("w6-p3", real_ns(), &[start_alert(&s)], format::MAX_TEXT).0;
    assert!(t.contains("w6-p3 started") && t.contains("gate shadow (mode_shadow)") && t.contains("FRZh…yTWS") && t.contains("budget left 0.0340 SOL"), "{t}");
    let snap = Snapshot { decisions: Some(12_345), opportunities: Some(87), would_send: Some(40), sends: Some(2), wins: Some(1), net_lamports: Some(123_000),
        gate_mode: Some("shadow".into()), ..Default::default() };
    let st = stop_alert("w6-p3", "deadline", "--minutes 60 reached", 0, None, Some(3_600), Some(&snap));
    let t = format::compose("w6-p3", real_ns(), &[st.clone()], format::MAX_TEXT).0;
    assert!(st.level == Level::Info && t.contains("w6-p3 stopped: deadline (exit 0)") && t.contains("ran 1h00m"), "{t}");
    assert!(t.contains("decisions 12,345 · opps 87 · would-send 40") && t.contains("sent 2 · wins 1 · net +0.000123 SOL"), "{t}");
    assert_eq!(stop_alert("x", "panic", "d", 30, None, None, None).level, Level::Critical);
    assert_eq!(stop_alert("x", "error", "d", 30, Some(("panic", "boom")), None, None).level, Level::Error);
    // the exit: the stop message first, then what was queued
    let fake = Fake::start();
    let dir = std::env::temp_dir().join(format!("arbx-alerts-exit-{}-{}", std::process::id(), real_ns()));
    std::fs::create_dir_all(&dir).unwrap();
    std::fs::write(dir.join("status.jsonl"), format!("{}\n", status_line(real_ns(), 3, 1, 9_000, 1_000))).unwrap();
    let (a, _) = Alerts::with(&on(20), quick(), &env_ok, &fake.base, Ctx { label: "w6-p4".into(), dir: Some(dir.clone()), started_ns: real_ns() - 125_000_000_000, ..Default::default() });
    a.raise(info("q", "queued before the stop").once());
    assert_eq!(a.exit(0, "deadline", "--minutes 1 reached", None), Some(Ok(2)));
    assert!(a.exit(0, "deadline", "again", None).is_none(), "once");
    let t = fake.texts().join("\n");
    assert!(t.find("w6-p4 stopped").unwrap() < t.find("queued before the stop").unwrap() && t.contains("ran 2m") && t.contains("sent 3"), "{t}");
    // a crash told by the hook is not repeated by the stop message
    let fake = Fake::start();
    let (a, _) = Alerts::with(&on(20), quick(), &env_ok, &fake.base, Ctx { label: "w6-p5".into(), ..Default::default() });
    a.on_panic("main", "src/engine.rs:1", "boom");
    assert_eq!(a.exit(30, "panic", "panic in thread main", None), Some(Ok(0)));
    let t = fake.texts().join("\n");
    assert!(t.contains("CRASH: w6-p5 panicked") && !t.contains("stopped: panic"), "{t}");
    let _ = std::fs::remove_dir_all(&dir);
}

/// review WP-20 #1: a crash alert the panic hook could not send (a 5xx) is put back with what was queued, and the exit
/// sends them all; a 429 on it is waited out when its `retry_after` fits the hook's bound
#[test]
fn a_crash_that_could_not_be_sent_goes_with_the_exit() {
    let fake = Fake::start();
    fake.push(Reply::Status(500, "<html>busy</html>".into()));
    let (a, _) = Alerts::with(&on(20), quick(), &env_ok, &fake.base, Ctx { label: "w6-p7".into(), ..Default::default() });
    a.raise(info("q", "queued before the crash").once());
    a.on_panic("main", "src/engine.rs:9", "boom");
    assert_eq!(fake.n(), 1, "the crash post was refused");
    assert_eq!(a.status_json()["pending_now"], 2, "the crash alert and the queued one are back for the next try");
    assert_eq!(a.exit(30, "panic", "panic in thread main", None), Some(Ok(2)));
    let t = fake.texts()[1].clone();
    assert!(t.contains("CRASH: w6-p7 panicked") && t.contains("queued before the crash") && !t.contains("stopped: panic"), "{t}");
    assert_eq!(a.status_json()["failed_total"], 0);
    // a 429 with a short retry_after: waited out within the hook's 3 s
    let fake = Fake::start();
    fake.push(Reply::Status(429, r#"{"ok":false,"error_code":429,"description":"Too Many Requests","parameters":{"retry_after":1}}"#.into()));
    let (a, _) = Alerts::with(&on(20), quick(), &env_ok, &fake.base, Ctx { label: "w6-p8".into(), ..Default::default() });
    let t0 = Instant::now();
    a.on_panic("main", "src/engine.rs:9", "boom");
    assert!(fake.n() == 2 && fake.texts()[1].contains("CRASH: w6-p8") && t0.elapsed() >= Duration::from_millis(950), "{:?}", fake.texts());
    // the exit after it: the crash alert told it, nothing is left
    assert_eq!(a.exit(30, "panic", "x", None), Some(Ok(0)), "told by the crash alert");
}

/// review WP-20 #3: `min_level` filters what the run raises, never what an operator asks to send now
#[test]
fn min_level_does_not_stop_the_operators_messages() {
    let fake = Fake::start();
    let cfg = AlertsCfg { min_level: "warning".into(), ..on(20) };
    let (a, _) = Alerts::with(&cfg, quick(), &env_ok, &fake.base, Ctx::default());
    assert!(!a.raise(info("i", "an info alert")), "under min_level");
    assert_eq!(a.status_json()["below_level_total"], 1);
    assert_eq!(a.deliver_now(vec![info("t", "alert test")], Duration::from_secs(10)), Ok(1));
    assert!(fake.texts()[0].contains("alert test"));
}

/// review WP-20 #5: an API description is redacted before it is cut, so a cut through the token leaves no piece of it
#[test]
fn a_description_is_redacted_before_it_is_cut() {
    let tok = token();
    let secret = tok.split_once(':').unwrap().1.to_string();
    let fake = Fake::start();
    for pad in [270usize, 280, 290, 295, 299] {
        fake.push(Reply::Status(401, json!({ "ok": false, "error_code": 401, "description": format!("{}{tok}{}", "x".repeat(pad), "y".repeat(40)) }).to_string()));
    }
    let rt = runtime();
    let c = telegram::client(Duration::from_secs(5), false).unwrap();
    for _ in 0..5 {
        let e = rt.block_on(telegram::post(&c, &fake.base, &tok, CHAT, "x", true)).unwrap_err();
        let text = e.text().to_string();
        for w in 0..secret.len() - 7 { assert!(!text.contains(&secret[w..w + 8]), "a piece of the token at {w}: {text}"); }
    }
}

/// `arbx notify`: the first line is the title, the rest the body, all of it escaped; nothing without the variables
#[test]
fn an_operator_note() {
    assert!(send_note(&on(20), &env_none, "x", Duration::from_secs(1)).unwrap_err().contains("not set"));
    let fake = Fake::start();
    // send_note goes to the real API base: build the same alert through a test instance at the fake server instead
    let (a, _) = Alerts::with(&on(20), quick(), &env_ok, &fake.base, Ctx { label: "note".into(), ..Default::default() });
    let n = Alert::new(Level::Info, "note", "note", "FT-001 goal: <3 h> & no drops").icon("📝").once().body(Body::new().txt("criteria: 0 core drops"));
    assert_eq!(a.deliver_now(vec![n], Duration::from_secs(10)), Ok(1));
    let t = fake.texts().join("\n");
    assert!(t.contains("📝 <b>FT-001 goal: &lt;3 h&gt; &amp; no drops</b>") && t.contains("criteria: 0 core drops"), "{t}");
}

/// the shipped configs turn the alerts on (naming the variables, never holding them) and watch /root/arbx/runs
#[test]
fn deploy_configs_turn_alerts_on() {
    for f in ["deploy/arbx-stage0.toml", "deploy/arb.toml"] {
        let c = crate::config::Config::load(&std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(f)).unwrap();
        let a = &c.alerts;
        assert!(a.enabled, "{f}");
        assert_eq!((a.token_env.as_str(), a.chat_env.as_str(), a.rate_per_min, a.dedup_s, a.heartbeat_min, a.min_level.as_str()),
            ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", 20, 600, 60, "info"), "{f}");
        assert_eq!((c.watchdog.dir(&c.out_dir), c.watchdog.grace_s, c.watchdog.status_min), (PathBuf::from("/root/arbx/runs"), 120, 60), "{f}");
        // what meta.json and the normalized hash hold of it: the names
        let sec = crate::provenance::section(a);
        assert_eq!((sec["token_env"].as_str(), sec["chat_env"].as_str()), (Some("TELEGRAM_BOT_TOKEN"), Some("TELEGRAM_CHAT_ID")));
    }
}

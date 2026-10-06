//! rpc.rs tests (WP-03b; PLAN-ADDENDUM I-1): fake JSON-RPC providers over real HTTP that answer as scripted (a result,
//! a JSON-RPC error, HTTP 429, a reply cut in the middle of its body, no answer), the boot policy, the bounded call's
//! classification and failover, the per-(role, provider) stats, the token buckets and the DNS cache.
use super::*;
use std::sync::atomic::AtomicU64;
use tokio::io::{AsyncReadExt, AsyncWriteExt};

/// What a fake provider does with one request
#[derive(Clone)]
pub(crate) enum Reply {
    /// a whole JSON-RPC reply body (HTTP 200)
    Body(Value),
    /// an HTTP status with an empty body
    Status(u16),
    /// HTTP 200 announcing 4,000 bytes and closing after 20 (the reply is cut while it is read: a body error)
    Truncated,
    /// no answer for this long, then the connection closes
    Hang(Duration),
}

pub(crate) fn ok(result: Value) -> Reply { Reply::Body(json!({ "jsonrpc": "2.0", "id": 1, "result": result })) }
pub(crate) fn rpc_err(code: i64, msg: &str) -> Reply { Reply::Body(json!({ "jsonrpc": "2.0", "id": 1, "error": { "code": code, "message": msg } })) }

/// A fake provider on 127.0.0.1: every request (its JSON body, and how many came before it) goes to `f`; one request per
/// connection (`connection: close`). Returns its URL and the number of requests served
pub(crate) async fn fake_http(f: impl Fn(&Value, u64) -> Reply + Send + Sync + 'static) -> (String, Arc<AtomicU64>) {
    let l = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = l.local_addr().unwrap();
    let (f, n) = (Arc::new(f), Arc::new(AtomicU64::new(0)));
    let n2 = n.clone();
    tokio::spawn(async move {
        loop {
            let Ok((mut s, _)) = l.accept().await else { return };
            let (f, n) = (f.clone(), n2.clone());
            tokio::spawn(async move {
                let mut buf = Vec::new();
                let mut chunk = [0u8; 16_384];
                let req = loop {
                    let Ok(k) = s.read(&mut chunk).await else { return };
                    if k == 0 { return; }
                    buf.extend_from_slice(&chunk[..k]);
                    let Some(end) = buf.windows(4).position(|w| w == b"\r\n\r\n") else { continue };
                    let head = String::from_utf8_lossy(&buf[..end]).to_ascii_lowercase();
                    let len: usize = head.lines().find_map(|l| l.strip_prefix("content-length:").map(|v| v.trim().parse().unwrap())).unwrap_or(0);
                    if buf.len() < end + 4 + len { continue; }
                    break serde_json::from_slice::<Value>(&buf[end + 4..end + 4 + len]).unwrap_or(Value::Null);
                };
                let k = n.fetch_add(1, Relaxed);
                match f(&req, k) {
                    Reply::Body(v) => {
                        let body = v.to_string();
                        let _ = s.write_all(format!("HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\nconnection: close\r\n\r\n{body}", body.len()).as_bytes()).await;
                    }
                    Reply::Status(code) => { let _ = s.write_all(format!("HTTP/1.1 {code} X\r\ncontent-length: 0\r\nconnection: close\r\n\r\n").as_bytes()).await; }
                    Reply::Truncated => {
                        let _ = s.write_all(b"HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: 4000\r\nconnection: close\r\n\r\n{\"jsonrpc\":\"2.0\",\"res").await;
                        let _ = s.flush().await;
                    }
                    Reply::Hang(d) => { tokio::time::sleep(d).await; }
                }
                let _ = s.shutdown().await;
            });
        }
    });
    (format!("http://{addr}"), n)
}

fn ep(name: &str, url: &str) -> Endpoint { Endpoint { name: name.into(), url: url.into(), bearer: None } }

/// a getMultipleAccounts result for the request's keys (every account present, its data = its index)
fn gma(req: &Value) -> Value {
    let keys = req["params"][0].as_array().map(|a| a.len()).unwrap_or(0);
    let owner = b58(&[7u8; 32]);
    json!({ "context": { "slot": 777 }, "value": (0..keys).map(|i| json!({ "lamports": 1_000 + i, "owner": owner,
        "data": [base64::engine::general_purpose::STANDARD.encode([i as u8; 4]), "base64"], "executable": false, "rentEpoch": 0 })).collect::<Vec<_>>() })
}

fn rec_in(tag: &str) -> (crate::rec::Rec, std::path::PathBuf) {
    let dir = std::env::temp_dir().join(format!("arbx-rpc-{tag}-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
    let rec = crate::rec::start(crate::rec::Opts { dir: dir.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
        echo: Some(Box::new(std::io::sink())) }).unwrap();
    (rec, dir)
}

/// PLAN-ADDENDUM I-1 (the cmp2 crash): at boot, Haan answers 429 and the failover to Shyft gets a reply cut while it is
/// read ("error decoding response body"). Under the boot policy the snapshot retries with backoff across both and
/// completes; every failure is classified and counted per (role, provider), and the retries are events. A client made
/// with `only` (as `Exec::new` makes its own) follows the same policy
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn boot_snapshot_survives_a_429_then_a_body_error() {
    let (haan, haan_n) = fake_http(|req, k| if k == 1 { Reply::Status(429) } else { ok(gma(req)) }).await;
    let (shyft, shyft_n) = fake_http(|req, k| if k == 0 { Reply::Truncated } else { ok(gma(req)) }).await;
    let reg = Arc::new(Registry::default());
    let (rec, dir) = rec_in("boot");
    reg.set_sink(rec.clone());
    let rpc = Rpc::race(vec![ep("haan", &haan), ep("shyft", &shyft)]).with_failover(true).with_registry(reg.clone()).with_role(Role::Boot);
    rpc.set_phase(Phase::Boot);
    rpc.set_boot_budget(Duration::from_secs(20));
    // 150 accounts: two getMultipleAccounts. The first goes to Haan (ok); the second meets Haan's 429, then Shyft's cut
    // reply, then (after the backoff and Haan's cool-down) Haan again
    let keys: Vec<Pk> = (0..150u32).map(|i| { let mut k = [0u8; 32]; k[..4].copy_from_slice(&i.to_le_bytes()); k }).collect();
    let t0 = Instant::now();
    let (slot, accts) = rpc.accounts(&keys).await.expect("the boot retries until it succeeds");
    assert_eq!((slot, accts.len()), (777, 150));
    assert!(accts.iter().all(|a| a.is_some()));
    assert_eq!(accts[149].as_ref().unwrap().data, vec![49u8; 4], "the second chunk's 50th account");
    assert!(t0.elapsed() < Duration::from_secs(5), "{:?}", t0.elapsed());
    assert_eq!((haan_n.load(Relaxed), shyft_n.load(Relaxed)), (3, 1));
    let (h, s) = (reg.total(Role::Boot, "haan"), reg.total(Role::Boot, "shyft"));
    assert_eq!((h.calls, h.ok, h.rate_limited), (3, 2, 1));
    assert_eq!((s.calls, s.body, s.errors), (1, 1, 1));
    // the executor's client (`only`) shares the phase: it retries too (Shyft's next answer is good)
    let ex = rpc.only(&["shyft".to_string()]);
    assert_eq!(ex.role(), Role::Exec);
    assert_eq!(ex.accounts(&keys[..3]).await.unwrap().1.len(), 3);
    // after the boot, a plain call is the configured one (no retry round)
    rpc.set_phase(Phase::Run);
    assert_eq!(ex.phase(), Phase::Run, "shared");
    rec.close();
    let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
    let retries: Vec<&Value> = ev.iter().filter(|e| e["kind"] == "rpc_boot_retry").collect();
    assert!(!retries.is_empty());
    assert_eq!((retries[0]["detail"]["provider"].as_str(), retries[0]["detail"]["class"].as_str()), (Some("haan"), Some("rate_limited")));
    let _ = std::fs::remove_dir_all(&dir);
}

/// I-1: only a sustained failure aborts the boot: when every provider keeps failing for the whole budget, the error
/// (stop.json's detail) says so, names each provider's failure classes, and an `rpc_boot_failed` event is written
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_sustained_boot_failure_aborts_with_its_reason() {
    let (haan, _) = fake_http(|_, _| Reply::Status(429)).await;
    let (shyft, _) = fake_http(|_, _| Reply::Truncated).await;
    let reg = Arc::new(Registry::default());
    let (rec, dir) = rec_in("sustained");
    reg.set_sink(rec.clone());
    let rpc = Rpc::race(vec![ep("haan", &haan), ep("shyft", &shyft)]).with_failover(true).with_registry(reg.clone()).with_role(Role::Boot);
    rpc.set_phase(Phase::Boot);
    rpc.set_boot_budget(Duration::from_millis(1_500));
    let t0 = Instant::now();
    let e = rpc.accounts(&[[1u8; 32]]).await.unwrap_err();
    let el = t0.elapsed();
    assert!(el >= Duration::from_millis(1_400) && el < Duration::from_secs(4), "{el:?}");
    let msg = format!("{e:#}");
    assert!(msg.contains("getMultipleAccounts: sustained RPC failure"), "{msg}");
    assert!(msg.contains("haan rate_limited x") && msg.contains("shyft body x"), "{msg}");
    let f = e.downcast_ref::<RpcFailure>().expect("the classified failure");
    assert!(f.attempts >= 3, "{}", f.attempts);
    rec.close();
    let ev = crate::rec::read_jsonl(&dir, "events").unwrap();
    let failed = ev.iter().find(|e| e["kind"] == "rpc_boot_failed").expect("rpc_boot_failed");
    assert_eq!(failed["detail"]["method"].as_str(), Some("getMultipleAccounts"));
    // a stop during the boot ends the retries at once
    rpc.set_boot_budget(Duration::from_secs(30));
    rpc.set_stop(Arc::new(AtomicBool::new(true)));
    let t0 = Instant::now();
    let e = rpc.accounts(&[[1u8; 32]]).await.unwrap_err();
    assert!(t0.elapsed() < Duration::from_secs(1));
    assert_eq!(e.downcast_ref::<RpcFailure>().unwrap().class, ErrClass::Stopped);
    let _ = std::fs::remove_dir_all(&dir);
}

/// FT-001 p1: the run's stop flag (`set_stop`, the stopper's) ends boot-policy calls only. Set by the stop request,
/// before the stop sequence, it had made every bounded call fail at once ("rpc getMultipleAccounts: no attempt before the
/// deadline", no provider asked): the ledger's stop snapshot, its window search, the executor's expiry checks. A bounded
/// call after the stop request asks its providers (and fails over) as before; a boot call still ends at once, unasked
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn the_run_stop_ends_boot_calls_only() {
    let (down, nd) = fake_http(|_, _| Reply::Status(503)).await;
    let (up, nu) = fake_http(|req, _| ok(gma(req))).await;
    let reg = Arc::new(Registry::default());
    let root = Rpc::race(vec![ep("down", &down), ep("up", &up)]).with_failover(true).with_registry(reg.clone());
    root.set_stop(Arc::new(AtomicBool::new(true)));
    let ledger = root.with_role(Role::Ledger);
    let f = ledger.call_bounded("getMultipleAccounts", json!([[b58(&[1u8; 32])], { "encoding": "base64" }]), Bounds::fetch(Duration::from_secs(5), 2)).await
        .expect("a bounded call after the stop request asks its providers");
    assert_eq!((f.provider.as_str(), f.attempts, f.value["context"]["slot"].as_u64()), ("up", 2, Some(777)), "the first failed, the call failed over");
    assert_eq!((nd.load(Relaxed), nu.load(Relaxed)), (1, 1));
    assert_eq!((reg.total(Role::Ledger, "down").errors, reg.total(Role::Ledger, "up").ok), (1, 1));
    // a boot call: the stop ends it at once, no provider asked
    root.set_phase(Phase::Boot);
    let e = root.accounts(&[[1u8; 32]]).await.unwrap_err();
    let f = e.downcast_ref::<RpcFailure>().unwrap();
    assert_eq!((f.class, f.attempts), (ErrClass::Stopped, 0), "{f:?}");
    assert!(f.msg.contains("the run is stopping"), "{}", f.msg);
    assert_eq!((nd.load(Relaxed), nu.load(Relaxed)), (1, 1), "nothing sent");
}

/// WP-03b item 5: `call_bounded` classifies every failure, moves to the next provider at once after a retryable one,
/// returns a JSON-RPC answer (a skipped slot) at once, and respects its retries; the per-(role, provider) stats
/// (resources.jsonl `rpc`, status `chainfetch.by_role`) count calls, 429s, timeouts and body errors, as deltas per
/// consumer
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn bounded_calls_classify_fail_over_and_are_counted_per_role() {
    let (a, _) = fake_http(|req, _| match req["method"].as_str() {
        Some("getBlock") => rpc_err(-32009, "Slot 453034309 was skipped, or missing in long-term storage"),
        Some("getSlot") => Reply::Status(429),
        _ => Reply::Hang(Duration::from_secs(3)),
    }).await;
    let (b, _) = fake_http(|req, _| match req["method"].as_str() {
        Some("getSlot") => ok(json!(42)),
        Some("getTransaction") => Reply::Truncated,
        _ => rpc_err(-32603, "internal"),
    }).await;
    let reg = Arc::new(Registry::default());
    let root = Rpc::race(vec![ep("a", &a), ep("b", &b)]).with_failover(true).with_registry(reg.clone());
    let slotidx = root.only_role(Role::Slotidx, &["a".to_string(), "b".to_string()]);
    // a skipped slot is an answer: returned at once, from the first provider, not retried
    let e = slotidx.call_bounded("getBlock", json!([453034309]), Bounds::fetch(Duration::from_secs(2), 3)).await.unwrap_err();
    assert_eq!((e.class, e.code, e.provider.as_deref(), e.attempts, e.retryable), (ErrClass::Rpc, Some(-32009), Some("a"), 1, false));
    // a timeout on one and a cut reply on the other (each asked once in the round), until the retries run out
    let w = root.with_role(Role::Wallet);
    let t0 = Instant::now();
    let e = w.call_bounded("getTransaction", json!(["x"]), Bounds { deadline: Duration::from_secs(3), retries: 1, attempt_timeout: Duration::from_millis(300),
        backoff_first: Duration::from_millis(50), backoff_max: Duration::from_millis(50) }).await.unwrap_err();
    assert!(t0.elapsed() < Duration::from_secs(2), "{:?}", t0.elapsed());
    assert_eq!((e.class, e.attempts), (ErrClass::Body, 2), "{}", e.msg);
    assert!(e.msg.contains("a timeout x1") && e.msg.contains("b body x1"), "{}", e.msg);
    // a 429 moves to the next provider at once
    let bf = root.with_role(Role::Backfill);
    let f = bf.call_bounded("getSlot", json!([]), Bounds::fetch(Duration::from_secs(2), 2)).await.unwrap();
    assert_eq!((f.value.as_u64(), f.provider.as_str(), f.attempts), (Some(42), "b", 2));
    // a provider cooling down after its 429 is passed over while another is ready: the next call starts at b
    let f = bf.call_bounded("getSlot", json!([]), Bounds::fetch(Duration::from_secs(2), 2)).await.unwrap();
    assert_eq!((f.provider.as_str(), f.attempts), ("b", 1));
    // the stats, per (role, provider)
    assert_eq!(reg.total(Role::Slotidx, "a").rpc, 1);
    let (ba, bb) = (reg.total(Role::Backfill, "a"), reg.total(Role::Backfill, "b"));
    assert_eq!((ba.calls, ba.rate_limited, bb.ok), (1, 1, 2));
    let (wa, wb) = (reg.total(Role::Wallet, "a"), reg.total(Role::Wallet, "b"));
    assert_eq!((wa.timeouts, wb.body), (1, 1));
    let r = reg.resources_json();
    assert_eq!(r["backfill/a"]["rate_limited_delta"], 1);
    assert_eq!(r["wallet/a"]["timeouts_delta"], 1);
    assert_eq!(r["wallet/b"]["body_errors_delta"], 1);
    assert!(r["backfill/b"]["p50_ms"].as_f64().is_some(), "{r}");
    assert_eq!(reg.resources_json(), json!({}), "deltas: nothing new since the last line");
    let by = reg.by_role_json("status");
    assert_eq!((by["backfill"]["calls_delta"].as_u64(), by["backfill"]["rate_limited_delta"].as_u64(), by["wallet"]["errors_delta"].as_u64()), (Some(3), Some(1), Some(2)));
    assert_eq!(reg.by_role_json("status"), json!({}), "each consumer has its own deltas");
}

/// A plain call outside the boot keeps its configured behaviour (failover: the next provider after a 429), now counted
/// in the registry under the client's role
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_plain_call_fails_over_and_is_counted() {
    let (a, an) = fake_http(|_, _| Reply::Status(429)).await;
    let (b, _) = fake_http(|_, _| ok(json!(5))).await;
    let reg = Arc::new(Registry::default());
    let rpc = Rpc::race(vec![ep("a", &a), ep("b", &b)]).with_failover(true).with_registry(reg.clone()).with_role(Role::Engine);
    assert_eq!(rpc.slot().await.unwrap(), 5);
    assert_eq!(an.load(Relaxed), 1, "the first provider is not retried: the next is asked");
    assert_eq!((reg.total(Role::Engine, "a").rate_limited, reg.total(Role::Engine, "b").ok), (1, 1));
    assert!(rpc.summary()[1].contains("b: first 1/1"), "{:?}", rpc.summary());
    // the first provider cools down after its 429: the next call goes straight to the second
    assert_eq!(rpc.slot().await.unwrap(), 5);
    assert_eq!(an.load(Relaxed), 1, "passed over while cooling");
    let lines = reg.summary_lines();
    assert!(lines.iter().any(|l| l.starts_with("engine/a: 1 calls, 0 ok, 1 rate_limited")), "{lines:?}");
    assert!(lines.iter().any(|l| l.starts_with("engine/b: 2 calls, 2 ok")), "{lines:?}");
}

/// The token bucket: critical roles may take the last token, normal ones keep a quarter of the burst, background ones
/// half; the rate refills it; a 429 drains it and cools the provider down, doubling while 429s follow
#[tokio::test(start_paused = true)]
async fn token_buckets_keep_a_reserve_for_critical_roles() {
    let l = Limiter::new(4.0, 4.0);
    let now = Instant::now();
    let takes = |prio: u8| (0..10).filter(|_| l.try_take(prio, now).is_ok()).count();
    assert_eq!(takes(2), 2, "background: only while 3 tokens are there (4 -> 2 left)");
    assert_eq!(takes(1), 1, "normal needs 2: one");
    assert_eq!(takes(0), 1, "critical takes the last one");
    // 1 s later: 4 more tokens (the burst)
    tokio::time::advance(Duration::from_secs(1)).await;
    let t = Instant::now();
    assert!(l.wait_hint(0, t).is_zero());
    assert_eq!((0..10).filter(|_| l.try_take(0, t).is_ok()).count(), 4);
    // the rate over 10 s: about 4 a second for one caller that waits
    let t0 = Instant::now();
    let mut n = 0;
    while t0.elapsed() < Duration::from_secs(10) { l.take(2, None).await.unwrap(); n += 1; }
    assert!((38..=42).contains(&n), "{n}");
    // a 429: drained and cooling for 250 ms, then 500 ms after a second one
    let now = Instant::now();
    l.on_rate_limited(now);
    assert_eq!(l.cooling(now), Duration::from_millis(250));
    assert!(l.try_take(0, now).is_err());
    l.on_rate_limited(now);
    assert_eq!(l.cooling(now), Duration::from_millis(500));
    l.on_ok();
    l.on_rate_limited(now);
    assert_eq!(l.cooling(now), Duration::from_millis(250), "the streak restarts after an answer");
    // review WP-03b #19: no tokens accrue while it cools: at the cool-down's end the bucket is still empty, a token
    // comes a quarter of a second later (at 4/s), not the whole burst at once
    tokio::time::advance(Duration::from_millis(250)).await;
    assert!(l.try_take(0, Instant::now()).is_err(), "empty when the cool-down ends");
    tokio::time::advance(Duration::from_millis(250)).await;
    assert!(l.try_take(0, Instant::now()).is_ok());
    assert!(l.try_take(0, Instant::now()).is_err(), "one token, not a burst");
    // a deadline before the next token fails the wait
    assert!(l.take(0, Some(Instant::now() + Duration::from_millis(10))).await.is_err());
    // no limit
    let u = Limiter::unlimited();
    assert!((0..1_000).all(|_| u.try_take(2, Instant::now()).is_ok()));
}

/// DNS (addendum: Haan's cold connect spent 35 of 53 ms on DNS): a provider's host is resolved once, and every new
/// connection after that is served from the cache, with no lookup
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn hosts_are_resolved_once_and_connections_reuse_the_cache() {
    let (url, n) = fake_http(|_, _| ok(json!(1))).await;
    let url = url.replace("127.0.0.1", "localhost");
    let rpc = Rpc::race(vec![ep("p", &url)]).with_registry(Arc::new(Registry::default()));
    let notes = rpc.prewarm().await;
    assert!(notes[0].starts_with("rpc p: DNS ") && notes[0].contains("first call"), "{notes:?}");
    assert_eq!(rpc.dns().lookups(), 1);
    assert!(rpc.dns().cached("localhost").is_some_and(|a| !a.is_empty()));
    // the fake closes every connection: each call connects again, from the cache
    for _ in 0..3 { assert_eq!(rpc.slot().await.unwrap(), 1); }
    assert_eq!(rpc.dns().lookups(), 1, "no new lookup");
    assert!(rpc.dns().hits() >= 4, "{}", rpc.dns().hits());
    assert_eq!(n.load(Relaxed), 4);
    rpc.dns().refresh().await;
    assert_eq!(rpc.dns().lookups(), 2, "a refresh is one lookup per host, off the request path");
}

/// The config: every [rpc] provider's bucket ([[chainfetch.provider]] max_rps, else default_max_rps) and each
/// chain-fetch role's providers (the entries naming it, in order; a role no entry names: every provider)
#[test]
fn budgets_and_roles_from_the_config() {
    let text = "config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"w\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n[[rpc.endpoint]]\nname = \"haan\"\nurl = \"http://h\"\n\
        [[rpc.endpoint]]\nname = \"shyft\"\nurl = \"http://s\"\n[[rpc.endpoint]]\nname = \"public\"\nurl = \"http://p\"\n[state]\nurl = \"http://localhost\"\n\
        [chainfetch]\ndefault_max_rps = 2\n[[chainfetch.provider]]\nname = \"haan\"\nroles = [\"wallet\", \"backfill\"]\nmax_rps = 4\n\
        [[chainfetch.provider]]\nname = \"shyft\"\nroles = [\"slotidx\", \"backfill\"]\nmax_rps = 0\n";
    let cfg = crate::config::Config::parse(text).unwrap();
    let cf = &cfg.chainfetch;
    assert_eq!((cf.limit_of("haan"), cf.limit_of("shyft"), cf.limit_of("public")), ((4.0, None), (0.0, None), (2.0, None)));
    let all: Vec<String> = ["haan", "shyft", "public"].map(String::from).to_vec();
    assert_eq!(cf.providers_for("backfill", &all), ["haan", "shyft"]);
    assert_eq!(cf.providers_for("slotidx", &all), ["shyft"]);
    assert_eq!(cf.providers_for("sample", &all), all, "a role no entry names: every provider");
    // meta.json `rpc[]`: the chain-fetch roles and the budget of each provider (null: no limit)
    let m = crate::provenance::rpc_json(&cfg);
    let row = |n: &str| m.as_array().unwrap().iter().find(|r| r["name"] == n).unwrap().clone();
    assert_eq!((row("haan")["roles"].clone(), row("haan")["max_rps"].as_f64()), (json!(["boot", "wallet", "blockhash", "backfill", "sample"]), Some(4.0)));
    assert_eq!((row("shyft")["roles"].clone(), row("shyft")["max_rps"].clone()), (json!(["boot", "blockhash", "backfill", "slotidx", "sample"]), Value::Null));
    assert_eq!((row("public")["roles"].clone(), row("public")["max_rps"].as_f64()), (json!(["boot", "blockhash", "sample"]), Some(2.0)));
    let reg = Registry::default();
    for n in &all { let (r, b) = cf.limit_of(n); reg.set_limit(n, r, b); }
    assert_eq!(reg.limits_json(), json!({ "haan": { "max_rps": 4.0, "burst": 4.0 }, "public": { "max_rps": 2.0, "burst": 2.0 }, "shyft": { "max_rps": null, "burst": null } }));
    // an unknown provider, an unknown role, a bad rate: load errors
    let base = text.split("[chainfetch]").next().unwrap();
    for (bad, why) in [("[[chainfetch.provider]]\nname = \"nope\"\n", "no [[rpc.endpoint]]"), ("[[chainfetch.provider]]\nname = \"public\"\nroles = [\"exec\"]\n", "not a chain-fetch role"),
        ("[chainfetch]\nrps = \"fast\"\n", "rps must be"), ("[chainfetch]\nrps = 0\n", "rps must be > 0"), ("[chainfetch]\nmax_tx_version = 2\n", "max_tx_version"),
        ("[chainfetch]\nblockhash_poll_ms = 50\n", "blockhash_poll_ms"), ("[chainfetch]\nafter_ms = 0\n", "after_ms"), ("[chainfetch]\nboot_retry_s = 0\n", "boot_retry_s"),
        ("[chainfetch]\nafter = 1\n", "unknown field `after`")] {
        let e = crate::config::Config::parse(&format!("{base}{bad}")).map(|_| ()).unwrap_err().to_string();
        assert!(e.contains(why), "{why}: {e}");
    }
    let d = crate::config::Config::parse(base).unwrap().chainfetch;
    assert_eq!((d.enabled, d.after_ms, d.rps.fixed(), d.max_backlog, d.sample_every_s, d.blockhash_poll_ms, d.sigs_every_s, d.default_max_rps, d.boot_retry_s, d.max_tx_version),
        (true, 1_500, None, 200_000, 60, 400, 3_600, 0.0, 90, 1), "the plan's defaults (no bucket for a provider no entry names: review WP-03b #18)");
    assert_eq!(crate::config::Config::parse(&format!("{base}[chainfetch]\nrps = 12.5\n")).unwrap().chainfetch.rps.fixed(), Some(12.5));
    // the maintained configs: the plan's keys, Haan and Shyft at 4 requests/s each (Haan answered 429 at about 5/s), no
    // bucket for the others, the slot index on Shyft, the blockhash poll on Haan, the backfill on both
    for f in ["deploy/arbx-stage0.toml", "deploy/arb.toml"] {
        let c = crate::config::Config::load(&std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join(f)).unwrap();
        let cf = &c.chainfetch;
        assert!(cf.enabled && cf.rps.fixed().is_none(), "{f}");
        assert_eq!((cf.after_ms, cf.max_backlog, cf.sample_every_s, cf.blockhash_poll_ms, cf.sigs_every_s, cf.boot_retry_s, cf.max_tx_version), (1_500, 200_000, 60, 400, 3_600, 90, 1), "{f}");
        assert_eq!((cf.limit_of("haan").0, cf.limit_of("shyft").0, cf.default_max_rps), (4.0, 4.0, 0.0), "{f}");
        let all: Vec<String> = ["haan", "shyft"].map(String::from).to_vec();
        assert_eq!((cf.providers_for("slotidx", &all), cf.providers_for("blockhash", &all), cf.providers_for("backfill", &all)),
            (vec!["shyft".to_string()], vec!["haan".to_string()], all.clone()), "{f}");
    }
}

/// review WP-03b #1: callers that wait are served by priority, then in order. With the bucket empty, three bulk callers
/// (the backfill) queue, then an index caller (the slot index) arrives: it takes the next token, then the bulk ones in
/// their order; a newcomer of the same priority goes behind those waiting
#[tokio::test(start_paused = true)]
async fn the_bucket_queue_serves_by_priority_then_in_order() {
    let l = Arc::new(Limiter::new(4.0, 4.0));
    while l.try_take(0, Instant::now()).is_ok() {}
    let order = Arc::new(Mutex::new(Vec::new()));
    let mut hs = Vec::new();
    for (i, prio) in [(1, Role::Backfill.priority()), (2, Role::Backfill.priority()), (3, Role::Backfill.priority()), (4, Role::Slotidx.priority())] {
        let (l, order) = (l.clone(), order.clone());
        hs.push(tokio::spawn(async move { let w = l.take(prio, None).await.unwrap(); order.lock().unwrap().push((i, w.as_millis() as u64)); }));
        tokio::time::sleep(Duration::from_millis(1)).await;
    }
    assert_eq!(l.queued(), 4);
    assert!(l.wait_hint(Role::Backfill.priority(), Instant::now()) >= Duration::from_millis(1_700), "a newcomer goes behind the four waiting");
    for h in hs { h.await.unwrap(); }
    let got = order.lock().unwrap().clone();
    assert_eq!(got.iter().map(|x| x.0).collect::<Vec<_>>(), vec![4, 1, 2, 3], "{got:?}");
    // index and bulk keep half the burst: the first token at 3 in the bucket (0.75 s), then one every 0.25 s
    assert!(got[0].1 >= 740 && got[0].1 <= 760, "{got:?}");
    assert_eq!(l.queued(), 0);
}

/// review WP-03b #1 (probe P1 at the client level): the slot index and the backfill share a provider's 4/s bucket, as
/// they share Shyft in the deploy split. Sixteen backfill callers keep it busy with bounded calls; the slot index asks
/// for one block every 270 ms (3.7/s). Its callers queue ahead of the backfill's: every one of its calls is served, none
/// is refused, and the backfill gets what is left. Before the fix the slot index got 0.12 calls/s
#[tokio::test(flavor = "multi_thread", worker_threads = 4)]
async fn the_slot_index_goes_before_the_backfill_on_a_shared_bucket() {
    let (url, served) = fake_http(|req, _| match req["method"].as_str() { Some("getBlock") => ok(json!({ "signatures": [] })), _ => ok(Value::Null) }).await;
    let reg = Arc::new(Registry::default());
    reg.set_limit("shyft", 4.0, None);
    let root = Rpc::race(vec![ep("shyft", &url)]).with_failover(true).with_registry(reg.clone());
    let (si, bf) = (root.only_role(Role::Slotidx, &["shyft".to_string()]), root.only_role(Role::Backfill, &["shyft".to_string()]));
    let stop = Arc::new(AtomicBool::new(false));
    let t_start = Instant::now();
    let workers: Vec<_> = (0..16).map(|_| {
        let (bf, stop) = (bf.clone(), stop.clone());
        tokio::spawn(async move { while !stop.load(Relaxed) { let _ = bf.call_bounded("getTransaction", json!(["x"]), Bounds::fetch(Duration::from_secs(2), 1)).await; } })
    }).collect();
    tokio::time::sleep(Duration::from_millis(500)).await;
    let t0 = Instant::now();
    let mut asks = Vec::new();
    for _ in 0..22 {
        let si = si.clone();
        asks.push(tokio::spawn(async move { si.call_bounded("getBlock", json!([1, { "transactionDetails": "signatures" }]), Bounds::fetch(Duration::from_secs(5), 1)).await.is_ok() }));
        tokio::time::sleep(Duration::from_millis(270)).await;
    }
    let mut ok = 0;
    for a in asks { if a.await.unwrap() { ok += 1; } }
    stop.store(true, Relaxed);
    for w in workers { w.await.unwrap(); }
    let el = t_start.elapsed().as_secs_f64();
    let _ = t0;
    assert_eq!(ok, 22, "every slot-index call served");
    let (s, b) = (reg.total(Role::Slotidx, "shyft"), reg.total(Role::Backfill, "shyft"));
    assert_eq!((s.calls, s.ok, s.budget), (22, 22, 0), "{s:?}");
    assert!(b.ok >= 1 && b.budget > 0, "the backfill had demand and got the rest: {b:?}");
    // the bucket as a whole stayed within its rate (4/s, and the burst of 4 at the start), from the first backfill call
    // to the last (queued ones finish after the stop)
    let total = served.load(Relaxed) as f64;
    assert!(total <= 4.0 * el + 4.0 + 1.0, "{total} requests in {el:.1} s");
}

/// review WP-03b #4 (probe P4): at boot, an error answer from the first provider (a gateway message without a code, a
/// method its plan lacks, its own parameter limit) is that provider's: the next one is asked and the boot goes on (it
/// failed at once before). The same refusal from every provider ends the boot at once, saying so; a chain fact (a
/// skipped slot) still ends a bounded call at once
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn boot_asks_every_provider_before_an_error_answer_aborts_it() {
    for err in [json!({ "message": "upstream connect error" }), json!({ "code": -32601, "message": "Method not found" }),
        json!({ "code": -32602, "message": "Invalid params: too many accounts" })] {
        let e2 = err.clone();
        let (a, an) = fake_http(move |_, _| Reply::Body(json!({ "jsonrpc": "2.0", "id": 1, "error": e2 }))).await;
        let (b, bn) = fake_http(|req, _| ok(gma(req))).await;
        let reg = Arc::new(Registry::default());
        let rpc = Rpc::race(vec![ep("a", &a), ep("b", &b)]).with_failover(true).with_registry(reg.clone()).with_role(Role::Boot);
        rpc.set_phase(Phase::Boot);
        rpc.set_boot_budget(Duration::from_secs(20));
        let t0 = Instant::now();
        let (_, accts) = rpc.accounts(&[[1u8; 32]]).await.unwrap_or_else(|e| panic!("{err}: {e:#}"));
        assert!(t0.elapsed() < Duration::from_secs(2), "{err}");
        assert_eq!((an.load(Relaxed), bn.load(Relaxed), accts.len()), (1, 1, 1), "{err}");
    }
    let (a, an) = fake_http(|_, _| rpc_err(-32602, "Invalid params")).await;
    let (b, bn) = fake_http(|_, _| rpc_err(-32602, "Invalid params: too large")).await;
    let rpc = Rpc::race(vec![ep("a", &a), ep("b", &b)]).with_failover(true).with_registry(Arc::new(Registry::default())).with_role(Role::Boot);
    rpc.set_phase(Phase::Boot);
    rpc.set_boot_budget(Duration::from_secs(20));
    let t0 = Instant::now();
    let e = rpc.accounts(&[[1u8; 32]]).await.unwrap_err();
    assert!(t0.elapsed() < Duration::from_secs(2), "{:?}", t0.elapsed());
    assert_eq!((an.load(Relaxed), bn.load(Relaxed)), (1, 1), "each asked once");
    let f = e.downcast_ref::<RpcFailure>().unwrap();
    assert_eq!((f.class, f.code, f.attempts, f.retryable), (ErrClass::Rpc, Some(-32602), 2, false));
    assert!(format!("{e:#}").contains("sustained RPC failure") && format!("{e:#}").contains("every provider refused the request"), "{e:#}");
    // a skipped slot: a fact of the chain, final at once (the second provider is not asked)
    let (c, cn) = fake_http(|_, _| rpc_err(-32007, "Slot 1 was skipped")).await;
    let (d, dn) = fake_http(|_, _| ok(json!({}))).await;
    let rpc = Rpc::race(vec![ep("c", &c), ep("d", &d)]).with_failover(true).with_registry(Arc::new(Registry::default())).with_role(Role::Slotidx);
    let e = rpc.call_bounded("getBlock", json!([1]), Bounds::fetch(Duration::from_secs(2), 3)).await.unwrap_err();
    assert_eq!((e.code, cn.load(Relaxed), dn.load(Relaxed)), (Some(-32007), 1, 0));
}

/// review WP-03b #7, #8 (probe P7): a token granted at once is no wait (`throttled` 0); a call refused for want of a
/// token sent nothing: it is a `rate_budget`, not a call or an error (resources.jsonl `calls_delta` counts requests)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn refusals_are_not_calls_and_immediate_tokens_are_not_waits() {
    let (c, n) = fake_http(|_, _| ok(json!(5))).await;
    let reg = Arc::new(Registry::default());
    reg.set_limit("c", 0.1, Some(1.0));
    let rpc = Rpc::race(vec![ep("c", &c)]).with_failover(true).with_registry(reg.clone()).with_role(Role::Backfill);
    let mut ok = 0;
    for _ in 0..3 { if rpc.call_bounded("getSlot", json!([]), Bounds::fetch(Duration::from_millis(200), 0)).await.is_ok() { ok += 1; } }
    assert_eq!((ok, n.load(Relaxed)), (1, 1));
    let t = reg.total(Role::Backfill, "c");
    assert_eq!((t.calls, t.ok, t.errors, t.budget, t.throttled), (1, 1, 0, 2, 0), "{t:?}");
    let r = reg.resources_json();
    assert_eq!((r["backfill/c"]["calls_delta"].as_u64(), r["backfill/c"]["rate_budget_delta"].as_u64(), r["backfill/c"]["throttled_delta"].as_u64()),
        (Some(1), Some(2), Some(0)), "{r}");
    let by = reg.by_role_json("status");
    assert_eq!(by["backfill"], json!({ "calls_delta": 1, "errors_delta": 0, "rate_limited_delta": 0, "rate_budget_delta": 2 }));
    // a request that waited for its token is throttled
    let reg2 = Arc::new(Registry::default());
    reg2.set_limit("c", 2.0, Some(1.0));
    let rpc2 = Rpc::race(vec![ep("c", &c)]).with_failover(true).with_registry(reg2.clone()).with_role(Role::Exec);
    for _ in 0..2 { rpc2.call_bounded("getSlot", json!([]), Bounds::fetch(Duration::from_secs(2), 0)).await.unwrap(); }
    let t2 = reg2.total(Role::Exec, "c");
    assert_eq!((t2.calls, t2.throttled), (2, 1), "the second waited about 0.5 s for its token: {t2:?}");
}

/// review WP-03b #14: a client with its own phase is not under the boot policy while the root boots (the LeaderBook's
/// calls fail over as configured, without boot retries or boot events)
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn a_client_with_its_own_phase_is_not_under_the_boot_policy() {
    let (a, an) = fake_http(|_, _| Reply::Status(503)).await;
    let reg = Arc::new(Registry::default());
    let root = Rpc::race(vec![ep("a", &a)]).with_failover(true).with_registry(reg.clone()).with_role(Role::Boot);
    root.set_phase(Phase::Boot);
    root.set_boot_budget(Duration::from_secs(30));
    let leaders = root.with_role(Role::Leaders).with_own_phase(Phase::Run);
    assert_eq!((root.phase(), leaders.phase()), (Phase::Boot, Phase::Run));
    let t0 = Instant::now();
    assert!(leaders.slot().await.is_err());
    assert!(t0.elapsed() < Duration::from_secs(2) && an.load(Relaxed) == 1, "one request, no boot retries");
    root.set_phase(Phase::Run);
    assert_eq!(leaders.phase(), Phase::Run);
}

/// The connections are kept warm (`start_warm`): a provider idle for `idle` gets a getSlot (role `warm`) on the next
/// pass; a busy one gets none
#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn idle_providers_are_kept_warm() {
    let (a, _) = fake_http(|_, _| ok(json!(1))).await;
    let (b, _) = fake_http(|_, _| ok(json!(1))).await;
    let reg = Arc::new(Registry::default());
    let rpc = Rpc::race(vec![ep("a", &a), ep("b", &b)]).with_failover(true).with_registry(reg.clone());
    let stop = Arc::new(AtomicBool::new(false));
    let h = rpc.start_warm(&tokio::runtime::Handle::current(), stop.clone(), Duration::from_millis(300), Duration::from_millis(100));
    let busy = rpc.only_role(Role::Engine, &["b".to_string()]);
    let t0 = Instant::now();
    while t0.elapsed() < Duration::from_millis(1_500) {
        busy.slot().await.unwrap();
        tokio::time::sleep(Duration::from_millis(50)).await;
    }
    stop.store(true, Relaxed);
    h.await.unwrap();
    let (wa, wb) = (reg.total(Role::Warm, "a"), reg.total(Role::Warm, "b"));
    assert!((2..=8).contains(&wa.ok), "idle a: a warm-up call about every 300-400 ms: {wa:?}");
    assert_eq!(wb.calls, 0, "busy b: none");
}

/// FT-000 (S1-1): a reserved share. A 4/s bucket kept busy by a normal role (the lookup tables, 8 callers always
/// waiting) starves the slot index (index priority) and the backfill (bulk) without a reserve; with 2/s reserved for the
/// slot index and 1/s for the backfill, each gets at least its share, the normal role the rest, the bucket as a whole
/// never more than its rate, and a critical caller still goes first. The reserved grants are counted (`reserved`), the
/// backfill's spare rate is never under its share, and the reserves are in `limits_json` and the status's
/// `rpc_budget`
#[tokio::test(start_paused = true)]
async fn reserved_shares_are_served_ahead_of_busier_roles() {
    async fn run(reserve: bool) -> (Arc<Registry>, BTreeMap<Role, u64>) {
        let reg = Arc::new(Registry::default());
        reg.set_limit("p", 4.0, None);
        if reserve { reg.set_reserve("p", Role::Slotidx, 2.0); reg.set_reserve("p", Role::Backfill, 1.0); }
        let lim = reg.limiter("p");
        let got: Arc<Mutex<BTreeMap<Role, u64>>> = Default::default();
        let stop = Arc::new(AtomicBool::new(false));
        let mut hs = Vec::new();
        for (role, n) in [(Role::Alt, 8), (Role::Slotidx, 3), (Role::Backfill, 3)] {
            for _ in 0..n {
                let (lim, got, stop, reg) = (lim.clone(), got.clone(), stop.clone(), reg.clone());
                hs.push(tokio::spawn(async move {
                    while !stop.load(Relaxed) {
                        if let Ok((w, lane)) = lim.take_role(role, Some(Instant::now() + Duration::from_secs(30))).await {
                            reg.record_lane(role, "p", lane);
                            reg.record(role, "p", Ok(1_000), w);
                            *got.lock().unwrap().entry(role).or_default() += 1;
                        }
                    }
                }));
            }
        }
        tokio::time::sleep(Duration::from_secs(60)).await;
        let out = got.lock().unwrap().clone();
        // a critical caller arriving now is served at once, ahead of everyone: the reserved and normal callers left a
        // quarter of the burst in the bucket for it
        let t = Instant::now();
        let (w, lane) = lim.take_role(Role::Snapshot, None).await.unwrap();
        assert!(lane == Lane::Critical && w.is_zero() && t.elapsed().is_zero(), "{w:?} {:?}", t.elapsed());
        stop.store(true, Relaxed);
        tokio::time::sleep(Duration::from_secs(40)).await;
        for h in hs { h.abort(); }
        (reg, out)
    }
    let (_, before) = run(false).await;
    assert_eq!((before.get(&Role::Slotidx).copied().unwrap_or(0), before.get(&Role::Backfill).copied().unwrap_or(0)), (0, 0), "without a reserve: starved {before:?}");
    let (reg, after) = run(true).await;
    let (si, bf, alt) = (after[&Role::Slotidx], after[&Role::Backfill], after[&Role::Alt]);
    // 60 s at 4/s (plus the burst, and the tail while the callers stop)
    assert!(si >= 115 && bf >= 57, "the reserved shares: slotidx {si} (>= 2/s), backfill {bf} (>= 1/s)");
    assert!(alt >= 40, "the normal role gets the rest: {alt}");
    assert!(si + bf + alt <= 4 * 60 + 4, "the bucket never exceeds its rate: {after:?}");
    let t = reg.total(Role::Slotidx, "p");
    assert!(t.reserved >= 100 && t.reserved <= t.calls, "{t:?}");
    assert_eq!(reg.total(Role::Alt, "p").reserved, 0, "no share, no reserved grant");
    assert!(reg.spare_rps("p", Role::Backfill).unwrap() >= 1.0, "the backfill paces to at least its share");
    assert_eq!(reg.limits_json()["p"]["reserve"], json!({ "backfill": 1.0, "slotidx": 2.0 }));
    // the status's budget section: per provider and role, with the shares; then the next interval's deltas only
    let b = reg.budget_json("test");
    assert!(b["interval_s"].is_null(), "the first call has no interval");
    let p = &b["providers"]["p"];
    assert_eq!((p["max_rps"].as_f64(), p["roles"]["slotidx"]["reserved_rps"].as_f64(), p["roles"]["alt"]["reserved_rps"].clone()), (Some(4.0), Some(2.0), Value::Null));
    assert_eq!(p["roles"]["slotidx"]["calls_delta"].as_u64(), Some(t.calls));
    assert!(b["roles"]["alt"]["calls_delta"].as_u64().unwrap() >= 40);
    tokio::time::sleep(Duration::from_secs(10)).await;
    for _ in 0..20 { if let Ok((w, l)) = reg.limiter("p").take_role(Role::Alt, None).await { reg.record_lane(Role::Alt, "p", l); reg.record(Role::Alt, "p", Ok(1), w); } }
    let b = reg.budget_json("test");
    let p = &b["providers"]["p"];
    let secs = b["interval_s"].as_f64().unwrap();
    assert!(secs > 10.0, "{b}");
    assert_eq!(p["roles"]["alt"]["calls_delta"].as_u64(), Some(20));
    assert!((p["roles"]["alt"]["rps"].as_f64().unwrap() - 20.0 / secs).abs() < 0.01 && (p["used_pct"].as_f64().unwrap() - 2_000.0 / secs / 4.0).abs() < 0.1, "{p}");
    assert_eq!(p["roles"]["slotidx"]["calls_delta"].as_u64(), Some(0), "a reserved role is listed even when idle");
}

/// FT-000 (S1-1): a share set on a bucket is scaled down when the shares add up to more than 95% of its rate, removed
/// with 0, and a provider without a limit has none
#[test]
fn reserves_are_bounded_and_need_a_limit() {
    let l = Limiter::new(4.0, 4.0);
    l.set_reserve(Role::Slotidx, 3.0);
    l.set_reserve(Role::Backfill, 3.0);
    let sum: f64 = l.reserves().iter().map(|x| x.1).sum();
    assert!((sum - 4.0 * MAX_RESERVE).abs() < 1e-9 && (sum - 3.8).abs() < 1e-9, "{:?}", l.reserves());
    l.set_reserve(Role::Backfill, 0.0);
    assert_eq!(l.reserves().len(), 1);
    let u = Limiter::unlimited();
    u.set_reserve(Role::Slotidx, 2.0);
    assert!(u.reserves().is_empty());
}

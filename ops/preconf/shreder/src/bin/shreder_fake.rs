//! shreder_fake — LOCAL fake Shreder Binary/preconf gRPC server for testing shreder_rec without access.
//! Streams synthetic VersionedTransaction bytes (pump bq3 buys + vote-like fillers) at a fixed rate. A tx in a
//! "connected-leader" slot is sent on preconf=true subscriptions immediately and on preconf=false subscriptions
//! --lead-ms later, so the recorder's live lead estimate can be checked. Never used against anything real.
use shreder_rec::pb::shreder_binary_service_server::{ShrederBinaryService, ShrederBinaryServiceServer};
use shreder_rec::pb::*;
use shreder_rec::txparse::{build, decode_pubkey, PUMP_PROGRAM};
use std::pin::Pin;
use std::sync::atomic::{AtomicU64, Ordering::Relaxed};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::broadcast;
use tokio_stream::Stream;
use tonic::{Request, Response, Status, Streaming};

#[derive(Clone)]
struct GenTx {
    sig: [u8; 64],
    bytes: Arc<Vec<u8>>,
    slot: u64,
    pump: bool,
    covered: bool,
    t_gen: Instant,
}

struct Opts {
    port: u16,
    rate: f64,
    pre_share: f64,
    lead_ms: f64,
    pump_share: f64,
    drop_after: u64,
    token: Option<String>,
    reject_unfiltered: bool,
    secs: f64,
    /// refuse a subscription when this many are already active (0 = unlimited)
    max_conns: i64,
    /// fill sigs/keys/blockhash with pseudo-random bytes (realistic compressibility for CPU tests)
    random: bool,
}

struct Fake {
    o: Arc<Opts>,
    tx: broadcast::Sender<GenTx>,
    conns_pre: AtomicU64,
    conns_bin: AtomicU64,
    active: Arc<std::sync::atomic::AtomicI64>,
    /// last request's filters, for tests: (name, preconf, include, exclude)
    seen: Arc<std::sync::Mutex<Vec<(String, bool, Vec<String>, Vec<String>)>>>,
}

struct ActiveGuard(Arc<std::sync::atomic::AtomicI64>);
impl Drop for ActiveGuard {
    fn drop(&mut self) {
        self.0.fetch_sub(1, Relaxed);
    }
}

type RespStream = Pin<Box<dyn Stream<Item = Result<SubscribeBinaryTransactionsResponse, Status>> + Send>>;

fn ts_now() -> prost_types::Timestamp {
    let d = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).unwrap();
    prost_types::Timestamp { seconds: d.as_secs() as i64, nanos: d.subsec_nanos() as i32 }
}

#[tonic::async_trait]
impl ShrederBinaryService for Fake {
    type SubscribeBinaryTransactionsStream = RespStream;

    async fn subscribe_binary_transactions(
        &self,
        request: Request<Streaming<SubscribeBinaryTransactionsRequest>>,
    ) -> Result<Response<RespStream>, Status> {
        if let Some(tok) = &self.o.token {
            let got = request.metadata().get("x-token").and_then(|v| v.to_str().ok()).unwrap_or("");
            if got != tok {
                return Err(Status::permission_denied("Access denied (fake): bad or missing token"));
            }
        }
        let mut inbound = request.into_inner();
        let first = match inbound.message().await {
            Ok(Some(r)) => r,
            _ => return Err(Status::invalid_argument("no subscribe request")),
        };
        if first.transactions.is_empty() {
            return Err(Status::invalid_argument("empty filter map"));
        }
        for (name, f) in &first.transactions {
            let accts: Vec<String> = f.account_include.iter().chain(f.account_required.iter()).cloned().collect();
            if accts.is_empty() && self.o.reject_unfiltered {
                return Err(Status::invalid_argument("fake: unfiltered subscriptions are not allowed"));
            }
            if f.preconf && !f.account_exclude.is_empty() {
                return Err(Status::invalid_argument("account_exclude is not allowed with preconf"));
            }
            if let Ok(mut v) = self.seen.lock() {
                v.push((name.clone(), f.preconf, f.account_include.clone(), f.account_exclude.clone()));
            }
        }
        if self.o.max_conns > 0 && self.active.load(Relaxed) >= self.o.max_conns {
            return Err(Status::resource_exhausted("fake: connection limit exceeded"));
        }
        self.active.fetch_add(1, Relaxed);
        let guard = Arc::new(ActiveGuard(self.active.clone()));
        let (out_tx, out_rx) = tokio::sync::mpsc::channel(20_000);
        let _keep_inbound = Arc::new(tokio::sync::Mutex::new(inbound)); // client half stays open
        for (name, f) in first.transactions {
            let accts: Vec<String> = f.account_include.iter().chain(f.account_required.iter()).cloned().collect();
            let want_pump = accts.iter().any(|a| a == PUMP_PROGRAM);
            let all = accts.is_empty();
            let preconf = f.preconf;
            let conn_no = if preconf { self.conns_pre.fetch_add(1, Relaxed) } else { self.conns_bin.fetch_add(1, Relaxed) } + 1;
            let drop_after = if conn_no == 1 { self.o.drop_after } else { 0 };
            let lead = Duration::from_secs_f64(self.o.lead_ms / 1000.0);
            let mut rx = self.tx.subscribe();
            let out_tx = out_tx.clone();
            let guard = guard.clone();
            let keep = _keep_inbound.clone();
            tokio::spawn(async move {
                let _g = guard;
                let _k = keep;
                let mut n = 0u64;
                loop {
                    let g = match rx.recv().await {
                        Ok(g) => g,
                        Err(broadcast::error::RecvError::Lagged(_)) => continue,
                        Err(_) => break,
                    };
                    if !(all || (want_pump && g.pump)) {
                        continue;
                    }
                    if preconf {
                        if !g.covered {
                            continue;
                        }
                    } else {
                        tokio::time::sleep_until((g.t_gen + lead).into()).await;
                    }
                    let resp = SubscribeBinaryTransactionsResponse {
                        filters: vec![name.clone()],
                        transaction: Some(SubscribeUpdateBinaryTransaction {
                            transaction: Some(BinaryTransaction { signatures: vec![g.sig.to_vec()], binary_transaction: (*g.bytes).clone() }),
                            slot: g.slot,
                            preconf,
                        }),
                        created_at: Some(ts_now()),
                    };
                    if out_tx.send(Ok(resp)).await.is_err() {
                        break;
                    }
                    n += 1;
                    if drop_after > 0 && n >= drop_after {
                        break; // ends this filter's feed; the stream ends when all feeds ended
                    }
                }
            });
        }
        drop(out_tx);
        Ok(Response::new(Box::pin(tokio_stream::wrappers::ReceiverStream::new(out_rx))))
    }
}

fn parse() -> Opts {
    let mut o = Opts { port: 0, rate: 2000.0, pre_share: 0.5, lead_ms: 5.0, pump_share: 0.2, drop_after: 0, token: None, reject_unfiltered: false, secs: 60.0, random: false, max_conns: 0 };
    let mut a = std::env::args().skip(1);
    while let Some(k) = a.next() {
        let mut v = || a.next().expect("value");
        match k.as_str() {
            "--port" => o.port = v().parse().unwrap(),
            "--rate" => o.rate = v().parse().unwrap(),
            "--pre-share" => o.pre_share = v().parse().unwrap(),
            "--lead-ms" => o.lead_ms = v().parse().unwrap(),
            "--pump-share" => o.pump_share = v().parse().unwrap(),
            "--drop-after" => o.drop_after = v().parse().unwrap(),
            "--token" => o.token = Some(v()),
            "--reject-unfiltered" => o.reject_unfiltered = true,
            "--secs" => o.secs = v().parse().unwrap(),
            "--random" => o.random = true,
            "--max-conns" => o.max_conns = v().parse().unwrap(),
            _ => panic!("unknown arg {k}"),
        }
    }
    o
}

#[tokio::main(flavor = "multi_thread", worker_threads = 2)]
async fn main() {
    let o = Arc::new(parse());
    let (tx, _) = broadcast::channel::<GenTx>(200_000);
    let pump = decode_pubkey(PUMP_PROGRAM).unwrap();
    // generator
    {
        let tx = tx.clone();
        let o = o.clone();
        tokio::spawn(async move {
            let t0 = Instant::now();
            let base_slot = 400_000_000u64;
            let mut made = 0u64;
            let mut tick = tokio::time::interval(Duration::from_millis(1));
            tick.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Burst);
            loop {
                tick.tick().await;
                let el = t0.elapsed().as_secs_f64();
                let due = (el * o.rate) as u64;
                while made < due {
                    made += 1;
                    let slot = base_slot + (el / 0.4) as u64;
                    let leader = slot / 4;
                    let covered = (leader.wrapping_mul(2654435761) % 1000) as f64 / 1000.0 < o.pre_share;
                    let mut sig = [0u8; 64];
                    sig[..8].copy_from_slice(&made.to_le_bytes());
                    sig[8..16].copy_from_slice(&0x5eed_u64.to_le_bytes());
                    sig[63] = 1;
                    let mut rng = made.wrapping_mul(0x9E3779B97F4A7C15) | 1;
                    let mut rnd = |buf: &mut [u8]| {
                        for b in buf.iter_mut() {
                            rng ^= rng << 13;
                            rng ^= rng >> 7;
                            rng ^= rng << 17;
                            *b = rng as u8;
                        }
                    };
                    if o.random {
                        rnd(&mut sig[16..]);
                    }
                    let is_pump = (made.wrapping_mul(11400714819323198485) >> 40) as f64 / (1u64 << 24) as f64 % 1.0 < o.pump_share;
                    let bytes = if is_pump {
                        let mut user = [0u8; 32];
                        user[..8].copy_from_slice(&made.to_le_bytes());
                        let mut mint = [7u8; 32];
                        mint[0] = (made % 50) as u8;
                        if o.random {
                            rnd(&mut user[8..]);
                        }
                        build::pump_bq3_tx(sig, user, mint, pump, 1_000_000 + made, 42, made % 2 == 0)
                    } else {
                        // vote-like filler: 1 signer, vote program key, one ix
                        let mut keys = vec![[1u8; 32], [2u8; 32], [0x07u8; 32]];
                        let mut bh = [3u8; 32];
                        let mut data = vec![14, 0, 0, 0, 1, 2, 3, 4, 5, 6, 7, 8];
                        if o.random {
                            rnd(&mut keys[0]);
                            rnd(&mut keys[1]);
                            rnd(&mut bh);
                            data.resize(120, 0);
                            rnd(&mut data[12..60]);
                        }
                        let ixs = vec![build::Ix { program_idx: 2, accounts: vec![1, 0], data }];
                        build::tx_bytes(&[sig], false, [1, 0, 1], &keys, bh, &ixs, &[])
                    };
                    let _ = tx.send(GenTx { sig, bytes: Arc::new(bytes), slot, pump: is_pump, covered, t_gen: Instant::now() });
                }
            }
        });
    }
    let seen = Arc::new(std::sync::Mutex::new(Vec::new()));
    let svc = Fake { o: o.clone(), tx, conns_pre: AtomicU64::new(0), conns_bin: AtomicU64::new(0), active: Arc::new(std::sync::atomic::AtomicI64::new(0)), seen: seen.clone() };
    // print every subscription's filters on stderr (tests read it)
    {
        let seen = seen.clone();
        tokio::spawn(async move {
            let mut printed = 0;
            loop {
                tokio::time::sleep(Duration::from_millis(100)).await;
                if let Ok(v) = seen.lock() {
                    while printed < v.len() {
                        let (n, p, i, e) = &v[printed];
                        eprintln!("FILTER name={n} preconf={p} include={} exclude={}", i.join(","), e.join(","));
                        printed += 1;
                    }
                }
            }
        });
    }
    let listener = tokio::net::TcpListener::bind(("127.0.0.1", o.port)).await.expect("bind");
    let port = listener.local_addr().unwrap().port();
    println!("PORT {port}");
    use std::io::Write;
    std::io::stdout().flush().ok();
    let incoming = tonic::transport::server::TcpIncoming::from(listener).with_nodelay(Some(true));
    let secs = o.secs;
    tokio::select! {
        r = tonic::transport::Server::builder().add_service(ShrederBinaryServiceServer::new(svc)).serve_with_incoming(incoming) => { r.expect("serve") }
        _ = tokio::time::sleep(Duration::from_secs_f64(secs)) => {}
    }
}

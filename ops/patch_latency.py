# Patch snipe_engine.rs: take the 3 sequential RPC round trips OFF the buy's critical path.
#  (1) background-cached blockhash (refreshed every 300 ms) used by send_and_poll (falls back to a fetch if empty/stale)
#  (2) send_slot from the slot poller's send::tpu::SLOT instead of a getSlot round trip
#  (3) bal_start read concurrently with the buy send (join), not before it
#  (4) log the prep latency: round_trip entry -> send, and send_and_poll entry -> send
import sys
P = "/root/arbx-fast/src/bin/snipe_engine.rs"
s = open(P).read()
if "BLOCKHASH_CACHE" in s:
    print("already patched"); sys.exit(0)

a = "static ALSO_PATH: std::sync::OnceLock<Arc<send::Path>> = std::sync::OnceLock::new();\n"
assert s.count(a) == 1
s = s.replace(a, a + """/// latest blockhash kept fresh in the background (hash, fetched-at), so a buy never waits on getLatestBlockhash.
static BLOCKHASH_CACHE: std::sync::Mutex<Option<([u8; 32], Instant)>> = std::sync::Mutex::new(None);
""", 1)

# (1) refresher next to the slot poller
a = """                tokio::time::sleep(Duration::from_millis(250)).await;
            }
        });
    }
"""
assert s.count(a) == 1, "slot poller"
s = s.replace(a, a + """    {
        // blockhash refresher: a buy takes the cached hash (<= ~300 ms old, valid ~60 s) instead of a round trip.
        let (rpc, stop) = (rpc.clone(), stop.clone());
        tokio::spawn(async move {
            while !stop.load(Ordering::Relaxed) {
                if let Ok((h, _)) = rpc.latest_blockhash().await {
                    *BLOCKHASH_CACHE.lock().unwrap() = Some((h, Instant::now()));
                }
                tokio::time::sleep(Duration::from_millis(300)).await;
            }
        });
    }
""", 1)

# (2)+(4) in send_and_poll
a = """    let (blockhash, _) = rpc.latest_blockhash().await.context("getLatestBlockhash")?;"""
assert s.count(a) == 1
s = s.replace(a, """    let cached = BLOCKHASH_CACHE.lock().unwrap().filter(|(_, t)| t.elapsed() < Duration::from_secs(20)).map(|(h, _)| h);
    let blockhash = match cached { Some(h) => h, None => rpc.latest_blockhash().await.context("getLatestBlockhash")?.0 };""", 1)
a = """    let send_slot = rpc.slot().await.unwrap_or(0);
    match also {"""
assert s.count(a) == 1, "send_slot in send_and_poll"
s = s.replace(a, """    let send_slot = match send::tpu::SLOT.load(Ordering::Relaxed) { 0 => rpc.slot().await.unwrap_or(0), s => s };
    eprintln!("  SEND-PREP {:.1} ms (send_and_poll entry -> send)", t_sp.elapsed().as_secs_f64() * 1e3);
    match also {""", 1)
a = """async fn send_and_poll(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, ixs: &[build::Ix], land_timeout: Duration) -> Result<Landed> {
"""
assert s.count(a) == 1
s = s.replace(a, a + "    let t_sp = Instant::now();\n", 1)

# (3)+(4) in round_trip_launch
a = """    let bal_start = native_balance(rpc, user).await.unwrap_or(0);
    let buy = send_and_poll(key, user, rpc, path, &buy_ixs, land_timeout).await?;"""
assert s.count(a) == 1
s = s.replace(a, """    eprintln!("  BUY-PREP {:.1} ms (round_trip entry -> send_and_poll)", t_rt.elapsed().as_secs_f64() * 1e3);
    let (bal_start, buy) = tokio::join!(async { native_balance(rpc, user).await.unwrap_or(0) },
                                        send_and_poll(key, user, rpc, path, &buy_ixs, land_timeout));
    let buy = buy?;""", 1)
a = "async fn round_trip_launch(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, launch: &Launch,"
i = s.index(a)
j = s.index("{\n", i) + 2
s = s[:j] + "    let t_rt = Instant::now();\n" + s[j:]
open(P, "w").write(s)
print("patched OK")

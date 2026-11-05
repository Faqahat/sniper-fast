//! `apex_probe --bench N` — ZERO COST, no config, no network, no wallet: measures on THIS machine what the hot path costs
//!  1. build + sign of a buy's lane copies: the lib path (v2) vs the fast path (v3), back-to-back (warm caches) and with
//!     50 ms idle between launches (cold: what a real launch every few seconds sees), and cold but kept warm (--warm-ms);
//!  2. the feed -> hot-thread hand-off over the same crossbeam channel: blocking recv (futex wake-up) vs --busy-poll.
//! Run it on the server (optionally with --pin-core C) to see that machine's numbers.

use crate::fastbuild::FastCtx;
use crate::logic::{self, BuyCfg, LaneCopy, GUARD_DEFAULT};
use arbx::fast;
use arbx::snipe_build;
use ed25519_dalek::SigningKey;
use std::sync::atomic::AtomicBool;
use std::sync::Arc;
use std::time::{Duration, Instant};

fn q(v: &mut [f64], f: f64) -> f64 { if v.is_empty() { return f64::NAN; } v.sort_by(|a, b| a.partial_cmp(b).unwrap()); v[((v.len() - 1) as f64 * f).round() as usize] }
fn line(name: &str, v: &mut [f64]) -> String { format!("{name:44} p50 {:7.1}  p90 {:7.1}  p99 {:7.1}  (n {})", q(v, 0.5), q(v, 0.9), q(v, 0.99), v.len()) }

fn rnd(i: u64, tag: u8) -> [u8; 32] {
    use sha2::{Digest, Sha256};
    Sha256::new().chain_update(i.to_le_bytes()).chain_update([tag]).finalize().into()
}

pub fn run(n: usize, pin: Option<usize>, warm_ms: u64) -> anyhow::Result<()> {
    if let Some(c) = pin { println!("pin to core {c}: {}", fast::pin_to_core(c)); }
    let key = SigningKey::from_bytes(&rnd(1, 1));
    let user = key.verifying_key().to_bytes();
    let stop = Arc::new(AtomicBool::new(false));
    let ps = fast::Presigner::new(&key);
    ps.start(300, stop.clone());
    let fx = FastCtx::new(&key, user, Some(ps));
    println!("{}", crate::fastbuild::selftest(&fx, 50).map_err(|e| anyhow::anyhow!(e))?);
    let lanes = [LaneCopy { pi: 0, tip: Some((rnd(9, 9), 2_000_000)), prio: 100_000 }, LaneCopy { pi: 1, tip: None, prio: 2_000_000 },
        LaneCopy { pi: 2, tip: Some((rnd(8, 8), 2_500_000)), prio: 500_000 }];
    let nonce = (rnd(7, 7), rnd(6, 6));
    let launch = |i: u64| {
        let mint = rnd(i, 2);
        let mut l = snipe_build::launch_from_target(mint, rnd(i, 3));
        l.buyback_fee_recipient = rnd(i, 4);
        l
    };
    let cfg = |slot: u64| BuyCfg { user, spend: 50_000_000, min_out: 1_234_567, cu_limit: 100_000, cu_price: 0, guard: Some((GUARD_DEFAULT, slot)) };
    let tpls: Vec<_> = lanes.iter().map(|ln| fx.template(50_000_000, 100_000, ln.tip.map(|t| t.1), ln.prio, Some(GUARD_DEFAULT)).unwrap()).collect();
    let mut tbuf = Vec::with_capacity(1232);
    let mut out: Vec<String> = Vec::new();
    for (mode, idle) in [("warm", 0u64), ("cold 50 ms idle", 50), ("cold, kept warm", 50), ("50 ms idle spinning", 50)] {
        let keep = mode == "cold, kept warm";
        let spin = mode == "50 ms idle spinning";
        let (mut slow1, mut slow_all, mut fast1, mut fast_all) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
        let (mut tpl1, mut tpl_all) = (Vec::new(), Vec::new());
        // idle between launches; "kept warm" runs one throw-away build every --warm-ms meanwhile (as the hot thread does)
        let wait = |i: u64| {
            if idle == 0 { return; }
            let t_end = Instant::now() + Duration::from_millis(idle);
            if spin { let mut k = 0u64; while Instant::now() < t_end { std::hint::spin_loop(); k += 1; if k % 4096 == 0 && warm_ms > 0 { /* busy-poll + warm, as the hot loop */ } } return; }
            while Instant::now() < t_end {
                if keep && warm_ms > 0 { let l = launch(1_000_000 + i); let k = fx.keys(&l); let _ = fx.lane_copy(&cfg(1), &k, nonce, &lanes[0]); }
                std::thread::sleep(Duration::from_millis(if keep { warm_ms.max(1) } else { idle }).min(t_end.saturating_duration_since(Instant::now())));
            }
        };
        for i in 0..n as u64 {
            wait(i);
            let l = launch(i);
            // v2 (lib) path, first copy then the rest
            let t = Instant::now();
            let a = logic::build_lane_copies(&key, &cfg(i), &l, nonce, &lanes[..1]).unwrap();
            slow1.push(t.elapsed().as_secs_f64() * 1e6);
            let _ = logic::build_lane_copies(&key, &cfg(i), &l, nonce, &lanes[1..]).unwrap();
            slow_all.push(t.elapsed().as_secs_f64() * 1e6);
            wait(i);
            // v3 fast path: keys once, then lane by lane
            let t = Instant::now();
            let k = fx.keys(&l);
            let b = fx.lane_copy(&cfg(i), &k, nonce, &lanes[0]).unwrap();
            fast1.push(t.elapsed().as_secs_f64() * 1e6);
            for ln in &lanes[1..] { let _ = fx.lane_copy(&cfg(i), &k, nonce, ln).unwrap(); }
            fast_all.push(t.elapsed().as_secs_f64() * 1e6);
            // same message bytes (signatures differ: presigned nonce)
            assert_eq!(a[0].raw[65..], b.raw[65..], "fast build != lib build");
            wait(i);
            // v3 templates: keys once, then patch + sign per lane
            let t = Instant::now();
            let k = fx.keys(&l);
            let c0 = fx.lane_copy_tpl(&tpls[0], &k, nonce, &lanes[0], 1_234_567, Some(i), &mut tbuf).unwrap();
            tpl1.push(t.elapsed().as_secs_f64() * 1e6);
            for (ln, tp) in lanes[1..].iter().zip(&tpls[1..]) { let _ = fx.lane_copy_tpl(tp, &k, nonce, ln, 1_234_567, Some(i), &mut tbuf).unwrap(); }
            tpl_all.push(t.elapsed().as_secs_f64() * 1e6);
            assert_eq!(c0.raw[65..], b.raw[65..], "template != fast build");
        }
        out.push(line(&format!("build v2 lib  first copy  [{mode}] us"), &mut slow1));
        out.push(line(&format!("build v2 lib  3 copies    [{mode}] us"), &mut slow_all));
        out.push(line(&format!("build v3 fast first copy  [{mode}] us"), &mut fast1));
        out.push(line(&format!("build v3 fast 3 copies    [{mode}] us"), &mut fast_all));
        out.push(line(&format!("build v3 TEMPLATE first   [{mode}] us"), &mut tpl1));
        out.push(line(&format!("build v3 TEMPLATE 3 copies [{mode}] us"), &mut tpl_all));
    }
    // hand-off latency: a producer thread every 2 ms, the consumer blocking (recv_timeout) or spinning (try_recv)
    for busy in [false, true] {
        let (tx, rx) = crossbeam_channel::unbounded::<u64>();
        let m = n.max(200);
        let h = std::thread::spawn(move || { for _ in 0..m { std::thread::sleep(Duration::from_millis(2)); let _ = tx.send(fast::mono_ns()); } });
        let mut lat = Vec::with_capacity(m);
        loop {
            let got = if busy {
                match rx.try_recv() { Ok(t) => Some(t), Err(crossbeam_channel::TryRecvError::Empty) => { std::hint::spin_loop(); continue; } Err(_) => None }
            } else { rx.recv_timeout(Duration::from_millis(100)).ok() };
            match got { Some(t) => lat.push((fast::mono_ns() - t) as f64 / 1e3), None => break }
        }
        let _ = h.join();
        out.push(line(&format!("feed->hot hand-off {} us", if busy { "--busy-poll   " } else { "blocking recv " }), &mut lat));
    }
    stop.store(true, std::sync::atomic::Ordering::Relaxed);
    for l in out { println!("{l}"); }
    Ok(())
}

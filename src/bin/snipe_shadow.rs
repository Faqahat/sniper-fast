//! Live shred SHADOW for the pump sniper — OBSERVER ONLY.
//!
//! Taps the same shred feed the arb engine uses, but with an Interest of just the pump.fun program, and
//! logs every detected `create_v2`/`create` launch with its feed-arrival timing. It builds NO engine, NO
//! wallet, NO executor, and has NO send path — it cannot trade. Its entire purpose is to answer one
//! question: do we see launches, and how fast, so we can judge same-slot feasibility before risking a cent.
//!
//! Usage: snipe_shadow --config <arb.toml> [--minutes N] [--out launches.jsonl]
//! Each detection appends one JSON line: wall_ns, feed, slot, t_rx, t_decoded, detect_lag_ns, mint,
//! bonding_curve, creator, dev_buy_lamports, create_v2.

use std::io::Write;
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

use arbx::feeds::{self, clock::now_ns, Event};

fn arg(flag: &str, default: Option<&str>) -> Option<String> {
    let a: Vec<String> = std::env::args().collect();
    a.iter().position(|x| x == flag).and_then(|i| a.get(i + 1).cloned()).or_else(|| default.map(String::from))
}

fn main() -> anyhow::Result<()> {
    let config = PathBuf::from(arg("--config", Some("arb.toml")).unwrap());
    let minutes: f64 = arg("--minutes", Some("10")).unwrap().parse().unwrap_or(10.0);
    let out_path = arg("--out", Some("launches.jsonl")).unwrap();

    // Load a FEEDS-ONLY toml (decoupled from the full arb trading config / its schema).
    #[derive(serde::Deserialize)]
    struct FeedsFile {
        #[serde(rename = "feed", default)]
        feeds: Vec<arbx::config::Feed>,
    }
    let ff: FeedsFile = toml::from_str(&std::fs::read_to_string(&config)?)?;
    let feeds_vec = ff.feeds;
    eprintln!(
        "snipe_shadow: OBSERVER ONLY (no wallet, no exec, no send). config={} feeds={} minutes={}",
        config.display(), feeds_vec.iter().filter(|f| f.enabled).count(), minutes
    );

    // Own tokio runtime (the feed layer runs gRPC tasks / raw-UDP threads on it).
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
    let (tx, rx) = crossbeam_channel::unbounded::<Event>();
    let stop = Arc::new(AtomicBool::new(false));

    // Interest = pump.fun program only. Recorder off, roles none: a pure read tap.
    let interest = Arc::new(arbx::snipe::pump_interest());
    let rec = arbx::rec::Rec::off();
    let fs = feeds::start(&feeds_vec, interest, tx, stop.clone(), rt.handle(), &rec, None)?;
    eprintln!("feeds: {}", fs.names.join(", "));

    // Ctrl-C -> graceful stop
    {
        let stop = stop.clone();
        let _ = ctrlc_set(move || stop.store(true, Ordering::Relaxed));
    }

    let mut out = std::io::BufWriter::new(std::fs::File::create(&out_path)?);
    let deadline = Instant::now() + Duration::from_secs_f64(minutes * 60.0);
    let seen = AtomicU64::new(0);
    let hits = AtomicU64::new(0);

    while Instant::now() < deadline && !stop.load(Ordering::Relaxed) {
        match rx.recv_timeout(Duration::from_millis(500)) {
            Ok(Event::Tx(a)) => {
                seen.fetch_add(1, Ordering::Relaxed);
                if let Some(l) = arbx::snipe::detect_launch(&a.tx) {
                    let n = hits.fetch_add(1, Ordering::Relaxed) + 1;
                    // where-in-slot: ms since the slot began on the leader's PoH clock (entries feeds).
                    // headroom to fire a same-slot buy ~= 400ms - poh_ms - (our detect + send transit).
                    let poh_ms = a.poh.as_ref().and_then(|p| p.ms());
                    let line = serde_json::json!({
                        "wall_ns": now_ns(),
                        "feed": a.feed,
                        "slot": a.slot,
                        "t_rx": a.t_rx,
                        "t_decoded": a.t_decoded,
                        "detect_lag_ns": now_ns().saturating_sub(a.t_decoded),
                        "poh_ms": poh_ms,
                        "poh_slot": a.poh.as_ref().map(|p| p.slot),
                        "mint": arbx::tx::b58(&l.mint),
                        "bonding_curve": arbx::tx::b58(&l.bonding_curve),
                        "creator": arbx::tx::b58(&l.creator),
                        "dev_buy_lamports": l.dev_buy_lamports,
                        "create_v2": l.is_create_v2,
                    });
                    writeln!(out, "{}", line)?;
                    out.flush()?;
                    if n <= 20 || n % 25 == 0 {
                        eprintln!("[{n}] slot={} poh_ms={:?} mint={} dev_buy={}",
                            a.slot, poh_ms.map(|m| (m * 10.0).round() / 10.0),
                            arbx::tx::b58(&l.mint), l.dev_buy_lamports);
                    }
                }
            }
            Ok(_) => {}
            Err(crossbeam_channel::RecvTimeoutError::Timeout) => {}
            Err(_) => break,
        }
    }
    stop.store(true, Ordering::Relaxed);
    eprintln!(
        "done: {} pump txs seen, {} launches detected -> {}",
        seen.load(Ordering::Relaxed), hits.load(Ordering::Relaxed), out_path
    );
    Ok(())
}

// Minimal Ctrl-C handler via the `signal-hook` crate (already a dependency); falls back to a no-op.
fn ctrlc_set<F: Fn() + Send + Sync + 'static>(f: F) -> anyhow::Result<()> {
    use signal_hook::consts::SIGINT;
    let f = Arc::new(f);
    let mut sigs = signal_hook::iterator::Signals::new([SIGINT])?;
    std::thread::spawn(move || {
        for _ in sigs.forever() { f(); break; }
    });
    Ok(())
}

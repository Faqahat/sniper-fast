//! obs_soak (dip24): the OBSERVATORY soak. Pushes a recorded day of the collector's 24/7 recording (run_*/txs/txs_<unix>.jsonl.gz:
//! one JSON line per tx: s, i, bt, sig, err, cup, cul, signers, ev = the tx's "Program data:" strings, ixn, progs, mints) through the
//! real observatory (arbx::obs: its feeder, bounded channel, thread, modules, writer) at full speed, and reports the observatory
//! thread's time per message / per trade, channel drops, memory high-water, records and MB per module, scaled to a day.
//!   * decoding: chunk files decoded by worker threads (gzip -dc), handed over in chain order;
//!   * t_rx is synthesized from the slot (213 ms per slot, the recording's own slot rate) + 20 us per block index (the recording has
//!     no arrival time); successful txs with pump events -> the engine's executed message (Feeder::exec); failed txs of watched
//!     wallets -> Feeder::arrival (executed false); migrations (ixn Migrate*) -> Feeder::arrival (the PumpSwap program + the mints);
//!   * --pace block (default): the producer waits for room in the channel (full speed, no drops: the thread's throughput);
//!     --pace drop: plain try_send at full speed (drops counted: what a stalled observatory would lose);
//!     --pace realtime:X: the recording's own time x X (e.g. 20 = 20x real time), try_send (drops at a realistic rate x X).
//! usage: obs_soak --run DIR [--hours 24] [--from UNIX_S] [--out DIR] [--watch FILE] [--workers 6] [--pace block|drop|realtime:X]
use arbx::dip::{create_event_raw, trade_event_raw, CreateEvent, TradeEvent};
use arbx::feeds::{Arrival, ExecInfo, RawTx};
use arbx::tx::{Pk, Tx};
use std::collections::BTreeMap;
use std::io::BufRead;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};

#[derive(serde::Deserialize)]
struct Line<'a> {
    s: u64, i: u64, #[serde(default)] bt: i64, #[serde(borrow)] sig: Option<&'a str>, #[serde(default)] err: Option<serde::de::IgnoredAny>,
    #[serde(default)] cup: Option<u64>, #[serde(default)] cul: Option<u64>, #[serde(default, borrow)] signers: Vec<&'a str>, #[serde(default, borrow)] ev: Vec<&'a str>,
    #[serde(default, borrow)] ixn: Vec<&'a str>, #[serde(default, borrow)] progs: Vec<&'a str>, #[serde(default, borrow)] mints: Vec<&'a str>,
}

/// one decoded tx (what the soak feeds)
enum Item {
    Exec { s: u64, i: u64, sig: [u8; 64], payer: Pk, cup: Option<u64>, cul: Option<u32>, trades: Vec<TradeEvent>, creates: Vec<CreateEvent>, mayhem: bool },
    Fail { s: u64, sig: [u8; 64], payer: Pk, cup: Option<u64>, cul: Option<u32> },
    Raw { s: u64, sig: [u8; 64], keys: Vec<Pk> },
}

fn pk(s: &str) -> Option<Pk> { bs58::decode(s).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok()) }
fn sig64(s: Option<&str>) -> [u8; 64] { s.and_then(|x| bs58::decode(x).into_vec().ok()).and_then(|v| <[u8; 64]>::try_from(v).ok()).unwrap_or([0; 64]) }

fn b64(s: &str) -> Option<Vec<u8>> {
    use base64::Engine as _;
    let pad = (4 - s.len() % 4) % 4;
    let mut t = s.to_string(); for _ in 0..pad { t.push('='); }
    base64::engine::general_purpose::STANDARD.decode(t).ok()
}

/// one chunk file -> its items (and the first block time)
fn decode(p: &PathBuf, watch: &rustc_hash::FxHashSet<Pk>) -> (Vec<Item>, u64, u64) {
    let mut out = Vec::new();
    let (mut lines, mut bad) = (0u64, 0u64);
    let Ok(mut ch) = std::process::Command::new("gzip").arg("-dc").arg("--").arg(p).stdout(std::process::Stdio::piped()).stderr(std::process::Stdio::null()).spawn() else { return (out, 0, 1) };
    let rd = std::io::BufReader::with_capacity(1 << 20, ch.stdout.take().unwrap());
    let pumpswap = *arbx::venues::PUMPSWAP;
    for l in rd.lines() {
        let Ok(l) = l else { bad += 1; break };
        lines += 1;
        let Ok(x) = serde_json::from_str::<Line>(&l) else { bad += 1; continue };
        let failed = x.err.is_some();
        let payer = x.signers.first().and_then(|s| pk(s)).unwrap_or([0; 32]);
        let cul = x.cul.map(|c| c.min(u32::MAX as u64) as u32);
        // the live executed feed carries only txs naming the pump program (its subscription): the same here
        let pump_tx = x.progs.iter().any(|p| *p == "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P");
        if failed {
            if pump_tx && watch.contains(&payer) { out.push(Item::Fail { s: x.s, sig: sig64(x.sig), payer, cup: x.cup, cul }); }
            continue;
        }
        let (mut trades, mut creates) = (Vec::new(), Vec::new());
        for e in &x.ev {
            let Some(b) = b64(e) else { continue };
            if let Some(t) = trade_event_raw(&b) { trades.push(t); } else if let Some(c) = create_event_raw(&b) { creates.push(c); }
        }
        if !trades.is_empty() || !creates.is_empty() {
            let mayhem = !creates.is_empty() && x.ixn.iter().any(|n| *n == "InitializeMayhemState");
            out.push(Item::Exec { s: x.s, i: x.i, sig: sig64(x.sig), payer, cup: x.cup, cul, trades, creates, mayhem });
        } else if pump_tx && x.progs.iter().any(|p| pk(p) == Some(pumpswap)) {
            let mut keys: Vec<Pk> = vec![payer];
            keys.extend(x.progs.iter().filter_map(|p| pk(p)));
            keys.extend(x.mints.iter().filter_map(|m| pk(m)));
            out.push(Item::Raw { s: x.s, sig: sig64(x.sig), keys });
        }
    }
    let _ = ch.wait();
    (out, lines, bad)
}

fn vm(key: &str) -> u64 {
    std::fs::read_to_string("/proc/self/status").ok().and_then(|s| s.lines().find(|l| l.starts_with(key)).and_then(|l| l.split_whitespace().nth(1)).and_then(|x| x.parse().ok())).unwrap_or(0)
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let arg = |f: &str| args.iter().position(|x| x == f).and_then(|i| args.get(i + 1)).cloned();
    let run = PathBuf::from(arg("--run").unwrap_or_else(|| "/home/moiz/sniper-data/collect/run_20261027_1410".into()));
    let hours: f64 = arg("--hours").and_then(|x| x.parse().ok()).unwrap_or(24.0);
    let out_dir = PathBuf::from(arg("--out").unwrap_or_else(|| std::env::temp_dir().join("obs_soak").display().to_string()));
    let watch_f = arg("--watch").unwrap_or_else(|| "/home/moiz/sniper/ops/obs/watch_default.txt".into());
    let workers: usize = arg("--workers").and_then(|x| x.parse().ok()).unwrap_or(6);
    let pace = arg("--pace").unwrap_or_else(|| "block".into());
    let rt_x: Option<f64> = pace.strip_prefix("realtime:").and_then(|x| x.parse().ok());
    std::fs::create_dir_all(&out_dir).expect("--out");
    let mut files: Vec<(u64, PathBuf)> = arbx::presend_quiet::chunks(&run, 0, u64::MAX);
    files.sort();
    if let Some(f) = arg("--from").and_then(|x| x.parse::<u64>().ok()) { files.retain(|x| x.0 + 300 >= f); }
    let n_files = ((hours * 12.0).ceil() as usize).min(files.len());
    files.truncate(n_files);
    assert!(!files.is_empty(), "no chunk files in {}", run.display());
    let (watch, names) = arbx::obs::load_watch(&watch_f).unwrap_or_else(|e| { eprintln!("watch: {e}"); (Vec::new(), Default::default()) });
    let wset: rustc_hash::FxHashSet<Pk> = watch.iter().copied().collect();
    let obs_file = out_dir.join("soak.obs.jsonl");
    for k in 0..1000 { let _ = std::fs::remove_file(format!("{}.{k}", obs_file.display())); }
    let _ = std::fs::remove_file(&obs_file);
    let user: Pk = [0x5A; 32];
    let cfg = arbx::obs::Cfg { rearm: true, hold: true, migr: true, blink: true, backrun: true, select: true, race: true, inslot: true, feed_names: vec!["kaldera".into(), "kaldera-tx".into()], watch: watch.clone(), watch_file: Some(watch_f.clone()), watch_names: names, out: obs_file.clone(),
        tail: None, user, rate_cap: 40, k: 8, drop: 0.12, cohort: Default::default(), fbots: Default::default(), quiet_book: None, quiet_fol: 2.24, chan: 0, rotate_ns: 0, rotate_bytes: 0 };
    let rss0 = vm("VmRSS:");
    eprintln!("obs_soak: {} chunk files ({:.1} h) from {} | watch {} wallets | pace {pace} | workers {workers} | rss at start {} MB", files.len(), files.len() as f64 / 12.0, run.display(), watch.len(), rss0 / 1024);
    let mut obs = arbx::obs::Obs::start(cfg).expect("obs");
    let cap = arbx::obs::CHAN;
    // decode workers: chunk k -> (k, items); at most 2 x workers chunks waiting
    let (jtx, jrx) = crossbeam_channel::unbounded::<(usize, PathBuf)>();
    let (rtx, rrx) = crossbeam_channel::bounded::<(usize, Vec<Item>, u64, u64)>(workers * 2);
    for (k, (_, p)) in files.iter().enumerate() { jtx.send((k, p.clone())).unwrap(); }
    drop(jtx);
    let wsh = Arc::new(wset);
    for _ in 0..workers {
        let (jrx, rtx, w) = (jrx.clone(), rtx.clone(), wsh.clone());
        std::thread::spawn(move || { while let Ok((k, p)) = jrx.recv() { let (v, l, b) = decode(&p, &w); if rtx.send((k, v, l, b)).is_err() { break; } } });
    }
    drop(rtx);
    let t_start = Instant::now();
    let (mut pending, mut next) = (BTreeMap::new(), 0usize);
    let (mut s0, mut t_feed0): (u64, Option<(u64, Instant)>) = (0, None);
    let (mut n_exec, mut n_trades, mut n_fail, mut n_raw, mut lines, mut bad, mut waits) = (0u64, 0u64, 0u64, 0u64, 0u64, 0u64, 0u64);
    let mut rss_max = 0u64;
    let t0_unix = files[0].0 * 1_000_000_000;
    let tx_of = |s: u64, s0: u64, i: u64| t0_unix + (s.saturating_sub(s0)) * 213_000_000 + i * 20_000;
    let mut feed_us: Vec<f32> = Vec::with_capacity(1 << 20);
    while next < files.len() {
        if !pending.contains_key(&next) {
            match rrx.recv() { Ok((k, v, l, b)) => { pending.insert(k, v); lines += l; bad += b; continue; } Err(_) => break }
        }
        let items = pending.remove(&next).unwrap();
        next += 1;
        rss_max = rss_max.max(vm("VmRSS:"));
        for it in items {
            let s = match &it { Item::Exec { s, .. } | Item::Fail { s, .. } | Item::Raw { s, .. } => *s };
            if s0 == 0 { s0 = s; }
            if let Some(x) = rt_x {
                let t_data = s.saturating_sub(s0) * 213_000_000;
                let (td0, w0) = *t_feed0.get_or_insert((t_data, Instant::now()));
                let due = Duration::from_nanos(((t_data - td0) as f64 / x) as u64);
                let el = w0.elapsed();
                if due > el { std::thread::sleep(due - el); }
            } else if pace == "block" {
                while obs.feeder.queued() + 64 >= cap { waits += 1; std::thread::sleep(Duration::from_micros(200)); }
            }
            let tf = Instant::now();
            match it {
                Item::Exec { s, i, sig, payer, cup, cul, trades, creates, mayhem } => {
                    n_exec += 1; n_trades += trades.len() as u64;
                    let x = Arc::new(ExecInfo { index: i, fee: 5_000, ok: true, trades, creates, mayhem });
                    let a = Arrival { feed: 0, slot: s, t_rx: tx_of(s, s0, i), t_decoded: 0, executed: Some(true), tx: Tx { sig, keys: vec![payer], cu_price_micro: cup, cu_limit: cul, ..Default::default() },
                        poh: None, raw: RawTx::None, exec: Some(x.clone()) };
                    obs.feeder.exec(&a, &x);
                }
                Item::Fail { s, sig, payer, cup, cul } => {
                    n_fail += 1;
                    let a = Arrival { feed: 0, slot: s, t_rx: tx_of(s, s0, 0), t_decoded: 0, executed: Some(false), tx: Tx { sig, keys: vec![payer], cu_price_micro: cup, cu_limit: cul, ..Default::default() },
                        poh: None, raw: RawTx::None, exec: None };
                    obs.feeder.arrival(&a);
                }
                Item::Raw { s, sig, keys } => {
                    n_raw += 1;
                    let a = Arrival { feed: 0, slot: s, t_rx: tx_of(s, s0, 0), t_decoded: 0, executed: Some(true), tx: Tx { sig, keys, ..Default::default() }, poh: None, raw: RawTx::None, exec: None };
                    obs.feeder.arrival(&a);
                }
            }
            if feed_us.len() < (1 << 22) { feed_us.push(tf.elapsed().as_secs_f32() * 1e6); }
        }
        if next % 12 == 0 { eprintln!("  {:.1} h fed: {n_exec} exec txs, {n_trades} trades, queued {}, dropped {}, rss {} MB, {:.0} s", next as f64 / 12.0, obs.feeder.queued(),
            obs.feeder.ctr.drops.load(std::sync::atomic::Ordering::Relaxed), vm("VmRSS:") / 1024, t_start.elapsed().as_secs_f64()); }
    }
    let t_fed = t_start.elapsed();
    let end = obs.finish(Duration::from_secs(600));
    let t_all = t_start.elapsed();
    feed_us.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let fq = |q: f64| feed_us.get(((feed_us.len().max(1) - 1) as f64 * q) as usize).copied().unwrap_or(0.0);
    let hwm = vm("VmHWM:");
    // the last obs_status record: the observatory's own memory estimate
    let mut mem_est = serde_json::Value::Null;
    let mut parts = vec![obs_file.clone()];
    for k in 1..1000 { let p = PathBuf::from(format!("{}.{k}", obs_file.display())); if p.exists() { parts.push(p); } }
    for p in &parts {
        if let Ok(f) = std::fs::File::open(p) {
            for l in std::io::BufReader::new(f).lines().map_while(Result::ok) {
                if l.contains("\"ev\":\"obs_status\"") { if let Ok(v) = serde_json::from_str::<serde_json::Value>(&l) { mem_est = v["mem_mb_est"].clone(); } }
            }
        }
    }
    let scale = 24.0 / (files.len() as f64 / 12.0);
    let names = arbx::obs::MOD_NAMES;
    let recs = end["records"].as_array().cloned().unwrap_or_default();
    let bytes = end["bytes"].as_array().cloned().unwrap_or_default();
    let per_mod: serde_json::Map<String, serde_json::Value> = names.iter().enumerate().map(|(k, n)| (n.to_string(), serde_json::json!({
        "records": recs.get(k), "mb": bytes.get(k).and_then(|b| b.as_f64()).map(|b| b / 1e6), "records_per_day": recs.get(k).and_then(|r| r.as_f64()).map(|r| (r * scale).round()),
        "mb_per_day": bytes.get(k).and_then(|b| b.as_f64()).map(|b| (b * scale / 1e6 * 10.0).round() / 10.0)}))).collect();
    let rep = serde_json::json!({"run": run.display().to_string(), "hours": files.len() as f64 / 12.0, "pace": pace, "lines": lines, "bad_lines": bad, "exec_txs": n_exec, "trades": n_trades,
        "watched_fails": n_fail, "raw_txs": n_raw, "wall_s_fed": t_fed.as_secs_f64(), "wall_s_total": t_all.as_secs_f64(), "producer_waits": waits,
        "hook_us": {"p50": fq(0.5), "p99": fq(0.99), "max": feed_us.last()},
        "observatory": end, "rss_mb_start": rss0 / 1024, "rss_mb_max_sampled": rss_max / 1024, "vm_hwm_mb": hwm / 1024, "obs_mem_est_mb": mem_est, "parts": parts.len(), "per_module": per_mod});
    let rp = out_dir.join("soak_report.json");
    std::fs::write(&rp, serde_json::to_string_pretty(&rep).unwrap()).unwrap();
    println!("{}", serde_json::to_string_pretty(&rep).unwrap());
    eprintln!("-> {}", rp.display());
}

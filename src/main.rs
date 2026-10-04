//! arb-lab: a minimal arbitrage bot built to answer one question: which data feed and which send path make us money.
//!   input       every feed at once (raw UDP shreds, DoubleZero multicast, ShredStream gRPC, Yellowstone deshred / tx)
//!   processing  decode swaps on watched pools, predict the pool after the swap, look for a profitable round trip
//!   output      shadow mode: record every decision with per-feed arrival times and our own stage timings
//!   send paths  `send`: Jito bundles (gRPC) and JSON-RPC, Helius Sender, Shyft, RPC Fast Beam, Haan, Bolt, Iris,
//!               Lunar Lander; `arb-lab senders` checks them without sending
mod build;
mod config;
mod engine;
mod exec;
mod feeds;
mod lat;
mod pda;
mod pools;
mod record;
mod rpc;
mod send;
mod store;
mod tx;
mod wallet;
mod venues;

use anyhow::{Context, Result};
use clap::{Parser, Subcommand};
use feeds::clock::now_ns;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

#[derive(Parser)]
#[command(version, about)]
struct Cli { #[command(subcommand)] cmd: Cmd }

#[derive(Subcommand)]
enum Cmd {
    /// Check a config file and print what it would run
    Check { #[arg(long, default_value = "arb.toml")] config: PathBuf },
    /// Boot the pools from chain and print the registry (no feeds)
    Pools { #[arg(long, default_value = "arb.toml")] config: PathBuf },
    /// Check every enabled send path WITHOUT sending a transaction: build it (jito-bundle: connect, authenticate, compare
    /// tip accounts with the block engine's), then time keep-alive round trips. With --raw, also send that signed
    /// transaction through the paths and follow the bundle results (this spends its fee and tips if it lands).
    Senders {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        #[arg(long, default_value_t = 5)] rounds: u32,
        /// only these send paths (comma-separated)
        #[arg(long)] only: Option<String>,
        /// file with one signed transaction, base64
        #[arg(long)] raw: Option<PathBuf>,
        /// seconds to follow bundle results after --raw
        #[arg(long, default_value_t = 10)] wait: u64,
        /// also send each path 4 junk bytes (never a transaction: nothing lands, nothing is paid) to see whether its
        /// key is accepted (a decode error) or rejected (an auth error)
        #[arg(long)] probe: bool,
    },
    /// Replay the engine's RPC pattern (concurrent single-table fetches) against every provider and print why calls fail
    RpcTest {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        #[arg(long, default_value_t = 300)] calls: usize,
        #[arg(long, default_value_t = 30)] concurrency: usize,
    },
    /// Create durable-nonce accounts owned by the wallet (seeds `arb-nonce-<i>`, i from --from); prints their addresses.
    /// Spends their rent (about 0.00145 SOL each, recoverable by closing) and fees.
    Nonces {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        #[arg(long, default_value_t = 0)] from: u32,
        #[arg(long)] count: u32,
    },
    /// Move SOL into the wallet's WSOL account (created if missing): the trading capital the arbitrage program spends.
    /// Shows the plan and asks you to type the amount again before signing.
    Wrap { #[arg(long, default_value = "arb.toml")] config: PathBuf, #[arg(long)] sol: f64 },
    /// Encrypt a secret key into a keystore file: the key comes on stdin (solana-keygen JSON or base58), the
    /// passphrase from the terminal (asked twice, no echo). Prints the public key only. Run it on your own machine.
    /// With --generate, a brand-new key is made in memory instead (nothing on stdin, no plaintext anywhere); with
    /// --show-backup its base58 secret is printed once so you can keep an offline paper copy.
    KeystoreEncrypt { #[arg(long)] out: PathBuf, #[arg(long)] generate: bool, #[arg(long)] show_backup: bool },
    /// Check a keystore file: asks the passphrase, prints the public key it unlocks to
    KeystoreCheck { #[arg(long)] file: PathBuf },
    /// Unlock the trading keystore and check it is the config's wallet (prints the public key only)
    Wallet { #[arg(long, default_value = "arb.toml")] config: PathBuf },
    /// STEP 2 without feeds: build one real round trip per pool pair (pools as they are now) and simulate it, unsigned.
    /// Nothing is sent. Writes <out_dir>/simcheck-<time>/sims.jsonl and prints what the chain said, by venue pair.
    Simcheck {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        #[arg(long, default_value_t = 40)] max: usize,
        #[arg(long, default_value_t = 0.01)] size_sol: f64,
        /// then send this many canaries on probe routes (needs [canary] enabled too): the whole live path end to end
        #[arg(long, default_value_t = 0)] canaries: u32,
    },
    /// Run the engine (shadow mode: decide and record, never send)
    Run {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        #[arg(long)] minutes: Option<f64>,
        #[arg(long)] name: Option<String>,
        /// only these feeds (comma-separated)
        #[arg(long)] only: Option<String>,
        /// send the canaries `[canary]` describes (real transactions built to fail our profit check; fees only)
        #[arg(long)] canary: bool,
        /// trade for real (`[live]` limits); needs mode = "live" in the config too
        #[arg(long)] live: bool,
        /// run in shadow whatever the config's mode (recorded in meta.json `overrides`; WP-01 keeps this flag)
        #[arg(long)] shadow: bool,
        /// this run without the recorder (`[record] enabled = false`; recorded in meta.json `overrides`): WP-00's
        /// recorder-off shadow run, without editing the config
        #[arg(long)] no_record: bool,
    },
}

fn load_env(config: &Path) {
    let dir = config.parent().filter(|p| !p.as_os_str().is_empty()).unwrap_or(Path::new("."));
    let _ = dotenvy::from_path(dir.join(".env"));
}

fn utc_stamp() -> String {
    let s = now_ns() / 1_000_000_000;
    let (d, r) = (s / 86_400, s % 86_400);
    // civil date from days since 1970-01-01
    let z = d as i64 + 719_468;
    let era = z.div_euclid(146_097);
    let doe = z - era * 146_097;
    let yoe = (doe - doe / 1460 + doe / 36_524 - doe / 146_096) / 365;
    let doy = doe - (365 * yoe + yoe / 4 - yoe / 100);
    let mp = (5 * doy + 2) / 153;
    let day = doy - (153 * mp + 2) / 5 + 1;
    let month = if mp < 10 { mp + 3 } else { mp - 9 };
    let year = yoe + era * 400 + if month <= 2 { 1 } else { 0 };
    format!("{year:04}{month:02}{day:02}-{:02}{:02}{:02}", r / 3600, r % 3600 / 60, r % 60)
}

fn main() -> Result<()> {
    match Cli::parse().cmd {
        Cmd::Check { config } => {
            let cfg = config::Config::load(&config)?;
            println!("mode {}, wallet {}, {} feeds, {} send paths", cfg.mode, cfg.wallet, cfg.feeds.len(), cfg.sends.len());
            for f in &cfg.feeds { println!("  feed {:<20} {:?}{}", f.name, f.kind, if f.enabled { "" } else { " (disabled)" }); }
            for s in &cfg.sends {
                let tip = match (s.tip_share, s.tip_lamports) { (Some(x), l) => format!("{:.0}% of the edge, {l}..{} lamports", x * 100.0, s.tip_max_lamports.unwrap_or(u64::MAX)), (None, 0) => "no tip".into(), (None, l) => format!("tip {l} lamports") };
                let rate = s.max_per_sec.map(|n| format!(", max {n}/s")).unwrap_or_default();
                println!("  send {:<20} {:?} {tip}{rate}{}", s.name, s.kind, if s.enabled { "" } else { " (disabled)" });
            }
            if cfg.gate.enabled { println!("  jito gate on: paid copies wait up to {} ms for the bundle's first result (canary every {})", cfg.gate.wait_ms, cfg.gate.canary_every); }
            let on: Vec<&str> = cfg.sends.iter().filter(|s| s.enabled).map(|s| s.name.as_str()).collect();
            println!("enabled send paths: {}", if on.is_empty() { "none".to_string() } else { on.join(", ") });
            let (s, l) = (&cfg.strategy, &cfg.live);
            println!("safety: decoded_sends {}, skip_failing_signers {}, state_triggers {}, record {}; live: max {} SOL a trade, {} new token accounts, sim_gate {}, bundle_mix {} (tpu_max_expected {}), big band >= {} lamports at {}/s, crowded pools {}",
                s.decoded_sends, s.skip_failing_signers, s.state_triggers, cfg.record.enabled, l.max_size_sol, l.max_new_token_accounts, l.sim_gate, l.bundle_mix,
                l.tpu_max_expected_lamports, l.big_band_min_expected_lamports, l.big_band_max_per_sec,
                if l.crowded_pools_file.is_empty() { "none".to_string() } else { l.crowded_pools_file.clone() });
            if l.crowded_skip_min_expected_lamports > 0 { println!("  crowded pools not sent from {} lamports expected", l.crowded_skip_min_expected_lamports); }
            // review N3: the crowded list, where this machine has it (the configured path, or the repo's data/ copy)
            if !l.crowded_pools_file.is_empty() {
                let p = Path::new(&l.crowded_pools_file);
                let repo_copy = config.parent().and_then(|d| d.parent()).zip(p.file_name()).map(|(d, f)| d.join("data").join(f));
                match std::iter::once(p.to_path_buf()).chain(repo_copy).find(|c| c.is_file()) {
                    Some(c) => println!("  crowded list {}: {} pools", c.display(), exec::load_crowded_pools(&c.to_string_lossy())?.len()),
                    None => println!("  crowded list not on this machine (loaded at start; a bad list stops the run)"),
                }
            }
            if let Some(w) = cfg.pricing_warning() { println!("{w}"); }
            Ok(())
        }
        Cmd::Pools { config } => {
            load_env(&config);
            let cfg = config::Config::load(&config)?;
            let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
            rt.block_on(async {
                let (eps, skipped) = cfg.rpc.endpoints();
                if eps.is_empty() { anyhow::bail!("no RPC provider configured (skipped: {skipped:?})"); }
                let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover);
                let (cands, seeds, ours) = pools::candidates(&cfg.pools)?;
                let reg = pools::boot(&rpc, &cands, seeds, ours).await?;
                println!("{} candidates -> {}", cands.len(), reg.summary());
                for (k, v) in &reg.pairs {
                    let mint = if k.0 == *venues::WSOL { k.1 } else { k.0 };
                    let names: Vec<String> = v.iter().map(|&i| format!("{:?}:{}", reg.pools[i].venue, pools::show(&reg.pools[i].pool))).collect();
                    println!("  {} {}", pools::show(&mint), names.join(" "));
                }
                Ok(())
            })
        }
        Cmd::Run { config, minutes, name, only, canary, live, shadow, no_record } => run(&config, minutes, name, only, canary, live, Overrides { shadow, no_record }),
        Cmd::Simcheck { config, max, size_sol, canaries } => simcheck(&config, max, size_sol, canaries),
        Cmd::KeystoreEncrypt { out, generate, show_backup } => {
            use std::io::Read;
            if out.exists() { anyhow::bail!("{} exists: not overwriting", out.display()); }
            let secret = if generate {
                let mut seed = [0u8; 32];
                std::fs::File::open("/dev/urandom")?.read_exact(&mut seed)?;
                let k = ed25519_dalek::SigningKey::from_bytes(&seed);
                seed.fill(0);
                let mut b = k.to_bytes().to_vec(); b.extend_from_slice(k.verifying_key().as_bytes());
                let s = bs58::encode(&b).into_string();
                b.fill(0);
                s
            } else {
                let mut input = String::new();
                std::io::stdin().read_to_string(&mut input)?;
                let s = wallet::secret_to_b58(&input)?;
                input.clear();
                s
            };
            let p1 = wallet::prompt_pass("passphrase: ")?;
            let p2 = wallet::prompt_pass("again: ")?;
            if p1 != p2 { anyhow::bail!("the passphrases differ"); }
            if p1.len() < 16 { anyhow::bail!("use a passphrase of at least 16 characters"); }
            let blob = wallet::encrypt(&secret, &p1, wallet::V3_LOG_N)?;
            let key = wallet::keypair(&wallet::decrypt(&blob, &p1)?)?;
            if out.exists() { anyhow::bail!("{} exists: not overwriting", out.display()); }
            use std::os::unix::fs::OpenOptionsExt;
            let mut f = std::fs::OpenOptions::new().write(true).create_new(true).mode(0o600).open(&out)?;
            std::io::Write::write_all(&mut f, blob.as_bytes())?;
            println!("wrote {} (scrypt 2^{}): wallet {}", out.display(), wallet::V3_LOG_N, bs58::encode(key.verifying_key().as_bytes()).into_string());
            if show_backup { println!("BACKUP (base58 secret key; copy to paper, then clear this terminal): {secret}"); }
            Ok(())
        }
        Cmd::KeystoreCheck { file } => {
            let blob = std::fs::read_to_string(&file)?;
            let pass = wallet::prompt_pass("passphrase: ")?;
            let key = wallet::keypair(&wallet::decrypt(&blob, &pass)?)?;
            println!("{} unlocks to wallet {}", file.display(), bs58::encode(key.verifying_key().as_bytes()).into_string());
            Ok(())
        }
        Cmd::Wallet { config } => {
            let cfg = config::Config::load(&config)?;
            let k = wallet::load_cfg(&cfg)?;
            println!("keystore {} unlocks to {} = the config's wallet", cfg.wallet_profile, bs58::encode(k.verifying_key().as_bytes()).into_string());
            Ok(())
        }
        Cmd::Nonces { config, from, count } => nonces(&config, from, count),
        Cmd::Wrap { config, sol } => wrap(&config, sol),
        Cmd::RpcTest { config, calls, concurrency } => rpc_test(&config, calls, concurrency),
        Cmd::Senders { config, rounds, only, raw, wait, probe } => senders(&config, rounds, only, raw, wait, probe),
    }
}

/// every token of the registry's pools, with its token program (the wallet's possible token accounts)
fn reg_mints(reg: &pools::Registry) -> Vec<(tx::Pk, tx::Pk)> {
    reg.pools.iter().flat_map(|m| [(m.t0, m.t0_prog), (m.t1, m.t1_prog)]).collect()
}

fn wrap(config: &Path, sol: f64) -> Result<()> {
    use base64::Engine as _;
    load_env(config);
    let cfg = config::Config::load(config)?;
    let lamports = (sol * 1e9).round() as u64;
    if lamports == 0 { anyhow::bail!("--sol must be > 0"); }
    // the config's own providers, the [exec] ones (Helius expired 2026-10-03: no hard-wired RPC)
    let (eps, _) = cfg.rpc.endpoints();
    let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover).only(&cfg.exec.rpc);
    if rpc.is_empty() { anyhow::bail!("no [exec] rpc provider available: check [exec] rpc and .env"); }
    let payer: tx::Pk = tx::pk(&cfg.wallet);
    let wsol = tx::pk("So11111111111111111111111111111111111111112");
    let ata = build::ata_of(&payer, &wsol, &pda::TOKEN_PROGRAM);
    let rt = tokio::runtime::Runtime::new()?;
    let bal = rt.block_on(rpc.call("getBalance", serde_json::json!([cfg.wallet])))?["value"].as_u64().unwrap_or(0);
    println!("wallet {}  SOL balance {:.6}\nwrap {:.6} SOL into its WSOL account {}", cfg.wallet, bal as f64 / 1e9, sol, tx::b58(&ata));
    if lamports + 3_000_000 > bal { anyhow::bail!("not enough SOL: keep at least 0.003 SOL for the account rent and fees"); }
    let typed = wallet::prompt_visible(&format!("type {sol} to confirm (shown as you type), then the passphrase is asked: "))?;
    if typed.trim().parse::<f64>().ok() != Some(sol) { anyhow::bail!("not confirmed: you typed {:?}, expected {sol}", typed.trim()); }
    let key = wallet::load_cfg(&cfg)?;
    rt.block_on(async {
        let ixs = vec![build::create_ata_idempotent_ix(payer, payer, wsol, *pda::TOKEN_PROGRAM), build::transfer_ix(payer, ata, lamports), build::sync_native_ix(ata)];
        let (bh, _) = rpc.latest_blockhash().await?;
        let msg = build::compile_v0(payer, &ixs, bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
        let raw = build::sign(&msg, &key);
        let sig = rpc.call("sendTransaction", serde_json::json!([base64::engine::general_purpose::STANDARD.encode(&raw), { "encoding": "base64", "preflightCommitment": "processed" }])).await?;
        println!("sent {sig}");
        for _ in 0..30 {
            tokio::time::sleep(std::time::Duration::from_millis(500)).await;
            if let Ok(v) = rpc.call("getTokenAccountBalance", serde_json::json!([tx::b58(&ata)])).await {
                if let Some(a) = v["value"]["amount"].as_str() { if a.parse::<u64>().unwrap_or(0) >= lamports { println!("WSOL account now holds {} SOL", a.parse::<u64>().unwrap_or(0) as f64 / 1e9); return anyhow::Ok(()); } }
            }
        }
        println!("not confirmed after 15 s; check the signature");
        anyhow::Ok(())
    })
}

fn nonces(config: &Path, from: u32, count: u32) -> Result<()> {
    use base64::Engine as _;
    load_env(config);
    let cfg = config::Config::load(config)?;
    let key = wallet::load_cfg(&cfg)?;
    let payer: tx::Pk = key.verifying_key().to_bytes();
    let rt = tokio::runtime::Runtime::new()?;
    // the config's own providers, the [exec] ones (Helius expired 2026-10-03: no hard-wired RPC)
    let (eps, _) = cfg.rpc.endpoints();
    let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover).only(&cfg.exec.rpc);
    if rpc.is_empty() { anyhow::bail!("no [exec] rpc provider available: check [exec] rpc and .env"); }
    rt.block_on(async {
        let rent = rpc.call("getMinimumBalanceForRentExemption", serde_json::json!([80])).await?.as_u64().context("rent")?;
        for i in from..from + count {
            let seed = format!("arb-nonce-{i}");
            let (addr, ixs) = build::create_nonce_ixs(payer, &seed, rent);
            if let (_, v) = rpc.accounts(&[addr]).await? { if v.first().map_or(false, |a| a.is_some()) { println!("{seed} {} exists", tx::b58(&addr)); continue; } }
            let (bh, _) = rpc.latest_blockhash().await?;
            let msg = build::compile_v0(payer, &ixs, bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
            let raw = build::sign(&msg, &key);
            let sig = rpc.call("sendTransaction", serde_json::json!([base64::engine::general_purpose::STANDARD.encode(&raw), { "encoding": "base64", "preflightCommitment": "processed" }])).await?;
            let mut done = false;
            for _ in 0..30 {
                tokio::time::sleep(std::time::Duration::from_millis(500)).await;
                if let (_, v) = rpc.accounts(&[addr]).await? { if v.first().map_or(false, |a| a.is_some()) { done = true; break; } }
            }
            println!("{seed} {} {} ({sig})", tx::b58(&addr), if done { "created" } else { "NOT SEEN after 15 s" });
        }
        anyhow::Ok(())
    })
}

fn simcheck(config: &Path, max: usize, size_sol: f64, canaries: u32) -> Result<()> {
    load_env(config);
    let mut cfg = config::Config::load(config)?;
    cfg.sim.enabled = true;
    if canaries > 0 && !cfg.canary.enabled { anyhow::bail!("--canaries needs [canary] enabled = true in the config too"); }
    let key = if canaries > 0 { Some((exec::Kind::Canary, wallet::load_cfg(&cfg)?)) } else { None };
    let dir = PathBuf::from(&cfg.out_dir).join(format!("simcheck-{}", utc_stamp()));
    std::fs::create_dir_all(&dir)?;
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
    let (eps, _) = cfg.rpc.endpoints();
    let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover);
    let fetch = |store: &mut store::Store, keys: &[tx::Pk]| -> Result<()> {
        let (slot, accts) = rt.block_on(rpc.accounts(keys))?;
        for (k, a) in keys.iter().zip(accts) { if let Some(a) = a { store.update(*k, a.data, slot, now_ns(), None); } }
        Ok(())
    };
    let (cands, seeds, ours) = pools::candidates(&cfg.pools)?;
    let reg = rt.block_on(pools::boot(&rpc, &cands, seeds, ours))?;
    let mut store = store::Store::default();
    fetch(&mut store, &reg.static_accounts())?;
    engine::initial_dlmm_arrays(&reg, &mut store);
    let arr: Vec<tx::Pk> = store.dlmm_arrays.values().flatten().map(|x| x.1).collect();
    fetch(&mut store, &arr)?;
    println!("booted: {}", reg.summary());
    let (tx, rx) = crossbeam_channel::unbounded::<feeds::Event>();
    let (wtx, _) = tokio::sync::watch::channel(Vec::new());
    let paths = if canaries > 0 {
        let (p, notes) = rt.block_on(send::Paths::new(&cfg.sends, cfg.gate.clone(), Some(&dir), true))?;
        for n in notes { println!("send path {n}"); }
        p.start(Arc::new(AtomicBool::new(false)), std::time::Duration::from_secs(30), |m: String| println!("  {m}"));
        Some(p)
    } else { None };
    let (x, notes) = rt.block_on(exec::Exec::new(&cfg, &rpc, paths.clone(), &dir, tx.clone(), vec![], key, reg_mints(&reg)))?;
    for n in notes { println!("exec: {n}"); }
    let mut eng = engine::Engine::new(Arc::new(reg), store, cfg.strategy.clone(), vec![], 0, Arc::new(engine::interest(&engine_dummy_registry(), None)), &dir, rpc.clone(),
        rt.handle().clone(), tx, wtx)?;
    eng.exec = Some(x);
    let routes = eng.probe_routes((size_sol * 1e9) as u64, max);
    for r in &routes { let r2 = eng.refresh_route(r); if let Some(r2) = r2 { eng.exec.as_mut().unwrap().simulate(r2); } std::thread::sleep(std::time::Duration::from_millis(500)); }
    println!("{} simulations sent; waiting for the answers ...", routes.len());
    std::thread::sleep(std::time::Duration::from_secs(8));
    let text = std::fs::read_to_string(dir.join("sims.jsonl")).unwrap_or_default();
    let mut by: std::collections::BTreeMap<String, (u32, u32, std::collections::BTreeMap<String, u32>)> = Default::default();
    let mut good: Vec<(String, String)> = Vec::new();
    for l in text.lines() {
        let v: serde_json::Value = serde_json::from_str(l)?;
        let key = format!("{} -> {}", v["buy_venue"].as_str().unwrap_or("?"), v["sell_venue"].as_str().unwrap_or("?"));
        let e = by.entry(key).or_default();
        e.0 += 1;
        if v["encoding_ok"].as_bool() == Some(true) { e.1 += 1; good.push((v["buy_pool"].as_str().unwrap_or("").into(), v["sell_pool"].as_str().unwrap_or("").into())); }
        let why = v["build_error"].as_str().map(|b| format!("build: {}", b.split('(').next().unwrap_or(b)))
            .or_else(|| v["sim_error"].as_str().map(|e| format!("rpc: {}", &e[..e.len().min(60)])))
            .unwrap_or_else(|| format!("{} {}", v["code"].as_str().unwrap_or(""), v["meaning"].as_str().unwrap_or("")));
        *e.2.entry(why).or_default() += 1;
    }
    for (k, (n, ok, why)) in &by { println!("{k:<22} {ok}/{n} encoding ok   {why:?}"); }
    // canaries on routes whose simulation ran every leg: refresh both pools, build, sign, send to every path, settle
    let mut sent = 0;
    for r in routes.iter().filter(|r| good.contains(&(tx::b58(&r.buy.pool), tx::b58(&r.sell.pool)))) {
        if sent >= canaries { break; }
        let keys = eng.route_accounts(r);
        fetch(&mut eng.store, &keys)?;
        let Some(fresh) = eng.refresh_route(r) else { continue };
        let x = eng.exec.as_mut().unwrap();
        if x.wants_send().is_none() { println!("canary: not allowed now ({})", x.status()); break; }
        println!("canary {sent}: {:?} -> {:?}, {} lamports ...", fresh.buy.venue, fresh.sell.venue, fresh.size);
        x.send(fresh);
        sent += 1;
        match rx.recv_timeout(std::time::Duration::from_secs(cfg.canary.settle_s + 40)) {
            Ok(feeds::Event::Settled(s)) => { x.on_settled(*s, &|_| None); }
            Ok(_) | Err(_) => { println!("canary {}: not settled in time", sent - 1); break; }
        }
        let last = std::fs::read_to_string(dir.join("outcomes.jsonl")).unwrap_or_default();
        if let Some(l) = last.lines().last() {
            let v: serde_json::Value = serde_json::from_str(l)?;
            println!("  landed via {}  slot {}  {} {}  fee {}  copies: {}", v["landed"], v["slot"], v["code"], v["meaning"], v["fee_lamports"],
                v["copies"].as_array().map(|a| a.iter().map(|c| format!("{}={}{}", c["path"].as_str().unwrap_or("?"), if c["accepted"].as_bool() == Some(true) { "accepted" } else { "REFUSED" },
                    c["status"].as_u64().map(|s| format!("({s})")).unwrap_or_default())).collect::<Vec<_>>().join(" ")).unwrap_or_default());
            println!("  jito: {}", v["jito"]);
        }
        std::thread::sleep(std::time::Duration::from_secs(2));
    }
    println!("written to {}", dir.display());
    Ok(())
}

/// an empty registry for the simcheck engine's feed filter (no feeds run)
fn engine_dummy_registry() -> pools::Registry {
    pools::Registry { pools: vec![], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() }
}

fn senders(config: &Path, rounds: u32, only: Option<String>, raw: Option<PathBuf>, wait: u64, probe: bool) -> Result<()> {
    load_env(config);
    let mut cfg = config::Config::load(config)?;
    if let Some(only) = &only {
        let want: Vec<&str> = only.split(',').map(str::trim).collect();
        for s in &mut cfg.sends { s.enabled = want.contains(&s.name.as_str()); }
    }
    let enabled: Vec<config::SendPath> = cfg.sends.iter().filter(|s| s.enabled).cloned().collect();
    if enabled.is_empty() { anyhow::bail!("no enabled send path"); }
    let raw = raw.map(|p| -> Result<Vec<u8>> {
        use base64::Engine as _;
        let text = std::fs::read_to_string(&p).with_context(|| format!("reading {}", p.display()))?;
        Ok(base64::engine::general_purpose::STANDARD.decode(text.trim()).context("--raw: not base64")?)
    }).transpose()?;
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).thread_name("arb-io").enable_all().build()?;
    rt.block_on(async {
        // each path on its own, so one that fails does not hide the others
        let mut bad = 0;
        for s in &enabled {
            match send::Paths::new(std::slice::from_ref(s), config::GateCfg::default(), None, false).await.map(|x| x.0) {
                Err(e) => { bad += 1; println!("{:<18} FAILED: {e:#}", s.name); }
                Ok(ps) => {
                    let p = &ps.list[0];
                    let mut ms = Vec::new();
                    for _ in 0..rounds {
                        match p.warm().await {
                            Ok(Some(d)) => ms.push(d.as_secs_f64() * 1e3),
                            Ok(None) => {}
                            Err(e) => { println!("{:<18} keep-alive error: {e:#}", s.name); break; }
                        }
                        tokio::time::sleep(std::time::Duration::from_secs(1)).await;
                    }
                    let warm = ms.iter().skip(1).copied().fold(f64::INFINITY, f64::min);
                    let jito = p.jito.as_ref().map(|j| format!("; authenticated as {}", j.pubkey())).unwrap_or_default();
                    println!("{:<18} ok  {}  tip {}{jito}; keep-alive cold {} warm best {}", s.name, p.describe(),
                        p.tip(0).map(|(_, l)| format!("{l} lamports")).unwrap_or_else(|| "none".into()),
                        ms.first().map(|x| format!("{x:.1} ms")).unwrap_or_else(|| "-".into()),
                        if warm.is_finite() { format!("{warm:.1} ms") } else { "-".into() });
                    if probe { println!("{:<18} probe: {}", "", p.probe().await); }
                }
            }
        }
        let Some(raw) = raw else { if bad > 0 { anyhow::bail!("{bad} send path(s) failed") } return Ok(()) };
        let dir = PathBuf::from(&cfg.out_dir).join(format!("send-{}", utc_stamp()));
        std::fs::create_dir_all(&dir).with_context(|| format!("creating {}", dir.display()))?;
        let (ps, _) = send::Paths::new(&enabled, cfg.gate.clone(), Some(&dir), false).await?;
        let stop = Arc::new(AtomicBool::new(false));
        ps.start(stop.clone(), std::time::Duration::from_secs(30), |m: String| println!("  {m}"));
        let copies = (0..ps.list.len()).map(|i| send::Copy { path: i, raw: Arc::new(raw.clone()), tip: None }).collect();
        let fired = ps.fire(0, copies, send::Prio::default(), true).await?;
        if let Some(g) = &fired.gate { println!("gate: {}", serde_json::to_string(g)?); }
        for c in &fired.copies {
            println!("  {:<16} {:>7.1} ms  {} {}", c.path, c.ms, if c.ok { "ok" } else { "REFUSED" }, c.reply.as_deref().unwrap_or("-"));
        }
        if ps.list.iter().any(|p| p.jito.is_some()) {
            println!("following bundle results for {wait} s ...");
            tokio::time::sleep(std::time::Duration::from_secs(wait)).await;
        }
        stop.store(true, Ordering::Relaxed);
        for l in ps.summary() { println!("  {l}"); }
        println!("written to {}", dir.display());
        Ok(())
    })
}

/// lookup tables real traders use (from templates.json): the engine's most common RPC request is fetching one
fn sample_tables(path: Option<&str>, n: usize) -> Vec<tx::Pk> {
    let Some(p) = path else { return vec![] };
    let Ok(t) = std::fs::read_to_string(p) else { return vec![] };
    let Ok(v) = serde_json::from_str::<serde_json::Value>(&t) else { return vec![] };
    let mut out = Vec::new();
    for x in v.as_object().into_iter().flat_map(|o| o.values()) {
        for a in x["alts"].as_array().into_iter().flatten() {
            if let Some(k) = a.as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|b| tx::Pk::try_from(b).ok()) { if !out.contains(&k) { out.push(k); } }
            if out.len() >= n { return out; }
        }
    }
    out
}

fn rpc_test(config: &Path, calls: usize, concurrency: usize) -> Result<()> {
    load_env(config);
    let cfg = config::Config::load(config)?;
    let (eps, skipped) = cfg.rpc.endpoints();
    println!("providers: {} (skipped: {skipped:?})", eps.iter().map(|e| e.name.clone()).collect::<Vec<_>>().join(", "));
    let tables = sample_tables(cfg.pools.templates_json.as_deref(), calls);
    anyhow::ensure!(!tables.is_empty(), "no lookup tables found in templates_json");
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
    rt.block_on(async {
        let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover);
        let sem = Arc::new(tokio::sync::Semaphore::new(concurrency));
        let mut tasks = Vec::new();
        for i in 0..calls {
            let (rpc, t, sem) = (rpc.clone(), tables[i % tables.len()], sem.clone());
            tasks.push(tokio::spawn(async move { let _p = sem.acquire().await; let _ = rpc.accounts(&[t]).await; }));
        }
        for t in tasks { let _ = t.await; }
        tokio::time::sleep(std::time::Duration::from_secs(3)).await; // let slower providers finish
        for l in rpc.summary() { println!("{l}"); }
        println!("failure reasons:");
        for l in rpc.reasons(4) { println!("  {l}"); }
        anyhow::Ok(())
    })
}

/// command-line changes to the config for one run, recorded in meta.json `overrides`
#[derive(Clone, Copy, Default)]
struct Overrides { shadow: bool, no_record: bool }

impl Overrides {
    /// apply them; Err when they contradict the other flags
    fn apply(&self, cfg: &mut config::Config, live: bool) -> Result<()> {
        if self.shadow {
            if live { anyhow::bail!("--shadow and --live contradict each other"); }
            cfg.mode = "shadow".into();
        }
        if self.no_record { cfg.record.enabled = false; }
        Ok(())
    }

    fn json(&self) -> serde_json::Value {
        let mut v = serde_json::Map::new();
        if self.shadow { v.insert("mode".into(), "shadow".into()); }
        if self.no_record { v.insert("record.enabled".into(), false.into()); }
        v.into()
    }
}

/// meta.json `limits` (MEASUREMENT §4.2, v1.1): the effective safety limits of this run
fn limits_json(cfg: &config::Config, live: bool, canary: bool) -> serde_json::Value {
    let l = &cfg.live;
    serde_json::json!({
        "sending": if live { "live" } else if canary { "canary" } else { "none" },
        "max_size_sol": l.max_size_sol, "max_size_src": "config", "sim_max_size_sol": cfg.exec.max_size_sol,
        "max_failed_fees_lamports": l.max_failed_fees_lamports, "max_new_token_accounts": l.max_new_token_accounts,
        "decoded_sends": cfg.strategy.decoded_sends, "state_triggers": cfg.strategy.state_triggers,
        "big_band_min_expected_lamports": l.big_band_min_expected_lamports, "big_band_max_per_sec": l.big_band_max_per_sec,
        "crowded_pools_file": l.crowded_pools_file, "crowded_skip_min_expected_lamports": l.crowded_skip_min_expected_lamports,
        "record": cfg.record.enabled,
    })
}

fn run(config: &Path, minutes: Option<f64>, name: Option<String>, only: Option<String>, canary: bool, live: bool, ov: Overrides) -> Result<()> {
    load_env(config);
    let mut cfg = config::Config::load(config)?;
    ov.apply(&mut cfg, live)?;
    // live trading needs both mode = "live" and --live; either alone refuses to start (so neither can spend by itself)
    if live != (cfg.mode == "live") { anyhow::bail!("live trading needs mode = \"live\" in the config AND --live (got mode {}, --live {live}; --shadow runs a live config in shadow)", cfg.mode); }
    if let Some(w) = cfg.pricing_warning() { println!("{w}"); }
    if live && canary { anyhow::bail!("--live and --canary are separate runs"); }
    if canary && !cfg.canary.enabled { anyhow::bail!("--canary needs [canary] enabled = true in the config (both, so neither alone can spend)"); }
    if cfg.canary.enabled && !canary { println!("[canary] is enabled in the config but --canary was not given: no canaries this run"); }
    // the trading key is read only when something will really be sent, and must be the config's wallet
    let send_key = if live || canary { Some((if live { exec::Kind::Live } else { exec::Kind::Canary }, wallet::load_cfg(&cfg)?)) } else { None };
    let exec_on = cfg.sim.enabled || canary || live;
    // every entries-feed transaction on its leader's PoH clock (poh.log), whenever we build or send
    let poh_log_on = exec_on;
    if let Some(only) = &only {
        let want: Vec<&str> = only.split(',').map(str::trim).collect();
        for f in &mut cfg.feeds { f.enabled = want.contains(&f.name.as_str()); }
    }
    let dir = PathBuf::from(&cfg.out_dir).join(name.unwrap_or_else(utc_stamp));
    std::fs::create_dir_all(&dir).with_context(|| format!("creating {}", dir.display()))?;
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).thread_name("arb-io").enable_all().build()?;
    let stop = Arc::new(AtomicBool::new(false));
    {
        let stop = stop.clone();
        rt.spawn(async move {
            let mut term = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate()).expect("signal");
            tokio::select! { _ = tokio::signal::ctrl_c() => {}, _ = term.recv() => {} }
            stop.store(true, Ordering::Relaxed);
        });
    }
    let (eps, skipped) = cfg.rpc.endpoints();
    if eps.is_empty() { anyhow::bail!("no RPC provider configured (skipped: {skipped:?})"); }
    let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover);
    let state_token = config::env_token(&cfg.state.token_env, "state")?;
    // pools, then a first snapshot of every followed account
    let (reg, mut store) = rt.block_on(async {
        let (cands, seeds, ours) = pools::candidates(&cfg.pools)?;
        let reg = pools::boot(&rpc, &cands, seeds, ours).await?;
        let mut store = store::Store::default();
        let keys = reg.static_accounts();
        let (slot, accts) = rpc.accounts(&keys).await?;
        for (k, a) in keys.iter().zip(accts) { if let Some(a) = a { store.update(*k, a.data, slot, now_ns(), None); } }
        engine::initial_dlmm_arrays(&reg, &mut store);
        let arr: Vec<tx::Pk> = store.dlmm_arrays.values().flatten().map(|x| x.1).collect();
        let (slot, accts) = rpc.accounts(&arr).await?;
        for (k, a) in arr.iter().zip(accts) { if let Some(a) = a { store.update(*k, a.data, slot, now_ns(), None); } }
        anyhow::Ok((reg, store))
    })?;
    let reg = Arc::new(reg);
    let mut log = std::fs::OpenOptions::new().create(true).append(true).open(dir.join("run.log"))?;
    let mut say = |s: &str| { use std::io::Write; println!("{s}"); let _ = writeln!(log, "{} {s}", now_ns()); };
    say(&format!("booted: {}; {} accounts held", reg.summary(), store.accts.len()));
    say(&format!("rpc providers raced: {} (skipped, env missing: {:?})", rpc.names().join(", "), skipped));
    let mut interest = engine::interest(&reg, cfg.pools.templates_json.as_deref());
    // our own transactions (canaries): every feed forwards them, so we see when each one appears
    if exec_on { interest.keys.insert(tx::pk(&cfg.wallet)); }
    let interest = Arc::new(interest);
    say(&format!("interest: {} keys, {} lookup tables", interest.keys.len(), interest.tables.read().unwrap().len()));
    let (tx, rx) = crossbeam_channel::unbounded::<feeds::Event>();
    let mut list: Vec<String> = reg.static_accounts().iter().map(tx::b58).collect();
    for l in store.dlmm_arrays.values() { for (_, k) in l { list.push(tx::b58(k)); } }
    say(&format!("state stream follows {} accounts", list.len()));
    let (wtx, wrx) = tokio::sync::watch::channel(list);
    if poh_log_on { let _ = feeds::POH_LOG.set(std::sync::Mutex::new(std::io::BufWriter::with_capacity(1 << 20, std::fs::File::create(dir.join("poh.log"))?))); }
    if cfg.record.enabled {
        let archive = cfg.feeds.iter().filter(|f| f.enabled).position(|f| f.name == cfg.record.archive_feed).map(|i| i as u16);
        record::init(&dir, archive)?;
        say(&format!("recording: rivals, executed results, arrivals, moves, slots{}", if archive.is_some() { format!(", raw entries of {}", cfg.record.archive_feed) } else { String::new() }));
    }
    let fs = feeds::start(&cfg.feeds, interest.clone(), tx.clone(), stop.clone(), rt.handle())?;
    feeds::start_state(cfg.state.url.clone(), state_token, wrx, tx.clone(), stop.clone(), rt.handle());
    say(&format!("feeds: {}", fs.names.join(", ")));
    // STEP 1: every send path kept warm and timed (keepalive.jsonl); paths that can't be built are named, not fatal
    let paths = if cfg.sends.iter().any(|s| s.enabled) {
        let (p, notes) = rt.block_on(send::Paths::new(&cfg.sends, cfg.gate.clone(), Some(&dir), true))?;
        for n in notes { say(&format!("send path {n}")); }
        let back = tx.clone();
        p.start(stop.clone(), std::time::Duration::from_secs(cfg.exec.keepalive_s), move |m: String| { let _ = back.send(feeds::Event::Status { feed: u16::MAX, msg: m }); });
        say(&format!("send paths: {} (keep-alive every {} s)", p.list.iter().map(|x| x.name.as_str()).collect::<Vec<_>>().join(", "), cfg.exec.keepalive_s));
        Some(p)
    } else { None };
    // STEPS 2-3: simulation of every would-send decision, canaries
    let exec = if exec_on {
        let (x, notes) = rt.block_on(exec::Exec::new(&cfg, &rpc, paths.clone(), &dir, tx.clone(), fs.names.clone(), send_key, reg_mints(&reg)))?;
        for n in notes { say(&format!("exec: {n}")); }
        if !cfg.live.crowded_pools_file.is_empty() {
            // review N1: a list made for another registry would rank and skip nothing
            let (have, all) = x.crowded_in(|p| reg.by_pool.contains_key(p));
            say(&format!("exec: crowded pools in this registry: {have} of {all}"));
        }
        say(&format!("exec: simulation {}, canaries {}", if cfg.sim.enabled { format!("on (at most {}/s)", cfg.sim.max_per_sec) } else { "off".into() },
            if canary { format!("ARMED ({} max, cap {} lamports)", cfg.canary.count, cfg.canary.max_spend_lamports) } else { "off".into() }));
        if live { say(&format!("exec: LIVE TRADING: at most {} SOL a trade, stops after {} lamports of failed fees", cfg.live.max_size_sol, cfg.live.max_failed_fees_lamports)); }
        Some(x)
    } else { None };
    std::fs::write(dir.join("meta.json"), serde_json::to_string_pretty(&serde_json::json!({
        "started_ns": now_ns(), "feeds": fs.names, "strategy": format!("{:?}", cfg.strategy), "pools": reg.summary(),
        "wallet": cfg.wallet, "send_paths": paths.as_ref().map(|p| p.list.iter().map(|x| x.name.clone()).collect::<Vec<_>>()),
        "gate": format!("{:?}", cfg.gate), "sim": format!("{:?}", cfg.sim), "canary": if canary { Some(format!("{:?}", cfg.canary)) } else { None },
        "live": if live { Some(format!("{:?}", cfg.live)) } else { None },
        "exec": format!("{:?}", cfg.exec),
        // the effective safety limits (WP-00; MEASUREMENT §4.2 `limits`): the trade size is the owner's Stage-0 decision (OD-4)
        "limits": limits_json(&cfg, live, canary),
        // what the command line changed in the config for this run (--shadow, --no-record)
        "overrides": ov.json(),
    }))?)?;
    let min_tip = cfg.sends.iter().filter(|s| s.enabled).map(|s| s.tip_lamports).min().unwrap_or(0);
    let mut eng = engine::Engine::new(reg.clone(), store, cfg.strategy.clone(), fs.names.clone(), min_tip, interest, &dir, rpc,
        rt.handle().clone(), tx.clone(), wtx)?;
    eng.exec = exec;
    let until = minutes.map(|m| now_ns() + (m * 60e9) as u64).unwrap_or(u64::MAX);
    let counters = fs.counters.clone();
    let names = fs.names.clone();
    let rpc_stats = eng.rpc_handle();
    let mut ticks = 0u64;
    eng.run(&rx, &stop, until, |s| {
        let per: Vec<String> = names.iter().zip(&counters).map(|(n, c)| format!("{n} {}/{}", c.forwarded.load(Ordering::Relaxed), c.txs.load(Ordering::Relaxed))).collect();
        say(&format!("{s} | fwd/txs: {}", per.join(", ")));
        ticks += 1;
        if ticks % 6 == 0 {
            for l in rpc_stats.summary() { say(&format!("rpc {l}")); }
            for l in rpc_stats.reasons(2) { say(&format!("rpc failure {l}")); }
            if let Some(p) = &paths { for l in p.summary() { say(&format!("send {l}")); } }
        }
    });
    for l in rpc_stats.summary() { say(&format!("rpc final {l}")); }
    for l in rpc_stats.reasons(5) { say(&format!("rpc failure {l}")); }
    if let Some(p) = &paths { for l in p.summary() { say(&format!("send final {l}")); } }
    if let Some(x) = &eng.exec { say(&format!("exec final {}", x.status())); }
    stop.store(true, Ordering::Relaxed);
    if let Some(r) = record::get() { r.finish(); }
    say(&format!("done: {}", dir.display()));
    rt.shutdown_timeout(std::time::Duration::from_secs(2));
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn stage0() -> config::Config { config::Config::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-stage0.toml")).unwrap() }

    /// review F8 (d): meta.json `limits` carries the WP-00 limits (MEASUREMENT §7 v1.1)
    #[test]
    fn meta_limits_carry_the_stage0_limits() {
        let cfg = stage0();
        let l = limits_json(&cfg, true, false);
        assert_eq!(l["sending"], "live");
        assert_eq!(limits_json(&cfg, false, false)["sending"], "none");
        assert_eq!(limits_json(&cfg, false, true)["sending"], "canary");
        assert_eq!((l["max_size_sol"].as_f64(), l["max_new_token_accounts"].as_u64(), l["max_size_src"].as_str()), (Some(4.2), Some(0), Some("config")));
        assert_eq!((l["decoded_sends"].as_bool(), l["state_triggers"].as_bool(), l["record"].as_bool()), (Some(false), Some(true), Some(true)));
        assert_eq!((l["big_band_min_expected_lamports"].as_u64(), l["big_band_max_per_sec"].as_f64()), (Some(1_000_000), Some(0.5)));
        assert_eq!((l["crowded_pools_file"].as_str(), l["crowded_skip_min_expected_lamports"].as_u64()), (Some("/root/arbx/data/crowded-pools.json"), Some(100_000)));
    }

    /// review F1: both field-acceptance shadow runs work on the shipped file without editing it, and `--shadow` runs a
    /// live config in shadow
    #[test]
    fn shadow_and_no_record_overrides() {
        let mut cfg = stage0();
        Overrides::default().apply(&mut cfg, false).unwrap();
        assert_eq!(cfg.mode, "shadow", "ships in shadow: a plain run is a shadow run");
        assert!(cfg.record.enabled);
        let ov = Overrides { shadow: false, no_record: true };
        ov.apply(&mut cfg, false).unwrap();
        assert!(!cfg.record.enabled, "the recorder-off run");
        assert_eq!(ov.json(), serde_json::json!({ "record.enabled": false }));
        let mut live = stage0();
        live.mode = "live".into();
        let ov = Overrides { shadow: true, no_record: false };
        ov.apply(&mut live, false).unwrap();
        assert_eq!(live.mode, "shadow");
        assert_eq!(ov.json(), serde_json::json!({ "mode": "shadow" }));
        assert!(Overrides { shadow: true, no_record: false }.apply(&mut stage0(), true).is_err(), "--shadow with --live");
        assert_eq!(Overrides::default().json(), serde_json::json!({}));
    }
}

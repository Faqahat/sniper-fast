//! arbx: the command line over the arbx library (src/lib.rs). An atomic, self-funded Solana arbitrage bot built to
//! measure which data feed and which send path make money, and to trade only round trips that revert unless profitable.
//!   input       every feed at once (raw UDP shreds, DoubleZero multicast, ShredStream gRPC, Yellowstone deshred / tx)
//!   processing  follow watched pools, look for a profitable round trip
//!   output      shadow mode: record every decision with per-feed arrival times and our own stage timings
//!   send paths  `send`: Jito bundles (gRPC) and JSON-RPC paths; `arbx senders` checks them without sending
//!   provenance  every run writes meta.json (build, config and program hashes) and stop.json (why it stopped);
//!               `arbx ctl` drives a running segment through its control socket
use anyhow::{Context, Result};
use arbx::control::{self, StopInfo, StopReason};
use arbx::feeds::clock::now_ns;
use arbx::{build, chainfetch, config, engine, exec, feeds, leaders, pda, pools, probe, provenance, reads, rec, rpc, runtime, send, store, tx, venues, wallet};
use clap::{Parser, Subcommand};
use serde_json::{json, Value};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;

#[derive(Parser)]
#[command(version = concat!(env!("CARGO_PKG_VERSION"), " (git ", env!("ARBX_GIT_COMMIT"), ", dirty ", env!("ARBX_GIT_DIRTY"), ", ", env!("ARBX_PROFILE"), ")"), about)]
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
    /// Run the engine (shadow mode: decide and record, never send). Writes meta.json (provenance) before the feeds
    /// start and stop.json (why it stopped) at the end. Exit code: 0 deadline, 10 operator stop (signal, control
    /// socket), 20 safety stop, 30 error
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
        /// run in shadow whatever the config's mode (meta.json `run.forced_shadow` and `overrides`; the SendGate is
        /// shadow with reason `forced_shadow`). Refused with --live
        #[arg(long)] shadow: bool,
        /// what is left of the campaign's failed-fee budget, lamports: this segment's `[live] max_failed_fees_lamports` is
        /// the smaller of this and the config's (deploy/run-w.sh passes it, so the frozen config is never edited)
        #[arg(long)] budget_left: Option<u64>,
        /// the campaign directory (deploy/run-w.sh): the segment's directory is <campaign-dir>/<name>, and meta.json
        /// compares this config with the campaign's frozen one (campaign.json)
        #[arg(long)] campaign_dir: Option<PathBuf>,
        /// the .env file to load (default: `.env` beside the config). The supervisor runs the campaign's frozen config
        /// copy and names the .env of the config it froze (a path, never a secret)
        #[arg(long)] env_file: Option<PathBuf>,
    },
    /// Print the provenance of this binary and a config without starting anything: build (git commit, dirty state,
    /// rustc), the binary's sha256, the config's file and normalized sha256, host and clock; unless --offline, also the
    /// route and venue programs' ELF hashes (RPC, read-only)
    Provenance {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        /// no RPC: skip the programs
        #[arg(long)] offline: bool,
    },
    /// Send a command to a running segment through its control socket (<run>/control.sock): status, pause-sending,
    /// resume-sending, shadow (for the rest of the segment) or stop. Every command is logged in <run>/control.jsonl.
    /// Exit code 0 accepted, 2 refused
    Ctl {
        /// the segment's run directory
        #[arg(long)] run: PathBuf,
        /// status | pause-sending | resume-sending | shadow | stop
        cmd: String,
        /// who sends it
        #[arg(long)] who: String,
        /// why (required for every command but status)
        #[arg(long, default_value = "")] why: String,
    },
    /// What the configured gRPC provider accepts (PLAN WP-03 item 5): subscribes, one after the other, to each
    /// subscription the plan needs (the full accounts filter, interslot slots, blocks_meta, transaction filters of 1, 2
    /// and 5 accounts, blocks of the venue programs, the deshred filter with 5 programs) for --seconds each, and writes
    /// probe.json (`[state] probe_file`, default <out_dir>/probe.json) and a dated copy. Sends no transaction. Refuses
    /// to start while a segment or campaign may hold the provider (Haan serves the first process only), and holds the
    /// campaign supervisor's lock while it runs. A 503 / Unavailable result is inconclusive: probe.json is then not
    /// replaced and the exit code is 3
    GrpcProbe {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        #[arg(long, default_value_t = 30.0)] seconds: f64,
        /// where to write probe.json (default: `[state] probe_file`, else <out_dir>/probe.json)
        #[arg(long)] out: Option<PathBuf>,
        /// only these subscriptions (comma-separated names)
        #[arg(long)] only: Option<String>,
        /// probe even though a segment, a campaign or another bot process may hold the provider
        #[arg(long)] force: bool,
    },
    /// Fold segments' signer statistics into the shared file (PLAN-ADDENDUM I-5): each run directory's
    /// `signer-stats-delta.json` (that segment's own counts) is added to --into, written atomically; a merged run is
    /// marked (`signer-stats.merged.json`) and refused a second time, and a run without `stop.json` (still running) is
    /// refused. Runs never write the shared file themselves
    SignerStats {
        /// merge (the only action)
        action: String,
        #[arg(long)] into: PathBuf,
        /// run directories
        runs: Vec<PathBuf>,
    },
    /// (tests) install `run`'s signal handler, control socket and stop path, without feeds or RPC; print "ready <pid>",
    /// wait for a stop, write stop.json and exit with its code
    #[command(hide = true)]
    WaitSignal {
        #[arg(long)] dir: PathBuf,
        #[arg(long)] minutes: Option<f64>,
        /// panic on the main thread once ready (the panic path of the stop)
        #[arg(long)] panic: bool,
        /// fail with an error once stopped (a crash during shutdown: stop.json `secondary`, exit 30)
        #[arg(long)] fail_after_stop: bool,
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
            let (cfg, raw) = config::Config::load_raw(&config)?;
            println!("config_version {}, sha256 {}, normalized {}", config::CONFIG_VERSION, provenance::sha256_hex(&raw), cfg.normalized_sha256());
            println!("mode {}, wallet {}, {} feeds, {} send paths", cfg.mode, cfg.wallet, cfg.feeds.len(), cfg.sends.len());
            for f in &cfg.feeds { println!("  feed {:<20} {:?}{}", f.name, f.kind, if f.enabled { "" } else { " (disabled)" }); }
            for t in &cfg.state.tx_streams {
                println!("  tx stream {:<15} yellowstone-tx on {} include {:?}{}{}", t.name, provenance::host_of(t.url.as_deref().unwrap_or(&cfg.state.url)), t.account_include,
                    t.max_accounts.map(|m| format!(" (max {m})")).unwrap_or_default(), if t.enabled { "" } else { " (disabled)" });
            }
            let st = &cfg.state;
            println!("state stream {}: watch clock {}, programdata {}, wallet {}; slot statuses {}, block meta {}", provenance::host_of(&st.url), st.watch_clock,
                st.watch_programdata, st.watch_wallet, st.slot_statuses, st.block_meta);
            if cfg.leaders.enabled { println!("leaders: lists {:?} every {} min, static fallback {}", cfg.leaders.validator_lists, cfg.leaders.refresh_min, cfg.leaders.static_fallback); }
            // WP-04: state consistency, the state-health gate (I-4), lookup-table retries (I-6), the accuracy monitor
            println!("state consistency: commit timeout {} ms, quiescence {} ms, part skew <= {} slots, tip lag <= {} slots, clock <= {} slots; lag SLO p50 {} / p90 {} ms ({}); stop if no state update within {} s, price nothing past {} ms without one, re-read after every connection {} (warn {} s, give up {} s); {}",
                st.commit_timeout_ms, st.quiescence_ms, st.max_part_skew_slots, st.max_tip_lag_slots, st.clock_max_age_slots, st.lag_slo_p50_ms, st.lag_slo_p90_ms, st.slo_action,
                st.boot_timeout_s, st.max_update_age_ms, st.resnapshot, st.resync_warn_s, st.resync_give_up_s,
                if st.unavailable_stop_s == 0 { "an outage after the first message does not stop the run".to_string() } else { format!("stop after {} s unavailable", st.unavailable_stop_s) });
            println!("lookup tables: retries {:?} ms then every {} s, give up after {} s, at most {} waiting, {} fetches at once, preload {:?} (used in the last {} h, at most {}); accuracy {} ({} versions per account)",
                cfg.alts.retry_ms, cfg.alts.retry_every_s, cfg.alts.give_up_s, cfg.alts.wait_cap, cfg.alts.max_inflight, cfg.alts.preload, cfg.alts.preload_max_age_h,
                cfg.alts.preload_max_tables, cfg.accuracy.action, cfg.accuracy.ring_versions);
            // WP-03b: the providers' budgets (every client of the process) and the chain-fetch roles
            let cf = &cfg.chainfetch;
            let all: Vec<String> = cfg.rpc.url_env.iter().map(|_| "default".to_string()).chain(cfg.rpc.endpoints.iter().filter(|e| e.enabled).map(|e| e.name.clone())).collect();
            let budgets: Vec<String> = all.iter().map(|n| match cf.limit_of(n) { (r, _) if r > 0.0 => format!("{n} {r}/s"), _ => format!("{n} unlimited") }).collect();
            println!("rpc budgets: {}; boot retries for {} s", budgets.join(", "), cf.boot_retry_s);
            println!("chain fetch {}: after {} ms, backfill rps {}, backlog {}, sample every {} s, blockhash poll {} ms, sigs every {} s, tx version {}; roles {}", if cf.enabled { "on" } else { "off" },
                cf.after_ms, cf.rps.fixed().map_or("auto".to_string(), |r| format!("{r}/s")), cf.max_backlog, cf.sample_every_s, cf.blockhash_poll_ms, cf.sigs_every_s, cf.max_tx_version,
                rpc::Role::FETCH.iter().map(|r| format!("{}={}", r.as_str(), cf.providers_for(r.as_str(), &all).join("+"))).collect::<Vec<_>>().join(" "));
            for s in &cfg.sends {
                let tip = match (s.tip_share, s.tip_lamports) { (Some(x), l) => format!("{:.0}% of the edge, {l}..{} lamports", x * 100.0, s.tip_max_lamports.unwrap_or(u64::MAX)), (None, 0) => "no tip".into(), (None, l) => format!("tip {l} lamports") };
                let rate = s.max_per_sec.map(|n| format!(", max {n}/s")).unwrap_or_default();
                println!("  send {:<20} {:?} {tip}{rate}{}", s.name, s.kind, if s.enabled { "" } else { " (disabled)" });
            }
            if cfg.gate.enabled { println!("  jito gate on: paid copies wait up to {} ms for the bundle's first result (canary every {})", cfg.gate.wait_ms, cfg.gate.canary_every); }
            let on: Vec<&str> = cfg.sends.iter().filter(|s| s.enabled).map(|s| s.name.as_str()).collect();
            println!("enabled send paths: {}", if on.is_empty() { "none".to_string() } else { on.join(", ") });
            let (s, l) = (&cfg.strategy, &cfg.live);
            println!("safety: decoded swaps are hints only, skip_failing_signers {}, state_triggers {}; live: max {} SOL a trade, {} new token accounts, sim_gate {}, bundle_mix {} (tpu_max_expected {}), big band >= {} lamports at {}/s, crowded pools {}",
                s.skip_failing_signers, s.state_triggers, l.max_size_sol, l.max_new_token_accounts, l.sim_gate, l.bundle_mix,
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
            let e = &cfg.exec;
            println!("route program {}: {}", e.program, if e.expected_program_sha256.is_empty() && e.expected_program_md5.is_empty() { "no expected hash (recorded, not checked)".to_string() }
                else { format!("expected sha256 {} md5 {} (checked at start; a mismatch refuses live sends)", e.expected_program_sha256, e.expected_program_md5) });
            println!("control socket {}", if cfg.control.socket { "on" } else { "off" });
            let r = &cfg.record;
            println!("recorder (always on): disk budget {} GB per segment, min free {} GB, rotate at {} MiB or {} min, frames every {} ms, zstd {}, archived feeds {}; background runtime {} threads",
                r.disk_budget_gb, r.min_free_gb, r.rotate_mb, r.rotate_min, r.flush_ms, r.zstd_level,
                if r.archive_feeds.is_empty() { "none".to_string() } else { r.archive_feeds.join(",") }, cfg.runtime.bg_threads);
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
        Cmd::Run { config, minutes, name, only, canary, live, shadow, budget_left, campaign_dir, env_file } => {
            let a = RunArgs { config, minutes, name, only, canary, live, ov: Overrides { shadow, budget_left }, campaign_dir, env_file };
            let sess = control::Session::new();
            control::install_panic_hook(sess.clone());
            let res = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| run(&a, &sess)));
            std::process::exit(end_run(&sess, res))
        }
        Cmd::WaitSignal { dir, minutes, panic, fail_after_stop } => {
            let sess = control::Session::new();
            control::install_panic_hook(sess.clone());
            let res = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| wait_signal(&dir, minutes, panic, fail_after_stop, &sess)));
            std::process::exit(end_run(&sess, res))
        }
        Cmd::Provenance { config, offline } => {
            load_env(&config);
            let (cfg, raw) = config::Config::load_raw(&config)?;
            let programs = if offline { None } else {
                let (eps, skipped) = cfg.rpc.endpoints();
                if eps.is_empty() { eprintln!("no RPC provider available (skipped: {skipped:?}): programs not read"); None } else {
                    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
                    let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover);
                    Some(rt.block_on(provenance::fetch_programs(&rpc, &provenance::program_specs(&cfg))))
                }
            };
            println!("{}", serde_json::to_string_pretty(&provenance::report(&config, &raw, &cfg, programs))?);
            Ok(())
        }
        Cmd::Ctl { run, cmd, who, why } => {
            let r = control::send_command(&run, &cmd, &who, &why)?;
            println!("{}", serde_json::to_string_pretty(&r)?);
            if r["accepted"].as_bool() != Some(true) { std::process::exit(2); }
            Ok(())
        }
        Cmd::Simcheck { config, max, size_sol, canaries } => simcheck(&config, max, size_sol, canaries),
        Cmd::SignerStats { action, into, runs } => {
            anyhow::ensure!(action == "merge", "signer-stats: the only action is `merge`");
            anyhow::ensure!(!runs.is_empty(), "signer-stats merge: name the run directories");
            for (r, signers, n) in engine::merge_signer_stats(&into, &runs)? { println!("{r}: {signers} signers, {n} outcomes added to {}", into.display()); }
            Ok(())
        }
        Cmd::GrpcProbe { config, seconds, out, only, force } => grpc_probe(&config, seconds, out, only, force),
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

/// `arbx grpc-probe` (PLAN WP-03 item 5): what the state stream's provider (and each deshred feed) accepts
fn grpc_probe(config: &Path, seconds: f64, out: Option<PathBuf>, only: Option<String>, force: bool) -> Result<()> {
    load_env(config);
    let cfg = config::Config::load(config)?;
    if !(seconds > 0.0) { anyhow::bail!("--seconds must be > 0"); }
    // review WP-03 #4 (PLAN-ADDENDUM I-3): Haan gives its streams to the first process only. A probe run beside a segment
    // learns nothing (503 everywhere), and one started first blinds a segment that reconnects meanwhile
    let runs = PathBuf::from(&cfg.out_dir);
    let busy = probe::busy(&runs, true);
    let lock = probe::lock_runs(&runs);
    if !force {
        let mut why = busy.clone();
        if let Err(e) = &lock { why.push(format!("{e:#}")); }
        if !why.is_empty() {
            anyhow::bail!("the provider may be in use (Haan serves the first process only, PLAN-ADDENDUM I-3): {}. Probe when nothing runs, or pass --force", why.join("; "));
        }
    } else if !busy.is_empty() || lock.is_err() {
        println!("--force: probing although the provider may be in use ({}); expect inconclusive results", busy.len() + lock.is_err() as usize);
    }
    let target = |url: &str, token_env: &Option<String>, header: &Option<String>, what: &str| -> Result<probe::Target> {
        Ok(probe::Target { url: url.to_string(), token: config::env_token(token_env, what)?, header: header.clone() })
    };
    let state = target(&cfg.state.url, &cfg.state.token_env, &None, "state")?;
    // the accounts filter's keys: the candidate pools (no RPC), the clock, the wallet and the programs' programdata,
    // padded to the full list's estimated size (pools with their vaults and extras, the wallet's token accounts)
    let (cands, _, _) = pools::candidates(&cfg.pools)?;
    let loader = tx::pk(provenance::UPGRADEABLE_LOADER);
    let mut keys: Vec<String> = cands.iter().map(|c| tx::b58(&c.1)).collect();
    keys.push(tx::b58(&pools::CLOCK_SYSVAR));
    keys.push(cfg.wallet.clone());
    for p in provenance::program_specs(&cfg) { keys.push(tx::b58(&pda::find_program_address(&[&p.id], &loader).0)); }
    let n = (4 * cands.len()).max(probe::MIN_ACCOUNTS);
    let accounts = probe::pad_accounts(&keys, n);
    let venue_programs: Vec<String> = provenance::venue_specs().iter().map(|p| tx::b58(&p.id)).collect();
    let mut deshred = Vec::new();
    for f in cfg.feeds.iter().filter(|f| f.enabled && f.kind == config::FeedKind::YellowstoneDeshred) {
        if let Some(u) = &f.url { deshred.push((f.name.clone(), target(u, &f.token_env, &f.token_header, &f.name)?)); }
    }
    let plan = probe::Plan { state, accounts, venue_programs, deshred };
    let only: Option<Vec<String>> = only.map(|o| o.split(',').map(|x| x.trim().to_string()).collect());
    println!("probing {} for {seconds} s per subscription ({} accounts in the accounts filter) ...", provenance::host_of(&cfg.state.url), plan.accounts.len());
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
    let subs = rt.block_on(probe::probe(&plan, std::time::Duration::from_secs_f64(seconds), only.as_deref()));
    drop(lock);
    for s in &subs {
        let what = match s.verdict { "accepted" if s.messages_30s == 0 => "SILENT", "accepted" => "accepted", "refused" => "REFUSED", _ => "INCONCLUSIVE" };
        println!("  {:<24} {:<12} {:>6} msgs  first {:>8}  {}{}", s.sub, what, s.messages_30s,
            s.first_msg_ms.map(|m| format!("{m:.0} ms")).unwrap_or_else(|| "-".into()), s.host, s.error.as_ref().map(|e| format!("  ({e})")).unwrap_or_default());
    }
    let v = probe::probe_json(&plan, &subs);
    let path = out.unwrap_or_else(|| if cfg.state.probe_file.is_empty() { PathBuf::from(&cfg.out_dir).join("probe.json") } else { PathBuf::from(&cfg.state.probe_file) });
    if let Some(d) = path.parent().filter(|d| !d.as_os_str().is_empty()) { std::fs::create_dir_all(d)?; }
    let text = serde_json::to_string_pretty(&v)?;
    let bad = probe::inconclusive(&subs);
    if !bad.is_empty() {
        // an inconclusive probe never replaces a conclusive one (`auto` reads probe.json)
        let dated = path.with_file_name(format!("probe-{}-inconclusive.json", &utc_stamp()[..15]));
        control::write_atomic(&dated, text.as_bytes())?;
        eprintln!("{} of {} subscriptions inconclusive ({}): the provider was busy or down (503 / Unavailable: another process holding Haan, I-3, or an outage, I-2). \
            {} not replaced; this result is in {}. Probe again when nothing else uses the provider",
            bad.len(), subs.len(), bad.iter().map(|s| format!("{} {}", s.sub, s.code.as_deref().unwrap_or("no gRPC answer"))).collect::<Vec<_>>().join(", "), path.display(), dated.display());
        std::process::exit(3);
    }
    control::write_atomic(&path, text.as_bytes())?;
    let dated = path.with_file_name(format!("probe-{}.json", &utc_stamp()[..8]));
    control::write_atomic(&dated, text.as_bytes())?;
    println!("wrote {} and {} (copy it into docs/ and record the result in PLAN §9)", path.display(), dated.display());
    Ok(())
}

fn simcheck(config: &Path, max: usize, size_sol: f64, canaries: u32) -> Result<()> {
    load_env(config);
    let mut cfg = config::Config::load(config)?;
    cfg.sim.enabled = true;
    if canaries > 0 && !cfg.canary.enabled { anyhow::bail!("--canaries needs [canary] enabled = true in the config too"); }
    let key = if canaries > 0 { Some((exec::Kind::Canary, wallet::load_cfg(&cfg)?)) } else { None };
    let name = format!("simcheck-{}", utc_stamp());
    let dir = PathBuf::from(&cfg.out_dir).join(&name);
    let rec = tool_recorder(&dir, &name)?;
    // review N5: closed on an error too (its unflushed tail is kept)
    let _rec_guard = RecGuard(rec.clone());
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build()?;
    let (eps, _) = cfg.rpc.endpoints();
    let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover);
    let fetch = |store: &mut store::Store, keys: &[tx::Pk]| -> Result<()> {
        let (slot, accts) = rt.block_on(rpc.accounts(keys))?;
        for (k, a) in keys.iter().zip(accts) { if let Some(a) = a { store.update(*k, a.data.into(), slot, now_ns(), None); } }
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
        let (p, notes) = rt.block_on(send::Paths::new(&cfg.sends, cfg.gate.clone(), rec.clone(), true))?;
        for n in notes { println!("send path {n}"); }
        p.start(Arc::new(AtomicBool::new(false)), std::time::Duration::from_secs(30), |m: String| println!("  {m}"));
        Some(p)
    } else { None };
    let (x, notes) = rt.block_on(exec::Exec::new(&cfg, &rpc, paths.clone(), rec.clone(), tx.clone(), vec![], key, reg_mints(&reg)))?;
    for n in notes { println!("exec: {n}"); }
    let mut eng = engine::Engine::new(Arc::new(reg), store, cfg.strategy.clone(), vec![], 0, Arc::new(engine::interest(&engine_dummy_registry(), None)), rec.clone(), rpc.clone(),
        rt.handle().clone(), tx, wtx)?;
    eng.exec = Some(x);
    let routes = eng.probe_routes((size_sol * 1e9) as u64, max);
    for r in &routes { let r2 = eng.refresh_route(r); if let Some(r2) = r2 { eng.exec.as_mut().unwrap().simulate(r2); } std::thread::sleep(std::time::Duration::from_millis(500)); }
    println!("{} simulations sent; waiting for the answers ...", routes.len());
    std::thread::sleep(std::time::Duration::from_secs(8));
    rec.sync();
    let mut by: std::collections::BTreeMap<String, (u32, u32, std::collections::BTreeMap<String, u32>)> = Default::default();
    let mut good: Vec<(String, String)> = Vec::new();
    for v in rec::read_jsonl(&dir, "sims")? {
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
        rec.sync();
        if let Some(v) = rec::read_jsonl(&dir, "outcomes")?.last() {
            println!("  landed via {}  slot {}  {} {}  fee {}  copies: {}", v["landed"], v["slot"], v["code"], v["meaning"], v["fee_lamports"],
                v["copies"].as_array().map(|a| a.iter().map(|c| format!("{}={}{}", c["path"].as_str().unwrap_or("?"), if c["accepted"].as_bool() == Some(true) { "accepted" } else { "REFUSED" },
                    c["status"].as_u64().map(|s| format!("({s})")).unwrap_or_default())).collect::<Vec<_>>().join(" ")).unwrap_or_default());
            println!("  jito: {}", v["jito"]);
        }
        std::thread::sleep(std::time::Duration::from_secs(2));
    }
    rec.close();
    println!("written to {}", dir.display());
    Ok(())
}

/// The recorder of a tool's own directory (simcheck, senders --raw): the run's streams, no monitor thread
fn tool_recorder(dir: &Path, name: &str) -> Result<rec::Rec> {
    let producer = provenance::build_json()["binary_sha256"].as_str().map(|h| h[..16].to_string()).unwrap_or_else(|| "unknown".into());
    rec::start(rec::Opts { dir: dir.to_path_buf(), run: name.to_string(), producer, cfg: config::RecordCfg::default(), feeds: vec![], monitor: false, echo: None })
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
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).thread_name("arbx-io").enable_all().build()?;
    rt.block_on(async {
        // each path on its own, so one that fails does not hide the others
        let mut bad = 0;
        for s in &enabled {
            match send::Paths::new(std::slice::from_ref(s), config::GateCfg::default(), rec::Rec::off(), false).await.map(|x| x.0) {
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
        let name = format!("send-{}", utc_stamp());
        let dir = PathBuf::from(&cfg.out_dir).join(&name);
        let rec = tool_recorder(&dir, &name)?;
        let _rec_guard = RecGuard(rec.clone());
        let (ps, _) = send::Paths::new(&enabled, cfg.gate.clone(), rec.clone(), false).await?;
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
        rec.close();
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

/// command-line changes to the config for one run, recorded in meta.json `overrides` (WP-02: `--no-record` is gone,
/// recording cannot be turned off)
#[derive(Clone, Copy, Default)]
struct Overrides { shadow: bool, budget_left: Option<u64> }

impl Overrides {
    /// apply them; Err when they contradict the other flags
    fn apply(&self, cfg: &mut config::Config, live: bool, canary: bool) -> Result<()> {
        if self.shadow {
            if live { anyhow::bail!("--shadow and --live contradict each other"); }
            // review M7: --shadow never sends, so a canary run under it would unlock the key and arm canaries for nothing
            if canary { anyhow::bail!("--shadow and --canary contradict each other (--shadow never sends)"); }
            cfg.mode = "shadow".into();
        }
        // the supervisor's budget never raises the config's own cap (res-stops: sed used to overwrite it)
        if let Some(b) = self.budget_left { cfg.live.max_failed_fees_lamports = cfg.live.max_failed_fees_lamports.min(b); }
        Ok(())
    }

    fn json(&self) -> serde_json::Value {
        let mut v = serde_json::Map::new();
        if self.shadow { v.insert("mode".into(), "shadow".into()); }
        if let Some(b) = self.budget_left { v.insert("budget_left_lamports".into(), b.into()); }
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
        "decoded_sends": false, "state_triggers": cfg.strategy.state_triggers,
        // WP-04: prices only committed, complete, canonical state; nothing priced or sent while the state is unavailable
        "state_gate": { "boot_timeout_s": cfg.state.boot_timeout_s, "max_update_age_ms": cfg.state.max_update_age_ms },
        "big_band_min_expected_lamports": l.big_band_min_expected_lamports, "big_band_max_per_sec": l.big_band_max_per_sec,
        "crowded_pools_file": l.crowded_pools_file, "crowded_skip_min_expected_lamports": l.crowded_skip_min_expected_lamports,
        // WP-02: always on
        "record": true,
    })
}

/// `arbx run`'s arguments
struct RunArgs { config: PathBuf, minutes: Option<f64>, name: Option<String>, only: Option<String>, canary: bool, live: bool, ov: Overrides, campaign_dir: Option<PathBuf>,
    env_file: Option<PathBuf> }

/// A run's config: `cfg` with the command line applied (what the run uses); `config_json` (meta.json `config`) hashes
/// the file as loaded, before the overrides (review F2: the normalized hash is the same in every segment of a campaign,
/// whatever `--budget-left` or `--shadow` say, and equals `arbx provenance`'s); `config_cap` is the
/// file's failed-fee cap
struct RunConfig { cfg: config::Config, raw: Vec<u8>, config_json: Value, config_cap: u64 }

fn run_config(a: &RunArgs) -> Result<RunConfig> {
    let (loaded, raw) = config::Config::load_raw(&a.config)?;
    let mut config_json = provenance::config_json(&a.config, &raw, &loaded, Some("config.toml"), a.campaign_dir.as_deref());
    let config_cap = loaded.live.max_failed_fees_lamports;
    let mut cfg = loaded;
    a.ov.apply(&mut cfg, a.live, a.canary)?;
    config_json["effective_mode"] = json!(cfg.mode);
    Ok(RunConfig { cfg, raw, config_json, config_cap })
}

/// The SendGate a run starts with (review M3): `--shadow` makes it shadow for the whole segment (`forced_shadow`); so
/// does a run without `--live` or `--canary`, which sends nothing anyway (`mode_shadow`); a live or canary run starts live
fn initial_gate(gate: &control::SendGate, forced_shadow: bool, live: bool, canary: bool) {
    if forced_shadow { let _ = gate.shadow("forced_shadow", "--shadow", true); }
    else if !live && !canary { let _ = gate.shadow("mode_shadow", "no --live or --canary: nothing is sent", true); }
}

/// The route program's check, applied to the gate before anything can send: a route program whose hash differs from
/// `[exec] expected_program_*`, or could not be read (`route_check` fails closed), keeps a live or canary run in shadow
/// for the whole segment (`program_hash_mismatch`); a shadow run only records it. Returns the run.log lines
fn apply_route_check(gate: &control::SendGate, check: Option<(bool, String)>, live: bool, canary: bool) -> Vec<String> {
    match check {
        Some((true, line)) => vec![format!("provenance: {line}: ok")],
        Some((false, line)) => {
            let mut v = vec![format!("provenance: {line}: MISMATCH")];
            if live || canary {
                let _ = gate.shadow("program_hash_mismatch", &line, true);
                v.push("provenance: NOT SENDING this segment (program_hash_mismatch): it runs and records in shadow".into());
            }
            v
        }
        None => vec!["provenance: no [exec] expected_program_sha256/md5: the route program is recorded, not checked".into()],
    }
}

/// the segment's directory: `<campaign-dir>/<name>` in a campaign (MEASUREMENT §1.1), else `<out_dir>/<name>`
fn run_dir(out_dir: &str, campaign_dir: Option<&Path>, name: &str) -> PathBuf {
    match campaign_dir { Some(c) => c.join(name), None => PathBuf::from(out_dir).join(name) }
}

/// The end of `run` / `wait-signal`: the stop reason they set, or error / panic; stop.json; the exit code. An error or
/// panic after a stop request keeps that reason, is stop.json `secondary`, and exits 30 (review M5)
fn end_run(sess: &control::Session, res: std::thread::Result<Result<()>>) -> i32 {
    match res {
        Ok(Ok(())) => sess.finish(StopInfo::new(StopReason::Error, "the run ended without a stop reason")),
        Ok(Err(e)) => {
            let msg = rpc::scrub(&format!("{e:#}"));
            // a failing stderr must not turn the error into a panic before stop.json is written (review F2)
            rec::err_line(&format!("Error: {msg}"));
            sess.fail(StopInfo::new(StopReason::Error, msg))
        }
        Err(_) => {
            let info = StopInfo::new(StopReason::Panic, sess.last_panic().map(|p| rpc::scrub(&p)).unwrap_or_else(|| "panic".into()));
            // a main-thread panic already went through the panic hook (`last_panic` set, stop.json written)
            if sess.last_panic().is_some() { sess.finish(info) } else { sess.fail(info) }
        }
    }
}

/// `arbx wait-signal` (tests): `run`'s signal handler, control socket and stop path, nothing else. `fail_after_stop`:
/// return an error once stopped (a crash during shutdown)
fn wait_signal(dir: &Path, minutes: Option<f64>, panic: bool, fail_after_stop: bool, sess: &Arc<control::Session>) -> Result<()> {
    std::fs::create_dir_all(dir)?;
    sess.set_dir(dir.to_path_buf());
    control::install_signals(sess.clone())?;
    let _ctl = control::serve(sess.clone(), dir)?;
    {
        use std::io::Write;
        println!("ready {}", std::process::id());
        std::io::stdout().flush()?;
    }
    if panic { panic!("wait-signal --panic: a test panic"); }
    let until = minutes.map(|m| now_ns() + (m * 60e9) as u64).unwrap_or(u64::MAX);
    while !sess.stopper.stopping() {
        if now_ns() >= until { sess.stopper.request(StopInfo::new(StopReason::Deadline, "--minutes reached")); break; }
        std::thread::sleep(std::time::Duration::from_millis(5));
    }
    // no executor: nothing was in flight, and the drain fields say so by being null (review M11)
    *sess.drain.lock().unwrap() = control::Drain::default();
    if fail_after_stop { anyhow::bail!("wait-signal --fail-after-stop: a test failure while stopping"); }
    Ok(())
}

/// `--env-file`: load it; a file that cannot be read is named in run.log (without its contents: a parse error's line
/// could hold a secret)
fn load_env_file(f: &Path) -> Option<String> {
    match dotenvy::from_path(f) {
        Ok(()) => None,
        Err(e) => {
            let why = match &e {
                dotenvy::Error::Io(io) => io.kind().to_string(),
                dotenvy::Error::LineParse(_, i) => format!("a line it cannot parse (at byte {i})"),
                other => other.to_string(),
            };
            Some(format!("WARNING: --env-file {}: {why}: nothing loaded from it", f.display()))
        }
    }
}

/// Closes a recorder on every way out of `run`, `simcheck` and `senders --raw` (an error, a panic): its queues are
/// drained and its files closed. An error's stop.json is written after it; a main-thread panic's stop.json is written
/// by the panic hook, before the unwinding reaches it (MEASUREMENT §1.6)
struct RecGuard(rec::Rec);
impl Drop for RecGuard { fn drop(&mut self) { self.0.close(); } }

/// One account of the boot snapshot: accounts.bin (src rpc_boot), the boot journal (its ACCOUNT record, t_engine 0, with
/// the store's verdict) and the store
fn boot_account(store: &mut store::Store, ar: &rec::accounts::AcctRec, j: &rec::journal::Journal, k: tx::Pk, a: rpc::Account, slot: u64) {
    let t = now_ns();
    let data: Arc<[u8]> = a.data.into();
    let src = feeds::src::RPC_BOOT;
    let aseq = ar.record(&rec::accounts::AcctUpdate { pubkey: k, slot, write_version: 0, t_recv: t, src, is_startup: false, txn: None,
        lamports: a.lamports, owner: a.owner, data: &data, bank_id: None });
    j.account(0, aseq, store.is_stale(&k, slot, src, 0, aseq));
    store.apply(k, store::Acct::rpc(data, slot, t, aseq, src));
}

/// a preloaded lookup table: its address, its entries (gaps kept), when a transaction last used it (ns)
type Preloaded = (tx::Pk, Vec<Option<tx::Pk>>, Option<u64>);

/// PLAN-ADDENDUM I-6: the lookup tables of a previous segment's `alts-final.jsonl.zst` (`[alts] preload`: "auto" = the
/// newest one among this run directory's siblings, a path, or "" for none). Review WP-04 #11: only the tables a
/// transaction used within `preload_max_age_h` of `now_ns` (a table without `last_used_ns`, from an older file, counts as
/// used when the file was written), the `preload_max_tables` most recently used. Returns the file, its tables, and how
/// many it held
fn alts_preload(cfg: &config::AltsCfg, dir: &Path, now: u64) -> Option<(PathBuf, Vec<Preloaded>, usize)> {
    let file = match cfg.preload.as_str() {
        "" => return None,
        "auto" => {
            let parent = dir.parent()?;
            let mut best: Option<(std::time::SystemTime, PathBuf)> = None;
            for e in std::fs::read_dir(parent).ok()?.flatten() {
                let p = e.path().join("alts-final.jsonl.zst");
                if e.path() == dir || !p.is_file() { continue; }
                let Ok(t) = std::fs::metadata(&p).and_then(|m| m.modified()) else { continue };
                if best.as_ref().map_or(true, |b| t > b.0) { best = Some((t, p)); }
            }
            best?.1
        }
        p => PathBuf::from(p),
    };
    let (bytes, _) = if file.extension().is_some_and(|e| e == "zst") { rec::decode_zst(&file).ok()? } else { (std::fs::read(&file).ok()?, 0) };
    let written = std::fs::metadata(&file).and_then(|m| m.modified()).ok().and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok()).map(|d| d.as_nanos() as u64);
    let mut out = Vec::new();
    for l in bytes.split(|b| *b == b'\n').filter(|l| !l.is_empty()) {
        let Ok(v) = serde_json::from_slice::<Value>(l) else { continue };
        let Some(t) = v["table"].as_str().and_then(|t| bs58::decode(t).into_vec().ok()).and_then(|b| tx::Pk::try_from(b).ok()) else { continue };
        let addrs: Vec<Option<tx::Pk>> = v["addrs"].as_array().into_iter().flatten()
            .map(|a| a.as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|b| tx::Pk::try_from(b).ok())).collect();
        out.push((t, addrs, v["last_used_ns"].as_u64().or(written)));
    }
    let held = out.len();
    let oldest = now.saturating_sub(cfg.preload_max_age_h.saturating_mul(3_600_000_000_000));
    out.retain(|x| x.2.is_some_and(|u| u >= oldest));
    // the most recently used first (then by address: deterministic), at most preload_max_tables
    out.sort_by(|a, b| b.2.cmp(&a.2).then(a.0.cmp(&b.0)));
    out.truncate(cfg.preload_max_tables);
    Some((file, out, held))
}

fn run(a: &RunArgs, sess: &Arc<control::Session>) -> Result<()> {
    let started_ns = now_ns();
    let (live, canary) = (a.live, a.canary);
    let env_note = match &a.env_file { Some(f) => load_env_file(f), None => { load_env(&a.config); None } };
    let RunConfig { mut cfg, raw, config_json, config_cap } = run_config(a)?;
    // WP-03 item 3: the transaction streams run as feeds after the [[feed]] list (their ids follow its)
    let tx_stream_feeds = cfg.state.tx_stream_feeds();
    cfg.feeds.extend(tx_stream_feeds);
    // live trading needs both mode = "live" and --live; either alone refuses to start (so neither can spend by itself)
    if live != (cfg.mode == "live") { anyhow::bail!("live trading needs mode = \"live\" in the config AND --live (got mode {}, --live {live}; --shadow runs a live config in shadow)", cfg.mode); }
    if let Some(w) = cfg.pricing_warning() { println!("{w}"); }
    if live && canary { anyhow::bail!("--live and --canary are separate runs"); }
    if canary && !cfg.canary.enabled { anyhow::bail!("--canary needs [canary] enabled = true in the config (both, so neither alone can spend)"); }
    if cfg.canary.enabled && !canary { println!("[canary] is enabled in the config but --canary was not given: no canaries this run"); }
    // review F3: a supervised segment is paused through its socket; without one, `.pause` could not reach it
    if a.campaign_dir.is_some() && !cfg.control.socket { anyhow::bail!("[control] socket = false: a supervised segment (--campaign-dir) needs its control socket (the supervisor pauses sending through it)"); }
    // the trading key is read only when something will really be sent, and must be the config's wallet. Before the
    // signal handlers: Ctrl-C at the passphrase prompt still ends the process at once (nothing has started)
    let send_key = if live || canary { Some((if live { exec::Kind::Live } else { exec::Kind::Canary }, wallet::load_cfg(&cfg)?)) } else { None };
    // the enabled feeds, in order: their index is the feed id every stream uses (txarr's columns, the entries archives)
    if let Some(only) = &a.only {
        let want: Vec<&str> = only.split(',').map(str::trim).collect();
        for f in &mut cfg.feeds { f.enabled = want.contains(&f.name.as_str()); }
    }
    let feed_names: Vec<String> = cfg.feeds.iter().filter(|f| f.enabled).map(|f| f.name.clone()).collect();
    // the run directory next: from here on every end, even a failed boot, leaves stop.json
    let name = a.name.clone().unwrap_or_else(utc_stamp);
    let dir = run_dir(&cfg.out_dir, a.campaign_dir.as_deref(), &name);
    // review F13: a directory that already holds a run is refused (the recorder would replace its compressed files and
    // append to its plain ones); nothing is written into it
    if let Some(n) = std::fs::read_dir(&dir).ok().map(|d| d.count()).filter(|n| *n > 0) {
        anyhow::bail!("{} already holds {n} files (an earlier run?): choose another --name", dir.display());
    }
    std::fs::create_dir_all(&dir).with_context(|| format!("creating {}", dir.display()))?;
    sess.set_dir(dir.clone());
    // WP-02: the recorder, always on (MEASUREMENT §0), before anything records. Its writer threads write every stream
    // (run.log too: `say` hands the line over; the engine thread writes nothing); a core-stream drop or the disk
    // budget's last step closes the SendGate. Closed on every way out of `run`, before stop.json's line
    let producer = provenance::build_json()["binary_sha256"].as_str().map(|h| h[..16].to_string()).unwrap_or_else(|| "unknown".into());
    let rec = rec::start(rec::Opts { dir: dir.clone(), run: name.clone(), producer, cfg: cfg.record.clone(), feeds: feed_names.clone(), monitor: true, echo: None })?;
    let _rec_guard = RecGuard(rec.clone());
    rec.bind_session(sess.gate.clone(), sess.stopper.clone());
    let say = |s: &str| rec.say(s);
    say(&format!("arbx {} build {} ({}), config {} (sha256 {}), run {}", env!("CARGO_PKG_VERSION"), provenance::build_short(), env!("ARBX_PROFILE"),
        a.config.display(), &provenance::sha256_hex(&raw)[..16], dir.display()));
    if let Some(n) = &env_note { say(n); }
    for n in rec.recorder().map(|r| r.notes.clone()).unwrap_or_default() { say(&n); }
    // the run's identity, and a partial meta.json that stop.json's writer leaves if the boot fails before the full one
    let run_json = json!({ "campaign": a.campaign_dir.as_deref().and_then(|c| c.file_name()).map(|c| c.to_string_lossy().into_owned()), "segment": name,
        "dir": dir.display().to_string(), "started_ns": started_ns, "host": provenance::hostname(), "pid": std::process::id(),
        "uid": unsafe { libc::getuid() }, "argv": std::env::args().collect::<Vec<_>>(),
        "mode": if live { "live" } else if canary { "canary" } else { "shadow" }, "forced_shadow": a.ov.shadow, "live_flag": live,
        "env_file": a.env_file.as_ref().map(|f| f.display().to_string()), "env_file_loaded": a.env_file.as_ref().map(|_| env_note.is_none()) });
    sess.set_meta_stub(json!({ "schema": provenance::META_SCHEMA, "partial": true, "run": run_json, "build": provenance::build_json(),
        "config": config_json, "campaign_dir": a.campaign_dir.as_ref().map(|c| c.display().to_string()), "overrides": a.ov.json() }));
    // stop reasons (WP-01): SIGINT / SIGTERM with their sender, and the control socket. Outside a campaign a socket that
    // cannot be opened is not fatal (signals still stop the run); a supervised segment needs it (review F3)
    control::install_signals(sess.clone())?;
    let _control = if !cfg.control.socket { None } else {
        match control::serve(sess.clone(), &dir) {
            Ok(c) => Some(c),
            Err(e) if a.campaign_dir.is_some() => return Err(e.context("the control socket (a supervised segment needs it)")),
            Err(e) => { say(&format!("WARNING: no control socket: {e:#}")); None }
        }
    };
    // the gate says what this run may do: --shadow forces shadow; a run without --live or --canary sends nothing anyway
    initial_gate(&sess.gate, a.ov.shadow, live, canary);
    // the frozen copy of the config this run uses (meta.json config.frozen_copy)
    std::fs::write(dir.join("config.toml"), &raw)?;
    let stop = sess.stopper.flag();
    let exec_on = cfg.sim.enabled || canary || live;
    // WP-02 (F9): two runtimes. rt_hot (2 workers, `arbx-hot`) runs only stream I/O and sends: the state stream, the gRPC
    // feeds, the send paths, the Jito result streams, keep-alives. rt_bg (`[runtime] bg_threads`, `arbx-bg`, niced +5)
    // runs every RPC call: the client is bound to it, so the boot, the engine's fetches, the executor's simulations and
    // settlements and the program hashing all run there, and large replies are parsed in its blocking pool
    let rts = runtime::Runtimes::new(cfg.runtime.bg_threads)?;
    let (hot, bg) = (rts.hot.handle().clone(), rts.bg.handle().clone());
    rec.set_runtimes(hot.clone(), bg.clone());
    let (eps, skipped) = cfg.rpc.endpoints();
    if eps.is_empty() { anyhow::bail!("no RPC provider configured (skipped: {skipped:?})"); }
    let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover).bind(bg.clone()).with_role(rpc::Role::Boot);
    // WP-03b (PLAN-ADDENDUM I-1): every provider's token bucket, shared by every client and role of the process (Haan
    // answered 429 at about 5 requests/s); the boot policy (until the executor is built, every call retries with backoff
    // across the providers for `[chainfetch] boot_retry_s`: only a sustained failure aborts the boot, with its stop
    // reason); each provider's host resolved once and its connection opened (no DNS lookup on a reconnect)
    let rpc_reg = rpc::Registry::global();
    for n in rpc.names() { let (r, b) = cfg.chainfetch.limit_of(&n); rpc_reg.set_limit(&n, r, b); }
    rpc_reg.set_sink(rec.clone());
    rpc.set_phase(rpc::Phase::Boot);
    rpc.set_boot_budget(std::time::Duration::from_secs(cfg.chainfetch.boot_retry_s));
    rpc.set_stop(stop.clone());
    for n in rts.bg.block_on(rpc.prewarm()) { say(&n); }
    let state_token = config::env_token(&cfg.state.token_env, "state")?;
    // WP-03 items 6, 7: what the state stream subscribes to besides the accounts. blocks_meta = "auto" follows the probe
    // (`arbx grpc-probe`), whose result is copied into the segment (probe.json)
    let state_host = provenance::host_of(&cfg.state.url);
    let probe_path = if cfg.state.probe_file.is_empty() { PathBuf::from(&cfg.out_dir).join("probe.json") } else { PathBuf::from(&cfg.state.probe_file) };
    let probe_raw = std::fs::read(&probe_path).ok();
    let probe_v: Option<Value> = probe_raw.as_deref().and_then(|b| serde_json::from_slice(b).ok());
    if probe_v.is_some() { let _ = std::fs::copy(&probe_path, dir.join("probe.json")); }
    // meta.json `probe` (MEASUREMENT §4.2): the file's hash, when it was taken, what was accepted and refused
    let probe_meta = probe_v.as_ref().map(|p| {
        let subs = p["subs"].as_array().cloned().unwrap_or_default();
        let name = |s: &Value| match s["feed"].as_str() { Some(f) => format!("{}@{f}", s["sub"].as_str().unwrap_or("?")), None => s["sub"].as_str().unwrap_or("?").to_string() };
        let ok = |s: &&Value| s["accepted"] == json!(true) && s["messages_30s"].as_u64().unwrap_or(0) > 0;
        json!({ "file_sha256": provenance::sha256_hex(probe_raw.as_deref().unwrap_or_default()), "t_ns": p["t_ns"], "provider_host": p["provider_host"],
            // review WP-03 N7: how old the probe is when this segment reads it
            "age_s": p["t_ns"].as_u64().map(|t| started_ns.saturating_sub(t) / 1_000_000_000),
            "accepted": subs.iter().filter(ok).map(name).collect::<Vec<_>>(),
            "refused": subs.iter().filter(|s| s["accepted"] == json!(false)).map(|s| json!({ "sub": name(s), "error": s["error"] })).collect::<Vec<_>>(),
            "inconclusive": subs.iter().filter(|s| !ok(s) && s["accepted"] != json!(false)).map(|s| json!({ "sub": name(s), "error": s["error"], "code": s["code"],
                "messages_30s": s["messages_30s"] })).collect::<Vec<_>>() })
    });
    let probe_ok = |sub: &str| probe_v.as_ref().and_then(|p| probe::accepted(p, &state_host, sub)).unwrap_or(false);
    let block_meta = match cfg.state.block_meta.as_str() { "on" => true, "off" => false, _ => probe_ok("blocks_meta") };
    // review WP-03 #5: interslot statuses share the state stream's one subscription with the accounts; a provider that
    // refused them would refuse the whole stream. "auto" (the default): on only where the probe accepted them
    let interslot = match cfg.state.slot_statuses.as_str() { "all" => true, "commitment" => false, _ => probe_ok("slots_interslot") };
    let state_subs = feeds::grpc::StateSubs { interslot, block_meta };
    say(&format!("state stream: slot statuses {} ({}), blocks_meta {} ({}; probe {})", if interslot { "all" } else { "commitment" }, cfg.state.slot_statuses,
        if block_meta { "on" } else { "off" }, cfg.state.block_meta,
        match &probe_v { Some(p) => format!("{} of {}", probe_path.display(), p["provider_host"].as_str().unwrap_or("?")), None => format!("none at {}", probe_path.display()) }));
    // the LeaderBook (WP-03 item 10): its static fallback now, its refreshes once the engine's channel exists
    let book = leaders::LeaderBook::new(rec.clone());
    leaders::install(book.clone());
    if cfg.leaders.enabled {
        match book.load_static(Path::new(&cfg.leaders.static_fallback)) {
            Ok(n) => say(&format!("leaders: static fallback {} ({n} validators)", cfg.leaders.static_fallback)),
            Err(e) => say(&format!("leaders: no static fallback: {e:#}")),
        }
    }
    // WP-03 items 1, 2, 11: accounts.bin (every account update with its aseq; the snapshot's as src rpc_boot between
    // boot marks) and the boot journal (the snapshot's ACCOUNT records, t_engine 0); the extra watched accounts (the
    // Clock sysvar, the programs' programdata, the wallet and its token accounts) and every account's role
    let journal = rec::journal::Journal::new(rec.clone());
    let mut boot_extra = None;
    // pools, then a first snapshot of every followed account
    let (reg, store, snapshot_slot) = rts.bg.block_on(async {
        let (cands, seeds, ours) = pools::candidates(&cfg.pools)?;
        let reg = pools::boot(&rpc, &cands, seeds, ours).await?;
        let programs: Vec<tx::Pk> = if cfg.state.watch_programdata { provenance::program_specs(&cfg).iter().map(|p| p.id).collect() } else { vec![] };
        // (a wallet that is not a key leaves the wallet accounts out: the run's keystore check names it)
        let wallet = cfg.state.watch_wallet.then(|| bs58::decode(&cfg.wallet).into_vec().ok().and_then(|b| tx::Pk::try_from(b).ok())).flatten();
        let extra = reg.extra_watch(cfg.state.watch_clock, &programs, wallet.as_ref());
        let mut role_list = reg.watch_roles();
        role_list.extend(extra.iter().copied());
        let roles = Arc::new(rec::accounts::Roles::new(role_list));
        let acct_rec = rec::accounts::AcctRec::new(rec.clone(), roles.clone());
        let mut base = reg.static_accounts();
        let mut have: std::collections::HashSet<tx::Pk> = base.iter().copied().collect();
        for (k, _) in &extra { if have.insert(*k) { base.push(*k); } }
        let mut store = store::Store::default();
        // the snapshot leaves out the programdata accounts (megabytes each; the stream reports their upgrades)
        let keys: Vec<tx::Pk> = base.iter().copied().filter(|k| roles.get(k).map_or(true, |r| r.role != rec::accounts::role::PROGRAMDATA)).collect();
        acct_rec.mark(rec::accounts::MARK_BOOT_BEGIN, &[]);
        // 100 accounts per call, paced; each labelled with its own call's context slot (review WP-04 #1c: one label, the
        // last call's, put early accounts at a slot they were not read at). The stream's first connection reads them all
        // again (the engine's re-read), closing the gap between this snapshot and the subscription
        let mut slot = 0;
        for (n, chunk) in keys.chunks(reads::CHUNK).enumerate() {
            if n > 0 { tokio::time::sleep(std::time::Duration::from_millis(120)).await; }
            let (s, accts) = rpc.accounts(chunk).await?;
            slot = slot.max(s);
            for (k, a) in chunk.iter().zip(accts) { if let Some(a) = a { boot_account(&mut store, &acct_rec, &journal, *k, a, s); } }
        }
        engine::initial_dlmm_arrays(&reg, &mut store);
        let arr: Vec<tx::Pk> = store.dlmm_arrays.values().flatten().map(|x| x.1).collect();
        roles.add(store.dlmm_arrays.iter().flat_map(|(p, l)| { let pi = reg.by_pool.get(p).map_or(rec::accounts::NO_POOL, |i| *i as u32);
            l.iter().map(move |(_, k)| (*k, rec::accounts::RoleOf { role: rec::accounts::role::DLMM_BIN_ARRAY, pool_index: pi })) }).collect::<Vec<_>>());
        for chunk in arr.chunks(reads::CHUNK) {
            tokio::time::sleep(std::time::Duration::from_millis(120)).await;
            let (s, accts) = rpc.accounts(chunk).await?;
            for (k, a) in chunk.iter().zip(accts) { if let Some(a) = a { boot_account(&mut store, &acct_rec, &journal, *k, a, s); } }
        }
        acct_rec.mark(rec::accounts::MARK_BOOT_END, &[]);
        boot_extra = Some((roles, acct_rec, base, extra.len()));
        anyhow::Ok((reg, store, slot))
    })?;
    let (roles, acct_rec, base_watch, n_extra) = boot_extra.expect("set by the boot");
    let snapshot_ns = now_ns();
    // review F1: the state stream starts right after the snapshot, as in arb-lab. It sends only the writes after it
    // subscribes and the engine never re-reads the pools, so every step put between the two (the programs, the send
    // paths, the executor, meta.json) would leave pools on a pre-write price until their next write. Its updates queue
    // until the engine starts; the tx feeds still start after meta.json
    let (tx, rx) = crossbeam_channel::unbounded::<feeds::Event>();
    let mut list: Vec<String> = base_watch.iter().map(tx::b58).collect();
    for l in store.dlmm_arrays.values() { for (_, k) in l { list.push(tx::b58(k)); } }
    let followed = list.len();
    let (wtx, wrx) = tokio::sync::watch::channel(list);
    let state_counters = Arc::new(feeds::FeedCounters::named("state", "state-stream"));
    // WP-03b wiring: the chain-fetch service (wallet transactions, the watched-transaction backfill, the slot index, the
    // blockhash ring) on rt_bg, its roles on the `[[chainfetch.provider]]` providers. Its taps are installed before the
    // state stream starts (its first updates name transactions too); nothing here waits on the network. If the service
    // dies while the run goes on, the SendGate closes for the rest of the segment (wallet.jsonl is the reconciliation
    // source; review WP-03b #12). The idle providers' connections are kept warm
    let cf_clients = chainfetch::RoleClients::new(&rpc, &cfg.chainfetch);
    let cf_meta = chainfetch::meta_json(&cfg.chainfetch, &cf_clients, &rpc_reg);
    if cfg.chainfetch.enabled {
        let (cap, wallet_pk) = (cf_clients.cap(rpc::Role::Backfill), bs58::decode(&cfg.wallet).into_vec().ok().and_then(|b| tx::Pk::try_from(b).ok()));
        let gate = sess.gate.clone();
        let on_dead: chainfetch::OnDead = Arc::new(move |why: &str| { let _ = gate.shadow("chainfetch_dead", why, true); });
        chainfetch::start(chainfetch::Opts { cfg: cfg.chainfetch.clone(), wallet: wallet_pk, route_program: tx::pk(&cfg.exec.program), roles: roles.clone(), rec: rec.clone(),
            back: Some(tx.clone()), chain: Arc::new(cf_clients), backfill_cap: cap }, rpc_reg.clone(), &bg, stop.clone(), Some(on_dead));
    }
    rpc.start_warm(&bg, stop.clone(), std::time::Duration::from_secs(20), std::time::Duration::from_secs(5));
    feeds::start_state(cfg.state.url.clone(), state_token, wrx, state_subs, tx.clone(), stop.clone(), &hot, state_counters.clone(), rec.clone(),
        feeds::Fwd { state: true, acct: Some(acct_rec.clone()), leaders: Some(book.clone()) });
    let stream_started_ns = now_ns();
    say(&format!("state stream: {n_extra} extra watched accounts (clock {}, programdata {}, wallet {}); {} accounts with a role", cfg.state.watch_clock,
        cfg.state.watch_programdata, cfg.state.watch_wallet, roles.len()));
    // the LeaderBook's refreshes (schedule windows reach the engine as inputs) and the SendGate's changes, sampled every
    // 100 ms (`src` "watch": status and coverage only; the mode each send check saw is journaled by the engine at the
    // decision, `src` "decision": review WP-03 #3)
    // (the LeaderBook calls as configured from the start: its own phase, not the boot policy; review WP-03b #14)
    if cfg.leaders.enabled { leaders::start(book.clone(), rpc.with_role(rpc::Role::Leaders).with_own_phase(rpc::Phase::Run), cfg.leaders.clone(), &bg, stop.clone(), tx.clone(), rec.clone()); }
    {
        let (gate, back, stop) = (sess.gate.clone(), tx.clone(), stop.clone());
        bg.spawn(async move {
            let mut last = Value::Null;
            while !stop.load(Ordering::Relaxed) {
                let mut g = gate.json();
                if let Some(m) = g.as_object_mut() { m.remove("since_ns"); }
                if g != last {
                    let mut d = gate.json();
                    d["src"] = json!("watch");
                    let _ = back.send(feeds::Event::Input { kind: feeds::InputKind::Gate, data: Arc::new(d) });
                    last = g;
                }
                tokio::time::sleep(std::time::Duration::from_millis(100)).await;
            }
        });
    }
    // WP-03 item 3: the transaction streams' `@watched_writable` / `@venue_programs`, now that the registry is known
    let venue_programs: Vec<String> = provenance::venue_specs().iter().map(|p| tx::b58(&p.id)).collect();
    config::expand_includes(&mut cfg.feeds, &reg.watched_writable(), &venue_programs)?;
    let reg = Arc::new(reg);
    say(&format!("booted: {}; {} accounts held (snapshot at slot {snapshot_slot})", reg.summary(), store.len()));
    say(&format!("state stream follows {followed} accounts, started {:.1} ms after the snapshot (its first update's slot follows in this log)",
        stream_started_ns.saturating_sub(snapshot_ns) as f64 / 1e6));
    say(&format!("rpc providers raced: {} (skipped, env missing: {:?})", rpc.names().join(", "), skipped));
    if sess.stopper.stopping() { return Ok(()); }
    // provenance (WP-01): the route program's ELF hash, before anything can send. A route program that is not the
    // expected one refuses live sends: the SendGate stays shadow for the whole segment. The venue programs are hashed
    // in the background once the feeds run (review F1, M8)
    let route = rts.bg.block_on(provenance::fetch_programs(&rpc, &[provenance::route_spec(&cfg)]));
    for p in route.iter().filter(|p| p["error"].is_string()) { say(&format!("provenance: program {} ({}) not hashed: {}", p["name"].as_str().unwrap_or("?"), p["id"].as_str().unwrap_or("?"), p["error"].as_str().unwrap_or(""))); }
    for l in apply_route_check(&sess.gate, provenance::route_check(&route), live, canary) { say(&l); }
    // invariant 9: the trading key never holds a program's upgrade authority
    for p in route.iter().filter(|p| p["upgrade_authority"].as_str() == Some(cfg.wallet.as_str())) {
        say(&format!("WARNING: the trading wallet holds the upgrade authority of {} ({})", p["name"].as_str().unwrap_or("?"), p["id"].as_str().unwrap_or("?")));
    }
    if sess.stopper.stopping() { return Ok(()); }
    let mut interest = engine::interest(&reg, cfg.pools.templates_json.as_deref());
    // our own transactions (canaries): every feed forwards them, so we see when each one appears
    if exec_on { interest.keys.insert(tx::pk(&cfg.wallet)); }
    let interest = Arc::new(interest);
    say(&format!("interest: {} keys, {} lookup tables", interest.keys.len(), interest.tables.read().unwrap().len()));
    say(&format!("recording (always on): every stream compressed in {} (frames every {} ms, rotation at {} MiB or {} min; disk budget {} GB, min free {} GB){}",
        dir.display(), cfg.record.flush_ms, cfg.record.rotate_mb, cfg.record.rotate_min, cfg.record.disk_budget_gb, cfg.record.min_free_gb,
        if cfg.record.archive_feeds.is_empty() { String::new() } else { format!("; raw entries of {}", cfg.record.archive_feeds.join(", ")) }));
    // STEP 1: every send path kept warm and timed (keepalive.jsonl); paths that can't be built are named, not fatal. On
    // the hot runtime (their sends and result streams run there)
    let paths = if cfg.sends.iter().any(|s| s.enabled) {
        let (p, notes) = rts.hot.block_on(send::Paths::new(&cfg.sends, cfg.gate.clone(), rec.clone(), true))?;
        for n in notes { say(&format!("send path {n}")); }
        let back = tx.clone();
        p.start(stop.clone(), std::time::Duration::from_secs(cfg.exec.keepalive_s), move |m: String| { let _ = back.send(feeds::Event::Status { feed: u16::MAX, msg: m }); });
        say(&format!("send paths: {} (keep-alive every {} s)", p.list.iter().map(|x| x.name.as_str()).collect::<Vec<_>>().join(", "), cfg.exec.keepalive_s));
        Some(p)
    } else { None };
    // STEPS 2-3: simulation of every would-send decision, canaries. The executor's sends run on the hot runtime; its
    // RPC (lookup tables, nonces, simulations, settlements) on the background one through the bound client
    let exec = if exec_on {
        let (mut x, notes) = rts.hot.block_on(exec::Exec::new(&cfg, &rpc, paths.clone(), rec.clone(), tx.clone(), feed_names.clone(), send_key, reg_mints(&reg)))?;
        x.set_gate(sess.gate.clone());
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
    // WP-03b: the boot is over (pools, snapshot, route program, executor): every client calls as configured again
    rpc.set_phase(rpc::Phase::Run);
    say(&format!("rpc: boot done; budgets {} (requests/s, every role); chain fetch {}", rpc_reg.limits_json(),
        if cfg.chainfetch.enabled { cf_meta["roles"].to_string() } else { "off".to_string() }));
    // meta.json v2 (MEASUREMENT §4.2), written before the feeds start; rewritten once when the venue programs are hashed
    let built: Vec<String> = paths.as_ref().map(|p| p.list.iter().map(|x| x.name.clone()).collect()).unwrap_or_default();
    let mut limits = limits_json(&cfg, live, canary);
    limits["supervisor"] = json!({ "budget_left_lamports": a.ov.budget_left, "config_max_failed_fees_lamports": config_cap,
        "effective_max_failed_fees_lamports": cfg.live.max_failed_fees_lamports });
    limits["ledger"] = Value::Null;
    let tx_streams: Vec<Value> = cfg.feeds.iter().filter(|f| f.enabled && f.kind == config::FeedKind::YellowstoneTx)
        .map(|f| json!({ "name": f.name, "url_host": f.url.as_deref().map(provenance::host_of), "account_include": f.account_include, "max_accounts": f.max_accounts,
            "failed": f.failed.unwrap_or(true) })).collect();
    let venue_specs = provenance::venue_specs();
    let mut programs = route.clone();
    programs.extend(venue_specs.iter().map(provenance::pending_entry));
    let mut streams = provenance::streams_json();
    if let (Some(m), Value::Object(r)) = (streams.as_object_mut(), rec.streams_json()) { m.extend(r); }
    let meta = json!({
        "schema": provenance::META_SCHEMA,
        "run": run_json, "build": provenance::build_json(), "config": config_json,
        "programs": programs, "programs_pending": true,
        "wallet": { "pubkey": cfg.wallet, "keystore_path": if cfg.wallet_keystore.is_empty() { format!("~/.nexus-v2-{}-wallet.enc", cfg.wallet_profile) } else { cfg.wallet_keystore.clone() },
            "held_mints_at_boot": exec.as_ref().map(|x| x.held_mints()) },
        "feeds": provenance::feeds_json(&cfg), "send_paths": provenance::send_paths_json(&cfg, &built), "rpc": provenance::rpc_json(&cfg),
        "state": { "url_host": provenance::host_of(&cfg.state.url), "tx_streams": tx_streams, "watch_clock": cfg.state.watch_clock,
            "watch_programdata": cfg.state.watch_programdata, "watch_wallet": cfg.state.watch_wallet, "block_meta": block_meta,
            "slot_statuses": if interslot { "all" } else { "commitment" }, "extra_watched": n_extra, "config": provenance::section(&cfg.state),
            "snapshot_slot": snapshot_slot, "snapshot_ns": snapshot_ns, "stream_started_ns": stream_started_ns, "followed": followed },
        "probe": probe_meta, "chainfetch": cf_meta, "leaders": provenance::section(&cfg.leaders),
        "pools": provenance::pools_json(&reg, &cfg), "inputs": provenance::inputs_json(&cfg),
        "streams": streams, "experiments": null,
        "limits": limits, "campaign_dir": a.campaign_dir.as_ref().map(|c| c.display().to_string()),
        "clock": provenance::clock_json(),
        "strategy": provenance::section(&cfg.strategy), "send": provenance::section(&cfg.sends), "builder": provenance::section(&cfg.exec),
        "live": provenance::section(&cfg.live), "sim": provenance::section(&cfg.sim), "canary": provenance::section(&cfg.canary),
        "gate": provenance::section(&cfg.gate), "record": provenance::section(&cfg.record), "control": provenance::section(&cfg.control), "tips": null,
        "runtime": provenance::section(&cfg.runtime),
        "send_gate": sess.gate.json(),
        // what the command line changed in the config for this run (--shadow, --budget-left)
        "overrides": a.ov.json(),
    });
    control::write_atomic(&dir.join("meta.json"), serde_json::to_string_pretty(&meta)?.as_bytes())?;
    if sess.stopper.stopping() { return Ok(()); }
    let fs = feeds::start(&cfg.feeds, interest.clone(), tx.clone(), stop.clone(), &hot, &rec, Some(roles.clone()))?;
    anyhow::ensure!(fs.names == feed_names, "feed ids changed: {:?} vs {:?}", fs.names, feed_names);
    say(&format!("feeds: {}", fs.names.join(", ")));
    // the venue programs, in the background: once per campaign (the campaign's cache, keyed by each programdata's last
    // deploy slot), then meta.json is rewritten with them; what happened goes to run.log through the engine
    {
        let (rpc, back, dir, wallet) = (rpc.with_role(rpc::Role::Provenance), tx.clone(), dir.clone(), cfg.wallet.clone());
        let cache = a.campaign_dir.as_ref().map(|c| c.join(provenance::PROGRAMS_CACHE));
        let mut meta = meta.clone();
        rts.bg.spawn(async move {
            let t0 = now_ns();
            let venues = provenance::fetch_programs_cached(&rpc, &venue_specs, cache.as_deref()).await;
            let say = |msg: String| { let _ = back.send(feeds::Event::Status { feed: u16::MAX, msg }); };
            for p in venues.iter().filter(|p| p["error"].is_string()) { say(format!("provenance: program {} ({}) not hashed: {}", p["name"].as_str().unwrap_or("?"), p["id"].as_str().unwrap_or("?"), p["error"].as_str().unwrap_or(""))); }
            for p in venues.iter().filter(|p| p["upgrade_authority"].as_str() == Some(wallet.as_str())) {
                say(format!("WARNING: the trading wallet holds the upgrade authority of {} ({})", p["name"].as_str().unwrap_or("?"), p["id"].as_str().unwrap_or("?")));
            }
            let cached = venues.iter().filter(|p| p["source"] == "cache").count();
            let n = venues.len();
            if let Some(list) = meta["programs"].as_array_mut() { list.retain(|p| p["role"] != "venue"); list.extend(venues); }
            meta["programs_pending"] = json!(false);
            meta["programs_done_ns"] = json!(now_ns());
            let wrote = serde_json::to_string_pretty(&meta).map_err(anyhow::Error::from).and_then(|s| control::write_atomic(&dir.join("meta.json"), s.as_bytes()));
            say(format!("provenance: {n} venue programs hashed in {:.0} ms ({cached} from the campaign cache); meta.json {}", (now_ns() - t0) as f64 / 1e6,
                match wrote { Ok(()) => "rewritten".to_string(), Err(e) => format!("NOT rewritten: {e:#}") }));
        });
    }
    let min_tip = cfg.sends.iter().filter(|s| s.enabled).map(|s| s.tip_lamports).min().unwrap_or(0);
    // status.jsonl exists (with its header) before the engine can send anything: the supervisor reads its existence as
    // "the engine started" (deploy/run-w.sh `spent`, review F4). A run that cannot write it does not start: it is the
    // supervisor's failed-fee budget source
    rec.open_now(rec::STATUS).context("status.jsonl (the supervisor's budget source)")?;
    let mut eng = engine::Engine::new(reg.clone(), store, cfg.strategy.clone(), fs.names.clone(), min_tip, interest, rec.clone(), rpc.with_role(rpc::Role::Engine),
        bg.clone(), tx.clone(), wtx)?;
    eng.set_feed_counters(fs.counters.clone(), Some(state_counters));
    eng.set_acct_rec(acct_rec.clone());
    eng.set_base_watch(base_watch);
    // ---- WP-04 wiring: state consistency knobs, signer statistics per segment (I-5), lookup-table preload (I-6)
    eng.set_knobs(engine::EngineKnobs::from_cfg(&cfg));
    eng.set_signer_stats_out(&dir);
    if !cfg.strategy.signer_stats_file.is_empty() {
        say(&format!("signer statistics: read {} (sha256 {}); this segment writes signer-stats.json and signer-stats-delta.json here (`arbx signer-stats merge` folds the delta back)",
            cfg.strategy.signer_stats_file, eng.signer_stats_sha256().unwrap_or("none: not read")));
    }
    match alts_preload(&cfg.alts, &dir, now_ns()) {
        Some((file, tables, held)) => {
            let n = tables.len();
            // journaled with the boot records (ALT found 3): a replay starts from the same tables
            for (t, v, used) in tables { eng.preload_alt(t, v, used, true); }
            say(&format!("lookup tables: preloaded {n} of the {held} in {} (used in the last {} h, at most {})", file.display(), cfg.alts.preload_max_age_h,
                cfg.alts.preload_max_tables));
            rec.event("alts_preload", "engine", None, json!({ "file": file.display().to_string(), "tables": n, "held": held,
                "sha256": provenance::file_sha256(&file).ok().map(|x| x.0) }));
        }
        None => say(&format!("lookup tables: nothing preloaded ([alts] preload {:?})", cfg.alts.preload)),
    }
    eng.exec = exec;
    eng.gate = Some(sess.gate.clone());
    // the minutes count from the engine's start, as in arb-lab (boot time is not part of the segment)
    let until = a.minutes.map(|m| now_ns() + (m * 60e9) as u64).unwrap_or(u64::MAX);
    let counters = fs.counters.clone();
    let names = fs.names.clone();
    let rpc_stats = rpc.clone();
    let mut ticks = 0u64;
    let end = eng.run(&rx, &stop, until, |s| {
        let per: Vec<String> = names.iter().zip(&counters).map(|(n, c)| format!("{n} {}/{}", c.forwarded.load(Ordering::Relaxed), c.txs.load(Ordering::Relaxed))).collect();
        say(&format!("{s} | fwd/txs: {}", per.join(", ")));
        ticks += 1;
        if ticks % 6 == 0 {
            for l in rpc_stats.summary() { say(&format!("rpc {l}")); }
            for l in rpc_stats.reasons(2) { say(&format!("rpc failure {l}")); }
            if let Some(p) = &paths { for l in p.summary() { say(&format!("send {l}")); } }
        }
    });
    match end {
        engine::RunEnd::Deadline => { sess.stopper.request(StopInfo::new(StopReason::Deadline, format!("--minutes {} reached", a.minutes.unwrap_or(0.0)))); }
        engine::RunEnd::Disconnected => { sess.stopper.request(StopInfo::new(StopReason::Error, "the engine's event channel closed")); }
        // PLAN-ADDENDUM I-4: the state stream never delivered (cmp2 ran blind for 28 minutes and exited 0)
        engine::RunEnd::StateUnavailable => { sess.stopper.request(StopInfo::new(StopReason::StateUnavailable, eng.stop_req.clone().unwrap_or_default())); }
        engine::RunEnd::Stopped => {}
    }
    let reason = sess.stopper.info().map_or("error", |i| i.reason.as_str());
    // what was still open when the stop began (stop.json; WP-05 / WP-07 drain them, the next segment's ledger picks them
    // up). No executor: null (review M11)
    let open = eng.exec.as_ref().map(|x| x.open_attempts());
    eng.write_final_status(rx.len(), reason);
    *sess.drain.lock().unwrap() = control::Drain { in_flight_at_stop: open.as_ref().map(|o| o.len()), drained: open.as_ref().map(|o| o.is_empty()),
        unsettled: open.unwrap_or_default(), drain_ms: None, final_status_seq: eng.status_lines.checked_sub(1) };
    for l in rpc_stats.summary() { say(&format!("rpc final {l}")); }
    for l in rpc_stats.reasons(5) { say(&format!("rpc failure {l}")); }
    // WP-03b: every client's requests by role and provider (resources.jsonl `rpc` has them every 10 s)
    for l in rpc_reg.summary_lines() { say(&format!("rpc role {l}")); }
    if let Some(p) = &paths { for l in p.summary() { say(&format!("send final {l}")); } }
    if let Some(x) = &eng.exec { say(&format!("exec final {}", x.status())); }
    if runtime::hot_violations() > 0 { say(&format!("WARNING: {} RPC calls ran on an arbx-hot thread", runtime::hot_violations())); }
    stop.store(true, Ordering::Relaxed);
    // the feeds and send tasks stop with the runtimes; then the recorder drains what they handed it (its guard closes it)
    rts.shutdown(std::time::Duration::from_secs(2));
    say(&format!("done: {} (stop: {reason})", dir.display()));
    rec.close();
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

    /// review F1: a plain run of the shipped file is a shadow run, and `--shadow` runs a live config in shadow. WP-02:
    /// the recorder cannot be turned off (`--no-record` is gone: clap refuses it, tests/meta_config_hash.rs)
    #[test]
    fn shadow_override() {
        let mut cfg = stage0();
        Overrides::default().apply(&mut cfg, false, false).unwrap();
        assert_eq!(cfg.mode, "shadow", "ships in shadow: a plain run is a shadow run");
        let mut live = stage0();
        live.mode = "live".into();
        let ov = Overrides { shadow: true, budget_left: None };
        ov.apply(&mut live, false, false).unwrap();
        assert_eq!(live.mode, "shadow");
        assert_eq!(ov.json(), serde_json::json!({ "mode": "shadow" }));
        assert!(Overrides { shadow: true, ..Default::default() }.apply(&mut stage0(), true, false).is_err(), "--shadow with --live");
        // review M7: --shadow never sends, so --canary with it is refused (it would unlock the key for nothing)
        let e = Overrides { shadow: true, ..Default::default() }.apply(&mut stage0(), false, true).unwrap_err();
        assert!(e.to_string().contains("--shadow and --canary"), "{e}");
        assert_eq!(Overrides::default().json(), serde_json::json!({}));
    }

    /// WP-01 `--budget-left`: the supervisor's per-segment budget lowers the failed-fee cap, never raises it, and the
    /// config file is not touched (res-stops: sed rewrote it every segment)
    #[test]
    fn budget_left_caps_without_editing_the_config() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-stage0.toml");
        let before = std::fs::read(&path).unwrap();
        let mut cfg = stage0();
        let cap = cfg.live.max_failed_fees_lamports;
        assert_eq!(cap, 25_000_000);
        let ov = Overrides { budget_left: Some(3_000_000), ..Default::default() };
        ov.apply(&mut cfg, false, false).unwrap();
        assert_eq!(cfg.live.max_failed_fees_lamports, 3_000_000);
        assert_eq!(ov.json(), serde_json::json!({ "budget_left_lamports": 3_000_000 }));
        let mut cfg = stage0();
        Overrides { budget_left: Some(90_000_000), ..Default::default() }.apply(&mut cfg, false, false).unwrap();
        assert_eq!(cfg.live.max_failed_fees_lamports, cap, "the config's own cap still applies");
        assert_eq!(std::fs::read(&path).unwrap(), before);
    }

    /// a campaign's segments live in the campaign directory (MEASUREMENT §1.1)
    #[test]
    fn segment_directory() {
        assert_eq!(run_dir("/root/arbx/runs", None, "x-p1"), PathBuf::from("/root/arbx/runs/x-p1"));
        assert_eq!(run_dir("/root/arbx/runs", Some(Path::new("/root/arbx/runs/w6")), "w6-p3"), PathBuf::from("/root/arbx/runs/w6/w6-p3"));
    }

    /// a run that failed or panicked still leaves stop.json with the reason and exit 30; a stop requested first stands
    #[test]
    fn end_run_codes() {
        let d = std::env::temp_dir().join(format!("arbx-endrun-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&d).unwrap();
        let read = |d: &Path| -> Value { serde_json::from_str(&std::fs::read_to_string(d.join("stop.json")).unwrap()).unwrap() };
        let s = control::Session::new();
        s.set_dir(d.clone());
        assert_eq!(end_run(&s, Ok(Err(anyhow::anyhow!("boot: rpc https://x.example/?api-key=SECRET refused")))), 30);
        let v = read(&d);
        assert_eq!(v["reason"], "error");
        assert!(!v["detail"].as_str().unwrap().contains("SECRET"), "{v}");
        let s = control::Session::new();
        s.set_dir(d.clone());
        let _ = std::fs::remove_file(d.join("stop.json"));
        assert_eq!(end_run(&s, Err(Box::new("boom"))), 30);
        assert_eq!(read(&d)["reason"], "panic");
        let s = control::Session::new();
        s.set_dir(d.clone());
        s.stopper.request(StopInfo::new(StopReason::Deadline, "--minutes reached"));
        assert_eq!(end_run(&s, Ok(Ok(()))), 0);
        assert_eq!(read(&d)["reason"], "deadline");
        let _ = std::fs::remove_dir_all(&d);
    }

    fn args(config: &Path, ov: Overrides, live: bool, canary: bool, campaign_dir: Option<PathBuf>) -> RunArgs {
        RunArgs { config: config.to_path_buf(), minutes: None, name: None, only: None, canary, live, ov, campaign_dir, env_file: None }
    }

    /// review F2: meta.json `config.normalized_sha256` hashes the file as loaded, so every override leaves it equal to
    /// `arbx provenance`'s (campaign.json's); the overrides themselves still apply to the run's config
    #[test]
    fn normalized_hash_ignores_the_command_line() {
        let path = Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-stage0.toml");
        let (loaded, raw) = config::Config::load_raw(&path).unwrap();
        let want = provenance::report(&path, &raw, &loaded, None)["config"]["normalized_sha256"].clone();
        assert!(want.is_string());
        let all = [
            Overrides::default(),
            Overrides { budget_left: Some(1_000_000), ..Default::default() },
            Overrides { budget_left: Some(99_999_999_999), ..Default::default() },
            Overrides { shadow: true, ..Default::default() },
            Overrides { shadow: true, budget_left: Some(0) },
        ];
        for ov in all {
            let rc = run_config(&args(&path, ov, false, false, None)).unwrap();
            assert_eq!(rc.config_json["normalized_sha256"], want, "{:?}", ov.json());
            assert_eq!(rc.config_json["file_sha256"], provenance::sha256_hex(&raw));
            assert_eq!((rc.config_json["mode"].as_str(), rc.config_json["effective_mode"].as_str()), (Some("shadow"), Some("shadow")));
            assert_eq!(rc.config_cap, 25_000_000, "the file's cap");
            // the overrides did apply to what the run uses
            if let Some(b) = ov.budget_left { assert_eq!(rc.cfg.live.max_failed_fees_lamports, b.min(25_000_000)); }
        }
        // a live config under --shadow: the file's mode is kept, the effective one is shadow
        let d = std::env::temp_dir().join(format!("arbx-runcfg-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&d).unwrap();
        let live_path = d.join("live.toml");
        std::fs::write(&live_path, String::from_utf8(raw.clone()).unwrap().replacen("mode = \"shadow\"", "mode = \"live\"", 1)).unwrap();
        let (l, lraw) = config::Config::load_raw(&live_path).unwrap();
        assert_eq!(l.mode, "live");
        let rc = run_config(&args(&live_path, Overrides { shadow: true, budget_left: Some(5), ..Default::default() }, false, false, None)).unwrap();
        assert_eq!((rc.config_json["mode"].as_str(), rc.config_json["effective_mode"].as_str(), rc.cfg.mode.as_str()), (Some("live"), Some("shadow"), "shadow"));
        assert_eq!(rc.config_json["normalized_sha256"], provenance::report(&live_path, &lraw, &l, None)["config"]["normalized_sha256"]);
        let _ = std::fs::remove_dir_all(&d);
    }

    /// review M3: the gate a run starts with, and what the route program's check does to it, for every combination
    #[test]
    fn the_send_gate_at_start() {
        use control::{GateMode, SendGate};
        let ok = Some((true, "route program X".to_string()));
        let bad = Some((false, "route program X: rate limited".to_string()));
        // (--shadow, --live, --canary, route check) -> (mode, reason, sticky)
        let cases: [(bool, bool, bool, Option<(bool, String)>, GateMode, &str, bool); 12] = [
            (false, true, false, ok.clone(), GateMode::Live, "", false),
            (false, false, true, ok.clone(), GateMode::Live, "", false),
            (false, true, false, None, GateMode::Live, "", false),
            (false, false, true, None, GateMode::Live, "", false),
            (false, true, false, bad.clone(), GateMode::Shadow, "program_hash_mismatch", true),
            (false, false, true, bad.clone(), GateMode::Shadow, "program_hash_mismatch", true),
            (false, false, false, ok.clone(), GateMode::Shadow, "mode_shadow", true),
            (false, false, false, bad.clone(), GateMode::Shadow, "mode_shadow", true),
            (false, false, false, None, GateMode::Shadow, "mode_shadow", true),
            (true, false, false, ok.clone(), GateMode::Shadow, "forced_shadow", true),
            (true, false, false, bad.clone(), GateMode::Shadow, "forced_shadow", true),
            (true, false, false, None, GateMode::Shadow, "forced_shadow", true),
        ];
        for (shadow, live, canary, check, mode, reason, sticky) in cases {
            let g = SendGate::new();
            initial_gate(&g, shadow, live, canary);
            let lines = apply_route_check(&g, check.clone(), live, canary);
            let what = format!("--shadow {shadow} --live {live} --canary {canary} check {:?}", check.as_ref().map(|c| c.0));
            assert_eq!((g.mode(), g.reason().as_str(), g.sticky()), (mode, reason, sticky), "{what}");
            assert_eq!(g.allows(), mode == GateMode::Live, "{what}");
            assert!(g.resume("try").is_ok() == (mode == GateMode::Live), "{what}: a start-up shadow cannot be resumed");
            let not_sending = lines.iter().any(|l| l.contains("NOT SENDING"));
            assert_eq!(not_sending, reason == "program_hash_mismatch", "{what}: {lines:?}");
            assert!(lines[0].ends_with(match check.as_ref().map(|c| c.0) { Some(true) => ": ok", Some(false) => ": MISMATCH", None => "recorded, not checked" }), "{lines:?}");
        }
    }

    /// review F1, a structural guard on `run`'s boot order (it needs RPC and a gRPC server, so it is not run here): the
    /// state stream starts right after the account snapshot, before the route program, the send paths, the executor
    /// and meta.json; the transaction feeds start after meta.json; the venue programs are hashed after that
    #[test]
    fn the_state_stream_starts_right_after_the_snapshot() {
        let src = include_str!("main.rs");
        let body = &src[src.find("\nfn run(a: &RunArgs").expect("run")..];
        let body = &body[..body.find("\n#[cfg(test)]").unwrap_or(body.len())];
        let at = |needle: &str| body.find(needle).unwrap_or_else(|| panic!("{needle} not in run()"));
        let order = ["for chunk in arr.chunks(", "feeds::start_state(", "provenance::route_spec(", "send::Paths::new(", "exec::Exec::new(",
            "write_atomic(&dir.join(\"meta.json\")", "feeds::start(&cfg.feeds", "fetch_programs_cached(", "engine::Engine::new("];
        for w in order.windows(2) { assert!(at(w[0]) < at(w[1]), "{} must come before {}", w[0], w[1]); }
        // nothing that waits on the network between the snapshot and the stream
        let gap = &body[at("anyhow::Ok((reg, store, slot))")..at("feeds::start_state(")];
        assert!(!gap.contains("block_on") && !gap.contains(".await"), "{gap}");
    }

    /// WP-03b (PLAN-ADDENDUM I-1), a structural guard on `run`: the budgets and the boot policy are set before the first
    /// boot call (pools, snapshot) and stay on through the route program and the executor; the chain-fetch taps are
    /// installed before the state stream starts; the service's settings reach meta.json
    #[test]
    fn the_boot_policy_spans_the_boot_and_the_taps_precede_the_stream() {
        let src = include_str!("main.rs");
        let body = &src[src.find("\nfn run(a: &RunArgs").expect("run")..];
        let body = &body[..body.find("\n#[cfg(test)]").unwrap_or(body.len())];
        let at = |needle: &str| body.find(needle).unwrap_or_else(|| panic!("{needle} not in run()"));
        let order = ["rpc_reg.set_limit(", "rpc.set_phase(rpc::Phase::Boot)", "rpc.prewarm()", "pools::boot(&rpc", "rpc.accounts(chunk)", "chainfetch::start(",
            "feeds::start_state(", "provenance::route_spec(", "exec::Exec::new(", "rpc.set_phase(rpc::Phase::Run)", "write_atomic(&dir.join(\"meta.json\")"];
        for w in order.windows(2) { assert!(at(w[0]) < at(w[1]), "{} must come before {}", w[0], w[1]); }
        assert!(body.contains("\"chainfetch\": cf_meta"), "meta.json `chainfetch`");
        assert!(body.contains("rpc.with_role(rpc::Role::Engine)") && body.contains("rpc.with_role(rpc::Role::Leaders).with_own_phase(rpc::Phase::Run)"), "per-role clients");
        assert!(body.contains("gate.shadow(\"chainfetch_dead\""), "the watchdog closes the SendGate");
    }

    /// review F3: a supervised segment needs its control socket (the supervisor pauses through it): refused before
    /// anything starts
    #[test]
    fn a_supervised_segment_needs_its_control_socket() {
        let d = std::env::temp_dir().join(format!("arbx-nosock-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&d).unwrap();
        let src = std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-stage0.toml")).unwrap();
        assert!(src.contains("[control]"), "the stage-0 config has a [control] section");
        let p = d.join("nosock.toml");
        std::fs::write(&p, src.replacen("socket = true", "socket = false", 1)).unwrap();
        assert!(!config::Config::load(&p).unwrap().control.socket);
        let sess = control::Session::new();
        let e = run(&args(&p, Overrides::default(), false, false, Some(d.join("camp"))), &sess).unwrap_err();
        assert!(e.to_string().contains("needs its control socket"), "{e}");
        assert!(!d.join("camp").exists(), "refused before the segment directory");
        let _ = std::fs::remove_dir_all(&d);
    }

    /// PLAN-ADDENDUM I-6: `[alts] preload = "auto"` finds the newest sibling segment's alts-final and reads its tables
    /// (gaps kept); "" preloads nothing; an explicit path is read as given
    #[test]
    fn alts_preload_reads_the_previous_segments_tables() {
        let root = std::env::temp_dir().join(format!("arbx-alts-preload-{}-{}", std::process::id(), now_ns()));
        let (old, prev, me) = (root.join("c-p1"), root.join("c-p2"), root.join("c-p3"));
        for d in [&old, &prev, &me] { std::fs::create_dir_all(d).unwrap(); }
        let k = |n: u8| tx::b58(&[n; 32]);
        let write = |dir: &Path, lines: &str| {
            let z = zstd::stream::encode_all(lines.as_bytes(), 3).unwrap();
            std::fs::write(dir.join("alts-final.jsonl.zst"), z).unwrap();
        };
        write(&old, &format!("{{\"table\":\"{}\",\"addrs\":[\"{}\"]}}\n", k(1), k(2)));
        std::thread::sleep(std::time::Duration::from_millis(20));
        // review WP-04 #11: tables used more than 24 h ago are left out, the most recently used kept first (at most
        // preload_max_tables); a table without last_used_ns counts as used when its file was written
        let now = now_ns();
        let h = 3_600_000_000_000u64;
        write(&prev, &format!("{{\"schema\":\"arbx.alts-final/1.1\"}}\n{{\"table\":\"{}\",\"addrs\":[\"{}\",null,\"{}\"],\"last_used_ns\":{}}}\n\
            {{\"table\":\"{}\",\"addrs\":[\"{}\"],\"last_used_ns\":{}}}\n{{\"table\":\"{}\",\"addrs\":[\"{}\"],\"last_used_ns\":null}}\n\
            {{\"table\":\"{}\",\"addrs\":[\"{}\"],\"last_used_ns\":{}}}\n", k(3), k(4), k(5), now - h, k(6), k(7), now - 25 * h, k(8), k(9), k(10), k(11), now - 2 * h));
        let cfg = config::AltsCfg::default();
        let (file, tables, held) = alts_preload(&cfg, &me, now).expect("found");
        assert_eq!(file, prev.join("alts-final.jsonl.zst"), "the newest sibling");
        assert_eq!(held, 4);
        assert_eq!(tables.iter().map(|t| t.0).collect::<Vec<_>>(), vec![[8u8; 32], [3u8; 32], [10u8; 32]], "the 25 h old one left out; newest first");
        assert_eq!(tables[1], ([3u8; 32], vec![Some([4u8; 32]), None, Some([5u8; 32])], Some(now - h)));
        let (_, capped, _) = alts_preload(&config::AltsCfg { preload_max_tables: 2, ..cfg.clone() }, &me, now).unwrap();
        assert_eq!(capped.len(), 2);
        assert!(alts_preload(&config::AltsCfg { preload: String::new(), ..cfg.clone() }, &me, now).is_none());
        let (_, t, _) = alts_preload(&config::AltsCfg { preload: old.join("alts-final.jsonl.zst").display().to_string(), ..cfg }, &me, now).unwrap();
        assert_eq!(t[0].0, [1u8; 32]);
        let _ = std::fs::remove_dir_all(&root);
    }
}

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
use arbx::{alerts, build, campaign, chainfetch, config, engine, exec, feeds, leaders, ledger, pda, pools, probe, provenance, reads, rec, replay, rpc, runtime, send, store, tx, venues, wallet, watchdog};
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
    /// (WP-05: the built-to-fail canaries are gone; a canary is a small live run, `arbx run --canary`)
    Simcheck {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        #[arg(long, default_value_t = 40)] max: usize,
        #[arg(long, default_value_t = 0.01)] size_sol: f64,
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
        /// a canary run: live bundles under `[canary]`'s caps (at most 0.2 SOL a trade); needs `[canary] enabled = true` too
        #[arg(long)] canary: bool,
        /// go-live gate item 4: build and sign every would-send bundle with a throwaway key made in memory (never the
        /// trading keystore), record it in full (attempts.jsonl `dry_run`) and never send it; no send path is built
        #[arg(long)] dry_run: bool,
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
        /// WP-07: at a stop, wait at most this long for the attempts still open to settle (their wallet records, the
        /// block engine's results, the expiry checks: longer than a blockhash's validity) before listing them as
        /// unsettled in stop.json; then the stop snapshot and the final reconciliation
        #[arg(long, default_value_t = 60)]
        drain_s: u64,
        /// WP-07: the campaign's equity floor, lamports of SOL + WSOL (`arbx campaign` passes it once the campaign's start
        /// is known): the segment stops (`equity_floor`, exit 20) below it; the highest of the floors applies
        #[arg(long)]
        equity_floor: Option<i64>,
    },
    /// WP-07: the campaign supervisor (on the server it replaces deploy/run-w.sh: Cherry gets only this binary, its
    /// config and data). It freezes the binary and the config into <runs>/<name>/, runs segments of --segment-min back to
    /// back for --hours (each `arbx run` of the frozen copies, started only once the previous segment's process has
    /// exited: Haan grants its streams to the first process, I-3), passes each what is left of the test budget, applies
    /// the campaign-wide equity stops (the start read from the chain: SOL + WSOL, each token, the rent), and writes
    /// campaign.json, events.jsonl, supervisor.jsonl and spend.json. Controls: <runs>/<name>.pause, .next, .stop (a
    /// reason inside)
    Campaign {
        #[arg(long)] name: String,
        #[arg(long)] config: PathBuf,
        #[arg(long)] hours: f64,
        #[arg(long, default_value_t = 60.0)] segment_min: f64,
        /// what every segment does: shadow (records only, the default), dry-run, canary, live
        #[arg(long, default_value = "shadow")] mode: String,
        /// the campaign's test budget, lamports (at most 34,000,000: the owner's hard cap, docs/field-tests/BUDGET.md);
        /// default the config's `[supervisor] test_budget_lamports`. Required for canary and live
        #[arg(long)] test_budget_lamports: Option<u64>,
        /// who started it (campaign.json `operator`)
        #[arg(long)] who: Option<String>,
        /// the runs directory (default: the config's out_dir)
        #[arg(long)] runs: Option<PathBuf>,
        /// stop after this many segments
        #[arg(long)] max_segments: Option<u32>,
        /// the .env the segments load (default: `.env` beside the config given; a path, never read here)
        #[arg(long)] env_file: Option<PathBuf>,
        /// each segment's `--drain-s`
        #[arg(long, default_value_t = 60)] drain_s: u64,
        /// run in the background, detached from the terminal (its log: <runs>/<name>/supervisor.log)
        #[arg(long)] detach: bool,
        /// start although something may hold the provider (a live segment socket, another `arbx … run` or `arb-lab … run`
        /// process: Haan serves the first process only, I-3), and do not wait for it between segments; recorded in
        /// campaign.json `forced`. Only when you know nothing else uses the provider
        #[arg(long)] force: bool,
        /// (tests) the control-file poll and the back-off after a crash
        #[arg(long, hide = true, default_value_t = 2000)] poll_ms: u64,
        #[arg(long, hide = true, default_value_t = 10)] backoff_s: u64,
    },
    /// WP-07: a campaign's money from its segments' files (`ledger::history`, the code the segments and `arbx campaign`
    /// use): the start, SOL + WSOL now, the rolling drops, the floor, the spend (JSON). Reads only
    CampaignEquity {
        #[arg(long)] campaign_dir: PathBuf,
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
    /// replaced and the exit code is 3. A plan limit (ResourceExhausted `<LIMIT> exceeded: n/m`) is a refusal
    /// (`refused_plan_limit`, its numbers recorded): it never keeps probe.json from being written
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
    /// Replay a recorded run (PLAN WP-09): the run's engine rebuilt offline from its boot records, registry (pools.json,
    /// registry-run.json) and frozen config, fed its journal in order at the journaled times; a shadow or dry-run
    /// executor rebuilt offline from its exec_init record (no RPC, no send path, no key). Nothing is sent. Writes the
    /// replay's own streams, replay.json and (--compare) replay-diff.json into --out. Recordings made before WP-03 cannot
    /// be replayed. Exit code: 0 a whole replay and (--compare) no difference; 1 differences, or a replay that is not
    /// whole (journal or accounts.bin gaps, missing account records, store verdicts not reproduced, recorder drops, an
    /// executor not replayed: replay.json `not_whole`); 2 refused
    Replay {
        /// the segment's run directory
        #[arg(long)] run: PathBuf,
        /// compare only decisions whose trigger slot is at least this (the replay starts at the boot all the same)
        #[arg(long)] from_slot: Option<u64>,
        /// stop once the chain tip passes this slot
        #[arg(long)] to_slot: Option<u64>,
        /// the run's frozen config (default: <run>/config.toml)
        #[arg(long)] config: Option<PathBuf>,
        /// the run's registry (default: <run>/pools.json; its registry-run.json beside it)
        #[arg(long)] pools: Option<PathBuf>,
        /// a new directory the replay records into (refused if it exists; default: ./replay-<run>-<unix time>-<pid>)
        #[arg(long)] out: Option<PathBuf>,
        /// diff the decisions and commit groups against the run's into replay-diff.json
        #[arg(long)] compare: bool,
        /// re-price every opportunity's best route at these fractions of its size and/or `opt` (X3), e.g. 0.5,0.25,0.125,opt
        #[arg(long, value_delimiter = ',')] reprice_sizes: Vec<String>,
        /// what-if: strategy.<field>=<v>, state.<knob>=<v>, alts.<knob>=<v>, accuracy.ring_versions=<v>, min_tip=<v>, tips.<field>=<v>,
        /// cu.min_samples=<v> (repeatable)
        #[arg(long = "set")] set: Vec<String>,
    },
    /// Price one route at one recorded state version of a run (PLAN WP-09 item 3; the toolkit's R4, R8): the run replayed
    /// up to the version, then the engine's own pricing. --version: an accounts.bin aseq, slot:write_version, a transaction
    /// signature (its post-state) or pre:<signature>. --batch: JSON lines {id, route, version, size} in, JSON lines out.
    /// Exit code: 0 every answer priced, 1 one was not, 2 refused
    Quote {
        /// the segment's run directory
        #[arg(long)] run: PathBuf,
        /// buy,sell,mint (base58)
        #[arg(long)] route: Option<String>,
        /// aseq (or aseq:N), slot:write_version, <signature> or pre:<signature>
        #[arg(long)] version: Option<String>,
        /// lamports
        #[arg(long)] size: Option<u64>,
        /// a file of questions, one JSON line each: {"id", "route", "version", "size"}
        #[arg(long)] batch: Option<PathBuf>,
        /// the run's frozen config (default: <run>/config.toml)
        #[arg(long)] config: Option<PathBuf>,
        /// the run's registry (default: <run>/pools.json; its registry-run.json beside it)
        #[arg(long)] pools: Option<PathBuf>,
    },
    /// The watchdog (PLAN-ADDENDUM WP-20): a long-running process that watches the runs directory (`[watchdog]`) and
    /// tells Telegram (`[alerts]`) whether a segment runs: "running" every `status_min`, "NOT running" when no segment
    /// process has been alive for `grace_s` or the running one's status.jsonl is `stale_s` old, "back up" when it
    /// recovers. One per runs directory (a lock). Reads only the runs directory and /proc; sends no transaction. Stops on
    /// SIGINT or SIGTERM (exit 0)
    Watchdog {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        /// the .env to load (default: the .env beside the config)
        #[arg(long)] env_file: Option<PathBuf>,
        /// look once, print the verdict as JSON and exit (0 running, 1 not); sends nothing and takes no lock
        #[arg(long)] once: bool,
    },
    /// Send one test message through `[alerts]` (whatever its `enabled` says) and print whether it went out. Never prints
    /// the token or the chat id. Exit 0 sent, 1 not
    AlertTest {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        /// the .env to load (default: the .env beside the config)
        #[arg(long)] env_file: Option<PathBuf>,
    },
    /// Post an operator's note to the alerts' chat now (`[alerts]`, whatever its `enabled` says): a field test's goal when
    /// it starts and its result when it ends (docs/field-tests/README.md). The first line is the title; the text is
    /// escaped (no markup). Never prints the token or the chat id. Exit 0 sent, 1 not
    Notify {
        #[arg(long, default_value = "arb.toml")] config: PathBuf,
        /// the .env to load (default: the .env beside the config)
        #[arg(long)] env_file: Option<PathBuf>,
        /// the note (its first line is the title)
        #[arg(long)] text: String,
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
            // the .env beside the config, as `run` loads it: the I-10 key-material check reads the keys it names (never
            // printing them)
            load_env(&config);
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
            println!("lookup tables: retries {:?} ms then every {} s, give up after {} s, at most {} waiting, {} tables fetched at once, preload {:?} (used in the last {} h, at most {}); accuracy {} ({} versions per account)",
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
            // FT-000: the reserved shares, the lookup tables' batching and cache, the wallet cursor, exec.jsonl's sampling
            let res: Vec<String> = cf.reserves(&all).iter().map(|(p, r, rate)| format!("{} {:.2}/s of {p}", r.as_str(), rate)).collect();
            println!("reserved shares: {}; lookup tables: {} a request at most every {} ms ({} at once), cache {} tables / {} MiB; wallet cursor {:?}; exec.jsonl keeps 1 in {} unwatched",
                if res.is_empty() { "none".to_string() } else { res.join(", ") }, cfg.alts.batch_max, cfg.alts.call_every_ms, cfg.alts.calls_inflight,
                cfg.alts.max_tables, cfg.alts.max_mb, cf.wallet_cursor, cfg.record.exec_unwatched_sample);
            let payer = bs58::decode(&cfg.wallet).into_vec().ok().and_then(|b| tx::Pk::try_from(b).ok());
            let mut keys_checked = 0;
            for s in &cfg.sends {
                let tip = match (s.kind, s.tip_share, s.tip_lamports) {
                    // WP-06: a bundle tips [tips] by band (its floor is the path's minimum)
                    (config::SendKind::JitoBundle, _, l) => format!("[tips] by band {:?} of the edge, {}..{} lamports (path minimum {l})", cfg.tips.shares, cfg.tips.floor, cfg.tips.cap),
                    (_, Some(x), l) => format!("{:.0}% of the edge, {l}..{} lamports", x * 100.0, s.tip_max_lamports.unwrap_or(u64::MAX)),
                    (_, None, 0) => "no tip".into(),
                    (_, None, l) => format!("tip {l} lamports"),
                };
                let rate = s.max_per_sec.map(|n| format!(", max {n}/s")).unwrap_or_default();
                println!("  send {:<20} {:?} {tip}{rate}{}", s.name, s.kind, if s.enabled { "" } else { " (disabled)" });
                // PLAN-ADDENDUM I-10: a secret over plain http only with a recorded exception; no provider key is the payer's
                if s.enabled { if let Some(note) = config::cleartext_check(s)? { println!("    I-10 exception: {note}"); } }
                if let Some(p) = &payer { keys_checked += send::check_key_material(s, p)?; }
            }
            println!("I-10: no secret over plain http or udp (in the URL or a header) without a recorded exception (above); {keys_checked} values a provider key could be checked (URL variables and parts, header keys, block engine keypairs): none is the payer's keypair");
            let on: Vec<&str> = cfg.sends.iter().filter(|s| s.enabled).map(|s| s.name.as_str()).collect();
            println!("enabled send paths: {}{}", if on.is_empty() { "none".to_string() } else { on.join(", ") },
                if config::bundle_only(&cfg.sends).is_ok() { " (bundle-only: a live or canary run may start)" } else { " (NOT bundle-only: live and canary runs refuse to start)" });
            let (s, l, sp) = (&cfg.strategy, &cfg.live, &cfg.send_policy);
            println!("safety: decoded swaps are hints only, skip_failing_signers {}, state_triggers {}; live: max {} SOL a trade, stop after {} lamports of failed fees; canary: {} SOL, {} attempts",
                s.skip_failing_signers, s.state_triggers, l.max_size_sol, l.max_failed_fees_lamports, cfg.canary.size_sol,
                if cfg.canary.count == 0 { "no cap on".to_string() } else { cfg.canary.count.to_string() });
            // WP-06: the builder
            let b = &cfg.builder;
            // the CU table where this machine has it (the configured path, or the repo's data/ copy): a table that does not
            // parse fails the check; a missing one is read at start (a run without it refuses to start)
            let cu = if b.cu_table.is_empty() { "none (every route the fallback formula)".to_string() } else {
                let p = Path::new(&b.cu_table);
                let repo_copy = config.parent().and_then(|d| d.parent()).zip(p.file_name()).map(|(d, f)| d.join("data").join(f));
                match std::iter::once(p.to_path_buf()).chain(repo_copy).find(|c| c.is_file()) {
                    Some(c) => {
                        let t = arbx::cu_table::CuTable::load(&c.to_string_lossy()).map_err(|e| anyhow::anyhow!("[builder] cu_table: {e}"))?;
                        format!("{}: {} legs, overhead n {}, source {}", c.display(), t.legs.len(), t.overhead.n, t.source.clone().unwrap_or_else(|| t.source_runs.join(",")))
                    }
                    None => format!("{} not on this machine (read at start: a run without it refuses to start)", b.cu_table),
                }
            };
            // review WP-06 #1, #9: whether a trade can leave an account (and its rent) behind
            let accounts = if !b.create_close { "none created: routes through a token the wallet holds no account for are refused (mid_not_held, the held-only arm)".to_string() }
                else if b.held_max == 0 { "created and closed in the same transaction (rent-neutral: nothing stays locked); held-set additions off (held_max = 0)".to_string() }
                else { format!("created and closed in the same transaction; HELD-SET ADDITIONS ON (held_max = {}): an oversized bundle may keep its account, locking up to {} lamports \
                    of rent each, only when the expected profit covers min_profit + that rent and the recoverable rent plus it stays within the rent cap ([supervisor] \
                    rent_cap_sol {} SOL) (the go-live gate wants nothing locked: an owner decision)", b.held_max, arbx::build::HELD_RENT_BOUND, cfg.supervisor.rent_cap_sol) };
            println!("builder (WP-06): new token accounts {accounts}; \
                PumpSwap volume accumulator creation {}; loaded-data limit {}; CU table {} (cells under {} samples: the fallback); lookup-table index {} (max {}); payer guard {}; bands {:?}",
                if b.allow_uva_create { "ALLOWED" } else { "refused (uva_missing)" },
                match b.loaded_limit() { None => "off".to_string(), Some(None) => "auto".to_string(), Some(Some(n)) => format!("{n} bytes") }, cu, b.cu_min_samples, b.alt_index, b.max_alts,
                if b.payer_guard { format!("on, max drop {}", b.payer_guard_max_drop) } else { "off".into() }, cfg.bands.edges);
            // WP-07: the ledger, the equity stops (OD-11), the bankroll cap
            let (lg, sv) = (&cfg.ledger, &cfg.supervisor);
            println!("ledger (WP-07): snapshots at start, every {} min inside the segment and at stop; the money view stale (nothing sent: equity_stale) past {} s, after {} failed snapshots in a row, or a landing {} s without its record; reconciliation within {} lamports on both bases ({} s after each snapshot); tokens valued at the pools' quote less {:.0}%; extra token accounts {:?}",
                lg.snapshot_min, lg.max_view_age_s, lg.stale_after_failures, lg.max_record_wait_s, lg.tolerance_lamports, lg.recon_grace_s, lg.token_haircut * 100.0, lg.extra_mints);
            println!("equity stops (WP-07, OD-11; basis: the net spend since the campaign's start, fees + tips + non-recoverable rent - the trading result, the owner's transfers not in it; each token its own floor, rent apart): shadow and stop the campaign when the net spend passes {} SOL within an hour, {} SOL within 24 h, or {}; a token moved by routes below its start less {:.2}%; test budget {} lamports a run (hard cap {} in all tests: <out_dir>/budget-state.json); rent cap {} SOL (on held-set additions only: a create+close locks nothing); native SOL alert under {} SOL",
                sv.max_drop_per_hour_sol, sv.max_drop_per_day_sol, if sv.test_budget_lamports > 0 { format!("{} lamports since the start", sv.test_budget_lamports) } else { "the budget given (--budget-left; none here)".into() },
                sv.token_floor_tolerance * 100.0, sv.test_budget_lamports, config::TEST_BUDGET_HARD_CAP, sv.rent_cap_sol, sv.native_floor_sol);
            if l.bankroll_share > 0.0 { println!("bankroll (WP-07): a trade at most {:.0}% of the liquid SOL + WSOL - {} SOL, and at most the WSOL", l.bankroll_share * 100.0, l.bankroll_reserve_sol); }
            println!("send policy (WP-05): live and canary sends are one-transaction bundles, fail closed; blockhash {} at most {} slots old; skip leaders {:?}; in-flight hold {} slots; queue {} ms; >=1M bands at {}/s; crowding {:?} over {} h, crowded list {}; on-chain margin max({}, {} x net); dry run simulate {}",
                sp.blockhash_commitment, sp.max_blockhash_age_slots, sp.skip_leader_kinds, sp.inflight_hold_slots, sp.queue_ms, sp.big_band_max_per_sec, sp.crowding_buckets,
                sp.crowding_window_h, if sp.crowded_pools_file.is_empty() { "none".to_string() } else { sp.crowded_pools_file.clone() }, sp.margin_floor, sp.margin_share, cfg.dry_run.simulate);
            if sp.crowded_skip_min_expected_lamports > 0 { println!("  crowded pools not sent from {} lamports expected", sp.crowded_skip_min_expected_lamports); }
            // FT-006: the BAM landing fix
            let bp = &sp.bam;
            if bp.enabled {
                println!("  BAM-led slots (FT-006): bid at least {} lamports per CU of the CU limit, within {:.0}% of the edge and the decision's bar; out of reach: {}; Jito-led slots bid the band's tip",
                    bp.min_tip_per_cu, bp.max_share * 100.0, if bp.below_floor == "skip" { "not sent (bam_bid_below_floor)" } else { "bid what the edge allows" });
            } else { println!("  BAM-led slots: the band's tip, as Jito-led ones ([send_policy.bam] off)"); }
            // review N3: the crowded list, where this machine has it (the configured path, or the repo's data/ copy)
            if !sp.crowded_pools_file.is_empty() {
                let p = Path::new(&sp.crowded_pools_file);
                let repo_copy = config.parent().and_then(|d| d.parent()).zip(p.file_name()).map(|(d, f)| d.join("data").join(f));
                match std::iter::once(p.to_path_buf()).chain(repo_copy).find(|c| c.is_file()) {
                    Some(c) => println!("  crowded list {}: {} pools", c.display(), exec::load_crowded_pools(&c.to_string_lossy())?.len()),
                    None => println!("  crowded list not on this machine (loaded at start; a bad list stops the run)"),
                }
            }
            if let Some(w) = cfg.pricing_warning() { println!("{w}"); }
            // PLAN-ADDENDUM WP-21: the CLMM venues' switches (off: not read; quote: priced and monitored, never sent live)
            let note = |m: &str| match m { "off" => "its seed-list rows are not read", "quote" => "priced, decided and monitored; shadow and dry runs build its bundles; live and canary sends refused (venue_quote_only)", _ => "traded" };
            println!("venues (WP-21): Raydium CLMM {} ({}); Orca Whirlpool {} ({}); PumpSwap, Raydium CPMM and AMM v4, DLMM, DAMM v2 traded",
                cfg.pools.rayclmm, note(&cfg.pools.rayclmm), cfg.pools.whirlpool, note(&cfg.pools.whirlpool));
            let e = &cfg.exec;
            println!("route program {}: {}", e.program, if e.expected_program_sha256.is_empty() && e.expected_program_md5.is_empty() { "no expected hash (recorded, not checked)".to_string() }
                else { format!("expected sha256 {} md5 {} (checked at start; a mismatch refuses live sends)", e.expected_program_sha256, e.expected_program_md5) });
            println!("control socket {}", if cfg.control.socket { "on" } else { "off" });
            let r = &cfg.record;
            println!("recorder (always on): disk budget {} GB per segment, min free {} GB, rotate at {} MiB or {} min, frames every {} ms, zstd {}, archived feeds {}; background runtime {} threads",
                r.disk_budget_gb, r.min_free_gb, r.rotate_mb, r.rotate_min, r.flush_ms, r.zstd_level,
                if r.archive_feeds.is_empty() { "none".to_string() } else { r.archive_feeds.join(",") }, cfg.runtime.bg_threads);
            // WP-08: the LeaderBook's telemetry and I-9's sampling. The geo table where this machine has it (the configured
            // path, or the repo's data/ copy): a table that does not parse fails the check; a missing one is loaded at start
            println!("rivals.jsonl: 1 in {} `why = venues` rows kept (by signature){}", r.rivals_venues_sample, if r.rivals_venues_sample == 1 { " (all)" } else { "" });
            if cfg.leaders.enabled {
                let l = &cfg.leaders;
                println!("leaders telemetry: RTT probe {}; geo table {}", if l.rtt_probe { format!("on, at most {} handshakes/s (host -> TPU-QUIC endpoint)", l.rtt_per_sec) } else { "off".into() },
                    l.geo_table);
                let p = Path::new(&l.geo_table);
                let repo_copy = config.parent().and_then(|d| d.parent()).zip(p.file_name()).map(|(d, f)| d.join("data").join(f));
                match std::iter::once(p.to_path_buf()).chain(repo_copy).find(|c| c.is_file()) {
                    Some(c) => { let g = leaders::Geo::load(&c)?; let (regions, cities) = g.counts();
                        println!("  geo table {}: {} ranges, {cities} cities in {regions} regions", c.display(), g.len()); }
                    None => println!("  geo table not on this machine (loaded at start; without it regions stay null)"),
                }
            }
            // WP-20: the alerts and the watchdog (the variables are named here, never read)
            let al = &cfg.alerts;
            println!("alerts: {} (Telegram; token from ${}, chat from ${}): at most {} messages a minute, dedup {} s, min level {}, coalesce {} ms, heartbeat {}, daily summary {}{}",
                if al.enabled { "on" } else { "off" }, al.token_env, al.chat_env, al.rate_per_min, al.dedup_s, al.min_level, al.coalesce_ms,
                if al.heartbeat_min == 0 { "off".to_string() } else { format!("every {} min", al.heartbeat_min) }, if al.daily_summary { "on" } else { "off" },
                if al.low_balance_sol > 0.0 { format!(", low balance under {} SOL", al.low_balance_sol) } else { String::new() });
            let w = &cfg.watchdog;
            println!("watchdog: watches {} (not running after {} s without a segment process, or a status.jsonl {} s old, or {} s of boot); running every {} min; looks every {} s",
                w.dir(&cfg.out_dir).display(), w.grace_s, w.stale_s, w.boot_s, w.status_min, w.poll_s);
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
                let (reg, drops) = pools::boot(&rpc, &cands, seeds, ours).await?;
                println!("{} candidates -> {}", cands.len(), reg.summary());
                // the candidates not kept, with why (WP-16 review F8)
                println!("dropped: {}", pools::drops_json(&drops)["counts"]);
                for d in &drops { println!("  {:?} {} {}{}", d.venue, d.pool, d.why, d.mint.as_ref().map_or(String::new(), |m| format!(" (mint {m})"))); }
                for (k, v) in &reg.pairs {
                    let mint = if k.0 == *venues::WSOL { k.1 } else { k.0 };
                    let names: Vec<String> = v.iter().map(|&i| format!("{:?}:{}", reg.pools[i].venue, pools::show(&reg.pools[i].pool))).collect();
                    println!("  {} {}", pools::show(&mint), names.join(" "));
                }
                Ok(())
            })
        }
        Cmd::Run { config, minutes, name, only, canary, dry_run, live, shadow, budget_left, campaign_dir, env_file, drain_s, equity_floor } => {
            let a = RunArgs { config, minutes, name, only, canary, dry_run, live, ov: Overrides { shadow, budget_left }, campaign_dir, env_file, drain_s, equity_floor };
            let sess = control::Session::new();
            control::install_panic_hook(sess.clone());
            // WP-20: a main-thread panic sends a Critical alert after stop.json is written (best effort, bounded)
            alerts::install_panic_hook();
            let res = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| run(&a, &sess)));
            std::process::exit(end_run(&sess, res))
        }
        Cmd::WaitSignal { dir, minutes, panic, fail_after_stop } => {
            let sess = control::Session::new();
            control::install_panic_hook(sess.clone());
            let res = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| wait_signal(&dir, minutes, panic, fail_after_stop, &sess)));
            std::process::exit(end_run(&sess, res))
        }
        Cmd::Campaign { name, config, hours, segment_min, mode, test_budget_lamports, who, runs, max_segments, env_file, drain_s, detach, force, poll_ms, backoff_s } => {
            let o = campaign::Opts { name, config, hours, segment_min, mode, test_budget: test_budget_lamports, who, runs, max_segments, env_file, drain_s, force,
                poll: std::time::Duration::from_millis(poll_ms.max(10)), backoff: std::time::Duration::from_secs(backoff_s) };
            std::process::exit(campaign::main(o, detach)?)
        }
        Cmd::CampaignEquity { campaign_dir } => {
            println!("{}", serde_json::to_string_pretty(&campaign::equity_json(&campaign_dir, now_ns()))?);
            Ok(())
        }
        Cmd::Watchdog { config, env_file, once } => {
            let note = match &env_file { Some(f) => load_env_file(f), None => { load_env(&config); None } };
            let cfg = config::Config::load(&config)?;
            let runs = cfg.watchdog.dir(&cfg.out_dir);
            if once {
                let (v, up) = watchdog::once(&runs, &cfg.watchdog);
                println!("{}", serde_json::to_string_pretty(&v)?);
                std::process::exit(if up { 0 } else { 1 });
            }
            std::process::exit(watchdog::run(&cfg.alerts, &cfg.watchdog, &runs, note)?)
        }
        Cmd::AlertTest { config, env_file } => {
            if let Some(n) = match &env_file { Some(f) => load_env_file(f), None => { load_env(&config); None } } { eprintln!("{n}"); }
            let cfg = config::Config::load(&config)?;
            if !cfg.alerts.enabled { println!("note: [alerts] enabled = false in {}: runs of this config send no alerts", config.display()); }
            let what = format!("arbx alert-test from {} (build {}, config {})", provenance::hostname(), provenance::build_short(), config.display());
            match alerts::send_test(&cfg.alerts, &alerts::env_var, &what, std::time::Duration::from_secs(15)) {
                Ok(line) => { println!("{line}"); Ok(()) }
                Err(e) => { println!("failed: {e}"); std::process::exit(1) }
            }
        }
        Cmd::Notify { config, env_file, text } => {
            if let Some(n) = match &env_file { Some(f) => load_env_file(f), None => { load_env(&config); None } } { eprintln!("{n}"); }
            let cfg = config::Config::load(&config)?;
            match alerts::send_note(&cfg.alerts, &alerts::env_var, &text, std::time::Duration::from_secs(15)) {
                Ok(line) => { println!("{line}"); Ok(()) }
                Err(e) => { println!("failed: {e}"); std::process::exit(1) }
            }
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
        Cmd::Simcheck { config, max, size_sol } => simcheck(&config, max, size_sol),
        Cmd::SignerStats { action, into, runs } => {
            anyhow::ensure!(action == "merge", "signer-stats: the only action is `merge`");
            anyhow::ensure!(!runs.is_empty(), "signer-stats merge: name the run directories");
            for (r, signers, n) in engine::merge_signer_stats(&into, &runs)? { println!("{r}: {signers} signers, {n} outcomes added to {}", into.display()); }
            Ok(())
        }
        Cmd::GrpcProbe { config, seconds, out, only, force } => grpc_probe(&config, seconds, out, only, force),
        // ---- WP-09: replay and quote (src/replay.rs); a refused recording exits 2
        Cmd::Replay { run, from_slot, to_slot, config, pools, out, compare, reprice_sizes, set } => {
            let parsed = (|| -> Result<replay::Opts> {
                Ok(replay::Opts { from_slot, to_slot, config, pools, out, compare, sets: set.iter().map(|s| s.parse()).collect::<Result<_>>()?,
                    reprice: reprice_sizes.iter().map(|s| s.parse()).collect::<Result<_>>()? })
            })();
            match parsed.and_then(|o| replay::cli_replay(&run, &o)) {
                Ok(code) => std::process::exit(code),
                Err(e) => { eprintln!("arbx replay: {e:#}"); std::process::exit(2) }
            }
        }
        Cmd::Quote { run, route, version, size, batch, config, pools } => {
            match replay::cli_quote(&run, config.as_deref(), pools.as_deref(), route.as_deref(), version.as_deref(), size, batch.as_deref()) {
                Ok(code) => std::process::exit(code),
                Err(e) => { eprintln!("arbx quote: {e:#}"); std::process::exit(2) }
            }
        }
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
            let blob = wallet::encrypt(&secret, p1.as_bytes(), wallet::V3_LOG_N)?;
            let key = wallet::keypair(&wallet::decrypt(&blob, p1.as_bytes())?)?;
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
            let key = wallet::keypair(&wallet::decrypt(&blob, pass.as_bytes())?)?;
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

/// the run's mode as the budget state names it
fn mode_name(live: bool, canary: bool) -> &'static str { if live { "live" } else if canary { "canary" } else { "shadow" } }

/// WP-07: the accounts every balance snapshot reads besides the wallet: its WSOL account, its ATAs of the mints it held
/// at boot (the executor's read) and of `[ledger] extra_mints` (USDC, USDT; each with its registry token program, SPL
/// Token otherwise), the configured nonce accounts and lookup tables (counted only when the wallet is their authority),
/// its PumpSwap accumulator. The token accounts its transactions touch join them as they come
fn ledger_candidates(cfg: &config::Config, reg: &pools::Registry, held: &[String], wallet: &tx::Pk) -> Vec<tx::Pk> {
    let progs: std::collections::HashMap<tx::Pk, tx::Pk> = reg_mints(reg).into_iter().collect();
    let prog = |m: &tx::Pk| progs.get(m).copied().unwrap_or(*pda::TOKEN_PROGRAM);
    let mut out = vec![build::ata_of(wallet, &venues::WSOL, &pda::TOKEN_PROGRAM)];
    for m in held.iter().chain(cfg.ledger.extra_mints.iter()).filter_map(|m| bs58::decode(m).into_vec().ok().and_then(|b| tx::Pk::try_from(b).ok())) {
        out.push(build::ata_of(wallet, &m, &prog(&m)));
    }
    for k in cfg.send_policy.direct.nonce_accounts.iter().chain(cfg.exec.alts.iter()).filter_map(|k| bs58::decode(k).into_vec().ok().and_then(|b| tx::Pk::try_from(b).ok())) {
        out.push(k);
    }
    out.push(ledger::accumulator_of(wallet));
    let mut seen = std::collections::HashSet::new();
    out.retain(|k| seen.insert(*k));
    out
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
    let venue_programs: Vec<String> = provenance::venue_specs(&cfg.pools).iter().map(|p| tx::b58(&p.id)).collect();
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
        let what = match s.verdict { "accepted" if s.messages_30s == 0 => "SILENT", "accepted" => "accepted", "refused" => "REFUSED", "refused_plan_limit" => "PLAN LIMIT",
            _ => "INCONCLUSIVE" };
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

fn simcheck(config: &Path, max: usize, size_sol: f64) -> Result<()> {
    load_env(config);
    let mut cfg = config::Config::load(config)?;
    cfg.sim.enabled = true;
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
    let (reg, drops) = rt.block_on(pools::boot(&rpc, &cands, seeds, ours))?;
    rec.event("pools_dropped", "engine", None, pools::drops_json(&drops));
    let mut store = store::Store::default();
    fetch(&mut store, &reg.static_accounts())?;
    engine::initial_dlmm_arrays(&reg, &mut store);
    let arr: Vec<tx::Pk> = store.dlmm_arrays.values().flatten().map(|x| x.1).collect();
    fetch(&mut store, &arr)?;
    println!("booted: {}", reg.summary());
    let (tx, _rx) = crossbeam_channel::unbounded::<feeds::Event>();
    let (wtx, _) = tokio::sync::watch::channel(Vec::new());
    // a shadow executor: it builds and simulates, holds no key and no send path
    let (x, notes) = rt.block_on(exec::Exec::new(&cfg, &rpc, None, rec.clone(), tx.clone(), vec![], exec::Mode::Shadow, None, reg_mints(&reg)))?;
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
    for v in rec::read_jsonl(&dir, "sims")? {
        let key = format!("{} -> {}", v["buy_venue"].as_str().unwrap_or("?"), v["sell_venue"].as_str().unwrap_or("?"));
        let e = by.entry(key).or_default();
        e.0 += 1;
        if v["encoding_ok"].as_bool() == Some(true) { e.1 += 1; }
        let why = v["build_error"].as_str().map(|b| format!("build: {}", b.split('(').next().unwrap_or(b)))
            .or_else(|| v["sim_error"].as_str().map(|e| format!("rpc: {}", &e[..e.len().min(60)])))
            .unwrap_or_else(|| format!("{} {}", v["code"].as_str().unwrap_or(""), v["meaning"].as_str().unwrap_or("")));
        *e.2.entry(why).or_default() += 1;
    }
    for (k, (n, ok, why)) in &by { println!("{k:<22} {ok}/{n} encoding ok   {why:?}"); }
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
    // PLAN-ADDENDUM I-10, for the paths --only enabled too (the config's load checked the ones enabled in the file)
    for s in &enabled { if let Some(n) = config::cleartext_check(s)? { println!("{n}"); } }
    let opts = send::PathsOpts { queue_ms: cfg.send_policy.queue_ms, payer: bs58::decode(&cfg.wallet).into_vec().ok().and_then(|b| tx::Pk::try_from(b).ok()) };
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
            match send::Paths::new(std::slice::from_ref(s), opts.clone(), rec::Rec::off(), false).await.map(|x| x.0) {
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
        let (ps, _) = send::Paths::new(&enabled, opts, rec.clone(), false).await?;
        let stop = Arc::new(AtomicBool::new(false));
        ps.start(stop.clone(), std::time::Duration::from_secs(30), |m: String| println!("  {m}"));
        let copies = (0..ps.list.len()).map(|i| send::Copy { path: i, raw: Arc::new(raw.clone()), tip: None, blockhash_slot: None, leader_kind: None }).collect();
        let fired = ps.fire(0, copies, send::Prio::default()).await?;
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
    // a canary trades at most its own size (never above [live]'s): the cap the executor applies (review WP-05 #17)
    let (max_size, src) = if canary && !live { (cfg.canary.size_sol.min(l.max_size_sol), "canary") } else { (l.max_size_sol, "config") };
    serde_json::json!({
        "sending": if live { "live" } else if canary { "canary" } else { "none" },
        "max_size_sol": max_size, "max_size_src": src, "sim_max_size_sol": cfg.exec.max_size_sol,
        "max_failed_fees_lamports": l.max_failed_fees_lamports,
        // WP-06: rent-neutral create+close (`create_close`); the held set grows only by the size budget's fallback, at most
        // held_max, off at 0 (the default: review WP-06 #1), and `rent_neutral` says whether any account can stay locked
        "rent_neutral": cfg.builder.rent_neutral(), "create_close": cfg.builder.create_close, "held_max": cfg.builder.held_max,
        "allow_uva_create": cfg.builder.allow_uva_create, "payer_guard": cfg.builder.payer_guard,
        "decoded_sends": false, "state_triggers": cfg.strategy.state_triggers,
        // WP-04: prices only committed, complete, canonical state; nothing priced or sent while the state is unavailable
        "state_gate": { "boot_timeout_s": cfg.state.boot_timeout_s, "max_update_age_ms": cfg.state.max_update_age_ms },
        // WP-05: the ≥1M bands' rate and the crowding policy moved to [send_policy]; bundle-only
        // (the bands are over the expected edge, gross − the base fee: src/bands.rs)
        "big_band_min_expected_lamports": arbx::bands::EDGES[arbx::bands::BIG_FROM as usize - 1], "big_band_max_per_sec": cfg.send_policy.big_band_max_per_sec,
        "crowded_pools_file": cfg.send_policy.crowded_pools_file, "crowded_skip_min_expected_lamports": cfg.send_policy.crowded_skip_min_expected_lamports,
        "bundle_only": config::bundle_only(&cfg.sends).is_ok(), "canary_max_size_sol": cfg.canary.size_sol, "canary_count": cfg.canary.count,
        // WP-07: the trade size capped by the bankroll (0 = off)
        "bankroll_share": cfg.live.bankroll_share, "bankroll_reserve_sol": cfg.live.bankroll_reserve_sol,
        "max_blockhash_age_slots": cfg.send_policy.max_blockhash_age_slots, "skip_leader_kinds": cfg.send_policy.skip_leader_kinds,
        "margin_floor": cfg.send_policy.margin_floor, "margin_share": cfg.send_policy.margin_share,
        // WP-02: always on
        "record": true,
    })
}

/// What a run may send with (go-live gate item 4): the executor's mode, its key, and whether the run builds its send
/// paths. A dry run builds none (nothing in it can transmit) and signs with a throwaway key made in memory, never
/// reading the trading keystore; only a live or canary run reads it (`load_key`); a shadow run holds no key and builds
/// the enabled paths for their keep-alives (a shadow executor is handed none)
fn send_setup(live: bool, canary: bool, dry_run: bool, any_send: bool, load_key: impl FnOnce() -> Result<ed25519_dalek::SigningKey>)
    -> Result<(exec::Mode, Option<ed25519_dalek::SigningKey>, bool)> {
    let mode = if live { exec::Mode::Live } else if canary { exec::Mode::Canary } else if dry_run { exec::Mode::DryRun } else { exec::Mode::Shadow };
    let key = match mode { exec::Mode::Live | exec::Mode::Canary => Some(load_key()?), exec::Mode::DryRun => Some(exec::ephemeral_key()?), exec::Mode::Shadow => None };
    Ok((mode, key, any_send && mode != exec::Mode::DryRun))
}

/// `arbx run`'s arguments
struct RunArgs { config: PathBuf, minutes: Option<f64>, name: Option<String>, only: Option<String>, canary: bool, dry_run: bool, live: bool, ov: Overrides,
    campaign_dir: Option<PathBuf>, env_file: Option<PathBuf>, drain_s: u64, equity_floor: Option<i64> }

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
/// does a run without `--live` or `--canary`, which sends nothing anyway (`mode_shadow`; a dry run: `dry_run`); a live
/// or canary run starts live
fn initial_gate(gate: &control::SendGate, forced_shadow: bool, live: bool, canary: bool, dry_run: bool) {
    if forced_shadow { let _ = gate.shadow("forced_shadow", "--shadow", true); }
    else if dry_run { let _ = gate.shadow("dry_run", "--dry-run: would-sends are signed by a throwaway key and never sent", true); }
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
    let code = end_code(sess, res);
    // WP-20: the stop message (reason, run time, the last status line's numbers) and whatever alerts are still queued,
    // after stop.json; bounded (alerts::EXIT_WAIT), a no-op without alerts
    if let Some(i) = sess.stopper.info() {
        alerts::on_exit(code, i.reason.as_str(), &i.detail, sess.secondary().map(|(r, d)| (r.as_str(), d.as_str())));
    }
    code
}

fn end_code(sess: &control::Session, res: std::thread::Result<Result<()>>) -> i32 {
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
    store.apply(k, store::Acct::rpc(data, slot, t, aseq, src).with_lamports(a.lamports));
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

/// PLAN-ADDENDUM WP-21 (review F5): the programdata headers of venues `vs` read now, as `venues::clmm::deploy_entry`s (one
/// call; a failed read is each venue's error)
async fn clmm_deploy_read(rpc: &rpc::Rpc, vs: &[venues::Venue]) -> Vec<Value> {
    let keys: Vec<tx::Pk> = vs.iter().map(|v| venues::clmm::programdata(*v)).collect();
    match rpc.accounts_slice(&keys, 0, provenance::PROGRAMDATA_HEADER).await {
        Ok((_, accts)) => vs.iter().zip(accts).map(|(v, a)| venues::clmm::deploy_entry(*v, a.as_ref().map(|a| &a.data[..]), None)).collect(),
        Err(e) => vs.iter().map(|v| venues::clmm::deploy_entry(*v, None, Some(&format!("{e:#}")))).collect(),
    }
}

fn run(a: &RunArgs, sess: &Arc<control::Session>) -> Result<()> {
    let started_ns = now_ns();
    let (live, canary, dry_run) = (a.live, a.canary, a.dry_run);
    let env_note = match &a.env_file { Some(f) => load_env_file(f), None => { load_env(&a.config); None } };
    let RunConfig { mut cfg, raw, config_json, config_cap } = run_config(a)?;
    // WP-03 item 3: the transaction streams run as feeds after the [[feed]] list (their ids follow its)
    let tx_stream_feeds = cfg.state.tx_stream_feeds();
    cfg.feeds.extend(tx_stream_feeds);
    // live trading needs both mode = "live" and --live; either alone refuses to start (so neither can spend by itself)
    if live != (cfg.mode == "live") { anyhow::bail!("live trading needs mode = \"live\" in the config AND --live (got mode {}, --live {live}; --shadow runs a live config in shadow)", cfg.mode); }
    if let Some(w) = cfg.pricing_warning() { println!("{w}"); }
    if live && canary { anyhow::bail!("--live and --canary are separate runs"); }
    // go-live gate item 4: a dry run never sends, so it is no live or canary run
    if dry_run && (live || canary) { anyhow::bail!("--dry-run never sends: it is refused with --live and --canary"); }
    if canary && !cfg.canary.enabled { anyhow::bail!("--canary needs [canary] enabled = true in the config (both, so neither alone can spend)"); }
    if cfg.canary.enabled && !canary { println!("[canary] is enabled in the config but --canary was not given: no canaries this run"); }
    // PLAN WP-05 item 1: a live or canary run sends one-transaction Jito bundles only
    if live || canary { config::bundle_only(&cfg.sends).context("PLAN WP-05: live and canary runs are bundle-only")?; }
    // WP-07 (docs/field-tests/README.md "Enforcement"; review WP-07 #5, #8): a live or canary run arms the equity floor, so
    // it needs a test budget (the config's `[supervisor] test_budget_lamports`, or what a campaign has left:
    // --budget-left), never above the owner's hard cap; a floor given is a lamport amount
    // (a run that sends nothing has no use for them: its ledger reads the budget at the cap, for its records)
    if (live || canary) && a.ov.budget_left.is_some_and(|b| b > config::TEST_BUDGET_HARD_CAP) {
        anyhow::bail!("--budget-left {} is over the owner's hard cap {} (docs/field-tests/BUDGET.md)", a.ov.budget_left.unwrap_or(0), config::TEST_BUDGET_HARD_CAP);
    }
    if (live || canary) && a.equity_floor.is_some_and(|f| f < 0) { anyhow::bail!("--equity-floor must be >= 0 lamports"); }
    if (live || canary) && cfg.supervisor.test_budget_lamports == 0 && a.ov.budget_left.is_none() {
        anyhow::bail!("a live or canary run needs a test budget for its equity floor: [supervisor] test_budget_lamports (at most {}) or --budget-left", config::TEST_BUDGET_HARD_CAP);
    }
    // review F3: a supervised segment is paused through its socket; without one, `.pause` could not reach it
    if a.campaign_dir.is_some() && !cfg.control.socket { anyhow::bail!("[control] socket = false: a supervised segment (--campaign-dir) needs its control socket (the supervisor pauses sending through it)"); }
    // WP-05 crowding (F6; review F8 c): a configured crowded list must load, before anything starts (fail closed: a missing
    // one would put the crowded pools back in front of the queue)
    let crowded = if cfg.send_policy.crowded_pools_file.is_empty() { Default::default() } else { exec::load_crowded_pools(&cfg.send_policy.crowded_pools_file)? };
    // the run's name and directory. review F13: a directory that already holds a run is refused (the recorder would
    // replace its compressed files and append to its plain ones); nothing is written into it
    let name = a.name.clone().unwrap_or_else(utc_stamp);
    let dir = run_dir(&cfg.out_dir, a.campaign_dir.as_deref(), &name);
    if let Some(n) = std::fs::read_dir(&dir).ok().map(|d| d.count()).filter(|n| *n > 0) {
        anyhow::bail!("{} already holds {n} files (an earlier run?): choose another --name", dir.display());
    }
    // WP-07 (review #5): a live or canary start. Outside a campaign: the runs directory's lock (no campaign, no other
    // manual run), no other bot on the provider or the wallet (I-3, arbed's bot), and the owner's cumulative budget
    // (`<out_dir>/budget-state.json`: refused when nothing is left; this run gets the smaller of what it asks and what is
    // left). A campaign's segment: its campaign's supervisor holds the lock (it did all of that)
    let wanted = match (a.ov.budget_left, cfg.supervisor.test_budget_lamports) { (Some(b), c) if c > 0 => b.min(c), (Some(b), _) => b, (None, c) => c };
    let hold = if !(live || canary) { None } else {
        match a.campaign_dir.as_deref() {
            Some(c) => {
                let runs = c.parent().unwrap_or(Path::new("."));
                if !probe::lock_held(runs) { anyhow::bail!("--campaign-dir {}: no campaign supervisor holds {} (a live or canary segment runs only under `arbx campaign`)", c.display(), runs.display()); }
                None
            }
            None => {
                let runs = PathBuf::from(&cfg.out_dir);
                std::fs::create_dir_all(&runs).with_context(|| format!("creating {}", runs.display()))?;
                let h = arbx::budget::manual_start(&runs, &name, &dir, mode_name(live, canary), wanted, &|| probe::busy(&runs, true), now_ns())?;
                println!("budget: {} lamports for this run ({} left of the owner's {} before it; {})", h.grant.allotment, h.grant.remaining_before, config::TEST_BUDGET_HARD_CAP,
                    arbx::budget::path(&runs).display());
                Some(h)
            }
        }
    };
    let budget_left = hold.as_ref().map(|h| h.grant.allotment).or(a.ov.budget_left);
    // the trading key is read only when something will really be sent, and must be the config's wallet. Before the
    // signal handlers: Ctrl-C at the passphrase prompt still ends the process at once (nothing has started). A dry run
    // makes a throwaway key in memory instead (never the keystore); a shadow run holds none
    let (mode, send_key, build_paths) = send_setup(live, canary, dry_run, cfg.sends.iter().any(|s| s.enabled), || wallet::load_cfg(&cfg))?;
    // the enabled feeds, in order: their index is the feed id every stream uses (txarr's columns, the entries archives)
    if let Some(only) = &a.only {
        let want: Vec<&str> = only.split(',').map(str::trim).collect();
        for f in &mut cfg.feeds { f.enabled = want.contains(&f.name.as_str()); }
    }
    let feed_names: Vec<String> = cfg.feeds.iter().filter(|f| f.enabled).map(|f| f.name.clone()).collect();
    // the run directory next: from here on every end, even a failed boot, leaves stop.json
    std::fs::create_dir_all(&dir).with_context(|| format!("creating {}", dir.display()))?;
    sess.set_dir(dir.clone());
    // WP-20: the alerts (src/alerts.rs), before anything else can fail: from here on every end of the run sends its stop
    // message (`alerts::on_exit` in end_run). The token and chat id come from the environment loaded above; missing ones
    // turn the alerts off with one warning (said once the recorder runs). Producers never wait; the sender runs on rt_bg
    let runs_dir = match a.campaign_dir.as_deref() { Some(c) => c.parent().map(Path::to_path_buf), None => dir.parent().map(Path::to_path_buf) };
    let (alerter, alert_notes) = alerts::Alerts::new(&cfg.alerts, &alerts::env_var, alerts::Ctx { label: name.clone(), dir: Some(dir.clone()), runs_dir, started_ns, seg: None,
        max_blockhash_age_slots: cfg.send_policy.max_blockhash_age_slots });
    alerts::install(alerter.clone());
    // integration (WP-07 x WP-20): WP-07's notices (the ledger's, the in-process supervisor's: every stop, money event and
    // stale money view) go to these alerts, mapped to their levels and deduplicated by kind and subject; the hook never
    // waits, and runs after the stop it tells of (notify::notify, inside catch_unwind)
    arbx::notify::set_hook(alerts::notice_hook(alerter.clone()));
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
    // WP-20: the alerts' own events go to events.jsonl, and every events.jsonl event is shown to them (`alerts::classify`)
    alerter.set_rec(rec.clone());
    {
        let w = Arc::downgrade(&alerter);
        rec.set_alert_tap(Box::new(move |kind, _subsystem, _feed, d| if let Some(x) = w.upgrade() { x.on_event(kind, d) }));
    }
    for n in &alert_notes { say(n); }
    if let Some(n) = &env_note { say(n); }
    for n in rec.recorder().map(|r| r.notes.clone()).unwrap_or_default() { say(&n); }
    // the run's identity, and a partial meta.json that stop.json's writer leaves if the boot fails before the full one
    let run_json = json!({ "campaign": a.campaign_dir.as_deref().and_then(|c| c.file_name()).map(|c| c.to_string_lossy().into_owned()), "segment": name,
        "dir": dir.display().to_string(), "started_ns": started_ns, "host": provenance::hostname(), "pid": std::process::id(),
        "uid": unsafe { libc::getuid() }, "argv": std::env::args().collect::<Vec<_>>(),
        "mode": mode.as_str(), "forced_shadow": a.ov.shadow, "live_flag": live, "dry_run": dry_run,
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
    initial_gate(&sess.gate, a.ov.shadow, live, canary, dry_run);
    // the frozen copy of the config this run uses (meta.json config.frozen_copy)
    std::fs::write(dir.join("config.toml"), &raw)?;
    let stop = sess.stopper.flag();
    // FT-001 p1: what the stop sequence waits for runs until it ends (`exit`, set after `Engine::stop_sequence`): the
    // chain-fetch service (the wallet's records of what landed) and the send paths' result streams and block-engine token
    // (the bundles' results). With `stop` they ended at the stop request, before the drain that waits for them
    let exit = Arc::new(AtomicBool::new(false));
    // WP-02 (F9): two runtimes. rt_hot (2 workers, `arbx-hot`) runs only stream I/O and sends: the state stream, the gRPC
    // feeds, the send paths, the Jito result streams, keep-alives. rt_bg (`[runtime] bg_threads`, `arbx-bg`, niced +5)
    // runs every RPC call: the client is bound to it, so the boot, the engine's fetches, the executor's simulations and
    // settlements and the program hashing all run there, and large replies are parsed in its blocking pool
    let rts = runtime::Runtimes::new(cfg.runtime.bg_threads)?;
    let (hot, bg) = (rts.hot.handle().clone(), rts.bg.handle().clone());
    rec.set_runtimes(hot.clone(), bg.clone());
    // WP-20: on rt_bg, the alerts' sender, the SendGate watcher (every change, with its reason) and the monitor (the last
    // status line: a stale blockhash, the failed-fee cap, a low balance; the RPC 429 storms; the heartbeat and the daily
    // summary)
    alerter.start(&bg, stop.clone());
    alerter.watch_gate(&bg, sess.gate.clone(), stop.clone());
    alerter.start_monitor(&bg, stop.clone());
    let (eps, skipped) = cfg.rpc.endpoints();
    if eps.is_empty() { anyhow::bail!("no RPC provider configured (skipped: {skipped:?})"); }
    let rpc = rpc::Rpc::race(eps).with_failover(cfg.rpc.failover).bind(bg.clone()).with_role(rpc::Role::Boot);
    // WP-03b (PLAN-ADDENDUM I-1): every provider's token bucket, shared by every client and role of the process (Haan
    // answered 429 at about 5 requests/s); the boot policy (until the executor is built, every call retries with backoff
    // across the providers for `[chainfetch] boot_retry_s`: only a sustained failure aborts the boot, with its stop
    // reason); each provider's host resolved once and its connection opened (no DNS lookup on a reconnect)
    let rpc_reg = rpc::Registry::global();
    for n in rpc.names() { let (r, b) = cfg.chainfetch.limit_of(&n); rpc_reg.set_limit(&n, r, b); }
    // FT-000 (S1-1): the reserved shares (`[chainfetch] reserve`): the slot index and the backfill keep their rate on every
    // provider that serves them, whatever the busier roles ask
    for (p, role, rate) in cfg.chainfetch.reserves(&rpc.names()) { rpc_reg.set_reserve(&p, role, rate); }
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
        // WP-08: the places of validators' gossip IPs and TPU-QUIC endpoints (leaders.jsonl, validators.jsonl, attempts'
        // leader snapshot); the RTT probe and the validator metadata start with the refreshes below (`leaders::start`)
        match leaders::Geo::load(Path::new(&cfg.leaders.geo_table)) {
            Ok(g) => { let (regions, cities) = g.counts(); say(&format!("leaders: geo table {} ({} ranges, {cities} cities in {regions} regions); RTT probe {}",
                cfg.leaders.geo_table, g.len(), if cfg.leaders.rtt_probe { format!("on, at most {} handshakes/s", cfg.leaders.rtt_per_sec) } else { "off".into() })); book.set_geo(g); }
            Err(e) => say(&format!("leaders: no geo table, regions stay null: {e:#}")),
        }
    }
    // WP-03 items 1, 2, 11: accounts.bin (every account update with its aseq; the snapshot's as src rpc_boot between
    // boot marks) and the boot journal (the snapshot's ACCOUNT records, t_engine 0); the extra watched accounts (the
    // Clock sysvar, the programs' programdata, the wallet and its token accounts) and every account's role
    let journal = rec::journal::Journal::new(rec.clone());
    let mut boot_extra = None;
    // PLAN-ADDENDUM WP-21 (review F5): a CLMM venue is priced only on the binary its port was proven on. Each one switched
    // on has its programdata's last deploy slot read now: changed, or unknown (the read failed), the venue is switched off
    // for this segment (fail closed) with a WARNING. meta.json `clmm_deploy` records the reads at the start and at the end
    let clmm_on: Vec<venues::Venue> = [venues::Venue::RayClmm, venues::Venue::Whirlpool].into_iter().filter(|v| cfg.pools.venue_on(*v)).collect();
    let clmm_start = if clmm_on.is_empty() { vec![] } else { rts.bg.block_on(clmm_deploy_read(&rpc, &clmm_on)) };
    for (v, e) in clmm_on.iter().zip(&clmm_start) {
        if e["ok"] == json!(true) { say(&format!("{}: deployed at slot {} as proven: priced ({})", e["venue"].as_str().unwrap_or("?"), e["last_deploy_slot"], cfg.pools.venue_mode(*v))); continue; }
        say(&format!("WARNING: {}: programdata last deployed at {} (proven on {}{}): the venue is OFF for this segment (fail closed: its port was not proven on this binary)",
            e["venue"].as_str().unwrap_or("?"), e["last_deploy_slot"], e["proven_deploy_slot"], e["error"].as_str().map(|w| format!("; {w}")).unwrap_or_default()));
        if *v == venues::Venue::RayClmm { cfg.pools.rayclmm = "off".into() } else { cfg.pools.whirlpool = "off".into() }
    }
    // pools, then a first snapshot of every followed account
    let (reg, store, snapshot_slot) = rts.bg.block_on(async {
        let (cands, seeds, ours) = pools::candidates(&cfg.pools)?;
        let (reg, drops) = pools::boot(&rpc, &cands, seeds, ours).await?;
        // the candidates the registry did not keep, with why (WP-16 review F8): a boot record in events.jsonl, and meta.json
        // `pools.dropped` below
        rec.event("pools_dropped", "engine", None, pools::drops_json(&drops));
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
        // PLAN-ADDENDUM WP-21: a CLMM pool's account that may not exist (Raydium's bitmap extension, Orca's oracle, their
        // followed tick arrays), not found, is recorded empty: known not to exist (the quote must tell it from unread)
        let mut absentable: std::collections::HashSet<tx::Pk> = reg.pools.iter().filter(|m| m.venue.is_clmm())
            .flat_map(|m| m.clmm_ext().into_iter().chain(m.whirl_oracle()).copied()).collect();
        let absent = || rpc::Account { owner: [0u8; 32], lamports: 0, data: vec![] };
        for (n, chunk) in keys.chunks(reads::CHUNK).enumerate() {
            if n > 0 { tokio::time::sleep(std::time::Duration::from_millis(120)).await; }
            let (s, accts) = rpc.accounts(chunk).await?;
            slot = slot.max(s);
            for (k, a) in chunk.iter().zip(accts) {
                match a { Some(a) => boot_account(&mut store, &acct_rec, &journal, *k, a, s), None if absentable.contains(k) => boot_account(&mut store, &acct_rec, &journal, *k, absent(), s), None => {} }
            }
        }
        engine::initial_dlmm_arrays(&reg, &mut store);
        let arr: Vec<tx::Pk> = store.dlmm_arrays.values().flatten().map(|x| x.1).collect();
        roles.add(store.dlmm_arrays.iter().flat_map(|(p, l)| { let pi = reg.by_pool.get(p).map_or(rec::accounts::NO_POOL, |i| *i as u32);
            let role = reg.by_pool.get(p).map_or(rec::accounts::role::DLMM_BIN_ARRAY, |&i| pools::array_role(&reg.pools[i]));
            l.iter().map(move |(_, k)| (*k, rec::accounts::RoleOf { role, pool_index: pi })) }).collect::<Vec<_>>());
        absentable.extend(reg.pools.iter().filter(|m| m.venue.is_clmm()).flat_map(|m| store.dlmm_arrays.get(&m.pool).into_iter().flatten().map(|x| x.1)));
        for chunk in arr.chunks(reads::CHUNK) {
            tokio::time::sleep(std::time::Duration::from_millis(120)).await;
            let (s, accts) = rpc.accounts(chunk).await?;
            for (k, a) in chunk.iter().zip(accts) {
                match a { Some(a) => boot_account(&mut store, &acct_rec, &journal, *k, a, s), None if absentable.contains(k) => boot_account(&mut store, &acct_rec, &journal, *k, absent(), s), None => {} }
            }
        }
        acct_rec.mark(rec::accounts::MARK_BOOT_END, &[]);
        boot_extra = Some((roles, acct_rec, base, extra.len(), drops));
        anyhow::Ok((reg, store, slot))
    })?;
    let (roles, acct_rec, base_watch, n_extra, pool_drops) = boot_extra.expect("set by the boot");
    let snapshot_ns = now_ns();
    // review F1: the state stream starts right after the snapshot, as in arb-lab. It sends only the writes after it
    // subscribes and the engine never re-reads the pools, so every step put between the two (the programs, the send
    // paths, the executor, meta.json) would leave pools on a pre-write price until their next write. Its updates queue
    // until the engine starts; the tx feeds still start after meta.json
    let (tx, rx) = crossbeam_channel::unbounded::<feeds::Event>();
    let mut list: Vec<tx::Pk> = base_watch.clone();
    for l in store.dlmm_arrays.values() { list.extend(l.iter().map(|x| x.1)); }
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
    // WP-07: the campaign so far (the earlier segments' snapshots, ledgers and reconciliations of the last 25 h), read once
    // here: the ledger below takes it, and (integration, FT-000 x WP-07) the wallet cursor never passes the window it
    // reconciles first
    let campaign_hist = a.campaign_dir.as_deref().map(|c| ledger::history(c, Some(name.as_str()), now_ns(), arbx::supervisor::DAY_NS + arbx::supervisor::HOUR_NS));
    if cfg.chainfetch.enabled {
        let (cap, wallet_pk) = (cf_clients.cap(rpc::Role::Backfill), bs58::decode(&cfg.wallet).into_vec().ok().and_then(|b| tx::Pk::try_from(b).ok()));
        let gate = sess.gate.clone();
        let on_dead: chainfetch::OnDead = Arc::new(move |why: &str| { let _ = gate.shadow("chainfetch_dead", why, true); });
        // FT-000 (S1-12): our wallet's history starts after the previous segment's cursor
        let cursor = chainfetch::read_wallet_cursor(&cfg.chainfetch.wallet_cursor, &dir, &cfg.wallet);
        // integration (FT-000 x WP-07): in a campaign, not past the window the ledger reconciles between segments
        let cursor = match (&campaign_hist, cursor) {
            (Some(h), Some((sig, slot, file))) => {
                let from = h.prev_window.as_ref().map_or(0, |w| w.from.slot);
                match ledger::bound_wallet_cursor(Some((sig.clone(), slot)), h) {
                    (Some((s2, sl2)), "moved_back") => {
                        say(&format!("wallet history: the cursor {}… (slot {slot}) is past the ledger's window between segments (from slot {from}): \
                            from {}… (slot {sl2}), the newest earlier ledger entry before it", &sig[..sig.len().min(12)], &s2[..s2.len().min(12)]));
                        Some((s2, sl2, file))
                    }
                    (None, _) => {
                        say(&format!("wallet history: the cursor {}… (slot {slot}) is past the ledger's window between segments (from slot {from}) and no \
                            earlier ledger entry precedes it: not used", &sig[..sig.len().min(12)]));
                        None
                    }
                    (c, _) => c.map(|(s, sl)| (s, sl, file)),
                }
            }
            (_, c) => c,
        };
        match &cursor {
            Some((sig, slot, file)) => say(&format!("wallet history: after {}…'s slot {slot} ({}): only newer signatures are listed", &sig[..sig.len().min(12)], file.display())),
            None => say(&format!("wallet history: no cursor ([chainfetch] wallet_cursor {:?}): the last hour is listed", cfg.chainfetch.wallet_cursor)),
        }
        chainfetch::start(chainfetch::Opts { cfg: cfg.chainfetch.clone(), wallet: wallet_pk, route_program: tx::pk(&cfg.exec.program), roles: roles.clone(), rec: rec.clone(),
            back: Some(tx.clone()), chain: Arc::new(cf_clients), backfill_cap: cap, wallet_cursor: cursor.map(|c| (c.0, c.1)) }, rpc_reg.clone(), &bg, exit.clone(),
            Some(on_dead));
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
    let venue_programs: Vec<String> = provenance::venue_specs(&cfg.pools).iter().map(|p| tx::b58(&p.id)).collect();
    config::expand_includes(&mut cfg.feeds, &reg.watched_writable(), &venue_programs)?;
    let reg = Arc::new(reg);
    // ---- WP-09 wiring: pools.json (MEASUREMENT §4.29: the registry this segment trades, the toolkit's attribution reads
    // it) and registry-run.json (its pairs in order, the state stream's watch list with its roles): what `arbx replay` and
    // `arbx quote` rebuild the engine from (the boot read the pools from chain); meta.json `pools.file` names it
    let pools_sha256 = replay::write_pools_json(&dir, &reg, &base_watch, &roles)?;
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
    // our own transactions: every feed forwards them, so we see when each one appears
    interest.keys.insert(tx::pk(&cfg.wallet));
    let interest = Arc::new(interest);
    say(&format!("interest: {} keys, {} lookup tables", interest.keys.len(), interest.tables.read().unwrap().len()));
    say(&format!("recording (always on): every stream compressed in {} (frames every {} ms, rotation at {} MiB or {} min; disk budget {} GB, min free {} GB){}",
        dir.display(), cfg.record.flush_ms, cfg.record.rotate_mb, cfg.record.rotate_min, cfg.record.disk_budget_gb, cfg.record.min_free_gb,
        if cfg.record.archive_feeds.is_empty() { String::new() } else { format!("; raw entries of {}", cfg.record.archive_feeds.join(", ")) }));
    // STEP 1: every send path kept warm and timed (keepalive.jsonl), each block engine's auth token renewed in the
    // background; paths that can't be built are named, not fatal (a provider key that is the payer's is: I-10). On the
    // hot runtime (their sends and result streams run there). A dry run builds none: nothing in it can transmit
    let paths_opts = send::PathsOpts { queue_ms: cfg.send_policy.queue_ms, payer: bs58::decode(&cfg.wallet).into_vec().ok().and_then(|b| tx::Pk::try_from(b).ok()) };
    let paths = if build_paths {
        let (p, notes) = rts.hot.block_on(send::Paths::new(&cfg.sends, paths_opts, rec.clone(), true))?;
        for n in notes { say(&format!("send path {n}")); }
        let back = tx.clone();
        p.start(exit.clone(), std::time::Duration::from_secs(cfg.exec.keepalive_s), move |m: String| { let _ = back.send(feeds::Event::Status { feed: u16::MAX, msg: m }); });
        say(&format!("send paths: {} (keep-alive every {} s)", p.list.iter().map(|x| x.name.as_str()).collect::<Vec<_>>().join(", "), cfg.exec.keepalive_s));
        Some(p)
    } else {
        if dry_run { say("send paths: none (--dry-run: nothing is sent, no block engine is contacted)"); }
        None
    };
    // The executor, in every run (PLAN-ADDENDUM I-7: a shadow run runs every send check up to the signature and records
    // its would-sends with sent = false). Its sends run on the hot runtime; its RPC (lookup tables, settlements, the
    // diagnostic simulations) on the background one through the bound client. A shadow executor that cannot start
    // leaves the run recording without one (decisions `no_executor`); a live, canary or dry-run one stops the start
    let exec = match rts.hot.block_on(exec::Exec::new(&cfg, &rpc, paths.clone(), rec.clone(), tx.clone(), feed_names.clone(), mode, send_key, reg_mints(&reg))) {
        Ok((mut x, notes)) => {
            x.set_gate(sess.gate.clone());
            x.set_leaders(book.clone());
            for n in notes { say(&format!("exec: {n}")); }
            say(&format!("exec: {}; simulation {}", mode.as_str(), if cfg.sim.enabled { format!("on (at most {}/s)", cfg.sim.max_per_sec) } else { "off".into() }));
            if live { say(&format!("exec: LIVE TRADING: bundle-only, at most {} SOL a trade, stops after {} lamports of failed fees", cfg.live.max_size_sol, cfg.live.max_failed_fees_lamports)); }
            Some(x)
        }
        Err(e) if mode == exec::Mode::Shadow => {
            say(&format!("WARNING: the shadow executor did not start ({e:#}): decisions are recorded without send checks (no_executor)"));
            rec.event("log", "send", None, json!({ "msg": format!("shadow executor not started: {}", rpc::scrub(&format!("{e:#}"))) }));
            None
        }
        Err(e) => return Err(e.context("the executor")),
    };
    // ---- WP-07 wiring: the ledger (money by signature from the wallet stream, balance snapshots at start, hourly and at
    // stop, the hourly reconciliation) and the equity stops: campaign-wide with --campaign-dir (the earlier segments'
    // snapshots and ledgers of the last 25 h; the campaign's start read from the chain). Its snapshots run on rt_bg
    // (role ledger); a stop rule acts on this run's gate and stop path; a live or canary run sends nothing until the
    // first snapshot (`equity_unknown`)
    let wallet_pk = bs58::decode(&cfg.wallet).into_vec().ok().and_then(|b| tx::Pk::try_from(b).ok());
    let ledger = wallet_pk.map(|w| {
        let hist = campaign_hist.unwrap_or_default();
        if a.campaign_dir.is_some() {
            say(&format!("ledger: the campaign so far: {} segments read ({:?}), start {}, test budget {:?}, net spend {}, SOL + WSOL now {:?}, {} lines unreadable",
                hist.segments_read.len(), hist.segments_read, hist.start.as_ref().map_or("not yet (this segment's first snapshot)".to_string(), |s| format!("{} lamports of SOL + WSOL in {} at slot {}",
                    s.equity_stop, s.segment, s.slot)), hist.test_budget, hist.spent, hist.equity_stop_now, hist.bad_lines));
        }
        // the stop rules act in a run that can send; a shadow or dry run records what would have fired (review WP-07 #2:
        // `Ledger::for_run` is what this assembles, and its tests arm it)
        let mut l = ledger::Ledger::for_run(&cfg, w, rec.clone(), &name, mode.sends(), sess.gate.clone(), sess.stopper.clone(), hist, budget_left, a.equity_floor);
        l.set_io(rpc.with_role(rpc::Role::Ledger), bg.clone(), tx.clone());
        l.add_candidates(ledger_candidates(&cfg, &reg, &exec.as_ref().map(|x| x.held_mints()).unwrap_or_default(), &w));
        l
    });
    if ledger.is_none() && mode.sends() { anyhow::bail!("the config's wallet is not a public key: no ledger, no equity stops: a live or canary run refuses to start"); }
    if ledger.is_none() { say("WARNING: the config's wallet is not a public key: no ledger, no equity stops"); }
    // WP-03b: the boot is over (pools, snapshot, route program, executor): every client calls as configured again
    rpc.set_phase(rpc::Phase::Run);
    say(&format!("rpc: boot done; budgets {} (requests/s, every role); chain fetch {}", rpc_reg.limits_json(),
        if cfg.chainfetch.enabled { cf_meta["roles"].to_string() } else { "off".to_string() }));
    // meta.json v2 (MEASUREMENT §4.2), written before the feeds start; rewritten once when the venue programs are hashed
    let built: Vec<String> = paths.as_ref().map(|p| p.list.iter().map(|x| x.name.clone()).collect()).unwrap_or_default();
    let mut limits = limits_json(&cfg, live, canary);
    limits["supervisor"] = json!({ "budget_left_lamports": budget_left, "budget_state": hold.as_ref().map(|h| json!({ "file": arbx::budget::path(&h.runs).display().to_string(),
            "allotment": h.grant.allotment, "remaining_before": h.grant.remaining_before, "spent_before": h.grant.spent_before })), "config_max_failed_fees_lamports": config_cap,
        "effective_max_failed_fees_lamports": cfg.live.max_failed_fees_lamports });
    limits["ledger"] = ledger.as_ref().map_or(Value::Null, |l| l.limits_json());
    let tx_streams: Vec<Value> = cfg.feeds.iter().filter(|f| f.enabled && f.kind == config::FeedKind::YellowstoneTx)
        .map(|f| json!({ "name": f.name, "url_host": f.url.as_deref().map(provenance::host_of), "account_include": f.account_include, "max_accounts": f.max_accounts,
            "failed": f.failed.unwrap_or(true) })).collect();
    let venue_specs = provenance::venue_specs(&cfg.pools);
    let mut programs = route.clone();
    programs.extend(venue_specs.iter().map(provenance::pending_entry));
    let mut streams = provenance::streams_json();
    if let (Some(m), Value::Object(r)) = (streams.as_object_mut(), rec.streams_json()) { m.extend(r); }
    // the registry and the candidates it did not keep (WP-16 review F8)
    // (WP-09: pools.json, its sha256 and registry-run.json beside it)
    let mut pools_meta = replay::meta_pools(provenance::pools_json(&reg, &cfg), &pools_sha256);
    pools_meta["dropped"] = pools::drops_json(&pool_drops);
    let meta = json!({
        "schema": provenance::META_SCHEMA,
        "run": run_json, "build": provenance::build_json(), "config": config_json,
        "programs": programs, "programs_pending": true,
        "wallet": { "pubkey": cfg.wallet, "keystore_path": if cfg.wallet_keystore.is_empty() { format!("~/.nexus-v2-{}-wallet.enc", cfg.wallet_profile) } else { cfg.wallet_keystore.clone() },
            "held_mints_at_boot": exec.as_ref().map(|x| x.held_mints()), "keystore_read": mode.sends(),
            // a dry run's throwaway signer (made in memory, never written; it is not the payer)
            "dry_run_signer": exec.as_ref().and_then(|x| x.dry_signer()).map(|k| tx::b58(&k)) },
        "executor": { "mode": mode.as_str(), "started": exec.is_some() },
        "feeds": provenance::feeds_json(&cfg), "send_paths": provenance::send_paths_json(&cfg, &built), "rpc": provenance::rpc_json(&cfg),
        "state": { "url_host": provenance::host_of(&cfg.state.url), "tx_streams": tx_streams, "watch_clock": cfg.state.watch_clock,
            "watch_programdata": cfg.state.watch_programdata, "watch_wallet": cfg.state.watch_wallet, "block_meta": block_meta,
            "slot_statuses": if interslot { "all" } else { "commitment" }, "extra_watched": n_extra, "config": provenance::section(&cfg.state),
            "snapshot_slot": snapshot_slot, "snapshot_ns": snapshot_ns, "stream_started_ns": stream_started_ns, "followed": followed },
        "probe": probe_meta, "chainfetch": cf_meta, "leaders": provenance::section(&cfg.leaders),
        "pools": pools_meta, "inputs": provenance::inputs_json(&cfg),
        "streams": streams, "experiments": null,
        "limits": limits, "campaign_dir": a.campaign_dir.as_ref().map(|c| c.display().to_string()),
        "clock": provenance::clock_json(),
        "strategy": provenance::section(&cfg.strategy), "send": provenance::section(&cfg.sends), "builder": provenance::section(&cfg.exec),
        "live": provenance::section(&cfg.live), "sim": provenance::section(&cfg.sim), "canary": provenance::section(&cfg.canary),
        "send_policy": provenance::section(&cfg.send_policy), "dry_run": provenance::section(&cfg.dry_run),
        "record": provenance::section(&cfg.record), "control": provenance::section(&cfg.control), "tips": null,
        "runtime": provenance::section(&cfg.runtime),
        // WP-20: the alerts' config (the variables' names, never their values) and whether they are on
        "alerts": { "enabled": alerter.enabled(), "off_why": alerter.off_why(), "config": provenance::section(&cfg.alerts) },
        "send_gate": sess.gate.json(),
        // what the command line changed in the config for this run (--shadow, --budget-left)
        "overrides": a.ov.json(),
        // PLAN-ADDENDUM WP-21 (review F5): the CLMM venues switched on, their deploy slots read at the start (`end` at the end)
        "clmm_deploy": { "start": clmm_start, "end": null },
    });
    control::write_atomic(&dir.join("meta.json"), serde_json::to_string_pretty(&meta)?.as_bytes())?;
    // WP-20: the segment start message (mode, build, config hash, wallet, budget)
    alerter.segment_start(alerts::SegmentStart { segment: name.clone(), mode: mode.as_str().into(), gate_mode: sess.gate.mode().as_str().into(),
        gate_reason: Some(sess.gate.reason()).filter(|r| !r.is_empty()), build: provenance::build_short(),
        config_sha: config_json["normalized_sha256"].as_str().map(|h| h.chars().take(12).collect()).unwrap_or_default(), wallet: cfg.wallet.clone(),
        // integration: the budget this run has (WP-07: its share of the owner's budget state, or what the campaign left it)
        budget_left_lamports: budget_left, fee_cap_lamports: if canary { cfg.canary.max_spend_lamports } else { cfg.live.max_failed_fees_lamports } });
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
    // ---- WP-06 wiring: the fee and CU model (the tips by band, the measured CU table), journaled with engine_init
    let model = engine::BuilderModel::from_cfg(&cfg).map_err(|e| anyhow::anyhow!("[builder] / [tips]: {e}"))?;
    say(&format!("builder: CU table {}; tips by band {:?} of the edge, {}..{} lamports", model.cu.table.as_ref().map_or("none (the fallback formula)".to_string(),
        |t| format!("{} ({} legs; source {})", cfg.builder.cu_table, t.legs.len(), t.source.clone().unwrap_or_else(|| t.source_runs.join(",")))), model.tips.shares, model.tips.floor, model.tips.cap));
    eng.set_builder(model);
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
    // WP-05 crowding (F6): the activity map's window and buckets; WP-00's static list stands in until it holds one
    if !crowded.is_empty() { say(&format!("crowding: {} of the {} listed pools are in this registry", crowded.iter().filter(|p| reg.by_pool.contains_key(*p)).count(), crowded.len())); }
    let b = &cfg.send_policy.crowding_buckets;
    eng.set_crowding(arbx::crowding::Activity::new(cfg.send_policy.crowding_window_h, [b[0], b[1]], crowded));
    eng.exec = exec;
    eng.ledger = ledger;
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
    // WP-07: the stop's drain (`--drain-s`), the stop snapshot and the final reconciliation, then `unsettled` for what is
    // still open (`Engine::stop_sequence`; FT-001: it journals its `stop_end` digest point last). No executor: null
    // (review M11)
    let st = eng.stop_sequence(&rx, a.drain_s * 1_000_000_000, &mut |l: &str| say(l));
    eng.write_final_status(rx.len(), reason);
    *sess.drain.lock().unwrap() = control::Drain { in_flight_at_stop: st.in_flight, drained: st.open.as_ref().map(|o| o.is_empty()),
        unsettled: st.open.clone().unwrap_or_default(), drain_ms: st.in_flight.map(|_| st.drain_ms), final_status_seq: eng.status_lines.checked_sub(1) };
    if !st.settled { say(&format!("stop: {} attempts still open after {:.0} ms: unsettled", sess.drain.lock().unwrap().unsettled.len(), st.drain_ms)); }
    for l in rpc_stats.summary() { say(&format!("rpc final {l}")); }
    for l in rpc_stats.reasons(5) { say(&format!("rpc failure {l}")); }
    // WP-03b: every client's requests by role and provider (resources.jsonl `rpc` has them every 10 s)
    for l in rpc_reg.summary_lines() { say(&format!("rpc role {l}")); }
    if let Some(p) = &paths { for l in p.summary() { say(&format!("send final {l}")); } }
    if let Some(x) = &eng.exec { say(&format!("exec final {}", x.status())); }
    if runtime::hot_violations() > 0 { say(&format!("WARNING: {} RPC calls ran on an arbx-hot thread", runtime::hot_violations())); }
    // WP-07 (review #5): a manual live or canary run's net spend into the owner's budget state (its entry final)
    if let (Some(h), Some(l)) = (&hold, eng.ledger.as_ref()) {
        let spent = l.totals.net_spend();
        match arbx::budget::update(&h.runs, &h.id, spent, true, now_ns()) {
            Ok(()) => say(&format!("budget: this run spent {spent} lamports net ({})", arbx::budget::path(&h.runs).display())),
            Err(e) => say(&format!("WARNING: the budget state was not updated: {e:#} (the next start re-reads this run's ledger)")),
        }
    }
    // PLAN-ADDENDUM WP-21 (review F5): the CLMM venues' deploy slots at the segment's end, beside the start's (meta.json
    // `clmm_deploy.end`): an upgrade during the segment shows there (and stopped pricing at once: `venue_upgraded`)
    if !clmm_on.is_empty() {
        let end = rts.bg.block_on(async { tokio::time::timeout(std::time::Duration::from_secs(10), clmm_deploy_read(&rpc, &clmm_on)).await
            .unwrap_or_else(|_| clmm_on.iter().map(|v| venues::clmm::deploy_entry(*v, None, Some("timed out"))).collect()) });
        for e in end.iter().filter(|e| e["ok"] != json!(true)) {
            say(&format!("WARNING: {} at the segment's end: programdata last deployed at {} (proven on {})", e["venue"].as_str().unwrap_or("?"), e["last_deploy_slot"], e["proven_deploy_slot"]));
        }
        let path = dir.join("meta.json");
        let wrote = std::fs::read_to_string(&path).map_err(anyhow::Error::from).and_then(|t| Ok(serde_json::from_str::<Value>(&t)?))
            .and_then(|mut m| { m["clmm_deploy"]["end"] = json!(end); control::write_atomic(&path, serde_json::to_string_pretty(&m)?.as_bytes()) });
        if let Err(e) = wrote { say(&format!("meta.json: the CLMM venues' end deploy slots NOT recorded: {e:#}")); }
    }
    stop.store(true, Ordering::Relaxed);
    exit.store(true, Ordering::Relaxed);
    // WP-20: what the alerts' sender holds goes out before its runtime stops (bounded); the rest with the stop message
    alerter.flush(alerts::FLUSH_WAIT);
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
        // review WP-05 #17: a canary run's cap is the canary's size, as the executor applies it
        let c = limits_json(&cfg, false, true);
        assert_eq!((c["max_size_sol"].as_f64(), c["max_size_src"].as_str(), c["canary_max_size_sol"].as_f64()), (Some(cfg.canary.size_sol), Some("canary"), Some(cfg.canary.size_sol)));
        assert_eq!((l["max_size_sol"].as_f64(), l["max_size_src"].as_str()), (Some(4.2), Some("config")));
        // WP-06: trades are rent-neutral; held-set additions are off (review #1); `rent_neutral` says whether any can stay
        assert_eq!((l["rent_neutral"].as_bool(), l["create_close"].as_bool(), l["held_max"].as_u64(), l["allow_uva_create"].as_bool(), l["payer_guard"].as_bool()),
            (Some(true), Some(true), Some(0), Some(false), Some(false)));
        let mut opted = cfg.clone();
        opted.builder.held_max = 3;
        assert_eq!((limits_json(&opted, true, false)["rent_neutral"].as_bool(), limits_json(&opted, true, false)["held_max"].as_u64()), (Some(false), Some(3)));
        assert!(l.get("max_new_token_accounts").is_none());
        // WP-07 beside them (merge): the bankroll cap (off in this file) and the canary's attempt cap; the frz canary's
        // bankroll, with the same rent-neutral builder
        assert_eq!((l["bankroll_share"].as_f64(), l["bankroll_reserve_sol"].as_f64(), l["canary_count"].as_u64()), (Some(0.0), Some(0.0), Some(cfg.canary.count as u64)));
        let frz = config::Config::load(&Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-canary-frz.toml")).unwrap();
        let f = limits_json(&frz, false, true);
        assert_eq!((f["max_size_sol"].as_f64(), f["bankroll_share"].as_f64(), f["bankroll_reserve_sol"].as_f64(), f["rent_neutral"].as_bool(), f["create_close"].as_bool(),
            f["held_max"].as_u64()), (Some(0.2), Some(0.85), Some(0.03), Some(true), Some(true), Some(0)));
        assert_eq!((l["decoded_sends"].as_bool(), l["state_triggers"].as_bool(), l["record"].as_bool()), (Some(false), Some(true), Some(true)));
        assert_eq!((l["big_band_min_expected_lamports"].as_u64(), l["big_band_max_per_sec"].as_f64()), (Some(1_000_000), Some(0.5)));
        assert_eq!((l["crowded_pools_file"].as_str(), l["crowded_skip_min_expected_lamports"].as_u64()), (Some("/root/arbx/data/crowded-pools.json"), Some(100_000)));
        assert_eq!((l["bundle_only"].as_bool(), l["max_blockhash_age_slots"].as_u64(), l["margin_floor"].as_u64()), (Some(true), Some(20), Some(1)));
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
        RunArgs { config: config.to_path_buf(), minutes: None, name: None, only: None, canary, dry_run: false, live, ov, campaign_dir, env_file: None, drain_s: 60, equity_floor: None }
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
            initial_gate(&g, shadow, live, canary, false);
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

    /// integration (WP-07 x WP-20 x FT-000), a structural guard on `run` and `arbx campaign` (they need RPC, a gRPC server
    /// and a frozen binary, so they are not run here): the alerts are the process's and WP-07's notice hook before the
    /// recorder starts, so every notice of the ledger and the in-process supervisor reaches them; the campaign's history is
    /// read once, before the chain-fetch service starts, and bounds its wallet cursor, then goes to the ledger, whose RPC
    /// is its own role; the start message names the run's budget. WP-06 (at its merge with integ/stage0): the executor
    /// (its boot read of the wallet's token accounts and PumpSwap volume accumulator) before the ledger, which takes its
    /// held mints; the builder's fee and CU model (the tips by band, the CU table) on the engine after it is made and
    /// before the executor and the ledger are handed to it and it runs (engine_init journals the model at the run's
    /// start). Each step is found once in `run`. `arbx campaign` starts its own alerts after the detach and finishes them
    /// after its last segment
    #[test]
    fn the_alerts_take_wp07s_notices_and_the_cursor_follows_the_ledger() {
        let src = include_str!("main.rs");
        let body = &src[src.find("\nfn run(a: &RunArgs").expect("run")..];
        let body = &body[..body.find("\n#[cfg(test)]").unwrap_or(body.len())];
        let at = |needle: &str| body.find(needle).unwrap_or_else(|| panic!("{needle} not in run()"));
        let order = ["alerts::install(alerter.clone())", "arbx::notify::set_hook(alerts::notice_hook(alerter.clone()))", "rec::start(rec::Opts", "let campaign_hist =",
            "ledger::bound_wallet_cursor(", "chainfetch::start(", "exec::Exec::new(&cfg", "let hist = campaign_hist.unwrap_or_default()", "rpc.with_role(rpc::Role::Ledger)",
            "ledger_candidates(&cfg, &reg, &exec.as_ref().map(|x| x.held_mints())", "write_atomic(&dir.join(\"meta.json\")", "budget_left_lamports: budget_left,",
            "engine::Engine::new(", "engine::BuilderModel::from_cfg(&cfg)", "eng.set_builder(model)", "eng.exec = exec;", "eng.ledger = ledger;", "eng.run(&rx"];
        for w in order.windows(2) { assert!(at(w[0]) < at(w[1]), "{} must come before {}", w[0], w[1]); }
        for n in ["exec::Exec::new(", "engine::BuilderModel::from_cfg(", "eng.set_builder(", "eng.exec = ", "eng.ledger = "] {
            assert_eq!(body.matches(n).count(), 1, "{n} once in run()");
        }
        assert!(!body.contains("rpc::Role::Snapshot"), "the state re-read's role is the FT-000 fixes', the ledger's is `ledger`");
        let camp = include_str!("campaign.rs");
        let m = &camp[camp.find("\npub fn main(o: Opts").expect("campaign main")..];
        let m = &m[..m.find("\n}\n").unwrap_or(m.len())];
        let at = |needle: &str| m.find(needle).unwrap_or_else(|| panic!("{needle} not in campaign::main"));
        for w in ["daemonize(&dir.join(\"supervisor.log\"))", "CampaignAlerts::start(a, true)", "c.run(&mut runner, &RealClock)", "alerts.finish()"].windows(2) {
            assert!(at(w[0]) < at(w[1]), "{} must come before {}", w[0], w[1]);
        }
    }

    /// FT-001: `run` stops as the scenario tests stop a run: the loop (`finish`, the `run_end` digest point), then
    /// `Engine::stop_sequence` (the drain, the stop snapshot, the final reconciliation, `settle_at_stop`, the `stop_end`
    /// digest point), then the final status line; each once
    /// PLAN-ADDENDUM WP-21 (review F5), a structural guard on `run`: the CLMM venues' deploy check runs before the pools
    /// are read (a venue it switches off contributes no candidate), meta.json carries its start and its end reads, and the
    /// end's read comes after the engine's stop sequence
    #[test]
    fn the_clmm_deploy_check_comes_before_the_candidates() {
        let src = include_str!("main.rs");
        let body = &src[src.find("\nfn run(a: &RunArgs").expect("run")..];
        let body = &body[..body.find("\n#[cfg(test)]").unwrap_or(body.len())];
        let at = |s: &str| body.find(s).unwrap_or_else(|| panic!("{s} not in run()"));
        for w in ["clmm_deploy_read(&rpc, &clmm_on)", "pools::candidates(&cfg.pools)", "\"clmm_deploy\": { \"start\": clmm_start", "eng.stop_sequence(&rx",
            "m[\"clmm_deploy\"][\"end\"] = json!(end)"].windows(2) {
            assert!(at(w[0]) < at(w[1]), "{} must come before {}", w[0], w[1]);
        }
    }

    #[test]
    fn run_stops_through_the_engines_stop_sequence() {
        let src = include_str!("main.rs");
        let body = &src[src.find("\nfn run(a: &RunArgs").expect("run")..];
        let body = &body[..body.find("\n#[cfg(test)]").unwrap_or(body.len())];
        let at = |needle: &str| body.find(needle).unwrap_or_else(|| panic!("{needle} not in run()"));
        for w in ["eng.run(&rx", "eng.stop_sequence(&rx", "eng.write_final_status("].windows(2) { assert!(at(w[0]) < at(w[1]), "{} must come before {}", w[0], w[1]); }
        for n in ["eng.stop_sequence(", "eng.write_final_status(", "settle_at_stop", "eng.drain(", "digest_point("] {
            assert_eq!(body.matches(n).count(), usize::from(n == "eng.stop_sequence(" || n == "eng.write_final_status("), "{n} in run(): the stop sequence is the engine's");
        }
        // FT-001 p1: what the stop sequence waits for (the chain-fetch service: the wallet's records; the send paths: the
        // bundles' results and the block-engine token) runs until it ends, not until the stop request
        let cf = &body[at("chainfetch::start(")..];
        assert!(cf[..cf.find(';').unwrap()].contains("exit.clone()"), "the chain-fetch service stops at the exit, after the stop sequence");
        assert!(body.contains("p.start(exit.clone()"), "the send paths' result streams stop at the exit");
        assert!(at("eng.stop_sequence(&rx") < at("exit.store(true"), "the exit comes after the stop sequence");
        assert_eq!(body.matches("exit.store(true").count(), 1);
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

    /// Go-live gate item 4: `--dry-run` never sends, so it is refused with `--live` and with `--canary`, before anything
    /// starts; in `run` (a structural guard: it needs RPC and a gRPC server) a dry run builds no send path and signs with a
    /// throwaway key made in memory, while only a live or canary run reads the trading keystore
    #[test]
    fn a_dry_run_never_sends() {
        let d = std::env::temp_dir().join(format!("arbx-dryrun-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&d).unwrap();
        let src = std::fs::read_to_string(Path::new(env!("CARGO_MANIFEST_DIR")).join("deploy/arbx-stage0.toml")).unwrap();
        let (shadow_p, live_p) = (d.join("shadow.toml"), d.join("live.toml"));
        std::fs::write(&shadow_p, &src).unwrap();
        std::fs::write(&live_p, src.replacen("mode = \"shadow\"", "mode = \"live\"", 1)).unwrap();
        assert_eq!(config::Config::load(&live_p).unwrap().mode, "live");
        let sess = control::Session::new();
        for (p, live, canary) in [(&live_p, true, false), (&shadow_p, false, true)] {
            let mut a = args(p, Overrides::default(), live, canary, Some(d.join("camp")));
            a.dry_run = true;
            let e = run(&a, &sess).unwrap_err();
            assert!(e.to_string().contains("--dry-run never sends"), "--live {live} --canary {canary}: {e}");
        }
        assert!(!d.join("camp").exists(), "refused before the segment directory");
        let _ = std::fs::remove_dir_all(&d);
    }

    /// Go-live gate item 4, by behaviour (review WP-05 #14: the source's text proved nothing): `run`'s send setup. A dry
    /// run builds no send path and signs with a throwaway key made in memory (a new one each run, never the wallet's),
    /// never calling the keystore loader, even one that would fail; a live and a canary run read the keystore (its failure
    /// stops them) and build their paths; a shadow run holds no key and builds the enabled paths for their keep-alives
    #[test]
    fn a_dry_run_reads_no_keystore_and_builds_no_send_path() {
        let reads = std::cell::Cell::new(0);
        let wallet = ed25519_dalek::SigningKey::from_bytes(&[3u8; 32]);
        let load = || { reads.set(reads.get() + 1); Ok(wallet.clone()) };
        let (mode, key, paths) = send_setup(false, false, true, true, load).unwrap();
        let dry = key.expect("a throwaway key");
        assert_eq!((mode, paths, reads.get()), (exec::Mode::DryRun, false, 0), "no path, no keystore");
        assert_ne!(dry.verifying_key(), wallet.verifying_key());
        let (_, again, _) = send_setup(false, false, true, true, || panic!("a dry run must not read the keystore")).unwrap();
        assert_ne!(again.unwrap().verifying_key(), dry.verifying_key(), "made anew each run");
        for (live, canary, want) in [(true, false, exec::Mode::Live), (false, true, exec::Mode::Canary)] {
            let (mode, key, paths) = send_setup(live, canary, false, true, load).unwrap();
            assert_eq!((mode, paths, key.map(|k| k.verifying_key())), (want, true, Some(wallet.verifying_key())));
            assert!(send_setup(live, canary, false, true, || anyhow::bail!("no keystore")).is_err(), "a sending run needs its key");
        }
        assert_eq!(reads.get(), 2, "read once per sending run");
        let (mode, key, paths) = send_setup(false, false, false, true, || panic!("a shadow run must not read the keystore")).unwrap();
        assert_eq!((mode, key.is_none(), paths), (exec::Mode::Shadow, true, true), "keep-alives only");
        assert!(!send_setup(false, false, false, false, load).unwrap().2, "nothing enabled, nothing built");
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

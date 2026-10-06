//! arbx configuration (TOML). Secrets are never in the file: each one is named by an environment variable that
//! `.env` (next to the config, mode 600) provides.
//!
//! Config hygiene (PLAN WP-01 item 2): every struct denies unknown keys, so a misspelled or removed key is a load error
//! that names the key, never a silently ignored setting; `config_version = 2` is required (arb-lab's v1 files, such as
//! `deploy/legacy/arb-w-live.toml`, do not load); `Config::normalized_json` gives the hash that ignores comments and
//! formatting (meta.json `config.normalized_sha256`).
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::path::Path;

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Config {
    /// the config format: 2 (arbx). Required: `Config::parse` refuses a file without it or with another value
    #[serde(default)]
    pub config_version: Option<u32>,
    /// where each run writes its own directory (`run --campaign-dir` puts the segment in the campaign's directory instead)
    pub out_dir: String,
    /// "shadow" (decide, log, never send) or "live" (send; also needs --live and the confirm phrase)
    #[serde(default = "shadow")]
    pub mode: String,
    /// the trading wallet's public key (shadow mode builds against it; live mode loads its keystore)
    pub wallet: String,
    /// keystore profile for live mode: ~/.nexus-v2-<profile>-wallet.enc and .pass (the current bot's format)
    #[serde(default = "trading")]
    pub wallet_profile: String,
    /// an encrypted v3 keystore file (arbx keystore-encrypt / tools/encrypt-keystore.mjs). When set, the passphrase
    /// is read once at start from stdin (piped over SSH) or the terminal, never from a file; wallet_profile is unused.
    #[serde(default)]
    pub wallet_keystore: String,
    pub pools: PoolsCfg,
    pub rpc: RpcCfg,
    pub state: StateCfg,
    #[serde(default)]
    pub strategy: StrategyCfg,
    #[serde(rename = "feed", default)]
    pub feeds: Vec<Feed>,
    #[serde(rename = "send", default)]
    pub sends: Vec<SendPath>,
    /// WP-05: the send policy (PLAN WP-05's `[send]` keys: TOML cannot hold a `[send]` table beside the `[[send]]` paths,
    /// so they live here). `[gate]` (the Jito gate) is gone: a config that still has it does not load
    #[serde(default)]
    pub send_policy: SendPolicyCfg,
    /// WP-05 (go-live gate item 4): `arbx run --dry-run` signs every would-send bundle with a throwaway key and never sends
    #[serde(default)]
    pub dry_run: DryRunCfg,
    #[serde(default)]
    pub exec: ExecCfg,
    #[serde(default)]
    pub sim: SimCfg,
    #[serde(default)]
    pub canary: CanaryCfg,
    #[serde(default)]
    pub live: LiveCfg,
    #[serde(default)]
    pub record: RecordCfg,
    #[serde(default)]
    pub control: ControlCfg,
    #[serde(default)]
    pub runtime: RuntimeCfg,
    #[serde(default)]
    pub leaders: LeadersCfg,
    #[serde(default)]
    pub alts: AltsCfg,
    #[serde(default)]
    pub accuracy: AccuracyCfg,
    /// WP-03b: wallet transactions, watched-transaction backfill, slot index, blockhash sources; per-provider RPC budgets
    #[serde(default)]
    pub chainfetch: ChainfetchCfg,
    /// WP-07: the ledger (src/ledger.rs): money by signature, balance snapshots, the hourly reconciliation
    #[serde(default)]
    pub ledger: LedgerCfg,
    /// WP-07: the equity stops and the money alerts (src/supervisor.rs), for the segment and the whole campaign
    #[serde(default)]
    pub supervisor: SupervisorCfg,
}

/// The owner's hard cap on the test budget (docs/field-tests/BUDGET.md, 2026-10-05: $3-5 of the frz wallet), lamports.
/// `[supervisor] test_budget_lamports` and `arbx campaign --test-budget-lamports` above it do not load
pub const TEST_BUDGET_HARD_CAP: u64 = 34_000_000;

/// The ledger (src/ledger.rs; PLAN WP-07 items 2-4, MEASUREMENT §4.42-§4.44): every wallet transaction is split into
/// summing categories from its chain record; balance snapshots (one common context slot) are taken at start, every
/// `snapshot_min` inside the segment and at stop; consecutive snapshots are reconciled against the entries between them,
/// and the executor's money against the entries of its landings. The money view (the last snapshot and the entries
/// after it) is what live and canary sends need: stale, nothing is sent (`equity_stale`, review WP-07 #3)
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LedgerCfg {
    /// a balance snapshot this often inside a segment (minutes; each asked for up to 30 s early so the view is fresh
    /// when it is due), besides the one at start and the one at stop
    #[serde(default = "snapshot_min")]
    pub snapshot_min: u64,
    /// the money view is stale (the gate in shadow, `equity_stale`) once its last good snapshot is older than this, s
    /// (at least `snapshot_min`)
    #[serde(default = "max_view_age_s")]
    pub max_view_age_s: u64,
    /// ... or once this many snapshots in a row failed (or came back on different slots)
    #[serde(default = "stale_after_failures")]
    pub stale_after_failures: u32,
    /// ... or while a landing the executor found by a status check has had no wallet record for this long, s
    #[serde(default = "max_record_wait_s")]
    pub max_record_wait_s: u64,
    /// a reconciliation passes when both residuals (total and liquid) are within this, lamports
    #[serde(default = "recon_tolerance")]
    pub tolerance_lamports: u64,
    /// where token mids come from: "pools" (the engine's committed pool state: the quote for selling the amount into WSOL)
    #[serde(default = "mid_pools")]
    pub mid_source: String,
    /// a snapshot whose answers' context slots differ is taken again this many times; then it is written with
    /// `slot_mismatch` and not reconciled (F34)
    #[serde(default = "snapshot_retries")]
    pub snapshot_retries: u32,
    /// a snapshot that failed is tried again after this many seconds
    #[serde(default = "snapshot_retry_s")]
    pub snapshot_retry_s: u64,
    /// a reconciliation is decided this long after its snapshot (the window's wallet records may still be on their
    /// way); an unexplained residual is searched with getSignaturesForAddress and decided once more this long later
    #[serde(default = "recon_grace_s")]
    pub recon_grace_s: u64,
    /// non-SOL holdings are valued at the engine's quote for selling them into WSOL, less this share (status and
    /// snapshots only: no stop reads a token's value, each held token has its own floor instead)
    #[serde(default = "token_haircut")]
    pub token_haircut: f64,
    /// mints whose wallet ATA (SPL Token) every snapshot reads, besides the token accounts held at boot and those the
    /// wallet's transactions create (default USDC and USDT)
    #[serde(default = "extra_mints")]
    pub extra_mints: Vec<String>,
}
fn snapshot_min() -> u64 { 10 }
fn max_view_age_s() -> u64 { 600 }
fn stale_after_failures() -> u32 { 3 }
fn max_record_wait_s() -> u64 { 120 }
fn recon_tolerance() -> u64 { 10_000 }
fn mid_pools() -> String { "pools".into() }
fn snapshot_retries() -> u32 { 3 }
fn snapshot_retry_s() -> u64 { 30 }
fn recon_grace_s() -> u64 { 60 }
fn token_haircut() -> f64 { 0.10 }
fn extra_mints() -> Vec<String> { vec!["EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v".into(), "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB".into()] }
impl Default for LedgerCfg {
    fn default() -> Self {
        LedgerCfg { snapshot_min: snapshot_min(), max_view_age_s: max_view_age_s(), stale_after_failures: stale_after_failures(), max_record_wait_s: max_record_wait_s(),
            tolerance_lamports: recon_tolerance(), mid_source: mid_pools(), snapshot_retries: snapshot_retries(),
            snapshot_retry_s: snapshot_retry_s(), recon_grace_s: recon_grace_s(), token_haircut: token_haircut(), extra_mints: extra_mints() }
    }
}

/// The equity stops and money alerts (src/supervisor.rs; PLAN WP-07 item 5, OD-11). Each holding is tracked on its
/// own (STAGE1-PLAN review F6): SOL + WSOL (lamports; the start read from the chain) carries the budget floor and the
/// drop caps; every non-SOL token held at the campaign's start has a quantity floor (`token_floor_tolerance`); the
/// recoverable rent is tracked apart. Each rule names its reason in stop.json, events.jsonl and the SendGate
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SupervisorCfg {
    /// OD-11: the bot goes to shadow and the campaign stops (`equity_hour`, exit 20) when SOL + WSOL falls more than
    /// this within a rolling hour, campaign-wide (SOL; PLAN WP-07's `hour_drop_sol`)
    #[serde(default = "hour_drop")]
    pub max_drop_per_hour_sol: f64,
    /// the same over a rolling 24 h (`equity_day`, exit 20; PLAN WP-07's `day_drop_sol`)
    #[serde(default = "day_drop")]
    pub max_drop_per_day_sol: f64,
    /// the test budget, lamports (at most `TEST_BUDGET_HARD_CAP`); the floor is the campaign's start SOL + WSOL minus
    /// it (`equity_floor`, exit 20). 0: none here; a live or canary run then needs `--budget-left`
    #[serde(default)]
    pub test_budget_lamports: u64,
    /// a non-SOL token held at the campaign's start may lose at most this share of its start amount (rounding, dust)
    /// before the campaign stops (`token_floor`, exit 20)
    #[serde(default = "token_tolerance")]
    pub token_floor_tolerance: f64,
    /// no held-set growth (no new token account) while the recoverable rent is above this, SOL (create-and-close
    /// stays allowed: it is rent-neutral)
    #[serde(default = "rent_cap")]
    pub rent_cap_sol: f64,
    /// an alert when native SOL (tips and fees are paid from it) falls below this, SOL
    #[serde(default = "native_floor")]
    pub native_floor_sol: f64,
    /// the automatic unwrap of `unwrap_sol` WSOL when native SOL is low: it writes to the wallet, an owner decision
    /// (R §6). Stage 0 refuses `true`
    #[serde(default)]
    pub auto_unwrap: bool,
    #[serde(default = "unwrap_sol")]
    pub unwrap_sol: f64,
    /// an alert when a token a route left behind is still held this long after, s (automatic sale is Stage 2+)
    #[serde(default = "stranded_s")]
    pub stranded_s: u64,
    /// a live or canary run sends nothing until its first balance snapshot (the floor needs the start equity); an
    /// alert when it has none this long after the start, s
    #[serde(default = "equity_wait_s")]
    pub equity_wait_s: u64,
}
fn hour_drop() -> f64 { 0.02 }
fn token_tolerance() -> f64 { 0.001 }
fn day_drop() -> f64 { 0.15 }
fn rent_cap() -> f64 { 0.1 }
fn native_floor() -> f64 { 0.02 }
fn unwrap_sol() -> f64 { 0.05 }
fn stranded_s() -> u64 { 60 }
fn equity_wait_s() -> u64 { 120 }
impl Default for SupervisorCfg {
    fn default() -> Self {
        SupervisorCfg { max_drop_per_hour_sol: hour_drop(), max_drop_per_day_sol: day_drop(), test_budget_lamports: 0, token_floor_tolerance: token_tolerance(), rent_cap_sol: rent_cap(),
            native_floor_sol: native_floor(), auto_unwrap: false, unwrap_sol: unwrap_sol(), stranded_s: stranded_s(), equity_wait_s: equity_wait_s() }
    }
}

/// The chain-fetch service (src/chainfetch; PLAN WP-03b) and the RPC budgets every client shares (src/rpc.rs)
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChainfetchCfg {
    /// run the service (wallet transactions, backfill, slot index, blockhash ring). The provider budgets and the boot
    /// policy apply either way
    #[serde(default = "yes")]
    pub enabled: bool,
    /// a watched transaction seen without an exec.jsonl record this long is queued for a getTransaction, ms
    #[serde(default = "cf_after_ms")]
    pub after_ms: u64,
    /// the backfill's request rate: "auto" (1.25 x the measured rate of uncovered signatures, a 1-minute EWMA) or a fixed
    /// number of requests/s; either way capped by its providers' `max_rps`
    #[serde(default)]
    pub rps: CfRps,
    /// past this many queued signatures the oldest low-priority ones are dropped (and counted)
    #[serde(default = "cf_backlog")]
    pub max_backlog: usize,
    /// one full block every this many seconds measures the share of watched transactions no source reported (0: off)
    #[serde(default = "cf_sample")]
    pub sample_every_s: u64,
    /// getLatestBlockhash (confirmed) this often, ms (0: off)
    #[serde(default = "cf_bh_poll")]
    pub blockhash_poll_ms: u64,
    /// getSignaturesForAddress(wallet) over the last hour, this often, seconds (source (d); 0: off)
    #[serde(default = "cf_sigs")]
    pub sigs_every_s: u64,
    /// the token bucket (requests/s) of every [rpc] provider no `[[chainfetch.provider]]` gives a `max_rps` (0, the
    /// default: no limit; a config without `[chainfetch]` keeps unlimited providers, review WP-03b #18). Haan answered
    /// 429 at about 5 requests/s (tools/rpc_latency.py, 2026-10-04): the deploy configs list it with its own `max_rps`
    #[serde(default = "cf_default_rps")]
    pub default_max_rps: f64,
    /// PLAN-ADDENDUM I-1: at boot (pools, snapshot, route program, executor) an RPC call retries with backoff across the
    /// providers this long before the boot gives up, seconds
    #[serde(default = "cf_boot_retry")]
    pub boot_retry_s: u64,
    /// getTransaction / getBlock `maxSupportedTransactionVersion` (mainnet blocks carry v1 transactions, SIMD-0385: a
    /// lower value makes the provider refuse a whole block with -32015)
    #[serde(default = "cf_txver")]
    pub max_tx_version: u8,
    /// which providers serve which chain-fetch role, and each provider's budget
    #[serde(default, rename = "provider")]
    pub providers: Vec<ChainfetchProviderCfg>,
}

/// One `[[chainfetch.provider]]`: an [rpc] endpoint, the chain-fetch roles it serves (`wallet`, `blockhash`, `slotidx`,
/// `backfill`, `sample`; a role no provider names uses every available [rpc] provider in order), and its token bucket,
/// shared by every client and role of the process (boot, exec, engine and leaders calls too)
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ChainfetchProviderCfg {
    pub name: String,
    #[serde(default)]
    pub roles: Vec<String>,
    /// requests/s for the whole process (None: `[chainfetch] default_max_rps`; 0: no limit)
    pub max_rps: Option<f64>,
    /// the bucket's burst (default: max(1, max_rps))
    pub burst: Option<f64>,
}

/// `[chainfetch] rps`: "auto" or a fixed rate
#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(untagged)]
pub enum CfRps { Fixed(f64), Auto(String) }
impl Default for CfRps { fn default() -> Self { CfRps::Auto("auto".into()) } }
impl CfRps {
    /// the fixed rate, None for "auto"
    pub fn fixed(&self) -> Option<f64> { match self { CfRps::Fixed(r) => Some(*r), CfRps::Auto(_) => None } }
}

fn cf_after_ms() -> u64 { 1_500 }
fn cf_backlog() -> usize { 200_000 }
fn cf_sample() -> u64 { 60 }
fn cf_bh_poll() -> u64 { 400 }
fn cf_sigs() -> u64 { 3_600 }
fn cf_default_rps() -> f64 { 0.0 }
fn cf_boot_retry() -> u64 { 90 }
fn cf_txver() -> u8 { 1 }
impl Default for ChainfetchCfg {
    fn default() -> Self {
        ChainfetchCfg { enabled: true, after_ms: cf_after_ms(), rps: CfRps::default(), max_backlog: cf_backlog(), sample_every_s: cf_sample(),
            blockhash_poll_ms: cf_bh_poll(), sigs_every_s: cf_sigs(), default_max_rps: cf_default_rps(), boot_retry_s: cf_boot_retry(),
            max_tx_version: cf_txver(), providers: vec![] }
    }
}

impl ChainfetchCfg {
    /// The providers (by name, in order) serving `role`: the `[[chainfetch.provider]]` entries that name it, in their
    /// order; a role no entry names gets every provider of `all` (the [rpc] order)
    pub fn providers_for(&self, role: &str, all: &[String]) -> Vec<String> {
        let named: Vec<String> = self.providers.iter().filter(|p| p.roles.iter().any(|r| r == role)).map(|p| p.name.clone()).filter(|n| all.contains(n)).collect();
        if self.providers.iter().any(|p| p.roles.iter().any(|r| r == role)) { named } else { all.to_vec() }
    }
    /// (rate, burst) of provider `name`'s bucket: its entry's `max_rps`, else `default_max_rps` (0: no limit)
    pub fn limit_of(&self, name: &str) -> (f64, Option<f64>) {
        match self.providers.iter().find(|p| p.name == name) {
            Some(p) => (p.max_rps.unwrap_or(self.default_max_rps), p.burst),
            None => (self.default_max_rps, None),
        }
    }
}

/// the config format this binary reads
pub const CONFIG_VERSION: u32 = 2;

/// The run's control socket (src/control.rs): `<run dir>/control.sock` (mode 0600), driven by `arbx ctl`
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ControlCfg {
    /// listen on the socket (default true). Off: signals and the supervisor's files still stop the run
    #[serde(default = "yes")]
    pub socket: bool,
}
impl Default for ControlCfg { fn default() -> Self { ControlCfg { socket: true } } }

/// The recorder (src/rec; PLAN WP-02, MEASUREMENT §1). It is always on: these keys only set budgets, files and queues
/// (`enabled` and `archive_feed` are gone: a config that still has them does not load)
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RecordCfg {
    /// the segment directory's size limit, GB (§1.4: the disk ladder acts past it)
    #[serde(default = "rec_budget_gb")]
    pub disk_budget_gb: f64,
    /// the filesystem's free-space floor, GB (the ladder acts under it; the supervisor refuses to start under it)
    #[serde(default = "rec_min_free_gb")]
    pub min_free_gb: f64,
    /// a stream's file rotates at this much raw (uncompressed) data, MiB
    #[serde(default = "rec_rotate_mb")]
    pub rotate_mb: f64,
    /// ... or at this age, minutes
    #[serde(default = "rec_rotate_min")]
    pub rotate_min: u64,
    /// every stream's zstd frame ends this often (so a file can be read up to its last frame while the run goes on), ms
    #[serde(default = "rec_flush_ms")]
    pub flush_ms: u64,
    #[serde(default = "rec_zstd_level")]
    pub zstd_level: i32,
    /// the entries feeds whose raw messages are archived (`entries-<feed>.NNN.bin.zst`, bulk class; 1-2 GB/h each)
    #[serde(default)]
    pub archive_feeds: Vec<String>,
    /// queue sizes, records (§1.2): core, chain and bulk are per class, accounts and journal per stream
    #[serde(default = "rec_queue_core")]
    pub queue_core: u64,
    #[serde(default = "rec_queue_accounts")]
    pub queue_accounts: u64,
    #[serde(default = "rec_queue_journal")]
    pub queue_journal: u64,
    #[serde(default = "rec_queue_core")]
    pub queue_chain: u64,
    #[serde(default = "rec_queue_bulk")]
    pub queue_bulk: u64,
    /// each bounded queue's byte cap, MiB: the payload bytes producers declare (binary records, sized closures) are
    /// counted, and a record past the cap drops as a full queue would (review F17: a stalled replay writer must not hold
    /// gigabytes of account data)
    #[serde(default = "rec_queue_max_mb")]
    pub queue_max_mb: f64,
    /// accounts.bin: a FULL record of an account every this many of its records (WP-03; the disk ladder lengthens it 4x)
    #[serde(default = "rec_keyframe")]
    pub accounts_keyframe_every: u32,
    /// CPUs the writer threads are pinned to (away from the engine's); empty = any
    #[serde(default)]
    pub writer_cpus: Vec<usize>,
    /// plan addendum I-9 (WP-08): rivals.jsonl keeps 1 in this many of its `why = venues` rows (88% of cmp2's rows),
    /// chosen by the signature so a replay keeps the same ones; each kept one carries the rate and the running counts
    /// (`sample`). 1 keeps every row
    #[serde(default = "rec_rivals_venues_sample")]
    pub rivals_venues_sample: u32,
}

impl Default for RecordCfg {
    fn default() -> Self {
        RecordCfg { disk_budget_gb: rec_budget_gb(), min_free_gb: rec_min_free_gb(), rotate_mb: rec_rotate_mb(), rotate_min: rec_rotate_min(), flush_ms: rec_flush_ms(),
            zstd_level: rec_zstd_level(), archive_feeds: vec![], queue_core: rec_queue_core(), queue_accounts: rec_queue_accounts(), queue_journal: rec_queue_journal(),
            queue_chain: rec_queue_core(), queue_bulk: rec_queue_bulk(), queue_max_mb: rec_queue_max_mb(), accounts_keyframe_every: rec_keyframe(), writer_cpus: vec![],
            rivals_venues_sample: rec_rivals_venues_sample() }
    }
}
fn rec_budget_gb() -> f64 { 40.0 }
fn rec_min_free_gb() -> f64 { 25.0 }
fn rec_rotate_mb() -> f64 { 256.0 }
fn rec_rotate_min() -> u64 { 60 }
fn rec_flush_ms() -> u64 { 1_000 }
fn rec_zstd_level() -> i32 { 3 }
fn rec_queue_core() -> u64 { 262_144 }
fn rec_queue_accounts() -> u64 { 1_048_576 }
fn rec_queue_journal() -> u64 { 524_288 }
fn rec_queue_bulk() -> u64 { 131_072 }
fn rec_queue_max_mb() -> f64 { 1_024.0 }
fn rec_keyframe() -> u32 { 64 }
fn rec_rivals_venues_sample() -> u32 { 10 }

/// The runtime split (src/runtime.rs; PLAN WP-02 item 1): the hot runtime (2 workers) runs stream I/O and sends; the
/// background runtime runs every RPC call
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RuntimeCfg {
    /// the background runtime's workers (`arbx-bg`, niced +5)
    #[serde(default = "rt_bg_threads")]
    pub bg_threads: usize,
}
impl Default for RuntimeCfg { fn default() -> Self { RuntimeCfg { bg_threads: rt_bg_threads() } } }
fn rt_bg_threads() -> usize { 3 }

/// STEP 4: real trades. Needs mode = "live" AND `arbx run --live`. Every send is a one-transaction Jito bundle (PLAN
/// WP-05): its on-chain min_profit is tip + base fee + margin (`[send_policy] margin_*`), so a landed trade cannot lose,
/// and a losing bundle never lands. What landed failures cost (their fees) is capped by `max_failed_fees_lamports`, after
/// which no trade is sent (the engine keeps recording). WP-05 removed the direct arm's keys (`test_all_paths`,
/// `max_priority_lamports`, `bid_*`, `spec_cu_price_micro`, `rotate_paths`, `race_mix`, `bundle_mix`, `tpu_*`,
/// `pair_lock_ms`, `sim_gate`, `bundle_resend_ms`, `bundle_size_variants`, `compete_*`, `gross_floor`), the durable nonces
/// (`nonce_accounts`: `[send_policy.direct]`), `settle_s` (attempts settle from the chain: the wallet stream, or the
/// blockhash's expiry) and moved `big_band_*`, `crowded_pools_file` and `crowded_skip_min_expected_lamports` to
/// `[send_policy]`: a config that still has one does not load
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LiveCfg {
    /// at most this much per trade, SOL (paid from the wallet's WSOL account)
    #[serde(default = "live_size")]
    pub max_size_sol: f64,
    /// stop sending once fees of landed transactions that failed reach this, lamports
    #[serde(default = "live_fee_cap")]
    pub max_failed_fees_lamports: u64,
    /// the decision's own margin: a trade is sent only when its expected profit covers tip + base fee + this (today's
    /// rule, kept); the on-chain floor is `[send_policy] margin_floor` / `margin_share`
    #[serde(default = "live_margin")]
    pub margin_lamports: u64,
    /// new token accounts a winning trade may create (rent, recoverable by closing them); 0 = none (WP-06 makes trades
    /// rent-neutral and removes the key)
    #[serde(default = "live_atas")]
    pub max_new_token_accounts: u32,
    /// WP-07 (go-live gate: the size capped by the bankroll): a trade is at most `bankroll_share` x the wallet's liquid
    /// SOL (native + WSOL, the ledger's chain truth) minus `bankroll_reserve_sol`, and never more than its WSOL (the
    /// route spends WSOL). 0 = off. Shadow and dry runs model it too. Before the ledger's first balance snapshot the
    /// configured cap applies (live and canary send nothing then: `equity_unknown`); a bankroll that allows nothing is
    /// refused `bankroll_empty`
    #[serde(default)]
    pub bankroll_share: f64,
    #[serde(default)]
    pub bankroll_reserve_sol: f64,
}
fn live_size() -> f64 { 0.1 }
fn live_fee_cap() -> u64 { 20_000_000 }
fn live_margin() -> u64 { 1_000 }
fn live_atas() -> u32 { 5 }
impl Default for LiveCfg {
    fn default() -> Self {
        LiveCfg { max_size_sol: live_size(), max_failed_fees_lamports: live_fee_cap(), margin_lamports: live_margin(), max_new_token_accounts: live_atas(),
            bankroll_share: 0.0, bankroll_reserve_sol: 0.0 }
    }
}

/// PLAN WP-05: the send policy. Bundle-only, fail-closed send checks (blockhash age, leader kind, cached Jito token,
/// recorder, SendGate, store health), the in-flight lock, the rate queue's bands and crowding, the on-chain margin
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SendPolicyCfg {
    /// a blockhash older than this (slots behind the chain tip) is not used: no send (`blockhash_stale`)
    #[serde(default = "pol_bh_age")]
    pub max_blockhash_age_slots: u64,
    /// which blockhash-ring entry a bundle uses: "confirmed" (the WP-03b ring's confirmed head) or "processed" (the newest
    /// of the head and the state stream's block metas)
    #[serde(default = "pol_bh_commitment")]
    pub blockhash_commitment: String,
    /// a send waits at most this long for a slot of the Jito rate budget (best first: bands, crowding, EV), ms; then it is
    /// dropped (`rate_queue_timeout`, or `crowded_pool` when a less crowded send took its slot)
    #[serde(default = "pol_queue_ms")]
    pub queue_ms: u64,
    /// the ≥1M bands (bands 3-4, src/bands.rs) at most this often (a token bucket, burst 1; R §3.4); 0 = none of them
    #[serde(default = "pol_big_rate")]
    pub big_band_max_per_sec: f64,
    /// crowding (F6): distinct arbitrage-like signers that landed on either pool over this many hours ...
    #[serde(default = "pol_crowd_h")]
    pub crowding_window_h: u64,
    /// ... bucketed < [0], [0]..[1], ≥ [1] (buckets 0, 1, 2); bucket 2 queues behind the others of its band
    #[serde(default = "pol_crowd_buckets")]
    pub crowding_buckets: Vec<u32>,
    /// WP-00's static list of the ≥150-bot pools (data/crowded-pools.json): bucket 2 until the activity map holds
    /// `crowding_window_h` of data. "" = none
    #[serde(default)]
    pub crowded_pools_file: String,
    /// WP-00 (OD-3's alternative; review F2), kept: a trade on a bucket-2 pool expecting at least this is not sent
    /// (`crowded_pool`). 0 = never (rank only)
    #[serde(default)]
    pub crowded_skip_min_expected_lamports: u64,
    /// on-chain min_profit = tip + base fee + priority (0) + margin, margin = max(margin_floor, margin_share × expected
    /// net) (R §3.9). Stage 0 keeps today's floor (F23): 1 and 0
    #[serde(default = "pol_margin_floor")]
    pub margin_floor: u64,
    #[serde(default)]
    pub margin_share: f64,
    /// an in-flight entry (key: buy pool, sell pool, mint) holds this many slots past its target slot, or until its final
    /// verdict
    #[serde(default = "pol_hold")]
    pub inflight_hold_slots: u64,
    /// leaders of these kinds are not sent to (`leader_skip_kind`; `unknown`: `leader_unknown`). R §3.6: non-Jito leaders
    /// cannot take a bundle
    #[serde(default = "pol_skip_kinds")]
    pub skip_leader_kinds: Vec<String>,
    /// the non-bundle (direct) arm, for a future experiment only: loading `true` is refused in Stage 0
    #[serde(default)]
    pub direct_experiment: bool,
    /// the direct arm's durable nonces (only with `direct_experiment`)
    #[serde(default)]
    pub direct: DirectCfg,
}
fn pol_bh_age() -> u64 { 20 }
fn pol_bh_commitment() -> String { "confirmed".into() }
fn pol_queue_ms() -> u64 { 10 }
fn pol_big_rate() -> f64 { 0.5 }
fn pol_crowd_h() -> u64 { 6 }
fn pol_crowd_buckets() -> Vec<u32> { vec![20, 150] }
fn pol_margin_floor() -> u64 { 1 }
fn pol_hold() -> u64 { 2 }
fn pol_skip_kinds() -> Vec<String> { vec!["other".into(), "unknown".into()] }
impl Default for SendPolicyCfg {
    fn default() -> Self {
        SendPolicyCfg { max_blockhash_age_slots: pol_bh_age(), blockhash_commitment: pol_bh_commitment(), queue_ms: pol_queue_ms(), big_band_max_per_sec: pol_big_rate(),
            crowding_window_h: pol_crowd_h(), crowding_buckets: pol_crowd_buckets(), crowded_pools_file: String::new(), crowded_skip_min_expected_lamports: 0,
            margin_floor: pol_margin_floor(), margin_share: 0.0, inflight_hold_slots: pol_hold(), skip_leader_kinds: pol_skip_kinds(), direct_experiment: false,
            direct: DirectCfg::default() }
    }
}

/// `[send_policy.direct]`: the direct (non-bundle) arm's durable nonce accounts, kept for its experiment
#[derive(Debug, Clone, Default, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DirectCfg {
    #[serde(default)]
    pub nonce_accounts: Vec<String>,
}

/// `arbx run --dry-run` (go-live gate item 4): every would-send bundle is built and signed by a throwaway key made in
/// memory at the start (never the trading keystore, never written anywhere: its pubkey is recorded), then recorded in
/// full and never sent. The payer stays the config's wallet, so accounts, sizes and tips are the live ones, and the
/// signature cannot pass on chain
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct DryRunCfg {
    /// also simulate each would-send bundle (read-only `simulateTransaction`, sigVerify off, the blockhash checked)
    #[serde(default)]
    pub simulate: bool,
    /// at most this many simulations a second
    #[serde(default = "dry_sim_rate")]
    pub max_sim_per_sec: u32,
}
fn dry_sim_rate() -> u32 { 2 }
impl Default for DryRunCfg { fn default() -> Self { DryRunCfg { simulate: false, max_sim_per_sec: dry_sim_rate() } } }

/// Building real transactions from the engine's decisions (simulation and canaries)
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct ExecCfg {
    /// the nexus-arb-v2 program
    #[serde(default = "v2_program")]
    pub program: String,
    /// lookup tables the v0 transaction may load accounts from (arbed's V2_ALTS; missing ones are skipped)
    #[serde(default = "v2_alts")]
    pub alts: Vec<String>,
    /// [rpc] endpoint names used for simulation, signature statuses and landed transactions (one provider, not the race)
    #[serde(default = "exec_rpc")]
    pub rpc: Vec<String>,
    /// never build a trade above this size (the wallet's WSOL must cover it), SOL
    #[serde(default = "exec_max_size")]
    pub max_size_sol: f64,
    /// keep-alive round trip to every send path this often, seconds
    #[serde(default = "keepalive_s")]
    pub keepalive_s: u64,
    /// WP-01: the route program's ELF hashes (programdata without its header and zero padding; MEASUREMENT §4.2),
    /// lowercase hex. When set, a live or canary run whose program on chain differs (or cannot be read) does not send:
    /// the SendGate goes to shadow with reason `program_hash_mismatch`. A shadow run only records the check. "" = no check
    #[serde(default)]
    pub expected_program_sha256: String,
    #[serde(default)]
    pub expected_program_md5: String,
}
fn v2_program() -> String { "8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg".into() }
fn v2_alts() -> Vec<String> {
    ["GbCnMvierZ4mBjscruG6ymhkBzvnZgq2DisJAzPsG5wT", "AKr5BBdyzKwWc7QT36GwxH4eYfoZjzsgwuJHxd1JmVcH", "76caanFrJk59QpbuxVQFo2pifi6M3ZKCu4cVfUQEHYR1",
     "2tSjMLpN8iGqQkerNctpmygsiMTq15sw6yr2VNSy7CRX", "9Na4PhRjn6xhdREhPdXBajcMXtqouS7XKQvCHj6tnLS9", "318motzPcAPsvRYUTCJ74cKE4YEwD7pspMo7cTM7xSHA",
     "EDCGTccPMtKPNQtGwuLB5Mr2EauNVxN21taKyHWaqxV5", "j8dtjv7iPoc7SJGirCqmwwsYtYgvNvqGMf1CtfMRpY1", "8YvWKtLpajoiB2vpkCF7L8VMduMRjaVC9RiGG1RiNPas",
     "6oke1NP6w1t5EuSaM1mUQ29GfN5pmjFYSvMaSArA5RNr", "FEBAESsawhR2AYgEcitBHi1QbdofJ2AEnveuByxaHaXq", "2nE9VyDDfvUMHLc5ndRvtdGEztRTVXncVqrD2FCE7Y7R"]
        .iter().map(|s| s.to_string()).collect()
}
fn exec_rpc() -> Vec<String> { vec!["helius".into()] }
fn exec_max_size() -> f64 { 0.15 }
fn keepalive_s() -> u64 { 30 }
impl Default for ExecCfg {
    fn default() -> Self { ExecCfg { program: v2_program(), alts: v2_alts(), rpc: exec_rpc(), max_size_sol: exec_max_size(), keepalive_s: keepalive_s(),
        expected_program_sha256: String::new(), expected_program_md5: String::new() } }
}

/// STEP 2, free: build the real transaction for each would-send decision and simulate it (sims.jsonl). An answer of
/// "ok" or our profit check (0x4e580002) means every leg ran: the encoding is right; anything else names what is not.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SimCfg {
    #[serde(default)]
    pub enabled: bool,
    /// at most this many simulations a second (the rest are counted, not simulated)
    #[serde(default = "sim_rate")]
    pub max_per_sec: u32,
}
fn sim_rate() -> u32 { 2 }
impl Default for SimCfg { fn default() -> Self { SimCfg { enabled: false, max_per_sec: sim_rate() } } }

/// PLAN WP-05: a canary run (`arbx run --canary`, with `enabled = true` here) is a live run under these caps: real
/// bundles, size at most `size_sol` (0.2 SOL at most), at most `count` attempts, `every_ms` apart, stopping once landed
/// failures' fees reach `max_spend_lamports`. Built-to-fail canaries under a durable nonce (and `nonce_account`,
/// `settle_s`) are gone: they only made sense for the direct paths
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CanaryCfg {
    #[serde(default)]
    pub enabled: bool,
    /// how many attempts in all (per segment); 0 = no attempt cap (WP-07: a 24 h baseline such as FT-005 is bounded by
    /// the equity stops, the spend cap and `every_ms` instead)
    #[serde(default = "canary_count")]
    pub count: u32,
    /// at least this long between two attempts, ms
    #[serde(default = "canary_every")]
    pub every_ms: u64,
    /// trade size cap, SOL (refused above 0.2)
    #[serde(default = "canary_size")]
    pub size_sol: f64,
    /// stop once fees of landed failures plus the worst case of those in flight would pass this, lamports
    #[serde(default = "canary_spend")]
    pub max_spend_lamports: u64,
}
fn canary_count() -> u32 { 100 }
fn canary_every() -> u64 { 5_000 }
fn canary_size() -> f64 { 0.01 }
fn canary_spend() -> u64 { 3_000_000 }
/// PLAN WP-05: a canary trades at most this much
pub const CANARY_MAX_SIZE_SOL: f64 = 0.2;
impl Default for CanaryCfg {
    fn default() -> Self { CanaryCfg { enabled: false, count: canary_count(), every_ms: canary_every(), size_sol: canary_size(), max_spend_lamports: canary_spend() } }
}

fn shadow() -> String { "shadow".into() }
fn trading() -> String { "trading".into() }
fn skip_signers() -> bool { true }

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct PoolsCfg {
    /// seed pools (venue,pool,vault_a,vault_b,mint_a,mint_b,...) — the pools whose swaps we react to
    pub seed_csv: String,
    /// the current bot's registry.json ("our" pools): with `registry_all`, every pool on a supported venue is watched;
    /// otherwise only those on the same token pairs as the seed pools
    pub registry_json: Option<String>,
    #[serde(default)]
    pub registry_all: bool,
    /// the current bot's templates.json: its lookup tables seed the feed filter
    pub templates_json: Option<String>,
    /// quote mints we start and end a cycle in (default: WSOL)
    #[serde(default = "wsol")]
    pub quote_mints: Vec<String>,
}
fn wsol() -> Vec<String> { vec!["So11111111111111111111111111111111111111112".into()] }

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RpcCfg {
    /// env var holding the RPC URL (account snapshots, lookup tables, blockhash, signature statuses)
    pub url_env: Option<String>,
    /// several providers raced on every call (the fastest answer wins; all are timed)
    #[serde(default, rename = "endpoint")]
    pub endpoints: Vec<RpcEndpointCfg>,
    /// try the endpoints in the listed order, the next only on failure (default: race them all)
    #[serde(default)]
    pub failover: bool,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct RpcEndpointCfg {
    pub name: String,
    /// env var with the full URL (key included if the provider puts it in the URL)
    pub url_env: Option<String>,
    /// or a fixed URL (no secret in it)
    pub url: Option<String>,
    /// env var whose value is sent as `Authorization: Bearer <value>`
    pub bearer_env: Option<String>,
    #[serde(default = "yes")]
    pub enabled: bool,
}

impl RpcCfg {
    /// providers whose environment is complete; the others are skipped with a note
    pub fn endpoints(&self) -> (Vec<crate::rpc::Endpoint>, Vec<String>) {
        let mut eps = Vec::new();
        let mut skipped = Vec::new();
        if let Some(v) = &self.url_env { if let Ok(u) = std::env::var(v) { if !u.trim().is_empty() { eps.push(crate::rpc::Endpoint { name: "default".into(), url: u.trim().into(), bearer: None }); } } }
        for e in self.endpoints.iter().filter(|e| e.enabled) {
            let url = match (&e.url_env, &e.url) {
                (Some(v), _) => std::env::var(v).ok().filter(|u| !u.trim().is_empty()).map(|u| u.trim().to_string()),
                (None, Some(u)) => expand(u),
                _ => None,
            };
            let bearer = match &e.bearer_env { Some(v) => match std::env::var(v) { Ok(b) if !b.trim().is_empty() => Some(Some(b.trim().to_string())), _ => None }, None => Some(None) };
            match (url, bearer) {
                (Some(url), Some(bearer)) => eps.push(crate::rpc::Endpoint { name: e.name.clone(), url, bearer }),
                _ => skipped.push(e.name.clone()),
            }
        }
        (eps, skipped)
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StateCfg {
    /// Yellowstone endpoint for pool-state account updates
    pub url: String,
    pub token_env: Option<String>,
    /// WP-03 item 2: also follow the Clock sysvar (chain time, WP-04)
    #[serde(default = "yes")]
    pub watch_clock: bool,
    /// ... the programdata accounts of the route program and every venue program (upgrade detection, WP-07)
    #[serde(default = "yes")]
    pub watch_programdata: bool,
    /// ... the wallet and its token accounts (every landed transaction we pay for writes the wallet: its `txn` names
    /// it, WP-03b)
    #[serde(default = "yes")]
    pub watch_wallet: bool,
    /// WP-03 item 7: "all" (processed, confirmed, finalized and the interslot first-shred, completed, created-bank,
    /// dead, with parents), "commitment" (the first three only, arb-lab's subscription), or "auto" (the default: "all"
    /// where `arbx grpc-probe` accepted `slots_interslot` on this provider, else "commitment"; review WP-03 #5: the
    /// interslot filter shares the state stream's one subscription, and a refusal would refuse the accounts too)
    #[serde(default = "slot_statuses_auto")]
    pub slot_statuses: String,
    /// WP-03 item 6: subscribe to `blocks_meta`: "on", "off", or "auto" (on if `arbx grpc-probe` accepted it on this
    /// provider: `probe_file`)
    #[serde(default = "block_meta_auto")]
    pub block_meta: String,
    /// the probe result `block_meta = "auto"` and `slot_statuses = "auto"` read ("" = `<out_dir>/probe.json`, where
    /// `arbx grpc-probe` writes it)
    #[serde(default)]
    pub probe_file: String,
    /// WP-03 item 3: the executed-transaction streams (Yellowstone transaction filters). Each runs as a feed
    /// (`yellowstone-tx`) after the `[[feed]]` list; Stage 0 has one, on the PumpSwap program
    #[serde(default, rename = "tx_stream")]
    pub tx_streams: Vec<TxStreamCfg>,
    /// WP-04 item 3 (CommitTracker): a transaction whose write set W(T) is known stays pending at most this long after
    /// its first account update (then `timeout_unknown`), ms
    #[serde(default = "commit_timeout_ms")]
    pub commit_timeout_ms: u64,
    /// ... one whose W(T) is unknown resolves when no update stamped with it arrived for this long (`timeout_quiescent`),
    /// and the routes of a group resolved by a timeout need every account of both pools quiet this long, ms. 3 is a
    /// placeholder until WP-03 recordings measure the spread of one transaction's updates (arb-lab's moves logs, first
    /// update per pool only: 0.38-0.63 ms at p99.9 across the pools of one transaction, w5h2-p1/p2, w5h-p12)
    #[serde(default = "quiescence_ms")]
    pub quiescence_ms: u64,
    /// WP-04 item 4: a pool's consistency set (the accounts every swap of it writes) may span at most this many slots
    #[serde(default = "two")]
    pub max_part_skew_slots: u64,
    /// ... and the store may be at most this many slots behind the chain tip (the warm-up gate too)
    #[serde(default = "two")]
    pub max_tip_lag_slots: u64,
    /// WP-04 item 6: DLMM and DAMM v2 routes are refused (`clock_stale`) when the Clock sysvar is more than this many
    /// slots behind the tip
    #[serde(default = "two")]
    pub clock_max_age_slots: u64,
    /// WP-04 item 8: the lag SLO (first shred of T to T's complete commit), checked every minute
    #[serde(default = "slo_p50")]
    pub lag_slo_p50_ms: f64,
    #[serde(default = "slo_p90")]
    pub lag_slo_p90_ms: f64,
    #[serde(default = "slo_breach")]
    pub lag_slo_breach_minutes: u32,
    /// "log" (Stage 0: breaches are recorded only) or "shadow" (`lag_slo_breach_minutes` breaches in a row shadow the
    /// SendGate, reason `state_slo`; `slo_recover_minutes` good minutes in a row bring it back; F32)
    #[serde(default = "slo_log")]
    pub slo_action: String,
    #[serde(default = "slo_recover")]
    pub slo_recover_minutes: u32,
    /// WP-04 item 8: a Tier-A pool whose parts are still missing this long after the engine started leaves Tier A, so
    /// one dead pool cannot hold the warm-up gate shut, s
    #[serde(default = "tier_a_grace")]
    pub tier_a_grace_s: u64,
    /// PLAN-ADDENDUM I-4: the run stops (`state_unavailable`) when the state stream has delivered nothing this long after
    /// the engine started, s (0: never)
    #[serde(default = "boot_timeout")]
    pub boot_timeout_s: u64,
    /// ... and nothing is priced or sent while the stream is down or its newest message is older than this, ms
    #[serde(default = "max_update_age")]
    pub max_update_age_ms: u64,
    /// ... and a run whose state has been unavailable this long without a break (after it had delivered) stops with
    /// `state_unavailable` too, so the supervisor starts a fresh segment (review WP-04 #10: an outage after the first
    /// message otherwise runs blind to the deadline and exits 0), s; 0 never (the default: owner decision)
    #[serde(default)]
    pub unavailable_stop_s: u64,
    /// ... and every followed account is read again (RPC) after the stream's first connection and every reconnection
    /// (review WP-04 #1: writes not delivered meanwhile are not resent); until the re-read has landed the gate is shut
    /// (`resync`) and a pool with a part not read again since is refused (`resync`)
    #[serde(default = "yes")]
    pub resnapshot: bool,
    /// ... a WARNING when the re-read has not landed this long after the connection (the gate stays shut), s
    #[serde(default = "resync_warn")]
    pub resync_warn_s: u64,
    /// ... and a chunk of it still unread this long after the re-read started is given up: the gate opens, and the
    /// accounts it held stay refused one by one until the stream writes them, s
    #[serde(default = "resync_give_up")]
    pub resync_give_up_s: u64,
}
fn slot_statuses_auto() -> String { "auto".into() }
fn block_meta_auto() -> String { "auto".into() }
fn commit_timeout_ms() -> u64 { 5 }
fn quiescence_ms() -> u64 { 3 }
fn two() -> u64 { 2 }
fn slo_p50() -> f64 { 16.0 }
fn slo_p90() -> f64 { 30.0 }
fn slo_breach() -> u32 { 5 }
fn slo_log() -> String { "log".into() }
fn slo_recover() -> u32 { 10 }
fn tier_a_grace() -> u64 { 60 }
fn boot_timeout() -> u64 { 60 }
fn max_update_age() -> u64 { 2_000 }
fn resync_warn() -> u64 { 10 }
fn resync_give_up() -> u64 { 300 }

/// Lookup tables (PLAN WP-04 item 7; PLAN-ADDENDUM I-6): a failed fetch is retried, never cached as missing for the run
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AltsCfg {
    /// the retries after the 1st, 2nd, ... failure, ms; then every `retry_every_s`
    #[serde(default = "alt_retry_ms")]
    pub retry_ms: Vec<u64>,
    #[serde(default = "alt_retry_every")]
    pub retry_every_s: u64,
    /// a table still not fetched this long after its first failure is given up (its waiting transactions dropped), s
    #[serde(default = "alt_give_up")]
    pub give_up_s: u64,
    /// transactions waiting for tables, at most (the oldest are dropped and counted)
    #[serde(default = "alt_wait_cap")]
    pub wait_cap: usize,
    /// fetches running at once, at most (the rest queue)
    #[serde(default = "alt_inflight")]
    pub max_inflight: usize,
    /// a previous segment's `alts-final.jsonl.zst` to start with: "auto" (the newest one in this run directory's sibling
    /// segments), a path, or "" (none)
    #[serde(default = "auto")]
    pub preload: String,
    /// review WP-04 #11: only the tables a transaction used in the last `preload_max_age_h` hours are preloaded (each
    /// segment's alts-final says when each table was last used), at most `preload_max_tables` of them (the most recently
    /// used): the set no longer grows across a campaign, and neither does the journal's boot section that holds it
    #[serde(default = "alt_preload_age")]
    pub preload_max_age_h: u64,
    #[serde(default = "alt_preload_max")]
    pub preload_max_tables: usize,
}
fn alt_retry_ms() -> Vec<u64> { vec![50, 250, 1_000, 5_000] }
fn alt_retry_every() -> u64 { 30 }
fn alt_give_up() -> u64 { 600 }
fn alt_wait_cap() -> usize { 10_000 }
fn alt_inflight() -> usize { 16 }
fn auto() -> String { "auto".into() }
fn alt_preload_age() -> u64 { 24 }
fn alt_preload_max() -> usize { 5_000 }
impl Default for AltsCfg {
    fn default() -> Self {
        AltsCfg { retry_ms: alt_retry_ms(), retry_every_s: alt_retry_every(), give_up_s: alt_give_up(), wait_cap: alt_wait_cap(), max_inflight: alt_inflight(), preload: auto(),
            preload_max_age_h: alt_preload_age(), preload_max_tables: alt_preload_max() }
    }
}

/// The accuracy monitor (PLAN WP-04 item 13): decoded hints scored against their transaction's pre-state
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AccuracyCfg {
    /// "log": no quarantine acts in Stage 0 (OD-8)
    #[serde(default = "slo_log")]
    pub action: String,
    /// versions kept per account (the pre-state, fork rollback)
    #[serde(default = "ring_versions")]
    pub ring_versions: usize,
    /// scores waiting for idle time, at most (overflow counted)
    #[serde(default = "acc_queue")]
    pub queue: usize,
}
fn ring_versions() -> usize { 8 }
fn acc_queue() -> usize { 10_000 }
impl Default for AccuracyCfg { fn default() -> Self { AccuracyCfg { action: slo_log(), ring_versions: ring_versions(), queue: acc_queue() } } }

/// One executed-transaction stream (`[[state.tx_stream]]`, WP-03 item 3). The provider of the Stage-0 plan allows one
/// transaction filter with one account; a second filter or provider covering the other venues is owner decision OD-1
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct TxStreamCfg {
    pub name: String,
    #[serde(default = "yes")]
    pub enabled: bool,
    /// default: `[state] url`
    pub url: Option<String>,
    /// default: `[state] token_env`
    pub token_env: Option<String>,
    pub token_header: Option<String>,
    /// literal base58 keys, or `@watched_writable` (every watched pool and vault) / `@venue_programs` (the venue programs)
    #[serde(default)]
    pub account_include: Vec<String>,
    /// deliver failed transactions too (default true; false: successful only)
    #[serde(default = "yes")]
    pub failed: bool,
    /// the provider's limit of accounts per filter: an expanded list longer than this refuses to start
    pub max_accounts: Option<usize>,
}

/// The LeaderBook's sources (src/leaders.rs; WP-03 item 10) and its metadata and RTT probe (WP-08 item 1)
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LeadersCfg {
    #[serde(default = "yes")]
    pub enabled: bool,
    /// Jito validators API URLs (`{"validators": [{identity_account, running_jito, running_bam}]}`)
    #[serde(default = "leader_lists")]
    pub validator_lists: Vec<String>,
    /// the dated static fallback
    #[serde(default = "leader_static")]
    pub static_fallback: String,
    /// how often the lists and the vote accounts are fetched again, minutes (WP-08: validators.jsonl every 10 minutes)
    #[serde(default = "leader_refresh")]
    pub refresh_min: u64,
    /// WP-08: measure host -> leader TPU-QUIC RTT with a QUIC handshake (no data sent) to the next leaders' announced
    /// TPU-QUIC endpoints, once per endpoint however many validators share it (F40)
    #[serde(default = "yes")]
    pub rtt_probe: bool,
    /// ... at most this many handshakes a second
    #[serde(default = "leader_rtt_per_sec")]
    pub rtt_per_sec: f64,
    /// WP-08: the offline IP -> location table (DB-IP City Lite ranges): a validator's city and region (metro) from its
    /// gossip IP, its TPU-QUIC endpoint's region (the RTT fallback's bucket)
    #[serde(default = "leader_geo")]
    pub geo_table: String,
}
fn leader_lists() -> Vec<String> { vec!["https://kobe.mainnet.jito.network/api/v1/validators".into()] }
fn leader_static() -> String { "data/validators-meta.json".into() }
fn leader_refresh() -> u64 { 60 }
fn leader_rtt_per_sec() -> f64 { 2.0 }
fn leader_geo() -> String { "data/ip-geo.csv".into() }
impl Default for LeadersCfg {
    fn default() -> Self { LeadersCfg { enabled: true, validator_lists: leader_lists(), static_fallback: leader_static(), refresh_min: leader_refresh(),
        rtt_probe: true, rtt_per_sec: leader_rtt_per_sec(), geo_table: leader_geo() } }
}

/// `[[state.tx_stream]]` include tokens (expanded once the registry is booted: `expand_includes`)
pub const WATCHED_WRITABLE: &str = "@watched_writable";
pub const VENUE_PROGRAMS: &str = "@venue_programs";

impl StateCfg {
    /// the transaction streams as feeds (kind `yellowstone-tx`), url and token defaulting to the state stream's
    pub fn tx_stream_feeds(&self) -> Vec<Feed> {
        self.tx_streams.iter().map(|t| Feed { name: t.name.clone(), kind: FeedKind::YellowstoneTx, enabled: t.enabled, bind: None, group: None, port: None,
            interface: None, allowed_src: vec![], url: Some(t.url.clone().unwrap_or_else(|| self.url.clone())), token_env: t.token_env.clone().or_else(|| self.token_env.clone()),
            token_header: t.token_header.clone(), account_include: t.account_include.clone(), split_include: false,
            failed: if t.failed { None } else { Some(false) }, max_accounts: t.max_accounts }).collect()
    }
}

/// Replace the `@watched_writable` / `@venue_programs` tokens of every gRPC feed's include list, and refuse a list
/// longer than its feed's `max_accounts`
pub fn expand_includes(feeds: &mut [Feed], watched_writable: &[String], venue_programs: &[String]) -> Result<()> {
    for f in feeds.iter_mut() {
        if f.account_include.iter().any(|a| a.starts_with('@')) {
            let mut out: Vec<String> = Vec::new();
            for a in &f.account_include {
                let add: Vec<String> = match a.as_str() { WATCHED_WRITABLE => watched_writable.to_vec(), VENUE_PROGRAMS => venue_programs.to_vec(), x => vec![x.to_string()] };
                for k in add { if !out.contains(&k) { out.push(k); } }
            }
            f.account_include = out;
        }
        if let Some(m) = f.max_accounts.filter(|m| f.account_include.len() > *m) {
            bail!("feed {}: account_include holds {} accounts, more than its max_accounts {m} (the provider's limit; OD-1)", f.name, f.account_include.len());
        }
    }
    Ok(())
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct StrategyCfg {
    /// trade sizes tried per opportunity, in SOL
    #[serde(default = "sizes")]
    pub sizes_sol: Vec<f64>,
    /// minimum net profit after fees and tip, in lamports
    #[serde(default = "min_profit")]
    pub min_profit_lamports: u64,
    /// priority fee for our transaction, micro-lamports per CU
    #[serde(default = "cu_price")]
    pub cu_price_micro: u64,
    /// how long (ms) after a trigger we keep watching the pools for who took the opportunity
    #[serde(default = "watch_ms")]
    pub outcome_watch_ms: u64,
    /// per trigger signer (ok, failed) carried across runs: read once at start (its sha256 goes to run.log and the
    /// journal's engine_init); never written by a run (PLAN-ADDENDUM I-5): each segment writes its own copy and this
    /// segment's counts into its run directory (`signer-stats.json`, `signer-stats-delta.json`), and merging them back is
    /// an explicit step (`arbx signer-stats merge`). "" starts empty
    #[serde(default)]
    pub signer_stats_file: String,
    /// skip triggers from signers whose triggers mostly fail. Decoded swaps are hints only (WP-04): the skip drops only
    /// the hint's accuracy check (its write set is still registered with the CommitTracker)
    #[serde(default = "skip_signers")]
    pub skip_failing_signers: bool,
    /// price on committed state: whenever a transaction's writes to one of our pools are complete (its commit group
    /// resolved, WP-04), the pool's routes are evaluated. The only pricing path (decoded swaps are hints)
    #[serde(default)]
    pub state_triggers: bool,
    /// record, per opportunity, the best round trip at each of these budgets (SOL) to caps.jsonl (what a bigger
    /// balance would add; nothing is traded above live.max_size_sol)
    #[serde(default)]
    pub budget_caps_sol: Vec<f64>,
}
fn yes() -> bool { true }
fn sizes() -> Vec<f64> { vec![0.02, 0.05, 0.1, 0.2, 0.5, 1.0] }
fn min_profit() -> u64 { 10_000 }
fn cu_price() -> u64 { 40_000 }
fn watch_ms() -> u64 { 2_000 }
impl Default for StrategyCfg {
    fn default() -> Self { StrategyCfg { sizes_sol: sizes(), min_profit_lamports: min_profit(), cu_price_micro: cu_price(), outcome_watch_ms: watch_ms(), signer_stats_file: String::new(), skip_failing_signers: true, state_triggers: false, budget_caps_sol: vec![] } }
}

#[derive(Debug, Clone, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "kebab-case")]
pub enum FeedKind {
    /// raw shreds pushed over UDP
    Udp,
    /// raw shreds over multicast (DoubleZero)
    Multicast,
    /// Jito ShredStream entries over gRPC (ERPC, Constant-K ShredPrism, ...)
    JitoEntries,
    /// Yellowstone SubscribeDeshred (unexecuted transactions)
    YellowstoneDeshred,
    /// Yellowstone Subscribe transactions at processed (executed)
    YellowstoneTx,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct Feed {
    pub name: String,
    pub kind: FeedKind,
    #[serde(default = "yes")]
    pub enabled: bool,
    pub bind: Option<String>,
    pub group: Option<String>,
    pub port: Option<u16>,
    pub interface: Option<String>,
    #[serde(default)]
    pub allowed_src: Vec<String>,
    pub url: Option<String>,
    pub token_env: Option<String>,
    pub token_header: Option<String>,
    /// Yellowstone filters: program/account include list (empty = the watched venue programs)
    #[serde(default)]
    pub account_include: Vec<String>,
    /// one filter per include entry (plans that allow 1 account per filter)
    #[serde(default)]
    pub split_include: bool,
    /// yellowstone-tx: Some(false) delivers successful transactions only; None both (`[[state.tx_stream]] failed`)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub failed: Option<bool>,
    /// yellowstone-tx: the provider's limit of accounts per filter
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub max_accounts: Option<usize>,
}

#[derive(Debug, Clone, Copy, Deserialize, Serialize, PartialEq)]
#[serde(rename_all = "kebab-case")]
pub enum SendKind {
    /// Jito block engine searcher gRPC: a one-transaction bundle, authenticated with a whitelisted keypair
    /// (`auth_keypair`). A bundle whose transaction would fail is dropped, so a lost race costs nothing
    JitoBundle,
    /// Jito block engine JSON-RPC sendTransaction (`token_env`: the UUID sent as `x-jito-auth`, optional)
    JitoTx,
    /// Helius Sender (JSON-RPC sendTransaction, base64; `?swqos_only=true` in the URL for the 5,000-lamport tier)
    Helius,
    /// Shyft staked RPC (SWQoS): JSON-RPC sendTransaction, no tip
    Shyft,
    /// RPC Fast Beam: JSON-RPC sendTransaction (base64); the tip account picks Beam's provider (Astralane)
    Rpcfast,
    /// Haan Sender: POST raw bytes, `Authorization: Bearer` (`token_env`) + `x-jito-auth` (`jito_auth_env`); no tip
    Haan,
    /// Raiden Bolt (POST raw bytes, header api-x-token)
    Bolt,
    /// Astralane Iris binary (POST raw bytes, ?api-key=&method=sendTransaction)
    Iris,
    /// Hello Moon Lunar Lander binary (POST raw bytes to /send-bin?api-key=)
    Lunar,
    /// direct to the leader: QUIC to the current and next leader's TPU, no relay, no tip. `url` is an RPC used for the
    /// leader schedule and the validators' TPU addresses
    Tpu,
    /// any JSON-RPC sendTransaction endpoint without a tip (a staked RPC, e.g. Helius's normal RPC on a paid plan)
    Rpc,
    // senders the rivals use (research log S-011; formats from each provider's docs, 2026-10-03)
    /// Temporal Nozomi: JSON-RPC sendTransaction, key in the URL (?c=); tip >= 0.001 SOL (lower is dropped silently)
    Nozomi,
    /// Jupiter tx.jup.ag: JSON-RPC sendTransaction, base64, skipPreflight/maxRetries 0; key as header x-api-key
    /// (token_env); tip >= 0.001 SOL to one of its 16 receivers (developers.jup.ag/docs/transaction/submit, 2026-07-29)
    JupiterTx,
    /// LandX (landx.dev): tip >= 0.001 SOL to one of its 10 receivers. url `udp://host:10000` (packet = the 12-byte key from
    /// token_env, then the transaction bytes; no reply; fra3 sits in Cherry Servers Frankfurt) or `http://host/txb/${KEY}` (raw bytes)
    Landx,
    /// SpeedLanding (speedlanding.trade/docs.html): JSON-RPC sendTransaction (base64) to /sendTx?apikey=<key> on port 80,
    /// GET /ping keep-alive; tip >= 0.001 SOL to one of its 8 receivers
    SpeedLanding,
    /// 0slot: JSON-RPC sendTransaction, key in the URL (?api-key=); tip >= 0.001 SOL
    #[serde(rename = "0slot")]
    ZeroSlot,
    /// NodeOne: raw bytes to /v2, header api-key (token_env); tip >= 0.001 SOL
    NodeOne,
    /// Corvus Falcon: JSON-RPC sendTransaction, key in the URL (?api-key=); tip >= 0.001 SOL, static top-level transfer
    Falcon,
    /// Everstake SWQoS: JSON-RPC sendTransaction, NO key; tip >= 0.001 SOL as the first instruction, not via a table
    Everstake,
    /// BlockRazor: raw bytes to /v2/sendBinaryTransaction, key in the URL (?auth=); tip >= 0.0001 SOL
    BlockRazor,
    /// FlashBlock: POST /api/v2/submit-batch {"transactions":[b64]}, header Authorization (token_env); tip >= 0.0001 SOL
    FlashBlock,
    /// NextBlock: POST /api/v2/submit {"transaction":{"content":b64}}, header Authorization (token_env); tip 0.001 SOL
    NextBlock,
    /// bloXroute Trader API: POST /api/v2/submit {"transaction":{"content":b64}}, header Authorization; tip >= 0.001 SOL
    Bloxroute,
}

impl SendKind {
    /// the tip this path refuses to deliver without (lamports); 0 = no tip needed
    pub fn min_tip(self) -> u64 {
        match self {
            // Jito's floor; Helius's swqos_only tier (Sender Max wants 1,000,000); Beam's Astralane minimum; Iris at VIP 3
            // (the free tier wants 1,000,000); Bolt and Lunar Lander 0.001 SOL
            SendKind::JitoBundle | SendKind::JitoTx => 1_000,
            SendKind::Helius => 5_000,
            SendKind::Rpcfast | SendKind::Iris => 10_000,
            SendKind::Bolt | SendKind::Lunar => 1_000_000,
            SendKind::Shyft | SendKind::Haan | SendKind::Tpu | SendKind::Rpc => 0,
            SendKind::BlockRazor | SendKind::FlashBlock => 100_000,
            SendKind::Nozomi | SendKind::ZeroSlot | SendKind::NodeOne | SendKind::Falcon | SendKind::Everstake | SendKind::NextBlock | SendKind::Bloxroute
            | SendKind::JupiterTx | SendKind::Landx | SendKind::SpeedLanding => 1_000_000,
        }
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct SendPath {
    pub name: String,
    pub kind: SendKind,
    #[serde(default = "yes")]
    pub enabled: bool,
    /// endpoint; `${NAME}` is replaced from the environment (for keys that live in the URL). jito-bundle: the block
    /// engine's gRPC URL (https://frankfurt.mainnet.block-engine.jito.wtf)
    pub url: String,
    /// env var with the API key / auth value (jito-tx: x-jito-auth; haan: Bearer; bolt: api-x-token)
    pub token_env: Option<String>,
    /// haan: env var with the `x-jito-auth` value (the Jito UUID)
    pub jito_auth_env: Option<String>,
    /// tip paid to this path's tip accounts, lamports (only paid when the trade succeeds: the tip transfer comes
    /// after the profit check in the same transaction). jito-bundle with `tip_share`: the floor
    #[serde(default)]
    pub tip_lamports: u64,
    /// jito-bundle: tip this share of the predicted gross edge, never below `tip_lamports` or above `tip_max_lamports`
    pub tip_share: Option<f64>,
    pub tip_max_lamports: Option<u64>,
    /// tip accounts (base58); one is picked per send, in rotation. Empty = the provider's whole documented list
    #[serde(default)]
    pub tip_accounts: Vec<String>,
    /// at most this many sends in any rolling second (the plan's limit); a send over it is refused
    pub max_per_sec: Option<u32>,
    /// with the rate full, wait up to this long for a slot (best first: seed pools, then expected profit); 0 = refuse
    #[serde(default)]
    pub queue_ms: u64,
    /// jito-bundle: the whitelisted auth keypair (solana-keygen JSON; never the trading wallet). Default
    /// ~/.nexus-v2-jito-auth.json, the current bot's
    pub auth_keypair: Option<String>,
    /// JSON-RPC paths: let the endpoint run its own preflight simulation (default: skip it)
    #[serde(default)]
    pub preflight: bool,
    /// keep-alive URL (GET) hit every 20 s; default per kind (Helius /ping, Iris /gethealth, JSON-RPC getHealth)
    pub ping_url: Option<String>,
    /// PLAN-ADDENDUM I-10: a secret (`${...}`) in an `http://` URL is refused unless the provider has no TLS endpoint;
    /// this says so, with the evidence (recorded: `arbx check`, run.log, meta.json `send_paths`)
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub no_tls_endpoint: Option<String>,
}

impl Config {
    pub fn load(path: &Path) -> Result<Config> { Ok(Config::load_raw(path)?.0) }

    /// the parsed config and the file's raw bytes (meta.json `config.file_sha256`, the run directory's frozen copy)
    pub fn load_raw(path: &Path) -> Result<(Config, Vec<u8>)> {
        let raw = std::fs::read(path).with_context(|| format!("reading {}", path.display()))?;
        let text = std::str::from_utf8(&raw).with_context(|| format!("{}: not UTF-8", path.display()))?;
        let cfg = Config::parse(text).with_context(|| format!("parsing {}", path.display()))?;
        Ok((cfg, raw))
    }

    /// a config file's text, parsed and checked
    pub fn parse(text: &str) -> Result<Config> {
        // the version first, so an arb-lab (v1) file is named as such rather than by its first unknown key
        if let Ok(v) = text.parse::<toml::Table>() {
            match v.get("config_version") {
                None => bail!("config_version = {CONFIG_VERSION} is required (this file has none: an arb-lab v1 config? those stay in deploy/legacy/)"),
                Some(toml::Value::Integer(n)) if *n == CONFIG_VERSION as i64 => {}
                Some(x) => bail!("config_version {x} is not supported: this binary reads config_version = {CONFIG_VERSION}"),
            }
        }
        let cfg: Config = toml::from_str(text)?;
        if cfg.config_version != Some(CONFIG_VERSION) { bail!("config_version = {CONFIG_VERSION} is required"); }
        if cfg.mode != "shadow" && cfg.mode != "live" { bail!("mode must be \"shadow\" or \"live\""); }
        for (k, v, n) in [("expected_program_sha256", &cfg.exec.expected_program_sha256, 64), ("expected_program_md5", &cfg.exec.expected_program_md5, 32)] {
            if !v.is_empty() && (v.len() != n || !v.bytes().all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))) {
                bail!("[exec] {k} must be {n} lowercase hex characters (or \"\" for no check)");
            }
        }
        let mut names = std::collections::HashSet::new();
        for f in &cfg.feeds {
            if !names.insert(f.name.clone()) { bail!("duplicate feed name {}", f.name); }
            match f.kind {
                FeedKind::Udp => { if f.bind.is_none() { bail!("{}: udp needs `bind`", f.name); } }
                FeedKind::Multicast => {
                    if f.group.is_none() || f.port.is_none() || f.interface.is_none() { bail!("{}: multicast needs group, port, interface", f.name); }
                }
                _ => { if f.url.is_none() { bail!("{}: grpc feeds need `url`", f.name); } }
            }
        }
        let mut names = std::collections::HashSet::new();
        for s in &cfg.sends {
            if !names.insert(s.name.clone()) { bail!("duplicate send path name {}", s.name); }
            let min = s.kind.min_tip();
            if s.tip_lamports < min { bail!("send path {}: {:?} needs tip_lamports >= {min}", s.name, s.kind); }
            // tip accounts default to the provider's own list (send::known_tip_accounts); a configured one must be on it
            let known = crate::send::known_tip_accounts(s.kind);
            if s.tip_lamports > 0 && known.is_empty() { bail!("send path {}: {:?} takes no tip", s.name, s.kind); }
            for a in &s.tip_accounts {
                if !known.contains(&a.as_str()) { bail!("send path {}: tip account {a} is not one of {:?}'s documented tip accounts", s.name, s.kind); }
            }
            if let Some(x) = s.tip_share {
                // any tipped path may tip a share of the expected profit (paid only when the trade succeeds), its minimum the floor
                if crate::send::known_tip_accounts(s.kind).is_empty() { bail!("send path {}: tip_share needs a path that takes a tip", s.name); }
                if !(0.0..=1.0).contains(&x) { bail!("send path {}: tip_share is a share of the edge, 0..1", s.name); }
            }
            if s.tip_max_lamports.is_some_and(|m| m < s.tip_lamports) { bail!("send path {}: tip_max_lamports is below tip_lamports", s.name); }
            if s.max_per_sec == Some(0) { bail!("send path {}: max_per_sec must be at least 1", s.name); }
            if s.queue_ms > 0 && s.max_per_sec.is_none() { bail!("send path {}: queue_ms needs max_per_sec", s.name); }
            // WP-05: the bundle path's queue is the send policy's (one queue_ms for the bands, the crowding and lambda)
            if s.kind == SendKind::JitoBundle && s.queue_ms > 0 { bail!("send path {}: a jito-bundle path waits [send_policy] queue_ms, not its own queue_ms", s.name); }
            // PLAN-ADDENDUM I-10: a secret may travel only over TLS (or QUIC) or in a header
            if s.enabled { cleartext_check(s)?; }
        }
        // PLAN WP-05 item 1: live sends are one-transaction Jito bundles; every other kind stays compiled (`arbx senders`
        // checks, a future direct experiment) but may not be enabled in a live config
        if cfg.mode == "live" { bundle_only(&cfg.sends).map_err(|e| anyhow::anyhow!("mode = \"live\": {e}"))?; }
        let sp = &cfg.send_policy;
        if sp.direct_experiment { bail!("[send_policy] direct_experiment = true is refused in Stage 0 (bundle-only; PLAN WP-05 item 1)"); }
        if !["confirmed", "processed"].contains(&sp.blockhash_commitment.as_str()) { bail!("[send_policy] blockhash_commitment must be \"confirmed\" or \"processed\""); }
        if sp.max_blockhash_age_slots == 0 || sp.max_blockhash_age_slots > 150 { bail!("[send_policy] max_blockhash_age_slots must be 1..150 (a blockhash is valid for 150 blocks)"); }
        let bb = sp.big_band_max_per_sec;
        if !bb.is_finite() || bb < 0.0 { bail!("[send_policy] big_band_max_per_sec must be a rate >= 0 (0 = no big-band trade)"); }
        // the bucket keeps the rate to 0.001 token/s: a smaller positive rate would silently mean "never"
        if bb > 0.0 && bb < 0.001 { bail!("[send_policy] big_band_max_per_sec {bb}: under 0.001/s (use 0 for no big-band trade)"); }
        if sp.crowding_window_h == 0 { bail!("[send_policy] crowding_window_h must be > 0"); }
        if sp.crowding_buckets.len() != 2 || sp.crowding_buckets[0] == 0 || sp.crowding_buckets[0] >= sp.crowding_buckets[1] {
            bail!("[send_policy] crowding_buckets must be two increasing positive signer counts (e.g. [20, 150])");
        }
        if sp.margin_floor == 0 { bail!("[send_policy] margin_floor must be >= 1 (a landed bundle must clear tip + fee + at least 1 lamport)"); }
        if !sp.margin_share.is_finite() || !(0.0..=1.0).contains(&sp.margin_share) { bail!("[send_policy] margin_share is a share of the expected net, 0..1"); }
        if sp.inflight_hold_slots == 0 { bail!("[send_policy] inflight_hold_slots must be >= 1"); }
        for k in &sp.skip_leader_kinds {
            if !["jito", "bam", "other", "unknown"].contains(&k.as_str()) { bail!("[send_policy] skip_leader_kinds: {k:?} is not a leader kind (jito, bam, other, unknown)"); }
        }
        if !(cfg.canary.size_sol > 0.0 && cfg.canary.size_sol <= CANARY_MAX_SIZE_SOL) { bail!("[canary] size_sol must be in (0, {CANARY_MAX_SIZE_SOL}] (PLAN WP-05: a canary is a small live run)"); }
        // WP-07: the bankroll cap, the ledger and the equity stops
        let l = &cfg.live;
        if !l.bankroll_share.is_finite() || !(0.0..=1.0).contains(&l.bankroll_share) { bail!("[live] bankroll_share is a share of the liquid SOL, 0..1 (0 = off)"); }
        if !l.bankroll_reserve_sol.is_finite() || l.bankroll_reserve_sol < 0.0 { bail!("[live] bankroll_reserve_sol must be >= 0"); }
        let lg = &cfg.ledger;
        if lg.snapshot_min == 0 || lg.snapshot_min > 24 * 60 { bail!("[ledger] snapshot_min must be 1..1440 minutes"); }
        // review WP-07 #3: the view must be refreshed before it can go stale by construction
        if lg.max_view_age_s < lg.snapshot_min * 60 { bail!("[ledger] max_view_age_s ({}) must be at least snapshot_min ({} min): the money view would go stale between snapshots", lg.max_view_age_s, lg.snapshot_min); }
        if lg.stale_after_failures == 0 { bail!("[ledger] stale_after_failures must be >= 1"); }
        if lg.max_record_wait_s < 10 { bail!("[ledger] max_record_wait_s must be >= 10"); }
        if lg.tolerance_lamports == 0 { bail!("[ledger] tolerance_lamports must be > 0"); }
        if lg.mid_source != "pools" { bail!("[ledger] mid_source must be \"pools\" (the engine's committed pool state)"); }
        if lg.snapshot_retries > 10 { bail!("[ledger] snapshot_retries must be 0..10"); }
        if lg.snapshot_retry_s == 0 || lg.recon_grace_s == 0 || lg.recon_grace_s > 3_600 { bail!("[ledger] snapshot_retry_s must be > 0 and recon_grace_s 1..3600"); }
        if !lg.token_haircut.is_finite() || !(0.0..1.0).contains(&lg.token_haircut) { bail!("[ledger] token_haircut is a share, 0..1"); }
        for m in &lg.extra_mints {
            if !bs58::decode(m).into_vec().is_ok_and(|b| b.len() == 32) { bail!("[ledger] extra_mints: {m:?} is not a base58 mint"); }
        }
        let sv = &cfg.supervisor;
        for (k, v) in [("max_drop_per_hour_sol", sv.max_drop_per_hour_sol), ("max_drop_per_day_sol", sv.max_drop_per_day_sol)] {
            if !v.is_finite() || v <= 0.0 { bail!("[supervisor] {k} must be a positive amount of SOL"); }
        }
        if sv.test_budget_lamports > TEST_BUDGET_HARD_CAP { bail!("[supervisor] test_budget_lamports {} is over the owner's hard cap {TEST_BUDGET_HARD_CAP} (docs/field-tests/BUDGET.md)", sv.test_budget_lamports); }
        if !sv.token_floor_tolerance.is_finite() || !(0.0..=0.1).contains(&sv.token_floor_tolerance) { bail!("[supervisor] token_floor_tolerance is a share of the start amount, 0..0.1"); }
        for (k, v) in [("rent_cap_sol", sv.rent_cap_sol), ("native_floor_sol", sv.native_floor_sol), ("unwrap_sol", sv.unwrap_sol)] {
            if !v.is_finite() || v < 0.0 { bail!("[supervisor] {k} must be >= 0"); }
        }
        if sv.auto_unwrap { bail!("[supervisor] auto_unwrap = true is refused in Stage 0: it writes to the wallet, an owner decision (R §6)"); }
        if sv.stranded_s == 0 || sv.equity_wait_s == 0 { bail!("[supervisor] stranded_s and equity_wait_s must be > 0"); }
        if cfg.dry_run.max_sim_per_sec == 0 { bail!("[dry_run] max_sim_per_sec must be >= 1"); }
        if cfg.feeds.len() > u16::MAX as usize { bail!("too many feeds"); }
        // WP-03: the state stream's options and its transaction streams (feeds after the [[feed]] list)
        let st = &cfg.state;
        if !["auto", "all", "commitment"].contains(&st.slot_statuses.as_str()) { bail!("[state] slot_statuses must be \"auto\", \"all\" or \"commitment\""); }
        if !["auto", "on", "off"].contains(&st.block_meta.as_str()) { bail!("[state] block_meta must be \"auto\", \"on\" or \"off\""); }
        let mut tx_names = std::collections::HashSet::new();
        for t in &st.tx_streams {
            if !tx_names.insert(t.name.clone()) || cfg.feeds.iter().any(|f| f.name == t.name) { bail!("[[state.tx_stream]] {}: the name is taken (feed names are shared)", t.name); }
            if t.account_include.is_empty() { bail!("[[state.tx_stream]] {}: account_include is empty", t.name); }
            for a in &t.account_include {
                let ok = a == WATCHED_WRITABLE || a == VENUE_PROGRAMS || bs58::decode(a).into_vec().is_ok_and(|b| b.len() == 32);
                if !ok { bail!("[[state.tx_stream]] {}: account_include {a:?} is neither a base58 key nor {WATCHED_WRITABLE} / {VENUE_PROGRAMS}", t.name); }
            }
            if t.max_accounts == Some(0) { bail!("[[state.tx_stream]] {}: max_accounts must be at least 1", t.name); }
            let literal = t.account_include.iter().filter(|a| !a.starts_with('@')).count();
            if let Some(m) = t.max_accounts.filter(|m| literal > *m) { bail!("[[state.tx_stream]] {}: {literal} accounts in account_include, over max_accounts {m}", t.name); }
        }
        // review WP-03 N8: a [[feed]]'s literal include list is checked here, not first at run time after the boot
        for f in &cfg.feeds {
            if f.max_accounts == Some(0) { bail!("feed {}: max_accounts must be at least 1", f.name); }
            let literal: std::collections::HashSet<&String> = f.account_include.iter().filter(|a| !a.starts_with('@')).collect();
            if let Some(m) = f.max_accounts.filter(|m| literal.len() > *m) {
                bail!("feed {}: {} accounts in account_include, over max_accounts {m} (the provider's limit; OD-1)", f.name, literal.len());
            }
        }
        if cfg.leaders.refresh_min == 0 { bail!("[leaders] refresh_min must be > 0"); }
        // WP-04: the state consistency keys, [alts] and [accuracy]
        if st.commit_timeout_ms == 0 || st.quiescence_ms == 0 { bail!("[state] commit_timeout_ms and quiescence_ms must be > 0"); }
        if !["log", "shadow"].contains(&st.slo_action.as_str()) { bail!("[state] slo_action must be \"log\" or \"shadow\""); }
        for (k, v) in [("lag_slo_p50_ms", st.lag_slo_p50_ms), ("lag_slo_p90_ms", st.lag_slo_p90_ms)] { if !v.is_finite() || v <= 0.0 { bail!("[state] {k} must be a positive number"); } }
        if st.lag_slo_breach_minutes == 0 || st.slo_recover_minutes == 0 { bail!("[state] lag_slo_breach_minutes and slo_recover_minutes must be > 0"); }
        if st.max_update_age_ms == 0 { bail!("[state] max_update_age_ms must be > 0"); }
        if st.resync_warn_s == 0 || st.resync_give_up_s == 0 { bail!("[state] resync_warn_s and resync_give_up_s must be > 0"); }
        let a = &cfg.alts;
        if a.retry_ms.is_empty() || a.retry_ms.contains(&0) || a.retry_ms.windows(2).any(|w| w[0] > w[1]) { bail!("[alts] retry_ms must be a non-empty, non-decreasing list of positive delays"); }
        if a.retry_every_s == 0 || a.give_up_s == 0 || a.wait_cap == 0 || a.max_inflight == 0 { bail!("[alts] retry_every_s, give_up_s, wait_cap and max_inflight must be > 0"); }
        // OD-8: no quarantine acts in Stage 0
        if cfg.accuracy.action != "log" { bail!("[accuracy] action must be \"log\" in Stage 0 (no quarantine acts; OD-8)"); }
        if cfg.accuracy.ring_versions < 2 || cfg.accuracy.ring_versions > 64 { bail!("[accuracy] ring_versions must be 2..64"); }
        if cfg.accuracy.queue == 0 { bail!("[accuracy] queue must be > 0"); }
        let r = &cfg.record;
        // review N4: a zero budget (or byte cap) would stop (or drop) everything; the free-space floor may be 0
        for (k, v) in [("disk_budget_gb", r.disk_budget_gb), ("rotate_mb", r.rotate_mb), ("queue_max_mb", r.queue_max_mb)] {
            if !v.is_finite() || v <= 0.0 { bail!("[record] {k} must be a positive number"); }
        }
        if !r.min_free_gb.is_finite() || r.min_free_gb < 0.0 { bail!("[record] min_free_gb must be a number >= 0"); }
        if let Some(c) = r.writer_cpus.iter().find(|c| **c >= 1024) { bail!("[record] writer_cpus: CPU {c} is out of range (0..1023)"); }
        if r.flush_ms == 0 || r.rotate_min == 0 { bail!("[record] flush_ms and rotate_min must be > 0"); }
        if !(1..=19).contains(&r.zstd_level) { bail!("[record] zstd_level must be 1..19"); }
        if [r.queue_core, r.queue_accounts, r.queue_journal, r.queue_chain, r.queue_bulk].contains(&0) { bail!("[record] queue sizes must be > 0"); }
        if r.accounts_keyframe_every == 0 { bail!("[record] accounts_keyframe_every must be > 0"); }
        // WP-08: the RTT prober's rate; I-9's sampling (1 keeps every row)
        let rps = cfg.leaders.rtt_per_sec;
        if !(rps.is_finite() && rps > 0.0 && rps <= 20.0) { bail!("[leaders] rtt_per_sec must be in (0, 20] handshakes a second (got {rps})"); }
        if r.rivals_venues_sample == 0 { bail!("[record] rivals_venues_sample must be >= 1 (1 keeps every row)"); }
        // a typo would archive nothing, silently
        for a in &r.archive_feeds {
            match cfg.feeds.iter().find(|f| &f.name == a) {
                None => bail!("[record] archive_feeds: no [[feed]] named {a}"),
                Some(f) if f.is_raw() => bail!("[record] archive_feeds: {a} is a raw shred feed (only entries feeds are archived)"),
                Some(_) => {}
            }
        }
        if cfg.runtime.bg_threads == 0 { bail!("[runtime] bg_threads must be > 0"); }
        // WP-03b: [chainfetch]
        let cf = &cfg.chainfetch;
        match &cf.rps {
            CfRps::Auto(s) if s == "auto" => {}
            CfRps::Auto(s) => bail!("[chainfetch] rps must be \"auto\" or a number of requests/s (got {s:?})"),
            CfRps::Fixed(r) if !r.is_finite() || *r <= 0.0 => bail!("[chainfetch] rps must be > 0 (or \"auto\")"),
            CfRps::Fixed(_) => {}
        }
        if cf.after_ms < 100 { bail!("[chainfetch] after_ms must be at least 100"); }
        if cf.max_backlog == 0 { bail!("[chainfetch] max_backlog must be > 0"); }
        if cf.blockhash_poll_ms > 0 && cf.blockhash_poll_ms < 100 { bail!("[chainfetch] blockhash_poll_ms must be 0 (off) or at least 100"); }
        if !cf.default_max_rps.is_finite() || cf.default_max_rps < 0.0 { bail!("[chainfetch] default_max_rps must be a rate >= 0 (0 = no limit)"); }
        if cf.boot_retry_s == 0 { bail!("[chainfetch] boot_retry_s must be > 0"); }
        if cf.max_tx_version > 1 { bail!("[chainfetch] max_tx_version must be 0 or 1"); }
        let rpc_names: Vec<String> = cfg.rpc.url_env.iter().map(|_| "default".to_string()).chain(cfg.rpc.endpoints.iter().map(|e| e.name.clone())).collect();
        let mut seen = std::collections::HashSet::new();
        for p in &cf.providers {
            if !seen.insert(p.name.clone()) { bail!("[[chainfetch.provider]] {}: named twice", p.name); }
            if !rpc_names.contains(&p.name) { bail!("[[chainfetch.provider]] {}: no [[rpc.endpoint]] of that name", p.name); }
            for r in &p.roles {
                if !crate::rpc::Role::FETCH.iter().any(|x| x.as_str() == r) {
                    bail!("[[chainfetch.provider]] {}: role {r:?} is not a chain-fetch role (wallet, blockhash, backfill, slotidx, sample)", p.name);
                }
            }
            if let Some(m) = p.max_rps { if !m.is_finite() || m < 0.0 { bail!("[[chainfetch.provider]] {}: max_rps must be >= 0 (0 = no limit)", p.name); } }
            if let Some(b) = p.burst { if !b.is_finite() || b < 1.0 { bail!("[[chainfetch.provider]] {}: burst must be at least 1", p.name); } }
        }
        Ok(cfg)
    }

    /// The parsed config as JSON with every default filled in and every object's keys sorted: the same settings give
    /// the same text whatever the file's comments, order and formatting (meta.json `config.normalized_sha256`)
    pub fn normalized_json(&self) -> String {
        sorted(serde_json::to_value(self).expect("a config serializes")).to_string()
    }

    /// sha256 (hex) of `normalized_json`
    pub fn normalized_sha256(&self) -> String { crate::provenance::sha256_hex(self.normalized_json().as_bytes()) }

    /// WP-00 (review F3): a config whose strategy prices nothing runs, records and never finds an opportunity. Since
    /// WP-04 committed state is the only pricing path (`state_triggers`; decoded swaps are hints). `arbx check` and
    /// `arbx run` print this
    pub fn pricing_warning(&self) -> Option<String> {
        (!self.strategy.state_triggers).then(|| "WARNING: [strategy] state_triggers is off: nothing is priced (decoded swaps are hints only), no opportunity can be found".to_string())
    }
}

/// PLAN WP-05 item 1: only jito-bundle paths enabled (a live config, a canary or live run); Err names the others
pub fn bundle_only(sends: &[SendPath]) -> Result<()> {
    let other: Vec<String> = sends.iter().filter(|s| s.enabled && s.kind != SendKind::JitoBundle).map(|s| format!("{} ({:?})", s.name, s.kind)).collect();
    if !other.is_empty() { bail!("only jito-bundle send paths may be enabled (bundle-only); enabled: {}", other.join(", ")); }
    if !sends.iter().any(|s| s.enabled && s.kind == SendKind::JitoBundle) { bail!("no jito-bundle send path is enabled"); }
    Ok(())
}

/// the `${NAME}` variables a string names
pub fn env_vars(s: &str) -> Vec<String> {
    let mut out = Vec::new();
    let mut rest = s;
    while let Some(i) = rest.find("${") {
        let Some(j) = rest[i..].find('}') else { break };
        out.push(rest[i + 2..i + j].to_string());
        rest = &rest[i + j + 1..];
    }
    out
}

/// a URL whose scheme carries its data in clear text: `http://`, and `udp://` (LandX's key starts every packet)
pub fn cleartext_scheme(u: &str) -> bool {
    let l = u.trim_start().to_ascii_lowercase();
    l.starts_with("http://") || l.starts_with("udp://")
}

/// PLAN-ADDENDUM I-10: a sender's secret travels only over TLS (or QUIC), in the URL or in a header alike (review WP-05
/// #5: a header is as readable on the wire as a query). A `url` or `ping_url` that is plain (`http://`, `udp://`) and
/// carries a secret to it (a `${...}` in that URL, or the path's header key, `token_env` / `jito_auth_env`, which every
/// request and keep-alive carries) is refused, unless `no_tls_endpoint` says the provider has none (the exception is
/// recorded where `cleartext_exception` is read: `arbx check`, run.log, meta.json). An exception on a path that needs
/// none is refused too (a stale claim hides the next mistake). A URL that is wholly `${...}` has no scheme until it is
/// expanded: `Path::new` checks it then. Ok(Some(note)): the exception taken
pub fn cleartext_check(s: &SendPath) -> Result<Option<String>> {
    let headers: Vec<String> = [("token_env", &s.token_env), ("jito_auth_env", &s.jito_auth_env)].into_iter()
        .filter_map(|(k, v)| v.as_ref().map(|v| format!("{v} ({k}, a header)"))).collect();
    let plain: Vec<(&str, String, Vec<String>)> = [("url", Some(s.url.as_str())), ("ping_url", s.ping_url.as_deref())].into_iter()
        .filter_map(|(k, u)| u.map(|u| (k, u)))
        .filter(|(_, u)| cleartext_scheme(u))
        .map(|(k, u)| {
            let scheme = u.trim_start().split("://").next().unwrap_or("").to_ascii_lowercase();
            (k, format!("{scheme}://"), env_vars(u).into_iter().map(|v| format!("${{{v}}}")).chain(headers.iter().cloned()).collect::<Vec<_>>())
        })
        .filter(|(_, _, secrets)| !secrets.is_empty()).collect();
    let why = s.no_tls_endpoint.as_deref().map(str::trim).filter(|w| !w.is_empty());
    let what = plain.iter().map(|x| x.0).collect::<Vec<_>>().join(" and ");
    let mut seen = std::collections::HashSet::new();
    let secrets: Vec<String> = plain.iter().flat_map(|x| x.2.iter().cloned()).filter(|x| seen.insert(x.clone())).collect();
    match (plain.is_empty(), why) {
        (true, None) => Ok(None),
        (true, Some(_)) => bail!("send path {}: no_tls_endpoint is set but no plain (http://, udp://) URL carries a secret (remove the stale exception)", s.name),
        (false, Some(w)) => Ok(Some(format!("send path {}: {what} carries {} over plain {}: allowed, the provider has no TLS endpoint ({w})", s.name, secrets.join(", "),
            plain[0].1))),
        (false, None) => bail!("send path {}: {what} is plain {} and carries a secret ({}): use the provider's https:// endpoint (PLAN-ADDENDUM I-10), or, if it has none, \
            say so with no_tls_endpoint = \"<evidence>\"", s.name, plain[0].1, secrets.join(", ")),
    }
}

/// `v` with every object's keys in sorted order (whatever map type serde_json was built with)
pub fn sorted(v: serde_json::Value) -> serde_json::Value {
    use serde_json::Value;
    match v {
        Value::Object(m) => {
            let mut kv: Vec<(String, Value)> = m.into_iter().collect();
            kv.sort_by(|a, b| a.0.cmp(&b.0));
            Value::Object(kv.into_iter().map(|(k, v)| (k, sorted(v))).collect())
        }
        Value::Array(a) => Value::Array(a.into_iter().map(sorted).collect()),
        x => x,
    }
}

/// expand `${NAME}` from the environment; None if a variable is missing or empty
pub fn expand(s: &str) -> Option<String> {
    let mut out = String::new();
    let mut rest = s;
    while let Some(i) = rest.find("${") {
        out.push_str(&rest[..i]);
        let j = rest[i..].find('}')? + i;
        let v = std::env::var(&rest[i + 2..j]).ok().filter(|v| !v.trim().is_empty())?;
        out.push_str(v.trim().trim_matches('"').trim_matches('\''));
        rest = &rest[j + 1..];
    }
    out.push_str(rest);
    Some(out)
}

pub fn env_token(var: &Option<String>, what: &str) -> Result<Option<String>> {
    match var {
        None => Ok(None),
        Some(v) => match std::env::var(v) {
            Ok(x) if !x.trim().is_empty() => Ok(Some(x.trim().to_string())),
            _ => bail!("{what}: environment variable {v} is empty or missing (set it in .env)"),
        },
    }
}

impl Feed {
    pub fn token(&self) -> Result<Option<String>> { env_token(&self.token_env, &self.name) }
    pub fn is_raw(&self) -> bool { matches!(self.kind, FeedKind::Udp | FeedKind::Multicast) }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn repo(rel: &str) -> std::path::PathBuf { Path::new(env!("CARGO_MANIFEST_DIR")).join(rel) }
    /// the file a /root/arbx/... path on Cherry names, in this checkout
    fn in_repo(cherry: &str) -> std::path::PathBuf { repo(cherry.strip_prefix("/root/arbx/").expect("a path in the arbx tree")) }

    const DAMM_V2: &str = "cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG";

    /// WP-00 acceptance: `arbx check --config deploy/arbx-stage0.toml` lists only jito-bundle as enabled, and the day-0
    /// switches are what PLAN.md WP-00 says
    #[test]
    fn stage0_config_is_the_day0_safety_switch() {
        let cfg = Config::load(&repo("deploy/arbx-stage0.toml")).unwrap();
        // review F1: it ships in shadow, so both field-acceptance shadow runs need no edit; the owner flips it to live
        // after they pass
        assert_eq!(cfg.mode, "shadow");
        let on: Vec<&str> = cfg.sends.iter().filter(|s| s.enabled).map(|s| s.name.as_str()).collect();
        assert_eq!(on, ["jito-bundle"], "bundle-only");
        let j = cfg.sends.iter().find(|s| s.name == "jito-bundle").unwrap();
        assert_eq!(j.kind, SendKind::JitoBundle);
        assert_eq!((j.tip_share, j.tip_max_lamports, j.max_per_sec), (Some(0.7), Some(100_000), Some(5)));
        // review F2: a 10 ms queue only delayed sends (it reordered none in the legacy replay); WP-05 brings the queue
        assert_eq!(j.queue_ms, 0, "the budget refuses at once, as in arb-lab");
        for name in ["helius", "rpcfast", "jito-tx", "haan", "astralane", "bolt", "tpu-direct", "everstake", "nozomi", "blockrazor", "flashblock",
            "nextblock", "jupiter", "landx-fra3", "landx-fra1", "speedlanding"] {
            assert!(cfg.sends.iter().any(|s| s.name == name && !s.enabled), "{name} is listed and disabled");
        }
        let (st, l, sp) = (&cfg.strategy, &cfg.live, &cfg.send_policy);
        assert!(st.skip_failing_signers && st.state_triggers);
        assert_eq!((l.max_new_token_accounts, l.max_size_sol), (0, 4.2));
        // WP-05: the send policy (bundle-only is enforced at load for a live config: `live_configs_are_bundle_only`)
        assert_eq!((sp.big_band_max_per_sec, sp.queue_ms, sp.max_blockhash_age_slots, sp.blockhash_commitment.as_str(), sp.inflight_hold_slots), (0.5, 10, 20, "confirmed", 2));
        assert_eq!(sp.crowded_skip_min_expected_lamports, 100_000, "OD-3's alternative on top of the rank (review F2), kept by WP-05");
        assert_eq!((sp.margin_floor, sp.margin_share, sp.skip_leader_kinds.clone()), (1, 0.0, vec!["other".to_string(), "unknown".to_string()]), "F23: today's on-chain floor");
        assert!(!sp.direct_experiment);
        assert!(cfg.record.archive_feeds.is_empty(), "no raw entries archive until an entries feed is alive");
        assert_eq!((cfg.record.disk_budget_gb, cfg.record.min_free_gb, cfg.record.flush_ms, cfg.runtime.bg_threads), (40.0, 25.0, 1_000, 3));
        // the stage-0 file is bundle-only as it ships, so flipping it to live loads
        let live = std::fs::read_to_string(repo("deploy/arbx-stage0.toml")).unwrap().replacen("mode = \"shadow\"", "mode = \"live\"", 1);
        assert_eq!(Config::parse(&live).unwrap().mode, "live");
        // both deshred feeds now ask for DAMM v2 too
        let deshred: Vec<&Feed> = cfg.feeds.iter().filter(|f| f.kind == FeedKind::YellowstoneDeshred).collect();
        assert_eq!(deshred.len(), 2);
        for f in deshred { assert!(f.account_include.iter().any(|a| a == DAMM_V2), "{}", f.name); }
        // repointed to the arbx tree; the data files it names are in this repo
        assert_eq!(cfg.out_dir, "/root/arbx/runs");
        for f in [cfg.pools.seed_csv.as_str(), cfg.pools.registry_json.as_deref().unwrap(), cfg.pools.templates_json.as_deref().unwrap(), sp.crowded_pools_file.as_str()] {
            assert!(f.starts_with("/root/arbx/data/"), "{f}");
            assert!(in_repo(f).is_file(), "{f} is in arbx/data");
        }
        assert!(st.signer_stats_file.starts_with("/root/arbx/"));
    }

    /// review F3 (PLAN §7: every WP updates both maintained configs): each one prices something (committed state is the
    /// only pricing path since WP-04)
    #[test]
    fn maintained_configs_have_a_pricing_path() {
        for f in ["deploy/arbx-stage0.toml", "deploy/arb.toml"] {
            let cfg = Config::load(&repo(f)).unwrap();
            assert!(cfg.strategy.state_triggers, "{f} prices nothing");
            assert!(cfg.pricing_warning().is_none(), "{f}");
        }
        assert!(Config::parse(MINIMAL).unwrap().pricing_warning().is_some(), "the defaults price nothing: warned");
    }

    #[test]
    fn arb_toml_jito_tip_matches_live() {
        let cfg = Config::load(&repo("deploy/arb.toml")).unwrap();
        let j = cfg.sends.iter().find(|s| s.kind == SendKind::JitoBundle).unwrap();
        assert_eq!((j.tip_share, j.tip_max_lamports), (Some(0.7), Some(100_000)), "R §3.6: no drift from the live config");
    }

    const MINIMAL: &str = "config_version = 2\nout_dir = \"/tmp/x\"\nwallet = \"w\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n[state]\nurl = \"http://localhost\"\n";

    fn err(text: &str) -> String { format!("{:#}", Config::parse(text).err().expect("refused")) }

    /// PLAN WP-01 acceptance: a misspelled key fails to load, with the key's name in the error, in every section
    /// (res-code §2: unknown keys were silently ignored)
    #[test]
    fn unknown_keys_are_load_errors() {
        assert!(Config::parse(MINIMAL).is_ok());
        for (section, typo) in [("", "out_dirr = \"/tmp\""), ("[live]", "max_failed_fee_lamports = 1"), ("[strategy]", "decoded_send = true"),
            ("[exec]", "expected_program_sha = \"x\""), ("[sim]", "enable = true"), ("[canary]", "enabled_ = true"), ("[record]", "rotate_mbb = 1"), ("[runtime]", "bg_thread = 1"),
            ("[send_policy]", "queue = 1"), ("[dry_run]", "simulates = true"), ("[control]", "sockets = false"), ("[[feed]]\nname = \"f\"\nkind = \"udp\"\nbind = \"0.0.0.0:1\"", "binds = \"x\""),
            ("[[send]]\nname = \"s\"\nkind = \"rpc\"\nurl = \"http://x\"", "max_per_second = 1"),
            ("[[rpc.endpoint]]\nname = \"r\"\nurl = \"http://x\"", "url_envv = \"X\"")] {
            let key = typo.split(' ').next().unwrap();
            let text = if section.is_empty() { MINIMAL.replacen("wallet", &format!("{typo}\nwallet"), 1) } else { format!("{MINIMAL}{section}\n{typo}\n") };
            let e = err(&text);
            assert!(e.contains(&format!("unknown field `{key}`")), "{section} {key}: {e}");
        }
        // [pools] and [state] (required sections) too
        assert!(err(&MINIMAL.replace("seed_csv", "registry_al = true\nseed_csv")).contains("unknown field `registry_al`"));
        assert!(err(&MINIMAL.replace("url = \"http://localhost\"", "url = \"http://localhost\"\ntoken = \"X\"")).contains("unknown field `token`"));
    }

    /// PLAN WP-01 acceptance: config_version = 2 is required; 1 (or none: an arb-lab file) fails
    #[test]
    fn config_version_2_is_required() {
        assert!(err(&MINIMAL.replace("config_version = 2", "config_version = 1")).contains("config_version 1 is not supported"));
        assert!(err(&MINIMAL.replace("config_version = 2\n", "")).contains("config_version = 2 is required"));
        assert!(err(&MINIMAL.replace("config_version = 2", "config_version = \"2\"")).contains("not supported"));
        assert_eq!(Config::parse(MINIMAL).unwrap().config_version, Some(CONFIG_VERSION));
        // F19: the arb-lab record stays as it was and is not loadable
        let e = format!("{:#}", Config::load(&repo("deploy/legacy/arb-w-live.toml")).err().unwrap());
        assert!(e.contains("config_version = 2 is required"), "{e}");
        assert!(!repo("deploy/arb-w-live.toml").exists(), "moved to deploy/legacy/");
        // the maintained configs are v2 and parse with every key known
        for f in ["deploy/arbx-stage0.toml", "deploy/arb.toml"] { assert_eq!(Config::load(&repo(f)).unwrap().config_version, Some(2), "{f}"); }
    }

    /// `normalized_json`: defaults filled, keys sorted, comments and formatting ignored; a changed value changes it
    #[test]
    fn normalized_hash_ignores_comments_and_order() {
        let a = Config::parse(&format!("{MINIMAL}[live]\nmax_size_sol = 0.5\nmax_new_token_accounts = 3\n")).unwrap();
        let b = Config::parse(&format!("# a comment\n{}[live]\nmax_new_token_accounts   =   3 # inline\nmax_size_sol = 0.50\n", MINIMAL.replace("wallet = \"w\"\n", "")
            .replace("out_dir", "wallet = \"w\"\nout_dir"))).unwrap();
        assert_eq!(a.normalized_json(), b.normalized_json());
        assert_eq!(a.normalized_sha256(), b.normalized_sha256());
        let c = Config::parse(&format!("{MINIMAL}[live]\nmax_size_sol = 0.6\nmax_new_token_accounts = 3\n")).unwrap();
        assert_ne!(a.normalized_sha256(), c.normalized_sha256());
        // a default written out explicitly is the same config
        let d = Config::parse(&format!("{MINIMAL}[live]\nmax_size_sol = 0.5\nmax_new_token_accounts = 3\nmargin_lamports = 1000\n")).unwrap();
        assert_eq!(a.normalized_sha256(), d.normalized_sha256());
        let v: serde_json::Value = serde_json::from_str(&a.normalized_json()).unwrap();
        assert_eq!((v["config_version"].as_u64(), v["live"]["max_new_token_accounts"].as_u64(), v["control"]["socket"].as_bool()), (Some(2), Some(3), Some(true)));
        let keys: Vec<&String> = v.as_object().unwrap().keys().collect();
        let mut sorted_keys = keys.clone();
        sorted_keys.sort();
        assert_eq!(keys, sorted_keys);
        assert!(a.normalized_json().find("\"canary\"").unwrap() < a.normalized_json().find("\"wallet\"").unwrap(), "sorted in the text");
    }

    /// `[exec] expected_program_*` must be hex of the right length (a typo would make every live run shadow)
    #[test]
    fn expected_program_hashes_are_checked() {
        assert!(Config::parse(&format!("{MINIMAL}[exec]\nexpected_program_md5 = \"809315befcb9554211f8019bf9df290b\"\n")).is_ok());
        assert!(err(&format!("{MINIMAL}[exec]\nexpected_program_md5 = \"809315be\"\n")).contains("expected_program_md5"));
        assert!(err(&format!("{MINIMAL}[exec]\nexpected_program_sha256 = \"{}\"\n", "E".repeat(64))).contains("lowercase hex"));
    }

    /// WP-02: recording cannot be turned off (`[record] enabled` and `archive_feed` are gone: a config that still has
    /// them does not load); the new keys have the plan's defaults and are checked
    #[test]
    fn record_and_runtime_keys() {
        let c = Config::parse(MINIMAL).unwrap();
        let r = &c.record;
        assert_eq!((r.disk_budget_gb, r.min_free_gb, r.rotate_mb, r.rotate_min, r.flush_ms, r.zstd_level), (40.0, 25.0, 256.0, 60, 1_000, 3));
        assert_eq!((r.queue_core, r.queue_accounts, r.queue_journal, r.queue_chain, r.queue_bulk), (262_144, 1_048_576, 524_288, 262_144, 131_072));
        assert_eq!((r.accounts_keyframe_every, c.runtime.bg_threads), (64, 3));
        assert!(r.archive_feeds.is_empty() && r.writer_cpus.is_empty());
        for k in ["enabled = true", "archive_feed = \"\""] {
            let key = k.split(' ').next().unwrap();
            assert!(err(&format!("{MINIMAL}[record]\n{k}\n")).contains(&format!("unknown field `{key}`")), "{k}");
        }
        let feeds = "[[feed]]\nname = \"ent\"\nkind = \"jito-entries\"\nurl = \"http://x\"\n[[feed]]\nname = \"raw\"\nkind = \"udp\"\nbind = \"0.0.0.0:1\"\n";
        assert_eq!(Config::parse(&format!("{MINIMAL}{feeds}[record]\narchive_feeds = [\"ent\"]\n")).unwrap().record.archive_feeds, ["ent"]);
        assert!(err(&format!("{MINIMAL}{feeds}[record]\narchive_feeds = [\"nope\"]\n")).contains("no [[feed]] named nope"));
        assert!(err(&format!("{MINIMAL}{feeds}[record]\narchive_feeds = [\"raw\"]\n")).contains("raw shred feed"));
        assert_eq!(r.queue_max_mb, 1_024.0);
        for bad in ["zstd_level = 0", "flush_ms = 0", "rotate_mb = 0", "queue_core = 0", "disk_budget_gb = -1", "accounts_keyframe_every = 0",
            "disk_budget_gb = 0", "queue_max_mb = 0", "min_free_gb = -1", "writer_cpus = [1024]"] {
            assert!(Config::parse(&format!("{MINIMAL}[record]\n{bad}\n")).is_err(), "{bad}");
        }
        assert!(err(&format!("{MINIMAL}[runtime]\nbg_threads = 0\n")).contains("bg_threads"));
        // integers where the defaults are numbers with a fraction
        assert_eq!(Config::parse(&format!("{MINIMAL}[record]\nrotate_mb = 1\ndisk_budget_gb = 2\n")).unwrap().record.rotate_mb, 1.0);
        assert_eq!(Config::parse(&format!("{MINIMAL}[record]\nmin_free_gb = 0\nwriter_cpus = [2, 3]\n")).unwrap().record.writer_cpus, [2, 3]);
    }

    /// WP-03: the state stream's keys, the transaction streams (feeds after the [[feed]] list, url and token from the
    /// state stream's, the include tokens expanded once the registry is known, the provider's limit enforced) and
    /// [leaders]
    #[test]
    fn wp03_state_keys_and_tx_streams() {
        let c = Config::parse(MINIMAL).unwrap();
        let st = &c.state;
        assert!(st.watch_clock && st.watch_programdata && st.watch_wallet && st.tx_streams.is_empty());
        assert_eq!((st.slot_statuses.as_str(), st.block_meta.as_str(), c.leaders.refresh_min), ("auto", "auto", 60));
        let stage0 = Config::load(&repo("deploy/arbx-stage0.toml")).unwrap();
        let tx = &stage0.state.tx_streams;
        assert_eq!((tx.len(), tx[0].name.as_str(), tx[0].max_accounts, tx[0].failed), (1, "haan-grpc", Some(1), true));
        assert!(!stage0.feeds.iter().any(|f| f.kind == FeedKind::YellowstoneTx), "the PumpSwap stream moved to [[state.tx_stream]]");
        let mut f = stage0.state.tx_stream_feeds();
        assert_eq!((f[0].kind.clone(), f[0].url.as_deref(), f[0].token_env.as_deref(), f[0].failed), (FeedKind::YellowstoneTx, Some(stage0.state.url.as_str()),
            Some("HAAN_X_TOKEN"), None));
        // its feed id is the one the [[feed]] had: it was the last feed, and the streams follow the list
        assert_eq!(stage0.feeds.len() + 1, 10);
        expand_includes(&mut f, &["W1".into()], &["V1".into()]).unwrap();
        let ok = |extra: &str| Config::parse(&format!("{MINIMAL}{extra}"));
        let txs = |inc: &str, max: &str| format!("[[state.tx_stream]]\nname = \"t\"\naccount_include = {inc}\n{max}");
        let mut feeds = ok(&txs("[\"@watched_writable\", \"@venue_programs\"]", "")).unwrap().state.tx_stream_feeds();
        expand_includes(&mut feeds, &["W1".into(), "W2".into()], &["V1".into(), "W1".into()]).unwrap();
        assert_eq!(feeds[0].account_include, ["W1", "W2", "V1"], "expanded, without duplicates");
        let mut feeds = ok(&txs("[\"@watched_writable\"]", "max_accounts = 1")).unwrap().state.tx_stream_feeds();
        assert!(expand_includes(&mut feeds, &["W1".into(), "W2".into()], &[]).unwrap_err().to_string().contains("more than its max_accounts 1"));
        for (bad, why) in [(txs("[\"nope\"]", ""), "neither a base58 key"), (txs("[]", ""), "is empty"),
            (txs("[\"pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA\", \"CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C\"]", "max_accounts = 1"), "over max_accounts"),
            ("[state]\nslot_statuses = \"some\"\n".to_string(), "slot_statuses"), ("[leaders]\nrefresh_min = 0\n".to_string(), "refresh_min"),
            // review WP-03 N8: a [[feed]]'s literal list, at load
            ("[[feed]]\nname = \"g\"\nkind = \"yellowstone-tx\"\nurl = \"http://localhost\"\naccount_include = [\"A\", \"B\"]\nmax_accounts = 1\n".to_string(), "over max_accounts 1")] {
            let text = if bad.starts_with("[state]") { MINIMAL.replace("[state]\n", &bad) } else { format!("{MINIMAL}{bad}") };
            let e = Config::parse(&text).map(|_| ()).unwrap_err().to_string();
            assert!(e.contains(why), "{why}: {e}");
        }
        // a stream named like a feed is refused (feed names are shared)
        let mut stage = std::fs::read_to_string(repo("deploy/arbx-stage0.toml")).unwrap();
        stage = stage.replace("name = \"haan-grpc\"", "name = \"haan-deshred\"");
        assert!(Config::parse(&stage).unwrap_err().to_string().contains("the name is taken"));
    }

    /// WP-08: [leaders] rtt_probe, rtt_per_sec, geo_table (defaults; the maintained configs; a rate outside (0, 20]) and
    /// [record] rivals_venues_sample
    #[test]
    fn wp08_leaders_keys() {
        let c = Config::parse(MINIMAL).unwrap();
        assert_eq!((c.leaders.rtt_probe, c.leaders.rtt_per_sec, c.leaders.geo_table.as_str()), (true, 2.0, "data/ip-geo.csv"));
        let stage0 = Config::load(&repo("deploy/arbx-stage0.toml")).unwrap();
        assert_eq!((stage0.leaders.rtt_probe, stage0.leaders.rtt_per_sec, stage0.leaders.geo_table.as_str()), (true, 2.0, "/root/arbx/data/ip-geo.csv"));
        let off = Config::parse(&format!("{MINIMAL}[leaders]\nrtt_probe = false\nrtt_per_sec = 0.5\ngeo_table = \"g.csv\"\n")).unwrap();
        assert_eq!((off.leaders.rtt_probe, off.leaders.rtt_per_sec, off.leaders.geo_table.as_str()), (false, 0.5, "g.csv"));
        for bad in ["rtt_per_sec = 0", "rtt_per_sec = -1.0", "rtt_per_sec = 21", "rtt_per_sec = nan"] {
            let e = Config::parse(&format!("{MINIMAL}[leaders]\n{bad}\n")).map(|_| ()).unwrap_err().to_string();
            assert!(e.contains("rtt_per_sec"), "{bad}: {e}");
        }
        // plan addendum I-9: [record] rivals_venues_sample, 1 in 10 by default and in both maintained configs; 1 keeps all
        assert_eq!((c.record.rivals_venues_sample, stage0.record.rivals_venues_sample, Config::load(&repo("deploy/arb.toml")).unwrap().record.rivals_venues_sample), (10, 10, 10));
        assert_eq!(Config::parse(&format!("{MINIMAL}[record]\nrivals_venues_sample = 1\n")).unwrap().record.rivals_venues_sample, 1);
        let e = Config::parse(&format!("{MINIMAL}[record]\nrivals_venues_sample = 0\n")).map(|_| ()).unwrap_err().to_string();
        assert!(e.contains("rivals_venues_sample"), "{e}");
    }

    /// WP-00's keys, moved to `[send_policy]` by WP-05 (the big band is the band table's bands 3-4 now: no
    /// `big_band_min_expected_lamports`)
    #[test]
    fn wp00_keys_default_safe() {
        let cfg = Config::parse(MINIMAL).unwrap();
        assert_eq!(cfg.send_policy.big_band_max_per_sec, 0.5);
        assert!(cfg.send_policy.crowded_pools_file.is_empty());
        let pol = |k: &str| Config::parse(&format!("{MINIMAL}[send_policy]\n{k}\n"));
        assert!(pol("big_band_max_per_sec = -1.0").is_err());
        assert!(pol("big_band_max_per_sec = 0").is_ok(), "0 = no big-band trade");
        assert_eq!(cfg.send_policy.crowded_skip_min_expected_lamports, 0, "OD-3 default: rank only");
        // review N1: a positive rate the bucket would round to "never"
        assert!(pol("big_band_max_per_sec = 0.0004").is_err());
        assert!(pol("big_band_max_per_sec = 0.001").is_ok());
        // the WP-00 keys are no longer in [live]: a config that still has them does not load
        for k in ["big_band_max_per_sec = 0.5", "big_band_min_expected_lamports = 1", "crowded_pools_file = \"\"", "crowded_skip_min_expected_lamports = 1"] {
            let key = k.split(' ').next().unwrap();
            assert!(err(&format!("{MINIMAL}[live]\n{k}\n")).contains(&format!("unknown field `{key}`")), "{k}");
        }
    }

    /// PLAN WP-05 config keys: `[send_policy]` with the plan's defaults and checks; the removed keys (`[gate]`, the direct
    /// arm's `[live]` keys, `nonce_accounts`, the canary's nonce and settle) refuse to load; `direct_experiment = true` is
    /// refused in Stage 0; a canary is at most 0.2 SOL
    #[test]
    fn wp05_send_policy_keys() {
        let c = Config::parse(MINIMAL).unwrap();
        let sp = &c.send_policy;
        assert_eq!((sp.max_blockhash_age_slots, sp.blockhash_commitment.as_str(), sp.queue_ms, sp.big_band_max_per_sec, sp.crowding_window_h, sp.crowding_buckets.clone()),
            (20, "confirmed", 10, 0.5, 6, vec![20, 150]));
        assert_eq!((sp.margin_floor, sp.margin_share, sp.inflight_hold_slots, sp.skip_leader_kinds.clone(), sp.direct_experiment),
            (1, 0.0, 2, vec!["other".to_string(), "unknown".to_string()], false));
        assert!(!c.dry_run.simulate && c.dry_run.max_sim_per_sec == 2);
        let pol = |k: &str| Config::parse(&format!("{MINIMAL}[send_policy]\n{k}\n")).map(|_| ()).map_err(|e| format!("{e:#}"));
        assert!(pol("direct_experiment = true").unwrap_err().contains("refused in Stage 0"));
        assert!(pol("blockhash_commitment = \"finalized\"").is_err());
        assert!(pol("blockhash_commitment = \"processed\"").is_ok());
        assert!(pol("max_blockhash_age_slots = 151").is_err() && pol("max_blockhash_age_slots = 0").is_err());
        assert!(pol("crowding_buckets = [150, 20]").is_err() && pol("crowding_buckets = [20]").is_err());
        assert!(pol("margin_floor = 0").is_err(), "a landed bundle clears at least 1 lamport");
        assert!(pol("margin_share = 1.5").is_err() && pol("margin_share = 0.02").is_ok());
        assert!(pol("skip_leader_kinds = [\"bam\"]").is_ok() && pol("skip_leader_kinds = [\"leader\"]").is_err());
        assert!(pol("inflight_hold_slots = 0").is_err());
        assert!(Config::parse(&format!("{MINIMAL}[send_policy.direct]\nnonce_accounts = [\"x\"]\n")).is_ok(), "kept for the experiment");
        // removed keys
        for (section, k) in [("[live]", "test_all_paths = true"), ("[live]", "max_priority_lamports = 1"), ("[live]", "bid_tiers = true"), ("[live]", "bid_share = 0.5"),
            ("[live]", "spec_cu_price_micro = 1"), ("[live]", "rotate_paths = true"), ("[live]", "race_mix = true"), ("[live]", "bundle_mix = true"),
            ("[live]", "tpu_cu_price_micro = 1"), ("[live]", "tpu_max_expected_lamports = 1"), ("[live]", "pair_lock_ms = 1"), ("[live]", "sim_gate = true"),
            ("[live]", "bundle_resend_ms = [1]"), ("[live]", "bundle_size_variants = [0.5]"), ("[live]", "compete_mult = 1.0"), ("[live]", "gross_floor = true"),
            ("[live]", "nonce_accounts = []"), ("[live]", "settle_s = 3"), ("[canary]", "nonce_account = \"x\""), ("[canary]", "settle_s = 3")] {
            let key = k.split(' ').next().unwrap();
            assert!(err(&format!("{MINIMAL}{section}\n{k}\n")).contains(&format!("unknown field `{key}`")), "{section} {k}");
        }
        assert!(err(&format!("{MINIMAL}[gate]\nenabled = false\n")).contains("unknown field `gate`"), "the Jito gate is gone");
        assert!(err(&format!("{MINIMAL}[canary]\nsize_sol = 0.25\n")).contains("0.2"));
        assert!(Config::parse(&format!("{MINIMAL}[canary]\nsize_sol = 0.2\n")).is_ok());
        assert!(err(&format!("{MINIMAL}[[send]]\nname = \"j\"\nkind = \"jito-bundle\"\nurl = \"https://x\"\ntip_lamports = 1000\nmax_per_sec = 5\nqueue_ms = 10\n"))
            .contains("[send_policy] queue_ms"));
    }

    /// WP-07: the ledger's and the equity stops' keys: their defaults (OD-11: 0.02 SOL a rolling hour; no test budget until
    /// one is set), the frz canary's values, and every refusal (a budget over the owner's hard cap, auto_unwrap in Stage 0,
    /// a share outside 0..1, a mint that is not one)
    #[test]
    fn wp07_ledger_and_supervisor_keys() {
        let c = Config::parse(MINIMAL).unwrap();
        let (lg, sv) = (&c.ledger, &c.supervisor);
        assert_eq!((lg.snapshot_min, lg.tolerance_lamports, lg.mid_source.as_str(), lg.snapshot_retries, lg.snapshot_retry_s, lg.recon_grace_s, lg.token_haircut),
            (10, 10_000, "pools", 3, 30, 60, 0.10), "review WP-07 #3: a snapshot every 10 minutes inside a segment");
        assert_eq!((lg.max_view_age_s, lg.stale_after_failures, lg.max_record_wait_s), (600, 3, 120), "the money view's freshness");
        assert_eq!(lg.extra_mints.len(), 2, "USDC and USDT");
        assert_eq!((sv.max_drop_per_hour_sol, sv.max_drop_per_day_sol, sv.test_budget_lamports, sv.token_floor_tolerance, sv.rent_cap_sol, sv.native_floor_sol, sv.auto_unwrap),
            (0.02, 0.15, 0, 0.001, 0.1, 0.02, false));
        assert_eq!((c.live.bankroll_share, c.live.bankroll_reserve_sol), (0.0, 0.0), "the bankroll cap is off unless set");
        let frz = Config::parse(&std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/deploy/arbx-canary-frz.toml")).unwrap()).unwrap();
        assert_eq!((frz.supervisor.test_budget_lamports, frz.live.bankroll_share, frz.live.bankroll_reserve_sol, frz.live.max_new_token_accounts, frz.canary.size_sol),
            (5_000_000, 0.85, 0.03, 0, 0.2), "review WP-07 #5: one run's allotment (FT-004's), never the whole hard cap");
        assert_eq!((frz.ledger.snapshot_min, frz.ledger.max_view_age_s), (10, 600));
        let e = |section: &str, k: &str| err(&format!("{MINIMAL}[{section}]\n{k}\n"));
        assert!(e("supervisor", "test_budget_lamports = 34000001").contains("hard cap"));
        assert!(Config::parse(&format!("{MINIMAL}[supervisor]\ntest_budget_lamports = 34000000\n")).is_ok());
        assert!(e("supervisor", "auto_unwrap = true").contains("owner decision"));
        assert!(e("supervisor", "max_drop_per_hour_sol = 0").contains("positive"));
        assert!(e("supervisor", "token_floor_tolerance = 0.5").contains("0..0.1"));
        assert!(e("supervisor", "stranded_s = 0").contains("> 0"));
        assert!(e("supervisor", "hour_drop_sol = 0.05").contains("unknown field `hour_drop_sol`"), "the key is max_drop_per_hour_sol");
        assert!(e("live", "bankroll_share = 1.5").contains("0..1"));
        assert!(e("live", "bankroll_reserve_sol = -0.1").contains(">= 0"));
        assert!(e("ledger", "mid_source = \"oracle\"").contains("pools"));
        assert!(e("ledger", "tolerance_lamports = 0").contains("> 0"));
        assert!(e("ledger", "token_haircut = 1.0").contains("0..1"));
        assert!(e("ledger", "extra_mints = [\"USDC\"]").contains("base58 mint"));
        assert!(e("ledger", "snapshot_min = 0").contains("1..1440"));
        assert!(e("ledger", "snapshot_min = 60").contains("max_view_age_s (600) must be at least snapshot_min"), "the view would go stale between snapshots");
        assert!(Config::parse(&format!("{MINIMAL}[ledger]\nsnapshot_min = 60\nmax_view_age_s = 3600\n")).is_ok());
        assert!(e("ledger", "stale_after_failures = 0").contains(">= 1"));
        assert!(e("ledger", "max_record_wait_s = 5").contains(">= 10"));
    }

    const JITO: &str = "[[send]]\nname = \"jito-bundle\"\nkind = \"jito-bundle\"\nurl = \"https://frankfurt.mainnet.block-engine.jito.wtf\"\ntip_lamports = 1000\n";

    /// PLAN WP-05 acceptance: a live config with a non-bundle path enabled fails to load (and one without an enabled bundle
    /// path); a shadow config may keep other paths enabled (keep-alive measurement), and disabled ones stay listed
    #[test]
    fn live_configs_are_bundle_only() {
        let live = MINIMAL.replace("out_dir", "mode = \"live\"\nout_dir");
        assert!(Config::parse(&format!("{live}{JITO}")).is_ok());
        let helius = "[[send]]\nname = \"helius\"\nkind = \"helius\"\nurl = \"https://fra-sender.helius-rpc.com/fast\"\ntip_lamports = 5000\n";
        let e = err(&format!("{live}{JITO}{helius}"));
        assert!(e.contains("only jito-bundle send paths may be enabled") && e.contains("helius (Helius)"), "{e}");
        assert!(Config::parse(&format!("{live}{JITO}{}", helius.replace("tip_lamports", "enabled = false\ntip_lamports"))).is_ok(), "listed, disabled: fine");
        assert!(err(&live).contains("no jito-bundle send path is enabled"));
        assert!(Config::parse(&format!("{MINIMAL}{JITO}{helius}")).is_ok(), "shadow: other paths may run their keep-alives");
        assert!(bundle_only(&Config::parse(&format!("{MINIMAL}{JITO}{helius}")).unwrap().sends).is_err(), "a canary / live run checks the same");
    }

    /// PLAN-ADDENDUM I-10: an enabled path whose http:// URL carries a `${...}` secret is refused at load, unless
    /// `no_tls_endpoint` records that the provider has none (the note names it); https, a secret-free http URL, a header
    /// key and a disabled path are fine; a stale exception is refused
    #[test]
    fn cleartext_secrets_are_refused() {
        let path = |url: &str, extra: &str| format!("{MINIMAL}[[send]]\nname = \"nozomi\"\nkind = \"nozomi\"\nurl = \"{url}\"\ntip_lamports = 1000000\n{extra}");
        let e = err(&path("http://fra2.nozomi.temporal.xyz/?c=${NOZOMI_KEY}", ""));
        assert!(e.contains("plain http://") && e.contains("${NOZOMI_KEY}") && e.contains("I-10"), "{e}");
        assert!(Config::parse(&path("https://fra.nozomi.temporal.xyz/?c=${NOZOMI_KEY}", "")).is_ok(), "TLS");
        assert!(Config::parse(&path("http://fra2.nozomi.temporal.xyz/?c=${NOZOMI_KEY}", "enabled = false\n")).is_ok(), "disabled: checked when it is enabled");
        let ok = Config::parse(&path("http://fra2.nozomi.temporal.xyz/?c=${NOZOMI_KEY}", "no_tls_endpoint = \"docs show http only (2026-10-04)\"\n")).unwrap();
        let note = cleartext_check(&ok.sends[0]).unwrap().unwrap();
        assert!(note.contains("no TLS endpoint") && note.contains("docs show http only") && note.contains("${NOZOMI_KEY}"), "{note}");
        assert!(err(&path("https://fra.nozomi.temporal.xyz/?c=${NOZOMI_KEY}", "no_tls_endpoint = \"x\"\n")).contains("stale exception"));
        // review WP-05 #5: a header key over plain http is clear text too (refused, or allowed with the exception
        // recorded); over https it is fine, and so is a plain-http URL without any secret
        let nodeone = |url: &str, extra: &str| format!("{MINIMAL}[[send]]\nname = \"n1\"\nkind = \"node-one\"\nurl = \"{url}\"\ntoken_env = \"NODEONE_KEY\"\ntip_lamports = 1000000\n{extra}");
        let e = err(&nodeone("http://fra.node1.me/v2", ""));
        assert!(e.contains("plain http://") && e.contains("NODEONE_KEY (token_env, a header)") && e.contains("I-10"), "{e}");
        let ok = Config::parse(&nodeone("http://fra.node1.me/v2", "no_tls_endpoint = \"node1.me lists http only (2026-10-05)\"\n")).unwrap();
        let note = cleartext_check(&ok.sends[0]).unwrap().unwrap();
        assert!(note.contains("NODEONE_KEY") && note.contains("no TLS endpoint") && note.contains("http only"), "{note}");
        assert!(Config::parse(&nodeone("https://fra.node1.me/v2", "")).is_ok(), "a header key over TLS");
        assert!(Config::parse(&nodeone("http://fra.node1.me/v2", "enabled = false\n")).is_ok(), "disabled");
        let e = err(&nodeone("https://fra.node1.me/v2", "ping_url = \"http://fra.node1.me/ping\"\n"));
        assert!(e.contains("ping_url") && e.contains("NODEONE_KEY"), "the keep-alive carries the header too: {e}");
        let haan = format!("{MINIMAL}[[send]]\nname = \"h\"\nkind = \"haan\"\nurl = \"http://sender.haandigital.eu/api/v1/transactions\"\njito_auth_env = \"JITO_UUID\"\n");
        assert!(err(&haan).contains("JITO_UUID (jito_auth_env, a header)"));
        let landx = format!("{MINIMAL}[[send]]\nname = \"lx\"\nkind = \"landx\"\nurl = \"udp://fra3.landx.dev:10000\"\ntoken_env = \"LANDX_KEY\"\ntip_lamports = 1000000\n");
        assert!(err(&landx).contains("plain udp://"), "a key at the head of every UDP packet");
        let helius = format!("{MINIMAL}[[send]]\nname = \"hl\"\nkind = \"helius\"\nurl = \"http://fra-sender.helius-rpc.com/fast\"\ntip_lamports = 5000\n");
        assert!(Config::parse(&helius).is_ok(), "plain http without a secret");
        assert!(err(&format!("{helius}no_tls_endpoint = \"x\"\n")).contains("stale exception"));
        assert!(cleartext_scheme("HTTP://x") && cleartext_scheme(" udp://x") && !cleartext_scheme("https://x") && !cleartext_scheme("${URL}"));
        // the keep-alive URL is checked too
        let e = err(&path("https://fra.nozomi.temporal.xyz/?c=${NOZOMI_KEY}", "ping_url = \"http://fra.nozomi.temporal.xyz/ping?c=${NOZOMI_KEY}\"\n"));
        assert!(e.contains("ping_url"), "{e}");
        assert_eq!(env_vars("http://x/${A}/y?k=${B_KEY}&z"), vec!["A".to_string(), "B_KEY".to_string()]);
        // the maintained configs pass (their enabled paths)
        for f in ["deploy/arbx-stage0.toml", "deploy/arb.toml"] {
            let cfg = Config::load(&repo(f)).unwrap();
            for s in cfg.sends.iter().filter(|s| s.enabled) { cleartext_check(s).unwrap(); }
        }
    }

    /// PLAN WP-04 config keys: the state consistency keys, [alts] and [accuracy] with the plan's defaults and checks; the
    /// removed keys (`strategy.confirm_trigger_ms`, `strategy.decoded_sends`: there is no decoded send path) refuse to load
    #[test]
    fn wp04_keys() {
        let c = Config::parse(MINIMAL).unwrap();
        let st = &c.state;
        assert_eq!((st.commit_timeout_ms, st.quiescence_ms, st.max_part_skew_slots, st.max_tip_lag_slots, st.clock_max_age_slots), (5, 3, 2, 2, 2));
        assert_eq!((st.lag_slo_p50_ms, st.lag_slo_p90_ms, st.lag_slo_breach_minutes, st.slo_action.as_str(), st.slo_recover_minutes), (16.0, 30.0, 5, "log", 10));
        assert_eq!((st.tier_a_grace_s, st.boot_timeout_s, st.max_update_age_ms, st.resnapshot), (60, 60, 2_000, true));
        assert_eq!((st.resync_warn_s, st.resync_give_up_s), (10, 300), "review WP-04 #1");
        assert_eq!((c.alts.retry_ms.clone(), c.alts.retry_every_s, c.alts.give_up_s, c.alts.wait_cap, c.alts.max_inflight, c.alts.preload.as_str()),
            (vec![50, 250, 1_000, 5_000], 30, 600, 10_000, 16, "auto"));
        assert_eq!((c.alts.preload_max_age_h, c.alts.preload_max_tables), (24, 5_000), "review WP-04 #11");
        assert_eq!((c.accuracy.action.as_str(), c.accuracy.ring_versions, c.accuracy.queue), ("log", 8, 10_000));
        for k in ["confirm_trigger_ms = 60", "decoded_sends = false"] {
            let key = k.split(' ').next().unwrap();
            assert!(err(&format!("{MINIMAL}[strategy]\n{k}\n")).contains(&format!("unknown field `{key}`")), "{k}");
        }
        for (bad, why) in [("[state]\nslo_action = \"halt\"\n", "slo_action"), ("[state]\nquiescence_ms = 0\n", "quiescence_ms"),
            ("[alts]\nretry_ms = [250, 50]\n", "retry_ms"), ("[alts]\nmax_inflight = 0\n", "max_inflight"), ("[accuracy]\naction = \"quarantine\"\n", "OD-8"),
            ("[accuracy]\nring_versions = 1\n", "ring_versions"), ("[state]\nresync_give_up_s = 0\n", "resync_give_up_s")] {
            let text = if bad.starts_with("[state]") { MINIMAL.replace("[state]\n", bad) } else { format!("{MINIMAL}{bad}") };
            let e = Config::parse(&text).map(|_| ()).unwrap_err().to_string();
            assert!(e.contains(why), "{why}: {e}");
        }
        let shadow = Config::parse(&MINIMAL.replace("[state]\n", "[state]\nslo_action = \"shadow\"\n")).unwrap();
        assert_eq!(shadow.state.slo_action, "shadow");
    }
}

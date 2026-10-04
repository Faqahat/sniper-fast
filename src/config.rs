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
    #[serde(default)]
    pub gate: GateCfg,
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

/// The long run's recorders (record.rs): rivals, executed results, arrivals per feed, pool moves, slots, raw entries.
#[derive(Debug, Clone, Deserialize, Serialize, Default)]
#[serde(deny_unknown_fields)]
pub struct RecordCfg {
    #[serde(default)]
    pub enabled: bool,
    /// the entries feed whose raw messages are archived (entries.zst); "" = none
    #[serde(default)]
    pub archive_feed: String,
}

/// STEP 4: real trades. Needs mode = "live" AND `arbx run --live`. Each copy's on-chain min_profit is base fee +
/// priority fee + that copy's tip + `margin_lamports`, so a landed trade cannot lose; what failures cost (their fees)
/// is capped by `max_failed_fees_lamports`, after which no trade is sent (the engine keeps recording).
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct LiveCfg {
    /// at most this much per trade, SOL (paid from the wallet's WSOL account)
    #[serde(default = "live_size")]
    pub max_size_sol: f64,
    /// stop sending once fees of landed transactions that failed reach this, lamports
    #[serde(default = "live_fee_cap")]
    pub max_failed_fees_lamports: u64,
    #[serde(default = "live_margin")]
    pub margin_lamports: u64,
    /// new token accounts a winning trade may create (rent, recoverable by closing them)
    #[serde(default = "live_atas")]
    pub max_new_token_accounts: u32,
    /// settle each trade this long after it is sent, seconds (its nonce is leased until then)
    #[serde(default = "live_settle")]
    pub settle_s: u64,
    /// durable nonce accounts (authority: the wallet), one per trade in flight; arbed's three by default
    #[serde(default = "live_nonces")]
    pub nonce_accounts: Vec<String>,
    /// TESTING LANDING, not profit (owner, 2026-10-03): every enabled path gets a copy on every trade, even when its tip
    /// (Bolt, Astralane: 0.001 SOL) is above the expected profit. Each copy's on-chain min_profit still includes its tip,
    /// so such a copy lands as a failed transaction (fee only) unless the trade really clears its tip.
    #[serde(default)]
    pub test_all_paths: bool,
    /// never more than this priority fee on one trade, lamports, whatever the expected profit says (arbed's
    /// PRIORITY_MAX_LAMPORTS): live-run-1 paid 1,104,138 on one trade whose expected profit was overstated
    #[serde(default = "live_prio_cap")]
    pub max_priority_lamports: u64,
    /// TWO-TIER BID (9EwQoN74's pattern, research log S-010): speculative copies at ZERO priority (a miss costs the 5,000
    /// base fee only), and only when the expected profit reaches `bid_min_expected_lamports` a priority fee of
    /// `bid_share` of it (at most `bid_max_priority_lamports`) to win the pool's next turn behind the trigger. Replaces
    /// the trigger-copy / flat rule and `max_priority_lamports` when on.
    #[serde(default)]
    pub bid_tiers: bool,
    #[serde(default = "bid_min")]
    pub bid_min_expected_lamports: u64,
    #[serde(default = "bid_share")]
    pub bid_share: f64,
    #[serde(default = "bid_max")]
    pub bid_max_priority_lamports: u64,
    /// the speculative (default) tier's compute-unit price, micro-lamports: 0 = none at all; 1 = about 0.2 lamports,
    /// enough for Helius Sender, which refuses a transaction without a CU price
    #[serde(default)]
    pub spec_cu_price_micro: u64,
    /// PATH ROTATION (measurement): each trade goes out through ONE path, the next in turn (the Jito bundle excluded: a
    /// failing bundle never lands), so every path gets its own landings timed on the leader clock
    #[serde(default)]
    pub rotate_paths: bool,
    /// the long run's 2x2: even trades put a copy on every path ("race", path data), odd ones only the copies whose tip
    /// the gap covers ("win"); and in pairs, the fee copies the trigger (0.95x) or is flat. Needs bid_tiers off.
    #[serde(default)]
    pub race_mix: bool,
    /// tonight's 2-arm test: even trades go on every TPU path (only copies whose tip the gap covers), odd trades as a
    /// Jito bundle only, with no priority fee (a bundle that would fail never lands: a miss costs nothing)
    #[serde(default)]
    pub bundle_mix: bool,
    /// the TPU arm's flat priority fee, µlamports/CU (0 = the fee rule)
    #[serde(default)]
    pub tpu_cu_price_micro: u64,
    /// one trade per pool pair within this many ms (was: until the trade settled, 8+ s)
    #[serde(default = "pair_lock")]
    pub pair_lock_ms: u64,
    /// simulate a TPU trade's own signed transaction before sending it (the chain's fees, clock and state, so a quote
    /// error never lands as a paid failure); the bundle arm needs none (Jito drops a bundle that would fail)
    #[serde(default)]
    pub sim_gate: bool,
    /// TPU copies only below this predicted profit (0 = no limit): long run 1's wins had a median 51k, the gaps fast
    /// bots took 438k, the mispriced ones 650k; above it the trade goes as a bundle only (a miss costs nothing)
    #[serde(default)]
    pub tpu_max_expected_lamports: u64,
    /// TPU copies never on pools from MriyaNN8's list (1 win in 335 sends there in long run 1): bundle only
    #[serde(default)]
    pub tpu_skip_mriya_pools: bool,
    /// TPU copies never for these tokens: bundle only (w5h seg 1-4: SOL/USDC DLMM gaps pass the simulation, then lose
    /// on chain to faster bots; 14 landed, 2 wins worth +12k and +0.7k gross against 108k lamports of fees)
    #[serde(default)]
    pub tpu_skip_mints: Vec<String>,
    /// TPU copies only from this predicted profit up (0 = no floor): below it the trade goes as a bundle only
    #[serde(default)]
    pub tpu_min_expected_lamports: u64,
    /// the bundle arm's resends of the same bundle, ms after the first (w5h seg 7: +100/+250 ms were never accepted,
    /// the gap was gone; empty = none)
    #[serde(default)]
    pub bundle_resend_ms: Vec<u64>,
    /// the bundle arm also sends the same trade at these fractions of its size, at once, under the same nonce (our
    /// quote is exact at small sizes and off at big ones: seg 6 failures were 0.2-4.2 SOL, the wins 0.006-0.024 SOL)
    #[serde(default)]
    pub bundle_size_variants: Vec<f64>,
    /// the TPU arm bids this multiple of the pools' recent 75th-percentile CU price (0 = off) ...
    #[serde(default)]
    pub compete_mult: f64,
    /// ... but never more than this share of the expected profit as priority fee
    #[serde(default = "compete_share")]
    pub compete_max_share: f64,
    /// alternate competitive and flat bids in pairs of TPU trades (measures which wins more per lamport)
    #[serde(default)]
    pub compete_ab: bool,
    /// on-chain min_profit = the copy's tip + 1 lamport (fees are paid whatever happens, so completing a trade whose
    /// gross gain dropped below the fees loses less than reverting it); the decision still needs the full margin
    #[serde(default)]
    pub gross_floor: bool,
    /// WP-00 (temporary; moves to `[send]` in WP-05): live trades expecting at least this profit (lamports) form the
    /// "big band", which is throttled to `big_band_max_per_sec` (0 of 1,869 such bundles landed while they took the
    /// 5/s Jito budget from smaller ones; R §1, §3.4)
    #[serde(default = "big_band_min")]
    pub big_band_min_expected_lamports: u64,
    /// WP-00: the big band's token bucket (rate per second, burst 1); over it the trade is skipped with
    /// `live_skip_big_band_throttle`. 0 = no big-band trade at all
    #[serde(default = "big_band_rate")]
    pub big_band_max_per_sec: f64,
    /// WP-00 (F6, OD-3): JSON list of the pools with 150 or more distinct arbitrage bots (data/crowded-pools.json).
    /// An attempt touching one ranks last (Prio rank 2) in a send path's rate queue, and its rate drops are counted
    /// apart. "" = none
    #[serde(default)]
    pub crowded_pools_file: String,
    /// WP-00 (OD-3's alternative; review F2): a live trade on a crowded pool expecting at least this (lamports) is
    /// skipped (`live_skip_crowded_pool`). 0 = never (rank only). The rank alone changes nothing at the 5/s budget's
    /// load (no two bundles wait at once); in the 12 legacy segments 0 of 1,896 crowded bundles expecting 100k or more
    /// landed, against 12 of 1,214 under 100k
    #[serde(default)]
    pub crowded_skip_min_expected_lamports: u64,
}
fn big_band_min() -> u64 { 1_000_000 }
fn big_band_rate() -> f64 { 0.5 }
fn compete_share() -> f64 { 0.25 }
fn pair_lock() -> u64 { 8_000 }
fn live_prio_cap() -> u64 { 100_000 }
fn bid_min() -> u64 { 100_000 }
fn bid_share() -> f64 { 0.5 }
fn bid_max() -> u64 { 5_000_000 }
fn live_size() -> f64 { 0.1 }
fn live_fee_cap() -> u64 { 20_000_000 }
fn live_margin() -> u64 { 1_000 }
fn live_atas() -> u32 { 5 }
fn live_settle() -> u64 { 15 }
fn live_nonces() -> Vec<String> {
    ["58XHXCVwizLunHZdtXRr21NXnraG8Y4vQWjpXLN2FgVe", "G6MfymxNMNSBResfcJccuvwQMswPW8cq7nB1tsCUN2DC", "CK9tCKm9PNt7Smrymh87UG6PyPi8XmV4gmV3BCPtxJdM"]
        .iter().map(|s| s.to_string()).collect()
}
impl Default for LiveCfg {
    fn default() -> Self { LiveCfg { max_size_sol: live_size(), max_failed_fees_lamports: live_fee_cap(), margin_lamports: live_margin(),
        max_new_token_accounts: live_atas(), settle_s: live_settle(), nonce_accounts: live_nonces(), test_all_paths: false, max_priority_lamports: live_prio_cap(),
        bid_tiers: false, bid_min_expected_lamports: bid_min(), bid_share: bid_share(), bid_max_priority_lamports: bid_max(), spec_cu_price_micro: 0, rotate_paths: false, race_mix: false, bundle_mix: false, tpu_cu_price_micro: 0, pair_lock_ms: pair_lock(), sim_gate: false, tpu_max_expected_lamports: 0, tpu_skip_mriya_pools: false, tpu_skip_mints: Vec::new(), tpu_min_expected_lamports: 0, bundle_resend_ms: Vec::new(), bundle_size_variants: Vec::new(), compete_mult: 0.0, compete_max_share: compete_share(), compete_ab: false, gross_floor: false,
        big_band_min_expected_lamports: big_band_min(), big_band_max_per_sec: big_band_rate(), crowded_pools_file: String::new(), crowded_skip_min_expected_lamports: 0 } }
}

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

/// STEP 3, fees only: real transactions built to FAIL our own profit check (min_profit = 1,000 SOL), one copy per send
/// path under one durable nonce, so at most one lands and it lands failed: only its network fee is paid, and every
/// tip reverts with the trade. Needs `enabled = true` here AND `--canary` on the command line.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct CanaryCfg {
    #[serde(default)]
    pub enabled: bool,
    /// how many canaries in all
    #[serde(default = "canary_count")]
    pub count: u32,
    /// at least this long between two canaries, ms (one is in flight at a time)
    #[serde(default = "canary_every")]
    pub every_ms: u64,
    /// trade size, SOL (the legs really execute before the profit check fails, so the wallet must hold it)
    #[serde(default = "canary_size")]
    pub size_sol: f64,
    /// stop once landed canaries' fees plus the worst case of the one in flight would pass this, lamports
    #[serde(default = "canary_spend")]
    pub max_spend_lamports: u64,
    /// settle each canary this long after it is sent, seconds
    #[serde(default = "canary_settle")]
    pub settle_s: u64,
    /// the durable nonce account (authority: the wallet); arbed's first by default. Never shared with a running arbed.
    #[serde(default = "canary_nonce")]
    pub nonce_account: String,
}
fn canary_count() -> u32 { 100 }
fn canary_every() -> u64 { 5_000 }
fn canary_size() -> f64 { 0.01 }
fn canary_spend() -> u64 { 3_000_000 }
fn canary_settle() -> u64 { 30 }
fn canary_nonce() -> String { "58XHXCVwizLunHZdtXRr21NXnraG8Y4vQWjpXLN2FgVe".into() }
impl Default for CanaryCfg {
    fn default() -> Self { CanaryCfg { enabled: false, count: canary_count(), every_ms: canary_every(), size_sol: canary_size(),
        max_spend_lamports: canary_spend(), settle_s: canary_settle(), nonce_account: canary_nonce() } }
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
    /// per trigger signer (ok, failed) carried across runs: loaded at start, saved every 10 s; "" keeps them per run
    #[serde(default)]
    pub signer_stats_file: String,
    /// wait (at most this many ms) for the pool update naming the trigger before acting: a trigger that failed on chain
    /// never shows, so no trade on a gap that never existed (long run 1: 52% of trades), and the trade is priced on the
    /// real post-trigger state. 0 = act on the prediction at once.
    #[serde(default)]
    pub confirm_trigger_ms: u64,
    /// skip triggers from signers whose triggers mostly fail (with confirm_trigger_ms on, a phantom is never traded
    /// anyway, and the filter only loses the real gaps such signers sometimes make)
    #[serde(default = "skip_signers")]
    pub skip_failing_signers: bool,
    /// also act on CONFIRMED pool moves: whenever any transaction (aggregator- or bot-routed swaps included, which
    /// the instruction decoder cannot see) moves one of our pools, re-check that pair on the live state
    #[serde(default)]
    pub state_triggers: bool,
    /// record, per opportunity, the best round trip at each of these budgets (SOL) to caps.jsonl (what a bigger
    /// balance would add; nothing is traded above live.max_size_sol)
    #[serde(default)]
    pub budget_caps_sol: Vec<f64>,
    /// WP-00 (temporary; removed with the decoded path in WP-04): act on decoded, unconfirmed swaps. Off (default): a
    /// decoded swap is a hint only. Its signer check, slippage check, accuracy check and signer bookkeeping still run,
    /// but no prediction is stored and no route is priced or sent from it (`trigger_hint_only`): 681 of 822 decoded
    /// triggers of 0.1 SOL or more failed on chain (W §7.1)
    #[serde(default)]
    pub decoded_sends: bool,
}
fn yes() -> bool { true }
fn sizes() -> Vec<f64> { vec![0.02, 0.05, 0.1, 0.2, 0.5, 1.0] }
fn min_profit() -> u64 { 10_000 }
fn cu_price() -> u64 { 40_000 }
fn watch_ms() -> u64 { 2_000 }
impl Default for StrategyCfg {
    fn default() -> Self { StrategyCfg { sizes_sol: sizes(), min_profit_lamports: min_profit(), cu_price_micro: cu_price(), outcome_watch_ms: watch_ms(), signer_stats_file: String::new(), confirm_trigger_ms: 0, skip_failing_signers: true, state_triggers: false, budget_caps_sol: vec![], decoded_sends: false } }
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
}

/// THE JITO GATE (arbed's JITO_GATE, owner's Run 2): the jito-bundle copy goes out first, and the paid copies wait up
/// to `wait_ms` after it for the block engine's first result. A `would-fail` on our own profit check (0x4e580002)
/// means the gap is already gone: the paid copies are not sent and nothing is spent. Every `canary_every`-th skip is
/// sent anyway (0 = never), so the gate's cost in lost wins stays measured.
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct GateCfg {
    #[serde(default)]
    pub enabled: bool,
    #[serde(default = "gate_wait")]
    pub wait_ms: u64,
    #[serde(default = "gate_canary")]
    pub canary_every: u64,
}
fn gate_wait() -> u64 { 25 }
fn gate_canary() -> u64 { 10 }
impl Default for GateCfg {
    fn default() -> Self { GateCfg { enabled: false, wait_ms: gate_wait(), canary_every: gate_canary() } }
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
        }
        if cfg.gate.enabled {
            match cfg.sends.iter().find(|s| s.enabled) {
                Some(s) if s.kind == SendKind::JitoBundle => {}
                _ => bail!("[gate] enabled needs a jito-bundle send path listed FIRST among the enabled ones (its copy goes out before the paid ones)"),
            }
        }
        if cfg.feeds.len() > u16::MAX as usize { bail!("too many feeds"); }
        let bb = cfg.live.big_band_max_per_sec;
        if !bb.is_finite() || bb < 0.0 { bail!("[live] big_band_max_per_sec must be a rate >= 0 (0 = no big-band trade)"); }
        // the bucket keeps the rate to 0.001 token/s: a smaller positive rate would silently mean "never"
        if bb > 0.0 && bb < 0.001 { bail!("[live] big_band_max_per_sec {bb}: under 0.001/s (use 0 for no big-band trade)"); }
        if cfg.live.big_band_min_expected_lamports == 0 { bail!("[live] big_band_min_expected_lamports must be > 0 (0 would throttle every live trade)"); }
        Ok(cfg)
    }

    /// The parsed config as JSON with every default filled in and every object's keys sorted: the same settings give
    /// the same text whatever the file's comments, order and formatting (meta.json `config.normalized_sha256`)
    pub fn normalized_json(&self) -> String {
        sorted(serde_json::to_value(self).expect("a config serializes")).to_string()
    }

    /// sha256 (hex) of `normalized_json`
    pub fn normalized_sha256(&self) -> String { crate::provenance::sha256_hex(self.normalized_json().as_bytes()) }

    /// WP-00 (review F3): a config whose strategy prices nothing (neither `state_triggers` nor `decoded_sends`) runs,
    /// records and never finds an opportunity. `arbx check` and `arbx run` print this
    pub fn pricing_warning(&self) -> Option<String> {
        let s = &self.strategy;
        (!s.state_triggers && !s.decoded_sends).then(|| "WARNING: [strategy] state_triggers and decoded_sends are both off: nothing is priced, no opportunity can be found".to_string())
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
        let (st, l) = (&cfg.strategy, &cfg.live);
        assert!(!st.decoded_sends && st.skip_failing_signers && st.state_triggers);
        assert_eq!(st.confirm_trigger_ms, 60, "stays until WP-04 removes it");
        assert!(l.bundle_mix && !l.sim_gate);
        assert_eq!(l.tpu_max_expected_lamports, 1, "every trade on the bundle arm");
        assert_eq!((l.max_new_token_accounts, l.settle_s, l.max_size_sol), (0, 3, 4.2));
        assert_eq!((l.big_band_min_expected_lamports, l.big_band_max_per_sec), (1_000_000, 0.5));
        assert_eq!(l.crowded_skip_min_expected_lamports, 100_000, "OD-3's alternative on top of the rank (review F2)");
        assert!(cfg.record.enabled && cfg.record.archive_feed.is_empty());
        assert!(!cfg.gate.enabled);
        // both deshred feeds now ask for DAMM v2 too
        let deshred: Vec<&Feed> = cfg.feeds.iter().filter(|f| f.kind == FeedKind::YellowstoneDeshred).collect();
        assert_eq!(deshred.len(), 2);
        for f in deshred { assert!(f.account_include.iter().any(|a| a == DAMM_V2), "{}", f.name); }
        // repointed to the arbx tree; the data files it names are in this repo
        assert_eq!(cfg.out_dir, "/root/arbx/runs");
        for f in [cfg.pools.seed_csv.as_str(), cfg.pools.registry_json.as_deref().unwrap(), cfg.pools.templates_json.as_deref().unwrap(), l.crowded_pools_file.as_str()] {
            assert!(f.starts_with("/root/arbx/data/"), "{f}");
            assert!(in_repo(f).is_file(), "{f} is in arbx/data");
        }
        assert!(st.signer_stats_file.starts_with("/root/arbx/"));
    }

    /// review F3 (PLAN §7: every WP updates both maintained configs): each one prices something. arb.toml lost its
    /// only pricing path when decoded_sends became off by default
    #[test]
    fn maintained_configs_have_a_pricing_path() {
        for f in ["deploy/arbx-stage0.toml", "deploy/arb.toml"] {
            let cfg = Config::load(&repo(f)).unwrap();
            assert!(cfg.strategy.state_triggers || cfg.strategy.decoded_sends, "{f} prices nothing");
            assert!(cfg.pricing_warning().is_none(), "{f}");
            assert!(!cfg.strategy.decoded_sends, "{f}: decoded swaps are hints in Stage 0");
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
            ("[exec]", "expected_program_sha = \"x\""), ("[sim]", "enable = true"), ("[canary]", "enabled_ = true"), ("[record]", "enabeld = true"),
            ("[gate]", "wait = 1"), ("[control]", "sockets = false"), ("[[feed]]\nname = \"f\"\nkind = \"udp\"\nbind = \"0.0.0.0:1\"", "binds = \"x\""),
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
        let a = Config::parse(&format!("{MINIMAL}[live]\nmax_size_sol = 0.5\nsettle_s = 3\n")).unwrap();
        let b = Config::parse(&format!("# a comment\n{}[live]\nsettle_s   =   3 # inline\nmax_size_sol = 0.50\n", MINIMAL.replace("wallet = \"w\"\n", "")
            .replace("out_dir", "wallet = \"w\"\nout_dir"))).unwrap();
        assert_eq!(a.normalized_json(), b.normalized_json());
        assert_eq!(a.normalized_sha256(), b.normalized_sha256());
        let c = Config::parse(&format!("{MINIMAL}[live]\nmax_size_sol = 0.6\nsettle_s = 3\n")).unwrap();
        assert_ne!(a.normalized_sha256(), c.normalized_sha256());
        // a default written out explicitly is the same config
        let d = Config::parse(&format!("{MINIMAL}[live]\nmax_size_sol = 0.5\nsettle_s = 3\nmargin_lamports = 1000\n")).unwrap();
        assert_eq!(a.normalized_sha256(), d.normalized_sha256());
        let v: serde_json::Value = serde_json::from_str(&a.normalized_json()).unwrap();
        assert_eq!((v["config_version"].as_u64(), v["live"]["settle_s"].as_u64(), v["control"]["socket"].as_bool()), (Some(2), Some(3), Some(true)));
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

    #[test]
    fn wp00_keys_default_safe() {
        let cfg = Config::parse(MINIMAL).unwrap();
        assert!(!cfg.strategy.decoded_sends, "decoded swaps are hints unless asked");
        assert_eq!((cfg.live.big_band_min_expected_lamports, cfg.live.big_band_max_per_sec), (1_000_000, 0.5));
        assert!(cfg.live.crowded_pools_file.is_empty());
        let on = Config::parse(&format!("{MINIMAL}[strategy]\ndecoded_sends = true\n")).unwrap();
        assert!(on.strategy.decoded_sends);
        assert!(Config::parse(&format!("{MINIMAL}[live]\nbig_band_max_per_sec = -1.0\n")).is_err());
        assert!(Config::parse(&format!("{MINIMAL}[live]\nbig_band_max_per_sec = 0\n")).is_ok(), "0 = no big-band trade");
        assert_eq!(cfg.live.crowded_skip_min_expected_lamports, 0, "OD-3 default: rank only");
        // review N1: a positive rate the bucket would round to "never", and a band that throttles every trade
        assert!(Config::parse(&format!("{MINIMAL}[live]\nbig_band_max_per_sec = 0.0004\n")).is_err());
        assert!(Config::parse(&format!("{MINIMAL}[live]\nbig_band_max_per_sec = 0.001\n")).is_ok());
        assert!(Config::parse(&format!("{MINIMAL}[live]\nbig_band_min_expected_lamports = 0\n")).is_err());
    }
}

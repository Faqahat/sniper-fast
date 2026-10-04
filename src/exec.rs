//! From the engine's decisions to real transactions, in the send plan's steps (step 1, keep-alives, is in send):
//!   step 2  simulation  each would-send decision is built into the real nexus-v2 transaction and simulated, unsigned.
//!                       "ok" or our profit check (0x4e580002) = every leg ran: the encoding is right. sims.jsonl
//!   step 3  canaries    real transactions built to FAIL our profit check (min_profit 1,000 SOL), one copy per send
//!                       path, all under one durable nonce: at most one lands, failed, paying only its network fee
//!                       (tips revert with the trade; a Jito bundle that would fail is dropped and only reports why).
//!                       attempts.jsonl (one per canary), copies.jsonl (send), outcomes.jsonl (settled from chain)
//!   step 4  live        real trades on the engine's decisions: size at most [live] max_size_sol, the owner's fee rule,
//!                       one copy per path with that path's tip and its own on-chain min_profit (base + priority + tip +
//!                       margin: a landed trade cannot lose), all under one durable nonce lease, the Jito gate first.
//!                       Stops by itself once fees of failed landed transactions reach [live] max_failed_fees_lamports.
//! Building and signing run on the engine thread (microseconds); RPC and sending run on the runtime.
use crate::build::{self, Alt, PumpGlobal};
use crate::config::{Config, SendKind};
use crate::control::{GateMode, SendGate};
use crate::feeds::{clock::now_ns, Event};
use crate::rpc::Rpc;
use crate::lat::Series;
use crate::rec::{self, Rec};
use crate::send::{self, Copy, Fired, Paths, Prio, TokenBucket, RANK_CROWDED, RANK_OTHER, RANK_SEED};
use crate::tx::{b58, pk, Pk};
use crate::venues::{PoolMeta, WSOL};
use anyhow::{Context, Result};
use crossbeam_channel::Sender;
use rustc_hash::{FxHashMap as HashMap, FxHashSet as HashSet};
use serde_json::{json, Value};
use std::collections::VecDeque;
use std::sync::Arc;

/// a canary's min_profit: unreachable, so the profit check always fails (1,000 SOL)
const CANARY_MIN_PROFIT: u64 = 1_000_000_000_000;
/// the fee rule (owner, 2026-10-03): the flat bid, which is also Helius Sender's floor; a copy of the trigger's bid at
/// 0.95x; and the priority fee never above a quarter of the expected profit (what a failed send still costs)
const FLAT_CU_PRICE: u64 = 40_000;
const TRIGGER_SHARE: f64 = 0.95;
const MAX_FEE_SHARE_OF_PROFIT: f64 = 0.25;
/// CU for creating the mid token account when the wallet has none (arbed's cu-budget allowance)
const ATA_CREATE_CU: u64 = 30_000;
const BASE_FEE: u64 = 5_000;

/// Everything a build needs about one round trip, owned (the engine fills it at the size the step wants)
#[derive(Clone)]
pub struct RouteIn {
    pub opp: u64,
    pub trig: [u8; 64],
    pub trig_feed: Option<String>,
    pub slot: u64,
    /// engine stage times: rx, decoded, engine, resolved, decided
    pub st: [u64; 5],
    pub buy: PoolMeta,
    pub sell: PoolMeta,
    pub buy_data: Vec<u8>,
    pub sell_data: Vec<u8>,
    pub buy_source: &'static str,
    pub sell_source: &'static str,
    pub mint: Pk,
    pub size: u64,
    /// our prediction at `size`: what the buy leg delivers, what the sell leg returns
    pub mid: u64,
    pub back: u64,
    pub gross_at_opp: i64,
    pub net_at_opp: i64,
    /// the trigger's own compute-unit price, micro-lamports per CU (None: it bid none)
    pub trig_cu_price: Option<u64>,
    /// what others bid on these pools lately: the 75th percentile CU price of every transaction that touched them
    /// in the last 30 s (they compete for the pools' write locks in the leader's scheduler)
    pub rival_cu_price: Option<u64>,
    pub cu: u64,
    pub buy_live: Vec<i64>,
    pub sell_live: Vec<i64>,
    pub buy_end: Option<i32>,
    pub sell_end: Option<i32>,
    /// WP-04 item 10: the state version the decision priced (xxh3 over the route accounts' (pubkey, slot,
    /// write_version)), the time since the route's last write, and the decision (decisions.jsonl `decision`)
    pub state_version: u64,
    pub route_age_ms: Option<f64>,
    pub decision: u64,
}

struct Built { msg: build::Message, cu_limit: u64, creates_ata: bool }

/// A settled attempt (canary or live), sent back to the engine (which adds what its own feeds saw)
pub struct Settled {
    pub attempt: u64,
    pub fired: Fired,
    /// (path index, signature, chain slot, landed transaction)
    pub landed: Option<(usize, String, u64, Value)>,
    pub jito: Option<send::jito::Outcome>,
    pub nonce_value: Option<[u8; 32]>,
    pub error: Option<String>,
}

fn sig64(s: &str) -> Option<[u8; 64]> { bs58::decode(s).into_vec().ok()?.try_into().ok() }

/// what the sender sends: canaries (built to fail) or live trades
#[derive(Clone, Copy, PartialEq, Debug, serde::Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum Kind { Canary, Live }

/// one durable nonce account, leased to one attempt at a time (its copies share it, so at most one lands)
struct NonceSlot { acct: Pk, value: Option<[u8; 32]>, busy: Option<u64> }

/// an attempt waiting for its settlement
struct Open { route: RouteIn, nonce: usize, worst: u64, creates_ata: bool, expected: i64, t: u64, bundle: bool }

struct Sending {
    kind: Kind,
    key: ed25519_dalek::SigningKey,
    nonces: Vec<NonceSlot>,
    /// canary: how many, how far apart, what size; live: the size cap
    count: u32,
    every_ms: u64,
    size: u64,
    /// stop once `spent` plus the worst case of what is in flight would pass this (lamports)
    cap: u64,
    settle_s: u64,
    margin: u64,
    max_new_atas: u32,
    sent: u32,
    last_ns: u64,
    /// fees of landed transactions that failed (from chain); worst-case fees of attempts still in flight
    spent: u64,
    reserved: u64,
    /// all fees, tips paid, real profit (chain balance changes) of landed transactions
    fees: u64,
    tips: u64,
    profit: i64,
    landed: u32,
    wins: u32,
    new_atas: u32,
    /// our copies' signatures -> (attempt, path) while open, and what our feeds saw of them
    watch: HashMap<[u8; 64], (u64, usize)>,
    seen: HashMap<[u8; 64], (u64, u16, Vec<(u16, u64)>)>,
    open: HashMap<u64, Open>,
    stopped: Option<&'static str>,
}

impl Sending {
    fn new(cfg: &Config, kind: Kind, key: ed25519_dalek::SigningKey, nonces: Vec<NonceSlot>) -> Sending {
        let (c, l) = (&cfg.canary, &cfg.live);
        match kind {
            Kind::Canary => Sending { kind, key, nonces, count: c.count, every_ms: c.every_ms, size: sol(c.size_sol), cap: c.max_spend_lamports, settle_s: c.settle_s,
                margin: 0, max_new_atas: u32::MAX, sent: 0, last_ns: 0, spent: 0, reserved: 0, fees: 0, tips: 0, profit: 0, landed: 0, wins: 0, new_atas: 0,
                watch: HashMap::default(), seen: HashMap::default(), open: HashMap::default(), stopped: None },
            Kind::Live => Sending { kind, key, nonces, count: u32::MAX, every_ms: 0, size: sol(l.max_size_sol), cap: l.max_failed_fees_lamports, settle_s: l.settle_s,
                margin: l.margin_lamports, max_new_atas: l.max_new_token_accounts, sent: 0, last_ns: 0, spent: 0, reserved: 0, fees: 0, tips: 0, profit: 0, landed: 0,
                wins: 0, new_atas: 0, watch: HashMap::default(), seen: HashMap::default(), open: HashMap::default(), stopped: None },
        }
    }
}


pub struct Exec {
    payer: Pk,
    program: Pk,
    alts: Vec<Alt>,
    pump: Option<PumpGlobal>,
    held: HashSet<Pk>,
    rpc: Rpc,
    rt: tokio::runtime::Handle,
    back: Sender<Event>,
    paths: Option<Arc<Paths>>,
    cu_price: u64,
    max_size: u64,
    min_tip_paid: u64,
    sim_rate: Option<usize>,
    sim_recent: VecDeque<u64>,
    /// sims.jsonl ([sim] enabled), attempts.jsonl, outcomes.jsonl and the diagnostic `log` events, through the recorder
    rec: Rec,
    sims_on: bool,
    sending: Option<Sending>,
    /// the Jito gate is on ([gate] enabled): live paid copies then need a bundle copy to wait behind
    gate_on: bool,
    /// [live] test_all_paths: a copy on every path whatever its tip (testing landing, not profit)
    all_paths: bool,
    /// [live] max_priority_lamports: the absolute cap on one trade's priority fee
    prio_cap: u64,
    /// [live] bid_tiers: (min expected profit for the bid tier, share of it bid, cap), or None for the old rule
    tiers: Option<(u64, f64, u64)>,
    /// [live] spec_cu_price_micro: the speculative tier's compute-unit price
    spec_price: u64,
    /// [live] rotate_paths: one path per trade, the next in turn (measurement)
    rotate: bool,
    /// [live] race_mix, and the path arm of the trade being built
    mix: bool,
    path_arm: &'static str,
    /// [live] bundle_mix / tpu_cu_price_micro / pair_lock_ms
    bmix: bool,
    tpu_price: u64,
    sim_gate: bool,
    /// [live] compete_mult / compete_max_share / compete_ab: the TPU arm's competitive bid
    compete_mult: f64,
    compete_share: f64,
    compete_ab: bool,
    /// [live] gross_floor: the on-chain min_profit is the tip + 1, not fees + tip + margin (the send decision is unchanged)
    gross_floor: bool,
    tpu_max_expected: u64,
    tpu_skip_mriya: bool,
    tpu_skip_mints: HashSet<Pk>,
    tpu_min_expected: u64,
    bundle_resend_ms: Vec<u64>,
    bundle_variants: Vec<f64>,
    /// per token: (Jito rejections in a row, paused until (ns), pauses so far). A token whose gaps the crowd always takes
    /// first (w5h seg 9: SPEC, 550 bundles, 0 accepted) burns the 5/s Jito budget and the nonces other tokens need.
    mint_cool: HashMap<Pk, (u32, u64, u32)>,
    pair_lock_ns: u64,
    /// WP-00: the crowded pools and the band rules of live trades (big-band bucket, crowded skip)
    band: BandGate,
    rot: usize,
    next_attempt: u64,
    feeds: Vec<String>,
    pub counts: HashMap<&'static str, u64>,
    /// stage latencies of the send (status.jsonl `latency`, A.8): `decided_to_signed`, `signed_to_fired` (handed to
    /// the runtime: the cost of the spawn), `signed_to_sent` (the first copy's send task running, from `on_settled`)
    pub lat: Vec<Series>,
    /// WP-01: the run's SendGate (control socket pause / shadow, `--shadow`, a route program hash mismatch, a stop
    /// request): `wants_send` refuses while it is not live
    gate: Arc<SendGate>,
    /// the SendGate mode the last `wants_send` read (None: it returned before reading it); the engine journals it at the
    /// decision point (review WP-03 #3)
    gate_seen: Option<GateMode>,
    /// WP-04 item 8 / PLAN-ADDENDUM I-4: the engine's store health (warm-up, state availability). `wants_send` refuses
    /// unless it is ready. An executor on its own (tools, tests) is always ready; `Engine::run` installs the engine's
    health: Arc<crate::store_health::HealthFlags>,
    /// why the last `wants_send` refused (decisions.jsonl `reason`), None when it allowed a send
    refused: Option<String>,
}

/// `Exec::lat` series, in order
const LAT_DECIDED_TO_SIGNED: usize = 0;
const LAT_SIGNED_TO_FIRED: usize = 1;
const LAT_SIGNED_TO_SENT: usize = 2;
fn exec_lat() -> Vec<Series> { ["decided_to_signed", "signed_to_fired", "signed_to_sent"].into_iter().map(Series::new).collect() }

/// WP-00's band rules for live trades, apart from `copies` so they can be tested (review F8):
/// - a route touching a crowded pool ranks last in the send paths' rate queues (F6, OD-3 default), and from
///   `crowded_skip_min` lamports expected it is not sent at all (`live_skip_crowded_pool`, OD-3's alternative; 0 = never);
/// - the big band (expected >= `big_min`) takes a token from a bucket (`live_skip_big_band_throttle`). `check` only
///   peeks at the token; `commit` takes it once the attempt is built and about to fire (review F5: an attempt that
///   then fails to build used to waste the next 2 s of big-band capacity).
/// Canaries are never subject to them.
pub struct BandGate { crowded: HashSet<Pk>, crowded_skip_min: u64, big_min: u64, big: TokenBucket }

impl BandGate {
    pub fn new(crowded: HashSet<Pk>, crowded_skip_min: u64, big_min: u64, big_per_sec: f64) -> BandGate {
        BandGate { crowded, crowded_skip_min, big_min, big: TokenBucket::new(big_per_sec, 1) }
    }

    pub fn from_cfg(cfg: &Config, crowded: HashSet<Pk>) -> BandGate {
        let l = &cfg.live;
        BandGate::new(crowded, l.crowded_skip_min_expected_lamports, l.big_band_min_expected_lamports, l.big_band_max_per_sec)
    }

    pub fn crowded(&self) -> &HashSet<Pk> { &self.crowded }

    pub fn is_crowded(&self, buy: &Pk, sell: &Pk) -> bool { self.crowded.contains(buy) || self.crowded.contains(sell) }

    /// may this attempt go? Err = the skip reason (counted in status.jsonl)
    pub fn check(&self, kind: Kind, buy: &Pk, sell: &Pk, expected: i64, now: u64) -> Result<(), &'static str> {
        if kind != Kind::Live { return Ok(()); }
        // 0 of 1,896 legacy crowded bundles expecting 100k or more landed: they only took budget from the rest
        if self.crowded_skip_min > 0 && expected >= self.crowded_skip_min as i64 && self.is_crowded(buy, sell) { return Err("live_skip_crowded_pool"); }
        // the big band (expected >= 1M: 0 of 1,869 such bundles landed, while 1,020 attempts were lost to the 5/s Jito
        // limit) gets at most big_band_max_per_sec, so it stops crowding out the trades that do land
        if expected >= self.big_min as i64 && !self.big.peek(now) { return Err("live_skip_big_band_throttle"); }
        Ok(())
    }

    /// the attempt passed `check` and is going out now: a big-band one uses its token (still there: a bucket only fills)
    pub fn commit(&mut self, kind: Kind, expected: i64, now: u64) {
        if kind == Kind::Live && expected >= self.big_min as i64 { let _ = self.big.try_take(now); }
    }
}

fn sol(x: f64) -> u64 { (x * 1e9) as u64 }
fn hex_code(c: u32) -> String { format!("0x{c:x}") }

#[cfg(test)]
mod tests {
    use super::*;
    use crate::send::budget::Budget;
    use crate::venues::Venue;
    use std::time::Duration;

    /// arbx-exec REVIEW.md #8: every arbx-exec code has its own meaning, none falls through to "a venue's own error"
    #[test]
    fn meaning_knows_the_arbx_exec_codes() {
        let e = Some(serde_json::json!("x"));
        for c in 0x4e58_0001u32..=0x4e58_000c {
            assert_ne!(super::meaning(Some(c), &e), "a venue's own error (see code)", "{c:#x}");
        }
        assert_eq!(super::meaning(Some(0x4e58_0009), &e).split(':').next(), Some("arbx-exec"));
        assert_eq!(super::meaning(Some(0x4e58_0107), &e), "nexus: a leg delivered nothing");
    }

    fn key(b: u8) -> Pk { [b; 32] }

    /// WP-00 acceptance (F6): a route touching a crowded pool ranks behind both other ranks
    #[test]
    fn crowded_pool_ranks_behind_both_other_ranks() {
        let crowded: HashSet<Pk> = [key(9)].into_iter().collect();
        let seed = prio_rank(&key(1), &key(2), "mriya", "ours", &crowded);
        let other = prio_rank(&key(1), &key(2), "ours", "?", &crowded);
        let crowd = prio_rank(&key(9), &key(2), "mriya", "mriya", &crowded);
        assert_eq!((seed, other, crowd), (RANK_SEED, RANK_OTHER, RANK_CROWDED));
        assert!(crowd > seed && crowd > other, "crowded queues last, even on a seed pool");
        assert_eq!(prio_rank(&key(1), &key(9), "ours", "ours", &crowded), RANK_CROWDED, "either pool of the route");
        assert_eq!(prio_rank(&key(9), &key(2), "ours", "ours", &HashSet::default()), RANK_OTHER, "no list: arb-lab's ranks");
        assert!(Prio { rank: crowd, net: 0 }.crowded() && !Prio { rank: seed, net: 0 }.crowded() && !Prio { rank: other, net: 0 }.crowded());
        // review N2: a seed pool our registry also has ("both") is a seed pool
        assert_eq!(prio_rank(&key(1), &key(2), "ours", "both", &crowded), RANK_SEED);
    }

    /// ... and when bundles do wait for a slot, the rate queue serves it after both, even with by far the biggest
    /// expected profit. The Budget's ordering only: Stage 0 ships without a queue (queue_ms 0; review F2: at 10 ms it
    /// reordered nothing), so there the crowded share is cut by `BandGate` (`band_gate_cuts_the_crowded_share`).
    /// WP-05 brings the queue back.
    #[tokio::test(start_paused = true)]
    async fn crowded_route_is_served_last_by_the_rate_queue() {
        let b = Arc::new(Budget::new(1, Duration::from_millis(3_500)));
        assert!(b.acquire(Prio::default()).await);
        let crowded: HashSet<Pk> = [key(9)].into_iter().collect();
        let order = Arc::new(std::sync::Mutex::new(Vec::new()));
        let mut hs = Vec::new();
        for (name, buy, src, net) in [("crowded-big", key(9), "ours", 1_000_000_000i64), ("other", key(1), "ours", 10), ("seed", key(1), "mriya", 1)] {
            let prio = Prio { rank: prio_rank(&buy, &key(2), src, "ours", &crowded), net };
            let (b, order) = (b.clone(), order.clone());
            hs.push(tokio::spawn(async move { if b.acquire(prio).await { order.lock().unwrap().push(name); } }));
            tokio::task::yield_now().await;
        }
        for h in hs { h.await.unwrap(); }
        // one slot a second: the seed route at 1 s, the other at 2 s, the crowded one at 3 s
        assert_eq!(*order.lock().unwrap(), vec!["seed", "other", "crowded-big"]);
    }

    /// data/crowded-pools.json: the 21 pools with 150 or more bots, with its source and date; bad entries are errors
    #[test]
    fn crowded_pools_file_loads() {
        let text = std::fs::read_to_string(concat!(env!("CARGO_MANIFEST_DIR"), "/data/crowded-pools.json")).unwrap();
        let set = parse_crowded_pools(&text).unwrap();
        assert_eq!(set.len(), 21, "PATTERNS.md item 10: 21 pools with 150 or more bots");
        let v: serde_json::Value = serde_json::from_str(&text).unwrap();
        assert!(v["source"].is_string() && v["date"].is_string());
        assert!(v["pools"].as_array().unwrap().iter().all(|p| p["bots"].as_u64().unwrap() >= 150));
        assert_eq!(parse_crowded_pools("[\"58oQChx4yWmvKdwLLZzBi4ChoCc2fqCUWBkwMihLYQo2\"]").unwrap().len(), 1, "a plain array");
        assert!(parse_crowded_pools("{\"pools\": [{\"pool\": \"not-a-key\"}]}").is_err());
        assert!(parse_crowded_pools("{\"pools\": [{\"bots\": 200}]}").is_err());
        assert!(parse_crowded_pools("{}").is_err());
        assert!(parse_crowded_pools("{\"pools\": []}").is_err(), "review N1: an empty list is a mistake, not a list");
        assert!(super::load_crowded_pools("/nonexistent/crowded-pools.json").is_err(), "a configured list must load");
    }

    const S: u64 = 1_000_000_000;

    /// the Stage-0 band rules (deploy/arbx-stage0.toml): crowded out from 100k, the big band at 0.5/s
    fn stage0_gate() -> BandGate { BandGate::new([key(9)].into_iter().collect(), 100_000, 1_000_000, 0.5) }

    /// WP-00 (F6, OD-3's alternative; review F2, F5, F8a): the live band rules, and canaries are never subject to them
    #[test]
    fn band_gate_skips_crowded_from_100k_and_throttles_the_big_band() {
        let mut g = stage0_gate();
        let t = 1_000 * S;
        let (c, o) = (key(9), key(1));
        assert_eq!(g.check(Kind::Live, &c, &o, 99_999, t), Ok(()), "a small crowded trade still goes (12 of the 20 legacy bundle wins)");
        assert_eq!(g.check(Kind::Live, &o, &c, 100_000, t), Err("live_skip_crowded_pool"), "either pool of the route");
        assert_eq!(g.check(Kind::Live, &c, &o, 5_000_000, t), Err("live_skip_crowded_pool"), "crowded before the big band: no token used");
        assert_eq!(g.check(Kind::Canary, &c, &o, 5_000_000, t), Ok(()));
        // the big band: check only peeks; the token goes with commit
        assert_eq!(g.check(Kind::Live, &o, &key(2), 1_000_000, t), Ok(()));
        assert_eq!(g.check(Kind::Live, &o, &key(2), 1_000_000, t), Ok(()), "an attempt that never went (no commit) took no token");
        g.commit(Kind::Live, 1_000_000, t);
        assert_eq!(g.check(Kind::Live, &o, &key(2), 2_000_000, t + S), Err("live_skip_big_band_throttle"));
        assert_eq!(g.check(Kind::Live, &o, &key(2), 999_999, t + S), Ok(()), "below the band");
        assert_eq!(g.check(Kind::Canary, &o, &key(2), 2_000_000, t + S), Ok(()), "canaries are not throttled");
        g.commit(Kind::Canary, 2_000_000, t + S);
        assert_eq!(g.check(Kind::Live, &o, &key(2), 2_000_000, t + 2 * S), Ok(()), "a token every 2 s; the canary used none");
        // rank only (OD-3 default, skip 0): nothing crowded is skipped
        let g0 = BandGate::new([key(9)].into_iter().collect(), 0, 1_000_000, 0.5);
        assert_eq!(g0.check(Kind::Live, &c, &o, 500_000, t), Ok(()));
    }

    /// review F2: the configured policy cuts the crowded share of what is sent, and keeps every crowded trade under
    /// 100k (where the legacy crowded wins were). Legacy mix of jito-bundle attempts (12 segments, testdata/legacy):
    /// crowded 1,214 / 866 / 1,030 and other 437 / 614 / 621 in the bands < 100k / 100k-1M / >= 1M; 66% crowded.
    #[test]
    fn band_gate_cuts_the_crowded_share() {
        // the legacy mix, interleaved deterministically, one attempt every 400 ms (about the legacy busy rate)
        let mix = [(true, 50_000i64, 1_214u32), (true, 500_000, 866), (true, 3_000_000, 1_030), (false, 50_000, 437), (false, 500_000, 614), (false, 3_000_000, 621)];
        let mut stream = Vec::new();
        for (crowded, exp, n) in mix { for k in 0..n { stream.push(((k as u64 * 7_919 + exp as u64) % 4_797, crowded, exp)); } }
        stream.sort();
        let run = |mut g: BandGate| {
            let (mut sent_c, mut sent_o, mut small_c) = (0u32, 0u32, 0u32);
            for (k, (_, crowded, exp)) in stream.iter().enumerate() {
                let t = 1_000 * S + k as u64 * 400_000_000;
                let buy = if *crowded { key(9) } else { key(1) };
                if g.check(Kind::Live, &buy, &key(2), *exp, t).is_ok() {
                    g.commit(Kind::Live, *exp, t);
                    if *crowded { sent_c += 1; if *exp < 100_000 { small_c += 1; } } else { sent_o += 1; }
                }
            }
            (sent_c as f64 / (sent_c + sent_o) as f64, small_c, sent_o)
        };
        let (rank_only, _, other_rank_only) = run(BandGate::new([key(9)].into_iter().collect(), 0, 1_000_000, 0.5));
        let (stage0, small, other_stage0) = run(stage0_gate());
        // here 0.57 -> 0.42 (the legacy replay of the same rules: 0.64 -> 0.45)
        assert!(rank_only > 0.55, "rank only: the crowded pools keep {rank_only:.2} of the sends");
        assert!(stage0 < 0.45 && rank_only - stage0 > 0.1, "Stage 0: {stage0:.2}");
        assert_eq!(small, 1_214, "every crowded trade under 100k still goes");
        assert!(other_stage0 >= other_rank_only, "the big band's tokens go to the other routes: {other_stage0} vs {other_rank_only}");
    }

    // ------------------------------------------------------------ Exec wiring (review F8)

    const MINT: Pk = [7u8; 32];

    fn test_cfg(dir: &std::path::Path, crowded: &str) -> Config { test_cfg_live(dir, crowded, "") }

    /// `extra`: more `[live]` lines
    fn test_cfg_live(dir: &std::path::Path, crowded: &str, extra: &str) -> Config {
        let wallet = bs58::encode(ed25519_dalek::SigningKey::from_bytes(&[1u8; 32]).verifying_key().to_bytes()).into_string();
        Config::parse(&format!("config_version = 2\nout_dir = \"{}\"\nwallet = \"{wallet}\"\n[pools]\nseed_csv = \"s.csv\"\n[rpc]\n[state]\nurl = \"http://localhost\"\n\
            [live]\npair_lock_ms = 0\ncrowded_pools_file = \"{crowded}\"\ncrowded_skip_min_expected_lamports = 100000\n{extra}\
            [[send]]\nname = \"rpc0\"\nkind = \"rpc\"\nurl = \"http://127.0.0.1:1\"\n", dir.display())).unwrap()
    }

    fn damm(n: u8, t0: Pk) -> PoolMeta {
        PoolMeta { venue: Venue::DammV2, pool: [n; 32], t0, t1: *WSOL, vault0: [n + 50; 32], vault1: [n + 100; 32],
            t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false }
    }

    /// a round trip of 1 SOL between pools `buy` and `sell` (1 or 9: 9 is on the crowded list) expecting `expected`
    fn route(buy: u8, sell: PoolMeta, expected: u64) -> RouteIn {
        let size = 1_000_000_000u64;
        RouteIn { opp: buy as u64, trig: [3u8; 64], trig_feed: None, slot: 11, st: [100, 100, 200, 300, now_ns()], buy: damm(buy, MINT), sell,
            buy_data: vec![], sell_data: vec![], buy_source: "ours", sell_source: "ours", mint: MINT, size, mid: 1_000, back: size + expected,
            gross_at_opp: expected as i64, net_at_opp: expected as i64, trig_cu_price: None, rival_cu_price: None, cu: 100_000,
            buy_live: vec![], sell_live: vec![], buy_end: None, sell_end: None, state_version: 0, route_age_ms: None, decision: 0 }
    }

    struct Rig { x: Exec, dir: std::path::PathBuf, rec: Rec }
    impl Drop for Rig { fn drop(&mut self) { self.rec.close(); let _ = std::fs::remove_dir_all(&self.dir); } }

    /// a recorder in `dir` (no monitor thread)
    fn test_rec(dir: &std::path::Path) -> Rec {
        rec::start(rec::Opts { dir: dir.to_path_buf(), run: "test".into(), producer: "test".into(), cfg: Default::default(), feeds: vec![], monitor: false, echo: None }).unwrap()
    }

    /// a live Exec on a made-up wallet (no network: the one send path is a closed local port), three nonces
    async fn live_rig(name: &str) -> Rig { live_rig_with(name, "").await.0 }

    /// a live rig with more `[live]` lines; also the events the executor sends back (settlements)
    async fn live_rig_with(name: &str, extra: &str) -> (Rig, crossbeam_channel::Receiver<Event>) {
        let dir = std::env::temp_dir().join(format!("arbx-exec-{name}-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&dir).unwrap();
        let rec = test_rec(&dir);
        let (x, rx) = live_exec(&dir, &rec, extra).await;
        (Rig { x, dir, rec }, rx)
    }

    /// a live Exec recording into `rec` (see `live_rig`)
    async fn live_exec(dir: &std::path::Path, rec: &Rec, extra: &str) -> (Exec, crossbeam_channel::Receiver<Event>) {
        let crowded_file = dir.join("crowded.json");
        std::fs::write(&crowded_file, format!("[\"{}\"]", bs58::encode([9u8; 32]).into_string())).unwrap();
        let cfg = test_cfg_live(dir, crowded_file.to_str().unwrap(), extra);
        let rec = rec.clone();
        let (paths, _) = Paths::new(&cfg.sends, cfg.gate.clone(), rec.clone(), false).await.unwrap();
        let key = ed25519_dalek::SigningKey::from_bytes(&[1u8; 32]);
        let nonces = (0..3u8).map(|k| NonceSlot { acct: [200 + k; 32], value: Some([k; 32]), busy: None }).collect();
        let sending = Sending::new(&cfg, Kind::Live, key, nonces);
        let held: HashSet<Pk> = [*WSOL, MINT].into_iter().collect();
        let (tx, rx) = crossbeam_channel::unbounded();
        let band = BandGate::from_cfg(&cfg, load_crowded_pools(&cfg.live.crowded_pools_file).unwrap());
        let x = Exec::assemble(&cfg, Rpc::race(vec![]), Some(paths), rec.clone(), tx, vec![], vec![], None, held, Some(sending), band).unwrap();
        (x, rx)
    }

    /// attempts.jsonl as written so far (through the recorder: attempts.000.jsonl.zst, its header skipped)
    fn attempts(r: &Rig) -> Vec<Value> {
        r.rec.sync();
        rec::read_jsonl(&r.dir, "attempts").unwrap()
    }
    fn n(x: &Exec, k: &str) -> u64 { x.counts.get(k).copied().unwrap_or(0) }

    /// review F8 (a, b) and F5 through `Exec::send`: the attempt line carries `crowded`, `queue_rank` and `st.fired`
    /// (after `signed`: the line is written after the copies were handed to the send paths); a crowded route from 100k
    /// and a second big-band trade inside 2 s are skipped; a big-band attempt that fails to build uses no token
    #[tokio::test]
    async fn send_writes_the_queue_fields_and_applies_the_band_rules() {
        let mut r = live_rig("send").await;
        // a big-band trade whose sell leg cannot be built (wrong mints): no copy, and the token stays
        r.x.send(route(1, damm(2, [8u8; 32]), 2_000_000));
        assert_eq!(n(&r.x, "live_skip_no_copy_worth_sending"), 1);
        assert!(attempts(&r).is_empty());
        // a small crowded trade goes, ranked last
        r.x.send(route(9, damm(2, MINT), 50_000));
        // a big-band trade goes (the failed one above used no token) ...
        r.x.send(route(1, damm(3, MINT), 2_000_000));
        // ... and the next one inside 2 s is throttled; a crowded one from 100k is skipped
        r.x.send(route(1, damm(4, MINT), 3_000_000));
        r.x.send(route(9, damm(5, MINT), 200_000));
        let x = &r.x;
        assert_eq!((n(x, "live_sent"), n(x, "rank_crowded"), n(x, "live_skip_big_band_throttle"), n(x, "live_skip_crowded_pool")), (2, 1, 1, 1));
        let a = attempts(&r);
        assert_eq!(a.len(), 2);
        assert_eq!((a[0]["crowded"].as_bool(), a[0]["queue_rank"].as_u64()), (Some(true), Some(RANK_CROWDED as u64)));
        assert_eq!((a[1]["crowded"].as_bool(), a[1]["queue_rank"].as_u64()), (Some(false), Some(RANK_OTHER as u64)));
        for l in &a {
            let st = &l["st"];
            let (signed, fired) = (st["signed"].as_u64().unwrap(), st["fired"].as_u64().expect("fired: no sim gate"));
            assert!(fired >= signed && signed >= st["built"].as_u64().unwrap());
            assert_eq!(st["rx"].as_u64(), Some(100));
        }
        assert_eq!((x.lat[LAT_DECIDED_TO_SIGNED].n(), x.lat[LAT_SIGNED_TO_FIRED].n()), (2, 2));
    }

    /// PLAN WP-01 acceptance (control test): `pause-sending` through the control socket makes `wants_send` return None
    /// and writes a control.jsonl line; `resume-sending` lets it send again; a stop request closes it for good
    #[tokio::test]
    async fn control_pause_closes_wants_send() {
        use crate::control::{self, StopInfo, StopReason};
        let mut r = live_rig("ctl").await;
        let sess = control::Session::new();
        sess.set_dir(r.dir.clone());
        r.x.set_gate(sess.gate.clone());
        let size = r.x.sending.as_ref().unwrap().size;
        assert_eq!(r.x.wants_send(), Some(size), "live: may send");
        let _srv = control::serve(sess.clone(), &r.dir).unwrap();
        let rep = control::send_command(&r.dir, "pause-sending", "moiz", "WP-01 control test").unwrap();
        assert_eq!((rep["accepted"].as_bool(), rep["send_gate"]["mode"].as_str()), (Some(true), Some("shadow")));
        assert_eq!(r.x.wants_send(), None, "paused");
        assert_eq!(n(&r.x, "reject_gate_shadow"), 1);
        let log: Vec<Value> = std::fs::read_to_string(r.dir.join("control.jsonl")).unwrap().lines().map(|l| serde_json::from_str(l).unwrap()).collect();
        assert_eq!(log.len(), 1);
        assert_eq!((log[0]["src"].as_str(), log[0]["cmd"].as_str(), log[0]["who"].as_str(), log[0]["why"].as_str(), log[0]["accepted"].as_bool(), log[0]["result"].as_str()),
            (Some("socket"), Some("pause-sending"), Some("moiz"), Some("WP-01 control test"), Some(true), Some("shadow")));
        assert!(control::send_command(&r.dir, "resume-sending", "moiz", "done").unwrap()["accepted"].as_bool().unwrap());
        assert!(r.x.wants_send().is_some(), "resumed");
        sess.stopper.request(StopInfo::new(StopReason::Signal, "SIGINT"));
        assert_eq!(r.x.wants_send(), None, "stopping");
        assert_eq!(n(&r.x, "reject_gate_stopped"), 1);
        assert!(!control::send_command(&r.dir, "resume-sending", "moiz", "again").unwrap()["accepted"].as_bool().unwrap());
    }

    /// review WP-03 #3: the SendGate mode each send check saw is journaled on the engine thread at the decision (INPUT
    /// gate, `src` "decision", with the opportunity's id) whenever it differs from the last one journaled, and is part
    /// of the decision digest; the live gate still decides (a pause closes the very next check)
    #[tokio::test]
    async fn the_gate_each_send_check_saw_is_journaled() {
        use crate::config::StrategyCfg;
        use crate::engine::Engine;
        use crate::rec::journal::{self, JBody};
        let dir = std::env::temp_dir().join(format!("arbx-exec-gatej-{}-{}", std::process::id(), now_ns()));
        std::fs::create_dir_all(&dir).unwrap();
        let rec = test_rec(&dir);
        let (mut x, _rx) = live_exec(&dir, &rec, "").await;
        let gate = SendGate::new();
        x.set_gate(gate.clone());
        // two AMM v4 pools on MINT / WSOL
        let amm = |n: u8| PoolMeta { venue: Venue::RayAmmV4, pool: [n; 32], t0: MINT, t1: *WSOL, vault0: [n + 10; 32], vault1: [n + 20; 32],
            t0_prog: *crate::pda::TOKEN_PROGRAM, t1_prog: *crate::pda::TOKEN_PROGRAM, extra: vec![], flag: false };
        let vault = |amount: u64| -> Arc<[u8]> { let mut v = vec![0u8; 165]; v[64..72].copy_from_slice(&amount.to_le_bytes()); v.into() };
        let pool_data: Arc<[u8]> = { let mut p = vec![0u8; 752]; p[0..8].copy_from_slice(&1u64.to_le_bytes()); p[176..184].copy_from_slice(&25u64.to_le_bytes());
            p[184..192].copy_from_slice(&10_000u64.to_le_bytes()); p.into() };
        let (a, b) = (amm(1), amm(2));
        let mut reg = crate::pools::Registry { pools: vec![a.clone(), b.clone()], by_pool: Default::default(), pairs: Default::default(), seeds: Default::default(), ours: Default::default() };
        reg.by_pool.insert(a.pool, 0);
        reg.by_pool.insert(b.pool, 1);
        reg.pairs.insert(crate::pools::pair_key(&MINT, &WSOL), vec![0, 1]);
        let mut store = crate::store::Store::default();
        for (m, sol) in [(&a, 1_000u64), (&b, 1_010)] {
            store.update(m.pool, pool_data.clone(), 10, 1, None);
            store.update(m.vault0, vault(1_000_000_000_000_000), 10, 1, None);
            store.update(m.vault1, vault(sol * 1_000_000_000), 10, 1, None);
        }
        let mut e = Engine::new_offline(Arc::new(reg), store, StrategyCfg { state_triggers: true, ..StrategyCfg::default() });
        e.set_rec(rec.clone());
        // WP-04: the executor follows the engine's health (as `Engine::run` installs it)
        x.set_health(e.health_flags());
        e.exec = Some(x);
        let mut status = |_: &str| {};
        let mut t = 1_791_000_000_000_000_000u64;
        // the stream delivers and Tier A is complete: the warm-up gate opens (WP-04)
        e.step(Event::Slot { slot: 12, status: 0, t, parent: Some(11), dead_error: None, bank_id: None }, t, &mut status);
        t += 6_000_000;
        e.timers(t, &mut status);
        // three transactions, each moving one pool ~3% above the other: live, then paused (twice). Their groups resolve by
        // quiescence (W unknown) at the timers 4 ms later
        for (n, sol, pause) in [(0u8, 1_030u64, false), (1, 1_060, true), (2, 1_090, false)] {
            if pause { gate.shadow("control", "pause-sending by test", false).unwrap(); }
            let m = if n % 2 == 0 { &a } else { &b };
            let txn = [n + 50; 64];
            for (k, data) in [(m.vault1, vault(sol * 1_000_000_000)), (m.vault0, vault(1_000_000_000_000_000 - n as u64))] {
                t += 1_000;
                e.step(Event::Account { slot: 12, pubkey: k, owner: [3; 32], lamports: 1, data, t, txn: Some(txn), write_version: t, is_startup: false,
                    src: 0, aseq: 0, bank_id: None }, t, &mut status);
            }
            t += 4_000_000;
            e.timers(t, &mut status);
        }
        let x = e.exec.as_ref().unwrap();
        assert_eq!((n(x, "reject_gate_shadow"), x.gate_seen()), (2, Some(GateMode::Shadow)), "the live gate decided the last two");
        rec.close();
        let j = journal::read_dir(&dir).unwrap();
        let seen: Vec<(String, u64)> = j.iter().filter_map(|r| match &r.body {
            JBody::Input { kind: 3, data } if data["src"] == "decision" => Some((data["mode"].as_str().unwrap().to_string(), data["opp"].as_u64().unwrap())),
            _ => None,
        }).collect();
        assert_eq!(seen, vec![("live".to_string(), 0), ("shadow".to_string(), 1)], "one record per change, at the decision that saw it");
        // the shadow record carries the reason, and sits right after the input whose handling made the decision
        let i = j.iter().position(|r| matches!(&r.body, JBody::Input { kind: 3, data } if data["mode"] == "shadow")).unwrap();
        assert!(matches!(j[i].body, JBody::Input { ref data, .. } if data["reason"] == "control"));
        assert!(matches!(j[i - 1].body, JBody::Timer { .. }) && j[i - 1].t_engine == j[i].t_engine, "{:?}", j[i - 1]);
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// WP-04 item 8 / PLAN-ADDENDUM I-4 (the wants_send hook; WP-05's send_checks takes the same flags): the executor
    /// refuses while the engine is warming up or its state is unavailable, and says why (decisions.jsonl `reason`)
    #[tokio::test]
    async fn wants_send_refuses_unless_the_store_is_ready() {
        use crate::store_health::{HealthFlags, Shut};
        let mut r = live_rig("health").await;
        assert!(r.x.wants_send().is_some(), "an executor on its own is ready");
        let h = Arc::new(HealthFlags::default());
        r.x.set_health(h.clone());
        assert!(r.x.wants_send().is_none());
        assert_eq!((r.x.refusal().as_deref(), n(&r.x, "reject_warmup")), (Some("warmup"), 1));
        h.set(Shut::StateUnavailable);
        assert!(r.x.wants_send().is_none());
        assert_eq!((r.x.refusal().as_deref(), n(&r.x, "reject_state_unavailable")), (Some("state_unavailable"), 1));
        h.set(Shut::Ready);
        assert!(r.x.wants_send().is_some() && r.x.refusal().is_none(), "ready: allowed");
        // the gate still comes first, with its reason
        let g = SendGate::new();
        g.shadow("control", "test", false).unwrap();
        r.x.set_gate(g);
        assert!(r.x.wants_send().is_none());
        assert_eq!(r.x.refusal().as_deref(), Some("gate_shadow:control"));
    }

    /// review M10: a send deferred past the decision (the sim gate re-checks the route first) is cancelled when the
    /// SendGate closes in between: the attempt settles as not sent, nothing is fired
    #[tokio::test]
    async fn a_pause_cancels_a_deferred_send() {
        use crate::control::{self, StopInfo, StopReason};
        for stop in [false, true] {
            let (mut r, rx) = live_rig_with(if stop { "defer-stop" } else { "defer-pause" }, "sim_gate = true\n").await;
            let sess = control::Session::new();
            r.x.set_gate(sess.gate.clone());
            r.x.send(route(1, damm(3, MINT), 50_000));
            assert_eq!(n(&r.x, "live_sent"), 1, "decided and signed while the gate was open");
            assert!(attempts(&r)[0]["st"]["fired"].is_null(), "the sim gate fires later, from the task");
            // the task has not run yet (current-thread runtime): close the gate first
            if stop { sess.stopper.request(StopInfo::new(StopReason::Signal, "SIGINT")); } else { sess.gate.shadow("control", "pause-sending by test", false).unwrap(); }
            let t0 = std::time::Instant::now();
            let settled = loop {
                if let Ok(Event::Settled(s)) = rx.try_recv() { break s; }
                assert!(t0.elapsed() < std::time::Duration::from_secs(10), "no settlement");
                tokio::time::sleep(std::time::Duration::from_millis(5)).await;
            };
            assert!(settled.fired.copies.is_empty(), "nothing was fired");
            let want = if stop { "(stopped)" } else { "(shadow)" };
            assert!(settled.error.as_deref().is_some_and(|e| e.contains("send gate closed before the deferred send") && e.contains(want)), "{:?}", settled.error);
        }
    }

    /// review F8 (c): a configured crowded list that does not load stops the start, before any RPC call
    #[tokio::test]
    async fn exec_new_fails_closed_on_a_missing_crowded_file() {
        let dir = std::env::temp_dir().join(format!("arbx-exec-crowded-{}-{}", std::process::id(), now_ns()));
        let cfg = test_cfg(&dir, "/nonexistent/crowded-pools.json");
        let (tx, _rx) = crossbeam_channel::unbounded();
        let e = Exec::new(&cfg, &Rpc::race(vec![]), None, Rec::off(), tx, vec![], None, vec![]).await.err().expect("refused");
        assert!(format!("{e:#}").contains("crowded_pools_file"), "{e:#}");
    }

    #[test]
    fn fee_rule() {
        // copy 0.95x the trigger, but a failed send may cost at most a quarter of the expected profit, never below 40,000
        assert_eq!(super::fee_rule(true, Some(100_000), 1_000_000, 200_000), (95_000, "trigger"));
        assert_eq!(super::fee_rule(true, Some(10_000_000), 100_000, 200_000), (125_000, "trigger"), "capped: 25,000 lamports on 200k CU");
        assert_eq!(super::fee_rule(true, Some(1_000), 1_000_000, 200_000), (40_000, "trigger"), "floor");
        assert_eq!(super::fee_rule(false, Some(100_000), 1_000_000, 200_000), (40_000, "flat"));
        assert_eq!(super::fee_rule(true, None, 1_000_000, 200_000), (40_000, "flat"), "no trigger bid to copy");
    }
}

/// what a nexus-v2 or venue error code means, in words
pub fn meaning(code: Option<u32>, err: &Option<Value>) -> &'static str {
    match (code, err) {
        (_, None) => "ok",
        (Some(build::ERR_PROFIT), _) => "profit check: every leg ran, the round trip did not pay",
        (Some(0x4e58_0001), _) => "nexus: bad instruction data",
        (Some(0x4e58_0003), _) => "nexus: a leg program is not allowlisted",
        (Some(0x4e58_0004), _) => "nexus: an output or quote account is not a token account",
        (Some(0x4e58_0005), _) => "nexus: payer guard",
        (Some(0x4e58_0006), _) => "nexus: token guard",
        (Some(0x4e58_0007), _) => "nexus: a leg named a foreign signer",
        // arbx-exec only (program/arbx-exec REVIEW.md #8): its v2 path can return 0x4e580009 where nexus-arb-v2 gave
        // ERR_PROFIT or PrivilegeEscalation; the others come from its v3 layout
        (Some(build::arbx_v3::ERR_UNSUPPORTED), _) => "arbx-exec: a reserved v3 feature flag is set",
        (Some(build::arbx_v3::ERR_BAD_ACCOUNTS), _) => "arbx-exec: account structure (last leg not into the quote, output = input, NATIVE_OUT slot, read-only authority, or a quote/output not owned by the authority)",
        (Some(build::arbx_v3::ERR_TIP_ACCOUNT), _) => "arbx-exec: CPI tip account or System program slot wrong",
        (Some(build::arbx_v3::ERR_TIP_FUNDS), _) => "arbx-exec: the CPI tip would leave the authority below rent exemption",
        (Some(build::arbx_v3::ERR_QUOTE_NOT_WSOL), _) => "arbx-exec: COUNT_LAMPORTS or CPI_TIP needs a wSOL quote account",
        (Some(c), _) if (0x4e58_0100..0x4e58_0108).contains(&c) => "nexus: a leg delivered nothing",
        (Some(3005), _) => "anchor: not enough accounts (bin/tick arrays)",
        (Some(1), _) => "token: insufficient funds",
        (Some(_), _) => "a venue's own error (see code)",
        (None, Some(_)) => "not a program error (see err)",
    }
}

/// The compute-unit price for one attempt: 0.95x the trigger's ("trigger") or the flat 40,000 ("flat"); the priority
/// fee then capped at a quarter of the expected profit, but never below the flat floor Helius Sender requires.
pub fn fee_rule(trigger_arm: bool, trig: Option<u64>, expected_profit: i64, cu_limit: u64) -> (u64, &'static str) {
    let (want, arm) = match (trigger_arm, trig) { (true, Some(t)) => (((t as f64) * TRIGGER_SHARE) as u64, "trigger"), _ => (FLAT_CU_PRICE, "flat") };
    let cap = if cu_limit == 0 { u64::MAX } else { ((expected_profit.max(0) as f64 * MAX_FEE_SHARE_OF_PROFIT) * 1e6 / cu_limit as f64) as u64 };
    (want.min(cap).max(FLAT_CU_PRICE), arm)
}

/// The rate-queue rank of a route (`Prio::rank`; lower goes first when a send path's budget is short). WP-00 (F6): a
/// route touching a pool on the crowded list ranks last, behind every other route: 49% of our attempts went to the 21
/// pools with 150 or more bots, where we won 0.4% (PATTERNS.md item 10). Otherwise the seed pools first: source
/// "mriya", or "both" (a seed pool our registry also has; review N2: arb-lab ranked those 1).
pub fn prio_rank(buy: &Pk, sell: &Pk, buy_source: &str, sell_source: &str, crowded: &HashSet<Pk>) -> u8 {
    let seed = |s: &str| s == "mriya" || s == "both";
    if crowded.contains(buy) || crowded.contains(sell) { RANK_CROWDED }
    else if seed(buy_source) || seed(sell_source) { RANK_SEED }
    else { RANK_OTHER }
}

/// The crowded-pool list (data/crowded-pools.json): `{"pools": [{"pool": "<base58>", ...}, ...]}`, or a plain array of
/// base58 strings. Every entry must be an account key: a typo must not silently un-rank a pool.
pub fn parse_crowded_pools(text: &str) -> Result<HashSet<Pk>> {
    let v: Value = serde_json::from_str(text).context("not JSON")?;
    let list = match &v {
        Value::Array(a) => a,
        Value::Object(o) => o.get("pools").and_then(|p| p.as_array()).context("no \"pools\" array")?,
        _ => anyhow::bail!("neither a JSON object with \"pools\" nor an array"),
    };
    let mut out = HashSet::default();
    for e in list {
        let s = match e {
            Value::String(s) => s.as_str(),
            Value::Object(o) => o.get("pool").and_then(|p| p.as_str()).with_context(|| format!("entry {e} has no \"pool\""))?,
            _ => anyhow::bail!("entry {e} is not a pool"),
        };
        let k: Pk = bs58::decode(s).into_vec().ok().and_then(|b| b.try_into().ok()).with_context(|| format!("{s} is not a base58 account key"))?;
        out.insert(k);
    }
    // review N1: an empty list ranks and skips nothing; that is "no file", not a list
    anyhow::ensure!(!out.is_empty(), "no pool listed (leave [live] crowded_pools_file empty for none)");
    Ok(out)
}

pub fn load_crowded_pools(path: &str) -> Result<HashSet<Pk>> {
    let text = std::fs::read_to_string(path).with_context(|| format!("[live] crowded_pools_file {path}"))?;
    parse_crowded_pools(&text).with_context(|| format!("[live] crowded_pools_file {path}"))
}

impl Exec {
    /// Everything off the hot path: lookup tables, PumpSwap's GlobalConfig, the wallet's token accounts, the nonce.
    #[allow(clippy::too_many_arguments)]
    pub async fn new(cfg: &Config, rpc_all: &Rpc, paths: Option<Arc<Paths>>, rec: Rec, back: Sender<Event>, feeds: Vec<String>,
        send_key: Option<(Kind, ed25519_dalek::SigningKey)>, mints: Vec<(Pk, Pk)>) -> Result<(Exec, Vec<String>)> {
        let mut notes = Vec::new();
        // a configured crowded list must load, first, before any RPC call (fail closed: a missing file would silently put
        // the crowded pools back in front)
        let crowded = if cfg.live.crowded_pools_file.is_empty() { HashSet::default() } else {
            let c = load_crowded_pools(&cfg.live.crowded_pools_file)?;
            let skip = match cfg.live.crowded_skip_min_expected_lamports { 0 => String::new(), m => format!(", not sent from {m} lamports expected") };
            notes.push(format!("crowded pools: {} from {} rank last in the send queues{skip}", c.len(), cfg.live.crowded_pools_file));
            c
        };
        let rpc = rpc_all.only(&cfg.exec.rpc);
        anyhow::ensure!(!rpc.is_empty(), "[exec] rpc names {:?}: none of them is a configured, available [rpc] endpoint", cfg.exec.rpc);
        let payer = pk(&cfg.wallet);
        let alt_keys: Vec<Pk> = cfg.exec.alts.iter().map(|a| pk(a)).collect();
        let (_, accts) = rpc.accounts(&alt_keys).await.context("lookup tables")?;
        let mut alts = Vec::new();
        for (k, a) in alt_keys.iter().zip(accts) {
            match a.and_then(|a| crate::tx::parse_alt(&a.data)) { Some(addrs) => alts.push(Alt::new(*k, &addrs)), None => notes.push(format!("lookup table {} not found, skipped", b58(k))) }
        }
        let (_, g) = rpc.accounts(&[*build::PUMP_GLOBAL_CONFIG]).await.context("PumpSwap GlobalConfig")?;
        let pump = g.into_iter().next().flatten().and_then(|a| build::decode_pump_global(&a.data));
        if pump.is_none() { notes.push("PumpSwap GlobalConfig unreadable: PumpSwap legs will not build".into()); }
        // which of the pools' tokens the wallet already holds an account for: their associated token accounts, read
        // in batches (getTokenAccountsByOwner needs an index most providers refuse; this works everywhere)
        let mut cands: Vec<(Pk, Pk)> = mints.clone();
        cands.push((*WSOL, *crate::pda::TOKEN_PROGRAM));
        cands.sort(); cands.dedup();
        let atas: Vec<Pk> = cands.iter().map(|(m, p)| build::ata_of(&payer, m, p)).collect();
        let (_, accts) = rpc.accounts(&atas).await.context("wallet token accounts")?;
        let held: HashSet<Pk> = cands.iter().zip(accts).filter(|(_, a)| a.is_some()).map(|((m, _), _)| *m).collect();
        anyhow::ensure!(held.contains(&*WSOL), "wallet {} has no WSOL account: every route starts from it", cfg.wallet);
        let mut sending = None;
        if let Some((kind, key)) = send_key {
            let accts: Vec<String> = match kind { Kind::Canary => vec![cfg.canary.nonce_account.clone()], Kind::Live => cfg.live.nonce_accounts.clone() };
            let keys: Vec<Pk> = accts.iter().map(|a| pk(a)).collect();
            let (_, ns) = rpc.accounts(&keys).await.context("nonce accounts")?;
            let mut nonces = Vec::new();
            for (k, n) in keys.iter().zip(ns) {
                let n = n.with_context(|| format!("nonce account {} not found", b58(k)))?;
                anyhow::ensure!(n.data.len() >= 72 && n.data[8..40] == payer, "nonce account {}: its authority is not the wallet", b58(k));
                nonces.push(NonceSlot { acct: *k, value: build::nonce_value(&n.data), busy: None });
            }
            let (c, l) = (&cfg.canary, &cfg.live);
            let s = Sending::new(cfg, kind, key, nonces);
            notes.push(match kind {
                Kind::Canary => format!("canaries armed: {} of {} SOL, every {} ms, cap {} lamports, nonce {}", c.count, c.size_sol, c.every_ms, c.max_spend_lamports, accts.join(",")),
                Kind::Live => format!("LIVE TRADING armed: at most {} SOL a trade, stop after {} lamports of failed fees, at most {} new token accounts, {} nonce accounts",
                    l.max_size_sol, l.max_failed_fees_lamports, l.max_new_token_accounts, s.nonces.len()),
            });
            sending = Some(s);
        }
        Ok((Exec::assemble(cfg, rpc, paths, rec, back, feeds, alts, pump, held, sending, BandGate::from_cfg(cfg, crowded))?, notes))
    }

    /// The executor from what `new` fetched (or a test made up): no network here. Needs a tokio runtime.
    #[allow(clippy::too_many_arguments)]
    fn assemble(cfg: &Config, rpc: Rpc, paths: Option<Arc<Paths>>, rec: Rec, back: Sender<Event>, feeds: Vec<String>,
        alts: Vec<Alt>, pump: Option<PumpGlobal>, held: HashSet<Pk>, sending: Option<Sending>, band: BandGate) -> Result<Exec> {
        let payer = pk(&cfg.wallet);
        let min_tip_paid = cfg.sends.iter().filter(|s| s.enabled).map(|s| s.tip_lamports).max().unwrap_or(0);
        Ok(Exec { payer, program: pk(&cfg.exec.program), alts, pump, held, rpc, rt: tokio::runtime::Handle::current(), back, paths,
            cu_price: cfg.strategy.cu_price_micro, max_size: sol(cfg.exec.max_size_sol), min_tip_paid,
            sim_rate: cfg.sim.enabled.then_some(cfg.sim.max_per_sec as usize), sim_recent: VecDeque::new(),
            rec, sims_on: cfg.sim.enabled,
            sending, gate_on: cfg.gate.enabled, all_paths: cfg.live.test_all_paths, prio_cap: cfg.live.max_priority_lamports,
            spec_price: cfg.live.spec_cu_price_micro, rotate: cfg.live.rotate_paths, mix: cfg.live.race_mix, path_arm: "", bmix: cfg.live.bundle_mix, tpu_price: cfg.live.tpu_cu_price_micro, sim_gate: cfg.live.sim_gate, compete_mult: cfg.live.compete_mult, compete_share: cfg.live.compete_max_share, compete_ab: cfg.live.compete_ab, gross_floor: cfg.live.gross_floor, tpu_max_expected: cfg.live.tpu_max_expected_lamports, tpu_skip_mriya: cfg.live.tpu_skip_mriya_pools, tpu_skip_mints: cfg.live.tpu_skip_mints.iter().map(|m| pk(m)).collect(), tpu_min_expected: cfg.live.tpu_min_expected_lamports, bundle_resend_ms: cfg.live.bundle_resend_ms.clone(), bundle_variants: cfg.live.bundle_size_variants.clone(), mint_cool: HashMap::default(), pair_lock_ns: cfg.live.pair_lock_ms * 1_000_000,
            band, rot: 0,
            tiers: cfg.live.bid_tiers.then_some((cfg.live.bid_min_expected_lamports, cfg.live.bid_share, cfg.live.bid_max_priority_lamports)), next_attempt: 0, feeds, counts: HashMap::default(),
            lat: exec_lat(), gate: SendGate::new(), gate_seen: None, health: Arc::new(crate::store_health::HealthFlags::always_ready()), refused: None })
    }

    /// WP-01: follow the run's SendGate (a new Exec has its own, always live)
    pub fn set_gate(&mut self, gate: Arc<SendGate>) { self.gate = gate; }

    /// the SendGate mode the last `wants_send` read (None: it returned before reading the gate)
    pub fn gate_seen(&self) -> Option<GateMode> { self.gate_seen }

    /// WP-04: follow the engine's store health (the warm-up gate, state availability): no send unless it is ready
    pub fn set_health(&mut self, h: Arc<crate::store_health::HealthFlags>) { self.health = h; }

    /// why the last `wants_send` refused (decisions.jsonl `reason`: `gate_shadow:<reason>`, `gate_stopped`, `warmup`,
    /// `state_unavailable`, ...), None when it allowed a send
    pub fn refusal(&self) -> Option<String> { self.refused.clone() }

    /// the SendGate as it is now (`SendGate::json`)
    pub fn gate_json(&self) -> Value { self.gate.json() }

    /// the attempts still open (sent, not settled): stop.json `in_flight_at_stop` / `unsettled`
    pub fn open_attempts(&self) -> Vec<u64> {
        let mut v: Vec<u64> = self.sending.as_ref().map(|s| s.open.keys().copied().collect()).unwrap_or_default();
        v.sort_unstable();
        v
    }

    /// the tokens the wallet held an account for at boot (meta.json `wallet.held_mints_at_boot`), sorted
    pub fn held_mints(&self) -> Vec<String> {
        let mut v: Vec<String> = self.held.iter().map(b58).collect();
        v.sort();
        v
    }

    /// review N1: how many of the crowded pools this run's registry has (a list made for another registry shows here)
    pub fn crowded_in(&self, has: impl Fn(&Pk) -> bool) -> (usize, usize) {
        (self.band.crowded().iter().filter(|p| has(p)).count(), self.band.crowded().len())
    }

    fn count(&mut self, k: &'static str) { *self.counts.entry(k).or_default() += 1; }

    /// the size to simulate this decision at, if a simulation slot is free (at most max_per_sec)
    pub fn wants_sim(&mut self, size: u64) -> Option<u64> {
        let per = self.sim_rate?;
        let now = now_ns();
        while self.sim_recent.front().is_some_and(|t| now - t >= 1_000_000_000) { self.sim_recent.pop_front(); }
        if self.sim_recent.len() >= per { self.count("sim_skipped_rate"); return None; }
        self.sim_recent.push_back(now);
        Some(size.min(self.max_size))
    }

    /// the largest size the sender would send now (canary: its fixed size; live: the size cap), if it may send now
    pub fn wants_send(&mut self) -> Option<u64> {
        self.gate_seen = None;
        self.refused = Some("no_sender".into());
        self.sending.as_ref()?;
        // WP-01: paused, shadow or stopping (control socket, --shadow, program hash mismatch, a stop request). The live
        // gate, read once: the mode this decision saw is what the engine journals (`gate_seen`)
        let mode = self.gate.mode();
        self.gate_seen = Some(mode);
        if mode != GateMode::Live {
            self.count(if mode == GateMode::Stopped { "reject_gate_stopped" } else { "reject_gate_shadow" });
            self.refused = Some(if mode == GateMode::Stopped { "gate_stopped".into() } else { format!("gate_shadow:{}", self.gate.reason()) });
            return None;
        }
        // WP-04 / I-4: fail closed while the store is warming up or its state stream is unavailable (WP-05's send_checks
        // takes the same flags)
        let shut = self.health.shut();
        if shut != crate::store_health::Shut::Ready {
            self.count(if shut == crate::store_health::Shut::Warmup { "reject_warmup" } else { "reject_state_unavailable" });
            self.refused = Some(shut.as_str().into());
            return None;
        }
        let s = self.sending.as_mut()?;
        if s.stopped.is_some() { self.refused = Some("sender_stopped".into()); return None; }
        let worst = BASE_FEE + FLAT_CU_PRICE * 400_000 / 1_000_000;
        if s.spent + s.reserved + worst > s.cap {
            if s.open.is_empty() { s.stopped = Some(if s.kind == Kind::Live { "failed-fee cap reached" } else { "spend cap reached" }); }
            self.refused = Some("fee_cap".into());
            return None;
        }
        if s.kind == Kind::Canary {
            if !s.open.is_empty() || now_ns() < s.last_ns + s.every_ms * 1_000_000 { self.refused = Some("canary_wait".into()); return None; }
            if s.sent >= s.count { s.stopped = Some("count reached"); self.refused = Some("canary_count".into()); return None; }
        }
        if !s.nonces.iter().any(|n| n.busy.is_none() && n.value.is_some()) { *self.counts.entry("send_no_free_nonce").or_default() += 1; self.refused = Some("no_free_nonce".into()); return None; }
        self.refused = None;
        Some(s.size)
    }

    /// `tip_first`: the tip right after the nonce advance instead of last (Everstake wants it first; the transaction is
    /// atomic, so a failed trade still reverts it)
    fn build(&self, r: &RouteIn, min_profit: u64, nonce: Option<(Pk, [u8; 32])>, tip: Option<(Pk, u64)>, cu_price: u64, tip_first: bool, tag: u64) -> Result<Built, String> {
        let leg = |m: &PoolMeta, data: &[u8], tin: Pk, tout: Pk, live: &[i64], end: Option<i32>| build::leg(&build::LegIn {
            m, pool: data, tin, tout, amount_in: r.size, payer: self.payer, pump: self.pump.as_ref(), dlmm_live: live, dlmm_end: end });
        let l1 = leg(&r.buy, &r.buy_data, *WSOL, r.mint, &r.buy_live, r.buy_end).map_err(|e| format!("buy leg: {e}"))?;
        let l2 = leg(&r.sell, &r.sell_data, r.mint, *WSOL, &r.sell_live, r.sell_end).map_err(|e| format!("sell leg: {e}"))?;
        let quote = build::ata_of(&self.payer, &WSOL, &crate::pda::TOKEN_PROGRAM);
        let v2 = build::route_ix(self.program, self.payer, quote, r.size, min_profit, &[l1, l2])?;
        let creates_ata = !self.held.contains(&r.mint);
        // `tag` (the copy's index) makes every copy's bytes, so its signature, its own: tip-less copies would otherwise be
        // identical and a landing could not be told apart by path
        let cu_limit = r.cu + if creates_ata { ATA_CREATE_CU } else { 0 } + tag;
        let mut ixs = Vec::new();
        let mut keep = Vec::new();
        if let Some((acct, _)) = nonce { ixs.push(build::advance_nonce_ix(acct, self.payer)); keep.push(acct); keep.push(crate::tx::pk("SysvarRecentB1ockHashes11111111111111111111")); }
        if tip_first { if let Some((to, lamports)) = tip { ixs.push(build::transfer_ix(self.payer, to, lamports)); keep.push(to); } }
        ixs.push(build::cu_limit_ix(cu_limit as u32));
        if cu_price > 0 { ixs.push(build::cu_price_ix(cu_price)); }
        if creates_ata {
            let prog = if r.mint == r.buy.t0 { r.buy.t0_prog } else { r.buy.t1_prog };
            ixs.push(build::create_ata_idempotent_ix(self.payer, self.payer, r.mint, prog));
        }
        ixs.push(v2);
        if !tip_first { if let Some((to, lamports)) = tip { ixs.push(build::transfer_ix(self.payer, to, lamports)); keep.push(to); } }
        let alts: Vec<&Alt> = self.alts.iter().collect();
        let msg = build::compile_v0(self.payer, &ixs, nonce.map_or([0u8; 32], |n| n.1), &alts, &keep)?;
        let bytes = build::tx_bytes(&msg);
        if bytes > build::MAX_TX_BYTES || msg.locks > build::MAX_LOCKS { return Err(format!("oversized({bytes} bytes, {} locks)", msg.locks)); }
        Ok(Built { msg, cu_limit, creates_ata })
    }

    fn route_json(r: &RouteIn) -> Value {
        json!({ "opp": r.opp, "trigger": bs58::encode(r.trig).into_string(), "trigger_feed": r.trig_feed, "slot": r.slot,
            "buy_pool": b58(&r.buy.pool), "buy_venue": r.buy.venue, "buy_source": r.buy_source,
            "sell_pool": b58(&r.sell.pool), "sell_venue": r.sell.venue, "sell_source": r.sell_source, "mint": b58(&r.mint),
            "size_lamports": r.size, "predicted_mid": r.mid, "predicted_back": r.back, "predicted_profit": r.back as i64 - r.size as i64,
            "gross_at_opp": r.gross_at_opp, "net_at_opp": r.net_at_opp,
            // WP-04 item 10: the decision and the state version it priced
            "decision": r.decision, "sv": format!("{:016x}", r.state_version), "route_age_ms": r.route_age_ms })
    }

    /// STEP 2: build this decision's transaction and simulate it (the answer goes to sims.jsonl)
    pub fn simulate(&mut self, r: RouteIn) {
        let t0 = now_ns();
        let min_profit = (BASE_FEE + self.cu_price * r.cu / 1_000_000 + self.min_tip_paid).max(1);
        let built = self.build(&r, min_profit, None, None, self.cu_price, false, 0);
        // the same route as a canary would carry it (nonce + a tip, both static): its size
        let canary_shape = self.build(&r, min_profit, Some(([7; 32], [0; 32])), Some(([8; 32], 1_000_000)), self.cu_price, false, 0).map(|b| build::tx_bytes(&b.msg));
        let t_built = now_ns();
        let mut line = Self::route_json(&r);
        line["t_ns"] = json!(t0);
        line["build_us"] = json!((t_built - t0) / 1_000);
        line["canary_bytes"] = match &canary_shape { Ok(n) => json!(n), Err(e) => json!(e) };
        if !self.sims_on { return; }
        let rec = self.rec.clone();
        let b = match built {
            Ok(b) => b,
            Err(e) => { self.count("sim_build_failed"); line["build_error"] = json!(e); rec.json(rec::SIMS, line); return; }
        };
        self.count("sim_sent");
        line["bytes"] = json!(build::tx_bytes(&b.msg));
        line["locks"] = json!(b.msg.locks);
        line["cu_limit"] = json!(b.cu_limit);
        line["creates_ata"] = json!(b.creates_ata);
        line["min_profit"] = json!(min_profit);
        let raw = build::unsigned(&b.msg);
        let rpc = self.rpc.clone();
        self.rt.spawn(async move {
            let t = std::time::Instant::now();
            match rpc.simulate_full(&raw).await {
                Ok(s) => {
                    let code = s.err.as_ref().and_then(build::custom_code);
                    let delivered = build::delivered_from_logs(&s.logs);
                    line["sim_ms"] = json!(t.elapsed().as_secs_f64() * 1e3);
                    line["sim_slot"] = json!(s.slot);
                    line["err"] = json!(s.err);
                    line["code"] = json!(code.map(hex_code));
                    line["meaning"] = json!(meaning(code, &s.err));
                    line["encoding_ok"] = json!(s.err.is_none() || code == Some(build::ERR_PROFIT));
                    line["units"] = json!(s.units);
                    line["delivered"] = json!(delivered.iter().map(|d| d.1).collect::<Vec<_>>());
                    if s.err.is_some() && code != Some(build::ERR_PROFIT) { line["logs_tail"] = json!(s.logs.iter().rev().take(8).rev().collect::<Vec<_>>()); }
                }
                Err(e) => { line["sim_error"] = json!(format!("{e:#}")); }
            }
            rec.json(rec::SIMS, line);
        });
    }

    /// The copies of one attempt, one per path: (path, built, tip, its min_profit), the compute-unit price and fee arm,
    /// and the attempt's worst-case fee. Err = why this decision is not sent.
    #[allow(clippy::type_complexity)]
    fn copies(&mut self, r: &RouteIn, nonce: (Pk, [u8; 32])) -> Result<(Vec<(usize, Built, Option<(Pk, u64)>, u64)>, Vec<Value>, u64, &'static str, i64), &'static str> {
        let paths = self.paths.clone().ok_or("no send paths")?;
        let s = self.sending.as_ref().ok_or("no sender")?;
        let expected = r.back as i64 - r.size as i64;
        let creates_ata = !self.held.contains(&r.mint);
        if s.kind == Kind::Live {
            if expected <= 0 { return Err("live_skip_no_expected_profit"); }
            if self.mint_cool.get(&r.mint).is_some_and(|c| now_ns() < c.1) { return Err("live_skip_token_cooling"); }
            // a gap worth more than half the trade is a broken quote, not an opportunity (seen: 9.9e12 lamports)
            if expected > r.size as i64 { return Err("live_skip_implausible_gap"); }
            // one trade per pool pair at a time: a burst of triggers on one pair would otherwise race itself
            // (rotation sends one copy per trade, each under its own nonce: several on one pair can't collide)
            let now = now_ns();
            // (a bundle in flight holds no lock: a losing bundle costs nothing, Jito rejects it within ~10 ms, and each attempt has
            // its own nonce. w5h seg 14: the lock kept 108 rival-proven gaps (1.76 SOL) from being sent behind dead bundles)
            if !self.rotate && s.open.values().any(|o| !o.bundle && o.route.buy.pool == r.buy.pool && o.route.sell.pool == r.sell.pool && now.saturating_sub(o.t) < self.pair_lock_ns) { return Err("live_skip_pair_in_flight"); }
            if creates_ata && s.new_atas >= s.max_new_atas { return Err("live_skip_new_token_account_cap"); }
            // WP-00: crowded pools out of the bands from 100k, the big band throttled (its token is taken in `send`)
            self.band.check(s.kind, &r.buy.pool, &r.sell.pool, expected, now)?;
        }
        let est_cu = r.cu + if creates_ata { ATA_CREATE_CU } else { 0 };
        // the fee experiment: attempts alternate between copying the trigger's bid (0.95x) and the flat bid
        let arm_trigger = if self.mix { (self.next_attempt / 2) % 2 == 0 } else { self.next_attempt % 2 == 0 } && r.trig_cu_price.is_some();
        let all_paths = (self.all_paths || (self.mix && self.next_attempt % 2 == 0)) && !self.bmix;
        // where TPU copies can't win (fast bots' pools, outsized gaps) the trade goes as a bundle only, free when it loses
        let tpu_hopeless = (self.tpu_max_expected > 0 && expected > self.tpu_max_expected as i64)
            || (self.tpu_skip_mriya && (r.buy_source == "mriya" || r.sell_source == "mriya"))
            || self.tpu_skip_mints.contains(&r.mint)
            || (self.tpu_min_expected > 0 && expected < self.tpu_min_expected as i64);
        let bundle_arm = self.bmix && (self.next_attempt % 2 == 1 || tpu_hopeless);
        self.path_arm = if self.bmix { if bundle_arm { "bundle" } else { "tpu" } } else if !self.mix { "" } else if all_paths { "race" } else { "win" };
        let profit_basis = if s.kind == Kind::Live { expected } else { r.net_at_opp };
        let (mut cu_price, mut arm) = fee_rule(arm_trigger, r.trig_cu_price, profit_basis, est_cu);
        match (s.kind, self.tiers) {
            // two tiers: zero priority unless the gap is big enough to buy the pool's next turn
            (Kind::Live, Some((min, share, cap))) if est_cu > 0 => {
                if expected >= min as i64 {
                    let target = ((expected as f64 * share) as u64).min(cap);
                    cu_price = target.saturating_mul(1_000_000) / est_cu;
                    arm = "bid";
                } else { cu_price = self.spec_price; arm = "spec"; }
            }
            // live: an absolute cap on the priority fee too (the 25% rule trusts the expected profit, which can be wrong)
            (Kind::Live, _) if est_cu > 0 => { cu_price = cu_price.min((self.prio_cap.saturating_mul(1_000_000) / est_cu).max(FLAT_CU_PRICE)); }
            _ => {}
        }
        if s.kind == Kind::Live && self.bmix {
            // the bundle arm pays its tip only (Jito orders bundles by tip); the TPU arm a flat bid if one is set
            if bundle_arm { cu_price = 0; arm = "bundle-no-priority"; } else if self.tpu_price > 0 { cu_price = self.tpu_price; arm = "flat"; }
            // the competitive bid: just above what the pools' recent traffic pays, never past a share of the expected profit
            // (A/B: in pairs of TPU trades, one competes, one stays flat)
            let compete_turn = !self.compete_ab || (self.next_attempt / 2) % 2 == 0;
            if !bundle_arm && self.compete_mult > 0.0 && compete_turn && est_cu > 0 {
                if let Some(rp) = r.rival_cu_price {
                    let target = (rp as f64 * self.compete_mult) as u64;
                    let cap = ((expected.max(0) as f64 * self.compete_share) * 1e6 / est_cu as f64) as u64;
                    // and never past the absolute per-trade priority cap ([live] max_priority_lamports): a lost race
                    // pays it in full (2026-10-03 seg 2: one 1.94 SOL trade paid 1.3M lamports and reverted)
                    let cap_abs = self.prio_cap.saturating_mul(1_000_000) / est_cu;
                    let bid = target.min(cap).min(cap_abs).max(self.tpu_price);
                    if bid > cu_price { cu_price = bid; }
                    arm = "compete";
                }
            }
        }
        let prio = cu_price * est_cu / 1_000_000;
        let mut out = Vec::new();
        let mut not = Vec::new();
        let mut bundle_built = None;
        // rotation: one path per trade, starting from the next in turn (the bundle can't be timed: a failing one never lands)
        let n = paths.list.len();
        let order: Vec<usize> = if self.rotate && s.kind == Kind::Live { (0..n).map(|k| (self.rot + k) % n).collect() } else { (0..n).collect() };
        for i in order {
            let p = &paths.list[i];
            if self.bmix && s.kind == Kind::Live && (bundle_arm != (p.kind == SendKind::JitoBundle)) { continue; }
            if self.rotate && s.kind == Kind::Live && p.free_miss() { continue; }
            if self.rotate && s.kind == Kind::Live && !out.is_empty() { break; }
            // Helius Sender rejects a transaction without a compute-unit price: not on a zero-priority copy
            if cu_price == 0 && p.kind == SendKind::Helius { not.push(json!({ "path": p.name, "why": "zero priority (Helius Sender needs a CU price)" })); continue; }
            let (tip, min_profit) = match s.kind {
                Kind::Canary => (p.tip(r.gross_at_opp), CANARY_MIN_PROFIT),
                Kind::Live => {
                    let tip = match p.kind {
                        SendKind::Shyft | SendKind::Haan => None,
                        // the 0.001 SOL paths only when the expected profit covers that tip and the fees
                        SendKind::Bolt | SendKind::Iris | SendKind::Lunar => match p.tip(expected) {
                            Some(t) if all_paths || expected > (t.1 + BASE_FEE + prio) as i64 => Some(t),
                            _ => { not.push(json!({ "path": p.name, "why": "its 0.001 SOL tip is more than the expected profit after fees" })); continue }
                        },
                        // jito-bundle: tip_share of the expected profit within its floor and cap; helius, jito-tx: fixed
                        // a bundle's tip comes out of the profit left after the base fee (w5h seg 7: a 50% tip on a predicted
                        // 24k gross, on a real 12.6k round trip, landed at -4,447 net)
                        SendKind::JitoBundle => p.tip(expected - BASE_FEE as i64),
                        _ => p.tip(expected),
                    };
                    let mp = BASE_FEE + prio + tip.map_or(0, |t| t.1) + s.margin;
                    if expected < mp as i64 && !all_paths { not.push(json!({ "path": p.name, "why": format!("expected {expected} < this copy's min_profit {mp}") })); if p.free_miss() { bundle_built = Some(false); } continue; }
                    // on chain only the tip (+1) must be covered: the fee is paid either way, so a trade whose gross
                    // gain fell below the fees is still better completed (a smaller loss) than reverted (the whole fee)
                    // a bundle that reverts costs nothing, so it must never land at a loss: it covers its tip AND the fees
                    let chain_mp = if p.kind == SendKind::JitoBundle { tip.map_or(0, |t| t.1) + BASE_FEE + prio + 1 }
                        else if self.gross_floor { tip.map_or(0, |t| t.1) + 1 } else { mp };
                    (tip, chain_mp)
                }
            };
            match self.build(r, min_profit, Some(nonce), tip, cu_price, p.kind == SendKind::Everstake, out.len() as u64) {
                Ok(b) => { if p.free_miss() { bundle_built = Some(true); } out.push((i, b, tip, min_profit)); }
                Err(e) => { if p.free_miss() { bundle_built = Some(false); } not.push(json!({ "path": p.name, "build_error": e })); }
            }
        }
        // live with the gate on: no bundle copy, nothing for the gate to wait for, so no paid copies either (arbed's rule
        // since Run 2). With the gate off the paid copies go on their own.
        if s.kind == Kind::Live && self.gate_on && bundle_built == Some(false) { return Err("live_skip_bundle_copy_not_built"); }
        if out.is_empty() { return Err(if s.kind == Kind::Live { "live_skip_no_copy_worth_sending" } else { "canary_build_failed" }); }
        if self.rotate { self.rot = out.first().map_or(self.rot + 1, |c| c.0 + 1); }
        let worst = BASE_FEE + out.iter().map(|x| cu_price * x.1.cu_limit / 1_000_000).max().unwrap_or(0);
        Ok((out, not, cu_price, arm, worst as i64))
    }

    /// STEP 3 / 4: one attempt on this decision: a copy per path under one nonce lease. Canaries fire every copy at
    /// once (the gate would stop them); live trades go through the Jito gate.
    pub fn send(&mut self, r: RouteIn) {
        let Some(paths) = self.paths.clone() else { return };
        let Some(s) = self.sending.as_ref() else { return };
        let kind = s.kind;
        let Some(ni) = s.nonces.iter().position(|n| n.busy.is_none() && n.value.is_some()) else { return };
        let (nonce, value) = (s.nonces[ni].acct, s.nonces[ni].value.unwrap());
        let t_decided = r.st[4];
        let (copies, not, cu_price, arm, worst) = match self.copies(&r, (nonce, value)) {
            Ok(x) => x,
            Err(why) => { self.count(why); return; }
        };
        let worst = worst as u64;
        let expected = r.back as i64 - r.size as i64;
        let t_built = now_ns();
        // built: nothing below can refuse the attempt now, so a big-band one uses its token (review F5)
        self.band.commit(kind, expected, t_built);
        let attempt = self.next_attempt;
        self.next_attempt += 1;
        // the bundle arm's resends (free when they fail): Jito turned down every first bundle, sent ~15 ms after the
        // trigger (w5h seg 4: 222 of 222 would-fail), while rivals' bundles won our gaps at a median 246 ms. Each resend
        // is the same trade under the same nonce (one can land at most) with its own signature (a CU-limit tag).
        // ([live] bundle_resend_ms), and smaller copies of the trade sent with the first ([live] bundle_size_variants)
        let mut retry_built: Vec<(u64, usize, Built, Option<(Pk, u64)>, String)> = Vec::new();
        if kind == Kind::Live && self.path_arm == "bundle" {
            if let Some((i, _, tip, mp)) = copies.first() {
                for (k, d) in self.bundle_resend_ms.iter().enumerate() {
                    if let Ok(b) = self.build(&r, *mp, Some((nonce, value)), *tip, cu_price, false, 100 + k as u64) { retry_built.push((*d, *i, b, *tip, format!("resend +{d}ms"))); }
                }
                for (k, f) in self.bundle_variants.iter().enumerate() {
                    let size = (r.size as f64 * f) as u64;
                    if size < 5_000_000 || size >= r.size { continue; }
                    let mut rv = r.clone();
                    rv.size = size;
                    let tip_v = paths.list[*i].tip((expected as f64 * f) as i64 - BASE_FEE as i64);
                    let mp_v = tip_v.map_or(0, |t| t.1) + BASE_FEE + cu_price * r.cu / 1_000_000 + 1;
                    if let Ok(b) = self.build(&rv, mp_v, Some((nonce, value)), tip_v, cu_price, false, 200 + k as u64) { retry_built.push((0, *i, b, tip_v, format!("size x{f}"))); }
                }
            }
        }
        let s = self.sending.as_mut().unwrap();
        let signed: Vec<Copy> = copies.iter().map(|(i, b, tip, _)| Copy { path: *i, raw: Arc::new(build::sign(&b.msg, &s.key)), tip: *tip }).collect();
        let retries: Vec<(u64, Copy)> = retry_built.iter().map(|(d, i, b, tip, _)| (*d, Copy { path: *i, raw: Arc::new(build::sign(&b.msg, &s.key)), tip: *tip })).collect();
        let t_signed = now_ns();
        s.sent += 1;
        s.last_ns = t_signed;
        s.reserved += worst;
        s.nonces[ni].busy = Some(attempt);
        for x in signed.iter().chain(retries.iter().map(|r| &r.1)) {
            if let Some(sig) = send::first_signature(&x.raw).as_deref().and_then(sig64) { s.watch.insert(sig, (attempt, x.path)); }
        }
        let settle = std::time::Duration::from_secs(s.settle_s);
        let margin = s.margin;
        // the rate-queue rank: a crowded pool on the route queues behind everything else (WP-00, F6); then seed pools first
        let rank = prio_rank(&r.buy.pool, &r.sell.pool, r.buy_source, r.sell_source, self.band.crowded());
        let crowded = rank == RANK_CROWDED;
        let prio = Prio { rank, net: expected };
        // the TPU arm's pre-send simulation: the first copy, exactly as signed
        let gate_raw = if self.sim_gate && kind == Kind::Live && self.path_arm != "bundle" { signed.first().map(|c| c.raw.clone()) } else { None };
        // the gate's bar: the full fees + tip + margin on the simulated round trip (the chain floor may be lower: see
        // gross_floor), and what we predicted per leg, to log where a slip happened
        let gate_bar = copies.first().map(|c| BASE_FEE + cu_price * c.1.cu_limit / 1_000_000 + c.2.map_or(0, |t| t.1) + margin).unwrap_or(0);
        let live = kind == Kind::Live;
        // fire first, then record (WP-00, F44): nothing (the attempt line's formatting, write and flush) sits between
        // signing and firing. With the sim gate the copies fire later, from the task below (`fired` stays null).
        // `fired` = handed to the runtime (`fire` spawns; review F11): the bytes leave later (copies.jsonl `t_sent`,
        // the `signed_to_sent` series)
        let fire_now = if gate_raw.is_none() { Some(paths.fire(attempt, signed.clone(), prio, live)) } else { None };
        let t_fired = fire_now.as_ref().map(|_| now_ns());
        let retry_labels: Vec<String> = retry_built.iter().map(|x| x.4.clone()).collect();
        let cu_limit = copies.iter().map(|c| c.1.cu_limit).max().unwrap_or(0);
        let creates_ata = copies.first().is_some_and(|c| c.1.creates_ata);
        let mut line = Self::route_json(&r);
        line["attempt"] = json!(attempt);
        line["kind"] = json!(kind);
        line["t_ns"] = json!(t_signed);
        line["expected_profit"] = json!(expected);
        line["cu_limit"] = json!(cu_limit);
        line["fee_arm"] = json!(arm);
        if !self.path_arm.is_empty() { line["path_arm"] = json!(self.path_arm); }
        line["trigger_cu_price_micro"] = json!(r.trig_cu_price);
        line["rival_cu_price_micro"] = json!(r.rival_cu_price);
        line["cu_price_micro"] = json!(cu_price);
        line["priority_fee_lamports"] = json!(cu_price * cu_limit / 1_000_000);
        line["worst_fee_lamports"] = json!(worst);
        line["creates_token_account"] = json!(creates_ata);
        line["crowded"] = json!(crowded);
        line["queue_rank"] = json!(rank);
        line["nonce"] = json!({ "account": b58(&nonce), "value": bs58::encode(value).into_string() });
        // state triggers: rx = the pool update's receive time, engine = its dequeue (WP-00, F13); fired = handed to the
        // send paths (null: the sim gate fires later)
        line["st"] = json!({ "rx": r.st[0], "decoded": r.st[1], "engine": r.st[2], "resolved": r.st[3], "decided": t_decided, "built": t_built, "signed": t_signed, "fired": t_fired });
        line["copies"] = json!(signed.iter().zip(&copies).map(|(x, c)| json!({ "path": paths.list[x.path].name, "sig": send::first_signature(&x.raw), "bytes": x.raw.len(),
            "tip": x.tip.map(|t| t.1), "min_profit": c.3 })).collect::<Vec<_>>());
        if !not.is_empty() { line["not_sent"] = json!(not); }
        if !retries.is_empty() { line["bundle_resends"] = json!(retries.iter().zip(&retry_labels).map(|((d, x), l)| json!({ "after_ms": d, "what": l, "sig": send::first_signature(&x.raw), "tip": x.tip.map(|t| t.1) })).collect::<Vec<_>>()); }
        self.rec.json(rec::ATTEMPTS, line);
        self.count(if live { "live_sent" } else { "canary_sent" });
        if crowded { self.count("rank_crowded"); }
        self.lat[LAT_DECIDED_TO_SIGNED].push(t_signed.saturating_sub(t_decided));
        if let Some(t) = t_fired { self.lat[LAT_SIGNED_TO_FIRED].push(t.saturating_sub(t_signed)); }
        let (gate_size, gate_mid, gate_back, gate_slot) = (r.size, r.mid, r.back, r.slot);
        // WP-03b: the route's pools, for the chain-fetch tap after each firing below
        let pools = [r.buy.pool, r.sell.pool];
        let bundle = self.path_arm == "bundle";
        if let Some(s) = self.sending.as_mut() { s.open.insert(attempt, Open { route: r, nonce: ni, worst, creates_ata, expected, t: t_signed, bundle }); }
        let (rpc, back, paths2, gate, log) = (self.rpc.clone(), self.back.clone(), paths.clone(), self.gate.clone(), self.rec.clone());
        self.rt.spawn(async move {
            if let Some(raw) = gate_raw {
                let t0 = now_ns();
                // the RPC can be behind the trigger (w5h seg 4: the short leg was the trigger's own pool in 40 of 46
                // gated trades, often with no rival move in between): a failed check is re-run at +30 and +90 ms, and
                // the trade goes if one passes. Every check's slot is logged, to see how far behind the RPC was.
                let mut slots = Vec::new();
                let mut fail = None;
                for (k, wait) in [0u64, 30, 60].into_iter().enumerate() {
                    if wait > 0 { tokio::time::sleep(std::time::Duration::from_millis(wait)).await; }
                    let Ok(sim) = rpc.simulate_full(&raw).await else { fail = None; break };
                    slots.push(sim.slot);
                    let legs = build::delivered_from_logs(&sim.logs);
                    let back_sim = legs.last().map(|x| x.1);
                    let thin = sim.err.is_none() && back_sim.is_some_and(|b| (b as i64 - gate_size as i64) < gate_bar as i64);
                    if sim.err.is_none() && !thin {
                        if k > 0 { log.log("send", format!("gate: attempt {attempt} passed on re-check {k} at +{:.0} ms (sim slots {slots:?})", (now_ns() - t0) as f64 / 1e6)); }
                        fail = None;
                        break;
                    }
                    // a check from before the trigger's slot (the RPC is behind: w5h seg 5, 13 of 16 gated checks ran a
                    // slot behind the trigger, still behind at +90 ms) priced the pools without the trigger: its "gap gone"
                    // says nothing about this trade, which goes on our own quote
                    if sim.slot < gate_slot {
                        log.log("send", format!("gate: attempt {attempt} sim stale (slot {} < trigger {gate_slot}, check {k}): sent on our quote", sim.slot));
                        fail = None;
                        break;
                    }
                    let why = match &sim.err { Some(err) => build::custom_code(err).map_or(err.to_string(), |c| format!("0x{c:x}")), None => format!("thin: gross {} < bar {gate_bar}", back_sim.unwrap_or(0) as i64 - gate_size as i64) };
                    fail = Some(format!("{why} | legs {:?} predicted [{gate_mid}, {gate_back}]", legs.iter().map(|x| x.1).collect::<Vec<_>>()));
                }
                if let Some(f) = fail {
                    let msg = format!("sim_gated after {:.1} ms: {f} | sim slots {slots:?}", (now_ns() - t0) as f64 / 1e6);
                    let _ = back.send(Event::Settled(Box::new(Settled { attempt, fired: Fired { id: attempt, t_ns: 0, copies: vec![], gate: None },
                        landed: None, jito: None, nonce_value: None, error: Some(msg) })));
                    return;
                }
            }
            // review M10: a send deferred past the decision (the sim gate's re-checks) still asks the SendGate: a pause,
            // shadow or stop that came in meanwhile cancels it
            if fire_now.is_none() && !gate.allows() {
                let _ = back.send(Event::Settled(Box::new(Settled { attempt, fired: Fired { id: attempt, t_ns: 0, copies: vec![], gate: None },
                    landed: None, jito: None, nonce_value: None, error: Some(format!("not sent: the send gate closed before the deferred send ({})", gate.mode().as_str())) })));
                return;
            }
            let fire = match fire_now { Some(f) => f, None => paths2.fire(attempt, signed, prio, live) };
            let fired = match fire.await { Ok(f) => f, Err(e) => { let _ = back.send(Event::Settled(Box::new(Settled { attempt, fired: Fired { id: attempt, t_ns: 0, copies: vec![], gate: None },
                landed: None, jito: None, nonce_value: None, error: Some(e.to_string()) }))); return; } };
            let mut fired = fired;
            // WP-03b tap, after the firing: the signatures of the copies that left (wallet source (b): watched until a status
            // shows them landed) and the route's pools (backfill priority 0); nothing for copies the gate kept back
            crate::chainfetch::note_fired(attempt, &fired.copies, &pools);
            // the bundle resends, on their schedule after the first send
            let t_fire = std::time::Instant::now();
            for (delay, c) in retries {
                let d = std::time::Duration::from_millis(delay);
                let el = t_fire.elapsed();
                if d > el { tokio::time::sleep(d - el).await; }
                // review M10: no scheduled resend after a pause, shadow or stop
                if !gate.allows() { break; }
                if let Ok(f2) = paths2.fire(attempt, vec![c], prio, live).await {
                    crate::chainfetch::note_fired(attempt, &f2.copies, &pools);
                    fired.copies.extend(f2.copies);
                }
            }
            // a gate skip sent only the bundle, which Jito already rejected: nothing can land, so the nonce lease ends now
            let gated = fired.gate.as_ref().is_some_and(|g| matches!(g.decision, send::Decision::Gated | send::Decision::GatedNoBundle));
            tokio::time::sleep(if gated { std::time::Duration::from_millis(300) } else { settle }).await;
            let mut s = Settled { attempt, fired, landed: None, jito: None, nonce_value: None, error: None };
            let sigs: Vec<(usize, [u8; 64], String)> = s.fired.copies.iter().enumerate().filter_map(|(i, c)| {
                let sg = c.sig.clone()?;
                Some((i, sig64(&sg)?, sg))
            }).collect();
            match rpc.statuses(&sigs.iter().map(|x| x.1).collect::<Vec<_>>()).await {
                Ok(st) => {
                    if let Some(((i, _, sg), Some((slot, _)))) = sigs.iter().zip(st).find(|(_, v)| v.is_some()) {
                        let path = paths2.index(&s.fired.copies[*i].path).unwrap_or(usize::MAX);
                        let mut tx = Value::Null;
                        for _ in 0..5 { if let Ok(Some(t)) = rpc.transaction(sg).await { tx = t; break; } tokio::time::sleep(std::time::Duration::from_secs(2)).await; }
                        s.landed = Some((path, sg.clone(), slot, tx));
                    }
                }
                Err(e) => s.error = Some(format!("statuses: {e:#}")),
            }
            for c in &s.fired.copies {
                if let (Some(j), Some(sig)) = (paths2.list.iter().find(|p| p.name == c.path).and_then(|p| p.jito.clone()), &c.sig) {
                    s.jito = j.verdict(sig, tokio::time::Instant::now()).await;
                }
            }
            if let Ok((_, v)) = rpc.accounts(&[nonce]).await { s.nonce_value = v.into_iter().next().flatten().and_then(|a| build::nonce_value(&a.data)); }
            let _ = back.send(Event::Settled(Box::new(s)));
        });
    }

    /// one of our own copies (a pool move by our own trade is not a trigger)
    pub fn is_ours(&self, sig: &[u8; 64]) -> bool { self.sending.as_ref().is_some_and(|c| c.watch.contains_key(sig)) }

    /// a feed delivered a transaction: note it if it is one of our open copies
    pub fn on_arrival(&mut self, sig: &[u8; 64], feed: u16, t: u64) {
        let Some(c) = self.sending.as_mut() else { return };
        if !c.watch.contains_key(sig) { return; }
        let e = c.seen.entry(*sig).or_insert((t, feed, Vec::new()));
        if t < e.0 { e.0 = t; e.1 = feed; }
        if !e.2.iter().any(|x| x.0 == feed) { e.2.push((feed, t)); }
    }

    /// the attempt's outcome, from chain plus what our own feeds saw, written once (outcomes.jsonl)
    pub fn on_settled(&mut self, s: Settled, poh: &dyn Fn(&[u8; 64]) -> Option<crate::feeds::entries::Poh>) {
        // the token cool-down: 25 Jito rejections in a row (no accept, no landing) pause the token 60 s, doubling per
        // pause up to 5 min; an accepted or landed bundle clears it
        if let Some(mint) = self.sending.as_ref().and_then(|c| c.open.get(&s.attempt)).map(|o| o.route.mint) {
            let e = self.mint_cool.entry(mint).or_insert((0, 0, 0));
            match (s.landed.is_some(), s.jito.as_ref().map(|o| o.outcome)) {
                (true, _) | (_, Some("accepted")) | (_, Some("landed")) => { *e = (0, 0, 0); }
                (false, Some("would-fail")) => {
                    e.0 += 1;
                    if e.0 >= 25 {
                        let secs = (60u64 << e.2.min(3)).min(300);
                        e.1 = now_ns() + secs * 1_000_000_000; e.0 = 0; e.2 += 1;
                        self.rec.log("send", format!("cool: token {} paused {secs} s after 25 Jito rejections in a row (pause {})", b58(&mint), e.2));
                    }
                }
                _ => {}
            }
        }
        let feeds = self.feeds.clone();
        let paths = self.paths.clone();
        let Some(c) = self.sending.as_mut() else { return };
        let Some(o) = c.open.remove(&s.attempt) else { return };
        let spent_before = c.spent;
        // signed -> the first copy's send task running (its t_sent; 0 = never sent): the send baseline (review F11)
        if let Some(x) = s.fired.copies.first().filter(|x| x.t_sent > 0) { self.lat[LAT_SIGNED_TO_SENT].push(x.t_sent.saturating_sub(o.t)); }
        let route = o.route;
        c.reserved = c.reserved.saturating_sub(o.worst);
        let slot_n = &mut c.nonces[o.nonce];
        slot_n.busy = None;
        if let Some(v) = s.nonce_value { slot_n.value = Some(v); }
        let mut new_mint = None;
        let mut line = json!({ "attempt": s.attempt, "kind": c.kind, "t_ns": now_ns(), "opp": route.opp, "trigger": bs58::encode(route.trig).into_string(),
            "trigger_slot": route.slot, "expected_profit": o.expected, "gate": s.fired.gate });
        let feed = |f: u16| feeds.get(f as usize).cloned().unwrap_or_default();
        let mut copies = Vec::new();
        for x in &s.fired.copies {
            let b: Option<[u8; 64]> = x.sig.as_ref().and_then(|sg| bs58::decode(sg).into_vec().ok()).and_then(|v| v.try_into().ok());
            let seen = b.and_then(|b| c.seen.get(&b));
            copies.push(json!({ "path": x.path, "sig": x.sig, "accepted": x.ok, "status": x.status, "t_sent": x.t_sent,
                "seen_first_ns": seen.map(|v| v.0), "seen_first_feed": seen.map(|v| feed(v.1)),
                "send_to_seen_ms": seen.filter(|_| x.t_sent > 0).map(|v| (v.0 as f64 - x.t_sent as f64) / 1e6) }));
        }
        line["copies"] = json!(copies);
        match &s.landed {
            Some((path, sig, slot, tx)) => {
                c.landed += 1;
                let meta = &tx["meta"];
                let fee = meta["fee"].as_u64().unwrap_or(0);
                let err = if meta["err"].is_null() { None } else { Some(meta["err"].clone()) };
                if tx.is_null() { c.spent += o.worst; } else if err.is_some() { c.spent += fee; }
                c.fees += fee;
                let code = err.as_ref().and_then(build::custom_code);
                // real profit from the chain: the wallet's lamports plus its WSOL account, after minus before
                let keys: Vec<String> = tx["transaction"]["message"]["accountKeys"].as_array().map(|a| a.iter().filter_map(|k| k.as_str().map(String::from)).collect()).unwrap_or_default();
                let me = b58(&self.payer);
                let lamports = keys.iter().position(|k| *k == me).map(|i| meta["postBalances"][i].as_i64().unwrap_or(0) - meta["preBalances"][i].as_i64().unwrap_or(0));
                let wsol = |side: &str| meta[side].as_array().into_iter().flatten()
                    .filter(|b| b["owner"].as_str() == Some(me.as_str()) && b["mint"].as_str() == Some(&b58(&WSOL)))
                    .map(|b| b["uiTokenAmount"]["amount"].as_str().and_then(|a| a.parse::<i64>().ok()).unwrap_or(0)).sum::<i64>();
                let profit = lamports.map(|l| l + wsol("postTokenBalances") - wsol("preTokenBalances"));
                let b: Option<[u8; 64]> = bs58::decode(sig).into_vec().ok().and_then(|v| v.try_into().ok());
                let seen = b.and_then(|b| c.seen.get(&b));
                let sent = s.fired.copies.iter().find(|x| x.sig.as_deref() == Some(sig.as_str()));
                line["landed"] = json!(paths.as_ref().and_then(|p| p.list.get(*path)).map(|p| p.name.clone()));
                line["sig"] = json!(sig);
                line["slot"] = json!(slot);
                line["slots_after_trigger"] = json!(*slot as i64 - route.slot as i64);
                line["ok"] = json!(err.is_none());
                line["err"] = json!(err);
                line["code"] = json!(code.map(hex_code));
                line["meaning"] = json!(meaning(code, &err));
                line["fee_lamports"] = json!(fee);
                let tip_paid = if err.is_none() && !tx.is_null() { sent.map_or(0, |x| x.tip_lamports) } else { 0 };
                if err.is_none() && !tx.is_null() {
                    c.wins += 1;
                    c.tips += tip_paid;
                    c.profit += profit.unwrap_or(0);
                    if o.creates_ata { c.new_atas += 1; new_mint = Some(route.mint); }
                }
                line["tip_paid_lamports"] = json!(tip_paid);
                line["profit_lamports"] = json!(profit);
                line["profit_vs_expected"] = json!(profit.map(|p| p - o.expected));
                // what each leg really delivered on chain (the program's NXV2OUT logs, kept in failed transactions too):
                // the round trip's real result against our prediction at the moment it executed
                let logs: Vec<String> = meta["logMessages"].as_array().map(|a| a.iter().filter_map(|l| l.as_str().map(String::from)).collect()).unwrap_or_default();
                let got = build::delivered_from_logs(&logs);
                line["delivered"] = json!(got.iter().map(|d| d.1).collect::<Vec<_>>());
                line["predicted"] = json!([route.mid, route.back]);
                if let Some(&(_, back)) = got.iter().find(|d| d.0 == 1) {
                    line["round_trip_on_chain"] = json!(back as i64 - route.size as i64);
                    line["round_trip_predicted"] = json!(route.back as i64 - route.size as i64);
                }
                line["send_to_seen_ms"] = json!(seen.zip(sent).filter(|(_, x)| x.t_sent > 0).map(|(v, x)| (v.0 as f64 - x.t_sent as f64) / 1e6));
                line["seen_by"] = json!(seen.map(|v| v.2.iter().map(|(f, t)| (feed(*f), json!(t))).collect::<serde_json::Map<_, _>>()));
            }
            None => { line["landed"] = Value::Null; }
        }
        // on the leaders' PoH clocks: when the trigger ran and how long after it OUR transaction ran (the proof of how
        // late we reach the leader, independent of network clocks)
        let tp = poh(&route.trig);
        let op = s.landed.as_ref().and_then(|(_, sg, _, _)| sig64(sg)).and_then(|b| poh(&b));
        line["poh"] = json!({ "trigger": tp.map(|p| json!({ "slot": p.slot, "ms_in_slot": p.ms(), "ticks": p.ticks })),
            "ours": op.map(|p| json!({ "slot": p.slot, "ms_in_slot": p.ms(), "ticks": p.ticks })),
            "ours_ms_after_trigger": op.zip(tp).and_then(|(a, b)| a.ms_after(&b)) });
        line["jito"] = json!(s.jito);
        line["settle_error"] = json!(s.error);
        // status.jsonl v2 counter semantics (MEASUREMENT §2.2): the running total after this attempt, and this attempt's part
        line["failed_fees_total_lamports"] = json!(c.spent);
        line["failed_fees_delta_lamports"] = json!(c.spent - spent_before);
        line["cap_lamports"] = json!(c.cap);
        line["run_profit_lamports"] = json!(c.profit);
        for x in &s.fired.copies {
            if let Some(b) = x.sig.as_ref().and_then(|sg| bs58::decode(sg).into_vec().ok()).and_then(|v| <[u8; 64]>::try_from(v).ok()) { c.watch.remove(&b); c.seen.remove(&b); }
        }
        self.rec.json(rec::OUTCOMES, line);
        if let Some(m) = new_mint { self.held.insert(m); }
    }

    /// for status.jsonl: counters, spend so far against the cap
    pub fn status(&self) -> Value {
        let mut v = json!({ "counts": self.counts });
        // sends refused for the paths' rates, split by the crowded rank (WP-00, F6), totals
        if let Some(p) = &self.paths {
            let (mut all, mut crowded) = (0u64, 0u64);
            for x in &p.list { let st = x.stats.lock().unwrap(); all += st.limited; crowded += st.limited_crowded; }
            v["over_rate"] = json!({ "crowded": crowded, "other": all.saturating_sub(crowded) });
        }
        if let Some(c) = &self.sending {
            v["sending"] = json!({ "kind": c.kind, "sent": c.sent, "landed": c.landed, "wins": c.wins, "in_flight": c.open.len(),
                "failed_fees_total_lamports": c.spent, "cap_lamports": c.cap, "fees_lamports": c.fees, "tips_lamports": c.tips, "profit_lamports": c.profit,
                "new_token_accounts": c.new_atas, "stopped": c.stopped });
        }
        v
    }

    /// status.jsonl v2 (MEASUREMENT §4.8, §2.2): the `exec` section and the `money` section, deltas against `prev`.
    /// `money` holds the bot's own counters until WP-07's ledger (`src: "bot"`; null without a sender). Every number is
    /// `_total`, `_delta` or `_now`
    pub fn status_v2(&self, prev: &mut ExecPrev) -> (Value, Value) {
        let mut counts_delta = serde_json::Map::new();
        for (k, v) in &self.counts {
            let d = v - prev.counts.get(k).copied().unwrap_or(0);
            if d > 0 { counts_delta.insert(k.to_string(), json!(d)); }
        }
        prev.counts = self.counts.clone();
        // every block-engine result so far, by outcome (the jito paths' result streams)
        let mut verdicts: std::collections::BTreeMap<&'static str, u64> = Default::default();
        if let Some(p) = &self.paths {
            for x in p.list.iter().filter_map(|x| x.jito.as_ref()) { for (k, v) in x.counts.lock().unwrap().iter() { *verdicts.entry(k).or_default() += v; } }
        }
        let verdicts_delta: serde_json::Map<String, Value> = verdicts.iter().filter_map(|(k, v)| {
            let d = v - prev.verdicts.get(k).copied().unwrap_or(0);
            (d > 0).then(|| (k.to_string(), json!(d)))
        }).collect();
        prev.verdicts = verdicts;
        let over_rate = self.paths.as_ref().map(|p| {
            let (mut all, mut crowded) = (0u64, 0u64);
            for x in &p.list { let st = x.stats.lock().unwrap(); all += st.limited; crowded += st.limited_crowded; }
            json!({ "crowded": crowded, "other": all.saturating_sub(crowded) })
        });
        let mut exec = json!({ "counts_total": self.counts, "counts_delta": counts_delta, "verdicts_delta": verdicts_delta, "over_rate_total": over_rate,
            // WP-05's send policy fills these
            "decisions_total": null, "refused_total": null, "queue_now": null, "lambda_now": null });
        let money = match &self.sending {
            Some(c) => {
                exec["kind"] = json!(c.kind);
                exec["stopped"] = json!(c.stopped);
                exec["attempts_total"] = json!(c.sent);
                exec["attempts_delta"] = json!(c.sent as u64 - prev.attempts);
                exec["landed_total"] = json!(c.landed);
                exec["landed_delta"] = json!(c.landed as u64 - prev.landed);
                exec["ok_total"] = json!(c.wins);
                exec["in_flight_now"] = json!(c.open.len());
                let m = json!({ "src": "bot", "failed_fees_total_lamports": c.spent, "failed_fees_delta_lamports": c.spent - prev.spent.min(c.spent),
                    "failed_fees_cap_now_lamports": c.cap, "fees_landed_total_lamports": c.fees, "tips_paid_total_lamports": c.tips,
                    // v1 `profit_lamports`: chain balance changes of winning landings, rent included (WP-07's ledger separates it)
                    "bot_profit_total_lamports": c.profit, "new_token_accounts_total": c.new_atas });
                prev.attempts = c.sent as u64;
                prev.landed = c.landed as u64;
                prev.spent = c.spent;
                m
            }
            None => Value::Null,
        };
        (exec, money)
    }

    pub fn payer(&self) -> Pk { self.payer }
}

/// What `Exec::status_v2`'s deltas are against (the previous status line)
#[derive(Default)]
pub struct ExecPrev { counts: HashMap<&'static str, u64>, verdicts: std::collections::BTreeMap<&'static str, u64>, attempts: u64, landed: u64, spent: u64 }

//! snipe_engine — a long-running "warm" pump.fun sniper ENGINE that reuses the arb bot's WARM send path.
//!
//! WHY: the earlier COLD one-shot (`snipe_fire`) measured send->land at 2-4 slots. That is cold-start latency
//! (a fresh QUIC handshake to the leader on every fire), NOT the bot's real same-slot capability. The arb bot
//! lands same-slot because it keeps the `tpu` send path WARM: pre-opened QUIC to the upcoming leaders plus a
//! continuous leader-schedule / cluster-node refresh (src/send/tpu.rs `keep_warm`). This binary runs that warm
//! loop continuously, waits until the path is demonstrably HOT, and only THEN fires — so each send uses an
//! already-open QUIC stream, not a cold connect. It then reports the true steady-state send->land slot delta.
//!
//! SAFETY (hard):
//!  * Default-safe: no real token buys ever. Real buys need BOTH `--live` and `--max-sol <cap>` and a `--mint`.
//!  * The `--warm-probe` latency probe fires tiny 1-lamport SELF-transfers (recent blockhash, no nonce) through
//!    the warm path. It still transmits, so it is gated by `--live` + `--max-sol` too. Spend is capped hard:
//!    `--max-sends N` (default 20) and a per-send cost estimate; it refuses the next send once cumulative spend
//!    (base fee + any priority fee + the 1-lamport transfer) would exceed `--max-sol`.
//!  * This binary NEVER touches /root/arbx (the live deploy) and runs no arb campaign.
//!
//! Modes:
//!   --warm-probe   create the send path, keep its warm loop alive, WAIT until hot, then fire capped 1-lamport
//!                  self-transfers and log send_slot / land_slot / delta / wall_ms. THE key measurement.
//!   --shadow       start the shred feed + pump detector (needs [[feed]] in the config), log each launch; with
//!                  --warm-probe-on-trigger, fire one capped self-transfer per launch to measure trigger->land.
//!   --live         real buy on a filtered launch (dev_buy>0) via buy_message_ixs through the warm path. GATED.
//!
//! Usage (the key run):
//!   snipe_engine --warm-probe --config probe_tpu.toml --env-file /root/arbx/deploy/.env \
//!                --send-path tpu-direct --max-sends 20 --max-sol 0.003 --live  < /root/.nexus-...wallet.pass
//!
//! probe config (minimal; unknown fields ignored so the live schema can't break it):
//!   wallet          = "<expected pubkey>"        # verified against the keystore
//!   wallet_keystore = "/path/keystore.enc"       # v3 keystore, passphrase from stdin
//!   rpc_url         = "https://.../?api-key=${CONSTANTK_TOKEN}"  # blockhash + slot + status polling (${} expanded)
//!   [[send]] name=.. kind=.. url=.. ...          # the warm path(s); e.g. tpu-direct (kind="tpu")
//!   [[feed]] ...                                 # only for --shadow

use anyhow::{bail, Context, Result};
use arbx::snipe::{self, Launch};
use arbx::snipe_build::{self, BuyPlan};
use arbx::tx::{b58, pk, Pk};
use arbx::{build, config, pda, rpc, send, wallet};
use base64::Engine as _;
use ed25519_dalek::SigningKey;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::{Duration, Instant};

/// --sell-path: the path SELLS go through (default: the buy path). Helius Sender rate-limited our sells (HTTP 429).
static SELL_PATH: std::sync::OnceLock<Arc<send::Path>> = std::sync::OnceLock::new();
fn sp(p: &Arc<send::Path>) -> &Arc<send::Path> { SELL_PATH.get().unwrap_or(p) }
/// --also-send: a second path every BUY goes through too (same signed tx, both tips). Not used for sells.
static ALSO_PATH: std::sync::OnceLock<Arc<send::Path>> = std::sync::OnceLock::new();
/// --fallback-path: a TIPLESS path a refused send (429 / over-rate) is re-sent through (DET 2026-10-18; default off).
static FALLBACK_PATH: std::sync::OnceLock<Arc<send::Path>> = std::sync::OnceLock::new();
/// latest blockhash kept fresh in the background (hash, fetched-at), so a buy never waits on getLatestBlockhash.
static BLOCKHASH_CACHE: std::sync::Mutex<Option<([u8; 32], Instant)>> = std::sync::Mutex::new(None);

fn arg(flag: &str) -> Option<String> {
    let a: Vec<String> = std::env::args().collect();
    a.iter().position(|x| x == flag).and_then(|i| a.get(i + 1).cloned())
}
fn has(flag: &str) -> bool { std::env::args().any(|x| x == flag) }
fn arg_u64(flag: &str, default: u64) -> u64 { arg(flag).and_then(|s| s.parse().ok()).unwrap_or(default) }
fn arg_u64_opt(flag: &str) -> Option<u64> { arg(flag).and_then(|s| s.parse().ok()) }
fn arg_f64(flag: &str, default: f64) -> f64 { arg(flag).and_then(|s| s.parse().ok()).unwrap_or(default) }
fn arg_pk(flag: &str) -> Option<Pk> { arg(flag).map(|s| pk(&s)) }

/// minimal probe config — NOT the full arb schema; unknown fields are ignored on purpose.
#[derive(Default, serde::Deserialize)]
struct Probe {
    #[serde(default)] wallet: Option<String>,
    #[serde(default)] wallet_keystore: Option<String>,
    #[serde(default)] rpc_url: Option<String>,
    #[serde(rename = "send", default)] sends: Vec<config::SendPath>,
    #[serde(rename = "feed", default)] feeds: Vec<config::Feed>,
}

/// unlock the keystore named in the probe config (passphrase from stdin/tty), verifying against `expect`.
fn keystore_key(path: &str, expect: Option<&str>) -> Result<SigningKey> {
    wallet::harden_process();
    let blob = std::fs::read_to_string(path).with_context(|| format!("reading {path}"))?;
    let pass = wallet::read_pass()?;
    let key = wallet::keypair(&wallet::decrypt(&blob, pass.as_bytes())?)?;
    let got = b58(&key.verifying_key().to_bytes());
    if let Some(w) = expect {
        if got != w { bail!("{path} holds {got}, but the config's wallet is {w}"); }
    }
    Ok(key)
}

/// percentiles of a slice (q in [0,1]); NaN when empty.
fn pct(v: &mut [f64], q: f64) -> f64 {
    if v.is_empty() { return f64::NAN; }
    v.sort_by(|a, b| a.partial_cmp(b).unwrap());
    v[(((v.len() - 1) as f64) * q).round() as usize]
}

/// one fired probe's outcome.
struct Shot { send_slot: u64, land_slot: Option<u64>, ok: bool, wall_ms: f64, to: String, create_slot: Option<u64>, internal_ms: f64, poh_ms: f64, close: bool }

/// Per-mint de-dup so running MULTIPLE feeds (erpc + Kaldera) for coverage never processes the same create twice
/// (first feed to deliver a mint wins; the other feed's copy is dropped). Ring-buffered so memory stays bounded.
struct MintDedup { seen: std::collections::HashSet<Pk>, order: std::collections::VecDeque<Pk>, cap: usize }
impl MintDedup {
    fn new(cap: usize) -> Self { Self { seen: std::collections::HashSet::new(), order: std::collections::VecDeque::new(), cap } }
    /// true the FIRST time a mint is seen; false if already seen (skip the duplicate).
    fn first(&mut self, mint: Pk) -> bool {
        if !self.seen.insert(mint) { return false; }
        self.order.push_back(mint);
        if self.order.len() > self.cap { if let Some(old) = self.order.pop_front() { self.seen.remove(&old); } }
        true
    }
}

/// DET (2026-10-18): detection measurement + the detection-side gates shared by the paper and live loops.
///  * one `DETECT` line per create arrival per feed (the duplicate copy too): feed, first/dup, dt to the first copy (µs),
///    slot, t_rx (ns, realtime), poh_ms, lag_ms = how long after its PoH position the create reached us (slot start
///    estimated from the entries feed: min over the slot's arrivals of t_rx - poh), dev reads, quote, verdict.
///  * a `FEEDS` health line every 60 s (per feed: messages, forwarded, reconnects, errors, ms since the last message).
///  * the new gates' switches: --dev-sized-only (old dev read), --allow-nonsol-quote, --allow-legacy-create.
struct DetLog {
    names: Vec<String>,
    slot_t0: std::collections::BTreeMap<u64, u64>,
    first: std::collections::HashMap<Pk, (u64, u16, Option<f64>)>,
    order: std::collections::VecDeque<Pk>,
    last_health: Instant,
    dev_sized_only: bool,
    allow_nonsol: bool,
    allow_legacy: bool,
    /// --no-router: do not fire on decoded router (CPI) creates (detect-only, as the paper-tested AFTER binary)
    no_router: bool,
}

impl DetLog {
    fn new(names: Vec<String>) -> Self {
        DetLog { names, slot_t0: Default::default(), first: Default::default(), order: Default::default(), last_health: Instant::now(),
            dev_sized_only: has("--dev-sized-only"), allow_nonsol: has("--allow-nonsol-quote"), allow_legacy: has("--allow-legacy-create"),
            no_router: has("--no-router") }
    }
    fn name(&self, f: u16) -> &str { self.names.get(f as usize).map(|s| s.as_str()).unwrap_or("?") }
    /// every arrival: the slot-start estimate from PoH-positioned (entries feed) transactions
    fn note(&mut self, a: &arbx::feeds::Arrival) {
        if let Some(ms) = a.poh.as_ref().and_then(|p| p.ms()) {
            let t0 = a.t_rx.saturating_sub((ms * 1e6) as u64);
            let e = self.slot_t0.entry(a.slot).or_insert(t0);
            if t0 < *e { *e = t0; }
            while self.slot_t0.len() > 256 { let k = *self.slot_t0.keys().next().unwrap(); self.slot_t0.remove(&k); }
        }
    }
    /// log one create arrival; true = the first copy of this mint (any feed)
    fn create(&mut self, a: &arbx::feeds::Arrival, mint: &Pk, kind: &str, extra: &str) -> bool {
        let poh = a.poh.as_ref().and_then(|p| p.ms());
        let (first, dt_us, poh_any) = match self.first.get(mint) {
            Some(&(t, _, p)) => (false, (a.t_rx as i64 - t as i64) / 1000, poh.or(p)),
            None => {
                self.first.insert(*mint, (a.t_rx, a.feed, poh));
                self.order.push_back(*mint);
                if self.order.len() > 50_000 { if let Some(o) = self.order.pop_front() { self.first.remove(&o); } }
                (true, 0, poh)
            }
        };
        if !first { if let (Some(p), Some(e)) = (poh, self.first.get_mut(mint)) { if e.2.is_none() { e.2 = Some(p); } } }
        let lag = match (self.slot_t0.get(&a.slot), poh_any) {
            (Some(&t0), Some(p)) => format!("{:.1}", (a.t_rx as f64 - t0 as f64) / 1e6 - p),
            _ => "-".into(),
        };
        eprintln!("  DETECT feed={} first={} dt_us={dt_us} slot={} t_rx={} poh_ms={} lag_ms={lag} mint={} kind={kind} sig={} {extra}",
            self.name(a.feed), first as u8, a.slot, a.t_rx, poh.map(|p| format!("{p:.1}")).unwrap_or_else(|| "-".into()), b58(mint),
            &a.tx.sig_b58()[..16]);
        first
    }
    /// the base filter's verdict for the log (same order as the loops' gates)
    #[allow(clippy::too_many_arguments)]
    fn verdict(&self, l: &Launch, tx: &arbx::tx::Tx, quote: Option<Pk>, min_dev: u64, max_dev: u64, allow_nonvanilla: bool, wl: bool, bl: bool) -> &'static str {
        if quote.is_some() && !self.allow_nonsol { return "skip_quote"; }
        if !l.is_create_v2 && !self.allow_legacy { return "skip_legacy"; }
        if l.dev_buy_lamports < min_dev { return "skip_dev_low"; }
        if l.dev_buy_lamports > max_dev { return "skip_dev_high"; }
        if !allow_nonvanilla && !l.is_snipeable() { return "skip_flags"; }
        if wl && !snipe::trusted_launch_host(tx) { return "skip_host"; }
        if bl && snipe::is_bot_launchpad(tx) { return "skip_host"; }
        "pass"
    }
    /// one FEEDS line every 60 s
    fn health(&mut self, feeds: &arbx::feeds::Feeds) {
        if self.last_health.elapsed() < Duration::from_secs(60) { return; }
        self.last_health = Instant::now();
        let now = arbx::feeds::clock::now_ns();
        let parts: Vec<String> = feeds.counters.iter().map(|c| format!("{}:msgs={},fwd={},rc={},err={},drops={},age_ms={},slot={}", c.name,
            c.packets.load(Ordering::Relaxed), c.forwarded.load(Ordering::Relaxed), c.reconnects.load(Ordering::Relaxed),
            c.errors.load(Ordering::Relaxed), c.channel_drops.load(Ordering::Relaxed),
            now.saturating_sub(c.last_msg_ns.load(Ordering::Relaxed)) / 1_000_000, c.slot_max.load(Ordering::Relaxed))).collect();
        eprintln!("  FEEDS t={} {}", now / 1_000_000_000, parts.join(" "));
    }
}

/// DET FIX: a Launch for a router (CPI) create: bonding curve + ATA derived from the mint (as --round-trip does), the
/// creator from the router args, dev = the curve cost of the router's min_tokens_out / 0.98 (its default 2% slippage;
/// on chain the cost of min_tokens_out was 0.978-0.980 x the true dev SOL), mayhem from the args, other flags default.
fn router_launch(tx: &arbx::tx::Tx) -> Option<Launch> {
    let (mint, creator, min_tokens, mayhem, holder) = snipe::router_create(tx)?;
    let mut l = snipe_build::launch_from_target(mint, creator);
    l.dev_buy_lamports = (snipe::curve_cost(snipe::CURVE_VQ0, min_tokens) as u128 * 100 / 98) as u64;
    l.is_mayhem = mayhem;
    l.is_holder_reward = holder;
    Some(l)
}

fn main() -> Result<()> {
    // provider secrets (e.g. CONSTANTK_TOKEN) into the process env, so a [[send]] url with ${...} expands.
    let envf = arg("--env-file").unwrap_or_else(|| "/root/arbx/deploy/.env".to_string());
    let _ = dotenvy::from_filename(&envf).or_else(|_| dotenvy::dotenv());

    let warm_probe = has("--warm-probe");
    let shadow = has("--shadow");
    let round_trip = has("--round-trip");
    let snipe_once = has("--snipe-once");
    let simulate = has("--simulate");
    let paper_trade = has("--paper-trade");
    let unwrap = has("--unwrap");
    let live = has("--live");
    if !warm_probe && !shadow && !round_trip && !snipe_once && !simulate && !paper_trade && !unwrap && !has("--sell-held") {
        bail!("pick a mode: --warm-probe (latency), --shadow (observe launches), --round-trip (gated buy+sell on --mint), --snipe-once (gated: auto-detect a fresh launch + round-trip it), --simulate (ZERO-COST: simulateTransaction a v3 buy, no send), --paper-trade (ZERO-COST: forward paper-trade the filter+exit-ladder on live launches, no send), --unwrap (gated: close the WSOL ATA back to native SOL), optionally with --live for real txs (gated)");
    }

    let probe: Probe = match arg("--config") {
        Some(p) => toml::from_str(&std::fs::read_to_string(&p).with_context(|| format!("reading {p}"))?)
            .with_context(|| format!("parsing {p} as a minimal probe config"))?,
        None => Probe::default(),
    };

    // wallet — a real send needs the real keystore (never a throwaway).
    let key: SigningKey = match probe.wallet_keystore.as_deref().filter(|s| !s.is_empty()) {
        Some(ks) => keystore_key(ks, probe.wallet.as_deref())?,
        None => bail!("the engine needs wallet_keystore in --config (the warm path sends real, capped txs)"),
    };
    let user: Pk = key.verifying_key().to_bytes();
    eprintln!("snipe_engine: payer = {}", b58(&user));

    // rpc for blockhash + slot + status polling (the ${...} in rpc_url is expanded from the env file).
    let rpc_url = probe.rpc_url.as_deref().filter(|s| !s.is_empty())
        .map(|u| config::expand(u).with_context(|| format!("rpc_url {u} names an env var that is empty/missing")))
        .transpose()?
        .context("the engine needs rpc_url in --config (blockhash, slot, status polling)")?;
    let rpc = Arc::new(rpc::Rpc::new(rpc_url));

    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(4).enable_all().build()?;

    rt.block_on(run(&probe, key, user, rpc, warm_probe, shadow, round_trip, snipe_once, simulate, paper_trade, live))
}

#[allow(clippy::too_many_arguments)]
async fn run(probe: &Probe, key: SigningKey, user: Pk, rpc: Arc<rpc::Rpc>, warm_probe: bool, shadow: bool, round_trip: bool, snipe_once: bool, simulate: bool, paper_trade: bool, live: bool) -> Result<()> {
    let stop = Arc::new(AtomicBool::new(false));

    // ---- --simulate: ZERO-COST. No send path, no warming — build+sign the v3 buy exactly as the live path and call
    // simulateTransaction. Does not require --live (spends nothing). Handle before any send-path setup.
    if simulate {
        return run_simulate(probe, &key, user, &rpc, &stop).await;
    }

    // ---- --paper-trade: ZERO-COST. Detect launches off the feed, forward-poll each winner's real curve price, and
    // replay the exit ladder for counterfactual PnL. No send path, no wallet spend. Handle before send-path setup.
    if paper_trade {
        return run_paper_trade(probe, &rpc, &stop).await;
    }

    // ---- build the send paths (the WARM path lives here). lenient: a path that can't be built is named, not fatal.
    if probe.sends.is_empty() { bail!("--config needs at least one [[send]] (e.g. tpu-direct, kind=\"tpu\")"); }
    let opts = send::PathsOpts { queue_ms: 0, payer: Some(user) };
    eprintln!("snipe_engine: building {} send path(s) ...", probe.sends.len());
    let (paths, notes) = send::Paths::new(&probe.sends, opts, arbx::rec::Rec::off(), true).await?;
    for n in &notes { eprintln!("  send note: {n}"); }
    if paths.list.is_empty() { bail!("no usable send path was built (see notes above)"); }

    // which path to fire through (default tpu-direct, else the first).
    let want = arg("--send-path").unwrap_or_else(|| "tpu-direct".to_string());
    let pidx = paths.index(&want).or_else(|| paths.list.iter().position(|p| p.name.contains("tpu"))).unwrap_or(0);
    let path = paths.list[pidx].clone();
    if let Some(sn) = arg("--sell-path") {
        match paths.index(&sn) {
            Some(i) => { let _ = SELL_PATH.set(paths.list[i].clone()); eprintln!("snipe_engine: SELL path = {}", paths.list[i].name); }
            None => bail!("--sell-path {sn}: no such [[send]] path"),
        }
    }
    if let Some(an) = arg("--also-send") {
        match paths.index(&an) {
            Some(i) => { let _ = ALSO_PATH.set(paths.list[i].clone()); eprintln!("snipe_engine: ALSO-SEND buys via {}", paths.list[i].name); }
            None => bail!("--also-send {an}: no such [[send]] path"),
        }
    }
    if let Some(fname) = arg("--fallback-path") {
        match paths.index(&fname) {
            Some(i) if paths.list[i].tip(0).is_none() => { let _ = FALLBACK_PATH.set(paths.list[i].clone()); eprintln!("snipe_engine: FALLBACK path = {}", paths.list[i].name); }
            Some(_) => bail!("--fallback-path {fname}: must be a tipless path (the signed tx would not pay its tip)"),
            None => bail!("--fallback-path {fname}: no such [[send]] path"),
        }
    }
    eprintln!("snipe_engine: fire path = {} ({})", path.name, path.describe());

    // ---- keep the current slot fresh for the tpu leader targeting (the real engine feeds this from its state
    // stream; here a lightweight poller feeds send::tpu::SLOT from the RPC's processed slot).
    {
        let (rpc, stop) = (rpc.clone(), stop.clone());
        tokio::spawn(async move {
            while !stop.load(Ordering::Relaxed) {
                if let Ok(s) = rpc.slot().await {
                    let cur = send::tpu::SLOT.load(Ordering::Relaxed);
                    if s > cur { send::tpu::SLOT.store(s, Ordering::Relaxed); }
                }
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
        });
    }
    {
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

    // ---- start the WARM loops: for a tpu path this spawns Tpu::keep_warm (pre-opens QUIC to the next leaders,
    // refreshes the leader window + cluster nodes) and a per-path keep-alive. THIS is the whole point.
    paths.start(stop.clone(), Duration::from_secs(2), |m: String| eprintln!("  keepalive: {m}"));

    // ---- WAIT until the path is demonstrably HOT before firing.
    wait_until_warm(&path, &rpc).await?;
    if let Some(list) = arg("--sell-held") {
        if !live { bail!("--sell-held sends real sells: needs --live"); }
        run_sell_held(&key, user, &rpc, &path, &list).await?;
        stop.store(true, Ordering::Relaxed);
        return Ok(());
    }

    if has("--unwrap") {
        run_unwrap(&key, user, &rpc, &path, live).await?;
        stop.store(true, Ordering::Relaxed);
        return Ok(());
    }
    if snipe_once {
        run_snipe_once(probe, &key, user, &rpc, &path, live, &stop).await?;
    }
    if round_trip {
        run_round_trip(&key, user, &rpc, &path, live).await?;
    }
    if shadow {
        run_shadow(probe, &key, user, &rpc, &path, live, &stop).await?;
    }
    if warm_probe {
        run_warm_probe(&key, user, &rpc, &path, live).await?;
    }

    stop.store(true, Ordering::Relaxed);
    Ok(())
}

/// Confirm the send path is warm. For a tpu path: wait for a leader to be known (SLOT>0 + leader book filled),
/// record the FIRST connect (the cold handshake), then poll connect_next until it returns a REUSED (fast)
/// connection a few times — proof the QUIC stream is already open. For a non-tpu (http/rpc) path: warm the HTTP
/// keep-alive a few times and take the best round trip. Caps the wait at --warm-wait-ms (default 15000).
async fn wait_until_warm(path: &Arc<send::Path>, _rpc: &rpc::Rpc) -> Result<()> {
    let cap = Duration::from_millis(arg_u64("--warm-wait-ms", 15_000));
    let start = Instant::now();
    if let Some(tpu) = &path.tpu {
        eprintln!("snipe_engine: warming tpu path (waiting for an open QUIC stream to the next leader) ...");
        let mut cold: Option<f64> = None;
        let mut fast_hits = 0u32;
        while start.elapsed() < cap {
            match tpu.connect_next().await {
                Ok((d, leader)) => {
                    let ms = d.as_secs_f64() * 1e3;
                    if cold.is_none() {
                        cold = Some(ms);
                        eprintln!("  first connect to {leader}: {ms:.2} ms (cold handshake)");
                    }
                    // a reused (warm) connection returns in well under a millisecond; a fresh handshake is ms+.
                    if ms < 2.0 {
                        fast_hits += 1;
                        if fast_hits >= 3 {
                            eprintln!("  WARM: connect_next reused an open stream to {leader} ({ms:.3} ms) x{fast_hits}; slot={}",
                                send::tpu::SLOT.load(Ordering::Relaxed));
                            return Ok(());
                        }
                    } else {
                        fast_hits = 0;
                    }
                }
                Err(e) => eprintln!("  warming: {e:#}"),
            }
            tokio::time::sleep(Duration::from_millis(300)).await;
        }
        // Did not see a clearly-reused stream, but the keep-alive loop is running; proceed and note it.
        eprintln!("  NOTE: never saw a sub-2ms (clearly reused) connect within {:?}; the keep-alive loop IS running \
                   (next leaders pre-connected every 400 ms). Proceeding; treat delta with care.", cap);
        if send::tpu::SLOT.load(Ordering::Relaxed) == 0 { bail!("tpu: no current slot known — cannot target a leader (rpc.slot failing?)"); }
        Ok(())
    } else {
        eprintln!("snipe_engine: warming {} (http keep-alive) ...", path.name);
        let mut best = f64::INFINITY;
        for _ in 0..6 {
            if start.elapsed() >= cap { break; }
            match path.warm().await {
                Ok(Some(d)) => { let ms = d.as_secs_f64() * 1e3; best = best.min(ms); eprintln!("  keep-alive {ms:.2} ms"); }
                Ok(None) => {}
                Err(e) => eprintln!("  keep-alive: {e:#}"),
            }
            tokio::time::sleep(Duration::from_millis(300)).await;
        }
        eprintln!("  WARM: best keep-alive {best:.2} ms (connection pooled)");
        Ok(())
    }
}

/// Fire capped 1-lamport self-transfers through the warm path and report the send->land slot delta distribution.
async fn run_warm_probe(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, live: bool) -> Result<()> {
    let max_sends = arg_u64("--max-sends", 20);
    let interval = Duration::from_millis(arg_u64("--interval-ms", 1500));
    let cu_limit = arg_u64("--cu-limit", 450) as u32;
    let cu_price = arg_u64("--cu-price-micro", 0);
    let land_timeout = Duration::from_millis(arg_u64("--land-timeout-ms", 15_000));

    // hard spend cap
    if !live {
        eprintln!("\nDRY: --warm-probe without --live does not transmit. To measure, the owner adds --live --max-sol <cap>.");
        return Ok(());
    }
    let max_sol = arg_f64("--max-sol", -1.0);
    if max_sol <= 0.0 { bail!("--live requires --max-sol <cap> (a hard SOL cap)"); }
    let cap_lamports = (max_sol * 1e9) as u64;
    // per-send cost: base fee (5000/sig) + priority fee (cu_price_micro * cu_limit / 1e6, rounded up) + 1 lamport transfer
    let prio_fee = ((cu_price as u128 * cu_limit as u128 + 999_999) / 1_000_000) as u64;
    let per_send = 5000 + prio_fee + 1;
    eprintln!("\nWARM-PROBE: up to {max_sends} self-transfers via {}, every {:?}; per-send ~{} lamports (cap {} lamports = {:.6} SOL)",
        path.name, interval, per_send, cap_lamports, max_sol);

    let prio = send::Prio { band: 0, crowd: 0, ev: 0 };
    let mut shots: Vec<Shot> = Vec::new();
    let mut spent: u64 = 0;

    for i in 0..max_sends {
        if spent + per_send > cap_lamports {
            eprintln!("  stopping: next send would exceed the cap ({} + {} > {})", spent, per_send, cap_lamports);
            break;
        }
        // fresh recent blockhash each time (NO durable nonce for a self-transfer — fixes snipe_fire's --nonce bug).
        let (blockhash, _bh_slot) = rpc.latest_blockhash().await.context("getLatestBlockhash")?;
        let mut ixs = vec![build::cu_limit_ix(cu_limit)];
        if cu_price > 0 { ixs.push(build::cu_price_ix(cu_price)); }
        ixs.push(build::transfer_ix(user, user, 1));
        let msg = build::compile_v0(user, &ixs, blockhash, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
        let raw = build::sign(&msg, key);
        let sig = send::first_signature(&raw).context("signed tx has no signature")?;
        let mut sig_bytes = [0u8; 64];
        sig_bytes.copy_from_slice(&bs58::decode(&sig).into_vec()?);

        // slot just before the send (same RPC clock used for the land slot, so the delta is self-consistent).
        let send_slot = rpc.slot().await.unwrap_or(0);
        let t = Instant::now();
        let to = match path.send(&raw, prio, None).await {
            Ok(r) => { spent += per_send; r.reply }
            Err(e) => { eprintln!("  [{i}] send refused: {e}"); continue; }
        };

        // poll for the land slot on the same RPC.
        let mut shot = Shot { send_slot, land_slot: None, ok: false, wall_ms: 0.0, to: to.clone(), create_slot: None, internal_ms: 0.0, poh_ms: 0.0, close: false };
        let poll_deadline = Instant::now() + land_timeout;
        while Instant::now() < poll_deadline {
            tokio::time::sleep(Duration::from_millis(300)).await;
            if let Ok(v) = rpc.statuses(&[sig_bytes]).await {
                if let Some(Some((land, ok))) = v.into_iter().next() {
                    shot.land_slot = Some(land);
                    shot.ok = ok;
                    shot.wall_ms = t.elapsed().as_secs_f64() * 1e3;
                    break;
                }
            }
        }
        match shot.land_slot {
            Some(land) => eprintln!("  [{i}] send_slot={send_slot} land_slot={land} delta={} ok={} wall={:.0}ms to=[{}]",
                land as i64 - send_slot as i64, shot.ok, shot.wall_ms, to),
            None => eprintln!("  [{i}] send_slot={send_slot} NOT SEEN in {:?} (sig {}) to=[{}]", land_timeout, sig, to),
        }
        shots.push(shot);
        tokio::time::sleep(interval).await;
    }

    report(path, &shots, spent);
    Ok(())
}

fn report(path: &Arc<send::Path>, shots: &[Shot], spent: u64) {
    let landed: Vec<&Shot> = shots.iter().filter(|s| s.land_slot.is_some()).collect();
    let mut deltas: Vec<f64> = landed.iter().map(|s| (s.land_slot.unwrap() as i64 - s.send_slot as i64) as f64).collect();
    let mut walls: Vec<f64> = landed.iter().map(|s| s.wall_ms).collect();
    println!("\n========== WARM-PROBE RESULT ({}) ==========", path.name);
    println!("sends fired      {}", shots.len());
    println!("landed           {}", landed.len());
    println!("total spent      {} lamports ({:.6} SOL)", spent, spent as f64 / 1e9);
    if !deltas.is_empty() {
        let (mn, md, p90, mx) = (pct(&mut deltas, 0.0), pct(&mut deltas, 0.5), pct(&mut deltas, 0.9), pct(&mut deltas, 1.0));
        println!("slot delta       min={mn:.0} median={md:.0} p90={p90:.0} max={mx:.0}  (land_slot - send_slot)");
        // distribution histogram
        let mut hist: std::collections::BTreeMap<i64, u32> = Default::default();
        for s in &landed { *hist.entry(s.land_slot.unwrap() as i64 - s.send_slot as i64).or_default() += 1; }
        print!("delta histogram  ");
        for (d, c) in &hist { print!("{d}:{c}  "); }
        println!();
        let (wmn, wmd, w90) = (pct(&mut walls, 0.0), pct(&mut walls, 0.5), pct(&mut walls, 0.9));
        println!("wall-to-land ms  min={wmn:.0} median={wmd:.0} p90={w90:.0}");
    }
    println!("path summary     {}", path.summary());
    println!("note             send_slot and land_slot are both the RPC's `processed` slot; the RPC's processed view");
    println!("                 can lag the network by ~1 slot, so delta has a small fixed offset. The QUIC write time");
    println!("                 (path summary 'send …ms') is the direct warm-send cost and is the cleanest warmth proof.");
    println!("================================================");
}

/// Observe launches off the shred feed; optionally fire one capped self-transfer per launch, timed to the trigger,
/// to measure create_slot -> send_slot and create_slot -> land_slot. NON-BLOCKING: the detector loop never awaits a
/// land-poll. Each fire's land-poll runs as its own tokio task (bounded by a semaphore) and writes its Shot into a
/// shared sink drained at the end, so a sustained feed stays same-slot instead of backing up behind 15s polls.
async fn run_shadow(probe: &Probe, key: &SigningKey, user: Pk, rpc: &Arc<rpc::Rpc>, path: &Arc<send::Path>, live: bool, stop: &Arc<AtomicBool>) -> Result<()> {
    if probe.feeds.is_empty() { bail!("--shadow needs at least one [[feed]] in --config (the shred feed + pump detector)"); }
    let on_trigger = has("--warm-probe-on-trigger");
    let min_dev_buy = arg_u64("--min-dev-buy", 1_000_000); // sane default: >= 0.001 SOL bundled dev buy; override with --min-dev-buy 0 to fire broadly
    let allow_nonvanilla = has("--allow-nonvanilla"); // default: vanilla-only (matches the proven sniper; avoids pump 6062)
    let max_sends = arg_u64("--max-sends", 20);
    let cap_lamports = (arg_f64("--max-sol", 0.0) * 1e9) as u64;
    let land_timeout = Duration::from_millis(arg_u64("--land-timeout-ms", 15_000));
    let duration = Duration::from_secs(arg_u64("--duration-s", 600));
    let max_inflight = arg_u64("--max-inflight", 64) as usize;
    let cu_price_probe = arg_u64("--cu-price-micro", 0); // apply the real buy's per-CU priority to the probe to test its effect on landing
    let probe_cu_limit = arg_u64("--probe-cu-limit", 450) as u32; // requested CU of the probe: set to the real buy's cu_limit (120k heavy / ~50k slim) to test the scheduler-packing effect on same-slot landing
    // base fee (5000) + 1-lamport transfer + worst-case priority fee (cu_price_micro * cu_limit / 1e6, only charged if it lands).
    // Counting the priority fee here makes --max-sol a TRUE hard cost cap for the probe even at high cu_price/cu_limit.
    let per_send: u64 = 5001 + cu_price_probe.saturating_mul(probe_cu_limit as u64) / 1_000_000;

    let interest = Arc::new(snipe::pump_interest());
    // feeds::start delivers over a crossbeam (sync) channel; bridge it to an async receiver on a blocking thread.
    let (tx, rx) = crossbeam_channel::unbounded();
    let handle = tokio::runtime::Handle::current();
    let _feeds = arbx::feeds::start(&probe.feeds, interest, tx, stop.clone(), &handle, &arbx::rec::Rec::off(), None)
        .context("starting the shred feed")?;
    let (atx, mut arx) = tokio::sync::mpsc::unbounded_channel();
    std::thread::spawn(move || { while let Ok(ev) = rx.recv() { if atx.send(ev).is_err() { break; } } });
    eprintln!("\nSHADOW: watching pump.fun launches (fire-on-trigger={on_trigger}, min_dev_buy={min_dev_buy} lamports, max_sends={max_sends}, duration={duration:?}, max_inflight={max_inflight}) ...");

    // a cached recent blockhash, refreshed in the background so the fire path never awaits getLatestBlockhash.
    let bh_cache = Arc::new(std::sync::Mutex::new([0u8; 32]));
    if let Ok((bh, _)) = rpc.latest_blockhash().await { *bh_cache.lock().unwrap() = bh; }
    {
        let (rpc, bh_cache, stop) = (rpc.clone(), bh_cache.clone(), stop.clone());
        tokio::spawn(async move {
            while !stop.load(Ordering::Relaxed) {
                if let Ok((bh, _)) = rpc.latest_blockhash().await { *bh_cache.lock().unwrap() = bh; }
                tokio::time::sleep(Duration::from_millis(1200)).await;
            }
        });
    }

    let sink: Arc<std::sync::Mutex<Vec<Shot>>> = Arc::new(std::sync::Mutex::new(Vec::new()));
    let sem = Arc::new(tokio::sync::Semaphore::new(max_inflight));
    let key = Arc::new(key.clone());
    let land_poll_ms = arg_u64("--land-poll-ms", 300); // tighten (e.g. 15) to measure true send->land inclusion time
    let (mut seen, mut passed, mut skipped_filter, mut fired, mut spent, mut skipped_backpressure, mut skipped_cap) = (0u64, 0u64, 0u64, 0u64, 0u64, 0u64, 0u64);
    let mut skipped_farleader = 0u64;
    let mut dedup = MintDedup::new(20000); // cross-feed de-dup (erpc + Kaldera)
    // --close-leaders <file>: LEADER-PROXIMITY GATE. Fire only when the create slot's leader is network-close to us
    // (pubkey set precomputed by pinging the cluster). We measured same-slot 88% on close leaders vs 22% on far — so
    // skipping far-leader launches concentrates fires on the ~71% we can actually win same-slot, no stake needed.
    let close_set: Option<std::collections::HashSet<String>> = arg("--close-leaders").map(|p|
        std::fs::read_to_string(&p).unwrap_or_default().lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect());
    // slot -> leader for the current epoch (one fetch; an epoch is ~2-3 days so a short run never rolls over).
    let slot_leader: std::collections::HashMap<u64, String> = if close_set.is_some() {
        let mut m = std::collections::HashMap::new();
        if let (Ok(ei), Ok(ls)) = (rpc.call("getEpochInfo", serde_json::json!([])).await,
                                   rpc.call("getLeaderSchedule", serde_json::json!([null])).await) {
            let epoch_start = ei["absoluteSlot"].as_u64().unwrap_or(0).saturating_sub(ei["slotIndex"].as_u64().unwrap_or(0));
            if let Some(obj) = ls.as_object() {
                for (leader, slots) in obj {
                    if let Some(arr) = slots.as_array() {
                        for s in arr { if let Some(si) = s.as_u64() { m.insert(epoch_start + si, leader.clone()); } }
                    }
                }
            }
        }
        eprintln!("CLOSE-LEADER GATE ON: {} close leaders, {} slots mapped", close_set.as_ref().map(|s| s.len()).unwrap_or(0), m.len());
        m
    } else { std::collections::HashMap::new() };
    let deadline = tokio::time::Instant::now() + duration;

    loop {
        if stop.load(Ordering::Relaxed) || fired >= max_sends { break; }
        let ev = tokio::select! {
            _ = tokio::time::sleep_until(deadline) => break,
            ev = arx.recv() => match ev { Some(e) => e, None => break },
        };
        let arbx::feeds::Event::Tx(a) = ev else { continue };
        let Some(l) = snipe::detect_launch(&a.tx) else { continue };
        // FEED COMPARE: log every create's arrival (feed index + rx nanos) so two feeds can be raced head-to-head
        // (same mint seen on both -> whichever t_rx is smaller delivered it first). t_rx is the shared monotonic clock.
        if has("--feed-compare") { eprintln!("FEEDCMP feed={} trx={} slot={} mint={}", a.feed, a.t_rx, a.slot, b58(&l.mint)); }
        // cross-feed de-dup (erpc + Kaldera): process each mint once — but NOT in feed-compare mode, which wants both arrivals.
        if !has("--feed-compare") && !dedup.first(l.mint) { continue; }
        seen += 1;
        let create_slot = a.slot;
        let flags_ok = allow_nonvanilla || l.is_snipeable();
        let pass = l.dev_buy_lamports >= min_dev_buy && flags_ok;
        if pass { passed += 1; } else { skipped_filter += 1; }
        // keep the launch log light under load: every launch that passes, and 1-in-20 of the skipped.
        if pass || seen % 20 == 0 {
            eprintln!("  LAUNCH slot={create_slot} poh_ms={:?} mint={} dev_buy={} v2={} vanilla={} (mayhem={} fee_bps={} holder={} cashback={}) {}",
                a.poh.as_ref().and_then(|p| p.ms()), b58(&l.mint), l.dev_buy_lamports, l.is_create_v2, l.is_vanilla(),
                l.is_mayhem, l.creator_fee_bps, l.is_holder_reward, l.is_cashback, if pass { "PASS" } else { "skip" });
        }
        if !(on_trigger && live && pass) { continue; }
        // leader-proximity: is this create slot's leader in the close set? (false if no set / unknown leader)
        let is_close = close_set.as_ref().map(|cs| slot_leader.get(&create_slot).map(|l| cs.contains(l)).unwrap_or(false)).unwrap_or(false);
        // GATE: skip far/unknown leaders — UNLESS --leader-tag-only (interleaved test: fire on ALL, just tag closeness).
        if close_set.is_some() && !has("--leader-tag-only") && !is_close { skipped_farleader += 1; continue; }
        if spent + per_send > cap_lamports { skipped_cap += 1; continue; }
        // backpressure: never block the detector; if max_inflight polls are outstanding, skip this fire.
        let bh = *bh_cache.lock().unwrap();
        if bh == [0u8; 32] { continue; } // no blockhash cached yet
        let permit = match sem.clone().try_acquire_owned() { Ok(p) => p, Err(_) => { skipped_backpressure += 1; continue } };
        fired += 1; spent += per_send;
        // fire-and-forget: build + sign + send + land-poll all off the detector loop.
        // t_recv = the instant we (the engine) hold this launch event — everything after is OUR internal cost.
        let t_recv = Instant::now();
        let poh_ms = a.poh.as_ref().and_then(|p| p.ms()).unwrap_or(-1.0);
        let (path, rpc, key, sink) = (path.clone(), rpc.clone(), key.clone(), sink.clone());
        let shot_close = is_close;
        tokio::spawn(async move {
            let _permit = permit; // released when the poll finishes
            let mut ixs = vec![build::cu_limit_ix(probe_cu_limit)];
            if cu_price_probe > 0 { ixs.push(build::cu_price_ix(cu_price_probe)); } // per-CU priority: same ordering a real buy gets at this cu_price
            ixs.push(build::transfer_ix(user, user, 1));
            let msg = match build::compile_v0(user, &ixs, bh, &[], &[]) { Ok(m) => m, Err(_) => return };
            let raw = build::sign(&msg, &*key);
            let sig = match send::first_signature(&raw) { Some(s) => s, None => return };
            let mut sig_bytes = [0u8; 64];
            if bs58::decode(&sig).into_vec().map(|v| sig_bytes.copy_from_slice(&v)).is_err() { return; }
            let send_slot = send::tpu::SLOT.load(Ordering::Relaxed); // current slot (kept fresh in run()); non-blocking
            let internal_ms = t_recv.elapsed().as_secs_f64() * 1e3; // event-receipt -> just before send (OUR build/sign/queue cost)
            let t = Instant::now();
            if let Err(e) = path.send(&raw, send::Prio { band: 0, crowd: 0, ev: 0 }, None).await {
                eprintln!("    fire refused: {e}");
                sink.lock().unwrap().push(Shot { send_slot, land_slot: None, ok: false, wall_ms: 0.0, to: "refused".into(), create_slot: Some(create_slot), internal_ms, poh_ms, close: shot_close });
                return;
            }
            let mut shot = Shot { send_slot, land_slot: None, ok: false, wall_ms: 0.0, to: sig.clone(), create_slot: Some(create_slot), internal_ms, poh_ms, close: shot_close };
            let poll_deadline = Instant::now() + land_timeout;
            while Instant::now() < poll_deadline {
                tokio::time::sleep(Duration::from_millis(land_poll_ms)).await;
                if let Ok(v) = rpc.statuses(&[sig_bytes]).await {
                    if let Some(Some((land, ok))) = v.into_iter().next() { shot.land_slot = Some(land); shot.ok = ok; shot.wall_ms = t.elapsed().as_secs_f64() * 1e3; break; }
                }
            }
            sink.lock().unwrap().push(shot);
        });
    }

    // drain: wait for the outstanding land-poll tasks to finish (acquire every permit), bounded by land_timeout.
    eprintln!("\nSHADOW: detector stopped (fired={fired}); waiting for {} in-flight land-polls to settle ...", max_inflight - sem.available_permits());
    let _ = tokio::time::timeout(land_timeout + Duration::from_secs(2), sem.acquire_many(max_inflight as u32)).await;

    if close_set.is_some() { eprintln!("CLOSE-LEADER GATE: skipped {skipped_farleader} far/unknown-leader launches (fired only on close leaders)"); }
    let shots = std::mem::take(&mut *sink.lock().unwrap());
    report_shadow(&shots, seen, passed, skipped_filter, fired, skipped_backpressure, skipped_cap, spent);
    Ok(())
}

/// DET FIX: tell the PoH clock the cluster's real slot length (getRecentPerformanceSamples, last ~4 min).
async fn set_slot_clock(rpc: &rpc::Rpc) {
    if let Ok(v) = rpc.call("getRecentPerformanceSamples", serde_json::json!([4])).await {
        let (mut slots, mut secs) = (0u64, 0u64);
        for x in v.as_array().into_iter().flatten() { slots += x["numSlots"].as_u64().unwrap_or(0); secs += x["samplePeriodSecs"].as_u64().unwrap_or(0); }
        if slots > 0 {
            let us = secs * 1_000_000 / slots;
            arbx::feeds::entries::set_slot_us(us);
            eprintln!("POH CLOCK: {slots} slots in {secs} s -> {:.1} ms a slot (PoH ms scaled to it; was a fixed 400 ms)", us as f64 / 1000.0);
        }
    }
}

/// DET FIX: slot -> leader for the CURRENT and the NEXT epoch (getLeaderSchedule keys are slot indexes relative to the
/// epoch's first slot; the next epoch's schedule is already fixed and served for any slot in it).
async fn leader_map(rpc: &rpc::Rpc) -> std::collections::HashMap<u64, String> {
    let mut m = std::collections::HashMap::new();
    let Ok(ei) = rpc.call("getEpochInfo", serde_json::json!([])).await else { return m };
    let start = ei["absoluteSlot"].as_u64().unwrap_or(0).saturating_sub(ei["slotIndex"].as_u64().unwrap_or(0));
    let len = ei["slotsInEpoch"].as_u64().unwrap_or(432_000);
    for (base, arg) in [(start, serde_json::Value::Null), (start + len, serde_json::json!(start + len))] {
        if let Ok(ls) = rpc.call("getLeaderSchedule", serde_json::json!([arg])).await {
            if let Some(obj) = ls.as_object() {
                for (leader, slots) in obj { if let Some(arr) = slots.as_array() {
                    for s in arr { if let Some(si) = s.as_u64() { m.insert(base + si, leader.clone()); } } } }
            }
        }
    }
    m
}

/// histogram of integer deltas as "d:count" pairs, sorted by delta.
fn hist_line(vals: &[i64]) -> String {
    let mut h: std::collections::BTreeMap<i64, u32> = Default::default();
    for &d in vals { *h.entry(d).or_default() += 1; }
    h.iter().map(|(d, c)| format!("{d}:{c}")).collect::<Vec<_>>().join("  ")
}

#[allow(clippy::too_many_arguments)]
fn report_shadow(shots: &[Shot], seen: u64, passed: u64, skipped_filter: u64, fired: u64, skipped_backpressure: u64, skipped_cap: u64, spent: u64) {
    let landed: Vec<&Shot> = shots.iter().filter(|s| s.land_slot.is_some()).collect();
    let send_vs_create: Vec<i64> = shots.iter().filter_map(|s| s.create_slot.map(|c| s.send_slot as i64 - c as i64)).collect();
    let land_vs_create: Vec<i64> = landed.iter().filter_map(|s| s.create_slot.map(|c| s.land_slot.unwrap() as i64 - c as i64)).collect();
    if let Some(p) = arg("--dump-shots") {
        use std::io::Write;
        if let Ok(mut f) = std::fs::File::create(&p) {
            for s in shots {
                if let (Some(c), Some(l)) = (s.create_slot, s.land_slot) {
                    let _ = writeln!(f, "{{\"create\":{},\"land\":{},\"delta\":{},\"poh\":{:.1},\"close\":{}}}", c, l, l as i64 - c as i64, s.poh_ms, s.close);
                }
            }
        }
    }
    println!("\n========== SHADOW RESULT ==========");
    println!("launches seen    {seen}  (passed filter {passed}, skipped by filter {skipped_filter})");
    println!("fired            {fired}  (skipped: backpressure {skipped_backpressure}, cap {skipped_cap})");
    println!("recorded shots   {}  (landed {}, dropped/not-seen {})", shots.len(), landed.len(), shots.len() - landed.len());
    println!("total spent      {} lamports ({:.6} SOL)", spent, spent as f64 / 1e9);
    if !send_vs_create.is_empty() {
        let mut v: Vec<f64> = send_vs_create.iter().map(|&x| x as f64).collect();
        println!("send - create    min={:.0} median={:.0} p90={:.0} max={:.0}  (did we FIRE in the create slot)", pct(&mut v, 0.0), pct(&mut v, 0.5), pct(&mut v, 0.9), pct(&mut v, 1.0));
        println!("  histogram      {}", hist_line(&send_vs_create));
    }
    if !land_vs_create.is_empty() {
        let mut v: Vec<f64> = land_vs_create.iter().map(|&x| x as f64).collect();
        println!("land - create    min={:.0} median={:.0} p90={:.0} max={:.0}  (did we LAND in the create slot — the real same-slot metric)", pct(&mut v, 0.0), pct(&mut v, 0.5), pct(&mut v, 0.9), pct(&mut v, 1.0));
        println!("  histogram      {}", hist_line(&land_vs_create));
    }
    // --- LATENCY BREAKDOWN: where the slot is lost ---
    let mut internal: Vec<f64> = shots.iter().map(|s| s.internal_ms).filter(|&x| x > 0.0).collect();
    let mut wall: Vec<f64> = landed.iter().map(|s| s.wall_ms).filter(|&x| x > 0.0).collect();
    if !internal.is_empty() {
        println!("internal_ms      min={:.1} median={:.1} p90={:.1} max={:.1}  (event-receipt -> just before send: OUR build/sign/queue cost)", pct(&mut internal, 0.0), pct(&mut internal, 0.5), pct(&mut internal, 0.9), pct(&mut internal, 1.0));
    }
    if !wall.is_empty() {
        println!("send->land ms    min={:.0} median={:.0} p90={:.0} max={:.0}  (wire + inclusion; incl. the 300ms status poll granularity)", pct(&mut wall, 0.0), pct(&mut wall, 0.5), pct(&mut wall, 0.9), pct(&mut wall, 1.0));
    }
    // poh correlation: do we make same-slot only when the create lands EARLY in its slot?
    let mut poh_d0: Vec<f64> = landed.iter().filter(|s| s.create_slot.map(|c| s.land_slot.unwrap() == c).unwrap_or(false) && s.poh_ms >= 0.0).map(|s| s.poh_ms).collect();
    let mut poh_late: Vec<f64> = landed.iter().filter(|s| s.create_slot.map(|c| s.land_slot.unwrap() > c).unwrap_or(false) && s.poh_ms >= 0.0).map(|s| s.poh_ms).collect();
    if !poh_d0.is_empty() && !poh_late.is_empty() {
        println!("poh_ms | SAME-slot lands: median={:.0} (n={})   vs   LATE (+1) lands: median={:.0} (n={})", pct(&mut poh_d0, 0.5), poh_d0.len(), pct(&mut poh_late, 0.5), poh_late.len());
        println!("                 (if same-slot lands cluster at LOW poh, the limiter is our reaction latency, not the send path)");
    }
    println!("note             send_slot is the engine's current-slot atomic (non-blocking); create_slot is the launch's");
    println!("                 feed slot; land_slot is the RPC processed slot. delta 0 = same slot as the create.");
    println!("===================================");
}

/// Build a real buy for a launch (GATED; never auto-run). Uses buy_message_ixs (which prepends advance_nonce when a
/// durable nonce is configured; None here = plain recent-blockhash). `default_spend` is the --spend-lamports default.
fn build_buy(user: Pk, launch: &Launch, nonce: Option<(Pk, Pk)>, default_spend: u64, min_out: u64) -> (Vec<build::Ix>, u64) {
    let plan = BuyPlan {
        spend_lamports: arg_u64("--spend-lamports", default_spend),
        min_tokens_out: min_out,
        cu_limit: arg_u64("--cu-limit", 120_000) as u32,
        // Priority fee default = 3,000,000 micro-lamports. MEASURED (2026-10-14): this lands us at ~1.02x the floor
        // (vs 1.33x at 0, 1.08x at 2M) — intra-slot ordering is pure cu_price, and winners were paying ~1M+. 3M is the
        // knee of the curve (we're at the floor on normal launches; only whale-contested slots need more).
        cu_price_micro: arg_u64("--cu-price-micro", 3_000_000),
        create_ata: !has("--no-ata"),
        track_volume: true,
        nonce,
        wrap: has("--wrap"),
    };
    let spend = plan.spend_lamports;
    (snipe_build::buy_message_ixs(user, launch, &plan), spend)
}

/// One landed transaction: its signature, the slot read just before send, the land slot (None = never seen), ok.
struct Landed { sig: String, send_slot: u64, land_slot: Option<u64>, ok: bool }

/// Reusable: compile the given ixs on a FRESH recent blockhash, sign, send through the WARM path, and poll
/// getSignatureStatuses for the land slot. The one place the engine turns an instruction list into a landed tx.
async fn send_and_poll(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, ixs: &[build::Ix], land_timeout: Duration) -> Result<Landed> {
    let t_sp = Instant::now();
    // Tipped send paths (nozomi / jito-tx / helius / 0slot ...) require a top-level System tip transfer to one of the
    // path's tip accounts, or Path::check refuses the send. Tipless paths (staked-rpc / tpu-direct) return None -> unchanged.
    let _tip_owned: Vec<build::Ix>;
    // --also-send: only for non-sell sends (a sell goes through SELL_PATH), and only to a different path.
    // DET FIX: "is this a buy" is read from the instructions (the pump buy disc). The old test (path != SELL_PATH) also
    // double-sent every SELL, paying the also-path's tip, whenever --sell-path was not given (sells then use the buy path).
    let is_buy = ixs.iter().any(|ix| ix.data.starts_with(&snipe_build::BUY_EXACT_QUOTE_IN_V3_DISC));
    let also = ALSO_PATH.get().filter(|a| is_buy && a.name != path.name);
    let mut tips: Vec<(Pk, u64)> = Vec::new();
    if let Some((t, l)) = path.tip(0) { if l > 0 { tips.push((t, l)); } }
    if let Some(a) = also { if let Some((t, l)) = a.tip(0) { if l > 0 { tips.push((t, l)); } } }
    let ixs: &[build::Ix] = if tips.is_empty() { ixs } else {
        let mut v = Vec::with_capacity(ixs.len() + tips.len());
        for (t, l) in &tips { v.push(build::transfer_ix(user, *t, *l)); }
        v.extend_from_slice(ixs);
        _tip_owned = v;
        &_tip_owned
    };
    let cached = BLOCKHASH_CACHE.lock().unwrap().filter(|(_, t)| t.elapsed() < Duration::from_secs(20)).map(|(h, _)| h);
    let blockhash = match cached { Some(h) => h, None => rpc.latest_blockhash().await.context("getLatestBlockhash")?.0 };
    let msg = build::compile_v0(user, ixs, blockhash, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
    let raw = build::sign(&msg, key);
    let sig = send::first_signature(&raw).context("signed tx has no signature")?;
    let mut sig_bytes = [0u8; 64];
    sig_bytes.copy_from_slice(&bs58::decode(&sig).into_vec()?);
    let send_slot = match send::tpu::SLOT.load(Ordering::Relaxed) { 0 => rpc.slot().await.unwrap_or(0), s => s };
    eprintln!("  SEND-PREP {:.1} ms (send_and_poll entry -> send)", t_sp.elapsed().as_secs_f64() * 1e3);
    // DET: one SEND-ACK line per path answer: how long the endpoint took to accept, its HTTP status and reply (constant-k's
    // x-ck-tx-route is appended by send::deliver). Zero-cost diagnostics for the send-path A/B.
    let timed = |p: Arc<send::Path>, raw: Vec<u8>| async move {
        let t = Instant::now();
        let r = p.send(&raw, send::Prio { band: 0, crowd: 0, ev: 0 }, None).await;
        match &r {
            Ok(rep) => eprintln!("  SEND-ACK path={} ack_ms={:.2} status={:?} reply={}", p.name, t.elapsed().as_secs_f64() * 1e3, rep.status, rep.reply.chars().take(120).collect::<String>()),
            Err(e) => eprintln!("  SEND-ACK path={} ack_ms={:.2} REFUSED status={:?} {}", p.name, t.elapsed().as_secs_f64() * 1e3, e.status, e.msg.chars().take(120).collect::<String>()),
        }
        r
    };
    match also {
        Some(a) => {
            let (r1, r2) = tokio::join!(timed(path.clone(), raw.clone()), timed(a.clone(), raw.clone()));
            match (&r1, &r2) {
                (Err(e1), Err(e2)) => bail!("send refused: {}: {e1} / {}: {e2}", path.name, a.name),
                (Err(e1), Ok(_)) => eprintln!("  (also-send: {} refused: {e1}; {} accepted)", path.name, a.name),
                (Ok(_), Err(e2)) => eprintln!("  (also-send: {} refused: {e2}; {} accepted)", a.name, path.name),
                _ => {}
            }
        }
        None => {
            if let Err(e) = timed(path.clone(), raw.clone()).await {
                // DET (--fallback-path, default off): a refusal (HTTP 429 from Helius' keyless 1 req/s/IP limit, or the
                // local max_per_sec guard) re-sends the SAME signed tx through a tipless fallback path instead of
                // losing the trade. Only tipless fallbacks (staked-rpc) are accepted at start-up: no extra tip is paid.
                match FALLBACK_PATH.get().filter(|f| f.name != path.name) {
                    Some(f) => {
                        timed(f.clone(), raw.clone()).await
                            .map_err(|e2| anyhow::anyhow!("send refused: {}: {e} / fallback {}: {e2}", path.name, f.name))?;
                        eprintln!("  (fallback: {} refused: {e}; re-sent via {})", path.name, f.name);
                    }
                    None => bail!("send refused: {e}"),
                }
            }
        }
    }
    let mut out = Landed { sig, send_slot, land_slot: None, ok: false };
    let deadline = Instant::now() + land_timeout;
    // DET: --land-poll-ms (default 300 = unchanged). The buy's land is only noticed at the next poll, so the first
    // sell leg (and the exit clock) starts up to one poll late; 100 ms costs ~10 getSignatureStatuses/s per open send.
    let poll = Duration::from_millis(arg_u64("--land-poll-ms", 300).max(20));
    while Instant::now() < deadline {
        tokio::time::sleep(poll).await;
        if let Ok(v) = rpc.statuses(&[sig_bytes]).await {
            if let Some(Some((land, ok))) = v.into_iter().next() { out.land_slot = Some(land); out.ok = ok; break; }
        }
    }
    Ok(out)
}

/// native SOL balance of `who` (lamports, processed commitment).
async fn native_balance(rpc: &rpc::Rpc, who: Pk) -> Result<u64> {
    let v = rpc.call("getBalance", serde_json::json!([b58(&who), { "commitment": "processed" }])).await.context("getBalance")?;
    v["value"].as_u64().context("getBalance: no value")
}

/// raw u64 token amount in the SPL token account `ata` (processed); 0 if the account does not exist yet.
/// --sell-held: for each mint, rebuild its Launch from the create tx (oldest signature, raw wire bytes -> the same
/// parser as the shred feed), then sell our whole Token-2022 balance via the SELL path and close the ATA (rent back).
async fn run_sell_held(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, list: &str) -> Result<()> {
    let cu = arg_u64("--cu-limit", 120_000) as u32;
    let price = arg_u64("--sell-cu-price-micro", 1_500_000);
    for m in list.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
        let mint = pk(m);
        let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
        let amount = token_balance(rpc, &ata).await?;
        if amount == 0 { eprintln!("  SELL-HELD {m}: balance 0 — skip"); continue; }
        // oldest signature = the create
        let mut before: Option<String> = None;
        let mut oldest: Option<String> = None;
        for _ in 0..40 {
            let mut o = serde_json::json!({ "limit": 1000 });
            if let Some(b) = &before { o["before"] = serde_json::json!(b); }
            let v = match rpc.call("getSignaturesForAddress", serde_json::json!([m, o])).await { Ok(v) => v, Err(e) => { eprintln!("  SELL-HELD {m}: sigs failed: {e}"); break; } };
            let arr = v.as_array().cloned().unwrap_or_default();
            if arr.is_empty() { break; }
            let last = arr.last().and_then(|x| x["signature"].as_str()).map(|x| x.to_string());
            oldest = last.clone();
            if arr.len() < 1000 { break; }
            before = last;
        }
        let Some(csig) = oldest else { eprintln!("  SELL-HELD {m}: no signatures — skip"); continue; };
        let t = match rpc.call("getTransaction", serde_json::json!([csig, { "encoding": "base64", "maxSupportedTransactionVersion": 1, "commitment": "confirmed" }])).await {
            Ok(t) => t,
            Err(e) => { eprintln!("  SELL-HELD {m}: getTransaction failed: {e} — skip"); continue; }
        };
        let raw = t["transaction"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok());
        let Some(raw) = raw else { eprintln!("  SELL-HELD {m}: create tx not decodable — skip"); continue; };
        let Some((tx, _)) = arbx::tx::parse_wire(&raw) else { eprintln!("  SELL-HELD {m}: parse_wire failed — skip"); continue; };
        let Some(launch) = snipe::detect_launch(&tx) else { eprintln!("  SELL-HELD {m}: oldest tx is not a create — skip"); continue; };
        let ixs = snipe_build::sell_message_ixs(user, &launch, amount, 0, cu, price, false);
        match send_and_poll(key, user, rpc, sp(path), &ixs, Duration::from_secs(30)).await {
            Ok(l) => eprintln!("  SELL-HELD {m}: qty={amount} sig={} land_slot={:?} ok={}", l.sig, l.land_slot, l.ok),
            Err(e) => eprintln!("  SELL-HELD {m}: send failed: {e}"),
        }
    }
    Ok(())
}

async fn token_balance(rpc: &rpc::Rpc, ata: &Pk) -> Result<u64> {
    match rpc.call("getTokenAccountBalance", serde_json::json!([b58(ata), { "commitment": "processed" }])).await {
        Ok(v) => Ok(v["value"]["amount"].as_str().and_then(|s| s.parse::<u64>().ok()).unwrap_or(0)),
        Err(_) => Ok(0), // account not found yet
    }
}

/// --round-trip (GATED): buy a tiny amount of `--mint` through the WARM path, wait for it to land, read our token
/// balance, sell all of it back, and report both legs plus the native-balance round-trip cost. A safer first real
/// buy than a momentum hold: it immediately exits the position. Does NOTHING without --live --max-sol, caps the buy
/// spend at the cap, and (because the engine only ever uses the real keystore) never fires with a throwaway key.
async fn run_round_trip(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, live: bool) -> Result<()> {
    if !live {
        eprintln!("\nDRY: --round-trip does nothing without --live --max-sol <cap>. The owner reviews, then runs it live.");
        return Ok(());
    }
    let max_sol = arg_f64("--max-sol", -1.0);
    if max_sol <= 0.0 { bail!("--live requires --max-sol <cap> (a hard SOL cap on the buy spend)"); }
    let cap_lamports = (max_sol * 1e9) as u64;
    let land_timeout = Duration::from_millis(arg_u64("--land-timeout-ms", 15_000));

    // resolve the launch: explicit bonding-curve, else derive the PDAs from mint + creator.
    let mint = arg_pk("--mint").context("--round-trip needs --mint <PK> (use --snipe-once to auto-detect a fresh launch)")?;
    let creator = arg_pk("--creator").unwrap_or(mint);
    let mut launch = match arg_pk("--bonding-curve") {
        Some(bc) => Launch { mint, bonding_curve: bc, assoc_bonding_curve: snipe_build::assoc_bonding_curve(&bc, &mint), creator, dev_buy_lamports: 0, is_create_v2: true,
            is_mayhem: false, is_cashback: false, creator_fee_bps: 0, is_holder_reward: false, buyback_fee_recipient: [0u8; 32] },
        None => snipe_build::launch_from_target(mint, creator),
    };
    if let Some(bb) = arg_pk("--buyback") { launch.buyback_fee_recipient = bb; }
    round_trip_launch(key, user, rpc, path, &launch, cap_lamports, max_sol, land_timeout, None).await
}

/// --simulate (ZERO-COST, no --live): build+sign the v3 buy EXACTLY as the live path (WSOL wrap +
/// buy_exact_quote_in_v3) and call simulateTransaction — no send, nothing spent. Resolve the launch from
/// --mint/--creator/--bonding-curve (repeatable on a stable curve), or from the first vanilla launch off the feed when
/// [[feed]] is configured. Vary --spend-lamports to sweep the v3 minimum buy size (where 6020 BuyZeroAmount stops and
/// a real base-token amount appears in the logs).
async fn run_simulate(probe: &Probe, key: &SigningKey, user: Pk, rpc: &Arc<rpc::Rpc>, stop: &Arc<AtomicBool>) -> Result<()> {
    let spend = arg_u64("--spend-lamports", 2_000_000);
    let min_out = arg_u64("--min-tokens-out", 1);
    if let Some(mint) = arg_pk("--mint") {
        let creator = arg_pk("--creator").unwrap_or(mint);
        let mut launch = match arg_pk("--bonding-curve") {
            Some(bc) => Launch { mint, bonding_curve: bc, assoc_bonding_curve: snipe_build::assoc_bonding_curve(&bc, &mint), creator, dev_buy_lamports: 0, is_create_v2: true,
                is_mayhem: false, is_cashback: false, creator_fee_bps: 0, is_holder_reward: false, buyback_fee_recipient: [0u8; 32] },
            None => snipe_build::launch_from_target(mint, creator),
        };
    if let Some(bb) = arg_pk("--buyback") { launch.buyback_fee_recipient = bb; }
        eprintln!("\nSIMULATE buy (ZERO-COST): mint={} spend={} lamports ({:.6} SOL) — no send", b58(&mint), spend, spend as f64 / 1e9);
        return simulate_buy(key, user, rpc, &launch, spend, min_out).await;
    }
    if probe.feeds.is_empty() { bail!("--simulate needs --mint <PK> (direct, repeatable) OR a [[feed]] in --config (auto-detect the first launch)"); }
    let allow_nonvanilla = has("--allow-nonvanilla");
    let interest = Arc::new(snipe::pump_interest());
    let (tx, rx) = crossbeam_channel::unbounded();
    let handle = tokio::runtime::Handle::current();
    let _feeds = arbx::feeds::start(&probe.feeds, interest, tx, stop.clone(), &handle, &arbx::rec::Rec::off(), None).context("starting the shred feed")?;
    let (atx, mut arx) = tokio::sync::mpsc::unbounded_channel();
    std::thread::spawn(move || { while let Ok(ev) = rx.recv() { if atx.send(ev).is_err() { break; } } });

    // ---- CONTINUOUS CAP-PROBE (ZERO-COST): with --fill-cap and --minutes, tally FILL-vs-REVERT over many launches.
    // For each launch passing --min-dev-buy we run TWO simulateTransaction calls (nothing sent, nothing spent):
    //   (a) uncapped (min_out=1): sanity — is the launch buyable at all right now?
    //   (b) capped (min_out from the 1.04x floor): the real decision — would we FILL <=cap or REVERT?
    // Both fill => we'd trade at <=cap. (a) fills but (b) reverts => the cap correctly rejected a worse fill (the guard
    // works). This is the live fill-cap mechanism proven with no capital at risk.
    if let Some(cap) = arg("--fill-cap").and_then(|s| s.parse::<f64>().ok()) {
        let min_dev_buy = arg_u64("--min-dev-buy", 8_000_000_000);
        let minutes = arg_u64("--minutes", 120);
        let deadline = Instant::now() + Duration::from_secs(minutes * 60);
        let (mut seen, mut buyable, mut would_fill, mut cap_revert, mut other) = (0u64, 0u64, 0u64, 0u64, 0u64);
        eprintln!("\nCAP-PROBE (ZERO-COST, {minutes} min): dev_buy>={min_dev_buy}, fill-cap={cap}x, spend={spend}. Two sims/launch, no send, nothing spent.");
        loop {
            if Instant::now() >= deadline || stop.load(Ordering::Relaxed) { break; }
            let ev = match tokio::time::timeout(Duration::from_secs(2), arx.recv()).await { Ok(Some(e)) => e, Ok(None) => break, Err(_) => continue };
            let arbx::feeds::Event::Tx(a) = ev else { continue };
            let Some(launch) = snipe::detect_launch(&a.tx) else { continue };
            if launch.dev_buy_lamports < min_dev_buy { continue; }
            if !allow_nonvanilla && !launch.is_snipeable() { continue; }
            seen += 1;
            let floor_px = pump_floor_px(launch.dev_buy_lamports);
            let capped_min_out = if floor_px > 0.0 { (spend as f64 / (cap * floor_px)).floor() as u64 } else { 1 };
            let (fill_uncapped, _) = simulate_classify(key, user, rpc, &launch, spend, 1).await;
            let (fill_capped, err) = simulate_classify(key, user, rpc, &launch, spend, capped_min_out).await;
            let verdict = if fill_capped { would_fill += 1; "FILL<=cap" }
                else if fill_uncapped { cap_revert += 1; "CAP-REVERT (fill>cap, guard fired)" }
                else { other += 1; "unbuyable/other" };
            if fill_uncapped { buyable += 1; }
            eprintln!("  CAP-PROBE #{seen} slot={} mint={} dev_buy={} floor={:.3e} cap_min_out={} -> {} {}",
                a.slot, b58(&launch.mint), launch.dev_buy_lamports, floor_px, capped_min_out, verdict,
                if verdict == "unbuyable/other" { format!("err={err}") } else { String::new() });
        }
        println!("\n========== CAP-PROBE RESULT (ZERO-COST) ==========");
        println!("dev_buy>= {min_dev_buy} lamports ({:.2} SOL), fill-cap {cap}x, spend {spend} lamports", min_dev_buy as f64/1e9);
        println!("launches seen     {seen}  (buyable now: {buyable})");
        println!("would FILL <=cap  {would_fill}  ({:.0}% of seen)  <- we'd trade these at <= {cap}x floor", if seen>0 {100.0*would_fill as f64/seen as f64} else {0.0});
        println!("CAP-REVERT fired  {cap_revert}  (buyable but fill > cap -> guard reverts, cost=fees only live)");
        println!("unbuyable/other   {other}");
        println!("note: proves the live --fill-cap guard both lets good fills through and reverts bad ones, with no capital at risk.");
        println!("==================================================");
        return Ok(());
    }

    eprintln!("\nSIMULATE (ZERO-COST): watching for the first {} launch to simulate a buy on ...", if allow_nonvanilla { "(any)" } else { "VANILLA" });
    loop {
        if stop.load(Ordering::Relaxed) { return Ok(()); }
        let ev = match arx.recv().await { Some(e) => e, None => bail!("feed closed before a launch was detected") };
        let arbx::feeds::Event::Tx(a) = ev else { continue };
        let Some(launch) = snipe::detect_launch(&a.tx) else { continue };
        if !allow_nonvanilla && !launch.is_snipeable() { continue; }
        eprintln!("  DETECTED launch slot={} mint={} — simulating buy at {} lamports", a.slot, b58(&launch.mint), spend);
        return simulate_buy(key, user, rpc, &launch, spend, min_out).await;
    }
}

/// Quiet variant of `simulate_buy` for the cap-probe: returns (would_fill, err_string). Spends nothing.
async fn simulate_classify(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, launch: &Launch, spend: u64, min_out: u64) -> (bool, String) {
    let plan = BuyPlan {
        spend_lamports: spend, min_tokens_out: min_out, cu_limit: arg_u64("--cu-limit", 120_000) as u32,
        cu_price_micro: arg_u64("--cu-price-micro", 3_000_000), create_ata: true, track_volume: false, nonce: None, wrap: has("--wrap"),
    };
    let ixs = snipe_build::buy_message_ixs(user, launch, &plan);
    let bh = rpc.latest_blockhash().await.map(|x| x.0).unwrap_or([0u8; 32]);
    let msg = match build::compile_v0(user, &ixs, bh, &[], &[]) { Ok(m) => m, Err(e) => return (false, format!("compile:{e}")) };
    let raw = build::sign(&msg, key);
    let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
    let opts = serde_json::json!({ "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed" });
    match rpc.call("simulateTransaction", serde_json::json!([b64, opts])).await {
        Ok(v) => { let err = &v["value"]["err"]; (err.is_null(), err.to_string()) }
        Err(e) => (false, format!("rpc:{e}")),
    }
}

/// Build+sign a v3 buy message and simulateTransaction it (sigVerify off, replaceRecentBlockhash on). Prints err,
/// unitsConsumed, returnData and every log line. Spends nothing.
async fn simulate_buy(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, launch: &Launch, spend: u64, min_out: u64) -> Result<()> {
    let plan = BuyPlan {
        spend_lamports: spend, min_tokens_out: min_out, cu_limit: arg_u64("--cu-limit", 120_000) as u32,
        cu_price_micro: arg_u64("--cu-price-micro", 3_000_000), create_ata: true, track_volume: false, nonce: None,
        wrap: has("--wrap"),
    };
    let ixs = snipe_build::buy_message_ixs(user, launch, &plan);
    let bh = rpc.latest_blockhash().await.map(|x| x.0).unwrap_or([0u8; 32]); // replaced by replaceRecentBlockhash anyway
    let msg = build::compile_v0(user, &ixs, bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
    let raw = build::sign(&msg, key);
    let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
    let opts = serde_json::json!({ "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed" });
    let v = rpc.call("simulateTransaction", serde_json::json!([b64, opts])).await.context("simulateTransaction")?;
    let val = &v["value"];
    println!("\n========== SIMULATE BUY RESULT ==========");
    println!("mint             {}", b58(&launch.mint));
    println!("spend_lamports   {} ({:.6} SOL)", spend, spend as f64 / 1e9);
    println!("err              {}", val["err"]);
    println!("unitsConsumed    {}", val["unitsConsumed"]);
    if !val["returnData"].is_null() { println!("returnData       {}", val["returnData"]); }
    println!("--- logs ---");
    if let Some(logs) = val["logs"].as_array() {
        for l in logs { if let Some(s) = l.as_str() { println!("  {s}"); } }
    } else {
        println!("  (no logs — check err / the raw result): {v}");
    }
    let logtext = val["logs"].to_string();
    if logtext.contains("6020") || logtext.contains("BuyZeroAmount") {
        println!(">>> BuyZeroAmount (6020): this spend is BELOW the v3 minimum — raise --spend-lamports and re-run.");
    } else if val["err"].is_null() {
        println!(">>> SUCCESS: this spend WOULD land. The base-token amount received is in the logs above.");
    } else {
        println!(">>> reverted with a DIFFERENT error (see err/logs) — not the minimum-size issue.");
    }
    println!("NOTE: the SELL is not simulated here — simulateTransaction of a sell needs the base tokens actually held,");
    println!("      which an un-sent (simulated) buy never creates. Confirm the sell on the live 1-trade test.");
    println!("=========================================");
    Ok(())
}

/// --snipe-once (GATED): run the shred-feed detector and, on the FIRST launch that passes the dev-buy filter,
/// immediately round-trip THAT detected launch's own mint/creator/bonding_curve (no --mint). Then stop. This is the
/// real sniper: the mint comes from the feed, not the CLI. Does NOTHING without --live --max-sol; real keystore only.
async fn run_snipe_once(probe: &Probe, key: &SigningKey, user: Pk, rpc: &Arc<rpc::Rpc>, path: &Arc<send::Path>, live: bool, stop: &Arc<AtomicBool>) -> Result<()> {
    if probe.feeds.is_empty() { bail!("--snipe-once needs at least one [[feed]] in --config (e.g. probe_shadow.toml's erpc ShredStream)"); }
    // --concurrent: fire on EVERY qualifying launch in parallel (not one-at-a-time) so we don't miss the launches that
    // happen while a serial sniper is mid-trade. This is the throughput fix — the single biggest gap to the target.
    if has("--concurrent") { return run_snipe_live(probe, key, user, rpc, path, live, stop).await; }
    if !live {
        eprintln!("\nDRY: --snipe-once does nothing without --live --max-sol <cap>. The owner reviews, then runs it live.");
        return Ok(());
    }
    let max_sol = arg_f64("--max-sol", -1.0);
    if max_sol <= 0.0 { bail!("--live requires --max-sol <cap> (a hard SOL cap on the buy spend)"); }
    let cap_lamports = (max_sol * 1e9) as u64;
    let land_timeout = Duration::from_millis(arg_u64("--land-timeout-ms", 15_000));
    // Default = the PROFITABLE floor (selection study 2026-10-14): a SIZED spendable dev buy >= 2.0 SOL is the one
    // slot-0 signal that stays positive under realistic same-slot fills (+0.17 SOL/snipe vs -0.02 at the old 0.3 floor;
    // OOS win 73-81%). It is selective (~16% of launches, ~35% of his picks) — fewer trades, but the profitable ones.
    // Note dev_buy_lamports is now the SIZED spendable value only (cap/unbounded buys read 0 and are skipped here).
    let min_dev_buy = arg_u64("--min-dev-buy", 2_000_000_000);
    let allow_nonvanilla = has("--allow-nonvanilla");

    let interest = Arc::new(snipe::pump_interest());
    let (tx, rx) = crossbeam_channel::unbounded();
    let handle = tokio::runtime::Handle::current();
    let _feeds = arbx::feeds::start(&probe.feeds, interest, tx, stop.clone(), &handle, &arbx::rec::Rec::off(), None)
        .context("starting the shred feed")?;
    let (atx, mut arx) = tokio::sync::mpsc::unbounded_channel();
    std::thread::spawn(move || { while let Ok(ev) = rx.recv() { if atx.send(ev).is_err() { break; } } });
    eprintln!("\nSNIPE-ONCE (LIVE): watching for the first {} pump.fun launch with dev_buy >= {min_dev_buy} lamports (cap {:.6} SOL) ...",
        if allow_nonvanilla { "(any, --allow-nonvanilla)" } else { "VANILLA" }, max_sol);

    loop {
        if stop.load(Ordering::Relaxed) { eprintln!("stopped before a launch qualified"); return Ok(()); }
        let ev = match arx.recv().await { Some(e) => e, None => bail!("feed closed before any launch was detected") };
        let arbx::feeds::Event::Tx(a) = ev else { continue };
        let Some(launch) = snipe::detect_launch(&a.tx) else { continue };
        if launch.dev_buy_lamports < min_dev_buy {
            eprintln!("  skip launch slot={} mint={} dev_buy={} (< {})", a.slot, b58(&launch.mint), launch.dev_buy_lamports, min_dev_buy);
            continue;
        }
        // FLAG gate: the v3 buy is flag-agnostic (RE 2026-10-14: non-vanilla uses the identical 17-account buy), so we
        // snipe holder_reward/mayhem/cashback too — matching the target's full volume. We skip only creator_fee_bps>0
        // (a per-trade fee that eats our flip margin; the target skips these too). --allow-nonvanilla snipes even those.
        if !allow_nonvanilla && !launch.is_snipeable() {
            eprintln!("  skip CREATOR-FEE launch slot={} mint={} (creator_fee_bps={} — avoids paying the per-trade fee; --allow-nonvanilla to override)",
                a.slot, b58(&launch.mint), launch.creator_fee_bps);
            continue;
        }
        // --nonvanilla-only: for the one-shot confirm that the v3 buy lands on a NON-vanilla launch — wait for a
        // holder_reward/mayhem/cashback launch, skip plain vanilla ones (which the vanilla path already proved).
        if has("--nonvanilla-only") && launch.is_vanilla() {
            eprintln!("  skip VANILLA launch slot={} mint={} (--nonvanilla-only: waiting for a non-vanilla launch to confirm)", a.slot, b58(&launch.mint));
            continue;
        }
        eprintln!("  DETECTED {} launch slot={} mint={} creator={} bonding_curve={} dev_buy={} v2={} — sniping THIS mint",
            if launch.is_vanilla() { "VANILLA" } else { "non-vanilla" }, a.slot, b58(&launch.mint), b58(&launch.creator), b58(&launch.bonding_curve), launch.dev_buy_lamports, launch.is_create_v2);
        return round_trip_launch(key, user, rpc, path, &launch, cap_lamports, max_sol, land_timeout, Some(a.slot)).await;
    }
}

/// One paper position's outcome: counterfactual PnL in R (return multiple; +0.17 means +17% on the position).
struct PaperRec { mint: String, entry: f64, peak_r: f64, pnl_r: f64, nets: [f64; FILLS.len()], legs: usize, dev_buy: u64, vanilla: bool, fill: f64 }

/// pump.fun genesis virtual reserves; the post-dev-buy floor price is deterministic from dev_buy alone (no curve read).
const PUMP_VQ0: f64 = 30_000_000_000.0; // 30 SOL virtual quote
const PUMP_VT0: f64 = 1_073_000_000_000_000.0; // 1.073e9 tokens * 1e6 decimals virtual
fn pump_floor_px(dev_buy_lamports: u64) -> f64 {
    let vq = PUMP_VQ0 + dev_buy_lamports as f64;
    vq * vq / (PUMP_VQ0 * PUMP_VT0) // (vq')^2 / k  == vq'/vt'
}

/// Contested-fill stress levels: entry = floor-fill (1.00) up to 1.10x (a bad, outbid fill). Each position is scored
/// at ALL of these on the SAME recorded price path, so the tiers are directly comparable on identical tokens.
const FILLS: [f64; 6] = [1.00, 1.05, 1.08, 1.10, 1.25, 1.40];

/// Replay the live exit ladder over a recorded price path at a given entry fill, and return (gross_R, net_R, legs).
/// `path` is (ms_since_entry, r_base) where r_base = observed_price / floor_fill; at fill f the effective r = r_base / f.
#[allow(clippy::too_many_arguments)]
#[allow(clippy::too_many_arguments)]
fn sim_net(path: &[(f64, f64)], fill: f64, cap_ms: f64, derisk: f64, ride_mult: f64, trail: f64, cut_r: f64,
    ladder_frac: f64, fee_in: f64, fee_out: f64, fixed_per_rt: f64, demand_window_ms: f64, demand_min_r: f64) -> (f64, f64, usize) {
    let (mut remaining, mut peak_r, mut riding, mut first) = (1.0f64, 1.0f64, false, true);
    let (mut proceeds, mut legs, mut last_sell_slot, mut last_r) = (0.0f64, 0usize, 0i64, 1.0f64);
    for &(ms, r_base) in path {
        if remaining <= 1e-9 { break; }
        let r = r_base / fill;
        last_r = r;
        if r > peak_r { peak_r = r; }
        if !riding && r >= ride_mult { riding = true; }
        let cur_slot = (ms / 215.0) as i64;
        let (qty, final_): (f64, bool) = if first {
            first = false; (derisk.min(remaining), false)
        } else if r <= cut_r { (remaining, true) }
        else if riding && r <= peak_r * trail { (remaining, true) }
        else if !riding && demand_window_ms > 0.0 && ms >= demand_window_ms && peak_r < demand_min_r { (remaining, true) } // DEAD-no-demand cut
        else if ms >= cap_ms { (remaining, true) }
        else if !riding && (1.0..ride_mult).contains(&r) && (cur_slot - last_sell_slot) >= 4 { (remaining * ladder_frac, false) }
        else { (0.0, false) };
        let qty = qty.min(remaining);
        if qty > 0.0 { proceeds += qty * r; remaining -= qty; last_sell_slot = cur_slot; legs += 1; if final_ || remaining <= 1e-9 { break; } }
    }
    if remaining > 1e-9 { proceeds += remaining * last_r; }
    let gross = proceeds - 1.0;
    let net = (1.0 - fee_in) * (1.0 - fee_out) * proceeds - 1.0 - fixed_per_rt;
    (gross, net, legs)
}

/// SCALE-IN sim (floor entry): buy 1 SOL at floor; when the price first crosses `add_thr` x floor (a CONFIRMED mover),
/// add `add_size` SOL at that price; ride/trail/cut/cap the combined position. Returns net SOL for the trade (base
/// notional 1 + add_size only on the ~37% that confirm). `path` is (ms, r) with r = price/floor. Fees: fee/leg
/// multiplicative + a fixed per-leg lamport cost (extra buy leg when we add).
#[allow(clippy::too_many_arguments)]
fn sim_scalein(path: &[(f64, f64)], add_thr: f64, add_size: f64, cap_ms: f64, ride_mult: f64, trail: f64, cut_r: f64,
    fee: f64, fixed_leg_sol: f64) -> f64 {
    let (mut tokens, mut cost, mut proceeds, mut peak, mut riding, mut last_r, mut added) =
        (1.0f64, 1.0f64, 0.0f64, 1.0f64, false, 1.0f64, false);
    for &(ms, r) in path {
        if tokens <= 1e-9 { break; }
        last_r = r;
        if r > peak { peak = r; }
        if !added && r >= add_thr { tokens += add_size / r; cost += add_size; added = true; } // confirmation add
        if !riding && r >= ride_mult { riding = true; }
        let sell_all = r <= cut_r || (riding && r <= peak * trail) || ms >= cap_ms;
        if sell_all { proceeds += tokens * r; tokens = 0.0; break; }
    }
    if tokens > 1e-9 { proceeds += tokens * last_r; }
    let legs = if added { 3.0 } else { 2.0 }; // base buy + (add buy) + sell
    (1.0 - fee) * (1.0 - fee) * proceeds - cost - fixed_leg_sol * legs
}

// =====================================================================================================================
// RACE GATE (2026-10-18). All behaviour below is behind NEW flags that default OFF; with none of them set the paper and
// live loops behave exactly as before.
//   --dev-from-cap          read the dev buy of CAP-family dev buys (buy/buy_v2/buy_v3) from the token amount on the fresh
//                           curve (snipe::dev_buy_cap_lamports). Without it those launches read 0 SOL and are skipped.
//   --race-gate             fire only on launches that pass the race gate (static create-time conditions, and, with
//                           --race-window-ms > 0, enough OUTSIDE buyers seen on the mint in the shred stream in the window).
//   --race-log              log per-launch race features + outsider counts (implied by --race-gate). Paper/live both.
//   --race-min-dev-sol F    gate: effective dev buy >= F SOL (default 0)
//   --race-max-dev-sol F    gate: effective dev buy <= F SOL (default no limit)
//   --race-window-ms W      gate: hold the launch W ms after the create and count outside buyers (default 0 = decide at
//                           the create on static conditions only)
//   --race-min-out N        gate: >= N distinct outside payers seen in the window (default 1; needs W > 0)
//   --race-min-out-sol F    gate: outside buy SOL hint seen in the window >= F (default 0)
//   --race-bundle any|yes|no gate: require a creator bundle in the first --race-bundle-ms (yes) / none (no). default any
//   --race-bundle-ms B      txs on the mint within B ms of the create, from non-pro wallets, count as creator bundle (3)
//   --race-pros FILE        JSON array of known multi-creator sniper wallets: never counted as creator bundle
//   --race-obs-ms O         keep observing to O ms for the log (default max(W, 200))
//   --race-min-bundle N     gate: creator bundle of >= N buy txs seen within --race-bundle-ms (0 = off)
//   --race-max-name-len L   gate: token name <= L characters (0 = off)
//   --race-track-rejects    PAPER only: price-track rejected launches too, as shadow positions (dump "fired":false,
//                           log "PAPER shadow-done", excluded from the PAPER report). Ignored by the live loop.
// Outside payer = payer of a tx touching the mint that is not the creator, not a create-tx signer, not creator bundle.
// =====================================================================================================================
#[derive(Clone)]
struct RaceCfg {
    gate: bool,
    log: bool,
    dev_from_cap: bool,
    min_dev: u64,
    max_dev: u64,
    window_ms: f64,
    min_out: usize,
    min_out_sol: u64,
    bundle: i8,
    bundle_ms: f64,
    obs_ms: f64,
    /// count outside buyers in the window (true when --race-window-ms > 0)
    count_out: bool,
    /// --race-track-rejects (paper only): also price-track rejected launches as shadow positions
    track_rejects: bool,
    /// --race-min-bundle N: creator bundle of >= N buy txs within bundle_ms (0 = off)
    min_bundle: u32,
    /// --race-max-name-len L: token name <= L chars (0 = off)
    max_name_len: usize,
    pros: std::collections::HashSet<Pk>,
}

impl RaceCfg {
    fn from_args() -> Self {
        let gate = has("--race-gate");
        let window_cfg = arg_f64("--race-window-ms", 0.0).max(0.0);
        let bundle: i8 = match arg("--race-bundle").as_deref() { Some("yes") => 1, Some("no") => -1, _ => 0 };
        let bundle_ms = arg_f64("--race-bundle-ms", 3.0);
        // a bundle condition needs to see the first bundle_ms of the stream before deciding
        let min_bundle = arg_u64("--race-min-bundle", 0) as u32;
        let window_ms = if bundle != 0 || min_bundle > 0 { window_cfg.max(bundle_ms) } else { window_cfg };
        let pros = arg("--race-pros").and_then(|p| std::fs::read_to_string(p).ok())
            .and_then(|s| serde_json::from_str::<Vec<String>>(&s).ok())
            .map(|v| v.iter().map(|s| pk(s)).collect()).unwrap_or_default();
        RaceCfg {
            gate,
            log: gate || has("--race-log"),
            dev_from_cap: has("--dev-from-cap"),
            min_dev: (arg_f64("--race-min-dev-sol", 0.0) * 1e9) as u64,
            max_dev: (arg_f64("--race-max-dev-sol", 1e9) * 1e9) as u64,
            window_ms,
            min_out: arg_u64("--race-min-out", 1) as usize,
            min_out_sol: (arg_f64("--race-min-out-sol", 0.0) * 1e9) as u64,
            bundle,
            bundle_ms,
            obs_ms: arg_f64("--race-obs-ms", window_ms.max(200.0)).max(window_ms),
            count_out: window_cfg > 0.0,
            track_rejects: has("--race-track-rejects"),
            min_bundle,
            max_name_len: arg_u64("--race-max-name-len", 0) as usize,
            pros,
        }
    }
    fn active(&self) -> bool { self.gate || self.log }
    fn describe(&self) -> String {
        format!("race-gate={} log={} dev-from-cap={} dev=[{:.2},{:.2}] SOL window={}ms count_out={} min_out={} min_out_sol={:.2} bundle={} bundle_ms={} obs={}ms pros={} min_bundle={} max_name_len={} track_rejects={}",
            self.gate, self.log, self.dev_from_cap, self.min_dev as f64 / 1e9, self.max_dev as f64 / 1e9, self.window_ms, self.count_out, self.min_out,
            self.min_out_sol as f64 / 1e9, self.bundle, self.bundle_ms, self.obs_ms, self.pros.len(), self.min_bundle, self.max_name_len, self.track_rejects)
    }
}

/// apply --dev-from-cap to a freshly detected launch (effective dev = max(sized, cap-family estimate)).
fn race_dev_fix(cfg: &RaceCfg, launch: &mut Launch, tx: &arbx::tx::Tx) {
    if cfg.dev_from_cap {
        launch.dev_buy_lamports = launch.dev_buy_lamports.max(snipe::dev_buy_cap_lamports(tx));
    }
}

/// one line of create-time race features (logged for every launch the base filter passes when --race-log/--race-gate).
fn race_feat_line(launch: &Launch, tx: &arbx::tx::Tx, slot: u64) -> String {
    let ci = snipe::create_info(tx);
    let clean = |s: &str| s.chars().filter(|c| !c.is_whitespace() && *c != '=').take(24).collect::<String>();
    format!("slot={slot} mint={} dev={} dev_sized={} dev_cap={} kind={} host={} cu_price={} cu_limit={} nsig={} nkeys={} luts={} v1={} nix={} t22={} tip={} tip_to={} creator={} name_len={} sym={} name={}",
        b58(&launch.mint), launch.dev_buy_lamports, snipe::detect_launch(tx).map(|l| l.dev_buy_lamports).unwrap_or(0), snipe::dev_buy_cap_lamports(tx),
        snipe::dev_buy_kind(tx), if ci.uri_host.is_empty() { "-".to_string() } else { ci.uri_host.clone() }, ci.cu_price, ci.cu_limit, ci.nsig, ci.nkeys,
        ci.n_lookups, ci.v1, ci.n_ixs, ci.t22, ci.tip_lamports, ci.tip_to.map(|k| b58(&k)).unwrap_or_else(|| "-".into()), b58(&launch.creator),
        ci.name.chars().count(), clean(&ci.symbol), clean(&ci.name))
}

struct RacePend {
    launch: Launch,
    slot: u64,
    t0: Instant,
    cset: std::collections::HashSet<Pk>,
    bundle_n: u32,
    /// (ms after the create, payer, sol hint lamports, cu price, is_buy)
    out: Vec<(f64, Pk, u64, u64, bool)>,
    decided: bool,
    static_ok: bool,
    pass: bool,
    /// signatures already counted (the same tx arrives once per feed)
    sigs: std::collections::HashSet<[u8; 64]>,
}

struct RaceWatch { cfg: RaceCfg, pend: std::collections::HashMap<Pk, RacePend>, shadow: Vec<(Launch, u64)> }

impl RaceWatch {
    fn new(cfg: RaceCfg) -> Self { RaceWatch { cfg, pend: Default::default(), shadow: Vec::new() } }

    /// static (create-time) part of the gate.
    fn static_ok(&self, launch: &Launch, tx: &arbx::tx::Tx) -> bool {
        let name_ok = self.cfg.max_name_len == 0
            || snipe::create_strings(tx).map(|(n, _, _)| n.chars().count() <= self.cfg.max_name_len).unwrap_or(false);
        name_ok && launch.dev_buy_lamports >= self.cfg.min_dev && launch.dev_buy_lamports <= self.cfg.max_dev
    }

    /// a launch passed the engine's base filter: log it and start watching. Returns true when it should be fired NOW
    /// (gate off, or gate on with no window and the static conditions met).
    fn add(&mut self, launch: &Launch, tx: &arbx::tx::Tx, slot: u64) -> bool {
        let static_ok = self.static_ok(launch, tx);
        if self.cfg.log { eprintln!("  RACE seen {} static_ok={static_ok}", race_feat_line(launch, tx, slot)); }
        let mut cset: std::collections::HashSet<Pk> = tx.keys.iter().take(tx.num_signers as usize).copied().collect();
        cset.insert(launch.creator);
        let fire_now = !self.cfg.gate || (self.cfg.window_ms <= 0.0 && static_ok);
        self.pend.insert(launch.mint, RacePend { launch: launch.clone(), slot, t0: Instant::now(), cset, bundle_n: 0, out: Vec::new(),
            decided: fire_now || !self.cfg.gate || !static_ok, static_ok, pass: fire_now, sigs: Default::default() });
        if self.cfg.gate && !static_ok {
            eprintln!("  RACE reject-static slot={slot} mint={}", b58(&launch.mint));
            if self.cfg.track_rejects { self.shadow.push((launch.clone(), slot)); }
        }
        fire_now
    }

    /// every non-create pump tx: if it touches a watched mint, classify its payer (creator side / bundle / outsider).
    fn observe(&mut self, tx: &arbx::tx::Tx) {
        if self.pend.is_empty() || tx.is_vote { return; }
        let Some(&payer) = tx.keys.first() else { return };
        // a tx touches at most a couple of watched mints; scan its static keys against the (small) pending map
        let hits: Vec<Pk> = tx.keys.iter().filter(|k| self.pend.contains_key(*k)).copied().collect();
        for mint in hits {
            let Some(touch) = snipe::mint_touch(tx, &mint) else { continue };
            let bundle_ms = self.cfg.bundle_ms;
            let is_pro = self.cfg.pros.contains(&payer);
            let Some(p) = self.pend.get_mut(&mint) else { continue };
            if !p.sigs.insert(tx.sig) { continue; } // duplicate delivery from the second feed
            let ms = p.t0.elapsed().as_secs_f64() * 1e3;
            let signers: Vec<Pk> = tx.keys.iter().take(tx.num_signers as usize).copied().collect();
            if signers.iter().any(|s| p.cset.contains(s)) {
                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; }
                continue;
            }
            if ms <= bundle_ms && !is_pro {
                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; }
                p.cset.insert(payer);
                continue;
            }
            // cap-family buys: price the token amount on the curve after the dev buy + the outside SOL seen so far
            let seen: u64 = p.out.iter().map(|o| o.2).sum();
            let (sol, buy) = match touch {
                snipe::MintTouch::Buy(s) => (s, true),
                snipe::MintTouch::BuyCap { tokens, max_sol } => {
                    let est = snipe::curve_cost(snipe::CURVE_VQ0 + p.launch.dev_buy_lamports + seen, tokens);
                    (if max_sol > 0 && max_sol < est { max_sol } else { est }, true)
                }
                _ => (0, false),
            };
            if matches!(touch, snipe::MintTouch::Sell) { continue; }
            p.out.push((ms, payer, sol, tx.cu_price().unwrap_or(0), buy));
        }
    }

    fn counts(p: &RacePend, upto_ms: f64) -> (usize, u64, u64) {
        let mut payers: Vec<Pk> = Vec::new();
        let (mut sol, mut maxcu) = (0u64, 0u64);
        for &(ms, pk_, s, cu, _) in &p.out {
            if ms > upto_ms { continue; }
            if !payers.contains(&pk_) { payers.push(pk_); }
            sol = sol.saturating_add(s);
            maxcu = maxcu.max(cu);
        }
        (payers.len(), sol, maxcu)
    }

    /// decisions that are due + finished observations. Returns the launches to fire now (gate passed).
    fn due(&mut self) -> Vec<(Launch, u64)> {
        let mut ready = Vec::new();
        let mut done: Vec<Pk> = Vec::new();
        for (mint, p) in self.pend.iter_mut() {
            let el = p.t0.elapsed().as_secs_f64() * 1e3;
            if !p.decided && el >= self.cfg.window_ms {
                let (n, sol, maxcu) = Self::counts(p, self.cfg.window_ms);
                let bundle_ok = p.bundle_n >= self.cfg.min_bundle
                    && match self.cfg.bundle { 1 => p.bundle_n > 0, -1 => p.bundle_n == 0, _ => true };
                p.pass = p.static_ok && bundle_ok && (!self.cfg.count_out || (n >= self.cfg.min_out && sol >= self.cfg.min_out_sol));
                p.decided = true;
                eprintln!("  RACE decide slot={} mint={} at_ms={:.1} out_n={n} out_sol={:.3} max_cu={maxcu} bundle_n={} pass={}",
                    p.slot, b58(mint), el, sol as f64 / 1e9, p.bundle_n, p.pass);
                if p.pass { ready.push((p.launch.clone(), p.slot)); }
                else if self.cfg.track_rejects { self.shadow.push((p.launch.clone(), p.slot)); }
            }
            if el >= self.cfg.obs_ms {
                let c = |ms: f64| Self::counts(p, ms);
                let (n25, _, _) = c(25.0);
                let (n50, _, _) = c(50.0);
                let (n100, s100, cu100) = c(100.0);
                let (n200, s200, _) = c(200.0);
                let (nall, sall, _) = c(f64::MAX);
                let first = p.out.first().map(|o| o.0).unwrap_or(-1.0);
                let outs: String = p.out.iter().take(24).map(|o| format!("{:.1}:{:.3}:{}:{}", o.0, o.2 as f64 / 1e9, o.4 as u8, &b58(&o.1)[..6])).collect::<Vec<_>>().join(",");
                if self.cfg.log {
                    eprintln!("  RACE obs slot={} mint={} n25={n25} n50={n50} n100={n100} n200={n200} n_obs={nall} sol100={:.3} sol200={:.3} sol_obs={:.3} max_cu100={cu100} first_ms={first:.1} bundle_n={} fired={} outs={}",
                        p.slot, b58(mint), s100 as f64 / 1e9, s200 as f64 / 1e9, sall as f64 / 1e9, p.bundle_n, p.pass, if outs.is_empty() { "-".to_string() } else { outs });
                }
                done.push(*mint);
            }
        }
        for m in done { self.pend.remove(&m); }
        ready
    }

    /// how long the event loop may block before the next decision is due.
    fn next_wait(&self) -> Duration {
        if self.pend.is_empty() { Duration::from_secs(2) } else { Duration::from_millis(1) }
    }
}

/// --paper-trade (ZERO-COST): run the shred detector with the LIVE profit filter (sized dev buy >= --min-dev-buy,
/// is_snipeable), and for each qualifying launch forward-poll its REAL bonding-curve price and replay the exit ladder
/// to log counterfactual PnL. No buys, no sends, no wallet spend — this is the honest forward out-of-sample check of
/// the shipped config before any capital. Runs for --minutes (default 180 = 3h), then prints the aggregate.
async fn run_paper_trade(probe: &Probe, rpc: &Arc<rpc::Rpc>, stop: &Arc<AtomicBool>) -> Result<()> {
    if probe.feeds.is_empty() { bail!("--paper-trade needs at least one [[feed]] in --config (the erpc ShredStream)"); }
    let min_dev_buy = arg_u64("--min-dev-buy", 2_000_000_000);
    let allow_nonvanilla = has("--allow-nonvanilla");
    let minutes = arg_u64("--minutes", 180);
    let max_inflight = arg_u64("--max-inflight", 96) as usize;
    // exit-ladder params (same defaults as the live ladder — measured from the target wallet).
    let cap = Duration::from_millis(arg_u64("--exit-cap-ms", 3200));
    let derisk_frac = arg_f64("--derisk-frac", 0.0);
    let ride_mult = arg_f64("--ride-mult", 2.0);
    let trail_frac = arg_f64("--trail-frac", 0.90);
    let cut_r = arg_f64("--cut-r", 0.0);
    let ladder_frac = arg_f64("--ladder-frac", 0.0);
    let demand_window_ms = arg_u64("--demand-window-ms", 0); // DEAD-token early cut (only dev+us bought): cut if no demand by here
    let demand_min_r = arg_f64("--demand-min-r", 1.0);
    let entry_at_floor = has("--entry-at-floor"); // enter at the deterministic floor (what same-slot landing gets), not first-readable
    let max_r_cap = arg_f64("--max-r-cap", 1e9); // clamp recorded price multiple to a realistic max (kills graduated-token 6518x garbage)
    let scale_add_thr = arg_f64("--scale-add-thr", 0.0); // scale-in: add size when price crosses this x floor (0 = off)
    let scale_add_size = arg_f64("--scale-add-size", 2.0);
    let dump_paths = arg("--dump-paths"); // write each trade's raw path to this JSONL file for offline grid-search

    // ---- SELECTION FILTER (overnight research 2026-10-16): the dominant runner signal is EARLY DEMAND, not dev-buy.
    //  R1 demand gate: after observing the first --early-slots slots, require the curve price to have moved to >=
    //     --min-demand-mult x floor (demand = buyers beyond the dev pushing price up). The curve read is IMMEDIATE (no
    //     getSignaturesForAddress indexing lag). 1.0 = off. This skips the dead rugs our fill-cap over-selects.
    //  R2 whale gate: skip dev_buy > --max-dev-buy-sol (>8 SOL is poison: 5.6% runner / 50% dump).
    let min_demand_mult = arg_f64("--min-demand-mult", 1.0);
    let early_slots = arg_u64("--early-slots", 3);
    let observe_ms = arg_u64("--observe-ms", early_slots * 215 + 450); // wait this long after detect before the demand check + entry
    let demand_cobuy_lam = (arg_f64("--demand-cobuy-sol", 0.0) * 1e9) as u64; // co-buy demand gate: non-dev same-slot co-buy SOL
    let max_dev_buy_lam = (arg_f64("--max-dev-buy-sol", 1e9) * 1e9) as u64;
    // --max-creator-sigs N: 4yFAz's reverse-engineered SELECTION filter — he buys FRESH deployers (low prior-sig
    // creators) and skips serial launchers. Keep only launches whose creator had <= N signatures BEFORE this create.
    // 0 or unset = gate off. Evidence: his picks' creator median 1 prior sig vs 73-142 for skipped (OOS lift ~1.9x).
    let max_creator_sigs = arg_u64("--max-creator-sigs", 0);
    let mut skipped_creator = 0u64;
    let uri_whitelist = has("--uri-whitelist");
    let uri_blacklist = has("--uri-blacklist");
    let mut skipped_host = 0u64;

    // ---- LIVE-FAITHFUL cost model: the exact legs a real round-trip pays, so pnl_net == what the wallet would net.
    // size_sol = notional per trade (fixed fees amortize against it). $200 ~= 1.0 SOL at ~$200/SOL; override with --size-sol.
    let size_sol = arg_f64("--size-sol", 1.0);
    let size_lamports = (size_sol * 1e9).max(1.0);
    let pump_fee = arg_f64("--pump-fee-bps", 100.0) / 10_000.0; // pump protocol fee ~1% per leg
    let cost_slip = arg_f64("--cost-slip-bps", 25.0) / 10_000.0; // curve taker slippage ~0.25% per leg at our size
    let prio_lamports = arg_u64("--prio-lamports", 360_000); // cu_price 3M micro * 120k CU / 1e6 (matches live buy/sell)
    let base_lamports = arg_u64("--base-lamports", 5_000); // per signed tx
    // round-trip fixed fees (buy+sell) as a fraction of notional; variable fees apply multiplicatively per leg.
    let fixed_per_rt = ((prio_lamports + base_lamports) as f64 * 2.0) / size_lamports;
    let fee_in = pump_fee + cost_slip;
    let fee_out = pump_fee + cost_slip;

    let interest = Arc::new(snipe::pump_interest());
    let (tx, rx) = crossbeam_channel::unbounded();
    let handle = tokio::runtime::Handle::current();
    let _feeds = arbx::feeds::start(&probe.feeds, interest, tx, stop.clone(), &handle, &arbx::rec::Rec::off(), None)
        .context("starting the shred feed")?;
    let (atx, mut arx) = tokio::sync::mpsc::unbounded_channel();
    std::thread::spawn(move || { while let Ok(ev) = rx.recv() { if atx.send(ev).is_err() { break; } } });

    let mut det = DetLog::new(_feeds.names.clone());
    set_slot_clock(rpc).await;
    let deadline = Instant::now() + Duration::from_secs(minutes * 60);
    let sink: Arc<std::sync::Mutex<Vec<PaperRec>>> = Arc::new(std::sync::Mutex::new(Vec::new()));
    let sem = Arc::new(tokio::sync::Semaphore::new(max_inflight));
    let (mut detected, mut skipped_dev, mut skipped_flag) = (0u64, 0u64, 0u64);
    let mut dedup = MintDedup::new(20000); // cross-feed de-dup (erpc + Kaldera): process each mint once
    eprintln!("\nPAPER-TRADE (LIVE-FAITHFUL, {minutes} min): filter dev_buy>={min_dev_buy} + {} , exit ladder derisk={derisk_frac} ride>={ride_mult} trail={trail_frac} cut<={cut_r} ladder={ladder_frac} cap={cap:?}.\n  cost model: size={size_sol} SOL, pump_fee={:.2}%/leg slip={:.2}%/leg prio+base={} lamports/leg (fixed_rt={:.3}% of notional), fill sweep={:?}. No sends.",
        if allow_nonvanilla { "(any flags)" } else { "snipeable(creator_fee==0)" },
        pump_fee * 100.0, cost_slip * 100.0, prio_lamports + base_lamports, fixed_per_rt * 100.0, FILLS);

    // RACE GATE (default off): with --race-gate / --race-log launches that pass the base filter go through the race watch.
    let mut race = RaceWatch::new(RaceCfg::from_args());
    if race.cfg.active() || race.cfg.dev_from_cap { eprintln!("RACE: {}", race.cfg.describe()); }
    let mut ready: Vec<(Launch, u64)> = Vec::new();
    loop {
        if Instant::now() >= deadline || stop.load(Ordering::Relaxed) { break; }
        let wait = if race.cfg.active() { race.next_wait() } else { Duration::from_secs(2) };
        let ev = match tokio::time::timeout(wait, arx.recv()).await {
            Ok(Some(e)) => Some(e),
            Ok(None) => break,
            Err(_) => None, // timeout: re-check the deadline (and due race decisions)
        };
        det.health(&_feeds);
        if let Some(arbx::feeds::Event::Status { feed, msg }) = &ev { eprintln!("  FEEDSTATUS feed={} {msg}", det.name(*feed)); }
        if let Some(arbx::feeds::Event::Tx(a)) = ev {
            det.note(&a);
            // DET FIX: a top-level create, else pump's router create (CPI) decoded from the router's own args
            let cand = match snipe::detect_launch(&a.tx) { Some(l) => Some((l, false)), None if !det.no_router => router_launch(&a.tx).map(|l| (l, true)), None => None };
            match cand {
                None => {
                    if let Some(m) = snipe::detect_cpi_create(&a.tx) { det.create(&a, &m, "cpi", "verdict=cpi_not_decoded"); }
                    if race.cfg.active() { race.observe(&a.tx); }
                }
                Some((mut launch, via_router)) => 'create: {
                    if det.dev_sized_only && !via_router { launch.dev_buy_lamports = snipe::dev_buy_sized(&a.tx); }
                    race_dev_fix(&race.cfg, &mut launch, &a.tx);
                    let quote = snipe::create_quote_mint(&a.tx);
                    // DET: one DETECT line per create arrival per feed (the duplicate copy too: feed race + coverage)
                    let verdict = det.verdict(&launch, &a.tx, quote, min_dev_buy, max_dev_buy_lam, allow_nonvanilla, uri_whitelist, uri_blacklist);
                    let first = det.create(&a, &launch.mint, if via_router { "router" } else if launch.is_create_v2 { "v2" } else { "v1" },
                        &format!("dev={} dev_sized={} quote={} vanilla={} snipeable={} verdict={verdict}", launch.dev_buy_lamports, snipe::dev_buy_sized(&a.tx),
                            quote.map(|q| b58(&q)[..8].to_string()).unwrap_or_else(|| "sol".into()), launch.is_vanilla(), launch.is_snipeable()));
                    if !first { break 'create; }
                    if !dedup.first(launch.mint) { break 'create; } // same create seen on the other feed -> skip the duplicate
                    // DET FIX: non-SOL-quoted (31% of creates) and legacy SPL `create` launches cannot be bought by our
                    // WSOL / Token-2022 buy, and their dev read is not SOL: skip them (old behaviour behind flags).
                    if quote.is_some() && !det.allow_nonsol { skipped_flag += 1; break 'create; }
                    if !launch.is_create_v2 && !det.allow_legacy { skipped_flag += 1; break 'create; }
                    if launch.dev_buy_lamports < min_dev_buy { skipped_dev += 1; break 'create; }
                    if launch.dev_buy_lamports > max_dev_buy_lam { skipped_dev += 1; break 'create; } // R2 whale gate
                    if !allow_nonvanilla && !launch.is_snipeable() { skipped_flag += 1; break 'create; }
                    if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; break 'create; }
                    if uri_blacklist && snipe::is_bot_launchpad(&a.tx) { skipped_host += 1; break 'create; }
                    // CREATOR-FRESHNESS selection gate (4yFAz's measured selector): count the creator's signatures strictly
                    // BEFORE this create slot; skip if the deployer isn't fresh. One getSignaturesForAddress; fine in paper.
                    if max_creator_sigs > 0 {
                        let prior = match rpc.call("getSignaturesForAddress", serde_json::json!([b58(&launch.creator), { "limit": max_creator_sigs + 20 }])).await {
                            Ok(v) => v.as_array().map(|arr| arr.iter().filter(|s| s["slot"].as_u64().map(|sl| sl < a.slot).unwrap_or(false)).count() as u64).unwrap_or(0),
                            Err(_) => 0,
                        };
                        if prior > max_creator_sigs { skipped_creator += 1; break 'create; }
                    }
                    if !race.cfg.active() || race.add(&launch, &a.tx, a.slot) { ready.push((launch, a.slot)); }
                }
            }
        }
        if race.cfg.active() { ready.extend(race.due()); }
        let shadows: Vec<(Launch, u64)> = race.shadow.drain(..).collect();
        let batch: Vec<(Launch, u64, bool)> = ready.drain(..).map(|(l, s)| (l, s, true)).chain(shadows.into_iter().map(|(l, s)| (l, s, false))).collect();
        for (launch, create_slot, fired) in batch {
        let vanilla = launch.is_vanilla();
        if fired {
            detected += 1;
            eprintln!("  PAPER launch #{detected} slot={create_slot} mint={} dev_buy={} vanilla={vanilla} — tracking price path", b58(&launch.mint), launch.dev_buy_lamports);
        } else {
            eprintln!("  PAPER shadow-launch slot={create_slot} mint={} dev_buy={} (race gate rejected; tracked for comparison only)", b58(&launch.mint), launch.dev_buy_lamports);
        }

        // Spawn a concurrent tracker for THIS launch so fast-arriving launches don't queue behind a 9s hold.
        let (rpc2, sink2, sem2) = (rpc.clone(), sink.clone(), sem.clone());
        let dump_paths = dump_paths.clone();
        tokio::spawn(async move {
            let t_q = Instant::now();
            let Ok(_permit) = sem2.acquire().await else { return };
            let wait_ms = t_q.elapsed().as_secs_f64() * 1e3; // DET: a full --max-inflight delays the path start (not a skip)
            let (mut rd_ok, mut rd_fail) = (0u32, 0u32);
            let bc = launch.bonding_curve;
            // R1 DEMAND GATE: observe the first --early-slots, then require price >= min_demand_mult x floor (buyers came
            // in and moved the price). Skips the dead rugs. We enter at the post-observe price (realistic observe-then-buy).
            if min_demand_mult > 1.0 {
                tokio::time::sleep(Duration::from_millis(observe_ms)).await;
                let fl = pump_floor_px(launch.dev_buy_lamports);
                let p = curve_price(&rpc2, &bc).await.unwrap_or(0.0);
                let dm = if fl > 0.0 { p / fl } else { 0.0 };
                if dm < min_demand_mult {
                    eprintln!("  PAPER SKIP no-demand mint={} demand={:.3}x (< {:.3})", b58(&launch.mint), dm, min_demand_mult);
                    return;
                }
                eprintln!("  PAPER PASS demand mint={} demand={:.3}x — entering", b58(&launch.mint), dm);
            }
            // CO-BUY DEMAND GATE (--demand-cobuy-sol, the agent's OOS-perfect loser separator): observe, then require
            // non-dev same-slot co-buys >= threshold. co-buy SOL = curve real_sol (vq - 30 SOL virtual base) - dev buy.
            if demand_cobuy_lam > 0 {
                tokio::time::sleep(Duration::from_millis(observe_ms)).await;
                match curve_reserves(&rpc2, &bc).await {
                    Some((_vt, vq)) => {
                        let cobuy = vq.saturating_sub(30_000_000_000).saturating_sub(launch.dev_buy_lamports);
                        if cobuy < demand_cobuy_lam {
                            eprintln!("  PAPER SKIP no-cobuy mint={} cobuy={:.2}SOL (< {:.2})", b58(&launch.mint), cobuy as f64 / 1e9, demand_cobuy_lam as f64 / 1e9);
                            return;
                        }
                        eprintln!("  PAPER PASS cobuy mint={} cobuy={:.2}SOL — entering", b58(&launch.mint), cobuy as f64 / 1e9);
                    }
                    None => return,
                }
            }
            // Entry = first readable curve price (post-observe when the demand gate is on = realistic observe-then-buy).
            let mut entry = None;
            for _ in 0..16 { // ~4s of 250ms retries for the curve to become visible
                if let Some(p) = curve_price(&rpc2, &bc).await { entry = Some(p); break; }
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
            let Some(first_readable) = entry.filter(|&e| e > 0.0) else { return };
            // entry = the TRUE floor (same-slot landing) when --entry-at-floor, else the first-readable price (land +1).
            let entry_base = if entry_at_floor { pump_floor_px(launch.dev_buy_lamports).max(1e-12) } else { first_readable };
            let start = Instant::now();
            let pos_deadline = start + cap;
            // Record the FULL price path to the cap (don't exit early) so every fill level replays on the same path.
            let mut path: Vec<(f64, f64)> = Vec::with_capacity(32);
            let mut last_rb = 1.0f64;
            loop {
                if Instant::now() >= pos_deadline { break; }
                let ms = start.elapsed().as_millis() as f64;
                let rb = match curve_price(&rpc2, &bc).await { Some(p) => { rd_ok += 1; (p / entry_base).min(max_r_cap) }, None => { rd_fail += 1; last_rb } };
                last_rb = rb;
                path.push((ms, rb));
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
            let cap_ms = cap.as_millis() as f64;
            let peak_path = path.iter().map(|&(_, rb)| rb).fold(1.0f64, f64::max);
            // DUMP the raw path + metadata for offline grid-search of ALL exit/scale params (one JSONL line per trade).
            if let Some(ref df) = dump_paths {
                use std::io::Write;
                let obj = serde_json::json!({ "mint": b58(&launch.mint), "dev": launch.dev_buy_lamports as f64 / 1e9,
                    "vanilla": vanilla, "peak": peak_path, "path": path, "fired": fired, "slot": create_slot });
                // DET FIX: ONE write() per line. writeln! on an unbuffered File issues several writes, so concurrent trackers
                // interleaved their lines (2 garbled lines in the first 30 min of the det AFTER run).
                if let Ok(mut fh) = std::fs::OpenOptions::new().create(true).append(true).open(df) { let _ = fh.write_all(format!("{obj}\n").as_bytes()); }
            }
            // Score the position at every contested-fill level on this one recorded path.
            let mut nets = [0.0f64; FILLS.len()];
            let (mut base_gross, mut base_legs) = (0.0f64, 0usize);
            for (i, &f) in FILLS.iter().enumerate() {
                // Filter (deep research 2026-10-16): keep if n_trades_0_3>=4 OR non-vanilla. => the dead-token cut
                // fires ONLY on VANILLA tokens; non-vanilla launches (holder-reward/creator-fee/mayhem/cashback) run
                // more and are NEVER cut (the vanilla override that recovers runners).
                let dw = if vanilla { demand_window_ms as f64 } else { 0.0 };
                let (g, net, legs) = sim_net(&path, f, cap_ms, derisk_frac, ride_mult, trail_frac, cut_r, ladder_frac, fee_in, fee_out, fixed_per_rt, dw, demand_min_r);
                nets[i] = net;
                if i == 0 { base_gross = g; base_legs = legs; }
            }
            let peak_r = path.iter().map(|&(_, rb)| rb).fold(1.0f64, f64::max);
            // implied fill = our entry (first-readable, post dev-buy + early co-snipers) / deterministic floor.
            let floor_px = pump_floor_px(launch.dev_buy_lamports);
            let fill = if floor_px > 0.0 { entry_base / floor_px } else { 0.0 };
            let rec = PaperRec { mint: b58(&launch.mint), entry: entry_base, peak_r, pnl_r: base_gross, nets, legs: base_legs,
                dev_buy: launch.dev_buy_lamports, vanilla, fill };
            let net_str: String = FILLS.iter().zip(rec.nets.iter()).map(|(f, n)| format!(" @{:.2}={:+.4}", f, n)).collect();
            // scale-in forward value (floor entry): add scale_add_size SOL when price crosses scale_add_thr x floor.
            let scale_str = if scale_add_thr > 1.0 {
                let s = sim_scalein(&path, scale_add_thr, scale_add_size, cap_ms, ride_mult, trail_frac, cut_r, fee_in, (prio_lamports + base_lamports) as f64 / 1e9);
                format!(" pnl_SCALE={:+.4}", s)
            } else { String::new() };
            if !fired {
                eprintln!("  PAPER shadow-done mint={} fill={:.3}x peak_r={:.3} pnl_NET{}", rec.mint, rec.fill, rec.peak_r, net_str);
                return;
            }
            eprintln!("  PAPER done mint={} entry={:.3e} fill={:.3}x peak_r={:.3} legs={} pnl_R={:+.4} pnl_NET{}{}",
                rec.mint, rec.entry, rec.fill, rec.peak_r, rec.legs, rec.pnl_r, net_str, scale_str);
            eprintln!("  PAPER stats mint={} rd_ok={rd_ok} rd_fail={rd_fail} wait_ms={wait_ms:.0}", rec.mint);
            sink2.lock().unwrap().push(rec);
        });
        } // batch
    }

    // let in-flight positions finish (max one cap window).
    eprintln!("\nPAPER-TRADE window elapsed — draining {} in-flight positions ...", max_inflight - sem.available_permits());
    tokio::time::sleep(cap + Duration::from_secs(2)).await;

    let recs = std::mem::take(&mut *sink.lock().unwrap());
    if max_creator_sigs > 0 { eprintln!("CREATOR-FRESHNESS gate (<= {max_creator_sigs} prior sigs): skipped {skipped_creator} non-fresh-deployer launches"); }
    if uri_whitelist { eprintln!("URI-HOST GATE: skipped {skipped_host} non-trusted-host launches"); }
    paper_report(&recs, detected, skipped_dev, skipped_flag, min_dev_buy);
    Ok(())
}

fn paper_report(recs: &[PaperRec], detected: u64, skipped_dev: u64, skipped_flag: u64, min_dev_buy: u64) {
    println!("\n========== PAPER-TRADE RESULT ==========");
    println!("filter            dev_buy>={min_dev_buy} lamports ({:.2} SOL), creator_fee==0", min_dev_buy as f64 / 1e9);
    println!("launches seen     passed={detected}  skipped(dev too low)={skipped_dev}  skipped(creator-fee)={skipped_flag}");
    println!("paper positions   {} (passed launches whose curve became readable)", recs.len());
    if recs.is_empty() { println!("no positions to score."); println!("========================================"); return; }
    let n = recs.len() as f64;
    let gross_total: f64 = recs.iter().map(|r| r.pnl_r).sum();
    println!("gross mean PnL    {:+.4} R per position (no fees)", gross_total / n);
    println!("\nNET PnL by contested-fill level (same positions, live cost legs applied):");
    println!("  fill   mean_net_R   win%     total_net_R   mean_ex-top2");
    for (i, &f) in FILLS.iter().enumerate() {
        let mut v: Vec<f64> = recs.iter().map(|r| r.nets[i]).collect();
        v.sort_by(|a, b| a.partial_cmp(b).unwrap());
        let total: f64 = v.iter().sum();
        let mean = total / n;
        let wins = v.iter().filter(|&&p| p > 0.0).count();
        let ex2 = if v.len() > 2 { (total - v[v.len()-1] - v[v.len()-2]) / (n - 2.0) } else { f64::NAN };
        println!("  {:.2}x  {:+.4}      {:5.1}%   {:+.3}        {:+.4}", f, mean, 100.0 * wins as f64 / n, total, ex2);
    }
    // --- Implied-fill feasibility: how often could we actually fill at/under each cap, and what would we net if we did? ---
    let mut fills: Vec<f64> = recs.iter().map(|r| r.fill).filter(|&f| f > 0.0).collect();
    fills.sort_by(|a, b| a.partial_cmp(b).unwrap());
    if !fills.is_empty() {
        let fp = |q: f64| fills[((q * (fills.len() as f64 - 1.0)).round() as usize).min(fills.len() - 1)];
        println!("\nIMPLIED FILL (entry / deterministic floor from dev_buy): median={:.3}x p25={:.3}x p75={:.3}x min={:.3}x max={:.3}x", fp(0.50), fp(0.25), fp(0.75), fills[0], fills[fills.len()-1]);
        println!("fill-cap feasibility (only trade when implied fill <= cap; net scored at that cap's column):");
        println!("  cap    hit-rate      mean_net_R(filled)   total_net_R(filled)");
        for &cap in &[1.03f64, 1.05, 1.08, 1.10] {
            // nearest fill column >= cap for net scoring (what we'd pay when we do fill)
            let col = FILLS.iter().position(|&f| f >= cap - 1e-9).unwrap_or(FILLS.len() - 1);
            let taken: Vec<&PaperRec> = recs.iter().filter(|r| r.fill > 0.0 && r.fill <= cap).collect();
            let hits = taken.len();
            let (mean, tot) = if hits > 0 { let t: f64 = taken.iter().map(|r| r.nets[col]).sum(); (t / hits as f64, t) } else { (f64::NAN, 0.0) };
            println!("  {:.2}x  {:4}/{:<4} ({:4.1}%)   {:+.4}              {:+.3}", cap, hits, recs.len(), 100.0 * hits as f64 / n, mean, tot);
        }
    }
    println!("note: entry = first-readable curve price; implied fill = entry / floor(dev_buy). A live min_tokens_out cap reverts any fill above the cap (cost = base fee only), so the filled subset is what we'd actually trade. NET subtracts live round-trip cost legs over --size-sol notional.");
    println!("========================================");
}

/// --unwrap (gated by --live): close the wallet's WSOL ATA, returning the wrapped SOL (+ account rent) to the native
/// balance. Recovers funds only — no market exposure. `--account <PK>` overrides the ATA to close.
async fn run_unwrap(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, live: bool) -> Result<()> {
    let land_timeout = Duration::from_millis(arg_u64("--land-timeout-ms", 15_000));
    let wsol_ata = arg_pk("--account").unwrap_or_else(|| pda::ata(&user, &snipe_build::WSOL, &pda::TOKEN_PROGRAM));
    let bal_before = native_balance(rpc, user).await.unwrap_or(0);
    let ixs = vec![build::cu_limit_ix(30_000), build::close_account_ix(wsol_ata, user, user, *pda::TOKEN_PROGRAM)];
    eprintln!("\nUNWRAP: close WSOL ATA {} -> native SOL to {} (native before: {} lamports)", b58(&wsol_ata), b58(&user), bal_before);
    if !live { eprintln!("DRY: --unwrap does nothing without --live. Re-run with --live to send the close tx."); return Ok(()); }
    let landed = send_and_poll(key, user, rpc, path, &ixs, land_timeout).await?;
    match landed.land_slot {
        Some(s) => eprintln!("  UNWRAP sig={} land_slot={} ok={}", landed.sig, s, landed.ok),
        None => { eprintln!("  UNWRAP sig={} NOT SEEN within {:?}", landed.sig, land_timeout); return Ok(()); }
    }
    tokio::time::sleep(Duration::from_millis(1500)).await;
    let bal_after = native_balance(rpc, user).await.unwrap_or(bal_before);
    eprintln!("  native after: {} lamports (recovered {:+} lamports = {:+.6} SOL)", bal_after, bal_after as i64 - bal_before as i64, (bal_after as i64 - bal_before as i64) as f64 / 1e9);
    Ok(())
}

/// --snipe-once --concurrent (GATED): CONCURRENT sniper. The detector never blocks — every qualifying launch spawns its
/// own round-trip (buy with fill-cap + exit ladder), bounded by --max-inflight. This fixes the throughput gap: a serial
/// sniper is mid-trade (~3-30s) while dozens of launches pass by, so it only ever samples a handful and misses the
/// runners. Hard-bounded by: --max-sol (per-buy cap), --max-total-sol (cumulative buy-spend cap), and an in-engine
/// balance kill-switch (--max-loss-sol). Runs for --minutes.
async fn run_snipe_live(probe: &Probe, key: &SigningKey, user: Pk, rpc: &Arc<rpc::Rpc>, path: &Arc<send::Path>, live: bool, stop: &Arc<AtomicBool>) -> Result<()> {
    if !live { eprintln!("\nDRY: --snipe-once --concurrent needs --live --max-sol <cap> --max-total-sol <cap>."); return Ok(()); }
    let max_sol = arg_f64("--max-sol", -1.0);
    if max_sol <= 0.0 { bail!("--live requires --max-sol <cap> (per-buy cap)"); }
    let cap_lamports = (max_sol * 1e9) as u64;
    let max_total = arg_f64("--max-total-sol", -1.0);
    if max_total <= 0.0 { bail!("--concurrent requires --max-total-sol <cap> (hard cap on cumulative buy spend across the run)"); }
    let total_cap = (max_total * 1e9) as u64;
    let max_loss = arg_f64("--max-loss-sol", max_total); // balance kill-switch; default = total spend cap
    let loss_cap = (max_loss * 1e9) as u64;
    let minutes = arg_u64("--minutes", 30);
    let max_inflight = arg_u64("--max-inflight", 6) as usize;
    let land_timeout = Duration::from_millis(arg_u64("--land-timeout-ms", 15_000));
    let min_dev_buy = arg_u64("--min-dev-buy", 2_000_000_000);
    let max_dev_buy_lam = (arg_f64("--max-dev-buy-sol", 1e9) * 1e9) as u64; // whale gate
    let allow_nonvanilla = has("--allow-nonvanilla");
    let spend_per = arg_u64("--spend-lamports", 2_000_000);

    let interest = Arc::new(snipe::pump_interest());
    let (tx, rx) = crossbeam_channel::unbounded();
    let handle = tokio::runtime::Handle::current();
    let _feeds = arbx::feeds::start(&probe.feeds, interest, tx, stop.clone(), &handle, &arbx::rec::Rec::off(), None).context("starting the shred feed")?;
    let (atx, mut arx) = tokio::sync::mpsc::unbounded_channel();
    std::thread::spawn(move || { while let Ok(ev) = rx.recv() { if atx.send(ev).is_err() { break; } } });

    let key = Arc::new(key.clone());
    let sem = Arc::new(tokio::sync::Semaphore::new(max_inflight));
    let spent = Arc::new(std::sync::atomic::AtomicU64::new(0));
    let fired = Arc::new(std::sync::atomic::AtomicU64::new(0));
    let start_bal = native_balance(rpc, user).await.unwrap_or(0);
    let deadline = Instant::now() + Duration::from_secs(minutes * 60);

    // In-engine balance kill-switch: poll every 8s; if net loss exceeds --max-loss-sol, stop the whole run.
    {
        let (rpc2, user2, stop2) = (rpc.clone(), user, stop.clone());
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_secs(8)).await;
                if stop2.load(Ordering::Relaxed) { break; }
                if let Ok(b) = native_balance(&rpc2, user2).await {
                    if start_bal.saturating_sub(b) > loss_cap {
                        eprintln!("  KILL-SWITCH: net down {} lamports > {} cap — stopping run.", start_bal.saturating_sub(b), loss_cap);
                        stop2.store(true, Ordering::Relaxed); break;
                    }
                }
            }
        });
    }

    // --close-leaders <file>: LEADER-PROXIMITY GATE. Fire only when the create slot's leader is network-close to us
    // (pubkey set from pinging the cluster). Interleaved probe proved close leaders land in-time 84% vs 62% far, so
    // skipping far-leader launches concentrates buys on the slots we can actually win same-slot — no stake needed.
    let close_set: Option<std::collections::HashSet<String>> = arg("--close-leaders").map(|p|
        std::fs::read_to_string(&p).unwrap_or_default().lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect());
    let slot_leader: std::collections::HashMap<u64, String> = if close_set.is_some() {
        let m = leader_map(rpc).await;
        eprintln!("CLOSE-LEADER GATE ON: {} close leaders, {} slots mapped (current + next epoch)", close_set.as_ref().map(|s| s.len()).unwrap_or(0), m.len());
        m
    } else { std::collections::HashMap::new() };
    let mut skipped_far = 0u64;
    let mut skipped_inflight = 0u64;
    let mut rx_t: std::collections::HashMap<Pk, u64> = std::collections::HashMap::new();
    let uri_whitelist = has("--uri-whitelist");
    let uri_blacklist = has("--uri-blacklist");
    let mut skipped_host = 0u64;
    let mut dedup = MintDedup::new(20000); // cross-feed de-dup (erpc + Kaldera): never double-buy a mint seen on both feeds
    let mut det = DetLog::new(_feeds.names.clone());
    set_slot_clock(rpc).await;

    eprintln!("\nSNIPE-LIVE (CONCURRENT): dev_buy>={min_dev_buy}, per-buy cap {max_sol} SOL, TOTAL spend cap {max_total} SOL, loss kill-switch {max_loss} SOL, max_inflight {max_inflight}, {minutes}min. Fires every qualifying launch in parallel.");

    // RACE GATE (default off): same watch as the paper loop. With no race flag the launch goes straight to `ready` and is
    // fired in the same iteration, exactly as before.
    let mut race = RaceWatch::new(RaceCfg::from_args());
    if race.cfg.active() || race.cfg.dev_from_cap { eprintln!("RACE: {}", race.cfg.describe()); }
    let mut ready: Vec<(Launch, u64)> = Vec::new();
    loop {
        if Instant::now() >= deadline || stop.load(Ordering::Relaxed) { break; }
        if spent.load(Ordering::Relaxed) + spend_per > total_cap { eprintln!("  TOTAL spend cap reached — no more fires."); break; }
        let wait = if race.cfg.active() { race.next_wait() } else { Duration::from_secs(2) };
        let ev = match tokio::time::timeout(wait, arx.recv()).await { Ok(Some(e)) => Some(e), Ok(None) => break, Err(_) => None };
        det.health(&_feeds);
        if let Some(arbx::feeds::Event::Status { feed, msg }) = &ev { eprintln!("  FEEDSTATUS feed={} {msg}", det.name(*feed)); }
        if let Some(arbx::feeds::Event::Tx(a)) = ev {
            // DET FIX: the current slot for leader targeting / send_slot comes from the shred feed (the leader's slot as it
            // is being produced). The 250 ms getSlot poller alone lagged the create slot by 2-3 slots (live_land_fast.log:
            // send_slot 458515365 for a create in 458515368), so tpu-direct aimed at leaders already past.
            send::tpu::SLOT.fetch_max(a.slot, Ordering::Relaxed);
            det.note(&a);
            // DET FIX: a top-level create, else pump's router create (CPI) decoded from the router's own args
            let cand = match snipe::detect_launch(&a.tx) { Some(l) => Some((l, false)), None if !det.no_router => router_launch(&a.tx).map(|l| (l, true)), None => None };
            match cand {
                None => {
                    if let Some(m) = snipe::detect_cpi_create(&a.tx) { det.create(&a, &m, "cpi", "verdict=cpi_not_decoded"); }
                    if race.cfg.active() { race.observe(&a.tx); }
                }
                Some((mut launch, via_router)) => 'create: {
                    if det.dev_sized_only && !via_router { launch.dev_buy_lamports = snipe::dev_buy_sized(&a.tx); }
                    race_dev_fix(&race.cfg, &mut launch, &a.tx);
                    let quote = snipe::create_quote_mint(&a.tx);
                    let verdict = det.verdict(&launch, &a.tx, quote, min_dev_buy, max_dev_buy_lam, allow_nonvanilla, uri_whitelist, uri_blacklist);
                    let first = det.create(&a, &launch.mint, if via_router { "router" } else if launch.is_create_v2 { "v2" } else { "v1" },
                        &format!("dev={} dev_sized={} quote={} verdict={verdict}", launch.dev_buy_lamports, snipe::dev_buy_sized(&a.tx),
                            quote.map(|q| b58(&q)[..8].to_string()).unwrap_or_else(|| "sol".into())));
                    if !first { break 'create; }
                    if !dedup.first(launch.mint) { break 'create; } // same create seen on the other feed -> skip the duplicate
                    // DET FIX: our buy is WSOL-quoted + Token-2022: a non-SOL or legacy-SPL launch would revert (fees lost)
                    if quote.is_some() && !det.allow_nonsol { break 'create; }
                    if !launch.is_create_v2 && !det.allow_legacy { break 'create; }
                    if launch.dev_buy_lamports < min_dev_buy { break 'create; }
                    if launch.dev_buy_lamports > max_dev_buy_lam { break 'create; } // whale gate: dev>8 SOL is poison (50% dump)
                    if !allow_nonvanilla && !launch.is_snipeable() { break 'create; }
                    if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; break 'create; }
                    if uri_blacklist && snipe::is_bot_launchpad(&a.tx) { skipped_host += 1; break 'create; }
                    // leader-proximity gate: only fire when the create slot's leader is close (skip far/unknown).
                    // DET FIX: an UNKNOWN leader (slot outside the mapped epochs) no longer counts as far: it used to skip
                    // every launch after an epoch boundary (the map held one epoch, fetched once at start).
                    if close_set.as_ref().map(|cs| slot_leader.get(&a.slot).map(|l| !cs.contains(l)).unwrap_or(false)).unwrap_or(false) {
                        skipped_far += 1; break 'create;
                    }
                    rx_t.insert(launch.mint, a.t_rx); if rx_t.len() > 4096 { rx_t.clear(); }
                    if !race.cfg.active() || race.add(&launch, &a.tx, a.slot) { ready.push((launch, a.slot)); }
                }
            }
        }
        if race.cfg.active() { ready.extend(race.due()); race.shadow.clear(); } // shadows are paper-only: never fired live
        for (launch, create_slot) in ready.drain(..) {
        // reserve a concurrency slot (never block the detector) and budget
        // DET: a full --max-inflight SKIPS the launch (live): count it, so the backpressure cost is visible
        let permit = match sem.clone().try_acquire_owned() { Ok(p) => p, Err(_) => { skipped_inflight += 1; eprintln!("  SKIP-INFLIGHT slot={create_slot} mint={} (max_inflight {max_inflight} busy)", b58(&launch.mint)); continue } };
        let rx_age_us = rx_t.get(&launch.mint).map(|t| arbx::feeds::clock::now_ns().saturating_sub(*t) / 1000).unwrap_or(0);
        if spent.fetch_add(spend_per, Ordering::Relaxed) + spend_per > total_cap { spent.fetch_sub(spend_per, Ordering::Relaxed); break; }
        fired.fetch_add(1, Ordering::Relaxed);
        let (key2, rpc2, path2) = (key.clone(), rpc.clone(), path.clone());
        tokio::spawn(async move {
            let _permit = permit;
            eprintln!("  FIRE slot={create_slot} mint={} dev_buy={} rx_to_fire_us={rx_age_us}", b58(&launch.mint), launch.dev_buy_lamports);
            if let Err(e) = round_trip_launch(&key2, user, &rpc2, &path2, &launch, cap_lamports, max_sol, land_timeout, Some(create_slot)).await {
                eprintln!("  position {} ended: {e:#}", b58(&launch.mint));
            }
        });
        } // ready.drain
    }

    if close_set.is_some() { eprintln!("CLOSE-LEADER GATE: skipped {skipped_far} far-leader launches"); }
    eprintln!("MAX-INFLIGHT: skipped {skipped_inflight} qualifying launches (all {max_inflight} slots busy)");
    if uri_whitelist { eprintln!("URI-HOST GATE: skipped {skipped_host} non-trusted-host launches"); }
    eprintln!("\nSNIPE-LIVE: window ended — draining {} in-flight positions ...", max_inflight - sem.available_permits());
    let _ = tokio::time::timeout(Duration::from_secs(30), sem.acquire_many(max_inflight as u32)).await;
    let end_bal = native_balance(rpc, user).await.unwrap_or(start_bal);
    eprintln!("=== SNIPE-LIVE DONE === fired {} positions; net {} SOL (start {} end {})",
        fired.load(Ordering::Relaxed), (end_bal as i64 - start_bal as i64) as f64 / 1e9, start_bal as f64/1e9, end_bal as f64/1e9);
    Ok(())
}

/// The shared buy -> read-balance -> sell -> report round-trip on a resolved Launch (from --mint or the feed).
/// `create_slot` (snipe-once only) adds the create->buy slot delta: did we snipe same-slot. GATED by the caller.
#[allow(clippy::too_many_arguments)]
async fn round_trip_launch(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, launch: &Launch,
    cap_lamports: u64, max_sol: f64, land_timeout: Duration, create_slot: Option<u64>) -> Result<()> {
    let t_rt = Instant::now();
    let mint = launch.mint;

    // DEMAND GATE (live, additive): if --demand-window-ms>0, watch the live curve for up to that window and only
    // proceed to buy if price reaches --demand-min-r x floor (early-demand confirmation, like the paper filter).
    // NOTE: waiting forfeits same-slot/floor fill by design. demand-window=0 (default) = unchanged behavior.
    let demand_window_ms = arg_u64("--demand-window-ms", 0);
    if demand_window_ms > 0 {
        let demand_min_r = arg_f64("--demand-min-r", 1.05);
        let floor_px = pump_floor_px(launch.dev_buy_lamports);
        let t0 = Instant::now();
        let mut confirmed = false;
        while t0.elapsed() < Duration::from_millis(demand_window_ms) {
            if let Some((vt, vq)) = curve_reserves(rpc, &launch.bonding_curve).await {
                if vt > 0 && floor_px > 0.0 {
                    let r = (vq as f64 / vt as f64) / floor_px;
                    if r >= demand_min_r { confirmed = true; break; }
                }
            }
            tokio::time::sleep(Duration::from_millis(150)).await;
        }
        if !confirmed {
            eprintln!("  DEMAND-SKIP mint={} (no {:.2}x floor within {}ms)", b58(&launch.mint), demand_min_r, demand_window_ms);
            return Ok(());
        }
        eprintln!("  DEMAND-OK mint={} reached >={:.2}x floor", b58(&launch.mint), demand_min_r);
    }

    // --- BUY leg (recent blockhash, no nonce) ---
    // Slippage floor: compute min_tokens_out from the live curve so a co-sniper pushing the price up between our
    // read and our land makes the buy REVERT rather than fill at a bad price. --min-tokens-out overrides (manual);
    // otherwise expected_out = vt*spend/(vq+spend) discounted by --slip-bps (default 2000 = 20%, comfortably over
    // pump's ~1% fee + same-slot curve drift). floor<=1 only when the curve can't be read (fail open, like before).
    let spend = arg_u64("--spend-lamports", 2_000_000);
    let fill_cap = arg("--fill-cap").and_then(|s| s.parse::<f64>().ok());
    let min_out = if let Some(m) = arg_u64_opt("--min-tokens-out") {
        m
    } else if let Some(cap) = fill_cap {
        // DETERMINISTIC fill cap: floor is computable from dev_buy alone (no curve read, never fails open). We require
        // at least spend/(cap*floor_px) tokens, so any fill worse than `cap`x floor makes the buy REVERT (cost = fees
        // only, no token exposure). This is the "only buy at <=cap x floor or don't trade" guard.
        let floor_px = pump_floor_px(launch.dev_buy_lamports);
        let moc = if floor_px > 0.0 { (spend as f64 / (cap * floor_px)).floor() as u64 } else { 1 };
        eprintln!("  FILL CAP {:.3}x: dev_buy={} floor_px={:.3e} spend={} -> min_tokens_out={} (reverts if our fill > {:.3}x floor)",
            cap, launch.dev_buy_lamports, floor_px, spend, moc.max(1), cap);
        moc.max(1)
    } else {
        match curve_reserves(rpc, &launch.bonding_curve).await {
            Some((vt, vq)) if vt > 0 => {
                let expected = (vt as u128 * spend as u128 / (vq as u128 + spend as u128)) as u64;
                let slip_bps = arg_u64("--slip-bps", 2000).min(10_000);
                let floor = (expected as u128 * (10_000 - slip_bps) as u128 / 10_000) as u64;
                eprintln!("  slippage floor: curve vt={} vq={} expected_out={} slip={}bps -> min_tokens_out={}", vt, vq, expected, slip_bps, floor.max(1));
                floor.max(1)
            }
            _ => { eprintln!("  slippage floor: curve unreadable -> min_tokens_out=1 (fail open)"); 1 }
        }
    };
    let (buy_ixs, spend) = build_buy(user, launch, None, 2_000_000, min_out); // default 0.002 SOL
    if spend > cap_lamports { bail!("REFUSED: buy spend {} lamports exceeds --max-sol cap {} lamports ({:.6} SOL)", spend, cap_lamports, max_sol); }
    eprintln!("\nROUND-TRIP (LIVE): mint={} buy spend={} lamports ({:.6} SOL) via {} ...", b58(&mint), spend, spend as f64 / 1e9, path.name);

    eprintln!("  BUY-PREP {:.1} ms (round_trip entry -> send_and_poll)", t_rt.elapsed().as_secs_f64() * 1e3);
    let (bal_start, buy) = tokio::join!(async { native_balance(rpc, user).await.unwrap_or(0) },
                                        send_and_poll(key, user, rpc, path, &buy_ixs, land_timeout));
    let buy = buy?;
    match buy.land_slot {
        Some(land) => eprintln!("  BUY  sig={} send_slot={} land_slot={} delta={} ok={}", buy.sig, buy.send_slot, land, land as i64 - buy.send_slot as i64, buy.ok),
        None => bail!("BUY did not land within {:?} (sig {}) — aborting round-trip, no sell attempted", land_timeout, buy.sig),
    }
    // Fill-cap revert: the buy landed but failed its min_tokens_out guard (fill worse than the cap). No tokens bought,
    // cost = fees only. This is the intended "don't trade a bad fill" outcome, not an error.
    if fill_cap.is_some() && !buy.ok {
        eprintln!("  FILL-CAP REVERT: buy landed but min_tokens_out not met (fill > cap) — no position, cost = fees only. Skipping.");
        return Ok(());
    }

    // --- read our token balance (buyer ATA under TOKEN-2022) ---
    // DET: the two post-buy reads run concurrently (was 2 sequential RPC round trips before the first sell leg)
    let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
    let (bal_after_buy, amount) = tokio::join!(async { native_balance(rpc, user).await.unwrap_or(bal_start) }, token_balance(rpc, &ata));
    let amount = amount?;
    eprintln!("  tokens received: {amount} (ATA {})", b58(&ata));
    if amount == 0 { bail!("no tokens in the buyer ATA after the buy landed — aborting before the sell (ATA {})", b58(&ata)); }

    // --- EXIT: price-reactive ladder (--exit-ladder) replaces the fixed --hold-ms sell.
    if has("--exit-ladder") {
        return exit_ladder(key, user, rpc, path, launch, amount, spend, bal_start, bal_after_buy, &buy, create_slot, land_timeout).await;
    }

    // --- HOLD (ride the launch-slot move, like the sniper's ~3s holds) before selling.
    let hold_ms = arg_u64("--hold-ms", 0);
    if hold_ms > 0 {
        eprintln!("  HOLDING {} ms before the sell (riding the move) ...", hold_ms);
        tokio::time::sleep(Duration::from_millis(hold_ms)).await;
    }

    // --- SELL leg (all of it, min_sol_output=0; recent blockhash). sell_message_ixs also UNWRAPS the WSOL ATA
    // (closeAccount -> native SOL) and reclaims the empty base-ATA rent after the sell.
    let cu = arg_u64("--cu-limit", 120_000) as u32;
    let price = arg_u64("--sell-cu-price-micro", arg_u64("--cu-price-micro", 3_000_000)); // sells: own (low) fee, buys keep --cu-price-micro
    let sell_ixs = snipe_build::sell_message_ixs(user, launch, amount, 0, cu, price, has("--wrap"));
    let sell = send_and_poll(key, user, rpc, sp(path), &sell_ixs, land_timeout).await?;
    match sell.land_slot {
        Some(land) => eprintln!("  SELL sig={} send_slot={} land_slot={} delta={} ok={}", sell.sig, sell.send_slot, land, land as i64 - sell.send_slot as i64, sell.ok),
        None => eprintln!("  SELL NOT SEEN within {:?} (sig {}) — position may still be held; check on chain", land_timeout, sell.sig),
    }
    let bal_end = native_balance(rpc, user).await.unwrap_or(bal_after_buy);

    // --- report ---
    println!("\n========== ROUND-TRIP RESULT ==========");
    println!("mint             {}", b58(&mint));
    if let Some(cs) = create_slot {
        println!("create_slot      {cs}");
        println!("create -> buy    {}  (buy land_slot - create_slot: did we snipe same-slot)", buy.land_slot.map_or("not landed".to_string(), |l| (l as i64 - cs as i64).to_string()));
    }
    println!("buy              sig={} land_slot={:?} delta={:?}", buy.sig, buy.land_slot, buy.land_slot.map(|l| l as i64 - buy.send_slot as i64));
    println!("tokens received  {amount}");
    println!("sell             sig={} land_slot={:?} delta={:?}", sell.sig, sell.land_slot, sell.land_slot.map(|l| l as i64 - sell.send_slot as i64));
    println!("native balance   start={} after_buy={} end={} (lamports)", bal_start, bal_after_buy, bal_end);
    println!("buy cost         {} lamports ({:.6} SOL)  [start - after_buy]", bal_start.saturating_sub(bal_after_buy), bal_start.saturating_sub(bal_after_buy) as f64 / 1e9);
    println!("sell return      {} lamports ({:.6} SOL)  [end - after_buy]", bal_end.saturating_sub(bal_after_buy), bal_end.saturating_sub(bal_after_buy) as f64 / 1e9);
    println!("round-trip cost  {} lamports ({:.6} SOL)  [start - end = fees + curve spread]", bal_start.saturating_sub(bal_end), bal_start.saturating_sub(bal_end) as f64 / 1e9);
    println!("=======================================");
    Ok(())
}

/// Bonding-curve spot price (quote per token) from the curve account: virtual_token_reserves u64 @8,
/// virtual_quote_reserves u64 @16 (post-disc). price = vq / vt. None if unreadable or vt==0.
async fn curve_price(rpc: &rpc::Rpc, bonding_curve: &Pk) -> Option<f64> {
    let (vt, vq) = curve_reserves(rpc, bonding_curve).await?;
    if vt == 0 { return None; }
    Some(vq as f64 / vt as f64)
}

/// Raw virtual reserves (virtual_token_reserves @8, virtual_quote_reserves @16) from the bonding-curve account.
/// Used to size the buy slippage floor: tokens_out ≈ vt*quote_in/(vq+quote_in) on the constant-product curve.
async fn curve_reserves(rpc: &rpc::Rpc, bonding_curve: &Pk) -> Option<(u64, u64)> {
    let v = rpc.call("getAccountInfo", serde_json::json!([b58(bonding_curve), { "encoding": "base64", "commitment": "processed" }])).await.ok()?;
    let data_b64 = v["value"]["data"][0].as_str()?;
    let raw = base64::engine::general_purpose::STANDARD.decode(data_b64).ok()?;
    if raw.len() < 24 { return None; }
    let vt = u64::from_le_bytes(raw[8..16].try_into().ok()?);
    let vq = u64::from_le_bytes(raw[16..24].try_into().ok()?);
    Some((vt, vq))
}

/// One sell leg: cu-limit [+ cu-price] + sell_exact_tokens_in_v3(qty). When `close`, also UNWRAP the WSOL ATA
/// (closeAccount -> native SOL) and reclaim the empty base-ATA rent — only on the FINAL leg (partials keep the
/// quote proceeds accruing in the WSOL ATA and keep the base ATA open for the next partial).
#[allow(clippy::too_many_arguments)]
async fn do_sell(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, launch: &Launch, qty: u64, close: bool, cu: u32, price: u64, land_timeout: Duration) -> Result<Landed> {
    let mut ixs = vec![build::cu_limit_ix(cu)];
    if price > 0 { ixs.push(build::cu_price_ix(price)); }
    ixs.push(snipe_build::sell_ix(user, launch, qty, 0));
    if close {
        // unwrap WSOL only when we wrapped (v3 SOL trades settle native; closing a nonexistent WSOL ATA would fail)
        if has("--wrap") {
            ixs.push(build::close_account_ix(snipe_build::assoc_quote(&user), user, user, *pda::TOKEN_PROGRAM));
        }
        ixs.push(build::close_account_ix(snipe_build::assoc_user(&user, &launch.mint), user, user, *pda::TOKEN_2022));
    }
    send_and_poll(key, user, rpc, sp(path), &ixs, land_timeout).await
}

/// Price-reactive exit ladder (--exit-ladder). After the buy lands: de-risk early, ladder out while flat, RIDE the
/// tail with a trailing stop once it runs, CUT losers fast, and deadline-flush. Each leg goes through the WARM path.
/// Phase params (flags, defaults MEASURED from the target wallet's 200 snipes, 2026-10-14): --derisk-frac 0.30
/// (his median first-sell fraction), --ride-mult 1.40 (where he stops laddering + holds the runner; winner peak
/// median 1.28), --trail-frac 0.92 (winners exit at ~0.92 of peak = ~8% trailing stop), --cut-r 0.80 (deep hard stop —
/// tolerate shallow early drawdown so dip-then-rip runners survive; the old 0.95 + eager fade clipped them),
/// --ladder-frac 0.25 (his scale-out chunk), --exit-cap-ms 9000 (covers winner last-sell p75=31/p90=66 slots).
/// Replaying this ladder on his own entries reproduces ~84% of his PnL (+32 SOL @ 2% slip). One retry per non-landing
/// sell, then stop and flush the remainder.
#[allow(clippy::too_many_arguments)]
async fn exit_ladder(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, launch: &Launch,
    amount: u64, buy_spend: u64, bal_start: u64, bal_after_buy: u64, buy: &Landed, create_slot: Option<u64>, land_timeout: Duration) -> Result<()> {
    let cap = Duration::from_millis(arg_u64("--exit-cap-ms", 3200));
    let derisk_frac = arg_f64("--derisk-frac", 0.0);
    let ride_mult = arg_f64("--ride-mult", 2.0);
    let trail_frac = arg_f64("--trail-frac", 0.90);
    let cut_r = arg_f64("--cut-r", 0.0);
    let ladder_frac = arg_f64("--ladder-frac", 0.0);
    // DEAD-TOKEN INSTANT CHECK: the "only the dev (and us) bought it" loser filter. Read the curve ONCE right after our
    // buy lands and measure SOL from OTHER buyers (= real SOL in the curve minus the dev-buy minus our spend). If nobody
    // else has bought (others < --min-others-sol), it's a dead/rug launch — dump immediately. No waiting: a real token
    // already has co-snipers in the curve by the time our buy lands, and its price is up, so this never cuts a mover.
    let min_others_sol = arg_f64("--min-others-sol", 0.0); // 0 = off
    let cu = arg_u64("--cu-limit", 120_000) as u32;
    let price = arg_u64("--sell-cu-price-micro", arg_u64("--cu-price-micro", 3_000_000)); // sells: own (low) fee, buys keep --cu-price-micro
    let mint = launch.mint;
    let entry = buy_spend as f64 / amount.max(1) as f64; // lamports(quote)/token at the fill

    // --- instant dead-token check (one read, no delay) ---
    if min_others_sol > 0.0 {
        if let Some((_vt, vq)) = curve_reserves(rpc, &launch.bonding_curve).await {
            let others_sol = (vq as f64 - PUMP_VQ0 - launch.dev_buy_lamports as f64 - buy_spend as f64) / 1e9;
            if others_sol < min_others_sol {
                eprintln!("  DEAD-no-demand: only dev+us in curve (others={:.4} SOL < {:.4}) — dumping immediately.", others_sol, min_others_sol);
                let sell_ixs = snipe_build::sell_message_ixs(user, launch, amount, 0, cu, price, has("--wrap"));
                let sell = send_and_poll(key, user, rpc, sp(path), &sell_ixs, land_timeout).await?;
                eprintln!("  SELL[DEAD] qty={amount} land_slot={:?} ok={}", sell.land_slot, sell.ok);
                return Ok(());
            }
            eprintln!("  demand ok: others={:.4} SOL bought beyond dev+us — holding.", others_sol);
        }
    }

    let mut remaining = amount;
    let mut peak_r = 1.0f64;
    let mut riding = false;
    let mut first = true;
    let mut last_sell_slot = send::tpu::SLOT.load(Ordering::Relaxed);
    let deadline = Instant::now() + cap;
    let mut legs: Vec<(f64, u64, Landed)> = Vec::new();
    eprintln!("\nEXIT-LADDER: amount={amount} entry={entry:.6e} cap={cap:?} derisk={derisk_frac} ride>={ride_mult} trail={trail_frac} cut<={cut_r} ladder={ladder_frac}");

    loop {
        if remaining == 0 { break; }
        let cur_slot = send::tpu::SLOT.load(Ordering::Relaxed);
        let r = match curve_price(rpc, &launch.bonding_curve).await { Some(p) => p / entry, None => 1.0 };
        if r > peak_r { peak_r = r; }
        if !riding && r >= ride_mult { riding = true; eprintln!("  RIDE armed at r={r:.3} (peak {peak_r:.3})"); }

        let (mut qty, final_, why): (u64, bool, &str) = if first {
            first = false;
            ((amount as f64 * derisk_frac) as u64, false, "de-risk")
        } else if r <= cut_r {
            (remaining, true, "CUT")
        } else if riding && r <= peak_r * trail_frac {
            (remaining, true, "RIDE-trail")
        } else if Instant::now() >= deadline {
            (remaining, true, "deadline")
        // NO eager "fading" dump: the old branch dumped the whole position the instant r ticked <1.0 for one slot,
        // which clipped dip-then-rip RUNNERS on their initial dip (validated 2026-10-14: removing it + deeper cut_r
        // recovers +15 R on >=1.5x runners, win 25%->43%). Below-entry exits now happen ONLY via the deeper cut_r hard
        // stop, the trail, or the time cap — tolerating shallow early drawdown the way the target does.
        } else if !riding && (1.0..ride_mult).contains(&r) && cur_slot.saturating_sub(last_sell_slot) >= 4 {
            ((remaining as f64 * ladder_frac) as u64, false, "ladder")
        } else {
            (0, false, "")
        };
        qty = qty.min(remaining);

        if qty > 0 {
            let close = final_ || qty == remaining;
            let mut sell = do_sell(key, user, rpc, path, launch, qty, close, cu, price, land_timeout).await?;
            if sell.land_slot.is_none() {
                eprintln!("  SELL[{why}] qty={qty} not seen — retry once");
                sell = do_sell(key, user, rpc, path, launch, qty, close, cu, price, land_timeout).await?;
            }
            match sell.land_slot {
                Some(land) => {
                    eprintln!("  SELL[{why}] qty={qty} r={r:.3} peak={peak_r:.3} land={land} delta={} ok={}", land as i64 - sell.send_slot as i64, sell.ok);
                    remaining = remaining.saturating_sub(qty);
                    last_sell_slot = send::tpu::SLOT.load(Ordering::Relaxed);
                    legs.push((r, qty, sell));
                    if final_ || remaining == 0 { break; }
                }
                None => {
                    eprintln!("  SELL[{why}] qty={qty} NOT SEEN after retry (sig {}) — stopping ladder, will flush remainder", sell.sig);
                    legs.push((r, qty, sell));
                    break;
                }
            }
        }
        tokio::time::sleep(Duration::from_millis(250)).await;
    }

    // robustness: always try to flush any remainder (sell all actually-held tokens, with unwrap+close)
    let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
    let held = token_balance(rpc, &ata).await.unwrap_or(0);
    if held > 0 {
        eprintln!("  FLUSH remaining {held} tokens ...");
        let _ = do_sell(key, user, rpc, path, launch, held, true, cu, price, land_timeout).await;
    }

    let bal_end = native_balance(rpc, user).await.unwrap_or(bal_after_buy);
    println!("\n========== EXIT-LADDER RESULT ==========");
    println!("mint             {}", b58(&mint));
    if let Some(cs) = create_slot {
        println!("create -> buy    {}  (buy land_slot - create_slot: same-slot snipe?)", buy.land_slot.map_or("n/a".to_string(), |l| (l as i64 - cs as i64).to_string()));
    }
    println!("entry_price      {entry:.6e} (lamports quote / token)");
    println!("tokens bought    {amount}");
    println!("legs ({}):", legs.len());
    for (r, q, s) in &legs {
        println!("  r={r:.3} qty={q} land_slot={:?} ok={}", s.land_slot, s.ok);
    }
    let buy_cost = bal_start.saturating_sub(bal_after_buy);
    let sell_ret = bal_end.saturating_sub(bal_after_buy);
    println!("buy cost         {buy_cost} lamports ({:.6} SOL)  [start - after_buy]", buy_cost as f64 / 1e9);
    println!("sell return      {sell_ret} lamports ({:.6} SOL)  [end - after_buy]", sell_ret as f64 / 1e9);
    let pnl = bal_end as i64 - bal_start as i64;
    println!("net PnL          {pnl} lamports ({:.6} SOL)  [end - start]", pnl as f64 / 1e9);
    println!("========================================");
    Ok(())
}

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
    /// FAST: hold the DETECT lines until after the prepare / fire (flush), instead of a stderr write per create
    defer: bool,
    buf: Vec<String>,
}

impl DetLog {
    fn new(names: Vec<String>) -> Self {
        DetLog { names, slot_t0: Default::default(), first: Default::default(), order: Default::default(), last_health: Instant::now(),
            dev_sized_only: has("--dev-sized-only"), allow_nonsol: has("--allow-nonsol-quote"), allow_legacy: has("--allow-legacy-create"),
            no_router: has("--no-router"), defer: false, buf: Vec::new() }
    }
    fn flush(&mut self) { for l in self.buf.drain(..) { fastfire::log_line(l); } }
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
        let line = format!("  DETECT feed={} first={} dt_us={dt_us} slot={} t_rx={} poh_ms={} lag_ms={lag} mint={} kind={kind} sig={} {extra}",
            self.name(a.feed), first as u8, a.slot, a.t_rx, poh.map(|p| format!("{p:.1}")).unwrap_or_else(|| "-".into()), b58(mint),
            &a.tx.sig_b58()[..16]);
        if self.defer { self.buf.push(line); } else { eprintln!("{line}"); }
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

/// FIX2 (2026-10-19, /root/fix2/NOTES.md): the LANDING gates shared by the paper and live loops (all default off).
///  --max-create-ms X           skip a launch whose create sits later than X ms into its slot on the leader's PoH clock.
///                              Source, in order: the PoH index the shred feeds build while walking the slot from its first
///                              data set (feeds::poh_index: dz-leader / dz-retrans-eu, needs --race-glued), else the entries
///                              feed's (erpc) PoH position of any copy of the create. Checked when the race gate decides
///                              (the glued run is read from the same walk, so the create's position is known by then).
///  --max-create-ms-unknown P   pass|skip (default skip) when no PoH position is known at the decision.
///  --log-create-poh            a CREATE-POH line ~120 ms after every create's first arrival (its PoH ms, source, sig):
///                              the input of the on-chain validation (/root/fix2/pohval.py).
///  paper (--paper-trade) only: --close-leaders is applied here too, at the decision, and every decided launch gets a
///  GATE line (leader, close?, create_ms, verdict), so one paper run gives the rule-#2 count with and without each gate.
struct LandGate {
    max_ms: Option<f64>,
    unknown_pass: bool,
    log_poh: bool,
    /// mint -> (create sig8, slot, PoH ms of any arrival, create sig (b58, 16 chars), first arrival)
    info: std::collections::HashMap<Pk, (u64, u64, Option<f64>, String, Instant)>,
    order: std::collections::VecDeque<Pk>,
    pend_log: std::collections::VecDeque<Pk>,
    pub late: u64,
    pub unknown: u64,
    pub passed: u64,
    pub lines: Vec<String>,
}

impl LandGate {
    fn new() -> Self {
        let max_ms = arg("--max-create-ms").and_then(|s| s.parse::<f64>().ok());
        let unknown_pass = arg("--max-create-ms-unknown").map(|s| s == "pass").unwrap_or(false);
        LandGate { max_ms, unknown_pass, log_poh: has("--log-create-poh"), info: Default::default(), order: Default::default(), pend_log: Default::default(),
            late: 0, unknown: 0, passed: 0, lines: Vec::new() }
    }
    fn on(&self) -> bool { self.max_ms.is_some() || self.log_poh }
    fn describe(&self) -> String {
        format!("LAND-GATE: max_create_ms={} (unknown -> {}) log_create_poh={}", self.max_ms.map(|x| format!("{x:.0}")).unwrap_or_else(|| "off".into()),
            if self.unknown_pass { "pass" } else { "skip" }, self.log_poh)
    }
    /// every create arrival (first copy or not, before the dedup): remember its sig8 / slot and any PoH position
    fn note(&mut self, a: &arbx::feeds::Arrival, mint: &Pk) {
        if !self.on() { return; }
        let poh = a.poh.as_ref().and_then(|p| p.ms());
        match self.info.get_mut(mint) {
            Some(e) => { if e.2.is_none() { e.2 = poh; } }
            None => {
                self.info.insert(*mint, (sig8_of(&a.tx.sig), a.slot, poh, a.tx.sig_b58()[..16].to_string(), Instant::now()));
                self.order.push_back(*mint);
                if self.log_poh { self.pend_log.push_back(*mint); }
                while self.order.len() > 20_000 { if let Some(o) = self.order.pop_front() { self.info.remove(&o); } }
            }
        }
    }
    /// the create's PoH ms into its slot and where it came from
    fn create_ms(&self, mint: &Pk) -> (Option<f64>, &'static str) {
        let Some(e) = self.info.get(mint) else { return (None, "none") };
        if let Some((p, _)) = arbx::feeds::poh_index().get(e.0) { if let Some(ms) = p.ms() { return (Some(ms), "poh-index"); } }
        match e.2 { Some(ms) => (Some(ms), "arrival"), None => (None, "none") }
    }
    /// at the decision: true = fire. Logs (deferred) one GATE-CREATE-MS line
    fn check(&mut self, mint: &Pk, slot: u64) -> bool {
        let Some(max) = self.max_ms else { return true };
        let (ms, src) = self.create_ms(mint);
        let pass = match ms { Some(x) => x <= max, None => self.unknown_pass };
        match (ms, pass) { (None, _) => self.unknown += 1, (Some(_), false) => self.late += 1, _ => {} }
        if pass { self.passed += 1; }
        self.lines.push(format!("  GATE-CREATE-MS slot={slot} mint={} create_ms={} src={src} max={max:.0} verdict={}", b58(mint),
            ms.map(|x| format!("{x:.1}")).unwrap_or_else(|| "-".into()), if pass { "pass" } else if ms.is_none() { "skip_unknown" } else { "skip_late" }));
        pass
    }
    /// off the hot path: CREATE-POH lines for creates first seen >= 120 ms ago, and the held GATE lines
    fn flush(&mut self) {
        for l in self.lines.drain(..) { fastfire::log_line(l); }
        while let Some(m) = self.pend_log.front().copied() {
            let Some(e) = self.info.get(&m) else { self.pend_log.pop_front(); continue };
            if e.4.elapsed() < Duration::from_millis(120) { break; }
            self.pend_log.pop_front();
            let (ms, src) = self.create_ms(&m);
            let e = &self.info[&m];
            fastfire::log_line(format!("  CREATE-POH slot={} mint={} sig={} poh_ms={} src={src} arrival_poh_ms={}", e.1, b58(&m), e.3,
                ms.map(|x| format!("{x:.1}")).unwrap_or_else(|| "-".into()), e.2.map(|x| format!("{x:.1}")).unwrap_or_else(|| "-".into())));
        }
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
    if !warm_probe && !shadow && !round_trip && !snipe_once && !simulate && !paper_trade && !unwrap && !has("--sell-held") && !has("--ack-probe")
        && !has("--landed-via-probe") && !has("--jito-poll-probe") {
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

    // ---- FIX2 zero-cost probes of the attribution / status-poll code on OLD signatures / bundle ids (no send path)
    if let Some(list) = arg("--landed-via-probe") { return fix2::landed_via_probe(&list).await; }
    if let Some(list) = arg("--jito-poll-probe") {
        let base = probe.sends.iter().find(|s| s.kind == config::SendKind::JitoBundle).and_then(|s| config::expand(&s.url)).context("--jito-poll-probe: no jito-bundle [[send]] in --config")?;
        return fix2::jito_poll_probe(&base, &list).await;
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
    // ---- LAT (2026-10-19): multi-path fan-out / per-leader-client routing / per-path send log (all default off)
    if let Some(list) = arg("--multi-send") {
        let mut v = Vec::new();
        for n in list.split([',', '+']).map(str::trim).filter(|s| !s.is_empty()) {
            match paths.index(n) { Some(i) => v.push(paths.list[i].clone()), None => bail!("--multi-send {n}: no such [[send]] path (or it failed to build: see the send notes)") }
        }
        eprintln!("snipe_engine: MULTI-SEND buys via {} (one signature, every path's tip)", v.iter().map(|p| p.name.as_str()).collect::<Vec<_>>().join(", "));
        let _ = lat::MULTI.set(v);
    }
    if let Some(spec) = arg("--route-by-client") {
        let r = lat::parse_routes(&spec, &paths)?;
        let mut ks: Vec<_> = r.keys().cloned().collect(); ks.sort();
        for c in ks { eprintln!("snipe_engine: ROUTE {c:8} -> {}", r[&c].iter().map(|p| p.name.as_str()).collect::<Vec<_>>().join(" + ")); }
        let _ = lat::ROUTES.set(r);
    }
    if lat::ROUTES.get().is_some() || has("--ack-probe") {
        match lat::refresh(&rpc).await {
            Ok(m) => eprintln!("  {m}"),
            Err(e) if lat::ROUTES.get().is_some() => bail!("--route-by-client: the leader book failed: {e:#}"),
            Err(e) => eprintln!("  leader book: {e:#}"),
        }
        lat::start_refresh(rpc.clone(), stop.clone());
    }
    if let Some(f) = arg("--send-log") {
        let file = std::fs::OpenOptions::new().create(true).append(true).open(&f).with_context(|| format!("--send-log {f}"))?;
        let _ = lat::SEND_LOG.set(std::sync::Mutex::new(file));
        eprintln!("snipe_engine: per-path send log -> {f}");
    }

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
    if let Some(n) = arg_u64_opt("--ack-probe") {
        // ZERO COST: junk requests only (nothing can land); allowed without --live
        let _ = wait_until_warm_all(&paths).await;
        lat::ack_probe(&key, user, &rpc, &paths, &path, n).await?;
        stop.store(true, Ordering::Relaxed);
        return Ok(());
    }
    // LAT: warm EVERY fan-out path before the first fire (not only the --send-path one)
    if lat::ROUTES.get().is_some() || lat::MULTI.get().is_some() { wait_until_warm_all(&paths).await; }
    // FAST (--fast-send / --fast-bench): our own send connections, templates, the hot-thread fire
    if has("--fast-send") || has("--fast-bench") {
        if live && !has("--fast-send") { bail!("--fast-bench is zero-network: never with --live"); }
        let (k2, p2, m2, junk, st2) = (key.clone(), paths.clone(), path.clone(), has("--junk-fanout"), stop.clone());
        tokio::task::block_in_place(|| fastfire::init(&k2, user, &p2, &m2, junk, st2))?;
        if let Some(n) = arg_u64_opt("--fast-probe") {
            // ZERO COST: N junk fires through the fast path (synthetic launch), 1.5 s apart; needs --junk-fanout
            if !has("--junk-fanout") || live { bail!("--fast-probe sends junk only: it needs --junk-fanout and never --live"); }
            fastfire::probe(n as usize).await;
            stop.store(true, Ordering::Relaxed);
            return Ok(());
        }
        if let Some(n) = arg_u64_opt("--fast-bench") {
            fastfire::bench(n as usize);
            stop.store(true, Ordering::Relaxed);
            return Ok(());
        }
    }
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
    if snipe_once && has("--busy-poll") {
        // FAST --busy-poll: the event loop gets its own thread (it spins on the feed channel; a spinning tokio worker
        // would starve the tasks queued behind it)
        let h = tokio::runtime::Handle::current();
        tokio::task::block_in_place(|| h.block_on(run_snipe_once(probe, &key, user, &rpc, &path, live, &stop)))?;
    } else if snipe_once {
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

/// LAT: one keep-alive round trip on every path at once, twice (the pool then holds a warm connection for each); prints
/// the second round's RTT per path
async fn wait_until_warm_all(paths: &Arc<send::Paths>) {
    for round in 0..2 {
        let hs: Vec<_> = paths.list.iter().map(|p| { let p = p.clone(); tokio::spawn(async move { (p.name.clone(), p.warm().await) }) }).collect();
        let mut line = Vec::new();
        for h in hs {
            if let Ok((n, r)) = h.await {
                line.push(match r { Ok(Some(d)) => format!("{n} {:.2} ms", d.as_secs_f64() * 1e3), Ok(None) => format!("{n} -"), Err(e) => format!("{n} ERR {}", format!("{e:#}").chars().take(60).collect::<String>()) });
            }
        }
        if round == 1 { eprintln!("  WARM-ALL: {}", line.join(" | ")); }
        tokio::time::sleep(Duration::from_millis(200)).await;
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
    send_and_poll_at(key, user, rpc, path, ixs, land_timeout, None).await
}

/// `send_and_poll` for a BUY aimed at `target_slot` (the create's slot: LAT per-leader-client routing reads its leader)
#[allow(clippy::too_many_arguments)]
async fn send_and_poll_at(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, ixs: &[build::Ix], land_timeout: Duration, target_slot: Option<u64>) -> Result<Landed> {
    let t_sp = Instant::now();
    // Tipped send paths (nozomi / jito-tx / helius / 0slot ...) require a top-level System tip transfer to one of the
    // path's tip accounts, or Path::check refuses the send. Tipless paths (staked-rpc / tpu-direct) return None -> unchanged.
    // --also-send: only for non-sell sends (a sell goes through SELL_PATH), and only to a different path.
    // DET FIX: "is this a buy" is read from the instructions (the pump buy disc). The old test (path != SELL_PATH) also
    // double-sent every SELL, paying the also-path's tip, whenever --sell-path was not given (sells then use the buy path).
    let is_buy = ixs.iter().any(|ix| ix.data.starts_with(&snipe_build::BUY_EXACT_QUOTE_IN_V3_DISC));
    // LAT: the fan-out set: --route-by-client / --multi-send for buys; else [path] (+ --also-send for buys), as before
    let (mut fan, mut meta) = if is_buy { lat::buy_paths(path, ALSO_PATH.get(), target_slot) } else { (vec![path.clone()], lat::Meta { route: "single".into(), ..Default::default() }) };
    let cached = BLOCKHASH_CACHE.lock().unwrap().filter(|(_, t)| t.elapsed() < Duration::from_secs(20)).map(|(h, _)| h);
    let blockhash = match cached { Some(h) => h, None => rpc.latest_blockhash().await.context("getLatestBlockhash")?.0 };
    // one tip per tip family for every path in the fan-out, the CU limit raised for the extra transfers; a tx over the
    // 1232-byte packet limit drops paths from the end (their tips with them) until it fits
    let (raw, tips) = lat::build_tx(key, user, ixs, &mut fan, blockhash)?;
    let sig = send::first_signature(&raw).context("signed tx has no signature")?;
    let mut sig_bytes = [0u8; 64];
    sig_bytes.copy_from_slice(&bs58::decode(&sig).into_vec()?);
    let send_slot = match send::tpu::SLOT.load(Ordering::Relaxed) { 0 => rpc.slot().await.unwrap_or(0), s => s };
    meta.sig = sig.clone();
    meta.bytes = raw.len();
    meta.tips = tips.iter().map(|t| t.1).sum();
    eprintln!("  SEND-PREP {:.1} ms (send_and_poll entry -> send)", t_sp.elapsed().as_secs_f64() * 1e3);
    if fan.len() > 1 || lat::ROUTES.get().is_some() || lat::MULTI.get().is_some() {
        eprintln!("  SEND-FAN sig={} {} slot={:?} leader={} client={} paths={} tips={} lamports bytes={}", &sig[..16.min(sig.len())], meta.route, target_slot,
            meta.leader.chars().take(8).collect::<String>(), meta.client, fan.iter().map(|p| p.name.as_str()).collect::<Vec<_>>().join(","), meta.tips, meta.bytes);
    }
    if fan.len() > 1 {
        // LAT: every path at once, each on its own task (no path waits for another's write); the buy proceeds as soon as
        // ONE path accepts, the rest log their SEND-ACK when they answer. All refused -> error, as before
        let t0 = Instant::now();
        let raw = Arc::new(raw);
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
        for p in &fan {
            let (p, raw, tx, m) = (p.clone(), raw.clone(), tx.clone(), meta.clone());
            tokio::spawn(async move {
                let r = lat::send_one(&p, &raw, t0, &m).await;
                let _ = tx.send((p.name.clone(), r.err().map(|e| e.msg)));
            });
        }
        drop(tx);
        let mut errs = Vec::new();
        let mut any_ok = false;
        while let Some((name, e)) = rx.recv().await {
            match e { None => { any_ok = true; break; } Some(m) => errs.push(format!("{name}: {m}")) }
        }
        if !any_ok { bail!("send refused on every path: {}", errs.join(" / ")); }
        fix2::spawn_jito_poll(&fan, &sig, 0);
        let out = poll_land(rpc, sig.clone(), sig_bytes, send_slot, land_timeout).await;
        jito_results(&fan, &meta);
        fix2::spawn_landed_via(&fan, &meta, out.land_slot, 0);
        return Ok(out);
    }
    // single path (the old code path): its SEND-ACK, and the tipless --fallback-path on a refusal
    let t0 = Instant::now();
    if let Err(e) = lat::send_one(path, &raw, t0, &meta).await {
        // DET (--fallback-path, default off): a refusal (HTTP 429 from Helius' keyless 1 req/s/IP limit, or the
        // local max_per_sec guard) re-sends the SAME signed tx through a tipless fallback path instead of
        // losing the trade. Only tipless fallbacks (staked-rpc) are accepted at start-up: no extra tip is paid.
        match FALLBACK_PATH.get().filter(|f| f.name != path.name) {
            Some(f) => {
                lat::send_one(f, &raw, t0, &meta).await
                    .map_err(|e2| anyhow::anyhow!("send refused: {}: {e} / fallback {}: {e2}", path.name, f.name))?;
                eprintln!("  (fallback: {} refused: {e}; re-sent via {})", path.name, f.name);
            }
            None => bail!("send refused: {e}"),
        }
    }
    let out = poll_land(rpc, sig, sig_bytes, send_slot, land_timeout).await;
    if is_buy { jito_results(&fan, &meta); }
    Ok(out)
}

/// poll getSignatureStatuses until the tx lands or `land_timeout`
async fn poll_land(rpc: &rpc::Rpc, sig: String, sig_bytes: [u8; 64], send_slot: u64, land_timeout: Duration) -> Landed {
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
    out
}

/// LAT: after the land poll, what each jito-bundle path's result stream said about our bundle (accepted / processed with
/// its slot / rejected / dropped ...): which path carried the landing on Jito leaders
fn jito_results(fan: &[Arc<send::Path>], meta: &lat::Meta) {
    for p in fan {
        let Some(j) = &p.jito else { continue };
        // FIX2: with each verdict's detail and decoded error code (a would-fail's reason was dropped before)
        let s = if j.verdicts(&meta.sig).is_empty() { String::new() } else { fix2::verdict_str(j, &meta.sig) };
        eprintln!("  JITO-RESULT path={} sig={} {}", p.name, &meta.sig[..16.min(meta.sig.len())], if s.is_empty() { "(no result yet)".to_string() } else { s.clone() });
        lat::log_json(serde_json::json!({ "ev": "jito_result", "t_ns": arbx::feeds::clock::now_ns(), "sig": meta.sig, "path": p.name, "results": s }));
    }
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

/// FIX2: Err on an RPC failure (token_balance maps it to 0, which looks like "not created yet")
async fn token_balance_strict(rpc: &rpc::Rpc, ata: &Pk) -> Result<u64> {
    let v = rpc.call("getTokenAccountBalance", serde_json::json!([b58(ata), { "commitment": "processed" }])).await?;
    v["value"]["amount"].as_str().and_then(|s| s.parse::<u64>().ok()).context("getTokenAccountBalance: no amount")
}

/// FIX2: up to `tries` reads 250 ms apart; Some(amount) on the first answer (a missing/closed account reads 0), None if
/// every read failed
async fn token_balance_retry(rpc: &rpc::Rpc, ata: &Pk, tries: u32) -> Option<u64> {
    for k in 0..tries.max(1) {
        if k > 0 { tokio::time::sleep(Duration::from_millis(250)).await; }
        match rpc.call("getTokenAccountBalance", serde_json::json!([b58(ata), { "commitment": "processed" }])).await {
            Ok(v) => if let Some(a) = v["value"]["amount"].as_str().and_then(|s| s.parse::<u64>().ok()) { return Some(a) },
            Err(e) => { let m = format!("{e:#}"); if m.contains("could not find account") || m.contains("Invalid param") { return Some(0); } }
        }
    }
    None
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
//   --race-min-bundle-sol F / --race-max-bundle-sol F  gate: creator bundle SOL (sum of its buys within --race-bundle-ms)
//   --race-create-tip-prefix P  gate: the create tx's largest SOL transfer goes to an account starting with P ("moon" = Lunar)
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
    /// LAT --race-early: decide PASS the moment the (monotone) bundle condition is met instead of waiting out the window
    /// (same selection; the 3 ms Gate B window cost ~5 ms rx->fire with the 1 ms loop tick)
    early: bool,
    /// --race-max-name-len L: token name <= L chars (0 = off)
    max_name_len: usize,
    /// --race-min-bundle-sol / --race-max-bundle-sol: creator bundle SOL bounds (lamports)
    min_bundle_sol: u64,
    max_bundle_sol: u64,
    /// --race-create-tip-prefix: create tx's largest non-signer SOL transfer goes to an account with this base58 prefix
    create_tip_prefix: Option<String>,
    pros: std::collections::HashSet<Pk>,
    /// GAP --race-glued: the creator bundle is the on-chain labels' "glued" run: the unbroken run of buys of the mint
    /// right after the create in the leader's order (slot order from an entries/shred feed), each leg's SOL simulated on
    /// the curve (fee-adjusted, slippage-checked). Decided when the run is closed (first non-buy) or at run_max_ms.
    glued: bool,
    run_max_ms: f64,
}

impl RaceCfg {
    fn from_args() -> Self {
        let gate = has("--race-gate");
        let window_cfg = arg_f64("--race-window-ms", 0.0).max(0.0);
        let bundle: i8 = match arg("--race-bundle").as_deref() { Some("yes") => 1, Some("no") => -1, _ => 0 };
        let bundle_ms = arg_f64("--race-bundle-ms", 3.0);
        // a bundle condition needs to see the first bundle_ms of the stream before deciding
        let min_bundle = arg_u64("--race-min-bundle", 0) as u32;
        let bsol_flags = arg("--race-min-bundle-sol").is_some() || arg("--race-max-bundle-sol").is_some();
        let window_ms = if bundle != 0 || min_bundle > 0 || bsol_flags { window_cfg.max(bundle_ms) } else { window_cfg };
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
            early: has("--race-early"),
            max_name_len: arg_u64("--race-max-name-len", 0) as usize,
            min_bundle_sol: (arg_f64("--race-min-bundle-sol", 0.0) * 1e9) as u64,
            max_bundle_sol: (arg_f64("--race-max-bundle-sol", 1e9) * 1e9) as u64,
            create_tip_prefix: arg("--race-create-tip-prefix"),
            pros,
            glued: has("--race-glued"),
            run_max_ms: arg_f64("--race-run-max-ms", 40.0),
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
    format!("slot={slot} mint={} dev={} dev_sized={} dev_cap={} kind={} host={} cu_price={} cu_limit={} nsig={} nkeys={} luts={} v1={} nix={} t22={} tip={} tip_to={} creator={} name_len={} sym={} name={} uri={}",
        b58(&launch.mint), launch.dev_buy_lamports, snipe::detect_launch(tx).map(|l| l.dev_buy_lamports).unwrap_or(0), snipe::dev_buy_cap_lamports(tx),
        snipe::dev_buy_kind(tx), if ci.uri_host.is_empty() { "-".to_string() } else { ci.uri_host.clone() }, ci.cu_price, ci.cu_limit, ci.nsig, ci.nkeys,
        ci.n_lookups, ci.v1, ci.n_ixs, ci.t22, ci.tip_lamports, ci.tip_to.map(|k| b58(&k)).unwrap_or_else(|| "-".into()), b58(&launch.creator),
        ci.name.chars().count(), clean(&ci.symbol), clean(&ci.name),
        snipe::create_strings(tx).map(|(_, _, u)| u.chars().filter(|c| !c.is_whitespace()).take(200).collect::<String>()).filter(|u| !u.is_empty()).unwrap_or_else(|| "-".into()))
}

struct RacePend {
    launch: Launch,
    slot: u64,
    t0: Instant,
    cset: std::collections::HashSet<Pk>,
    bundle_n: u32,
    /// creator-bundle buy SOL seen within bundle_ms (sized amount, or cap-family priced on the curve)
    bundle_sol: u64,
    /// (ms after the create, payer, sol hint lamports, cu price, is_buy)
    out: Vec<(f64, Pk, u64, u64, bool)>,
    decided: bool,
    static_ok: bool,
    pass: bool,
    /// signatures already counted (the same tx arrives once per feed)
    sigs: std::collections::HashSet<[u8; 64]>,
    /// GAP --race-glued: the create's sig8, the curve's virtual SOL after the create tx, what each tx touching the mint does
    csig8: u64,
    vq_create: u64,
    legs: std::collections::HashMap<u64, snipe::Legs>,
    last_eval: Option<Instant>,
}

struct RaceWatch { cfg: RaceCfg, pend: std::collections::HashMap<Pk, RacePend>, shadow: Vec<(Launch, u64)>, defer: Option<Vec<String>>,
    /// GAP --race-glued: sig8 of every tx the feeds forwarded (to tell "a pump tx of another mint" from "not decoded yet")
    seen: std::collections::HashSet<u64>, seen_q: std::collections::VecDeque<u64> }

fn sig8_of(sig: &[u8; 64]) -> u64 { u64::from_be_bytes(sig[..8].try_into().unwrap()) }

impl RaceWatch {
    fn new(cfg: RaceCfg) -> Self {
        if cfg.glued { arbx::feeds::ORDER_ON.store(true, Ordering::Relaxed); }
        RaceWatch { cfg, pend: Default::default(), shadow: Vec::new(), defer: None, seen: Default::default(), seen_q: Default::default() }
    }
    /// GAP: note every forwarded tx (all feeds; duplicates are harmless)
    fn note_hit(&mut self, tx: &arbx::tx::Tx) {
        if !self.cfg.glued { return; }
        let k = sig8_of(&tx.sig);
        if self.seen.insert(k) { self.seen_q.push_back(k); if self.seen_q.len() > 400_000 { if let Some(o) = self.seen_q.pop_front() { self.seen.remove(&o); } } }
    }
    /// GAP --race-glued: (legs, curve SOL, unknown legs, closed, slot order found) of the run after the create
    fn glued_eval(&self, p: &RacePend) -> (u32, u64, u32, bool, bool) {
        let Some(tail) = arbx::feeds::slot_order().after(p.slot, p.csig8, 64) else { return (0, 0, 0, false, false) };
        let (mut n, mut sol, mut unk, mut vq) = (0u32, 0u64, 0u32, p.vq_create);
        for (k, hit) in tail {
            if !hit { return (n, sol, unk, true, true); }
            match p.legs.get(&k) {
                Some(snipe::Legs::Buys(v)) => match snipe::simulate_legs(vq, v) {
                    Some(s_) => { n += 1; sol = sol.saturating_add(s_); vq = vq.saturating_add(s_); }
                    None => return (n, sol, unk, true, true), // the leg would revert: a failed tx ends the run
                },
                Some(snipe::Legs::Unknown) => { n += 1; unk += 1; }
                Some(snipe::Legs::NotBuy) => return (n, sol, unk, true, true),
                None => {
                    if self.seen.contains(&k) { return (n, sol, unk, true, true); } // a pump tx of another mint
                    return (n, sol, unk, false, true); // forwarded but not processed yet: wait
                }
            }
        }
        (n, sol, unk, false, true)
    }
    /// FAST: print the held decision lines (after the fire)
    fn flush(&mut self) { if let Some(b) = &mut self.defer { for l in b.drain(..) { fastfire::log_line(l); } } }

    /// static (create-time) part of the gate.
    fn static_ok(&self, launch: &Launch, tx: &arbx::tx::Tx) -> bool {
        let name_ok = self.cfg.max_name_len == 0
            || snipe::create_strings(tx).map(|(n, _, _)| n.chars().count() <= self.cfg.max_name_len).unwrap_or(false);
        let tip_ok = match &self.cfg.create_tip_prefix {
            None => true,
            Some(pf) => snipe::create_info(tx).tip_to.map(|k| b58(&k).starts_with(pf.as_str())).unwrap_or(false),
        };
        tip_ok && name_ok && launch.dev_buy_lamports >= self.cfg.min_dev && launch.dev_buy_lamports <= self.cfg.max_dev
    }

    /// a launch passed the engine's base filter: log it and start watching. Returns true when it should be fired NOW
    /// (gate off, or gate on with no window and the static conditions met).
    fn add(&mut self, launch: &Launch, tx: &arbx::tx::Tx, slot: u64) -> bool {
        let static_ok = self.static_ok(launch, tx);
        if self.cfg.log { let l = format!("  RACE seen {} static_ok={static_ok}", race_feat_line(launch, tx, slot)); match &mut self.defer { Some(b) => b.push(l), None => eprintln!("{l}") } }
        let mut cset: std::collections::HashSet<Pk> = tx.keys.iter().take(tx.num_signers as usize).copied().collect();
        cset.insert(launch.creator);
        let fire_now = !self.cfg.gate || (self.cfg.window_ms <= 0.0 && static_ok);
        let vq_create = match snipe::bundle_legs(tx, &launch.mint) {
            Some(snipe::Legs::Buys(v)) => snipe::CURVE_VQ0 + snipe::simulate_legs(snipe::CURVE_VQ0, &v).unwrap_or(0),
            _ => snipe::CURVE_VQ0,
        };
        self.pend.insert(launch.mint, RacePend { launch: launch.clone(), slot, t0: Instant::now(), cset, bundle_n: 0, bundle_sol: 0, out: Vec::new(),
            decided: fire_now || !self.cfg.gate || !static_ok, static_ok, pass: fire_now, sigs: Default::default(),
            csig8: sig8_of(&tx.sig), vq_create, legs: Default::default(), last_eval: None });
        if self.cfg.gate && !static_ok {
            let l = format!("  RACE reject-static slot={slot} mint={}", b58(&launch.mint));
            match &mut self.defer { Some(b) => b.push(l), None => eprintln!("{l}") }
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
            let glued = self.cfg.glued;
            let Some(p) = self.pend.get_mut(&mint) else { continue };
            if !p.sigs.insert(tx.sig) { continue; } // duplicate delivery from the second feed
            if glued { if let Some(l) = snipe::bundle_legs(tx, &mint) { p.legs.insert(sig8_of(&tx.sig), l); } }
            let ms = p.t0.elapsed().as_secs_f64() * 1e3;
            let signers: Vec<Pk> = tx.keys.iter().take(tx.num_signers as usize).copied().collect();
            let bvq = snipe::CURVE_VQ0 + p.launch.dev_buy_lamports + p.bundle_sol;
            let bsol = match touch {
                snipe::MintTouch::Buy(s) => s,
                snipe::MintTouch::BuyCap { tokens, max_sol } => { let est = snipe::curve_cost(bvq, tokens); if max_sol > 0 && max_sol < est { max_sol } else { est } }
                _ => 0,
            };
            if signers.iter().any(|s| p.cset.contains(s)) {
                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; p.bundle_sol = p.bundle_sol.saturating_add(bsol); }
                continue;
            }
            if ms <= bundle_ms && !is_pro {
                if matches!(touch, snipe::MintTouch::Buy(_) | snipe::MintTouch::BuyCap { .. }) { p.bundle_n += 1; p.bundle_sol = p.bundle_sol.saturating_add(bsol); }
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
            // LAT --race-early: pass now when the bundle condition (it only grows) already holds and nothing else waits on
            // the window (no outsider count, no "no bundle" rule, no bundle-SOL maximum). A launch that passes early would
            // pass at the window end too: the selection is unchanged, only the decision is earlier.
            let early = self.cfg.early && !p.decided && p.static_ok && !self.cfg.count_out && self.cfg.bundle != -1
                && self.cfg.max_bundle_sol >= 1_000_000_000_000_000_000 && p.bundle_n >= self.cfg.min_bundle.max(1)
                && p.bundle_sol >= self.cfg.min_bundle_sol && el <= self.cfg.window_ms;
            if self.cfg.glued && !p.decided {
                // GAP --race-glued: decide when the run after the create is closed (or at run_max_ms); re-evaluate at most
                // every 0.2 ms (the slot order grows as data sets complete)
                if p.last_eval.is_some_and(|t| t.elapsed() < Duration::from_micros(200)) && el < self.cfg.run_max_ms { continue; }
                p.last_eval = Some(Instant::now());
                let ord = arbx::feeds::slot_order();
                let _ = ord;
                let (n, gsol, unk, closed, found) = {
                    // inline glued_eval (self is borrowed mutably by the loop)
                    let tail = arbx::feeds::slot_order().after(p.slot, p.csig8, 64);
                    match tail {
                        None => (0u32, 0u64, 0u32, false, false),
                        Some(tail) => {
                            let (mut n, mut sol, mut unk, mut vq) = (0u32, 0u64, 0u32, p.vq_create);
                            let mut res = None;
                            for (k, hit) in tail {
                                if !hit { res = Some((n, sol, unk, true, true)); break; }
                                match p.legs.get(&k) {
                                    Some(snipe::Legs::Buys(v)) => match snipe::simulate_legs(vq, v) {
                                        Some(s_) => { n += 1; sol = sol.saturating_add(s_); vq = vq.saturating_add(s_); }
                                        None => { res = Some((n, sol, unk, true, true)); break; }
                                    },
                                    Some(snipe::Legs::Unknown) => { n += 1; unk += 1; }
                                    Some(snipe::Legs::NotBuy) => { res = Some((n, sol, unk, true, true)); break; }
                                    None => { res = Some((n, sol, unk, self.seen.contains(&k), true)); break; }
                                }
                            }
                            res.unwrap_or((n, sol, unk, false, true))
                        }
                    }
                };
                if closed || el >= self.cfg.run_max_ms {
                    let (on, osol) = (p.bundle_n, p.bundle_sol);
                    p.bundle_n = n; p.bundle_sol = gsol;
                    let (no, solo, maxcu) = Self::counts(p, self.cfg.window_ms.max(el));
                    let bundle_ok = closed && unk == 0 && n >= self.cfg.min_bundle && gsol >= self.cfg.min_bundle_sol && gsol <= self.cfg.max_bundle_sol
                        && match self.cfg.bundle { 1 => n > 0, -1 => n == 0, _ => true };
                    p.pass = p.static_ok && bundle_ok && (!self.cfg.count_out || (no >= self.cfg.min_out && solo >= self.cfg.min_out_sol));
                    p.decided = true;
                    let line = format!("  RACE decide slot={} mint={} at_ms={:.1} out_n={no} out_sol={:.3} max_cu={maxcu} bundle_n={n} bundle_sol={:.3} glued_closed={closed} glued_unknown={unk} order={} old_bundle_n={on} old_bundle_sol={:.3} pass={}",
                        p.slot, b58(mint), el, solo as f64 / 1e9, gsol as f64 / 1e9, if found { "yes" } else { "none" }, osol as f64 / 1e9, p.pass);
                    match &mut self.defer { Some(b) => b.push(line), None => eprintln!("{line}") }
                    if p.pass { ready.push((p.launch.clone(), p.slot)); }
                    else if self.cfg.track_rejects { self.shadow.push((p.launch.clone(), p.slot)); }
                }
            }
            if !self.cfg.glued && !p.decided && (el >= self.cfg.window_ms || early) {
                let (n, sol, maxcu) = Self::counts(p, self.cfg.window_ms);
                let bundle_ok = p.bundle_n >= self.cfg.min_bundle
                    && p.bundle_sol >= self.cfg.min_bundle_sol && p.bundle_sol <= self.cfg.max_bundle_sol
                    && match self.cfg.bundle { 1 => p.bundle_n > 0, -1 => p.bundle_n == 0, _ => true };
                p.pass = p.static_ok && bundle_ok && (!self.cfg.count_out || (n >= self.cfg.min_out && sol >= self.cfg.min_out_sol));
                p.decided = true;
                let line = format!("  RACE decide slot={} mint={} at_ms={:.1} out_n={n} out_sol={:.3} max_cu={maxcu} bundle_n={} pass={}",
                    p.slot, b58(mint), el, sol as f64 / 1e9, p.bundle_n, p.pass);
                match &mut self.defer { Some(b) => b.push(line), None => eprintln!("{line}") }
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
                    let l = format!("  RACE obs slot={} mint={} n25={n25} n50={n50} n100={n100} n200={n200} n_obs={nall} sol100={:.3} sol200={:.3} sol_obs={:.3} max_cu100={cu100} first_ms={first:.1} bundle_n={} bundle_sol={:.3} fired={} outs={}",
                        p.slot, b58(mint), s100 as f64 / 1e9, s200 as f64 / 1e9, sall as f64 / 1e9, p.bundle_n, p.bundle_sol as f64 / 1e9, p.pass, if outs.is_empty() { "-".to_string() } else { outs });
                    match &mut self.defer { Some(b) => b.push(l), None => eprintln!("{l}") }
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
    // FIX2: the landing gates in paper too (at the decision, with a GATE line per decided launch: the census)
    let mut gate = LandGate::new();
    if gate.on() { eprintln!("{}", gate.describe()); }
    let close_set: Option<std::collections::HashSet<String>> = arg("--close-leaders").map(|p|
        std::fs::read_to_string(&p).unwrap_or_default().lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect());
    let slot_leader: std::collections::HashMap<u64, String> = if close_set.is_some() {
        let m = leader_map(rpc).await;
        eprintln!("CLOSE-LEADER GATE ON (paper, at the decision): {} close leaders, {} slots mapped (current + next epoch)", close_set.as_ref().map(|s| s.len()).unwrap_or(0), m.len());
        m
    } else { std::collections::HashMap::new() };
    let (mut gate_far, mut gate_late, mut gate_pass) = (0u64, 0u64, 0u64);
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
            if race.cfg.glued { race.note_hit(&a.tx); }
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
                    gate.note(&a, &launch.mint);
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
        if fired && (close_set.is_some() || gate.max_ms.is_some()) {
            // FIX2 census: both gates, logged for every launch the race gate passed
            let leader = slot_leader.get(&create_slot).cloned();
            let far = close_set.as_ref().map(|cs| leader.as_ref().map(|l| !cs.contains(l)).unwrap_or(false)).unwrap_or(false);
            let (ms, src) = gate.create_ms(&launch.mint);
            let ok_ms = gate.check(&launch.mint, create_slot);
            let verdict = if far { "skip_far" } else if !ok_ms { if ms.is_none() { "skip_unknown" } else { "skip_late" } } else { "pass" };
            eprintln!("  GATE slot={create_slot} mint={} leader={} close={} create_ms={} src={src} verdict={verdict}", b58(&launch.mint),
                leader.as_deref().map(|l| &l[..8.min(l.len())]).unwrap_or("?"), !far, ms.map(|x| format!("{x:.1}")).unwrap_or_else(|| "-".into()));
            if far { gate_far += 1; } else if !ok_ms { gate_late += 1; } else { gate_pass += 1; }
            if far || !ok_ms { eprintln!("  PAPER gate-skip slot={create_slot} mint={} ({verdict})", b58(&launch.mint)); continue; }
        }
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
        if gate.on() { gate.flush(); }
    }
    if close_set.is_some() || gate.max_ms.is_some() { eprintln!("LAND GATES (paper): race-gate passes {} -> skipped far {gate_far}, skipped late/unknown {gate_late}, fired {gate_pass}", gate_far + gate_late + gate_pass); }

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
    // LAT --junk-fanout: the ZERO-COST dry run of this loop: detection, gates, routing, the real tx built + signed and
    // DISCARDED, and only junk (undecodable) bytes go to the routed paths. Never with --live.
    let junk = has("--junk-fanout");
    if junk && live { bail!("--junk-fanout is the zero-cost dry run: never combine it with --live"); }
    if junk { eprintln!("\nJUNK-FANOUT (ZERO COST): real detection + routing; every fire sends only undecodable junk to its paths, nothing can land"); }
    if !live && !junk { eprintln!("\nDRY: --snipe-once --concurrent needs --live --max-sol <cap> --max-total-sol <cap>."); return Ok(()); }
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
    // FAST --busy-poll: no bridge thread; the loop spins on the feed's crossbeam channel itself
    let busy = has("--busy-poll");
    if !busy { let rx = rx.clone(); std::thread::spawn(move || { while let Ok(ev) = rx.recv() { if atx.send(ev).is_err() { break; } } }); } else { drop(atx); }
    let fast = fastfire::get();
    if fast.is_some() {
        if arg_u64("--demand-window-ms", 0) > 0 { bail!("--fast-send fires at the decision: it cannot wait a --demand-window-ms"); }
        if arg("--fill-cap").is_none() && arg_u64_opt("--min-tokens-out").is_none() { bail!("--fast-send needs --fill-cap or --min-tokens-out (min_out is computed at the create, no curve read)"); }
        eprintln!("FAST-SEND: prepare at the create, write at the decision from the event loop{}", if busy { " (busy-poll)" } else { "" });
    }
    if busy { if let Some(c) = arg_u64_opt("--pin-core") { eprintln!("BUSY-POLL: event loop pinned to core {c}: {}", arbx::fast::pin_to_core(c as usize)); } }
    let fill_cap_v = arg("--fill-cap").and_then(|s| s.parse::<f64>().ok());
    let min_out_fixed = arg_u64_opt("--min-tokens-out");
    let mut preps: std::collections::HashMap<Pk, fastfire::Prep> = std::collections::HashMap::new();
    let mut ev_st = [0u64; 4];

    let key = Arc::new(key.clone());
    let sem = Arc::new(tokio::sync::Semaphore::new(max_inflight));
    let spent = Arc::new(std::sync::atomic::AtomicU64::new(0));
    let fired = Arc::new(std::sync::atomic::AtomicU64::new(0));
    let start_bal = match native_balance(rpc, user).await {
        Ok(b) => b,
        // FIX2 --strict-balance: without a start balance the kill-switch could never trip (review finding 4)
        Err(e) if has("--strict-balance") => bail!("--strict-balance: the start balance could not be read ({e:#}): the kill-switch needs it"),
        Err(_) => 0,
    };
    if has("--strict-balance") { eprintln!("START BALANCE {} lamports ({:.9} SOL); kill-switch trips below {:.9} SOL", start_bal, start_bal as f64 / 1e9, start_bal.saturating_sub(loss_cap) as f64 / 1e9); }
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
    let mut gate = LandGate::new();
    if gate.on() { eprintln!("{}", gate.describe()); }

    eprintln!("\nSNIPE-LIVE (CONCURRENT): dev_buy>={min_dev_buy}, per-buy cap {max_sol} SOL, TOTAL spend cap {max_total} SOL, loss kill-switch {max_loss} SOL, max_inflight {max_inflight}, {minutes}min. Fires every qualifying launch in parallel.");

    // RACE GATE (default off): same watch as the paper loop. With no race flag the launch goes straight to `ready` and is
    // fired in the same iteration, exactly as before.
    let mut race = RaceWatch::new(RaceCfg::from_args());
    if race.cfg.active() || race.cfg.dev_from_cap { eprintln!("RACE: {}", race.cfg.describe()); }
    if fast.is_some() { race.defer = Some(Vec::new()); det.defer = true; }
    let mut ready: Vec<(Launch, u64)> = Vec::new();
    loop {
        if Instant::now() >= deadline || stop.load(Ordering::Relaxed) { break; }
        if spent.load(Ordering::Relaxed) + spend_per > total_cap { eprintln!("  TOTAL spend cap reached — no more fires."); break; }
        let wait = if race.cfg.active() { race.next_wait() } else { Duration::from_secs(2) };
        let ev = if busy {
            match fastfire::spin_recv(&rx, wait) { Ok(e) => e, Err(()) => break }
        } else {
            match tokio::time::timeout(wait, arx.recv()).await { Ok(Some(e)) => Some(e), Ok(None) => break, Err(_) => None }
        };
        let (t_deq, t_deq_real) = (arbx::fast::mono_ns(), arbx::feeds::clock::now_ns());
        if let Some(arbx::feeds::Event::Tx(a)) = &ev { ev_st = [a.t_rx, a.t_decoded, t_deq_real, t_deq]; }
        det.health(&_feeds);
        if let Some(arbx::feeds::Event::Status { feed, msg }) = &ev { eprintln!("  FEEDSTATUS feed={} {msg}", det.name(*feed)); }
        if let Some(arbx::feeds::Event::Tx(a)) = ev {
            if race.cfg.glued { race.note_hit(&a.tx); }
            // DET FIX: the current slot for leader targeting / send_slot comes from the shred feed (the leader's slot as it
            // is being produced). The 250 ms getSlot poller alone lagged the create slot by 2-3 slots (live_land_fast.log:
            // send_slot 458515365 for a create in 458515368), so tpu-direct aimed at leaders already past.
            send::tpu::SLOT.fetch_max(a.slot, Ordering::Relaxed);
            det.note(&a);
            // DET FIX: a top-level create, else pump's router create (CPI) decoded from the router's own args
            let cand = match snipe::detect_launch(&a.tx) { Some(l) => Some((l, false)), None if !det.no_router => router_launch(&a.tx).map(|l| (l, true)), None => None };
            let t_det = arbx::fast::mono_ns();
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
                    gate.note(&a, &launch.mint);
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
                    if let Some(f) = fast {
                        // FAST: everything but the decision, now (the race gate decides on a later tx)
                        let t_gated = arbx::fast::mono_ns();
                        let min_out = min_out_fixed.unwrap_or_else(|| {
                            let cap = fill_cap_v.unwrap_or(2.5);
                            let floor_px = pump_floor_px(launch.dev_buy_lamports);
                            (if floor_px > 0.0 { (spend_per as f64 / (cap * floor_px)).floor() as u64 } else { 1 }).max(1)
                        });
                        match f.prepare(&launch, a.slot, min_out, [a.t_rx, a.t_decoded, t_deq_real, t_deq, t_det, t_gated]) {
                            Ok(p) => { preps.insert(launch.mint, p); }
                            Err(e) => eprintln!("  FAST prepare {} failed (fires on the old path): {e:#}", b58(&launch.mint)),
                        }
                    }
                    if !race.cfg.active() || race.add(&launch, &a.tx, a.slot) { ready.push((launch, a.slot)); }
                }
            }
        }
        if race.cfg.active() { ready.extend(race.due()); race.shadow.clear(); } // shadows are paper-only: never fired live
        let t_dec = arbx::fast::mono_ns();
        for (launch, create_slot) in ready.drain(..) {
        // FIX2 --max-create-ms: a create late in its slot cannot be beaten into that slot (next 50 ms auction tick / batch)
        if !gate.check(&launch.mint, create_slot) { continue; }
        // reserve a concurrency slot (never block the detector) and budget
        // DET: a full --max-inflight SKIPS the launch (live): count it, so the backpressure cost is visible
        let permit = match sem.clone().try_acquire_owned() { Ok(p) => p, Err(_) => { skipped_inflight += 1; eprintln!("  SKIP-INFLIGHT slot={create_slot} mint={} (max_inflight {max_inflight} busy)", b58(&launch.mint)); continue } };
        let rx_age_us = rx_t.get(&launch.mint).map(|t| arbx::feeds::clock::now_ns().saturating_sub(*t) / 1000).unwrap_or(0);
        if spent.fetch_add(spend_per, Ordering::Relaxed) + spend_per > total_cap { spent.fetch_sub(spend_per, Ordering::Relaxed); break; }
        fired.fetch_add(1, Ordering::Relaxed);
        if let Some(f) = fast {
            if spend_per > cap_lamports { eprintln!("  REFUSED: buy spend {spend_per} lamports exceeds --max-sol cap {cap_lamports} lamports"); continue; }
            // FAST: write every path from here, now; logging, verification and (live) the land poll + exit afterwards
            let p = match preps.remove(&launch.mint).filter(|p| p.made.elapsed() < Duration::from_secs(2)) {
                Some(p) => p,
                None => {
                    let floor_px = pump_floor_px(launch.dev_buy_lamports);
                    let min_out = min_out_fixed.unwrap_or_else(|| (if floor_px > 0.0 { (spend_per as f64 / (fill_cap_v.unwrap_or(2.5) * floor_px)).floor() as u64 } else { 1 }).max(1));
                    match f.prepare(&launch, create_slot, min_out, [0, 0, 0, t_dec, t_dec, t_dec]) { Ok(p) => p, Err(e) => { eprintln!("  FAST prepare failed at the fire: {e:#}"); continue; } }
                }
            };
            let rec = f.fire(&p);
            let ev = ev_st;
            let (key2, rpc2, path2) = (key.clone(), rpc.clone(), path.clone());
            tokio::spawn(async move {
                let _permit = permit;
                eprintln!("  FIRE slot={create_slot} mint={} dev_buy={} rx_to_fire_us={rx_age_us} fast=1", b58(&launch.mint), launch.dev_buy_lamports);
                let first = rec.w.iter().filter(|x| x.4 == "written").map(|x| x.3).min().map(|t| t.saturating_sub(t_dec) as f64 / 1e3);
                eprintln!("  FAST-FIRE tag={} slot={create_slot} mint={} {} leader={} client={} built={} tips={} bytes={} decide_to_first_write_us={} writes: {}", p.id, b58(&launch.mint),
                    p.meta.route, p.meta.leader.chars().take(8).collect::<String>(), p.meta.client, if p.fast_built { "template" } else { "compile" }, p.meta.tips, p.meta.bytes,
                    first.map(|x| format!("{x:.1}")).unwrap_or_else(|| "-".into()),
                    rec.w.iter().map(|x| format!("{}={}@{:.1}us", x.0, x.4, x.3.saturating_sub(t_dec) as f64 / 1e3)).collect::<Vec<_>>().join(" "));
                f.trace_fire(&p, &rec, ev, t_dec);
                f.trace_prep(&p);
                fix2::spawn_jito_poll(&p.fan, &p.meta.sig, p.id);
                if f.junk { return; }
                if let Err(e) = round_trip_fast(&key2, user, &rpc2, &path2, &p, cap_lamports, max_sol, land_timeout).await {
                    eprintln!("  position {} ended: {e:#}", b58(&launch.mint));
                }
            });
            continue;
        }
        let (key2, rpc2, path2) = (key.clone(), rpc.clone(), path.clone());
        tokio::spawn(async move {
            let _permit = permit;
            eprintln!("  FIRE slot={create_slot} mint={} dev_buy={} rx_to_fire_us={rx_age_us}", b58(&launch.mint), launch.dev_buy_lamports);
            if junk {
                if let Err(e) = lat::junk_fire(&key2, user, &path2, &launch, create_slot).await { eprintln!("  junk fire {} failed: {e:#}", b58(&launch.mint)); }
                return;
            }
            if let Err(e) = round_trip_launch(&key2, user, &rpc2, &path2, &launch, cap_lamports, max_sol, land_timeout, Some(create_slot)).await {
                eprintln!("  position {} ended: {e:#}", b58(&launch.mint));
            }
        });
        } // ready.drain
        if gate.on() { gate.flush(); }
        if fast.is_some() {
            det.flush();
            race.flush();
            // creates the gate dropped: trace their prep (stage timings + verification), off the hot path
            if preps.len() > 16 || preps.values().any(|p| p.made.elapsed() > Duration::from_millis(400)) {
                let old: Vec<Pk> = preps.iter().filter(|(_, p)| p.made.elapsed() > Duration::from_millis(400)).map(|(k, _)| *k).collect();
                for k in old { if let (Some(p), Some(f)) = (preps.remove(&k), fast) { tokio::spawn(async move { f.trace_prep(&p) }); } }
            }
        }
    }
    if let Some(f) = fast { for l in f.summary() { eprintln!("FAST: {l}"); } }

    if close_set.is_some() { eprintln!("CLOSE-LEADER GATE: skipped {skipped_far} far-leader launches"); }
    if gate.max_ms.is_some() { eprintln!("CREATE-MS GATE: passed {} skipped late {} skipped unknown {}", gate.passed, gate.late, gate.unknown); }
    eprintln!("MAX-INFLIGHT: skipped {skipped_inflight} qualifying launches (all {max_inflight} slots busy)");
    if uri_whitelist { eprintln!("URI-HOST GATE: skipped {skipped_host} non-trusted-host launches"); }
    eprintln!("\nSNIPE-LIVE: window ended — draining {} in-flight positions ...", max_inflight - sem.available_permits());
    // FIX2: with --sell-robust / --sell-retries an in-flight position may need longer than 30 s to finish its exit
    let drain_s = if has("--sell-robust") || arg_u64("--sell-retries", 0) > 0 {
        30u64.max(land_timeout.as_secs() + arg_u64("--late-land-s", 45) + arg_u64("--sell-retries", 0) * (arg_u64("--sell-retry-s", 4) + 2) + 15)
    } else { 30 };
    let _ = tokio::time::timeout(Duration::from_secs(drain_s), sem.acquire_many(max_inflight as u32)).await;
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
    // LAT: the send future first (tokio::join! polls in order: the buy's request leaves before getBalance is built);
    // the create slot routes the buy by its leader's client (--route-by-client)
    let (buy, bal_start) = tokio::join!(send_and_poll_at(key, user, rpc, path, &buy_ixs, land_timeout, create_slot),
                                        async { native_balance(rpc, user).await.unwrap_or(0) });
    let buy = buy?;
    round_trip_tail(key, user, rpc, path, launch, buy, bal_start, spend, fill_cap, land_timeout, create_slot, min_out).await
}

/// FAST: the buy was written by fastfire::Fast::fire; poll its land, then the same exit as round_trip_launch
#[allow(clippy::too_many_arguments)]
async fn round_trip_fast(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, p: &fastfire::Prep, cap_lamports: u64, max_sol: f64, land_timeout: Duration) -> Result<()> {
    let spend = arg_u64("--spend-lamports", 2_000_000);
    if spend > cap_lamports { bail!("REFUSED: buy spend {} lamports exceeds --max-sol cap {} lamports ({:.6} SOL)", spend, cap_lamports, max_sol); }
    let fill_cap = arg("--fill-cap").and_then(|s| s.parse::<f64>().ok());
    let send_slot = match send::tpu::SLOT.load(Ordering::Relaxed) { 0 => rpc.slot().await.unwrap_or(0), s => s };
    let (buy, bal_start) = tokio::join!(poll_land(rpc, p.meta.sig.clone(), p.sig, send_slot, land_timeout), async { native_balance(rpc, user).await.unwrap_or(0) });
    jito_results(&p.fan, &p.meta);
    fix2::spawn_landed_via(&p.fan, &p.meta, buy.land_slot, p.id);
    round_trip_tail(key, user, rpc, path, &p.launch, buy, bal_start, spend, fill_cap, land_timeout, Some(p.slot), p.min_out).await
}

/// the shared exit after the buy's land poll: fill-cap revert check, token balance, exit ladder / hold + sell, report
#[allow(clippy::too_many_arguments)]
async fn round_trip_tail(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, launch: &Launch, mut buy: Landed, bal_start: u64, spend: u64,
    fill_cap: Option<f64>, land_timeout: Duration, create_slot: Option<u64>, min_out: u64) -> Result<()> {
    let mint = launch.mint;
    // FIX2 --sell-robust: a buy not seen within the land poll may still land (its blockhash lives ~60 s): keep watching its
    // signature AND our token account for --late-land-s (default 45) before giving up, so a late fill is still sold
    let robust = has("--sell-robust");
    if buy.land_slot.is_none() && robust {
        let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
        let mut sb = [0u8; 64];
        if let Ok(v) = bs58::decode(&buy.sig).into_vec() { if v.len() == 64 { sb.copy_from_slice(&v); } }
        let until = Instant::now() + Duration::from_secs(arg_u64("--late-land-s", 45));
        eprintln!("  BUY not seen within {:?} (sig {}) — watching for a late landing ({}s)", land_timeout, buy.sig, arg_u64("--late-land-s", 45));
        while Instant::now() < until && buy.land_slot.is_none() {
            tokio::time::sleep(Duration::from_secs(2)).await;
            if let Ok(v) = rpc.statuses(&[sb]).await { if let Some(Some((land, ok))) = v.into_iter().next() { buy.land_slot = Some(land); buy.ok = ok; break; } }
            if let Ok(b) = token_balance(rpc, &ata).await { if b > 0 { eprintln!("  LATE-LAND: {b} tokens in the ATA (signature status not seen yet)"); buy.ok = true; buy.land_slot = Some(0); break; } }
        }
    }
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
    let mut amount = amount?;
    // FIX2 --sell-robust: a read of 0 / an RPC error right after the landing is re-read (the RPC node may trail the slot),
    // and if it still reads nothing on a successful buy, sell the guaranteed minimum (min_tokens_out) without the close
    let mut close_ata = true;
    if amount == 0 && robust {
        for k in 0..8 {
            tokio::time::sleep(Duration::from_millis(250)).await;
            match token_balance_strict(rpc, &ata).await { Ok(b) if b > 0 => { amount = b; eprintln!("  tokens re-read #{}: {b}", k + 1); break; } _ => {} }
        }
        if amount == 0 && buy.ok && min_out > 1 {
            eprintln!("  token balance still unreadable after the landed buy — selling the guaranteed min_tokens_out {min_out} (no ATA close)");
            amount = min_out;
            close_ata = false;
        }
    }
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
    // FIX2 --sell-retries N (default 0 = one sell, as before): a sell not seen within --sell-retry-s (default 4) or seen
    // failed is re-sent (fresh blockhash, so a new signature) for whatever the token account still holds, up to N times
    let retries = arg_u64("--sell-retries", 0);
    let sell_wait = if retries > 0 { Duration::from_secs(arg_u64("--sell-retry-s", 4)) } else { land_timeout };
    let sell_ixs = if close_ata { snipe_build::sell_message_ixs(user, launch, amount, 0, cu, price, has("--wrap")) }
        else { vec![build::cu_limit_ix(cu), build::cu_price_ix(price), snipe_build::sell_ix(user, launch, amount, 0)] };
    let mut sell = send_and_poll(key, user, rpc, sp(path), &sell_ixs, sell_wait).await?;
    for k in 0..retries {
        if sell.land_slot.is_some() && sell.ok { break; }
        let held = token_balance_retry(rpc, &ata, 4).await;
        eprintln!("  SELL-RETRY {}/{retries}: last sell {} (sig {}); token account holds {held:?}", k + 1,
            if sell.land_slot.is_some() { "landed FAILED" } else { "not seen" }, sell.sig);
        match held {
            Some(0) => { if sell.land_slot.is_none() { eprintln!("  SELL-RETRY: balance 0 — the last sell must have landed"); } break; }
            Some(h) => {
                let ixs = snipe_build::sell_message_ixs(user, launch, h, 0, cu, price, has("--wrap"));
                sell = send_and_poll(key, user, rpc, sp(path), &ixs, sell_wait).await?;
            }
            None => { sell = send_and_poll(key, user, rpc, sp(path), &sell_ixs, sell_wait).await?; }
        }
    }
    match sell.land_slot {
        Some(land) => eprintln!("  SELL sig={} send_slot={} land_slot={} delta={} ok={}", sell.sig, sell.send_slot, land, land as i64 - sell.send_slot as i64, sell.ok),
        None => eprintln!("  SELL NOT SEEN within {:?} (sig {}) — position may still be held; check on chain", sell_wait, sell.sig),
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

// ================================================================================================================
// LAT (2026-10-19, /root/lat/NOTES.md): multi-path fan-out, per-leader-client routing, per-path send log, ack probe.
// All default OFF: without --multi-send / --route-by-client the buy goes exactly as before (path [+ --also-send]).
//  --multi-send a,b,c        every BUY goes to all these paths at once: ONE signed tx (one signature, so it can land
//                            once only), carrying every path's tip (one transfer per tip family: jito-bundle and
//                            jito-tx share Jito's accounts). Sells never fan out (--sell-path).
//  --route-by-client SPEC    per create-slot LEADER CLIENT, the paths a BUY goes to. SPEC = "class=p1+p2;class=...;
//                            default=..." with class in bam|harmonic|jito|fd|agave|other (getClusterNodes clientId:
//                            AgaveBam/FireBAM=bam, Harmonic*=harmonic, JitoLabs=jito, Firedancer/Frankendancer=fd).
//                            When the create slot is its leader's last, the next leader's paths are added too.
//  --send-log FILE           one JSON line per path per buy (route, leader, client, t_off_us, ack_ms, reply) and one
//                            per Jito bundle result: the per-path record for the landing test.
//  --ack-probe N             ZERO COST (no --live needed): print the routing for the coming slots, build + simulate the
//                            multi-tip buy (--mint), then N rounds of junk (undecodable) requests to every routed path
//                            through the warm send clients; per-path ack p50/p90. Nothing can land, nothing is paid.
// ================================================================================================================
mod lat {
    use super::*;
    use base64::Engine as _;
    use std::collections::HashMap;
    use std::sync::{Mutex, OnceLock, RwLock};

    pub static MULTI: OnceLock<Vec<Arc<send::Path>>> = OnceLock::new();
    pub static ROUTES: OnceLock<HashMap<String, Vec<Arc<send::Path>>>> = OnceLock::new();
    pub static SEND_LOG: OnceLock<Mutex<std::fs::File>> = OnceLock::new();
    pub const CLASSES: [&str; 6] = ["bam", "harmonic", "jito", "fd", "agave", "other"];

    pub struct Book { base: u64, idx: Vec<u32>, names: Vec<String>, client: HashMap<String, String> }
    pub static BOOK: RwLock<Option<Book>> = RwLock::new(None);

    pub fn class(client: &str) -> &'static str {
        match client {
            "AgaveBam" | "FireBAM" => "bam",
            c if c.starts_with("Harmonic") => "harmonic",
            "JitoLabs" => "jito",
            "Firedancer" | "Frankendancer" => "fd",
            "Agave" => "agave",
            "" => "unknown",
            _ => "other",
        }
    }

    /// (leader, clientId) of `slot` from the cached book (no network)
    pub fn leader_of(slot: u64) -> Option<(String, String)> {
        let g = BOOK.read().unwrap();
        let b = g.as_ref()?;
        let i = *b.idx.get(slot.checked_sub(b.base)? as usize)?;
        if i == u32::MAX { return None; }
        let l = b.names.get(i as usize)?.clone();
        let c = b.client.get(&l).cloned().unwrap_or_default();
        Some((l, c))
    }

    /// leader schedule (current + next epoch, compact: one u32 per slot) + every node's clientId
    pub async fn refresh(rpc: &rpc::Rpc) -> Result<String> {
        let ei = rpc.call("getEpochInfo", serde_json::json!([])).await.context("getEpochInfo")?;
        let start = ei["absoluteSlot"].as_u64().unwrap_or(0).saturating_sub(ei["slotIndex"].as_u64().unwrap_or(0));
        let len = ei["slotsInEpoch"].as_u64().unwrap_or(432_000) as usize;
        let mut names: Vec<String> = Vec::new();
        let mut pos: HashMap<String, u32> = HashMap::new();
        let mut idx = vec![u32::MAX; 2 * len];
        for (k, a) in [(0usize, serde_json::Value::Null), (1usize, serde_json::json!(start + len as u64))] {
            let Ok(ls) = rpc.call("getLeaderSchedule", serde_json::json!([a])).await else { continue };
            let Some(obj) = ls.as_object() else { continue };
            for (leader, slots) in obj {
                let id = *pos.entry(leader.clone()).or_insert_with(|| { names.push(leader.clone()); (names.len() - 1) as u32 });
                for s in slots.as_array().into_iter().flatten().filter_map(|x| x.as_u64()) {
                    let j = k * len + s as usize;
                    if j < idx.len() { idx[j] = id; }
                }
            }
        }
        let mapped = idx.iter().filter(|x| **x != u32::MAX).count();
        if mapped == 0 { bail!("getLeaderSchedule returned nothing"); }
        let cn = rpc.call("getClusterNodes", serde_json::json!([])).await.context("getClusterNodes")?;
        let mut client = HashMap::new();
        for n in cn.as_array().into_iter().flatten() {
            if let (Some(p), Some(c)) = (n["pubkey"].as_str(), n["clientId"].as_str()) { client.insert(p.to_string(), c.to_string()); }
        }
        let msg = format!("LEADER-BOOK epoch_start={start} slots_mapped={mapped} leaders={} nodes_with_client={}", names.len(), client.len());
        // keep the old client map if the new one came back empty (an RPC hiccup must not blind the router)
        let mut g = BOOK.write().unwrap();
        if client.is_empty() { if let Some(old) = g.as_ref() { client = old.client.clone(); } }
        *g = Some(Book { base: start, idx, names, client });
        Ok(msg)
    }

    pub fn start_refresh(rpc: Arc<rpc::Rpc>, stop: Arc<AtomicBool>) {
        tokio::spawn(async move {
            while !stop.load(Ordering::Relaxed) {
                tokio::time::sleep(Duration::from_secs(600)).await;
                match refresh(&rpc).await { Ok(m) => eprintln!("  {m}"), Err(e) => eprintln!("  LEADER-BOOK refresh failed (kept the old one): {e:#}") }
            }
        });
    }

    /// parse --route-by-client against the built paths
    pub fn parse_routes(spec: &str, paths: &send::Paths) -> Result<HashMap<String, Vec<Arc<send::Path>>>> {
        let mut m = HashMap::new();
        for part in spec.split(';').map(str::trim).filter(|s| !s.is_empty()) {
            let (c, list) = part.split_once('=').with_context(|| format!("--route-by-client: '{part}' is not class=path+path"))?;
            let c = c.trim().to_string();
            if c != "default" && !CLASSES.contains(&c.as_str()) { bail!("--route-by-client: unknown class '{c}' (use {} or default)", CLASSES.join("|")); }
            let mut v = Vec::new();
            for n in list.split(['+', ',']).map(str::trim).filter(|s| !s.is_empty()) {
                let i = paths.index(n).with_context(|| format!("--route-by-client: no such [[send]] path '{n}' (or it failed to build: see send notes)"))?;
                v.push(paths.list[i].clone());
            }
            m.insert(c, v);
        }
        if !m.contains_key("default") { bail!("--route-by-client needs a default=... entry"); }
        Ok(m)
    }

    /// Route metadata for one buy (printed + logged)
    #[derive(Clone, Default)]
    pub struct Meta { pub route: String, pub leader: String, pub client: String, pub slot: Option<u64>, pub sig: String, pub bytes: usize, pub tips: u64 }

    /// the paths a BUY goes to, and why
    pub fn buy_paths(path: &Arc<send::Path>, also: Option<&Arc<send::Path>>, slot: Option<u64>) -> (Vec<Arc<send::Path>>, Meta) {
        let mut meta = Meta { slot, ..Default::default() };
        if let Some((l, c)) = slot.and_then(leader_of) { meta.leader = l; meta.client = c; }
        if let Some(r) = ROUTES.get() {
            let mut classes: Vec<&'static str> = Vec::new();
            if let Some(s) = slot {
                if !meta.client.is_empty() || !meta.leader.is_empty() { classes.push(class(&meta.client)); }
                // the create is in its leader's LAST slot: a buy may land under the next leader, route for it too
                if let (Some((l0, _)), Some((l1, c1))) = (leader_of(s), leader_of(s + 1)) {
                    if l1 != l0 { let k = class(&c1); if !classes.contains(&k) { classes.push(k); } }
                }
            }
            let mut v: Vec<Arc<send::Path>> = Vec::new();
            for c in &classes {
                for p in r.get(*c).or_else(|| r.get("default")).into_iter().flatten() {
                    if !v.iter().any(|x| x.name == p.name) { v.push(p.clone()); }
                }
            }
            if v.is_empty() { v = r.get("default").cloned().unwrap_or_else(|| vec![path.clone()]); classes.push("default"); }
            meta.route = format!("route:{}", classes.join("+"));
            return (v, meta);
        }
        if let Some(m) = MULTI.get() { meta.route = "multi".into(); return (m.clone(), meta); }
        let mut v = vec![path.clone()];
        if let Some(a) = also { if a.name != path.name { v.push(a.clone()); } }
        meta.route = if v.len() > 1 { "also".into() } else { "single".into() };
        (v, meta)
    }

    /// one tip per tip family (paths whose tip accounts overlap, e.g. jito-bundle + jito-tx, share one, at the larger
    /// amount); each path's `check` then finds its own tip in the tx
    pub fn tips_for(paths: &[Arc<send::Path>]) -> Vec<(Pk, u64)> {
        let mut tips: Vec<(Pk, u64)> = Vec::new();
        for p in paths {
            let Some((t, l)) = p.tip(0) else { continue };
            if l == 0 { continue; }
            let accts = p.tip_accounts();
            match tips.iter_mut().find(|e| accts.contains(&e.0)) { Some(e) => e.1 = e.1.max(l), None => tips.push((t, l)) }
        }
        tips
    }

    /// raise the SetComputeUnitLimit ix by `extra` units (each System tip transfer costs ~150 CU)
    pub fn bump_cu_limit(ixs: &mut [build::Ix], extra: u32) {
        for ix in ixs.iter_mut() {
            if ix.program == arbx::tx::COMPUTE_BUDGET && ix.data.len() == 5 && ix.data[0] == 2 {
                let cur = u32::from_le_bytes(ix.data[1..5].try_into().unwrap());
                ix.data[1..5].copy_from_slice(&cur.saturating_add(extra).min(1_400_000).to_le_bytes());
                return;
            }
        }
    }

    /// The fan-out tx: one tip per tip family for every path in `fan`, the CU limit raised for the extra transfers; a tx
    /// over the 1232-byte packet limit drops paths from the end (their tips with them) until it fits. (raw, tips)
    pub fn build_tx(key: &SigningKey, user: Pk, ixs: &[build::Ix], fan: &mut Vec<Arc<send::Path>>, blockhash: [u8; 32]) -> Result<(Vec<u8>, Vec<(Pk, u64)>)> {
        loop {
            let tips = tips_for(fan);
            let mut v: Vec<build::Ix> = Vec::with_capacity(ixs.len() + tips.len());
            for (t, l) in &tips { v.push(build::transfer_ix(user, *t, *l)); }
            v.extend_from_slice(ixs);
            if tips.len() > 2 { bump_cu_limit(&mut v, 300 * (tips.len() as u32 - 2)); }
            let msg = build::compile_v0(user, &v, blockhash, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
            let raw = build::sign(&msg, key);
            if raw.len() <= 1232 || fan.len() <= 1 { return Ok((raw, tips)); }
            let d = fan.pop().unwrap();
            eprintln!("  TX-SIZE {} bytes > 1232: dropped path {} from the fan-out", raw.len(), d.name);
        }
    }

    /// --junk-fanout fire (ZERO COST): route + build + sign the real buy exactly as a live fire, DISCARD it, and send
    /// only junk to the routed paths (Path::ack_probe never sends the tx). Logs JUNK-FAN / JUNK-ACK and the send log.
    pub async fn junk_fire(key: &SigningKey, user: Pk, path: &Arc<send::Path>, launch: &Launch, create_slot: u64) -> Result<()> {
        let t_b = Instant::now();
        let (buy_ixs, _) = build_buy(user, launch, None, 2_000_000, 1);
        let (mut fan, mut meta) = buy_paths(path, ALSO_PATH.get(), Some(create_slot));
        let bh = BLOCKHASH_CACHE.lock().unwrap().map(|(h, _)| h).unwrap_or([0u8; 32]);
        let (raw, tips) = build_tx(key, user, &buy_ixs, &mut fan, bh)?;
        drop(raw); // never sent
        meta.sig = "junk".into();
        meta.tips = tips.iter().map(|t| t.1).sum();
        let build_us = t_b.elapsed().as_micros();
        eprintln!("  JUNK-FAN slot={create_slot} mint={} {} leader={} client={} paths={} tips={} build_us={build_us}", b58(&launch.mint), meta.route,
            meta.leader.chars().take(8).collect::<String>(), meta.client, fan.iter().map(|p| p.name.as_str()).collect::<Vec<_>>().join(","), meta.tips);
        let t0 = Instant::now();
        let hs: Vec<_> = fan.iter().map(|p| { let (p, m) = (p.clone(), meta.clone()); let mint = b58(&launch.mint); tokio::spawn(async move {
            let off = t0.elapsed().as_micros() as u64;
            let (ms, answered, reply) = p.ack_probe().await;
            eprintln!("  JUNK-ACK path={} t_off_us={off} ack_ms={ms:.2} answered={answered} {}", p.name, reply.chars().take(80).collect::<String>());
            log_json(serde_json::json!({ "ev": "junk_ack", "t_ns": arbx::feeds::clock::now_ns(), "mint": mint, "slot": m.slot, "route": m.route, "leader": m.leader,
                "client": m.client, "path": p.name, "t_off_us": off, "ack_ms": ms, "answered": answered, "reply": reply, "build_us": build_us as u64 }));
        }) }).collect();
        for h in hs { let _ = h.await; }
        Ok(())
    }

    pub fn log_json(v: serde_json::Value) {
        if let Some(f) = SEND_LOG.get() {
            use std::io::Write;
            if let Ok(mut f) = f.lock() { let _ = writeln!(f, "{v}"); }
        }
    }

    /// send through one path, print SEND-ACK (t_off_us = when this path's send started, after the fan-out began), log it
    pub async fn send_one(p: &Arc<send::Path>, raw: &[u8], t0: Instant, meta: &Meta) -> std::result::Result<send::Reply, send::Refusal> {
        let t_off = t0.elapsed();
        let t = Instant::now();
        let r = p.send(raw, send::Prio { band: 0, crowd: 0, ev: 0 }, None).await;
        let ack = t.elapsed().as_secs_f64() * 1e3;
        let (ok, status, reply) = match &r {
            Ok(rep) => (true, rep.status, rep.reply.chars().take(120).collect::<String>()),
            Err(e) => (false, e.status, e.msg.chars().take(120).collect::<String>()),
        };
        eprintln!("  SEND-ACK path={} t_off_us={} ack_ms={ack:.2} {}status={status:?} reply={reply}", p.name, t_off.as_micros(), if ok { "" } else { "REFUSED " });
        log_json(serde_json::json!({ "ev": "ack", "t_ns": arbx::feeds::clock::now_ns(), "sig": meta.sig, "slot": meta.slot, "route": meta.route,
            "leader": meta.leader, "client": meta.client, "path": p.name, "kind": format!("{:?}", p.kind), "t_off_us": t_off.as_micros() as u64,
            "ack_ms": ack, "ok": ok, "status": status, "reply": reply, "tx_bytes": meta.bytes, "tips_lamports": meta.tips }));
        r
    }

    /// --ack-probe N (zero cost)
    pub async fn ack_probe(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, paths: &Arc<send::Paths>, path: &Arc<send::Path>, rounds: u64) -> Result<()> {
        // the probe set: every routed / multi path, else every built path
        let mut cand: Vec<Arc<send::Path>> = Vec::new();
        if let Some(r) = ROUTES.get() { for v in r.values() { cand.extend(v.iter().cloned()); } }
        if let Some(m) = MULTI.get() { cand.extend(m.iter().cloned()); }
        if cand.is_empty() { cand.extend(paths.list.iter().cloned()); }
        let mut set: Vec<Arc<send::Path>> = Vec::new();
        for p in cand { if !set.iter().any(|x| x.name == p.name) { set.push(p); } }
        eprintln!("\nACK-PROBE (ZERO COST): paths = {}", set.iter().map(|p| p.name.as_str()).collect::<Vec<_>>().join(", "));

        // 1. routing preview
        let cur = rpc.slot().await.unwrap_or(0);
        if BOOK.read().unwrap().is_some() && cur > 0 {
            let mut cnt: HashMap<&'static str, u64> = HashMap::new();
            for s in cur..cur + 20_000 { if let Some((_, c)) = leader_of(s) { *cnt.entry(class(&c)).or_default() += 1; } }
            let tot: u64 = cnt.values().sum();
            let mut v: Vec<_> = cnt.into_iter().collect(); v.sort_by(|a, b| b.1.cmp(&a.1));
            eprintln!("  next 20,000 slots by leader class: {}", v.iter().map(|(k, n)| format!("{k} {:.0}%", 100.0 * *n as f64 / tot.max(1) as f64)).collect::<Vec<_>>().join(", "));
            for s in (cur..cur + 16).step_by(4) {
                let (pp, m) = buy_paths(path, ALSO_PATH.get(), Some(s));
                eprintln!("  slot {s}: leader {} client {} -> {} [{}]", &m.leader.chars().take(8).collect::<String>(), m.client, m.route,
                    pp.iter().map(|p| p.name.as_str()).collect::<Vec<_>>().join(","));
            }
        }

        // 2. the multi-tip buy: size, each path's own check, simulateTransaction (sigVerify off)
        let launch = match arg_pk("--mint") {
            Some(m) => snipe_build::launch_from_target(m, arg_pk("--creator").unwrap_or(m)),
            None => snipe_build::launch_from_target(pk("So11111111111111111111111111111111111111112"), user),
        };
        let (buy_ixs, _) = build_buy(user, &launch, None, 2_000_000, 1);
        let tips = tips_for(&set);
        let mut v: Vec<build::Ix> = tips.iter().map(|(t, l)| build::transfer_ix(user, *t, *l)).collect();
        v.extend_from_slice(&buy_ixs);
        if tips.len() > 1 { bump_cu_limit(&mut v, 300 * (tips.len() as u32 - 1)); }
        let bh = rpc.latest_blockhash().await.map(|x| x.0).unwrap_or([0u8; 32]);
        let msg = build::compile_v0(user, &v, bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
        let raw = build::sign(&msg, key);
        let tip_sum: u64 = tips.iter().map(|t| t.1).sum();
        eprintln!("  MULTI-TIP BUY: {} tips (total {} lamports = {:.4} SOL), {} bytes (limit 1232) {}", tips.len(), tip_sum, tip_sum as f64 / 1e9, raw.len(),
            if raw.len() <= 1232 { "OK" } else { "TOO BIG: the engine drops paths from the end until it fits" });
        for p in &set { eprintln!("    check {:14} {}", p.name, match p.check(&raw) { Ok(_) => "OK (pays its tip)".to_string(), Err(e) => format!("REFUSED: {e:#}") }); }
        let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
        let opts = serde_json::json!({ "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed" });
        match rpc.call("simulateTransaction", serde_json::json!([b64, opts])).await {
            Ok(v) => {
                let val = &v["value"];
                let logs = val["logs"].as_array().map(|a| a.len()).unwrap_or(0);
                eprintln!("    simulate: err={} unitsConsumed={} logs={logs} {}", val["err"], val["unitsConsumed"],
                    if arg_pk("--mint").is_none() { "(synthetic mint: the BUY is expected to fail; the tips run first)" } else { "" });
                if let Some(a) = val["logs"].as_array() { for l in a.iter().take(6) { eprintln!("      {}", l.as_str().unwrap_or("")); } }
            }
            Err(e) => eprintln!("    simulate failed: {e:#}"),
        }

        // 3. junk-request ack rounds, all paths at once (as a fan-out does), 1.5 s apart
        let mut ms: HashMap<String, Vec<f64>> = HashMap::new();
        let mut first: HashMap<String, String> = HashMap::new();
        for r in 0..rounds {
            let t0 = Instant::now();
            let hs: Vec<_> = set.iter().map(|p| { let p = p.clone(); tokio::spawn(async move { let off = t0.elapsed().as_micros(); let (m, a, s) = p.ack_probe().await; (p.name.clone(), off, m, a, s) }) }).collect();
            let mut line = Vec::new();
            for h in hs {
                if let Ok((n, off, m, a, s)) = h.await {
                    line.push(format!("{n}={m:.2}{}", if a { "" } else { "?" }));
                    log_json(serde_json::json!({ "ev": "ackprobe", "round": r, "path": n, "t_off_us": off as u64, "ack_ms": m, "answered": a, "reply": s }));
                    ms.entry(n.clone()).or_default().push(m);
                    first.entry(n).or_insert(s);
                }
            }
            eprintln!("  round {r}: {}", line.join(" "));
            tokio::time::sleep(Duration::from_millis(1500)).await;
        }
        println!("\n========== ACK-PROBE RESULT (junk requests, nothing can land) ==========");
        for p in &set {
            let mut v = ms.remove(&p.name).unwrap_or_default();
            println!("{:14} n={:2} ack p50 {:6.2} ms  p90 {:6.2} ms  max {:6.2} ms  | {}", p.name, v.len(), pct(&mut v, 0.5), pct(&mut v, 0.9), pct(&mut v, 1.0),
                first.get(&p.name).map(|s| s.chars().take(90).collect::<String>()).unwrap_or_default());
        }
        for l in paths.summary() { println!("  {l}"); }
        Ok(())
    }
}

// ================================================================================================================
// FAST (2026-10-19): --fast-send, the sub-100 µs fire path (all default off; no flag = the LAT behaviour above).
//  * prepare at CREATE time (before the race gate decides): route, tips, blockhash, the template-patched message,
//    signature, and every path's framed request; the decision then only writes.
//  * fire from the event-loop thread itself: Jito (gRPC, async) is spawned first, then LandX UDP and every HTTP path is
//    written with one syscall on our own keep-alive connection (arbx::fast::FastConn). A path whose fast connection is
//    down, or that has no fast form, goes through the old async send (lat::send_one) as before.
//  * --busy-poll: the event loop runs on its own thread (block_in_place + Handle::block_on) and spins on the feed's
//    crossbeam channel (no bridge thread, no tokio wake-up); --pin-core N pins it.
//  * --lat-trace FILE: one JSON line per prepared create ("prep") and per fire ("fire") with monotonic ns stamps.
//  * --fast-verify: every fast-built message is compared with the full compile (same tips, blockhash, min_out).
//  * --fast-bench N: zero-network microbenchmark of the build stages (fast vs the old build), then exit.
// Junk mode (--junk-fanout): the SAME path code writes the signed tx with its signature count set to 0 (undecodable as
// a transaction: zero signatures can never pass sanitize), so the providers parse the real-sized request and reject it.
// ================================================================================================================
mod fastfire {
    use super::*;
    use arbx::config::SendKind;
    use arbx::fast::{self, Ack, FastConn, FastH2, Template};
    use ed25519_dalek::Signer;
    use std::collections::HashMap;
    use std::io::Write as _;
    use std::sync::atomic::AtomicU64;
    use std::sync::{Mutex, OnceLock};

    pub enum Kind { Http { conn: Arc<FastConn>, json: bool }, Udp, Jito, JitoH2 { conn: Arc<FastH2>, jito: Arc<send::jito::Jito> }, Slow }
    /// jito-h2 fires: tag -> tx signature (the result stream joins bundles by signature)
    static TAGSIG: Mutex<Option<HashMap<u64, String>>> = Mutex::new(None);
    pub struct Fp { pub path: Arc<send::Path>, pub kind: Kind }

    pub struct Fast {
        key: SigningKey,
        user: Pk,
        main: Arc<send::Path>,
        pub fps: Vec<Fp>,
        templates: Mutex<HashMap<Vec<u64>, Option<Arc<Template>>>>,
        handle: tokio::runtime::Handle,
        pub junk: bool,
        verify: bool,
        trace: Option<Mutex<std::io::BufWriter<std::fs::File>>>,
        udp_copies: u32,
        next_id: AtomicU64,
        pub verified: AtomicU64,
        pub mismatched: AtomicU64,
        presign: Option<Arc<fast::Presigner>>,
        fast_derive: bool,
    }
    pub static FAST: OnceLock<Fast> = OnceLock::new();

    pub fn get() -> Option<&'static Fast> { FAST.get() }

    /// the event loop's held log lines go to this thread (one buffered write per line), never a stderr write on the loop
    static LOGQ: OnceLock<crossbeam_channel::Sender<String>> = OnceLock::new();
    pub fn log_line(l: String) {
        let q = LOGQ.get_or_init(|| {
            let (tx, rx) = crossbeam_channel::unbounded::<String>();
            std::thread::Builder::new().name("fast-log".into()).spawn(move || {
                let mut e = std::io::BufWriter::with_capacity(1 << 16, std::io::stderr());
                for l in rx.iter() { let _ = writeln!(e, "{l}"); if rx.is_empty() { let _ = e.flush(); } }
            }).expect("log thread");
            tx
        });
        if let Err(e) = q.send(l) { eprintln!("{}", e.0); }
    }

    fn json_kind(k: SendKind) -> bool {
        matches!(k, SendKind::Helius | SendKind::Shyft | SendKind::Rpc | SendKind::Nozomi | SendKind::ZeroSlot | SendKind::Falcon | SendKind::Everstake | SendKind::JupiterTx
            | SendKind::HarmonicBundle)
    }
    fn bin_kind(k: SendKind) -> bool { matches!(k, SendKind::Haan | SendKind::Bolt | SendKind::Iris | SendKind::Lunar | SendKind::NodeOne | SendKind::BlockRazor | SendKind::Landx) }

    pub fn init(key: &SigningKey, user: Pk, paths: &Arc<send::Paths>, main: &Arc<send::Path>, junk: bool, stop: Arc<AtomicBool>) -> Result<()> {
        let (atx, arx) = crossbeam_channel::unbounded::<Ack>();
        let mut fps = Vec::new();
        for p in &paths.list {
            let kind = if p.kind == SendKind::JitoBundle && p.jito.is_some() && has("--jito-h2") {
                    match FastH2::start(&p.name, p.fast_url(), atx.clone(), stop.clone()) {
                        Ok(c) => Kind::JitoH2 { conn: c, jito: p.jito.clone().unwrap() },
                        Err(e) => { eprintln!("FAST: {} stays on tonic: {e}", p.name); Kind::Jito }
                    }
                }
                else if p.kind == SendKind::JitoBundle && p.jito.is_some() { Kind::Jito }
                else if p.kind == SendKind::Landx && p.fast_udp_ok() { Kind::Udp }
                // FIX2: harmonic-bundle with a working Harmonic login goes through its gRPC client (async send)
                else if p.kind == SendKind::HarmonicBundle && p.hb.is_some() { Kind::Slow }
                else if (json_kind(p.kind) || bin_kind(p.kind)) && !p.fast_preflight() {
                    let json = json_kind(p.kind);
                    match FastConn::start(&p.name, p.fast_url(), if json { "application/json" } else { "application/octet-stream" }, &p.fast_headers(), p.fast_ping(), atx.clone(), stop.clone()) {
                        Ok(c) => Kind::Http { conn: c, json },
                        Err(e) => { eprintln!("FAST: {} stays on the async send: {}", p.name, e.split(": url").next().unwrap_or("")); Kind::Slow }
                    }
                } else { Kind::Slow };
            eprintln!("FAST: path {:14} -> {}", p.name, match &kind { Kind::Http { json, .. } => if *json { "own HTTP/1.1 conn (json)" } else { "own HTTP/1.1 conn (binary)" }, Kind::Udp => "UDP from the hot thread", Kind::Jito => "gRPC (spawned first)", Kind::JitoH2 { .. } => "own raw HTTP/2 gRPC conn", Kind::Slow => "async send (unchanged)" });
            fps.push(Fp { path: p.clone(), kind });
        }
        // the ack logger: FAST-ACK lines + the send log
        std::thread::Builder::new().name("fast-acks".into()).spawn(move || {
            for a in arx {
                let ms = a.t_ack.saturating_sub(a.t_write) as f64 / 1e6;
                eprintln!("  FAST-ACK tag={} path={} ack_ms={ms:.3} status={:?} reply={}", a.tag, a.path, a.status, a.body.chars().take(100).collect::<String>());
                // a jito-h2 acceptance: hand the bundle id to the Jito client (results join by signature)
                if a.status == Some(200) {
                    let sig = TAGSIG.lock().unwrap().as_mut().and_then(|m| m.remove(&a.tag));
                    if let (Some(sig), Some(f)) = (sig, get()) {
                        for x in &f.fps { if let Kind::JitoH2 { jito, conn } = &x.kind { if conn.name == a.path { jito.note_bundle(&sig, &a.body); } } }
                    }
                }
                lat::log_json(serde_json::json!({ "ev": "fast_ack", "t_ns": arbx::feeds::clock::now_ns(), "tag": a.tag, "path": a.path, "ack_ms": ms, "status": a.status, "reply": a.body }));
            }
        })?;
        let trace = match arg("--lat-trace") {
            Some(f) => Some(Mutex::new(std::io::BufWriter::new(std::fs::OpenOptions::new().create(true).append(true).open(&f).with_context(|| format!("--lat-trace {f}"))?))),
            None => None,
        };
        // self-check: our JSON body is byte-identical to the old serde_json body
        {
            use base64::Engine as _;
            let raw: Vec<u8> = (0..1042u32).map(|i| (i * 131 + 7) as u8).collect();
            let old = serde_json::json!({ "jsonrpc": "2.0", "id": 1, "method": "sendTransaction",
                "params": [base64::engine::general_purpose::STANDARD.encode(&raw), { "encoding": "base64", "skipPreflight": true, "maxRetries": 0 }] });
            let mut b = Vec::new();
            fast::json_send_body(&raw, &mut b);
            let same = serde_json::to_vec(&old).map(|o| o == b).unwrap_or(false);
            eprintln!("FAST: JSON body byte-identical to the old serde_json body: {same}");
            if !same { bail!("FAST: the JSON body differs from the old one"); }
        }
        let udp_copies = std::env::var("LANDX_UDP_COPIES").ok().and_then(|v| v.parse::<u32>().ok()).unwrap_or(2).clamp(1, 4);
        // --fast-presign: pre-computed nonces (self-test: 300 signatures, each verify_strict-ed)
        let presign = if has("--fast-presign") {
            let ps = fast::Presigner::new(key);
            ps.start(300, stop.clone());
            let vk = key.verifying_key();
            let mut bad = 0;
            for i in 0..300u32 {
                let m: Vec<u8> = (0..900u32).map(|j| (j * 31 + i) as u8).collect();
                match ps.sign(&m) { Some(sg) => if vk.verify_strict(&m, &ed25519_dalek::Signature::from_bytes(&sg)).is_err() { bad += 1; }, None => bad += 1 }
            }
            eprintln!("FAST: presign self-test: 300 signatures, {bad} failed verify_strict");
            if bad > 0 { bail!("FAST: presign self-test failed"); }
            Some(ps)
        } else { None };
        let f = Fast { key: key.clone(), user, main: main.clone(), fps, templates: Mutex::new(HashMap::new()), handle: tokio::runtime::Handle::current(), junk,
            verify: has("--fast-verify"), trace, udp_copies, next_id: AtomicU64::new(1), verified: AtomicU64::new(0), mismatched: AtomicU64::new(0), presign,
            fast_derive: if has("--fast-derive") {
                let (bad, bad_ata) = fast::derive_selftest(200_000, 3_000);
                eprintln!("FAST: fast-derive self-test: on-curve disagreements with dalek {bad}/200012, ATA mismatches {bad_ata}/3000");
                if bad > 0 || bad_ata > 0 { bail!("FAST: fast-derive self-test failed"); }
                true
            } else { false },
        };
        if FAST.set(f).is_err() { bail!("fast path initialised twice"); }
        // wait (<= 6 s) for the fast connections to come up
        let t = Instant::now();
        while t.elapsed() < Duration::from_secs(6) {
            if get().unwrap().fps.iter().all(|f| match &f.kind { Kind::Http { conn, .. } => conn.up.load(Ordering::Relaxed), Kind::JitoH2 { conn, .. } => conn.up.load(Ordering::Relaxed), _ => true }) { break; }
            std::thread::sleep(Duration::from_millis(50));
        }
        for l in get().unwrap().summary() { eprintln!("FAST: {l}"); }
        Ok(())
    }

    /// one prepared buy
    pub struct Prep {
        pub id: u64,
        pub launch: Launch,
        pub slot: u64,
        pub fan: Vec<Arc<send::Path>>,
        pub fpi: Vec<usize>,
        pub meta: lat::Meta,
        pub raw: Vec<u8>,
        pub sig: [u8; 64],
        pub payload: Arc<Vec<u8>>,
        /// per fan path: the framed request (HTTP: whole request; jito-h2: HEADERS+DATA and the header block length)
        pub reqs: Vec<Option<(Vec<u8>, usize)>>,
        pub tips: Vec<(Pk, u64)>,
        /// jito-h2: "Bearer <access token>" at prepare time
        pub jtok: Option<String>,
        pub bh: [u8; 32],
        pub min_out: u64,
        pub fast_built: bool,
        /// mono ns: start, routed, derived, patched (or full compile), signed, encoded
        pub st: [u64; 6],
        pub made: Instant,
        /// create-side stamps: (rx realtime ns, decoded realtime ns, dequeued realtime ns, dequeued mono, detected mono, gated mono)
        pub cr: [u64; 6],
    }

    /// one fire's writes: (path, kind, t0, t1, status)
    pub struct FireRec { pub t_fire0: u64, pub t_end: u64, pub w: Vec<(String, &'static str, u64, u64, &'static str)> }

    impl Fast {
        fn template(&self, tips: &[(Pk, u64)]) -> Option<Arc<Template>> {
            let k: Vec<u64> = tips.iter().map(|t| t.1).collect();
            if let Some(t) = self.templates.lock().unwrap().get(&k) { return t.clone(); }
            let t = self.make_template(tips).map_err(|e| eprintln!("FAST: no template for tips {k:?}: {e} (full compile for this shape)")).ok().map(Arc::new);
            self.templates.lock().unwrap().insert(k, t.clone());
            t
        }

        fn make_template(&self, tips: &[(Pk, u64)]) -> std::result::Result<Template, String> {
            let user = self.user;
            let probe = Launch { mint: fast::probe_var(0), bonding_curve: fast::probe_var(1), assoc_bonding_curve: fast::probe_var(2), creator: fast::probe_var(9),
                dev_buy_lamports: 0, is_create_v2: true, is_mayhem: false, is_cashback: false, creator_fee_bps: 0, is_holder_reward: false, buyback_fee_recipient: fast::probe_var(5) };
            let (mut ixs, _) = build_buy(user, &probe, None, 2_000_000, fast::PROBE_MIN_OUT);
            let (p0, p1) = (probe.mint, probe.bonding_curve);
            let map = [(pda::ata(&p1, &p0, &pda::TOKEN_2022), fast::probe_var(2)), (pda::ata(&p1, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), fast::probe_var(3)),
                (pda::ata(&user, &p0, &pda::TOKEN_2022), fast::probe_var(4))];
            for ix in ixs.iter_mut() { for a in ix.accounts.iter_mut() { if let Some((_, to)) = map.iter().find(|(from, _)| *from == a.key) { a.key = *to; } } }
            let mut v: Vec<build::Ix> = tips.iter().enumerate().map(|(i, (_, l))| build::transfer_ix(user, fast::probe_tip(i), *l)).collect();
            v.extend(ixs);
            if tips.len() > 2 { lat::bump_cu_limit(&mut v, 300 * (tips.len() as u32 - 2)); }
            let msg = build::compile_v0(user, &v, fast::PROBE_BH, &[], &[])?;
            if 1 + 64 + msg.bytes.len() > 1232 { return Err(format!("{} bytes > 1232", 1 + 64 + msg.bytes.len())); }
            Template::from_probe_msg(msg.bytes, tips.len())
        }

        /// the full compile of the same buy (the reference the fast build must equal byte for byte)
        fn reference(&self, launch: &Launch, tips: &[(Pk, u64)], bh: [u8; 32], min_out: u64) -> Option<Vec<u8>> {
            let (ixs, _) = build_buy(self.user, launch, None, 2_000_000, min_out);
            let mut v: Vec<build::Ix> = tips.iter().map(|(t, l)| build::transfer_ix(self.user, *t, *l)).collect();
            v.extend(ixs);
            if tips.len() > 2 { lat::bump_cu_limit(&mut v, 300 * (tips.len() as u32 - 2)); }
            build::compile_v0(self.user, &v, bh, &[], &[]).ok().map(|m| m.bytes)
        }

        /// build + sign + frame everything for one launch (create time)
        pub fn prepare(&self, launch: &Launch, slot: u64, min_out: u64, cr: [u64; 6]) -> Result<Prep> {
            let t0 = fast::mono_ns();
            let (mut fan, mut meta) = lat::buy_paths(&self.main, ALSO_PATH.get(), Some(slot));
            let mut tips = lat::tips_for(&fan);
            let bh = BLOCKHASH_CACHE.lock().unwrap().map(|(h, _)| h).unwrap_or([0u8; 32]);
            let t1 = fast::mono_ns();
            let tpl = self.template(&tips);
            let (mint, bc) = (launch.mint, launch.bonding_curve);
            let ata = |o: &Pk, m: &Pk, t: &Pk| if self.fast_derive { fast::ata_fast(o, m, t) } else { pda::ata(o, m, t) };
            let abc = if launch.is_create_v2 { launch.assoc_bonding_curve } else { ata(&bc, &mint, &pda::TOKEN_2022) };
            let vars: fast::VarKeys = [mint, bc, abc, ata(&bc, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), ata(&self.user, &mint, &pda::TOKEN_2022), launch.buyback_fee_recipient];
            let t2 = fast::mono_ns();
            let tip_keys: Vec<Pk> = tips.iter().map(|t| t.0).collect();
            let mut msg: Vec<u8> = Vec::with_capacity(1232);
            let fast_built = tpl.as_ref().and_then(|t| t.patch(&mut msg, &vars, &tip_keys, &bh, min_out)).is_some();
            let (raw, sig, t3) = if fast_built {
                let t3 = fast::mono_ns();
                let sig = self.presign.as_ref().and_then(|ps| ps.sign(&msg)).unwrap_or_else(|| self.key.sign(&msg).to_bytes());
                let mut raw = Vec::with_capacity(65 + msg.len());
                raw.push(1); raw.extend_from_slice(&sig); raw.extend_from_slice(&msg);
                (raw, sig, t3)
            } else {
                let (ixs, _) = build_buy(self.user, launch, None, 2_000_000, min_out);
                let (raw, t) = lat::build_tx(&self.key, self.user, &ixs, &mut fan, bh)?;
                tips = t;
                let mut sig = [0u8; 64]; sig.copy_from_slice(&raw[1..65]);
                (raw, sig, t2)
            };
            let t4 = fast::mono_ns();
            let mut payload = raw.clone();
            if self.junk { payload[0] = 0; } // zero signatures: never a valid transaction
            let mut fpi = Vec::with_capacity(fan.len());
            let mut reqs = Vec::with_capacity(fan.len());
            let mut body = Vec::with_capacity(2048);
            let mut jtok: Option<String> = None;
            for p in &fan {
                let i = self.fps.iter().position(|f| f.path.name == p.name).unwrap_or(usize::MAX);
                fpi.push(i);
                reqs.push(match self.fps.get(i).map(|f| &f.kind) {
                    Some(Kind::Http { conn, json }) => {
                        let mut req = Vec::with_capacity(2400);
                        // FIX2: harmonic-bundle is JSON-RPC sendBundle ([[b64], {"encoding":"base64"}]), the rest sendTransaction
                        if *json && p.kind == SendKind::HarmonicBundle { fast::json_bundle_body(&payload, &mut body); conn.frame(&body, &mut req); }
                        else if *json { fast::json_send_body(&payload, &mut body); conn.frame(&body, &mut req); } else { conn.frame(&payload, &mut req); }
                        Some((req, 0))
                    }
                    Some(Kind::JitoH2 { conn, jito }) => {
                        let now_ms = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_millis() as i64).unwrap_or(0);
                        let _ = conn;
                        jito.cached_token(now_ms).map(|tok| {
                            use prost::Message as _;
                            let j = send::jito::SendBundleRequest { bundle: Some(send::jito::Bundle { packets: vec![send::jito::Packet { data: payload.clone(),
                                meta: Some(send::jito::Meta { size: payload.len() as u64, addr: "0.0.0.0".into(), port: 0, sender_stake: 0 }) }] }) };
                            jtok = Some(format!("Bearer {tok}"));
                            (j.encode_to_vec(), 0)
                        })
                    }
                    _ => None,
                });
            }
            let t5 = fast::mono_ns();
            // warm the kernel send path of every socket this fire may write (zero-length sends: nothing goes out; not in prep_ns)
            for &i in &fpi { match self.fps.get(i).map(|f| &f.kind) { Some(Kind::Http { conn, .. }) => conn.prewarm(), Some(Kind::JitoH2 { conn, .. }) => conn.prewarm(), _ => {} } }
            meta.sig = if self.junk { "junk".into() } else { bs58::encode(&sig).into_string() };
            meta.bytes = raw.len();
            meta.tips = tips.iter().map(|t| t.1).sum();
            Ok(Prep { id: self.next_id.fetch_add(1, Ordering::Relaxed), launch: launch.clone(), slot, fan, fpi, meta, raw, sig, payload: Arc::new(payload), reqs, tips, jtok, bh, min_out,
                fast_built, st: [t0, t1, t2, t3, t4, t5], made: Instant::now(), cr })
        }

        /// HOT PATH: write every path (the decision has been taken). Never blocks on the network.
        pub fn fire(&self, p: &Prep) -> FireRec {
            let t_fire0 = fast::mono_ns();
            let mut w: Vec<(String, &'static str, u64, u64, &'static str)> = Vec::with_capacity(p.fan.len());
            // 1. Jito first: its write happens on the runtime, so it overlaps with the writes below
            for (i, path) in p.fan.iter().enumerate() {
                let Some(Kind::Jito) = self.fps.get(p.fpi[i]).map(|f| &f.kind) else { continue };
                let t = fast::mono_ns();
                if !path.fast_budget() { w.push((path.name.clone(), "jito", t, t, "over_rate")); continue; }
                let (path2, pl, sig, tag) = (path.clone(), p.payload.clone(), p.meta.sig.clone(), p.id);
                self.handle.spawn(async move {
                    let t = fast::mono_ns();
                    let r = match &path2.jito { Some(j) => j.send_bundle(&[&pl[..]], &sig, None).await.map_err(|e| e.to_string()), None => Err("no block engine".into()) };
                    let ms = fast::mono_ns().saturating_sub(t) as f64 / 1e6;
                    let (ok, reply) = match &r { Ok(id) => (true, id.clone()), Err(e) => (false, e.chars().take(120).collect()) };
                    eprintln!("  FAST-ACK tag={tag} path={} ack_ms={ms:.3} ok={ok} reply={reply}", path2.name);
                    lat::log_json(serde_json::json!({ "ev": "fast_ack", "t_ns": arbx::feeds::clock::now_ns(), "tag": tag, "path": path2.name, "ack_ms": ms, "ok": ok, "reply": reply }));
                });
                w.push((path.name.clone(), "jito", t, fast::mono_ns(), "spawned"));
            }
            // 2. UDP + 3. our HTTP connections, written from this thread
            let mut ubuf: Vec<u8> = Vec::with_capacity(1300);
            for pass in 0..3 {
                for (i, path) in p.fan.iter().enumerate() {
                    match (pass, self.fps.get(p.fpi[i]).map(|f| &f.kind)) {
                        (1, Some(Kind::JitoH2 { conn, .. })) => {
                            let t = fast::mono_ns();
                            if !path.fast_budget() { w.push((path.name.clone(), "jito-h2", t, t, "over_rate")); continue; }
                            let r = match (&p.reqs[i], &p.jtok) { (Some((msg, _)), Some(tok)) => conn.write_call_idx("/searcher.SearcherService/SendBundle", tok, msg, p.id), _ => Err("no token".into()) };
                            match r {
                                Ok((a, b)) => w.push((path.name.clone(), "jito-h2", a, b, "written")),
                                Err(_) => { self.slow(path, p); w.push((path.name.clone(), "jito-h2", t, fast::mono_ns(), "conn_down_async")); }
                            }
                        }
                        (0, Some(Kind::Udp)) => {
                            let t = fast::mono_ns();
                            if !path.fast_budget() { w.push((path.name.clone(), "udp", t, t, "over_rate")); continue; }
                            let r = path.fast_udp(&p.payload, &mut ubuf, 1);
                            w.push((path.name.clone(), "udp", t, fast::mono_ns(), match r { Some(Ok(())) => "written", _ => "udp_error" }));
                        }
                        (2, Some(Kind::Http { conn, .. })) => {
                            let t = fast::mono_ns();
                            if !path.fast_budget() { w.push((path.name.clone(), "http", t, t, "over_rate")); continue; }
                            match conn.write_req(p.reqs[i].as_ref().map(|r| &r.0[..]).unwrap_or(&[]), p.id) {
                                Ok((a, b)) => w.push((path.name.clone(), "http", a, b, "written")),
                                Err(_) => { self.slow(path, p); w.push((path.name.clone(), "http", t, fast::mono_ns(), "conn_down_async")); }
                            }
                        }
                        _ => {}
                    }
                }
            }
            // the extra LandX copies (redundancy against a dropped datagram) after every first write
            if self.udp_copies > 1 {
                for (i, path) in p.fan.iter().enumerate() {
                    if let Some(Kind::Udp) = self.fps.get(p.fpi[i]).map(|f| &f.kind) { let _ = path.fast_udp(&p.payload, &mut ubuf, self.udp_copies - 1); }
                }
            }
            // 4. paths without a fast form: the old async send
            for (i, path) in p.fan.iter().enumerate() {
                if matches!(self.fps.get(p.fpi[i]).map(|f| &f.kind), Some(Kind::Slow) | None) {
                    let t = fast::mono_ns();
                    self.slow(path, p);
                    w.push((path.name.clone(), "async", t, fast::mono_ns(), "spawned"));
                }
            }
            let t_end = fast::mono_ns();
            if p.fan.iter().enumerate().any(|(i, _)| matches!(self.fps.get(p.fpi[i]).map(|f| &f.kind), Some(Kind::JitoH2 { .. }))) {
                let mut g = TAGSIG.lock().unwrap();
                let m = g.get_or_insert_with(HashMap::new);
                if m.len() > 1000 { m.clear(); }
                m.insert(p.id, p.meta.sig.clone());
            }
            FireRec { t_fire0, t_end, w }
        }

        fn slow(&self, path: &Arc<send::Path>, p: &Prep) {
            let (path, pl, meta, junk, tag) = (path.clone(), p.payload.clone(), p.meta.clone(), self.junk, p.id);
            self.handle.spawn(async move {
                if junk {
                    let (ms, answered, reply) = path.ack_probe().await;
                    eprintln!("  FAST-ACK tag={tag} path={} ack_ms={ms:.3} answered={answered} reply={} (async junk)", path.name, reply.chars().take(100).collect::<String>());
                } else {
                    let _ = lat::send_one(&path, &pl, Instant::now(), &meta).await;
                }
            });
        }

        /// after the fire (or for a create that never fired): verify + trace, off the hot path
        pub fn trace_prep(&self, p: &Prep) {
            let ok = if self.verify && p.fast_built {
                let r = self.reference(&p.launch, &p.tips, p.bh, p.min_out);
                let sig_ok = self.key.verifying_key().verify_strict(&p.raw[65..], &ed25519_dalek::Signature::from_bytes(&p.sig)).is_ok();
                let same = r.as_deref() == Some(&p.raw[65..]) && sig_ok;
                if same { self.verified.fetch_add(1, Ordering::Relaxed); } else {
                    self.mismatched.fetch_add(1, Ordering::Relaxed);
                    eprintln!("  FAST-VERIFY MISMATCH mint={} (fast-built message != full compile)", b58(&p.launch.mint));
                }
                Some(same)
            } else { None };
            self.trace_line(serde_json::json!({ "ev": "prep", "id": p.id, "mint": b58(&p.launch.mint), "slot": p.slot, "route": p.meta.route, "paths": p.fan.len(),
                "tips": p.tips.len(), "bytes": p.raw.len(), "fast_built": p.fast_built, "verify": ok,
                "route_ns": p.st[1] - p.st[0], "derive_ns": p.st[2] - p.st[1], "patch_ns": p.st[3].saturating_sub(p.st[2]), "sign_ns": p.st[4] - p.st[3],
                "encode_ns": p.st[5] - p.st[4], "prep_ns": p.st[5] - p.st[0],
                "rx_to_dec_us": (p.cr[1] as i64 - p.cr[0] as i64) / 1000, "dec_to_deq_us": (p.cr[2] as i64 - p.cr[1] as i64) / 1000,
                "deq_to_detect_ns": p.cr[4].saturating_sub(p.cr[3]), "detect_to_gated_ns": p.cr[5].saturating_sub(p.cr[4]), "gated_to_prep_ns": p.st[0].saturating_sub(p.cr[5]) }));
        }

        /// ev: the deciding event's (rx realtime, decoded realtime, dequeued realtime, dequeued mono); t_dec: decided (mono)
        pub fn trace_fire(&self, p: &Prep, r: &FireRec, ev: [u64; 4], t_dec: u64) {
            let first = r.w.iter().filter(|x| x.4 == "written").map(|x| x.3).min().unwrap_or(0);
            let ws: Vec<serde_json::Value> = r.w.iter().map(|x| serde_json::json!({ "path": x.0, "kind": x.1, "start_ns": x.2.saturating_sub(r.t_fire0),
                "done_ns": x.3.saturating_sub(r.t_fire0), "from_decide_ns": x.3.saturating_sub(t_dec), "from_create_deq_ns": x.3.saturating_sub(p.cr[3]), "status": x.4 })).collect();
            self.trace_line(serde_json::json!({ "ev": "fire", "id": p.id, "mint": b58(&p.launch.mint), "slot": p.slot, "route": p.meta.route, "junk": self.junk,
                "fast_built": p.fast_built, "prep_age_us": p.made.elapsed().as_micros() as u64,
                "ev_rx_to_deq_us": (ev[2] as i64 - ev[0] as i64) / 1000, "ev_dec_to_deq_us": (ev[2] as i64 - ev[1] as i64) / 1000,
                "ev_deq_to_decide_ns": t_dec.saturating_sub(ev[3]), "decide_to_fire_ns": r.t_fire0.saturating_sub(t_dec),
                "decide_to_first_write_ns": if first > 0 { first.saturating_sub(t_dec) } else { 0 }, "fire_total_ns": r.t_end - r.t_fire0,
                "create_deq_to_decide_us": t_dec.saturating_sub(p.cr[3]) / 1000, "t_fire0_mono": r.t_fire0, "t_decide_mono": t_dec, "writes": ws }));
        }

        fn trace_line(&self, v: serde_json::Value) {
            if let Some(t) = &self.trace { if let Ok(mut f) = t.lock() { let _ = writeln!(f, "{v}"); let _ = f.flush(); } }
        }

        pub fn summary(&self) -> Vec<String> {
            let mut v: Vec<String> = self.fps.iter().filter_map(|f| match &f.kind { Kind::Http { conn, .. } => Some(conn.summary()), Kind::JitoH2 { conn, .. } => Some(conn.summary()), _ => None }).collect();
            v.push(format!("fast-verify: {} identical, {} MISMATCHED", self.verified.load(Ordering::Relaxed), self.mismatched.load(Ordering::Relaxed)));
            v
        }
    }

    /// spin on the feed channel until an event or `wait` (the --busy-poll receive). Err: the feed closed.
    #[inline]
    pub fn spin_recv(rx: &crossbeam_channel::Receiver<arbx::feeds::Event>, wait: Duration) -> std::result::Result<Option<arbx::feeds::Event>, ()> {
        let dl = Instant::now() + wait;
        let mut n = 0u32;
        loop {
            match rx.try_recv() {
                Ok(e) => return Ok(Some(e)),
                Err(crossbeam_channel::TryRecvError::Disconnected) => return Err(()),
                Err(crossbeam_channel::TryRecvError::Empty) => {}
            }
            n = n.wrapping_add(1);
            if n % 64 == 0 && Instant::now() >= dl { return Ok(None); }
            std::hint::spin_loop();
        }
    }

    /// --fast-probe N (with --junk-fanout): junk fires of a synthetic launch through every fast path, 1.5 s apart
    pub async fn probe(n: usize) {
        let f = get().unwrap();
        for i in 0..n {
            let mut m = [0u8; 32];
            m[..8].copy_from_slice(&(0x9000_0000u64 + i as u64).to_le_bytes());
            let mut l = snipe_build::launch_from_target(m, f.user);
            l.dev_buy_lamports = 1_000_000_000;
            let p = match f.prepare(&l, 0, 1, [0; 6]) { Ok(p) => p, Err(e) => { eprintln!("probe prepare: {e:#}"); return; } };
            let t_dec = fast::mono_ns();
            let rec = f.fire(&p);
            eprintln!("  FAST-PROBE tag={} paths={} writes: {}", p.id, p.fan.iter().map(|x| x.name.as_str()).collect::<Vec<_>>().join(","),
                rec.w.iter().map(|x| format!("{}={}@{:.1}us", x.0, x.4, x.3.saturating_sub(t_dec) as f64 / 1e3)).collect::<Vec<_>>().join(" "));
            f.trace_fire(&p, &rec, [0; 4], t_dec);
            tokio::time::sleep(Duration::from_millis(1500)).await;
        }
        tokio::time::sleep(Duration::from_secs(2)).await;
        for l in f.summary() { eprintln!("FAST: {l}"); }
    }

    /// --fast-bench N: zero network. The build stages of the fast path vs the old build (build_buy + lat::build_tx), on
    /// a synthetic launch per iteration (fresh mint each time: no derivation cache can help), byte-compared.
    pub fn bench(n: usize) {
        let f = get().unwrap();
        let mut old_ns: Vec<u64> = Vec::new();
        let mut st: [Vec<u64>; 6] = Default::default();
        let (mut same, mut diff) = (0u64, 0u64);
        for i in 0..n {
            let mut m = [0u8; 32];
            m[..8].copy_from_slice(&(0x5eed_0000_0000u64 + i as u64).to_le_bytes());
            m[31] = 0x77;
            let mut l = snipe_build::launch_from_target(m, f.user);
            l.dev_buy_lamports = 1_000_000_000;
            let p = match f.prepare(&l, 0, 12_345_678, [0; 6]) { Ok(p) => p, Err(e) => { eprintln!("bench prepare: {e:#}"); return; } };
            for k in 0..5 { st[k].push(p.st[k + 1] - p.st[k]); }
            st[5].push(p.st[5] - p.st[0]);
            // the old path for the same launch and tips
            let t = fast::mono_ns();
            let (ixs, _) = build_buy(f.user, &l, None, 2_000_000, 12_345_678);
            let mut fan = p.fan.clone();
            let _ = lat::build_tx(&f.key, f.user, &ixs, &mut fan, p.bh);
            old_ns.push(fast::mono_ns() - t);
            if p.fast_built { if f.reference(&l, &p.tips, p.bh, p.min_out).as_deref() == Some(&p.raw[65..]) { same += 1 } else { diff += 1 } }
        }
        let q = |v: &mut Vec<u64>, x: f64| { v.sort_unstable(); v[((v.len() - 1) as f64 * x).round() as usize] as f64 / 1e3 };
        println!("\n========== FAST-BENCH (n={n}, µs p50 / p99) ==========");
        for (k, name) in ["route+tips+blockhash", "derive 2 ATAs", "template patch", "ed25519 sign", "encode+frame all paths", "PREPARE TOTAL"].iter().enumerate() {
            println!("{name:24} {:8.2} / {:8.2}", q(&mut st[k], 0.5), q(&mut st[k], 0.99));
        }
        println!("{:24} {:8.2} / {:8.2}", "OLD build_buy+build_tx", q(&mut old_ns, 0.5), q(&mut old_ns, 0.99));
        println!("byte check vs full compile: {same} identical, {diff} different");
        // the derivation and the signature alone
        let mut d: Vec<u64> = Vec::new();
        let mut s: Vec<u64> = Vec::new();
        let msg = vec![7u8; 900];
        for i in 0..n {
            let mut m = [3u8; 32]; m[..8].copy_from_slice(&(i as u64).to_le_bytes());
            let t = fast::mono_ns(); let _ = pda::ata(&f.user, &m, &pda::TOKEN_2022); d.push(fast::mono_ns() - t);
            let t = fast::mono_ns(); let _ = f.key.sign(&msg); s.push(fast::mono_ns() - t);
        }
        println!("{:24} {:8.2} / {:8.2}", "one ATA derivation", q(&mut d, 0.5), q(&mut d, 0.99));
        let mut d2: Vec<u64> = Vec::new();
        for i in 0..n {
            let mut m = [3u8; 32]; m[..8].copy_from_slice(&(i as u64).to_le_bytes());
            let t = fast::mono_ns(); let _ = fast::ata_fast(&f.user, &m, &pda::TOKEN_2022); d2.push(fast::mono_ns() - t);
        }
        println!("{:24} {:8.2} / {:8.2}", "one ATA derivation FAST", q(&mut d2, 0.5), q(&mut d2, 0.99));
        println!("{:24} {:8.2} / {:8.2}", "one sign (900 B)", q(&mut s, 0.5), q(&mut s, 0.99));
        if let Some(ps) = &f.presign {
            let mut s2: Vec<u64> = Vec::new();
            let vk = f.key.verifying_key();
            let mut bad = 0;
            for _ in 0..n {
                while ps.pool_len() < 2 { std::thread::sleep(Duration::from_millis(1)); }
                let t = fast::mono_ns(); let sg = ps.sign(&msg); s2.push(fast::mono_ns() - t);
                if sg.map(|sg| vk.verify_strict(&msg, &ed25519_dalek::Signature::from_bytes(&sg)).is_err()).unwrap_or(true) { bad += 1; }
            }
            println!("{:24} {:8.2} / {:8.2}   ({bad} failed verify_strict)", "presign sign (900 B)", q(&mut s2, 0.5), q(&mut s2, 0.99));
        }
    }
}

// ================================================================================================================
// FIX2 (2026-10-19, /root/fix2/NOTES.md): result polling and landing attribution (logging only; all default off).
//  --jito-poll          after every fire, poll each jito-bundle path's bundle at +0.5 s, +2 s and +10 s: the result
//                       stream's verdicts WITH their detail and decoded error code, plus the block engine's JSON-RPC
//                       getInflightBundleStatuses (+0.5/+2/+10 s) and getBundleStatuses (+3.2/+11.2 s). Every JSON-RPC
//                       call to the block engine is spaced >= 1.1 s from the previous one (Jito: 1 request/s per IP).
//                       JITO-POLL lines + "jito_poll" send-log records. In --junk-fanout the bundles are refused (no id):
//                       JITO_POLL_PROBE_IDS=id1,id2 (old landed bundles) exercises the same code on real ids.
//  --landed-via         after a buy LANDS: which copy landed. bundles.jito.wtf /bundles/transaction/<sig> at +8/+30/+90 s:
//                       our own jito-bundle id -> "our-jito-bundle"; another bundle -> its txs / tippers (a 2-tx bundle
//                       whose other tx is a tip tx = a sender's wrapper, e.g. Helius Sender's 0.001 SOL tip tx); none ->
//                       "no-jito-bundle" (a non-bundle path of the route, or harmonic-bundle on a Harmonic leader).
//                       LANDED-VIA lines + "landed_via" send-log records.
//  --landed-via-probe SIG[:BUNDLE],..   ZERO COST: run the attribution on old signatures and exit.
//  --jito-poll-probe ID,..              ZERO COST: run the status polls on old bundle ids and exit.
// ================================================================================================================
mod fix2 {
    use super::*;
    use arbx::config::SendKind;

    fn http() -> &'static reqwest::Client {
        static C: std::sync::OnceLock<reqwest::Client> = std::sync::OnceLock::new();
        C.get_or_init(|| reqwest::Client::builder().timeout(Duration::from_secs(8)).tcp_nodelay(true).build().expect("http client"))
    }

    /// one JSON-RPC call to a block engine, spaced >= 1.1 s from the previous one (all callers share the gap)
    async fn be_call(base: &str, method: &str, ids: &[String]) -> (Option<u16>, String) {
        static GATE: std::sync::OnceLock<tokio::sync::Mutex<Option<Instant>>> = std::sync::OnceLock::new();
        let mut g = GATE.get_or_init(|| tokio::sync::Mutex::new(None)).lock().await;
        if let Some(t) = *g { let since = t.elapsed(); if since < Duration::from_millis(1100) { tokio::time::sleep(Duration::from_millis(1100) - since).await; } }
        *g = Some(Instant::now());
        drop(g);
        let url = format!("{}/api/v1/{method}", base.trim_end_matches('/'));
        let body = serde_json::json!({ "jsonrpc": "2.0", "id": 1, "method": method, "params": [ids] });
        match http().post(&url).json(&body).send().await {
            Ok(r) => { let st = r.status().as_u16(); (Some(st), r.text().await.unwrap_or_default().chars().take(64_000).collect()) }
            Err(e) => (None, format!("transport: {}", e.without_url())),
        }
    }

    /// the stream's verdicts for `sig` with detail and the decoded error code: "would-fail[0x1771: custom program error ...]"
    pub fn verdict_str(j: &send::jito::Jito, sig: &str) -> String {
        let v = j.verdicts(sig);
        if v.is_empty() { return "(none)".into(); }
        v.iter().map(|(_, o)| {
            let code = send::jito::error_code(o.detail.as_deref());
            format!("{}{}{}{}", o.outcome, o.slot.map(|x| format!("@{x}")).unwrap_or_default(), o.index.map(|i| format!("#{i}")).unwrap_or_default(),
                match (&o.detail, code) { (Some(d), Some(c)) => format!("[{c}: {}]", d.chars().take(160).collect::<String>()), (Some(d), None) => format!("[{}]", d.chars().take(160).collect::<String>()), _ => String::new() })
        }).collect::<Vec<_>>().join(",")
    }

    fn short_status(method: &str, body: &str) -> String {
        let v: serde_json::Value = serde_json::from_str(body).unwrap_or(serde_json::Value::Null);
        if let Some(e) = v.get("error").filter(|e| !e.is_null()) { return format!("error {}", e.to_string().chars().take(160).collect::<String>()); }
        let vals = v["result"]["value"].as_array().cloned().unwrap_or_default();
        if vals.is_empty() { return format!("no value ({})", body.chars().take(120).collect::<String>()); }
        vals.iter().map(|x| {
            if x.is_null() { return "null(not landed / unknown)".to_string(); }
            if method == "getInflightBundleStatuses" {
                format!("{}:{}{}", x["bundle_id"].as_str().map(|s| &s[..8.min(s.len())]).unwrap_or("?"), x["status"].as_str().unwrap_or("?"),
                    x["landed_slot"].as_u64().map(|s| format!("@{s}")).unwrap_or_default())
            } else {
                format!("{}:{}@{} err={}", x["bundle_id"].as_str().map(|s| &s[..8.min(s.len())]).unwrap_or("?"), x["confirmation_status"].as_str().unwrap_or("?"),
                    x["slot"].as_u64().map(|s| s.to_string()).unwrap_or_else(|| "?".into()), x["err"].to_string().chars().take(80).collect::<String>())
            }
        }).collect::<Vec<_>>().join(",")
    }

    /// poll one bundle (or the probe ids) at +0.5 s, +2 s, +10 s from `t0`
    async fn poll_one(path: Arc<send::Path>, sig: String, tag: u64, t0: Instant, probe_ids: Vec<String>) {
        let Some(j) = path.jito.clone() else { return };
        let base = path.fast_url().to_string();
        for (at, with_statuses) in [(500u64, false), (2000, true), (10_000, true)] {
            let due = t0 + Duration::from_millis(at);
            if let Some(d) = due.checked_duration_since(Instant::now()) { tokio::time::sleep(d).await; }
            let ids: Vec<String> = if probe_ids.is_empty() { j.bundle_of(&sig).into_iter().collect() } else { probe_ids.clone() };
            let stream = verdict_str(&j, &sig);
            let (mut infl, mut stat) = ("-".to_string(), "-".to_string());
            let (mut s1, mut s2) = (None, None);
            if !ids.is_empty() {
                let (st, b) = be_call(&base, "getInflightBundleStatuses", &ids).await; s1 = st; infl = format!("http={} {}", st.map(|x| x.to_string()).unwrap_or_else(|| "-".into()), short_status("getInflightBundleStatuses", &b));
                if with_statuses {
                    let (st, b) = be_call(&base, "getBundleStatuses", &ids).await; s2 = st; stat = format!("http={} {}", st.map(|x| x.to_string()).unwrap_or_else(|| "-".into()), short_status("getBundleStatuses", &b));
                }
            }
            let t = format!("+{:.1}s", at as f64 / 1e3);
            eprintln!("  JITO-POLL tag={tag} {t} path={} sig={} bundle={} stream={stream} inflight={infl} statuses={stat}", path.name, &sig[..16.min(sig.len())],
                ids.iter().map(|x| &x[..12.min(x.len())]).collect::<Vec<_>>().join(","));
            lat::log_json(serde_json::json!({ "ev": "jito_poll", "t_ns": arbx::feeds::clock::now_ns(), "tag": tag, "at": t, "path": path.name, "sig": sig,
                "bundles": ids, "stream": stream, "inflight": infl, "statuses": stat, "http_inflight": s1, "http_statuses": s2 }));
        }
    }

    /// --jito-poll: spawn the polls for every jito-bundle path of a fire
    pub fn spawn_jito_poll(fan: &[Arc<send::Path>], sig: &str, tag: u64) {
        if !has("--jito-poll") { return; }
        let probe: Vec<String> = if has("--junk-fanout") {
            std::env::var("JITO_POLL_PROBE_IDS").ok().map(|v| v.split(',').map(|x| x.trim().to_string()).filter(|x| !x.is_empty()).collect()).unwrap_or_default()
        } else { Vec::new() };
        let t0 = Instant::now();
        for p in fan.iter().filter(|p| p.kind == SendKind::JitoBundle && p.jito.is_some()) {
            tokio::spawn(poll_one(p.clone(), sig.to_string(), tag, t0, probe.clone()));
        }
    }

    async fn jget(url: &str) -> (Option<u16>, serde_json::Value) {
        match http().get(url).header("user-agent", "arbx-fix2").send().await {
            Ok(r) => { let st = r.status().as_u16(); (Some(st), r.json::<serde_json::Value>().await.unwrap_or(serde_json::Value::Null)) }
            Err(_) => (None, serde_json::Value::Null),
        }
    }

    /// which copy of a landed buy landed (bundle membership on the Jito explorer); `ours`: (path, bundle id) we were given
    pub async fn landed_via(sig: String, ours: Vec<(String, String)>, route: String, client: String, land_slot: Option<u64>, tag: u64) -> String {
        let mut verdict = String::from("unknown (explorer did not answer)");
        for wait in [8u64, 22, 60] {
            tokio::time::sleep(Duration::from_secs(wait)).await;
            let (st, v) = jget(&format!("https://bundles.jito.wtf/api/v1/bundles/transaction/{sig}")).await;
            let bid = v.as_array().and_then(|a| a.first()).and_then(|x| x["bundle_id"].as_str()).map(String::from);
            match (st, bid) {
                (_, Some(bid)) => {
                    if let Some((p, _)) = ours.iter().find(|(_, id)| *id == bid) { verdict = format!("our-jito-bundle path={p} bundle={}", &bid[..12]); break; }
                    let (_, b) = jget(&format!("https://bundles.jito.wtf/api/v1/bundles/bundle/{bid}")).await;
                    let b0 = b.as_array().and_then(|a| a.first()).cloned().unwrap_or(serde_json::Value::Null);
                    let ntx = b0["txSignatures"].as_array().map(|a| a.len()).unwrap_or(0);
                    let tippers: Vec<String> = b0["tippers"].as_array().into_iter().flatten().filter_map(|x| x.as_str()).map(|x| x[..8.min(x.len())].to_string()).collect();
                    let kind = if ntx == 2 { "2-tx bundle (ours + a sender's tip tx: Helius Sender / another relay's wrapper)" } else if ntx == 1 { "1-tx bundle (a relay's bundleOnly copy)" } else { "other bundle" };
                    verdict = format!("other-bundle {kind} bundle={} txs={ntx} tippers={} landed_tip={} block_index={}", &bid[..12], tippers.join("|"),
                        b0["landedTipLamports"], b0["blockIndex"]);
                    break;
                }
                (Some(404), None) | (Some(200), None) => {
                    verdict = format!("no-jito-bundle (non-bundle path of route {route}{})", if client.starts_with("Harmonic") { "; on a Harmonic leader: harmonic-bundle, nozomi or staked-rpc" } else { "" });
                    if wait >= 22 { break; }
                }
                _ => {}
            }
        }
        eprintln!("  LANDED-VIA tag={tag} sig={} land_slot={land_slot:?} route={route} client={client} via={verdict}", &sig[..16.min(sig.len())]);
        lat::log_json(serde_json::json!({ "ev": "landed_via", "t_ns": arbx::feeds::clock::now_ns(), "tag": tag, "sig": sig, "land_slot": land_slot, "route": route,
            "client": client, "via": verdict }));
        verdict
    }

    /// spawn the attribution for a landed buy (--landed-via)
    pub fn spawn_landed_via(fan: &[Arc<send::Path>], meta: &lat::Meta, land_slot: Option<u64>, tag: u64) {
        if !has("--landed-via") || land_slot.is_none() { return; }
        let ours: Vec<(String, String)> = fan.iter().filter_map(|p| p.jito.as_ref().and_then(|j| j.bundle_of(&meta.sig)).map(|id| (p.name.clone(), id))).collect();
        tokio::spawn(landed_via(meta.sig.clone(), ours, meta.route.clone(), meta.client.clone(), land_slot, tag));
    }

    /// --landed-via-probe SIG[:BUNDLE],.. (zero cost): the attribution on old signatures
    pub async fn landed_via_probe(list: &str) -> Result<()> {
        let mut hs = Vec::new();
        for (i, item) in list.split(',').map(str::trim).filter(|x| !x.is_empty()).enumerate() {
            let (sig, bid) = match item.split_once(':') { Some((a, b)) => (a.to_string(), Some(b.to_string())), None => (item.to_string(), None) };
            let ours = bid.map(|b| vec![("jito-bundle".to_string(), b)]).unwrap_or_default();
            hs.push(tokio::spawn(landed_via(sig, ours, "probe".into(), String::new(), None, i as u64)));
        }
        for h in hs { let _ = h.await; }
        Ok(())
    }

    /// --jito-poll-probe ID,.. (zero cost): the status polls on old bundle ids against the config's block engine
    pub async fn jito_poll_probe(base: &str, list: &str) -> Result<()> {
        let ids: Vec<String> = list.split(',').map(|x| x.trim().to_string()).filter(|x| !x.is_empty()).collect();
        for m in ["getInflightBundleStatuses", "getBundleStatuses"] {
            for chunk in ids.chunks(5) {
                let (st, b) = be_call(base, m, chunk).await;
                eprintln!("  JITO-POLL-PROBE {m} http={st:?} {}", short_status(m, &b));
            }
        }
        Ok(())
    }
}

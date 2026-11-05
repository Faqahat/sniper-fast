//! apex_probe — APEX S2 launch-snipe PROBE (separate from the live dip engine).
//!
//! When a creator on the watchlist launches a pump.fun token, buy in the CREATE slot as early as possible, fired straight
//! from the create shred (no RPC on the hot path), then sell after a fixed hold (default 2 s). Its job is to MEASURE how
//! fast we land after a launch: create shred -> decision -> each send -> landing (slot, index in the block, position vs the
//! create tx, the dev buy and the other buyers), and the realized P&L from the actual balance changes.
//!
//! Modes: `--mode shadow` (default: never sends; logs the would-be buy, its timing and the slot's real buyers) and
//! `--mode live` (refuses to start without --kill-below and --max-runtime-min; size <= 0.25 SOL; one position at a time).
//! Spec: /home/moiz/sniper-apexsnipe/REPORT.md (S2) + FROZEN.md; docs: ops/apex_probe/README.md.
//!
//! Reuses the lib: feeds::start (shred/deshred + executed feeds), snipe::detect_launch / router_create, snipe_build (v3 buy /
//! sell), build (compile + sign + nonce + ATA close), send::Paths (every send kind, rate budgets, keep-alives), fast::FastConn
//! (the dip engine's own HTTP/1.1 send connections), rpc::Rpc, wallet (the keystore unlock + passphrase prompt).

#![recursion_limit = "512"]

mod bench;
mod entry;
mod fastbuild;
mod logic;
mod route;
#[cfg(test)]
mod tests;

use anyhow::{bail, Context, Result};
use arbx::config::{self, SendKind};
use arbx::fast::{self, Ack, FastConn};
use arbx::feeds::{self, clock::now_ns, Event};
use arbx::snipe::{self, Launch};
use arbx::snipe_build;
use arbx::tx::{b58, Pk};
use arbx::{build, pda, rpc, send, wallet};
use base64::Engine as _;
use clap::Parser;
use ed25519_dalek::SigningKey;
use logic::*;
use std::collections::{HashMap, HashSet, VecDeque};
use std::io::Write as _;
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex, RwLock};
use std::time::{Duration, Instant};

const MAINNET_GENESIS: &str = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d";

#[derive(Parser, Debug, Clone)]
#[command(name = "apex_probe", about = "APEX S2 launch-snipe probe: buy watched creators' launches from the create shred, sell after a hold, measure the landing")]
pub struct Args {
    /// shadow (never sends) | live
    #[arg(long, default_value = "shadow")]
    mode: String,
    /// minimal TOML: wallet, wallet_keystore, rpc_url, [[send]], [[feed]] (the dip engine's config shape)
    #[arg(long)]
    config: Option<String>,
    /// provider secrets for ${...} in the config (never printed)
    #[arg(long, default_value = "/root/sniper/deploy/.env")]
    env_file: String,
    /// creators to buy: JSON list of pubkeys or of objects with "creator" (re-read when the file changes)
    #[arg(long, default_value = "/root/apex/watchlist.json")]
    watchlist: String,
    /// which create key is matched: creator (the CreateEvent creator, as the APEX backtests: the args' creator, or the
    /// holder-rewards PDA on a holder-reward launch) | args (the create args' creator: the pre-11-04 `creator`) | signer (fee
    /// payer) | either (CreateEvent creator or signer)
    #[arg(long = "match", default_value = "creator")]
    match_on: String,
    /// APEX-3 entry score: off | log (score every watched create and record it, never gate: default) | on (skip a create
    /// scoring under the threshold; computed before signing)
    #[arg(long, default_value = "log")]
    entry_filter: String,
    /// the entry model (ops/apex_probe/entry_export.py: trees, bin edges, threshold, creator history)
    #[arg(long, default_value = "/root/apex/entry_model.json")]
    entry_model: String,
    /// override the model file's threshold (score >= this passes)
    #[arg(long)]
    entry_thr: Option<f64>,
    /// OFFLINE: score the exporter's entry_cases.jsonl with --entry-model and compare with the APEX-3 code's scores
    #[arg(long)]
    entry_validate: Option<String>,
    /// with --entry-validate: raw create (+ bundle) txs (ops/apex_probe/entry_fetch_txs.py) to derive the inputs from the txs
    #[arg(long)]
    entry_txs: Option<String>,
    /// SOL per buy (max 0.1)
    #[arg(long, default_value_t = 0.05)]
    size_sol: f64,
    /// buys fired at most (live)
    #[arg(long, default_value_t = 20)]
    max_buys: u32,
    /// total SOL at risk incl. fees: realized net loss + open positions' worst case
    #[arg(long, default_value_t = 1.5)]
    max_spend_sol: f64,
    /// stop new buys when the wallet balance is under this (SOL); required live
    #[arg(long)]
    kill_below: Option<f64>,
    /// stop new buys after this many minutes; required live
    #[arg(long)]
    max_runtime_min: Option<f64>,
    /// positions open at once
    #[arg(long, default_value_t = 1)]
    max_open: usize,
    /// buy guard: pay at most this much above the expected post-create price (0.2 = 20%)
    #[arg(long, default_value_t = 0.20)]
    buy_guard: f64,
    /// sell guard: min SOL out = expected x (1 - guard) on the first 3 tries, then 0 (never stuck)
    #[arg(long, default_value_t = 0.50)]
    sell_guard: f64,
    /// sell everything this long after our confirmed fill
    #[arg(long, default_value_t = 2000)]
    hold_ms: u64,
    /// buy recipe: lanes (APEX-FEES: one durable-nonce copy per lane, ONE tip each; needs --nonce-accounts live) |
    /// multitip (v1: one tx with every lane's tip, --routes)
    #[arg(long, default_value = "lanes")]
    recipe: String,
    /// lanes per leader class: "class=path[:tip][@priority],...;default=..." (lamports) or @FILE holding that string
    #[arg(long, default_value = logic::LANES_DEFAULT)]
    lanes: String,
    /// priority fee (lamports) of a lane without @priority (paid on reverts too: keep small)
    #[arg(long, default_value_t = 100_000)]
    prio_lamports: u64,
    /// multitip recipe: per leader client routes, a preset (v8, v9, v12, v13) or "class=p1+p2;...;default=..."
    #[arg(long, default_value = "v13")]
    routes: String,
    /// FIRST-OR-REVERT off (then --buy-guard applies): by default the buy reverts unless the curve is still exactly where the
    /// create + the creator bundle seen before signing left it
    #[arg(long)]
    no_first_or_revert: bool,
    /// first-or-revert tolerance on min_tokens_out (0.005 = 0.5%)
    #[arg(long, default_value_t = 0.005)]
    first_tol: f64,
    /// after a watched create, wait up to this long (µs) for the creator-bundle buys of the same slot in the shreds
    #[arg(long, default_value_t = 300)]
    bundle_wait_us: u64,
    /// end the bundle window as soon as the create's feed moves past the create's position (another mint's tx in its
    /// slot, or a later slot) instead of waiting out --bundle-wait-us
    #[arg(long, default_value_t = true, action = clap::ArgAction::Set)]
    bundle_early_exit: bool,
    /// auto = wait only for creators whose watchlist bundle_txs_median >= 0.5 (until that many are seen) | always | never
    #[arg(long, default_value = "auto")]
    bundle_wait: String,
    /// spin on the feed channel (one core busy; no futex wake-up between the feed and the decision)
    #[arg(long)]
    busy_poll: bool,
    /// pin the hot thread to this core (the runtime's threads then avoid it)
    #[arg(long)]
    pin_core: Option<usize>,
    /// keep the hot path warm: one throw-away build every this many ms while idle (0 = off)
    #[arg(long, default_value_t = 20)]
    warm_ms: u64,
    /// v2's lib builder instead of the v3 fast build (precomputed keys, fast derive, presigned nonces)
    #[arg(long)]
    no_fast_build: bool,
    /// sign without pre-computed nonces
    #[arg(long)]
    no_presign: bool,
    /// ZERO-COST benchmark of the hot path on this machine (N launches; no config, no network): see bench.rs
    #[arg(long)]
    bench: Option<usize>,
    /// add the next leader's route on Harmonic leaders too (the dip engine runs --no-union-harmonic)
    #[arg(long)]
    union_harmonic: bool,
    /// first sell try goes here (tipless staked forwarder in the dip engine)
    #[arg(long, default_value = "staked-rpc")]
    sell_path: String,
    /// every sell retry also goes here (its tip in the tx); "" = none
    #[arg(long, default_value = "nozomi")]
    sell_fallback: String,
    /// on-chain slot deadline (Lighthouse): the buy fails on chain after create slot + N
    #[arg(long, default_value_t = 1)]
    max_slot_delta: u64,
    /// shadow only: no slot guard
    #[arg(long)]
    no_slot_guard: bool,
    #[arg(long, default_value_t = 100_000)]
    cu_limit: u32,
    /// micro-lamports per CU (5,000,000 x 100k CU = 0.0005 SOL, the dip engine's buy priority)
    #[arg(long, default_value_t = 5_000_000)]
    cu_price_micro: u64,
    #[arg(long, default_value_t = 120_000)]
    sell_cu_limit: u32,
    #[arg(long, default_value_t = 5_000_000)]
    sell_cu_price_micro: u64,
    /// sell retry interval
    #[arg(long, default_value_t = 1000)]
    sell_retry_ms: u64,
    /// give a sell up (UNSOLD; the end check retries) after this long
    #[arg(long, default_value_t = 60)]
    sell_deadline_s: u64,
    /// durable-nonce accounts of this wallet (one per line): each buy = one variant per tip group, one tip paid
    #[arg(long)]
    nonce_accounts: Option<String>,
    /// also buy Mayhem launches (APEX excludes them)
    #[arg(long)]
    allow_mayhem: bool,
    /// also buy legacy `create` launches (Token-2022 layout assumed by the v3 buy: off)
    #[arg(long)]
    allow_legacy: bool,
    /// shadow: unlock the real keystore anyway (default: a throwaway signer, the config wallet's pubkey as payer)
    #[arg(long)]
    unlock: bool,
    /// JSONL records
    #[arg(long, default_value = "apex_probe.jsonl")]
    out: String,
    /// OFFLINE replay: synthesize creates from a collector launches.jsonl and run detection + decision + build + sign
    #[arg(long)]
    replay_launches: Option<String>,
    /// replay: watch every creator with >= this many launches in the file (when --watchlist does not exist)
    #[arg(long, default_value_t = 3)]
    replay_min_launches: usize,
}

// ==================================================================================================================
// records
// ==================================================================================================================

/// the record writer's messages: a record, or "flush everything and tell me" (the shutdown)
pub enum RecMsg { Line(serde_json::Value), Flush(crossbeam_channel::Sender<()>) }

pub struct Recorder { tx: crossbeam_channel::Sender<RecMsg> }

/// the writer of this process (the shutdown flushes it even while tasks still hold a Recorder)
static REC_TX: std::sync::OnceLock<crossbeam_channel::Sender<RecMsg>> = std::sync::OnceLock::new();

impl Recorder {
    pub fn open(path: &str) -> Result<(Recorder, std::thread::JoinHandle<()>)> {
        let f = std::fs::OpenOptions::new().create(true).append(true).open(path).with_context(|| format!("--out {path}"))?;
        let (tx, rx) = crossbeam_channel::unbounded::<RecMsg>();
        let h = std::thread::Builder::new().name("apex-rec".into()).spawn(move || {
            let mut w = std::io::BufWriter::new(f);
            for m in rx.iter() {
                match m {
                    RecMsg::Line(v) => { let _ = writeln!(w, "{v}"); if rx.is_empty() { let _ = w.flush(); } }
                    RecMsg::Flush(done) => { let _ = w.flush(); let _ = w.get_ref().sync_data(); let _ = done.send(()); }
                }
            }
            let _ = w.flush();
        })?;
        let _ = REC_TX.set(tx.clone());
        Ok((Recorder { tx }, h))
    }
    /// one record: `ev` + the fields, t = wall-clock ns
    pub fn ev(&self, ev: &str, mut v: serde_json::Value) {
        if let Some(o) = v.as_object_mut() { o.insert("ev".into(), ev.into()); o.insert("t".into(), now_ns().into()); }
        let _ = self.tx.send(RecMsg::Line(v));
    }
    /// write + fsync everything queued so far; true when the writer confirmed within `timeout`
    pub fn flush(&self, timeout: Duration) -> bool { flush_via(&self.tx, timeout) }
}

fn flush_via(tx: &crossbeam_channel::Sender<RecMsg>, timeout: Duration) -> bool {
    let (dtx, drx) = crossbeam_channel::bounded::<()>(1);
    tx.send(RecMsg::Flush(dtx)).is_ok() && drx.recv_timeout(timeout).is_ok()
}

/// SHUTDOWN (FRA shadow run 1: the v1 probe printed DONE and never exited — its last step waited for the record writer,
/// whose channel stayed open while feed / keep-alive / poller tasks still held the shared state): flush the records, then
/// end the process. Nothing waits for threads or the runtime.
fn hard_exit(code: i32) -> ! {
    if let Some(tx) = REC_TX.get() { if !flush_via(tx, Duration::from_secs(5)) { eprintln!("records: the writer did not confirm the flush within 5 s"); } }
    use std::io::Write as _;
    let _ = std::io::stderr().flush();
    let _ = std::io::stdout().flush();
    std::process::exit(code)
}

/// what a stop signal does: 1st = no new buys (open positions finish their exit, then the end check, then exit);
/// 2nd = the same, and the process exits the moment the end check is done (nothing else waited for); 3rd = exit NOW
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SigAction { Drain, DrainThenExit, ExitNow }

pub fn sig_action(n: u32) -> SigAction { match n { 0 | 1 => SigAction::Drain, 2 => SigAction::DrainThenExit, _ => SigAction::ExitNow } }

/// set by the main flow once the end check + summary are written: a signal after that exits at once
static SHUTDOWN_DONE: AtomicBool = AtomicBool::new(false);

fn say(l: String) { eprintln!("{} {l}", chrono_hms()); }
fn chrono_hms() -> String {
    let s = now_ns() / 1_000_000_000 + 5 * 3600; // PKT (owner)
    format!("{:02}:{:02}:{:02}", (s / 3600) % 24, (s / 60) % 60, s % 60)
}
fn sol(l: i64) -> String { format!("{:+.4}", l as f64 / 1e9) }
fn gmgn(m: &Pk) -> String { format!("https://gmgn.ai/sol/token/{}", b58(m)) }
fn redact(s: &str) -> String { arbx::rpc::scrub(s) }

// ==================================================================================================================
// config
// ==================================================================================================================

#[derive(Default, serde::Deserialize)]
struct Cfg {
    #[serde(default)] wallet: Option<String>,
    #[serde(default)] wallet_keystore: Option<String>,
    #[serde(default)] rpc_url: Option<String>,
    #[serde(rename = "send", default)] sends: Vec<config::SendPath>,
    #[serde(rename = "feed", default)] feeds: Vec<config::Feed>,
}

/// the dip engine's keystore unlock (snipe_engine.rs keystore_key): passphrase from the tty (hidden), verified against
/// the config's wallet
fn keystore_key(path: &str, expect: Option<&str>) -> Result<SigningKey> {
    wallet::harden_process();
    let blob = std::fs::read_to_string(path).with_context(|| format!("reading {path}"))?;
    let pass = wallet::read_pass()?;
    let key = wallet::keypair(&wallet::decrypt(&blob, pass.as_bytes())?)?;
    let got = b58(&key.verifying_key().to_bytes());
    if let Some(w) = expect { if got != w { bail!("{path} holds {got}, but the config's wallet is {w}"); } }
    Ok(key)
}

fn throwaway_key() -> Result<SigningKey> {
    use std::io::Read;
    let mut seed = [0u8; 32];
    std::fs::File::open("/dev/urandom")?.read_exact(&mut seed)?;
    Ok(SigningKey::from_bytes(&seed))
}

// ==================================================================================================================
// shared state
// ==================================================================================================================

/// how a path is fired from the hot thread
enum FastKind { Http { conn: Arc<FastConn>, json: bool }, Udp, Slow }

fn json_kind(k: SendKind) -> bool {
    matches!(k, SendKind::Helius | SendKind::Shyft | SendKind::Rpc | SendKind::Nozomi | SendKind::ZeroSlot | SendKind::Falcon | SendKind::Everstake | SendKind::JupiterTx)
}
fn bin_kind(k: SendKind) -> bool {
    matches!(k, SendKind::Haan | SendKind::Bolt | SendKind::Iris | SendKind::Lunar | SendKind::NodeOne | SendKind::BlockRazor | SendKind::Landx | SendKind::Glaive)
}

/// first sightings of our own signatures
#[derive(Clone, Debug, Default)]
struct Sighting {
    /// first shred/deshred arrival (wall ns), its slot and feed
    shred: Option<(u64, u64, u16)>,
    /// executed feed: slot, index, ok, wall ns, (tokens, curve SOL, vsol, vtok) of our TradeEvent on the mint
    exec: Option<(u64, Option<u64>, bool, u64, Option<(u64, u64, u64, u64)>)>,
}

#[derive(Clone, Copy, Debug)]
enum NonceSt { Ready([u8; 32]), Fired { value: [u8; 32], deadline: u64 } }

struct NoncePool { keys: Vec<Pk>, st: Mutex<Vec<NonceSt>> }

impl NoncePool {
    fn take(&self) -> Option<(usize, Pk, [u8; 32])> {
        let g = self.st.lock().unwrap();
        g.iter().enumerate().find_map(|(i, s)| if let NonceSt::Ready(v) = s { Some((i, self.keys[i], *v)) } else { None })
    }
    fn fired(&self, i: usize, value: [u8; 32], deadline: u64) { self.st.lock().unwrap()[i] = NonceSt::Fired { value, deadline }; }
}

struct Shared {
    a: Args,
    caps: Caps,
    live: bool,
    key: SigningKey,
    user: Pk,
    rpc: Arc<rpc::Rpc>,
    handle: tokio::runtime::Handle,
    t_start: Instant,
    match_on: MatchOn,
    /// no new buys (signal, cap, runtime)
    stopping: AtomicBool,
    /// feeds / paths / pollers (the very end)
    infra_stop: Arc<AtomicBool>,
    ledger: Mutex<Ledger>,
    bh: Mutex<Option<([u8; 32], Instant)>>,
    balance: AtomicU64,
    max_slot: AtomicU64,
    watch: RwLock<Arc<HashSet<Pk>>>,
    bundle_hint: RwLock<Arc<HashMap<Pk, f64>>>,
    rec: Recorder,
    /// our signatures -> trade id
    sig_watch: Mutex<HashMap<[u8; 64], u64>>,
    sightings: Mutex<HashMap<[u8; 64], Sighting>>,
    /// tracked mints: every executed tx that touched them
    mint_recs: Mutex<HashMap<Pk, Vec<ExecRec>>>,
    /// latest virtual reserves (vsol, vtok) per tracked mint, from TradeEvents
    curve: Mutex<HashMap<Pk, (u64, u64)>>,
    /// every mint a live buy was sent for (the end check)
    touched: Mutex<Vec<Launch>>,
    seq: AtomicU64,
    open_tasks: AtomicUsize,
    routes: route::Routes,
    fast: Vec<FastKind>,
    sell_path: Arc<send::Path>,
    sell_fb: Option<Arc<send::Path>>,
    guard: Option<GuardEnc>,
    nonce: Option<NoncePool>,
    /// v3 fast build (None: --no-fast-build or its self-test failed)
    fastb: Option<fastbuild::FastCtx>,
    /// v3 lane templates, by (tip, priority, guard)
    tpls: HashMap<fastbuild::TplKey, arbx::fast::Template>,
    /// buys that never landed (their sigs: a late landing is checked at the end)
    unlanded: Mutex<Vec<(u64, Vec<[u8; 64]>)>>,
    feed_names: Vec<String>,
    worst: u64,
    /// APEX-3 entry score (--entry-filter / --entry-model): None = not scored
    entry_mode: entry::EntryMode,
    entry: Option<entry::EntryModel>,
}

impl Shared {
    fn stop(&self, why: &str) {
        if !self.stopping.swap(true, Ordering::SeqCst) {
            say(format!("STOP NEW BUYS: {why} (open positions finish their exit, then the end check)"));
            self.rec.ev("stop", serde_json::json!({ "why": why }));
        }
    }
    fn balance(&self) -> Option<u64> { let b = self.balance.load(Ordering::Relaxed); (b != u64::MAX).then_some(b) }
    fn blockhash(&self, max_age: Duration) -> Option<[u8; 32]> {
        self.bh.lock().unwrap().filter(|(_, t)| t.elapsed() <= max_age).map(|x| x.0)
    }
}

// ==================================================================================================================
// main
// ==================================================================================================================

fn main() -> Result<()> {
    let a = Args::parse();
    if let Some(f) = a.replay_launches.clone() { return replay(&a, &f); }
    if let Some(f) = a.entry_validate.clone() { return entry_validate(&a, &f); }
    if let Some(n) = a.bench { return bench::run(n.clamp(10, 100_000), a.pin_core, a.warm_ms); }
    let _ = dotenvy::from_filename(&a.env_file);
    let live = match a.mode.as_str() { "live" => true, "shadow" => false, m => bail!("--mode {m}: shadow|live") };
    let caps = validate_caps(&CapArgs { live, size_sol: a.size_sol, max_buys: a.max_buys, max_spend_sol: a.max_spend_sol, kill_below_sol: a.kill_below,
        max_runtime_min: a.max_runtime_min, max_open: a.max_open, buy_guard: a.buy_guard, sell_guard: a.sell_guard, hold_ms: a.hold_ms })
        .map_err(|e| anyhow::anyhow!("REFUSED: {e}"))?;
    if live && a.no_slot_guard { bail!("REFUSED: --no-slot-guard is shadow-only (the on-chain deadline is what stops a late buy)"); }
    if !(0..=3).contains(&a.max_slot_delta) { bail!("REFUSED: --max-slot-delta must be 0..3"); }
    if a.cu_price_micro > 50_000_000 || a.sell_cu_price_micro > 50_000_000 { bail!("REFUSED: CU price above 50M micro-lamports"); }
    let match_on = MatchOn::parse(&a.match_on).map_err(|e| anyhow::anyhow!(e))?;
    let entry_mode = entry::EntryMode::parse(&a.entry_filter).map_err(|e| anyhow::anyhow!(e))?;
    let entry_model = if entry_mode == entry::EntryMode::Off { None } else {
        match entry::EntryModel::load(&a.entry_model) {
            Ok(mut m) => {
                if let Some(t) = a.entry_thr { m.thr = t; }
                let age_h = (entry::now_bt() - m.data_end_bt) as f64 / 3600.0;
                say(format!("entry score {}: {} ({} trees, thr {:.6}, history {} creators, data end {:.1} h ago, sha256 {})", a.entry_filter, m.name, m.n_trees(), m.thr,
                    m.n_creators(), age_h, &m.sha256[..16]));
                Some(m)
            }
            Err(e) if entry_mode == entry::EntryMode::Log => { say(format!("entry score NOT recorded (log mode): --entry-model {e}")); None }
            Err(e) => bail!("REFUSED: --entry-filter on needs the model: {e}"),
        }
    };
    let lanes_mode = match a.recipe.as_str() { "lanes" => true, "multitip" => false, r => bail!("--recipe {r}: lanes|multitip") };
    if !(0.0..=0.05).contains(&a.first_tol) { bail!("REFUSED: --first-tol must be 0..0.05"); }
    if a.prio_lamports > 2_000_000 { bail!("REFUSED: --prio-lamports above 0.002 SOL"); }
    if a.bundle_wait_us > 5_000 { bail!("REFUSED: --bundle-wait-us above 5000"); }
    if !["auto", "always", "never"].contains(&a.bundle_wait.as_str()) { bail!("--bundle-wait auto|always|never"); }
    let lane_text = if lanes_mode {
        match a.lanes.strip_prefix('@') { Some(f) => std::fs::read_to_string(f).with_context(|| format!("--lanes @{f}"))?.lines().filter(|l| !l.trim_start().starts_with('#')).collect::<Vec<_>>().join(";"), None => a.lanes.clone() }
    } else { a.routes.clone() };
    let route_spec = parse_lanes(&lane_text).map_err(|e| anyhow::anyhow!(e))?;
    if live && lanes_mode && a.nonce_accounts.is_none() {
        bail!("REFUSED: the lanes recipe sends one copy per lane: live it needs --nonce-accounts FILE (the shared nonce is what lets at most one copy land)");
    }
    if live && a.nonce_accounts.is_some() && dip_engine_running() {
        bail!("REFUSED: a snipe_engine (dip engine) runs on this server: its durable-nonce accounts may be the same; stop it first");
    }
    let cfg_path = a.config.clone().context("--config is required (wallet, rpc_url, [[feed]], [[send]])")?;
    let cfg: Cfg = toml::from_str(&std::fs::read_to_string(&cfg_path).with_context(|| format!("reading {cfg_path}"))?)
        .with_context(|| format!("parsing {cfg_path}"))?;
    let watch = load_watch(&a.watchlist).with_context(|| format!("--watchlist {}", a.watchlist))?;
    if live && watch.is_empty() { bail!("REFUSED: the watchlist is empty"); }

    // wallet: live = the keystore (hidden passphrase prompt, as the dip engine); shadow = a throwaway signer
    let (key, user) = if live || a.unlock {
        let ks = cfg.wallet_keystore.as_deref().filter(|s| !s.is_empty()).context("wallet_keystore missing in --config")?;
        let k = keystore_key(ks, cfg.wallet.as_deref())?;
        let u = k.verifying_key().to_bytes();
        (k, u)
    } else {
        let k = throwaway_key()?;
        let u = cfg.wallet.as_deref().map(arbx::tx::pk).unwrap_or_else(|| k.verifying_key().to_bytes());
        (k, u)
    };
    say(format!("apex_probe {} | payer {} | watchlist {} creators | size {} SOL, max {} buys, max at risk {} SOL, kill below {}, runtime {}, hold {} ms, guard +{:.0}% / sell -{:.0}%",
        if live { "LIVE" } else { "SHADOW (never sends)" }, b58(&user), watch.len(), a.size_sol, caps.max_buys, a.max_spend_sol,
        a.kill_below.map(|k| format!("{k} SOL")).unwrap_or("-".into()), a.max_runtime_min.map(|m| format!("{m} min")).unwrap_or("until stopped".into()),
        caps.hold_ms, caps.buy_guard * 100.0, caps.sell_guard * 100.0));

    let rpc_url = cfg.rpc_url.as_deref().filter(|s| !s.is_empty()).map(|u| config::expand(u).with_context(|| format!("rpc_url {u}: an env var is missing")))
        .transpose()?.context("rpc_url missing in --config")?;
    let excl = a.pin_core;
    let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(6)
        .on_thread_start(move || { if let Some(c) = excl { arbx::fast::exclude_core(c); } }).enable_all().build()?;
    let r = rt.block_on(run(a, cfg, caps, live, key, user, Arc::new(rpc::Rpc::new(rpc_url)), watch, match_on, route_spec, (entry_mode, entry_model)));
    // never wait for the runtime / feed / keep-alive threads: flush the records, exit
    match r {
        Ok(()) => hard_exit(0),
        Err(e) => { eprintln!("Error: {e:#}"); hard_exit(1) }
    }
}

fn load_watch(path: &str) -> Result<HashSet<Pk>> {
    let t = std::fs::read_to_string(path)?;
    parse_watchlist(&t).map_err(|e| anyhow::anyhow!(e))
}

#[allow(clippy::too_many_arguments)]
async fn run(a: Args, cfg: Cfg, caps: Caps, live: bool, key: SigningKey, user: Pk, rpc: Arc<rpc::Rpc>, watch: HashSet<Pk>, match_on: MatchOn,
             route_spec: HashMap<String, Vec<LaneSpec>>, entry: (entry::EntryMode, Option<entry::EntryModel>)) -> Result<()> {
    // mainnet only (a wrong-cluster RPC would feed blockhashes and balances)
    let g = tokio::time::timeout(Duration::from_secs(10), rpc.call("getGenesisHash", serde_json::json!([]))).await
        .map_err(|_| anyhow::anyhow!("getGenesisHash timed out: refusing to start"))?.map_err(|e| anyhow::anyhow!("getGenesisHash: {}", redact(&format!("{e:#}"))))?;
    if g.as_str() != Some(MAINNET_GENESIS) { bail!("rpc_url genesis {g} is not mainnet: refusing to start"); }
    let infra_stop = Arc::new(AtomicBool::new(false));

    // ---- send paths: only those the routes / sells name
    let mut want: Vec<String> = route_spec.values().flatten().map(|l| l.path.clone()).collect();
    want.sort(); want.dedup();
    want.push(a.sell_path.clone());
    if !a.sell_fallback.is_empty() { want.push(a.sell_fallback.clone()); }
    let sends: Vec<config::SendPath> = cfg.sends.iter().filter(|s| want.contains(&s.name)).cloned()
        .map(|mut s| { s.enabled = true; s }).collect();
    let missing: Vec<&String> = want.iter().filter(|n| !sends.iter().any(|s| s.name == **n)).collect();
    if !missing.is_empty() { say(format!("NOTE: paths named but not in the config: {}", missing.iter().map(|s| s.as_str()).collect::<Vec<_>>().join(", "))); }
    let (paths, notes) = send::Paths::new(&sends, send::PathsOpts { queue_ms: 0, payer: Some(user) }, arbx::rec::Rec::off(), true).await?;
    for n in &notes { say(format!("send note: {n}")); }
    let sell_path = paths.index(&a.sell_path).map(|i| paths.list[i].clone()).with_context(|| format!("--sell-path {}: not built", a.sell_path))?;
    let sell_fb = if a.sell_fallback.is_empty() { None } else {
        Some(paths.index(&a.sell_fallback).map(|i| paths.list[i].clone()).with_context(|| format!("--sell-fallback {}: not built", a.sell_fallback))?)
    };
    let (routes, rnotes) = route::Routes::resolve(&route_spec, paths.list.clone(), !a.union_harmonic)?;
    for n in &rnotes { say(format!("NOTE: {n}")); }
    for l in routes.describe() { say(l); }
    match route::refresh(&rpc).await {
        Ok(m) => say(m),
        Err(e) if live => bail!("leader book failed (routes by leader client need it): {e:#}"),
        Err(e) => say(format!("leader book failed (shadow: default route only): {e:#}")),
    }
    paths.start(infra_stop.clone(), Duration::from_secs(2), |m: String| eprintln!("  keepalive: {m}"));

    // ---- FAST: own HTTP/1.1 connections for the JSON / binary kinds, UDP from the hot thread, the rest async
    let (atx, arx) = crossbeam_channel::unbounded::<Ack>();
    let mut fastk = Vec::new();
    for p in &routes.paths {
        let k = if (p.kind == SendKind::Landx || p.kind == SendKind::FalconUdp) && p.fast_udp_ok() { FastKind::Udp }
            else if (json_kind(p.kind) || bin_kind(p.kind)) && !p.fast_preflight() {
                let json = json_kind(p.kind);
                match FastConn::start(&p.name, p.fast_url(), if json { "application/json" } else { "application/octet-stream" }, &p.fast_headers(), p.fast_ping(), atx.clone(), infra_stop.clone()) {
                    Ok(c) => FastKind::Http { conn: c, json },
                    Err(e) => { say(format!("FAST: {} stays async: {}", p.name, e.split(": url").next().unwrap_or(""))); FastKind::Slow }
                }
            } else { FastKind::Slow };
        say(format!("path {:14} -> {}", p.name, match &k { FastKind::Http { json: true, .. } => "own HTTP/1.1 (json)", FastKind::Http { .. } => "own HTTP/1.1 (binary)", FastKind::Udp => "UDP from the hot thread", FastKind::Slow => "async send (spawned first)" }));
        fastk.push(k);
    }
    drop(atx);

    // ---- slot guard (verified by simulation; fail closed live)
    let guard = if a.no_slot_guard { None } else {
        match verify_guard(&rpc, &key, user).await {
            Ok(gx) => { say(format!("SLOT-GUARD verified on chain: Lighthouse disc {} op {} acct {}; deadline = create slot + {}", gx.disc, gx.op, gx.acct, a.max_slot_delta)); Some(gx) }
            Err(e) if live => bail!("REFUSED: slot guard not verified: {e:#}"),
            Err(e) => { say(format!("SLOT-GUARD not verified ({e:#}): shadow uses the dip engine's encoding")); Some(GUARD_DEFAULT) }
        }
    };

    // ---- nonce pool (optional)
    let nonce = match &a.nonce_accounts {
        None => None,
        Some(f) => {
            let keys = parse_nonce_file(&std::fs::read_to_string(f).with_context(|| format!("--nonce-accounts {f}"))?).map_err(|e| anyhow::anyhow!("--nonce-accounts {f}: {e}"))?;
            let (slot, vals) = read_nonces(&rpc, &keys).await?;
            let mut st = Vec::new();
            for (k, v) in keys.iter().zip(&vals) {
                match nonce_check(v, &user) { Ok(val) => st.push(NonceSt::Ready(val)), Err(e) => bail!("REFUSED: nonce account {}: {e}", b58(k)) }
            }
            say(format!("NONCE: {} durable-nonce account(s) verified at slot {slot}: one variant per tip group, one tip paid per landed buy", keys.len()));
            Some(NoncePool { keys, st: Mutex::new(st) })
        }
    };

    // ---- worst case of one round trip (caps): lanes = the dearest single lane (one lands); multitip = every tip family
    let lanes_mode = a.recipe == "lanes";
    let (max_tips, max_prio): (u64, u64) = {
        let (mut mt, mut mp) = (0u64, a.cu_limit as u64 * a.cu_price_micro / 1_000_000);
        for c in routes.map.values() {
            if lanes_mode {
                for l in c {
                    let p = &routes.paths[l.pi];
                    let tip = l.tip.unwrap_or_else(|| p.tip(0).map_or(0, |t| t.1));
                    mt = mt.max(tip);
                    mp = mp.max(l.prio.unwrap_or(a.prio_lamports));
                }
            } else {
                let pp: Vec<(Option<(Pk, u64)>, &[Pk])> = c.iter().map(|l| (routes.paths[l.pi].tip(0), routes.paths[l.pi].tip_accounts())).collect();
                let s: u64 = tip_groups(&pp).iter().filter_map(|g| g.0.map(|t| t.1)).sum();
                let one: u64 = tip_groups(&pp).iter().filter_map(|g| g.0.map(|t| t.1)).max().unwrap_or(0);
                mt = mt.max(if nonce.is_some() { one } else { s });
            }
        }
        (mt, mp)
    };
    let sell_tips = sell_fb.as_ref().and_then(|p| p.tip(0)).map_or(0, |t| t.1);
    let worst = worst_cost(caps.size, max_tips, a.cu_limit, cu_price_for(max_prio, a.cu_limit), sell_tips, a.sell_cu_limit, a.sell_cu_price_micro, 3);
    say(format!("worst case per round trip {:.4} SOL (size + buy tip {:.4} + priority {:.4} + fees + rents + 3 sell tries) | recipe {}{}", worst as f64 / 1e9,
        max_tips as f64 / 1e9, max_prio as f64 / 1e9, a.recipe, if a.no_first_or_revert { "" } else { " + FIRST-OR-REVERT" }));

    // ---- v3 fast build (self-tested; falls back to the lib builder on any disagreement)
    let fastb = if a.no_fast_build { None } else {
        let ps = if a.no_presign { None } else { let p = arbx::fast::Presigner::new(&key); p.start(300, infra_stop.clone()); Some(p) };
        let fx = fastbuild::FastCtx::new(&key, user, ps);
        match fastbuild::selftest(&fx, 300) {
            Ok(m) => { say(m); Some(fx) }
            Err(e) if live => bail!("REFUSED: fast build self-test: {e} (or run with --no-fast-build)"),
            Err(e) => { say(format!("FAST-BUILD off (self-test: {e})")); None }
        }
    };
    // ---- v3 templates: one per lane shape (the routes' tips + priorities), compiled from probe keys now
    let mut tpls: HashMap<fastbuild::TplKey, arbx::fast::Template> = HashMap::new();
    if let (Some(fx), "lanes") = (&fastb, a.recipe.as_str()) {
        for l in routes.map.values().flatten() {
            let p = &routes.paths[l.pi];
            let tip = p.tip(0).map(|(_, m)| l.tip.unwrap_or(m)).filter(|t| *t > 0);
            let prio = l.prio.unwrap_or(a.prio_lamports);
            let key = (tip, prio, guard.is_some());
            if tpls.contains_key(&key) { continue; }
            match fx.template(caps.size, a.cu_limit, tip, prio, guard) {
                Ok(t) => { tpls.insert(key, t); }
                Err(e) => say(format!("TEMPLATE for tip {tip:?} prio {prio}: {e} (that lane full-builds)")),
            }
        }
        say(format!("TEMPLATES: {} lane shape(s) compiled", tpls.len()));
    }
    let (rec, rec_h) = Recorder::open(&a.out)?;
    // ---- feeds
    let fcfg: Vec<config::Feed> = cfg.feeds.iter().filter(|f| f.enabled).cloned().collect();
    if fcfg.is_empty() { bail!("no enabled [[feed]] in --config"); }
    if !fcfg.iter().any(|f| matches!(f.kind, config::FeedKind::YellowstoneTx)) { say("NOTE: no yellowstone-tx (executed) feed: landing index + buyers ahead come from getBlock only".into()); }
    let mut interest = snipe::pump_interest();
    interest.keys.insert(*snipe::PUMP_ROUTER);
    let (ftx, frx) = crossbeam_channel::unbounded::<Event>();
    let fs = feeds::start(&fcfg, Arc::new(interest), ftx, infra_stop.clone(), &tokio::runtime::Handle::current(), &arbx::rec::Rec::off(), None)?;
    say(format!("feeds: {}", fs.names.join(", ")));

    let sh = Arc::new(Shared {
        caps: caps.clone(), live, key, user, rpc: rpc.clone(), handle: tokio::runtime::Handle::current(), t_start: Instant::now(), match_on,
        stopping: AtomicBool::new(false), infra_stop: infra_stop.clone(), ledger: Mutex::new(Ledger::default()), bh: Mutex::new(None),
        balance: AtomicU64::new(u64::MAX), max_slot: AtomicU64::new(0), watch: RwLock::new(Arc::new(watch)),
        bundle_hint: RwLock::new(Arc::new(parse_bundle_hints(&std::fs::read_to_string(&a.watchlist).unwrap_or_default()))), rec, sig_watch: Mutex::new(HashMap::new()),
        sightings: Mutex::new(HashMap::new()), mint_recs: Mutex::new(HashMap::new()), curve: Mutex::new(HashMap::new()), touched: Mutex::new(Vec::new()),
        seq: AtomicU64::new(1), open_tasks: AtomicUsize::new(0), routes, fast: fastk, sell_path, sell_fb, guard, nonce, fastb, tpls, unlanded: Mutex::new(Vec::new()),
        feed_names: fs.names.clone(), worst, a: a.clone(), entry_mode: entry.0, entry: entry.1,
    });
    sh.rec.ev("start", serde_json::json!({ "mode": a.mode, "payer": b58(&user), "watch": sh.watch.read().unwrap().len(), "size": caps.size, "max_buys": caps.max_buys,
        "max_spend": caps.max_spend, "kill_below": caps.kill_below, "max_runtime_s": caps.max_runtime_s, "hold_ms": caps.hold_ms, "buy_guard": caps.buy_guard,
        "sell_guard": caps.sell_guard, "routes": a.routes, "route_map": sh.routes.describe(), "sell_path": a.sell_path, "sell_fallback": a.sell_fallback,
        "slot_guard": guard.map(|g| format!("{g:?}")), "max_slot_delta": a.max_slot_delta, "recipe": a.recipe, "lanes": lane_text_of(&a),
        "first_or_revert": !a.no_first_or_revert, "first_tol": a.first_tol, "bundle_wait_us": a.bundle_wait_us, "bundle_wait": a.bundle_wait, "prio_lamports": a.prio_lamports, "busy_poll": a.busy_poll, "pin_core": a.pin_core,
        "warm_ms": a.warm_ms, "fast_build": !a.no_fast_build, "presign": !a.no_presign, "nonce": sh.nonce.as_ref().map(|n| n.keys.len()), "worst": worst,
        "cu_limit": a.cu_limit, "cu_price": a.cu_price_micro, "feeds": fs.names.clone(), "match": a.match_on,
        "entry_filter": a.entry_filter, "entry_model": sh.entry.as_ref().map(|m| serde_json::json!({ "path": a.entry_model, "name": m.name, "sha256": m.sha256, "thr": m.thr,
            "trees": m.n_trees(), "creators": m.n_creators(), "data_end_bt": m.data_end_bt, "u_default": m.u_default })) }));

    // ---- background: blockhash, balance, nonce refresh, watchlist reload, leader book, fast acks
    spawn_pollers(&sh);
    route::start_refresh(rpc.clone(), infra_stop.clone());
    {
        let sh2 = sh.clone();
        std::thread::Builder::new().name("apex-acks".into()).spawn(move || {
            for ak in arx {
                let ms = ak.t_ack.saturating_sub(ak.t_write) as f64 / 1e6;
                sh2.rec.ev("fast_ack", serde_json::json!({ "trade": ak.tag >> 8, "path": ak.path, "ack_ms": ms, "status": ak.status, "reply": ak.body.chars().take(160).collect::<String>() }));
            }
        })?;
    }
    // wait for the first blockhash + the fast connections
    let t = Instant::now();
    while t.elapsed() < Duration::from_secs(8) {
        let conns_up = sh.fast.iter().all(|k| match k { FastKind::Http { conn, .. } => conn.up.load(Ordering::Relaxed), _ => true });
        if sh.blockhash(Duration::from_secs(10)).is_some() && conns_up && (!live || sh.balance().is_some()) { break; }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }
    if sh.blockhash(Duration::from_secs(10)).is_none() { bail!("no blockhash from the RPC after 8 s"); }
    for (i, k) in sh.fast.iter().enumerate() { if let FastKind::Http { conn, .. } = k { if !conn.up.load(Ordering::Relaxed) { say(format!("NOTE: fast connection {} not up yet (falls back to async while down)", sh.routes.paths[i].name)); } } }

    // ---- self-test: every route's copy passes each path's own check (tip, CU price), size <= 1232
    selftest(&sh).map_err(|e| anyhow::anyhow!("REFUSED: self-test: {e}"))?;
    if live {
        let b = sh.balance().context("REFUSED: wallet balance unknown")?;
        let k = caps.kill_below.unwrap_or(0);
        if b < k + worst { bail!("REFUSED: balance {:.4} SOL is below --kill-below {:.4} + one worst-case round trip {:.4}", b as f64 / 1e9, k as f64 / 1e9, worst as f64 / 1e9); }
        say(format!("wallet balance {:.4} SOL", b as f64 / 1e9));
    }

    // ---- signals: no new buys, finish exits, end check
    {
        use tokio::signal::unix::{signal, SignalKind};
        let (mut term, mut int, mut hup) = (signal(SignalKind::terminate())?, signal(SignalKind::interrupt())?, signal(SignalKind::hangup())?);
        let sh2 = sh.clone();
        tokio::spawn(async move {
            let mut n = 0u32;
            loop {
                let name = tokio::select! { _ = term.recv() => "SIGTERM", _ = int.recv() => "SIGINT", _ = hup.recv() => "SIGHUP" };
                n += 1;
                if SHUTDOWN_DONE.load(Ordering::SeqCst) { say(format!("signal {name} after the end check: exiting")); hard_exit(0); }
                match sig_action(n) {
                    SigAction::Drain => sh2.stop(&format!("signal {name}")),
                    SigAction::DrainThenExit => {
                        sh2.stop(&format!("signal {name}"));
                        say(format!("signal {name} again: exiting as soon as the open position's exit + the end check are done (a 3rd signal exits NOW)"));
                    }
                    SigAction::ExitNow => {
                        let open = sh2.open_tasks.load(Ordering::SeqCst);
                        say(format!("signal {name} a 3rd time: exiting NOW{}", if open > 0 { format!(" — {open} position(s) still open: check the wallet / sell by hand") } else { String::new() }));
                        sh2.rec.ev("forced_exit", serde_json::json!({ "signal": name, "open": open }));
                        hard_exit(130);
                    }
                }
            }
        });
    }

    // ---- the hot thread
    let hot = {
        let sh2 = sh.clone();
        let (btx, brx) = crossbeam_channel::unbounded::<(Event, u64)>();
        let sh3 = sh.clone();
        std::thread::Builder::new().name("apex-bulk".into()).spawn(move || bulk_loop(sh3, brx))?;
        std::thread::Builder::new().name("apex-hot".into()).spawn(move || hot_loop(sh2, frx, btx))?
    };
    say(format!("READY: watching {} creators' launches ({})", sh.watch.read().unwrap().len(), if live { "LIVE buys" } else { "shadow: no sends" }));

    // ---- wait: runtime / stop, then the open positions, then the end check
    let mut last_status = Instant::now();
    loop {
        tokio::time::sleep(Duration::from_millis(250)).await;
        if let Some(m) = caps.max_runtime_s { if sh.t_start.elapsed().as_secs() >= m { sh.stop("max runtime reached"); } }
        if live { if let (Some(b), Some(k)) = (sh.balance(), caps.kill_below) { if b < k { sh.stop("wallet balance under --kill-below"); } } }
        if sh.stopping.load(Ordering::SeqCst) && sh.open_tasks.load(Ordering::SeqCst) == 0 { break; }
        if last_status.elapsed() >= Duration::from_secs(60) {
            last_status = Instant::now();
            let l = sh.ledger.lock().unwrap().clone();
            let (it, fwd, cr) = (HOT_ITEMS.load(Ordering::Relaxed), HOT_FWD_NS.load(Ordering::Relaxed), HOT_CREATES.load(Ordering::Relaxed));
            say(format!("STATUS buys {}/{} open {} realized {} SOL at risk {:.4} | balance {} | slot {} | hot: {} items ({:.0}/s), {} creates, forward {:.2} us/item", l.buys_fired, caps.max_buys, l.open, sol(l.realized),
                l.at_risk() as f64 / 1e9, sh.balance().map(|b| format!("{:.4}", b as f64 / 1e9)).unwrap_or("-".into()), sh.max_slot.load(Ordering::Relaxed),
                it, it as f64 / sh.t_start.elapsed().as_secs_f64().max(1.0), cr, fwd as f64 / 1e3 / (it.saturating_sub(cr)).max(1) as f64));
            sh.rec.ev("hot_stats", serde_json::json!({ "items": it, "creates": cr, "fwd_ns": fwd }));
        }
    }
    // the end check is bounded (each sell has its own deadline; this caps RPC stalls)
    if live && tokio::time::timeout(Duration::from_secs(240), end_check(&sh)).await.is_err() {
        say("END CHECK did not finish within 240 s — CHECK THE WALLET BY HAND".into());
        sh.rec.ev("end_check_timeout", serde_json::json!({}));
    }
    let l = sh.ledger.lock().unwrap().clone();
    let summary = serde_json::json!({ "buys_fired": l.buys_fired, "realized_lamports": l.realized, "realized_sol": l.realized as f64 / 1e9, "runtime_s": sh.t_start.elapsed().as_secs(),
        "balance_end": sh.balance() });
    sh.rec.ev("summary", summary.clone());
    say(format!("APEX_PROBE DONE: buys {} realized {} SOL runtime {:.0} min (records {})", l.buys_fired, sol(l.realized), sh.t_start.elapsed().as_secs_f64() / 60.0, a.out));
    SHUTDOWN_DONE.store(true, Ordering::SeqCst);
    sh.infra_stop.store(true, Ordering::SeqCst);
    // the hot thread sees infra_stop within 100 ms; it is not joined (main exits the process right after the flush)
    let _ = (hot, rec_h);
    if !sh.rec.flush(Duration::from_secs(5)) { say("records: the writer did not confirm the flush within 5 s".into()); }
    Ok(())
}

// ==================================================================================================================
// pollers
// ==================================================================================================================

fn spawn_pollers(sh: &Arc<Shared>) {
    // blockhash every 400 ms (the hot path signs with the cached one)
    let s = sh.clone();
    tokio::spawn(async move {
        while !s.infra_stop.load(Ordering::Relaxed) {
            if let Ok(Ok((h, _))) = tokio::time::timeout(Duration::from_secs(2), s.rpc.latest_blockhash()).await { *s.bh.lock().unwrap() = Some((h, Instant::now())); }
            tokio::time::sleep(Duration::from_millis(400)).await;
        }
    });
    // wallet balance every 2 s (the gate reads the last value; never on the hot path)
    let s = sh.clone();
    tokio::spawn(async move {
        while !s.infra_stop.load(Ordering::Relaxed) {
            let r = s.rpc.call("getBalance", serde_json::json!([b58(&s.user), { "commitment": "processed" }])).await;
            if let Some(b) = r.ok().and_then(|v| v["value"].as_u64()) { s.balance.store(b, Ordering::Relaxed); }
            tokio::time::sleep(Duration::from_secs(2)).await;
        }
    });
    // watchlist reload when the file changes
    let s = sh.clone();
    tokio::spawn(async move {
        let mtime = |p: &str| std::fs::metadata(p).and_then(|m| m.modified()).ok();
        let mut last = mtime(&s.a.watchlist);
        while !s.infra_stop.load(Ordering::Relaxed) {
            tokio::time::sleep(Duration::from_secs(15)).await;
            let m = mtime(&s.a.watchlist);
            if m.is_some() && m != last {
                last = m;
                match load_watch(&s.a.watchlist) {
                    Ok(w) if !w.is_empty() => {
                        say(format!("WATCHLIST reloaded: {} creators", w.len()));
                        s.rec.ev("watch_reload", serde_json::json!({ "n": w.len() }));
                        *s.watch.write().unwrap() = Arc::new(w);
                        *s.bundle_hint.write().unwrap() = Arc::new(parse_bundle_hints(&std::fs::read_to_string(&s.a.watchlist).unwrap_or_default()));
                    }
                    Ok(_) => say("WATCHLIST reload: empty file ignored (kept the old list)".into()),
                    Err(e) => say(format!("WATCHLIST reload failed (kept the old list): {e:#}")),
                }
            }
        }
    });
    // nonce refresh: a fired account is back once its value changed (a variant landed / failed) or 150 slots past the deadline
    if sh.nonce.is_some() {
        let s = sh.clone();
        tokio::spawn(async move {
            let np = s.nonce.as_ref().unwrap();
            while !s.infra_stop.load(Ordering::Relaxed) {
                tokio::time::sleep(Duration::from_millis(300)).await;
                let fired: Vec<usize> = np.st.lock().unwrap().iter().enumerate().filter(|(_, x)| matches!(x, NonceSt::Fired { .. })).map(|(i, _)| i).collect();
                if fired.is_empty() { continue; }
                let keys: Vec<Pk> = fired.iter().map(|&i| np.keys[i]).collect();
                let Ok((ctx, vals)) = read_nonces(&s.rpc, &keys).await else { continue };
                let mut g = np.st.lock().unwrap();
                for (&i, v) in fired.iter().zip(&vals) {
                    if let NonceSt::Fired { value, deadline } = g[i] {
                        match nonce_check(v, &s.user) {
                            Ok(nv) if nv != value => g[i] = NonceSt::Ready(nv),
                            Ok(_) if ctx >= deadline + 150 => g[i] = NonceSt::Ready(value),
                            Ok(_) => {}
                            Err(e) => say(format!("NONCE {} unusable: {e}", b58(&np.keys[i]))),
                        }
                    }
                }
            }
        });
    }
}

// ==================================================================================================================
// the hot thread
// ==================================================================================================================

/// the hot thread's own state: dedup of creates, the events put aside during a bundle window
/// the hot thread's own state: dedup of creates, the creates put aside during a bundle window, and the hand-off of
/// everything that is not a create to the bulk thread (v4: the hot thread only classifies + forwards non-creates, so the
/// items queued ahead of a create cost ~0.1-0.3 µs each instead of the full handling + the drop)
struct Hot { rx: crossbeam_channel::Receiver<Event>, pending: VecDeque<(Event, u64)>, seen: HashSet<Pk>, order: VecDeque<Pk>, buf: Vec<u8>,
    bulk: crossbeam_channel::Sender<(Event, u64)>, q_at_dequeue: usize }

/// hot-thread counters (STATUS line + summary): items seen, forwarded to the bulk thread, creates handled
pub static HOT_ITEMS: AtomicU64 = AtomicU64::new(0);
pub static HOT_FWD_NS: AtomicU64 = AtomicU64::new(0);
pub static HOT_CREATES: AtomicU64 = AtomicU64::new(0);

fn hot_loop(sh: Arc<Shared>, rx: crossbeam_channel::Receiver<Event>, bulk: crossbeam_channel::Sender<(Event, u64)>) {
    if let Some(c) = sh.a.pin_core { say(format!("hot thread pinned to core {c}: {}", arbx::fast::pin_to_core(c))); }
    let mut h = Hot { rx, pending: VecDeque::new(), seen: HashSet::new(), order: VecDeque::new(), buf: Vec::with_capacity(4096), bulk, q_at_dequeue: 0 };
    let busy = sh.a.busy_poll;
    let warm = Duration::from_millis(sh.a.warm_ms);
    let mut last_warm = Instant::now();
    let mut spins: u32 = 0;
    while !sh.infra_stop.load(Ordering::Relaxed) {
        let (ev, t_hot) = if let Some(x) = h.pending.pop_front() { x } else if busy {
            match h.rx.try_recv() {
                Ok(e) => (e, now_ns()),
                Err(crossbeam_channel::TryRecvError::Empty) => {
                    spins = spins.wrapping_add(1);
                    std::hint::spin_loop();
                    if spins % 4096 == 0 {
                        if sh.infra_stop.load(Ordering::Relaxed) { break; }
                        if !warm.is_zero() && last_warm.elapsed() >= warm { warm_build(&sh); last_warm = Instant::now(); }
                    }
                    continue;
                }
                Err(crossbeam_channel::TryRecvError::Disconnected) => break,
            }
        } else {
            let wait = if warm.is_zero() { Duration::from_millis(100) } else { warm.saturating_sub(last_warm.elapsed()).max(Duration::from_micros(200)) };
            match h.rx.recv_timeout(wait) {
                Ok(e) => (e, now_ns()),
                Err(crossbeam_channel::RecvTimeoutError::Timeout) => {
                    if !warm.is_zero() && last_warm.elapsed() >= warm { warm_build(&sh); last_warm = Instant::now(); }
                    continue;
                }
                Err(crossbeam_channel::RecvTimeoutError::Disconnected) => break,
            }
        };
        HOT_ITEMS.fetch_add(1, Ordering::Relaxed);
        // creates are handled here; everything else (executed feed, our own sigs, trades, status) goes to the bulk thread
        match ev {
            Event::Tx(a) if a.executed.is_none() && snipe::is_create_candidate(&a.tx) => {
                h.q_at_dequeue = h.rx.len();
                HOT_CREATES.fetch_add(1, Ordering::Relaxed);
                on_create(&sh, a, t_hot, &mut h);
            }
            other => { let t0 = now_ns(); let _ = h.bulk.send((other, t_hot)); HOT_FWD_NS.fetch_add(now_ns() - t0, Ordering::Relaxed); }
        }
    }
}

/// the bulk thread: our own signatures in the shreds (the landing clock), the executed feed (landings, positions, curve
/// states), feed status lines. Never on the path from a create shred to our first send.
fn bulk_loop(sh: Arc<Shared>, rx: crossbeam_channel::Receiver<(Event, u64)>) {
    while !sh.infra_stop.load(Ordering::Relaxed) {
        match rx.recv_timeout(Duration::from_millis(100)) {
            Ok((Event::Tx(a), _)) => on_tx(&sh, a),
            Ok((Event::Status { feed, msg }, _)) => say(format!("feed {}: {msg}", sh.feed_names.get(feed as usize).map(|s| s.as_str()).unwrap_or("?"))),
            Ok(_) | Err(crossbeam_channel::RecvTimeoutError::Timeout) => {}
            Err(crossbeam_channel::RecvTimeoutError::Disconnected) => break,
        }
    }
}

/// a throw-away build of one lane copy for a synthetic launch (never sent): keeps the build code, its data and the core warm
fn warm_build(sh: &Shared) {
    static N: AtomicU64 = AtomicU64::new(0);
    let i = N.fetch_add(1, Ordering::Relaxed);
    let mut mint = [0x3Cu8; 32];
    mint[..8].copy_from_slice(&i.to_le_bytes());
    let l = snipe_build::launch_from_target(mint, [0x4Du8; 32]);
    let c = BuyCfg { user: sh.user, spend: sh.caps.size, min_out: 1, cu_limit: sh.a.cu_limit, cu_price: 0, guard: Some((GUARD_DEFAULT, 1)) };
    let ln = LaneCopy { pi: 0, tip: Some(([0x5Eu8; 32], 1_000_000)), prio: 100_000 };
    match &sh.fastb {
        Some(f) => {
            let k = f.keys(&l);
            match sh.tpls.iter().next() {
                Some((key, t)) => {
                    let mut b = Vec::with_capacity(1232);
                    let ln0 = LaneCopy { pi: 0, tip: key.0.map(|l| ([0x5Eu8; 32], l)), prio: key.1 };
                    let _ = f.lane_copy_tpl(t, &k, ([0xEEu8; 32], [0xDDu8; 32]), &ln0, 1, key.2.then_some(1), &mut b);
                }
                None => { let _ = f.lane_copy(&c, &k, ([0xEEu8; 32], [0xDDu8; 32]), &ln); }
            }
        }
        None => { let _ = build_lane_copies(&sh.key, &c, &l, ([0xEEu8; 32], [0xDDu8; 32]), std::slice::from_ref(&ln)); }
    }
}

/// bulk thread: a non-create tx
fn on_tx(sh: &Arc<Shared>, a: feeds::Arrival) {
    sh.max_slot.fetch_max(a.slot, Ordering::Relaxed);
    if let Some(ok) = a.executed {
        on_exec(sh, &a, ok);
        return;
    }
    // our own tx in the shreds: the first sighting (the landing clock)
    let ours = { let sw = sh.sig_watch.lock().unwrap(); !sw.is_empty() && sw.contains_key(&a.tx.sig) };
    if ours {
        let mut g = sh.sightings.lock().unwrap();
        let e = g.entry(a.tx.sig).or_default();
        if e.shred.is_none() { e.shred = Some((a.t_rx, a.slot, a.feed)); }
    }
}

/// hot thread: a create candidate
fn on_create(sh: &Arc<Shared>, a: feeds::Arrival, t_hot: u64, h: &mut Hot) {
    sh.max_slot.fetch_max(a.slot, Ordering::Relaxed);
    let (launch, kind) = match snipe::detect_launch(&a.tx) { Some(l) => (l, "create"), None => match router_launch(&a.tx) { Some(l) => (l, "router"), None => return } };
    if !h.seen.insert(launch.mint) { return; }
    h.order.push_back(launch.mint);
    if h.order.len() > 50_000 { if let Some(m) = h.order.pop_front() { h.seen.remove(&m); } }
    let w = sh.watch.read().unwrap().clone();
    let ev = event_creator(&launch);
    let Some(mkey) = sh.match_on.key(&w, &ev, &launch.creator, a.tx.keys.first()) else { return };
    decide(sh, &a, launch, kind, t_hot, h, Who { ev, mkey });
}

/// executed feed: our landings, and every tx on a tracked mint (create, buys, sells) for the position analysis
fn on_exec(sh: &Arc<Shared>, a: &feeds::Arrival, ok: bool) {
    let ours = sh.sig_watch.lock().unwrap().contains_key(&a.tx.sig);
    let e = a.exec.as_ref();
    if ours {
        let te = e.and_then(|x| x.trades.iter().find(|t| t.user == sh.user)).map(|t| (t.tok, t.sol, t.vsol, t.vtok));
        let mut g = sh.sightings.lock().unwrap();
        let s = g.entry(a.tx.sig).or_default();
        if s.exec.is_none() { s.exec = Some((a.slot, e.map(|x| x.index), ok, a.t_rx, te)); }
    }
    let Some(e) = e else { return };
    let mut mr = sh.mint_recs.lock().unwrap();
    if mr.is_empty() { return; }
    let mut mints: Vec<Pk> = e.trades.iter().map(|t| t.mint).chain(e.creates.iter().map(|c| c.mint)).filter(|m| mr.contains_key(m)).collect();
    mints.sort_unstable();
    mints.dedup();
    for m in mints {
        let buys: Vec<(Pk, u64, u64)> = e.trades.iter().filter(|t| t.mint == m && t.buy).map(|t| (t.user, t.sol, t.tok)).collect();
        let sells = e.trades.iter().filter(|t| t.mint == m && !t.buy).count();
        if let Some(t) = e.trades.iter().rev().find(|t| t.mint == m) { sh.curve.lock().unwrap().insert(m, (t.vsol, t.vtok)); }
        if let Some(v) = mr.get_mut(&m) {
            v.push(ExecRec { slot: a.slot, index: e.index, sig: a.tx.sig, ok: e.ok, is_create: e.creates.iter().any(|c| c.mint == m), buys, sells });
        }
    }
}

/// FIRST-OR-REVERT state: the create tx's own buy legs + the creator-bundle buys of the same slot seen in the shreds within
/// --bundle-wait-us (other events are put aside and handled right after the fire). -> (legs, exact, bundle txs seen,
/// first bundle sighting µs after the create, why not exact)
fn bundle_window(sh: &Arc<Shared>, a: &feeds::Arrival, mint: &Pk, creator: &Pk, h: &mut Hot) -> Window {
    let mut w = Window { legs: Vec::new(), exact: true, why: None, n: 0, first_us: None, end: "no_wait", hint: None, waited_us: 0, pulled: 0, eb: Vec::new(), eb_end: false, eb_unseen: 0 };
    match snipe::bundle_legs(&a.tx, mint) {
        Some(snipe::Legs::Buys(v)) => w.legs.extend(v),
        Some(snipe::Legs::NotBuy) if snipe::dev_buy_effective(&a.tx, mint) == 0 => {} // a create with no buy
        _ => { w.exact = false; w.why = Some("create_legs_unknown"); }
    }
    w.hint = sh.bundle_hint.read().unwrap().get(creator).copied();
    let (wait, expect) = bundle_plan(&sh.a.bundle_wait, w.hint, sh.a.bundle_wait_us);
    if wait == 0 { return w; }
    let t0 = Instant::now();
    let t_end = t0 + Duration::from_micros(wait);
    let mut sigs: HashSet<[u8; 64]> = HashSet::new();
    sigs.insert(a.tx.sig);
    w.end = "timeout";
    while Instant::now() < t_end {
        if expect.is_some_and(|e| w.n >= e) { w.end = "count"; break; }
        let ev = match h.rx.try_recv() { Ok(e) => e, Err(crossbeam_channel::TryRecvError::Empty) => { std::hint::spin_loop(); continue; } Err(_) => break };
        let t = now_ns();
        w.pulled += 1;
        let mut moved_on = false;
        if let Event::Tx(b) = &ev {
            if b.executed.is_none() && sigs.insert(b.tx.sig) {
                match window_step(a.slot, a.feed, mint, b.slot, b.feed, &b.tx) {
                    Step::Bundle(v) => { w.legs.extend(v); w.n += 1; w.first_us.get_or_insert(b.t_rx.saturating_sub(a.t_rx) / 1000); entry_bundle_tx(sh, &mut w, &b.tx, mint); }
                    Step::NotPlain => { w.exact = false; w.why = Some("bundle_tx_not_a_plain_buy"); entry_bundle_tx(sh, &mut w, &b.tx, mint); }
                    Step::MovedOn => moved_on = true,
                    Step::Other => {}
                }
            }
        }
        if matches!(&ev, Event::Tx(b) if b.executed.is_none() && snipe::is_create_candidate(&b.tx)) { h.pending.push_back((ev, t)); } else { let _ = h.bulk.send((ev, t)); }
        if moved_on && sh.a.bundle_early_exit { w.end = "moved_on"; break; }
    }
    if w.end == "timeout" && expect.is_some_and(|e| w.n >= e) { w.end = "count"; }
    w.waited_us = t0.elapsed().as_micros() as u64;
    w
}

/// entry score: one bundle-window tx of the mint in the create slot (the tape's bundle ends at the first non-buy)
fn entry_bundle_tx(sh: &Shared, w: &mut Window, tx: &arbx::tx::Tx, mint: &Pk) {
    if sh.entry.is_none() || w.eb_end { return; }
    match entry::entry_legs(tx, mint) {
        Some(entry::ELegs::Buys(v)) => w.eb.extend(v),
        Some(entry::ELegs::NotBuy) => w.eb_end = true,
        Some(entry::ELegs::Unseen) => w.eb_unseen += 1,
        None => {}
    }
}

/// one shred tx seen during a create's bundle window
#[derive(Debug, PartialEq)]
pub enum Step { Bundle(Vec<(bool, u64, u64)>), NotPlain, MovedOn, Other }

/// classify it: a buy of the mint in the create's slot = a bundle leg; another pump tx touching the mint there = not a plain
/// buy (state unknown); the create's OWN feed showing a later tx of that slot on another mint, or a later slot = moved on
/// (that feed delivers a slot in block order and the creator bundle sits right after the create); anything else = other
pub fn window_step(c_slot: u64, c_feed: u16, mint: &Pk, slot: u64, feed: u16, tx: &arbx::tx::Tx) -> Step {
    if slot == c_slot {
        match snipe::bundle_legs(tx, mint) {
            Some(snipe::Legs::Buys(v)) => Step::Bundle(v),
            Some(_) => Step::NotPlain,
            None if feed == c_feed => Step::MovedOn,
            None => Step::Other,
        }
    } else if feed == c_feed && slot > c_slot { Step::MovedOn } else { Step::Other }
}

/// what the creator-bundle window saw: the legs (create's + bundle), whether the state is exact, the bundle txs found,
/// why it ended (no_wait | count | moved_on | timeout), the creator's watchlist hint, how long it waited, items pulled
struct Window { legs: Vec<(bool, u64, u64)>, exact: bool, why: Option<&'static str>, n: usize, first_us: Option<u64>, end: &'static str, hint: Option<f64>, waited_us: u64, pulled: usize,
    /// entry score: the bundle's buy legs + buyers as entry::entry_legs reads them (lenient: wrappers, multi-wallet txs),
    /// until the first non-buy of the mint in the slot; unseen = bundle txs touching the mint with no readable buy
    eb: Vec<((bool, u64, u64), Pk)>, eb_end: bool, eb_unseen: usize }

/// a watched create's keys: the CreateEvent creator (entry-score history) and the watchlist key that matched (bundle hint)
#[derive(Clone, Copy)]
struct Who { ev: Pk, mkey: Pk }

/// the decision and (live) the fire. No RPC, no file I/O before the sends: records go to the writer thread afterwards.
fn decide(sh: &Arc<Shared>, a: &feeds::Arrival, launch: Launch, kind: &str, t_hot: u64, h: &mut Hot, who: Who) {
    let t_dec0 = now_ns();
    let c = &sh.caps;
    let sol_quote = snipe::create_quote_mint(&a.tx).is_none();
    let skip = |sh: &Arc<Shared>, why: &str, extra: serde_json::Value| {
        let mut r = serde_json::json!({ "mint": b58(&launch.mint), "creator": b58(&launch.creator), "ev_creator": b58(&who.ev), "match_key": b58(&who.mkey),
            "signer": a.tx.keys.first().map(b58), "slot": a.slot, "kind": kind, "skip": why, "gmgn": gmgn(&launch.mint) });
        // the entry score of a create skipped before the bundle window: create legs only (bund_src "before_window")
        if extra.get("entry").is_none() { if let Some(e) = entry_score(sh, a, &launch, &who, None) { r["entry"] = e.1; } }
        if let (Some(o), Some(x)) = (r.as_object_mut(), extra.as_object()) { for (k, v) in x { o.insert(k.clone(), v.clone()); } }
        sh.rec.ev("create_seen", r);
        say(format!("WATCHED create {} skipped: {why}", b58(&launch.mint)));
    };
    if let Some(why) = skip_reason(&launch, sol_quote, sh.a.allow_legacy, sh.a.allow_mayhem) { skip(sh, why, serde_json::json!({})); return; }
    // gate + commit under one lock (live); shadow: only the stop
    let worst = sh.worst;
    if sh.live {
        let mut l = sh.ledger.lock().unwrap();
        match gate(c, &l, worst, true, sh.balance(), sh.t_start.elapsed().as_secs(), sh.stopping.load(Ordering::SeqCst)) {
            Gate::Go => { l.buys_fired += 1; l.open += 1; l.open_worst += worst; }
            Gate::Skip(why) => { drop(l); skip(sh, why, serde_json::json!({})); return; }
            Gate::Stop(why) => { drop(l); skip(sh, why, serde_json::json!({})); sh.stop(why); return; }
        }
    } else if sh.stopping.load(Ordering::SeqCst) { return; }
    let release = |sh: &Arc<Shared>| { if sh.live { let mut l = sh.ledger.lock().unwrap(); l.open -= 1; l.open_worst -= worst; l.buys_fired -= 1; } };

    // ---- the price we accept
    let first = !sh.a.no_first_or_revert;
    let win = if first { Some(bundle_window(sh, a, &launch.mint, &who.mkey, h)) } else { None };
    // ---- APEX-3 entry score: gate (on) before signing; log mode records it after the sends (no latency added)
    let mut entry_rec: Option<serde_json::Value> = None;
    if sh.entry_mode == entry::EntryMode::On {
        if let Some((pass, e)) = entry_score(sh, a, &launch, &who, win.as_ref()) {
            if !pass { release(sh); skip(sh, "entry_score", serde_json::json!({ "entry": e })); return; }
            entry_rec = Some(e);
        }
    }
    let (legs, mut exact, bundle_seen, bundle_us, mut why_inexact) = match &win { Some(w) => (w.legs.clone(), w.exact, w.n, w.first_us, w.why), None => (Vec::new(), false, 0, None, None) };
    let t_state = now_ns();
    let vq = if first {
        match curve_after_legs(&legs) {
            Some(v) => v,
            None => { exact = false; why_inexact = why_inexact.or(Some("a_leg_would_fail")); snipe::CURVE_VQ0 + launch.dev_buy_lamports }
        }
    } else { snipe::CURVE_VQ0 + launch.dev_buy_lamports };
    let (expected, min_out) = if first { first_min_out(vq, c.size, sh.a.first_tol) } else { let e = expected_tokens(launch.dev_buy_lamports, c.size); (e, buy_min_out(e, c.buy_guard)) };

    // ---- copies
    let (fan, meta) = sh.routes.fan(a.slot);
    let deadline = sh.guard.map(|g| (g, a.slot + sh.a.max_slot_delta));
    let cfgb = BuyCfg { user: sh.user, spend: c.size, min_out, cu_limit: sh.a.cu_limit, cu_price: sh.a.cu_price_micro, guard: deadline };
    let lanes_mode = sh.a.recipe == "lanes";
    let lease = sh.nonce.as_ref().and_then(|n| n.take());
    let ej = || serde_json::json!({ "entry": entry_rec.clone().or_else(|| entry_score(sh, a, &launch, &who, win.as_ref()).map(|e| e.1)) });
    if sh.live && lanes_mode && lease.is_none() { release(sh); skip(sh, "no_nonce_ready", ej()); return; }
    let Some(bh) = sh.blockhash(Duration::from_secs(20)) else { release(sh); skip(sh, "blockhash_stale", ej()); return; };
    let t_b0 = now_ns();
    let id = sh.seq.fetch_add(1, Ordering::Relaxed);
    // live: register the nonce as fired before the first copy leaves
    if sh.live { if let (Some(np), Some((i, _, v)), Some((_, dl))) = (&sh.nonce, lease, deadline) { np.fired(i, v, dl); } }
    let mut sends: Vec<serde_json::Value> = Vec::new();
    let mut t_first_write = 0u64;
    let mut copies: Vec<Copy> = Vec::new();
    let mut t_built = 0u64;
    let mut lane_info: Vec<(Pk, u64)> = Vec::new(); // (tip account or zero, priority) per copy
    let mut build_paths: Vec<&'static str> = Vec::new();
    let built: std::result::Result<(), String> = if lanes_mode {
        let lc: Vec<LaneCopy> = fan.iter().map(|l| {
            let p = &sh.routes.paths[l.pi];
            let tip = p.tip(0).map(|(acct, min)| (acct, l.tip.unwrap_or(min))).filter(|t| t.1 > 0);
            LaneCopy { pi: l.pi, tip, prio: l.prio.unwrap_or(sh.a.prio_lamports) }
        }).collect();
        lane_info = lc.iter().map(|x| (x.tip.map_or([0u8; 32], |t| t.0), x.prio)).collect();
        // shadow without nonce accounts: a stand-in nonce (the copies' shape and size are the real ones; never sent)
        let n = lease.map(|(_, k, v)| (k, v)).unwrap_or(([0xEEu8; 32], [0xDDu8; 32]));
        // sign + send lane by lane, in the lanes' order: the first copy leaves after ONE signature
        let mut r = Ok(());
        let fk = sh.fastb.as_ref().map(|f| f.keys(&launch)); // the launch's keys once, for every lane
        let mut tbuf: Vec<u8> = Vec::with_capacity(1232);
        for ln in &lc {
            build_paths.push(match (&sh.fastb, sh.tpls.contains_key(&(ln.tip.map(|t| t.1).filter(|t| *t > 0), ln.prio, deadline.is_some()))) { (Some(_), true) => "template", (Some(_), false) => "fast", _ => "lib" });
            let tpl = sh.tpls.get(&(ln.tip.map(|t| t.1).filter(|t| *t > 0), ln.prio, deadline.is_some()));
            let one = match (&sh.fastb, &fk, tpl) {
                (Some(f), Some(k), Some(t)) => match f.lane_copy_tpl(t, k, n, ln, min_out, deadline.map(|d| d.1), &mut tbuf) {
                    Some(c) => Ok(vec![c]),
                    None => f.lane_copy(&cfgb, k, n, ln).map(|c| vec![c]),
                },
                (Some(f), Some(k), None) => f.lane_copy(&cfgb, k, n, ln).map(|c| vec![c]),
                _ => build_lane_copies(&sh.key, &cfgb, &launch, n, std::slice::from_ref(ln)),
            };
            match one {
                Ok(mut v) => {
                    let cp = v.remove(0);
                    if t_built == 0 { t_built = now_ns(); }
                    if sh.live { fire_copy(sh, id, &cp, t_dec0, &mut sends, &mut t_first_write, &mut h.buf); }
                    copies.push(cp);
                }
                Err(e) => { r = Err(e); break; }
            }
        }
        r
    } else {
        let pp: Vec<(Option<(Pk, u64)>, &[Pk])> = fan.iter().map(|l| (sh.routes.paths[l.pi].tip(0), sh.routes.paths[l.pi].tip_accounts())).collect();
        let groups: Vec<(Option<(Pk, u64)>, Vec<usize>)> = tip_groups(&pp).into_iter().map(|(t, v)| (t, v.into_iter().map(|j| fan[j].pi).collect())).collect();
        match build_copies(&sh.key, &cfgb, &launch, bh, lease.map(|(_, k, v)| (k, v)), &groups) {
            Ok(v) => {
                t_built = now_ns();
                if sh.live { for cp in &v { fire_copy(sh, id, cp, t_dec0, &mut sends, &mut t_first_write, &mut h.buf); } }
                copies = v;
                Ok(())
            }
            Err(e) => Err(e),
        }
    };
    if let Err(e) = built {
        if copies.is_empty() { release(sh); let mut x = ej(); x["err"] = serde_json::json!(e); skip(sh, "build_failed", x); return; }
        say(format!("BUILD of a later lane failed after {} copies went out: {e}", copies.len()));
    }
    if sh.live {
        let mut sw = sh.sig_watch.lock().unwrap();
        for cp in &copies { sw.insert(cp.sig, id); }
    }
    let t_sent = now_ns();
    if entry_rec.is_none() { entry_rec = entry_score(sh, a, &launch, &who, win.as_ref()).map(|e| e.1); }

    // ---- the record (after the sends)
    let us = |a: u64, b: u64| a.saturating_sub(b) / 1000;
    let copy_meta: Vec<CopyMeta> = copies.iter().enumerate().map(|(i, cp)| CopyMeta {
        sig: cp.sig, raw: cp.raw.clone(), path: cp.paths.iter().map(|&pi| sh.routes.paths[pi].name.clone()).collect::<Vec<_>>().join("+"),
        tip: cp.tip, prio: lane_info.get(i).map_or(sh.a.cu_limit as u64 * sh.a.cu_price_micro / 1_000_000, |x| x.1) }).collect();
    let r = serde_json::json!({ "id": id, "mint": b58(&launch.mint), "creator": b58(&launch.creator), "ev_creator": b58(&who.ev), "match_key": b58(&who.mkey),
        "signer": a.tx.keys.first().map(b58), "create_sig": a.tx.sig_b58(), "holder_reward": launch.is_holder_reward, "entry": entry_rec,
        "slot": a.slot, "kind": kind, "feed": sh.feed_names.get(a.feed as usize), "dev_buy": launch.dev_buy_lamports, "mayhem": launch.is_mayhem, "cashback": launch.is_cashback,
        "route": meta, "recipe": sh.a.recipe, "first_or_revert": first, "state_exact": exact, "state_why": why_inexact, "legs": legs.len(), "bundle_seen": bundle_seen, "bundle_hint": win.as_ref().and_then(|w| w.hint), "bundle_end": win.as_ref().map(|w| w.end), "bundle_waited_us": win.as_ref().map(|w| w.waited_us),
        "bundle_pulled": win.as_ref().map(|w| w.pulled), "q_at_dequeue": h.q_at_dequeue, "prep_us": us(t_b0, t_state),
        "bundle_first_us": bundle_us, "build_paths": build_paths, "vq_state": vq, "spend": c.size, "expected_tokens": expected, "min_out": min_out, "deadline_slot": deadline.map(|d| d.1),
        "nonce": lease.map(|l| b58(&l.1)),
        "copies": copy_meta.iter().map(|m| serde_json::json!({ "sig": bs58::encode(m.sig).into_string(), "lane": m.path, "tip": m.tip, "prio": m.prio, "bytes": m.raw.len() })).collect::<Vec<_>>(),
        "sends": sends, "t_rx": a.t_rx, "t_decoded": a.t_decoded, "t_hot": t_hot, "t_decide": t_dec0, "t_built": t_built, "t_sent": t_sent,
        "feed_to_hot_us": us(t_hot, a.t_rx), "hot_to_decide_us": us(t_dec0, t_hot), "bundle_window_us": us(t_state, t_dec0), "build_sign_us": us(t_built, t_b0),
        "rx_to_built_us": us(t_built, a.t_rx), "rx_to_first_write_us": (t_first_write > 0).then(|| us(t_first_write, a.t_rx)), "rx_to_sent_us": us(t_sent, a.t_rx),
        "queue_len": h.rx.len(), "gmgn": gmgn(&launch.mint) });
    if !sh.live {
        sh.rec.ev("buy_shadow", r);
        say(format!("SHADOW BUY #{id} {} creator {} slot {} {} {} | {} copies | feed->hot {} us, window {} us, build+sign {} us, rx->signed {} us", b58(&launch.mint), b58(&launch.creator), a.slot,
            meta.route, meta.client, copies.len(), us(t_hot, a.t_rx), us(t_state, t_dec0), us(t_built, t_b0), us(t_built, a.t_rx)));
        track_mint(sh, launch.mint);
        let sh2 = sh.clone();
        let (create_sig, create_slot) = (a.tx.sig, a.slot);
        sh.handle.spawn(async move { shadow_landscape(sh2, id, launch, create_sig, create_slot).await });
        return;
    }
    track_mint(sh, launch.mint);
    sh.touched.lock().unwrap().push(launch.clone());
    say(format!("BUY SENT #{id} {} creator {} slot {} {} {} {} copies | rx->first write {} us | {}", b58(&launch.mint), b58(&launch.creator), a.slot, meta.route, meta.client,
        copies.len(), if t_first_write > 0 { us(t_first_write, a.t_rx) } else { us(t_sent, a.t_rx) }, gmgn(&launch.mint)));
    sh.rec.ev("buy_sent", r);
    sh.open_tasks.fetch_add(1, Ordering::SeqCst);
    let sh2 = sh.clone();
    let guard_task = TaskGuard(sh.clone());
    let t = Trade { id, launch, create_sig: a.tx.sig, create_slot: a.slot, create_t_rx: a.t_rx, t_decide: t_dec0, sigs: copies.iter().map(|c| c.sig).collect(),
        deadline: deadline.map(|d| d.1), worst, expected, min_out, copies: copy_meta, meta };
    sh.handle.spawn(async move {
        let _g = guard_task;
        let id = t.id;
        if let Err(e) = manage(sh2, t).await { say(format!("TRADE #{id} task error: {e:#}")); }
    });
}

/// the APEX-3 entry score of a watched create (None: no model). -> (passes the threshold, record). Inputs (entry.rs doc):
/// dev = the create tx's first buy leg, bundle = the window's legs after the create's + their fee payers, u = PoH position
/// or the model's default, history = the CreateEvent creator's resolved launches in the model file.
fn entry_score(sh: &Shared, a: &feeds::Arrival, launch: &Launch, who: &Who, win: Option<&Window>) -> Option<(bool, serde_json::Value)> {
    let m = sh.entry.as_ref()?;
    let t0 = now_ns();
    let (create_legs, dev_src): (Vec<(bool, u64, u64)>, &str) = match entry::entry_legs(&a.tx, &launch.mint) {
        Some(entry::ELegs::Buys(v)) => (v.into_iter().map(|x| x.0).collect(), "legs"),
        _ if launch.dev_buy_lamports == 0 => (Vec::new(), "no_buy"),
        _ => (Vec::new(), "dev_buy_est"),
    };
    let (bundle, busers, bund_src, unseen): (Vec<(bool, u64, u64)>, usize, &str, usize) = match win {
        Some(w) if w.end != "no_wait" => {
            let mut u: Vec<Pk> = Vec::new();
            for (_, p) in &w.eb { if !u.contains(p) { u.push(*p); } }
            (w.eb.iter().map(|x| x.0).collect(), u.len(), w.end, w.eb_unseen)
        }
        Some(_) => (Vec::new(), 0, "no_wait", 0),
        None => (Vec::new(), 0, "before_window", 0),
    };
    let (mut dev, bund) = entry::leg_sols(&create_legs, &bundle);
    if dev_src == "dev_buy_est" { dev = net_of_fee(launch.dev_buy_lamports); }
    let (u, u_src) = match entry::u_from_poh(a.poh.as_ref()) { Some(u) => (u, "poh"), None => (m.u_default, "default") };
    let o = entry::Obs { dev_sol: dev as f64 / 1e9, bund_sol: bund as f64 / 1e9, bund_users: busers as f64, u, bt: entry::now_bt() };
    let sc = m.score(&who.ev, &o);
    let us = now_ns().saturating_sub(t0) / 1000;
    Some((sc.pass, serde_json::json!({ "score": sc.score, "thr": sc.thr, "pass": sc.pass, "mode": sh.a.entry_filter, "x": sc.x.to_vec(),
        "dev_src": dev_src, "bund_src": bund_src, "bund_unseen": unseen, "u_src": u_src, "bt": o.bt, "us": us })))
}

/// send one signed copy on its path(s): async kinds spawned, the fast HTTP / UDP written from this (hot) thread
fn fire_copy(sh: &Arc<Shared>, id: u64, cp: &Copy, t_dec0: u64, sends: &mut Vec<serde_json::Value>, t_first: &mut u64, buf: &mut Vec<u8>) {
    for &pi in &cp.paths {
        let p = &sh.routes.paths[pi];
        match &sh.fast[pi] {
            FastKind::Slow => {
                spawn_send(sh, id, p.clone(), cp.raw.clone(), t_dec0);
                let t = now_ns(); if *t_first == 0 { *t_first = t; }
                sends.push(serde_json::json!({ "path": p.name, "how": "async", "t_off_us": (t - t_dec0) / 1000 }));
            }
            FastKind::Http { conn, json } => {
                if !p.fast_budget() { sends.push(serde_json::json!({ "path": p.name, "how": "http", "skipped": "rate" })); continue; }
                let mut body = Vec::with_capacity(2400);
                if *json { fast::json_send_body(&cp.raw, &mut body); conn.frame(&body, buf); } else { conn.frame(&cp.raw, buf); }
                match conn.write_req(buf, (id << 8) | pi as u64) {
                    Ok((w0, w1)) => { let t = now_ns(); if *t_first == 0 { *t_first = t; } sends.push(serde_json::json!({ "path": p.name, "how": "http", "t_off_us": (t - t_dec0) / 1000, "write_us": (w1 - w0) / 1000 })) }
                    Err(e) => { spawn_send(sh, id, p.clone(), cp.raw.clone(), t_dec0); sends.push(serde_json::json!({ "path": p.name, "how": "http->async", "err": e })); }
                }
            }
            FastKind::Udp => {
                if !p.fast_budget() { sends.push(serde_json::json!({ "path": p.name, "how": "udp", "skipped": "rate" })); continue; }
                let mut ub = Vec::with_capacity(1300);
                let res = p.fast_udp(&cp.raw, &mut ub, p.udp_copies());
                let t = now_ns(); if *t_first == 0 { *t_first = t; }
                sends.push(serde_json::json!({ "path": p.name, "how": "udp", "t_off_us": (t - t_dec0) / 1000, "err": res.and_then(|x| x.err()).map(|e| e.to_string()) }));
            }
        }
    }
}

/// one copy (lane) of a buy, for the attempt record
#[derive(Clone)]
struct CopyMeta { sig: [u8; 64], raw: Vec<u8>, path: String, tip: u64, prio: u64 }

/// counts an open trade task; dropped (also on a panic) = done, so the stop never waits forever
struct TaskGuard(Arc<Shared>);
impl Drop for TaskGuard { fn drop(&mut self) { self.0.open_tasks.fetch_sub(1, Ordering::SeqCst); } }

fn lane_text_of(a: &Args) -> String { if a.recipe == "lanes" { a.lanes.clone() } else { a.routes.clone() } }

/// a dip engine (any snipe_engine*) running on this machine
fn dip_engine_running() -> bool {
    let Ok(rd) = std::fs::read_dir("/proc") else { return false };
    let me = std::process::id().to_string();
    rd.filter_map(|e| e.ok()).filter(|e| e.file_name().to_string_lossy().chars().all(|c| c.is_ascii_digit()) && e.file_name().to_string_lossy() != me)
        .any(|e| std::fs::read(e.path().join("cmdline")).map(|c| String::from_utf8_lossy(&c).split('\0').next().unwrap_or("").contains("snipe_engine")).unwrap_or(false))
}

fn spawn_send(sh: &Arc<Shared>, id: u64, p: Arc<send::Path>, raw: Vec<u8>, t_dec0: u64) {
    let sh2 = sh.clone();
    sh.handle.spawn(async move {
        let t_start = now_ns();
        let t = Instant::now();
        let r = p.send(&raw, send::Prio { band: 0, crowd: 0, ev: 0 }, None).await;
        let ms = t.elapsed().as_secs_f64() * 1e3;
        let (ok, status, reply) = match &r { Ok(x) => (true, x.status, x.reply.chars().take(160).collect::<String>()), Err(e) => (false, e.status, e.msg.chars().take(160).collect::<String>()) };
        sh2.rec.ev("send_ack", serde_json::json!({ "trade": id, "path": p.name, "t_off_us": (t_start.saturating_sub(t_dec0)) / 1000, "ack_ms": ms, "ok": ok, "status": status, "reply": reply }));
    });
}

fn track_mint(sh: &Arc<Shared>, m: Pk) { sh.mint_recs.lock().unwrap().entry(m).or_default(); }
fn untrack_mint(sh: &Arc<Shared>, m: &Pk) -> Vec<ExecRec> { sh.curve.lock().unwrap().remove(m); sh.mint_recs.lock().unwrap().remove(m).unwrap_or_default() }

// ==================================================================================================================
// one trade: landing -> hold -> sell -> P&L + position
// ==================================================================================================================

struct Trade { id: u64, launch: Launch, create_sig: [u8; 64], create_slot: u64, create_t_rx: u64, t_decide: u64, sigs: Vec<[u8; 64]>, deadline: Option<u64>, worst: u64,
    expected: u64, min_out: u64, copies: Vec<CopyMeta>, meta: route::Meta }

/// landed: (sig, slot, ok, via, index if known, our TradeEvent (tokens, sol, vsol, vtok))
type Land = ([u8; 64], u64, bool, &'static str, Option<u64>, Option<(u64, u64, u64, u64)>);

/// wait for any of `sigs` to land: the executed feed first, getSignatureStatuses every 200 ms; gives up `until` says
async fn wait_land(sh: &Arc<Shared>, sigs: &[[u8; 64]], until: impl Fn(&Shared, Duration) -> bool) -> Option<Land> {
    let t0 = Instant::now();
    let mut last_poll = Instant::now() - Duration::from_secs(1);
    loop {
        {
            let g = sh.sightings.lock().unwrap();
            for s in sigs {
                if let Some(Sighting { exec: Some((slot, idx, ok, _, te)), .. }) = g.get(s) { return Some((*s, *slot, *ok, "feed", *idx, *te)); }
            }
        }
        if last_poll.elapsed() >= Duration::from_millis(200) {
            last_poll = Instant::now();
            if let Ok(v) = sh.rpc.statuses(sigs).await {
                if let Some((i, (slot, ok))) = v.iter().enumerate().find_map(|(i, x)| x.map(|y| (i, y))) {
                    // give the feed 150 ms more for the index + our TradeEvent
                    tokio::time::sleep(Duration::from_millis(150)).await;
                    let g = sh.sightings.lock().unwrap();
                    if let Some(Sighting { exec: Some((s2, idx, ok2, _, te)), .. }) = g.get(&sigs[i]) { return Some((sigs[i], *s2, *ok2, "feed", *idx, *te)); }
                    return Some((sigs[i], slot, ok, "rpc", None, None));
                }
            }
        }
        if until(sh, t0.elapsed()) { return None; }
        tokio::time::sleep(Duration::from_millis(25)).await;
    }
}

async fn manage(sh: Arc<Shared>, t: Trade) -> Result<()> {
    let m = t.launch.mint;
    let ms = |a: u64, b: u64| (a as f64 - b as f64) / 1e6;
    // ---- 1. the buy's landing: with the slot guard, nothing can succeed past the deadline (+4 slots of margin)
    let dl = t.deadline;
    let land = wait_land(&sh, &t.sigs, |s, el| el > Duration::from_millis(1500) && match dl {
        Some(d) => s.max_slot.load(Ordering::Relaxed) > d + 4,
        None => el > Duration::from_secs(20),
    } || el > Duration::from_secs(30)).await;
    let t_known = Instant::now();
    let shred = { let g = sh.sightings.lock().unwrap(); t.sigs.iter().find_map(|s| g.get(s).and_then(|x| x.shred)) };
    let Some((sig, slot, ok, via, idx, te)) = land else {
        sh.unlanded.lock().unwrap().push((t.id, t.sigs.clone()));
        sh.rec.ev("buy_failed", serde_json::json!({ "id": t.id, "mint": b58(&m), "why": "not_landed", "deadline_slot": dl, "seen_in_shreds": shred.is_some(), "gmgn": gmgn(&m) }));
        say(format!("BUY #{} NOT LANDED {} (deadline slot {:?}){}", t.id, b58(&m), dl, if shred.is_some() { " — but seen in shreds (dropped / failed?)" } else { "" }));
        let (pnl, known) = finish(&sh, &t, 0, Vec::new()).await;
        attempt(&sh, &t, None, None, pnl, known);
        return Ok(());
    };
    let sig58 = bs58::encode(sig).into_string();
    let mut base = serde_json::json!({ "id": t.id, "mint": b58(&m), "sig": sig58, "slot": slot, "via": via, "index": idx, "create_slot": t.create_slot,
        "slot_delta": slot as i64 - t.create_slot as i64, "create_to_shred_ms": shred.map(|s| ms(s.0, t.create_t_rx)), "decide_to_shred_ms": shred.map(|s| ms(s.0, t.t_decide)),
        "shred_slot": shred.map(|s| s.1), "shred_feed": shred.and_then(|s| sh.feed_names.get(s.2 as usize).cloned()), "gmgn": gmgn(&m) });
    if !ok {
        let (err, line) = tx_error(&sh.rpc, &sig58).await;
        base["err"] = err.clone(); base["err_line"] = line.clone().into(); base["why"] = "failed_on_chain".into();
        sh.rec.ev("buy_failed", base);
        say(format!("BUY #{} REVERTED on chain {} slot {} (create +{}): {}", t.id, b58(&m), slot, slot as i64 - t.create_slot as i64, line.unwrap_or_default()));
        {
            let sh2 = sh.clone();
            let (id, cs, cslot) = (t.id, t.create_sig, t.create_slot);
            tokio::spawn(async move { block_position(sh2, id, m, cs, cslot, sig, slot).await });
        }
        let (pnl, known) = finish(&sh, &t, 0, vec![sig]).await;
        attempt(&sh, &t, Some((sig, slot, false, idx)), Some(err), pnl, known);
        return Ok(());
    }
    // tokens: our TradeEvent (executed feed) or the token account (RPC, during the hold: never between the sell decision and the send)
    let ata = snipe_build::assoc_user(&sh.user, &m);
    let mut tokens = te.map(|x| x.0);
    if tokens.is_none() {
        for _ in 0..20 {
            if let Some(a) = token_balance(&sh.rpc, &ata, "processed").await.ok().flatten().filter(|a| *a > 0) { tokens = Some(a); break; }
            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    }
    if let Some((_, _, vs, vt)) = te { sh.curve.lock().unwrap().entry(m).or_insert((vs, vt)); }
    base["tokens"] = tokens.into(); base["buy_sol"] = te.map(|x| x.1).into(); base["expected_tokens"] = t.expected.into(); base["min_out"] = t.min_out.into();
    base["fill_vs_expected"] = tokens.map(|k| t.expected as f64 / k.max(1) as f64).into();
    sh.rec.ev("buy_landed", base.clone());
    say(format!("BUY #{} LANDED {} slot {} (create +{}) idx {:?} | create->our shred {} ms | tokens {:?} | price x{:.3} expected", t.id, b58(&m), slot,
        slot as i64 - t.create_slot as i64, idx, shred.map(|s| format!("{:.1}", ms(s.0, t.create_t_rx))).unwrap_or("-".into()), tokens,
        tokens.map(|k| t.expected as f64 / k.max(1) as f64).unwrap_or(f64::NAN)));

    // ---- 2. hold from our confirmed fill
    let hold_end = t_known + Duration::from_millis(sh.caps.hold_ms);
    tokio::time::sleep_until(tokio::time::Instant::from_std(hold_end)).await;

    // ---- 3. sell everything (no RPC between the decision and the send: cached blockhash, known amount)
    let amount = match tokens { Some(a) => a, None => token_balance(&sh.rpc, &ata, "confirmed").await.ok().flatten().unwrap_or(0) };
    let mut all = vec![sig];
    if amount > 0 {
        let (sold, sigs) = sell_all(&sh, t.id, &t.launch, amount, sh.caps.sell_guard, Duration::from_secs(sh.a.sell_deadline_s)).await;
        all.extend(sigs);
        if !sold { say(format!("SELL #{} UNSOLD {} after {} s: the end check retries", t.id, b58(&m), sh.a.sell_deadline_s)); }
    } else {
        say(format!("TRADE #{}: no token amount known for {}: the end check reads the account", t.id, b58(&m)));
    }
    // ---- 4. position (executed feed, then getBlock) + P&L
    tokio::time::sleep(Duration::from_millis(300)).await;
    let recs = untrack_mint(&sh, &m);
    let pos = position(&recs, Some(&t.create_sig), &sig, &sh.user);
    let riv = rivals(&recs, Some(&t.create_sig), &sig, &sh.user);
    let ahead = ahead_list(&recs, &t.create_sig, &sig, &sh.user);
    sh.rec.ev("position", serde_json::json!({ "id": t.id, "mint": b58(&m), "src": "feed", "pos": pos, "rivals": riv, "ahead": ahead, "recs": recs.len() }));
    if let Some(p) = &pos {
        say(format!("POSITION #{} slot {:+} idx {:?} | buyers ahead {} ({} txs, {:.3} SOL) | dev buys in create {} | rank {}", t.id, p.slot_delta, p.idx_delta,
            p.buyers_ahead, p.buy_txs_ahead, p.sol_ahead as f64 / 1e9, p.dev_buys_in_create, p.buy_rank));
    }
    {
        let sh2 = sh.clone();
        let (id, cs, cslot) = (t.id, t.create_sig, t.create_slot);
        tokio::spawn(async move { block_position(sh2, id, m, cs, cslot, sig, slot).await });
    }
    let (pnl, known) = finish(&sh, &t, 1, all).await;
    attempt(&sh, &t, Some((sig, slot, true, idx)), None, pnl, known);
    Ok(())
}

/// one record per buy attempt: every copy (lane, tip, priority) and its outcome — landed / reverted (error code, the
/// instruction it failed in) / not_landed (another copy took the nonce) / not_seen — the client, and the trade's cost
fn attempt(sh: &Arc<Shared>, t: &Trade, landed: Option<([u8; 64], u64, bool, Option<u64>)>, err: Option<serde_json::Value>, pnl: i64, known: bool) {
    let g = sh.sightings.lock().unwrap();
    let copies: Vec<serde_json::Value> = t.copies.iter().map(|c| {
        let shred = g.get(&c.sig).and_then(|x| x.shred).map(|s| (s.0.saturating_sub(t.create_t_rx)) as f64 / 1e6);
        let (outcome, code, role) = match &landed {
            Some((s, _, true, _)) if *s == c.sig => ("landed", None, None),
            Some((s, _, false, _)) if *s == c.sig => {
                let (ixi, code) = err.as_ref().map(err_code).unwrap_or((None, None));
                ("reverted", code, ixi.map(|i| ix_role(&c.raw, i)))
            }
            Some(_) => ("not_landed", None, None),
            None => ("not_seen", None, None),
        };
        serde_json::json!({ "lane": c.path, "tip": c.tip, "prio": c.prio, "sig": bs58::encode(c.sig).into_string(), "outcome": outcome, "err_code": code, "err_ix": role,
            "create_to_shred_ms": shred })
    }).collect();
    let (outcome, slot) = match &landed { Some((_, s, true, _)) => ("landed", Some(*s)), Some((_, s, false, _)) => ("reverted", Some(*s)), None => ("not_seen", None) };
    sh.rec.ev("attempt", serde_json::json!({ "id": t.id, "mint": b58(&t.launch.mint), "client": t.meta.client, "class": t.meta.class, "route": t.meta.route, "leader": t.meta.leader,
        "outcome": outcome, "slot": slot, "slot_delta": slot.map(|s| s as i64 - t.create_slot as i64), "index": landed.and_then(|x| x.3), "err": err, "copies": copies,
        "cost_lamports": -pnl, "cost_known": known, "pnl": pnl, "gmgn": gmgn(&t.launch.mint) }));
}

/// the trade's P&L from the actual balance changes of every landed tx of it, then the ledger
async fn finish(sh: &Arc<Shared>, t: &Trade, landed: u32, sigs: Vec<[u8; 64]>) -> (i64, bool) {
    let mut pnl: i64 = 0;
    let mut known = true;
    let mut parts = Vec::new();
    for s in &sigs {
        match tx_delta(&sh.rpc, &bs58::encode(s).into_string(), &sh.user).await {
            Some(d) => { pnl += d; parts.push(serde_json::json!({ "sig": bs58::encode(s).into_string(), "delta": d })); }
            None => { known = false; parts.push(serde_json::json!({ "sig": bs58::encode(s).into_string(), "delta": null })); }
        }
    }
    let charged = if known { pnl } else { pnl.min(-(t.worst as i64)) };
    {
        let mut l = sh.ledger.lock().unwrap();
        l.open = l.open.saturating_sub(1);
        l.open_worst = l.open_worst.saturating_sub(t.worst);
        l.realized += charged;
    }
    untrack_mint(sh, &t.launch.mint);
    sh.sig_watch.lock().unwrap().retain(|_, v| *v != t.id);
    sh.rec.ev("realized", serde_json::json!({ "id": t.id, "mint": b58(&t.launch.mint), "pnl": pnl, "pnl_known": known, "charged": charged, "landed": landed, "txs": parts, "gmgn": gmgn(&t.launch.mint) }));
    if !sigs.is_empty() { say(format!("REALIZED #{} {} SOL{} {}", t.id, sol(pnl), if known { "" } else { " (some txs unread: worst case charged)" }, gmgn(&t.launch.mint))); }
    (pnl, known)
}

/// sell `amount` tokens of `l`: first try on the sell path, retries every --sell-retry-ms also on the fallback path; the
/// guard for the first 3 tries, then min 0. Returns (sold, every sig that landed)
async fn sell_all(sh: &Arc<Shared>, id: u64, l: &Launch, amount: u64, guard: f64, deadline: Duration) -> (bool, Vec<[u8; 64]>) {
    let t0 = Instant::now();
    let mut sigs: Vec<[u8; 64]> = Vec::new();
    let mut landed: Vec<[u8; 64]> = Vec::new();
    let mut attempt = 0u32;
    let mut unguarded = guard <= 0.0;
    while t0.elapsed() < deadline {
        attempt += 1;
        if attempt > 3 { unguarded = true; }
        let (vs, vt) = sh.curve.lock().unwrap().get(&l.mint).copied().unwrap_or((0, 0));
        let exp = sell_expected(vs, vt, amount);
        let min = if unguarded { 0 } else { sell_min_out(exp, guard) };
        let mut fan: Vec<Arc<send::Path>> = vec![sh.sell_path.clone()];
        if attempt > 1 { if let Some(f) = &sh.sell_fb { fan.push(f.clone()); } }
        let pp: Vec<(Option<(Pk, u64)>, &[Pk])> = fan.iter().map(|p| (p.tip(0), p.tip_accounts())).collect();
        let tips: Vec<(Pk, u64)> = tip_groups(&pp).into_iter().filter_map(|g| g.0).collect();
        // the cached blockhash (refresh inline only when it is stale: never on a fresh decision)
        let bh = match sh.blockhash(Duration::from_secs(25)) { Some(h) => h, None => match sh.rpc.latest_blockhash().await { Ok((h, _)) => h, Err(_) => { tokio::time::sleep(Duration::from_millis(300)).await; continue; } } };
        let ixs = sell_ixs(sh.user, l, amount, min, sh.a.sell_cu_limit, sh.a.sell_cu_price_micro, &tips);
        let raw = match build::compile_v0(sh.user, &ixs, bh, &[], &[]) { Ok(m) => build::sign(&m, &sh.key), Err(e) => { say(format!("SELL #{id} build failed: {e}")); return (false, landed); } };
        let sig = sig_of(&raw);
        sh.sig_watch.lock().unwrap().insert(sig, id);
        sigs.push(sig);
        let t_send = now_ns();
        for p in &fan { spawn_send(sh, id, p.clone(), raw.clone(), t_send); }
        sh.rec.ev("sell_sent", serde_json::json!({ "id": id, "mint": b58(&l.mint), "attempt": attempt, "sig": bs58::encode(sig).into_string(), "amount": amount,
            "min_sol": min, "expected_sol": exp, "paths": fan.iter().map(|p| p.name.clone()).collect::<Vec<_>>(), "tips": tips.iter().map(|t| t.1).sum::<u64>() }));
        let wait = Duration::from_millis(sh.a.sell_retry_ms);
        let r = wait_land(sh, &sigs, |_, el| el >= wait).await;
        if let Some((s, slot, ok, via, idx, te)) = r {
            if !landed.contains(&s) { landed.push(s); }
            let s58 = bs58::encode(s).into_string();
            if ok {
                sh.rec.ev("sell_landed", serde_json::json!({ "id": id, "mint": b58(&l.mint), "sig": s58, "slot": slot, "via": via, "index": idx, "sol": te.map(|x| x.1), "attempt": attempt,
                    "hold_to_land_ms": t0.elapsed().as_secs_f64() * 1e3 }));
                say(format!("SELL #{id} LANDED {} slot {slot} after {} tries ({:.0} ms)", b58(&l.mint), attempt, t0.elapsed().as_secs_f64() * 1e3));
                return (true, landed);
            }
            let (err, line) = tx_error(&sh.rpc, &s58).await;
            sh.rec.ev("sell_failed", serde_json::json!({ "id": id, "mint": b58(&l.mint), "sig": s58, "slot": slot, "err": err, "err_line": line, "attempt": attempt }));
            say(format!("SELL #{id} failed on chain (try {attempt}): {} — next try unguarded", line.unwrap_or_default()));
            unguarded = true;
            sigs.retain(|x| *x != s);
            // tokens left? (a failed sell keeps them; an earlier one may have landed meanwhile: the status poll sees it)
        }
    }
    (false, landed)
}

/// getTransaction: our lamport change in it (we are the fee payer, account 0)
async fn tx_delta(rpc: &rpc::Rpc, sig: &str, user: &Pk) -> Option<i64> {
    for k in 0..30 {
        if k > 0 { tokio::time::sleep(Duration::from_secs(1)).await; }
        let Ok(v) = rpc.call("getTransaction", serde_json::json!([sig, { "encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed" }])).await else { continue };
        if v.is_null() { continue; }
        let keys = v["transaction"]["message"]["accountKeys"].as_array()?;
        let i = keys.iter().position(|k| k.as_str() == Some(&b58(user)))?;
        let pre = v["meta"]["preBalances"][i].as_i64()?;
        let post = v["meta"]["postBalances"][i].as_i64()?;
        return Some(post - pre);
    }
    None
}

/// a landed-failed tx's error and its most telling log line
async fn tx_error(rpc: &rpc::Rpc, sig: &str) -> (serde_json::Value, Option<String>) {
    for k in 0..10 {
        if k > 0 { tokio::time::sleep(Duration::from_millis(700)).await; }
        let Ok(v) = rpc.call("getTransaction", serde_json::json!([sig, { "encoding": "json", "maxSupportedTransactionVersion": 0, "commitment": "confirmed" }])).await else { continue };
        if v.is_null() { continue; }
        let logs: Vec<String> = v["meta"]["logMessages"].as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default();
        let line = logs.iter().rev().find(|l| l.contains("Error") || l.contains("failed") || l.contains("custom program error")).cloned();
        return (v["meta"]["err"].clone(), line);
    }
    (serde_json::Value::Null, None)
}

/// a token account's amount: Ok(None) = no such account
async fn token_balance(rpc: &rpc::Rpc, ata: &Pk, commitment: &str) -> Result<Option<u64>> {
    match rpc.call("getTokenAccountBalance", serde_json::json!([b58(ata), { "commitment": commitment }])).await {
        Ok(v) => Ok(v["value"]["amount"].as_str().and_then(|s| s.parse().ok())),
        Err(e) => { let s = format!("{e:#}"); if s.contains("could not find account") || s.contains("Invalid param") || s.contains("-32602") { Ok(None) } else { Err(e) } }
    }
}

/// the buys ahead of us, each (slot delta, idx delta vs the create, buyer, curve SOL): the report's detail
fn ahead_list(recs: &[ExecRec], create_sig: &[u8; 64], our: &[u8; 64], us: &Pk) -> serde_json::Value {
    let mut v: Vec<&ExecRec> = recs.iter().collect();
    v.sort_by_key(|r| (r.slot, r.index));
    let Some(c) = v.iter().position(|r| r.is_create || r.sig == *create_sig) else { return serde_json::Value::Null };
    let end = v.iter().position(|r| r.sig == *our).unwrap_or(v.len().min(c + 40));
    let cr = v[c];
    v[c..end.max(c)].iter().filter(|r| r.ok && !r.buys.is_empty()).take(30).map(|r| serde_json::json!({
        "slot_d": r.slot as i64 - cr.slot as i64, "idx_d": (r.slot == cr.slot).then(|| r.index as i64 - cr.index as i64), "create_tx": r.sig == cr.sig,
        "buyers": r.buys.iter().filter(|b| b.0 != *us).map(|b| b58(&b.0)).collect::<Vec<_>>(), "sol": r.buys.iter().map(|b| b.1).sum::<u64>() })).collect::<Vec<_>>().into()
}

/// shadow: the create's slot + the real buyers after it (the executed feed, then getBlock) — where a buy would have had to land
async fn shadow_landscape(sh: Arc<Shared>, id: u64, l: Launch, create_sig: [u8; 64], create_slot: u64) {
    tokio::time::sleep(Duration::from_secs(6)).await;
    let recs = untrack_mint(&sh, &l.mint);
    let mut v: Vec<&ExecRec> = recs.iter().collect();
    v.sort_by_key(|r| (r.slot, r.index));
    let c = v.iter().position(|r| r.is_create || r.sig == create_sig);
    let ahead = ahead_list(&recs, &create_sig, &[0u8; 64], &sh.user);
    let (cs, ci) = c.map(|i| (v[i].slot, v[i].index)).unwrap_or((create_slot, 0));
    let same_slot_buys = v.iter().filter(|r| r.ok && r.slot == cs && c.is_some_and(|i| r.index > v[i].index) && !r.buys.is_empty()).count();
    let next_slot_buys = v.iter().filter(|r| r.ok && r.slot == cs + 1 && !r.buys.is_empty()).count();
    sh.rec.ev("shadow_landscape", serde_json::json!({ "id": id, "mint": b58(&l.mint), "create_found": c.is_some(), "create_slot": cs, "create_idx": ci,
        "dev_buys_in_create": c.map(|i| v[i].buys.len()), "buy_txs_same_slot_after_create": same_slot_buys, "buy_txs_next_slot": next_slot_buys, "first_buys": ahead, "gmgn": gmgn(&l.mint) }));
    say(format!("SHADOW #{id} {}: create slot {cs} idx {ci} | buy txs after it in the create slot {same_slot_buys}, next slot {next_slot_buys}", b58(&l.mint)));
}

/// getBlock (transactionDetails accounts) over create slot ..= land slot: our index, the create's, and the txs that
/// raised another wallet's balance of the mint between them (buyers ahead) — the check of the feed's numbers
async fn block_position(sh: Arc<Shared>, id: u64, mint: Pk, create_sig: [u8; 64], create_slot: u64, our: [u8; 64], land_slot: u64) {
    if land_slot < create_slot || land_slot - create_slot > 3 {
        sh.rec.ev("position", serde_json::json!({ "id": id, "mint": b58(&mint), "src": "block", "skipped": "slot span" }));
        return;
    }
    let m58 = b58(&mint);
    let mut recs: Vec<ExecRec> = Vec::new();
    for s in create_slot..=land_slot {
        let mut got = None;
        for k in 0..25 {
            if k > 0 { tokio::time::sleep(Duration::from_secs(1)).await; }
            if let Ok(v) = sh.rpc.call("getBlock", serde_json::json!([s, { "encoding": "json", "transactionDetails": "accounts", "maxSupportedTransactionVersion": 0, "rewards": false, "commitment": "confirmed" }])).await {
                if !v.is_null() { got = Some(v); break; }
            }
        }
        let Some(b) = got else { sh.rec.ev("position", serde_json::json!({ "id": id, "mint": m58, "src": "block", "skipped": format!("getBlock {s} unavailable") })); return; };
        for (i, t) in b["transactions"].as_array().into_iter().flatten().enumerate() {
            let keys: Vec<&str> = t["transaction"]["accountKeys"].as_array().into_iter().flatten().filter_map(|k| k["pubkey"].as_str()).collect();
            if !keys.contains(&m58.as_str()) { continue; }
            let sig: [u8; 64] = t["transaction"]["signatures"][0].as_str().and_then(|x| bs58::decode(x).into_vec().ok()).and_then(|v| v.try_into().ok()).unwrap_or([0u8; 64]);
            let ok = t["meta"]["err"].is_null();
            let bal = |side: &str| -> HashMap<String, u64> {
                t["meta"][side].as_array().into_iter().flatten().filter(|x| x["mint"].as_str() == Some(m58.as_str()))
                    .filter_map(|x| Some((x["owner"].as_str()?.to_string(), x["uiTokenAmount"]["amount"].as_str()?.parse().ok()?))).collect()
            };
            let (pre, post) = (bal("preTokenBalances"), bal("postTokenBalances"));
            let curve_owner = b58(&snipe_build::bonding_curve(&mint));
            let mut buys = Vec::new();
            let mut sells = 0;
            for (o, a) in &post {
                if *o == curve_owner { continue; }
                let p0 = pre.get(o).copied().unwrap_or(0);
                if *a > p0 { buys.push((arbx::tx::pk(o), 0u64, a - p0)); } else if *a < p0 { sells += 1; }
            }
            recs.push(ExecRec { slot: s, index: i as u64, sig, ok, is_create: sig == create_sig, buys, sells });
        }
    }
    // position() counts landed txs only: a reverted buy of ours still has its place (it is in `recs` with ok false)
    let pos = position(&recs, Some(&create_sig), &our, &sh.user);
    let riv = rivals(&recs, Some(&create_sig), &our, &sh.user);
    sh.rec.ev("position", serde_json::json!({ "id": id, "mint": m58, "src": "block", "pos": pos, "rivals": riv, "ahead": ahead_list(&recs, &create_sig, &our, &sh.user) }));
}

// ==================================================================================================================
// end check: every mint touched — sell leftovers, close empty token accounts; late landings of never-landed buys
// ==================================================================================================================

async fn end_check(sh: &Arc<Shared>) {
    let mints: Vec<Launch> = { let mut v = sh.touched.lock().unwrap().clone(); v.dedup_by_key(|l| l.mint); v };
    say(format!("END CHECK: {} mint(s) touched", mints.len()));
    let mut rows = Vec::new();
    for l in &mints {
        let ata = snipe_build::assoc_user(&sh.user, &l.mint);
        let bal = token_balance(&sh.rpc, &ata, "confirmed").await;
        let mut row = serde_json::json!({ "mint": b58(&l.mint), "before": bal.as_ref().ok().cloned().flatten(), "read_ok": bal.is_ok(), "gmgn": gmgn(&l.mint) });
        match bal {
            Ok(Some(a)) if a > 0 => {
                say(format!("END CHECK {}: {a} tokens left: selling (min 0)", b58(&l.mint)));
                sh.mint_recs.lock().unwrap().entry(l.mint).or_default();
                let (sold, sigs) = sell_all(sh, 0, l, a, 0.0, Duration::from_secs(60)).await;
                let mut d = 0i64;
                for s in &sigs { d += tx_delta(&sh.rpc, &bs58::encode(s).into_string(), &sh.user).await.unwrap_or(0); }
                sh.ledger.lock().unwrap().realized += d;
                row["sold"] = sold.into(); row["sell_delta"] = d.into();
            }
            Ok(Some(_)) => {
                // empty account left open: close it (rent back)
                let ixs = vec![build::cu_limit_ix(20_000), build::cu_price_ix(sh.a.sell_cu_price_micro), build::close_account_ix(ata, sh.user, sh.user, *pda::TOKEN_2022)];
                if let Some(bh) = sh.blockhash(Duration::from_secs(25)) {
                    if let Ok(msg) = build::compile_v0(sh.user, &ixs, bh, &[], &[]) {
                        let raw = build::sign(&msg, &sh.key);
                        let _ = sh.sell_path.send(&raw, send::Prio { band: 0, crowd: 0, ev: 0 }, None).await;
                        let s = sig_of(&raw);
                        let land = wait_land(sh, &[s], |_, el| el > Duration::from_secs(10)).await;
                        row["closed"] = land.is_some_and(|x| x.2).into();
                    }
                }
            }
            Ok(None) => { row["closed"] = true.into(); }
            Err(e) => { row["err"] = redact(&format!("{e:#}")).into(); say(format!("END CHECK {}: could not read the token account — CHECK BY HAND", b58(&l.mint))); }
        }
        let after = token_balance(&sh.rpc, &ata, "confirmed").await.ok().flatten();
        row["after"] = after.into();
        say(format!("END CHECK {}: left {:?}", b58(&l.mint), after));
        rows.push(row);
    }
    // never-landed buys: a late landing (failed at the slot guard: a fee) is counted
    let un = sh.unlanded.lock().unwrap().clone();
    let mut late = Vec::new();
    for (id, sigs) in un {
        if let Ok(v) = sh.rpc.call("getSignatureStatuses", serde_json::json!([sigs.iter().map(|s| bs58::encode(s).into_string()).collect::<Vec<_>>(), { "searchTransactionHistory": true }])).await {
            for (i, x) in v["value"].as_array().into_iter().flatten().enumerate() {
                if x.is_null() { continue; }
                let s58 = bs58::encode(sigs[i]).into_string();
                let d = tx_delta(&sh.rpc, &s58, &sh.user).await.unwrap_or(0);
                sh.ledger.lock().unwrap().realized += d;
                late.push(serde_json::json!({ "id": id, "sig": s58, "err": x["err"], "delta": d }));
            }
        }
    }
    sh.rec.ev("end_check", serde_json::json!({ "mints": rows, "late_landings": late }));
}

// ==================================================================================================================
// start-up checks
// ==================================================================================================================

/// the slot guard: the encoding that passes a deadline 50 slots ahead and fails one 50 behind AT the guard (simulated,
/// sigVerify off: the payer must exist)
async fn verify_guard(rpc: &rpc::Rpc, key: &SigningKey, user: Pk) -> Result<GuardEnc> {
    let ai = rpc.call("getAccountInfo", serde_json::json!([b58(&LIGHTHOUSE), { "encoding": "base64", "dataSlice": { "offset": 0, "length": 0 } }])).await.context("getAccountInfo(lighthouse)")?;
    if ai["value"].is_null() || ai["value"]["executable"].as_bool() != Some(true) { bail!("Lighthouse is not an executable account"); }
    let s = rpc.slot().await.context("getSlot")?;
    let sim = |ix: build::Ix| async move {
        let bh = rpc.latest_blockhash().await.map(|x| x.0).unwrap_or([0u8; 32]);
        let msg = build::compile_v0(user, &[build::cu_limit_ix(20_000), ix], bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
        let raw = build::sign(&msg, key);
        let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
        let v = rpc.call("simulateTransaction", serde_json::json!([b64, { "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed" }])).await?;
        anyhow::Ok(v["value"]["err"].clone())
    };
    let mut tried = Vec::new();
    for g in [GUARD_DEFAULT, GuardEnc { disc: 14, op: 5, acct: false }, GuardEnc { disc: 15, op: 4, acct: false }, GuardEnc { disc: 14, op: 4, acct: false }, GuardEnc { disc: 15, op: 5, acct: true }] {
        let ok = sim(guard_ix(g, s + 50)).await?;
        let bad = sim(guard_ix(g, s.saturating_sub(50))).await?;
        let at_guard = bad.get("InstructionError").and_then(|x| x.get(0)).and_then(|x| x.as_u64()) == Some(1);
        if ok.is_null() && !bad.is_null() && at_guard { return Ok(g); }
        tried.push(format!("{g:?}: ahead={ok} behind={bad}"));
    }
    bail!("no Lighthouse encoding behaved as a slot deadline: {}", tried.join("; "))
}

/// every route's copy (multi-tip and, with nonces, each variant) passes each of its paths' own check; size <= 1232
fn selftest(sh: &Shared) -> std::result::Result<(), String> {
    let dummy = snipe_build::launch_from_target([0x5Au8; 32], [0x6Bu8; 32]);
    let mut lines = Vec::new();
    let cfgb = BuyCfg { user: sh.user, spend: sh.caps.size, min_out: 1, cu_limit: sh.a.cu_limit, cu_price: sh.a.cu_price_micro, guard: sh.guard.map(|g| (g, 1)) };
    let nonce = sh.nonce.as_ref().and_then(|n| n.take()).map(|(_, k, v)| (k, v));
    for (c, fan) in &sh.routes.map {
        let copies: Vec<(Copy, bool)> = if sh.a.recipe == "lanes" {
            let mut lc = Vec::new();
            for l in fan {
                let p = &sh.routes.paths[l.pi];
                if l.tip.is_some_and(|t| t > 0) && p.tip(0).is_none() { return Err(format!("lane {c}: {} has a tip but the path has no tip accounts", p.name)); }
                lc.push(LaneCopy { pi: l.pi, tip: p.tip(0).map(|(a, m)| (a, l.tip.unwrap_or(m))).filter(|t| t.1 > 0), prio: l.prio.unwrap_or(sh.a.prio_lamports) });
            }
            build_lane_copies(&sh.key, &cfgb, &dummy, nonce.unwrap_or(([0xEEu8; 32], [0xDDu8; 32])), &lc)?.into_iter().map(|x| (x, true)).collect()
        } else {
            let pp: Vec<(Option<(Pk, u64)>, &[Pk])> = fan.iter().map(|l| (sh.routes.paths[l.pi].tip(0), sh.routes.paths[l.pi].tip_accounts())).collect();
            let groups: Vec<(Option<(Pk, u64)>, Vec<usize>)> = tip_groups(&pp).into_iter().map(|(t, v)| (t, v.into_iter().map(|j| fan[j].pi).collect())).collect();
            let mut v: Vec<(Copy, bool)> = build_copies(&sh.key, &cfgb, &dummy, [7u8; 32], None, &groups)?.into_iter().map(|x| (x, false)).collect();
            if let Some(n) = nonce { v.extend(build_copies(&sh.key, &cfgb, &dummy, [7u8; 32], Some(n), &groups)?.into_iter().map(|x| (x, true))); }
            let covered: usize = v.iter().filter(|x| !x.1).map(|x| x.0.paths.len()).sum();
            if covered < fan.len() { lines.push(format!("{c}: {} of {} paths fit in 1232 bytes (the rest are dropped from multi-tip buys)", covered, fan.len())); }
            v
        };
        for (cp, nn) in &copies {
            for &pi in &cp.paths {
                let p = &sh.routes.paths[pi];
                p.check(&cp.raw).map_err(|e| format!("lane {c} path {} refuses its copy ({} bytes, tip {}, nonce {nn}): {e:#}", p.name, cp.raw.len(), cp.tip))?;
            }
        }
    }
    for l in lines { say(format!("NOTE: {l}")); }
    say(format!("SELF-TEST OK: every lane's buy copy passes its path's check (recipe {})", sh.a.recipe));
    Ok(())
}

fn parse_nonce_file(text: &str) -> std::result::Result<Vec<Pk>, String> {
    let mut out: Vec<Pk> = Vec::new();
    for (n, l) in text.lines().enumerate() {
        let s = l.split('#').next().unwrap_or("").trim();
        if s.is_empty() { continue; }
        let k: Pk = bs58::decode(s).into_vec().ok().and_then(|v| v.try_into().ok()).ok_or_else(|| format!("line {}: '{s}' is not a pubkey", n + 1))?;
        if !out.contains(&k) { out.push(k); }
    }
    if out.is_empty() || out.len() > 100 { return Err(format!("{} accounts (1..100)", out.len())); }
    Ok(out)
}

async fn read_nonces(rpc: &rpc::Rpc, keys: &[Pk]) -> Result<(u64, Vec<serde_json::Value>)> {
    let ks: Vec<String> = keys.iter().map(b58).collect();
    let v = rpc.call("getMultipleAccounts", serde_json::json!([ks, { "encoding": "base64", "commitment": "confirmed" }])).await?;
    let vals = v["value"].as_array().context("getMultipleAccounts: no value")?.clone();
    if vals.len() != keys.len() { bail!("getMultipleAccounts: {} values for {} keys", vals.len(), keys.len()); }
    Ok((v["context"]["slot"].as_u64().unwrap_or(0), vals))
}

/// an initialized current-version nonce account of the System program whose authority is `user`: its stored value
fn nonce_check(v: &serde_json::Value, user: &Pk) -> std::result::Result<[u8; 32], String> {
    if v.is_null() { return Err("no such account".into()); }
    if v["owner"].as_str() != Some("11111111111111111111111111111111") { return Err("owner is not the System program".into()); }
    let d = v["data"][0].as_str().and_then(|s| base64::engine::general_purpose::STANDARD.decode(s).ok()).ok_or("data is not base64")?;
    if d.len() != 80 || d[0..4] != 1u32.to_le_bytes() { return Err("not a current-version nonce account".into()); }
    let value = build::nonce_value(&d).ok_or("not an initialized nonce")?;
    if d[8..40] != user[..] { return Err("its authority is not this wallet".into()); }
    Ok(value)
}

// ==================================================================================================================
// OFFLINE replay of recorded launches (collector launches.jsonl): detection -> watch match -> decision -> build + sign
// ==================================================================================================================

/// one recorded launch as a create_v2 tx the shred decoder would hand over (keys + ix data per the IDL layout). The record's
/// `creator` is the CreateEvent's: a holder-reward launch (creator = the holder-rewards PDA of the mint) is synthesized as
/// the program saw it, args creator = the user + the holder-reward flag.
pub fn synth_create(rec: &serde_json::Value) -> Option<(arbx::tx::Tx, Pk)> {
    let p = |k: &str| rec[k].as_str().map(arbx::tx::pk);
    let (mint, bc, user, ev_creator) = (p("mint")?, p("bonding_curve")?, p("user")?, p("creator")?);
    let holder = ev_creator != user && ev_creator == holder_rewards_pda(&mint);
    let creator = if holder { user } else { ev_creator };
    let abc = snipe_build::assoc_bonding_curve(&bc, &mint);
    // static keys: 0 user (signer, payer), 1 mint (signer), 2 mint authority, 3 bonding curve, 4 assoc bc, 5 global, 6 PUMP
    let keys = vec![user, mint, *snipe::MINT_AUTHORITY, bc, abc, *snipe_build::GLOBAL, *snipe::PUMP];
    let mut d = snipe::CREATE_V2_DISC.to_vec();
    for k in ["name", "symbol", "uri"] { let s = rec[k].as_str().unwrap_or("").as_bytes(); d.extend((s.len() as u32).to_le_bytes()); d.extend(s); }
    d.extend(creator);
    d.extend([0u8, 0u8]); d.extend(0u64.to_le_bytes()); d.push(holder as u8);
    let ix = arbx::tx::Ix { program: 6, accounts: vec![1, 2, 3, 4, 5, 0], data: d };
    let mut sig = [0u8; 64];
    if let Some(s) = rec["sig"].as_str().and_then(|s| bs58::decode(s).into_vec().ok()) { if s.len() == 64 { sig.copy_from_slice(&s); } }
    Some((arbx::tx::Tx { sig, num_signers: 2, num_ro_signed: 0, num_ro_unsigned: 3, keys, ixs: vec![ix], ..Default::default() }, bc))
}

#[derive(Debug, Default, serde::Serialize)]
pub struct ReplaySum { pub records: usize, pub creates: usize, pub detected: usize, pub mint_ok: usize, pub creator_ok: usize, pub curve_pda_ok: usize,
    pub watched: usize, pub fired: usize, pub build_us_p50: u64, pub build_us_p99: u64, pub bad: Vec<String> }

/// the replay core (tests use it): every create_v2 record -> synthesized tx -> detect -> derived bonding curve vs the
/// recorded one -> watch match -> buy build + sign (throwaway key, shadow) -> parse back and check the accounts
pub fn replay_records(lines: &[serde_json::Value], watch: &HashSet<Pk>) -> ReplaySum {
    let key = SigningKey::from_bytes(&[42u8; 32]);
    let user = key.verifying_key().to_bytes();
    let mut s = ReplaySum { records: lines.len(), ..Default::default() };
    let mut us: Vec<u64> = Vec::new();
    for r in lines {
        let ix0 = r["ix0"].as_str().or_else(|| r["ixn"][0].as_str()).unwrap_or("");
        if ix0 != "CreateV2" { continue; }
        s.creates += 1;
        let Some((tx, bc_rec)) = synth_create(r) else { s.bad.push("synth".into()); continue };
        if !snipe::is_create_candidate(&tx) { s.bad.push(format!("{}: not a create candidate", r["mint"])); continue; }
        let Some(l) = snipe::detect_launch(&tx) else { s.bad.push(format!("{}: not detected", r["mint"])); continue };
        s.detected += 1;
        if r["mint"].as_str() == Some(&b58(&l.mint)) { s.mint_ok += 1; }
        if r["creator"].as_str() == Some(&b58(&event_creator(&l))) { s.creator_ok += 1; }
        // the bonding curve derived from the mint (what a buy for a router create uses) must be the recorded one
        if snipe_build::bonding_curve(&l.mint) == bc_rec { s.curve_pda_ok += 1; } else { s.bad.push(format!("{}: derived curve differs", r["mint"])); }
        if !MatchOn::Creator.hit(watch, &event_creator(&l), &l.creator, tx.keys.first()) { continue; }
        s.watched += 1;
        let t0 = Instant::now();
        let exp = expected_tokens(l.dev_buy_lamports, 50_000_000);
        let c = BuyCfg { user, spend: 50_000_000, min_out: buy_min_out(exp, 0.2), cu_limit: 100_000, cu_price: 5_000_000, guard: Some((GUARD_DEFAULT, r["slot"].as_u64().unwrap_or(0) + 1)) };
        // first-or-revert state from the create's own legs (the recording has no dev-buy legs: the fresh curve) + 3 lanes
        let (_, mo) = first_min_out(curve_after_legs(&[]).unwrap_or(snipe::CURVE_VQ0), 50_000_000, 0.005);
        let c = BuyCfg { min_out: mo, ..c };
        let lanes = [LaneCopy { pi: 0, tip: Some(([9u8; 32], 2_000_000)), prio: 100_000 }, LaneCopy { pi: 1, tip: None, prio: 2_000_000 }, LaneCopy { pi: 2, tip: Some(([8u8; 32], 2_500_000)), prio: 500_000 }];
        let copies = match build_lane_copies(&key, &c, &l, ([0xEEu8; 32], [0xDDu8; 32]), &lanes) { Ok(v) => v, Err(e) => { s.bad.push(format!("{}: build {e}", r["mint"])); continue; } };
        us.push(t0.elapsed().as_micros() as u64);
        // parse the signed tx back: the pump buy's base mint [1], bonding curve [5], user ATA [9]
        let Some((ptx, _)) = arbx::tx::parse_wire(&copies[0].raw) else { s.bad.push(format!("{}: unparsable", r["mint"])); continue };
        let buy = ptx.ixs.iter().find(|ix| ptx.keys[ix.program as usize] == *snipe::PUMP);
        let ok = buy.is_some_and(|ix| ptx.keys[ix.accounts[1] as usize] == l.mint && ptx.keys[ix.accounts[5] as usize] == bc_rec
            && ptx.keys[ix.accounts[9] as usize] == snipe_build::assoc_user(&user, &l.mint));
        if ok { s.fired += 1; } else { s.bad.push(format!("{}: built buy accounts differ", r["mint"])); }
    }
    us.sort_unstable();
    let q = |f: f64| us.get(((us.len() as f64 - 1.0) * f).round() as usize).copied().unwrap_or(0);
    s.build_us_p50 = q(0.5);
    s.build_us_p99 = q(0.99);
    s
}

fn replay(a: &Args, file: &str) -> Result<()> {
    let text = std::fs::read_to_string(file).with_context(|| format!("--replay-launches {file}"))?;
    let lines: Vec<serde_json::Value> = text.lines().filter_map(|l| serde_json::from_str(l).ok()).collect();
    let watch = match load_watch(&a.watchlist) {
        Ok(w) => w,
        Err(_) => {
            let mut n: HashMap<String, usize> = HashMap::new();
            for r in &lines { if let Some(c) = r["creator"].as_str() { *n.entry(c.to_string()).or_default() += 1; } }
            n.into_iter().filter(|(_, k)| *k >= a.replay_min_launches).map(|(c, _)| arbx::tx::pk(&c)).collect()
        }
    };
    let s = replay_records(&lines, &watch);
    println!("{}", serde_json::to_string_pretty(&s)?);
    if !s.bad.is_empty() { bail!("replay: {} problem(s)", s.bad.len()); }
    Ok(())
}

// ==================================================================================================================
// OFFLINE: the entry score vs the APEX-3 code (entry_export.py cases; optional raw txs from entry_fetch_txs.py)
// ==================================================================================================================

/// one tx as entry_fetch_txs.py stores it (getTransaction json: static keys, loaded addresses, header, instructions)
pub fn tx_from_json(v: &serde_json::Value) -> Option<arbx::tx::Tx> {
    let pks = |k: &str| -> Option<Vec<Pk>> { v[k].as_array()?.iter().map(|x| x.as_str().and_then(parse_pk)).collect() };
    let keys = pks("keys")?;
    let (lw, lr) = (pks("lw").unwrap_or_default(), pks("lr").unwrap_or_default());
    let h = v["hdr"].as_array()?;
    let mut ixs = Vec::new();
    for ix in v["ixs"].as_array()? {
        let data = base64::engine::general_purpose::STANDARD.decode(ix[2].as_str()?).ok()?;
        ixs.push(arbx::tx::Ix { program: ix[0].as_u64()? as u8, accounts: ix[1].as_array()?.iter().map(|x| x.as_u64().map(|n| n as u8)).collect::<Option<Vec<_>>>()?, data });
    }
    let mut sig = [0u8; 64];
    if let Some(s) = v["sig"].as_str().and_then(|s| bs58::decode(s).into_vec().ok()) { if s.len() == 64 { sig.copy_from_slice(&s); } }
    Some(arbx::tx::Tx { sig, num_signers: h.first()?.as_u64()? as u8, num_ro_signed: h.get(1)?.as_u64()? as u8, num_ro_unsigned: h.get(2)?.as_u64()? as u8,
        keys, loaded: (!lw.is_empty() || !lr.is_empty()).then_some((lw, lr)), ixs, ..Default::default() })
}

/// the probe's create-time inputs derived from the raw txs (as decide/entry_score do from the shreds): CreateEvent creator,
/// dev SOL (first create leg), bundle SOL (bundle txs' legs, in block order) and the bundle's distinct fee payers
pub fn obs_from_txs(create: &arbx::tx::Tx, bundle: &[arbx::tx::Tx]) -> Option<(Pk, u64, u64, usize, usize)> {
    let l = snipe::detect_launch(create).or_else(|| router_launch(create))?;
    let cl: Vec<(bool, u64, u64)> = match entry::entry_legs(create, &l.mint) { Some(entry::ELegs::Buys(v)) => v.into_iter().map(|x| x.0).collect(), _ => Vec::new() };
    let mut bl = Vec::new();
    let mut users: Vec<Pk> = Vec::new();
    let mut unseen = 0;
    // the tape's bundle: consecutive txs after the create, buys only (the first non-buy ends it)
    for t in bundle {
        match entry::entry_legs(t, &l.mint) {
            Some(entry::ELegs::Buys(v)) => for (leg, p) in v { bl.push(leg); if !users.contains(&p) { users.push(p); } },
            Some(entry::ELegs::Unseen) => unseen += 1,
            _ => break,
        }
    }
    let (dev, bund) = entry::leg_sols(&cl, &bl);
    Some((event_creator(&l), dev, bund, users.len(), unseen))
}

fn entry_validate(a: &Args, file: &str) -> Result<()> {
    let m = entry::EntryModel::load(&a.entry_model).map_err(|e| anyhow::anyhow!("--entry-model {e}"))?;
    let thr = a.entry_thr.unwrap_or(m.thr);
    let text = std::fs::read_to_string(file).with_context(|| format!("--entry-validate {file}"))?;
    let f = |v: &serde_json::Value| -> f64 { v.as_str().and_then(|s| s.parse().ok()).or_else(|| v.as_f64()).unwrap_or(f64::NAN) };
    let txs: HashMap<String, serde_json::Value> = match &a.entry_txs {
        Some(p) => std::fs::read_to_string(p).with_context(|| format!("--entry-txs {p}"))?.lines().filter_map(|l| serde_json::from_str::<serde_json::Value>(l).ok())
            .filter_map(|v| Some((v["mint"].as_str()?.to_string(), v))).collect(),
        None => HashMap::new(),
    };
    let (mut n, mut exact, mut dmax, mut dlive, mut pick_agree, mut picks) = (0usize, 0usize, 0f64, 0f64, 0usize, 0usize);
    let mut fmax = [0f64; entry::NF];
    let mut fbad = [0usize; entry::NF];
    // tx-derived inputs
    let (mut tn, mut t_ev_ok, mut t_dev_ok, mut t_bund_ok, mut t_users_ok, mut t_exact, mut t_dmax, mut t_pick_agree) = (0usize, 0usize, 0usize, 0usize, 0usize, 0usize, 0f64, 0usize);
    let (mut t_dev_max, mut t_bund_max, mut t_unseen) = (0f64, 0f64, 0usize);
    let mut bad: Vec<String> = Vec::new();
    let mut score_ns: Vec<u64> = Vec::new();
    for l in text.lines() {
        let Ok(c) = serde_json::from_str::<serde_json::Value>(l) else { continue };
        let Some(cre) = c["creator"].as_str().and_then(parse_pk) else { continue };
        let o = entry::Obs { dev_sol: f(&c["dev_sol"]), bund_sol: f(&c["bund_sol"]), bund_users: c["bund_users"].as_f64().unwrap_or(0.0), u: f(&c["u"]), bt: c["bt"].as_i64().unwrap_or(0) };
        let t0 = Instant::now();
        let sc = m.score(&cre, &o);
        score_ns.push(t0.elapsed().as_nanos() as u64);
        let py = f(&c["score"]);
        let py_live = f(&c["score_live"]);
        n += 1;
        if sc.score.to_bits() == py.to_bits() { exact += 1; }
        dmax = dmax.max((sc.score - py).abs());
        dlive = dlive.max((sc.score - py_live).abs());
        if (sc.score >= thr) == (py >= thr) { pick_agree += 1; }
        if c["sel"].as_bool() == Some(true) && py >= thr { picks += 1; }
        if let Some(xs) = c["x"].as_array() {
            for j in 0..entry::NF {
                let (p, r) = (f(&xs[j]), sc.x[j]);
                let same = (p.is_nan() && r.is_nan()) || p.to_bits() == r.to_bits();
                if !same { fbad[j] += 1; fmax[j] = fmax[j].max(if p.is_nan() || r.is_nan() { f64::INFINITY } else { (p - r).abs() }); }
            }
        }
        // the same launch from its raw txs (the probe's own derivation)
        let mint = c["mint"].as_str().unwrap_or("");
        if let Some(t) = txs.get(mint) {
            let Some(ct) = tx_from_json(&t["create"]) else { bad.push(format!("{mint}: create tx unreadable")); continue };
            let bts: Vec<arbx::tx::Tx> = t["bundle"].as_array().map(|v| v.iter().filter_map(tx_from_json).collect()).unwrap_or_default();
            let Some((ev, dev, bund, nu, unseen)) = obs_from_txs(&ct, &bts) else { bad.push(format!("{mint}: create not detected")); continue };
            if unseen > 0 { t_unseen += 1; }
            tn += 1;
            if ev == cre { t_ev_ok += 1; } else { bad.push(format!("{mint}: event creator {} != {}", b58(&ev), b58(&cre))); }
            let (dv, bv) = (dev as f64 / 1e9, bund as f64 / 1e9);
            if dv.to_bits() == o.dev_sol.to_bits() { t_dev_ok += 1; } else if bad.len() < 40 { bad.push(format!("{mint}: dev {dv} != tape {}", o.dev_sol)); }
            if bv.to_bits() == o.bund_sol.to_bits() { t_bund_ok += 1; } else if bad.len() < 40 { bad.push(format!("{mint}: bundle {bv} != tape {}", o.bund_sol)); }
            if nu as f64 == o.bund_users { t_users_ok += 1; } else if bad.len() < 40 { bad.push(format!("{mint}: bundle users {nu} != tape {}", o.bund_users)); }
            t_dev_max = t_dev_max.max((dv - o.dev_sol).abs());
            t_bund_max = t_bund_max.max((bv - o.bund_sol).abs());
            let st = m.score(&ev, &entry::Obs { dev_sol: dv, bund_sol: bv, bund_users: nu as f64, ..o });
            if st.score.to_bits() == py.to_bits() { t_exact += 1; }
            t_dmax = t_dmax.max((st.score - py).abs());
            if (st.score >= thr) == (py >= thr) { t_pick_agree += 1; }
        }
    }
    score_ns.sort_unstable();
    let sq = [score_ns.get(score_ns.len() / 2).copied(), score_ns.get(score_ns.len() * 99 / 100).copied()];
    let out = serde_json::json!({ "model": m.name, "sha256": m.sha256, "thr": thr, "cases": n, "score_bit_exact": exact, "score_max_abs_diff": dmax,
        "score_live_max_abs_diff": dlive, "pass_agree": pick_agree, "backtest_picks_passing": picks,
        "score_ns_p50_p99": sq,
        "feature_mismatch_n": FEATURE_NAMES.iter().zip(fbad).map(|(k, v)| (k.to_string(), serde_json::json!(v))).collect::<serde_json::Map<_, _>>(),
        "feature_max_abs_diff": FEATURE_NAMES.iter().zip(fmax).map(|(k, v)| (k.to_string(), serde_json::json!(v))).collect::<serde_json::Map<_, _>>(),
        "from_txs": { "n": tn, "event_creator_ok": t_ev_ok, "dev_exact": t_dev_ok, "dev_max_abs_diff_sol": t_dev_max, "bundle_sol_exact": t_bund_ok,
            "bundle_max_abs_diff_sol": t_bund_max, "bundle_users_ok": t_users_ok, "launches_with_unreadable_bundle_tx": t_unseen, "score_bit_exact": t_exact, "score_max_abs_diff": t_dmax, "pass_agree": t_pick_agree },
        "problems": bad });
    println!("{}", serde_json::to_string_pretty(&out)?);
    Ok(())
}

const FEATURE_NAMES: [&str; entry::NF] = entry::FEATURES;

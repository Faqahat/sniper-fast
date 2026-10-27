// ===================================================================================================================
// --dip: the dip-backrun engine (2026-10-24 PKT; ops/dip/ENGINE_IMIT1.md, ops/overnight/sel/SELECTION.md).
// Trade history and triggers come from an EXECUTED feed (yellowstone-tx, pump program, processed): every pump TradeEvent
// with the tx's index in its block (src/feeds ExecInfo). Each token created after the start is followed in a
// `dip_imit::TokenBook` (the study builder's exact rules and features, parity-tested against the Python). On a dump (a
// >= 1 SOL curve sell, first big sell of its slot) the frozen IMIT1 selector scores it; inside the watch envelope with a
// score >= the tier's threshold it is a PICK.
//   * shadow (no --live): every pick is logged with the route it would take; nothing is sent
//   * --live: a guarded buy (min tokens out = the post-dump curve's quote / --dip-guard, default 1.02; on-chain slot
//     deadline with --buy-max-slot-delta) through the FAST path, then a take-profit / stop-loss / time-limit exit
//     driven by the executed feed's prices; sold with the engine's sell loop (cached blockhash first send)
// Records: --dip-log JSONL (dump / pick / fire / buy_land / exit / sell_land / close / run), one line per event.
// Caps: --max-buys (landed buys per run), --max-inflight (open positions), --max-sol (per buy), --max-loss-sol (kill
// switch on the balance), --minutes. One position per token; a new pick on a token needs --dip-spacing-slots (5).
// ===================================================================================================================
use super::*;
use arbx::dip_imit::{self as di, Imit, LaunchInfo, TokenBook, T};
// PRE-SEND LIVE (--presend-live; ops/strategies/presend/LIVE.md): the capped live probe of pre-sent buys (off without the flag)
#[path = "pslive.rs"]
mod pslive;
// SHRED FIRE (--dip-shred-fire; dip14; ops/dip/speed/fixes/FIXES.md): fire on the first shred sighting of a dump (off without the flag)
#[path = "shredfire.rs"]
mod shredfire;
use std::collections::{HashMap, HashSet};
use std::io::Write as _;

/// the JSONL recorder (one line per event; flushed per line so a crash keeps everything up to it)
struct DipLog(Option<std::sync::Mutex<std::io::BufWriter<std::fs::File>>>);
impl DipLog {
    fn open(p: Option<String>) -> Result<DipLog> {
        Ok(DipLog(match p { Some(p) => Some(std::sync::Mutex::new(std::io::BufWriter::new(std::fs::OpenOptions::new().create(true).append(true).open(&p).with_context(|| format!("--dip-log {p}"))?))), None => None }))
    }
    fn w(&self, v: serde_json::Value) {
        if let Some(f) = &self.0 { let mut g = f.lock().unwrap(); let _ = writeln!(g, "{v}"); let _ = g.flush(); }
    }
    /// PRE-SEND SHADOW: several records with one lock and one flush (the shadow writes a call's records together)
    fn w_all(&self, vs: impl IntoIterator<Item = serde_json::Value>) {
        if let Some(f) = &self.0 {
            let mut g = f.lock().unwrap();
            let mut any = false;
            for v in vs { let _ = writeln!(g, "{v}"); any = true; }
            if any { let _ = g.flush(); }
        }
    }
}

/// one followed token
/// `keys` (B2 --dip-defer, dip14): the buy's mint-dependent keys derived at the create (None: derived at the buy, as dip13)
struct Tok { book: TokenBook, launch: Option<Launch>, t_created: Instant, last_pick_slot: Option<u64>, dev: bool, keys: Option<arbx::fast::VarKeys> }

/// a fired buy and its position
struct LivePos {
    mint: Pk, launch: Launch, dump_sig: String, dump_slot: u64, dump_idx: u64, t_dump_rx: u64, dump_vsol: u64, dump_vtok: u64,
    score: f64, t_fire_ns: u64, buy_sig: String, buy_sig_b: [u8; 64], route: String, leader: String, client: String, tips: u64,
    spend: u64, min_out: u64, send_slot: u64,
    land: Option<(u64, u64, u64)>, tokens: u64, sol_in: u64, buy_ok: Option<bool>,
    exit: Option<(&'static str, u64, f64, u64)>, sell_land: Option<(u64, u64, u64, u64)>,
    pos: Option<Pos>, fired_at: Instant,
    /// NONCE (--nonce-fanout): the buy's sent variants (empty: today's one tx). Until one is seen landed `buy_sig` /
    /// `buy_sig_b` are the first-written one and `tips` the largest; then the landed one's (`adopt`)
    vars: Vec<Var>,
}

/// NONCE: one sent durable-nonce variant of a buy: its signature, the one tip it pays (0: tipless), its send paths
#[derive(Clone)]
struct Var { sig: String, sig_b: [u8; 64], tip: u64, tip_acct: Option<Pk>, paths: Vec<String> }

fn var_json(v: &Var) -> serde_json::Value { serde_json::json!({"sig": v.sig, "tip": v.tip, "tip_acct": v.tip_acct.map(|a| b58(&a)), "paths": v.paths}) }

impl LivePos {
    /// our buy's signature: the one tx, or (NONCE) any of its variants
    fn ours(&self, sig: &[u8; 64]) -> bool { self.buy_sig_b == *sig || self.vars.iter().any(|v| v.sig_b == *sig) }
    /// NONCE: the variant `sig` (seen on chain) becomes THE buy: its signature (the realized PnL reads that tx) and its one
    /// tip (the only one paid). Some(its record) for the logs; None when it is not one of our variants (nothing changes)
    fn adopt(&mut self, sig: &[u8; 64]) -> Option<serde_json::Value> {
        let v = self.vars.iter().find(|v| v.sig_b == *sig)?.clone();
        self.buy_sig = v.sig.clone();
        self.buy_sig_b = v.sig_b;
        self.tips = v.tip;
        Some(var_json(&v))
    }
}

/// a JSON record with the NONCE variant field added when there is one (records of today's one-tx buys are unchanged)
fn with_var(mut j: serde_json::Value, var: Option<serde_json::Value>) -> serde_json::Value {
    if let Some(v) = var { j["variant"] = v; }
    j
}

enum Msg { Land(Pk, Landed), Sold(Pk, SellOut), Ps(pslive::PsMsg) }

const TXC: f64 = 0.0008;    // the replay's per-tx cost (value math for TP / SL, as the study)
/// dip15: the run ends this long after the pre-send stop even if its bookkeeping never goes idle (AMS run 17, 10-25: 9 attempts
/// never resolved and the engine never exited); no pre-send position may be open
const PS_END_GRACE: Duration = Duration::from_secs(20);

pub async fn run_dip(probe: &Probe, key: &SigningKey, user: Pk, rpc: &Arc<rpc::Rpc>, path: &Arc<send::Path>, live: bool, stop: &Arc<AtomicBool>) -> Result<()> {
    let model_p = arg("--dip-model").unwrap_or_else(|| "/root/dip/IMIT1.json".into());
    let model = Imit::load(&model_p).map_err(|e| anyhow::anyhow!("--dip-model: {e}"))?;
    let cohort_p = arg("--dip-cohort").unwrap_or_else(|| "/root/dip/cohort_train.json".into());
    let cohort: HashSet<String> = serde_json::from_str::<Vec<String>>(&std::fs::read_to_string(&cohort_p).with_context(|| format!("--dip-cohort {cohort_p}"))?)?.into_iter().collect();
    let targets: HashSet<String> = di::TARGETS.iter().map(|s| s.to_string()).collect();
    // M2 (--dip-m2 BUNDLE, 10-25 PKT; ops/strategies/dipdetect/PORT.md): the new dip detector (25-feature GBDT, "Stage A").
    //   --dip-m2-mode shadow (default): trading stays IMIT1; every in-envelope dump ALSO gets its M2 score, computed after the
    //     IMIT1 decision and any send, in its "dump" record (m2, m2_pick, m2_feats, m2_us)
    //   --dip-m2-mode gate: M2 score >= --dip-m2-min replaces the IMIT1 gate for tokens off the dev list (envelope, near
    //     leaders, spacing, launch checks, guard, sizes unchanged; dev-list tokens keep their IMIT1 tier); IMIT1 is still logged
    //   --dip-m2-min X: the threshold (default: the bundle's Stage A threshold)
    //   --dip-m2-extra on|off (default on; off with --dip-probe): M2 also scores the big sells the IMIT1 rules skip only because
    //     an earlier big sell of the same slot was the dump event (in the study's Stage A: ~20% of its picks); IMIT1 never picks them
    // Without --dip-m2 none of this runs (the other M2 flags alone are refused). (--dip-model is IMIT1's file, as before.)
    let m2: Option<arbx::dip_model::Bundle> = match arg("--dip-m2") {
        Some(p) => Some(arbx::dip_model::Bundle::load(&p).map_err(|e| anyhow::anyhow!("--dip-m2: {e}"))?),
        None => None,
    };
    let m2_gate = match arg("--dip-m2-mode").as_deref() { None | Some("shadow") => false, Some("gate") => true, Some(x) => bail!("--dip-m2-mode {x}: shadow | gate") };
    if m2.is_none() && (has("--dip-m2-mode") || has("--dip-m2-min") || has("--dip-m2-extra")) { bail!("--dip-m2-mode / --dip-m2-min / --dip-m2-extra need --dip-m2 BUNDLE"); }
    let m2_min = match (&m2, arg("--dip-m2-min")) {
        (Some(_), Some(s)) => s.parse::<f64>().map_err(|_| anyhow::anyhow!("--dip-m2-min {s}: not a number"))?,
        (Some(b), None) => b.thr_default,
        (None, _) => 0.0,
    };
    // PRE-SEND SHADOW (--presend-shadow; owner GO 10-25 ~02:00 PKT; ops/strategies/presend/SHADOW.md): the study's pre-sent
    // conditional buy, trigger T2 "whale buy" (src/presend.rs), LOG ONLY: it never sends and never changes a decision. Every
    // executed tx goes in AFTER the IMIT1 decision, any send and the exits of that tx; records presend_arm / _fill / _exit /
    // _disarm / _skip in --dip-log, counts in the 60 s status line. Parameters (defaults = the study's chosen config "T2|c"):
    // --presend-whale-pct 5, --presend-window-slots 10, --presend-drop 0.12, --presend-ref-ms 50, --presend-live-ms 50,
    // --presend-size-sol 0.55, --presend-exit-slots 2, --presend-tp 0.10 (0 = none), --presend-sl 0.20 (0 = none). A parameter
    // without --presend-shadow is refused; without --presend-shadow nothing of this runs.
    let presend_params = ["--presend-whale-pct", "--presend-window-slots", "--presend-drop", "--presend-ref-ms", "--presend-live-ms", "--presend-size-sol",
                          "--presend-exit-slots", "--presend-tp", "--presend-sl"];
    let mut presend: Option<arbx::presend::Shadow> = if has("--presend-shadow") {
        let d = arbx::presend::Params::default();
        let p = arbx::presend::Params { whale_pct: arg_f64("--presend-whale-pct", d.whale_pct), window_slots: arg_u64("--presend-window-slots", d.window_slots),
            drop: arg_f64("--presend-drop", d.drop), ref_ms: arg_f64("--presend-ref-ms", d.ref_ms), live_ms: arg_f64("--presend-live-ms", d.live_ms),
            size_sol: arg_f64("--presend-size-sol", d.size_sol), exit_slots: arg_u64("--presend-exit-slots", d.exit_slots), tp: arg_f64("--presend-tp", d.tp),
            sl: arg_f64("--presend-sl", d.sl), ..d };
        p.check().map_err(|e| anyhow::anyhow!("--presend-shadow: {e}"))?;
        Some(arbx::presend::Shadow::new(p))
    } else {
        if let Some(f) = presend_params.iter().find(|f| has(f)) { bail!("{f} needs --presend-shadow"); }
        None
    };
    let mut ps_marks: Vec<[u64; 5]> = Vec::new();
    let mut ps_time = PresendTime::default();
    let tier = arg("--dip-tier").unwrap_or_else(|| "strict".into());
    let thr_key = match tier.as_str() { "strict" => "top2", "wider" => "top4", "top8" => "top8", t => bail!("--dip-tier {t}: strict | wider | top8") };
    let thr = *model.thresholds.get(thr_key).ok_or_else(|| anyhow::anyhow!("{model_p}: no threshold {thr_key}"))?;
    let tp = arg_f64("--dip-tp", 0.05); let sl = arg_f64("--dip-sl", 0.10); let hold = arg_u64("--dip-hold-slots", 6);
    // --dip-tp >= 9 (+900%) = no take-profit: stop-loss or the time limit (owner 10-24 for run 5: "1.3")
    let tp_s = if tp >= 9.0 { "TP off".to_string() } else { format!("TP +{:.0}%", tp * 100.0) };
    // --dip-dev-list FILE (owner 10-24: "0.75 for this dev tier"): tokens whose create was SIGNED by, or names as creator, a
    // listed wallet (serial launchers the imitated bots over-weight; ops/overnight/sel/haqq_dev.py) are picked from
    // --dip-dev-tier (default wider) and bought with --dip-dev-spend-lamports (default --spend-lamports)
    let devs: HashSet<String> = match arg("--dip-dev-list") {
        Some(p) => std::fs::read_to_string(&p).with_context(|| format!("--dip-dev-list {p}"))?.lines()
            .map(|l| l.split('#').next().unwrap_or("").trim().to_string()).filter(|l| !l.is_empty()).collect(),
        None => HashSet::new(),
    };
    for d in &devs { if bs58::decode(d).into_vec().map(|v| v.len()) != Ok(32) { bail!("--dip-dev-list: {d} is not a wallet address"); } }
    let dev_tier = arg("--dip-dev-tier").unwrap_or_else(|| "wider".into());
    let dev_key = match dev_tier.as_str() { "strict" => "top2", "wider" => "top4", "top8" => "top8", t => bail!("--dip-dev-tier {t}: strict | wider | top8") };
    let thr_dev = *model.thresholds.get(dev_key).ok_or_else(|| anyhow::anyhow!("{model_p}: no threshold {dev_key}"))?;
    let guard = arg_f64("--dip-guard", 1.02).max(1.0);
    let max_age_s = arg_f64("--dip-max-age-s", 1800.0);
    let spacing = arg_u64("--dip-spacing-slots", 5);
    let allow_holder = has("--dip-allow-holder");
    // --dip-probe N (10-24, owner: "improve our landing by fee or path"): LANDING PROBES instead of trades. On every in-envelope
    // dump (any score) of a tradable token, at most one per --dip-probe-gap-ms, fire a buy that CANNOT fill (min tokens out =
    // u64::MAX -> pump 6042 on chain: no token bought, tips revert, cost = base + priority fee) through the normal route for the
    // leader; its block position after the dump is the landing delay of that route (ops/dip/speed/probe_speed.py). No trades.
    let probe_n = arg_u64("--dip-probe", 0);
    let probe_gap = Duration::from_millis(arg_u64("--dip-probe-gap-ms", 1500));
    let (mut probes_fired, mut last_probe, mut probe_done_at): (u64, Option<Instant>, Option<Instant>) = (0, None, None);
    let mut probe_sigs: HashMap<[u8; 64], (String, u64)> = HashMap::new();
    // --dip-probe-paths a,b,c: one FORCED send path per probe, rotated (every path measured under the same conditions);
    // --dip-near-leaders FILE: probes AND picks only when the dump slot's leader is in the list (one pubkey per line)
    let probe_paths: Vec<String> = arg("--dip-probe-paths").map(|s| s.split(',').map(|x| x.trim().to_string()).filter(|x| !x.is_empty()).collect()).unwrap_or_default();
    let near: Option<HashSet<String>> = match arg("--dip-near-leaders") {
        Some(p) => Some(std::fs::read_to_string(&p).with_context(|| format!("--dip-near-leaders {p}"))?.lines().map(|l| l.trim().to_string()).filter(|l| !l.is_empty()).collect()),
        None => None,
    };
    // ---- dip14 (owner OK 10-25 ~08:45 PKT "yes do the fixes"; ops/dip/speed/fixes/FIXES.md); each one is off without its flag
    //   B1 SHRED FIRE: --dip-shred-fire shadow|live (+ --dip-shred-index exact|window, --dip-shred-window N, --dip-shred-margin N)
    let shred_cfg = shredfire::Cfg::from_args(live, probe_n > 0)?;
    //   C1: --dip-skip-clients LIST = no buy (executed or shred path) when the dump slot's leader client (clientId or class) is listed
    //   probes: --dip-probe-clients LIST (probe only on these leaders' slots), --dip-probe-tipless on|off (D3: every probe also sends a
    //   TIPLESS twin through its one path: do tipped copies that would revert get dropped?)
    let shredfire::ClientFlags { skip_clients, probe_clients, probe_tipless } = shredfire::client_flags(&std::env::args().collect::<Vec<_>>(), probe_n, !probe_paths.is_empty())?;
    if (skip_clients.is_some() || probe_clients.is_some()) && lat::BOOK.read().unwrap().is_none() { bail!("--dip-skip-clients / --dip-probe-clients need the leader book (--route-by-client)"); }
    //   B2: --dip-defer = the dump / pick / pick_skip records of a buy written after its sends; its route computed once
    let defer = has("--dip-defer");
    //   D1: --dip-clock2 = timing records with the block-position clocks (PoH position in the block, the real block size, the entries
    //   feed's arrival, every feed's own arrival of both txs) and both block indexes
    let clock2 = has("--dip-clock2");
    //   B3: --dip-feed-lag = a feed_lag record every 60 s (executed vs shred feeds on every pump tx, the providers' own lag, the queue)
    let feed_lag = has("--dip-feed-lag");
    // ---- dip16 (owner OK 10-25 ~19:50 PKT; speed16.rs, ops/dip/speed/clients/CLIENTS.md); each one is off without its flag
    //   B4: --dip-probe-nonce on|ab = landing probes on a durable nonce of the --nonce-fanout pool (ab: both arms on every path)
    //   C5: --dip-probe-lock-only on = landing probes that SUCCEED and only write-lock the token's curve accounts (they pay their tips)
    let argv: Vec<String> = std::env::args().collect();
    let probe_nonce = speed16::ProbeNonce::parse(&argv)?;
    let lock_only = speed16::lock_only_flag(&argv)?;
    if probe_n == 0 && (has("--dip-probe-nonce") || has("--dip-probe-lock-only") || has("--dip-probe-lock-cu")) { bail!("--dip-probe-nonce / --dip-probe-lock-only / --dip-probe-lock-cu need --dip-probe N"); }
    if has("--dip-probe-lock-cu") && !lock_only { bail!("--dip-probe-lock-cu needs --dip-probe-lock-only on"); }
    if probe_nonce != speed16::ProbeNonce::Off && lock_only { bail!("--dip-probe-nonce with --dip-probe-lock-only: one probe experiment at a time"); }
    // a lock-only probe SUCCEEDS, so it pays every tip it carries: one forced path per probe (a whole route's 3-4 tips would be ~0.003 SOL)
    if lock_only && probe_paths.is_empty() { bail!("--dip-probe-lock-only on needs --dip-probe-paths (one path per probe: a landed lock-only probe pays its tips)"); }
    if probe_nonce != speed16::ProbeNonce::Off && probe_tipless { bail!("--dip-probe-nonce with --dip-probe-tipless on: one probe experiment at a time (a twin would race its probe's nonce)"); }
    if probe_nonce != speed16::ProbeNonce::Off && live && noncefan::get().is_none() { bail!("--dip-probe-nonce {probe_nonce:?} needs the durable-nonce pool: --nonce-fanout --nonce-accounts FILE"); }
    let lock_cu = speed16::lock_cu();
    //   C4: --window-clock = the dump's leader-window clock in the fire / probe / timing (and shadow pick) records; the feeds' slot
    //   first-arrival table starts now, before the feeds
    speed16::window_setup();
    let wclock = speed16::window_on();
    // exact timing (10-24, owner: "focus on getting landings in nearby area"): the first sighting of every tx on ANY feed
    // (sig8 -> t_rx, feed; kept 30 s), and ~2 s after a fire / probe the PoH positions (the leader's clock) of the dump and of
    // our tx -> one "timing" record each (feed lag, our reaction, fire -> seen back, landing delay on the leader's clock)
    let feed_names: Vec<String> = probe.feeds.iter().filter(|f| f.enabled).map(|f| f.name.clone()).collect();
    let mut first_seen: rustc_hash::FxHashMap<u64, (u64, u16)> = Default::default();
    let mut first_order: std::collections::VecDeque<(u64, u64)> = Default::default();
    let mut pend: Vec<Pend> = Vec::new();
    let mut last_pend_check = Instant::now();
    let log = Arc::new(DipLog::open(arg("--dip-log"))?);
    if !probe.feeds.iter().any(|f| f.kind == config::FeedKind::YellowstoneTx) { bail!("--dip needs an executed feed (kind = \"yellowstone-tx\") in --config"); }
    let spend = arg_u64("--spend-lamports", 2_000_000);
    let dev_spend = arg_u64("--dip-dev-spend-lamports", spend);
    let minutes = arg_u64("--minutes", 30);
    let max_buys = arg_u64("--max-buys", 0);
    let max_inflight = arg_u64("--max-inflight", 2) as usize;
    let (cap_lamports, loss_cap) = if live {
        let max_sol = arg_f64("--max-sol", -1.0);
        if max_sol <= 0.0 { bail!("--dip --live requires --max-sol <cap> (per-buy cap)"); }
        let max_loss = arg_f64("--max-loss-sol", -1.0);
        if max_loss <= 0.0 { bail!("--dip --live requires --max-loss-sol <cap> (balance kill switch)"); }
        if max_buys == 0 { bail!("--dip --live requires --max-buys N (landed buys in this run)"); }
        ((max_sol * 1e9) as u64, (max_loss * 1e9) as u64)
    } else { (u64::MAX, u64::MAX) };
    if live && spend > cap_lamports { bail!("REFUSED: --spend-lamports {spend} exceeds --max-sol"); }
    // PRE-SEND LIVE (--presend-live): its flags checked now (refused before any feed starts); started below
    let ps_live_cfg = pslive::Cfg::from_args(&presend.as_ref().map(|s| s.p.clone()).unwrap_or_default(), live, cap_lamports)?;
    if live && dev_spend > cap_lamports { bail!("REFUSED: --dip-dev-spend-lamports {dev_spend} exceeds --max-sol"); }
    let fast = fastfire::get();
    if live && fast.is_none() { bail!("--dip --live fires through the FAST path: add --fast-send"); }
    // every buy template (tip shape x size) built now, not at a fire
    if let Some(f) = fast {
        let sp: Vec<u64> = if dev_spend != spend && !devs.is_empty() { vec![spend, dev_spend] } else { vec![spend] };
        let t0 = Instant::now();
        let n = f.warm_templates(&sp);
        eprintln!("DIP FAST templates ready: {n} (sizes {:?} lamports) in {:.1} ms", sp, t0.elapsed().as_secs_f64() * 1e3);
    }
    // NONCE (--nonce-fanout; set up and self-tested in run()): the variant templates too
    let npool = if live { noncefan::get() } else { None };
    if let (Some(f), Some(np)) = (fast, npool) {
        let sp: Vec<u64> = if dev_spend != spend && !devs.is_empty() { vec![spend, dev_spend] } else { vec![spend] };
        let t0 = Instant::now();
        let n = f.warm_nonce_templates(&sp);
        eprintln!("DIP NONCE variant templates ready: {n} (sizes {:?} lamports) in {:.1} ms | {}", sp, t0.elapsed().as_secs_f64() * 1e3, np.line());
    }
    let me = b58(&user);
    eprintln!("\nDIP {} | model {} tier {tier} (score >= {thr:.4}) | exit {tp_s} / SL -{:.0}% / {hold} slots | guard x{guard} | spend {:.3} SOL | max buys {max_buys} | max open {max_inflight} | loss cap {} | {minutes} min",
        if live { "LIVE" } else { "SHADOW (no sends)" }, model.g.name, sl * 100.0, spend as f64 / 1e9,
        if live { format!("{:.3} SOL", loss_cap as f64 / 1e9) } else { "-".into() });
    if !devs.is_empty() { eprintln!("DIP dev list: {} wallet(s) -> their tokens: tier {dev_tier} (score >= {thr_dev:.4}), spend {:.3} SOL", devs.len(), dev_spend as f64 / 1e9); }
    let m2_extra = m2.is_some() && probe_n == 0 && match arg("--dip-m2-extra").as_deref() { None | Some("on") => true, Some("off") => false, Some(x) => bail!("--dip-m2-extra {x}: on | off") };
    if let Some(b) = &m2 {
        eprintln!("DIP M2 {}{} | M2 score >= {m2_min} | bundle {} | {}", if m2_extra { "(+ later big sells of a dump slot) " } else { "" }, if m2_gate { "GATE: the M2 score replaces the IMIT1 gate (dev-list tokens keep their IMIT1 tier)" }
            else { "SHADOW: trading stays IMIT1; every in-envelope dump is also scored, after the decision and any send" }, b.path, b.summary());
    }
    if let Some(ps) = &presend {
        let p = &ps.p;
        eprintln!("DIP PRESEND SHADOW (log only, never sends): T2 whale buy >= {}% of supply -> window {} slots from +{} ms, fill on a -{:.0}% drop vs the price {} ms \
                   before, {} SOL, exit {} slots / TP {} / SL {} | queue rows a/b/c = +0/+5/+10 ms | after the IMIT1 decision and any send of each tx",
            p.whale_pct, p.window_slots, p.live_ms, p.drop * 100.0, p.ref_ms, p.size_sol, p.exit_slots, if p.tp > 0.0 { format!("+{:.0}%", p.tp * 100.0) } else { "off".into() },
            if p.sl > 0.0 { format!("-{:.0}%", p.sl * 100.0) } else { "off".into() });
    }
    if let Some(c) = &shred_cfg {
        eprintln!("DIP SHRED FIRE {}: a dump first seen on a shred feed is priced on the token's book (pump's integer sell) and decided for every tx index it can have \
                   ({}); a pick for every index {} | records shred_dump / shred_parity", c.mode.as_str().to_uppercase(),
            match c.window { None => "exact: after the token's newest trade of the slot .. end of slot".to_string(), Some((m, w)) => format!("window: executed feed's progress - {m} .. + {w}") },
            if c.mode == arbx::dip_shred::Mode::Live { "FIRES now (the executed feed then confirms it, never a second buy)" } else { "is logged (shadow: nothing is sent)" });
    }
    if let Some(l) = &skip_clients { eprintln!("DIP SKIP CLIENTS: no buy when the dump slot's leader is {}", l.join(", ")); }
    if probe_n > 0 && (probe_clients.is_some() || probe_tipless) {
        eprintln!("DIP PROBE filters: clients {} | tipless twin {}", probe_clients.as_ref().map(|l| l.join(",")).unwrap_or_else(|| "any".into()), if probe_tipless { "ON" } else { "off" });
    }
    if defer { eprintln!("DIP DEFER: dump / pick records written after the sends; the route computed once per buy"); }
    if clock2 { eprintln!("DIP CLOCK2: timing records with block indexes, PoH position, real block size, entries arrival, per-feed arrivals"); }
    // dip16
    if probe_nonce != speed16::ProbeNonce::Off {
        eprintln!("DIP PROBE NONCE {}: probes built as a buy's durable-nonce variant (still min_out = MAX: they cannot fill){}", if probe_nonce == speed16::ProbeNonce::On { "ON" } else { "A/B" },
            if probe_nonce == speed16::ProbeNonce::Ab { format!(": blocks of {} probe(s) alternate blockhash / nonce, so every path gets both arms", probe_paths.len().max(1)) } else { String::new() });
    }
    if lock_only { eprintln!("DIP PROBE LOCK-ONLY: probes SUCCEED (a 0-lamport self-transfer write-locking the curve accounts; {lock_cu} CU): they land through revert-protected paths and PAY their tips"); }
    let mut rs = serde_json::json!({"ev": "run_start", "t": arbx::feeds::clock::now_ns(), "live": live, "wallet": me, "model": model.g.name, "tier": tier, "thr": thr, "tp": tp, "sl": sl,
        "hold_slots": hold, "guard": guard, "allow_holder": allow_holder, "spend": spend, "max_buys": max_buys, "max_inflight": max_inflight, "loss_cap": if live { loss_cap } else { 0 }, "minutes": minutes,
        "devs": devs.iter().collect::<Vec<_>>(), "dev_tier": dev_tier, "thr_dev": thr_dev, "dev_spend": dev_spend});
    if let Some(np) = npool { rs["nonce_accounts"] = serde_json::json!(np.keys.iter().map(b58).collect::<Vec<_>>()); }
    if let Some(b) = &m2 {
        rs["m2"] = serde_json::json!({"mode": if m2_gate { "gate" } else { "shadow" }, "min": m2_min, "extra": m2_extra, "bundle": b.path, "sha256": b.sha256, "model": b.model.name, "thr_default": b.thr_default});
    }
    if let Some(ps) = &presend { rs["presend"] = ps.p.json(); }
    if let Some(c) = &ps_live_cfg { rs["presend_live"] = c.json(); }
    // dip14: only when on (dip13's run_start is unchanged otherwise)
    if let Some(c) = &shred_cfg { rs["shred"] = c.json(); }
    if let Some(l) = &skip_clients { rs["skip_clients"] = serde_json::json!(l); }
    if probe_n > 0 && (probe_clients.is_some() || probe_tipless) { rs["probe_x"] = serde_json::json!({"clients": probe_clients, "tipless": probe_tipless, "paths": probe_paths}); }
    if defer { rs["defer"] = serde_json::json!(true); }
    if clock2 { rs["clock2"] = serde_json::json!(true); }
    if feed_lag { rs["feed_lag"] = serde_json::json!(true); }
    // dip16: only when one of its flags is on (dip15's run_start is unchanged otherwise)
    let d16 = (speed16::loaded_limit(), speed16::route_on(), wclock, probe_nonce != speed16::ProbeNonce::Off, lock_only);
    if d16.0.is_some() || d16.1 || d16.2 || d16.3 || d16.4 {
        rs["dip16"] = serde_json::json!({"loaded_data_limit": d16.0, "route_headers": d16.1, "window_clock": d16.2,
            "probe_nonce": format!("{probe_nonce:?}").to_lowercase(), "probe_lock_only": lock_only, "probe_lock_cu": if lock_only { Some(lock_cu) } else { None }});
    }
    log.w(rs);

    // feeds (the executed feed is the history; unexecuted feeds are ignored by the book)
    let interest = Arc::new(snipe::pump_interest());
    let (tx, rx) = crossbeam_channel::unbounded();
    let handle = tokio::runtime::Handle::current();
    // the feeds have their OWN stop: a signal stops new buys, but the exits of open positions need the feed's prices and
    // slots, so the feeds run until the loop below has closed every position
    let feed_stop = Arc::new(AtomicBool::new(false));
    let _feeds = arbx::feeds::start(&probe.feeds, interest, tx, feed_stop.clone(), &handle, &arbx::rec::Rec::off(), None).context("starting the feeds")?;
    set_slot_clock(rpc).await;
    if let Some(n) = &near { eprintln!("DIP near-leader gate: {} leaders (--dip-near-leaders)", n.len()); }
    if !probe_paths.is_empty() {
        let f = fast.ok_or_else(|| anyhow::anyhow!("--dip-probe-paths needs --fast-send"))?;
        for n in &probe_paths { if !f.fps.iter().any(|fp| &fp.path.name == n) { bail!("--dip-probe-paths: no send path named {n} in --config"); } }
        eprintln!("DIP probes rotate over {} path(s): {}", probe_paths.len(), probe_paths.join(", "));
    }
    // SIGTERM / SIGINT / SIGHUP = no new buys; open positions finish their exit, then the run ends (the snipe loop's drain
    // handler is not installed in this mode: without this, a signal killed the engine with a position open)
    {
        use tokio::signal::unix::{signal, SignalKind};
        let (mut term, mut int, mut hup) = (signal(SignalKind::terminate())?, signal(SignalKind::interrupt())?, signal(SignalKind::hangup())?);
        let st = stop.clone();
        tokio::spawn(async move {
            loop {
                let name = tokio::select! { _ = term.recv() => "SIGTERM", _ = int.recv() => "SIGINT", _ = hup.recv() => "SIGHUP" };
                eprintln!("  SIGNAL {name}: no new buys; open positions finish their exit, then the run ends");
                st.store(true, Ordering::SeqCst);
            }
        });
    }
    let (atx, mut arx) = tokio::sync::mpsc::unbounded_channel();
    // B2 (--dip-busy-poll, dip14): no bridge thread: the loop spins on the feed channel itself (its own thread: run() put it in
    // block_in_place); --pin-core C pins it (the runtime's threads then avoid core C)
    let busy = has("--dip-busy-poll");
    if busy {
        drop(atx);
        if let Some(c) = arg_u64_opt("--pin-core") { eprintln!("DIP BUSY-POLL: event loop pinned to core {c}: {}", arbx::fast::pin_to_core(c as usize)); }
        else { eprintln!("DIP BUSY-POLL: the event loop spins on the feed channel (one core)"); }
    } else { let rx = rx.clone(); std::thread::spawn(move || { while let Ok(ev) = rx.recv() { if atx.send(ev).is_err() { break; } } }); }
    let (mtx, mut mrx) = tokio::sync::mpsc::unbounded_channel::<Msg>();

    // balance kill switch (live): stop new buys when balance + open positions at cost < start - loss cap
    let start_bal = if live { native_balance(rpc, user).await.context("--dip --live: the start balance must be readable")? } else { 0 };
    if live {
        ACCT.bal.store(start_bal, Ordering::SeqCst);
        eprintln!("START BALANCE {:.6} SOL; kill switch below {:.6} SOL", start_bal as f64 / 1e9, start_bal.saturating_sub(loss_cap) as f64 / 1e9);
        let (rpc2, stop2, cap) = (rpc.clone(), stop.clone(), loss_cap as i64);
        tokio::spawn(async move {
            let mut st = KsState::default();
            loop {
                tokio::time::sleep(Duration::from_secs(2)).await;
                if stop2.load(Ordering::Relaxed) || DIP_NO_FIRE.load(Ordering::Relaxed) && ACCT.inflight.load(Ordering::SeqCst) == 0 { break; }
                let a = &*ACCT; let seq0 = a.seq.load(Ordering::SeqCst);
                let (open, pending, inflight, realized) = (a.open.load(Ordering::SeqCst), a.pending.load(Ordering::SeqCst), a.inflight.load(Ordering::SeqCst), a.realized.load(Ordering::SeqCst));
                let Ok(b) = native_balance_at(&rpc2, user, a.last_slot.load(Ordering::SeqCst)).await else { continue };
                ACCT.bal.store(b, Ordering::SeqCst);
                if a.seq.load(Ordering::SeqCst) != seq0 { continue; }
                let pnl = (b + open) as i64 - start_bal as i64;
                let (v, _) = ks_eval(&mut st, pnl, realized, pending, inflight, cap, &[]);
                if v == KsVerdict::Go { continue; }
                eprintln!("  DIP KILL-SWITCH: run PnL {:.6} SOL (balance {:.6} + open {:.6}) below -{:.6}: no new buys", pnl as f64 / 1e9, b as f64 / 1e9, open as f64 / 1e9, cap as f64 / 1e9);
                tg::raise(arbx::alerts::Level::Critical, "dip_kill", "kill", "🛑", "DIP KILL-SWITCH", arbx::alerts::format::Body::new().kv("run PnL", sol_str(pnl)).txt("no new buys; open positions finish their exit"), false);
                DIP_NO_FIRE.store(true, Ordering::SeqCst);
                break;
            }
        });
        let mut body = arbx::alerts::format::Body::new().kv("start balance", sol_str(start_bal as i64)).kv("loss cap", sol_str(loss_cap as i64)).kv("exit", format!("{tp_s} / SL -{:.0}% / {hold} slots", sl * 100.0));
        if !devs.is_empty() { body = body.kv("dev list", format!("{} wallet(s): {dev_tier}, {:.2} SOL", devs.len(), dev_spend as f64 / 1e9)); }
        tg::raise(arbx::alerts::Level::Info, "dip_start", "start", "🚀", &format!("DIP RUN START ({tier}, {:.2} SOL, max {max_buys} buys)", spend as f64 / 1e9), body, false);
    }

    let deadline = Instant::now() + Duration::from_secs(minutes * 60);
    let mut toks: HashMap<Pk, Tok> = HashMap::new();
    // M2 (--dip-m2): one M2 state per followed token (made at its create, as the IMIT1 book), and the counters
    let mut m2toks: HashMap<Pk, arbx::dip_model::Tok> = HashMap::new();
    let mut m2st = M2Stats::default();
    let mut open: HashMap<Pk, LivePos> = HashMap::new();
    let (mut n_dumps, mut n_env, mut n_picks, mut n_fired, mut n_closed, mut skipped) = (0u64, 0u64, 0u64, 0u64, 0u64, HashMap::<&'static str, u64>::new());
    let mut last_status = Instant::now();
    let mut slot_now = 0u64;
    let key_arc = Arc::new(key.clone());
    // PRE-SEND LIVE: the sender + writer threads, the feed's failed-tx side channel for our wallet
    let mut pslive: Option<pslive::PsLive> = match ps_live_cfg {
        Some(c) => Some(pslive::PsLive::start(c, key_arc.clone(), user, rpc, path, &log, mtx.clone(), allow_holder, &cohort)?),
        None => None,
    };
    let ss = |_s: u64| -> Option<u64> { None };           // block sizes are unknown live (parity: 1 of 55 picks flips)
    // ---- dip14 state (all idle without the flags)
    let mut shred = shred_cfg.map(shredfire::ShredFire::new);
    // the shred decision scores M2 only when M2 is the gate (B2: M2 SHADOW scoring stays after the sends, in the executed path)
    let gates = shredfire::Gates { model: &model, cohort: &cohort, targets: &targets, max_age_s, thr, thr_dev, m2: if m2_gate { m2.as_ref() } else { None }, m2_gate, m2_min, m2_extra };
    let held = Held { on: defer, v: std::cell::RefCell::new(Vec::new()) };
    // D1 (--dip-clock2): every feed's own arrival of each tx (sig8 -> per feed ns, 0 = not seen), the executed feed's block index
    // of each tx (sig8 -> slot, index), our failed txs' indexes (the executed feed's side channel)
    let mut feed_seen: rustc_hash::FxHashMap<u64, [u64; 8]> = Default::default();
    let mut exec_idx: rustc_hash::FxHashMap<u64, (u64, u64)> = Default::default();
    let mut own_idx: rustc_hash::FxHashMap<u64, (u64, u64)> = Default::default();
    if clock2 { arbx::feeds::own_fail_watch(user); }
    // B3 (--dip-feed-lag): executed-feed lag behind the first shred sighting of every pump tx (ns, by the first feed), the event
    // loop's queue on executed arrivals (ns), this minute
    let mut lag_all: Vec<u64> = Vec::new();
    let mut lag_by: HashMap<u16, Vec<u64>> = HashMap::new();
    let mut q_exec: Vec<u64> = Vec::new();
    loop {
        let stopping = Instant::now() >= deadline || stop.load(Ordering::Relaxed) || DIP_NO_FIRE.load(Ordering::Relaxed)
            || (max_buys > 0 && ACCT.landed_buys.load(Ordering::SeqCst) >= max_buys)
            || probe_done_at.is_some_and(|t| t.elapsed() > Duration::from_secs(5));
        // PRE-SEND LIVE: its positions finish their exit and its attempts resolve before the run ends
        if stopping && open.is_empty() && pslive.as_ref().is_none_or(|p| p.can_end(PS_END_GRACE)) {
            if let Some(p) = pslive.as_ref().filter(|p| !p.idle()) {
                eprintln!("  PRESEND LIVE: run end {} s after the stop with state left: {} (finish() resolves the attempts as unseen)", PS_END_GRACE.as_secs(), p.not_idle_why());
            }
            break;
        }
        if stopping && !DIP_NO_FIRE.swap(true, Ordering::SeqCst) { eprintln!("  DIP: no new buys from here (end of run reached); {} position(s) finishing", open.len()); }
        if stopping { if let Some(p) = pslive.as_mut() { p.stop("run_stopping"); } }
        // positions + feed, whichever first
        let ev = if busy {
            // B2 (--dip-busy-poll): the positions' messages first, then the feed channel (spun 1 ms at a time; 500 ms quiet = the timeout)
            let t_wait = Instant::now();
            let (mut got, mut msg, mut closed) = (None, None, false);
            loop {
                if let Ok(m) = mrx.try_recv() { msg = Some(m); break; }
                match fastfire::spin_recv(&rx, Duration::from_millis(1)) {
                    Ok(Some(e)) => { got = Some(e); break; }
                    Ok(None) => { if t_wait.elapsed() >= Duration::from_millis(500) { break; } }
                    Err(()) => { closed = true; break; }
                }
            }
            if let Some(m) = msg {
                match m { Msg::Ps(m) => { if let Some(p) = pslive.as_mut() { p.on_msg(m, &|k| open.contains_key(k)); } } m => on_msg(m, &mut open, &log, &mut n_closed, rpc) }
                continue;
            }
            if closed {
                if open.is_empty() && pslive.as_ref().is_none_or(|p| p.can_end(PS_END_GRACE)) { break; }
                tokio::time::sleep(Duration::from_millis(200)).await;
            }
            match got {
                Some(e) => e,
                None => {
                    time_exits(&mut open, slot_now, hold, &log, &key_arc, user, rpc, path, &mtx);
                    if let Some(p) = pslive.as_mut() { p.reactive_open(open.len()); p.tick(slot_now, Some(&first_seen)); }
                    continue;
                }
            }
        } else { tokio::select! {
            m = mrx.recv() => {
                match m {
                    Some(Msg::Ps(m)) => { if let Some(p) = pslive.as_mut() { p.on_msg(m, &|k| open.contains_key(k)); } }
                    Some(m) => on_msg(m, &mut open, &log, &mut n_closed, rpc),
                    None => {}
                }
                continue;
            }
            e = tokio::time::timeout(Duration::from_millis(500), arx.recv()) => match e {
                Ok(Some(e)) => e,
                // every feed died: never leave a position behind; the wall-clock backstop in time_exits sells it
                Ok(None) => {
                    if open.is_empty() && pslive.as_ref().is_none_or(|p| p.can_end(PS_END_GRACE)) { break; }
                    tokio::time::sleep(Duration::from_millis(200)).await;
                    time_exits(&mut open, slot_now, hold, &log, &key_arc, user, rpc, path, &mtx);
                    if let Some(p) = pslive.as_mut() { p.reactive_open(open.len()); p.tick(slot_now, Some(&first_seen)); }
                    continue;
                }
                Err(_) => {
                    time_exits(&mut open, slot_now, hold, &log, &key_arc, user, rpc, path, &mtx);
                    if let Some(p) = pslive.as_mut() { p.reactive_open(open.len()); p.tick(slot_now, Some(&first_seen)); }
                    continue
                }
            },
        } };
        if last_status.elapsed() > Duration::from_secs(60) {
            last_status = Instant::now();
            eprintln!("  DIP status: tokens {} dumps {n_dumps} in-envelope {n_env} picks {n_picks} fired {n_fired} closed {n_closed} open {} slot {slot_now} skipped {:?}{}{}{}{}", toks.len(), open.len(), skipped,
                npool.map(|np| format!(" | {}", np.line())).unwrap_or_default(), if m2.is_some() { m2st.line(m2_gate) } else { String::new() },
                presend.as_ref().map(|p| format!("{}{}", p.line(), ps_time.line())).unwrap_or_default(), pslive.as_mut().map(|p| p.status()).unwrap_or_default());
            let cutoff = Duration::from_secs_f64(max_age_s + 300.0);
            toks.retain(|m, t| t.t_created.elapsed() < cutoff || open.contains_key(m));
            if m2.is_some() { m2toks.retain(|m, _| toks.contains_key(m)); }
            // dip14
            if let Some(sf) = shred.as_ref() { eprintln!("  DIP SHRED{}", sf.line()); }
            if clock2 && own_idx.len() > 20_000 { own_idx.clear(); }
            if feed_lag { log.w(feed_lag_rec(&mut lag_all, &mut lag_by, &mut q_exec, &feed_names, &_feeds)); }
        }
        let arbx::feeds::Event::Tx(a) = ev else { continue };
        let t_loop = arbx::feeds::clock::now_ns();     // the decision-time breakdown of a fire (lat_us in the fire record)
        {
            let k8 = u64::from_be_bytes(a.tx.sig[..8].try_into().unwrap());
            if let std::collections::hash_map::Entry::Vacant(v) = first_seen.entry(k8) { v.insert((a.t_rx, a.feed)); first_order.push_back((a.t_rx, k8)); }
            while first_order.front().is_some_and(|&(t, _)| a.t_rx.saturating_sub(t) > 30_000_000_000) {
                let (_, k) = first_order.pop_front().unwrap();
                first_seen.remove(&k);
                if clock2 { feed_seen.remove(&k); exec_idx.remove(&k); }
            }
            // D1 (--dip-clock2): this feed's own arrival; the executed feed's block index
            if clock2 {
                let e = feed_seen.entry(k8).or_insert([0u64; 8]);
                if (a.feed as usize) < 8 && e[a.feed as usize] == 0 { e[a.feed as usize] = a.t_rx; }
                if let Some(x) = a.exec.as_ref() { exec_idx.entry(k8).or_insert((a.slot, x.index)); }
            }
            // B3 (--dip-feed-lag): the executed feed's lag behind the tx's first sighting on another feed
            if feed_lag && a.executed.is_some() {
                if let Some(&(t0, f0)) = first_seen.get(&k8) { if f0 != a.feed { let l = a.t_rx.saturating_sub(t0); lag_all.push(l); lag_by.entry(f0).or_default().push(l); } }
                q_exec.push(t_loop.saturating_sub(a.t_rx));
            }
        }
        if !pend.is_empty() && last_pend_check.elapsed() > Duration::from_millis(500) {
            last_pend_check = Instant::now();
            let now_i = Instant::now();
            pend.retain(|p| { if p.due > now_i { return true; }
                log.w(if clock2 { timing_rec2(p, &first_seen, &feed_names, &feed_seen, &exec_idx, &own_idx) } else { timing_rec(p, &first_seen, &feed_names) }); false });
        }
        slot_now = slot_now.max(a.slot);
        // our own buy failed on chain (no TradeEvent, so no exec info): the executed feed says so first
        if a.executed == Some(false) && !probe_sigs.is_empty() {
            if let Some((mint_s, t_dump)) = probe_sigs.remove(&a.tx.sig) {
                let mut j = serde_json::json!({"ev": "probe_land", "mint": mint_s, "sig": bs58::encode(&a.tx.sig).into_string(), "slot": a.slot, "t": a.t_rx,
                    "ms_after_dump_feed": (a.t_rx as i64 - t_dump as i64) as f64 / 1e6});
                // D1 (--dip-clock2): its block index (the executed feed's failed-tx side channel) and error
                if clock2 {
                    if let Some(of) = arbx::feeds::own_fail_take(&a.tx.sig) {
                        own_idx.insert(u64::from_be_bytes(a.tx.sig[..8].try_into().unwrap()), (of.slot, of.index));
                        j["idx"] = serde_json::json!(of.index); j["err"] = serde_json::json!(of.err); j["fee"] = serde_json::json!(of.fee);
                    }
                }
                log.w(j);
            }
        }
        // dip16 C5 (--dip-probe-lock-only on): a lock-only probe SUCCEEDS and emits no pump event (so no exec info): the executed feed's
        // success is its landing
        if lock_only && a.executed == Some(true) && a.exec.is_none() && !probe_sigs.is_empty() {
            if let Some((mint_s, t_dump)) = probe_sigs.remove(&a.tx.sig) {
                log.w(serde_json::json!({"ev": "probe_land", "mint": mint_s, "sig": bs58::encode(&a.tx.sig).into_string(), "slot": a.slot, "t": a.t_rx,
                    "ms_after_dump_feed": (a.t_rx as i64 - t_dump as i64) as f64 / 1e6, "ok": true, "lock_only": true}));
            }
        }
        // D1 (--dip-clock2): our failed buys' block index (kept for their timing records)
        if clock2 && a.executed == Some(false) && a.exec.is_none() && open.values().any(|p| p.ours(&a.tx.sig)) {
            if let Some(of) = arbx::feeds::own_fail_take(&a.tx.sig) { own_idx.insert(u64::from_be_bytes(a.tx.sig[..8].try_into().unwrap()), (of.slot, of.index)); }
        }
        if a.executed == Some(false) && a.exec.is_none() {
            // NONCE: any of the buy's variants (the failed one is THE buy: its fee was paid, its tip reverted)
            if let Some(p) = open.values_mut().find(|p| p.ours(&a.tx.sig) && p.buy_ok.is_none()) {
                p.buy_ok = Some(false);
                let var = p.adopt(&a.tx.sig);
                log.w(with_var(serde_json::json!({"ev": "buy_failed", "mint": b58(&p.mint), "sig": p.buy_sig, "slot": a.slot, "t": a.t_rx}), var));
            }
        }
        // PRE-SEND LIVE: our failed attempts (no pump event, so no ExecInfo) and the feed's slot for the sender
        if let Some(p) = pslive.as_mut() { p.on_arrival(&a, slot_now); }
        // SHRED FIRE (dip14): an executed arrival confirms its tx (no longer pending on its tokens); a shred arrival is classified once
        // and its dump decided for every tx index; a pick fires here (live) or is logged (shadow), with the executed path's checks
        if shred.is_some() {
            let sf = shred.as_mut().unwrap();
            sf.tick(t_loop, &log);
            if a.executed.is_some() { sf.on_exec_arrival(&a, &log); }
            else {
                let (picks, decided) = sf.on_shred(&a, &mut toks, &mut m2toks, &gates);
                for pk in picks {
                    let (what, fired, min_out_s) = shred_pick(&pk, &a, t_loop, pk.t_dec, &mut toks, &mut open, &mut pend, &mut n_fired, ShredCtx {
                        live: sf.cfg.mode == arbx::dip_shred::Mode::Live && live, spacing, allow_holder, guard, spend, dev_spend, near: near.as_ref(),
                        skip_clients: skip_clients.as_deref(), max_inflight, pslive: pslive.as_ref(), npool, fast, user, rpc, path, mtx: &mtx, log: &log, names: &feed_names });
                    sf.set_what(pk.sig8, what, fired, min_out_s);
                }
                // the decision's record, after any send
                if decided { if let Some(r) = sf.dump_rec(arbx::dip_shred::sig8(&a.tx.sig), &feed_names) { log.w(r); } }
            }
        }
        let Some(x) = a.exec.clone() else { time_exits(&mut open, slot_now, hold, &log, &key_arc, user, rpc, path, &mtx); continue };
        if !x.ok { continue; }
        let sig = bs58::encode(&a.tx.sig).into_string();
        // launches
        for c in &x.creates {
            let mint = c.mint;
            if toks.contains_key(&mint) { continue; }
            let launch = snipe::detect_launch(&a.tx).filter(|l| l.mint == mint);
            let (cr_s, us_s) = (b58(&c.creator), b58(&c.user));
            let dev = !devs.is_empty() && (devs.contains(&cr_s) || devs.contains(&us_s));
            let li = LaunchInfo { slot: a.slot, idx: Some(x.index as u32), creator: Some(cr_s), signer: Some(us_s), sig: sig.clone(), mayhem: x.mayhem };
            // B2 (--dip-defer): the buy's two ATA derivations now (off any decision), not at the buy
            let keys = match (defer, launch.as_ref(), fast) { (true, Some(l), Some(f)) => Some(f.var_keys(l)), _ => None };
            toks.insert(mint, Tok { book: TokenBook::new(li), launch, t_created: Instant::now(), last_pick_slot: None, dev, keys });
            if m2.is_some() { m2toks.insert(mint, arbx::dip_model::Tok::new(a.slot)); }
        }
        // trades
        for (j, e) in x.trades.iter().enumerate() {
            // B2 (--dip-defer): the previous trade's held records (a no-op without the flag)
            held.flush(&log);
            // PRE-SEND SHADOW: the dip counters before this trade (what the reactive bot did on it goes into the shadow's records)
            if presend.is_some() { ps_marks.push([n_dumps, n_env, n_picks, n_fired, m2st.picks]); }
            let user_s = b58(&e.user);
            // our own trades: buy landed / sell landed
            if e.user == user {
                if let Some(p) = open.get_mut(&e.mint) {
                    if e.buy && p.land.is_none() {
                        // NONCE: the variant that landed is THE buy (its signature for the realized PnL, its one tip as the tips paid)
                        let var = p.adopt(&a.tx.sig);
                        p.land = Some((a.slot, x.index, a.t_rx)); p.tokens = e.tok; p.sol_in = e.sol; p.buy_ok = Some(true);
                        let cost = p.spend + x.fee + p.tips;
                        if let Some(pos) = p.pos.as_mut() { pos.landed(cost, a.slot); }
                        log.w(with_var(serde_json::json!({"ev": "buy_land", "mint": b58(&e.mint), "sig": sig, "slot": a.slot, "idx": x.index, "t": a.t_rx, "tokens": e.tok, "sol": e.sol,
                            "fee": x.fee, "slots_after_dump": a.slot as i64 - p.dump_slot as i64, "rx_ms_after_dump": (a.t_rx as i64 - p.t_dump_rx as i64) as f64 / 1e6,
                            "vsol": e.vsol, "vtok": e.vtok}), var));
                    } else if !e.buy {
                        p.sell_land = Some((a.slot, x.index, a.t_rx, e.sol));
                        log.w(serde_json::json!({"ev": "sell_land", "mint": b58(&e.mint), "sig": sig, "slot": a.slot, "idx": x.index, "t": a.t_rx, "sol": e.sol, "fee": x.fee}));
                    }
                }
            }
            // the tape of a token we hold (who bought / sold around us: the run report's bots before / after)
            if open.contains_key(&e.mint) {
                log.w(serde_json::json!({"ev": "tape", "mint": b58(&e.mint), "sig": sig, "slot": a.slot, "idx": x.index, "j": j, "t": a.t_rx, "user": b58(&e.user),
                    "buy": e.buy, "sol": e.sol, "tok": e.tok, "vsol": e.vsol, "vtok": e.vtok}));
            }
            let Some(tk) = toks.get_mut(&e.mint) else { continue };
            let t = T { s: a.slot, i: x.index as u32, j: j as i32, sig: sig.clone(), user: user_s, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok,
                        fbps: e.fbps as u32, cbps: e.cbps as u32, syn: false };
            let dump_k = tk.book.push(t, &targets, max_age_s, &ss);
            // M2: this trade for the M2 state (a non-dump trade is applied after the exit check below, a dump trade by M2Dump)
            let m2t = m2.as_ref().map(|_| arbx::dip_model::Tr { s: a.slot, i: x.index as u32, j: j as i32, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok, user: e.user });
            // exits on this token's newest price
            if let Some(p) = open.get_mut(&e.mint) {
                if p.land.is_some() && p.exit.is_none() && e.user != user {
                    let fr = (e.fbps + e.cbps).max(1) as f64 / 1e4;
                    let so = di_sell_out(e.vsol, e.vtok, p.tokens) as f64 * (1.0 - fr) / 1e9;
                    let val = (so - TXC) / (p.spend as f64 / 1e9 + TXC);
                    let why = if val >= 1.0 + tp { Some("take-profit") } else if val <= 1.0 - sl { Some("stop-loss") } else { None };
                    if let Some(why) = why { trigger_exit(p, why, a.slot, val, a.t_rx, &log, &key_arc, user, rpc, path, &mtx); }
                }
            }
            // M2 extra dump: a big sell the IMIT1 rules skip only because an earlier big sell of this slot was the dump event
            let extra_k = match (dump_k, m2t.as_ref()) { (None, Some(t2)) if m2_extra && !e.buy && e.sol >= arbx::dip::MIN_SELL => tk.book.later_in_slot((t2.s, t2.i, t2.j), max_age_s), _ => None };
            if let (None, None, Some(t2), Some(b)) = (dump_k, extra_k, m2t.as_ref(), m2.as_ref()) { if let Some(mt) = m2toks.get_mut(&e.mint) { mt.push(t2, &b.sets); } }
            let Some(k) = dump_k.or(extra_k) else { continue };
            n_dumps += 1;
            let t_d0 = arbx::feeds::clock::now_ns();
            let d = tk.book.dump(&b58(&e.mint), k, &model, &cohort, &ss);
            let t_d1 = arbx::feeds::clock::now_ns();
            // M2 at this dump: gate = the dump trade enters the M2 state and (in the envelope) is scored NOW, before the decision;
            // shadow = when this trade's iteration ends (M2Dump's drop), i.e. after the IMIT1 decision and any send
            let mut m2d = match (m2.as_ref(), m2t) {
                (Some(b), Some(t2)) => Some(M2Dump::new(b, m2toks.get_mut(&e.mint), t2, d.env_ok, m2_gate, m2_min, extra_k.is_some(), &log, &mut m2st).held(defer.then_some(&held))),
                _ => None,
            };
            if !d.env_ok {
                // SHRED FIRE (dip14): the executed decision (no pick: out of the envelope) for the parity record
                if let Some(sf) = shred.as_mut() { sf.exec_dump(&a.tx.sig, &e.mint, &tk.book.tr[k], x.index, false, a.t_rx, &log); }
                continue;
            }
            n_env += 1;
            let (thr_t, spend_p) = if tk.dev { (thr_dev, dev_spend) } else { (thr, spend) };
            let pass = d.launch_ok && d.score >= thr_t;
            // M2 gate: the M2 score decides for tokens off the dev list (dev-list tokens keep their IMIT1 tier: PORT.md); IMIT1 never
            // picks an M2 extra dump (it is no IMIT1 dump event)
            let pass = match m2d.as_ref() { Some(g) if g.gate && !tk.dev => d.launch_ok && g.pick(), _ => pass && extra_k.is_none() };
            // SHRED FIRE (dip14): the parity record of a dump decided on its shred sighting; one already bought then is not bought again
            let shred_fired = match shred.as_mut() { Some(sf) => sf.exec_dump(&a.tx.sig, &e.mint, &tk.book.tr[k], x.index, pass, a.t_rx, &log), None => false };
            if shred_fired { if let Some(p) = open.get_mut(&e.mint) { if p.dump_idx == u64::MAX && p.dump_sig == sig { p.dump_idx = x.index; } } }
            let tr = &tk.book.tr[k];
            let dump_rec = serde_json::json!({"ev": "dump", "mint": b58(&e.mint), "sig": sig, "slot": a.slot, "idx": x.index, "t": a.t_rx, "age": d.age, "sell": d.feats[1],
                "drop_pct": d.feats[2], "score": d.score, "thr": thr_t, "pass": pass, "launch_ok": d.launch_ok, "vsol": tr.vsol, "vtok": tr.vtok, "dev": tk.dev});
            match m2d.as_mut() {
                Some(g) => g.record(dump_rec, d.launch_ok && d.score >= thr_t && extra_k.is_none(), d.score, d.age, d.feats[1], d.feats[2], d.launch_ok, tk.dev),
                None => held.w(&log, dump_rec),
            }
            if probe_n > 0 {
                held.flush(&log);
                if live && probes_fired < probe_n && d.launch_ok && last_probe.is_none_or(|t| t.elapsed() >= probe_gap) && !DIP_NO_FIRE.load(Ordering::Relaxed) {
                    let ok_kind = tk.launch.as_ref().is_some_and(|l| l.is_create_v2 && (l.is_vanilla() || (allow_holder && l.is_holder_reward && !l.is_mayhem && !l.is_cashback && l.creator_fee_bps == 0)));
                    let lead_ok = near.as_ref().is_none_or(|n| n.contains(&lat::buy_paths(path, ALSO_PATH.get(), Some(a.slot)).1.leader));
                    // dip14: --dip-probe-clients = only on these leader clients (e.g. only Jito, only Harmonic)
                    let client_ok = probe_clients.as_ref().is_none_or(|l| shredfire::client_in(l, &lat::buy_paths(path, ALSO_PATH.get(), Some(a.slot)).1.client));
                    if let (true, true, true, Some(launch), Some(f)) = (ok_kind, lead_ok, client_ok, tk.launch.clone(), fast) {
                        let t0 = arbx::feeds::clock::now_ns();
                        let cr = [a.t_rx, a.t_decoded, t0, t0, t0, t0];
                        let force = if probe_paths.is_empty() { None } else {
                            let name = &probe_paths[(probes_fired as usize) % probe_paths.len()];
                            f.fps.iter().find(|fp| &fp.path.name == name).map(|fp| vec![fp.path.clone()])
                        };
                        let force2 = if probe_tipless { force.clone() } else { None };
                        // dip16 B4 (--dip-probe-nonce on|ab): this probe's arm; on the nonce arm a READY nonce of the pool -> the probe is a
                        // buy's durable-nonce variant on the same route (still min_out = MAX). Off (dip15): never
                        let arm = probe_nonce.arm(probes_fired, probe_paths.len());
                        let lease = if arm { npool.and_then(|np| np.take()) } else { None };
                        let mut nonce_fb: Option<String> = if arm && lease.is_none() { Some("no nonce account ready".into()) } else { None };
                        let nprep = match &lease {
                            Some(l) => {
                                let (mut fan, mut meta) = lat::buy_paths(path, ALSO_PATH.get(), Some(a.slot));
                                if let Some(v) = force.clone().filter(|v| !v.is_empty()) {
                                    meta.route = format!("forced:{}", v.iter().map(|p| p.name.as_str()).collect::<Vec<_>>().join("+"));
                                    fan = v;
                                }
                                meta.route.push_str(":nonce");
                                match f.prepare_nonce_route(&launch, a.slot, u64::MAX, cr, None, (l.key, l.value), fan, meta, tk.keys) { Ok(p) => Some(p), Err(err) => { nonce_fb = Some(format!("{err:#}")); None } }
                            }
                            None => None,
                        };
                        if nprep.is_none() { if let (Some(np), Some(l)) = (npool, lease.as_ref()) { np.give_back(l); } }
                        // dip16 C5 (--dip-probe-lock-only on): a lock-only probe (succeeds; write-locks the curve accounts); else dip15's
                        let prep_r = match nprep {
                            Some(p) => Ok(p),
                            None if lock_only => f.prepare_lock_probe(&launch, a.slot, cr, force, lock_cu, false),
                            None => f.prepare_on(&launch, a.slot, u64::MAX, cr, force, None),
                        };
                        match prep_r {
                            Ok(mut prep) => {
                                let rec = f.fire(&mut prep);
                                let t_fire = arbx::feeds::clock::now_ns();
                                // D3 (--dip-probe-tipless on): the same can't-fill buy WITHOUT any tip through the same one path, right after
                                // (dip16 C5: the same lock-only probe without its tip)
                                let twin = if probe_tipless {
                                    match if lock_only { f.prepare_lock_probe(&launch, a.slot, cr, force2, lock_cu, true) } else { f.prepare_on_x(&launch, a.slot, u64::MAX, cr, force2, None, true) } {
                                        Ok(mut p2) => { let r2 = f.fire(&mut p2); Some(Ok((p2, r2, arbx::feeds::clock::now_ns()))) }
                                        Err(err) => Some(Err(format!("{err:#}"))),
                                    }
                                } else { None };
                                // B4: a nonce probe's account is out of rotation until its value changes, as a buy's
                                if let (Some(np), Some(l)) = (npool, lease.as_ref()) { if prep.nonce.is_some() { np.fired(l, prep.deadline); } }
                                probes_fired += 1; last_probe = Some(Instant::now());
                                if probes_fired >= probe_n { probe_done_at = Some(Instant::now()); }
                                probe_sigs.insert(prep.sig, (b58(&e.mint), a.t_rx));
                                // B4: a nonce probe's other variants (one per tip family of an unforced route; at most one can land)
                                let more: Vec<[u8; 64]> = prep.variants().into_iter().map(|v| v.1).filter(|s| *s != prep.sig).collect();
                                for s in &more { probe_sigs.insert(*s, (b58(&e.mint), a.t_rx)); }
                                // C4 (--window-clock): the dump's window clock at the decision and first write; C3 (--log-route-headers): the write tag
                                let t_first = first_seen.get(&u64::from_be_bytes(a.tx.sig[..8].try_into().unwrap())).map(|x| x.0);
                                let win = wclock.then(|| speed16::window_json(a.slot, t_first, a.t_rx, Some(t0), speed16::first_write_rt(&rec.w), &feed_names));
                                let tag = if speed16::route_on() { prep.id } else { 0 };
                                pend.push(Pend { kind: "probe", mint: b58(&e.mint), buy_sig: prep.meta.sig.clone(), dump_sig_b: a.tx.sig, buy_sig_b: prep.sig, t_dump_rx: a.t_rx, t_fire,
                                                 due: Instant::now() + Duration::from_secs(2), more, via: "", win: win.clone(), tag });
                                let mut pj = serde_json::json!({"ev": "probe", "n": probes_fired, "mint": b58(&e.mint), "dump_sig": sig, "slot": a.slot, "idx": x.index, "t_dump_rx": a.t_rx,
                                    "t_fire": t_fire, "decision_us": (t_fire as i64 - a.t_rx as i64) as f64 / 1e3, "buy_sig": prep.meta.sig, "route": prep.meta.route,
                                    "leader": prep.meta.leader, "client": prep.meta.client, "tips": prep.meta.tips, "score": d.score, "deadline": prep.deadline,
                                    "writes": rec.w.iter().map(|(n, k, a0, a1, st)| serde_json::json!({"path": n, "kind": k, "t0": a0, "t1": a1, "st": st})).collect::<Vec<_>>()});
                                // the fast path's tag (its FAST-ACK lines in the .log carry it: the relay's answer per copy), with --dip-clock2 (dip16: or C3)
                                if clock2 || tag != 0 { pj["tag"] = serde_json::json!(prep.id); }
                                // dip16 (each only with its flag)
                                if let Some(w) = &win { pj["win"] = w.clone(); }
                                if probe_nonce != speed16::ProbeNonce::Off {
                                    pj["nonce_arm"] = serde_json::json!(if prep.nonce.is_some() { "nonce" } else { "blockhash" });
                                    if let Some(n) = &prep.nonce {
                                        pj["nonce"] = serde_json::json!({"acct": b58(&n.acct), "value": b58(&n.value), "variants": prep.variants().iter().map(|v| serde_json::json!({"sig": v.0, "tip": v.2, "paths": v.4})).collect::<Vec<_>>()});
                                    }
                                    if let Some(why) = &nonce_fb { pj["nonce_fallback"] = serde_json::json!(why); }
                                }
                                if lock_only { pj["lock_only"] = serde_json::json!({"cu": lock_cu}); }
                                match twin {
                                    Some(Ok((p2, r2, t2))) => {
                                        if clock2 || tag != 0 { pj["tipless_tag"] = serde_json::json!(p2.id); }
                                        probe_sigs.insert(p2.sig, (b58(&e.mint), a.t_rx));
                                        let win2 = wclock.then(|| speed16::window_json(a.slot, t_first, a.t_rx, Some(t0), speed16::first_write_rt(&r2.w), &feed_names));
                                        pend.push(Pend { kind: "probe_tipless", mint: b58(&e.mint), buy_sig: p2.meta.sig.clone(), dump_sig_b: a.tx.sig, buy_sig_b: p2.sig, t_dump_rx: a.t_rx,
                                                         t_fire: t2, due: Instant::now() + Duration::from_secs(2), more: Vec::new(), via: "", win: win2, tag: if tag != 0 { p2.id } else { 0 } });
                                        pj["tipless"] = serde_json::json!({"buy_sig": p2.meta.sig, "tips": p2.meta.tips, "t_fire": t2, "route": p2.meta.route,
                                            "writes": r2.w.iter().map(|(n, k, a0, a1, st)| serde_json::json!({"path": n, "kind": k, "t0": a0, "t1": a1, "st": st})).collect::<Vec<_>>()});
                                    }
                                    Some(Err(e2)) => { pj["tipless"] = serde_json::json!({"error": e2}); }
                                    None => {}
                                }
                                log.w(pj);
                                eprintln!("  DIP PROBE #{probes_fired} {} | route {} leader {} ({}) | {}{}{}", b58(&e.mint), prep.meta.route, &prep.meta.leader[..8.min(prep.meta.leader.len())], prep.meta.client,
                                    prep.meta.sig, if probe_tipless { " + tipless twin" } else { "" }, match (&prep.nonce, &nonce_fb) { (Some(n), _) => format!(" | nonce {}", &b58(&n.acct)[..8]), (None, Some(w)) => format!(" | NONCE-FALLBACK: {w}"), _ => String::new() });
                            }
                            Err(err) => eprintln!("  DIP probe prepare {} failed: {err:#}", b58(&e.mint)),
                        }
                    }
                }
                continue;
            }
            if !pass { continue; }
            n_picks += 1;
            // the launch kind (create_v2 flags) goes with every pick / skip: the run report splits results by it
            let kind = tk.launch.as_ref().map(|l| serde_json::json!({"v2": l.is_create_v2, "mayhem": l.is_mayhem, "cashback": l.is_cashback, "holder": l.is_holder_reward, "cfee_bps": l.creator_fee_bps}));
            let skip = |why: &'static str, sk: &mut HashMap<&'static str, u64>| { *sk.entry(why).or_default() += 1; held.w(&log, serde_json::json!({"ev": "pick_skip", "mint": b58(&e.mint), "sig": sig, "why": why, "kind": kind})); };
            if shred_fired { skip("shred_fired", &mut skipped); continue; }
            if tk.last_pick_slot.is_some_and(|s| a.slot < s + spacing) { skip("spacing", &mut skipped); continue; }
            tk.last_pick_slot = Some(a.slot);
            let Some(launch) = tk.launch.clone() else { skip("no_launch_accounts", &mut skipped); continue };
            // our buy / sell build the TOKEN-2022 accounts of a create_v2 token: a legacy `create` (SPL Token) would fail on chain
            if !launch.is_create_v2 { skip("legacy_create", &mut skipped); continue; }
            // vanilla only until the sell is verified on each kind; mayhem never passes the study's launch filter anyway.
            // --dip-allow-holder: holder-reward tokens too (10-24: --sim-roundtrip buy+sell as our wallet OK on 2 of them, same
            // Token-2022 extensions as vanilla; ~half of all picks). Cashback / creator-fee tokens stay skipped (unverified).
            let holder_ok = allow_holder && launch.is_holder_reward && !launch.is_mayhem && !launch.is_cashback && launch.creator_fee_bps == 0;
            if !launch.is_vanilla() && !holder_ok { skip("non_vanilla", &mut skipped); continue; }
            // the guard: tokens our spend buys on the post-dump curve, divided by --dip-guard
            let fr = (tr.fbps + tr.cbps).max(1) as f64 / 1e4;
            let xin = (spend_p as f64 / (1.0 + fr)) as u128;
            let q = (tr.vtok as u128 * xin / (tr.vsol as u128 + xin)) as f64;
            let min_out = ((q / guard).floor() as u64).max(1);
            let (fan, meta) = lat::buy_paths(path, ALSO_PATH.get(), Some(a.slot));
            if near.as_ref().is_some_and(|n| !n.contains(&meta.leader)) { skip("far_leader", &mut skipped); continue; }
            // C1 (--dip-skip-clients, dip14): never on these leader clients
            if skip_clients.as_ref().is_some_and(|l| shredfire::client_in(l, &meta.client)) { skip("skip_client", &mut skipped); continue; }
            let mut pick_j = serde_json::json!({"ev": "pick", "mint": b58(&e.mint), "sig": sig, "slot": a.slot, "idx": x.index, "t": a.t_rx, "score": d.score, "age": d.age,
                "min_out": min_out, "route": meta.route, "leader": meta.leader, "client": meta.client, "paths": fan.iter().map(|p| p.name.clone()).collect::<Vec<_>>(),
                "kind": kind, "feats": d.feats.to_vec(), "dev": tk.dev, "spend": spend_p});
            // dip16 C4 (--window-clock): the window clock of a SHADOW pick (nothing is sent); live, the fire record carries it (computed
            // after the writes: nothing more before them)
            if wclock && !live {
                let t_first = first_seen.get(&u64::from_be_bytes(a.tx.sig[..8].try_into().unwrap())).map(|x| x.0);
                pick_j["win"] = speed16::window_json(a.slot, t_first, a.t_rx, Some(arbx::feeds::clock::now_ns()), None, &feed_names);
            }
            held.w(&log, pick_j);
            if !live { continue; }
            if DIP_NO_FIRE.load(Ordering::Relaxed) { skip("no_new_buys", &mut skipped); continue; }
            if open.contains_key(&e.mint) { skip("open_on_token", &mut skipped); continue; }
            if open.len() >= max_inflight { skip("max_open", &mut skipped); continue; }
            // PRE-SEND LIVE: a pre-send position on this token (or any, one position per server) / attempts armed or in flight on it
            if let Some(why) = pslive.as_ref().and_then(|p| p.blocks_reactive(&e.mint)) { skip(why, &mut skipped); continue; }
            if KS_PAUSE.load(Ordering::Relaxed) || FIRE_PAUSE.load(Ordering::Relaxed) { skip("paused", &mut skipped); continue; }
            let bal = ACCT.bal.load(Ordering::SeqCst);
            if bal > 0 && bal < spend_p + 30_000_000 + ACCT.reserved.load(Ordering::SeqCst) { skip("balance", &mut skipped); continue; }
            // FIRE
            let f = fast.expect("checked above");
            let t0 = arbx::feeds::clock::now_ns();
            let cr = [a.t_rx, a.t_decoded, t0, t0, t0, t0];
            // NONCE (--nonce-fanout): a READY durable nonce (no I/O) -> one variant per send path, one tip each. None ready, or
            // its variants cannot be built -> this buy is today's multi-tip tx (NONCE-FALLBACK, logged after the writes)
            let lease = npool.and_then(|np| np.take());
            let mut nonce_fb: Option<String> = if npool.is_some() && lease.is_none() { Some("no nonce account ready".into()) } else { None };
            let nprep = match &lease {
                // B2 (--dip-defer): the route computed above (same slot) instead of a second lookup
                Some(l) => match if defer { f.prepare_nonce_route(&launch, a.slot, min_out, cr, Some(spend_p), (l.key, l.value), fan.clone(), meta.clone(), tk.keys) }
                                 else { f.prepare_nonce(&launch, a.slot, min_out, cr, Some(spend_p), (l.key, l.value)) } {
                    Ok(p) => Some(p), Err(err) => { nonce_fb = Some(format!("{err:#}")); None }
                },
                None => None,
            };
            if nprep.is_none() { if let (Some(np), Some(l)) = (npool, lease.as_ref()) { np.give_back(l); } }
            let mut prep = match nprep {
                Some(p) => p,
                None => match f.prepare_on(&launch, a.slot, min_out, cr, None, Some(spend_p)) { Ok(p) => p, Err(err) => { eprintln!("  DIP prepare {} failed: {err:#}", b58(&e.mint)); skip("prepare_failed", &mut skipped); continue; } },
            };
            let t_p1 = arbx::feeds::clock::now_ns();
            let rec = f.fire(&mut prep);
            // ---- everything below runs after the writes ----
            // B2 (--dip-defer): this dump's held dump / pick records now, before its fire record (the same order as without)
            held.flush(&log);
            // NONCE: the account is out of rotation until its value changes (a variant landed / failed) or deadline + 150 slots
            if let (Some(np), Some(l)) = (npool, lease.as_ref()) { if prep.nonce.is_some() { np.fired(l, prep.deadline); } }
            n_fired += 1;
            let pos = Pos::new(e.mint, spend_p, 5_000 + prep.meta.tips + arg_u64("--cu-limit", 120_000) * arg_u64("--cu-price-micro", 3_000_000) / 1_000_000, &prep.meta.sig);
            let t_fire = arbx::feeds::clock::now_ns();
            // NONCE: the variants sent (only a signed one can have been): per path its own signature and tip
            let vars: Vec<Var> = prep.variants().into_iter().map(|(sig, sig_b, tip, tip_acct, paths)| Var { sig, sig_b, tip, tip_acct, paths }).collect();
            // dip16 C4 (--window-clock): the dump's window clock at our decision (t0, before the prepare) and first write; C3: the write tag
            let win = wclock.then(|| speed16::window_json(a.slot, first_seen.get(&u64::from_be_bytes(a.tx.sig[..8].try_into().unwrap())).map(|x| x.0), a.t_rx, Some(t0),
                speed16::first_write_rt(&rec.w), &feed_names));
            let tag = if speed16::route_on() { prep.id } else { 0 };
            pend.push(Pend { kind: "fire", mint: b58(&e.mint), buy_sig: prep.meta.sig.clone(), dump_sig_b: a.tx.sig, buy_sig_b: prep.sig, t_dump_rx: a.t_rx, t_fire,
                             due: Instant::now() + Duration::from_secs(3), more: vars.iter().skip(1).map(|v| v.sig_b).collect(), via: "", win: win.clone(), tag });
            let mut fj = serde_json::json!({"ev": "fire", "mint": b58(&e.mint), "dump_sig": sig, "buy_sig": prep.meta.sig, "slot": a.slot, "t_dump_rx": a.t_rx, "t_fire": t_fire,
                "decision_us": (t_fire as i64 - a.t_rx as i64) as f64 / 1e3, "lat_us": {"queue": (t_loop as i64 - a.t_rx as i64) as f64 / 1e3, "book": (t_d0 as i64 - t_loop as i64) as f64 / 1e3,
                    "score": (t_d1 as i64 - t_d0 as i64) as f64 / 1e3, "checks_logs": (t0 as i64 - t_d1 as i64) as f64 / 1e3, "prepare": (t_p1 as i64 - t0 as i64) as f64 / 1e3,
                    "fire": (t_fire as i64 - t_p1 as i64) as f64 / 1e3}, "route": prep.meta.route, "leader": prep.meta.leader, "client": prep.meta.client,
                "tips": prep.meta.tips, "min_out": min_out, "spend": spend_p, "dev": tk.dev, "deadline": prep.deadline,
                "writes": rec.w.iter().map(|(n, k, a0, a1, st)| serde_json::json!({"path": n, "kind": k, "t0": a0, "t1": a1, "st": st})).collect::<Vec<_>>()});
            if let Some(n) = &prep.nonce {
                // "tips" above = the largest single variant tip (one variant lands: the most this buy pays in tips)
                fj["nonce"] = serde_json::json!({"acct": b58(&n.acct), "value": b58(&n.value), "variants": vars.iter().map(var_json).collect::<Vec<_>>(),
                    "per_path": prep.fan.iter().enumerate().map(|(i, pth)| { let v = &n.vars[n.vi[i]];
                        serde_json::json!({"path": pth.name, "sig": if v.signed { Some(v.sig58.clone()) } else { None }, "tip": v.tip.map_or(0, |t| t.1)}) }).collect::<Vec<_>>()});
            }
            if let Some(why) = &nonce_fb { fj["nonce_fallback"] = serde_json::json!(why); }
            // dip16 (each only with its flag)
            if let Some(w) = win { fj["win"] = w; }
            if tag != 0 { fj["tag"] = serde_json::json!(tag); }
            log.w(fj);
            let nnote = match (&prep.nonce, &nonce_fb) { (Some(n), _) => format!(" | nonce {} x{} variants", &b58(&n.acct)[..8], vars.len()), (None, Some(_)) => " | NONCE-FALLBACK".into(), _ => String::new() };
            eprintln!("  DIP FIRE {} score {:.3} age {:.1}s dump {:.2} SOL -{:.1}% | {:.2} SOL{} | route {} leader {} ({}) | buy {}{nnote}", b58(&e.mint), d.score, d.age, d.feats[1], d.feats[2],
                spend_p as f64 / 1e9, if tk.dev { " DEV-LIST" } else { "" }, prep.meta.route, &prep.meta.leader[..8.min(prep.meta.leader.len())], prep.meta.client, prep.meta.sig);
            if let (Some(np), Some(why)) = (npool, nonce_fb.as_ref()) {
                np.fallbacks.fetch_add(1, Ordering::Relaxed);
                eprintln!("  NONCE-FALLBACK {}: {why}: this buy went as today's multi-tip tx ({})", b58(&e.mint), np.line());
            }
            // the RPC land poll runs beside the executed feed (whichever sees the landing first; the poll also classifies failures)
            {
                let (rpc2, mtx2, sigs, sigb, slot, bhv, mint) = (rpc.clone(), mtx.clone(), prep.meta.sig.clone(), prep.sig, a.slot, prep.bh_valid, e.mint);
                let all: Vec<(String, [u8; 64])> = vars.iter().map(|v| (v.sig.clone(), v.sig_b)).collect();
                let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
                tokio::spawn(async move {
                    let to = Duration::from_millis(arg_u64("--land-timeout-ms", 8_000));
                    // NONCE: every variant's status in one call per round (at most one of them can land)
                    let l = if all.is_empty() { poll_land(&rpc2, sigs, sigb, slot, to, Watch::BuyAta(ata), bhv).await } else { poll_land_any(&rpc2, all, slot, to, Watch::BuyAta(ata)).await };
                    let _ = mtx2.send(Msg::Land(mint, l));
                });
            }
            open.insert(e.mint, LivePos { mint: e.mint, launch, dump_sig: sig.clone(), dump_slot: a.slot, dump_idx: x.index, t_dump_rx: a.t_rx, dump_vsol: tr.vsol, dump_vtok: tr.vtok,
                score: d.score, t_fire_ns: t_fire, buy_sig: prep.meta.sig.clone(), buy_sig_b: prep.sig, route: prep.meta.route.clone(), leader: prep.meta.leader.clone(),
                client: prep.meta.client.clone(), tips: prep.meta.tips, spend: spend_p, min_out, send_slot: a.slot, land: None, tokens: 0, sol_in: 0, buy_ok: None,
                exit: None, sell_land: None, pos: Some(pos), fired_at: Instant::now(), vars });
            // NONCE --fast-verify (off the hot path): every sent variant vs its own full compile, signature, requests and tips
            if prep.nonce.is_some() && f.verify_on() { tokio::spawn(async move { f.trace_prep(&prep) }); }
        }
        // B2 (--dip-defer): the last trade's held records; SHRED FIRE: a shred-decided dump of this tx the executed path found no dump in
        held.flush(&log);
        if let Some(sf) = shred.as_mut() { sf.exec_tx_done(&a.tx.sig, a.t_rx, &log); }
        time_exits(&mut open, slot_now, hold, &log, &key_arc, user, rpc, path, &mtx);
        // PRE-SEND LIVE: this tx's creates / trades (after every IMIT1 decision, send and exit of it): triggers, the windows' prices,
        // our fills, its positions' exits
        if let Some(p) = pslive.as_mut() {
            p.reactive_open(open.len());
            p.on_exec(&a, &x, slot_now, |m| toks.get(m).and_then(|t| t.launch.clone()), &|m| open.contains_key(m), Some(&first_seen));
        }
        // PRE-SEND SHADOW: this tx's creates and trades go in only now, after every IMIT1 decision, send and exit of the tx
        if let Some(ps) = presend.as_mut() {
            let t0 = Instant::now();
            ps_marks.push([n_dumps, n_env, n_picks, n_fired, m2st.picks]);
            presend_tx_live(ps, a.slot, slot_now, &x, &a.tx.sig, a.t_rx, &ps_marks, &log, pslive.as_mut());
            ps_marks.clear();
            ps_time.add(t0.elapsed().as_secs_f64() * 1e6, x.trades.len());
        }
    }
    eprintln!("=== DIP DONE: dumps {n_dumps} in-envelope {n_env} picks {n_picks} fired {n_fired} closed {n_closed} landed buys {} realized {:+.6} SOL skipped {:?}",
        ACCT.landed_buys.load(Ordering::SeqCst), ACCT.realized.load(Ordering::SeqCst) as f64 / 1e9, skipped);
    if let Some(np) = npool { eprintln!("=== DIP NONCE: {}", np.line()); }
    if m2.is_some() { eprintln!("=== DIP M2:{}", m2st.line(m2_gate)); }
    // PRE-SEND SHADOW: what is buffered is processed; windows still open get a "run_end" disarm
    if let Some(ps) = presend.as_mut() {
        ps.finish();
        // dip20 QUIET: what it would have decided goes into the shadow's last records too (nothing without it)
        let mut evs = ps.drain();
        if let Some(p) = pslive.as_mut() { p.annotate_shadow(&mut evs); }
        for ev in evs {
            // PRE-SEND LIVE: the shadow's last triggers for the parity
            if ev.rec["ev"] == "presend_arm" { if let Some(p) = pslive.as_mut() { p.on_shadow_arm(&ev.rec); } }
            log.w(ev.rec);
        }
        eprintln!("=== DIP PRESEND:{}{}", ps.line(), ps_time.line());
    }
    // PRE-SEND LIVE: the sender stops; unresolved attempts resolved, the records written, the totals for run_end
    let mut ps_live_end = pslive.as_mut().map(|p| p.finish(slot_now, Some(&first_seen)));
    // dip19 (fix 4): every mint pre-send filled / found holding / left open gets a confirmed read: a balance is sold now (the drain), an
    // empty account closed; what is still held is HELD-AT-EXIT (Telegram, --sell-held). Nothing of this without --presend-live
    if let Some(p) = pslive.as_mut() {
        let e = p.end_drain().await;
        if let Some(j) = ps_live_end.as_mut() { j["end_check"] = e; }
    }
    // let the realized-PnL readers finish (chain reads of the last trades)
    for _ in 0..40 { if REALIZED_INFLIGHT.load(Ordering::SeqCst) == 0 { break; } tokio::time::sleep(Duration::from_millis(500)).await; }
    let mut re = serde_json::json!({"ev": "run_end", "t": arbx::feeds::clock::now_ns(), "dumps": n_dumps, "in_envelope": n_env, "picks": n_picks, "fired": n_fired, "closed": n_closed,
        "landed_buys": ACCT.landed_buys.load(Ordering::SeqCst), "realized": ACCT.realized.load(Ordering::SeqCst), "skipped": skipped});
    if let Some(np) = npool {
        re["nonce"] = serde_json::json!({"used": np.taken.load(Ordering::Relaxed), "fallbacks": np.fallbacks.load(Ordering::Relaxed), "advanced": np.advanced.load(Ordering::Relaxed),
            "reused": np.reused.load(Ordering::Relaxed)});
    }
    if m2.is_some() {
        let (p50, p99) = m2st.pct();
        re["m2"] = serde_json::json!({"mode": if m2_gate { "gate" } else { "shadow" }, "min": m2_min, "scored": m2st.scored, "picks": m2st.picks, "imit_also": m2st.both,
            "skipped": m2st.skipped, "us_p50": p50, "us_p99": p99});
    }
    if let Some(ps) = &presend { let mut j = ps.stats_json(); j["timing"] = ps_time.json(); re["presend"] = j; }
    if let Some(j) = ps_live_end { re["presend_live"] = j; }
    if let Some(sf) = shred.as_ref() { re["shred"] = sf.json(); eprintln!("=== DIP SHRED:{}", sf.line()); }
    log.w(re);
    feed_stop.store(true, Ordering::SeqCst);    // every position is closed: the feeds may stop now
    if live { tg::raise(arbx::alerts::Level::Info, "dip_end", "end", "🏁", "DIP RUN END", arbx::alerts::format::Body::new().kv("trades", ACCT.landed_buys.load(Ordering::SeqCst).to_string()).kv("realized", sol_str(ACCT.realized.load(Ordering::SeqCst))), false); }
    Ok(())
}

/// a fire / probe waiting for its timing record (the PoH positions arrive with the shreds, a little after the landing)
/// NONCE: `more` = the buy's other variants' signatures (empty: one tx)
/// dip14: `via` = "shred" for a buy fired on the dump's shred sighting ("" otherwise: the record is dip13's)
/// dip16: `win` = C4's window clock of the fire (--window-clock; None: off), `tag` = its write tag for C3's answers (--log-route-headers;
/// 0: off). Both None / 0: the timing record is dip15's
struct Pend { kind: &'static str, mint: String, buy_sig: String, dump_sig_b: [u8; 64], buy_sig_b: [u8; 64], t_dump_rx: u64, t_fire: u64, due: Instant, more: Vec<[u8; 64]>,
              via: &'static str, win: Option<serde_json::Value>, tag: u64 }

/// feed lag of the trigger (first sighting on any feed -> the executed feed), our reaction (first sighting -> fire), fire -> our tx
/// seen back on a feed, and the landing delay on the LEADER'S clock (PoH: our tx's position minus the dump's)
fn timing_rec(p: &Pend, first: &rustc_hash::FxHashMap<u64, (u64, u16)>, names: &[String]) -> serde_json::Value {
    let k8 = |s: &[u8; 64]| u64::from_be_bytes(s[..8].try_into().unwrap());
    let fs = |s: &[u8; 64]| first.get(&k8(s)).map(|&(t, f)| (t, names.get(f as usize).cloned().unwrap_or_else(|| f.to_string())));
    let poh = |s: &[u8; 64]| arbx::feeds::poh_index().get_sig(s).and_then(|(ph, _)| ph.ms().map(|ms| (ph.slot, ms)));
    // NONCE: the variant that was seen (only the landed one can be); without variants the one tx, as before
    let bsig = if p.more.is_empty() { &p.buy_sig_b } else { std::iter::once(&p.buy_sig_b).chain(p.more.iter()).find(|s| fs(s).is_some() || poh(s).is_some()).unwrap_or(&p.buy_sig_b) };
    let (df, bf) = (fs(&p.dump_sig_b), fs(bsig));
    let (dp, bp) = (poh(&p.dump_sig_b), poh(bsig));
    let slot_ms = arbx::feeds::entries::SLOT_US.load(Ordering::Relaxed) as f64 / 1000.0;
    let land = match (dp, bp) { (Some((ds, dm)), Some((bs, bm))) => Some((bs as f64 - ds as f64) * slot_ms + (bm - dm)), _ => None };
    let mut j = serde_json::json!({"ev": "timing", "kind": p.kind, "mint": p.mint, "buy_sig": p.buy_sig,
        "dump_first_rx": df.as_ref().map(|x| x.0), "dump_first_feed": df.as_ref().map(|x| x.1.clone()), "dump_exec_rx": p.t_dump_rx,
        "exec_lag_ms": df.as_ref().map(|x| (p.t_dump_rx as i64 - x.0 as i64) as f64 / 1e6),
        "reaction_ms": df.as_ref().map(|x| (p.t_fire as i64 - x.0 as i64) as f64 / 1e6),
        "buy_first_rx": bf.as_ref().map(|x| x.0), "buy_first_feed": bf.as_ref().map(|x| x.1.clone()),
        "fire_to_seen_ms": bf.as_ref().map(|x| (x.0 as i64 - p.t_fire as i64) as f64 / 1e6),
        "dump_poh": dp, "buy_poh": bp, "land_ms_poh": land, "slot_ms": slot_ms});
    if !p.more.is_empty() { j["buy_sig_seen"] = serde_json::json!(bs58::encode(bsig).into_string()); }
    if !p.via.is_empty() { j["via"] = serde_json::json!(p.via); }
    // dip16 C4 (--window-clock): the fire's window clock + when our tx was first seen, in ms since the window start and left in the block
    if let Some(w) = &p.win {
        let mut w = w.clone();
        if let (Some(w0), Some(b)) = (w["w0_rx"].as_u64(), bf.as_ref()) {
            let m = ((b.0 as i64 - w0 as i64) as f64 / 1e3).round() / 1e3;
            w["buy_seen_ms"] = serde_json::json!(m);
            w["left_ms_seen"] = serde_json::json!(((w["deadline_ms"].as_f64().unwrap_or(0.0) - m) * 1e3).round() / 1e3);
        }
        j["win"] = w;
    }
    // dip16 C3 (--log-route-headers): every send path's answer of this fire / probe (HTTP status, ms, Constant-K's route)
    if p.tag != 0 { if let Some(a) = speed16::take_acks(p.tag) { j["acks"] = serde_json::json!(a); } }
    j
}

/// D1 (--dip-clock2, dip14): the timing record + the clocks that still work since Alpenglow (ops/dip/speed/fixes/FIXES.md: the PoH
/// hash count now counts the block position, not time):
///  * both txs' block index (the executed feed; our failed tx's from its side channel) and slot; the slots' real sizes (entries feed)
///  * `pos`: the PoH hash count before the tx / the slot's total = its fraction of the block (the "fixed PoH": a position clock)
///  * land_ms_pos / land_ms_bmix (the real block size) / land_ms_b400 (size 400): slots x slot_ms + the position difference x slot_ms
///  * every feed's own arrival of both txs and the difference (`feeds`), the entries feed's (land_ms_ent)
fn timing_rec2(p: &Pend, first: &rustc_hash::FxHashMap<u64, (u64, u16)>, names: &[String], feed_seen: &rustc_hash::FxHashMap<u64, [u64; 8]>,
               exec_idx: &rustc_hash::FxHashMap<u64, (u64, u64)>, own_idx: &rustc_hash::FxHashMap<u64, (u64, u64)>) -> serde_json::Value {
    let mut j = timing_rec(p, first, names);
    let k8 = |s: &[u8; 64]| u64::from_be_bytes(s[..8].try_into().unwrap());
    // the buy: the variant that was seen (as timing_rec)
    let bsig = j["buy_sig_seen"].as_str().and_then(|s| bs58::decode(s).into_vec().ok()).and_then(|v| <[u8; 64]>::try_from(v).ok()).unwrap_or(p.buy_sig_b);
    let (dk, bk) = (k8(&p.dump_sig_b), k8(&bsig));
    let idx_of = |k: u64| exec_idx.get(&k).or_else(|| own_idx.get(&k)).copied();
    let (di, bi) = (idx_of(dk), idx_of(bk));
    let slot_ms = j["slot_ms"].as_f64().unwrap_or(212.0);
    let pi = arbx::feeds::poh_index();
    let pos = |k: u64| pi.get_full(k).and_then(|(ph, _, _)| pi.slot_total(ph.slot).filter(|t| t.valid && t.hashes > 0).map(|t| (ph.slot, ph.hashes as f64 / t.hashes as f64)));
    let (dp, bp) = (pos(dk), pos(bk));
    let size = |s: u64| pi.slot_total(s).filter(|t| t.valid).map(|t| t.txs);
    // B400: index / max(400, index + 1); Bmix: the real block size when it is above 400 (the study's clocks); the difference is
    // taken in slots + fractions (no absolute ms: f64 keeps sub-µs precision)
    let frac = |i: u64, n: Option<u64>| i as f64 / n.map_or(400, |x| x.max(400)).max(i + 1) as f64;
    let bland = |mix: bool| di.zip(bi).map(|(d, b)| {
        let (nd, nb) = if mix { (size(d.0), size(b.0)) } else { (None, None) };
        ((b.0 as f64 - d.0 as f64) + frac(b.1, nb) - frac(d.1, nd)) * slot_ms
    });
    let mut c = serde_json::json!({"dump_slot": di.map(|x| x.0), "dump_idx": di.map(|x| x.1), "buy_slot": bi.map(|x| x.0), "buy_idx": bi.map(|x| x.1),
        "dump_slot_txs": di.and_then(|x| size(x.0)), "buy_slot_txs": bi.and_then(|x| size(x.0)),
        "dump_pos": dp.map(|x| x.1), "buy_pos": bp.map(|x| x.1),
        "land_ms_pos": dp.zip(bp).map(|(d, b)| (b.0 as f64 - d.0 as f64) * slot_ms + (b.1 - d.1) * slot_ms),
        "land_ms_bmix": bland(true), "land_ms_b400": bland(false)});
    // the entries feed's own arrival of both (its message clock) and every feed's
    let ent = |k: u64| pi.get_full(k).map(|(_, f, t)| (f, t));
    if let (Some((fd, td)), Some((fb, tb))) = (ent(dk), ent(bk)) { if fd == fb { c["land_ms_ent"] = serde_json::json!((tb as i64 - td as i64) as f64 / 1e6); } }
    if let (Some(fd), Some(fb)) = (feed_seen.get(&dk), feed_seen.get(&bk)) {
        let mut m = serde_json::Map::new();
        for (i, n) in names.iter().enumerate().take(8) {
            if fd[i] > 0 && fb[i] > 0 { m.insert(n.clone(), serde_json::json!([fd[i], fb[i], (fb[i] as i64 - fd[i] as i64) as f64 / 1e6])); }
        }
        c["feeds"] = serde_json::Value::Object(m);
    }
    j["clock2"] = c;
    j
}

/// B2 (--dip-defer, dip14): the event loop's dump / pick / pick_skip records of the tx being decided, held until after its sends and
/// then written in the same order (without the flag every record is written at once, as dip13)
struct Held { on: bool, v: std::cell::RefCell<Vec<serde_json::Value>> }

impl Held {
    fn w(&self, log: &DipLog, v: serde_json::Value) { if self.on { self.v.borrow_mut().push(v); } else { log.w(v); } }
    fn flush(&self, log: &DipLog) {
        if !self.on { return; }
        let v = std::mem::take(&mut *self.v.borrow_mut());
        if !v.is_empty() { log.w_all(v); }
    }
}

/// B3 (--dip-feed-lag, dip14): one record per minute: the executed feed's lag behind the first sighting of every pump tx on another
/// feed (all of them, by the feed that saw it first), the providers' own lag (their message stamp -> our receipt), the event loop's
/// queue on executed arrivals; the minute's samples are cleared
fn feed_lag_rec(all: &mut Vec<u64>, by: &mut HashMap<u16, Vec<u64>>, q: &mut Vec<u64>, names: &[String], feeds: &arbx::feeds::Feeds) -> serde_json::Value {
    fn three(v: &mut [u64]) -> serde_json::Value {
        if v.is_empty() { return serde_json::json!({"n": 0}); }
        v.sort_unstable();
        let at = |q: f64| v[((v.len() - 1) as f64 * q).round() as usize] as f64 / 1e6;
        serde_json::json!({"n": v.len(), "p50": at(0.5), "p90": at(0.9), "p99": at(0.99), "max": at(1.0)})
    }
    let mut j = serde_json::json!({"ev": "feed_lag", "t": arbx::feeds::clock::now_ns(), "exec_vs_first_ms": three(all), "queue_exec_ms": three(q)});
    let mut m = serde_json::Map::new();
    for (f, v) in by.iter_mut() { m.insert(names.get(*f as usize).cloned().unwrap_or_else(|| f.to_string()), three(v)); }
    j["exec_vs_first_ms_by_first_feed"] = serde_json::Value::Object(m);
    let mut pl = serde_json::Map::new();
    for c in &feeds.counters {
        if let Some(sr) = c.provider_lag.lock().unwrap_or_else(|e| e.into_inner()).as_mut() { pl.insert(c.name.clone(), sr.take_interval(1e6)); }
    }
    j["provider_lag_ms"] = serde_json::Value::Object(pl);
    all.clear(); by.clear(); q.clear();
    j
}

/// SHRED FIRE (dip14): what the executed path's checks + fire need besides the books
struct ShredCtx<'a> {
    live: bool, spacing: u64, allow_holder: bool, guard: f64, spend: u64, dev_spend: u64, near: Option<&'a HashSet<String>>, skip_clients: Option<&'a [String]>,
    max_inflight: usize, pslive: Option<&'a pslive::PsLive>, npool: Option<&'static Arc<noncefan::Pool>>, fast: Option<&'static fastfire::Fast>, user: Pk,
    rpc: &'a Arc<rpc::Rpc>, path: &'a Arc<send::Path>, mtx: &'a tokio::sync::mpsc::UnboundedSender<Msg>, log: &'a DipLog,
    /// dip16 C4: the feeds' names (the window clock's first-arrival feed)
    names: &'a [String],
}

/// SHRED FIRE (dip14): a robust shred pick through the executed path's own checks, in its order (spacing, launch kind, the guard's
/// min_out on the shred-priced post-dump curve, route, near leaders, skipped clients, the run's state) and, live, its buy: the
/// executed path's FIRE (prepare, writes, nonce, position, land poll), its records labeled "via": "shred" (fire, timing). Shadow
/// (or a run without --live): nothing is sent ("would_fire"). -> (what it became, (t_fire, buy sig) when fired, min_out)
#[allow(clippy::too_many_arguments)]
fn shred_pick(pk: &shredfire::Pick, a: &arbx::feeds::Arrival, t_loop: u64, t_dec: u64, toks: &mut HashMap<Pk, Tok>, open: &mut HashMap<Pk, LivePos>, pend: &mut Vec<Pend>,
              n_fired: &mut u64, c: ShredCtx) -> (String, Option<(u64, String)>, Option<u64>) {
    let skip = |w: &str, mo: Option<u64>| (format!("skip:{w}"), None, mo);
    let Some(tk) = toks.get_mut(&pk.mint) else { return skip("no_token", None) };
    let tr = &pk.tr;
    let spend_p = if pk.dev { c.dev_spend } else { c.spend };
    if tk.last_pick_slot.is_some_and(|s| a.slot < s + c.spacing) { return skip("spacing", None); }
    let Some(launch) = tk.launch.clone() else { return skip("no_launch_accounts", None) };
    if !launch.is_create_v2 { return skip("legacy_create", None); }
    let holder_ok = c.allow_holder && launch.is_holder_reward && !launch.is_mayhem && !launch.is_cashback && launch.creator_fee_bps == 0;
    if !launch.is_vanilla() && !holder_ok { return skip("non_vanilla", None); }
    let min_out = arbx::dip_shred::guard_min_out(spend_p, tr.vsol, tr.vtok, pk.fees, c.guard);
    let (fan, meta) = lat::buy_paths(c.path, ALSO_PATH.get(), Some(a.slot));
    if c.near.is_some_and(|n| !n.contains(&meta.leader)) { return skip("far_leader", Some(min_out)); }
    if c.skip_clients.is_some_and(|l| shredfire::client_in(l, &meta.client)) { return skip("skip_client", Some(min_out)); }
    if DIP_NO_FIRE.load(Ordering::Relaxed) { return skip("no_new_buys", Some(min_out)); }
    if open.contains_key(&pk.mint) { return skip("open_on_token", Some(min_out)); }
    if open.len() >= c.max_inflight { return skip("max_open", Some(min_out)); }
    if let Some(why) = c.pslive.and_then(|p| p.blocks_reactive(&pk.mint)) { return skip(why, Some(min_out)); }
    if KS_PAUSE.load(Ordering::Relaxed) || FIRE_PAUSE.load(Ordering::Relaxed) { return skip("paused", Some(min_out)); }
    let bal = ACCT.bal.load(Ordering::SeqCst);
    if bal > 0 && bal < spend_p + 30_000_000 + ACCT.reserved.load(Ordering::SeqCst) { return skip("balance", Some(min_out)); }
    if !c.live { return ("would_fire".into(), None, Some(min_out)); }
    let Some(f) = c.fast else { return skip("no_fast_path", Some(min_out)) };
    // FIRE (the executed path's code; the route computed above is reused)
    tk.last_pick_slot = Some(a.slot);
    let t0 = arbx::feeds::clock::now_ns();
    let cr = [a.t_rx, a.t_decoded, t0, t0, t0, t0];
    let lease = c.npool.and_then(|np| np.take());
    let mut nonce_fb: Option<String> = if c.npool.is_some() && lease.is_none() { Some("no nonce account ready".into()) } else { None };
    let nprep = match &lease {
        Some(l) => match f.prepare_nonce_route(&launch, a.slot, min_out, cr, Some(spend_p), (l.key, l.value), fan.clone(), meta.clone(), tk.keys) {
            Ok(p) => Some(p), Err(err) => { nonce_fb = Some(format!("{err:#}")); None }
        },
        None => None,
    };
    if nprep.is_none() { if let (Some(np), Some(l)) = (c.npool, lease.as_ref()) { np.give_back(l); } }
    let mut prep = match nprep {
        Some(p) => p,
        None => match f.prepare_on(&launch, a.slot, min_out, cr, None, Some(spend_p)) { Ok(p) => p, Err(err) => { eprintln!("  DIP SHRED prepare {} failed: {err:#}", b58(&pk.mint)); return skip("prepare_failed", Some(min_out)); } },
    };
    let t_p1 = arbx::feeds::clock::now_ns();
    let rec = f.fire(&mut prep);
    // ---- everything below runs after the writes ----
    if let (Some(np), Some(l)) = (c.npool, lease.as_ref()) { if prep.nonce.is_some() { np.fired(l, prep.deadline); } }
    *n_fired += 1;
    let pos = Pos::new(pk.mint, spend_p, 5_000 + prep.meta.tips + arg_u64("--cu-limit", 120_000) * arg_u64("--cu-price-micro", 3_000_000) / 1_000_000, &prep.meta.sig);
    let t_fire = arbx::feeds::clock::now_ns();
    let vars: Vec<Var> = prep.variants().into_iter().map(|(sig, sig_b, tip, tip_acct, paths)| Var { sig, sig_b, tip, tip_acct, paths }).collect();
    let dump_sig_b = a.tx.sig;
    // dip16 C4 (--window-clock): the window clock (the shred arrival is the dump's first sighting); C3: the write tag
    let win = speed16::window_on().then(|| speed16::window_json(a.slot, Some(a.t_rx), a.t_rx, Some(t0), speed16::first_write_rt(&rec.w), c.names));
    let tag = if speed16::route_on() { prep.id } else { 0 };
    pend.push(Pend { kind: "fire", mint: b58(&pk.mint), buy_sig: prep.meta.sig.clone(), dump_sig_b, buy_sig_b: prep.sig, t_dump_rx: a.t_rx, t_fire,
                     due: Instant::now() + Duration::from_secs(3), more: vars.iter().skip(1).map(|v| v.sig_b).collect(), via: "shred", win: win.clone(), tag });
    let mut fj = serde_json::json!({"ev": "fire", "via": "shred", "mint": b58(&pk.mint), "dump_sig": tr.sig, "buy_sig": prep.meta.sig, "slot": a.slot, "t_dump_rx": a.t_rx,
        "t_fire": t_fire, "decision_us": (t_fire as i64 - a.t_rx as i64) as f64 / 1e3,
        "lat_us": {"queue": (t_loop as i64 - a.t_rx as i64) as f64 / 1e3, "book": 0.0, "score": pk.eval_us, "checks_logs": (t0 as i64 - t_dec as i64) as f64 / 1e3,
                   "shred": (t_dec as i64 - t_loop as i64) as f64 / 1e3, "prepare": (t_p1 as i64 - t0 as i64) as f64 / 1e3, "fire": (t_fire as i64 - t_p1 as i64) as f64 / 1e3},
        "route": prep.meta.route, "leader": prep.meta.leader, "client": prep.meta.client, "tips": prep.meta.tips, "min_out": min_out, "spend": spend_p, "dev": pk.dev,
        "deadline": prep.deadline, "shred": {"i_lo": tr.i, "fees": pk.fees, "vsol": tr.vsol, "vtok": tr.vtok, "sol": tr.sol, "tok": tr.tok, "user": tr.user, "feed": a.feed},
        "writes": rec.w.iter().map(|(n, k, a0, a1, st)| serde_json::json!({"path": n, "kind": k, "t0": a0, "t1": a1, "st": st})).collect::<Vec<_>>()});
    if let Some(n) = &prep.nonce {
        fj["nonce"] = serde_json::json!({"acct": b58(&n.acct), "value": b58(&n.value), "variants": vars.iter().map(var_json).collect::<Vec<_>>(),
            "per_path": prep.fan.iter().enumerate().map(|(i, pth)| { let v = &n.vars[n.vi[i]];
                serde_json::json!({"path": pth.name, "sig": if v.signed { Some(v.sig58.clone()) } else { None }, "tip": v.tip.map_or(0, |t| t.1)}) }).collect::<Vec<_>>()});
    }
    if let Some(why) = &nonce_fb { fj["nonce_fallback"] = serde_json::json!(why); }
    // dip16 (each only with its flag)
    if let Some(w) = win { fj["win"] = w; }
    if tag != 0 { fj["tag"] = serde_json::json!(tag); }
    c.log.w(fj);
    let nnote = match (&prep.nonce, &nonce_fb) { (Some(n), _) => format!(" | nonce {} x{} variants", &b58(&n.acct)[..8], vars.len()), (None, Some(_)) => " | NONCE-FALLBACK".into(), _ => String::new() };
    eprintln!("  DIP FIRE (SHRED) {} score {:.3} age {:.1}s dump {:.2} SOL -{:.1}% | {:.2} SOL{} | route {} leader {} ({}) | buy {}{nnote}", b58(&pk.mint), pk.d.score, pk.d.age, pk.d.feats[1],
        pk.d.feats[2], spend_p as f64 / 1e9, if pk.dev { " DEV-LIST" } else { "" }, prep.meta.route, &prep.meta.leader[..8.min(prep.meta.leader.len())], prep.meta.client, prep.meta.sig);
    if let (Some(np), Some(why)) = (c.npool, nonce_fb.as_ref()) {
        np.fallbacks.fetch_add(1, Ordering::Relaxed);
        eprintln!("  NONCE-FALLBACK {}: {why}: this buy went as today's multi-tip tx ({})", b58(&pk.mint), np.line());
    }
    {
        let (rpc2, mtx2, sigs, sigb, slot, bhv, mint) = (c.rpc.clone(), c.mtx.clone(), prep.meta.sig.clone(), prep.sig, a.slot, prep.bh_valid, pk.mint);
        let all: Vec<(String, [u8; 64])> = vars.iter().map(|v| (v.sig.clone(), v.sig_b)).collect();
        let ata = pda::ata(&c.user, &mint, &pda::TOKEN_2022);
        tokio::spawn(async move {
            let to = Duration::from_millis(arg_u64("--land-timeout-ms", 8_000));
            let l = if all.is_empty() { poll_land(&rpc2, sigs, sigb, slot, to, Watch::BuyAta(ata), bhv).await } else { poll_land_any(&rpc2, all, slot, to, Watch::BuyAta(ata)).await };
            let _ = mtx2.send(Msg::Land(mint, l));
        });
    }
    let buy_sig = prep.meta.sig.clone();
    open.insert(pk.mint, LivePos { mint: pk.mint, launch, dump_sig: tr.sig.clone(), dump_slot: a.slot, dump_idx: u64::MAX, t_dump_rx: a.t_rx, dump_vsol: tr.vsol, dump_vtok: tr.vtok,
        score: pk.d.score, t_fire_ns: t_fire, buy_sig: prep.meta.sig.clone(), buy_sig_b: prep.sig, route: prep.meta.route.clone(), leader: prep.meta.leader.clone(),
        client: prep.meta.client.clone(), tips: prep.meta.tips, spend: spend_p, min_out, send_slot: a.slot, land: None, tokens: 0, sol_in: 0, buy_ok: None,
        exit: None, sell_land: None, pos: Some(pos), fired_at: Instant::now(), vars });
    if prep.nonce.is_some() && f.verify_on() { tokio::spawn(async move { f.trace_prep(&prep) }); }
    ("fired".into(), Some((t_fire, buy_sig)), Some(min_out))
}

/// no new buys (kill switch, end of run)
static DIP_NO_FIRE: AtomicBool = AtomicBool::new(false);

fn di_sell_out(vsol: u64, vtok: u64, tokens: u64) -> u64 { arbx::dip::sell_sol_out(vsol, vtok, tokens) }

/// time limit: the sell goes out one slot before the limit so it lands at buy slot + hold (the replay's exit slot)
#[allow(clippy::too_many_arguments)]
fn time_exits(open: &mut HashMap<Pk, LivePos>, slot_now: u64, hold: u64, log: &Arc<DipLog>, key: &Arc<SigningKey>, user: Pk, rpc: &Arc<rpc::Rpc>, path: &Arc<send::Path>,
              mtx: &tokio::sync::mpsc::UnboundedSender<Msg>) {
    for p in open.values_mut() {
        if p.exit.is_some() { continue; }
        if let Some((ls, _, _)) = p.land {
            // backstop: the feed's slot stopped moving (stall / feed down) -> sell on the wall clock (hold x 400 ms + 3 s after the fire)
            let wall = p.fired_at.elapsed() > Duration::from_millis(hold * 400 + 3_000);
            if slot_now + 1 >= ls + hold || wall {
                let why = if slot_now + 1 >= ls + hold { "time-limit" } else { "time-limit-wall" };
                trigger_exit(p, why, slot_now, f64::NAN, arbx::feeds::clock::now_ns(), log, key, user, rpc, path, mtx);
            }
        } else if p.buy_ok == Some(false) || p.fired_at.elapsed() > Duration::from_secs(20) {
            // never landed / failed: nothing to sell; the land poll's answer closes the record
        }
    }
}

#[allow(clippy::too_many_arguments)]
fn trigger_exit(p: &mut LivePos, why: &'static str, slot: u64, val: f64, t: u64, log: &Arc<DipLog>, key: &Arc<SigningKey>, user: Pk, rpc: &Arc<rpc::Rpc>, path: &Arc<send::Path>,
                mtx: &tokio::sync::mpsc::UnboundedSender<Msg>) {
    p.exit = Some((why, slot, val, t));
    log.w(serde_json::json!({"ev": "exit", "mint": b58(&p.mint), "why": why, "slot": slot, "value": if val.is_nan() { serde_json::Value::Null } else { serde_json::json!(val) }, "t": t,
        "slots_held": p.land.map(|(ls, _, _)| slot as i64 - ls as i64)}));
    eprintln!("  DIP EXIT {} {why} slot {slot}{}", b58(&p.mint), if val.is_nan() { String::new() } else { format!(" value x{val:.3}") });
    let (key, rpc, path, mtx, launch, mint, tokens, land_slot) = (key.clone(), rpc.clone(), path.clone(), mtx.clone(), p.launch.clone(), p.mint, p.tokens, p.land.map(|l| l.0).unwrap_or(slot));
    tokio::spawn(async move {
        let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
        let out = sell_until_zero(&key, user, &rpc, &path, &launch, &ata, (tokens > 0).then_some(tokens), tokens, land_slot, SellOpts::main()).await;
        let _ = mtx.send(Msg::Sold(mint, out));
    });
}

fn on_msg(m: Msg, open: &mut HashMap<Pk, LivePos>, log: &Arc<DipLog>, n_closed: &mut u64, rpc: &Arc<rpc::Rpc>) {
    match m {
        // PRE-SEND LIVE: routed to the probe by the event loop (never here)
        Msg::Ps(_) => {}
        Msg::Land(mint, l) => {
            let Some(p) = open.get_mut(&mint) else { return };
            log.w(serde_json::json!({"ev": "land_poll", "mint": b58(&mint), "sig": l.sig, "ok": l.ok, "land_slot": l.land_slot, "via": l.via, "err": l.err}));
            if p.land.is_some() { return; }                       // the executed feed saw it first
            // NONCE: the variant whose status the poll found is THE buy (its signature, its one tip). Not when the landing was
            // seen only on the token account (`via` "ata": which variant is unknown; the realized PnL then falls back)
            let var = if l.via == "status" { bs58::decode(&l.sig).into_vec().ok().and_then(|b| <[u8; 64]>::try_from(b).ok()).and_then(|b| p.adopt(&b)) } else { None };
            if l.ok && l.land_slot.is_some() {
                // landed but the executed feed missed our TradeEvent: open with the token count the poll read (or a quote)
                let ls = l.land_slot.unwrap();
                p.land = Some((ls, u64::MAX, 0)); p.buy_ok = Some(true);
                p.tokens = l.tokens.unwrap_or(p.min_out);
                if let Some(pos) = p.pos.as_mut() { pos.landed(p.spend + 5_000 + p.tips, ls); }
                log.w(with_var(serde_json::json!({"ev": "buy_land", "mint": b58(&mint), "sig": p.buy_sig, "slot": ls, "via": "rpc_poll", "tokens": p.tokens}), var));
            } else {
                // failed (guard / deadline) or never landed: release and close the record
                if let Some(mut pos) = p.pos.take() { if l.land_slot.is_some() { pos.reverted(5_000 + arg_u64("--cu-limit", 120_000) * arg_u64("--cu-price-micro", 3_000_000) / 1_000_000); } else { pos.not_landed(); } }
                let p = open.remove(&mint).unwrap();
                *n_closed += 1;
                log.w(with_var(serde_json::json!({"ev": "close", "mint": b58(&mint), "result": if l.land_slot.is_some() { "buy_failed" } else { "buy_not_landed" }, "buy_sig": p.buy_sig,
                    "dump_sig": p.dump_sig, "err": l.err, "route": p.route, "leader": p.leader, "client": p.client, "score": p.score}), var));
                eprintln!("  DIP BUY {} {} ({})", b58(&mint), if l.land_slot.is_some() { "FAILED on chain" } else { "did not land" }, l.err.map(|e| e.to_string()).unwrap_or_default());
            }
        }
        Msg::Sold(mint, out) => {
            let Some(mut p) = open.remove(&mint) else { return };
            *n_closed += 1;
            let sold = out.sold_at.is_some();
            if let Some(mut pos) = p.pos.take() {
                if sold { pos.sold(out.sold_at.unwrap()); }
                pos.realized_done = true;
                let est = p.sell_land.map(|s| s.3 as i64).unwrap_or(0) - p.spend as i64;
                spawn_realized_x((**rpc).clone(), mint, p.buy_sig.clone(), out.sigs.clone(), (est, "feed"), Some((p.spend, p.fired_at.elapsed().as_secs_f64(), None, p.tips, 5_000)));
                drop(pos);
            }
            let (why, xslot, xval, _) = p.exit.unwrap_or(("?", 0, f64::NAN, 0));
            let feed_pnl = p.sell_land.map(|s| s.3 as i64 - p.sol_in as i64);
            // NONCE: the variant that landed ("tips" = its one tip: the only one paid)
            let var = p.vars.iter().find(|v| v.sig_b == p.buy_sig_b).map(var_json);
            log.w(with_var(serde_json::json!({"ev": "close", "mint": b58(&mint), "result": if sold { "sold" } else { "UNSOLD" }, "buy_sig": p.buy_sig, "dump_sig": p.dump_sig,
                "dump_slot": p.dump_slot, "dump_idx": p.dump_idx, "land": p.land, "exit_why": why, "exit_slot": xslot, "exit_value": if xval.is_nan() { serde_json::Value::Null } else { serde_json::json!(xval) },
                "sell_land": p.sell_land, "sell_sigs": out.sigs, "sol_in_curve": p.sol_in, "sol_out_curve": p.sell_land.map(|s| s.3), "curve_pnl": feed_pnl,
                "route": p.route, "leader": p.leader, "client": p.client, "tips": p.tips, "spend": p.spend, "score": p.score, "min_out": p.min_out,
                "dump_vsol": p.dump_vsol, "dump_vtok": p.dump_vtok, "held_s": p.fired_at.elapsed().as_secs_f64()}), var));
            eprintln!("  DIP CLOSED {} {} via {why}; curve PnL {}", b58(&mint), if sold { "sold" } else { "UNSOLD" }, feed_pnl.map(|v| format!("{:+.4} SOL", v as f64 / 1e9)).unwrap_or("?".into()));
        }
    }
}

// ---- PRE-SEND SHADOW (--presend-shadow; src/presend.rs, ops/strategies/presend/SHADOW.md) ---------------------------------

/// PRE-SEND SHADOW: one executed tx into the shadow: its creates, then its trades, each with what the reactive bot did on it
/// (`marks`: the dip counters [dumps, in-envelope, picks, fired, M2 picks] before each trade, then after the last one); the
/// feed's clock moves on; the records go to --dip-log (and the short lines to the terminal)
#[allow(clippy::too_many_arguments)]
#[allow(dead_code)] // the engine calls presend_tx_live; the tests call this
fn presend_tx(ps: &mut arbx::presend::Shadow, slot: u64, slot_now: u64, x: &arbx::feeds::ExecInfo, sig: &[u8; 64], t_rx: u64, marks: &[[u64; 5]], log: &DipLog) {
    presend_tx_live(ps, slot, slot_now, x, sig, t_rx, marks, log, None)
}

/// `presend_tx`, and (PRE-SEND LIVE) the shadow's presend_arm records handed to the live probe (parity of the triggers)
#[allow(clippy::too_many_arguments)]
fn presend_tx_live(ps: &mut arbx::presend::Shadow, slot: u64, slot_now: u64, x: &arbx::feeds::ExecInfo, sig: &[u8; 64], t_rx: u64, marks: &[[u64; 5]], log: &DipLog,
                   live: Option<&mut pslive::PsLive>) {
    use arbx::presend::{F_DUMP, F_ENV, F_FIRED, F_M2, F_PICK};
    for c in &x.creates { ps.create(c.mint, slot, c.creator, c.user, x.mayhem, t_rx); }
    let ok = marks.len() == x.trades.len() + 1;
    for (j, e) in x.trades.iter().enumerate() {
        let flags = if ok {
            let (b0, b1) = (marks[j], marks[j + 1]);
            [F_DUMP, F_ENV, F_PICK, F_FIRED, F_M2].iter().enumerate().fold(0u8, |f, (k, &bit)| if b1[k] > b0[k] { f | bit } else { f })
        } else { 0 };
        ps.push(arbx::presend::In { mint: e.mint, s: slot, i: x.index as u32, j: j as i32, sig: *sig, user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok,
                                    fbps: e.fbps, cbps: e.cbps, t_rx, flags });
    }
    ps.advance(slot_now);
    let mut evs = ps.drain();
    if evs.is_empty() { if let Some(l) = live { l.shadow_done(ps.done_slot()); } return; }
    // dip20 QUIET: the shadow's arm / disarm records get what QUIET would have decided (the shadow itself unchanged; nothing without it)
    if let Some(l) = live { l.annotate_shadow(&mut evs); for e in evs.iter().filter(|e| e.rec["ev"] == "presend_arm") { l.on_shadow_arm(&e.rec); } l.shadow_done(ps.done_slot()); }
    // one terminal write and one log flush for all of this call's records
    let lines: String = evs.iter().filter_map(|e| e.line.as_ref()).fold(String::new(), |mut a, l| { a.push_str(l); a.push('\n'); a });
    if !lines.is_empty() { eprint!("{lines}"); }
    log.w_all(evs.into_iter().map(|e| e.rec));
}

/// PRE-SEND SHADOW: its time per executed tx (microseconds, the last PS_US_KEEP txs), txs and trades fed
#[derive(Default)]
struct PresendTime { us: Vec<f32>, i: usize, calls: u64, trades: u64, total_us: f64, max_us: f64, over50: u64 }
const PS_US_KEEP: usize = 8192;

impl PresendTime {
    fn add(&mut self, us: f64, trades: usize) {
        if self.us.len() < PS_US_KEEP { self.us.push(us as f32); } else { self.us[self.i] = us as f32; self.i = (self.i + 1) % PS_US_KEEP; }
        self.calls += 1; self.trades += trades as u64; self.total_us += us; self.max_us = self.max_us.max(us);
        if us > 50.0 { self.over50 += 1; }
    }
    fn pct(&self) -> (f64, f64) {
        let mut v = self.us.clone();
        v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let q = |p: f64| v.get(((v.len().max(1) - 1) as f64 * p).round() as usize).map(|&x| x as f64).unwrap_or(0.0);
        (q(0.5), q(0.99))
    }
    fn line(&self) -> String {
        let (p50, p99) = self.pct();
        format!(" | {:.1} / {:.1} / {:.0} us per tx p50 / p99 / max, {} over 50 us ({} txs, {} trades, {:.2} us per trade)", p50, p99, self.max_us, self.over50, self.calls,
                self.trades, self.total_us / self.trades.max(1) as f64)
    }
    fn json(&self) -> serde_json::Value {
        let (p50, p99) = self.pct();
        serde_json::json!({"us_p50": p50, "us_p99": p99, "us_max": self.max_us, "over_50us": self.over50, "txs": self.calls, "trades": self.trades,
                           "us_per_trade": self.total_us / self.trades.max(1) as f64})
    }
}

// ---- M2 (--dip-m2; ops/strategies/dipdetect/PORT.md) --------------------------------------------------------------------

/// M2 counters for the status line / run end: in-envelope dumps scored, M2 picks (and how many IMIT1 also picked), dumps not
/// scored (why), the M2 time per scored dump (the dump trade's state update + features + score, microseconds; the last
/// M2_US_KEEP dumps)
#[derive(Default)]
struct M2Stats { scored: u64, picks: u64, both: u64, extra: u64, extra_picks: u64, skipped: HashMap<&'static str, u64>, us: Vec<f32>, us_i: usize }
const M2_US_KEEP: usize = 4096;

impl M2Stats {
    fn time(&mut self, us: f64) {
        if self.us.len() < M2_US_KEEP { self.us.push(us as f32); } else { self.us[self.us_i] = us as f32; self.us_i = (self.us_i + 1) % M2_US_KEEP; }
    }
    fn pct(&self) -> (f64, f64) {
        let mut v = self.us.clone();
        v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let q = |p: f64| v.get(((v.len().max(1) - 1) as f64 * p).round() as usize).map(|&x| x as f64).unwrap_or(0.0);
        (q(0.5), q(0.99))
    }
    fn line(&self, gate: bool) -> String {
        let (p50, p99) = self.pct();
        format!(" | M2 {}: scored {} picks {} (IMIT1 also {}; extra dumps {} picks {}) skipped {:?} | {p50:.0} / {p99:.0} us p50 / p99", if gate { "gate" } else { "shadow" },
            self.scored, self.picks, self.both, self.extra, self.extra_picks, self.skipped)
    }
}

/// The M2 work of ONE dump: the dump trade enters the token's M2 state and, in the envelope, is scored; the "dump" record then
/// carries m2 (score), m2_pick, m2_min, m2_feats (the 25 values, dip_model::FN order), m2_us (time), m2_mode, and m2_skip /
/// m2_gaps when they apply. gate: done at `new`, before the decision (the record is written where it always was). shadow: done
/// when this value is dropped at the end of the trade's iteration, i.e. after the IMIT1 decision and any send; the "dump" record
/// is written then (after the pick / fire records of the same dump; the readers match records by mint + sig).
struct M2Dump<'a> {
    b: &'a arbx::dip_model::Bundle, mt: Option<&'a mut arbx::dip_model::Tok>, t2: arbx::dip_model::Tr, env: bool, gate: bool, min: f64,
    /// an M2 extra dump (no IMIT1 dump event: a later big sell of the slot)
    extra: bool,
    log: &'a DipLog, st: &'a mut M2Stats,
    done: bool, score: Option<f64>, feats: Option<[f64; arbx::dip_model::NF]>, skip: Option<&'static str>, us: f64, gaps: u32, reorders: u32,
    /// shadow: the dump record waiting for the M2 fields; (IMIT1 pass, IMIT1 score, age, sell, drop %, launch ok, dev list)
    rec: Option<serde_json::Value>, info: (bool, f64, f64, f64, f64, bool, bool),
    /// the pick's log line, printed at drop (in gate mode too: never a terminal write ahead of a send)
    line: Option<String>,
    /// B2 (--dip-defer, dip14): the dump record goes through the held records (written after the sends)
    held: Option<&'a Held>,
}

impl<'a> M2Dump<'a> {
    #[allow(clippy::too_many_arguments)]
    fn new(b: &'a arbx::dip_model::Bundle, mt: Option<&'a mut arbx::dip_model::Tok>, t2: arbx::dip_model::Tr, env: bool, gate: bool, min: f64, extra: bool,
           log: &'a DipLog, st: &'a mut M2Stats) -> M2Dump<'a> {
        let mut g = M2Dump { b, mt, t2, env, gate, min, extra, log, st, done: false, score: None, feats: None, skip: None, us: 0.0, gaps: 0, reorders: 0, rec: None,
                             info: (false, f64::NAN, 0.0, 0.0, 0.0, false, false), line: None, held: None };
        if gate { g.eval(); }
        g
    }

    /// B2 (--dip-defer, dip14): write the dump record through `h` (None: at once, as dip13)
    fn held(mut self, h: Option<&'a Held>) -> M2Dump<'a> { self.held = h; self }

    /// the dump trade into the M2 state; the features and the score when the dump is in the envelope (once)
    fn eval(&mut self) {
        if self.done { return; }
        self.done = true;
        let t0 = Instant::now();
        match self.mt.as_deref_mut() {
            // the token's create was not seen by this engine (its history is incomplete): never scored
            None => self.skip = Some("no_history"),
            Some(mt) => {
                mt.push(&self.t2, &self.b.sets);
                self.reorders = mt.reorders;
                if self.env {
                    if mt.last_key() != Some((self.t2.s, self.t2.i, self.t2.j)) { self.skip = Some("not_newest"); }
                    else {
                        match mt.features() {
                            Ok(x) => { self.score = Some(self.b.model.score(&x)); self.feats = Some(x); }
                            Err(w) => self.skip = Some(w.as_str()),
                        }
                    }
                }
                self.gaps = mt.gaps;
            }
        }
        self.us = t0.elapsed().as_secs_f64() * 1e6;
        if self.env {
            match self.skip { Some(w) => *self.st.skipped.entry(w).or_default() += 1, None => { self.st.scored += 1; self.st.time(self.us); } }
            if self.extra { self.st.extra += 1; }
        }
    }

    /// the model's verdict (the caller adds the launch check, as for IMIT1)
    fn pick(&self) -> bool { self.score.is_some_and(|s| s >= self.min) }

    /// the in-envelope dump's record (+ what the log line needs): gate writes it now with the M2 fields, shadow keeps it for drop
    #[allow(clippy::too_many_arguments)]
    fn record(&mut self, rec: serde_json::Value, imit_pass: bool, imit_score: f64, age: f64, sell: f64, drop: f64, launch_ok: bool, dev: bool) {
        self.info = (imit_pass, imit_score, age, sell, drop, launch_ok, dev);
        if self.gate { self.finish(rec); } else { self.rec = Some(rec); }
    }

    fn finish(&mut self, mut rec: serde_json::Value) {
        let (imit_pass, imit_score, age, sell, drop, launch_ok, dev) = self.info;
        let pick = launch_ok && self.pick();
        rec["m2"] = serde_json::json!(self.score);
        rec["m2_pick"] = serde_json::json!(pick);
        rec["m2_min"] = serde_json::json!(self.min);
        rec["m2_feats"] = serde_json::json!(self.feats.map(|x| x.to_vec()));
        rec["m2_us"] = serde_json::json!((self.us * 10.0).round() / 10.0);
        rec["m2_mode"] = serde_json::json!(if self.gate { "gate" } else { "shadow" });
        if self.gate { rec["imit_pass"] = serde_json::json!(imit_pass); }
        if self.extra { rec["m2_extra"] = serde_json::json!(true); }
        if let Some(w) = self.skip { rec["m2_skip"] = serde_json::json!(w); }
        if self.gaps > 0 { rec["m2_gaps"] = serde_json::json!(self.gaps); }
        if self.reorders > 0 { rec["m2_reorders"] = serde_json::json!(self.reorders); }
        let mint = rec["mint"].as_str().unwrap_or("?").to_string();
        match self.held { Some(h) => h.w(self.log, rec), None => self.log.w(rec) }
        if pick {
            self.st.picks += 1;
            if imit_pass { self.st.both += 1; }
            if self.extra { self.st.extra_picks += 1; }
            self.line = Some(format!("  DIP M2-{} pick {mint} m2 {:+.4} (>= {:.4}) | IMIT1 {imit_score:.3} {} | age {age:.1}s dump {sell:.2} SOL -{drop:.1}%{} | {:.0} us",
                if self.gate { "GATE" } else { "SHADOW" }, self.score.unwrap_or(f64::NAN), self.min,
                if self.extra { "no IMIT1 dump event (later big sell of the slot)" } else if imit_pass { "also picked" } else { "not picked" }, if dev { if self.gate { " | DEV-LIST (IMIT1 decides)" } else { " | DEV-LIST" } } else { "" }, self.us));
        }
    }
}

impl Drop for M2Dump<'_> {
    /// shadow: the M2 work of this dump, after the IMIT1 decision and any send of this iteration (gate: already done)
    fn drop(&mut self) {
        self.eval();
        if let Some(rec) = self.rec.take() { self.finish(rec); }
        if let Some(l) = self.line.take() { eprintln!("{l}"); }
    }
}

#[cfg(test)]
mod m2_tests {
    use super::*;
    use arbx::dip_model::{Bundle, Tok as M2Tok, Tr};

    fn load(p: &str) -> Option<serde_json::Value> { std::fs::read_to_string(p).ok().and_then(|s| serde_json::from_str(&s).ok()) }

    /// the M2 flags pass the engine's start-up flag check (a wrong spelling is refused; it is built at run time: a "--..."
    /// literal in this file would itself become a known flag); --dip-m2-min may be negative (it is not an arg_f64 flag)
    #[test]
    fn m2_flags_known() {
        let v = |a: &[&str]| a.iter().map(|s| s.to_string()).collect::<Vec<String>>();
        assert!(check_flags(&v(&["snipe_engine", "--dip", "--dip-m2", "/x/m2.json", "--dip-m2-mode", "gate", "--dip-m2-min", "-0.002", "--dip-m2-extra", "off"])).is_ok());
        let wrong = ["-", "-dip-m2-mod"].concat();
        assert!(check_flags(&v(&["snipe_engine", "--dip", &wrong, "gate"])).is_err());
    }

    /// the engine's M2 wiring on the parity tapes: every trade enters the M2 state (non-dump trades directly, the study's
    /// in-envelope dump rows through M2Dump, as dipmode does), in shadow AND gate mode. Both modes give the study's exact score in
    /// the "dump" record; shadow writes the record only when the M2Dump is dropped (after the decision), gate before; a token
    /// with no M2 state is skipped as no_history.
    #[test]
    fn m2_dump_records_shadow_and_gate() {
        let root = env!("CARGO_MANIFEST_DIR");
        let (Some(par), Ok(b)) = (load(&format!("{root}/testdata/dip_m2_parity.json")), Bundle::load(&format!("{root}/testdata/dip_m2_bundle.json"))) else {
            eprintln!("M2 parity data missing: skipped"); return;
        };
        let dir = std::env::temp_dir().join(format!("m2_tests_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        for gate in [false, true] {
            let p = dir.join(format!("dip_{gate}.jsonl"));
            let _ = std::fs::remove_file(&p);
            let log = DipLog::open(Some(p.to_string_lossy().to_string())).unwrap();
            let mut st = M2Stats::default();
            let (mut want, mut n_env) = (Vec::<(String, f64)>::new(), 0usize);
            for tk in par["tokens"].as_array().unwrap().iter().take(60) {
                let s0 = tk["launch"]["slot"].as_u64().unwrap();
                let mut mt = M2Tok::new(s0);
                let dumps: HashMap<usize, &serde_json::Value> = tk["dumps"].as_array().unwrap().iter().filter(|d| d["env"].as_bool().unwrap()).map(|d| (d["k"].as_u64().unwrap() as usize, d)).collect();
                for (k, r) in tk["trades"].as_array().unwrap().iter().enumerate() {
                    let user: Pk = bs58::decode(r[4].as_str().unwrap()).into_vec().unwrap().try_into().unwrap();
                    let t2 = Tr { s: r[0].as_u64().unwrap(), i: r[1].as_u64().unwrap() as u32, j: r[2].as_i64().unwrap() as i32, buy: r[5].as_bool().unwrap(),
                                  sol: r[6].as_u64().unwrap(), tok: r[7].as_u64().unwrap(), vsol: r[8].as_u64().unwrap(), vtok: r[9].as_u64().unwrap(), user };
                    let Some(d) = dumps.get(&k) else { mt.push(&t2, &b.sets); continue };
                    n_env += 1;
                    let sig = format!("{}:{k}", tk["mint"].as_str().unwrap());
                    let before = std::fs::read_to_string(&p).unwrap_or_default().lines().count();
                    {
                        let mut g = M2Dump::new(&b, Some(&mut mt), t2, true, gate, b.thr_default, false, &log, &mut st);
                        assert_eq!(g.score.is_some(), gate, "gate scores at new(), shadow at drop");
                        g.record(serde_json::json!({"ev": "dump", "mint": tk["mint"], "sig": sig}), false, 0.0, 10.0, 1.5, 6.0, true, false);
                        let mid = std::fs::read_to_string(&p).unwrap_or_default().lines().count();
                        assert_eq!(mid, before + gate as usize, "gate writes the record at once, shadow at drop");
                    }
                    want.push((sig, d["score"].as_str().unwrap().parse::<f64>().unwrap()));
                }
            }
            // a dump of a token the engine has no M2 state for
            {
                let t2 = Tr { s: 1, i: 0, j: 0, buy: false, sol: 2_000_000_000, tok: 1, vsol: 40_000_000_000, vtok: 800_000_000_000_000, user: [9; 32] };
                let mut g = M2Dump::new(&b, None, t2, true, gate, b.thr_default, false, &log, &mut st);
                g.record(serde_json::json!({"ev": "dump", "mint": "none", "sig": "none"}), false, 0.0, 10.0, 1.5, 6.0, true, false);
            }
            drop(log);
            let text = std::fs::read_to_string(&p).unwrap();
            let recs: Vec<serde_json::Value> = text.lines().map(|l| serde_json::from_str(l).unwrap()).collect();
            assert_eq!(recs.len(), want.len() + 1);
            let by: HashMap<String, &serde_json::Value> = recs.iter().map(|r| (r["sig"].as_str().unwrap().to_string(), r)).collect();
            // the score as WRITTEN (serde_json's reader can be 1 ulp off; Python's and Rust's str::parse are exact)
            let raw: HashMap<String, f64> = text.lines().filter_map(|l| {
                let v: serde_json::Value = serde_json::from_str(l).ok()?;
                let i = l.find("\"m2\":")? + 5;
                let n: String = l[i..].chars().take_while(|c| c.is_ascii_digit() || matches!(c, '-' | '+' | '.' | 'e' | 'E')).collect();
                Some((v["sig"].as_str()?.to_string(), n.parse::<f64>().ok()?))
            }).collect();
            let mut picks = 0;
            for (sig, s) in &want {
                let r = by[sig];
                assert_eq!(raw[sig], *s, "record score == study score ({sig})");
                assert_eq!(r["m2_feats"].as_array().unwrap().len(), 25);
                assert_eq!(r["m2_pick"].as_bool().unwrap(), *s >= b.thr_default);
                assert_eq!(r["m2_mode"].as_str().unwrap(), if gate { "gate" } else { "shadow" });
                picks += (*s >= b.thr_default) as u64;
            }
            assert_eq!(by["none"]["m2_skip"].as_str(), Some("no_history"));
            assert!(by["none"]["m2"].is_null());
            assert_eq!((st.scored as usize, st.picks), (n_env, picks));
            assert_eq!(st.skipped.get("no_history"), Some(&1));
            eprintln!("m2 wiring ({}): {} in-envelope dumps scored, {} picks, status{}", if gate { "gate" } else { "shadow" }, st.scored, st.picks, st.line(gate));
        }
        let _ = std::fs::remove_dir_all(&dir);
    }
}

#[cfg(test)]
mod presend_tests {
    use super::*;

    fn load(p: &str) -> Option<serde_json::Value> { std::fs::read_to_string(p).ok().and_then(|s| serde_json::from_str(&s).ok()) }
    fn pk32(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }

    /// the pre-send flags pass the start-up check with their values; a wrong spelling (built at run time: a "--..." literal in
    /// this file would itself become a known flag) or a non-number is refused
    #[test]
    fn presend_flags_known() {
        let v = |a: &[&str]| a.iter().map(|s| s.to_string()).collect::<Vec<String>>();
        assert!(check_flags(&v(&["snipe_engine", "--dip", "--presend-shadow", "--presend-whale-pct", "5", "--presend-window-slots", "10", "--presend-drop", "0.12",
            "--presend-ref-ms", "50", "--presend-live-ms", "50", "--presend-size-sol", "0.55", "--presend-exit-slots", "2", "--presend-tp", "0.10", "--presend-sl", "0.20"])).is_ok());
        let wrong = ["-", "-presend-shadw"].concat();
        assert!(check_flags(&v(&["snipe_engine", "--dip", &wrong])).is_err());
        let wrong2 = ["-", "-presend-whale"].concat();
        assert!(check_flags(&v(&["snipe_engine", "--dip", "--presend-shadow", &wrong2, "5"])).is_err());
        assert!(check_flags(&v(&["snipe_engine", "--dip", "--presend-shadow", "--presend-drop", "x"])).is_err());
        assert!(check_flags(&v(&["snipe_engine", "--dip", "--presend-shadow", "--presend-drop", "-0.1"])).is_err());
        assert!(check_flags(&v(&["snipe_engine", "--dip", "--presend-shadow", "--presend-window-slots", "1.5"])).is_err());
        assert!(arbx::presend::Params { drop: 1.5, ..Default::default() }.check().is_err());
        assert!(arbx::presend::Params::default().check().is_ok());
    }

    /// a parity token's executed txs as the engine's feed delivers them: (slot, tx index, signature, ExecInfo) in chain order, the
    /// create in its own tx
    fn token_txs(tk: &serde_json::Value) -> (Pk, Vec<(u64, u64, [u8; 64], arbx::feeds::ExecInfo)>) {
        let mint = pk32(tk["mint"].as_str().unwrap());
        let users: Vec<Pk> = tk["users"].as_array().unwrap().iter().map(|u| pk32(u.as_str().unwrap())).collect();
        let la = &tk["launch"];
        let signer = pk32(la["user"].as_str().unwrap());
        let creator = la["creator"].as_str().map(pk32).unwrap_or(signer);
        let (cs, ci) = (la["slot"].as_u64().unwrap(), la["idx"].as_u64().unwrap_or(0));
        let mut txs: Vec<(u64, u64, [u8; 64], arbx::feeds::ExecInfo)> = Vec::new();
        for r in tk["trades"].as_array().unwrap() {
            let (s, i) = (r[0].as_u64().unwrap(), r[1].as_u64().unwrap());
            if txs.last().map(|t| (t.0, t.1)) != Some((s, i)) {
                let sig: [u8; 64] = bs58::decode(r[3].as_str().unwrap()).into_vec().unwrap().try_into().unwrap();
                txs.push((s, i, sig, arbx::feeds::ExecInfo { index: i, fee: 5000, ok: true, trades: Vec::new(), creates: Vec::new(), mayhem: false }));
            }
            txs.last_mut().unwrap().3.trades.push(arbx::dip::TradeEvent { mint, sol: r[6].as_u64().unwrap(), tok: r[7].as_u64().unwrap(), buy: r[5].as_u64().unwrap() == 1,
                user: users[r[4].as_u64().unwrap() as usize], vsol: r[8].as_u64().unwrap(), vtok: r[9].as_u64().unwrap(), fbps: r[10].as_u64().unwrap_or(0), cbps: r[11].as_u64().unwrap_or(0) });
        }
        let cev = arbx::dip::CreateEvent { mint, bonding_curve: [0; 32], user: signer, creator };
        match txs.iter_mut().find(|t| (t.0, t.1) == (cs, ci)) {
            Some(t) => t.3.creates.push(cev),
            None => { let pos = txs.iter().position(|t| (t.0, t.1) > (cs, ci)).unwrap_or(txs.len());
                      txs.insert(pos, (cs, ci, [1; 64], arbx::feeds::ExecInfo { index: ci, fee: 5000, ok: true, trades: Vec::new(), creates: vec![cev], mayhem: false })); }
        }
        (mint, txs)
    }

    /// TIMING of the engine's wiring on a whole study day (PRESEND_PARITY_FULL=FILE from ps12_parity.py --full R4): every token's
    /// txs merged in chain order, each through `presend_tx` as the engine calls it (records written to a file): time per call
    #[test]
    fn presend_tx_timing_full_day() {
        let Ok(path) = std::env::var("PRESEND_PARITY_FULL") else { eprintln!("PRESEND_PARITY_FULL not set: skipped"); return; };
        let par = load(&path).expect("PRESEND_PARITY_FULL unreadable");
        let mut all: Vec<(u64, u64, [u8; 64], arbx::feeds::ExecInfo)> = Vec::new();
        for tk in par["tokens"].as_array().unwrap() { all.extend(token_txs(tk).1); }
        all.sort_by_key(|t| (t.0, t.1));
        let dir = std::env::temp_dir().join(format!("presend_timing_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let p = dir.join("dip.jsonl");
        // PRESEND_TIMING_NOLOG=1: the same without a log file (the shadow's own work only)
        let nolog = std::env::var("PRESEND_TIMING_NOLOG").is_ok();
        let log = DipLog::open(if nolog { None } else { Some(p.to_string_lossy().to_string()) }).unwrap();
        let mut ps = arbx::presend::Shadow::new(arbx::presend::Params::default());
        let mut tm = PresendTime::default();
        let mut slot_now = 0u64;
        let mut marks: Vec<[u64; 5]> = Vec::new();
        for (s, _, sig, x) in &all {
            slot_now = slot_now.max(*s);
            let t0 = Instant::now();
            for _ in 0..=x.trades.len() { marks.push([0; 5]); }
            presend_tx(&mut ps, *s, slot_now, x, sig, 1, &marks, &log);
            marks.clear();
            tm.add(t0.elapsed().as_secs_f64() * 1e6, x.trades.len());
        }
        ps.finish();
        for ev in ps.drain() { log.w(ev.rec); }
        drop(log);
        let n = std::fs::read_to_string(&p).map(|t| t.lines().count()).unwrap_or(0);
        // the library alone (no records written, no terminal lines), twice in this process: the second pass runs on warm memory
        // (a long-running engine's case: freed memory is reused)
        for pass in 1..=2 {
            let mut ps2 = arbx::presend::Shadow::new(arbx::presend::Params::default());
            let (mut t_lib, mut slow, mut slow_adv, mut worst) = (PresendTime::default(), 0u64, 0u64, (0f64, 0usize, 0u64));
            let mut sn = 0u64;
            for (s, _, sig, x) in &all {
                let adv = *s > sn; sn = sn.max(*s);
                let t0 = Instant::now();
                for c in &x.creates { ps2.create(c.mint, *s, c.creator, c.user, false, 1); }
                for (j, e) in x.trades.iter().enumerate() {
                    ps2.push(arbx::presend::In { mint: e.mint, s: *s, i: x.index as u32, j: j as i32, sig: *sig, user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol,
                                                 vtok: e.vtok, fbps: e.fbps, cbps: e.cbps, t_rx: 1, flags: 0 });
                }
                ps2.advance(sn);
                let nev = ps2.drain().len();
                let us = t0.elapsed().as_secs_f64() * 1e6;
                t_lib.add(us, x.trades.len());
                if us > 50.0 { slow += 1; if adv { slow_adv += 1; } if us > worst.0 { worst = (us, nev, *s); } }
            }
            eprintln!("presend library alone, pass {pass}:{} | over 50 us: {slow} ({slow_adv} on a new slot), worst {:.0} us ({} records then)", t_lib.line(), worst.0, worst.1);
        }
        let _ = std::fs::remove_dir_all(&dir);
        eprintln!("presend wiring timing: {} executed txs{} | {n} records{}", all.len(), tm.line(), ps.line());
    }

    /// the engine's wiring (`presend_tx`, one executed tx at a time) writes exactly the library's records to --dip-log, and the
    /// reactive bot's marks on a trade reach the fill records of that trade only
    #[test]
    fn presend_tx_records() {
        let root = env!("CARGO_MANIFEST_DIR");
        let Some(par) = load(&format!("{root}/testdata/presend_parity.json")) else { eprintln!("presend_parity.json missing: skipped"); return; };
        let dir = std::env::temp_dir().join(format!("presend_tests_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let (mut n_tok, mut n_recs, mut n_marked) = (0, 0, 0);
        for tk in par["tokens"].as_array().unwrap() {
            if !tk["windows"].as_array().unwrap().iter().any(|w| w["rows"]["c"]["fill"]["valid"].as_bool() == Some(true) && w["rows"]["c"]["armed"].as_bool() == Some(true)) { continue; }
            if n_tok == 25 { break; }
            n_tok += 1;
            let (mint, txs) = token_txs(tk);
            // run 1: no marks; the first row-c fill's crossing trade becomes the marked trade of run 2
            // the lines as written (compared as text: serde_json's reader can be 1 ulp off; Python's, the evaluator's, is exact)
            let run = |mark: Option<(u64, u64, i64)>, path: &std::path::Path| -> Vec<String> {
                let _ = std::fs::remove_file(path);
                let log = DipLog::open(Some(path.to_string_lossy().to_string())).unwrap();
                let mut ps = arbx::presend::Shadow::new(arbx::presend::Params::default());
                for (s, i, sig, x) in &txs {
                    let mut c = [0u64; 5]; let mut marks = Vec::new();
                    for j in 0..x.trades.len() {
                        marks.push(c);
                        if mark == Some((*s, *i, j as i64)) { for v in c.iter_mut() { *v += 1; } }
                    }
                    marks.push(c);
                    presend_tx(&mut ps, *s, *s, x, sig, 7, &marks, &log);
                }
                ps.complete();
                for ev in ps.drain() { log.w(ev.rec); }
                drop(log);
                std::fs::read_to_string(path).unwrap().lines().map(|l| l.to_string()).collect()
            };
            let parse = |v: &[String]| -> Vec<serde_json::Value> { v.iter().map(|l| serde_json::from_str(l).unwrap()).collect() };
            let p = dir.join("dip.jsonl");
            let r1s = run(None, &p);
            let r1 = parse(&r1s);
            let f = r1.iter().find(|r| r["ev"] == "presend_fill" && r["row"] == "c").expect("the study fills row c on this token");
            let mark = (f["x"]["slot"].as_u64().unwrap(), f["x"]["idx"].as_u64().unwrap(), f["x"]["j"].as_i64().unwrap());
            let r2 = parse(&run(Some(mark), &p));
            // the library's own records for the same feed
            let mut ps = arbx::presend::Shadow::new(arbx::presend::Params::default());
            for (s, _, sig, x) in &txs {
                for c in &x.creates { ps.create(c.mint, *s, c.creator, c.user, false, 7); }
                for (j, e) in x.trades.iter().enumerate() {
                    ps.push(arbx::presend::In { mint, s: *s, i: x.index as u32, j: j as i32, sig: *sig, user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok,
                                                fbps: e.fbps, cbps: e.cbps, t_rx: 7, flags: 0 });
                }
                ps.advance(*s);
            }
            ps.complete();
            let lib: Vec<String> = ps.drain().into_iter().map(|e| e.rec.to_string()).collect();
            assert_eq!(r1s, lib, "the engine's records differ from the library's ({})", tk["mint"]);
            assert_eq!(r1.len(), r2.len());
            for (a, b) in r1.iter().zip(r2.iter()) {
                if a["ev"] == "presend_fill" {
                    let on = (a["x"]["slot"].as_u64().unwrap(), a["x"]["idx"].as_u64().unwrap(), a["x"]["j"].as_i64().unwrap()) == mark;
                    for k in ["dump", "env", "pick", "fired", "m2"] {
                        assert_eq!(a["imit"][k], false);
                        assert_eq!(b["imit"][k], on, "mark {k} on the fill at {mark:?}");
                    }
                    n_marked += on as usize;
                    let (mut a2, mut b2) = (a.clone(), b.clone());
                    a2["imit"] = serde_json::Value::Null; b2["imit"] = serde_json::Value::Null;
                    assert_eq!(a2, b2);
                } else { assert_eq!(a, b); }
            }
            n_recs += r1.len();
        }
        let _ = std::fs::remove_dir_all(&dir);
        eprintln!("presend wiring: {n_tok} tokens, {n_recs} records identical to the library's, {n_marked} fill records carry the reactive bot's marks");
        assert!(n_tok >= 10 && n_marked >= 10);
    }
}

#[cfg(test)]
mod defer_tests {
    use super::*;

    /// B2 (dip14) MEASUREMENT, run by hand: `cargo test --release --bin snipe_engine defer_hot_path_cost -- --ignored --nocapture`.
    /// The executed path's dump + pick records (the same json! expressions, realistic values) built and written to a --dip-log file
    /// (a) at once with a flush each, as dip13 does before the sends, (b) held (built only; the write happens after the sends);
    /// and the per-buy key derivations prepare does (fast vs dalek ATA). Times per buy, this machine.
    #[test]
    #[ignore]
    fn defer_hot_path_cost() {
        let dir = std::env::temp_dir().join(format!("defer_cost_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let p = dir.join("dip.jsonl");
        let log = DipLog::open(Some(p.to_string_lossy().to_string())).unwrap();
        let n = 3000usize;
        let feats: [f64; 42] = std::array::from_fn(|i| (i as f64 * 1.37).sin() * 100.0 + 0.123456789);
        let mint: Pk = [7; 32];
        let sig = "4YsCCYitRJQ2wr1r6bnjeQjLhCKafYvo5bH1UNsg3TLnSFzaQu1Jxe1nXoRwYRiYbcmaXXBrRfRNze9AgasL2Ffc".to_string();
        let paths = vec!["nozomi".to_string(), "helius-swqos".to_string(), "landx-fra3".to_string(), "staked-rpc".to_string()];
        let build = |i: usize| -> (serde_json::Value, serde_json::Value) {
            let dump_rec = serde_json::json!({"ev": "dump", "mint": b58(&mint), "sig": sig, "slot": 461066304u64 + i as u64, "idx": 210, "t": 1792890727605937418u64 + i as u64,
                "age": feats[0], "sell": feats[1], "drop_pct": feats[2], "score": -0.7893482073165923, "thr": 0.21088520504965255, "pass": true, "launch_ok": true,
                "vsol": 32881911007u64, "vtok": 978957701200960u64, "dev": false});
            let kind = Some(serde_json::json!({"v2": true, "mayhem": false, "cashback": false, "holder": true, "cfee_bps": 0}));
            let pick = serde_json::json!({"ev": "pick", "mint": b58(&mint), "sig": sig, "slot": 461066304u64 + i as u64, "idx": 210, "t": 1792890727605937418u64, "score": 0.73, "age": 7.42,
                "min_out": 1840809047694u64, "route": "route:harmonic", "leader": "5ZqveVffQPiUbkjBg4KD9kib1MKHLqiFno4ke9jSq9qk", "client": "HarmonicAgave",
                "paths": paths.clone(), "kind": kind, "feats": feats.to_vec(), "dev": false, "spend": 350_000_000u64});
            (dump_rec, pick)
        };
        let pct = |v: &mut Vec<f64>, q: f64| { v.sort_by(|a, b| a.partial_cmp(b).unwrap()); v[((v.len() - 1) as f64 * q) as usize] };
        // warm up
        for i in 0..200 { let (a, b) = build(i); log.w(a); log.w(b); }
        let (mut inline, mut built, mut ata_d, mut ata_f) = (Vec::new(), Vec::new(), Vec::new(), Vec::new());
        let held = Held { on: true, v: std::cell::RefCell::new(Vec::new()) };
        for i in 0..n {
            let t0 = Instant::now();
            let (a, b) = build(i);
            log.w(a); log.w(b);
            inline.push(t0.elapsed().as_secs_f64() * 1e6);
            let t1 = Instant::now();
            let (a, b) = build(i);
            held.w(&log, a); held.w(&log, b);
            built.push(t1.elapsed().as_secs_f64() * 1e6);
            held.flush(&log);                       // after the sends: not on the hot path
            let user: Pk = [9; 32];
            let m: Pk = { let mut x = [0u8; 32]; x[..8].copy_from_slice(&(i as u64).to_le_bytes()); x[31] = 3; x };
            let t2 = Instant::now();
            let _ = (pda::ata(&m, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), pda::ata(&user, &m, &pda::TOKEN_2022));
            ata_d.push(t2.elapsed().as_secs_f64() * 1e6);
            let t3 = Instant::now();
            let _ = (arbx::fast::ata_fast(&m, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), arbx::fast::ata_fast(&user, &m, &pda::TOKEN_2022));
            ata_f.push(t3.elapsed().as_secs_f64() * 1e6);
        }
        drop(log);
        let lines = std::fs::read_to_string(&p).unwrap().lines().count();
        eprintln!("B2 hot-path cost per buy ({n} buys, this machine, µs p50 / p90 / p99):");
        eprintln!("  dump + pick records built AND written + flushed (dip13, before the sends): {:.1} / {:.1} / {:.1}", pct(&mut inline, 0.5), pct(&mut inline, 0.9), pct(&mut inline, 0.99));
        eprintln!("  the same records only built (--dip-defer: written after the sends):       {:.1} / {:.1} / {:.1}", pct(&mut built, 0.5), pct(&mut built, 0.9), pct(&mut built, 0.99));
        eprintln!("  the two ATAs of a buy, dalek / fast derive:                               {:.1} / {:.1}", pct(&mut ata_d, 0.5), pct(&mut ata_f, 0.5));
        assert_eq!(lines, 400 + 4 * n);
        let _ = std::fs::remove_dir_all(&dir);
    }

    /// D1 (dip14): timing_rec2 on a synthetic slot: PoH position = hashes / the slot's total, the block clocks with the real size
    /// and 400, the entries feed's and every feed's arrival differences, both block indexes
    #[test]
    fn clock2_timing_record() {
        let pi = arbx::feeds::poh_index();
        let slot = 4_000_000_123u64;
        let (mut ds, mut bs) = ([0u8; 64], [0u8; 64]);
        ds[..8].copy_from_slice(&0xD00Du64.to_be_bytes()); bs[..8].copy_from_slice(&0xB0B0u64.to_be_bytes());
        let ph = |h: u64| arbx::feeds::entries::Poh { slot, hashes: h, ticks: 0, hpt: 400 };
        pi.insert_many(&[(0xD00D, ph(100))], 3, 1_000_000);
        pi.insert_many(&[(0xB0B0, ph(300))], 3, 21_000_000);
        pi.slot_note(arbx::feeds::SlotTot { slot, feed: 3, hashes: 400, ticks: 1, entries: 50, txs: 800, t_first: 0, t_last: 0, valid: true });
        let p = Pend { kind: "fire", mint: "m".into(), buy_sig: bs58::encode(bs).into_string(), dump_sig_b: ds, buy_sig_b: bs, t_dump_rx: 2_000_000, t_fire: 3_000_000,
                       due: Instant::now(), more: Vec::new(), via: "shred", win: None, tag: 0 };
        let names = vec!["kaldera".to_string(), "turbo-kaldera".to_string(), "kaldera-tx".to_string(), "erpc".to_string()];
        let mut first = rustc_hash::FxHashMap::default(); first.insert(0xD00Du64, (1_500_000u64, 0u16)); first.insert(0xB0B0u64, (20_500_000u64, 1u16));
        let mut fs = rustc_hash::FxHashMap::default();
        fs.insert(0xD00Du64, [1_500_000u64, 1_600_000, 2_000_000, 1_000_000, 0, 0, 0, 0]);
        fs.insert(0xB0B0u64, [20_700_000u64, 20_500_000, 22_000_000, 21_000_000, 0, 0, 0, 0]);
        let mut ex = rustc_hash::FxHashMap::default(); ex.insert(0xD00Du64, (slot, 200u64));
        let mut ow = rustc_hash::FxHashMap::default(); ow.insert(0xB0B0u64, (slot, 600u64));
        let j = timing_rec2(&p, &first, &names, &fs, &ex, &ow);
        let c = &j["clock2"];
        let sm = j["slot_ms"].as_f64().unwrap();
        assert_eq!(j["via"], "shred");
        assert_eq!((c["dump_idx"].as_u64(), c["buy_idx"].as_u64(), c["dump_slot_txs"].as_u64()), (Some(200), Some(600), Some(800)));
        assert_eq!((c["dump_pos"].as_f64(), c["buy_pos"].as_f64()), (Some(0.25), Some(0.75)));
        assert!((c["land_ms_pos"].as_f64().unwrap() - 0.5 * sm).abs() < 1e-9);
        assert!((c["land_ms_bmix"].as_f64().unwrap() - (600.0 / 800.0 - 200.0 / 800.0) * sm).abs() < 1e-9);
        assert!((c["land_ms_b400"].as_f64().unwrap() - (600.0 / 601.0 - 200.0 / 400.0) * sm).abs() < 1e-9);
        assert_eq!(c["land_ms_ent"].as_f64(), Some(20.0));
        assert_eq!(c["feeds"]["kaldera"][2].as_f64(), Some(19.2));
        assert_eq!(c["feeds"]["kaldera-tx"][2].as_f64(), Some(20.0));
        assert!(c["feeds"].get("x").is_none());
    }

    /// B2 (dip14): the token's keys derived once (var_keys_of) = the per-buy derivation, dalek and fast, create_v2 or not
    #[test]
    fn var_keys_equal_per_buy_derivation() {
        let user: Pk = [0x42; 32];
        for i in 0..300u64 {
            let mut m = [0u8; 32]; m[..8].copy_from_slice(&i.to_le_bytes()); m[31] = 0x5a;
            let mut l = snipe_build::launch_from_target(m, [7u8; 32]);
            if i % 2 == 0 { l.is_create_v2 = false; }
            let bc = l.bonding_curve;
            let abc = if l.is_create_v2 { l.assoc_bonding_curve } else { pda::ata(&bc, &l.mint, &pda::TOKEN_2022) };
            let want: arbx::fast::VarKeys = [l.mint, bc, abc, pda::ata(&bc, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), pda::ata(&user, &l.mint, &pda::TOKEN_2022), l.buyback_fee_recipient];
            assert_eq!(fastfire::var_keys_of(user, false, &l), want);
            assert_eq!(fastfire::var_keys_of(user, true, &l), want);
        }
    }

    /// B2 (dip14): the held records are written in the same order and with the same bytes as the immediate ones (two logs, the same
    /// sequence of writes and flush points)
    #[test]
    fn defer_records_identical() {
        let dir = std::env::temp_dir().join(format!("defer_same_{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let (pa, pb) = (dir.join("a.jsonl"), dir.join("b.jsonl"));
        let (la, lb) = (DipLog::open(Some(pa.to_string_lossy().to_string())).unwrap(), DipLog::open(Some(pb.to_string_lossy().to_string())).unwrap());
        let (ha, hb) = (Held { on: false, v: std::cell::RefCell::new(Vec::new()) }, Held { on: true, v: std::cell::RefCell::new(Vec::new()) });
        for i in 0..500u64 {
            for (h, l) in [(&ha, &la), (&hb, &lb)] {
                h.flush(l);                                                  // top of a trade
                h.w(l, serde_json::json!({"ev": "dump", "i": i, "x": i as f64 / 7.0}));
                if i % 3 == 0 { h.w(l, serde_json::json!({"ev": "pick_skip", "i": i})); continue; }
                h.w(l, serde_json::json!({"ev": "pick", "i": i, "feats": [1.5, i as f64 / 3.0]}));
                if i % 2 == 0 { h.flush(l); l.w(serde_json::json!({"ev": "fire", "i": i})); }   // a fire: held first, then the fire record
            }
        }
        ha.flush(&la); hb.flush(&lb);
        drop(la); drop(lb);
        assert_eq!(std::fs::read(&pa).unwrap(), std::fs::read(&pb).unwrap());
        let _ = std::fs::remove_dir_all(&dir);
    }
}

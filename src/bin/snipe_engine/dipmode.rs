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
}

/// one followed token
struct Tok { book: TokenBook, launch: Option<Launch>, t_created: Instant, last_pick_slot: Option<u64>, dev: bool }

/// a fired buy and its position
struct LivePos {
    mint: Pk, launch: Launch, dump_sig: String, dump_slot: u64, dump_idx: u64, t_dump_rx: u64, dump_vsol: u64, dump_vtok: u64,
    score: f64, t_fire_ns: u64, buy_sig: String, buy_sig_b: [u8; 64], route: String, leader: String, client: String, tips: u64,
    spend: u64, min_out: u64, send_slot: u64,
    land: Option<(u64, u64, u64)>, tokens: u64, sol_in: u64, buy_ok: Option<bool>,
    exit: Option<(&'static str, u64, f64, u64)>, sell_land: Option<(u64, u64, u64, u64)>,
    pos: Option<Pos>, fired_at: Instant,
}

enum Msg { Land(Pk, Landed), Sold(Pk, SellOut) }

const TXC: f64 = 0.0008;    // the replay's per-tx cost (value math for TP / SL, as the study)

pub async fn run_dip(probe: &Probe, key: &SigningKey, user: Pk, rpc: &Arc<rpc::Rpc>, path: &Arc<send::Path>, live: bool, stop: &Arc<AtomicBool>) -> Result<()> {
    let model_p = arg("--dip-model").unwrap_or_else(|| "/root/dip/IMIT1.json".into());
    let model = Imit::load(&model_p).map_err(|e| anyhow::anyhow!("--dip-model: {e}"))?;
    let cohort_p = arg("--dip-cohort").unwrap_or_else(|| "/root/dip/cohort_train.json".into());
    let cohort: HashSet<String> = serde_json::from_str::<Vec<String>>(&std::fs::read_to_string(&cohort_p).with_context(|| format!("--dip-cohort {cohort_p}"))?)?.into_iter().collect();
    let targets: HashSet<String> = di::TARGETS.iter().map(|s| s.to_string()).collect();
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
    let me = b58(&user);
    eprintln!("\nDIP {} | model {} tier {tier} (score >= {thr:.4}) | exit {tp_s} / SL -{:.0}% / {hold} slots | guard x{guard} | spend {:.3} SOL | max buys {max_buys} | max open {max_inflight} | loss cap {} | {minutes} min",
        if live { "LIVE" } else { "SHADOW (no sends)" }, model.g.name, sl * 100.0, spend as f64 / 1e9,
        if live { format!("{:.3} SOL", loss_cap as f64 / 1e9) } else { "-".into() });
    if !devs.is_empty() { eprintln!("DIP dev list: {} wallet(s) -> their tokens: tier {dev_tier} (score >= {thr_dev:.4}), spend {:.3} SOL", devs.len(), dev_spend as f64 / 1e9); }
    log.w(serde_json::json!({"ev": "run_start", "t": arbx::feeds::clock::now_ns(), "live": live, "wallet": me, "model": model.g.name, "tier": tier, "thr": thr, "tp": tp, "sl": sl,
        "hold_slots": hold, "guard": guard, "allow_holder": allow_holder, "spend": spend, "max_buys": max_buys, "max_inflight": max_inflight, "loss_cap": if live { loss_cap } else { 0 }, "minutes": minutes,
        "devs": devs.iter().collect::<Vec<_>>(), "dev_tier": dev_tier, "thr_dev": thr_dev, "dev_spend": dev_spend}));

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
    { let rx = rx.clone(); std::thread::spawn(move || { while let Ok(ev) = rx.recv() { if atx.send(ev).is_err() { break; } } }); }
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
    let mut open: HashMap<Pk, LivePos> = HashMap::new();
    let (mut n_dumps, mut n_env, mut n_picks, mut n_fired, mut n_closed, mut skipped) = (0u64, 0u64, 0u64, 0u64, 0u64, HashMap::<&'static str, u64>::new());
    let mut last_status = Instant::now();
    let mut slot_now = 0u64;
    let key_arc = Arc::new(key.clone());
    let ss = |_s: u64| -> Option<u64> { None };           // block sizes are unknown live (parity: 1 of 55 picks flips)
    loop {
        let stopping = Instant::now() >= deadline || stop.load(Ordering::Relaxed) || DIP_NO_FIRE.load(Ordering::Relaxed)
            || (max_buys > 0 && ACCT.landed_buys.load(Ordering::SeqCst) >= max_buys)
            || probe_done_at.is_some_and(|t| t.elapsed() > Duration::from_secs(5));
        if stopping && open.is_empty() { break; }
        if stopping && !DIP_NO_FIRE.swap(true, Ordering::SeqCst) { eprintln!("  DIP: no new buys from here (end of run reached); {} position(s) finishing", open.len()); }
        // positions + feed, whichever first
        let ev = tokio::select! {
            m = mrx.recv() => { if let Some(m) = m { on_msg(m, &mut open, &log, &mut n_closed, rpc); } continue; }
            e = tokio::time::timeout(Duration::from_millis(500), arx.recv()) => match e {
                Ok(Some(e)) => e,
                // every feed died: never leave a position behind; the wall-clock backstop in time_exits sells it
                Ok(None) => {
                    if open.is_empty() { break; }
                    tokio::time::sleep(Duration::from_millis(200)).await;
                    time_exits(&mut open, slot_now, hold, &log, &key_arc, user, rpc, path, &mtx);
                    continue;
                }
                Err(_) => { time_exits(&mut open, slot_now, hold, &log, &key_arc, user, rpc, path, &mtx); continue }
            },
        };
        if last_status.elapsed() > Duration::from_secs(60) {
            last_status = Instant::now();
            eprintln!("  DIP status: tokens {} dumps {n_dumps} in-envelope {n_env} picks {n_picks} fired {n_fired} closed {n_closed} open {} slot {slot_now} skipped {:?}", toks.len(), open.len(), skipped);
            let cutoff = Duration::from_secs_f64(max_age_s + 300.0);
            toks.retain(|m, t| t.t_created.elapsed() < cutoff || open.contains_key(m));
        }
        let arbx::feeds::Event::Tx(a) = ev else { continue };
        let t_loop = arbx::feeds::clock::now_ns();     // the decision-time breakdown of a fire (lat_us in the fire record)
        {
            let k8 = u64::from_be_bytes(a.tx.sig[..8].try_into().unwrap());
            if let std::collections::hash_map::Entry::Vacant(v) = first_seen.entry(k8) { v.insert((a.t_rx, a.feed)); first_order.push_back((a.t_rx, k8)); }
            while first_order.front().is_some_and(|&(t, _)| a.t_rx.saturating_sub(t) > 30_000_000_000) { let (_, k) = first_order.pop_front().unwrap(); first_seen.remove(&k); }
        }
        if !pend.is_empty() && last_pend_check.elapsed() > Duration::from_millis(500) {
            last_pend_check = Instant::now();
            let now_i = Instant::now();
            pend.retain(|p| { if p.due > now_i { return true; } log.w(timing_rec(p, &first_seen, &feed_names)); false });
        }
        slot_now = slot_now.max(a.slot);
        // our own buy failed on chain (no TradeEvent, so no exec info): the executed feed says so first
        if a.executed == Some(false) && !probe_sigs.is_empty() {
            if let Some((mint_s, t_dump)) = probe_sigs.remove(&a.tx.sig) {
                log.w(serde_json::json!({"ev": "probe_land", "mint": mint_s, "sig": bs58::encode(&a.tx.sig).into_string(), "slot": a.slot, "t": a.t_rx,
                    "ms_after_dump_feed": (a.t_rx as i64 - t_dump as i64) as f64 / 1e6}));
            }
        }
        if a.executed == Some(false) && a.exec.is_none() {
            if let Some(p) = open.values_mut().find(|p| p.buy_sig_b == a.tx.sig && p.buy_ok.is_none()) {
                p.buy_ok = Some(false);
                log.w(serde_json::json!({"ev": "buy_failed", "mint": b58(&p.mint), "sig": p.buy_sig, "slot": a.slot, "t": a.t_rx}));
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
            toks.insert(mint, Tok { book: TokenBook::new(li), launch, t_created: Instant::now(), last_pick_slot: None, dev });
        }
        // trades
        for (j, e) in x.trades.iter().enumerate() {
            let user_s = b58(&e.user);
            // our own trades: buy landed / sell landed
            if e.user == user {
                if let Some(p) = open.get_mut(&e.mint) {
                    if e.buy && p.land.is_none() {
                        p.land = Some((a.slot, x.index, a.t_rx)); p.tokens = e.tok; p.sol_in = e.sol; p.buy_ok = Some(true);
                        let cost = p.spend + x.fee + p.tips;
                        if let Some(pos) = p.pos.as_mut() { pos.landed(cost, a.slot); }
                        log.w(serde_json::json!({"ev": "buy_land", "mint": b58(&e.mint), "sig": sig, "slot": a.slot, "idx": x.index, "t": a.t_rx, "tokens": e.tok, "sol": e.sol,
                            "fee": x.fee, "slots_after_dump": a.slot as i64 - p.dump_slot as i64, "rx_ms_after_dump": (a.t_rx as i64 - p.t_dump_rx as i64) as f64 / 1e6,
                            "vsol": e.vsol, "vtok": e.vtok}));
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
            let Some(k) = dump_k else { continue };
            n_dumps += 1;
            let t_d0 = arbx::feeds::clock::now_ns();
            let d = tk.book.dump(&b58(&e.mint), k, &model, &cohort, &ss);
            let t_d1 = arbx::feeds::clock::now_ns();
            if !d.env_ok { continue; }
            n_env += 1;
            let (thr_t, spend_p) = if tk.dev { (thr_dev, dev_spend) } else { (thr, spend) };
            let pass = d.launch_ok && d.score >= thr_t;
            let tr = &tk.book.tr[k];
            log.w(serde_json::json!({"ev": "dump", "mint": b58(&e.mint), "sig": sig, "slot": a.slot, "idx": x.index, "t": a.t_rx, "age": d.age, "sell": d.feats[1],
                "drop_pct": d.feats[2], "score": d.score, "thr": thr_t, "pass": pass, "launch_ok": d.launch_ok, "vsol": tr.vsol, "vtok": tr.vtok, "dev": tk.dev}));
            if probe_n > 0 {
                if live && probes_fired < probe_n && d.launch_ok && last_probe.is_none_or(|t| t.elapsed() >= probe_gap) && !DIP_NO_FIRE.load(Ordering::Relaxed) {
                    let ok_kind = tk.launch.as_ref().is_some_and(|l| l.is_create_v2 && (l.is_vanilla() || (allow_holder && l.is_holder_reward && !l.is_mayhem && !l.is_cashback && l.creator_fee_bps == 0)));
                    let lead_ok = near.as_ref().is_none_or(|n| n.contains(&lat::buy_paths(path, ALSO_PATH.get(), Some(a.slot)).1.leader));
                    if let (true, true, Some(launch), Some(f)) = (ok_kind, lead_ok, tk.launch.clone(), fast) {
                        let t0 = arbx::feeds::clock::now_ns();
                        let force = if probe_paths.is_empty() { None } else {
                            let name = &probe_paths[(probes_fired as usize) % probe_paths.len()];
                            f.fps.iter().find(|fp| &fp.path.name == name).map(|fp| vec![fp.path.clone()])
                        };
                        match f.prepare_on(&launch, a.slot, u64::MAX, [a.t_rx, a.t_decoded, t0, t0, t0, t0], force, None) {
                            Ok(prep) => {
                                let rec = f.fire(&prep);
                                let t_fire = arbx::feeds::clock::now_ns();
                                probes_fired += 1; last_probe = Some(Instant::now());
                                if probes_fired >= probe_n { probe_done_at = Some(Instant::now()); }
                                probe_sigs.insert(prep.sig, (b58(&e.mint), a.t_rx));
                                pend.push(Pend { kind: "probe", mint: b58(&e.mint), buy_sig: prep.meta.sig.clone(), dump_sig_b: a.tx.sig, buy_sig_b: prep.sig, t_dump_rx: a.t_rx, t_fire,
                                                 due: Instant::now() + Duration::from_secs(2) });
                                log.w(serde_json::json!({"ev": "probe", "n": probes_fired, "mint": b58(&e.mint), "dump_sig": sig, "slot": a.slot, "idx": x.index, "t_dump_rx": a.t_rx,
                                    "t_fire": t_fire, "decision_us": (t_fire as i64 - a.t_rx as i64) as f64 / 1e3, "buy_sig": prep.meta.sig, "route": prep.meta.route,
                                    "leader": prep.meta.leader, "client": prep.meta.client, "tips": prep.meta.tips, "score": d.score, "deadline": prep.deadline,
                                    "writes": rec.w.iter().map(|(n, k, a0, a1, st)| serde_json::json!({"path": n, "kind": k, "t0": a0, "t1": a1, "st": st})).collect::<Vec<_>>()}));
                                eprintln!("  DIP PROBE #{probes_fired} {} | route {} leader {} ({}) | {}", b58(&e.mint), prep.meta.route, &prep.meta.leader[..8.min(prep.meta.leader.len())], prep.meta.client, prep.meta.sig);
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
            let skip = |why: &'static str, sk: &mut HashMap<&'static str, u64>| { *sk.entry(why).or_default() += 1; log.w(serde_json::json!({"ev": "pick_skip", "mint": b58(&e.mint), "sig": sig, "why": why, "kind": kind})); };
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
            log.w(serde_json::json!({"ev": "pick", "mint": b58(&e.mint), "sig": sig, "slot": a.slot, "idx": x.index, "t": a.t_rx, "score": d.score, "age": d.age,
                "min_out": min_out, "route": meta.route, "leader": meta.leader, "client": meta.client, "paths": fan.iter().map(|p| p.name.clone()).collect::<Vec<_>>(),
                "kind": kind, "feats": d.feats.to_vec(), "dev": tk.dev, "spend": spend_p}));
            if !live { continue; }
            if DIP_NO_FIRE.load(Ordering::Relaxed) { skip("no_new_buys", &mut skipped); continue; }
            if open.contains_key(&e.mint) { skip("open_on_token", &mut skipped); continue; }
            if open.len() >= max_inflight { skip("max_open", &mut skipped); continue; }
            if KS_PAUSE.load(Ordering::Relaxed) || FIRE_PAUSE.load(Ordering::Relaxed) { skip("paused", &mut skipped); continue; }
            let bal = ACCT.bal.load(Ordering::SeqCst);
            if bal > 0 && bal < spend_p + 30_000_000 + ACCT.reserved.load(Ordering::SeqCst) { skip("balance", &mut skipped); continue; }
            // FIRE
            let f = fast.expect("checked above");
            let t0 = arbx::feeds::clock::now_ns();
            let prep = match f.prepare_on(&launch, a.slot, min_out, [a.t_rx, a.t_decoded, t0, t0, t0, t0], None, Some(spend_p)) { Ok(p) => p, Err(err) => { eprintln!("  DIP prepare {} failed: {err:#}", b58(&e.mint)); skip("prepare_failed", &mut skipped); continue; } };
            let t_p1 = arbx::feeds::clock::now_ns();
            let rec = f.fire(&prep);
            n_fired += 1;
            let pos = Pos::new(e.mint, spend_p, 5_000 + prep.meta.tips + arg_u64("--cu-limit", 120_000) * arg_u64("--cu-price-micro", 3_000_000) / 1_000_000, &prep.meta.sig);
            let t_fire = arbx::feeds::clock::now_ns();
            pend.push(Pend { kind: "fire", mint: b58(&e.mint), buy_sig: prep.meta.sig.clone(), dump_sig_b: a.tx.sig, buy_sig_b: prep.sig, t_dump_rx: a.t_rx, t_fire,
                             due: Instant::now() + Duration::from_secs(3) });
            log.w(serde_json::json!({"ev": "fire", "mint": b58(&e.mint), "dump_sig": sig, "buy_sig": prep.meta.sig, "slot": a.slot, "t_dump_rx": a.t_rx, "t_fire": t_fire,
                "decision_us": (t_fire as i64 - a.t_rx as i64) as f64 / 1e3, "lat_us": {"queue": (t_loop as i64 - a.t_rx as i64) as f64 / 1e3, "book": (t_d0 as i64 - t_loop as i64) as f64 / 1e3,
                    "score": (t_d1 as i64 - t_d0 as i64) as f64 / 1e3, "checks_logs": (t0 as i64 - t_d1 as i64) as f64 / 1e3, "prepare": (t_p1 as i64 - t0 as i64) as f64 / 1e3,
                    "fire": (t_fire as i64 - t_p1 as i64) as f64 / 1e3}, "route": prep.meta.route, "leader": prep.meta.leader, "client": prep.meta.client,
                "tips": prep.meta.tips, "min_out": min_out, "spend": spend_p, "dev": tk.dev, "deadline": prep.deadline,
                "writes": rec.w.iter().map(|(n, k, a0, a1, st)| serde_json::json!({"path": n, "kind": k, "t0": a0, "t1": a1, "st": st})).collect::<Vec<_>>()}));
            eprintln!("  DIP FIRE {} score {:.3} age {:.1}s dump {:.2} SOL -{:.1}% | {:.2} SOL{} | route {} leader {} ({}) | buy {}", b58(&e.mint), d.score, d.age, d.feats[1], d.feats[2],
                spend_p as f64 / 1e9, if tk.dev { " DEV-LIST" } else { "" }, prep.meta.route, &prep.meta.leader[..8.min(prep.meta.leader.len())], prep.meta.client, prep.meta.sig);
            // the RPC land poll runs beside the executed feed (whichever sees the landing first; the poll also classifies failures)
            {
                let (rpc2, mtx2, sigs, sigb, slot, bhv, mint) = (rpc.clone(), mtx.clone(), prep.meta.sig.clone(), prep.sig, a.slot, prep.bh_valid, e.mint);
                let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
                tokio::spawn(async move {
                    let l = poll_land(&rpc2, sigs, sigb, slot, Duration::from_millis(arg_u64("--land-timeout-ms", 8_000)), Watch::BuyAta(ata), bhv).await;
                    let _ = mtx2.send(Msg::Land(mint, l));
                });
            }
            open.insert(e.mint, LivePos { mint: e.mint, launch, dump_sig: sig.clone(), dump_slot: a.slot, dump_idx: x.index, t_dump_rx: a.t_rx, dump_vsol: tr.vsol, dump_vtok: tr.vtok,
                score: d.score, t_fire_ns: t_fire, buy_sig: prep.meta.sig.clone(), buy_sig_b: prep.sig, route: prep.meta.route.clone(), leader: prep.meta.leader.clone(),
                client: prep.meta.client.clone(), tips: prep.meta.tips, spend: spend_p, min_out, send_slot: a.slot, land: None, tokens: 0, sol_in: 0, buy_ok: None,
                exit: None, sell_land: None, pos: Some(pos), fired_at: Instant::now() });
        }
        time_exits(&mut open, slot_now, hold, &log, &key_arc, user, rpc, path, &mtx);
    }
    eprintln!("=== DIP DONE: dumps {n_dumps} in-envelope {n_env} picks {n_picks} fired {n_fired} closed {n_closed} landed buys {} realized {:+.6} SOL skipped {:?}",
        ACCT.landed_buys.load(Ordering::SeqCst), ACCT.realized.load(Ordering::SeqCst) as f64 / 1e9, skipped);
    // let the realized-PnL readers finish (chain reads of the last trades)
    for _ in 0..40 { if REALIZED_INFLIGHT.load(Ordering::SeqCst) == 0 { break; } tokio::time::sleep(Duration::from_millis(500)).await; }
    log.w(serde_json::json!({"ev": "run_end", "t": arbx::feeds::clock::now_ns(), "dumps": n_dumps, "in_envelope": n_env, "picks": n_picks, "fired": n_fired, "closed": n_closed,
        "landed_buys": ACCT.landed_buys.load(Ordering::SeqCst), "realized": ACCT.realized.load(Ordering::SeqCst), "skipped": skipped}));
    feed_stop.store(true, Ordering::SeqCst);    // every position is closed: the feeds may stop now
    if live { tg::raise(arbx::alerts::Level::Info, "dip_end", "end", "🏁", "DIP RUN END", arbx::alerts::format::Body::new().kv("trades", ACCT.landed_buys.load(Ordering::SeqCst).to_string()).kv("realized", sol_str(ACCT.realized.load(Ordering::SeqCst))), false); }
    Ok(())
}

/// a fire / probe waiting for its timing record (the PoH positions arrive with the shreds, a little after the landing)
struct Pend { kind: &'static str, mint: String, buy_sig: String, dump_sig_b: [u8; 64], buy_sig_b: [u8; 64], t_dump_rx: u64, t_fire: u64, due: Instant }

/// feed lag of the trigger (first sighting on any feed -> the executed feed), our reaction (first sighting -> fire), fire -> our tx
/// seen back on a feed, and the landing delay on the LEADER'S clock (PoH: our tx's position minus the dump's)
fn timing_rec(p: &Pend, first: &rustc_hash::FxHashMap<u64, (u64, u16)>, names: &[String]) -> serde_json::Value {
    let k8 = |s: &[u8; 64]| u64::from_be_bytes(s[..8].try_into().unwrap());
    let fs = |s: &[u8; 64]| first.get(&k8(s)).map(|&(t, f)| (t, names.get(f as usize).cloned().unwrap_or_else(|| f.to_string())));
    let (df, bf) = (fs(&p.dump_sig_b), fs(&p.buy_sig_b));
    let poh = |s: &[u8; 64]| arbx::feeds::poh_index().get_sig(s).and_then(|(ph, _)| ph.ms().map(|ms| (ph.slot, ms)));
    let (dp, bp) = (poh(&p.dump_sig_b), poh(&p.buy_sig_b));
    let slot_ms = arbx::feeds::entries::SLOT_US.load(Ordering::Relaxed) as f64 / 1000.0;
    let land = match (dp, bp) { (Some((ds, dm)), Some((bs, bm))) => Some((bs as f64 - ds as f64) * slot_ms + (bm - dm)), _ => None };
    serde_json::json!({"ev": "timing", "kind": p.kind, "mint": p.mint, "buy_sig": p.buy_sig,
        "dump_first_rx": df.as_ref().map(|x| x.0), "dump_first_feed": df.as_ref().map(|x| x.1.clone()), "dump_exec_rx": p.t_dump_rx,
        "exec_lag_ms": df.as_ref().map(|x| (p.t_dump_rx as i64 - x.0 as i64) as f64 / 1e6),
        "reaction_ms": df.as_ref().map(|x| (p.t_fire as i64 - x.0 as i64) as f64 / 1e6),
        "buy_first_rx": bf.as_ref().map(|x| x.0), "buy_first_feed": bf.as_ref().map(|x| x.1.clone()),
        "fire_to_seen_ms": bf.as_ref().map(|x| (x.0 as i64 - p.t_fire as i64) as f64 / 1e6),
        "dump_poh": dp, "buy_poh": bp, "land_ms_poh": land, "slot_ms": slot_ms})
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
        Msg::Land(mint, l) => {
            let Some(p) = open.get_mut(&mint) else { return };
            log.w(serde_json::json!({"ev": "land_poll", "mint": b58(&mint), "sig": l.sig, "ok": l.ok, "land_slot": l.land_slot, "via": l.via, "err": l.err}));
            if p.land.is_some() { return; }                       // the executed feed saw it first
            if l.ok && l.land_slot.is_some() {
                // landed but the executed feed missed our TradeEvent: open with the token count the poll read (or a quote)
                let ls = l.land_slot.unwrap();
                p.land = Some((ls, u64::MAX, 0)); p.buy_ok = Some(true);
                p.tokens = l.tokens.unwrap_or(p.min_out);
                if let Some(pos) = p.pos.as_mut() { pos.landed(p.spend + 5_000 + p.tips, ls); }
                log.w(serde_json::json!({"ev": "buy_land", "mint": b58(&mint), "sig": p.buy_sig, "slot": ls, "via": "rpc_poll", "tokens": p.tokens}));
            } else {
                // failed (guard / deadline) or never landed: release and close the record
                if let Some(mut pos) = p.pos.take() { if l.land_slot.is_some() { pos.reverted(5_000 + arg_u64("--cu-limit", 120_000) * arg_u64("--cu-price-micro", 3_000_000) / 1_000_000); } else { pos.not_landed(); } }
                let p = open.remove(&mint).unwrap();
                *n_closed += 1;
                log.w(serde_json::json!({"ev": "close", "mint": b58(&mint), "result": if l.land_slot.is_some() { "buy_failed" } else { "buy_not_landed" }, "buy_sig": p.buy_sig,
                    "dump_sig": p.dump_sig, "err": l.err, "route": p.route, "leader": p.leader, "client": p.client, "score": p.score}));
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
            log.w(serde_json::json!({"ev": "close", "mint": b58(&mint), "result": if sold { "sold" } else { "UNSOLD" }, "buy_sig": p.buy_sig, "dump_sig": p.dump_sig,
                "dump_slot": p.dump_slot, "dump_idx": p.dump_idx, "land": p.land, "exit_why": why, "exit_slot": xslot, "exit_value": if xval.is_nan() { serde_json::Value::Null } else { serde_json::json!(xval) },
                "sell_land": p.sell_land, "sell_sigs": out.sigs, "sol_in_curve": p.sol_in, "sol_out_curve": p.sell_land.map(|s| s.3), "curve_pnl": feed_pnl,
                "route": p.route, "leader": p.leader, "client": p.client, "tips": p.tips, "spend": p.spend, "score": p.score, "min_out": p.min_out,
                "dump_vsol": p.dump_vsol, "dump_vtok": p.dump_vtok, "held_s": p.fired_at.elapsed().as_secs_f64()}));
            eprintln!("  DIP CLOSED {} {} via {why}; curve PnL {}", b58(&mint), if sold { "sold" } else { "UNSOLD" }, feed_pnl.map(|v| format!("{:+.4} SOL", v as f64 / 1e9)).unwrap_or("?".into()));
        }
    }
}

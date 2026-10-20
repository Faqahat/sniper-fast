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
//!  * This binary NEVER touches /root/sniper (the live deploy dir) and runs no arb campaign.
//!
//! Modes:
//!   --warm-probe   create the send path, keep its warm loop alive, WAIT until hot, then fire capped 1-lamport
//!                  self-transfers and log send_slot / land_slot / delta / wall_ms. THE key measurement.
//!   --shadow       start the shred feed + pump detector (needs [[feed]] in the config), log each launch; with
//!                  --warm-probe-on-trigger, fire one capped self-transfer per launch to measure trigger->land.
//!   --live         real buy on a filtered launch (dev_buy>0) via buy_message_ixs through the warm path. GATED.
//!
//! Usage (the key run):
//!   snipe_engine --warm-probe --config probe_tpu.toml --env-file /root/sniper/deploy/.env \
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
/// latest blockhash kept fresh in the background (hash, fetched-at, lastValidBlockHeight), so a buy never waits on
/// getLatestBlockhash. L1: the last valid block height tells when a never-seen buy can no longer land.
static BLOCKHASH_CACHE: std::sync::Mutex<Option<([u8; 32], Instant, u64)>> = std::sync::Mutex::new(None);
/// C2 --sell-fallback-path: a second sell path, used (together with the sell path, one signature) on every sell RETRY.
/// A path that requires a tip gets its minimum tip in the retry tx (one transfer; paid only if the sell lands).
static SELL_FALLBACK: std::sync::OnceLock<Arc<send::Path>> = std::sync::OnceLock::new();
/// H1: the background loops the EXIT still needs (blockhash refresher, slot poller, leader book, send-path keep-alives)
/// stop on this flag, set only when run() returns. `stop` (no new fires) is set by the kill switch / lock / a signal /
/// the run's end, and the open positions keep selling with fresh blockhashes while they drain.
static INFRA_STOP: std::sync::LazyLock<Arc<AtomicBool>> = std::sync::LazyLock::new(|| Arc::new(AtomicBool::new(false)));

/// a cached blockhash younger than `max_age`, else a fresh getLatestBlockhash: (hash, lastValidBlockHeight)
async fn blockhash_fresh(rpc: &rpc::Rpc, max_age: Duration) -> Result<([u8; 32], u64)> {
    if let Some(x) = cached_blockhash(max_age) { return Ok(x); }
    // L5-1 (audit 5): refresh_blockhash stores what it accepts with its own timestamp; nothing is re-stamped here
    let r = refresh_blockhash(rpc, Duration::from_secs(1)).await;
    cached_blockhash(max_age).with_context(|| format!("no blockhash younger than {max_age:?} ({})", r.err().map(|e| redact(&format!("{e:#}"))).unwrap_or_else(|| "the RPCs returned no newer one".into())))
}

// =====================================================================================================================
// H-1 (audit 3): the exit must survive an outage of the one RPC.
//  * --rpc-fallback-url-env NAME: a second RPC (the URL is read from env var NAME, e.g. RMR_RPC_URL; never printed). Every
//    read of the exit path (blockhash, signature statuses, token reads, getBalance, getBlockHeight, getTransaction) goes
//    to the primary with a 3 s cap, then to the fallback on any error / timeout (`call2`);
//  * a sell whose fresh blockhash cannot be fetched from either RPC uses the cached one while it is <= 25 s old
//    (lastValidBlockHeight is ~150 blocks: ~33 s at 217 ms slots); the background refresher uses the fallback too.
// =====================================================================================================================
static RPC_FB: std::sync::OnceLock<rpc::Rpc> = std::sync::OnceLock::new();
/// L7-5 (audit 7): getGenesisHash with 3 attempts 1 s apart (a transient error / timeout does not refuse the start; a
/// mismatch is final at once: the caller refuses)
async fn genesis_retry(r: &rpc::Rpc) -> std::result::Result<Result<serde_json::Value>, tokio::time::error::Elapsed> {
    let mut last = None;
    for k in 0..3 {
        if k > 0 { tokio::time::sleep(Duration::from_secs(1)).await; }
        match tokio::time::timeout(Duration::from_secs(5), r.call("getGenesisHash", serde_json::json!([]))).await {
            Ok(Ok(v)) => return Ok(Ok(v)),
            x => last = Some(x),
        }
    }
    last.unwrap()
}
/// mainnet-beta's genesis hash (M5-2: both RPCs are checked against it at start-up)
const MAINNET_GENESIS: &str = "5eykt4UsFv8P8NJdTREpY1vzqKqZKvdpKuc147dw2N9d";

/// never print an RPC URL (they carry keys)
fn redact(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut rest = s;
    while let Some(i) = rest.find("http") {
        out.push_str(&rest[..i]);
        out.push_str("<url>");
        let r = &rest[i..];
        let end = r.find(|c: char| c.is_whitespace() || c == ')' || c == '"').unwrap_or(r.len());
        rest = &r[end..];
    }
    out.push_str(rest);
    out
}

/// M4-1 (audit 4) + the owner ("the sell has to take place on time, not wait 3 s"): every exit-path read RACES the primary
/// and the fallback RPC IN PARALLEL with a short cap; the first ACCEPTED answer wins (a signature status / transaction
/// that one node does not have yet is not accepted while the other may still answer). Nothing is sequential, so a slow
/// primary costs nothing when the fallback answers. Caps: 1 s for the polled reads (statuses, token account, balance,
/// block height, blockhash), 3 s for the heavy ones (getTransaction, getSignaturesForAddress, a lookup table). Without a
/// fallback RPC it is the primary alone with the same cap.
fn race_cap(method: &str) -> Duration {
    match method { "getTransaction" | "getSignaturesForAddress" | "getAccountInfo(alt)" => Duration::from_secs(3), _ => Duration::from_secs(1) }
}
fn race_accept(method: &str, v: &serde_json::Value) -> bool {
    match method {
        "getSignatureStatuses" => v["value"].get(0).is_some_and(|x| !x.is_null()),
        "getTransaction" => !v.is_null(),
        _ => true,
    }
}
/// the no-RPC trap: armed by the test of the sell decision -> send path; any engine RPC read while armed panics
static RPC_TRAP: AtomicBool = AtomicBool::new(false);

async fn call2(rpc: &rpc::Rpc, method: &str, params: serde_json::Value) -> Result<serde_json::Value> {
    let (wire, cap) = match method { "getAccountInfo(alt)" => ("getAccountInfo", race_cap(method)), m => (m, race_cap(m)) };
    call_race(rpc, wire, params, cap, |v| race_accept(method, v)).await
}

async fn call_race(rpc: &rpc::Rpc, method: &str, params: serde_json::Value, cap: Duration, accept: impl Fn(&serde_json::Value) -> bool) -> Result<serde_json::Value> {
    if RPC_TRAP.load(Ordering::SeqCst) { panic!("RPC {method} on the no-RPC path (sell decision -> send)"); }
    let p = tokio::time::timeout(cap, rpc.call(method, params.clone()));
    let Some(fb) = RPC_FB.get() else {
        return match p.await { Ok(r) => r, Err(_) => Err(anyhow::anyhow!("{method} timed out after {cap:?}")) };
    };
    let f = tokio::time::timeout(cap, fb.call(method, params));
    tokio::pin!(p);
    tokio::pin!(f);
    let (mut pd, mut fd) = (false, false);
    let mut held: Option<serde_json::Value> = None; // a valid but not-accepted answer (e.g. status null), used if nothing better
    let mut errs: Vec<String> = Vec::new();
    while !(pd && fd) {
        let (r, from_fb) = tokio::select! {
            r = &mut p, if !pd => { pd = true; (r, false) }
            r = &mut f, if !fd => { fd = true; (r, true) }
        };
        match r {
            Ok(Ok(v)) if accept(&v) => {
                if from_fb && FB_USED.fetch_add(1, Ordering::Relaxed) == 0 {
                    // Telegram (deduplicated 10 min): the fallback RPC answered first (exit path only, never a hot path)
                    tg::raise(arbx::alerts::Level::Warning, "snipe_rpc_fallback", "rpc_fallback", "🔁", "RPC fallback in use", arbx::alerts::format::Body::new().kv("method", method).txt("the fallback RPC answered before the primary"), true);
                }
                if from_fb && FB_USED.load(Ordering::Relaxed) % 500 == 0 { tg::raise(arbx::alerts::Level::Warning, "snipe_rpc_fallback", "rpc_fallback", "🔁", "RPC fallback in use", arbx::alerts::format::Body::new().kv("fallback answers so far", FB_USED.load(Ordering::Relaxed).to_string()), true); }
                return Ok(v);
            }
            Ok(Ok(v)) => { held.get_or_insert(v); }
            Ok(Err(e)) => errs.push(format!("{}: {}", if from_fb { "fallback" } else { "primary" }, redact(&format!("{e:#}")))),
            Err(_) => errs.push(format!("{}: timed out after {cap:?}", if from_fb { "fallback" } else { "primary" })),
        }
    }
    match held { Some(v) => Ok(v), None => Err(anyhow::anyhow!("{method}: {}", errs.join(" | "))) }
}
static FB_USED: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

/// getLatestBlockhash (confirmed) from one RPC: (hash, lastValidBlockHeight, context slot)
async fn latest_blockhash_one(r: &rpc::Rpc, cap: Duration) -> Result<([u8; 32], u64, u64)> {
    let v = tokio::time::timeout(cap, r.call("getLatestBlockhash", serde_json::json!([{ "commitment": "confirmed" }]))).await.map_err(|_| anyhow::anyhow!("getLatestBlockhash timed out"))??;
    let h = bs58::decode(v["value"]["blockhash"].as_str().context("no blockhash")?).into_vec()?;
    Ok((h.try_into().map_err(|_| anyhow::anyhow!("bad blockhash"))?, v["value"]["lastValidBlockHeight"].as_u64().unwrap_or(0), v["context"]["slot"].as_u64().unwrap_or(0)))
}

/// SOL text for Telegram messages
fn sol_str(l: i64) -> String { arbx::alerts::format::sol(l) }

/// one getLatestBlockhash answer: hash, lastValidBlockHeight, context slot, source (0 primary, 1 fallback)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Cand { h: [u8; 32], v: u64, ctx: u64, src: usize }

/// M7-1 (audit 7): the slot->height cross-check's state. `offset` = the learned (context slot - last valid height);
/// `recent` = each source's last offsets (for single-source learning); `excluded` = a source currently disagreeing
/// (logged on both edges, never permanent: re-admitted as soon as it agrees again)
#[derive(Default, Debug)]
struct BhState { offset: Option<i128>, recent: [std::collections::VecDeque<i128>; 2], excluded: [bool; 2], rejects: [u64; 2] }

/// M7-1: two honest nodes differ by a few blocks at most on (ctx - height) (it changes by 1 per skipped slot): 20 is the
/// agreement / offset tolerance (a drift of more than 20 is rejected at its first step)
const BH_TOL: i128 = 20;
/// (ctx - height) without overflow (L7-6f)
fn bh_off(c: &Cand) -> i128 { c.ctx as i128 - c.v as i128 }
/// a source's last `n` offsets all within 20 of each other
fn consistent(r: &std::collections::VecDeque<i128>, n: usize) -> Option<i128> {
    if r.len() < n { return None; }
    let w: Vec<i128> = r.iter().rev().take(n).copied().collect();
    let (lo, hi) = (*w.iter().min()?, *w.iter().max()?);
    (hi - lo <= 20).then_some(w[0])
}

/// M5-2 + AUDIT6 + AUDIT7: which candidate blockhash to keep (pure apart from `st`: unit-tested). `win_ref` = the slot
/// reference for the window (0 when unknown / stale: no window, M6-1); `age_ref` = the reference for FRESHNESS (when the
/// live reference is stale, the last one extrapolated at 400 ms per slot, L7-4; 0 never known); `cached` = (hash, age,
/// height); `since_accept` = time since the last accepted blockhash. Returns the choice and the log lines (edges only).
///  * plausibility (M7-1a): context slot > 0, last valid height <= context + 150 (block height <= slot on every honest
///    node: kills every bogus-high answer), the window around `win_ref` (saturating);
///  * learning (M7-1b, continuous): when BOTH sources agree within BH_TOL (20) the offset is (re-)learned from them; with no
///    offset yet, one source alone teaches it only after 5 consistent samples; with an offset, a lone agreeing source moves
///    it by at most 2 per sample (bounded drift); after 5 s with nothing accepted, a source that is consistent over 10
///    samples re-teaches it (M7-1c);
///  * a candidate more than BH_TOL from the offset is rejected — its source EXCLUDED until it agrees again (RE-ADMITTED);
///    with no offset, nothing is accepted (M7-1e: never "the lower");
///  * the best = the highest remaining height; it replaces the cache when HIGHER, or when the cache is > 10 s old and it
///    is a DIFFERENT hash that is fresh (context within 30 slots of `age_ref`) — never a re-stamp (L6-1).
fn pick_blockhash(st: &mut BhState, cands: &[Cand], win_ref: u64, age_ref: u64, cached: Option<([u8; 32], Duration, u64)>, since_accept: Duration) -> (Option<Cand>, Vec<String>) {
    let mut log = Vec::new();
    let sane = |c: &Cand| c.v > 0 && c.ctx > 0 && c.v <= c.ctx.saturating_add(150)
        && (win_ref == 0 || (c.ctx.saturating_add(150) >= win_ref && c.ctx <= win_ref.saturating_add(150)));
    let pl: Vec<Cand> = cands.iter().copied().filter(sane).collect();
    for c in &pl { let r = &mut st.recent[c.src]; r.push_back(bh_off(c)); if r.len() > 10 { r.pop_front(); } }
    // learning
    let agree = pl.len() == 2 && pl[0].src != pl[1].src && (bh_off(&pl[0]) - bh_off(&pl[1])).abs() <= BH_TOL;
    if agree {
        let o = bh_off(&pl[0]).max(bh_off(&pl[1]));
        if st.offset.is_none_or(|x| (x - o).abs() > BH_TOL) { log.push(format!("BLOCKHASH offset {} from both RPCs agreeing (was {:?})", o, st.offset)); }
        st.offset = Some(o);
    } else if st.offset.is_none() {
        if pl.len() == 2 && pl[0].src != pl[1].src {
            if st.rejects[0] == 0 && st.rejects[1] == 0 { log.push(format!("BLOCKHASH: the two RPCs DISAGREE on slot->height ({} vs {}) and no offset is learned: neither accepted", bh_off(&pl[0]), bh_off(&pl[1]))); }
            st.rejects[0] += 1; st.rejects[1] += 1;
            // L8-6 (audit 8): a persistent start-up disagreement (> 60 s with nothing accepted): learn from the PRIMARY (the
            // configured main RPC) when it is consistent over 10 samples, loudly; the other is excluded until it agrees
            if since_accept > Duration::from_secs(60) {
                if let Some(o) = consistent(&st.recent[0], 10) { st.offset = Some(o); log.push(format!("BLOCKHASH offset RE-LEARNED {o} from source 0 (the primary) after > 60 s of start-up disagreement with nothing accepted")); }
            }
        } else if let Some(c) = pl.first() {
            if let Some(o) = consistent(&st.recent[c.src], 5) { st.offset = Some(o); log.push(format!("BLOCKHASH offset {o} learned from source {} alone (5 consistent samples)", c.src)); }
        }
    } else if since_accept > Duration::from_secs(5) {
        for c in &pl {
            if let Some(o) = consistent(&st.recent[c.src], 10) {
                if st.offset.is_some_and(|x| (x - o).abs() > BH_TOL) {
                    log.push(format!("BLOCKHASH offset RE-LEARNED {o} from source {} (consistent over 10 samples; nothing accepted for {:.1} s; was {:?})", c.src, since_accept.as_secs_f64(), st.offset));
                    st.offset = Some(o);
                    break;
                }
            }
        }
    }
    // filter by the offset; exclusion / re-admission edges
    let Some(off) = st.offset else { return (None, log) };
    let mut ok = Vec::new();
    for c in &pl {
        if (bh_off(c) - off).abs() <= BH_TOL {
            if st.excluded[c.src] { st.excluded[c.src] = false; log.push(format!("BLOCKHASH source {} RE-ADMITTED (agrees with the offset again)", c.src)); }
            ok.push(*c);
        } else {
            st.rejects[c.src] += 1;
            if !st.excluded[c.src] { st.excluded[c.src] = true; log.push(format!("BLOCKHASH source {} EXCLUDED: slot->height {} vs learned {off} (re-admitted when it agrees again)", c.src, bh_off(c))); }
            else if st.rejects[c.src] % 100 == 0 { log.push(format!("BLOCKHASH source {} still excluded ({} rejects)", c.src, st.rejects[c.src])); }
        }
    }
    // bounded drift from a lone agreeing source
    if !agree && ok.len() == 1 { let d = (bh_off(&ok[0]) - off).clamp(-2, 2); st.offset = Some(off + d); }
    let Some(best) = ok.iter().max_by_key(|c| c.v).copied() else { return (None, log) };
    let pick = match cached {
        None => Some(best),
        Some((_, _, cv)) if best.v > cv => Some(best),
        Some((ch, age, _)) if age > Duration::from_secs(10) && best.h != ch && (age_ref == 0 || age_ref.saturating_sub(best.ctx) <= 30) => Some(best),
        _ => None,
    };
    (pick, log)
}
static BH_REJECTS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static BH_STATE: std::sync::LazyLock<std::sync::Mutex<BhState>> = std::sync::LazyLock::new(|| std::sync::Mutex::new(BhState::default()));
static BH_LAST_ACCEPT: std::sync::Mutex<Option<Instant>> = std::sync::Mutex::new(None);
/// M8-1: a blockhash's birth back-dating: its slot lag behind a LIVE reference (`win_ref`, 0 when stale / unknown: no
/// back-dating at all), 400 ms per slot, at most 150 slots (pure: unit-tested)
fn birth_lag(win_ref: u64, ctx: u64) -> Duration {
    if win_ref == 0 { Duration::ZERO } else { Duration::from_millis(400 * win_ref.saturating_sub(ctx).min(150)) }
}

/// M8-1 (audit 8): the slot reference's writers. A value more than SLOT_JUMP above the current one (a bogus shred slot,
/// a wrong getSlot) is HELD until a DIFFERENT source reports a value within SLOT_JUMP of it; then applied. A lone
/// source can never push the reference far ahead. Cheap (a load and a compare; the event loop calls it per tx).
pub const SLOT_SRC_FEED: u64 = 1;
pub const SLOT_SRC_PRIMARY: u64 = 2;
pub const SLOT_SRC_FALLBACK: u64 = 4;
const SLOT_JUMP: u64 = 1_000;
static JUMP_SLOT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static JUMP_SRC: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static JUMPS_HELD: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
fn slot_note(src: u64, v: u64) { slot_note_on(&send::tpu::SLOT, src, v) }
fn slot_note_on(slot: &std::sync::atomic::AtomicU64, src: u64, v: u64) {
    let cur = slot.load(Ordering::Relaxed);
    if v <= cur { return; }
    // L9-5 (audit 9): the FIRST value (cur 0) needs a second source too, like a jump
    if cur > 0 && v <= cur + SLOT_JUMP { slot.fetch_max(v, Ordering::Relaxed); return; }
    // a big jump: confirmed by another source?
    let (j, js) = (JUMP_SLOT.load(Ordering::Relaxed), JUMP_SRC.load(Ordering::Relaxed));
    if j > 0 && js & src == 0 && v.abs_diff(j) <= SLOT_JUMP {
        slot.fetch_max(v.min(j), Ordering::Relaxed);
        JUMP_SLOT.store(0, Ordering::Relaxed); JUMP_SRC.store(0, Ordering::Relaxed);
        return;
    }
    if j == 0 || v.abs_diff(j) > SLOT_JUMP { JUMP_SLOT.store(v, Ordering::Relaxed); JUMP_SRC.store(src, Ordering::Relaxed); } else { JUMP_SRC.fetch_or(src, Ordering::Relaxed); }
    JUMPS_HELD.fetch_add(1, Ordering::Relaxed);
}

/// M6-1 / L7-4: the slot reference's last value and when it last ADVANCED
static REF_SLOT: std::sync::Mutex<(u64, Option<Instant>)> = std::sync::Mutex::new((0, None));
/// (window reference, age reference): the window uses send::tpu::SLOT only while it advances (0 when stale for 3 s: no
/// window, M6-1); freshness uses the last live value extrapolated at 400 ms per slot when stale (L7-4: with no slot source
/// advancing an old hash is never taken as fresh), 0 when never known
fn ref_slots() -> (u64, u64) {
    let cur = send::tpu::SLOT.load(Ordering::Relaxed);
    let mut g = REF_SLOT.lock().unwrap();
    if cur != g.0 { *g = (cur, Some(Instant::now())); }
    match g.1 {
        Some(t) if cur > 0 && t.elapsed() <= Duration::from_secs(3) => (cur, cur),
        Some(t) if cur > 0 => (0, cur + (t.elapsed().as_millis() / 400) as u64),
        _ => (0, 0),
    }
}

/// the owner's M4-1: primary AND fallback queried IN PARALLEL (plus, M6-1, the fallback's getSlot into the slot
/// reference); the accepted answer is stored with its BIRTH time (back-dated by its slot lag behind the age reference,
/// 400 ms per slot): a cache entry's age is the blockhash's own age, never the time it was (re-)fetched. Ok(true): updated.
async fn refresh_blockhash(rpc: &rpc::Rpc, cap: Duration) -> Result<bool> {
    if RPC_TRAP.load(Ordering::SeqCst) { panic!("RPC getLatestBlockhash on the no-RPC path (sell decision -> send)"); }
    let fb = async { match RPC_FB.get() { Some(f) => Some(tokio::join!(latest_blockhash_one(f, cap), tokio::time::timeout(cap, f.slot()))), None => None } };
    let (a, b) = tokio::join!(latest_blockhash_one(rpc, cap), fb);
    let (b, fb_slot) = match b { Some((x, s)) => (Some(x), s.ok().and_then(|r| r.ok())), None => (None, None) };
    if let Some(sl) = fb_slot { slot_note(SLOT_SRC_FALLBACK, sl); }
    let cands: Vec<Cand> = [a.ok().map(|x| (x, 0usize)), b.and_then(|x| x.ok()).map(|x| (x, 1usize))].into_iter().flatten()
        .map(|((h, v, ctx), src)| Cand { h, v, ctx, src }).collect();
    if cands.is_empty() { bail!("getLatestBlockhash failed on every RPC"); }
    let (wr, ar) = ref_slots();
    let since = BH_LAST_ACCEPT.lock().unwrap().map(|t| t.elapsed()).unwrap_or(Duration::from_secs(3600));
    let (pick, log) = {
        let mut st = BH_STATE.lock().unwrap();
        let cached = BLOCKHASH_CACHE.lock().unwrap().map(|(h, t, v)| (h, t.elapsed(), v));
        pick_blockhash(&mut st, &cands, wr, ar, cached, since)
    };
    for l in log {
        if l.contains("EXCLUDED") || l.contains("RE-ADMITTED") || l.contains("DISAGREE") || l.contains("RE-LEARNED") {
            // L8-5: deduplicated (10 min) per source and edge
            let src = if l.contains("source 0") { "0" } else if l.contains("source 1") { "1" } else { "-" };
            let edge = ["EXCLUDED", "RE-ADMITTED", "DISAGREE", "RE-LEARNED"].into_iter().find(|e| l.contains(e)).unwrap_or("?");
            tg::raise(arbx::alerts::Level::Warning, "snipe_blockhash_source", &format!("bh_src:{src}:{edge}"), "🧭", &format!("Blockhash source {src}: {edge}"), arbx::alerts::format::Body::new().txt(&l), true);
        }
        eprintln!("  {l}");
    }
    match pick {
        Some(c) => {
            // M8-1 (audit 8): back-date ONLY from a LIVE (advancing) reference: an extrapolated one (possibly a bogus jump
            // that then froze) must never make an honest new blockhash look ~60 s old
            let lag = birth_lag(wr, c.ctx);
            *BLOCKHASH_CACHE.lock().unwrap() = Some((c.h, Instant::now().checked_sub(lag).unwrap_or_else(Instant::now), c.v));
            *BH_LAST_ACCEPT.lock().unwrap() = Some(Instant::now());
            Ok(true)
        }
        None => {
            if cands.iter().all(|c| wr > 0 && !(c.ctx.saturating_add(150) >= wr && c.ctx <= wr.saturating_add(150))) {
                let n = BH_REJECTS.fetch_add(1, Ordering::Relaxed) + 1;
                if n == 1 || n % 100 == 0 { eprintln!("  BLOCKHASH candidate(s) REJECTED (#{n}): context slot(s) {:?} vs reference slot {wr} (> 150 apart)", cands.iter().map(|c| c.ctx).collect::<Vec<_>>()); }
                bail!("every blockhash candidate was outside the reference slot window");
            }
            Ok(false)
        }
    }
}

/// L6-3 (audit 6) / L7-3: no usable blockhash (the newest older than 7 s, birth-dated) PAUSES new fires (not the permanent stop); fires resume after 10 s of
/// usable blockhashes. Both edges are logged.
static FIRE_PAUSE: AtomicBool = AtomicBool::new(false);

/// the owner's M4-1: the SELL path only READS the cache (kept fresh by the background refresher every ~400 ms). None:
/// older than `max_age` (pure: no RPC; used on the decision -> send path)
fn cached_blockhash(max_age: Duration) -> Option<([u8; 32], u64)> {
    BLOCKHASH_CACHE.lock().unwrap().filter(|(_, t, _)| t.elapsed() <= max_age).map(|(h, _, v)| (h, v))
}

/// a sell's blockhash: the cache when <= 20 s old (no RPC); only when it is older, an inline refresh racing BOTH RPCs in
/// parallel with a 300 ms cap; then the cache up to 25 s old. Err only when nothing usable exists.
async fn sell_blockhash(_rpc: &rpc::Rpc) -> Result<([u8; 32], u64)> {
    if let Some(x) = cached_blockhash(Duration::from_secs(20)) { return Ok(x); }
    let r = refresh_blockhash(_rpc, Duration::from_millis(300)).await;
    if let Some(x) = cached_blockhash(Duration::from_secs(25)) {
        if r.is_err() { eprintln!("  SELL-BLOCKHASH: the cache is > 20 s old and the 300 ms parallel refresh failed — using the cached one"); }
        return Ok(x);
    }
    bail!("no usable blockhash: the cache is > 25 s old and the parallel refresh failed ({})", r.err().map(|e| redact(&format!("{e:#}"))).unwrap_or_default())
}

/// the run's stop flag (no new fires), for the exit path (M-2 stops the run after repeated non-slippage buy failures)
static RUN_STOP: std::sync::OnceLock<Arc<AtomicBool>> = std::sync::OnceLock::new();

// =====================================================================================================================
// M-3 (audit 3; send-path change APPROVED by the owner): an ON-CHAIN slot deadline on every buy. A Lighthouse
// (L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95, the open-source assertion program wallets add to transactions)
// AssertSysvarClock instruction, placed right before the pump buy: "Clock.slot <= create_slot + N" (--buy-max-slot-delta
// N). A buy landing later fails on chain (no tokens; the base + priority fee is paid, tip transfers revert with it; a
// Jito bundle that fails is not landed at all). Data: [ix disc, log_level 0 (silent), assertion 0 (Slot), slot u64 LE,
// integer operator]: 12 bytes, no accounts; adds the program key (32 B) + ~15 B to the tx.
// FAIL CLOSED: the encoding is VERIFIED ON CHAIN at start-up by simulation (zero cost: sigVerify off, nothing sent): a
// deadline 50 slots ahead must PASS and one 50 slots behind must FAIL, both at the guard instruction; the first candidate
// encoding that behaves so is used. If none does (program missing, encoding unknown), the engine refuses to start.
// =====================================================================================================================
static LIGHTHOUSE: std::sync::LazyLock<Pk> = std::sync::LazyLock::new(|| pk("L2TExMFKdjpN9kozasaurPirfHy9P8sbXoAN1qA3S95"));

/// a verified guard encoding (ix discriminator, integer operator, whether the program is passed as account 0)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct GuardEnc { disc: u8, op: u8, acct: bool }
static SLOT_GUARD: std::sync::OnceLock<(GuardEnc, u64)> = std::sync::OnceLock::new(); // (encoding, N = --buy-max-slot-delta)

fn guard_ix_enc(g: GuardEnc, deadline: u64) -> build::Ix {
    let mut d = vec![g.disc, 0, 0];
    d.extend(deadline.to_le_bytes());
    d.push(g.op);
    build::Ix { program: *LIGHTHOUSE, accounts: if g.acct { vec![build::Meta { key: *LIGHTHOUSE, signer: false, writable: false }] } else { vec![] }, data: d }
}

/// M-3: insert the slot guard (deadline slot) right before the pump buy instruction (no-op when the guard is off)
fn with_guard(ixs: Vec<build::Ix>, deadline: Option<u64>) -> Vec<build::Ix> {
    match (SLOT_GUARD.get(), deadline) { (Some((g, _)), Some(dl)) => insert_guard(ixs, *g, dl), _ => ixs }
}
fn insert_guard(mut ixs: Vec<build::Ix>, g: GuardEnc, deadline: u64) -> Vec<build::Ix> {
    let at = ixs.iter().position(|ix| ix.program == *snipe::PUMP).unwrap_or(ixs.len());
    ixs.insert(at, guard_ix_enc(g, deadline));
    ixs
}
/// the buy's deadline slot for a create in `create_slot` (None: guard off or the create slot unknown)
fn buy_deadline(create_slot: Option<u64>) -> Option<u64> { SLOT_GUARD.get().and_then(|(_, n)| create_slot.map(|s| s + n)) }

/// M-2/M-3: the index of the slot guard and of the pump buy instruction in a signed tx (to classify a failure)
fn ix_roles(raw: &[u8]) -> (Option<u8>, Option<u8>) {
    let Some((tx, _)) = arbx::tx::parse_wire(raw) else { return (None, None) };
    let at = |p: &Pk| tx.ixs.iter().position(|ix| tx.keys.get(ix.program as usize) == Some(p)).map(|i| i as u8);
    (at(&LIGHTHOUSE), at(&snipe::PUMP))
}

/// M-3 start-up check (fail closed): find the encoding that passes a deadline 50 slots ahead and fails one 50 behind
async fn verify_slot_guard(rpc: &rpc::Rpc, key: &SigningKey, user: Pk) -> Result<(GuardEnc, u64)> {
    let ai = rpc.call("getAccountInfo", serde_json::json!([b58(&LIGHTHOUSE), { "encoding": "base64", "dataSlice": { "offset": 0, "length": 0 } }])).await.context("getAccountInfo(lighthouse)")?;
    if ai["value"].is_null() || ai["value"]["executable"].as_bool() != Some(true) { bail!("the Lighthouse program {} is not an executable account on this cluster", b58(&LIGHTHOUSE)); }
    let sim = |ix: build::Ix| async move {
        let bh = rpc.latest_blockhash().await.map(|x| x.0).unwrap_or([0u8; 32]);
        let msg = build::compile_v0(user, &[build::cu_limit_ix(20_000), ix], bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
        let raw = build::sign(&msg, key);
        let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
        let v = rpc.call("simulateTransaction", serde_json::json!([b64, { "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed" }])).await?;
        anyhow::Ok((v["value"]["err"].clone(), v["value"]["unitsConsumed"].as_u64().unwrap_or(0), v["context"]["slot"].as_u64().unwrap_or(0)))
    };
    let s = rpc.slot().await.context("getSlot")?;
    let mut tried = Vec::new();
    for disc in [14u8, 15] { for op in [5u8, 4] { for acct in [false, true] {
        let g = GuardEnc { disc, op, acct };
        let (e_ok, cu, ctx) = sim(guard_ix_enc(g, s + 50)).await?;
        let (e_bad, _, _) = sim(guard_ix_enc(g, s.saturating_sub(50))).await?;
        // the late case must fail AT the guard (instruction 1, after the CU-limit ix)
        let at_guard = e_bad.get("InstructionError").and_then(|x| x.get(0)).and_then(|x| x.as_u64()) == Some(1);
        tried.push(format!("disc {disc} op {op} acct {acct}: ahead={} behind={}", if e_ok.is_null() { "pass".into() } else { e_ok.to_string() }, if e_bad.is_null() { "pass".into() } else { e_bad.to_string() }));
        if e_ok.is_null() && !e_bad.is_null() && at_guard {
            let n = arg_u64("--buy-max-slot-delta", 1);
            eprintln!("SLOT-GUARD verified on chain (simulated at slot {ctx}): Lighthouse AssertSysvarClock disc {disc} op {op} acct {acct}; {cu} CU incl. the CU-limit ix; deadline = create slot + {n}");
            return Ok((g, n));
        }
    } } }
    bail!("--buy-max-slot-delta: no Lighthouse AssertSysvarClock encoding behaved as a slot deadline in simulation — refusing to start (fail closed). Tried: {}", tried.join("; "))
}

/// M3: RPC errors seen by the land / sell polls, logged at most once per 5 s (with the count since the last line)
static POLL_ERRS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static POLL_ERR_LAST: std::sync::Mutex<Option<Instant>> = std::sync::Mutex::new(None);
fn poll_err(what: &str, e: &anyhow::Error) {
    let n = POLL_ERRS.fetch_add(1, Ordering::Relaxed) + 1;
    let mut g = POLL_ERR_LAST.lock().unwrap();
    if g.is_none_or(|t| t.elapsed() >= Duration::from_secs(5)) {
        *g = Some(Instant::now());
        eprintln!("  POLL-RPC-ERROR {what}: {} (poll errors so far: {n})", redact(&format!("{e:#}")).chars().take(200).collect::<String>());
    }
}

/// L8 (audit) + N5 (re-audit): every flag must be known and every numeric flag must parse. An unparsable value (or a flag
/// given without a value) used to fall back to its default silently (--max-loss-sol garbage -> the 30 SOL total cap;
/// --max-inflight garbage -> 6 in flight), and a misspelled flag (--max-buy) was ignored. Checked first in main: refuse
/// to start. The lists come from this file's own source, so a new flag is covered without maintaining a table:
///  * known flags = every "--flag" string literal in snipe_engine.rs;
///  * integer flags = every flag read with arg_u64 / arg_u64_opt; number flags = every flag read with arg_f64, plus the
///    ones parsed from arg() directly (--fill-cap, --max-create-ms, --race-min/max-bundle-sol).
const ENGINE_SRC: &str = include_str!("snipe_engine.rs");

/// flag names after each occurrence of `prefix` (e.g. `arg_u64("`) in the source
fn src_flags(prefix: &str) -> std::collections::BTreeSet<String> {
    // the engine's code only: the unit tests below name deliberately WRONG flags
    let src = ENGINE_SRC.split("#[cfg(test)]\nmod audit_tests").next().unwrap_or(ENGINE_SRC);
    let mut out = std::collections::BTreeSet::new();
    for (i, _) in src.match_indices(prefix) {
        let rest = &src[i + prefix.len()..];
        if !rest.starts_with("--") { continue; }
        let n = rest[2..].bytes().take_while(|b| b.is_ascii_lowercase() || b.is_ascii_digit() || *b == b'-').count();
        if n > 0 { out.insert(rest[..2 + n].to_string()); }
    }
    out
}

fn check_flags(argv: &[String]) -> Result<()> {
    let known = src_flags("\"");
    let u64s: std::collections::BTreeSet<String> = src_flags("arg_u64(\"").into_iter().chain(src_flags("arg_u64_opt(\"")).collect();
    let mut f64s = src_flags("arg_f64(\"");
    for f in ["--fill-cap", "--max-create-ms", "--race-min-bundle-sol", "--race-max-bundle-sol", "--min-balance-margin-sol"] { f64s.insert(f.to_string()); }
    let val = |f: &str| argv.iter().position(|x| x == f).and_then(|i| argv.get(i + 1)).cloned();
    for a in argv.iter().skip(1) {
        if a.starts_with("--") && !known.contains(a.as_str()) { bail!("unknown flag {a} (misspelled?): refusing to start"); }
    }
    for f in argv.iter().skip(1).filter(|a| a.starts_with("--")) {
        if u64s.contains(f.as_str()) {
            match val(f) { Some(v) if v.parse::<u64>().is_ok() => {}, v => bail!("{f}: '{}' is not a non-negative integer: refusing to start", v.unwrap_or_default()) }
        } else if f64s.contains(f.as_str()) {
            match val(f).map(|v| (v.parse::<f64>(), v)) { Some((Ok(x), _)) if x.is_finite() && x >= 0.0 => {}, Some((_, v)) => bail!("{f}: '{v}' is not a number >= 0: refusing to start"), None => bail!("{f} needs a value: refusing to start") }
        }
    }
    let has_a = |f: &str| argv.iter().any(|x| x == f);
    if has_a("--slip-cap-bps") && val("--slip-cap-bps").and_then(|v| v.parse::<u64>().ok()).unwrap_or(0) >= 10_000 { bail!("--slip-cap-bps must be < 10000"); }
    if has_a("--max-inflight") && val("--max-inflight").and_then(|v| v.parse::<u64>().ok()) == Some(0) { bail!("--max-inflight must be >= 1"); }
    if has_a("--env-name") && !matches!(val("--env-name").map(|v| v.to_ascii_uppercase()).as_deref(), Some("DEV" | "PROD")) { bail!("--env-name must be DEV or PROD: refusing to start"); }
    if has_a("--race-bundle") && !matches!(val("--race-bundle").as_deref(), Some("yes" | "no")) { bail!("--race-bundle must be yes or no: refusing to start"); }
    if has_a("--max-create-ms-unknown") && !matches!(val("--max-create-ms-unknown").as_deref(), Some("pass" | "skip")) { bail!("--max-create-ms-unknown must be pass or skip: refusing to start"); }
    if has_a("--lock-tiers") {
        let t = val("--lock-tiers").filter(|v| !v.starts_with("--")).context("--lock-tiers needs a value: refusing to start")?;
        for kv in t.split(',') {
            let ok = kv.split_once(':').is_some_and(|(a, f)| a.trim().parse::<f64>().is_ok_and(|x| x.is_finite()) && f.trim().parse::<f64>().is_ok_and(|x| x.is_finite()));
            if !ok { bail!("--lock-tiers: '{kv}' is not ARM:FLOOR (SOL): refusing to start"); }
        }
    }
    Ok(())
}
fn check_safety_flags() -> Result<()> { check_flags(&std::env::args().collect::<Vec<_>>()) }

/// L11: Alpenglow (2026-10-21 14:50 UTC) changes slot timing: the --max-create-ms gate was measured before it
fn alpenglow_warning() {
    const ALPENGLOW_UNIX: u64 = 1_792_594_200; // 2026-10-21T14:50:00Z
    let now = std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    if now >= ALPENGLOW_UNIX {
        eprintln!("WARNING: date >= 2026-10-21 14:50 UTC (Alpenglow): re-validate create-ms gate (--max-create-ms was measured on pre-Alpenglow slot timing)");
    }
}

// =====================================================================================================================
// ALT RESOLUTION (2026-10-20, server dry run of 39810395): raw shred / entries feeds do not resolve address lookup tables,
// so a create that reaches the curve / quote mint / buy accounts through a table read as "unresolved" (M6: skip_quote)
// although it is SOL-quoted (launchpad table HQ4G6Fjm…: a true rule-#2 launch every 3-5 min was skipped; M5 had the same
// blind spot for bundle legs). This cache resolves them:
//  * table pubkey -> its addresses (Arc), behind a std RwLock: the event loop only takes the READ lock (writers are the
//    rare fetch completions) — no RPC, no contended lock on the detection / decision path;
//  * `fill(&mut tx)`: every feed tx with lookups and no feed-resolved addresses gets `tx.loaded` from the cache, before
//    detection. A table not cached, or an index past its cached length (the table was extended), leaves the tx
//    unresolved — the fail-closed behaviour stays (skip / unknown leg) — and starts ONE async fetch (getAccountInfo
//    through call2: primary, then the fallback RPC), so the next launch through that table resolves. `ALT-MISS <table>`
//    is logged once per table, `ALT-REFRESH <table>` when an index is out of range;
//  * preloaded at start-up: the known launchpad table(s), every table in --alt-cache-file (the last 200 tables seen, kept
//    across runs: appended when a table is first fetched) and --alt-preload a,b,...
// =====================================================================================================================
mod altc {
    use super::*;
    use std::collections::{HashMap, HashSet, VecDeque};
    use std::sync::atomic::{AtomicBool, AtomicU64};
    use std::sync::{Mutex, OnceLock, RwLock};

    /// launchpad tables known to carry SOL-quoted rule-#2 creates (full keys)
    pub const KNOWN: [&str; 1] = ["HQ4G6FjmW8yZ15XGoiQdGDvbi5C7fJKktNg6pzCzdHg4"];
    /// M5-1 (audit 5): bounds. At most RATE_PER_S fetches started per second, INFLIGHT at once, QUEUE_CAP waiting (the
    /// oldest dropped), LRU_CAP tables cached (the least recently used 10% evicted past it)
    pub const LRU_CAP: usize = 5_000;
    const RATE_PER_S: u64 = 5;
    const INFLIGHT: usize = 4;
    const QUEUE_CAP: usize = 256;

    struct Ent { addrs: Arc<Vec<Pk>>, last: AtomicU64 }
    static TABLES: std::sync::LazyLock<RwLock<HashMap<Pk, Ent>>> = std::sync::LazyLock::new(|| RwLock::new(HashMap::new()));
    /// the fetch queue (touched only on a relevant miss and by the dispatcher: never on a hit)
    #[derive(Default)]
    struct Q { queue: VecDeque<(Pk, bool, bool)>, hi: VecDeque<(Pk, bool, bool)>, queued: HashSet<Pk>, backoff: HashMap<Pk, (u32, Instant)>, missed: HashSet<Pk> }
    static QU: std::sync::LazyLock<Mutex<Q>> = std::sync::LazyLock::new(|| Mutex::new(Q::default()));
    static WATCHING: AtomicBool = AtomicBool::new(false);
    static CLOCK: AtomicU64 = AtomicU64::new(1);
    static RPC: OnceLock<Arc<rpc::Rpc>> = OnceLock::new();
    static FILE: OnceLock<String> = OnceLock::new();
    pub static HITS: AtomicU64 = AtomicU64::new(0);
    pub static MISSES: AtomicU64 = AtomicU64::new(0);
    /// misses not fetched: not a create and no watched launch (M5-1)
    pub static IGNORED: AtomicU64 = AtomicU64::new(0);
    pub static FETCHED: AtomicU64 = AtomicU64::new(0);
    pub static FAILED: AtomicU64 = AtomicU64::new(0);
    pub static EVICTED: AtomicU64 = AtomicU64::new(0);

    /// the outcome of resolving one tx's lookups (pure: unit-tested)
    #[derive(Debug, PartialEq, Eq)]
    pub enum Res { Done((Vec<Pk>, Vec<Pk>)), Missing(Vec<Pk>), Stale(Vec<Pk>) }

    pub fn resolve_with(tx: &arbx::tx::Tx, get: impl Fn(&Pk) -> Option<Arc<Vec<Pk>>>) -> Res {
        let (mut missing, mut stale) = (Vec::new(), Vec::new());
        let mut got: Vec<Option<Arc<Vec<Pk>>>> = Vec::with_capacity(tx.lookups.len());
        for l in &tx.lookups {
            let t = get(&l.table);
            match &t {
                None => { if !missing.contains(&l.table) { missing.push(l.table); } }
                Some(t) => if l.writable.iter().chain(&l.readonly).any(|&i| i as usize >= t.len()) && !stale.contains(&l.table) { stale.push(l.table); },
            }
            got.push(t);
        }
        if !missing.is_empty() { return Res::Missing(missing); }
        if !stale.is_empty() { return Res::Stale(stale); }
        let (mut w, mut r) = (Vec::new(), Vec::new());
        for (l, t) in tx.lookups.iter().zip(&got) { let t = t.as_ref().unwrap(); w.extend(l.writable.iter().map(|&i| t[i as usize])); }
        for (l, t) in tx.lookups.iter().zip(&got) { let t = t.as_ref().unwrap(); r.extend(l.readonly.iter().map(|&i| t[i as usize])); }
        Res::Done((w, r))
    }

    /// M5-1: a launch is being watched (race pending): unresolved pump buys are then worth fetching (bundle legs)
    pub fn set_watching(b: bool) { WATCHING.store(b, Ordering::Relaxed); }

    /// fill `tx.loaded` from the cache (read lock only; no allocation beyond the result, no logging). false: a table is
    /// missing / stale; it is QUEUED for a fetch only when the tx matters (M5-1: a pump create, or an unresolved pump buy
    /// while a launch is watched) — never for every tx on the feed
    pub fn fill(tx: &mut arbx::tx::Tx) -> bool {
        if tx.lookups.is_empty() || tx.loaded.is_some() { return true; }
        let now = CLOCK.fetch_add(1, Ordering::Relaxed);
        let res = { let g = TABLES.read().unwrap(); resolve_with(tx, |k| g.get(k).map(|e| { e.last.store(now, Ordering::Relaxed); e.addrs.clone() })) };
        let (tabs, stale) = match res {
            Res::Done(l) => { tx.loaded = Some(l); HITS.fetch_add(1, Ordering::Relaxed); return true; }
            Res::Missing(v) => (v, false),
            Res::Stale(v) => (v, true),
        };
        MISSES.fetch_add(1, Ordering::Relaxed);
        let create = snipe::is_create_candidate(tx);
        if create || (WATCHING.load(Ordering::Relaxed) && snipe::pump_buy_mint_unresolved(tx)) { for t in tabs { request(t, create, stale); } }
        else { IGNORED.fetch_add(1, Ordering::Relaxed); }
        false
    }

    /// test / preload: put a table in the cache
    pub fn insert(table: Pk, addrs: Vec<Pk>) {
        let mut g = TABLES.write().unwrap();
        if g.len() >= LRU_CAP && !g.contains_key(&table) {
            // M5-1: evict the least recently used 10%
            let v: Vec<(u64, Pk)> = g.iter().map(|(k, e)| (e.last.load(Ordering::Relaxed), *k)).collect();
            for k in lru_victims(v, (LRU_CAP / 10).max(1)) { g.remove(&k); EVICTED.fetch_add(1, Ordering::Relaxed); }
        }
        g.insert(table, Ent { addrs: Arc::new(addrs), last: AtomicU64::new(CLOCK.fetch_add(1, Ordering::Relaxed)) });
    }
    pub fn len() -> usize { TABLES.read().unwrap().len() }
    /// the `n` least recently used of (last use, table) (pure: unit-tested)
    pub fn lru_victims(mut v: Vec<(u64, Pk)>, n: usize) -> Vec<Pk> { v.sort_unstable(); v.into_iter().take(n).map(|x| x.1).collect() }
    /// is `table` waiting for a fetch (tests)
    pub fn is_queued(table: &Pk) -> bool { QU.lock().unwrap().queued.contains(table) }

    /// queue one fetch (deduplicated, per-table back-off after a failure, bounded queue). No logging here: the event loop
    /// calls it
    fn request(table: Pk, create: bool, stale: bool) {
        let mut q = QU.lock().unwrap();
        if q.queued.contains(&table) {
            // L7-6e: a table first queued from a leg and now needed by a create moves to the create queue
            if create { if let Some(i) = q.queue.iter().position(|x| x.0 == table) { q.queue.remove(i); q.hi.push_back((table, true, stale)); } }
            return;
        }
        if q.backoff.get(&table).is_some_and(|(_, until)| Instant::now() < *until) { return; }
        // L6-5c (audit 6): creates in their own queue, served first; a full queue drops the oldest LEG table first
        if q.queue.len() + q.hi.len() >= QUEUE_CAP {
            let old = q.queue.pop_front().or_else(|| if create { q.hi.pop_front() } else { None });
            match old { Some((o, ..)) => { q.queued.remove(&o); } None => return }
        }
        q.queued.insert(table);
        if create { q.hi.push_back((table, create, stale)); } else { q.queue.push_back((table, create, stale)); }
    }

    /// the one dispatcher: <= RATE_PER_S fetch starts per second, <= INFLIGHT at once; logs from the fetch tasks only
    fn start_dispatcher(rpc: Arc<rpc::Rpc>) {
        let sem = Arc::new(tokio::sync::Semaphore::new(INFLIGHT));
        tokio::spawn(async move {
            loop {
                tokio::time::sleep(Duration::from_millis(1000 / RATE_PER_S)).await;
                let Ok(permit) = sem.clone().acquire_owned().await else { break };
                let job = { let mut q = QU.lock().unwrap(); q.hi.pop_front().or_else(|| q.queue.pop_front()) };
                let Some((table, create, stale)) = job else { drop(permit); continue };
                let rpc = rpc.clone();
                tokio::spawn(async move {
                    let _p = permit;
                    let r = fetch(&rpc, table).await;
                    let mut q = QU.lock().unwrap();
                    q.queued.remove(&table);
                    match r {
                        Ok(n) => {
                            q.backoff.remove(&table);
                            let first_miss = create && q.missed.insert(table);
                            if q.missed.len() > 20_000 { q.missed.clear(); }
                            drop(q);
                            if first_miss { eprintln!("  ALT-MISS {} (a pump create): was not cached — that create stayed unresolved (fail closed); now loaded ({n} addresses)", b58(&table)); }
                            if stale { eprintln!("  ALT-REFRESH {}: the table was extended — re-fetched ({n} addresses)", b58(&table)); }
                            if create { remember(table); }
                        }
                        Err(e) => {
                            let k = q.backoff.get(&table).map(|x| x.0).unwrap_or(0) + 1;
                            let wait = Duration::from_secs((5u64 << (k - 1).min(5)).min(120));
                            q.backoff.insert(table, (k, Instant::now() + wait));
                            if q.backoff.len() > 10_000 { let now = Instant::now(); q.backoff.retain(|_, (_, u)| *u > now); }
                            drop(q);
                            let f = FAILED.fetch_add(1, Ordering::Relaxed) + 1;
                            if f == 1 || f % 50 == 0 { eprintln!("  ALT-FETCH-FAIL {} (#{f} so far): {} — retry after {} s", b58(&table), redact(&format!("{e:#}")).chars().take(120).collect::<String>(), wait.as_secs()); }
                        }
                    }
                });
            }
        });
    }

    /// getAccountInfo of one lookup table: ONE RPC per fetch (M5-1): the primary (2 s), the fallback only on its error
    pub async fn fetch(rpc: &rpc::Rpc, table: Pk) -> Result<usize> {
        let params = serde_json::json!([b58(&table), { "encoding": "base64", "commitment": "confirmed" }]);
        let one = |r: &rpc::Rpc| { let p = params.clone(); let r = r.clone(); async move { tokio::time::timeout(Duration::from_secs(2), r.call("getAccountInfo", p)).await.map_err(|_| anyhow::anyhow!("timed out"))? } };
        let v = match one(rpc).await {
            Ok(v) => v,
            Err(e) => match RPC_FB.get() { Some(fb) => one(fb).await.map_err(|e2| anyhow::anyhow!("primary: {} | fallback: {}", redact(&format!("{e:#}")), redact(&format!("{e2:#}"))))?, None => return Err(e) },
        };
        if v["value"].is_null() { bail!("lookup table {} does not exist", b58(&table)); }
        if v["value"]["owner"].as_str() != Some("AddressLookupTab1e1111111111111111111111111") { bail!("{} is not a lookup table", b58(&table)); }
        let data = base64::engine::general_purpose::STANDARD.decode(v["value"]["data"][0].as_str().unwrap_or("")).context("lookup table data")?;
        let addrs = arbx::tx::parse_alt(&data).context("lookup table layout")?;
        let n = addrs.len();
        insert(table, addrs);
        let k = FETCHED.fetch_add(1, Ordering::Relaxed) + 1;
        if k % 1000 == 0 { eprintln!("  ALT CACHE: {k} fetches so far, {} cached (cap {LRU_CAP}), {} evicted, {} failed, {} misses ignored (not relevant)", len(), EVICTED.load(Ordering::Relaxed), FAILED.load(Ordering::Relaxed), IGNORED.load(Ordering::Relaxed)); }
        Ok(n)
    }

    /// --alt-cache-file: keep the last 200 tables seen in pump creates (one base58 key per line)
    fn remember(table: Pk) {
        let Some(path) = FILE.get() else { return };
        let mut v: Vec<String> = std::fs::read_to_string(path).unwrap_or_default().lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect();
        let k = b58(&table);
        if v.last() == Some(&k) { return; }
        v.retain(|x| *x != k);
        v.push(k);
        if v.len() > 200 { v.drain(..v.len() - 200); }
        let _ = std::fs::write(path, v.join("\n") + "\n");
    }

    /// start-up: the dispatcher, then preload KNOWN + the cache file + --alt-preload (8 at a time, 15 s bound)
    pub async fn init(rpc: Arc<rpc::Rpc>) {
        let _ = RPC.set(rpc.clone());
        start_dispatcher(rpc.clone());
        let mut list: Vec<String> = KNOWN.iter().map(|s| s.to_string()).collect();
        if let Some(p) = arg("--alt-cache-file") {
            list.extend(std::fs::read_to_string(&p).unwrap_or_default().lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()));
            let _ = FILE.set(p);
        }
        if let Some(x) = arg("--alt-preload") { list.extend(x.split(',').map(|s| s.trim().to_string()).filter(|s| !s.is_empty())); }
        let mut seen = HashSet::new();
        let tabs: Vec<Pk> = list.iter().filter_map(|s| bs58::decode(s).into_vec().ok().filter(|v| v.len() == 32).map(|v| { let mut k = [0u8; 32]; k.copy_from_slice(&v); k })).filter(|k| seen.insert(*k)).collect();
        let t0 = Instant::now();
        let sem = Arc::new(tokio::sync::Semaphore::new(8));
        let mut js = tokio::task::JoinSet::new();
        for t in &tabs { let (rpc, t, sem) = (rpc.clone(), *t, sem.clone()); js.spawn(async move { let _p = sem.acquire_owned().await; (t, fetch(&rpc, t).await) }); }
        let res = tokio::time::timeout(Duration::from_secs(15), async { let mut v = Vec::new(); while let Some(Ok(x)) = js.join_next().await { v.push(x); } v }).await;
        match res {
            Ok(v) => {
                let ok = v.iter().filter(|x| x.1.is_ok()).count();
                for (t, r) in v.iter().filter(|x| x.1.is_err()).take(5) { if let Err(e) = r { eprintln!("  ALT-PRELOAD {} failed: {}", b58(t), redact(&format!("{e:#}"))); } }
                eprintln!("ALT CACHE: preloaded {ok} of {} lookup table(s) in {:.1} s (known launchpad tables + {}); fetch limits {RATE_PER_S}/s, {INFLIGHT} in flight, LRU cap {LRU_CAP}",
                    tabs.len(), t0.elapsed().as_secs_f64(), FILE.get().map(|s| s.as_str()).unwrap_or("no --alt-cache-file"));
            }
            Err(_) => eprintln!("ALT CACHE: preload of {} table(s) timed out after 15 s ({} cached; the rest load on first relevant sight)", tabs.len(), len()),
        }
    }
}

// =====================================================================================================================
// TELEGRAM (owner, 2026-10-20: "update everything to telegram, check the old arb about the telegram"). The old arb bot's
// alert system is REUSED as is (arbx::alerts, PLAN-ADDENDUM WP-20): the bounded queue (try_send: a full queue drops and
// counts, never waits), the one sender task (HTML sendMessage, <= 20/min, 429 retry_after, coalescing, dedup), token
// redaction everywhere, the panic hook (a crash posts a Critical alert), the exit flush. Credentials from the env
// (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID in /root/sniper/deploy/.env); never printed. Every message header carries the
// --env-name label (DEV / PROD).
// NEVER ON A HOT PATH: nothing between a buy's decision and its first write, or a sell's decision and its write, calls it:
// the fire message is raised from the spawned task after the writes, everything else is on the exit / control paths.
// A raise is a level check, a try-lock dedup check and a try_send (O(1), never waits). TG_TRAP (tests) panics on any raise
// while armed. --no-telegram (or missing env vars) turns it off: every call is then a no-op.
// =====================================================================================================================
mod tg {
    use super::*;
    use arbx::alerts::format::{esc, sol, sol_signed, Body};
    use arbx::alerts::{Alert, Alerts, AlertsCfg, Level};
    use std::sync::OnceLock;

    static TG: OnceLock<Arc<Alerts>> = OnceLock::new();
    static ENV: OnceLock<String> = OnceLock::new();
    /// the sender's stop (set at the very end, after the last message is queued)
    pub static STOP: std::sync::LazyLock<Arc<AtomicBool>> = std::sync::LazyLock::new(|| Arc::new(AtomicBool::new(false)));
    /// tests: any raise while armed panics (proves a path never touches Telegram)
    pub static TG_TRAP: AtomicBool = AtomicBool::new(false);

    pub fn env_name() -> &'static str { ENV.get().map(|s| s.as_str()).unwrap_or("DEV") }
    static BUILD: OnceLock<String> = OnceLock::new();
    /// the running binary's sha256 (12 hex), computed once at start-up before the feeds (INFO, audit 8)
    pub fn build_id() -> String {
        BUILD.get_or_init(|| std::fs::read("/proc/self/exe").map(|b| { use sha2::Digest; let h = sha2::Sha256::digest(&b); h.iter().take(6).map(|x| format!("{x:02x}")).collect::<String>() }).unwrap_or_else(|_| "?".into())).clone()
    }
    pub fn on() -> bool { TG.get().is_some_and(|a| a.enabled()) }

    /// the engine's [alerts] (no heartbeat / daily summary of the arb bot's: the engine sends its own)
    pub fn cfg() -> AlertsCfg { AlertsCfg { enabled: true, heartbeat_min: 0, daily_summary: false, ..AlertsCfg::default() } }

    /// start-up (inside the runtime): label, credentials, sender, panic hook. Off with --no-telegram or missing env vars
    pub fn init(rt: &tokio::runtime::Handle) {
        let _ = ENV.set(arg("--env-name").unwrap_or_else(|| "DEV".into()).to_ascii_uppercase());
        let _ = build_id(); // hashed now, before any feed runs
        // --telegram (the default: on) / --no-telegram (off; wins over --telegram)
        let _explicit_on = has("--telegram");
        if has("--no-telegram") { eprintln!("TELEGRAM: off (--no-telegram)"); return; }
        let ctx = arbx::alerts::Ctx { label: format!("SNIPER {}", env_name()), started_ns: arbx::feeds::clock::real_ns(), ..Default::default() };
        let (a, notes) = Alerts::new(&cfg(), &|k| std::env::var(k).ok(), ctx);
        for n in notes { eprintln!("TELEGRAM: {n}"); }
        if !a.enabled() { return; }
        arbx::alerts::install(a.clone());
        arbx::alerts::install_panic_hook();
        a.start(rt, STOP.clone());
        let _ = TG.set(a);
    }

    /// queue one message (O(1), never waits). `dedup`: repeats of `key` inside 10 min are counted, not sent
    pub fn raise(level: Level, kind: &'static str, key: &str, icon: &'static str, title: &str, body: Body, dedup: bool) {
        if TG_TRAP.load(Ordering::SeqCst) { panic!("Telegram raise ({kind}) on a no-Telegram path"); }
        let Some(a) = TG.get() else { return };
        let mut al = Alert::new(level, kind, key.to_string(), title).icon(icon).body(body);
        if !dedup { al = al.once(); }
        a.raise(al);
    }

    /// the end of the run: everything queued goes out (blocks the caller up to `wait`: main thread only, after the run)
    pub fn flush(wait: Duration) { if let Some(a) = TG.get() { STOP.store(true, Ordering::SeqCst); let _ = a.flush(wait); } }

    /// the delivery counters (the run's last log line about Telegram)
    pub fn stats_line() -> Option<String> {
        let a = TG.get()?;
        let v = a.status_json();
        let g = |k: &str| v[k].as_u64().unwrap_or(0);
        Some(format!("TELEGRAM: raised {} sent {} (in {} messages) dropped {} failed {} deduped {} still queued {}{}", g("raised_total"), g("sent_total"), g("messages_total"),
            g("dropped_total"), g("failed_total"), g("deduped_total"), g("queued_now") + g("pending_now"),
            v["last_error"].as_str().map(|e| format!(" last error: {e}")).unwrap_or_default()))
    }

    pub fn mint_link(m: &Pk) -> String { let s = b58(m); format!("<a href=\"https://solscan.io/token/{s}\">{}…{}</a>", &s[..4], &s[s.len() - 4..]) }
    pub fn tx_link(sig: &str) -> String { if sig.len() < 16 { esc(sig) } else { format!("<a href=\"https://solscan.io/tx/{sig}\">{}…</a>", &sig[..8]) } }
    fn pct(num: i64, den: u64) -> String { if den == 0 { "-".into() } else { format!("{:+.1}%", num as f64 * 100.0 / den as f64) } }

    // -------- message bodies (pure: unit-tested)

    pub struct Start { pub wallet: Pk, pub build: String, pub size: u64, pub fee_est: u64, pub max_buys: u64, pub budget_sol: f64, pub run_stop_sol: f64,
        pub lock_tiers: String, pub minutes: u64, pub checks: Vec<(String, String)> }
    pub fn start_body(s: &Start) -> Body {
        let mut b = Body::new().kv("env", env_name()).kv("wallet", short(&s.wallet)).kv("build", &s.build).nl()
            .kv("size", sol(s.size as i64)).kv("fee/buy ≈", sol(s.fee_est as i64)).nl()
            .kv("max buys", s.max_buys.to_string()).kv("budget", format!("{} SOL", s.budget_sol)).kv("run stop", format!("-{} SOL (new fires)", s.run_stop_sol)).nl()
            .kv("lock tiers", if s.lock_tiers.is_empty() { "off" } else { &s.lock_tiers }).kv("minutes", s.minutes.to_string()).nl();
        for (k, v) in &s.checks { b = b.kv(k, v).nl(); }
        b
    }
    pub fn fire_body(mint: &Pk, slot: u64, dev: u64, bundle: Option<u64>, client: &str, route: &str, prio: u64, tips: u64, deadline: Option<u64>) -> Body {
        Body::new().raw(format!("mint {}", mint_link(mint))).kv("slot", slot.to_string()).nl()
            .kv("dev", sol(dev as i64)).kv("bundle", bundle.map(|b| sol(b as i64)).unwrap_or_else(|| "-".into())).nl()
            .kv("leader client", client).kv("route", route).nl()
            .kv("fee", format!("{} (priority {} + tips {})", sol((prio + tips + 5000) as i64), sol(prio as i64), sol(tips as i64)))
            .kv("deadline", deadline.map(|d| d.to_string()).unwrap_or_else(|| "none".into()))
    }
    pub fn landed_body(mint: &Pk, delta: Option<i64>, via: &str, tokens: Option<u64>, cost: u64, sig: &str) -> Body {
        Body::new().raw(format!("mint {}", mint_link(mint))).raw(format!("tx {}", tx_link(sig))).nl()
            .kv("landing", match delta { Some(0) => "SAME SLOT".to_string(), Some(d) => format!("create {d:+} slots"), None => "-".into() }).kv("seen via", via).nl()
            .kv("tokens", tokens.map(|t| t.to_string()).unwrap_or_else(|| "(read in the background)".into())).kv("cost incl. fees", sol(cost as i64))
    }
    pub fn failed_body(mint: &Pk, class: &str, delta: &str, line: &str, fee: u64, sig: &str) -> Body {
        Body::new().raw(format!("mint {}", mint_link(mint))).raw(format!("tx {}", tx_link(sig))).nl()
            .kv("class", class).kv("slots after create", delta).kv("fee", sol(fee as i64)).nl().code("error", line)
    }
    pub struct Exit { pub mint: Pk, pub legs: u32, pub proceeds: Option<i64>, pub pnl: i64, pub cost: u64, pub hold_s: f64, pub dec_send_us: Option<f64>, pub run_pnl: i64, pub trades: u64, pub src: String }
    pub fn exit_body(e: &Exit) -> Body {
        Body::new().raw(format!("mint {}", mint_link(&e.mint))).nl()
            .kv("trade PnL", format!("{} ({})", sol_signed(e.pnl), pct(e.pnl, e.cost))).kv("proceeds", e.proceeds.map(sol).unwrap_or_else(|| "- (sell txs not found)".into())).nl()
            .kv("sell legs", e.legs.to_string()).kv("hold", format!("{:.2} s", e.hold_s)).kv("decision→send", e.dec_send_us.map(|u| format!("{u:.0} µs")).unwrap_or_else(|| "-".into())).nl()
            .kv("run PnL", sol_signed(e.run_pnl)).kv("trades", e.trades.to_string()).kv("source", &e.src)
    }
    pub struct End { pub fires: u64, pub landed: u64, pub wins: u64, pub losses: u64, pub net: i64, pub usd: Option<f64>, pub best: Option<(Pk, i64)>,
        pub worst: Option<(Pk, i64)>, pub fees: u64, pub same_slot_pct: Option<f64>, pub median_delta: Option<i64>, pub reason: String,
        /// M8-2: end balance - start balance (None: a balance read failed); L8-3: estimated fees, the SOL price's age (min)
        pub wallet_net: Option<i64>, pub fees_est: u64, pub usd_age_min: Option<u64> }
    pub fn end_body(e: &End) -> Body {
        let tr = |x: &Option<(Pk, i64)>| x.map(|(m, p)| format!("{} {}", short(&m), sol_signed(p))).unwrap_or_else(|| "-".into());
        // L8-3: USD only from a SOL price <= 30 min old (else marked stale, no dollar figure)
        let usd = |l: i64| match (e.usd, e.usd_age_min) { (Some(p), Some(a)) if a <= 30 => format!(" (${:+.2})", l as f64 / 1e9 * p), (Some(_), Some(a)) => format!(" (SOL price stale: {a} min)"), _ => String::new() };
        Body::new().kv("ended", &e.reason).nl().kv("fires", e.fires.to_string()).kv("landed", e.landed.to_string())
            .kv("wins / losses", format!("{} / {}", e.wins, e.losses)).nl()
            .kv("net (trades)", format!("{}{}", sol_signed(e.net), usd(e.net)))
            .kv("net (wallet)", e.wallet_net.map(|w| format!("{}{}", sol_signed(w), usd(w))).unwrap_or_else(|| "unread".into())).nl()
            .kv("fees paid", format!("{}{}", sol(e.fees as i64), if e.fees_est > 0 { format!(" + {} est (CU limit x price + tips + base)", sol(e.fees_est as i64)) } else { String::new() }))
            .nl().kv("best", tr(&e.best)).kv("worst", tr(&e.worst)).nl()
            .kv("same slot", e.same_slot_pct.map(|p| format!("{p:.0}%")).unwrap_or_else(|| "-".into()))
            .kv("median landing", e.median_delta.map(|d| format!("create {d:+} slots")).unwrap_or_else(|| "-".into()))
    }
    fn short(k: &Pk) -> String { let s = b58(k); format!("{}…{}", &s[..4], &s[s.len() - 4..]) }

    /// /root/solprice.json {"sol_usd": ...}: (price, age in minutes from the file's mtime; the cron rewrites it every 10 min)
    pub fn sol_usd() -> Option<(f64, Option<u64>)> {
        let path = "/root/solprice.json";
        let v: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(path).ok()?).ok()?;
        let p = v["sol_usd"].as_f64().or_else(|| v["sol_usd"].as_str().and_then(|s| s.parse().ok())).filter(|p| *p > 0.0)?;
        let age = std::fs::metadata(path).ok().and_then(|m| m.modified().ok()).and_then(|t| t.elapsed().ok()).map(|d| d.as_secs() / 60);
        Some((p, age))
    }

    // -------- the run's trade records (exit path only), for the end summary
    #[derive(Default)]
    pub struct Book { pub trades: Vec<(Pk, i64)>, pub deltas: Vec<i64>, pub fees: u64, pub fees_est: u64 }
    pub static BOOK: std::sync::LazyLock<std::sync::Mutex<Book>> = std::sync::LazyLock::new(|| std::sync::Mutex::new(Book::default()));
    pub static FEED_TXS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

    pub fn end_summary(fires: u64, landed: u64, reason: &str, wallet_net: Option<i64>) -> End {
        let b = BOOK.lock().unwrap();
        let wins = b.trades.iter().filter(|t| t.1 > 0).count() as u64;
        let net: i64 = ACCT.realized.load(Ordering::SeqCst);
        let mut d = b.deltas.clone();
        d.sort_unstable();
        let px = sol_usd();
        End { fires, landed, wins, losses: b.trades.len() as u64 - wins, net, usd: px.map(|x| x.0), usd_age_min: px.and_then(|x| x.1), wallet_net, fees_est: b.fees_est,
            best: b.trades.iter().max_by_key(|t| t.1).copied(), worst: b.trades.iter().min_by_key(|t| t.1).copied(), fees: b.fees,
            same_slot_pct: (!d.is_empty()).then(|| d.iter().filter(|x| **x <= 0).count() as f64 * 100.0 / d.len() as f64),
            median_delta: d.get(d.len() / 2).copied(), reason: reason.into() }
    }

    /// --telegram-test: one message, delivered now (blocking, up to 15 s), then exit
    pub fn test_message() -> Result<()> {
        let _ = ENV.set(arg("--env-name").unwrap_or_else(|| "DEV".into()).to_ascii_uppercase());
        let ctx = arbx::alerts::Ctx { label: format!("SNIPER {}", env_name()), ..Default::default() };
        let (a, notes) = Alerts::new(&cfg(), &|k| std::env::var(k).ok(), ctx);
        for n in notes { eprintln!("TELEGRAM: {n}"); }
        if !a.enabled() { bail!("Telegram is off: {}", a.off_why().unwrap_or("?")); }
        let al = Alert::new(Level::Info, "snipe_test", "test", "snipe_engine Telegram test").icon("✅")
            .body(Body::new().kv("env", env_name()).kv("host", arbx::provenance::hostname())).once();
        match a.deliver_now(vec![al], Duration::from_secs(15)) {
            Ok(n) => { eprintln!("TELEGRAM TEST: {n} message(s) delivered"); Ok(()) }
            Err((n, e)) => bail!("Telegram test: {n} delivered, error: {e}"),
        }
    }
}

// =====================================================================================================================
// RUN ACCOUNTING (audit 2026-10-20: C1, L3, L4, M7; re-audit N1-N3). One per process (the live loop runs once).
//  * a position's cost counts as OPEN only from "buy landed with tokens" until "sold" (N1: a CONFIRMED read shows the
//    token account closed or at 0, at a context slot >= the last sell's landing): a buy that never lands or reverts never
//    inflates the run PnL;
//  * `pending`: fired buys whose landing is not resolved yet; `inflight`: positions from fire until the exit is done;
//  * the budget (--max-total-sol) and --max-buys count LANDED buys (actual cost incl. fees); a fire RESERVES its spend
//    until its landing resolves (so two concurrent fires cannot overshoot), REFUSED / prepare-failed never reserve;
//  * `realized`: in-engine realized PnL from each position's own transactions (payer balance deltas): the kill
//    switch's second check;
//  * `fired`: EVERY mint the run fired a buy on, with the slot a read of its token account must reach (the buy's landing,
//    0 when unknown): after the drain each one is re-read at CONFIRMED commitment and anything not 0 is HELD-AT-EXIT
//    (N1/N3: whatever the in-run logic concluded, a token left on the wallet is listed);
//  * `seq`: bumped on every position state change (N2: the kill switch skips a poll whose read raced one);
//  * `last_slot`: the highest slot of a landing / sold read the engine acted on (N2: the kill switch's getBalance asks a
//    node at least that far: minContextSlot);
//  * `bal`: the kill switch's last good balance (L3 pre-fire balance check, no RPC on the fire path).
// =====================================================================================================================
#[derive(Default)]
struct Acct {
    open: std::sync::atomic::AtomicU64,
    pending: std::sync::atomic::AtomicU64,
    pending_spend: std::sync::atomic::AtomicU64,
    inflight: std::sync::atomic::AtomicU64,
    reserved: std::sync::atomic::AtomicU64,
    budget_used: std::sync::atomic::AtomicU64,
    landed_buys: std::sync::atomic::AtomicU64,
    realized: std::sync::atomic::AtomicI64,
    bal: std::sync::atomic::AtomicU64,
    /// L3: cost of buys seen landed since the kill switch's last balance read began (that balance may not show them yet)
    landed_since_bal: std::sync::atomic::AtomicU64,
    seq: std::sync::atomic::AtomicU64,
    last_slot: std::sync::atomic::AtomicU64,
    fired: std::sync::Mutex<std::collections::HashMap<Pk, u64>>,
    pend_sigs: std::sync::Mutex<std::collections::HashMap<Pk, String>>,
    /// L-1 (audit 3): open positions (mint -> cost), logged with their worst-case exposure when the kill switch trips
    open_pos: std::sync::Mutex<std::collections::HashMap<Pk, u64>>,
    /// H-1: the Launch of every landed buy (the exit sells of HELD-AT-EXIT mints need its accounts)
    launches: std::sync::Mutex<std::collections::HashMap<Pk, Launch>>,
}
static ACCT: std::sync::LazyLock<Acct> = std::sync::LazyLock::new(Acct::default);
fn acct_bump() { ACCT.seq.fetch_add(1, Ordering::SeqCst); }
fn acct_slot(s: u64) { if s > 0 { ACCT.last_slot.fetch_max(s, Ordering::SeqCst); } }

/// Token-2022 base ATA rent (170 bytes: account + ImmutableOwner), refunded when the sell closes it
const T22_ATA_RENT: u64 = 2_074_080;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
enum PosState { Pending, Open, Closed }

/// one position's accounting (RAII: a task that ends early releases what it holds)
struct Pos { mint: Pk, spend: u64, fee_est: u64, state: PosState, cost: u64, realized_done: bool }
impl Pos {
    /// at the FIRE: reserve the budget, count it pending + in flight
    fn new(mint: Pk, spend: u64, fee_est: u64, sig: &str) -> Pos {
        let a = &*ACCT;
        a.inflight.fetch_add(1, Ordering::SeqCst);
        a.pending.fetch_add(1, Ordering::SeqCst);
        a.pending_spend.fetch_add(spend + fee_est, Ordering::SeqCst);
        a.reserved.fetch_add(spend + fee_est, Ordering::SeqCst);
        a.pend_sigs.lock().unwrap().insert(mint, sig.to_string());
        a.fired.lock().unwrap().entry(mint).or_insert(0);
        acct_bump();
        Pos { mint, spend, fee_est, state: PosState::Pending, cost: 0, realized_done: false }
    }
    /// release the pending counters + reservation; `keep_sig`: the buy is UNRESOLVED (N3): keep it for PENDING-AT-EXIT
    fn unpend_keep(&self, keep_sig: bool) {
        let a = &*ACCT;
        a.pending.fetch_sub(1, Ordering::SeqCst);
        a.pending_spend.fetch_sub(self.spend + self.fee_est, Ordering::SeqCst);
        a.reserved.fetch_sub(self.spend + self.fee_est, Ordering::SeqCst);
        if !keep_sig { a.pend_sigs.lock().unwrap().remove(&self.mint); }
        acct_bump();
    }
    fn unpend(&self) { self.unpend_keep(false) }
    /// the buy landed WITH tokens at `land_slot`: the position is open at `cost` (actual: balance delta, or spend + fees + rent)
    fn landed(&mut self, cost: u64, land_slot: u64) {
        if self.state != PosState::Pending { return; }
        self.unpend();
        let a = &*ACCT;
        a.open.fetch_add(cost, Ordering::SeqCst);
        a.landed_since_bal.fetch_add(cost, Ordering::SeqCst);
        a.budget_used.fetch_add(cost.saturating_sub(T22_ATA_RENT).max(self.spend), Ordering::SeqCst);
        a.landed_buys.fetch_add(1, Ordering::SeqCst);
        a.fired.lock().unwrap().insert(self.mint, land_slot);
        a.open_pos.lock().unwrap().insert(self.mint, cost);
        acct_slot(land_slot);
        acct_bump();
        self.state = PosState::Open;
        self.cost = cost;
    }
    /// the position's cost refined after the fact (the balance read finished after the sell decision): the budget (and the
    /// open total while still open) move by the difference
    fn refine_cost(&mut self, new: u64) {
        if self.cost == 0 || self.cost == new || self.state == PosState::Pending { return; }
        let b = |c: u64| c.saturating_sub(T22_ATA_RENT).max(self.spend) as i64;
        let db = b(new) - b(self.cost);
        if db >= 0 { ACCT.budget_used.fetch_add(db as u64, Ordering::SeqCst); } else { ACCT.budget_used.fetch_sub((-db) as u64, Ordering::SeqCst); }
        if self.state == PosState::Open {
            if new > self.cost { ACCT.open.fetch_add(new - self.cost, Ordering::SeqCst); } else { ACCT.open.fetch_sub(self.cost - new, Ordering::SeqCst); }
            ACCT.open_pos.lock().unwrap().insert(self.mint, new);
        }
        self.cost = new;
        acct_bump();
    }
    /// the buy can no longer land (its blockhash is dead) or was never sent: release the reservation
    fn not_landed(&mut self) {
        if self.state != PosState::Pending { return; }
        self.unpend();
        self.state = PosState::Closed;
        self.realized_done = true;
    }
    /// N3: the buy's fate is UNKNOWN (the late-landing watch hit its safety cap before the blockhash was seen dead):
    /// counters released, the signature kept for PENDING-AT-EXIT, the mint re-read at exit (HELD-AT-EXIT)
    fn unresolved(&mut self) {
        if self.state != PosState::Pending { return; }
        self.unpend_keep(true);
        self.state = PosState::Closed;
        self.realized_done = true;
    }
    /// the buy landed but REVERTED (fill cap): no position; its fee counts (budget + realized)
    fn reverted(&mut self, fee: u64) {
        if self.state != PosState::Pending { return; }
        self.unpend();
        ACCT.budget_used.fetch_add(fee, Ordering::SeqCst);
        ACCT.realized.fetch_sub(fee as i64, Ordering::SeqCst);
        self.state = PosState::Closed;
        self.realized_done = true;
    }
    /// N1: a CONFIRMED read shows the token account closed / at 0 at context slot `ctx`: the position is no longer open
    fn sold(&mut self, ctx: u64) {
        if self.state != PosState::Open { return; }
        ACCT.open.fetch_sub(self.cost, Ordering::SeqCst);
        ACCT.open_pos.lock().unwrap().remove(&self.mint);
        acct_slot(ctx);
        acct_bump();
        self.state = PosState::Closed;
    }
}
impl Drop for Pos {
    fn drop(&mut self) {
        match self.state {
            PosState::Pending => self.unpend(),
            // ended while still holding tokens (UNSOLD / error): no longer valued at cost (the balance shows the loss, so
            // the kill switch sees it); the mint is re-read at exit (HELD-AT-EXIT)
            PosState::Open => { ACCT.open.fetch_sub(self.cost, Ordering::SeqCst); ACCT.open_pos.lock().unwrap().remove(&self.mint); acct_bump(); }
            PosState::Closed => {}
        }
        if self.state != PosState::Pending && !self.realized_done && self.cost > 0 { ACCT.realized.fetch_sub(self.cost as i64, Ordering::SeqCst); }
        ACCT.inflight.fetch_sub(1, Ordering::SeqCst);
        acct_bump();
    }
}

/// C1/M7/N2: the kill switch / profit lock decision for one EVALUATED balance poll (pure: unit-tested with the audit's
/// scenarios). A poll whose read raced a position change is not evaluated at all (the caller skips it).
#[derive(Clone, Copy, Debug, Default)]
struct KsState { floor: Option<i64>, prev_below: bool, prev_lock: bool }
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum KsVerdict { Go, Kill, KillRealized, Lock }
/// `pnl` = balance + open (landed positions at cost) - start; `pending` = fired buys not resolved; `inflight` = positions
/// from fire to exit done. N2: KILL needs pnl < -cap on 2 consecutive evaluated polls, always (a lagging node's balance
/// can trail a sale or a landing by a poll). Realized < -cap (from confirmed transactions) kills at once. The lock tiers
/// arm and trip only with nothing in flight, and the trip needs 2 consecutive evaluated polls below the floor.
fn ks_eval(st: &mut KsState, pnl: i64, realized: i64, pending: u64, inflight: u64, cap: i64, tiers: &[(i64, i64)]) -> (KsVerdict, Vec<String>) {
    let mut log = Vec::new();
    let below = pnl < -cap;
    let kill = below && st.prev_below;
    if below && !kill { log.push(format!("KILL-SWITCH pending confirmation: run PnL {:.6} below -{:.6} ({pending} buy(s) unresolved; re-check next poll)", pnl as f64 / 1e9, cap as f64 / 1e9)); }
    st.prev_below = below;
    if kill { return (KsVerdict::Kill, log); }
    if realized < -cap { return (KsVerdict::KillRealized, log); }
    if inflight > 0 { st.prev_lock = false; return (KsVerdict::Go, log); }
    for (arm, fl) in tiers {
        if pnl >= *arm && st.floor.is_none_or(|f| *fl > f) { st.floor = Some(*fl); log.push(format!("PROFIT-LOCK armed: run PnL {:.6} SOL >= {:.6} -> floor {:.6}", pnl as f64 / 1e9, *arm as f64 / 1e9, *fl as f64 / 1e9)); }
    }
    let under = st.floor.is_some_and(|f| pnl < f);
    let lock = under && st.prev_lock;
    if under && !lock { log.push(format!("PROFIT-LOCK pending confirmation: run PnL {:.6} below floor {:.6} (re-check next poll)", pnl as f64 / 1e9, st.floor.unwrap_or(0) as f64 / 1e9)); }
    st.prev_lock = under;
    if lock { return (KsVerdict::Lock, log); }
    (KsVerdict::Go, log)
}

// =====================================================================================================================
// N1 / N8 (re-audit 2026-10-20): token-account and balance reads with their CONTEXT SLOT and a per-call timeout.
// getAccountInfo (base64, dataSlice = the amount at bytes 64..72) with minContextSlot: a node that is behind the required
// slot answers an error, which reads as Unknown — never as a stale 0. Only a well-formed answer whose value is null (the
// account does not exist at that node's commitment, at a context slot >= the required one) reads as Closed. Every RPC
// error (incl. "could not find account" / "Invalid param" / timeouts) is Unknown.
// =====================================================================================================================
/// per-call cap on the reads of the exit path (the client's own timeout is 20 s)
const RPC_READ_TIMEOUT: Duration = Duration::from_secs(3);

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum Tok { Amount(u64, u64), Closed(u64), Unknown }
impl Tok {
    /// the account holds nothing (closed or 0): the context slot of that answer
    fn zero_at(self) -> Option<u64> { match self { Tok::Closed(c) | Tok::Amount(0, c) => Some(c), _ => None } }
    fn amount(self) -> Option<u64> { match self { Tok::Amount(a, _) => Some(a), Tok::Closed(_) => Some(0), Tok::Unknown => None } }
    fn show(self) -> String { match self { Tok::Amount(a, c) => format!("{a} (slot {c})"), Tok::Closed(c) => format!("closed (slot {c})"), Tok::Unknown => "unreadable".into() } }
}

/// parse a getAccountInfo(dataSlice 64..8) result into a Tok (pure: unit-tested)
fn tok_parse(v: &serde_json::Value, min_slot: u64) -> Tok {
    let Some(ctx) = v["context"]["slot"].as_u64() else { return Tok::Unknown };
    if ctx < min_slot { return Tok::Unknown; }
    if v.get("value").is_some_and(|x| x.is_null()) { return Tok::Closed(ctx); }
    let Some(b64) = v["value"]["data"][0].as_str() else { return Tok::Unknown };
    match base64::engine::general_purpose::STANDARD.decode(b64) {
        Ok(b) if b.len() == 8 => Tok::Amount(u64::from_le_bytes(b.try_into().unwrap()), ctx),
        _ => Tok::Unknown,
    }
}

/// one read of the token account `ata` at `commitment` ("processed" / "confirmed"), from a node at slot >= `min_slot`
async fn tok_read(rpc: &rpc::Rpc, ata: &Pk, commitment: &str, min_slot: u64) -> Tok {
    let mut cfg = serde_json::json!({ "encoding": "base64", "commitment": commitment, "dataSlice": { "offset": 64, "length": 8 } });
    if min_slot > 0 { cfg["minContextSlot"] = serde_json::json!(min_slot); }
    // H-1: primary then the fallback RPC, each capped at 3 s
    match call2(rpc, "getAccountInfo", serde_json::json!([b58(ata), cfg])).await {
        Ok(v) => tok_parse(&v, min_slot),
        Err(e) => { poll_err("getAccountInfo(token)", &e); Tok::Unknown }
    }
}

/// up to `tries` reads 300 ms apart; the first answer that is not Unknown
async fn tok_read_retry(rpc: &rpc::Rpc, ata: &Pk, commitment: &str, min_slot: u64, tries: u32) -> Tok {
    for k in 0..tries.max(1) {
        if k > 0 { tokio::time::sleep(Duration::from_millis(300)).await; }
        let t = tok_read(rpc, ata, commitment, min_slot).await;
        if t != Tok::Unknown { return t; }
    }
    Tok::Unknown
}

/// N2/N8: getBalance (processed) from a node at slot >= `min_slot`, capped at RPC_READ_TIMEOUT
async fn native_balance_at(rpc: &rpc::Rpc, who: Pk, min_slot: u64) -> Result<u64> {
    let mut cfg = serde_json::json!({ "commitment": "processed" });
    if min_slot > 0 { cfg["minContextSlot"] = serde_json::json!(min_slot); }
    let v = call2(rpc, "getBalance", serde_json::json!([b58(&who), cfg])).await.context("getBalance")?;
    v["value"].as_u64().context("getBalance: no value")
}

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
    let envf = arg("--env-file").unwrap_or_else(|| "/root/sniper/deploy/.env".to_string());
    let _ = dotenvy::from_filename(&envf).or_else(|_| dotenvy::dotenv());
    check_safety_flags()?;
    alpenglow_warning();
    // --telegram-test: one message to the chat (TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID from the env file), then exit
    if has("--telegram-test") { return tg::test_message(); }

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

    let r = rt.block_on(run(&probe, key, user, rpc, warm_probe, shadow, round_trip, snipe_once, simulate, paper_trade, live));
    if let Err(e) = &r { tg::raise(arbx::alerts::Level::Critical, "snipe_error", "error", "💥", "ENGINE STOPPED WITH AN ERROR", arbx::alerts::format::Body::new().code("error", redact(&format!("{e:#}"))), false); }
    // Telegram: everything queued goes out before the process ends (<= 6 s; the runtime still runs the sender)
    tg::flush(Duration::from_secs(6));
    if let Some(l) = tg::stats_line() { eprintln!("{l}"); }
    INFRA_STOP.store(true, Ordering::Relaxed);
    r
}

#[allow(clippy::too_many_arguments)]
async fn run(probe: &Probe, key: SigningKey, user: Pk, rpc: Arc<rpc::Rpc>, warm_probe: bool, shadow: bool, round_trip: bool, snipe_once: bool, simulate: bool, paper_trade: bool, live: bool) -> Result<()> {
    let stop = Arc::new(AtomicBool::new(false));
    let _ = RUN_STOP.set(stop.clone());
    // Telegram: the old arb bot's sender on this runtime (off with --no-telegram or without the env vars)
    tg::init(&tokio::runtime::Handle::current());
    // SELF-HEAL (every send path: the slow client and the FAST connections): one line per health edge + a Telegram
    // alert, deduplicated (10 min) per path and edge
    send::set_health_hook(|name, healthy, detail| {
        eprintln!("  SEND-PATH {name} {}: {detail}", if healthy { "RECOVERED" } else { "UNHEALTHY" });
        tg::raise(if healthy { arbx::alerts::Level::Info } else { arbx::alerts::Level::Warning }, "snipe_path_health", &format!("path:{name}:{healthy}"),
            if healthy { "🟢" } else { "🩹" }, &format!("Send path {name} {}", if healthy { "RECOVERED" } else { "UNHEALTHY (self-heal)" }), arbx::alerts::format::Body::new().txt(detail), true);
    });
    // M5-2: the primary must be mainnet too (a wrong-cluster RPC would feed blockhashes and balances)
    match genesis_retry(&rpc).await {
        Ok(Ok(v)) if v.as_str() == Some(MAINNET_GENESIS) => {}
        Ok(Ok(v)) => bail!("rpc_url: genesis hash {v} is NOT mainnet ({MAINNET_GENESIS}) — refusing to start"),
        // L6-5a (audit 6): an unverifiable primary refuses to start too (as the fallback)
        Ok(Err(e)) => bail!("rpc_url: getGenesisHash failed ({}) — cannot verify the cluster: refusing to start", redact(&format!("{e:#}"))),
        Err(_) => bail!("rpc_url: getGenesisHash timed out — cannot verify the cluster: refusing to start"),
    }
    let infra = INFRA_STOP.clone();
    // H-1 (audit 3): --rpc-fallback-url-env NAME: the second RPC of the exit path (the URL from env var NAME, never printed).
    // Given but empty / missing: refuse to start (fail closed).
    if let Some(name) = arg("--rpc-fallback-url-env") {
        let url = std::env::var(&name).ok().filter(|u| !u.trim().is_empty()).with_context(|| format!("--rpc-fallback-url-env {name}: the env var is empty or missing — refusing to start"))?;
        let url = config::expand(url.trim()).with_context(|| format!("--rpc-fallback-url-env {name}: names an empty env var"))?;
        let fb = rpc::Rpc::new(url);
        // M5-2 (audit 5): the fallback must be MAINNET (genesis hash), or no start: it feeds the blockhash and every exit read
        match genesis_retry(&fb).await {
            Ok(Ok(v)) if v.as_str() == Some(MAINNET_GENESIS) => eprintln!("RPC-FALLBACK: {name} genesis = mainnet ({}…)", &MAINNET_GENESIS[..8]),
            Ok(Ok(v)) => bail!("--rpc-fallback-url-env {name}: genesis hash {v} is NOT mainnet ({MAINNET_GENESIS}) — refusing to start"),
            Ok(Err(e)) => bail!("--rpc-fallback-url-env {name}: getGenesisHash failed ({}) — cannot verify the cluster: refusing to start", redact(&format!("{e:#}"))),
            Err(_) => bail!("--rpc-fallback-url-env {name}: getGenesisHash timed out — cannot verify the cluster: refusing to start"),
        }
        match tokio::time::timeout(Duration::from_secs(5), fb.slot()).await {
            Ok(Ok(sl)) => eprintln!("RPC-FALLBACK: {name} answers (slot {sl}); the exit path's reads + sell blockhashes fall back to it"),
            Ok(Err(e)) => eprintln!("RPC-FALLBACK: {name} did NOT answer getSlot at start ({}) — kept as the fallback anyway", redact(&format!("{e:#}")).chars().take(120).collect::<String>()),
            Err(_) => eprintln!("RPC-FALLBACK: {name} did not answer getSlot within 5 s at start — kept as the fallback anyway"),
        }
        let _ = RPC_FB.set(fb);
    }
    // ALT cache: the known launchpad tables + --alt-cache-file + --alt-preload, before any feed starts
    altc::init(rpc.clone()).await;
    // M-3 (audit 3): --buy-max-slot-delta N: the on-chain slot deadline, verified by simulation now or no start (fail closed)
    if has("--buy-max-slot-delta") {
        let g = verify_slot_guard(&rpc, &key, user).await.context("--buy-max-slot-delta")?;
        let _ = SLOT_GUARD.set(g);
    }
    // H1 (audit 2026-10-20): SIGTERM / SIGINT = stop new fires and DRAIN: the open positions finish their exit (the drain
    // is bounded, then every mint still held is logged HELD-AT-EXIT). A second signal changes nothing (still draining).
    // Only the snipe loop installs it (the other modes exit on their own); the guard stops the engine this way.
    if snipe_once {
        use tokio::signal::unix::{signal, SignalKind};
        // M-1 (audit 3): SIGHUP too (a dropped SSH session): the same stop + drain, never the default kill
        let (mut term, mut int, mut hup) = (signal(SignalKind::terminate())?, signal(SignalKind::interrupt())?, signal(SignalKind::hangup())?);
        let st = stop.clone();
        tokio::spawn(async move {
            loop {
                let name = tokio::select! { _ = term.recv() => "SIGTERM", _ = int.recv() => "SIGINT", _ = hup.recv() => "SIGHUP" };
                eprintln!("  SIGNAL {name}: stopping new fires; open positions keep selling (drain), then HELD-AT-EXIT lists anything still held");
                tg::raise(arbx::alerts::Level::Warning, "snipe_signal", name, "🛑", &format!("SIGNAL {name}: stopping new fires, draining"), arbx::alerts::format::Body::new().txt("open positions keep selling; HELD-AT-EXIT lists anything still held"), false);
                st.store(true, Ordering::SeqCst);
            }
        });
    }

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
    if let Some(fname) = arg("--sell-fallback-path") {
        match paths.index(&fname) {
            Some(i) => {
                let fb = paths.list[i].clone();
                if SELL_PATH.get().is_some_and(|sp| sp.name == fb.name) { bail!("--sell-fallback-path {fname}: is the --sell-path itself"); }
                eprintln!("snipe_engine: SELL FALLBACK path = {} (every sell retry goes to the sell path AND {}, one signature{})", fb.name, fb.name,
                    fb.tip(0).map(|(_, l)| format!(", its minimum tip {l} lamports in the retry tx")).unwrap_or_default());
                let _ = SELL_FALLBACK.set(fb);
            }
            None => bail!("--sell-fallback-path {fname}: no such [[send]] path (or it failed to build: see the send notes)"),
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
    // M2: the close-leader gate reads the same compact leader book (current + next epoch, refreshed every 10 min)
    if lat::ROUTES.get().is_some() || has("--ack-probe") || has("--close-leaders") {
        match lat::refresh(&rpc).await {
            Ok(m) => eprintln!("  {m}"),
            Err(e) if lat::ROUTES.get().is_some() || has("--close-leaders") => bail!("--route-by-client / --close-leaders: the leader book failed: {e:#}"),
            Err(e) => eprintln!("  leader book: {e:#}"),
        }
        lat::start_refresh(rpc.clone(), infra.clone());
    }
    if let Some(f) = arg("--send-log") {
        let file = std::fs::OpenOptions::new().create(true).append(true).open(&f).with_context(|| format!("--send-log {f}"))?;
        let _ = lat::SEND_LOG.set(std::sync::Mutex::new(file));
        eprintln!("snipe_engine: per-path send log -> {f}");
    }

    // ---- keep the current slot fresh for the tpu leader targeting (the real engine feeds this from its state
    // stream; here a lightweight poller feeds send::tpu::SLOT from the RPC's processed slot).
    {
        let (rpc, stop) = (rpc.clone(), infra.clone());
        tokio::spawn(async move {
            while !stop.load(Ordering::Relaxed) {
                if let Ok(s) = rpc.slot().await {
                    let cur = send::tpu::SLOT.load(Ordering::Relaxed);
                    if s > cur { slot_note(SLOT_SRC_PRIMARY, s); }
                }
                tokio::time::sleep(Duration::from_millis(250)).await;
            }
        });
    }
    {
        // blockhash refresher: a buy takes the cached hash (<= ~300 ms old, valid ~60 s) instead of a round trip.
        let (rpc, stop) = (rpc.clone(), infra.clone());
        tokio::spawn(async move {
            // M4-1 (owner): primary AND fallback in parallel every ~400 ms, the newest blockhash kept (the sell path only
            // reads this cache)
            // M5-2: no usable blockhash for > 5 s (no newer one accepted from either RPC) = log loudly and stop NEW fires
            // (open positions keep trying: the sell path uses the cache up to 20-25 s, then the inline refresh)
            // L6-3 (audit 6): a PAUSE of new fires that clears after 10 s of usable blockhashes (both edges logged)
            let t_start = Instant::now();
            let mut good_since: Option<Instant> = None;
            let mut long_alerted = false;
            while !stop.load(Ordering::Relaxed) {
                let _ = refresh_blockhash(&rpc, Duration::from_secs(1)).await;
                let age = BLOCKHASH_CACHE.lock().unwrap().map(|(_, t, _)| t.elapsed()).unwrap_or_else(|| t_start.elapsed());
                let paused = FIRE_PAUSE.load(Ordering::SeqCst);
                // L8-6: fires paused for > 60 s: a Critical alert (once per pause episode)
                if paused && good_since.is_none() && age > Duration::from_secs(67) && !long_alerted {
                    long_alerted = true;
                    tg::raise(arbx::alerts::Level::Critical, "snipe_bh_pause_long", "bh_pause_long", "🚨", "Fires PAUSED for > 60 s: no usable blockhash", arbx::alerts::format::Body::new().kv("newest blockhash age", format!("{:.0} s", age.as_secs_f64())).txt("check both RPCs (genesis-verified at start); open positions keep selling"), false);
                }
                if !paused { long_alerted = false; }
                // L7-3 (audit 7): the age is the blockhash's own (birth-dated, incl. the ~1-2.5 s confirmed-vs-tip lag): pause at 7 s
                if age > Duration::from_secs(7) {
                    good_since = None;
                    if !paused {
                        FIRE_PAUSE.store(true, Ordering::SeqCst);
                        eprintln!("  !!!!! PAUSE: NO USABLE BLOCKHASH: the newest is {:.1} s old (neither RPC returned a newer one) — NEW FIRES PAUSED; open positions keep trying to sell; resumes after 10 s of usable blockhashes !!!!!", age.as_secs_f64());
                        tg::raise(arbx::alerts::Level::Error, "snipe_bh_pause", "bh_pause", "⏸", "Blockhash PAUSE: new fires paused", arbx::alerts::format::Body::new().kv("newest blockhash age", format!("{:.1} s", age.as_secs_f64())).txt("open positions keep selling; resumes after 10 s of usable blockhashes"), false);
                    }
                } else if paused {
                    let since = *good_since.get_or_insert_with(Instant::now);
                    if since.elapsed() >= Duration::from_secs(10) {
                        FIRE_PAUSE.store(false, Ordering::SeqCst);
                        good_since = None;
                        eprintln!("  RESUME: usable blockhashes for 10 s (age {:.1} s) — new fires allowed again", age.as_secs_f64());
                        tg::raise(arbx::alerts::Level::Info, "snipe_bh_resume", "bh_resume", "▶️", "Blockhash RESUME: new fires allowed again", arbx::alerts::format::Body::new().kv("age", format!("{:.1} s", age.as_secs_f64())), false);
                    }
                }
                tokio::time::sleep(Duration::from_millis(400)).await;
            }
        });
    }

    // ---- start the WARM loops: for a tpu path this spawns Tpu::keep_warm (pre-opens QUIC to the next leaders,
    // refreshes the leader window + cluster nodes) and a per-path keep-alive. THIS is the whole point.
    paths.start(infra.clone(), Duration::from_secs(2), |m: String| eprintln!("  keepalive: {m}"));

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
        let arbx::feeds::Event::Tx(mut a) = ev else { continue };
        altc::fill(&mut a.tx); // ALT: lookup tables resolved from the cache (fail closed on a miss)
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
/// M3: when / how the landing was SEEN (`t_seen`; via "status" = getSignatureStatuses with its exact slot, "ata" = the
/// token account changed: the slot is the RPC's context slot, an upper bound). L1: `last_valid` = the blockhash's last
/// valid block height (0 unknown): past it a never-seen tx can no longer land.
/// M-2: `err` = the on-chain error of a landed-failed tx (signature status); `roles` = (slot-guard ix, pump buy ix) indices.
/// M4-1: `tokens` = the token amount the landing watch saw (a buy seen via its token account); `t_sent` = when a sell was
/// handed to the send paths.
struct Landed { sig: String, send_slot: u64, land_slot: Option<u64>, ok: bool, t_seen: Option<Instant>, via: &'static str, last_valid: u64,
    err: Option<serde_json::Value>, roles: (Option<u8>, Option<u8>), tokens: Option<u64>, t_sent: Option<Instant>, tips: u64 }

/// M3: what else a land poll watches besides the signature status: the token account (a buy: tokens appear; a sell: the
/// balance drops below the amount held before it / the account is closed). Landing is then seen even when every
/// getSignatureStatuses call fails.
/// N1: SellAta carries the slot the read must reach (the buy's landing): a node behind it answers Unknown, not a stale 0.
/// A token-account change is only a landing HINT for a sell: the position is closed only by a CONFIRMED zero read.
#[derive(Clone, Copy)]
enum Watch { None, BuyAta(Pk), SellAta(Pk, u64, u64) }

/// Reusable: compile the given ixs on a FRESH recent blockhash, sign, send through the WARM path, and poll
/// getSignatureStatuses for the land slot. The one place the engine turns an instruction list into a landed tx.
async fn send_and_poll(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, ixs: &[build::Ix], land_timeout: Duration) -> Result<Landed> {
    send_and_poll_at(key, user, rpc, path, ixs, land_timeout, None, Watch::None).await
}

/// `send_and_poll` for a BUY aimed at `target_slot` (the create's slot: LAT per-leader-client routing reads its leader)
#[allow(clippy::too_many_arguments)]
async fn send_and_poll_at(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, ixs: &[build::Ix], land_timeout: Duration, target_slot: Option<u64>, watch: Watch) -> Result<Landed> {
    let t_sp = Instant::now();
    // Tipped send paths (nozomi / jito-tx / helius / 0slot ...) require a top-level System tip transfer to one of the
    // path's tip accounts, or Path::check refuses the send. Tipless paths (staked-rpc / tpu-direct) return None -> unchanged.
    // --also-send: only for non-sell sends (a sell goes through SELL_PATH), and only to a different path.
    // DET FIX: "is this a buy" is read from the instructions (the pump buy disc). The old test (path != SELL_PATH) also
    // double-sent every SELL, paying the also-path's tip, whenever --sell-path was not given (sells then use the buy path).
    let is_buy = ixs.iter().any(|ix| ix.data.starts_with(&snipe_build::BUY_EXACT_QUOTE_IN_V3_DISC));
    // LAT: the fan-out set: --route-by-client / --multi-send for buys; else [path] (+ --also-send for buys), as before
    let (mut fan, mut meta) = if is_buy { lat::buy_paths(path, ALSO_PATH.get(), target_slot) } else { (vec![path.clone()], lat::Meta { route: "single".into(), ..Default::default() }) };
    let (blockhash, last_valid) = blockhash_fresh(rpc, Duration::from_secs(20)).await?;
    // one tip per tip family for every path in the fan-out, the CU limit raised for the extra transfers; a tx over the
    // 1232-byte packet limit drops paths from the end (their tips with them) until it fits
    let (raw, tips) = lat::build_tx(key, user, ixs, &mut fan, blockhash)?;
    let roles = ix_roles(&raw); // M-2
    let sig = send::first_signature(&raw).context("signed tx has no signature")?;
    let mut sig_bytes = [0u8; 64];
    sig_bytes.copy_from_slice(&bs58::decode(&sig).into_vec()?);
    let send_slot = match send::tpu::SLOT.load(Ordering::Relaxed) { 0 => rpc.slot().await.unwrap_or(0), s => s };
    meta.sig = sig.clone();
    meta.bytes = raw.len();
    meta.tips = tips.iter().map(|t| t.1).sum();
    eprintln!("  SEND-PREP {:.1} ms (send_and_poll entry -> send)", t_sp.elapsed().as_secs_f64() * 1e3);
    if is_buy { eprintln!("  FEE sig={} {}", &sig[..16.min(sig.len())], fee_line(ixs, meta.tips)); }
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
        if is_buy { fire_note_raise(ixs, &meta); }
        fix2::spawn_jito_poll(&fan, &sig, 0);
        let mut out = poll_land(rpc, sig.clone(), sig_bytes, send_slot, land_timeout, watch, last_valid).await;
        out.roles = roles;
        out.tips = meta.tips; // L9-3: the slow path's buy tips (fees paid)
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
    if is_buy { fire_note_raise(ixs, &meta); }
    let mut out = poll_land(rpc, sig, sig_bytes, send_slot, land_timeout, watch, last_valid).await;
    out.roles = roles;
    out.tips = meta.tips; // L9-3
    if is_buy { jito_results(&fan, &meta); }
    Ok(out)
}

/// L8-4: the slow path's FIRE message, after its send (the mint is the pump buy's account 1)
fn fire_note_raise(ixs: &[build::Ix], meta: &lat::Meta) {
    let Some(mint) = ixs.iter().find(|ix| ix.program == *snipe::PUMP).and_then(|ix| ix.accounts.get(1)).map(|a| a.key) else { return };
    let Some((cs, dev, bundle)) = FIRE_NOTES.lock().unwrap().remove(&mint) else { return };
    let prio = arg_u64("--cu-limit", 120_000).saturating_mul(arg_u64("--cu-price-micro", 3_000_000)).div_ceil(1_000_000);
    tg::raise(arbx::alerts::Level::Info, "snipe_fire", &b58(&mint), "🎯", "FIRE (slow path)", tg::fire_body(&mint, cs, dev, bundle, &meta.client, &meta.route, prio, meta.tips, buy_deadline(Some(cs))), false);
}

/// L9: one buy's fee breakdown (priority = CU limit x CU price of its compute-budget ixs, tips, 5000 base)
fn fee_line(ixs: &[build::Ix], tips: u64) -> String {
    let (mut cu, mut price) = (200_000u64, 0u64);
    for ix in ixs {
        if ix.program == arbx::tx::COMPUTE_BUDGET && ix.data.len() == 5 && ix.data[0] == 2 { cu = u32::from_le_bytes(ix.data[1..5].try_into().unwrap()) as u64; }
        if ix.program == arbx::tx::COMPUTE_BUDGET && ix.data.len() == 9 && ix.data[0] == 3 { price = u64::from_le_bytes(ix.data[1..9].try_into().unwrap()); }
    }
    fee_str(cu, price, tips)
}
fn fee_str(cu: u64, price: u64, tips: u64) -> String {
    let prio = (cu as u128 * price as u128).div_ceil(1_000_000) as u64;
    format!("fee_prio={prio} (cu {cu} x {price} uL) tips={tips} base=5000 fee_total={} lamports ({:.6} SOL)", prio + tips + 5000, (prio + tips + 5000) as f64 / 1e9)
}

/// poll getSignatureStatuses (and, M3, the token account of `watch` in the same round, concurrently) until the tx lands
/// or `land_timeout`
async fn poll_land(rpc: &rpc::Rpc, sig: String, sig_bytes: [u8; 64], send_slot: u64, land_timeout: Duration, watch: Watch, last_valid: u64) -> Landed {
    let mut out = Landed { sig, send_slot, land_slot: None, ok: false, t_seen: None, via: "", last_valid, err: None, roles: (None, None), tokens: None, t_sent: None, tips: 0 };
    let deadline = Instant::now() + land_timeout;
    // DET: --land-poll-ms (default 300 = unchanged). The buy's land is only noticed at the next poll, so the first
    // sell leg (and the exit clock) starts up to one poll late; 100 ms costs ~10 getSignatureStatuses/s per open send.
    let poll = Duration::from_millis(arg_u64("--land-poll-ms", 300).max(20));
    while Instant::now() < deadline {
        tokio::time::sleep(poll).await;
        if land_check(rpc, &sig_bytes, watch, &mut out).await { break; }
    }
    out
}

/// M3: one land check: signature status + (watch) token account, concurrently. true = landed (`out` filled).
/// N1/N8: each RPC call is capped at RPC_READ_TIMEOUT; the token read is a context-slot read (Tok): an error or a node
/// behind the required slot is Unknown (no landing), never "0".
async fn land_check(rpc: &rpc::Rpc, sig_bytes: &[u8; 64], watch: Watch, out: &mut Landed) -> bool {
    let tk = async { match watch {
        Watch::BuyAta(a) => Some(tok_read(rpc, &a, "processed", 0).await),
        Watch::SellAta(a, _, min) => Some(tok_read(rpc, &a, "processed", min).await),
        Watch::None => None,
    } };
    // H-1 primary then fallback; M-2 the status keeps the on-chain error
    let ss = [bs58::encode(sig_bytes).into_string()];
    let (st, tk) = tokio::join!(call2(rpc, "getSignatureStatuses", serde_json::json!([ss, { "searchTransactionHistory": false }])), tk);
    // L5-2 (audit 5): keep the token amount the buy's account read saw, EVEN when the signature status wins this round
    if let (Watch::BuyAta(_), Some(Tok::Amount(a, _))) = (watch, tk) { if a > 0 { out.tokens = Some(a); } }
    match st {
        Ok(v) => if let Some(x) = v["value"].get(0).filter(|x| !x.is_null()) {
            out.land_slot = Some(x["slot"].as_u64().unwrap_or(0)); out.ok = x["err"].is_null(); out.t_seen = Some(Instant::now()); out.via = "status";
            out.err = if x["err"].is_null() { None } else { Some(x["err"].clone()) };
            return true;
        },
        Err(e) => poll_err("getSignatureStatuses", &e),
    }
    let (landed, ctx) = match (watch, tk) {
        (Watch::BuyAta(_), Some(Tok::Amount(a, c))) => (a > 0, c),
        (Watch::SellAta(_, before, _), Some(Tok::Amount(a, c))) => (a < before, c),
        (Watch::SellAta(..), Some(Tok::Closed(c))) => (true, c),
        _ => (false, 0),
    };
    if landed {
        // the token account moved: our tx landed successfully (a failed tx moves nothing); its slot <= the context slot
        out.land_slot = Some(ctx); out.ok = true; out.t_seen = Some(Instant::now()); out.via = "ata";
    }
    landed
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
    let v = call2(rpc, "getBalance", serde_json::json!([b58(&who), { "commitment": "processed" }])).await.context("getBalance")?;
    v["value"].as_u64().context("getBalance: no value")
}

/// --sell-held: for each mint, rebuild its Launch from the create tx (oldest signature, raw wire bytes -> the same
/// parser as the shred feed), then sell our whole Token-2022 balance via the SELL path and close the ATA (rent back).
async fn run_sell_held(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, list: &str) -> Result<()> {
    for m in list.split(',').map(|x| x.trim()).filter(|x| !x.is_empty()) {
        let mint = pk(m);
        let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
        // N9: an RPC error is UNKNOWN (retried, then logged loudly), never "balance 0"; 0 = a confirmed read of 0 / closed.
        // H-1: every read goes to the primary, then to --rpc-fallback-url-env
        let amount = match tok_read_retry(rpc, &ata, "confirmed", 0, 8).await {
            Tok::Amount(a, _) if a > 0 => a,
            Tok::Unknown => { eprintln!("  SELL-HELD {m}: TOKEN BALANCE UNREADABLE after 8 reads — NOT sold, NOT known to be 0: re-run --sell-held {m}"); continue; }
            t => { eprintln!("  SELL-HELD {m}: confirmed balance 0 ({}) — nothing to sell", t.show()); continue; }
        };
        let (launch, how) = resolve_launch(rpc, &mint).await;
        eprintln!("  SELL-HELD {m}: {amount} tokens; accounts from {how} (bonding curve {}, buyback {})", b58(&launch.bonding_curve), b58(&launch.buyback_fee_recipient));
        // the live exit's loop: confirmed-zero rule, fallback path (M-5), fallback RPC + cached blockhash (H-1), CU bump
        let o = SellOpts { read_first: false, wait: Duration::from_secs(arg_u64("--sell-retry-s", 2).max(1)), deadline: Duration::from_secs(arg_u64("--sell-deadline-s", 60).max(30)), bg: false, t_decision: None };
        let out = sell_until_zero(key, user, rpc, sp(path), &launch, &ata, Some(amount), amount, 0, o).await;
        eprintln!("  SELL-HELD {m}: {} after {} attempt(s)", if out.sold_at.is_some() { "SOLD (confirmed 0)" } else { "NOT SOLD (see UNSOLD above)" }, out.attempts);
    }
    Ok(())
}

/// M-4 (audit 3): a mint's Launch for a sell outside the live flow (--sell-held, the exit sells): the SAME resolution as
/// the live detector — the oldest transaction of the mint (its create), parsed from raw wire bytes, as a top-level
/// create (detect_launch) or else pump's router create (router_launch, CPI). Fallback when neither works: the accounts
/// derived from the mint (sell_v3 needs no creator; DEFAULT_BUYBACK as the buyback recipient). Reads go through call2.
async fn resolve_launch(rpc: &rpc::Rpc, mint: &Pk) -> (Launch, &'static str) {
    let m = b58(mint);
    let derived = || snipe_build::launch_from_target(*mint, *mint);
    let mut before: Option<String> = None;
    let mut oldest: Option<String> = None;
    for _ in 0..40 {
        let mut o = serde_json::json!({ "limit": 1000 });
        if let Some(b) = &before { o["before"] = serde_json::json!(b); }
        let v = match call2(rpc, "getSignaturesForAddress", serde_json::json!([m, o])).await { Ok(v) => v, Err(e) => { eprintln!("  RESOLVE {m}: signatures failed: {}", redact(&format!("{e:#}"))); break; } };
        let arr = v.as_array().cloned().unwrap_or_default();
        if arr.is_empty() { break; }
        let last = arr.last().and_then(|x| x["signature"].as_str()).map(|x| x.to_string());
        oldest = last.clone();
        if arr.len() < 1000 { break; }
        before = last;
    }
    let Some(csig) = oldest else { return (derived(), "derived from the mint (no signatures)") };
    // L4-3: version 1 as the old --sell-held asked (a v1 create stays readable)
    let Ok(t) = call2(rpc, "getTransaction", serde_json::json!([csig, { "encoding": "base64", "maxSupportedTransactionVersion": 1, "commitment": "confirmed" }])).await else { return (derived(), "derived from the mint (create tx unreadable)") };
    let Some(raw) = t["transaction"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok()) else { return (derived(), "derived from the mint (create tx not decodable)") };
    let Some((mut tx, _)) = arbx::tx::parse_wire(&raw) else { return (derived(), "derived from the mint (parse failed)") };
    // lookup-table addresses as the RPC resolved them (a router create may reference the curve through a table)
    let la = &t["meta"]["loadedAddresses"];
    // L4-2 (audit 4): a malformed address is dropped (no panic): the tx then simply does not resolve
    let pk_opt = |s: &str| -> Option<Pk> { bs58::decode(s).into_vec().ok().filter(|v| v.len() == 32).map(|v| { let mut k = [0u8; 32]; k.copy_from_slice(&v); k }) };
    let keys = |k: &str| -> Vec<Pk> { la[k].as_array().map(|a| a.iter().filter_map(|x| x.as_str().and_then(pk_opt)).collect()).unwrap_or_default() };
    if !tx.lookups.is_empty() { tx.loaded = Some((keys("writable"), keys("readonly"))); }
    if let Some(l) = snipe::detect_launch(&tx).filter(|l| l.mint == *mint) { return (l, "its create tx (top-level create)"); }
    if let Some(l) = router_launch(&tx).filter(|l| l.mint == *mint) { return (l, "its create tx (router create)"); }
    (derived(), "derived from the mint (oldest tx is not a create of it)")
}

/// N4: the sells' own CU limit (--sell-cu-limit, default 120,000: the engine's sell tx measured 44-56k CU for SellV3 +
/// the ATA close in simulation, ops/review/REPORT.md section 5; ~2x headroom). A sell that lands FAILED is retried with
/// 1.5x the limit (capped at 400,000), so a ComputeBudgetExceeded sell cannot repeat identically until UNSOLD.
fn sell_cu_limit() -> u32 { arg_u64("--sell-cu-limit", 120_000).clamp(20_000, 1_400_000) as u32 }

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
    round_trip_launch(key, user, rpc, path, &launch, cap_lamports, max_sol, land_timeout, None, None, None).await
}

/// --simulate (ZERO-COST, no --live): build+sign the v3 buy EXACTLY as the live path (WSOL wrap +
/// buy_exact_quote_in_v3) and call simulateTransaction — no send, nothing spent. Resolve the launch from
/// --mint/--creator/--bonding-curve (repeatable on a stable curve), or from the first vanilla launch off the feed when
/// [[feed]] is configured. Vary --spend-lamports to sweep the v3 minimum buy size (where 6020 BuyZeroAmount stops and
/// a real base-token amount appears in the logs).
async fn run_simulate(probe: &Probe, key: &SigningKey, user: Pk, rpc: &Arc<rpc::Rpc>, stop: &Arc<AtomicBool>) -> Result<()> {
    let spend = arg_u64("--spend-lamports", 2_000_000);
    let min_out = arg_u64("--min-tokens-out", 1);
    // L7 (audit 2026-10-20): --sim-as PUBKEY simulates the buy AS another (funded, system-owned) account: sigVerify is off,
    // so no key is needed and nothing is sent; this measures the CU of a full-size buy without funding our wallet.
    let user = match arg_pk("--sim-as") {
        Some(u) => {
            let v = rpc.call("getAccountInfo", serde_json::json!([b58(&u), { "encoding": "base64", "commitment": "processed" }])).await.context("--sim-as: getAccountInfo")?;
            let (lam, owner) = (v["value"]["lamports"].as_u64().unwrap_or(0), v["value"]["owner"].as_str().unwrap_or("-").to_string());
            eprintln!("SIMULATE AS {} (lamports {lam} = {:.3} SOL, owner {owner})", b58(&u), lam as f64 / 1e9);
            if owner != "11111111111111111111111111111111" { bail!("--sim-as {}: not a system-owned account (owner {owner}): it cannot pay a fee", b58(&u)); }
            if lam < spend + 100_000_000 { bail!("--sim-as {}: holds {:.3} SOL < spend + 0.1 SOL: the simulated buy would fail on funds", b58(&u), lam as f64 / 1e9); }
            u
        }
        None => user,
    };
    if let Some(mint) = arg_pk("--mint") {
        let creator = arg_pk("--creator").unwrap_or(mint);
        let mut launch = match arg_pk("--bonding-curve") {
            Some(bc) => Launch { mint, bonding_curve: bc, assoc_bonding_curve: snipe_build::assoc_bonding_curve(&bc, &mint), creator, dev_buy_lamports: 0, is_create_v2: true,
                is_mayhem: false, is_cashback: false, creator_fee_bps: 0, is_holder_reward: false, buyback_fee_recipient: [0u8; 32] },
            None => snipe_build::launch_from_target(mint, creator),
        };
    if let Some(bb) = arg_pk("--buyback") { launch.buyback_fee_recipient = bb; }
        eprintln!("\nSIMULATE buy (ZERO-COST): mint={} spend={} lamports ({:.6} SOL) — no send", b58(&mint), spend, spend as f64 / 1e9);
        if has("--sim-sell") { return simulate_sell(key, rpc, &launch).await.map(|_| ()); }
        return simulate_buy(key, user, rpc, &launch, spend, min_out).await.map(|_| ());
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
            let arbx::feeds::Event::Tx(mut a) = ev else { continue };
        altc::fill(&mut a.tx); // ALT: lookup tables resolved from the cache (fail closed on a miss)
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

    // L7: --sim-count N simulates the first N SOL-quoted create_v2 launches (each --sim-delay-ms after its create, so the RPC
    // has processed it) and prints the CU spread; default 1 (as before)
    let count = arg_u64("--sim-count", 1).max(1);
    let delay = Duration::from_millis(arg_u64("--sim-delay-ms", 1500));
    let mut done = 0u64;
    eprintln!("\nSIMULATE (ZERO-COST): watching for {count} {} launch(es) to simulate a buy on ...", if allow_nonvanilla { "(any)" } else { "VANILLA" });
    let mut seen = MintDedup::new(4096);
    loop {
        if stop.load(Ordering::Relaxed) || done >= count { break; }
        let ev = match arx.recv().await { Some(e) => e, None => bail!("feed closed before a launch was detected") };
        let arbx::feeds::Event::Tx(mut a) = ev else { continue };
        altc::fill(&mut a.tx); // ALT: lookup tables resolved from the cache (fail closed on a miss)
        let Some(launch) = snipe::detect_launch(&a.tx) else { continue };
        if !allow_nonvanilla && !launch.is_snipeable() { continue; }
        if snipe::create_quote_mint(&a.tx).is_some() || !launch.is_create_v2 || !seen.first(launch.mint) { continue; }
        // L-12 (audit 3): --sim-cashback-only: only cashback / holder-reward launches (their sell is otherwise unverified)
        if has("--sim-cashback-only") && !(launch.is_cashback || launch.is_holder_reward) { continue; }
        eprintln!("  DETECTED launch slot={} mint={} dev_buy={} — simulating a {} lamports buy in {} ms", a.slot, b58(&launch.mint), launch.dev_buy_lamports, spend, delay.as_millis());
        tokio::time::sleep(delay).await;
        // N4 --sim-sell: simulate the engine's SELL (as a holder of this fresh token) instead of the buy
        let r = if has("--sim-sell") { simulate_sell(key, rpc, &launch).await } else { simulate_buy(key, user, rpc, &launch, spend, min_out).await };
        match r { Ok(true) => done += 1, Ok(false) => {}, Err(e) => eprintln!("  simulate failed: {e:#}") }
    }
    Ok(())
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
/// N4 (re-audit): ZERO-COST SELL CU check. Simulates the engine's own sell tx (sell_message_ixs: --sell-cu-limit,
/// --sell-cu-price-micro, sell_v3 of the whole balance + close of the base ATA, exactly as sell_until_zero sends it) AS a
/// wallet that holds this fresh pump token: among the 20 largest token accounts (getTokenLargestAccounts), not the bonding
/// curve's, the first whose owner is a system-owned wallet with >= 0.01 SOL, whose token account IS its Token-2022 ATA,
/// and which (like our wallet after its buy) has a WSOL ATA and a pump user volume accumulator. sigVerify off and
/// replaceRecentBlockhash: nothing is signed by that wallet, nothing is sent. Ok(true): simulated; Ok(false): no holder fit.
async fn simulate_sell(key: &SigningKey, rpc: &rpc::Rpc, launch: &Launch) -> Result<bool> {
    let mint = launch.mint;
    let curve_ata = snipe_build::assoc_bonding_curve(&launch.bonding_curve, &mint);
    let v = rpc.call("getTokenLargestAccounts", serde_json::json!([b58(&mint), { "commitment": "confirmed" }])).await.context("getTokenLargestAccounts")?;
    let list = v["value"].as_array().cloned().unwrap_or_default();
    let mut why: Vec<String> = Vec::new();
    for e in list.iter().take(20) {
        let Some(addr) = e["address"].as_str() else { continue };
        let acc = pk(addr);
        if acc == curve_ata { continue; } // the bonding curve's own reserve
        let amount = e["amount"].as_str().and_then(|x| x.parse::<u64>().ok()).unwrap_or(0);
        if amount == 0 { continue; }
        let ai = rpc.call("getAccountInfo", serde_json::json!([addr, { "encoding": "jsonParsed", "commitment": "confirmed" }])).await?;
        let Some(owner) = ai["value"]["data"]["parsed"]["info"]["owner"].as_str().map(pk) else { why.push(format!("{}: not parsed", &addr[..6])); continue };
        if snipe_build::assoc_user(&owner, &mint) != acc { why.push(format!("{}: not the owner's T22 ATA", &addr[..6])); continue; }
        let keys: Vec<String> = [owner, snipe_build::assoc_quote(&owner), snipe_build::user_volume_accumulator(&owner)].iter().map(b58).collect();
        let m = rpc.call("getMultipleAccounts", serde_json::json!([keys, { "encoding": "base64", "dataSlice": { "offset": 0, "length": 0 }, "commitment": "confirmed" }])).await?;
        let vals = m["value"].as_array().cloned().unwrap_or_default();
        if vals.len() != 3 { continue; }
        let (lam, sys) = (vals[0]["lamports"].as_u64().unwrap_or(0), vals[0]["owner"].as_str() == Some("11111111111111111111111111111111"));
        if !sys || lam < 10_000_000 { why.push(format!("{}: owner not a funded system wallet", &addr[..6])); continue; }
        if vals[1].is_null() || vals[2].is_null() { why.push(format!("{}: no WSOL ATA / volume accumulator", &addr[..6])); continue; }
        let cu = sell_cu_limit();
        let price = arg_u64("--sell-cu-price-micro", 5_000_000);
        let ixs = snipe_build::sell_message_ixs(owner, launch, amount, 0, cu, price, has("--wrap"));
        let bh = rpc.latest_blockhash().await.map(|x| x.0).unwrap_or([0u8; 32]); // replaced by replaceRecentBlockhash
        let msg = build::compile_v0(owner, &ixs, bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
        let raw = build::sign(&msg, key); // not the holder's signature: sigVerify is off
        let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
        let opts = serde_json::json!({ "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "confirmed" });
        let r = rpc.call("simulateTransaction", serde_json::json!([b64, opts])).await.context("simulateTransaction")?;
        let val = &r["value"];
        println!("\n========== SIMULATE SELL RESULT ==========");
        println!("mint             {}", b58(&mint));
        println!("as holder        {} (token account {}, {} tokens, {:.3} SOL)", b58(&owner), addr, amount, lam as f64 / 1e9);
        println!("launch kind      cashback={} holder_reward={} mayhem={}", launch.is_cashback, launch.is_holder_reward, launch.is_mayhem);
        println!("err              {}", val["err"]);
        println!("unitsConsumed    {}", val["unitsConsumed"]);
        if let Some(u) = val["unitsConsumed"].as_u64() {
            let pctu = 100.0 * u as f64 / cu as f64;
            println!("SELL-CU-CHECK    {u} of the sell CU limit {cu} ({pctu:.1}%): {}",
                if val["err"].to_string().contains("ComputeBudgetExceeded") || val["err"].to_string().contains("exceeded CUs") { "FAIL: ComputeBudgetExceeded — raise --sell-cu-limit" }
                else if !val["err"].is_null() { "ERROR (see logs: not a CU result)" }
                else if pctu > 90.0 { "WARN: < 10% headroom — raise --sell-cu-limit" } else { "OK" });
        }
        if !val["err"].is_null() { if let Some(logs) = val["logs"].as_array() { for l in logs.iter().rev().take(12).rev() { if let Some(x) = l.as_str() { println!("  {x}"); } } } }
        println!("==========================================");
        return Ok(true);
    }
    eprintln!("  SELL-SIMULATE {}: no suitable holder among the {} largest accounts ({}) — next launch", b58(&mint), list.len().min(20), why.join("; "));
    Ok(false)
}

async fn simulate_buy(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, launch: &Launch, spend: u64, min_out: u64) -> Result<bool> {
    let plan = BuyPlan {
        spend_lamports: spend, min_tokens_out: min_out, cu_limit: arg_u64("--cu-limit", 120_000) as u32,
        cu_price_micro: arg_u64("--cu-price-micro", 3_000_000), create_ata: true, track_volume: false, nonce: None,
        wrap: has("--wrap"),
    };
    let mut ixs = snipe_build::buy_message_ixs(user, launch, &plan);
    // L7 --sim-tips a,b,..: the route's tip transfers (lamports), first, exactly as the live fan-out tx (System transfers,
    // here to the payer itself: same CU), with the same CU-limit bump (+300 per tip beyond 2)
    let tips: Vec<u64> = arg("--sim-tips").map(|t| t.split(',').filter_map(|x| x.trim().parse().ok()).collect()).unwrap_or_default();
    if !tips.is_empty() {
        let mut v: Vec<build::Ix> = tips.iter().map(|l| build::transfer_ix(user, user, *l)).collect();
        v.extend(ixs);
        if tips.len() > 2 { lat::bump_cu_limit(&mut v, 300 * (tips.len() as u32 - 2)); }
        ixs = v;
    }
    // M-3: with --buy-max-slot-delta the buy carries the on-chain slot guard, exactly as live (deadline = now + 100 here,
    // so it passes: the CU of the guard is what this checks)
    let guarded = SLOT_GUARD.get().is_some();
    if guarded { let s = rpc.slot().await.unwrap_or(0); ixs = with_guard(ixs, Some(s + 100)); }
    let cu_limit = ixs.iter().find(|ix| ix.program == arbx::tx::COMPUTE_BUDGET && ix.data.len() == 5 && ix.data[0] == 2).map(|ix| u32::from_le_bytes(ix.data[1..5].try_into().unwrap())).unwrap_or(200_000);
    let bh = rpc.latest_blockhash().await.map(|x| x.0).unwrap_or([0u8; 32]); // replaced by replaceRecentBlockhash anyway
    let msg = build::compile_v0(user, &ixs, bh, &[], &[]).map_err(|e| anyhow::anyhow!(e))?;
    let raw = build::sign(&msg, key);
    let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
    let opts = serde_json::json!({ "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed" });
    let v = rpc.call("simulateTransaction", serde_json::json!([b64, opts])).await.context("simulateTransaction")?;
    let val = &v["value"];
    println!("\n========== SIMULATE BUY RESULT ==========");
    println!("tx bytes         {} (limit 1232){}", raw.len(), if guarded { " incl. the slot guard" } else { "" });
    println!("mint             {}", b58(&launch.mint));
    println!("spend_lamports   {} ({:.6} SOL)", spend, spend as f64 / 1e9);
    println!("err              {}", val["err"]);
    println!("unitsConsumed    {}", val["unitsConsumed"]);
    if let Some(u) = val["unitsConsumed"].as_u64() {
        let pctu = 100.0 * u as f64 / cu_limit.max(1) as f64;
        println!("CU-CHECK         {u} of the CU limit {cu_limit} ({pctu:.1}%) with {} tip transfer(s){}: {}", tips.len(), if guarded { " + the M-3 slot guard" } else { "" },
            if !val["err"].is_null() && val["err"].to_string().contains("ComputeBudgetExceeded") { "FAIL: ComputeBudgetExceeded — raise --cu-limit" }
            else if pctu > 90.0 { "WARN: < 10% headroom — raise --cu-limit" } else { "OK" });
    }
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
    println!("NOTE: the SELL is simulated with --sim-sell (as a holder of a fresh token: ops/run1/cu_check.sh).");
    println!("=========================================");
    Ok(true)
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
        let arbx::feeds::Event::Tx(mut a) = ev else { continue };
        altc::fill(&mut a.tx); // ALT: lookup tables resolved from the cache (fail closed on a miss)
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
        return round_trip_launch(key, user, rpc, path, &launch, cap_lamports, max_sol, land_timeout, Some(a.slot), None, None).await;
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
    seen: std::collections::HashSet<u64>, seen_q: std::collections::VecDeque<u64>,
    /// M5: sig8 of pump buys whose mint sits in an unresolved lookup table (may be a leg of a watched run: UNKNOWN)
    alt_unres: std::collections::HashSet<u64>, alt_q: std::collections::VecDeque<u64> }

/// one launch the race gate passed: (launch, create slot, M1: the curve's virtual SOL after the dev buy + the glued
/// creator bundle when that total is known (glued run closed, every leg simulated), else None)
type Ready = (Launch, u64, Option<u64>);

fn sig8_of(sig: &[u8; 64]) -> u64 { u64::from_be_bytes(sig[..8].try_into().unwrap()) }

impl RaceWatch {
    fn new(cfg: RaceCfg) -> Self {
        if cfg.glued { arbx::feeds::ORDER_ON.store(true, Ordering::Relaxed); }
        RaceWatch { cfg, pend: Default::default(), shadow: Vec::new(), defer: None, seen: Default::default(), seen_q: Default::default(),
            alt_unres: Default::default(), alt_q: Default::default() }
    }
    /// L5: --race-early decides before the window ends only when nothing can still change the verdict; with --race-glued
    /// (decided when the glued run closes) or a bundle-SOL maximum / an outsider count / --race-bundle no it never applies
    fn early_note(&self) -> Option<&'static str> {
        if !self.cfg.early { return None; }
        if self.cfg.glued { return Some("INACTIVE with --race-glued (the glued run decides when it closes; a later leg can still push the bundle over --race-max-bundle-sol)"); }
        if self.cfg.max_bundle_sol < 1_000_000_000_000_000_000 { return Some("INACTIVE with --race-max-bundle-sol (a later bundle leg can still exceed the maximum)"); }
        if self.cfg.count_out || self.cfg.bundle == -1 { return Some("INACTIVE with --race-window-ms / --race-bundle no"); }
        None
    }
    /// GAP: note every forwarded tx (all feeds; duplicates are harmless)
    fn note_hit(&mut self, tx: &arbx::tx::Tx) {
        if !self.cfg.glued { return; }
        let k = sig8_of(&tx.sig);
        if self.seen.insert(k) { self.seen_q.push_back(k); if self.seen_q.len() > 400_000 { if let Some(o) = self.seen_q.pop_front() { self.seen.remove(&o); } } }
        if snipe::pump_buy_mint_unresolved(tx) && self.alt_unres.insert(k) {
            self.alt_q.push_back(k);
            if self.alt_q.len() > 100_000 { if let Some(o) = self.alt_q.pop_front() { self.alt_unres.remove(&o); } }
        }
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
        // M5: a router (CPI) create has no top-level dev buy leg: its curve starts at 30 SOL + the dev buy (it read 30 SOL,
        // so the bundle legs were priced ~10% low at dev 2)
        let vq_create = match snipe::bundle_legs(tx, &launch.mint) {
            Some(snipe::Legs::Buys(v)) => snipe::CURVE_VQ0 + snipe::simulate_legs(snipe::CURVE_VQ0, &v).unwrap_or(launch.dev_buy_lamports),
            _ => snipe::CURVE_VQ0 + launch.dev_buy_lamports,
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
        let mut hits: Vec<Pk> = tx.keys.iter().filter(|k| self.pend.contains_key(*k)).copied().collect();
        // M5: a mint behind a lookup table the feed resolved (Yellowstone deshred) is a hit too
        if let Some((w, r)) = &tx.loaded { hits.extend(w.iter().chain(r.iter()).filter(|k| self.pend.contains_key(*k) && !hits.contains(*k)).copied().collect::<Vec<_>>()); }
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
    fn due(&mut self) -> Vec<Ready> {
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
                                    // M5: a pump buy whose mint is behind an unresolved lookup table: an UNKNOWN leg (reject),
                                    // not "a pump tx of another mint" (that closed the run early and passed a short bundle)
                                    None if self.alt_unres.contains(&k) => { n += 1; unk += 1; }
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
                    if p.pass { ready.push((p.launch.clone(), p.slot, Some(p.vq_create.saturating_add(gsol)))); }
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
                if p.pass { ready.push((p.launch.clone(), p.slot, None)); }
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
        if let Some(arbx::feeds::Event::Tx(mut a)) = ev {
            altc::set_watching(!race.pend.is_empty()); // M5-1: unresolved pump buys are fetched only while a launch is watched
            altc::fill(&mut a.tx); // ALT: lookup tables resolved from the cache (fail closed on a miss)
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
        if race.cfg.active() { ready.extend(race.due().into_iter().map(|(l, s, _)| (l, s))); }
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
/// own round-trip (buy with fill-cap + exit), bounded by --max-inflight. Hard-bounded by: --max-sol (per-buy cap),
/// --max-total-sol (budget on LANDED buys: actual cost incl. fees), --max-buys (landed buys), a pre-fire balance check
/// and an in-engine kill switch (--max-loss-sol: balance + open positions at cost, and realized PnL) with the
/// --lock-tiers profit lock. Runs for --minutes, or until a signal / the kill switch / the lock / a cap stops new fires;
/// the open positions then finish their exit (drain) and any mint still held is logged HELD-AT-EXIT.
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
    // L4: --max-buys N: stop after N LANDED buys (0 = off)
    let max_buys = arg_u64("--max-buys", 0);
    // M1: --slip-cap-bps B: min_tokens_out = (1 - B/10000) x quote(curve after dev + glued bundle, our spend net of the pump fee)
    let slip_bps = arg_u64_opt("--slip-cap-bps");
    // L3: the balance a fire needs on top of its spend + fees
    let bal_margin = (arg_f64("--min-balance-margin-sol", 0.05) * 1e9) as u64;
    // L9 / budget: fee of a buy before its route is known (non-fast path; the fast path knows its tips at prepare)
    let (cu_limit, cu_price) = (arg_u64("--cu-limit", 120_000), arg_u64("--cu-price-micro", 3_000_000));
    let prio_fee = (cu_limit as u128 * cu_price as u128).div_ceil(1_000_000) as u64;
    let fee_guess = prio_fee + 5000 + arg_u64("--tip-budget-lamports", 15_000_000);

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
    // M1: min_tokens_out for a launch: --min-tokens-out, else the slip cap on the post-bundle curve (bundle total known),
    // else the --fill-cap fallback on the dev-only floor. Never fails open (>= 1, a computed floor).
    let min_out_for = |launch: &Launch, vq_after: Option<u64>| -> (u64, &'static str) {
        if let Some(m) = min_out_fixed { return (m, "fixed"); }
        if let (Some(bps), Some(vq)) = (slip_bps, vq_after) {
            let m = slip_min_out(vq, spend_per, bps);
            if m > 1 { return (m, "slip-cap"); }
        }
        let floor_px = pump_floor_px(launch.dev_buy_lamports);
        ((if floor_px > 0.0 { (spend_per as f64 / (fill_cap_v.unwrap_or(2.5) * floor_px)).floor() as u64 } else { 1 }).max(1), "fill-cap")
    };
    if let Some(b) = slip_bps { eprintln!("SLIP-CAP: min_tokens_out = {:.1}% of the post-bundle quote when the glued bundle total is known; else --fill-cap {} on the dev-only floor", 100.0 - b as f64 / 100.0, fill_cap_v.map(|x| x.to_string()).unwrap_or_else(|| "2.5 (default)".into())); }
    let mut preps: std::collections::HashMap<Pk, fastfire::Prep> = std::collections::HashMap::new();
    let mut ev_st = [0u64; 4];

    let key = Arc::new(key.clone());
    let sem = Arc::new(tokio::sync::Semaphore::new(max_inflight));
    let fired = Arc::new(std::sync::atomic::AtomicU64::new(0));
    // --lock-tiers "ARM:FLOOR,..." (SOL, run PnL): once run PnL >= ARM, stop new fires if PnL falls below FLOOR
    // (e.g. "0.3:0,0.6:0.3" = break-even lock after +0.3, lock +0.3 after +0.6). Open positions finish their exit.
    // C1: evaluated only with NO position in flight (fire .. exit done); deferred otherwise. (Format checked at start.)
    let lock_tiers: Vec<(i64, i64)> = arg("--lock-tiers").map(|t| t.split(',').filter_map(|kv| {
        let (a, f) = kv.split_once(':')?; Some(((a.trim().parse::<f64>().ok()? * 1e9) as i64, (f.trim().parse::<f64>().ok()? * 1e9) as i64)) }).collect()).unwrap_or_default();
    if !lock_tiers.is_empty() { eprintln!("PROFIT-LOCK tiers (arm:floor SOL): {} (evaluated only with no position in flight)", lock_tiers.iter().map(|(a, f)| format!("{}:{}", *a as f64 / 1e9, *f as f64 / 1e9)).collect::<Vec<_>>().join(",")); }
    let start_bal = match native_balance(rpc, user).await {
        Ok(b) => b,
        // FIX2 --strict-balance: without a start balance the kill-switch could never trip (review finding 4)
        Err(e) if has("--strict-balance") => bail!("--strict-balance: the start balance could not be read ({e:#}): the kill-switch needs it"),
        Err(_) => 0,
    };
    ACCT.bal.store(start_bal, Ordering::SeqCst);
    if has("--strict-balance") { eprintln!("START BALANCE {} lamports ({:.9} SOL); kill-switch trips below {:.9} SOL", start_bal, start_bal as f64 / 1e9, start_bal.saturating_sub(loss_cap) as f64 / 1e9); }
    let deadline = Instant::now() + Duration::from_secs(minutes * 60);

    // In-engine kill switch (M7: every 2 s). PnL = balance + open positions at cost (C1: from landing to sold) - start.
    // Stops new fires on: PnL < -max_loss (confirmed on 2 polls while a buy is unresolved), realized PnL < -max_loss,
    // the profit lock, or 3 consecutive getBalance failures (blind).
    {
        let (rpc2, user2, stop2, tiers) = (rpc.clone(), user, stop.clone(), lock_tiers.clone());
        let cap = loss_cap as i64;
        tokio::spawn(async move {
            let mut st = KsState::default();
            let mut fails = 0u32;
            let mut alpen_warned = false;
            loop {
                tokio::time::sleep(Duration::from_secs(2)).await;
                // L-7 (audit 3): a run that STRADDLES Alpenglow (2026-10-21 14:50 UTC) is warned when it crosses, not only at start
                if !alpen_warned && std::time::SystemTime::now().duration_since(std::time::UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0) >= 1_792_594_200 {
                    alpen_warned = true;
                    eprintln!("  WARNING: Alpenglow time reached DURING the run (2026-10-21 14:50 UTC): slot timing may change — --max-create-ms, --hold-ms 450 (= 3 slots at 217 ms) and the sim were measured before it. Consider stopping the run.");
                }
                if stop2.load(Ordering::Relaxed) { break; }
                // L3: landings from here on may or may not be in this read: count them against the balance until the next read
                let since = ACCT.landed_since_bal.swap(0, Ordering::SeqCst);
                // N2: snapshot the accounting BEFORE the read, ask a node at least as far as every landing / sale the
                // engine acted on (minContextSlot), and skip the evaluation when a position changed during the read
                let a = &*ACCT;
                let seq0 = a.seq.load(Ordering::SeqCst);
                let (open, pending, inflight, realized) = (a.open.load(Ordering::SeqCst), a.pending.load(Ordering::SeqCst), a.inflight.load(Ordering::SeqCst), a.realized.load(Ordering::SeqCst));
                let r = native_balance_at(&rpc2, user2, a.last_slot.load(Ordering::SeqCst)).await;
                if r.is_err() { ACCT.landed_since_bal.fetch_add(since, Ordering::SeqCst); }
                match r {
                    Ok(b) => {
                        fails = 0;
                        ACCT.bal.store(b, Ordering::SeqCst);
                        if a.seq.load(Ordering::SeqCst) != seq0 { eprintln!("  KILL-SWITCH poll not evaluated: a position changed during the balance read (next poll in 2 s)"); continue; }
                        let pnl = (b + open) as i64 - start_bal as i64;
                        let (v, lines) = ks_eval(&mut st, pnl, realized, pending, inflight, cap, &tiers);
                        for l in lines {
                            if l.contains("PROFIT-LOCK armed") { tg::raise(arbx::alerts::Level::Warning, "snipe_lock_armed", &l.chars().take(60).collect::<String>(), "🔒", "Profit lock ARMED", arbx::alerts::format::Body::new().txt(&l), false); }
                            eprintln!("  {l}");
                        }
                        let why = match v {
                            KsVerdict::Go => continue,
                            KsVerdict::Kill => format!("KILL-SWITCH: run PnL {:.6} SOL (balance {:.6} + open {:.6}) below -{:.6}", pnl as f64 / 1e9, b as f64 / 1e9, open as f64 / 1e9, cap as f64 / 1e9),
                            KsVerdict::KillRealized => format!("KILL-SWITCH (realized): in-engine realized PnL {:.6} SOL below -{:.6}", realized as f64 / 1e9, cap as f64 / 1e9),
                            KsVerdict::Lock => format!("PROFIT-LOCK: run PnL {:.6} SOL fell below floor {:.6}", pnl as f64 / 1e9, st.floor.unwrap_or(0) as f64 / 1e9),
                        };
                        eprintln!("  {why} — stopping new fires (open positions finish their exit).");
                        tg::raise(arbx::alerts::Level::Critical, "snipe_kill", "kill", if why.starts_with("PROFIT-LOCK") { "🔒" } else { "🛑" }, &why, arbx::alerts::format::Body::new().txt("NO NEW FIRES; open positions finish their exit"), false);
                        // L-1 (audit 3): the -max-loss cap stops NEW fires; positions already open are still exposed. Log them
                        // with the worst case (each one going to 0) so the gap is explicit.
                        let open_list: Vec<(Pk, u64)> = ACCT.open_pos.lock().unwrap().iter().map(|(k, v)| (*k, *v)).collect();
                        let worst: u64 = open_list.iter().map(|x| x.1).sum();
                        eprintln!("  OPEN AT STOP: {} position(s), {:.6} SOL at cost: {} — worst case (all to 0): run PnL {:.6} SOL (the cap stops new fires, not these)",
                            open_list.len(), worst as f64 / 1e9, open_list.iter().map(|(m, c)| format!("{}={:.4}", &b58(m)[..8], *c as f64 / 1e9)).collect::<Vec<_>>().join(" "),
                            (pnl - worst as i64) as f64 / 1e9);
                        tg::raise(arbx::alerts::Level::Critical, "snipe_open_at_stop", "open_at_stop", "📉", &format!("Open at stop: {} position(s)", open_list.len()),
                            arbx::alerts::format::Body::new().kv("at cost", sol_str(worst as i64)).kv("worst case run PnL", sol_str(pnl - worst as i64)).txt("the cap stops new fires, not these"), false);
                        stop2.store(true, Ordering::SeqCst);
                        break;
                    }
                    Err(e) => {
                        fails += 1;
                        eprintln!("  KILL-SWITCH getBalance failed ({fails}/3): {}", format!("{e:#}").chars().take(120).collect::<String>());
                        if fails >= 3 {
                            eprintln!("  KILL-SWITCH BLIND: 3 consecutive getBalance failures — stopping new fires (open positions finish their exit).");
                            stop2.store(true, Ordering::SeqCst);
                            break;
                        }
                    }
                }
            }
        });
    }

    // --close-leaders <file>: LEADER-PROXIMITY GATE. Fire only when the create slot's leader is network-close to us
    // (pubkey set from pinging the cluster). M2 (audit 2026-10-20): the slot -> leader map is the leader book (current +
    // next epoch, refreshed every 10 min); an UNKNOWN leader counts as far (skip, counted); the run refuses to start when
    // the set is empty / unreadable or the current slot is not mapped.
    let close_set: Option<std::collections::HashSet<String>> = match arg("--close-leaders") {
        None => None,
        Some(p) => {
            let set: std::collections::HashSet<String> = std::fs::read_to_string(&p).with_context(|| format!("--close-leaders {p}"))?
                .lines().map(|s| s.trim().to_string()).filter(|s| !s.is_empty()).collect();
            if set.is_empty() { bail!("--close-leaders {p}: no leaders in the file"); }
            let cur = rpc.slot().await.context("--close-leaders: getSlot")?;
            match lat::leader_of(cur) {
                Some((l, _)) => eprintln!("CLOSE-LEADER GATE ON: {} close leaders; current slot {cur} mapped (leader {}…, close={}); unknown leaders are skipped", set.len(), &l[..8.min(l.len())], set.contains(&l)),
                None => bail!("--close-leaders: the current slot {cur} is not in the leader book (refusing to start: every launch would be skipped)"),
            }
            Some(set)
        }
    };
    let (mut skipped_far, mut skipped_unknown_leader, mut skipped_inflight, mut skipped_balance, mut skipped_budget, mut skipped_maxbuys) = (0u64, 0u64, 0u64, 0u64, 0u64, 0u64);
    let mut rx_t: std::collections::HashMap<Pk, u64> = std::collections::HashMap::new();
    let uri_whitelist = has("--uri-whitelist");
    let uri_blacklist = has("--uri-blacklist");
    let mut skipped_host = 0u64;
    let mut dedup = MintDedup::new(20000); // cross-feed de-dup (erpc + Kaldera): never double-buy a mint seen on both feeds
    let mut det = DetLog::new(_feeds.names.clone());
    set_slot_clock(rpc).await;
    let mut gate = LandGate::new();
    if gate.on() { eprintln!("{}", gate.describe()); }

    eprintln!("\nSNIPE-LIVE (CONCURRENT): dev_buy>={min_dev_buy}, per-buy cap {max_sol} SOL, budget {max_total} SOL on landed buys, max buys {}, loss kill-switch {max_loss} SOL, max_inflight {max_inflight}, {minutes}min. Fires every qualifying launch in parallel.",
        if max_buys > 0 { max_buys.to_string() } else { "off".into() });
    // Telegram: the run's start (the startup checks passed to get here: genesis, SLOT-GUARD, ALT preload, close leaders)
    {
        let build = tg::build_id();
        let checks = vec![
            ("RPC genesis".to_string(), format!("primary mainnet ✓, fallback {}", if RPC_FB.get().is_some() { "mainnet ✓" } else { "none" })),
            ("SLOT-GUARD".to_string(), SLOT_GUARD.get().map(|(g, n)| format!("verified on chain (disc {} op {}), deadline create + {n}", g.disc, g.op)).unwrap_or_else(|| "off".into())),
            ("ALT cache".to_string(), format!("{} table(s) preloaded", altc::len())),
            ("close leaders".to_string(), close_set.as_ref().map(|c| format!("{} leaders", c.len())).unwrap_or_else(|| "off".into())),
            ("start balance".to_string(), sol_str(start_bal as i64)),
            ("mode".to_string(), if junk { "DRY (junk fan-out, nothing can land)".into() } else { "LIVE".into() }),
        ];
        let st = tg::Start { wallet: user, build, size: spend_per, fee_est: fee_guess, max_buys, budget_sol: max_total, run_stop_sol: max_loss,
            lock_tiers: lock_tiers.iter().map(|(a, f)| format!("{}:{}", *a as f64 / 1e9, *f as f64 / 1e9)).collect::<Vec<_>>().join(","), minutes, checks };
        tg::raise(arbx::alerts::Level::Info, "snipe_start", "start", "🚀", &format!("RUN START ({})", if junk { "dry" } else { "live" }), tg::start_body(&st), false);
        // heartbeat every --telegram-heartbeat-min (default 30) while the run lasts
        let every = Duration::from_secs(arg_u64("--telegram-heartbeat-min", 30).max(1) * 60);
        tokio::spawn(async move {
            let mut last_txs = tg::FEED_TXS.load(Ordering::Relaxed);
            loop {
                tokio::time::sleep(every).await;
                if INFRA_STOP.load(Ordering::Relaxed) { break; }
                let txs = tg::FEED_TXS.load(Ordering::Relaxed);
                let open: Vec<u64> = ACCT.open_pos.lock().unwrap().values().copied().collect();
                tg::raise(arbx::alerts::Level::Info, "snipe_heartbeat", "heartbeat", "💓", "Heartbeat", arbx::alerts::format::Body::new()
                    .kv("run PnL (realized)", arbx::alerts::format::sol_signed(ACCT.realized.load(Ordering::SeqCst))).kv("trades", ACCT.landed_buys.load(Ordering::SeqCst).to_string()).nl()
                    .kv("open", format!("{} ({})", open.len(), sol_str(open.iter().sum::<u64>() as i64))).kv("fires paused", FIRE_PAUSE.load(Ordering::SeqCst).to_string()).nl()
                    .kv("feed txs", format!("{} in {} min", txs.saturating_sub(last_txs), every.as_secs() / 60)).kv("slot", send::tpu::SLOT.load(Ordering::Relaxed).to_string())
                    .kv("ALT hits/misses", format!("{}/{}", altc::HITS.load(Ordering::Relaxed), altc::MISSES.load(Ordering::Relaxed))), false);
                last_txs = txs;
            }
        });
    }

    // RACE GATE (default off): same watch as the paper loop. With no race flag the launch goes straight to `ready` and is
    // fired in the same iteration, exactly as before.
    let mut race = RaceWatch::new(RaceCfg::from_args());
    if race.cfg.active() || race.cfg.dev_from_cap { eprintln!("RACE: {}", race.cfg.describe()); }
    if let Some(n) = race.early_note() { eprintln!("RACE-EARLY: {n}"); }
    if slip_bps.is_some() && !race.cfg.glued { eprintln!("SLIP-CAP: the bundle total is known only with --race-glued: every fire uses the --fill-cap fallback"); }
    if fast.is_some() { race.defer = Some(Vec::new()); det.defer = true; }
    let mut ready: Vec<Ready> = Vec::new();
    loop {
        if Instant::now() >= deadline || stop.load(Ordering::Relaxed) { break; }
        // L4: the budget counts LANDED buys (actual cost incl. fees); a full budget / --max-buys ends the fires
        if ACCT.budget_used.load(Ordering::SeqCst) + spend_per + fee_guess.min(prio_fee + 5000) > total_cap { eprintln!("  TOTAL budget reached ({:.6} SOL landed) — no more fires.", ACCT.budget_used.load(Ordering::SeqCst) as f64 / 1e9); break; }
        if max_buys > 0 && ACCT.landed_buys.load(Ordering::SeqCst) >= max_buys { eprintln!("  MAX-BUYS {max_buys} landed — no more fires."); break; }
        let wait = if race.cfg.active() { race.next_wait() } else { Duration::from_secs(2) };
        let ev = if busy {
            match fastfire::spin_recv(&rx, wait) { Ok(e) => e, Err(()) => break }
        } else {
            match tokio::time::timeout(wait, arx.recv()).await { Ok(Some(e)) => Some(e), Ok(None) => break, Err(_) => None }
        };
        let (t_deq, t_deq_real) = (arbx::fast::mono_ns(), arbx::feeds::clock::now_ns());
        if let Some(arbx::feeds::Event::Tx(a)) = &ev { ev_st = [a.t_rx, a.t_decoded, t_deq_real, t_deq]; tg::FEED_TXS.fetch_add(1, Ordering::Relaxed); }
        det.health(&_feeds);
        if let Some(arbx::feeds::Event::Status { feed, msg }) = &ev { eprintln!("  FEEDSTATUS feed={} {msg}", det.name(*feed)); }
        if let Some(arbx::feeds::Event::Tx(mut a)) = ev {
            altc::set_watching(!race.pend.is_empty()); // M5-1: unresolved pump buys are fetched only while a launch is watched
            altc::fill(&mut a.tx); // ALT: lookup tables resolved from the cache (fail closed on a miss)
            if race.cfg.glued { race.note_hit(&a.tx); }
            // DET FIX: the current slot for leader targeting / send_slot comes from the shred feed (the leader's slot as it
            // is being produced). The 250 ms getSlot poller alone lagged the create slot by 2-3 slots (live_land_fast.log:
            // send_slot 458515365 for a create in 458515368), so tpu-direct aimed at leaders already past.
            slot_note(SLOT_SRC_FEED, a.slot); // M8-1: a jump > 1,000 slots needs a second source
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
                            quote.map(|q| if q == snipe::UNRESOLVED_QUOTE { "unresolved".to_string() } else { b58(&q)[..8].to_string() }).unwrap_or_else(|| "sol".into())));
                    gate.note(&a, &launch.mint);
                    if !first { break 'create; }
                    if !dedup.first(launch.mint) { break 'create; } // same create seen on the other feed -> skip the duplicate
                    // DET FIX: our buy is WSOL-quoted + Token-2022: a non-SOL or legacy-SPL launch would revert (fees lost).
                    // M6: an unresolvable quote account (lookup table) reads as non-SOL (UNRESOLVED_QUOTE) and is skipped too.
                    if quote.is_some() && !det.allow_nonsol { break 'create; }
                    if !launch.is_create_v2 && !det.allow_legacy { break 'create; }
                    if launch.dev_buy_lamports < min_dev_buy { break 'create; }
                    if launch.dev_buy_lamports > max_dev_buy_lam { break 'create; } // whale gate: dev>8 SOL is poison (50% dump)
                    if !allow_nonvanilla && !launch.is_snipeable() { break 'create; }
                    if uri_whitelist && !snipe::trusted_launch_host(&a.tx) { skipped_host += 1; break 'create; }
                    if uri_blacklist && snipe::is_bot_launchpad(&a.tx) { skipped_host += 1; break 'create; }
                    // leader-proximity gate: only fire when the create slot's leader is close. M2: unknown = far (skip, counted)
                    if let Some(cs) = &close_set {
                        match lat::leader_of(a.slot) {
                            Some((l, _)) if cs.contains(&l) => {}
                            Some(_) => { skipped_far += 1; break 'create; }
                            None => { skipped_unknown_leader += 1; break 'create; }
                        }
                    }
                    rx_t.insert(launch.mint, a.t_rx); if rx_t.len() > 4096 { rx_t.clear(); }
                    if let Some(f) = fast {
                        // FAST: everything but the decision, now (the race gate decides on a later tx). min_out here is the
                        // --fill-cap one (the bundle is not known yet); M1 re-signs at the decision with the slip cap.
                        let t_gated = arbx::fast::mono_ns();
                        let (min_out, _) = min_out_for(&launch, None);
                        match f.prepare(&launch, a.slot, min_out, [a.t_rx, a.t_decoded, t_deq_real, t_deq, t_det, t_gated]) {
                            Ok(p) => { preps.insert(launch.mint, p); }
                            Err(e) => eprintln!("  FAST prepare {} failed (re-tried at the fire): {e:#}", b58(&launch.mint)),
                        }
                    }
                    if !race.cfg.active() || race.add(&launch, &a.tx, a.slot) { ready.push((launch, a.slot, None)); }
                }
            }
        }
        if race.cfg.active() { ready.extend(race.due()); race.shadow.clear(); } // shadows are paper-only: never fired live
        let t_dec = arbx::fast::mono_ns();
        for (launch, create_slot, vq_after) in ready.drain(..) {
        // N7: a stop (signal / kill switch / lock) set during this iteration fires nothing more; L6-3: nor a blockhash pause
        if stop.load(Ordering::SeqCst) { eprintln!("  STOP set: launch {} not fired", b58(&launch.mint)); continue; }
        if FIRE_PAUSE.load(Ordering::SeqCst) { eprintln!("  PAUSED (no usable blockhash): launch {} not fired", b58(&launch.mint)); continue; }
        // FIX2 --max-create-ms: a create late in its slot cannot be beaten into that slot (next 50 ms auction tick / batch)
        if !gate.check(&launch.mint, create_slot) { continue; }
        // L4: budget (landed + reserved by unresolved fires) and --max-buys (landed + unresolved), before anything is spent
        let a = &*ACCT;
        if a.budget_used.load(Ordering::SeqCst) + a.reserved.load(Ordering::SeqCst) + spend_per + fee_guess > total_cap {
            skipped_budget += 1; eprintln!("  SKIP-BUDGET slot={create_slot} mint={} (landed {:.6} + reserved {:.6} SOL + this buy > {max_total} SOL)", b58(&launch.mint),
                a.budget_used.load(Ordering::SeqCst) as f64 / 1e9, a.reserved.load(Ordering::SeqCst) as f64 / 1e9); continue;
        }
        if max_buys > 0 && a.landed_buys.load(Ordering::SeqCst) + a.pending.load(Ordering::SeqCst) >= max_buys {
            skipped_maxbuys += 1; eprintln!("  SKIP-MAX-BUYS slot={create_slot} mint={} (landed {} + unresolved {} >= {max_buys})", b58(&launch.mint), a.landed_buys.load(Ordering::SeqCst), a.pending.load(Ordering::SeqCst)); continue;
        }
        if spend_per > cap_lamports { eprintln!("  REFUSED: buy spend {spend_per} lamports exceeds --max-sol cap {cap_lamports} lamports"); continue; }
        // reserve a concurrency slot (never block the detector)
        // DET: a full --max-inflight SKIPS the launch (live): count it, so the backpressure cost is visible
        let permit = match sem.clone().try_acquire_owned() { Ok(p) => p, Err(_) => { skipped_inflight += 1; eprintln!("  SKIP-INFLIGHT slot={create_slot} mint={} (max_inflight {max_inflight} busy)", b58(&launch.mint)); continue } };
        // (hot path: the rx timestamp is looked up here, the age is computed after the writes)
        let t_rx_of = rx_t.get(&launch.mint).copied();
        let (min_out, mo_src) = min_out_for(&launch, vq_after);
        if let Some(f) = fast {
            // FAST: write every path from here, now; logging, verification and (live) the land poll + exit afterwards
            let mut p = match preps.remove(&launch.mint).filter(|p| p.made.elapsed() < Duration::from_secs(2)) {
                Some(p) => p,
                None => match f.prepare(&launch, create_slot, min_out, [0, 0, 0, t_dec, t_dec, t_dec]) { Ok(p) => p, Err(e) => { eprintln!("  FAST prepare failed at the fire (no fire, no budget used): {e:#}"); continue; } },
            };
            // M1: the decision knows the glued bundle: re-sign with the post-bundle min_out (patch 8 bytes + one signature)
            let mo_prep = p.min_out;
            if min_out != p.min_out {
                // never fall back to the looser --fill-cap when the bundle total IS known: no fire (nothing spent)
                if let Err(e) = f.resign(&mut p, min_out) { eprintln!("  M1 re-sign failed ({e}) mint={}: NO FIRE (the prepared min_out {} is the looser --fill-cap)", b58(&launch.mint), p.min_out); continue; }
            }
            // (plain arithmetic on captured values: nothing allocates or reads argv between the decision and the write)
            let cu_eff = if p.tips.len() > 2 { (cu_limit + 300 * (p.tips.len() as u64 - 2)).min(1_400_000) } else { cu_limit };
            let fee = (cu_eff as u128 * cu_price as u128).div_ceil(1_000_000) as u64 + p.meta.tips + 5000;
            // L3: never fire without spend + fees + margin on the wallet (last kill-switch balance minus unresolved buys)
            // (hot path: ACCT.bal is the kill switch's cached balance, refreshed every 2 s off this thread; atomics only.
            // The dry run's "would skip" line is printed AFTER the writes, never between the decision and the write.)
            let avail = a.bal.load(Ordering::SeqCst).saturating_sub(a.pending_spend.load(Ordering::SeqCst) + a.landed_since_bal.load(Ordering::SeqCst));
            let short = avail < spend_per + fee + bal_margin;
            if short && !junk { skipped_balance += 1; eprintln!("  SKIP-BALANCE slot={create_slot} mint={} available {:.6} SOL < spend + fees + margin {:.6}", b58(&launch.mint), avail as f64 / 1e9, (spend_per + fee + bal_margin) as f64 / 1e9); continue; }
            if stop.load(Ordering::SeqCst) || FIRE_PAUSE.load(Ordering::SeqCst) { eprintln!("  STOP / PAUSE set: launch {} not fired", b58(&launch.mint)); continue; } // N7, L6-3
            let rec = f.fire(&p);
            // ---- everything below runs after the writes ----
            let rx_age_us = t_rx_of.map(|t| arbx::feeds::clock::now_ns().saturating_sub(t) / 1000).unwrap_or(0);
            if short { eprintln!("  SKIP-BALANCE (dry: would skip live) mint={} available {:.6} SOL < spend + fees + margin {:.6}", b58(&launch.mint), avail as f64 / 1e9, (spend_per + fee + bal_margin) as f64 / 1e9); }
            // C1: counted pending from the fire (registered right after the writes: it allocates; a landing is >= 100 ms away)
            let pos = if junk { None } else { Some(Pos::new(launch.mint, spend_per, fee, &p.meta.sig)) };
            fired.fetch_add(1, Ordering::Relaxed);
            let ev = ev_st;
            let (key2, rpc2, path2) = (key.clone(), rpc.clone(), path.clone());
            tokio::spawn(async move {
                let _permit = permit;
                eprintln!("  FIRE slot={create_slot} mint={} dev_buy={} rx_to_fire_us={rx_age_us} fast=1 min_out={} min_out_src={mo_src} prep_min_out={mo_prep} vq_after={} resign_us={:.1} {}",
                    b58(&launch.mint), launch.dev_buy_lamports, p.min_out, vq_after.map(|v| v.to_string()).unwrap_or_else(|| "-".into()), p.resign_ns as f64 / 1e3, fee_str(cu_eff, cu_price, p.meta.tips));
                let first = rec.w.iter().filter(|x| x.4 == "written").map(|x| x.3).min().map(|t| t.saturating_sub(t_dec) as f64 / 1e3);
                eprintln!("  FAST-FIRE tag={} slot={create_slot} mint={} deadline={} {} leader={} client={} built={} tips={} bytes={} decide_to_first_write_us={} writes: {}", p.id, b58(&launch.mint),
                    p.deadline.map(|d| d.to_string()).unwrap_or_else(|| "none".into()), p.meta.route, p.meta.leader.chars().take(8).collect::<String>(), p.meta.client, if p.fast_built { "template" } else { "compile" }, p.meta.tips, p.meta.bytes,
                    first.map(|x| format!("{x:.1}")).unwrap_or_else(|| "-".into()),
                    rec.w.iter().map(|x| format!("{}={}@{:.1}us", x.0, x.4, x.3.saturating_sub(t_dec) as f64 / 1e3)).collect::<Vec<_>>().join(" "));
                // Telegram (after the writes, in this spawned task): the fire
                let bundle = vq_after.map(|v| v.saturating_sub(snipe::CURVE_VQ0 + launch.dev_buy_lamports));
                let prio = fee.saturating_sub(p.meta.tips + 5000);
                tg::raise(arbx::alerts::Level::Info, "snipe_fire", &b58(&launch.mint), if junk { "🧪" } else { "🎯" }, if junk { "FIRE (dry: junk only)" } else { "FIRE" },
                    tg::fire_body(&launch.mint, create_slot, launch.dev_buy_lamports, bundle, &p.meta.client, &p.meta.route, prio, p.meta.tips, p.deadline), false);
                f.trace_fire(&p, &rec, ev, t_dec);
                f.trace_prep(&p);
                fix2::spawn_jito_poll(&p.fan, &p.meta.sig, p.id);
                let Some(pos) = pos else { return }; // junk: nothing was sent that can land
                if let Err(e) = round_trip_fast(&key2, user, &rpc2, &path2, &p, cap_lamports, max_sol, land_timeout, fee, pos).await {
                    eprintln!("  position {} ended: {e:#}", b58(&launch.mint));
                }
            });
            continue;
        }
        // the old (non-fast) path: L3 with the fee estimate
        let avail = a.bal.load(Ordering::SeqCst).saturating_sub(a.pending_spend.load(Ordering::SeqCst) + a.landed_since_bal.load(Ordering::SeqCst));
        if !junk && avail < spend_per + fee_guess + bal_margin {
            skipped_balance += 1; eprintln!("  SKIP-BALANCE slot={create_slot} mint={} available {:.6} SOL < spend + fees + margin {:.6}", b58(&launch.mint), avail as f64 / 1e9, (spend_per + fee_guess + bal_margin) as f64 / 1e9); continue;
        }
        if stop.load(Ordering::SeqCst) || FIRE_PAUSE.load(Ordering::SeqCst) { eprintln!("  STOP / PAUSE set: launch {} not fired", b58(&launch.mint)); continue; } // N7, L6-3
        let rx_age_us = t_rx_of.map(|t| arbx::feeds::clock::now_ns().saturating_sub(t) / 1000).unwrap_or(0);
        let pos = if junk { None } else { Some(Pos::new(launch.mint, spend_per, fee_guess, "")) };
        fired.fetch_add(1, Ordering::Relaxed);
        let (key2, rpc2, path2) = (key.clone(), rpc.clone(), path.clone());
        tokio::spawn(async move {
            let _permit = permit;
            eprintln!("  FIRE slot={create_slot} mint={} dev_buy={} rx_to_fire_us={rx_age_us} min_out={min_out} min_out_src={mo_src}", b58(&launch.mint), launch.dev_buy_lamports);
            // L8-4: the slow path's FIRE message is raised AFTER the send (send_and_poll_at reads this note), dry after junk_fire
            FIRE_NOTES.lock().unwrap().insert(launch.mint, (create_slot, launch.dev_buy_lamports, vq_after.map(|v| v.saturating_sub(snipe::CURVE_VQ0 + launch.dev_buy_lamports))));
            if junk {
                if let Err(e) = lat::junk_fire(&key2, user, &path2, &launch, create_slot).await { eprintln!("  junk fire {} failed: {e:#}", b58(&launch.mint)); }
                if let Some((cs, dev, bundle)) = FIRE_NOTES.lock().unwrap().remove(&launch.mint) {
                    tg::raise(arbx::alerts::Level::Info, "snipe_fire", &b58(&launch.mint), "🧪", "FIRE (dry: junk only)", tg::fire_body(&launch.mint, cs, dev, bundle, "-", "junk", 0, 0, buy_deadline(Some(cs))), false);
                }
                return;
            }
            if let Err(e) = round_trip_launch(&key2, user, &rpc2, &path2, &launch, cap_lamports, max_sol, land_timeout, Some(create_slot), vq_after, pos).await {
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
    if stop.load(Ordering::Relaxed) { eprintln!("  STOP: no new fires (kill switch / profit lock / signal)"); }
    if let Some(f) = fast { for l in f.summary() { eprintln!("FAST: {l}"); } }

    if close_set.is_some() { eprintln!("CLOSE-LEADER GATE: skipped {skipped_far} far-leader launches, {skipped_unknown_leader} unknown-leader launches"); }
    if gate.max_ms.is_some() { eprintln!("CREATE-MS GATE: passed {} skipped late {} skipped unknown {}", gate.passed, gate.late, gate.unknown); }
    eprintln!("MAX-INFLIGHT: skipped {skipped_inflight} qualifying launches (all {max_inflight} slots busy)");
    eprintln!("SKIPPED: balance {skipped_balance}, budget {skipped_budget}, max-buys {skipped_maxbuys}");
    eprintln!("ALT CACHE: {} table(s) cached (cap {}); {} tx(s) resolved from it, {} unresolved at arrival (fail closed; {} not relevant: not fetched); {} fetches, {} failed, {} evicted",
        altc::len(), altc::LRU_CAP, altc::HITS.load(Ordering::Relaxed), altc::MISSES.load(Ordering::Relaxed), altc::IGNORED.load(Ordering::Relaxed),
        altc::FETCHED.load(Ordering::Relaxed), altc::FAILED.load(Ordering::Relaxed), altc::EVICTED.load(Ordering::Relaxed));
    if uri_whitelist { eprintln!("URI-HOST GATE: skipped {skipped_host} non-trusted-host launches"); }
    // H1: the drain covers the worst-case position: land timeout + late-land watch + hold cap + the sell deadline + one
    // last sell wait + the realized-PnL lookups, plus margin
    let robust = has("--sell-robust");
    // (N3: the late-landing watch runs until the buy's blockhash is dead, capped at --late-land-s, default 120; N8: one sell
    // iteration can overrun the sell deadline by <= ~20 s of capped reads + the send wait)
    let drain_s = land_timeout.as_secs() + 1
        + if robust { late_land_cap_s() } else { 0 }
        + arg_u64("--hold-max-ms", 1500).max(arg_u64("--hold-ms", 0)) / 1000 + 1
        + arg_u64("--sell-deadline-s", 30).max(30) + arg_u64("--sell-retry-s", 4).max(1) + 40;
    eprintln!("\nSNIPE-LIVE: window ended — draining {} in-flight positions (up to {drain_s} s) ...", max_inflight - sem.available_permits());
    let drained = tokio::time::timeout(Duration::from_secs(drain_s), sem.acquire_many(max_inflight as u32)).await.is_ok();
    if !drained { eprintln!("  DRAIN TIMEOUT after {drain_s} s: {} position(s) still running", max_inflight - sem.available_permits()); }
    // H-1: UNSOLD positions retrying in the background get --unsold-drain-s (default 120) more, then give up
    let ud = arg_u64("--unsold-drain-s", 120);
    if UNSOLD_BG.load(Ordering::SeqCst) > 0 {
        eprintln!("  DRAIN: {} UNSOLD position(s) still retrying in the background — up to {ud} s more", UNSOLD_BG.load(Ordering::SeqCst));
        let t = Instant::now();
        while UNSOLD_BG.load(Ordering::SeqCst) > 0 && t.elapsed() < Duration::from_secs(ud) { tokio::time::sleep(Duration::from_millis(500)).await; }
    }
    SELL_GIVEUP.store(true, Ordering::SeqCst);
    let t = Instant::now();
    while UNSOLD_BG.load(Ordering::SeqCst) > 0 && t.elapsed() < Duration::from_secs(40) { tokio::time::sleep(Duration::from_millis(250)).await; }
    // H1 + N1/N3: EVERY mint this run fired on is re-read at CONFIRMED commitment (from a node at/after its buy's landing):
    // anything not 0 is HELD-AT-EXIT, whatever the exit logic concluded; an unreadable account is listed too
    let fired_list: Vec<(Pk, u64)> = ACCT.fired.lock().unwrap().iter().map(|(k, v)| (*k, *v)).collect();
    let mut held_n = 0;
    for (m, slot) in &fired_list {
        let ata = pda::ata(&user, m, &pda::TOKEN_2022);
        let mut t = tok_read_retry(rpc, &ata, "confirmed", *slot, 6).await;
        // H-1 step 4: anything still held gets ONE more exit sell (15 s: the fallback path, fallback RPC, cached blockhash)
        if t.zero_at().is_none() {
            let launch = match ACCT.launches.lock().unwrap().get(m).cloned() { Some(l) => (l, "the live create"), None => (snipe_build::launch_from_target(*m, *m), "derived") };
            let launch = if launch.1 == "derived" { resolve_launch(rpc, m).await.0 } else { launch.0 };
            eprintln!("  EXIT-SELL mint={} tokens={} — one last sell before the exit", b58(m), t.show());
            let o = SellOpts { read_first: false, wait: Duration::from_secs(2), deadline: Duration::from_secs(15), bg: false, t_decision: None };
            let out = sell_until_zero(&key, user, rpc, path, &launch, &ata, t.amount().filter(|a| *a > 0), t.amount().unwrap_or(1).max(1), *slot, o).await;
            if let Some(c) = out.sold_at { t = Tok::Closed(c); }
        }
        match t {
            t if t.zero_at().is_some() => {}
            Tok::Unknown => { held_n += 1; eprintln!("  HELD-AT-EXIT? mint={} tokens=UNREADABLE (6 confirmed reads failed) — check by hand, sell with --sell-held {}", b58(m), b58(m));
                tg::raise(arbx::alerts::Level::Critical, "snipe_held_at_exit", &b58(m), "🚨", "HELD-AT-EXIT? (unreadable)", arbx::alerts::format::Body::new().raw(format!("mint {}", tg::mint_link(m))).code("sell by hand: --sell-held", b58(m)), false); }
            t => { held_n += 1; eprintln!("  HELD-AT-EXIT mint={} tokens={} — sell by hand: --sell-held {}", b58(m), t.show(), b58(m));
                tg::raise(arbx::alerts::Level::Critical, "snipe_held_at_exit", &b58(m), "🚨", "HELD-AT-EXIT", arbx::alerts::format::Body::new().raw(format!("mint {}", tg::mint_link(m))).kv("tokens", t.show()).code("sell by hand: --sell-held", b58(m)), false); }
        }
    }
    eprintln!("  EXIT CHECK: {} fired mint(s) re-read at confirmed, {held_n} held / unreadable", fired_list.len());
    for (m, sig) in ACCT.pend_sigs.lock().unwrap().iter() {
        eprintln!("  PENDING-AT-EXIT mint={} buy sig={sig} (landing never resolved: check the wallet)", b58(m));
        tg::raise(arbx::alerts::Level::Critical, "snipe_pending_at_exit", &b58(m), "🚨", "PENDING-AT-EXIT", arbx::alerts::format::Body::new().raw(format!("mint {}", tg::mint_link(m))).raw(format!("buy {}", tg::tx_link(sig))).txt("landing never resolved: check the wallet"), false);
    }
    let end_bal_r = native_balance(rpc, user).await.ok();
    let end_bal = end_bal_r.unwrap_or(start_bal);
    eprintln!("=== SNIPE-LIVE DONE === fired {} landed {} budget used {:.6} SOL realized (in-engine) {:+.6} SOL; net {} SOL (start {} end {})",
        fired.load(Ordering::Relaxed), ACCT.landed_buys.load(Ordering::SeqCst), ACCT.budget_used.load(Ordering::SeqCst) as f64 / 1e9, ACCT.realized.load(Ordering::SeqCst) as f64 / 1e9,
        (end_bal as i64 - start_bal as i64) as f64 / 1e9, start_bal as f64/1e9, end_bal as f64/1e9);
    // M8-2: the realized lookups (incl. any started by the exit sells) are done or bounded-waited; wallet net next to the trades'
    let t = Instant::now();
    // L9-4 (audit 9): this wait comes AFTER the EXIT CHECK (whose last sells of anything still held go first); <= 30 s
    if REALIZED_INFLIGHT.load(Ordering::SeqCst) > 0 { eprintln!("  RUN END: waiting for {} realized-PnL lookup(s) (<= 30 s)", REALIZED_INFLIGHT.load(Ordering::SeqCst)); }
    while REALIZED_INFLIGHT.load(Ordering::SeqCst) > 0 && t.elapsed() < Duration::from_secs(30) { tokio::time::sleep(Duration::from_millis(200)).await; }
    let wallet_net = end_bal_r.filter(|_| start_bal > 0).map(|e| e as i64 - start_bal as i64);
    tg::raise(arbx::alerts::Level::Info, "snipe_end", "end", "🏁", "RUN END", tg::end_body(&tg::end_summary(fired.load(Ordering::Relaxed), ACCT.landed_buys.load(Ordering::SeqCst),
        if stop.load(Ordering::Relaxed) { "stopped (signal / kill switch / lock / failure stop)" } else { "window ended" }, wallet_net)), false);
    Ok(())
}

/// M1: min_tokens_out = (1 - bps/10000) x the tokens `spend` buys on a curve at virtual SOL `vq` (net of the pump fee)
fn slip_min_out(vq: u64, spend: u64, bps: u64) -> u64 {
    let net = (spend as u128 * 10_000 / (10_000 + snipe::PUMP_FEE_BPS) as u128) as u64;
    let q = snipe::curve_tokens_out(vq, net);
    (q as u128 * 10_000u128.saturating_sub(bps as u128) / 10_000) as u64
}

/// The shared buy -> read-balance -> sell -> report round-trip on a resolved Launch (from --mint or the feed).
/// `create_slot` (snipe-once only) adds the create->buy slot delta: did we snipe same-slot. GATED by the caller.
/// `vq_after` (M1): the curve after the dev buy + glued bundle, when known; `pos`: the run accounting (None: own one).
#[allow(clippy::too_many_arguments)]
async fn round_trip_launch(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, launch: &Launch,
    cap_lamports: u64, max_sol: f64, land_timeout: Duration, create_slot: Option<u64>, vq_after: Option<u64>, pos: Option<Pos>) -> Result<()> {
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
    // Slippage floor: --min-tokens-out (manual); else M1 --slip-cap-bps on the post-bundle curve (when the glued bundle is
    // known); else the deterministic --fill-cap on the dev-only floor; else a live curve read (--slip-bps).
    let spend = arg_u64("--spend-lamports", 2_000_000);
    let fill_cap = arg("--fill-cap").and_then(|s| s.parse::<f64>().ok());
    let slip = arg_u64_opt("--slip-cap-bps").zip(vq_after).map(|(b, vq)| (b, vq, slip_min_out(vq, spend, b))).filter(|x| x.2 > 1);
    let min_out = if let Some(m) = arg_u64_opt("--min-tokens-out") {
        m
    } else if let Some((b, vq, m)) = slip {
        eprintln!("  SLIP CAP {b} bps: curve after dev + bundle vq={vq} spend={spend} -> min_tokens_out={m}");
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
    // M-3: the on-chain slot deadline (create slot + N) when the guard is on and the create slot is known
    let buy_ixs = with_guard(buy_ixs, buy_deadline(create_slot));
    if spend > cap_lamports { bail!("REFUSED: buy spend {} lamports exceeds --max-sol cap {} lamports ({:.6} SOL)", spend, cap_lamports, max_sol); }
    let fee_est = arg_u64("--cu-limit", 120_000).saturating_mul(arg_u64("--cu-price-micro", 3_000_000)).div_ceil(1_000_000) + 5000;
    let pos = pos.unwrap_or_else(|| Pos::new(mint, spend, fee_est, ""));
    eprintln!("\nROUND-TRIP (LIVE): mint={} buy spend={} lamports ({:.6} SOL) via {} ...", b58(&mint), spend, spend as f64 / 1e9, path.name);

    eprintln!("  BUY-PREP {:.1} ms (round_trip entry -> send_and_poll)", t_rt.elapsed().as_secs_f64() * 1e3);
    // LAT: the send future first (tokio::join! polls in order: the buy's request leaves before getBalance is built);
    // the create slot routes the buy by its leader's client (--route-by-client). M3: the token account is watched too.
    let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
    let (buy, bal_start) = tokio::join!(send_and_poll_at(key, user, rpc, path, &buy_ixs, land_timeout, create_slot, Watch::BuyAta(ata)),
                                        async { native_balance(rpc, user).await.unwrap_or(0) });
    let buy = buy?;
    round_trip_tail(key, user, rpc, path, launch, buy, bal_start, spend, land_timeout, create_slot, min_out, fee_est, fee_est, pos).await
}

/// FAST: the buy was written by fastfire::Fast::fire; poll its land, then the same exit as round_trip_launch
#[allow(clippy::too_many_arguments)]
async fn round_trip_fast(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, p: &fastfire::Prep, cap_lamports: u64, max_sol: f64, land_timeout: Duration, fee: u64, pos: Pos) -> Result<()> {
    let spend = arg_u64("--spend-lamports", 2_000_000);
    if spend > cap_lamports { bail!("REFUSED: buy spend {} lamports exceeds --max-sol cap {} lamports ({:.6} SOL)", spend, cap_lamports, max_sol); }
    let send_slot = match send::tpu::SLOT.load(Ordering::Relaxed) { 0 => rpc.slot().await.unwrap_or(0), s => s };
    let ata = pda::ata(&user, &p.launch.mint, &pda::TOKEN_2022);
    let (mut buy, bal_start) = tokio::join!(poll_land(rpc, p.meta.sig.clone(), p.sig, send_slot, land_timeout, Watch::BuyAta(ata), p.bh_valid), async { native_balance(rpc, user).await.unwrap_or(0) });
    buy.roles = p.roles;
    jito_results(&p.fan, &p.meta);
    fix2::spawn_landed_via(&p.fan, &p.meta, buy.land_slot, p.id);
    // L-8: a failed buy pays its fee without the tips (they revert with it)
    let revert_fee = fee.saturating_sub(p.meta.tips);
    round_trip_tail(key, user, rpc, path, &p.launch, buy, bal_start, spend, land_timeout, Some(p.slot), p.min_out, fee, revert_fee, pos).await
}

/// the shared exit after the buy's land poll: late-landing watch, revert check, token balance, hold, sell until the token
/// account reads 0, report. `pos` carries the run accounting (C1: open from landing with tokens until sold).
#[allow(clippy::too_many_arguments)]
async fn round_trip_tail(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, launch: &Launch, mut buy: Landed, bal_start: u64, spend: u64,
    land_timeout: Duration, create_slot: Option<u64>, min_out: u64, fee_est: u64, revert_fee: u64, mut pos: Pos) -> Result<()> {
    let mint = launch.mint;
    let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
    // FIX2 --sell-robust: a buy not seen within the land poll may still land. N3 (re-audit): keep watching its signature
    // AND our token account until its blockhash is DEAD (confirmed block height > its lastValidBlockHeight, read every 2 s),
    // not on a fixed timer, so a change of slot timing (Alpenglow) cannot open a gap. --late-land-s (default 120) is only a
    // safety cap: a buy still unresolved there (block height never read / last valid height unknown) is kept as
    // PENDING-AT-EXIT and its mint is re-read at exit (HELD-AT-EXIT).
    let robust = has("--sell-robust");
    let mut unresolved = false;
    if buy.land_slot.is_none() && robust {
        let mut sb = [0u8; 64];
        if let Ok(v) = bs58::decode(&buy.sig).into_vec() { if v.len() == 64 { sb.copy_from_slice(&v); } }
        let cap = late_land_cap_s();
        let until = Instant::now() + Duration::from_secs(cap);
        eprintln!("  BUY not seen within {:?} (sig {}) — watching for a late landing until its blockhash is dead (last valid height {}; safety cap {cap} s)",
            land_timeout, buy.sig, if buy.last_valid > 0 { buy.last_valid.to_string() } else { "UNKNOWN".into() });
        let mut last_h: Option<Instant> = None;
        let mut dead = false;
        while Instant::now() < until {
            tokio::time::sleep(Duration::from_millis(500)).await;
            if land_check(rpc, &sb, Watch::BuyAta(ata), &mut buy).await {
                eprintln!("  LATE-LAND: buy seen via {} after the land timeout", buy.via);
                break;
            }
            if buy.last_valid > 0 && last_h.is_none_or(|t| t.elapsed() >= Duration::from_secs(2)) {
                last_h = Some(Instant::now());
                let h = call2(rpc, "getBlockHeight", serde_json::json!([{ "commitment": "confirmed" }])).await;
                if let Ok(h) = h.map(|v| v.as_u64().unwrap_or(0)) {
                    if h > buy.last_valid {
                        if land_check(rpc, &sb, Watch::BuyAta(ata), &mut buy).await { eprintln!("  LATE-LAND: buy seen via {} (final check)", buy.via); break; }
                        eprintln!("  BUY blockhash dead (confirmed block height {h} > last valid {}): it can no longer land — releasing its in-flight slot", buy.last_valid);
                        dead = true;
                        break;
                    }
                }
            }
        }
        if buy.land_slot.is_none() && !dead {
            unresolved = true;
            eprintln!("  BUY UNRESOLVED after the {cap} s safety cap (blockhash death not confirmed) sig={} — kept as PENDING-AT-EXIT; its mint is re-read at exit", buy.sig);
        }
    }
    match buy.land_slot {
        Some(land) => eprintln!("  BUY  sig={} send_slot={} land_slot={} delta={} ok={} seen_via={}", buy.sig, buy.send_slot, land, land as i64 - buy.send_slot as i64, buy.ok, buy.via),
        None if unresolved => { pos.unresolved(); bail!("BUY unresolved (sig {}) — no sell; PENDING-AT-EXIT", buy.sig) }
        None => { pos.not_landed(); bail!("BUY did not land within {:?} (sig {}) — no position, no sell", land_timeout, buy.sig) }
    }
    // M-2 (audit 3): a buy that landed FAILED: its real on-chain error is logged and classified. "slippage" = the fill cap
    // working (pump's min_tokens_out error), "slot-deadline" = the M-3 guard (landed after create slot + N, by design),
    // "other" = anything else (layout change, compute budget, accounts ...): 3 of those in a run stop new fires.
    // L-8: the fee booked is the buy's real CU limit (incl. the +300/tip bump) x price + base; tips revert with the tx.
    if !buy.ok {
        pos.reverted(revert_fee);
        let err = buy.err.clone().unwrap_or(serde_json::Value::Null);
        let line = tx_error_line(rpc, &buy.sig, 4).await;
        let class = classify_buy_err(&err, buy.roles, line.as_deref());
        let late = match (buy.land_slot, create_slot) { (Some(l), Some(c)) => format!("{:+}", l as i64 - c as i64), _ => "-".into() };
        eprintln!("  BUY FAILED sig={} land_slot={:?} slots_after_create={late} err={} class={class} error_line={} (fee {revert_fee} lamports)", buy.sig, buy.land_slot, err,
            line.as_deref().unwrap_or("(tx logs not found)"));
        {
            let mut b = tg::BOOK.lock().unwrap();
            b.fees_est += revert_fee; // L8-3: an estimate (CU limit x price + base), labelled so
            if let (Some(l), Some(c)) = (buy.land_slot, create_slot) { b.deltas.push(l as i64 - c as i64); }
        }
        tg::raise(if class == "other" { arbx::alerts::Level::Error } else { arbx::alerts::Level::Warning }, "snipe_buy_failed", &b58(&mint), "❌", &format!("BUY FAILED ({class})"),
            tg::failed_body(&mint, class, &late, line.as_deref().unwrap_or("(tx logs not found)"), revert_fee, &buy.sig), false);
        match class {
            "slippage" => eprintln!("  FILL-CAP REVERT: min_tokens_out {min_out} not met (fill > cap) — no position, cost = fees only."),
            "slot-deadline" => {
                // M4-2 (audit 4): a slot-deadline failure that landed WITHIN create + N contradicts the guard (an off-by-one
                // operator, a wrong create slot from a feed, an upgraded program): stop new fires on the first one
                let n = SLOT_GUARD.get().map(|g| g.1).unwrap_or(0);
                let within = matches!((buy.land_slot, create_slot), (Some(l), Some(c)) if l <= c + n);
                if within {
                    if let Some(st) = RUN_STOP.get() { st.store(true, Ordering::SeqCst); }
                    eprintln!("  !!!!! STOP: SLOT-DEADLINE CONTRADICTION — the buy landed at slots_after_create={late} (<= {n}) yet failed at the slot guard: the guard or the create slot is wrong. NO NEW FIRES. !!!!!");
                    tg::raise(arbx::alerts::Level::Critical, "snipe_fail_stop", "fail_stop", "🛑", "STOP: slot-deadline contradiction", arbx::alerts::format::Body::new().txt("NO NEW FIRES; open positions finish their exit").raw(format!("last {}", tg::tx_link(&buy.sig))), false);
                } else {
                    eprintln!("  SLOT-DEADLINE: the buy landed after create slot + {n} and failed on chain by design — no position, cost = fees only.");
                }
                // M4-2: slot-deadline failures count toward the 3-failure stop too
                let k = NONSLIP_FAILS.fetch_add(1, Ordering::SeqCst) + 1;
                eprintln!("  BUY-FAILURE (slot-deadline) #{k} of 3 allowed in this run");
                if k >= 3 {
                    if let Some(st) = RUN_STOP.get() { st.store(true, Ordering::SeqCst); }
                    eprintln!("  !!!!! STOP: {k} failed buys (slot-deadline / non-slippage) in this run — NO NEW FIRES. Open positions finish their exit. !!!!!");
                    tg::raise(arbx::alerts::Level::Critical, "snipe_fail_stop", "fail_stop", "🛑", "STOP: 3 failed buys", arbx::alerts::format::Body::new().txt("NO NEW FIRES; open positions finish their exit").raw(format!("last {}", tg::tx_link(&buy.sig))), false);
                }
            }
            _ => {
                let n = NONSLIP_FAILS.fetch_add(1, Ordering::SeqCst) + 1;
                eprintln!("  BUY-FAILURE (not slippage) #{n} of 3 allowed in this run (slot-deadline failures count too): err={err}");
                if n >= 3 {
                    if let Some(st) = RUN_STOP.get() { st.store(true, Ordering::SeqCst); }
                    eprintln!("  !!!!! STOP: {n} non-slippage buy failures in this run — NO NEW FIRES (something systematic: check the error lines above). Open positions finish their exit. !!!!!");
                    tg::raise(arbx::alerts::Level::Critical, "snipe_fail_stop", "fail_stop", "🛑", "STOP: 3 non-slippage buy failures", arbx::alerts::format::Body::new().txt("NO NEW FIRES; open positions finish their exit").raw(format!("last {}", tg::tx_link(&buy.sig))), false);
                }
            }
        }
        return Ok(());
    }

    // --- landed WITH tokens (ok: min_tokens_out met).
    // M4-1 (owner: "the sell has to take place on time"): NOTHING between the hold's end (the decision) and the first sell's
    // write waits on an RPC. The token amount and the wallet balance are read IN THE BACKGROUND during the hold (racing
    // both RPCs, minContextSlot = the landing slot); at the decision the amount is whatever is already known: the token
    // account seen by the landing watch, else a finished background read, else the guaranteed min_tokens_out (sold
    // without the ATA close; the remainder is re-read and sold after the first sell is sent). The cost is booked at the
    // estimate now and refined from the balance read when it is available (never waited for before the sell).
    let land = buy.land_slot.unwrap_or(0);
    let t_landing_seen = buy.t_seen.unwrap_or_else(Instant::now);
    let est = spend + fee_est + T22_ATA_RENT;
    ACCT.launches.lock().unwrap().insert(mint, launch.clone());
    pos.landed(est, land);
    let amt_task = {
        let (r, known) = (rpc.clone(), buy.tokens);
        tokio::spawn(async move {
            if let Some(t) = known { return Some(t); }
            for k in 0..9 {
                if k > 0 { tokio::time::sleep(Duration::from_millis(250)).await; }
                if let Tok::Amount(a, _) = tok_read(&r, &ata, "processed", land).await { if a > 0 { return Some(a); } }
            }
            None
        })
    };
    let bal_task = { let r = rpc.clone(); tokio::spawn(async move { native_balance(&r, user).await.ok() }) };
    let cost_of = |bal_after: Option<u64>| -> (u64, &'static str) {
        let delta = match bal_after { Some(b) if bal_start > 0 && b > 0 => bal_start.saturating_sub(b), _ => 0 };
        if delta >= spend && delta <= est + 1_000_000 { (delta, "balance-delta") } else { (est, "estimate") }
    };
    eprintln!("  POSITION OPEN mint={} cost={} lamports (estimate; refined from the balance in the background) open_total={:.6} SOL", b58(&mint), est, ACCT.open.load(Ordering::SeqCst) as f64 / 1e9);
    let land_delta = create_slot.map(|c| land as i64 - c as i64);
    { let mut b = tg::BOOK.lock().unwrap(); if let Some(d) = land_delta { b.deltas.push(d); } } // fees: from the txs at the exit (L8-3)
    tg::raise(arbx::alerts::Level::Info, "snipe_landed", &b58(&mint), "✅", &format!("BUY LANDED{}", match land_delta { Some(0) => " — same slot".to_string(), Some(d) => format!(" — create {d:+}"), None => String::new() }),
        tg::landed_body(&mint, land_delta, buy.via, buy.tokens, est, &buy.sig), false);

    // --- EXIT: price-reactive ladder (--exit-ladder) replaces the fixed hold + sell (not used by Run 1).
    if has("--exit-ladder") {
        let exact = amt_task.await.ok().flatten();
        let bal_after_buy = bal_task.await.ok().flatten();
        let (cost, _) = cost_of(bal_after_buy);
        pos.refine_cost(cost);
        let r = exit_ladder(key, user, rpc, path, launch, exact.unwrap_or(min_out), spend, bal_start, bal_after_buy.unwrap_or(0), &buy, create_slot, land_timeout).await;
        // N1: closed only on a CONFIRMED zero read at/after the landing
        if let Some(c) = tok_read_retry(rpc, &ata, "confirmed", land, 6).await.zero_at() { pos.sold(c); }
        // N6: the balance fallback only with BOTH reads good, else the position's cost is booked as the loss
        let bal_end = native_balance(rpc, user).await.ok();
        pos.realized_done = true;
        ACCT.realized.fetch_add(realized_fallback(bal_start, bal_end, cost).0, Ordering::SeqCst);
        return r;
    }

    // --- HOLD from the landing as SEEN (M3): --hold-slots N (feed slot >= land slot + N), else --hold-ms
    hold_wait(&buy).await;

    // --- DECISION: no RPC from here to the first sell's write
    let t_decision = Instant::now();
    let slot_decision = send::tpu::SLOT.load(Ordering::Relaxed);
    let (exact, amount_src) = if let Some(t) = buy.tokens { (Some(t), "landing watch (token account)") }
        else if amt_task.is_finished() { match amt_task.await.ok().flatten() { Some(t) => (Some(t), "background token read"), None => (None, "guaranteed min_tokens_out (token read gave nothing)") } }
        else { amt_task.abort(); (None, "guaranteed min_tokens_out (token read not back yet)") };
    {
        // (printed off this task: nothing but the sell between the decision and its write)
        let line = format!("  SELL-DECISION mint={} landing->decision_ms={:.1} amount={} source={amount_src}{}", b58(&mint), t_decision.duration_since(t_landing_seen).as_secs_f64() * 1e3,
            exact.unwrap_or(min_out), if exact.is_none() { " (no ATA close; the remainder is re-read and sold after this sell is sent)" } else { "" });
        tokio::spawn(async move { eprintln!("{line}"); });
    }

    // --- SELL until the token account is CONFIRMED empty (C2 / M4 / N1): the first sell is sent from the decision with no
    // RPC (cached blockhash, known amount); reads, confirmations and the remainder come after it
    let mut o = SellOpts::main();
    o.t_decision = Some((t_decision, slot_decision));
    let out = sell_until_zero(key, user, rpc, path, launch, &ata, exact, min_out, land, o).await;
    // the cost from the balance read (it finished long ago in the normal case; never waited for before the sell)
    let bal_after_r = bal_task.await.ok().flatten();
    let (cost, cost_src) = cost_of(bal_after_r);
    pos.refine_cost(cost);
    let bal_after_buy = bal_after_r.unwrap_or(0);
    let bal_before_sell = bal_after_buy;
    if let Some(c) = out.sold_at { pos.sold(c); }
    // H-1: an UNSOLD position keeps retrying in the background (lower rate) until the exit; it is booked at its cost
    // as a loss now (the Pos drops Open) and whatever those sells return is added to realized
    else { spawn_unsold_retry(key.clone(), user, rpc.clone(), path.clone(), launch.clone(), ata, land, out.last_qty); }
    let bal_end_r = native_balance(rpc, user).await.ok();
    let bal_end = bal_end_r.unwrap_or(bal_after_buy);
    // M7: realized PnL of this position from its own transactions (payer deltas), in the background
    pos.realized_done = true;
    spawn_realized_x(rpc.clone(), mint, buy.sig.clone(), out.sigs.clone(), realized_fallback(bal_start, bal_end_r, cost),
        Some((cost, t_landing_seen.elapsed().as_secs_f64(), out.first_send_us, fee_est.saturating_sub(revert_fee).max(buy.tips), fee_est)));

    // --- report ---
    let last = out.last.as_ref();
    println!("\n========== ROUND-TRIP RESULT ==========");
    println!("mint             {}", b58(&mint));
    if let Some(cs) = create_slot {
        println!("create_slot      {cs}");
        println!("create -> buy    {}  (buy land_slot - create_slot: did we snipe same-slot)", buy.land_slot.map_or("not landed".to_string(), |l| (l as i64 - cs as i64).to_string()));
    }
    println!("buy              sig={} land_slot={:?} delta={:?} seen_via={}", buy.sig, buy.land_slot, buy.land_slot.map(|l| l as i64 - buy.send_slot as i64), buy.via);
    println!("tokens received  {}", exact.map(|a| a.to_string()).unwrap_or_else(|| format!("unreadable (>= {min_out})")));
    println!("sell             {} attempt(s), sold={} last sig={} land_slot={:?}", out.attempts, out.sold_at.is_some(), last.map(|l| l.sig.as_str()).unwrap_or("-"), last.and_then(|l| l.land_slot));
    println!("native balance   start={} after_buy={} before_sell={} end={} (lamports)", bal_start, bal_after_buy, bal_before_sell, bal_end);
    println!("buy cost         {} lamports ({:.6} SOL)  [{cost_src}]", cost, cost as f64 / 1e9);
    println!("sell return      {} lamports ({:.6} SOL)  [end - before_sell]", bal_end.saturating_sub(bal_before_sell), bal_end.saturating_sub(bal_before_sell) as f64 / 1e9);
    println!("round-trip       {:+} lamports ({:+.6} SOL)  [end - start; other positions in flight distort it: see REALIZED]", bal_end as i64 - bal_start as i64, (bal_end as i64 - bal_start as i64) as f64 / 1e9);
    println!("=======================================");
    Ok(())
}

/// M3: the hold before the sell, measured from the landing as SEEN by the land poll (not from after the post-landing RPC
/// reads). --hold-slots N (> 0, landing seen by its signature status: exact slot): sell once the shred feed's current slot
/// reaches land_slot + N (~N x 217 ms after the landing slot began), capped at --hold-max-ms (default 1500) after the
/// landing was seen. Otherwise (or landing seen via the token account) --hold-ms after the landing was seen.
async fn hold_wait(buy: &Landed) {
    let hold_ms = arg_u64("--hold-ms", 0);
    let hold_slots = arg_u64("--hold-slots", 0);
    let t_obs = buy.t_seen.unwrap_or_else(Instant::now);
    let land = buy.land_slot.unwrap_or(0);
    let mode = if hold_slots > 0 && buy.via == "status" && land > 0 {
        let target = land + hold_slots;
        let cap = t_obs + Duration::from_millis(arg_u64("--hold-max-ms", 1500).max(hold_ms));
        while send::tpu::SLOT.load(Ordering::Relaxed) < target && Instant::now() < cap { tokio::time::sleep(Duration::from_millis(5)).await; }
        if send::tpu::SLOT.load(Ordering::Relaxed) >= target { "slots" } else { "slots-capped" }
    } else {
        if hold_ms > 0 { tokio::time::sleep_until((t_obs + Duration::from_millis(hold_ms)).into()).await; }
        "ms"
    };
    let cur = send::tpu::SLOT.load(Ordering::Relaxed);
    // (printed off this task: the sell decision follows immediately and must not wait on stderr)
    let (ms, via) = (t_obs.elapsed().as_secs_f64() * 1e3, buy.via);
    tokio::spawn(async move { eprintln!("  HOLD-END mode={mode} land_slot={land} feed_slot={cur} slots_after_land={} ms_since_land_seen={ms:.0} (seen via {via})",
        if land > 0 { (cur as i64 - land as i64).to_string() } else { "-".into() }); });
}

/// L8-4: the slow path's fire facts (create slot, dev, bundle) by mint, read by send_and_poll_at after the send
static FIRE_NOTES: std::sync::LazyLock<std::sync::Mutex<std::collections::HashMap<Pk, (u64, u64, Option<u64>)>>> = std::sync::LazyLock::new(|| std::sync::Mutex::new(std::collections::HashMap::new()));

/// one exit's sells. `sold_at`: the context slot of the CONFIRMED read that showed the token account closed / at 0;
/// `last_qty`: the last amount it tried to sell ((amount, exact))
struct SellOut { sold_at: Option<u64>, sigs: Vec<(String, bool, u64)>, last: Option<Landed>, attempts: u32, last_qty: (u64, bool), first_send_us: Option<f64> }

/// how a sell loop runs: `read_first` (a confirmed read before the first send), `wait` (land poll per attempt = the
/// re-send interval), `deadline`, `bg` (a background UNSOLD retry round: stops on SELL_GIVEUP, no UNSOLD line)
#[derive(Clone, Copy)]
struct SellOpts { read_first: bool, wait: Duration, deadline: Duration, bg: bool, t_decision: Option<(Instant, u64)> }
impl SellOpts {
    /// the live exit: --sell-retry-s (M-5: Run 1 = 1 s) re-sends, --sell-deadline-s (>= 30)
    fn main() -> SellOpts {
        SellOpts { read_first: false, wait: Duration::from_secs(arg_u64("--sell-retry-s", 4).max(1)), deadline: Duration::from_secs(arg_u64("--sell-deadline-s", 30).max(30)), bg: false, t_decision: None }
    }
}

/// H-1: UNSOLD positions keep retrying in the background (one round per --unsold-retry-s, default 5 s) until the exit
static UNSOLD_BG: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
static SELL_GIVEUP: AtomicBool = AtomicBool::new(false);

/// H-1: keep selling an UNSOLD position at a lower rate until the run's exit gives up (then HELD-AT-EXIT + one exit sell)
#[allow(clippy::too_many_arguments)]
fn spawn_unsold_retry(key: SigningKey, user: Pk, rpc: rpc::Rpc, path: Arc<send::Path>, launch: Launch, ata: Pk, land: u64, last_qty: (u64, bool)) {
    UNSOLD_BG.fetch_add(1, Ordering::SeqCst);
    tokio::spawn(async move {
        let every = Duration::from_secs(arg_u64("--unsold-retry-s", 5).max(1));
        eprintln!("  UNSOLD-RETRY mint={}: retrying in the background every {} s until the run's exit", b58(&launch.mint), every.as_secs());
        let mut sigs = Vec::new();
        let mut round = 0u32;
        let mut sold = false;
        let mut qty = last_qty;
        while !SELL_GIVEUP.load(Ordering::SeqCst) {
            tokio::time::sleep(every).await;
            if SELL_GIVEUP.load(Ordering::SeqCst) { break; }
            round += 1;
            let o = SellOpts { read_first: true, wait: every, deadline: Duration::from_secs(30), bg: true, t_decision: None };
            let out = sell_until_zero(&key, user, &rpc, &path, &launch, &ata, qty.1.then_some(qty.0), qty.0, land, o).await;
            sigs.extend(out.sigs.clone());
            qty = out.last_qty;
            if let Some(c) = out.sold_at {
                sold = true;
                acct_slot(c);
                eprintln!("  UNSOLD-RECOVERED mint={} after {round} background round(s): token account confirmed empty at slot {c}", b58(&launch.mint));
                tg::raise(arbx::alerts::Level::Info, "snipe_unsold_recovered", &b58(&launch.mint), "✅", "UNSOLD recovered (sold)", arbx::alerts::format::Body::new().raw(format!("mint {}", tg::mint_link(&launch.mint))).kv("rounds", round.to_string()), false);
                break;
            }
        }
        if !sold { eprintln!("  UNSOLD-RETRY mint={} stopped at the exit after {round} round(s): still held (see EXIT CHECK)", b58(&launch.mint)); }
        // the position was booked at its full cost as a loss when it went UNSOLD: add what these sells returned
        let mut back = 0i64;
        for (s, seen, _) in &sigs { if let Some(d) = tx_payer_delta(&rpc, s, if *seen { 6 } else { 2 }).await { back += d; } }
        if back != 0 { let run = ACCT.realized.fetch_add(back, Ordering::SeqCst) + back; eprintln!("  REALIZED (unsold retries) mint={} {:+.6} SOL run_realized={:+.6} SOL", b58(&launch.mint), back as f64 / 1e9, run as f64 / 1e9); }
        UNSOLD_BG.fetch_sub(1, Ordering::SeqCst);
    });
}

/// N3: the late-landing watch's safety cap (s); the watch normally ends when the buy's blockhash is dead
fn late_land_cap_s() -> u64 { arg_u64("--late-land-s", 120).max(60) }

/// N6: a position's realized PnL when its own transactions are not found: the wallet's balance change over the position,
/// only when BOTH balance reads succeeded; else the position's cost is booked as the loss (never a missing read = +balance)
fn realized_fallback(bal_start: u64, bal_end: Option<u64>, cost: u64) -> (i64, &'static str) {
    match bal_end { Some(e) if bal_start > 0 && e > 0 => (e as i64 - bal_start as i64, "balance"), _ => (-(cost as i64), "cost-as-loss (balance unread)") }
}

/// M-2 / L-11: a failed transaction's program error from its logs (Anchor "Error Code: X. Error Number: N. Error Message: M"),
/// read through call2 (up to `tries` getTransaction reads 1.5 s apart). None: not found / no Anchor error line.
async fn tx_error_line(rpc: &rpc::Rpc, sig: &str, tries: u32) -> Option<String> {
    for k in 0..tries {
        if k > 0 { tokio::time::sleep(Duration::from_millis(1500)).await; }
        let Ok(v) = call2(rpc, "getTransaction", serde_json::json!([sig, { "encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 0 }])).await else { continue };
        if v.is_null() { continue; }
        let logs: Vec<String> = v["meta"]["logMessages"].as_array().map(|a| a.iter().filter_map(|x| x.as_str().map(String::from)).collect()).unwrap_or_default();
        return Some(logs.iter().rev().find(|l| l.contains("Error Code:") || l.contains("Error Number:")).cloned()
            .or_else(|| logs.iter().rev().find(|l| l.contains("failed:")).cloned()).unwrap_or_else(|| "(no error line in the logs)".into()));
    }
    None
}

/// M-2: classify a landed-FAILED buy: "slot-deadline" (failed at the M-3 guard: landed too late, by design), "slippage"
/// (pump's min_tokens_out / slippage error at the buy instruction: the fill cap working) or "other" (anything else).
/// Pure part (unit-tested): the status error, the (guard, buy) indices and the Anchor error line when known.
fn classify_buy_err(err: &serde_json::Value, roles: (Option<u8>, Option<u8>), line: Option<&str>) -> &'static str {
    let idx = err.get("InstructionError").and_then(|x| x.get(0)).and_then(|x| x.as_u64());
    if idx.is_some() && idx == roles.0.map(|x| x as u64) { return "slot-deadline"; }
    if idx.is_none() || idx != roles.1.map(|x| x as u64) { return "other"; }
    if let Some(l) = line {
        let ll = l.to_ascii_lowercase();
        if ll.contains("slippage") || ll.contains("toomuchsolrequired") || ll.contains("toolittlesolreceived") || ll.contains("too few tokens") { return "slippage"; }
        if ll.contains("error code:") { return "other"; }
    }
    // no decodable log line: pump's slippage codes (6002 TooMuchSolRequired, 6003 TooLittleSolReceived; L4-1: the current
    // min-out errors 6040 and 6042 BuySlippageBelowMinTokensOut)
    match build::custom_code(err) { Some(6002) | Some(6003) | Some(6040) | Some(6042) => "slippage", _ => "other" }
}

/// M-2: buy failures that are neither slippage nor the slot deadline; 3 in a run stop new fires
static NONSLIP_FAILS: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

/// C2 + M4 (audit 2026-10-20) + N1/N4/N8 (re-audit) + H-1/M-5 (audit 3): sell until the token account is CONFIRMED empty.
///  * a send error (refused path, HTTP / JSON-RPC error, blockhash fetch failure) retries: blockhash fresh / fallback RPC /
///    cached (H-1), backoff 250 ms .. 2 s;
///  * M-5: EVERY sell (the first too) goes to the sell path AND --sell-fallback-path (one signature); a sell not seen
///    within `wait` (--sell-retry-s, Run 1 = 1 s) is re-sent;
///  * N1: "sold" = a CONFIRMED read (node slot >= the buy's landing and >= every landed sell) showing the account closed or
///    0; a processed status / token change is only a hint (the loop waits for confirmation instead of re-sending);
///  * M4: after every landed sell the CONFIRMED balance is re-read and the remainder sold;
///  * N4: --sell-cu-limit, x1.5 after a sell that landed FAILED (its error line is logged: L-11 a completed curve);
///  * N8: every read capped (3 s per RPC), the send wait at 5 s, so the deadline holds.
/// Runs for `opts.deadline`; the live exit then logs UNSOLD and hands the position to a background retry (H-1).
#[allow(clippy::too_many_arguments)]
async fn sell_until_zero(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, launch: &Launch, ata: &Pk, known: Option<u64>, guess: u64, land_slot: u64, opts: SellOpts) -> SellOut {
    let mut cu = sell_cu_limit();
    let price = arg_u64("--sell-cu-price-micro", arg_u64("--cu-price-micro", 3_000_000)); // sells: own (low) fee
    let t0 = Instant::now();
    let deadline = t0 + opts.deadline;
    let wait = opts.wait;
    // (amount, exact): exact = a real balance read (sell it all + close the ATA); else a guess (no close)
    let mut qty: (u64, bool) = match known { Some(a) => (a, true), None => (guess.max(1), false) };
    let mut out = SellOut { sold_at: None, sigs: Vec::new(), last: None, attempts: 0, last_qty: qty, first_send_us: None };
    let mut need_slot = land_slot; // a "sold" read must come from a node at least this far
    let mut backoff = Duration::from_millis(250);
    // a sell landed (hint) and its confirmation is awaited: since when
    let mut awaiting: Option<Instant> = None;
    let mut first = !opts.read_first;
    let mut landed_logged = false;
    loop {
        if opts.bg && SELL_GIVEUP.load(Ordering::SeqCst) { break; }
        if !first {
            match tok_read(rpc, ata, "confirmed", need_slot).await {
                t if t.zero_at().is_some() => { out.sold_at = t.zero_at(); break; }
                Tok::Amount(h, _) => { qty = (h, true); awaiting = None; }
                _ => {
                    // UNKNOWN (error / node behind need_slot). After a landed sell: wait for confirmation (up to 6 s), do
                    // not re-send blind; else re-send the last amount (a sell of tokens no longer held only fails: fee only)
                    if Instant::now() >= deadline { break; }
                    if awaiting.is_some_and(|t| t.elapsed() < Duration::from_secs(6)) { tokio::time::sleep(Duration::from_millis(300)).await; continue; }
                    awaiting = None;
                }
            }
        }
        first = false;
        if Instant::now() >= deadline { break; }
        out.last_qty = qty;
        let fb = SELL_FALLBACK.get(); // M-5: from the first sell
        let ixs = if qty.1 { snipe_build::sell_message_ixs(user, launch, qty.0, 0, cu, price, has("--wrap")) }
            else { vec![build::cu_limit_ix(cu), build::cu_price_ix(price), snipe_build::sell_ix(user, launch, qty.0, 0)] };
        out.attempts += 1;
        let watch = if qty.1 { Watch::SellAta(*ata, qty.0, need_slot) } else { Watch::None };
        match send_sell(key, user, rpc, path, fb, &ixs, wait, watch).await {
            Ok(l) => {
                eprintln!("  SELL{} #{} qty={}{} cu_limit={cu} sig={} {} via={}{}", if opts.bg { "[bg]" } else { "" }, out.attempts, qty.0, if qty.1 { "" } else { " (guess, no close)" }, l.sig,
                    match (l.land_slot, l.ok) { (Some(s), true) => format!("LANDED slot={s} delta={} (awaiting a confirmed 0)", s as i64 - l.send_slot as i64), (Some(_), false) => format!("landed FAILED err={}", l.err.as_ref().map(|e| e.to_string()).unwrap_or_default()), (None, _) => format!("not seen in {wait:?}") },
                    if l.via.is_empty() { "-" } else { l.via }, fb.map(|f| format!(" (+ {})", f.name)).unwrap_or_default());
                out.sigs.push((l.sig.clone(), l.land_slot.is_some(), l.tips));
                // M4-1: per-sell timings from the decision (no RPC between the decision and the first write)
                if let (Some((td, sd)), 1, Some(ts)) = (opts.t_decision, out.attempts, l.t_sent) {
                    out.first_send_us = Some(ts.duration_since(td).as_secs_f64() * 1e6);
                    eprintln!("  SELL-TIMING mint={} decision->send_us={:.0} (cached blockhash, known amount, built + signed + handed to {} path(s); no RPC)",
                        b58(&launch.mint), ts.duration_since(td).as_secs_f64() * 1e6, if fb.is_some() { 2 } else { 1 });
                    let _ = sd;
                }
                if let (Some((td, sd)), false, Some(s), true) = (opts.t_decision, landed_logged, l.land_slot, l.ok) {
                    landed_logged = true;
                    eprintln!("  SELL-TIMING mint={} decision->first_sell_landed_ms={:.0} slots_after_decision={} (attempt #{}, seen via {})", b58(&launch.mint),
                        l.t_seen.map(|t| t.duration_since(td).as_secs_f64() * 1e3).unwrap_or(-1.0), if sd > 0 { (s as i64 - sd as i64).to_string() } else { "-".into() }, out.attempts, l.via);
                }
                match (l.land_slot, l.ok) {
                    (Some(s), true) => { need_slot = need_slot.max(s); awaiting = Some(Instant::now()); }
                    (Some(_), false) => {
                        // landed FAILED (each costs a fee): N4 more CU next time (a ComputeBudgetExceeded sell would repeat), back off;
                        // L-11: its program error is logged in the background (a completed curve cannot be sold here)
                        cu = (cu as u64 * 3 / 2).min(400_000) as u32;
                        let (r2, sig2, m) = (rpc.clone(), l.sig.clone(), launch.mint);
                        tokio::spawn(async move {
                            let line = tx_error_line(&r2, &sig2, 4).await.unwrap_or_else(|| "(tx not found)".into());
                            let loud = if line.to_ascii_lowercase().contains("complete") { " — BONDING CURVE COMPLETE: this engine cannot sell it; sell on PumpSwap by hand" } else { "" };
                            eprintln!("  SELL-FAILED-ERROR mint={} sig={sig2}: {line}{loud}", b58(&m));
                        });
                        tokio::time::sleep(backoff).await; backoff = (backoff * 2).min(Duration::from_secs(2));
                    }
                    (None, _) => {}
                }
                out.last = Some(l);
            }
            Err(e) => {
                eprintln!("  SELL-SEND-ERROR #{} qty={}: {} — retrying (backoff {} ms)", out.attempts, qty.0,
                    redact(&format!("{e:#}")).chars().take(200).collect::<String>(), backoff.as_millis());
                tokio::time::sleep(backoff).await;
                backoff = (backoff * 2).min(Duration::from_secs(2));
            }
        }
    }
    if out.sold_at.is_none() && !(opts.bg && SELL_GIVEUP.load(Ordering::SeqCst)) {
        let t = tok_read_retry(rpc, ata, "confirmed", need_slot, 6).await;
        match t.zero_at() {
            Some(c) => out.sold_at = Some(c),
            None if !opts.bg => {
                eprintln!("  UNSOLD mint={} tokens={} (confirmed read, node slot >= {need_slot}) after {:.0} s / {} sell attempt(s) — STILL HELD (or unknown): retrying in the background; by hand: --sell-held {}",
                    b58(&launch.mint), t.show(), t0.elapsed().as_secs_f64(), out.attempts, b58(&launch.mint));
                tg::raise(arbx::alerts::Level::Critical, "snipe_unsold", &b58(&launch.mint), "🚨", "UNSOLD: position still held", arbx::alerts::format::Body::new().raw(format!("mint {}", tg::mint_link(&launch.mint)))
                    .kv("tokens", t.show()).kv("attempts", out.attempts.to_string()).txt("retrying in the background; by hand: --sell-held").code("mint", b58(&launch.mint)), false);
            }
            None => {}
        }
        if let Tok::Amount(a, _) = t { if a > 0 { out.last_qty = (a, true); } }
    }
    if let Some(c) = out.sold_at { eprintln!("  SOLD mint={} token account confirmed {} at slot {c}", b58(&launch.mint), if qty.1 { "closed/0" } else { "0" }); }
    out
}

/// C2: one sell attempt: a fresh blockhash (cache <= 1.5 s old, else getLatestBlockhash), one signed tx sent to the sell
/// path (and `fb`, the fallback, with its minimum tip when it needs one) at once; Ok when one path accepted, then the land
/// poll (signature status + the token account). Err: blockhash failure / build failure / every path refused.
#[allow(clippy::too_many_arguments)]
/// a built and signed sell, ready for the send paths
struct SellTx { raw: Vec<u8>, sig: String, sig_bytes: [u8; 64], fan: Vec<Arc<send::Path>>, meta: lat::Meta, last_valid: u64, send_slot: u64 }

/// M4-1 (owner): the WHOLE pre-send work of a sell, with NO RPC (there is no Rpc argument): the blockhash from the cache
/// (refreshed in the background every ~400 ms from both RPCs), build + sign, the fan-out (sell path + fallback path).
/// Err(None): the cached blockhash is older than `max_age` (the caller refreshes it, racing both RPCs, 300 ms cap).
fn sell_presend(key: &SigningKey, user: Pk, path: &Arc<send::Path>, fb: Option<&Arc<send::Path>>, ixs: &[build::Ix], max_age: Duration) -> std::result::Result<SellTx, Option<anyhow::Error>> {
    let (bh, last_valid) = cached_blockhash(max_age).ok_or(None)?;
    let mut fan = vec![sp(path).clone()];
    if let Some(f) = fb { if f.name != fan[0].name { fan.push(f.clone()); } }
    let (raw, tips) = lat::build_tx(key, user, ixs, &mut fan, bh).map_err(Some)?;
    let sig = send::first_signature(&raw).context("signed tx has no signature").map_err(Some)?;
    let mut sig_bytes = [0u8; 64];
    sig_bytes.copy_from_slice(&raw[1..65]);
    let send_slot = send::tpu::SLOT.load(Ordering::Relaxed); // the feed's slot (0 unknown): never an RPC here
    let meta = lat::Meta { route: "sell".into(), sig: sig.clone(), bytes: raw.len(), tips: tips.iter().map(|t| t.1).sum(), ..Default::default() };
    Ok(SellTx { raw, sig, sig_bytes, fan, meta, last_valid, send_slot })
}

async fn send_sell(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, fb: Option<&Arc<send::Path>>, ixs: &[build::Ix], wait: Duration, watch: Watch) -> Result<Landed> {
    let pre = match sell_presend(key, user, path, fb, ixs, Duration::from_secs(20)) {
        Ok(p) => p,
        Err(Some(e)) => return Err(e),
        // the cache is > 20 s old (refresher failing on both RPCs): one inline parallel refresh (300 ms), then <= 25 s
        Err(None) => { sell_blockhash(rpc).await?; sell_presend(key, user, path, fb, ixs, Duration::from_secs(25)).map_err(|e| e.unwrap_or_else(|| anyhow::anyhow!("no usable blockhash")))? }
    };
    let SellTx { raw, sig, sig_bytes, fan, meta, last_valid, send_slot } = pre;
    let t0 = Instant::now();
    let raw = Arc::new(raw);
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel();
    for p in &fan {
        let (p, raw, tx, m) = (p.clone(), raw.clone(), tx.clone(), meta.clone());
        tokio::spawn(async move { let r = lat::send_one(&p, &raw, t0, &m).await; let _ = tx.send((p.name.clone(), r.err().map(|e| e.msg))); });
    }
    drop(tx);
    let t_sent = Instant::now(); // handed to every send path
    // N8: wait for the first acceptance at most 5 s (the send paths keep their own behaviour; only our wait is bounded).
    // No answer at all in 5 s: the tx may still be in flight, so poll for it anyway; every path refused: Err (retry)
    let mut errs = Vec::new();
    let mut any_ok = false;
    let until = tokio::time::Instant::now() + Duration::from_secs(5);
    loop {
        match tokio::time::timeout_at(until, rx.recv()).await {
            Ok(Some((_, None))) => { any_ok = true; break; }
            Ok(Some((name, Some(m)))) => errs.push(format!("{name}: {m}")),
            Ok(None) => break,
            Err(_) => { eprintln!("  SELL send: no path answered within 5 s ({} refused) — polling for it anyway", errs.len()); any_ok = true; break; }
        }
    }
    if !any_ok { bail!("sell refused on every path: {}", errs.join(" / ")); }
    let tips_paid = meta.tips;
    let mut l = poll_land(rpc, sig, sig_bytes, send_slot, wait, watch, last_valid).await;
    l.t_sent = Some(t_sent);
    l.tips = tips_paid;
    Ok(l)
}

/// M7: one position's realized PnL from its own transactions: the payer's balance delta in the buy and in every sell
/// (getTransaction, confirmed). Fallback (buy tx not found): the wallet's balance change over the position.
fn spawn_realized(rpc: rpc::Rpc, mint: Pk, buy_sig: String, sells: Vec<(String, bool, u64)>, fallback: (i64, &'static str)) {
    spawn_realized_x(rpc, mint, buy_sig, sells, fallback, None);
}
/// the exit's facts for its Telegram message: (cost estimate, hold s, decision->send us, the buy's tips, the buy's fee
/// estimate = CU limit x price + tips + base)
type ExitInfo = (u64, f64, Option<f64>, u64, u64);
fn spawn_realized_x(rpc: rpc::Rpc, mint: Pk, buy_sig: String, sells: Vec<(String, bool, u64)>, fallback: (i64, &'static str), info: Option<ExitInfo>) {
    REALIZED_INFLIGHT.fetch_add(1, Ordering::SeqCst);
    tokio::spawn(async move {
        let buy = tx_payer(&rpc, &buy_sig, 8).await;
        // L8-3: the sells' own flows: proceeds = sum of their payer deltas (net of their fees + tips); fees from the txs
        let (mut sold, mut sell_fees, mut sell_tips, mut sells_found) = (0i64, 0u64, 0u64, 0usize);
        for (s, seen, tips) in &sells {
            // L9-3: a FAILED sell's tips revert with it: only its fee is paid
            if let Some((d, f, ok)) = tx_payer(&rpc, s, if *seen { 8 } else { 2 }).await { sold += d; sell_fees += f; if ok { sell_tips += tips; } sells_found += 1; }
        }
        let (pnl, src) = match buy { Some((d, _, _)) => (d + sold, "tx"), None => fallback };
        let run = ACCT.realized.fetch_add(pnl, Ordering::SeqCst) + pnl;
        eprintln!("  REALIZED mint={} pnl={:+.6} SOL source={src} run_realized={:+.6} SOL", b58(&mint), pnl as f64 / 1e9, run as f64 / 1e9);
        if let Some((cost_est, hold_s, dec, buy_tips, fee_est)) = info {
            {
                let mut b = tg::BOOK.lock().unwrap();
                b.trades.push((mint, pnl));
                // L8-3: actual fees (base + priority from the txs, + the tips we paid) where the txs were found, else estimates
                // L9-3: the not-found estimate is the buy's fee estimate (CU limit x price + tips + base) — never derived from the
                // cost (which holds the spend, pump's trade fee and rent)
                match buy { Some((_, f, _)) => b.fees += f + buy_tips, None => b.fees_est += fee_est }
                b.fees += sell_fees + sell_tips;
            }
            let cost = buy.map(|(d, _, _)| (-d).max(0) as u64).unwrap_or(cost_est);
            let e = tg::Exit { mint, legs: sells.len() as u32, proceeds: (sells_found > 0).then_some(sold), pnl, cost, hold_s, dec_send_us: dec, run_pnl: run,
                trades: ACCT.landed_buys.load(Ordering::SeqCst), src: src.to_string() };
            let verified = src == "tx";
            tg::raise(arbx::alerts::Level::Info, "snipe_exit", &b58(&mint), if pnl >= 0 { "🟢" } else { "🔴" },
                &format!("EXIT {} SOL{}", sol_str(pnl).trim_end_matches(" SOL"), if verified { "" } else { " (UNVERIFIED: buy tx not found)" }), tg::exit_body(&e), false);
        }
        REALIZED_INFLIGHT.fetch_sub(1, Ordering::SeqCst);
    });
}

/// the fee payer's lamport change in a landed transaction (None: not found after `tries` reads 1.5 s apart)
async fn tx_payer_delta(rpc: &rpc::Rpc, sig: &str, tries: u32) -> Option<i64> { tx_payer(rpc, sig, tries).await.map(|x| x.0) }

/// L8-3: (the payer's lamport change, the transaction's fee = base + priority, it SUCCEEDED) of a landed transaction
async fn tx_payer(rpc: &rpc::Rpc, sig: &str, tries: u32) -> Option<(i64, u64, bool)> {
    for k in 0..tries {
        if k > 0 { tokio::time::sleep(Duration::from_millis(1500)).await; }
        if let Ok(v) = call2(rpc, "getTransaction", serde_json::json!([sig, { "encoding": "json", "commitment": "confirmed", "maxSupportedTransactionVersion": 0 }])).await {
            if v.is_null() { continue; }
            let (pre, post) = (v["meta"]["preBalances"][0].as_i64()?, v["meta"]["postBalances"][0].as_i64()?);
            return Some((post - pre, v["meta"]["fee"].as_u64().unwrap_or(0), v["meta"]["err"].is_null()));
        }
    }
    None
}

/// M8-2 (audit 8): realized-PnL lookups still running (the run's end waits for them, bounded, before EXIT CHECK / RUN END)
static REALIZED_INFLIGHT: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);

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
    let cu = sell_cu_limit(); // N4
    let price = arg_u64("--sell-cu-price-micro", arg_u64("--cu-price-micro", 3_000_000)); // sells: own (low) fee, buys keep --cu-price-micro
    let mint = launch.mint;
    let land = buy.land_slot.unwrap_or(0);
    let entry = buy_spend as f64 / amount.max(1) as f64; // lamports(quote)/token at the fill

    // --- instant dead-token check (one read, no delay) ---
    if min_others_sol > 0.0 {
        if let Some((_vt, vq)) = curve_reserves(rpc, &launch.bonding_curve).await {
            let others_sol = (vq as f64 - PUMP_VQ0 - launch.dev_buy_lamports as f64 - buy_spend as f64) / 1e9;
            if others_sol < min_others_sol {
                eprintln!("  DEAD-no-demand: only dev+us in curve (others={:.4} SOL < {:.4}) — dumping immediately.", others_sol, min_others_sol);
                let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
                let out = sell_until_zero(key, user, rpc, path, launch, &ata, Some(amount), amount, land, SellOpts::main()).await;
                eprintln!("  SELL[DEAD] qty={amount} sold={} attempts={}", out.sold_at.is_some(), out.attempts);
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
            // C2: a send error no longer aborts the exit (`?`): it ends the ladder and the flush below sells until 0
            let mut sell = match do_sell(key, user, rpc, path, launch, qty, close, cu, price, land_timeout).await {
                Ok(l) => l,
                Err(e) => { eprintln!("  SELL[{why}] qty={qty} send error: {e:#} — stopping ladder, flushing the remainder"); break; }
            };
            if sell.land_slot.is_none() {
                eprintln!("  SELL[{why}] qty={qty} not seen — retry once");
                sell = match do_sell(key, user, rpc, path, launch, qty, close, cu, price, land_timeout).await {
                    Ok(l) => l,
                    Err(e) => { eprintln!("  SELL[{why}] qty={qty} retry send error: {e:#} — stopping ladder, flushing the remainder"); legs.push((r, qty, sell)); break; }
                };
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
    // N1: a CONFIRMED read at/after the landing; unreadable is not 0 (flush with the guess)
    let held = tok_read_retry(rpc, &ata, "confirmed", land, 4).await;
    if held.zero_at().is_none() {
        eprintln!("  FLUSH remaining {} tokens (sell until a confirmed 0) ...", held.show());
        let _ = sell_until_zero(key, user, rpc, path, launch, &ata, held.amount().filter(|h| *h > 0), remaining.max(1), land, SellOpts::main()).await;
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
            // M2: every 10 min (the book always holds the current + next epoch, so an epoch boundary is covered); a failed
            // refresh keeps the old book and is retried after 60 s
            let mut wait = Duration::from_secs(600);
            while !stop.load(Ordering::Relaxed) {
                tokio::time::sleep(wait).await;
                match refresh(&rpc).await {
                    Ok(m) => { eprintln!("  {m}"); wait = Duration::from_secs(600); }
                    Err(e) => { eprintln!("  LEADER-BOOK refresh failed (kept the old one, retry in 60 s): {e:#}"); wait = Duration::from_secs(60); }
                }
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
        let bh = BLOCKHASH_CACHE.lock().unwrap().map(|(h, _, _)| h).unwrap_or([0u8; 32]);
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
        /// L1: the blockhash's last valid block height
        pub bh_valid: u64,
        /// M-3: the on-chain slot deadline in this buy (None: guard off); M-2: (guard ix, buy ix) indices
        pub deadline: Option<u64>,
        pub roles: (Option<u8>, Option<u8>),
        /// M1: offset of min_tokens_out in `raw` (None: not found once -> no re-sign, the prepared min_out stays)
        pub mo_off: Option<usize>,
        /// M1: where each framed request carries the tx bytes (patched in place on a re-sign)
        pub ats: Vec<fast::TxAt>,
        /// M1: the re-sign at the decision (ns; 0 = none)
        pub resign_ns: u64,
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
            let (ixs, _) = build_buy(user, &probe, None, 2_000_000, fast::PROBE_MIN_OUT);
            // M-3: the slot guard (when on) with the probe deadline, patched per launch
            let guard = SLOT_GUARD.get().is_some();
            let mut ixs = with_guard(ixs, guard.then_some(fast::PROBE_DEADLINE));
            let (p0, p1) = (probe.mint, probe.bonding_curve);
            let map = [(pda::ata(&p1, &p0, &pda::TOKEN_2022), fast::probe_var(2)), (pda::ata(&p1, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), fast::probe_var(3)),
                (pda::ata(&user, &p0, &pda::TOKEN_2022), fast::probe_var(4))];
            for ix in ixs.iter_mut() { for a in ix.accounts.iter_mut() { if let Some((_, to)) = map.iter().find(|(from, _)| *from == a.key) { a.key = *to; } } }
            let mut v: Vec<build::Ix> = tips.iter().enumerate().map(|(i, (_, l))| build::transfer_ix(user, fast::probe_tip(i), *l)).collect();
            v.extend(ixs);
            if tips.len() > 2 { lat::bump_cu_limit(&mut v, 300 * (tips.len() as u32 - 2)); }
            let msg = build::compile_v0(user, &v, fast::PROBE_BH, &[], &[])?;
            if 1 + 64 + msg.bytes.len() > 1232 { return Err(format!("{} bytes > 1232", 1 + 64 + msg.bytes.len())); }
            Template::from_probe_msg_dl(msg.bytes, tips.len(), guard)
        }

        /// the full compile of the same buy (the reference the fast build must equal byte for byte)
        fn reference(&self, launch: &Launch, tips: &[(Pk, u64)], bh: [u8; 32], min_out: u64, deadline: Option<u64>) -> Option<Vec<u8>> {
            let (ixs, _) = build_buy(self.user, launch, None, 2_000_000, min_out);
            let ixs = with_guard(ixs, deadline);
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
            // L2: the cached blockhash's age (refreshed every 300 ms): > 2 s is logged (refresher lagging), > 20 s or none
            // refuses the prepare (a buy on a dying blockhash cannot land; no fire, no budget used)
            let (bh, bh_age, bh_valid) = match *BLOCKHASH_CACHE.lock().unwrap() { Some((h, t, v)) => (h, t.elapsed(), v), None => bail!("no blockhash cached yet") };
            if bh_age > Duration::from_secs(20) { bail!("the cached blockhash is {:.1} s old (refresher failing?): refusing to prepare", bh_age.as_secs_f64()); }
            // L7-3: the age includes the confirmed-vs-tip lag (~1-2.5 s normally): log only past 4 s, at most once per 30 s
            if bh_age > Duration::from_secs(4) {
                static LAST: std::sync::Mutex<Option<Instant>> = std::sync::Mutex::new(None);
                let mut g = LAST.lock().unwrap();
                if g.is_none_or(|t| t.elapsed() > Duration::from_secs(30)) { *g = Some(Instant::now()); log_line(format!("  BLOCKHASH-AGE {:.1} s at prepare (mint {}): no newer blockhash accepted lately (normal: 1-2.5 s incl. the confirmation lag)", bh_age.as_secs_f64(), b58(&launch.mint))); }
            }
            let t1 = fast::mono_ns();
            let tpl = self.template(&tips);
            let (mint, bc) = (launch.mint, launch.bonding_curve);
            let ata = |o: &Pk, m: &Pk, t: &Pk| if self.fast_derive { fast::ata_fast(o, m, t) } else { pda::ata(o, m, t) };
            let abc = if launch.is_create_v2 { launch.assoc_bonding_curve } else { ata(&bc, &mint, &pda::TOKEN_2022) };
            let vars: fast::VarKeys = [mint, bc, abc, ata(&bc, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), ata(&self.user, &mint, &pda::TOKEN_2022), launch.buyback_fee_recipient];
            let t2 = fast::mono_ns();
            let tip_keys: Vec<Pk> = tips.iter().map(|t| t.0).collect();
            let mut msg: Vec<u8> = Vec::with_capacity(1232);
            // M-3: the on-chain slot deadline = the create slot + N (None: guard off)
            let deadline = buy_deadline(Some(slot));
            let fast_built = tpl.as_ref().and_then(|t| t.patch_dl(&mut msg, &vars, &tip_keys, &bh, min_out, deadline)).is_some();
            let (raw, sig, t3) = if fast_built {
                let t3 = fast::mono_ns();
                let sig = self.presign.as_ref().and_then(|ps| ps.sign(&msg)).unwrap_or_else(|| self.key.sign(&msg).to_bytes());
                let mut raw = Vec::with_capacity(65 + msg.len());
                raw.push(1); raw.extend_from_slice(&sig); raw.extend_from_slice(&msg);
                (raw, sig, t3)
            } else {
                let (ixs, _) = build_buy(self.user, launch, None, 2_000_000, min_out);
                let ixs = with_guard(ixs, deadline);
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
            // M1: locate min_out in the tx and the tx in every framed request (off the decision path)
            let mo_off = fast::min_out_offset(&raw, &snipe_build::BUY_EXACT_QUOTE_IN_V3_DISC).filter(|&o| raw[o..o + 8] == min_out.to_le_bytes());
            let ats: Vec<fast::TxAt> = reqs.iter().map(|r| r.as_ref().map(|(q, _)| fast::locate_tx(q, &payload)).unwrap_or(fast::TxAt::None)).collect();
            // warm the kernel send path of every socket this fire may write (zero-length sends: nothing goes out; not in prep_ns)
            for &i in &fpi { match self.fps.get(i).map(|f| &f.kind) { Some(Kind::Http { conn, .. }) => conn.prewarm(), Some(Kind::JitoH2 { conn, .. }) => conn.prewarm(), _ => {} } }
            meta.sig = if self.junk { "junk".into() } else { bs58::encode(&sig).into_string() };
            meta.bytes = raw.len();
            meta.tips = tips.iter().map(|t| t.1).sum();
            let roles = ix_roles(&raw);
            Ok(Prep { id: self.next_id.fetch_add(1, Ordering::Relaxed), launch: launch.clone(), slot, fan, fpi, meta, raw, sig, payload: Arc::new(payload), reqs, tips, jtok, bh, min_out,
                bh_valid, deadline, roles, mo_off, ats, resign_ns: 0, fast_built, st: [t0, t1, t2, t3, t4, t5], made: Instant::now(), cr })
        }

        /// M1 HOT PATH (between the decision and the first write): set min_tokens_out to `min_out` and re-sign. Patches 8
        /// bytes of the message, signs once (presigned nonce with --fast-presign), and patches the signature + those 8 bytes
        /// into the payload and every framed request in place. No allocation but the signature's base58 for the logs.
        pub fn resign(&self, p: &mut Prep, min_out: u64) -> std::result::Result<(), &'static str> {
            let t = fast::mono_ns();
            let mo = p.mo_off.ok_or("min_out offset unknown")?;
            let b = min_out.to_le_bytes();
            p.raw[mo..mo + 8].copy_from_slice(&b);
            let sig = self.presign.as_ref().and_then(|ps| ps.sign(&p.raw[65..])).unwrap_or_else(|| self.key.sign(&p.raw[65..]).to_bytes());
            p.raw[1..65].copy_from_slice(&sig);
            let pl = Arc::make_mut(&mut p.payload);
            pl[1..65].copy_from_slice(&sig);
            pl[mo..mo + 8].copy_from_slice(&b);
            let ranges = [(1usize, 65usize), (mo, mo + 8)];
            for (i, r) in p.reqs.iter_mut().enumerate() {
                if let Some((q, _)) = r { fast::repatch_req(q, p.ats.get(i).copied().unwrap_or(fast::TxAt::None), pl, &ranges); }
            }
            p.sig = sig;
            p.min_out = min_out;
            if !self.junk { p.meta.sig = bs58::encode(&sig).into_string(); }
            p.resign_ns = fast::mono_ns().saturating_sub(t);
            Ok(())
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
                let r = self.reference(&p.launch, &p.tips, p.bh, p.min_out, p.deadline);
                let sig_ok = self.key.verifying_key().verify_strict(&p.raw[65..], &ed25519_dalek::Signature::from_bytes(&p.sig)).is_ok();
                // M1: every framed request must carry exactly the (re-signed) payload
                let reqs_ok = p.reqs.iter().zip(&p.ats).all(|(r, at)| match (r, at) {
                    (Some((q, _)), fast::TxAt::Raw(o)) => q.get(*o..*o + p.payload.len()) == Some(&p.payload[..]),
                    (Some((q, _)), fast::TxAt::B64(o)) => { use base64::Engine as _; let b = base64::engine::general_purpose::STANDARD.encode(&p.payload[..]); q.get(*o..*o + b.len()) == Some(b.as_bytes()) }
                    _ => true,
                });
                let payload_ok = p.payload[1..] == p.raw[1..];
                if !reqs_ok || !payload_ok { eprintln!("  FAST-VERIFY REQUEST MISMATCH mint={} (requests_ok={reqs_ok} payload_ok={payload_ok})", b58(&p.launch.mint)); }
                let same = r.as_deref() == Some(&p.raw[65..]) && sig_ok && reqs_ok && payload_ok;
                if same { self.verified.fetch_add(1, Ordering::Relaxed); } else {
                    self.mismatched.fetch_add(1, Ordering::Relaxed);
                    eprintln!("  FAST-VERIFY MISMATCH mint={} (fast-built message != full compile)", b58(&p.launch.mint));
                }
                Some(same)
            } else { None };
            self.trace_line(serde_json::json!({ "ev": "prep", "id": p.id, "mint": b58(&p.launch.mint), "slot": p.slot, "route": p.meta.route, "paths": p.fan.len(),
                "tips": p.tips.len(), "bytes": p.raw.len(), "fast_built": p.fast_built, "verify": ok, "min_out": p.min_out, "resign_ns": p.resign_ns,
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
                "decide_to_first_write_ns": if first > 0 { first.saturating_sub(t_dec) } else { 0 }, "fire_total_ns": r.t_end - r.t_fire0, "resign_ns": p.resign_ns,
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
        // zero network: a placeholder blockhash when the refresher has not answered yet (nothing is ever sent here)
        BLOCKHASH_CACHE.lock().unwrap().get_or_insert(([7u8; 32], Instant::now(), 0));
        let mut old_ns: Vec<u64> = Vec::new();
        let mut rs: Vec<u64> = Vec::new();
        let mut rs_fail = 0u64;
        let mut st: [Vec<u64>; 6] = Default::default();
        let (mut same, mut diff) = (0u64, 0u64);
        for i in 0..n {
            let mut m = [0u8; 32];
            m[..8].copy_from_slice(&(0x5eed_0000_0000u64 + i as u64).to_le_bytes());
            m[31] = 0x77;
            let mut l = snipe_build::launch_from_target(m, f.user);
            l.dev_buy_lamports = 1_000_000_000;
            let mut p = match f.prepare(&l, 0, 12_345_678, [0; 6]) { Ok(p) => p, Err(e) => { eprintln!("bench prepare: {e:#}"); return; } };
            for k in 0..5 { st[k].push(p.st[k + 1] - p.st[k]); }
            // M1: the re-sign at the decision (new min_out), then checked byte for byte below and the requests verified
            if f.resign(&mut p, 23_456_789 + i as u64).is_ok() { rs.push(p.resign_ns); } else { rs_fail += 1; }
            st[5].push(p.st[5] - p.st[0]);
            // the old path for the same launch and tips
            let t = fast::mono_ns();
            let (ixs, _) = build_buy(f.user, &l, None, 2_000_000, 12_345_678);
            let mut fan = p.fan.clone();
            let _ = lat::build_tx(&f.key, f.user, &ixs, &mut fan, p.bh);
            old_ns.push(fast::mono_ns() - t);
            if p.fast_built { if f.reference(&l, &p.tips, p.bh, p.min_out, p.deadline).as_deref() == Some(&p.raw[65..]) { same += 1 } else { diff += 1 } }
        }
        let q = |v: &mut Vec<u64>, x: f64| { v.sort_unstable(); v[((v.len() - 1) as f64 * x).round() as usize] as f64 / 1e3 };
        println!("\n========== FAST-BENCH (n={n}, µs p50 / p99) ==========");
        for (k, name) in ["route+tips+blockhash", "derive 2 ATAs", "template patch", "ed25519 sign", "encode+frame all paths", "PREPARE TOTAL"].iter().enumerate() {
            println!("{name:24} {:8.2} / {:8.2}", q(&mut st[k], 0.5), q(&mut st[k], 0.99));
        }
        println!("{:24} {:8.2} / {:8.2}", "OLD build_buy+build_tx", q(&mut old_ns, 0.5), q(&mut old_ns, 0.99));
        if !rs.is_empty() { println!("{:24} {:8.2} / {:8.2}   (added between the decision and the first write; {rs_fail} not re-signable)", "M1 RE-SIGN at decision", q(&mut rs, 0.5), q(&mut rs, 0.99)); }
        println!("byte check vs full compile (after the M1 re-sign): {same} identical, {diff} different");
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
                    if let Some((p, _)) = ours.iter().find(|(_, id)| *id == bid) { verdict = format!("our-jito-bundle path={p} bundle={}", bid.get(..12).unwrap_or(&bid)); break; }
                    let (_, b) = jget(&format!("https://bundles.jito.wtf/api/v1/bundles/bundle/{bid}")).await;
                    let b0 = b.as_array().and_then(|a| a.first()).cloned().unwrap_or(serde_json::Value::Null);
                    let ntx = b0["txSignatures"].as_array().map(|a| a.len()).unwrap_or(0);
                    let tippers: Vec<String> = b0["tippers"].as_array().into_iter().flatten().filter_map(|x| x.as_str()).map(|x| x[..8.min(x.len())].to_string()).collect();
                    let kind = if ntx == 2 { "2-tx bundle (ours + a sender's tip tx: Helius Sender / another relay's wrapper)" } else if ntx == 1 { "1-tx bundle (a relay's bundleOnly copy)" } else { "other bundle" };
                    verdict = format!("other-bundle {kind} bundle={} txs={ntx} tippers={} landed_tip={} block_index={}", bid.get(..12).unwrap_or(&bid), tippers.join("|"),
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

#[cfg(test)]
mod audit_tests {
    use super::*;
    /// tests that touch BLOCKHASH_CACHE / SLOT / BH_STATE run one at a time
    static BH_GLOBALS: std::sync::Mutex<()> = std::sync::Mutex::new(());
    const SOL: i64 = 1_000_000_000;

    /// C1/M7: the audit's kill-switch scenarios (ops/run1/killswitch_model.py) on the engine's own decision function.
    /// Each poll: (pnl, realized, pending, inflight) as the new accounting reports them.
    fn run(polls: &[(i64, i64, u64, u64)]) -> Option<(usize, KsVerdict)> {
        let tiers = [(3 * SOL / 10, 0), (6 * SOL / 10, 3 * SOL / 10)];
        let mut st = KsState::default();
        for (i, &(pnl, real, pend, infl)) in polls.iter().enumerate() {
            let (v, _) = ks_eval(&mut st, pnl, real, pend, infl, SOL / 2, &tiers);
            if v != KsVerdict::Go { return Some((i, v)); }
        }
        None
    }

    #[test]
    fn scenario_a_never_landing_buy_does_not_arm_the_lock() {
        // the buy is pending/in flight for ~36 s; it never adds open cost: pnl stays 0, the lock never arms
        let mut p = vec![(0, 0, 1, 1); 18];
        p.extend(vec![(0, 0, 0, 0); 10]);
        assert_eq!(run(&p), None);
    }

    #[test]
    fn scenario_b_winning_trade_no_misfire() {
        // a poll inside the landing -> seen gap reads -1.53 with the buy unresolved: not confirmed; next poll +0.05
        let p = vec![(0, 0, 1, 1), (-1_527_600_000, 0, 1, 1), (5 * SOL / 100, 0, 0, 0), (5 * SOL / 100, 5 * SOL / 100, 0, 0)];
        assert_eq!(run(&p), None);
    }

    #[test]
    fn scenario_c_real_loss_kills_with_a_pending_buy() {
        // real -0.6 with a never-landing buy pending: confirmed on the 2nd poll (it was masked ~60 s before)
        let p = vec![(-45 * SOL / 100, 0, 1, 1), (-60 * SOL / 100, 0, 1, 1), (-60 * SOL / 100, 0, 1, 1)];
        assert_eq!(run(&p), Some((2, KsVerdict::Kill)));
        // N2: nothing pending: still 2 consecutive polls (one lagging balance read never kills)
        assert_eq!(run(&[(-60 * SOL / 100, 0, 0, 1)]), None);
        assert_eq!(run(&[(-60 * SOL / 100, 0, 0, 1), (-60 * SOL / 100, 0, 0, 1)]), Some((1, KsVerdict::Kill)));
        // N2: a single false -1.5 right after a sale (balance lagging the proceeds), then the true value: no stop
        assert_eq!(run(&[(5 * SOL / 100, 0, 0, 1), (-145 * SOL / 100, 0, 0, 0), (5 * SOL / 100, 0, 0, 0), (5 * SOL / 100, 0, 0, 0)]), None);
        // realized below the cap: at once (second check)
        assert_eq!(run(&[(0, -60 * SOL / 100, 0, 0)]), Some((0, KsVerdict::KillRealized)));
    }

    #[test]
    fn lock_only_with_nothing_in_flight() {
        // +0.35 arms the break-even floor; a dip to -0.1 while a position is in flight is deferred; once flat: LOCK on the
        // 2nd consecutive evaluated poll below the floor (N2)
        let p = vec![(35 * SOL / 100, 0, 0, 0), (-SOL / 10, 0, 0, 1), (-SOL / 10, 0, 0, 0), (-SOL / 10, 0, 0, 0)];
        assert_eq!(run(&p), Some((3, KsVerdict::Lock)));
        // one poll below the floor, then back above: no lock
        assert_eq!(run(&[(35 * SOL / 100, 0, 0, 0), (-SOL / 10, 0, 0, 0), (SOL / 10, 0, 0, 0), (-SOL / 10, 0, 0, 0)]), None);
        // arming is deferred too while in flight
        assert_eq!(run(&[(35 * SOL / 100, 0, 0, 1), (-SOL / 10, 0, 0, 0)]), None);
    }

    /// N1: a token read is Closed only for a well-formed `value: null` at a context slot >= the required one; anything else
    /// that is not an amount is Unknown (never 0)
    #[test]
    fn tok_parse_n1() {
        use serde_json::json;
        let amt = base64::engine::general_purpose::STANDARD.encode(1234u64.to_le_bytes());
        assert_eq!(tok_parse(&json!({ "context": { "slot": 100 }, "value": { "data": [amt, "base64"] } }), 90), Tok::Amount(1234, 100));
        assert_eq!(tok_parse(&json!({ "context": { "slot": 100 }, "value": null }), 100), Tok::Closed(100));
        // a node behind the required slot (defensive: the RPC normally errors) -> Unknown
        assert_eq!(tok_parse(&json!({ "context": { "slot": 99 }, "value": null }), 100), Tok::Unknown);
        // no context / no value field / bad data -> Unknown
        assert_eq!(tok_parse(&json!({ "value": null }), 0), Tok::Unknown);
        assert_eq!(tok_parse(&json!({ "context": { "slot": 100 } }), 0), Tok::Unknown);
        assert_eq!(tok_parse(&json!({ "context": { "slot": 100 }, "value": { "data": ["AAAA", "base64"] } }), 0), Tok::Unknown);
        assert_eq!(Tok::Closed(5).zero_at(), Some(5));
        assert_eq!(Tok::Amount(0, 6).zero_at(), Some(6));
        assert_eq!(Tok::Amount(1, 6).zero_at(), None);
        assert_eq!(Tok::Unknown.zero_at(), None);
        assert_eq!(Tok::Unknown.amount(), None);
    }

    /// N6: a failed balance read never inflates realized PnL
    #[test]
    fn realized_fallback_n6() {
        assert_eq!(realized_fallback(5_000_000_000, Some(5_050_000_000), 1_527_000_000).0, 50_000_000);
        assert_eq!(realized_fallback(0, Some(5_050_000_000), 1_527_000_000).0, -1_527_000_000);
        assert_eq!(realized_fallback(5_000_000_000, None, 1_527_000_000).0, -1_527_000_000);
    }

    /// N5: unknown / misspelled flags and bad numeric values refuse to start; the exact Run-1 flag set passes
    #[test]
    fn flags_n5() {
        let a = |v: &[&str]| -> Vec<String> { std::iter::once("snipe_engine").chain(v.iter().copied()).map(String::from).collect() };
        assert!(check_flags(&a(&["--snipe-once", "--max-inflight", "2", "--minutes", "180"])).is_ok());
        for bad in [&["--max-buy", "20"][..], &["--max-inflight", "two"], &["--max-inflight", "0"], &["--max-dev-buy-sol", "x"], &["--min-dev-buy", "-5"],
                    &["--minutes", "1.5"], &["--sell-deadline-s"], &["--hold-slots", "--live"], &["--hold-max-ms", "1e3"], &["--land-timeout-ms", ""],
                    &["--late-land-s", "abc"], &["--max-create-ms", "nan"], &["--race-max-bundle-sol", "inf"], &["--race-bundle", "maybe"],
                    &["--sell-cu-limit", "big"], &["--max-loss-sol", "abc"], &["--lock-tiers", "0.3:0,x"], &["--slip-cap-bps", "15000"]] {
            assert!(check_flags(&a(bad)).is_err(), "{bad:?} must refuse to start");
        }
        // the Run-1 command (ops/run1/run1_common.sh FLAGS, with its variables filled in) passes
        let sh = include_str!("../../ops/run1/run1_common.sh");
        let body = &sh[sh.find("FLAGS=(").unwrap() + 7..];
        let body = &body[..body.find(')').unwrap()];
        let mut v: Vec<String> = vec!["snipe_engine".into(), "--snipe-once".into(), "--concurrent".into(), "--live".into()];
        for t in body.split_whitespace() {
            v.push(match t { "$C" => "/root/run1/run1_landing.toml".into(), "\"$ROUTES\"" => "bam=jito-bundle".into(), "$ENV_NAME" => "DEV".into(), t => t.trim_matches('"').to_string() });
        }
        v.extend(["--send-log", "x", "--lat-trace", "y"].map(String::from));
        check_flags(&v).unwrap();
        assert!(v.iter().any(|x| x == "--sell-cu-limit"), "Run 1 sets the sell CU limit explicitly");
        // audit 3: the slot deadline (M-3), the fallback RPC (H-1), 1 s sell re-sends (M-5)
        let val = |f: &str| v.iter().position(|x| x == f).and_then(|i| v.get(i + 1)).cloned();
        assert_eq!(val("--buy-max-slot-delta").as_deref(), Some("1"));
        assert_eq!(val("--rpc-fallback-url-env").as_deref(), Some("RMR_RPC_URL"));
        assert_eq!(val("--sell-retry-s").as_deref(), Some("1"));
        assert_eq!(val("--sell-fallback-path").as_deref(), Some("nozomi"));
        // the dry run and the CU checks
        let mut d = v.clone(); d[3] = "--junk-fanout".into();
        check_flags(&d).unwrap();
        check_flags(&a(&["--simulate", "--sim-as", "x", "--sim-count", "5", "--sim-delay-ms", "1500", "--spend-lamports", "1500000000", "--cu-limit", "95000",
            "--cu-price-micro", "110000000", "--sim-tips", "12000000,1000000,1000000", "--config", "c", "--env-file", "e"])).unwrap();
        check_flags(&a(&["--simulate", "--sim-sell", "--sim-count", "5", "--sim-delay-ms", "3000", "--sell-cu-limit", "120000", "--sell-cu-price-micro", "5000000",
            "--config", "c", "--env-file", "e"])).unwrap();
        check_flags(&a(&["--simulate", "--sim-sell", "--sim-cashback-only", "--sim-count", "2", "--sim-delay-ms", "3000", "--sell-cu-limit", "120000",
            "--sell-cu-price-micro", "5000000", "--config", "c", "--env-file", "e"])).unwrap();
        check_flags(&a(&["--simulate", "--sim-as", "x", "--buy-max-slot-delta", "1", "--cu-limit", "95000"])).unwrap();
        check_flags(&a(&["--sell-held", "m1,m2", "--live", "--rpc-fallback-url-env", "RMR_RPC_URL", "--unsold-retry-s", "5", "--unsold-drain-s", "120"])).unwrap();
        assert!(check_flags(&a(&["--buy-max-slot-delta", "one"])).is_err());
        assert!(check_flags(&a(&["--unsold-retry-s", "x"])).is_err());
    }

    /// M-2: failure classification from the status error, the (guard, buy) ix indices and the Anchor error line
    #[test]
    fn classify_buy_err_m2() {
        use serde_json::json;
        let roles = (Some(4u8), Some(5u8));
        let at = |i: u64, code: u64| json!({ "InstructionError": [i, { "Custom": code }] });
        assert_eq!(classify_buy_err(&at(4, 6000), roles, None), "slot-deadline");
        assert_eq!(classify_buy_err(&at(5, 6002), roles, None), "slippage");
        assert_eq!(classify_buy_err(&at(5, 6003), roles, None), "slippage");
        assert_eq!(classify_buy_err(&at(5, 6040), roles, Some("Program log: AnchorError occurred. Error Code: SlippageExceeded. Error Number: 6040. Error Message: slippage: too few tokens.")), "slippage");
        assert_eq!(classify_buy_err(&at(5, 6002), roles, Some("Program log: AnchorError occurred. Error Code: AccountNotInitialized. Error Number: 3012. Error Message: x.")), "other");
        assert_eq!(classify_buy_err(&at(5, 6017), roles, None), "other");
        assert_eq!(classify_buy_err(&at(5, 6042), roles, None), "slippage"); // L4-1
        assert_eq!(classify_buy_err(&at(5, 6040), roles, None), "slippage");
        assert_eq!(classify_buy_err(&at(2, 6002), roles, None), "other"); // not at the buy (an ATA create, a tip ...)
        assert_eq!(classify_buy_err(&json!({ "InstructionError": [5, "ComputationalBudgetExceeded"] }), roles, None), "other");
        assert_eq!(classify_buy_err(&json!("InsufficientFundsForFee"), roles, None), "other");
        assert_eq!(classify_buy_err(&at(4, 1), (None, Some(5)), None), "other"); // no guard in this tx
    }

    /// M-3: the guard data layout, its place right before the pump buy, the template's deadline patch equals a full
    /// compile, and the largest Run-1 fan-out (4 tips) still fits the 1232-byte packet with the guard
    #[test]
    fn slot_guard_m3() {
        use arbx::fast;
        let g = GuardEnc { disc: 14, op: 5, acct: false };
        let ix = guard_ix_enc(g, 0x0102_0304_0506_0708);
        assert_eq!(ix.program, *LIGHTHOUSE);
        assert!(ix.accounts.is_empty());
        assert_eq!(ix.data, vec![14, 0, 0, 8, 7, 6, 5, 4, 3, 2, 1, 5]);
        assert_eq!(guard_ix_enc(GuardEnc { acct: true, ..g }, 1).accounts.len(), 1);
        let user = pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q");
        let mint = [0x5Au8; 32]; // (not a real account: 4wTV1Ymi... would be pump's Global, a template constant)
        let launch = snipe_build::launch_from_target(mint, pk("9WzDXwBbmkg8ZTbNMqUxvQRAyrZzDsGYdLVL9zYtAWWM"));
        let (ixs, _) = build_buy(user, &launch, None, 1_500_000_000, 777);
        let n = ixs.len();
        let gi = insert_guard(ixs.clone(), g, 1234);
        assert_eq!(gi.len(), n + 1);
        let at = gi.iter().position(|x| x.program == *LIGHTHOUSE).unwrap();
        assert_eq!(gi[at + 1].program, *snipe::PUMP, "the guard sits right before the buy");
        // the template path (probe deadline, patched) == the full compile with the real deadline, for 1..=4 tips
        for ntips in 1..=4usize {
            let tips: Vec<(Pk, u64)> = (0..ntips).map(|i| ([60 + i as u8; 32], 1_000_000)).collect();
            let compile = |dl: u64, ks: &[(Pk, u64)], ls: &Launch, mo: u64| {
                let (ixs, _) = build_buy(user, ls, None, 1_500_000_000, mo);
                let mut v: Vec<build::Ix> = ks.iter().map(|(t, l)| build::transfer_ix(user, *t, *l)).collect();
                v.extend(insert_guard(ixs, g, dl));
                if ks.len() > 2 { lat::bump_cu_limit(&mut v, 300 * (ks.len() as u32 - 2)); }
                build::compile_v0(user, &v, [9u8; 32], &[], &[]).unwrap().bytes
            };
            let real = compile(458_000_001, &tips, &launch, 777);
            assert!(1 + 64 + real.len() <= 1232, "{ntips} tips + guard: {} bytes > 1232", 1 + 64 + real.len());
            eprintln!("M-3 buy tx with {ntips} tip(s) + slot guard: {} bytes (limit 1232)", 1 + 64 + real.len());
            // probe template exactly as Fast::make_template builds it
            let probe = Launch { mint: fast::probe_var(0), bonding_curve: fast::probe_var(1), assoc_bonding_curve: fast::probe_var(2), creator: fast::probe_var(9),
                dev_buy_lamports: 0, is_create_v2: true, is_mayhem: false, is_cashback: false, creator_fee_bps: 0, is_holder_reward: false, buyback_fee_recipient: fast::probe_var(5) };
            let (ixs, _) = build_buy(user, &probe, None, 1_500_000_000, fast::PROBE_MIN_OUT);
            let mut ixs = insert_guard(ixs, g, fast::PROBE_DEADLINE);
            let (p0, p1) = (probe.mint, probe.bonding_curve);
            let map = [(pda::ata(&p1, &p0, &pda::TOKEN_2022), fast::probe_var(2)), (pda::ata(&p1, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), fast::probe_var(3)),
                (pda::ata(&user, &p0, &pda::TOKEN_2022), fast::probe_var(4))];
            for ix in ixs.iter_mut() { for a in ix.accounts.iter_mut() { if let Some((_, to)) = map.iter().find(|(from, _)| *from == a.key) { a.key = *to; } } }
            let mut v: Vec<build::Ix> = tips.iter().enumerate().map(|(i, (_, l))| build::transfer_ix(user, fast::probe_tip(i), *l)).collect();
            v.extend(ixs);
            if ntips > 2 { lat::bump_cu_limit(&mut v, 300 * (ntips as u32 - 2)); }
            let pm = build::compile_v0(user, &v, fast::PROBE_BH, &[], &[]).unwrap();
            let t = fast::Template::from_probe_msg_dl(pm.bytes, ntips, true).unwrap();
            let (bc, abc) = (launch.bonding_curve, launch.assoc_bonding_curve);
            let vars: fast::VarKeys = [mint, bc, abc, pda::ata(&bc, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), pda::ata(&user, &mint, &pda::TOKEN_2022), launch.buyback_fee_recipient];
            let mut out = Vec::new();
            t.patch_dl(&mut out, &vars, &tips.iter().map(|x| x.0).collect::<Vec<_>>(), &[9u8; 32], 777, Some(458_000_001)).unwrap();
            assert_eq!(out, real, "template + deadline patch == full compile ({ntips} tips)");
            assert!(t.patch_dl(&mut out, &vars, &tips.iter().map(|x| x.0).collect::<Vec<_>>(), &[9u8; 32], 777, None).is_none(), "a guarded template needs a deadline");
            // M-2 roles: guard index right before the buy
            let mut raw = vec![1u8]; raw.extend([0u8; 64]); raw.extend(&real);
            let (gr, br) = ix_roles(&raw);
            assert_eq!(gr.map(|x| x + 1), br);
        }
    }

    #[test]
    fn redact_urls_h1() {
        assert_eq!(redact("error sending request for url (https://rpc.example.com/?api-key=SECRET): timed out"), "error sending request for url (<url>): timed out");
        assert_eq!(redact("no url here"), "no url here");
        assert!(!redact("a http://x/y?k=1 b https://z").contains("k=1"));
    }

    /// ALT fix: the real HQ4G6Fjm create of ADkDx1… (slot 459235310, tests/fixtures/alt_hq4g, mainnet bytes): unresolved
    /// it read as a non-SOL quote (skip); with the table cached the quote is WSOL (SOL), the launch decodes with the right
    /// curve, the resolved addresses equal the RPC's loadedAddresses, and the 3 glued legs count as buys (~3.21 SOL)
    #[test]
    fn alt_hq4g_create_resolves() {
        use std::collections::HashMap;
        let b = |s: &str| base64::engine::general_purpose::STANDARD.decode(s.trim()).unwrap();
        let raw = b(include_str!("../../tests/fixtures/alt_hq4g/create.b64"));
        let table = pk("HQ4G6FjmW8yZ15XGoiQdGDvbi5C7fJKktNg6pzCzdHg4");
        let addrs = arbx::tx::parse_alt(&b(include_str!("../../tests/fixtures/alt_hq4g/table_HQ4G6FjmW8yZ15XGoiQdGDvbi5C7fJKktNg6pzCzdHg4.b64"))).unwrap();
        assert_eq!(addrs.len(), 44);
        let (tx0, _) = arbx::tx::parse_wire(&raw).unwrap();
        assert_eq!(tx0.lookups.len(), 1);
        assert_eq!(tx0.lookups[0].table, table);
        // as the raw-shred feed delivers it: unresolved -> the M6 skip (what the server dry run logged)
        assert_eq!(snipe::create_quote_mint(&tx0), Some(snipe::UNRESOLVED_QUOTE));
        // cache states: missing / stale (table shorter than an index) / done
        let mut m: HashMap<Pk, Arc<Vec<Pk>>> = HashMap::new();
        assert_eq!(altc::resolve_with(&tx0, |k| m.get(k).cloned()), altc::Res::Missing(vec![table]));
        m.insert(table, Arc::new(addrs[..20].to_vec()));
        assert_eq!(altc::resolve_with(&tx0, |k| m.get(k).cloned()), altc::Res::Stale(vec![table]));
        m.insert(table, Arc::new(addrs.clone()));
        let altc::Res::Done(loaded) = altc::resolve_with(&tx0, |k| m.get(k).cloned()) else { panic!("resolves") };
        // M5-1: the create is a create candidate (its fetch would be queued); its legs are not creates
        assert!(snipe::is_create_candidate(&tx0));
        // equal to what the RPC itself resolved for this transaction
        let rl: serde_json::Value = serde_json::from_str(include_str!("../../tests/fixtures/alt_hq4g/create_loaded.json")).unwrap();
        let ks = |k: &str| -> Vec<Pk> { rl[k].as_array().unwrap().iter().map(|x| pk(x.as_str().unwrap())).collect() };
        assert_eq!(loaded, (ks("writable"), ks("readonly")));
        let mut tx = tx0.clone();
        tx.loaded = Some(loaded);
        assert_eq!(snipe::create_quote_mint(&tx), None, "the quote resolves to SOL (WSOL)");
        let mint = pk("ADkDx1QYii7DpKgFMBBxCaWg9pwjPY4GYYnz4qnrpump");
        let l = snipe::detect_launch(&tx).expect("the create decodes");
        assert_eq!(l.mint, mint);
        assert!(l.is_create_v2);
        assert_eq!(l.bonding_curve, snipe_build::bonding_curve(&mint));
        assert_eq!(l.assoc_bonding_curve, snipe_build::assoc_bonding_curve(&l.bonding_curve, &mint));
        assert!(l.dev_buy_lamports >= 3_000_000_000 && l.dev_buy_lamports <= 3_200_000_000, "dev ~3.09 SOL: {}", l.dev_buy_lamports);
        // the glued bundle: block index 846-848, all buys of the mint
        let vq = snipe::CURVE_VQ0 + l.dev_buy_lamports;
        let mut legs = Vec::new();
        for line in include_str!("../../tests/fixtures/alt_hq4g/legs.b64").lines().filter(|x| !x.trim().is_empty()) {
            let (lt, _) = arbx::tx::parse_wire(&b(line)).unwrap();
            assert!(!snipe::pump_buy_mint_unresolved(&lt));
            match snipe::bundle_legs(&lt, &mint) { Some(snipe::Legs::Buys(v)) => legs.extend(v), x => panic!("a glued leg must be a buy of the mint: {x:?}") }
        }
        assert_eq!(legs.len(), 3);
        let sol = snipe::simulate_legs(vq, &legs).unwrap() as f64 / 1e9;
        assert!((3.0..3.5).contains(&sol), "glued bundle ~3.21 SOL: {sol}");
        // fill() through the live cache (the event loop's call)
        altc::insert(table, addrs);
        let mut t2 = tx0.clone();
        assert!(altc::fill(&mut t2));
        assert_eq!(snipe::create_quote_mint(&t2), None);
    }

    /// M4-1 (owner): the sell decision -> send path makes NO RPC. With the RPC trap ARMED (any engine RPC read panics) the
    /// whole pre-send work — the sell instructions, the cached blockhash, build + sign for the sell path + the fallback
    /// path — runs and yields the signed tx; the trap itself is proven to panic on an RPC read; a stale cache gives
    /// "needs a refresh" (Err(None)) without fetching. Prints the pre-send time (p50 / p99 over 300 runs).
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn sell_decision_to_send_makes_no_rpc_m41() {
        let _g = BH_GLOBALS.lock().unwrap_or_else(|e| e.into_inner());
        let key = SigningKey::from_bytes(&[7u8; 32]);
        let user = key.verifying_key().to_bytes();
        let cfgs: Vec<config::SendPath> = ["staked-rpc", "nozomi"].iter().map(|name| {
            let mut c: config::SendPath = toml::from_str(&format!("name = \"{name}\"\nkind = \"rpc\"\nurl = \"http://127.0.0.1:1\"")).unwrap();
            c.tip_lamports = c.kind.min_tip();
            c
        }).collect();
        let (paths, _) = send::Paths::new(&cfgs, send::PathsOpts::default(), arbx::rec::Rec::off(), false).await.unwrap();
        let (p1, p2) = (paths.list[0].clone(), paths.list[1].clone());
        *BLOCKHASH_CACHE.lock().unwrap() = Some(([3u8; 32], Instant::now(), 1_000));
        let launch = snipe_build::launch_from_target([0x5Au8; 32], [0x6Bu8; 32]);
        RPC_TRAP.store(true, Ordering::SeqCst);
        tg::TG_TRAP.store(true, Ordering::SeqCst); // Telegram: the same path must never touch it either
        let mut us = Vec::new();
        let mut last = None;
        for i in 0..300u64 {
            let t = Instant::now();
            let ixs = snipe_build::sell_message_ixs(user, &launch, 123_456 + i, 0, 120_000, 5_000_000, false);
            let pre = sell_presend(&key, user, &p1, Some(&p2), &ixs, Duration::from_secs(20)).ok().expect("pre-send from the cache, no RPC");
            us.push(t.elapsed().as_nanos() as u64);
            last = Some(pre);
        }
        let pre = last.unwrap();
        assert_eq!(pre.fan.len(), 2, "sell path + fallback path (M-5)");
        let (tx, _) = arbx::tx::parse_wire(&pre.raw).unwrap();
        assert!(tx.ixs.iter().any(|ix| ix.data.starts_with(&snipe_build::SELL_V3_DISC)));
        assert_eq!(&pre.raw[1..65], &pre.sig_bytes[..]);
        assert!(ed25519_dalek::VerifyingKey::from_bytes(&user).unwrap().verify_strict(&pre.raw[65..], &ed25519_dalek::Signature::from_bytes(&pre.sig_bytes)).is_ok());
        // the trap is live: an engine RPC read on this path panics
        let rpc = rpc::Rpc::new("http://127.0.0.1:1".into());
        let j = tokio::spawn(async move { call2(&rpc, "getSlot", serde_json::json!([])).await }).await;
        assert!(j.is_err_and(|e| e.is_panic()), "an RPC read while the trap is armed must panic");
        let j = tokio::spawn(async move { refresh_blockhash(&rpc::Rpc::new("http://127.0.0.1:1".into()), Duration::from_millis(1)).await }).await;
        assert!(j.is_err_and(|e| e.is_panic()));
        // stale cache: no fetch inside the pre-send, the caller is told to refresh
        *BLOCKHASH_CACHE.lock().unwrap() = Some(([3u8; 32], Instant::now().checked_sub(Duration::from_secs(30)).unwrap(), 1_000));
        let ixs = snipe_build::sell_message_ixs(user, &launch, 1, 0, 120_000, 5_000_000, false);
        assert!(matches!(sell_presend(&key, user, &p1, Some(&p2), &ixs, Duration::from_secs(20)), Err(None)));
        // the Telegram trap is live: a raise while armed panics
        let j = tokio::spawn(async { tg::raise(arbx::alerts::Level::Info, "x", "x", "x", "x", arbx::alerts::format::Body::new(), false) }).await;
        assert!(j.is_err_and(|e| e.is_panic()), "a Telegram raise while the trap is armed must panic");
        tg::TG_TRAP.store(false, Ordering::SeqCst);
        RPC_TRAP.store(false, Ordering::SeqCst);
        us.sort_unstable();
        eprintln!("M4-1 SELL decision->send pre-work (ixs + cached blockhash + build + sign, 2 paths), no RPC: p50 {:.1} us p99 {:.1} us",
            us[us.len() / 2] as f64 / 1e3, us[us.len() * 99 / 100] as f64 / 1e3);
        assert!(us[us.len() / 2] < 5_000_000, "pre-send far slower than expected");
    }

    /// M5-2 / L5-1 / L5-3 (audit 5): the blockhash cache's acceptance rule
    #[test]
    fn pick_blockhash_m52() {
        let feed = 459_000_000u64;
        let off = 21_000_000u64; // honest: ctx - last_valid_height
        let hon = |src: usize, k: u64, h: u8| Cand { h: [h; 32], v: feed + k - off, ctx: feed + k, src };
        let s = Duration::from_secs;
        let new = || BhState::default();
        let p = |st: &mut BhState, c: &[Cand], cached: Option<([u8; 32], Duration, u64)>, since: Duration| pick_blockhash(st, c, feed, feed, cached, since).0;
        // both RPCs agree: learned + accepted; the highest wins
        let mut st = new();
        assert_eq!(p(&mut st, &[hon(0, 0, 1), hon(1, 2, 2)], None, s(9)), Some(hon(1, 2, 2)));
        // plausibility (M7-1a): ctx 0, a height above ctx + 150 (bogus high), u64::MAX ctx, out of the window: rejected
        let mut st = new();
        assert_eq!(p(&mut st, &[Cand { h: [7; 32], v: 5, ctx: 0, src: 0 }, Cand { h: [8; 32], v: feed + 1_000, ctx: feed, src: 1 }], None, s(9)), None);
        assert!(st.offset.is_none());
        assert_eq!(p(&mut st, &[Cand { h: [7; 32], v: 5, ctx: u64::MAX, src: 0 }], None, s(9)), None);
        assert_eq!(p(&mut st, &[Cand { h: [7; 32], v: 5, ctx: feed - 10_000, src: 0 }], None, s(9)), None);
        // PROBE 1 (audit 7): an honest and a bogus-LOW first answer disagree with no offset: NEITHER is accepted, nothing
        // is learned; once they agree again the honest offset is learned
        let mut st = new();
        let low = Cand { h: [9; 32], v: feed - off - 5_000, ctx: feed, src: 1 };
        assert_eq!(p(&mut st, &[hon(0, 0, 1), low], None, s(9)), None);
        assert!(st.offset.is_none());
        assert_eq!(p(&mut st, &[hon(0, 1, 1), hon(1, 1, 2)], None, s(9)).map(|c| c.ctx), Some(feed + 1));
        assert_eq!(st.offset, Some(off as i128));
        // a later bogus-low answer from source 1 is EXCLUDED (logged), the honest one accepted; source 1 RE-ADMITTED when it agrees
        let (c, log) = pick_blockhash(&mut st, &[hon(0, 3, 3), Cand { ctx: feed + 3, ..low }], feed, feed, Some(([2; 32], s(1), feed + 1 - off)), s(1));
        assert_eq!(c, Some(hon(0, 3, 3)));
        assert!(st.excluded[1] && log.iter().any(|l| l.contains("source 1 EXCLUDED")));
        let (_, log) = pick_blockhash(&mut st, &[hon(0, 4, 4), hon(1, 4, 5)], feed, feed, Some(([3; 32], s(1), feed + 3 - off)), s(1));
        assert!(!st.excluded[1] && log.iter().any(|l| l.contains("source 1 RE-ADMITTED")));
        // PROBE 2: a context-less answer while the reference is unknown is rejected (no -height offset learned)
        let mut st = new();
        assert_eq!(pick_blockhash(&mut st, &[Cand { h: [1; 32], v: 400_000_000, ctx: 0, src: 0 }], 0, 0, None, s(9)).0, None);
        assert!(st.offset.is_none() && st.recent[0].is_empty());
        // PROBE 3: gradual drift (100, 200, 300 ... higher than honest, from source 1, with source 0 honest): the drifting
        // answers are above ctx + 150 from the second step on, and never move the offset away from honest
        let mut st = new();
        p(&mut st, &[hon(0, 0, 1), hon(1, 0, 1)], None, s(9));
        for k in 1..6u64 {
            let d = Cand { h: [k as u8 + 20; 32], v: feed + k - off + 100 * k, ctx: feed + k, src: 1 };
            let c = p(&mut st, &[hon(0, k, k as u8 + 40), d], Some(([0; 32], s(1), 0)), s(1)).unwrap();
            assert_eq!(c.src, 0, "step {k}: the honest source keeps winning");
        }
        assert!((st.offset.unwrap() - off as i128).abs() <= 10, "offset stays honest: {:?}", st.offset);
        // single source: learned only after 5 consistent samples; then accepted
        let mut st = new();
        for k in 0..4 { assert_eq!(p(&mut st, &[hon(0, k, 1)], None, s(9)), None); }
        assert_eq!(p(&mut st, &[hon(0, 4, 1)], None, s(9)).map(|c| c.ctx), Some(feed + 4));
        // M7-1c: a wrongly learned offset is RE-LEARNED after 5 s with nothing accepted, from a source consistent over 10
        let mut st = BhState { offset: Some(5), ..Default::default() };
        for k in 0..9 { assert_eq!(p(&mut st, &[hon(0, k, 1)], None, s(6)), None); }
        assert!(p(&mut st, &[hon(0, 9, 1)], None, s(6)).is_some());
        // L6-1: an old cache (> 10 s): the SAME hash never re-stamped; a different FRESH one taken; a stale one not
        let mut st = new();
        p(&mut st, &[hon(0, 0, 1), hon(1, 0, 1)], None, s(9));
        assert_eq!(p(&mut st, &[hon(0, 0, 1), hon(1, 0, 1)], Some(([1; 32], s(30), feed - off)), s(30)), None);
        assert!(p(&mut st, &[hon(0, 0, 2), hon(1, 0, 2)], Some(([1; 32], s(11), feed + 9_999)), s(11)).is_some());
        // L7-4: with the age reference extrapolated past a stale live reference, a 40-slot-old hash is not fresh
        assert_eq!(pick_blockhash(&mut st, &[hon(0, 0, 3), hon(1, 0, 3)], 0, feed + 40, Some(([1; 32], s(11), feed + 9_999)), s(11)).0, None);
    }

    /// M5-1 (audit 5): only relevant txs queue a lookup-table fetch; the LRU evicts the least recently used
    #[tokio::test]
    async fn alt_fetch_relevance_m51() {
        let mk = |table: Pk, create: bool| {
            let mut d = if create { snipe::CREATE_V2_DISC.to_vec() } else { vec![9u8; 8] };
            d.extend([0u8; 16]);
            arbx::tx::Tx { keys: vec![[1u8; 32], *snipe::PUMP], lookups: vec![arbx::tx::Lookup { table, writable: vec![0], readonly: vec![1] }],
                ixs: vec![arbx::tx::Ix { program: 1, accounts: vec![0, 2], data: d }], ..Default::default() }
        };
        let (t_other, t_create) = ([0xA1u8; 32], [0xA2u8; 32]);
        altc::set_watching(false);
        // an unresolved non-create pump tx while nothing is watched: NOT fetched
        assert!(!altc::fill(&mut mk(t_other, false)));
        assert!(!altc::is_queued(&t_other));
        // an unresolved create: queued (once)
        assert!(snipe::is_create_candidate(&mk(t_create, true)));
        assert!(!altc::fill(&mut mk(t_create, true)));
        assert!(altc::is_queued(&t_create));
        // LRU: the oldest last-use go first
        let v = vec![(5, [5u8; 32]), (1, [1u8; 32]), (9, [9u8; 32]), (3, [3u8; 32])];
        assert_eq!(altc::lru_victims(v, 2), vec![[1u8; 32], [3u8; 32]]);
    }

    /// Telegram: the reused sink never blocks (a full queue drops and counts), the token never leaks, the bodies render
    #[test]
    fn telegram_m_tg() {
        use arbx::alerts::{format::Body, Alert, Alerts, Level};
        let token = "1234567890:AAFakeTokenSecretPart_abcdefghijkl";
        let env = |k: &str| match k { "TELEGRAM_BOT_TOKEN" => Some(token.to_string()), "TELEGRAM_CHAT_ID" => Some("-1001234567890".to_string()), _ => None };
        let (a, notes) = Alerts::new(&tg::cfg(), &env, arbx::alerts::Ctx { label: "SNIPER DEV".into(), ..Default::default() });
        assert!(a.enabled(), "{notes:?}");
        assert!(notes.iter().all(|n| !n.contains(token) && !n.contains("AAFakeToken")), "notes never carry the token");
        // never blocks: no sender started, 5,000 distinct alerts into a 1,024 queue
        let t = Instant::now();
        let mut ok = 0;
        for i in 0..5_000 { if a.raise(Alert::new(Level::Info, "snipe_fire", format!("k{i}"), "FIRE").once().body(Body::new().kv("i", i.to_string()))) { ok += 1; } }
        let el = t.elapsed();
        assert!(ok <= 1_024 && ok > 0, "queue bound: {ok}");
        assert!(el < Duration::from_millis(500), "5,000 raises took {el:?}: the sink must never wait");
        let st = a.status_json();
        assert_eq!(st["dropped_total"].as_u64().unwrap() + ok, 5_000);
        assert!(!st.to_string().contains("AAFakeToken"));
        // token redaction (the old bot's redact, and the engine's URL redaction)
        let err = format!("error sending request for url (https://api.telegram.org/bot{token}/sendMessage): timed out");
        assert!(!arbx::alerts::telegram::redact(&err, token).contains("AAFakeToken"));
        assert!(!redact(&err).contains("AAFakeToken"));
        // bodies: links, escaping, fields
        let m = [0x33u8; 32];
        let f = tg::fire_body(&m, 459_000_000, 3_090_000_000, Some(3_210_000_000), "jito<agave>", "bam", 10_500_000, 13_000_000, Some(459_000_001)).html();
        assert!(f.contains("https://solscan.io/token/") && f.contains("3.09") && f.contains("3.21") && f.contains("459000001"), "{f}");
        assert!(f.contains("jito&lt;agave&gt;") && !f.contains("jito<agave>"), "escaped: {f}");
        let e = tg::exit_body(&tg::Exit { mint: m, legs: 2, proceeds: Some(1_600_000_000), pnl: 75_000_000, cost: 1_525_000_000, hold_s: 0.8, dec_send_us: Some(61.0),
            run_pnl: 120_000_000, trades: 3, src: "tx".into() }).html();
        assert!(e.contains("+4.9%") && e.contains("61 µs") && e.contains("0.80 s"), "{e}");
        let end = tg::end_body(&tg::End { fires: 5, landed: 3, wins: 2, losses: 1, net: 100_000_000, usd: Some(150.0), best: Some((m, 90_000_000)), worst: Some((m, -40_000_000)),
            fees: 75_000_000, same_slot_pct: Some(33.3), median_delta: Some(1), reason: "window ended".into(), wallet_net: Some(95_000_000), fees_est: 10_500_000, usd_age_min: Some(4) }).html();
        assert!(end.contains("$+15.00") && end.contains("33%") && end.contains("create +1"), "{end}");
        // M8-2 / L8-3: wallet net next to the trades', estimated fees labelled, a stale SOL price gives no dollar figure
        assert!(end.contains("net (wallet)") && end.contains("+0.095") && end.contains("est"), "{end}");
        let stale = tg::end_body(&tg::End { fires: 1, landed: 1, wins: 1, losses: 0, net: 100_000_000, usd: Some(150.0), best: None, worst: None, fees: 0,
            same_slot_pct: None, median_delta: None, reason: "x".into(), wallet_net: None, fees_est: 0, usd_age_min: Some(45) }).html();
        assert!(stale.contains("stale") && !stale.contains("$+"), "{stale}");
        // --env-name: DEV / PROD only
        let a2 = |v: &[&str]| -> Vec<String> { std::iter::once("e").chain(v.iter().copied()).map(String::from).collect() };
        assert!(check_flags(&a2(&["--env-name", "PROD", "--telegram"])).is_ok());
        assert!(check_flags(&a2(&["--env-name", "STAGING"])).is_err());
        assert!(check_flags(&a2(&["--no-telegram", "--telegram-heartbeat-min", "x"])).is_err());
    }

    /// M8-1 (audit 8), the auditor's probe: a mock RPC at the real slot; the slot reference 1,000 slots AHEAD and stale for
    /// 4 s. Before: the honest blockhash was stored 60 s old and sell_blockhash failed. Now: stored fresh, the sell gets it.
    /// Also: a lone source cannot jump the reference; a second source confirms a jump; birth_lag needs a live reference.
    #[tokio::test(flavor = "multi_thread", worker_threads = 2)]
    async fn slot_ahead_probe_m81() {
        let _g = BH_GLOBALS.lock().unwrap_or_else(|e| e.into_inner());
        // pure parts
        assert_eq!(birth_lag(0, 123), Duration::ZERO);
        assert_eq!(birth_lag(1_000, 990), Duration::from_millis(4_000));
        let a = std::sync::atomic::AtomicU64::new(0);
        JUMP_SLOT.store(0, Ordering::Relaxed); JUMP_SRC.store(0, Ordering::Relaxed);
        slot_note_on(&a, SLOT_SRC_PRIMARY, 459_000_000); // L9-5: the first value alone is held
        assert_eq!(a.load(Ordering::Relaxed), 0);
        slot_note_on(&a, SLOT_SRC_PRIMARY, 459_000_003); // the same source again: still held
        assert_eq!(a.load(Ordering::Relaxed), 0);
        slot_note_on(&a, SLOT_SRC_FEED, 459_000_005); // a second source confirms: applied (the lower: the held first value)
        assert_eq!(a.load(Ordering::Relaxed), 459_000_000);
        slot_note_on(&a, SLOT_SRC_PRIMARY, 459_000_003); // then normal advances
        assert_eq!(a.load(Ordering::Relaxed), 459_000_003);
        slot_note_on(&a, SLOT_SRC_FEED, 459_000_500); // a normal advance (one source is enough once the reference is set)
        assert_eq!(a.load(Ordering::Relaxed), 459_000_500);
        slot_note_on(&a, SLOT_SRC_FEED, 459_100_000); // a lone jump: held
        assert_eq!(a.load(Ordering::Relaxed), 459_000_500);
        slot_note_on(&a, SLOT_SRC_FEED, 459_100_010); // the same source again: still held
        assert_eq!(a.load(Ordering::Relaxed), 459_000_500);
        slot_note_on(&a, SLOT_SRC_FALLBACK, 459_100_020); // another source confirms: applied (the lower of the two)
        assert_eq!(a.load(Ordering::Relaxed), 459_100_000);
        // the probe: a mock JSON-RPC answering getLatestBlockhash / getSlot at the real slot
        let real = 459_235_000u64;
        let off = 21_000_000u64;
        let lst = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
        let port = lst.local_addr().unwrap().port();
        tokio::spawn(async move {
            use tokio::io::{AsyncReadExt, AsyncWriteExt};
            loop {
                let Ok((mut c, _)) = lst.accept().await else { break };
                tokio::spawn(async move {
                    let mut buf = Vec::new();
                    let mut tmp = [0u8; 4096];
                    loop {
                        let n = c.read(&mut tmp).await.unwrap_or(0);
                        if n == 0 { return; }
                        buf.extend_from_slice(&tmp[..n]);
                        let Some(h) = buf.windows(4).position(|w| w == b"\r\n\r\n") else { continue };
                        let head = String::from_utf8_lossy(&buf[..h]).to_ascii_lowercase();
                        let len = head.lines().find_map(|l| l.strip_prefix("content-length:").map(|v| v.trim().parse::<usize>().unwrap_or(0))).unwrap_or(0);
                        if buf.len() < h + 4 + len { continue; }
                        let req: serde_json::Value = serde_json::from_slice(&buf[h + 4..h + 4 + len]).unwrap_or_default();
                        buf.drain(..h + 4 + len);
                        let result = match req["method"].as_str().unwrap_or("") {
                            "getLatestBlockhash" => serde_json::json!({ "context": { "slot": real }, "value": { "blockhash": bs58::encode([7u8; 32]).into_string(), "lastValidBlockHeight": real - off + 150 } }),
                            "getSlot" => serde_json::json!(real),
                            _ => serde_json::Value::Null,
                        };
                        let body = serde_json::json!({ "jsonrpc": "2.0", "id": req["id"].clone(), "result": result }).to_string();
                        let resp = format!("HTTP/1.1 200 OK\r\ncontent-type: application/json\r\ncontent-length: {}\r\n\r\n{body}", body.len());
                        if c.write_all(resp.as_bytes()).await.is_err() { return; }
                    }
                });
            }
        });
        let rpc = rpc::Rpc::new(format!("http://127.0.0.1:{port}"));
        // state: offset learned (honest), the reference 1,000 slots ahead and frozen for 4 s, nothing cached
        *BLOCKHASH_CACHE.lock().unwrap() = None;
        *BH_STATE.lock().unwrap() = BhState { offset: Some(real as i128 - (real - off + 150) as i128), ..Default::default() };
        *BH_LAST_ACCEPT.lock().unwrap() = None;
        send::tpu::SLOT.store(real + 1_000, Ordering::Relaxed);
        *REF_SLOT.lock().unwrap() = (real + 1_000, Instant::now().checked_sub(Duration::from_secs(4)));
        let r = refresh_blockhash(&rpc, Duration::from_secs(2)).await;
        let age = BLOCKHASH_CACHE.lock().unwrap().map(|(_, t, _)| t.elapsed());
        let sb = sell_blockhash(&rpc).await;
        // restore the globals for the other tests
        send::tpu::SLOT.store(0, Ordering::Relaxed);
        *REF_SLOT.lock().unwrap() = (0, None);
        *BH_STATE.lock().unwrap() = BhState::default();
        assert!(matches!(r, Ok(true)), "the honest blockhash is accepted: {r:?}");
        assert!(age.is_some_and(|a| a < Duration::from_secs(2)), "stored FRESH, not back-dated from the frozen reference: {age:?}");
        assert!(sb.is_ok(), "the sell gets a blockhash: {sb:?}");
        *BLOCKHASH_CACHE.lock().unwrap() = None;
    }

    #[test]
    fn slip_cap_min_out_m1() {
        // dev 0.5 + bundle 4 SOL: 85% of the quote for 1.5 SOL net of the 1.25% pump fee on the post-bundle curve
        let vq = snipe::CURVE_VQ0 + 500_000_000 + 4_000_000_000;
        let q = snipe::curve_tokens_out(vq, (1_500_000_000u128 * 10_000 / 10_125) as u64);
        let m = slip_min_out(vq, 1_500_000_000, 1500);
        assert_eq!(m, (q as u128 * 8500 / 10_000) as u64);
        // a bigger bundle (higher curve) -> fewer tokens required; 0 bps -> the whole quote
        assert!(slip_min_out(vq + 1_000_000_000, 1_500_000_000, 1500) < m);
        assert_eq!(slip_min_out(vq, 1_500_000_000, 0), q);
        // the effective price cap: spend / min_out vs the post-bundle spot price ~ 1/0.85 x (incl. own impact + fee)
        let spot = vq as f64 * vq as f64 / (snipe::CURVE_VQ0 as f64 * snipe::CURVE_VT0 as f64);
        let cap_px = 1_500_000_000f64 / m as f64;
        assert!(cap_px / spot > 1.15 && cap_px / spot < 1.30, "cap {:.3}x spot", cap_px / spot);
    }
}

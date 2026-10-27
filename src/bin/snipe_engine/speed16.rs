// ===================================================================================================================
// dip16 (10-25 PKT; owner OK ~19:50 PKT: build the FREE landing-speed engine fixes of the validator-client study,
// ops/dip/speed/clients/CLIENTS.md, action list ops/dip/speed/landing2/CLIENT_ACTIONS.md). EVERY one is OFF without its flag:
// with none of them the engine is dip15 on the wire (dip16_tests: the golden digest of every tx shape) and in its records.
//   C1 --loaded-data-limit BYTES   every BUY carries ComputeBudget SetLoadedAccountsDataSizeLimit(BYTES), as its LAST instruction
//   C3 --log-route-headers         Constant-K's X-CK-Tx-Route answer header per send (FAST-ACK lines; the dip timing records' acks)
//   C4 --window-clock              the dump's leader-window clock in the dip fire / probe / timing (and shadow pick) records
//   B4 --dip-probe-nonce on|ab     landing probes on a durable nonce of the --nonce-fanout pool (ab: both arms on every path)
//   C5 --dip-probe-lock-only on    landing probes that SUCCEED and only write-lock the token's curve accounts (+ --dip-probe-lock-cu N)
// ===================================================================================================================
use super::*;
use std::collections::HashMap;
use std::sync::{Mutex, OnceLock};

// ---- C1: --loaded-data-limit BYTES ----------------------------------------------------------------------------------
// Why (CLIENTS.md §2, §7c; CODE agave cost_model.rs, firedancer fd_pack_cost.h): Agave / Jito / Rakurai / Firedancer rank a tx by
// fee / cost, and the cost carries 8 units per 32 KiB of the REQUESTED loaded-accounts data limit: 16,384 for the 64 MiB default.
// MEASURED 10-25 (dip16_loaded_data_sim_onchain: read-only simulateTransaction of our buy shapes on live tokens, node 4.3.2): our buy
// loads 12,513,940..12,520,412 bytes (3 runs, 9 tokens; SIMD-0186: 64 + data per account key + the programdata of every upgradeable program among them:
// pump 10 MiB, Token-2022 1.38 MB, Lighthouse 0.42 MB, Token 0.11 MB, ATA 0.11 MB; the token's own accounts ~2 KB; a nonce variant
// +6 KB). So the floor is ~383 pages (3,064 units), not ~0: the gain is ~11% at 16 MiB (CU limit 100k), not the study's 14%.
// A limit below the real size FAILS the tx (MaxLoadedAccountsDataSizeExceeded, fee paid): values under LL_MIN are refused, and the
// start-up check reads the fixed accounts' sizes on chain (fail closed). The ix goes LAST: no instruction index moves, so the
// guard / buy / tip indices in on-chain errors (classify_buy_err, pre-send classify, the ops scripts) stay dip15's.

/// the smallest limit the engine accepts: 13 MiB = 8.9% above the largest measured buy (12,520,412 B)
pub const LL_MIN: u64 = 13 << 20;
/// the runtime's maximum (and default) limit, 64 MiB
pub const LL_MAX: u64 = 64 << 20;
/// the start-up check: the limit must exceed the buy's fixed accounts (read on chain) by this much (the token's own accounts,
/// the tips, a nonce account and the RecentBlockhashes sysvar are ~8 KB in all, measured)
pub const LL_PER_TX: u64 = 64 << 10;
static LOADED_LIMIT: OnceLock<u32> = OnceLock::new();

/// the limit every buy carries (None: off, dip15)
#[inline]
pub fn loaded_limit() -> Option<u32> { LOADED_LIMIT.get().copied() }

/// --loaded-data-limit's value: LL_MIN..=LL_MAX bytes, else refused (a too-small limit fails every buy)
pub fn ll_check(v: u64) -> Result<u32> {
    if v < LL_MIN { bail!("--loaded-data-limit {v}: below {LL_MIN} (13 MiB). Our buy loads ~12.52 MB (pump's programdata alone is 10 MiB): every buy would fail with MaxLoadedAccountsDataSizeExceeded"); }
    if v > LL_MAX { bail!("--loaded-data-limit {v}: above the runtime's 64 MiB maximum (= the default: no gain)"); }
    Ok(v as u32)
}

/// C1: append SetLoadedAccountsDataSizeLimit(`ll`) (None: nothing, dip15). LAST, so no other instruction's index moves
#[inline]
pub fn add_ll(ixs: &mut Vec<build::Ix>, ll: Option<u32>) { if let Some(b) = ll { ixs.push(build::loaded_data_limit_ix(b)); } }

/// the cost-model units of a requested loaded-data limit: 8 per 32 KiB page, rounded up (Agave cost_model.rs
/// calculate_loaded_accounts_data_size_cost; Firedancer fd_pack_cost.h)
pub fn ll_cost(bytes: u64) -> u64 { bytes.div_ceil(32 * 1024) * 8 }

/// the Agave / Firedancer priority of a tx: reward (100% of the priority fee + 50% of the 5,000 base fee) x 1e6 / (cost + 1), cost =
/// 720 per signature + 300 per writable account + instruction data bytes / 4 + the requested CU limit + the loaded-data cost
/// (CODE agave core/src/transaction_priority.rs, cost-model/src/cost_model.rs; the gain of C1 is the ratio of two of these)
pub fn priority(cu_limit: u64, cu_price: u64, writable: u64, ix_data_bytes: u64, loaded_limit: u64) -> f64 {
    let reward = (cu_limit as u128 * cu_price as u128).div_ceil(1_000_000) as f64 + 2_500.0;
    let cost = 720 + 300 * writable + ix_data_bytes / 4 + cu_limit + ll_cost(loaded_limit);
    reward * 1e6 / (cost + 1) as f64
}

/// the buy's accounts that do not depend on the token (+ the nonce variant's RecentBlockhashes sysvar): their programdata is
/// read too. The token's own accounts, the tips and the nonce account are the LL_PER_TX allowance
fn ll_fixed_accounts() -> Vec<Pk> {
    vec![*snipe::PUMP, *pda::TOKEN_2022, *pda::TOKEN_PROGRAM, *pda::ATA_PROGRAM, *LIGHTHOUSE, *pda::SYSTEM_PROGRAM, arbx::tx::COMPUTE_BUDGET,
         *snipe_build::GLOBAL, *snipe_build::FEE_CONFIG, *snipe_build::EVENT_AUTHORITY, *snipe_build::WSOL, *snipe::DEFAULT_BUYBACK,
         pk("SysvarRecentB1ockHashes11111111111111111111")]
}

/// SIMD-0186 sizes from getMultipleAccounts answers: 64 + `space` per account; the programdata addresses of the upgradeable
/// programs among them (their account data: u32 tag 2 + the address) -> (bytes, [(programdata, program)], rows for the log)
pub fn ll_sum(keys: &[Pk], vals: &[serde_json::Value]) -> (u64, Vec<(Pk, Pk)>, Vec<(u64, String)>) {
    use base64::Engine as _;
    let (mut sum, mut pd, mut rows) = (0u64, Vec::new(), Vec::new());
    for (k, a) in keys.iter().zip(vals) {
        if a.is_null() { continue; }
        let space = a["space"].as_u64().unwrap_or(0);
        sum += 64 + space;
        rows.push((64 + space, b58(k)));
        if a["owner"].as_str() == Some("BPFLoaderUpgradeab1e11111111111111111111111") {
            if let Some(d) = a["data"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok()).filter(|d| d.len() >= 36 && d[..4] == [2, 0, 0, 0]) {
                pd.push((d[4..36].try_into().unwrap(), *k));
            }
        }
    }
    (sum, pd, rows)
}

/// C1 START-UP CHECK (fail closed; read-only: two getMultipleAccounts): the buy's fixed accounts + their programdata, as the runtime
/// counts them; the limit must exceed that by LL_PER_TX. -> the log line
pub async fn ll_verify(rpc: &rpc::Rpc, limit: u32) -> Result<String> {
    let keys = ll_fixed_accounts();
    let ks: Vec<String> = keys.iter().map(b58).collect();
    let v = rpc.call("getMultipleAccounts", serde_json::json!([ks, { "encoding": "base64", "dataSlice": { "offset": 0, "length": 36 }, "commitment": "confirmed" }])).await
        .map_err(|e| anyhow::anyhow!("getMultipleAccounts: {}", redact(&format!("{e:#}"))))?;
    let vals = v["value"].as_array().cloned().unwrap_or_default();
    if vals.len() != keys.len() || vals.iter().take(4).any(|x| x.is_null()) { bail!("the programs' accounts did not come back ({} of {})", vals.len(), keys.len()); }
    let (mut sum, pd, mut rows) = ll_sum(&keys, &vals);
    if pd.len() < 3 { bail!("only {} upgradeable programs found (pump, Token-2022, Lighthouse expected)", pd.len()); }
    let pks: Vec<String> = pd.iter().map(|x| b58(&x.0)).collect();
    let v2 = rpc.call("getMultipleAccounts", serde_json::json!([pks, { "encoding": "base64", "dataSlice": { "offset": 0, "length": 0 }, "commitment": "confirmed" }])).await
        .map_err(|e| anyhow::anyhow!("getMultipleAccounts (programdata): {}", redact(&format!("{e:#}"))))?;
    for ((_, prog), a) in pd.iter().zip(v2["value"].as_array().cloned().unwrap_or_default()) {
        let Some(space) = a["space"].as_u64() else { bail!("the programdata of {} did not come back", b58(prog)) };
        sum += 64 + space;
        rows.push((64 + space, format!("programdata of {}", &b58(prog)[..8])));
    }
    rows.sort_by(|a, b| b.0.cmp(&a.0));
    let need = sum + LL_PER_TX;
    let top = rows.iter().take(3).map(|(b, n)| format!("{n} {:.2} MB", *b as f64 / 1e6)).collect::<Vec<_>>().join(", ");
    if (limit as u64) < need {
        bail!("--loaded-data-limit {limit}: the buy's fixed accounts load {sum} B on chain now ({top}); with the token's own accounts it needs >= {need}: every buy would fail");
    }
    // the gain on the fee / cost schedulers for a 3-tip buy at this run's CU limit and price (11 write locks, 89 + 5 data bytes)
    let (cu, price) = (arg_u64("--cu-limit", 120_000) + 300, arg_u64("--cu-price-micro", 3_000_000));
    let gain = priority(cu, price, 11, 94, limit as u64) / priority(cu, price, 11, 89, LL_MAX) - 1.0;
    Ok(format!("LOADED-DATA-LIMIT {limit} B ({:.2} MiB) checked on chain: the buy's fixed accounts load {sum} B ({top}); headroom {:.2} MB; its priority cost {} \
                vs 16384 at the 64 MiB default: +{:.1}% priority on Agave / Jito / Firedancer for a 3-tip buy at CU {cu} x {price} uL (every buy carries \
                SetLoadedAccountsDataSizeLimit as its last instruction)",
        limit as f64 / 1048576.0, (limit as u64 - sum) as f64 / 1e6, ll_cost(limit as u64), gain * 100.0))
}

/// C1 at start: --loaded-data-limit BYTES checked (range, then on chain) and set before any buy template is built; nothing without it
pub async fn ll_setup(rpc: &rpc::Rpc) -> Result<()> {
    let Some(v) = arg_u64_opt("--loaded-data-limit") else { return Ok(()) };
    let b = ll_check(v)?;
    let line = ll_verify(rpc, b).await.context("--loaded-data-limit (fail closed)")?;
    eprintln!("{line}");
    if LOADED_LIMIT.set(b).is_err() { bail!("--loaded-data-limit set twice"); }
    Ok(())
}

// ---- C3: --log-route-headers ----------------------------------------------------------------------------------------
// Why (CLIENTS.md §8 X2, §7b "staked-rpc lands mostly failures / late"): Constant-K names the route of every send in its answer's
// X-CK-Tx-Route header; over the plan's staked sends per second it silently falls back to its own node and rebroadcasts every 420 ms.
// FAST path: the connection's reader thread keeps the header (arbx::fast::ROUTE_HDRS) -> FAST-ACK lines `ck_route=` and the send
// log's fast_ack `ck_route`; the async sends already print it (send::Path::deliver: "route=" in SEND-ACK). The dip records: every
// answer of a fire / probe (status, ms, route; every HTTP path: Helius' 429s too) is kept by its write tag until the fire's timing
// record takes it (`acks`), and the fire / probe records carry the tag. Nothing on the write path.

/// --log-route-headers is on
#[inline]
pub fn route_on() -> bool { arbx::fast::ROUTE_HDRS.load(Ordering::Relaxed) }

/// at start (before the fast connections): --log-route-headers
pub fn route_setup() {
    if has("--log-route-headers") {
        arbx::fast::ROUTE_HDRS.store(true, Ordering::Relaxed);
        eprintln!("ROUTE-HEADERS: every HTTP answer's X-CK-Tx-Route (Constant-K's route) and status per send: FAST-ACK ck_route=, the dip timing records' acks");
    }
}

/// a fire's answers by its write tag (at most ACKS_KEEP tags; the oldest go)
static ACKS: std::sync::LazyLock<Mutex<(HashMap<u64, Vec<serde_json::Value>>, std::collections::VecDeque<u64>)>> = std::sync::LazyLock::new(Default::default);
const ACKS_KEEP: usize = 4096;

/// one answer of write tag `tag` (the fast-acks thread / an async send's task): kept for the dip timing record. Only with C3 on
#[inline]
pub fn note_ack(tag: u64, path: &str, status: Option<u16>, ms: f64, route: Option<&str>) {
    if !route_on() || tag == 0 { return; }
    keep_ack(tag, path, status, ms, route);
}

/// the store behind note_ack (no flag check: the tests' entry)
pub fn keep_ack(tag: u64, path: &str, status: Option<u16>, ms: f64, route: Option<&str>) {
    let mut g = ACKS.lock().unwrap_or_else(|e| e.into_inner());
    let (m, order) = &mut *g;
    let e = m.entry(tag).or_insert_with(|| { order.push_back(tag); Vec::new() });
    e.push(serde_json::json!({"path": path, "status": status, "ms": (ms * 1000.0).round() / 1000.0, "ck_route": route}));
    while order.len() > ACKS_KEEP { if let Some(k) = order.pop_front() { m.remove(&k); } }
}

/// the answers kept for `tag` (taken)
pub fn take_acks(tag: u64) -> Option<Vec<serde_json::Value>> {
    let mut g = ACKS.lock().unwrap_or_else(|e| e.into_inner());
    let (m, order) = &mut *g;
    let v = m.remove(&tag)?;
    order.retain(|&k| k != tag);
    Some(v)
}

/// the Constant-K route an async send's answer carries (send::Path::deliver appends " route=<header>" to the reply)
pub fn reply_route(reply: &str) -> Option<&str> { reply.rsplit_once(" route=").map(|x| x.1.trim()).filter(|x| !x.is_empty()) }

// ---- C4: --window-clock (log only) ----------------------------------------------------------------------------------
// Why (CLIENTS.md §2 "Slot timing", §3 J4; CODE agave block_creation_loop.rs:455-461): under Alpenglow block k (1..4) of a leader's
// 4-slot window records until 200 ms x k - 56 ms after the window's start: 144 / 344 / 544 / 744 ms. A dump in window slot 1 leaves
// < 144 ms for our buy to make its block: a "spill" there is structural, not the path's fault. The window start is the first arrival
// of anything of the window's first slot on ANY of our feeds (arbx::feeds::slot_first; the PoH hash count is no clock since
// Alpenglow: FIXES.md D1). Fields ("win"): idx (slot % 4: the window starts at slot % 4 == 0, epochs are multiples of 4 slots),
// deadline_ms, the window's / the dump slot's first arrival, and ms since the window start at the dump's first sighting, at the
// executed feed's arrival, at our decision and at our first write, with the ms LEFT in the dump's block at the decision and first write.

/// the end of block `idx` (0-based in its window) after the window starts, ms (Alpenglow; 200 ms slots)
pub fn deadline_ms(idx: u64) -> f64 { 200.0 * (idx + 1) as f64 - 56.0 }

/// C4 is on (--window-clock); the feeds' slot first-arrival table is started by `window_setup`
pub fn window_on() -> bool { arbx::feeds::SLOT_FIRST_ON.load(Ordering::Relaxed) }

/// at the dip engine's start (before the feeds): --window-clock
pub fn window_setup() {
    if has("--window-clock") {
        arbx::feeds::slot_first_on();
        eprintln!("WINDOW-CLOCK: fire / probe / timing records carry the dump's leader-window clock (window slot, block deadline 144/344/544/744 ms, ms left at decision and first write)");
    }
}

/// the window fields from the clocks (pure: unit-tested). `w0_rx` / `slot_rx`: the first arrival of the window's first slot / of the
/// dump's slot; `t_*`: realtime ns (None: not known)
pub fn window_core(slot: u64, w0_rx: Option<u64>, slot_rx: Option<u64>, t_first: Option<u64>, t_dump_rx: u64, t_dec: Option<u64>, t_write: Option<u64>) -> serde_json::Value {
    let idx = slot % 4;
    let dl = deadline_ms(idx);
    let r3 = |x: f64| (x * 1000.0).round() / 1000.0;
    let ms = |t: u64, base: u64| r3((t as i64 - base as i64) as f64 / 1e6);
    let mut j = serde_json::json!({"idx": idx, "w0": slot - idx, "deadline_ms": dl, "w0_rx": w0_rx, "slot_rx": slot_rx});
    if let Some(w) = w0_rx {
        if let Some(t) = t_first { j["first_ms"] = serde_json::json!(ms(t, w)); }
        j["dump_ms"] = serde_json::json!(ms(t_dump_rx, w));
        if let Some(t) = t_dec { let m = ms(t, w); j["dec_ms"] = serde_json::json!(m); j["left_ms_dec"] = serde_json::json!(r3(dl - m)); }
        if let Some(t) = t_write { let m = ms(t, w); j["write_ms"] = serde_json::json!(m); j["left_ms_write"] = serde_json::json!(r3(dl - m)); }
    }
    if let (Some(s), Some(t)) = (slot_rx, t_first.or(Some(t_dump_rx))) { j["in_slot_ms"] = serde_json::json!(ms(t, s)); }
    j
}

/// how many slots right before `slot` share its leader in the leader book (Alpenglow windows: = slot % 4 unless the leader has
/// back-to-back windows); None without the book
fn book_idx(slot: u64) -> Option<u64> {
    let (l, _) = lat::leader_of(slot)?;
    let mut n = 0;
    while n < 8 && slot > n && lat::leader_of(slot - n - 1).is_some_and(|(x, _)| x == l) { n += 1; }
    Some(n)
}

/// C4: the "win" record of a dump in `slot` (the feeds' first arrivals looked up now; off the write path)
pub fn window_json(slot: u64, t_first: Option<u64>, t_dump_rx: u64, t_dec: Option<u64>, t_write: Option<u64>, names: &[String]) -> serde_json::Value {
    let idx = slot % 4;
    let w0 = arbx::feeds::slot_first(slot - idx);
    let s = arbx::feeds::slot_first(slot);
    let mut j = window_core(slot, w0.map(|x| x.0), s.map(|x| x.0), t_first, t_dump_rx, t_dec, t_write);
    if let Some((_, f)) = w0 { j["w0_feed"] = serde_json::json!(names.get(f as usize).cloned().unwrap_or_else(|| f.to_string())); }
    if let Some(b) = book_idx(slot) { j["book_idx"] = serde_json::json!(b); }
    j
}

/// the first write of a fire (its "written" writes' end, monotonic ns) on the realtime clock of the feeds' arrivals
pub fn first_write_rt(w: &[(String, &'static str, u64, u64, &'static str)]) -> Option<u64> {
    let t = w.iter().filter(|x| x.4 == "written").map(|x| x.3).min()?;
    let off = arbx::feeds::clock::now_ns() as i64 - arbx::fast::mono_ns() as i64;
    Some((t as i64 + off) as u64)
}

// ---- B4: --dip-probe-nonce on|ab ------------------------------------------------------------------------------------
// Why (CLIENTS.md §0 "All clients" 4, §8b; CLIENT_ACTIONS B4): Nozomi's docs say builders "may deprioritize durable-nonce
// transactions"; nozomi is our main BAM / Harmonic path and our buys go out on a durable nonce (--nonce-fanout). dip15's probes are
// recent-blockhash txs (prepare_on): they are the no-nonce arm. This flag adds the nonce arm: a probe built as a buy's variant on a
// nonce of the pool (AdvanceNonceAccount first, its path's one tip; still min_out = u64::MAX, so it can never fill; a probe that
// lands advances its nonce and the pool reads it back as for a buy). on = every probe; ab = alternating in blocks of the
// --dip-probe-paths rotation, so every path gets both arms under the same conditions. No nonce ready -> that probe is a recent-blockhash
// one ("nonce_fallback" in its record). Probes only: the buys are unchanged.

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProbeNonce { Off, On, Ab }

impl ProbeNonce {
    /// --dip-probe-nonce off|on|ab (absent: off)
    pub fn parse(argv: &[String]) -> Result<ProbeNonce> {
        let v = argv.iter().position(|x| x == "--dip-probe-nonce").map(|i| argv.get(i + 1).cloned().unwrap_or_default());
        Ok(match v.as_deref() { None | Some("off") => ProbeNonce::Off, Some("on") => ProbeNonce::On, Some("ab") => ProbeNonce::Ab, Some(x) => bail!("--dip-probe-nonce {x}: off | on | ab") })
    }
    /// probe number `k` (0-based) on a rotation of `n_paths` paths goes on a nonce
    pub fn arm(self, k: u64, n_paths: usize) -> bool {
        match self { ProbeNonce::Off => false, ProbeNonce::On => true, ProbeNonce::Ab => (k / n_paths.max(1) as u64) % 2 == 1 }
    }
}

// ---- C5: --dip-probe-lock-only on -----------------------------------------------------------------------------------
// Why (CLIENTS.md §0 "All clients" 1, §8 C7, X1): dip15's probe (min_out = u64::MAX) always FAILS, so it can never land through a
// revert-protected path (Jito bundles, Helius Sender Max's Jito leg, nozomi's builder leg, DBI): those paths cannot be ranked. A
// lock-only probe always SUCCEEDS and conflicts like our buy: one System transfer of 0 lamports from the wallet to the wallet whose
// account list also carries the token's curve accounts WRITABLE (bonding curve, its two token accounts, the buyback fee recipient: the
// buy's write locks that are not ours) and the pump program read-only (so our feeds, which follow the pump program, see it land).
// Nothing reads or writes them: no token and no SOL moves but the fee and the path's tip (dip16_tests::dip16_loaded_data_sim_onchain: read-only
// simulation on live curves: err null, only the System and ComputeBudget programs run, every curve account byte-identical, the wallet
// down by exactly fee + tips). COST: a landed lock probe PAYS ITS PATH'S TIP (it succeeds): ~0.001 SOL on tipped paths (vs ~0.0005 for
// dip15's failing probe, tips reverted), ~0.00002 on tipless ones; so it needs --dip-probe-paths (one path, one tip family per probe:
// refused without). MEASURED 10-25 (5 curves): 1,050 CU with 3 tips, 600 tipless. Ranking caveat: its CU limit (--dip-probe-lock-cu, default 3000)
// at the buy's CU price gives it the buy's per-CU rank (BAM, Harmonic) but a lower fee / cost rank on Agave / Firedancer
// (CLIENTS.md §1): set --dip-probe-lock-cu 100000 for the buy's exact priority (and its priority fee).

/// --dip-probe-lock-only on|off (absent: off)
pub fn lock_only_flag(argv: &[String]) -> Result<bool> {
    let v = argv.iter().position(|x| x == "--dip-probe-lock-only").map(|i| argv.get(i + 1).cloned().unwrap_or_default());
    Ok(match v.as_deref() { None | Some("off") => false, Some("on") => true, Some(x) => bail!("--dip-probe-lock-only {x}: on | off") })
}

/// the lock-only probe's CU limit (--dip-probe-lock-cu, 1,000..=1,400,000; default 3,000: its ~1,200 CU with 4 tips, measured)
pub fn lock_cu() -> u32 { arg_u64("--dip-probe-lock-cu", 3_000).clamp(1_000, 1_400_000) as u32 }

/// the accounts a lock-only probe write-locks: the buy's writable accounts that are not the wallet's (bonding curve, its base and
/// quote token accounts, the buyback fee recipient)
pub fn lock_accounts(l: &Launch) -> [Pk; 4] {
    let bc = l.bonding_curve;
    [bc, if l.is_create_v2 { l.assoc_bonding_curve } else { pda::ata(&bc, &l.mint, &pda::TOKEN_2022) }, pda::ata(&bc, &snipe_build::WSOL, &pda::TOKEN_PROGRAM), l.buyback_fee_recipient]
}

/// C5: a lock-only probe's instructions: the tips first (as the buy), CU limit, CU price, the 0-lamport self-transfer carrying the
/// lock accounts (writable) and the pump program (read-only), then C1's limit when on
pub fn lock_probe_ixs(user: Pk, l: &Launch, tips: &[(Pk, u64)], cu_limit: u32, cu_price: u64, ll: Option<u32>) -> Vec<build::Ix> {
    let mut v: Vec<build::Ix> = tips.iter().map(|(t, a)| build::transfer_ix(user, *t, *a)).collect();
    v.push(build::cu_limit_ix(cu_limit));
    if cu_price > 0 { v.push(build::cu_price_ix(cu_price)); }
    let mut t = build::transfer_ix(user, user, 0);
    for k in lock_accounts(l) { t.accounts.push(build::Meta { key: k, signer: false, writable: true }); }
    t.accounts.push(build::Meta { key: *snipe::PUMP, signer: false, writable: false });
    v.push(t);
    add_ll(&mut v, ll);
    v
}

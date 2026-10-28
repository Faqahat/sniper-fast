// =====================================================================================================================
// PRE-SEND LIVE (--presend-live; owner GO 10-25 ~07:05 PKT "ok lets do the real test"; ops/strategies/presend/LIVE.md).
// A small, capped LIVE probe of the study's pre-sent conditional buy (trigger T2 "whale buy"). Its job is to MEASURE where
// cheap pre-sent attempts land relative to the dump (ms after the crossing trade, block position, ahead of / behind the
// "instant" bots), the real fill rate, costs per fill and P&L, next to the shadow's rows a / b / c (--presend-shadow, needed).
//   * ARMING: the shadow's T2 rules (arbx::presend_live::Detector), decided on the live feed as trades arrive (the shadow works
//     2 slots late, sorted); every trigger is matched with the shadow's presend_arm (presend_live_parity records). The window:
//     from trigger + --presend-live-ms (50) to the trigger's block-clock slot + --presend-window-slots (10), or 30 ms after the
//     whale's first sell, or a fill. Create-slot triggers (the create's signer in its own create tx) are skipped unless
//     --presend-live-create-slot on. One window per token; none while we hold the token, nor until our sell + 300 ms.
//   * ATTEMPTS (a sender THREAD: never the event loop): k per slot, evenly spaced; each a separately signed tx on a recent cached
//     blockhash: CU limit + price, the Lighthouse slot deadline (min(slot + N, the window's last slot)), a NON-idempotent
//     Token-2022 ATA create (double-fill guard), the WSOL ATA (idempotent), the pump buy (spend = size, min tokens out at the
//     latest price x (1 - drop)), one tip to that attempt's path (reverted with a failed attempt). Paths per leader client
//     (--presend-live-routes), separate [[send]] entries from every reactive / sell path (refused otherwise), a global and a
//     per-path rate cap; LOWEST priority: paused while a reactive position is open (--presend-live-one-position on).
//   * FILLS: our buy TradeEvent with an attempt's signature (executed feed) opens a position; the window stops; the reactive bot
//     skips the token while it is held (and while attempts are armed / in flight on it). Exit the shadow's way: sell when the
//     feed reaches entry slot + --presend-exit-slots (2), or at once on a +--presend-tp / -(--presend-sl) value; the engine's
//     sell loop (sell_until_zero). An unexpected fill (any attempt's signature) is tracked and exited the same way; a window
//     whose attempts were not all seen is checked on the token account (RPC) and a held balance is sold.
//   * CAPS (refused without): --presend-live-max-fills N, --presend-live-fee-budget-sol X (fees of failed attempts); the run's
//     kill switch sees every lamport (balance based) and stops the stream with the reactive bot.
//   * RECORDS (--dip-log): presend_live_arm / _skip / _disarm / _parity, presend_attempt (each send), presend_attempt_land (each
//     attempt's result: ok / 6042 / deadline / ata_exists / other / unseen, fee, slot, block index, ms after the crossing trade
//     and the dump on the feed clock, the block-position clock and PoH, the trades between the dump and our tx, the instant
//     bots), presend_live_fill / _exit / _sell_land / _close / _realized / _tape; totals in the 60 s status line and run_end.
//   * dip19 (10-26 PKT; FRA run 22 w51, MEASURED: fill A in slot 461415576, a same-slot stop-loss sold it AND CLOSED the token
//     account, attempt B of the next slot then passed its NON-idempotent ATA create and bought 11.8T tokens again; B was merged into
//     the position whose sell was already done, the Sold message closed it, B's tokens were never sold; realized counted A's buy
//     only (-0.084 SOL vs about -0.48 real); a FILLED window was never re-checked):
//       1. every pre-send sell KEEPS the token account open (SellOpts::keep_ata: sells the whole balance, no close): it is the
//          attempts' double-fill guard. It is closed later (rent back) only after a CONFIRMED 0 read, once no attempt of the mint
//          can land (its quiet slot = the last deadline, incl. an attempt built as its window was disarmed, + 2 slots), with no
//          window armed and no position open on it; a balance there instead = an ORPHAN (2). While it is open no window arms on
//          the mint ("blocked_ata_open": every attempt would fail at its ATA create);
//       2. a fill on a position whose exit has started is never merged into the sell under way: it is that position's next sell
//          ROUND (its own sell once the round under way finishes; a buy that landed at or before that round's confirmed-0 read
//          was sold with it). EVERY window (filled or not) gets a confirmed balance read once it settles: tokens with no
//          position open = ORPHAN (log + record + Telegram critical, a recovery position sold at once); an unreadable balance
//          is retried, never read as 0;
//       3. a position's realized P&L counts every buy (each buy tx's payer delta: spend, fees, tips, rent) and every sell of
//          every round; the curve P&L the same way (all buys' SOL in, all sells' SOL out); the records list every buy signature;
//       4. the run's end (end_drain): every mint pre-send filled / found holding / left open / never read definitely gets a
//          CONFIRMED read: a balance is sold (the drain), an empty account closed, anything left HELD-AT-EXIT (Telegram,
//          --sell-held command), as the reactive bot's EXIT CHECK.
//     The chain work (sells, reads, closes, realized lookups, Telegram) goes through Cmd: spawned at once in a run; queued in the
//     tests, which play the chain's answers back (dip19_tests.rs). Nothing changes without --presend-live.
//   * dip20 QUIET (owner 10-27 ~13:30 PKT "implement QUIET in engine"; research ops/strategies/presend/filter/REPORT.md, pure parts in
//     src/presend_quiet.rs). Every part is OFF unless its flag is given; with none of them nothing of it runs (`qt` None):
//       --presend-live-quiet-stop N:M (owner 6:2): per trigger, the trades by any wallet but the whale's and ours after it ("others",
//         the feed's order); once the slot clock (the attempts' own: max(feed, TPU)) reaches trigger slot + N with others < M, the
//         armed window is disarmed "quiet" (no more attempts). Counted in the trade-ingest path, decided in tick(): never between an
//         attempt's decision and its send (the sender thread is not touched)
//       --presend-live-quiet-skip on: a trigger that would arm is skipped "quiet" when all four signals hold (since_last >= 1, no
//         cohort wallet (--dip-cohort) holding it, < 2 follower bots (--presend-live-fbots FILE) ever on it, the whale's dumps of the
//         last --presend-live-quiet-hist-h hours (24) drew < --presend-live-quiet-fol (2.24) buyers, or none); the whale DumpBook is
//         fed every trade (O(1)); the arm rule waits --presend-live-quiet-warmup-min (60) after the start (the book starts empty),
//         less what --presend-live-quiet-preload DIR|current_run brought in (the 24/7 raw recording, read in a background thread)
//       records: presend_live_arm / _skip / _disarm get "quiet" (the signals) and quiet_skip / quiet_stop; the shadow's presend_arm
//         and presend_disarm get what QUIET would have decided ("quiet"); the status line and run_end get the counters
//   * dip23 QUIET v2 (owner OK 10-28 23:35 PKT; ops/strategies/presend/filter/QUIET2.md §5.2, pure part pq::V2Ring): LOG-ONLY.
//       --presend-live-quiet-v2-log: every pre-send live ARM and SKIP record (and the shadow's presend_arm when QUIET is on) gets
//         "v2": {n_tr_60s, at_120s_high, maxdd_120s, skip, n_120s, ring_s} = the study's candidate rule at the trigger (trades of the
//         token in the last 60 s, the trigger's pre-trade price within 0.1% of the 120 s high, the drawdown from that high; skip =
//         n_tr_60s <= 6 AND at the high), computed from a per-token 120 s ring of (feed arrival time, post-trade price) fed AFTER each
//         trade's trigger decision (causal: only trades strictly before the trigger). NEVER acted on: no arm, skip, attempt or exit
//         changes; the status line and run_end count the arms / skips with v2.skip true / false. Without the flag: no ring, no field
//         (dip22's records byte for byte).
//   * dip24 LIMITS (owner 10-29 02:10 PKT "remove any hard limits on fills, run time etc. - we can afford week-long runs"):
//       --presend-live-max-fills is optional: absent or 0 = unlimited (a given N still stops the stream at N fills, as before);
//       --presend-live-fee-budget-sol X is optional (default 1.0) and is now a ROLLING 24 h budget of failed-attempt fees: when the fees of
//         the last 24 h (feed clock) reach X the sender PAUSES (no new attempts; windows still arm and are recorded; a loud line and a
//         presend_live_fee_pause record), and resumes when the rolling sum falls back under X (presend_live_fee_resume). It never stops
//         the run (dip23 stopped the stream for good at X). Range (0, 100] SOL.
// =====================================================================================================================
use super::*;
use arbx::presend_live as pl;
use arbx::presend_quiet as pq;
use rustc_hash::{FxHashMap, FxHashSet};
use std::collections::VecDeque;
use std::sync::atomic::AtomicU64;
use std::sync::Mutex;

/// every --presend-live-* flag (a stray one without --presend-live is refused)
const FLAGS: [&str; 17] = ["--presend-live-dry", "--presend-live-size-sol", "--presend-live-k", "--presend-live-drop", "--presend-live-deadline-slots",
    "--presend-live-cu-limit", "--presend-live-cu-price-micro", "--presend-live-tip-lamports", "--presend-live-routes", "--presend-live-max-per-sec",
    "--presend-live-path-max-per-sec", "--presend-live-max-fills", "--presend-live-fee-budget-sol", "--presend-live-create-slot", "--presend-live-one-position",
    "--presend-live-exit-ms", "--presend-live-quiet-v2-log"];

/// dip20 QUIET: its flags (each needs --presend-live; the history / threshold / warm-up / fbots / preload ones need
/// --presend-live-quiet-skip on)
const QFLAGS: [&str; 10] = ["--presend-live-quiet-stop", "--presend-live-quiet-skip", "--presend-live-quiet-hist-h", "--presend-live-quiet-fol",
    "--presend-live-quiet-warmup-min", "--presend-live-fbots", "--presend-live-quiet-preload", "--presend-live-quiet-state", "--presend-live-quiet-state-max-gap-min",
    "--presend-live-quiet-book"];

/// dip20 QUIET's parameters (all off by default)
#[derive(Clone, Debug, PartialEq)]
pub struct QuietCfg {
    /// --presend-live-quiet-stop N:M
    pub stop: Option<pq::QStop>,
    /// --presend-live-quiet-skip on
    pub skip: bool,
    /// --presend-live-quiet-hist-h (24), --presend-live-quiet-fol (2.24), --presend-live-quiet-warmup-min (60)
    pub hist_h: f64, pub fol: f64, pub warmup_min: f64,
    /// --presend-live-fbots FILE (needed by the skip), --presend-live-quiet-preload DIR | current_run file
    pub fbots: Option<String>, pub preload: Option<String>,
    /// dip21: --presend-live-quiet-state FILE (the whale history's journal), --presend-live-quiet-state-max-gap-min (30)
    pub state: Option<String>, pub state_max_gap_min: f64,
    /// dip21: --presend-live-quiet-book FILE (the host's book of the whale history, pushed to the node; read at the start)
    pub book: Option<String>,
}

impl Default for QuietCfg {
    fn default() -> QuietCfg { QuietCfg { stop: None, skip: false, hist_h: 24.0, fol: 2.24, warmup_min: 60.0, fbots: None, preload: None, state: None, state_max_gap_min: 30.0, book: None } }
}

impl QuietCfg {
    pub fn on(&self) -> bool { self.stop.is_some() || self.skip }
    pub fn json(&self) -> serde_json::Value {
        let mut j = serde_json::json!({"stop": self.stop.map(|q| format!("{}:{}", q.n, q.m)), "skip": self.skip, "hist_h": self.hist_h, "fol": self.fol, "warmup_min": self.warmup_min,
            "fbots": self.fbots, "preload": self.preload});
        // dip21: only with the journal / the book (without them: dip20's record)
        if self.state.is_some() { j["state"] = self.state.clone().into(); }
        if self.book.is_some() { j["book"] = self.book.clone().into(); }
        if self.state.is_some() || self.book.is_some() { j["state_max_gap_min"] = self.state_max_gap_min.into(); }
        j
    }
}

/// the default CU limit of an attempt: MEASURED 10-25 in simulation on live tokens (LIVE.md): a filled attempt used 71.5k..88.6k CU,
/// a 6042 one 55k..72k; 120k = ~35% above the highest (a failed attempt's priority fee is charged on the limit: 120 lamports at 1,000 uL)
pub const CU_DEFAULT: u64 = 120_000;
/// a fill blocks the token until our sell + this (the shadow's MARGIN)
const MARGIN_MS: u64 = 300;
/// the whale's first sell ends the window this much later (the shadow's 30 ms)
const WHALE_SELL_MS: u64 = 30;

/// the probe's parameters
#[derive(Clone, Debug)]
pub struct Cfg {
    pub dry: bool,
    pub spend: u64,
    pub k: u64,
    pub drop: f64,
    pub deadline_slots: u64,
    pub cu_limit: u32,
    pub cu_price: u64,
    /// None: each path's own configured tip
    pub tip: Option<u64>,
    pub routes: String,
    pub max_per_sec: u64,
    pub path_max_per_sec: u64,
    pub max_fills: u64,
    pub fee_budget: u64,
    pub create_slot: bool,
    pub one_position: bool,
    /// the shadow's T2 / exit parameters (--presend-*): the same rules
    pub whale_pct: f64, pub window_slots: u64, pub live_ms: f64, pub exit_slots: u64, pub tp: f64, pub sl: f64,
    /// dip22 (--presend-live-exit-ms N; 0 = off, the default): sell N ms after our fill is seen, before the slot limit. The "sell
    /// earlier" exit verified on live fills (ops/strategies/haqq_dissect/verify/REPORT.md: ~200 ms after the fill beat the 2-slot exit)
    pub exit_ms: u64,
    /// dip20 QUIET (default: all off)
    pub quiet: QuietCfg,
    /// dip23 (--presend-live-quiet-v2-log; off by default): the QUIET v2 candidate's features written into the arm / skip records
    /// (log-only; a per-token 120 s price ring is kept only with it)
    pub quiet_v2_log: bool,
}

impl Cfg {
    /// the flags (None: --presend-live absent; every --presend-live-* flag then refused). `live`: the run sends (--live);
    /// `cap`: its per-buy cap (--max-sol, lamports)
    pub fn from_args(sh: &arbx::presend::Params, live: bool, cap: u64) -> Result<Option<Cfg>> { Cfg::from_argv(&std::env::args().collect::<Vec<_>>(), sh, live, cap) }

    /// `from_args` on a given command line (unit-tested). The readers below are named as the engine's own (arg_u64 / arg_f64 ...),
    /// so the start-up flag check (check_flags: the source's `arg_u64("--...` calls) knows which flags must be numbers
    pub fn from_argv(argv: &[String], sh: &arbx::presend::Params, live: bool, cap: u64) -> Result<Option<Cfg>> {
        let has = |f: &str| argv.iter().skip(1).any(|x| x == f);
        let arg = |f: &str| argv.iter().position(|x| x == f).and_then(|i| argv.get(i + 1)).cloned();
        let arg_u64 = |f: &str, d: u64| arg(f).and_then(|s| s.parse::<u64>().ok()).unwrap_or(d);
        let arg_u64_opt = |f: &str| arg(f).and_then(|s| s.parse::<u64>().ok());
        let arg_f64 = |f: &str, d: f64| arg(f).and_then(|s| s.parse::<f64>().ok()).unwrap_or(d);
        if !has("--presend-live") {
            if let Some(f) = FLAGS.iter().chain(QFLAGS.iter()).find(|f| has(f)) { bail!("{f} needs --presend-live"); }
            return Ok(None);
        }
        if !has("--presend-shadow") { bail!("--presend-live needs --presend-shadow (its records are the comparison)"); }
        let dry = has("--presend-live-dry");
        if !dry && !live { bail!("--presend-live sends real attempts: it needs --live (or --presend-live-dry: build, sign and log every attempt, never send)"); }
        let onoff = |f: &str, d: bool| -> Result<bool> { match arg(f).as_deref() { None => Ok(d), Some("on") => Ok(true), Some("off") => Ok(false), Some(x) => bail!("{f} {x}: on | off") } };
        // dip24: optional; 0 / absent = unlimited
        let max_fills = arg_u64("--presend-live-max-fills", 0);
        // dip24: optional (1.0); SOL of failed-attempt fees per ROLLING 24 h (the sender pauses above it, never stops)
        let fee_sol = arg_f64("--presend-live-fee-budget-sol", 1.0);
        if !(fee_sol > 0.0) { bail!("REFUSED: --presend-live-fee-budget-sol must be > 0 SOL (failed-attempt fees per rolling 24 h)"); }
        let c = Cfg {
            dry,
            spend: (arg_f64("--presend-live-size-sol", sh.size_sol) * 1e9).round() as u64,
            k: arg_u64("--presend-live-k", 4),
            drop: arg_f64("--presend-live-drop", sh.drop),
            deadline_slots: arg_u64("--presend-live-deadline-slots", 1),
            cu_limit: arg_u64("--presend-live-cu-limit", CU_DEFAULT).min(u32::MAX as u64) as u32,
            cu_price: arg_u64("--presend-live-cu-price-micro", 1_000),
            tip: arg_u64_opt("--presend-live-tip-lamports"),
            routes: arg("--presend-live-routes").context("--presend-live needs --presend-live-routes \"class=path+path;...;default=path\" (its own [[send]] entries)")?,
            max_per_sec: arg_u64("--presend-live-max-per-sec", 20),
            path_max_per_sec: arg_u64("--presend-live-path-max-per-sec", 10),
            max_fills,
            fee_budget: (fee_sol * 1e9).round() as u64,
            create_slot: onoff("--presend-live-create-slot", false)?,
            one_position: onoff("--presend-live-one-position", true)?,
            whale_pct: sh.whale_pct, window_slots: sh.window_slots, live_ms: sh.live_ms, exit_slots: sh.exit_slots, tp: sh.tp, sl: sh.sl,
            exit_ms: arg_u64("--presend-live-exit-ms", 0),
            quiet: Cfg::quiet_from(&has, &arg, &arg_f64, &onoff)?,
            quiet_v2_log: has("--presend-live-quiet-v2-log"),
        };
        c.check(live, cap)?;
        Ok(Some(c))
    }

    /// dip20 QUIET's flags (refused: a bad N:M, a skip parameter without --presend-live-quiet-skip on, the skip without its
    /// follower-bot list, values out of range)
    fn quiet_from(has: &dyn Fn(&str) -> bool, arg: &dyn Fn(&str) -> Option<String>, arg_f64: &dyn Fn(&str, f64) -> f64, onoff: &dyn Fn(&str, bool) -> Result<bool>) -> Result<QuietCfg> {
        let d = QuietCfg::default();
        let stop = match arg("--presend-live-quiet-stop") {
            Some(s) => Some(pq::QStop::parse(&s).map_err(|e| anyhow::anyhow!("--presend-live-quiet-stop {e}"))?),
            None if has("--presend-live-quiet-stop") => bail!("--presend-live-quiet-stop needs N:M (e.g. 6:2)"),
            None => None,
        };
        let skip = onoff("--presend-live-quiet-skip", false)?;
        if !skip {
            if let Some(f) = QFLAGS[2..].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-quiet-skip on"); }
        }
        let q = QuietCfg { stop, skip, hist_h: arg_f64("--presend-live-quiet-hist-h", d.hist_h), fol: arg_f64("--presend-live-quiet-fol", d.fol),
            warmup_min: arg_f64("--presend-live-quiet-warmup-min", d.warmup_min), fbots: arg("--presend-live-fbots"), preload: arg("--presend-live-quiet-preload"),
            state: arg("--presend-live-quiet-state"), state_max_gap_min: arg_f64("--presend-live-quiet-state-max-gap-min", d.state_max_gap_min),
            book: arg("--presend-live-quiet-book") };
        if has("--presend-live-quiet-state") && q.state.as_deref().is_none_or(|p| p.starts_with("--")) { bail!("--presend-live-quiet-state needs a path"); }
        if has("--presend-live-quiet-book") && q.book.as_deref().is_none_or(|p| p.starts_with("--")) { bail!("--presend-live-quiet-book needs a path"); }
        if has("--presend-live-quiet-state-max-gap-min") && q.state.is_none() && q.book.is_none() {
            bail!("--presend-live-quiet-state-max-gap-min needs --presend-live-quiet-state FILE or --presend-live-quiet-book FILE");
        }
        if !(q.state_max_gap_min >= 0.0 && q.state_max_gap_min <= 1440.0) { bail!("--presend-live-quiet-state-max-gap-min must be 0..1440"); }
        if q.skip && q.fbots.is_none() { bail!("--presend-live-quiet-skip on needs --presend-live-fbots FILE (the follower-bot list, e.g. /root/dip/fbots_frozen.json)"); }
        if !(q.hist_h > 0.0 && q.hist_h <= 48.0) { bail!("--presend-live-quiet-hist-h must be in (0, 48] hours"); }
        if !(q.fol > 0.0 && q.fol <= 100.0) { bail!("--presend-live-quiet-fol must be in (0, 100]"); }
        if !(q.warmup_min >= 0.0 && q.warmup_min <= 1440.0) { bail!("--presend-live-quiet-warmup-min must be 0..1440"); }
        if has("--presend-live-quiet-preload") && q.preload.as_deref().is_none_or(|p| p.starts_with("--")) { bail!("--presend-live-quiet-preload needs a path"); }
        if has("--presend-live-fbots") && q.fbots.as_deref().is_none_or(|p| p.starts_with("--")) { bail!("--presend-live-fbots needs a path"); }
        Ok(q)
    }

    /// the ranges (pure: unit-tested)
    pub fn check(&self, live: bool, cap: u64) -> Result<()> {
        if self.spend == 0 || self.spend > 2_000_000_000 { bail!("--presend-live-size-sol must be in (0, 2]"); }
        if live && self.spend > cap { bail!("REFUSED: --presend-live-size-sol {:.3} exceeds --max-sol (the per-buy cap)", self.spend as f64 / 1e9); }
        if !(1..=20).contains(&self.k) { bail!("--presend-live-k must be 1..20 attempts per slot"); }
        if !(self.drop > 0.0 && self.drop <= 0.5) { bail!("--presend-live-drop must be in (0, 0.5]"); }
        if !(1..=8).contains(&self.deadline_slots) { bail!("--presend-live-deadline-slots must be 1..8"); }
        if !(20_000..=400_000).contains(&self.cu_limit) { bail!("--presend-live-cu-limit must be 20000..400000"); }
        if self.cu_price > 1_000_000 { bail!("--presend-live-cu-price-micro above 1,000,000 (a failed attempt would cost > 0.0001 SOL in priority): refusing"); }
        if self.tip.is_some_and(|t| t > 10_000_000) { bail!("--presend-live-tip-lamports above 0.01 SOL: refusing"); }
        if !(1..=200).contains(&self.max_per_sec) || !(1..=200).contains(&self.path_max_per_sec) { bail!("--presend-live-max-per-sec / --presend-live-path-max-per-sec must be 1..200"); }
        // dip24: --presend-live-max-fills any N (0 = unlimited); the fee budget is per rolling 24 h, (0, 100] SOL
        if self.fee_budget == 0 || self.fee_budget > 100_000_000_000 { bail!("--presend-live-fee-budget-sol must be in (0, 100] SOL per rolling 24 h"); }
        if self.exit_ms != 0 && !(50..=2_000).contains(&self.exit_ms) { bail!("--presend-live-exit-ms must be 0 (off) or 50..2000"); }
        Ok(())
    }

    /// a failed attempt's fee: 5,000 base + CU limit x price (the priority fee is charged on the limit)
    pub fn fail_fee(&self) -> u64 { 5_000 + (self.cu_limit as u64 * self.cu_price).div_ceil(1_000_000) }

    pub fn json(&self) -> serde_json::Value {
        let mut j = serde_json::json!({"dry": self.dry, "spend": self.spend, "k": self.k, "drop": self.drop, "deadline_slots": self.deadline_slots, "cu_limit": self.cu_limit,
            "cu_price": self.cu_price, "tip": self.tip, "routes": self.routes, "max_per_sec": self.max_per_sec, "path_max_per_sec": self.path_max_per_sec,
            "max_fills": self.max_fills, "fee_budget": self.fee_budget, "create_slot": self.create_slot, "one_position": self.one_position,
            "whale_pct": self.whale_pct, "window_slots": self.window_slots, "live_ms": self.live_ms, "exit_slots": self.exit_slots, "exit_ms": self.exit_ms, "tp": self.tp, "sl": self.sl,
            "fail_fee": self.fail_fee(), "margin_ms": MARGIN_MS, "whale_sell_ms": WHALE_SELL_MS});
        // dip20: only when a QUIET flag is on (flags off: dip19's record)
        if self.quiet.on() { j["quiet"] = self.quiet.json(); }
        // dip23: only with the v2 log flag
        if self.quiet_v2_log { j["quiet_v2_log"] = true.into(); }
        j
    }
}

/// every send path a reactive buy or a sell can use (incl. --sell-fanout; an attempt path must be none of them: its own rate budget)
pub fn reactive_paths(main: &Arc<send::Path>) -> Vec<String> {
    let mut v = vec![main.name.clone()];
    for p in [ALSO_PATH.get(), SELL_PATH.get(), SELL_FALLBACK.get(), FALLBACK_PATH.get()].into_iter().flatten() { v.push(p.name.clone()); }
    if let Some(m) = lat::MULTI.get() { v.extend(m.iter().map(|p| p.name.clone())); }
    if let Some(m) = SELL_FANOUT.get() { v.extend(m.iter().map(|p| p.name.clone())); }
    if let Some(r) = lat::ROUTES.get() { for ps in r.values() { v.extend(ps.iter().map(|p| p.name.clone())); } }
    v.sort(); v.dedup();
    v
}

/// one attempt path: the path, its fast connection (when FAST built one), its own rate bucket
struct RouteP { path: Arc<send::Path>, fast: Option<(Arc<arbx::fast::FastConn>, bool)>, bucket: send::TokenBucket }

/// --presend-live-routes against the built paths: class -> paths (the reactive paths refused; a tip override below a path
/// kind's minimum refused; classes need the leader book)
pub fn parse_routes(spec: &str, paths: &send::Paths, reactive: &[String], tip: Option<u64>) -> Result<FxHashMap<String, Vec<Arc<send::Path>>>> {
    let r = lat::parse_routes(spec, paths).context("--presend-live-routes")?;
    refuse_empty_classes(&r)?;
    let mut out = FxHashMap::default();
    for (c, ps) in r {
        for p in &ps {
            if reactive.contains(&p.name) {
                bail!("--presend-live-routes: path {} is also a reactive buy / sell path: give the attempts their own [[send]] entry (e.g. a helius-ps copy of helius-swqos with its own max_per_sec)", p.name);
            }
            if let (Some(t), Some(_)) = (tip, p.tip(0)) {
                if t < p.kind.min_tip() { bail!("--presend-live-tip-lamports {t}: below {}'s minimum tip {} ({:?})", p.name, p.kind.min_tip(), p.kind); }
            }
        }
        out.insert(c, ps);
    }
    Ok(out)
}

/// dip15: an empty class (e.g. "jito=") panicked the sender on its first attempt there (a modulo by zero): refused at start
fn refuse_empty_classes<T>(r: &std::collections::HashMap<String, Vec<T>>) -> Result<()> {
    let mut empty: Vec<&String> = r.iter().filter(|(_, v)| v.is_empty()).map(|(c, _)| c).collect();
    empty.sort();
    if let Some(c) = empty.first() { bail!("--presend-live-routes: class '{c}' has no paths: give it at least one (e.g. {c}=helius-ps) or leave it out (it then uses default)"); }
    Ok(())
}

/// an armed window as the sender sees it
#[derive(Clone)]
struct SWin { id: u64, mint: Pk, launch: Launch, st_ns: u64, stop_ns: u64, en_slot: u64, vsol: u64, vtok: u64, fr: f64, pos: (u64, u32, i32), pace: pl::Pace, n: u32, done: bool }

/// the last RING samples (µs), for p50 / p99
#[derive(Default)]
pub struct Ring { v: Vec<f32>, i: usize }
const RING: usize = 4096;
impl Ring {
    pub fn add(&mut self, x: f32) { if self.v.len() < RING { self.v.push(x); } else { self.v[self.i] = x; self.i = (self.i + 1) % RING; } }
    pub fn pct(&self) -> (f32, f32) {
        let mut v = self.v.clone(); v.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let q = |p: f64| v.get(((v.len().max(1) - 1) as f64 * p).round() as usize).copied().unwrap_or(0.0);
        (q(0.5), q(0.99))
    }
}

/// the main loop <-> sender state
struct Shared {
    wins: Mutex<Vec<SWin>>,
    /// no new attempts any more (caps / run end)
    stop: AtomicBool,
    /// a reactive position is open / a pre-send position is open (one position per server)
    pause_reactive: AtomicBool,
    pause_pos: AtomicBool,
    /// dip24: the rolling 24 h failed-attempt fee budget is spent (no new attempts until it rolls back under)
    pause_fee: AtomicBool,
    /// the feed's newest slot (the main loop's)
    slot: AtomicU64,
    seq: AtomicU64,
    sent: AtomicU64,
    dry: AtomicU64,
    /// the sender left its loop (after a stop): nothing more can be sent
    exited: AtomicBool,
    skips: Mutex<FxHashMap<&'static str, u64>>,
    build_us: Mutex<Ring>,
}

impl Shared {
    fn skip(&self, why: &'static str) { *self.skips.lock().unwrap().entry(why).or_default() += 1; }
    fn cur_slot(&self) -> u64 { self.slot.load(Ordering::Relaxed).max(send::tpu::SLOT.load(Ordering::Relaxed)) }
}

/// one sent (or dry) attempt, as the main loop registers it
#[derive(Clone, Debug)]
pub struct Att {
    pub w: u64, pub n: u32, pub mint: Pk, pub sig: [u8; 64], pub tag: u64, pub path: String, pub client: String, pub slot: u64, pub deadline: u64, pub lim: f64,
    pub min_out: u64, pub p_sign: f64, pub sign_pos: (u64, u32, i32), pub t_send: u64, pub roles: pl::Roles, pub tip: u64, pub wst: &'static str,
}

/// what the sender needs
struct SCfg { cfg: Cfg, user: Pk, key: SigningKey, guard: GuardEnc, routes: FxHashMap<String, Vec<RouteP>>, handle: tokio::runtime::Handle }

/// log records and terminal lines go to a writer thread (no write on the event loop)
pub enum Out { Rec(serde_json::Value), Line(String) }
impl Out {
    /// dip24 (tests): the record, if this is one
    #[cfg(test)]
    pub fn rec(self) -> Option<serde_json::Value> { match self { Out::Rec(v) => Some(v), Out::Line(_) => None } }
}

fn spawn_writer(log: Arc<DipLog>) -> crossbeam_channel::Sender<Out> {
    let (tx, rx) = crossbeam_channel::unbounded::<Out>();
    std::thread::Builder::new().name("ps-log".into()).spawn(move || {
        while let Ok(o) = rx.recv() {
            let mut recs = Vec::new(); let mut lines = String::new();
            let mut add = |o: Out| match o { Out::Rec(v) => recs.push(v), Out::Line(l) => { lines.push_str(&l); lines.push('\n'); } };
            add(o);
            let mut n = 1;
            while let Ok(o) = rx.try_recv() { add(o); n += 1; if n > 256 { break; } }
            if !lines.is_empty() { eprint!("{lines}"); }
            log.w_all(recs);
        }
    }).expect("ps-log thread");
    tx
}

/// THE SENDER (its own thread): the armed windows' attempts, k per slot, evenly spaced
fn sender(sh: Arc<Shared>, mut sc: SCfg, out: crossbeam_channel::Sender<Out>, atx: crossbeam_channel::Sender<Att>) {
    let mut global = send::TokenBucket::new(sc.cfg.max_per_sec as f64, (sc.cfg.max_per_sec as u32 / 4).max(1));
    let (mut body, mut req) = (Vec::with_capacity(2048), Vec::with_capacity(2400));
    let mut warned: FxHashMap<String, u64> = FxHashMap::default();
    loop {
        if sh.stop.load(Ordering::Relaxed) && sh.wins.lock().unwrap().is_empty() { break; }
        let now = arbx::fast::mono_ns();
        let slot = sh.cur_slot();
        let mut due: Vec<SWin> = Vec::new();
        let mut any = false;
        {
            let mut g = sh.wins.lock().unwrap();
            for w in g.iter_mut() {
                if w.done { continue; }
                any = true;
                if now < w.st_ns || now >= w.stop_ns || slot > w.en_slot { continue; }
                if w.pace.due(now) { w.n += 1; due.push(w.clone()); }
            }
        }
        for w in due {
            let t0 = arbx::fast::mono_ns();
            // why not now (each counted)
            let why: Option<&'static str> = if sh.stop.load(Ordering::Relaxed) || DIP_NO_FIRE.load(Ordering::Relaxed) { Some("stopped") }
                else if sc.cfg.one_position && sh.pause_reactive.load(Ordering::Relaxed) { Some("paused_reactive_position") }
                else if sc.cfg.one_position && sh.pause_pos.load(Ordering::Relaxed) { Some("paused_presend_position") }
                // dip24: the rolling 24 h fee budget is spent (resumes when it rolls back under)
                else if sh.pause_fee.load(Ordering::Relaxed) { Some("paused_fee_budget") }
                else if fires_paused() { Some("paused_blockhash_or_balance_read") }
                else {
                    let bal = ACCT.bal.load(Ordering::SeqCst);
                    if bal > 0 && bal < sc.cfg.spend + 30_000_000 + ACCT.reserved.load(Ordering::SeqCst) { Some("paused_balance") } else { None }
                };
            if let Some(why) = why { sh.skip(why); continue; }
            let deadline = (slot + sc.cfg.deadline_slots).min(w.en_slot);
            if deadline < slot { sh.skip("window_over"); continue; }
            let (leader, client) = lat::leader_of(slot).unwrap_or_default();
            let class = lat::class(&client);
            let rkey = if sc.routes.contains_key(class) { class } else { "default" };
            let Some(rs) = sc.routes.get_mut(rkey) else { sh.skip("no_route"); continue };
            if rs.is_empty() { sh.skip("no_route"); continue; }            // parse_routes refuses empty classes; never a modulo by zero
            let ri = (w.n as usize + w.id as usize) % rs.len();
            let r = &mut rs[ri];
            if let Err(why) = take_rate(&mut global, &mut r.bucket, now, || r.path.fast_budget()) { sh.skip(why); continue; }
            let Some((min_out, lim, _)) = pl::limit_min_out(w.vsol, w.vtok, sc.cfg.spend, w.fr, sc.cfg.drop) else { sh.skip("untradeable"); continue };
            let tip = r.path.tip(0).map(|(a, l)| (a, sc.cfg.tip.unwrap_or(l)));
            let (mut ixs, roles) = pl::attempt_ixs(sc.user, &w.launch, sc.cfg.spend, min_out, sc.cfg.cu_limit, sc.cfg.cu_price, guard_ix_enc(sc.guard, deadline), tip);
            // dip16 C1 (--loaded-data-limit): the limit LAST (the roles' guard / ATA / buy / tip indices stay dip15's); nothing without it
            speed16::add_ll(&mut ixs, speed16::loaded_limit());
            let Some((bh, bh_age)) = (*BLOCKHASH_CACHE.lock().unwrap()).map(|(h, t, _)| (h, t.elapsed())) else { sh.skip("no_blockhash"); continue };
            if bh_age > Duration::from_secs(20) { sh.skip("blockhash_old"); continue; }
            let raw = match build::compile_v0(sc.user, &ixs, bh, &[], &[]) { Ok(m) => build::sign(&m, &sc.key), Err(e) => { sh.skip("build_error"); warn_once(&out, &mut warned, "build", &e); continue; } };
            if raw.len() > 1232 { sh.skip("too_big"); warn_once(&out, &mut warned, "size", &format!("{} bytes", raw.len())); continue; }
            if let Err(e) = r.path.check(&raw) { sh.skip("path_check"); warn_once(&out, &mut warned, &r.path.name, &format!("{e:#}")); continue; }
            let mut sig = [0u8; 64]; sig.copy_from_slice(&raw[1..65]);
            let seq = sh.seq.fetch_add(1, Ordering::Relaxed) + 1;
            let tag = pl::PS_TAG | seq;
            let t_send = arbx::feeds::clock::now_ns();
            let t1 = arbx::fast::mono_ns();
            let mut a = Att { w: w.id, n: w.n, mint: w.mint, sig, tag, path: r.path.name.clone(), client: client.clone(), slot, deadline, lim, min_out, p_sign: w.vsol as f64 / w.vtok.max(1) as f64,
                sign_pos: w.pos, t_send, roles, tip: tip.map_or(0, |t| t.1), wst: "dry" };
            // registered BEFORE the write: the main loop knows the signature before its landing can arrive
            if !sc.cfg.dry {
                let _ = atx.send(a.clone());
                a.wst = send_one(r, &raw, tag, &sc.handle, &mut body, &mut req);
                sh.sent.fetch_add(1, Ordering::Relaxed);
            } else { sh.dry.fetch_add(1, Ordering::Relaxed); }
            let t2 = arbx::fast::mono_ns();
            sh.build_us.lock().unwrap().add(((t1 - t0) as f64 / 1e3) as f32);
            let _ = out.send(Out::Rec(serde_json::json!({"ev": "presend_attempt", "w": a.w, "n": a.n, "mint": b58(&a.mint), "sig": bs58::encode(&a.sig).into_string(), "tag": seq,
                "path": a.path, "client": a.client, "leader": leader.chars().take(8).collect::<String>(), "slot": slot, "deadline": deadline, "en_slot": w.en_slot,
                "vsol": w.vsol, "vtok": w.vtok, "p": a.p_sign, "lim": lim, "min_out": min_out, "spend": sc.cfg.spend, "tip": a.tip, "cu": sc.cfg.cu_limit, "cu_price": sc.cfg.cu_price,
                "pos": [w.pos.0, w.pos.1, w.pos.2], "t": t_send, "w_status": a.wst, "dry": sc.cfg.dry, "build_us": (t1 - t0) as f64 / 1e3, "write_us": (t2 - t1) as f64 / 1e3,
                "bh_age_ms": bh_age.as_secs_f64() * 1e3, "bytes": raw.len()})));
        }
        // idle: 5 ms steps; armed: 0.5 ms (the pace's resolution)
        std::thread::sleep(if any { Duration::from_micros(500) } else { Duration::from_millis(5) });
    }
    sh.exited.store(true, Ordering::SeqCst);
}

/// the attempt rate caps (pure apart from `config`: the path's own [[send]] max_per_sec): this path's bucket, the global one,
/// then the path's configured budget; a refused attempt takes no token
fn take_rate(global: &mut send::TokenBucket, path: &mut send::TokenBucket, now: u64, config: impl FnOnce() -> bool) -> std::result::Result<(), &'static str> {
    if !path.peek(now) { return Err("rate_path"); }
    if !global.peek(now) { return Err("rate_global"); }
    if !config() { return Err("rate_path_config"); }
    path.try_take(now);
    global.try_take(now);
    Ok(())
}

fn warn_once(out: &crossbeam_channel::Sender<Out>, seen: &mut FxHashMap<String, u64>, k: &str, e: &str) {
    let n = seen.entry(k.to_string()).or_default();
    *n += 1;
    if *n == 1 || *n % 1000 == 0 { let _ = out.send(Out::Line(format!("  PRESEND LIVE attempt refused before sending ({k}, #{n}): {}", redact(e).chars().take(200).collect::<String>()))); }
}

/// write one attempt: the path's own fast connection (one syscall, this thread), else the path's async send on the runtime
fn send_one(r: &RouteP, raw: &[u8], tag: u64, handle: &tokio::runtime::Handle, body: &mut Vec<u8>, req: &mut Vec<u8>) -> &'static str {
    if let Some((conn, json)) = &r.fast {
        if *json { arbx::fast::json_send_body(raw, body); conn.frame(&body[..], req); } else { conn.frame(raw, req); }
        if conn.write_req(req, tag).is_ok() { return "written"; }
    }
    let (p, raw) = (r.path.clone(), raw.to_vec());
    handle.spawn(async move {
        let t = Instant::now();
        let res = p.send(&raw, send::Prio::default(), None).await;
        pl::note_ack(tag, match &res { Ok(rep) => rep.status.or(Some(200)), Err(e) => e.status }, t.elapsed().as_secs_f64() * 1e3);
    });
    if r.fast.is_some() { "conn_down_async" } else { "async" }
}

/// dip19 (fix 1): close our (confirmed EMPTY) Token-2022 account of `mint`: CloseAccount (rent to the wallet) at CLOSE_CU x the
/// attempts' CU price, through the sell path alone (its own tip only when it has one: staked-rpc has none), landing polled 8 s; its
/// payer delta (the rent back minus the fee) into the run's realized total. A close can never take tokens: the token program refuses
/// to close an account with a balance (the tx then fails: its fee only). -> (signature, Some(slot) = landed OK, why not)
async fn close_ata(key: &SigningKey, user: Pk, rpc: &rpc::Rpc, path: &Arc<send::Path>, mint: &Pk, price: u64, out: &crossbeam_channel::Sender<Out>) -> (String, Option<u64>, String) {
    let ixs = close_ixs(user, mint, price);
    match send_and_poll(key, user, rpc, sp(path), &ixs, Duration::from_secs(8)).await {
        Ok(l) => match (l.land_slot, l.ok) {
            (Some(s), true) => {
                let d = tx_payer(rpc, &l.sig, 8).await;
                if let Some((v, _, _)) = d { ACCT.realized.fetch_add(v, Ordering::SeqCst); }
                let _ = out.send(Out::Rec(serde_json::json!({"ev": "presend_live_ata_close", "mint": b58(mint), "sig": l.sig, "slot": s, "ok": true, "delta": d.map(|x| x.0), "fee": d.map(|x| x.1)})));
                let _ = out.send(Out::Line(format!("  PRESEND LIVE ATA CLOSED {} (slot {s}){}", b58(mint), d.map(|x| format!(": {:+.6} SOL back", x.0 as f64 / 1e9)).unwrap_or_default())));
                (l.sig, Some(s), String::new())
            }
            (Some(_), false) => (l.sig, None, format!("landed failed: {}", l.err.map(|e| e.to_string()).unwrap_or_default())),
            (None, _) => (l.sig, None, "not seen".into()),
        },
        Err(e) => (String::new(), None, redact(&format!("{e:#}")).chars().take(160).collect()),
    }
}

/// dip19: the close's instructions (pure: unit-tested): CU limit, CU price, Token-2022 CloseAccount of our account of `mint` (rent to us)
fn close_ixs(user: Pk, mint: &Pk, price: u64) -> Vec<build::Ix> {
    vec![build::cu_limit_ix(CLOSE_CU), build::cu_price_ix(price), build::close_account_ix(pda::ata(&user, mint, &pda::TOKEN_2022), user, user, *pda::TOKEN_2022)]
}

// ---- the event loop's side ------------------------------------------------------------------------------------------

/// one live window (the main loop's)
struct Win {
    id: u64, mint: Pk, whale: Pk, trig_slot: u64, en_slot: u64, armed_at: Instant, stop_at: Option<Instant>,
    /// attempts sent / resolved; the last attempt's deadline
    sent: u32, resolved: u32, unseen: u32, last_deadline: u64,
    disarmed: Option<&'static str>, filled: bool, checked: bool,
    /// dip19: set at the disarm: the sender's slot then + the deadline slots (an attempt built just before the disarm, registered
    /// after it, has a deadline at or below this)
    quiet: u64,
    /// dip20 QUIET (None without it): the arm's signals (its records' "quiet"), the trigger's key (its stop watch), the "other" trades
    /// counted when the stop rule decided (None: not decided yet)
    qj: Option<serde_json::Value>, qkey: Option<u64>, q_others: Option<u32>,
}

// ---- dip20 QUIET (src/presend_quiet.rs; all off without its flags) --------------------------------------------------------

/// one trigger's stop watch (every trigger, armed or not: the live window's stop and the shadow's paper both read it)
struct QWatch { id: u64, whale: Pk, trig_slot: u64, others: u32, win: Option<u64> }

/// a trigger's QUIET view, kept until the shadow's records of it passed: (trigger key, the arm signals record, the stop decision
/// (stop, slot, others), the slot it was made in)
struct QTrig { key: (String, String, i64), arm: serde_json::Value, stop: Option<(bool, u64, u32)>, slot: u64, v2: Option<serde_json::Value> }

/// the preload's state: off, running (its thread), done, failed
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum PreSt { Off, Running, Done, Failed }

/// the QUIET state of the probe
struct Quiet {
    cfg: QuietCfg,
    /// the arm rule (--presend-live-quiet-skip on): the whale dump history, the cohort and follower-bot sets
    book: Option<pq::DumpBook>, coh: FxHashSet<Pk>, fb: FxHashSet<Pk>,
    /// the arm rule's schedule: the start (unix ns), the warm-up, what a preload brought in
    start_ns: u64, warm_ns: u64, covered_ns: u64,
    /// the preload: its thread's answer, the cut slot it needs (the live book's first slot + 1, set at its first trade)
    pre_rx: Option<crossbeam_channel::Receiver<std::result::Result<pq::PreloadOut, String>>>, cut: Arc<AtomicU64>, pre: PreSt, pre_info: serde_json::Value,
    /// the stop watches (mint -> the undecided ones) and every trigger's view (id -> it), the shadow's window ids -> trigger id
    watch: FxHashMap<Pk, Vec<QWatch>>, trigs: FxHashMap<u64, QTrig>, by_key: FxHashMap<(String, String, i64), u64>, shadow_w: FxHashMap<u64, (u64, u64)>,
    qid: u64, last_slot: u64,
    /// trigger views are kept this many slots (the shadow's records of them come by then; a replay keeps them all)
    keep_slots: u64,
    /// the slot clock of the stop: max(feed, TPU) in a run (the attempts' own clock); the feed only in the tests
    tpu_clock: bool,
    /// counters: skips, stops, triggers whose four signals held during the warm-up (not skipped), signals computed; times (µs)
    skips: u64, stops: u64, warm_would: u64, signals: u64, sig_us: Ring, merge_us: f64,
    /// dip21 (--presend-live-quiet-state FILE): the journal writer's channel, thread and counters; the sessions the file had (the
    /// history's coverage); what the load found; this session's first slot; the last heartbeat (data time); the loaded dumps until the
    /// preload thread takes them
    jtx: Option<crossbeam_channel::Sender<pq::JMsg>>, jthread: Option<std::thread::JoinHandle<()>>, jstats: Arc<Mutex<pq::JStats>>,
    sessions: Vec<pq::Sess>, state_info: serde_json::Value, c0: u64, last_beat_t: u64, journal: Vec<pq::JDump>,
}

impl Quiet {
    /// `cohort`: the engine's --dip-cohort list (base58); `fbots`: the follower-bot list (loaded by the caller)
    fn new(cfg: &QuietCfg, cohort: &std::collections::HashSet<String>, fb: FxHashSet<Pk>, start_ns: u64, tpu_clock: bool) -> Quiet {
        let coh: FxHashSet<Pk> = if cfg.skip { cohort.iter().filter_map(|s| bs58::decode(s).into_vec().ok().and_then(|v| <[u8; 32]>::try_from(v).ok())).collect() } else { FxHashSet::default() };
        Quiet { cfg: cfg.clone(), book: cfg.skip.then(|| pq::DumpBook::new((cfg.hist_h * 3.6e12) as u64)), coh, fb, start_ns, warm_ns: (cfg.warmup_min * 6e10) as u64, covered_ns: 0,
            pre_rx: None, cut: Arc::new(AtomicU64::new(0)), pre: PreSt::Off, pre_info: serde_json::Value::Null, watch: FxHashMap::default(), trigs: FxHashMap::default(),
            by_key: FxHashMap::default(), shadow_w: FxHashMap::default(), qid: 0, last_slot: 0, keep_slots: 1_500, tpu_clock, skips: 0, stops: 0, warm_would: 0, signals: 0,
            sig_us: Ring::default(), merge_us: 0.0, jtx: None, jthread: None, jstats: Arc::new(Mutex::new(pq::JStats::default())), sessions: Vec::new(),
            state_info: serde_json::Value::Null, c0: 0, last_beat_t: 0, journal: Vec::new() }
    }

    /// dip21: the whale history at the start (`now_ns`: the engine's start), from the host's BOOK (--presend-live-quiet-book, pushed
    /// to the node) and the engine's own JOURNAL (--presend-live-quiet-state), merged by dump identity (the book's version kept): history
    /// at once; journaling on (with the journal); the arm rule's schedule from the merged history's continuity (`pq::coverage`: the gap
    /// between the history's end and the start is tolerated up to max-gap and not counted). Fallback order: a fresh book, the journal,
    /// (later) the preload, the warm-up; a missing / damaged / stale source counts for what it holds and never stops the start. -> the
    /// log line, the record, the compacted MERGED history for the journal writer (None: no journal). None: neither flag (or the skip off)
    fn open_state(&mut self, now_ns: u64) -> Option<(String, serde_json::Value, Option<Vec<pq::JRec>>)> {
        if self.cfg.state.is_none() && self.cfg.book.is_none() { return None; }
        let hist = (self.cfg.hist_h * 3.6e12) as u64;
        let gap_ns = (self.cfg.state_max_gap_min * 6e10) as u64;
        let t0 = Instant::now();
        let lb = self.cfg.book.as_ref().map(|p| pq::load_state(std::path::Path::new(p), now_ns, hist));
        let lj = self.cfg.state.as_ref().map(|p| pq::load_state(std::path::Path::new(p), now_ns, hist));
        let m = pq::merge_loaded(lb.as_ref(), lj.as_ref());
        let dumps: Vec<pq::JDump> = m.dumps.iter().map(|x| x.0).collect();
        let warm = self.warm_ns;
        let b = self.book.as_mut()?;
        b.load_finalized(&dumps);
        if self.cfg.state.is_some() { b.journal_on(); }
        let sellers = b.sellers();
        self.sessions = m.sessions.clone();
        let spans = |l: &pq::Loaded| -> Vec<(u64, u64)> { l.sessions.iter().map(|x| (x.t0, x.t1)).collect() };
        let cov = pq::coverage(&spans(&m), now_ns, gap_ns);
        let covb = lb.as_ref().map(|l| pq::coverage(&spans(l), now_ns, gap_ns));
        let covj = lj.as_ref().map(|l| pq::coverage(&spans(l), now_ns, gap_ns));
        self.covered_ns = cov.covered_ns;
        let on = self.arm_on(now_ns);
        let enough = |c: &Option<pq::Cov>| c.is_some_and(|c| c.covered_ns >= warm);
        let source = if !on { "none" } else if warm == 0 { "no warm-up" } else if enough(&covb) { "book" } else if enough(&covj) { "journal" } else { "book+journal" };
        let load_ms = t0.elapsed().as_secs_f64() * 1e3;
        let gap_s = |c: &pq::Cov| if c.gap_ns == u64::MAX { "none".to_string() } else { format!("{:.1} min", c.gap_ns as f64 / 6e10) };
        let desc = |name: &str, path: &str, l: &pq::Loaded, c: &pq::Cov| -> String {
            if l.missing { return format!("{name} {path}: {}", if name == "journal" { "no file yet (a first start)" } else { "MISSING" }); }
            if let Some(e) = &l.err { return format!("{name} {path}: UNREADABLE ({e})"); }
            let issues = if l.bad + l.truncated_tail as u64 + l.dups > 0 || l.skipped_bytes > 0 {
                format!(" [WARNING: skipped {} bad line(s){}{}{}]", l.bad, if l.truncated_tail { ", a truncated last line" } else { "" },
                    if l.dups > 0 { format!(", {} duplicate(s)", l.dups) } else { String::new() }, if l.skipped_bytes > 0 { format!(", the first {} MB", l.skipped_bytes >> 20) } else { String::new() })
            } else { String::new() };
            format!("{name} {path}: {} dumps, {} session(s), continuous {:.2} h{}, gap {}{}{issues}", l.dumps.len(), l.sessions.len(), c.covered_ns as f64 / 3.6e12,
                if c.to > 0 { format!(" to {}", ts_pkt(c.to)) } else { String::new() }, gap_s(c), if c.covered_ns == 0 && c.to > 0 { " (TOO OLD for the arm rule)" } else { "" })
        };
        let parts: Vec<String> = [lb.as_ref().zip(covb.as_ref()).zip(self.cfg.book.as_ref()).map(|((l, c), p)| desc("book", p, l, c)),
                                  lj.as_ref().zip(covj.as_ref()).zip(self.cfg.state.as_ref()).map(|((l, c), p)| desc("journal", p, l, c))].into_iter().flatten().collect();
        let line = format!("  QUIET history at the start: {} | merged {} dumps / {} sellers, {} session(s), continuous {:.2} h{}, gap {} ({} old, {:.0} ms) | arm rule {}",
            parts.join(" | "), dumps.len(), sellers, self.sessions.len(), cov.covered_ns as f64 / 3.6e12, if cov.to > 0 { format!(" to {}", ts_pkt(cov.to)) } else { String::new() },
            gap_s(&cov), m.old, load_ms,
            if on { format!("ON now (source: {source})") } else { format!("warming up until {} (needs {} min continuous ending within {} min of the start{})", ts_pkt(self.arm_at()),
                self.cfg.warmup_min, self.cfg.state_max_gap_min, if self.cfg.preload.is_some() { "; the preload may turn it on sooner" } else { "" }) });
        let src_json = |l: &Option<pq::Loaded>, c: &Option<pq::Cov>, p: &Option<String>| -> serde_json::Value {
            match (l, c, p) {
                (Some(l), Some(c), Some(p)) => serde_json::json!({"path": p, "dumps": l.dumps.len(), "sessions": l.sessions.len(), "covered_h": c.covered_ns as f64 / 3.6e12, "to": c.to,
                    "gap_min": if c.gap_ns == u64::MAX { serde_json::Value::Null } else { (c.gap_ns as f64 / 6e10).into() }, "missing": l.missing, "err": l.err, "bad": l.bad,
                    "truncated_tail": l.truncated_tail, "dups": l.dups, "old": l.old, "bytes": l.bytes}),
                _ => serde_json::Value::Null,
            }
        };
        self.state_info = serde_json::json!({"dumps": dumps.len(), "sellers": sellers, "sessions": self.sessions.len(), "covered_h": cov.covered_ns as f64 / 3.6e12, "from": cov.from,
            "to": cov.to, "gap_min": if cov.gap_ns == u64::MAX { serde_json::Value::Null } else { (cov.gap_ns as f64 / 6e10).into() }, "arm_on": on, "source": source,
            "arm_rule_on_at": self.arm_at(), "load_ms": load_ms, "book": src_json(&lb, &covb, &self.cfg.book), "journal": src_json(&lj, &covj, &self.cfg.state)});
        let mut rec = self.state_info.clone();
        rec["ev"] = "presend_live_quiet_state".into();
        rec["t"] = arbx::feeds::clock::now_ns().into();
        let compacted = self.cfg.state.is_some().then(|| pq::compact(&m));
        self.journal = dumps;
        Some((line, rec, compacted))
    }

    /// dip21: the journal writer thread (lowest CPU priority, idle I/O): it first rewrites the journal compacted, then appends what the
    /// event loop sends (never waited for); a thread that cannot start = no journal (warned)
    fn spawn_journal(&mut self, compacted: Vec<pq::JRec>) -> Option<String> {
        let path = self.cfg.state.clone()?;
        let (tx, rx) = crossbeam_channel::unbounded();
        let st = self.jstats.clone();
        match std::thread::Builder::new().name("ps-quiet-jrnl".into()).spawn(move || {
            unsafe {
                let tid = libc::syscall(libc::SYS_gettid);
                libc::setpriority(libc::PRIO_PROCESS, tid as libc::id_t, 19);
                libc::syscall(libc::SYS_ioprio_set, 1 /* IOPRIO_WHO_PROCESS */, tid, 3 << 13 /* IOPRIO_CLASS_IDLE */);
            }
            pq::journal_writer(std::path::PathBuf::from(path), Some(compacted), rx, st);
        }) {
            Ok(h) => { self.jtx = Some(tx); self.jthread = Some(h); None }
            Err(e) => Some(format!("  QUIET state: the journal writer did not start ({e}): NOTHING IS SAVED this run"))
        }
    }

    /// dip21, the run's end: the journal's last dumps (windows past their 2 slots; the others dropped), the stop marker; the writer
    /// drains, syncs and exits (waited for up to `wait`, never longer). -> (dumps saved now, dropped)
    fn close_journal(&mut self, wait: Duration) -> (usize, u64) {
        let Some(tx) = self.jtx.take() else { return (0, 0) };
        let mut r = (0, 0);
        if let Some(b) = self.book.as_mut() {
            let (v, dropped) = b.finalize_on_shutdown();
            r = (v.len(), dropped);
            if !v.is_empty() { let _ = tx.send(pq::JMsg::Dumps(v)); }
            if self.c0 != 0 { let _ = tx.send(pq::JMsg::Stop { t: b.max_t(), s: b.max_slot() }); }
        }
        drop(tx);
        if let Some(h) = self.jthread.take() {
            let t = Instant::now();
            while !h.is_finished() && t.elapsed() < wait { std::thread::sleep(Duration::from_millis(5)); }
            if h.is_finished() { let _ = h.join(); }
        }
        r
    }
    /// the preload thread (--presend-live-quiet-preload with the skip on): background, lowest CPU priority, never the event loop; its
    /// answer comes back through `pre_rx` (tick merges it); a thread that cannot start = a failed preload (the plain warm-up)
    fn spawn_preload(&mut self, timeout: Duration) {
        let (true, Some(p)) = (self.cfg.skip, self.cfg.preload.clone()) else { return };
        let (ptx, prx) = crossbeam_channel::bounded(1);
        // dip21: the journal's loaded dumps go with it (joined with the recording's by identity in that thread)
        let pc = pq::PreloadCfg { path: std::path::PathBuf::from(&p), hist_ns: (self.cfg.hist_h * 3.6e12) as u64, start_unix_ns: self.start_ns, timeout,
            journal: std::mem::take(&mut self.journal) };
        let cut = self.cut.clone();
        match std::thread::Builder::new().name("ps-quiet-pre".into()).spawn(move || {
            // the lowest CPU priority and the idle I/O class for this thread (and the gzip it starts: both are inherited)
            unsafe {
                let tid = libc::syscall(libc::SYS_gettid);
                libc::setpriority(libc::PRIO_PROCESS, tid as libc::id_t, 19);
                libc::syscall(libc::SYS_ioprio_set, 1 /* IOPRIO_WHO_PROCESS */, tid, 3 << 13 /* IOPRIO_CLASS_IDLE */);
            }
            let r = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| pq::preload(&pc, &cut))).unwrap_or_else(|_| Err("the preload thread panicked".into()));
            let _ = ptx.send(r);
        }) {
            Ok(_) => { self.pre_rx = Some(prx); self.pre = PreSt::Running; }
            Err(e) => { self.pre = PreSt::Failed; self.pre_info = serde_json::json!({"ok": false, "err": format!("thread: {e}")}); }
        }
    }
    /// is the arm rule on now (the warm-up less what a preload brought in; while a preload runs it is still off)
    fn arm_on(&self, now_ns: u64) -> bool { pq::arm_on(now_ns, self.start_ns, self.warm_ns, self.covered_ns) }
    /// when the arm rule turns on (unix ns)
    fn arm_at(&self) -> u64 { self.start_ns.saturating_add(self.warm_ns.saturating_sub(self.covered_ns)) }
}

/// the follower-bot list (a JSON array of base58 wallets): refused when unreadable, empty or with a bad entry
pub fn load_fbots(path: &str) -> Result<FxHashSet<Pk>> {
    let v: Vec<String> = serde_json::from_str(&std::fs::read_to_string(path).with_context(|| format!("--presend-live-fbots {path}"))?).with_context(|| format!("--presend-live-fbots {path}: not a JSON list"))?;
    let mut s = FxHashSet::default();
    for w in &v { s.insert(<[u8; 32]>::try_from(bs58::decode(w).into_vec().map_err(|_| anyhow::anyhow!("--presend-live-fbots: bad wallet {w}"))?).map_err(|_| anyhow::anyhow!("--presend-live-fbots: bad wallet {w}"))?); }
    if s.is_empty() { bail!("--presend-live-fbots {path}: empty"); }
    Ok(s)
}

fn ts_pkt(ns: u64) -> String {
    let s = (ns / 1_000_000_000) as i64 + 5 * 3600;
    format!("{:02}:{:02} PKT", (s / 3600) % 24, (s / 60) % 60)
}

/// a landed (or never seen) attempt waiting for its record (the tape around it is complete 2 slots later)
struct Land { att: Att, res: String, err: String, fee: u64, slot: u64, idx: Option<u64>, t_rx: u64, at: Instant }

/// dip19 (fix 2/3): one buy of a pre-send position: a fill on the feed, or the balance a confirmed read found (`sig` empty: its tx
/// is not known; `cost` then the spend, an estimate). `round` = the sell round that covers it (0: none yet: the next round sells it).
/// `cost` = what the kill switch values it at while held (spend + fee + tip + the ATA rent: every fill creates the account)
#[derive(Clone, Debug)]
struct Buy { sig: String, w: u64, slot: u64, idx: u64, t_rx: u64, tokens: u64, sol_in: u64, fee: u64, tip: u64, cost: u64, round: u32, via: &'static str }

/// one pre-send position: every buy on the mint from its first fill until its last sell round sold them all
struct PPos {
    /// dip19: the position's id (a sell round's answer names it)
    pid: u64,
    w: u64, mint: Pk, launch: Launch,
    /// dip19: `launch` was derived from the mint (its accounts are resolved from the create tx before the sell)
    derived: bool,
    /// dip19: every buy (the first one opened it): `merged` of them came before its exit, `late` after its exit started
    buys: Vec<Buy>,
    /// the first buy's landing (slot, idx, t_rx): the exit clock
    land: (u64, u64, u64),
    /// the tokens the exit values (the buys before the exit: TP / SL)
    tokens: u64, spend: u64, att: Option<Att>,
    exit: Option<(&'static str, u64, f64, u64)>,
    /// dip19: every sell landing the feed showed (slot, idx, t_rx, curve SOL out) and every sell tx of every round
    sell_lands: Vec<(u64, u64, u64, u64)>, sells: Vec<(String, bool, u64)>,
    /// dip19: sell rounds started (0: no exit yet); a round's sell is under way while `selling`
    round: u32, selling: bool,
    opened: Instant, acct: PsAcct, merged: u32, late: u32, via: &'static str,
}

impl PPos {
    fn sol_in(&self) -> u64 { self.buys.iter().map(|b| b.sol_in).sum() }
    fn sol_out(&self) -> u64 { self.sell_lands.iter().map(|s| s.3).sum() }
    fn tokens_all(&self) -> u64 { self.buys.iter().map(|b| b.tokens).sum() }
    fn fees(&self) -> u64 { self.buys.iter().map(|b| b.fee).sum() }
    fn tips(&self) -> u64 { self.buys.iter().map(|b| b.tip).sum() }
    /// the first buy's signature (dip18's record field)
    fn buy_sig(&self) -> String { self.buys.first().map(|b| b.sig.clone()).unwrap_or_default() }
    /// the curve P&L: every sell's SOL out (as the feed showed them) - every buy's SOL in; None before any sell landing was seen
    fn curve_pnl(&self) -> Option<i64> { (!self.sell_lands.is_empty()).then(|| self.sol_out() as i64 - self.sol_in() as i64) }
    fn buys_json(&self) -> serde_json::Value {
        serde_json::json!(self.buys.iter().map(|b| serde_json::json!({"sig": b.sig, "w": b.w, "slot": b.slot, "idx": b.idx, "t": b.t_rx, "tokens": b.tokens, "sol_in": b.sol_in,
            "fee": b.fee, "tip": b.tip, "cost": b.cost, "round": b.round, "via": b.via})).collect::<Vec<_>>())
    }
}

/// a pre-send position in the run's accounting (the kill switch values it at cost while open; no reactive buy budget used)
struct PsAcct { mint: Pk, cost: u64, open: bool }
impl PsAcct {
    fn open(mint: Pk, cost: u64, slot: u64) -> PsAcct {
        let a = &*ACCT;
        a.inflight.fetch_add(1, Ordering::SeqCst);
        a.open.fetch_add(cost, Ordering::SeqCst);
        a.open_pos.lock().unwrap().insert(mint, cost);
        acct_slot(slot);
        acct_bump();
        PsAcct { mint, cost, open: true }
    }
    fn add(&mut self, more: u64) {
        if !self.open { return; }
        ACCT.open.fetch_add(more, Ordering::SeqCst);
        self.cost += more;
        ACCT.open_pos.lock().unwrap().insert(self.mint, self.cost);
        acct_bump();
    }
    fn sold(&mut self, ctx: u64) {
        if !self.open { return; }
        ACCT.open.fetch_sub(self.cost, Ordering::SeqCst);
        ACCT.open_pos.lock().unwrap().remove(&self.mint);
        acct_slot(ctx);
        acct_bump();
        self.open = false;
    }
    /// dip19: a sell round confirmed (at `ctx`) the buys worth `part`: that part leaves the open total, the rest stays open (a
    /// later round sells it); all of it = sold
    fn sold_part(&mut self, part: u64, ctx: u64) {
        if !self.open { return; }
        if part >= self.cost { self.sold(ctx); return; }
        ACCT.open.fetch_sub(part, Ordering::SeqCst);
        self.cost -= part;
        ACCT.open_pos.lock().unwrap().insert(self.mint, self.cost);
        acct_slot(ctx);
        acct_bump();
    }
}
impl Drop for PsAcct {
    fn drop(&mut self) {
        if self.open { ACCT.open.fetch_sub(self.cost, Ordering::SeqCst); ACCT.open_pos.lock().unwrap().remove(&self.mint); }
        ACCT.inflight.fetch_sub(1, Ordering::SeqCst);
        acct_bump();
    }
}

/// messages back to the event loop (sells, token-account reads, closes)
pub enum PsMsg {
    /// a sell round finished: (mint, position id, round, its sells)
    Sold(Pk, u64, u32, SellOut),
    /// dip19: a CONFIRMED token-account read: (mint, what for, the slot it had to reach, how many reads so far, the answer;
    /// Unknown = unreadable: retried, never read as 0)
    Read(Pk, Why, u64, u32, crate::Tok),
    /// dip19: a close of a kept-open token account: (mint, its signature, Some(slot) = landed OK / None = failed or not seen, why)
    Closed(Pk, String, Option<u64>, String),
    /// dip19: the background UNSOLD retry of a pre-send position ended (true: sold, the account confirmed empty)
    UnsoldDone(Pk, bool),
}

/// dip19: what a token-account read is for
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Why {
    /// window w settled (every attempt resolved, its quiet slot + 2 passed): a balance with no position open is an ORPHAN
    Window(u64),
    /// a sold position's kept-open account, before its close: 0 = close it, a balance = an ORPHAN
    Close,
}

/// dip19: the probe's chain work (the answers come back to on_msg as PsMsg). A run spawns each at once on the engine's runtime;
/// the tests queue them and answer them (no RPC, no send, no Telegram)
#[derive(Clone, Debug)]
pub enum Cmd {
    /// sell round `round` of position `pid`: `known` exact tokens (else a `guess`), confirmed reads from `land_slot` on;
    /// `keep_ata`: the account stays open (every pre-send sell); `read_first`: a confirmed read before the first send (never set by
    /// the probe: its sells go out at once, M4-1); `derived`: the launch's accounts are resolved from the create tx first
    Sell { mint: Pk, pid: u64, round: u32, launch: Launch, derived: bool, known: Option<u64>, guess: u64, land_slot: u64, read_first: bool, keep_ata: bool },
    /// a CONFIRMED read of our token account of `mint` from a node at slot >= `min_slot`; `n` = reads of it so far
    Read { mint: Pk, min_slot: u64, why: Why, n: u32 },
    /// close our (confirmed empty) token account of `mint`: the rent back
    Close { mint: Pk },
    /// a position's realized P&L from its transactions: every buy (sig, cost estimate when not found) and every sell
    Realized { pid: u64, w: u64, mint: Pk, buys: Vec<(String, u64)>, sells: Vec<(String, bool, u64)> },
    /// the background UNSOLD retry of a position (its sells keep the account open; PsMsg::UnsoldDone at its end)
    Unsold { mint: Pk, launch: Launch, land_slot: u64, last_qty: (u64, bool) },
    /// a Telegram alert (the tests keep its title; a run raises it at once, never through this)
    #[allow(dead_code)]
    Alert { level: arbx::alerts::Level, title: String },
}

/// dip19 (fix 1): our token account of a mint, from the fill that created it until a read shows it closed
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum AtaSt {
    /// a position holds it (or its background UNSOLD retry)
    Held,
    /// sold, empty, KEPT OPEN (the attempts' double-fill guard): read (then closed on a confirmed 0) once close_due
    Idle,
    /// its read or close is under way
    Busy,
    /// CLOSE_TRIES closes failed: left open (the run's end tries once more)
    GaveUp,
}
#[derive(Clone, Copy, Debug)]
struct Ata { st: AtaSt, not_before: Option<Instant>, min_slot: u64, reads: u32, closes: u32 }
/// closes of one account before it is left to the run's end
const CLOSE_TRIES: u32 = 3;
/// the close: Token-2022 CloseAccount only (a few thousand CU); the attempts' CU price (it is not urgent)
const CLOSE_CU: u32 = 20_000;

/// dip19 (fix 1): may a kept-open token account be read for its close now: no attempt of the mint can land any more (`quiet` =
/// its last deadline, incl. one built as its window was disarmed) for 2 slots, no window armed on it, no position open on it
pub fn close_due(slot_now: u64, quiet: u64, armed: bool, pos_open: bool) -> bool { !armed && !pos_open && slot_now > quiet + 2 }

/// dip22: a position's time exit (pure; unit-tested). `held_ms`: since our fill was seen. --presend-live-exit-ms N > 0 sells first,
/// N ms after the fill ("time-ms"); then the slot limit (entry slot + exit_slots) and the wall-clock backstop (the feed stalled), as before
pub fn time_exit_due(slot_now: u64, land_slot: u64, exit_slots: u64, held_ms: u64, exit_ms: u64) -> Option<&'static str> {
    if exit_ms > 0 && held_ms >= exit_ms { return Some("time-ms"); }
    if slot_now >= land_slot + exit_slots { return Some("time-limit"); }
    if held_ms > exit_slots * 400 + 3_000 { return Some("time-limit-wall"); }
    None
}

/// dip19 (fix 3): a position's realized P&L from its transactions: every buy's payer delta (its spend, fees, tips and the ATA
/// rent), a buy whose tx is not found (or not known: a balance a read found) at minus its cost estimate, plus every sell's payer
/// delta (a sell not found: 0, as dip18). `buys` = (tx answer, cost), `sells` = tx answers. -> (pnl, buys found, sells found)
pub fn pnl_of(buys: &[(Option<(i64, u64, bool)>, u64)], sells: &[Option<(i64, u64, bool)>]) -> (i64, usize, usize) {
    let (mut pnl, mut nb, mut ns) = (0i64, 0usize, 0usize);
    for (b, cost) in buys { match b { Some((d, _, _)) => { pnl += d; nb += 1; } None => pnl -= *cost as i64 } }
    for s in sells.iter().flatten() { pnl += s.0; ns += 1; }
    (pnl, nb, ns)
}

/// dip19 (fix 4): what the run's end does with a mint after its confirmed read
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum EndAct { Nothing, Sell(u64), Close, Unreadable }
pub fn end_act(t: crate::Tok) -> EndAct {
    match t { crate::Tok::Amount(n, _) if n > 0 => EndAct::Sell(n), crate::Tok::Amount(..) => EndAct::Close, crate::Tok::Closed(_) => EndAct::Nothing, crate::Tok::Unknown => EndAct::Unreadable }
}

/// per path / per leader client: [sent, ok, 6042, deadline, ata_exists, other, unseen]
type Cnt = [u64; 7];

#[derive(Default)]
struct Stats {
    triggers: u64, armed: u64, skips: FxHashMap<&'static str, u64>, disarms: FxHashMap<&'static str, u64>, fills: u64, late_fills: u64, unexpected: u64, fees: u64, fee_fills: u64,
    tips: u64, exits: u64, closed: u64, unsold: u64, landed: FxHashMap<String, u64>, per_path: FxHashMap<String, Cnt>,
    per_client: FxHashMap<String, Cnt>, parity_matched: u64, parity_live_only: u64, parity_shadow_only: u64, held_checks: u64, held_found: u64, us: Ring,
    /// dip19: fills on a position whose exit had started, its follow-up sell rounds, orphans found (sold), unreadable reads (retried),
    /// kept-open accounts closed / close reads / closes failed
    after_exit: u64, follow_ups: u64, orphans: u64, unreadable: u64, ata_closed: u64, ata_reads: u64, ata_close_fail: u64,
    /// dip23 (--presend-live-quiet-v2-log): arms / skips whose v2 candidate said skip (true) or keep (false)
    v2_arm: [u64; 2], v2_skip: [u64; 2],
}

fn cnt_add(m: &mut FxHashMap<String, Cnt>, k: &str, i: usize) { m.entry(k.to_string()).or_default()[i] += 1; }

/// the probe in the event loop
pub struct PsLive {
    pub cfg: Cfg,
    det: pl::Detector,
    wins: FxHashMap<u64, Win>,
    armed: FxHashMap<Pk, u64>,
    wid: u64,
    sh: Arc<Shared>,
    arx: crossbeam_channel::Receiver<Att>,
    atts: FxHashMap<[u8; 64], (Att, bool)>,
    order: VecDeque<(u64, [u8; 64], Instant)>,
    lands: Vec<Land>,
    tapes: FxHashMap<Pk, (VecDeque<pl::Trade>, u64)>,
    pos: FxHashMap<Pk, PPos>,
    free_at: FxHashMap<Pk, Instant>,
    last_deadline: FxHashMap<Pk, u64>,
    /// the launch accounts of every token armed lately (its fills / held checks are sold with them)
    launches: FxHashMap<Pk, Launch>,
    last_sweep: u64,
    /// token-account checks under way (their answer may open a position: the run waits for them)
    checks: u64,
    /// parity with the shadow: live triggers waiting for the shadow's presend_arm (key: mint, signature, event index)
    par: FxHashMap<(String, String, i64), (u64, serde_json::Value)>,
    st: Stats,
    out: crossbeam_channel::Sender<Out>,
    thread: Option<std::thread::JoinHandle<()>>,
    user: Pk, key: Arc<SigningKey>, rpc: Arc<rpc::Rpc>, path: Option<Arc<send::Path>>, mtx: tokio::sync::mpsc::UnboundedSender<Msg>, allow_holder: bool,
    stopped: Option<&'static str>,
    /// when stop() ran (dip15: the run ends a grace period after it even when the bookkeeping never goes idle)
    stopped_at: Option<Instant>,
    /// dip19: the tests' queue of the chain work (None: a run spawns it at once)
    q: Option<Vec<Cmd>>,
    /// dip19: the last position id
    pid: u64,
    /// dip19 (fix 1): our token accounts the attempts created (or a read found), until one is seen closed
    atas: FxHashMap<Pk, Ata>,
    /// dip19 (fix 1): per mint, the slot after which no attempt can land any more (every deadline; a disarm's sender slot +
    /// the deadline slots)
    quiet: FxHashMap<Pk, u64>,
    /// dip19 (fix 4): every mint the run's end must read (filled, found holding, read unreadable): the slot the read must reach
    ends: FxHashMap<Pk, u64>,
    /// dip19 (fix 2): unreadable reads waiting for their retry (when, the read)
    retry: Vec<(Instant, Cmd)>,
    /// dip19 (fix 4): the window reads under way (mint -> the slot each must reach): the run's end reads these mints too
    reading: FxHashMap<Pk, u64>,
    /// dip19: the probe's spawned sells / reads / closes still running (the run's end waits for them)
    tasks: Arc<AtomicU64>,
    /// dip20 QUIET (None: every QUIET flag off, nothing of it runs)
    qt: Option<Quiet>,
    /// dip23 (--presend-live-quiet-v2-log; None without it): the per-token 120 s price ring of the QUIET v2 annotation (log-only)
    v2: Option<pq::V2Ring>,
    /// dip24: the failed-attempt fees of the last 24 h per second of the feed clock ((unix s, lamports)), their sum, the pause state,
    /// pauses so far, the feed's latest arrival time (the rolling window's clock)
    fee_q: VecDeque<(u64, u64)>, fee_24h: u64, fee_paused: bool, fee_pauses: u64, last_t: u64,
}

impl PsLive {
    /// start the probe: the routes, the writer and sender threads; the feed's failed-transaction side channel for our wallet
    #[allow(clippy::too_many_arguments)]
    pub fn start(cfg: Cfg, key: Arc<SigningKey>, user: Pk, rpc: &Arc<rpc::Rpc>, path: &Arc<send::Path>, log: &Arc<DipLog>, mtx: tokio::sync::mpsc::UnboundedSender<Msg>,
                 allow_holder: bool, cohort: &std::collections::HashSet<String>) -> Result<PsLive> {
        let guard = SLOT_GUARD.get().map(|g| g.0).context("--presend-live needs --buy-max-slot-delta N (the on-chain slot deadline, verified at start)")?;
        // dip20 QUIET: the follower-bot list is read (and refused when bad) before any thread starts
        let fbots = match (&cfg.quiet.fbots, cfg.quiet.skip) { (Some(f), true) => load_fbots(f)?, _ => FxHashSet::default() };
        let paths = ALL_PATHS.get().context("--presend-live: the send paths are not built")?;
        let reactive = reactive_paths(path);
        let rmap = parse_routes(&cfg.routes, paths, &reactive, cfg.tip)?;
        if rmap.keys().any(|c| c != "default") && lat::BOOK.read().unwrap().is_none() { bail!("--presend-live-routes by leader class needs the leader book: add --route-by-client (or use default=... only)"); }
        let fast = fastfire::get();
        let mut routes: FxHashMap<String, Vec<RouteP>> = FxHashMap::default();
        let mut desc = Vec::new();
        for (c, ps) in &rmap {
            let v: Vec<RouteP> = ps.iter().map(|p| {
                let f = fast.and_then(|f| f.fps.iter().find(|x| x.path.name == p.name)).and_then(|x| match &x.kind { fastfire::Kind::Http { conn, json } => Some((conn.clone(), *json)), _ => None });
                RouteP { path: p.clone(), fast: f, bucket: send::TokenBucket::new(cfg.path_max_per_sec as f64, (cfg.path_max_per_sec as u32 / 4).max(1)) }
            }).collect();
            desc.push(format!("{c}={}", v.iter().map(|r| format!("{}{}", r.path.name, if r.fast.is_some() { "(fast)" } else { "(async)" })).collect::<Vec<_>>().join("+")));
            routes.insert(c.clone(), v);
        }
        desc.sort();
        let slot_ns = arbx::feeds::entries::SLOT_US.load(Ordering::Relaxed) * 1_000;
        let out = spawn_writer(log.clone());
        let (atx, arx) = crossbeam_channel::unbounded::<Att>();
        let sh = Arc::new(Shared { wins: Mutex::new(Vec::new()), stop: AtomicBool::new(false), pause_reactive: AtomicBool::new(false), pause_pos: AtomicBool::new(false), pause_fee: AtomicBool::new(false),
            slot: AtomicU64::new(0), seq: AtomicU64::new(0), sent: AtomicU64::new(0), dry: AtomicU64::new(0), exited: AtomicBool::new(false), skips: Mutex::new(FxHashMap::default()), build_us: Mutex::new(Ring::default()) });
        arbx::feeds::own_fail_watch(user);
        let sc = SCfg { cfg: cfg.clone(), user, key: (*key).clone(), guard, routes, handle: tokio::runtime::Handle::current() };
        let fee1 = cfg.fail_fee();
        let line = format!("DIP PRESEND LIVE{} | T2 whale >= {}% -> window {} slots from +{} ms (create-slot triggers {}) | {} attempts per slot ({:.0} ms apart), {:.3} SOL, limit = latest price x {:.2}, \
            deadline slot + {} | CU {} x {} uL (a failed attempt {} lamports) | routes {} | caps: {} fills, fees {:.4} SOL per rolling 24 h (pause), {} attempts/s ({} per path) | one position {} | exit {} slots{} / TP +{:.0}% / SL -{:.0}%",
            if cfg.dry { " DRY (builds + signs + logs; NEVER sends)" } else { " (REAL attempts)" }, cfg.whale_pct, cfg.window_slots, cfg.live_ms, if cfg.create_slot { "on" } else { "skipped" },
            cfg.k, slot_ns as f64 / 1e6 / cfg.k as f64, cfg.spend as f64 / 1e9, 1.0 - cfg.drop, cfg.deadline_slots, cfg.cu_limit, cfg.cu_price, fee1, desc.join(";"), if cfg.max_fills == 0 { "unlimited".to_string() } else { cfg.max_fills.to_string() },
            cfg.fee_budget as f64 / 1e9, cfg.max_per_sec, cfg.path_max_per_sec, if cfg.one_position { "on" } else { "off" }, cfg.exit_slots,
            if cfg.exit_ms > 0 { format!(" or {} ms after the fill (dip22, first)", cfg.exit_ms) } else { String::new() }, cfg.tp * 100.0, cfg.sl * 100.0);
        eprintln!("{line}");
        let thread = {
            let (sh, out) = (sh.clone(), out.clone());
            std::thread::Builder::new().name("ps-send".into()).spawn(move || sender(sh, sc, out, atx)).context("ps-send thread")?
        };
        if !cfg.dry {
            tg::raise(arbx::alerts::Level::Info, "dip_presend_live", "start", "🧪", "PRESEND LIVE probe ON", arbx::alerts::format::Body::new()
                .kv("size", format!("{:.3} SOL", cfg.spend as f64 / 1e9)).kv("attempts", format!("{} per slot, {} lamports each when failed", cfg.k, fee1))
                .kv("caps", format!("{} fills, {:.4} SOL fees per rolling 24 h", if cfg.max_fills == 0 { "unlimited".to_string() } else { cfg.max_fills.to_string() }, cfg.fee_budget as f64 / 1e9)), false);
        }
        let mut det = pl::Detector::new(cfg.whale_pct);
        det.idle_slots = 6 * 3600 * 1000 / 212;
        // dip20 QUIET: its state (None without its flags), the preload thread (background, lowest CPU priority; its answer is merged
        // in tick())
        // dip21: the state journal first (its dumps are history at once and go with the preload), its writer, then the preload
        let (mut qstate, mut qrec): (Vec<String>, Option<serde_json::Value>) = (Vec::new(), None);
        let qt = cfg.quiet.on().then(|| {
            let mut q = Quiet::new(&cfg.quiet, cohort, fbots, arbx::feeds::clock::now_ns(), true);
            if let Some((line, rec, compacted)) = q.open_state(q.start_ns) {
                qstate.push(line);
                qrec = Some(rec);
                if let Some(w) = compacted.and_then(|c| q.spawn_journal(c)) { qstate.push(w); }
            }
            q.spawn_preload(Duration::from_secs(25 * 60));
            q
        });
        if let Some(q) = &qt {
            eprintln!("DIP PRESEND LIVE QUIET: stop {} | skip {}{}", q.cfg.stop.map(|s| format!("at trigger + {} slots with < {} other trades", s.n, s.m)).unwrap_or("off".into()),
                if q.cfg.skip { format!("on: all 4 signals (since_last >= 1, no cohort holder ({} wallets), < 2 follower bots ({} wallets), whale's dumps of the last {} h drew < {} buyers or none)",
                    q.coh.len(), q.fb.len(), q.cfg.hist_h, q.cfg.fol) } else { "off".into() },
                if q.cfg.skip { format!(" | arm rule from {} (warm-up {} min){}", ts_pkt(q.arm_at()), q.cfg.warmup_min,
                    match q.pre { PreSt::Running => format!("; preload of {} h from {} RUNNING (the arm rule turns on when it is merged)", q.cfg.hist_h, q.cfg.preload.as_deref().unwrap_or("")),
                                  PreSt::Failed => format!("; preload FAILED to start: {}", q.pre_info), _ => String::new() }) } else { String::new() });
        }
        for l in &qstate { eprintln!("{l}"); }
        // dip23: the v2 annotation (log-only) and its ring
        let v2_log = cfg.quiet_v2_log;
        if v2_log { eprintln!("DIP PRESEND LIVE QUIET v2 LOG: every arm / skip record gets \"v2\" (trades in 60 s, at the 120 s high, drawdown, candidate skip = <= {} trades AND at the high); LOG ONLY, nothing acts on it", pq::V2_N_MAX); }
        let p = PsLive { cfg, det, wins: FxHashMap::default(), armed: FxHashMap::default(), wid: 0, sh, arx, atts: FxHashMap::default(), order: VecDeque::new(), lands: Vec::new(),
            tapes: FxHashMap::default(), pos: FxHashMap::default(), free_at: FxHashMap::default(), last_deadline: FxHashMap::default(), launches: FxHashMap::default(), last_sweep: 0, checks: 0,
            par: FxHashMap::default(),
            st: Stats::default(), out, thread: Some(thread), user, key, rpc: rpc.clone(), path: Some(path.clone()), mtx, allow_holder, stopped: None, stopped_at: None,
            q: None, pid: 0, atas: FxHashMap::default(), quiet: FxHashMap::default(), ends: FxHashMap::default(), retry: Vec::new(), reading: FxHashMap::default(),
            tasks: Arc::new(AtomicU64::new(0)), qt, v2: v2_log.then(pq::V2Ring::new), fee_q: VecDeque::new(), fee_24h: 0, fee_paused: false, fee_pauses: 0, last_t: 0 };
        if let Some(r) = qrec { p.rec(r); }
        Ok(p)
    }

    fn rec(&self, v: serde_json::Value) { let _ = self.out.send(Out::Rec(v)); }
    fn line(&self, l: String) { let _ = self.out.send(Out::Line(l)); }

    /// the attempts the sender registered
    fn drain_atts(&mut self) {
        while let Ok(a) = self.arx.try_recv() {
            if let Some(w) = self.wins.get_mut(&a.w) { w.sent += 1; w.last_deadline = w.last_deadline.max(a.deadline); }
            let e = self.last_deadline.entry(a.mint).or_default(); *e = (*e).max(a.deadline);
            let q = self.quiet.entry(a.mint).or_default(); *q = (*q).max(a.deadline);
            cnt_add(&mut self.st.per_path, &a.path, 0);
            cnt_add(&mut self.st.per_client, &a.client, 0);
            self.order.push_back((a.deadline, a.sig, Instant::now()));
            self.atts.insert(a.sig, (a, false));
        }
    }

    /// the reactive bot must not buy `mint` now (a pre-send position on it / any while one is open with one position per server /
    /// attempts armed or in flight on it): the reason
    pub fn blocks_reactive(&self, mint: &Pk) -> Option<&'static str> {
        if self.pos.contains_key(mint) { return Some("presend_position"); }
        if self.cfg.one_position && !self.pos.is_empty() { return Some("presend_position_open"); }
        if self.armed.contains_key(mint) || self.last_deadline.get(mint).is_some_and(|&d| d >= self.sh.slot.load(Ordering::Relaxed)) { return Some("presend_armed"); }
        None
    }

    /// the reactive bot's open positions now (one position per server: the attempts pause while it holds one)
    pub fn reactive_open(&self, n: usize) { self.sh.pause_reactive.store(n > 0, Ordering::Relaxed); }

    /// nothing left to do (positions closed, attempts resolved, records written)
    pub fn idle(&self) -> bool {
        // after a stop the sender must have left its loop (an attempt built at that moment is still registered and watched)
        (self.stopped.is_none() || self.sh.exited.load(Ordering::SeqCst)) && self.arx.is_empty() && self.pos.is_empty() && self.checks == 0
            && self.atts.values().all(|x| x.1) && self.lands.is_empty() && self.wins.values().all(|w| w.disarmed.is_some() && w.resolved >= w.sent)
    }

    /// the run may end: idle, or no pre-send position open and `grace` since the stop. dip15 fix: AMS run 17 (10-25) sent 3,429
    /// attempts, resolved 3,420 and never went idle, so the engine never exited; finish() resolves what is left as unseen
    pub fn can_end(&self, grace: Duration) -> bool {
        self.idle() || (self.pos.is_empty() && self.stopped_at.is_some_and(|t| t.elapsed() >= grace))
    }

    /// which idle() condition still holds the run (the forced end's log line)
    pub fn not_idle_why(&self) -> String {
        let mut v: Vec<String> = Vec::new();
        if !(self.stopped.is_none() || self.sh.exited.load(Ordering::SeqCst)) { v.push("sender thread still in its loop".into()); }
        if !self.arx.is_empty() { v.push("attempt registrations queued".into()); }
        if !self.pos.is_empty() { v.push(format!("{} position(s) open", self.pos.len())); }
        if self.checks != 0 { v.push(format!("{} token-account check(s) pending", self.checks)); }
        let un = self.atts.values().filter(|x| !x.1).count();
        if un > 0 { v.push(format!("{un} attempt(s) unresolved")); }
        if !self.lands.is_empty() { v.push(format!("{} landing record(s) pending", self.lands.len())); }
        let ws: Vec<String> = self.wins.values().filter(|w| !(w.disarmed.is_some() && w.resolved >= w.sent))
            .map(|w| format!("w{} sent {} resolved {}{}", w.id, w.sent, w.resolved, if w.disarmed.is_none() { " armed" } else { "" })).collect();
        if !ws.is_empty() { v.push(format!("window(s) not settled: {}", ws.join(", "))); }
        if v.is_empty() { "nothing".into() } else { v.join("; ") }
    }

    /// every executed or unexecuted arrival, before its pump events: our failed attempts (no pump event, so no ExecInfo)
    pub fn on_arrival(&mut self, a: &arbx::feeds::Arrival, slot_now: u64) {
        self.sh.slot.store(slot_now, Ordering::Relaxed);
        self.last_t = self.last_t.max(a.t_rx);
        if a.executed != Some(false) || a.tx.keys.first() != Some(&self.user) { return; }
        self.drain_atts();
        let Some((att, done)) = self.atts.get_mut(&a.tx.sig) else { return };
        if *done { return; }
        *done = true;
        let att = att.clone();
        let of = arbx::feeds::own_fail_take(&a.tx.sig);
        let (idx, fee, err) = match &of { Some(f) => (Some(f.index), f.fee, f.err.clone()), None => (None, self.cfg.fail_fee(), "?".to_string()) };
        let res = if of.is_some() { pl::classify(&err, &att.roles) } else { "failed_unknown".to_string() };
        self.st.fees += fee;
        self.resolve(&att, &res);
        self.lands.push(Land { att, res, err, fee, slot: a.slot, idx, t_rx: a.t_rx, at: Instant::now() });
        // dip24: the rolling 24 h budget (pauses the sender, never stops the stream)
        self.fee_add(a.t_rx, fee);
    }

    /// dip24: a failed attempt's fee into the ROLLING 24 h budget; at the budget the sender pauses (loudly) until the sum rolls back
    /// under it; the stream is never stopped by it
    fn fee_add(&mut self, t: u64, fee: u64) {
        let s = t / 1_000_000_000;
        match self.fee_q.back_mut() { Some(b) if b.0 == s => b.1 += fee, _ => self.fee_q.push_back((s, fee)) }
        self.fee_24h += fee;
        self.last_t = self.last_t.max(t);
        self.fee_roll();
        if !self.fee_paused && self.fee_24h >= self.cfg.fee_budget {
            self.fee_paused = true;
            self.fee_pauses += 1;
            self.sh.pause_fee.store(true, Ordering::SeqCst);
            self.line(format!("  PRESEND LIVE PAUSED (fee budget): failed-attempt fees of the last 24 h {:.6} SOL >= {:.6} SOL: NO NEW ATTEMPTS until they roll back under \
                (pause #{}; the run goes on)", self.fee_24h as f64 / 1e9, self.cfg.fee_budget as f64 / 1e9, self.fee_pauses));
            self.rec(serde_json::json!({"ev": "presend_live_fee_pause", "t": t, "fees_24h": self.fee_24h, "budget": self.cfg.fee_budget, "fees_total": self.st.fees, "n": self.fee_pauses}));
            if !self.cfg.dry && self.q.is_none() {
                tg::raise(arbx::alerts::Level::Warning, "dip_presend_fee_pause", "pause", "⏸️", "PRESEND LIVE paused: 24 h fee budget", arbx::alerts::format::Body::new()
                    .kv("fees 24 h", format!("{:.4} SOL", self.fee_24h as f64 / 1e9)).kv("budget", format!("{:.4} SOL", self.cfg.fee_budget as f64 / 1e9)), false);
            }
        }
    }

    /// dip24: the fees older than 24 h (feed clock) leave the rolling sum; a paused sender resumes under the budget
    fn fee_roll(&mut self) {
        let lo = (self.last_t / 1_000_000_000).saturating_sub(24 * 3600);
        while self.fee_q.front().is_some_and(|x| x.0 < lo) { let (_, f) = self.fee_q.pop_front().unwrap(); self.fee_24h = self.fee_24h.saturating_sub(f); }
        if self.fee_paused && self.fee_24h < self.cfg.fee_budget {
            self.fee_paused = false;
            self.sh.pause_fee.store(false, Ordering::SeqCst);
            self.line(format!("  PRESEND LIVE RESUMED (fee budget): failed-attempt fees of the last 24 h {:.6} SOL < {:.6} SOL", self.fee_24h as f64 / 1e9, self.cfg.fee_budget as f64 / 1e9));
            self.rec(serde_json::json!({"ev": "presend_live_fee_resume", "t": self.last_t, "fees_24h": self.fee_24h, "budget": self.cfg.fee_budget}));
        }
    }

    /// dip24 (tests): the sender is paused by the fee budget
    #[cfg(test)]
    pub fn fee_paused(&self) -> bool { self.fee_paused && self.sh.pause_fee.load(Ordering::SeqCst) }

    fn resolve(&mut self, att: &Att, res: &str) {
        if let Some(w) = self.wins.get_mut(&att.w) { w.resolved += 1; if res == "unseen" { w.unseen += 1; } }
        let i = match res { "ok" => 1, "6042" => 2, "deadline" => 3, "ata_exists" => 4, "unseen" => 6, _ => 5 };
        cnt_add(&mut self.st.per_path, &att.path, i);
        cnt_add(&mut self.st.per_client, &att.client, i);
        *self.st.landed.entry(res.to_string()).or_default() += 1;
    }

    /// stop the stream for good (caps / run end): every window disarmed, no new ones
    pub fn stop(&mut self, why: &'static str) {
        if self.stopped.is_some() { return; }
        self.stopped = Some(why);
        self.stopped_at = Some(Instant::now());
        self.sh.stop.store(true, Ordering::SeqCst);
        let ids: Vec<u64> = self.wins.iter().filter(|(_, w)| w.disarmed.is_none()).map(|(k, _)| *k).collect();
        for id in ids { self.disarm(id, "stopped"); }
        self.line(format!("  PRESEND LIVE STOPPED ({why}): no new attempts; open positions finish their exit | fills {} / {} | failed-attempt fees {:.6} / {:.6} SOL", self.st.fills, self.cfg.max_fills,
            self.st.fees as f64 / 1e9, self.cfg.fee_budget as f64 / 1e9));
        self.rec(serde_json::json!({"ev": "presend_live_stop", "why": why, "t": arbx::feeds::clock::now_ns(), "fills": self.st.fills, "fees": self.st.fees}));
        if !self.cfg.dry && why != "run_end" {
            tg::raise(arbx::alerts::Level::Info, "dip_presend_live", "stop", "🧪", &format!("PRESEND LIVE stopped: {why}"), arbx::alerts::format::Body::new()
                .kv("fills", self.st.fills.to_string()).kv("failed-attempt fees", format!("{:.4} SOL", self.st.fees as f64 / 1e9)), false);
        }
    }

    fn disarm(&mut self, id: u64, why: &'static str) {
        let Some(w) = self.wins.get_mut(&id) else { return };
        if w.disarmed.is_some() { return; }
        w.disarmed = Some(why);
        // dip19: an attempt the sender took before this disarm can still be registered after it; its deadline is at most the
        // sender's slot now + the deadline slots (the sender reads its slot before it takes the windows)
        w.quiet = self.sh.cur_slot() + self.cfg.deadline_slots;
        let q = self.quiet.entry(w.mint).or_default(); *q = (*q).max(w.quiet);
        if self.armed.get(&w.mint) == Some(&id) { self.armed.remove(&w.mint); }
        { let mut g = self.sh.wins.lock().unwrap(); g.retain(|x| x.id != id); }
        *self.st.disarms.entry(why).or_default() += 1;
        let mut r = serde_json::json!({"ev": "presend_live_disarm", "w": id, "mint": b58(&w.mint), "why": why, "t": arbx::feeds::clock::now_ns(), "trig_slot": w.trig_slot, "en_slot": w.en_slot,
            "slot": self.sh.slot.load(Ordering::Relaxed), "armed_ms": w.armed_at.elapsed().as_secs_f64() * 1e3, "attempts": w.sent, "filled": w.filled});
        // dip20 QUIET (only with it): the stop's verdict, the "other" trades counted (at the stop's decision, or so far when the window
        // ended before it), the arm's signals
        if let Some(qs) = self.qt.as_ref() {
            let others = w.q_others.or_else(|| w.qkey.and_then(|k| qs.watch.get(&w.mint).and_then(|v| v.iter().find(|x| x.id == k)).map(|x| x.others)));
            let mut j = w.qj.clone().unwrap_or_else(|| serde_json::json!({}));
            j["others"] = others.into();
            j["decided"] = w.q_others.is_some().into();
            r["quiet"] = j;
            r["quiet_stop"] = (why == "quiet").into();
        }
        self.rec(r);
    }

    /// an executed tx with pump events (after the reactive bot's decisions and sends of it): creates, triggers, the windows'
    /// prices, our fills, the positions' exits
    #[allow(clippy::too_many_arguments)]
    pub fn on_exec(&mut self, a: &arbx::feeds::Arrival, x: &arbx::feeds::ExecInfo, slot_now: u64, launch_of: impl Fn(&Pk) -> Option<Launch>,
                   reactive_open: &dyn Fn(&Pk) -> bool, first: Option<&FxHashMap<u64, (u64, u16)>>) {
        let t0 = Instant::now();
        self.sh.slot.store(slot_now, Ordering::Relaxed);
        for c in &x.creates { self.det.create(c.mint, a.slot, c.creator, c.user, x.mayhem); }
        let mut evs: Vec<pl::Det> = Vec::new();
        for (j, e) in x.trades.iter().enumerate() {
            let t = pl::Trade { mint: e.mint, s: a.slot, i: x.index as u32, j: j as i32, sig: a.tx.sig, user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok,
                fbps: e.fbps, cbps: e.cbps, t_rx: a.t_rx };
            // our own trades: a pre-sent attempt filled / our pre-send sell landed
            if e.user == self.user {
                if e.buy {
                    self.drain_atts();
                    if self.atts.contains_key(&a.tx.sig) { self.fill(&t, x.fee, reactive_open(&e.mint)); }
                } else if let Some(p) = self.pos.get_mut(&e.mint) {
                    // dip19: every sell landing is kept (a round's remainder sell, a follow-up round's): the curve P&L sums them all
                    p.sell_lands.push((a.slot, x.index, a.t_rx, e.sol));
                    let r = serde_json::json!({"ev": "presend_live_sell_land", "w": p.w, "mint": b58(&e.mint), "sig": bs58::encode(&a.tx.sig).into_string(), "slot": a.slot, "idx": x.index,
                        "t": a.t_rx, "sol": e.sol, "fee": x.fee, "pid": p.pid, "round": p.round});
                    self.rec(r);
                }
            }
            // the tape of tokens with a window / attempts / a position
            if let Some((tp, _)) = self.tapes.get_mut(&e.mint) { tp.push_back(t.clone()); if tp.len() > 256 { tp.pop_front(); } }
            if self.pos.contains_key(&e.mint) {
                self.rec(serde_json::json!({"ev": "presend_live_tape", "mint": b58(&e.mint), "sig": bs58::encode(&a.tx.sig).into_string(), "slot": a.slot, "idx": x.index, "j": j,
                    "t": a.t_rx, "user": b58(&e.user), "buy": e.buy, "sol": e.sol, "tok": e.tok, "vsol": e.vsol, "vtok": e.vtok}));
            }
            // the armed window's latest curve state (the next attempt's limit)
            if let Some(&id) = self.armed.get(&e.mint) {
                let mut g = self.sh.wins.lock().unwrap();
                if let Some(w) = g.iter_mut().find(|w| w.id == id) { w.vsol = e.vsol; w.vtok = e.vtok; w.fr = t.fr(); w.pos = t.pos(); }
            }
            // dip20 QUIET: the whale dump history takes every trade (its first one sets the preload's cut: that slot + 1); the stop
            // watches count the "other" trades (a trigger's own trade never: its watch is made below, in trigger())
            if let Some(q) = self.qt.as_mut() {
                if let Some(b) = q.book.as_mut() {
                    if q.cut.load(Ordering::Relaxed) == 0 {
                        q.cut.store(a.slot + 1, Ordering::SeqCst);
                        // dip21: this session's first slot (the journal's start marker: its coverage begins here)
                        q.c0 = a.slot;
                        if let Some(tx) = &q.jtx { let _ = tx.send(pq::JMsg::Start { t: a.t_rx, s: a.slot }); }
                    }
                    b.ingest(e, a.slot, x.index as u32, j as i32, a.t_rx);
                }
                if !q.watch.is_empty() {
                    if let Some(v) = q.watch.get_mut(&e.mint) { for w in v.iter_mut() { if pq::QStop::other(&e.user, &w.whale, &self.user) { w.others += 1; } } }
                }
            }
            evs.clear();
            self.det.trade(&t, &mut evs);
            for ev in evs.drain(..) {
                match ev {
                    pl::Det::Trigger { whale, pct, bal, age_slots } => self.trigger(&t, whale, pct, bal, age_slots, &launch_of, reactive_open),
                    pl::Det::WhaleSell { whale } => {
                        if let Some(&id) = self.armed.get(&e.mint) {
                            if let Some(w) = self.wins.get_mut(&id) {
                                if w.whale == whale && w.stop_at.is_none() {
                                    let at = Instant::now() + Duration::from_millis(WHALE_SELL_MS);
                                    w.stop_at = Some(at);
                                    let stop_ns = arbx::fast::mono_ns() + WHALE_SELL_MS * 1_000_000;
                                    let mut g = self.sh.wins.lock().unwrap();
                                    if let Some(s) = g.iter_mut().find(|s| s.id == id) { s.stop_ns = s.stop_ns.min(stop_ns); }
                                }
                            }
                        }
                    }
                    pl::Det::Gone => { if let Some(&id) = self.armed.get(&e.mint) { self.disarm(id, "token_gone"); } }
                    pl::Det::Below => {}
                }
            }
            // dip23 v2 (log-only): the ring takes the trade AFTER its trigger decision (the features of a trigger see only the trades
            // before it)
            if let Some(v) = self.v2.as_mut() { v.push(&e.mint, a.t_rx, t.p()); }
            // a pre-send position's exit on this price (take-profit / stop-loss: at once)
            if e.user != self.user {
                if let Some(p) = self.pos.get_mut(&e.mint) {
                    if p.exit.is_none() && p.tokens > 0 {
                        let v = pl::value(e.vsol, e.vtok, p.tokens, t.fr(), p.spend);
                        let why = if self.cfg.tp > 0.0 && v >= 1.0 + self.cfg.tp { Some("take-profit") } else if self.cfg.sl > 0.0 && v <= 1.0 - self.cfg.sl { Some("stop-loss") } else { None };
                        if let Some(why) = why { let m = e.mint; self.exit(&m, why, a.slot, v, a.t_rx); }
                    }
                }
            }
        }
        self.tick(slot_now, first);
        self.st.us.add((t0.elapsed().as_secs_f64() * 1e6) as f32);
    }

    #[allow(clippy::too_many_arguments)]
    fn trigger(&mut self, t: &pl::Trade, whale: Pk, pct: f64, bal: i64, age_slots: u64, launch_of: &impl Fn(&Pk) -> Option<Launch>, reactive_open: &dyn Fn(&Pk) -> bool) {
        // dip20 QUIET: the window's start is taken BEFORE the QUIET work, so it never moves an attempt (without QUIET: dip19's moment)
        let t_top = self.qt.as_ref().map(|_| arbx::fast::mono_ns());
        self.st.triggers += 1;
        let (mint_s, sig_s) = (b58(&t.mint), bs58::encode(&t.sig).into_string());
        let trig = serde_json::json!({"mint": mint_s, "wallet": b58(&whale), "pct": pct, "bal": bal, "sig": sig_s, "slot": t.s, "idx": t.i, "j": t.j, "t": t.t_rx, "a": t.a(),
            "age_slots": age_slots, "sol": t.sol, "tok": t.tok, "vsol": t.vsol, "vtok": t.vtok});
        self.par.insert((mint_s.clone(), sig_s.clone(), t.j as i64), (t.s, trig.clone()));
        let launch = launch_of(&t.mint);
        let mut why: Option<&'static str> = if self.stopped.is_some() || DIP_NO_FIRE.load(Ordering::Relaxed) { Some("stopped") }
            else if age_slots == 0 && !self.cfg.create_slot { Some("create_slot") }
            else if self.armed.contains_key(&t.mint) { Some("blocked_armed") }
            else if self.pos.contains_key(&t.mint) || self.free_at.get(&t.mint).is_some_and(|f| Instant::now() < *f) { Some("blocked_position") }
            // dip19: our token account of the mint is still open (sold and kept open until no attempt can land, then closed; or an
            // UNSOLD retry holds it): every attempt would fail at its ATA create
            else if self.atas.contains_key(&t.mint) { Some("blocked_ata_open") }
            else if reactive_open(&t.mint) { Some("reactive_position") }
            else {
                match &launch {
                    None => Some("no_launch_accounts"),
                    Some(l) if !l.is_create_v2 => Some("legacy_create"),
                    Some(l) if l.is_mayhem => Some("mayhem"),
                    Some(l) if !(l.is_vanilla() || (self.allow_holder && l.is_holder_reward && !l.is_cashback && l.creator_fee_bps == 0)) => Some("non_vanilla"),
                    _ => None,
                }
            };
        // dip23 v2 (log-only): the candidate's features at this trigger (the ring holds the token's trades before it), for the records
        let v2 = self.v2.as_mut().map(|r| r.feats(&t.mint, t.t_rx, t.p_pre()).json());
        // dip20 QUIET: the four signals (skip on; every trigger, for the records and the shadow's paper), the ARM RULE (last: only a
        // trigger that would arm can be skipped "quiet"; off during the warm-up), the trigger's stop watch (stop on)
        let (mut qj, mut qkey): (Option<serde_json::Value>, Option<u64>) = (None, None);
        if let Some(q) = self.qt.as_mut() {
            let mut j = serde_json::json!({});
            if q.cfg.skip {
                let t0 = Instant::now();
                let sig = pq::arm_signals(&self.det, q.book.as_ref(), &t.mint, &whale, t.s, t.tok, t.t_rx, &q.coh, &q.fb);
                q.sig_us.add((t0.elapsed().as_secs_f64() * 1e6) as f32);
                q.signals += 1;
                // the schedule on the trigger's own arrival time (the feed's clock = now, live; a replay's time in a replay)
                let on = q.arm_on(t.t_rx);
                match sig {
                    Some(sg) => {
                        j = sg.json(q.cfg.fol);
                        j["rule_on"] = on.into();
                        if why.is_none() && sg.quiet(q.cfg.fol) {
                            if on { why = Some("quiet"); q.skips += 1; } else { q.warm_would += 1; j["would_skip"] = true.into(); }
                        }
                    }
                    None => { j["err"] = "token not followed".into(); }
                }
            }
            if let Some(stop) = q.cfg.stop { j["stop"] = format!("{}:{}", stop.n, stop.m).into(); }
            q.qid += 1;
            let id = q.qid;
            if q.cfg.stop.is_some() { q.watch.entry(t.mint).or_default().push(QWatch { id, whale, trig_slot: t.s, others: 0, win: None }); }
            let key = (mint_s.clone(), sig_s.clone(), t.j as i64);
            q.by_key.insert(key.clone(), id);
            q.trigs.insert(id, QTrig { key, arm: j.clone(), stop: None, slot: t.s, v2: v2.clone() });
            qkey = Some(id);
            qj = Some(j);
        }
        if let Some(why) = why {
            *self.st.skips.entry(why).or_default() += 1;
            let mut r = serde_json::json!({"ev": "presend_live_skip", "why": why, "trig": trig});
            if let Some(j) = &qj { r["quiet"] = j.clone(); r["quiet_skip"] = (why == "quiet").into(); }
            if let Some(v) = v2 { self.st.v2_skip[if v["skip"] == true { 0 } else { 1 }] += 1; r["v2"] = v; }
            self.rec(r);
            if why == "quiet" {
                let j = qj.as_ref().unwrap();
                self.line(format!("  PRESEND LIVE QUIET SKIP {} whale {} {:.1}% ({:.2} SOL) | since last trade {} slots, cohort holders {}, follower bots {}, whale's dumps drew {:.2} ({})",
                    b58(&t.mint), &b58(&whale)[..8], pct, t.sol as f64 / 1e9, j["since_last"], j["coh_hold"], j["fb_n"], j["wh_fol"].as_f64().unwrap_or(-1.0), j["wh_dumps"]));
            }
            return;
        }
        let launch = launch.expect("checked");
        self.launches.insert(t.mint, launch.clone());
        self.wid += 1;
        let id = self.wid;
        // the window's last slot on the block-position clock (the shadow's en0 = trigger + live_ms + W slots)
        let en_slot = ((t.a() + self.cfg.live_ms + self.cfg.window_slots as f64 * pl::SMS) / pl::SMS).floor() as u64;
        let st_ns = t_top.unwrap_or_else(arbx::fast::mono_ns) + (self.cfg.live_ms * 1e6) as u64;
        let slot_ns = arbx::feeds::entries::SLOT_US.load(Ordering::Relaxed) * 1_000;
        let sw = SWin { id, mint: t.mint, launch, st_ns, stop_ns: u64::MAX, en_slot, vsol: t.vsol, vtok: t.vtok, fr: t.fr(), pos: t.pos(), pace: pl::Pace::new(st_ns, self.cfg.k, slot_ns), n: 0, done: false };
        self.sh.wins.lock().unwrap().push(sw);
        self.armed.insert(t.mint, id);
        self.tapes.entry(t.mint).or_insert_with(|| (VecDeque::new(), 0)).0.push_back(t.clone());
        self.wins.insert(id, Win { id, mint: t.mint, whale, trig_slot: t.s, en_slot, armed_at: Instant::now(), stop_at: None, sent: 0, resolved: 0, unseen: 0,
            last_deadline: 0, disarmed: None, filled: false, checked: false, quiet: 0, qj: qj.clone(), qkey, q_others: None });
        // dip20 QUIET: the trigger's stop watch knows its window now
        if let (Some(q), Some(k)) = (self.qt.as_mut(), qkey) {
            if let Some(w) = q.watch.get_mut(&t.mint).and_then(|v| v.iter_mut().find(|w| w.id == k)) { w.win = Some(id); }
        }
        self.st.armed += 1;
        let mut r = serde_json::json!({"ev": "presend_live_arm", "w": id, "trig": trig, "en_slot": en_slot, "k": self.cfg.k, "spend": self.cfg.spend, "drop": self.cfg.drop,
            "lim0": t.p() * (1.0 - self.cfg.drop), "dry": self.cfg.dry});
        if let Some(j) = qj { r["quiet"] = j; r["quiet_skip"] = false.into(); }
        if let Some(v) = v2 { self.st.v2_arm[if v["skip"] == true { 0 } else { 1 }] += 1; r["v2"] = v; }
        self.rec(r);
        self.line(format!("  PRESEND LIVE ARM w{id} {} whale {} {:.1}% ({:.2} SOL) age {} slots | until slot {en_slot} | {} attempts/slot, limit {:.2}x", b58(&t.mint),
            &b58(&whale)[..8], pct, t.sol as f64 / 1e9, age_slots, self.cfg.k, 1.0 - self.cfg.drop));
    }

    /// one of our attempts filled (its buy TradeEvent)
    fn fill(&mut self, t: &pl::Trade, fee: u64, reactive_on_mint: bool) {
        let Some((att, done)) = self.atts.get_mut(&t.sig) else { return };
        let first = !*done;
        *done = true;
        let att = att.clone();
        if first { self.resolve(&att, "ok"); }
        self.lands.push(Land { att: att.clone(), res: "ok".into(), err: String::new(), fee, slot: t.s, idx: Some(t.i as u64), t_rx: t.t_rx, at: Instant::now() });
        self.st.fills += 1;
        self.st.fee_fills += fee;
        self.st.tips += att.tip;
        // a fill while its window was still armed, or a late one (an attempt in flight when the window ended)
        let window_open = self.wins.get(&att.w).is_some_and(|w| w.disarmed.is_none());
        if !window_open { self.st.late_fills += 1; }
        if let Some(w) = self.wins.get_mut(&att.w) { w.filled = true; }
        self.disarm(att.w, "filled");
        // every fill created our token account (its NON-idempotent create passed): the ATA rent is in its cost
        let cost = self.cfg.spend + fee + att.tip + T22_ATA_RENT;
        let trig_slot = self.wins.get(&att.w).map(|w| w.trig_slot).unwrap_or(0);
        // dip19 (fix 2): a fill on a position whose exit has started (w51's attempt B): never merged into the sell under way
        let after_exit = self.pos.get(&t.mint).is_some_and(|p| p.round > 0);
        let rec = serde_json::json!({"ev": "presend_live_fill", "w": att.w, "n": att.n, "mint": b58(&t.mint), "sig": bs58::encode(&t.sig).into_string(), "slot": t.s, "idx": t.i,
            "t": t.t_rx, "tokens": t.tok, "sol_in": t.sol, "fee": fee, "tip": att.tip, "path": att.path, "client": att.client, "p_sign": att.p_sign, "lim": att.lim, "min_out": att.min_out,
            "p_entry_post": t.p(), "p_entry_pre": t.p_pre(), "slots_after_trigger": t.s.saturating_sub(trig_slot), "slots_after_send": t.s.saturating_sub(att.slot),
            "ms_send_to_rx": (t.t_rx as i64 - att.t_send as i64) as f64 / 1e6, "window_open": window_open, "reactive_on_mint": reactive_on_mint, "after_exit": after_exit});
        self.rec(rec);
        let sig = bs58::encode(&t.sig).into_string();
        let buy = Buy { sig: sig.clone(), w: att.w, slot: t.s, idx: t.i as u64, t_rx: t.t_rx, tokens: t.tok, sol_in: t.sol, fee, tip: att.tip, cost, round: 0, via: "feed" };
        // dip19: the run's end reads this mint's account (fix 4); our account of it exists now (fix 1)
        let e = self.ends.entry(t.mint).or_default(); *e = (*e).max(t.s);
        self.ata_held(t.mint, t.s);
        // (pid, round, a read's estimated buy replaced) of a fill after the exit
        let mut late: Option<(u64, u32, bool)> = None;
        match self.pos.get_mut(&t.mint) {
            Some(p) if p.round == 0 => {
                // a second fill before the position's exit (the ATA guard should make this impossible): sold with it, in its first round
                p.tokens += t.tok; p.merged += 1; p.acct.add(cost); p.buys.push(buy);
                self.line(format!("  PRESEND LIVE FILL MERGED w{} {}: a second fill on a held token before its exit (+{} tokens; sold with it)", att.w, b58(&t.mint), t.tok));
            }
            Some(p) => {
                // dip19 (fix 2): its exit has started. NOT merged into the sell under way (that sell knows only its own tokens and its
                // confirmed-0 read can come before this landing: w51). This buy waits for the position's next sell round: its own sell
                // once the round under way finishes (a buy that landed before that round's confirmed-0 read is sold with it)
                // A recovery position's estimated buy (the balance a read found before the feed showed its fill): this fill is it
                let est = p.buys.iter().position(|b| b.sig.is_empty() && b.via == "rpc_read" && t.s <= b.slot);
                match est {
                    Some(i) => {
                        let old = p.buys[i].cost;
                        if cost > old { p.acct.add(cost - old); }
                        let b = &mut p.buys[i];
                        b.sig = sig.clone(); b.fee = fee; b.tip = att.tip; b.sol_in = t.sol; b.cost = b.cost.max(cost); b.via = "rpc_read+feed";
                    }
                    None => { p.late += 1; p.acct.add(cost); p.buys.push(buy); }
                }
                late = Some((p.pid, p.round, est.is_some()));
            }
            None => {
                // dip19: without the launch accounts (never expected: kept while the mint is ours) the accounts are derived from the
                // mint and resolved from its create tx before the sell (dip18: "SELL BY HAND")
                let (launch, derived) = match self.launches.get(&t.mint).cloned() { Some(l) => (l, false), None => (snipe_build::launch_from_target(t.mint, t.mint), true) };
                self.pid += 1;
                let acct = PsAcct::open(t.mint, cost, t.s);
                self.pos.insert(t.mint, PPos { pid: self.pid, w: att.w, mint: t.mint, launch, derived, buys: vec![buy], land: (t.s, t.i as u64, t.t_rx), tokens: t.tok, spend: self.cfg.spend,
                    att: Some(att.clone()), exit: None, sell_lands: Vec::new(), sells: Vec::new(), round: 0, selling: false, opened: Instant::now(), acct, merged: 0, late: 0, via: "feed" });
                self.sh.pause_pos.store(true, Ordering::Relaxed);
                self.tapes.entry(t.mint).or_insert_with(|| (VecDeque::new(), 0));
            }
        }
        if let Some((pid, round, matched)) = late {
            self.st.after_exit += 1;
            self.line(format!("  PRESEND LIVE FILL AFTER THE EXIT w{} {}: +{} tokens on a token whose sell (round {round}) is under way: NOT merged into it; {}", att.w, b58(&t.mint), t.tok,
                if matched { "it is the balance a read found (its recovery sell covers it)".to_string() } else { format!("its own sell (round {}) when that one finishes", round + 1) }));
            self.rec(serde_json::json!({"ev": "presend_live_late_fill", "w": att.w, "pid": pid, "round": round, "mint": b58(&t.mint), "sig": sig, "slot": t.s, "idx": t.i, "tokens": t.tok,
                "sol_in": t.sol, "fee": fee, "tip": att.tip, "matched_read": matched}));
            self.alert(arbx::alerts::Level::Warning, "dip_presend_late_fill", &b58(&t.mint), "⚠️", "PRESEND LIVE: a fill after the exit (its own sell next)", arbx::alerts::format::Body::new()
                .raw(format!("mint {}", tg::mint_link(&t.mint))).kv("tokens", t.tok.to_string()).kv("window", format!("w{}", att.w)).txt("not merged into the sell under way: sold by the next round"));
        }
        self.line(format!("  PRESEND LIVE FILL w{} {} {:.3} SOL -> {} tokens | slot {} (+{} after the send, {:.0} ms send->seen) | path {} ({}) | fills {}/{}", att.w, b58(&t.mint),
            t.sol as f64 / 1e9, t.tok, t.s, t.s.saturating_sub(att.slot), (t.t_rx as i64 - att.t_send as i64) as f64 / 1e6, att.path, att.client, self.st.fills, self.cfg.max_fills));
        if self.cfg.max_fills > 0 && self.st.fills >= self.cfg.max_fills { self.stop("max_fills"); }
    }

    /// dip19 (fix 1): our token account of `mint` exists and a position (or its UNSOLD retry) holds it; a read of it must reach `slot`
    fn ata_held(&mut self, mint: Pk, slot: u64) {
        let a = self.atas.entry(mint).or_insert(Ata { st: AtaSt::Held, not_before: None, min_slot: 0, reads: 0, closes: 0 });
        a.st = AtaSt::Held;
        a.not_before = None;
        a.min_slot = a.min_slot.max(slot);
    }

    /// sell a pre-send position (the dip engine's sell loop): its exit decision, then its first sell round
    fn exit(&mut self, mint: &Pk, why: &'static str, slot: u64, val: f64, t: u64) {
        let Some(p) = self.pos.get_mut(mint) else { return };
        if p.exit.is_some() { return; }
        p.exit = Some((why, slot, val, t));
        self.st.exits += 1;
        let r = serde_json::json!({"ev": "presend_live_exit", "w": p.w, "mint": b58(mint), "why": why, "slot": slot, "value": if val.is_nan() { serde_json::Value::Null } else { serde_json::json!(val) },
            "t": t, "slots_held": slot as i64 - p.land.0 as i64, "pid": p.pid, "round": 1, "tokens": p.tokens});
        let l = format!("  PRESEND LIVE EXIT {} {why} slot {slot} (held {} slots){}", b58(mint), slot as i64 - p.land.0 as i64, if val.is_nan() { String::new() } else { format!(" value x{val:.3}") });
        self.sell_round(mint);
        self.rec(r);
        self.line(l);
    }

    /// dip19 (fix 1/2): the position's next sell round: every buy no round covers yet, sold as one (exact tokens; confirmed reads from
    /// the latest of their landings), the token account KEPT OPEN (the attempts' guard). Every round sends at once from its decision
    /// (no RPC first: M4-1): a buy left for a follow-up round landed after the previous round's last confirmed read, so that round
    /// never saw (nor sold) its tokens
    fn sell_round(&mut self, mint: &Pk) {
        let Some(p) = self.pos.get_mut(mint) else { return };
        p.round += 1;
        let round = p.round;
        let (mut tokens, mut land) = (0u64, 0u64);
        for b in p.buys.iter_mut().filter(|b| b.round == 0) { b.round = round; tokens += b.tokens; land = land.max(b.slot); }
        p.selling = true;
        let c = Cmd::Sell { mint: *mint, pid: p.pid, round, launch: p.launch.clone(), derived: p.derived, known: (tokens > 0).then_some(tokens), guess: tokens, land_slot: land,
            read_first: false, keep_ata: true };
        self.exec(c);
    }

    /// a message back from a sell round / a token-account read / a close (`reactive_open`: the reactive bot holds this mint)
    pub fn on_msg(&mut self, m: PsMsg, reactive_open: &dyn Fn(&Pk) -> bool) {
        match m {
            PsMsg::Sold(mint, pid, round, out) => self.on_sold(mint, pid, round, out),
            PsMsg::Read(mint, why, min_slot, n, crate::Tok::Unknown) => {
                // dip19: UNREADABLE is never read as 0: the read again, 2 .. 10 s later; the run's end reads the mint too
                self.st.unreadable += 1;
                let e = self.ends.entry(mint).or_default(); *e = (*e).max(min_slot);
                if n == 1 || n % 10 == 0 {
                    self.line(format!("  PRESEND LIVE READ {} ({why:?}): token account UNREADABLE ({n} confirmed read round(s) failed): retrying, never read as 0", b58(&mint)));
                }
                let at = Instant::now() + Duration::from_secs((2 * n as u64).min(10));
                match why {
                    // still a check under way (`checks` unchanged): its answer may open a position
                    Why::Window(_) => self.retry.push((at, Cmd::Read { mint, min_slot, why, n })),
                    Why::Close => {
                        self.checks = self.checks.saturating_sub(1);
                        if let Some(a) = self.atas.get_mut(&mint) { if a.st == AtaSt::Busy { a.st = AtaSt::Idle; a.not_before = Some(at); } }
                    }
                }
            }
            PsMsg::Read(mint, why, _, _, t) => {
                self.checks = self.checks.saturating_sub(1);
                match why {
                    Why::Window(w) => { self.reading.remove(&mint); self.on_window_read(mint, w, t, reactive_open) }
                    Why::Close => self.on_close_read(mint, t, reactive_open),
                }
            }
            PsMsg::Closed(mint, sig, slot, err) => self.on_closed(mint, sig, slot, err),
            PsMsg::UnsoldDone(mint, sold) => {
                // the background retry ended: sold = an empty account (closed later, as any), else (given up at the run's end) left to the end check
                if self.pos.contains_key(&mint) { return; }
                if let Some(a) = self.atas.get_mut(&mint) { if a.st == AtaSt::Held { a.st = if sold { AtaSt::Idle } else { AtaSt::GaveUp }; } }
            }
        }
    }

    /// dip19 (fix 2): a sell round of position `pid` finished
    fn on_sold(&mut self, mint: Pk, pid: u64, round: u32, out: SellOut) {
        let Some(p) = self.pos.get_mut(&mint).filter(|p| p.pid == pid && p.round == round && p.selling) else {
            // never expected (one sell per position at a time, rounds in order): recorded, nothing changes
            self.rec(serde_json::json!({"ev": "presend_live_sold_stale", "mint": b58(&mint), "pid": pid, "round": round, "sold_at": out.sold_at, "sell_sigs": out.sigs}));
            return;
        };
        p.selling = false;
        p.sells.extend(out.sigs.iter().cloned());
        let mut next: Option<(u32, u64, u64, u64)> = None;
        match out.sold_at {
            Some(c) => {
                // this round's buys are sold, and so is a buy no round covered yet that landed at or before this confirmed-0 read (the
                // sell loop sells the confirmed balance until it reads 0)
                let mut part = 0;
                for b in p.buys.iter_mut() {
                    if b.round == 0 && b.slot <= c { b.round = round; }
                    if b.round == round { part += b.cost; }
                }
                let (n, toks) = p.buys.iter().filter(|b| b.round == 0).fold((0u32, 0u64), |a, b| (a.0 + 1, a.1 + b.tokens));
                if n > 0 {
                    // buys that landed after it (w51's B): the position's next round, their own sell; this round's part is no longer open
                    p.acct.sold_part(part, c);
                    next = Some((n, toks, c, p.w));
                } else {
                    p.acct.sold(c);
                }
            }
            None => {
                // UNSOLD: the background retry sells the confirmed balance (every buy)
                for b in p.buys.iter_mut().filter(|b| b.round == 0) { b.round = round; }
                self.st.unsold += 1;
            }
        }
        if let Some((n, toks, c, w)) = next {
            self.st.follow_ups += 1;
            self.rec(serde_json::json!({"ev": "presend_live_exit", "w": w, "mint": b58(&mint), "why": "follow-up", "slot": self.sh.slot.load(Ordering::Relaxed), "value": null,
                "t": arbx::feeds::clock::now_ns(), "pid": pid, "round": round + 1, "tokens": toks, "buys": n, "after_sold_at": c}));
            self.line(format!("  PRESEND LIVE FOLLOW-UP SELL {}: round {round} sold (a confirmed 0 at slot {c}); {n} buy(s) landed after it ({toks} tokens): round {}, its own sell",
                b58(&mint), round + 1));
            self.sell_round(&mint);
            return;
        }
        let p = self.pos.remove(&mint).expect("checked above");
        self.close_pos(p, out);
    }

    /// the position is done (every buy sold, or UNSOLD): its record (every buy, every sell), its token account's next state, its realized P&L
    fn close_pos(&mut self, p: PPos, out: SellOut) {
        let mint = p.mint;
        self.sh.pause_pos.store(!self.pos.is_empty(), Ordering::Relaxed);
        self.st.closed += 1;
        let sold = out.sold_at.is_some();
        self.free_at.insert(mint, Instant::now() + Duration::from_millis(MARGIN_MS));
        // dip19 (fix 1): the account stays open (every pre-send sell keeps it): closed once no attempt can land (tick); an UNSOLD
        // position's background retry holds it
        let last = p.buys.iter().map(|b| b.slot).max().unwrap_or(p.land.0).max(out.sold_at.unwrap_or(0));
        if sold {
            let a = self.atas.entry(mint).or_insert(Ata { st: AtaSt::Idle, not_before: None, min_slot: 0, reads: 0, closes: 0 });
            a.st = AtaSt::Idle; a.not_before = None; a.min_slot = a.min_slot.max(last);
        } else { self.ata_held(mint, last); }
        let (why, xslot, xval, _) = p.exit.unwrap_or(("?", 0, f64::NAN, 0));
        let feed_pnl = p.curve_pnl();
        let r = serde_json::json!({"ev": "presend_live_close", "w": p.w, "pid": p.pid, "mint": b58(&mint), "result": if sold { "sold" } else { "UNSOLD" }, "buy_sig": p.buy_sig(),
            "buy_sigs": p.buys.iter().map(|b| b.sig.clone()).collect::<Vec<_>>(), "buys": p.buys_json(), "land": [p.land.0, p.land.1, p.land.2],
            "exit_why": why, "exit_slot": xslot, "exit_value": if xval.is_nan() { serde_json::Value::Null } else { serde_json::json!(xval) }, "sell_land": p.sell_lands.last(),
            "sell_lands": p.sell_lands, "sell_sigs": p.sells, "rounds": p.round, "sol_in_curve": p.sol_in(), "sol_out_curve": (!p.sell_lands.is_empty()).then(|| p.sol_out()), "curve_pnl": feed_pnl,
            "tokens": p.tokens_all(), "fee": p.fees(), "tips": p.tips(), "spend": p.spend, "path": p.att.as_ref().map(|a| a.path.clone()), "client": p.att.as_ref().map(|a| a.client.clone()),
            "held_s": p.opened.elapsed().as_secs_f64(), "merged": p.merged, "late": p.late, "via": p.via});
        self.rec(r);
        self.line(format!("  PRESEND LIVE CLOSED {} {} via {why}; curve PnL {}{}", b58(&mint), if sold { "sold" } else { "UNSOLD (retrying in the background)" },
            feed_pnl.map(|v| format!("{:+.4} SOL", v as f64 / 1e9)).unwrap_or("?".into()),
            if p.buys.len() > 1 || p.round > 1 { format!(" ({} buys, {} sell round(s), every one in the P&L)", p.buys.len(), p.round) } else { String::new() }));
        if !sold { self.exec(Cmd::Unsold { mint, launch: p.launch.clone(), land_slot: last, last_qty: out.last_qty }); }
        self.realized(&p);
    }

    /// dip19 (fix 2): a settled window's confirmed read
    fn on_window_read(&mut self, mint: Pk, w: u64, t: crate::Tok, reactive_open: &dyn Fn(&Pk) -> bool) {
        self.st.held_checks += 1;
        let (tokens, ctx) = match t { crate::Tok::Amount(a, c) => (a, c), crate::Tok::Closed(c) => (0, c), crate::Tok::Unknown => return };
        if tokens == 0 {
            // an empty account of ours nobody tracks (one an earlier run's pre-send sell left open): closed as the others
            if matches!(t, crate::Tok::Amount(..)) && !self.atas.contains_key(&mint) && !self.pos.contains_key(&mint) && !reactive_open(&mint) {
                self.atas.insert(mint, Ata { st: AtaSt::Idle, not_before: None, min_slot: ctx, reads: 0, closes: 0 });
            }
            return;
        }
        // a position on it: its sell rounds sell the balance (a buy it does not know is caught by the read before the account's close)
        if self.pos.contains_key(&mint) { return; }
        // the reactive bot bought this token since (its own position, its own exit)
        if reactive_open(&mint) { self.rec(serde_json::json!({"ev": "presend_live_held", "w": w, "mint": b58(&mint), "tokens": tokens, "ctx_slot": ctx, "skipped": "reactive_position"})); return; }
        // the background UNSOLD retry of its position sells it
        if self.atas.get(&mint).is_some_and(|a| a.st == AtaSt::Held) { self.rec(serde_json::json!({"ev": "presend_live_held", "w": w, "mint": b58(&mint), "tokens": tokens, "ctx_slot": ctx, "skipped": "unsold_retry"})); return; }
        self.st.held_found += 1;
        self.orphan(mint, tokens, ctx, w, "window_read");
    }

    /// dip19 (fix 1): the read before a kept-open account's close: closed already / 0 (close it now) / a balance (an ORPHAN)
    fn on_close_read(&mut self, mint: Pk, t: crate::Tok, reactive_open: &dyn Fn(&Pk) -> bool) {
        let Some(st) = self.atas.get(&mint).map(|a| a.st) else { return };
        if st != AtaSt::Busy { return; }
        let busy_again = self.armed.contains_key(&mint) || self.pos.contains_key(&mint) || reactive_open(&mint);
        let later = |a: &mut Ata| { a.st = AtaSt::Idle; a.not_before = Some(Instant::now() + Duration::from_secs(2)); };
        match t {
            crate::Tok::Closed(c) => {
                // closed already (the reactive bot's sell closes it; a close of ours landed though its answer was missed)
                self.atas.remove(&mint);
                self.rec(serde_json::json!({"ev": "presend_live_ata", "mint": b58(&mint), "state": "closed", "ctx_slot": c}));
            }
            crate::Tok::Amount(0, c) => {
                // a window / a position / the reactive bot came since the read was sent: later
                if busy_again { if let Some(a) = self.atas.get_mut(&mint) { later(a); } return; }
                let n = match self.atas.get_mut(&mint) { Some(a) => { a.closes += 1; a.closes } None => return };
                self.rec(serde_json::json!({"ev": "presend_live_ata", "mint": b58(&mint), "state": "close_sent", "ctx_slot": c, "try": n}));
                self.exec(Cmd::Close { mint });
            }
            crate::Tok::Amount(n, c) => {
                if self.pos.contains_key(&mint) { if let Some(a) = self.atas.get_mut(&mint) { a.st = AtaSt::Held; } return; }
                if reactive_open(&mint) { if let Some(a) = self.atas.get_mut(&mint) { later(a); } return; }
                // tokens in an account whose position is done: a fill that landed after its last confirmed-0 read and the feed missed
                self.orphan(mint, n, c, 0, "close_read");
            }
            crate::Tok::Unknown => {}
        }
    }

    /// dip19 (fix 1): a close's answer: landed (the account is gone) / failed or not seen (read again later; CLOSE_TRIES, then left)
    fn on_closed(&mut self, mint: Pk, sig: String, slot: Option<u64>, err: String) {
        let held = self.pos.contains_key(&mint);
        let Some(a) = self.atas.get_mut(&mint) else { return };
        match slot {
            Some(s) => {
                // a position on it since (it would need the account closed in between): it holds the new one
                if held { a.st = AtaSt::Held; } else { self.atas.remove(&mint); }
                self.st.ata_closed += 1;
                self.rec(serde_json::json!({"ev": "presend_live_ata", "mint": b58(&mint), "state": "closed_by_us", "sig": sig, "slot": s}));
            }
            None => {
                let gave_up = a.closes >= CLOSE_TRIES;
                a.st = if held { AtaSt::Held } else if gave_up { AtaSt::GaveUp } else { AtaSt::Idle };
                a.not_before = Some(Instant::now() + Duration::from_secs(3));
                self.st.ata_close_fail += 1;
                self.rec(serde_json::json!({"ev": "presend_live_ata", "mint": b58(&mint), "state": "close_failed", "sig": sig, "err": err, "gave_up": gave_up}));
                if gave_up { self.line(format!("  PRESEND LIVE ATA {}: {CLOSE_TRIES} closes failed ({err}): left open (the run's end tries again)", b58(&mint))); }
            }
        }
    }

    /// dip19 (fix 2): tokens in our account of `mint` and no position open on it (a fill the feed did not show, or one that landed
    /// after its position's last confirmed-0 read): ORPHAN. Logged, recorded, Telegram critical; a recovery position sells it now
    fn orphan(&mut self, mint: Pk, tokens: u64, ctx: u64, w: u64, from: &'static str) {
        self.st.orphans += 1;
        self.st.unexpected += 1;
        let (launch, derived) = match self.launches.get(&mint).cloned() { Some(l) => (l, false), None => (snipe_build::launch_from_target(mint, mint), true) };
        self.line(format!("  PRESEND LIVE ORPHAN {}: our token account holds {tokens} tokens with no position open ({from}{}, slot {ctx}): selling", b58(&mint),
            if w > 0 { format!(", window w{w}") } else { String::new() }));
        self.rec(serde_json::json!({"ev": "presend_live_orphan", "w": w, "mint": b58(&mint), "tokens": tokens, "ctx_slot": ctx, "from": from, "launch": if derived { "derived" } else { "create" }}));
        self.alert(arbx::alerts::Level::Critical, "dip_presend_orphan", &b58(&mint), "🚨", "PRESEND LIVE ORPHAN: selling", arbx::alerts::format::Body::new()
            .raw(format!("mint {}", tg::mint_link(&mint))).kv("tokens", tokens.to_string()).kv("found by", from).txt("a recovery position sells it now; by hand: --sell-held").code("mint", b58(&mint)));
        let e = self.ends.entry(mint).or_default(); *e = (*e).max(ctx);
        let now_ns = arbx::feeds::clock::now_ns();
        self.pid += 1;
        // its buy's tx is not known: valued at the spend (dip18's held-check), replaced by the fill if the feed shows it later
        let acct = PsAcct::open(mint, self.cfg.spend, ctx);
        let buy = Buy { sig: String::new(), w, slot: ctx, idx: 0, t_rx: now_ns, tokens, sol_in: self.cfg.spend, fee: 0, tip: 0, cost: self.cfg.spend, round: 0, via: "rpc_read" };
        self.pos.insert(mint, PPos { pid: self.pid, w, mint, launch, derived, buys: vec![buy], land: (ctx, 0, now_ns), tokens, spend: self.cfg.spend, att: None, exit: None,
            sell_lands: Vec::new(), sells: Vec::new(), round: 0, selling: false, opened: Instant::now(), acct, merged: 0, late: 0, via: "rpc_read" });
        self.ata_held(mint, ctx);
        self.sh.pause_pos.store(true, Ordering::Relaxed);
        self.tapes.entry(mint).or_insert_with(|| (VecDeque::new(), 0));
        let s = self.sh.slot.load(Ordering::Relaxed);
        self.exit(&mint, "orphan", s, f64::NAN, now_ns);
    }

    /// dip19 (fix 3): the position's realized P&L from its own transactions: EVERY buy's payer delta (spend, fees, tips, the ATA
    /// rent) and EVERY sell's of every round, into the run's realized total (the kill switch's realized rule) and the log
    fn realized(&mut self, p: &PPos) {
        let buys: Vec<(String, u64)> = p.buys.iter().map(|b| (b.sig.clone(), b.cost)).collect();
        self.exec(Cmd::Realized { pid: p.pid, w: p.w, mint: p.mint, buys, sells: p.sells.clone() });
    }

    /// dip19: a Telegram alert (the tests keep its title instead: no raise while another test traps them)
    fn alert(&mut self, level: arbx::alerts::Level, kind: &'static str, key: &str, icon: &'static str, title: &str, body: arbx::alerts::format::Body) {
        if let Some(q) = self.q.as_mut() { q.push(Cmd::Alert { level, title: title.to_string() }); return; }
        tg::raise(level, kind, key, icon, title, body, false);
    }

    /// dip19: the chain work: queued (the tests) or spawned at once on the engine's runtime (a run); every answer comes back as a PsMsg
    fn exec(&mut self, c: Cmd) {
        if let Some(q) = self.q.as_mut() { q.push(c); return; }
        let (user, tasks) = (self.user, self.tasks.clone());
        match c {
            Cmd::Sell { mint, pid, round, launch, derived, known, guess, land_slot, read_first, keep_ata } => {
                let Some(path) = self.path.clone() else { self.line(format!("  PRESEND LIVE {}: NO SEND PATH: sell by hand (--sell-held {})", b58(&mint), b58(&mint))); return };
                let (key, rpc, mtx) = (self.key.clone(), self.rpc.clone(), self.mtx.clone());
                tasks.fetch_add(1, Ordering::SeqCst);
                tokio::spawn(async move {
                    let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
                    let launch = if derived { resolve_launch(&rpc, &mint).await.0 } else { launch };
                    let mut o = SellOpts::main();
                    o.read_first = read_first;
                    o.keep_ata = keep_ata;
                    let out = sell_until_zero(&key, user, &rpc, &path, &launch, &ata, known, guess, land_slot, o).await;
                    let _ = mtx.send(Msg::Ps(PsMsg::Sold(mint, pid, round, out)));
                    tasks.fetch_sub(1, Ordering::SeqCst);
                });
            }
            Cmd::Read { mint, min_slot, why, n } => {
                let (rpc, mtx) = (self.rpc.clone(), self.mtx.clone());
                tasks.fetch_add(1, Ordering::SeqCst);
                tokio::spawn(async move {
                    let t = tok_read_retry(&rpc, &pda::ata(&user, &mint, &pda::TOKEN_2022), "confirmed", min_slot, 3).await;
                    let _ = mtx.send(Msg::Ps(PsMsg::Read(mint, why, min_slot, n, t)));
                    tasks.fetch_sub(1, Ordering::SeqCst);
                });
            }
            Cmd::Close { mint } => {
                let Some(path) = self.path.clone() else { return };
                let (key, rpc, mtx, out, price) = (self.key.clone(), self.rpc.clone(), self.mtx.clone(), self.out.clone(), self.cfg.cu_price);
                tasks.fetch_add(1, Ordering::SeqCst);
                tokio::spawn(async move {
                    let (sig, slot, err) = close_ata(&key, user, &rpc, &path, &mint, price, &out).await;
                    let _ = mtx.send(Msg::Ps(PsMsg::Closed(mint, sig, slot, err)));
                    tasks.fetch_sub(1, Ordering::SeqCst);
                });
            }
            Cmd::Realized { pid, w, mint, buys, sells } => {
                let (rpc, out) = ((*self.rpc).clone(), self.out.clone());
                REALIZED_INFLIGHT.fetch_add(1, Ordering::SeqCst);
                tokio::spawn(async move {
                    let mut bs = Vec::with_capacity(buys.len());
                    for (sig, cost) in &buys { bs.push((if sig.is_empty() { None } else { tx_payer(&rpc, sig, 8).await }, *cost)); }
                    let mut ss = Vec::with_capacity(sells.len());
                    for (s, seen, _) in &sells { ss.push(tx_payer(&rpc, s, if *seen { 8 } else { 2 }).await); }
                    let (pnl, nb, ns) = pnl_of(&bs, &ss);
                    let src = if nb == buys.len() { "tx" } else if nb > 0 || ns > 0 { "tx+estimate" } else { "estimate" };
                    ACCT.realized.fetch_add(pnl, Ordering::SeqCst);
                    let found: Vec<(i64, u64)> = bs.iter().filter_map(|(b, _)| b.map(|x| (x.0, x.1))).collect();
                    let _ = out.send(Out::Rec(serde_json::json!({"ev": "presend_live_realized", "w": w, "pid": pid, "mint": b58(&mint), "pnl": pnl, "src": src,
                        "buy_delta": (!found.is_empty()).then(|| found.iter().map(|x| x.0).sum::<i64>()), "buy_fee": (!found.is_empty()).then(|| found.iter().map(|x| x.1).sum::<u64>()),
                        "buys": buys.iter().zip(&bs).map(|((s, c), (b, _))| serde_json::json!({"sig": s, "delta": b.map(|x| x.0), "fee": b.map(|x| x.1), "found": b.is_some(), "cost_est": c})).collect::<Vec<_>>(),
                        "buys_found": nb, "sells_found": ns, "sells": sells.len()})));
                    let _ = out.send(Out::Line(format!("  PRESEND LIVE REALIZED {} {:+.6} SOL ({src}: {nb}/{} buy tx(s), {ns}/{} sell tx(s))", b58(&mint), pnl as f64 / 1e9, buys.len(), sells.len())));
                    REALIZED_INFLIGHT.fetch_sub(1, Ordering::SeqCst);
                });
            }
            Cmd::Unsold { mint, launch, land_slot, last_qty } => {
                let Some(path) = self.path.as_ref() else { return };
                let mtx = self.mtx.clone();
                let done: UnsoldDone = Box::new(move |sold| { let _ = mtx.send(Msg::Ps(PsMsg::UnsoldDone(mint, sold))); });
                spawn_unsold_retry((*self.key).clone(), user, (*self.rpc).clone(), sp(path).clone(), launch, pda::ata(&user, &mint, &pda::TOKEN_2022), land_slot, last_qty, true, Some(done));
            }
            Cmd::Alert { .. } => {}
        }
    }

    /// the clock: windows end, positions' time exits, attempts never seen, landing records whose tape is complete. `first`: the
    /// first sighting of a signature on any feed (sig8 -> rx ns, feed), when the caller has it
    pub fn tick(&mut self, slot_now: u64, first: Option<&FxHashMap<u64, (u64, u16)>>) {
        // dip24: the rolling 24 h fee budget (a paused sender resumes when the old fees roll out)
        if self.fee_paused || !self.fee_q.is_empty() { self.fee_roll(); }
        self.drain_atts();
        let now = Instant::now();
        // windows: the last slot passed / the whale sold 30 ms ago
        let ends: Vec<(u64, &'static str)> = self.wins.values().filter(|w| w.disarmed.is_none())
            .filter_map(|w| if slot_now > w.en_slot { Some((w.id, "expired")) } else if w.stop_at.is_some_and(|t| now >= t) { Some((w.id, "whale_sold")) } else { None }).collect();
        for (id, why) in ends { self.disarm(id, why); }
        // dip20 QUIET: the preload's answer, the stop's decisions (once per slot), housekeeping. AFTER the regular ends: a window due to
        // end now (a late tick: a stalled feed) ends as it would without QUIET, the stop only acts on a window still running
        if self.qt.is_some() { self.quiet_tick(slot_now); }
        // dip23 v2: tokens idle for 120 s leave the ring (at most once per 10 s of feed time)
        if let Some(v) = self.v2.as_mut() { v.sweep(); }
        // positions: time exit at entry slot + exit_slots; the wall-clock backstop (the feed stalled)
        let due: Vec<(Pk, &'static str)> = self.pos.values().filter(|p| p.exit.is_none()).filter_map(|p| {
            time_exit_due(slot_now, p.land.0, self.cfg.exit_slots, p.opened.elapsed().as_millis() as u64, self.cfg.exit_ms).map(|w| (p.mint, w))
        }).collect();
        for (m, why) in due { self.exit(&m, why, slot_now, f64::NAN, arbx::feeds::clock::now_ns()); }
        // attempts not seen by their deadline + 3 slots (or 6 s on the wall clock: the feed may be down)
        while let Some(&(dl, sig, at)) = self.order.front() {
            if !(slot_now > dl + 3 || at.elapsed() > Duration::from_secs(6)) { break; }
            self.order.pop_front();
            let Some((att, done)) = self.atts.get_mut(&sig) else { continue };
            if *done { continue; }
            *done = true;
            let att = att.clone();
            self.resolve(&att, "unseen");
            self.lands.push(Land { att, res: "unseen".into(), err: String::new(), fee: 0, slot: 0, idx: None, t_rx: 0, at: now });
        }
        // landing records once the tape around them is complete (2 slots later, or 2 s)
        if !self.lands.is_empty() {
            let mut keep = Vec::new();
            for l in std::mem::take(&mut self.lands) {
                if l.res == "unseen" || slot_now >= l.slot + 2 || l.at.elapsed() > Duration::from_secs(2) { let r = self.land_rec(&l, first); self.rec(r); } else { keep.push(l); }
            }
            self.lands = keep;
        }
        // windows over with every attempt resolved and no attempt able to land any more (its quiet slot + 2): a CONFIRMED read of
        // our token account. dip19 (fix 2): EVERY window with an attempt sent, filled or not (dip18: only an unfilled one with an
        // attempt never seen; w51 was filled, so B was never caught)
        let mut chk = Vec::new();
        for w in self.wins.values_mut() {
            let quiet = w.last_deadline.max(w.quiet);
            if w.disarmed.is_some() && !w.checked && w.resolved >= w.sent && slot_now > quiet + 2 {
                w.checked = true;
                if w.sent > 0 && !self.cfg.dry { chk.push((w.mint, w.id, quiet)); }
            }
        }
        for (mint, w, q) in chk {
            self.checks += 1;
            let e = self.reading.entry(mint).or_default(); *e = (*e).max(q);
            self.exec(Cmd::Read { mint, min_slot: q, why: Why::Window(w), n: 1 });
        }
        // dip19: the unreadable reads again (2 .. 10 s later: never read as 0)
        if self.retry.iter().any(|(t, _)| now >= *t) {
            let (due, keep): (Vec<(Instant, Cmd)>, Vec<(Instant, Cmd)>) = std::mem::take(&mut self.retry).into_iter().partition(|(t, _)| now >= *t);
            self.retry = keep;
            for (_, c) in due { if let Cmd::Read { mint, min_slot, why, n } = c { self.exec(Cmd::Read { mint, min_slot, why, n: n + 1 }); } }
        }
        // dip19 (fix 1): our kept-open token accounts: a CONFIRMED read once no attempt of the mint can land any more, with no window
        // armed and no position on it (close_due); on_msg closes the account on a 0, sells a balance (an ORPHAN)
        if !self.atas.is_empty() && !self.cfg.dry {
            let (quiet, armed, pos) = (&self.quiet, &self.armed, &self.pos);
            let due: Vec<(Pk, u64)> = self.atas.iter().filter(|(m, a)| a.st == AtaSt::Idle && a.not_before.is_none_or(|t| now >= t)
                && close_due(slot_now, quiet.get(*m).copied().unwrap_or(0), armed.contains_key(*m), pos.contains_key(*m)))
                .map(|(m, a)| (*m, a.min_slot.max(quiet.get(m).copied().unwrap_or(0)))).collect();
            for (m, min_slot) in due {
                if let Some(a) = self.atas.get_mut(&m) { a.st = AtaSt::Busy; a.reads += 1; }
                self.st.ata_reads += 1;
                self.checks += 1;
                self.exec(Cmd::Read { mint: m, min_slot, why: Why::Close, n: 1 });
            }
        }
        // forget finished windows, old attempts, idle tapes
        let done: Vec<u64> = self.wins.values().filter(|w| w.disarmed.is_some() && w.checked && w.resolved >= w.sent).map(|w| w.id).collect();
        for id in done { self.wins.remove(&id); }
        if self.atts.len() > 4096 { self.atts.retain(|_, (a, d)| !*d || a.deadline + 300 > slot_now); }
        if slot_now >= self.last_sweep + 4 {
            self.last_sweep = slot_now;
            let (armed, pos, ld) = (&self.armed, &self.pos, &self.last_deadline);
            self.tapes.retain(|m, _| armed.contains_key(m) || pos.contains_key(m) || ld.get(m).is_some_and(|&d| d + 8 >= slot_now));
            let tapes = &self.tapes;
            // dip19: the launch accounts of every mint we may still sell (an open account, the run's end check) are kept
            let (atas, ends) = (&self.atas, &self.ends);
            self.launches.retain(|m, _| armed.contains_key(m) || pos.contains_key(m) || tapes.contains_key(m) || ld.get(m).is_some_and(|&d| d + 300 >= slot_now)
                || atas.contains_key(m) || ends.contains_key(m));
            self.last_deadline.retain(|_, d| *d + 300 >= slot_now);
            let atas = &self.atas;
            self.quiet.retain(|m, d| *d + 300 >= slot_now || atas.contains_key(m));
            self.free_at.retain(|_, t| now < *t);
            let (armed, pos) = (&self.armed, &self.pos);
            self.det.retire(slot_now, |m| armed.contains_key(m) || pos.contains_key(m));
        }
    }

    /// dip20 QUIET's part of the tick: (1) the preload's answer, merged into the live book (once; the arm rule's schedule moves up by
    /// the history it brought in) or a failure (the plain warm-up stays); (2) the stop: each trigger's watch is decided once the slot
    /// clock reaches its trigger slot + N: an armed window with fewer than M other trades is disarmed "quiet"; (3) old trigger views
    fn quiet_tick(&mut self, slot_now: u64) {
        let (mut lines, mut recs, mut decided): (Vec<String>, Vec<serde_json::Value>, Vec<(u64, bool, u32, u64)>) = (Vec::new(), Vec::new(), Vec::new());
        let tpu = self.sh.cur_slot();
        let Some(q) = self.qt.as_mut() else { return };
        if let Some(rx) = &q.pre_rx {
            let got = match rx.try_recv() { Ok(r) => Some(r), Err(crossbeam_channel::TryRecvError::Empty) => None, Err(_) => Some(Err("the preload thread ended without an answer".into())) };
            if let Some(r) = got {
                q.pre_rx = None;
                match r {
                    Ok(mut out) => {
                        let t0 = Instant::now();
                        let mut live = q.book.take().unwrap_or_else(|| pq::DumpBook::new((q.cfg.hist_h * 3.6e12) as u64));
                        let (cut, covered) = (out.cut, out.covered_ns);
                        // dip21: the journal's pending dumps go out first (the merged book journals from here on)
                        if let Some(tx) = q.jtx.as_ref() { let p = live.take_finalized(); if !p.is_empty() { let _ = tx.send(pq::JMsg::Dumps(p)); } }
                        // dip21: with the journal's dumps in the preload (ids): the base (recording + journal, by identity) takes this session's
                        // dumps; the old book (the journal's copy) is dropped off the event loop. Without: dip20's merge
                        let mut merged = match out.ids.take() {
                            Some(ids) => {
                                let (m, old) = pq::merge_base(out.book, &ids, live);
                                let _ = std::thread::Builder::new().name("ps-quiet-drop".into()).spawn(move || drop((old, ids)));
                                m
                            }
                            None => pq::merge_preload(out.book, live),
                        };
                        if q.jtx.is_some() { merged.journal_on(); }
                        q.merge_us = t0.elapsed().as_secs_f64() * 1e6;
                        // dip21: the coverage = the journal's sessions and the recording's span, joined (the continuity rule); dip20: the span
                        q.covered_ns = if q.cfg.state.is_some() || q.cfg.book.is_some() {
                            let mut spans: Vec<(u64, u64)> = q.sessions.iter().map(|x| (x.t0, x.t1)).collect();
                            if out.bt_cut > out.bt_first { spans.push((out.bt_first.max(0) as u64 * 1_000_000_000, out.bt_cut.max(0) as u64 * 1_000_000_000)); }
                            pq::coverage(&spans, q.start_ns, (q.cfg.state_max_gap_min * 6e10) as u64).covered_ns
                        } else { covered };
                        q.pre = PreSt::Done;
                        q.pre_info = serde_json::json!({"ok": true, "secs": out.secs, "dumps": merged.dumps(), "sellers": merged.sellers(), "mem_mb": merged.mem_bytes() as f64 / 1e6,
                            "chunks": out.st.chunks, "gz_bytes": out.st.bytes_gz, "lines": out.st.lines, "txs": out.st.txs, "trades": out.st.trades, "bad_lines": out.st.bad_lines,
                            "partial_tails": out.st.partial_tails, "truncated": out.st.truncated.len(), "dups": out.st.dups, "cut": cut, "bt_first": out.bt_first, "bt_cut": out.bt_cut,
                            "covered_h": covered as f64 / 3.6e12, "waited_cut_s": out.waited_cut_s, "waited_tail_s": out.waited_tail_s, "merge_us": q.merge_us,
                            "dropped_at_cut": merged.st.dropped_at_cut, "arm_rule_on_at": q.arm_at()});
                        // dip21: only with the journal / the book (dip20's record otherwise)
                        if q.cfg.state.is_some() || q.cfg.book.is_some() { q.pre_info["journal_added"] = out.journal_added.into(); q.pre_info["journal_dup"] = out.journal_dup.into(); }
                        lines.push(format!("  QUIET preload done: {} dumps, {} sellers, {:.0} s ({} chunks {:.2} GB, {} trades, {:.1} h of history to slot {}; merged in {:.0} us; ~{:.1} MB) | arm rule on {}",
                            merged.dumps(), merged.sellers(), out.secs, out.st.chunks, out.st.bytes_gz as f64 / 1e9, out.st.trades, covered as f64 / 3.6e12, cut, q.merge_us,
                            merged.mem_bytes() as f64 / 1e6, if q.arm_on(arbx::feeds::clock::now_ns()) {
                                if q.cfg.state.is_some() || q.cfg.book.is_some() { format!("now (source: {})", if q.state_info["arm_on"] == true { q.state_info["source"].as_str().unwrap_or("?").to_string() } else { "preload".into() }) } else { "now".to_string() }
                            } else { format!("at {}", ts_pkt(q.arm_at())) }));
                        q.book = Some(merged);
                    }
                    Err(e) => {
                        q.pre = PreSt::Failed;
                        q.pre_info = serde_json::json!({"ok": false, "err": e, "arm_rule_on_at": q.arm_at()});
                        lines.push(format!("  QUIET preload FAILED: {e} | the arm rule warms up {} min from the start (on at {})", q.cfg.warmup_min, ts_pkt(q.arm_at())));
                    }
                }
                let mut r = q.pre_info.clone();
                r["ev"] = "presend_live_quiet_preload".into();
                r["t"] = arbx::feeds::clock::now_ns().into();
                recs.push(r);
            }
        }
        // dip21: the dumps finalized since the last tick go to the journal writer (one channel send; the writer formats); a heartbeat
        // every FLUSH_S of data time (the session's coverage so far: a crash keeps it)
        if let (Some(tx), Some(b)) = (q.jtx.as_ref(), q.book.as_mut()) {
            if b.has_finalized() { let _ = tx.send(pq::JMsg::Dumps(b.take_finalized())); }
            if q.c0 != 0 && b.max_t() >= q.last_beat_t.saturating_add(pq::FLUSH_S * 1_000_000_000) {
                q.last_beat_t = b.max_t();
                let _ = tx.send(pq::JMsg::Beat { t: b.max_t(), s: b.max_slot() });
            }
        }
        let cur = if q.tpu_clock { tpu.max(slot_now) } else { slot_now };
        if cur > q.last_slot {
            let prev = q.last_slot;
            q.last_slot = cur;
            if let (Some(stop), false) = (q.cfg.stop, q.watch.is_empty()) {
                let trigs = &mut q.trigs;
                q.watch.retain(|_, v| {
                    v.retain(|w| match stop.due(cur, w.trig_slot, w.others) {
                        None => true,
                        Some(s) => {
                            if let Some(tg) = trigs.get_mut(&w.id) { tg.stop = Some((s, cur, w.others)); }
                            if let Some(win) = w.win { decided.push((win, s, w.others, w.trig_slot)); }
                            false
                        }
                    });
                    !v.is_empty()
                });
            }
            // the trigger views: kept ~1,500 slots (the shadow's records of a window come by then)
            if cur / 256 != prev / 256 {
                let lim = cur.saturating_sub(q.keep_slots);
                let old: Vec<u64> = q.trigs.iter().filter(|(_, t)| t.slot < lim).map(|(k, _)| *k).collect();
                for k in old { if let Some(t) = q.trigs.remove(&k) { q.by_key.remove(&t.key); } }
                q.shadow_w.retain(|_, (_, s)| *s >= lim);
            }
        }
        for (win, stop, others, trig_slot) in decided {
            let Some(w) = self.wins.get_mut(&win) else { continue };
            w.q_others = Some(others);
            if stop && w.disarmed.is_none() {
                let (n, m) = self.qt.as_ref().and_then(|q| q.cfg.stop).map(|x| (x.n, x.m)).unwrap_or((0, 0));
                let mint = w.mint;
                self.disarm(win, "quiet");
                if let Some(q) = self.qt.as_mut() { q.stops += 1; }
                lines.push(format!("  PRESEND LIVE QUIET STOP w{win} {}: {others} other trade(s) since the trigger by slot +{} (needs {m} by +{n}): no more attempts",
                    b58(&mint), self.qt.as_ref().map(|q| q.last_slot).unwrap_or(0).saturating_sub(trig_slot)));
            }
        }
        for r in recs { self.rec(r); }
        for l in lines { self.line(l); }
    }

    /// dip20 QUIET: the SHADOW's records of a tx (before they are written) get what QUIET would have decided, without changing the
    /// shadow: a presend_arm gets "quiet" (the live trigger's signals and arm-rule verdict; {"live_trigger": false} when the live
    /// detector had no such trigger), a presend_disarm gets "quiet_stop" (the stop's verdict for that trigger: stop, slot, others;
    /// stop null = not decided yet: the window ended before trigger + N). Nothing without QUIET
    pub fn annotate_shadow(&mut self, evs: &mut [arbx::presend::Ev]) {
        let Some(q) = self.qt.as_mut() else { return };
        for e in evs.iter_mut() {
            match e.rec["ev"].as_str() {
                Some("presend_arm") => {
                    let key = (e.rec["mint"].as_str().unwrap_or("").to_string(), e.rec["sig"].as_str().unwrap_or("").to_string(), e.rec["j"].as_i64().unwrap_or(-1));
                    match q.by_key.get(&key).copied() {
                        Some(id) => {
                            e.rec["quiet"] = q.trigs.get(&id).map(|t| t.arm.clone()).unwrap_or(serde_json::Value::Null);
                            // dip23: the live trigger's v2 features (only with --presend-live-quiet-v2-log)
                            if let Some(v) = q.trigs.get(&id).and_then(|t| t.v2.clone()) { e.rec["v2"] = v; }
                            if let Some(w) = e.rec["w"].as_u64() { q.shadow_w.insert(w, (id, e.rec["slot"].as_u64().unwrap_or(0))); }
                        }
                        None => { e.rec["quiet"] = serde_json::json!({"live_trigger": false}); }
                    }
                }
                Some("presend_disarm") => {
                    let Some((id, _)) = e.rec["w"].as_u64().and_then(|w| q.shadow_w.remove(&w)) else { continue };
                    e.rec["quiet_stop"] = match q.trigs.get(&id).and_then(|t| t.stop) {
                        Some((s, slot, n)) => serde_json::json!({"stop": s, "slot": slot, "others": n}),
                        None => {
                            let mint: Option<Pk> = e.rec["mint"].as_str().and_then(|m| bs58::decode(m).into_vec().ok()).and_then(|v| <[u8; 32]>::try_from(v).ok());
                            let n = mint.and_then(|m| q.watch.get(&m)).and_then(|v| v.iter().find(|w| w.id == id)).map(|w| w.others);
                            serde_json::json!({"stop": null, "others": n})
                        }
                    };
                }
                _ => {}
            }
        }
    }

    /// an attempt's landing record: where it landed vs the crossing trade / the dump / the other bots (the tape around it)
    fn land_rec(&self, l: &Land, first: Option<&FxHashMap<u64, (u64, u16)>>) -> serde_json::Value {
        let a = &l.att;
        let k8 = |s: &[u8; 64]| u64::from_be_bytes(s[..8].try_into().unwrap());
        let first_rx = |s: &[u8; 64]| first.and_then(|f| f.get(&k8(s)).map(|x| x.0));
        let poh = |s: &[u8; 64]| arbx::feeds::poh_index().get_sig(s).and_then(|(p, _)| p.ms().map(|ms| (p.slot, ms)));
        let slot_ms = arbx::feeds::entries::SLOT_US.load(Ordering::Relaxed) as f64 / 1000.0;
        let mut j = serde_json::json!({"ev": "presend_attempt_land", "w": a.w, "n": a.n, "mint": b58(&a.mint), "sig": bs58::encode(&a.sig).into_string(), "path": a.path, "client": a.client,
            "res": l.res, "err": l.err, "fee": l.fee, "send_slot": a.slot, "deadline": a.deadline, "t_send": a.t_send, "lim": a.lim, "p_sign": a.p_sign});
        if let Some((s, ms)) = pl::ack_of(a.tag) { j["ack"] = serde_json::json!(s); j["ack_ms"] = serde_json::json!(ms); }
        if let Some(f) = first_rx(&a.sig) { j["first_rx"] = serde_json::json!(f); j["ms_send_to_first_rx"] = serde_json::json!((f as i64 - a.t_send as i64) as f64 / 1e6); }
        if l.res == "unseen" { return j; }
        let idx = l.idx.unwrap_or(u32::MAX as u64) as u32;
        let a_ours = arbx::dip_model::arrival(l.slot, idx.min(10_000));
        j["slot"] = serde_json::json!(l.slot); j["idx"] = serde_json::json!(l.idx); j["t"] = serde_json::json!(l.t_rx);
        if l.idx.is_some() { j["a"] = serde_json::json!(a_ours); }
        j["slots_after_send"] = serde_json::json!(l.slot as i64 - a.slot as i64);
        j["ms_send_to_rx"] = serde_json::json!((l.t_rx as i64 - a.t_send as i64) as f64 / 1e6);
        let our_poh = poh(&a.sig);
        if let Some(p) = our_poh { j["poh"] = serde_json::json!(p); }
        let Some((tp, _)) = self.tapes.get(&a.mint) else { return j };
        let mut v: Vec<&pl::Trade> = tp.iter().collect();
        v.sort_by_key(|t| t.pos());
        v.dedup_by_key(|t| t.pos());
        let ours = (l.slot, idx);
        let before: Vec<&pl::Trade> = v.iter().copied().filter(|t| (t.s, t.i) < ours).collect();
        let after: Vec<&pl::Trade> = v.iter().copied().filter(|t| (t.s, t.i) > ours && t.s <= l.slot + 1).collect();
        // x: the first trade after the signing state, before our tx, at or below the attempt's limit (it made the attempt fillable)
        let x = before.iter().copied().find(|t| t.pos() > a.sign_pos && t.p() <= a.lim);
        // d: the dump = the biggest one-trade price drop (>= 2%) among the sells in the 2 slots before our tx
        let d = before.iter().copied().filter(|t| !t.buy && t.s + 2 >= l.slot).map(|t| (t, 1.0 - t.p() / t.p_pre())).filter(|(_, dr)| *dr >= 0.02)
            .max_by(|p, q| p.1.partial_cmp(&q.1).unwrap_or(std::cmp::Ordering::Equal));
        let ti = |t: &pl::Trade| serde_json::json!({"sig8": bs58::encode(&t.sig[..8]).into_string(), "slot": t.s, "idx": t.i, "j": t.j, "t": t.t_rx, "a": t.a(), "user": b58(&t.user)[..8].to_string(),
            "buy": t.buy, "sol": t.sol, "p_rel": t.p() / a.p_sign, "first_rx": first_rx(&t.sig), "poh": poh(&t.sig)});
        let gaps = |t: &pl::Trade| -> (f64, f64, Option<f64>, Option<f64>) {
            let rx = (l.t_rx as i64 - t.t_rx as i64) as f64 / 1e6;
            let ab = if l.idx.is_some() { a_ours - t.a() } else { f64::NAN };
            let fr = match (first_rx(&a.sig), first_rx(&t.sig)) { (Some(o), Some(x)) => Some((o as i64 - x as i64) as f64 / 1e6), _ => None };
            let ph = match (our_poh, poh(&t.sig)) { (Some((os, om)), Some((xs, xm))) => Some((os as f64 - xs as f64) * slot_ms + (om - xm)), _ => None };
            (rx, ab, fr, ph)
        };
        if let Some(x) = x {
            let (rx, ab, fr, ph) = gaps(x);
            j["x"] = ti(x); j["ms_after_x_rx"] = serde_json::json!(rx); j["ms_after_x_a"] = serde_json::json!(ab); j["ms_after_x_first"] = serde_json::json!(fr); j["ms_after_x_poh"] = serde_json::json!(ph);
        }
        if let Some((dt, dr)) = d {
            let (rx, ab, fr, ph) = gaps(dt);
            let mut dj = ti(dt); dj["drop_pct"] = serde_json::json!(dr * 100.0);
            j["d"] = dj; j["ms_after_d_rx"] = serde_json::json!(rx); j["ms_after_d_a"] = serde_json::json!(ab); j["ms_after_d_first"] = serde_json::json!(fr); j["ms_after_d_poh"] = serde_json::json!(ph);
            // the trades between the dump and our tx, and right after us: the instant bots = buys within 1 ms (feed) of the dump
            let between: Vec<&pl::Trade> = before.iter().copied().filter(|t| t.pos() > dt.pos()).collect();
            let near = |t: &pl::Trade| t.buy && (t.t_rx as i64 - dt.t_rx as i64).abs() <= 1_000_000;
            j["n_between"] = serde_json::json!(between.len());
            j["between"] = serde_json::json!(between.iter().take(8).map(|t| ti(t)).collect::<Vec<_>>());
            j["after"] = serde_json::json!(after.iter().take(4).map(|t| ti(t)).collect::<Vec<_>>());
            let ib: Vec<String> = between.iter().filter(|t| near(t)).map(|t| b58(&t.user)[..8].to_string()).collect();
            let ia: Vec<String> = after.iter().filter(|t| near(t)).map(|t| b58(&t.user)[..8].to_string()).collect();
            j["instant_before_us"] = serde_json::json!(ib);
            j["instant_after_us"] = serde_json::json!(ia);
            j["ahead_of_instant"] = if ib.is_empty() && ia.is_empty() { serde_json::Value::Null } else { serde_json::json!(ib.is_empty()) };
        }
        j
    }

    /// the shadow's presend_arm records of this tx (parity with the live triggers)
    pub fn on_shadow_arm(&mut self, rec: &serde_json::Value) {
        let k = (rec["mint"].as_str().unwrap_or("").to_string(), rec["sig"].as_str().unwrap_or("").to_string(), rec["j"].as_i64().unwrap_or(-1));
        if self.par.remove(&k).is_some() { self.st.parity_matched += 1; return; }
        self.st.parity_shadow_only += 1;
        self.rec(serde_json::json!({"ev": "presend_live_parity", "kind": "shadow_only", "mint": k.0, "sig": k.1, "j": k.2, "slot": rec["slot"], "idx": rec["idx"], "pct": rec["pct"]}));
    }

    /// the shadow has processed every slot <= `done` (it works >= 2 slots late, sorted): a live trigger of those slots it did not
    /// report is live-only
    pub fn shadow_done(&mut self, done: Option<u64>) { if let Some(d) = done { self.parity_sweep(d); } }

    /// live triggers of slots <= `upto` the shadow did not report: live-only
    fn parity_sweep(&mut self, upto: u64) {
        let old: Vec<(String, String, i64)> = self.par.iter().filter(|(_, (s, _))| *s <= upto).map(|(k, _)| k.clone()).collect();
        for k in old {
            if let Some((_, trig)) = self.par.remove(&k) {
                self.st.parity_live_only += 1;
                self.rec(serde_json::json!({"ev": "presend_live_parity", "kind": "live_only", "trig": trig}));
            }
        }
    }

    /// the 60 s status line's part
    pub fn status(&mut self) -> String {
        let qs = self.quiet_status() + &self.v2_status() + &self.fee_status();
        let (u50, u99) = self.st.us.pct();
        let (b50, b99) = self.sh.build_us.lock().unwrap().pct();
        let mut lands: Vec<_> = self.st.landed.iter().collect(); lands.sort();
        let pp = |m: &FxHashMap<String, Cnt>| { let mut v: Vec<String> = m.iter().map(|(k, c)| format!("{k} {}/{}/{}/{}/{}/{}/{}", c[0], c[1], c[2], c[3], c[4], c[5], c[6])).collect(); v.sort(); v.join(", ") };
        format!(" | PRESEND LIVE{}{}: triggers {} armed {} (now {}) skips {:?} | attempts sent {} dry {} not-sent {:?} | results {:?} | per path sent/ok/6042/deadline/ata/other/unseen {} \
                 | per client {} | fills {}/{} (late {} unexpected {}) exits {} closed {} unsold {} | failed-attempt fees {:.6}/{:.6} SOL, fill fees {:.6}, tips {:.6} | acks {:?} | parity matched {} live-only {} shadow-only {} \
                 | held checks {} found {} | dip19: fills after an exit {} follow-up sells {} orphans {} unreadable reads {} | accounts kept open {} closed {} (close reads {} failed closes {}) \
                 | loop {:.1}/{:.1} us p50/p99, build {:.0}/{:.0} us{qs}",
            if self.cfg.dry { " DRY" } else { "" }, self.stopped.map(|w| format!(" STOPPED ({w})")).unwrap_or_default(), self.st.triggers, self.st.armed, self.armed.len(), self.st.skips,
            self.sh.sent.load(Ordering::Relaxed), self.sh.dry.load(Ordering::Relaxed), self.sh.skips.lock().unwrap(), lands, pp(&self.st.per_path), pp(&self.st.per_client), self.st.fills,
            self.cfg.max_fills, self.st.late_fills, self.st.unexpected, self.st.exits, self.st.closed, self.st.unsold, self.st.fees as f64 / 1e9, self.cfg.fee_budget as f64 / 1e9, self.st.fee_fills as f64 / 1e9,
            self.st.tips as f64 / 1e9, pl::ack_counts(), self.st.parity_matched, self.st.parity_live_only, self.st.parity_shadow_only, self.st.held_checks, self.st.held_found,
            self.st.after_exit, self.st.follow_ups, self.st.orphans, self.st.unreadable, self.atas.len(), self.st.ata_closed, self.st.ata_reads, self.st.ata_close_fail,
            u50, u99, b50, b99)
    }

    /// dip20 QUIET's part of the status line ("" without it: dip19's line)
    fn quiet_status(&self) -> String {
        let Some(q) = self.qt.as_ref() else { return String::new() };
        let (s50, s99) = q.sig_us.pct();
        let now = arbx::feeds::clock::now_ns();
        let rule = if !q.cfg.skip { "off".to_string() } else if q.arm_on(now) { "on".to_string() } else if q.pre == PreSt::Running { format!("off (preload running; warm-up until {})", ts_pkt(q.arm_at())) }
            else { format!("off (warm-up until {})", ts_pkt(q.arm_at())) };
        format!(" | QUIET: skips {} (would-skip in the warm-up {}) stops {} | arm rule {rule} | signals {} ({s50:.1}/{s99:.1} us p50/p99){}{} | watches {}",
            q.skips, q.warm_would, q.stops, q.signals,
            q.book.as_ref().map(|b| format!(" | book {} dumps {} sellers ~{:.1} MB", b.dumps(), b.sellers(), b.mem_bytes() as f64 / 1e6)).unwrap_or_default(),
            match q.pre { PreSt::Off => String::new(), PreSt::Running => " | preload running".into(), PreSt::Done => format!(" | preload done ({:.0} s, {:.1} h)", q.pre_info["secs"].as_f64().unwrap_or(0.0), q.covered_ns as f64 / 3.6e12),
                PreSt::Failed => " | preload FAILED (warm-up)".into() },
            q.watch.values().map(|v| v.len()).sum::<usize>())
            // dip21: only with the book / the journal (dip20's line otherwise)
            + &q.cfg.book.as_ref().filter(|_| q.cfg.state.is_none()).map(|_| format!(" | history: book loaded {} (source {})", q.state_info["dumps"].as_u64().unwrap_or(0),
                q.state_info["source"].as_str().unwrap_or("?"))).unwrap_or_default()
            + &q.cfg.state.as_ref().map(|_| {
                let j = q.jstats.lock().unwrap_or_else(|e| e.into_inner());
                format!(" | state: loaded {} saved {} ({} flushes){}", q.state_info["dumps"].as_u64().unwrap_or(0), j.dumps, j.flushes,
                    if j.errors > 0 { format!(" WRITE ERRORS {} ({})", j.errors, j.first_err.clone().unwrap_or_default()) } else { String::new() })
            }).unwrap_or_default()
    }

    /// dip24: the rolling fee budget's part of the status line
    fn fee_status(&self) -> String {
        format!(" | fees 24 h {:.4}/{:.4} SOL{}{}", self.fee_24h as f64 / 1e9, self.cfg.fee_budget as f64 / 1e9, if self.fee_paused { " PAUSED" } else { "" },
            if self.fee_pauses > 0 { format!(" (pauses {})", self.fee_pauses) } else { String::new() })
    }

    /// dip23 v2's part of the status line ("" without --presend-live-quiet-v2-log)
    fn v2_status(&self) -> String {
        let Some(v) = self.v2.as_ref() else { return String::new() };
        format!(" | QUIET v2 (log-only): arms skip/keep {}/{} skips skip/keep {}/{} | ring {} tokens {} trades", self.st.v2_arm[0], self.st.v2_arm[1], self.st.v2_skip[0], self.st.v2_skip[1],
            v.tokens(), v.entries())
    }

    /// dip23 v2's totals for run_end (None without it)
    fn v2_json(&self) -> Option<serde_json::Value> {
        let v = self.v2.as_ref()?;
        Some(serde_json::json!({"arm_skip": self.st.v2_arm[0], "arm_keep": self.st.v2_arm[1], "skip_skip": self.st.v2_skip[0], "skip_keep": self.st.v2_skip[1],
            "ring_tokens": v.tokens(), "ring_trades": v.entries(), "rule": {"n_max": pq::V2_N_MAX, "high_tol": pq::V2_HIGH_TOL}}))
    }

    /// dip20 QUIET's totals for run_end (None without it)
    fn quiet_json(&self) -> Option<serde_json::Value> {
        let q = self.qt.as_ref()?;
        let (s50, s99) = q.sig_us.pct();
        let mut j = serde_json::json!({"cfg": q.cfg.json(), "skips": q.skips, "stops": q.stops, "warm_would": q.warm_would, "signals": q.signals, "sig_us_p50": s50, "sig_us_p99": s99,
            "arm_rule_on_at": q.arm_at(), "covered_ns": q.covered_ns, "preload": q.pre_info, "book": q.book.as_ref().map(|b| serde_json::json!({"dumps": b.dumps(), "sellers": b.sellers(),
            "mem_mb": b.mem_bytes() as f64 / 1e6, "stats": format!("{:?}", b.st)})), "cohort": q.coh.len(), "fbots": q.fb.len()});
        // dip21: only with the journal / the book (dip20's totals otherwise)
        if q.cfg.state.is_some() || q.cfg.book.is_some() { j["state"] = q.state_info.clone(); }
        Some(j)
    }

    /// the run's end: the sender stopped, unresolved attempts resolved as unseen, the records written; the totals (run_end)
    pub fn finish(&mut self, slot_now: u64, first: Option<&FxHashMap<u64, (u64, u16)>>) -> serde_json::Value {
        self.stop("run_end");
        self.sh.stop.store(true, Ordering::SeqCst);
        // dip15: never block the run's end on the sender thread (up to 2 s for it to leave its loop, else it is not joined)
        if let Some(h) = self.thread.take() {
            let t = Instant::now();
            while !self.sh.exited.load(Ordering::SeqCst) && t.elapsed() < Duration::from_secs(2) { std::thread::sleep(Duration::from_millis(10)); }
            if self.sh.exited.load(Ordering::SeqCst) { let _ = h.join(); }
            else { self.line("  PRESEND LIVE: the sender thread had not left its loop at the run end (not joined; the process exit ends it)".into()); }
        }
        self.drain_atts();
        let pend: Vec<[u8; 64]> = self.atts.iter().filter(|(_, (_, d))| !*d).map(|(k, _)| *k).collect();
        for sig in pend {
            if let Some((att, done)) = self.atts.get_mut(&sig) { *done = true; let att = att.clone(); self.resolve(&att, "unseen"); self.lands.push(Land { att, res: "unseen".into(), err: String::new(), fee: 0, slot: 0, idx: None, t_rx: 0, at: Instant::now() }); }
        }
        for l in std::mem::take(&mut self.lands) { let r = self.land_rec(&l, first); self.rec(r); }
        self.parity_sweep(u64::MAX);
        let _ = slot_now;
        let line = self.status();
        eprintln!("=== DIP PRESEND LIVE:{line}");
        let mut fin = serde_json::json!({"cfg": self.cfg.json(), "triggers": self.st.triggers, "armed": self.st.armed, "skips": self.st.skips, "disarms": self.st.disarms, "sent": self.sh.sent.load(Ordering::Relaxed),
            "dry": self.sh.dry.load(Ordering::Relaxed), "not_sent": *self.sh.skips.lock().unwrap(), "results": self.st.landed, "per_path": self.st.per_path, "per_client": self.st.per_client,
            "fills": self.st.fills, "late_fills": self.st.late_fills, "unexpected": self.st.unexpected, "exits": self.st.exits, "closed": self.st.closed, "unsold": self.st.unsold, "fees_failed": self.st.fees,
            "fees_fills": self.st.fee_fills, "tips": self.st.tips, "acks": pl::ack_counts(), "parity": {"matched": self.st.parity_matched, "live_only": self.st.parity_live_only,
            "shadow_only": self.st.parity_shadow_only}, "held_checks": self.st.held_checks, "held_found": self.st.held_found, "stopped": self.stopped,
            "dip19": {"after_exit": self.st.after_exit, "follow_ups": self.st.follow_ups, "orphans": self.st.orphans, "unreadable": self.st.unreadable, "ata_open": self.atas.len(),
                "ata_closed": self.st.ata_closed, "ata_reads": self.st.ata_reads, "ata_close_fail": self.st.ata_close_fail}});
        // dip20: only with QUIET (dip19's totals otherwise)
        // dip21: the journal's last records and stop marker; the writer drains and exits (up to 3 s: the run's end never waits longer)
        let jr = self.qt.as_mut().filter(|q| q.jtx.is_some()).map(|q| q.close_journal(Duration::from_secs(3)));
        if let Some(mut j) = self.quiet_json() {
            if let (Some((saved, dropped)), Some(q)) = (jr, self.qt.as_ref()) {
                let st = q.jstats.lock().unwrap_or_else(|e| e.into_inner()).clone();
                j["state"]["end"] = serde_json::json!({"saved_at_end": saved, "dropped_open_windows": dropped, "lines": st.lines, "dumps": st.dumps, "bytes": st.bytes,
                    "flushes": st.flushes, "syncs": st.syncs, "errors": st.errors, "first_err": st.first_err, "writer_done": st.done, "compacted": st.compacted,
                    "compact_lines": st.compact_lines, "compact_bytes_before": st.compact_bytes_before, "compact_bytes_after": st.compact_bytes_after, "compact_ms": st.compact_ms});
                self.line(format!("  QUIET state: {} dumps saved this run ({} at the end; {} windows still open dropped), {} flushes{}", st.dumps, saved, dropped, st.flushes,
                    if st.errors > 0 { format!(", WRITE ERRORS {}: {}", st.errors, st.first_err.unwrap_or_default()) } else { String::new() }));
            }
            fin["quiet"] = j;
        }
        // dip23: only with the v2 log flag
        if let Some(j) = self.v2_json() { fin["quiet_v2"] = j; }
        fin
    }

    /// dip19 (fix 4): the mints the run's end reads: every mint pre-send filled or found holding, every account of ours still open,
    /// every read left unreadable or unanswered, every window that never settled; with the slot the read must reach (its last fill /
    /// read, its quiet slot) and its launch when known
    fn end_list(&self) -> Vec<(Pk, u64, Option<Launch>)> {
        let mut m: FxHashMap<Pk, u64> = self.ends.clone();
        for (k, a) in &self.atas { let e = m.entry(*k).or_default(); *e = (*e).max(a.min_slot); }
        for (_, c) in &self.retry { if let Cmd::Read { mint, min_slot, .. } = c { let e = m.entry(*mint).or_default(); *e = (*e).max(*min_slot); } }
        // a window read whose answer never came, a window that never settled (the run stopped first): a fill the feed missed there
        for (k, s) in &self.reading { let e = m.entry(*k).or_default(); *e = (*e).max(*s); }
        for w in self.wins.values().filter(|w| w.sent > 0) { let e = m.entry(w.mint).or_default(); *e = (*e).max(w.last_deadline.max(w.quiet)); }
        let mut v: Vec<(Pk, u64, Option<Launch>)> = m.into_iter().map(|(k, s)| (k, s.max(self.quiet.get(&k).copied().unwrap_or(0)), self.launches.get(&k).cloned())).collect();
        v.sort_by_key(|x| x.0);
        v
    }

    /// dip19 (fix 4): the run's end, after finish() (the sender stopped, no position open): every mint of end_list gets one CONFIRMED
    /// read (a node at its slot), all at once: a balance is sold now (one last sell, 15 s, the account closed with it: no attempt can
    /// land any more), an empty account closed (rent back); anything still held or unreadable is HELD-AT-EXIT (Telegram critical,
    /// the --sell-held command), as the reactive bot's EXIT CHECK. First: the probe's reads / closes under way (<= 20 s), the
    /// UNSOLD retries (<= 30 s, then they give up: <= 40 s), every attempt's deadline passed (<= 10 s). -> its JSON (run_end)
    pub async fn end_drain(&mut self) -> serde_json::Value {
        let list = self.end_list();
        if self.cfg.dry || list.is_empty() { return serde_json::json!({"mints": 0}); }
        if self.q.is_some() { return serde_json::json!({"mints": list.len(), "test": true}); }
        let Some(path) = self.path.clone() else { return serde_json::json!({"mints": list.len(), "error": "no send path"}) };
        eprintln!("  PRESEND LIVE END CHECK: {} mint(s) (filled / found holding / left open / unread): a confirmed read each, a balance sold, an empty account closed ...", list.len());
        let t = Instant::now();
        while self.tasks.load(Ordering::SeqCst) > 0 && t.elapsed() < Duration::from_secs(20) { tokio::time::sleep(Duration::from_millis(200)).await; }
        if UNSOLD_BG.load(Ordering::SeqCst) > 0 {
            eprintln!("  PRESEND LIVE END CHECK: {} UNSOLD retry(ies) still running: up to 30 s more, then they give up", UNSOLD_BG.load(Ordering::SeqCst));
            let t = Instant::now();
            while UNSOLD_BG.load(Ordering::SeqCst) > 0 && t.elapsed() < Duration::from_secs(30) { tokio::time::sleep(Duration::from_millis(500)).await; }
            SELL_GIVEUP.store(true, Ordering::SeqCst);
            let t = Instant::now();
            while UNSOLD_BG.load(Ordering::SeqCst) > 0 && t.elapsed() < Duration::from_secs(40) { tokio::time::sleep(Duration::from_millis(250)).await; }
        }
        let need = list.iter().map(|x| x.1).max().unwrap_or(0) + 3;
        let t = Instant::now();
        while self.sh.cur_slot() < need && t.elapsed() < Duration::from_secs(10) { tokio::time::sleep(Duration::from_millis(200)).await; }
        let mut set = tokio::task::JoinSet::new();
        for (m, min, launch) in list {
            let (key, rpc, path, out, user, price) = (self.key.clone(), self.rpc.clone(), path.clone(), self.out.clone(), self.user, self.cfg.cu_price);
            set.spawn(async move { end_one(key, user, rpc, path, m, min, launch, price, out).await });
        }
        let (mut n, mut sold, mut closed, mut held, mut unread, mut close_failed) = (0u64, 0u64, 0u64, 0u64, 0u64, 0u64);
        while let Some(r) = set.join_next().await {
            let Ok((m, first, act, last)) = r else { continue };
            n += 1;
            match act { "sold" => sold += 1, "closed" => closed += 1, "close_failed" => close_failed += 1, _ => {} }
            self.rec(serde_json::json!({"ev": "presend_live_end_check", "mint": b58(&m), "read": first.show(), "action": act, "after": last.show()}));
            match last {
                t if t.zero_at().is_some() => {}
                crate::Tok::Unknown => {
                    unread += 1;
                    eprintln!("  HELD-AT-EXIT? (pre-send) mint={} tokens=UNREADABLE (confirmed reads failed) — check by hand, sell with --sell-held {}", b58(&m), b58(&m));
                    tg::raise(arbx::alerts::Level::Critical, "snipe_held_at_exit", &b58(&m), "🚨", "HELD-AT-EXIT? (pre-send, unreadable)", arbx::alerts::format::Body::new()
                        .raw(format!("mint {}", tg::mint_link(&m))).code("sell by hand: --sell-held", b58(&m)), false);
                }
                t => {
                    held += 1;
                    eprintln!("  HELD-AT-EXIT (pre-send) mint={} tokens={} — sell by hand: --sell-held {}", b58(&m), t.show(), b58(&m));
                    tg::raise(arbx::alerts::Level::Critical, "snipe_held_at_exit", &b58(&m), "🚨", "HELD-AT-EXIT (pre-send)", arbx::alerts::format::Body::new()
                        .raw(format!("mint {}", tg::mint_link(&m))).kv("tokens", t.show()).code("sell by hand: --sell-held", b58(&m)), false);
                }
            }
        }
        eprintln!("  PRESEND LIVE END CHECK: {n} mint(s) read at confirmed: {sold} sold now, {closed} empty account(s) closed{}, {held} held / {unread} unreadable",
            if close_failed > 0 { format!(" ({close_failed} close(s) failed: rent only)") } else { String::new() });
        serde_json::json!({"mints": n, "sold": sold, "closed": closed, "close_failed": close_failed, "held": held, "unreadable": unread})
    }
}

/// dip19 (fix 4): one mint at the run's end: its confirmed read, then (end_act) one last sell (the account closed with it) / the
/// close of an empty account / nothing; -> (mint, the read, what was done, the account after it)
#[allow(clippy::too_many_arguments)]
async fn end_one(key: Arc<SigningKey>, user: Pk, rpc: Arc<rpc::Rpc>, path: Arc<send::Path>, m: Pk, min: u64, launch: Option<Launch>, price: u64, out: crossbeam_channel::Sender<Out>)
    -> (Pk, crate::Tok, &'static str, crate::Tok) {
    let ata = pda::ata(&user, &m, &pda::TOKEN_2022);
    let first = tok_read_retry(&rpc, &ata, "confirmed", min, 6).await;
    match end_act(first) {
        EndAct::Nothing => (m, first, "none", first),
        EndAct::Unreadable => (m, first, "unreadable", first),
        EndAct::Close => {
            let (_, slot, _) = close_ata(&key, user, &rpc, &path, &m, price, &out).await;
            match slot { Some(s) => (m, first, "closed", crate::Tok::Closed(s)), None => (m, first, "close_failed", first) }
        }
        EndAct::Sell(n) => {
            let launch = match launch { Some(l) => l, None => resolve_launch(&rpc, &m).await.0 };
            eprintln!("  PRESEND LIVE EXIT-SELL mint={} tokens={n} — one last sell before the exit (the account closed with it: no attempt can land any more)", b58(&m));
            let o = SellOpts { read_first: false, wait: Duration::from_secs(2), deadline: Duration::from_secs(15), bg: false, t_decision: None, keep_ata: false };
            let s = sell_until_zero(&key, user, &rpc, &path, &launch, &ata, Some(n), n, min, o).await;
            // what these sells returned, into the run's realized total (a position's buys were booked when it closed)
            let mut back = 0i64;
            for (sig, seen, _) in &s.sigs { if let Some((d, _, _)) = tx_payer(&rpc, sig, if *seen { 6 } else { 2 }).await { back += d; } }
            if back != 0 { ACCT.realized.fetch_add(back, Ordering::SeqCst); }
            let _ = out.send(Out::Rec(serde_json::json!({"ev": "presend_live_end_sell", "mint": b58(&m), "tokens": n, "sold_at": s.sold_at, "sell_sigs": s.sigs, "back": back})));
            match s.sold_at {
                Some(c) => (m, first, "sold", crate::Tok::Closed(c)),
                None => { let after = tok_read_retry(&rpc, &ata, "confirmed", min, 3).await; (m, first, "sell_failed", after) }
            }
        }
    }
}


#[cfg(test)]
impl PsLive {
    /// tests: the probe without its threads, send path or RPC; the attempts are injected (as the sender registers them), the
    /// records read back from the writer's channel
    fn for_test(cfg: Cfg, user: Pk) -> (PsLive, crossbeam_channel::Sender<Att>, crossbeam_channel::Receiver<Out>) {
        let cfg_quiet = cfg.quiet.clone();
        let v2_log = cfg.quiet_v2_log;
        let (out, orx) = crossbeam_channel::unbounded();
        let (atx, arx) = crossbeam_channel::unbounded();
        let (mtx, _) = tokio::sync::mpsc::unbounded_channel();
        let sh = Arc::new(Shared { wins: Mutex::new(Vec::new()), stop: AtomicBool::new(false), pause_reactive: AtomicBool::new(false), pause_pos: AtomicBool::new(false), pause_fee: AtomicBool::new(false),
            slot: AtomicU64::new(0), seq: AtomicU64::new(0), sent: AtomicU64::new(0), dry: AtomicU64::new(0), exited: AtomicBool::new(true), skips: Mutex::new(FxHashMap::default()),
            build_us: Mutex::new(Ring::default()) });
        let det = pl::Detector::new(cfg.whale_pct);
        (PsLive { cfg, det, wins: FxHashMap::default(), armed: FxHashMap::default(), wid: 0, sh, arx, atts: FxHashMap::default(), order: VecDeque::new(), lands: Vec::new(),
            tapes: FxHashMap::default(), pos: FxHashMap::default(), free_at: FxHashMap::default(), last_deadline: FxHashMap::default(), launches: FxHashMap::default(), last_sweep: 0,
            checks: 0, par: FxHashMap::default(), st: Stats::default(), out, thread: None, user, key: Arc::new(SigningKey::from_bytes(&[1u8; 32])),
            rpc: Arc::new(rpc::Rpc::new("http://127.0.0.1:9".into())), path: None, mtx, allow_holder: false, stopped: None, stopped_at: None,
            // dip19: the chain work is queued: a test answers it (no RPC, no send, no Telegram)
            q: Some(Vec::new()), pid: 0, atas: FxHashMap::default(), quiet: FxHashMap::default(), ends: FxHashMap::default(), retry: Vec::new(), reading: FxHashMap::default(),
            tasks: Arc::new(AtomicU64::new(0)),
            // dip20: QUIET as its flags say, the arm rule on from the start (no warm-up: a test sets start_ns / warm_ns), the feed's slot
            // clock; the tests set its lists
            qt: cfg_quiet.on().then(|| { let mut q = Quiet::new(&cfg_quiet, &std::collections::HashSet::new(), FxHashSet::default(), 0, false); q.warm_ns = 0; q }),
            v2: v2_log.then(pq::V2Ring::new), fee_q: VecDeque::new(), fee_24h: 0, fee_paused: false, fee_pauses: 0, last_t: 0 }, atx, orx)
    }

    /// dip19 tests: the chain work queued so far (taken)
    fn take_cmds(&mut self) -> Vec<Cmd> { self.q.as_mut().map(std::mem::take).unwrap_or_default() }

    /// dip24 tests (outside this module): the probe without threads (for_test) with a wallet of our own
    pub fn test_probe(cfg: Cfg) -> (PsLive, crossbeam_channel::Sender<Att>, crossbeam_channel::Receiver<Out>) { PsLive::for_test(cfg, [0x5Au8; 32]) }
    /// dip24 tests: a failed attempt's fee at feed time `t`; the feed clock moved to `t`
    pub fn test_fee(&mut self, t: u64, fee: u64) { self.fee_add(t, fee); }
    pub fn test_clock(&mut self, t: u64) { self.last_t = self.last_t.max(t); self.fee_roll(); }
}

/// dip19 tests: the tests that open pre-send positions move the process-wide ACCT counters (one asserts they come back): one at a time
#[cfg(test)]
static ACCT_TESTS: Mutex<()> = Mutex::new(());

// dip19 (10-26 PKT): the w51 regression (FRA run 22), the kept-open account's close rules, the P&L over every buy, the run's end list,
// the golden bytes with --presend-live off. Declared here (not at the crate root as dip16-18's) to reach the probe's state machine
#[cfg(test)]
#[path = "dip19_tests.rs"]
mod dip19_tests;

// dip20 (10-27 PKT): QUIET's flags, the stop, the arm rule, the shadow's annotation, the preload thread; flags off = dip19 (they only ADD)
#[cfg(test)]
#[path = "dip20_tests.rs"]
mod dip20_tests;

// dip21 (10-27 PKT): the QUIET state journal (restarts without the recorder), its flags, the preload merged with it, the restarts harness
#[cfg(test)]
#[path = "dip21_tests.rs"]
mod dip21_tests;

// dip22 (10-28 PKT): the pre-send "sell earlier" exit (--presend-live-exit-ms; off by default = dip21)
#[cfg(test)]
#[path = "dip22_tests.rs"]
mod dip22_tests;

// dip23 (10-28 PKT): the QUIET v2 log-only annotation (--presend-live-quiet-v2-log; off by default = dip22)
#[cfg(test)]
#[path = "dip23_tests.rs"]
mod dip23_tests;

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine as _;

    fn v(a: &[&str]) -> Vec<String> { a.iter().map(|s| s.to_string()).collect() }

    #[test]
    fn presend_live_dip15_end_grace_and_empty_routes() {
        // (1) an empty route class is refused at start (it panicked the sender: a modulo by zero)
        let mut r: std::collections::HashMap<String, Vec<u8>> = std::collections::HashMap::new();
        r.insert("default".into(), vec![1]);
        assert!(refuse_empty_classes(&r).is_ok());
        r.insert("jito".into(), vec![]);
        let e = refuse_empty_classes(&r).unwrap_err().to_string();
        assert!(e.contains("'jito' has no paths"), "{e}");
        // (2) the run's end never waits forever on the pre-send bookkeeping (AMS run 17, 10-25: 9 attempts never resolved)
        let user = [0x5Bu8; 32];
        let cfg = Cfg::from_argv(&v(&BASE), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap().unwrap();
        let (mut p, atx, _orx) = PsLive::for_test(cfg, user);
        let mut sg = [0u8; 64]; sg[0] = 0xD1; sg[1] = 0x5F;
        let roles = pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) };
        atx.send(Att { w: 999, n: 1, mint: [7u8; 32], sig: sg, tag: pl::PS_TAG | 1, path: "helius-ps".into(), client: "JitoLabs".into(), slot: 100, deadline: 101,
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (100, 0, 0), t_send: 0, roles, tip: 0, wst: "written" }).unwrap();
        p.drain_atts();
        assert!(!p.idle(), "an unresolved attempt keeps the probe busy");
        assert!(!p.can_end(Duration::ZERO), "never before the stop");
        p.stop("run_end");      // the run end's own stop: no Telegram (another test traps raises while the suite runs in parallel)
        assert!(!p.can_end(Duration::from_secs(3600)), "not before the grace period");
        assert!(p.can_end(Duration::ZERO), "after the grace, no position open");
        assert!(p.not_idle_why().contains("1 attempt(s) unresolved"), "{}", p.not_idle_why());
        let end = p.finish(200, None);
        assert_eq!(end["results"]["unseen"], 1, "finish resolves the leftover attempt as unseen: {end}");
    }
    const BASE: [&str; 11] = ["snipe_engine", "--dip", "--live", "--presend-shadow", "--presend-live", "--presend-live-routes", "default=helius-ps", "--presend-live-max-fills", "20",
        "--presend-live-fee-budget-sol", "0.03"];
    fn with(extra: &[&str]) -> Vec<String> { let mut x = v(&BASE); x.extend(extra.iter().map(|s| s.to_string())); x }
    /// BASE with flag `f` set to `x` (replaced when BASE has it)
    fn set(f: &str, x: &str) -> Vec<String> {
        let mut y = v(&BASE);
        match y.iter().position(|a| a == f) { Some(i) => y[i + 1] = x.to_string(), None => { y.push(f.to_string()); y.push(x.to_string()); } }
        y
    }
    fn without(drop: &[&str]) -> Vec<String> {
        let mut x = v(&BASE);
        for d in drop { if let Some(i) = x.iter().position(|y| y == d) { x.drain(i..i + 2); } }
        x
    }

    /// every new flag passes the start-up check with its value; a misspelled one (built at run time: a literal would itself
    /// become a known flag) and a non-number are refused; the probe's own refusals: no caps, no shadow, real attempts without
    /// --live, a stray --presend-live-* flag, out-of-range values; FLAGS OFF: None
    #[test]
    fn presend_live_flags_and_refusals() {
        let all = with(&["--presend-live-dry", "--presend-live-size-sol", "0.2", "--presend-live-k", "4", "--presend-live-drop", "0.12", "--presend-live-deadline-slots", "1",
            "--presend-live-cu-limit", "90000", "--presend-live-cu-price-micro", "1000", "--presend-live-tip-lamports", "200000", "--presend-live-max-per-sec", "20",
            "--presend-live-path-max-per-sec", "10", "--presend-live-create-slot", "off", "--presend-live-one-position", "on", "--presend-live-exit-ms", "200",
            "--presend-live-quiet-v2-log"]);
        assert!(check_flags(&all).is_ok(), "{:?}", check_flags(&all));
        for f in FLAGS { assert!(all.iter().any(|a| a == f), "{f} in the test line"); }
        let wrong = ["-", "-presend-live-kk"].concat();
        assert!(check_flags(&v(&["snipe_engine", "--dip", &wrong, "4"])).is_err());
        let wrong2 = ["-", "-presend-lve"].concat();
        assert!(check_flags(&v(&["snipe_engine", "--dip", &wrong2])).is_err());
        for (f, x) in [("--presend-live-k", "x"), ("--presend-live-k", "1.5"), ("--presend-live-fee-budget-sol", "-1"), ("--presend-live-size-sol", "abc"), ("--presend-live-max-fills", "-3")] {
            assert!(check_flags(&set(f, x)).is_err(), "{f} {x}");
        }
        let p = arbx::presend::Params::default();
        let cap = 1_000_000_000;
        let c = Cfg::from_argv(&v(&BASE), &p, true, cap).unwrap().unwrap();
        assert_eq!((c.k, c.drop, c.deadline_slots, c.max_fills, c.fee_budget, c.create_slot, c.one_position, c.dry, c.spend, c.cu_limit as u64, c.cu_price, c.tip),
            (4, 0.12, 1, 20, 30_000_000, false, true, false, 550_000_000, CU_DEFAULT, 1_000, None));
        assert_eq!(c.fail_fee(), 5_000 + (CU_DEFAULT * 1_000).div_ceil(1_000_000));
        let c = Cfg::from_argv(&all, &p, true, cap).unwrap().unwrap();
        assert_eq!((c.dry, c.spend, c.tip, c.max_per_sec, c.path_max_per_sec), (true, 200_000_000, Some(200_000), 20, 10));
        // flags off: None; a stray --presend-live-* flag refused
        assert!(Cfg::from_argv(&v(&["snipe_engine", "--dip", "--presend-shadow"]), &p, true, cap).unwrap().is_none());
        assert!(Cfg::from_argv(&v(&["snipe_engine", "--dip"]), &p, false, cap).unwrap().is_none());
        for f in FLAGS {
            let e = Cfg::from_argv(&v(&["snipe_engine", "--dip", "--presend-shadow", f, "1"]), &p, true, cap).unwrap_err().to_string();
            assert!(e.contains("needs --presend-live"), "{f}: {e}");
        }
        // the shadow's own --presend-live-ms is not one of ours
        assert!(Cfg::from_argv(&v(&["snipe_engine", "--dip", "--presend-shadow", "--presend-live-ms", "50"]), &p, true, cap).unwrap().is_none());
        // dip24 (owner 10-29 "remove any hard limits"): the fill cap and the fee budget are optional: absent = unlimited fills, 1.0 SOL
        // of failed-attempt fees per rolling 24 h; the routes stay required
        let c = Cfg::from_argv(&without(&["--presend-live-max-fills"]), &p, true, cap).unwrap().unwrap();
        assert_eq!(c.max_fills, 0, "absent = unlimited");
        let c = Cfg::from_argv(&without(&["--presend-live-fee-budget-sol"]), &p, true, cap).unwrap().unwrap();
        assert_eq!(c.fee_budget, 1_000_000_000, "absent = 1.0 SOL per rolling 24 h");
        assert_eq!(Cfg::from_argv(&set("--presend-live-max-fills", "0"), &p, true, cap).unwrap().unwrap().max_fills, 0);
        assert_eq!(Cfg::from_argv(&set("--presend-live-max-fills", "20000"), &p, true, cap).unwrap().unwrap().max_fills, 20_000);
        assert_eq!(Cfg::from_argv(&set("--presend-live-fee-budget-sol", "2"), &p, true, cap).unwrap().unwrap().fee_budget, 2_000_000_000);
        assert!(Cfg::from_argv(&without(&["--presend-live-routes"]), &p, true, cap).is_err());
        // the shadow is needed; real attempts need --live (a dry run does not)
        let mut no_sh = v(&BASE); no_sh.retain(|x| x != "--presend-shadow");
        assert!(Cfg::from_argv(&no_sh, &p, true, cap).unwrap_err().to_string().contains("--presend-shadow"));
        let mut no_live = v(&BASE); no_live.retain(|x| x != "--live");
        assert!(Cfg::from_argv(&no_live, &p, false, cap).unwrap_err().to_string().contains("--live"));
        no_live.push("--presend-live-dry".into());
        assert!(Cfg::from_argv(&no_live, &p, false, cap).unwrap().unwrap().dry);
        // ranges
        for (f, x) in [("--presend-live-k", "0"), ("--presend-live-k", "21"), ("--presend-live-drop", "0"), ("--presend-live-drop", "0.6"), ("--presend-live-deadline-slots", "0"),
                       ("--presend-live-deadline-slots", "9"), ("--presend-live-cu-limit", "10000"), ("--presend-live-cu-price-micro", "2000000"),
                       ("--presend-live-fee-budget-sol", "0"), ("--presend-live-fee-budget-sol", "101"), ("--presend-live-max-per-sec", "0"), ("--presend-live-tip-lamports", "20000000"), ("--presend-live-create-slot", "yes")] {
            assert!(Cfg::from_argv(&set(f, x), &p, true, cap).is_err(), "{f} {x} should be refused");
        }
        // the size within the per-buy cap (live)
        assert!(Cfg::from_argv(&set("--presend-live-size-sol", "0.6"), &p, true, 500_000_000).unwrap_err().to_string().contains("--max-sol"));
        assert!(Cfg::from_argv(&set("--presend-live-size-sol", "0.4"), &p, true, 500_000_000).is_ok());
    }

    /// the rate caps: one window at k = 4 (~19 a second) against 10 a second per path and 20 global; two windows on two paths
    /// against the global cap; the path's configured budget refuses without taking a token
    #[test]
    fn presend_live_rate_caps() {
        let (mut g, mut pa, mut pb) = (send::TokenBucket::new(20.0, 5), send::TokenBucket::new(10.0, 2), send::TokenBucket::new(10.0, 2));
        let slot_ns = 212_000_000u64;
        let (mut w1, mut w2) = (pl::Pace::new(0, 4, slot_ns), pl::Pace::new(26_000_000, 4, slot_ns));
        let (mut sent1, mut sent2, mut ticks) = (0u64, 0u64, 0u64);
        let mut t = 0u64;
        while t < 10_000_000_000 {
            if w1.due(t) { ticks += 1; if take_rate(&mut g, &mut pa, t, || true).is_ok() { sent1 += 1; } }
            t += 500_000;
        }
        // ~189 due ticks in 10 s; the path cap lets ~10 a second through (+ its burst)
        assert!((185..=192).contains(&ticks), "{ticks}");
        assert!((95..=105).contains(&sent1), "{sent1}");
        // two windows on two paths: 2 x ~19 a second offered, 2 x 10 a second path cap, 20 a second global
        let (mut g, mut s, mut t) = (send::TokenBucket::new(20.0, 5), 0u64, 0u64);
        let (mut w1, mut a1, mut a2) = (pl::Pace::new(0, 4, slot_ns), send::TokenBucket::new(10.0, 2), send::TokenBucket::new(10.0, 2));
        while t < 10_000_000_000 {
            if w1.due(t) && take_rate(&mut g, &mut a1, t, || true).is_ok() { s += 1; }
            if w2.due(t) && take_rate(&mut g, &mut a2, t, || true).is_ok() { sent2 += 1; }
            t += 500_000;
        }
        assert!((185..=210).contains(&(s + sent2)), "{s} + {sent2}");
        // a refused configured budget takes no token (the next attempt still goes)
        let (mut g, mut p) = (send::TokenBucket::new(1.0, 1), send::TokenBucket::new(1.0, 1));
        assert_eq!(take_rate(&mut g, &mut p, 1, || false), Err("rate_path_config"));
        assert_eq!(take_rate(&mut g, &mut p, 2, || true), Ok(()));
        assert_eq!(take_rate(&mut g, &mut p, 3, || true), Err("rate_path"));
        let _ = &mut pb;
    }

    /// the attempt with the engine's real Lighthouse encoding: one packet, accepted by a Helius Sender path's own check (CU price
    /// + a tip to one of its accounts) and by a Jito path's; the deadline is the guard's slot
    #[test]
    fn presend_live_attempt_tx_checks() {
        let user = pk("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE");
        let l = snipe_build::launch_from_target(pk("7oeUduY1zhUwQ3YdSP9CGDYF8nYzfRdhgqtc6wAbpump"), pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q"));
        let key = SigningKey::from_bytes(&[7u8; 32]);
        for g in [GuardEnc { disc: 14, op: 5, acct: false }, GuardEnc { disc: 15, op: 4, acct: true }] {
            let helius: Vec<Pk> = send::known_tip_accounts(config::SendKind::Helius).iter().map(|a| pk(a)).collect();
            let (ixs, r) = pl::attempt_ixs(user, &l, 200_000_000, 1_234_567, 90_000, 1_000, guard_ix_enc(g, 461_000_123), Some((helius[3], 200_000)));
            assert_eq!(r.guard, Some(2));
            assert_eq!(u64::from_le_bytes(ixs[2].data[3..11].try_into().unwrap()), 461_000_123, "the deadline slot in the guard");
            let raw = build::sign(&build::compile_v0(user, &ixs, [9u8; 32], &[], &[]).unwrap(), &key);
            assert!(raw.len() <= 1232, "{} bytes", raw.len());
            assert!(send::verify_copy(&raw, config::SendKind::Helius, &helius, "helius-ps").is_ok());
            // the same tip below the Sender's minimum, or without a CU price: refused before sending
            let (ixs2, _) = pl::attempt_ixs(user, &l, 200_000_000, 1, 90_000, 1_000, guard_ix_enc(g, 1), Some((helius[0], 4_999)));
            assert!(send::verify_copy(&build::sign(&build::compile_v0(user, &ixs2, [9u8; 32], &[], &[]).unwrap(), &key), config::SendKind::Helius, &helius, "x").is_err());
            let jito: Vec<Pk> = send::known_tip_accounts(config::SendKind::JitoBundle).iter().map(|a| pk(a)).collect();
            let (ixs3, _) = pl::attempt_ixs(user, &l, 200_000_000, 1, 90_000, 1_000, guard_ix_enc(g, 1), Some((jito[1], 1_000)));
            assert!(send::verify_copy(&build::sign(&build::compile_v0(user, &ixs3, [9u8; 32], &[], &[]).unwrap(), &key), config::SendKind::JitoBundle, &jito, "x").is_ok());
            // the roles read back from the signed tx: the guard, the ATA create and the buy at their indices
            assert_eq!(ix_roles(&raw), (r.guard, r.buy));
        }
    }

    fn pk32(s: &str) -> Pk { bs58::decode(s).into_vec().unwrap().try_into().unwrap() }

    /// the parity tokens' executed txs in chain order: one ExecInfo per (slot, tx index) across the tokens (a tx's events in their
    /// own order; a create not in a trade tx in its own tx): (slot, idx, sig, ExecInfo), and the launches
    fn tape(n: usize) -> Option<(Vec<(u64, u64, [u8; 64], arbx::feeds::ExecInfo)>, HashMap<Pk, Launch>)> {
        let root = env!("CARGO_MANIFEST_DIR");
        let par: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(format!("{root}/testdata/presend_parity.json")).ok()?).ok()?;
        // (slot, idx) -> (sig, [(j, trade)], creates)
        let mut by: std::collections::BTreeMap<(u64, u64), ([u8; 64], Vec<(i64, arbx::dip::TradeEvent)>, Vec<arbx::dip::CreateEvent>)> = Default::default();
        let mut launches = HashMap::new();
        for tk in par["tokens"].as_array().unwrap().iter().take(n) {
            let mint = pk32(tk["mint"].as_str().unwrap());
            let users: Vec<Pk> = tk["users"].as_array().unwrap().iter().map(|u| pk32(u.as_str().unwrap())).collect();
            let la = &tk["launch"];
            let signer = pk32(la["user"].as_str().unwrap());
            let creator = la["creator"].as_str().map(pk32).unwrap_or(signer);
            let (cs, ci) = (la["slot"].as_u64().unwrap(), la["idx"].as_u64().unwrap_or(0));
            for r in tk["trades"].as_array().unwrap() {
                let (s, i, j) = (r[0].as_u64().unwrap(), r[1].as_u64().unwrap(), r[2].as_i64().unwrap());
                let sig: [u8; 64] = bs58::decode(r[3].as_str().unwrap()).into_vec().unwrap().try_into().unwrap();
                by.entry((s, i)).or_insert_with(|| (sig, Vec::new(), Vec::new())).1.push((j, arbx::dip::TradeEvent { mint, sol: r[6].as_u64().unwrap(), tok: r[7].as_u64().unwrap(),
                    buy: r[5].as_u64().unwrap() == 1, user: users[r[4].as_u64().unwrap() as usize], vsol: r[8].as_u64().unwrap(), vtok: r[9].as_u64().unwrap(),
                    fbps: r[10].as_u64().unwrap_or(0), cbps: r[11].as_u64().unwrap_or(0) }));
            }
            by.entry((cs, ci)).or_insert_with(|| ([1; 64], Vec::new(), Vec::new())).2.push(arbx::dip::CreateEvent { mint, bonding_curve: [0; 32], user: signer, creator });
            launches.insert(mint, snipe_build::launch_from_target(mint, creator));
        }
        let all = by.into_iter().map(|((s, i), (sig, mut tr, cr))| {
            tr.sort_by_key(|x| x.0);
            (s, i, sig, arbx::feeds::ExecInfo { index: i, fee: 5000, ok: true, trades: tr.into_iter().map(|x| x.1).collect(), creates: cr, mayhem: false })
        }).collect();
        Some((all, launches))
    }

    fn arrival(slot: u64, sig: [u8; 64], payer: Pk, ok: bool, exec: Option<arbx::feeds::ExecInfo>, t_rx: u64) -> arbx::feeds::Arrival {
        let tx = arbx::tx::Tx { sig, keys: vec![payer], ..Default::default() };
        arbx::feeds::Arrival { feed: 0, slot, t_rx, t_decoded: t_rx, executed: Some(ok), tx, poh: None, raw: arbx::feeds::RawTx::None, exec: exec.map(Arc::new) }
    }

    fn recs(orx: &crossbeam_channel::Receiver<Out>) -> Vec<serde_json::Value> { orx.try_iter().filter_map(|o| match o { Out::Rec(v) => Some(v), Out::Line(_) => None }).collect() }

    /// THE WIRING on the parity tapes, as the event loop calls it (on_arrival, on_exec, the shadow's presend_tx_live, tick):
    ///  * every live trigger is matched by the shadow's presend_arm (chain order: no live-only / shadow-only);
    ///  * a window arms on each non-create-slot trigger (create-slot ones are skipped, as the flag's default), blocked while one is
    ///    armed on the token;
    ///  * injected attempts resolve from the feed: a failed one through the failed-tx side channel (6042 at the buy index, its
    ///    fee), a fill from our buy TradeEvent (a position, the token blocked for the reactive bot, the attempts paused with one
    ///    position per server, its exit at entry slot + 2);
    ///  * the max-fills cap (scenario A) and the fee budget (scenario B) stop the stream; the records carry what the evaluator reads
    #[test]
    fn presend_live_wiring_on_parity_tapes() {
        let Some((txs, launches)) = tape(120) else { eprintln!("presend_parity.json missing: skipped"); return };
        let rt = tokio::runtime::Builder::new_current_thread().enable_all().build().unwrap();
        let _g = rt.enter();
        // dip19: the tests that open pre-send positions (the process-wide ACCT counters) run one at a time
        let _acct = ACCT_TESTS.lock().unwrap_or_else(|e| e.into_inner());
        let inflight0 = ACCT.inflight.load(Ordering::SeqCst);
        // the feed's failed-tx side channel watches our (test) wallet
        arbx::feeds::own_fail_watch([0x5Au8; 32]);
        for scenario in ["A: fills, max 2", "B: no fills, fee budget 20 failed attempts"] {
            let user = [0x5Au8; 32];
            let mut cfg = Cfg::from_argv(&v(&BASE), &arbx::presend::Params::default(), true, 1_000_000_000).unwrap().unwrap();
            let fills_on = scenario.starts_with('A');
            cfg.max_fills = if fills_on { 2 } else { 100 };
            cfg.fee_budget = if fills_on { 1_000_000_000 } else { 20 * cfg.fail_fee() };
            let fail_fee = cfg.fail_fee();
            let cfg_json = cfg.json();
            let (mut p, atx, orx) = PsLive::for_test(cfg, user);
            // PRESEND_LIVE_RECORDS_OUT=FILE: scenario A's records (the shadow's and the probe's) for the evaluator's plumbing test
            let out_file = std::env::var("PRESEND_LIVE_RECORDS_OUT").ok().filter(|_| fills_on);
            if let Some(f) = &out_file { let _ = std::fs::remove_file(f); }
            let log = DipLog::open(out_file.clone()).unwrap();
            log.w(serde_json::json!({"ev": "run_start", "t": 1_792_900_000_000_000_000u64, "presend_live": cfg_json, "synthetic": true}));
            let mut ps = arbx::presend::Shadow::new(arbx::presend::Params::default());
            let launch_of = |m: &Pk| launches.get(m).cloned();
            let (mut seq, mut n_fail, mut n_fill) = (0u64, 0u64, 0u64);
            let roles = pl::Roles { guard: Some(2), ata: Some(3), buy: Some(5), tip: Some(6) };
            let err6042 = [8u8, 0, 0, 0, 5, 25, 0, 0, 0, 0x9a, 0x17, 0, 0];
            let mut slot_now = 0;
            for (s, idx, sig, x) in &txs {
                slot_now = slot_now.max(*s);
                let a = arrival(*s, *sig, [3u8; 32], true, Some(x.clone()), *s * 1_000_000);
                p.on_arrival(&a, slot_now);
                p.on_exec(&a, x, slot_now, launch_of, &|_| false, None);
                let marks: Vec<[u64; 5]> = (0..=x.trades.len()).map(|_| [0u64; 5]).collect();
                presend_tx_live(&mut ps, *s, slot_now, x, sig, *s, &marks, &log, Some(&mut p));
                // the sender's part: one attempt per armed window per tx, registered; most fail (6042), every 7th fills (scenario A)
                let armed: Vec<(Pk, u64)> = p.armed.iter().map(|(m, w)| (*m, *w)).collect();
                // dip24: a paused sender (the rolling fee budget) sends nothing
                let armed = if p.sh.pause_fee.load(Ordering::Relaxed) { Vec::new() } else { armed };
                for (m, w) in armed {
                    seq += 1;
                    let mut sg = [0u8; 64]; sg[..8].copy_from_slice(&seq.to_be_bytes()); sg[8] = 0xA7; sg[9] = fills_on as u8;
                    let att = Att { w, n: 1, mint: m, sig: sg, tag: pl::PS_TAG | seq, path: "helius-ps".into(), client: "JitoLabs".into(), slot: *s, deadline: *s + 1, lim: 1.0,
                        min_out: 1, p_sign: 1.0, sign_pos: (*s, *idx as u32, 0), t_send: *s * 1_000_000, roles, tip: 200_000, wst: "written" };
                    atx.send(att).unwrap();
                    assert!(p.blocks_reactive(&m).is_some(), "an armed token is not for the reactive bot");
                    if fills_on && seq % 7 == 0 {
                        // our buy at the window's latest curve state (the size at that price)
                        let (wv, wt) = p.sh.wins.lock().unwrap().iter().find(|x| x.id == w).map(|x| (x.vsol, x.vtok)).unwrap();
                        let tok = pl::buy_out(wv, wt, 550_000_000, 0.0125);
                        let ev = arbx::dip::TradeEvent { mint: m, sol: 543_209_876, tok, buy: true, user, vsol: wv + 543_209_876, vtok: wt - tok, fbps: 95, cbps: 30 };
                        let xf = arbx::feeds::ExecInfo { index: 50, fee: 5_090, ok: true, trades: vec![ev], creates: Vec::new(), mayhem: false };
                        let af = arrival(*s, sg, user, true, Some(xf.clone()), *s * 1_000_000 + 40_000_000);
                        p.on_arrival(&af, slot_now);
                        p.on_exec(&af, &xf, slot_now, launch_of, &|_| false, None);
                        n_fill += 1;
                        assert_eq!(p.blocks_reactive(&m), Some("presend_position"));
                        let other = [0x99u8; 32];
                        assert_eq!(p.blocks_reactive(&other), Some("presend_position_open"), "one position per server");
                        assert!(p.sh.pause_pos.load(Ordering::Relaxed), "attempts paused while it is held");
                    } else {
                        arbx::feeds::own_fail_note(&sg, Some(&user[..]), *s, 60, fail_fee, &err6042);
                        let af = arrival(*s, sg, user, false, None, *s * 1_000_000 + 30_000_000);
                        p.on_arrival(&af, slot_now);
                        n_fail += 1;
                    }
                }
            }
            // the shadow's last slots (it works 2 slots late), then the run's end
            ps.complete();
            for e in ps.drain() { if e.rec["ev"] == "presend_arm" { p.on_shadow_arm(&e.rec); } }
            p.tick(slot_now + 50, None);
            let end = p.finish(slot_now + 50, None);
            let r = recs(&orx);
            if out_file.is_some() { log.w_all(r.iter().cloned()); log.w(serde_json::json!({"ev": "run_end", "t": 1_792_903_600_000_000_000u64, "presend_live": end.clone()})); }
            let ev = |k: &str| r.iter().filter(|x| x["ev"] == k).count();
            eprintln!("presend live wiring [{scenario}]: {} txs | triggers {} armed {} skips {:?} | attempts {seq} (failed {n_fail}, fills {n_fill}) | records arm {} disarm {} land {} fill {} \
                       exit {} stop {:?} parity {} | results {}", txs.len(), p.st.triggers, p.st.armed, p.st.skips, ev("presend_live_arm"), ev("presend_live_disarm"),
                ev("presend_attempt_land"), ev("presend_live_fill"), ev("presend_live_exit"), p.stopped, ev("presend_live_parity"), end["results"]);
            // parity: every live trigger matched by the shadow's presend_arm, none on either side alone
            assert!(p.st.triggers > 50);
            assert_eq!((p.st.parity_live_only, p.st.parity_shadow_only, p.st.parity_matched), (0, 0, p.st.triggers));
            // arming: create-slot triggers skipped by default; every other trigger armed or blocked (no other reason here)
            assert!(p.st.skips.get("create_slot").copied().unwrap_or(0) > 0);
            assert_eq!(p.st.armed + p.st.skips.values().sum::<u64>(), p.st.triggers);
            assert_eq!(ev("presend_live_arm") as u64, p.st.armed);
            // every attempt resolved and recorded; the failed ones as 6042 through the side channel, with their fee and block index
            assert_eq!(ev("presend_attempt_land") as u64, seq);
            let lands: Vec<&serde_json::Value> = r.iter().filter(|x| x["ev"] == "presend_attempt_land").collect();
            assert_eq!(lands.iter().filter(|x| x["res"] == "6042").count() as u64, n_fail);
            assert!(lands.iter().filter(|x| x["res"] == "6042").all(|x| x["fee"] == fail_fee && x["idx"] == 60 && x["slot"].is_u64() && x["a"].is_f64()));
            assert_eq!(p.st.fees, n_fail * fail_fee);
            if fills_on {
                assert_eq!((p.st.fills, n_fill), (2, 2));
                assert_eq!(ev("presend_live_fill"), 2);
                assert_eq!(lands.iter().filter(|x| x["res"] == "ok").count(), 2);
                assert_eq!(p.stopped, Some("max_fills"));
                    // their exits: at entry slot + 2 or on a +10% / -20% value (no send path in the test: "sell by hand")
                assert_eq!(ev("presend_live_exit"), 2);
                assert!(r.iter().filter(|x| x["ev"] == "presend_live_exit").all(|x| ["time-limit", "time-ms", "take-profit", "stop-loss"].contains(&x["why"].as_str().unwrap())
                    && (x["why"] != "time-limit" || x["slots_held"].as_i64().unwrap() >= 2)));
            } else {
                assert_eq!(p.st.fills, 0);
                // dip24: the rolling 24 h budget PAUSES the sender at 20 failed attempts (synthetic feed clock: < 24 h, so it never rolls
                // back under); the stream is not stopped
                assert_eq!(p.stopped, Some("run_end"), "only the run's end stops it");
                assert!(p.fee_paused());
                assert_eq!(n_fail, 20, "the sender paused at the fee budget");
            }
            let whys = ["expired", "whale_sold", "filled", "stopped", "token_gone"];
            assert!(r.iter().filter(|x| x["ev"] == "presend_live_disarm").all(|x| whys.contains(&x["why"].as_str().unwrap())));
            assert_eq!(ev("presend_live_disarm") as u64, p.st.armed, "every armed window disarmed once");
            drop(p);
        }
        assert_eq!(ACCT.inflight.load(Ordering::SeqCst), inflight0, "the positions' accounting released");
    }

    /// a simulation / status error as the feed's text (`rec::tx_error` style) for `classify`
    fn err_text(e: &serde_json::Value) -> String {
        if e.is_null() { return String::new(); }
        if let Some(ie) = e.get("InstructionError") {
            let i = ie[0].as_u64().unwrap_or(99);
            if let Some(c) = ie[1].get("Custom").and_then(|x| x.as_u64()) { return format!("ix{i}:custom:0x{c:x}"); }
            return format!("ix{i}:{}", ie[1].as_str().map(|x| x.to_string()).unwrap_or_else(|| ie[1].to_string()));
        }
        format!("tx:{e}")
    }

    /// READ-ONLY ON-CHAIN CHECK (zero cost: simulateTransaction with sigVerify off and replaceRecentBlockhash; nothing is signed by
    /// the wallet, nothing is sent). Run by hand:
    ///   PRESEND_SIM_MINTS=mint,mint,... cargo test --release --bin snipe_engine presend_live_sim -- --ignored --nocapture
    /// The RPC URL is read from ~/.config/sniper/ck_rpc_url (never printed). Each live pump token (create_v2, bonding curve at
    /// 25..100 SOL, not complete): an attempt AS our prod wallet (a funded system account) with the engine's own instruction list
    /// (Lighthouse deadline verified on chain as the engine does at start, the NON-idempotent T22 ATA create, the WSOL ATA, the
    /// buy, a Helius tip): (a) 6042 above the limit and a fill below it, and both sides of a +-0.05% limit; (b) the ATA already
    /// there (an idempotent create of it first, and as a real holder) fails at the create; (c) a passed deadline fails at the
    /// guard; the CU of the successful attempt
    #[test]
    #[ignore]
    fn presend_live_sim_onchain() {
        let home = std::env::var("HOME").unwrap();
        let url = std::fs::read_to_string(format!("{home}/.config/sniper/ck_rpc_url")).expect("~/.config/sniper/ck_rpc_url").trim().to_string();
        let mints: Vec<Pk> = std::env::var("PRESEND_SIM_MINTS").expect("PRESEND_SIM_MINTS=mint,mint").split(',').filter(|x| !x.is_empty()).map(|x| pk(x.trim())).collect();
        let spends: Vec<u64> = std::env::var("PRESEND_SIM_SPENDS").ok().map(|x| x.split(',').filter_map(|y| y.trim().parse().ok()).collect()).unwrap_or(vec![200_000_000]);
        let rt = tokio::runtime::Builder::new_multi_thread().worker_threads(2).enable_all().build().unwrap();
        rt.block_on(async move {
            let rpc = rpc::Rpc::new(url);
            let user = pk("2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE");
            let key = SigningKey::from_bytes(&[42u8; 32]); // not the wallet's key: sigVerify is off
            let bal = rpc.call("getBalance", serde_json::json!([b58(&user)])).await.unwrap()["value"].as_u64().unwrap();
            println!("SIM as {} (balance {:.4} SOL; its signature is not checked, nothing is sent)", b58(&user), bal as f64 / 1e9);
            let (g, _) = verify_slot_guard(&rpc, &key, user).await.expect("the Lighthouse slot deadline (as the engine verifies it at start)");
            let helius: Vec<Pk> = send::known_tip_accounts(config::SendKind::Helius).iter().map(|a| pk(a)).collect();
            let sim = |ixs: Vec<build::Ix>, payer: Pk| { let rpc = &rpc; let key = &key; async move {
                let bh = rpc.latest_blockhash().await.map(|x| x.0).unwrap_or([0u8; 32]);
                let raw = build::sign(&build::compile_v0(payer, &ixs, bh, &[], &[]).unwrap(), key);
                let b64 = base64::engine::general_purpose::STANDARD.encode(&raw);
                let v = rpc.call("simulateTransaction", serde_json::json!([b64, { "sigVerify": false, "replaceRecentBlockhash": true, "encoding": "base64", "commitment": "processed" }])).await.unwrap();
                let val = v["value"].clone();
                (err_text(&val["err"]), val["unitsConsumed"].as_u64().unwrap_or(0), raw.len(), v["context"]["slot"].as_u64().unwrap_or(0),
                 val["logs"].as_array().map(|a| a.iter().rev().take(4).filter_map(|x| x.as_str().map(|s| s.to_string())).collect::<Vec<_>>()).unwrap_or_default())
            } };
            let (mut cu_ok, mut n_tok) = (Vec::new(), 0);
            let mut fails = Vec::new();
            for mint in &mints {
                let bc = snipe_build::bonding_curve(mint);
                let ai = rpc.call("getAccountInfo", serde_json::json!([b58(&bc), { "encoding": "base64", "commitment": "processed" }])).await.unwrap();
                let Some(d) = ai["value"]["data"][0].as_str().and_then(|b| base64::engine::general_purpose::STANDARD.decode(b).ok()) else { println!("{}: no bonding curve", b58(mint)); continue };
                if d.len() < 49 { continue; }
                let (vt, vs, complete) = (u64::from_le_bytes(d[8..16].try_into().unwrap()), u64::from_le_bytes(d[16..24].try_into().unwrap()), d[48] != 0);
                let mi = rpc.call("getAccountInfo", serde_json::json!([b58(mint), { "encoding": "base64", "dataSlice": { "offset": 0, "length": 0 } }])).await.unwrap();
                let t22 = mi["value"]["owner"].as_str() == Some("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb");
                if complete || !t22 || !(25_000_000_000..100_000_000_000).contains(&vs) { println!("{}: skipped (complete {complete}, token-2022 {t22}, curve {:.1} SOL)", b58(mint), vs as f64 / 1e9); continue; }
                // the token's own fee rate: its latest trade's TradeEvent (protocol + creator bps), as the engine reads it from the feed
                let sg = rpc.call("getSignaturesForAddress", serde_json::json!([b58(mint), { "limit": 5 }])).await.unwrap();
                let (mut fr, mut fees) = (arbx::presend::fee_rate(0, 0), (0, 0));
                for x in sg.as_array().into_iter().flatten() {
                    let Ok(t) = rpc.call("getTransaction", serde_json::json!([x["signature"], { "encoding": "json", "maxSupportedTransactionVersion": 0 }])).await else { continue };
                    let logs: Vec<String> = t["meta"]["logMessages"].as_array().map(|a| a.iter().filter_map(|y| y.as_str().map(String::from)).collect()).unwrap_or_default();
                    if let Some(e) = arbx::dip::trade_events(&logs).into_iter().find(|e| e.mint == *mint) { fr = arbx::presend::fee_rate(e.fbps, e.cbps); fees = (e.fbps, e.cbps); break; }
                }
                n_tok += 1;
                let l = snipe_build::launch_from_target(*mint, *mint);
                let slot = rpc.slot().await.unwrap();
                println!("\n{} curve {:.2} SOL, price {:.4e}, fee rate {:.4} (event fee bps {:?}), slot {slot}", b58(mint), vs as f64 / 1e9, vs as f64 / vt as f64, fr, fees);
                // the curve right now (an active token moves between two simulations: each case reads it again)
                let curve = || { let rpc = &rpc; let bc = bc; async move {
                    let ai = rpc.call("getAccountInfo", serde_json::json!([b58(&bc), { "encoding": "base64", "commitment": "processed" }])).await.ok()?;
                    let d = base64::engine::general_purpose::STANDARD.decode(ai["value"]["data"][0].as_str()?).ok()?;
                    Some((u64::from_le_bytes(d[8..16].try_into().ok()?), u64::from_le_bytes(d[16..24].try_into().ok()?)))
                } };
                for &spend in &spends {
                    let att = |drop: f64, deadline: u64, (vt, vs): (u64, u64)| {
                        let (mo, _, _) = pl::limit_min_out(vs, vt, spend, fr, drop).unwrap();
                        pl::attempt_ixs(user, &l, spend, mo, CU_DEFAULT as u32, 1_000, guard_ix_enc(g, deadline), Some((helius[0], 200_000)))
                    };
                    let c0 = curve().await.unwrap_or((vt, vs));
                    let mut cases: Vec<(&str, Vec<build::Ix>, pl::Roles, Pk, Option<&str>)> = Vec::new();
                    let (x, r) = att(0.12, slot + 5, c0); cases.push(("a above the limit (limit = price x 0.88)", x, r, user, Some("6042")));
                    let (x, r) = att(-0.03, slot + 5, c0); cases.push(("a below the limit (limit = price x 1.03)", x, r, user, Some("ok")));
                    let (x, r) = att(0.0005, slot + 5, c0); cases.push(("a boundary: limit = price x 0.9995", x, r, user, None));
                    let (x, r) = att(-0.0005, slot + 5, c0); cases.push(("a boundary: limit = price x 1.0005", x, r, user, None));
                    // (b) the ATA already there: an idempotent create of it first; the attempt's own Create then fails
                    let (mut x, mut r) = att(-0.03, slot + 5, c0);
                    x.insert(2, build::create_ata_idempotent_ix(user, user, *mint, *pda::TOKEN_2022));
                    for f in [&mut r.guard, &mut r.ata, &mut r.buy, &mut r.tip] { if let Some(i) = f.as_mut() { *i += 1; } }
                    cases.push(("b ATA exists (created first in the same tx)", x, r, user, Some("ata_exists")));
                    // (c) the deadline passed
                    let (x, r) = att(-0.03, slot.saturating_sub(3), c0); cases.push(("c deadline passed (slot - 3)", x, r, user, Some("deadline")));
                    let (x, r) = att(-0.03, slot, c0); cases.push(("c deadline = the slot read just before", x, r, user, None));
                    println!("  spend {:.3} SOL:", spend as f64 / 1e9);
                    for (name, ixs, roles, payer, want) in cases {
                        // the price cases at the curve of this moment (the others do not depend on it)
                        let ixs = match name.split(':').next().unwrap_or("") {
                            _ if name.starts_with("a ") => {
                                let c = curve().await.unwrap_or(c0);
                                let drop = if name.contains("0.88") { 0.12 } else if name.contains("1.03") { -0.03 } else if name.contains("0.9995") { 0.0005 } else { -0.0005 };
                                att(drop, slot + 5, c).0
                            }
                            _ => ixs,
                        };
                        let (err, cu, bytes, ctx, logs) = sim(ixs, payer).await;
                        let res = pl::classify(&err, &roles);
                        let ok = want.is_none_or(|w| w == res);
                        if !ok { fails.push(format!("{} {name}: {res} ({err}) want {want:?}", b58(mint))); }
                        if res == "ok" { cu_ok.push(cu); }
                        println!("    {name:44} -> {res:10} {err:24} CU {cu:6} | {bytes} bytes, sim slot {ctx}{}", if ok { "" } else { "   <-- UNEXPECTED" });
                        if !ok { for lg in logs.iter().rev() { println!("        {lg}"); } }
                    }
                }
                // (b) as a REAL holder of the token (its Token-2022 ATA exists): the attempt fails at the create
                let la = rpc.call("getTokenLargestAccounts", serde_json::json!([b58(mint)])).await.unwrap();
                let curve_ata = snipe_build::assoc_bonding_curve(&bc, mint);
                for e in la["value"].as_array().into_iter().flatten().take(12) {
                    let acc = pk(e["address"].as_str().unwrap());
                    if acc == curve_ata { continue; }
                    let p = rpc.call("getAccountInfo", serde_json::json!([b58(&acc), { "encoding": "jsonParsed" }])).await.unwrap();
                    let Some(owner) = p["value"]["data"]["parsed"]["info"]["owner"].as_str().map(pk) else { continue };
                    if snipe_build::assoc_user(&owner, mint) != acc { continue; }
                    let o = rpc.call("getAccountInfo", serde_json::json!([b58(&owner), { "encoding": "base64", "dataSlice": { "offset": 0, "length": 0 } }])).await.unwrap();
                    if o["value"]["owner"].as_str() != Some("11111111111111111111111111111111") || o["value"]["lamports"].as_u64().unwrap_or(0) < 10_000_000 { continue; }
                    let (mo, _, _) = pl::limit_min_out(vs, vt, 1_000_000, fr, -0.03).unwrap();
                    let (x, r) = pl::attempt_ixs(owner, &l, 1_000_000, mo, 90_000, 1_000, guard_ix_enc(g, slot + 5), Some((helius[0], 200_000)));
                    let (err, cu, _, _, _) = sim(x, owner).await;
                    let res = pl::classify(&err, &r);
                    println!("  b as a real holder ({}..., its T22 ATA exists): {res} ({err}) CU {cu}", &b58(&owner)[..8]);
                    if res != "ata_exists" { fails.push(format!("{} holder: {res} ({err})", b58(mint))); }
                    break;
                }
            }
            cu_ok.sort();
            println!("\nSUMMARY: {n_tok} live tokens simulated; successful attempts' CU: min {:?} median {:?} max {:?} (limit used in the sim {})",
                cu_ok.first(), cu_ok.get(cu_ok.len() / 2), cu_ok.last(), CU_DEFAULT);
            for f in &fails { println!("UNEXPECTED: {f}"); }
            assert!(n_tok >= 1, "no live token to simulate on");
            assert!(fails.is_empty(), "{} unexpected result(s)", fails.len());
        });
    }
}

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
//   * dip26 LIVE RE-ARM (owner 10-29 19:35 PKT "add re-arm in the engine"; psrearm.rs has the rule): --presend-live-rearm on arms a
//       window on a followed token <= 141 slots old after a single >= 6% sell, when another wallet still holds >= 6% at the end of slot
//       dump + 2 (the observatory's rule R0, src/obs/rearm.rs); the T2 machinery does the rest (sender, caps, fee budget, one position,
//       exits, the dip19 account guard). --presend-live-rearm-size-sol X (default: the pre-send size; <= --max-sol),
//       --presend-live-rearm-gap-slots G (20), --presend-live-rearm-quiet-stop N:M (6:2), --presend-live-rearm-r5-skip on|off (off; needs
//       --presend-live-quiet-skip on). Off: nothing of it runs and every record is dip25's (golden test, dip26_tests.rs).
// =====================================================================================================================
use super::*;
use arbx::presend_live as pl;
use arbx::presend_quiet as pq;
use rustc_hash::{FxHashMap, FxHashSet};
use std::collections::VecDeque;
use std::sync::atomic::AtomicU64;
use std::sync::Mutex;

/// every --presend-live-* flag (a stray one without --presend-live is refused)
const FLAGS: [&str; 40] = ["--presend-live-dry", "--presend-live-size-sol", "--presend-live-k", "--presend-live-drop", "--presend-live-deadline-slots",
    "--presend-live-cu-limit", "--presend-live-cu-price-micro", "--presend-live-tip-lamports", "--presend-live-routes", "--presend-live-max-per-sec",
    "--presend-live-path-max-per-sec", "--presend-live-max-fills", "--presend-live-fee-budget-sol", "--presend-live-create-slot", "--presend-live-one-position",
    "--presend-live-exit-ms", "--presend-live-quiet-v2-log", "--presend-live-min-age-slots", "--presend-live-lone-whale-slots", "--presend-live-ann",
    "--presend-live-deep-drop", "--presend-live-holds-state", "--presend-live-breaker", "--presend-live-cr-unfollowed", "--presend-live-cr-loss",
    "--presend-live-creator-state", "--presend-live-f3-log", "--presend-live-tag-wallets", "--presend-live-quiet3a", "--presend-live-exact-exit",
    "--presend-live-cr-earn-log", "--presend-live-seen-log", "--presend-live-eqgrp-log", "--presend-live-q4-log", "--presend-live-fam-log",
    "--presend-live-fam-thr", "--presend-live-fam-rpc", "--presend-live-cr-log", "--presend-live-blocklist", "--presend-live-blocklist-pct"];

/// dip20 QUIET: its flags (each needs --presend-live; the history / threshold / warm-up / fbots / preload ones need
/// --presend-live-quiet-skip on)
const QFLAGS: [&str; 10] = ["--presend-live-quiet-stop", "--presend-live-quiet-skip", "--presend-live-quiet-hist-h", "--presend-live-quiet-fol",
    "--presend-live-quiet-warmup-min", "--presend-live-fbots", "--presend-live-quiet-preload", "--presend-live-quiet-state", "--presend-live-quiet-state-max-gap-min",
    "--presend-live-quiet-book"];

/// dip36 FP-NOBOT (log-only): its flags (each needs --presend-live; the paths need --presend-fpnb-log on)
const FPFLAGS: [&str; 9] = ["--presend-fpnb-log", "--presend-fpnb-bots", "--presend-fpnb-preload", "--presend-skip2-log", "--presend-skip2-seed", "--presend-fpnb-live",
    "--presend-fpnb-control", "--presend-fpnb-stale-hold", "--presend-skip2-live"];

/// dip37 WHALE / DUMPER LOSS LEDGER: its flags (each needs --presend-live; the mode and the state need --presend-live-wh-loss; pswh.rs)
const WHFLAGS: [&str; 5] = ["--presend-live-wh-loss", "--presend-live-wh-loss-mode", "--presend-live-whale-state", "--presend-live-wh-learn", "--presend-live-wh-split"];

/// dip37 HOLDER LEDGER + the ledgers' control file: its flags (each needs --presend-live; pshl.rs)
const HLFLAGS: [&str; 4] = ["--presend-live-holder-loss", "--presend-live-holder-state", "--presend-live-holder-learn", "--presend-live-ledger-control"];

/// dip37 HYBRID-2 inputs: its flags (each needs --presend-live; psh2.rs)
const H2FLAGS: [&str; 2] = ["--presend-live-m2seen-log", "--presend-live-m2seen-gate"];

/// dip37 FEE A/B: its flags (each needs --presend-live; the parameters after the first need --presend-live-fee-ab on; psfeeab.rs)
/// dip37c: the per-send blocklist's flag (needs --presend-live-blocklist)
const BLSFLAGS: [&str; 1] = ["--presend-live-blocklist-send"];

const FABFLAGS: [&str; 6] = ["--presend-live-fee-ab", "--presend-live-ab-cu-price-micro", "--presend-live-ab-cu-limit", "--presend-live-ab-tip-lamports",
    "--presend-live-ab-clients", "--presend-live-ab-split"];

/// dip26 RE-ARM: its flags (each needs --presend-live; the parameters after the first need --presend-live-rearm on)
/// dip38 ANTI-BAIT: the blocklist's launcher match (LIVE, needs --presend-live-blocklist) and the log-only insider / family / shape flags
/// (each needs --presend-live; the resolver's / ledgers' parameters need their log on; pslog38.rs, psfund.rs)
const D38FLAGS: [&str; 8] = ["--presend-live-blocklist-launcher", "--presend-live-insider-log", "--presend-live-fund-rpc", "--presend-live-fund-rps", "--presend-live-fund-state",
    "--presend-live-family-state", "--presend-live-shape-log", "--presend-live-shape-state"];

/// dip38 PSM12-S1: its flags (each needs --presend-live; the live gate and the parts need --presend-live-s1-log on; pss1.rs)
const S1FLAGS: [&str; 3] = ["--presend-live-s1-log", "--presend-live-s1", "--presend-live-s1-parts"];

/// dip39 BOT DEPTH: its flags (each needs --presend-live; the list and the mode need --presend-live-botdepth; psbd.rs)
const BDFLAGS: [&str; 6] = ["--presend-live-botdepth", "--presend-live-botdepth-list", "--presend-live-botdepth-mode", "--presend-live-botdepth-source",
    "--presend-live-botdepth-organic", "--presend-live-botdepth-state"];

/// dip41 DUMPER LEDGER + WIDE-DUMPER tier: its flags (each needs --presend-live; the others need --presend-live-dumper-ledger on; psdl.rs)
const DLFLAGS: [&str; 8] = ["--presend-live-dumper-ledger", "--presend-live-dumper-state", "--presend-live-wide-dumper", "--presend-live-wide-dumper-mode",
    "--presend-live-wide-size-sol", "--presend-live-qf2", "--presend-live-qf2-filters", "--presend-live-qf2-mode"];

/// dip42 FAM2 (the 2NUM family's presence on our windows; LOG ONLY): its flags (each needs --presend-live; the wallets / slots need
/// --presend-live-fam2 on; psfam2.rs)
const F2FLAGS: [&str; 3] = ["--presend-live-fam2", "--presend-live-fam2-wallets", "--presend-live-fam2-slots"];

/// dip42 Q1 (the quiet-token fresh-wallet big-buy shadow; LOG ONLY): its flags (each needs --presend-live: the probe's feed hook; the
/// others need --q1-log on; psq1.rs)
const Q1FLAGS: [&str; 11] = ["--q1-log", "--q1-bots", "--q1-fresh-state", "--q1-min-sol", "--q1-age-slots", "--q1-bot-slots", "--q1-dip-slots", "--q1-fresh-max",
    "--q1-gap-slots", "--q1-size-sol", "--q1-fresh-hours"];

/// dip43 Builder A (ps43.rs, ps43_stall.rs): its flags (each needs --presend-live; all off / log by default)
const A43FLAGS: [&str; 15] = ["--presend-live-stall-mode", "--presend-live-stall", "--presend-live-deadman", "--presend-live-deadman-ms", "--presend-live-tbal",
    "--presend-live-cascade", "--presend-live-fanout", "--presend-live-fanout-mode", "--presend-live-mint-ledger", "--presend-live-mint-ledger-mode",
    "--presend-live-shadow-exit", "--presend-live-acct", "--presend-live-botdepth-allow-log", "--presend-live-shadows43", "--presend-live-fpnb-strict"];
/// dip43 BUILDER B (send path + exits; ps43_b.rs): its flags (each needs --presend-live; every one OFF by default = dip42)
const B43FLAGS: [&str; 12] = ["--presend-live-reroute", "--presend-live-single-token", "--presend-live-skip-clients", "--presend-live-fee-tier", "--presend-live-start-ms",
    "--presend-live-exit-lots", "--presend-live-exit-lots-ab", "--presend-live-exit-lots-kinds", "--presend-live-lot2-cu-price-micro", "--presend-live-timer-sell-cu-price-micro",
    "--presend-live-timer-sell-ab", "--presend-live-exit-ab"];

const RFLAGS: [&str; 5] = ["--presend-live-rearm", "--presend-live-rearm-size-sol", "--presend-live-rearm-gap-slots", "--presend-live-rearm-quiet-stop",
    "--presend-live-rearm-r5-skip"];

// dip26 LIVE RE-ARM: the rule's state machine (off without --presend-live-rearm on)
#[path = "psrearm.rs"]
mod psrearm;

// dip34 LOG-ONLY annotations (seen whale, equal-size groups, QUIET4 fields; each off unless its flag is given)
#[path = "pslog34.rs"]
mod pslog34;
use pslog34::L34;

// dip35 LOG-ONLY "fam" (the bundle family's holding from a background holders read at every arm; off unless its flag is given)
#[path = "pslog35.rs"]
mod pslog35;
use pslog35::{FamReq, FamRes, L35};

// dip36 LIVE wallet blocklist (arm-time skips; off unless --presend-live-blocklist PATH)
#[path = "psblock.rs"]
mod psblock;

// dip36 LOG-ONLY FP-NOBOT (the frozen no-follower-bot filter scored at every arm / send slot / fill on its own thread; off unless its flag)
#[path = "pslog36.rs"]
mod pslog36;

// dip37 FEE A/B (a per-window priority-fee A/B on the attempts; off unless --presend-live-fee-ab on)
#[path = "psfeeab.rs"]
pub mod psfeeab;

// dip37 LIVE whale / dumper loss ledger (arm-time skips; off unless --presend-live-wh-loss N:SOL)
#[path = "pswh.rs"]
pub mod pswh;

// dip37 HYBRID-2 inputs: nd / m2max per arm (log only) and the m2_unseen gate (off unless its flags)
#[path = "psh2.rs"]
pub mod psh2;

// dip37 LIVE holder ledger and the ledgers' hot control file (off unless their flags)
#[path = "pshl.rs"]
pub mod pshl;

// dip38 the funding resolver (a background task; off unless --presend-live-insider-log on)
#[path = "psfund.rs"]
pub mod psfund;

// dip38 ANTI-BAIT LOG: launcher record, INSIDER / FAMILY / FAMILY LEDGER, SHAPE LEDGER (log-only; off unless their flags)
#[path = "pslog38.rs"]
pub mod pslog38;

// dip38 PSM12-S1 arm filter: LOG ONLY (--presend-live-s1-log on); its live gate built, off unless --presend-live-s1 / the control file's "s1"
#[path = "pss1.rs"]
pub mod pss1;

// dip39 BOT DEPTH pre-send gate (withholds an attempt with < MIN listed bot wallets trading the mint in the last SLOTS slots; off unless
// --presend-live-botdepth MIN:SLOTS; log mode by default)
#[path = "psbd.rs"]
pub mod psbd;

// dip41 WHALE FAST-DUMP LEDGER + WIDE-DUMPER arming tier (3..6% whales that dump fast; off unless --presend-live-dumper-ledger on; the tier
// in log mode by default: nothing sent)
#[path = "psdl.rs"]
pub mod psdl;

// dip42 FAM2: the 2NUM family's presence on the pre-send windows' records (LOG ONLY; off unless --presend-live-fam2 on)
#[path = "psfam2.rs"]
pub mod psfam2;

// dip42 Q1: the quiet-token fresh-wallet big-buy reactive trigger as a shadow log (LOG ONLY, its own thread; off unless --q1-log on)
#[path = "psq1.rs"]
pub mod psq1;

// dip43 Builder A: the feed-stall watchdog / dead-man (ps43_stall.rs) and the safety / control / shadow items (ps43.rs); off / log by default
#[path = "ps43_stall.rs"]
pub mod ps43_stall;
#[path = "ps43.rs"]
pub mod ps43;
// dip43 A12: the react-watch recorder (LOG ONLY; off unless --react-watch FILE)
#[path = "ps43_react.rs"]
pub mod ps43_react;
// dip43 BUILDER B: cap / re-route / single token / skip clients (B1), fee tier (B2), two-lot exit (B3), cheap timer sells (B4), window
// start (B5); every item OFF by default (= dip42)
#[path = "ps43_b.rs"]
pub mod ps43_b;

/// dip26 RE-ARM's parameters (off by default)
#[derive(Clone, Debug, PartialEq)]
pub struct RearmCfg {
    /// --presend-live-rearm on
    pub on: bool,
    /// --presend-live-rearm-size-sol (lamports; default: the pre-send size)
    pub spend: u64,
    /// --presend-live-rearm-gap-slots G (20): the window's last slot = dump + 3 + G
    pub gap: u64,
    /// --presend-live-rearm-quiet-stop N:M (6:2): at the first slot >= the arm slot + N, fewer than M trades by anyone but us
    pub stop: pq::QStop,
    /// --presend-live-rearm-r5-skip on: no window when all four QUIET arm signals hold for the largest remaining holder
    pub r5_skip: bool,
}

impl RearmCfg {
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"on": self.on, "spend": self.spend, "gap": self.gap, "quiet_stop": format!("{}:{}", self.stop.n, self.stop.m), "r5_skip": self.r5_skip,
            "big_pct": psrearm::RE_BIG as f64 / pl::SUPPLY * 100.0, "max_age_slots": psrearm::RE_MAX_AGE, "wait_slots": psrearm::RE_WAIT, "untradeable_sol": psrearm::RE_UNTRADE / 1_000_000_000,
            "stop_ms": WHALE_SELL_MS})
    }
}

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
    /// --presend-live-min-age-slots N (0 = off, the default): skip a trigger whose token is younger than N slots (trigger slot −
    /// create slot < N; "young_age"). 2 = also skip age 1 (10-29 loss study: age-1 whales lose; 24-run check ops/strategies/presend/losses/verify)
    pub min_age_slots: u64,
    /// dip27 --presend-live-lone-whale-slots N (0 = off, the default; 1..=64): skip a trigger when the whale is the token's only buyer in
    /// its last N slots (the trigger's slot and the N - 1 before it, the trigger's own buy counted, ours never): "lone_whale". Decided
    /// LAST (after QUIET): only a trigger that would arm is skipped. 50 = the 10-30 loss study's rule (ops/strategies/presend/prevent:
    /// STATE nbuyers50 <= 1, verified; ~+0.6 SOL/day, 20 of 24 runs helped)
    pub lone_whale_slots: u64,
    /// dip27 --presend-live-ann on (off by default): LOG-ONLY annotations ("ann") for the 10-30 loss study's leads: the trigger's
    /// buyers in its last 50 slots and the token's creator / its holding (arm and skip records; the bad-creator list is scored
    /// offline), each attempt's largest other holder at signing (`ob6`), and at a fill: its depth, "ctx85" (another wallet >= 6% at
    /// signing and a drop < 15%: the deeper-limit lead's would-skip) and the holders >= 2% with their hold clocks (the sell-timer
    /// lead). Never changes a decision
    pub ann: bool,
    /// dip28 --presend-live-deep-drop D (0 = off, the default; D in (drop, 0.5]): an attempt's limit drop is D instead of `drop` while,
    /// at its signing, a wallet but the window's whale / re-arm dumper and ours holds >= DEEP_OB6 % of supply (T2 AND re-arm windows).
    /// 0.15 = the 10-30 loss study's "deeper limit" (GUARDS ctx lead; run 37 replay with re-arm: +1.08 SOL alone, +1.29 with the
    /// lone-whale skip; ops/strategies/presend/prevent, sniper-data/multiarm/flt_summary.json)
    pub deep_drop: f64,
    /// dip28 --presend-live-holds-state PATH (needs --presend-live-ann on): the hold clocks are preloaded from PATH at the start (if it
    /// exists) and saved to it at the run's end (the next run continues them; the safe sell-timer check's log needs a long history)
    pub holds_state: Option<String>,
    /// dip31 --presend-live-breaker N:L:W:P (off by default): the CIRCUIT BREAKER (owner 11-03 ~07:45 PKT, after the 11-02 10:29 bait
    /// attack: 13 tokens with one holder template, 4 x ~24 SOL dumps into our holds, -2.1 SOL in 7 min). When N realized losses of at least
    /// L SOL come within W minutes, no new buys for P minutes: T2 triggers skip "breaker", re-arm checks skip "rearm_breaker", armed
    /// windows send nothing ("paused_breaker"). Replay on runs 37-46 real fills (ops/strategies/presend/prevent/breaker): 2:0.2:10:30
    /// fired only in run 42 (+1.54 SOL saved, no other run touched); 1:0.15:10:30 +2.69, 6 runs helped, 1 hurt (-0.14)
    pub breaker: Breaker,
    /// dip32 CREATOR GATE (FILTERS-3, owner 11-03 ~10:00 PKT "do that"; ops/strategies/presend/filters3, verified on the r43-46 holdout):
    /// each of OUR closed positions goes into its token creator's history (realized P&L, FOLLOWED = another wallet, not us / the
    /// trigger whale / the re-arm's holders, bought between our first buy and our last sell landing). At every arm (T2 and re-arm):
    /// --presend-live-cr-unfollowed K:H: skip "cr_unfollowed" when the creator's last <= K positions known in the last H hours were ALL
    ///   not followed (QUIET3-B: DEV +0.68, VAL +0.77, holdout +0.57 SOL); off by default
    pub cr_unf: Option<(usize, u64)>,
    /// --presend-live-cr-loss N:SOL: skip "cr_loss" when the creator has >= N of our earlier positions and their realized sum is
    ///   <= -SOL (the BAD CREATOR ledger, kept across runs, kept positions only, checked at the arm; FILTERS-3 tune 2:0.05 = DEV +0.87,
    ///   VAL w/o the attack +1.70, holdout +0.54 SOL, positive without the top 5 in all three); off by default (cr_loss 0)
    pub cr_loss_n: u32,
    pub cr_loss: i64,
    /// dip35 --presend-live-cr-log on|off (default off; needs --presend-live-cr-loss / -cr-unfollowed): the creator gate LOG-ONLY: the
    ///   ledger is kept and saved as live, its verdict goes on the records as cr.would ("loss" / "unfollowed"), nothing is skipped
    pub cr_log: bool,
    /// --presend-live-creator-state FILE: the creator histories preloaded at the start (the seed / the last run's) and saved back (every
    ///   ~10 min and at the run's end)
    pub cr_state: Option<String>,
    /// --presend-live-f3-log (log-only): the arm / skip records get "f3": {q3a (QUIET3-A: T2, the 120 s ring's trades <= 15 and the
    ///   whale's dumps <= 3, QUIET's rule on), fresh / fresh_n (holders >= 2% with <= 1 hold on record, not the whale / dumper: TAIL G3
    ///   fires at >= 35%)}
    pub f3_log: bool,
    /// dip32 --presend-live-tag-wallets W,W,... (log-only, <= 8; needs --presend-live-f3-log): the T2 arm / skip and re-arm arm records
    ///   get "tags": {wallet prefix: {n: its trades on the token, hold: holds it now, rt: bought before and holds nothing now}} for the
    ///   listed wallets that traded the token (9pQQ study 11-03: "9pQQ round-tripped this token before" = our trips +15..+30 mSOL vs
    ///   -2..+12), and the T2 records get "r41": the trigger's tx ran program 41Pr4XqE (it draws 9pQQ's buys 8-14x)
    pub tag_wallets: Vec<Pk>,
    /// dip33 --presend-live-quiet3a on (owner 11-03 ~13:05 PKT "turn it on live"): QUIET3-A LIVE — a T2 trigger that would arm is skipped
    ///   "quiet3_a" when the token had <= 15 trades in the 120 s ring AND the whale has <= 3 dumps in QUIET's 24 h history (QUIET's rule
    ///   on). Needs --presend-live-quiet-v2-log and the QUIET skip. Real-fill replay: r37 +0.68, r40 +0.41, r42 +2.59 (attack +2.03, 9 of
    ///   its T2 trades), r43 -0.01, r44 +0.38, r48 +0.23; verifier holdout +0.44
    pub q3a_live: bool,
    /// dip34 --presend-live-exact-exit on|off (default on; owner 11-03 ~21:55 PKT "make that update in engine"): the time-ms exit fires on
    ///   the clock. Before, tick() ran only on a feed trade (any token) or after 500 ms of feed silence, so the exit came a median 21 ms
    ///   late (p90 84, max 373 ms; filters3/exitpick: exact timing ~+0.3 SOL/day at 125 ms). The loop now waits at most until the
    ///   earliest open position's exit is due (next_exit_in). off = dip33's timing
    pub exact_exit: bool,
    /// dip34 --presend-live-cr-earn-log K (LOG-ONLY; 0 = off, the default; K in (0, 1]; needs --presend-live-cr-loss). CR-EARNBACK (owner
    ///   11-03 ~22:30 PKT "let them earn back"): a T2 trigger skipped "cr_loss" is still armed by the SHADOW; when the shadow's row c exits
    ///   that window, K x its net (cheap fees, scaled to the live size) is credited to the creator's PAPER column (ps / pn, kept in the
    ///   state file) and written as presend_live_cr_paper; the arm / skip records' "cr" get "earn": {ps, pn, trade = the earn-back rule
    ///   (n >= N and sum + ps <= -SOL is still a block) would trade it}. The live decision NEVER changes: the r39-r50 replay
    ///   (ops/strategies/presend/filters3/crearn) found no earn-back variant positive on DEV, VAL and holdout (A k=0.5: -0.13 / -0.02 /
    ///   -0.11 SOL), so it is collected forward first
    pub cr_earn: f64,
    /// dip34 --presend-live-seen-log [H] (LOG-ONLY; 0 = off, the default; H hours in (0, 48], 3 when given without a value): "seen" on the
    ///   T2 arm / skip (and re-arm arm) records = the whale had a cr_loss / quiet3_a / rearm_cr_loss skip in the last H hours (pslog34.rs)
    pub seen_h: f64,
    /// dip34 --presend-live-eqgrp-log (LOG-ONLY): "eqgrp" (equal-size holder groups >= 2%) on the arm / skip / fill records (pslog34.rs)
    pub eqgrp_log: bool,
    /// dip34 --presend-live-q4-log (LOG-ONLY): "q4" (QUIET4: wh_l10, repeat hold-sellers, wh_unf1h) on the arm / skip records (pslog34.rs)
    pub q4_log: bool,
    /// dip35 --presend-live-fam-log (LOG-ONLY): at every presend_live_arm a background holders read (getProgramAccounts) -> the
    ///   presend_live_fam record (fam = create-slot owners + transfer recipients, % of supply; pslog35.rs)
    pub fam_log: bool,
    /// dip35 --presend-live-fam-thr X (default 26.825, the frozen threshold): only the record's "hit"
    pub fam_thr: f64,
    /// dip35 --presend-live-fam-rpc URL (`${VAR}` expanded from the environment; never printed): the read's RPC (default: rpc_url)
    pub fam_rpc: Option<String>,
    /// dip36 --presend-live-blocklist PATH (LIVE; off when not given): skip an arm whose T2 whale / re-arm dumper / holder >= blocklist_pct %
    ///   is a listed wallet ("blocklist" / "rearm_blocklist"); the file hot-reloads (psblock.rs)
    pub blocklist: Option<String>,
    /// dip36 --presend-live-blocklist-pct X (default 3.0; (0, 100]): the holder role's threshold (% of supply)
    pub blocklist_pct: f64,
    /// dip37c --presend-live-blocklist-send on|off (default on with the blocklist): every send of an armed window is withheld while a listed wallet
    /// holds >= blocklist_pct % of the mint (the window stays armed); the ledger control file's "blocklist_send": "live"|"log" flips it
    pub blocklist_send: bool,
    /// dip36 --presend-fpnb-log on|off (default off; LOG-ONLY): FP-NOBOT scored at every pre-send arm, send slot and fill on its own
    ///   thread (pslog36.rs, src/fpnb.rs): presend_live_fpnb records; never a decision
    pub fpnb_log: bool,
    /// dip36 --presend-fpnb-bots FILE (needed with the log): the follower-bot list (registry engine view or cohort_full_b58.json), hot-reloaded
    pub fpnb_bots: Option<String>,
    /// dip36 --presend-skip2-log on|off (default off; LOG-ONLY; needs --presend-fpnb-log on): the SKIP-2 per-send logistic score on the
    ///   FP-NOBOT records ("skip2"); --presend-skip2-seed FILE seeds its creator / whale / mint ledgers (s2_seed.py)
    pub skip2_log: bool,
    /// dip37b --presend-skip2-live t2,rearm | t2 | rearm | off (default off; LIVE; needs --presend-skip2-log on): the SKIP-2 per-send gate's start
    /// mode (a send whose skip2 verdict says skip is withheld, FP-NOBOT's way); the ledger control file's "skip2" key overrides it
    pub skip2_live: u64,
    pub skip2_seed: Option<String>,
    /// dip36 --presend-fpnb-live t2,rearm | t2 | rearm | off (default off; LIVE; needs --presend-fpnb-log on): the FP-NOBOT send gate's start
    ///   mode (bit 0 T2, bit 1 re-arm); --presend-fpnb-control FILE ({"live": [...]}, re-read every ~10 s) overrides it
    pub fpnb_live: u64,
    pub fpnb_control: Option<String>,
    /// dip36 --presend-fpnb-preload FILE (optional): the 24 h whale history + our earlier results (fp_preload.py); without it they warm up
    pub fpnb_preload: Option<String>,
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
    /// dip26 RE-ARM (default: off)
    pub rearm: RearmCfg,
    /// dip37 FEE A/B (default: off; psfeeab.rs)
    pub fab: psfeeab::FeeAbCfg,
    /// dip37 --presend-live-wh-loss N:SOL (LIVE; wh_loss 0 = off): skip an arm whose T2 whale / re-arm dumper has >= N realized positions with us
    /// summing to <= -SOL (pswh.rs); --presend-live-wh-loss-mode mean: sum / n <= -SOL instead; --presend-live-whale-state PATH: preload + save
    pub wh_loss_n: u32,
    pub wh_loss: i64,
    pub wh_mean: bool,
    pub wh_state: Option<String>,
    /// dip37 --presend-live-wh-learn paper: a "wh_loss"-skipped T2 trigger's shadow row c is added to the whale's ledger (paper position)
    pub wh_learn: bool,
    /// dip37 --presend-live-wh-split on: separate T2 / re-arm ledgers (the same rule)
    pub wh_split: bool,
    /// dip37 --presend-fpnb-stale-hold N (0 = off, the default): with no fresh FP-NOBOT verdict, a send is withheld when the window's last
    /// verdict blocked and is <= N slots old (pslog36::gate_withhold_why); else fail open as dip36
    pub fpnb_stale_hold: u64,
    /// dip37 --presend-live-m2seen-log on (LOG ONLY): nd / m2max / h2_keep / h2_size on the arm and skip records (psh2.rs)
    pub m2seen_log: bool,
    /// dip37 --presend-live-m2seen-gate on (LIVE): skip an arm with nd = 0 ("m2_unseen" / "rearm_m2_unseen"); the counter runs with it
    pub m2seen_gate: bool,
    /// dip37 --presend-live-holder-loss PCT:SOL:WIN (LIVE; hl_loss 0 = off): skip an arm with a holder >= PCT% whose positions with us sum
    /// <= -SOL and never had one >= +WIN (pshl.rs); --presend-live-holder-state PATH; --presend-live-holder-learn paper
    pub hl_pct: f64, pub hl_loss: i64, pub hl_win: i64,
    pub hl_state: Option<String>,
    pub hl_learn: bool,
    /// dip37 --presend-live-ledger-control PATH: {"whale": live|log, "holder": live|log}, re-read every ~10 s
    pub ledger_ctl: Option<String>,
    /// dip38 --presend-live-blocklist-launcher on|off (LIVE; default on WITH the blocklist, off without it): the blocklist also matches the
    /// token's launcher (its create tx's fee payer) at the arm (role "launcher") and in the per-send check
    pub blocklist_launcher: bool,
    /// dip38 --presend-live-insider-log on|off (LOG ONLY; default off): launcher fields, the funding resolver, INSIDER / FAMILY / FAMILY LEDGER
    /// on presend_live_insider records at arm / send / fill / realize (pslog38.rs)
    pub insider_log: bool,
    /// dip38 --presend-live-fund-rpc URL (`${VAR}` expanded from the environment; never printed; default the public mainnet endpoint),
    /// --presend-live-fund-rps X (RPC calls per second, (0, 50], default 3), --presend-live-fund-state FILE (wallet -> chain, hot-reloaded),
    /// --presend-live-family-state FILE (the family ledger)
    pub fund_rpc: Option<String>,
    pub fund_rps: f64,
    pub fund_state: Option<String>,
    pub family_state: Option<String>,
    /// dip38 --presend-live-shape-log on|off (LOG ONLY; default off): the SHAPE ledger on presend_live_shape records; --presend-live-shape-state FILE
    pub shape_log: bool,
    pub shape_state: Option<String>,
    /// dip38 --presend-live-s1-log on|off (LOG ONLY; default off): the PSM12-S1 verdict on every arm, its fill and realized (pss1.rs)
    pub s1_log: bool,
    /// dip38 --presend-live-s1 off|t2|rearm|t2,rearm (LIVE; default off, NOT used now): skip an arm S1 would skip; the control file's "s1" overrides
    pub s1_live: u64,
    /// dip38 --presend-live-s1-parts nd,age,whale,cold (default all): the parts the live gate acts on
    pub s1_parts: u8,
    /// dip39 the BOT DEPTH gate (None = off, the default; psbd.rs): --presend-live-botdepth-source list (default: --presend-live-botdepth
    /// MIN:SLOTS + --presend-live-botdepth-list PATH) | organic (--presend-live-botdepth-organic DMIN:QMIN[:TRIPS[:HOURS]], default 2:2:10:2;
    /// --presend-live-botdepth-state PATH optional); --presend-live-botdepth-mode log|live (default log: nothing withheld); the control
    /// file's "botdepth" overrides the mode
    pub bd: Option<psbd::Gate>,
    pub bd_list: Option<String>,
    pub bd_live: bool,
    pub bd_state: Option<String>,
    /// dip41 the whale FAST-DUMP LEDGER (--presend-live-dumper-ledger on|off, default off; psdl.rs) and its state file
    /// (--presend-live-dumper-state PATH); the WIDE-DUMPER tier with it: --presend-live-wide-dumper N:SCORE (default 3:0.8),
    /// --presend-live-wide-dumper-mode log|live (default log: records only), --presend-live-wide-size-sol X (default the T2 size); the control
    /// file's "widedumper" flips the mode
    pub dl_on: bool,
    pub dl_state: Option<String>,
    pub wd: psdl::WdCfg,
    pub wd_live: bool,
    pub wd_size: u64,
    /// dip41 QF2 (with the ledger; None = off): --presend-live-qf2 N:SCORE[:WIN], --presend-live-qf2-filters SOLMIN:SOLMAX:CURVEMIN:CURVEMAX:AGEMAX
    /// (default 2:8:36:70:300), --presend-live-qf2-mode log|live (default log); the control file's "qf2" flips the mode
    pub qf: Option<psdl::QfCfg>,
    pub qf_filt: psdl::QfFilt,
    pub qf_live: bool,
    /// dip42 FAM2 (LOG ONLY; None = off): --presend-live-fam2 on, --presend-live-fam2-wallets W1,W2,.. (default the 2NUM family's 4),
    /// --presend-live-fam2-slots N (300): "fam2" on every arm / skip / fill / realized record (psfam2.rs)
    pub f2: Option<psfam2::F2Cfg>,
    /// dip42 Q1 (LOG ONLY; None = off): --q1-log on, --q1-bots FILE, --q1-fresh-state FILE and the rule's thresholds (psq1.rs)
    pub q1: Option<psq1::Q1Cfg>,
    /// dip43 Builder A's options (ps43.rs; all off / log by default)
    pub c43: ps43::Cfg43,
    /// dip43 BUILDER B's items (ps43_b.rs; Default = all off = dip42)
    pub b43: ps43_b::B43Cfg,
}

impl Cfg {
    /// dip37: the holder ledger is on
    pub fn hl_on(&self) -> bool { self.hl_loss > 0 }
    /// dip37: the HYBRID-2 counter runs (its log or its gate)
    pub fn m2seen_on(&self) -> bool { self.m2seen_log || self.m2seen_gate || self.s1_log }
    /// dip37: the whale / dumper loss ledger is on
    pub fn wh_on(&self) -> bool { self.wh_loss > 0 }
    /// dip37: its rule as given ("2:0.05 sum")
    pub fn wh_spec(&self) -> String {
        format!("{}:{} {}{}{}", self.wh_loss_n, self.wh_loss as f64 / 1e9, if self.wh_mean { "mean" } else { "sum" }, if self.wh_split { " split" } else { "" },
            if self.wh_learn { " learn-paper" } else { "" })
    }

    /// dip32: the creator gate is on (either rule)
    pub fn cr_on(&self) -> bool { self.cr_unf.is_some() || self.cr_loss > 0 }

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
        // dip43 B: its flags need --presend-live too
        ps43_b::needs_presend_live(argv)?;
        if !has("--presend-live") {
            if let Some(f) = FLAGS.iter().chain(QFLAGS.iter()).chain(RFLAGS.iter()).chain(FPFLAGS.iter()).chain(FABFLAGS.iter()).chain(WHFLAGS.iter()).chain(H2FLAGS.iter()).chain(HLFLAGS.iter()).chain(BLSFLAGS.iter()).chain(D38FLAGS.iter()).chain(S1FLAGS.iter()).chain(BDFLAGS.iter()).chain(DLFLAGS.iter()).chain(F2FLAGS.iter()).chain(Q1FLAGS.iter()).chain(A43FLAGS.iter()).find(|f| has(f)) { bail!("{f} needs --presend-live"); }
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
        let spend = (arg_f64("--presend-live-size-sol", sh.size_sol) * 1e9).round() as u64;
        let quiet = Cfg::quiet_from(&has, &arg, &arg_f64, &onoff)?;
        let one_position = onoff("--presend-live-one-position", true)?;
        // dip26: the re-arm's flags (off: RearmCfg { on: false, .. }, nothing of it runs)
        let rearm = Cfg::rearm_from(&has, &arg, &arg_u64, &arg_f64, &onoff, spend, quiet.skip, one_position)?;
        // dip37: the fee A/B's flags (off: FeeAbCfg::default(), nothing of it runs)
        let fab = Cfg::fab_from(&has, &arg, &arg_u64_opt, &onoff)?;
        let mut c = Cfg {
            dry,
            spend,
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
            one_position,
            min_age_slots: arg_u64("--presend-live-min-age-slots", 0),
            lone_whale_slots: arg_u64("--presend-live-lone-whale-slots", 0),
            ann: onoff("--presend-live-ann", false)?,
            deep_drop: arg_f64("--presend-live-deep-drop", 0.0),
            holds_state: arg("--presend-live-holds-state").filter(|p| !p.starts_with("--")),
            breaker: match arg("--presend-live-breaker") { Some(s) => Breaker::parse(&s)?, None => Breaker::default() },
            cr_unf: match arg("--presend-live-cr-unfollowed") { Some(s) => Some(cr_unf_parse(&s)?), None => None },
            cr_loss_n: match arg("--presend-live-cr-loss") { Some(s) => cr_loss_parse(&s)?.0, None => 0 },
            cr_loss: match arg("--presend-live-cr-loss") { Some(s) => cr_loss_parse(&s)?.1, None => 0 },
            cr_state: arg("--presend-live-creator-state").filter(|p| !p.starts_with("--")),
            cr_log: onoff("--presend-live-cr-log", false)?,
            f3_log: has("--presend-live-f3-log"),
            tag_wallets: match arg("--presend-live-tag-wallets") { Some(s) => tag_parse(&s)?, None => Vec::new() },
            q3a_live: onoff("--presend-live-quiet3a", false)?,
            exact_exit: onoff("--presend-live-exact-exit", true)?,
            cr_earn: match arg("--presend-live-cr-earn-log") { Some(s) => cr_earn_parse(&s)?, None if has("--presend-live-cr-earn-log") => cr_earn_parse("")?, None => 0.0 },
            // dip34 (log-only)
            seen_h: if has("--presend-live-seen-log") { seen_parse(arg("--presend-live-seen-log").as_deref())? } else { 0.0 },
            eqgrp_log: has("--presend-live-eqgrp-log"),
            q4_log: has("--presend-live-q4-log"),
            // dip35 (log-only)
            fam_log: has("--presend-live-fam-log"),
            fam_thr: arg_f64("--presend-live-fam-thr", pslog35::FAM_THR),
            fam_rpc: arg("--presend-live-fam-rpc").filter(|u| !u.starts_with("--")),
            // dip36 LIVE blocklist
            blocklist: arg("--presend-live-blocklist").filter(|p| !p.starts_with("--")),
            blocklist_pct: arg_f64("--presend-live-blocklist-pct", psblock::BL_PCT),
            blocklist_send: onoff("--presend-live-blocklist-send", true)? && arg("--presend-live-blocklist").is_some(),
            // dip36 (log-only)
            fpnb_log: onoff("--presend-fpnb-log", false)?,
            fpnb_bots: arg("--presend-fpnb-bots").filter(|p| !p.starts_with("--")),
            fpnb_preload: arg("--presend-fpnb-preload").filter(|p| !p.starts_with("--")),
            skip2_log: onoff("--presend-skip2-log", false)?,
            skip2_live: match arg("--presend-skip2-live") { Some(s) => pslog36::mode_parse(&s).map_err(|e| anyhow::anyhow!("--presend-skip2-live {e}"))?, None => 0 },
            skip2_seed: arg("--presend-skip2-seed").filter(|p| !p.starts_with("--")),
            fpnb_live: match arg("--presend-fpnb-live") { Some(s) => pslog36::mode_parse(&s).map_err(|e| anyhow::anyhow!("--presend-fpnb-live {e}"))?, None => 0 },
            fpnb_control: arg("--presend-fpnb-control").filter(|p| !p.starts_with("--")),
            whale_pct: sh.whale_pct, window_slots: sh.window_slots, live_ms: sh.live_ms, exit_slots: sh.exit_slots, tp: sh.tp, sl: sh.sl,
            exit_ms: arg_u64("--presend-live-exit-ms", 0),
            quiet,
            quiet_v2_log: has("--presend-live-quiet-v2-log"),
            rearm,
            fab,
            // dip37 the whale / dumper loss ledger (LIVE) and the FP-NOBOT stale hold
            wh_loss_n: match arg("--presend-live-wh-loss") { Some(s) => pswh::wh_loss_parse(&s)?.0, None => 0 },
            wh_loss: match arg("--presend-live-wh-loss") { Some(s) => pswh::wh_loss_parse(&s)?.1, None => 0 },
            wh_mean: match arg("--presend-live-wh-loss-mode").as_deref() { None | Some("sum") => false, Some("mean") => true, Some(x) => bail!("--presend-live-wh-loss-mode {x}: sum | mean") },
            wh_state: arg("--presend-live-whale-state").filter(|p| !p.starts_with("--")),
            wh_learn: match arg("--presend-live-wh-learn").as_deref() { None | Some("off") => false, Some("paper") => true, Some(x) => bail!("--presend-live-wh-learn {x}: paper | off") },
            wh_split: onoff("--presend-live-wh-split", false)?,
            fpnb_stale_hold: arg_u64("--presend-fpnb-stale-hold", 0),
            m2seen_log: onoff("--presend-live-m2seen-log", false)?,
            m2seen_gate: onoff("--presend-live-m2seen-gate", false)?,
            hl_pct: match arg("--presend-live-holder-loss") { Some(s) => pshl::hl_parse(&s)?.0, None => 0.0 },
            hl_loss: match arg("--presend-live-holder-loss") { Some(s) => pshl::hl_parse(&s)?.1, None => 0 },
            hl_win: match arg("--presend-live-holder-loss") { Some(s) => pshl::hl_parse(&s)?.2, None => 0 },
            hl_state: arg("--presend-live-holder-state").filter(|p| !p.starts_with("--")),
            hl_learn: match arg("--presend-live-holder-learn").as_deref() { None | Some("off") => false, Some("paper") => true, Some(x) => bail!("--presend-live-holder-learn {x}: paper | off") },
            ledger_ctl: arg("--presend-live-ledger-control").filter(|p| !p.starts_with("--")),
            // dip38: the blocklist's launcher match (LIVE, default on with the blocklist) and the anti-bait logs (off by default)
            blocklist_launcher: onoff("--presend-live-blocklist-launcher", true)? && arg("--presend-live-blocklist").is_some(),
            insider_log: onoff("--presend-live-insider-log", false)?,
            fund_rpc: arg("--presend-live-fund-rpc").filter(|u| !u.starts_with("--")),
            fund_rps: arg_f64("--presend-live-fund-rps", psfund::FUND_RPS),
            fund_state: arg("--presend-live-fund-state").filter(|p| !p.starts_with("--")),
            family_state: arg("--presend-live-family-state").filter(|p| !p.starts_with("--")),
            shape_log: onoff("--presend-live-shape-log", false)?,
            shape_state: arg("--presend-live-shape-state").filter(|p| !p.starts_with("--")),
            // dip38 PSM12-S1 (log only; the live gate off by default)
            s1_log: onoff("--presend-live-s1-log", false)?,
            s1_live: match arg("--presend-live-s1") { Some(s) if !s.starts_with("--") => pslog36::mode_parse(&s).map_err(|e| anyhow::anyhow!("--presend-live-s1 {e}"))?, _ => 0 },
            s1_parts: match arg("--presend-live-s1-parts") { Some(s) if !s.starts_with("--") => pss1::parts_parse(&s)?, _ => pss1::P_ALL },
            // dip39 BOT DEPTH (off unless its flag; log mode by default)
            bd: None,
            bd_list: arg("--presend-live-botdepth-list").filter(|p| !p.starts_with("--")),
            bd_live: match arg("--presend-live-botdepth-mode") { Some(s) if !s.starts_with("--") => psbd::mode_parse(&s)?, _ => false },
            bd_state: arg("--presend-live-botdepth-state").filter(|p| !p.starts_with("--")),
            // dip41 the dumper ledger + the WIDE-DUMPER tier (off unless --presend-live-dumper-ledger on; the tier's mode log by default)
            dl_on: onoff("--presend-live-dumper-ledger", false)?,
            dl_state: arg("--presend-live-dumper-state").filter(|p| !p.starts_with("--")),
            wd: match arg("--presend-live-wide-dumper") { Some(s) if !s.starts_with("--") => psdl::wd_parse(&s)?, _ => psdl::WdCfg::default() },
            wd_live: match arg("--presend-live-wide-dumper-mode") { Some(s) if !s.starts_with("--") => psdl::mode_parse("--presend-live-wide-dumper-mode", &s)?, _ => false },
            qf: match arg("--presend-live-qf2") { Some(s) if !s.starts_with("--") => Some(psdl::qf_parse(&s)?), _ => None },
            qf_filt: match arg("--presend-live-qf2-filters") { Some(s) if !s.starts_with("--") => psdl::qf_filt_parse(&s)?, _ => psdl::QfFilt::default() },
            qf_live: match arg("--presend-live-qf2-mode") { Some(s) if !s.starts_with("--") => psdl::mode_parse("--presend-live-qf2-mode", &s)?, _ => false },
            wd_size: match arg("--presend-live-wide-size-sol") {
                Some(v) if !v.starts_with("--") => {
                    let x: f64 = v.parse().ok().filter(|x: &f64| x.is_finite()).with_context(|| format!("--presend-live-wide-size-sol {v}: not a number (SOL)"))?;
                    (x * 1e9).round().max(0.0) as u64
                }
                _ => spend,
            },
            // dip42 (LOG ONLY; set below)
            f2: None,
            q1: None,
            // dip43 (ps43.rs)
            c43: ps43::Cfg43::parse(argv)?,
            // dip43 B (every item off unless its flag)
            b43: ps43_b::B43Cfg::from_argv(argv)?,
        };
        // dip43: the true balances and the fan-out come from dip35's fam read at the arm (verifier 11-10: the feeds carry no plain transfers)
        if (c.c43.tbal || c.c43.fanout.is_some()) && !c.fam_log { bail!("--presend-live-tbal / --presend-live-cascade / --presend-live-fanout need --presend-live-fam-log (its RPC read at the arm is their source)"); }
        if c.c43.fp_strict.is_some() && !c.fpnb_log { bail!("--presend-live-fpnb-strict needs --presend-fpnb-log on (the score it thresholds)"); }
        // dip42 FAM2 + Q1 (both LOG ONLY; off unless their switch): every value given; the parameters need their switch
        for f in F2FLAGS.iter().chain(Q1FLAGS.iter()) { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        let f2_on = onoff("--presend-live-fam2", false)?;
        if !f2_on { if let Some(f) = F2FLAGS[1..].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-fam2 on"); } }
        let f2_wallets = match arg("--presend-live-fam2-wallets") { Some(s) => psfam2::wallets_parse(&s)?, None => psfam2::default_wallets() };
        if f2_on {
            if has("--presend-live-fam2-slots") && arg_u64_opt("--presend-live-fam2-slots").is_none() { bail!("--presend-live-fam2-slots N: a whole number of slots"); }
            let slots = arg_u64("--presend-live-fam2-slots", psfam2::F2_SLOTS);
            if !(1..=psfam2::F2_SLOTS_MAX).contains(&slots) { bail!("--presend-live-fam2-slots must be 1..{} slots", psfam2::F2_SLOTS_MAX); }
            c.f2 = Some(psfam2::F2Cfg { wallets: f2_wallets.clone(), slots });
        }
        let q1_on = onoff("--q1-log", false)?;
        if !q1_on { if let Some(f) = Q1FLAGS[1..].iter().find(|f| has(f)) { bail!("{f} needs --q1-log on"); } }
        if q1_on {
            let bots = arg("--q1-bots").context("--q1-log on needs --q1-bots FILE (the bot registry / a list of bot wallets: \"quiet\" = none of them on the token)")?;
            for f in ["--q1-bot-slots", "--q1-dip-slots", "--q1-fresh-max", "--q1-gap-slots"] { if has(f) && arg_u64_opt(f).is_none() { bail!("{f}: a whole number"); } }
            for f in ["--q1-min-sol", "--q1-size-sol", "--q1-fresh-hours"] { if has(f) && !arg(f).is_some_and(|v| v.parse::<f64>().is_ok_and(|x| x.is_finite())) { bail!("{f}: a number"); } }
            let (min_sol, size, hours) = (arg_f64("--q1-min-sol", 0.5), arg_f64("--q1-size-sol", 0.5), arg_f64("--q1-fresh-hours", 48.0));
            let age = match arg("--q1-age-slots") { Some(s) => psq1::age_parse(&s)?, None => (3, 80) };
            let (bot_slots, dip_slots, fresh_max, gap) = (arg_u64("--q1-bot-slots", 100), arg_u64("--q1-dip-slots", 200), arg_u64("--q1-fresh-max", 2), arg_u64("--q1-gap-slots", 30));
            if !(min_sol >= 0.01 && min_sol <= 100.0) { bail!("--q1-min-sol must be 0.01..100 SOL"); }
            if !(size >= 0.01 && size <= 10.0) { bail!("--q1-size-sol must be 0.01..10 SOL (the paper trade's size)"); }
            if !(hours >= 1.0 && hours <= 240.0) { bail!("--q1-fresh-hours must be 1..240 hours (a wallet idle that long is forgotten)"); }
            if !(1..=psq1::Q1_FREQ_AGE).contains(&bot_slots) || !(1..=psq1::Q1_FREQ_AGE).contains(&dip_slots) { bail!("--q1-bot-slots / --q1-dip-slots must be 1..{} slots", psq1::Q1_FREQ_AGE); }
            if fresh_max as usize > psq1::Q1_K - 2 { bail!("--q1-fresh-max must be 0..{} earlier tokens", psq1::Q1_K - 2); }
            if gap > 100_000 { bail!("--q1-gap-slots must be 0..100000 slots"); }
            c.q1 = Some(psq1::Q1Cfg { min_sol: (min_sol * 1e9).round() as u64, age, bot_slots, dip_slots, fresh_max: fresh_max as u32, gap, size: (size * 1e9).round() as u64,
                fresh_ns: (hours * 3.6e12).round() as u64, bots, state: arg("--q1-fresh-state"), fam: f2_wallets });
        }
        // dip41: every value given; the state / the tier's flags need the ledger
        for f in DLFLAGS { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        if !c.dl_on { if let Some(f) = DLFLAGS[1..].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-dumper-ledger on"); } }
        if c.qf.is_none() { if let Some(f) = DLFLAGS[6..].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-qf2 N:SCORE[:WIN]"); } }
        // dip39 BOT DEPTH: every value given; the list source needs MIN:SLOTS and the list, the organic one refuses them; each source's flags
        // need it; the mode needs a gate
        for f in BDFLAGS { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        let organic = match arg("--presend-live-botdepth-source").as_deref() { None | Some("list") => false, Some("organic") => true,
            Some(x) => bail!("--presend-live-botdepth-source {x}: list | organic") };
        if organic {
            if let Some(f) = ["--presend-live-botdepth", "--presend-live-botdepth-list"].iter().find(|f| has(f)) {
                bail!("{f} is the list source's: --presend-live-botdepth-source organic uses --presend-live-botdepth-organic DMIN:QMIN");
            }
            c.bd = Some(psbd::Gate::Org(match arg("--presend-live-botdepth-organic") { Some(s) => psbd::org_parse(&s)?, None => psbd::OrgCfg::default() }));
        } else {
            if let Some(f) = ["--presend-live-botdepth-organic", "--presend-live-botdepth-state"].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-botdepth-source organic"); }
            if let Some(s) = arg("--presend-live-botdepth") { let (min, slots) = psbd::spec_parse(&s)?; c.bd = Some(psbd::Gate::List { min, slots }); }
            if c.bd.is_none() { if let Some(f) = ["--presend-live-botdepth-list", "--presend-live-botdepth-mode"].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-botdepth MIN:SLOTS"); } }
            if c.bd.is_some() && c.bd_list.is_none() { bail!("--presend-live-botdepth needs --presend-live-botdepth-list FILE (the listed bot wallets)"); }
        }
        // dip38 PSM12-S1: every value given; the live gate and the parts need the log; the log needs the whale ledger (its history)
        for f in S1FLAGS { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        if c.s1_live != 0 && !c.s1_log { bail!("--presend-live-s1 needs --presend-live-s1-log on (the verdict it acts on)"); }
        if has("--presend-live-s1-parts") && !c.s1_log { bail!("--presend-live-s1-parts needs --presend-live-s1-log on"); }
        if c.s1_log && !c.wh_on() { bail!("--presend-live-s1-log on needs --presend-live-wh-loss N:SOL (S1 reads the whale / dumper ledger's history)"); }
        // dip38: every value given; the blocklist's launcher match needs the blocklist, the resolver's / ledgers' parameters their log
        for f in D38FLAGS { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        if has("--presend-live-blocklist-launcher") && arg("--presend-live-blocklist").is_none() { bail!("--presend-live-blocklist-launcher needs --presend-live-blocklist PATH"); }
        if !c.insider_log { if let Some(f) = D38FLAGS[2..6].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-insider-log on"); } }
        if has("--presend-live-shape-state") && !c.shape_log { bail!("--presend-live-shape-state needs --presend-live-shape-log on"); }
        if let Some(v) = arg("--presend-live-fund-rps") { if !v.parse::<f64>().is_ok_and(|x| x > 0.0 && x <= 50.0) { bail!("--presend-live-fund-rps must be in (0, 50] calls per second"); } }
        for f in HLFLAGS { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        if !c.hl_on() { if let Some(f) = HLFLAGS[1..3].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-holder-loss PCT:SOL:WIN"); } }
        if c.ledger_ctl.is_some() && !c.hl_on() && !c.wh_on() && c.bd.is_none() && !c.dl_on { bail!("--presend-live-ledger-control needs --presend-live-wh-loss, --presend-live-holder-loss, --presend-live-botdepth or --presend-live-dumper-ledger (what it switches)"); }
        // dip37: the ledger's flags need a value and the rule; the stale hold needs the live gate
        for f in WHFLAGS { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        if !c.wh_on() { if let Some(f) = WHFLAGS[1..].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-wh-loss N:SOL"); } }
        if has("--presend-fpnb-stale-hold") && arg("--presend-fpnb-stale-hold").is_none_or(|v| v.parse::<u64>().is_err()) { bail!("--presend-fpnb-stale-hold N: a whole number of slots (0 = off)"); }
        if c.fpnb_stale_hold > 20 { bail!("--presend-fpnb-stale-hold must be 0 (off) or 1..20 slots"); }
        if c.fpnb_stale_hold > 0 && c.fpnb_live == 0 && c.fpnb_control.is_none() { bail!("--presend-fpnb-stale-hold needs the FP-NOBOT live gate (--presend-fpnb-live / --presend-fpnb-control)"); }
        if has("--presend-live-fam-rpc") && c.fam_rpc.is_none() { bail!("--presend-live-fam-rpc needs a URL ({}VAR{} expanded from the environment)", "${", "}"); }
        if (has("--presend-live-fam-thr") || has("--presend-live-fam-rpc")) && !c.fam_log { bail!("--presend-live-fam-thr / --presend-live-fam-rpc need --presend-live-fam-log"); }
        // dip36: the FP-NOBOT paths need a value and the log on; the log needs the bot list
        for f in ["--presend-fpnb-bots", "--presend-fpnb-preload"] {
            if has(f) && arg(f).is_none_or(|p| p.starts_with("--")) { bail!("{f} needs a path"); }
            if has(f) && !c.fpnb_log { bail!("{f} needs --presend-fpnb-log on"); }
        }
        if has("--presend-live-blocklist") && c.blocklist.is_none() { bail!("--presend-live-blocklist needs a path"); }
        if has("--presend-live-blocklist-pct") && c.blocklist.is_none() { bail!("--presend-live-blocklist-pct needs --presend-live-blocklist PATH"); }
        if has("--presend-live-blocklist-send") && c.blocklist.is_none() { bail!("--presend-live-blocklist-send needs --presend-live-blocklist PATH"); }
        if !(c.blocklist_pct > 0.0 && c.blocklist_pct <= 100.0) { bail!("--presend-live-blocklist-pct must be in (0, 100] (% of supply)"); }
        if has("--presend-skip2-seed") && c.skip2_seed.is_none() { bail!("--presend-skip2-seed needs a path"); }
        if has("--presend-fpnb-control") && c.fpnb_control.is_none() { bail!("--presend-fpnb-control needs a path"); }
        if has("--presend-fpnb-live") && arg("--presend-fpnb-live").is_none_or(|v| v.starts_with("--")) { bail!("--presend-fpnb-live needs t2,rearm | t2 | rearm | off"); }
        if (c.fpnb_live != 0 || c.fpnb_control.is_some()) && !c.fpnb_log { bail!("--presend-fpnb-live / --presend-fpnb-control need --presend-fpnb-log on (the scores they act on)"); }
        if c.skip2_log && !c.fpnb_log { bail!("--presend-skip2-log on needs --presend-fpnb-log on (it reuses FP-NOBOT's per-send inputs)"); }
        if c.skip2_seed.is_some() && !c.skip2_log { bail!("--presend-skip2-seed needs --presend-skip2-log on"); }
        if has("--presend-skip2-live") && arg("--presend-skip2-live").is_none_or(|v| v.starts_with("--")) { bail!("--presend-skip2-live needs t2,rearm | t2 | rearm | off"); }
        if c.skip2_live != 0 && !c.skip2_log { bail!("--presend-skip2-live needs --presend-skip2-log on (the verdict it acts on)"); }
        if c.fpnb_log && c.fpnb_bots.is_none() { bail!("--presend-fpnb-log on needs --presend-fpnb-bots FILE (the follower-bot list)"); }
        c.check(live, cap)?;
        Ok(Some(c))
    }

    /// dip37 FEE A/B's flags. Refused: a value missing / not a whole number / not on|off / not arm|hour, a parameter without
    /// --presend-live-fee-ab on, the A/B on without arm B's CU price, an unknown leader client; the ranges in check()
    fn fab_from(has: &dyn Fn(&str) -> bool, arg: &dyn Fn(&str) -> Option<String>, arg_u64_opt: &dyn Fn(&str) -> Option<u64>,
                onoff: &dyn Fn(&str, bool) -> Result<bool>) -> Result<psfeeab::FeeAbCfg> {
        for f in FABFLAGS { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        let on = onoff("--presend-live-fee-ab", false)?;
        if !on {
            if let Some(f) = FABFLAGS[1..].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-fee-ab on"); }
            return Ok(psfeeab::FeeAbCfg::default());
        }
        for f in &FABFLAGS[1..4] {
            if let Some(v) = arg(f) { if v.parse::<u64>().is_err() { bail!("{f} {v}: not a whole number"); } }
        }
        let cu_price = arg_u64_opt("--presend-live-ab-cu-price-micro").context("--presend-live-fee-ab on needs --presend-live-ab-cu-price-micro N (arm B's CU price)")?;
        let cu_limit = arg_u64_opt("--presend-live-ab-cu-limit").map(|x| x.min(u32::MAX as u64) as u32);
        let tip = arg_u64_opt("--presend-live-ab-tip-lamports");
        let clients = match arg("--presend-live-ab-clients") { Some(s) => psfeeab::clients_parse(&s)?, None => psfeeab::FeeAbCfg::default().clients };
        let split = match arg("--presend-live-ab-split").as_deref() {
            None | Some("arm") => psfeeab::Split::Arm,
            Some("hour") => psfeeab::Split::Hour,
            Some(x) => bail!("--presend-live-ab-split {x}: arm | hour"),
        };
        Ok(psfeeab::FeeAbCfg { on, split, cu_price, cu_limit, tip, clients })
    }

    /// dip26 RE-ARM's flags. Refused: a value missing or not a number / not on|off / not N:M, a parameter without --presend-live-rearm
    /// on, the R5 skip without the QUIET arm rule (--presend-live-quiet-skip on: its whale history, cohort and follower-bot lists), the
    /// re-arm with --presend-live-one-position off (never two positions at once); the ranges and the per-buy cap in check()
    #[allow(clippy::too_many_arguments)]
    fn rearm_from(has: &dyn Fn(&str) -> bool, arg: &dyn Fn(&str) -> Option<String>, arg_u64: &dyn Fn(&str, u64) -> u64, arg_f64: &dyn Fn(&str, f64) -> f64,
                  onoff: &dyn Fn(&str, bool) -> Result<bool>, spend: u64, quiet_skip: bool, one_position: bool) -> Result<RearmCfg> {
        for f in RFLAGS { if has(f) && arg(f).is_none_or(|v| v.starts_with("--")) { bail!("{f} needs a value"); } }
        let on = onoff("--presend-live-rearm", false)?;
        if !on { if let Some(f) = RFLAGS[1..].iter().find(|f| has(f)) { bail!("{f} needs --presend-live-rearm on"); } }
        if let Some(v) = arg("--presend-live-rearm-size-sol") { if !v.parse::<f64>().is_ok_and(|x| x.is_finite()) { bail!("--presend-live-rearm-size-sol {v}: not a number (SOL)"); } }
        if let Some(v) = arg("--presend-live-rearm-gap-slots") { if v.parse::<u64>().is_err() { bail!("--presend-live-rearm-gap-slots {v}: not a whole number of slots"); } }
        let size = match arg("--presend-live-rearm-size-sol") { Some(_) => (arg_f64("--presend-live-rearm-size-sol", 0.0) * 1e9).round().max(0.0) as u64, None => spend };
        let stop = match arg("--presend-live-rearm-quiet-stop") {
            Some(s) => pq::QStop::parse(&s).map_err(|e| anyhow::anyhow!("--presend-live-rearm-quiet-stop {e}"))?,
            None => pq::QStop { n: 6, m: 2 },
        };
        let r5_skip = onoff("--presend-live-rearm-r5-skip", false)?;
        if on && r5_skip && !quiet_skip {
            bail!("--presend-live-rearm-r5-skip on needs --presend-live-quiet-skip on (the QUIET arm rule's whale dump history, cohort and follower-bot lists)");
        }
        if on && !one_position { bail!("REFUSED: --presend-live-rearm on needs --presend-live-one-position on (never two positions at once)"); }
        Ok(RearmCfg { on, spend: size, gap: arg_u64("--presend-live-rearm-gap-slots", 20), stop, r5_skip })
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
        // dip37: arm B's ranges (off: nothing)
        self.fab.check()?;
        if self.cu_price > 1_000_000 { bail!("--presend-live-cu-price-micro above 1,000,000 (a failed attempt would cost > 0.0001 SOL in priority): refusing"); }
        if self.tip.is_some_and(|t| t > 10_000_000) { bail!("--presend-live-tip-lamports above 0.01 SOL: refusing"); }
        if !(1..=200).contains(&self.max_per_sec) || !(1..=200).contains(&self.path_max_per_sec) { bail!("--presend-live-max-per-sec / --presend-live-path-max-per-sec must be 1..200"); }
        // dip24: --presend-live-max-fills any N (0 = unlimited); the fee budget is per rolling 24 h, (0, 100] SOL
        if self.fee_budget == 0 || self.fee_budget > 100_000_000_000 { bail!("--presend-live-fee-budget-sol must be in (0, 100] SOL per rolling 24 h"); }
        if self.exit_ms != 0 && !(50..=2_000).contains(&self.exit_ms) { bail!("--presend-live-exit-ms must be 0 (off) or 50..2000"); }
        // dip27: the lone-whale window within the recent buys a token keeps
        if self.lone_whale_slots > pl::RB_SLOTS { bail!("--presend-live-lone-whale-slots must be 0 (off) or 1..{}", pl::RB_SLOTS); }
        // dip28: the deeper limit is deeper than the normal one; the holds state needs the clocks (the annotations)
        if self.deep_drop != 0.0 && !(self.deep_drop > self.drop && self.deep_drop <= 0.5) { bail!("--presend-live-deep-drop must be 0 (off) or in ({}, 0.5] (deeper than --presend-live-drop)", self.drop); }
        if self.q3a_live && !(self.quiet_v2_log && self.quiet.skip) { bail!("--presend-live-quiet3a on needs --presend-live-quiet-v2-log and the QUIET skip (its inputs)"); }
        if !self.tag_wallets.is_empty() && !self.f3_log { bail!("--presend-live-tag-wallets needs --presend-live-f3-log (log-only fields)"); }
        if self.cr_earn > 0.0 && self.cr_loss == 0 { bail!("--presend-live-cr-earn-log needs --presend-live-cr-loss (it credits the loss ledger's blocked creators)"); }
        if self.cr_log && !self.cr_on() { bail!("--presend-live-cr-log on needs --presend-live-cr-loss or --presend-live-cr-unfollowed (the rule it logs)"); }
        if self.cr_state.is_some() && !self.cr_on() { bail!("--presend-live-creator-state needs --presend-live-cr-unfollowed or --presend-live-cr-loss (the histories are kept only with the gate)"); }
        if !(self.fam_thr > 0.0 && self.fam_thr <= 100.0) { bail!("--presend-live-fam-thr must be in (0, 100] (% of supply)"); }
        if self.holds_state.is_some() && !self.ann { bail!("--presend-live-holds-state needs --presend-live-ann on (the hold clocks are kept only with it)"); }
        // dip41: the wide windows' size as the pre-send size (and within the per-buy cap)
        if self.dl_on {
            if self.wd_size == 0 || self.wd_size > 2_000_000_000 { bail!("--presend-live-wide-size-sol must be in (0, 2]"); }
            if live && self.wd_size > cap { bail!("REFUSED: --presend-live-wide-size-sol {:.3} exceeds --max-sol (the per-buy cap)", self.wd_size as f64 / 1e9); }
        }
        // dip26 RE-ARM: its size as the pre-send size (and within the per-buy cap), its window length
        if self.rearm.on {
            if self.rearm.spend == 0 || self.rearm.spend > 2_000_000_000 { bail!("--presend-live-rearm-size-sol must be in (0, 2]"); }
            if live && self.rearm.spend > cap { bail!("REFUSED: --presend-live-rearm-size-sol {:.3} exceeds --max-sol (the per-buy cap)", self.rearm.spend as f64 / 1e9); }
            if !(1..=60).contains(&self.rearm.gap) { bail!("--presend-live-rearm-gap-slots must be 1..60 (the window's last slot = dump + 3 + G)"); }
        }
        Ok(())
    }

    /// a failed attempt's fee: 5,000 base + CU limit x price (the priority fee is charged on the limit)
    pub fn fail_fee(&self) -> u64 { 5_000 + (self.cu_limit as u64 * self.cu_price).div_ceil(1_000_000) }

    pub fn json(&self) -> serde_json::Value {
        let mut j = serde_json::json!({"dry": self.dry, "spend": self.spend, "k": self.k, "drop": self.drop, "deadline_slots": self.deadline_slots, "cu_limit": self.cu_limit,
            "cu_price": self.cu_price, "tip": self.tip, "routes": self.routes, "max_per_sec": self.max_per_sec, "path_max_per_sec": self.path_max_per_sec,
            "max_fills": self.max_fills, "fee_budget": self.fee_budget, "create_slot": self.create_slot, "one_position": self.one_position, "min_age_slots": self.min_age_slots,
            "whale_pct": self.whale_pct, "window_slots": self.window_slots, "live_ms": self.live_ms, "exit_slots": self.exit_slots, "exit_ms": self.exit_ms, "tp": self.tp, "sl": self.sl,
            "fail_fee": self.fail_fee(), "margin_ms": MARGIN_MS, "whale_sell_ms": WHALE_SELL_MS});
        // dip20: only when a QUIET flag is on (flags off: dip19's record)
        if self.quiet.on() { j["quiet"] = self.quiet.json(); }
        // dip23: only with the v2 log flag
        if self.quiet_v2_log { j["quiet_v2_log"] = true.into(); }
        // dip26: only with the re-arm on (off: dip25's record)
        if self.rearm.on { j["rearm"] = self.rearm.json(); }
        // dip27: only when on (off: dip26's record)
        if self.lone_whale_slots > 0 { j["lone_whale_slots"] = self.lone_whale_slots.into(); }
        if self.ann { j["ann"] = true.into(); }
        // dip31: only when on (off: dip30's record)
        if self.breaker.on() { j["breaker"] = self.breaker.spec().into(); }
        // dip32: only when on (off: dip31's record)
        if let Some((k, h)) = self.cr_unf { j["cr_unfollowed"] = format!("{k}:{}", h / 3_600_000_000_000).into(); }
        if self.cr_loss > 0 { j["cr_loss"] = format!("{}:{}", self.cr_loss_n, self.cr_loss as f64 / 1e9).into(); }
        if let Some(p) = &self.cr_state { j["creator_state"] = p.clone().into(); }
        if self.cr_log { j["cr_log"] = true.into(); }
        if self.f3_log { j["f3_log"] = true.into(); }
        if self.q3a_live { j["quiet3a"] = true.into(); }
        if self.exit_ms > 0 { j["exact_exit"] = self.exact_exit.into(); }
        // dip34: only when on (off: dip33's record)
        if self.cr_earn > 0.0 { j["cr_earn_log"] = self.cr_earn.into(); }
        if self.seen_h > 0.0 { j["seen_log"] = self.seen_h.into(); }
        if self.eqgrp_log { j["eqgrp_log"] = true.into(); }
        if self.q4_log { j["q4_log"] = true.into(); }
        // dip35: only when on (off: dip34's record; the URL never)
        if self.fam_log { j["fam_log"] = serde_json::json!({"thr": self.fam_thr, "rpc": if self.fam_rpc.is_some() { "--presend-live-fam-rpc" } else { "rpc_url" }}); }
        // dip36: only when on (off: dip35's record)
        if let Some(p) = &self.blocklist { j["blocklist"] = serde_json::json!({"path": p, "holder_pct": self.blocklist_pct}); }
        // dip37c: the per-send check (only with the blocklist; dip36's record otherwise)
        if self.blocklist.is_some() { j["blocklist"]["send"] = self.blocklist_send.into(); }
        if self.fpnb_log { j["fpnb_log"] = serde_json::json!({"bots": self.fpnb_bots, "preload": self.fpnb_preload, "thr_t2": arbx::fpnb::THR_T2, "thr_rearm": arbx::fpnb::THR_REARM}); }
        if self.skip2_log { j["skip2_log"] = serde_json::json!({"seed": self.skip2_seed}); }
        if self.fpnb_live != 0 || self.fpnb_control.is_some() { j["fpnb_live"] = serde_json::json!({"mode": pslog36::mode_str(self.fpnb_live), "control": self.fpnb_control}); }
        if !self.tag_wallets.is_empty() { j["tag_wallets"] = self.tag_wallets.iter().map(b58).collect::<Vec<_>>().into(); }
        // dip28: only when on (off: dip27's record)
        if self.deep_drop > 0.0 { j["deep_drop"] = self.deep_drop.into(); j["deep_ob6"] = DEEP_OB6.into(); }
        if let Some(p) = &self.holds_state { j["holds_state"] = p.clone().into(); }
        // dip37: only when on (off: dip36's record)
        if self.wh_on() { j["wh_loss"] = self.wh_spec().into(); if let Some(p) = &self.wh_state { j["whale_state"] = p.clone().into(); } }
        if self.fpnb_stale_hold > 0 { j["fpnb_stale_hold"] = self.fpnb_stale_hold.into(); }
        if self.hl_on() { j["holder_loss"] = format!("{}:{}:{}", self.hl_pct, self.hl_loss as f64 / 1e9, self.hl_win as f64 / 1e9).into(); j["holder_state"] = self.hl_state.clone().into(); j["holder_learn"] = self.hl_learn.into(); }
        if let Some(p) = &self.ledger_ctl { j["ledger_control"] = p.clone().into(); }
        if self.skip2_live != 0 { j["skip2_live"] = pslog36::mode_str(self.skip2_live).into(); }
        if self.m2seen_on() { j["m2seen"] = serde_json::json!({"log": self.m2seen_log, "gate": self.m2seen_gate, "age": psh2::H2_AGE, "m2": psh2::H2_M2}); }
        if self.fab.on { j["fee_ab"] = self.fab.json(self.cu_limit, self.cu_price, self.tip); }
        // dip38: only when on (off: dip37c's record; the URL never)
        if self.blocklist_launcher { j["blocklist"]["launcher"] = true.into(); }
        if self.insider_log { j["insider_log"] = serde_json::json!({"rpc": if self.fund_rpc.is_some() { "--presend-live-fund-rpc" } else { "public" }, "rps": self.fund_rps,
            "fund_state": self.fund_state, "family_state": self.family_state, "pct": pslog38::AB_PCT, "fl": [pslog38::FL_WIN_NS / 3_600_000_000_000, pslog38::FL_LOSS, pslog38::FL_WIN]}); }
        if self.s1_log { j["s1"] = serde_json::json!({"log": true, "live": pslog36::mode_str(self.s1_live), "parts": pss1::parts_str(self.s1_parts), "nd": pss1::S1_ND,
            "age": pss1::S1_AGE, "wh_loss": pss1::S1_WH_LOSS as f64 / 1e9, "cold_nd": pss1::S1_COLD_ND, "spec": "PSM12-S1"}); }
        if self.shape_log { j["shape_log"] = serde_json::json!({"shape_state": self.shape_state, "sh": [pslog38::SH_WIN_NS / 3_600_000_000_000, pslog38::SH_LOSS, pslog38::SH_WIN]}); }
        // dip39: only when on (off: dip38's record)
        match self.bd {
            Some(psbd::Gate::List { min, slots }) => { j["botdepth"] = serde_json::json!({"src": "list", "min": min, "slots": slots, "list": self.bd_list, "mode": psbd::mode_str(self.bd_live)}); }
            Some(psbd::Gate::Org(o)) => { j["botdepth"] = serde_json::json!({"src": "organic", "dmin": o.dmin, "qmin": o.qmin, "trips": o.trips, "hours": o.hours(),
                "state": self.bd_state, "mode": psbd::mode_str(self.bd_live)}); }
            None => {}
        }
        // dip41: only when on (off: dip39's record)
        if self.dl_on {
            j["widedumper"] = serde_json::json!({"ledger": true, "state": self.dl_state, "n": self.wd.n, "score": self.wd.score, "win": self.wd.win, "frac": self.wd.frac,
                "mode": psdl::mode_str(self.wd_live), "size": self.wd_size});
            if let Some(q) = self.qf {
                j["widedumper"]["qf2"] = serde_json::json!({"n": q.n, "score": q.score, "win": q.win, "filters": self.qf_filt.spec(), "mode": psdl::mode_str(self.qf_live)});
            }
        }
        // dip42: only when on (off: dip41's record)
        if let Some(f) = &self.f2 { j["fam2"] = f.json(); }
        if let Some(q) = &self.q1 { j["q1"] = q.json(); }
        // dip43: only when an option is given (off: dip42's record)
        if self.c43.any() { j["dip43"] = self.c43.json(); }
        // dip43 B: only when an item is on (off: dip42's record)
        if self.b43.any_on() { j["b43"] = self.b43.json(); }
        j
    }
}

/// dip26: the re-arm's config for the start-up line's end (none of the words the monitors parse from that line's earlier parts)
fn rearm_desc(cfg: &Cfg) -> String {
    let r = &cfg.rearm;
    format!("REARM ON: after a single sell >= {:.0}% of supply on a followed token <= {} slots old (curve < {} SOL), every other wallet >= {:.0}% at the end of slot dump+{} \
             -> window from then to slot dump+{}+{} (tries as T2, size {:.3} SOL) | ends: the next >= {:.0}% sell / no holder >= {:.0}% left (+{} ms), QUIET {}:{} since the arm, \
             a T2 window takes over | waits while our position / token account is open on the token | R5 skip {}",
        psrearm::RE_BIG as f64 / pl::SUPPLY * 100.0, psrearm::RE_MAX_AGE, psrearm::RE_UNTRADE / 1_000_000_000, psrearm::RE_BIG as f64 / pl::SUPPLY * 100.0, psrearm::RE_WAIT - 1,
        psrearm::RE_WAIT, r.gap, r.spend as f64 / 1e9, psrearm::RE_BIG as f64 / pl::SUPPLY * 100.0, psrearm::RE_BIG as f64 / pl::SUPPLY * 100.0, WHALE_SELL_MS, r.stop.n, r.stop.m,
        if r.r5_skip { "on (all 4 QUIET signals of the largest holder; not during the QUIET warm-up)" } else { "off" })
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

/// an armed window as the sender sees it. dip26: `spend` = what its attempts buy with (the pre-send size; a re-arm window's own size),
/// `rearm` = a re-arm window (its attempt records say so)
#[derive(Clone)]
struct SWin { id: u64, mint: Pk, launch: Launch, st_ns: u64, stop_ns: u64, en_slot: u64, vsol: u64, vtok: u64, fr: f64, pos: (u64, u32, i32), pace: pl::Pace, n: u32, done: bool,
              spend: u64, rearm: bool, ob6: f32, grd: Grd,
              /// dip36 live gate: the window's FP-NOBOT verdict (None: --presend-fpnb-log off)
              fpg: Option<Arc<pslog36::Gate>>,
              /// dip37 the window's fee arm (0 A, 1 B; None: the fee A/B off)
              fab: Option<u8>,
              /// dip37c the window's largest listed holder >= the blocklist threshold now (wallet, %), kept by the main loop; None: none / off
              blk: Option<(Pk, f32)>,
              /// dip39 the window's copy of its mint's listed traders, kept by the main loop (None: the bot depth gate off / no good list)
              bd: Option<psbd::Snap> }

/// dip28: the deeper limit's holder threshold (% of supply)
pub const DEEP_OB6: f32 = 6.0;

/// dip28: an attempt's limit drop: the deeper one while another wallet holds >= DEEP_OB6 % at signing (the window's `ob6`), else the
/// normal one (pure: the sender's)
fn att_drop(w: &SWin, cfg: &Cfg) -> f64 { if cfg.deep_drop > 0.0 && w.ob6 >= DEEP_OB6 { cfg.deep_drop } else { cfg.drop } }

/// dip27 (log-only): the largest holding of `mint` now by a wallet but `whale` and `user` (% of supply); 0 with the annotations off
fn ob6_pct(det: &pl::Detector, on: bool, mint: &Pk, whale: &Pk, user: &Pk) -> f32 {
    if !on { return 0.0; }
    det.max_other(mint, whale, user).map_or(0.0, |b| (b as f64 / pl::SUPPLY * 100.0) as f32)
}

/// dip30 LANDING GUARD (log-only; owner 10-31 ~01:05 PKT "design it, replay it and lets start with logging ... proper at landing"): the
/// on-chain check's account set, chosen at SIGNING: the risky holders (>= 2%, >= 5 holds at risk, hz3 >= 0.3; ours never) of the
/// token, the top GRD_K by holding, with their holdings then. At our landing the check sums their holdings (sold out / closed = 0) and
/// fails the buy at >= GRD_PCT % (replay 20 runs: K 4 = no cap, +4.27 SOL, 15/20 runs). Copy: no allocation on the sender's path
pub const GRD_K: usize = 4;
pub const GRD_PCT: f64 = 6.0;
#[derive(Clone, Copy, Default, Debug)]
pub struct Grd { pub n: u8, pub w: [(Pk, i64); GRD_K] }
fn grd_set(det: &pl::Detector, on: bool, mint: &Pk, user: &Pk, slot: u64) -> Grd {
    let mut g = Grd::default();
    if !on { return g; }
    for h in det.holder_clocks(mint, (0.02 * pl::SUPPLY) as i64, user, slot, 12).into_iter().filter(|h| h.risk >= 5 && h.hz3 >= 0.3).take(GRD_K) {
        g.w[g.n as usize] = (h.w, h.bal); g.n += 1;
    }
    g
}

/// dip27 (log-only): an arm's / a skip's annotation: the token's distinct buyers in the 50 slots up to `slot` (ours never), its
/// creator and the creator's holding now (% of supply)
fn ann_arm(det: &pl::Detector, user: &Pk, mint: &Pk, slot: u64) -> serde_json::Value {
    let nb50 = det.buyers_since(mint, slot.saturating_sub(49), user);
    let (cr, bal) = det.creator_bal(mint).map_or((None, 0), |(c, b)| (Some(b58(&c)), b));
    let pct = bal as f64 / pl::SUPPLY * 100.0;
    // dip34 (coordinator 11-04): cr_hold = the creator's holding now (= cr_pct), cr_big = >= 20% (r50 9rgBypb1: the creator's 33.9%)
    serde_json::json!({"nb50": nb50, "creator": cr, "cr_pct": pct, "cr_hold": pct, "cr_big": pct >= CR_BIG_PCT})
}

/// dip34 (ann): the creator's holding flagged "cr_big" from this % of supply
pub const CR_BIG_PCT: f64 = 20.0;

/// dip28: the hold clocks' state file: {"v": 1, "slot": the save's slot, "w": {wallet: [holds, oldest first]}}. -> wallets loaded
fn holds_load(det: &mut pl::Detector, path: &str) -> Result<usize> {
    let txt = std::fs::read_to_string(path).with_context(|| format!("read {path}"))?;
    let j: serde_json::Value = serde_json::from_str(&txt).with_context(|| format!("parse {path}"))?;
    let last = j["slot"].as_u64().unwrap_or(0);
    let mut n = 0usize;
    for (w, v) in j["w"].as_object().context("no \"w\" object")? {
        let Ok(pk) = bs58::decode(w).into_vec() else { continue };
        let Ok(pk) = <[u8; 32]>::try_from(pk) else { continue };
        let hs: Vec<u32> = v.as_array().map(|a| a.iter().filter_map(|x| x.as_u64()).map(|x| x.min(u32::MAX as u64) as u32).collect()).unwrap_or_default();
        if hs.is_empty() { continue; }
        det.clock_preload(pk, pl::Holds::from_holds(&hs, last));
        n += 1;
    }
    Ok(n)
}

/// dip28: save every hold clock (written to PATH.tmp, then renamed). -> wallets saved
fn holds_save(det: &pl::Detector, path: &str, slot: u64) -> Result<usize> {
    let mut w = serde_json::Map::new();
    for (k, h) in det.clocks_iter() { w.insert(b58(k), h.all().iter().copied().collect::<Vec<u32>>().into()); }
    let n = w.len();
    let tmp = format!("{path}.tmp");
    std::fs::write(&tmp, serde_json::to_vec(&serde_json::json!({"v": 1, "slot": slot, "w": w}))?).with_context(|| format!("write {tmp}"))?;
    std::fs::rename(&tmp, path).with_context(|| format!("rename {tmp}"))?;
    Ok(n)
}

/// dip26: an attempt's min tokens out and limit at its window's latest curve state, for the WINDOW's spend (the sender's; pure).
/// None: untradeable
fn att_limit(w: &SWin, drop: f64) -> Option<(u64, f64, u64)> { pl::limit_min_out(w.vsol, w.vtok, w.spend, w.fr, drop) }

/// dip26: an attempt's instructions (presend_live::attempt_ixs) for the WINDOW's spend (the sender's; pure). dip37: the run's own CU values
/// (the tests' reference; the sender builds with att_ixs_fee)
#[cfg(test)]
fn att_ixs(user: Pk, w: &SWin, min_out: u64, cfg: &Cfg, guard: build::Ix, tip: Option<(Pk, u64)>) -> (Vec<build::Ix>, pl::Roles) {
    att_ixs_fee(user, w, min_out, cfg.cu_limit, cfg.cu_price, guard, tip)
}

/// dip37: the same with THIS attempt's CU limit / price (psfeeab::att_fee: the run's own with the fee A/B off)
#[allow(clippy::too_many_arguments)]
fn att_ixs_fee(user: Pk, w: &SWin, min_out: u64, cu_limit: u32, cu_price: u64, guard: build::Ix, tip: Option<(Pk, u64)>) -> (Vec<build::Ix>, pl::Roles) {
    pl::attempt_ixs(user, &w.launch, w.spend, min_out, cu_limit, cu_price, guard, tip)
}

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
    /// dip31 the circuit breaker: no new buys before this mono ns (0 = never); the recent big losses' times; trips so far
    brk_until: AtomicU64,
    brk_losses: Mutex<VecDeque<u64>>,
    brk_trips: AtomicU64,
    /// dip37c the per-send blocklist: live (true) or log (the control file's "blocklist_send"); its withheld / would-withhold sends [T2, re-arm]
    bl_send_live: AtomicBool, bl_withheld: [AtomicU64; 2], bl_would: [AtomicU64; 2],
    /// dip39 the bot depth gate's mode and counts (psbd.rs; idle without it)
    bd: psbd::BdShared,
    /// dip32 the creator gate's histories (empty without it): filled by the realized task, read at every arm
    cr: Mutex<FxHashMap<Pk, CrHist>>,
    /// dip37 the whale / dumper loss ledger (empty without it): filled by the realized task, read at every arm (pswh.rs)
    wh: Mutex<pswh::WhMaps>,
    /// dip37 the holder ledger (empty without it; pshl.rs)
    hl: Mutex<FxHashMap<Pk, pshl::HlHist>>,
    /// the feed's newest slot (the main loop's)
    slot: AtomicU64,
    seq: AtomicU64,
    sent: AtomicU64,
    dry: AtomicU64,
    /// the sender left its loop (after a stop): nothing more can be sent
    exited: AtomicBool,
    skips: Mutex<FxHashMap<&'static str, u64>>,
    build_us: Mutex<Ring>,
    /// dip43 Builder A's main loop <-> sender state (ps43.rs; idle by default)
    g43: ps43::Sh43,
}

impl Shared {
    fn skip(&self, why: &'static str) { *self.skips.lock().unwrap().entry(why).or_default() += 1; ps43::acct_skip(&self.g43, why); }
    fn cur_slot(&self) -> u64 { self.slot.load(Ordering::Relaxed).max(send::tpu::SLOT.load(Ordering::Relaxed)) }
}

/// one sent (or dry) attempt, as the main loop registers it
#[derive(Clone, Debug)]
pub struct Att {
    pub w: u64, pub n: u32, pub mint: Pk, pub sig: [u8; 64], pub tag: u64, pub path: String, pub client: String, pub slot: u64, pub deadline: u64, pub lim: f64,
    pub min_out: u64, pub p_sign: f64, pub sign_pos: (u64, u32, i32), pub t_send: u64, pub roles: pl::Roles, pub tip: u64, pub wst: &'static str,
    /// dip27 (log-only, --presend-live-ann on; else 0): the window's largest holding of a wallet but its whale and ours at signing (% of supply)
    pub ob6: f32,
    /// dip30 (log-only, --presend-live-ann on; else empty): the landing guard's account set at this attempt's signing
    pub grd: Grd,
    /// dip37 the attempt's fee arm, leader group and signed CU values (None: the fee A/B off)
    pub fa: Option<psfeeab::AttFee>,
    /// dip39 the bot depth gate's verdict at this attempt; None: the gate off
    pub bd: Option<psbd::BdV>,
}

/// what the sender needs
struct SCfg { cfg: Cfg, user: Pk, key: SigningKey, guard: GuardEnc, routes: FxHashMap<String, Vec<RouteP>>, handle: tokio::runtime::Handle,
    /// dip36 FP-NOBOT live gate's mode / counters (None: --presend-fpnb-log off)
    fpg: Option<Arc<pslog36::GateShared>> }

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
    // dip43 B2: the fee tier's per window-slot try counter (unused with the tier off)
    let mut tctr = ps43_b::TierCtr::default();
    let (mut body, mut req) = (Vec::with_capacity(2048), Vec::with_capacity(2400));
    let mut warned: FxHashMap<String, u64> = FxHashMap::default();
    // dip39 the bot depth gate's record limiter (window -> the slot of its last withheld record)
    let mut bd_last: FxHashMap<u64, u64> = FxHashMap::default();
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
            // dip43 A8 (--presend-live-acct on; nothing otherwise): this window's due try (its refusals are charged by Shared::skip)
            ps43::cur_set(&sh.g43, w.id, slot);
            // why not now (each counted); dip26: the same gate for every window (send_gate: unit-tested), at the window's own spend
            if let Some(why) = send_gate(&sh, sc.cfg.one_position, w.spend) { sh.skip(why); continue; }
            // dip36 FP-NOBOT LIVE GATE (--presend-fpnb-live / --presend-fpnb-control; off: never): this slot's verdict blocks -> withheld (one
            // atomic load; no fresh verdict -> fail open)
            let mut leak43: Option<&'static str> = None;
            if let (Some(g), Some(gs)) = (&w.fpg, &sc.fpg) {
                if let Some(stale) = pslog36::gate_withhold_why(g, gs, slot, w.rearm) {
                    sh.skip(if stale { "fpnb_withheld_stale" } else { "fpnb_withheld" });
                    let vs = g.v.load(Ordering::Relaxed) >> 2;
                    let mut r = serde_json::json!({"ev": "presend_live_fpnb_withheld", "w": w.id, "n": w.n, "mint": b58(&w.mint), "slot": slot,
                        "kind": if w.rearm { "rearm" } else { "T2" }, "verdict_slot": vs, "t": arbx::feeds::clock::now_ns()});
                    // dip37 --presend-fpnb-stale-hold: a held send on the window's last (blocking, not fresh) verdict says so
                    if stale { r["stale"] = true.into(); r["age"] = slot.saturating_sub(vs).into(); }
                    let _ = out.send(Out::Rec(r));
                    continue;
                }
                // dip43 A10 (log only; --presend-live-shadows43 on): the FP-NOBOT leak fix's / sticky block's would-hold, kept for the fill record
                leak43 = ps43::leak_why(&sh.g43, g, gs, slot, w.rearm);
                // dip37b SKIP-2 LIVE GATE (--presend-skip2-live / the ledger control file's "skip2"; off: never): the same rule on the skip2 verdict
                if let Some(stale) = pslog36::skip2_withhold_why(g, gs, slot, w.rearm) {
                    sh.skip(if stale { "skip2_withheld_stale" } else { "skip2_withheld" });
                    let vs = g.v2.load(Ordering::Relaxed) >> 2;
                    let mut r = serde_json::json!({"ev": "presend_live_skip2_withheld", "w": w.id, "n": w.n, "mint": b58(&w.mint), "slot": slot,
                        "kind": if w.rearm { "rearm" } else { "T2" }, "verdict_slot": vs, "t": arbx::feeds::clock::now_ns()});
                    if stale { r["stale"] = true.into(); r["age"] = slot.saturating_sub(vs).into(); }
                    let _ = out.send(Out::Rec(r));
                    continue;
                }
            }
            // dip37c PER-SEND BLOCKLIST: a listed wallet holds >= the threshold now (the main loop's cache: no work here) -> withheld (live) or
            // counted (log); the window stays armed (nothing without the blocklist)
            if let Some((bw, bp, live)) = bl_send_check(&sh, &w) {
                let mut r = serde_json::json!({"ev": "presend_live_blocklist_withheld", "w": w.id, "n": w.n, "mint": b58(&w.mint), "slot": slot,
                    "kind": if w.rearm { "rearm" } else { "T2" }, "wallet": b58(&bw), "pct": ((bp as f64) * 1000.0).round() / 1000.0, "t": arbx::feeds::clock::now_ns()});
                if !live { r["log"] = true.into(); }
                let _ = out.send(Out::Rec(r));
                if live { sh.skip("blocklist_withheld"); continue; }
            }
            // dip39 BOT DEPTH: fewer than MIN listed bot wallets traded the mint in the last SLOTS slots (the window's copy, kept by the main
            // loop: a count over <= 16 slots here) -> withheld (live) or counted (log); no good list: fail open (counted). Nothing with it off
            let bdv = sc.cfg.bd.as_ref().map(|g| psbd::check(&sh.bd, g, w.bd.as_ref(), slot, w.rearm));
            if let Some(v) = bdv.filter(|v| v.ok && v.block) {
                let first = psbd::rec_due(&mut bd_last, w.id, slot);
                if first == Some(true) { let c = if v.live { &sh.bd.wins_held } else { &sh.bd.wins_would }; c.fetch_add(1, Ordering::Relaxed); }
                if v.withhold() {
                    sh.skip("botdepth_withheld");
                    if first.is_some() {
                        let mut r = serde_json::json!({"ev": "presend_live_botdepth_withheld", "w": w.id, "n": w.n, "mint": b58(&w.mint), "slot": slot,
                            "kind": if w.rearm { "rearm" } else { "T2" }, "first": first == Some(true), "t": arbx::feeds::clock::now_ns()});
                        match sc.cfg.bd { Some(psbd::Gate::List { min, slots }) => { r["depth"] = v.n.into(); r["min"] = min.into(); r["slots"] = slots.into(); }
                            Some(psbd::Gate::Org(o)) => { r["src"] = "organic".into(); r["dipb"] = v.n.into(); r["qt"] = v.q.into(); r["dmin"] = o.dmin.into(); r["qmin"] = o.qmin.into(); }
                            None => {} }
                        let _ = out.send(Out::Rec(r));
                    }
                    continue;
                }
            }
            let deadline = (slot + sc.cfg.deadline_slots).min(w.en_slot);
            if deadline < slot { sh.skip("window_over"); continue; }
            let (leader, client) = lat::leader_of(slot).unwrap_or_default();
            // dip43 B1: no pre-send try for a listed leader client (empty list: never)
            if sc.cfg.b43.skip_client(&client) { sh.skip("skip_client"); continue; }
            let class = lat::class(&client);
            let rkey = if sc.routes.contains_key(class) { class } else { "default" };
            let Some(rs) = sc.routes.get_mut(rkey) else { sh.skip("no_route"); continue };
            if rs.is_empty() { sh.skip("no_route"); continue; }            // parse_routes refuses empty classes; never a modulo by zero
            let ri0 = (w.n as usize + w.id as usize) % rs.len();
            // dip43 B1: re-route OFF = exactly take_rate on the planned lane (dip42); ON: a lane-refused try takes the class's next lane with room
            let ri = match ps43_b::pick_route(rs.len(), ri0, sc.cfg.b43.reroute, |j| { let r = &mut rs[j]; take_rate(&mut global, &mut r.bucket, now, || r.path.fast_budget()) }) {
                Ok((i, _)) => i, Err(why) => { sh.skip(why); continue; } };
            let path0 = (ri != ri0).then(|| rs[ri0].path.name.clone());
            let r = &mut rs[ri];
            // dip28: the deeper limit while another big holder is in (off: dip27's drop)
            let drop = att_drop(&w, &sc.cfg);
            let Some((min_out, lim, _)) = att_limit(&w, drop) else { sh.skip("untradeable"); continue };
            // dip37: this attempt's CU limit / price / tip: its window's fee arm, the client rule on this attempt's leader (off: the run's own)
            let (cu_limit, cu_price, tip, fa) = psfeeab::att_fee(&sc.cfg, w.fab, &client, r.path.tip(0));
            // dip43 B2: the fee tier (off: the values above unchanged)
            let (cu_price, fa, tier) = ps43_b::tier_apply(&sc.cfg.b43, &mut tctr, w.id, slot, &client, cu_price, fa);
            let (mut ixs, roles) = att_ixs_fee(sc.user, &w, min_out, cu_limit, cu_price, guard_ix_enc(sc.guard, deadline), tip);
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
                sign_pos: w.pos, t_send, roles, tip: tip.map_or(0, |t| t.1), wst: "dry", ob6: w.ob6, grd: w.grd, fa, bd: bdv };
            // registered BEFORE the write: the main loop knows the signature before its landing can arrive
            // dip43 B2: a tiered try's failed fee for the main loop's fallback (nothing with the tier off)
            if tier.is_some_and(|t| t.on) { ps43_b::tier_fee_note(&sig, psfeeab::fail_fee(cu_limit, cu_price)); }
            if !sc.cfg.dry {
                let _ = atx.send(a.clone());
                // dip43 B1 --presend-live-single-token on: the async send takes no second rate token (off: dip42's send_one)
                a.wst = if sc.cfg.b43.single_token { ps43_b::send_one_prepaid(r, &raw, tag, &sc.handle, &mut body, &mut req) } else { send_one(r, &raw, tag, &sc.handle, &mut body, &mut req) };
                sh.sent.fetch_add(1, Ordering::Relaxed);
            } else { sh.dry.fetch_add(1, Ordering::Relaxed); }
            // dip43 (nothing with their flags off): A8 the window's try went out; A10 its would-hold
            ps43::acct_sent(&sh.g43);
            if let Some(why) = leak43 { ps43::leak_note(&sh.g43, &a.sig, why); }
            let t2 = arbx::fast::mono_ns();
            sh.build_us.lock().unwrap().add(((t1 - t0) as f64 / 1e3) as f32);
            let mut rec = serde_json::json!({"ev": "presend_attempt", "w": a.w, "n": a.n, "mint": b58(&a.mint), "sig": bs58::encode(&a.sig).into_string(), "tag": seq,
                "path": a.path, "client": a.client, "leader": leader.chars().take(8).collect::<String>(), "slot": slot, "deadline": deadline, "en_slot": w.en_slot,
                "vsol": w.vsol, "vtok": w.vtok, "p": a.p_sign, "lim": lim, "min_out": min_out, "spend": w.spend, "tip": a.tip, "cu": cu_limit, "cu_price": cu_price,
                "pos": [w.pos.0, w.pos.1, w.pos.2], "t": t_send, "w_status": a.wst, "dry": sc.cfg.dry, "build_us": (t1 - t0) as f64 / 1e3, "write_us": (t2 - t1) as f64 / 1e3,
                "bh_age_ms": bh_age.as_secs_f64() * 1e3, "bytes": raw.len()});
            // dip26: a re-arm window's attempt says so (T2 attempts: dip25's record)
            if w.rearm { rec["kind"] = "rearm".into(); }
            // dip28: the drop used, only with the deeper limit on
            if sc.cfg.deep_drop > 0.0 { rec["drop"] = drop.into(); rec["ob6"] = (w.ob6 as f64).into(); }
            // dip37: only with the fee A/B on
            if let Some(f) = &a.fa { f.put(&mut rec, a.tip); }
            // dip39: the bot depth verdict (only with the gate on; "ok": false = no list, sent)
            if let (Some(v), Some(g)) = (bdv, sc.cfg.bd.as_ref()) { rec["botdepth"] = v.json(g); }
            // dip43 B1 / B2: only when re-routed / with the tier on
            if let Some(p0) = path0 { rec["path_orig"] = p0.into(); }
            if let Some(t) = tier { rec["tier"] = t.json(); }
            let _ = out.send(Out::Rec(rec));
        }
        // idle: 5 ms steps; armed: 0.5 ms (the pace's resolution)
        std::thread::sleep(if any { Duration::from_micros(500) } else { Duration::from_millis(5) });
    }
    sh.exited.store(true, Ordering::SeqCst);
}

/// dip37c the per-send blocklist's check of a due send (the window's cached listed holder; counted): Some((wallet, %, live)) = withhold when
/// live, log only otherwise; None = no listed holder (or the blocklist / its per-send check off)
#[inline]
fn bl_send_check(sh: &Shared, w: &SWin) -> Option<(Pk, f32, bool)> {
    let (bw, bp) = w.blk?;
    let live = sh.bl_send_live.load(Ordering::Relaxed);
    let k = w.rearm as usize;
    if live { sh.bl_withheld[k].fetch_add(1, Ordering::Relaxed); } else { sh.bl_would[k].fetch_add(1, Ordering::Relaxed); }
    Some((bw, bp, live))
}

/// dip31 the circuit breaker's setting (see Cfg::breaker): `n` losses of at least `loss` lamports within `win_ns`, then `pause_ns` without
/// new buys; n = 0: off
#[derive(Clone, Copy, Debug, Default, PartialEq)]
pub struct Breaker { pub n: u32, pub loss: i64, pub win_ns: u64, pub pause_ns: u64 }
impl Breaker {
    pub fn on(&self) -> bool { self.n > 0 }
    /// "N:L:W:P" = losses, SOL, minutes, minutes
    pub fn parse(s: &str) -> Result<Breaker> {
        let v: Vec<&str> = s.split(':').collect();
        let bad = || anyhow::anyhow!("--presend-live-breaker N:L:W:P (losses 1..10, loss SOL in (0, 1], window minutes 1..240, pause minutes 1..1440), e.g. 2:0.2:10:30; got '{s}'");
        if v.len() != 4 { return Err(bad()); }
        let n: u32 = v[0].parse().map_err(|_| bad())?;
        let l: f64 = v[1].parse().map_err(|_| bad())?;
        let (w, p): (u64, u64) = (v[2].parse().map_err(|_| bad())?, v[3].parse().map_err(|_| bad())?);
        if !(1..=10).contains(&n) || !(l > 0.0 && l <= 1.0) || !(1..=240).contains(&w) || !(1..=1440).contains(&p) { return Err(bad()); }
        Ok(Breaker { n, loss: (l * 1e9).round() as i64, win_ns: w * 60_000_000_000, pause_ns: p * 60_000_000_000 })
    }
    pub fn spec(&self) -> String { format!("{}:{}:{}:{}", self.n, self.loss as f64 / 1e9, self.win_ns / 60_000_000_000, self.pause_ns / 60_000_000_000) }
}

/// dip31: no new buys now (the breaker's pause runs)
#[inline]
fn breaker_paused(sh: &Shared) -> bool { arbx::fast::mono_ns() < sh.brk_until.load(Ordering::Relaxed) && !sh.g43.brk_log.load(Ordering::Relaxed) }

/// dip31: a realized P&L (lamports) into the breaker at `now` (mono ns): Some(losses in the window) when it trips now (the pause
/// then runs to now + pause; the window starts empty again)
fn breaker_note(sh: &Shared, b: &Breaker, pnl: i64, now: u64) -> Option<usize> {
    if !b.on() || pnl > -b.loss { return None; }
    let mut q = sh.brk_losses.lock().unwrap();
    q.push_back(now);
    while q.front().is_some_and(|t| now.saturating_sub(*t) > b.win_ns) { q.pop_front(); }
    if q.len() < b.n as usize { return None; }
    let n = q.len();
    q.clear();
    sh.brk_until.fetch_max(now + b.pause_ns, Ordering::SeqCst);
    sh.brk_trips.fetch_add(1, Ordering::SeqCst);
    Some(n)
}

/// dip32 --presend-live-cr-unfollowed K:H -> (K, H in ns): K 1..10 positions, H 1..168 hours
fn cr_unf_parse(s: &str) -> Result<(usize, u64)> {
    let bad = || anyhow::anyhow!("--presend-live-cr-unfollowed K:H (last K positions 1..10 within H hours 1..168), e.g. 3:24; got '{s}'");
    let (k, h) = s.split_once(':').ok_or_else(bad)?;
    let (k, h): (usize, u64) = (k.parse().map_err(|_| bad())?, h.parse().map_err(|_| bad())?);
    if !(1..=10).contains(&k) || !(1..=168).contains(&h) { return Err(bad()); }
    Ok((k, h * 3_600_000_000_000))
}

/// dip32 --presend-live-tag-wallets W,W,... -> the wallets (1..8 base58 keys)
fn tag_parse(s: &str) -> Result<Vec<Pk>> {
    let v: Vec<Pk> = s.split(',').filter(|x| !x.is_empty()).map(|x| bs58::decode(x).into_vec().ok().and_then(|b| <[u8; 32]>::try_from(b).ok())
        .ok_or_else(|| anyhow::anyhow!("--presend-live-tag-wallets: '{x}' is not a wallet"))).collect::<Result<_>>()?;
    if v.is_empty() || v.len() > 8 { bail!("--presend-live-tag-wallets takes 1..8 wallets, comma-separated"); }
    Ok(v)
}

/// dip32 (tag log): the program 41Pr4XqEcmgV1PqZF9yccpuFvxF7PpKLGfTD9jWJBn1q (9pQQ study: trades routed through it draw 9pQQ's buys)
pub const P41: Pk = [44, 172, 228, 135, 168, 166, 182, 194, 127, 108, 185, 187, 34, 123, 88, 184, 191, 180, 103, 124, 128, 239, 230, 73, 232, 186, 96, 78, 16, 4, 16, 196];

/// dip32 (tag log): the listed wallets' history on `mint` (only those that traded it); None when none did
fn tags_json(det: &pl::Detector, mint: &Pk, ws: &[Pk]) -> Option<serde_json::Value> {
    let mut m = serde_json::Map::new();
    for w in ws {
        if let Some((n, bal, fb)) = det.wal_hist(mint, w) {
            if n == 0 { continue; }
            m.insert(b58(w)[..8].to_string(), serde_json::json!({"n": n, "hold": bal > 0, "rt": fb > 0 && bal <= 0}));
        }
    }
    (!m.is_empty()).then_some(serde_json::Value::Object(m))
}

/// dip32 --presend-live-cr-loss N:SOL -> (N, SOL in lamports): N 1..20 positions, SOL in (0, 5]
fn cr_loss_parse(s: &str) -> Result<(u32, i64)> {
    let bad = || anyhow::anyhow!("--presend-live-cr-loss N:SOL (positions 1..20, realized sum SOL in (0, 5]), e.g. 2:0.05; got '{s}'");
    let (n, v) = s.split_once(':').ok_or_else(bad)?;
    let (n, v): (u32, f64) = (n.parse().map_err(|_| bad())?, v.parse().map_err(|_| bad())?);
    if !(1..=20).contains(&n) || !(v > 0.0 && v <= 5.0) { return Err(bad()); }
    Ok((n, (v * 1e9).round() as i64))
}

/// dip34 --presend-live-cr-earn-log K -> K (the paper credit's factor, in (0, 1])
fn cr_earn_parse(s: &str) -> Result<f64> {
    match s.parse::<f64>() {
        Ok(k) if k > 0.0 && k <= 1.0 => Ok(k),
        _ => bail!("--presend-live-cr-earn-log K (the paper credit's factor in (0, 1], e.g. 0.5); got '{s}'"),
    }
}

/// dip34 --presend-live-seen-log [H] -> H hours in (0, 48]; no value (absent, or the next flag) = 3
fn seen_parse(s: Option<&str>) -> Result<f64> {
    match s {
        None => Ok(3.0),
        Some(x) if x.starts_with("--") => Ok(3.0),
        Some(x) => match x.parse::<f64>() {
            Ok(h) if h > 0.0 && h <= 48.0 => Ok(h),
            _ => bail!("--presend-live-seen-log [H] (hours in (0, 48], default 3); got '{x}'"),
        },
    }
}

/// dip32: the most positions a creator's history keeps (the K of the unfollowed rule is <= 10); the realized sum counts them all
pub const CR_KEEP: usize = 10;
/// dip32: the creator state's save period (slots, ~10 min)
pub const CR_SAVE_SLOTS: u64 = 1500;

/// dip32: one creator's history: the realized sum and count over ALL our positions on its tokens, and the last CR_KEEP of them as
/// (known at: epoch ns, realized lamports, followed). dip34 (--presend-live-cr-earn-log): `ps` / `pn` = the PAPER credits of its
/// cr_loss-skipped windows (lamports, count; 0 without the flag; never part of `sum` / `n`)
#[derive(Clone, Debug, Default, PartialEq)]
pub struct CrHist { pub sum: i64, pub n: u32, pub h: VecDeque<(u64, i64, bool)>, pub ps: i64, pub pn: u32 }
impl CrHist {
    /// dip34 the earn-back rule (log-only): would the loss ledger with the paper credits counted still block? -> trade = !block
    pub fn earn_trade(&self, n_min: u32, loss: i64) -> bool { !(self.n >= n_min && self.sum + self.ps <= -loss) }
    pub fn add(&mut self, t: u64, pnl: i64, followed: bool) {
        self.sum += pnl;
        self.n += 1;
        self.h.push_back((t, pnl, followed));
        while self.h.len() > CR_KEEP { self.h.pop_front(); }
    }
    /// QUIET3-B: the last <= k positions known before `t0` and not older than `h_ns` were ALL not followed (none: false)
    pub fn unfollowed(&self, t0: u64, k: usize, h_ns: u64) -> bool {
        let mut v: Vec<&(u64, i64, bool)> = self.h.iter().filter(|e| e.0 < t0 && e.0.saturating_add(h_ns) >= t0).collect();
        v.sort_by_key(|e| e.0);
        let last = &v[v.len().saturating_sub(k)..];
        !last.is_empty() && last.iter().all(|e| !e.2)
    }
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"n": self.n, "sum": self.sum as f64 / 1e9, "last": self.h.iter().rev().take(3).map(|e| serde_json::json!([e.1 as f64 / 1e9, e.2])).collect::<Vec<_>>()})
    }
}

/// dip32: the creator gate at an arm (T2: `t0` = the trigger's arrival; re-arm: the check's): Some(the skip: "loss" / "unfollowed")
/// and the creator's history for the records (None: no creator / no history)
fn cr_gate(sh: &Shared, cfg: &Cfg, creator: Option<Pk>, t0: u64) -> (Option<&'static str>, Option<serde_json::Value>) {
    let Some(c) = creator else { return (None, None) };
    let g = sh.cr.lock().unwrap();
    let Some(h) = g.get(&c) else { return (None, None) };
    let why = if cfg.cr_loss > 0 && h.n >= cfg.cr_loss_n && h.sum <= -cfg.cr_loss { Some("loss") }
        else if cfg.cr_unf.is_some_and(|(k, hn)| h.unfollowed(t0, k, hn)) { Some("unfollowed") } else { None };
    // QUIET3-B as a log-only verdict (the last <= 3 in 24 h all not followed), whether or not its live flag is on
    let mut j = h.json();
    j["unf3"] = h.unfollowed(t0, 3, 24 * 3_600_000_000_000).into();
    // dip34 CR-EARNBACK (log-only): the paper credits and the earn-back rule's verdict (the decision above is unchanged)
    if cfg.cr_earn > 0.0 { j["earn"] = serde_json::json!({"ps": h.ps as f64 / 1e9, "pn": h.pn, "trade": h.earn_trade(cfg.cr_loss_n, cfg.cr_loss)}); }
    // dip35 --presend-live-cr-log: the verdict only on the records (cr.would), never a skip
    if cfg.cr_log { if let Some(w) = why { j["would"] = w.into(); } return (None, Some(j)); }
    (why, Some(j))
}

/// dip32: was our position FOLLOWED: a buy on the token's tape by a wallet that is not us, not the trigger whale / re-arm dumper, not
/// one of `excl` (the re-arm's holders) after our first buy (slot, idx) and at or before our last sell landing (slot, idx)
fn followed(tape: &VecDeque<pl::Trade>, user: &Pk, whale: Option<&Pk>, excl: &[Pk], first: (u64, u64), last: (u64, u64)) -> bool {
    tape.iter().any(|t| t.buy && t.user != *user && whale != Some(&t.user) && !excl.contains(&t.user)
        && (t.s, t.i as u64) > first && (t.s, t.i as u64) <= last)
}

/// dip32: the creator state file: {"v": 1, "c": {creator: {"sum": lamports, "n": positions, "h": [[known ns, lamports, followed]]}}}
/// (dip34: optional "ps": paper lamports, "pn": paper credits per creator; files without them load as 0)
fn cr_load(path: &str) -> Result<FxHashMap<Pk, CrHist>> {
    let txt = std::fs::read_to_string(path).with_context(|| format!("read {path}"))?;
    let j: serde_json::Value = serde_json::from_str(&txt).with_context(|| format!("parse {path}"))?;
    let mut m = FxHashMap::default();
    for (c, v) in j["c"].as_object().context("no \"c\" object")? {
        let Ok(pk) = bs58::decode(c).into_vec() else { continue };
        let Ok(pk) = <[u8; 32]>::try_from(pk) else { continue };
        // dip34: ps / pn optional (dip32/33 files have none: 0)
        let mut h = CrHist { sum: v["sum"].as_i64().unwrap_or(0), n: v["n"].as_u64().unwrap_or(0) as u32, h: VecDeque::new(),
            ps: v["ps"].as_i64().unwrap_or(0), pn: v["pn"].as_u64().unwrap_or(0) as u32 };
        for e in v["h"].as_array().into_iter().flatten() {
            if let (Some(t), Some(p), Some(f)) = (e[0].as_u64(), e[1].as_i64(), e[2].as_bool()) { h.h.push_back((t, p, f)); }
        }
        while h.h.len() > CR_KEEP { h.h.pop_front(); }
        m.insert(pk, h);
    }
    Ok(m)
}

/// dip32: save the creator histories (PATH.tmp, then renamed). -> creators saved. dip34: + "ps" / "pn" when a creator has paper credits
fn cr_save(m: &FxHashMap<Pk, CrHist>, path: &str) -> Result<usize> {
    let c: serde_json::Map<String, serde_json::Value> = m.iter().map(|(k, h)| {
        let mut j = serde_json::json!({"sum": h.sum, "n": h.n, "h": h.h.iter().map(|e| serde_json::json!([e.0, e.1, e.2])).collect::<Vec<_>>()});
        // dip34: the paper credits only when there are some (else dip32's entry, byte for byte)
        if h.pn > 0 { j["ps"] = h.ps.into(); j["pn"] = h.pn.into(); }
        (b58(k), j)
    }).collect();
    let tmp = format!("{path}.tmp");
    std::fs::write(&tmp, serde_json::json!({"v": 1, "c": c}).to_string()).with_context(|| format!("write {tmp}"))?;
    std::fs::rename(&tmp, path).with_context(|| format!("rename {tmp}"))?;
    Ok(m.len())
}

/// dip34 CR-EARNBACK (log-only): a cr_loss-skipped trigger is remembered this long (ns) for the shadow's arm; at most CE_MAX of
/// each map (a full map takes nothing new: counted in `full`)
pub const CE_KEEP_NS: u64 = 600_000_000_000;
pub const CE_MAX: usize = 4096;

/// dip34 CR-EARNBACK (--presend-live-cr-earn-log K, log-only): the T2 triggers skipped "cr_loss" (signature -> creator, mint, skip
/// time ns) and the shadow windows armed on them (window id -> signature, row c sol_in once filled); credits written / their lamports
#[derive(Default, Debug)]
pub struct CrEarn {
    skipped: FxHashMap<String, (Pk, Pk, u64)>,
    w: FxHashMap<u64, (String, Option<f64>)>,
    credits: u64,
    credit_sum: i64,
    full: u64,
}

/// dip32 (--presend-live-f3-log) QUIET3-A's thresholds (log-only): the 120 s ring's trades and the whale's dumps
pub const F3_N120: u64 = 15;
pub const F3_WHD: u64 = 3;

/// dip32 (--presend-live-f3-log): the fresh holders of a token at `slot`: holders >= 2% (not us, not `not`: the whale / dumper) with
/// <= 1 hold on record, summed (% of supply) and counted (TAIL G3 fires at >= 35%)
fn f3_fresh(det: &pl::Detector, mint: &Pk, user: &Pk, not: &Pk, slot: u64) -> (f64, usize) {
    let v: Vec<_> = det.holder_clocks(mint, (0.02 * pl::SUPPLY) as i64, user, slot, 16).into_iter().filter(|h| h.w != *not && h.n <= 1).collect();
    (v.iter().map(|h| h.bal as f64 / pl::SUPPLY * 100.0).sum(), v.len())
}

/// why the sender sends no attempt of a window now (None: it may). Every window the same (T2 and dip26 re-arm windows): the stop (caps,
/// run end) or no new buys (kill switch, profit lock: DIP_NO_FIRE), the one-position pause (a reactive / pre-send position open), the
/// rolling 24 h fee budget's pause (dip24), the blockhash / balance-read pause, a balance below the window's spend (dip26: its own
/// spend: a re-arm window's size) + 0.03 SOL + what is reserved. The sender's own order (dip25's code, moved here unchanged)
#[inline]
fn send_gate(sh: &Shared, one_position: bool, spend: u64) -> Option<&'static str> {
    if sh.stop.load(Ordering::Relaxed) || DIP_NO_FIRE.load(Ordering::Relaxed) { Some("stopped") }
    else if one_position && sh.pause_reactive.load(Ordering::Relaxed) { Some("paused_reactive_position") }
    else if one_position && sh.pause_pos.load(Ordering::Relaxed) { Some("paused_presend_position") }
    // dip24: the rolling 24 h fee budget is spent (resumes when it rolls back under)
    else if sh.pause_fee.load(Ordering::Relaxed) { Some("paused_fee_budget") }
    // dip31: the circuit breaker's pause (0 = never set)
    else if breaker_paused(sh) { Some("paused_breaker") }
    // dip43 A1: the executed feed is blind (only with --presend-live-stall-mode live / the control file's "stall": "live")
    else if sh.g43.pause_stall.load(Ordering::Relaxed) { Some("paused_stall") }
    else if fires_paused() { Some("paused_blockhash_or_balance_read") }
    else {
        let bal = ACCT.bal.load(Ordering::SeqCst);
        if bal > 0 && bal < spend + 30_000_000 + ACCT.reserved.load(Ordering::SeqCst) { Some("paused_balance") } else { None }
    }
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
    /// dip29 (the deeper limit on): (largest other holder seen %, highest price seen, deepest drop from it) since the arm
    dl: Option<(f32, f64, f64)>,
    /// dip32: the re-arm's holders at the check (a T2 window: none): never counted as followers of our position
    excl: Vec<Pk>,
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
    /// dip26: opened by a re-arm window's fill (its records carry "kind":"rearm", its lines " [rearm]")
    rearm: bool,
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
    /// dip35 (log-only): a fam holders read answered
    Fam(Box<FamRes>),
    /// dip38 (log-only): the funding resolver's answer
    Fund(Box<psfund::FundOut>),
    /// dip43 A2: a blind try's status read answered
    Status(Box<ps43::StatusRes>),
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
    Sell { mint: Pk, pid: u64, round: u32, launch: Launch, derived: bool, known: Option<u64>, guess: u64, land_slot: u64, read_first: bool, keep_ata: bool,
        /// dip43 B3 / B4: a lot's part / an exit's own CU price (None: dip42's sell)
        x43: Option<SellX> },
    /// a CONFIRMED read of our token account of `mint` from a node at slot >= `min_slot`; `n` = reads of it so far
    Read { mint: Pk, min_slot: u64, why: Why, n: u32 },
    /// close our (confirmed empty) token account of `mint`: the rent back
    Close { mint: Pk },
    /// a position's realized P&L from its transactions: every buy (sig, cost estimate when not found) and every sell
    /// (dip26 `rearm`: a re-arm position's: its record and line say so, its P&L goes to the re-arm side of the split)
    /// dip32 `cr`: (the token's creator, followed) when the creator gate is on
    Realized { pid: u64, w: u64, mint: Pk, buys: Vec<(String, u64)>, sells: Vec<(String, bool, u64)>, rearm: bool, cr: Option<(Pk, bool)>,
        /// dip37: the position's fee arm / group / values (None: the fee A/B off)
        ab: Option<psfeeab::RzAb>,
        /// dip37: the position's window's whale / dumper and its kind (re-arm) for the loss ledger (None: the ledger off or unknown)
        wh: Option<(Pk, bool)>,
        /// dip37: the position's holder keys for the holder ledger (empty: off)
        hl: Vec<Pk>,
        /// dip38 (log-only): the position's anti-bait view (the family / shape ledgers learn its P&L; None: the logs off)
        l38: Option<Box<pslog38::Rz38>>,
        /// dip38 (log-only): the window's PSM12-S1 verdict ({keep, why, ...}) for the realized record (None: the log off / unknown)
        s1: Option<serde_json::Value>,
        /// dip41: a WIDE-DUMPER / QF2 window's position: (kind, field, the whale's ledger values) for the realized record (None: neither)
        wd: Option<(&'static str, &'static str, serde_json::Value)>,
        /// dip42 (log-only): the position's fill "fam2" object for the realized record (None: the flag off / no fill kept)
        f2: Option<serde_json::Value> },
    /// the background UNSOLD retry of a position (its sells keep the account open; PsMsg::UnsoldDone at its end)
    Unsold { mint: Pk, launch: Launch, land_slot: u64, last_qty: (u64, bool) },
    /// a Telegram alert (the tests keep its title; a run raises it at once, never through this)
    #[allow(dead_code)]
    Alert { level: arbx::alerts::Level, title: String },
    /// dip35 (log-only): a fam holders read (the answer: PsMsg::Fam; not a task the run's end waits for)
    Fam(Box<FamReq>),
    /// dip43 A2 (--presend-live-deadman live): a blind try's getSignatureStatuses + our token account at processed (the answer: PsMsg::Status)
    Status(Box<ps43::StatusReq>),
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
    time_exit_due_w(slot_now, land_slot, exit_slots, held_ms, exit_ms, exit_slots * 400 + 3_000)
}

/// dip43 A2: the same with the wall-clock backstop given (ms; dip42's exit_slots x 400 + 3000 unless --presend-live-deadman live)
pub fn time_exit_due_w(slot_now: u64, land_slot: u64, exit_slots: u64, held_ms: u64, exit_ms: u64, wall_ms: u64) -> Option<&'static str> {
    if exit_ms > 0 && held_ms >= exit_ms { return Some("time-ms"); }
    if slot_now >= land_slot + exit_slots { return Some("time-limit"); }
    if held_ms > wall_ms { return Some("time-limit-wall"); }
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

/// dip19 (fix 3): a position's realized record and log line from its buys' and sells' tx answers (pure: unit-tested; dip26 moved it out
/// of the realized task unchanged). dip26 `rearm`: the record gets "kind":"rearm", the line ends with " [rearm]" (its prefix unchanged)
#[allow(clippy::too_many_arguments)]
pub fn realized_out(w: u64, pid: u64, mint: &Pk, pnl: i64, buys: &[(String, u64)], bs: &[(Option<(i64, u64, bool)>, u64)], nb: usize, ns: usize, n_sells: usize, rearm: bool)
    -> (serde_json::Value, String) {
    let src = if nb == buys.len() { "tx" } else if nb > 0 || ns > 0 { "tx+estimate" } else { "estimate" };
    let found: Vec<(i64, u64)> = bs.iter().filter_map(|(b, _)| b.map(|x| (x.0, x.1))).collect();
    let mut rec = serde_json::json!({"ev": "presend_live_realized", "w": w, "pid": pid, "mint": b58(mint), "pnl": pnl, "src": src,
        "buy_delta": (!found.is_empty()).then(|| found.iter().map(|x| x.0).sum::<i64>()), "buy_fee": (!found.is_empty()).then(|| found.iter().map(|x| x.1).sum::<u64>()),
        "buys": buys.iter().zip(bs).map(|((s, c), (b, _))| serde_json::json!({"sig": s, "delta": b.map(|x| x.0), "fee": b.map(|x| x.1), "found": b.is_some(), "cost_est": c})).collect::<Vec<_>>(),
        "buys_found": nb, "sells_found": ns, "sells": n_sells});
    if rearm { rec["kind"] = "rearm".into(); }
    let line = format!("  PRESEND LIVE REALIZED {} {:+.6} SOL ({src}: {nb}/{} buy tx(s), {ns}/{} sell tx(s)){}", b58(mint), pnl as f64 / 1e9, buys.len(), n_sells,
        if rearm { " [rearm]" } else { "" });
    (rec, line)
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
    /// dip27 (--presend-live-ann on): fills the deeper-limit lead would have skipped (log-only)
    ann_ctx85: u64,
    /// dip28 (--presend-live-ann on): fills the safe sell-timer check would have blocked (log-only)
    ann_st: u64,
    /// dip30: fills the GROUP RISK rule (log-only) would have blocked
    ann_grp: u64,
    /// dip30: fills the LANDING GUARD (log-only) would have failed
    ann_guard: u64,
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
    /// dip32: the slot of the creator state's last save
    cr_saved: u64,
    /// dip32 (f3 log): the tx being ingested ran program 41Pr4XqE (set per executed tx, read by the T2 trigger's records)
    cur_r41: bool,
    /// dip34 CR-EARNBACK (log-only, --presend-live-cr-earn-log): the cr_loss-skipped T2 triggers waiting for the shadow's row c
    ce: CrEarn,
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
    /// dip26 LIVE RE-ARM (None: --presend-live-rearm off, nothing of it runs)
    rm: Option<psrearm::Rearm>,
    /// dip34 LOG-ONLY annotations' state (pslog34.rs; empty with their flags off)
    l34: L34,
    /// dip35 LOG-ONLY fam reads' state (pslog35.rs; no client with the flag off)
    l35: L35,
    /// dip36 LOG-ONLY FP-NOBOT (pslog36.rs; None with the flag off: nothing sent, no thread)
    fp: Option<pslog36::Fp>,
    /// dip36 LIVE blocklist (psblock.rs; None without --presend-live-blocklist)
    bl: Option<psblock::Blocklist>,
    /// dip37 FEE A/B's counters (psfeeab.rs; None with it off: nothing of it runs)
    fab: Option<psfeeab::FabSt>,
    /// dip37 the whale / dumper ledger's window wallets, save slot, skips (pswh.rs; empty with it off)
    whs: pswh::WhSt,
    /// dip37 HYBRID-2's per-mint scored-dump counter (None with its flags off)
    h2: Option<psh2::H2>,
    /// dip37 the holder ledger's window keys / counters and the ledgers' control file (pshl.rs)
    hls: pshl::HlSt,
    /// dip38 the launchers, chains, windows, ledgers of the anti-bait log (pslog38.rs; empty and idle with its flags off)
    l38: pslog38::L38,
    /// dip38 PSM12-S1's live mode, armed windows' verdicts, counts (pss1.rs; idle with its log off)
    s1: pss1::S1St,
    /// dip39 the bot depth gate's list and book (psbd.rs; None with it off)
    bd: Option<psbd::Bd>,
    /// dip41 the dumper ledger + the WIDE-DUMPER tier (None = off, the default; psdl.rs)
    wd: Option<psdl::Wd>,
    /// dip42 FAM2 (LOG ONLY): the family's trades per mint (None = off, the default; psfam2.rs)
    f2: Option<psfam2::Fam2>,
    /// dip42 Q1 (LOG ONLY): the handle of its thread (None = off, the default; psq1.rs)
    q1: Option<psq1::Q1Tap>,
    /// dip43 Builder A's state (ps43.rs; idle by default)
    d43: ps43::D43,
    /// dip43 B: the lots exits under way, the lots mode, counters (empty with its flags off)
    b43: ps43_b::B43St,
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
        // dip37: arm B's tip override is held to every attempt path's minimum tip as A's (nothing with the A/B off or no B tip)
        if cfg.fab.on && cfg.fab.tip.is_some() { parse_routes(&cfg.routes, paths, &reactive, cfg.fab.tip).context("--presend-live-ab-tip-lamports")?; }
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
        // dip36 (log-only): the FP-NOBOT thread (refused here, before the sender starts, when its bot list is bad; None with the flag off)
        let fp = pslog36::Fp::start(&cfg, user, &out, false)?;
        // dip36 LIVE blocklist (a bad / missing file refuses the start; None without the flag)
        let bl = cfg.blocklist.as_deref().map(psblock::Blocklist::load).transpose()?;
        if let Some(b) = &bl {
            eprintln!("DIP PRESEND LIVE BLOCKLIST (dip36, LIVE): {} wallets from {} (version {}); an arm is skipped when the T2 whale / re-arm dumper / a holder >= {}% is listed; re-read on change",
                b.set.len(), b.path, b.ver, cfg.blocklist_pct);
        }
        let (atx, arx) = crossbeam_channel::unbounded::<Att>();
        let sh = Arc::new(Shared { wins: Mutex::new(Vec::new()), stop: AtomicBool::new(false), pause_reactive: AtomicBool::new(false), pause_pos: AtomicBool::new(false), pause_fee: AtomicBool::new(false),
            brk_until: AtomicU64::new(0), brk_losses: Mutex::new(VecDeque::new()), brk_trips: AtomicU64::new(0), bl_send_live: AtomicBool::new(true), bl_withheld: Default::default(), bl_would: Default::default(), bd: Default::default(), cr: Mutex::new(FxHashMap::default()), wh: Mutex::new(Default::default()), hl: Mutex::new(FxHashMap::default()),
            slot: AtomicU64::new(0), seq: AtomicU64::new(0), sent: AtomicU64::new(0), dry: AtomicU64::new(0), exited: AtomicBool::new(false), skips: Mutex::new(FxHashMap::default()), build_us: Mutex::new(Ring::default()), g43: Default::default() });
        // dip39 BOT DEPTH: the start mode and the list (a bad / missing list: FAIL OPEN, a warning; None with it off)
        sh.bd.live.store(cfg.bd_live, Ordering::SeqCst);
        let bd = cfg.bd.map(|g| psbd::Bd::open(g, cfg.bd_list.as_deref(), cfg.bd_state.as_deref(), &user));
        if let Some(b) = &bd {
            let src = match (&b.gate, &b.org) {
                (psbd::Gate::List { .. }, _) => format!("list {}: {}", b.path, match &b.err { None => format!("{} wallets (re-read on change)", b.n_list()),
                    Some(e) => format!("NOT LOADED ({e}): FAIL OPEN, nothing withheld until a good list is read") }),
                (_, _) => format!("organic warm-up: FAIL OPEN until the quick-trip history covers the hours | state {}", match (&cfg.bd_state, &b.err) {
                    (None, _) => "none".to_string(), (Some(p), None) => format!("{p} (used if saved <= 30 min before the first trade)"), (Some(p), Some(e)) => format!("{p} NOT read: {e}") }),
            };
            eprintln!("DIP PRESEND LIVE BOT DEPTH (dip39, {}): a pre-send attempt (T2 + re-arm) failing {} is {} | {src} | the control file's \"botdepth\": live|log flips it",
                if cfg.bd_live { "LIVE" } else { "LOG ONLY" }, b.gate.desc(), if cfg.bd_live { "WITHHELD (the window stays armed)" } else { "logged (never withheld)" });
        }
        // dip41 the dumper ledger + the WIDE-DUMPER tier (its state preloaded; None with it off)
        let wd = cfg.dl_on.then(|| psdl::Wd::open(cfg.wd, cfg.wd_live, cfg.qf, cfg.qf_filt, cfg.qf_live, cfg.wd_size, cfg.dl_state.as_deref()));
        if let Some(w) = &wd {
            eprintln!("DIP PRESEND LIVE WIDE DUMPER (dip41, {}): fast-dump ledger of every >= 3% buy (dumped = >= 30% sold within {} slots, counted after {} slots, last {} per wallet) | \
                a whale's first crossing into [3%, {}%) at age >= {} slot(s) whose whale has >= {} resolved buys and >= {:.0}% dumped, one window per token: {} | size {:.3} SOL | state {} | the control file's \"widedumper\": live|log flips it",
                if cfg.wd_live { "LIVE" } else { "LOG ONLY" }, cfg.wd.win, psdl::DL_RESOLVE_SLOTS, psdl::DL_KEEP, cfg.whale_pct, cfg.min_age_slots.max(1), cfg.wd.n, cfg.wd.score * 100.0,
                if cfg.wd_live { "a T2-path window (every live filter, kind \"wide\")" } else { "logged (presend_live_widedumper), nothing sent" }, cfg.wd_size as f64 / 1e9,
                match (&cfg.dl_state, &w.err, w.loaded) { (None, _, _) => "none (empty ledger)".to_string(), (Some(p), Some(e), _) => format!("{p} NOT read ({e}): EMPTY ledger"),
                    (Some(p), None, Some(0)) => format!("{p} (not there yet: empty ledger)"), (Some(p), None, n) => format!("{p}: {} wallets preloaded", n.unwrap_or(0)) });
            if let Some(q) = cfg.qf {
                eprintln!("DIP PRESEND LIVE QF2 (dip41, {}): a whale's first >= 3% crossing whose whale has >= {} resolved >= 3% buys and sold within {} slots on >= {:.0}% of them, \
                    filters {} (SOL in, curve vSOL after, age slots): 3..{}% -> {} ; >= {}% (T2) -> annotated only | the control file's \"qf2\": live|log flips it",
                    if cfg.qf_live { "LIVE" } else { "LOG ONLY" }, q.n, q.win, q.score * 100.0, cfg.qf_filt.spec(), cfg.whale_pct,
                    if cfg.qf_live { "a T2-path window (kind \"qf2\")" } else { "logged (presend_live_qf2), nothing sent" }, cfg.whale_pct);
            }
        }
        // dip42 FAM2 + Q1 (both LOG ONLY; None with them off): FAM2's book; Q1's own thread (its lists read, its start record)
        let f2 = cfg.f2.clone().map(psfam2::Fam2::new);
        if let Some(f) = &f2 {
            eprintln!("DIP PRESEND LIVE FAM2 (dip42, LOG ONLY): \"fam2\" on every arm / skip / fill / realized record = the 2NUM family's wallets ({}) that traded the token in the last {} slots; nothing is withheld",
                f.cfg.wallets.iter().map(|w| b58(w)[..8].to_string()).collect::<Vec<_>>().join(", "), f.cfg.slots);
        }
        let q1 = cfg.q1.clone().map(|c| psq1::Q1Tap::start(c, user, &out, false));
        arbx::feeds::own_fail_watch(user);
        // dip32: the creator histories' preload (the offline seed / the last run's state)
        if let Some(p) = &cfg.cr_state {
            match cr_load(p) {
                Ok(m) => { eprintln!("DIP PRESEND LIVE CREATOR GATE: preloaded {} creators from {p} (saved back every ~10 min and at the run's end)", m.len()); *sh.cr.lock().unwrap() = m; }
                Err(e) => eprintln!("DIP PRESEND LIVE CREATOR GATE: no preload from {p} ({e:#}); the histories start empty"),
            }
        }
        // dip37: the whale / dumper ledger (LIVE) and its preload (a missing file: an empty ledger)
        if cfg.wh_on() {
            let n = match &cfg.wh_state {
                Some(p) if std::path::Path::new(p).exists() => {
                    let m = pswh::wh_load(p)?;
                    let s = format!("{} wallets preloaded from {p} (T2 {}, re-arm {}){}", m.all.len(), m.t2.len(), m.re.len(),
                        if cfg.wh_split && m.t2.is_empty() && m.re.is_empty() { ": NOTE the file has no split ledgers: with --presend-live-wh-split on they start EMPTY" } else { "" });
                    *sh.wh.lock().unwrap() = m;
                    s
                }
                Some(p) => format!("NOTE: {p} does not exist: the ledger starts EMPTY (saved there every ~10 min and at the run's end)"),
                None => "no state file: the ledger starts empty and is not saved".to_string(),
            };
            eprintln!("DIP PRESEND LIVE WHALE LEDGER (dip37, LIVE): skip an arm whose T2 whale / re-arm dumper has rule {} with us | {n}", cfg.wh_spec());
        }
        // dip37: the holder ledger (LIVE) and its preload (a missing file: an empty ledger)
        if cfg.hl_on() {
            let n = match &cfg.hl_state {
                Some(p) if std::path::Path::new(p).exists() => { let m = pshl::hl_load(p)?; let s = format!("{} wallets preloaded from {p}", m.len()); *sh.hl.lock().unwrap() = m; s }
                Some(p) => format!("NOTE: {p} does not exist: the ledger starts EMPTY (saved there every ~10 min and at the run's end)"),
                None => "no state file: the ledger starts empty and is not saved".to_string(),
            };
            eprintln!("DIP PRESEND LIVE HOLDER LEDGER (dip37, LIVE): skip an arm with a holder >= {}% whose positions with us sum <= -{} SOL and never won >= {} SOL{} | {n}",
                cfg.hl_pct, cfg.hl_loss as f64 / 1e9, cfg.hl_win as f64 / 1e9, if cfg.hl_learn { " | learns from the shadow's paper on its T2 skips" } else { "" });
        }
        let sc = SCfg { cfg: cfg.clone(), user, key: (*key).clone(), guard, routes, handle: tokio::runtime::Handle::current(), fpg: fp.as_ref().map(|f| f.gs.clone()) };
        let fee1 = cfg.fail_fee();
        let line = format!("DIP PRESEND LIVE{} | T2 whale >= {}% -> window {} slots from +{} ms (create-slot triggers {}) | {} attempts per slot ({:.0} ms apart), {:.3} SOL, limit = latest price x {:.2}, \
            deadline slot + {} | CU {} x {} uL (a failed attempt {} lamports) | routes {} | caps: {} fills, fees {:.4} SOL per rolling 24 h (pause), {} attempts/s ({} per path) | one position {} | exit {} slots{} / TP +{:.0}% / SL -{:.0}% | min token age {}",
            if cfg.dry { " DRY (builds + signs + logs; NEVER sends)" } else { " (REAL attempts)" }, cfg.whale_pct, cfg.window_slots, cfg.live_ms, if cfg.create_slot { "on" } else { "skipped" },
            cfg.k, slot_ns as f64 / 1e6 / cfg.k as f64, cfg.spend as f64 / 1e9, 1.0 - cfg.drop, cfg.deadline_slots, cfg.cu_limit, cfg.cu_price, fee1, desc.join(";"), if cfg.max_fills == 0 { "unlimited".to_string() } else { cfg.max_fills.to_string() },
            cfg.fee_budget as f64 / 1e9, cfg.max_per_sec, cfg.path_max_per_sec, if cfg.one_position { "on" } else { "off" }, cfg.exit_slots,
            if cfg.exit_ms > 0 { format!(" or {} ms after the fill (dip22, first)", cfg.exit_ms) } else { String::new() }, cfg.tp * 100.0, cfg.sl * 100.0,
            if cfg.min_age_slots == 0 { "off".to_string() } else { format!("{} slots (younger skipped)", cfg.min_age_slots) });
        // dip26: the re-arm's config at the END of the start-up line, only when on (the monitors read the line's earlier parts; a line of its
        // own starting "DIP PRESEND LIVE" would replace dipmon's parse of this one)
        let line = if cfg.rearm.on { format!("{line} | {}", rearm_desc(&cfg)) } else { line };
        // dip27: also at the END, only when on
        let line = if cfg.lone_whale_slots > 0 { format!("{line} | LONE WHALE SKIP ON: a trigger whose whale is the only buyer in the last {} slots is skipped (after QUIET)", cfg.lone_whale_slots) } else { line };
        let line = if cfg.ann { format!("{line} | ANN ON (log-only): buyers/creator at arm, other holder at signing, ctx85 + holder clocks at fills") } else { line };
        // dip28: also at the END, only when on
        let line = if cfg.cr_on() { format!("{line} | CREATOR GATE {}:{}{}", if cfg.cr_log { "LOG ONLY (verdict as cr.would on the records, never a skip)" } else { "ON" }, cfg.cr_unf.map(|(k, h)| format!(" skip when the creator's last {k} positions in {} h were all not followed;", h / 3_600_000_000_000)).unwrap_or_default(),
            if cfg.cr_loss > 0 { format!(" skip when >= {} of our positions on its tokens realized <= -{} SOL", cfg.cr_loss_n, cfg.cr_loss as f64 / 1e9) } else { String::new() }) } else { line };
        let line = if cfg.f3_log { format!("{line} | F3 LOG (QUIET3-A, fresh holders) ON") } else { line };
        // dip34: the log-only annotations, only when on
        let l34d: Vec<String> = [(cfg.seen_h > 0.0).then(|| format!("seen whale {} h", cfg.seen_h)), cfg.eqgrp_log.then(|| "equal-size groups".to_string()),
            cfg.q4_log.then(|| "QUIET4 fields".to_string())].into_iter().flatten().collect();
        let line = if l34d.is_empty() { line } else { format!("{line} | DIP34 LOG ({})", l34d.join(", ")) };
        // dip35: only when on
        let line = if cfg.fam_log { format!("{line} | DIP35 FAM LOG (holders read at every arm via {}, <= {} at once; hit = fam >= {}%)",
            if cfg.fam_rpc.is_some() { "--presend-live-fam-rpc" } else { "rpc_url" }, pslog35::FAM_INFLIGHT, cfg.fam_thr) } else { line };
        let line = if cfg.breaker.on() { format!("{line} | CIRCUIT BREAKER ON: {} losses of >= {} SOL within {} min -> no new buys for {} min", cfg.breaker.n,
            cfg.breaker.loss as f64 / 1e9, cfg.breaker.win_ns / 60_000_000_000, cfg.breaker.pause_ns / 60_000_000_000) } else { line };
        let line = if cfg.deep_drop > 0.0 { format!("{line} | DEEP LIMIT ON: limit {:.2}x (drop {}) while another wallet holds >= {DEEP_OB6}% at signing (T2 + re-arm)", 1.0 - cfg.deep_drop, cfg.deep_drop) } else { line };
        // dip37: also at the END, only when on
        let line = if cfg.fab.on { format!("{line} | {}", cfg.fab.desc(cfg.cu_limit, cfg.cu_price, cfg.tip)) } else { line };
        // dip38: also at the END, only when on
        let line = if cfg.blocklist_launcher { format!("{line} | BLOCKLIST LAUNCHER MATCH ON (the create tx's fee payer listed -> skip)") } else { line };
        let line = if cfg.insider_log || cfg.shape_log { format!("{line} | DIP38 ANTI-BAIT LOG ({}{})", if cfg.insider_log { format!("launcher + funding resolver {} rps{} + INSIDER / FAMILY / FAMILY LEDGER {}h <= -{} SOL",
            cfg.fund_rps, if cfg.fund_rpc.is_some() { " via --presend-live-fund-rpc" } else { " via public RPC" }, pslog38::FL_WIN_NS / 3_600_000_000_000, pslog38::FL_LOSS as f64 / 1e9) } else { String::new() },
            if cfg.shape_log { format!("{}SHAPE LEDGER {}h <= -{} SOL", if cfg.insider_log { "; " } else { "" }, pslog38::SH_WIN_NS / 3_600_000_000_000, pslog38::SH_LOSS as f64 / 1e9) } else { String::new() }) } else { line };
        // dip39: also at the END, only when on
        let line = match &cfg.bd { Some(g) => format!("{line} | BOT DEPTH {} {}", if cfg.bd_live { "LIVE" } else { "LOG" }, g.desc()), None => line };
        // dip43 B: one line per item (on or off), before the main line
        for l in cfg.b43.desc_lines(cfg.max_per_sec, cfg.path_max_per_sec, cfg.live_ms) { eprintln!("{l}"); }
        eprintln!("{line}");
        // dip43: one line per Builder A feature (lines of their own, after the start-up line: the monitors parse that one)
        for l in cfg.c43.banner(cfg.fpnb_log) { eprintln!("{l}"); }
        let thread = {
            let (sh, out) = (sh.clone(), out.clone());
            std::thread::Builder::new().name("ps-send".into()).spawn(move || sender(sh, sc, out, atx)).context("ps-send thread")?
        };
        if !cfg.dry {
            let mut body = arbx::alerts::format::Body::new()
                .kv("size", format!("{:.3} SOL", cfg.spend as f64 / 1e9)).kv("attempts", format!("{} per slot, {} lamports each when failed", cfg.k, fee1))
                .kv("caps", format!("{} fills, {:.4} SOL fees per rolling 24 h", if cfg.max_fills == 0 { "unlimited".to_string() } else { cfg.max_fills.to_string() }, cfg.fee_budget as f64 / 1e9));
            // dip26: only with the re-arm on
            if cfg.rearm.on { body = body.kv("re-arm", format!("ON, {:.3} SOL, window to dump + 3 + {}, QUIET {}:{}, R5 skip {}", cfg.rearm.spend as f64 / 1e9, cfg.rearm.gap,
                cfg.rearm.stop.n, cfg.rearm.stop.m, if cfg.rearm.r5_skip { "on" } else { "off" })); }
            tg::raise(arbx::alerts::Level::Info, "dip_presend_live", "start", "🧪", "PRESEND LIVE probe ON", body, false);
        }
        let mut det = pl::Detector::new(cfg.whale_pct);
        det.idle_slots = 6 * 3600 * 1000 / 212;
        // dip27: the hold clocks only with the annotations on
        det.track = cfg.ann;
        // dip28: the hold clocks' preload (the last run's saved state / the offline seed)
        if let Some(p) = &cfg.holds_state {
            match holds_load(&mut det, p) {
                Ok(n) => eprintln!("DIP PRESEND LIVE HOLD CLOCKS: preloaded {n} wallets from {p} (saved back at the run's end)"),
                Err(e) => eprintln!("DIP PRESEND LIVE HOLD CLOCKS: no preload from {p} ({e:#}); they start empty and are saved at the run's end"),
            }
        }
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
        // dip26: the re-arm's state (None when off)
        let rm = cfg.rearm.on.then(|| psrearm::Rearm::new(cfg.rearm.clone()));
        // dip34: the log-only annotations' books (None with their flags off)
        let l34 = L34::new(&cfg);
        // dip35: the holders-read client (None with the flag off)
        let l35 = L35::new(&cfg)?;
        // dip38: the anti-bait log's state and its funding resolver task (nothing with its flags off)
        let l38 = pslog38::L38::new(&cfg, Some(mtx.clone()))?;
        let fab_on = cfg.fab.on;
        // dip37 HYBRID-2: the dump notes from dipmode's M2 path (only with its flags)
        let h2_on = cfg.m2seen_on();
        if h2_on {
            psh2::M2SEEN.store(true, Ordering::SeqCst);
            eprintln!("DIP PRESEND LIVE HYBRID-2 (dip37): nd / m2max / h2_keep / h2_size on every arm and skip record (LOG ONLY){}",
                if cfg.m2seen_gate { " | M2-UNSEEN GATE LIVE: an arm with no M2-scored dump of its mint before the trigger is skipped" } else { "" });
        }
        // dip38 PSM12-S1 (nothing with its log off)
        let s1 = pss1::S1St::new(&cfg);
        if cfg.s1_log {
            eprintln!("DIP PRESEND LIVE PSM12-S1 (dip38): keep iff nd >= {} AND (re-arm OR T2 age >= {}) AND NOT whale ledger (n >= 1, sum <= -{} SOL) AND NOT cold (n == 0, nd < {}) | {}",
                pss1::S1_ND, pss1::S1_AGE, pss1::S1_WH_LOSS as f64 / 1e9, pss1::S1_COLD_ND,
                if cfg.s1_live == 0 { "LOG ONLY (\"s1\" on every arm, fill, realized)".to_string() } else { format!("LIVE GATE {} on parts {}", pslog36::mode_str(cfg.s1_live), pss1::parts_str(cfg.s1_parts)) });
        }
        let mut p = PsLive { cfg, det, wins: FxHashMap::default(), armed: FxHashMap::default(), wid: 0, sh, arx, atts: FxHashMap::default(), order: VecDeque::new(), lands: Vec::new(),
            tapes: FxHashMap::default(), pos: FxHashMap::default(), free_at: FxHashMap::default(), last_deadline: FxHashMap::default(), launches: FxHashMap::default(), last_sweep: 0, cr_saved: 0, cur_r41: false, ce: CrEarn::default(), checks: 0,
            par: FxHashMap::default(),
            st: Stats::default(), out, thread: Some(thread), user, key, rpc: rpc.clone(), path: Some(path.clone()), mtx, allow_holder, stopped: None, stopped_at: None,
            q: None, pid: 0, atas: FxHashMap::default(), quiet: FxHashMap::default(), ends: FxHashMap::default(), retry: Vec::new(), reading: FxHashMap::default(),
            tasks: Arc::new(AtomicU64::new(0)), qt, v2: v2_log.then(pq::V2Ring::new), fee_q: VecDeque::new(), fee_24h: 0, fee_paused: false, fee_pauses: 0, last_t: 0, rm, l34, l35, fp, bl,
            fab: fab_on.then(psfeeab::FabSt::default), whs: pswh::WhSt::default(), h2: h2_on.then(psh2::H2::default), hls: pshl::HlSt::default(), l38, s1, bd, wd, f2, q1,
            d43: Default::default(), b43: ps43_b::B43St::default() };
        if let Some(r) = qrec { p.rec(r); }
        // dip37: the ledgers' control file decides the start modes (nothing without it)
        p.ledger_ctl_open();
        // dip39: the bot depth gate's start record (after the control file: its mode is the start mode; nothing with it off)
        p.bd_start();
        // dip41: the dumper ledger's start record (after the control file; nothing with it off)
        p.wd_start();
        // dip42: FAM2's start record (nothing with it off)
        p.f2_start();
        // dip43: the modes, the book, the taps, the control file's dip43 keys (a record only when an option is given)
        p.d43_start();
        // dip43 B: the control file's "exit_lots", its start record (nothing with its items off)
        p.b43_start();
        Ok(p)
    }

    fn rec(&self, v: serde_json::Value) {
        // dip36 skip2 (log-only): its history sees the skips and disarms (nothing without the flag)
        if let Some(f) = self.fp.as_ref() { f.on_rec(&v); }
        let _ = self.out.send(Out::Rec(v));
    }
    fn line(&self, l: String) { let _ = self.out.send(Out::Line(l)); }

    /// the attempts the sender registered
    fn drain_atts(&mut self) {
        while let Ok(a) = self.arx.try_recv() {
            if let Some(w) = self.wins.get_mut(&a.w) { w.sent += 1; w.last_deadline = w.last_deadline.max(a.deadline); }
            let e = self.last_deadline.entry(a.mint).or_default(); *e = (*e).max(a.deadline);
            let q = self.quiet.entry(a.mint).or_default(); *q = (*q).max(a.deadline);
            cnt_add(&mut self.st.per_path, &a.path, 0);
            cnt_add(&mut self.st.per_client, &a.client, 0);
            // dip37: the fee A/B's count (nothing with it off)
            if let (Some(fs), Some(f)) = (self.fab.as_mut(), a.fa.as_ref()) { fs.cell(f).att += 1; }
            // dip26: the re-arm's own count (nothing without it)
            if let Some(rm) = self.rm.as_mut() { if rm.is_win(a.w) { rm.st.sent += 1; } }
            // dip36 (log-only): the attempt's send slot for FP-NOBOT's per-send score (nothing without the flag)
            if let Some(f) = self.fp.as_ref() { f.send(pslog36::FpMsg::Send { w: a.w, n: a.n, slot: a.slot }); }
            // dip38 (log-only): the window slot's first attempt = its stage "send" (nothing without its flags)
            if self.l38_on() { self.l38_send(a.w, a.slot); }
            self.order.push_back((a.deadline, a.sig, Instant::now()));
            // dip43 A5 (--presend-live-cascade on): the try's holder set at its signing
            if self.cfg.c43.cascade { self.sign43(&a); }
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
        // dip37: an attempt signed with arm B's values is charged on them (off: the run's own, dip36's)
        // dip43 B2: a tiered try (the fee A/B off) on its signed price (nothing noted with the tier off)
        let ff = att.fa.as_ref().map_or_else(|| ps43_b::tier_fail_fee(&att.sig).unwrap_or_else(|| self.cfg.fail_fee()), |f| f.fail_fee());
        let (idx, fee, err) = match &of { Some(f) => (Some(f.index), f.fee, f.err.clone()), None => (None, ff, "?".to_string()) };
        let res = if of.is_some() { pl::classify(&err, &att.roles) } else { "failed_unknown".to_string() };
        // dip43 A5 (cascade on): a later try failing ata_exists gets its own set's verdict at its position
        self.land_note43(&a.tx.sig, &att.mint, &res);
        self.st.fees += fee;
        // dip37: the fee A/B's share (nothing with it off)
        if let (Some(fs), Some(f)) = (self.fab.as_mut(), att.fa.as_ref()) { let c = fs.cell(f); c.fail += 1; c.fail_fee += fee; }
        // dip26: the re-arm's share of the failed-attempt fees (the 24 h budget below is shared)
        if let Some(rm) = self.rm.as_mut() { if rm.is_win(att.w) { rm.st.fees += fee; } }
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
        // dip37 (nothing with the fee A/B off)
        if res == "unseen" { if let (Some(fs), Some(f)) = (self.fab.as_mut(), att.fa.as_ref()) { fs.cell(f).unseen += 1; } }
    }

    /// stop the stream for good (caps / run end): every window disarmed, no new ones
    pub fn stop(&mut self, why: &'static str) {
        if self.stopped.is_some() { return; }
        self.stopped = Some(why);
        self.stopped_at = Some(Instant::now());
        self.sh.stop.store(true, Ordering::SeqCst);
        let ids: Vec<u64> = self.wins.iter().filter(|(_, w)| w.disarmed.is_none()).map(|(k, _)| *k).collect();
        for id in ids { self.disarm(id, "stopped"); }
        // dip26: the re-arm's candidates and waiting windows end (nothing without it)
        self.rearm_stop_all();
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
        // dip26: a re-arm window's end goes to the re-arm's own counters and its record says so (T2 windows: dip25's)
        let re = self.rm.as_mut().and_then(|rm| rm.end(id, why));
        let is_re = re.is_some();
        if !is_re { *self.st.disarms.entry(why).or_default() += 1; }
        let mut r = serde_json::json!({"ev": "presend_live_disarm", "w": id, "mint": b58(&w.mint), "why": why, "t": arbx::feeds::clock::now_ns(), "trig_slot": w.trig_slot, "en_slot": w.en_slot,
            "slot": self.sh.slot.load(Ordering::Relaxed), "armed_ms": w.armed_at.elapsed().as_secs_f64() * 1e3, "attempts": w.sent, "filled": w.filled});
        if let Some(x) = re { r["kind"] = "rearm".into(); r["rearm"] = x; }
        // dip41: a wide window's end
        if let Some((k, v)) = self.wd.as_ref().and_then(|d| d.wins.get(&id)) { r["kind"] = k.key().into(); r[k.field()] = v.json(*k); }
        // dip29: a window that ran under the deeper limit and never filled: what the normal limit would have done (approx: the deepest
        // drop from the highest price since the arm)
        if self.cfg.deep_drop > 0.0 && !w.filled {
            if let Some((m6, _, md)) = w.dl.filter(|d| d.0 >= DEEP_OB6) {
                let would = md >= self.cfg.drop;
                r["deep"] = serde_json::json!({"ob6_max": m6, "max_drop": md, "would_fill_088": would});
                let line = format!("  PRESEND LIVE DEEP-LIMIT NO-FILL w{id} {} | other holder up to {:.1}% | deepest dip {:.1}% -> {}{}", b58(&w.mint), m6, md * 100.0,
                    if would { "BLOCKED (0.88x would have filled)" } else { "no dip deep enough for 0.88x either" }, if is_re { " [rearm]" } else { "" });
                let _ = self.out.send(Out::Line(line));
            }
        }
        // dip20 QUIET (only with it): the stop's verdict, the "other" trades counted (at the stop's decision, or so far when the window
        // ended before it), the arm's signals. dip26: not on a re-arm window's (its own QUIET count is in "rearm")
        if let (Some(qs), false) = (self.qt.as_ref(), is_re) {
            let others = w.q_others.or_else(|| w.qkey.and_then(|k| qs.watch.get(&w.mint).and_then(|v| v.iter().find(|x| x.id == k)).map(|x| x.others)));
            let mut j = w.qj.clone().unwrap_or_else(|| serde_json::json!({}));
            j["others"] = others.into();
            j["decided"] = w.q_others.is_some().into();
            r["quiet"] = j;
            r["quiet_stop"] = (why == "quiet").into();
        }
        // dip43 A8 (--presend-live-acct on): the window's tries not sent, by reason
        self.acct_disarm43(&mut r, id);
        self.rec(r);
    }

    /// an executed tx with pump events (after the reactive bot's decisions and sends of it): creates, triggers, the windows'
    /// prices, our fills, the positions' exits
    #[allow(clippy::too_many_arguments)]
    pub fn on_exec(&mut self, a: &arbx::feeds::Arrival, x: &arbx::feeds::ExecInfo, slot_now: u64, launch_of: impl Fn(&Pk) -> Option<Launch>,
                   reactive_open: &dyn Fn(&Pk) -> bool, first: Option<&FxHashMap<u64, (u64, u16)>>) {
        let t0 = Instant::now();
        self.sh.slot.store(slot_now, Ordering::Relaxed);
        // dip37 HYBRID-2: the dumps dipmode recorded (this tx's and earlier) into the counter, before any trigger of this tx (nothing without it)
        if let Some(h) = self.h2.as_mut() { h.drain(); h.prune(&self.det, slot_now); }
        // dip26 RE-ARM: the executed feed's slot clock first (a new slot: the re-arm windows' stops, the candidates' holders checks), as
        // the observatory's (nothing without it)
        if self.rm.is_some() { self.rearm_slot(a.slot, a.t_rx, &launch_of, reactive_open); }
        for c in &x.creates { self.det.create(c.mint, a.slot, c.creator, c.user, x.mayhem); }
        // dip42 Q1 (log-only): the creates to its thread (nothing with it off)
        if let Some(q) = self.q1.as_mut() { for c in &x.creates { q.create(c.mint, a.slot, x.mayhem); } }
        // dip38: the launchers (the create tx's fee payer; nothing with the blocklist's launcher match and the logs off)
        if !x.creates.is_empty() && self.l38_launch_on() { self.l38_creates(&x.creates, a.tx.keys.first().copied(), a.slot); }
        // dip36 (log-only): FP-NOBOT's chain store takes the creates, then the trades, before any trigger decision (nothing without the flag)
        if let Some(f) = self.fp.as_ref() {
            for c in &x.creates { f.send(pslog36::FpMsg::Create(c.mint, a.slot)); }
            for (j, e) in x.trades.iter().enumerate() {
                f.send(pslog36::FpMsg::Trade(e.mint, arbx::fpnb::Row { s: a.slot, i: x.index as u32, j: j as i32, buy: e.buy, user: e.user, sol: e.sol, tok: e.tok, vsol: e.vsol }));
            }
        }
        let mut evs: Vec<pl::Det> = Vec::new();
        // dip32 (f3 log): did this tx run program 41Pr4XqE (a static key; program ids never come from lookup tables)
        if self.cfg.f3_log { self.cur_r41 = a.tx.ixs.iter().any(|ix| a.tx.keys.get(ix.program as usize) == Some(&P41)); }
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
                    let mut r = serde_json::json!({"ev": "presend_live_sell_land", "w": p.w, "mint": b58(&e.mint), "sig": bs58::encode(&a.tx.sig).into_string(), "slot": a.slot, "idx": x.index,
                        "t": a.t_rx, "sol": e.sol, "fee": x.fee, "pid": p.pid, "round": p.round});
                    if p.rearm { r["kind"] = "rearm".into(); }
                    // dip43 B3: which lot (only a lots exit's position)
                    if !self.b43.lots.is_empty() { if let Some(l) = self.b43_land_lot(&e.mint, e.tok) { r["lot"] = l.into(); } }
                    self.rec(r);
                    // dip43 A7 (shadow exit on): the flow after our sell
                    self.sell_land43(&e.mint, a.slot, a.t_rx);
                }
            }
            // dip43 A6 / A7 (their flags on): the paper landings and the exit shadows see every trade
            self.trade43(&t);
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
            // dip39 BOT DEPTH: a listed wallet's trade into the book and the armed window's copy, before any trigger of it (nothing with it off)
            if self.bd.is_some() { self.bd_trade(&e.mint, &e.user, e.buy, e.sol, e.tok, a.slot, a.t_rx); }
            // dip41 the dumper ledger: every trade (before the detector: a trigger's lookup sees the buys resolved by its slot; nothing with it off)
            if self.wd.is_some() { self.wd_trade(e, a.slot, a.t_rx); }
            // dip42 (log-only; nothing with them off): a family wallet's trade into FAM2's book (before any record of this trade); every
            // trade to Q1's thread
            if self.f2.is_some() { self.f2_trade(&e.mint, &e.user, a.slot); }
            if let Some(q) = self.q1.as_mut() {
                q.trade(psq1::Q1Trade { mint: e.mint, user: e.user, buy: e.buy, sol: e.sol, tok: e.tok, vsol: e.vsol, vtok: e.vtok, slot: a.slot, idx: x.index as u32, j: j as i32,
                    sig: a.tx.sig, t: a.t_rx });
            }
            evs.clear();
            self.det.trade(&t, &mut evs);
            // dip37c: the per-send blocklist's cached listed holder (a listed wallet's trade only; nothing without the flag)
            if self.cfg.blocklist_send { self.bl_send_refresh(&e.mint, Some(&e.user)); }
            // dip38 (log-only): the launcher's trades, the shape's slot deltas, a new >= 3% buyer of an armed token queued (nothing with it off)
            if self.l38_launch_on() { self.l38_trade(&t); }
            for ev in evs.drain(..) {
                match ev {
                    pl::Det::Trigger { whale, pct, bal, age_slots } => {
                        // dip41 QF2: a T2 trigger's annotation record (nothing with QF2 off)
                        if self.wd.is_some() { self.wd_t2(&t, whale, pct, bal, age_slots); }
                        self.trigger(&t, whale, pct, bal, age_slots, &launch_of, reactive_open)
                    }
                    pl::Det::WhaleSell { whale } => {
                        // dip26: never a re-arm window's (its own stops: rearm_trade)
                        if let Some(id) = self.armed.get(&e.mint).copied().filter(|id| !self.rearm_w(*id)) {
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
                    // dip41 the WIDE-DUMPER tier (nothing with the ledger off)
                    pl::Det::Below { whale, pct, bal, age_slots } => if self.wd.is_some() { self.wd_below(&t, whale, pct, bal, age_slots, &launch_of, reactive_open) },
                }
            }
            // dip27 (log-only) / dip28 (the deeper limit): the armed window's largest other holder after this trade (the next attempt's `ob6`)
            if self.cfg.ann || self.cfg.deep_drop > 0.0 {
                if let Some(&id) = self.armed.get(&e.mint) {
                    let o6 = self.wins.get(&id).map_or(0.0, |w| ob6_pct(&self.det, true, &e.mint, &w.whale, &self.user));
                    // dip29: the window's deeper-limit trace (its end line says what the 0.88x limit would have done)
                    if self.cfg.deep_drop > 0.0 {
                        if let Some(w) = self.wins.get_mut(&id) {
                            let (m6, pm, md) = w.dl.unwrap_or((0.0, 0.0, 0.0));
                            let pm = pm.max(t.p_pre());
                            let dr = if pm > 0.0 { 1.0 - t.p() / pm } else { 0.0 };
                            w.dl = Some((m6.max(o6), pm, md.max(dr)));
                        }
                    }
                    let mut g = self.sh.wins.lock().unwrap();
                    // dip30: the landing guard's set as of this trade (the next attempt signs with it)
                    let gs = grd_set(&self.det, self.cfg.ann, &e.mint, &self.user, t.s);
                    if let Some(w) = g.iter_mut().find(|w| w.id == id) { w.ob6 = o6; w.grd = gs; }
                }
            }
            // dip26 RE-ARM: this trade for the re-arm (its windows' stops and QUIET count, a new candidate; nothing without it)
            if self.rm.is_some() { self.rearm_trade(&t); }
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
                // dip43 B3: a stop-loss value while lot 2 waits sells lot 2 at once (nothing without a lots exit under way)
                if !self.b43.lots.is_empty() { self.b43_lot2_stop(&e.mint, e.vsol, e.vtok, t.fr(), a.slot); }
            }
        }
        // dip43 A3 (--presend-live-tbal on): this tx's creates and post balances into the book (after its trades: a fill saw the state before it)
        if self.d43.book.is_some() { self.book43(a, x); }
        self.tick(slot_now, first);
        self.st.us.add((t0.elapsed().as_secs_f64() * 1e6) as f32);
    }

    #[allow(clippy::too_many_arguments)]
    fn trigger(&mut self, t: &pl::Trade, whale: Pk, pct: f64, bal: i64, age_slots: u64, launch_of: &impl Fn(&Pk) -> Option<Launch>, reactive_open: &dyn Fn(&Pk) -> bool) {
        self.trigger_kind(t, whale, pct, bal, age_slots, launch_of, reactive_open, None)
    }

    /// a T2 trigger (`wide` None) or dip41 a WIDE-DUMPER tier's live window (`wide`: the whale's ledger values): the same path, the same live
    /// filters; a wide one's records say "kind": "wide" + "widedumper", its size is --presend-live-wide-size-sol, it is not in T2's counts
    /// nor in the shadow parity (the main shadow never arms a 3..6% whale)
    #[allow(clippy::too_many_arguments)]
    pub(super) fn trigger_kind(&mut self, t: &pl::Trade, whale: Pk, pct: f64, bal: i64, age_slots: u64, launch_of: &impl Fn(&Pk) -> Option<Launch>, reactive_open: &dyn Fn(&Pk) -> bool,
                               wide: Option<(psdl::Kind, psdl::WdV)>) {
        // dip20 QUIET: the window's start is taken BEFORE the QUIET work, so it never moves an attempt (without QUIET: dip19's moment)
        let t_top = self.qt.as_ref().map(|_| arbx::fast::mono_ns());
        if wide.is_none() { self.st.triggers += 1; }
        let (mint_s, sig_s) = (b58(&t.mint), bs58::encode(&t.sig).into_string());
        let trig = serde_json::json!({"mint": mint_s, "wallet": b58(&whale), "pct": pct, "bal": bal, "sig": sig_s, "slot": t.s, "idx": t.i, "j": t.j, "t": t.t_rx, "a": t.a(),
            "age_slots": age_slots, "sol": t.sol, "tok": t.tok, "vsol": t.vsol, "vtok": t.vtok});
        if wide.is_none() { self.par.insert((mint_s.clone(), sig_s.clone(), t.j as i64), (t.s, trig.clone())); }
        // dip41: the wide window's size (T2: the pre-send size)
        let spend = match wide { Some((k, _)) => self.wd.as_ref().map_or(self.cfg.spend, |w| w.size_of(k)), None => self.cfg.spend };
        let launch = launch_of(&t.mint);
        // dip43 A9: the create-slot / young-age gates' control keys ("log": the verdict is kept in would43, the trigger goes on; live: dip42)
        let (cs_hit, ya_hit) = (age_slots == 0 && !self.cfg.create_slot, age_slots < self.cfg.min_age_slots);
        let mut would43: Vec<&'static str> = Vec::new();
        if cs_hit && !self.d43.g.create_slot { would43.push("create_slot"); }
        if ya_hit && !self.d43.g.young_age { would43.push("young_age"); }
        let mut why: Option<&'static str> = if self.stopped.is_some() || DIP_NO_FIRE.load(Ordering::Relaxed) { Some("stopped") }
            else if cs_hit && self.d43.g.create_slot { Some("create_slot") }
            else if ya_hit && self.d43.g.young_age { Some("young_age") }
            // dip26: a re-arm window armed on the token does not block a T2 trigger: the T2 window takes the token over (below)
            else if self.armed.get(&t.mint).is_some_and(|id| !self.rearm_w(*id)) { Some("blocked_armed") }
            else if self.pos.contains_key(&t.mint) || self.free_at.get(&t.mint).is_some_and(|f| Instant::now() < *f) { Some("blocked_position") }
            // dip19: our token account of the mint is still open (sold and kept open until no attempt can land, then closed; or an
            // UNSOLD retry holds it): every attempt would fail at its ATA create
            else if self.atas.contains_key(&t.mint) { Some("blocked_ata_open") }
            else if reactive_open(&t.mint) { Some("reactive_position") }
            // no / legacy / mayhem / non-vanilla launch accounts (dip26: the rule shared with the re-arm, unchanged)
            else { psrearm::launch_refusal(launch.as_ref(), self.allow_holder) };
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
                            // dip43 A9 "quiet": "log" keeps the verdict in would43
                            if on && !self.d43.g.quiet { would43.push("quiet"); }
                            else if on { why = Some("quiet"); q.skips += 1; } else { q.warm_would += 1; j["would_skip"] = true.into(); }
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
        // dip27 LONE WHALE (decided LAST: only a trigger that would arm is skipped "lone_whale"; the detector took its buy already)
        let lw = self.cfg.lone_whale_slots;
        let nb = if lw > 0 { self.det.buyers_since(&t.mint, t.s.saturating_sub(lw - 1), &self.user) } else { None };
        if why.is_none() && nb.is_some_and(|n| n <= 1) { if self.d43.g.lone_whale { why = Some("lone_whale"); } else { would43.push("lone_whale"); } }
        // dip31 the circuit breaker's pause (decided last, like the lone whale: only a trigger that would arm is skipped "breaker")
        if why.is_none() && breaker_paused(&self.sh) { why = Some("breaker"); }
        // dip32 the creator gate (decided last, like the lone whale: only a trigger that would arm is skipped "cr_loss" / "cr_unfollowed")
        let (crw, crj) = if self.cfg.cr_on() { cr_gate(&self.sh, &self.cfg, self.det.creator_bal(&t.mint).map(|c| c.0), t.t_rx) } else { (None, None) };
        if why.is_none() { if let Some(w) = crw { if self.d43.g.cr_loss { why = Some(if w == "loss" { "cr_loss" } else { "cr_unfollowed" }); } else { would43.push(if w == "loss" { "cr_loss" } else { "cr_unfollowed" }); } } }
        // dip37 the whale ledger (LIVE; with the arm-time skips, right after the creator gate; None with it off)
        let whg = pswh::wh_gate(&self.sh, &self.cfg, &whale, false);
        // dip37 the control file: in "log" mode the whale verdict is logged (wh_would), never a skip
        let wh_would = whg.is_some_and(|g| g.0) && !self.hls.live[0];
        if why.is_none() && whg.is_some_and(|g| g.0) && self.hls.live[0] { why = Some("wh_loss"); }
        // dip37 the holder ledger (LIVE; with the arm-time skips; "log" mode: hl_would on the record)
        let hlg = self.hl_gate(&t.mint, &whale);
        let hl_would = hlg.is_some() && !self.hls.live[1];
        if why.is_none() && hlg.is_some() && self.hls.live[1] { why = Some("holder_loss"); }
        // dip37 HYBRID-2: the mint's scored dumps before this trigger (chain order); the m2_unseen gate (LIVE only with its flag)
        let h2v = self.h2.as_ref().map(|h| h.view(&t.mint, t.s, t.i));
        if why.is_none() && self.cfg.m2seen_gate && h2v.is_some_and(|v| v.0 == 0) { why = Some("m2_unseen"); }
        // dip36 LIVE blocklist (with the arm-time skips: only a trigger that would arm; nothing without the flag)
        let blh = if why.is_none() && self.bl.is_some() { self.bl_hit(&t.mint, &whale, "whale", Some(bal)) } else { None };
        let blh = if blh.is_some() && !self.d43.g.blocklist_arm { would43.push("blocklist"); None } else { blh };
        if blh.is_some() { why = Some("blocklist"); }
        // dip32/33 QUIET3-A: the 120 s ring's trades <= 15 and the whale's dumps <= 3 (QUIET's rule on); dip33: LIVE with --presend-live-quiet3a
        let n120 = v2.as_ref().and_then(|v| v["n_120s"].as_u64());
        let whd = qj.as_ref().and_then(|q| q["wh_dumps"].as_u64());
        let q_on = qj.as_ref().is_none_or(|q| q["rule_on"] != false);
        let q3a = q_on && n120.is_some_and(|n| n <= F3_N120) && whd.is_some_and(|d| d <= F3_WHD);
        if why.is_none() && self.cfg.q3a_live && q3a { if self.d43.g.quiet3a { why = Some("quiet3_a"); } else { would43.push("quiet3_a"); } }
        // dip43 (each nothing with its flag off): A1 live a stale trigger after a blind feed; A4 a fan-out mint; A6 the mint ledger
        if why.is_none() && self.stale43(t.s) { why = Some("stale_trigger"); }
        if why.is_none() && self.fan_skip43(&t.mint) { why = Some("fanout"); }
        let mlv = self.ml_view43(&t.mint);
        if why.is_none() && mlv.is_some_and(|v| v.2) { if self.cfg.c43.ml_live { self.d43.ml_skips += 1; why = Some("mint_ledger"); } else { self.d43.ml_would += 1; } }
        if wide.is_none() { self.paper43(t, why, spend); }
        // dip38 PSM12-S1 (log only; LIVE only with its gate on for T2): decided LAST, on a trigger that would arm (None with the log off)
        let s1v = if why.is_none() { self.s1_view(false, h2v.map(|v| v.0), age_slots, &whale) } else { None };
        if let Some(w) = s1v.as_ref().and_then(|v| self.s1_skip_why(v)) { why = Some(w); }
        // dip32 (log-only): QUIET3-A and the fresh holders
        let f3 = self.cfg.f3_log.then(|| {
            let (fresh, fresh_n) = f3_fresh(&self.det, &t.mint, &self.user, &whale, t.s);
            serde_json::json!({"q3a": q3a, "n_120s": n120, "wh_dumps": whd, "fresh": fresh, "fresh_n": fresh_n, "r41": self.cur_r41})
        });
        let tags = (self.cfg.f3_log && !self.cfg.tag_wallets.is_empty()).then(|| tags_json(&self.det, &t.mint, &self.cfg.tag_wallets)).flatten();
        // dip27 (log-only): the annotations
        let ann = self.cfg.ann.then(|| ann_arm(&self.det, &self.user, &t.mint, t.s));
        if let Some(why) = why {
            if wide.is_none() { *self.st.skips.entry(why).or_default() += 1; }
            let mut r = serde_json::json!({"ev": "presend_live_skip", "why": why, "trig": trig});
            // dip41: a wide window's skip says so; a T2 skip carries the whale's dumper ledger values (each only with the ledger on)
            if let Some((k, v)) = wide { r["kind"] = k.key().into(); r[k.field()] = v.json(k); } else { self.wd_t2_fields(&mut r, &whale, t, age_slots); }
            if let Some(j) = &qj { r["quiet"] = j.clone(); r["quiet_skip"] = (why == "quiet").into(); }
            if let Some(v) = v2 { self.st.v2_skip[if v["skip"] == true { 0 } else { 1 }] += 1; r["v2"] = v; }
            if let Some(n) = nb { r["nb"] = n.into(); }
            if let Some(a) = ann { r["ann"] = a; }
            if let Some(j) = &crj { r["cr"] = j.clone(); }
            if let Some((_, h)) = &whg { pswh::wh_fields(&mut r, &self.cfg, &whale, h); }
            if wh_would { r["wh_would"] = true.into(); }
            if let Some(h) = &hlg { PsLive::hl_fields(&mut r, h); if hl_would { r["hl_would"] = true.into(); } }
            if let Some((nd, mx)) = h2v { psh2::fields(&mut r, nd, mx, false, age_slots, self.cfg.spend); }
            if let Some(h) = &blh { PsLive::bl_fields(&mut r, h); }
            if let Some(v) = &s1v { r["s1"] = v.json(self.cfg.s1_parts, self.s1_live(false), self.cfg.spend, t.vsol, t.p()); }
            // dip39 (only with the gate on): the depth at the trigger's slot
            if let Some(j) = self.bd_json(&t.mint, t.s) { r["botdepth"] = j; }
            // dip42 (log-only; only with the flag on): the 2NUM family on the token at the trigger's slot
            if let Some(j) = self.f2_json(true, &t.mint, t.s) { r["fam2"] = j; }
            // dip43 (only with their flags / keys): the mint ledger, the fan-out flag, the gates in log mode
            if let Some(v) = mlv { r["mint_ledger"] = PsLive::ml_json43(v); }
            if let Some(j) = self.fan_json43(&t.mint, None) { r["fanout"] = j; }
            if !would43.is_empty() { r["would43"] = would43.clone().into(); }
            if let Some(f) = &f3 { r["f3"] = f.clone(); }
            if let Some(g) = &tags { r["tags"] = g.clone(); }
            // dip34 (log-only): seen / eqgrp / q4 (each only with its flag); then this skip into the seen book (cr_loss / quiet3_a)
            self.log34(&mut r, &t.mint, &whale, t.s, t.t_rx);
            self.rec(r);
            // dip41: a wide window withheld by a live filter: counted and a line; none of the T2 skip's ledger / paper notes (no shadow row)
            if let Some((k, _)) = wide {
                self.wd_skipped(k, why);
                self.line(format!("  PRESEND LIVE {} SKIP ({why}) {} whale {} {:.1}%", k.name(), b58(&t.mint), &b58(&whale)[..8], pct));
                return;
            }
            self.seen_note(why, whale, t.t_rx, t.mint);
            if why == "wh_loss" {
                if let Some((_, h)) = whg { self.wh_skip_line(&t.mint, &whale, &h, false); }
                // --presend-live-wh-learn paper: the shadow's row c on this trigger will be added to the whale's ledger
                self.wh_paper_note(sig_s.clone(), whale, t.mint, t.t_rx);
            }
            if why == "holder_loss" {
                if let Some(h) = hlg { self.hl_note(&t.mint, &h, false, true); }
                // --presend-live-holder-learn paper: the shadow's row c on this trigger will be added to its holders' ledger
                let keys: Vec<Pk> = self.hl_holders(&t.mint, &whale).into_iter().map(|h| h.0).collect();
                self.hl_paper_note(sig_s.clone(), keys, t.mint, t.t_rx);
            }
            if let (Some(v), true) = (&s1v, why.starts_with("s1_")) { self.s1_skip_note(&t.mint, &whale, v); }
            if why == "quiet3_a" {
                self.line(format!("  PRESEND LIVE QUIET3-A SKIP {} whale {} {:.1}% ({:.2} SOL) | trades in 120 s {}, whale's dumps {}", b58(&t.mint), &b58(&whale)[..8], pct,
                    t.sol as f64 / 1e9, n120.unwrap_or(0), whd.unwrap_or(0)));
            }
            // dip34 CR-EARNBACK (log-only): the shadow's row c on this trigger will be credited to the creator's paper column
            if why == "cr_loss" && self.cfg.cr_earn > 0.0 {
                if let Some(c) = self.det.creator_bal(&t.mint).map(|c| c.0) { self.ce_note(sig_s.clone(), c, t.mint, t.t_rx); }
            }
            if why == "cr_loss" || why == "cr_unfollowed" {
                self.line(format!("  PRESEND LIVE CREATOR SKIP ({why}) {} whale {} {:.1}% ({:.2} SOL) | creator {} history {}", b58(&t.mint), &b58(&whale)[..8], pct,
                    t.sol as f64 / 1e9, self.det.creator_bal(&t.mint).map(|c| b58(&c.0)[..8].to_string()).unwrap_or_default(), crj.as_ref().map(|j| j.to_string()).unwrap_or_default()));
            }
            if let Some(h) = blh.as_ref().filter(|_| why == "blocklist") {
                if let Some(b) = self.bl.as_mut() { b.skips += 1; }
                self.line(format!("  PRESEND LIVE BLOCKLIST SKIP {} whale {} {:.1}% | listed {} ({}, {:.2}%): {}", b58(&t.mint), &b58(&whale)[..8], pct, &b58(&h.0)[..8], h.1, h.2, h.3));
            }
            if why == "lone_whale" {
                self.line(format!("  PRESEND LIVE LONE-WHALE SKIP {} whale {} {:.1}% ({:.2} SOL) | buyers in the last {lw} slots: {}", b58(&t.mint), &b58(&whale)[..8], pct,
                    t.sol as f64 / 1e9, nb.unwrap_or(0)));
            }
            if why == "quiet" {
                let j = qj.as_ref().unwrap();
                self.line(format!("  PRESEND LIVE QUIET SKIP {} whale {} {:.1}% ({:.2} SOL) | since last trade {} slots, cohort holders {}, follower bots {}, whale's dumps drew {:.2} ({})",
                    b58(&t.mint), &b58(&whale)[..8], pct, t.sol as f64 / 1e9, j["since_last"], j["coh_hold"], j["fb_n"], j["wh_fol"].as_f64().unwrap_or(-1.0), j["wh_dumps"]));
            }
            return;
        }
        let launch = launch.expect("checked");
        // dip26: the T2 window takes the token over: its armed re-arm window is disarmed "superseded", its waiting ones end (nothing
        // without the re-arm)
        if self.rm.is_some() { self.rearm_take_over(&t.mint); }
        self.launches.insert(t.mint, launch.clone());
        self.wid += 1;
        let id = self.wid;
        // the window's last slot on the block-position clock (the shadow's en0 = trigger + live_ms + W slots)
        let en_slot = ((t.a() + self.cfg.live_ms + self.cfg.window_slots as f64 * pl::SMS) / pl::SMS).floor() as u64;
        // dip43 B5 --presend-live-start-ms: the first try's offset (off: --presend-live-ms, dip42); the end slot above unchanged
        let st_ns = t_top.unwrap_or_else(arbx::fast::mono_ns) + (self.cfg.b43.start_ms.unwrap_or(self.cfg.live_ms) * 1e6) as u64;
        let slot_ns = arbx::feeds::entries::SLOT_US.load(Ordering::Relaxed) * 1_000;
        // dip36 live gate: the window's verdict cell (shared with the FP thread; None without the log)
        let fpg = self.fp.as_ref().map(|_| Arc::new(pslog36::Gate::default()));
        // dip37: the window's fee arm, once, now (None with the A/B off)
        let fab = self.fab_assign(id);
        let sw = SWin { id, mint: t.mint, launch, st_ns, stop_ns: u64::MAX, en_slot, vsol: t.vsol, vtok: t.vtok, fr: t.fr(), pos: t.pos(), pace: pl::Pace::new(st_ns, self.cfg.k, slot_ns), n: 0, done: false,
            spend, rearm: false, ob6: ob6_pct(&self.det, self.cfg.ann || self.cfg.deep_drop > 0.0, &t.mint, &whale, &self.user),
            grd: grd_set(&self.det, self.cfg.ann, &t.mint, &self.user, t.s), fpg: fpg.clone(), fab, blk: self.bl_send_hit(&t.mint), bd: self.bd_snap(&t.mint) };
        self.sh.wins.lock().unwrap().push(sw);
        self.armed.insert(t.mint, id);
        self.tapes.entry(t.mint).or_insert_with(|| (VecDeque::new(), 0)).0.push_back(t.clone());
        self.wins.insert(id, Win { id, mint: t.mint, whale, trig_slot: t.s, en_slot, armed_at: Instant::now(), stop_at: None, sent: 0, resolved: 0, unseen: 0,
            last_deadline: 0, disarmed: None, filled: false, checked: false, quiet: 0, qj: qj.clone(), qkey, q_others: None, dl: None, excl: Vec::new() });
        // dip20 QUIET: the trigger's stop watch knows its window now
        if let (Some(q), Some(k)) = (self.qt.as_mut(), qkey) {
            if let Some(w) = q.watch.get_mut(&t.mint).and_then(|v| v.iter_mut().find(|w| w.id == k)) { w.win = Some(id); }
        }
        if wide.is_none() { self.st.armed += 1; }
        let mut r = serde_json::json!({"ev": "presend_live_arm", "w": id, "trig": trig, "en_slot": en_slot, "k": self.cfg.k, "spend": spend, "drop": self.cfg.drop,
            "lim0": t.p() * (1.0 - self.cfg.drop), "dry": self.cfg.dry});
        // dip41: a wide window says so (its values kept for its fill / realized); a T2 arm carries the whale's dumper ledger values
        if let Some((k, v)) = wide { r["kind"] = k.key().into(); r[k.field()] = v.json(k); self.wd_armed(id, k, v); } else { self.wd_t2_fields(&mut r, &whale, t, age_slots); }
        if let Some(j) = qj { r["quiet"] = j; r["quiet_skip"] = false.into(); }
        if let Some(v) = v2 { self.st.v2_arm[if v["skip"] == true { 0 } else { 1 }] += 1; r["v2"] = v; }
        // dip27: only when on (off: dip26's record)
        if let Some(n) = nb { r["nb"] = n.into(); }
        if let Some(a) = ann { r["ann"] = a; }
        if let Some(j) = crj { r["cr"] = j; }
        if let Some(f) = f3 { r["f3"] = f; }
        if let Some(g) = tags { r["tags"] = g; }
        // dip37: the window's fee arm and its values (only with the A/B on); the whale ledger's view (only with it on)
        self.fab_arm_rec(&mut r, fab);
        if let Some((_, h)) = &whg { pswh::wh_fields(&mut r, &self.cfg, &whale, h); }
        if wh_would { r["wh_would"] = true.into(); }
        if let Some(h) = &hlg { PsLive::hl_fields(&mut r, h); r["hl_would"] = true.into(); }
        if let Some((nd, mx)) = h2v { psh2::fields(&mut r, nd, mx, false, age_slots, self.cfg.spend); }
        // dip38 PSM12-S1 (log only): the verdict on the arm; the window keeps it for its fill / realize
        if let Some(v) = s1v { r["s1"] = v.json(self.cfg.s1_parts, self.s1_live(false), self.cfg.spend, t.vsol, t.p()); self.s1_arm(id, v); }
        // dip39 (only with the gate on): the depth at the trigger's slot (the first attempts' view)
        if let Some(j) = self.bd_json(&t.mint, t.s) { r["botdepth"] = j; }
        // dip42 (log-only; only with the flag on): the 2NUM family on the token at the trigger's slot
        if let Some(j) = self.f2_json(false, &t.mint, t.s) { r["fam2"] = j; }
        // dip43 (only with their flags / keys): the mint ledger, the fan-out flag, the gates in log mode; A5 the window's first holder set
        if let Some(v) = mlv { r["mint_ledger"] = PsLive::ml_json43(v); }
        if let Some(j) = self.fan_json43(&t.mint, None) { r["fanout"] = j; }
        if !would43.is_empty() { r["would43"] = would43.into(); }
        if self.cfg.c43.cascade { self.wset43(id, &t.mint); }
        self.wh_arm(id, whale);
        self.hl_arm(id, &t.mint, &whale);
        if let Some(h) = &hlg { self.hl_note(&t.mint, h, false, false); }
        // dip34 (log-only): seen / eqgrp / q4 (each only with its flag)
        self.log34(&mut r, &t.mint, &whale, t.s, t.t_rx);
        // dip36 (log-only): FP-NOBOT's copy of the arm record (only with its flag)
        let fpr = self.fp.is_some().then(|| r.clone());
        self.rec(r);
        // dip35 (log-only): the fam holders read (nothing without its flag)
        self.fam_arm(id, t.mint, false, t.s);
        // dip38 (log-only): the anti-bait stage "arm" (nothing without its flags)
        self.l38_arm(id, t.mint, whale, false, t.s, t.t_rx);
        // dip36 (log-only): FP-NOBOT at the arm (its thread; nothing without the flag)
        if let Some(r) = fpr { self.fpnb_arm(id, false, t.mint, t, whale, t.s, Vec::new(), &r, en_slot, fpg); }
        self.line(format!("  PRESEND LIVE ARM w{id} {} whale {} {:.1}% ({:.2} SOL) age {} slots | until slot {en_slot} | {} attempts/slot, limit {:.2}x{}", b58(&t.mint),
            &b58(&whale)[..8], pct, t.sol as f64 / 1e9, age_slots, self.cfg.k, 1.0 - self.cfg.drop,
            wide.map(|(k, v)| format!(" [{}: {}/{} {}, {:.3} SOL]", k.key(), v.hits(k), v.n, if k == psdl::Kind::Wide { "dumped" } else { "sold fast" }, spend as f64 / 1e9)).unwrap_or_default()));
    }

    /// one of our attempts filled (its buy TradeEvent)
    fn fill(&mut self, t: &pl::Trade, fee: u64, reactive_on_mint: bool) {
        let w_fp = self.atts.get(&t.sig).map(|(a, _)| a.w);
        self.fill_inner(t, fee, reactive_on_mint);
        // dip38 (log-only): the anti-bait stage "fill" (the holders at our landing; the detector has not taken our buy yet)
        if let (Some(w), true) = (w_fp, self.l38_on()) { self.l38_fill(w, t.mint, t.s, t.t_rx); }
        // dip36 (log-only): FP-NOBOT's decided send (t = fill slot - 1) for this fill (nothing without the flag)
        if let (Some(w), true) = (w_fp, self.fp.is_some()) {
            let pid = self.pos.get(&t.mint).map(|p| p.pid);
            if let Some(f) = self.fp.as_ref() { f.send(pslog36::FpMsg::Fill { w, pid, mint: t.mint, slot: t.s }); }
        }
    }

    fn fill_inner(&mut self, t: &pl::Trade, fee: u64, reactive_on_mint: bool) {
        // dip43 A2: a fill a status read opened already (the feed was blind): its buy gets the feed's values, never a second open
        if self.fill_dedupe43(t, fee) { return; }
        let Some((att, done)) = self.atts.get_mut(&t.sig) else { return };
        let first = !*done;
        *done = true;
        let att = att.clone();
        if first { self.resolve(&att, "ok"); }
        self.lands.push(Land { att: att.clone(), res: "ok".into(), err: String::new(), fee, slot: t.s, idx: Some(t.i as u64), t_rx: t.t_rx, at: Instant::now() });
        self.st.fills += 1;
        self.st.fee_fills += fee;
        self.st.tips += att.tip;
        // dip37 (nothing with the fee A/B off)
        if let (Some(fs), Some(f)) = (self.fab.as_mut(), att.fa.as_ref()) { let c = fs.cell(f); c.fills += 1; c.fill_fee += fee; c.tips += att.tip; }
        // dip37 holder ledger: the holders at our landing join the window's keys (nothing with it off)
        if self.cfg.hl_on() { let wh = self.wins.get(&att.w).map_or(self.user, |w| w.whale); self.hl_fill(att.w, &t.mint, &wh); }
        // dip26: a re-arm window's fill (its size; its records and lines say so; the re-arm's own count)
        let (rearm, spend) = (self.rearm_w(att.w), self.w_spend(att.w));
        if rearm { if let Some(rm) = self.rm.as_mut() { rm.st.fills += 1; } }
        // a fill while its window was still armed, or a late one (an attempt in flight when the window ended)
        let window_open = self.wins.get(&att.w).is_some_and(|w| w.disarmed.is_none());
        if !window_open { self.st.late_fills += 1; }
        if let Some(w) = self.wins.get_mut(&att.w) { w.filled = true; }
        self.disarm(att.w, "filled");
        // every fill created our token account (its NON-idempotent create passed): the ATA rent is in its cost
        let cost = spend + fee + att.tip + T22_ATA_RENT;
        let trig_slot = self.wins.get(&att.w).map(|w| w.trig_slot).unwrap_or(0);
        // dip19 (fix 2): a fill on a position whose exit has started (w51's attempt B): never merged into the sell under way
        let after_exit = self.pos.get(&t.mint).is_some_and(|p| p.round > 0);
        let mut rec = serde_json::json!({"ev": "presend_live_fill", "w": att.w, "n": att.n, "mint": b58(&t.mint), "sig": bs58::encode(&t.sig).into_string(), "slot": t.s, "idx": t.i,
            "t": t.t_rx, "tokens": t.tok, "sol_in": t.sol, "fee": fee, "tip": att.tip, "path": att.path, "client": att.client, "p_sign": att.p_sign, "lim": att.lim, "min_out": att.min_out,
            "p_entry_post": t.p(), "p_entry_pre": t.p_pre(), "slots_after_trigger": t.s.saturating_sub(trig_slot), "slots_after_send": t.s.saturating_sub(att.slot),
            "ms_send_to_rx": (t.t_rx as i64 - att.t_send as i64) as f64 / 1e6, "window_open": window_open, "reactive_on_mint": reactive_on_mint, "after_exit": after_exit});
        if rearm { rec["kind"] = "rearm".into(); rec["spend"] = spend.into(); }
        // dip41: a wide window's fill (its size, the whale's ledger values at the arm)
        if let Some((k, v)) = self.wd_win(att.w) { rec["kind"] = k.key().into(); rec["spend"] = spend.into(); rec[k.field()] = v.json(k); }
        // dip38 PSM12-S1 (log only): the window's verdict at its arm (nothing with the log off)
        if let Some(j) = self.s1_fill(att.w, true) { rec["s1"] = j; }
        // dip39 (only with the gate on): the filling attempt's verdict at its send, the depth at the fill's slot
        if let Some(j) = self.bd_fill_json(att.bd, &t.mint, t.s) { rec["botdepth"] = j; }
        // dip42 (log-only; only with the flag on): the 2NUM family on the token before our fill (kept for the realized record)
        if let Some(j) = self.f2_fill_json(att.w, t) { rec["fam2"] = j; }
        // dip37: the filling attempt's fee arm and values (only with the A/B on)
        if let Some(f) = &att.fa { f.put(&mut rec, att.tip); }
        // dip27 (log-only): the deeper-limit lead's would-skip (T2: another wallet >= 6% at signing and a drop < 15% from the signing
        // price to the price just before our buy) and the holders >= 2% at our landing with their hold clocks (the detector has not
        // taken our buy yet: the holders just before it)
        // dip28: the fill's try used the deeper limit (only with it on)
        if self.cfg.deep_drop > 0.0 { rec["deep"] = (att.ob6 >= DEEP_OB6).into(); }
        if self.cfg.ann {
            let depth = if att.p_sign > 0.0 { 1.0 - t.p_pre() / att.p_sign } else { 0.0 };
            let ctx85 = !rearm && att.ob6 >= 6.0 && depth < 0.15;
            if ctx85 { self.st.ann_ctx85 += 1; }
            // dip30: up to 12 holders (6 cut groups of 2-6% holders short: 62 of run 40's 290 fills had 6)
            let hc = self.det.holder_clocks(&t.mint, (0.02 * pl::SUPPLY) as i64, &self.user, t.s, 12);
            // dip28 (log-only): the SAFE sell-timer check's would-block: a holder >= 6% (the whale too) still holding at our landing whose
            // hold clock gives a first sell within 3 slots a hazard >= 0.3 with >= 5 holds at risk (TIMING a2 X6 t0.3)
            let st = hc.iter().any(|h| h.bal as f64 >= 0.06 * pl::SUPPLY && h.risk >= 5 && h.hz3 >= 0.3);
            if st { self.st.ann_st += 1; }
            // dip30 GROUP RISK (log-only; owner 10-30 ~23:55 PKT): the safe check's per-holder test (>= 5 holds at risk, hz3 >= 0.3) on
            // holders of ANY size (>= 2%) still holding at our landing, their holdings summed >= 6% (replay 20 runs: +4.27 SOL, 15/20 runs)
            let grp: Vec<&pl::HolderClock> = hc.iter().filter(|h| h.risk >= 5 && h.hz3 >= 0.3).collect();
            let grp_pct: f64 = grp.iter().map(|h| h.bal as f64 / pl::SUPPLY * 100.0).sum();
            let grp_block = grp_pct >= 6.0;
            if grp_block { self.st.ann_grp += 1; }
            // dip30 LANDING GUARD (log-only): the set chosen at this fill's signing, their holdings NOW (our landing, before our buy) summed
            let gl: Vec<(Pk, i64, i64)> = att.grd.w[..att.grd.n as usize].iter().map(|(w, b)| (*w, *b, self.det.bal(&t.mint, w))).collect();
            let gd_pct: f64 = gl.iter().map(|(_, _, b)| *b as f64 / pl::SUPPLY * 100.0).sum();
            let gd_block = gd_pct >= GRD_PCT;
            if gd_block { self.st.ann_guard += 1; }
            // dip29: one plain line per fill with what every filter / log-only rule said
            let due: Vec<String> = hc.iter().filter(|h| h.bal as f64 >= 0.06 * pl::SUPPLY && h.risk >= 5 && h.hz3 >= 0.3).map(|h| format!("{} {:.1}% hz {:.2}", &b58(&h.w)[..8], h.bal as f64 / pl::SUPPLY * 100.0, h.hz3)).collect();
            self.line(format!("  PRESEND LIVE FLAGS w{} {}: dip {:.1}% | other holder {:.1}% -> deeper limit {} | safe sell timer {} | group risk {} | landing guard {}{}", att.w, b58(&t.mint), depth * 100.0, att.ob6,
                if self.cfg.deep_drop > 0.0 { if att.ob6 >= DEEP_OB6 { "USED" } else { "not needed" } } else if ctx85 { "WOULD SKIP (log)" } else { "no" },
                if st { format!("WOULD BLOCK (log): {}", due.join(", ")) } else { "no".to_string() },
                if grp_block { format!("WOULD BLOCK (log): {:.1}% = {}", grp_pct, grp.iter().map(|h| format!("{} {:.1}%", &b58(&h.w)[..8], h.bal as f64 / pl::SUPPLY * 100.0)).collect::<Vec<_>>().join(" + ")) }
                else { format!("no ({grp_pct:.1}%)") },
                if gd_block { format!("WOULD BLOCK (log): {:.1}% still held by {}", gd_pct, gl.iter().map(|(w, s, b)| format!("{} {:.1}->{:.1}%", &b58(w)[..8], *s as f64 / pl::SUPPLY * 100.0, *b as f64 / pl::SUPPLY * 100.0)).collect::<Vec<_>>().join(", ")) }
                else { format!("no ({} wallets, {gd_pct:.1}%)", gl.len()) }, if rearm { " [rearm]" } else { "" }));
            rec["ann"] = serde_json::json!({"ob6": att.ob6, "depth": depth, "ctx85": ctx85, "st_block": st, "grp_block": grp_block, "grp_pct": grp_pct,
                "guard": {"block": gd_block, "pct": gd_pct, "set": gl.iter().map(|(w, s, b)| serde_json::json!({"w": b58(w), "sign_pct": *s as f64 / pl::SUPPLY * 100.0, "land_pct": *b as f64 / pl::SUPPLY * 100.0})).collect::<Vec<_>>()},
                "holders": hc.iter().map(|h| serde_json::json!({"w": b58(&h.w),
                "pct": h.bal as f64 / pl::SUPPLY * 100.0, "age": h.age, "n": h.n, "p25": h.p25, "p50": h.p50, "p75": h.p75, "h3": h.h3, "risk": h.risk, "hz3": h.hz3})).collect::<Vec<_>>()});
        }
        // dip34 (--presend-live-eqgrp-log, log-only): equal-size holder groups at our landing (the window's whale / dumper out)
        if self.cfg.eqgrp_log {
            let wh = self.wins.get(&att.w).map_or(self.user, |w| w.whale);
            self.eqgrp_fill(&mut rec, &t.mint, &wh);
        }
        // dip43 (each only with its flag): A5 cascade, A6 mint ledger, A4 fan-out, A10 shadows, A7 the exit shadow's start
        self.fill43(&mut rec, &att, t);
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
                self.pos.insert(t.mint, PPos { pid: self.pid, w: att.w, mint: t.mint, launch, derived, buys: vec![buy], land: (t.s, t.i as u64, t.t_rx), tokens: t.tok, spend,
                    att: Some(att.clone()), exit: None, sell_lands: Vec::new(), sells: Vec::new(), round: 0, selling: false, opened: Instant::now(), acct, merged: 0, late: 0, via: "feed",
                    rearm });
                self.sh.pause_pos.store(true, Ordering::Relaxed);
                self.tapes.entry(t.mint).or_insert_with(|| (VecDeque::new(), 0));
            }
        }
        if let Some((pid, round, matched)) = late {
            self.st.after_exit += 1;
            self.line(format!("  PRESEND LIVE FILL AFTER THE EXIT w{} {}: +{} tokens on a token whose sell (round {round}) is under way: NOT merged into it; {}", att.w, b58(&t.mint), t.tok,
                if matched { "it is the balance a read found (its recovery sell covers it)".to_string() } else { format!("its own sell (round {}) when that one finishes", round + 1) }));
            let mut r = serde_json::json!({"ev": "presend_live_late_fill", "w": att.w, "pid": pid, "round": round, "mint": b58(&t.mint), "sig": sig, "slot": t.s, "idx": t.i, "tokens": t.tok,
                "sol_in": t.sol, "fee": fee, "tip": att.tip, "matched_read": matched});
            if rearm { r["kind"] = "rearm".into(); }
            self.rec(r);
            self.alert(arbx::alerts::Level::Warning, "dip_presend_late_fill", &b58(&t.mint), "⚠️", "PRESEND LIVE: a fill after the exit (its own sell next)", arbx::alerts::format::Body::new()
                .raw(format!("mint {}", tg::mint_link(&t.mint))).kv("tokens", t.tok.to_string()).kv("window", format!("w{}", att.w)).txt("not merged into the sell under way: sold by the next round"));
        }
        self.line(format!("  PRESEND LIVE FILL w{} {} {:.3} SOL -> {} tokens | slot {} (+{} after the send, {:.0} ms send->seen) | path {} ({}) | fills {}/{}{}", att.w, b58(&t.mint),
            t.sol as f64 / 1e9, t.tok, t.s, t.s.saturating_sub(att.slot), (t.t_rx as i64 - att.t_send as i64) as f64 / 1e6, att.path, att.client, self.st.fills, self.cfg.max_fills,
            if rearm { " [rearm]" } else { "" }));
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
        let mut r = serde_json::json!({"ev": "presend_live_exit", "w": p.w, "mint": b58(mint), "why": why, "slot": slot, "value": if val.is_nan() { serde_json::Value::Null } else { serde_json::json!(val) },
            "t": t, "slots_held": slot as i64 - p.land.0 as i64, "pid": p.pid, "round": 1, "tokens": p.tokens});
        // dip26: a re-arm position's exit says so (the line's end: its prefix unchanged)
        if p.rearm { r["kind"] = "rearm".into(); }
        let pid = p.pid;
        let l = format!("  PRESEND LIVE EXIT {} {why} slot {slot} (held {} slots){}{}", b58(mint), slot as i64 - p.land.0 as i64, if val.is_nan() { String::new() } else { format!(" value x{val:.3}") },
            if p.rearm { " [rearm]" } else { "" });
        // dip43 B3 / B4: lot 1 of a two-lot exit / a cheap timer sell (false with their flags off: dip42's sell_round)
        if !self.b43_exit(mint, why, slot, &mut r) { self.sell_round(mint); }
        self.rec(r);
        self.line(l);
        // dip43 A7 (shadow exit on): the real exit and the stop shadow
        self.exit43(mint, why, slot, val, t, pid);
    }

    /// dip19 (fix 1/2): the position's next sell round: every buy no round covers yet, sold as one (exact tokens; confirmed reads from
    /// the latest of their landings), the token account KEPT OPEN (the attempts' guard). Every round sends at once from its decision
    /// (no RPC first: M4-1): a buy left for a follow-up round landed after the previous round's last confirmed read, so that round
    /// never saw (nor sold) its tokens
    fn sell_round(&mut self, mint: &Pk) { self.sell_round_x(mint, None) }

    /// `sell_round` with dip43's per-exit sell options (`x` None: dip42's round)
    fn sell_round_x(&mut self, mint: &Pk, x: Option<SellX>) {
        let Some(p) = self.pos.get_mut(mint) else { return };
        p.round += 1;
        let round = p.round;
        let (mut tokens, mut land) = (0u64, 0u64);
        for b in p.buys.iter_mut().filter(|b| b.round == 0) { b.round = round; tokens += b.tokens; land = land.max(b.slot); }
        p.selling = true;
        let c = Cmd::Sell { mint: *mint, pid: p.pid, round, launch: p.launch.clone(), derived: p.derived, known: (tokens > 0).then_some(tokens), guess: tokens, land_slot: land,
            read_first: false, keep_ata: true, x43: x };
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
            PsMsg::Fam(r) => self.fam_done(*r),
            PsMsg::Fund(o) => self.l38_fund(*o),
            PsMsg::Status(r) => self.on_status43(*r),
            PsMsg::UnsoldDone(mint, sold) => {
                // the background retry ended: sold = an empty account (closed later, as any), else (given up at the run's end) left to the end check
                if self.pos.contains_key(&mint) { return; }
                if let Some(a) = self.atas.get_mut(&mint) { if a.st == AtaSt::Held { a.st = if sold { AtaSt::Idle } else { AtaSt::GaveUp }; } }
            }
        }
    }

    /// dip19 (fix 2): a sell round of position `pid` finished
    fn on_sold(&mut self, mint: Pk, pid: u64, round: u32, out: SellOut) {
        // dip43 B3: a lots exit's answers (lot 1's / lot 2's while lot 1's loop runs) are taken there; nothing without a lots exit under way
        let (round, out) = if self.b43.lots.is_empty() { (round, out) } else { match self.b43_sold(mint, pid, round, out) { Some(x) => x, None => return } };
        let Some(p) = self.pos.get_mut(&mint).filter(|p| p.pid == pid && p.round == round && p.selling) else {
            // never expected (one sell per position at a time, rounds in order): recorded, nothing changes
            self.rec(serde_json::json!({"ev": "presend_live_sold_stale", "mint": b58(&mint), "pid": pid, "round": round, "sold_at": out.sold_at, "sell_sigs": out.sigs}));
            return;
        };
        p.selling = false;
        p.sells.extend(out.sigs.iter().cloned());
        // dip26: a re-arm position's follow-up exit says so
        let rearm = p.rearm;
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
            let mut r = serde_json::json!({"ev": "presend_live_exit", "w": w, "mint": b58(&mint), "why": "follow-up", "slot": self.sh.slot.load(Ordering::Relaxed), "value": null,
                "t": arbx::feeds::clock::now_ns(), "pid": pid, "round": round + 1, "tokens": toks, "buys": n, "after_sold_at": c});
            if rearm { r["kind"] = "rearm".into(); }
            self.rec(r);
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
        // dip26: the re-arm's own count
        if p.rearm { if let Some(rm) = self.rm.as_mut() { rm.st.closed += 1; } }
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
        let mut r = r;
        if p.rearm { r["kind"] = "rearm".into(); }
        self.rec(r);
        self.line(format!("  PRESEND LIVE CLOSED {} {} via {why}; curve PnL {}{}{}", b58(&mint), if sold { "sold" } else { "UNSOLD (retrying in the background)" },
            feed_pnl.map(|v| format!("{:+.4} SOL", v as f64 / 1e9)).unwrap_or("?".into()),
            if p.buys.len() > 1 || p.round > 1 { format!(" ({} buys, {} sell round(s), every one in the P&L)", p.buys.len(), p.round) } else { String::new() },
            if p.rearm { " [rearm]" } else { "" }));
        if !sold { self.exec(Cmd::Unsold { mint, launch: p.launch.clone(), land_slot: last, last_qty: out.last_qty }); }
        // dip32 the creator gate: the position's creator and whether another wallet followed us (the token's tape), into its history
        let cr = self.cfg.cr_on().then(|| self.det.creator_bal(&mint).map(|c| c.0)).flatten().map(|c| {
            let (wh, ex) = self.wins.get(&p.w).map(|w| (Some(w.whale), w.excl.clone())).unwrap_or((None, Vec::new()));
            let first = p.buys.iter().map(|b| (b.slot, b.idx)).min().unwrap_or((p.land.0, p.land.1));
            let lastl = p.sell_lands.iter().map(|x| (x.0, x.1)).max().unwrap_or((first.0 + 3, u64::MAX));
            let fol = self.tapes.get(&mint).is_some_and(|(tp, _)| followed(tp, &self.user, wh.as_ref(), &ex, first, lastl));
            (c, fol)
        });
        // dip34 QUIET4 (--presend-live-q4-log, log-only): the position's whale / dumper, followed (dip32's rule, the same hold window) and
        // its hold tape's sellers into the rolling maps (nothing without the flag)
        if self.cfg.q4_log {
            let (wh, ex) = self.wins.get(&p.w).map(|w| (Some(w.whale), w.excl.clone())).unwrap_or((None, Vec::new()));
            let first = p.buys.iter().map(|b| (b.slot, b.idx)).min().unwrap_or((p.land.0, p.land.1));
            let lastl = p.sell_lands.iter().map(|x| (x.0, x.1)).max().unwrap_or((first.0 + 3, u64::MAX));
            let (fol, sellers) = match self.tapes.get(&mint) {
                Some((tp, _)) => (followed(tp, &self.user, wh.as_ref(), &ex, first, lastl), pslog34::hold_sellers(tp, &self.user, first, lastl)),
                None => (false, Vec::new()),
            };
            self.q4_note(arbx::feeds::clock::now_ns(), wh, fol, &sellers);
        }
        // dip43 A6 / A7 (their flags on): the landing's result into the mint ledger, the exit shadow may finish
        self.close43(p.pid, mint, feed_pnl, p.fees(), p.tips());
        // dip36 (log-only): the position into FP-NOBOT's own-result book (its P&L follows; nothing without the flag)
        self.fpnb_close(&p);
        self.realized(&p, cr);
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
        // dip26: a re-arm window's (its size, its records say so)
        let (rearm, spend) = (self.rearm_w(w), self.w_spend(w));
        let mut r = serde_json::json!({"ev": "presend_live_orphan", "w": w, "mint": b58(&mint), "tokens": tokens, "ctx_slot": ctx, "from": from, "launch": if derived { "derived" } else { "create" }});
        if rearm { r["kind"] = "rearm".into(); }
        self.rec(r);
        self.alert(arbx::alerts::Level::Critical, "dip_presend_orphan", &b58(&mint), "🚨", "PRESEND LIVE ORPHAN: selling", arbx::alerts::format::Body::new()
            .raw(format!("mint {}", tg::mint_link(&mint))).kv("tokens", tokens.to_string()).kv("found by", from).txt("a recovery position sells it now; by hand: --sell-held").code("mint", b58(&mint)));
        let e = self.ends.entry(mint).or_default(); *e = (*e).max(ctx);
        let now_ns = arbx::feeds::clock::now_ns();
        self.pid += 1;
        // its buy's tx is not known: valued at the spend (dip18's held-check), replaced by the fill if the feed shows it later
        let acct = PsAcct::open(mint, spend, ctx);
        let buy = Buy { sig: String::new(), w, slot: ctx, idx: 0, t_rx: now_ns, tokens, sol_in: spend, fee: 0, tip: 0, cost: spend, round: 0, via: "rpc_read" };
        self.pos.insert(mint, PPos { pid: self.pid, w, mint, launch, derived, buys: vec![buy], land: (ctx, 0, now_ns), tokens, spend, att: None, exit: None,
            sell_lands: Vec::new(), sells: Vec::new(), round: 0, selling: false, opened: Instant::now(), acct, merged: 0, late: 0, via: "rpc_read", rearm });
        self.ata_held(mint, ctx);
        self.sh.pause_pos.store(true, Ordering::Relaxed);
        self.tapes.entry(mint).or_insert_with(|| (VecDeque::new(), 0));
        let s = self.sh.slot.load(Ordering::Relaxed);
        self.exit(&mint, "orphan", s, f64::NAN, now_ns);
    }

    /// dip19 (fix 3): the position's realized P&L from its own transactions: EVERY buy's payer delta (spend, fees, tips, the ATA
    /// rent) and EVERY sell's of every round, into the run's realized total (the kill switch's realized rule) and the log
    fn realized(&mut self, p: &PPos, cr: Option<(Pk, bool)>) {
        let buys: Vec<(String, u64)> = p.buys.iter().map(|b| (b.sig.clone(), b.cost)).collect();
        // dip37: the position's arm (its filling attempt's; an orphan's: its window's, group "other"); None with the A/B off
        let ab = self.fab.as_ref().and_then(|fs| match p.att.as_ref().and_then(|a| a.fa.map(|f| (f, a.tip))) {
            Some((f, tip)) => Some(psfeeab::RzAb { arm: f.arm, grp: f.grp, fee: Some(f), tip }),
            None => fs.arm_of(p.w).map(|arm| psfeeab::RzAb { arm, grp: 2, fee: None, tip: 0 }),
        });
        // dip37: the window's arm wallet (the ledger on)
        let wh = self.cfg.wh_on().then(|| self.whs.win.get(&p.w).map(|k| (*k, p.rearm))).flatten();
        // dip37: the window's holder keys (the holder ledger on; empty otherwise)
        let hl = if self.cfg.hl_on() { self.hls.keys.get(&p.w).cloned().unwrap_or_default() } else { Vec::new() };
        // dip38 (log-only): the fill's anti-bait view for the ledgers (None with its flags off)
        let l38 = self.l38_realize(p.w, p.pid, p.rearm);
        // dip38 PSM12-S1 (log only): the window's verdict on the realized record (None with the log off)
        let s1 = self.s1_fill(p.w, false);
        // dip41: a wide window's position (its record says so; the values kept until now are let go)
        let wd = self.wd.as_mut().and_then(|d| d.wins.remove(&p.w)).map(|(k, v)| (k.key(), k.field(), v.json(k)));
        // dip42 (log-only): the fill's family view (None with the flag off)
        let f2 = self.f2_realized(p.w);
        self.exec(Cmd::Realized { pid: p.pid, w: p.w, mint: p.mint, buys, sells: p.sells.clone(), rearm: p.rearm, cr, ab, wh, hl, l38, s1, wd, f2 });
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
            Cmd::Sell { mint, pid, round, launch, derived, known, guess, land_slot, read_first, keep_ata, x43 } => {
                let Some(path) = self.path.clone() else { self.line(format!("  PRESEND LIVE {}: NO SEND PATH: sell by hand (--sell-held {})", b58(&mint), b58(&mint))); return };
                let (key, rpc, mtx) = (self.key.clone(), self.rpc.clone(), self.mtx.clone());
                tasks.fetch_add(1, Ordering::SeqCst);
                tokio::spawn(async move {
                    let ata = pda::ata(&user, &mint, &pda::TOKEN_2022);
                    let launch = if derived { resolve_launch(&rpc, &mint).await.0 } else { launch };
                    let mut o = SellOpts::main();
                    o.read_first = read_first;
                    o.keep_ata = keep_ata;
                    let out = sell_until_zero_x(&key, user, &rpc, &path, &launch, &ata, known, guess, land_slot, o, x43).await;
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
            Cmd::Realized { pid, w, mint, buys, sells, rearm, cr, ab, wh, hl, l38, s1, wd, f2 } => {
                let (rpc, out) = ((*self.rpc).clone(), self.out.clone());
                // dip31: the circuit breaker sees every realized P&L (off: nothing)
                let (sh, brk) = (self.sh.clone(), self.cfg.breaker);
                // dip26: the realized split by kind (only with the re-arm on)
                let rz = self.rz();
                // dip36 (log-only): the P&L to FP-NOBOT's book (None without the flag)
                let fpx = self.fp.as_ref().and_then(|f| f.tx.clone());
                // dip37: the realized split by fee arm x group (None with the A/B off); the whale ledger's split
                let frz = self.fab.as_ref().map(|f| f.rz.clone());
                let whsplit = self.cfg.wh_split;
                REALIZED_INFLIGHT.fetch_add(1, Ordering::SeqCst);
                tokio::spawn(async move {
                    let mut bs = Vec::with_capacity(buys.len());
                    for (sig, cost) in &buys { bs.push((if sig.is_empty() { None } else { tx_payer(&rpc, sig, 8).await }, *cost)); }
                    let mut ss = Vec::with_capacity(sells.len());
                    for (s, seen, _) in &sells { ss.push(tx_payer(&rpc, s, if *seen { 8 } else { 2 }).await); }
                    let (pnl, nb, ns) = pnl_of(&bs, &ss);
                    if let Some(tx) = &fpx { let _ = tx.send(pslog36::FpMsg::Realized { pid, pnl, mint, w, t: arbx::feeds::clock::now_ns() }); }
                    ACCT.realized.fetch_add(pnl, Ordering::SeqCst);
                    if let Some(z) = &rz { z.add(rearm, pnl); }
                    let (mut rec, line) = realized_out(w, pid, &mint, pnl, &buys, &bs, nb, ns, sells.len(), rearm);
                    // dip38 PSM12-S1 (log only): the window's verdict
                    if let Some(j) = s1 { rec["s1"] = j; }
                    // dip41: a wide window's position
                    if let Some((k, f, j)) = wd { rec["kind"] = k.into(); rec[f] = j; }
                    // dip42 (log-only): the fill's family view
                    if let Some(j) = f2 { rec["fam2"] = j; }
                    // dip37 (nothing with the fee A/B off)
                    if let (Some(z), Some(a)) = (&frz, &ab) { z.add(a.arm, a.grp, pnl); a.put(&mut rec); }
                    // dip37 the whale / dumper ledger: this position into its arm wallet's history (nothing with the ledger off)
                    if let Some((k, re)) = wh {
                        let h = sh.wh.lock().unwrap().add(whsplit, re, k, pnl, false);
                        rec["wh"] = serde_json::json!({"wallet": b58(&k), "n": h.n, "sum": h.sum as f64 / 1e9});
                    }
                    // dip37 the holder ledger: this position into each of its holder keys (nothing with it off)
                    if !hl.is_empty() {
                        { let mut g = sh.hl.lock().unwrap(); for k in &hl { g.entry(*k).or_default().add(pnl, false); } }
                        rec["hl"] = hl.iter().map(b58).collect::<Vec<_>>().into();
                    }
                    // dip32 the creator gate: this position into its creator's history (known from now on)
                    if let Some((c, fol)) = cr {
                        sh.cr.lock().unwrap().entry(c).or_default().add(arbx::feeds::clock::now_ns(), pnl, fol);
                        rec["cr"] = serde_json::json!({"creator": b58(&c), "followed": fol});
                    }
                    let _ = out.send(Out::Rec(rec));
                    let _ = out.send(Out::Line(line));
                    // dip38 (log-only): the family / shape ledgers learn this P&L; their realize records (nothing with the logs off)
                    if let Some(z) = &l38 { for r in z.learn(pnl, arbx::feeds::clock::now_ns()) { let _ = out.send(Out::Rec(r)); } }
                    if let Some(n) = breaker_note(&sh, &brk, pnl, arbx::fast::mono_ns()) {
                        let _ = out.send(Out::Rec(serde_json::json!({"ev": "presend_live_breaker", "losses": n, "last_mint": b58(&mint), "last_pnl": pnl,
                            "pause_min": brk.pause_ns / 60_000_000_000, "trips": sh.brk_trips.load(Ordering::SeqCst)})));
                        let _ = out.send(Out::Line(format!("  PRESEND LIVE CIRCUIT BREAKER TRIPPED: {n} losses of >= {} SOL within {} min (last {} {:+.4}) -> no new buys for {} min",
                            brk.loss as f64 / 1e9, brk.win_ns / 60_000_000_000, b58(&mint), pnl as f64 / 1e9, brk.pause_ns / 60_000_000_000)));
                    }
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
            // dip43 A2: the blind try's status + our token account (processed), off the event loop; a sell after it never waits on it
            Cmd::Status(req) => {
                let (rpc, mtx) = (self.rpc.clone(), self.mtx.clone());
                tokio::spawn(async move {
                    let t0 = Instant::now();
                    let ss = [bs58::encode(&req.sig).into_string()];
                    let ata = pda::ata(&user, &req.mint, &pda::TOKEN_2022);
                    let (st, tk) = tokio::join!(call2(&rpc, "getSignatureStatuses", serde_json::json!([ss, { "searchTransactionHistory": false }])), tok_read(&rpc, &ata, "processed", 0));
                    let st = match st { Ok(v) => v["value"].get(0).filter(|x| !x.is_null()).map(|x| (x["slot"].as_u64().unwrap_or(0), x["err"].is_null())), Err(_) => None };
                    let tokens = match tk { crate::Tok::Amount(a, _) => Some(a), crate::Tok::Closed(_) => Some(0), crate::Tok::Unknown => None };
                    let _ = mtx.send(Msg::Ps(PsMsg::Status(Box::new(ps43::StatusRes { req: *req, st, tokens, ms: t0.elapsed().as_secs_f64() * 1e3 }))));
                });
            }
            // dip35 (log-only): the holders read on the runtime; its own in-flight count (FAM_INFLIGHT), never `tasks`
            Cmd::Fam(req) => {
                let Some(rpc) = self.l35.rpc.clone() else { return };
                let (mtx, inf) = (self.mtx.clone(), self.l35.inflight.clone());
                inf.fetch_add(1, Ordering::SeqCst);
                tokio::spawn(async move {
                    let (prog, read) = pslog35::fam_read(&rpc, &req.mint, req.t22).await;
                    let _ = mtx.send(Msg::Ps(PsMsg::Fam(Box::new(FamRes { req: *req, prog, read }))));
                    inf.fetch_sub(1, Ordering::SeqCst);
                });
            }
        }
    }

    /// dip34 exact exit: how long until the earliest open position's time-ms exit is due (zero = due now); None = no such exit pending
    /// (no position, the exit is off, or --presend-live-exact-exit off). The engine loop waits at most this long for the feed
    pub fn next_exit_in(&self) -> Option<Duration> {
        // dip43 B6: a position's own ms timer (off: cfg.exit_ms for every position, dip42)
        if !self.cfg.exact_exit || (self.cfg.exit_ms == 0 && self.cfg.b43.exit_ab.is_none()) { return None; }
        self.pos.values().filter(|p| p.exit.is_none()).filter_map(|p| { let ms = self.b43_exit_ms(p.pid); (ms > 0).then(|| Duration::from_millis(ms).saturating_sub(p.opened.elapsed())) }).min()
    }

    /// the clock: windows end, positions' time exits, attempts never seen, landing records whose tape is complete. `first`: the
    /// first sighting of a signature on any feed (sig8 -> rx ns, feed), when the caller has it
    pub fn tick(&mut self, slot_now: u64, first: Option<&FxHashMap<u64, (u64, u16)>>) {
        // dip39: the bot depth book's prune and its list's reload check (nothing with it off)
        if self.bd.is_some() { self.bd_tick(slot_now); }
        // dip41: the dumper ledger's prunes and its state (nothing with it off)
        if self.wd.is_some() { self.wd_tick(slot_now); }
        // dip42: FAM2's prune (nothing with it off)
        if self.f2.is_some() { self.f2_tick(slot_now); }
        // dip36: the blocklist's reload check (a stat every ~10 s; nothing without the flag)
        if let Some(r) = self.bl.as_mut().and_then(|b| b.check(false)) {
            self.line(format!("  PRESEND LIVE BLOCKLIST {} {}", if r["ok"] == true { "reloaded:" } else { "NOT reloaded (the last good list stays):" }, r));
            self.rec(r);
            // dip37c: a new list -> every armed window's listed holder again
            let ms: Vec<Pk> = self.armed.keys().copied().collect();
            for m in ms { self.bl_send_refresh(&m, None); }
        }
        // dip24: the rolling 24 h fee budget (a paused sender resumes when the old fees roll out)
        if self.fee_paused || !self.fee_q.is_empty() { self.fee_roll(); }
        self.drain_atts();
        let now = Instant::now();
        // windows: the last slot passed / the whale sold 30 ms ago
        let ends: Vec<(u64, &'static str)> = self.wins.values().filter(|w| w.disarmed.is_none())
            .filter_map(|w| if slot_now > w.en_slot { Some((w.id, "expired")) } else if w.stop_at.is_some_and(|t| now >= t) { Some((w.id, "whale_sold")) } else { None }).collect();
        for (id, why) in ends {
            // dip26: a re-arm window's 30 ms stop has its own reason (whale_dump / no_holder); T2 windows unchanged
            let why = if why == "whale_sold" { self.rearm_stop_why(id).unwrap_or(why) } else { why };
            self.disarm(id, why);
        }
        // dip20 QUIET: the preload's answer, the stop's decisions (once per slot), housekeeping. AFTER the regular ends: a window due to
        // end now (a late tick: a stalled feed) ends as it would without QUIET, the stop only acts on a window still running
        if self.qt.is_some() { self.quiet_tick(slot_now); }
        // dip23 v2: tokens idle for 120 s leave the ring (at most once per 10 s of feed time)
        if let Some(v) = self.v2.as_mut() { v.sweep(); }
        // positions: time exit at entry slot + exit_slots; the wall-clock backstop (the feed stalled)
        // dip43 A2: the backstop is dip42's (exit_slots x 400 + 3000 ms) unless the dead-man is live (x 215 + 600); the dead-man sell during a
        // long blind episode (live) / its would-records (log)
        let wall = self.wall43();
        let due: Vec<(Pk, &'static str)> = self.pos.values().filter(|p| p.exit.is_none()).filter_map(|p| {
            // dip43 B6: the position's ms timer (off: cfg.exit_ms, dip42); A2: the wall backstop (dead-man live only)
            time_exit_due_w(slot_now, p.land.0, self.cfg.exit_slots, p.opened.elapsed().as_millis() as u64, self.b43_exit_ms(p.pid), wall).map(|w| (p.mint, w))
        }).collect();
        for (m, why) in due { self.exit(&m, why, slot_now, f64::NAN, arbx::feeds::clock::now_ns()); }
        if self.d43.blind.is_some() { self.deadman43(slot_now); }
        if !self.pos.is_empty() && !self.d43.deadman_live && self.d43.blind.is_some() {
            let w: Vec<(u64, Pk, u64)> = self.pos.values().filter(|p| p.exit.is_none()).map(|p| (p.pid, p.mint, p.opened.elapsed().as_millis() as u64)).collect();
            for (pid, m, ms) in w { self.wall_would43(pid, &m, ms); }
        }
        // dip43 B3: lot 2 of the lots exits whose slot came; the control file's "exit_lots" (nothing without --presend-live-exit-lots)
        if self.cfg.b43.lots.is_some() { self.b43_tick(slot_now); }
        // attempts not seen by their deadline + 3 slots (or 6 s on the wall clock: the feed may be down)
        while let Some(&(dl, sig, at)) = self.order.front() {
            if !(slot_now > dl + 3 || at.elapsed() > Duration::from_secs(6)) { break; }
            self.order.pop_front();
            let Some((att, done)) = self.atts.get_mut(&sig) else { continue };
            if *done { continue; }
            *done = true;
            let att = att.clone();
            self.resolve(&att, "unseen");
            // dip43 A8 (--presend-live-acct on): its fee booked as a failed try's (the run's own records keep fee 0)
            self.acct_unseen43(&att);
            self.lands.push(Land { att, res: "unseen".into(), err: String::new(), fee: 0, slot: 0, idx: None, t_rx: 0, at: now });
        }
        // landing records once the tape around them is complete (2 slots later, or 2 s)
        if !self.lands.is_empty() {
            let mut keep = Vec::new();
            for l in std::mem::take(&mut self.lands) {
                if l.res == "unseen" || slot_now >= l.slot + 2 || l.at.elapsed() > Duration::from_secs(2) { let mut r = self.land_rec(&l, first); self.land_rec43(&mut r, &l.att.sig); self.rec(r); } else { keep.push(l); }
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
        // dip37: the whale ledger's state, every ~10 min (nothing without it)
        self.wh_tick(slot_now);
        // dip37: the holder ledger's state and the ledgers' control file (nothing without them)
        self.hl_tick(slot_now);
        // dip38 (log-only): housekeeping and the ledgers' saves (nothing without its flags)
        self.l38_tick(slot_now);
        // dip32: the creator state, every ~10 min (written off the event loop)
        if let Some(p) = self.cfg.cr_state.clone() {
            if slot_now >= self.cr_saved + CR_SAVE_SLOTS {
                if self.cr_saved > 0 {
                    let m = self.sh.cr.lock().unwrap().clone();
                    std::thread::spawn(move || { if let Err(e) = cr_save(&m, &p) { eprintln!("DIP PRESEND LIVE CREATOR GATE: NOT saved to {p}: {e:#}"); } });
                }
                self.cr_saved = slot_now;
            }
        }
        // forget finished windows, old attempts, idle tapes
        let done: Vec<u64> = self.wins.values().filter(|w| w.disarmed.is_some() && w.checked && w.resolved >= w.sent).map(|w| w.id).collect();
        for id in done { self.wins.remove(&id); self.acct_forget43(id); }
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
        // dip26 RE-ARM: the waiting windows whose position / token account cleared arm now (nothing without it)
        if self.rm.is_some() { self.rearm_tick(slot_now); }
        // dip43: papers, shadows, the book's retire, the control file's dip43 keys (each nothing with its flag off)
        self.tick43(slot_now);
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
        // dip26: a re-arm window's attempt says so (T2 attempts: dip25's record)
        if self.rearm_w(a.w) { j["kind"] = "rearm".into(); }
        // dip37: only with the fee A/B on
        if let Some(f) = &a.fa { f.put(&mut j, a.tip); }
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
        // dip37: a landed try's slot, every trade of the mint in it (full addresses: the rivals' in-slot order); only with the A/B on
        if a.fa.is_some() && (l.res == "ok" || l.res == "6042") {
            j["slot_tr"] = psfeeab::slot_tr(&v, l.slot, idx).into();
        }
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

    /// dip34 CR-EARNBACK (log-only): remember a cr_loss-skipped T2 trigger (signature) for the shadow's window on it
    fn ce_note(&mut self, sig: String, creator: Pk, mint: Pk, t: u64) {
        let ce = &mut self.ce;
        if ce.skipped.len() >= CE_MAX { ce.skipped.retain(|_, v| v.2.saturating_add(CE_KEEP_NS) >= t); }
        if ce.skipped.len() >= CE_MAX { ce.full += 1; return; }
        ce.skipped.insert(sig, (creator, mint, t));
    }

    /// dip34 CR-EARNBACK (log-only; nothing without --presend-live-cr-earn-log): every SHADOW record of a tx. A presend_arm on a
    /// cr_loss-skipped trigger is followed; its row c fill gives sol_in; its row c exit credits K x net_cheap x (live size / sol_in)
    /// to the creator's paper column (ps / pn) and writes presend_live_cr_paper; a window that ends without a row c fill is dropped.
    /// The creator gate's decision never reads the paper column
    pub fn on_shadow_rec(&mut self, rec: &serde_json::Value) {
        // dip36 (log-only): the shadow's row c for FP-NOBOT's s_* inputs (nothing without the flag)
        if self.fp.is_some() { self.fpnb_shadow(rec); }
        // dip37 --presend-live-wh-learn paper: a wh_loss-skipped trigger's row c into the whale's ledger (nothing without it)
        self.wh_on_shadow(rec);
        if self.cfg.cr_earn <= 0.0 { return; }
        let Some(w) = rec["w"].as_u64() else { return };
        match rec["ev"].as_str() {
            Some("presend_arm") => {
                let Some(sig) = rec["sig"].as_str() else { return };
                if !self.ce.skipped.contains_key(sig) { return; }
                if self.ce.w.len() >= CE_MAX { self.ce.full += 1; return; }
                self.ce.w.insert(w, (sig.to_string(), None));
            }
            Some("presend_fill") => {
                if rec["row"].as_str().unwrap_or("c") != "c" { return; }
                if let Some(e) = self.ce.w.get_mut(&w) { if e.1.is_none() { e.1 = rec["entry"]["sol_in"].as_f64().filter(|x| *x > 0.0); } }
            }
            Some("presend_disarm") => {
                if self.ce.w.get(&w).is_some_and(|e| e.1.is_none()) { if let Some((sig, _)) = self.ce.w.remove(&w) { self.ce.skipped.remove(&sig); } }
            }
            Some("presend_exit") => {
                if rec["row"] != "c" { return; }
                let Some((sig, sol_in)) = self.ce.w.remove(&w) else { return };
                let Some((creator, mint, _)) = self.ce.skipped.remove(&sig) else { return };
                let Some(sol_in) = sol_in else { return };
                let net = rec["net_cheap"].as_f64().or_else(|| rec["pnl"].as_f64()).unwrap_or(0.0);
                let credit = (self.cfg.cr_earn * net * self.cfg.spend as f64 / sol_in * 1e9).round() as i64;
                let (n, sum, ps, pn, trade) = {
                    let mut g = self.sh.cr.lock().unwrap();
                    let h = g.entry(creator).or_default();
                    h.ps += credit;
                    h.pn += 1;
                    (h.n, h.sum, h.ps, h.pn, h.earn_trade(self.cfg.cr_loss_n, self.cfg.cr_loss))
                };
                self.ce.credits += 1;
                self.ce.credit_sum += credit;
                self.rec(serde_json::json!({"ev": "presend_live_cr_paper", "creator": b58(&creator), "mint": b58(&mint), "sig": sig, "w": w, "net_cheap": net,
                    "sol_in": sol_in, "k": self.cfg.cr_earn, "credit": credit as f64 / 1e9, "n": n, "sum": sum as f64 / 1e9, "ps": ps as f64 / 1e9, "pn": pn, "trade": trade}));
                self.line(format!("  PRESEND LIVE CREATOR EARN (log only) {} creator {} | shadow {:+.4} SOL -> credit {:+.4} | ledger {:+.4} over {} + paper {:+.4} ({}) -> {}",
                    b58(&mint), &b58(&creator)[..8], net, credit as f64 / 1e9, sum as f64 / 1e9, n, ps as f64 / 1e9, pn, if trade { "would trade" } else { "still blocked" }));
            }
            _ => {}
        }
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
        // dip26: the re-arm's part last ("" without it)
        let qs = self.quiet_status() + &self.v2_status() + &self.fee_status() + &self.rearm_status() + &self.ann_status() + &self.breaker_status() + &self.cr_status() + &self.wh_status() + &self.hl_status() + &self.bl_send_status() + &self.fp.as_ref().map(|f| f.status()).unwrap_or_default()
            + &self.fab.as_ref().map(|f| f.status()).unwrap_or_default() + &self.l38_status() + &self.s1_status() + &self.bd_status() + &self.wd_status()
            + &self.f2_status() + &self.q1.as_ref().map(|q| q.status()).unwrap_or_default() + &self.status43() + &self.b43_status();
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

    /// dip27's part of the status line, LAST ("" without --presend-live-ann on; the lone-whale skips are in the skips map)
    /// dip32 the creator gate's part of the status line ("" when off)
    fn cr_status(&self) -> String {
        if !self.cfg.cr_on() { return String::new(); }
        let sk = |w: &str| self.st.skips.get(w).copied().unwrap_or(0);
        let earn = if self.cfg.cr_earn > 0.0 { format!(", earn-log credits {} ({:+.3} SOL)", self.ce.credits, self.ce.credit_sum as f64 / 1e9) } else { String::new() };
        format!(" | CREATORS {}: skips loss {} unfollowed {}{earn}", self.sh.cr.lock().unwrap().len(), sk("cr_loss"), sk("cr_unfollowed"))
    }

    /// dip31 the circuit breaker's part of the status line ("" when off)
    fn breaker_status(&self) -> String {
        if !self.cfg.breaker.on() { return String::new(); }
        let left = self.sh.brk_until.load(Ordering::Relaxed).saturating_sub(arbx::fast::mono_ns());
        format!(" | BREAKER {}: trips {}{}", self.cfg.breaker.spec(), self.sh.brk_trips.load(Ordering::Relaxed),
            if left > 0 { format!(", PAUSED {:.1} min more", left as f64 / 60e9) } else { String::new() })
    }

    fn ann_status(&self) -> String {
        if !self.cfg.ann { return String::new(); }
        format!(" | ANN (log-only): ctx85 would-skip fills {} | st-safe would-block fills {} | group-risk would-block fills {} | landing-guard would-fail fills {} | hold clocks {} wallets",
                self.st.ann_ctx85, self.st.ann_st, self.st.ann_grp, self.st.ann_guard, self.det.clocks())
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
        // dip37: the whale ledger for the next run (and its counts for run_end)
        let whj = self.wh_finish();
        let hlj = self.hl_finish();
        // dip32: the creator histories for the next run
        if let Some(p) = self.cfg.cr_state.clone() {
            let m = self.sh.cr.lock().unwrap().clone();
            match cr_save(&m, &p) {
                Ok(n) => self.line(format!("  PRESEND LIVE CREATOR GATE: {n} creators saved to {p}")),
                Err(e) => self.line(format!("  PRESEND LIVE CREATOR GATE: NOT saved to {p}: {e:#}")),
            }
        }
        // dip28: the hold clocks for the next run (after the stop: no trade waits on it)
        if let Some(p) = self.cfg.holds_state.clone() {
            match holds_save(&self.det, &p, slot_now) {
                Ok(n) => self.line(format!("  PRESEND LIVE HOLD CLOCKS: {n} wallets saved to {p}")),
                Err(e) => self.line(format!("  PRESEND LIVE HOLD CLOCKS: NOT saved to {p}: {e:#}")),
            }
        }
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
        // dip26: only with the re-arm on (its realized split is completed in run_end once the realized lookups are in: dipmode)
        if let Some(j) = self.rearm_json() { fin["rearm"] = j; }
        // dip34: only with a log flag on
        if let Some(j) = self.l34_json() { fin["dip34_log"] = j; }
        // dip35: only with the fam log on
        if let Some(j) = self.l35_json() { fin["dip35_log"] = j; }
        // dip36: only with the FP-NOBOT log on / the blocklist
        if let Some(f) = self.fp.as_mut() { fin["dip36_fpnb"] = f.finish(); }
        if let Some(j) = whj { fin["wh_ledger"] = j; }
        if let Some(j) = hlj { fin["hl_ledger"] = j; }
        if let Some(b) = &self.bl {
            fin["blocklist"] = b.json();
            // dip37c: the per-send check's counts (only with it)
            if self.cfg.blocklist_send {
                let a = |x: &[AtomicU64; 2]| serde_json::json!({"t2": x[0].load(Ordering::Relaxed), "rearm": x[1].load(Ordering::Relaxed)});
                fin["blocklist"]["send"] = serde_json::json!({"live": self.sh.bl_send_live.load(Ordering::Relaxed), "withheld": a(&self.sh.bl_withheld), "would": a(&self.sh.bl_would)});
            }
        }
        // dip37: only with the fee A/B on (its realized part is completed in run_end once the realized lookups are in: dipmode)
        if let Some(f) = &self.fab { fin["fee_ab"] = f.json(); }
        // dip38: only with its logs on (the chains / ledgers saved)
        if let Some(j) = self.l38_finish() { fin["dip38_log"] = j; }
        if let Some(j) = self.s1_finish() { fin["s1"] = j; }
        if let Some(j) = self.bd_finish() { fin["botdepth"] = j; }
        if let Some(j) = self.wd_finish() { fin["widedumper"] = j; }
        // dip42: only with them on (Q1: its thread saves the wallet history and answers)
        if let Some(j) = self.f2_finish() { fin["fam2"] = j; }
        if let Some(j) = self.q1.as_mut().and_then(|q| q.finish()) { fin["q1"] = j; }
        // dip43: only when an option is given / something happened (the exit shadows still open are written)
        if let Some(j) = self.finish43() { fin["dip43"] = j; }
        // dip43 B: only with an item on
        if let Some(j) = self.b43_finish() { fin["b43"] = j; }
        fin
    }

    /// dip37: the fee A/B's realized P&L per arm (x group) once the realized lookups are in, and its summary line (None with it off)
    pub fn fee_ab_end(&self) -> Option<(serde_json::Value, String)> { self.fab.as_ref().map(|f| (f.realized_json(), f.end_line())) }

    /// dip37: a window's fee arm at its arm (None with the A/B off; the arm is remembered for its positions' realized lookups)
    fn fab_assign(&mut self, id: u64) -> Option<u8> {
        let fs = self.fab.as_mut()?;
        let a = self.cfg.fab.assign(id, arbx::feeds::clock::now_ns());
        fs.armed[a as usize] += 1;
        fs.wins.insert(id, a);
        Some(a)
    }

    /// dip37: an arm record's fee fields: the window's arm and that arm's values (B's apply only on its listed leaders; nothing when off)
    fn fab_arm_rec(&self, r: &mut serde_json::Value, arm: Option<u8>) {
        let Some(a) = arm else { return };
        let f = &self.cfg.fab;
        r["fee_arm"] = psfeeab::ARMS[a as usize].into();
        if a == 1 {
            r["cu_price"] = f.cu_price.into(); r["cu_limit"] = f.cu_limit.unwrap_or(self.cfg.cu_limit).into(); r["tip"] = f.tip.or(self.cfg.tip).into();
            r["ab_clients"] = f.clients.clone().into();
        } else {
            r["cu_price"] = self.cfg.cu_price.into(); r["cu_limit"] = self.cfg.cu_limit.into(); r["tip"] = self.cfg.tip.into();
        }
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
        let fab_on = cfg.fab.on;
        let h2_on = cfg.m2seen_on();
        // dip26: the re-arm as its flags say
        let rearm = cfg.rearm.on.then(|| psrearm::Rearm::new(cfg.rearm.clone()));
        let l34 = L34::new(&cfg);
        let (out, orx) = crossbeam_channel::unbounded();
        // dip36: FP-NOBOT inline (every message handled at once; no thread, no tap)
        let fp = pslog36::Fp::start(&cfg, user, &out, true).unwrap();
        let bl = cfg.blocklist.as_deref().map(|p| psblock::Blocklist::load(p).unwrap());
        // dip39: the bot depth gate's list (fail open on a bad one, as a run)
        let bd = cfg.bd.map(|g| psbd::Bd::open(g, cfg.bd_list.as_deref(), cfg.bd_state.as_deref(), &user));
        // dip41: the dumper ledger + the WIDE-DUMPER tier (as a run)
        let wd = cfg.dl_on.then(|| psdl::Wd::open(cfg.wd, cfg.wd_live, cfg.qf, cfg.qf_filt, cfg.qf_live, cfg.wd_size, cfg.dl_state.as_deref()));
        // dip42: FAM2's book; Q1 inline (every message handled at once; no thread)
        let f2 = cfg.f2.clone().map(psfam2::Fam2::new);
        let q1 = cfg.q1.clone().map(|c| psq1::Q1Tap::start(c, user, &out, true));
        // dip38: the anti-bait log with the tests' queue (no task, no RPC)
        let l38 = pslog38::L38::new(&cfg, None).unwrap();
        let (atx, arx) = crossbeam_channel::unbounded();
        let (mtx, _) = tokio::sync::mpsc::unbounded_channel();
        let sh = Arc::new(Shared { wins: Mutex::new(Vec::new()), stop: AtomicBool::new(false), pause_reactive: AtomicBool::new(false), pause_pos: AtomicBool::new(false), pause_fee: AtomicBool::new(false),
            brk_until: AtomicU64::new(0), brk_losses: Mutex::new(VecDeque::new()), brk_trips: AtomicU64::new(0), bl_send_live: AtomicBool::new(true), bl_withheld: Default::default(), bl_would: Default::default(), bd: Default::default(), cr: Mutex::new(FxHashMap::default()), wh: Mutex::new(Default::default()), hl: Mutex::new(FxHashMap::default()),
            slot: AtomicU64::new(0), seq: AtomicU64::new(0), sent: AtomicU64::new(0), dry: AtomicU64::new(0), exited: AtomicBool::new(true), skips: Mutex::new(FxHashMap::default()),
            build_us: Mutex::new(Ring::default()), g43: Default::default() });
        sh.bd.live.store(cfg.bd_live, Ordering::SeqCst);
        let mut det = pl::Detector::new(cfg.whale_pct);
        // dip27: the hold clocks only with the annotations on (as a run)
        det.track = cfg.ann;
        let s1 = pss1::S1St::new(&cfg);
        (PsLive { cfg, det, wins: FxHashMap::default(), armed: FxHashMap::default(), wid: 0, sh, arx, atts: FxHashMap::default(), order: VecDeque::new(), lands: Vec::new(),
            tapes: FxHashMap::default(), pos: FxHashMap::default(), free_at: FxHashMap::default(), last_deadline: FxHashMap::default(), launches: FxHashMap::default(), last_sweep: 0, cr_saved: 0, cur_r41: false, ce: CrEarn::default(),
            checks: 0, par: FxHashMap::default(), st: Stats::default(), out, thread: None, user, key: Arc::new(SigningKey::from_bytes(&[1u8; 32])),
            rpc: Arc::new(rpc::Rpc::new("http://127.0.0.1:9".into())), path: None, mtx, allow_holder: false, stopped: None, stopped_at: None,
            // dip19: the chain work is queued: a test answers it (no RPC, no send, no Telegram)
            q: Some(Vec::new()), pid: 0, atas: FxHashMap::default(), quiet: FxHashMap::default(), ends: FxHashMap::default(), retry: Vec::new(), reading: FxHashMap::default(),
            tasks: Arc::new(AtomicU64::new(0)),
            // dip20: QUIET as its flags say, the arm rule on from the start (no warm-up: a test sets start_ns / warm_ns), the feed's slot
            // clock; the tests set its lists
            qt: cfg_quiet.on().then(|| { let mut q = Quiet::new(&cfg_quiet, &std::collections::HashSet::new(), FxHashSet::default(), 0, false); q.warm_ns = 0; q }),
            v2: v2_log.then(pq::V2Ring::new), fee_q: VecDeque::new(), fee_24h: 0, fee_paused: false, fee_pauses: 0, last_t: 0, rm: rearm, l34, l35: L35::default(), fp, bl,
            fab: fab_on.then(psfeeab::FabSt::default), whs: pswh::WhSt::default(), h2: h2_on.then(psh2::H2::default), hls: pshl::HlSt::default(), l38, s1, bd, wd, f2, q1, d43: Default::default(),
            b43: ps43_b::B43St::default() }, atx, orx)
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

// dip26 (10-29 PKT): the LIVE RE-ARM (--presend-live-rearm on; off by default = dip25, golden)
#[cfg(test)]
#[path = "dip26_tests.rs"]
mod dip26_tests;

// dip34 (11-03 PKT): CR-EARNBACK, the creator ledger's paper credits (--presend-live-cr-earn-log; log-only, off by default = dip33)
#[cfg(test)]
#[path = "dip34_cr_tests.rs"]
mod dip34_cr_tests;

// dip34 (11-04 PKT): the log-only seen / eqgrp / q4 annotations and ann.cr_hold (pslog34.rs; off by default = dip33's records)
#[cfg(test)]
#[path = "dip34_log_tests.rs"]
mod dip34_log_tests;

// dip35 (11-04 PKT): the log-only fam holders read (pslog35.rs; off by default = dip34's records, nothing spawned)
#[cfg(test)]
#[path = "dip35_fam_tests.rs"]
mod dip35_fam_tests;

// dip36 (11-05 PKT): the log-only FP-NOBOT (pslog36.rs, src/fpnb.rs; off by default = dip35's records, no thread)
#[cfg(test)]
#[path = "dip36_fpnb_tests.rs"]
mod dip36_fpnb_tests;

// dip36 (11-05 PKT): the LIVE wallet blocklist (psblock.rs; off by default)
#[cfg(test)]
#[path = "dip36_blocklist_tests.rs"]
mod dip36_blocklist_tests;

// dip37 (11-04): the per-window priority-fee A/B on the pre-send attempts (psfeeab.rs; off by default = dip36's bytes and records)
#[cfg(test)]
#[path = "dip37_feeab_tests.rs"]
mod dip37_feeab_tests;

// dip37 (11-04): the LIVE whale / dumper loss ledger (pswh.rs) and the FP-NOBOT stale hold (pslog36.rs); off by default = dip36
#[cfg(test)]
#[path = "dip37_wh_tests.rs"]
mod dip37_wh_tests;

// dip37 (11-05): the HYBRID-2 inputs (psh2.rs: nd / m2max log, the m2_unseen gate); off by default = dip36
#[cfg(test)]
#[path = "dip37_h2_tests.rs"]
mod dip37_h2_tests;

// dip38 (11-05): the blocklist's launcher match (LIVE) and the anti-bait log (launcher, funding resolver, INSIDER / FAMILY / ledgers, SHAPE)
#[cfg(test)]
#[path = "dip38_tests.rs"]
mod dip38_tests;
// dip38 (11-05): PSM12-S1 arm filter, log only (pss1.rs); the live gate off by default
#[cfg(test)]
#[path = "dip38_s1_tests.rs"]
mod dip38_s1_tests;
// dip39 (11-05): the BOT DEPTH pre-send gate (psbd.rs); off by default = dip38
#[cfg(test)]
#[path = "dip39_bd_tests.rs"]
mod dip39_bd_tests;

// dip41 (11-06 PKT): the whale fast-dump ledger + the WIDE-DUMPER tier (--presend-live-dumper-ledger on; off by default = dip39)
#[cfg(test)]
#[path = "dip41_wd_tests.rs"]
mod dip41_wd_tests;

// dip42 (11-06 PKT): FAM2 (the 2NUM family on our windows' records) and the Q1 shadow log; both LOG ONLY, off by default = dip41
#[cfg(test)]
#[path = "dip42_tests.rs"]
mod dip42_tests;
// dip43 Builder A (11-10 PKT): the feed-stall watchdog, blind-fill recovery / dead-man, control keys, accounting and shadows; off / log by
// default = dip42 (golden)
#[cfg(test)]
#[path = "dip43a_tests.rs"]
mod dip43a_tests;

// dip43 BUILDER B (11-10): cap / re-route / single token / skip clients, fee tier, two-lot exit, cheap timer sells, window start
// (ps43_b.rs); off by default = dip42
#[cfg(test)]
#[path = "dip43_b_tests.rs"]
mod dip43_b_tests;

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
            lim: 1.0, min_out: 1, p_sign: 1.0, sign_pos: (100, 0, 0), t_send: 0, roles, tip: 0, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None }).unwrap();
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
    /// dip32 the creator gate: the flags (parse, refusals, start record), the history (sum over all, the last CR_KEEP kept), QUIET3-B
    /// (the last <= K known before the trigger within H hours, all not followed), the gate's order (loss first), FOLLOWED on a tape
    /// (not us / the whale / the re-arm's holders; after our first buy, up to our last sell landing) and the state file round trip
    #[test]
    fn presend_live_dip32_creator_gate() {
        let p = arbx::presend::Params { whale_pct: 6.0, ..Default::default() };
        let c = Cfg::from_argv(&with(&["--presend-live-cr-unfollowed", "3:24", "--presend-live-cr-loss", "2:0.05", "--presend-live-creator-state", "/tmp/x.json", "--presend-live-f3-log"]),
            &p, true, 1_000_000_000).unwrap().unwrap();
        assert!(c.cr_on() && c.f3_log && c.cr_unf == Some((3, 24 * 3_600_000_000_000)) && (c.cr_loss_n, c.cr_loss) == (2, 50_000_000));
        assert!(c.json()["cr_unfollowed"] == "3:24" && c.json()["cr_loss"] == "2:0.05" && c.json()["creator_state"] == "/tmp/x.json" && c.json()["f3_log"] == true);
        let cl = Cfg::from_argv(&with(&["--presend-live-cr-loss", "2:0.05"]), &p, true, 1_000_000_000).unwrap().unwrap();
        assert!(cl.cr_on() && cl.cr_unf.is_none(), "the ledger alone");
        let c0 = Cfg::from_argv(&v(&BASE), &p, true, 1_000_000_000).unwrap().unwrap();
        assert!(!c0.cr_on() && !c0.f3_log && ["cr_unfollowed", "cr_loss", "creator_state", "f3_log"].iter().all(|k| c0.json().get(*k).is_none()), "off: dip31's start record");
        for (f, x) in [("--presend-live-cr-unfollowed", "0:24"), ("--presend-live-cr-unfollowed", "3"), ("--presend-live-cr-unfollowed", "3:200"), ("--presend-live-cr-loss", "2:0"),
            ("--presend-live-cr-loss", "2:9"), ("--presend-live-cr-loss", "0:0.05"), ("--presend-live-cr-loss", "0.05"), ("--presend-live-cr-loss", "x:y")] {
            assert!(Cfg::from_argv(&set(f, x), &p, true, 1_000_000_000).is_err(), "{f} {x}");
        }
        assert!(Cfg::from_argv(&set("--presend-live-creator-state", "/tmp/x.json"), &p, true, 1_000_000_000).is_err(), "the state needs a rule");
        // the tag wallets (log-only; need the f3 log), the program constant
        let ct = Cfg::from_argv(&with(&["--presend-live-f3-log", "--presend-live-tag-wallets", "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN,8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk"]),
            &p, true, 1_000_000_000).unwrap().unwrap();
        assert_eq!(ct.tag_wallets.len(), 2);
        assert!(ct.json()["tag_wallets"][1] == "8PgC4ngpx6zUG3KFQAQHqSeePDFA7kGyEaA2yMoZ4HUk" && c0.json().get("tag_wallets").is_none());
        assert!(Cfg::from_argv(&set("--presend-live-tag-wallets", "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN"), &p, true, 1_000_000_000).is_err(), "needs the f3 log");
        assert!(tag_parse("notawallet").is_err() && tag_parse("").is_err());
        assert_eq!(b58(&P41), "41Pr4XqEcmgV1PqZF9yccpuFvxF7PpKLGfTD9jWJBn1q");
        // dip33 QUIET3-A live: needs its inputs (QUIET v2 log + QUIET skip); off by default
        assert!(!c0.q3a_live && c0.json().get("quiet3a").is_none());
        assert!(Cfg::from_argv(&set("--presend-live-quiet3a", "on"), &p, true, 1_000_000_000).is_err(), "no inputs: refused");
        // the history
        let h_ns = 24 * 3_600_000_000_000u64;
        let mut h = CrHist::default();
        assert!(!h.unfollowed(100, 3, h_ns), "no history: never");
        h.add(10, -30_000_000, false);
        assert!(h.unfollowed(11, 3, h_ns) && !h.unfollowed(10, 3, h_ns), "known before the trigger only");
        assert!(!h.unfollowed(10 + h_ns + 1, 3, h_ns), "older than H: forgotten");
        h.add(20, 40_000_000, true);
        assert!(!h.unfollowed(30, 3, h_ns), "one of the last 3 followed");
        h.add(30, -20_000_000, false); h.add(40, -20_000_000, false); h.add(50, -20_000_000, false);
        assert!(h.unfollowed(60, 3, h_ns) && !h.unfollowed(60, 4, h_ns), "the last 3 not followed; the last 4 hold a follow");
        for i in 0..20 { h.add(100 + i, 1, true); }
        assert_eq!((h.h.len(), h.n, h.sum), (CR_KEEP, 25, -50_000_000 + 20), "sum and count over all, the last CR_KEEP kept");
        // the gate (loss first, then unfollowed), its record
        let sh = Shared { wins: Mutex::new(Vec::new()), stop: AtomicBool::new(false), pause_reactive: AtomicBool::new(false), pause_pos: AtomicBool::new(false),
            pause_fee: AtomicBool::new(false), brk_until: AtomicU64::new(0), brk_losses: Mutex::new(VecDeque::new()), brk_trips: AtomicU64::new(0), bl_send_live: AtomicBool::new(true), bl_withheld: Default::default(), bl_would: Default::default(), bd: Default::default(), cr: Mutex::new(FxHashMap::default()), wh: Mutex::new(Default::default()), hl: Mutex::new(FxHashMap::default()),
            slot: AtomicU64::new(0), seq: AtomicU64::new(0), sent: AtomicU64::new(0), dry: AtomicU64::new(0), exited: AtomicBool::new(true),
            skips: Mutex::new(FxHashMap::default()), build_us: Mutex::new(Ring::default()), g43: Default::default() };
        let (ca, cb, cc) = ([1u8; 32], [2u8; 32], [3u8; 32]);
        {
            let mut g = sh.cr.lock().unwrap();
            g.entry(ca).or_default().add(9, -10_000_000, true);
            g.entry(ca).or_default().add(10, -150_000_000, true);
            g.entry(cb).or_default().add(10, -20_000_000, false);
            g.entry(cc).or_default().add(10, 80_000_000, false);
            g.entry(cc).or_default().add(11, 20_000_000, true);
        }
        assert_eq!(cr_gate(&sh, &c, Some(ca), 20).0, Some("loss"), "2 positions, -0.16");
        assert!(cr_gate(&sh, &c, Some(cb), 20).1.unwrap()["unf3"] == true && cr_gate(&sh, &c, Some(ca), 20).1.unwrap()["unf3"] == false, "QUIET3-B logged");
        assert_eq!(cr_gate(&sh, &cl, Some(cb), 20).0, None, "1 position: not the ledger's; unfollowed only logged");
        assert_eq!(cr_gate(&sh, &c, Some(cb), 20).0, Some("unfollowed"));
        assert_eq!(cr_gate(&sh, &c, Some(cc), 20).0, None);
        assert_eq!(cr_gate(&sh, &c, Some([9u8; 32]), 20), (None, None), "unknown creator");
        assert_eq!(cr_gate(&sh, &c, None, 20), (None, None));
        assert!(cr_gate(&sh, &c, Some(cb), 20).1.unwrap()["n"] == 1);
        // dip35 --presend-live-cr-log on: the verdict as "would", never a skip; off: no "would"
        let mut clog = c.clone(); clog.cr_log = true;
        let (w, j) = cr_gate(&sh, &clog, Some(ca), 20);
        assert!(w.is_none() && j.as_ref().unwrap()["would"] == "loss", "log-only: no skip, the verdict recorded");
        assert!(cr_gate(&sh, &clog, Some(cc), 20).1.unwrap().get("would").is_none(), "no verdict: no would");
        assert!(cr_gate(&sh, &c, Some(ca), 20).1.unwrap().get("would").is_none(), "live: no would field");
        // FOLLOWED on a tape
        let (us, whale, holder, other) = ([5u8; 32], [6u8; 32], [7u8; 32], [8u8; 32]);
        let tr = |u: Pk, buy: bool, s: u64, i: u32| pl::Trade { mint: [0; 32], s, i, j: 0, sig: [0; 64], user: u, buy, sol: 1, tok: 1, vsol: 1, vtok: 1, fbps: 0, cbps: 0, t_rx: 0 };
        let tape: VecDeque<pl::Trade> = [tr(us, true, 100, 5), tr(whale, true, 100, 9), tr(holder, true, 101, 1), tr(other, false, 101, 2), tr(us, false, 102, 3)].into_iter().collect();
        assert!(!followed(&tape, &us, Some(&whale), &[holder], (100, 5), (102, 3)), "only us, the whale, a holder and a sell");
        assert!(followed(&tape, &us, None, &[holder], (100, 5), (102, 3)), "the whale unknown: its buy counts");
        let mut t2 = tape.clone(); t2.push_back(tr(other, true, 102, 3));
        assert!(followed(&t2, &us, Some(&whale), &[holder], (100, 5), (102, 3)), "a buy at our last sell landing counts");
        let mut t3 = tape.clone(); t3.push_back(tr(other, true, 100, 4)); t3.push_back(tr(other, true, 102, 4));
        assert!(!followed(&t3, &us, Some(&whale), &[holder], (100, 5), (102, 3)), "before our buy / after our last sell: never");
        // the state file
        let path = std::env::temp_dir().join(format!("dip32-cr-{}.json", std::process::id()));
        let ps = path.to_str().unwrap();
        let m = sh.cr.lock().unwrap().clone();
        assert_eq!(cr_save(&m, ps).unwrap(), 3);
        assert_eq!(cr_load(ps).unwrap(), m);
        let _ = std::fs::remove_file(&path);
    }

    /// dip31 the circuit breaker: the flag's parse / refusals / start record, the trip rule (N losses of >= L within W, then a P pause;
    /// smaller losses, wins and old losses never count; the window empties at a trip) and the sender's gate during the pause
    #[test]
    fn presend_live_dip31_breaker() {
        let b = Breaker::parse("2:0.2:10:30").unwrap();
        assert_eq!(b, Breaker { n: 2, loss: 200_000_000, win_ns: 600_000_000_000, pause_ns: 1_800_000_000_000 });
        assert_eq!(b.spec(), "2:0.2:10:30");
        for s in ["2:0.2:10", "0:0.2:10:30", "11:0.2:10:30", "2:0:10:30", "2:1.5:10:30", "2:0.2:0:30", "2:0.2:10:0", "2:x:10:30"] { assert!(Breaker::parse(s).is_err(), "{s}"); }
        let p = arbx::presend::Params { whale_pct: 6.0, ..Default::default() };
        let c = Cfg::from_argv(&set("--presend-live-breaker", "1:0.15:10:30"), &p, true, 1_000_000_000).unwrap().unwrap();
        assert!(c.breaker.on() && c.json()["breaker"] == "1:0.15:10:30");
        let c0 = Cfg::from_argv(&v(&BASE), &p, true, 1_000_000_000).unwrap().unwrap();
        assert!(!c0.breaker.on() && c0.json().get("breaker").is_none(), "off: dip30's start record");
        assert!(Cfg::from_argv(&set("--presend-live-breaker", "2:0.2"), &p, true, 1_000_000_000).is_err());
        let sh = Shared { wins: Mutex::new(Vec::new()), stop: AtomicBool::new(false), pause_reactive: AtomicBool::new(false), pause_pos: AtomicBool::new(false),
            pause_fee: AtomicBool::new(false), brk_until: AtomicU64::new(0), brk_losses: Mutex::new(VecDeque::new()), brk_trips: AtomicU64::new(0), bl_send_live: AtomicBool::new(true), bl_withheld: Default::default(), bl_would: Default::default(), bd: Default::default(), cr: Mutex::new(FxHashMap::default()), wh: Mutex::new(Default::default()), hl: Mutex::new(FxHashMap::default()),
            slot: AtomicU64::new(0), seq: AtomicU64::new(0), sent: AtomicU64::new(0), dry: AtomicU64::new(0), exited: AtomicBool::new(true),
            skips: Mutex::new(FxHashMap::default()), build_us: Mutex::new(Ring::default()), g43: Default::default() };
        let m = 60_000_000_000u64;
        let t0 = 1_000 * m;
        assert_eq!(breaker_note(&sh, &b, -300_000_000, t0), None, "one big loss: not yet");
        assert_eq!(breaker_note(&sh, &b, -100_000_000, t0 + m), None, "a small loss never counts");
        assert_eq!(breaker_note(&sh, &b, 500_000_000, t0 + m), None, "a win never counts");
        assert_eq!(breaker_note(&sh, &b, -250_000_000, t0 + 11 * m), None, "the first big loss is out of the 10 min window");
        assert_eq!(breaker_note(&sh, &b, -200_000_000, t0 + 15 * m), Some(2), "two of >= 0.2 within 10 min: trips");
        assert_eq!((sh.brk_until.load(Ordering::SeqCst), sh.brk_trips.load(Ordering::SeqCst)), (t0 + 45 * m, 1));
        assert_eq!(breaker_note(&sh, &b, -200_000_000, t0 + 16 * m), None, "the window starts empty after a trip");
        assert_eq!(breaker_note(&Shared { brk_until: AtomicU64::new(0), ..sh }, &Breaker::default(), -900_000_000, t0), None, "off: never");
        // the sender's gate while the pause runs (mono clock), then not after it
        let sh2 = Shared { wins: Mutex::new(Vec::new()), stop: AtomicBool::new(false), pause_reactive: AtomicBool::new(false), pause_pos: AtomicBool::new(false),
            pause_fee: AtomicBool::new(false), brk_until: AtomicU64::new(arbx::fast::mono_ns() + 60 * m), brk_losses: Mutex::new(VecDeque::new()), brk_trips: AtomicU64::new(1), bl_send_live: AtomicBool::new(true), bl_withheld: Default::default(), bl_would: Default::default(), bd: Default::default(), cr: Mutex::new(FxHashMap::default()), wh: Mutex::new(Default::default()), hl: Mutex::new(FxHashMap::default()),
            slot: AtomicU64::new(0), seq: AtomicU64::new(0), sent: AtomicU64::new(0), dry: AtomicU64::new(0), exited: AtomicBool::new(true),
            skips: Mutex::new(FxHashMap::default()), build_us: Mutex::new(Ring::default()), g43: Default::default() };
        assert!(breaker_paused(&sh2));
        sh2.brk_until.store(arbx::fast::mono_ns().saturating_sub(1), Ordering::SeqCst);
        assert!(!breaker_paused(&sh2));
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
            "--presend-live-quiet-v2-log", "--presend-live-min-age-slots", "2", "--presend-live-lone-whale-slots", "50", "--presend-live-ann", "on",
            "--presend-live-deep-drop", "0.15", "--presend-live-holds-state", "/tmp/dip28-test-holds.json", "--presend-live-breaker", "2:0.2:10:30",
            "--presend-live-cr-unfollowed", "3:24", "--presend-live-cr-loss", "2:0.05", "--presend-live-creator-state", "/tmp/dip32-test-cr.json", "--presend-live-f3-log",
            "--presend-live-tag-wallets", "9pQQc1xyqwPzYdHztDHEYkgNucYWSQsZTrzNRzdCrRdN", "--presend-live-quiet3a", "off", "--presend-live-exact-exit", "on",
            "--presend-live-cr-earn-log", "0.5", "--presend-live-seen-log", "3", "--presend-live-eqgrp-log", "--presend-live-q4-log",
            "--presend-live-fam-log", "--presend-live-fam-thr", "26.825", "--presend-live-fam-rpc", "https://rpc.example", "--presend-live-cr-log", "off",
            "--presend-live-blocklist", "/root/dip/blocklist_ams.json", "--presend-live-blocklist-pct", "3"]);
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
        // dip27: the lone-whale window and the annotations (off by default; the window at most the recent buys kept)
        assert_eq!((c.lone_whale_slots, c.ann), (50, true));
        let c0 = Cfg::from_argv(&v(&BASE), &p, true, cap).unwrap().unwrap();
        assert_eq!((c0.lone_whale_slots, c0.ann), (0, false));
        assert!(c0.json().get("lone_whale_slots").is_none() && c0.json().get("ann").is_none(), "off: dip26's start record");
        assert!(Cfg::from_argv(&set("--presend-live-lone-whale-slots", "65"), &p, true, cap).unwrap_err().to_string().contains("lone-whale"));
        assert_eq!(Cfg::from_argv(&set("--presend-live-lone-whale-slots", "64"), &p, true, cap).unwrap().unwrap().lone_whale_slots, 64);
        assert!(Cfg::from_argv(&set("--presend-live-ann", "maybe"), &p, true, cap).is_err());
        // dip28: the deeper limit (deeper than the drop, <= 0.5) and the holds state (needs the annotations)
        assert_eq!((c.deep_drop, c.holds_state.as_deref()), (0.15, Some("/tmp/dip28-test-holds.json")));
        assert_eq!((c0.deep_drop, c0.holds_state.is_none()), (0.0, true));
        assert!(c0.json().get("deep_drop").is_none() && c0.json().get("holds_state").is_none(), "off: dip27's start record");
        for bad in ["0.10", "0.12", "0.6"] {
            assert!(Cfg::from_argv(&set("--presend-live-deep-drop", bad), &p, true, cap).unwrap_err().to_string().contains("deep-drop"), "{bad}");
        }
        assert!(Cfg::from_argv(&set("--presend-live-holds-state", "/tmp/x.json"), &p, true, cap).unwrap_err().to_string().contains("needs --presend-live-ann on"));
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
        // dip26 RE-ARM: its flags pass the start-up check (with --presend-live-rearm on); each needs --presend-live, a parameter needs
        // --presend-live-rearm on; numbers checked at the start; its size within the per-buy cap; off by default (dip25's config)
        let re = with(&["--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.4", "--presend-live-rearm-gap-slots", "20", "--presend-live-rearm-quiet-stop", "6:2",
            "--presend-live-rearm-r5-skip", "off"]);
        assert!(check_flags(&re).is_ok(), "{:?}", check_flags(&re));
        for f in RFLAGS { assert!(re.iter().any(|a| a == f), "{f} in the test line"); }
        let c = Cfg::from_argv(&re, &p, true, cap).unwrap().unwrap();
        assert_eq!((c.rearm.on, c.rearm.spend, c.rearm.gap, c.rearm.stop, c.rearm.r5_skip), (true, 400_000_000, 20, pq::QStop { n: 6, m: 2 }, false));
        assert!(!Cfg::from_argv(&v(&BASE), &p, true, cap).unwrap().unwrap().rearm.on, "off by default");
        for f in RFLAGS {
            let e = Cfg::from_argv(&v(&["snipe_engine", "--dip", "--presend-shadow", f, "on"]), &p, true, cap).unwrap_err().to_string();
            assert!(e.contains("needs --presend-live"), "{f}: {e}");
        }
        assert!(Cfg::from_argv(&with(&["--presend-live-rearm-gap-slots", "20"]), &p, true, cap).unwrap_err().to_string().contains("needs --presend-live-rearm on"));
        let e = Cfg::from_argv(&with(&["--presend-live-size-sol", "0.4", "--presend-live-rearm", "on", "--presend-live-rearm-size-sol", "0.6"]), &p, true, 500_000_000).unwrap_err().to_string();
        assert!(e.contains("REFUSED: --presend-live-rearm-size-sol 0.600 exceeds --max-sol"), "{e}");
        for (f, x) in [("--presend-live-rearm-gap-slots", "x"), ("--presend-live-rearm-gap-slots", "1.5"), ("--presend-live-rearm-size-sol", "abc")] {
            assert!(check_flags(&with(&["--presend-live-rearm", "on", f, x])).is_err(), "{f} {x}");
        }
        for (f, x) in [("--presend-live-rearm", "yes"), ("--presend-live-rearm-gap-slots", "61"), ("--presend-live-rearm-quiet-stop", "6")] {
            let mut a = with(&["--presend-live-rearm", "on"]);
            match a.iter().position(|y| y == f) { Some(i) => a[i + 1] = x.to_string(), None => { a.push(f.to_string()); a.push(x.to_string()); } }
            assert!(Cfg::from_argv(&a, &p, true, cap).is_err(), "{f} {x} should be refused");
        }
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
                        min_out: 1, p_sign: 1.0, sign_pos: (*s, *idx as u32, 0), t_send: *s * 1_000_000, roles, tip: 200_000, wst: "written", ob6: 0.0, grd: Grd::default(), fa: None, bd: None };
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

//! Alerts to Telegram (PLAN-ADDENDUM WP-20; MEASUREMENT §4.6 `alert_*` events, §4.8 status `alerts`, §4.51 "How alerts
//! read"), shared by `arbx run`, `arbx watchdog` and `arbx alert-test`.
//!
//! - **Never on the hot path.** A producer (the engine thread, a hot-runtime task, the recorder's event path, the
//!   executor's settlement) calls [`Alerts::raise`]: a level check, a dedup check under a lock tried without waiting (a
//!   lock still taken lets the alert through), a `try_send` into a bounded queue ([`Tuning::queue`]). Nothing wakes the
//!   sender (it looks every [`Tuning::tick`]), so no producer touches a waker's lock. A full queue drops the alert and
//!   counts it (`alerts.dropped_total`). Nothing a producer does waits, least of all on the network.
//! - **One sender task on rt_bg** ([`Alerts::start`]) posts `sendMessage` over HTTPS (parse_mode HTML): at most
//!   `rate_per_min` messages in any 60 s and one a second (per chat), bursts coalesced into one message (`coalesce_ms`),
//!   a 429 retried after the API's `retry_after` (later messages wait too), transport errors and 5xx after a backoff (at
//!   most [`Tuning::max_attempts`] tries), a message whose HTML the API refuses sent again as plain text.
//! - **Dedup** by key (`dedup_s`): a repeat inside the window is counted, and the next one sent says how many came in
//!   between. Transitions (down / up) form a family: a change suppressed by the dedup is held and sent when its window
//!   ends, unless the state went back, so what the owner read last is never wrong for longer than `dedup_s`.
//! - **Secrets.** The token and the chat id come from the environment (`token_env`, `chat_env`: the .env beside the
//!   config, or `--env-file`). They never appear in a log, a record, meta.json or an error: the sender's every text goes
//!   through [`telegram::redact`], which also strips reqwest's URLs. Missing variables turn the alerts off with one
//!   warning; never fatal.
//! - **Exit and crash.** At the end of `arbx run` the stop message and whatever is still queued go out from the main
//!   thread ([`on_exit`], at most [`EXIT_WAIT`]); a panic on the main thread (the engine's) sends a Critical alert from
//!   the panic hook ([`install_panic_hook`], at most [`CRASH_WAIT`]), and the exit sends it again if it did not go out.
//!   Both post from a thread of their own with its own runtime (they work wherever the panic happened and after the
//!   run's runtimes are gone), wait for the chat's rate when it fits, and put back what they could not send.
//! - **What raises alerts.** The recorder's events (a tap in `Recorder::event`, [`classify`]): the state stream down /
//!   up, a re-read that does not land, recorder drops, I/O errors, dead or stalled writers, disk-ladder steps, the
//!   chain fetch dead, Jito token failures and result-stream outages, a failed boot; the SendGate's changes with their
//!   reason (a watcher, [`Alerts::watch_gate`]); 503 and 429 storms ([`note_stream_error`] from the feeds, the RPC
//!   registry's rate-limited counts); from the status line ([`Alerts::start_monitor`]): a stale blockhash, the
//!   executor's failed-fee cap (the budget floor), a low balance, the heartbeat and the daily summary; the money calls
//!   ([`win`], [`failed_landing`], [`loss`], [`budget_floor`], [`low_balance`]) that WP-05's settlement and WP-07's ledger
//!   make, and WP-07's notices ([`notice`]: its equity and token floors, reconciliation misses, balances and campaign
//!   lifecycle); the segment's start and stop; a crash.
pub mod format;
pub mod summary;
pub mod telegram;
#[cfg(test)]
mod tests;

use crate::feeds::clock::real_ns;
use crate::rec::Rec;
use format::{int, short_key, sol, sol_signed, Body};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use std::collections::{HashMap, VecDeque};
use std::path::PathBuf;
use std::sync::atomic::{AtomicBool, AtomicU64, Ordering::Relaxed};
use std::sync::{Arc, Mutex, OnceLock};
use std::time::{Duration, Instant};
use summary::Snapshot;
use telegram::PostErr;

/// how long the exit message (and what was still queued) may take at the end of `arbx run`
pub const EXIT_WAIT: Duration = Duration::from_secs(5);
/// how long the panic hook waits for its Critical alert
pub const CRASH_WAIT: Duration = Duration::from_secs(3);
/// how long `arbx run` waits for the sender to empty its queue before the runtimes stop
pub const FLUSH_WAIT: Duration = Duration::from_secs(4);
/// dedup keys held at most (past it a new key is not deduplicated: memory stays bounded)
const MAX_KEYS: usize = 4_096;
/// at most this many messages at exit (what does not fit is counted as dropped and named in the last one)
const MAX_EXIT_MESSAGES: usize = 3;
/// a stream's failed connections that look like 503 (or 429) within [`STORM_WINDOW_NS`] that make a storm
pub const STORM_STREAM: usize = 3;
pub const STORM_WINDOW_NS: u64 = 300_000_000_000;
/// rate-limited RPC answers of one provider within a minute that make a 429 storm
pub const STORM_RPC_429: u64 = 30;
/// how often the monitor reads the segment's last status line
const MONITOR_EVERY: Duration = Duration::from_secs(15);
/// the run.log line of a failed message at most this often
const LOG_EVERY_NS: u64 = 600_000_000_000;

// ------------------------------------------------------------------ config

/// `[alerts]` (PLAN-ADDENDUM WP-20): off unless `enabled`. The token and the chat id are named by environment variables,
/// never held in the config (so never in meta.json, the frozen config copy or the normalized hash)
#[derive(Debug, Clone, PartialEq, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
pub struct AlertsCfg {
    /// send alerts (the variables must be set too; missing ones turn the alerts off with one warning)
    #[serde(default)]
    pub enabled: bool,
    /// the environment variable holding the bot token (the .env beside the config)
    #[serde(default = "token_env")]
    pub token_env: String,
    /// the environment variable holding the chat id (a group's is negative)
    #[serde(default = "chat_env")]
    pub chat_env: String,
    /// a heartbeat with the key numbers every this many minutes, across segments (0: none)
    #[serde(default = "heartbeat_min")]
    pub heartbeat_min: u64,
    /// alerts below this level are not sent: info, warning, error, critical
    #[serde(default = "min_level")]
    pub min_level: String,
    /// an alert repeated within this many seconds (same key) is counted, not sent
    #[serde(default = "dedup_s")]
    pub dedup_s: u64,
    /// messages per chat in any 60 s at most (Telegram allows a group 20 a minute)
    #[serde(default = "rate_per_min")]
    pub rate_per_min: u32,
    /// alerts arriving within this many ms of the first one go out in one message (a Critical one goes at once)
    #[serde(default = "coalesce_ms")]
    pub coalesce_ms: u64,
    /// the daily summary of the UTC day before, sent at 00:00 UTC by the first segment or watchdog to notice
    #[serde(default = "yes")]
    pub daily_summary: bool,
    /// a warning when the liquid balance (WP-07's `money.equity_liquid_now`, or `alerts::low_balance`) is under this
    /// many SOL (0: none)
    #[serde(default)]
    pub low_balance_sol: f64,
}

fn token_env() -> String { "TELEGRAM_BOT_TOKEN".into() }
fn chat_env() -> String { "TELEGRAM_CHAT_ID".into() }
fn heartbeat_min() -> u64 { 60 }
fn min_level() -> String { "info".into() }
fn dedup_s() -> u64 { 600 }
fn rate_per_min() -> u32 { 20 }
fn coalesce_ms() -> u64 { 2_000 }
fn yes() -> bool { true }

impl Default for AlertsCfg {
    fn default() -> Self {
        AlertsCfg { enabled: false, token_env: token_env(), chat_env: chat_env(), heartbeat_min: heartbeat_min(), min_level: min_level(), dedup_s: dedup_s(),
            rate_per_min: rate_per_min(), coalesce_ms: coalesce_ms(), daily_summary: true, low_balance_sol: 0.0 }
    }
}

/// an environment variable's name as arbx's are: upper-case letters, digits and `_`, not starting with a digit, at most
/// 64 (a token's secret half, mixed case, never passes)
fn env_name_ok(s: &str) -> bool { !s.is_empty() && s.len() <= 64 && !s.starts_with(|c: char| c.is_ascii_digit()) && s.bytes().all(|b| b.is_ascii_uppercase() || b.is_ascii_digit() || b == b'_') }

impl AlertsCfg {
    /// `Config::parse`'s checks. A `token_env` / `chat_env` that is no variable name (a pasted token or chat id) is
    /// refused without echoing it
    pub fn check(&self) -> anyhow::Result<()> {
        for (k, v) in [("token_env", &self.token_env), ("chat_env", &self.chat_env)] {
            if !env_name_ok(v) { anyhow::bail!("[alerts] {k} must name an environment variable (A-Z, 0-9, _), not hold a value: put the value in .env"); }
        }
        if Level::parse(&self.min_level).is_none() { anyhow::bail!("[alerts] min_level must be info, warning, error or critical"); }
        if !(1..=60).contains(&self.rate_per_min) { anyhow::bail!("[alerts] rate_per_min must be 1..60 (Telegram allows a group 20 a minute)"); }
        if self.dedup_s > 86_400 { anyhow::bail!("[alerts] dedup_s must be at most 86400"); }
        if self.coalesce_ms > 60_000 { anyhow::bail!("[alerts] coalesce_ms must be at most 60000"); }
        if self.heartbeat_min > 10_080 { anyhow::bail!("[alerts] heartbeat_min must be at most 10080 (a week; 0: none)"); }
        if !self.low_balance_sol.is_finite() || self.low_balance_sol < 0.0 { anyhow::bail!("[alerts] low_balance_sol must be a number >= 0 (0: none)"); }
        Ok(())
    }
    pub fn level(&self) -> Level { Level::parse(&self.min_level).unwrap_or(Level::Info) }
}

// ------------------------------------------------------------------ alerts

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum Level { Info = 1, Warning = 2, Error = 3, Critical = 4 }

impl Level {
    pub fn parse(s: &str) -> Option<Level> {
        match s { "info" => Some(Level::Info), "warning" => Some(Level::Warning), "error" => Some(Level::Error), "critical" => Some(Level::Critical), _ => None }
    }
    pub fn as_str(self) -> &'static str { match self { Level::Info => "info", Level::Warning => "warning", Level::Error => "error", Level::Critical => "critical" } }
    pub fn icon(self) -> &'static str { match self { Level::Info => "ℹ️", Level::Warning => "⚠️", Level::Error => "❌", Level::Critical => "🚨" } }
}

/// One alert. `title` and `body` are HTML made of escaped pieces only ([`format`])
#[derive(Clone, Debug)]
pub struct Alert {
    pub level: Level,
    /// what raised it: an events.jsonl kind (A.6) or the alerts' own (`win`, `segment_start`, ...)
    pub kind: &'static str,
    /// the dedup key
    pub key: String,
    /// transitions of one thing share a family (see the module doc)
    pub family: Option<&'static str>,
    /// false: never deduplicated (lifecycle, money, the watchdog's verdicts)
    pub dedup: bool,
    pub icon: &'static str,
    pub title: String,
    pub body: String,
    pub t_ns: u64,
    /// repeats suppressed since the last one of its key was sent
    pub repeats: u64,
}

impl Alert {
    /// `title` is text (escaped here)
    pub fn new(level: Level, kind: &'static str, key: impl Into<String>, title: &str) -> Alert {
        Alert { level, kind, key: key.into(), family: None, dedup: true, icon: level.icon(), title: format::text(title, 200), body: String::new(), t_ns: real_ns(), repeats: 0 }
    }
    pub fn icon(mut self, i: &'static str) -> Alert { self.icon = i; self }
    pub fn body(mut self, b: Body) -> Alert { self.body = b.html(); self }
    pub fn once(mut self) -> Alert { self.dedup = false; self }
    pub fn family(mut self, f: &'static str) -> Alert { self.family = Some(f); self }
}

// ------------------------------------------------------------------ money (WP-05 / WP-07 call these)

/// A landed bundle whose route succeeded (`alerts::win`; WP-05's `Exec::finalize` for `landed_ok`). Its net is the
/// realised one from chain data: the round trip of the route program's events, minus the tip, the fee and the rent of
/// any account the transaction created (Stage-1 plan review F12: a success is "profitable" only when that net is > 0)
#[derive(Clone, Debug, Default)]
pub struct Win {
    /// the route's venues in order (`PumpSwap>Dlmm`), when known
    pub route: Option<String>,
    /// the token (base58) and its name, when known
    pub mint: String,
    pub mint_name: Option<String>,
    pub size_lamports: u64,
    /// the round trip on chain (the last leg's output − size), None while the record has none
    pub gross_lamports: Option<i64>,
    pub tip_lamports: u64,
    pub fee_lamports: u64,
    /// SOL the transaction left locked in new accounts (token-account rent, recoverable only by closing them; 0 for
    /// WP-06's create+close in the same transaction)
    pub rent_lamports: u64,
    pub slot: Option<u64>,
    pub signature: String,
    pub attempt: Option<u64>,
}

impl Win {
    /// the realised net: gross − tip − fee − rent (None while the gross is unknown). In i128, clamped: no input overflows
    pub fn net_lamports(&self) -> Option<i64> {
        self.gross_lamports.map(|g| clamp_i64(g as i128 - self.tip_lamports as i128 - self.fee_lamports as i128 - self.rent_lamports as i128))
    }
}

/// an i128 sum back into i64, saturating (lamport sums never come near it; a corrupt input must not panic or wrap)
pub(crate) fn clamp_i64(x: i128) -> i64 { x.clamp(i64::MIN as i128, i64::MAX as i128) as i64 }

/// A landed transaction that failed (the route reverted: the fee is lost; `alerts::failed_landing`)
#[derive(Clone, Debug, Default)]
pub struct FailedLanding {
    pub route: Option<String>,
    pub mint: String,
    pub mint_name: Option<String>,
    pub size_lamports: u64,
    pub fee_lamports: u64,
    pub slot: Option<u64>,
    pub signature: String,
    /// the program error, when known (`custom 0x1771: min_profit not met`)
    pub error: Option<String>,
    pub attempt: Option<u64>,
}

/// A realised loss (`alerts::loss`: WP-07's ledger, a trade whose net after fees, tips and rent is below 0)
#[derive(Clone, Debug, Default)]
pub struct Loss {
    pub route: Option<String>,
    pub mint: String,
    pub mint_name: Option<String>,
    pub size_lamports: u64,
    pub net_lamports: i64,
    pub tip_lamports: u64,
    pub fee_lamports: u64,
    pub rent_lamports: u64,
    pub slot: Option<u64>,
    pub signature: Option<String>,
    pub why: Option<String>,
}

/// A budget or equity floor reached (Critical; `alerts::budget_floor`)
#[derive(Clone, Debug, Default)]
pub struct BudgetFloor {
    /// `failed_fee_cap`, `equity_floor`, `equity_hour`, ...
    pub what: String,
    pub value_lamports: i64,
    pub floor_lamports: i64,
    pub detail: Option<String>,
}

/// A balance under its warning level (`alerts::low_balance`)
#[derive(Clone, Debug, Default)]
pub struct LowBalance {
    /// `liquid SOL + WSOL`, `native SOL`, ...
    pub what: String,
    pub lamports: u64,
    pub warn_below_lamports: u64,
}

/// `route · mint` (the mint's name first when known)
fn route_mint(b: Body, route: &Option<String>, mint: &str, name: &Option<String>) -> Body {
    let b = b.code("", route.as_deref().unwrap_or("route ?"));
    match name { Some(n) if !n.trim().is_empty() => b.kv(n.trim(), short_key(mint)), _ => b.code("", short_key(mint)) }
}

fn sig_part(b: Body, sig: &str) -> Body {
    match format::solscan_tx(sig) { Some(l) => b.raw(l), None if sig.is_empty() => b, None => b.code("tx", short_key(sig)) }
}

/// The alert of a landing whose route succeeded: "succeeded" and the realised net from chain data (the round trip of the
/// route program's events − tip − fee − rent). Never "profitable" (the word is not used) and a gain only when that net
/// is above 0 (Stage-1 plan review F12): a net below 0 is a Warning that says it lost, a net of 0 says "no profit"
pub fn win_alert(w: &Win) -> Alert {
    let (level, icon, title) = match w.net_lamports() {
        Some(n) if n > 0 => (Level::Info, "💰", format!("succeeded · net {}", sol_signed(n))),
        Some(0) => (Level::Info, "➖", "succeeded · net 0 SOL: no profit after fee, tip, rent".to_string()),
        Some(n) => (Level::Warning, "🔻", format!("succeeded but lost: net {} after fee, tip, rent", sol_signed(n))),
        None => (Level::Info, "✅", "succeeded · net not known yet".to_string()),
    };
    let mut b = route_mint(Body::new(), &w.route, &w.mint, &w.mint_name).nl()
        .kv("size", format::sol_num(w.size_lamports as i64)).kv("gross", w.gross_lamports.map_or("?".to_string(), format::sol_num_signed))
        .kv("tip", format::sol_num(w.tip_lamports as i64)).kv("fee", format::sol_num(w.fee_lamports as i64));
    if w.rent_lamports > 0 { b = b.kv("rent", format::sol_num(w.rent_lamports as i64)); }
    let b = b.nl().kv("slot", w.slot.map_or("?".to_string(), int));
    Alert::new(level, "win", format!("win:{}", w.signature), &title).icon(icon).once().body(sig_part(b, &w.signature))
}

/// the alert of a failed landing (Error; one key, so a run of them is one message every `dedup_s` with the count)
pub fn failed_landing_alert(f: &FailedLanding) -> Alert {
    let mut b = route_mint(Body::new(), &f.route, &f.mint, &f.mint_name).nl().kv("size", format::sol_num(f.size_lamports as i64));
    if let Some(e) = &f.error { b = b.code("", e); }
    let b = b.nl().kv("slot", f.slot.map_or("?".to_string(), int));
    Alert::new(Level::Error, "failed_landing", "failed_landing", &format!("failed landing · fee {} lost", sol(f.fee_lamports as i64))).body(sig_part(b, &f.signature))
}

/// the alert of a realised loss
pub fn loss_alert(l: &Loss) -> Alert {
    let mut b = route_mint(Body::new(), &l.route, &l.mint, &l.mint_name).nl().kv("size", format::sol_num(l.size_lamports as i64))
        .kv("tip", format::sol_num(l.tip_lamports as i64)).kv("fee", format::sol_num(l.fee_lamports as i64));
    if l.rent_lamports > 0 { b = b.kv("rent", format::sol_num(l.rent_lamports as i64)); }
    if let Some(w) = &l.why { b = b.nl().txt(w); }
    if let Some(s) = l.slot { b = b.nl().kv("slot", int(s)); }
    let b = match &l.signature { Some(s) => sig_part(b, s), None => b };
    Alert::new(Level::Warning, "loss", format!("loss:{}", l.signature.as_deref().unwrap_or(&real_ns().to_string())), &format!("loss · net {}", sol_signed(l.net_lamports)))
        .icon("🔻").once().body(b)
}

/// the alert of a budget or equity floor reached (Critical)
pub fn budget_floor_alert(b: &BudgetFloor) -> Alert {
    let body = Body::new().kv("at", sol(b.value_lamports)).kv("floor", sol(b.floor_lamports));
    let body = match &b.detail { Some(d) => body.nl().txt(d), None => body };
    Alert::new(Level::Critical, "budget_floor", format!("budget_floor:{}", b.what), &format!("BUDGET FLOOR ({}): sending stops", b.what)).icon("🛑").body(body)
}

/// the alert of a low balance (Warning)
pub fn low_balance_alert(b: &LowBalance) -> Alert {
    Alert::new(Level::Warning, "low_balance", format!("low_balance:{}", b.what), &format!("low balance · {} {}", b.what, sol(b.lamports as i64)))
        .icon("🪫").body(Body::new().kv("warn below", sol(b.warn_below_lamports as i64)))
}

/// The alert of one of WP-07's notices (src/notify.rs on lane/wp-07: the ledger's, its in-process supervisor's and the
/// campaign's money and lifecycle events: `equity_floor`, `equity_hour`, `equity_day`, `token_floor`, `recon_miss`,
/// `low_native_sol`, `stranded_token`, `equity_unknown`, `campaign_start`, `equity_start`, `segment_end`,
/// `segment_not_sending`, `segment_start_failed`, `campaign_shadow`, `campaign_end`). The merge wires it with
/// `notify::set_hook(|n| { alerts::notice(<n.level as a Level: Warn is Warning>, n.kind, &n.subject, &n.text); })`.
/// Its level is WP-07's; its key `<kind>:<subject>`; it is never deduplicated (WP-07 raises each once); `text`, WP-07's
/// line for a person, is the title (escaped, cut at 200 characters)
pub fn notice_alert(level: Level, kind: &'static str, subject: &str, text: &str) -> Alert {
    let icon = match kind {
        "equity_floor" | "equity_hour" | "equity_day" | "token_floor" => "🛑",
        "low_native_sol" => "🪫",
        "stranded_token" => "🪙",
        "campaign_start" | "equity_start" => "🟢",
        "campaign_shadow" | "segment_not_sending" => "🚦",
        "campaign_end" | "segment_end" if level < Level::Error => "⏹",
        _ => level.icon(),
    };
    Alert::new(level, kind, format!("{kind}:{subject}"), text).icon(icon).once()
}

// ------------------------------------------------------------------ events.jsonl kinds -> alerts

fn s_of(d: &Value, k: &str) -> String { d[k].as_str().map(str::to_string).unwrap_or_else(|| if d[k].is_null() { String::new() } else { d[k].to_string() }) }
/// a free-text field (an error, a why, a detail) with every URL cut to its host and key parameters masked
/// (`rpc::scrub`): a provider's key in a URL never goes to the chat
fn t_of(d: &Value, k: &str) -> String { crate::rpc::scrub(&s_of(d, k)) }
fn n_of(d: &Value, k: &str) -> Option<u64> { d[k].as_u64() }
fn gb(b: Option<u64>) -> String { b.map_or("?".into(), |b| format!("{:.1} GB", b as f64 / (1u64 << 30) as f64)) }

/// The alert of an events.jsonl event (MEASUREMENT A.6), if it is one worth telling (None for the rest). Pure: the
/// recorder's tap calls it on the producer's thread, so it only reads `detail`
pub fn classify(kind: &str, d: &Value) -> Option<Alert> {
    let a = match kind {
        "state_unavailable" => {
            let why = s_of(d, "why");
            if why == "boot_timeout" || why == "unavailable_stop" {
                Alert::new(Level::Critical, "state_unavailable", "state_stop", "state stream unavailable: the segment stops").family("state")
                    .body(Body::new().kv("why", &why).nl().txt(t_of(d, "detail")))
            } else {
                let mut b = Body::new().kv("why", &why);
                if let Some(a) = n_of(d, "age_ms") { b = b.kv("last message", format!("{} ago", format::dur(a / 1000))); }
                if let Some(r) = n_of(d, "reconnects") { b = b.kv("reconnects", r.to_string()); }
                let e = s_of(d, "error");
                if !e.is_empty() { b = b.nl().code("error", crate::rpc::scrub(&e)); }
                Alert::new(Level::Error, "state_unavailable", "state_down", "state stream down: nothing is priced or sent").family("state").body(b)
            }
        }
        "state_available" => Alert::new(Level::Info, "state_available", "state_up", "state stream back").icon("✅").family("state")
            .body(Body::new().kv("down for", n_of(d, "down_ms").map_or("?".into(), |m| format::dur(m / 1000))).kv("reconnects", n_of(d, "reconnects").map_or("?".into(), |r| r.to_string()))),
        "state_resync_slow" => Alert::new(Level::Warning, "state_resync_slow", "resync_slow", "state re-read has not landed: the gate stays shut")
            .body(Body::new().kv("why", s_of(d, "why")).kv("chunks", format!("{}/{}", n_of(d, "chunks_done").unwrap_or(0), n_of(d, "chunks").unwrap_or(0)))
                .kv("accounts", n_of(d, "accounts").unwrap_or(0).to_string()).nl().code("error", t_of(d, "err"))),
        "read_gave_up" => Alert::new(Level::Warning, "read_gave_up", format!("read_gave_up:{}", s_of(d, "what")), "gave up re-reading accounts")
            .body(Body::new().kv("what", s_of(d, "what")).kv("accounts", n_of(d, "accounts").unwrap_or(0).to_string()).nl().code("error", t_of(d, "err"))),
        "recorder_drop" => {
            let class = s_of(d, "class");
            let level = if class == "core" || class == "replay" { Level::Error } else { Level::Warning };
            let what = if class == "core" { "recorder lost a core record: sending stops for the rest of the segment" } else { "recorder dropped records" };
            Alert::new(level, "recorder_drop", format!("recorder_drop:{}", s_of(d, "stream")), what)
                .body(Body::new().code("stream", s_of(d, "stream")).kv("class", &class).kv("dropped", n_of(d, "dropped_total").map_or("?".into(), int)).kv("why", s_of(d, "why")))
        }
        "recorder_io_error" => Alert::new(Level::Error, "recorder_io_error", format!("recorder_io:{}", s_of(d, "stream")), "recorder I/O error")
            .body(Body::new().code("stream", s_of(d, "stream")).kv("op", s_of(d, "op")).kv("records lost", n_of(d, "lost_total").map_or("?".into(), int)).nl()
                .code("error", t_of(d, "error"))),
        "recorder_encode_error" => Alert::new(Level::Warning, "recorder_encode_error", format!("recorder_enc:{}", s_of(d, "stream")), "recorder: a record's encoder failed")
            .body(Body::new().code("stream", s_of(d, "stream")).kv("so far", n_of(d, "encode_errors_total").map_or("?".into(), int))),
        "recorder_writer_dead" => Alert::new(Level::Error, "recorder_writer_dead", format!("writer_dead:{}", s_of(d, "class")), "recorder writer died")
            .body(Body::new().kv("class", s_of(d, "class")).nl().txt(t_of(d, "detail"))),
        "recorder_writer_stalled" => Alert::new(Level::Error, "recorder_writer_stalled", format!("writer_stalled:{}", s_of(d, "class")), "recorder writer stalled")
            .body(Body::new().kv("class", s_of(d, "class")).kv("queued", n_of(d, "queued").map_or("?".into(), int)).nl().txt(t_of(d, "detail"))),
        "recorder_fatal" => Alert::new(Level::Critical, "recorder_fatal", "recorder_fatal", "recorder stopped the segment").body(Body::new().txt(t_of(d, "detail"))),
        "disk_action" => {
            let action = s_of(d, "action");
            let level = if action == "shadow_and_stop" { Level::Critical } else { Level::Warning };
            Alert::new(level, "disk_action", format!("disk:{action}"), &format!("disk budget: {action}")).icon(if level == Level::Critical { "🚨" } else { "💾" })
                .body(Body::new().kv("used", gb(n_of(d, "used_bytes"))).kv("budget", gb(n_of(d, "budget_bytes"))).kv("free", gb(n_of(d, "fs_free_bytes"))))
        }
        "chainfetch_dead" => Alert::new(Level::Error, "chainfetch_dead", "chainfetch_dead", "chain fetch died: sending stops for the rest of the segment")
            .family("chainfetch").body(Body::new().txt(t_of(d, "why"))),
        "chainfetch_stalled" => Alert::new(Level::Warning, "chainfetch_stalled", "chainfetch_stalled", "chain fetch stalled").family("chainfetch")
            .body(Body::new().kv("no publication for", format!("{} ms", n_of(d, "published_age_ms").unwrap_or(0)))),
        "chainfetch_recovered" => Alert::new(Level::Info, "chainfetch_recovered", "chainfetch_recovered", "chain fetch recovered").icon("✅").family("chainfetch"),
        "rpc_boot_failed" => Alert::new(Level::Error, "rpc_boot_failed", "rpc_boot_failed", "boot failed: no RPC provider answered")
            .body(Body::new().code("method", s_of(d, "method")).kv("attempts", n_of(d, "attempts").map_or("?".into(), int)).nl().code("last", t_of(d, "last"))),
        "jito_token_refresh" if d["ok"] == json!(false) => {
            let stale = d["stale"] == json!(true);
            Alert::new(Level::Error, "jito_token_refresh", "jito_token", if stale { "Jito auth token renewal failed: no valid token, sends are refused" } else { "Jito auth token renewal failed" })
                .body(Body::new().kv("retry in", format!("{} s", n_of(d, "retry_s").unwrap_or(0))).nl().code("error", t_of(d, "error")))
        }
        "jito_stream_down" => Alert::new(Level::Warning, "jito_stream_down", "jito_stream_down", "Jito result stream down").family("jito_stream")
            .body(Body::new().code("error", t_of(d, "error"))),
        "jito_stream_up" => Alert::new(Level::Info, "jito_stream_up", "jito_stream_up", "Jito result stream back").icon("✅").family("jito_stream")
            .body(Body::new().kv("down for", n_of(d, "down_ms").map_or("?".into(), |m| format::dur(m / 1000)))),
        // `recon_miss` and WP-07's other money events come as its notices (`alerts::notice`, with WP-07's own text): telling
        // them here too would send each twice
        _ => return None,
    };
    Some(a)
}

/// The alert of a SendGate change (None for the stop: the stop message says it)
pub fn gate_alert(prev: &(String, String), mode: &str, reason: &str, detail: &str, sticky: bool) -> Option<Alert> {
    let was = if prev.1.is_empty() { prev.0.clone() } else { format!("{} ({})", prev.0, prev.1) };
    match mode {
        "live" => Some(Alert::new(Level::Info, "gate_change", "gate:live", "sending resumed: SendGate live").icon("🚦").family("gate")
            .body(Body::new().kv("was", was).nl().txt(detail))),
        "shadow" => {
            let level = match reason {
                "control" | "mode_shadow" | "forced_shadow" | "dry_run" => Level::Info,
                "state_slo" => Level::Warning,
                "core_record_loss" | "recorder_unhealthy" | "disk_budget" | "chainfetch_dead" | "program_hash_mismatch" => Level::Error,
                // the money stops: WP-07's equity and token floors (its supervisor's rule names), a reconciliation miss
                "token_floor" => Level::Critical,
                r if r.contains("equity") || r.contains("budget") || r.contains("recon") || r.contains("fee_cap") => Level::Critical,
                _ => Level::Warning,
            };
            let mut b = Body::new().kv("was", was);
            if sticky { b = b.txt("for the rest of the segment"); }
            if !detail.is_empty() { b = b.nl().txt(detail); }
            Some(Alert::new(level, "gate_change", format!("gate:shadow:{reason}"), &format!("SendGate shadow: {reason}")).icon("🚦").family("gate").body(b))
        }
        _ => None,
    }
}

// ------------------------------------------------------------------ the segment's facts

/// What a segment tells the alerts at its start (the start message; the heartbeat reads its mode)
#[derive(Clone, Debug, Default)]
pub struct SegmentStart {
    pub segment: String,
    /// live, canary, shadow, dry_run
    pub mode: String,
    pub gate_mode: String,
    pub gate_reason: Option<String>,
    pub build: String,
    pub config_sha: String,
    pub wallet: String,
    /// `--budget-left`, lamports (the supervisor's), and the effective failed-fee cap
    pub budget_left_lamports: Option<u64>,
    pub fee_cap_lamports: u64,
}

/// the segment start message
pub fn start_alert(s: &SegmentStart) -> Alert {
    let gate = match &s.gate_reason { Some(r) => format!("{} ({r})", s.gate_mode), None => s.gate_mode.clone() };
    let mut b = Body::new().txt(&s.mode).kv("gate", gate).nl().kv("build", &s.build).kv("config", &s.config_sha).nl().kv("wallet", short_key(&s.wallet));
    b = match s.budget_left_lamports { Some(l) => b.kv("budget left", sol(l as i64)), None => b.kv("fee cap", sol(s.fee_cap_lamports as i64)) };
    Alert::new(Level::Info, "segment_start", format!("start:{}", s.segment), &format!("{} started", s.segment)).icon("🟢").once().body(b)
}

/// the net of a status line (`≥` while a win's round trip is unknown)
fn net_text(s: &Snapshot) -> String {
    s.net_lamports.map_or("?".to_string(), |v| format!("{}{}", if s.net_partial { "≥ " } else { "" }, sol_signed(v)))
}

/// two short lines of a status line's numbers: `decisions 12,345 · opps 87 · would-send 40`, `sent 2 · wins 1 · net +0.0001 SOL`
fn numbers(b: Body, s: &Snapshot) -> Body {
    let n = |x: Option<u64>| x.map_or("?".to_string(), int);
    let mut b = b.kv("decisions", n(s.decisions));
    if let Some(o) = s.opportunities { b = b.kv("opps", int(o)); }
    if let Some(w) = s.would_send { b = b.kv("would-send", int(w)); }
    b.nl().kv("sent", n(s.sends)).kv("wins", n(s.wins)).kv("net", net_text(s))
}

/// the stop message: the reason, how long the segment ran, its last status line's numbers
pub fn stop_alert(label: &str, reason: &str, detail: &str, code: i32, secondary: Option<(&str, &str)>, ran_s: Option<u64>, snap: Option<&Snapshot>) -> Alert {
    let level = match reason {
        "deadline" | "signal" | "control" => if code == 0 || code == 10 { Level::Info } else { Level::Error },
        // a crash, and every safety stop (exit 20: the campaign ends): the disk budget, the equity stops (WP-07 adds
        // equity_hour, equity_floor and token_floor beside equity_day)
        "panic" | "equity_day" | "disk_budget" | "equity_hour" | "equity_floor" | "token_floor" => Level::Critical,
        _ if code == 20 => Level::Critical,
        _ => Level::Error,
    };
    let icon = match level { Level::Info => "⏹", Level::Critical => "🚨", _ => "❌" };
    let mut b = Body::new().txt(detail);
    if let Some((r, d)) = secondary { b = b.nl().kv("then", r).txt(d); }
    b = b.nl();
    if let Some(r) = ran_s { b = b.kv("ran", format::dur(r)); }
    if let Some(s) = snap {
        if let Some(g) = &s.gate_mode { b = b.kv("gate", match &s.gate_reason { Some(r) => format!("{g} ({r})"), None => g.clone() }); }
        b = numbers(b.nl(), s);
    }
    Alert::new(level, "segment_stop", format!("stop:{label}"), &format!("{label} stopped: {reason} (exit {code})")).icon(icon).once().body(b)
}

/// the net of a period's totals, its source named (`ledger`, `wallet records`)
fn totals_net(t: &summary::DayTotals) -> String {
    if t.net_known { format!("{}{} ({})", if t.net_partial { "≥ " } else { "" }, sol_signed(t.net_lamports), t.net_src.unwrap_or("wallet records")) }
    else { "? (no ledger or wallet records)".into() }
}

/// The heartbeat: the current segment's gate and state, and the numbers of the last `period_s` across every segment of
/// the runs directory (a segment shorter than the period still gets its numbers into the heartbeat)
pub fn heartbeat_alert(label: &str, mode: &str, up_s: u64, s: &Snapshot, w: &summary::DayTotals, period_s: u64, sent: u64) -> Alert {
    let gate = match (&s.gate_mode, &s.gate_reason) { (Some(g), Some(r)) => format!("{g} ({r})"), (Some(g), None) => g.clone(), _ => "?".into() };
    let state = match (s.state_ok, &s.shut) { (Some(true), _) => "ok".to_string(), (_, Some(sh)) => sh.clone(), _ => "?".into() };
    let mut b = Body::new().txt(mode).kv("gate", gate).kv("state", state).nl()
        .kv(&format!("last {}: decisions", format::dur(period_s)), int(w.decisions)).kv("would-send", int(w.would_send)).nl()
        .kv("sent", if w.sends_known { int(w.sends) } else { "?".into() }).kv("wins", int(w.wins)).kv("net", totals_net(w)).nl();
    if let Some(l) = s.budget_left() { b = b.kv("budget left", sol(l)); }
    b = b.kv("alerts sent", int(sent));
    Alert::new(Level::Info, "heartbeat", "heartbeat", &format!("{label} up {}", format::dur(up_s))).icon("💓").once().body(b)
}

/// "1 win", "12 wins"
fn count_of(n: u64, one: &str, many: &str) -> String { format!("{} {}", int(n), if n == 1 { one } else { many }) }

/// The win ratio as the owner reads it (docs/STAGE1-PLAN.md §1 "What you will see"; Stage-1 plan review F12): wins ÷
/// bundles sent, where a win is a landed bundle whose route succeeded (`exec.ok_total`) and sent counts live bundles only
/// (`exec.sent_total`: never would-sends, never `attempts_total`, no fallback), always beside both numbers and the net
/// from chain data: `win ratio 1.2% (12 wins / 1,003 sent) · net +0.0031 SOL (ledger)`, or
/// `win ratio: no sends (0 wins / 0 sent) · net …` when nothing was sent. Under 1% it keeps two decimals (0.29%: the old
/// bot's range)
pub fn ratio_line(wins: u64, sent: u64, net: &str) -> String {
    let counts = format!("{} / {} sent", count_of(wins, "win", "wins"), int(sent));
    if sent == 0 { return format!("win ratio: no sends ({counts}) · net {net}"); }
    let pct = wins as f64 * 100.0 / sent as f64;
    format!("win ratio {}% ({counts}) · net {net}", if pct < 1.0 { format!("{pct:.2}") } else { format!("{pct:.1}") })
}

/// The daily summary (docs/STAGE1-PLAN.md §1; F12): the [`ratio_line`] (wins ÷ bundles sent, `exec.sent_total` only,
/// "no sends" when there were none, beside the wins, the sends and the net from chain data), then the fees, tips and
/// rent, the budget left, the segments and crashes
pub fn daily_alert(t: &summary::DayTotals) -> Alert {
    let approx = if t.rent_estimated && t.rent > 0 { "≈ " } else { "" };
    let mut b = Body::new().txt(ratio_line(t.wins, t.sends, &totals_net(t))).nl()
        .kv("fees", format::sol_num(t.fees as i64)).kv("tips", format::sol_num(t.tips as i64))
        .kv("rent", format!("{approx}{} SOL", format::sol_num(t.rent as i64))).nl();
    if let Some(l) = t.budget_left { b = b.kv("budget left", sol(l)); }
    b = b.kv("segments", t.segments.to_string()).kv("crashes", t.crashes.to_string());
    Alert::new(Level::Info, "daily_summary", format!("daily:{}", t.day), &format!("daily {} (UTC)", t.day)).icon("📊").once().body(b)
}

// ------------------------------------------------------------------ the sink and its sender

/// The sender's timings (the tests shorten them)
#[derive(Clone, Debug)]
pub struct Tuning {
    /// the rate window (60 s) and the gap between two messages (1 s)
    pub window: Duration,
    pub spacing: Duration,
    pub coalesce: Duration,
    pub dedup: Duration,
    /// a failed try's backoff, doubling
    pub retry_base: Duration,
    pub max_attempts: u32,
    /// a `retry_after` waited at most this long
    pub retry_after_cap: Duration,
    /// after a refusal for good (a bad token, the bot out of the chat): the next message waits this long
    pub refused_pause: Duration,
    pub http_timeout: Duration,
    /// the queue's bound (alerts)
    pub queue: usize,
    /// how often the sender looks at the queue: nothing wakes it (a producer only queues, so it never touches a waker's
    /// lock), so an alert waits at most this long before the sender sees it
    pub tick: Duration,
}

impl Tuning {
    pub fn of(cfg: &AlertsCfg) -> Tuning {
        Tuning { window: Duration::from_secs(60), spacing: Duration::from_secs(1), coalesce: Duration::from_millis(cfg.coalesce_ms), dedup: Duration::from_secs(cfg.dedup_s),
            retry_base: Duration::from_secs(1), max_attempts: 5, retry_after_cap: Duration::from_secs(300), refused_pause: Duration::from_secs(60),
            http_timeout: Duration::from_secs(10), queue: 1_024, tick: Duration::from_millis(250) }
    }
}

/// the token, the chat (it can move: a group upgraded to a supergroup) and the API base. Never printed
struct Creds { token: String, chat: Mutex<String>, base: String }

impl std::fmt::Debug for Creds {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result { f.write_str("Creds { token: <redacted>, chat: <redacted> }") }
}

#[derive(Default)]
struct Counters {
    raised: AtomicU64,
    below_level: AtomicU64,
    deduped: AtomicU64,
    dropped: AtomicU64,
    sent: AtomicU64,
    messages: AtomicU64,
    failed: AtomicU64,
    coalesced: AtomicU64,
    attempts_failed: AtomicU64,
    rate_waits: AtomicU64,
    held: AtomicU64,
    /// alerts in the queue now, and taken by the sender but not yet delivered or failed
    queued: AtomicU64,
    pending: AtomicU64,
    last_sent_ns: AtomicU64,
}

struct Seen { last_ns: u64, suppressed: u64 }
struct Fam { last_key: String, pending: Option<Alert> }

/// the dedup state, under one lock: each key's last send and its repeats since; per family, the key sent last and the
/// change held
#[derive(Default)]
struct Dedup { seen: HashMap<String, Seen>, fams: HashMap<&'static str, Fam> }

/// what the sender has taken from the queue: alerts waiting for their message, and the message being sent. `gen`
/// changes when the exit path takes them over (a crash): the sender then counts nothing for the message it was sending
#[derive(Default)]
struct Work { batch: Vec<Alert>, in_flight: Vec<Alert>, gen: u64 }

/// What the alerts know about the process they run in (message headers, the exit message, the monitor)
#[derive(Clone, Debug, Default)]
pub struct Ctx {
    /// the segment's name, or `watchdog`
    pub label: String,
    /// the segment's directory (its status.jsonl), and the runs directory (heartbeat and daily markers)
    pub dir: Option<PathBuf>,
    pub runs_dir: Option<PathBuf>,
    pub started_ns: u64,
    pub seg: Option<SegmentStart>,
    /// `[send_policy] max_blockhash_age_slots` (the stale-blockhash alert)
    pub max_blockhash_age_slots: u64,
}

fn label_of(c: &Ctx) -> String { if c.label.is_empty() { crate::provenance::hostname() } else { c.label.clone() } }

/// The alerts of one process: the queue, the sender's state, the counters
pub struct Alerts {
    cfg: AlertsCfg,
    t: Tuning,
    min_level: Level,
    creds: Option<Creds>,
    off_why: Option<String>,
    tx: crossbeam_channel::Sender<Alert>,
    rx: crossbeam_channel::Receiver<Alert>,
    dd: Mutex<Dedup>,
    /// families holding a change: the sender takes the dedup lock only while one is held (and once a minute to prune it),
    /// so a producer's dedup check almost never finds it taken
    held_now: AtomicU64,
    work: Mutex<Work>,
    /// the chat's rate, shared by the sender and the exit path
    rate: Arc<Mutex<Rate>>,
    c: Counters,
    last_error: Mutex<Option<String>>,
    rec: OnceLock<Rec>,
    ctx: Mutex<Ctx>,
    storms: Mutex<HashMap<(String, &'static str), VecDeque<u64>>>,
    sender_alive: AtomicBool,
    flush_req: AtomicBool,
    exit_sent: AtomicBool,
    /// the panic hook tried the crash alert (sent, or put back with the undelivered ones: the exit sends it then)
    crash_tried: AtomicBool,
    last_log_ns: AtomicU64,
    last_drop_event_ns: AtomicU64,
}

impl std::fmt::Debug for Alerts {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Alerts").field("enabled", &self.creds.is_some()).field("off_why", &self.off_why).field("cfg", &self.cfg).field("creds", &self.creds).finish()
    }
}

/// `x -= n`, never below 0 (the exit path may take what the sender counted)
fn sub_sat(x: &AtomicU64, n: u64) { let _ = x.fetch_update(Relaxed, Relaxed, |v| Some(v.saturating_sub(n))); }

/// a lock, poisoned or not (the sender's and the main thread's short sections)
fn lock<T>(m: &Mutex<T>) -> std::sync::MutexGuard<'_, T> { m.lock().unwrap_or_else(|e| e.into_inner()) }

/// A lock tried a few times without sleeping or a system call (a producer's dedup check): None when it stays taken
fn try_spin<T>(m: &Mutex<T>) -> Option<std::sync::MutexGuard<'_, T>> {
    for _ in 0..64 {
        match m.try_lock() {
            Ok(g) => return Some(g),
            Err(std::sync::TryLockError::Poisoned(p)) => return Some(p.into_inner()),
            Err(std::sync::TryLockError::WouldBlock) => std::hint::spin_loop(),
        }
    }
    None
}

/// Lock briefly: a few tries over about 50 ms, then give up. Only on the exit, crash and alert-test paths (a dying
/// thread may hold a lock; never on a runtime)
fn lock_briefly<T>(m: &Mutex<T>) -> Option<std::sync::MutexGuard<'_, T>> {
    for _ in 0..50 {
        match m.try_lock() {
            Ok(g) => return Some(g),
            Err(std::sync::TryLockError::Poisoned(p)) => return Some(p.into_inner()),
            Err(std::sync::TryLockError::WouldBlock) => std::thread::sleep(Duration::from_millis(1)),
        }
    }
    None
}

/// The per-chat rate: at most `max` messages in any `window`, `spacing` between two, nothing while a 429 says wait
struct Rate { max: usize, window: Duration, spacing: Duration, sent: VecDeque<Instant>, blocked_until: Option<Instant> }

impl Rate {
    fn new(max: u32, window: Duration, spacing: Duration) -> Rate { Rate { max: max.max(1) as usize, window, spacing, sent: VecDeque::new(), blocked_until: None } }
    /// how long the next message must wait from `now` (None: it may go)
    fn wait(&mut self, now: Instant) -> Option<Duration> {
        if let Some(b) = self.blocked_until { if now < b { return Some(b - now); } self.blocked_until = None; }
        while self.sent.front().is_some_and(|t| now.saturating_duration_since(*t) >= self.window) { self.sent.pop_front(); }
        if self.sent.len() >= self.max { return self.sent.front().map(|t| (*t + self.window).saturating_duration_since(now).max(Duration::from_millis(1))); }
        if let Some(l) = self.sent.back() { if now < *l + self.spacing { return Some(*l + self.spacing - now); } }
        None
    }
    fn note(&mut self, now: Instant) { self.sent.push_back(now); }
    fn block(&mut self, until: Instant) { if self.blocked_until.is_none_or(|b| until > b) { self.blocked_until = Some(until); } }
}

impl Alerts {
    /// Alerts from `[alerts]`, the environment (`env`: a variable's value, None when unset or empty) and the process's
    /// context. Off when `enabled` is false or a variable is missing: then the notes say why (one warning), and every
    /// call is a no-op. Never fails
    pub fn new(cfg: &AlertsCfg, env: &dyn Fn(&str) -> Option<String>, ctx: Ctx) -> (Arc<Alerts>, Vec<String>) {
        Alerts::with(cfg, Tuning::of(cfg), env, telegram::API, ctx)
    }

    /// `new` with the sender's timings and the API base given (tests: a fake server on a loopback address)
    pub(crate) fn with(cfg: &AlertsCfg, t: Tuning, env: &dyn Fn(&str) -> Option<String>, base: &str, ctx: Ctx) -> (Arc<Alerts>, Vec<String>) {
        let mut notes = Vec::new();
        let get = |k: &str| env(k).map(|v| v.trim().to_string()).filter(|v| !v.is_empty());
        let (creds, off_why) = if !cfg.enabled {
            (None, Some("[alerts] enabled = false".to_string()))
        } else if !telegram::base_ok(base) {
            (None, Some("the alerts API base is not https (I-10)".to_string()))
        } else {
            match (get(&cfg.token_env), get(&cfg.chat_env)) {
                (Some(token), Some(chat)) => {
                    let (id, secret) = token.split_once(':').unwrap_or(("", ""));
                    if id.is_empty() || !id.bytes().all(|b| b.is_ascii_digit()) || secret.len() < 20 {
                        notes.push(format!("WARNING: alerts: {} does not look like a bot token (<bot id>:<secret>); sends will be refused if it is wrong", cfg.token_env));
                    }
                    (Some(Creds { token, chat: Mutex::new(chat), base: base.trim_end_matches('/').to_string() }), None)
                }
                (t, c) => {
                    let missing: Vec<&str> = [(t.is_none(), cfg.token_env.as_str()), (c.is_none(), cfg.chat_env.as_str())].into_iter().filter(|x| x.0).map(|x| x.1).collect();
                    let why = format!("{} not set", missing.join(" and "));
                    notes.push(format!("WARNING: alerts off: {why} (the .env beside the config, or --env-file); the run goes on without them"));
                    (None, Some(why))
                }
            }
        };
        if creds.is_some() {
            notes.push(format!("alerts on: Telegram (token from {}, chat from {}); at most {} messages a minute, dedup {} s, min level {}, heartbeat {}", cfg.token_env,
                cfg.chat_env, cfg.rate_per_min, cfg.dedup_s, cfg.min_level, if cfg.heartbeat_min == 0 { "off".into() } else { format!("every {} min", cfg.heartbeat_min) }));
        }
        let (tx, rx) = crossbeam_channel::bounded(t.queue.max(1));
        let rate = Arc::new(Mutex::new(Rate::new(cfg.rate_per_min, t.window, t.spacing)));
        let a = Arc::new(Alerts { min_level: cfg.level(), cfg: cfg.clone(), t, creds, off_why, tx, rx, dd: Mutex::new(Dedup::default()), held_now: AtomicU64::new(0),
            work: Mutex::new(Work::default()), rate, c: Counters::default(), last_error: Mutex::new(None), rec: OnceLock::new(), ctx: Mutex::new(ctx),
            storms: Mutex::new(HashMap::new()), sender_alive: AtomicBool::new(false), flush_req: AtomicBool::new(false), exit_sent: AtomicBool::new(false),
            crash_tried: AtomicBool::new(false), last_log_ns: AtomicU64::new(0),
            last_drop_event_ns: AtomicU64::new(0) });
        (a, notes)
    }

    pub fn enabled(&self) -> bool { self.creds.is_some() }
    pub fn off_why(&self) -> Option<&str> { self.off_why.as_deref() }
    pub fn cfg(&self) -> &AlertsCfg { &self.cfg }
    pub fn min_level(&self) -> Level { self.min_level }

    /// events.jsonl and run.log for the alerts' own events (`alert_sent`, `alert_failed`, `alert_dropped`)
    pub fn set_rec(&self, rec: Rec) { let _ = self.rec.set(rec); }
    pub fn set_ctx(&self, f: impl FnOnce(&mut Ctx)) { f(&mut lock(&self.ctx)); }
    pub fn ctx(&self) -> Ctx { lock(&self.ctx).clone() }
    /// the context on the exit and crash paths (never waits on a lock a dying thread may hold)
    fn ctx_briefly(&self) -> Ctx { lock_briefly(&self.ctx).map(|c| c.clone()).unwrap_or_default() }

    fn event(&self, kind: &'static str, detail: Value) { if let Some(r) = self.rec.get() { r.event(kind, "alerts", None, detail); } }
    fn say(&self, line: String) {
        match self.rec.get() { Some(r) if r.is_on() => r.say(line), _ => crate::rec::err_line(&line) }
    }

    /// redacted with this process's token
    fn redact(&self, s: &str) -> String { telegram::redact(s, self.creds.as_ref().map_or("", |c| c.token.as_str())) }

    /// keep the last failure's text (redacted); a busy lock skips it rather than wait
    fn set_error(&self, e: &str) {
        let e = self.redact(e);
        if let Some(mut g) = try_spin(&self.last_error) { *g = Some(e); }
    }

    // ---------------------------------------------------------------- producers (never wait)

    /// Hand an alert to the sender: never waits. False when it is not sent: off, under `min_level`, a repeat inside
    /// `dedup_s`, the queue full (dropped and counted), or raised on a replaying thread (a replay recomputes the past)
    pub fn raise(&self, mut a: Alert) -> bool {
        if self.creds.is_none() || crate::feeds::clock::virtual_time().is_some() { return false; }
        if a.level < self.min_level { self.c.below_level.fetch_add(1, Relaxed); return false; }
        self.c.raised.fetch_add(1, Relaxed);
        if !self.admit(&mut a) { self.c.deduped.fetch_add(1, Relaxed); return false; }
        self.enqueue(a)
    }

    /// The dedup check, the key and its family under one lock, tried without waiting (the sender holds it only while a
    /// change is held, for microseconds; a lock still taken lets the alert through). See the module doc for families
    fn admit(&self, a: &mut Alert) -> bool {
        if !a.dedup || a.key.is_empty() || self.t.dedup.is_zero() { return true; }
        let Some(mut g) = try_spin(&self.dd) else { return true };
        let now = real_ns();
        let win = self.t.dedup.as_nanos() as u64;
        let d = &mut *g;
        let pass = match d.seen.get_mut(&a.key) {
            Some(s) if now.saturating_sub(s.last_ns) < win => { s.suppressed += 1; false }
            Some(s) => { a.repeats = s.suppressed; s.suppressed = 0; s.last_ns = now; true }
            None => { if d.seen.len() < MAX_KEYS { d.seen.insert(a.key.clone(), Seen { last_ns: now, suppressed: 0 }); } true }
        };
        if let Some(f) = a.family {
            let e = d.fams.entry(f).or_insert_with(|| Fam { last_key: String::new(), pending: None });
            let held_before = e.pending.is_some();
            if pass { e.last_key = a.key.clone(); e.pending = None; }
            else if e.last_key != a.key { e.pending = Some(a.clone()); self.c.held.fetch_add(1, Relaxed); }
            else { e.pending = None; }
            match (held_before, e.pending.is_some()) {
                (false, true) => { self.held_now.fetch_add(1, Relaxed); }
                (true, false) => sub_sat(&self.held_now, 1),
                _ => {}
            }
        }
        pass
    }

    /// queue it (nothing wakes the sender: it looks every `tick`)
    fn enqueue(&self, a: Alert) -> bool {
        self.c.queued.fetch_add(1, Relaxed);
        match self.tx.try_send(a) {
            Ok(()) => true,
            Err(e) => {
                sub_sat(&self.c.queued, 1);
                let n = self.c.dropped.fetch_add(1, Relaxed) + 1;
                let a = e.into_inner();
                let now = real_ns();
                let last = self.last_drop_event_ns.load(Relaxed);
                if (n == 1 || now.saturating_sub(last) >= 1_000_000_000) && self.last_drop_event_ns.compare_exchange(last, now, Relaxed, Relaxed).is_ok() {
                    self.event("alert_dropped", json!({ "why": "queue full", "kind": a.kind, "level": a.level, "key": a.key, "dropped_total": n, "queue": self.t.queue }));
                }
                false
            }
        }
    }

    /// An events.jsonl event (the recorder's tap): its alert, if [`classify`] makes one
    pub fn on_event(&self, kind: &str, d: &Value) {
        if self.creds.is_none() { return; }
        if let Some(a) = classify(kind, d) { self.raise(a); }
    }

    /// A gRPC stream (the state stream, a feed) failed to connect or ended with `msg`: failures that look like 503 /
    /// `Unavailable` (any connect, DNS or TLS failure reads so through tonic) and like 429 / rate limits are counted per
    /// stream, and [`STORM_STREAM`] of one kind within 5 minutes is a storm (one alert per `dedup_s`)
    pub fn note_stream_error(&self, stream: &str, msg: &str) {
        if self.creds.is_none() { return; }
        let (class, what): (&'static str, &str) = if msg.contains("503") || msg.contains("Unavailable") || msg.contains("unavailable") { ("503", "unavailable (503)") }
            else if msg.contains("429") || msg.contains("Too Many Requests") || msg.contains("ResourceExhausted") || msg.contains("rate limit") { ("429", "rate-limit (429)") }
            else { return };
        let now = real_ns();
        let n = {
            let Some(mut s) = try_spin(&self.storms) else { return };
            if s.len() > 256 && !s.contains_key(&(stream.to_string(), class)) { return; }
            let q = s.entry((stream.to_string(), class)).or_default();
            q.push_back(now);
            while q.len() > 64 || q.front().is_some_and(|t| now.saturating_sub(*t) > STORM_WINDOW_NS) { q.pop_front(); }
            q.len()
        };
        if n >= STORM_STREAM {
            self.raise(Alert::new(Level::Warning, "stream_storm", format!("storm:{class}:{stream}"), &format!("{what} storm on {stream}: {n} failed connections in 5 min"))
                .icon("🌩").body(Body::new().code("last", self.redact(msg))));
        }
    }

    // ---------------------------------------------------------------- money and lifecycle (nothing is built when off)

    pub fn win(&self, w: &Win) -> bool { self.enabled() && self.raise(win_alert(w)) }
    pub fn failed_landing(&self, f: &FailedLanding) -> bool { self.enabled() && self.raise(failed_landing_alert(f)) }
    pub fn loss(&self, l: &Loss) -> bool { self.enabled() && self.raise(loss_alert(l)) }
    pub fn budget_floor(&self, b: &BudgetFloor) -> bool { self.enabled() && self.raise(budget_floor_alert(b)) }
    pub fn low_balance(&self, b: &LowBalance) -> bool { self.enabled() && self.raise(low_balance_alert(b)) }
    pub fn notice(&self, level: Level, kind: &'static str, subject: &str, text: &str) -> bool { self.enabled() && self.raise(notice_alert(level, kind, subject, text)) }

    /// The segment started (after meta.json): its facts are kept for the heartbeat and the monitor
    pub fn segment_start(&self, s: SegmentStart) -> bool {
        if !self.enabled() { return false; }
        let a = start_alert(&s);
        self.set_ctx(|c| c.seg = Some(s));
        self.raise(a)
    }

    // ---------------------------------------------------------------- counters

    /// status.jsonl `alerts` (MEASUREMENT §4.8): every number `_total` since the start, or `_now`; never the token or the
    /// chat id. Reads atomics only (`last_error` under `try_lock`): the engine thread calls it
    pub fn status_json(&self) -> Value {
        let c = &self.c;
        let g = |x: &AtomicU64| x.load(Relaxed);
        json!({ "enabled": self.creds.is_some(), "off_why": self.off_why, "raised_total": g(&c.raised), "sent_total": g(&c.sent), "messages_total": g(&c.messages),
            "dropped_total": g(&c.dropped), "failed_total": g(&c.failed), "deduped_total": g(&c.deduped), "held_total": g(&c.held), "below_level_total": g(&c.below_level),
            "coalesced_total": g(&c.coalesced), "attempts_failed_total": g(&c.attempts_failed), "rate_waits_total": g(&c.rate_waits),
            "queued_now": g(&c.queued), "pending_now": g(&c.pending), "last_sent_ns": Some(g(&c.last_sent_ns)).filter(|t| *t > 0),
            "last_error": self.last_error.try_lock().ok().and_then(|e| e.clone()) })
    }

    // ---------------------------------------------------------------- the sender

    /// Start the sender task on `rt` (rt_bg): until `stop` is set and nothing is left to send (then a run's last alerts go
    /// out with its exit message). Once; nothing when off
    pub fn start(self: &Arc<Self>, rt: &tokio::runtime::Handle, stop: Arc<AtomicBool>) {
        if self.creds.is_none() || self.sender_alive.swap(true, Relaxed) { return; }
        // a sender that ends (a stop, a panic, its runtime shut down, even before it first ran) says so: `flush` then
        // waits for nothing
        struct Alive(Arc<Alerts>);
        impl Drop for Alive { fn drop(&mut self) { self.0.sender_alive.store(false, Relaxed); } }
        let guard = Alive(self.clone());
        let me = self.clone();
        rt.spawn(async move {
            let _guard = guard;
            me.sender(stop).await;
        });
    }

    /// whether the sender task runs
    pub fn sender_alive(&self) -> bool { self.sender_alive.load(Relaxed) }

    /// Wait until the queue is empty and nothing is being sent, at most `wait` (the caller's thread blocks: never call
    /// it from a runtime or the hot path; `arbx run` calls it on the main thread once the engine ended). True when empty
    pub fn flush(&self, wait: Duration) -> bool {
        let empty = || self.c.queued.load(Relaxed) == 0 && self.c.pending.load(Relaxed) == 0;
        if self.creds.is_none() || empty() { return true; }
        if !self.sender_alive() { return false; }
        self.flush_req.store(true, Relaxed);
        let until = Instant::now() + wait;
        while !empty() {
            if Instant::now() >= until || !self.sender_alive() { self.flush_req.store(false, Relaxed); return false; }
            std::thread::sleep(Duration::from_millis(10));
        }
        self.flush_req.store(false, Relaxed);
        true
    }

    /// move what is queued into the batch (pending counted before the queue is decremented: `flush` never sees a gap)
    fn take_queue(&self) -> usize {
        let mut n = 0;
        let mut w = lock(&self.work);
        while w.batch.len() < 4 * self.t.queue.max(1) {
            let Ok(a) = self.rx.try_recv() else { break };
            self.c.pending.fetch_add(1, Relaxed);
            sub_sat(&self.c.queued, 1);
            w.batch.push(a);
            n += 1;
        }
        n
    }

    /// the held transitions whose dedup window ended: into the batch, each with its repeat count (nothing to do, and no
    /// lock taken, while none is held)
    fn release_held(&self) {
        if self.held_now.load(Relaxed) == 0 { return; }
        let now = real_ns();
        let win = self.t.dedup.as_nanos() as u64;
        let mut out = Vec::new();
        {
            let mut g = lock(&self.dd);
            let Dedup { seen, fams } = &mut *g;
            for f in fams.values_mut() {
                let due = f.pending.as_ref().is_some_and(|p| seen.get(&p.key).is_none_or(|s| now.saturating_sub(s.last_ns) >= win));
                if !due { continue; }
                let Some(mut a) = f.pending.take() else { continue };
                sub_sat(&self.held_now, 1);
                if let Some(s) = seen.get_mut(&a.key) { a.repeats = s.suppressed.saturating_sub(1); s.suppressed = 0; s.last_ns = now; }
                f.last_key = a.key.clone();
                out.push(a);
            }
        }
        if out.is_empty() { return; }
        let mut w = lock(&self.work);
        for a in out { self.c.pending.fetch_add(1, Relaxed); w.batch.push(a); }
    }

    /// forget dedup keys older than their window (bounded memory; the sender, once a minute)
    fn prune(&self) {
        let now = real_ns();
        let win = self.t.dedup.as_nanos() as u64;
        lock(&self.dd).seen.retain(|_, v| now.saturating_sub(v.last_ns) < win || v.suppressed > 0);
    }

    async fn sender(self: &Arc<Self>, stop: Arc<AtomicBool>) {
        let Some(creds) = self.creds.as_ref() else { return };
        let client = match telegram::client(self.t.http_timeout, !creds.base.starts_with("http://")) {
            Ok(c) => c,
            Err(e) => { self.set_error(&e); self.say(format!("WARNING: alerts: {}", self.redact(&e))); return; }
        };
        let mut first: Option<Instant> = None;
        let mut last_prune = Instant::now();
        let mut waiting_rate = false;
        let tick = self.t.tick.max(Duration::from_millis(1));
        loop {
            if self.take_queue() > 0 && first.is_none() { first = Some(Instant::now()); }
            self.release_held();
            if last_prune.elapsed() >= Duration::from_secs(60) { self.prune(); last_prune = Instant::now(); }
            let (n, critical) = { let w = lock(&self.work); (w.batch.len(), w.batch.iter().any(|a| a.level == Level::Critical)) };
            if n == 0 {
                first = None;
                if stop.load(Relaxed) { break; }
                tokio::time::sleep(tick).await;
                continue;
            }
            let t0 = *first.get_or_insert_with(Instant::now);
            let now = Instant::now();
            let urgent = critical || self.flush_req.load(Relaxed) || stop.load(Relaxed);
            if !urgent && now < t0 + self.t.coalesce {
                tokio::time::sleep((t0 + self.t.coalesce - now).min(tick)).await;
                continue;
            }
            let wait = lock(&self.rate).wait(now);
            if let Some(w) = wait {
                if !waiting_rate { waiting_rate = true; self.c.rate_waits.fetch_add(1, Relaxed); }
                // more alerts may come meanwhile: they join this message
                tokio::time::sleep(w.min(tick)).await;
                continue;
            }
            waiting_rate = false;
            let (text, k, kinds, level, gen) = {
                let mut w = lock(&self.work);
                let label = label_of(&lock(&self.ctx));
                let (text, k) = format::compose(&label, real_ns(), &w.batch, format::MAX_TEXT);
                // the bot's own token never goes into a message, whatever an alert's text carried
                let text = telegram::strip_token(&text, &creds.token);
                let taken: Vec<Alert> = w.batch.drain(..k).collect();
                let kinds: Vec<&'static str> = taken.iter().map(|a| a.kind).collect();
                let level = taken.iter().map(|a| a.level).max().unwrap_or(Level::Info);
                w.in_flight = taken;
                (text, k, kinds, level, w.gen)
            };
            // the exit path took the batch meanwhile (a crash): nothing to send
            if k == 0 { continue; }
            lock(&self.rate).note(Instant::now());
            let started = Instant::now();
            let res = self.deliver(&client, creds, text).await;
            // a crash's exit path may have taken this message over meanwhile: then it counts it, not the sender
            let mine = { let mut w = lock(&self.work); let m = w.gen == gen; if m { w.in_flight.clear(); } m };
            if mine {
                let n = k as u64;
                sub_sat(&self.c.pending, n);
                match &res {
                    Ok(attempts) => {
                        self.c.sent.fetch_add(n, Relaxed);
                        self.c.messages.fetch_add(1, Relaxed);
                        self.c.coalesced.fetch_add(n.saturating_sub(1), Relaxed);
                        self.c.last_sent_ns.store(real_ns(), Relaxed);
                        self.event("alert_sent", json!({ "alerts": n, "kinds": kinds, "level": level, "attempts": attempts, "ms": started.elapsed().as_millis() as u64 }));
                    }
                    Err((attempts, e)) => {
                        self.c.failed.fetch_add(n, Relaxed);
                        self.event("alert_failed", json!({ "alerts": n, "kinds": kinds, "level": level, "attempts": attempts, "error": e }));
                        let now_ns = real_ns();
                        let last = self.last_log_ns.load(Relaxed);
                        if last == 0 || now_ns.saturating_sub(last) >= LOG_EVERY_NS {
                            self.last_log_ns.store(now_ns, Relaxed);
                            self.say(format!("WARNING: alerts: a message ({n} alert{}) could not be sent after {attempts} tries: {e}", if n == 1 { "" } else { "s" }));
                        }
                    }
                }
            }
            // what a full message left behind has waited its window already: it goes next (at the rate)
            if lock(&self.work).batch.is_empty() { first = None; }
        }
    }

    /// One message, with its retries: a 429 after its `retry_after` (and every later message waits too), a transport
    /// error or 5xx after a doubling backoff, an HTML refusal as plain text, a moved group at its new chat id. Ok(tries)
    /// or Err((tries, the redacted error))
    async fn deliver(&self, client: &reqwest::Client, creds: &Creds, text: String) -> Result<u32, (u32, String)> {
        let mut html = true;
        let mut body = text;
        let mut attempt = 0u32;
        loop {
            attempt += 1;
            let chat = lock(&creds.chat).clone();
            let err = match telegram::post(client, &creds.base, &creds.token, &chat, &body, html).await {
                Ok(_) => return Ok(attempt),
                Err(e) => e,
            };
            self.c.attempts_failed.fetch_add(1, Relaxed);
            let msg = self.redact(err.text());
            self.set_error(&msg);
            let last = attempt >= self.t.max_attempts.max(1);
            match err {
                PostErr::RetryAfter(d, _) => {
                    let d = d.min(self.t.retry_after_cap);
                    lock(&self.rate).block(Instant::now() + d);
                    if last { return Err((attempt, msg)); }
                    tokio::time::sleep(d).await;
                }
                PostErr::Transient(_) => {
                    if last { return Err((attempt, msg)); }
                    tokio::time::sleep(self.t.retry_base.saturating_mul(1 << (attempt - 1).min(5))).await;
                }
                PostErr::Parse(_) if html => { html = false; body = format::to_plain(&body); }
                PostErr::Migrated(new, _) => {
                    if last { return Err((attempt, msg)); }
                    *lock(&creds.chat) = new;
                    self.say(format!("WARNING: alerts: {msg}"));
                }
                PostErr::Parse(_) | PostErr::Permanent(_) => {
                    lock(&self.rate).block(Instant::now() + self.t.refused_pause);
                    return Err((attempt, msg));
                }
            }
        }
    }

    // ---------------------------------------------------------------- now (exit, crash, alert-test, notify)

    /// Everything not delivered yet, oldest first: the message in flight, the batch, the queue, the held transitions. The
    /// sender's message in flight becomes the caller's (`gen`: the sender counts nothing for it)
    fn take_undelivered(&self) -> Vec<Alert> {
        let mut out = Vec::new();
        if let Some(mut w) = lock_briefly(&self.work) {
            let n = (w.in_flight.len() + w.batch.len()) as u64;
            out.append(&mut w.in_flight);
            out.append(&mut w.batch);
            w.gen = w.gen.wrapping_add(1);
            sub_sat(&self.c.pending, n);
        }
        while let Ok(a) = self.rx.try_recv() { sub_sat(&self.c.queued, 1); out.push(a); }
        if let Some(mut d) = lock_briefly(&self.dd) {
            for f in d.fams.values_mut() { if let Some(p) = f.pending.take() { out.push(p); } }
            self.held_now.store(0, Relaxed);
        }
        out.sort_by_key(|a| a.t_ns);
        out
    }

    /// alerts the exit path could not send, back at the front of the batch for the next try (the sender, or the exit)
    fn requeue(&self, mut list: Vec<Alert>) {
        if list.is_empty() { return; }
        match lock_briefly(&self.work) {
            Some(mut w) => {
                self.c.pending.fetch_add(list.len() as u64, Relaxed);
                list.append(&mut w.batch);
                w.batch = list;
            }
            None => { self.c.dropped.fetch_add(list.len() as u64, Relaxed); }
        }
    }

    /// Send `first` (whatever its level: the callers choose), then everything not delivered yet, now, from a thread of
    /// its own with its own runtime (the caller may be in a runtime, or a panicking main thread), waiting at most `wait`:
    /// the chat's rate first when its wait fits, a 429's `retry_after` once when it fits. At most three messages; what
    /// does not go out goes back for the next try (the sender, or the exit). Ok(alerts sent) or Err((alerts sent, why))
    pub fn deliver_now(&self, first: Vec<Alert>, wait: Duration) -> Result<usize, (usize, String)> {
        let Some(creds) = &self.creds else { return Err((0, format!("alerts are off: {}", self.off_why.as_deref().unwrap_or("?")))) };
        let mut list = first;
        list.extend(self.take_undelivered());
        if list.is_empty() { return Ok(0); }
        let label = label_of(&self.ctx_briefly());
        let now = real_ns();
        let mut msgs: Vec<(String, usize)> = Vec::new();
        let mut i = 0;
        while i < list.len() && msgs.len() < MAX_EXIT_MESSAGES {
            let (t, n) = format::compose(&label, now, &list[i..], format::MAX_TEXT);
            if n == 0 { break; }
            msgs.push((telegram::strip_token(&t, &creds.token), n));
            i += n;
        }
        let chat = lock_briefly(&creds.chat).map(|c| c.clone()).unwrap_or_default();
        let (token, base, rate) = (creds.token.clone(), creds.base.clone(), self.rate.clone());
        let deadline = Instant::now() + wait;
        let (tx, rx) = crossbeam_channel::bounded::<(usize, u64, Option<String>)>(1);
        let spawned = std::thread::Builder::new().name("arbx-alert-now".into()).spawn(move || {
            let r = match tokio::runtime::Builder::new_current_thread().enable_all().build() {
                Err(e) => (0, 0, Some(format!("a runtime: {e}"))),
                Ok(rt) => rt.block_on(async move {
                    let c = match telegram::client(wait, !base.starts_with("http://")) { Ok(c) => c, Err(e) => return (0, 0, Some(e)) };
                    let (mut sent, mut messages) = (0usize, 0u64);
                    for (m, n) in msgs {
                        // the chat's rate (the sender's 429s and window), when its wait fits ours
                        let w = lock_briefly(&rate).and_then(|mut r| r.wait(Instant::now()));
                        if let Some(w) = w.filter(|w| Instant::now() + *w < deadline) { tokio::time::sleep(w).await; }
                        let mut tries = 0;
                        let res = loop {
                            tries += 1;
                            let r = match telegram::post(&c, &base, &token, &chat, &m, true).await {
                                Err(PostErr::Parse(_)) => telegram::post(&c, &base, &token, &chat, &format::to_plain(&m), false).await,
                                r => r,
                            };
                            match r {
                                Ok(_) => break Ok(()),
                                Err(PostErr::RetryAfter(d, e)) => {
                                    if let Some(mut g) = lock_briefly(&rate) { g.block(Instant::now() + d); }
                                    if tries == 1 && Instant::now() + d < deadline { tokio::time::sleep(d).await; continue; }
                                    break Err(e);
                                }
                                Err(e) => break Err(e.text().to_string()),
                            }
                        };
                        match res {
                            Ok(()) => { sent += n; messages += 1; if let Some(mut g) = lock_briefly(&rate) { g.note(Instant::now()); } }
                            Err(e) => return (sent, messages, Some(e)),
                        }
                    }
                    (sent, messages, None)
                }),
            };
            let _ = tx.send(r);
        });
        if spawned.is_err() { self.requeue(list); return Err((0, "could not start the sending thread".into())); }
        let (sent, messages, err) = rx.recv_timeout(wait + Duration::from_millis(250)).unwrap_or_else(|_| (0, 0, Some(format!("no answer within {} ms", wait.as_millis()))));
        let sent = sent.min(list.len());
        self.c.sent.fetch_add(sent as u64, Relaxed);
        self.c.messages.fetch_add(messages, Relaxed);
        if messages > 0 {
            self.c.coalesced.fetch_add((sent as u64).saturating_sub(messages), Relaxed);
            self.c.last_sent_ns.store(real_ns(), Relaxed);
        }
        // what did not go out (a failed message, or more than three) goes back for the next try
        let unsent = list.split_off(sent);
        self.requeue(unsent);
        match err {
            None => Ok(sent),
            Some(e) => {
                let e = self.redact(&e);
                self.c.attempts_failed.fetch_add(1, Relaxed);
                self.set_error(&e);
                Err((sent, e))
            }
        }
    }

    /// The end of a run (after stop.json): the stop message with the last status line's numbers (when its level passes
    /// `min_level`; after a panic the crash alert tells it, and is among the undelivered ones when the panic hook could
    /// not send it), then whatever is undelivered. Once. What still does not go out is lost with the process
    /// (`failed_total`)
    pub fn exit(&self, code: i32, reason: &str, detail: &str, secondary: Option<(&str, &str)>) -> Option<Result<usize, (usize, String)>> {
        if self.creds.is_none() || self.exit_sent.swap(true, Relaxed) { return None; }
        let ctx = self.ctx_briefly();
        let snap = ctx.dir.as_ref().and_then(|d| summary::last_status(&d.join("status.jsonl"))).map(|v| Snapshot::of(&v));
        let ran = (ctx.started_ns > 0).then(|| real_ns().saturating_sub(ctx.started_ns) / 1_000_000_000);
        let mut first = Vec::new();
        if !(reason == "panic" && self.crash_tried.load(Relaxed)) {
            let label = label_of(&ctx);
            let second = secondary.map(|(r, d)| (r.to_string(), self.redact(d)));
            let st = stop_alert(&label, reason, &self.redact(detail), code, second.as_ref().map(|(r, d)| (r.as_str(), d.as_str())), ran, snap.as_ref());
            if st.level >= self.min_level { first.push(st); }
        }
        let r = self.deliver_now(first, EXIT_WAIT);
        let left = self.take_undelivered().len() as u64;
        self.c.failed.fetch_add(left, Relaxed);
        Some(r)
    }

    /// A panic: on the main thread (the engine's: the run ends) a Critical alert now, waiting at most [`CRASH_WAIT`] (if
    /// it does not go out, it is put back and the exit sends it); elsewhere (a task, a writer: the run goes on) an Error
    /// alert through the queue, never waiting
    pub fn on_panic(&self, thread: &str, at: &str, msg: &str) {
        if self.creds.is_none() { return; }
        let text = self.redact(&format!("{at}: {msg}"));
        if thread == "main" {
            if self.crash_tried.swap(true, Relaxed) { return; }
            let a = Alert::new(Level::Critical, "crash", "crash", &format!("CRASH: {} panicked (thread main)", label_of(&self.ctx_briefly()))).icon("🚨").once()
                .body(Body::new().code("", &text));
            let _ = self.deliver_now(vec![a], CRASH_WAIT);
        } else {
            self.raise(Alert::new(Level::Error, "panic", format!("panic:{thread}:{at}"), &format!("panic in thread {thread} (the run goes on)")).body(Body::new().code("", &text)));
        }
    }

    // ---------------------------------------------------------------- watchers (rt_bg)

    /// Watch the SendGate (every second) and alert on every change of mode or reason after the first look, with its reason
    /// (a stop is left to the stop message). Lock-free while nothing changes: it compares the gate's change count and
    /// reads the gate (under its lock) only after a change, because the engine takes that lock on every send decision and
    /// this task runs on the niced rt_bg (a watcher preempted while holding it would stall the engine)
    pub fn watch_gate(self: &Arc<Self>, rt: &tokio::runtime::Handle, gate: Arc<crate::control::SendGate>, stop: Arc<AtomicBool>) {
        if self.creds.is_none() { return; }
        let me = self.clone();
        rt.spawn(async move {
            let mut last: Option<(String, String)> = None;
            let mut seen: Option<u64> = None;
            loop {
                let n = gate.changes();
                if seen != Some(n) {
                    seen = Some(n);
                    let g = gate.json();
                    let cur = (g["mode"].as_str().unwrap_or("?").to_string(), g["reason"].as_str().unwrap_or("").to_string());
                    if let Some(prev) = &last {
                        if *prev != cur {
                            if let Some(a) = gate_alert(prev, &cur.0, &cur.1, g["detail"].as_str().unwrap_or(""), g["sticky"] == json!(true)) { me.raise(a); }
                        }
                    }
                    last = Some(cur);
                }
                if gate.mode() == crate::control::GateMode::Stopped || stop.load(Relaxed) { break; }
                tokio::time::sleep(Duration::from_secs(1)).await;
            }
        });
    }

    /// The monitor of a segment (every 15 s; its file reads on `rt`'s blocking pool): from the segment's last status
    /// line, a stale blockhash, the executor's failed-fee cap (the budget floor), a low balance; from the RPC registry, a
    /// provider's 429 storm; the heartbeat every `heartbeat_min` with the numbers of that period across segments, and the
    /// daily summary (markers in the runs directory)
    pub fn start_monitor(self: &Arc<Self>, rt: &tokio::runtime::Handle, stop: Arc<AtomicBool>) {
        if self.creds.is_none() { return; }
        let me = self.clone();
        rt.spawn(async move {
            let mut m = Monitor::default();
            while !stop.load(Relaxed) {
                tokio::time::sleep(MONITOR_EVERY).await;
                if stop.load(Relaxed) { break; }
                let ctx = me.ctx();
                let every = me.cfg.heartbeat_min.saturating_mul(60_000_000_000);
                let daily = me.cfg.daily_summary;
                let c2 = ctx.clone();
                // the file reads, off the runtime's workers: the last status line, the heartbeat's period, the day before
                let read = tokio::task::spawn_blocking(move || {
                    let snap = c2.dir.as_ref().and_then(|d| summary::last_status(&d.join("status.jsonl"))).map(|v| Snapshot::of(&v));
                    let now = real_ns();
                    let beat = match (&c2.runs_dir, &snap) {
                        (Some(r), Some(_)) if every > 0 && summary::heartbeat_due(r, every, now) => Some(summary::totals(r, now.saturating_sub(every), now)),
                        _ => None,
                    };
                    let day = c2.runs_dir.as_ref().filter(|_| daily).and_then(|r| summary::daily_due(r, now).map(|(_, start)| summary::day_totals(r, start)));
                    (snap, beat, day)
                }).await;
                let Ok((snap, beat, day)) = read else { continue };
                if let Some(s) = &snap { for a in m.check(s, &ctx, &me.cfg, Instant::now()) { me.raise(a); } }
                for a in m.rpc_storms(&crate::rpc::Registry::global().totals(), Instant::now()) { me.raise(a); }
                if let (Some(s), Some(w)) = (&snap, &beat) {
                    let mode = ctx.seg.as_ref().map_or("?".to_string(), |x| x.mode.clone());
                    let up = real_ns().saturating_sub(ctx.started_ns) / 1_000_000_000;
                    me.raise(heartbeat_alert(&label_of(&ctx), &mode, up, s, w, me.cfg.heartbeat_min * 60, me.c.sent.load(Relaxed)));
                }
                if let Some(t) = day.filter(|t| t.segments > 0 || t.crashes > 0) { me.raise(daily_alert(&t)); }
            }
        });
    }
}

/// The monitor's memory between two status lines
#[derive(Default)]
struct Monitor {
    stale: u32,
    stale_told: bool,
    bh_seen: bool,
    stopped_told: Option<String>,
    first_ok: Option<Instant>,
    rpc: VecDeque<(Instant, HashMap<String, u64>)>,
}

impl Monitor {
    /// alerts from one status line: a stale blockhash (two reads in a row while the state is fine; recovery told; "none
    /// at all" only for a segment that sends: a shadow run without a blockhash source is no fault), the executor stopping
    /// on its failed-fee cap (the budget floor), a low balance
    fn check(&mut self, s: &Snapshot, ctx: &Ctx, cfg: &AlertsCfg, now: Instant) -> Vec<Alert> {
        let mut out = Vec::new();
        let max = ctx.max_blockhash_age_slots;
        let sends = ctx.seg.as_ref().is_some_and(|x| x.mode == "live" || x.mode == "canary");
        if s.state_ok == Some(true) && max > 0 {
            self.first_ok.get_or_insert(now);
            let age = s.blockhash_age_slots;
            if age.is_some() { self.bh_seen = true; }
            let stale = match age {
                Some(a) => a > max,
                None => self.bh_seen || (sends && self.first_ok.is_some_and(|t| now.saturating_duration_since(t) > Duration::from_secs(120))),
            };
            if stale { self.stale += 1; } else {
                if self.stale_told {
                    out.push(Alert::new(Level::Info, "blockhash_fresh", "blockhash_ok", "blockhash fresh again").icon("✅").family("blockhash")
                        .body(Body::new().kv("age", age.map_or("?".into(), |a| format!("{a} slots")))));
                }
                self.stale = 0;
                self.stale_told = false;
            }
            if self.stale >= 2 && !self.stale_told {
                self.stale_told = true;
                let what = match age { Some(a) => format!("{a} slots old (max {max})"), None => "none".into() };
                out.push(Alert::new(Level::Warning, "blockhash_stale", "blockhash_stale", &format!("stale blockhash: {what}: sends are refused (blockhash_stale)"))
                    .family("blockhash"));
            }
        }
        if let Some(why) = &s.sender_stopped {
            if self.stopped_told.as_deref() != Some(why.as_str()) {
                self.stopped_told = Some(why.clone());
                // WP-05's `exec.stopped`: a fee or spend cap is the budget floor; a canary's count is the canary's end
                if why.contains("cap") {
                    let b = BudgetFloor { what: "failed_fee_cap".into(), value_lamports: s.failed_fees.unwrap_or(0) as i64, floor_lamports: s.fee_cap.unwrap_or(0) as i64,
                        detail: Some(format!("the executor stopped sending: {why}")) };
                    out.push(budget_floor_alert(&b));
                } else {
                    out.push(Alert::new(Level::Info, "sender_stopped", format!("sender_stopped:{why}"), &format!("sending stopped: {why}")).icon("⏹")
                        .body(Body::new().kv("sent", s.sends.map_or("?".into(), int)).kv("wins", s.wins.map_or("?".into(), int))));
                }
            }
        }
        let floor = (cfg.low_balance_sol * 1e9) as u64;
        if let Some(b) = s.balance_lamports.filter(|b| floor > 0 && *b < floor) {
            out.push(low_balance_alert(&LowBalance { what: "liquid SOL + WSOL".into(), lamports: b, warn_below_lamports: floor }));
        }
        out
    }

    /// a provider's rate-limited answers over the last minute (the registry's totals, kept for about 70 s): a 429 storm
    fn rpc_storms(&mut self, totals: &std::collections::BTreeMap<(crate::rpc::Role, String), crate::rpc::Totals>, now: Instant) -> Vec<Alert> {
        let mut by: HashMap<String, u64> = HashMap::new();
        for ((_, p), t) in totals { *by.entry(p.clone()).or_default() += t.rate_limited; }
        let mut out = Vec::new();
        if let Some((t0, old)) = self.rpc.iter().find(|(t, _)| now.saturating_duration_since(*t) <= Duration::from_secs(70)) {
            let secs = now.saturating_duration_since(*t0).as_secs().max(1);
            for (p, n) in &by {
                let d = n.saturating_sub(old.get(p).copied().unwrap_or(0));
                if d >= STORM_RPC_429 && secs >= 30 {
                    out.push(Alert::new(Level::Warning, "rpc_storm", format!("storm:429:{p}"), &format!("rate-limit (429) storm: {p} refused {d} calls in {secs} s")).icon("🌩"));
                }
            }
        }
        self.rpc.push_back((now, by));
        while self.rpc.front().is_some_and(|(t, _)| now.saturating_duration_since(*t) > Duration::from_secs(70)) { self.rpc.pop_front(); }
        out
    }
}

// ------------------------------------------------------------------ the process's alerts

static GLOBAL: OnceLock<Arc<Alerts>> = OnceLock::new();

/// make `a` the process's alerts (what the free functions use). Once: false when another was installed first
pub fn install(a: Arc<Alerts>) -> bool { GLOBAL.set(a).is_ok() }
pub fn global() -> Option<&'static Arc<Alerts>> { GLOBAL.get() }

/// [`Alerts::raise`] on the process's alerts (a no-op without them)
pub fn raise(a: Alert) -> bool { global().is_some_and(|g| g.raise(a)) }
/// WP-05 merge hook: a landing whose route succeeded (never waits)
pub fn win(w: Win) -> bool { global().is_some_and(|g| g.win(&w)) }
/// WP-05 merge hook: a landed transaction that failed (never waits)
pub fn failed_landing(f: FailedLanding) -> bool { global().is_some_and(|g| g.failed_landing(&f)) }
/// WP-07 merge hook: a realised loss (never waits)
pub fn loss(l: Loss) -> bool { global().is_some_and(|g| g.loss(&l)) }
/// WP-05 / WP-07 merge hook: a budget or equity floor reached (never waits)
pub fn budget_floor(b: BudgetFloor) -> bool { global().is_some_and(|g| g.budget_floor(&b)) }
/// WP-07 merge hook: a balance under its warning level (never waits)
pub fn low_balance(b: LowBalance) -> bool { global().is_some_and(|g| g.low_balance(&b)) }
/// WP-07 merge hook: one of its notices (`notify::set_hook`; [`notice_alert`]; never waits)
pub fn notice(level: Level, kind: &'static str, subject: &str, text: &str) -> bool { global().is_some_and(|g| g.notice(level, kind, subject, text)) }
/// the feeds' hook: a gRPC stream's failed connection (never waits)
pub fn note_stream_error(stream: &str, msg: &str) { if let Some(g) = global() { g.note_stream_error(stream, msg); } }
/// status.jsonl `alerts`: null without alerts
pub fn status() -> Value { global().map_or(Value::Null, |g| g.status_json()) }

/// The end of `arbx run` (main.rs `end_run`, after stop.json is written): the stop message and what is still queued,
/// sent from a helper thread, at most [`EXIT_WAIT`]
pub fn on_exit(code: i32, reason: &str, detail: &str, secondary: Option<(&str, &str)>) {
    if let Some(g) = global() { let _ = g.exit(code, reason, detail, secondary); }
}

/// A panic hook in front of the one installed (the stop path's: stop.json first): a panic on the main thread sends a
/// Critical alert (best effort, at most [`CRASH_WAIT`]; the exit sends it again if it could not); one on another thread
/// an Error alert through the queue. It does nothing without alerts, and nothing in it can panic in turn
pub fn install_panic_hook() {
    let prev = std::panic::take_hook();
    std::panic::set_hook(Box::new(move |p| {
        prev(p);
        let Some(a) = global() else { return };
        let msg = p.payload().downcast_ref::<&str>().map(|s| s.to_string()).or_else(|| p.payload().downcast_ref::<String>().cloned()).unwrap_or_else(|| "?".into());
        let at = p.location().map(|l| format!("{}:{}", l.file(), l.line())).unwrap_or_default();
        let thread = std::thread::current().name().unwrap_or("unnamed").to_string();
        a.on_panic(&thread, &at, &msg);
    }));
}

/// `arbx notify`: an operator's note to the chat now (a field test's goal at its start, its result at its end:
/// docs/field-tests/README.md), whatever `[alerts] enabled` and `min_level` say. Its first line is the title, the rest
/// the body; all of it is text (escaped: no markup). Ok(a line to print) or Err(why), never naming the token or the chat
pub fn send_note(cfg: &AlertsCfg, env: &dyn Fn(&str) -> Option<String>, text: &str, wait: Duration) -> Result<String, String> {
    let on = AlertsCfg { enabled: true, ..cfg.clone() };
    let (a, _) = Alerts::new(&on, env, Ctx { label: "note".into(), ..Default::default() });
    if !a.enabled() { return Err(a.off_why().unwrap_or("off").to_string()); }
    let (title, rest) = text.trim().split_once('\n').unwrap_or((text.trim(), ""));
    if title.trim().is_empty() { return Err("an empty note".into()); }
    let mut b = Body::new();
    for l in rest.lines().filter(|l| !l.trim().is_empty()).take(30) { b = b.txt(l.trim()).nl(); }
    let n = Alert::new(Level::Info, "note", "note", title.trim()).icon("📝").once().body(b);
    match a.deliver_now(vec![n], wait) {
        Ok(k) if k > 0 => Ok(format!("ok: the note was sent (token from {}, chat from {})", cfg.token_env, cfg.chat_env)),
        Ok(_) => Err("nothing was sent".into()),
        Err((_, e)) => Err(e),
    }
}

/// the production environment lookup: a variable's value, trimmed (None when unset or empty)
pub fn env_var(k: &str) -> Option<String> { std::env::var(k).ok().map(|v| v.trim().to_string()).filter(|v| !v.is_empty()) }

/// `arbx alert-test`: one test message now (whatever `[alerts] enabled` and `min_level` say), waiting at most `wait`.
/// Ok(a line to print) or Err(why), never naming the token or the chat id
pub fn send_test(cfg: &AlertsCfg, env: &dyn Fn(&str) -> Option<String>, what: &str, wait: Duration) -> Result<String, String> {
    let on = AlertsCfg { enabled: true, ..cfg.clone() };
    let (a, notes) = Alerts::new(&on, env, Ctx { label: "alert-test".into(), ..Default::default() });
    if !a.enabled() { return Err(a.off_why().unwrap_or("off").to_string()); }
    for n in notes.iter().filter(|n| n.starts_with("WARNING")) { crate::rec::err_line(n); }
    let t = Alert::new(Level::Info, "alert_test", "alert_test", "alert test: if you read this, alerts work").icon("🔔").once().body(Body::new().txt(what));
    match a.deliver_now(vec![t], wait) {
        Ok(n) if n > 0 => Ok(format!("ok: the test message was sent (token from {}, chat from {})", cfg.token_env, cfg.chat_env)),
        Ok(_) => Err("nothing was sent".into()),
        Err((_, e)) => Err(e),
    }
}

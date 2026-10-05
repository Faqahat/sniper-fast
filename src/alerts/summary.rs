//! What the alerts read back from the records, so that nothing has to be handed to them from the engine thread: a
//! status line's key numbers ([`Snapshot`]), the last line of a segment's status.jsonl ([`last_status`]), a UTC day's
//! totals over a runs directory ([`day_totals`], the daily summary), and the marker files that make one process send
//! each heartbeat and each daily summary when several segments and the watchdog share a runs directory.
//!
//! Wins and sends (docs/STAGE1-PLAN.md §1, "What you will see"): a win is a landed bundle whose route succeeded
//! (`exec.ok_total`); sends are live bundles sent, `exec.sent_total` only (WP-05): never `attempts_total`, which counts
//! would-sends that were never sent. The net is after fees, tips and rent (Stage-1 plan review F12: 12 of the old bot's
//! 23 "wins" lost SOL to account rent) and from chain data only: WP-07's chain ledger, `money.trade_net_total −
//! money.rent_nonrecoverable_total` (MEASUREMENT §4.42: `trade_net` = trade_gross − fee − tip; non-recoverable rent is
//! its own expense line), else WP-05's counters from our wallet's transaction records, `round_trip_total_lamports −
//! tips_paid_total_lamports − fees_landed_total_lamports − rent` (rent: `new_token_accounts_total` ×
//! [`ATA_RENT_LAMPORTS`], an estimate; partial while `round_trip_unknown_total` > 0). A line with neither has no net.
//! With the ledger on, WP-07 moves WP-05's money counters under `money.bot`: every executor counter is read at
//! `money.<name>`, else at `money.bot.<name>`; the ledger's own fees and tips (`fees_win_total` + `fees_fail_total`,
//! `tips_total`) and test budget (`budget_left_now`) come first.
use serde_json::Value;
use std::path::{Path, PathBuf};

pub const DAY_NS: u64 = 86_400_000_000_000;
/// the rent one new token account locks, for the estimate while the ledger has none: the larger of an SPL account's
/// (1,488,440 lamports) and a Token-2022 account's (1,513,840; PLAN-ADDENDUM go-live gate), so an estimated net is never
/// overstated. WP-06's create+close in the same transaction leaves none locked
pub const ATA_RENT_LAMPORTS: u64 = 1_513_840;

/// A status line's key numbers (MEASUREMENT §4.8); None where the line does not have them
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Snapshot {
    pub t_ns: u64,
    pub run_s: Option<f64>,
    pub seq: Option<u64>,
    pub slot: Option<u64>,
    pub tip: Option<u64>,
    pub gate_mode: Option<String>,
    pub gate_reason: Option<String>,
    pub state_ok: Option<bool>,
    pub shut: Option<String>,
    pub recorder_ok: Option<bool>,
    pub decisions: Option<u64>,
    pub would_send: Option<u64>,
    pub opportunities: Option<u64>,
    pub sends: Option<u64>,
    pub landed: Option<u64>,
    pub wins: Option<u64>,
    pub net_lamports: Option<i64>,
    /// some wins' round trips were not known yet: the net counts them as 0
    pub net_partial: bool,
    /// where the net comes from: `ledger` (WP-07) or `wallet records` (WP-05's counters)
    pub net_src: Option<&'static str>,
    /// fees of landed transactions, tips paid, rent of new accounts (lamports; `rent_estimated`: from the count of new
    /// token accounts, not the ledger)
    pub fees_lamports: Option<u64>,
    pub tips_lamports: Option<u64>,
    pub rent_lamports: Option<u64>,
    pub rent_estimated: bool,
    pub failed_fees: Option<u64>,
    pub fee_cap: Option<u64>,
    /// WP-07: the campaign's test budget left (`money.budget_left_now`, equity-based), lamports
    pub budget_left_now: Option<i64>,
    /// why the executor stopped sending (`failed-fee cap reached`, ...)
    pub sender_stopped: Option<String>,
    pub blockhash_age_slots: Option<u64>,
    pub jito_token_age_s: Option<u64>,
    /// the liquid balance (WP-07 `money.equity_liquid_now`), lamports
    pub balance_lamports: Option<u64>,
    pub stop_reason: Option<String>,
}

fn at<'a>(v: &'a Value, path: &[&str]) -> Option<&'a Value> {
    let mut x = v;
    for k in path { x = x.get(*k)?; }
    (!x.is_null()).then_some(x)
}

impl Snapshot {
    pub fn of(v: &Value) -> Snapshot {
        let u = |p: &[&str]| at(v, p).and_then(Value::as_u64);
        let i = |p: &[&str]| at(v, p).and_then(|x| x.as_i64().or_else(|| x.as_u64().map(|n| n.min(i64::MAX as u64) as i64)));
        let s = |p: &[&str]| at(v, p).and_then(Value::as_str).map(str::to_string);
        let b = |p: &[&str]| at(v, p).and_then(Value::as_bool);
        // the executor's money counter `k` (WP-05): at `money.k`, or at `money.bot.k` once WP-07's ledger owns `money`
        let mu = |k: &str| u(&["money", k]).or_else(|| u(&["money", "bot", k]));
        let mi = |k: &str| i(&["money", k]).or_else(|| i(&["money", "bot", k]));
        // tips and fees: the ledger's (WP-07) first, else the executor's
        let tips_lamports = u(&["money", "tips_total"]).or_else(|| mu("tips_paid_total_lamports"));
        let fees_lamports = match (u(&["money", "fees_win_total"]), u(&["money", "fees_fail_total"])) {
            (None, None) => mu("fees_landed_total_lamports"),
            (w, f) => Some(w.unwrap_or(0).saturating_add(f.unwrap_or(0))),
        };
        let failed = u(&["money", "failed_fees_total_lamports"]);
        // rent: the ledger's non-recoverable rent when it has one (WP-07), else the new token accounts' (an estimate)
        let ledger_rent = u(&["money", "rent_nonrecoverable_total"]);
        let (rent_lamports, rent_estimated) = match (ledger_rent, mu("new_token_accounts_total")) {
            (Some(r), _) => (Some(r), false),
            (None, Some(n)) => (Some(n.saturating_mul(ATA_RENT_LAMPORTS)), true),
            (None, None) => (None, false),
        };
        let (tips, fees, rent) = (tips_lamports.unwrap_or(0) as i128, fees_lamports.unwrap_or(0) as i128, rent_lamports.unwrap_or(0) as i128);
        // the net after fees, tips and rent: the ledger's trade net (gross − fee − tip) less its non-recoverable rent, else
        // the executor's round trips less tips, fees and the rent estimate
        let (net_lamports, net_partial, net_src) = if let Some(n) = i(&["money", "trade_net_total"]) {
            (Some(super::clamp_i64(n as i128 - ledger_rent.unwrap_or(0) as i128)), false, Some("ledger"))
        } else if let Some(rt) = mi("round_trip_total_lamports") {
            (Some(super::clamp_i64(rt as i128 - tips - fees - rent)), mu("round_trip_unknown_total").unwrap_or(0) > 0, Some("wallet records"))
        } else {
            (None, false, None)
        };
        Snapshot {
            t_ns: u(&["t_ns"]).unwrap_or(0),
            run_s: at(v, &["run_s"]).and_then(Value::as_f64),
            seq: u(&["seq"]),
            slot: u(&["slot", "processed"]),
            tip: u(&["slot", "tip"]).or(u(&["slot", "processed"])),
            gate_mode: s(&["send_gate", "mode"]),
            gate_reason: s(&["send_gate", "reason"]),
            state_ok: b(&["health", "state_ok"]),
            shut: s(&["health", "shut"]),
            recorder_ok: b(&["health", "recorder_ok"]),
            decisions: u(&["exec", "decisions_total"]).or(u(&["counts_total", "evaluation"])),
            would_send: u(&["exec", "would_send_total"]),
            opportunities: u(&["counts_total", "state_opportunity"]),
            sends: u(&["exec", "sent_total"]),
            landed: u(&["exec", "landed_total"]),
            wins: u(&["exec", "ok_total"]),
            net_lamports,
            net_partial,
            net_src,
            fees_lamports,
            tips_lamports,
            rent_lamports,
            rent_estimated,
            failed_fees: failed,
            fee_cap: mu("failed_fees_cap_now_lamports"),
            budget_left_now: i(&["money", "budget_left_now"]),
            sender_stopped: s(&["exec", "stopped"]),
            blockhash_age_slots: u(&["health", "blockhash_age_slots_now"]),
            jito_token_age_s: u(&["health", "jito_token_age_s_now"]),
            balance_lamports: u(&["money", "equity_liquid_now"]),
            stop_reason: s(&["stop_reason"]),
        }
    }

    /// the budget left, lamports: WP-07's test budget (`money.budget_left_now`) when the line has it, else what is left of
    /// the executor's failed-fee cap (cap − spent)
    pub fn budget_left(&self) -> Option<i64> {
        self.budget_left_now.or_else(|| self.fee_cap.map(|c| super::clamp_i64(c as i128 - self.failed_fees.unwrap_or(0) as i128)))
    }
}

/// a status.jsonl header line (`{"schema":"arbx.status/...","file_seq":..}`), not a status line
fn is_header(v: &Value) -> bool { v["schema"].as_str().is_some_and(|s| s.starts_with("arbx.")) && v.get("file_seq").is_some() }

/// The last status line of a status.jsonl (its last 512 KiB read; a torn last line skipped), None without one
pub fn last_status(path: &Path) -> Option<Value> {
    use std::io::{Read, Seek, SeekFrom};
    let mut f = std::fs::File::open(path).ok()?;
    let len = f.metadata().ok()?.len();
    f.seek(SeekFrom::Start(len.saturating_sub(512 * 1024))).ok()?;
    let mut b = Vec::new();
    f.take(512 * 1024).read_to_end(&mut b).ok()?;
    String::from_utf8_lossy(&b).lines().rev().filter_map(|l| serde_json::from_str::<Value>(l).ok()).find(|v| v.is_object() && !is_header(v))
}

/// every status line of a status.jsonl (headers and unreadable lines left out)
pub fn status_lines(path: &Path) -> Vec<Value> {
    let Ok(t) = std::fs::read_to_string(path) else { return Vec::new() };
    t.lines().filter_map(|l| serde_json::from_str::<Value>(l).ok()).filter(|v| v.is_object() && !is_header(v)).collect()
}

/// The segment directories of a runs directory: its subdirectories that hold a status.jsonl or a run.log, and those of
/// its subdirectories (campaigns: `runs/<campaign>/<campaign>-p<i>/`)
pub fn segment_dirs(runs_dir: &Path) -> Vec<PathBuf> {
    let is_seg = |d: &Path| d.join("status.jsonl").is_file() || d.join("run.log").is_file();
    let mut out = Vec::new();
    for e in std::fs::read_dir(runs_dir).into_iter().flatten().flatten() {
        let p = e.path();
        if !p.is_dir() { continue; }
        if is_seg(&p) { out.push(p); continue; }
        for e2 in std::fs::read_dir(&p).into_iter().flatten().flatten() {
            let q = e2.path();
            if q.is_dir() && is_seg(&q) { out.push(q); }
        }
    }
    out.sort();
    out
}

fn mtime_ns(p: &Path) -> Option<u64> {
    std::fs::metadata(p).ok()?.modified().ok()?.duration_since(std::time::UNIX_EPOCH).ok().map(|d| d.as_nanos() as u64)
}

/// One UTC day's totals over every segment of a runs directory (the daily summary)
#[derive(Clone, Debug, Default, PartialEq)]
pub struct DayTotals {
    pub day: String,
    /// segments with a status line in the period; segments that ended in it as a crash (stop.json `error`, `panic`,
    /// `state_unavailable`), a boot that failed before any status line included
    pub segments: u32,
    pub crashes: u32,
    /// wins: landed bundles whose route succeeded; sends: live bundles sent, `exec.sent_total` only (the win ratio is
    /// wins ÷ sends; `sends_known`: some segment's lines have `sent_total`)
    pub decisions: u64,
    pub would_send: u64,
    pub sends: u64,
    pub landed: u64,
    pub wins: u64,
    /// the net over the segments whose lines have one (`net_known`), partial when a win's round trip was unknown
    pub net_lamports: i64,
    pub net_known: bool,
    pub net_partial: bool,
    /// `ledger` when every segment's net came from WP-07's ledger, else `wallet records`
    pub net_src: Option<&'static str>,
    pub sends_known: bool,
    pub failed_fees: u64,
    /// fees of landed transactions, tips paid, rent of new accounts (`rent_estimated`: from the count of new accounts)
    pub fees: u64,
    pub tips: u64,
    pub rent: u64,
    pub rent_estimated: bool,
    /// the newest segment's failed-fee budget left at the day's end
    pub budget_left: Option<i64>,
    pub last_segment: Option<String>,
}

/// The day starting at `day_start_ns` (UTC midnight): [`totals`] over it, named by its date
pub fn day_totals(runs_dir: &Path, day_start_ns: u64) -> DayTotals {
    let mut t = totals(runs_dir, day_start_ns, day_start_ns + DAY_NS);
    t.day = super::format::utc_date(day_start_ns);
    t
}

/// The totals of the period [`from_ns`, `to_ns`) over every segment of a runs directory, from each segment's status
/// lines: a `_total` counter's period value is its last value in the period minus its last value before it (MEASUREMENT
/// §2.2: totals are never summed across lines). Crashes come from stop.json alone (a boot that failed before the engine
/// started has no status line)
pub fn totals(runs_dir: &Path, from_ns: u64, to_ns: u64) -> DayTotals {
    let mut t = DayTotals::default();
    let mut newest: Option<(u64, Option<i64>, String)> = None;
    for dir in segment_dirs(runs_dir) {
        let stop = dir.join("stop.json");
        if mtime_ns(&stop).is_some_and(|m| m >= from_ns) {
            if let Some(v) = std::fs::read_to_string(&stop).ok().and_then(|s| serde_json::from_str::<Value>(&s).ok()) {
                let ended = v["ended_ns"].as_u64().unwrap_or(0);
                if (from_ns..to_ns).contains(&ended) && matches!(v["reason"].as_str(), Some("error" | "panic" | "state_unavailable")) { t.crashes += 1; }
            }
        }
        let st = dir.join("status.jsonl");
        if mtime_ns(&st).is_none_or(|m| m < from_ns) { continue; }
        let lines: Vec<Snapshot> = status_lines(&st).iter().map(Snapshot::of).collect();
        let Some(last) = lines.iter().filter(|s| s.t_ns >= from_ns && s.t_ns < to_ns).last() else { continue };
        let base = lines.iter().filter(|s| s.t_ns < from_ns).last().cloned().unwrap_or_default();
        let d = |a: Option<u64>, b: Option<u64>| a.unwrap_or(0).saturating_sub(b.unwrap_or(0));
        t.segments += 1;
        t.decisions = t.decisions.saturating_add(d(last.decisions, base.decisions));
        t.would_send = t.would_send.saturating_add(d(last.would_send, base.would_send));
        t.sends = t.sends.saturating_add(d(last.sends, base.sends));
        t.sends_known |= last.sends.is_some();
        t.landed = t.landed.saturating_add(d(last.landed, base.landed));
        t.wins = t.wins.saturating_add(d(last.wins, base.wins));
        t.failed_fees = t.failed_fees.saturating_add(d(last.failed_fees, base.failed_fees));
        t.fees = t.fees.saturating_add(d(last.fees_lamports, base.fees_lamports));
        t.tips = t.tips.saturating_add(d(last.tips_lamports, base.tips_lamports));
        t.rent = t.rent.saturating_add(d(last.rent_lamports, base.rent_lamports));
        t.rent_estimated |= last.rent_estimated;
        if let Some(n) = last.net_lamports {
            t.net_lamports = super::clamp_i64(t.net_lamports as i128 + n as i128 - base.net_lamports.unwrap_or(0) as i128);
            t.net_known = true;
            t.net_partial |= last.net_partial;
            // the weaker source names the sum
            if t.net_src != Some("wallet records") { t.net_src = last.net_src; }
        }
        let name = dir.file_name().map(|n| n.to_string_lossy().into_owned()).unwrap_or_default();
        if newest.as_ref().is_none_or(|n| last.t_ns > n.0) { newest = Some((last.t_ns, last.budget_left(), name)); }
    }
    if let Some((_, left, name)) = newest { t.budget_left = left; t.last_segment = Some(name); }
    t
}

/// create `<dir>/<name>` if it does not exist yet: true for the one process that created it
pub fn claim(dir: &Path, name: &str) -> bool {
    std::fs::OpenOptions::new().write(true).create_new(true).open(dir.join(name)).is_ok()
}

/// The daily summary due now, if any: the UTC day before `now_ns`'s, unless a process already claimed it (its marker
/// `.alerts-daily-<day>` in the runs directory); claiming it here. Markers older than 8 days are removed
pub fn daily_due(runs_dir: &Path, now_ns: u64) -> Option<(String, u64)> {
    let start = (now_ns / DAY_NS).checked_sub(1)? * DAY_NS;
    let day = super::format::utc_date(start);
    let marker = format!(".alerts-daily-{day}");
    if runs_dir.join(&marker).exists() || !claim(runs_dir, &marker) { return None; }
    let oldest = super::format::utc_date(start.saturating_sub(8 * DAY_NS));
    for e in std::fs::read_dir(runs_dir).into_iter().flatten().flatten() {
        let n = e.file_name().to_string_lossy().into_owned();
        if let Some(d) = n.strip_prefix(".alerts-daily-") { if d.len() == 10 && d < oldest.as_str() { let _ = std::fs::remove_file(e.path()); } }
    }
    Some((day, start))
}

/// The heartbeat marker (`.alerts-heartbeat` in the runs directory): one heartbeat every `every_ns` across segments
pub const HEARTBEAT_MARKER: &str = ".alerts-heartbeat";

/// whether a heartbeat is due at `now_ns` (the marker older than `every_ns`); a due one rewrites the marker. A
/// missing marker is written and is not due (the clock starts)
pub fn heartbeat_due(runs_dir: &Path, every_ns: u64, now_ns: u64) -> bool {
    let p = runs_dir.join(HEARTBEAT_MARKER);
    match mtime_ns(&p) {
        Some(m) if now_ns.saturating_sub(m) < every_ns => false,
        Some(_) => std::fs::write(&p, now_ns.to_string()).is_ok(),
        None => { let _ = std::fs::write(&p, now_ns.to_string()); false }
    }
}


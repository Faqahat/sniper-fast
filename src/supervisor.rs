//! The in-process supervisor (PLAN WP-07 item 5; OD-11; docs/field-tests/README.md "Enforcement"): the equity stops of a
//! segment, campaign-wide, and the money alerts. It acts through the SendGate and the Stopper only: a stop rule puts the
//! gate in shadow for the rest of the segment with the rule's name as its reason, then asks the run to stop with the
//! same name (exit 20: a safety stop, which ends the campaign); every action is an events.jsonl line and, after the
//! action, a [`crate::notify`] notice (a hook that blocks or panics cannot delay or lose a stop: review WP-07 #13).
//!
//! **What the stops measure** (review WP-07 #4; STAGE1-PLAN review F6): the **net spend** since the campaign's start,
//! from the ledger's categories (`ledger::Entry::spend`): a route's fee, tip and non-recoverable rent less its trading
//! result (its change of SOL + WSOL and of recoverable rent; a token it left behind counts 0), and any other transaction's
//! fee and non-recoverable rent. The owner's own deposits and withdrawals are not in it: a deposit extends no allowance,
//! a withdrawal trips no stop (each is recorded and alerted as `owner_transfer`). Nothing is converted at a market price.
//! - **The stop value** is the campaign's start SOL + WSOL (read from the chain at its first balance snapshot) less the
//!   net spend since; the floor and the drop caps compare it, in lamports.
//! - **Every other token** the wallet holds at the campaign's start (the frz wallet's ~22.97 USDC) has a **quantity
//!   floor**: what the routes moved of it may never take it more than `token_floor_tolerance` below its start amount
//!   (`token_floor`). Its SOL value is reported, never read by a stop. Stage 0 routes start and end in WSOL; a route
//!   through a token the wallet holds passes the amount it bought straight to its sale, so the holding does not move.
//! - **Recoverable rent** (token, nonce and lookup-table accounts) is tracked apart (status `rent_recoverable_now`, the
//!   rent cap).
//!
//! **Rules**, evaluated on every ledger change and every housekeeping tick (engine time):
//! - `equity_floor`: the stop value below the floor = the campaign's start − its test budget (the net spend past the
//!   budget; the highest of the floors given applies);
//! - `token_floor`: a token held at the start below its start amount less the tolerance;
//! - `equity_hour` (OD-11): max(stop value over [t − 1 h, t]) − stop value(t) > `max_drop_per_hour_sol`;
//! - `equity_day`: the same over 24 h > `max_drop_per_day_sol`.
//!
//! **Freshness** (review WP-07 #3): while the ledger's money view is stale (`ledger::Ledger` decides), the gate is in
//! shadow with reason `equity_stale`, lifted when it is fresh again.
//!
//! The series is campaign-wide (F8): a segment of a campaign starts from the earlier segments' ledger entries of the
//! last 24 h (`ledger::history`), so a loss split across two segments trips the rule.
use crate::config::SupervisorCfg;
use crate::control::{SendGate, StopInfo, StopReason, Stopper};
use crate::notify::{self, Level};
use crate::rec::Rec;
use serde_json::{json, Value};
use std::collections::{BTreeMap, BTreeSet, VecDeque};
use std::sync::Arc;

pub const HOUR_NS: u64 = 3_600_000_000_000;
pub const DAY_NS: u64 = 24 * HOUR_NS;

pub fn sol_to_lamports(x: f64) -> i64 { (x * 1e9).round() as i64 }

// ------------------------------------------------------------------ the equity series

/// The stop equity over time: a point at each change (a snapshot, a ledger entry), in time order. Between points the
/// value is the last point's
#[derive(Clone, Debug, Default)]
pub struct Series { pts: VecDeque<(u64, i64)> }

impl Series {
    pub fn new() -> Series { Series::default() }
    /// a value at `t` (a point out of order is put at the last point's time: the series never goes back)
    pub fn push(&mut self, t: u64, v: i64) {
        let t = self.pts.back().map_or(t, |l| t.max(l.0));
        if self.pts.back().is_some_and(|l| l.0 == t) { self.pts.pop_back(); }
        self.pts.push_back((t, v));
    }
    pub fn last(&self) -> Option<(u64, i64)> { self.pts.back().copied() }
    pub fn first(&self) -> Option<(u64, i64)> { self.pts.front().copied() }
    pub fn len(&self) -> usize { self.pts.len() }
    pub fn is_empty(&self) -> bool { self.pts.is_empty() }
    /// the value at `t`: the last point at or before it
    pub fn value_at(&self, t: u64) -> Option<i64> { self.pts.iter().rev().find(|p| p.0 <= t).map(|p| p.1) }
    /// the highest value over [from, to]: the value carried into `from` and every point after it
    pub fn max_in(&self, from: u64, to: u64) -> Option<i64> {
        let carried = self.value_at(from);
        let inside = self.pts.iter().filter(|p| p.0 > from && p.0 <= to).map(|p| p.1).max();
        match (carried, inside) { (Some(a), Some(b)) => Some(a.max(b)), (a, b) => a.or(b) }
    }
    /// how far the value at `now` is below the highest value of the `window` before it (0 or more); None: no value yet
    pub fn drop_over(&self, now: u64, window: u64) -> Option<i64> {
        let v = self.value_at(now)?;
        Some((self.max_in(now.saturating_sub(window), now)? - v).max(0))
    }
    /// forget what no window needs: points older than `keep` before `now`, except the one carried into the window
    pub fn trim(&mut self, now: u64, keep: u64) {
        let from = now.saturating_sub(keep);
        while self.pts.len() >= 2 && self.pts[1].0 <= from { self.pts.pop_front(); }
    }
    pub fn points(&self) -> impl Iterator<Item = &(u64, i64)> { self.pts.iter() }
}

// ------------------------------------------------------------------ the rules

/// A stop rule (MEASUREMENT A.5: each is a stop reason and a SendGate shadow reason)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Rule { EquityFloor, TokenFloor, EquityHour, EquityDay }

impl Rule {
    pub fn as_str(self) -> &'static str { self.reason().as_str() }
    pub fn reason(self) -> StopReason {
        match self { Rule::EquityFloor => StopReason::EquityFloor, Rule::TokenFloor => StopReason::TokenFloor, Rule::EquityHour => StopReason::EquityHour,
            Rule::EquityDay => StopReason::EquityDay }
    }
}

/// What the rules compare against
#[derive(Clone, Debug, Default, PartialEq)]
pub struct Limits {
    /// lamports
    pub hour_drop: i64,
    pub day_drop: i64,
    /// SOL + WSOL may not fall below this (None: no budget, no floor)
    pub floor: Option<i64>,
    /// mint -> the lowest amount it may fall to (its start amount less the tolerance)
    pub token_floors: BTreeMap<String, u128>,
    /// the share of a token's start amount it may lose (rounding, dust) before `token_floor`
    pub token_tolerance: f64,
}

impl Limits {
    pub fn from_cfg(c: &SupervisorCfg) -> Limits {
        Limits { hour_drop: sol_to_lamports(c.max_drop_per_hour_sol), day_drop: sol_to_lamports(c.max_drop_per_day_sol), floor: None, token_floors: BTreeMap::new(),
            token_tolerance: c.token_floor_tolerance }
    }
    /// the token floors from the amounts held at the campaign's start: each start amount less its tolerance
    pub fn set_token_floors(&mut self, start: &BTreeMap<String, u128>) {
        let tol = self.token_tolerance;
        self.token_floors = start.iter().filter(|(_, a)| **a > 0).map(|(m, a)| (m.clone(), a - ((*a as f64 * tol).floor() as u128).min(*a))).collect();
    }
}

/// One rule that fired, with what it saw
#[derive(Clone, Debug, PartialEq)]
pub struct Hit { pub rule: Rule, pub detail: String, pub data: Value }

/// The stop rules at `now` (engine time) on the series and the current stop value (the start's SOL + WSOL less the net
/// spend) and token amounts (the start's, moved by routes), the most severe first: the floor, a token floor, the hour
/// drop, the day drop. Pure: tests drive it on a virtual clock
pub fn check(l: &Limits, now: u64, series: &Series, value: i64, tokens: &BTreeMap<String, u128>) -> Option<Hit> {
    if let Some(f) = l.floor.filter(|f| value < *f) {
        return Some(Hit { rule: Rule::EquityFloor, detail: format!("the net spend took the stop value to {value}, below the floor {f} (start - test budget) by {}", f - value),
            data: json!({ "basis": crate::ledger::STOP_BASIS, "stop_value": value, "floor": f, "below_by": f - value }) });
    }
    for (mint, floor) in &l.token_floors {
        let now_amt = tokens.get(mint).copied().unwrap_or(0);
        if now_amt < *floor {
            return Some(Hit { rule: Rule::TokenFloor, detail: format!("token {mint} at {now_amt}, below its floor {floor} (its start amount less the tolerance)"),
                data: json!({ "mint": mint, "amount": now_amt.to_string(), "floor": floor.to_string(), "tolerance": l.token_tolerance }) });
        }
    }
    for (rule, window, limit, name) in [(Rule::EquityHour, HOUR_NS, l.hour_drop, "hour"), (Rule::EquityDay, DAY_NS, l.day_drop, "24 h")] {
        let Some(d) = series.drop_over(now, window) else { continue };
        if d > limit {
            let high = series.max_in(now.saturating_sub(window), now);
            return Some(Hit { rule, detail: format!("the net spend lost {d} lamports within a rolling {name} (limit {limit})"),
                data: json!({ "basis": crate::ledger::STOP_BASIS, "drop": d, "limit": limit, "window_s": window / 1_000_000_000, "high": high, "stop_value": value }) });
        }
    }
    None
}

// ------------------------------------------------------------------ the in-process supervisor

/// The segment's supervisor: the rules' limits, what fired, the alerts already raised. It acts through the gate and
/// the stopper (set by `arbx run`; tests give their own)
pub struct Supervisor {
    pub cfg: SupervisorCfg,
    pub limits: Limits,
    gate: Option<Arc<SendGate>>,
    stopper: Option<Arc<Stopper>>,
    rec: Rec,
    /// the run's segment name (notices' subject)
    pub segment: String,
    /// the stop rule that fired (once: the run is stopping)
    pub fired: Option<(Hit, u64)>,
    /// the reconciliation misses so far (the gate is shadow from the first)
    pub recon_misses: u32,
    /// alerts raised once (`low_native_sol`, `stranded_token:<mint>`, `equity_unknown`)
    alerted: BTreeSet<String>,
    /// every action, in order (status `money.supervisor`)
    pub actions: Vec<Value>,
    /// whether a stop rule acts (the run can send: live, canary); in a shadow or dry run a rule that fires is recorded
    /// only (nothing is at stake, and the run keeps measuring)
    pub acts: bool,
}

impl Supervisor {
    pub fn new(cfg: SupervisorCfg, rec: Rec, segment: &str) -> Supervisor {
        Supervisor { limits: Limits::from_cfg(&cfg), cfg, gate: None, stopper: None, rec, segment: segment.to_string(), fired: None, recon_misses: 0,
            alerted: BTreeSet::new(), actions: Vec::new(), acts: true }
    }
    /// act on this run's SendGate and stop path
    pub fn bind(&mut self, gate: Arc<SendGate>, stopper: Arc<Stopper>) { self.gate = Some(gate); self.stopper = Some(stopper); }

    /// The rules at `now`. A rule that fires: the gate goes to shadow for the rest of the segment (its reason the rule),
    /// the run is asked to stop with it (exit 20 ends the campaign), an events.jsonl line, then a Critical notice (after
    /// the stop request: a hook that blocks or panics cannot delay or lose it). Once: later evaluations change nothing
    pub fn evaluate(&mut self, now: u64, series: &Series, value: i64, tokens: &BTreeMap<String, u128>) -> Option<Rule> {
        if self.fired.is_some() { return None; }
        let hit = check(&self.limits, now, series, value, tokens)?;
        let rule = hit.rule;
        let name = rule.as_str();
        if !self.acts {
            // a run that sends nothing: recorded, nothing to stop
            let mut detail = hit.data.clone();
            detail["rule"] = json!(name);
            detail["text"] = json!(hit.detail);
            detail["acted"] = json!(false);
            self.rec.event(name, "supervisor", None, detail);
            self.rec.say(format!("SUPERVISOR: {name}: {} (this run sends nothing: recorded only)", hit.detail));
            self.actions.push(json!({ "t_ns": now, "action": "recorded", "rule": name, "detail": hit.detail }));
            self.fired = Some((hit, now));
            return Some(rule);
        }
        if let Some(g) = &self.gate {
            if let Ok(true) = g.shadow(name, &hit.detail, true) {
                self.rec.event("gate_change", "supervisor", None, json!({ "to": "shadow", "reason": name, "detail": hit.detail }));
            }
        }
        let mut detail = hit.data.clone();
        detail["rule"] = json!(name);
        detail["text"] = json!(hit.detail);
        detail["segment"] = json!(self.segment);
        self.rec.event(name, "supervisor", None, detail.clone());
        // the stop first, the notice after it (review WP-07 #13)
        if let Some(s) = &self.stopper { s.request(StopInfo::new(rule.reason(), hit.detail.clone())); }
        self.actions.push(json!({ "t_ns": now, "action": "stop", "rule": name, "detail": hit.detail }));
        self.rec.say(format!("SUPERVISOR: {name}: {}: shadow, and the run stops (exit 20: the campaign ends)", hit.detail));
        notify::notify(notify::now(Level::Critical, name, "supervisor", self.segment.clone(), format!("{name}: {} (segment {}): sending stopped, campaign stops", hit.detail, self.segment), detail));
        self.fired = Some((hit, now));
        Some(rule)
    }

    /// A reconciliation miss: shadow for the rest of the segment (`reconcile_miss`); the campaign starts its later
    /// segments in shadow (src/campaign.rs). An events.jsonl `recon_miss` and an Error notice
    pub fn reconcile_miss(&mut self, now: u64, detail: Value) { self.reconcile_miss_at(now, detail, Level::Error) }

    /// `reconcile_miss` with the notice's level (a refused bundle that landed is Critical)
    pub fn reconcile_miss_at(&mut self, now: u64, detail: Value, level: Level) {
        self.recon_misses += 1;
        let text = detail["why"].as_str().unwrap_or("reconciliation outside its tolerance").to_string();
        if let Some(g) = &self.gate {
            if let Ok(true) = g.shadow("reconcile_miss", &text, true) {
                self.rec.event("gate_change", "supervisor", None, json!({ "to": "shadow", "reason": "reconcile_miss", "detail": text }));
            }
        }
        self.rec.event("recon_miss", "ledger", None, detail.clone());
        self.actions.push(json!({ "t_ns": now, "action": "shadow", "reason": "reconcile_miss", "detail": text }));
        self.rec.say(format!("SUPERVISOR: reconcile_miss: {text}: shadow for the rest of the segment"));
        notify::notify(notify::now(level, "recon_miss", "ledger", self.segment.clone(), format!("reconciliation miss (segment {}): {text}: sending stopped", self.segment), detail));
    }

    /// The money view went stale (`why`) or fresh again (None; review WP-07 #3). Stale: a live gate goes to shadow with
    /// reason `equity_stale` (not sticky: another shadow keeps its own reason), an events.jsonl `equity_stale` and an Error
    /// notice. Fresh: a gate in shadow for `equity_stale` goes back to live, an `equity_fresh` event and an Info notice. A
    /// run that sends nothing records it only
    pub fn equity_stale(&mut self, now: u64, why: Option<&str>, detail: Value) {
        match why {
            Some(w) => {
                self.rec.event("equity_stale", "supervisor", None, detail.clone());
                if self.acts { self.hold_stale(now, w); }
                self.actions.push(json!({ "t_ns": now, "action": if self.acts { "shadow" } else { "recorded" }, "reason": "equity_stale", "detail": w }));
                self.rec.say(format!("SUPERVISOR: equity_stale: {w}: nothing is sent until the money view is fresh"));
                notify::notify(notify::now(Level::Error, "equity_stale", "ledger", self.segment.clone(), format!("money view stale (segment {}): {w}: sending paused", self.segment), detail));
            }
            None => {
                self.rec.event("equity_fresh", "supervisor", None, detail.clone());
                if self.acts {
                    if let Some(g) = &self.gate {
                        if let Ok(true) = g.resume_if("equity_stale", "the money view is fresh again") {
                            self.rec.event("gate_change", "supervisor", None, json!({ "to": "live", "reason": "equity_fresh" }));
                        }
                    }
                }
                self.actions.push(json!({ "t_ns": now, "action": "fresh", "reason": "equity_stale" }));
                self.rec.say("SUPERVISOR: equity_fresh: the money view is fresh again".to_string());
                notify::notify(notify::now(Level::Info, "equity_fresh", "ledger", self.segment.clone(), format!("money view fresh again (segment {})", self.segment), detail));
            }
        }
    }

    /// While the money view stays stale: a live gate (an operator's resume meanwhile) goes back to shadow (`equity_stale`)
    pub fn hold_stale(&mut self, _now: u64, why: &str) {
        if !self.acts { return; }
        if let Some(g) = &self.gate {
            if g.allows() {
                if let Ok(true) = g.shadow("equity_stale", why, false) {
                    self.rec.event("gate_change", "supervisor", None, json!({ "to": "shadow", "reason": "equity_stale", "detail": why }));
                }
            }
        }
    }

    /// The owner's own transfer into or out of the wallet (review WP-07 #4): not the bot's spend, so no stop; an
    /// events.jsonl `owner_transfer` and a Warn notice (the owner learns that a campaign saw it)
    pub fn owner_transfer(&mut self, now: u64, detail: Value) {
        self.rec.event("owner_transfer", "ledger", None, detail.clone());
        self.actions.push(json!({ "t_ns": now, "action": "recorded", "reason": "owner_transfer", "detail": detail.clone() }));
        let text = format!("owner transfer in segment {}: {} {} lamports ({}): recorded, not a stop", self.segment, detail["category"].as_str().unwrap_or("?"),
            detail["lamports"], detail["sig"].as_str().unwrap_or("?"));
        self.rec.say(format!("SUPERVISOR: {text}"));
        notify::notify(notify::now(Level::Warn, "owner_transfer", "ledger", self.segment.clone(), text, detail));
    }

    /// An alert raised once per `key` (an events.jsonl line of kind `kind` and a notice); true when it was raised now
    pub fn alert_once(&mut self, key: &str, kind: &'static str, level: Level, text: String, detail: Value) -> bool {
        if !self.alerted.insert(key.to_string()) { return false; }
        self.rec.event(kind, "supervisor", None, detail.clone());
        self.rec.say(format!("SUPERVISOR: {kind}: {text}"));
        notify::notify(notify::now(level, kind, "supervisor", key.to_string(), text, detail));
        true
    }

    /// an alert raised again later (`key` forgotten): when its condition clears
    pub fn clear_alert(&mut self, key: &str) { self.alerted.remove(key); }

    /// status.jsonl `money.supervisor`
    pub fn json(&self) -> Value {
        json!({ "acts": self.acts, "limits": { "basis": crate::ledger::STOP_BASIS, "max_drop_per_hour_lamports": self.limits.hour_drop, "max_drop_per_day_lamports": self.limits.day_drop,
                "floor_lamports": self.limits.floor, "token_floor_tolerance": self.limits.token_tolerance,
                "token_floors": self.limits.token_floors.iter().map(|(m, a)| (m.clone(), json!(a.to_string()))).collect::<serde_json::Map<_, _>>() },
            "fired": self.fired.as_ref().map(|(h, t)| json!({ "rule": h.rule.as_str(), "t_ns": t, "detail": h.detail })),
            "recon_misses_total": self.recon_misses, "alerts": self.alerted.iter().collect::<Vec<_>>() })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const M: u64 = 60_000_000_000;
    const T0: u64 = 1_800_000_000_000_000_000;

    fn limits(floor: Option<i64>) -> Limits { Limits { hour_drop: 20_000_000, day_drop: 150_000_000, floor, token_floors: BTreeMap::new(), token_tolerance: 0.001 } }

    /// The series: the value carried into a window counts; points out of order never go back; trimming keeps the
    /// carried value
    #[test]
    fn the_series() {
        let mut s = Series::new();
        assert_eq!(s.drop_over(T0, HOUR_NS), None);
        s.push(T0, 1_000);
        s.push(T0 + 29 * M, 970);
        // an hour later the 1,000 is outside the window, but the 970 carried into it is not
        assert_eq!(s.drop_over(T0 + 30 * M, HOUR_NS), Some(30));
        assert_eq!(s.drop_over(T0 + 90 * M, HOUR_NS), Some(0), "the window [30 min, 90 min]: 970 throughout");
        assert_eq!(s.drop_over(T0 + 89 * M, HOUR_NS), Some(0), "the window [29 min, 89 min] starts at the 970 point");
        assert_eq!(s.drop_over(T0 + 88 * M, HOUR_NS), Some(30), "the window [28 min, 88 min]: the 1,000 is carried into it");
        s.push(T0 + 10 * M, 5);
        assert_eq!(s.last(), Some((T0 + 29 * M, 5)), "out of order: put at the last point's time");
        s.trim(T0 + 200 * M, HOUR_NS);
        assert_eq!(s.len(), 1);
        assert_eq!(s.value_at(T0 + 200 * M), Some(5));
    }

    /// OD-11 under a virtual (paused) clock: the floor, the hour drop and the day drop each fire with their reason at the
    /// first evaluation past their limit, never before; a token below its start amount fires `token_floor`
    #[test]
    fn stop_rules_on_a_virtual_clock() {
        let start = 414_000_000i64;
        let l = limits(Some(start - 34_000_000));
        let mut s = Series::new();
        let toks = BTreeMap::new();
        s.push(T0, start);
        assert_eq!(check(&l, T0, &s, start, &toks), None);
        // 19.9M lost over 50 minutes: under the hour limit
        s.push(T0 + 50 * M, start - 19_900_000);
        assert_eq!(check(&l, T0 + 50 * M, &s, start - 19_900_000, &toks), None);
        // 0.2M more 5 minutes later: 20.1M within the hour
        s.push(T0 + 55 * M, start - 20_100_000);
        let h = check(&l, T0 + 55 * M, &s, start - 20_100_000, &toks).unwrap();
        assert_eq!((h.rule, h.data["drop"].as_i64(), h.rule.as_str()), (Rule::EquityHour, Some(20_100_000), "equity_hour"));
        assert_eq!(h.rule.reason().exit_code(), 20, "a safety stop");
        // the same loss spread over 2 hours: no hour rule; the floor at 34M below the start fires only past it
        let mut s = Series::new();
        s.push(T0, start);
        let mut v = start;
        let mut t = T0;
        let mut fired = None;
        for k in 1..=12u64 {
            t = T0 + k * 15 * M;
            v -= 3_000_000;
            s.push(t, v);
            if let Some(h) = check(&l, t, &s, v, &toks) { fired = Some((k, h)); break; }
        }
        let (k, h) = fired.expect("the floor fires");
        assert_eq!((k, h.rule), (12, Rule::EquityFloor), "36M below the start: past the 34M budget at the 12th step, never the hour rule (12M an hour)");
        assert_eq!(h.data["below_by"].as_i64(), Some(2_000_000));
        let _ = t;
        // the day rule: 0.16 SOL over 20 hours, 8M an hour, no floor
        let l2 = limits(None);
        let mut s = Series::new();
        s.push(T0, start);
        let mut got = None;
        for k in 1..=20u64 {
            let v = start - 8_000_000 * k as i64;
            s.push(T0 + k * 60 * M, v);
            if let Some(h) = check(&l2, T0 + k * 60 * M, &s, v, &toks) { got = Some((k, h.rule)); break; }
        }
        assert_eq!(got, Some((19, Rule::EquityDay)), "152M within 24 h");
        // a token floor: the USDC held at the start (22.97 USDC) may lose at most 0.1% (22,970 raw), never more
        let mut l3 = limits(None);
        l3.set_token_floors(&[("USDC".to_string(), 22_970_000u128), ("EMPTY".to_string(), 0)].into_iter().collect());
        assert_eq!(l3.token_floors.get("USDC"), Some(&22_947_030), "start less the tolerance");
        assert!(!l3.token_floors.contains_key("EMPTY"), "nothing held, no floor");
        let mut s = Series::new();
        s.push(T0, start);
        let mut toks = BTreeMap::new();
        toks.insert("USDC".to_string(), 22_970_000u128);
        assert_eq!(check(&l3, T0, &s, start, &toks), None);
        toks.insert("USDC".to_string(), 22_947_030u128);
        assert_eq!(check(&l3, T0, &s, start, &toks), None, "within the tolerance");
        toks.insert("USDC".to_string(), 22_947_029u128);
        let h = check(&l3, T0, &s, start, &toks).unwrap();
        assert_eq!((h.rule, h.rule.as_str(), h.rule.reason().exit_code()), (Rule::TokenFloor, "token_floor", 20), "its own reason");
        toks.remove("USDC");
        assert_eq!(check(&l3, T0, &s, start, &toks).map(|h| h.rule), Some(Rule::TokenFloor), "an account gone is 0");
        // a SOL price move changes no token amount and no lamport: nothing can trip (the token's value is read by no rule)
        toks.insert("USDC".to_string(), 22_970_000u128);
        assert_eq!(check(&l3, T0 + 5 * M, &s, start, &toks), None);
    }

    /// The supervisor acts: the gate goes to shadow with the rule's name, the run is asked to stop with it (exit 20), an
    /// event and a Critical notice, once; a reconciliation miss shadows (sticky) without a stop
    #[test]
    fn the_supervisor_acts_through_the_gate_and_the_stopper() {
        let sess = crate::control::Session::new();
        let mut sup = Supervisor::new(SupervisorCfg::default(), Rec::off(), "c-p1");
        sup.bind(sess.gate.clone(), sess.stopper.clone());
        sup.limits.floor = Some(100);
        let mut s = Series::new();
        s.push(T0, 150);
        let (r, notes) = notify::capture(|| sup.evaluate(T0, &s, 150, &BTreeMap::new()));
        assert_eq!((r, notes.len()), (None, 0));
        assert!(sess.gate.allows());
        s.push(T0 + M, 99);
        let (r, notes) = notify::capture(|| sup.evaluate(T0 + M, &s, 99, &BTreeMap::new()));
        assert_eq!(r, Some(Rule::EquityFloor));
        assert_eq!((notes.len(), notes[0].level, notes[0].kind), (1, Level::Critical, "equity_floor"));
        assert_eq!(sess.stopper.info().map(|i| (i.reason, i.reason.exit_code())), Some((StopReason::EquityFloor, 20)));
        assert!(!sess.gate.allows());
        assert_eq!(sup.evaluate(T0 + 2 * M, &s, 50, &BTreeMap::new()), None, "once");
        // a recon miss on a live gate: shadow, sticky, no stop
        let sess = crate::control::Session::new();
        let mut sup = Supervisor::new(SupervisorCfg::default(), Rec::off(), "c-p2");
        sup.bind(sess.gate.clone(), sess.stopper.clone());
        let (_, notes) = notify::capture(|| sup.reconcile_miss(T0, json!({ "why": "liquid residual 12,000 > 10,000" })));
        assert_eq!((notes[0].kind, notes[0].level), ("recon_miss", Level::Error));
        assert_eq!((sess.gate.reason().as_str(), sess.gate.sticky(), sess.stopper.stopping()), ("reconcile_miss", true, false));
        assert!(sess.gate.resume("try").is_err(), "for the rest of the segment");
        // alerts once per key
        assert!(sup.alert_once("low_native_sol", "low_native_sol", Level::Warn, "x".into(), Value::Null));
        assert!(!sup.alert_once("low_native_sol", "low_native_sol", Level::Warn, "x".into(), Value::Null));
        sup.clear_alert("low_native_sol");
        assert!(sup.alert_once("low_native_sol", "low_native_sol", Level::Warn, "x".into(), Value::Null));
    }

    /// Review WP-07 #13: the alert hook (WP-20's) runs after the stop request, and a hook that panics loses nothing: the
    /// stop was requested before its notice, the panic is caught and counted (`notify::HOOK_PANICS`), the supervisor goes
    /// on. Through the process's real hook (not a capture): it acts only on this test's segment
    #[test]
    fn the_stop_comes_before_its_notice_and_a_panicking_hook_loses_nothing() {
        let sess = crate::control::Session::new();
        let seen: Arc<std::sync::Mutex<Vec<(String, bool)>>> = Default::default();
        let (s2, stopper) = (seen.clone(), sess.stopper.clone());
        notify::set_hook(move |n| {
            if n.subject != "hook-order-seg" { return; }
            s2.lock().unwrap().push((n.kind.to_string(), stopper.stopping()));
            panic!("the hook's own bug");
        });
        let before = notify::HOOK_PANICS.load(std::sync::atomic::Ordering::Relaxed);
        let mut sup = Supervisor::new(SupervisorCfg::default(), Rec::off(), "hook-order-seg");
        sup.bind(sess.gate.clone(), sess.stopper.clone());
        sup.limits.floor = Some(100);
        let mut s = Series::new();
        s.push(T0, 99);
        let r = sup.evaluate(T0, &s, 99, &BTreeMap::new());
        notify::clear_hook();
        assert_eq!(r, Some(Rule::EquityFloor));
        assert_eq!(sess.stopper.info().map(|i| i.reason), Some(StopReason::EquityFloor), "the stop request survived the hook's panic");
        assert_eq!(seen.lock().unwrap().clone(), vec![("equity_floor".to_string(), true)], "the hook ran after the stop was requested");
        assert!(notify::HOOK_PANICS.load(std::sync::atomic::Ordering::Relaxed) > before);
    }
}

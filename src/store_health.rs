//! Store health (PLAN WP-04 item 8; PLAN-ADDENDUM I-4): whether the engine's state can be priced on, and the gate the
//! executor reads before it sends.
//!
//! - **State stream health** (I-4). In cmp2 arbx's state stream got HTTP 503 for 28 minutes and the run priced against
//!   its boot snapshot, slot 0, with no warning, and exited 0. The state is *unavailable* while the stream is down (its
//!   task says so through journaled `health` inputs) or its newest message (account update or slot status) is more
//!   than `max_update_age_ms` old; nothing is priced or sent then, a WARNING goes to run.log, and a run whose stream
//!   delivers nothing within `boot_timeout_s` of the engine's start stops with reason `state_unavailable`.
//! - **Re-read** (I-4; review WP-04 #1). The stream does not resend the writes made while it was down, nor those made
//!   between the boot snapshot and its first subscription. On every (re)connection, the boot's first included, every
//!   followed account is read again over RPC (chunked by pool) and the gate stays shut (`resync`) until every chunk has
//!   landed (or, after `resync_give_up_s`, given up: its accounts stay refused one by one, reason `resync`, until the
//!   stream writes them). Each account is unverified until the re-read or a stream write after the (re)connection
//!   brings it: a pool with an unverified part is refused (`resync`), so a pool idle since the outage is never priced on
//!   its pre-outage version.
//! - **Warm-up** (item 8). `ready` turns on when every Tier-A pool has all its parts, the store is within
//!   `max_tip_lag_slots` of the chain tip and the state is available; until then decisions are refused with `warmup`
//!   and nothing is sent. A Tier-A pool whose parts are still missing `tier_a_grace_s` after the start is dropped from
//!   Tier A (an event), so one dead pool cannot hold the gate shut.
//! - **Lag SLO** (item 8). Every minute: the lag from the first shred of T (unexecuted feeds only, F33) to T's complete
//!   commit, p50 ≤ `lag_slo_p50_ms` and p90 ≤ `lag_slo_p90_ms`. `slo_action = "log"` (Stage 0) records breaches only;
//!   `"shadow"`: `lag_slo_breach_minutes` breaches in a row put the SendGate in shadow (`state_slo`), and
//!   `slo_recover_minutes` good minutes in a row bring it back (F32).
//!
//! [`HealthFlags`] is the part shared with the executor (`Exec::wants_send` refuses unless `ready`): the engine sets it
//! on its own thread before each send check, so a replay's checks see the same values (WP-05's `send_checks` takes it).
use std::sync::atomic::{AtomicBool, AtomicU8, Ordering::Relaxed};

/// why the gate is shut (HealthFlags reason). `Resync` (review WP-04 #1): the state stream (re)connected and the re-read
/// of every followed account has not landed yet (writes made while the stream was down, or before it first subscribed,
/// are not resent: until the re-read lands, the store cannot tell a pool written meanwhile from an idle one)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
#[repr(u8)]
pub enum Shut { Ready = 0, Warmup = 1, StateUnavailable = 2, Resync = 3 }

impl Shut {
    pub fn as_str(self) -> &'static str {
        match self { Shut::Ready => "ready", Shut::Warmup => "warmup", Shut::StateUnavailable => "state_unavailable", Shut::Resync => "resync" }
    }
    fn from_u8(x: u8) -> Shut { match x { 0 => Shut::Ready, 1 => Shut::Warmup, 3 => Shut::Resync, _ => Shut::StateUnavailable } }
}

/// The engine's health as the executor reads it (`Exec::wants_send`)
pub struct HealthFlags { ready: AtomicBool, why: AtomicU8 }

impl Default for HealthFlags { fn default() -> Self { HealthFlags { ready: AtomicBool::new(false), why: AtomicU8::new(Shut::Warmup as u8) } } }

impl HealthFlags {
    /// an executor without an engine (tools, tests): always ready
    pub fn always_ready() -> HealthFlags { HealthFlags { ready: AtomicBool::new(true), why: AtomicU8::new(Shut::Ready as u8) } }
    #[inline]
    pub fn ready(&self) -> bool { self.ready.load(Relaxed) }
    pub fn shut(&self) -> Shut { if self.ready() { Shut::Ready } else { Shut::from_u8(self.why.load(Relaxed)) } }
    pub fn set(&self, s: Shut) { self.why.store(s as u8, Relaxed); self.ready.store(s == Shut::Ready, Relaxed); }
}

/// The state stream's health, from journaled inputs and the receive times of its messages
#[derive(Clone, Debug, Default)]
pub struct StateStream {
    /// the stream task's last word (`health` input): None until it says anything
    pub connected: Option<bool>,
    pub reconnects: u64,
    pub resnapshots: u64,
    /// receive time of the newest state-stream message (account update or slot status)
    pub last_msg_t: u64,
    pub msgs: u64,
    pub last_error: Option<String>,
    /// while unavailable: since when (engine time)
    pub down_since: Option<u64>,
    /// when the last unavailable stretch ended (signer statistics count no miss across one, I-5)
    pub last_down_end: u64,
    pub down_total: u64,
}

impl StateStream {
    /// a message of the state stream received at `t`
    pub fn message(&mut self, t: u64) { self.msgs += 1; if t > self.last_msg_t { self.last_msg_t = t; } }
    /// available at engine time `t`: the stream has delivered, is not known to be down, and its newest message is recent
    pub fn ok(&self, t: u64, max_age_ns: u64) -> bool { self.msgs > 0 && self.connected != Some(false) && t.saturating_sub(self.last_msg_t) <= max_age_ns }
    /// the age of its newest message at `t` (None before the first)
    pub fn age_ns(&self, t: u64) -> Option<u64> { (self.msgs > 0).then(|| t.saturating_sub(self.last_msg_t)) }
    /// whether the state was unavailable at any time since `t0` (a pending trigger's outcome is then unknown, I-5)
    pub fn down_since_or_after(&self, t0: u64) -> bool { self.down_since.is_some() || self.last_down_end >= t0 }
}

/// One minute of the lag SLO (status.jsonl `lag_slo`)
#[derive(Clone, Debug, PartialEq)]
pub struct SloMinute { pub n: usize, pub p50_ms: Option<f64>, pub p90_ms: Option<f64>, pub ok: bool, pub breaches_in_row: u32, pub good_in_row: u32 }

/// What a minute of the SLO asks of the SendGate
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum SloAct { None, Shadow, Recover }

#[derive(Clone, Debug)]
pub struct LagSlo {
    pub p50_ms: f64,
    pub p90_ms: f64,
    pub breach_minutes: u32,
    pub recover_minutes: u32,
    /// "log" or "shadow"
    pub action: String,
    samples: Vec<u64>,
    pub minute_start: u64,
    pub last: Option<SloMinute>,
    pub breaches_in_row: u32,
    pub good_in_row: u32,
    /// the SLO put the SendGate in shadow (and has not brought it back)
    pub shadowed: bool,
}

impl LagSlo {
    pub fn new(p50_ms: f64, p90_ms: f64, breach_minutes: u32, recover_minutes: u32, action: &str) -> LagSlo {
        LagSlo { p50_ms, p90_ms, breach_minutes, recover_minutes, action: action.into(), samples: Vec::new(), minute_start: 0, last: None, breaches_in_row: 0,
            good_in_row: 0, shadowed: false }
    }
    /// a lag sample (ns): first shred of T to its complete commit
    pub fn push(&mut self, lag_ns: u64) { if self.samples.len() < 1_000_000 { self.samples.push(lag_ns); } }

    /// The minute that ended at `t`, if one has (`minute_start` is set at the first call). A minute with no sample is
    /// neither a breach nor a good minute
    pub fn tick(&mut self, t: u64) -> Option<(SloMinute, SloAct)> {
        if self.minute_start == 0 { self.minute_start = t; return None; }
        if t.saturating_sub(self.minute_start) < 60_000_000_000 { return None; }
        self.minute_start = t;
        let mut s = std::mem::take(&mut self.samples);
        s.sort_unstable();
        let pct = |p: f64| -> Option<f64> { (!s.is_empty()).then(|| s[((s.len() as f64 * p) as usize).min(s.len() - 1)] as f64 / 1e6) };
        let (p50, p90) = (pct(0.5), pct(0.9));
        let ok = match (p50, p90) { (Some(a), Some(b)) => a <= self.p50_ms && b <= self.p90_ms, _ => true };
        if !s.is_empty() {
            if ok { self.good_in_row += 1; self.breaches_in_row = 0; } else { self.breaches_in_row += 1; self.good_in_row = 0; }
        }
        let mut act = SloAct::None;
        if self.action == "shadow" {
            if !self.shadowed && self.breaches_in_row >= self.breach_minutes { self.shadowed = true; act = SloAct::Shadow; }
            else if self.shadowed && self.good_in_row >= self.recover_minutes { self.shadowed = false; act = SloAct::Recover; }
        }
        let m = SloMinute { n: s.len(), p50_ms: p50, p90_ms: p90, ok, breaches_in_row: self.breaches_in_row, good_in_row: self.good_in_row };
        self.last = Some(m.clone());
        Some((m, act))
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const MIN: u64 = 60_000_000_000;

    /// F32: with `shadow`, five breached minutes in a row shadow the gate and ten good ones bring it back; `log` never acts
    #[test]
    fn lag_slo_breaches_and_recovery() {
        let mut s = LagSlo::new(16.0, 30.0, 5, 10, "shadow");
        let mut t = 1;
        assert!(s.tick(t).is_none());
        let mut acts = Vec::new();
        for m in 0..20u64 {
            for _ in 0..10 { s.push(if m < 5 { 40_000_000 } else { 10_000_000 }); }
            t += MIN;
            let (minute, act) = s.tick(t).unwrap();
            assert_eq!(minute.ok, m >= 5);
            acts.push(act);
        }
        assert_eq!(acts.iter().position(|a| *a == SloAct::Shadow), Some(4), "the fifth breach");
        assert_eq!(acts.iter().position(|a| *a == SloAct::Recover), Some(14), "the tenth good minute");
        let mut l = LagSlo::new(16.0, 30.0, 5, 10, "log");
        l.tick(1);
        for k in 1..=10 { l.push(99_000_000); assert_eq!(l.tick(1 + k * MIN).unwrap().1, SloAct::None); }
        assert_eq!(l.breaches_in_row, 10);
    }

    #[test]
    fn state_stream_availability() {
        let mut s = StateStream::default();
        assert!(!s.ok(10, 2_000), "nothing delivered yet");
        s.message(100);
        assert!(s.ok(1_000, 2_000) && !s.ok(2_101, 2_000), "too old");
        s.connected = Some(false);
        assert!(!s.ok(150, 2_000), "the stream task says it is down");
        let f = HealthFlags::default();
        assert_eq!((f.ready(), f.shut()), (false, Shut::Warmup));
        f.set(Shut::StateUnavailable);
        assert_eq!(f.shut(), Shut::StateUnavailable);
        f.set(Shut::Ready);
        assert!(f.ready());
        f.set(Shut::Resync);
        assert_eq!((f.ready(), f.shut(), f.shut().as_str()), (false, Shut::Resync, "resync"));
    }
}

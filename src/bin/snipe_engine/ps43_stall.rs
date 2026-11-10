// =====================================================================================================================
// dip43 A1 FEED-STALL WATCHDOG + A2 BLIND-FILL RECOVERY / DEAD-MAN (BUILD_DIP43.md Builder A; integrator a1/a2, BASE-1, EXIT-4,
// onchain P3/A3/A4). The pure state machine (no I/O; times passed in, mono ns) driven by dipmode's event loop:
//   * three detectors: (1) SILENT: no executed-feed arrival for > SILENT_MS (default 1,500); (2) LAG: the TPU slot clock is more than
//     LAG_SLOTS (8) ahead of the executed feed's newest slot; (3) LATE: one of OUR transactions (fee payer = our wallet) was first seen on an
//     unexecuted (shred) feed and, LATE_MS (400) later, the probe still has an unresolved attempt with that signature.
//   * an EPISODE starts when any detector fires and ends when none does: a "FEED-STALL ..." line at its start, "FEED-STALL END dur_ms=..." at
//     its end, a presend_live_feed_stall record for both. ON BY DEFAULT as a log line + record (the only default-on dip43 output).
//   * --presend-live-stall-mode live (or the control file's "stall": "live"): during an episode the sender signs nothing new (send_gate:
//     "paused_stall"); triggers more than 2 slots behind the slot clock are skipped "stale_trigger" during the episode and for 10 s after it.
//   * A2 (--presend-live-deadman log|live, default log; key "deadman"): an unresolved try seen late (detector 3) is resolved by a status read
//     off the hot path (live) or logged as what would be done (log); a position open during an episode longer than DEADMAN_MS is sold at once
//     (live, why "deadman") or logged; the wall-clock backstop becomes exit_slots x 215 + 600 ms (live) instead of exit_slots x 400 + 3,000.
// Nothing here sends, reads RPC or waits; with the default flags the only effect is the line and the record.
// =====================================================================================================================
use std::collections::VecDeque;

/// the watchdog's thresholds and modes
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct StallCfg {
    pub silent_ms: u64,
    pub lag_slots: u64,
    pub late_ms: u64,
    /// --presend-live-stall-mode live: pause the sender during an episode
    pub live: bool,
    /// --presend-live-deadman live: status reads, the dead-man sell, the short backstop
    pub deadman_live: bool,
    /// --presend-live-deadman-ms N (0 = the immediate dead-man sell off)
    pub deadman_ms: u64,
}
impl Default for StallCfg {
    fn default() -> StallCfg { StallCfg { silent_ms: 1_500, lag_slots: 8, late_ms: 400, live: false, deadman_live: false, deadman_ms: 1_000 } }
}
impl StallCfg {
    pub fn spec(&self) -> String { format!("{}:{}:{}", self.silent_ms, self.lag_slots, self.late_ms) }
    pub fn desc(&self) -> String {
        format!("FEED-STALL WATCHDOG (dip43): executed feed silent > {} ms | > {} slots behind the TPU clock | our try seen on a shred feed with no result after {} ms -> \
                 {} | dead-man {} ({} ms; backstop {})", self.silent_ms, self.lag_slots, self.late_ms,
            if self.live { "LIVE: no new pre-send tries while blind, stale triggers skipped" } else { "LOG ONLY (FEED-STALL line + record)" },
            if self.deadman_live { "LIVE: status read of a blind try, sell after" } else { "LOG ONLY (would-records)" }, self.deadman_ms,
            if self.deadman_live { "exit_slots x 215 + 600 ms" } else { "exit_slots x 400 + 3000 ms (dip42)" })
    }
}

/// --presend-live-stall SILENT_MS:LAG_SLOTS:LATE_MS
pub fn stall_parse(s: &str) -> Result<(u64, u64, u64), String> {
    let bad = || format!("--presend-live-stall SILENT_MS:LAG_SLOTS:LATE_MS (300..60000 ms, 2..200 slots, 100..10000 ms), e.g. 1500:8:400; got '{s}'");
    let v: Vec<u64> = s.split(':').map(|x| x.trim().parse::<u64>()).collect::<Result<Vec<_>, _>>().map_err(|_| bad())?;
    if v.len() != 3 || !(300..=60_000).contains(&v[0]) || !(2..=200).contains(&v[1]) || !(100..=10_000).contains(&v[2]) { return Err(bad()); }
    Ok((v[0], v[1], v[2]))
}

/// the wall-clock backstop of a position's time exit (ms): dip42's 400 ms-slot constant, or the dead-man's (live)
pub fn wall_ms(exit_slots: u64, deadman_live: bool) -> u64 { if deadman_live { exit_slots * 215 + 600 } else { exit_slots * 400 + 3_000 } }

/// what fired
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind { Silent, Lag, Late }
impl Kind { pub fn s(self) -> &'static str { match self { Kind::Silent => "silent", Kind::Lag => "lag", Kind::Late => "late_try" } } }

/// one check's verdict
#[derive(Clone, Debug, PartialEq)]
pub enum Ev {
    /// an episode starts: what fired first, the silence (ms), the executed feed's slot, the TPU slot, the late tries' signatures
    Start { kind: Kind, silent_ms: u64, feed_slot: u64, tpu_slot: u64 },
    /// it ended: its length (ms), the detectors seen during it, the worst silence / lag
    End { dur_ms: u64, kinds: Vec<&'static str>, max_silent_ms: u64, max_lag: u64 },
}

/// the watchdog
#[derive(Debug, Default)]
pub struct Watch {
    pub cfg: StallCfg,
    /// the last executed-feed arrival (mono ns; 0 = none yet: no silence before the feed's first message) and its newest slot
    pub last_exec_ns: u64,
    pub exec_slot: u64,
    /// our transactions first seen on an unexecuted feed: (signature, mono ns), oldest first (bounded)
    sight: VecDeque<([u8; 64], u64)>,
    /// late tries reported already (each once)
    late_done: VecDeque<[u8; 64]>,
    /// the episode under way: (start ns, kinds seen, worst silence, worst lag)
    pub ep: Option<(u64, Vec<&'static str>, u64, u64)>,
    /// the last episode's end (mono ns; 0 = none)
    pub ended_ns: u64,
    pub episodes: u64,
    pub blind_ms: u64,
    pub late_tries: u64,
}

const SIGHT_CAP: usize = 4096;

impl Watch {
    pub fn new(cfg: StallCfg) -> Watch { Watch { cfg, ..Default::default() } }

    /// every arrival: an executed one moves the feed clock; an unexecuted one paid by us is a sighting (its first)
    pub fn on_arrival(&mut self, executed: bool, slot: u64, now_ns: u64, ours: Option<&[u8; 64]>) {
        if executed { self.last_exec_ns = now_ns; self.exec_slot = self.exec_slot.max(slot); return; }
        if let Some(s) = ours {
            if self.sight.iter().any(|x| &x.0 == s) { return; }
            self.sight.push_back((*s, now_ns));
            if self.sight.len() > SIGHT_CAP { self.sight.pop_front(); }
        }
    }

    pub fn active(&self) -> bool { self.ep.is_some() }

    /// within `ms` after the last episode ended (or during one)
    pub fn recent(&self, now_ns: u64, ms: u64) -> bool { self.ep.is_some() || (self.ended_ns > 0 && now_ns.saturating_sub(self.ended_ns) <= ms * 1_000_000) }

    /// the late tries now: our signatures first seen >= LATE_MS ago that `unresolved` (the probe: an attempt of ours not resolved yet)
    /// still holds; each reported once. Sightings resolved or older than 30 s leave
    pub fn late(&mut self, now_ns: u64, unresolved: &dyn Fn(&[u8; 64]) -> bool) -> Vec<([u8; 64], u64)> {
        let late_ns = self.cfg.late_ms * 1_000_000;
        let mut out = Vec::new();
        let done = &mut self.late_done;
        self.sight.retain(|(s, t)| {
            let age = now_ns.saturating_sub(*t);
            if !unresolved(s) || age > 30_000_000_000 { return false; }
            if age >= late_ns {
                if !done.contains(s) { done.push_back(*s); if done.len() > 256 { done.pop_front(); } out.push((*s, *t)); }
                return false;
            }
            true
        });
        self.late_tries += out.len() as u64;
        out
    }

    /// the detectors now (`late` = a late try was found by `late()` this round). -> the episode's start / end, if one
    pub fn check(&mut self, now_ns: u64, tpu_slot: u64, late: bool) -> Option<Ev> {
        let silent_ms = if self.last_exec_ns == 0 { 0 } else { now_ns.saturating_sub(self.last_exec_ns) / 1_000_000 };
        let lag = if tpu_slot == 0 || self.exec_slot == 0 { 0 } else { tpu_slot.saturating_sub(self.exec_slot) };
        let kind = if silent_ms > self.cfg.silent_ms { Some(Kind::Silent) } else if lag > self.cfg.lag_slots { Some(Kind::Lag) } else if late { Some(Kind::Late) } else { None };
        match (&mut self.ep, kind) {
            (None, Some(k)) => {
                self.ep = Some((now_ns, vec![k.s()], silent_ms, lag));
                self.episodes += 1;
                Some(Ev::Start { kind: k, silent_ms, feed_slot: self.exec_slot, tpu_slot })
            }
            (Some(e), Some(k)) => {
                if !e.1.contains(&k.s()) { e.1.push(k.s()); }
                e.2 = e.2.max(silent_ms); e.3 = e.3.max(lag);
                None
            }
            // a late try alone ends with the next check that finds none (the feed delivered or the status read resolved it)
            (Some(_), None) => {
                let (t0, kinds, ms, lg) = self.ep.take().unwrap();
                let dur_ms = now_ns.saturating_sub(t0) / 1_000_000;
                self.blind_ms += dur_ms;
                self.ended_ns = now_ns;
                Some(Ev::End { dur_ms, kinds, max_silent_ms: ms, max_lag: lg })
            }
            (None, None) => None,
        }
    }

    /// the episode's age now (ms; 0 = none)
    pub fn age_ms(&self, now_ns: u64) -> u64 { self.ep.as_ref().map_or(0, |e| now_ns.saturating_sub(e.0) / 1_000_000) }

    pub fn status(&self) -> String {
        if self.episodes == 0 && self.late_tries == 0 { return String::new(); }
        format!(" | FEED-STALL episodes {} blind {:.1} s late tries {}{}", self.episodes, self.blind_ms as f64 / 1e3, self.late_tries, if self.ep.is_some() { " (BLIND NOW)" } else { "" })
    }
    pub fn json(&self) -> serde_json::Value {
        serde_json::json!({"episodes": self.episodes, "blind_ms": self.blind_ms, "late_tries": self.late_tries, "cfg": self.cfg.spec(), "live": self.cfg.live, "deadman_live": self.cfg.deadman_live})
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    const MS: u64 = 1_000_000;

    #[test]
    fn dip43_stall_silent_episode_one_start_one_end() {
        let mut w = Watch::new(StallCfg::default());
        // no executed arrival yet: never silent
        assert_eq!(w.check(10_000 * MS, 0, false), None);
        w.on_arrival(true, 100, 1_000 * MS, None);
        assert_eq!(w.check(2_000 * MS, 100, false), None);
        // 2 s of silence with the TPU clock in step: one start
        match w.check(3_000 * MS, 101, false) { Some(Ev::Start { kind: Kind::Silent, silent_ms, feed_slot: 100, .. }) => assert_eq!(silent_ms, 2_000), x => panic!("{x:?}") }
        assert!(w.active());
        // still silent: no second line
        assert_eq!(w.check(3_500 * MS, 102, false), None);
        // the feed is back: one end with its length
        w.on_arrival(true, 103, 3_600 * MS, None);
        match w.check(3_610 * MS, 103, false) { Some(Ev::End { dur_ms, kinds, max_silent_ms, .. }) => { assert_eq!(dur_ms, 610); assert_eq!(kinds, vec!["silent"]); assert_eq!(max_silent_ms, 2_500); } x => panic!("{x:?}") }
        assert!(!w.active() && w.recent(3_700 * MS, 10_000) && !w.recent(20_000 * MS, 10_000));
        assert_eq!((w.episodes, w.blind_ms), (1, 610));
    }

    #[test]
    fn dip43_stall_lag_and_late_try() {
        let mut w = Watch::new(StallCfg::default());
        w.on_arrival(true, 100, 0, None);
        // 8 slots behind: fine; 9: lag
        assert_eq!(w.check(MS, 108, false), None);
        assert!(matches!(w.check(2 * MS, 109, false), Some(Ev::Start { kind: Kind::Lag, .. })));
        w.on_arrival(true, 109, 3 * MS, None);
        assert!(matches!(w.check(4 * MS, 109, false), Some(Ev::End { .. })));
        // our try seen on a shred feed, unresolved 400 ms later: late (once)
        let s = [7u8; 64];
        w.on_arrival(false, 110, 10 * MS, Some(&s));
        w.on_arrival(false, 110, 11 * MS, Some(&s));
        let un = |_: &[u8; 64]| true;
        assert!(w.late(300 * MS, &un).is_empty());
        let l = w.late(410 * MS, &un);
        assert_eq!(l, vec![(s, 10 * MS)]);
        assert!(w.late(500 * MS, &un).is_empty(), "each late try once");
        // a resolved sighting is dropped without a report
        let s2 = [8u8; 64];
        w.on_arrival(false, 111, 600 * MS, Some(&s2));
        assert!(w.late(1_100 * MS, &|_| false).is_empty());
        assert_eq!(w.late_tries, 1);
    }

    #[test]
    fn dip43_stall_parse_and_backstop() {
        assert_eq!(stall_parse("1500:8:400"), Ok((1500, 8, 400)));
        assert!(stall_parse("1500:8").is_err() && stall_parse("10:8:400").is_err() && stall_parse("1500:1:400").is_err());
        // dip42's backstop with the dead-man off; EXIT-4's with it live
        assert_eq!(wall_ms(6, false), 5_400);
        assert_eq!(wall_ms(6, true), 1_890);
    }
}

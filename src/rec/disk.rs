//! The disk budget (PLAN WP-02 item 6; MEASUREMENT §1.4). Every 10 s the monitor compares the segment directory's
//! size with `disk_budget_gb` and the filesystem's free space with `min_free_gb`. The bot never deletes what it wrote, so
//! once a limit is crossed it stays crossed; the ladder therefore acts in two stages (review F5):
//! - **soft** (the directory over 90% of the budget, or free space under `min_free_gb` / 0.9): one action per check,
//!   in this order, each written to `events.jsonl` (`disk_action`) and the manifest:
//!   1. stop the `entries-<feed>` archives;
//!   2. stop `rivals` (and `validators` once WP-08 writes it);
//!   3. lengthen the `accounts` keyframe interval 4x (a format change: no record is dropped);
//! - **hard** (the directory over the budget, or free space under `min_free_gb`): SendGate to shadow (`disk_budget`)
//!   and stop the segment (`stop.json` reason `disk_budget`, exit 20), at once.
//! The soft steps give the hard limit time to stay away; a segment that only crosses the soft limits runs on. Core,
//! replay and chain streams are never dropped by the budget. The actions hold for the rest of the segment. `arbx run`
//! refuses to start under `min_free_gb` (`rec::start`).
use super::Recorder;
use crate::config::RecordCfg;
use crate::control::{StopInfo, StopReason};
use crate::feeds::clock::now_ns;
use serde_json::json;
use std::path::Path;

const GB: u64 = 1 << 30;
/// the soft limits' share of the hard ones
const SOFT: f64 = 0.9;

#[derive(Clone, Copy, PartialEq, Eq, Debug)]
pub enum Action { StopEntries, StopRivals, KeyframesX4, ShadowAndStop }

impl Action {
    const LADDER: [Action; 4] = [Action::StopEntries, Action::StopRivals, Action::KeyframesX4, Action::ShadowAndStop];
    pub fn as_str(self) -> &'static str {
        match self { Action::StopEntries => "stop_entries_archive", Action::StopRivals => "stop_rivals", Action::KeyframesX4 => "accounts_keyframe_x4",
            Action::ShadowAndStop => "shadow_and_stop" }
    }
}

/// Where the ladder stands, and what the last check saw (manifest.json `disk`)
#[derive(Clone, Debug)]
pub struct Ladder {
    pub budget_bytes: u64,
    pub min_free_bytes: u64,
    /// the soft limits: 90% of the budget, the free-space floor / 0.9
    pub soft_budget_bytes: u64,
    pub soft_min_free_bytes: u64,
    /// soft steps taken (0-3); `stopped` once the hard step ran
    step: usize,
    stopped: bool,
    pub used_bytes: Option<u64>,
    pub fs_free_bytes: Option<u64>,
    pub actions: Vec<(u64, &'static str)>,
}

impl Ladder {
    pub fn new(cfg: &RecordCfg) -> Ladder {
        let (budget, floor) = ((cfg.disk_budget_gb * GB as f64) as u64, (cfg.min_free_gb * GB as f64) as u64);
        Ladder { budget_bytes: budget, min_free_bytes: floor, soft_budget_bytes: (budget as f64 * SOFT) as u64, soft_min_free_bytes: (floor as f64 / SOFT) as u64,
            step: 0, stopped: false, used_bytes: None, fs_free_bytes: None, actions: Vec::new() }
    }

    /// One check: past a hard limit the last step (once); past a soft limit the next soft step (one per check, in
    /// ladder order); else None
    pub fn check(&mut self, used: u64, free: u64, t: u64) -> Option<Action> {
        self.used_bytes = Some(used);
        self.fs_free_bytes = Some(free);
        if self.stopped { return None; }
        let a = if used > self.budget_bytes || free < self.min_free_bytes {
            self.stopped = true;
            Action::ShadowAndStop
        } else if used > self.soft_budget_bytes || free < self.soft_min_free_bytes {
            let a = *Action::LADDER[..3].get(self.step)?;
            self.step += 1;
            a
        } else {
            return None;
        };
        self.actions.push((t, a.as_str()));
        Some(a)
    }

    pub fn json(&self) -> serde_json::Value {
        json!({ "budget_bytes": self.budget_bytes, "min_free_bytes": self.min_free_bytes, "soft_budget_bytes": self.soft_budget_bytes,
            "soft_min_free_bytes": self.soft_min_free_bytes, "used_bytes": self.used_bytes, "fs_free_bytes": self.fs_free_bytes,
            "actions": self.actions.iter().map(|(t, a)| json!({ "t_ns": t, "action": a })).collect::<Vec<_>>() })
    }
}

/// The two numbers a check needs; tests give fake ones
pub trait FsUsage {
    /// (bytes under `dir`, free bytes on its filesystem for an unprivileged user)
    fn usage(&mut self, dir: &Path) -> (u64, u64);
}

/// The real filesystem: the directory's files (recursively) and `statvfs`
pub struct RealFs;

impl FsUsage for RealFs {
    fn usage(&mut self, dir: &Path) -> (u64, u64) { (dir_bytes(dir), fs_free(dir).unwrap_or(u64::MAX)) }
}

pub fn dir_bytes(dir: &Path) -> u64 {
    let mut n = 0;
    let Ok(rd) = std::fs::read_dir(dir) else { return 0 };
    for e in rd.flatten() {
        let Ok(m) = e.metadata() else { continue };
        if m.is_dir() { n += dir_bytes(&e.path()); } else { n += m.len(); }
    }
    n
}

pub fn fs_free(dir: &Path) -> Option<u64> {
    use std::os::unix::ffi::OsStrExt;
    let c = std::ffi::CString::new(dir.as_os_str().as_bytes()).ok()?;
    // SAFETY: a valid C string and a zeroed statvfs to fill
    unsafe {
        let mut s: libc::statvfs = std::mem::zeroed();
        if libc::statvfs(c.as_ptr(), &mut s) != 0 { return None; }
        Some(s.f_bavail as u64 * s.f_frsize as u64)
    }
}

impl Recorder {
    /// One disk check (the monitor every 10 s; tests with a fake `FsUsage`): takes the next action if a limit is crossed
    pub fn disk_check(&self, fs: &mut dyn FsUsage) -> Option<Action> {
        let (used, free) = fs.usage(&self.dir);
        let t = now_ns();
        let (a, ladder) = {
            let mut l = self.disk.lock().unwrap_or_else(|e| e.into_inner());
            let a = l.check(used, free, t)?;
            (a, l.clone())
        };
        let mut streams = Vec::new();
        let mut detail = format!("run dir {used} bytes (budget {}, soft {}), {free} bytes free (minimum {}, soft {})", ladder.budget_bytes, ladder.soft_budget_bytes,
            ladder.min_free_bytes, ladder.soft_min_free_bytes);
        match a {
            Action::StopEntries => streams = self.switch_off(|s| s.name.starts_with("entries-")),
            Action::StopRivals => streams = self.switch_off(|s| s.name == "rivals" || s.name == "validators"),
            Action::KeyframesX4 => {
                let k = self.keyframe_every.load(std::sync::atomic::Ordering::Relaxed).saturating_mul(4);
                self.keyframe_every.store(k, std::sync::atomic::Ordering::Relaxed);
                detail.push_str(&format!("; accounts keyframe every {k} records"));
            }
            Action::ShadowAndStop => {
                if let Some(g) = self.gate.get() {
                    if let Ok(true) = g.shadow("disk_budget", &detail, true) {
                        self.event("gate_change", "recorder", None, json!({ "to": "shadow", "reason": "disk_budget", "detail": detail }));
                    }
                }
                if let Some(s) = self.stopper.get() { s.request(StopInfo::new(StopReason::DiskBudget, detail.clone())); }
            }
        }
        self.event("disk_action", "recorder", None, json!({ "action": a.as_str(), "used_bytes": used, "fs_free_bytes": free, "budget_bytes": ladder.budget_bytes,
            "min_free_bytes": ladder.min_free_bytes, "streams_off": streams, "detail": detail }));
        Some(a)
    }
}

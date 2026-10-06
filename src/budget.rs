//! The owner's test budget across every live or canary start (docs/field-tests/BUDGET.md; review WP-07 #5): the hard cap
//! (34,000,000 lamports, `config::TEST_BUDGET_HARD_CAP`) is cumulative over all tests, not per campaign or per run.
//!
//! `<runs>/budget-state.json` (`arbx.budget/1.0`; on Cherry `/root/arbx/runs/budget-state.json`) lists every sending
//! campaign and manual run with its allotment and its net spend (the ledger's, `ledger::Totals::net_spend`: fees, tips,
//! non-recoverable rent, trading loss; the owner's transfers are not in it). Every live or canary start (`arbx campaign`
//! in a sending mode, `arbx run --canary` / `--live` outside a campaign) holds the runs directory's lock, reads the file,
//! re-reads the spend of every entry not final from its own files (a run that was killed still counts), refuses when
//! nothing is left, and takes as its allotment the smaller of what it asked for and what is left; it is recorded at once,
//! its spend updated as it runs (a campaign after each segment) and made final at its end. A file that does not read is
//! refused (fail closed): the owner fixes or removes it.
use crate::config::TEST_BUDGET_HARD_CAP;
use crate::supervisor::DAY_NS;
use anyhow::{bail, Context, Result};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

pub const FILE: &str = "budget-state.json";
pub const SCHEMA: &str = "arbx.budget/1.0";

/// One sending start: a campaign (`kind` `campaign`, its directory holds its segments) or a manual run (`run`, its
/// directory is the run's)
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct Entry {
    pub id: String,
    pub kind: String,
    pub dir: String,
    pub mode: String,
    pub started_ns: u64,
    pub ended_ns: Option<u64>,
    /// what it was allowed (at most what was left when it started)
    pub allotment: u64,
    /// its net spend so far (lamports; negative: it made money)
    pub spent: i64,
    /// its process recorded its last spend at its end; an entry that is not final is re-read from its files
    #[serde(rename = "final")]
    pub done: bool,
}

/// The budget state
#[derive(Clone, Debug, Serialize, Deserialize, PartialEq)]
pub struct State {
    pub schema: String,
    pub hard_cap_lamports: u64,
    pub entries: Vec<Entry>,
    pub updated_ns: u64,
}

/// what a sending start was granted
#[derive(Clone, Debug, PartialEq)]
pub struct Grant { pub allotment: u64, pub remaining_before: i64, pub spent_before: i64 }

impl Default for State {
    fn default() -> Self { State { schema: SCHEMA.into(), hard_cap_lamports: TEST_BUDGET_HARD_CAP, entries: Vec::new(), updated_ns: 0 } }
}

/// `<runs>/budget-state.json`
pub fn path(runs: &Path) -> PathBuf { runs.join(FILE) }

impl State {
    /// The state in `runs` (none yet: an empty one). A file that does not read is an error: a sending start refuses
    pub fn load(runs: &Path) -> Result<State> {
        let p = path(runs);
        match std::fs::read(&p) {
            Ok(b) => {
                let s: State = serde_json::from_slice(&b).with_context(|| format!("{} does not read (fix or remove it; nothing sends until then)", p.display()))?;
                if s.schema != SCHEMA { bail!("{}: schema {} is not {SCHEMA}", p.display(), s.schema); }
                Ok(s)
            }
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => Ok(State::default()),
            Err(e) => Err(e).with_context(|| format!("reading {}", p.display())),
        }
    }

    /// written atomically
    pub fn save(&mut self, runs: &Path, now: u64) -> Result<()> {
        self.updated_ns = now;
        self.hard_cap_lamports = TEST_BUDGET_HARD_CAP;
        crate::control::write_atomic(&path(runs), format!("{}\n", serde_json::to_string_pretty(self)?).as_bytes())
    }

    /// the net spend of every entry
    pub fn spent(&self) -> i64 { self.entries.iter().map(|e| e.spent).sum() }

    /// what is left of the hard cap (never more than the cap: a run that made money gives back what it spent, no more)
    pub fn remaining(&self) -> i64 { (TEST_BUDGET_HARD_CAP as i64 - self.spent()).min(TEST_BUDGET_HARD_CAP as i64) }

    /// every entry that is not final: its spend re-read from its files (the larger of that and what it last recorded)
    pub fn refresh(&mut self, now: u64) {
        for e in self.entries.iter_mut().filter(|e| !e.done) {
            if let Some(s) = spend_of(Path::new(&e.dir), &e.kind, now) { e.spent = e.spent.max(s); }
        }
    }

    /// the entry `id`
    pub fn entry_mut(&mut self, id: &str) -> Option<&mut Entry> { self.entries.iter_mut().find(|e| e.id == id) }
}

/// The net spend recorded in a campaign's or a run's files (the ledger; None: nothing there to read)
pub fn spend_of(dir: &Path, kind: &str, now: u64) -> Option<i64> {
    if !dir.exists() { return None; }
    let h = if kind == "campaign" { crate::ledger::history(dir, None, now, DAY_NS) } else { crate::ledger::history_of_run(dir, now) };
    Some(h.totals.net_spend())
}

/// A sending start (`kind` `campaign` or `run`, `id` unique in the file, its directory, its mode, what it asks for):
/// with the runs directory's lock held. Reads the state (every entry not final re-read from its files), refuses when
/// nothing is left of the hard cap, grants the smaller of `wanted` and what is left, and records the entry at once
pub fn begin(runs: &Path, id: &str, kind: &str, dir: &Path, mode: &str, wanted: u64, now: u64) -> Result<Grant> {
    if wanted == 0 { bail!("a {mode} start needs a test budget (lamports, at most {TEST_BUDGET_HARD_CAP})"); }
    if wanted > TEST_BUDGET_HARD_CAP { bail!("test budget {wanted} is over the owner's hard cap {TEST_BUDGET_HARD_CAP}"); }
    let mut s = State::load(runs)?;
    s.refresh(now);
    if s.entries.iter().any(|e| e.id == id) { bail!("{}: {id} is already recorded (pick a new name)", path(runs).display()); }
    let (spent, left) = (s.spent(), s.remaining());
    if left <= 0 {
        bail!("the owner's test budget is spent: {spent} of {TEST_BUDGET_HARD_CAP} lamports across {} recorded runs ({}); nothing sends until the owner raises it",
            s.entries.len(), path(runs).display());
    }
    let allotment = wanted.min(left as u64);
    s.entries.push(Entry { id: id.into(), kind: kind.into(), dir: dir.display().to_string(), mode: mode.into(), started_ns: now, ended_ns: None, allotment, spent: 0,
        done: false });
    s.save(runs, now)?;
    Ok(Grant { allotment, remaining_before: left, spent_before: spent })
}

/// A manual live or canary run's hold (review WP-07 #5): the runs directory's lock for its whole life, its budget-state
/// entry and what it was granted
pub struct RunHold { pub lock: Option<std::fs::File>, pub runs: PathBuf, pub id: String, pub grant: Grant }

/// `arbx run --live` / `--canary` outside a campaign: the runs directory's lock (a campaign or another manual run holds it:
/// refused), nothing else on the provider or the wallet (`busy`: another `arbx` / `arb-lab` run, arbed's bot, a live
/// segment socket; I-3), and the owner's cumulative budget (`begin`)
pub fn manual_start(runs: &Path, id: &str, dir: &Path, mode: &str, wanted: u64, busy: &dyn Fn() -> Vec<String>, now: u64) -> Result<RunHold> {
    if wanted == 0 { bail!("a {mode} run needs a test budget: [supervisor] test_budget_lamports or --budget-left (at most {TEST_BUDGET_HARD_CAP})"); }
    let lock = crate::probe::lock_runs(runs).context("a manual live or canary run takes the campaign lock")?;
    if lock.is_none() { bail!("{}: the campaign lock cannot be taken (no runs directory): a live or canary run refuses to start", runs.display()); }
    // the budget first (nothing left: refused whatever else runs), then what else holds the provider or the wallet
    let mut s = State::load(runs)?;
    s.refresh(now);
    if s.remaining() <= 0 {
        bail!("the owner's test budget is spent: {} of {TEST_BUDGET_HARD_CAP} lamports across {} recorded runs ({}); nothing sends until the owner raises it",
            s.spent(), s.entries.len(), path(runs).display());
    }
    let b = busy();
    if !b.is_empty() { bail!("another bot may hold the provider or the wallet (Haan serves the first process only, I-3): {}", b.join("; ")); }
    let grant = begin(runs, id, "run", dir, mode, wanted, now)?;
    Ok(RunHold { lock, runs: runs.to_path_buf(), id: id.to_string(), grant })
}

/// A start's spend so far (`done`: its end; the entry is final from then on)
pub fn update(runs: &Path, id: &str, spent: i64, done: bool, now: u64) -> Result<()> {
    let mut s = State::load(runs)?;
    let Some(e) = s.entry_mut(id) else { bail!("{}: no entry {id}", path(runs).display()) };
    e.spent = spent;
    if done { e.done = true; e.ended_ns = Some(now); }
    s.save(runs, now)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn tmp(tag: &str) -> PathBuf {
        let d = std::env::temp_dir().join(format!("arbx-budget-{tag}-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        std::fs::create_dir_all(&d).unwrap();
        d
    }

    /// Review WP-07 #5: the hard cap is cumulative. A first canary of 5,000,000 spends 4,000,000; a second asks for the
    /// whole cap and gets what is left (30,000,000); one that spent past it leaves nothing: the next start is refused. A
    /// run that was killed (its entry never final) is re-read from its files. A file that does not read refuses
    #[test]
    fn the_hard_cap_is_cumulative() {
        let runs = tmp("cum");
        let g = begin(&runs, "ft004", "campaign", &runs.join("ft004"), "canary", 5_000_000, 1).unwrap();
        assert_eq!((g.allotment, g.remaining_before), (5_000_000, 34_000_000));
        update(&runs, "ft004", 4_000_000, true, 2).unwrap();
        let g = begin(&runs, "ft005", "campaign", &runs.join("ft005"), "canary", 34_000_000, 3).unwrap();
        assert_eq!((g.allotment, g.spent_before), (30_000_000, 4_000_000), "what is left, not the cap again");
        assert!(begin(&runs, "ft005", "run", &runs.join("x"), "canary", 1, 4).unwrap_err().to_string().contains("already recorded"));
        update(&runs, "ft005", 30_000_001, true, 5).unwrap();
        let e = begin(&runs, "ft006", "run", &runs.join("ft006"), "live", 1_000_000, 6).unwrap_err().to_string();
        assert!(e.contains("test budget is spent"), "{e}");
        assert!(begin(&runs, "big", "run", &runs.join("big"), "live", 34_000_001, 6).unwrap_err().to_string().contains("hard cap"));
        // a killed manual run: not final, its spend read from its ledger
        let runs2 = tmp("killed");
        begin(&runs2, "r1", "run", &runs2.join("r1"), "canary", 5_000_000, 1).unwrap();
        let d = runs2.join("r1");
        std::fs::create_dir_all(&d).unwrap();
        let snap = crate::ledger::Snapshot { t_ns: 10, slot: 100, sol: 300_000_000, wsol: 100_000_000, ..Default::default() };
        let r = crate::ledger::Raw { kind: "route".into(), ok: false, payer: true, wallet_sol: -7_000, fee: 7_000, ..Default::default() };
        let e = crate::ledger::entry(&r, &crate::ledger::Head { sig: "f", slot: 101, idx: None, t_ns: 11, attempt: None, pre_run: false }, 0.1, &crate::ledger::no_prices);
        std::fs::write(d.join("snapshots.jsonl"), format!("{}\n{}\n", json!({ "schema": "arbx.snapshots/1.0", "file_seq": 0 }), snap.json())).unwrap();
        std::fs::write(d.join("ledger.jsonl"), format!("{}\n{}\n", json!({ "schema": "arbx.ledger/1.0", "file_seq": 0 }), e.json())).unwrap();
        let mut s = State::load(&runs2).unwrap();
        s.refresh(20);
        assert_eq!((s.spent(), s.remaining()), (7_000, 34_000_000 - 7_000));
        // a file that does not read refuses
        std::fs::write(path(&runs2), "{ not json").unwrap();
        assert!(begin(&runs2, "r2", "run", &runs2.join("r2"), "canary", 1, 2).unwrap_err().to_string().contains("does not read"));
        let _ = std::fs::remove_dir_all(&runs);
        let _ = std::fs::remove_dir_all(&runs2);
    }

    /// Review WP-07 #5: a manual live or canary run takes the campaign lock (refused while a campaign holds it), runs the
    /// other-bot check (refused when something else holds the provider or the wallet), and takes its allotment from the
    /// budget state; its lock is held until the run ends
    #[test]
    fn a_manual_run_takes_the_lock_and_the_budget() {
        let runs = tmp("manual");
        let quiet = || Vec::<String>::new();
        let campaign = crate::probe::lock_runs(&runs).unwrap().expect("the lock file");
        let e = manual_start(&runs, "r1", &runs.join("r1"), "canary", 5_000_000, &quiet, 1).err().unwrap();
        assert!(format!("{e:#}").contains("a campaign supervisor is running"), "{e:#}");
        drop(campaign);
        let e = manual_start(&runs, "r1", &runs.join("r1"), "canary", 5_000_000, &|| vec!["pid 9: bun bin/arbed.ts run --live".into()], 1).err().unwrap();
        assert!(format!("{e:#}").contains("arbed.ts"), "{e:#}");
        assert!(manual_start(&runs, "r0", &runs.join("r0"), "canary", 0, &quiet, 1).err().unwrap().to_string().contains("needs a test budget"));
        let h = manual_start(&runs, "r1", &runs.join("r1"), "canary", 5_000_000, &quiet, 1).unwrap();
        assert_eq!(h.grant.allotment, 5_000_000);
        assert!(crate::probe::lock_held(&runs), "held for the run's life");
        assert!(manual_start(&runs, "r2", &runs.join("r2"), "canary", 5_000_000, &quiet, 2).is_err(), "a second manual run beside it");
        drop(h);
        assert!(!crate::probe::lock_held(&runs));
        let _ = std::fs::remove_dir_all(&runs);
    }
}

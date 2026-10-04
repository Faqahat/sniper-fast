//! CommitTracker (PLAN WP-04 item 3): which account updates belong together, and when a transaction's writes have all
//! arrived. A route is priced only on committed, complete state: never while one of its accounts carries part of a
//! transaction whose other writes are still on their way (the split-route torn reads, W §7.2).
//!
//! **Groups.** The first account update stamped with transaction T opens T's group. Its write set W(T) (the watched
//! accounts T writes) comes from one of three Stage-0 sources (F2), named in every group as `w_src`:
//! - `tx-stream`: the executed-transaction stream (the PumpSwap filter, WP-03). Authoritative, PumpSwap only. Measured
//!   on w5h2-p1 (5,879 transactions): it arrives after T's first account update (p50 +0.23 ms, p90 +0.74 ms, p99
//!   +5.9 ms), so a PumpSwap group usually starts unknown and learns its W(T) while pending;
//! - `shred`: a hint from a live shred, deshred or entries feed (T decoded before execution, its writable watched keys);
//! - `unknown`: neither delivered T (aggregator- and bot-routed transactions on other venues, most non-PumpSwap ones).
//!
//! **Resolution** (`pending` → `complete` | `superseded` | `timeout_unknown` | `timeout_quiescent` | `fork_dropped`):
//! - known W(T): pending until every account of W(T) has an update stamped T (`complete`) or a newer version from
//!   another transaction (`superseded`), or until `commit_timeout_ms` after T's first update (`timeout_unknown`: the
//!   missing members' fate is unknown);
//! - unknown W(T): resolved when no update stamped T has arrived for `quiescence_ms` (`timeout_quiescent`);
//! - a group whose slot is abandoned by a fork is `fork_dropped`.
//! Routes of a group resolved by a timeout are priced only if route-level quiet (the engine's `route_not_quiet`).
//!
//! **Time.** Deadlines are on the updates' receive times (`t_recv`). They are checked (a) by `expire(t)` from the
//! engine's timers, which run only when its queue is empty (no update of T can be waiting in it), and (b) by stream
//! evidence: the state stream is FIFO, so a later stream message received at `x` shows every update of T received
//! before `x` has been handled; groups whose deadline is at or before `x` resolve then, whatever the engine's backlog.
//! Both are deterministic under replay (the journal holds the timer calls and every event's receive time).
//!
//! **Late members.** An update stamped T after T's group resolved is a `late_member`: the engine marks every decision
//! priced on T's pools since the resolution `torn_suspect`, and the update opens a new group (unknown W).
use crate::tx::Pk;
use rustc_hash::FxHashMap as HashMap;
use std::collections::{BTreeMap, VecDeque};

/// Where a group's write set came from (commits.jsonl `w_src`)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
pub enum WSrc { TxStream, Shred, Unknown }

impl WSrc {
    pub fn as_str(self) -> &'static str { match self { WSrc::TxStream => "tx-stream", WSrc::Shred => "shred", WSrc::Unknown => "unknown" } }
    pub const ALL: [WSrc; 3] = [WSrc::TxStream, WSrc::Shred, WSrc::Unknown];
}

/// How a group resolved (commits.jsonl `outcome`)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Outcome { Complete, Superseded, TimeoutUnknown, TimeoutQuiescent, ForkDropped }

impl Outcome {
    pub fn as_str(self) -> &'static str {
        match self { Outcome::Complete => "complete", Outcome::Superseded => "superseded", Outcome::TimeoutUnknown => "timeout_unknown",
            Outcome::TimeoutQuiescent => "timeout_quiescent", Outcome::ForkDropped => "fork_dropped" }
    }
    /// the engine's counter name
    pub fn counter(self) -> &'static str {
        match self { Outcome::Complete => "commit_complete", Outcome::Superseded => "commit_superseded", Outcome::TimeoutUnknown => "commit_timeout_unknown",
            Outcome::TimeoutQuiescent => "commit_timeout_quiescent", Outcome::ForkDropped => "commit_fork_dropped" }
    }
    /// a timeout: the routes it triggers need route-level quiet
    pub fn timed_out(self) -> bool { matches!(self, Outcome::TimeoutUnknown | Outcome::TimeoutQuiescent) }
}

/// What resolved a group (commits.jsonl `resolved_by`)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum By { Member, Register, Timer, Stream, Fork }

impl By {
    pub fn as_str(self) -> &'static str { match self { By::Member => "member", By::Register => "register", By::Timer => "timer", By::Stream => "stream", By::Fork => "fork" } }
}

/// One update stamped with the group's transaction (commits.jsonl `w_seen` / `late_members`)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Member { pub acct: Pk, pub slot: u64, pub wv: u64, pub aseq: u64, pub t: u64 }

#[derive(Clone, Debug)]
pub struct Group {
    /// sequence number (opening order): the deterministic order of everything done to groups
    pub id: u64,
    pub txn: [u8; 64],
    /// the slot of its first update
    pub slot: u64,
    /// W(T) when known (sorted)
    pub w: Option<Vec<Pk>>,
    pub w_src: WSrc,
    /// when W(T) was registered relative to the group: true when the registration came after its first update
    pub w_late: bool,
    pub seen: Vec<Member>,
    /// members of W(T) satisfied by a newer version written by another transaction
    pub superseded: Vec<Pk>,
    /// receive times of its first and last update, the engine time of its first
    pub t_first_update: u64,
    pub t_last_update: u64,
    pub t_first_engine: u64,
    /// the resolved group a late member reopened
    pub reopened_from: Option<u64>,
}

impl Group {
    /// every account it names: W(T) and the updates seen (sorted, unique)
    pub fn accounts(&self) -> Vec<Pk> {
        let mut v: Vec<Pk> = self.seen.iter().map(|m| m.acct).collect();
        if let Some(w) = &self.w { v.extend(w.iter().copied()); }
        v.sort();
        v.dedup();
        v
    }
    /// its newest update's version (slot, write_version)
    fn newest(&self) -> (u64, u64) { self.seen.iter().map(|m| (m.slot, m.wv)).max().unwrap_or((self.slot, 0)) }
    fn complete(&self) -> Option<Outcome> {
        let w = self.w.as_ref()?;
        let done = w.iter().all(|a| self.seen.iter().any(|m| m.acct == *a) || self.superseded.contains(a));
        done.then(|| if self.superseded.is_empty() { Outcome::Complete } else { Outcome::Superseded })
    }
    /// its deadline on the receive-time clock
    fn deadline(&self, c: &TrackerCfg) -> u64 {
        if self.w.is_some() { self.t_first_update.saturating_add(c.commit_timeout_ns) } else { self.t_last_update.saturating_add(c.quiescence_ns) }
    }
}

/// A group that resolved: `t_resolved` is the engine time of the input or timer that resolved it; `t_clock` the moment
/// on the receive-time clock (the completing update's receive time, the stream evidence's, the timer's), against which
/// route-level quiet is judged
#[derive(Clone, Debug)]
pub struct Resolution { pub group: Group, pub outcome: Outcome, pub t_resolved: u64, pub t_clock: u64, pub by: By }

/// A late member: an update stamped with a transaction whose group had already resolved
#[derive(Clone, Debug)]
pub struct Late { pub txn: [u8; 64], pub prev_id: u64, pub prev_t_resolved: u64, pub prev_accounts: Vec<Pk>, pub member: Member, pub reopened_id: u64 }

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct TrackerCfg {
    pub commit_timeout_ns: u64,
    pub quiescence_ns: u64,
    /// how long a resolved group is remembered for late members
    pub late_window_ns: u64,
    /// how long a registration waits for its transaction's first update
    pub reg_keep_ns: u64,
}

impl TrackerCfg {
    pub fn new(commit_timeout_ms: u64, quiescence_ms: u64) -> TrackerCfg {
        TrackerCfg { commit_timeout_ns: commit_timeout_ms * 1_000_000, quiescence_ns: quiescence_ms * 1_000_000, late_window_ns: 10_000_000_000, reg_keep_ns: 10_000_000_000 }
    }
}

/// at most this many registrations and resolved groups are remembered (the oldest go first)
const KEEP_MAX: usize = 200_000;

struct Reg { w: Vec<Pk>, src: WSrc }
struct Done { id: u64, t_resolved: u64, accounts: Vec<Pk> }

pub struct CommitTracker {
    pub cfg: TrackerCfg,
    reg: HashMap<[u8; 64], Reg>,
    reg_order: VecDeque<(u64, [u8; 64])>,
    pending: BTreeMap<u64, Group>,
    by_txn: HashMap<[u8; 64], u64>,
    /// account -> the pending groups that name it
    pend_accts: HashMap<Pk, Vec<u64>>,
    resolved: HashMap<[u8; 64], Done>,
    resolved_order: VecDeque<(u64, [u8; 64])>,
    next_id: u64,
    /// registrations that came after the transaction's group resolved (W(T) learned too late to matter)
    pub w_after_resolve: u64,
}

impl CommitTracker {
    pub fn new(cfg: TrackerCfg) -> CommitTracker {
        CommitTracker { cfg, reg: HashMap::default(), reg_order: VecDeque::new(), pending: BTreeMap::new(), by_txn: HashMap::default(), pend_accts: HashMap::default(),
            resolved: HashMap::default(), resolved_order: VecDeque::new(), next_id: 0, w_after_resolve: 0 }
    }

    /// whether an account is pending: named by a pending group's W(T), or carrying an update of a pending group
    pub fn is_pending(&self, acct: &Pk) -> bool { self.pend_accts.get(acct).is_some_and(|v| !v.is_empty()) }
    pub fn pending_groups(&self) -> usize { self.pending.len() }
    /// the earliest deadline of a pending group (receive-time clock): when the engine's timers have work
    pub fn next_deadline(&self) -> Option<u64> { self.pending.values().map(|g| g.deadline(&self.cfg)).min() }
    /// the pending groups, in opening order (digest)
    pub fn pending(&self) -> impl Iterator<Item = &Group> { self.pending.values() }

    /// Register W(T) (`w`: the watched accounts T writes) from `src`. A pending group of T takes it (a tx-stream W(T)
    /// replaces a shred hint's: it is authoritative) and may complete; otherwise it waits for T's first update
    pub fn register(&mut self, txn: [u8; 64], mut w: Vec<Pk>, src: WSrc, t_engine: u64) -> Vec<Resolution> {
        self.prune(t_engine);
        w.sort();
        w.dedup();
        if w.is_empty() { return vec![]; }
        if let Some(&id) = self.by_txn.get(&txn) {
            let upgrade = { let g = &self.pending[&id]; g.w.is_none() || (g.w_src == WSrc::Shred && src == WSrc::TxStream) };
            if !upgrade { return vec![]; }
            let old: Vec<Pk> = self.pending[&id].w.clone().unwrap_or_default();
            for a in &old { self.unindex(a, id); }
            {
                let g = self.pending.get_mut(&id).unwrap();
                g.w = Some(w.clone());
                g.w_src = src;
                g.w_late = true;
            }
            let seen: Vec<Pk> = self.pending[&id].seen.iter().map(|m| m.acct).collect();
            for a in w.iter().chain(seen.iter()) { self.index(*a, id); }
            return match self.pending[&id].complete() { Some(o) => vec![self.resolve(id, o, t_engine, t_engine, By::Register)], None => vec![] };
        }
        if self.resolved.contains_key(&txn) { self.w_after_resolve += 1; return vec![]; }
        match self.reg.get(&txn) {
            Some(r) if r.src == WSrc::TxStream && src == WSrc::Shred => {}
            _ => {
                if self.reg.insert(txn, Reg { w, src }).is_none() { self.reg_order.push_back((t_engine, txn)); }
            }
        }
        vec![]
    }

    /// One account update the store accepted (`txn`: the transaction that wrote it, None for RPC reads; `stream`: it came
    /// on the state stream, so its receive time is stream evidence). Returns the groups that resolved, in opening order,
    /// and a late member if this update is one
    #[allow(clippy::too_many_arguments)]
    pub fn on_update(&mut self, acct: Pk, txn: Option<[u8; 64]>, slot: u64, wv: u64, aseq: u64, t_recv: u64, t_engine: u64, stream: bool)
        -> (Vec<Resolution>, Option<Late>) {
        let mut out = Vec::new();
        let mut late = None;
        // a newer version from another transaction satisfies a pending group's member it has not seen
        if let Some(ids) = self.pend_accts.get(&acct).cloned() {
            for id in ids {
                let Some(g) = self.pending.get_mut(&id) else { continue };
                if txn == Some(g.txn) { continue; }
                let in_w = g.w.as_ref().is_some_and(|w| w.contains(&acct));
                if !in_w || g.seen.iter().any(|m| m.acct == acct) || g.superseded.contains(&acct) { continue; }
                let newer = if stream { (slot, wv) > g.newest() } else { slot > g.newest().0 };
                if newer { g.superseded.push(acct); }
            }
        }
        if let Some(t) = txn {
            let m = Member { acct, slot, wv, aseq, t: t_recv };
            if let Some(&id) = self.by_txn.get(&t) {
                let g = self.pending.get_mut(&id).unwrap();
                if !g.seen.iter().any(|x| x.acct == acct) {
                    g.seen.push(m);
                    g.t_last_update = g.t_last_update.max(t_recv);
                    self.index(acct, id);
                }
            } else if let Some(d) = self.resolved.get(&t) {
                // a late member: the group resolved without it; it opens a new group (W unknown)
                let (prev_id, prev_t, prev_accounts) = (d.id, d.t_resolved, d.accounts.clone());
                let id = self.open(t, slot, m.clone(), None, t_engine);
                self.pending.get_mut(&id).unwrap().reopened_from = Some(prev_id);
                late = Some(Late { txn: t, prev_id, prev_t_resolved: prev_t, prev_accounts, member: m, reopened_id: id });
            } else {
                let r = self.reg.remove(&t);
                self.open(t, slot, m, r, t_engine);
            }
        }
        // every pending group that names this account may be complete now
        if let Some(ids) = self.pend_accts.get(&acct).cloned() {
            for id in ids {
                if let Some(o) = self.pending.get(&id).and_then(|g| g.complete()) { out.push(self.resolve(id, o, t_engine, t_recv, By::Member)); }
            }
        }
        // stream evidence: the stream has moved past these groups' deadlines
        if stream { out.extend(self.expire_by(t_recv, t_engine, By::Stream)); }
        out.sort_by_key(|r| r.group.id);
        (out, late)
    }

    /// Stream evidence without an account update (a slot status on the state stream, received at `t_recv`)
    pub fn stream_time(&mut self, t_recv: u64, t_engine: u64) -> Vec<Resolution> { self.expire_by(t_recv, t_engine, By::Stream) }

    /// The timers (the engine's queue is empty): resolve every group whose deadline is at or before `t`
    pub fn expire(&mut self, t: u64) -> Vec<Resolution> { self.prune(t); self.expire_by(t, t, By::Timer) }

    fn expire_by(&mut self, x: u64, t_engine: u64, by: By) -> Vec<Resolution> {
        let due: Vec<(u64, Outcome)> = self.pending.values().filter(|g| g.deadline(&self.cfg) <= x)
            .map(|g| (g.id, if g.w.is_some() { Outcome::TimeoutUnknown } else { Outcome::TimeoutQuiescent })).collect();
        due.into_iter().map(|(id, o)| self.resolve(id, o, t_engine, x, by)).collect()
    }

    /// The groups opened in slots a fork abandoned
    pub fn drop_slots(&mut self, abandoned: &dyn Fn(u64) -> bool, t_engine: u64) -> Vec<Resolution> {
        let ids: Vec<u64> = self.pending.values().filter(|g| abandoned(g.slot)).map(|g| g.id).collect();
        ids.into_iter().map(|id| self.resolve(id, Outcome::ForkDropped, t_engine, t_engine, By::Fork)).collect()
    }

    /// The groups of `txns` opened in `slot` (slot-index `missing` evidence: the confirmed block of that slot does not
    /// hold them; review WP-04 #7)
    pub fn drop_txns(&mut self, slot: u64, txns: &[[u8; 64]], t_engine: u64) -> Vec<Resolution> {
        let ids: Vec<u64> = self.pending.values().filter(|g| g.slot == slot && txns.contains(&g.txn)).map(|g| g.id).collect();
        ids.into_iter().map(|id| self.resolve(id, Outcome::ForkDropped, t_engine, t_engine, By::Fork)).collect()
    }

    fn open(&mut self, txn: [u8; 64], slot: u64, m: Member, r: Option<Reg>, t_engine: u64) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        let (w, w_src) = match r { Some(r) => (Some(r.w), r.src), None => (None, WSrc::Unknown) };
        let t = m.t;
        let g = Group { id, txn, slot, w, w_src, w_late: false, seen: vec![m], superseded: vec![], t_first_update: t, t_last_update: t, t_first_engine: t_engine,
            reopened_from: None };
        for a in g.accounts() { self.index(a, id); }
        self.by_txn.insert(txn, id);
        self.pending.insert(id, g);
        id
    }

    fn resolve(&mut self, id: u64, outcome: Outcome, t_resolved: u64, t_clock: u64, by: By) -> Resolution {
        let g = self.pending.remove(&id).expect("a pending group");
        self.by_txn.remove(&g.txn);
        let accounts = g.accounts();
        for a in &accounts { self.unindex(a, id); }
        // a group a fork dropped is not remembered: if its transaction executes again on the canonical branch, its
        // updates open a new group rather than count as late members of the dropped one (review WP-04 N3: nothing was torn)
        if outcome != Outcome::ForkDropped {
            self.resolved.insert(g.txn, Done { id, t_resolved, accounts });
            self.resolved_order.push_back((t_resolved, g.txn));
        }
        Resolution { group: g, outcome, t_resolved, t_clock, by }
    }

    fn index(&mut self, a: Pk, id: u64) {
        let v = self.pend_accts.entry(a).or_default();
        if !v.contains(&id) { v.push(id); }
    }
    fn unindex(&mut self, a: &Pk, id: u64) {
        if let Some(v) = self.pend_accts.get_mut(a) {
            v.retain(|x| *x != id);
            if v.is_empty() { self.pend_accts.remove(a); }
        }
    }

    /// forget registrations and resolved groups past their windows (and past the size cap, the oldest first)
    fn prune(&mut self, t: u64) {
        while let Some(&(t0, txn)) = self.reg_order.front() {
            if t.saturating_sub(t0) < self.cfg.reg_keep_ns && self.reg_order.len() <= KEEP_MAX { break; }
            self.reg_order.pop_front();
            self.reg.remove(&txn);
        }
        while let Some(&(t0, txn)) = self.resolved_order.front() {
            if t.saturating_sub(t0) < self.cfg.late_window_ns && self.resolved_order.len() <= KEEP_MAX { break; }
            self.resolved_order.pop_front();
            if self.resolved.get(&txn).is_some_and(|d| d.t_resolved == t0) { self.resolved.remove(&txn); }
        }
    }

    /// a digest of the tracker's state (replay determinism)
    pub fn digest(&self, x: &mut xxhash_rust::xxh3::Xxh3) {
        for g in self.pending.values() {
            x.update(&g.id.to_le_bytes());
            x.update(&g.txn);
            x.update(&[g.w_src as u8, g.w.is_some() as u8]);
            for m in &g.seen { x.update(&m.acct); x.update(&m.wv.to_le_bytes()); }
            for a in &g.superseded { x.update(a); }
        }
        x.update(&self.next_id.to_le_bytes());
        x.update(&(self.reg.len() as u64).to_le_bytes());
        x.update(&(self.resolved.len() as u64).to_le_bytes());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    const MS: u64 = 1_000_000;
    fn k(n: u8) -> Pk { [n; 32] }
    fn t(n: u8) -> [u8; 64] { [n; 64] }
    fn tracker() -> CommitTracker { CommitTracker::new(TrackerCfg::new(5, 3)) }
    fn outs(r: &[Resolution]) -> Vec<(u8, Outcome)> { r.iter().map(|r| (r.group.txn[0], r.outcome)).collect() }

    /// PLAN WP-04 acceptance, commit groups: a known W(T) completes when every member has an update stamped T; until
    /// then every account of W(T) is pending (also the ones whose update has not come yet)
    #[test]
    fn a_known_write_set_completes_on_its_last_member() {
        let mut c = tracker();
        assert!(c.register(t(1), vec![k(1), k(2), k(3)], WSrc::Shred, 0).is_empty());
        let (r, _) = c.on_update(k(1), Some(t(1)), 10, 100, 0, 1 * MS, 1 * MS, true);
        assert!(r.is_empty());
        assert!(c.is_pending(&k(1)) && c.is_pending(&k(3)), "W(T) members are pending before their update arrives");
        let (r, _) = c.on_update(k(3), Some(t(1)), 10, 101, 1, 2 * MS, 2 * MS, true);
        assert!(r.is_empty());
        let (r, _) = c.on_update(k(2), Some(t(1)), 10, 102, 2, 3 * MS, 3 * MS, true);
        assert_eq!(outs(&r), vec![(1, Outcome::Complete)]);
        assert_eq!((r[0].by, r[0].group.w_src, r[0].group.seen.len()), (By::Member, WSrc::Shred, 3));
        assert!(!c.is_pending(&k(1)) && !c.is_pending(&k(2)) && c.pending_groups() == 0);
    }

    /// superseding: a member of W(T) whose next version comes from another transaction (a newer write version) is
    /// satisfied without T's own update (T may not have changed it)
    #[test]
    fn a_newer_write_supersedes_a_missing_member() {
        let mut c = tracker();
        c.register(t(1), vec![k(1), k(2)], WSrc::TxStream, 0);
        c.on_update(k(1), Some(t(1)), 10, 100, 0, 1 * MS, 1 * MS, true);
        let (r, _) = c.on_update(k(2), Some(t(9)), 10, 99, 1, 2 * MS, 2 * MS, true);
        assert!(r.iter().all(|x| x.group.txn != t(1)), "an older write of another transaction satisfies nothing");
        let (r, _) = c.on_update(k(2), Some(t(8)), 10, 105, 2, 2 * MS, 2 * MS, true);
        let mine: Vec<&Resolution> = r.iter().filter(|x| x.group.txn == t(1)).collect();
        assert_eq!((mine.len(), mine[0].outcome, mine[0].group.superseded.clone()), (1, Outcome::Superseded, vec![k(2)]));
    }

    /// timeouts under the virtual clock: a known W(T) still missing a member `commit_timeout_ms` after its first update is
    /// `timeout_unknown`; an unknown W(T) resolves `quiescence_ms` after its last update (`timeout_quiescent`), each
    /// later update pushing the deadline; the timers and stream evidence give the same result
    #[test]
    fn timeouts_and_quiescence() {
        let mut c = tracker();
        c.register(t(1), vec![k(1), k(2)], WSrc::Shred, 0);
        c.on_update(k(1), Some(t(1)), 10, 1, 0, 10 * MS, 10 * MS, false);
        c.on_update(k(5), Some(t(2)), 10, 2, 1, 11 * MS, 11 * MS, false);
        c.on_update(k(6), Some(t(2)), 10, 3, 2, 13 * MS, 13 * MS, false);
        assert_eq!(c.next_deadline(), Some(15 * MS));
        assert!(c.expire(15 * MS - 1).is_empty());
        assert_eq!(outs(&c.expire(15 * MS)), vec![(1, Outcome::TimeoutUnknown)]);
        assert_eq!(c.next_deadline(), Some(16 * MS), "the unknown group's deadline is its last update + 3 ms");
        assert_eq!(outs(&c.expire(16 * MS)), vec![(2, Outcome::TimeoutQuiescent)]);
        // the same through stream evidence: a later stream message received past the deadline
        let mut c = tracker();
        c.on_update(k(5), Some(t(3)), 10, 2, 1, 20 * MS, 20 * MS, true);
        let (r, _) = c.on_update(k(7), Some(t(4)), 10, 4, 2, 22 * MS, 30 * MS, true);
        assert!(r.is_empty(), "2 ms later: still quiet-pending, whatever the engine's backlog (t_engine 30 ms)");
        let r = c.stream_time(23 * MS, 31 * MS);
        assert_eq!((outs(&r), r[0].by, r[0].t_resolved), (vec![(3, Outcome::TimeoutQuiescent)], By::Stream, 31 * MS));
    }

    /// a registration that arrives while the group is pending gives it its W(T) (and may complete it at once); a
    /// tx-stream W(T) replaces a shred hint's; a registration after the group resolved is only counted
    #[test]
    fn late_registrations() {
        let mut c = tracker();
        c.on_update(k(1), Some(t(1)), 10, 1, 0, 1 * MS, 1 * MS, true);
        c.on_update(k(2), Some(t(1)), 10, 2, 1, 1 * MS, 1 * MS, true);
        let r = c.register(t(1), vec![k(2), k(1)], WSrc::TxStream, 2 * MS);
        assert_eq!((outs(&r), r[0].by, r[0].group.w_src, r[0].group.w_late), (vec![(1, Outcome::Complete)], By::Register, WSrc::TxStream, true));
        c.register(t(1), vec![k(1)], WSrc::TxStream, 3 * MS);
        assert_eq!(c.w_after_resolve, 1);
        let mut c = tracker();
        c.register(t(2), vec![k(1), k(2), k(3)], WSrc::Shred, 0);
        c.on_update(k(1), Some(t(2)), 10, 1, 0, 1 * MS, 1 * MS, true);
        c.on_update(k(2), Some(t(2)), 10, 2, 1, 1 * MS, 1 * MS, true);
        let r = c.register(t(2), vec![k(1), k(2)], WSrc::TxStream, 2 * MS);
        assert_eq!(outs(&r), vec![(2, Outcome::Complete)], "the authoritative W(T) has no third member");
        // a shred hint never downgrades a tx-stream registration
        let mut c = tracker();
        c.register(t(3), vec![k(1)], WSrc::TxStream, 0);
        c.register(t(3), vec![k(1), k(2)], WSrc::Shred, 0);
        let (r, _) = c.on_update(k(1), Some(t(3)), 10, 1, 0, 1 * MS, 1 * MS, true);
        assert_eq!(outs(&r), vec![(3, Outcome::Complete)]);
    }

    /// a late member: an update stamped T after T's group resolved is reported (with the resolved group's accounts and
    /// resolution time) and opens a new group
    #[test]
    fn a_late_member_is_reported_and_reopens() {
        let mut c = tracker();
        c.on_update(k(1), Some(t(1)), 10, 1, 0, 1 * MS, 1 * MS, true);
        let r = c.expire(4 * MS);
        assert_eq!(outs(&r), vec![(1, Outcome::TimeoutQuiescent)]);
        let (r, late) = c.on_update(k(2), Some(t(1)), 10, 2, 1, 6 * MS, 6 * MS, true);
        assert!(r.is_empty());
        let late = late.expect("late member");
        assert_eq!((late.prev_id, late.prev_t_resolved, late.prev_accounts.clone(), late.member.acct), (0, 4 * MS, vec![k(1)], k(2)));
        assert!(c.is_pending(&k(2)));
        let r = c.expire(9 * MS);
        assert_eq!((outs(&r), r[0].group.reopened_from), (vec![(1, Outcome::TimeoutQuiescent)], Some(0)));
    }

    /// forks: the pending groups of an abandoned slot become `fork_dropped`; slot-index `missing` evidence drops a
    /// transaction's group in that slot only; a transaction that executes again after its group was dropped opens a new
    /// group, not a late member (review WP-04 N3)
    #[test]
    fn groups_of_an_abandoned_slot_are_dropped() {
        let mut c = tracker();
        c.on_update(k(1), Some(t(1)), 10, 1, 0, 1 * MS, 1 * MS, true);
        c.on_update(k(2), Some(t(2)), 11, 2, 1, 1 * MS, 1 * MS, true);
        let r = c.drop_slots(&|s| s == 11, 2 * MS);
        assert_eq!((outs(&r), r[0].by), (vec![(2, Outcome::ForkDropped)], By::Fork));
        assert!(!c.is_pending(&k(2)) && c.is_pending(&k(1)));
        let (r, late) = c.on_update(k(2), Some(t(2)), 12, 3, 2, 2 * MS, 2 * MS, true);
        assert!(r.is_empty() && late.is_none(), "T2 again on the canonical branch: a new group");
        assert!(c.is_pending(&k(2)));
        assert!(c.drop_txns(10, &[t(2)], 3 * MS).is_empty(), "T2's group is in slot 12");
        assert_eq!(outs(&c.drop_txns(12, &[t(2), t(9)], 3 * MS)), vec![(2, Outcome::ForkDropped)]);
        assert!(c.is_pending(&k(1)));
    }
}

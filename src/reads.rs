//! RPC account reads the engine asks for (PLAN-ADDENDUM I-4; review WP-04 #1 and #7): the re-read of every followed
//! account after the state stream (re)connects (`resnapshot`), the accounts a fork left with no version
//! (`fork_refetch`), and newly followed DLMM bin arrays (`dlmm_arrays`).
//!
//! - **Chunks.** A job is split into chunks of at most `CHUNK` (100) accounts: one getMultipleAccounts call, so one
//!   context slot, per chunk. The re-read packs each pool's accounts into one chunk (its consistency set is then read at
//!   one slot: the skew rule holds after every reconnect, review WP-04 #1).
//! - **Answers.** Each chunk is read on the background runtime. Its accounts come back as account events (recorded in
//!   accounts.bin first), then one INPUT 11 `fetch` record says how the chunk ended (`ok`, its context `slot`, the
//!   accounts the node did not have; or the error). The journal holds both, so a replay sees exactly the run's answers.
//! - **Retries.** A failed chunk is read again after 250 ms, 1 s, 2 s and 5 s, then every 10 s, until its job's give-up
//!   time (then `GaveUp`). The engine also sends a re-read's chunk back here when it read a slot behind the stream.
//! - **Pace.** A job's chunks start at `first_at`, `pace` apart; at most `MAX_INFLIGHT` chunks are read at once (the
//!   rest wait for an answer). All times are engine times, run by the engine's timers: deterministic under replay.
use crate::feeds::src as asrc;
use crate::tx::Pk;
use std::collections::BTreeMap;

/// accounts per getMultipleAccounts call
pub const CHUNK: usize = 100;
/// chunks read at once, at most
pub const MAX_INFLIGHT: usize = 4;
/// the waits after a chunk's 1st, 2nd, ... failure, ms; then every `RETRY_EVERY_MS`
const RETRY_MS: [u64; 4] = [250, 1_000, 2_000, 5_000];
const RETRY_EVERY_MS: u64 = 10_000;

/// What a job reads (journal INPUT 11 `what`, `offline_fetches`). PLAN-ADDENDUM WP-21: `ClmmArrays`, newly followed
/// Raydium CLMM and Orca Whirlpool tick arrays (one the node does not have is then known not to exist)
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum What { Resync, ForkRefetch, DlmmArrays, ClmmArrays }

impl What {
    pub fn as_str(self) -> &'static str {
        match self { What::Resync => "resnapshot", What::ForkRefetch => "fork_refetch", What::DlmmArrays => "dlmm_arrays", What::ClmmArrays => "clmm_arrays" }
    }
    /// accounts.bin `src` of what it reads
    pub fn src(self) -> u8 { match self { What::Resync => asrc::RPC_SNAPSHOT, _ => asrc::RPC_REFETCH } }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
enum St { Due(u64), Inflight, Done, GaveUp }

#[derive(Clone, Debug)]
pub struct Chunk { pub keys: Vec<Pk>, st: St, pub attempts: u32, pub last_err: Option<String> }

impl Chunk {
    pub fn done(&self) -> bool { self.st == St::Done }
    pub fn gave_up(&self) -> bool { self.st == St::GaveUp }
}

#[derive(Clone, Debug)]
pub struct Job { pub id: u64, pub what: What, pub t_start: u64, pub give_up_ns: u64, pub chunks: Vec<Chunk>, pub retries: u32 }

impl Job {
    pub fn n_done(&self) -> usize { self.chunks.iter().filter(|c| c.done()).count() }
    pub fn last_err(&self) -> Option<&str> { self.chunks.iter().filter_map(|c| c.last_err.as_deref()).last() }
}

/// a chunk to read now (`attempt`: 1-based)
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Fetch { pub job: u64, pub chunk: usize, pub what: What, pub keys: Vec<Pk>, pub attempt: u32 }

/// what a failed answer led to
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Failed { Retry { at: u64, attempt: u32 }, GaveUp, Unknown }

#[derive(Default)]
pub struct Reads { next_id: u64, jobs: BTreeMap<u64, Job>, inflight: usize }

impl Reads {
    /// A job of `chunks` (in order): the k-th is first read at `first_at + k * pace_ns`; a chunk still failing
    /// `give_up_ns` after `t` is given up. Returns its id; the chunks that can start now go to `out`
    #[allow(clippy::too_many_arguments)]
    pub fn start(&mut self, what: What, chunks: Vec<Vec<Pk>>, t: u64, first_at: u64, pace_ns: u64, give_up_ns: u64, out: &mut Vec<Fetch>) -> u64 {
        let id = self.next_id;
        self.next_id += 1;
        let chunks = chunks.into_iter().enumerate().map(|(k, keys)| Chunk { keys, st: St::Due(first_at + k as u64 * pace_ns), attempts: 0, last_err: None }).collect();
        self.jobs.insert(id, Job { id, what, t_start: t, give_up_ns, chunks, retries: 0 });
        self.fill(t, out);
        id
    }

    /// the timers: chunks whose time has come start (as the in-flight cap allows)
    pub fn due(&mut self, t: u64, out: &mut Vec<Fetch>) { self.fill(t, out); }

    /// the earliest chunk start the timers must run for (None while the in-flight cap is reached: an answer frees a slot)
    pub fn next_due(&self) -> Option<u64> {
        if self.inflight >= MAX_INFLIGHT { return None; }
        self.jobs.values().flat_map(|j| j.chunks.iter()).filter_map(|c| match c.st { St::Due(at) => Some(at), _ => None }).min()
    }

    fn fill(&mut self, t: u64, out: &mut Vec<Fetch>) {
        while self.inflight < MAX_INFLIGHT {
            // the chunk due first (then by job and position: deterministic)
            let next = self.jobs.values().flat_map(|j| j.chunks.iter().enumerate().map(move |(k, c)| (j.id, k, c)))
                .filter_map(|(id, k, c)| match c.st { St::Due(at) if at <= t => Some((at, id, k)), _ => None }).min();
            let Some((_, id, k)) = next else { break };
            let j = self.jobs.get_mut(&id).unwrap();
            let c = &mut j.chunks[k];
            c.st = St::Inflight;
            c.attempts += 1;
            self.inflight += 1;
            out.push(Fetch { job: id, chunk: k, what: j.what, keys: c.keys.clone(), attempt: c.attempts });
        }
    }

    pub fn what_of(&self, job: u64) -> Option<What> { self.jobs.get(&job).map(|j| j.what) }
    pub fn job(&self, job: u64) -> Option<&Job> { self.jobs.get(&job) }
    /// chunks being read now
    pub fn inflight(&self) -> usize { self.inflight }
    /// chunks waiting for their (first or next) read
    pub fn pending(&self) -> usize { self.jobs.values().flat_map(|j| j.chunks.iter()).filter(|c| matches!(c.st, St::Due(_))).count() }

    fn inflight_chunk(&mut self, job: u64, chunk: usize) -> Option<&mut Chunk> {
        let c = self.jobs.get_mut(&job)?.chunks.get_mut(chunk)?;
        (c.st == St::Inflight).then_some(c)
    }

    /// A chunk's answer landed: its keys (the chunk is done), None for a job or chunk not being read (a cancelled job)
    pub fn landed(&mut self, job: u64, chunk: usize, t: u64, out: &mut Vec<Fetch>) -> Option<Vec<Pk>> {
        let c = self.inflight_chunk(job, chunk)?;
        c.st = St::Done;
        let keys = c.keys.clone();
        self.inflight = self.inflight.saturating_sub(1);
        self.fill(t, out);
        Some(keys)
    }

    /// A chunk's read failed (an RPC error, or a read the engine refused): read again later, or given up
    pub fn failed(&mut self, job: u64, chunk: usize, t: u64, err: String, out: &mut Vec<Fetch>) -> Failed {
        let Some(j) = self.jobs.get_mut(&job) else { return Failed::Unknown };
        let (t_start, give_up) = (j.t_start, j.give_up_ns);
        let Some(c) = j.chunks.get_mut(chunk).filter(|c| c.st == St::Inflight) else { return Failed::Unknown };
        c.last_err = Some(err);
        let r = if t.saturating_sub(t_start) >= give_up {
            c.st = St::GaveUp;
            Failed::GaveUp
        } else {
            let ms = RETRY_MS.get(c.attempts.saturating_sub(1) as usize).copied().unwrap_or(RETRY_EVERY_MS);
            let at = t + ms * 1_000_000;
            c.st = St::Due(at);
            j.retries += 1;
            Failed::Retry { at, attempt: c.attempts + 1 }
        };
        self.inflight = self.inflight.saturating_sub(1);
        self.fill(t, out);
        r
    }

    /// every chunk of the job has landed or was given up
    pub fn complete(&self, job: u64) -> bool { self.jobs.get(&job).is_some_and(|j| j.chunks.iter().all(|c| matches!(c.st, St::Done | St::GaveUp))) }

    /// forget a complete job (its last state returned)
    pub fn finish(&mut self, job: u64) -> Option<Job> { self.jobs.remove(&job) }

    /// drop a job (a newer re-read replaces it): its answers still in flight are ignored when they come
    pub fn cancel(&mut self, job: u64) {
        if let Some(j) = self.jobs.remove(&job) { self.inflight = self.inflight.saturating_sub(j.chunks.iter().filter(|c| c.st == St::Inflight).count()); }
    }

    /// a digest of the state (replay determinism)
    pub fn digest(&self, x: &mut dyn crate::engine::Fold) {
        x.update(&self.next_id.to_le_bytes());
        x.update(&(self.inflight as u64).to_le_bytes());
        for j in self.jobs.values() {
            x.update(&j.id.to_le_bytes());
            x.update(&j.retries.to_le_bytes());
            for c in &j.chunks {
                let (s, at) = match c.st { St::Due(at) => (0u8, at), St::Inflight => (1, 0), St::Done => (2, 0), St::GaveUp => (3, 0) };
                x.update(&[s]);
                x.update(&at.to_le_bytes());
                x.update(&c.attempts.to_le_bytes());
            }
        }
    }
}

/// Pack groups of accounts (each pool's own accounts first, then the rest) into chunks of at most `CHUNK`, never
/// splitting a group of at most `CHUNK` accounts
pub fn pack(groups: Vec<Vec<Pk>>) -> Vec<Vec<Pk>> {
    let mut out: Vec<Vec<Pk>> = Vec::new();
    let mut cur: Vec<Pk> = Vec::new();
    for g in groups {
        if g.len() > CHUNK {
            if !cur.is_empty() { out.push(std::mem::take(&mut cur)); }
            out.extend(g.chunks(CHUNK).map(|c| c.to_vec()));
            continue;
        }
        if cur.len() + g.len() > CHUNK { out.push(std::mem::take(&mut cur)); }
        cur.extend(g);
    }
    if !cur.is_empty() { out.push(cur); }
    out
}

#[cfg(test)]
mod tests {
    use super::*;

    const MS: u64 = 1_000_000;
    fn k(n: u8) -> Pk { [n; 32] }
    fn ids(f: &[Fetch]) -> Vec<(u64, usize, u32)> { f.iter().map(|x| (x.job, x.chunk, x.attempt)).collect() }

    /// a job's chunks start on their pace, at most MAX_INFLIGHT at once (an answer frees a slot); a failed chunk is read
    /// again after 250 ms, 1 s, 2 s, 5 s, then every 10 s, and given up past the job's give-up time
    #[test]
    fn chunks_pace_cap_retry_and_give_up() {
        let mut r = Reads::default();
        let mut out = Vec::new();
        let id = r.start(What::Resync, (0..6u8).map(|n| vec![k(n)]).collect(), 0, 400 * MS, 120 * MS, 60_000 * MS, &mut out);
        assert!(out.is_empty() && r.next_due() == Some(400 * MS), "nothing before its first read");
        r.due(400 * MS + 3 * 120 * MS, &mut out);
        assert_eq!(ids(&out), vec![(id, 0, 1), (id, 1, 1), (id, 2, 1), (id, 3, 1)]);
        r.due(10_000 * MS, &mut out);
        assert_eq!((out.len(), r.inflight(), r.next_due()), (4, 4, None), "the cap: the next one waits for an answer");
        out.clear();
        assert_eq!(r.landed(id, 0, 1_000 * MS, &mut out), Some(vec![k(0)]));
        assert_eq!(ids(&out), vec![(id, 4, 1)], "a slot freed: the next due chunk starts");
        assert!(r.landed(id, 0, 1_000 * MS, &mut out).is_none(), "an answer for a chunk not being read");
        out.clear();
        for c in [2usize, 3, 4] { assert!(r.landed(id, c, 1_000 * MS, &mut out).is_some()); }
        assert_eq!((ids(&out), r.inflight()), (vec![(id, 5, 1)], 2), "chunks 1 and 5 in flight");
        out.clear();
        let mut t = 1_000 * MS;
        let mut waits = Vec::new();
        for _ in 0..6 {
            match r.failed(id, 1, t, "429".into(), &mut out) { Failed::Retry { at, .. } => { waits.push((at - t) / MS); t = at; } x => panic!("{x:?}") }
            assert!(out.is_empty() && r.next_due() == Some(t), "not before its time");
            r.due(t, &mut out);
            assert_eq!(ids(&out).last().map(|x| (x.1, x.2)), Some((1, waits.len() as u32 + 1)), "chunk 1 read again at {t}");
            out.clear();
        }
        assert_eq!(waits, vec![250, 1_000, 2_000, 5_000, 10_000, 10_000]);
        assert_eq!(r.job(id).unwrap().retries, 6);
        assert!(!r.complete(id));
        assert_eq!(r.failed(id, 1, 60_000 * MS, "429".into(), &mut out), Failed::GaveUp);
        assert!(r.landed(id, 5, 60_001 * MS, &mut out).is_some());
        assert!(r.complete(id), "every chunk landed or given up");
        let j = r.finish(id).unwrap();
        assert_eq!((j.n_done(), j.chunks[1].gave_up(), j.last_err()), (5, true, Some("429")));
        assert_eq!((r.inflight(), r.pending()), (0, 0));
    }

    /// a cancelled job frees its in-flight slots; its late answers are ignored
    #[test]
    fn a_cancelled_job() {
        let mut r = Reads::default();
        let mut out = Vec::new();
        let a = r.start(What::Resync, vec![vec![k(1)], vec![k(2)]], 0, 0, 0, u64::MAX, &mut out);
        assert_eq!(r.inflight(), 2);
        r.cancel(a);
        assert_eq!((r.inflight(), r.what_of(a)), (0, None));
        assert!(r.landed(a, 0, 1, &mut out).is_none());
        assert_eq!(r.failed(a, 1, 1, "x".into(), &mut out), Failed::Unknown);
        assert_eq!(r.inflight(), 0);
    }

    /// groups are packed whole into chunks of at most 100
    #[test]
    fn packing_keeps_each_group_in_one_chunk() {
        let g = |n: usize, b: u8| (0..n).map(|i| { let mut x = [0u8; 32]; x[0] = b; x[1] = i as u8; x }).collect::<Vec<Pk>>();
        let c = pack(vec![g(60, 1), g(30, 2), g(20, 3), g(3, 4), g(250, 5)]);
        assert_eq!(c.iter().map(|x| x.len()).collect::<Vec<_>>(), vec![90, 23, 100, 100, 50]);
        assert!(c[1].starts_with(&g(20, 3)), "the 20-account group moved whole into the next chunk");
    }
}

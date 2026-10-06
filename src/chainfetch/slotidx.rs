//! The slot index (PLAN WP-03b item 3; F1, F10; MEASUREMENT §4.16b): one `getBlock(slot, {transactionDetails:
//! "signatures", rewards: false, commitment: "confirmed"})` per confirmed slot (about 3.7/s). The position of a
//! signature in the returned list is checked every slot against the transaction stream's `idx` (`idx_check`).
//!
//! **Positions and what they are (FT-000 S1-2).** In FT-000 the stream's `idx` and the slot index's position disagreed
//! in 73% of 394,225 comparisons, whole slots at a time, following the leader's client. The cause: Shyft's getBlock
//! with `transactionDetails: "signatures"` leaves the vote transactions out. Its list is the block's non-vote
//! transactions in block order, so a position is a signature's rank among the non-votes, not its block index (checked
//! on the public RPC: slots 453,426,744 / 745 / 747 hold 1,126 / 960 / 1,265 transactions, Shyft listed 461 / 331 /
//! 623, exactly the non-votes, and all 59 tracked positions equal the non-vote rank). It equals the block index only up
//! to the first vote, which is why slots whose leader puts every vote after the non-votes matched (453,426,743: 583
//! non-votes, then 667 votes). The other sources are block indexes: the stream's `TransactionInfo.index` (1,081 of 1,081
//! equal to the public RPC's getBlock position, slots 453,433,382..387) and Shyft's getTransaction `transactionIndex`
//! (2 of 2). So:
//! - each line says what its positions are (`pos_kind`): `nonvote_rank` when the provider's list leaves votes out (this
//!   slot shows it: a stream transaction listed below its index, none above; or the same provider showed it before:
//!   `votes_omitted`, kept per provider), `block_index` when the provider has not shown it and this slot's comparisons
//!   all match, `unverified` otherwise (no comparison, or one listed above its index); `idx_check` counts `below` and
//!   `above` beside the mismatches;
//! - a rank keeps the block order among non-vote transactions (what attribution compares within a slot), but it is
//!   never written as an `idx`: exec.jsonl / wallet.jsonl `idx_update` lines come only from `block_index` lines, and a
//!   record's `idx` is always a block index (the stream's, getTransaction's, or a full block's that holds the votes).
//!
//! What it yields, per slot (slotidx.jsonl, one line): blockhash, parent, height, block time, transaction count, the
//! positions of every tracked signature (D1: account updates stamped with the slot; D2: shred-seen candidates; ours),
//! and `missing`: D1 signatures stamped with this slot by an account update but absent from the confirmed block (fork
//! evidence for WP-04). The service turns the positions into `idx` for exec.jsonl / wallet.jsonl records (`idx_update`
//! lines), D2 candidates found into the coverage denominator (and the backfill), and the blockhash into the ring.
//!
//! Which slots: every slot the state stream reports confirmed. A gap between two confirmed slots is filled: the slots
//! after the new slot's parent were skipped on this fork (a line `status: "skipped"`, `by: "parent"`, no RPC call); the
//! others are fetched too (a skipped one answers -32007 / -32009). A block not available yet (-32004, -32014) is asked
//! again after 0.4, 0.8, 1.6 ... s, at most 12 times; other failures after 1, 2, 4 ... s, at most 6 times; then the line
//! is `status: "error"`. A call refused for want of a token (nothing was sent) is asked again 250 ms later without
//! using a try. A slot more than `max_lag` slots behind the newest confirmed one is dropped (counted: the `slotidx_pct`
//! coverage gauge shows it). The slot index goes before the backfill in every provider bucket they share (its role's
//! priority, `rpc::Role::priority`; review WP-03b #1).
use crate::rpc::{ErrClass, Fetched, RpcFailure};
use serde_json::{json, Value};
use std::collections::{BTreeMap, HashMap, HashSet, VecDeque};

/// What a tracked signature is to the slot index
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Kind { D1, D2, Ours }

#[derive(Default, Debug)]
pub struct Track { pub d1: Vec<[u8; 64]>, pub d2: Vec<[u8; 64]>, pub ours: Vec<[u8; 64]> }

impl Track {
    fn all(&self) -> Vec<([u8; 64], Kind)> {
        let mut seen = HashSet::new();
        let mut out = Vec::new();
        for (list, k) in [(&self.d1, Kind::D1), (&self.ours, Kind::Ours), (&self.d2, Kind::D2)] {
            for s in list { if seen.insert(*s) { out.push((*s, k)); } }
        }
        out
    }
}

struct Pend { next_ns: u64, tries: u32, inflight: bool }

/// One indexed (or skipped, or failed) slot
#[derive(Debug)]
pub struct Indexed {
    pub slot: u64,
    pub line: Value,
    /// tracked signatures found, with their block index
    pub found: Vec<([u8; 64], u64, Kind)>,
    /// D1 signatures stamped with this slot but absent from the block (or the slot was skipped): fork evidence
    pub missing: Vec<[u8; 64]>,
    /// D2 candidates not in the block (or the slot was skipped)
    pub d2_absent: Vec<[u8; 64]>,
    /// D2 candidates of a slot whose block could not be read: nothing is known of them (review WP-03b #11)
    pub d2_unknown: Vec<[u8; 64]>,
    /// (blockhash, height) of an ok block
    pub blockhash: Option<([u8; 32], Option<u64>)>,
    pub ok: bool,
    /// FT-000 (S1-2): what the positions in `found` are (`block_index`, `nonvote_rank`, `unverified`)
    pub pos_kind: &'static str,
}

/// FT-000 (S1-2): what a slot line's positions are, from the slot's `n` stream comparisons (`below`: listed before the
/// stream's index, `above`: after; `beyond`: a stream transaction sits at an index past the list's end) and whether the
/// provider has left votes out before. The list leaves transactions out when `beyond`, or when at least two comparisons
/// and half of them are listed below their index and none above (a list without the votes puts every non-vote at or
/// before its index); that is kept for the provider. `block_index`: no omission, and at least 90% of the comparisons
/// match (a stray mismatch is a stream copy from another fork); `unverified` otherwise. Returns (kind, omits)
pub fn pos_kind(n: u64, below: u64, above: u64, beyond: bool, omits_before: bool) -> (&'static str, bool) {
    let omits_here = beyond || (below >= 2 && above == 0 && below * 2 >= n);
    let omits = omits_before || omits_here;
    let matched = n.saturating_sub(below + above);
    let kind = if omits { "nonvote_rank" } else if n > 0 && matched * 10 >= n * 9 { "block_index" } else { "unverified" };
    (kind, omits)
}

/// What a getBlock reply came to
#[derive(Debug)]
pub enum Reply { Done(Box<Indexed>), Retry }

pub struct SlotIndex {
    pending: BTreeMap<u64, Pend>,
    tracked: HashMap<u64, Track>,
    stream: HashMap<u64, Vec<([u8; 64], u64)>>,
    last_confirmed: Option<u64>,
    pub newest_confirmed: u64,
    pub newest_done: u64,
    pub inflight: usize,
    pub max_inflight: usize,
    pub max_lag: u64,
    /// recently indexed ok slots (monotonic time, slot): the coverage sampler picks from them
    recent_ok: VecDeque<(u64, u64)>,
    /// coverage: confirmed slots (monotonic time, slot) to evaluate a minute later, and when each got its line
    cov_q: VecDeque<(u64, u64)>,
    line_at: HashMap<u64, u64>,
    pub ok_total: u64,
    pub skipped_total: u64,
    pub error_total: u64,
    pub dropped_total: u64,
    pub idx_n_total: u64,
    pub idx_mismatch_total: u64,
    pub slots_n_total: u64,
    pub slots_with_line_total: u64,
    /// calls refused for want of a token (asked again without using a try)
    pub refused_total: u64,
    /// FT-000 (S1-2): the providers whose getBlock list left the vote transactions out (seen once: kept), and the lines
    /// by position kind
    pub omits_votes: HashSet<String>,
    pub kind_block_index_total: u64,
    pub kind_nonvote_rank_total: u64,
    pub kind_unverified_total: u64,
    pub idx_below_total: u64,
    pub idx_above_total: u64,
}

/// the longest gap a new confirmed slot fills (a longer one, after an outage, is dropped and counted)
const MAX_FILL: u64 = 2_000;
const NOT_AVAILABLE_TRIES: u32 = 12;
const ERROR_TRIES: u32 = 6;

fn b58s(s: &[u8; 64]) -> String { bs58::encode(s).into_string() }

impl SlotIndex {
    pub fn new(max_inflight: usize, max_lag: u64) -> SlotIndex {
        SlotIndex { pending: BTreeMap::new(), tracked: HashMap::new(), stream: HashMap::new(), last_confirmed: None, newest_confirmed: 0, newest_done: 0, inflight: 0,
            max_inflight: max_inflight.max(1), max_lag: max_lag.max(10), recent_ok: VecDeque::new(), cov_q: VecDeque::new(), line_at: HashMap::new(), ok_total: 0,
            skipped_total: 0, error_total: 0, dropped_total: 0, idx_n_total: 0, idx_mismatch_total: 0, slots_n_total: 0, slots_with_line_total: 0, refused_total: 0,
            omits_votes: HashSet::new(), kind_block_index_total: 0, kind_nonvote_rank_total: 0, kind_unverified_total: 0, idx_below_total: 0, idx_above_total: 0 }
    }

    pub fn pending_now(&self) -> usize { self.pending.len() }
    /// how many confirmed slots, from the oldest not yet indexed to the newest, wait for their line (None: no confirmed
    /// slot seen yet)
    pub fn lag_slots(&self) -> Option<u64> {
        (self.newest_confirmed > 0).then(|| self.pending.keys().next().map_or(0, |s| self.newest_confirmed.saturating_sub(*s) + 1))
    }

    /// The state stream says `slot` is confirmed (its `parent` when sent; `now`: monotonic ns). Returns the slots this
    /// shows were skipped (between the parent and the slot, after the last confirmed slot): their lines need no RPC
    pub fn confirmed(&mut self, slot: u64, parent: Option<u64>, now: u64) -> Vec<u64> {
        if self.pending.contains_key(&slot) || self.line_at.contains_key(&slot) { return vec![]; }
        let mut skipped = Vec::new();
        if let Some(last) = self.last_confirmed.filter(|l| slot > l + 1) {
            if slot - last - 1 > MAX_FILL { self.dropped_total += slot - last - 1; }
            else {
                for s in last + 1..slot {
                    if parent.is_some_and(|p| s > p) { skipped.push(s); }
                    else if !self.pending.contains_key(&s) && !self.line_at.contains_key(&s) { self.add(s, now); }
                }
            }
        }
        self.add(slot, now);
        if self.last_confirmed.is_none_or(|l| slot > l) { self.last_confirmed = Some(slot); }
        if slot > self.newest_confirmed { self.newest_confirmed = slot; }
        for s in &skipped { self.cov_q.push_back((now, *s)); }
        skipped
    }

    fn add(&mut self, slot: u64, now: u64) {
        self.pending.insert(slot, Pend { next_ns: now, tries: 0, inflight: false });
        self.cov_q.push_back((now, slot));
    }

    /// a dead slot (the state stream's status 6): never confirmed, so nothing to fetch
    pub fn dead(&mut self, slot: u64) { if self.pending.get(&slot).is_some_and(|p| !p.inflight) { self.pending.remove(&slot); } }

    pub fn track(&mut self, slot: u64, sig: [u8; 64], k: Kind) {
        if slot <= self.newest_done && self.line_at.contains_key(&slot) { return; }
        let t = self.tracked.entry(slot).or_default();
        match k { Kind::D1 => t.d1.push(sig), Kind::D2 => t.d2.push(sig), Kind::Ours => t.ours.push(sig) }
    }

    /// a transaction stream's record of `sig` at `idx` in `slot` (the idx check)
    pub fn stream_idx(&mut self, slot: u64, sig: [u8; 64], idx: u64) { if !self.line_at.contains_key(&slot) { self.stream.entry(slot).or_default().push((sig, idx)); } }

    /// the slots to fetch now (oldest first, within the in-flight cap); slots too far behind are dropped
    pub fn due(&mut self, now: u64) -> Vec<u64> {
        let floor = self.newest_confirmed.saturating_sub(self.max_lag);
        let old: Vec<u64> = self.pending.iter().filter(|(s, p)| **s < floor && !p.inflight).map(|(s, _)| *s).collect();
        for s in old { self.pending.remove(&s); self.tracked.remove(&s); self.stream.remove(&s); self.dropped_total += 1; }
        let mut out = Vec::new();
        for (s, p) in self.pending.iter_mut() {
            if self.inflight + out.len() >= self.max_inflight { break; }
            if p.inflight || p.next_ns > now { continue; }
            p.inflight = true;
            out.push(*s);
        }
        self.inflight += out.len();
        out
    }

    /// A slot whose line needs no RPC: skipped on this fork (its parent says so)
    pub fn skipped_by_parent(&mut self, slot: u64, now: u64, t_ns: u64) -> Indexed {
        self.pending.remove(&slot);
        self.finish(slot, now);
        let track = self.tracked.remove(&slot).unwrap_or_default();
        self.stream.remove(&slot);
        self.skipped_total += 1;
        let line = json!({ "slot": slot, "parent_slot": null, "status": "skipped", "by": "parent", "blockhash": null, "previous_blockhash": null,
            "block_height": null, "block_time": null, "tx_count": 0, "tracked": [], "missing": track.d1.iter().map(b58s).collect::<Vec<_>>(),
            "idx_check": null, "t_fetch_ns": t_ns, "latency_ms": null, "provider": null });
        Indexed { slot, line, found: vec![], missing: track.d1, d2_absent: track.d2, d2_unknown: vec![], blockhash: None, ok: false, pos_kind: "unverified" }
    }

    fn finish(&mut self, slot: u64, now: u64) {
        self.line_at.insert(slot, now);
        if slot > self.newest_done { self.newest_done = slot; }
    }

    /// A getBlock reply for `slot` (`now` monotonic, `t_ns` wall clock)
    pub fn on_reply(&mut self, slot: u64, r: Result<Fetched, RpcFailure>, now: u64, t_ns: u64) -> Reply {
        self.inflight = self.inflight.saturating_sub(1);
        let (latency, provider) = match &r { Ok(f) => (Some(f.latency_ms), Some(f.provider.clone())), Err(e) => (None, e.provider.clone()) };
        let lat = latency.map(|l| (l * 1000.0).round() / 1000.0);
        let retry = |me: &mut SlotIndex, not_available: bool| -> bool {
            let Some(p) = me.pending.get_mut(&slot) else { return false };
            p.inflight = false;
            p.tries += 1;
            let (max, base) = if not_available { (NOT_AVAILABLE_TRIES, 400_000_000u64) } else { (ERROR_TRIES, 1_000_000_000) };
            if p.tries >= max { return false; }
            p.next_ns = now + (base << (p.tries - 1).min(5));
            true
        };
        match r {
            Ok(f) if !f.value.is_null() => {
                self.pending.remove(&slot);
                self.finish(slot, now);
                let track = self.tracked.remove(&slot).unwrap_or_default();
                let stream = self.stream.remove(&slot).unwrap_or_default();
                let omits_before = provider.as_ref().is_some_and(|p| self.omits_votes.contains(p));
                let ix = index_block(slot, &f.value, &track, &stream, t_ns, lat, provider.clone(), omits_before);
                if ix.line["votes_omitted"] == json!(true) { if let Some(p) = provider { self.omits_votes.insert(p); } }
                self.ok_total += 1;
                self.idx_n_total += ix.line["idx_check"]["n"].as_u64().unwrap_or(0);
                self.idx_mismatch_total += ix.line["idx_check"]["mismatches"].as_u64().unwrap_or(0);
                self.idx_below_total += ix.line["idx_check"]["below"].as_u64().unwrap_or(0);
                self.idx_above_total += ix.line["idx_check"]["above"].as_u64().unwrap_or(0);
                match ix.pos_kind { "block_index" => self.kind_block_index_total += 1, "nonvote_rank" => self.kind_nonvote_rank_total += 1, _ => self.kind_unverified_total += 1 }
                self.recent_ok.push_back((now, slot));
                while self.recent_ok.len() > 2_000 { self.recent_ok.pop_front(); }
                Reply::Done(Box::new(ix))
            }
            // a null block: not available here yet
            Ok(_) => if retry(self, true) { Reply::Retry } else { self.failed(slot, "not_available", "the block stayed unavailable", now, t_ns, lat, provider) },
            Err(e) if matches!(e.code, Some(-32007 | -32009)) => {
                self.pending.remove(&slot);
                self.finish(slot, now);
                let track = self.tracked.remove(&slot).unwrap_or_default();
                self.stream.remove(&slot);
                self.skipped_total += 1;
                let line = json!({ "slot": slot, "parent_slot": null, "status": "skipped", "by": "rpc", "blockhash": null, "previous_blockhash": null,
                    "block_height": null, "block_time": null, "tx_count": 0, "tracked": [], "missing": track.d1.iter().map(b58s).collect::<Vec<_>>(),
                    "idx_check": null, "t_fetch_ns": t_ns, "latency_ms": lat, "provider": provider, "rpc_code": e.code });
                Reply::Done(Box::new(Indexed { slot, line, found: vec![], missing: track.d1, d2_absent: track.d2, d2_unknown: vec![], blockhash: None, ok: false,
                    pos_kind: "unverified" }))
            }
            // refused for want of a token: nothing was sent; asked again soon, without using a try
            Err(e) if e.class == ErrClass::Budget => {
                let Some(p) = self.pending.get_mut(&slot) else { return self.failed(slot, "rate_budget", &e.msg, now, t_ns, lat, provider) };
                p.inflight = false;
                p.next_ns = now + 250_000_000;
                self.refused_total += 1;
                Reply::Retry
            }
            Err(e) if matches!(e.code, Some(-32004 | -32014)) => {
                if retry(self, true) { Reply::Retry } else { self.failed(slot, "not_available", &e.msg, now, t_ns, lat, provider) }
            }
            Err(e) => {
                if e.retryable && retry(self, false) { Reply::Retry } else { self.failed(slot, e.class.as_str(), &e.msg, now, t_ns, lat, provider) }
            }
        }
    }

    fn failed(&mut self, slot: u64, err: &str, msg: &str, now: u64, t_ns: u64, lat: Option<f64>, provider: Option<String>) -> Reply {
        self.pending.remove(&slot);
        self.finish(slot, now);
        let track = self.tracked.remove(&slot).unwrap_or_default();
        self.stream.remove(&slot);
        self.error_total += 1;
        let line = json!({ "slot": slot, "parent_slot": null, "status": "error", "err": err, "detail": msg.chars().take(200).collect::<String>(),
            "blockhash": null, "previous_blockhash": null, "block_height": null, "block_time": null, "tx_count": null, "tracked": [], "missing": [],
            "idx_check": null, "t_fetch_ns": t_ns, "latency_ms": lat, "provider": provider });
        // an unknown block says nothing about its candidates: the D2 ones are unknown (not absent), the D1 ones keep their
        // records
        Reply::Done(Box::new(Indexed { slot, line, found: vec![], missing: vec![], d2_absent: vec![], d2_unknown: track.d2, blockhash: None, ok: false,
            pos_kind: "unverified" }))
    }

    /// the newest ok slot indexed at least `min_age_ns` ago (the coverage sampler's block)
    pub fn sample_candidate(&self, now: u64, min_age_ns: u64) -> Option<u64> {
        self.recent_ok.iter().rev().find(|(t, _)| now.saturating_sub(*t) >= min_age_ns).map(|x| x.1)
    }

    /// Coverage (`slotidx_pct`): confirmed slots whose minute has passed, and how many got a line within it
    pub fn evaluate(&mut self, now: u64) {
        while let Some(&(t, s)) = self.cov_q.front() {
            if now.saturating_sub(t) < 60_000_000_000 { break; }
            self.cov_q.pop_front();
            self.slots_n_total += 1;
            if self.line_at.get(&s).is_some_and(|l| l.saturating_sub(t) <= 60_000_000_000) { self.slots_with_line_total += 1; }
        }
        let floor = self.cov_q.front().map_or(now, |x| x.0).min(now.saturating_sub(120_000_000_000));
        if self.line_at.len() > 4_096 { self.line_at.retain(|_, t| *t >= floor); }
        // tracked signatures of slots that will never be fetched (a long-lost confirmation) are dropped after a while
        if self.tracked.len() > 20_000 {
            let keep = self.newest_confirmed.saturating_sub(self.max_lag);
            self.tracked.retain(|s, _| *s >= keep);
            self.stream.retain(|s, _| *s >= keep);
        }
    }
}

/// The slotidx.jsonl line of one ok block, and what it says about the tracked signatures (`stream`: the transaction
/// stream's (signature, idx) stamped with this slot, for `idx_check`; `omits_before`: the provider has left the votes
/// out of a list before, FT-000 S1-2)
#[allow(clippy::too_many_arguments)]
pub fn index_block(slot: u64, b: &Value, track: &Track, stream: &[([u8; 64], u64)], t_ns: u64, latency_ms: Option<f64>, provider: Option<String>,
    omits_before: bool) -> Indexed {
    let sigs = b["signatures"].as_array().map(|a| a.as_slice()).unwrap_or(&[]);
    let pos: HashMap<&str, u64> = sigs.iter().enumerate().filter_map(|(i, s)| s.as_str().map(|s| (s, i as u64))).collect();
    let (mut found, mut missing, mut d2_absent) = (Vec::new(), Vec::new(), Vec::new());
    for (sig, k) in track.all() {
        match pos.get(b58s(&sig).as_str()) {
            Some(i) => found.push((sig, *i, k)),
            None => match k { Kind::D1 => missing.push(sig), Kind::D2 => d2_absent.push(sig), Kind::Ours => {} },
        }
    }
    let (mut n, mut mism, mut absent, mut below, mut above) = (0u64, 0u64, 0u64, 0u64, 0u64);
    for (sig, idx) in stream {
        match pos.get(b58s(sig).as_str()) {
            Some(i) => { n += 1; if i != idx { mism += 1; if i < idx { below += 1; } else { above += 1; } } }
            None => absent += 1,
        }
    }
    let beyond = stream.iter().any(|(sig, idx)| *idx >= sigs.len() as u64 && pos.contains_key(b58s(sig).as_str()));
    let (kind, omits) = pos_kind(n, below, above, beyond, omits_before);
    found.sort_by_key(|f| f.1);
    let blockhash = b["blockhash"].as_str().and_then(|h| bs58::decode(h).into_vec().ok()).and_then(|v| <[u8; 32]>::try_from(v).ok());
    let height = b["blockHeight"].as_u64();
    let line = json!({ "slot": slot, "parent_slot": b["parentSlot"], "status": "ok", "blockhash": b["blockhash"], "previous_blockhash": b["previousBlockhash"],
        "block_height": height, "block_time": b["blockTime"], "tx_count": sigs.len(),
        "tracked": found.iter().map(|(s, i, _)| json!([b58s(s), i])).collect::<Vec<_>>(), "missing": missing.iter().map(b58s).collect::<Vec<_>>(),
        "idx_check": { "n": n, "mismatches": mism, "absent": absent, "below": below, "above": above }, "pos_kind": kind, "votes_omitted": omits.then_some(true),
        "t_fetch_ns": t_ns, "latency_ms": latency_ms, "provider": provider });
    Indexed { slot, line, found, missing, d2_absent, d2_unknown: vec![], blockhash: blockhash.map(|h| (h, height)), ok: true, pos_kind: kind }
}

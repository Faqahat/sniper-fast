//! The blockhash ring (PLAN WP-03b item 4; F14): recent `(hash, slot, height, src)` from independent sources, so a
//! bundle never depends on one of them:
//! - `blocks_meta`: the state stream's block metas (WP-03 item 6, when the probe accepted them; processed);
//! - `slotidx`: the slot index's confirmed blocks (blockhash and height, every confirmed slot);
//! - `entries`: the last entry hash of a completed slot from the shred / entries assemblers (that slot's blockhash; the
//!   feed side is WP-08's: `chainfetch::note_entry_hash`; processed);
//! - `poll`: `getLatestBlockhash` (confirmed), at most every `blockhash_poll_ms`, and only while no other source gave
//!   a fresh confirmed blockhash (`fresh_confirmed_elsewhere`: learned in the last second, at most 8 slots behind the
//!   chain's newest slot): with the slot index running the poll is a fallback that costs nothing (review WP-03b #6). Its
//!   slot is the node's context slot, so it is compared with the others by height only.
//!
//! The builder (WP-05) takes the newest entry that meets its commitment and is not stale ([`Ring::best`]); the service
//! hands every change of the confirmed head to the engine as an INPUT `blockhash_head`. Two sources naming different
//! hashes for one slot (or height) are a disagreement (events.jsonl `blockhash_source_disagree`).
use std::collections::{BTreeMap, HashMap};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub enum Commitment { Processed, Confirmed, Finalized }
impl Commitment {
    pub fn as_str(self) -> &'static str { match self { Commitment::Processed => "processed", Commitment::Confirmed => "confirmed", Commitment::Finalized => "finalized" } }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
pub enum Src { BlocksMeta, Slotidx, Entries, Poll }
impl Src {
    pub fn as_str(self) -> &'static str { match self { Src::BlocksMeta => "blocks_meta", Src::Slotidx => "slotidx", Src::Entries => "entries", Src::Poll => "poll" } }
    /// the commitment of what the source reports
    pub fn commitment(self) -> Commitment { match self { Src::BlocksMeta | Src::Entries => Commitment::Processed, Src::Slotidx | Src::Poll => Commitment::Confirmed } }
}

/// One blockhash: its slot (the poll's: the node's context slot, approximate), height when known, who said it, when
#[derive(Clone, Debug, PartialEq)]
pub struct Entry { pub hash: [u8; 32], pub slot: u64, pub height: Option<u64>, pub src: Src, pub commitment: Commitment, pub t_ns: u64 }

/// Two sources disagree on a slot's (or a height's) blockhash
#[derive(Clone, Debug, PartialEq)]
pub struct Disagree { pub slot: Option<u64>, pub height: Option<u64>, pub a: (Src, [u8; 32]), pub b: (Src, [u8; 32]) }

pub struct Ring {
    /// slot-exact entries by slot (the newest `cap`)
    by_slot: BTreeMap<u64, Entry>,
    /// the latest poll answer
    poll: Option<Entry>,
    /// height -> (src, hash) for the disagreement check (the newest `cap`)
    by_height: BTreeMap<u64, (Src, [u8; 32])>,
    cap: usize,
    /// the newest slot the chain is known to be at (the state stream's processed slots), for ages in slots
    pub tip_slot: u64,
    pub inserts: HashMap<&'static str, u64>,
    pub disagreements: u64,
}

impl Ring {
    pub fn new(cap: usize) -> Ring { Ring { by_slot: BTreeMap::new(), poll: None, by_height: BTreeMap::new(), cap: cap.max(8), tip_slot: 0, inserts: HashMap::new(), disagreements: 0 } }

    /// the chain's newest slot moved
    pub fn note_slot(&mut self, slot: u64) { if slot > self.tip_slot { self.tip_slot = slot; } }

    /// Add what a source said. A disagreement (another hash for the same slot or height from another source) is returned
    /// and counted; the newer report is kept. The same hash from another source raises the entry's commitment
    pub fn insert(&mut self, e: Entry) -> Option<Disagree> {
        *self.inserts.entry(e.src.as_str()).or_default() += 1;
        let mut dis = None;
        if let Some(h) = e.height {
            match self.by_height.get(&h) {
                Some((s, x)) if *x != e.hash => dis = Some(Disagree { slot: (e.src != Src::Poll && *s != Src::Poll).then_some(e.slot), height: Some(h), a: (*s, *x), b: (e.src, e.hash) }),
                _ => {}
            }
            self.by_height.insert(h, (e.src, e.hash));
            while self.by_height.len() > self.cap { let k = *self.by_height.keys().next().unwrap(); self.by_height.remove(&k); }
        }
        if e.src == Src::Poll {
            self.note_slot(e.slot);
            if self.poll.as_ref().is_none_or(|p| (p.height, p.slot) <= (e.height, e.slot)) { self.poll = Some(e); }
        } else {
            match self.by_slot.get_mut(&e.slot) {
                Some(x) if x.hash != e.hash => {
                    if dis.is_none() { dis = Some(Disagree { slot: Some(e.slot), height: e.height.or(x.height), a: (x.src, x.hash), b: (e.src, e.hash) }); }
                    // the higher commitment stands (a processed report never replaces a confirmed one); else the newer
                    if e.commitment >= x.commitment { *x = e; }
                }
                Some(x) => {
                    if e.commitment > x.commitment { x.commitment = e.commitment; x.src = e.src; }
                    if x.height.is_none() { x.height = e.height; }
                }
                None => {
                    self.by_slot.insert(e.slot, e);
                    while self.by_slot.len() > self.cap { let k = *self.by_slot.keys().next().unwrap(); self.by_slot.remove(&k); }
                }
            }
        }
        if dis.is_some() { self.disagreements += 1; }
        dis
    }

    /// The newest entry of at least `min` commitment learned at most `max_age_ns` ago (`now_ns`): slot-exact entries by
    /// slot, the poll's by height against theirs when both have one
    pub fn best(&self, min: Commitment, now_ns: u64, max_age_ns: u64) -> Option<Entry> {
        let fresh = |e: &Entry| e.commitment >= min && now_ns.saturating_sub(e.t_ns) <= max_age_ns;
        let exact = self.by_slot.values().rev().find(|e| fresh(e));
        let poll = self.poll.as_ref().filter(|e| fresh(e));
        match (exact, poll) {
            (Some(a), Some(p)) => {
                let poll_newer = match (a.height, p.height) { (Some(ha), Some(hp)) => hp > ha, _ => p.slot > a.slot };
                Some(if poll_newer { p.clone() } else { a.clone() })
            }
            (Some(a), None) => Some(a.clone()),
            (None, Some(p)) => Some(p.clone()),
            (None, None) => None,
        }
    }

    /// slots between the chain's newest slot and `e`'s
    pub fn age_slots(&self, e: &Entry) -> Option<u64> { (self.tip_slot > 0).then(|| self.tip_slot.saturating_sub(e.slot)) }

    /// A source other than the poll gave a confirmed blockhash learned at most `max_age_ns` ago and at most `max_slots`
    /// behind the chain's newest slot (unknown: no limit): the poll is not needed now
    pub fn fresh_confirmed_elsewhere(&self, now_ns: u64, max_age_ns: u64, max_slots: u64) -> bool {
        self.by_slot.values().rev().take(16).any(|e| e.src != Src::Poll && e.commitment >= Commitment::Confirmed && now_ns.saturating_sub(e.t_ns) <= max_age_ns
            && (self.tip_slot == 0 || self.tip_slot.saturating_sub(e.slot) <= max_slots))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn e(hash: u8, slot: u64, height: Option<u64>, src: Src, t_ns: u64) -> Entry { Entry { hash: [hash; 32], slot, height, src, commitment: src.commitment(), t_ns } }

    /// PLAN WP-03b acceptance: the ring's source choice (the newest entry meeting the commitment), staleness, and
    /// disagreement between sources
    #[test]
    fn source_choice_staleness_and_disagreement() {
        let s = 1_000_000_000u64;
        let mut r = Ring::new(64);
        assert!(r.best(Commitment::Processed, 0, u64::MAX).is_none(), "empty");
        // the slot index's confirmed block 100, then the stream's processed block meta 102 (newer, but only processed)
        assert!(r.insert(e(1, 100, Some(90), Src::Slotidx, 10 * s)).is_none());
        assert!(r.insert(e(2, 102, Some(92), Src::BlocksMeta, 11 * s)).is_none());
        assert_eq!(r.best(Commitment::Confirmed, 12 * s, 60 * s).unwrap().slot, 100, "confirmed: the slot index's");
        let p = r.best(Commitment::Processed, 12 * s, 60 * s).unwrap();
        assert_eq!((p.slot, p.src), (102, Src::BlocksMeta), "processed: the newest of any source");
        // the poll (confirmed; context slot approximate) at height 91: newer than the slot index's 90 by height
        assert!(r.insert(e(3, 105, Some(91), Src::Poll, 12 * s)).is_none());
        let c = r.best(Commitment::Confirmed, 13 * s, 60 * s).unwrap();
        assert_eq!((c.src, c.height), (Src::Poll, Some(91)), "the poll's entry is newer by height");
        // the slot index confirms slot 102 with the block meta's hash: one entry, now confirmed, no disagreement
        assert!(r.insert(e(2, 102, Some(92), Src::Slotidx, 14 * s)).is_none());
        let c = r.best(Commitment::Confirmed, 14 * s, 60 * s).unwrap();
        assert_eq!((c.slot, c.commitment, c.hash), (102, Commitment::Confirmed, [2; 32]));
        // staleness: nothing confirmed learned in the last 0.5 s
        assert!(r.best(Commitment::Confirmed, 14 * s + 600_000_000, 500_000_000).is_none());
        // the shred assembler names another hash for slot 102: a disagreement, kept and counted
        let d = r.insert(e(9, 102, None, Src::Entries, 15 * s)).unwrap();
        assert_eq!((d.slot, d.a, d.b), (Some(102), (Src::Slotidx, [2; 32]), (Src::Entries, [9; 32])));
        // the poll disagrees by height with the slot index (height 92)
        let d = r.insert(e(7, 106, Some(92), Src::Poll, 16 * s)).unwrap();
        assert_eq!((d.height, d.slot, d.b.0), (Some(92), None, Src::Poll), "a poll is compared by height only");
        assert_eq!(r.disagreements, 2);
        // ages in slots against the chain's newest slot
        r.note_slot(110);
        let c = r.best(Commitment::Processed, 16 * s, 60 * s).unwrap();
        assert_eq!(r.age_slots(&c), Some(110 - c.slot));
        assert_eq!(r.inserts.get("slotidx"), Some(&2));
    }

    /// review WP-03b #6: the poll is needed only while no other source gave a fresh confirmed blockhash near the tip
    #[test]
    fn the_poll_is_needed_only_without_a_fresh_confirmed_source() {
        let s = 1_000_000_000u64;
        let mut r = Ring::new(64);
        assert!(!r.fresh_confirmed_elsewhere(10 * s, s, 8), "empty");
        r.insert(e(1, 100, Some(90), Src::BlocksMeta, 10 * s));
        assert!(!r.fresh_confirmed_elsewhere(10 * s, s, 8), "processed only");
        r.insert(e(2, 101, Some(91), Src::Slotidx, 10 * s));
        r.note_slot(104);
        assert!(r.fresh_confirmed_elsewhere(10 * s + s / 2, s, 8), "the slot index's, 3 slots behind, half a second old");
        assert!(!r.fresh_confirmed_elsewhere(12 * s, s, 8), "two seconds old");
        r.note_slot(120);
        assert!(!r.fresh_confirmed_elsewhere(10 * s, s, 8), "19 slots behind: the slot index lags");
        r.insert(e(3, 125, Some(95), Src::Poll, 10 * s));
        assert!(!r.fresh_confirmed_elsewhere(10 * s, s, 8), "the poll's own answer does not count");
    }

    /// the ring keeps only the newest `cap` slots
    #[test]
    fn the_ring_is_bounded() {
        let mut r = Ring::new(8);
        for s in 0..100 { r.insert(e((s % 250) as u8, s, Some(s), Src::Slotidx, s)); }
        assert_eq!(r.by_slot.len(), 8);
        assert_eq!(*r.by_slot.keys().next().unwrap(), 92);
        assert!(r.by_height.len() <= 8);
    }
}

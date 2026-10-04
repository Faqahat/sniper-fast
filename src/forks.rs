//! Forks (PLAN WP-04 item 9; review F4). At processed commitment a slot on a minority fork is streamed, its account
//! versions are stored, and the fork is then abandoned, usually with no `dead` status. Priced on, those versions are
//! phantoms (invariant 3). This keeps a tree of the slots the state stream reports (slot, parent, status) and says which
//! slots are abandoned and which are contested:
//! - **abandoned**: when slot S becomes confirmed (or finalized), every slot after the last root that is not an ancestor
//!   of S and is at most S (as far as the parents are known), every slot above S whose ancestry passes below S without
//!   going through it (a confirmed slot's higher-numbered sibling and its descendants: review WP-04 #3a), a `dead` slot,
//!   and every slot built on an abandoned one. A slot whose status arrives after the confirmation that dooms it is
//!   abandoned on arrival. The engine drops their versions from the store's rings (each account falls back to its newest
//!   surviving version: the store keeps an older-slot version from another branch below the current one, review WP-04
//!   #2; or it is fetched again), drops their pending commit groups (`fork_dropped`), re-evaluates the pools they
//!   touched, and marks decisions priced on them `fork_priced`. An account update written in a slot already abandoned
//!   is refused (`refuses`; review WP-04 #3b: interslot statuses can abandon a slot before its writes arrive);
//! - **contested**: an unconfirmed slot with an unconfirmed sibling (two children of one parent), and the slots built on
//!   it. A route that reads a version written in one is refused (`fork_pending`) until one branch is confirmed.
//! A slot's `bank_id` (Alpenglow providers send it; WP-03 #12) is kept: a dead status naming a bank abandons only that
//! bank's versions of the slot.
use std::collections::{BTreeMap, BTreeSet};

/// why a slot was abandoned (events.jsonl `fork_abandoned` / `fork_dead_slot`)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Why { Dead, NotAncestor, ParentAbandoned }

impl Why {
    pub fn as_str(self) -> &'static str { match self { Why::Dead => "dead", Why::NotAncestor => "not_ancestor", Why::ParentAbandoned => "parent_abandoned" } }
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Abandoned { pub slot: u64, pub why: Why, pub bank_id: Option<u64>, pub by: u64 }

#[derive(Clone, Debug, Default)]
struct Node { parent: Option<u64>, confirmed: bool, dead: bool, abandoned: bool, bank_id: Option<u64> }

/// at most this many slots are kept (the oldest go first), whatever the root
const MAX_NODES: usize = 4_096;

#[derive(Default)]
pub struct SlotTree {
    nodes: BTreeMap<u64, Node>,
    /// the newest finalized slot (0: none yet): nothing below it can change
    pub root: u64,
    pub confirmed_max: u64,
    contested: BTreeSet<u64>,
    /// totals (status.jsonl `forks`)
    pub abandoned_total: u64,
    pub dead_total: u64,
}

impl SlotTree {
    pub fn is_abandoned(&self, slot: u64) -> bool { self.nodes.get(&slot).is_some_and(|n| n.abandoned) }
    /// Whether an account version written in `slot` (bank `bank_id`) must be refused: the slot is already abandoned (for
    /// a slot with a known bank, only that bank's versions; the store's fork drop uses the same rule)
    pub fn refuses(&self, slot: u64, bank_id: Option<u64>) -> bool {
        self.nodes.get(&slot).is_some_and(|n| n.abandoned && (n.bank_id.is_none() || bank_id.is_none() || n.bank_id == bank_id))
    }
    /// a version written in this slot may still be on the losing branch (an unconfirmed sibling exists)
    pub fn is_contested(&self, slot: u64) -> bool { !self.contested.is_empty() && self.contested.contains(&slot) }
    pub fn contested_now(&self) -> usize { self.contested.len() }
    pub fn len(&self) -> usize { self.nodes.len() }
    pub fn is_empty(&self) -> bool { self.nodes.is_empty() }

    /// One slot status of the state stream (Yellowstone SlotStatus: 0 processed, 1 confirmed, 2 finalized, 3 first-shred,
    /// 4 completed, 5 created-bank, 6 dead). Returns the slots it abandoned, in slot order
    pub fn on_status(&mut self, slot: u64, parent: Option<u64>, status: i32, bank_id: Option<u64>) -> Vec<Abandoned> {
        if self.root > 0 && slot < self.root { return vec![]; }
        let mut out = Vec::new();
        let parent_abandoned = parent.is_some_and(|p| self.is_abandoned(p));
        {
            let n = self.nodes.entry(slot).or_default();
            if parent.is_some() { n.parent = parent; }
            if bank_id.is_some() { n.bank_id = bank_id; }
        }
        if parent_abandoned { self.abandon(slot, Why::ParentAbandoned, slot, &mut out); }
        match status {
            6 => {
                self.nodes.get_mut(&slot).unwrap().dead = true;
                self.dead_total += 1;
                // the dead slot itself may be confirmed elsewhere? never: a dead slot is not replayed
                let bank = bank_id.or(self.nodes[&slot].bank_id);
                if !self.nodes[&slot].abandoned { self.abandon_with(slot, Why::Dead, bank, slot, &mut out); }
            }
            1 | 2 => {
                self.confirm(slot, &mut out);
                if status == 2 && slot > self.root { self.root = slot; }
            }
            _ => {
                // a status of a slot the newest confirmation already decided (review WP-04 #3): an ancestor of it is
                // confirmed, a slot off its chain is abandoned at once
                match self.on_confirmed_chain(slot) {
                    Some(true) => { if let Some(n) = self.nodes.get_mut(&slot) { n.confirmed = true; } }
                    Some(false) => { let by = self.confirmed_max; self.abandon(slot, Why::NotAncestor, by, &mut out); }
                    None => {}
                }
            }
        }
        self.descendants(slot, &mut out);
        self.prune();
        self.recompute_contested();
        out.sort_by_key(|a| a.slot);
        out
    }

    fn abandon(&mut self, slot: u64, why: Why, by: u64, out: &mut Vec<Abandoned>) {
        let bank = self.nodes.get(&slot).and_then(|n| n.bank_id);
        self.abandon_with(slot, why, bank, by, out)
    }

    fn abandon_with(&mut self, slot: u64, why: Why, bank_id: Option<u64>, by: u64, out: &mut Vec<Abandoned>) {
        let n = self.nodes.entry(slot).or_default();
        if n.abandoned { return; }
        n.abandoned = true;
        self.abandoned_total += 1;
        out.push(Abandoned { slot, why, bank_id, by });
    }

    /// `slot` and its ancestors are confirmed; every other slot in (the bottom of its known ancestry, slot] is abandoned
    fn confirm(&mut self, slot: u64, out: &mut Vec<Abandoned>) {
        if slot > self.confirmed_max { self.confirmed_max = slot; }
        let mut chain = BTreeSet::new();
        let mut cur = slot;
        // the bottom (exclusive) of what the walk can decide: below it the ancestry is not known
        let lo;
        loop {
            chain.insert(cur);
            if let Some(n) = self.nodes.get_mut(&cur) { n.confirmed = true; }
            match self.nodes.get(&cur).and_then(|n| n.parent) {
                Some(p) if p > self.root && self.nodes.contains_key(&p) => cur = p,
                // the parent is below the root or was never seen: every slot between it and here is off the chain
                Some(p) => { lo = p; break; }
                None => { lo = cur; break; }
            }
        }
        if lo < slot {
            let off: Vec<u64> = self.nodes.range(lo + 1..=slot).filter(|(s, n)| !chain.contains(s) && !n.abandoned && !n.confirmed).map(|(s, _)| *s).collect();
            for s in off { self.abandon(s, Why::NotAncestor, slot, out); }
        }
        // review WP-04 #3a: a live slot above `slot` whose ancestry passes below it without going through it (siblings 12
        // and 13 of 11: once 12 is confirmed, 13 can never be canonical) is abandoned now, not at a later confirmation
        let above: Vec<u64> = self.nodes.range(slot + 1..).filter(|(_, n)| !n.abandoned && !n.confirmed).map(|(s, _)| *s).collect();
        for s in above { if self.descends(s, slot) == Some(false) { self.abandon(s, Why::NotAncestor, slot, out); } }
    }

    /// Whether `n` (above `h`) descends from `h`, as far as the known parents tell: Some(false) when its ancestry passes
    /// below `h` without going through it, None when a parent on the way is unknown
    fn descends(&self, n: u64, h: u64) -> Option<bool> {
        let mut cur = n;
        loop {
            let p = self.nodes.get(&cur).and_then(|x| x.parent)?;
            if p == h { return Some(true); }
            if p < h { return Some(false); }
            if !self.nodes.contains_key(&p) { return None; }
            cur = p;
        }
    }

    /// Where a live, unconfirmed slot stands against the newest confirmed slot `h` (`confirmed_max`): Some(true) an
    /// ancestor of `h` (so confirmed too), Some(false) off `h`'s chain (it can never be canonical: below `h` and not an
    /// ancestor, or above `h` and not a descendant), None when it cannot be told (no confirmation yet, a descendant of
    /// `h`, or a parent on the way unknown)
    fn on_confirmed_chain(&self, n: u64) -> Option<bool> {
        let h = self.confirmed_max;
        let node = self.nodes.get(&n)?;
        if h == 0 || n == h || node.confirmed || node.abandoned { return None; }
        if n > h { return match self.descends(n, h) { Some(false) => Some(false), _ => None }; }
        // below h: walk h's ancestry down to n's level
        let mut cur = h;
        loop {
            let p = self.nodes.get(&cur).and_then(|x| x.parent)?;
            if p == n { return Some(true); }
            if p < n { return Some(false); }
            if !self.nodes.contains_key(&p) { return None; }
            cur = p;
        }
    }

    /// every slot built on an abandoned one is abandoned too
    fn descendants(&mut self, by: u64, out: &mut Vec<Abandoned>) {
        let slots: Vec<u64> = self.nodes.keys().copied().collect();
        for s in slots {
            let n = &self.nodes[&s];
            if n.abandoned { continue; }
            if n.parent.is_some_and(|p| self.is_abandoned(p)) { self.abandon(s, Why::ParentAbandoned, by, out); }
        }
    }

    fn prune(&mut self) {
        if self.root > 0 {
            let keep = self.nodes.split_off(&self.root);
            self.nodes = keep;
        }
        while self.nodes.len() > MAX_NODES { let first = *self.nodes.keys().next().unwrap(); self.nodes.remove(&first); }
    }

    /// contested: an unconfirmed live slot whose parent has another unconfirmed live child, and its descendants
    fn recompute_contested(&mut self) {
        self.contested.clear();
        let mut kids: BTreeMap<u64, Vec<u64>> = BTreeMap::new();
        for (s, n) in &self.nodes {
            if n.abandoned || n.confirmed { continue; }
            if let Some(p) = n.parent { kids.entry(p).or_default().push(*s); }
        }
        for v in kids.values().filter(|v| v.len() >= 2) { for s in v { self.contested.insert(*s); } }
        if self.contested.is_empty() { return; }
        // their descendants (slots ascend from parent to child)
        let slots: Vec<(u64, Option<u64>)> = self.nodes.iter().filter(|(_, n)| !n.abandoned && !n.confirmed).map(|(s, n)| (*s, n.parent)).collect();
        for (s, p) in slots { if p.is_some_and(|p| self.contested.contains(&p)) { self.contested.insert(s); } }
    }

    /// a digest of the tree (replay determinism)
    pub fn digest(&self, x: &mut xxhash_rust::xxh3::Xxh3) {
        for (s, n) in &self.nodes {
            x.update(&s.to_le_bytes());
            x.update(&n.parent.unwrap_or(u64::MAX).to_le_bytes());
            x.update(&[n.confirmed as u8, n.dead as u8, n.abandoned as u8]);
        }
        x.update(&self.root.to_le_bytes());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn slots(v: &[Abandoned]) -> Vec<(u64, Why)> { v.iter().map(|a| (a.slot, a.why)).collect() }

    /// PLAN WP-04 acceptance (S8b): an abandoned sibling fork with no `dead` status is abandoned when the other branch is
    /// confirmed; while both siblings are unconfirmed, both are contested (`fork_pending`)
    #[test]
    fn a_sibling_fork_is_abandoned_when_the_other_branch_is_confirmed() {
        let mut t = SlotTree::default();
        assert!(t.on_status(100, Some(99), 1, None).is_empty());
        t.on_status(101, Some(100), 0, None);
        t.on_status(102, Some(100), 0, None);
        assert!(t.is_contested(101) && t.is_contested(102), "two unconfirmed children of 100");
        t.on_status(103, Some(102), 0, None);
        assert!(t.is_contested(103), "built on a contested slot");
        let a = t.on_status(103, Some(102), 1, None);
        assert_eq!(slots(&a), vec![(101, Why::NotAncestor)]);
        assert!(t.is_abandoned(101) && !t.is_abandoned(102) && !t.is_contested(102) && t.contested_now() == 0);
        // a slot that arrives later on the abandoned branch is abandoned at once
        let a = t.on_status(104, Some(101), 0, None);
        assert_eq!(slots(&a), vec![(104, Why::ParentAbandoned)]);
    }

    /// review WP-04 #3a (probe 2): siblings 12 and 13 of 11 are contested while both are unconfirmed; once 12 is
    /// confirmed, 13 (the higher-numbered one) can never be canonical and is abandoned at once, with what is built on it;
    /// a slot built on 12 stays live
    #[test]
    fn a_confirmed_slots_higher_numbered_sibling_is_abandoned_at_once() {
        let mut t = SlotTree::default();
        t.on_status(11, Some(10), 1, None);
        t.on_status(12, Some(11), 0, None);
        t.on_status(13, Some(11), 0, None);
        t.on_status(15, Some(13), 0, None);
        t.on_status(14, Some(12), 0, None);
        assert!(t.is_contested(12) && t.is_contested(13) && t.is_contested(15));
        let a = t.on_status(12, Some(11), 1, None);
        assert_eq!(slots(&a), vec![(13, Why::NotAncestor), (15, Why::NotAncestor)]);
        assert!(t.is_abandoned(13) && t.refuses(13, None) && !t.is_contested(13) && !t.is_abandoned(14) && t.contested_now() == 0);
        // a status that arrives later for a slot the confirmation doomed: abandoned on arrival (16 forks off 11, below 12)
        assert_eq!(slots(&t.on_status(16, Some(11), 3, None)), vec![(16, Why::NotAncestor)]);
        // below the confirmed chain's known bottom (11's parent 10 was never seen) nothing can be told: left alone
        assert!(t.on_status(9, Some(8), 0, None).is_empty());
        // an ancestor of the confirmed slot reported late is confirmed, not abandoned
        let mut t = SlotTree::default();
        t.on_status(21, Some(20), 1, None);
        assert!(t.on_status(20, Some(19), 0, None).is_empty());
        assert!(t.nodes[&20].confirmed);
    }

    /// review WP-04 #3b (probe 3): a slot created on an abandoned parent is abandoned before its writes arrive; `refuses`
    /// then turns its writes away (for a slot with a known bank, only that bank's)
    #[test]
    fn a_slot_abandoned_on_arrival_refuses_its_writes() {
        let mut t = SlotTree::default();
        t.on_status(12, Some(11), 0, None);
        t.on_status(13, Some(11), 0, None);
        assert_eq!(slots(&t.on_status(13, Some(11), 1, None)), vec![(12, Why::NotAncestor)]);
        assert_eq!(slots(&t.on_status(14, Some(12), 5, Some(9))), vec![(14, Why::ParentAbandoned)]);
        assert!(t.refuses(14, None) && t.refuses(14, Some(9)) && !t.refuses(14, Some(8)) && !t.refuses(13, None) && !t.refuses(99, None));
        assert!(t.on_status(14, Some(12), 0, Some(9)).is_empty(), "its processed status abandons nothing more");
    }

    /// a `dead` slot is abandoned with its descendants
    #[test]
    fn a_dead_slot_and_its_descendants() {
        let mut t = SlotTree::default();
        t.on_status(200, Some(199), 1, None);
        t.on_status(201, Some(200), 0, Some(7));
        t.on_status(202, Some(201), 0, None);
        let a = t.on_status(201, None, 6, None);
        assert_eq!(slots(&a), vec![(201, Why::Dead), (202, Why::ParentAbandoned)]);
        assert_eq!((a[0].bank_id, t.dead_total), (Some(7), 1));
    }

    /// a confirmed slot whose parent jumps over skipped slots abandons the skipped ones it saw (they were produced on
    /// another fork); slots below an unknown parent are left alone; finalized slots move the root and prune
    #[test]
    fn skipped_slots_unknown_parents_and_the_root() {
        let mut t = SlotTree::default();
        t.on_status(300, Some(299), 2, None);
        t.on_status(301, None, 3, None);
        t.on_status(303, Some(300), 0, None);
        let a = t.on_status(303, None, 1, None);
        assert_eq!(slots(&a), vec![(301, Why::NotAncestor)], "301 lies between 303 and its parent 300");
        // unknown parent: nothing below it is decided
        t.on_status(310, None, 0, None);
        t.on_status(311, None, 0, None);
        assert!(t.on_status(311, None, 1, None).is_empty());
        t.on_status(320, Some(311), 2, None);
        assert_eq!((t.root, t.nodes.keys().next().copied()), (320, Some(320)), "pruned below the root");
        assert!(t.on_status(305, Some(304), 0, None).is_empty(), "below the root: ignored");
    }
}

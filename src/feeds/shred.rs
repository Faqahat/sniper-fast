//! Raw shred handling: header parsing and a per-slot **streaming** assembler. Each data set (the data shreds from the
//! previous DATA_COMPLETE + 1 up to the next one) is one serialized Vec<Entry>. The assembler appends a data set's
//! payloads as soon as they are contiguous and parses transactions out of the growing buffer, so a transaction is
//! handed over the moment the shred holding its last byte has arrived (and every shred before it), not when the whole
//! data set is complete.
//!
//! Shred layout (Agave): signature [0..64], variant [64], slot u64 [65..73], index u32 [73..77], version u16 [77..79],
//! fec_set_index u32 [79..83]; data shreds add parent_offset u16 [83..85], flags u8 [85], size u16 [86..88].
//! A data shred's payload is bytes [88..size]. Variants: legacy data 0xA5, legacy code 0x5A; merkle data 0x8_/0x9_/0xB_,
//! merkle code 0x4_/0x6_/0x7_. Recovery (code) shreds are counted but not used yet: a missing data shred stalls its
//! data set until it arrives (or the slot is dropped).
//!
//! PoH (PLAN WP-08 item 2): the finished data sets are walked in index order from the slot's first entry, so every
//! transaction gets its position on the leader's clock and its entry's index (poh.log v2); the forwarded ones also go to
//! the PoH index (`feeds::poh_index`). Each slot's coverage is a slots-feed.log v2 line, written when the walk reaches
//! the slot's last shred (LAST_SHRED_IN_SLOT) or, short of that, when the slot is dropped (20 s after its first shred):
//! data and code shreds, data sets decoded and failed, ticks, entries and transactions walked, and `poh_complete` (the
//! walk covered the whole slot: its first data set to its last shred, 64 ticks). A slot walked from its first data set to
//! its last shred, with whole slots' worth of ticks (64, or more for a leader whose parent is slots back), ended on its
//! final tick, whose hash is the slot's blockhash: it goes to the chain-fetch service's blockhash ring (PLAN WP-03b item
//! 4, source `entries`; `chainfetch::note_entry_hash`).
use crate::tx::{parse_wire, scan, Pk, Tx};
use std::collections::{BTreeMap, HashMap};

pub const DATA_COMPLETE: u8 = 0x40;
/// LAST_SHRED_IN_SLOT (it includes DATA_COMPLETE)
pub const LAST_IN_SLOT: u8 = 0xC0;

#[derive(Debug, Clone, Copy, PartialEq)]
pub enum ShredKind { Data, Code }

pub struct Header { pub kind: ShredKind, pub slot: u64, pub index: u32, pub flags: u8 }

pub fn parse_header(b: &[u8]) -> Option<Header> {
    if b.len() < 88 { return None; }
    let v = b[64];
    let hi = v & 0xf0;
    let kind = if v == 0xa5 || hi == 0x80 || hi == 0x90 || hi == 0xb0 { ShredKind::Data }
        else if v == 0x5a || hi == 0x40 || hi == 0x60 || hi == 0x70 { ShredKind::Code }
        else { return None };
    let slot = u64::from_le_bytes(b[65..73].try_into().ok()?);
    let index = u32::from_le_bytes(b[73..77].try_into().ok()?);
    let flags = if kind == ShredKind::Data { b[85] } else { 0 };
    Some(Header { kind, slot, index, flags })
}

/// payload bytes of a data shred
pub fn data_payload(b: &[u8]) -> Option<&[u8]> {
    let size = u16::from_le_bytes([b[86], b[87]]) as usize;
    if size < 88 || size > b.len() { return None; }
    Some(&b[88..size])
}

struct Shred { t: u64, flags: u8, payload: Vec<u8> }

#[derive(Clone, Copy, PartialEq, Debug)]
enum Parse { Count, EntryHeader, Txs, Done, Failed }

/// One data set being parsed as its shreds arrive.
struct Stream {
    /// next shred index to append
    next: u32,
    buf: Vec<u8>,
    /// end offset of each appended shred, and the latest arrival time up to and including it
    ends: Vec<usize>,
    pref_t: Vec<u64>,
    /// the last appended shred carried DATA_COMPLETE: no more bytes will come
    complete: bool,
    pos: usize,
    state: Parse,
    entries_left: u64,
    txs_left: u64,
    /// the leader's PoH: per entry (num_hashes, transactions, first 8 bytes of each non-vote signature and whether it is
    /// forwarded)
    entries: Vec<(u64, u64, Vec<([u8; 8], bool)>)>,
    /// the hash of the last entry parsed (the set's last entry once it is done)
    last_hash: Option<[u8; 32]>,
}

impl Stream {
    fn new(start: u32) -> Stream {
        Stream { next: start, buf: Vec::with_capacity(16 * 1024), ends: Vec::new(), pref_t: Vec::new(), complete: false,
            pos: 0, state: Parse::Count, entries_left: 0, txs_left: 0, entries: Vec::new(), last_hash: None }
    }
    fn u64_at(&self, p: usize) -> Option<u64> { self.buf.get(p..p + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap())) }
    /// arrival time at which byte `end - 1` became available
    fn t_of(&self, end: usize) -> u64 {
        let k = self.ends.partition_point(|&x| x < end).min(self.ends.len().saturating_sub(1));
        self.pref_t.get(k).copied().unwrap_or(0)
    }
}

#[derive(Default)]
struct SlotState {
    first_t: u64,
    data: HashMap<u32, Shred>,
    /// open data sets by start index
    streams: BTreeMap<u32, Stream>,
    /// start index of the open stream waiting for shred `k` (its `next`)
    waiting: HashMap<u32, u32>,
    /// the PoH clock rebuilt from the shreds: finished data sets by start index (end, entries, the last entry's hash), the
    /// next set start in order, the hashes so far in the slot, the hash count at the last tick; u32::MAX = a set failed,
    /// no clock
    sets: BTreeMap<u32, (u32, Vec<(u64, u64, Vec<([u8; 8], bool)>)>, Option<[u8; 32]>)>,
    poh_next: u32,
    cum: u64,
    last_tick: u64,
    /// entries walked so far in the slot (poh.log `entry_idx`)
    entries: u64,
    /// slots-feed.log v2 (WP-08): the last shred's arrival, data and code shreds, data sets decoded and failed, ticks and
    /// transactions walked, the index of the slot's last shred, whether the walk started at its first set, and whether
    /// the slot's line was written
    t_last: u64,
    data_n: u64,
    code_n: u64,
    sets_ok: u64,
    sets_failed: u64,
    ticks: u64,
    txs: u64,
    last_index: Option<u32>,
    walk_started: bool,
    reported: bool,
    /// the hash of the last entry walked (the slot's blockhash once the walk is complete)
    last_hash: Option<[u8; 32]>,
}

#[derive(Default, Debug, Clone, serde::Serialize)]
pub struct AsmStats {
    pub data_shreds: u64,
    pub code_shreds: u64,
    pub dup_shreds: u64,
    pub bad_packets: u64,
    pub sets_decoded: u64,
    pub sets_failed: u64,
    pub txs: u64,
    pub votes: u64,
    pub implausible: u64,
    pub wrong_version: u64,
    /// interesting transactions fully decoded
    pub decoded: u64,
}

/// one interesting transaction and when it became decodable (kernel time of the shred that completed it), with its wire
/// bytes (the input journal, WP-03)
pub struct DecodedTx { pub slot: u64, pub t: u64, pub tx: Tx, pub raw: std::sync::Arc<[u8]> }

/// what makes a transaction worth decoding: a static key or a lookup table (checked in place, no allocation)
pub struct Want<'a> { pub key: &'a dyn Fn(&Pk) -> bool, pub table: &'a dyn Fn(&Pk) -> bool }

pub struct Assembler {
    slots: BTreeMap<u64, SlotState>,
    pub stats: AsmStats,
    keep_ns: u64,
    versions: HashMap<u16, u64>,
    version: Option<u16>,
    pub bad_samples: Vec<String>,
    /// hashes per tick, learned from the ticks (needed to turn hashes into ms)
    hpt: u64,
    /// where the PoH positions go (poh.log, with this feed id); off: the PoH clock is not rebuilt
    pub rec: crate::rec::Rec,
    pub feed: u16,
    /// the slots dropped lately (the newest `DROPPED_KEEP`): a late shred of one starts no second slots-feed line
    /// (review WP-08 #15)
    dropped: std::collections::BTreeSet<u64>,
}

/// dropped slots remembered (about 7 minutes of slots)
const DROPPED_KEEP: usize = 1_024;

impl Assembler {
    pub fn new() -> Assembler {
        Assembler { slots: BTreeMap::new(), stats: AsmStats::default(), keep_ns: 20_000_000_000,
            versions: HashMap::new(), version: None, bad_samples: Vec::new(), hpt: 0, rec: crate::rec::Rec::off(), feed: 0, dropped: Default::default() }
    }

    /// the shred version the feed settled on
    pub fn version(&self) -> Option<u16> { self.version }

    fn note_bad(&mut self, pkt: &[u8], why: &str) {
        if self.bad_samples.len() < 5 {
            let hex: String = pkt.iter().take(24).map(|b| format!("{b:02x}")).collect();
            self.bad_samples.push(format!("{why}: {} bytes, starts {hex}", pkt.len()));
        }
    }

    /// Feed one packet. Returns the header (for shred-level recording); appends any transactions it completed.
    pub fn push(&mut self, pkt: &[u8], t: u64, out: &mut Vec<DecodedTx>, want: &Want) -> Option<Header> {
        let h = match parse_header(pkt) { Some(h) => h, None => { self.stats.bad_packets += 1; self.note_bad(pkt, "not a shred"); return None; } };
        if h.slot < 100_000_000 || h.slot > 10_000_000_000 { self.stats.implausible += 1; self.note_bad(pkt, "implausible slot"); return None; }
        let ver = u16::from_le_bytes([pkt[77], pkt[78]]);
        match self.version {
            Some(v) if v != ver => { self.stats.wrong_version += 1; self.note_bad(pkt, "other shred version"); return None; }
            Some(_) => {}
            None => { let n = self.versions.entry(ver).or_insert(0); *n += 1; if *n >= 500 { self.version = Some(ver); } }
        }
        // a slot dropped already was reported then (or had nothing to report): a late shred of it starts no new line
        let late = self.dropped.contains(&h.slot);
        if h.kind == ShredKind::Code {
            self.stats.code_shreds += 1;
            let st = self.slots.entry(h.slot).or_insert_with(|| SlotState { first_t: t, reported: late, ..Default::default() });
            st.code_n += 1;
            st.t_last = st.t_last.max(t);
            return Some(h);
        }
        let payload = match data_payload(pkt) { Some(p) => p, None => { self.stats.bad_packets += 1; return Some(h); } };
        let st = self.slots.entry(h.slot).or_insert_with(|| SlotState { first_t: t, reported: late, ..Default::default() });
        if st.data.contains_key(&h.index) { self.stats.dup_shreds += 1; return Some(h); }
        self.stats.data_shreds += 1;
        st.data_n += 1;
        st.t_last = st.t_last.max(t);
        if h.flags & LAST_IN_SLOT == LAST_IN_SLOT { st.last_index = Some(h.index); }
        st.data.insert(h.index, Shred { t, flags: h.flags, payload: payload.to_vec() });
        // does this shred start a data set? (index 0, or the previous shred ended one)
        let starts_set = h.index == 0 || st.data.get(&(h.index - 1)).map_or(false, |p| p.flags & DATA_COMPLETE != 0);
        if starts_set && !st.streams.contains_key(&h.index) {
            st.streams.insert(h.index, Stream::new(h.index));
            st.waiting.insert(h.index, h.index);
        }
        // does it end one, with the next set's first shred already here?
        if h.flags & DATA_COMPLETE != 0 {
            let n = h.index + 1;
            if st.data.contains_key(&n) && !st.streams.contains_key(&n) {
                st.streams.insert(n, Stream::new(n));
                st.waiting.insert(n, n);
                Self::advance(st, n, h.slot, &mut self.stats, out, want, &mut self.hpt, &self.rec, self.feed);
            }
        }
        if let Some(&start) = st.waiting.get(&h.index) { Self::advance(st, start, h.slot, &mut self.stats, out, want, &mut self.hpt, &self.rec, self.feed); }
        Some(h)
    }

    /// Append every contiguous shred to stream `start`, then parse as far as the bytes go.
    #[allow(clippy::too_many_arguments)]
    fn advance(st: &mut SlotState, start: u32, slot: u64, stats: &mut AsmStats, out: &mut Vec<DecodedTx>, want: &Want, hpt: &mut u64, rec: &crate::rec::Rec, feed: u16) {
        let Some(s) = st.streams.get_mut(&start) else { return };
        st.waiting.remove(&s.next);
        while !s.complete {
            let Some(sh) = st.data.get(&s.next) else { break };
            s.buf.extend_from_slice(&sh.payload);
            s.ends.push(s.buf.len());
            let tmax = s.pref_t.last().copied().unwrap_or(0).max(sh.t);
            s.pref_t.push(tmax);
            if sh.flags & DATA_COMPLETE != 0 { s.complete = true; }
            s.next += 1;
        }
        if !s.complete { st.waiting.insert(s.next, start); }
        loop {
            match s.state {
                Parse::Count => match s.u64_at(s.pos) {
                    Some(n) if n <= 1_000_000 => { s.entries_left = n; s.pos += 8; s.state = if n == 0 { Parse::Done } else { Parse::EntryHeader }; }
                    Some(_) => s.state = Parse::Failed,
                    None => break,
                },
                Parse::EntryHeader => match s.u64_at(s.pos + 40) {
                    Some(n) if n <= 100_000 => {
                        let h = s.u64_at(s.pos).unwrap_or(0);
                        s.entries.push((h, n, Vec::new()));
                        s.last_hash = s.buf.get(s.pos + 8..s.pos + 40).and_then(|b| b.try_into().ok());
                        s.txs_left = n; s.pos += 48; s.state = Parse::Txs;
                    }
                    Some(_) => s.state = Parse::Failed,
                    None => break,
                },
                Parse::Txs => {
                    if s.txs_left == 0 {
                        s.entries_left -= 1;
                        s.state = if s.entries_left == 0 { Parse::Done } else { Parse::EntryHeader };
                        continue;
                    }
                    match scan(&s.buf[s.pos..], want.key, want.table) {
                        Some(sc) => {
                            let (start_b, end) = (s.pos, s.pos + sc.len);
                            s.pos = end;
                            s.txs_left -= 1;
                            if sc.is_vote { stats.votes += 1; continue; }
                            // the signature follows a 1-byte count (fewer than 128 signers)
                            if s.buf.get(start_b).is_some_and(|c| *c < 0x80) {
                                if let (Some(sig), Some(e)) = (s.buf.get(start_b + 1..start_b + 9), s.entries.last_mut()) { e.2.push((sig.try_into().unwrap(), sc.hit)); }
                            }
                            stats.txs += 1;
                            if !sc.hit { continue; }
                            if let Some((tx, n)) = parse_wire(&s.buf[start_b..end]) {
                                stats.decoded += 1;
                                let raw = std::sync::Arc::from(&s.buf[start_b..start_b + n.min(end - start_b)]);
                                out.push(DecodedTx { slot, t: s.t_of(end), tx, raw });
                            }
                        }
                        // not enough bytes yet, or garbage: only the latter once the data set is complete
                        None => { if s.complete { s.state = Parse::Failed; } else { break; } }
                    }
                }
                Parse::Done | Parse::Failed => break,
            }
        }
        match s.state {
            Parse::Done => {
                stats.sets_decoded += 1; st.sets_ok += 1; let n = s.next;
                let (ents, last) = (std::mem::take(&mut s.entries), s.last_hash);
                st.streams.remove(&start); st.waiting.remove(&n);
                st.sets.insert(start, (n, ents, last));
                Self::poh_advance(st, slot, hpt, rec, feed);
            }
            Parse::Failed => {
                stats.sets_failed += 1; st.sets_failed += 1;
                let n = s.next; st.streams.remove(&start); st.waiting.remove(&n); st.poh_next = u32::MAX; st.sets.clear();
            }
            _ => {}
        }
    }

    /// Walk the finished data sets in index order from the slot's start: every entry's hashes add up to its position
    /// on the leader's PoH clock (ticks give hashes per tick, 6.25 ms each); record each transaction's position in
    /// poh.log v2 (`sig8 slot ms feed entry_idx`; the entry's index in the slot is known here, the walk starts at the
    /// slot's first entry). A gap waits; a failed set stops the clock. Without a recorder nothing is rebuilt
    fn poh_advance(st: &mut SlotState, slot: u64, hpt: &mut u64, rec: &crate::rec::Rec, feed: u16) {
        if !rec.is_on() { st.sets.clear(); return; }
        let mut lines: Vec<(u64, f64, u64)> = Vec::new();
        let mut hits: Vec<(u64, super::entries::Poh)> = Vec::new();
        while let Some((end, ents, last)) = st.sets.remove(&st.poh_next) {
            if st.poh_next == 0 { st.walk_started = true; }
            if last.is_some() { st.last_hash = last; }
            for (h, ntx, sigs) in ents {
                let entry = st.entries;
                st.entries += 1;
                st.cum += h;
                st.txs += ntx;
                if ntx == 0 {
                    let d = st.cum - st.last_tick;
                    if d > 0 && (*hpt == 0 || d.abs_diff(*hpt) * 10 < *hpt) { *hpt = d; }   // ignore a tick after a gap
                    st.last_tick = st.cum;
                    st.ticks += 1;
                    continue;
                }
                if *hpt == 0 { continue; }
                let ms = st.cum as f64 / *hpt as f64 * (crate::feeds::entries::SLOT_US.load(std::sync::atomic::Ordering::Relaxed) as f64 / 64_000.0); // DET FIX: real slot length
                let p = super::entries::Poh { slot, hashes: st.cum, ticks: st.ticks as u32, hpt: *hpt };
                for (sg, hit) in sigs {
                    let k = u64::from_be_bytes(sg);
                    lines.push((k, ms, entry));
                    if hit { hits.push((k, p)); }
                }
            }
            st.poh_next = end;
        }
        super::poh_index().insert_many(&hits, feed, st.t_last);
        // the walk reached the slot's last shred: its slots-feed line now. A walk from the slot's first set to its last
        // shred walked every entry, so it ended on the slot's final tick, whose hash is the slot's blockhash (the chain-fetch
        // ring's `entries` source; ticks come in whole slots: 64, or more for a leader whose parent is slots back)
        if !st.reported && st.last_index.is_some_and(|l| st.poh_next != u32::MAX && st.poh_next == l + 1) {
            if st.walk_started && st.ticks > 0 && st.ticks % 64 == 0 { if let Some(h) = st.last_hash { crate::chainfetch::note_entry_hash(slot, h, feed); } }
            Self::report(st, slot, rec, feed);
        }
        // one record per data set's lines (they are formatted on the writer; counted as lines)
        if !lines.is_empty() {
            rec.emit(crate::rec::POH, crate::rec::Record::enc_lines(lines.len() as u32, move |o| {
                for (k, (sg, ms, e)) in lines.iter().enumerate() {
                    if k > 0 { o.push(b'\n'); }
                    let _ = std::io::Write::write_fmt(o, format_args!("{sg:016x} {slot} {ms:.3} {feed} {e}"));
                }
            }));
        }
    }

    /// slots-feed.log v2 for one slot: `feed slot ticks entries txs t_first t_last valid data_shreds code_shreds sets_ok
    /// sets_failed poh_complete` (`valid`: the walk started at the slot's first data set; `poh_complete`: it reached the
    /// slot's last shred with 64 ticks)
    fn report(st: &mut SlotState, slot: u64, rec: &crate::rec::Rec, feed: u16) {
        st.reported = true;
        if !rec.is_on() { return; }
        let complete = st.walk_started && st.last_index.is_some_and(|l| st.poh_next != u32::MAX && st.poh_next == l + 1) && st.ticks == 64;
        let (ticks, entries, txs, t0, t1, valid, d, c, ok, bad) = (st.ticks, st.entries, st.txs, st.first_t, st.t_last, st.walk_started as u8, st.data_n, st.code_n,
            st.sets_ok, st.sets_failed);
        rec.emit(crate::rec::SLOTS_FEED, crate::rec::Record::enc(move |o| {
            let _ = std::io::Write::write_fmt(o, format_args!("{feed} {slot} {ticks} {entries} {txs} {t0} {t1} {valid} {d} {c} {ok} {bad} {}", complete as u8));
        }));
    }

    /// drop the slots older than `keep_ns` (from their first shred); a slot whose line was not written yet (its walk
    /// never reached the last shred) is written now, and every dropped slot is remembered (one line per slot)
    pub fn gc(&mut self, now: u64) {
        let keep = self.keep_ns;
        let (rec, feed, dropped) = (&self.rec, self.feed, &mut self.dropped);
        self.slots.retain(|slot, s| {
            let keep_it = now.saturating_sub(s.first_t) < keep;
            if !keep_it {
                if !s.reported && s.data_n > 0 { Self::report(s, *slot, rec, feed); }
                dropped.insert(*slot);
            }
            keep_it
        });
        while self.dropped.len() > DROPPED_KEEP { self.dropped.pop_first(); }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn data_shred(slot: u64, index: u32, flags: u8, payload: &[u8]) -> Vec<u8> {
        let mut b = vec![0u8; 88];
        b[64] = 0x95;
        b[65..73].copy_from_slice(&slot.to_le_bytes());
        b[73..77].copy_from_slice(&index.to_le_bytes());
        b[85] = flags;
        let size = (88 + payload.len()) as u16;
        b[86..88].copy_from_slice(&size.to_le_bytes());
        b.extend_from_slice(payload);
        b.extend([0u8; 40]);
        b
    }

    fn tx(s: u8) -> Vec<u8> {
        let mut t = vec![1u8]; t.extend([s; 64]); t.extend([1, 0, 0, 1]); t.extend([4u8; 32]); t.extend([7u8; 32]); t.push(0); t
    }

    fn set(txs: &[Vec<u8>]) -> Vec<u8> {
        let mut buf = Vec::new();
        buf.extend(1u64.to_le_bytes()); buf.extend(0u64.to_le_bytes()); buf.extend([0u8; 32]); buf.extend((txs.len() as u64).to_le_bytes());
        for t in txs { buf.extend(t); }
        buf
    }

    fn all() -> Want<'static> { Want { key: &|_| true, table: &|_| true } }

    #[test]
    fn hands_over_each_transaction_as_soon_as_its_bytes_are_contiguous() {
        let (t1, t2) = (tx(0x11), tx(0x22));
        let buf = set(&[t1.clone(), t2]);
        let cut1 = 48 + 8 + t1.len() + 8; // tx 1 fully inside shred 0, plus 8 bytes of tx 2
        let (p0, rest) = buf.split_at(cut1);
        let (p1, p2) = rest.split_at(20);
        let mut asm = Assembler::new();
        let mut out = Vec::new();
        asm.push(&data_shred(300_000_000, 0, 0, p0), 100, &mut out, &all());
        assert_eq!(out.len(), 1, "tx 1 is complete in shred 0 and must be handed over right away");
        assert_eq!(out[0].tx.sig[0], 0x11);
        assert_eq!(out[0].t, 100);
        asm.push(&data_shred(300_000_000, 2, DATA_COMPLETE, p2), 300, &mut out, &all());
        assert_eq!(out.len(), 1, "shred 1 is still missing");
        asm.push(&data_shred(300_000_000, 1, 0, p1), 200, &mut out, &all());
        assert_eq!(out.len(), 2);
        assert_eq!(out[1].tx.sig[0], 0x22);
        assert_eq!(out[1].t, 300);
        assert_eq!(asm.stats.sets_decoded, 1);
    }

    #[test]
    fn second_data_set_starts_after_the_first_completes() {
        let a = set(&[tx(0x31)]);
        let b = set(&[tx(0x32)]);
        let mut asm = Assembler::new();
        let mut out = Vec::new();
        // set B's only shred (index 1) arrives before set A's (index 0, DATA_COMPLETE)
        asm.push(&data_shred(300_000_001, 1, DATA_COMPLETE, &b), 50, &mut out, &all());
        assert!(out.is_empty());
        asm.push(&data_shred(300_000_001, 0, DATA_COMPLETE, &a), 60, &mut out, &all());
        assert_eq!(out.len(), 2);
        assert_eq!(asm.stats.sets_decoded, 2);
    }

    /// a data set of entries (num_hashes, transactions)
    fn set_entries(ents: &[(u64, Vec<Vec<u8>>)]) -> Vec<u8> {
        let mut buf = (ents.len() as u64).to_le_bytes().to_vec();
        for (h, txs) in ents {
            buf.extend(h.to_le_bytes()); buf.extend([0u8; 32]); buf.extend((txs.len() as u64).to_le_bytes());
            for t in txs { buf.extend(t); }
        }
        buf
    }

    fn code_shred(slot: u64, index: u32) -> Vec<u8> {
        let mut b = vec![0u8; 120];
        b[64] = 0x6a;
        b[65..73].copy_from_slice(&slot.to_le_bytes());
        b[73..77].copy_from_slice(&index.to_le_bytes());
        b
    }

    fn recorder(name: &str) -> (std::path::PathBuf, crate::rec::Rec) {
        let d = std::env::temp_dir().join(format!("arbx-shred-{name}-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        (d, rec)
    }

    /// PLAN WP-08 acceptance, per-feed PoH from shreds: a slot delivered whole (its first data set, then the last one,
    /// ending in LAST_SHRED_IN_SLOT, plus a code shred) is one slots-feed.log v2 line with every column, written when the
    /// walk reaches the last shred: 64 ticks, 65 entries, 1 transaction, valid, 3 data and 1 code shreds, 2 sets decoded,
    /// poh complete; the forwarded transaction's position goes to the PoH index with the feed's id; dropping the slot
    /// later writes nothing more. A slot whose sets never started (its first shreds missing), and one with a failed set,
    /// are written when dropped, with poh_complete 0
    #[test]
    fn slot_coverage_from_shreds() {
        let (d, rec) = recorder("cov");
        let mut asm = Assembler::new();
        asm.rec = rec.clone();
        asm.feed = 4;
        let mut out = Vec::new();
        let tick = || (100u64, Vec::<Vec<u8>>::new());
        // slot A: set 0 = 32 ticks and an entry with one transaction (50 hashes after the 32nd tick: 203.125 ms); set 1
        // (shreds 1-2) = 32 ticks, the last shred LAST_IN_SLOT
        let a = 300_000_010u64;
        let mut first: Vec<(u64, Vec<Vec<u8>>)> = (0..32).map(|_| tick()).collect();
        first.push((50, vec![tx(0x51)]));
        let second: Vec<(u64, Vec<Vec<u8>>)> = (0..32).map(|_| tick()).collect();
        let s1 = set_entries(&second);
        let (s1a, s1b) = s1.split_at(s1.len() / 2);
        asm.push(&data_shred(a, 0, DATA_COMPLETE, &set_entries(&first)), 1_000, &mut out, &all());
        asm.push(&code_shred(a, 0), 1_100, &mut out, &all());
        asm.push(&data_shred(a, 1, 0, s1a), 1_200, &mut out, &all());
        asm.push(&data_shred(a, 2, LAST_IN_SLOT, s1b), 1_300, &mut out, &all());
        assert_eq!(out.len(), 1, "the transaction");
        let (p, feed) = crate::feeds::poh_index().get(u64::from_be_bytes([0x51; 8])).expect("indexed");
        assert_eq!((p.slot, p.hashes, p.ticks, p.hpt, p.ms(), feed), (a, 3_250, 32, 100, Some(203.125), 4));
        // slot B: only its last set (index 5, LAST_IN_SLOT): never walked; slot C: a set that does not parse
        let b = 300_000_011u64;
        asm.push(&data_shred(b, 5, LAST_IN_SLOT, &set_entries(&[(100, vec![])])), 2_000, &mut out, &all());
        let c = 300_000_012u64;
        asm.push(&data_shred(c, 0, DATA_COMPLETE, &[0xff; 40]), 3_000, &mut out, &all());
        assert_eq!((asm.stats.sets_decoded, asm.stats.sets_failed), (2, 1), "B's lone set never starts (its first shred is missing)");
        asm.gc(25_000_000_000);
        asm.gc(26_000_000_000);
        // review WP-08 #15: late shreds of slots already dropped (A, written whole; B, written when dropped) start no
        // second line when they are dropped in turn
        asm.push(&data_shred(a, 7, 0, &[0u8; 40]), 27_000_000_000, &mut out, &all());
        asm.push(&code_shred(b, 9), 27_000_000_000, &mut out, &all());
        asm.push(&data_shred(b, 6, 0, &[0u8; 40]), 27_000_000_000, &mut out, &all());
        asm.gc(48_000_000_000);
        rec.close();
        let lines = crate::rec::read_text(&d, "slots-feed").unwrap();
        assert_eq!(lines, vec![format!("4 {a} 64 65 1 1000 1300 1 3 1 2 0 1"), format!("4 {b} 0 0 0 2000 2000 0 1 0 0 0 0"), format!("4 {c} 0 0 0 3000 3000 0 1 0 0 1 0")]);
        let poh = crate::rec::read_text(&d, "poh").unwrap();
        assert_eq!(poh, vec![format!("5151515151515151 {a} 203.125 4 32")], "the transaction's entry is the slot's 33rd");
        let _ = std::fs::remove_dir_all(&d);
    }

    /// a data set of entries (num_hashes, hash, transactions)
    fn set_hashed(ents: &[(u64, [u8; 32], Vec<Vec<u8>>)]) -> Vec<u8> {
        let mut buf = (ents.len() as u64).to_le_bytes().to_vec();
        for (h, hash, txs) in ents {
            buf.extend(h.to_le_bytes()); buf.extend(hash); buf.extend((txs.len() as u64).to_le_bytes());
            for t in txs { buf.extend(t); }
        }
        buf
    }

    /// The merge of WP-03b and WP-08 (WP-03b's hand-off): a shred feed gives the chain-fetch service's blockhash ring each
    /// slot it walked whole, with the hash of the slot's last entry (its final tick: the slot's blockhash; source
    /// `entries`), once, when the walk reaches the last shred. Slot A: 64 ticks in two sets, the last tick's hash 0xAB.
    /// Slot B: a leader whose parent is a slot back, 128 ticks, ending on 0xCD. Slot C: its first set missing (never
    /// walked), and slot D: a set that does not parse; neither gives a hash, when it arrives or when it is dropped
    #[test]
    fn a_slot_walked_whole_gives_its_blockhash() {
        let (d, rec) = recorder("bh");
        let (shared, rx) = crate::chainfetch::Shared::new(std::sync::Arc::new(crate::rpc::Registry::default()));
        let mut asm = Assembler::new();
        asm.rec = rec.clone();
        asm.feed = 4;
        let mut out = Vec::new();
        let ticks = |n: usize, last: [u8; 32]| -> Vec<(u64, [u8; 32], Vec<Vec<u8>>)> {
            (0..n).map(|k| (100u64, if k + 1 == n { last } else { [k as u8; 32] }, Vec::new())).collect() };
        crate::chainfetch::with_test_service(shared, || {
            let a = 300_000_020u64;
            let mut first = ticks(32, [1; 32]);
            first.insert(5, (50, [2; 32], vec![tx(0x52)]));
            asm.push(&data_shred(a, 0, DATA_COMPLETE, &set_hashed(&first)), 1_000, &mut out, &all());
            let second = set_hashed(&ticks(32, [0xAB; 32]));
            let (x, y) = second.split_at(second.len() / 2);
            asm.push(&data_shred(a, 1, 0, x), 1_100, &mut out, &all());
            assert!(rx.try_recv().is_err(), "nothing before the last shred");
            asm.push(&data_shred(a, 2, LAST_IN_SLOT, y), 1_200, &mut out, &all());
            let b = 300_000_022u64;
            asm.push(&data_shred(b, 0, DATA_COMPLETE, &set_hashed(&ticks(64, [3; 32]))), 2_000, &mut out, &all());
            asm.push(&data_shred(b, 1, LAST_IN_SLOT, &set_hashed(&ticks(64, [0xCD; 32]))), 2_100, &mut out, &all());
            let c = 300_000_023u64;
            asm.push(&data_shred(c, 3, LAST_IN_SLOT, &set_hashed(&ticks(64, [0xEE; 32]))), 3_000, &mut out, &all());
            let dd = 300_000_024u64;
            asm.push(&data_shred(dd, 0, LAST_IN_SLOT, &[0xff; 40]), 4_000, &mut out, &all());
            asm.gc(30_000_000_000);
        });
        let got: Vec<(u64, [u8; 32], u16)> = rx.try_iter().filter_map(|n| match n {
            crate::chainfetch::Note::EntryHash { slot, hash, feed, .. } => Some((slot, hash, feed)), _ => None }).collect();
        assert_eq!(got, vec![(300_000_020, [0xAB; 32], 4), (300_000_022, [0xCD; 32], 4)]);
        assert_eq!(out.len(), 1, "slot A's transaction");
        rec.close();
        let lines = crate::rec::read_text(&d, "slots-feed").unwrap();
        assert_eq!(lines.len(), 4, "{lines:?}");
        assert!(lines[0].ends_with(" 1") && lines[1].starts_with("4 300000022 128 128 0 "), "A complete; B walked whole with 128 ticks: {lines:?}");
        let _ = std::fs::remove_dir_all(&d);
    }

    /// review F12: poh.log v2 from a raw feed, through the recorder: each transaction's position on the leader's clock
    /// and its entry's index in the slot (`sig8 slot ms feed entry_idx`), one queue slot per data set, counted as lines
    #[test]
    fn poh_positions_are_recorded_with_their_entry_index() {
        let d = std::env::temp_dir().join(format!("arbx-shred-poh-{}-{}", std::process::id(), crate::feeds::clock::now_ns()));
        let rec = crate::rec::start(crate::rec::Opts { dir: d.clone(), run: "t".into(), producer: "p".into(), cfg: Default::default(), feeds: vec![], monitor: false,
            echo: Some(Box::new(std::io::sink())) }).unwrap();
        // the slot's first data set: a tick of 100 hashes, then an entry of two transactions 50 hashes later (9.375 ms)
        let mut buf = Vec::new();
        buf.extend(2u64.to_le_bytes());
        buf.extend(100u64.to_le_bytes()); buf.extend([0u8; 32]); buf.extend(0u64.to_le_bytes());
        buf.extend(50u64.to_le_bytes()); buf.extend([0u8; 32]); buf.extend(2u64.to_le_bytes()); buf.extend(tx(0x31)); buf.extend(tx(0x32));
        let mut asm = Assembler::new();
        asm.rec = rec.clone();
        asm.feed = 3;
        let mut out = Vec::new();
        asm.push(&data_shred(300_000_002, 0, DATA_COMPLETE, &buf), 10, &mut out, &all());
        assert_eq!(out.len(), 2);
        rec.close();
        assert_eq!(crate::rec::read_text(&d, "poh").unwrap(), vec!["3131313131313131 300000002 9.375 3 1", "3232323232323232 300000002 9.375 3 1"]);
        let m: serde_json::Value = serde_json::from_str(&std::fs::read_to_string(d.join("manifest.json")).unwrap()).unwrap();
        assert_eq!(m["streams"].as_array().unwrap().iter().find(|s| s["name"] == "poh").unwrap()["records_total"].as_u64(), Some(2));
        let _ = std::fs::remove_dir_all(&d);
    }
}

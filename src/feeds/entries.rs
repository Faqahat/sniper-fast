//! Parse a serialized `Vec<solana_entry::Entry>` (bincode) and walk its transactions, returning each transaction's
//! first signature, whether it is a vote, and the byte range it occupies (so the caller can tell which shred
//! completed it). Handles legacy, v0 and v1 (SIMD-0385) transactions without any Solana crates.
//!
//! bincode layout: u64 entry count; per entry: u64 num_hashes, 32-byte hash, u64 transaction count, transactions.
//! legacy / v0 wire: short_vec signature count, signatures (64 each), message (v0 starts with 0x80).
//! v1 wire: 0x81, header (3), config mask (u32), lifetime (32), instruction count (u8), address count (u8), addresses
//!          (32 each), config values (4 bytes per set mask bit), per-instruction header {program u8, accounts u8,
//!          data len u16}, per-instruction {account indexes, data}, then the signatures (64 each) at the end.

pub const VOTE_PROGRAM: [u8; 32] = [
    7, 97, 72, 29, 53, 116, 116, 187, 124, 77, 118, 36, 235, 211, 189, 179, 216, 53, 94, 115, 209, 16, 67, 252, 13,
    163, 83, 128, 0, 0, 0, 0,
];

pub struct TxRef {
    /// byte offset where this transaction starts in the buffer
    pub start: usize,
    pub sig: [u8; 64],
    pub is_vote: bool,
    /// byte offset (exclusive) where this transaction ends in the buffer
    pub end: usize,
    /// index of its entry in the buffer (see `parse_entries_poh`)
    pub entry: u32,
}

struct Cur<'a> { b: &'a [u8], p: usize }

impl<'a> Cur<'a> {
    #[inline] fn need(&self, n: usize) -> Option<()> { if self.p + n <= self.b.len() { Some(()) } else { None } }
    #[inline] fn u8(&mut self) -> Option<u8> { self.need(1)?; let v = self.b[self.p]; self.p += 1; Some(v) }
    #[inline] fn u16(&mut self) -> Option<u16> { self.need(2)?; let v = u16::from_le_bytes([self.b[self.p], self.b[self.p + 1]]); self.p += 2; Some(v) }
    #[inline] fn u32(&mut self) -> Option<u32> { self.need(4)?; let mut a = [0u8; 4]; a.copy_from_slice(&self.b[self.p..self.p + 4]); self.p += 4; Some(u32::from_le_bytes(a)) }
    #[inline] fn u64(&mut self) -> Option<u64> { self.need(8)?; let mut a = [0u8; 8]; a.copy_from_slice(&self.b[self.p..self.p + 8]); self.p += 8; Some(u64::from_le_bytes(a)) }
    #[inline] fn skip(&mut self, n: usize) -> Option<()> { self.need(n)?; self.p += n; Some(()) }
    #[inline] fn bytes(&mut self, n: usize) -> Option<&'a [u8]> { self.need(n)?; let s = &self.b[self.p..self.p + n]; self.p += n; Some(s) }
    /// Solana compact-u16 ("short_vec" length)
    #[inline] fn short_vec(&mut self) -> Option<usize> {
        let mut v: usize = 0;
        for i in 0..3 {
            let byte = self.u8()? as usize;
            v |= (byte & 0x7f) << (7 * i);
            if byte & 0x80 == 0 { return Some(v); }
        }
        None
    }
}

/// Parse one legacy/v0 message; returns whether any top-level instruction invokes the vote program.
fn legacy_v0_message(c: &mut Cur) -> Option<bool> {
    let first = *c.b.get(c.p)?;
    let versioned = first & 0x80 != 0;
    if versioned {
        let version = first & 0x7f;
        if version != 0 { return None; }
        c.skip(1)?;
    }
    c.skip(3)?; // header
    let nkeys = c.short_vec()?;
    if nkeys > 256 { return None; }
    let keys = c.bytes(nkeys * 32)?;
    c.skip(32)?; // recent blockhash
    let nix = c.short_vec()?;
    if nix > 1024 { return None; }
    let mut vote = false;
    for _ in 0..nix {
        let prog = c.u8()? as usize;
        if prog < nkeys && keys[prog * 32..prog * 32 + 32] == VOTE_PROGRAM { vote = true; }
        let na = c.short_vec()?; c.skip(na)?;
        let nd = c.short_vec()?; c.skip(nd)?;
    }
    if versioned {
        let nlut = c.short_vec()?;
        if nlut > 256 { return None; }
        for _ in 0..nlut {
            c.skip(32)?;
            let w = c.short_vec()?; c.skip(w)?;
            let r = c.short_vec()?; c.skip(r)?;
        }
    }
    Some(vote)
}

/// Parse one transaction at the cursor.
fn transaction(c: &mut Cur) -> Option<TxRef> {
    let start = c.p;
    let first = *c.b.get(c.p)?;
    if first == 0x81 {
        // v1: signatures at the end
        c.skip(1)?;
        let nsig = c.u8()? as usize;
        c.skip(2)?;
        let mask = c.u32()?;
        c.skip(32)?; // lifetime
        let nix = c.u8()? as usize;
        let naddr = c.u8()? as usize;
        let keys = c.bytes(naddr * 32)?;
        c.skip(4 * mask.count_ones() as usize)?;
        let mut lens = Vec::with_capacity(nix);
        let mut vote = false;
        for _ in 0..nix {
            let prog = c.u8()? as usize;
            let na = c.u8()? as usize;
            let nd = c.u16()? as usize;
            if prog < naddr && keys[prog * 32..prog * 32 + 32] == VOTE_PROGRAM { vote = true; }
            lens.push(na + nd);
        }
        for l in lens { c.skip(l)?; }
        if nsig == 0 { return None; }
        let sigs = c.bytes(nsig * 64)?;
        let mut sig = [0u8; 64];
        sig.copy_from_slice(&sigs[0..64]);
        return Some(TxRef { start, sig, is_vote: vote, end: c.p, entry: 0 });
    }
    let nsig = c.short_vec()?;
    if nsig == 0 || nsig > 64 { return None; }
    let sigs = c.bytes(nsig * 64)?;
    let mut sig = [0u8; 64];
    sig.copy_from_slice(&sigs[0..64]);
    let vote = legacy_v0_message(c)?;
    Some(TxRef { start, sig, is_vote: vote, end: c.p, entry: 0 })
}

/// Walk a serialized Vec<Entry>. Returns None if the bytes don't parse as one (wrong boundaries, garbage).
pub fn parse_entries(buf: &[u8]) -> Option<Vec<TxRef>> { parse_entries_poh(buf).map(|x| x.0) }

/// The same walk, plus each entry's PoH record: (num_hashes, transaction count). An entry with no transactions is a
/// tick; num_hashes counts the PoH hashes since the previous entry, so a running sum is the leader's clock in the slot.
pub fn parse_entries_poh(buf: &[u8]) -> Option<(Vec<TxRef>, Vec<(u64, u64)>)> {
    let mut c = Cur { b: buf, p: 0 };
    let n = c.u64()?;
    if n > 1_000_000 { return None; }
    let mut out = Vec::new();
    let mut ents = Vec::with_capacity(n as usize);
    for e in 0..n {
        let hashes = c.u64()?;
        c.skip(32)?; // hash
        let ntx = c.u64()?;
        if ntx > 100_000 { return None; }
        for _ in 0..ntx { let mut t = transaction(&mut c)?; t.entry = e as u32; out.push(t); }
        ents.push((hashes, ntx));
    }
    Some((out, ents))
}

/// Where a transaction sits on its leader's PoH clock: PoH hashes since the slot began (through its entry), ticks
/// completed before its entry, and the slot's hashes per tick. One tick is 6.25 ms of a 400 ms slot (64 ticks).
#[derive(Clone, Copy, Debug, PartialEq, serde::Serialize)]
pub struct Poh { pub slot: u64, pub hashes: u64, pub ticks: u32, pub hpt: u64 }

impl Poh {
    /// milliseconds since the slot began, on the leader's clock (None until a tick has fixed hashes per tick)
    pub fn ms(&self) -> Option<f64> { (self.hpt > 0).then(|| self.hashes as f64 / self.hpt as f64 * 6.25) }
    /// how far after `earlier` this one ran on the leaders' clocks (across slots: 400 ms a slot)
    pub fn ms_after(&self, earlier: &Poh) -> Option<f64> { Some((self.slot as f64 - earlier.slot as f64) * 400.0 + self.ms()? - earlier.ms()?) }
}

/// Running PoH count per slot for one entries feed. Entries of a slot arrive in order from its first; the first slot
/// after (re)connecting started before we joined, so it is not counted (`valid` false).
#[derive(Default)]
pub struct PohClock { slot: u64, hashes: u64, ticks: u32, last_tick: u64, hpt: u64, valid: bool, pub complete: u64, pub partial: u64,
    n_entries: u32, n_txs: u64, t_first: u64, t_last: u64 }

/// one finished slot as an entries feed delivered it (slots.log)
pub struct SlotRec { pub slot: u64, pub ticks: u32, pub entries: u32, pub txs: u64, pub t_first: u64, pub t_last: u64, pub valid: bool }

impl PohClock {
    /// `entries`, plus arrival bookkeeping: returns each entry's position, the previous slot's record once a newer slot
    /// starts, and the index in its slot of the message's first entry when the slot is followed from its start (poh.log
    /// v2 `entry_idx`: the entries of a slot arrive in order, so the count so far is the index)
    pub fn entries_at(&mut self, slot: u64, ents: &[(u64, u64)], t: u64) -> (Vec<Option<Poh>>, Option<SlotRec>, Option<u32>) {
        let done = (slot > self.slot && self.slot != 0).then(|| SlotRec { slot: self.slot, ticks: self.ticks, entries: self.n_entries, txs: self.n_txs,
            t_first: self.t_first, t_last: self.t_last, valid: self.valid });
        let out = self.entries(slot, ents);
        let mut first = None;
        if slot == self.slot {
            first = self.valid.then_some(self.n_entries);
            if self.t_first == 0 { self.t_first = t; }
            self.t_last = t;
            self.n_entries += ents.len() as u32;
            self.n_txs += ents.iter().map(|e| e.1).sum::<u64>();
        }
        (out, done, first)
    }

    /// account one message's entries of `slot`; returns each entry's position (None for a slot we joined midway)
    pub fn entries(&mut self, slot: u64, ents: &[(u64, u64)]) -> Vec<Option<Poh>> {
        if slot != self.slot {
            if slot < self.slot { return vec![None; ents.len()]; }   // a late message of an older slot
            if self.slot != 0 { if self.ticks == 64 { self.complete += 1; } else if self.valid { self.partial += 1; } }
            // every slot after the one we joined midway is seen from its first entry (skipped leader slots are fine)
            let valid = self.slot != 0;
            *self = PohClock { slot, hpt: self.hpt, valid, complete: self.complete, partial: self.partial, ..Default::default() };
        }
        ents.iter().map(|&(h, ntx)| {
            self.hashes += h;
            let p = self.valid.then_some(Poh { slot, hashes: self.hashes, ticks: self.ticks, hpt: self.hpt });
            if ntx == 0 { self.ticks += 1; self.hpt = self.hashes - self.last_tick; self.last_tick = self.hashes; }
            p
        }).collect()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn vote_program_bytes() {
        let v = bs58::decode("Vote111111111111111111111111111111111111111").into_vec().unwrap();
        assert_eq!(v.as_slice(), &VOTE_PROGRAM);
    }

    fn legacy_tx(sig_byte: u8, prog: [u8; 32]) -> Vec<u8> {
        let mut t = vec![1u8]; // one signature
        t.extend([sig_byte; 64]);
        t.extend([1, 0, 1]); // header
        t.push(2); // two keys
        t.extend([9u8; 32]); t.extend(prog);
        t.extend([7u8; 32]); // blockhash
        t.push(1); // one instruction
        t.push(1); // program index 1
        t.push(1); t.push(0); // one account: index 0
        t.push(3); t.extend([1, 2, 3]); // data
        t
    }

    fn v1_tx(sig_byte: u8) -> Vec<u8> {
        let mut t = vec![0x81, 1, 0, 1];
        t.extend((0b11u32 | 1 << 2).to_le_bytes()); // priority fee (2 words) + CU limit (1 word)
        t.extend([5u8; 32]); // lifetime
        t.push(1); t.push(2); // one instruction, two addresses
        t.extend([9u8; 32]); t.extend([8u8; 32]);
        t.extend([0u8; 12]); // config values: 3 words
        t.extend([1, 1, 2, 0]); // ix header: program 1, 1 account, 2 data bytes
        t.extend([0, 0xAA, 0xBB]); // account index + data
        t.extend([sig_byte; 64]); // signature at the end
        t
    }

    fn entries(txs: &[Vec<u8>]) -> Vec<u8> {
        let mut b = Vec::new();
        b.extend(1u64.to_le_bytes()); // one entry
        b.extend(0u64.to_le_bytes()); b.extend([0u8; 32]);
        b.extend((txs.len() as u64).to_le_bytes());
        for t in txs { b.extend(t); }
        b
    }

    #[test]
    fn parses_legacy_v1_and_votes() {
        let a = legacy_tx(0x11, [3u8; 32]);
        let v = legacy_tx(0x22, VOTE_PROGRAM);
        let w = v1_tx(0x33);
        let buf = entries(&[a.clone(), v, w]);
        let out = parse_entries(&buf).expect("parses");
        assert_eq!(out.len(), 3);
        assert_eq!(out[0].sig[0], 0x11); assert!(!out[0].is_vote);
        assert_eq!(out[1].sig[0], 0x22); assert!(out[1].is_vote);
        assert_eq!(out[2].sig[0], 0x33); assert!(!out[2].is_vote);
        assert_eq!(out[2].end, buf.len());
        assert_eq!(out[0].end, 8 + 8 + 32 + 8 + a.len());
    }

    #[test]
    fn poh_clock_times_transactions_on_the_leaders_ticks() {
        let mut c = PohClock::default();
        // slot 10 joined midway: no positions
        assert!(c.entries(10, &[(100, 1), (100, 0)]).iter().all(|p| p.is_none()));
        // slot 11 from its start: tick (100 hashes), tx entry after 50 more hashes, tick, tx entry after 25
        let p = c.entries(11, &[(100, 0), (50, 2), (50, 0), (25, 1)]);
        assert_eq!(p[1].unwrap().hashes, 150);
        assert_eq!(p[1].unwrap().ticks, 1);
        assert_eq!(p[1].unwrap().ms(), Some(9.375));   // 1.5 ticks of 6.25 ms
        assert_eq!(p[3].unwrap().ms(), Some(14.0625));
        assert_eq!(p[3].unwrap().ms_after(&p[1].unwrap()), Some(4.6875));
    }

    /// poh.log v2 `entry_idx` for an entries feed: the index in its slot of each message's first entry, known only for a
    /// slot followed from its start (the first slot after joining is not)
    #[test]
    fn entry_indexes_of_a_slot_followed_from_its_start() {
        let mut c = PohClock::default();
        assert_eq!(c.entries_at(10, &[(100, 1), (100, 0)], 1).2, None, "joined midway");
        assert_eq!(c.entries_at(11, &[(100, 0), (50, 2)], 2).2, Some(0));
        assert_eq!(c.entries_at(11, &[(50, 0), (25, 1), (25, 1)], 3).2, Some(2));
        let (p, done, first) = c.entries_at(12, &[(100, 0)], 4);
        assert_eq!((first, done.map(|d| (d.slot, d.entries, d.ticks, d.valid))), (Some(0), Some((11, 5, 2, true))));
        assert_eq!(p.len(), 1);
        assert_eq!(c.entries_at(11, &[(1, 1)], 5).2, None, "a late message of an older slot");
    }

    #[test]
    fn rejects_truncated() {
        let mut buf = entries(&[legacy_tx(1, [3u8; 32])]);
        buf.truncate(buf.len() - 5);
        assert!(parse_entries(&buf).is_none());
    }
}

//! Full decode of one transaction into its signature, header, account keys, lookup-table references and
//! instructions. Two sources produce the same `Tx`:
//!   - wire bytes (raw shreds, ShredStream entries): `parse_wire` handles legacy, v0 (0x80) and v1 (0x81, SIMD-0385)
//!   - Yellowstone protobuf (`solana.storage.ConfirmedBlock.Transaction`), built in `feeds::grpc`
//! Program ids are always static keys (a program can't be loaded from a lookup table), so a cheap static-key check
//! (`touches`) can drop uninteresting transactions before anything is resolved.
use std::sync::Arc;

pub type Pk = [u8; 32];

#[derive(Clone, Debug, Default)]
pub struct Ix {
    /// index into the full account list
    pub program: u8,
    pub accounts: Vec<u8>,
    pub data: Vec<u8>,
}

#[derive(Clone, Debug)]
pub struct Lookup {
    pub table: Pk,
    pub writable: Vec<u8>,
    pub readonly: Vec<u8>,
}

#[derive(Clone, Debug)]
pub struct Tx {
    pub sig: [u8; 64],
    pub num_signers: u8,
    pub num_ro_signed: u8,
    pub num_ro_unsigned: u8,
    /// static account keys, in message order (fee payer first)
    pub keys: Vec<Pk>,
    pub lookups: Vec<Lookup>,
    /// addresses already resolved by the feed (Yellowstone deshred / processed meta): writable then readonly
    pub loaded: Option<(Vec<Pk>, Vec<Pk>)>,
    pub ixs: Vec<Ix>,
    pub is_vote: bool,
    /// v1 inline priority fee (lamports) or the ComputeBudget price, filled by `fee_info`
    pub cu_price_micro: Option<u64>,
    pub cu_limit: Option<u32>,
    /// a v1 (SIMD-0385) transaction: `cu_price_micro` then holds its total priority fee in lamports
    pub v1: bool,
}

impl Default for Tx {
    fn default() -> Self {
        Tx { sig: [0u8; 64], num_signers: 0, num_ro_signed: 0, num_ro_unsigned: 0, keys: Vec::new(), lookups: Vec::new(),
            loaded: None, ixs: Vec::new(), is_vote: false, cu_price_micro: None, cu_limit: None, v1: false }
    }
}

impl Tx {
    pub fn fee_payer(&self) -> Option<&Pk> { self.keys.first() }
    /// true when any static key (and so any invoked program) is in `set`
    pub fn touches(&self, set: &std::collections::HashSet<Pk>) -> bool { self.keys.iter().any(|k| set.contains(k)) }

    /// Full account list in Solana order: static keys, then every lookup's writable addresses (lookup order), then
    /// every lookup's readonly addresses. `table` returns a lookup table's address list (from the ALT cache).
    pub fn resolve(&self, table: impl Fn(&Pk) -> Option<Arc<Vec<Pk>>>) -> Option<Vec<Pk>> {
        let mut out = self.keys.clone();
        if self.lookups.is_empty() { return Some(out); }
        if let Some((w, r)) = &self.loaded {
            out.extend_from_slice(w);
            out.extend_from_slice(r);
            return Some(out);
        }
        let tables: Vec<Arc<Vec<Pk>>> = self.lookups.iter().map(|l| table(&l.table)).collect::<Option<_>>()?;
        for (l, t) in self.lookups.iter().zip(&tables) {
            for &i in &l.writable { out.push(*t.get(i as usize)?); }
        }
        for (l, t) in self.lookups.iter().zip(&tables) {
            for &i in &l.readonly { out.push(*t.get(i as usize)?); }
        }
        Some(out)
    }

    /// Whether account `i` of the full list is writable (Solana's rules for static keys; loaded writable addresses
    /// come right after the static keys).
    pub fn is_writable(&self, i: usize) -> bool {
        let n = self.keys.len();
        let s = self.num_signers as usize;
        if i < s { return i < s - self.num_ro_signed as usize; }
        if i < n { return i < n - self.num_ro_unsigned as usize; }
        let w: usize = match &self.loaded {
            Some((w, _)) => w.len(),
            None => self.lookups.iter().map(|l| l.writable.len()).sum(),
        };
        i < n + w
    }

    pub fn sig_b58(&self) -> String { bs58::encode(self.sig).into_string() }

    /// the compute-unit price this transaction bids, micro-lamports per CU (a v1 total spread over its CU limit)
    pub fn cu_price(&self) -> Option<u64> {
        if !self.v1 { return self.cu_price_micro; }
        let limit = self.cu_limit.filter(|l| *l > 0)? as u128;
        Some((self.cu_price_micro? as u128 * 1_000_000 / limit) as u64)
    }
}

pub const COMPUTE_BUDGET: Pk = [
    3, 6, 70, 111, 229, 33, 23, 50, 255, 236, 173, 186, 114, 195, 155, 231, 188, 140, 229, 187, 197, 247, 18, 107,
    44, 67, 155, 58, 64, 0, 0, 0,
];

struct Cur<'a> { b: &'a [u8], p: usize }

impl<'a> Cur<'a> {
    #[inline] fn need(&self, n: usize) -> Option<()> { if self.p + n <= self.b.len() { Some(()) } else { None } }
    #[inline] fn u8(&mut self) -> Option<u8> { self.need(1)?; let v = self.b[self.p]; self.p += 1; Some(v) }
    #[inline] fn u16(&mut self) -> Option<u16> { self.need(2)?; let v = u16::from_le_bytes([self.b[self.p], self.b[self.p + 1]]); self.p += 2; Some(v) }
    #[inline] fn u32(&mut self) -> Option<u32> { self.need(4)?; let mut a = [0u8; 4]; a.copy_from_slice(&self.b[self.p..self.p + 4]); self.p += 4; Some(u32::from_le_bytes(a)) }
    #[inline] fn bytes(&mut self, n: usize) -> Option<&'a [u8]> { self.need(n)?; let s = &self.b[self.p..self.p + n]; self.p += n; Some(s) }
    #[inline] fn pk(&mut self) -> Option<Pk> { let s = self.bytes(32)?; let mut k = [0u8; 32]; k.copy_from_slice(s); Some(k) }
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

/// Result of a zero-allocation pass over a wire transaction
pub struct Scan { pub len: usize, pub is_vote: bool, pub hit: bool }

/// Walk one wire transaction in place: its length, whether it votes, and whether any static key (`key`) or lookup
/// table (`table`) is interesting. Nothing is allocated; this runs on every transaction of every raw feed, and only a
/// hit is fully decoded with `parse_wire`.
pub fn scan(b: &[u8], key: &dyn Fn(&Pk) -> bool, table: &dyn Fn(&Pk) -> bool) -> Option<Scan> {
    let mut c = Cur { b, p: 0 };
    let as_pk = |s: &[u8]| -> Pk { s.try_into().unwrap() };
    let vote = &crate::feeds::entries::VOTE_PROGRAM;
    if *b.first()? == 0x81 {
        c.p += 1;
        let nsig = c.u8()? as usize;
        c.bytes(2)?;
        let mask = c.u32()?;
        c.bytes(32)?;
        let nix = c.u8()? as usize;
        let naddr = c.u8()? as usize;
        let keys = c.bytes(naddr * 32)?;
        let mut hit = keys.chunks_exact(32).any(|k| key(&as_pk(k)));
        c.bytes(4 * mask.count_ones() as usize)?;
        let mut is_vote = false;
        let mut payload = 0usize;
        for _ in 0..nix {
            let prog = c.u8()? as usize;
            let na = c.u8()? as usize;
            let nd = c.u16()? as usize;
            if prog < naddr && &keys[prog * 32..prog * 32 + 32] == vote { is_vote = true; }
            payload += na + nd;
        }
        c.bytes(payload)?;
        if nsig == 0 { return None; }
        c.bytes(nsig * 64)?;
        if is_vote { hit = false; }
        return Some(Scan { len: c.p, is_vote, hit });
    }
    let nsig = c.short_vec()?;
    if nsig == 0 || nsig > 64 { return None; }
    c.bytes(nsig * 64)?;
    let first = *c.b.get(c.p)?;
    let versioned = first & 0x80 != 0;
    if versioned { if first & 0x7f != 0 { return None; } c.p += 1; }
    c.bytes(3)?;
    let nkeys = c.short_vec()?;
    if nkeys > 256 { return None; }
    let keys = c.bytes(nkeys * 32)?;
    c.bytes(32)?;
    let nix = c.short_vec()?;
    if nix > 1024 { return None; }
    let mut is_vote = false;
    for _ in 0..nix {
        let prog = c.u8()? as usize;
        if prog < nkeys && &keys[prog * 32..prog * 32 + 32] == vote { is_vote = true; }
        let na = c.short_vec()?; c.bytes(na)?;
        let nd = c.short_vec()?; c.bytes(nd)?;
    }
    let mut hit = !is_vote && keys.chunks_exact(32).any(|k| key(&as_pk(k)));
    if versioned {
        let nlut = c.short_vec()?;
        if nlut > 256 { return None; }
        for _ in 0..nlut {
            let t = c.bytes(32)?;
            if !hit && !is_vote && table(&as_pk(t)) { hit = true; }
            let w = c.short_vec()?; c.bytes(w)?;
            let r = c.short_vec()?; c.bytes(r)?;
        }
    }
    Some(Scan { len: c.p, is_vote, hit })
}

/// Decode one wire transaction. Returns the transaction and the number of bytes it used.
pub fn parse_wire(b: &[u8]) -> Option<(Tx, usize)> {
    let mut c = Cur { b, p: 0 };
    let tx = if *b.first()? == 0x81 { v1(&mut c)? } else { legacy_v0(&mut c)? };
    Some((tx, c.p))
}

fn legacy_v0(c: &mut Cur) -> Option<Tx> {
    let nsig = c.short_vec()?;
    if nsig == 0 || nsig > 64 { return None; }
    let sigs = c.bytes(nsig * 64)?;
    let mut tx = Tx::default();
    tx.sig.copy_from_slice(&sigs[..64]);
    let first = *c.b.get(c.p)?;
    let versioned = first & 0x80 != 0;
    if versioned {
        if first & 0x7f != 0 { return None; }
        c.p += 1;
    }
    tx.num_signers = c.u8()?;
    tx.num_ro_signed = c.u8()?;
    tx.num_ro_unsigned = c.u8()?;
    let nkeys = c.short_vec()?;
    if nkeys > 256 { return None; }
    tx.keys.reserve(nkeys);
    for _ in 0..nkeys { tx.keys.push(c.pk()?); }
    c.bytes(32)?; // recent blockhash
    let nix = c.short_vec()?;
    if nix > 1024 { return None; }
    for _ in 0..nix {
        let program = c.u8()?;
        let na = c.short_vec()?;
        let accounts = c.bytes(na)?.to_vec();
        let nd = c.short_vec()?;
        let data = c.bytes(nd)?.to_vec();
        tx.ixs.push(Ix { program, accounts, data });
    }
    if versioned {
        let nlut = c.short_vec()?;
        if nlut > 256 { return None; }
        for _ in 0..nlut {
            let table = c.pk()?;
            let w = c.short_vec()?; let writable = c.bytes(w)?.to_vec();
            let r = c.short_vec()?; let readonly = c.bytes(r)?.to_vec();
            tx.lookups.push(Lookup { table, writable, readonly });
        }
    }
    finish(tx)
}

/// v1 (SIMD-0385): 0x81, header(3), config mask u32, lifetime(32), num_ix u8, num_addr u8, addresses, config values
/// (4 bytes per set mask bit), per-ix header {program u8, num_accounts u8, data_len u16}, per-ix payloads, signatures.
fn v1(c: &mut Cur) -> Option<Tx> {
    c.p += 1;
    let mut tx = Tx::default();
    tx.v1 = true;
    tx.num_signers = c.u8()?;
    tx.num_ro_signed = c.u8()?;
    tx.num_ro_unsigned = c.u8()?;
    let mask = c.u32()?;
    c.bytes(32)?; // lifetime
    let nix = c.u8()? as usize;
    let naddr = c.u8()? as usize;
    for _ in 0..naddr { tx.keys.push(c.pk()?); }
    // config values in mask-bit order: bits 0-1 priority fee (u64 lamports, 2 words), bit 2 CU limit,
    // bit 3 loaded-accounts data size, bit 4 heap size
    let words = c.bytes(4 * mask.count_ones() as usize)?;
    let mut w = words.chunks_exact(4).map(|x| u32::from_le_bytes([x[0], x[1], x[2], x[3]]));
    if mask & 0b11 == 0b11 {
        let lo = w.next()? as u64; let hi = w.next()? as u64;
        tx.cu_price_micro = Some(lo | hi << 32); // total priority fee in lamports for v1, not a CU price
    }
    if mask & 0b100 != 0 { tx.cu_limit = w.next(); }
    let mut hdr = Vec::with_capacity(nix);
    for _ in 0..nix { hdr.push((c.u8()?, c.u8()? as usize, c.u16()? as usize)); }
    for (program, na, nd) in hdr {
        let accounts = c.bytes(na)?.to_vec();
        let data = c.bytes(nd)?.to_vec();
        tx.ixs.push(Ix { program, accounts, data });
    }
    if tx.num_signers == 0 { return None; }
    let sigs = c.bytes(tx.num_signers as usize * 64)?;
    tx.sig.copy_from_slice(&sigs[..64]);
    Some(tx).and_then(finish)
}

/// vote flag and ComputeBudget price/limit (legacy/v0)
pub fn finish(mut tx: Tx) -> Option<Tx> {
    for ix in &tx.ixs {
        let Some(p) = tx.keys.get(ix.program as usize) else { continue };
        if *p == crate::feeds::entries::VOTE_PROGRAM { tx.is_vote = true; }
        if *p == COMPUTE_BUDGET && !ix.data.is_empty() {
            match ix.data[0] {
                2 if ix.data.len() >= 5 => tx.cu_limit = Some(u32::from_le_bytes(ix.data[1..5].try_into().ok()?)),
                3 if ix.data.len() >= 9 => tx.cu_price_micro = Some(u64::from_le_bytes(ix.data[1..9].try_into().ok()?)),
                _ => {}
            }
        }
    }
    Some(tx)
}

/// Parse an ALT account's data into its address list (56-byte header, then 32-byte addresses).
pub fn parse_alt(data: &[u8]) -> Option<Vec<Pk>> {
    if data.len() < 56 || (data.len() - 56) % 32 != 0 { return None; }
    Some(data[56..].chunks_exact(32).map(|c| { let mut k = [0u8; 32]; k.copy_from_slice(c); k }).collect())
}

pub fn pk(s: &str) -> Pk {
    let v = bs58::decode(s).into_vec().expect("valid base58 pubkey");
    let mut k = [0u8; 32];
    k.copy_from_slice(&v);
    k
}

pub fn b58(k: &Pk) -> String { bs58::encode(k).into_string() }

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compute_budget_bytes() { assert_eq!(pk("ComputeBudget111111111111111111111111111111"), COMPUTE_BUDGET); }

    fn v0_tx() -> Vec<u8> {
        let mut t = vec![1u8];
        t.extend([0x11; 64]);
        t.push(0x80);
        t.extend([1, 0, 1]);
        t.push(3); t.extend([9u8; 32]); t.extend([8u8; 32]); t.extend(COMPUTE_BUDGET);
        t.extend([7u8; 32]);
        t.push(2);
        t.extend([2, 0, 9, 3]); t.extend(1000u64.to_le_bytes()); // SetComputeUnitPrice 1000 (tag + u64)
        t.push(1); t.push(2); t.extend([0, 3]); t.push(2); t.extend([0xAA, 0xBB]); // program key 1, accounts [0, 3]
        t.push(1); t.extend([5u8; 32]); t.push(1); t.push(4); t.push(1); t.push(6); // one lookup: w[4], r[6]
        t
    }

    #[test]
    fn scan_agrees_with_parse() {
        let b = v0_tx();
        let (_, used) = parse_wire(&b).unwrap();
        let sc = scan(&b, &|k| *k == [8u8; 32], &|_| false).unwrap();
        assert_eq!(sc.len, used);
        assert!(sc.hit && !sc.is_vote);
        let sc = scan(&b, &|_| false, &|t| *t == [5u8; 32]).unwrap();
        assert!(sc.hit, "lookup table hit");
        assert!(!scan(&b, &|_| false, &|_| false).unwrap().hit);
        assert!(scan(&b[..b.len() - 1], &|_| true, &|_| true).is_none(), "truncated");
    }

    #[test]
    fn parses_v0_with_lookup() {
        let b = v0_tx();
        let (tx, used) = parse_wire(&b).unwrap();
        assert_eq!(used, b.len());
        assert_eq!(tx.sig[0], 0x11);
        assert_eq!(tx.keys.len(), 3);
        assert_eq!(tx.cu_price_micro, Some(1000));
        assert_eq!(tx.ixs[1].accounts, vec![0, 3]);
        let table: Vec<Pk> = (0..8u8).map(|i| [i; 32]).collect();
        let t = Arc::new(table);
        let full = tx.resolve(|_| Some(t.clone())).unwrap();
        assert_eq!(full.len(), 5);
        assert_eq!(full[3], [4u8; 32]);
        assert_eq!(full[4], [6u8; 32]);
        assert!(tx.is_writable(0));
        assert!(tx.is_writable(3));
        assert!(!tx.is_writable(4));
        assert!(!tx.is_writable(2)); // last static key is readonly (num_ro_unsigned = 1)
    }
}

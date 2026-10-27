//! Minimal, allocation-light parser for bincode-serialized `VersionedTransaction` bytes (the Shreder
//! `binary_transaction` payload): signatures, legacy / v0 message, static account keys, top-level
//! instructions, address-table-lookup count. Plus a summary of top-level pump.fun / pump AMM instructions.
//!
//! Wire format (same as the Solana wire format, which is what bincode produces for VersionedTransaction):
//!   compact-u16 n_sigs, n_sigs * 64 bytes
//!   message: [0x80 | version] (v0 only) , header(3) , compact-u16 n_keys , n_keys * 32 , blockhash(32) ,
//!            compact-u16 n_ix , per ix: u8 program_idx , compact-u16 n_acc , n_acc * u8 , compact-u16 n_data , data
//!            v0 only: compact-u16 n_lookups , per lookup: key(32) , compact-u16 n_w , n_w * u8 , compact-u16 n_r , n_r * u8

pub const PUMP_PROGRAM: &str = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P";
pub const PUMP_AMM_PROGRAM: &str = "pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA";

#[derive(Debug, Clone)]
pub struct IxView<'a> {
    pub program_idx: u8,
    pub accounts: &'a [u8],
    pub data: &'a [u8],
}

#[derive(Debug, Clone)]
pub struct TxView<'a> {
    pub signatures: Vec<&'a [u8]>,
    /// -1 = legacy, 0 = v0
    pub version: i8,
    pub header: [u8; 3],
    pub keys: Vec<&'a [u8]>,
    pub blockhash: &'a [u8],
    pub instructions: Vec<IxView<'a>>,
    pub n_lookups: usize,
    /// bytes consumed by the parse (== input length for a well-formed tx)
    pub consumed: usize,
}

#[inline]
fn compact_u16(b: &[u8], off: &mut usize) -> Option<usize> {
    let mut val: usize = 0;
    for i in 0..3 {
        let byte = *b.get(*off)? as usize;
        *off += 1;
        val |= (byte & 0x7f) << (7 * i);
        if byte & 0x80 == 0 {
            return Some(val);
        }
    }
    None
}

#[inline]
fn take<'a>(b: &'a [u8], off: &mut usize, n: usize) -> Option<&'a [u8]> {
    let end = off.checked_add(n)?;
    let s = b.get(*off..end)?;
    *off = end;
    Some(s)
}

/// Parse a serialized VersionedTransaction. None on malformed / unsupported (version > 0) input.
pub fn parse_tx(b: &[u8]) -> Option<TxView<'_>> {
    let mut off = 0usize;
    let n_sigs = compact_u16(b, &mut off)?;
    if n_sigs > 127 {
        return None;
    }
    let mut signatures = Vec::with_capacity(n_sigs);
    for _ in 0..n_sigs {
        signatures.push(take(b, &mut off, 64)?);
    }
    let first = *b.get(off)?;
    let version: i8 = if first & 0x80 != 0 {
        if first & 0x7f != 0 {
            return None; // only v0 exists today
        }
        off += 1;
        0
    } else {
        -1
    };
    let h = take(b, &mut off, 3)?;
    let header = [h[0], h[1], h[2]];
    let n_keys = compact_u16(b, &mut off)?;
    let mut keys = Vec::with_capacity(n_keys);
    for _ in 0..n_keys {
        keys.push(take(b, &mut off, 32)?);
    }
    let blockhash = take(b, &mut off, 32)?;
    let n_ix = compact_u16(b, &mut off)?;
    let mut instructions = Vec::with_capacity(n_ix);
    for _ in 0..n_ix {
        let program_idx = *take(b, &mut off, 1)?.first()?;
        let n_acc = compact_u16(b, &mut off)?;
        let accounts = take(b, &mut off, n_acc)?;
        let n_data = compact_u16(b, &mut off)?;
        let data = take(b, &mut off, n_data)?;
        instructions.push(IxView { program_idx, accounts, data });
    }
    let mut n_lookups = 0;
    if version == 0 {
        n_lookups = compact_u16(b, &mut off)?;
        for _ in 0..n_lookups {
            take(b, &mut off, 32)?;
            let w = compact_u16(b, &mut off)?;
            take(b, &mut off, w)?;
            let r = compact_u16(b, &mut off)?;
            take(b, &mut off, r)?;
        }
    }
    Some(TxView { signatures, version, header, keys, blockhash, instructions, n_lookups, consumed: off })
}

/// One top-level pump instruction, summarised.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PumpIx {
    /// short kind name ("buy", "sell", "bq3", ...) or "other:<disc hex>"
    pub kind: String,
    /// mint / user as 32-byte keys; None when unknown layout or the index points into a lookup table
    pub mint: Option<[u8; 32]>,
    pub user: Option<[u8; 32]>,
    /// first two u64 args after the discriminator (0 when absent); meaning depends on kind (see README)
    pub a1: u64,
    pub a2: u64,
}

/// (discriminator, kind, mint account index, user account index); usize::MAX = layout not known
const NA: usize = usize::MAX;
const PUMP_KINDS: &[([u8; 8], &str, usize, usize)] = &[
    ([0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea], "buy", 2, 6), // amount tokens, max_sol_cost
    ([0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad], "sell", 2, 6), // amount tokens, min_sol_output
    ([0x38, 0xfc, 0x74, 0x08, 0x9e, 0xdf, 0xcd, 0x5f], "bxs", 2, 6), // buy_exact_sol_in: sol in, min tokens
    ([0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88], "bq3", 1, 8), // buy_exact_quote_in_v3: sol in, min tokens
    ([0x1c, 0x92, 0xde, 0x77, 0x26, 0xc4, 0x69, 0xd5], "sell3", 1, 8), // sell_v3: amount tokens, min sol out
    ([0x64, 0x6c, 0xbd, 0x84, 0x80, 0x67, 0x6c, 0xf9], "sellx3", 1, 8), // sell_exact_tokens_in_v3 (layout unconfirmed)
    ([0xc2, 0xab, 0x1c, 0x46, 0x68, 0x4d, 0x5b, 0x2f], "bq2", NA, NA), // buy_exact_quote_in_v2: sol in, min tokens
    ([0xb8, 0x17, 0xee, 0x61, 0x67, 0xc5, 0xd3, 0x3d], "buy2", NA, NA), // buy_v2: amount tokens, max sol
    ([0x07, 0x05, 0x1d, 0xc4, 0xf5, 0x17, 0x65, 0x50], "buy3", NA, NA), // buy_v3: amount tokens, max sol
    ([0x18, 0x1e, 0xc8, 0x28, 0x05, 0x1c, 0x07, 0x77], "create", 0, 7),
    ([0xd6, 0x90, 0x4c, 0xec, 0x5f, 0x8b, 0x31, 0xb4], "create_v2", 0, 5),
];
const AMM_KINDS: &[([u8; 8], &str, usize, usize)] = &[
    ([0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea], "amm_buy", 3, 1), // base_amount_out, max_quote_in
    ([0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad], "amm_sell", 3, 1), // base_amount_in, min_quote_out
    ([0xc6, 0x2e, 0x15, 0x52, 0xb4, 0xd9, 0xe8, 0x70], "amm_bq", 3, 1), // buy_exact_quote_in: quote in, min base out
];

fn key_at(tx: &TxView, ix: &IxView, pos: usize) -> Option<[u8; 32]> {
    if pos == NA {
        return None;
    }
    let idx = *ix.accounts.get(pos)? as usize;
    let k = tx.keys.get(idx)?; // index beyond static keys = lookup-table address: unknown here
    let mut out = [0u8; 32];
    out.copy_from_slice(k);
    Some(out)
}

#[inline]
fn u64_at(d: &[u8], off: usize) -> u64 {
    d.get(off..off + 8).map(|s| u64::from_le_bytes(s.try_into().unwrap())).unwrap_or(0)
}

/// Summarise the top-level instructions of `tx` that call pump.fun (and pump AMM when `amm` is Some).
pub fn pump_summary(tx: &TxView, pump: &[u8; 32], amm: Option<&[u8; 32]>) -> Vec<PumpIx> {
    let mut out = Vec::new();
    for ix in &tx.instructions {
        let Some(&prog) = tx.keys.get(ix.program_idx as usize) else { continue };
        let table = if prog == &pump[..] {
            PUMP_KINDS
        } else if amm.map(|a| prog == &a[..]).unwrap_or(false) {
            AMM_KINDS
        } else {
            continue;
        };
        let disc: Option<[u8; 8]> = ix.data.get(..8).map(|s| s.try_into().unwrap());
        let hit = disc.and_then(|d| table.iter().find(|(k, ..)| *k == d));
        let (kind, mi, ui) = match (hit, disc) {
            (Some((_, name, mi, ui)), _) => (name.to_string(), *mi, *ui),
            (None, Some(d)) => (format!("other:{}", hex(&d)), NA, NA),
            (None, None) => ("other:".to_string(), NA, NA),
        };
        out.push(PumpIx {
            kind,
            mint: key_at(tx, ix, mi),
            user: key_at(tx, ix, ui),
            a1: u64_at(ix.data, 8),
            a2: u64_at(ix.data, 16),
        });
    }
    out
}

pub fn hex(b: &[u8]) -> String {
    const H: &[u8; 16] = b"0123456789abcdef";
    let mut s = String::with_capacity(b.len() * 2);
    for &x in b {
        s.push(H[(x >> 4) as usize] as char);
        s.push(H[(x & 15) as usize] as char);
    }
    s
}

pub fn decode_pubkey(s: &str) -> Option<[u8; 32]> {
    let v = bs58::decode(s).into_vec().ok()?;
    v.try_into().ok()
}

// ---------------------------------------------------------------------------------------------
// Test-only serializer (also used by the fake-server integration test to build realistic payloads)
// ---------------------------------------------------------------------------------------------

pub mod build {
    //! Builds VersionedTransaction wire bytes (legacy or v0) from parts. Used by tests and the fake server.
    pub struct Ix {
        pub program_idx: u8,
        pub accounts: Vec<u8>,
        pub data: Vec<u8>,
    }
    pub struct Lookup {
        pub key: [u8; 32],
        pub writable: Vec<u8>,
        pub readonly: Vec<u8>,
    }

    pub fn compact_u16(out: &mut Vec<u8>, mut v: usize) {
        loop {
            let mut b = (v & 0x7f) as u8;
            v >>= 7;
            if v != 0 {
                b |= 0x80;
                out.push(b);
            } else {
                out.push(b);
                break;
            }
        }
    }

    pub fn tx_bytes(sigs: &[[u8; 64]], v0: bool, header: [u8; 3], keys: &[[u8; 32]], blockhash: [u8; 32], ixs: &[Ix], lookups: &[Lookup]) -> Vec<u8> {
        let mut o = Vec::new();
        compact_u16(&mut o, sigs.len());
        for s in sigs {
            o.extend_from_slice(s);
        }
        if v0 {
            o.push(0x80);
        }
        o.extend_from_slice(&header);
        compact_u16(&mut o, keys.len());
        for k in keys {
            o.extend_from_slice(k);
        }
        o.extend_from_slice(&blockhash);
        compact_u16(&mut o, ixs.len());
        for ix in ixs {
            o.push(ix.program_idx);
            compact_u16(&mut o, ix.accounts.len());
            o.extend_from_slice(&ix.accounts);
            compact_u16(&mut o, ix.data.len());
            o.extend_from_slice(&ix.data);
        }
        if v0 {
            compact_u16(&mut o, lookups.len());
            for l in lookups {
                o.extend_from_slice(&l.key);
                compact_u16(&mut o, l.writable.len());
                o.extend_from_slice(&l.writable);
                compact_u16(&mut o, l.readonly.len());
                o.extend_from_slice(&l.readonly);
            }
        }
        o
    }

    /// A realistic pump buy (buy_exact_quote_in_v3 layout: mint at [1], user at [8], program at [16]).
    /// keys: 0 user(signer) 1 mint 2 pump program, plus filler keys; v0 puts some accounts in a lookup table.
    pub fn pump_bq3_tx(sig: [u8; 64], user: [u8; 32], mint: [u8; 32], pump: [u8; 32], sol_in: u64, min_out: u64, v0: bool) -> Vec<u8> {
        let mut keys: Vec<[u8; 32]> = vec![user, mint, pump];
        for i in 0..14u8 {
            keys.push([100 + i; 32]);
        }
        // account order for the ix: 0 global,1 mint,2..7 filler,8 user, 9..16 filler ; indices into keys
        let mut acc: Vec<u8> = vec![3, 1, 4, 5, 6, 7, 8, 9, 0, 10, 11, 12, 13, 14, 15, 16, 2];
        if v0 {
            // last two accounts come from a lookup table (indices >= keys.len())
            acc[14] = keys.len() as u8;
            acc[15] = keys.len() as u8 + 1;
        }
        let mut data = vec![0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88];
        data.extend_from_slice(&sol_in.to_le_bytes());
        data.extend_from_slice(&min_out.to_le_bytes());
        data.push(0);
        let ixs = vec![
            Ix { program_idx: 4, accounts: vec![], data: vec![2, 0x40, 0x42, 0x0f, 0] }, // a compute-budget-like ix
            Ix { program_idx: 2, accounts: acc, data },
        ];
        let lookups = if v0 { vec![Lookup { key: [7; 32], writable: vec![3], readonly: vec![9] }] } else { vec![] };
        tx_bytes(&[sig], v0, [1, 0, 5], &keys, [9; 32], &ixs, &lookups)
    }
}

#[cfg(test)]
mod tests {
    use super::build::{self, pump_bq3_tx, tx_bytes, Ix, Lookup};
    use super::*;

    fn pk(b: u8) -> [u8; 32] {
        [b; 32]
    }

    #[test]
    fn legacy_roundtrip_and_pump_buy() {
        let pump = decode_pubkey(PUMP_PROGRAM).unwrap();
        let mut sig = [0u8; 64];
        sig[0] = 42;
        sig[63] = 7;
        let b = pump_bq3_tx(sig, pk(1), pk(2), pump, 300_000_000, 12345, false);
        let tx = parse_tx(&b).expect("parse legacy");
        assert_eq!(tx.version, -1);
        assert_eq!(tx.consumed, b.len());
        assert_eq!(tx.signatures.len(), 1);
        assert_eq!(tx.signatures[0], &sig[..]);
        assert_eq!(tx.keys.len(), 17);
        assert_eq!(tx.instructions.len(), 2);
        assert_eq!(tx.n_lookups, 0);
        let s = pump_summary(&tx, &pump, None);
        assert_eq!(s.len(), 1);
        assert_eq!(s[0].kind, "bq3");
        assert_eq!(s[0].mint, Some(pk(2)));
        assert_eq!(s[0].user, Some(pk(1)));
        assert_eq!(s[0].a1, 300_000_000);
        assert_eq!(s[0].a2, 12345);
    }

    #[test]
    fn v0_with_lookup_table() {
        let pump = decode_pubkey(PUMP_PROGRAM).unwrap();
        let sig = [3u8; 64];
        let b = pump_bq3_tx(sig, pk(1), pk(2), pump, 5, 6, true);
        let tx = parse_tx(&b).expect("parse v0");
        assert_eq!(tx.version, 0);
        assert_eq!(tx.consumed, b.len());
        assert_eq!(tx.n_lookups, 1);
        let s = pump_summary(&tx, &pump, None);
        assert_eq!(s.len(), 1);
        assert_eq!(s[0].kind, "bq3");
        assert_eq!(s[0].mint, Some(pk(2)));
        assert_eq!((s[0].a1, s[0].a2), (5, 6));
    }

    #[test]
    fn v0_mint_in_lookup_is_none_and_classic_buy_sell() {
        let pump = decode_pubkey(PUMP_PROGRAM).unwrap();
        let amm = decode_pubkey(PUMP_AMM_PROGRAM).unwrap();
        // keys: 0 user, 1 pump, 2 amm ; classic buy with mint (pos 2) pointing into a lookup table
        let keys = vec![pk(1), pump, amm, pk(4), pk(5)];
        let mut buy = vec![0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea];
        buy.extend_from_slice(&1000u64.to_le_bytes());
        buy.extend_from_slice(&2000u64.to_le_bytes());
        let mut sell = vec![0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad];
        sell.extend_from_slice(&7u64.to_le_bytes());
        sell.extend_from_slice(&8u64.to_le_bytes());
        let ixs = vec![
            Ix { program_idx: 1, accounts: vec![3, 4, 5, 3, 4, 3, 0], data: buy }, // mint idx 5 = lookup
            Ix { program_idx: 1, accounts: vec![3, 4, 3, 3, 4, 3, 0], data: sell.clone() }, // mint idx 3 = static
            Ix { program_idx: 2, accounts: vec![3, 0, 4, 4], data: sell }, // amm sell, mint at [3] = idx 4
            Ix { program_idx: 1, accounts: vec![], data: vec![1, 2, 3, 4, 5, 6, 7, 8, 9] }, // unknown disc
        ];
        let lookups = vec![Lookup { key: pk(9), writable: vec![0], readonly: vec![] }];
        let b = tx_bytes(&[[5u8; 64], [6u8; 64]], true, [2, 0, 2], &keys, pk(8), &ixs, &lookups);
        let tx = parse_tx(&b).unwrap();
        assert_eq!(tx.signatures.len(), 2);
        assert_eq!(tx.consumed, b.len());
        let s = pump_summary(&tx, &pump, None);
        assert_eq!(s.len(), 3, "amm not included without the amm flag");
        assert_eq!(s[0].kind, "buy");
        assert_eq!(s[0].mint, None);
        assert_eq!(s[0].user, Some(pk(1)));
        assert_eq!((s[0].a1, s[0].a2), (1000, 2000));
        assert_eq!(s[1].kind, "sell");
        assert_eq!(s[1].mint, Some(pk(4)));
        assert_eq!(s[2].kind, "other:0102030405060708");
        let s2 = pump_summary(&tx, &pump, Some(&amm));
        assert_eq!(s2.len(), 4);
        assert_eq!(s2[2].kind, "amm_sell");
        assert_eq!(s2[2].mint, Some(pk(5)));
        assert_eq!(s2[2].user, Some(pk(1)));
    }

    #[test]
    fn rejects_garbage_and_truncation() {
        let pump = decode_pubkey(PUMP_PROGRAM).unwrap();
        let b = pump_bq3_tx([1u8; 64], pk(1), pk(2), pump, 1, 2, true);
        for cut in [0, 1, 10, 64, 66, 100, b.len() - 1] {
            assert!(parse_tx(&b[..cut]).is_none(), "truncated at {cut} must fail");
        }
        assert!(parse_tx(&[0xff, 0xff, 0xff, 0xff]).is_none());
        let mut v1 = b.clone();
        v1[65] = 0x81; // version 1 does not exist
        assert!(parse_tx(&v1).is_none());
    }

    #[test]
    fn compact_u16_multibyte() {
        for v in [0usize, 1, 127, 128, 255, 300, 16383, 16384, 65535] {
            let mut o = Vec::new();
            build::compact_u16(&mut o, v);
            let mut off = 0;
            assert_eq!(super::compact_u16(&o, &mut off), Some(v));
            assert_eq!(off, o.len());
        }
    }
}

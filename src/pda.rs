//! Program-derived addresses and associated token accounts, without the Solana SDK. Derivation costs a SHA-256 plus
//! a curve check per bump tried, so callers precompute at load time and cache (`AtaCache`), never on the hot path.
use crate::tx::Pk;
use sha2::{Digest, Sha256};
use rustc_hash::FxHashMap as HashMap;
use std::cell::RefCell;
use std::sync::LazyLock;

pub static TOKEN_PROGRAM: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"));
pub static TOKEN_2022: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"));
pub static ATA_PROGRAM: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL"));
pub static SYSTEM_PROGRAM: LazyLock<Pk> = LazyLock::new(|| [0u8; 32]);

fn on_curve(b: &[u8; 32]) -> bool { curve25519_dalek::edwards::CompressedEdwardsY(*b).decompress().is_some() }

pub fn create_program_address(seeds: &[&[u8]], program: &Pk) -> Option<Pk> {
    let mut h = Sha256::new();
    for s in seeds { h.update(s); }
    h.update(program);
    h.update(b"ProgramDerivedAddress");
    let out: [u8; 32] = h.finalize().into();
    if on_curve(&out) { None } else { Some(out) }
}

pub fn find_program_address(seeds: &[&[u8]], program: &Pk) -> (Pk, u8) {
    for bump in (0..=255u8).rev() {
        let b = [bump];
        let mut s: Vec<&[u8]> = seeds.to_vec();
        s.push(&b);
        if let Some(k) = create_program_address(&s, program) { return (k, bump); }
    }
    panic!("no viable bump");
}

pub fn ata(owner: &Pk, mint: &Pk, token_program: &Pk) -> Pk {
    find_program_address(&[owner, token_program, mint], &ATA_PROGRAM).0
}

/// Cache of (owner, mint, token program) -> ATA. Engine-thread only (no lock); a miss costs one derivation.
#[derive(Default)]
pub struct AtaCache { m: RefCell<HashMap<(Pk, Pk, Pk), Pk>>, pub misses: std::cell::Cell<u64> }

impl AtaCache {
    pub fn get(&self, owner: &Pk, mint: &Pk, prog: &Pk) -> Pk {
        let key = (*owner, *mint, *prog);
        if let Some(k) = self.m.borrow().get(&key) { return *k; }
        let k = ata(owner, mint, prog);
        self.misses.set(self.misses.get() + 1);
        let mut m = self.m.borrow_mut();
        if m.len() > 500_000 { m.clear(); }
        m.insert(key, k);
        k
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tx::pk;

    #[test]
    fn known_addresses() {
        // Meteora DLMM event authority and Raydium AMM v4 authority, both quoted in the venue specs
        let dlmm = pk("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo");
        assert_eq!(crate::tx::b58(&find_program_address(&[b"__event_authority"], &dlmm).0), "D1ZN9Wj1fRSUQfCjhvnu1hqDMT7hzjzBBpi12nVniYD6");
        let amm = pk("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8");
        assert_eq!(crate::tx::b58(&find_program_address(&[b"amm authority"], &amm).0), "5Q544fKrFoe6tsEbD7S8EmxGTJYAKtTVhAW5Q5pge4j1");
        let cpmm = pk("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C");
        assert_eq!(crate::tx::b58(&find_program_address(&[b"vault_and_lp_mint_auth_seed"], &cpmm).0), "GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL");
    }
}

//! Meteora DLMM: bin-array indexing and PDAs, and decoding a third party's swap instruction. Quotes are
//! arbx-sizing's (`src/quote.rs`, PLAN-ADDENDUM WP-16; lb_clmm 0.12: limit-order layers, both fee modes, the bitmap
//! jump); the engine's own maths before WP-16 is in `venues::legacy::dlmm` (tests only).
use super::{u64_at, PendingSwap, PoolMeta, Venue};
use crate::tx::Pk;

pub const BINS_PER_ARRAY: i32 = 70;

pub fn array_index(bin: i32) -> i64 { (bin as i64).div_euclid(BINS_PER_ARRAY as i64) }

pub fn bin_array_pda(pair: &Pk, index: i64) -> Pk {
    crate::pda::find_program_address(&[b"bin_array", pair, &index.to_le_bytes()], &super::DLMM).0
}

fn hex8(s: &str) -> [u8; 8] { let v: Vec<u8> = (0..8).map(|i| u8::from_str_radix(&s[2 * i..2 * i + 2], 16).unwrap()).collect(); v.try_into().unwrap() }

/// Decode a third party's DLMM swap. Accounts 0..10 are shared by every variant: [0] lb_pair [4] user_token_in
/// [5] user_token_out [10] user. Exact-in variants carry amount_in @8; exact-out variants max_in @8, amount_out @16.
pub fn decode_pending<'a>(data: &[u8], acc: &[Pk], meta: &dyn Fn(&Pk) -> Option<&'a PoolMeta>, ata: &dyn Fn(&Pk, &Pk, &Pk) -> Pk) -> Option<PendingSwap> {
    let d: [u8; 8] = data.get(..8)?.try_into().ok()?;
    let exact_out = if d == hex8("414b3f4ceb5b5b88") || d == hex8("f8c69e91e17587c8") || d == hex8("38ade6d0ade49ccd") || d == hex8("4a62c0d6b1334b33") { false }
        else if d == hex8("2bd7f784893cf351") || d == hex8("fa49652126cf4bb8") { true } else { return None };
    if acc.len() < 11 { return None; }
    let pool = acc[0];
    let m = meta(&pool)?;
    let user = acc[10];
    let zfo = if acc[4] == ata(&user, &m.t0, &m.t0_prog) { true } else if acc[4] == ata(&user, &m.t1, &m.t1_prog) { false }
        // non-ATA token accounts: fall back to the output account
        else if acc[5] == ata(&user, &m.t1, &m.t1_prog) { true } else if acc[5] == ata(&user, &m.t0, &m.t0_prog) { false } else { return None };
    // swap / swap2: amount_in @8, min_amount_out @16; swap_exact_out(2): max_in_amount @8, out_amount @16;
    // swap_with_price_impact(2) carries no amount bound (a price-impact limit instead): none we check
    let price_impact = d == hex8("38ade6d0ade49ccd") || d == hex8("4a62c0d6b1334b33");
    let limit = if price_impact { 0 } else { u64_at(data, if exact_out { 8 } else { 16 }).unwrap_or(0) };
    Some(PendingSwap { pool, venue: Venue::Dlmm, zero_for_one: zfo, amount: u64_at(data, if exact_out { 16 } else { 8 })?, exact_out, user, limit })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn array_indexes() {
        assert_eq!(array_index(-1), -1);
        assert_eq!(array_index(69), 0);
        assert_eq!(array_index(-70), -1);
        assert_eq!(array_index(-71), -2);
        // the crate's walker indexes arrays the same way
        for b in [-71, -70, -1, 0, 69, 70, 443_636] { assert_eq!(array_index(b), arbx_sizing::venue::dlmm::array_index(b)); }
    }
}

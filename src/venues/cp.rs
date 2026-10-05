//! Constant-product venues (Raydium AMM v4, Raydium CPMM, PumpSwap): decoding a third party's swap instruction.
//! Their quotes are arbx-sizing's (`src/quote.rs`, PLAN-ADDENDUM WP-16); the engine's own maths before WP-16 is in
//! `venues::legacy::cp` (tests only).
use super::{u64_at, PendingSwap, PoolMeta, Venue};
use crate::tx::Pk;

fn disc(d: &[u8]) -> Option<[u8; 8]> { d.get(..8).map(|b| b.try_into().unwrap()) }
fn hex8(s: &str) -> [u8; 8] { let v: Vec<u8> = (0..8).map(|i| u8::from_str_radix(&s[2 * i..2 * i + 2], 16).unwrap()).collect(); v.try_into().unwrap() }

/// Decode a third party's swap on a constant-product venue. `acc` = the instruction's accounts resolved to keys.
/// `meta` finds our registry row for a pool; `ata` derives (owner, mint, token program) -> ATA (cached).
pub fn decode_pending<'a>(venue: Venue, data: &[u8], acc: &[Pk], meta: &dyn Fn(&Pk) -> Option<&'a PoolMeta>, ata: &dyn Fn(&Pk, &Pk, &Pk) -> Pk) -> Option<PendingSwap> {
    match venue {
        Venue::RayAmmV4 => {
            // 1-byte tags: 16 base-in v2 / 17 base-out v2 (8 accounts), 9 base-in / 11 base-out v1 (17-18 accounts)
            let tag = *data.first()?;
            let (v2, exact_out) = match tag { 16 => (true, false), 17 => (true, true), 9 => (false, false), 11 => (false, true), _ => return None };
            if data.len() < 17 { return None; }
            let n = acc.len();
            if (v2 && n < 8) || (!v2 && n != 17 && n != 18) { return None; }
            let pool = acc[1];
            let (user, user_in) = if v2 { (acc[7], acc[5]) } else { (acc[n - 1], acc[n - 3]) };
            let m = meta(&pool)?;
            let zfo = if user_in == ata(&user, &m.t0, &m.t0_prog) { true } else if user_in == ata(&user, &m.t1, &m.t1_prog) { false } else { return None };
            // base in: amount_in @1, minimum_amount_out @9; base out: max_amount_in @1, amount_out @9
            Some(PendingSwap { pool, venue, zero_for_one: zfo, amount: u64_at(data, if exact_out { 9 } else { 1 })?, exact_out, user, limit: u64_at(data, if exact_out { 1 } else { 9 })? })
        }
        Venue::RayCpmm => {
            let d = disc(data)?;
            let exact_out = if d == hex8("8fbe5adac41e33de") { false } else if d == hex8("37d96256a34ab4ad") { true } else { return None };
            if acc.len() < 8 { return None; }
            let pool = acc[3];
            let m = meta(&pool)?;
            let zfo = if acc[6] == m.vault0 { true } else if acc[6] == m.vault1 { false } else { return None };
            // swap_base_input: amount_in @8, minimum_amount_out @16; swap_base_output: max_amount_in @8, amount_out @16
            Some(PendingSwap { pool, venue, zero_for_one: zfo, amount: u64_at(data, if exact_out { 16 } else { 8 })?, exact_out, user: acc[0], limit: u64_at(data, if exact_out { 8 } else { 16 })? })
        }
        Venue::PumpSwap => {
            let d = disc(data)?;
            // sell: base in exact; buy_exact_quote_in: quote in exact; buy: base out exact
            let (sell, exact_out) = if d == hex8("33e685a4017f83ad") { (true, false) } else if d == hex8("c62e1552b4d9e870") { (false, false) }
                else if d == hex8("66063d1201daebea") { (false, true) } else { return None };
            if acc.len() < 4 { return None; }
            let pool = acc[0];
            let m = meta(&pool)?;
            if acc[3] != m.t0 { return None; }
            // sell: min_quote_out @16; buy_exact_quote_in: min_base_out @16; buy: max_quote_in @16
            Some(PendingSwap { pool, venue, zero_for_one: sell, amount: u64_at(data, 8)?, exact_out, user: acc[1], limit: u64_at(data, 16).unwrap_or(0) })
        }
        Venue::Dlmm | Venue::DammV2 => None,
    }
}

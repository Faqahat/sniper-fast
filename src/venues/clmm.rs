//! Raydium CLMM and Orca Whirlpool (PLAN-ADDENDUM WP-21; arbx-sizing kinds 7 and 8, DESIGN.md §9): the pool fields the
//! engine reads, the PDAs of their tick arrays, the bitmap extension and the oracle, the tick arrays the state stream
//! follows around the price, and decoding a third party's swap. Quotes are arbx-sizing's (`src/quote.rs`), proven against
//! the deployed binaries in program/venue-harness (`tests/clmm_exactness.rs`, `tests/clmm_adversarial.rs`).
//!
//! Which tick arrays are followed (DESIGN.md §9.0 item 3), per pool, re-derived whenever the price leaves the set's
//! current array or the pool's bitmaps change (`Store::clmm_drift`):
//! - **Raydium CLMM:** the current tick's array, then up to [`RAY_FOLLOW_EACH_WAY`] initialized arrays each way by the
//!   pool's tick-array bitmap and, beyond its default range, the TickArrayBitmapExtension. Only initialized arrays can be
//!   read by a swap (the program jumps over the others by the bitmaps), and a leg names at most 7 remaining accounts.
//! - **Orca Whirlpool:** the PDAs of the current tick's array and the next two each way (a→b uses the current array and
//!   the two below; b→a the current one and the two above, or the three above near the array's end), initialized or not:
//!   the program reads an uninitialized one as zeroed, so the engine must know which of them do not exist (the store holds
//!   such an account empty: `Engine::on_fetch`, the boot snapshot).
use super::{i32_at, pk_at, u128_at, u16_at, PendingSwap, PoolMeta, Venue, RAYCLMM, WHIRLPOOL};
use crate::pda;
use crate::tx::Pk;
use arbx_sizing::venue::{orca_whirlpool as orca, raydium_clmm as ray};

/// Raydium CLMM: initialized tick arrays followed each way from the current one (a route's leg names at most 6 with the
/// bitmap extension, 7 without)
pub const RAY_FOLLOW_EACH_WAY: usize = 6;
/// Orca Whirlpool: the tick arrays followed, relative to the current one (every array a swap's sequence can need)
pub const WHIRL_FOLLOW: std::ops::RangeInclusive<i32> = -2..=3;

/// `sha256("global:swap")[..8]` (Anchor; the `swap` of both programs) and `sha256("global:swap_v2")[..8]`
pub const SWAP: [u8; 8] = [0xf8, 0xc6, 0x9e, 0x91, 0xe1, 0x75, 0x87, 0xc8];
pub const SWAP_V2: [u8; 8] = [0x2b, 0x04, 0xed, 0x0b, 0x1a, 0xc9, 0x1e, 0x62];
/// Orca's `two_hop_swap` and `two_hop_swap_v2`, Raydium's `swap_router_base_in` (Anchor)
pub const TWO_HOP_SWAP: [u8; 8] = [0xc3, 0x60, 0xed, 0x6c, 0x44, 0xa2, 0xdb, 0xe6];
pub const TWO_HOP_SWAP_V2: [u8; 8] = [0xba, 0x8f, 0xd1, 0x1d, 0xfe, 0x02, 0xc2, 0x75];
pub const SWAP_ROUTER_BASE_IN: [u8; 8] = [0x45, 0x7d, 0x73, 0xda, 0xf5, 0xba, 0xf2, 0xc4];
/// every swap instruction of the two programs (ed1eb41 and the deployed Whirlpool): none creates an account
pub const SWAPS: [[u8; 8]; 5] = [SWAP, SWAP_V2, TWO_HOP_SWAP, TWO_HOP_SWAP_V2, SWAP_ROUTER_BASE_IN];

/// FT-009: whether a top-level instruction (`data`) of a CLMM program is one of its swaps, the instructions that never
/// create an account (an LP instruction may create the tick arrays it names)
pub fn is_swap(data: &[u8]) -> bool { data.get(..8).is_some_and(|d| SWAPS.iter().any(|s| s[..] == *d)) }

// ------------------------------------------------------------------ PDAs

/// Raydium CLMM TickArrayState PDA["tick_array", pool, start (i32 big-endian)]
pub fn ray_tick_array_pda(pool: &Pk, start: i32) -> Pk { pda::find_program_address(&[b"tick_array", pool, &start.to_be_bytes()], &RAYCLMM).0 }
/// Raydium CLMM TickArrayBitmapExtension PDA["pool_tick_array_bitmap_extension", pool]
pub fn ray_ext_pda(pool: &Pk) -> Pk { pda::find_program_address(&[b"pool_tick_array_bitmap_extension", pool], &RAYCLMM).0 }
/// Orca Whirlpool TickArray PDA["tick_array", whirlpool, start as a decimal string]
pub fn whirl_tick_array_pda(pool: &Pk, start: i32) -> Pk { pda::find_program_address(&[b"tick_array", pool, start.to_string().as_bytes()], &WHIRLPOOL).0 }
/// Orca Whirlpool Oracle PDA["oracle", whirlpool]
pub fn whirl_oracle_pda(pool: &Pk) -> Pk { pda::find_program_address(&[b"oracle", pool], &WHIRLPOOL).0 }

/// the PDA of tick array `start` of pool `m`
pub fn tick_array_pda(m: &PoolMeta, start: i32) -> Option<Pk> {
    match m.venue { Venue::RayClmm => Some(ray_tick_array_pda(&m.pool, start)), Venue::Whirlpool => Some(whirl_tick_array_pda(&m.pool, start)), _ => None }
}

// ------------------------------------------------------------------ the binaries the ports were proven on

/// The last deploy slots of the binaries arbx-sizing's ports were proven against (program/venue-harness
/// fixtures/programs/MANIFEST.json: raydium-clmm ed1eb41, whirlpool 0.9.0). DESIGN.md §6.5's upgrade watch, in the
/// engine: a programdata version the state stream delivers with another slot (an upgrade) stops pricing the venue
/// (`venue_upgraded`) until the port follows it and the harness passes again (DESIGN.md §7 item 12: Orca's U256 fix)
pub const RAY_DEPLOY_SLOT: u64 = 451_479_902;
pub const WHIRL_DEPLOY_SLOT: u64 = 440_170_207;

/// the programdata account of venue `v`'s program (upgradeable loader PDA[program])
pub fn programdata(v: Venue) -> Pk {
    use std::sync::LazyLock;
    static RAY: LazyLock<Pk> = LazyLock::new(|| pda::find_program_address(&[&*RAYCLMM], &crate::tx::pk(crate::provenance::UPGRADEABLE_LOADER)).0);
    static WHIRL: LazyLock<Pk> = LazyLock::new(|| pda::find_program_address(&[&*WHIRLPOOL], &crate::tx::pk(crate::provenance::UPGRADEABLE_LOADER)).0);
    if v == Venue::Whirlpool { *WHIRL } else { *RAY }
}

/// whether a programdata version of venue `v` is the deploy the port was proven on (false: upgraded, or unreadable)
pub fn deployed_as_proven(v: Venue, programdata: &[u8]) -> bool {
    let want = if v == Venue::Whirlpool { WHIRL_DEPLOY_SLOT } else { RAY_DEPLOY_SLOT };
    crate::provenance::parse_programdata_header(programdata).is_ok_and(|h| h.last_deploy_slot == want)
}

/// PLAN-ADDENDUM WP-21 (review F5): a venue's deploy check, as a segment records it at its start and end (meta.json
/// `clmm_deploy`): its programdata's header read now (`header`: the first 45 bytes; None when the read failed, `error`
/// then says why) against the deploy slot its port was proven on. `ok` false (changed, or unknown) switches the venue
/// off for the segment: it is not priced on a binary its port was not proven against
pub fn deploy_entry(v: Venue, header: Option<&[u8]>, error: Option<&str>) -> serde_json::Value {
    let proven = if v == Venue::Whirlpool { WHIRL_DEPLOY_SLOT } else { RAY_DEPLOY_SLOT };
    let parsed = header.map(crate::provenance::parse_programdata_header);
    let slot = parsed.as_ref().and_then(|h| h.as_ref().ok()).map(|h| h.last_deploy_slot);
    let why = match (header, &parsed) {
        (None, _) => Some(error.unwrap_or("the programdata account was not found").to_string()),
        (_, Some(Err(e))) => Some(format!("{e:#}")),
        _ => None,
    };
    serde_json::json!({ "venue": crate::replay::venue_name(v), "program": crate::tx::b58(&v.program()), "programdata": crate::tx::b58(&programdata(v)),
        "proven_deploy_slot": proven, "last_deploy_slot": slot, "ok": slot == Some(proven), "error": why })
}

// ------------------------------------------------------------------ pool fields

/// the pool's tick spacing (Raydium @235, Orca @41)
pub fn tick_spacing(v: Venue, pool: &[u8]) -> Option<u16> {
    match v { Venue::RayClmm => u16_at(pool, ray::off::TICK_SPACING), Venue::Whirlpool => u16_at(pool, orca::off::TICK_SPACING), _ => None }.filter(|t| *t > 0)
}
/// the pool's current tick (Raydium @269, Orca @81)
pub fn tick_current(v: Venue, pool: &[u8]) -> Option<i32> {
    match v { Venue::RayClmm => i32_at(pool, ray::off::TICK_CURRENT), Venue::Whirlpool => i32_at(pool, orca::off::TICK_CURRENT), _ => None }
}
/// the start index of the tick array holding the pool's current tick (Raydium: 60 ticks a spacing; Orca: 88). None for
/// a current tick outside the tick range (no real pool has one; both programs refuse it, and the start would overflow)
pub fn current_array(v: Venue, pool: &[u8]) -> Option<i32> {
    let (ts, t) = (tick_spacing(v, pool)?, tick_current(v, pool)?);
    if !(ray::MIN_TICK..=ray::MAX_TICK).contains(&t) { return None; }
    match v { Venue::RayClmm => Some(ray::array_start(t, ts)), Venue::Whirlpool => Some(orca::array_start(t, ts)), _ => None }
}
/// Raydium CLMM: the pool's observation account (@201; every swap writes it, no quote reads it: not followed)
pub fn observation(pool: &[u8]) -> Option<Pk> { pk_at(pool, ray::off::OBSERVATION) }
/// Raydium CLMM: the pool's AmmConfig (@9)
pub fn amm_config(pool: &[u8]) -> Option<Pk> { pk_at(pool, ray::off::AMM_CONFIG) }

/// Raydium CLMM: is the tick array starting at `start` initialized, by the pool's default bitmap (@904: arrays −512..511
/// of the pool's spacing, bit = array index + 512) or, beyond it, the TickArrayBitmapExtension (`ext`, 14 positive
/// bitmaps of 512 bits @40, 14 negative @936)? None beyond the default range without the extension. The program's own
/// classification (`check_tick_array_is_initialized`; arbx-sizing ports it for the walk itself): here only to choose the
/// arrays to follow and to name
pub fn ray_array_bit(pool: &[u8], ext: Option<&[u8]>, start: i32) -> Option<bool> {
    match ray_word_at(pool, ext, start) { BitWord::At(w, i) => Some(w >> i & 1 == 1), BitWord::Outside => Some(false), BitWord::Unknown => None }
}

/// Where a Raydium bitmap holds tick array `start`'s bit (`ray_array_bit`)
enum BitWord {
    /// the u64 word holding it and the bit within it: a word's 64 bits are 64 consecutive arrays, in start order
    At(u64, u32),
    /// past every bitmap (beyond the tick range)
    Outside,
    /// beyond the default range without the extension, or the bytes too short
    Unknown,
}

/// The word of the pool's default bitmap (@904: arrays −512..511 of the pool's spacing, bit = array index + 512) or,
/// beyond it, of the TickArrayBitmapExtension (`ext`: 14 positive bitmaps of 512 bits @40, 14 negative @936) holding
/// tick array `start`'s bit
fn ray_word_at(pool: &[u8], ext: Option<&[u8]>, start: i32) -> BitWord {
    // in i64: no input overflows
    let Some(ts) = tick_spacing(Venue::RayClmm, pool) else { return BitWord::Unknown };
    let (start, per) = (start as i64, ray::TICK_ARRAY_SIZE as i64 * ts as i64);
    let boundary = per * 512;
    let word = |d: &[u8], at: usize, bit: usize| crate::venues::u64_at(d, at + 8 * (bit / 64)).map_or(BitWord::Unknown, |w| BitWord::At(w, (bit % 64) as u32));
    if (-boundary..boundary).contains(&start) { return word(pool, ray::off::BITMAP, (start.div_euclid(per) + 512) as usize); }
    let Some(ext) = ext else { return BitWord::Unknown };
    let mut offset = start.abs() / boundary - 1;
    if start < 0 && start.abs() % boundary == 0 { offset -= 1; }
    if !(0..14).contains(&offset) { return BitWord::Outside; }
    let m = start.abs() % boundary;
    let mut bit = m / per;
    if start < 0 && m != 0 { bit = 512 - bit; }
    if !(0..512).contains(&bit) { return BitWord::Outside; }
    word(ext, (if start < 0 { ray::off::E_NEGATIVE } else { ray::off::E_POSITIVE }) + 64 * offset as usize, bit as usize)
}

/// Raydium CLMM: the start indexes of up to `k` initialized tick arrays from the current tick's array (inclusive) in the
/// swap's direction, in walk order, by the bitmaps (`ext`: the extension's bytes when it exists). Stops at the tick
/// range's end, or where the default bitmap ends and no extension is given. Word by word (review F2): the rest of a
/// bitmap word in the walk's direction is one test, so crossing the whole range of a tick-spacing-1 pool reads about
/// 240 words, not 14,788 arrays (the answer is `ray_array_bit`'s, array by array: `the_word_scan_is_the_array_scan`)
pub fn ray_initialized_arrays(pool: &[u8], ext: Option<&[u8]>, zfo: bool, k: usize) -> Vec<i32> {
    let mut out = Vec::new();
    let (Some(ts), Some(st0)) = (tick_spacing(Venue::RayClmm, pool), current_array(Venue::RayClmm, pool)) else { return out };
    let per = ray::TICK_ARRAY_SIZE * ts as i32;
    let (lo, hi) = (ray::array_start(ray::MIN_TICK, ts), ray::array_start(ray::MAX_TICK, ts));
    let mut st = st0;
    while out.len() < k && (lo..=hi).contains(&st) {
        match ray_word_at(pool, ext, st) {
            BitWord::Unknown => break,
            BitWord::Outside => st = if zfo { st - per } else { st + per },
            // the bits from `i` down (a→b) or up (b→a): the nearest set one is the next initialized array, none means
            // the whole rest of the word is skipped at once
            BitWord::At(w, i) => {
                let (rest, step) = if zfo { (if i == 63 { w } else { w & ((1u64 << (i + 1)) - 1) }, -1) } else { (w & (u64::MAX << i), 1) };
                if rest == 0 {
                    st += step * if zfo { i as i32 + 1 } else { 64 - i as i32 } * per;
                    continue;
                }
                let j = if zfo { 63 - rest.leading_zeros() } else { rest.trailing_zeros() };
                let found = st + (j as i32 - i as i32) * per;
                if !(lo..=hi).contains(&found) { break; }
                out.push(found);
                st = found + step * per;
            }
        }
    }
    out
}

/// The tick arrays to follow for pool `m` (start index, PDA), from its account bytes (`pool`) and, for Raydium, its
/// bitmap extension's (`ext`, when it exists); `known`: PDAs already derived (start index -> key), reused
pub fn follow_starts(m: &PoolMeta, pool: &[u8], ext: Option<&[u8]>) -> Vec<i32> {
    match m.venue {
        Venue::RayClmm => {
            let Some(cur) = current_array(Venue::RayClmm, pool) else { return vec![] };
            let mut v = vec![cur];
            for zfo in [true, false] { v.extend(ray_initialized_arrays(pool, ext, zfo, RAY_FOLLOW_EACH_WAY)); }
            v.sort_unstable();
            v.dedup();
            v
        }
        Venue::Whirlpool => {
            let (Some(ts), Some(cur)) = (tick_spacing(Venue::Whirlpool, pool), current_array(Venue::Whirlpool, pool)) else { return vec![] };
            let per = orca::TICK_ARRAY_SIZE * ts as i32;
            WHIRL_FOLLOW.filter_map(|k| cur.checked_add(k.checked_mul(per)?)).filter(|st| orca::valid_start(*st, ts)).collect()
        }
        _ => vec![],
    }
}

/// The tick arrays a quote needs near the price, by start index (review F2's hysteresis: the follow set of a pool is
/// re-derived only once one of them is not in it): Raydium the [`RAY_NEED_EACH_WAY`] nearest initialized arrays each way
/// from the current one (it among them when it is initialized: a swap never reads an uninitialized one, so the price
/// crossing empty arrays moves nothing; review round 2), Orca the 3 arrays of a swap's sequence each way
/// (`whirl_leg_starts`)
pub fn need_starts(m: &PoolMeta, pool: &[u8], ext: Option<&[u8]>) -> Vec<i32> {
    match m.venue {
        Venue::RayClmm => [true, false].iter().flat_map(|z| ray_initialized_arrays(pool, ext, *z, RAY_NEED_EACH_WAY)).collect(),
        Venue::Whirlpool => [true, false].iter().filter_map(|z| whirl_leg_starts(pool, *z)).flatten().collect(),
        _ => vec![],
    }
}

/// Raydium CLMM: the initialized arrays each way that must stay followed before the follow set moves (half of
/// [`RAY_FOLLOW_EACH_WAY`])
pub const RAY_NEED_EACH_WAY: usize = 3;

/// `follow_starts` with each start's PDA: the keys of `held` (the arrays followed now) are reused, the others derived
pub fn follow_list(m: &PoolMeta, pool: &[u8], ext: Option<&[u8]>, held: &[(i64, Pk)]) -> Vec<(i64, Pk)> {
    follow_starts(m, pool, ext).into_iter().filter_map(|st| {
        let key = held.iter().find(|(i, _)| *i == st as i64).map(|x| x.1).or_else(|| tick_array_pda(m, st))?;
        Some((st as i64, key))
    }).collect()
}

/// Orca Whirlpool: the start indexes of the 3 tick arrays a `swap_v2` leg names (the program's own sequence,
/// `needed_starts`), the last repeated where fewer than 3 are valid (DESIGN.md §9.2)
pub fn whirl_leg_starts(pool: &[u8], a_to_b: bool) -> Option<[i32; 3]> {
    let (ts, t) = (tick_spacing(Venue::Whirlpool, pool)?, tick_current(Venue::Whirlpool, pool)?);
    // (a current tick outside the range: no real pool; its starts would overflow)
    if !(orca::MIN_TICK..=orca::MAX_TICK).contains(&t) { return None; }
    let (need, n) = orca::needed_starts(t, ts, a_to_b);
    if n == 0 { return None; }
    let mut out = [0i32; 3];
    for (i, s) in out.iter_mut().enumerate() { *s = need[i.min(n - 1)]; }
    Some(out)
}

// ------------------------------------------------------------------ a third party's swap

/// Decode a third party's `swap` / `swap_v2` on Raydium CLMM or Orca Whirlpool (exact in or exact out). Data: amount
/// u64 @8, other_amount_threshold u64 @16 (the minimum out of an exact-in swap, the maximum in of an exact-out one),
/// sqrt_price_limit u128 @24, is_base_input / amount_specified_is_input bool @40, Orca's a_to_b bool @41. A swap with
/// a price limit inside the price range may stop early (a partial fill), which a prediction of the full amount would
/// misprice: only the default limits (0, or the range's end in the swap's direction) are decoded. Accounts:
/// - Raydium `swap`: payer, amm_config, pool, input/output token accounts, input/output vaults, observation, token
///   program, tick arrays; `swap_v2` the same, then Token-2022, Memo and the two mints: pool @2, input vault @5;
/// - Orca `swap`: token program, authority, whirlpool, owner a, vault a, owner b, vault b, tick arrays, oracle (pool @2,
///   authority @1); `swap_v2`: token programs a, b, Memo, authority, whirlpool, mints a, b, ... (pool @4, authority @3)
pub fn decode_pending<'a>(venue: Venue, data: &[u8], acc: &[Pk], meta: &dyn Fn(&Pk) -> Option<&'a PoolMeta>) -> Option<PendingSwap> {
    let d: [u8; 8] = data.get(..8)?.try_into().ok()?;
    let v2 = if d == SWAP_V2 { true } else if d == SWAP { false } else { return None };
    let amount = super::u64_at(data, 8)?;
    let limit = super::u64_at(data, 16)?;
    let price_limit = u128_at(data, 24)?;
    let exact_in = *data.get(40)? != 0;
    match venue {
        Venue::RayClmm => {
            if acc.len() < if v2 { 13 } else { 9 } { return None; }
            let pool = acc[2];
            let m = meta(&pool).filter(|m| m.venue == Venue::RayClmm)?;
            let zfo = if acc[5] == m.vault0 { true } else if acc[5] == m.vault1 { false } else { return None };
            // the program's default limit: MIN + 1 (0 → 1) or MAX − 1; any limit at or past it changes nothing
            let default = if zfo { price_limit <= ray::MIN_SQRT_PRICE_X64 + 1 } else { price_limit >= ray::MAX_SQRT_PRICE_X64 - 1 };
            if price_limit != 0 && !default { return None; }
            Some(PendingSwap { pool, venue, zero_for_one: zfo, amount, exact_out: !exact_in, user: acc[0], limit })
        }
        Venue::Whirlpool => {
            let (pool_at, auth_at, n) = if v2 { (4, 3, 15) } else { (2, 1, 11) };
            if acc.len() < n { return None; }
            let pool = acc[pool_at];
            meta(&pool).filter(|m| m.venue == Venue::Whirlpool)?;
            let a_to_b = *data.get(41)? != 0;
            let default = if a_to_b { price_limit <= orca::MIN_SQRT_PRICE_X64 } else { price_limit >= orca::MAX_SQRT_PRICE_X64 };
            if price_limit != 0 && !default { return None; }
            Some(PendingSwap { pool, venue, zero_for_one: a_to_b, amount, exact_out: !exact_in, user: acc[auth_at], limit })
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// the PDAs are the programs' (venue-harness keys.rs derives the same; the fixtures' snapshots hold them by these
    /// addresses), and the discriminators are Anchor's
    #[test]
    fn discriminators_are_anchors() {
        use sha2::Digest;
        assert_eq!(SWAP, sha2::Sha256::digest(b"global:swap")[..8]);
        assert_eq!(SWAP_V2, sha2::Sha256::digest(b"global:swap_v2")[..8]);
        assert_eq!(TWO_HOP_SWAP, sha2::Sha256::digest(b"global:two_hop_swap")[..8]);
        assert_eq!(TWO_HOP_SWAP_V2, sha2::Sha256::digest(b"global:two_hop_swap_v2")[..8]);
        assert_eq!(SWAP_ROUTER_BASE_IN, sha2::Sha256::digest(b"global:swap_router_base_in")[..8]);
        assert!(is_swap(&SWAP_V2) && is_swap(&[TWO_HOP_SWAP.as_slice(), &[1, 2]].concat()) && !is_swap(&SWAP[..7]));
        assert!(!is_swap(&sha2::Sha256::digest(b"global:open_position_v2")[..8]) && !is_swap(&sha2::Sha256::digest(b"global:initialize_tick_array")[..8]));
    }

    fn ray_pool(ts: u16, tick: i32, bits: &[usize]) -> Vec<u8> {
        let mut p = vec![0u8; ray::POOL_LEN];
        p[ray::off::TICK_SPACING..ray::off::TICK_SPACING + 2].copy_from_slice(&ts.to_le_bytes());
        p[ray::off::TICK_CURRENT..ray::off::TICK_CURRENT + 4].copy_from_slice(&tick.to_le_bytes());
        for &b in bits { let o = ray::off::BITMAP + 8 * (b / 64); let w = u64::from_le_bytes(p[o..o + 8].try_into().unwrap()) | 1 << (b % 64); p[o..o + 8].copy_from_slice(&w.to_le_bytes()); }
        p
    }

    /// Review round 2 (F2's hysteresis): Raydium's arrays a quote needs are the nearest initialized ones each way, so the
    /// price crossing uninitialized arrays between them moves nothing; the current array is among them once initialized
    #[test]
    fn raydium_needs_its_initialized_arrays_only() {
        let m = PoolMeta { venue: Venue::RayClmm, pool: [1; 32], t0: [2; 32], t1: [3; 32], vault0: [4; 32], vault1: [5; 32], t0_prog: [0; 32], t1_prog: [0; 32],
            extra: vec![], flag: false };
        // spacing 10 (600 ticks an array): arrays at -1,200, 0 (bits 510, 512) and +3,000 / +6,000 (bits 517, 522) initialized
        for tick in [1_250, 1_850, 2_450] {
            let p = ray_pool(10, tick, &[510, 512, 517, 522]);
            assert_eq!(need_starts(&m, &p, None), vec![0, -1_200, 3_000, 6_000], "tick {tick}: the current array ({}) is not initialized", tick / 600 * 600);
        }
        let p = ray_pool(10, 3_100, &[510, 512, 517, 522]);
        assert_eq!(need_starts(&m, &p, None), vec![3_000, 0, -1_200, 3_000, 6_000], "the current array initialized: both ways start at it");
    }

    /// review F5: a venue's deploy check passes only on the deploy slot its port was proven on; another slot, a header
    /// that is not a programdata account's, or no account at all (the read failed) each fail it, saying why
    #[test]
    fn the_deploy_check_passes_only_the_proven_binary() {
        let header = |tag: u32, slot: u64| { let mut h = vec![0u8; 45]; h[..4].copy_from_slice(&tag.to_le_bytes()); h[4..12].copy_from_slice(&slot.to_le_bytes()); h };
        for (v, proven) in [(Venue::RayClmm, RAY_DEPLOY_SLOT), (Venue::Whirlpool, WHIRL_DEPLOY_SLOT)] {
            let e = deploy_entry(v, Some(&header(3, proven)), None);
            assert_eq!((e["ok"].as_bool(), e["last_deploy_slot"].as_u64(), e["proven_deploy_slot"].as_u64(), e["error"].is_null()), (Some(true), Some(proven), Some(proven), true));
            assert_eq!(e["programdata"].as_str(), Some(crate::tx::b58(&programdata(v)).as_str()));
            let e = deploy_entry(v, Some(&header(3, proven + 1)), None);
            assert_eq!((e["ok"].as_bool(), e["last_deploy_slot"].as_u64()), (Some(false), Some(proven + 1)), "an upgrade");
            let e = deploy_entry(v, Some(&header(2, proven)), None);
            assert!(e["ok"] == false && e["error"].as_str().is_some_and(|w| w.contains("not a programdata")), "{e}");
            let e = deploy_entry(v, None, Some("rpc: 429"));
            assert_eq!((e["ok"].as_bool(), e["error"].as_str(), e["last_deploy_slot"].clone()), (Some(false), Some("rpc: 429"), serde_json::Value::Null), "unknown fails closed");
        }
    }

    /// the scan array by array (`ray_array_bit` at every start): the reference of `ray_initialized_arrays`
    fn arrays_one_by_one(pool: &[u8], ext: Option<&[u8]>, zfo: bool, k: usize) -> Vec<i32> {
        let mut out = Vec::new();
        let (Some(ts), Some(st0)) = (tick_spacing(Venue::RayClmm, pool), current_array(Venue::RayClmm, pool)) else { return out };
        let per = ray::TICK_ARRAY_SIZE * ts as i32;
        let (lo, hi) = (ray::array_start(ray::MIN_TICK, ts), ray::array_start(ray::MAX_TICK, ts));
        let mut st = st0;
        while out.len() < k && (lo..=hi).contains(&st) {
            match ray_array_bit(pool, ext, st) { Some(true) => out.push(st), Some(false) => {} None => break }
            st = if zfo { st - per } else { st + per };
        }
        out
    }

    struct Rng(u64);
    impl Rng { fn next(&mut self) -> u64 { self.0 ^= self.0 << 13; self.0 ^= self.0 >> 7; self.0 ^= self.0 << 17; self.0 } }

    /// Review F2: the word-by-word scan answers what the array-by-array one did, on random bitmaps (empty, sparse, dense;
    /// with the extension, with an empty one, without; every tick spacing; ticks over the whole range; short bytes) and on
    /// the venue-parity snapshots, both ways, for every count asked
    #[test]
    fn the_word_scan_is_the_array_scan() {
        let mut r = Rng(0x9e37_79b9_7f4a_7c15);
        let word = |r: &mut Rng, density: u64| -> u64 {
            match density { 0 => 0, 1 => if r.next() % 16 == 0 { 1 << (r.next() % 64) } else { 0 }, 2 => if r.next() % 3 == 0 { r.next() & r.next() } else { 0 }, _ => r.next() }
        };
        let mut found = 0usize;
        for it in 0..1_500u64 {
            let ts: u16 = [1, 2, 4, 5, 8, 10, 15, 16, 20, 50, 60, 100, 120, 200][(r.next() % 14) as usize];
            let tick = (r.next() % (2 * 443_636 + 1)) as i32 - 443_636;
            let density = r.next() % 4;
            let mut pool = ray_pool(ts, tick, &[]);
            for w in 0..16 { let v = word(&mut r, density); pool[ray::off::BITMAP + 8 * w..ray::off::BITMAP + 8 * w + 8].copy_from_slice(&v.to_le_bytes()); }
            let mut ext = vec![0u8; ray::EXT_LEN];
            if it % 3 != 0 {
                for base in [ray::off::E_POSITIVE, ray::off::E_NEGATIVE] {
                    for w in 0..14 * 8 { let v = word(&mut r, density); ext[base + 8 * w..base + 8 * w + 8].copy_from_slice(&v.to_le_bytes()); }
                }
            }
            let short = &pool[..ray::off::BITMAP + 8 * (r.next() % 17) as usize];
            for (pl, e) in [(&pool[..], Some(&ext[..])), (&pool[..], None), (short, Some(&ext[..]))] {
                for k in [1usize, 6, 40] {
                    for zfo in [true, false] {
                        let (a, b) = (ray_initialized_arrays(pl, e, zfo, k), arrays_one_by_one(pl, e, zfo, k));
                        assert_eq!(a, b, "ts {ts} tick {tick} density {density} ext {} k {k} zfo {zfo}", e.is_some());
                        found += a.len();
                    }
                }
            }
        }
        // the snapshots (both venue-parity sets' Raydium pools, with their extension when it exists)
        let mut pools = 0;
        for fx in crate::quote::clmm_tests::fixtures().values().filter(|f| f.venue == Venue::RayClmm) {
            let m = crate::quote::clmm_tests::meta(fx);
            let pool = &fx.accts[&fx.pool].1;
            let ext = m.clmm_ext().and_then(|k| fx.accts.get(k)).map(|a| &a.1[..]);
            for k in [1usize, 6, 40, 1_000] {
                for zfo in [true, false] { assert_eq!(ray_initialized_arrays(pool, ext, zfo, k), arrays_one_by_one(pool, ext, zfo, k), "{} k {k} zfo {zfo}", fx.file); }
            }
            pools += 1;
        }
        assert!(found > 10_000 && pools == 10, "{found} {pools}");
    }

    /// Raydium: the initialized arrays by the default bitmap, both ways from the current one, in walk order; the current
    /// array followed whether or not it is initialized; beyond the default range only with the extension
    #[test]
    fn raydium_arrays_by_the_bitmap() {
        // tick spacing 10: an array spans 600 ticks; array index i has bit i + 512
        let p = ray_pool(10, 1_250, &[510, 512, 514, 515, 600]);
        assert_eq!(current_array(Venue::RayClmm, &p), Some(1_200));
        assert_eq!(ray_initialized_arrays(&p, None, true, 6), vec![1_200, 0, -1_200], "the current array (bit 514) first");
        assert_eq!(ray_initialized_arrays(&p, None, false, 6), vec![1_200, 1_800, 88 * 600]);
        assert_eq!(ray_initialized_arrays(&p, None, false, 2), vec![1_200, 1_800]);
        let m = PoolMeta { venue: Venue::RayClmm, pool: [1; 32], t0: [2; 32], t1: [3; 32], vault0: [4; 32], vault1: [5; 32], t0_prog: [0; 32], t1_prog: [0; 32],
            extra: vec![], flag: false };
        assert_eq!(follow_starts(&m, &p, None), vec![-1_200, 0, 1_200, 1_800, 52_800]);
        // the current array not initialized: still followed, the walk starts at the next initialized one
        let p = ray_pool(10, 700, &[512, 514]);
        assert_eq!(follow_starts(&m, &p, None), vec![0, 600, 1_200]);
        // beyond the default range (array index 512 and up): None without the extension
        let far = ray_pool(1, 60 * 600, &[]);
        assert_eq!(ray_array_bit(&far, None, 60 * 600), None);
        let mut ext = vec![0u8; ray::EXT_LEN];
        // positive bitmap 0, bit 88: start 30,720 + 88·60
        ext[ray::off::E_POSITIVE + 8 + 3] = 1; // word 1 (bits 64..127), bit 24
        assert_eq!(ray_array_bit(&far, Some(&ext), 30_720 + 88 * 60), Some(true));
        assert_eq!(ray_array_bit(&far, Some(&ext), 30_720 + 87 * 60), Some(false));
    }

    /// Orca: the current array and two each way (three above), valid starts only; the leg's 3 arrays are the program's
    /// own sequence, the last repeated near the range's end
    #[test]
    fn whirlpool_arrays_and_the_legs_sequence() {
        let mut p = vec![0u8; orca::POOL_LEN];
        p[orca::off::TICK_SPACING..orca::off::TICK_SPACING + 2].copy_from_slice(&64u16.to_le_bytes());
        p[orca::off::TICK_CURRENT..orca::off::TICK_CURRENT + 4].copy_from_slice(&(-10_000i32).to_le_bytes());
        let per = 88 * 64;
        let m = PoolMeta { venue: Venue::Whirlpool, pool: [1; 32], t0: [2; 32], t1: [3; 32], vault0: [4; 32], vault1: [5; 32], t0_prog: [0; 32], t1_prog: [0; 32],
            extra: vec![], flag: false };
        let cur = (-10_000i32).div_euclid(per) * per;
        assert_eq!(follow_starts(&m, &p, None), (-2..=3).map(|k| cur + k * per).collect::<Vec<_>>());
        assert_eq!(whirl_leg_starts(&p, true), Some([cur, cur - per, cur - 2 * per]));
        assert_eq!(whirl_leg_starts(&p, false), Some([cur, cur + per, cur + 2 * per]));
        // near the array's end, b→a starts one array later
        p[orca::off::TICK_CURRENT..orca::off::TICK_CURRENT + 4].copy_from_slice(&(cur + per - 10).to_le_bytes());
        assert_eq!(whirl_leg_starts(&p, false), Some([cur + per, cur + 2 * per, cur + 3 * per]));
        // a splash pool (an array spans the range): a→b has two valid starts (0 and the one below the range's start,
        // `valid_start`), the last repeated
        p[orca::off::TICK_SPACING..orca::off::TICK_SPACING + 2].copy_from_slice(&32_896u16.to_le_bytes());
        p[orca::off::TICK_CURRENT..orca::off::TICK_CURRENT + 4].copy_from_slice(&0i32.to_le_bytes());
        let per = 88 * 32_896;
        assert_eq!(whirl_leg_starts(&p, true), Some([0, -per, -per]));
        assert_eq!(whirl_leg_starts(&p, false), Some([0, 0, 0]), "b→a: one valid start");
    }

    /// a third party's swaps: direction from the input vault (Raydium) or the a_to_b flag (Orca); a price limit inside
    /// the range is not decoded (a partial fill)
    #[test]
    fn third_party_swaps_decode() {
        let ray = PoolMeta { venue: Venue::RayClmm, pool: [1; 32], t0: [2; 32], t1: [3; 32], vault0: [4; 32], vault1: [5; 32], t0_prog: [0; 32], t1_prog: [0; 32],
            extra: vec![], flag: false };
        let whirl = PoolMeta { venue: Venue::Whirlpool, pool: [11; 32], ..ray.clone() };
        let meta = |k: &Pk| if *k == ray.pool { Some(&ray) } else if *k == whirl.pool { Some(&whirl) } else { None };
        let data = |disc: [u8; 8], limit: u128, exact_in: bool, a_to_b: bool| {
            let mut d = disc.to_vec();
            d.extend(1_000u64.to_le_bytes()); d.extend(7u64.to_le_bytes()); d.extend(limit.to_le_bytes()); d.push(exact_in as u8); d.push(a_to_b as u8); d
        };
        let mut acc: Vec<Pk> = (0..13).map(|i| [100 + i as u8; 32]).collect();
        acc[2] = ray.pool;
        acc[5] = ray.vault1;
        let s = decode_pending(Venue::RayClmm, &data(SWAP_V2, 0, true, false), &acc, &meta).unwrap();
        assert_eq!((s.zero_for_one, s.amount, s.limit, s.exact_out, s.user), (false, 1_000, 7, false, acc[0]));
        assert!(decode_pending(Venue::RayClmm, &data(SWAP_V2, 1 << 70, true, false), &acc, &meta).is_none(), "a price limit inside the range");
        assert!(decode_pending(Venue::RayClmm, &data(SWAP_V2, ray::MAX_SQRT_PRICE_X64 - 1, false, false), &acc, &meta).unwrap().exact_out);
        let mut acc: Vec<Pk> = (0..15).map(|i| [100 + i as u8; 32]).collect();
        acc[4] = whirl.pool;
        let s = decode_pending(Venue::Whirlpool, &data(SWAP_V2, orca::MIN_SQRT_PRICE_X64, true, true), &acc, &meta).unwrap();
        assert_eq!((s.zero_for_one, s.user), (true, acc[3]));
        acc[4] = [0; 32];
        assert!(decode_pending(Venue::Whirlpool, &data(SWAP_V2, 0, true, true), &acc, &meta).is_none(), "not a pool of ours");
    }
}

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
    // in i64: no input overflows
    let ts = tick_spacing(Venue::RayClmm, pool)? as i64;
    let start = start as i64;
    let per = ray::TICK_ARRAY_SIZE as i64 * ts;
    let boundary = per * 512;
    if (-boundary..boundary).contains(&start) {
        let b = (start.div_euclid(per) + 512) as usize;
        return crate::venues::u64_at(pool, ray::off::BITMAP + 8 * (b / 64)).map(|w| w >> (b % 64) & 1 == 1);
    }
    let ext = ext?;
    let mut offset = start.abs() / boundary - 1;
    if start < 0 && start.abs() % boundary == 0 { offset -= 1; }
    if !(0..14).contains(&offset) { return Some(false); }
    let m = start.abs() % boundary;
    let mut bit = m / per;
    if start < 0 && m != 0 { bit = 512 - bit; }
    if !(0..512).contains(&bit) { return Some(false); }
    let base = (if start < 0 { ray::off::E_NEGATIVE } else { ray::off::E_POSITIVE }) + 64 * offset as usize;
    let bit = bit as usize;
    crate::venues::u64_at(ext, base + 8 * (bit / 64)).map(|w| w >> (bit % 64) & 1 == 1)
}

/// Raydium CLMM: the start indexes of up to `k` initialized tick arrays from the current tick's array (inclusive) in the
/// swap's direction, in walk order, by the bitmaps (`ext`: the extension's bytes when it exists). Stops at the tick
/// range's end, or where the default bitmap ends and no extension is given
pub fn ray_initialized_arrays(pool: &[u8], ext: Option<&[u8]>, zfo: bool, k: usize) -> Vec<i32> {
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
    }

    fn ray_pool(ts: u16, tick: i32, bits: &[usize]) -> Vec<u8> {
        let mut p = vec![0u8; ray::POOL_LEN];
        p[ray::off::TICK_SPACING..ray::off::TICK_SPACING + 2].copy_from_slice(&ts.to_le_bytes());
        p[ray::off::TICK_CURRENT..ray::off::TICK_CURRENT + 4].copy_from_slice(&tick.to_le_bytes());
        for &b in bits { let o = ray::off::BITMAP + 8 * (b / 64); let w = u64::from_le_bytes(p[o..o + 8].try_into().unwrap()) | 1 << (b % 64); p[o..o + 8].copy_from_slice(&w.to_le_bytes()); }
        p
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

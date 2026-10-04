//! Swap instruction builders for the five venues, byte for byte the engine's (`src/build.rs::leg`, which arbed verified
//! against real on-chain swaps): PumpSwap `sell` / `buy_exact_quote_in`, Raydium CPMM `swap_base_input`, Raydium AMM v4
//! `swap_base_in_v2` (tag 16), Meteora DLMM `swap2`, Meteora DAMM v2 `swap`. The fetcher uses the same builders to list
//! the accounts a pool's snapshot must hold, so the fixture and the instruction can never disagree.
use crate::keys::{self, *};
use serde::{Deserialize, Serialize};
use solana_account::Account;
use solana_address::Address;
use solana_instruction::{AccountMeta, Instruction};
use std::collections::HashMap;

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
pub enum Venue {
    #[serde(rename = "PumpSwap")] PumpSwap,
    #[serde(rename = "RayCPMM")] RayCpmm,
    #[serde(rename = "RayAMMv4")] RayAmmV4,
    #[serde(rename = "DLMM")] Dlmm,
    #[serde(rename = "DAMMv2")] DammV2,
}

impl Venue {
    pub const ALL: [Venue; 5] = [Venue::PumpSwap, Venue::RayCpmm, Venue::RayAmmV4, Venue::Dlmm, Venue::DammV2];
    pub fn name(&self) -> &'static str {
        match self { Venue::PumpSwap => "PumpSwap", Venue::RayCpmm => "RayCPMM", Venue::RayAmmV4 => "RayAMMv4", Venue::Dlmm => "DLMM", Venue::DammV2 => "DAMMv2" }
    }
    pub fn parse(s: &str) -> Option<Venue> { Venue::ALL.into_iter().find(|v| v.name() == s.trim()) }
    pub fn program(&self) -> Address {
        match self { Venue::PumpSwap => PUMPSWAP, Venue::RayCpmm => RAYCPMM, Venue::RayAmmV4 => RAYAMMV4, Venue::Dlmm => DLMM, Venue::DammV2 => DAMMV2 }
    }
}

/// Direction in the pool's own token order (see `pool_tokens`): ZeroForOne spends token 0.
/// PumpSwap: ZeroForOne = `sell` (base in), OneForZero = `buy_exact_quote_in` (quote in).
/// DLMM: ZeroForOne = X in (swap_for_y). DAMM v2: ZeroForOne = a in. AMM v4: coin in. CPMM: mint0 in.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum Dir { ZeroForOne, OneForZero }

impl Dir {
    pub const BOTH: [Dir; 2] = [Dir::ZeroForOne, Dir::OneForZero];
    pub fn zfo(&self) -> bool { *self == Dir::ZeroForOne }
    pub fn from_zfo(z: bool) -> Dir { if z { Dir::ZeroForOne } else { Dir::OneForZero } }
    pub fn short(&self) -> &'static str { if self.zfo() { "0->1" } else { "1->0" } }
}

/// Read-only account lookup (the fixture's account map; the fetcher's partial maps).
pub trait View { fn acct(&self, k: &Address) -> Option<&Account>; }
impl View for HashMap<Address, Account> { fn acct(&self, k: &Address) -> Option<&Account> { self.get(k) } }

fn w(k: Address) -> AccountMeta { AccountMeta::new(k, false) }
fn r(k: Address) -> AccountMeta { AccountMeta::new_readonly(k, false) }
fn s(k: Address) -> AccountMeta { AccountMeta::new(k, true) }

pub fn pk_at(d: &[u8], o: usize) -> Option<Address> { d.get(o..o + 32).map(|b| Address::new_from_array(b.try_into().unwrap())) }
pub fn u64_at(d: &[u8], o: usize) -> Option<u64> { d.get(o..o + 8).map(|b| u64::from_le_bytes(b.try_into().unwrap())) }
pub fn i32_at(d: &[u8], o: usize) -> Option<i32> { d.get(o..o + 4).map(|b| i32::from_le_bytes(b.try_into().unwrap())) }
pub fn token_amount(d: &[u8]) -> Option<u64> { if d.len() >= 72 { u64_at(d, 64) } else { None } }

const PUMP_SELL: [u8; 8] = [0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad];
const PUMP_BUY_EXACT_QUOTE_IN: [u8; 8] = [0xc6, 0x2e, 0x15, 0x52, 0xb4, 0xd9, 0xe8, 0x70];
const CPMM_SWAP_BASE_INPUT: [u8; 8] = [0x8f, 0xbe, 0x5a, 0xda, 0xc4, 0x1e, 0x33, 0xde];
const DLMM_SWAP2: [u8; 8] = [0x41, 0x4b, 0x3f, 0x4c, 0xeb, 0x5b, 0x5b, 0x88];
const DAMMV2_SWAP: [u8; 8] = [0xf8, 0xc6, 0x9e, 0x91, 0xe1, 0x75, 0x87, 0xc8];
const AMMV4_SWAP_BASE_IN_V2: u8 = 16;

/// token 0 / token 1 and their pool vaults, in the program's own order
#[derive(Clone, Copy, Debug)]
pub struct PoolTokens { pub t0: Address, pub t1: Address, pub vault0: Address, pub vault1: Address }

pub fn pool_tokens(venue: Venue, d: &[u8]) -> Option<PoolTokens> {
    let (a, b, c, e) = match venue {
        Venue::RayAmmV4 => (400, 432, 336, 368),
        Venue::RayCpmm => (168, 200, 72, 104),
        Venue::PumpSwap => (43, 75, 139, 171),
        Venue::Dlmm => (88, 120, 152, 184),
        Venue::DammV2 => (168, 200, 232, 264),
    };
    Some(PoolTokens { t0: pk_at(d, a)?, t1: pk_at(d, b)?, vault0: pk_at(d, c)?, vault1: pk_at(d, e)? })
}

/// What a built swap spends from and delivers into.
#[derive(Clone, Debug)]
pub struct SwapIx {
    pub ix: Instruction,
    pub mint_in: Address,
    pub mint_out: Address,
    pub prog_in: Address,
    pub prog_out: Address,
    pub user_in: Address,
    pub user_out: Address,
    /// DLMM: the bin-array indices passed, in order
    pub dlmm_arrays: Vec<i64>,
}

#[derive(Clone, Debug)]
pub struct BuildOpts {
    pub min_out: u64,
    /// DLMM: at most this many bin arrays (the engine passes <= 5; the harness default passes every fetched array with
    /// liquidity in the swap direction, up to this cap)
    pub dlmm_max_arrays: usize,
    /// DLMM: pass exactly these bin-array indices, in this order (pin tests)
    pub dlmm_arrays: Option<Vec<i64>>,
}
impl Default for BuildOpts { fn default() -> Self { BuildOpts { min_out: 1, dlmm_max_arrays: 12, dlmm_arrays: None } } }

/// the token program owning a mint (Tokenkeg when the mint is not in the view yet: fetcher round 1)
pub fn mint_program(v: &impl View, mint: &Address) -> Address { v.acct(mint).map(|a| a.owner).unwrap_or(TOKEN) }

pub fn build_swap(venue: Venue, pool: &Address, v: &impl View, user: &Address, dir: Dir, amount_in: u64, o: &BuildOpts) -> Result<SwapIx, String> {
    let pa = v.acct(pool).ok_or("pool account missing")?;
    if pa.owner != venue.program() { return Err(format!("pool owner {} != {}", pa.owner, venue.program())); }
    let d = &pa.data;
    let t = pool_tokens(venue, d).ok_or("pool account too short")?;
    let zfo = dir.zfo();
    let (tin, tout) = if zfo { (t.t0, t.t1) } else { (t.t1, t.t0) };
    let (p0, p1) = (mint_program(v, &t.t0), mint_program(v, &t.t1));
    let (pin, pout) = if zfo { (p0, p1) } else { (p1, p0) };
    let (user_in, user_out) = (ata(user, &tin, &pin), ata(user, &tout, &pout));
    let amount = amount_in.to_le_bytes();
    let min_out = o.min_out.to_le_bytes();
    let mut dlmm_arrays = vec![];
    let (program, accounts, data) = match venue {
        Venue::RayAmmV4 => {
            if p0 != TOKEN || p1 != TOKEN { return Err("ammv4: token-2022 not supported by swap_base_in_v2".into()); }
            let nonce = u64_at(d, 8).ok_or("ammv4 pool short")?;
            let auth = u8::try_from(nonce).ok()
                .and_then(|n| Address::create_program_address(&[b"amm authority", &[n]], &RAYAMMV4).ok())
                .unwrap_or_else(|| pda(&[b"amm authority"], &RAYAMMV4).0);
            let acc = vec![r(TOKEN), w(*pool), r(auth), w(t.vault0), w(t.vault1), w(user_in), w(user_out), s(*user)];
            let mut data = vec![AMMV4_SWAP_BASE_IN_V2];
            data.extend(amount); data.extend(min_out);
            (RAYAMMV4, acc, data)
        }
        Venue::RayCpmm => {
            let cfg = pk_at(d, 8).ok_or("cpmm pool short")?;
            let obs = pk_at(d, 296).ok_or("cpmm pool short")?;
            let (vin, vout) = if zfo { (t.vault0, t.vault1) } else { (t.vault1, t.vault0) };
            let acc = vec![s(*user), r(RAYCPMM_AUTHORITY), r(cfg), w(*pool), w(user_in), w(user_out), w(vin), w(vout),
                r(pin), r(pout), r(tin), r(tout), w(obs)];
            let mut data = CPMM_SWAP_BASE_INPUT.to_vec();
            data.extend(amount); data.extend(min_out);
            (RAYCPMM, acc, data)
        }
        Venue::PumpSwap => {
            let (acc, data) = pump_accounts(pool, d, v, user, &t, p0, p1, zfo, amount_in, o.min_out)?;
            (PUMPSWAP, acc, data)
        }
        Venue::Dlmm => {
            let oracle = pk_at(d, 552).ok_or("dlmm pool short")?;
            let ext = dlmm_bitmap_extension(pool);
            let ext = if v.acct(&ext).is_some() { w(ext) } else { r(DLMM) };
            dlmm_arrays = match &o.dlmm_arrays { Some(l) => l.clone(), None => dlmm_arrays_for_swap(pool, d, v, zfo, o.dlmm_max_arrays) };
            let mut acc = vec![w(*pool), ext, w(t.vault0), w(t.vault1), w(user_in), w(user_out), r(t.t0), r(t.t1), w(oracle),
                r(DLMM), s(*user), r(p0), r(p1), r(MEMO), r(DLMM_EVENT_AUTHORITY), r(DLMM)];
            for i in &dlmm_arrays { acc.push(w(dlmm_bin_array(pool, *i))); }
            let mut data = DLMM_SWAP2.to_vec();
            data.extend(amount); data.extend(min_out);
            data.extend(0u32.to_le_bytes()); // remaining_accounts_info: no transfer-hook slices
            (DLMM, acc, data)
        }
        Venue::DammV2 => {
            // vaults and mints in the POOL's order whatever the direction; referral None = the program id
            let acc = vec![r(DAMMV2_POOL_AUTHORITY), w(*pool), w(user_in), w(user_out), w(t.vault0), w(t.vault1), r(t.t0), r(t.t1),
                s(*user), r(p0), r(p1), r(DAMMV2), r(DAMMV2_EVENT_AUTHORITY), r(DAMMV2)];
            let mut data = DAMMV2_SWAP.to_vec();
            data.extend(amount); data.extend(min_out);
            (DAMMV2, acc, data)
        }
    };
    Ok(SwapIx { ix: Instruction { program_id: program, accounts, data }, mint_in: tin, mint_out: tout, prog_in: pin, prog_out: pout,
        user_in, user_out, dlmm_arrays })
}

/// PumpSwap GlobalConfig: the fee recipients (mayhem pools use the reserved set) and the buyback recipients
pub struct PumpGlobal { pub disable_flags: u8, pub protocol: Vec<Address>, pub reserved: Vec<Address>, pub buyback: Vec<Address> }
pub fn decode_pump_global(g: &[u8]) -> Option<PumpGlobal> {
    if g.len() < 643 + 8 * 32 || g[..8] != [0x95, 0x08, 0x9c, 0xca, 0xa0, 0xfc, 0xb0, 0xd9] { return None; }
    let keys = |at: usize, n: usize| -> Vec<Address> { (0..n).filter_map(|i| pk_at(g, at + 32 * i)).filter(|k| k.as_ref() != [0u8; 32]).collect() };
    let mut reserved = keys(385, 1);
    reserved.extend(keys(418, 7));
    Some(PumpGlobal { disable_flags: g[56], protocol: keys(57, 8), reserved, buyback: keys(643, 8) })
}

/// PumpSwap pool's `creator` == the pump.fun "pool-authority" PDA of its base mint (canonical, migrated pool):
/// returns that PDA's bump, or 0 when the pool is not canonical (the sizing descriptor's `bump` byte, DESIGN §4.3)
pub fn pump_canonical_bump(pool_data: &[u8]) -> u8 {
    let (Some(creator), Some(base)) = (pk_at(pool_data, 11), pk_at(pool_data, 43)) else { return 0 };
    let (k, bump) = pda(&[b"pool-authority", base.as_ref()], &PUMP_FUN);
    if k == creator { bump } else { 0 }
}

#[allow(clippy::too_many_arguments)]
fn pump_accounts(pool: &Address, d: &[u8], v: &impl View, user: &Address, t: &PoolTokens, base_prog: Address, quote_prog: Address,
                 sell: bool, amount: u64, min_out: u64) -> Result<(Vec<AccountMeta>, Vec<u8>), String> {
    let g = v.acct(&PUMP_GLOBAL_CONFIG).and_then(|a| decode_pump_global(&a.data)).ok_or("pump: GlobalConfig missing")?;
    if g.disable_flags & if sell { 1 << 4 } else { 1 << 3 } != 0 { return Err(format!("pump: {} disabled", if sell { "sell" } else { "buy" })); }
    let creator = pk_at(d, 211).ok_or("pump pool short")?;
    let mayhem = d.get(243) == Some(&1);
    let cashback = d.get(244) == Some(&1);
    let fees = if mayhem { &g.reserved } else { &g.protocol };
    if fees.is_empty() || g.buyback.is_empty() { return Err("pump: no fee recipients".into()); }
    let pick = pool.as_ref()[0] as usize;
    let fee_recipient = fees[pick % fees.len()];
    let buyback = g.buyback[pick % g.buyback.len()];
    let creator_auth = pda(&[b"creator_vault", creator.as_ref()], &PUMPSWAP).0;
    let uva = pda(&[b"user_volume_accumulator", user.as_ref()], &PUMPSWAP).0;
    let quote = t.t1;
    let quote_ata = |owner: &Address| ata(owner, &quote, &quote_prog);
    let mut acc = vec![w(*pool), s(*user), r(PUMP_GLOBAL_CONFIG), r(t.t0), r(t.t1),
        w(ata(user, &t.t0, &base_prog)), w(ata(user, &t.t1, &quote_prog)), w(t.vault0), w(t.vault1),
        r(fee_recipient), w(quote_ata(&fee_recipient)), r(base_prog), r(quote_prog), r(SYSTEM), r(ATA_PROGRAM),
        r(PUMP_EVENT_AUTHORITY), r(PUMPSWAP), w(quote_ata(&creator_auth)), r(creator_auth)];
    if !sell { acc.push(r(PUMP_GLOBAL_VOLUME_ACCUMULATOR)); acc.push(w(uva)); }
    acc.push(r(PUMP_FEE_CONFIG));
    acc.push(r(PUMP_FEE_PROGRAM));
    let has_v2 = creator.as_ref() != [0u8; 32];
    // the engine drops the payer-seeded cashback block in front of pool_v2 (the program refuses it, 6062 InvalidPoolV2)
    if cashback && !has_v2 { acc.push(w(quote_ata(&uva))); if sell { acc.push(w(uva)); } }
    if has_v2 { acc.push(r(pda(&[b"pool-v2", t.t0.as_ref()], &PUMPSWAP).0)); }
    acc.push(r(buyback));
    acc.push(w(quote_ata(&buyback)));
    let mut data = if sell { PUMP_SELL.to_vec() } else { PUMP_BUY_EXACT_QUOTE_IN.to_vec() };
    data.extend(amount.to_le_bytes());
    data.extend(min_out.to_le_bytes());
    Ok((acc, data))
}

/// DLMM bin_array_bitmap (array indices -512..=511, bit = index + 512): does array `i` hold liquidity?
pub fn dlmm_bitmap_bit(pool_data: &[u8], i: i64) -> bool {
    if !(-512..=511).contains(&i) { return false; }
    let b = (i + 512) as usize;
    u64_at(pool_data, 584 + 8 * (b / 64)).is_some_and(|word| word >> (b % 64) & 1 == 1)
}

/// The bin arrays a swap walks, in its order: from the active bin's array onward in the swap direction (X in: down),
/// every array whose bitmap bit says it holds liquidity and that the view holds, up to `max`.
pub fn dlmm_arrays_for_swap(pool: &Address, d: &[u8], v: &impl View, swap_for_y: bool, max: usize) -> Vec<i64> {
    let Some(active) = i32_at(d, 76) else { return vec![] };
    let c = dlmm_array_index(active);
    let mut out = vec![];
    let mut i = c;
    while (-512..=511).contains(&i) && out.len() < max {
        if dlmm_bitmap_bit(d, i) && v.acct(&dlmm_bin_array(pool, i)).is_some() { out.push(i); }
        i += if swap_for_y { -1 } else { 1 };
    }
    out
}

/// DLMM arrays the fetcher snapshots: the active array +-3, plus the first 4 arrays with liquidity on each side.
pub fn dlmm_fixture_arrays(d: &[u8]) -> Vec<i64> {
    let Some(active) = i32_at(d, 76) else { return vec![] };
    let c = dlmm_array_index(active);
    let mut s: Vec<i64> = (c - 3..=c + 3).collect();
    for step in [-1i64, 1] {
        let (mut i, mut n) = (c + step, 0);
        while (-512..=511).contains(&i) && n < 4 {
            if dlmm_bitmap_bit(d, i) { s.push(i); n += 1; }
            i += step;
        }
    }
    s.sort();
    s.dedup();
    s
}

/// Keys derived from the test user (never snapshotted: the loader creates them).
pub fn user_keys(venue: Venue, t: &PoolTokens, p0: &Address, p1: &Address, user: &Address) -> Vec<Address> {
    let mut u = vec![*user, ata(user, &t.t0, p0), ata(user, &t.t1, p1)];
    if venue == Venue::PumpSwap {
        let uva = pda(&[b"user_volume_accumulator", user.as_ref()], &PUMPSWAP).0;
        u.push(uva);
        u.push(ata(&uva, &t.t1, p1));
    }
    u
}

/// Every non-program, non-user account a pool's snapshot must hold: the accounts of both swap directions, the mints
/// (to create the user's token accounts), PumpSwap's configs, DLMM's bin arrays and bitmap extension.
pub fn fixture_keys(venue: Venue, pool: &Address, v: &impl View, user: &Address) -> Result<Vec<Address>, String> {
    let pa = v.acct(pool).ok_or("pool account missing")?;
    let t = pool_tokens(venue, &pa.data).ok_or("pool account too short")?;
    let mut keys: Vec<Address> = vec![*pool, t.t0, t.t1, t.vault0, t.vault1];
    match venue {
        Venue::PumpSwap => keys.extend([PUMP_GLOBAL_CONFIG, PUMP_FEE_CONFIG]),
        Venue::Dlmm => {
            keys.push(dlmm_bitmap_extension(pool));
            keys.extend(dlmm_fixture_arrays(&pa.data).into_iter().map(|i| dlmm_bin_array(pool, i)));
        }
        _ => {}
    }
    for dir in Dir::BOTH {
        let sw = build_swap(venue, pool, v, user, dir, 1, &BuildOpts::default())?;
        keys.extend(sw.ix.accounts.iter().map(|m| m.pubkey));
    }
    let skip = user_keys(venue, &t, &mint_program(v, &t.t0), &mint_program(v, &t.t1), user);
    let mut out = vec![];
    for k in keys {
        if keys::is_program(&k) || skip.contains(&k) || out.contains(&k) { continue; }
        out.push(k);
    }
    Ok(out)
}

/// Token-2022 TransferFeeConfig (extension type 1) of a mint: the (older, newer) transfer_fee_basis_points, or None
/// when the mint has no such extension (SPL Token mints never do). Mint base 82 bytes, padding to 165, account type at
/// 165, then TLV entries (u16 type, u16 length, value) from 166.
pub fn transfer_fee_bps(mint: &[u8]) -> Option<(u16, u16)> {
    let mut o = 166;
    while o + 4 <= mint.len() {
        let (t, l) = (u16::from_le_bytes([mint[o], mint[o + 1]]), u16::from_le_bytes([mint[o + 2], mint[o + 3]]) as usize);
        if t == 0 { return None; }
        if t == 1 {
            // config authority 32, withdraw authority 32, withheld u64, older {epoch u64, max u64, bps u16}, newer {...}
            let v = mint.get(o + 4..o + 4 + l)?;
            let bps = |at: usize| v.get(at..at + 2).map(|b| u16::from_le_bytes([b[0], b[1]]));
            return Some((bps(72 + 16)?, bps(72 + 18 + 16)?));
        }
        o += 4 + l;
    }
    None
}

/// Does either of the pool's mints charge a nonzero Token-2022 transfer fee? (sizing aborts such legs: Abort::TransferFee)
pub fn pool_has_transfer_fee(v: &impl View, t: &PoolTokens) -> bool {
    [t.t0, t.t1].iter().any(|m| v.acct(m).and_then(|a| transfer_fee_bps(&a.data)).is_some_and(|(a, b)| a != 0 || b != 0))
}

//! Transaction builder: an engine round trip -> the real nexus-arb-v2 transaction, signed. Ported from arbed:
//! src/execution/nexus-v2.ts (instruction layout), src/execution/builder.ts (instruction order, v0 compile with
//! lookup tables, the nonce guard) and src/venues/encoders.ts (each venue's swap, from the synthetic templates and
//! buildSwap's rules, which arbed verified against real on-chain swaps). Only arb-lab's four venues.
//!
//! Instruction order (PLAN WP-06 item 1, `bundle_ixs`): CU limit > SetLoadedAccountsDataSizeLimit > [create the mid
//! token's ATA (idempotent), only when the wallet holds none] > nexus-v2 route > [CloseAccount of that ATA to the payer,
//! only when this transaction created it] > tip (a top-level System transfer, last). No CU price: a bundle pays its tip
//! only. The create's rent comes back in the same transaction (the close sends every lamport of the account to the
//! payer), so a trade through a token the wallet holds no account for is rent-neutral, and a route that fails reverts
//! the create too. The route's legs chain balances on chain: leg 1 spends `amount_in` of the quote account, every later
//! leg spends what the previous one delivered (the mid account, created empty, ends empty again), and the program fails
//! the whole transaction (0x4e580002) unless the quote account ends at least `min_profit` above where it started.
use crate::pda::{self, ATA_PROGRAM, SYSTEM_PROGRAM, TOKEN_PROGRAM};
use crate::tx::{pk, Pk, COMPUTE_BUDGET};
use crate::venues::{dlmm, i32_at, pk_at, u64_at, PoolMeta, Venue};
use rustc_hash::FxHashMap as HashMap;
use std::sync::LazyLock;

static MEMO: LazyLock<Pk> = LazyLock::new(|| pk("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr"));
static SYSVAR_RECENT_BLOCKHASHES: LazyLock<Pk> = LazyLock::new(|| pk("SysvarRecentB1ockHashes11111111111111111111"));
pub static PUMP_GLOBAL_CONFIG: LazyLock<Pk> = LazyLock::new(|| pk("ADyA8hdefvWN2dbGGWFotbzWxrAvLW83WG6QCVXvJKqw"));
static PUMP_EVENT_AUTHORITY: LazyLock<Pk> = LazyLock::new(|| pk("GS4CU59F31iL7aR2Q8zVS8DRrcRnXX1yjQ66TqNVQnaR"));
static PUMP_GLOBAL_VOLUME_ACCUMULATOR: LazyLock<Pk> = LazyLock::new(|| pk("C2aFPdENg4A2HQsmrd5rTw5TaYBX5Ku887cWjbFKtZpw"));
static PUMP_FEE_PROGRAM: LazyLock<Pk> = LazyLock::new(|| pk("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"));
static RAYCPMM_AUTHORITY: LazyLock<Pk> = LazyLock::new(|| pk("GpMZbSM2GgvTKHJirzeGfMFoaZ8UR2X7F4v8vHTvxFbL"));
static DLMM_EVENT_AUTHORITY: LazyLock<Pk> = LazyLock::new(|| pda::find_program_address(&[b"__event_authority"], &crate::venues::DLMM).0);
/// Meteora DAMM v2 (cp-amm): the pool authority (one for every pool) and the Anchor event authority
static DAMMV2_POOL_AUTHORITY: LazyLock<Pk> = LazyLock::new(|| pk("HLnpSz9h2S4hiLQ43rnSD9XkcUThA7B8hQMKmDaiTLcC"));
static DAMMV2_EVENT_AUTHORITY: LazyLock<Pk> = LazyLock::new(|| pk("3rmHSu74h1ZcmAisVcWerTCiRDQbUrBKmcwptYGjHfet"));
const DAMMV2_SWAP: [u8; 8] = [0xf8, 0xc6, 0x9e, 0x91, 0xe1, 0x75, 0x87, 0xc8];

const PUMP_SELL: [u8; 8] = [0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad];
const PUMP_BUY_EXACT_QUOTE_IN: [u8; 8] = [0xc6, 0x2e, 0x15, 0x52, 0xb4, 0xd9, 0xe8, 0x70];
const CPMM_SWAP_BASE_INPUT: [u8; 8] = [0x8f, 0xbe, 0x5a, 0xda, 0xc4, 0x1e, 0x33, 0xde];
const DLMM_SWAP2: [u8; 8] = [0x41, 0x4b, 0x3f, 0x4c, 0xeb, 0x5b, 0x5b, 0x88];
const AMMV4_SWAP_BASE_IN_V2: u8 = 16;
/// Raydium CLMM's and Orca Whirlpool's `swap_v2` (Anchor `global:swap_v2`, the same name in both)
const CLMM_SWAP_V2: [u8; 8] = crate::venues::clmm::SWAP_V2;
/// v0 transaction size limit, and the runtime's account-lock limit
pub const MAX_TX_BYTES: usize = 1232;
pub const MAX_LOCKS: usize = 64;
/// the runtime's largest loaded-accounts data size (64 MiB, the default when a transaction sets none)
pub const MAX_LOADED_DATA: u32 = 64 * 1024 * 1024;
/// nexus-arb-v2 errors (ERR_BASE 0x4e580000)
pub const ERR_PROFIT: u32 = 0x4e58_0002;
/// v2 layout: n_accounts shares its byte with the NATIVE_IN / NATIVE_OUT flags (bits 7 and 6)
pub const V2_MAX_LEG_ACCOUNTS: usize = 63;

#[derive(Clone, Debug, PartialEq)]
pub struct Meta { pub key: Pk, pub signer: bool, pub writable: bool }
fn w(key: Pk) -> Meta { Meta { key, signer: false, writable: true } }
fn r(key: Pk) -> Meta { Meta { key, signer: false, writable: false } }
fn s(key: Pk) -> Meta { Meta { key, signer: true, writable: true } }

#[derive(Clone, Debug)]
pub struct Ix { pub program: Pk, pub accounts: Vec<Meta>, pub data: Vec<u8> }

/// PumpSwap GlobalConfig (949 bytes, disc 95089ccaa0fcb0d9): disable_flags @56 (bit 3 buy, bit 4 sell),
/// protocol_fee_recipients[8] @57, reserved_fee_recipient @385 + [7] @418 (mayhem pools), buyback[8] @643
#[derive(Clone, Debug, PartialEq)]
pub struct PumpGlobal { pub disable_flags: u8, pub protocol: Vec<Pk>, pub reserved: Vec<Pk>, pub buyback: Vec<Pk> }

pub fn decode_pump_global(d: &[u8]) -> Option<PumpGlobal> {
    if d.len() < 643 + 8 * 32 || d[..8] != [0x95, 0x08, 0x9c, 0xca, 0xa0, 0xfc, 0xb0, 0xd9] { return None; }
    let keys = |at: usize, n: usize| -> Vec<Pk> { (0..n).filter_map(|i| pk_at(d, at + 32 * i)).filter(|k| *k != [0u8; 32]).collect() };
    let mut reserved = keys(385, 1);
    reserved.extend(keys(418, 7));
    Some(PumpGlobal { disable_flags: d[56], protocol: keys(57, 8), reserved, buyback: keys(643, 8) })
}

/// One leg for the v2 program: the venue's own swap, unchanged, plus the account the leg delivers into.
#[derive(Clone, Debug)]
pub struct Leg { pub program: Pk, pub out: Pk, pub accounts: Vec<Meta>, pub data: Vec<u8>, pub amount_offset: u8 }

/// What a leg needs beyond the pool's static facts
pub struct LegIn<'a> {
    pub m: &'a PoolMeta,
    /// the pool account's current bytes
    pub pool: &'a [u8],
    pub tin: Pk,
    pub tout: Pk,
    pub amount_in: u64,
    pub payer: Pk,
    pub pump: Option<&'a PumpGlobal>,
    /// DLMM: bin-array indices the quote may use (followed, read, usable: `quote::dlmm_window`'s `have`), and the bin
    /// where our quote ends. PLAN-ADDENDUM WP-21: Raydium CLMM the start indexes of the tick arrays the leg names, in walk
    /// order (`quote::Leg::clmm_arrays`: the quote's walk, then one buffer array); Orca Whirlpool the program's own 3
    /// (`venues::clmm::whirl_leg_starts`)
    pub dlmm_live: &'a [i64],
    pub dlmm_end: Option<i32>,
    /// DLMM: the pair's bitmap extension when the store holds it (it exists), read per send (PLAN WP-06 item 6; the
    /// boot-time check is gone). PLAN-ADDENDUM WP-21: Raydium CLMM's TickArrayBitmapExtension when it exists
    pub dlmm_ext: Option<Pk>,
}

fn prog_of(m: &PoolMeta, mint: &Pk) -> Pk { if *mint == m.t0 { m.t0_prog } else { m.t1_prog } }
pub fn ata_of(owner: &Pk, mint: &Pk, prog: &Pk) -> Pk { pda::ata(owner, mint, prog) }

pub fn leg(a: &LegIn) -> Result<Leg, String> {
    let m = a.m;
    if !((a.tin == m.t0 && a.tout == m.t1) || (a.tin == m.t1 && a.tout == m.t0)) { return Err("mints-not-this-pool".into()); }
    let ata = |mint: &Pk| ata_of(&a.payer, mint, &prog_of(m, mint));
    let zfo = a.tin == m.t0;
    let amount = a.amount_in.to_le_bytes();
    let min_out = 1u64.to_le_bytes();
    let out = ata(&a.tout);
    match m.venue {
        Venue::RayAmmV4 => {
            // swap_base_in_v2 (tag 16): every account from the pool; spl-token only
            if m.t0_prog != *TOKEN_PROGRAM || m.t1_prog != *TOKEN_PROGRAM { return Err("ammv4-token-2022-not-supported".into()); }
            let nonce = u64_at(a.pool, 8).ok_or("ammv4-pool-short")?;
            let auth = u8::try_from(nonce).ok().and_then(|n| pda::create_program_address(&[b"amm authority", &[n]], &m.venue.program()))
                .unwrap_or_else(|| pda::find_program_address(&[b"amm authority"], &m.venue.program()).0);
            let accounts = vec![r(*TOKEN_PROGRAM), w(m.pool), r(auth), w(m.vault0), w(m.vault1), w(ata(&a.tin)), w(out), s(a.payer)];
            let mut data = vec![AMMV4_SWAP_BASE_IN_V2];
            data.extend(amount); data.extend(min_out);
            Ok(Leg { program: m.venue.program(), out, accounts, data, amount_offset: 1 })
        }
        Venue::RayCpmm => {
            // SwapBaseInput: payer, authority, amm_config, pool, user in/out, vault in/out, token programs in/out,
            // mints in/out, observation; everything after the pool direction-ordered from the pool's own facts
            let cfg = pk_at(a.pool, 8).ok_or("cpmm-pool-short")?;
            let obs = pk_at(a.pool, 296).ok_or("cpmm-pool-short")?;
            let (vin, vout) = if zfo { (m.vault0, m.vault1) } else { (m.vault1, m.vault0) };
            let accounts = vec![s(a.payer), r(*RAYCPMM_AUTHORITY), r(cfg), w(m.pool), w(ata(&a.tin)), w(out), w(vin), w(vout),
                r(prog_of(m, &a.tin)), r(prog_of(m, &a.tout)), r(a.tin), r(a.tout), w(obs)];
            let mut data = CPMM_SWAP_BASE_INPUT.to_vec();
            data.extend(amount); data.extend(min_out);
            Ok(Leg { program: m.venue.program(), out, accounts, data, amount_offset: 8 })
        }
        Venue::PumpSwap => pump_leg(a, out),
        Venue::Dlmm => dlmm_leg(a, out),
        Venue::RayClmm => rayclmm_leg(a, out),
        Venue::Whirlpool => whirlpool_leg(a, out),
        Venue::DammV2 => {
            // `swap` (exact in), arbed's encoder: the vaults and mints are in the POOL's order (a then b) whatever the
            // direction; only the two user accounts follow the trade. referral_token_account None = the program id.
            let pid = m.venue.program();
            let accounts = vec![r(*DAMMV2_POOL_AUTHORITY), w(m.pool), w(ata(&a.tin)), w(out), w(m.vault0), w(m.vault1), r(m.t0), r(m.t1),
                s(a.payer), r(m.t0_prog), r(m.t1_prog), r(pid), r(*DAMMV2_EVENT_AUTHORITY), r(pid)];
            let mut data = DAMMV2_SWAP.to_vec();
            data.extend(amount); data.extend(min_out);
            Ok(Leg { program: pid, out, accounts, data, amount_offset: 8 })
        }
    }
}

/// PumpSwap's user volume accumulator of `user` (a PDA of PumpSwap): every buy names it, and creates it when it is
/// missing (1,346,200 lamports of rent, never recovered: PLAN WP-06 item 2)
pub fn pump_uva(user: &Pk) -> Pk { pda::find_program_address(&[b"user_volume_accumulator", user], &crate::venues::PUMPSWAP).0 }

/// PumpSwap `sell` (base in) or `buy_exact_quote_in` (quote in): arbed's pumpSwapTemplate + buildSwap's PumpSwap rules
/// (creator vault from the LIVE coin_creator, the payer's own volume accumulator, no cashback block before pool_v2).
fn pump_leg(a: &LegIn, out: Pk) -> Result<Leg, String> {
    let m = a.m;
    let pid = m.venue.program();
    let g = a.pump.ok_or("pump-no-global-config")?;
    let sell = a.tin == m.t0;
    if g.disable_flags & if sell { 1 << 4 } else { 1 << 3 } != 0 { return Err(format!("pump-{}-disabled", if sell { "sell" } else { "buy" })); }
    // a pool written before coin_creator existed (shorter than 243 bytes; arbx-sizing prices from 211): the program reads
    // it as zero, and so do the creator-vault accounts here (venue-harness adversarial "pool cut to 211 / 242 bytes")
    let creator = pk_at(a.pool, 211).unwrap_or([0u8; 32]);
    let mayhem = a.pool.get(243) == Some(&1);
    let cashback = a.pool.get(244) == Some(&1);
    let fees = if mayhem { &g.reserved } else { &g.protocol };
    if fees.is_empty() || g.buyback.is_empty() { return Err("pump-no-fee-recipients".into()); }
    let (base_prog, quote_prog, quote) = (m.t0_prog, m.t1_prog, m.t1);
    let pick = m.pool[0] as usize;
    let fee_recipient = fees[pick % fees.len()];
    let buyback = g.buyback[pick % g.buyback.len()];
    let creator_auth = pda::find_program_address(&[b"creator_vault", &creator], &pid).0;
    let uva = pump_uva(&a.payer);
    let quote_ata = |owner: &Pk| ata_of(owner, &quote, &quote_prog);
    let mut acc = vec![w(m.pool), s(a.payer), r(*PUMP_GLOBAL_CONFIG), r(m.t0), r(m.t1),
        w(ata_of(&a.payer, &m.t0, &base_prog)), w(ata_of(&a.payer, &m.t1, &quote_prog)), w(m.vault0), w(m.vault1),
        r(fee_recipient), w(quote_ata(&fee_recipient)), r(base_prog), r(quote_prog), r(*SYSTEM_PROGRAM), r(*ATA_PROGRAM),
        r(*PUMP_EVENT_AUTHORITY), r(pid), w(quote_ata(&creator_auth)), r(creator_auth)];
    if !sell { acc.push(r(*PUMP_GLOBAL_VOLUME_ACCUMULATOR)); acc.push(w(uva)); }
    acc.push(r(*crate::pools::PUMP_FEE_CONFIG));
    acc.push(r(*PUMP_FEE_PROGRAM));
    let has_v2 = creator != [0u8; 32];
    // arbed drops the payer-seeded cashback block in front of pool_v2 (the program refuses it, 6062 InvalidPoolV2) and
    // keeps it when there is no pool_v2 after it. That block names the user volume accumulator's WSOL account, which the
    // program could create at the payer's expense, rent we could not reclaim (review WP-06 #12): refused here too
    // (arbx-sizing refuses every cashback pool already, `sz_pump_cashback`)
    if cashback && !has_v2 { return Err("pump-cashback-without-pool-v2".into()); }
    if has_v2 { acc.push(r(pda::find_program_address(&[b"pool-v2", &m.t0], &pid).0)); }
    acc.push(r(buyback));
    acc.push(w(quote_ata(&buyback)));
    let mut data = if sell { PUMP_SELL.to_vec() } else { PUMP_BUY_EXACT_QUOTE_IN.to_vec() };
    data.extend(a.amount_in.to_le_bytes());
    data.extend(1u64.to_le_bytes());
    Ok(Leg { program: pid, out, accounts: acc, data, amount_offset: 8 })
}

/// the bin-array indices the pair's own bitmap covers: a named array outside needs the bitmap extension
pub const DLMM_INTERNAL_ARRAYS: std::ops::RangeInclusive<i64> = -512..=511;

/// The bin arrays a DLMM leg names (PLAN WP-06 item 6): the quote's window (`quote::dlmm_window`: the active bin's array,
/// then onward in the swap's direction while held, contiguous, at most 5) as far as the array of the quote's end bin,
/// plus one buffer array. The window is the one the quote walked, so the leg never runs past the liquidity it names.
/// An array outside the pair's own bitmap needs the bitmap extension: a buffer array there is left out when the pair has
/// none; an array the quote walks there is refused (`dlmm_ext_needed`)
pub fn dlmm_arrays(active: i32, zfo: bool, live: &[i64], end: Option<i32>, ext: bool) -> Result<Vec<i64>, String> {
    let c = dlmm::array_index(active);
    let window = crate::quote::dlmm_window(c, zfo, &|i| live.contains(&i));
    if window.is_empty() { return Err(format!("dlmm-active-binarray-not-held({c})")); }
    let e = end.map(dlmm::array_index).unwrap_or(c);
    let k = window.iter().position(|i| *i == e).ok_or_else(|| format!("dlmm-quote-end-outside-window({e})"))?;
    let mut names: Vec<i64> = window[..(k + 2).min(window.len())].to_vec();
    if !ext {
        if names[..=k].iter().any(|i| !DLMM_INTERNAL_ARRAYS.contains(i)) { return Err("dlmm_ext_needed".into()); }
        names.retain(|i| DLMM_INTERNAL_ARRAYS.contains(i));
    }
    Ok(names)
}

/// DLMM `swap2`: arbed's dlmmTemplate + buildSwap's DLMM rules. Bin arrays: `dlmm_arrays` (the quote's window as far as
/// its end bin, plus one buffer array). The bitmap extension when it exists (read from the store per send), else the
/// program id in its place (Anchor's None)
fn dlmm_leg(a: &LegIn, out: Pk) -> Result<Leg, String> {
    let m = a.m;
    let pid = m.venue.program();
    let oracle = pk_at(a.pool, 552).ok_or("dlmm-pool-short")?;
    let active = i32_at(a.pool, 76).ok_or("dlmm-pool-short")?;
    let zfo = a.tin == m.t0;
    let picks = dlmm_arrays(active, zfo, a.dlmm_live, a.dlmm_end, a.dlmm_ext.is_some())?;
    let ext = match a.dlmm_ext { Some(e) => w(e), None => r(pid) };
    let mut acc = vec![w(m.pool), ext, w(m.vault0), w(m.vault1), w(ata_of(&a.payer, &a.tin, &prog_of(m, &a.tin))), w(out),
        r(m.t0), r(m.t1), w(oracle), r(pid), s(a.payer), r(m.t0_prog), r(m.t1_prog), r(*MEMO), r(*DLMM_EVENT_AUTHORITY), r(pid)];
    for p in &picks { acc.push(w(dlmm::bin_array_pda(&m.pool, *p))); }
    let mut data = DLMM_SWAP2.to_vec();
    data.extend(a.amount_in.to_le_bytes());
    data.extend(1u64.to_le_bytes());
    data.extend(0u32.to_le_bytes());   // remaining_accounts_info: no transfer-hook slices
    Ok(Leg { program: pid, out, accounts: acc, data, amount_offset: 8 })
}

/// PLAN-ADDENDUM WP-21 (arbx-sizing DESIGN.md §9.1): Raydium CLMM `swap_v2`, exact in, the venue harness's layout
/// (program/venue-harness src/venues.rs, proven on the deployed binary): payer (signer), amm_config, pool (w), the
/// payer's input and output token accounts (w), the input and output vaults of the direction (w), observation (w), SPL
/// Token, Token-2022, Memo, the input and output mints; then the remaining accounts: the TickArrayBitmapExtension when it
/// exists (w), then the tick arrays in walk order (w), at most 7 in all. Data (41 B): amount, other_amount_threshold 1,
/// sqrt_price_limit_x64 0 (none: a partial fill fails), is_base_input 1
fn rayclmm_leg(a: &LegIn, out: Pk) -> Result<Leg, String> {
    let m = a.m;
    let pid = m.venue.program();
    let cfg = crate::venues::clmm::amm_config(a.pool).ok_or("rayclmm-pool-short")?;
    let obs = crate::venues::clmm::observation(a.pool).ok_or("rayclmm-pool-short")?;
    if Some(&cfg) != m.clmm_config() { return Err("rayclmm-config-mismatch".into()); }
    let zfo = a.tin == m.t0;
    let (vin, vout) = if zfo { (m.vault0, m.vault1) } else { (m.vault1, m.vault0) };
    if a.dlmm_live.is_empty() { return Err("rayclmm-no-tick-array".into()); }
    let n = a.dlmm_live.len() + a.dlmm_ext.is_some() as usize;
    if n > arbx_sizing::venue::raydium_clmm::MAX_REMAINING { return Err(format!("rayclmm-{n}-remaining-accounts")); }
    let mut acc = vec![s(a.payer), r(cfg), w(m.pool), w(ata_of(&a.payer, &a.tin, &prog_of(m, &a.tin))), w(out), w(vin), w(vout), w(obs),
        r(*TOKEN_PROGRAM), r(*crate::pda::TOKEN_2022), r(*MEMO), r(a.tin), r(a.tout)];
    if let Some(e) = a.dlmm_ext { acc.push(w(e)); }
    for st in a.dlmm_live {
        let st = i32::try_from(*st).map_err(|_| "rayclmm-bad-start")?;
        acc.push(w(crate::venues::clmm::ray_tick_array_pda(&m.pool, st)));
    }
    let mut data = CLMM_SWAP_V2.to_vec();
    data.extend(a.amount_in.to_le_bytes());
    data.extend(1u64.to_le_bytes());
    data.extend(0u128.to_le_bytes());
    data.push(1);
    Ok(Leg { program: pid, out, accounts: acc, data, amount_offset: 8 })
}

/// PLAN-ADDENDUM WP-21 (arbx-sizing DESIGN.md §9.2): Orca Whirlpool `swap_v2`, exact in, the venue harness's layout:
/// token programs of mint a and b, Memo, the payer (signer), the whirlpool (w), mints a and b, the payer's account of a
/// (w), vault a (w), the payer's account of b (w), vault b (w), all in the POOL's order whatever the direction; the 3 tick
/// arrays of the program's own sequence (w, initialized or not; the last repeated where fewer are valid), the oracle PDA
/// (w, initialized or not); no supplemental arrays. Data (43 B): amount, other_amount_threshold 1, sqrt_price_limit 0 (the
/// direction's limit), amount_specified_is_input 1, a_to_b, remaining_accounts_info None
fn whirlpool_leg(a: &LegIn, out: Pk) -> Result<Leg, String> {
    let m = a.m;
    let pid = m.venue.program();
    let a_to_b = a.tin == m.t0;
    let starts = crate::venues::clmm::whirl_leg_starts(a.pool, a_to_b).ok_or("whirlpool-no-tick-array")?;
    // the engine names the same 3 (route_in), from the same pool bytes
    if !a.dlmm_live.is_empty() && a.dlmm_live.iter().map(|x| *x as i32).ne(starts.iter().copied()) { return Err("whirlpool-tick-arrays-differ".into()); }
    let oracle = *m.whirl_oracle().ok_or("whirlpool-no-oracle-key")?;
    let mut acc = vec![r(m.t0_prog), r(m.t1_prog), r(*MEMO), s(a.payer), w(m.pool), r(m.t0), r(m.t1),
        w(ata_of(&a.payer, &m.t0, &m.t0_prog)), w(m.vault0), w(ata_of(&a.payer, &m.t1, &m.t1_prog)), w(m.vault1)];
    for st in starts { acc.push(w(crate::venues::clmm::whirl_tick_array_pda(&m.pool, st))); }
    acc.push(w(oracle));
    let mut data = CLMM_SWAP_V2.to_vec();
    data.extend(a.amount_in.to_le_bytes());
    data.extend(1u64.to_le_bytes());
    data.extend(0u128.to_le_bytes());
    data.push(1);
    data.push(a_to_b as u8);
    data.push(0);
    Ok(Leg { program: pid, out, accounts: acc, data, amount_offset: 8 })
}

/// nexus-arb-v2 route instruction. data: [0] 0x02 [1] n_legs [2..10] amount_in [10..18] min_profit, per leg
/// {n_accounts u8, amount_offset u8, data_len u16}, then every leg's data, then with `guard` the 8-byte
/// `max_payer_lamport_drop` trailer (nexus-v2's `encode_guarded`: presence is decided by the exact length; PLAN WP-06
/// item 9). accounts: authority, quote account, then per leg: output account, program, the leg's accounts.
pub fn route_ix(program: Pk, authority: Pk, quote: Pk, amount_in: u64, min_profit: u64, legs: &[Leg], guard: Option<u64>) -> Result<Ix, String> {
    if legs.is_empty() || legs.len() > 8 { return Err(format!("v2: {} legs, allowed 1..8", legs.len())); }
    if min_profit < 1 { return Err("v2: min_profit must be >= 1".into()); }
    if legs.last().unwrap().out != quote { return Err("v2: the last leg must deliver into the quote account".into()); }
    let mut data = vec![0x02, legs.len() as u8];
    data.extend(amount_in.to_le_bytes());
    data.extend(min_profit.to_le_bytes());
    for l in legs {
        // the v2 n_accounts byte carries the NATIVE flags in bits 6-7, so a leg of 64+ accounts would be re-read on
        // chain as a NATIVE leg of (n & 0x3F) accounts (arbx-exec REVIEW.md #9): refuse it here (v3 has a full byte)
        if l.accounts.len() > V2_MAX_LEG_ACCOUNTS { return Err(format!("v2: a leg of {} accounts (max {V2_MAX_LEG_ACCOUNTS}; use the v3 layout)", l.accounts.len())); }
        if l.data.len() > 0xffff || l.amount_offset as usize + 8 > l.data.len() { return Err("v2: leg too large".into()); }
        data.push(l.accounts.len() as u8);
        data.push(l.amount_offset);
        data.extend((l.data.len() as u16).to_le_bytes());
    }
    for l in legs { data.extend(&l.data); }
    if let Some(g) = guard { data.extend(g.to_le_bytes()); }
    let mut accounts = vec![s(authority), w(quote)];
    for l in legs { accounts.push(w(l.out)); accounts.push(r(l.program)); accounts.extend(l.accounts.iter().cloned()); }
    Ok(Ix { program, accounts, data })
}

/// arbx-exec's v3 route layout (program/arbx-exec, README.md has the byte table). The bytes are pinned by golden
/// vectors shared with the program (program/arbx-exec/tests/fixtures/golden), and this encoder refuses exactly what
/// the program's v3 parser refuses, so a route that builds here parses there. Not wired into `Exec::build` yet:
/// docs/PLAN.md WP-15 does that behind `[exec] route_program`; until then only the tests and `proglog::meaning` use it.
#[allow(dead_code)]
pub mod arbx_v3 {
    pub const VERSION: u8 = 3;
    /// flags byte. PAYER_GUARD is mandatory (arbx-exec REVIEW.md #2), so the encoder always sets it.
    pub const PAYER_GUARD: u8 = 0x01;
    pub const CPI_TIP: u8 = 0x02;
    pub const COUNT_LAMPORTS: u8 = 0x04;
    /// leg flags. At most one NATIVE flag per leg; AUTH_RO only on token legs, and only for venues that take the user
    /// as a plain signer (measured on mainnet snapshots: DLMM, CPMM, DAMM v2, AMM v4 yes; PumpSwap no).
    pub const LEG_NATIVE_IN: u8 = 0x01;
    pub const LEG_NATIVE_OUT: u8 = 0x02;
    pub const LEG_AUTH_RO: u8 = 0x04;
    pub const MAX_LEGS: usize = 8;
    /// the runtime's accounts per instruction
    pub const MAX_IX_ACCOUNTS: usize = 255;
    /// A CPI tip can only go to `JITO_TIP_ACCOUNTS[account_ix]` (compiled into the program, same order).
    pub const JITO_TIP_ACCOUNTS: [&str; 8] = [
        "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
        "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
        "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
        "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
        "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
        "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
        "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
        "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
    ];
    /// arbx-exec's error codes beyond nexus-arb-v2's (0x4e580001..07 keep their meaning)
    pub const ERR_UNSUPPORTED: u32 = 0x4e58_0008;
    pub const ERR_BAD_ACCOUNTS: u32 = 0x4e58_0009;
    pub const ERR_TIP_ACCOUNT: u32 = 0x4e58_000a;
    pub const ERR_TIP_FUNDS: u32 = 0x4e58_000b;
    pub const ERR_QUOTE_NOT_WSOL: u32 = 0x4e58_000c;
}

/// arbx-exec CPI tip: min(cap, max(floor, gain × bps / 10,000)) lamports to `JITO_TIP_ACCOUNTS[account_ix]`, paid only
/// when the route's guard passes.
#[allow(dead_code)] // WP-15
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct CpiTip { pub bps: u16, pub floor: u64, pub cap: u64, pub account_ix: u8 }

/// arbx-exec v3 route options. The payer guard is mandatory, so its drop is not optional.
#[allow(dead_code)] // WP-15
#[derive(Clone, Copy, Debug)]
pub struct V3Route { pub max_payer_lamport_drop: u64, pub count_lamports: bool, pub tip: Option<CpiTip> }

/// arbx-exec v3 route instruction. data: [0] 3 [1] flags [2] n_legs [3..11] amount_in [11..19] min_profit [19..27]
/// max_payer_lamport_drop, with CPI_TIP {u16 bps, u64 floor, u64 cap, u8 account_ix}, per leg {n_accounts u8,
/// leg_flags u8, amount_offset u8, data_len u16}, then every leg's data. accounts: authority, quote account, per leg
/// (output account, program, the leg's accounts), and with CPI_TIP the System program and the tip account.
#[allow(dead_code)] // WP-15
pub fn route_ix_v3(program: Pk, authority: Pk, quote: Pk, amount_in: u64, min_profit: u64, legs: &[Leg], leg_flags: &[u8], o: &V3Route) -> Result<Ix, String> {
    use arbx_v3::*;
    if legs.is_empty() || legs.len() > MAX_LEGS { return Err(format!("v3: {} legs, allowed 1..8", legs.len())); }
    if leg_flags.len() != legs.len() { return Err("v3: one flags byte per leg".into()); }
    if min_profit < 1 { return Err("v3: min_profit must be >= 1".into()); }
    let mut flags = PAYER_GUARD;
    if o.count_lamports { flags |= COUNT_LAMPORTS; }
    if let Some(t) = o.tip {
        if !o.count_lamports { return Err("v3: a CPI tip needs count_lamports (the tip is paid in lamports)".into()); }
        if t.bps > 10_000 || t.cap < t.floor || t.account_ix as usize >= JITO_TIP_ACCOUNTS.len() { return Err("v3: bad CPI tip parameters".into()); }
        flags |= CPI_TIP;
    }
    let native = |f: u8| f & (LEG_NATIVE_IN | LEG_NATIVE_OUT);
    for (i, (l, &f)) in legs.iter().zip(leg_flags).enumerate() {
        if l.accounts.is_empty() || l.accounts.len() > 255 { return Err(format!("v3: leg {i} has {} accounts, allowed 1..255", l.accounts.len())); }
        if l.data.len() > 0xffff || l.amount_offset as usize + 8 > l.data.len() { return Err(format!("v3: leg {i} data")); }
        if f & !(LEG_NATIVE_IN | LEG_NATIVE_OUT | LEG_AUTH_RO) != 0 || native(f) == LEG_NATIVE_IN | LEG_NATIVE_OUT || (native(f) != 0 && f & LEG_AUTH_RO != 0) {
            return Err(format!("v3: leg {i} flags {f:#04x}"));
        }
        if native(f) != 0 && !o.count_lamports { return Err(format!("v3: native leg {i} needs count_lamports")); }
        // lamports only chain into lamports: a NATIVE_IN leg follows a NATIVE_OUT leg (or is first), and vice versa
        let prev_out = i > 0 && leg_flags[i - 1] & LEG_NATIVE_OUT != 0;
        if (f & LEG_NATIVE_IN != 0 && i > 0 && !prev_out) || (f & LEG_NATIVE_IN == 0 && prev_out) { return Err(format!("v3: leg {i} breaks the native chain")); }
    }
    let last = legs.len() - 1;
    if leg_flags[last] & LEG_NATIVE_OUT != 0 {
        if legs[last].out != authority { return Err("v3: a NATIVE_OUT last leg delivers into the authority".into()); }
    } else if legs[last].out != quote {
        return Err("v3: the last leg must deliver into the quote account".into());
    }
    let n_accounts = 2 + legs.iter().map(|l| 2 + l.accounts.len()).sum::<usize>() + if o.tip.is_some() { 2 } else { 0 };
    if n_accounts > MAX_IX_ACCOUNTS { return Err(format!("v3: {n_accounts} accounts, the runtime allows {MAX_IX_ACCOUNTS}")); }
    let mut data = vec![VERSION, flags, legs.len() as u8];
    data.extend(amount_in.to_le_bytes());
    data.extend(min_profit.to_le_bytes());
    data.extend(o.max_payer_lamport_drop.to_le_bytes());
    if let Some(t) = o.tip {
        data.extend(t.bps.to_le_bytes());
        data.extend(t.floor.to_le_bytes());
        data.extend(t.cap.to_le_bytes());
        data.push(t.account_ix);
    }
    for (l, &f) in legs.iter().zip(leg_flags) {
        data.push(l.accounts.len() as u8);
        data.push(f);
        data.push(l.amount_offset);
        data.extend((l.data.len() as u16).to_le_bytes());
    }
    for l in legs { data.extend(&l.data); }
    let mut accounts = vec![s(authority), w(quote)];
    for l in legs { accounts.push(w(l.out)); accounts.push(r(l.program)); accounts.extend(l.accounts.iter().cloned()); }
    if let Some(t) = o.tip { accounts.push(r(*SYSTEM_PROGRAM)); accounts.push(w(pk(JITO_TIP_ACCOUNTS[t.account_ix as usize]))); }
    Ok(Ix { program, accounts, data })
}

pub fn cu_limit_ix(units: u32) -> Ix { let mut d = vec![2]; d.extend(units.to_le_bytes()); Ix { program: COMPUTE_BUDGET, accounts: vec![], data: d } }
/// ComputeBudget SetLoadedAccountsDataSizeLimit (instruction 4, u32 bytes)
pub fn loaded_data_limit_ix(bytes: u32) -> Ix { let mut d = vec![4]; d.extend(bytes.to_le_bytes()); Ix { program: COMPUTE_BUDGET, accounts: vec![], data: d } }
/// SPL Token / Token-2022 CloseAccount (instruction 9): every lamport of `account` (empty) to `destination`, signed by
/// its `owner`
pub fn close_account_ix(account: Pk, destination: Pk, owner: Pk, token_program: Pk) -> Ix {
    Ix { program: token_program, accounts: vec![w(account), w(destination), Meta { key: owner, signer: true, writable: false }], data: vec![9] }
}
pub fn cu_price_ix(micro: u64) -> Ix { let mut d = vec![3]; d.extend(micro.to_le_bytes()); Ix { program: COMPUTE_BUDGET, accounts: vec![], data: d } }
pub fn transfer_ix(from: Pk, to: Pk, lamports: u64) -> Ix {
    let mut d = 2u32.to_le_bytes().to_vec();
    d.extend(lamports.to_le_bytes());
    Ix { program: *SYSTEM_PROGRAM, accounts: vec![s(from), w(to)], data: d }
}
/// A new durable-nonce account at create_with_seed(payer, seed, system program), authority `payer`: its address and the
/// two instructions (CreateAccountWithSeed with `lamports` for 80 bytes, InitializeNonceAccount)
pub fn create_nonce_ixs(payer: Pk, seed: &str, lamports: u64) -> (Pk, Vec<Ix>) {
    use sha2::Digest;
    let addr: Pk = sha2::Sha256::new().chain_update(payer).chain_update(seed.as_bytes()).chain_update(*SYSTEM_PROGRAM).finalize().into();
    let mut d = 3u32.to_le_bytes().to_vec();
    d.extend(payer);
    d.extend((seed.len() as u64).to_le_bytes());
    d.extend(seed.as_bytes());
    d.extend(lamports.to_le_bytes());
    d.extend(80u64.to_le_bytes());
    d.extend(*SYSTEM_PROGRAM);
    let create = Ix { program: *SYSTEM_PROGRAM, accounts: vec![s(payer), w(addr), s(payer)], data: d };
    let mut d = 6u32.to_le_bytes().to_vec();
    d.extend(payer);
    let init = Ix { program: *SYSTEM_PROGRAM, accounts: vec![w(addr), r(*SYSVAR_RECENT_BLOCKHASHES), r(pk("SysvarRent111111111111111111111111111111111"))], data: d };
    (addr, vec![create, init])
}

/// AdvanceNonceAccount: must be the FIRST instruction of a durable-nonce transaction. Kept for the direct experiment
/// only (PLAN WP-05 item 3: bundles use a recent blockhash; `[send_policy.direct] nonce_accounts` keeps the accounts):
/// nothing calls it in Stage 0 (review WP-05 #17)
pub fn advance_nonce_ix(nonce: Pk, authority: Pk) -> Ix {
    Ix { program: *SYSTEM_PROGRAM, accounts: vec![w(nonce), r(*SYSVAR_RECENT_BLOCKHASHES), s(authority)], data: 4u32.to_le_bytes().to_vec() }
}
/// SPL Token SyncNative: a WSOL account's token amount catches up with its lamports
pub fn sync_native_ix(account: Pk) -> Ix { Ix { program: *TOKEN_PROGRAM, accounts: vec![w(account)], data: vec![17] } }
pub fn create_ata_idempotent_ix(payer: Pk, owner: Pk, mint: Pk, token_prog: Pk) -> Ix {
    Ix { program: *ATA_PROGRAM, accounts: vec![s(payer), w(ata_of(&owner, &mint, &token_prog)), r(owner), r(mint), r(*SYSTEM_PROGRAM), r(token_prog)], data: vec![1] }
}

/// The mid token's account in a bundle (PLAN WP-06 item 2): created (idempotent) before the route when the wallet holds
/// none, and closed to the payer after it when `close` (create+close: rent-neutral). `close` false is a deliberate
/// held-set addition (the size budget's fallback, off unless `[builder] held_max` > 0)
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct AtaOps { pub mint: Pk, pub token_program: Pk, pub close: bool }

/// The rent a token account the builder creates and keeps (a held-set addition: `[builder] held_max` > 0, an explicit
/// opt-in, off by default) may lock, taken as an upper bound: a 200-byte account (SPL Token's are 165 bytes, a Token-2022
/// ATA 170 with its ImmutableOwner extension, plus the account extensions a tradable mint can add) with the 128-byte
/// overhead, at 6,960 lamports a byte (3,480 a byte-year for two years: the rent before mainnet's reduction; on 2026-10-04
/// mainnet took 5,080 a byte, 1,488,440 lamports for an SPL account and 1,513,840 for a Token-2022 one, res-pnl §2 and
/// the venue harness). A held addition's on-chain min_profit adds it: the WSOL the route must make covers the SOL the
/// account keeps (review WP-06 #1), and the dry run's checks demand it (`min_profit_covers_tip`)
pub const HELD_RENT_BOUND: u64 = (200 + 128) * 6_960;

/// Everything a bundle transaction holds besides its route
#[derive(Clone, Debug, PartialEq)]
pub struct Plan { pub payer: Pk, pub cu_limit: u32, pub loaded_data_limit: Option<u32>, pub ata: Option<AtaOps>, pub tip: Option<(Pk, u64)>,
    /// arbx-fast: the compute-unit price (micro-lamports) for a Helius Sender copy; 0 = none (a Jito bundle carries none)
    pub cu_price: u64,
    /// arbx-fast: one more top-level tip transfer per extra send path of the same transaction (Bolt...), after `tip`
    pub extra_tips: Vec<(Pk, u64)> }

/// One bundle transaction's instructions, in PLAN WP-06 item 1's order: the CU limit; the loaded-accounts data size
/// limit; the mid token's ATA create (idempotent; the wallet holds none); the route; the CloseAccount of that ATA to the
/// payer (only when this transaction created it and `close`: its rent comes back in the same transaction); the tip, a
/// top-level System transfer, last (Jito ignores a tip account named through a table)
pub fn bundle_ixs(p: &Plan, route: Ix) -> Vec<Ix> {
    let mut ixs = vec![cu_limit_ix(p.cu_limit)];
    if p.cu_price > 0 { ixs.push(cu_price_ix(p.cu_price)); }
    if let Some(b) = p.loaded_data_limit { ixs.push(loaded_data_limit_ix(b)); }
    if let Some(a) = &p.ata { ixs.push(create_ata_idempotent_ix(p.payer, p.payer, a.mint, a.token_program)); }
    ixs.push(route);
    if let Some(a) = p.ata.filter(|a| a.close) { ixs.push(close_account_ix(ata_of(&p.payer, &a.mint, &a.token_program), p.payer, p.payer, a.token_program)); }
    if let Some((to, lamports)) = p.tip { ixs.push(transfer_ix(p.payer, to, lamports)); }
    for (to, lamports) in &p.extra_tips { ixs.push(transfer_ix(p.payer, *to, *lamports)); }
    ixs
}

// ------------------------------------------------------------------ the loaded-accounts data size (PLAN WP-06 item 1)

/// SIMD-0186's per-account base size and per-lookup-table size
pub const ACCOUNT_BASE_BYTES: u64 = 64;
pub const ALT_BASE_BYTES: u64 = 8_248;
/// what an account the store does not hold may weigh (DLMM oracles, fee recipients' accounts, PDAs): generous
pub const UNKNOWN_ACCOUNT_BYTES: u64 = 64 * 1024;
/// a program missing from `PROGRAM_BYTES`
pub const UNKNOWN_PROGRAM_BYTES: u64 = 4 * 1024 * 1024;

/// The programs our bundles invoke or name, with what loading one weighs beyond its own 64 base bytes: its program
/// account's data (36 bytes for an upgradeable one) plus, for an upgradeable one, its programdata account (64 base bytes,
/// the 45-byte header and the ELF region: program/venue-harness/fixtures/programs/MANIFEST.json `onchain_size`, which is
/// the region after the header, read on 2026-10-04; testdata/programs for nexus-v2, whose 43,485 bytes include the
/// header). An upgrade that extends a programdata account grows it: the estimate's margin covers that, and the dry run's
/// simulation checks the limit on chain (go-live gate item 4)
pub const PROGRAM_BYTES: [(&str, u64); 17] = [
    ("8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg", 36 + 64 + 43_485),       // nexus-arb-v2
    ("pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA", 36 + 64 + 45 + 10_485_715),    // PumpSwap
    ("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ", 36 + 64 + 45 + 948_944),       // PumpSwap's fee program
    ("CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C", 36 + 64 + 45 + 793_824),      // Raydium CPMM
    ("675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8", 36 + 64 + 45 + 1_406_384),    // Raydium AMM v4
    ("LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo", 36 + 64 + 45 + 2_229_776),     // Meteora DLMM
    ("cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG", 36 + 64 + 45 + 2_174_352),     // Meteora DAMM v2
    // PLAN-ADDENDUM WP-21 (MANIFEST.json of 2026-10-06)
    ("CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK", 36 + 64 + 45 + 1_700_160),    // Raydium CLMM
    ("whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc", 36 + 64 + 45 + 10_485_715),   // Orca Whirlpool
    ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", 36 + 64 + 45 + 108_600),       // SPL Token (p-token)
    ("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb", 36 + 64 + 45 + 1_382_016),     // Token-2022
    ("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL", 105_032),            // the ATA program (BPFLoader2: the ELF in its account)
    ("MemoSq4gqABAXKb96qnH8TysNcWxMyWCqXgDLGmfcHr", 128 * 1024),          // Memo v3 (named by DLMM's swap2), generous
    ("11111111111111111111111111111111", 64),                              // the System program (native)
    ("ComputeBudget111111111111111111111111111111", 64),                   // the ComputeBudget program (native)
    ("SysvarRent111111111111111111111111111111111", 64),
    ("SysvarC1ock11111111111111111111111111111111", 64),
];

/// What one account weighs when the transaction loads it: a listed program's bytes, else the store's size for it, else
/// `UNKNOWN_PROGRAM_BYTES` for a program the transaction invokes and `UNKNOWN_ACCOUNT_BYTES` for any other account
fn account_bytes(k: &Pk, invoked: bool, size: &dyn Fn(&Pk) -> Option<usize>) -> u64 {
    static PROGS: LazyLock<HashMap<Pk, u64>> = LazyLock::new(|| PROGRAM_BYTES.iter().map(|(k, b)| (pk(k), *b)).collect());
    if let Some(b) = PROGS.get(k) { return *b; }
    size(k).map_or(if invoked { UNKNOWN_PROGRAM_BYTES } else { UNKNOWN_ACCOUNT_BYTES }, |n| n as u64)
}

/// The bytes a transaction loads before any margin (SIMD-0186): 64 plus the weight (`account_bytes`) of every distinct
/// account, given as (key, whether the transaction invokes it as a program; a key given twice counts once, invoked if
/// either says so), and 8,248 per lookup table the message loads from
pub fn loaded_data_raw(accounts: impl IntoIterator<Item = (Pk, bool)>, n_alts: usize, size: &dyn Fn(&Pk) -> Option<usize>) -> u64 {
    let mut seen: HashMap<Pk, bool> = HashMap::default();
    for (k, invoked) in accounts { *seen.entry(k).or_default() |= invoked; }
    seen.iter().map(|(k, invoked)| ACCOUNT_BASE_BYTES + account_bytes(k, *invoked, size)).sum::<u64>() + ALT_BASE_BYTES * n_alts as u64
}

/// `[builder] loaded_data_limit = "auto"`'s margin on a raw count: 25% and 256 KiB on top, rounded up to 32 KiB, at most
/// 64 MiB
pub fn loaded_data_padded(raw: u64) -> u32 {
    let padded = raw + raw / 4 + 256 * 1024;
    (padded.div_ceil(32 * 1024) * 32 * 1024).min(MAX_LOADED_DATA as u64) as u32
}

/// `[builder] loaded_data_limit = "auto"`: an upper bound of the bytes the transaction loads (SIMD-0186: 64 bytes plus
/// the data of every distinct account, programs with their programdata, 8,248 per lookup table it loads from), from its
/// instructions and the payer, with `loaded_data_padded`'s margin. `size`: an account's data length as the store holds
/// it. The dry run derives the same number from the signed message's own accounts (`exec::verify_bundle`)
pub fn loaded_data_estimate(payer: &Pk, ixs: &[Ix], n_alts: usize, size: &dyn Fn(&Pk) -> Option<usize>) -> u32 {
    let programs = ixs.iter().map(|ix| (ix.program, true));
    let accounts = ixs.iter().flat_map(|ix| ix.accounts.iter().map(|a| (a.key, false)));
    loaded_data_padded(loaded_data_raw(programs.chain([(*payer, false)]).chain(accounts), n_alts, size))
}

/// A durable nonce account's stored value (the blockhash field the transaction carries), from its 80 bytes. The direct
/// experiment's, like `advance_nonce_ix`: no reader in Stage 0
pub fn nonce_value(d: &[u8]) -> Option<[u8; 32]> {
    if d.len() < 72 || crate::venues::u32_at(d, 4)? != 1 { return None; }
    d[40..72].try_into().ok()
}

/// A lookup table: its address and its entries (index = position)
pub struct Alt { pub key: Pk, pub index: HashMap<Pk, u8> }
impl Alt {
    pub fn new(key: Pk, addrs: &[Pk]) -> Alt {
        let mut index = HashMap::default();
        for (i, a) in addrs.iter().enumerate().take(256) { index.entry(*a).or_insert(i as u8); }
        Alt { key, index }
    }
}

fn compact(n: usize, out: &mut Vec<u8>) {
    let mut v = n;
    loop { let mut b = (v & 0x7f) as u8; v >>= 7; if v == 0 { out.push(b); break; } b |= 0x80; out.push(b); }
}

/// A compiled v0 message, ready to sign. `loadable`: its static keys a lookup table could hold instead (not a signer,
/// not an invoked program, not kept static): what the size budget's index tables may cover (PLAN WP-06 item 7);
/// `lookups`: the tables it loads accounts from (of those it was compiled with, the ones that hold any)
pub struct Message { pub bytes: Vec<u8>, pub static_keys: usize, pub locks: usize, pub loadable: Vec<Pk>, pub lookups: usize }

/// Compile a v0 message exactly as web3.js's compileToV0Message (arbed's compileV0Fast): payer first; a non-signer,
/// non-program account found in a table is loaded from it (tables in order, writable then readonly, first index);
/// static keys are writable signers, readonly signers, writable, readonly, each in first-use order. Accounts in
/// `keep_static` are never loaded from a table: the nonce account and RecentBlockhashes sysvar (the runtime checks a
/// durable nonce before tables load, and drops the transaction otherwise) and tip accounts (Jito ignores a tip
/// account named through a table).
pub fn compile_v0(payer: Pk, ixs: &[Ix], blockhash: [u8; 32], alts: &[&Alt], keep_static: &[Pk]) -> Result<Message, String> {
    #[derive(Clone, Copy, Default)]
    struct Flags { signer: bool, writable: bool, invoked: bool }
    let mut order: Vec<Pk> = Vec::new();
    let mut meta: HashMap<Pk, Flags> = HashMap::default();
    let mut add = |k: Pk, f: Flags, order: &mut Vec<Pk>| {
        let e = meta.entry(k).or_insert_with(|| { order.push(k); Flags::default() });
        e.signer |= f.signer; e.writable |= f.writable; e.invoked |= f.invoked;
    };
    add(payer, Flags { signer: true, writable: true, invoked: false }, &mut order);
    for ix in ixs {
        add(ix.program, Flags { invoked: true, ..Default::default() }, &mut order);
        for a in &ix.accounts { add(a.key, Flags { signer: a.signer, writable: a.writable, invoked: false }, &mut order); }
    }
    let mut lookups: Vec<(Pk, Vec<u8>, Vec<u8>)> = Vec::new();
    let (mut lw, mut lr): (Vec<Pk>, Vec<Pk>) = (Vec::new(), Vec::new());
    let mut loaded: rustc_hash::FxHashSet<Pk> = Default::default();
    for t in alts {
        let (mut wi, mut ri) = (Vec::new(), Vec::new());
        for pass in [true, false] {
            for k in &order {
                let f = meta[k];
                if f.signer || f.invoked || f.writable != pass || loaded.contains(k) || keep_static.contains(k) { continue; }
                if let Some(&i) = t.index.get(k) {
                    loaded.insert(*k);
                    if pass { wi.push(i); lw.push(*k); } else { ri.push(i); lr.push(*k); }
                }
            }
        }
        if !wi.is_empty() || !ri.is_empty() { lookups.push((t.key, wi, ri)); }
    }
    let stat: Vec<Pk> = order.iter().filter(|k| !loaded.contains(*k)).copied().collect();
    let group = |sg: bool, wr: bool| stat.iter().filter(|k| { let f = meta[*k]; f.signer == sg && f.writable == wr }).copied().collect::<Vec<_>>();
    let (ws, rs, wn, rn) = (group(true, true), group(true, false), group(false, true), group(false, false));
    if ws.first() != Some(&payer) { return Err("payer is not the first writable signer".into()); }
    let keys: Vec<Pk> = [ws.clone(), rs.clone(), wn, rn.clone()].concat();
    let all: Vec<Pk> = [keys.clone(), lw, lr].concat();
    if all.len() > 256 { return Err("more than 256 accounts".into()); }
    let pos: HashMap<Pk, u8> = all.iter().enumerate().map(|(i, k)| (*k, i as u8)).collect();
    let mut b = vec![0x80, (ws.len() + rs.len()) as u8, rs.len() as u8, rn.len() as u8];
    compact(keys.len(), &mut b);
    for k in &keys { b.extend(k); }
    b.extend(blockhash);
    compact(ixs.len(), &mut b);
    for ix in ixs {
        b.push(pos[&ix.program]);
        compact(ix.accounts.len(), &mut b);
        for a in &ix.accounts { b.push(pos[&a.key]); }
        compact(ix.data.len(), &mut b);
        b.extend(&ix.data);
    }
    compact(lookups.len(), &mut b);
    for (t, wi, ri) in &lookups {
        b.extend(t);
        compact(wi.len(), &mut b); b.extend(wi);
        compact(ri.len(), &mut b); b.extend(ri);
    }
    let loadable: Vec<Pk> = keys.iter().filter(|k| { let f = meta[*k]; !f.signer && !f.invoked && !keep_static.contains(k) }).copied().collect();
    Ok(Message { bytes: b, static_keys: keys.len(), locks: all.len(), loadable, lookups: lookups.len() })
}

/// signed wire bytes: one signature (the payer's), then the message
pub fn sign(msg: &Message, key: &ed25519_dalek::SigningKey) -> Vec<u8> {
    use ed25519_dalek::Signer;
    let sig = key.sign(&msg.bytes).to_bytes();
    let mut out = Vec::with_capacity(1 + 64 + msg.bytes.len());
    out.push(1);
    out.extend(sig);
    out.extend(&msg.bytes);
    out
}

/// unsigned wire bytes (an all-zero signature), for simulation with sigVerify off
pub fn unsigned(msg: &Message) -> Vec<u8> {
    let mut out = Vec::with_capacity(1 + 64 + msg.bytes.len());
    out.push(1);
    out.extend([0u8; 64]);
    out.extend(&msg.bytes);
    out
}

/// size of the signed transaction
pub fn tx_bytes(msg: &Message) -> usize { 1 + 64 + msg.bytes.len() }

/// A custom program error code from a simulation / transaction error value ({"InstructionError":[i,{"Custom":n}]})
pub fn custom_code(err: &serde_json::Value) -> Option<u32> {
    err.get("InstructionError")?.get(1)?.get("Custom")?.as_u64().map(|n| n as u32)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tx::b58;

    fn meta(venue: Venue) -> PoolMeta {
        PoolMeta { venue, pool: [21; 32], t0: [1; 32], t1: *crate::venues::WSOL, vault0: [3; 32], vault1: [4; 32],
            t0_prog: *TOKEN_PROGRAM, t1_prog: *TOKEN_PROGRAM, extra: vec![[9; 32]], flag: false }
    }

    #[test]
    fn dammv2_authorities_are_the_programs_pdas() {
        let pid = *crate::venues::DAMMV2;
        assert_eq!(*DAMMV2_EVENT_AUTHORITY, pda::find_program_address(&[b"__event_authority"], &pid).0);
        assert_eq!(*DAMMV2_POOL_AUTHORITY, pda::find_program_address(&[b"pool_authority"], &pid).0);
    }

    #[test]
    fn real_wallet_wsol_account() {
        // the trading wallet's WSOL account on chain (2026-10-03): the quote account every route starts from
        let wallet = pk("FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS");
        assert_eq!(b58(&ata_of(&wallet, &crate::venues::WSOL, &TOKEN_PROGRAM)), "HtT4ZeQdTRUtQHJ6ha7pBUbupQxEXdep8M5LVPnbxoyr");
        assert_eq!(b58(&DLMM_EVENT_AUTHORITY), "D1ZN9Wj1fRSUQfCjhvnu1hqDMT7hzjzBBpi12nVniYD6");
    }

    #[test]
    fn v2_data_layout() {
        let l = Leg { program: [5; 32], out: [6; 32], accounts: vec![w([7; 32])], data: vec![9; 24], amount_offset: 8 };
        let l2 = Leg { out: [8; 32], ..l.clone() };
        let ix = route_ix([1; 32], [2; 32], [8; 32], 1_000, 7, &[l, l2], None).unwrap();
        assert_eq!(&ix.data[..2], &[2, 2]);
        assert_eq!(u64::from_le_bytes(ix.data[2..10].try_into().unwrap()), 1_000);
        assert_eq!(u64::from_le_bytes(ix.data[10..18].try_into().unwrap()), 7);
        assert_eq!(&ix.data[18..22], &[1, 8, 24, 0]);
        assert_eq!(ix.data.len(), 18 + 2 * 4 + 48);
        assert_eq!(ix.accounts.len(), 2 + 2 * 3);
        assert!(ix.accounts[0].signer && ix.accounts[0].key == [2; 32]);
        assert!(route_ix([1; 32], [2; 32], [99; 32], 1, 1, &[Leg { program: [5; 32], out: [6; 32], accounts: vec![], data: vec![0; 16], amount_offset: 8 }], None).is_err(), "last leg must pay the quote account");
    }

    // ---- golden vectors shared with program/arbx-exec (its tests assert the same files) ----

    fn golden(name: &str) -> Vec<u8> {
        let path = format!("{}/program/arbx-exec/tests/fixtures/golden/{name}", env!("CARGO_MANIFEST_DIR"));
        let h = std::fs::read_to_string(&path).unwrap_or_else(|e| panic!("{path}: {e}"));
        let h = h.trim();
        (0..h.len()).step_by(2).map(|i| u8::from_str_radix(&h[i..i + 2], 16).unwrap()).collect()
    }
    fn legn(n: usize, out: Pk, byte: u8, len: usize) -> Leg {
        Leg { program: [5; 32], out, accounts: (0..n).map(|i| w([i as u8; 32])).collect(), data: vec![byte; len], amount_offset: 8 }
    }

    #[test]
    fn v2_route_matches_the_shared_golden_vector() {
        let (quote, x) = ([8; 32], [6; 32]);
        let ix = route_ix([1; 32], [2; 32], quote, 0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &[legn(3, x, 0xAA, 16), legn(4, quote, 0xBB, 16)], None).unwrap();
        assert_eq!(ix.data, golden("v2_route.hex"));
    }

    /// PLAN WP-06 item 9: the payer guard's trailer is nexus-v2's `encode_guarded`, byte for byte: the test vector pinned
    /// in program/nexus-arb-v2/src/lib.rs (`GUARDED_FIXTURE_HEX`: the legs (3, 8, 0xAA x 16) and (4, 8, 0xBB x 16),
    /// amount_in 0x0102030405060708, min_profit 0x1112131415161718, max_payer_lamport_drop 0x2122232425262728); without
    /// a guard the bytes are the pre-upgrade `FIXTURE_HEX` (the shared golden vector), so nexus-v2 parses both
    #[test]
    fn guard_trailer_matches_nexus_v2_encode_guarded() {
        let src = include_str!("../program/nexus-arb-v2/src/lib.rs");
        let fixture = |name: &str| -> String {
            let start = src.find(&format!("const {name}: &str = concat!(")).unwrap_or_else(|| panic!("{name} in nexus-arb-v2"));
            let block = &src[start..start + src[start..].find(");").unwrap()];
            block.split('"').skip(1).step_by(2).filter(|p| p.chars().all(|c| c.is_ascii_hexdigit())).collect()
        };
        let hex = |d: &[u8]| d.iter().map(|b| format!("{b:02x}")).collect::<String>();
        let (quote, x) = ([8; 32], [6; 32]);
        let legs = [legn(3, x, 0xAA, 16), legn(4, quote, 0xBB, 16)];
        let g = route_ix([1; 32], [2; 32], quote, 0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &legs, Some(0x2122_2324_2526_2728)).unwrap();
        assert_eq!(hex(&g.data), fixture("GUARDED_FIXTURE_HEX"));
        assert_eq!(hex(&g.data), "0202080706050403020118171615141312110308100004081000aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaabbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb2827262524232221");
        let plain = route_ix([1; 32], [2; 32], quote, 0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &legs, None).unwrap();
        assert_eq!(hex(&plain.data), fixture("FIXTURE_HEX"));
        assert_eq!((g.data.len(), plain.data.len()), (plain.data.len() + 8, 18 + 8 + 32), "8 bytes (R §3.9)");
        assert_eq!(g.accounts.len(), plain.accounts.len(), "no account added");
    }

    /// PLAN WP-06 item 1: the new instructions' encodings. SetLoadedAccountsDataSizeLimit is ComputeBudget instruction 4
    /// with a u32; CloseAccount is token instruction 9 (SPL Token and Token-2022 alike) over [account (writable),
    /// destination (writable), owner (signer)]
    #[test]
    fn close_account_and_loaded_data_limit_encodings() {
        let l = loaded_data_limit_ix(0x0012_D687);
        assert_eq!((l.program, l.accounts.len(), l.data.clone()), (COMPUTE_BUDGET, 0, vec![4, 0x87, 0xD6, 0x12, 0x00]));
        for prog in [*TOKEN_PROGRAM, *crate::pda::TOKEN_2022] {
            let c = close_account_ix([3; 32], [4; 32], [5; 32], prog);
            assert_eq!((c.program, c.data.clone()), (prog, vec![9]));
            assert_eq!(c.accounts, vec![w([3; 32]), w([4; 32]), Meta { key: [5; 32], signer: true, writable: false }]);
        }
        // the create they pair with: the ATA program's CreateIdempotent (1) over [payer, the account, owner, mint, System, token program]
        let a = create_ata_idempotent_ix([7; 32], [7; 32], [9; 32], *crate::pda::TOKEN_2022);
        assert_eq!((a.program, a.data.clone(), a.accounts[1].key), (*ATA_PROGRAM, vec![1], ata_of(&[7; 32], &[9; 32], &crate::pda::TOKEN_2022)));
    }

    /// PLAN WP-06 item 1, golden: the instruction order with and without create/close (CU limit, loaded-data limit, [ATA
    /// create], route, [CloseAccount of that ATA to the payer], tip last), and the compiled message: the create and the
    /// close name the same account, the close sends it to the payer, the tip stays a static key and the last instruction
    #[test]
    fn bundle_instruction_order_golden() {
        let payer = [77u8; 32];
        let (mint, quote) = ([9u8; 32], ata_of(&payer, &crate::venues::WSOL, &TOKEN_PROGRAM));
        let mid = ata_of(&payer, &mint, &TOKEN_PROGRAM);
        let route = route_ix([60; 32], payer, quote, 1_000, 5, &[legn(3, mid, 0xAA, 16), legn(4, quote, 0xBB, 16)], None).unwrap();
        let tip = ([96; 32], 1_234u64);
        let names = |ixs: &[Ix]| -> Vec<(Pk, Vec<u8>)> { ixs.iter().map(|ix| (ix.program, ix.data.iter().take(1).copied().collect())).collect() };
        let held = bundle_ixs(&Plan { payer, cu_limit: 200_000, loaded_data_limit: Some(1 << 20), ata: None, tip: Some(tip), cu_price: 0, extra_tips: vec![] }, route.clone());
        assert_eq!(names(&held), vec![(COMPUTE_BUDGET, vec![2]), (COMPUTE_BUDGET, vec![4]), ([60; 32], vec![2]), (*SYSTEM_PROGRAM, vec![2])]);
        let ata = Some(AtaOps { mint, token_program: *TOKEN_PROGRAM, close: true });
        let cc = bundle_ixs(&Plan { payer, cu_limit: 235_000, loaded_data_limit: Some(1 << 20), ata, tip: Some(tip), cu_price: 0, extra_tips: vec![] }, route.clone());
        assert_eq!(names(&cc), vec![(COMPUTE_BUDGET, vec![2]), (COMPUTE_BUDGET, vec![4]), (*ATA_PROGRAM, vec![1]), ([60; 32], vec![2]), (*TOKEN_PROGRAM, vec![9]),
            (*SYSTEM_PROGRAM, vec![2])]);
        assert_eq!((cc[2].accounts[1].key, cc[4].accounts[0].key, cc[4].accounts[1].key, cc[4].accounts[2].key), (mid, mid, payer, payer), "create and close the same account, to the payer");
        assert_eq!(cc[0].data, [vec![2], 235_000u32.to_le_bytes().to_vec()].concat());
        assert_eq!(cc[1].data, [vec![4], (1u32 << 20).to_le_bytes().to_vec()].concat());
        // a held-set addition: the create without the close
        let kept = bundle_ixs(&Plan { payer, cu_limit: 230_000, loaded_data_limit: None, ata: Some(AtaOps { mint, token_program: *TOKEN_PROGRAM, close: false }), tip: None, cu_price: 0, extra_tips: vec![] },
            route.clone());
        assert_eq!(names(&kept), vec![(COMPUTE_BUDGET, vec![2]), (*ATA_PROGRAM, vec![1]), ([60; 32], vec![2])]);
        // compiled: the tip account static and last; the message parses back to the same instruction order
        let m = compile_v0(payer, &cc, [8; 32], &[], &[tip.0]).unwrap();
        let key = ed25519_dalek::SigningKey::from_bytes(&[3; 32]);
        let (tx, _) = crate::tx::parse_wire(&sign(&m, &key)).unwrap();
        let progs: Vec<Pk> = tx.ixs.iter().map(|ix| tx.keys[ix.program as usize]).collect();
        assert_eq!(progs, vec![COMPUTE_BUDGET, COMPUTE_BUDGET, *ATA_PROGRAM, [60; 32], *TOKEN_PROGRAM, *SYSTEM_PROGRAM]);
        assert_eq!(tx.keys[*tx.ixs[5].accounts.get(1).unwrap() as usize], tip.0);
        assert!(m.loadable.contains(&mid) && !m.loadable.contains(&payer) && !m.loadable.contains(&tip.0) && !m.loadable.contains(&*TOKEN_PROGRAM),
            "the payer signs, the tip stays static, the token program is invoked (the close): none of them loadable");
    }

    /// `[builder] loaded_data_limit = "auto"`: an upper bound of SIMD-0186's loaded size: every listed program at its
    /// on-chain size (PumpSwap's 10.5 MB programdata), the store's sizes, 64 KiB for an account it does not hold, 8,248 per
    /// table, +25% +256 KiB, rounded to 32 KiB, never above 64 MiB
    #[test]
    fn loaded_data_estimate_bounds() {
        let payer = [77u8; 32];
        let route = |prog: Pk| Ix { program: prog, accounts: vec![w([1; 32]), w([2; 32]), r(*TOKEN_PROGRAM)], data: vec![] };
        let pump = crate::venues::Venue::PumpSwap.program();
        let ixs = [cu_limit_ix(1), route(pump)];
        let est = loaded_data_estimate(&payer, &ixs, 1, &|k| (*k == [1; 32]).then_some(300));
        // payer (unknown: 64 KiB), the compute budget program, PumpSwap, account 1 (300 bytes), account 2 (unknown), SPL Token;
        // an upgradeable program with its programdata account (64 base bytes, the 45-byte header, the ELF region)
        let raw = 6 * 64 + 64 * 1024 + 64 + (36 + 64 + 45 + 10_485_715) + 300 + 64 * 1024 + (36 + 64 + 45 + 108_600) + 8_248u64;
        let want = (raw + raw / 4 + 256 * 1024).div_ceil(32 * 1024) * 32 * 1024;
        assert_eq!(est as u64, want);
        assert!(est % (32 * 1024) == 0 && est as u64 > raw);
        // repeated accounts count once; an unlisted program is generous
        let twice = loaded_data_estimate(&payer, &[cu_limit_ix(1), route(pump), route(pump)], 1, &|k| (*k == [1; 32]).then_some(300));
        assert_eq!(twice, est);
        assert!(loaded_data_estimate(&payer, &[route([42; 32])], 0, &|_| None) as u64 >= UNKNOWN_PROGRAM_BYTES);
        let many: Vec<Ix> = (0..40u8).map(|i| route([100 + i; 32])).collect();
        assert_eq!(loaded_data_estimate(&payer, &many, 4, &|_| None), MAX_LOADED_DATA, "capped at 64 MiB");
    }

    /// arbx-exec REVIEW.md #9: a v2 leg of 64+ accounts is re-read on chain as a NATIVE leg; the builder refuses it.
    #[test]
    fn v2_refuses_a_leg_of_64_accounts() {
        let (quote, x) = ([8; 32], [6; 32]);
        assert!(route_ix([1; 32], [2; 32], quote, 1, 1, &[legn(63, x, 0, 24), legn(7, quote, 0, 24)], None).is_ok());
        let e = route_ix([1; 32], [2; 32], quote, 1, 1, &[legn(64, x, 0, 24), legn(7, quote, 0, 24)], None).unwrap_err();
        assert!(e.contains("64 accounts"), "{e}");
        assert!(route_ix([1; 32], [2; 32], quote, 1, 1, &[legn(7, x, 0, 24), legn(200, quote, 0, 24)], None).is_err());
        // the same 64-account leg is fine in the v3 layout
        let o = V3Route { max_payer_lamport_drop: 0, count_lamports: false, tip: None };
        assert!(route_ix_v3([1; 32], [2; 32], quote, 1, 1, &[legn(64, x, 0, 24), legn(7, quote, 0, 24)], &[0, 0], &o).is_ok());
    }

    /// arbx-exec REVIEW.md #3: the engine's v3 encoder produces the program's pinned fixture bytes.
    #[test]
    fn v3_route_matches_the_shared_golden_vectors() {
        use arbx_v3::*;
        let (auth, quote, x) = ([2; 32], [8; 32], [6; 32]);
        let tip = CpiTip { bps: 3_000, floor: 0x3132_3334_3536_3738, cap: 0x4142_4344_4546_4748, account_ix: 7 };
        let o = V3Route { max_payer_lamport_drop: 0x2122_2324_2526_2728, count_lamports: true, tip: Some(tip) };
        let ix = route_ix_v3([1; 32], auth, quote, 0x0102_0304_0506_0708, 0x1112_1314_1516_1718, &[legn(70, x, 0xAA, 16), legn(3, quote, 0xBB, 16)], &[0, 0], &o).unwrap();
        assert_eq!(ix.data, golden("v3_route.hex"));
        assert_eq!(ix.accounts.len(), 2 + (2 + 70) + (2 + 3) + 2);
        assert_eq!((ix.accounts[ix.accounts.len() - 2].key, ix.accounts.last().unwrap().key), (*SYSTEM_PROGRAM, pk(JITO_TIP_ACCOUNTS[7])));
        assert!(ix.accounts.last().unwrap().writable && ix.accounts[0].signer);
        // leg flags: NATIVE_IN on leg 0 (18 accounts), AUTH_RO on leg 1 (70 accounts), no tip
        let o = V3Route { max_payer_lamport_drop: 0x2122_2324_2526_2728, count_lamports: true, tip: None };
        let ix = route_ix_v3([1; 32], auth, quote, 0x0102_0304_0506_0708, 0x1112_1314_1516_1718,
            &[legn(18, x, 0xCC, 24), legn(70, quote, 0xDD, 28)], &[LEG_NATIVE_IN, LEG_AUTH_RO], &o).unwrap();
        assert_eq!(ix.data, golden("v3_route_leg_flags.hex"));
    }

    /// The v3 encoder refuses what arbx-exec's parser refuses (REVIEW.md #2, #4, #6, #11, #14).
    #[test]
    fn v3_route_refuses_what_the_program_refuses() {
        use arbx_v3::*;
        let (auth, quote, x) = ([2; 32], [8; 32], [6; 32]);
        let legs = [legn(9, x, 0, 24), legn(9, quote, 0, 24)];
        let base = V3Route { max_payer_lamport_drop: 0, count_lamports: false, tip: None };
        let tip = Some(CpiTip { bps: 1_000, floor: 0, cap: 1, account_ix: 0 });
        let ok = |l: &[Leg], f: &[u8], o: &V3Route| route_ix_v3([1; 32], auth, quote, 1, 1, l, f, o);
        assert_eq!(ok(&legs, &[0, 0], &base).unwrap().data[1], PAYER_GUARD, "the guard is always set");
        assert!(ok(&legs, &[0, 0], &V3Route { tip, ..base }).is_err(), "#4: a CPI tip needs count_lamports");
        assert!(ok(&legs, &[0, 0], &V3Route { tip, count_lamports: true, ..base }).is_ok());
        assert!(ok(&legs, &[0, 0], &V3Route { tip: Some(CpiTip { bps: 1, floor: 0, cap: 1, account_ix: 8 }), count_lamports: true, ..base }).is_err());
        let cl = V3Route { count_lamports: true, ..base };
        assert!(ok(&legs, &[LEG_NATIVE_IN | LEG_NATIVE_OUT, 0], &cl).is_err(), "#6");
        assert!(ok(&legs, &[LEG_NATIVE_IN | LEG_AUTH_RO, 0], &cl).is_err(), "#14: AUTH_RO on a native leg");
        assert!(ok(&legs, &[LEG_NATIVE_IN, 0], &base).is_err(), "native needs count_lamports");
        assert!(ok(&legs, &[LEG_NATIVE_IN, LEG_AUTH_RO], &cl).is_ok());
        assert!(ok(&legs, &[0, LEG_NATIVE_IN], &cl).is_err(), "a token leg cannot feed a NATIVE_IN leg");
        assert!(ok(&legs, &[0x08, 0], &base).is_err(), "unknown leg flag");
        assert!(ok(&[legn(9, x, 0, 24), legn(9, [99; 32], 0, 24)], &[0, 0], &base).is_err(), "last leg into the quote");
        assert!(ok(&[legn(9, x, 0, 24), legn(9, auth, 0, 24)], &[0, LEG_NATIVE_OUT], &cl).is_ok(), "NATIVE_OUT last leg into the authority");
        // #11: 2 + (2 + 242) + (2 + 7) = 255 fits, one more does not
        assert!(ok(&[legn(242, x, 0, 24), legn(7, quote, 0, 24)], &[0, 0], &base).is_ok());
        assert!(ok(&[legn(243, x, 0, 24), legn(7, quote, 0, 24)], &[0, 0], &base).is_err());
        assert!(ok(&[legn(0, x, 0, 24), legn(7, quote, 0, 24)], &[0, 0], &base).is_err(), "a leg needs an account");
        assert!(ok(&legs, &[0], &base).is_err(), "one flags byte per leg");
    }

    /// The tip accounts the encoder names are arbx-exec's compiled-in list, in its order.
    #[test]
    fn v3_jito_tip_accounts_are_the_programs() {
        let src = include_str!("../program/arbx-exec/src/lib.rs");
        let start = src.find("JITO_TIP_ACCOUNTS_B58: [&str; 8] = [").unwrap();
        let block = &src[start..start + src[start..].find("];").unwrap()];
        let listed: Vec<&str> = block.lines().skip(1).filter_map(|l| l.trim().strip_prefix('"')).map(|l| &l[..l.find('"').unwrap()]).collect();
        assert_eq!(listed, arbx_v3::JITO_TIP_ACCOUNTS.to_vec());
    }

    #[test]
    fn cpmm_leg_is_direction_ordered() {
        let m = meta(Venue::RayCpmm);
        let mut pool = vec![0u8; 400];
        pool[8..40].copy_from_slice(&[11; 32]);
        pool[296..328].copy_from_slice(&[12; 32]);
        let payer = [77; 32];
        let a = LegIn { m: &m, pool: &pool, tin: m.t1, tout: m.t0, amount_in: 5, payer, pump: None, dlmm_live: &[], dlmm_end: None, dlmm_ext: None };
        let l = leg(&a).unwrap();
        assert_eq!(l.accounts[6].key, m.vault1, "vault in = the WSOL side");
        assert_eq!(l.accounts[7].key, m.vault0);
        assert_eq!(l.accounts[10].key, m.t1);
        assert_eq!(l.accounts[12].key, [12; 32]);
        assert_eq!(l.out, ata_of(&payer, &m.t0, &TOKEN_PROGRAM));
        assert_eq!(l.data.len(), 24);
        assert_eq!(u64::from_le_bytes(l.data[8..16].try_into().unwrap()), 5);
    }

    #[test]
    fn dlmm_bin_arrays_follow_the_quote() {
        let m = meta(Venue::Dlmm);
        let mut pool = vec![0u8; 904];
        pool[76..80].copy_from_slice(&(150i32).to_le_bytes());   // array 2
        pool[552..584].copy_from_slice(&[13; 32]);
        let live = [0i64, 1, 2, 3, 4];
        // selling X (t0): price falls, arrays 2, 1, then one past the quote's end (bin 75, array 1) -> 0; the bitmap
        // extension the store holds (it exists), read per send
        let a = LegIn { m: &m, pool: &pool, tin: m.t0, tout: m.t1, amount_in: 5, payer: [77; 32], pump: None, dlmm_live: &live, dlmm_end: Some(75), dlmm_ext: Some([9; 32]) };
        let l = leg(&a).unwrap();
        let arrays: Vec<Pk> = l.accounts[16..].iter().map(|x| x.key).collect();
        assert_eq!(arrays, vec![dlmm::bin_array_pda(&m.pool, 2), dlmm::bin_array_pda(&m.pool, 1), dlmm::bin_array_pda(&m.pool, 0)]);
        assert!(l.accounts[1].writable && l.accounts[1].key == [9; 32], "the real bitmap extension, writable");
        assert!(l.accounts[10].signer);
        assert_eq!(l.data.len(), 28);
        // no extension in the store: the program id in its place (Anchor's None)
        let none = leg(&LegIn { dlmm_ext: None, ..a }).unwrap();
        assert!(!none.accounts[1].writable && none.accounts[1].key == m.venue.program());
        let no = LegIn { dlmm_live: &[1, 3], ..a };
        assert!(leg(&no).is_err(), "active array not held");
    }

    /// PLAN WP-06 item 6: the arrays a DLMM leg names are the quote's window (contiguous held arrays from the active one,
    /// at most 5) as far as its end bin's array plus one buffer; a quote end outside the window is refused (the leg would
    /// run past the liquidity it names); an array outside the pair's own bitmap (-512..=511) needs the extension: a
    /// buffer array there is left out without one, a walked one is refused `dlmm_ext_needed`
    #[test]
    fn dlmm_arrays_capped_and_the_extension_rule() {
        let live: Vec<i64> = (-10..=10).collect();
        // buying X (y in): upward from array 0 (bin 10), the quote ends in array 2: 0, 1, 2 and the buffer 3
        assert_eq!(dlmm_arrays(10, false, &live, Some(150), false).unwrap(), vec![0, 1, 2, 3]);
        // never more than 5, whatever the end
        assert_eq!(dlmm_arrays(10, false, &live, Some(4 * 70 + 5), false).unwrap(), vec![0, 1, 2, 3, 4]);
        assert!(dlmm_arrays(10, false, &live, Some(5 * 70 + 5), false).unwrap_err().contains("outside-window"), "a quote end the window cannot hold");
        // a gap in the held arrays ends the window
        assert_eq!(dlmm_arrays(10, false, &[0, 1, 3, 4], Some(70), false).unwrap(), vec![0, 1]);
        assert!(dlmm_arrays(10, false, &[0, 1, 3, 4], Some(3 * 70), false).is_err());
        // selling X: downward
        assert_eq!(dlmm_arrays(-1, true, &live, Some(-140), false).unwrap(), vec![-1, -2, -3]);
        // the pair's own bitmap ends at array 511: the buffer array 512 is left out without an extension, kept with one
        let edge: Vec<i64> = (505..=515).collect();
        let bin = |a: i64| (a * 70 + 3) as i32;
        assert_eq!(dlmm_arrays(bin(510), false, &edge, Some(bin(511)), false).unwrap(), vec![510, 511]);
        assert_eq!(dlmm_arrays(bin(510), false, &edge, Some(bin(511)), true).unwrap(), vec![510, 511, 512]);
        // a walked array outside it: refused without the extension
        assert_eq!(dlmm_arrays(bin(511), false, &edge, Some(bin(512)), false).unwrap_err(), "dlmm_ext_needed");
        assert_eq!(dlmm_arrays(bin(511), false, &edge, Some(bin(512)), true).unwrap(), vec![511, 512, 513]);
        assert_eq!(dlmm_arrays(-512 * 70 + 3, true, &(-520..=-500).collect::<Vec<_>>(), None, false).unwrap(), vec![-512], "buffer -513 left out");
    }

    #[test]
    fn compiles_like_web3() {
        let payer = [1u8; 32];
        let ixs = vec![cu_limit_ix(200_000), cu_price_ix(40_000),
            Ix { program: [50; 32], accounts: vec![s(payer), w([2; 32]), r([3; 32]), w([4; 32])], data: vec![7] },
            transfer_ix(payer, [9; 32], 5_000)];
        let alt = Alt::new([60; 32], &[[3; 32], [4; 32], [9; 32]]);
        let m = compile_v0(payer, &ixs, [8; 32], &[&alt], &[[9; 32]]).unwrap();
        // static: payer | [2] (writable) | compute budget, program 50, system (readonly, first-use order); loaded: [4] w, [3] r
        let b = &m.bytes;
        assert_eq!(&b[..4], &[0x80, 1, 0, 3]);
        assert_eq!(b[4], 6);
        let keys: Vec<&[u8]> = (0..6).map(|i| &b[5 + 32 * i..37 + 32 * i]).collect();
        assert_eq!(keys, vec![&[1u8; 32][..], &[2u8; 32][..], &[9u8; 32][..], &COMPUTE_BUDGET[..], &[50u8; 32][..], &[0u8; 32][..]]);
        assert_eq!(m.locks, 8);
        let tail = &b[b.len() - 37..];
        assert_eq!(&tail[..1], &[1]);
        assert_eq!(&tail[1..33], &[60u8; 32][..]);
        assert_eq!(&tail[33..], &[1, 1, 1, 0], "writable [4] at index 1, readonly [3] at index 0");
        let key = ed25519_dalek::SigningKey::from_bytes(&[3; 32]);
        let signed = sign(&m, &key);
        let (tx, used) = crate::tx::parse_wire(&signed).unwrap();
        assert_eq!(used, signed.len());
        assert_eq!(tx.keys.len(), 6);
        assert_eq!(tx.lookups.len(), 1);
        assert_eq!(tx.cu_price_micro, Some(40_000));
    }

    /// Every leg, account for account and byte for byte, against arbed's own encoder (src/venues/encoders.ts
    /// buildSwap on its synthetic templates; testdata-legs.json is its output for these inputs).
    #[test]
    fn legs_match_arbed() {
        let want: serde_json::Value = serde_json::from_str(include_str!("testdata-legs.json")).unwrap();
        let payer = [77u8; 32];
        let g = PumpGlobal { disable_flags: 0, protocol: vec![[30; 32], [31; 32], [32; 32]], reserved: vec![[33; 32]], buyback: vec![[34; 32], [35; 32]] };
        let mut pump_pool = vec![0u8; 300];
        pump_pool[211..243].copy_from_slice(&[40; 32]);
        let check = |name: &str, l: Leg| {
            let w = &want[name];
            let got: Vec<serde_json::Value> = l.accounts.iter().map(|a| serde_json::json!([b58(&a.key), a.signer, a.writable])).collect();
            assert_eq!(serde_json::Value::Array(got), w["accts"], "{name}: accounts");
            assert_eq!(l.data.iter().map(|b| format!("{b:02x}")).collect::<String>(), w["data"].as_str().unwrap(), "{name}: data");
        };
        for (name, cashback) in [("pump", false), ("pumpcb", true)] {
            let m = meta(Venue::PumpSwap);
            let mut pool = pump_pool.clone();
            pool[244] = cashback as u8;
            for (dir, tin, tout) in [("buy", m.t1, m.t0), ("sell", m.t0, m.t1)] {
                let a = LegIn { m: &m, pool: &pool, tin, tout, amount_in: 5, payer, pump: Some(&g), dlmm_live: &[], dlmm_end: None, dlmm_ext: None };
                check(&format!("{name}_{dir}"), leg(&a).unwrap());
            }
        }
        let m = meta(Venue::RayCpmm);
        let mut pool = vec![0u8; 400];
        pool[8..40].copy_from_slice(&[11; 32]);
        pool[296..328].copy_from_slice(&[12; 32]);
        check("cpmm_buy", leg(&LegIn { m: &m, pool: &pool, tin: m.t1, tout: m.t0, amount_in: 5, payer, pump: None, dlmm_live: &[], dlmm_end: None, dlmm_ext: None }).unwrap());
        let m = meta(Venue::RayAmmV4);
        let mut pool = vec![0u8; 752];
        let bump = pda::find_program_address(&[b"amm authority"], &m.venue.program()).1;
        pool[8] = bump;
        check("ammv4_sell", leg(&LegIn { m: &m, pool: &pool, tin: m.t0, tout: m.t1, amount_in: 5, payer, pump: None, dlmm_live: &[], dlmm_end: None, dlmm_ext: None }).unwrap());
        let m = meta(Venue::Dlmm);
        let mut pool = vec![0u8; 904];
        pool[76..80].copy_from_slice(&150i32.to_le_bytes());
        pool[552..584].copy_from_slice(&[13; 32]);
        check("dlmm_buy", leg(&LegIn { m: &m, pool: &pool, tin: m.t1, tout: m.t0, amount_in: 5, payer, pump: None, dlmm_live: &[2], dlmm_end: None, dlmm_ext: None }).unwrap());
    }

    /// Review WP-06 #12: a cashback PumpSwap pool without pool_v2 would name the user volume accumulator's WSOL account,
    /// which the program could create at the payer's expense (rent we could not reclaim): the leg refuses it, both ways;
    /// with pool_v2 the block is not named and the leg builds
    #[test]
    fn pump_cashback_without_pool_v2_is_refused() {
        let m = meta(Venue::PumpSwap);
        let g = PumpGlobal { disable_flags: 0, protocol: vec![[30; 32]], reserved: vec![[33; 32]], buyback: vec![[34; 32]] };
        let mut pool = vec![0u8; 300];
        pool[244] = 1;
        let a = |pool: &[u8], tin: Pk, tout: Pk| leg(&LegIn { m: &m, pool, tin, tout, amount_in: 5, payer: [77; 32], pump: Some(&g), dlmm_live: &[], dlmm_end: None, dlmm_ext: None });
        for (tin, tout) in [(m.t1, m.t0), (m.t0, m.t1)] { assert_eq!(a(&pool, tin, tout).unwrap_err(), "pump-cashback-without-pool-v2"); }
        pool[211..243].copy_from_slice(&[40; 32]);
        for (tin, tout) in [(m.t1, m.t0), (m.t0, m.t1)] {
            let l = a(&pool, tin, tout).unwrap();
            assert!(!l.accounts.iter().any(|x| x.key == ata_of(&pump_uva(&[77; 32]), &m.t1, &m.t1_prog)), "no accumulator WSOL account");
        }
    }

    /// `auto`'s count from a message's own accounts (the dry run's) is the instructions' (the build's): the same keys
    /// counted once, a program invoked as one; only the lookup tables the message loads from count
    #[test]
    fn loaded_data_from_the_message_is_the_instructions() {
        let payer = [77u8; 32];
        let pump = crate::venues::Venue::PumpSwap.program();
        let route = Ix { program: pump, accounts: vec![w([1; 32]), w([2; 32]), r(*TOKEN_PROGRAM), r(pump)], data: vec![] };
        let ixs = [cu_limit_ix(1), route, close_account_ix([1; 32], payer, payer, *TOKEN_PROGRAM)];
        let size = |k: &Pk| (*k == [1; 32]).then_some(300);
        let m = compile_v0(payer, &ixs, [8; 32], &[], &[]).unwrap();
        let key = ed25519_dalek::SigningKey::from_bytes(&[3; 32]);
        let (tx, _) = crate::tx::parse_wire(&sign(&m, &key)).unwrap();
        let invoked: Vec<Pk> = tx.ixs.iter().map(|ix| tx.keys[ix.program as usize]).collect();
        let raw = loaded_data_raw(tx.keys.iter().map(|k| (*k, invoked.contains(k))), m.lookups, &size);
        assert_eq!(loaded_data_padded(raw), loaded_data_estimate(&payer, &ixs, 0, &size));
        assert_eq!(loaded_data_raw([([42; 32], false), ([42; 32], true)], 0, &|_| None), 64 + UNKNOWN_PROGRAM_BYTES, "once, invoked");
        assert_eq!(loaded_data_raw([], 2, &|_| None), 2 * ALT_BASE_BYTES);
    }

    #[test]
    fn reads_nonce_and_logs() {
        let mut d = vec![0u8; 80];
        d[0..4].copy_from_slice(&1u32.to_le_bytes());
        d[4..8].copy_from_slice(&1u32.to_le_bytes());
        d[40..72].copy_from_slice(&[5; 32]);
        assert_eq!(nonce_value(&d), Some([5; 32]));
        // (the logs' decoder moved to src/proglog.rs with WP-05: `proglog::tests::delivered_reads_the_out_records`)
        let e = serde_json::json!({ "InstructionError": [3, { "Custom": 1314390018u64 }] });
        assert_eq!(custom_code(&e), Some(ERR_PROFIT));
    }
}

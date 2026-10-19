//! Pump.fun launch detector for the shred-trigger path (observer / shadow use).
//!
//! Pure, allocation-light logic over a shred-decoded [`crate::tx::Tx`]: find a pump `create_v2` (or legacy
//! `create`) instruction and extract the launch — mint, bonding curve, and the creator (a create_v2 arg,
//! which is what the buy's `creator-vault` PDA keys on), plus any bundled dev buy as a launch-quality
//! signal. No RPC, no account fetch: everything is in the create transaction we already parsed.
//!
//! This module is OBSERVER-ONLY. It never builds, signs, or sends anything; it just classifies a tx.

use crate::tx::{Pk, Tx};
use std::sync::LazyLock;

/// Pump.fun bonding-curve program.
pub static PUMP: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"));
/// Default buy_exact_quote_in_v3 account [13] `buyback_fee_recipient`. The handler validates it is a valid pfee
/// BuybackVault but NOT that it matches the mint (confirmed: another mint's vault buys fine; an invalid account errors
/// 2000). So one known-good pool vault works for ANY launch -> no per-mint lookup needed. Update if it ever closes.
pub static DEFAULT_BUYBACK: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW"));

/// `create_v2` = sha256("global:create_v2")[..8]; legacy `create`; buy family (for the dev-buy signal).
pub const CREATE_V2_DISC: [u8; 8] = [0xd6, 0x90, 0x4c, 0xec, 0x5f, 0x8b, 0x31, 0xb4];
pub const CREATE_DISC: [u8; 8] = [0x18, 0x1e, 0xc8, 0x28, 0x05, 0x1c, 0x07, 0x77];
pub const BUY_DISC: [u8; 8] = [0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea];
pub const BUY_EXACT_SOL_IN_DISC: [u8; 8] = [0x38, 0xfc, 0x74, 0x08, 0x9e, 0xdf, 0xcd, 0x5f];
/// the CURRENT dev-buy instruction bundled in the create tx: buy_exact_quote_in_v3 (quote_amount_in u64 @[8..16]).
pub const BUY_EXACT_QUOTE_IN_V3_DISC: [u8; 8] = [0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88];
// Other pump buy variants a dev buy can use (authoritative arg layouts from the official IDL). SOL-in offset differs
// by family: the "spendable_*" buys carry the ACTUAL SOL/quote spent at [8..16]; the "amount + max_sol_cost" buys carry
// the token amount at [8..16] and the SOL cap at [16..24]. Reading only one disc undercounts the dev buy to ~0.
pub const BUY_EXACT_QUOTE_IN_V2_DISC: [u8; 8] = [0xc2, 0xab, 0x1c, 0x46, 0x68, 0x4d, 0x5b, 0x2f];
pub const BUY_V2_DISC: [u8; 8] = [0xb8, 0x17, 0xee, 0x61, 0x67, 0xc5, 0xd3, 0x3d];
pub const BUY_V3_DISC: [u8; 8] = [0x07, 0x05, 0x1d, 0xc4, 0xf5, 0x17, 0x65, 0x50];
/// Buy discs whose SOL-in (actual spend) is the first u64 arg, at data[8..16]: the spendable_* family.
pub const DEV_BUY_SOL_AT_8: [[u8; 8]; 3] = [BUY_EXACT_QUOTE_IN_V3_DISC, BUY_EXACT_QUOTE_IN_V2_DISC, BUY_EXACT_SOL_IN_DISC];
/// Buy discs whose SOL (max_sol_cost) is the SECOND u64 arg, at data[16..24] (amount/tokens is first): buy/buy_v2/buy_v3.
pub const DEV_BUY_SOL_AT_16: [[u8; 8]; 3] = [BUY_DISC, BUY_V2_DISC, BUY_V3_DISC];
/// Quote-model buys (17 accounts) whose account[13] IS the per-mint buyback_fee_recipient; extract [13] from these.
pub const QUOTE_MODEL_BUYS: [[u8; 8]; 2] = [BUY_EXACT_QUOTE_IN_V3_DISC, BUY_EXACT_QUOTE_IN_V2_DISC];

// create / create_v2 account order (IDL-confirmed): 0 mint, 1 mint_authority, 2 bonding_curve,
// 3 associated_bonding_curve, 4 global, 5 user(creator signer), ...
const A_MINT: usize = 0;
const A_BONDING_CURVE: usize = 2;
const A_ASSOC_BC: usize = 3;

/// A fresh launch, extracted with no RPC from the create transaction.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Launch {
    pub mint: Pk,
    pub bonding_curve: Pk,
    pub assoc_bonding_curve: Pk,
    pub creator: Pk,
    /// bundled dev buy in the same tx (lamports of max-SOL / spendable-SOL), 0 if none. Launch-quality signal.
    pub dev_buy_lamports: u64,
    pub is_create_v2: bool,
    /// create_v2 trailing args (after the 3 strings + 32-byte creator). Legacy `create` has none: all default 0/false.
    /// A non-vanilla launch (mayhem / holder-reward / creator-fee / cashback) needs a buyback fee-recipient account our
    /// buy_exact_sol_in does not pass (pump error 6062 BuybackFeeRecipientMissing), so the sniper skips them.
    pub is_mayhem: bool,
    pub is_cashback: bool,
    pub creator_fee_bps: u64,
    pub is_holder_reward: bool,
    /// buy_exact_quote_in_v3 account [13] `buyback_fee_recipient` (a per-mint pfee BuybackVault; no PDA seeds, validated
    /// in the handler). Not in the create_v2 ix, so unknown at detect ([0;32]); set from the launch's dev-buy or a
    /// lookup before the buy. A zero value means "not resolved".
    pub buyback_fee_recipient: Pk,
}

impl Launch {
    /// A strictly "vanilla" launch: no mayhem, no creator fee, no holder reward, no cashback. Kept for reporting/ the
    /// strict opt-in; it is NOT the live gate anymore (see is_snipeable).
    pub fn is_vanilla(&self) -> bool {
        !self.is_mayhem && self.creator_fee_bps == 0 && !self.is_holder_reward && !self.is_cashback
    }

    /// Launches our v3 buy can snipe at full margin. RE (2026-10-14, 45/45 of the target's non-vanilla snipes decoded)
    /// proved buy_exact_quote_in_v3 is FLAG-AGNOSTIC: holder_reward / mayhem / cashback launches use the IDENTICAL
    /// 17-account buy + 25-byte data we already land on vanilla (the old 6062 was the stale 16-account instruction, not
    /// the flags). So the only launches we skip are creator_fee_bps > 0, where a per-trade creator fee would eat our
    /// flip margin — the target skips these too (only 2/45 of its non-vanilla picks). --allow-nonvanilla overrides this.
    pub fn is_snipeable(&self) -> bool {
        // creator_fee==0 (avoid the per-trade fee) AND NOT mayhem: the target almost never snipes mayhem launches
        // (1% of his picks vs 38% of the universe — every_angle study 2026-10-15). Skipping mayhem is pre-buy-knowable,
        // cuts ~38% of launches (big trade-count/bleed reduction matching his selectivity), R-neutral. holder_reward is
        // kept (he prefers it, 46% of his picks). --allow-nonvanilla overrides to take everything.
        self.creator_fee_bps == 0 && !self.is_mayhem
    }
}

#[inline]
fn ix_with_disc<'a>(tx: &'a Tx, disc: &[u8; 8]) -> Option<&'a crate::tx::Ix> {
    tx.ixs.iter().find(|ix| {
        tx.keys.get(ix.program as usize) == Some(&*PUMP) && ix.data.len() >= 8 && ix.data[0..8] == *disc
    })
}

#[inline]
fn acct(tx: &Tx, ix: &crate::tx::Ix, pos: usize) -> Option<Pk> {
    tx.keys.get(*ix.accounts.get(pos)? as usize).copied()
}

/// Detect a pump.fun launch in a (shred-decoded) transaction. One cheap scan of `tx.ixs`.
/// Returns `None` for the vast majority of forwarded pump txs (plain buys/sells).
pub fn detect_launch(tx: &Tx) -> Option<Launch> {
    if tx.is_vote {
        return None;
    }
    let (create, is_v2) = match ix_with_disc(tx, &CREATE_V2_DISC) {
        Some(ix) => (ix, true),
        None => (ix_with_disc(tx, &CREATE_DISC)?, false),
    };
    let mint = acct(tx, create, A_MINT)?;
    let bonding_curve = acct(tx, create, A_BONDING_CURVE)?;
    let assoc_bonding_curve = acct(tx, create, A_ASSOC_BC)?;
    let args = parse_create_args(&create.data);
    let creator = args.creator.unwrap_or(mint);
    // the mayhem/cashback/creator-fee/holder-reward flags are create_v2-only; legacy `create` leaves them default.
    let (is_mayhem, is_cashback, creator_fee_bps, is_holder_reward) = if is_v2 {
        (args.is_mayhem, args.is_cashback, args.creator_fee_bps, args.is_holder_reward)
    } else { (false, false, 0, false) };

    // DEV BUY — the single fill-robust slot-0 PROFIT signal (selection study 2026-10-14, out-of-sample + fill-stressed):
    // only a SIZED `spendable` dev buy predicts a winning flip. The spendable_* buys (v3/v2/exact_sol_in) carry the EXACT
    // SOL spent at [8..16] — that is "conviction": >=2 SOL wins ~73-86% and stays positive under realistic fills. The
    // cap-family (buy/buy_v2/buy_v3) carries only max_sol_cost at [16..24], NOT the actual spend, and the u64::MAX
    // unbounded-cap buys (which I previously treated as high-conviction "always pass") are in fact the OPPOSITE — they
    // win only ~9.7%. So dev_buy_lamports = the sized spendable value ONLY; a cap/unbounded-only launch is NOT sized
    // conviction and reads 0 (it then fails the sized --min-dev-buy threshold, which is exactly what we want).
    let read_u64 = |ix: &crate::tx::Ix, off: usize| ix.data.get(off..off + 8).and_then(|s| <[u8; 8]>::try_from(s).ok()).map(u64::from_le_bytes);
    let dev_buy_lamports = DEV_BUY_SOL_AT_8.iter().filter_map(|d| ix_with_disc(tx, d).and_then(|ix| read_u64(ix, 8))).max().unwrap_or(0);
    // buyback_fee_recipient must be a member of pump's authorized global buyback POOL. In the STANDARD 17-account
    // quote-model buy, account[13] IS that pool member, so we copy it. BUT some creators (e.g. 9jwfZT1V) bundle a
    // NON-STANDARD quote-model dev buy (buy_exact_quote_in_v2 with 27 accounts) whose account[13] is the CREATOR'S
    // WALLET, not the buyback — copying that reverts 6057 BuybackFeeRecipientNotAuthorized. So we ONLY trust [13] from
    // a buy with exactly 17 accounts; otherwise fall back to DEFAULT_BUYBACK (A7hAgC, a confirmed authorized pool
    // member, accepted for any mint). Verified on-chain 2026-10-14: successful co-snipers use pool members (5YxQFdt3
    // etc.); the pool is global, so DEFAULT is a safe fallback whenever the standard layout isn't present.
    let buyback_fee_recipient = QUOTE_MODEL_BUYS.iter()
        .filter_map(|d| ix_with_disc(tx, d))
        .filter(|ix| ix.accounts.len() == 17)
        .find_map(|ix| ix.accounts.get(13).and_then(|&i| tx.keys.get(i as usize)).copied())
        .unwrap_or(*DEFAULT_BUYBACK);

    Some(Launch { buyback_fee_recipient, mint, bonding_curve, assoc_bonding_curve, creator, dev_buy_lamports, is_create_v2: is_v2,
        is_mayhem, is_cashback, creator_fee_bps, is_holder_reward })
}

/// Extract the metadata URI (3rd borsh string) from a create/create_v2 tx. Zero RPC: it is in the ix data.
pub fn launch_uri(tx: &Tx) -> Option<String> {
    let create = match ix_with_disc(tx, &CREATE_V2_DISC) { Some(ix) => ix, None => ix_with_disc(tx, &CREATE_DISC)? };
    let data = &create.data;
    let mut p = 8usize;
    let mut uri = None;
    for i in 0..3 {
        let len = data.get(p..p + 4).and_then(|b| b.try_into().ok()).map(u32::from_le_bytes)? as usize;
        let start = p + 4;
        let end = start.checked_add(len)?;
        if i == 2 { uri = data.get(start..end).map(|b| String::from_utf8_lossy(b).into_owned()); }
        p = end;
    }
    uri
}

/// Host of a metadata URI, e.g. "ipfs.io" from "https://ipfs.io/ipfs/..". The launch-tool fingerprint.
pub fn uri_host(uri: &str) -> &str {
    uri.split("://").nth(1).unwrap_or(uri).split('/').next().unwrap_or("")
}

/// URI-HOST BLACKLIST gate ("like the wallet"): fire on EVERYTHING except the pure bundler-bot launch tools 4yFAz
/// never buys from (gg.sc, launchblitz, jake-workers, googleapis, *.trycloudflare). Keeps his whole legit host tail.
pub fn is_bot_launchpad(tx: &Tx) -> bool {
    const BOT: [&str; 4] = ["gg.sc", "ipfs.launchblitz.ai", "pf.jake-98f.workers.dev", "storage.googleapis.com"];
    match launch_uri(tx) {
        Some(u) => { let h = uri_host(&u); BOT.iter().any(|b| *b == h) || h.ends_with(".trycloudflare.com") }
        None => false,
    }
}

/// URI-HOST selection gate (reverse-engineered from 4yFAz, OOS lift ~3.7): he snipes tokens launched via the official
/// pump UI / trusted launchpads and skips third-party bundler-bot launch tools. True = trusted host.
pub fn trusted_launch_host(tx: &Tx) -> bool {
    const HOSTS: [&str; 4] = ["ipfs.io", "metadata.j7tracker.io", "m.rapidlaunch.io", "gateway.pinata.cloud"];
    launch_uri(tx).map(|u| { let h = uri_host(&u); HOSTS.iter().any(|x| *x == h) }).unwrap_or(false)
}

/// Parsed create/create_v2 args: the creator and (create_v2) the trailing flags. All default when absent (defensive).
#[derive(Default)]
struct CreateArgs { creator: Option<Pk>, is_mayhem: bool, is_cashback: bool, creator_fee_bps: u64, is_holder_reward: bool }

/// create/create_v2 args (borsh): name:string, symbol:string, uri:string, creator:pubkey,
/// then (create_v2) is_mayhem_mode:bool(1), is_cashback_enabled:bool(1), creator_fee_bps:u64(8), is_holder_reward:bool(1).
/// Walk the three length-prefixed strings, read the 32-byte creator, then the trailing flags if present.
fn parse_create_args(data: &[u8]) -> CreateArgs {
    let mut p = 8usize; // discriminator
    for _ in 0..3 {
        let len = match data.get(p..p + 4).and_then(|b| b.try_into().ok()).map(u32::from_le_bytes) {
            Some(l) => l as usize,
            None => return CreateArgs::default(),
        };
        p = match p.checked_add(4).and_then(|x| x.checked_add(len)) { Some(x) => x, None => return CreateArgs::default() };
    }
    let creator = data.get(p..p + 32).and_then(|b| b.try_into().ok());
    let mut a = CreateArgs { creator, ..Default::default() };
    p += 32;
    // trailing flags (create_v2 only; absent on legacy create -> defaults via get())
    a.is_mayhem = data.get(p).map(|&b| b != 0).unwrap_or(false);
    a.is_cashback = data.get(p + 1).map(|&b| b != 0).unwrap_or(false);
    a.creator_fee_bps = data.get(p + 2..p + 10).and_then(|b| b.try_into().ok()).map(u64::from_le_bytes).unwrap_or(0);
    a.is_holder_reward = data.get(p + 10).map(|&b| b != 0).unwrap_or(false);
    a
}

/// Interest that forwards ONLY pump.fun bonding-curve program transactions — for the shadow observer.
/// The shred feed decodes every tx and forwards just those whose static keys include a watched program,
/// so watching PUMP delivers every launch (and every pump buy/sell) with zero extra cost elsewhere.
pub fn pump_interest() -> crate::feeds::Interest {
    let mut keys: rustc_hash::FxHashSet<Pk> = Default::default();
    keys.insert(*PUMP);
    crate::feeds::Interest { keys, tables: std::sync::RwLock::new(Default::default()) }
}

// =====================================================================================================================
// RACE-GATE helpers (2026-10-18). ADDITIVE ONLY: nothing above changes. Used by snipe_engine behind the default-off
// flags --dev-from-cap / --race-gate / --race-log. Pure functions over the shred-decoded tx: no RPC, no sends.
// =====================================================================================================================

/// SOL (lamports) to buy `tokens` on a curve whose virtual SOL reserve is `vq` (constant product with the fresh k).
pub fn curve_cost(vq: u64, tokens: u64) -> u64 {
    let k = CURVE_VQ0 as u128 * CURVE_VT0 as u128;
    let vq = (vq as u128).max(1);
    let vt = k / vq;
    let t = tokens as u128;
    if t == 0 || t >= vt { return 0; }
    let nvq = k.div_ceil(vt - t);
    nvq.saturating_sub(vq).min(u64::MAX as u128) as u64
}

/// Fresh bonding-curve virtual reserves (lamports / raw token units, 6 decimals).
pub const CURVE_VQ0: u64 = 30_000_000_000;
pub const CURVE_VT0: u64 = 1_073_000_000_000_000;
/// Token-2022 program (create_v2 launches mint under it).
pub static TOKEN_2022: LazyLock<Pk> = LazyLock::new(|| crate::tx::pk("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"));

#[inline]
fn pump_ix_disc(tx: &Tx, ix: &crate::tx::Ix) -> Option<[u8; 8]> {
    if tx.keys.get(ix.program as usize) != Some(&*PUMP) || ix.data.len() < 8 { return None; }
    ix.data[0..8].try_into().ok()
}

/// --dev-from-cap: the SOL a CAP-family dev buy (buy / buy_v2 / buy_v3: token amount at data[8..16], max_sol_cost at
/// [16..24], often u64::MAX) really spends, priced on the fresh constant-product curve: sol = vq*T/(vt-T), applied in
/// sequence when the create tx holds several. detect_launch reads these as 0 SOL, so every cap-family launch was
/// skipped (e.g. GHEc1Z7L, BuyV2 unlimited, T=193593934369826 -> 6.604 SOL). Returns 0 with no cap-family buy.
pub fn dev_buy_cap_lamports(tx: &Tx) -> u64 {
    let (mut vq, mut vt, mut total) = (CURVE_VQ0 as u128, CURVE_VT0 as u128, 0u128);
    for ix in tx.ixs.iter() {
        let Some(d) = pump_ix_disc(tx, ix) else { continue };
        if !DEV_BUY_SOL_AT_16.contains(&d) || ix.data.len() < 16 { continue; }
        let t = u64::from_le_bytes(ix.data[8..16].try_into().unwrap_or([0u8; 8])) as u128;
        if t == 0 || t >= vt { continue; }
        let nvt = vt - t;
        let nvq = (vq * vt).div_ceil(nvt);
        total += nvq - vq;
        vq = nvq;
        vt = nvt;
    }
    total.min(u64::MAX as u128) as u64
}

/// Dev-buy instruction family in the create tx: 0 none, 1 sized (spendable SOL at [8..16]), 2 cap-family with a real
/// max_sol_cost, 3 cap-family with an UNLIMITED max_sol_cost (> 1e15 lamports).
pub fn dev_buy_kind(tx: &Tx) -> u8 {
    let mut k = 0u8;
    for ix in tx.ixs.iter() {
        let Some(d) = pump_ix_disc(tx, ix) else { continue };
        if DEV_BUY_SOL_AT_8.contains(&d) { return 1; }
        if DEV_BUY_SOL_AT_16.contains(&d) {
            let cap = ix.data.get(16..24).and_then(|b| <[u8; 8]>::try_from(b).ok()).map(u64::from_le_bytes).unwrap_or(0);
            k = k.max(if cap > 1_000_000_000_000_000 { 3 } else { 2 });
        }
    }
    k
}

/// What the race gate / race log knows about a create tx at shred time (no RPC).
#[derive(Clone, Debug, Default)]
pub struct CreateInfo {
    pub cu_price: u64,
    pub cu_limit: u32,
    pub nsig: u8,
    pub nkeys: usize,
    pub n_lookups: usize,
    pub v1: bool,
    pub n_ixs: usize,
    pub t22: bool,
    /// largest plain SOL transfer in the tx to a non-signer (the sender tip, if any) and its destination
    pub tip_lamports: u64,
    pub tip_to: Option<Pk>,
    pub name: String,
    pub symbol: String,
    pub uri_host: String,
}

/// The three borsh strings (name, symbol, uri) of a create/create_v2 ix.
pub fn create_strings(tx: &Tx) -> Option<(String, String, String)> {
    let create = match ix_with_disc(tx, &CREATE_V2_DISC) { Some(ix) => ix, None => ix_with_disc(tx, &CREATE_DISC)? };
    let data = &create.data;
    let mut p = 8usize;
    let mut out: Vec<String> = Vec::with_capacity(3);
    for _ in 0..3 {
        let len = data.get(p..p + 4).and_then(|b| b.try_into().ok()).map(u32::from_le_bytes)? as usize;
        let start = p + 4;
        let end = start.checked_add(len)?;
        out.push(String::from_utf8_lossy(data.get(start..end)?).into_owned());
        p = end;
    }
    let uri = out.pop()?;
    let symbol = out.pop()?;
    let name = out.pop()?;
    Some((name, symbol, uri))
}

pub fn create_info(tx: &Tx) -> CreateInfo {
    let system: Pk = [0u8; 32];
    let nsig = tx.num_signers as usize;
    let (mut tip_lamports, mut tip_to) = (0u64, None);
    for ix in tx.ixs.iter() {
        if tx.keys.get(ix.program as usize) != Some(&system) || ix.data.len() < 12 || ix.data[0..4] != [2, 0, 0, 0] { continue; }
        let lam = u64::from_le_bytes(ix.data[4..12].try_into().unwrap_or([0u8; 8]));
        let Some(&di) = ix.accounts.get(1) else { continue };
        if (di as usize) < nsig { continue; } // to a signer = funding, not a tip
        if lam > tip_lamports { tip_lamports = lam; tip_to = tx.keys.get(di as usize).copied(); }
    }
    let (name, symbol, uri) = create_strings(tx).unwrap_or_default();
    CreateInfo {
        cu_price: tx.cu_price().unwrap_or(0),
        cu_limit: tx.cu_limit.unwrap_or(0),
        nsig: tx.num_signers,
        nkeys: tx.keys.len(),
        n_lookups: tx.lookups.len(),
        v1: tx.v1,
        n_ixs: tx.ixs.len(),
        t22: tx.keys.contains(&*TOKEN_2022),
        tip_lamports,
        tip_to,
        uri_host: uri_host(&uri).to_string(),
        name,
        symbol,
    }
}

/// How a non-create pump tx touches a watched mint (race window): a top-level pump BUY (sized: the spendable SOL; cap-family:
/// token amount + max_sol_cost, priced by the caller on the curve), a SELL, or OTHER (the
/// mint is in the static keys but the pump call is not top-level, e.g. a sniper's own program CPI-ing pump).
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum MintTouch { Buy(u64), BuyCap { tokens: u64, max_sol: u64 }, Sell, Other }

pub fn mint_touch(tx: &Tx, mint: &Pk) -> Option<MintTouch> {
    if !tx.keys.contains(mint) { return None; }
    let read = |ix: &crate::tx::Ix, off: usize| ix.data.get(off..off + 8).and_then(|s| <[u8; 8]>::try_from(s).ok()).map(u64::from_le_bytes);
    let mut sell = false;
    for ix in tx.ixs.iter() {
        let Some(d) = pump_ix_disc(tx, ix) else { continue };
        if DEV_BUY_SOL_AT_8.contains(&d) { return Some(MintTouch::Buy(read(ix, 8).unwrap_or(0))); }
        if DEV_BUY_SOL_AT_16.contains(&d) {
            return Some(MintTouch::BuyCap { tokens: read(ix, 8).unwrap_or(0), max_sol: read(ix, 16).unwrap_or(0) });
        }
        if d != CREATE_V2_DISC && d != CREATE_DISC { sell = true; }
    }
    Some(if sell { MintTouch::Sell } else { MintTouch::Other })
}

#[cfg(test)]
mod tests {
    use super::*;
    use base64::Engine;

    // DRY RUN: a real mainnet pump create_v2 (mint 7oeU…pump, slot 456491124), raw signed-tx wire bytes.
    // We decode it with the SAME parser the shred feed uses (tx::parse_wire) and assert detection against
    // on-chain ground truth. No RPC, no live feed.
    const CREATE_V2_B64: &str = include_str!("../tests/fixtures/create_v2.b64");

    #[test]
    fn detects_real_create_v2() {
        let wire = base64::engine::general_purpose::STANDARD
            .decode(CREATE_V2_B64.trim())
            .expect("b64");
        let (tx, _) = crate::tx::parse_wire(&wire).expect("parse_wire");
        let l = detect_launch(&tx).expect("should detect a launch");
        assert!(l.is_create_v2, "should be create_v2");
        assert_eq!(crate::tx::b58(&l.mint), "7oeUduY1zhUwQ3YdSP9CGDYF8nYzfRdhgqtc6wAbpump");
        assert_eq!(crate::tx::b58(&l.bonding_curve), "2HsrtwTMpLGqdXb9W2JXa6Cta6dD4y8rMjqoALaK33BJ");
        assert_eq!(crate::tx::b58(&l.assoc_bonding_curve), "E7Ybq8JpT5rCsAcGxLVmGZrCPW6T18U1qFUybqPoKD2n");
        // creator must be a non-zero, non-sentinel key parsed from the args
        assert_ne!(l.creator, l.mint, "creator should parse from args, not fall back to mint");
        assert_ne!(l.creator, [0u8; 32]);
        eprintln!(
            "DRY RUN OK  mint={} bc={} creator={} dev_buy_lamports={}",
            crate::tx::b58(&l.mint), crate::tx::b58(&l.bonding_curve),
            crate::tx::b58(&l.creator), l.dev_buy_lamports
        );
    }

    #[test]
    fn ignores_non_create() {
        // an empty/again-decoded junk tx must not be seen as a launch
        let (tx, _) = crate::tx::parse_wire(&[]).unwrap_or((crate::tx::Tx::default(), 0));
        assert!(detect_launch(&tx).is_none());
    }
}

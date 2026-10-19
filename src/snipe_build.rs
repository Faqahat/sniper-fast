//! Pump.fun launch-sniper transaction builder: the CURRENT on-chain BUY (`buy_exact_quote_in_v3`) and SELL
//! (`sell_exact_tokens_in_v3`) instructions — a WSOL quote-model (the old `buy_exact_sol_in`/`sell` are dead on-chain,
//! reverting 6020 BuyZeroAmount) — and the full unsigned instruction lists (compute budget + ATA-creates + WSOL
//! wrap/unwrap + buy/sell). The v3 instructions are reverse-engineered from successful txs (the IDL is stale).
//!
//! Pure, no RPC, no signing, no sending. Every on-chain fact (program ids, discriminators, account order,
//! PDA seeds) is the VERIFIED pump Anchor IDL / live-transaction layout given in the task; the unit tests at
//! the bottom re-derive the constant PDAs (global, event authority, fee config) and assert they match the
//! published addresses, so a wrong seed is caught offline.
//!
//! The buy spends an exact amount of SOL (`spendable_sol_in`) with a slippage floor (`min_tokens_out`); the
//! sell burns an exact token `amount` with a SOL floor (`min_sol_output`). Account WRITABILITY and ORDER
//! follow the IDL exactly, and differ between buy and sell (sell drops the two volume accumulators and swaps
//! the creator_vault / token_program positions) — do not "normalize" them.

use crate::build::{self, Ix, Meta};
use crate::pda;
use crate::snipe::{Launch, PUMP};
use crate::tx::{pk, Pk};
use std::sync::LazyLock;

/// DEAD on-chain (2026-10): `buy_exact_sol_in`/`sell` are the stale-IDL discriminators. buy_exact_sol_in reverts with
/// 6020 BuyZeroAmount (computes 0 tokens) and appears in ZERO successful recent txs. Kept only for reference.
pub const BUY_EXACT_SOL_IN_DISC: [u8; 8] = [0x38, 0xfc, 0x74, 0x08, 0x9e, 0xdf, 0xcd, 0x5f];
pub const SELL_DISC: [u8; 8] = [0x33, 0xe6, 0x85, 0xa4, 0x01, 0x7f, 0x83, 0xad];

/// CURRENT working pump buy: `buy_exact_quote_in_v3` (quote = WSOL). disc = first 8 bytes seen on-chain; the IDL is
/// fully stale (no v3 instructions), so this is reverse-engineered from successful txs (ref sigs in the report).
/// args: quote_amount_in u64, min_tokens_out u64, then one trailing byte (0x00 on the working txs; an Option<bool>
/// track-volume tag left None). 17 accounts (see `buy_ix`).
pub const BUY_EXACT_QUOTE_IN_V3_DISC: [u8; 8] = [0xe1, 0xf7, 0x50, 0x1e, 0xd5, 0xb3, 0x84, 0x88];
/// CURRENT working pump sell: `sell_exact_tokens_in_v3` (quote = WSOL). args: amount(tokens) u64, min_quote_out u64,
/// trailing byte. Account layout UNCONFIRMED (no sell ref decoded yet) — mirrors the buy minus user_volume_accumulator.
pub const SELL_EXACT_TOKENS_IN_V3_DISC: [u8; 8] = [0x64, 0x6c, 0xbd, 0x84, 0x80, 0x67, 0x6c, 0xf9];
/// CURRENT working pump sell: `sell_v3` (disc from the official IDL), 17 accounts IDENTICAL to buy_exact_quote_in_v3,
/// args (amount tokens u64, min_sol_output u64) — NO trailing byte. (sell_exact_tokens_in_v3 above is not the one used.)
pub const SELL_V3_DISC: [u8; 8] = [0x1c, 0x92, 0xde, 0x77, 0x26, 0xc4, 0x69, 0xd5];

/// Wrapped SOL mint (the quote of the v3 quote-model). Its token accounts are LEGACY SPL Token (pda::TOKEN_PROGRAM).
pub static WSOL: LazyLock<Pk> = LazyLock::new(|| pk("So11111111111111111111111111111111111111112"));

/// pump fee recipient (writable in both ixs). Pump ROTATES fee recipients and validates against the global config's
/// allowed set; AVmoTthd… is a currently-valid rotated recipient (a confirmed-successful current buy used it; the old
/// CebN5WGQ… was stale and failed the global check).
pub static FEE_RECIPIENT: LazyLock<Pk> = LazyLock::new(|| pk("AVmoTthdrX6tKt4nDjco2D775W2YK3sDhxPcMmzUAmTY"));
/// pump fee program (PFEE).
pub static PFEE: LazyLock<Pk> = LazyLock::new(|| pk("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"));
/// Buyback remaining accounts the on-chain program expects AFTER the published 16 (the IDL is stale: a successful
/// current buy_exact_sol_in / sell has 18 / 16 accounts). Both WRITABLE, pfee/fee-config-global (same across mints):
///   16 buyback fee recipient (a lazily-created PDA, currently empty); 17 pfee buyback account (owned by PFEE).
pub static BUYBACK_FEE_RECIPIENT: LazyLock<Pk> = LazyLock::new(|| pk("AkQixH133X7f9nS4ZLGCei35iFY12rpzyAsYeuxHjRSA"));
pub static PFEE_BUYBACK: LazyLock<Pk> = LazyLock::new(|| pk("A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW"));

/// `[b"global"]` of PUMP (== 4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf).
pub static GLOBAL: LazyLock<Pk> = LazyLock::new(|| pda::find_program_address(&[b"global"], &PUMP).0);
/// `[b"__event_authority"]` of PUMP (== Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1).
pub static EVENT_AUTHORITY: LazyLock<Pk> = LazyLock::new(|| pda::find_program_address(&[b"__event_authority"], &PUMP).0);
/// `[b"global_volume_accumulator"]` of PUMP.
pub static GLOBAL_VOLUME_ACCUMULATOR: LazyLock<Pk> = LazyLock::new(|| pda::find_program_address(&[b"global_volume_accumulator"], &PUMP).0);
/// `[b"fee_config", PUMP]` of PFEE (== 8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt).
pub static FEE_CONFIG: LazyLock<Pk> = LazyLock::new(|| pda::find_program_address(&[b"fee_config", &*PUMP], &PFEE).0);

#[inline]
fn meta(key: Pk, signer: bool, writable: bool) -> Meta { Meta { key, signer, writable } }

/// `[b"creator-vault", creator]` of PUMP (HYPHEN in the seed; writable).
pub fn creator_vault(creator: &Pk) -> Pk { pda::find_program_address(&[b"creator-vault", creator], &PUMP).0 }
/// `[b"user_volume_accumulator", user]` of PUMP (writable; buy only).
pub fn user_volume_accumulator(user: &Pk) -> Pk { pda::find_program_address(&[b"user_volume_accumulator", user], &PUMP).0 }
/// `[b"bonding-curve", mint]` of PUMP (HYPHEN in the seed).
pub fn bonding_curve(mint: &Pk) -> Pk { pda::find_program_address(&[b"bonding-curve", mint], &PUMP).0 }
/// the bonding curve's associated token account for `mint`, in TOKEN-2022 (pda::ata encodes [owner, token_program, mint]).
pub fn assoc_bonding_curve(bonding_curve: &Pk, mint: &Pk) -> Pk { pda::ata(bonding_curve, mint, &pda::TOKEN_2022) }
/// the user's associated token account for `mint`, in TOKEN-2022.
pub fn assoc_user(user: &Pk, mint: &Pk) -> Pk { pda::ata(user, mint, &pda::TOKEN_2022) }
/// the WSOL (quote) associated token account of `owner`, in LEGACY SPL Token.
pub fn assoc_quote(owner: &Pk) -> Pk { pda::ata(owner, &WSOL, &pda::TOKEN_PROGRAM) }

/// The CURRENT pump buy: `buy_exact_quote_in_v3` (quote = WSOL), 17 accounts. `spend_lamports` = quote_amount_in
/// (WSOL to spend), `min_tokens_out` = base-token slippage floor. `track_volume` is ignored (the trailing byte is a
/// None Option<bool> = 0x00 on every working tx). Account ORDER + WRITABILITY are from a decoded successful on-chain
/// buy_exact_quote_in_v3 (disc e1f7…); each account is derived generically from `user` / `l` so it is correct for ANY
/// signer. CONFIRMED: 0-12,14-16. slot 13 (associated_quote_creator_vault) is a best-guess pending a live check.
pub fn buy_ix(user: Pk, l: &Launch, spend_lamports: u64, min_tokens_out: u64, _track_volume: bool) -> Ix {
    let base = l.mint;
    let bc = l.bonding_curve;
    let cv = creator_vault(&l.creator);
    let accounts = vec![
        meta(*GLOBAL, false, false),                               // 0  global (r)
        meta(base, false, false),                                  // 1  base_mint (r)
        meta(*WSOL, false, false),                                 // 2  quote_mint = WSOL (r)
        meta(*pda::TOKEN_2022, false, false),                      // 3  base_token_program = TOKEN-2022 (r)
        meta(*pda::TOKEN_PROGRAM, false, false),                   // 4  quote_token_program = legacy SPL (r)
        meta(bc, false, true),                                     // 5  bonding_curve (W)
        meta(pda::ata(&bc, &base, &pda::TOKEN_2022), false, true), // 6  associated_base_bonding_curve (W)
        meta(pda::ata(&bc, &WSOL, &pda::TOKEN_PROGRAM), false, true), // 7 associated_quote_bonding_curve (W)
        meta(user, true, true),                                    // 8  user (W, SIGNER)
        meta(pda::ata(&user, &base, &pda::TOKEN_2022), false, true), // 9 associated_base_user (W)
        meta(assoc_quote(&user), false, true),                     // 10 associated_quote_user (WSOL, W)
        meta(user_volume_accumulator(&user), false, true),         // 11 user_volume_accumulator (W)
        meta(*FEE_CONFIG, false, false),                           // 12 fee_config (r)
        meta(l.buyback_fee_recipient, false, true),                // 13 buyback_fee_recipient (W) — per-mint pfee BuybackVault
        meta(*pda::SYSTEM_PROGRAM, false, false),                  // 14 system_program (r)
        meta(*EVENT_AUTHORITY, false, false),                      // 15 event_authority (r)
        meta(*PUMP, false, false),                                 // 16 program (r)
    ];
    let mut data = BUY_EXACT_QUOTE_IN_V3_DISC.to_vec();
    data.extend(spend_lamports.to_le_bytes());  // quote_amount_in (WSOL)
    data.extend(min_tokens_out.to_le_bytes());   // min base tokens out
    data.push(0u8);                               // trailing Option<bool> tag = None (0x00 on all working txs)
    Ix { program: *PUMP, accounts, data }
}

/// The CURRENT pump sell: `sell_exact_tokens_in_v3` (quote = WSOL). `amount` = base tokens to sell, `min_sol_output`
/// = quote (WSOL) floor. UNCONFIRMED account layout: mirrors the v3 buy MINUS user_volume_accumulator (sells do not
/// track user volume); confirm against a decoded sell_exact_tokens_in_v3 before relying on it.
pub fn sell_ix(user: Pk, l: &Launch, amount: u64, min_sol_output: u64) -> Ix {
    let base = l.mint;
    let bc = l.bonding_curve;
    // sell_v3: 17 accounts IDENTICAL to buy_exact_quote_in_v3 (same order, same derivations).
    let accounts = vec![
        meta(*GLOBAL, false, false),                               // 0  global (r)
        meta(base, false, false),                                  // 1  base_mint (r)
        meta(*WSOL, false, false),                                 // 2  quote_mint = WSOL (r)
        meta(*pda::TOKEN_2022, false, false),                      // 3  base_token_program (r)
        meta(*pda::TOKEN_PROGRAM, false, false),                   // 4  quote_token_program = legacy SPL (r)
        meta(bc, false, true),                                     // 5  bonding_curve (W)
        meta(pda::ata(&bc, &base, &pda::TOKEN_2022), false, true), // 6  associated_base_bonding_curve (W)
        meta(pda::ata(&bc, &WSOL, &pda::TOKEN_PROGRAM), false, true), // 7 associated_quote_bonding_curve (W)
        meta(user, true, true),                                    // 8  user (W, SIGNER)
        meta(pda::ata(&user, &base, &pda::TOKEN_2022), false, true), // 9 associated_base_user (W)
        meta(assoc_quote(&user), false, true),                     // 10 associated_quote_user (W)
        meta(user_volume_accumulator(&user), false, true),         // 11 user_volume_accumulator (W)
        meta(*FEE_CONFIG, false, false),                           // 12 fee_config (r)
        meta(l.buyback_fee_recipient, false, true),                // 13 buyback_fee_recipient (W)
        meta(*pda::SYSTEM_PROGRAM, false, false),                  // 14 system_program (r)
        meta(*EVENT_AUTHORITY, false, false),                      // 15 event_authority (r)
        meta(*PUMP, false, false),                                 // 16 program (r)
    ];
    let mut data = SELL_V3_DISC.to_vec();
    data.extend(amount.to_le_bytes());           // base tokens to sell
    data.extend(min_sol_output.to_le_bytes());   // min quote (SOL) out
    Ix { program: *PUMP, accounts, data }
}

/// How to assemble a full buy message.
#[derive(Clone, Copy, Debug)]
pub struct BuyPlan {
    pub spend_lamports: u64,
    pub min_tokens_out: u64,
    pub cu_limit: u32,
    /// compute-unit price, micro-lamports per CU; 0 = no SetComputeUnitPrice ix.
    pub cu_price_micro: u64,
    /// prepend an idempotent TOKEN-2022 ATA-create for the buyer's associated_user account.
    pub create_ata: bool,
    pub track_volume: bool,
    /// durable-nonce mode: (nonce account, nonce authority). AdvanceNonceAccount is prepended as the FIRST ix;
    /// the caller must then compile the message with the nonce's stored value as the blockhash and keep the
    /// nonce account + RecentBlockhashes sysvar static. None = plain recent-blockhash mode.
    pub nonce: Option<(Pk, Pk)>,
    /// wrap native SOL into the WSOL ATA before the buy (transfer + SyncNative). false = use the WSOL already held
    /// (avoids the native-balance limit; the quote ATA must already hold >= spend_lamports WSOL).
    pub wrap: bool,
}

impl Default for BuyPlan {
    fn default() -> Self {
        BuyPlan { spend_lamports: 0, min_tokens_out: 0, cu_limit: 120_000, cu_price_micro: 0, create_ata: true, track_volume: true, nonce: None, wrap: false }
    }
}

/// The full unsigned instruction list for a snipe buy (v3 quote-model), in order:
///   [AdvanceNonceAccount (durable-nonce only)] > SetComputeUnitLimit > [SetComputeUnitPrice] >
///   create-idempotent base ATA (TOKEN-2022) > create-idempotent quote WSOL ATA (legacy) >
///   transfer spend_lamports into the WSOL ATA > SyncNative > buy_exact_quote_in_v3.
/// The buy spends WSOL (the quote), so we WRAP: fund the WSOL ATA with `spend_lamports` and SyncNative before the buy.
/// Unwrap (close the WSOL ATA back to SOL) happens on the SELL side, see `sell_message_ixs`.
/// Compile with `build::compile_v0` and sign with `build::sign`.
pub fn buy_message_ixs(user: Pk, l: &Launch, p: &BuyPlan) -> Vec<Ix> {
    let mut ixs = Vec::with_capacity(8);
    if let Some((nonce, auth)) = p.nonce {
        ixs.push(build::advance_nonce_ix(nonce, auth)); // MUST be first
    }
    ixs.push(build::cu_limit_ix(p.cu_limit));
    if p.cu_price_micro > 0 {
        ixs.push(build::cu_price_ix(p.cu_price_micro));
    }
    if p.create_ata {
        // base-token (TOKEN-2022) ATA to receive the bought tokens
        ixs.push(build::create_ata_idempotent_ix(user, user, l.mint, *pda::TOKEN_2022));
    }
    // WSOL (quote) wrap: create the legacy-SPL WSOL ATA, fund it with the spend, then SyncNative so its token balance
    // reflects the lamports. pump then pulls WSOL from it for the buy.
    let wsol_ata = assoc_quote(&user);
    ixs.push(build::create_ata_idempotent_ix(user, user, *WSOL, *pda::TOKEN_PROGRAM));
    if p.wrap {
        // fund the WSOL ATA with spend_lamports of native SOL, then SyncNative (needs that much native balance).
        ixs.push(build::transfer_ix(user, wsol_ata, p.spend_lamports));
        ixs.push(build::sync_native_ix(wsol_ata));
    }
    ixs.push(buy_ix(user, l, p.spend_lamports, p.min_tokens_out, p.track_volume));
    ixs
}

/// The full unsigned instruction list for a snipe sell (v3 quote-model), in order:
///   SetComputeUnitLimit > [SetComputeUnitPrice] > sell_exact_tokens_in_v3 >
///   close WSOL ATA -> user (UNWRAP the quote proceeds back to native SOL) > close empty base ATA -> user (reclaim rent).
/// `amount` = base tokens to sell, `min_sol_output` = quote floor.
pub fn sell_message_ixs(user: Pk, l: &Launch, amount: u64, min_sol_output: u64, cu_limit: u32, cu_price_micro: u64, close_wsol: bool) -> Vec<Ix> {
    let mut ixs = Vec::with_capacity(5);
    ixs.push(build::cu_limit_ix(cu_limit));
    if cu_price_micro > 0 {
        ixs.push(build::cu_price_ix(cu_price_micro));
    }
    ixs.push(sell_ix(user, l, amount, min_sol_output));
    // unwrap ONLY when we actually hold WSOL in the ATA (i.e. we wrapped on the buy). v3 SOL trades settle in
    // NATIVE SOL, so a no-wrap round-trip never touches the WSOL ATA — closing a nonexistent one fails the whole tx.
    if close_wsol {
        ixs.push(build::close_account_ix(assoc_quote(&user), user, user, *pda::TOKEN_PROGRAM));
    }
    // reclaim the (now-empty) base ATA rent
    ixs.push(build::close_account_ix(assoc_user(&user, &l.mint), user, user, *pda::TOKEN_2022));
    ixs
}

/// A Launch built straight from a target (mint/creator), deriving the bonding curve and its ATA. Use when
/// sniping a known mint without the create transaction in hand.
pub fn launch_from_target(mint: Pk, creator: Pk) -> Launch {
    let bc = bonding_curve(&mint);
    Launch { mint, bonding_curve: bc, assoc_bonding_curve: assoc_bonding_curve(&bc, &mint), creator, dev_buy_lamports: 0, is_create_v2: true,
        is_mayhem: false, is_cashback: false, creator_fee_bps: 0, is_holder_reward: false, buyback_fee_recipient: *crate::snipe::DEFAULT_BUYBACK }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::tx::b58;

    fn sample() -> Launch {
        // the task's sample launch (mint 7oeU…pump); bonding curve + abc derived.
        launch_from_target(pk("7oeUduY1zhUwQ3YdSP9CGDYF8nYzfRdhgqtc6wAbpump"), pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q"))
    }

    #[test]
    fn constant_pdas_match_published_addresses() {
        assert_eq!(b58(&GLOBAL), "4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf");
        assert_eq!(b58(&EVENT_AUTHORITY), "Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1");
        assert_eq!(b58(&FEE_CONFIG), "8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt");
    }

    #[test]
    fn derived_bonding_curve_matches_sample() {
        // the task's sample bonding_curve for mint 7oeU…pump
        assert_eq!(b58(&bonding_curve(&pk("7oeUduY1zhUwQ3YdSP9CGDYF8nYzfRdhgqtc6wAbpump"))), "2HsrtwTMpLGqdXb9W2JXa6Cta6dD4y8rMjqoALaK33BJ");
    }

    #[test]
    fn buy_ix_layout_v3() {
        let user = pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q");
        let l = sample();
        let ix = buy_ix(user, &l, 1_000_000, 42, true);
        assert_eq!(ix.program, *PUMP);
        assert_eq!(ix.accounts.len(), 17, "buy_exact_quote_in_v3 takes 17 accounts");
        assert_eq!(ix.data[..8], BUY_EXACT_QUOTE_IN_V3_DISC);
        // args: disc(8) + quote_amount_in u64 + min_tokens_out u64 + 1 trailing byte (0x00)
        assert_eq!(ix.data.len(), 8 + 8 + 8 + 1);
        assert_eq!(u64::from_le_bytes(ix.data[8..16].try_into().unwrap()), 1_000_000);
        assert_eq!(u64::from_le_bytes(ix.data[16..24].try_into().unwrap()), 42);
        assert_eq!(ix.data[24], 0);
        let a = &ix.accounts;
        assert_eq!(a[0].key, *GLOBAL);
        assert_eq!(a[1].key, l.mint);
        assert_eq!(a[2].key, *WSOL);
        assert_eq!(a[3].key, *pda::TOKEN_2022);
        assert_eq!(a[4].key, *pda::TOKEN_PROGRAM);
        assert_eq!(a[5].key, l.bonding_curve);
        assert_eq!(a[6].key, assoc_bonding_curve(&l.bonding_curve, &l.mint));
        assert_eq!(a[7].key, pda::ata(&l.bonding_curve, &WSOL, &pda::TOKEN_PROGRAM));
        assert_eq!(a[8].key, user);
        assert_eq!(a[9].key, assoc_user(&user, &l.mint));
        assert_eq!(a[10].key, assoc_quote(&user));
        assert_eq!(a[11].key, user_volume_accumulator(&user));
        assert_eq!(a[12].key, *FEE_CONFIG);
        assert_eq!(a[13].key, pda::ata(&creator_vault(&l.creator), &WSOL, &pda::TOKEN_PROGRAM));
        assert_eq!(a[14].key, *pda::SYSTEM_PROGRAM);
        assert_eq!(a[15].key, *EVENT_AUTHORITY);
        assert_eq!(a[16].key, *PUMP);
        let w: Vec<bool> = a.iter().map(|m| m.writable).collect();
        assert_eq!(w, vec![false, false, false, false, false, true, true, true, true, true, true, true, false, true, false, false, false]);
        assert!(a[8].signer && a.iter().enumerate().all(|(i, m)| i == 8 || !m.signer), "only user signs");
    }

    #[test]
    fn sell_ix_layout_v3() {
        let user = pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q");
        let l = sample();
        let ix = sell_ix(user, &l, 5_000, 7);
        assert_eq!(ix.accounts.len(), 16, "sell_exact_tokens_in_v3 takes 16 accounts (buy minus user_volume_accumulator) — UNCONFIRMED");
        assert_eq!(ix.data[..8], SELL_EXACT_TOKENS_IN_V3_DISC);
        assert_eq!(ix.data.len(), 8 + 8 + 8 + 1);
        assert_eq!(u64::from_le_bytes(ix.data[8..16].try_into().unwrap()), 5_000);
        assert_eq!(u64::from_le_bytes(ix.data[16..24].try_into().unwrap()), 7);
        let a = &ix.accounts;
        assert_eq!(a[8].key, user);
        assert_eq!(a[10].key, assoc_quote(&user));
        assert_eq!(a[11].key, *FEE_CONFIG);
        assert_eq!(a[15].key, *PUMP);
        let w: Vec<bool> = a.iter().map(|m| m.writable).collect();
        assert_eq!(w, vec![false, false, false, false, false, true, true, true, true, true, true, false, true, false, false, false]);
    }

    #[test]
    fn buy_message_wraps_wsol() {
        let user = pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q");
        let l = sample();
        let p = BuyPlan { spend_lamports: 1_000_000, min_tokens_out: 0, cu_limit: 120_000, cu_price_micro: 500_000, create_ata: true, track_volume: true, nonce: None, wrap: false };
        let ixs = buy_message_ixs(user, &l, &p);
        // cu_limit, cu_price, base-ATA, WSOL-ATA, transfer, sync_native, buy
        assert_eq!(ixs.len(), 7);
        assert_eq!(ixs[0].data[0], 2); // SetComputeUnitLimit
        assert_eq!(ixs[1].data[0], 3); // SetComputeUnitPrice
        assert_eq!(ixs[2].program, *pda::ATA_PROGRAM); // base ATA
        assert_eq!(ixs[3].program, *pda::ATA_PROGRAM); // WSOL ATA
        assert_eq!(ixs[4].program, *pda::SYSTEM_PROGRAM); // transfer into WSOL ATA
        assert_eq!(ixs[4].data[..4], 2u32.to_le_bytes());
        assert_eq!(u64::from_le_bytes(ixs[4].data[4..12].try_into().unwrap()), 1_000_000);
        assert_eq!(ixs[5].program, *pda::TOKEN_PROGRAM); // SyncNative
        assert_eq!(ixs[5].data, vec![17]);
        assert_eq!(ixs[6].data[..8], BUY_EXACT_QUOTE_IN_V3_DISC);
        // durable-nonce mode prepends AdvanceNonceAccount as the first ix
        let nonce = pk("4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf");
        let p2 = BuyPlan { nonce: Some((nonce, user)), create_ata: false, cu_price_micro: 0, ..p };
        let ixs2 = buy_message_ixs(user, &l, &p2);
        // advance_nonce, cu_limit, WSOL-ATA, transfer, sync, buy
        assert_eq!(ixs2.len(), 6);
        assert_eq!(ixs2[0].program, *pda::SYSTEM_PROGRAM);
        assert_eq!(ixs2[0].data, 4u32.to_le_bytes()); // AdvanceNonceAccount
        assert_eq!(ixs2[5].data[..8], BUY_EXACT_QUOTE_IN_V3_DISC);
    }

    #[test]
    fn sell_message_unwraps_wsol() {
        let user = pk("3tNPvytXB9yTZLgh5RGdjrXVxHp89vGeCiwx9juqgp7q");
        let l = sample();
        // close_wsol=true: cu_limit, sell, close-WSOL, close-base
        let ixs = sell_message_ixs(user, &l, 5_000, 0, 120_000, 0, true);
        assert_eq!(ixs.len(), 4);
        assert_eq!(ixs[0].data[0], 2);
        assert_eq!(ixs[1].data[..8], SELL_EXACT_TOKENS_IN_V3_DISC);
        assert_eq!(ixs[2].program, *pda::TOKEN_PROGRAM); // CloseAccount (WSOL ATA)
        assert_eq!(ixs[2].data, vec![9]);
        assert_eq!(ixs[3].program, *pda::TOKEN_2022); // CloseAccount (base ATA)
        assert_eq!(ixs[3].data, vec![9]);
        // close_wsol=false (no-wrap default): no WSOL close, just sell + base-ATA close
        let ixs = sell_message_ixs(user, &l, 5_000, 0, 120_000, 0, false);
        assert_eq!(ixs.len(), 3);
        assert_eq!(ixs[2].program, *pda::TOKEN_2022); // CloseAccount (base ATA) only
    }
}

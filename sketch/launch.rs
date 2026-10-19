//! SKETCH ONLY — pump.fun launch (create) detector for the shred-trigger path.
//! Not wired into lib.rs / the build. No send-path changes. Design doc: sketch/pump-sniper-detector.md
//!
//! Reuses the existing decode: `feeds::Event::Tx(Arrival{ tx: Tx, slot, t_rx, .. })` already gives us
//! `tx.ixs: Vec<Ix>` (program index + account indices + data) and `tx.keys: Vec<Pk>`. A pump `create`
//! that arrives from a raw-shred feed is fully decoded the moment its last shred lands — the same instant
//! the sniper 4yFAz... fires. All buy accounts are either constant, taken straight from the create ix,
//! or a cheap PDA derive — zero RPC on the hot path.

use crate::tx::{Ix, Pk, Tx};
use crate::pda::{ata, find_program_address};

// ---- constants (verified on-chain 2026-10-13) ----
pub const PUMP: Pk      = /* 6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P */ b58!("6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P");
pub const PFEE: Pk      = /* pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ */ b58!("pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ");
pub const TOKEN_2022: Pk = b58!("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb");
pub const WSOL: Pk       = b58!("So11111111111111111111111111111111111111112");
pub const FEE_RECIPIENT: Pk = b58!("CebN5WGQ4jvEPvsVU4EoHEpgzq1VV7AbicfhtW4xC9iM"); // pump fee recipient (writable, not a PDA)

// discriminators — confirmed against pump's on-chain Anchor IDL (sketch/pump_idl.json).
// Current launches are create_v2; also watch legacy `create`.
pub const CREATE_V2_DISC: [u8; 8] = [0xd6, 0x90, 0x4c, 0xec, 0x5f, 0x8b, 0x31, 0xb4]; // sha256("global:create_v2")
pub const CREATE_DISC:    [u8; 8] = [0x18, 0x1e, 0xc8, 0x28, 0x05, 0x1c, 0x07, 0x77]; // legacy create
// buy family (any of these in the create tx = a dev buy; we SEND buy_exact_sol_in)
pub const BUY_DISC:            [u8; 8] = [0x66, 0x06, 0x3d, 0x12, 0x01, 0xda, 0xeb, 0xea];
pub const BUY_EXACT_SOL_IN_DISC: [u8; 8] = [0x38, 0xfc, 0x74, 0x08, 0x9e, 0xdf, 0xcd, 0x5f];

/// Account order of pump `create_v2` (IDL-confirmed; matches the live create tx):
///   0 mint(S)  1 mint_authority  2 bonding_curve  3 assoc_bonding_curve  4 global
///   5 user(creator, signer)  6 system  7 token_program  8 ata_program  9..13 mayhem*  14 event_auth  15 pump
/// NOTE: the `creator` used by the buy's creator_vault is a create_v2 ARG (data), not an account.
const CREATE_MINT: usize = 0;
const CREATE_BONDING_CURVE: usize = 2;
const CREATE_ASSOC_BC: usize = 3;

/// A fresh launch worth evaluating, extracted with no RPC from the create tx itself.
#[derive(Clone, Debug)]
pub struct Launch {
    pub mint: Pk,
    pub bonding_curve: Pk,        // from create ix acct 2 — no derive needed
    pub assoc_bonding_curve: Pk,  // from create ix acct 3
    pub creator: Pk,             // parsed from create ix data tail (see below)
    pub dev_buy_lamports: u64,   // from the sibling buy ix in the SAME tx (0 if none)
    pub slot: u64,
}

/// Pull the pump program key index once (program ids are always static keys, never from a LUT).
#[inline]
fn pump_ix<'a>(tx: &'a Tx, disc: &[u8; 8]) -> Option<&'a Ix> {
    tx.ixs.iter().find(|ix| {
        tx.keys.get(ix.program as usize) == Some(&PUMP)
            && ix.data.len() >= 8
            && &ix.data[0..8] == disc
    })
}

#[inline]
fn acct(tx: &Tx, ix: &Ix, pos: usize) -> Option<Pk> {
    tx.keys.get(*ix.accounts.get(pos)? as usize).copied()
}

/// Detect a pump.fun launch in a shred-decoded transaction. Cheap: one scan of `tx.ixs`.
/// Returns None for the 99% of forwarded pump txs that are plain buys/sells.
pub fn detect_launch(tx: &Tx, slot: u64) -> Option<Launch> {
    let create = pump_ix(tx, &CREATE_V2_DISC).or_else(|| pump_ix(tx, &CREATE_DISC))?;
    let mint = acct(tx, create, CREATE_MINT)?;
    let bonding_curve = acct(tx, create, CREATE_BONDING_CURVE)?;
    let assoc_bonding_curve = acct(tx, create, CREATE_ASSOC_BC)?;

    // create_v2 args (borsh): name:str, symbol:str, uri:str, creator:pubkey, ...
    // creator is the 32 bytes immediately after the 3 strings — and it is exactly what the buy's
    // creator_vault PDA keys on (bonding_curve.creator). Parsing it here = no RPC read of the curve.
    let creator = parse_creator(&create.data).unwrap_or(mint); // mint as sentinel if layout shifts

    // dev buy bundled in the create tx (same signer, same slot) — the single best launch-quality signal
    let dev_buy_lamports = pump_ix(tx, &BUY_DISC).or_else(|| pump_ix(tx, &BUY_EXACT_SOL_IN_DISC))
        .and_then(|b| b.data.get(8..16))               // buy: disc|amount_u64|max_sol; exact_sol_in: disc|spendable_sol_u64|min_out
        .and_then(|s| s.try_into().ok())
        .map(u64::from_le_bytes)
        .unwrap_or(0);

    Some(Launch { mint, bonding_curve, assoc_bonding_curve, creator, dev_buy_lamports, slot })
}

/// Borsh string = u32 len + bytes. Walk name/symbol/uri, then read the 32-byte creator.
fn parse_creator(data: &[u8]) -> Option<Pk> {
    let mut p = 8usize; // skip discriminator
    for _ in 0..3 {
        let len = u32::from_le_bytes(data.get(p..p + 4)?.try_into().ok()?) as usize;
        p += 4 + len;
    }
    let c: [u8; 32] = data.get(p..p + 32)?.try_into().ok()?;
    Some(c)
}

// ---- the BUY account set — AUTHORITATIVE from pump's IDL (sketch/pump_idl.json) -----------------
// Send `buy_exact_sol_in` (disc 38fc74089edfcd5f, args: spendable_sol_in u64, min_tokens_out u64,
// track_volume OptionBool) — fixed SOL in with slippage protection. `buy` has the identical 16-account
// list. EVERY account is constant, from the create ix, or a zero-RPC PDA derive. Account ORDER below is
// the exact IDL order the instruction expects.
//
//  idx name                         how                                              verified
//   0 global                        fpa(["global"], PUMP)  == 4wTV1Ymi               ✅ const
//   1 fee_recipient    (W)          pump fee recipient CebN5WGQ                        const (writable)
//   2 mint                          from create ix                                     ✅
//   3 bonding_curve    (W)          fpa(["bonding-curve", mint], PUMP)                 ✅
//   4 associated_bonding_curve (W)  ata(bonding_curve, token_program, mint)            ✅
//   5 associated_user  (W)          ata(user, token_program, mint)                     ✅ (sniper pre-creates a
//                                                                                         non-canonical acct for speed)
//   6 user            (W,S)         our wallet                                         signer
//   7 system_program
//   8 token_program                 TOKEN-2022 for these mints
//   9 creator_vault    (W)          fpa(["creator-vault", creator], PUMP)  <-- HYPHEN  ✅ (creator from create_v2 arg)
//  10 event_authority               fpa(["__event_authority"], PUMP) == Ce6TQqe        ✅ const
//  11 program                       PUMP
//  12 global_volume_accumulator     fpa(["global_volume_accumulator"], PUMP)           ✅ (IDL — it IS in the buy)
//  13 user_volume_accumulator (W)   fpa(["user_volume_accumulator", user], PUMP)       ✅ (correction: present)
//  14 fee_config                    fpa(["fee_config", PUMP], PFEE) == 8Wf5Ti          ✅
//  15 fee_program                   PFEE (pfeeUxB)                                      const
//
// src/build.rs uses [b"creator_vault", ..] (UNDERSCORE) under PUMPSWAP — that is the AMM seed; do NOT
// reuse it for the bonding curve. The sniper's FCdY wrapper passes these in a custom order/subset — we
// follow the IDL order, not FCdY's.
pub struct BuyAccounts {
    pub global: Pk,
    pub fee_recipient: Pk,
    pub mint: Pk,
    pub bonding_curve: Pk,
    pub associated_bonding_curve: Pk,
    pub associated_user: Pk,
    pub user: Pk,
    pub creator_vault: Pk,
    pub event_authority: Pk,
    pub global_volume_accumulator: Pk,
    pub user_volume_accumulator: Pk,
    pub fee_config: Pk,
    // token_program (TOKEN_2022), system, PUMP, PFEE are constants the builder splices in by position.
}

impl Launch {
    /// Build the full IDL `buy_exact_sol_in` account set for our wallet. No RPC. `token_program` is the
    /// mint's token program (TOKEN-2022 for current pump launches; pass it in to stay correct if pump
    /// ever mixes legacy mints).
    pub fn buy_accounts(&self, wallet: &Pk, token_program: &Pk) -> BuyAccounts {
        let bc = self.bonding_curve; // == fpa(["bonding-curve", mint], PUMP); taken free from the create ix
        BuyAccounts {
            global: find_program_address(&[b"global"], &PUMP).0,
            fee_recipient: FEE_RECIPIENT,
            mint: self.mint,
            bonding_curve: bc,
            associated_bonding_curve: ata(&bc, &self.mint, token_program),
            associated_user: ata(wallet, &self.mint, token_program),
            user: *wallet,
            creator_vault: find_program_address(&[b"creator-vault", self.creator.as_ref()], &PUMP).0,
            event_authority: find_program_address(&[b"__event_authority"], &PUMP).0,
            global_volume_accumulator: find_program_address(&[b"global_volume_accumulator"], &PUMP).0,
            user_volume_accumulator: find_program_address(&[b"user_volume_accumulator", wallet.as_ref()], &PUMP).0,
            fee_config: find_program_address(&[b"fee_config", PUMP.as_ref()], &PFEE).0,
        }
    }
}

// ---- WHERE THIS HOOKS IN (no edits made; see doc) -----------------------------------------------
// 1) feeds Interest: add PUMP to `interest.keys` so create txs forward from shreds.
//    (config: watched programs; Interest::wants already matches any static program key.)
// 2) engine::Engine::on_tx(a: Arrival): after the existing arb path, add:
//        if let Some(l) = snipe::detect_launch(&a.tx, a.slot) {
//            if self.snipe_filter.passes(&l) {           // dev_buy band, creator allow/deny, 1-per-mint
//                self.snipe_fire(&l, a.t_rx);            // fill pre-signed nonce buy -> existing exec send
//            }
//        }
// 3) snipe_fire: take a durable-nonce buy TEMPLATE (slotfix), splice in l.buy_accounts(&wallet),
//    set opcode/amount, submit on the SAME slot via the current send path. No new send logic.

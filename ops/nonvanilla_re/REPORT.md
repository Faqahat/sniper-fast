# Non-Vanilla pump.fun Buy — Account-Layout Reverse Engineering

Target wallet: `4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3`
Date: 2026-10-14. Work dir: `/root/nonvanilla_re/`. RPC: constantk staked.
Pump program: `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P`
PFEE program (CORRECTED): `pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ` (task approx `...E4gUjSGAfvkx` was WRONG; verified as the owner of fee_config).

## TL;DR (headline result)
**Non-vanilla buys use the EXACT SAME 17-account layout and the EXACT SAME 25-byte
instruction data as vanilla.** There are NO extra accounts, NO different accounts,
NO extra data bytes for holder-reward / creator-fee / mayhem / cashback launches.
`buy_exact_quote_in_v3` is FLAG-AGNOSTIC. The official IDL confirms it: the instruction
defines exactly 17 accounts and ZERO optional/remaining accounts.

Therefore the ~23% of his picks we miss are NOT lost to a buy-construction revert —
they are lost because our DETECTOR/CLASSIFIER skips them (the vanilla-only gate).
**The fix is to relax the vanilla filter, not to append accounts to buy_ix.**

## Sample
- 45 NON-VANILLA buys decoded (100% of the 45 non-vanilla records in enriched200.json),
  spanning: HOLDERREWARD x41, CREATORFEE(100bps) x2, MAYHEM x1, ODD(000001) x1.
  No CASHBACK launch appears in this wallet's 200-snipe window.
- 200/200 buys (vanilla + non-vanilla) decoded for the cross-account tally.
- Buy instruction is a CPI from the wallet's own program `FCdY3UTqSrbKab7ba3V6LDVSwYue2GD1xyq8tPY6Yr3o`
  (found as an INNER instruction, not top-level).

## Account-count / data-length distribution (all 45 non-vanilla)
    account-count: {17: 45}      <- every single one is 17 accounts
    data-length:   {25: 45}      <- every single one is 25 bytes
    per kind: HOLDERREWARD(17,25)x41  CREATORFEE(17,25)x2  MAYHEM(17,25)x1  ODD(17,25)x1

## Instruction DATA layout (identical vanilla & non-vanilla)
    [0:8]   discriminator  e1f7501ed5b38488
    [8:16]  spendable_quote_in  u64 LE  (lamports of WSOL to spend)
    [16:24] min_tokens_out      u64 LE  (his snipes: usually =1, i.e. no slippage floor)
    [24]    partial_fill        1 byte  OptionBool, always 0x00 in his buys
    => total 25 bytes. No extra args for any flag.

## The 17 accounts (concrete non-vanilla example: HOLDERREWARD mint 7HpR..pump)
    [ 0] global                         4wTV1YmiEkRvAtNtsSGPtUrqRYQMe5SKy2uB4Jjaxnjf  (const PDA ["global"]@pump)
    [ 1] base_mint                      <mint>
    [ 2] quote_mint                     So11111111111111111111111111111111111111112  (WSOL, const)
    [ 3] base_token_program             TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb  (TOKEN-2022, 199/200)
    [ 4] quote_token_program            TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA  (legacy SPL, const)
    [ 5] bonding_curve                  PDA ["bonding-curve", mint]@pump
    [ 6] associated_base_bonding_curve  ATA(bonding_curve, mint, TOKEN-2022)
    [ 7] associated_quote_bonding_curve ATA(bonding_curve, WSOL, legacy SPL)
    [ 8] user (signer)                  4yFAz...fEQrG3
    [ 9] associated_base_user           ATA(user, mint, TOKEN-2022)
    [10] associated_quote_user          ATA(user, WSOL, legacy SPL)  = 2FLvcd... (const for this user)
    [11] user_volume_accumulator        PDA ["user_volume_accumulator", user]@pump  = 6zVPNJ... (const for this user)
    [12] fee_config                     8Wf5TiAheLUqBrKXeYg2JtAFFMWtKdG2BSFgqUcPVwTt  (CONST, owner=PFEE)
    [13] buyback_fee_recipient          ONE OF 8 GLOBAL recipients (see below)
    [14] system_program                 11111111111111111111111111111111
    [15] event_authority                Ce6TQqeHC9p8KetsN6JsjHK7UTZk7nasjjnr7XxXp9F1  (const PDA ["__event_authority"]@pump)
    [16] program                        6EF8rr...wF6P  (pump program)

## Cross-launch tally of the variable accounts (all 200 buys)
    fee_config[12]:           1 distinct  = 8Wf5Ti... (CONSTANT across every buy)
    quote_token_program[4]:   1 distinct  = Tokenkeg (legacy SPL, CONSTANT)
    base_token_program[3]:    TOKEN-2022 199/200, legacy SPL 1/200 (the 1 is a non-"pump"-suffix mint, NOT flag-related)
    buyback_fee_recipient[13]: 8 distinct, ~25 uses each (a FIXED rotating pool, see below)

## [13] buyback_fee_recipient — the ONLY per-buy variable
- It is NOT creator-derived and NOT in the create tx: two DIFFERENT creators
  (holder-reward mint & odd mint) use the SAME recipient EHAAiTxc..., proving it is global.
- It is ONE OF 8 fixed recipients stored IN THE PUMP GLOBAL ACCOUNT
  (4wTV1Y..., owner=pump program), at consecutive 32-byte slots, offsets 741..965 step 32.
  The 8 unique recipients:
    5YxQFdt3Tr9zJLvkFccqXVUwhdTWJQc1fFg2YPbxvxeD   (off 741)
    9M4giFFMxmFGXtc3feFzRai56WbBqehoSeRE5GK7gf7    (off 773)
    GXPFM2caqTtQYC2cJ5yJRi9VDkpsYZXzYdwYpGnLmtDL   (off 805)
    3BpXnfJaUTiwXnJNe7Ej1rcbzqTTQUvLShZaWazebsVR   (off 837)
    5cjcW9wExnJJiqgLjq7DEG75Pm6JBgE1hNv4B2vHXUW6   (off 869)
    EHAAiTxcdDwQ3U4bU6YcMsQGaekdzLS3B5SmYo46kJtL   (off 901)
    5eHhjP8JaYkz83CWwvGU2uMUXefd3AazWGx4gpcuEEYD   (off 933)
    A7hAgCzFw14fejgCp387JUJRMNyz4j89JKnhtKU8piqW   (off 965)
- The SAME 8-member pool serves vanilla AND non-vanilla identically. Whatever valid
  recipient our code already passes for vanilla is equally valid for non-vanilla.

## Buildable at slot 0? YES — fully, for every non-vanilla kind.
Every one of the 17 accounts is either (a) a constant, (b) a PDA from mint/user we have
at detection, (c) a standard ATA, or (d) a member of the fixed 8-recipient global pool.
NONE depend on the launch flags, the creator, or anything extracted from the create tx
beyond the mint itself. There is nothing flag-specific to extract. Slot-0 build of a
non-vanilla buy is exactly the slot-0 build of a vanilla buy.

## What the official IDL says about accounts beyond the core set
`buy_exact_quote_in_v3` (disc e1f7501ed5b38488) in github.com/pump-fun/pump-public-docs
idl/pump.json (fetched, current, has the v3 ix) defines EXACTLY these 17 accounts,
with ZERO marked optional and NO remaining_accounts clause:
  global, base_mint, quote_mint, base_token_program, quote_token_program, bonding_curve,
  associated_base_bonding_curve, associated_quote_bonding_curve, user, associated_base_user,
  associated_quote_user, user_volume_accumulator, fee_config, buyback_fee_recipient,
  system_program, event_authority, program.
Args: spendable_quote_in u64, min_tokens_out u64, partial_fill OptionBool. Nothing else.
=> Creator fees, holder rewards and cashback are handled by SEPARATE instructions
   (collect_creator_fee_v2 / distribute_creator_fees_v2, distribute_fee_to_holders,
   claim_cashback_v2) that run AFTER/outside the buy. They never add accounts to the buy.

## create_v2 flag layout (for the clone filter, NOT the buy)
create_v2 disc d6904cec5f8b31b4. Trailing bytes after the 32-byte creator pubkey (11 bytes):
    [0]     is_mayhem_mode       bool       (1 byte)
    [1]     is_cashback_enabled  OptionBool (1 byte)
    [2:10]  creator_fee_bps      OptionU64  (u64 LE, 8 bytes)
    [10]    is_holder_reward     OptionBool (1 byte)
  VANILLA == all 11 bytes zero. Observed non-vanilla flag_hex:
    0000000000000000000001  -> holder_reward        (41)
    00006400000000000000    -> creator_fee=100bps   (2; 10-byte truncated create variant, no holder byte)
    0100000000000000000000  -> mayhem               (1)
    000001                  -> older/short create variant (1); its buy is still the normal 17 accounts

## CONCRETE SPEC — how to extend our buy_ix for non-vanilla
**No account or data change is required.** The buy builder stays byte-for-byte identical.
  - Do NOT append any account for holder_reward / creator_fee / mayhem / cashback.
  - Keep the 17-account list and 25-byte data exactly as the vanilla path builds them.
  - [3] base_token_program = TOKEN-2022 (correct for pump-suffix mints; keep as is).
  - [13] = keep using the same valid buyback recipient from the pump global pool you
    already use for vanilla.

**The actual change to buy his non-vanilla picks is in the CLASSIFIER/DETECTOR, not buy_ix:**
  - Relax the slot-0 accept gate from "vanilla (all 11 flag bytes == 0)" to allow
    holder_reward / creator_fee / mayhem launches. Simplest: drop the vanilla gate entirely
    (or keep only creator_fee_bps==0 if you want to avoid paying creator fees). Keep the
    dev-buy threshold (~0.3 SOL) as the prior study recommends.
  - This recovers all 45/45 of his non-vanilla picks (23% of the 200-snipe window) with
    ZERO buy-path code change.

## Sample size & unresolved
- 45 non-vanilla buys (one wallet, ~38h window) — all 17/25. Strong for this wallet; not
  lifetime / all-wallets. 100% internal consistency.
- No CASHBACK launch in-window, so cashback is inferred (not directly observed) to also be
  17-account — but the IDL guarantees it (no optional accounts; cashback is a separate ix).
- The exact rule picking WHICH of the 8 buyback recipients per buy was not reverse-engineered
  (irrelevant: any valid member is accepted; our vanilla path already supplies one).
- fee_config[12] data is 4097 bytes owned by PFEE; the 8 recipients are NOT in it — they
  live in the pump GLOBAL account. fee_config seed not matched with simple seeds (not needed;
  [12] is a constant we read/hardcode once).

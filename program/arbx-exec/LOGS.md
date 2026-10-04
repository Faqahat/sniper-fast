# arbx-exec log records

Every record is one `sol_log_data` call with one field, so it appears as one `Program data: <base64>` line. Records
are told apart by length and magic. Integers are little-endian. Decoders: `logic::decode_leg_log`,
`logic::decode_summary` (host-side, no Solana dependency); pinned bytes in `src/tests.rs::log_records_match_the_pinned_bytes`.

## v2 routes (nexus-arb-v2 compatible, unchanged)

| Record | Bytes | Layout | When |
|---|---|---|---|
| NXV2LEG | 8 | `"NXV2LEG"` + leg u8 | just before leg i is invoked |
| NXV2OUT | 16 | `"NXV2OUT"` + leg u8 + delivered u64 | after leg i delivered |

The failing leg of a v2 route is the last NXV2LEG without a matching NXV2OUT.

## AXL1: one per completed v3 leg (24 bytes)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | `"AXL1"` |
| 4 | 1 | leg (0-based) |
| 5 | 1 | venue: index into `ALLOWLIST_B58` (0 DLMM, 1 Whirlpool, 2 Raydium CLMM, 3 PumpSwap, 4 PancakeSwap v3, 5 Byreal, 6 Raydium CPMM, 7 Raydium AMM v4, 8 DAMM v2, 9 pump.fun, 10 DBC, 11 LaunchLab) |
| 6 | 1 | leg flags: LEG_NATIVE_IN 0x01, LEG_NATIVE_OUT 0x02, LEG_AUTH_RO 0x04 |
| 7 | 1 | reserved, 0 |
| 8 | 8 | input: the amount patched into the venue's instruction |
| 16 | 8 | delivered: what the leg's output account (or the authority, for NATIVE_OUT) gained |

Example: leg 1 on Raydium CPMM, 1,000,000,000 in, 1,092,000,000 out:
`41584c31 01 06 00 00 00ca9a3b00000000 0099164100000000`.

## AXS1: one per route, at the guard, both layouts (92 bytes)

| Offset | Size | Field |
|---|---|---|
| 0 | 4 | `"AXS1"` |
| 4 | 1 | layout: 2 or 3 |
| 5 | 1 | flags: the v3 flags byte; for v2 synthesized (PAYER_GUARD if the trailer is present, COUNT_LAMPORTS if any leg is native) |
| 6 | 1 | n_legs |
| 7 | 1 | reserved, 0 |
| 8 | 4 | result: 0 = the guard passed; otherwise the code the instruction fails with right after this record |
| 12 | 8 | amount_in |
| 20 | 8 | min_profit |
| 28 | 8 | tip: the CPI tip computed from `gain` (0 without CPI_TIP); paid only when result = 0 |
| 36 | 16 | gain i128: what the guard compared, quote_delta + (COUNT_LAMPORTS ? lamport_delta : 0) |
| 52 | 16 | quote_delta i128: quote after the last leg minus at entry |
| 68 | 16 | lamport_delta i128: authority lamports after the last leg minus at entry, before the tip; reported even when not counted |
| 84 | 8 | cu_remaining: **reserved, always 0**. `sol_remaining_compute_units` is not active on mainnet (REVIEW.md #1); the runtime's `Program … consumed N of M compute units` line gives the instruction's total |

## How to read them

**AXS1 is the guard's verdict, not the transaction's outcome.** After a `result 0` the program still makes the CPI tip
transfer, and the runtime still checks compute and rent after the program returns. The recorder must take the outcome
from the transaction's status, never from AXS1. (Before REVIEW.md #5 a tip that broke the authority's rent exemption
produced `result 0` followed by InsufficientFundsForRent; the program now refuses that tip with ERR_TIP_FUNDS in the
record itself.)

**Which failures carry an AXS1 record.** Only those decided at the guard, after every leg ran:
- carried: `result 0`, ERR_PROFIT, ERR_PAYER_GUARD (the end-of-route lamport / owner check), ERR_TIP_FUNDS;
- not carried (the instruction fails before the guard): ERR_BAD_DATA, ERR_UNSUPPORTED (parse); ERR_NOT_TOKEN_ACCOUNT,
  ERR_QUOTE_NOT_WSOL, ERR_BAD_ACCOUNTS, ERR_TIP_ACCOUNT, ERR_NOT_ALLOWLISTED, ERR_FOREIGN_SIGNER (accounts);
  LEG_ERR + i and ERR_TOKEN_GUARD (per leg); any venue error (the CPI aborts the transaction inside the venue); and
  runtime errors such as compute exhaustion or PrivilegeEscalation (a LEG_AUTH_RO leg whose venue needs the user
  writable).

**Which v3 leg failed.** v3 has no pre-leg marker: the failing leg is the number of AXL1 records logged before the
failure (leg 0 failing logs none). Two caveats for the recorder (REVIEW.md #13):
- logs are capped at 10 KB, and DLMM and other Anchor programs log heavily (including self-CPI event instructions at
  depth 3). When the logs end in `Log truncated`, the AXL1 count is only a lower bound. Fall back to counting
  `Program <venue> invoke [2]` lines (depth 2 only: arbx-exec's CPIs; the venues' own event self-CPIs are depth 3);
  the leg being executed when the logs stop is the last depth-2 invocation without a matching `success` line;
- failed bundles often come back from the block engine without logs at all: record the leg as unknown, never as 0.

**Error codes** are listed in README.md; `exec::meaning` in the engine (src/exec.rs) names every one.

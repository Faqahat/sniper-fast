# arbx-exec

The arbx on-chain route executor. One instruction runs an atomic, self-funded round trip of 1 to 8 venue swaps
("legs"). Each leg spends exactly what the previous leg delivered, and the whole transaction reverts unless the route
ends at least `min_profit` above where it started. It never holds funds, owns no PDAs, and every swap is signed by
the trading wallet itself. Nothing here front-runs or sandwiches anyone: the program only executes our own round trip.

It started as a copy of nexus-arb-v2 (`program/nexus-arb-v2`, deployed as `8K8uyQDt…`, md5 `809315be`), whose v2
instruction layout it still accepts. The plan is `docs/research/redesign-final.md` §3.9. `REVIEW.md` is the
adversarial review and its disposition; `LOGS.md` documents the log records.

Deploying is the owner's action. No program id is fixed yet (`target/deploy/arbx_exec-keypair.json` is a local build
artifact).

## Build and test

```
./ci.sh                       # everything below, in order
cargo-build-sbf --features onchain            # target/deploy/arbx_exec.so (cargo-build-sbf 4.4.0, platform-tools v1.57)
(cd tests/mock-amm && cargo-build-sbf)        # the test-only hostile venue
cargo test --release                          # host + SVM tests (needs the .so files above)
```

| Suite | What it runs |
|---|---|
| `src/tests.rs` (host) | parser (v2 against a verbatim copy of nexus-arb-v2's, v3 rules), guard / tip / rent arithmetic in i128, property tests, a 400k-mutation fuzzer, golden vectors |
| `tests/litesvm.rs` | the BUILT program under LiteSVM's **mainnet** feature set, against `tests/mock-amm` loaded at allowlisted venue addresses, side by side with the deployed nexus-arb-v2 ELF; the ELF syscall audit; CU budgets; heap and 255-account limits; transaction size with lookup tables |
| `tests/venues.rs` | the built program in front of the **mainnet venue programs** (DLMM, PumpSwap + fee program, DAMM v2, Raydium CPMM, Raydium AMM v4) on captured account snapshots; legs built exactly as the engine's `src/build.rs` builds them |

The SVM tests refuse to run on a `.so` older than `src/lib.rs`. Snapshots and venue ELFs live in `tests/fixtures`
(`fetch_venues.py` refreshes them over public read-only RPC; `programs/MANIFEST.json` records each ELF's md5, sha256 and
last-deploy slot). `tests/fixtures/golden/*.hex` are the encodings the engine's builder must reproduce; both crates'
tests assert them.

### Syscalls

The program may only call syscalls that mainnet registers. SBPF v3 resolves syscalls at run time, so the loader
accepts any call at deploy time and an unregistered one aborts the instruction only when it executes (REVIEW.md #1:
`sol_remaining_compute_units`, feature `5TuppMut…`, is not active on mainnet). `review_01_elf_uses_only_syscalls_mainnet_registers`
lists every static syscall in the built ELF and requires each to be registered by agave's own registry under the
mainnet feature set and under "every known feature active". Today: `abort, sol_get_rent_sysvar, sol_invoke_signed_rust,
sol_log_, sol_log_data, sol_memcmp_, sol_memcpy_, sol_panic_`.

## Instruction layouts

Byte 0 picks the layout. Integers are little-endian.

### v2 (nexus-arb-v2, byte for byte)

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | version = 2 |
| 1 | 1 | n_legs, 1..=8 |
| 2 | 8 | amount_in (leg 0's input) |
| 10 | 8 | min_profit, > 0 |
| 18 | 4 × n | per leg: `n_accounts` u8 (bit 7 NATIVE_IN, bit 6 NATIVE_OUT, bits 0-5 the count, so at most 63), `amount_offset` u8, `data_len` u16 |
| … | Σ data_len | the legs' instruction data |
| end | 8 | optional `max_payer_lamport_drop` (present iff the total length says so) |

### v3

| Offset | Size | Field |
|---|---|---|
| 0 | 1 | version = 3 |
| 1 | 1 | flags: bit 0 PAYER_GUARD (**mandatory**), bit 1 CPI_TIP, bit 2 COUNT_LAMPORTS, bits 3-5 SELF_SIZE / BASKET / NOOP_ON_MISS (reserved: ERR_UNSUPPORTED), bits 6-7 must be 0 |
| 2 | 1 | n_legs, 1..=8 |
| 3 | 8 | amount_in |
| 11 | 8 | min_profit, > 0 |
| 19 | 8 | max_payer_lamport_drop |
| 27 | 19 | only with CPI_TIP: `tip_bps` u16 (≤ 10,000), `tip_floor` u64, `tip_cap` u64 (≥ floor), `tip_acct_ix` u8 (0..=7) |
| … | 5 × n | per leg: `n_accounts` u8 (1..=255), `leg_flags` u8, `amount_offset` u8, `data_len` u16 |
| … | Σ data_len | the legs' instruction data; the venue's own swap with min-out 0 or 1 |

`leg_flags`: bit 0 LEG_NATIVE_IN (spends the authority's lamports), bit 1 LEG_NATIVE_OUT (delivers lamports to the
authority; its output slot is the authority), bit 2 LEG_AUTH_RO (the venue gets the authority as a read-only signer).

The v3 parser refuses (ERR_BAD_DATA unless noted): a missing PAYER_GUARD; CPI_TIP without COUNT_LAMPORTS; a native leg
without COUNT_LAMPORTS; NATIVE_IN together with NATIVE_OUT on one leg; LEG_AUTH_RO on a native leg; unknown leg flags;
a broken native chain (lamports only chain into lamports); n_accounts 0; amount_offset + 8 > data_len; a total of more
than 255 accounts (`2 + Σ(2 + n_accounts) [+ 2]`); any length other than the exact one; reserved flags (ERR_UNSUPPORTED).

### Accounts

`[0]` authority (signer; writable whenever lamports can move), `[1]` quote token account, then per leg
`[output account, venue program, the leg's n_accounts accounts]`, and with CPI_TIP `[System program, Jito tip account
tip_acct_ix]` last. The venue program must be on the compiled-in allowlist (same 12 programs and order as nexus-arb-v2;
the AXL1 venue id is the index). At run time a v3 route also requires the quote account and every token leg's output
account to be token accounts **owned by the authority** (ERR_BAD_ACCOUNTS), and the quote to be wSOL when lamports are
counted (ERR_QUOTE_NOT_WSOL).

### Guard

```
Q0, L0 = quote amount and authority lamports at entry
legs:    leg i spends what leg i-1 delivered (leg 0: amount_in); delivered == 0 or a balance drop -> LEG_ERR + i
g      = (Q1 - Q0) + (COUNT_LAMPORTS ? L1 - L0 : 0)                      exact, i128
payer  : owner and data length unchanged, L0 - L1 <= max_drop              else ERR_PAYER_GUARD
         per leg: the authority's writable token accounts keep their delegate/close authority/state, and drop by at
         most the leg's own input                                          else ERR_TOKEN_GUARD
         no signer other than the authority is handed to a venue           else ERR_FOREIGN_SIGNER
tip    = CPI_TIP ? min(cap, max(floor, g * bps / 10_000)) : 0
need     g - tip >= min_profit                                             else ERR_PROFIT
         L1 - tip >= the authority's rent-exempt minimum (Rent sysvar)     else ERR_TIP_FUNDS
then     AXS1 is logged; on a pass the tip is a System transfer authority -> JITO[tip_acct_ix]
```

## Error codes

`Custom(code)`; the range sits above SPL Token (< 32), Anchor (100-5999) and venue codes (6000+).

| Code | Name | Meaning |
|---|---|---|
| 0x4E580001 | ERR_BAD_DATA | malformed or refused instruction data (see the parser rules); v2: a NATIVE_OUT slot that is not the authority |
| 0x4E580002 | ERR_PROFIT | every leg ran; `g - tip < min_profit` |
| 0x4E580003 | ERR_NOT_ALLOWLISTED | a leg's program is not on the allowlist |
| 0x4E580004 | ERR_NOT_TOKEN_ACCOUNT | the quote or an output account is not owned by a token program |
| 0x4E580005 | ERR_PAYER_GUARD | the authority was reassigned, resized, or lost more than max_drop |
| 0x4E580006 | ERR_TOKEN_GUARD | one of the authority's token accounts was drained, delegated, frozen, closed or re-owned |
| 0x4E580007 | ERR_FOREIGN_SIGNER | a leg passed a signer other than the authority |
| 0x4E580008 | ERR_UNSUPPORTED | v3 reserved feature flag |
| 0x4E580009 | ERR_BAD_ACCOUNTS | last leg not into the quote; token output = its input; v3 NATIVE_OUT slot not the authority; read-only authority when lamports move; v3 quote or output not owned by the authority |
| 0x4E58000A | ERR_TIP_ACCOUNT | wrong / read-only Jito tip account, or the System slot is not the System program |
| 0x4E58000B | ERR_TIP_FUNDS | the tip would leave the authority below rent exemption |
| 0x4E58000C | ERR_QUOTE_NOT_WSOL | COUNT_LAMPORTS or CPI_TIP with a non-wSOL quote |
| 0x4E580100 + i | LEG_ERR | leg i delivered nothing or its output balance went down |

0x4E580001-07 mean what they meant in nexus-arb-v2. The engine's `exec::meaning` (src/exec.rs) maps all of them.

## v2 compatibility: what differs from nexus-arb-v2 (REVIEW.md #8)

The v2 layout is parsed identically (property-tested against nexus-arb-v2's parser), but an engine that only switches
the program id sees these differences, all tested in `review_08_*`:
- ERR_BAD_ACCOUNTS (new) where nexus answered differently: a last leg not into the quote (nexus: ERR_PROFIT after
  running every leg), a native route with a read-only authority (nexus: the runtime's PrivilegeEscalation), a token leg
  whose output is its input.
- The NATIVE_OUT output-slot check runs before the foreign-signer scan (same codes).
- One extra AXS1 record per route, about 130 log bytes and +232 CU (20,137 against 19,905 on the mock round trip).
- v2 keeps nexus-arb-v2's weaker rules: the guard trailer is optional, the quote's owner is not checked, both native
  flags on one leg parse. New routes should use v3.

## Engine notes (measured, see the tests)

- **CPI tip is Jito-only** (REVIEW.md #12): it can only pay the 8 Jito tip accounts compiled in (same order as
  `data/sender-tip-accounts.json`), so it fits Jito bundles and Jito sendTransaction only; other senders need a
  top-level tip. A Jito tip-account rotation needs a program upgrade. The CPI tip costs about 2.4k CU inside the
  instruction (a top-level System transfer about 150).
- **LEG_AUTH_RO** works on DLMM, Raydium CPMM, Meteora DAMM v2 and Raydium AMM v4, and fails on PumpSwap
  (PrivilegeEscalation: it marks the user `mut`), measured on mainnet snapshots (`which_venues_accept_a_read_only_authority`).
- **Venue CU** per leg on the snapshots (2026-10-04): DLMM ~33.7k, Raydium AMM v4 ~15.4k, DAMM v2 ~13.5-14.1k, CPMM
  ~24.4k, PumpSwap buy 77-90k / sell 65-77k. arbx-exec itself adds 10.5k-18.2k CU to a 2-leg route (more accounts,
  more CPI serialization). PumpSwap's CU also depends on the payer key (its volume-accumulator PDA bump search costs
  1,500 CU per extra bump).
- **The first PumpSwap buy** creates the payer's user volume accumulator and charges 1,844,400 lamports of rent to the
  payer: with PAYER_GUARD that needs max_drop ≥ the rent (or the account created beforehand).
- **Transaction size**: the widest real route (PumpSwap buy + sell on a canonical pump-token pool, CPI tip, compute
  budget instructions, 58 metas) is 486 bytes with two lookup tables; a 26 + 21-account mock route is 520 bytes with
  tables and 1,878 without, so lookup tables are required.
- **Heap**: the default 32 KiB heap holds every route up to the runtime's 255 accounts per instruction.

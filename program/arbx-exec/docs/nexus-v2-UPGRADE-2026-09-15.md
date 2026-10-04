# nexus-arb-v2 upgrade — 2026-09-15 (audit fixes a + b)

Program id `8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg`
ProgramData `5V3ssdCfTyENu2YGzXdWo9RQP2se8KrqmLRHsLVrvGji`
Upgrade authority (the **deploy** wallet) `GNv76A95ozFcQibMqsRpmSBH6ymmHsJphd4sHqabGhQ4`

This is a **source draft only**. Nothing here has been deployed and no transaction has been sent.
The commands below are for the USER to run.

---

## What changed

Both audit findings are addressed in `programs/nexus-arb-v2/src/lib.rs`. `check_profit` is **unchanged**
(still `quote_after - quote_before >= min_profit`), and all arithmetic is checked.

### (c) Allowlist: +2 venues (added at the operator's explicit request, 2026-09-15, Path A)

`ALLOWLIST` goes from 7 to 9 programs. Nothing else in the allowlist logic changes.

| Program | Venue | Why |
|---|---|---|
| `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` | Raydium AMM v4 | 750-block census: ~1,129 arbs / 4 min whose other legs are already allowlisted |
| `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | Meteora DAMM v2 | ~761 arbs / 4 min, same criterion |

Raydium AMM v4 instruction data carries `amount_in` at byte **1** (1-byte tag), not 8. The program already
supports a per-leg `amount_offset` (lib.rs `LegMeta.amount_offset`), so no format change is needed; the TS
builder must pass offset 1 for AMM v4 legs. Both programs are upgradeable by their own teams — build routes
with the `max_payer_lamport_drop` trailer (below) once this upgrade is live so a malicious venue upgrade
cannot drain the payer.

### (a) HIGH — optional payer guard (backward compatible)

`check_profit` only measures the quote token account. Two allowlisted venues — the Raydium-CLMM forks
`HpNfyc2Saw7RKkQd8nEL4khUcuPhQ7WwY1B2qjx8jxFq` and `REALQqNEomY6cQGZJUGwywTBD2UmDT32rZcNnfxQ5N2` — are
upgradeable by third parties and receive the payer as **signer + writable** on every leg. A malicious
upgrade could take native SOL, other token balances, or a token account's authority inside a leg while
the quote account still shows a profit.

New **optional** trailing field `max_payer_lamport_drop: u64` (little-endian, 8 bytes appended after the
last leg's data). Presence is detected purely from the **exact total length** (the parser already
required an exact length): `total == end-of-leg-data` → no guard, parsed **identically** to the old
format; `total == end-of-leg-data + 8` → guarded; any other length → `DataLengthMismatch`. No
version/flag byte is spent (RayFork routes already build to 1,223 of the 1,232-byte tx limit). When
present, the program enforces, **inside this instruction only** (measured authority native lamports
before the first leg vs after the last leg):

1. **Native SOL**: the authority may not lose more than `max_payer_lamport_drop` lamports, and its
   `owner`/`data_len` may not change (a system `assign`/`allocate` hands the wallet away without moving
   a lamport). → `ERR_PAYER_GUARD`.
2. **Payer token accounts (the requested "OTHER token accounts" guard)** — implemented, cheap, sound:
   before each leg the program snapshots every **writable** account the leg carries whose SPL owner
   field is the authority; after the leg it re-reads each and requires it lost **no more than that
   leg's input if it is the leg's input account** (leg 0: the quote account; leg i: leg i-1's output
   account), **zero otherwise**, and that its delegate/state/close-authority are unchanged and it is
   still an authority-owned token account. → `ERR_TOKEN_GUARD` (the failing leg is named by the last
   `NXV2LEG` marker). This is one extra borrow+compare per writable authority-owned account per leg —
   a handful of accounts, negligible CU.
3. **Foreign signer**: no leg may carry a signer other than the authority (the guard only watches the
   authority). → `ERR_FOREIGN_SIGNER`.

Off by default: **without the trailer the on-chain behaviour is exactly as before**, plus the new
per-leg delivered log (below).

Recommended value once deployed: `max_payer_lamport_drop = 0n` (the strictest). Honest routes move
token balances, not the authority's native SOL, so the drop across the legs is 0; the tip transfer,
ATA-creation rent, and base/priority fees are **separate top-level instructions** (verified: in
`tools/arb-v2/live/send-live-feed.ts` the Jito tip is `SystemProgram.transfer` pushed onto
`preInstructions`, ATA creates are `createAssociatedTokenAccountIdempotentInstruction` in
`preInstructions`, and both sit outside the v2 instruction; priority fee is charged by the runtime at
the transaction level, not inside the instruction), so none of them count against this guard.

### (b) MEDIUM — per-leg delivered logging

Every leg now emits, right after it delivers, `sol_log_data([NXV2OUT | leg_index_u8 | delivered_u64_le])`
(one 16-byte record). With every leg's `minOut = 1`, a route that fails `ERR_PROFIT` previously could
not say which leg under-delivered; the log now names it. `sol_log_data` of a single 16-byte slice is
~a few hundred CU per leg (base syscall + 16 bytes), well under 0.5% of a ~55k-CU CLMM leg. The
existing `NXV2LEG` marker (8 bytes, logged *before* each leg) is unchanged; the 16-byte `NXV2OUT`
record is length-distinct so the existing `failingLegFromLogs` reader is unaffected. TS reader added:
`deliveredFromLogs(logs)` in `tools/arb-v2/exec/nexus-v2.ts`.

## Error code table (0x4E58_xxxx range — never collides with token <32 or Anchor 6000+)

| Code (hex)   | Constant              | Meaning                                                              | New? |
|--------------|-----------------------|---------------------------------------------------------------------|------|
| 0x4E580001   | ERR_BAD_DATA          | malformed instruction data (incl. wrong trailer length)             |      |
| 0x4E580002   | ERR_PROFIT            | quote profit below `min_profit` (unchanged)                         |      |
| 0x4E580003   | ERR_NOT_ALLOWLISTED   | a leg program is not on the allowlist                               |      |
| 0x4E580004   | ERR_NOT_TOKEN_ACCOUNT | an output/quote account is not a token account                     |      |
| **0x4E580005** | **ERR_PAYER_GUARD**   | authority lost more native SOL than allowed, or was reassigned    | ✅   |
| **0x4E580006** | **ERR_TOKEN_GUARD**   | an authority-owned token account drained past its input / re-authed | ✅   |
| **0x4E580007** | **ERR_FOREIGN_SIGNER**| a leg carried a signer other than the authority                   | ✅   |
| 0x4E580100+i | LEG_ERR_BASE + i      | leg i delivered nothing / its balance went down                    |      |

All three new codes are checked **only** when the guard trailer is present.

## Tests

- Rust: `cd programs/nexus-arb-v2 && cargo test` → **16 passed** (old-format parses identically,
  guarded-format parse, guard pass at the limit, guard fail with `ERR_PAYER_GUARD`, token-guard
  pass/fail with `ERR_TOKEN_GUARD`, delivered-log shape, error-code uniqueness).
- TS: `cd nexus && bun test tools/arb-v2/exec/nexus-v2.test.ts tools/arb-v2/exec/nexus-v2.litesvm.test.ts`
  → **16 passed**, incl. the byte-identical-when-unset assertion against the pinned fixture, the guarded
  fixture matching the Rust `GUARDED_FIXTURE_HEX`, and a LiteSVM test proving the built `.so` accepts
  the trailer (reaches the allowlist check rather than `ERR_BAD_DATA`).

## Build

```
cd programs/nexus-arb-v2
cargo-build-sbf --features onchain     # or: ~/.local/share/solana/install/active_release/bin/cargo-build-sbf
# output: programs/nexus-arb-v2/target/deploy/nexus_arb_v2.so
```

New `.so` size: **39,296 bytes** (was 33,200 deployed). Toolchain used: `cargo-build-sbf 4.1.0`,
platform-tools v1.54, `solana-cli 4.2.2 (Agave)`.

## SOL needed for the upgrade (deploy wallet)

Rent at this cluster's current rate ≈ **5,080 lamports/byte** (includes the 128-byte account overhead;
matches the live reading of 1,488,440 lamports for a 165-byte account = (165+128)×5,080).

- **Upgrade buffer** (temporary, refunded to the authority when the upgrade confirms): data =
  `.so` + 37-byte Buffer header = 39,333 bytes → rent `(39,333 + 128) × 5,080` = **200,461,880 lamports
  ≈ 0.2005 SOL**.
- **ProgramData extension** (permanent): the new `.so` (39,296) is larger than the deployed ProgramData
  can hold. Current ProgramData is 33,245 bytes total (= 33,200 program bytes + 45-byte header, which
  matches the old `.so`). New ProgramData must be `.so` + 45 = 39,341 bytes → **extend by 6,096 bytes**,
  costing `6,096 × 5,080` = **30,967,680 lamports ≈ 0.0310 SOL** (not refunded).
- Transaction fees: a few signatures, ~0.00002 SOL.

**The deploy wallet currently holds ~0.0032 SOL — far too little. Fund it first.** Send at least
**~0.24 SOL** (buffer 0.2005 + extend 0.0310 + fees + a small margin); ~0.2005 SOL comes back after a
successful upgrade, leaving the extension (~0.0310 SOL) as the net permanent cost.

## Exact upgrade commands (run these yourself; deploy wallet is the upgrade authority)

The deploy keypair is custody-encrypted. Export it to a plaintext file for the CLI, **and delete that
file the moment the upgrade confirms** — it is the live upgrade authority.

```bash
# 1) export the deploy keypair to a temp file (audit-fixed CLI, exact 2-arg form)
bun run tools/arb-v2/exec/wallet-cli.ts keypair-file deploy /tmp/deploy-authority.json
#    (this writes a PLAINTEXT keypair — treat it like a live private key)

# 2) fund the deploy wallet first (from another wallet you control), ~0.24 SOL:
#    solana transfer GNv76A95ozFcQibMqsRpmSBH6ymmHsJphd4sHqabGhQ4 0.24 --url mainnet-beta ...

# 3) BACK UP the currently-deployed program so you can roll back (see rollback note):
solana program dump 8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg \
  ~/nexus-backups/nexus_arb_v2-PRE-2026-09-15.so --url mainnet-beta

# 4) extend ProgramData by 6,096 bytes (required — new .so is larger than the deployed one):
solana program extend 8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg 6096 \
  --keypair /tmp/deploy-authority.json --url mainnet-beta

# 5a) write a buffer, then upgrade (two-step, resumable if a network hiccup interrupts write):
solana program write-buffer programs/nexus-arb-v2/target/deploy/nexus_arb_v2.so \
  --keypair /tmp/deploy-authority.json --url mainnet-beta
#     -> prints the buffer address <BUF>; the buffer's authority defaults to the payer (deploy wallet)
solana program upgrade <BUF> 8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg \
  --keypair /tmp/deploy-authority.json --upgrade-authority /tmp/deploy-authority.json \
  --url mainnet-beta

# 5b) OR the one-shot equivalent (does write-buffer + upgrade in one command):
solana program deploy programs/nexus-arb-v2/target/deploy/nexus_arb_v2.so \
  --program-id 8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg \
  --keypair /tmp/deploy-authority.json --upgrade-authority /tmp/deploy-authority.json \
  --url mainnet-beta

# 6) confirm on chain, then DELETE the plaintext keypair:
solana program show 8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg --url mainnet-beta
shred -u /tmp/deploy-authority.json    # or: rm -P / rm
```

If `write-buffer` succeeds but `upgrade` fails, the buffer's rent is recoverable:
`solana program close <BUF> --keypair /tmp/deploy-authority.json` returns its lamports to the authority.

## ⚠️ Sender wiring — do NOT set the new field until the upgrade is confirmed on chain

The **old** program rejects the longer (guarded) instruction with `DataLengthMismatch` → `ERR_BAD_DATA`.
So until `solana program show` confirms the new deploy:

- Keep `maxPayerLamportDrop` **undefined** everywhere. With it undefined, `encodeV2Data` /
  `buildV2Instruction` produce byte-identical output to today (there is a test pinning this).

Once the upgrade is confirmed, to turn the guard on, the sender in
`tools/arb-v2/live/send-live-feed.ts` (and `send-live.ts`) passes the field through
`buildRouteTransaction` → `buildV2Instruction`. Exact wiring (the two files below are owned by another
editor — this is the change for them to make):

- `tools/arb-v2/exec/builder.ts`: add `maxPayerLamportDrop?: bigint;` to the `buildRouteTransaction`
  argument type, and forward it in the `buildV2Instruction({ ... })` call (add
  `maxPayerLamportDrop: a.maxPayerLamportDrop,`). No other change; when the caller leaves it undefined
  the built transaction is byte-identical to today.
- `tools/arb-v2/live/send-live-feed.ts` (and `send-live.ts`): in the `buildRouteTransaction({ ... })`
  call, add `maxPayerLamportDrop: 0n` (SOL-denominated round trips) — gated behind a confirmation flag
  such as `V2_PAYER_GUARD === "1"` so it can be rolled out after the on-chain upgrade is verified.

## Rollback

The pre-upgrade `.so` is dumped in step 3 (`~/nexus-backups/nexus_arb_v2-PRE-2026-09-15.so`). To roll
back, repeat step 5 with that file (ProgramData is already large enough, so no `extend` needed):

```bash
solana program deploy ~/nexus-backups/nexus_arb_v2-PRE-2026-09-15.so \
  --program-id 8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg \
  --keypair /tmp/deploy-authority.json --upgrade-authority /tmp/deploy-authority.json --url mainnet-beta
```

After rolling back, ensure senders stop setting `maxPayerLamportDrop` (the reverted program rejects the
longer instruction).

# Deep-Dive: Solana Program `MEViEnscUm6tsQRoGd9h6nLQaQspKj7DB2M5FwM3Xvz` ("MEV/SMB")

**Date:** 2026-10-04 · **Method:** Solana platform-tools v1.54 `llvm-objdump` + call-graph/panic-metadata reconstruction + on-chain RPC. Public bytecode analysis.

---

## 1. Identity & scale

| Property | Value |
|---|---|
| Program | `MEViEnscUm6tsQRoGd9h6nLQaQspKj7DB2M5FwM3Xvz` |
| Upgrade authority | `SMB6JY59jr4JJCDdSt5uBD6DPEYX7VFKKJbCubvHV91` (referenced in code too) |
| Verified | No |
| Size | **2.76 MB · 192,275 instructions · 614 functions** (25×/14× program 1) |
| Framework | **Pinocchio** (zero-dep, max-CU-efficiency), source tree `programs/executor-pinocchio/`, at **version 10** (v9 kept as legacy) |
| Callers (on-chain) | multiple wallets (`2BKYGMaD`, `4BQ6ATUt`, `CPD18rED`, …) — not a single operator |

Entrypoint `0x163ec0` is a stock Pinocchio deserializer; the real handler is `process_instruction` at `0x1530a0`, which returns the **same `Result` convention as program 1** (tag `0x1a` = Ok, a jump table maps ~13 error variants `0x00`–`0x0c`).

---

## 2. What's actually in it — the source-module map (recovered from panic metadata, 533 locations)

### Venue adapters — `src/dex/*.rs` (16 adapters, vs program 1's ~6)
`dlmm` · `clmm` · `raydium` · `raydium_cp` · `orca` · `meteora` · `dammv2` · `pump` · **`byreal`** · **`pancakeswap`** · **`humidifi`** · **`heaven`** · **`vertigo`** · **`bisonfi`** · **`futarchy`**. Plus `pump_fee.rs`. The venue program IDs are **hardcoded** (unlike program 1, which took them per-tx), and the program derives their PDAs on-chain (`sol_try_find_program_address` ×22).

**Program IDs — 11 of 16 byte-confirmed in the binary** (the venue *names* come from the program's own source-module paths, so the list itself is definitive):

| Adapter | Venue | Program ID | Confirmed in binary |
|---|---|---|---|
| dlmm | Meteora DLMM | `LBUZKhRxPF3XUpBCjp4YzTKgLccjZhTSDM9YuVaPwxo` | ✓ |
| dammv2 | Meteora DAMM v2 | `cpamdpZCGKUy5JxQXB4dcpGPiikHawvSWAd6mEn1sGG` | ✓ |
| meteora | Meteora Dynamic AMM v1 | `Eo7WjKq67rjJQSZxS6z3YkapzY3eMj6Xy8X5EQVn5UaB` | ✓ |
| raydium | Raydium CLMM | `CAMMCzo5YL8w4VFF8KVHrK22GGUsp5VTaW7grrKgrWqK` | ✓ (code) |
| raydium_cp | Raydium CPMM | `CPMMoo8L3F4NbTegBCKVNunggL7H1ZpdTHKxQB5qKP1C` | ✓ |
| (raydium v4) | Raydium AMM v4 | `675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8` | ✓ |
| orca | Orca Whirlpool | `whirLbMiicVdio4qvUfM5KAg6Ct8VwpYzGff3uctyCc` | ✓ |
| pump | PumpSwap / Pump.fun | `pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA` / `6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P` | ✓ |
| pancakeswap | PancakeSwap (Solana) | `HpNfyc2Saw7RKkQd8nEL4khUcuPhQ7WwY1B2qjx8jxFq` | ✓ |
| humidifi | HumidiFi | `9H6tua7jkLhdm3w8BvgpTn5LZNU7g4ZynDmCiNN3q6Rp` | ✓ |
| byreal | Byreal (Bybit DEX) | — | pending |
| heaven | Heaven | — | pending |
| vertigo | Vertigo | — | pending |
| bisonfi | BisonFi | — | pending |
| futarchy | MetaDAO Futarchy AMM | — | pending |
| clmm | shared CLMM math layer | — | n/a |

The 5 "pending" adapters exist in the code and their IDs sit in the binary's shared `.rodata` pubkey table (not inline per-adapter), but no public registry cleanly labels them; they'd be pulled from each DEX's own docs or caught in a live trade. No flash-loan / lending programs are referenced — it uses its own capital.

### Core arbitrage logic
| Module | Panic sites | Role |
|---|---|---|
| `calculation/optimal_input.rs` | 58 | **the optimal trade-size solver** (biggest single source) |
| `execute_swap.rs` | 48 | swap execution (CPI builders) |
| `v10/search.rs` | 45 | opportunity/size **search engine** |
| `arbitrage.rs` | 22 | top-level arb orchestration |
| `pools.rs` | 21 | pool-state loading + PDA derivation |
| `v10/accounts.rs`, `v10/quote.rs`, `v10/execute.rs`, `v10/depth.rs`, `v10/candidates.rs`, `v10/sizing.rs`, `v10/pool_blocks.rs` | — | the v10 pipeline |

### Math — two generations
- **`math_v9/`** (legacy, *pairwise*): `dlmm_dlmm`, `dlmm_orca`, `dlmm_clmm`, `clmm_amm`, `orca_amm`, `orca_clmm`, `clmm_quote`, `quote_quote_optimized` — specialized closed-form math for each **pair** of venue types.
- **`v10/quote/`** (current, *generalized*): `segments`, `interval`, `product`, `product_prefix`, `ticks`, `refinement`, `refinement/inverse` — a unified piecewise-curve quoting framework (any venue → segments → composable quote).
- **Ported DEX math**: `raydium_clmm/libraries/` (`sqrt_price_math`, `liquidity_math`, `swap_math`, `full_math`, `big_num` = U256/U512) and `orca_math/` (`u256_math`, `tick_math`) — so it can reproduce each CLMM's exact output on-chain.

### Glue — `src/`
`lib.rs`, `encode.rs`, `decode.rs`, `internal.rs`, `syscalls.rs`, `pda.rs`, `user_balance.rs`.

---

## 3. The arbitrage engine (how sizing works — much more advanced than program 1)

Program 1 sized trades with a simple fixed-vs-adaptive bisection. Program 2 runs a real **numerical optimizer over piecewise concentrated-liquidity curves**:

1. **Quote** each pool as a piecewise function over its tick/bin **segments** (`v10/quote/segments.rs`, `interval.rs`), composing multi-hop routes with **prefix products** (`product_prefix.rs`).
2. **Search** for the profit-maximizing allocation (`v10/search.rs` — one function has **293 loop back-edges**; nested search over candidates/segments).
3. **Refine** the optimum with an **inverse/Newton-style iteration** (`v10/quote/refinement/inverse.rs` — 3,346 instructions, 115 loops, almost no mul/div = pure iterative convergence to invert the price function and solve "what input hits this marginal price").
4. **`optimal_input.rs`** (5,567 instructions, 45 mul / 11 div / 165 loops) ties it together into the final input amount.

All of it rides wide-integer primitives (`big_num` U256/U512) to stay exact at tick precision.

---

## 4. Execution, guard, and dispatch

- **34 `sol_invoke_signed_c` CPI sites** (vs program 1's 4) — one swap-builder per venue, concentrated in `execute_swap.rs`, `v10/execute.rs`, `clmm.rs`, and the legacy `v9.rs`.
- **Guard:** the string **`"No profitable arbitrage opportunity found"`** is referenced from the `v9.rs` execution path (`0x14d2b8`, which also holds `sol_invoke_signed_c` ×2). The on-chain behavior (below) shows the program **simulates first and exits `Ok` as a no-op** when nothing is profitable, rather than reverting.
- **Dispatch:** `process_instruction` matches the input against several **32-byte discriminators** → multiple instruction variants (plausibly v9 vs v10 paths / route shapes). A large 6,744-instruction routine at `0x165cf0` (1,597 shifts, no loops) is the unrolled instruction/account **decoder** (`decode.rs`).
- **Operator model (resolved on-chain):** the authority `SMB6JY…` is *compared* in code (≈3 sites, during account loading) but is the **upgrade authority, not a per-trade fee sink** — in sampled trades the SMB account isn't even present and its balance doesn't change (no cut flows to it). Callers are **5 distinct wallets, one dominant** (`4vAqkstz` ≈ 94% of txns, all no-ops; trades come from `4BQ6ATUt`, `6bVSWZxH`, …). Most plausibly one operator running parallel hot wallets (a "service mode" that supplies an SMB config account exists in code but wasn't used by any sampled trade).

---

## 5. On-chain behavior (1,000-tx window) — the opposite of program 1

| Metric | Program 2 | Program 1 |
|---|---|---|
| Throughput | ~88 tx/min | ~17 tx/min |
| **Land rate** | **99.8%** | 14.9% |
| Dominant outcome | **~96% clean no-ops** (~27–56k CU, exit `Ok`) | 75% reverts (`Custom(3)`) |
| Real trades | minority, 135–198k CU | the 15% that land |
| Priority fee | **~0** (lands via **Jito bundles**, v1 txs w/ lookup tables) | scaled tips up to ~1.3 SOL |
| Miss cost | base fee, DEX never touched | base fee, but ran both swaps (135k CU) |

**Interpretation:** program 2 quotes internally (that's what all the ported math is for) and only executes when profitable, exiting cleanly otherwise — so it has **no failed transactions** and cheaper misses, at the cost of 2.76 MB of math it must keep in sync with each DEX. Program 1 outsources "simulation" to actually executing on the DEX and relies on an atomic revert — simpler, but 85% failed txs and heavier misses.

**Confirmation (400-tx window, same methodology):** **118 tx/min**, **99.8% land**, but only **1.2% are real trades** — **98.5% are clean no-ops** (~40k CU, exit `Ok`). All fees ~base-only (Jito-bundle landing). Sampled trade routes: `DLMM+Pump`, `DLMM+DAMMv2`, `Pump+DLMM` (mostly 2-leg). Per-trade profit in a small sample: ~+0.009 to +0.019 SOL (and one ~break-even) — **fewer but fatter wins than program 1**, because it skips the marginal trades program 1 would execute-and-revert.

---

## 6. Best-of-both for an original build

- **From program 2:** Pinocchio; modular per-venue adapters; quote-on-chain-before-execute (no failed txs); segment/interval + Newton-refinement sizing; Jito-bundle landing.
- **From program 1:** keep the **atomic net ≥ 0 guard as a hard backstop** even with quote-first (defense in depth — program 2 trusts its own math; a drift bug could execute a loss); profit-proportional tip sizing; simplicity where a venue doesn't need full CLMM math.
- **Net:** quote-first efficiency + can't-lose backstop + smart tips — stronger than either program alone.

---

## 7. Limits
Stripped release build; reconstructed from control flow, retained panic-location paths, and on-chain data. Not fully pinned: the exact 32-byte discriminator meanings, the `SMB` key's precise role (fee sink vs allowlist), and per-venue account orderings. None of these change the architectural picture.

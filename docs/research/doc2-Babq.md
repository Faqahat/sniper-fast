# Reverse-Engineering Report (v2): Solana Program `Babq1RQD7MqrwfLroPUzMQwPj5994gbQGWzBX5B7NLHo`

**Date:** 2026-10-04
**Subject:** Closed-source, upgradeable SBF program on Solana mainnet
**Method:** Static disassembly (Solana platform-tools v1.54 `llvm-objdump`, LLVM 20.1.7) + call-graph/data reconstruction + live transaction analysis via public RPC. All data is from publicly-deployed bytecode and public transaction history.

---

## 1. TL;DR

A **private, single-operator, high-frequency cross-DEX arbitrage (MEV) bot**. It computes an optimal trade size on-chain, executes a **2–16 hop swap route** across Solana AMMs via PDA-signed CPIs, and **atomically reverts the whole transaction unless the round-trip nets ≥ 0** (break-even or better). It is hard-gated to its operator's signature, holds no standing funds, and has no admin/withdraw path — the only privileged lever is the upgrade authority. Over a sampled 1-hour window it fired ~17 tx/min with a **14.9% land rate**; ~75% of attempts self-revert as "not profitable."

---

## 2. Identity & operator

| Property | Value |
|---|---|
| Program | `Babq1RQD7MqrwfLroPUzMQwPj5994gbQGWzBX5B7NLHo` |
| Loader | `BPFLoaderUpgradeab1e…` (upgradeable) |
| Upgrade authority = fee-payer = hardcoded gate key | `9EwQoN74Hzw747EM7wB3WtvgAdRGH1czaPtbqZj1qDj4` |
| Verified build | No (OtterSec: `is_verified:false`) |
| Size | ~111 KB / 13,734 instructions / 57 functions |

The upgrade authority, the signer/fee-payer on every transaction, and a pubkey compiled into `.text` as an access gate are all the **same wallet**.

---

## 3. Execution model (end-to-end)

`entrypoint` (`0x17b58`, stock Rust deserializer, ≤128 accounts) → `process_instruction` (`0x14a98`):

1. **Operator gate.** Scan the passed accounts for a **signer whose key == `9EwQoN74…`**; if absent, return early (missing-signer error). Nobody but the operator can run it.
2. **Parse the route** from instruction data (see §4).
3. **Plan the trade** (`0x11dd0` → `0x13770`): read the Clock sysvar, then size the trade (see §5), returning the chosen input amount.
4. **Execute the hops**: for each hop, serialize that venue's swap instruction (`0x488`) and issue a **PDA-signed CPI** (`sol_invoke_signed_c`); create ATAs as needed (`ata_setup.rs`, `0x15e8`).
5. **Profit guard** (see §6): snapshot balances before, recompute after, and revert the entire transaction unless net P&L ≥ 0.

Syscall surface (18 total): `sol_invoke_signed_c` ×4 (CPIs), `sol_memcpy_` ×8, `sol_log_` ×4, `sol_memset_` ×1, `sol_get_clock_sysvar` ×1.

### Function → source map (from retained panic metadata)
| Addr | Insns | Source | Role |
|---|---|---|---|
| `0x14a98` | 1522 | `v3.rs` | main handler, CLMM/tick math, profit guard |
| `0x38e8` | 2022 | `dlmm.rs` | Meteora DLMM bin-walk simulation |
| `0x9ae8` | 1098 | `optimize.rs` | trade-size solver |
| `0xbd98` | 432 | `optimize.rs:187` | search-bounds clamp (`assert min<=max`) |
| `0x13770` | 224 | — | sizing orchestrator (fixed vs adaptive) |
| `0x11dd0` | 349 | — | trade planner (reads clock) |
| `0x15e8` | 416 | `ata_setup.rs` | idempotent ATA creation |
| `0x19780` | 662 | — | wide `mul_div` primitive (10 mul / 8 div / 92 shifts) |
| `0x128c0` | 458 | `logger.rs` | formats `fixed_in/p_adp/p_fix/adaptive_in/cap` |
| `0x488` | 155 | — | per-venue swap-instruction serializer |
| `0xf0a8`,`0x109a8` | 800,645 | — | pool-account deserializers (no arithmetic, heavy branching) |
| `0xcfd0`,`0xcb38` | 604,147 | — | per-venue simulation orchestration |

---

## 4. Instruction-data schema (the bot → program message)

A single instruction type (no sub-dispatch). Layout:
- **Header** (bytes `0x00`–`0x19`): includes at byte `0x10` an account-index bound (checked against `accounts.len()`), at byte `0x11` a **hop count in the low 5 bits (1–16) plus flags in bits 5–6**, and further config at `0x12+`.
- **Hop records** from offset `0x1a`: up to **16 variable-length records**, each beginning with a tag byte (validated `≥ 0x41`) and carrying a `u16` length/offset field; the parser walks them to locate per-hop accounts and amounts.

So the program is a **general multi-hop route executor**, not hardwired to two legs.

---

## 5. Sizing (`optimize.rs` + orchestrator `0x13770`) — items #2/#8

- **Pool simulators**: `dlmm.rs` (`0x38e8`) walks DLMM liquidity bins (fixed-point `(1+binStep)^id`, 133 shifts, 92 loop back-edges); `v3.rs` walks CLMM ticks (Q64.64 sqrt-price). Every product/quotient goes through the single wide `mul_div` primitive (`0x19780`).
- **Solver** (`0x9ae8`): iterative, bisection-style search (67 back-edges + a `min ≤ max` clamp invariant) for the input that maximizes modeled profit, bounded by a **cap**.
- **Fixed vs adaptive**: the orchestrator computes **two candidate sizes** — a **fixed probe (constant `0xf4240` = 1,000,000 units)** run through the solver, and an **adaptive** value (`0x13e70`) — simulates the full round-trip for each, and **selects the higher-profit one via `max` comparisons**. Both candidates and the cap are emitted to logs (`fixed_in=`, `adaptive_in=`, `p_fix=`, `p_adp=`, `cap=`).

---

## 6. Profit guard & threshold — item #1

In `process_instruction` the program records each relevant token account's balance **before** the swaps (SPL amount at serialized offset `+0x98`, lamports at `+0x48`), and **after** the swaps computes **signed 128-bit deltas across the accounts and sums them** into a net P&L (`v3.rs:134`; `neg64`/carry-propagation around `0x172b0`–`0x17320`). The final decision is a **signed comparison of that net against literal `0`** (`jsle r1,0x0` / `jsge r7,0x0` → success tag `0x1a`).

- **Threshold = break-even or better (net ≥ 0).** No separate profit-margin constant is enforced on-chain, and the DEX-level `other_amount_threshold`/min-out is set to **0** — the round-trip guard is the sole economic protection. Because the swaps are atomic, a failed guard unwinds both legs; the principal is never at market risk.
- The transaction fee/priority tip is paid by the runtime regardless and is *not* part of this comparison, so a landed trade can still be a net loss after a large tip (see §8).

---

## 7. Venue integrations & calldata — items #4/#7

Only Token-2022, the ATA program, and the operator key are hardcoded; **DEX program IDs and all pool accounts are supplied per-transaction** by the off-chain bot (positional account metas per hop). A selector chooses which encoding `0x488` serializes:

| Encoding | Payload | Venue |
|---|---|---|
| Anchor `swap_v2` (`2b04ed0b…`) | 41/42 B | Raydium CLMM (`SwapV2`) |
| Anchor `swap_base_input` (`8fbe5ada…`) | — | Raydium CPMM (`SwapBaseInput`) |
| Anchor `swap` (`f8c69e91…`) | 25/43 B | Meteora DAMM v2 / DLMM legacy (`Swap`) |
| Anchor `swap2` (`414b3f4c…`) | 24 B | Meteora DLMM (`Swap2`) |
| Anchor `sell` / `buy_exact_quote_in` | — | PumpSwap (`Sell` / `BuyExactQuoteIn`) |
| 1-byte tag `0x09` | 17 B | Raydium AMM v4-style (`swap_base_in`) |
| 1-byte tag `0x01` | 9/17 B | simple byte-tag venue |
| 2-byte tag `0x0200` | 20 B | 2-byte-disc venue (e.g. Obric-class) |
| non-Anchor, 25 B | 25 B | **ZeroFi `swap_v4`** |

**ZeroFi (#4):** 25-byte non-Anchor payload = 8-byte selector constant + an **XOR-masked 8-byte amount** + a masked 8-byte parameter + a 1-byte trailing tag (`0x2d`). The XOR masking of the amount field is unusual — ZeroFi appears to obfuscate its calldata.

Observed quote assets: **wSOL** and **USDC**; both SPL-Token and Token-2022 mints handled.

---

## 8. On-chain behavior & economics — items #11/#12

**Window:** 1,000 consecutive transactions spanning ~59 min (≈17 tx/min, ~1,000/hr).

| Outcome | Share | Meaning |
|---|---|---|
| `Custom(3)` | **75.4%** | profit guard: not profitable → atomic revert (post-swap, high CU) |
| **Landed (OK)** | **14.9%** | profitable arb executed |
| `Custom(14)` | 7.8% | checked-arithmetic (i128) overflow guard |
| `ProgramFailedToComplete` / `ComputationalBudgetExceeded` | 1.3% | ran out of compute |
| `Custom(6016/6036/6037)` | ~0.6% | errors propagated from a called DEX (Anchor 6000+ slippage/limit) |

**Routes seen landing** (confirming multi-hop): `Swap2,Sell` · `Swap2,Swap2` · `BuyExactQuoteIn,Swap2` · `SwapV2,Swap2,Swap2` (3-hop) · `Swap2,SwapBaseInput,Swap2` (3-hop) · `BuyExactQuoteIn,Swap`. PumpSwap × Meteora DLMM pairs dominate.

**Per-trade economics** (operator native-SOL + wSOL delta, sampled): typically **+0.002 to +0.07 SOL**, with occasional larger wins (one +0.30 SOL). A few samples read slightly negative under a wSOL-only metric (those took profit in USDC, which this metric doesn't capture). **Priority/Jito tips are scaled to the opportunity** — from 5,000 lamports (no tip) up to ~0.2 SOL on contested, high-value fills.

### Confirmation from a second window (400 txns, same methodology)
A fresh 400-tx pull confirmed the picture: **15.8% land**, 100% of txns run both swaps, `Custom(3)` = 94% of reverts, **single operator `9EwQ…`** (every tx), median CU ~137k on both wins and reverts, median win **+0.0007 SOL**, best win in-window **+0.44 SOL**.

### The win/loss asymmetry (why it works)
A 20-won / 20-lost deep sample showed the real engine:
- **Losing is nearly free.** The 20 reverts cost **~0.00001 SOL each** (base fee only; priority fee ≈ 0 on speculative probes) — about **$0.015 total**.
- **Winning pays a fee scaled to the prize.** Priority fees on wins ranged from `0.00001` SOL up to **1.295 SOL** on the biggest. The bot bids hard *only* when expected profit is high, and those confident shots land more — so "wins have high fees, losses ~zero" is the bot betting hard only when it's sure, not the fee reacting to the outcome.
- **Wins and losses are structurally identical** (same venues, ~2 hops, ~135k CU) — nothing about the route predicts success; only whether the spread survived to landing. The guard is what separates them.
- **Net:** losses ≈ free, wins pay for themselves, a few outliers dominate P&L. A volume machine built on a free-to-lose / pay-to-win asymmetry.

---

## 9. Error-code catalog (program's custom codes) — item #3

Variant N surfaces on-chain as `Custom(N)`:
| Code | Meaning (static context) |
|---|---|
| 3 | **Not profitable** (profit-guard revert) — dominant failure |
| 5 | account index / count out of range |
| 7 | missing operator signer (auth gate) |
| 12 | account data too large (`≥ 0xf5`) |
| 14,15,16 | checked i128 arithmetic overflow in P&L / sizing |
| 6000+ | *propagated from a called DEX program*, not this program |

(An unrelated account-unpack path also uses code 3 for "account data ≤ 71 bytes," but the observed `Custom(3)` failures are all post-swap, i.e. the profit guard.)

---

## 10. Security-relevant conclusions — item #10

- **No hidden privileged instruction.** One code path; no initialize/withdraw/config variants. The program is a **stateless executor** that operates only on accounts the operator passes in.
- **Hard operator gate** (signer must equal `9EwQoN74…`) — the program cannot be driven by third parties, and there are no funds parked in it to drain.
- The only standing risk is the **upgrade authority** (`9EwQoN74…`), which can replace the code at any time.

---

## 11. Residual unknowns

- Exact per-venue **account ordering** is positional and bot-supplied; not enumerated here (it mirrors each DEX's public account layout).
- The precise semantic of ZeroFi's XOR-masked amount field (needs ZeroFi's own spec).
- Whether the Clock is used as a hard deadline vs. only logged (read once in the planner; not traced to a compare).
- Binary is a stripped release build — all of the above is reconstructed from control flow, retained panic-location metadata, and on-chain corroboration; it is documentation of public bytecode, not a reimplementation.

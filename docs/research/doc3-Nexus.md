# Research: Nexus Arb v2 — your program, honestly assessed

**Date:** 2026-10-04 · **Wallet studied:** `2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE` · **Source:** `nexus-program.rs` (native Rust, `solana-program`)
**Scope:** 1,000 most-recent wallet transactions (~243 min window) + full source review.

---

## 1. Verdict up front

**The program is well-built. The money is lost off-chain and at the edges the guard can't see.** Nexus is a clean, careful "Fire-&-Revert" executor — the same family as Program 1, not Program 2. It is doing its job correctly: it reverts the trades that aren't profitable. The problem is that (a) **95% of the time the opportunity is already gone when you land**, and (b) **of the ~2% that do land, about half still lose money** because the profit check ignores the tip and the account rent the transaction actually pays.

Net over the sampled window: roughly **break-even, and only because of one lucky outlier**. Strip the single best trade and it's a steady **bleed** — which matches the wallet being down to ~0.05 SOL.

---

## 2. What the code is (and what's genuinely good)

A native-Rust atomic multi-leg arb executor. `amount_in`, `min_profit`, and the whole route are supplied by your **off-chain builder**; the program executes and guards.

Real strengths — this is not a beginner's program:
- **Exact balance-chaining.** Each leg spends exactly what the previous leg *actually delivered*, measured from the output account's own balance (`delivered()`), not an estimate. Correct and robust.
- **Per-leg error attribution.** `NXV2LEG`/`NXV2OUT` logs name which leg under-delivered — genuinely smart, and visible on-chain (I decoded them in your txns).
- **Error codes in a private range** (`0x4E58_xxxx`) that can't be confused with token (`<32`) or Anchor venue (`6000+`) errors. Thoughtful.
- **A real security model.** The optional payer/token guards defend against the two allowlisted *upgradeable* venues (Raydium-CLMM forks) draining the wallet inside a leg. Most people never think of this.
- **Native-SOL legs** for pump.fun's bonding curve, with a correct "lamports chain only into lamports" rule.
- **Thorough tests.** The host-side test suite pins parsing, guards, encoding, and the cross-language fixture.

Allowlist (12 venues): Meteora DLMM, Orca Whirlpool, Raydium CLMM/CPMM/AMMv4, PumpSwap, PancakeSwap & Byreal (CLMM forks), Meteora DAMM v2, pump.fun curve, Meteora DBC, Raydium LaunchLab.

---

## 3. What the on-chain data says

| Metric | Nexus (your wallet) | Program 1 (Fire-&-Revert) | Program 2 (Simulate-&-Skip) |
|---|---|---|---|
| Throughput | **~4 tx/min** | ~10–17 tx/min | ~118 tx/min |
| **Land rate** | **2.3%** | 15.8% | 99.8% |
| Dominant outcome | **95.3% `ERR_PROFIT` revert** | 83% revert | 98.5% clean no-op |
| Runs swaps on | 100% of txns | 100% | 1.2% |
| Wallet balance now | ~0.05 SOL | — | — |

**Failure breakdown (1,000 txns):** 95.3% `ERR_PROFIT` (ran the legs, round-trip missed `min_profit`, reverted) · 2.3% landed · 1.9% venue `6036` (Whirlpool slippage) · ~0.5% out-of-compute.

The program is working exactly as designed — it is *safely* reverting. But a 2.3% land rate is ~7× worse than Program 1, which runs the **same** philosophy. That gap is not the program; it's the off-chain pipeline losing the race.

---

## 4. The two real problems

### Problem A — you lose the race (95% of spend)
By the time your transaction lands, the spread is gone, so the guard correctly reverts. Likely contributors, from the data:
- **~4 tx/min** is slow for latency arb (Program 2 fires ~118/min). You're not firing on enough opportunities, or not fast enough.
- You build with a **durable nonce** (`advanceNonce` is instruction 0 in your txns). That's a latency smell — the tx can land late into a dead spread.
- **No on-chain quoting.** Program 2 re-checks the opportunity *inside the program* at execution time and no-ops for ~40k CU if it's gone. Nexus can't — it commits to the swaps and pays for a full revert (~100–170k CU) every miss. Same model as Program 1, but your miss rate is far higher, so the waste is larger.

### Problem B — half your *wins* still lose money
This is the quieter, more fixable one. Example landed trade `5RS6vJ1h` — **passed** the profit check, yet the wallet net **−0.00165 SOL**:
- Jito tip ≈ **0.00016 SOL** (transfer to a Jito tip account)
- ATA `createIdempotent` rent ≈ **0.0015 SOL** (instruction 2, before your program runs)
- Your guard measures only the **quote token account**, so it saw a tiny token gain ≥ `min_profit` and passed — **blind to the tip and the rent**, exactly as your own comment admits (*"the transaction fee, tips and account creations outside it do not [count]"*).

Across the 23 landed trades: ~10 are ~−0.0015 SOL, most others are +a-few-lamports, and **one** outlier is +0.0274 SOL. The whole set sums to +0.011 SOL — **all of it from that one trade.** Without it, the "wins" are net negative, before even counting the revert fees.

**Root cause of B:** the off-chain builder sets `min_profit` to clear the guard, not to clear *all-in cost* (tip + ATA rent + fee + margin). The guard rejecting `min_profit == 0` isn't enough — a small positive `min_profit` still lets through trades that lose after the costs the guard can't see.

---

## 5. Fixes, in priority order

1. **Set `min_profit` to all-in cost + margin, off-chain.** `min_profit ≥ tip + expected_ATA_rent + fee + margin`, denominated in the quote token. This alone turns most of the ~10 losing "wins" into correct skips. Cheapest, highest-impact fix.
2. **Stop paying ATA rent every trade.** Pre-create and *keep* your wSOL + hot-token ATAs (or reuse one wSOL account and don't close it). Each new-token `createIdempotent` is ~0.002 SOL the guard ignores. Maintain a warm set.
3. **Bring the guard's blind spot on-chain (optional but strong).** You already have `check_profit_native` (quote tokens + authority lamports). Route the tip and any rent *through the instruction* so the lamport side of the guard sees them — then a landed trade is profit-after-tip by construction, closing Problem B at the program level.
4. **Attack the latency (Problem A).** Drop the durable nonce for a fresh blockhash + Jito bundle; co-locate the sender; raise fire rate. This is where the real upside is, and it's an off-chain project.
5. **Consider a quote-first path for your top venues (the Program 2 lesson).** For DLMM/CLMM/CPMM you can port the math and check the spread *in-program*, converting expensive reverts into ~40k-CU no-ops. Big engineering lift; do it only after 1–4.

---

## 6. Head-to-head: Nexus vs Program 1 (the closest mirror)

Program 1 and Nexus are the **same species** — native Rust, Fire-&-Revert, commit-then-revert on a net≥0 guard, own capital, no on-chain quoting. That makes it the most instructive comparison: same philosophy, opposite results.

| | Program 1 (Babq) | Nexus (yours) |
|---|---|---|
| Legs | route passed in (1–3 seen) | **1–8, one clean loop** |
| Diagnostics | generic `Custom(3)` | **per-leg `NXV2LEG`/`NXV2OUT`** |
| Security guards | operator signer gate | **signer + payer + token guards** |
| Native-SOL legs | — | **yes** |
| Tests | (stripped) | **thorough** |
| **Land rate** | **15.8%** | 2.3% (~7× worse) |
| Throughput | 10–17/min | 4/min |
| Median win | +0.0004 SOL (net+) | ~0 (½ net-negative) |
| On-chain sizing | **yes (`optimize.rs`)** | no (amount_in passed in) |
| Per-trade ATA rent | avoided (reuses accounts) | **~0.0015 paid each trade** |
| Net | profitable | bleeding |

**Nexus is arguably the better-engineered program** (more legs, real guards, better diagnostics). It still loses because Program 1 has three things Nexus lacks — none of them fancy:
1. **On-chain adaptive sizing.** P1 reads the live pool at execution and sizes the trade (fixed vs adaptive, capped). When a spread has shrunk it sizes *down* to a smaller still-profitable trade and lands it; Nexus commits to a pre-decided `amount_in` and reverts. This converts marginal spreads into wins Nexus throws away — a direct chunk of the 7× land gap.
2. **Cost discipline.** P1's wins are net-positive because it reuses accounts (no per-trade ATA rent) and scales its fee to the profit. Nexus pays ATA rent + a tip the guard can't see on trades too thin to cover them.
3. **A faster pipeline.** 10–17/min and no durable nonce — it reaches opportunities while they're alive.

**Takeaway:** you don't need Program 2's 2.76 MB of ported math to beat Program 1 — you need P1's discipline. The single highest-leverage architectural change is **on-chain adaptive sizing** (the one thing P1 has that you don't); the rest is cost accounting and latency.

---

## 7. Bottom line

You built a safe, correct executor and then starved it: the edge that an arb bot lives or dies on is off-chain (speed, opportunity quality, cost-aware sizing), and that's where Nexus is losing. Nothing here is a rewrite. Fixes 1–2 stop the self-inflicted losses this week; on-chain adaptive sizing (the Program 1 lesson) attacks the land rate; latency is the real battle. The program is not why you haven't had success — the pipeline feeding it is.

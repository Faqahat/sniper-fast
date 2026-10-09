# Our on-chain program: old (deployed) vs new (built, not deployed)

## Old — nexus-arb-v2  `8K8uyQDtVKHYRPACP9fepz91q4sEZLBppR2Ty4vdXuWg`
**This is what the bot uses today, live.** (md5 `809315be…`)

Features:
- **Atomic round trip, 1–8 legs** in one loop. The whole transaction reverts unless it ends with at least `min_profit`
  more than it started.
- **Balance chaining:** each leg spends exactly what the previous leg delivered, read from the token account's real
  balance.
- **Venue allowlist (12):** Meteora DLMM, Orca Whirlpool, Raydium CLMM, PumpSwap, PancakeSwap v3, Byreal, Raydium CPMM,
  Raydium AMM v4, Meteora DAMM v2, pump.fun bonding curve (native SOL legs), Meteora DBC, Raydium LaunchLab. Keys
  compared as raw bytes.
- **`min_profit == 0` is rejected** — a break-even route can never pass.
- **Native-SOL legs** (NATIVE_IN / NATIVE_OUT) for pump.fun's bonding curve.
- **Optional payer guard** (an 8-byte trailer): caps how many lamports the wallet may lose, and blocks a malicious
  venue upgrade from taking SOL, other tokens or token-account authority while the quote account still shows a profit.
- **Per-leg logs** (`NXV2LEG`, `NXV2OUT`): every failure names the leg that under-delivered.
- Own error range `0x4E58_xxxx`, no panics on short input.
- **The tip is a separate instruction** in the transaction, not part of the program.

## New — arbx-exec  (built 2026-10-04…10-06, **NOT deployed, no program id yet**)
Started as a copy of nexus-arb-v2. Two instruction layouts, picked by the first byte:

**v2 layout (byte 0 = 2):** parsed byte-for-byte identically to nexus-arb-v2, so the engine can switch to it by
changing only the program id. Adds one `AXS1` summary log per route. A few stricter account-structure checks.

**v3 layout (byte 0 = 3) — the new capabilities:**
- **CPI tip paid from inside the program** (`CPI_TIP`): the Jito tip is paid by the program **only after the profit
  guard passes**, and scales to the realised gain (`clamp(gain × bps)`, with a floor and cap). Today the tip is a
  separate instruction; this makes the tip conditional on real profit and sized to it. **This is the biggest new
  feature for cheap misses / tip-on-profit.**
- **Lamport-accurate guard** (`COUNT_LAMPORTS`): counts lamports lost inside the legs (native swaps, the tip) against
  the gain, so `gain − tip ≥ min_profit` is honest. The old guard only measured the quote token account.
- **Payer guard is mandatory** in v3 (optional trailer in the old one): every venue sees the wallet as a signer.
- **Full 1–255 account count per leg:** fixes the old bug where a leg with 64+ accounts collided with the native-SOL
  flag bits.
- **Per-leg flags** (`leg_flags`) and stricter run-time checks: the quote account and every token output must be owned
  by the authority; a CPI tip must leave the wallet rent-exempt.
- **Structured logs per leg + a summary even on a miss** — a failed route says by how much it missed.
- **Same 12 venues**, plus exact Raydium CLMM and Orca Whirlpool maths proven against the real programs (WP-21).
- **Reserved, not active yet:** on-chain sizing (`SELF_SIZE`, `BASKET`) is rejected with `ERR_UNSUPPORTED` today. The
  maths exist in the `arbx-sizing` crate (the trade shrinks on chain to fit whatever gap is left), but it is **off by
  default** and not wired into a deployable build.

## On-chain sizing: SELF_SIZE and BASKET (designed in `arbx-sizing`, OFF today)
These are the two reserved v3 modes. The maths are built and unit-tested in the `arbx-sizing` crate, but the program
rejects them with `ERR_UNSUPPORTED` until exactness gates pass venue-by-venue, and they need the new program deployed.

- **SELF_SIZE** — the trade **auto-shrinks on chain to fit whatever gap is left**. A 2-leg round trip `A → X → A` (A =
  wSOL or USDC). At execution time, in the current slot, the program finds the input `x` that maximises the round-trip
  profit on the real pool state, instead of using the size we guessed when we sent. Native pump.fun legs are excluded.
- **BASKET** — carries **up to 3 candidate (buy pool, sell pool) pairs for one token X** in one transaction (up to 6
  distinct pools; pools may be shared). The program sizes each pair independently on chain, **executes only the single
  best by exact profit**, and reverts unless it clears `min_profit`. It picks the winning pair at the last moment, so
  if the pair we aimed at has closed by the time we land, it falls back to whichever pair is still open.

**Why these two matter:** gaps close in ~55 ms but we land at 25–200 ms, so the size and pair we chose at send time are
often stale. SELF_SIZE fixes the size on chain; BASKET fixes the pair on chain. Together they are the design the
profitable rivals (Bgok +1.71 SOL/h, A9pQ +0.82 SOL/h) win with.

## Side by side
| | Old (nexus-arb-v2, live) | New (arbx-exec, not deployed) |
|---|---|---|
| Legs | 1–8 | 1–8 |
| Balance chaining | yes | yes |
| Venues allowlisted | 12 | 12 (+ exact CLMM/Whirlpool maths) |
| Profit guard | quote account only | quote **+ lamports** (CPI tip, native) |
| Tip | separate instruction | **paid by the program, only on profit, sized to gain** |
| Payer guard | optional trailer | **mandatory** |
| 64+ accounts per leg | buggy (flag collision) | **fixed (full u8)** |
| Miss diagnostics | per-leg logs | per-leg **+ summary even on miss** |
| On-chain sizing (SELF_SIZE) | no | **designed (off): trade auto-shrinks to the live gap** |
| Multi-pair pick (BASKET) | no | **designed (off): 3 pairs, best one executes on chain** |
| Deployed? | **yes, in use** | **no — needs your deploy** |

## What this means
- The new program's headline win is the **tip paid from inside the program, only when the route actually profits** —
  which is exactly what we need for cheap misses (pay nothing on a loss, tip scaled to the real gain on a win).
- The **on-chain sizing** (trade auto-shrinks to the remaining gap) is the feature that profitable rivals (Bgok, A9pQ)
  use, but it is built as a library and **not yet turned on** in a deployable program.
- Deploying is your action; no program id is fixed yet.

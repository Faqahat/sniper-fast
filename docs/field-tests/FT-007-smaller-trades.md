# FT-007: smaller trade sizes (3 h, live canary on frz)

- **Status:** planned (owner request, 2026-10-06), after FT-006.
- **Mode:** canary, 3 × 60 min, bundle-only. Budget allotment 5,000,000 lamports within the cumulative hard cap.
- **Config:** FT-006's config (with its tip setting if FT-006's decision rule kept it, else FT-005's), with ONE size change:
  - the canary size cap `size_sol` / `max_size_sol` goes from 0.2 to **0.05 SOL**;
  - the size ladder `sizes_sol` gains small rungs: [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05].
  - Evidence: GLiCiNEn's median trade is 0.00065 SOL against our median send of 0.056 SOL. Smaller sizes fit partly-taken gaps and long-tail pools (docs/research/rival-GLiCiNEn.md).
- **Goal:** more wins on small and partly-taken gaps. Measured as net SOL/h and wins/h, not net per win.

## Pass/fail (safety, written before the run)
Same as FT-006: bundle-only, 0 failed-landing fees, every landed trade nets > 0, reconciliation ok, spend within budget.

## What is measured (decision rule)
- Wins/h, win ratio per send, net per win and **net SOL/h**, against FT-006 (and FT-005).
- Realised vs quoted on wins.
- The size distribution of wins.
- **Keep the smaller cap and ladder if net SOL/h ≥ FT-006's**; otherwise keep only the smaller rungs (the engine picks the best size) and restore the 0.2 cap.

**Caveat:** time-separated, as FT-006.

## Stage 0 exit (owner, 2026-10-06)
> **Superseded (owner, 2026-10-06 evening):** Stage 0 now closes **after FT-008** (WP-22 automatic pool refresh), with the criteria below measured over FT-005 + FT-006 + FT-007 + FT-008. See FT-008-auto-pool-refresh.md.

Stage 0 closes **after this test**. The exit report checks PLAN §6 (with the waived coverage gate) and the owner's trade-success criteria over the whole canary series **FT-005 + FT-006 + FT-007 (about 9 h)**:
- every landed trade nets > 0 (0 exceptions);
- series net ≥ 0;
- ≥ 10 wins;
- realised vs quoted median within ±10%;
- win ratio per send ≥ 0.3% (stretch 0.5%);
- bundle-only with 0 failed-landing fees;
- reconciliation ok at every stop.

## Results (3 h: 20:16–23:17 UTC, bin/arbx-6f6163c, `deploy/arbx-ft007-frz.toml`: FT-006's 0.2 tips kept by its rule)

| Segment | Sent | Landed | Win ratio | Net (chain ledger) |
|---|---|---|---|---|
| p1 (20:16–21:17) | 800 | 23 | 2.9% | +58,386 |
| p2 (21:17–22:18) | 738 | 31 | 4.2% | +65,904 |
| p3 (22:18–23:17) | 555 | 11 | 2.0% | +111,648 |
| **Total** | **2,093** | **65** | **3.1%** | **+235,938 lamports** |

**Safety: pass.**
- Bundle-only; **0 failed-landing fees**.
- **Every landed trade nets > 0:** 65 of 65, the smallest +953.
- Final reconciliation ok in all 3 segments (residual 0, executor diff 0, no refused bundle landed).
- Budget: ft007 −235,938, a profit.

**Measured against FT-006:**

| Measure | FT-006 | FT-007 |
|---|---|---|
| **Net SOL/h** | 77,562 | **78,668** |
| Win ratio per send | 1.6% | **3.1%** (best so far) |
| Wins/h | 12.7 | 21.7 |
| Net per win | 6,121 | 3,630 |
| Gross / tips / fees | 555,298 / 132,698 / 190,000 | 797,760 / 236,822 / 325,000 |
| Median winning trade | — | 0.002 SOL (47 of 65 under 0.005) |
| BAM-led / Jito-led land rate | 1.77% / 1.47% | 3.41% / 2.92% |

**Decision (rule written before the run): keep the 0.05 SOL cap and the small rungs.** Net SOL/h 78,668 ≥ FT-006's 77,562. The FT-008 launcher applied it, so FT-008 runs `deploy/arbx-ft008-frz.toml` (FT-007's config + `[pool_refresh]`).
- The margin is small and time-separated: indicative.
- Smaller trades nearly doubled the win ratio, at about 60% of the net per win.
- Fees are now the largest cost: 41% of gross.

**Win mix (Stage 0 exit criterion):**
- 31 meme wins vs 34 common (USDC 29, MET 2, PUMP 1, …), the closest yet. Corrected 2026-10-07: the "CAKE" win was the cake.xmr look-alike (`DAemPFNc…`), a meme, not PancakeSwap's CAKE (WP-11 review #12, classified by mint).
- Memes made about 69% of the net. Attention+ alone: 7 wins, +48,028.

# FT-006: lower tip share on small gaps + BAM landing fix (3 h, live canary on frz)

- **Status:** planned (owner request, 2026-10-06). It runs after FT-005 ends (17:14 UTC) once the BAM fix is committed and built.
- **Mode:** canary under `arbx campaign`, 3 × 60 min, bundle-only.
- **Budget:** WP-07 allotment 5,000,000 lamports within the cumulative 34,000,000 hard cap.
- **Config:** FT-005's config (`deploy/arbx-canary-frz.toml`, fresh pools, plus the BAM fix's settings) with ONE tip change:
  - `[tips] shares` = [0.20, 0.20, 0.20, 0.60, 0.70] for edge bands [<20k, 20k–100k, 100k–1M, 1M–10M, ≥10M], from 0.70 everywhere;
  - `contested_shares` = [0.16, 0.20, 0.20, 0.60, 0.64];
  - floor 1,000 and cap 100,000 unchanged.
  - Evidence: GLiCiNEn lands about 1,360 arbs/h paying about 15% of gross and raises its tip only on big gaps (docs/research/rival-GLiCiNEn.md).
- **Goal:** more profit per win (lower tips) and more wins on BAM leaders (the fix), without losing landings.

## Pass/fail (safety, written before the run)
1. Bundle-only; 0 failed-landing fees.
2. Every landed trade nets > 0 after fee + tip + rent (0 exceptions); create+close rent fully returned.
3. Reconciliation ok at every stop; spend within budget; no refused bundle lands.

## What is measured (the decision rule, written before the run)
Measured against FT-005, the same build family on the same fresh pools:

| Measure | Expected | Decision |
|---|---|---|
| Net per win | about 2× (tip ~20% instead of ~50–65% of gross) | — |
| Win ratio per send | unchanged or a small drop (lower tips lose some auctions) | — |
| **Net SOL/h** | **≥ FT-005's** | **keep the low tips if net SOL/h ≥ FT-005; else try 0.35, or revert** |
| BAM landing rate (landed / sends targeted at BAM leaders) | from 1.2% (FT-004) to ≥ 70% of the Jito-leader rate | keep the BAM fix if met |

**Caveat:** a time-separated comparison (FT-005 then FT-006), not a concurrent A/B. Market conditions differ, so 3 h is indicative. The concurrent X4 arms come with WP-11.

## Results (3 h: 17:15–20:16 UTC, bin/arbx-6f6163c)

| Segment | Sent | Landed | Win ratio | Net (chain ledger) |
|---|---|---|---|---|
| p1 (17:15–18:15) | 851 | 13 | 1.5% | +112,447 |
| p2 (18:15–19:16) | 899 | 16 | 1.8% | +68,713 |
| p3 (19:16–20:15) | 654 | 9 | 1.4% | +51,440 |
| **Total** | **2,404** | **38** | **1.6%** | **+232,600 lamports** |

**Safety: pass.**
- Bundle-only; **0 failed-landing fees**.
- **Every landed trade nets > 0:** 38 of 38, the smallest +602.
- Rent: 20,990,560 locked and recovered in the same transactions, 0 non-recoverable.
- Final reconciliation ok in all 3 segments (residual 0, executor diff 0, no refused bundle landed).
- Budget: ft006 −232,600, a profit.

**Measured against FT-005:**

| Measure | FT-005 | FT-006 | Change |
|---|---|---|---|
| **Net SOL/h** | 74,600 | **77,562** | +4% |
| Win ratio per send | 2.6% | 1.6% | −39% |
| Net per win | 4,127 | 6,121 | +48% |
| Tips / gross | 52% | 24% | |
| We keep of gross | 22% | 42% | |
| Jito-led land rate | 3.4% (43/1,253) | 1.47% (22/1,498) | lower tips lose Jito auctions |
| **BAM-led land rate** | 1.3% (11/825) | **1.77% (16/906)** | +36%; now ≥ Jito's |

**Decisions (rules written before the run):**
- **Keep the 0.2 tips:** net SOL/h 77,562 ≥ FT-005's 74,600. Applied automatically by the FT-007 launcher (FT-007 runs `deploy/arbx-ft007-frz.toml`). The margin is small (+4%) and time-separated, so it is indicative: lower tips traded about 40% of landings for about 1.5× net per win.
- **Keep the BAM fix:** BAM's land rate reached 120% of Jito's (target ≥ 70%). Caveat: part of that is Jito's rate falling with the lower tips; BAM's own rate rose from 1.3% to 1.77%.

**Win mix (Stage 0 exit criterion):**
- 9 meme wins against 29 common (USDC 24, MET 5).
- Memes made **72% of the net** (+168,354 of +232,600): Cadence +82,773, STONK +34,092, ANSEM +28,551, Buttcoin +12,282, GRIFFAIN 2 × ~3,300.

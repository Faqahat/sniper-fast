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

## Results
(filled in)

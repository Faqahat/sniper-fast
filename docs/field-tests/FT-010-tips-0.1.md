# FT-010: tip share 0.1 on small and mid gaps (3 h, live canary on frz)

- **Status:** planned (owner OK, 2026-10-07). It runs after FT-009 (the Whirlpool/CLMM shadow test). WP-11's side-by-side tip arms supersede it once built.
- **Mode:** canary under `arbx campaign`, 6 × 30 min (FT-008's segment length), bundle-only.
- **Budget:** WP-07 allotment 5,000,000 lamports within the cumulative 34,000,000 hard cap.
- **Config:** FT-008's config as it ran (FT-007's settings + WP-22 pool refresh, if FT-008 keeps it) with ONE change:
  - `[tips] shares` = [0.10, 0.10, 0.10, 0.60, 0.70], from 0.20 on the three bands under 1,000,000 lamports of edge;
  - `contested_shares` = [0.10, 0.10, 0.10, 0.60, 0.64];
  - floor 1,000 and cap 100,000 unchanged; the BAM floor (`[send_policy.bam]`) still raises BAM-led bids.
- **Evidence:**
  - FT-006 (0.7 → 0.2): net per win +48%, Jito-led land rate 3.4% → 1.47%, net SOL/h +4%.
  - In FT-006 and FT-007, 37–40% of wins already paid the 1,000-lamport floor, and tips were 24–30% of gross. The remaining room is small, so this test checks whether it is positive at all.
- **Goal:** find whether 0.1 beats 0.2 on net SOL/h.

## Pass/fail (safety, written before the run)
1. Bundle-only; 0 failed-landing fees.
2. Every landed trade nets > 0 after fee + tip + rent; create+close rent fully returned.
3. Reconciliation ok at every stop; spend within budget; no refused bundle lands.

## What is measured (decision rule, written before the run)
- Net SOL/h, wins/h, win ratio, net per win, tips/gross and land rate by leader kind, against FT-008.
- The meme vs common win mix (FT-008's definition).
- **Keep 0.1 if net SOL/h ≥ FT-008's; else return to 0.2.**

**Caveat:** time-separated (FT-008 then FT-010), so indicative. WP-11 arms give the clean answer.

## Results (3 h: 04:26–07:27 UTC, bin/arbx-b1318ef, `deploy/arbx-ft010-frz.toml`)

| Segment | Sent | Landed | Net (chain ledger) |
|---|---|---|---|
| p1 | 250 | 9 | +11,621 |
| p2 | 333 | 16 | +97,240 |
| p3 | 274 | 4 | +4,000 |
| p4 | 279 | 13 | +31,718 |
| p5 | 176 | 7 | +30,055 |
| p6 | 216 | 7 | +24,315 |
| **Total** | **1,528** | **56 (3.7%)** | **+198,949 lamports** |

**Safety: pass.**
- Bundle-only; 0 failed-landing fees.
- Every landed trade nets > 0 (56 of 56, the smallest +1,000).
- Final reconciliation ok in all 6 segments (residual 0, executor diff 0).

**Measured against FT-008:**

| Measure | FT-008 (0.2 tips) | FT-010 (0.1 tips) |
|---|---|---|
| **Net SOL/h** | 91,982 | **66,612** |
| Sent | 2,282 | 1,528 (a quieter morning; the list was refreshed down to 1,225 pools) |
| Win ratio | 3.2% | 3.7% |
| Net per win | 3,711 | 3,553 |
| Tips / fees per gross | 31% / 39% | 19% / 47% |
| Jito-led / BAM-led land rate | 3.35% / 3.04% | 4.27% / 2.77% |
| Meme / common wins | 42 / 32 | 15 / 41 (memes 47% of the net) |

**Decision (rule): return to 0.2.** Net SOL/h 66,612 is below FT-008's 91,982.
- Time-separated: FT-010 sent a third fewer bundles in quieter hours, while its win ratio and Jito-led land rate were higher.
- **FT-012 (side by side, same hours) decides the tip question properly.** Its 0.2 control arm stays in place.

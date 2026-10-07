# FT-011: size cap back to the wallet's limit, small rungs kept (3 h, live canary on frz)

- **Status:** superseded by FT-012 (2026-10-07). WP-11 was built and reviewed early, and FT-012 tests the 0.05 vs 0.2 cap side by side in the same hours.
- **Mode:** canary under `arbx campaign`, 6 × 30 min, bundle-only. Budget: WP-07 allotment 5,000,000 lamports.
- **Config:** FT-010's config as decided by its rule, with ONE change:
  - `[canary] size_sol` and `[live] max_size_sol` 0.05 → **0.2 SOL**;
  - `sizes_sol` = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05, 0.1, 0.2] (FT-007's small rungs kept).
  - The bankroll rules still bind below that: 85% of liquid SOL + WSOL − 0.03 SOL, and at most the WSOL (about 0.19 SOL today).
- **Evidence:**
  - FT-006 (cap 0.2): 5 of 38 wins were larger than 0.05 SOL and made 50% of the net.
  - FT-007 (cap 0.05): 3 wins sat exactly at the cap.
  - The engine picks the most profitable size per gap, so a higher cap only adds options.
- **Goal:** keep FT-007's win ratio from small trades and win back FT-006's big-gap profit.

## Pass/fail (safety, written before the run)
Same as FT-010: bundle-only with 0 failed-landing fees; every landed trade nets > 0; reconciliation ok; spend within budget.

## What is measured (decision rule, written before the run)
- Net SOL/h, wins/h, win ratio, net per win, and the share of net from wins above 0.05 SOL, against FT-010 (and FT-008).
- The meme vs common win mix.
- **Keep the 0.2 cap if net SOL/h ≥ FT-010's; else return to 0.05.**

## Results
(filled in)

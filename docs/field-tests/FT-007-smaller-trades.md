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
Stage 0 closes **after this test**. The exit report checks PLAN §6 (with the waived coverage gate) and the owner's trade-success criteria over the whole canary series **FT-005 + FT-006 + FT-007 (about 9 h)**:
- every landed trade nets > 0 (0 exceptions);
- series net ≥ 0;
- ≥ 10 wins;
- realised vs quoted median within ±10%;
- win ratio per send ≥ 0.3% (stretch 0.5%);
- bundle-only with 0 failed-landing fees;
- reconciliation ok at every stop.

## Results
(filled in)

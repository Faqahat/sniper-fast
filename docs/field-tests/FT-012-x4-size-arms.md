# FT-012: tip share × size cap, side by side (WP-11 arms), 12 h live canary on frz

- **Status:** planned (owner OK, 2026-10-07: "the side-by-side version once WP-11 is built"). It runs after FT-009 part 2 (the dry run), at about 08:30 UTC.
  - It supersedes FT-011 (size cap) and settles FT-010's tip question in the same hours.
- **Build:** master 8f76922 (WP-11 merged, reviewed, before-run fixes re-checked). The binary's git hash and sha256 are recorded at the start.
- **Mode:** canary under `arbx campaign`, 12 × 60 min, bundle-only. `[canary] every_ms` stays 1000 (one send a second, as in FT-005..FT-010).
- **Budget:** WP-07 allotment 5,000,000 lamports within the cumulative 34,000,000 hard cap (we are about +1,000,000 in profit overall).
- **Config:** `deploy/arbx-ft-x4size-frz.toml`, which is FT-008's config (WP-22 refresh on, BAM fix on) plus:
  - `sizes_sol` gains the rungs 0.1 and 0.2;
  - `[canary] size_sol` and `[live] max_size_sol` are 0.2. The bankroll rules still bind: 85% of liquid SOL + WSOL − 0.03, at most the WSOL (about 0.19 SOL).
  - **x4 tip-share arms [0.2 (control), 0.1, 0.35]** on bands under 1,000,000 lamports of edge. Floor 1,000 and cap 100,000 are kept, and the BAM floor still raises BAM-led bids.
  - **Size-cap arms [0.05 (control), 0.2] SOL.**
  - Each decision's arms are drawn by `xxh3(seed mixed with the segment name, experiment, decision id)`: replayable, independent, 6 cells.

## Pass/fail (safety, written before the run)
1. Bundle-only; 0 failed-landing fees.
2. Every landed trade nets > 0 after fee + tip + rent (0 exceptions); create+close rent fully returned.
3. Reconciliation ok at every stop; spend within budget; no refused bundle lands.
4. No `size_arm` or `size_cap` refusal of an engine-priced route (the engine never prices past its arm).

## What is measured (decision rules, written before the run)
`arbx-report experiments` (R10) per arm. Compare per send, because the arms share the one-send-a-second slot; `canary_wait` refusals per arm show that competition.
- **X4 (tips):**
  - land rate per send, Jito-led first (the BAM floor erases most of the contrast on BAM-led slots);
  - net per send, net per win, tips/gross.
  - **Adopt an arm over 0.2** if its Jito-led land-rate drop's 95% upper bound is below 20% and its net per send is at least the control's. Otherwise keep 0.2.
- **Size:** land rate and net per send, net per win, and the share of net from wins above 0.05 SOL.
  - **Adopt 0.2** if its net per send is at least the 0.05 arm's (the interval reported).
- **Win mix:** meme vs common wins per arm and in total (by mint).
- **Power** (WP-11 estimate at about 700 sends/h): about 2,800 sends per X4 arm and 4,200 per size arm. Enough to see about a ±50% difference in wins per send; smaller differences are reported as not resolved.
- **Context:** FT-010's time-separated 0.1 result. FT-012's same-hour comparison takes precedence.

## Results
(filled in)

# FT-008: automatic pool refresh, WP-22 (3 h, live canary on frz)

- **Status:** planned (owner request, 2026-10-06). It runs after FT-007, once WP-22 is reviewed, built and deployed. **Stage 0 closes after this test.**
- **Mode:** canary under `arbx campaign`, 6 × 30 min, bundle-only.
  - Each segment boots on the list refreshed during the segment before it: 5 refreshes in the run.
  - Segments are 30 min so the refresh is exercised often.
- **Budget:** WP-07 allotment 5,000,000 lamports within the cumulative 34,000,000 hard cap.
- **Config:** FT-007's config, with the tip and size settings FT-006's and FT-007's decision rules kept, and ONE change: `[pool_refresh] enabled = true`.
  - The first segment starts from the same list as FT-005 to FT-007 (data/seed-pools-20261006.csv).
- **Goal:** catch active multi-pool tokens (like BINDER) within the hour, automatically and safely, and measure whether trading them adds wins.

## Pass/fail (safety, written before the run)
1. Bundle-only; 0 failed-landing fees.
2. Every landed trade nets > 0 after fee + tip + rent (0 exceptions); create+close rent fully returned.
3. Reconciliation ok at every stop; spend within budget; no refused bundle lands.
4. No segment boots on an unverified pool list: every list has its verification record and hash.

## Pass/fail (function)
- Every refresh either completes within 5 min or keeps the previous list with a recorded reason.
- The gap between segments is ≤ 2 min (today's restart takes about 1 min).
- Every added pool passed on-chain verification (recorded).
- Added pools cause no state or decode errors: the state-health gate never trips on them.

## What is measured (decision rule)
- Pools added, dropped and kept per refresh, by source (our records, GeckoTerminal, DexScreener).
- Opportunities, sends and wins on pools WP-22 added, as a share of the run's totals.
- Net SOL/h and wins/h against FT-007 (time-separated, so indicative).
- **Decision:**
  - Keep the automatic refresh on for Stage 1 if both pass/fail lists hold.
  - Its value (wins on added pools) is reported, with no fixed threshold over 3 h.

## Stage 0 exit (owner, 2026-10-06 evening)
Stage 0 closes **after this test**. The exit report checks PLAN §6 (with the waived coverage gate) and the owner's trade-success criteria over the whole canary series **FT-005 + FT-006 + FT-007 + FT-008 (about 12 h)**:
- every landed trade nets > 0 (0 exceptions);
- series net ≥ 0;
- ≥ 10 wins;
- realised vs quoted median within ±10%;
- win ratio per send ≥ 0.3% (stretch 0.5%);
- bundle-only with 0 failed-landing fees;
- reconciliation ok at every stop.

## Pre-flight (WP-22, before the run; read-only)
On Cherry, with the FT-008 binary and config deployed, against FT-006's records (nothing is locked or sent, the gRPC
stream is never opened, the verification RPC is `[pool_refresh] rpc`: the public RPC, at most 2 requests a second):

    nice -n 10 arbx pools refresh --config /root/arbx/deploy/arbx-ft008-frz.toml --runs /root/arbx/runs/ft006 \
        --out /root/arbx/runs/wp22-preflight/pools.csv --segment preflight
    arbx pools refresh --config /root/arbx/deploy/arbx-ft008-frz.toml --inputs /root/arbx/runs/wp22-preflight/pools.csv.inputs.json \
        --out /root/arbx/runs/wp22-preflight/replayed.csv --segment preflight     (the same sha256: deterministic)

Check in `pools.csv.report.json`: `status` ok (`kept_previous` with an RPC reason: the public RPC refuses Cherry, switch
`rpc`); `duration_ms` well under 225,000 (the refresh's own deadline); `sources.*.status` ok; `records` one entry per
FT-006 segment, each `ok`, with `unlisted_pools_seen` > 0; `counts.rows` <= 1,500; `added` tokens with 2+ pools that look
right (BINDER-like), every one with `quote_liquidity` >= 2 SOL; `rejected_by` mostly `group`, `liquidity`, `quote`.
A local run of the same command on FT-005b's first segment (2026-10-06): 53 s, +13 added (4 records, 3 GeckoTerminal, 6
DexScreener), 13 idle pools cut by the cap, 23 getMultipleAccounts on the public RPC.

## Results
(filled in)

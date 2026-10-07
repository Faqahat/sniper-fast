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
- reconciliation ok at every stop;
- **win mix (owner, 2026-10-06 evening): more wins through meme / long-tail tokens than through common tokens.**
  - **Counted over FT-007 + FT-008 only** (owner, 2026-10-07: "meme rule is for ft007,008"), the final configuration's tests. The other criteria still cover FT-005..FT-008.
  - Standing at 01:00 UTC: FT-007 30 meme vs 35 common; FT-008 so far 16 vs 14; together 46 vs 49.
  - **Common tokens:**
    - stablecoins: USDC, USDT, USD1, PYUSD;
    - liquid-staking SOL: JitoSOL, mSOL, JupSOL, bSOL, INF;
    - wrapped majors: WBTC, cbBTC, WETH, ZEC;
    - protocol tokens: JUP, MET (Meteora), RAY, ORCA, JTO, PYTH, W, DRIFT, KMNO, JLP, BELIEVE, PUMP (pump.fun), CAKE (PancakeSwap).
  - **Meme:** every other token (pump.fun, bonk.fun and other launches).
  - **How it is counted:** each win by the token its route trades through (`route.mint` in attempts.jsonl). The exit report lists every win's token, and the mix is also reported by net.
  - **Standing on 2026-10-06 at 18:30 UTC:**
    - FT-005: 15 meme wins vs 39 common (USDC 28, MET 5, JUP 4, BELIEVE 1, USDT 1), but memes made 56% of the net (+125,384 of +222,873).
    - FT-006 so far: 1 meme win vs 7 common; the one meme win (+82,773) is 82% of its net.

## Pre-flight (WP-22, before the run; read-only)
On Cherry, with the WP-22 binary and deploy/arbx-ft008-frz.toml uploaded, against FT-006's records (FT-007's when they
exist). It may run while a campaign runs: nothing is locked or sent, the gRPC stream is never opened, it runs at nice 10,
and it verifies through `[pool_refresh] rpc` (the public RPC, at most 2 requests a second, never Haan or Shyft); a running
segment's records are read as far as they are written. It loads only its verification endpoints' variables from the
.env (none for the public RPC) and runs at nice +10 with the I/O class idle. `<bin>` is the uploaded WP-22 binary
(`/root/arbx/bin/arbx-<commit>`):

    nice -n 10 <bin> pools refresh --config /root/arbx/deploy/arbx-ft008-frz.toml --runs /root/arbx/runs/ft006 \
        --out /root/arbx/runs/wp22-preflight/pools.csv --segment preflight
    <bin> pools refresh --config /root/arbx/deploy/arbx-ft008-frz.toml --inputs /root/arbx/runs/wp22-preflight/pools.csv.inputs.json \
        --out /root/arbx/runs/wp22-preflight/replayed.csv --segment preflight

Each prints `pool refresh for preflight: ...` and `list <file> (sha256 <hash>)`: the two hashes must be equal (the same
inputs give the same list). Exit 0 when the list was refreshed, 3 when the previous list was kept. Check in
`pools.csv.report.json`:
- `status` ok. `kept_previous` with an RPC reason (HTTP 403 or 429 from api.mainnet-beta.solana.com) means the public
  RPC refuses Cherry: name another `[[rpc.endpoint]]` in `[pool_refresh] rpc` (a key of its own; never Haan's, and not
  Shyft's, whose slot index takes 3.8 of its 4 req/s).
- `duration_ms` well under 225,000 (the refresh's own deadline; locally 20-53 s).
- `sources.geckoterminal.status`, `sources.dexscreener.status` ok; `sources.records.status` ok with
  `unlisted_pools_seen` > 0 (the last segment's rival arbitrage on pools we do not list).
- `records`: one entry per FT-006 segment, each `ok`.
- `counts.rows` <= 1,500; `counts.dropped_by` with few `dead:*` (only pools the last boot had dropped too); few
  `counts.kept_unconfirmed` (pools the RPC called dead but the last boot found alive: kept; more than 75 for 1,500 rows
  keeps the previous list); `shrink_guard.idle_dropped` <= 150 (max(25, a tenth of the list)).
- `segments_counted_for_idle`: every complete ft006 segment `counts: true` (its triggers span 80% of its 60 minutes,
  with a trigger in 80% of them); a running one counts once half of it has elapsed.
- `added`: tokens with 2+ pools that look right (BINDER-like), every one with `quote_liquidity` >= 2,000,000,000.
- `rejected_by` mostly `group`, `liquidity`, `quote`; `rpc.calls` about 20-50.

Local runs (2026-10-06, the public RPC): FT-005b's first segment with 1 of its 31 exec files and live GeckoTerminal and
DexScreener, 53 s, +13 added (4 records, 3 GeckoTerminal, 6 DexScreener; BINDER and EXTRACTOR 3 pools each), 13 idle pools
cut by the cap, 23 getMultipleAccounts; the same segment with a full hour of exec files (31 files, 5.0 GB decompressed)
and recorded web answers: the records read in 9.6 s, the refresh 20 s.

## Results (3 h: 23:17–02:18 UTC, bin/arbx-b1318ef, `deploy/arbx-ft008-frz.toml`: FT-007's settings + WP-22)

| Segment | Pools (source) | Sent | Landed | Win ratio | Net (chain ledger) |
|---|---|---|---|---|---|
| p1 (23:17) | 1,500 (config) | 280 | 10 | 3.6% | +32,887 |
| p2 (23:48) | 1,500 (refresh: +26) | 363 | 11 | 3.0% | +44,295 |
| p3 (00:19) | 1,500 (refresh: +5) | 300 | 6 | 2.0% | +13,477 |
| p4 (00:50) | 1,500 (refresh: +1) | 346 | 9 | 2.6% | +41,727 |
| p5 (01:21) | 1,361 (refresh: +11, −150 idle) | 478 | 20 | 4.2% | +52,159 |
| p6 (01:52) | 1,232 (refresh: +7, −136 idle) | 515 | 18 | 3.5% | +90,099 |
| **Total** | | **2,282** | **74** | **3.2%** | **+274,644 lamports** |

**Safety: pass.**
- Bundle-only; **0 failed-landing fees**.
- **Every landed trade nets > 0:** 74 of 74, the smallest +84.
- Final reconciliation ok in all 6 segments (residual 0, executor diff 0, no refused bundle landed).
- The send gate stayed live all run (stopped only at each segment's end); recorder drops 0.
- **No segment booted on an unverified list:** `pool_lists` shows the config list, then 5 refreshed lists, every one `ok` and hash-checked.

**Function: pass.**
- Every refresh completed `ok` in 63–79 s (limit 5 min).
- The gap between segments stayed about 20–60 s.
- Every added pool was verified on chain.
- No state-health trip.

**Measured:**

| Measure | FT-007 | FT-008 |
|---|---|---|
| **Net SOL/h** | 78,668 | **91,982** (+17%) |
| Win ratio | 3.1% | 3.2% |
| Net per win | 3,630 | 3,711 |
| Tips / fees / gross | 236,822 / 325,000 / 797,760 | 292,859 / 370,000 / 937,503 |
| BAM-led / Jito-led land rate | 3.41% / 2.92% | 3.04% / 3.35% |

- **Refreshes:**
  - added 26, 5, 1, 11, 7 (records first, then DexScreener);
  - dropped 26, 5, 1 by the cap;
  - then 150 and 136 idle drops (the shrink guard held 280, then 157).
  - Additions dry up between 30-minute refreshes: the trending lists repeat.
- **Wins on WP-22-added pools:** 5 (+7,458, 3% of the net).
  - Most of FT-008's gain is not from new pools.
  - The two best segments (p5, p6) ran on the idle-trimmed lists. Whether trimming helps, or the hour did, is not separable here (time-separated).
- **Decision (rule): keep the automatic refresh on for Stage 1.** Both pass/fail lists hold.
  - Next steps: new pools from creation events in our own feed, and adding the CLMM venues to the refresh.

**Win mix (Stage 0 rule, FT-007 + FT-008):**
- FT-008: 42 meme vs 32 common (USDC 27, USDT 5). Memes made 73% of the net.
- Together: **73 meme vs 66 common: met.** Classified by mint; FT-007's "CAKE" win was the cake.xmr meme (WP-11 review #12).

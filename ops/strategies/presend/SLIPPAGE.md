# Pre-send price limit: what if we allowed MORE slippage? (10-29 ~03:00 PKT)

Owner question 10-29 02:30 PKT: "what if we had INCREASED slippage" on the pre-send buys, i.e. a looser price limit than the live 0.88.
Analyst task. Offline replay only: nothing sent, no server writes, no engine or config change.
- MEASURED = live run records or the chain recording.
- INFERRED = replay output.
- Times are PKT.

## Verdict
**No. More slippage makes less money on all three runs, and the further you loosen it, the more you lose.**
- **0.90:** −0.61 SOL over the three runs vs live (90% CI −1.38 to +0.05; better in only 7% of resamples).
- **0.92:** −1.55 SOL (CI −2.48 to −0.69).
- **0.95:** −3.52 SOL (CI −5.04 to −2.05). The three runs would have ended at −0.94 SOL in total instead of the live +2.58.
- **0.86 (tighter):** 19% fewer fills. The replay says −0.03 SOL (CI −0.58 to +0.49). On the live P&L of the fills it would drop, it is about −0.2 SOL. There is no gain in that direction either.

**Why (INFERRED, backed by MEASURED live fills):**
1. **The extra fills are the shallow dips.** These are windows whose price never fell 12% below the signing price.
   - At 10–12% down they are about break-even: +3.4 mSOL per fill, 55% wins.
   - Below 10% down they lose: −9 to −10 mSOL per fill at 8–10%, and −5 at 5–8%.
   - The live fills show the same slope (MEASURED): fills at 12–14% down made +2.3 mSOL each, at 14–18% +8.6, at 18–25% +14.1.
2. **The big cost: a looser limit buys real dumps too early.** Many −12% dumps arrive in steps: a small −10% sell first, then the big one.
   - With 0.90 we buy on the small step.
   - The big dump then lands on our position, and the 200 ms exit (or the stop-loss) sells into it. We also lose the good fill we got live.
   - Cost: **−54 mSOL per such window at 0.90** (15 windows: 0 better, 12 worse), −44 at 0.92 (30 windows), −46 at 0.95 (52 windows).

**How sure:**
- The replay reproduces the live runs at 0.88 try for try: the same fill try in 326 of 326 fills, and the same chain result on 43,710 of 43,710 tries.
- P&L is within 5.7% of live pooled (+5.3%, −10.0% and −8.0% per run).
- The answer holds when the exit timing is changed by ±30%. 0.90 is worse in 8 of the 12 hours where it changes anything (0.92: 10 of 13).
- **Sample: 3 runs, ~12 h, 326 live fills.** The 0.92 and 0.95 results are clear. For 0.90 the direction is clear, but the size (about −0.2 SOL per run) is not precise.

## Pooled table (FRA r28 + AMS r34 + AMS r35)
Totals are anchored on live: live net (MEASURED) plus the replay's change on each window (L minus the replay at 0.88).
| Limit | Fills | Extra vs live | Bought earlier | Lost | Total net (SOL) | vs live [90% CI] | Per fill (mSOL) |
|---|---|---|---|---|---|---|---|
| 0.86 | 264 | −62 | 2 | 62 | +2.550 | −0.026 [−0.578, +0.485] | +9.7 |
| **0.88 (live)** | **326** | – | – | – | **+2.577** | – | **+7.9** |
| 0.90 | 382 | +56 | 15 | 0 | +1.967 | −0.610 [−1.377, +0.054] | +5.2 |
| 0.92 | 433 | +107 | 30 | 1 | +1.025 | −1.552 [−2.476, −0.691] | +2.4 |
| 0.95 | 569 | +243 | 52 | 2 | −0.940 | −3.517 [−5.038, −2.049] | −1.7 |

| Limit | Extra fills' own P&L (SOL; per fill) | Bought-earlier windows (SOL) | Flat share, all / extra | 20% fewer followers: vs live |
|---|---|---|---|---|
| 0.90 | +0.193 (+3.4 mSOL) | −0.802 | 13% / 15% | −1.051 |
| 0.92 | −0.219 (−2.0) | −1.327 | 17% / 28% | −2.273 |
| 0.95 | −1.166 (−4.8) | −2.369 | 22% / 32% | −4.978 |

How to read the tables:
- **"Bought earlier"** = windows that filled live, but where the looser limit fills an earlier, shallower try first.
- **"Lost"** = live fills that do not happen. At 0.86 the live fill try fails the limit. At 0.92/0.95 the try is not sent because another counterfactual position is open (the one-position pause).
- **"Flat"** = no other wallet trades between our buy and our sell. Live is 12% flat (MEASURED), and the replay at 0.88 also gives 12%.

**Depth of the dumps behind the extra fills** (drop below the price when the try was signed, at the moment it fills; pooled):
| Limit | 10–12% down | 8–10% down | 5–8% down | Deepest any try in those windows saw (median) |
|---|---|---|---|---|
| 0.90 | 56 fills, +0.193 SOL, 55% win | – | – | 11.1% |
| 0.92 | 51, +0.283, 55% | 57, −0.502, 21% | – | 10.1% |
| 0.95 | 44, +0.078, 52% | 48, −0.495, 21% | 153, −0.749, 27% | 7.8% |

## Per run
Totals use the same anchoring as above (live net + replay change vs 0.88).

**FRA r28** (0.45 SOL, TP 10%, 10-28 14:32–20:02).
- Live +0.517 on 78 fills (MEASURED; on-chain +0.516).
- Replay at 0.88: +0.544 (+5.3%).

| Limit | Fills (extra / earlier / lost) | Extra fills' P&L | Total net | vs live [90% CI] | Per fill | Flat all / extra |
|---|---|---|---|---|---|---|
| 0.86 | 64 (0 / 1 / 14) | – | +0.442 | −0.075 [−0.362, +0.170] | +6.9 | 4% / – |
| 0.88 live | 78 | – | +0.517 | – | +6.6 | 7% |
| 0.90 | 88 (10 / 4 / 0) | +0.050 | +0.449 | −0.068 [−0.288, +0.106] | +5.1 | 9% / 20% |
| 0.92 | 101 (23 / 9 / 0) | +0.025 | +0.299 | −0.218 [−0.566, +0.110] | +3.0 | 12% / 29% |
| 0.95 | 145 (67 / 12 / 0) | −0.182 | −0.184 | −0.700 [−1.204, −0.240] | −1.3 | 21% / 35% |

**AMS r34** (0.45 SOL, TP 10%, 10-28 20:07–23:16).
- Live +0.526 on 120 fills (MEASURED; on-chain +0.523).
- Replay at 0.88: +0.473 (−10.0%).

| Limit | Fills (extra / earlier / lost) | Extra fills' P&L | Total net | vs live [90% CI] | Per fill | Flat all / extra |
|---|---|---|---|---|---|---|
| 0.86 | 92 (0 / 0 / 28) | – | +0.690 | +0.164 [+0.000, +0.343] | +7.5 | 9% / – |
| 0.88 live | 120 | – | +0.526 | – | +4.4 | 11% |
| 0.90 | 139 (19 / 4 / 0) | +0.018 | +0.362 | −0.164 [−0.459, +0.089] | +2.6 | 12% / 16% |
| 0.92 | 159 (39 / 7 / 0) | +0.054 | +0.366 | −0.160 [−0.531, +0.204] | +2.3 | 16% / 27% |
| 0.95 | 208 (89 / 17 / 1) | −0.318 | −0.488 | −1.014 [−1.623, −0.447] | −2.3 | 22% / 34% |

**AMS r35** (LIVE, 0.65 SOL, TP 20%; records read 10-29 02:32 PKT, tries 23:19 → 02:29).
- Live +1.534 on 128 fills so far (MEASURED: realized + rent back − failed tries).
- Replay at 0.88: +1.411 (−8.0%).

| Limit | Fills (extra / earlier / lost) | Extra fills' P&L | Total net | vs live [90% CI] | Per fill | Flat all / extra |
|---|---|---|---|---|---|---|
| 0.86 | 108 (0 / 1 / 20) | – | +1.418 | −0.116 [−0.538, +0.268] | +13.1 | 14% / – |
| 0.88 live | 128 | – | +1.534 | – | +12.0 | 15% |
| 0.90 | 155 (27 / 7 / 0) | +0.124 | +1.156 | −0.377 [−1.034, +0.230] | +7.5 | 15% / 13% |
| 0.92 | 173 (46 / 14 / 1) | −0.298 | +0.360 | −1.174 [−1.920, −0.474] | +2.1 | 20% / 29% |
| 0.95 | 216 (89 / 23 / 1) | −0.666 | −0.269 | −1.802 [−3.061, −0.588] | −1.2 | 23% / 27% |

In r35, the 8–10% extra fills are the worst bucket: 21 fills, −25 mSOL each, 10% wins. These are bigger buys (0.65 SOL) into dumps that keep falling.

**Examples of "bought earlier" at 0.90** (replay, mSOL; live = MEASURED):
- r35 7VjKDG: 0.90 fills at −10% one slot before a 7.7 SOL dump to −37%. Stop-loss: **−148**. Live bought at −34%: **+52**.
- r34 FWS5Hm: 0.90 fills just before a 6.6 SOL dump to −33%. Stop-loss: **−99**. Live: **+18**.
- r35 F1kEVf: 0.90 fills at −11.7%, then a 2.3 SOL dump to −21% comes. Result **−38**. Live bought after the dump: **+38**.

## Validation at 0.88 (the live limit)
| Check | r28 | r34 | r35 |
|---|---|---|---|
| Recorded min-out reproduced by limit_min_out (every try) | 11,230 / 11,230 | 17,556 / 17,556 | 21,294 / 21,294 |
| Per-try result (filled vs 6042) from the curve state before the try | 9,976 / 9,976 | 15,354 / 15,354 | 18,380 / 18,380 |
| Same fill try as live (pass mark ≥ 95%) | 78 / 78 | 120 / 120 | 128 / 128 |
| Fill tokens exact (pump math: sol_in − 1) | 78 / 78 | 120 / 120 | 128 / 128 |
| Sell proceeds exact at the real sell position | 78 / 78 | 120 / 120 | 128 / 128 |
| Net P&L, replay vs live (pass mark ~10%) | +0.544 vs +0.517 (+5.3%) | +0.473 vs +0.526 (−10.0%) | +1.411 vs +1.534 (−8.0%) |
| Exit mix, replay vs live (timer / TP / SL) | 61.7 / 14.0 / 2.3 vs 63 / 14 / 1 | 102.2 / 16.7 / 1.0 vs 102 / 17 / 1 | 120.7 / 3.2 / 4.1 vs 122 / 3 / 3 |

- The replay at 0.88 adds no fills and loses none.
- Per fill, the replay minus live has a mean of −0.4 to +0.4 mSOL in r28 and r34, and −1.0 in r35. The spread is 8–24 mSOL, which is the timing noise of a 200 ms exit in a moving market.
- Pooled, the replay is 5.7% below live: +2.428 vs +2.577.
- Every change above is the replay at L minus the replay at 0.88 on the same window and the same exit-timing draw, so this level bias cancels out.
- Without that anchoring, the replay's own totals are:

| Limit | 0.86 | 0.88 | 0.90 | 0.92 | 0.95 |
|---|---|---|---|---|---|
| Replay total (SOL) | +2.402 | +2.428 | +1.819 | +0.877 | −1.088 |

## Method
**Data, all read-only:**
- r28 and r34 records come from the local copies.
- r35 comes from a `sudo grep` of the pre-send events in /root/prod/runs/dip_ams_r35.jsonl on AMS (10-29 02:32).
- The chain tape comes from the local keeper copies of the FRA recorder (collect/run_20261027_1410 and run_20261028_1405, 151 chunks). These were streamed with `zcat | grep` on the 962 armed mints and decoded with presend/real/decode.py (`chunks_of`, `parse_trade`). No raw chunk was copied, and the intermediate TSVs were deleted.
- On those mints during the runs, the tape shows only our pre-send buys and sells from our wallets (no reactive trades).

**Fill rule:**
- For each armed live window, take every landed try in landing order (slot, idx). It carries its signing state (vsol/vtok in `presend_attempt`) and its chain result.
- A try can fill at limit L if it got past the slot guard and the token-account guard on chain (result `ok` or `6042`). Tries that failed with `deadline`, `ata_exists` or `buy_6005`, or were never seen, fail at any limit.
  - Exception at 0.86: `ata_exists` tries after a live fill that no longer happens are eligible.
- It fills if pump's tokens out at the curve state just before it are ≥ `limit_min_out(vsol, vtok, spend, fr = 0.0125 (f32), drop = 1 − L)`. That is the engine's own formula (src/presend_live.rs), so it includes our price impact and the 1.25% fee.
  - In words: it fills when the spot price just before our buy is ≤ L × the price the try was signed at.
- The first try that qualifies fills. Later tries in that window fail.

**Positions and costs:**
- **Pool:** other wallets' token amounts are kept fixed and V×T is kept. Our real live position's tokens are put back while it was held on the tape, and a counterfactual position's tokens are taken out while it is held.
- **One position:** a counterfactual fill pauses all sends until ~0.69 s after it was seen (live median: sell seen +290 ms, sends resume about 400 ms later). Other windows' tries sent in that pause are dropped: 26 / 144 / 181 tries at 0.90 / 0.92 / 0.95 (AMS mostly).
- **Exit:** calibrated per run on its own live 200 ms sells (63 / 102 / 122 sells; chain clock = slot plus tx position within the slot). For each live timer sell k we have D1 (the decision, 10th–90th percentile 204–313 ms after the fill was seen) and dA (the sell landed 223–418 ms after the fill on the chain clock; 1 or 2 slots later, about half each). A counterfactual fill is sold at its own fill + dA_k. TP or SL fires first if another wallet's trade seen before D1 crosses +TP or −20% (the engine's value formula). The P&L is the mean over all k, and the bootstrap draws one k per window.
- **Costs, MEASURED and identical in all three runs:**
  - pump fee 1.25% on both sides;
  - buy 1,718,960 lamports: 5,120 fee + 0.2 mSOL tip + 1,513,840 ATA rent;
  - sell 1,805,001 lamports: 0.605 mSOL fee + 1.2 mSOL tips. The brief said 0.6 + 0.2; the records show 1.805.
  - rent back on close +1,508,820;
  - each landed failed try 5,120.
- **Failed tries:** counted the conservative way the brief asks. Every landed try in a window except the fill counts as failed. Counting only tries sent before the fill was seen changes the totals by ≤ 0.04 SOL.
- **CI:** 4,000 resamples of windows, pooled across runs where pooled.

## Caveats
- **0.86 is a lower bound on fills.** When the live fill fails the tighter limit, the engine would have kept sending, and those tries were never made, so we cannot see them. 62 windows "lose" their fill. Some might fill deeper later.
  - Those 62 fills made +0.235 SOL live (MEASURED, +3.8 mSOL each). The replay values them at only +0.053.
  - On the live numbers, 0.86 is therefore about −0.2 SOL rather than −0.03. Either way, tightening does not pay.
- **Followers are held fixed.** An earlier or extra buy of ours could price out some followers. The "20% fewer followers" column (applied only to the changed fills) makes every looser limit worse still.
- **Pause side effects:**
  - Live pauses that move or disappear in the counterfactual overlap only 3–6 other windows. Their missing tries cannot be seen.
  - Windows ending earlier would also free a little room under the 40/s rate cap. Not modelled; small.
- **Live run snapshot:** r35 is still running. Its table is a snapshot to 02:29 PKT.
- **Sample size:** about 12 hours on two servers. The direction is the same per run for 0.92 and 0.95. For 0.90, r28 alone is within noise (−0.07). r34 (−0.16) and r35 (−0.38) both lean negative, but each run's own CI includes 0.

## Files
Code (scratch, not in the repo): /tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/slip/code/
- runs.py, core.py: records, the engine's limit and pump math, the pool;
- sim.py: the counterfactual windows, exit model and pause;
- analyze.py: runs every limit; writes results.json;
- report.py: the tables.

Tape cache: slip/tape.pkl; per-slot max index: slip/slots/.

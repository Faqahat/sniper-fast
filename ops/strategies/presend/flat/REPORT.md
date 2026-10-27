# Pre-send flat fills: two fixes tested by replay (agent, 10-27 PKT)

Owner request 10-27: can we stop losing money on pre-send **flat** fills? A flat fill is one where nobody else trades between our buy and our 2-slot exit, so we sell into an unchanged price and lose the round-trip fees. Two ideas, tested by replay.

Research only: nothing deployed; no engine, server or config touched. On the servers: one read-only `sudo cat` of r28's records.

MEASURED = engine records, chain recording, or the exact replay at the live exit. INFERRED = a replayed counterfactual. Times are PKT.
(Written by the main session from the agent's text; the harness blocks subagents from writing report files.)

## Short answer (phone)

| | Best variant | Dev (r24–r26) | Validation (r27) | Holdout (r28) | Bar |
|---|---|---|---|---|---|
| **A: hold flats longer** | hold to fill + 3 | −0.052 [−0.229, +0.125] | 0.000 | −0.087 [−0.221, +0.009] | **FAIL** |
| **B: filter** | skip if `since_last ≥ 1` AND `n_tr ≤ 6` | +0.282 [−0.173, +0.742]; r25 −0.193 | −0.145 [−0.591, +0.151] | −0.100 [−0.502, +0.206] | **FAIL** |
| A + B | both | +0.229 | −0.145 | −0.172 | — |

- Numbers are SOL gain over the deployed baseline, with 5–95% bootstrap ranges over windows.
- Neither idea had a variant that passed the pre-registered dev bar. The "best" rows are the best dev totals, tested for information only.

**Idea A fails.**
- All 36 hold variants lose on dev in total, and each one is worse on at least one dev run.
- The best one (sell at fill + 3) gains nothing on r27 and loses 0.087 on r28.
- Pooled over all 5 runs, every variant loses.
- Holding a dead token is a coin flip with a fat left tail: later dumps hit the −20% stop-loss and gap through it, to as low as −39% of size.

**Idea B fails.**
- 0 of 275 configs passed the dev selection, and every config with a positive dev total loses on r25.
- The best dev total (the pair above) removes 30 winners worth +1.24 SOL against 1.28 SOL saved.
- It loses on both validation and holdout.
- Flats cannot be told apart from winners at arm time: the best feature reaches AUC 0.65.

**Recommendation: deploy neither.** Keep the 2-slot exit and QUIET as they are.

**What flats cost (MEASURED).**
- 80 of 578 fills (13.8%) are flat.
- They cost −1.00 SOL over about 20 run-hours, roughly −0.05 SOL/h.
- That is 11–20% of each run's gross losses.
- Each one costs about −3% of size: −0.0104 at 0.34 and −0.0144 at 0.50, including the 0.0015 rent back.

**QUIET and the flat share.**
- Live QUIET runs did not show a lower flat share: 14.3% in r27 + r28, against 13.7% in r24–r26.
- On dev, the QUIET replay lowers it only from 13.7% to 12.1%.

**Size.** At 0.50 SOL the flat share is 17.9%, against 11.0% at 0.34–0.35. This is confounded with time of day.

**Post-hoc lead (not pre-registered, not validated).**
- Rule: send a try only once at least 1 other wallet has traded since the trigger. It is a gate, not a stop: the window stays armed.
- +0.31 SOL over the 5 runs, positive on 4 of 5; removes 16 winners (+0.31) against 42 losers (−0.59).
- It was found after looking at all 5 runs, so it needs a fresh test. r28 after 20:58 PKT has not been looked at by anyone and can serve as that test.

## 0. Pre-registration

The pre-registration is the `prereg.py` docstring, written **2026-10-27 20:55 PKT**, before any variant of this study was run (sha256 21fbc8a4…).

**Roles.**
- Dev = AMS r24 + r25 + r26 (dip19, no QUIET live).
- Validation = AMS r27 (dip20, QUIET live).
- Holdout = AMS r28 (dip21, QUIET live).

**Holdout protection.**
- r28 was fetched only after `FROZEN.json` was written (21:03 PKT).
- The phase-1 chain extraction stopped at 10-27 18:07 PKT, before r28 started at 18:20.
- The phase-2 extraction refuses to run without FROZEN.json.

**Unit and score.**
- Unit: one live window (Idea B), one live position (Idea A).
- Score = realized + rent back − failed-try fees, at the run's live size.
- Tries the engine logged "unseen" are priced from our failed tx on chain.

**Baselines.**
- Primary = what the engine running now (dip21, QUIET on) would keep.
  - Dev: QUIET replayed (arm-skip + 6:2 stop).
  - r27 and r28: as run.
- Secondary = dev as run (reported only).

**Pass bar.**
1. Dev better, and no dev run worse.
2. Validation better.
3. Holdout better.
4. For B only: winners removed ≤ 0.5 × what is saved (losses avoided + fees), pooled.

**Selection.**
- Rule: the best dev total among configs that meet bar 1. For B, bar 4 must also hold on dev.
- No config of either idea met it.
- So for each idea the best dev total was frozen as "informational" (FROZEN.json, `selected_by_prereg: false`).

## 1. Data and checks (MEASURED)

| Run | Engine | Size | Span (PKT) | Windows | Fills | Flats | Pre-send net, primary baseline |
|---|---|---|---|---|---|---|---|
| r24 | dip19 | 0.34 | 10-26 21:47 → 10-27 02:57 | 790 | 200 | 26 | +1.193 (as run +1.168) |
| r25 | dip19 | 0.34 | 02:58 → 06:09 | 371 | 95 | 6 | +1.068 (as run +1.042) |
| r26 | dip19 | 0.50 | 06:58 → 14:03 | 641 | 143 | 28 | +0.738 (as run +0.250) |
| r27 | dip20 QUIET | 0.35 | 15:27 → 17:37 | 177 | 49 | 6 | +0.622 |
| r28 | dip21 QUIET | 0.50 | 18:21 → 20:58 (cut) | 368 | 91 | 14 | +0.104 |

**Records.**
- r24–r27 come from the local copies.
- r28 is a snapshot fetched at 21:04 PKT.
  - It is cut at 20:58, 60 s before the end of the local chain recording copy; 13 windows after the cut were dropped.
  - Every kept fill has its realized and rent-back records.

**Chain.**
- Source: FRA's raw recording, 10-25 21:30 → 10-27 20:59 PKT, 7.45 M pump.fun trades.
- About 1% of slots are empty (leader skips). There is 1 gap longer than 5 slots in r28's span.
- Every trigger, buy and sell of the kept windows was found on chain.
- Our buy tokens and sell SOL on chain equal the records.

**The replay engine is exact on live exits.** Replaying each live time exit (N = 2) on the chain tape gives back the live sell SOL to the lamport on **344 of 344** dev positions.

**The QUIET replay reproduces the earlier work.**
- Dev skips: 60 / 29 / 111, as in the dip20 parity check.
- Nets: +1.193 / +1.068 / +0.738, against the earlier +1.190 / +1.067 / +0.736. The small difference is because I follow the engine's own "others" rule, where FRA's wallet counts as another wallet.
- On r28, the replayed 4 signals equal the engine's logged ones in **368 of 368** windows.

**Delays (MEASURED on dev).**
- TP/SL trigger trade → our sell landing: median 61.6 ms of chain clock (p10–p90 21–152, n = 94).
- Time exits: median 108 ms after the slot start (n = 344). Each position uses its own measured delay.

## 2. Flat fills (MEASURED)

| Run | Size | Fills | Flats | Share (95%) | Flat net | Per flat | % size | Flats' share of run's losses | Flat SOL/h |
|---|---|---|---|---|---|---|---|---|---|
| r24 | 0.34 | 200 | 26 | 13.0% (9.0–18.4) | −0.271 | −0.0104 | −3.06 | 15% | −0.059 |
| r25 | 0.34 | 95 | 6 | 6.3% (2.9–13.1) | −0.063 | −0.0104 | −3.06 | 11% | −0.020 |
| r26 | 0.50 | 143 | 28 | 19.6% (13.9–26.8) | −0.402 | −0.0144 | −2.87 | 17% | −0.057 |
| r27 | 0.35 | 49 | 6 | 12.2% (5.7–24.2) | −0.064 | −0.0107 | −3.04 | 20% | −0.030 |
| r28 | 0.50 | 91 | 14 | 15.4% (9.4–24.2) | −0.201 | −0.0144 | −2.87 | 15% | −0.077 |
| **All** | | **578** | **80** | **13.8% (11.3–16.9)** | **−1.000** | | | | **−0.051** |

**Definition.** A flat fill has no trade by any wallet other than ours on chain strictly between our buy and our sell.

**Cost.** Every flat loses exactly the round trip, about −3% of size: realized −0.0119 at 0.34 and −0.0159 at 0.50, plus 0.0015 rent back.

**QUIET.**

| Group | Flat share (95%) |
|---|---|
| No QUIET (r24–r26) | 13.7% (10.8–17.2) |
| QUIET live (r27, r28) | 14.3% (9.4–21.0) |
| Dev with QUIET replayed | 12.1% (9.2–15.6) |

- On dev, QUIET removes 12 of the 60 flats, along with 28 other fills.
- So QUIET trims flats a little but does not change the share materially.

**Size.**
- At 0.50: 17.9% flats (13.6–23.4), −0.062 SOL/h.
- At 0.34–0.35: 11.0% (8.2–14.8), −0.040 SOL/h.
- Per flat, 0.50 costs 38% more SOL, at a slightly lower % of size (the rent back is fixed).
- The share gap fits "bigger buys scare off or price out followers" (INFERRED). But the 0.50 runs were day and evening, and the 0.34 runs were at night.
- In 21 of 80 flat holds, another wallet's buy failed with a slippage error. That is an upper bound for priced-out followers: most are probably rival pre-senders' tries, and their limits were not decoded.

**Engine view vs chain.**
- All 80 chain-flat fills were also flat in the engine's view at its exit decision, so an exit rule sees every flat.
- 13 non-flat fills also looked flat to the engine: a trade landed before our sell but arrived after the decision.

**The owner's r28 figure.**
- Your figure: 16 flats / −0.254 on r28's first 85 fills.
- I count 14 chain-flat fills there (realized −0.222, net −0.201).
- 16 is the engine-view count. The 2 extra fills had a trade before our sell (ArQtH158 −0.019, HKknYNUv +0.194), so they are not −0.0159 fills.

## 3. Idea A: hold a flat position longer (exit-time)

**When it fires.**
- Only on a position whose time exit (fill + 2) was decided while the engine had seen no other wallet's trade since our buy. This uses the presend_live_tape receive times up to the exit record.
- Every other position is unchanged by construction.

**Replay (INFERRED).** Our live sell is removed. Every later trade keeps its size and chain order and is re-priced with pump's integer math, on the curve with our tokens still in:
- SOL-in buys use the formula measured on their real pre-state.
- Exact-token buys pay the recomputed cost.
- Sells keep their token amount.
- Our sell uses pump's math on the state at its landing.
- Fees, tips and rent are as live.

**Exit timing.**
- A time exit lands at (fill slot + N) × 212 ms plus the position's own live delay.
- TP, SL, big-sell and first-trade exits land 61.6 ms after the trigger trade, and never before the live sell would have.

**How followers are treated.**
- Nobody changes behaviour, and no follower fails.
- This is optimistic for holding. The counterfactual price is higher, so decoded slippage limits could only drop buys; a sell never fails because of us.
- Trades after our counterfactual sell do not affect our P&L and are not modeled.
- Our own later trades on the token inside the extra hold would be blocked. There were none.

**Side cost of holding.**
- While a pre-send position is open (one_position), every window's tries pause and the reactive bot is blocked.
- Inside each extra hold I dropped other windows' live tries, blocked same-token windows, and counted reactive fires.
- Result over all runs and variants: **0 lost fills, 0 blocked windows, 0–2 reactive fires (N ≥ 6)**. Negligible: extra holds are 0.2–1.7 s.

**Dev grid** (primary baseline, SOL gain; 56 positions held, 48 flat + 8 that only looked flat to the engine)

| Variant | r24 | r25 | r26 | Dev |
|---|---|---|---|---|
| A1 hold to +3 | +0.019 | −0.015 | −0.056 | **−0.052** (best) |
| A1 +4 / +5 / +6 | −0.006 / +0.023 / −0.066 | −0.019 / −0.137 / −0.137 | −0.084 / −0.002 / −0.011 | −0.109 / −0.116 / −0.214 |
| A1 +7 … +10 | −0.050 … −0.014 | −0.138 | −0.033 … −0.036 | −0.221 … −0.188 |
| A2: sell K slots after the first other trade (12 configs) | | | | −0.059 to −0.355 |
| A3: + sell at once on another wallet's sell ≥ X SOL (16 configs) | | | | −0.099 to −0.243 |

**The frozen variant, A1(+3).**
- Dev: −0.052 [−0.229, +0.125].
- Validation r27: 0.000. Of 7 positions held, none saw a trade in the extra slot.
- Holdout r28: −0.087 [−0.221, +0.009], with 2 positions better and 3 worse.

**All 36 variants on r27 / r28 (post-freeze, informational).**
- r27: every variant ≥ 0, up to +0.233 (hold to +10, from one late take-profit).
- r28: every variant negative, −0.087 to −0.561.

**Distribution, pooled over the 5 runs** (79 held positions; INFERRED)

| Hold to | Better | Same | Worse | Gains | Losses | Losses < −0.05 SOL | Net |
|---|---|---|---|---|---|---|---|
| +3 | 11 | 54 | 14 | +0.161 | −0.300 | 2 | −0.139 |
| +4 | 14 | 46 | 19 | +0.281 | −0.638 | 4 | −0.357 |
| +6 | 22 | 31 | 26 | +0.406 | −1.028 | 7 | −0.621 |
| +10 | 28 | 22 | 29 | +0.798 | −1.255 | 10 | −0.457 |

**The pattern.** Once the flat 2 slots pass, the token usually wakes up.
- Sometimes buyers come: take-profit gains of +0.04 to +0.09, and one +0.17 at +9/+10.
- More often the dump continues: stop-loss losses of −0.07 to −0.18. The −20% stop gaps to as low as −39% of size.
- Examples:
  - 8cj98gxH at 21:58: a 10.9 SOL dump at +3, −0.116.
  - CQg7MdwX at 20:12: −0.181.
  - GmjuE3EE at 04:14: −0.103.

**Non-flat positions (reverse check).**
- Positions the engine did not see as flat are untouched (0 change, by construction).
- The 11 non-flat positions that looked flat to the engine, kept in the baselines:
  - dev and validation: +0.021 in total (5SsPcWyE +0.019);
  - r28: −0.068 (ArQtH158 caught a dump in the extra slot).

**Secondary baseline (dev as run, 70 positions).** A1(+3) gives −0.059, and all 36 variants are negative.

## 4. Idea B: filter aimed at flat fills (arm-time and try-time)

**B1: try-time stop** (a generalised QUIET stop).
- At the first try sent at slot ≥ trigger + N, count the other trades since the trigger. The count uses what the engine had seen when it signed that try (its pos).
- If there are fewer than M, that try and every later try of the window are not sent.
- Grid: N = 1..5, M = 1..3 (15 configs). On dev, QUIET's 6:2 stop stays in as well.

**B2: arm-time skip.**
- 16 features, two directions, thresholds at the dev deciles: 250 distinct single-feature rules.
- Plus 10 pairs: the AND of the best rules of the 5 best features.
- Features: n_tr_10/50, n_u_10/50, since_last, n_tr, vol_50, fb_n, coh_hold, wh_dump_fol, wh_dumps, vsol, whale_pct, whale_sol, age_slots, quiet_n.
- They use only chain rows before the trigger tx, and whale dumps closed before the trigger slot (last 24 h).

Scores are MEASURED live window results; a rule only removes windows, tries or fills.

**B1 results** (dev gain, primary baseline). Early stops (+1/+2) remove at least as much winner SOL as loser SOL.

| Stop | r24 | r25 | r26 | Dev | Winners removed | Losers removed |
|---|---|---|---|---|---|---|
| +1, <1 | −0.317 | −0.019 | −0.014 | −0.349 | 24 (+0.78) | 33 (−0.39) |
| +2, <1 | −0.060 | +0.013 | −0.002 | −0.048 | 12 (+0.29) | 20 (−0.22) |
| **+2, <2** (best B1) | +0.111 | −0.084 | −0.023 | +0.003 | 29 (+0.57) | 38 (−0.53) |
| +3, <1 | −0.037 | +0.002 | +0.015 | −0.020 | 7 (+0.17) | 11 (−0.13) |
| +4, <1 | −0.027 | +0.001 | +0.015 | −0.011 | 2 (+0.09) | 5 (−0.07) |
| +5, <2 | −0.076 | +0.001 | +0.031 | −0.044 | 2 (+0.08) | 2 (−0.03) |
| the other 9 | | | | −0.015 to −1.263 | | |

Post-freeze on r27 / r28:
- The best B1 (+2, <2) gives −0.249 / −0.005.
- M = 1 stops at +2..+5 are about 0 pooled (−0.05 to +0.01); M = 1 at +1 is −0.55.

**B2 results.** The top dev totals; none qualifies, and each loses on r25.

| Rule | r24 | r25 | r26 | Dev | Winners removed vs saved |
|---|---|---|---|---|---|
| since_last ≥ 1 AND n_tr ≤ 6 (frozen) | +0.141 | −0.193 | +0.334 | +0.282 | 24 (+0.674) vs 0.956 |
| since_last ≥ 1 | +0.039 | −0.289 | +0.395 | +0.145 | 50 (+1.808) vs 1.953 |
| since_last ≥ 12 | +0.149 | −0.148 | +0.136 | +0.138 | 10 (+0.297) vs 0.436 |
| n_tr_10 ≤ 0 | +0.150 | −0.198 | +0.158 | +0.110 | 11 (+0.347) vs 0.458 |

**The frozen B rule on validation and holdout.**
- r27: −0.145; it removes 3 winners (+0.278) against 0.133 saved.
- r28: −0.100; it removes 3 winners (+0.286) against 0.186 saved.
- Bar 4, pooled: 30 winners (+1.238) against 1.276 saved, ratio 0.97 (the limit is 0.5).
- **It fails bars 1, 2, 3 and 4.**
- On dev as run (no QUIET), the same rule shows +0.718. Most of that is what QUIET already removes, which is why the primary baseline matters.

**Why B cannot work with these signals.** Separability over the 578 fills (AUC for flat vs. all other fills; flat vs. winners in brackets):
- Arm-time features are all weak:
  - quiet_n 0.65 (0.69);
  - n_tr_50 0.35, n_u_50 0.34, coh_hold 0.34: flats have somewhat fewer trades and holders;
  - since_last 0.55;
  - wh_dump_fol 0.46;
  - whale_pct 0.49;
  - vsol 0.37.
- Fill timing does not help: flats fill at the same slots as other fills (median +3 after the trigger).
- The only strong signal is at try time: the other trades the engine had seen when it signed the filling try. AUC 0.24, i.e. 0.76 read the other way. 27 of 80 flats had 0 such trades, against 36 of 498 other fills. Section 6 follows this up.

## 5. Combined A + B (frozen, informational)

| | Dev | Val r27 | Holdout r28 |
|---|---|---|---|
| A1(+3) applied after the B pair | +0.229 [−0.260, +0.716] | −0.145 [−0.591, +0.151] | −0.172 [−0.588, +0.160] |

All of the dev gain comes from B. A adds −0.053 on dev and −0.071 on r28.

## 6. Post-hoc lead: a try-time gate (NOT pre-registered; exploratory)

This came from the AUC analysis above, after the holdout test, so it is not validated.

**Rule.**
- A try is sent only when the engine has seen at least M other trades since the trigger (counted at the try's pos).
- The window stays armed, so later tries go out once M is reached.
- A gated fill is charged the remaining tries' fees, assuming no later fill (conservative).

**Results** on top of the primary baseline (`p1_gate.py`):

| Gate | r24 | r25 | r26 | r27 | r28 | Total | Winners removed | Losers removed |
|---|---|---|---|---|---|---|---|---|
| M = 1 | −0.035 | +0.056 | +0.142 | +0.049 | +0.096 | **+0.307** | 16 (+0.31) | 42 (−0.59) |
| M = 2 | −0.008 | +0.065 | +0.445 | +0.079 | −0.152 | +0.428 | 48 (+1.19) | 82 (−1.58) |

- M = 1 removes fills made before any other wallet had traded since the trigger; 24 of the 80 flats are among them.
- M = 1 is the more consistent of the two: positive on 4 of 5 runs, against 3 of 5 for M = 2.
- An earlier filter-study rule was similar but stricter (C1: send only after ≥ 2 other trades). It gave dev +0.088 and validation +0.757, with 27 winners removed on validation.
- **A clean test is available.** Nobody has looked at r28 after 20:58 PKT. Run `p1_gate.py` on it once r28 ends and its recording is copied.
- **Engine change if it holds** (INFERRED): skip a due try while others < 1. dip20's per-trigger "others" counter already exists.

## 7. Configs tried

**Pre-registered (selection used dev only):**
- Idea A: 36.
- Idea B: 275 (15 B1 + 250 singles + 10 pairs). The plan said 298; tied deciles collapsed 38 single thresholds.
- Total: 311.

**After the freeze (informational only):**
- the A grid on r27 / r28 (36);
- the B1 grid on r27 / r28 (15);
- the gate with M = 1 and M = 2 (post-hoc).

## 8. Caveats
- **Idea A is INFERRED.** Followers are assumed to trade the same as live, which is optimistic for holding, so the fail is robust. Failed sells that might pass at the higher counterfactual price are not modeled; that would also hurt holding.
- **Idea B removes MEASURED windows.** A skipped or stopped window cannot free its token for a later trigger in this replay (a second-order effect, not modeled).
- **Small samples.** 80 flats and 79 held positions. Per-run results swing by single dumps (±0.1–0.2 SOL).
- **Short holdout.** The r28 holdout covers only its first 2.6 hours (18:21–20:58 PKT).

## 9. Files

**Code:** `ops/strategies/presend/flat/`
- Pre-registration and freeze: `prereg.py`, `FROZEN.json`.
- Data pipeline:
  - `f1_extract.py`: the chain table.
  - `f2_live.py`: the engine records.
  - `f3_base.py`: windows and flat labels.
  - `f4_features.py`: features and QUIET signals.
  - `h_cut.py`: the r28 cut.
- Shared helpers: `flatlib.py`, `evalcore.py`.
- Idea A: `a_core.py`, `a_measure.py`, `a_eval.py`.
- Idea B: `b_eval.py`.
- Frozen variants with bootstrap: `v_eval.py`.
- MEASURED tables: `m1`–`m5`.
- Post-hoc gate: `p1_gate.py`.

**Data:** `/home/moiz/sniper-data/presend_flat/` (975 MB)
- `chain_p1.npz`, `chain_p2.npz`;
- `base_r24.pkl` … `base_r28.pkl`;
- `a_*.json`, `b_dev.json`, `v_*.json`;
- the r28 snapshot in `r28/`.

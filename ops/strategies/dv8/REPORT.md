# DV8 replayed over every recorded day, at our real landing (agent, 10-28 ~02:00 PKT)

Written by the main session from the agent's text; the harness blocks subagent report writes. Read-only: nothing was sent and no engine or config was touched. FRA r26 was copied once with a read-only `sudo cat`.
- Code: this folder; `run_all.sh` re-runs everything in about 20 min.
- Data and tables: `/home/moiz/sniper-data/dv8/` (2.3 GB). Every table below is a `*.txt` there: c0_coverage, l2, c1–c6, g1–g3, a1.

## Verdict
**DV8 as designed loses on every test day.**
- Calibrated: −12 to −25 SOL a day.
- At our landing before calibration: −2.5 to −16.

The earlier +31.8 / +18.9 came from two replay mechanics that are too optimistic, plus mayhem tokens.

**Best walk-forward version.** Threshold and exit are chosen on the previous day. It ends up very selective: 260–1,350 picks a day.
- Calibrated, current costs: **+0.34 SOL a day** (single days −0.26 to +1.66).
- With haqq's cheap tx recipe: **+1.5** (+0.2 to +3.3).
- 10% fewer followers: negative on 3 of the 4 full test days.
- With ideal landing the same picks make +3 to +19 SOL a day. The edge is still a landing-speed problem.

## 1. Coverage (MEASURED)
- **No recordings exist on the host before 10-22 03:07 PKT.** There is nothing for 10-19 to 10-21.
- Days are 24 h windows ending 23:15 PKT.
- An hour counts as usable when at least 95% of its slots are present and it has at least 50% of a typical hour's trades.

| Day | Usable hours | Use |
|---|---|---|
| D0 10-21 23:15→10-22 23:15 | 17 | Starts 03:07; 18:00–21:00 missing. Training only. |
| D1 →10-23 23:15 | 21 | 18:00–19:59 half missing. Training and validation. |
| D2 →10-24 23:15 | 24 | Test |
| D3 →10-25 23:15 | 23 | Test |
| D4 →10-26 23:15 | 23 | Test |
| D5 →10-27 23:15 | 23 | Test |
| D6 →now | 2 | Partial (to 10-28 01:12), shown only |

The merged tape has 21.9 M pump.fun trades. Eight chunks had been truncated in the earlier decodes (they were decoded while still being copied). They were decoded again from the raw files, and two of them are now complete.

## 2. Our landing model (MEASURED on 1,546 regular fires: AMS r9–r33, FRA r1–r26)

**Landing and fill**
- **Landing rate: 99.9%.** Almost every fire lands a copy on chain.
- **Fill rate: 38.6%.** The other 61% land but fail the +5% guard.
- Our first copy lands in the dump's slot 73% of the time and in the next slot 26%.
- Delay after the dump, p10 / p50 / p90: 23 / 55 / 138 ms.

**Delay by leader client**

| Client | Median delay | Fill |
|---|---|---|
| BAM | 41 ms | 38% |
| Harmonic | 54 ms | 45% |
| Jito | 85 ms | 33% |
| Firedancer | 73 ms | 24% |

**Fill depends almost entirely on how many outside trades land ahead of us** (typically 1 / 3 / 5 at p25 / p50 / p75):

| Trades ahead | 0 | 1 | 2–3 | 4–7 | 8+ |
|---|---|---|---|---|---|
| Fill | 100% | 78% | 29% | 15% | 17% |

On the tape, checking the curve just before our copy against the engine's min_out predicts the live fill or fail on 99.7% of fires.

**Costs per fire (fee and tips of every landed copy)**
- A fill costs 1.75 mSOL to buy and 1.77 mSOL to sell.
- A failed fire costs 0.53 mSOL.
- Since 10-24 23:15 that comes to 4.16 mSOL per fill when failed fires are included.

**Far leaders (INFERRED).** We never fired at far leaders because of the near-only rule.
- In 135k pre-send attempts, far leaders were seen a median 30 ms later than near ones, so the model adds 30 ms for them.
- 64–72% of DV8 picks are at far leaders, but near-only results come out about the same (section 4).

## 3. Calibration against live, and the "+70" contradiction

**Replay mechanics, checked on 595 live fills at our actual entry position** (mSOL per fill, no tx costs):

| Replay | Per fill |
|---|---|
| What we realized (tape) | +5.34 |
| Exact model, timer exit (later sells keep their token amounts) | +5.32 (gap +0.02) |
| Old model (later trades keep their SOL amounts) | +7.47 (gap −2.1) |

The earlier "−2.2 mSOL per fill" calibration was this old-model error, not landing.

**Landing is the main gap** (all 1,544 fires, P&L per fire before tx costs):
- **Live:** +2.2 mSOL per fire.
- **Old model** (landing delay drawn independently of the dump): fill 43%, +7.7 per fire, so 5.5 too optimistic. On a crowded dump it sometimes puts us ahead of the fast bots; live, we are always behind them there.
- **Contention-aware model** (our position drawn from the live distribution of trades ahead, given how many trades hit that dump):
  - fill 40%, +4.9 per fire;
  - still optimistic by 2.7 [1.4 to 4.0];
  - holds when fitted on one server and tested on the other, and across time halves.
- A model using each wallet's speed did no better.

**The gap is multiplicative:**
- Live ≈ 0.61 × modelled − 1.17 mSOL per fire (bootstrap: slope 0.51–0.71, intercept −2.3 to 0.0).
- This is "calibrated" below; "conservative" is the 5% bootstrap quantile.
- On our actual fires per day (c6; curve P&L, tx costs excluded):

| Day | Live | Calibrated replay |
|---|---|---|
| D2 | +1.18 | +0.96 |
| D3 | +0.03 | +0.18 |
| D4 | +2.18 | +1.68 |
| D5 | +0.04 | +0.58 |

**"Buy every dump = +70" was mayhem tokens:**
- On the old test day, the 3-position replay's fills on mayhem tokens made +203 SOL gross (one +29.6 SOL on a 0.40 SOL buy). Normal tokens made −101.
- 100 of the top 101 fills were mayhem.
- Mayhem reserves are not a normal bonding curve, so the old model invents profit: +55 mSOL per fill, against −19 with the exact model.
- With mayhem excluded, buying every dump loses 113 to 1,090 SOL a day under every model.

**The earlier DV8 +31.8 reproduces exactly:**
- Mayhem picks (785 of 8,065) carried +12.6 of it.
- None of our live fires were on mayhem tokens.
- DV8 now excludes mayhem.

## 4. DV8 walk-forward per day
- **Method:** train the gate on days before D−1, choose exit and threshold on D−1, test on D.
- **Setup:** 3 positions, all leaders, +5% guard, 0.40 SOL. SOL per day window.
- **Cost levels:** NOW = current tx costs; CHEAP = haqq's tx recipe.

| Day | Exit (slots) | Picks | Fires | Fills | Wins | Ideal NOW | Ours NOW | Calibrated NOW [5–95%] | Calibrated CHEAP | −10% followers NOW / CHEAP |
|---|---|---|---|---|---|---|---|---|---|---|
| D2 | 5 | 263 | 200 | 128 | 49 | +3.42 | +0.37 | −0.20 [−0.45..+0.01] | +0.20 | −0.60 / −0.19 |
| D3 | 12 | 1,347 | 898 | 545 | 242 | +19.10 | +2.66 | −0.25 [−1.34..+0.77] | +1.48 | −3.79 / −2.06 |
| D4 | 5 | 987 | 757 | 491 | 236 | +15.75 | +5.27 | +1.59 [+0.61..+2.67] | +3.12 | −0.55 / +0.99 |
| D5 | 12 | 712 | 485 | 295 | 128 | +13.19 | +1.91 | +0.15 [−0.44..+0.74] | +1.08 | −2.08 / −1.15 |
| D6 (2 h) | 5 | 32 | 28 | 15 | 8 | +1.76 | +0.27 | +0.11 | +0.16 | +0.02 / +0.07 |

- The 5% and 20% stress rows are in `g1.txt`. At 20% fewer followers, every full day is negative at both cost levels.

**Variants at the frozen threshold** (calibrated, NOW costs):
- **1 vs 3 positions:** about the same, because picks rarely overlap.
- **Near-only:** D2 −0.05, D3 +0.70, D4 +0.95, D5 +0.73.
- **5 vs 8 vs 12-slot exit:** the ranking changes from day to day; validation picked 5 twice and 12 twice.

**DV8 as designed** (~8,000 picks/day, 8-slot exit, 3 positions; g3):

| Day | Calibrated NOW | Old replay method, same picks |
|---|---|---|
| D2 | −17.5 | +42 |
| D3 | −12.3 | +65 |
| D4 | −25.5 | +43 |
| D5 | −17.0 | +69 |

## 5. What we actually made, and haqq (a1)

| Day | Ours (MEASURED, regular + pre-send, all costs) | haqq P&L before tx costs | haqq net (−0.78 mSOL/lot, INFERRED) |
|---|---|---|---|
| D2 | +0.55 | +48.0 | +42.4 |
| D3 | −0.17 | +28.1 | +24.4 |
| D4 | +1.28 | +40.7 | +35.6 |
| D5 | +3.18 (AMS pre-send +3.69) | +32.7 | +28.2 |

## 6. Paper test and the engine work it needs
**Recommendation: do not run DV8 live.** If you paper-test it at all, use the selective version:
- top 1–2% of the gate score (about 300–1,300 picks a day);
- 5-slot exit;
- one position is enough, and near-only is fine;
- mayhem excluded;
- judged at haqq's cheap costs.

**Engine work for a paper (shadow) mode:**
1. Compute the gate's 28 features in the dump path and load the gate model.
2. Skip mayhem tokens at create.
3. Log every pick: the dump's sig, slot and index, the score, the leader and its client, and the curve state.
4. **Probe mode (needs owner OK):** send a buy that is designed to fail the guard, to measure where we really land on these picks (~0.5 mSOL per pick).
5. A flag to lift the near-only rule.
6. More than one open position, with a lock per token.
7. haqq's cheap tx recipe (send path, needs owner OK). It is worth about +1.2 SOL a day on these picks.

## Measured vs inferred
- **Measured:** coverage; live fires, landing rate, fill, positions and costs; the guard check; the calibration fits; our per-day P&L; haqq's trade flows.
- **Inferred:** the far-leader landing delay; haqq's tx cost; every replay P&L, which is a forecast.

## Not resolved
- "Buy every dump" run the old way on the rebuilt tape for 10-27 comes out about −6, not +70. The old tape still contained our own live buys; how much of the difference that explains was not checked.
- The landing model was fitted on all live fires, which overlap the test days in time. It describes the engine as it is today.

## Main-session verification (10-28 ~02:15 PKT)
- **Re-run:** `run_all.sh` re-run end to end. All 12 tables come out identical; the only differences are run-time stamps (g1, c3).
- **Coverage:** the earliest host recording is `collect/run_20261021_2207` (UTC) = 10-22 03:07 PKT. There is no data for 10-19 to 10-21.
- **Landing model:** checked on a separate data path (haqq_strat h2h, 355 regular fires, 10-26 23:15 → 10-27 23:15).

  | | Separate check | Agent's model |
  |---|---|---|
  | ms after the dump, p10 / p50 / p90 | 22 / 49 / 130 | 23 / 55 / 138 |
  | Same slot as the dump | 78% | 73% |
  | Fill | 36% | 38.6% |

  Fill by wallets ahead in the separate check:

  | Wallets ahead | 0 | 1 | 2–3 | 4–7 | 8+ |
  |---|---|---|---|---|---|
  | Fill | 100% | 63% | 22% | 6% | 6% |

  These are no better than the model's, so the model is not too pessimistic.
- **Walk-forward split (g1_walkforward.py):** train on days < D−1, choose the exit and threshold on D−1 only, then test on D. The landing calibration was fitted on live fires that overlap the test days (noted in "Not resolved").
- **Mayhem:** consistent with the earlier finding that mayhem vsol is fake (strat-nonrace-search, devexit memory).

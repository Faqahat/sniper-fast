# QUIET in AMS run 28: did it cost us gains? (realistic replay; agent, 10-27 PKT)

Owner request 10-27: did QUIET cost us gains in AMS run 28? Realistic replay of what QUIET's skipped triggers and stopped pre-send windows would have made. Read-only: nothing was sent, and no engine, server or config was touched. MEASURED = engine records or the chain recording. INFERRED = replay or my reading. Times are PKT.

**Sign rule:** QUIET effect = live − the same run without QUIET. Plus means QUIET helped (saved money); minus means it cost us.

The method is run 27's (`live27/`, REPORT27.md), re-run on run 28's final records and a chain tape covering the whole run. The harness blocked the agent from writing this file; the main session saved it from the agent's text.

## Short answer (phone)
**No. QUIET did not cost us gains in run 28. The replay says it saved about +0.29 SOL**, and every variant agrees. Without QUIET, run 28's pre-send would have netted about **−0.01 SOL instead of the live +0.273** (INFERRED).

| QUIET effect, SOL (INFERRED) | Mean | 90% range (bootstrap over windows) | Draws > 0 |
|---|---|---|---|
| Skip rule (119 triggers skipped) | **+0.165** | −0.001 to +0.355 | 95% |
| Stop rule (97 windows stopped at slot +6) | **+0.037** | −0.050 to +0.122 | 78% |
| Overlap (the skipped windows would also have been stopped) | +0.083 | | |
| **QUIET total** | **+0.285** | **+0.072 to +0.530** | **98%** |
| Calibrated: wins × 0.81, losses × 1.05 | +0.300 | +0.099 to +0.534 | 99% |
| Run 28's own landing (instead of probe 3's) | +0.288 | +0.036 to +0.542 | 96% |
| +15 ms landing / 20% fewer later buyers | +0.284 / +0.294 | +0.054 to +0.549 / +0.097 to +0.525 | 97% / 99% |

| Hour (PKT) | Live pre-send net (MEASURED) | Skipped / stopped | **QUIET effect** | 90% range | Draws > 0 |
|---|---|---|---|---|---|
| 18–19 (from 18:20) | +0.359 | 11 / 14 | +0.025 | −0.012 to +0.066 | 85% |
| 19–20 | +0.081 | 13 / 17 | −0.004 (median draw +0.009) | −0.000 to +0.017 | 94% |
| 20–21 | **−0.327** | 49 / 22 | **+0.122** | +0.034 to +0.222 | 99% |
| 21–22:03 | +0.160 | 46 / 44 | **+0.142** | −0.018 to +0.350 | 92% |

- 19–20 is the only negative hour. One skipped token (S14, below) wins +0.26 in 4% of draws, which pulls the mean below the range.
- The savings came in the weak hour 20–21, when live lost −0.327 and QUIET skipped 49 triggers, and in 21–22.

**Calibration.** The replay is optimistic on this run, the opposite of run 27.
- Fills: 148.8 vs 150 live. Fill yes/no agreement: 87.5%.
- Net: replay +0.968 vs live +0.273. Live sits at the replay's 3rd percentile.
- Winners: replay +3.081 vs live +2.480, so f_win = 0.81.
- Losers: replay −2.033 vs live −2.130, so f_loss = 1.05.
- Most of the gap is phantom fills on fast-bouncing dumps: windows live never filled, which the replay fills in 8% of draws at a profit.
- Both corrections make QUIET look better, because the skipped windows are mostly losers. The calibrated total is +0.300.

**Verdict (INFERRED):** QUIET helped, by about **+0.29 SOL**, roughly as much as the run's whole pre-send net.
- The sign holds in 96–99% of bootstrap draws under every landing model and calibration.
- Quiet tokens got almost no buyers after the dump. The 119 skipped triggers, had they been armed, fill about 16 times with only 16% winners: −0.186 SOL. That is the flat round-trip cost (−0.0144 per fill at 0.50 SOL) again and again.
- Confidence: high on the sign, medium on the size (bootstrap +0.07 to +0.53).

**Top misses** (QUIET cost us):

| Window | PKT | Mint | QUIET effect | Why |
|---|---|---|---|---|
| w547 (stopped) | 21:45:01 | 34SxPM4f | −0.024 | Fills after the stop in 53% of draws, +0.045 per fill. The whale dumped 3.0 SOL at +7, then 3 buyers (1.8 SOL). |
| S14 (skipped) | 19:19:37 | 2Lq3DmdP | −0.012 | +0.001 in most draws, but +0.26 in 4% (the timer sell lands after 9 SOL of buys). |
| S43 (skipped) | 20:20:39 | 3xQjyeAU | −0.011 | +0.013 per fill. |

- Only w547 would have won more than +0.03 per fill. w572 did win, live, before its stop.
- No skipped trigger has a mean above +0.03.
- The CQg7MdwX twin (S35/S36 skipped, w253 live) nets −0.0006 for the token: a wash.

**Top saves** (each is a flat or losing dump with no buyers):

| Window | PKT | Mint | QUIET effect |
|---|---|---|---|
| S96 | 21:35:34 | G3S3hDmn | +0.021 (10.1 SOL dump, −45%) |
| w553 (stopped) | 21:47:42 | FvZoyHPV | +0.018 |
| S113 | 21:57:45 | 9VpoZVof | +0.016 |
| S57 | 20:30:22 | CDZcNX94 | +0.015 |
| S50 | 20:26:41 | F8NukDST | +0.014 (10.5 SOL dump, −50%) |
| S60 | 20:35:45 | 7EN4RYcP | +0.014 |
| S9 | 18:51:28 | 7CYEkFkb | +0.013 |
| S65 | 20:51:57 | HmCubckY | +0.013 |

## 1. Data and method
- **Live (MEASURED):** the final snapshot of `/root/prod/runs/dip_ams_r28.jsonl` and `.log`, taken after the run ended (18:20:27 → 22:03:02).
  - md5 `e7cacd3d96d3e08491a28d64cf199c02` and `a4194912eccf4e5ed1b5738032bc81f5`, equal to the server's.
  - 609 armed windows, 150 fills, 70 wins (realized + rent back > 0).
  - Pre-send net **+0.2726 SOL**: realized +0.124, rent back +0.226, failed-try fees −0.078 (engine-logged; 0.0797 on chain), computed as `eval_live.py` does.
  - The wallet's +0.313 = pre-send +0.273 + regular +0.04.
  - QUIET: 119 skips (rule on from the first trigger, no warm-up) and 97 stops, all at slot +6.
    - One stopped window, **w572** (4hynaATo, 21:52:53), had already filled at slot +6 from a try sent before the stop (+0.0357 MEASURED).
    - So 96 stops ended a window with no fill. The replay lets w572's earlier tries fill, and it counts in the stopped group.
- **Chain tape (MEASURED):** FRA's recording, decoded with the unchanged `real/decode.py` and `real/build.py`.
  - Chunks: `run_20261026_1415` (16 chunks, 18:17 → 19:37) and `run_20261027_1410` (35 chunks, 19:10 → 22:05:23; the overlap is deduplicated).
  - 51 chunks, none truncated: 781,902 pump trades. Block times run 18:16:46 → 22:05:12. The last chunks were checked with `gzip -t` after the keeper's 22:10 copy.
  - Coverage: 561 of the run's 62,665 slots have no block. Of the 28,157 slot references in the engine's records, 3 fall in them: 462098145-6 and 462098631, the **19:06 recording hole** found in the mid-run pass. They touch w94 and w98; the calibration without them is unchanged.
  - Our 150 fills and sells were removed from the tape (the replay puts its own buy in).
- **Model:** the LAST_HOUR realistic replay, `real/sim.py` imported unchanged.
  - Landing: the probe-3 donor transplant (P3).
  - Variants: run 28's own 609 windows as donors (R28, leave one out), +15 ms lag, and 20% fewer later buyers.
  - Run 28's settings come from its run_start: 0.50 SOL, k 4, helius-ps 20/s, limit × 0.88, deadline +1, 10 slots, exit 2 slots / TP 10% / SL 20%, one position, 5,120 per failed try.
  - Pace slot 212.6 ms, MEASURED on its tries.
  - Run 28's landing matches P3's (MEASURED): 39% / 52% / 5% / 4% land in the send slot / +1 / +2 / later, against 39% / 54% / 4% / 2%. Median chain-clock delay 117 vs 114 ms.
- **The `sim28.py` additions are identical to run 27's:** common random numbers, the live stop at its live time, no fill before the stop for stopped windows (except w572), the modeled stop for windows not armed live, and the dynamic arm checks.
  - The modeled stop decides at the start of slot +6 plus a delay drawn from the 97 live stops (median +37 ms; 5–95% −70 to +323 ms). It stops if fewer than 2 other trades were seen.
  - **Checked on run 28's 383 decided windows: 381 agree with live (99.5%):** 96/97 stops and 285/286 non-stops. The others count is exact in 86%.
- **Streams** (400 draws each): `cal`, `A0` (as live), `B` (no QUIET), `C` (skip rule off), `D` (stop rule off), `iso`.
  - Effects: skip = A0 − C, stop = A0 − D, total = A0 − B, in the QUIET-effect sign.
  - A live window that a counterfactual blocks loses its MEASURED live net.
- **Ranges:** model draws with the windows fixed, and a stratified bootstrap over windows (10,000 resamples). The 119 skipped, 97 stopped and 512 others are each resampled within their group.

## 2. Calibration on run 28's 609 live windows (task 1)

| Group | Fills live / replay | Wins live / replay | Realized + rent, live / replay | Fees live / replay | **Net live / replay [5–95%]** | Live pct |
|---|---|---|---|---|---|---|
| All 609 | 150 / 148.8 | 70 / 72.5 | +0.351 / +1.048 | 0.0779 / 0.0795 | **+0.273 / +0.968 [+0.380, +1.544]** | **3rd** |
| 18–19 (79) | 22 / 20.7 | 13 / 11.1 | +0.368 / +0.280 | 0.0088 / 0.0088 | +0.359 / +0.271 | 84th |
| 19–20 (121) | 32 / 32.1 | 14 / 15.7 | +0.097 / +0.297 | 0.0157 / 0.0158 | +0.081 / +0.281 | 13th |
| 20–21 (171) | 38 / 42.3 | 15 / 19.2 | −0.304 / −0.046 | 0.0224 / 0.0223 | −0.327 / −0.068 | 8th |
| 21–22 (238) | 58 / 53.8 | 28 / 26.6 | +0.191 / +0.517 | 0.0309 / 0.0326 | +0.160 / +0.484 | 10th |
| Stopped by QUIET (97), before the stop | 1 / 1.0 | 1 / 1.0 | +0.036 / +0.032 | 0.0105 / 0.0105 | +0.025 / +0.021 | 55th |
| Without the top live winner (w162, +0.195) | 149 / 147.9 | 69 / 71.6 | +0.155 / +0.867 | | +0.078 / +0.788 | 2nd |
| Without w94 and w98 (19:06 hole) | 148 / 147.0 | 68 / 70.8 | +0.333 / +1.001 | | +0.255 / +0.921 | 3rd |

**Winners and losers, separately** (all 609 windows):

| | Live | Replay | Factor live / replay |
|---|---|---|---|
| Winners | 70, +2.480 | 72.5, +3.081 | **f_win 0.81** (0.79 without w162) |
| Losers | 80, −2.130 | 76.2, −2.033 | **f_loss 1.05** |

By hour, f_win is 1.16 / 0.78 / 0.56 / 0.83 and f_loss is 0.89 / 1.09 / 0.94 / 1.17.

**Fills yes/no:**
- Agreement 87.5% (Brier 0.070; base rate 0.25).
- The replay fills live-filled windows in 74% of draws, and live-unfilled windows in 8%.
- Those 8% are worth **+0.0014 per window, +0.64 SOL over 459 windows**. This is most of the +0.70 gap.

**P&L at the same fill slot** (`samefill28.py`; 146 of 150 live fills have draws filled in the live fill slot):
- Live +0.0024 per fill against replay +0.0035 (correlation 0.94, same sign 94%).
- Winners: +2.454 live vs +2.307 replay. Losers: −2.109 live vs −1.800 replay.
- So the exit model is right on winners and 15% too mild on losers. The rest of the gap is *which* windows fill.

**Why the replay fills windows live did not (example, MEASURED):** w147 5JJjzSrG, 19:32:17.
- The dump came at +3, idx 79 (4.6 SOL, −19%).
- Live, our tries from slot +2 all landed at +3 idx 408–439, after a 1.2 SOL bounce buy at idx 242, so they failed 6042.
- The replay lands most draws before idx 242 and fills (+0.125). Its slot-level landing matches; its position within the slot on bouncing dumps does not. This is the known "we land later on bouncing dumps" bias (vm1-verify).

**Near-quiet windows check** (live windows by how many of QUIET's 4 signals held at arm; the 119 skips had all 4):

| Signals held | Windows | Fills live / replay | Net live / replay [5–95%] | Live pct |
|---|---|---|---|---|
| 0 | 93 | 27 / 25.5 | +0.207 / +0.392 [+0.108, +0.674] | 13th |
| 1 | 148 | 42 / 40.3 | +0.191 / +0.239 [−0.062, +0.533] | 40th |
| 2 | 215 | 55 / 54.5 | −0.102 / +0.226 [−0.081, +0.544] | 4th |
| 3 | 153 | 26 / 28.4 | −0.024 / +0.112 [−0.155, +0.407] | 22nd |

- Live net per window is positive with 0–1 signals and about zero or negative with 2–3.
- On the near-quiet windows (3 of 4), the replay is too optimistic, by +0.14 on 153 windows.
- So the replay is not pessimistic on near-quiet windows. If anything it flatters them, so it is unlikely to overstate QUIET's saving.

**Calibration verdict:** the model is off by more than 30% on the total (live at the 3rd percentile). The error is phantom winners plus mild losers.
- Calibration factor (INFERRED): winning fills × 0.81 (0.79 without w162) and losing fills × 1.05.
- On QUIET it moves the total from +0.285 to +0.300.
- Sensitivity: the "20% fewer later buyers" variant overshoots the other way (live at its 86th percentile). The truth is between it and the main model, and both give the same QUIET total (+0.294 vs +0.285).

## 3. The 119 skipped triggers, replayed as if armed (task 2)

| Case (INFERRED) | Fills | Wins | Realized | Failed-try fees | **Net** |
|---|---|---|---|---|---|
| Armed, stop rule on (= skip rule off) | 15.9 | 2.6 | −0.171 | 0.0155 | **−0.186** (draws −0.247 to −0.131) |
| Armed, no stop rule | 18.5 | 2.6 | −0.260 | 0.0221 | −0.282 |
| Armed, stop on, calibrated (wins × 0.81) | 15.9 | 2.6 | −0.176 | 0.0155 | −0.192 |
| Each window alone (stop on / no stop) | 16.8 / 19.4 | | | | −0.200 / −0.296 |

- **The fills are bad fills:** 16% winners, mean −0.0107 per fill, median −0.0144 (the flat round trip at 0.50 SOL). Live armed fills: 47% winners, +0.0023 per fill.
- 97 of the 119 never fill (no 12% drop in the window, or the bounce came first). They cost fees only: −0.013 in all.
- 18 fill in at least half of the draws: −0.167 in all. Only 2 of them have a positive mean (S14, S43).
- **Knock-on, exact by token** (skip rule = −0.165 given up):
  - Skipped windows' own P&L: −0.186.
  - Live windows on the same tokens: +0.038. These are the twins: arming the skipped trigger would have blocked the live window that armed instead.
  - Other live windows: −0.017. The extra positions and rate use crowd out other fills.
- **Twins:** 19 tokens have both a QUIET skip and a live window. Together they net +0.012 for QUIET, about zero, unlike run 27's +0.026.
  - Biggest: S9/w61 7CYEkFkb +0.013, S66–68/w364 FJjsuXcV +0.012, S14/w116 2Lq3DmdP −0.012.
  - CQg7MdwX (S35/S36, live w253): −0.0006, a wash.
- Per hour, the skip rule's effect is +0.013 / −0.010 / **+0.090** / +0.072 (18–19 / 19–20 / 20–21 / 21–22).

## 4. The 97 stopped windows, after the stop (task 3)

| Case (INFERRED) | Fills | Wins | Realized | Failed-try fees | Net |
|---|---|---|---|---|---|
| Stopped as live (live: 1 fill (w572), fees 0.0105, net +0.0252) | 0.8 | 0.8 | +0.030 | 0.0105 | +0.019 |
| Run to the window end | 5.7 | 2.1 | +0.021 | 0.0196 | +0.001 |

- **Stopping saved +0.018** (draws −0.030 to +0.071): about 4.9 more fills after the stop, net −0.009, plus 0.0091 more fees from 1,792 more tries.
- Knock-on on other windows: +0.019, mostly the one-position pause. 5 same-token triggers would also have been blocked, each worth about 0 live.
- **Stop rule total: +0.037** (bootstrap −0.050 to +0.122; 78% > 0).
- Per hour: +0.011 / +0.006 / +0.009 / +0.011.
- The stop's one real cost: **w547** 34SxPM4f (21:45:01), −0.024.
- The overlap (+0.083) is the stop rule acting on the skipped windows. Without the stop rule they lose −0.282 instead of −0.186.

## 5. Net QUIET effect on run 28 (task 4; live − no-QUIET counterfactual; + = QUIET helped)

| | Effect (model) | Draws 5–95% | Bootstrap 5–95% | Bootstrap > 0 | Wins × 0.81 | × 0.81, losses × 1.05 |
|---|---|---|---|---|---|---|
| Skip rule | +0.165 | +0.045 to +0.313 | −0.001 to +0.355 | 95% | +0.164 | +0.173 |
| Stop rule | +0.037 | −0.021 to +0.107 | −0.050 to +0.122 | 78% | +0.039 | +0.040 |
| Overlap | +0.083 | | | | +0.083 | +0.087 |
| **QUIET total** | **+0.285** | **+0.135 to +0.455** | **+0.072 to +0.530** | **98%** | **+0.286** | **+0.300** |
| 18–19 | +0.025 | +0.009 to +0.037 | −0.012 to +0.066 | 85% | +0.025 | +0.027 |
| 19–20 | −0.004 | +0.003 to +0.011 | −0.000 to +0.017 | 94% | −0.002 | −0.002 |
| 20–21 | +0.122 | +0.073 to +0.162 | +0.034 to +0.222 | 99% | +0.126 | +0.133 |
| 21–22 | +0.142 | +0.020 to +0.299 | −0.018 to +0.350 | 92% | +0.137 | +0.143 |

**Sensitivity (QUIET total; calibration = replay net vs live +0.273):**

| Variant | Replay net, live pct | QUIET total (model / calibrated) | Bootstrap 5–95% |
|---|---|---|---|
| P3 landing (main) | +0.968, 3rd | +0.285 / +0.300 | +0.072 to +0.530 |
| Run-28 landing (leave one out) | +1.057, 1st | +0.288 / +0.309 | +0.036 to +0.542 |
| P3, +15 ms landing | +0.910, 3rd | +0.284 / +0.282 | +0.054 to +0.549 |
| P3, 20% fewer later buyers | −0.137, 86th | +0.294 / +0.262 | +0.097 to +0.525 |

The key windows hold across all four variants:
- S96 +0.021 to +0.023.
- w553 +0.017 to +0.018.
- w547 −0.017 to −0.031.
- S14 −0.008 to −0.016.

## 6. Top misses and saves (task 5; per window, INFERRED; tape MEASURED)

| Window | PKT | Mint | Fill p / P&L per fill | QUIET effect | Tape |
|---|---|---|---|---|---|
| **Miss: w547 (stopped at +6)** | 21:45:01 | 34SxPM4fjDyxVWTyH3gRY3y9J63ENSwcZDkCtjdPoxuV | 53% after the stop / **+0.045** | **−0.024** | The whale (9qz7cWBq) sold 3.0 SOL at +7 (−17%). Then 3 buyers (1.8 SOL), +12% off the low. |
| Miss: S14 (skipped) | 19:19:37 | 2Lq3DmdPZ62xbL65ZSRtCsjv5nNM8mF4oprh3QV5pump | 86% / +0.014 | −0.012 | A follower sold 2.8 SOL at +3 (−14%). Our 2-slot sell lands at +5 (+0.001) in most draws; when it lands at +6, after 9.1 SOL of buys, it is +0.26 (4% of draws). |
| Miss: S43 (skipped) | 20:20:39 | 3xQjyeAUmLxTrA2wPtfqr1rViLknn62TypV415FPpump | 86% / +0.013 | −0.011 | The whale and one other sold 3.5 SOL at +5 (−17%). One 1.0 SOL buyer. |
| No miss: w572 (stopped) | 21:52:53 | 4hynaAToL6cF8DCbikwf21iprkaTij2UFrfhq2DXpump | filled before the stop | −0.003 | Won +0.036 live (MEASURED). The stop changed nothing. |
| Tail only: S98 (skipped) | 21:37:09 | 9JURJUiShwJraeDiRMkxy5ADMnZJa1wccDD9M3X4pump | 0% (P3), 4% (R28) / +0.26 | 0 to −0.010 | A 13.6 SOL dump at +5 (−48%), then 12.1 SOL of buyers in 2 slots. Too fast for our landing in almost every draw. |
| **Save: S96 (skipped)** | 21:35:34 | G3S3hDmnHKVxPRbbpYqt8rH8Fh6WQdn26XrgTYMepump | 85% / −0.025 | **+0.021** | 3 sellers including the whale, 10.1 SOL at +5 (−45%). No buyer. |
| Save: w553 (stopped) | 21:47:42 | FvZoyHPVQrQUEkUXYR2a83QmfzoyDqJxNR2aZxLwpump | 93% after the stop / −0.019 | +0.018 | 2 sellers, 5.0 SOL at +8 (−25%). One 0.7 SOL buyer. |
| Save: S113 (skipped) | 21:57:45 | 9VpoZVof7muEWqTALWSMoSDFCHJYoTh7ahopncampump | 91% / −0.018 | +0.016 | 3 sellers including the whale, 4.6 SOL at +9 (−24%). No buyer. |
| Save: S57 (skipped) | 20:30:22 | CDZcNX94eqTwYyWkLzWgJirLvC84YYuWG5Chs7mzpump | 92% / −0.016 | +0.015 | 2.9 SOL at +6 (−15%). No buyer. |
| Save: S50 (skipped) | 20:26:41 | F8NukDSTmNwMVhXidQFJ34dzSNxHmEDEcDgEPCxCpump | 80% / −0.017 | +0.014 | 4 sellers including the whale, 10.5 SOL at +4 (−50%). No buyer. |
| Save: S60, S9, S65, S88, S47, S67/w364 (same dump, counted once in the total), S53 | 18:51–21:22 | | 73–94% / −0.014 to −0.016 | +0.011 to +0.014 each | One or more sells of 2.8–8.3 SOL. No buyer within 2 slots: the flat round trip, −0.0144. |

- The other 197 skipped or stopped windows are within ±0.005 each, +0.025 in all.
- Windows that would have **won > +0.03 per fill**: only w547 (and w572, which did win, live).
- With a tail chance: S14 (4–6% of draws) and S98 (0–4%), each about +0.26 when it happens.

## 7. Caveats
- **The model is optimistic on run 28** (live at its 3rd percentile; in run 27 it was pessimistic, at the 96th).
  - Its biases (phantom winners on bouncing dumps, mild losers) push the skipped and stopped windows *up*. So the QUIET saving here is unlikely to be overstated.
  - Near-quiet live windows (3 of 4 signals) confirm it: live −0.024 vs replay +0.112.
- **Concentrated in time:** 93% of the saving is 20:00–22:03 (+0.264 of +0.285). 18–20 is about +0.02.
  - The bootstrap still puts 98% of draws above zero.
  - It comes from many small flat losses (about 13 windows at +0.011 to +0.021 each), not from 1–2 tokens.
- **Run 27 vs run 28:** run 27 gave +0.034 (−0.09 to +0.15), with no clear sign. Run 28 gives +0.285 (+0.07 to +0.53), a clear plus.
  - Run 28 was larger: 0.50 SOL vs 0.35, 3h40 vs 2h20, 119 skips vs 36.
  - It also had a weak hour (20–21, live −0.327), which is where QUIET pays.
- **Not modeled:**
  - Double fills.
  - The regular M2 bot sharing the one position (61 tries paused for it live). The ~15 extra pre-send fills of the no-QUIET run could have blocked an M2 trade or two.
  - Competitors reacting to us.
- **w572 handling:** the only stopped window that filled before its stop. Its pre-stop tries are left free to fill in every stream; the effect is −0.003.
- **The 19:06 recording hole** (3 slots) touches w94 and w98 only. The calibration without them is unchanged.
- **The bootstrap** treats windows as exchangeable within each group and does not include model error. Model error on the run total is +0.70 here, mostly phantom winners; on the QUIET windows it works in QUIET's favour, as above.

## 8. Files
- **Code** (`/home/moiz/sniper/ops/strategies/presend/filter/live28/`): run 27's scripts adapted.
  - `lib28.py`: the final snapshot, no cut (`LIVE28_CUT` only for trial runs), hour blocks.
  - `prep28.py`: donors and the coverage check, new.
  - `qcheck28.py`, `setup28.py`, `sim28.py` and `replay28.py`: w572 handling added.
  - `calib28.py`: the winners/losers split added.
  - `effects28.py`: f_loss and the per-hour skip/stop rows added.
  - `tables28.py`.
  - `top28.py`: per-window misses and saves, with twins counted per token, new.
  - `samefill28.py`: P&L at the live fill slot and the tails, new.
- **Data** (`/home/moiz/sniper-data/presend_filter/live28/`):
  - `dip_ams_r28.{jsonl,log}`: final, md5 as above.
  - `dec/` and `tab/`: the tape.
  - `donors28.pkl`, `qcheck.json` and `coverage.json`.
  - `replay28_{P3,R28}_main.pkl` and `replay28_P3_{lag15,cut20}.pkl`.
  - `calib28_*.txt`, `effects28_*.{txt,json}`, `tables28_P3_main.txt`, `top28_*.{txt,json}`, `samefill28_*.txt`, `qcheck28.txt` and `prep28.txt`.
  - The superseded mid-run (21:23 cut) pass is in `mid2123/`.
- **Re-run** (about 10 min):
  ```
  cd /home/moiz/sniper/ops/strategies/presend/filter/live28
  python3 prep28.py && python3 qcheck28.py
  python3 replay28.py --pool P3 --draws 400 && python3 replay28.py --pool R28 --draws 400
  python3 replay28.py --pool P3 --lag 15 --tag lag15 && python3 replay28.py --pool P3 --cut 0.2 --tag cut20
  python3 calib28.py P3 main; python3 effects28.py P3 main; python3 tables28.py P3 main; python3 top28.py P3 main; python3 samefill28.py P3 main
  ```

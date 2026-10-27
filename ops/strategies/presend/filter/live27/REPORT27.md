# QUIET in AMS run 27: what it gave up or saved (realistic replay; agent, 10-27 PKT)

Owner request 10-27: estimate what QUIET gave up or saved in AMS run 27 (dip20, the first live run with QUIET), with a
realistic replay on the chain recording. Read-only: nothing was sent, and no engine, server or config was touched.
MEASURED = engine records or the chain recording. INFERRED = replay or my reading. Times are PKT.
Sign rule: **QUIET effect = live − the same run without QUIET.** Plus means QUIET helped.
"Given up" (sections 3–4) is the opposite sign: the counterfactual minus live, so minus means QUIET saved.
(Written by the main session from the agent's text; the harness blocks subagents from writing report files.)

## Short answer (phone)
| QUIET effect, SOL (INFERRED) | Mean | 90% range (bootstrap over windows) | Draws > 0 |
|---|---|---|---|
| Skip rule (36 triggers skipped; rule on only) | +0.026 | −0.098 to +0.144 | 66% |
| Stop rule (45 windows stopped) | +0.034 | +0.004 to +0.097 | 100% |
| Overlap (one token counted by both rules) | −0.027 | | |
| **QUIET total** | **+0.034** | **−0.090 to +0.154** | **70%** |
| warm-up 15:27–16:27 (stop rule only) | +0.002 | fees only | |
| rule on 16:27–17:37 | +0.032 | −0.093 to +0.152 | 68% |
| Total, calibrated: wins × 1.20 / × 1.41 | +0.025 / +0.015 | −0.15 to +0.15 | 65% / 61% |

**Calibration.** The replay matches live on fills, losses and per-trade P&L, but **it is 44% low on the total**.
- Fills: 46.2 vs 49. Fill yes/no agreement: 86.5%.
- Losers: 23.0 vs 23, summing −0.319 vs −0.323.
- At the same fill slot, its P&L equals live: +0.665 vs +0.644, correlation 0.98.
- It under-calls winners: it fills live winners in 66% of draws, against 80% for live losers.
- Total net: replay +0.346 vs live +0.622. Live sits at the replay's 96th percentile.
- Without the one +0.22 take-profit (w120), the replay is 30% low.
- Calibration factor (INFERRED): winning fills × 1.20 to 1.41. Losses and fees stay as modeled, because they match live.

**Verdict (INFERRED):** QUIET added about **+0.03 SOL** in run 27. Across landing models and calibrations the estimate is
+0.008 to +0.043, about 5% of the run's pre-send net of +0.622. The 20%-fewer-buyers test gives +0.057 but does not fit
run 27. The range includes zero, so run 27 neither proves nor disproves QUIET. The result rests on about 6 tokens.

**Where it came from:**
- **Stop rule:** one token, FXSLE6wv at 17:09:20. It was stopped at slot +6 with 1 other trade. The dump came at +10
  (9 SOL, −46%) with one buyer. QUIET avoided about −0.030; fees saved add +0.004.
- **Skip rule, the 33 ordinary skips: about 0** (+0.001).
  - One winner was missed: 6B5kjYrA, 17:07:25, +0.041.
  - Two losers were avoided: DV4tGXxh −0.027 and UjqtDoAL −0.014. Fees saved: 0.006.
- **Skip rule, 3 "twin" triggers: +0.026.** Two whales bought in the same slot. QUIET skipped the first and armed the
  second, which is not quiet (the first whale's buy counts as an earlier trade in its slot). Two swaps helped (+0.018,
  +0.028) and one hurt (−0.020).

| Top misses and saves | PKT | Effect on QUIET's side |
|---|---|---|
| Missed winner: 6B5kjYrA (skipped) | 17:07:25 | −0.041 (fills 79% of draws, +0.052 per fill; dip bots bought the whale's dump) |
| Save: FXSLE6wv (skip S19 + stop w133) | 17:09:20 | +0.028 (one loss; either rule alone avoids it) |
| Save: DV4tGXxh (skipped) | 17:12:13 | +0.027 (a 6.5 SOL holder sold at +3, then a second sell at +5) |
| Cost: ii5pvjaC (twin) | 17:13:45 | −0.020 (QUIET's skip let the twin w147 arm; it lost −0.024, MEASURED) |
| Save: 77scJtHc (twin) | 16:35:54 | +0.018 (the twin w80 won +0.008 live; the skipped window would have lost −0.010) |
| Save: UjqtDoAL (skipped) | 17:27:48 | +0.014 (the whale dumped at +10 with no buyer) |

## 1. Data and method
- **Live (MEASURED):** `runs/ams/runs/dip_ams_r27.jsonl`. 177 armed windows and 36 QUIET skips. Live pre-send net is
  **+0.6221 SOL** (realized + rent back − failed-try fees, as `eval_live.py`).
  - Failed-try fees: the engine counted 0.0221 SOL. On chain they are 0.0224: 57 tries the engine logged "unseen" did
    land and fail.
  - All 4,419 tries but one are on chain.
- **Chain tape (MEASURED):** FRA's recording `collect/run_20261026_1415`, 29 chunks, 15:16:38 → 17:41:45 PKT, 342,559
  pump trades. Decoded with the unchanged `real/decode.py` and `real/build.py`.
  - **No gaps.** 571 of the 37,260 slots in the run span have no block. None of the 9,558 slot references in the engine's
    records (try landings, trades it saw, fills, sells, dumps) falls in them, so these are leader-skipped slots, not
    recording holes.
  - Every 5-min bin has ≥ 96.9% of its slots.
  - Our 49 fills and 49 sells were removed from the tape (the replay puts its own buy in). Our 8 regular M2 trades stay as
    market.
- **Model:** the LAST_HOUR realistic replay. `real/sim.py` is imported unchanged.
  - Landing: the donor transplant from probe 3's 153 windows (AMS run 19), the model that matched FRA r22 within 0.003 SOL.
  - The view model, the probes' sell delays, the follower slippage drop and the live costs, as there.
  - Run 27's own settings: k 4, helius-ps 20/s, 0.35 SOL, limit × 0.88, deadline +1, 10 slots, exit 2 slots / TP 10% /
    SL 20%, one position, 5,120 per failed try.
  - Pace slot 213.3 ms, MEASURED on 4,134 try gaps.
  - Check pool: run 27's own 54 full live windows. Its landing is MEASURED the same as probe 3's: 38% / 56% / 7% land in
    the send slot / +1 / +2, against 39% / 54% / 6%.
- **What `sim27.py` adds** (otherwise `sim.run` line for line; with one shared random generator it gives identical output,
  checked on 2 seeds):
  1. Common random numbers: each window draws from its own generator, so a window behaves the same in every stream unless
     the rule change reaches it.
  2. The live QUIET stop at its live time.
  3. The 45 stopped windows' tries before the stop cannot fill. Live, none did (MEASURED); only the tries after the stop
     are modeled.
  4. The modeled stop for windows not armed live: decide at the start of slot +6 plus a delay drawn from the 45 live stops
     (median +24.5 ms; 5–95% −70 to +235 ms), and stop if fewer than 2 other trades were seen. Checked on run 27's 117
     decided windows: **116 agree with the live decision** (45/45 stops, 71/72 non-stops). The others count is exact in
     91%.
  5. Dynamic arm checks: a trigger on a token whose window is still armed is blocked, as the engine does.
- **Streams** (400 draws each):
  - `cal`: the 177 windows, model free (calibration).
  - `A0`: as live.
  - `B`: no QUIET (36 skipped armed, no stops).
  - `C`: skip rule off only.
  - `D`: stop rule off only.
  - `iso`: each window alone.
  - Effects: skip = C − A0, stop = D − A0, total = B − A0.
  - A live window that a counterfactual blocks loses its MEASURED live net.
- **Ranges:** model draws with the windows fixed, and a bootstrap over windows (10,000 resamples). The bootstrap is
  stratified: the 36 skipped, the 45 stopped and the 132 others are each resampled within their group, and each picked
  window gets a random draw.

## 2. Calibration on run 27's own 177 windows (task 1)
| Group | Fills live / replay | Wins live / replay | Realized + rent, live / replay | Fees live / replay | **Net live / replay [5–95%]** | Live pct |
|---|---|---|---|---|---|---|
| All 177 | 49 / 46.2 | 26 / 23.2 | +0.644 / +0.369 | 0.0221 / 0.0225 | **+0.622 / +0.346 [+0.132, +0.602]** | 96th |
| Without w120 (3N44sv2M, +0.22 TP) | 48 / 45.6 | 25 / 22.7 | +0.422 / +0.303 | 0.0219 / 0.0223 | +0.401 / +0.280 [+0.095, +0.455] | 86th |
| Warm-up (74) | 19 / 17.2 | 8 / 6.8 | +0.070 / +0.027 | 0.0098 / 0.0099 | +0.060 / +0.017 | 78th |
| — would-skip, all 4 signals (20) | 4 / 4.5 | 1 / 0.8 | +0.004 / −0.012 | 0.0029 / 0.0028 | **+0.0015 / −0.0146 [−0.062, +0.016]** | 70th |
| — kept (54) | 15 / 12.8 | 7 / 6.0 | +0.066 / +0.039 | 0.0070 / 0.0071 | +0.059 / +0.032 | 71st |
| Rule on (103) | 30 / 28.9 | 18 / 16.4 | +0.574 / +0.342 | 0.0122 / 0.0126 | +0.562 / +0.329 | 95th |
| Stopped by QUIET (45), before the stop | 0 / 0.8 | 0 / 0 | 0 / −0.009 | 0.0050 / 0.0049 | −0.0050 / −0.0136 | 95th |

**Fills yes/no:**
- Agreement 86.5% (Brier 0.077; base rate 0.28).
- Live-filled windows: the replay fills them in 73% of draws.
- Live-unfilled windows: the replay fills them in 8% of draws, about +0.0004 per window net.

**P&L per fill:**
- Live +0.0131. Replay, given a fill on the same windows: +0.0112.
- At the live fill slot, the replay gives +0.0136 vs live +0.0131 (all 49 windows, correlation 0.98). So the exit and
  P&L model is right; the gap is which windows fill.

**Winners and losers:**
- Losers: 23 live vs 23.0 replay, −0.323 vs −0.319.
- Winners: 26 live vs 23.2 replay, +0.967 vs +0.688.
- The replay fills live winners in 66% of draws and live losers in 80%. The biggest single gap is w120: 52% fills,
  +0.066 mean, against +0.222 live.

**The 20 would-skip windows (the same kind of window as the 36 skips)** check well window by window:
- All 4 live fills are reproduced: in 76–89% of draws, with P&L if filled −0.016 / +0.046 / −0.011 / −0.014 against live
  −0.018 / +0.047 / −0.011 / −0.014.
- The replay's lower total (−0.015 vs +0.002) comes from 2 windows that live never filled: 5U7guGZV (41% of draws) and
  FSMjghTc (66%), both −0.011.
- So on quiet windows the replay is a little pessimistic.

**Verdict:**
- The model is **off by more than 30% on the total** (−44%; −30% without w120). Live at the 96th percentile is either luck
  on a few winners or a slow bias on fast-recovering dumps; one run cannot tell which.
- **Calibration factor (INFERRED):** every winning fill's P&L × 1.41 (from all 177 windows) or × 1.20 (without w120).
  Losses and fees are not scaled: they match live.
- A plain × 1.8 on the total would also scale losses, which the data do not support.

## 3. The 36 skipped triggers, replayed as if armed (task 2)
All 36 came after the 16:27:09 warm-up.

| Case (INFERRED) | Fills | Wins | Realized | Failed-try fees (model) | **Net = given up** |
|---|---|---|---|---|---|
| Armed, stop rule on (= skip rule off) | 5.5 | 2.0 | −0.038 | 0.0049 | **−0.043** (draws −0.103 to +0.001) |
| Armed, no stop rule | 6.2 | 2.0 | −0.040 | 0.0069 | −0.047 |
| Armed, stop on, wins × 1.20 / × 1.41 | 5.5 | 2.0 | −0.029 / −0.019 | 0.0049 | −0.033 / −0.024 |
| Each window alone (no interactions) | 5.5 | | | | −0.043 |

**Knock-on: twins.**
- Arming 3 skipped triggers would have blocked a live window on the same token: w80, w133 and w147. Each of those was the
  second whale's trigger in the same slot.
- The blocked windows lose their MEASURED live net: w80 +0.0077, w133 −0.00002 (stopped) and w147 −0.0241.
- That is a +0.0165 knock-on for the counterfactual.

**Total given up by the skip rule: −0.026.**
- Draws: −0.086 to +0.018. Bootstrap: −0.144 to +0.098. 34% of bootstrap draws are > 0.
- Calibrated: −0.017 (× 1.20) or −0.007 (× 1.41).
- Split:
  - 33 ordinary skips: −0.001 (≈ 0).
  - 3 twin swaps: −0.026.

| Twin pair (same slot, same token) | Skipped 1st whale, armed (model) | 2nd whale, live (MEASURED) | QUIET effect |
|---|---|---|---|
| 77scJtHc 16:35:54: S4 / w80 | −0.0098: its whale sells only at +9, so it also fills the +9 dump (60% of draws) | +0.0077: its whale's dump at +3 filled it, and its window then closed | +0.018 |
| FXSLE6wv 17:09:20: S19 / w133 | −0.028: not stoppable (2 others by +6), fills the +10 dump | −0.00002: stopped at +6 with 1 other trade | +0.028 |
| ii5pvjaC 17:13:45: S25 / w147 | −0.004: its whale sold at +4, window closed, fills 13% | −0.024: armed to +10, filled the +7 dump | −0.020 |

## 4. The 45 stopped windows, after the stop (task 3)
| Case (INFERRED) | Fills | Wins | Realized | Failed-try fees | Net |
|---|---|---|---|---|---|
| Stopped as live (live: 0 fills, fees 0.0050, net −0.0050) | 0 | 0 | 0 | 0.0049 | −0.0049 |
| Run to the window end | 0.9 | 0 | −0.030 | 0.0090 | −0.039 |

**Given up by stopping: −0.034.**
- Draws: −0.055 to −0.004. Bootstrap: −0.097 to −0.004. No bootstrap draw > 0.
- After the stop there are 821 more tries and 0.0041 SOL more failed-try fees.
- Only 2 windows fill after the stop:
  - w133 FXSLE6wv: 88% of draws, −0.034 per fill. At +10, 3 sellers dumped 9.0 SOL (−46%), the first whale among them,
    with one 1.0 SOL buyer.
  - w139 4BHf5WJh: 7% of draws, −0.011 per fill.
- Warm-up: 21 stopped, no fill after the stop in any draw. Given up −0.0022, fees only.
- Rule on: 24 stopped, −0.032.
- Knock-on: w103 HgYFsSYC (16:55:07) would have been blocked by an earlier window on its token still running. Its live net
  was −0.0001.

## 5. Net QUIET effect on run 27 (task 4; live − no-QUIET counterfactual; + = QUIET helped)
| | Effect (model) | Draws 5–95% | Bootstrap 5–95% | Bootstrap > 0 | Wins × 1.20 | Wins × 1.41 |
|---|---|---|---|---|---|---|
| Skip rule | +0.026 | −0.018 to +0.086 | −0.098 to +0.144 | 66% | +0.017 | +0.007 |
| Stop rule | +0.034 | +0.004 to +0.055 | +0.004 to +0.097 | 100% | +0.034 | +0.034 |
| Overlap (FXSLE6wv: with both rules off, w133 never arms) | −0.027 | | | | −0.027 | −0.027 |
| **QUIET total** | **+0.034** | −0.010 to +0.094 | **−0.090 to +0.154** | 70% | **+0.025** | **+0.015** |
| Warm-up phase (stop rule only) | +0.002 | +0.002 | +0.002 | 100% | +0.002 | +0.002 |
| Rule-on phase | +0.032 | −0.012 to +0.092 | −0.093 to +0.152 | 68% | +0.022 | +0.013 |

- **Without QUIET, run 27's pre-send would have netted about +0.588 SOL** (calibrated +0.597 to +0.607) instead of
  +0.622.
- **Warm-up, skip rule (MEASURED):** had the rule been on in the first hour, it would have dropped 20 windows that netted
  +0.0015 live (4 fills, 1 win). That is about zero; the replay says +0.015 saved.
- **Sensitivity (QUIET total, model / wins × the pool's factors):**

  | Variant | Calibration (replay net vs live +0.622) | QUIET total | Bootstrap 5–95% |
  |---|---|---|---|
  | P3 landing (main) | +0.346, 96th pct | +0.034 / +0.025 / +0.015 | −0.090 to +0.154 |
  | Run-27 landing (leave one out) | +0.360, 96th | +0.043 / +0.036 / +0.026 | −0.085 to +0.175 |
  | P3, +15 ms landing | +0.353, 96th | +0.027 / +0.017 / +0.008 | −0.097 to +0.146 |
  | P3, 20% fewer later buyers | +0.142, **100th (does not fit run 27)** | +0.057 | −0.059 to +0.178 |

- The key windows hold across variants:
  - 6B5kjYrA: +0.030 to +0.044.
  - FXSLE6wv: S19 −0.028 to −0.032, w133 −0.029 to −0.033.
  - DV4tGXxh: −0.027 to −0.030.
  - UjqtDoAL: −0.014 to −0.015.

## 6. Big winners and losers among the skipped and stopped windows (task 5)
Per window, mean over draws (INFERRED; the per-fill number is the P&L when the replay fills).

| Window | PKT | Mint | Replay: fill / mean / per fill | Why (tape, MEASURED) |
|---|---|---|---|---|
| **Winner > +0.03:** S17 (skipped) | 17:07:25 | 6B5kjYrA5ga2knc1jfppGomXoovob1pAYUqx1CVfpump | 79% / **+0.041** / +0.052 | Whale JA2VvAzt (9.0%) dumped at +7 with 2 others (4.4 SOL, −24%). Four dip buyers (3.1 SOL) took the price +22% off the low within 2 slots. All four signals held (no cohort holder, no follower bot on the token, whale with no dump history), but dip bots came anyway. |
| Loser: S19 (skipped) + w133 (stopped) | 17:09:20 | FXSLE6wvxbjHAmjPmrJdtdHuc123AB3GFUMgWAFJpump | 89% / −0.028 / −0.032 (w133 after stop: 88% / −0.030 / −0.034) | Two whales in one slot (4cHFZJqP 7.2%, then 7YD8Lwz6). At +10, 3 sellers dumped 9.0 SOL (−46%). One buyer (1.0 SOL), then 7YD8Lwz6 dumped at +11. Either rule avoids it once. |
| Loser: S23 (skipped) | 17:12:13 | DV4tGXxht2zsNKPKCA3JRRRDQxsyh2NmAJrp5HErpump | 93% / −0.027 / −0.029 | Big curve (60 SOL). Another holder sold 6.5 SOL at +3 (−19%). 3 buyers (2.0 SOL), but a 3.5 SOL sell at +5 hit our 2-slot exit. |
| Twin cost: S25 (skipped) / w147 (live) | 17:13:45 | ii5pvjaC8oNWX6VGR52BfhQ18DbPg5BjLMaTvHnpump | S25: 13% / −0.004 / −0.030; w147 live −0.024 | The skip handed the window to the 2nd whale (9qz7cWBq), whose window stayed armed to +10 and filled the +7 dump (live −0.024). The skipped whale sold at +4, which would have closed its window. |
| Near the bar: S31 (skipped) | 17:27:48 | UjqtDoALkbKxarkfyWteJCyGyegdHrsEd2hfJkApump | 86% / −0.014 / −0.016 | Whale 7ZBgJAWu (8.5%) and one other dumped 5.0 SOL at +10 (−28%). No buyer. |
| Near the bar: S4 (skipped) / w80 (live) | 16:35:54 | 77scJtHcGY4nWxHUKzYx74CsumEhSzb8CwU3PpUqpump | 99% / −0.010 / −0.010; w80 live +0.008 | The 2nd whale (GCu3HxLs) dumped at +3: a small win, w80's live fill. The skipped 1st whale's window would also have caught the +9 dump (8.5 SOL, −36%): fills there in 60% of draws, at a loss. |

- No stopped window was a winner after its stop.
- Of the other 30 skipped triggers, 28 never fill in the replay: there was no 12% drop within the window. Their cost is
  failed-try fees, about 0.0001–0.0002 each.
- 39WKYHpS (17:22:49) fills 83%, +0.003.
- EDkHHaQU (16:43:14): the stop rule would cut it before its whale's +7 dump (stopped in 97% of draws).

## 7. Caveats
- **Small and concentrated.** ±0.03 against a +0.62 run. The sign rests on 6 tokens. 70 min of rule-on data cannot judge
  QUIET.
  - The research expectation for AMS was +0.022 / +0.025 per run (REPORT.md dev: r24, r25). Run 27's +0.03 is in line
    (INFERRED).
  - The large gains in the research came from weak hours (FRA r23/r24).
- **The skip rule's +0.026 here came from twins, not from quiet tokens.** On the 33 ordinary skips the replay finds about
  zero: one dip-bot winner missed, two quiet losers avoided.
  - A twin swap is a coin flip: whose window stays open depends on which whale sells first.
  - Design note (INFERRED, not a request): a twin's second trigger can never pass the "no earlier trade in the slot"
    signal. So the skip rule effectively re-targets the window rather than skipping the token.
- **The model under-calls winners.** It fills live winners 66% vs losers 80%; live was at the replay's 96th percentile.
  The calibrated rows (× 1.20 / × 1.41) cover this. They lower QUIET's total to +0.025 / +0.015, because S17 is the
  biggest skipped window and a winner.
- **On quiet windows the replay is slightly pessimistic** (20 would-skip windows: −0.015 vs live +0.002, from 2 false
  fills). That would also lower QUIET's value a little.
- **Not modeled:** double fills; the regular M2 bot sharing the one position (4 regular fills in this run); competitors
  reacting to us. Rate-limit and position interactions are modeled; here they came out zero, because no extra window
  overlapped another.
- **The bootstrap** treats windows as exchangeable within each group. It does not include model error. That error was
  ~0.003 SOL on FRA r22 and is −0.28 SOL on this run's total (mostly winners).

## 8. Files
- Code (`ops/strategies/presend/filter/live27/`):
  - `lib27.py`: run loader, tape, donors, settings.
  - `qcheck.py`: the stop-rule check.
  - `setup27.py` and `sim27.py`: `sim.run` plus the QUIET pieces.
  - `replay27.py`: the streams.
  - `calib27.py`: task 1.
  - `effects27.py`: tasks 2–4 and the bootstrap.
  - `tables27.py`: tasks 2, 3 and 5.
  - `eval_live.py`: unchanged.
- Data (`/home/moiz/sniper-data/presend_filter/live27/`):
  - `dec/` and `tab/`: the tape.
  - `donors27.pkl`.
  - `qcheck.json`.
  - `replay27_{P3,R27}_main.pkl` and `replay27_P3_{lag15,cut20}.pkl`.
  - `calib27_*.txt`, `effects27_*.{txt,json}` and `tables27_P3_main.txt`.
- Re-run (about 2 min):
  ```
  cd /home/moiz/sniper/ops/strategies/presend/filter/live27
  python3 qcheck.py                          # needs donors27.pkl (lib27.build_donors) and tab/
  python3 replay27.py --pool P3 --draws 400 && python3 replay27.py --pool R27 --draws 400
  python3 replay27.py --pool P3 --lag 15 --tag lag15 && python3 replay27.py --pool P3 --cut 0.2 --tag cut20
  python3 calib27.py P3 main; python3 effects27.py P3 main; python3 tables27.py P3 main
  ```

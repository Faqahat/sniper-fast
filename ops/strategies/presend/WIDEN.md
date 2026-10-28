# Pre-send WIDEN check: catching more dumps (10-28 ~19:50 PKT)

Analyst task. Offline replay only: nothing sent, no server writes, no engine or existing file changed.
MEASURED = live records or the chain recording. INFERRED = replay output. Times are PKT.
Code and data: /tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/ps_widen/:
- wbook.py: QUIET dump book;
- wtrig.py: triggers for every kind;
- wsim.py: rsim plus the 200 ms exit;
- wrun.py: variants;
- wrep.py: tables;
- wcal.py: live check;
- tables.md: the full per-day tables.

## Verdict
**No widening passes.** The pass mark was: at least +0.5 SOL/day on the test day (10-28), a 90% CI above 0, and positive on every day. 0 of 21 variants pass.
- The best on the training days was **V4_20** (T2 window 20 slots):
  - +0.85 on 10-26 and +0.26 on 10-27;
  - on the test day **+0.17 [-0.56, +0.86]**, and -0.20 with 20% fewer followers.
  - It is the only variant positive on all 3 days. It is too small and too uncertain to act on.
- **These lose clearly:** creator triggers (V2: -2.1 to -3.3/day every day), insider triggers on the training days (V3: -1.2 to -3.4), all four kinds together (V5_all10: -2.0 to -3.1), and 30- or 50-slot windows.
- **Small or mixed:** laddered whales (V1: 0.00 / +0.07 / -0.37) and the 12% holding cap (V5_cap: -0.3 to -0.8).
- **V6 creator ladder:** +0.9 to +1.2 on 10-26, -0.3 to -1.3 on 10-27, and -0.4 to +0.3 on the test day. CIs are about ±2 SOL/day. Not proven. With 20% fewer followers every V6 variant is negative.
- **Multiple testing:** 21 variants against V0: 15 from the brief, 6 V6 variants added mid-task, and V0nq as a check. On ~22 h per day, a +1 SOL/day result on one day is within chance. That is why only the held-out day counts.
- **Why the owner's examples do not turn into replay profit (MEASURED on the tape):**
  1. Their rebounds (+29 to +123%) are the best price over the next **15 slots (~3 s)**. The live exit sells 200 ms after the fill, before most of that rebound.
  2. Ladder sell steps are often below 12% each. On GHocge the creator's steps at +28 to +31 are 13% / 9% / 9% / 6%. On F7qMuk the steps at +25 to +30 are 6–10%. A 0.88 limit set from the latest price seen does not fill on a 6–9% step.
  3. When it does fill, it often fills on an early, small step. One fill per window then means we sit in a flat position (about -11 mSOL, the pump fees) when the big dump comes. Example: F7qMuk V6_n20 fills at -17 mSOL; the 38% dump at +33 comes afterwards.

## 1. Setup (as live FRA r27/r28 unless noted)
- 0.45 SOL, k 8, helius-ps rate caps: path bucket 40/s, global 40/s, path [[send]] budget 20/s.
- Limit 0.88× the latest seen price; deadline +1 slot; whale ≥ 6%. The live config is 6% (run_start record), not the 5% in the brief.
- QUIET skip (4 signals, 24 h whale dump book rebuilt from the tape) and QUIET stop 6:2.
- One position at a time; create-slot T2 triggers skipped.
- **Exit:** sell 200 ms after the engine sees our fill (dip22 `--presend-live-exit-ms 200`), else TP 10% / SL 20% / 2 slots.
- **Costs:** 2.015 mSOL per fill (buy fee + 0.2 tip + sell fee and tips + net ATA rent; checked on an r28 fill: 3.524 mSOL incl. rent − 1.509 rent back). Every landed failed try costs 5,120 lamports.
- **Simulator:** haqq_dissect/rearm/rsim.py, the engine-faithful replay. Its fill pricing was checked on 740 live fills. Changes here:
  - the "ms" exit;
  - the QUIET stop excludes the trigger wallet for every kind;
  - the separate 20/s budget;
  - send logging.
- 10 draws per day with common random numbers, so a variant minus V0 is a paired difference.
- **CI:** 90%, from a bootstrap over hours plus the spread between draws.
- **Days:** 23:15 → 23:15 PKT, usable hours only (≥ 95% slot coverage):
  - 10-26: 23.0 h;
  - 10-27: 23.0 h;
  - **10-28 (test, nothing chosen on it): 10-27 23:15 → 10-28 19:35, 19.3 h** (03:00–04:00 dropped for coverage).
- **Tapes:**
  - rearm/tab_D4 and tab_D5 (reused, read-only);
  - a new tab28 built from dv8 / verify decodes plus a fresh decode of the 10-28 chunks. Two server chunks (19:25–19:35) were read with `sudo cat`, decoded, then deleted locally.

## 2. Calibration vs live (V0, same trigger time ranges)
| | Live (MEASURED) | Replay V0 (INFERRED, 10 draws) |
|---|---|---|
| FRA r27 (02:26–14:26, 2-slot exit) armed windows | 1,089 | 1,003 |
| r27 fills (wins) | 200 (107) | 165 (94) |
| r27 net (realized + rent back − failed tries) | **+1.553** | **+1.561 [+1.16, +1.92]** |
| r27 tries sent / refused by the caps | 34,878 / 24,113 (41%) | 32,037 / 22,527 (41%) |
| FRA r28 (14:31–19:24, 200 ms exit) armed windows | 309 | 332 |
| r28 fills (wins) | 61 (35) | 61.6 (33) |
| r28 net | **≈ +0.41** (+0.365 realized + 0.092 rent back − ~0.047 failed tries) | **+0.557 [+0.31, +0.84]** |

- The replay matches r27 net and is ~35% high on r28. Live sits inside its 90% range in both runs. I applied no scaling. Treat the replay levels as slightly optimistic; the deltas between variants are paired, so they are less affected.
- QUIET earns its keep again: V0 without the QUIET skip (V0nq) is **-0.8 to -0.9 SOL/day on every day**.

## 3. Variants (Δ = variant − V0, SOL/day scaled to 24 h; INFERRED)
Definitions:
- **V1 / lad:** any buy (curve < 100 SOL) that takes a non-creator, non-insider wallet from below 6% to 6% or more, when its first ≥ 3% buy did not already trigger.
- **V2 / cre:** the creator or create signer holds ≥ 6% at the end of the create slot. Window from slot +1 for 10 / 30 / 50 slots. It stops when the group's first sell is seen.
- **V3 / ins:** create-slot buyers holding ≥ 6%. Same window rules.
- **V4:** T2 window of 20 / 30 / 50 slots. It still stops at the whale's first sell.
- **V5:** combinations, plus a cap that skips holdings above 12%.
- **V6 / fs:** a ≥ 5% holder's FIRST sell (after the create slot) that leaves it holding X% or more. Window N slots from that sell. It stops when that wallet drops below 1%.
  - V6: creator or ≥ 5% create-slot holder only. V6b: any ≥ 5% holder.
- Every variant keeps V0's T2 windows and QUIET.


#### Test day detail
#### Day 10-28 (test): 19.3 usable hours (rates scaled to 24 h)
| Variant | arms/h | fills/h | wins % | SOL/day net | Δ vs V0 SOL/day [90% CI] | Δ with 20% fewer followers | P&L per fill mSOL | failed-try fees SOL/day | sends/s avg | peak sends/s (p99 / max s) | refused % | seconds at 20/s cap % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| V0 | 94 | 16.2 | 57 | +3.91 | — | — | +11.0 | 0.36 | 0.8 | 20 / 20 | 41 | 39.1 |
| V0nq | 111 | 17.9 | 53 | +3.09 | -0.82 [-1.47, -0.18] | -0.86 | +8.2 | 0.42 | 1.0 | 20 / 20 | 42 | 38.7 |
| V1 | 108 | 17.7 | 55 | +3.54 | -0.37 [-0.75, +0.10] | -0.47 | +9.3 | 0.42 | 1.0 | 20 / 20 | 42 | 39.5 |
| V2_10 | 172 | 23.7 | 47 | +1.81 | -2.10 [-2.91, -1.27] | -2.88 | +4.3 | 0.66 | 1.5 | 20 / 20 | 43 | 41.1 |
| V2_30 | 172 | 26.0 | 46 | +1.42 | -2.48 [-3.44, -1.51] | -3.40 | +3.5 | 0.77 | 1.8 | 20 / 20 | 46 | 46.7 |
| V2_50 | 172 | 25.9 | 46 | +1.13 | -2.78 [-3.84, -1.77] | -3.58 | +3.1 | 0.82 | 1.9 | 20 / 20 | 47 | 49.1 |
| V3_10 | 137 | 23.1 | 53 | +4.04 | +0.13 [-1.08, +1.46] | -0.97 | +8.2 | 0.49 | 1.1 | 20 / 20 | 41 | 38.5 |
| V3_30 | 137 | 24.9 | 52 | +4.07 | +0.16 [-1.04, +1.46] | -1.22 | +7.7 | 0.56 | 1.3 | 20 / 20 | 43 | 42.5 |
| V4_20 | 93 | 19.0 | 56 | +4.07 | +0.17 [-0.56, +0.86] | -0.20 | +10.1 | 0.50 | 1.1 | 20 / 20 | 44 | 49.7 |
| V4_30 | 93 | 19.8 | 56 | +4.10 | +0.20 [-0.82, +1.09] | -0.26 | +9.9 | 0.60 | 1.4 | 20 / 20 | 45 | 55.2 |
| V4_50 | 92 | 20.9 | 55 | +3.74 | -0.17 [-1.11, +0.83] | -0.72 | +9.0 | 0.76 | 1.7 | 20 / 20 | 48 | 61.2 |
| V5_L20 | 106 | 21.0 | 53 | +3.55 | -0.36 [-1.40, +0.47] | -0.87 | +8.2 | 0.58 | 1.3 | 20 / 20 | 45 | 50.3 |
| V5_L30 | 106 | 22.0 | 53 | +3.57 | -0.34 [-1.51, +0.63] | -0.99 | +8.1 | 0.70 | 1.6 | 20 / 20 | 46 | 55.8 |
| V5_cap | 86 | 14.4 | 58 | +3.65 | -0.26 [-0.97, +0.56] | +0.04 | +11.5 | 0.33 | 0.8 | 20 / 20 | 41 | 39.1 |
| V5_L30cap | 98 | 19.9 | 53 | +3.23 | -0.68 [-1.78, +0.46] | -0.98 | +8.1 | 0.65 | 1.5 | 20 / 20 | 46 | 55.9 |
| V5_all10 | 215 | 30.1 | 47 | +1.95 | -1.96 [-3.32, -0.35] | -3.65 | +3.8 | 0.80 | 1.8 | 20 / 20 | 44 | 40.8 |
| V6_x3_n10 | 230 | 28.2 | 52 | +3.51 | -0.40 [-2.15, +1.39] | -1.74 | +6.5 | 0.91 | 2.1 | 20 / 20 | 45 | 41.8 |
| V6_x3_n20 | 227 | 32.7 | 51 | +3.40 | -0.51 [-2.73, +1.80] | -2.27 | +5.8 | 1.12 | 2.6 | 20 / 20 | 47 | 49.0 |
| V6_x6_n10 | 182 | 25.8 | 53 | +4.16 | +0.25 [-1.32, +1.69] | -0.93 | +7.9 | 0.72 | 1.6 | 20 / 20 | 44 | 41.2 |
| V6_x6_n20 | 181 | 30.0 | 52 | +4.22 | +0.32 [-1.79, +2.17] | -1.25 | +7.1 | 0.86 | 2.0 | 20 / 20 | 45 | 47.1 |
| V6b_x3_n10 | 278 | 30.6 | 50 | +3.24 | -0.67 [-2.52, +1.26] | -2.31 | +5.9 | 1.10 | 2.5 | 20 / 20 | 46 | 42.8 |
| V6b_x3_n20 | 275 | 35.4 | 49 | +2.60 | -1.31 [-3.71, +1.15] | -3.39 | +4.7 | 1.43 | 3.2 | 20 / 20 | 48 | 51.6 |


#### Summary: Δ vs V0, SOL/day (train days 10-26, 10-27; test 10-28)
| Variant | 10-26 | 10-27 | 10-28 test [90% CI] | test, 20% fewer followers | all days > 0 | passes (test ≥ +0.5, CI > 0, every day > 0) |
|---|---|---|---|---|---|---|
| V0nq | -0.89 | -0.89 | -0.82 [-1.47, -0.18] | -0.86 | no | no |
| V1 | +0.00 | +0.07 | -0.37 [-0.75, +0.10] | -0.47 | no | no |
| V2_10 | -2.18 | -2.07 | -2.10 [-2.91, -1.27] | -2.88 | no | no |
| V2_30 | -2.72 | -3.13 | -2.48 [-3.44, -1.51] | -3.40 | no | no |
| V2_50 | -2.89 | -3.30 | -2.78 [-3.84, -1.77] | -3.58 | no | no |
| V3_10 | -1.23 | -2.68 | +0.13 [-1.08, +1.46] | -0.97 | no | no |
| V3_30 | -1.23 | -3.43 | +0.16 [-1.04, +1.46] | -1.22 | no | no |
| V4_20 | +0.85 | +0.26 | +0.17 [-0.56, +0.86] | -0.20 | yes | no |
| V4_30 | +0.09 | -0.36 | +0.20 [-0.82, +1.09] | -0.26 | no | no |
| V4_50 | -0.57 | -0.58 | -0.17 [-1.11, +0.83] | -0.72 | no | no |
| V5_L20 | +0.43 | -0.04 | -0.36 [-1.40, +0.47] | -0.87 | no | no |
| V5_L30 | -0.37 | -0.91 | -0.34 [-1.51, +0.63] | -0.99 | no | no |
| V5_cap | -0.78 | -0.71 | -0.26 [-0.97, +0.56] | +0.04 | no | no |
| V5_L30cap | -0.84 | -1.64 | -0.68 [-1.78, +0.46] | -0.98 | no | no |
| V5_all10 | -2.60 | -3.13 | -1.96 [-3.32, -0.35] | -3.65 | no | no |
| V6_x3_n10 | +0.92 | -1.13 | -0.40 [-2.15, +1.39] | -1.74 | no | no |
| V6_x3_n20 | +0.02 | -1.34 | -0.51 [-2.73, +1.80] | -2.27 | no | no |
| V6_x6_n10 | +1.20 | -0.34 | +0.25 [-1.32, +1.69] | -0.93 | no | no |
| V6_x6_n20 | +0.98 | -0.49 | +0.32 [-1.79, +2.17] | -1.25 | no | no |
| V6b_x3_n10 | -0.13 | -2.23 | -0.67 [-2.52, +1.26] | -2.31 | no | no |
| V6b_x3_n20 | -1.12 | -2.48 | -1.31 [-3.71, +1.15] | -3.39 | no | no |
## 4. The three example tokens (10-28 19:19–19:29; replay, mean of 10 draws)
| Token | What would arm | Replay result |
|---|---|---|
| ywBDE8 (creator 2Bonf2 dumps +9 / +11 / +12) | V2 (creator window from +1); V6 (first sell +9 leaves 7.7%, window catches +11 / +12); V3 (insider 8NaAua 6.4%) | **V6: 3 of 10 draws fill, +43.5 mSOL gross each** (≈ +0.012 net per draw on average); V2: 1 of 10 fills, -10.5 mSOL; V3: +7.6 mSOL in 2 of 10 |
| F7qMuk (bwamJz first sell +14 at 0.95 SOL; ladder +25..+30; 11.34 SOL at +33) | V2 stops at the first sell +14 (no fill); V6_n20 (first sell +14 → window to +34); V1 + 30-slot window (AbNUHf trigger at +17, dump at +39) | V6_n20: 9 of 10 fill **-17 mSOL** (fills on a 6–10% ladder step, misses the +33 crash). V5_L30: 17 fills over 10 draws, -9.7 mSOL. V1 with 10 slots: no fill (dump 22 slots after the trigger) |
| GHocge (creator G3eWaB first sell +25, ladder +28..+31) | V2 creator window (+1..+11, then stopped by the first sell); V6 (first sell +25 leaves 14.5%) | V2: 8 of 10 fill, **-11 mSOL** (flat); V6: no fill. The steps after +25 are 13/9/9/6%: the 0.88 limit rarely triggers; 29 tries refused by the 20/s cap |

- On all three, the profit the owner saw comes from holding ~3 s into the rebound. With the 200 ms exit, the replay makes about **+0.00 to +0.01 SOL in total** on them, whichever variant.

## 5. Send rate
- **Average:** V0 sends 0.8–1.0 tries/s over the day.
  - Wider variants: 1.1–1.4 (V1 / V4_20), 1.5–2.3 (V2 / V3 / V4_50), 2.0–3.9 (V6).
- **Peak:** every variant hits the helius-ps 20/s budget in its busiest seconds (the p99 second = 20).
  - Share of sending seconds at the cap: V0 39%; V4_20 49%; V4_50 61%; V6 41–52%.
  - Refused share: V0 41% (live 41%); wider windows 44–50%.
- Longer windows mostly add refused tries and failed-try fees: +0.15 SOL/day for V4_20 and +0.40 for V4_50 on the test day.
- No variant needs a new path to run, but every one makes the cap bind more often. A wider variant would need a second path at the cost of more failed tries.

## 6. Re-test of earlier evidence
- V2_OPTIONS (10-25: creator targeting -4.0..+1.6/day, create-slot triggers -3/day, 5/20-slot windows no better, holders > 12% lose) is **confirmed with the 200 ms exit on 10-26 → 10-28**:
  - creator windows -2.1 to -3.3/day;
  - 20-slot windows +0.2 to +0.9 (not significant);
  - the 12% cap does not help (skipping > 12% LOSES 0.3–0.8/day, so those holders are not losers here).
- The haqq_dissect "longer windows ruled out" also holds: 30 / 50 slots ≤ 0.

## 7. What might work instead (INFERRED, not tested here)
- The examples point at the **exit**, not the trigger. The creator/whale dump rebounds peak over ~15 slots.
- A variant worth testing is creator-ladder windows (V6_x6) **with a longer exit** on those windows only (for example a 10–15-slot timer, like haqq bot 247's 15–30-slot timers). It must be done on a fresh held-out day, because this check already used 10-28.

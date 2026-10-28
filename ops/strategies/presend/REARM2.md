# Pre-send RE-ARM, replayed again with today's live config (10-29 PKT)

## Pre-registered pass bar (written 10-29 ~01:55 PKT, before any TEST day was scored)
- TRAIN = days 10-24, 10-25, 10-26 (23:15 → 23:15 PKT). TEST = 10-27, 10-28, 10-29 (10-28 23:15 → end of tape). Variants are chosen on TRAIN only.
- Scored rule: R0 = the owner's rule (wait 3 slots, 20-slot window, token ≤ 30 s, holder ≥ 6%), plus the one TRAIN-best variant. Live config: 0.65 SOL, TP 20%.
- PASS needs all of:
  1. on TEST, re-arm minus base ≥ +0.5 SOL/day, with the 90% CI (hours resampled) above 0, **with 20% fewer followers**;
  2. re-arm minus base > 0 on each TEST day (20% fewer followers);
  3. the base replay within 30% of live net P&L on the live runs it is compared with (FRA r28, AMS r34, AMS r35).
- The TRAIN-best variant is the one with the highest pooled TRAIN Δ at 20% fewer followers (0.65 SOL, TP 20%). Variants (all with 8 tries/slot): R0 wait 3 / 20 slots / ≤ 30 s / ≥ 6%; R1 wait 1; R2 10-slot window; R3 ≤ 60 s; R4 holder ≥ 8%; R5 R0 + the QUIET arm skip applied to the remaining holder.
- Size is not chosen: every size is shown on TEST.

Analyst task. Offline replay only: nothing sent, nothing written on a server, no engine or existing file changed. MEASURED = live records, engine code or the chain recording. INFERRED = replay output. Times PKT.
Code + every table: /home/moiz/sniper/ops/strategies/presend/rearm2/ (tables.md = full output; wsim2.py = rsim + the changes below; run.py = day runs; rep*.py = tables). Working data: scratchpad rearm2/ (tapes, results).

## Verdict: FAIL on the pre-registered bar (narrowly). Do not build it on this evidence.
| Bar | R0 (owner's rule) | R2 (TRAIN-best: 10-slot window) |
|---|---|---|
| 1. TEST Δ ≥ +0.5/day, CI > 0, at −20% followers | +1.27 [−0.36, +2.90] → **fail** (CI includes 0) | +1.33 [−0.14, +2.81] → **fail** |
| 2. Δ > 0 on each TEST day at −20% | +1.65 / +0.91 / +1.21 → pass | +1.32 / +1.30 / +1.80 → pass |
| 3. Base replay within 30% of live | AMS r34 −15%, AMS r35 −35%, FRA r28 +80% → **partial fail** (AMS pooled −21% passes; FRA does not) | same |

- Raw (all followers kept) the re-arm looks big: **+5.0 SOL/day on TEST [+3.1, +7.0]** for R0 at 0.65 SOL. That is the same "raw looks good" seen before.
- It is almost entirely follower money: −20% followers → +1.3 (CI touches 0); **−40% followers → −2.5 [−4.0, −1.1]** (clearly negative). Prior work's verdict (0..+1.2/day, ≈ 0 at −20%) is **roughly confirmed, slightly better** with today's 200 ms exit and 0.65 SOL.
- Re-arm fills earn a bit less than normal T2 fills: +13 vs +14 mSOL per fill at 0.65 (TEST), median +3..6 vs +9..13 mSOL; only 52–54% win vs 56–61%.
- **Failed-try cost decides it:** with the measured 0.005 mSOL per landed reverted try the re-arm adds ~0.4 SOL/day of failed-try fees. At 0.3 mSOL/try it would be **−22 to −24 SOL/day** (re-arm adds ~100k landed failed tries/day).
- R5 (R0 + QUIET skip on the remaining holder) is the only variant whose TEST CI clears 0 at −20% (+1.73 [+0.16, +3.30]); it was NOT the TRAIN pick (TRAIN +1.40 vs R2 +1.44, a tie). With 6 variants that is within chance. Worth a forward check only, not a build.

## 1. Setup (as live AMS r35; checked against its run_start record, MEASURED)
- T2 pre-send: whale ≥ 6%, 10-slot window, limit 0.88×, 8 tries/slot, deadline +1, one position, QUIET skip (4 signals) + stop 6:2, create-slot skip, helius-ps 40/s path + 40/s global + 40/s budget.
- Exit: the live 200 ms timer, modelled by the **MEASURED live fill → sell-landing delay** of 228 time-ms exits (FRA r28 + AMS r34 + r35; median ~300 ms, p10–p90 230–410 ms), TP/SL only on trades seen ≥ 100 ms before that sale; SL 20%.
- Costs: 2.9 mSOL per trip (as briefed; live records show ≈ 2.0 after rent back), 5,000 lamports per landed failed try (0.3 mSOL/try shown as a stress column).
- Re-arm (R0): after a single sell ≥ 6% of supply on a token ≤ 30 s old (post-dump curve < 100 SOL), if a wallet still holds ≥ 6% at the end of slot dump+2: arm at dump+3 for 20 slots, k 8, stop 30 ms after the engine sees the next ≥ 6% sell or the trade after which no wallet holds ≥ 6%; the same QUIET stop 6:2; a T2 trigger takes the token over.
- QUIET signals rebuilt from the tape: 99% agreement with the live engine's arm/skip decision on 1,100 matched triggers (f28 518/521, a34 490/493, a35 266/266) (MEASURED vs replay).
- Days 23:15 → 23:15 PKT, usable hours only (≥ 95% slots; 10-28 03:00 dropped). 10-29 = 1.9 h (to 01:10). 10 draws per day, common random numbers; CI = 90%, resampling hours and draws.
- Landing is the AMS-probe donor model (rsim). A new tape was decoded for 10-27 22:00 → 10-29 01:13.

## 2. Base reproduction (no re-arm) vs live, same trigger time range
| Run | Live (MEASURED) arms / fills / net | Replay (INFERRED) arms / fills / net [draw range] | Replay − live |
|---|---|---|---|
| FRA r28 14:31–20:01 (0.45, TP 10%) | 375 / 78 / **+0.516** | 399 / 118 / **+0.930** [+0.47, +1.30] | +80% (FRA lands slower than the AMS donor model: replay sends 19.4k vs 11.1k failed tries) |
| AMS r34 20:07–23:16 (0.45, TP 10%) | 379 / 120 / **+0.524** | 401 / 118 / **+0.443** [+0.01, +0.84] | −15% |
| AMS r35 23:18–01:10 (0.65, TP 20%) | 207 / 57 / **+0.236** | 221 / 57 / **+0.154** [−0.32, +0.82] | −35% (small sample) |
| AMS pooled | +0.760 | +0.597 | **−21%** |
- Net here uses 2.015 mSOL/trip to match the live accounting (realized + rent back − failed-try fees). Arms and AMS fills match closely. The replay is not optimistic on AMS; it is very optimistic on FRA.

## 3. Re-arm per day (R0, 0.65 SOL, TP 20%; SOL/day scaled to 24 h; INFERRED)
| Day | base | extra re windows/day | extra fills/day | re fills alone | Δ total [90% CI] | Δ −20% followers | Δ −40% | Δ w/o top-5 re fills | Δ @0.3 mSOL/try | sends/s base→re | cap-bound s % | refused % |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 10-24 (train) | +8.30 | 1,357 | +283 | +3.15 | +2.85 [+1.00, +4.78] | −0.03 | −3.26 | +1.71 | −21.9 | 1.42→2.39 | 3.2→5.4 | 2.3→3.9 |
| 10-25 (train) | +10.24 | 1,059 | +242 | +4.20 | +4.10 [+2.22, +6.02] | +1.63 | −1.03 | +2.99 | −16.2 | 1.13→1.93 | 2.1→3.4 | 1.5→2.4 |
| 10-26 (train) | +11.06 | 1,636 | +378 | +5.43 | +5.30 [+2.91, +7.68] | +1.87 | −2.40 | +4.11 | −24.2 | 1.64→2.80 | 3.4→6.0 | 2.5→4.5 |
| **10-27 (test)** | +10.99 | 1,755 | +383 | +6.09 | +5.83 [+2.76, +9.22] | +1.65 [−0.82, +4.29] | −2.62 | +4.34 | −25.1 | 1.64→2.86 | 3.7→6.0 | 2.6→4.4 |
| **10-28 (test)** | +8.70 | 1,510 | +337 | +4.05 | +3.97 [+1.60, +6.43] | +0.91 [−1.38, +3.25] | −2.39 | +2.77 | −23.5 | 1.37→2.45 | 3.2→5.1 | 2.3→3.7 |
| **10-29 (test, 1.9 h)** | +1.13 | 2,176 | +543 | +7.94 | +8.07 [+2.75, +13.89] | +1.21 [−4.73, +8.31] | −2.59 | −0.56 | −27.1 | 1.57→2.96 | 4.6→7.9 | 3.4→5.7 |
| TRAIN pooled | +9.85 | | | +4.25 | +4.07 [+2.88, +5.31] | +1.14 [+0.07, +2.20] | −2.24 | +2.92 | −20.8 | | | |
| **TEST pooled** | +9.49 | | | +5.18 | **+5.03 [+3.14, +6.99]** | **+1.27 [−0.36, +2.90]** | **−2.51 [−3.98, −1.05]** | +3.39 | −24.4 | | | |
- p99 sends/s = 40 (the cap) with and without re-arm. Live refuses ~1% at 40/s; the replay 1.5–2.6% base, 2.4–5.7% with re-arm.
- Base levels (+9–11 SOL/day) are replay levels; live r34/r35 ran at ~3–4 SOL/day-equivalent in their evening hours, which the replay matches for those hours.

### Variants, TEST pooled (chosen on TRAIN at −20%; INFERRED)
| Variant | TRAIN Δ −20% | TEST Δ raw | TEST Δ −20% [CI] | TEST Δ −40% |
|---|---|---|---|---|
| R0 wait 3 / 20 slots / ≤ 30 s / ≥ 6% | +1.14 | +5.03 | +1.27 [−0.36, +2.90] | −2.51 |
| R1 wait 1 | +0.59 | +3.62 | −0.21 [−1.74, +1.37] | −4.39 |
| **R2 10-slot window (TRAIN-best)** | **+1.44** | +4.23 | **+1.33 [−0.14, +2.81]** | −1.82 |
| R3 ≤ 60 s | +1.00 | +4.94 | +1.13 [−0.49, +2.78] | −2.74 |
| R4 holder ≥ 8% | +0.90 | +3.72 | +1.27 [−0.11, +2.65] | −1.23 |
| R5 R0 + QUIET skip on holder | +1.40 | +5.41 | +1.73 [+0.16, +3.30] | −1.90 |

## 4. The 'second seller' risk (INFERRED on the recorded tape; 0.65 SOL; mSOL per fill after 2.9 trip cost)
Definitions: big sell = a sell of ≥ 1% of supply by a wallet holding ≥ 6% at our fill, or any single sell ≥ 6% of supply.
| TEST fills | per day | big sell lands inside our hold | big holder sells within fill+2 slots | per fill, sold within 2 slots: yes / no | at 1.0 SOL: yes / no | per fill, big sell inside hold: yes / no |
|---|---|---|---|---|---|---|
| Re-arm (R0) | 386 | **5%** | **8%** | **−42 / +20** | −69 / +28 | **−79 / +20** |
| Re-arm (R2) | 303 | 5% | 8% | −38 / +20 | −62 / +28 | −77 / +20 |
| Base T2 | 697 | 6% | 10% | −29 / +19 | −47 / +27 | −61 / +19 |
- TRAIN is the same: re 6% / 9%, −43 / +21 mSOL; T2 7% / 11%, −45 / +25.
- So re-arm fills are **not hit more often** than normal fills (8% vs 10%), but each hit costs a bit more (−42 vs −29 mSOL at 0.65 on TEST). The hits explain tonight's −0.09..−0.14 SOL fills (the in-hold group averages −79 mSOL per fill).
- The loss per hit scales roughly with size (−29 → −47 mSOL for T2, −42 → −69 for re-arm, 0.65 → 1.0).

## 5. Size (owner addition; TEST pooled, TP 20%; SOL/day; INFERRED)
**Fill rate does not depend on size in this engine (MEASURED, src/presend_live.rs `limit_min_out`):** min_out is computed on the limit state including our own price impact, so a try fills iff the curve price before it is ≤ 0.88× (the engine's own unit test). Bigger size does NOT add reverts; it adds price impact and prices out more followers (modelled by the slack table). Fill rate is 0.268 (base) / 0.251 (R0) of armed windows at every size.
Corrected = raw − live-fill size gap per fill (PAPER_VS_LIVE §4 per-SOL gap 15.2 @0.35, 21.5 @0.55, 27.0 @0.75, linear, extrapolated): 0.40 → 6.7, 0.45 → 8.3, 0.65 → 15.8, 0.85 → 25.3, 1.00 → 33.9 mSOL per fill.
| Size | Base: fills/day / raw [CI] / corrected / per fill raw→corr / −20% / w/o top-5 / 2nd-seller per fill | R0 total: raw / corrected / −20% / w/o top-5 / 2nd-seller per fill | Re-arm Δ: raw [CI] / corrected / −20% [CI] |
|---|---|---|---|
| 0.40 | 697 / +5.84 [+4.51, +7.29] / **+1.17** / +8.4→+1.7 / +1.03 / +4.67 / −16.6 | +8.88 / **+1.73** / +1.59 / +7.49 / −19.1 | +3.03 [+1.85, +4.26] / +0.57 / +0.56 [−0.47, +1.57] |
| 0.45 | 697 / +6.73 [+5.22, +8.34] / +0.97 / +9.7→+1.4 / +1.40 / +5.40 / −19.2 | +10.20 / +1.41 / +2.12 / +8.65 / −21.9 | +3.47 [+2.13, +4.85] / +0.44 / +0.73 [−0.41, +1.86] |
| 0.65 (live) | 697 / +9.49 [+7.31, +11.80] / −1.50 / +13.6→−2.1 / +2.24 / +7.61 / −28.5 | +14.52 / −2.25 / +3.52 / +12.35 / −32.5 | +5.03 [+3.14, +6.99] / −0.76 / +1.27 [−0.36, +2.90] |
| 0.85 | 697 / +11.69 [+8.87, +14.71] / −5.94 / +16.8→−8.5 / **+2.71** / +9.27 / −38.7 | +17.88 / −9.03 / **+4.24** / +15.08 / −44.3 | +6.19 [+3.77, +8.64] / −3.09 / +1.54 [−0.51, +3.61] |
| 1.00 | 697 / +12.87 [+9.67, +16.39] / −10.75 / +18.5→−15.4 / +2.57 / +10.07 / −46.7 | +19.86 / −16.20 / +4.25 / +16.64 / −53.1 | +6.99 [+4.19, +9.79] / −5.45 / +1.68 [−0.72, +4.07] |
- **Which size maximises corrected TEST P&L: 0.40 SOL** (base +1.17, R0 +1.73), with 0.45 a close second; 0.65 and above go negative after correction. Same order on each test day (10-27: 0.40 +1.70 base; 10-28: 0.40 > 0.45 > 0.65).
- **Not robust.** The optimum depends entirely on which correction is right:
  - raw: rises to 1.0 SOL (+12.9 base) — the replay's per-fill gain from size (+8.4 → +18.5 mSOL) grows far slower than the ECHO gap (+6.7 → +33.9 mSOL);
  - −20% followers (the other proxy for the same gap): best at **0.85** (+2.71 base), flat 0.85–1.0;
  - the ECHO correction was fitted on reactive dip fires, not pre-send fills. On pre-send the base replay is already at or below live on AMS at 0.45 (−15%) and 0.65 (−35%), so subtracting the full gap double-counts. Read the corrected column as a pessimistic bound and the −20% column as the central case.
  - What would settle it: one live AMS run at 0.85 (fills and per-fill vs replay), as the owner's size probe.
- TP 10% instead of 20% (R0): −0.7 to −0.9 SOL/day at every size; keep 20%.

## 6. Caveats
- All levels INFERRED; the replay's landing is the AMS probe model, fine for AMS (−21% pooled), wrong for FRA (+80%).
- 10-29 is 1.9 h only; its CIs are ±5–8 SOL/day.
- R1 (wait 1) gates on the holders at the end of the dump slot; its stop uses the dump+2 holder trace (small look-ahead, INFERRED small).
- Size rows reuse the 0.65-SOL timeline for one-position pauses (a size changes only exit P&L, not which windows fill).
- Next step if wanted: dry shadow of R0/R5 flags on AMS (log-only) for 24 h to measure the real re-window fill rate on next-holder dumps; no live change.

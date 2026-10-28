# Pre-send whale pct sweep (10-28 evening)

Analyst task. This was an offline replay only: nothing was sent, nothing was written to the servers, and no engine or existing file was changed.
- **MEASURED** = live records (dip_r27/r28.jsonl). **INFERRED** = replay output. Times are PKT.
- Code and data are in /tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/ps_whalepct/:
  - mtrig.py: the WIDEN trigger extractor with the T2 floor lowered to 3%;
  - mrun.py: the variants;
  - mrep.py: the tables;
  - mlive.py: the live split;
  - tables.md: every table.
- The simulator is ps_widen/wsim.py (WIDEN's calibrated rsim plus the 200 ms exit), unchanged. Settings are as live: 0.45 SOL, k 8, limit 0.88×, deadline +1, 10-slot window, QUIET skip + stop 6:2, one position. Each setting ran 20 draws per run with common random numbers, so "Δ vs 6%" is a paired difference.
- **Net** = fill P&L − 2.015 mSOL fixed costs per fill (pump fees, tips, net ATA rent) − 5,120 lamports per landed failed try.
- **CI** = 90%, from resampling hours plus the spread between draws.
- **Run times (MEASURED from the records):**
  - r27 ran 10-28 **02:26 → 14:25 PKT**. The brief's 21:30 → 09:26 were UTC. 03:00–04:00 is dropped for tape coverage, which leaves 11.0 h.
  - r28 is compared 14:31 → **19:30** (5.0 h), because the local tape ends at 19:35.
- What the engine does with the setting (src/presend_live.rs): a window opens on a wallet's **first ≥ 3% crossing** when that buy leaves it ≥ whale pct. So 3% means "every first 3% crossing". The 6–12 / 5–12 caps have **no engine flag**; they would need new code.

## Verdict
- **Keep 6% for AMS run 34.** No setting beats 6% on both runs by more than the noise.
- Only **5.5%** is ahead on most slices: +0.76 on r27, −0.14 on r28, and +0.34 / +0.21 / +0.57 SOL/day on the three full days. Every one of those CIs includes 0.
- This is the result expected from ~10 settings × 5 slices. With 90% CIs, about 5 of the 50 cells should exclude 0 by chance. 5.5% has none.
- **Clearly worse (INFERRED):**
  - 3% loses 3–8 SOL/day everywhere;
  - 8%, 10% and 12% lose 2–7 SOL/day;
  - 4% and 7% are slightly negative on most slices.
- **The 12% cap does not help.** 6–12 is below 6% on every slice, −0.2 to −1.1/day, with 2 CIs entirely below 0.
  - MEASURED: holders above 12% made **+0.42 SOL on 11 fills** in r28 and −0.015 on 24 fills in r27.
  - The older V2_OPTIONS finding ("> 12% holders lose") is **not confirmed** with the current exits and QUIET rule.

## 1. Calibration at 6% (each run's own exit, 20/s cap)
| | Live (MEASURED) | Replay at 6% (INFERRED, 20 draws) |
|---|---|---|
| r27 armed / fills | 1,089 / 200 | 1,003 / 163.5 |
| r27 net | **+1.553** | **+1.612** [+0.69, +2.62] |
| r28 to 19:30: armed / fills | 324 / 66 | 347 / 66.3 |
| r28 net | **+0.314** (full run to 20:02: +0.516, 78 fills) | **+0.536** [−0.15, +1.24] |

- On r27 the replay matches net P&L, with ~18% fewer fills.
- On r28 the replay matches fills and is **~+0.2 SOL (≈ 70%) high on P&L**. Live sits inside the replay CI.
- I did not rescale. Read levels as optimistic. The Δ columns are paired, so the bias mostly cancels in them.

## 2. Sweep, 200 ms exit (what run 34 uses), SOL/day scaled to 24 h (INFERRED)
| whale pct | r27 @20/s | r27 @40/s | r28 @20/s | r28 @40/s | Δ vs 6% r27 @40 [90% CI] | Δ vs 6% r28 @40 [90% CI] | fills/h r27 / r28 @40 | per fill mSOL r27 / r28 @40 |
|---|---|---|---|---|---|---|---|---|
| 3 | +1.80 | +3.89 | −1.62 | −1.47 | −3.08 [−5.39, −0.79] | −5.41 [−8.90, −1.66] | 48.9 / 47.0 | +6.6 / +1.7 |
| 4 | +3.52 | +7.56 | +1.78 | +2.95 | +0.59 [−1.28, +2.38] | −0.99 [−3.53, +1.50] | 38.2 / 35.0 | +10.2 / +5.2 |
| 5 | +3.73 | +7.77 | +2.40 | +3.81 | +0.80 [−0.72, +2.21] | −0.14 [−2.03, +2.04] | 30.2 / 28.4 | +12.2 / +6.8 |
| 5.5 | +3.92 | +7.73 | +2.09 | +3.80 | +0.76 [−0.07, +1.60] | −0.14 [−1.84, +1.81] | 25.9 / 25.5 | +13.8 / +7.2 |
| **6 (live)** | +3.57 | **+6.97** | +2.59 | **+3.94** | — | — | 22.7 / 21.1 | +13.9 / +8.6 |
| 7 | +3.67 | +6.10 | +2.56 | +3.63 | −0.87 [−1.96, +0.29] | −0.31 [−2.86, +2.30] | 15.9 / 12.5 | +17.0 / +12.9 |
| 8 | +1.67 | +2.98 | +1.22 | +1.52 | −3.99 [−5.81, −2.07] | −2.42 [−5.81, +0.83] | 10.2 / 6.4 | +13.2 / +10.7 |
| 10 | +0.60 | +1.29 | +1.58 | +1.83 | −5.68 [−7.97, −3.32] | −2.11 [−5.74, +1.47] | 5.4 / 2.6 | +11.0 / +29.6 |
| 12 | +0.36 | +0.46 | +1.04 | +1.07 | −6.51 [−8.98, −4.07] | −2.87 [−6.56, +1.02] | 2.8 / 1.9 | +7.9 / +24.0 |
| 6–12 cap | +3.49 | +6.78 | +1.53 | +2.85 | −0.19 [−1.28, +0.91] | −1.09 [−2.45, +0.11] | 20.1 / 19.3 | +15.1 / +7.0 |
| 5–12 cap | +3.64 | +7.54 | +1.37 | +2.73 | +0.57 [−1.28, +2.45] | −1.21 [−3.60, +1.37] | 27.8 / 26.6 | +12.8 / +5.6 |

- **The old exit (2 slots / TP 10% / SL 20%)** gives the same picture: Δ vs 6% moves by up to ±0.6 SOL/day, and no setting changes sign beyond its CI.
  - r27 at 20/s: 5.5% +0.33, 5% +0.22, 7% +0.33 vs 6%.
  - r28 at 20/s: everything is at or below 6%, except 7% at +0.07. At 40/s: 7% +0.31, 5.5% +0.02.
  - Full tables are in tables.md.
- **Absolute net per run (SOL, 200 ms, 40/s):**
  - r27: 6% +3.19 [+2.06, +4.38]; 5.5% +3.54.
  - r28: 6% +0.82 [+0.09, +1.59]; 5.5% +0.79.
- **Failed-try fees per run at 40/s:**
  - 6%: 0.26 (r27) / 0.09 (r28);
  - 5.5%: 0.38 / 0.13;
  - 5%: 0.48 / 0.17;
  - 3%: 1.75 / 0.71.
- **Share of sending seconds at the cap:**
  - at 20/s: 39–41% for 5–12%, and 45–46% for 3%;
  - at 40/s: 0–3% for every setting except 3% (7%).
  - Refused tries fall from ~41% to ~2% at 6%.

## 3. Per-hour and per-day stability (200 ms, 40/s; INFERRED)
- **Hours where a setting beats 6%:**
  - r27 (12 h): 5.5% 6/12, 5% 8/12, 4% 8/12, 7% 3/12, ≥ 8% 0–1/12.
  - r28 (6 h): 5.5% 3/6, 5% 4/6, 7% 3/6.
  - No setting wins hour after hour. The 5–5.5% edge comes from a few hours (r27 05–06 and 10 PKT).
- **Three full days** (Δ vs 6% SOL/day; 10-28 overlaps both runs, so it is not independent of them):

| whale pct | 10-26 | 10-27 | 10-28 |
|---|---|---|---|
| 5 | +0.58 [−0.51, +1.91] | −0.24 [−1.65, +1.23] | +0.54 [−0.49, +1.59] |
| 5.5 | +0.34 [−0.59, +1.27] | +0.21 [−0.71, +1.25] | +0.57 [−0.34, +1.54] |
| 7 | −0.55 [−1.75, +0.60] | −2.15 [−3.48, −1.04] | −0.82 [−2.07, +0.18] |
| 6–12 cap | −0.78 [−1.74, −0.03] | −0.81 [−1.49, −0.06] | −0.23 [−1.02, +0.59] |

- At 6%, a full day nets +8.1 / +8.0 / +6.4 SOL/day at 40/s (INFERRED; r28 suggests the real level is lower).

## 4. Live fills by whale pct (MEASURED, net incl. rent back and failed tries)
| holding at trigger | r27 fills / net SOL / per fill mSOL | r28 full fills / net / per fill |
|---|---|---|
| 6–7% | 65 / +0.936 / +14.4 | 20 / +0.008 / +0.4 |
| 7–8% | 56 / +0.550 / +9.8 | 27 / +0.280 / +10.4 |
| 8–10% | 39 / +0.274 / +7.0 | 18 / −0.155 / −8.6 |
| 10–12% | 16 / −0.177 / −11.1 | 2 / −0.018 / −9.1 |
| > 12% | 24 / −0.015 / −0.6 | 11 / +0.420 / +38.2 |

- These are small samples: the buckets above 8% have 2–39 fills each. They do not show a clean "6–12% good, > 12% bad" pattern.

## 5. Recommendation for AMS run 34 (200 ms exit, 40/s)
- **Keep `--presend-whale-pct 6`.**
- **Best alternative: 5.5%.**
  - Expected gain about +0.3 to +0.4 SOL/day (INFERRED: mean of the 3 full days +0.37, of the 2 runs +0.31). Every CI includes 0.
  - Cost: +40% arms, +15–20% fills, +0.1–0.3 SOL/day in failed-try fees, and more of the run spent holding a position.
  - Risk: the downside on an r28-type afternoon is about −0.1 SOL/day, with a CI down to −1.8.
  - Not worth changing two settings at once (the cap goes 20 → 40/s for run 34). If we want to try it, try it on a later run once 40/s has its own live baseline.
- **Do not** go below 5% or above 7%, and do not build the 12% cap.
- **Caveats:**
  - The replay is FRA-tape and FRA-landing based. AMS may land differently.
  - The 40/s levels (+6–8 SOL/day) are INFERRED only. They assume the extra tries land like the 20/s ones. Run 34 is the first live check of that.

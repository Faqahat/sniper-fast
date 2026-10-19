# Does the exit ladder's "fading" trigger clip dip-then-rip RUNNERS?

Replay of exit variants on the SAME unbiased entries as econ_102 (entry = floor*1.02, net of all
costs: 2% protocol + 0.5% slip + priority/base lamports, size 0.5 SOL). Out-of-sample by slot split.
Sample = 656 creates that pass the shipped filter (dev_buy>=2, creator_fee_bps==0), of which 201
reach >=1.5x lifetime peak and 92 reach >=2x -- this sample CONTAINS runners (the prior "exit isn't
the problem" test did not). Simulator = faithful port of the shipped exit_ladder (econ_102.simulate,
verified bit-identical, max|diff|=0.0) with the fading rule made configurable.

## The suspect
Shipped ladder, per poll, in order: de-risk 0.30 at first poll; r<=cut_r(0.95) -> dump CUT;
riding & r<=peak*trail(0.92) -> dump; age>=cap(40 slots/~9s) -> dump;
**NOT riding & r<1.0 & a slot passed -> dump ALL ("FADING")** <- SUSPECT; else ladder 0.25 up /
arm ride at r>=1.40. The fading cut only operates in the thin band **(cut_r, 1.0) = (0.95, 1.0)**:
it dumps the whole bag the first slot price sits 0-5% under entry.

## Variant comparison (net R per trade; subsets are mean net R on that peak-bucket)
FULL SAMPLE (n=656; most stable estimate):

| variant | mean | median | win% | total R | run>=1.5x (201) | run>=2x (92) | dud<1.1x (258) |
|---|---|---|---|---|---|---|---|
| **CURRENT (instant fade)** | +0.0363 | -0.0364 | 25.3% | +23.82 | +0.1806 | +0.3248 | -0.0540 |
| NO-FADING | +0.0358 | -0.0272 | 37.3% | +23.48 | +0.2553 | +0.4277 | -0.1025 |
| PATIENT N=3 (deep .90) | +0.0362 | -0.0272 | 37.2% | +23.75 | +0.2557 | +0.4291 | -0.1017 |
| PATIENT N=5 / deep-only | +0.0358 | -0.0272 | 37.3% | +23.48 | +0.2553 | +0.4277 | -0.1025 |
| NO-FADE + cut 0.85, ride 1.4 | +0.0364 | -0.0272 | 40.7% | +23.90 | +0.2721 | +0.4531 | -0.1109 |
| **NO-FADE + cut 0.80, ride 1.4** | **+0.0396** | -0.0272 | 43.4% | **+25.97** | **+0.2930** | **+0.4846** | -0.1224 |

OOS slot-split (train=earlier half, validate=later half, n=328 each): CURRENT val mean +0.0388;
NO-FADING +0.0319; best combo (NOFADE cut0.80 ride1.4) +0.0348. Reverse direction (val=earlier):
CURRENT +0.0338, NO-FADING +0.0397, combo +0.0456. **The net-mean ranking flips with split
direction** -- mean is tail-driven and the runner subset is only ~98 tokens per half.

200 random 50/50 held-out splits (mean net R +/- sd across splits):
CURRENT +0.0361 +/-0.0114; NO-FADING +0.0355 +/-0.0127; PATIENT3 +0.0360 +/-0.0128;
NOFADE cut0.80 +0.0400 +/-0.0130. Paired vs CURRENT: NO-FADING delta -0.0006 (better 45% of splits);
PATIENT3 -0.0002 (48%); **NOFADE cut0.80 +0.0039 (better 74% of splits)**.

## Is fading clipping runners? YES -- robustly.
Per-token, removing fading changes 328 of 656 trades (better on 124, worse on 204). Gains are
concentrated exactly where the hypothesis said: delta from **runners (>=1.5x) = +15.01 R**, mid
(1.1-1.5x) = -2.84, **duds (<1.1x) = -12.50**. Runner capture lifts from +0.1806 to +0.2553 (+41%)
on 1.5x runners and +0.3248 -> +0.4277 on 2x runners. Per-token mechanical facts, not split
artifacts: on a dip-then-rip token the eager fade exits on the dip, every time. Hypothesis confirmed.

## Does removing/softening fading improve NET OOS expectancy? By itself, NO.
The +15.01 R of recovered runner upside is almost exactly cancelled by -12.50 extra dud bleed and
-2.84 mid-tier: net **-0.33 R across 656** for plain NO-FADING. Across 200 splits the NO-FADING vs
CURRENT delta is a coin flip (-0.0006, 45% better). PATIENT N=3/5 and deep-only behave the same. So
softening the fade **massively improves the shape** -- win 25.3% -> 37%+, median -0.036 -> -0.027,
far less tail-reliance -- but does **not** move mean EV: the fade band is only 5% wide and the duds
it was (correctly) bailing out of just bleed instead.

## What DOES move net EV: remove fading AND deepen the hard stop.
The fade only matters in (cut_r, 1.0). Widening that band by lowering **cut_r to 0.80** (keep ride
1.40) is what lets dip-then-rip runners survive their drawdown: full-sample mean **+0.0396 vs
+0.0363 (+9%)**, total **+25.97 vs +23.82 (+2.15 R)**, win 43.4%, runner capture +0.2930 / 2x
+0.4846, better than CURRENT in **74% of random splits**. Cost: deeper dud bleed (-0.1224 vs -0.0540),
i.e. holding losers to -20% before the stop. cut 0.85 is the conservative midpoint: mean +0.0364
(=current) but win 40.7% and much better runner capture -- a healthier distribution at the same EV.

## RECOMMENDED exit config
    --derisk-frac 0.30 --ride-mult 1.40 --trail-frac 0.92 --ladder-frac 0.25
    remove the "fading" instant-dump entirely
    --cut-r 0.80            (0.85 for the conservative, target-faithful variant)
    --exit-cap-ms 9000      (cap near-irrelevant: 9s / 15s / 20s differ by <0.001 R)

Primary pick: **drop fading + cut_r 0.80** -- the only change that lifts net OOS expectancy (+9%
mean, +2.15 total R, better in 74% of splits) rather than just reshaping it. If -20% single-trade
downside is a concern, **cut_r 0.85** keeps current EV with a far healthier win/median/runner capture
and matches the target more closely.

## Target sanity-check (/root/exit_study): his exit looks like NO-FADE + flat deep cut, NOT our eager ladder.
- His LOSERS first-sell at **median slot 10 (~2.2 s)**, first-sell r **0.994** (flat), dumping the
  whole bag; worst-decile cut r **0.86**; max loser hold **188 slots**. He does NOT instant-dump the
  first slot under entry -- he tolerates shallow early drawdown ~10 slots, then cuts flat.
- That is PATIENT-FADING / lowered-flat-cut behavior (hold through the dip, hard stop ~0.86-0.95),
  not our 1-slot fade. His winners reach median peak 1.284x (p90 2.03x, max 3.35x), first-sell
  slot+1 / r 1.178 -- he catches the rip because he did not bail on the dip.
- exit_study flagged the same clipping on his big runners (9FjQbzeS: a fixed trail clipped the tail
  on the first 8% pullback vs his hold to the 2.69x peak). Same bug, different trigger.

## Honest caveats
- Heavy tail: mean EV dominated by a few extreme winners; runner subset ~98/half, 2x ~44/half. The
  CURRENT-vs-plain-NO-FADING net-mean ranking flips with split direction -- robust read is "plain
  removal is net-neutral," not "current is best."
- One wallet, one ~2-day regime (slots 456.60M-456.82M, 2026-10-12..14), 656 tokens post-filter.
  72 empty price paths. Costs per leg (2% + 0.5% + lamports); no live send-latency slippage (would
  dock all variants ~equally).
- The cut_r=0.80 edge is real but modest (+0.004 R/token) and raises per-trade variance.

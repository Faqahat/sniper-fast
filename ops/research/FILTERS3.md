# "Creator dev" create-time signals: do they pick winners? (2026-10-21, FILTERS3)

Third round after FILTERS.md (bundle, tip, dev-buy buckets, host, create time, leader class) and FILTERS2.md (creator reputation REP, text, create-tx fields, wallet age/funder, leader skip list, regime). Same model and launches, plus **240 fresh launches from today's live paper engine (group E, 12:37 → ~14:15 UTC)**. Nothing here was tuned on B–E.

## Summary (plain language)

- **The owner's idea "the creator launched exactly 1 token before" does not work.** On-chain, creators with exactly one earlier pump.fun launch made money in the in-sample evening (A: 18 launches, +0.045 SOL each) but **lost out of sample: 63 launches, −0.023 SOL each (90% interval −0.034 to −0.012)**, negative in B, D and E. Splitting by how that one earlier launch did (our model, outside buys, how fast the creator sold it) did not find a profitable subgroup; every subgroup with ≥ 5 launches lost out of sample.
  - Other counts: first-ever creators (0 earlier launches in the visible history) **+0.024 per launch out of sample (324 launches) but −0.021 in A and −0.017 in D**: no clear edge. 2–3 / 4–10 / 11+ earlier launches: −0.006 / −0.018 / +0.011. Inside rule #2 each bucket has ≤ 10 launches: nothing to see.
  - Coverage caveat: public RPC history is short (median visible history only 0.5–2.3 h before the create for active wallets); 908 of 1424 launches have a count, 216 of them only a lower bound.
- **One new signal adds to REP: a known pro sniper bought one of the creator's earlier launches.** "A pro (dKMjeG, 4yFAz7, 9XPMCa, 3yrJE1, AHwJSn, 2EsRia, 9qz7cW) bought in S..S+2 of one of this creator's earlier watched launches": **+0.033 SOL per launch out of sample (123 launches, 31 creators, interval +0.006 to +0.060), positive in all five periods** (A +0.082, B +0.027, C +0.039, D +0.041, E +0.026).
  - It mostly sharpens REP: **REP + pro history: +0.050 per launch out of sample (83 launches, interval +0.017 to +0.081; A +0.128, B +0.076, C +0.065, D +0.056, E +0.020)**. REP without pro history: +0.020 (51), and −0.021 on E.
  - Concentrated: 20 creators; GeUnv1 alone is 20 launches (+1.46 of +4.15 SOL). Landing 20 ms later leaves +0.023 per launch.
- **Three skip signals hold out of sample (useful only for wider triggers, they hardly touch rule #2):**
  - **Bundle wallets with bad history** (the creator's glued-bundle wallets were in earlier launches that lost on the model), for creators that are NOT already "bad history": **55 launches, −0.036 each, negative in all five periods**, interval −0.062 to −0.012. This catches operators who rotate creator wallets.
  - **An outside buy already in our feed ≤ 5 ms after the create** (someone faster than our decision): 24 launches, −0.038 each (A +0.003); small n.
  - Together with FILTERS2's bad-history skip, the remaining watched launches make **+0.022 per launch out of sample (759 launches, 92/h, interval +0.010 to +0.036; positive in all five periods)** against +0.005 for all watched launches; but only **+0.006 with a 20 ms slower landing**, so too thin for live.
- **No signal improves rule #2.** Dev-buy exact amount, dev share of the bundle, creator SOL left after the create, creator's selling speed on earlier coins, bundle reuse and pro history all split rule #2 into groups of ≤ 15 out-of-sample launches with overlapping intervals. Rule #2 itself was flat today: **D 16 launches +0.007, E 10 launches −0.007 SOL each** (A +0.133, B +0.058).
- **The rest is noise or fails in-sample:**
  - Dev buy exact amount: integer vs odd amounts make no difference (+0.014 vs +0.004 out of sample). "Exactly 5.0 SOL" is +0.041 out of sample but flat on E. dev / dev_sized / dev_cap are identical in 1157 of 1159 launches that have all three: no information.
  - Creator SOL after the create < 0.1 SOL (all-in creators): −0.041 out of sample (42), but +0.019 in A.
  - Creators who sold their last coin slowly (> 30 s) or held it: −0.025 / −0.022 out of sample, but positive in A. Fast dumpers (≤ 4 s) are about break-even (+0.006).
  - REP itself (FILTERS2) faded on the newest data: **E +0.001 per launch (47 launches)**.

## Key table (S+2 PnL per launch in SOL; A = in-sample, OOS = B+C+D+E pooled)

| signal | A n: per launch | OOS n | /h | per launch | +20 ms | win | OOS total w/o best 3 | 90% CI | verdict |
|---|---|---|---|---|---|---|---|---|---|
| all watched (baseline) | 325: −0.000 | 1099 | 133 | +0.005 | −0.008 | 26% | −1.82 | −0.005 to +0.015 | |
| rule #2 (baseline) | 19: +0.133 | 58 | 7.0 | +0.033 | +0.021 | 36% | +0.21 | −0.005 to +0.077 | D +0.007, E −0.007 |
| exactly 1 prior create (on-chain) | 18: +0.045 | 63 | 7.6 | **−0.023** | −0.030 | 21% | −1.86 | −0.034 to −0.012 | loses OOS |
| 0 prior creates (exact count) | 152: −0.021 | 324 | 39.2 | +0.024 | +0.008 | 28% | +0.67 | +0.000 to +0.050 | mixed (A, D < 0) |
| pro bought creator's earlier launch | 19: +0.082 | 123 | 14.9 | **+0.033** | +0.010 | 41% | +2.16 | +0.006 to +0.060 | + in all 5 |
| REP and pro history | 10: +0.128 | 83 | 10.0 | **+0.050** | +0.023 | 45% | +2.34 | +0.017 to +0.081 | + in all 5 |
| REP without pro history | 16: +0.102 | 51 | 6.2 | +0.020 | +0.010 | 49% | +0.12 | −0.012 to +0.050 | E −0.021 |
| bundle-bad, creator not bad | 18: −0.004 | 55 | 6.7 | **−0.036** | −0.037 | 13% | −2.66 | −0.062 to −0.012 | skip; − in all 5 |
| outside buy ≤ 5 ms in feed | 12: +0.003 | 24 | 2.9 | −0.038 | −0.040 | 17% | −1.17 | −0.065 to −0.010 | skip; small n |
| creator SOL after create < 0.1 | 17: +0.019 | 42 | 5.1 | −0.041 | −0.046 | 19% | −2.30 | −0.073 to −0.012 | fails A |
| creator sold last coin > 30 s after create | 11: +0.033 | 80 | 9.7 | −0.025 | −0.032 | 18% | −2.56 | −0.036 to −0.010 | fails A |
| dev buy exactly 5.0 SOL | 16: +0.090 | 57 | 6.9 | +0.041 | +0.027 | 32% | +0.37 | +0.004 to +0.094 | E −0.001 |
| all watched minus skips (bad history, bundle-bad, early buy) | 230: +0.007 | 759 | 91.9 | +0.022 | +0.006 | 31% | +9.81 | +0.010 to +0.036 | too thin |

## Recommendation

- **Implement nothing live now.** Leave rule #2 unchanged (confidence medium-high that no create-time signal here improves it; its n is small and it was flat today).
- **Paper-test (zero cost, add to the `paper_rep.py` tally): "REP + pro history" as the stricter version of REP.** At fire time it is a hash lookup on the creator (the recorder already sees pro wallets in S..S+2 of every watched launch). Promote only with ≥ +0.03 per launch over ≥ 60 fresh launches and a positive +20 ms column. Confidence **low-medium**: positive in all five periods, but 20 creators, one of them 20 launches, and the latest period is the weakest (+0.020).
- **If any wider trigger (C6/C7/REP) is ever promoted, add two skips:** bundle-bad (cache of bundle wallet → earlier launches' modelled PnL) and "an outside buy already in the feed ≤ 5 ms after the create". Confidence medium for bundle-bad (negative in all five periods), low for the early-buy skip (24 launches).
- **Drop:** "exactly 1 earlier launch" (loses out of sample), dev-buy exact amounts, dev share, dev_sized/dev_cap, creator SOL at create, creator selling speed. Confidence medium (on-chain coverage is partial, see caveats).

## Tables

Groups (hours): A 1.55 h (325 watched, 19 rule #2), B 3.40 h (553 watched, 31 rule #2), C 0.83 h (54 watched, 1 rule #2), D 2.42 h (252 watched, 16 rule #2), E 1.62 h (240 watched, 10 rule #2)
Cells: n: S+2 PnL per launch (SOL). OOS = B+C+D+E pooled. +20 ms = landing 20 ms later. CI = bootstrap over creators.

### Baselines

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| all watched launches | 325: -0.000 | 553: +0.005 | 54: +0.039 | 252: -0.005 | 240: +0.007 | 1099 | 133.0 | +5.18 | +0.005 | -0.040 | 26% | -0.008 | -1.82 | -0.005 to +0.015 |
| all watched, create <= 150 ms | 223: +0.008 | 370: +0.009 | 33: -0.001 | 181: -0.002 | 185: +0.012 | 769 | 93.1 | +5.38 | +0.007 | -0.037 | 28% | -0.006 | -0.14 | -0.004 to +0.018 |
| rule #2 | 19: +0.133 | 31: +0.058 | 1: +0.080 | 16: +0.007 | 10: -0.007 | 58 | 7.0 | +1.91 | +0.033 | -0.018 | 36% | +0.021 | +0.21 | -0.005 to +0.077 |

### 0a. Number of the creator's PRIOR pump.fun creates (on-chain), all watched launches

Coverage: 908 of 1424 launches have the creator's on-chain history; 216 of them have a count that is only a LOWER bound (history walk capped, <= 10 creates found). Buckets use the count of the creator's pump.fun creates strictly before this create's slot.

Per group: A: 231/325 launches, exact 192, median visible history before the create 0.5 h; B: 265/553 launches, exact 212, median visible history before the create 0.7 h; C: 35/54 launches, exact 29, median visible history before the create 0.6 h; D: 169/252 launches, exact 121, median visible history before the create 0.9 h; E: 208/240 launches, exact 138, median visible history before the create 2.3 h. 'Visible history' = from the oldest transaction we classified (or the oldest signature the RPC returned) to the create; creates older than that are not counted, so '0 prior' means none in that window.

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 prior creates (first-ever) | 157: -0.022 | 154: +0.022 | 19: +0.126 | 88: -0.026 | 81: +0.034 | 342 | 41.4 | +6.24 | +0.018 | -0.043 | 27% | +0.003 | -0.76 | -0.003 to +0.044 |
| exactly 1 prior | 18: +0.045 | 22: -0.035 | 4: +0.011 | 23: -0.016 | 14: -0.027 | 63 | 7.6 | -1.48 | -0.023 | -0.048 | 21% | -0.030 | -1.86 | -0.034 to -0.012 |
| 2-3 prior | 17: +0.077 | 39: -0.008 | 7: +0.017 | 17: -0.028 | 26: +0.004 | 89 | 10.8 | -0.54 | -0.006 | -0.044 | 21% | -0.020 | -2.04 | -0.031 to +0.019 |
| 4-10 prior | 34: +0.038 | 40: -0.032 | 4: -0.003 | 38: +0.003 | 51: -0.025 | 133 | 16.1 | -2.46 | -0.018 | -0.048 | 23% | -0.027 | -4.12 | -0.037 to +0.001 |
| 11+ prior | 5: -0.016 | 10: -0.038 | 1: -0.053 | 3: +0.074 | 36: +0.021 | 50 | 6.1 | +0.55 | +0.011 | -0.027 | 24% | -0.011 | -0.69 | -0.022 to +0.043 |
| 1 prior, exact count only | 11: +0.009 | 18: -0.031 | 3: +0.032 | 18: -0.007 | 7: -0.026 | 46 | 5.6 | -0.77 | -0.017 | -0.043 | 24% | -0.023 | -1.15 | -0.029 to -0.003 |
| 0 prior, exact count only | 152: -0.021 | 146: +0.024 | 18: +0.136 | 84: -0.017 | 76: +0.041 | 324 | 39.2 | +7.67 | +0.024 | -0.040 | 28% | +0.008 | +0.67 | +0.000 to +0.050 |
| <= 1 prior | 175: -0.015 | 176: +0.015 | 23: +0.106 | 111: -0.024 | 95: +0.025 | 405 | 49.0 | +4.77 | +0.012 | -0.044 | 26% | -0.002 | -2.23 | -0.008 to +0.033 |
| >= 2 prior | 56: +0.045 | 89: -0.022 | 12: +0.004 | 58: -0.002 | 113: -0.004 | 272 | 32.9 | -2.44 | -0.009 | -0.043 | 23% | -0.022 | -4.40 | -0.024 to +0.006 |

### 0b. The same inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 prior creates (first-ever) | 2: +0.304 | 2: +0.109 | - | 1: -0.052 | - | 3 | 0.4 | +0.17 | +0.055 | -0.052 | 33% | +0.046 | +0.00 | -0.052 to +0.163 |
| exactly 1 prior | - | - | - | - | 1: -0.053 | 1 | 0.1 | -0.05 | -0.053 | -0.053 | 0% | -0.053 | +0.00 | - |
| 2-3 prior | 1: -0.050 | 2: -0.058 | - | - | - | 2 | 0.2 | -0.12 | -0.058 | -0.058 | 0% | -0.058 | +0.00 | - |
| 4-10 prior | 4: +0.261 | 2: -0.022 | - | 4: -0.015 | 4: -0.014 | 10 | 1.2 | -0.16 | -0.016 | -0.051 | 30% | -0.016 | -0.36 | -0.045 to +0.017 |
| 11+ prior | - | 1: -0.039 | - | - | 1: -0.011 | 2 | 0.2 | -0.05 | -0.025 | -0.025 | 0% | -0.032 | +0.00 | - |
| 1 prior, exact count only | - | - | - | - | 1: -0.053 | 1 | 0.1 | -0.05 | -0.053 | -0.053 | 0% | -0.053 | +0.00 | - |
| 0 prior, exact count only | 2: +0.304 | 2: +0.109 | - | 1: -0.052 | - | 3 | 0.4 | +0.17 | +0.055 | -0.052 | 33% | +0.046 | +0.00 | -0.052 to +0.163 |
| <= 1 prior | 2: +0.304 | 2: +0.109 | - | 1: -0.052 | 1: -0.053 | 4 | 0.5 | +0.11 | +0.028 | -0.052 | 25% | +0.021 | -0.05 | -0.053 to +0.163 |
| >= 2 prior | 5: +0.199 | 5: -0.040 | - | 4: -0.015 | 5: -0.013 | 14 | 1.7 | -0.33 | -0.023 | -0.048 | 21% | -0.025 | -0.53 | -0.046 to +0.003 |

### 0c. Exactly 1 prior create: split by how that prior launch did (all watched launches)

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 prior, that launch was watched by us | 7: +0.053 | 4: -0.032 | - | 5: -0.044 | 4: -0.023 | 13 | 1.6 | -0.44 | -0.034 | -0.050 | 23% | -0.051 | -0.60 | -0.066 to -0.005 |
| 1 prior, watched, its model PnL > 0 | 2: +0.311 | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 1 prior, watched, its model PnL <= 0 | 5: -0.051 | 4: -0.032 | - | 5: -0.044 | 4: -0.023 | 13 | 1.6 | -0.44 | -0.034 | -0.050 | 23% | -0.051 | -0.60 | -0.066 to -0.005 |
| 1 prior, watched, outside buys S..S+2 >= 1 SOL | 2: +0.311 | 3: -0.064 | - | - | 2: +0.008 | 5 | 0.6 | -0.18 | -0.035 | -0.011 | 40% | -0.053 | -0.27 | -0.124 to +0.029 |
| 1 prior, watched, outside buys S..S+2 < 1 SOL | 5: -0.051 | 1: +0.063 | - | 5: -0.044 | 2: -0.053 | 8 | 1.0 | -0.26 | -0.033 | -0.050 | 12% | -0.049 | -0.26 | -0.051 to -0.008 |
| 1 prior, not watched by us | 11: +0.040 | 18: -0.036 | 4: +0.011 | 18: -0.009 | 10: -0.028 | 50 | 6.1 | -1.03 | -0.021 | -0.046 | 20% | -0.025 | -1.42 | -0.031 to -0.009 |
| 1 prior, creator first sold it <= 75 slots (30 s) after create | 11: -0.016 | 14: -0.036 | 2: -0.048 | 13: -0.020 | 9: -0.022 | 38 | 4.6 | -1.06 | -0.028 | -0.048 | 13% | -0.032 | -1.28 | -0.037 to -0.018 |
| 1 prior, creator first sold it > 75 slots after create | 3: +0.091 | 5: +0.010 | - | 8: -0.024 | 5: -0.034 | 18 | 2.2 | -0.32 | -0.018 | -0.047 | 33% | -0.032 | -0.47 | -0.034 to -0.001 |
| 1 prior, creator never sold it before this create | 4: +0.178 | 3: -0.106 | 2: +0.070 | 2: +0.038 | - | 7 | 0.8 | -0.10 | -0.015 | -0.053 | 29% | -0.015 | -0.37 | -0.093 to +0.063 |

### 0d. Exactly 1 prior create, inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 prior, that launch was watched by us | - | - | - | - | 1: -0.053 | 1 | 0.1 | -0.05 | -0.053 | -0.053 | 0% | -0.053 | +0.00 | - |
| 1 prior, watched, its model PnL > 0 | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 1 prior, watched, its model PnL <= 0 | - | - | - | - | 1: -0.053 | 1 | 0.1 | -0.05 | -0.053 | -0.053 | 0% | -0.053 | +0.00 | - |
| 1 prior, watched, outside buys S..S+2 >= 1 SOL | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 1 prior, watched, outside buys S..S+2 < 1 SOL | - | - | - | - | 1: -0.053 | 1 | 0.1 | -0.05 | -0.053 | -0.053 | 0% | -0.053 | +0.00 | - |
| 1 prior, not watched by us | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 1 prior, creator first sold it <= 75 slots (30 s) after create | - | - | - | - | 1: -0.053 | 1 | 0.1 | -0.05 | -0.053 | -0.053 | 0% | -0.053 | +0.00 | - |
| 1 prior, creator first sold it > 75 slots after create | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| 1 prior, creator never sold it before this create | - | - | - | - | - | - | - | - | - | - | - | - | - | - |

### 1a. Dev buy amount, all watched launches with create <= 150 ms

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| integer SOL (1.0, 2.0, ...) | 88: +0.037 | 160: +0.017 | 15: +0.033 | 73: +0.003 | 102: +0.014 | 350 | 42.4 | +4.81 | +0.014 | -0.038 | 27% | +0.005 | +0.60 | -0.003 to +0.032 |
| half SOL (x.5) | 7: +0.089 | 20: -0.025 | 3: -0.006 | 11: +0.015 | 9: -0.104 | 43 | 5.2 | -1.29 | -0.030 | -0.050 | 23% | -0.033 | -1.99 | -0.077 to +0.012 |
| one decimal (x.1-x.9) | 11: -0.000 | 14: +0.040 | - | 5: -0.043 | 2: -0.028 | 21 | 2.5 | +0.29 | +0.014 | -0.029 | 38% | -0.020 | -0.45 | -0.024 to +0.077 |
| odd amount | 117: -0.019 | 176: +0.004 | 15: -0.034 | 92: -0.005 | 72: +0.026 | 355 | 43.0 | +1.56 | +0.004 | -0.036 | 30% | -0.012 | -2.17 | -0.010 to +0.020 |
| dev exactly 1.0 | 26: -0.034 | 47: +0.018 | 2: -0.036 | 25: -0.020 | 23: -0.046 | 97 | 11.7 | -0.79 | -0.008 | -0.050 | 20% | -0.016 | -2.45 | -0.028 to +0.016 |
| dev exactly 2.0 | 6: +0.092 | 10: -0.083 | 3: -0.036 | 6: -0.010 | 11: -0.021 | 30 | 3.6 | -1.22 | -0.041 | -0.051 | 10% | -0.050 | -1.74 | -0.072 to -0.005 |
| dev exactly 3.0 | 22: +0.076 | 42: +0.041 | 6: +0.106 | 24: -0.038 | 27: +0.071 | 99 | 12.0 | +3.38 | +0.034 | -0.024 | 37% | +0.026 | +0.03 | -0.009 to +0.086 |
| dev exactly 4.0 | 12: +0.054 | 21: +0.025 | - | 3: -0.017 | 12: +0.054 | 36 | 4.4 | +1.13 | +0.031 | -0.022 | 36% | +0.026 | -0.19 | -0.004 to +0.073 |
| dev exactly 5.0 | 16: +0.090 | 24: +0.019 | 4: +0.008 | 11: +0.172 | 18: -0.001 | 57 | 6.9 | +2.36 | +0.041 | -0.030 | 32% | +0.027 | +0.37 | +0.004 to +0.094 |

### 1b. Dev buy amount inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| integer SOL (1.0, 2.0, ...) | 17: +0.112 | 26: +0.034 | - | 13: -0.020 | 10: -0.007 | 49 | 5.9 | +0.56 | +0.011 | -0.025 | 33% | -0.000 | -0.43 | -0.019 to +0.045 |
| half SOL (x.5) | 1: +0.661 | 2: -0.047 | 1: +0.080 | 2: +0.213 | - | 5 | 0.6 | +0.41 | +0.082 | +0.080 | 60% | +0.070 | -0.09 | - |
| one decimal (x.1-x.9) | - | 2: +0.005 | - | 1: -0.053 | - | 3 | 0.4 | -0.04 | -0.014 | -0.053 | 33% | -0.037 | +0.00 | - |
| odd amount | 1: -0.053 | 1: +0.988 | - | - | - | 1 | 0.1 | +0.99 | +0.988 | +0.988 | 100% | +0.988 | +0.00 | - |
| dev exactly 1.0 | 4: +0.003 | 5: +0.005 | - | - | - | 5 | 0.6 | +0.03 | +0.005 | -0.050 | 20% | -0.003 | -0.15 | -0.072 to +0.116 |
| dev exactly 2.0 | 2: +0.430 | 1: -0.030 | - | 1: -0.052 | 2: -0.053 | 4 | 0.5 | -0.19 | -0.047 | -0.052 | 0% | -0.047 | -0.05 | -0.053 to -0.037 |
| dev exactly 3.0 | 6: +0.131 | 16: +0.064 | - | 8: -0.037 | 2: -0.053 | 26 | 3.1 | +0.62 | +0.024 | -0.011 | 38% | +0.004 | -0.27 | -0.026 to +0.084 |
| dev exactly 4.0 | 1: -0.050 | 1: +0.008 | - | 1: -0.046 | - | 2 | 0.2 | -0.04 | -0.019 | -0.019 | 50% | -0.019 | +0.00 | - |
| dev exactly 5.0 | 3: +0.086 | 2: -0.051 | - | 2: +0.076 | 5: +0.038 | 9 | 1.1 | +0.24 | +0.027 | -0.011 | 44% | +0.027 | -0.16 | -0.035 to +0.050 |

### 1c. Dev buy as a share of (dev + glued bundle), all watched launches with create <= 150 ms

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no bundle (dev share 1.0) | 99: +0.014 | 164: +0.007 | 14: -0.020 | 83: +0.018 | 107: +0.031 | 368 | 44.5 | +5.67 | +0.015 | -0.037 | 28% | -0.002 | +0.16 | -0.002 to +0.035 |
| dev share < 0.3 | 62: -0.034 | 78: +0.007 | 7: -0.049 | 30: -0.024 | 24: -0.023 | 139 | 16.8 | -1.07 | -0.008 | -0.047 | 22% | -0.010 | -3.13 | -0.027 to +0.014 |
| dev share 0.3-0.5 | 37: +0.025 | 81: +0.008 | 8: +0.032 | 46: -0.014 | 28: -0.030 | 163 | 19.7 | -0.64 | -0.004 | -0.031 | 32% | -0.016 | -2.37 | -0.026 to +0.018 |
| dev share 0.5-0.8 | 21: +0.056 | 46: +0.024 | 4: +0.085 | 21: -0.015 | 26: +0.016 | 97 | 11.7 | +1.51 | +0.016 | -0.024 | 34% | +0.004 | -0.17 | -0.008 to +0.041 |
| dev share >= 0.8 (with bundle) | 4: +0.071 | 1: -0.050 | - | 1: -0.045 | - | 2 | 0.2 | -0.10 | -0.048 | -0.048 | 0% | -0.048 | +0.00 | - |

### 1d. Dev share inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| dev share < 0.3 | 6: +0.103 | 5: +0.005 | - | 1: -0.052 | 2: -0.053 | 8 | 1.0 | -0.13 | -0.016 | -0.051 | 12% | -0.022 | -0.31 | -0.066 to +0.069 |
| dev share 0.3-0.5 | 6: +0.287 | 20: +0.046 | 1: +0.080 | 7: +0.063 | 1: -0.053 | 29 | 3.5 | +1.39 | +0.048 | -0.011 | 45% | +0.030 | +0.36 | +0.000 to +0.094 |
| dev share 0.5-0.8 | 7: +0.025 | 6: +0.142 | - | 8: -0.035 | 7: +0.013 | 21 | 2.5 | +0.66 | +0.031 | -0.011 | 33% | +0.024 | -0.64 | -0.046 to +0.159 |
| dev share >= 0.8 (with bundle) | - | - | - | - | - | - | - | - | - | - | - | - | - | - |

dev / dev_sized / dev_cap fields: {'dev = dev_sized = dev_cap': 1157, 'dev_cap missing': 265, 'differ': 2}


Creator SOL known for 998 of 1424 launches.

### 2a. Creator wallet SOL at create (create tx pre/post balance), all watched launches with create <= 150 ms

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| creator SOL after create < 0.1 | 17: +0.019 | 17: +0.006 | 4: -0.052 | 7: -0.051 | 14: -0.090 | 42 | 5.1 | -1.72 | -0.041 | -0.051 | 19% | -0.046 | -2.30 | -0.073 to -0.012 |
| after create 0.1-1 | 47: -0.008 | 48: +0.014 | 8: -0.055 | 39: +0.013 | 45: +0.058 | 140 | 16.9 | +3.34 | +0.024 | -0.041 | 27% | +0.004 | -0.66 | -0.006 to +0.060 |
| after create 1-5 | 41: -0.019 | 48: +0.016 | 1: -0.329 | 42: -0.022 | 38: +0.048 | 129 | 15.6 | +1.34 | +0.010 | -0.029 | 30% | -0.005 | -2.06 | -0.019 to +0.046 |
| after create 5-20 | 31: +0.047 | 26: +0.035 | 7: -0.008 | 27: -0.023 | 24: +0.009 | 84 | 10.2 | +0.46 | +0.006 | -0.039 | 29% | -0.004 | -0.68 | -0.013 to +0.025 |
| after create >= 20 | 35: +0.051 | 51: -0.009 | 4: +0.147 | 20: -0.003 | 48: -0.017 | 123 | 14.9 | -0.75 | -0.006 | -0.039 | 22% | -0.014 | -2.35 | -0.028 to +0.017 |
| spent >= 90% of its SOL | 23: +0.005 | 19: +0.018 | 5: -0.060 | 15: -0.085 | 21: -0.035 | 60 | 7.3 | -1.98 | -0.033 | -0.049 | 25% | -0.036 | -2.78 | -0.063 to -0.005 |
| spent 50-90% | 50: +0.001 | 57: +0.001 | 7: -0.089 | 45: +0.019 | 43: +0.104 | 152 | 18.4 | +4.78 | +0.031 | -0.042 | 26% | +0.007 | -0.73 | -0.004 to +0.074 |
| spent < 50% (keeps most) | 98: +0.023 | 114: +0.014 | 12: +0.040 | 75: -0.014 | 105: -0.011 | 306 | 37.0 | -0.13 | -0.000 | -0.037 | 27% | -0.010 | -1.88 | -0.012 to +0.011 |

### 2b. The same inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| creator SOL after create < 0.1 | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| after create 0.1-1 | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| after create 1-5 | 4: +0.196 | - | - | - | - | - | - | - | - | - | - | - | - | - |
| after create 5-20 | 3: +0.187 | 3: -0.070 | - | 3: +0.011 | 3: -0.001 | 9 | 1.1 | -0.18 | -0.020 | -0.053 | 22% | -0.020 | -0.36 | -0.054 to +0.018 |
| after create >= 20 | 6: +0.193 | 4: -0.023 | - | 3: -0.051 | 5: -0.024 | 12 | 1.5 | -0.36 | -0.030 | -0.044 | 17% | -0.032 | -0.37 | -0.043 to -0.017 |
| spent >= 90% of its SOL | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| spent 50-90% | 1: -0.060 | - | - | - | - | - | - | - | - | - | - | - | - | - |
| spent < 50% (keeps most) | 12: +0.214 | 7: -0.043 | - | 6: -0.020 | 8: -0.015 | 21 | 2.5 | -0.55 | -0.026 | -0.049 | 19% | -0.027 | -0.75 | -0.042 to -0.008 |

### 3a. The creator's selling of its EARLIER coins (on-chain, creator wallet only, sells before this create), all watched

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| last prior coin: creator first sold <= 10 slots (4 s) | 20: +0.046 | 22: -0.014 | 2: -0.033 | 19: +0.029 | 38: +0.008 | 81 | 9.8 | +0.50 | +0.006 | -0.045 | 28% | -0.010 | -1.35 | -0.026 to +0.039 |
| last prior coin: first sold 11-75 slots (4-30 s) | 32: +0.012 | 45: -0.023 | 8: +0.022 | 30: -0.025 | 59: -0.002 | 142 | 17.2 | -1.74 | -0.012 | -0.036 | 22% | -0.026 | -3.20 | -0.030 to +0.006 |
| last prior coin: first sold > 75 slots (> 30 s) | 11: +0.033 | 31: -0.028 | - | 25: -0.010 | 24: -0.036 | 80 | 9.7 | -1.99 | -0.025 | -0.050 | 18% | -0.032 | -2.56 | -0.036 to -0.010 |
| last prior coin: creator never sold (holder) | 11: +0.149 | 13: -0.038 | 6: -0.002 | 7: -0.009 | 6: -0.020 | 32 | 3.9 | -0.69 | -0.022 | -0.046 | 22% | -0.025 | -1.12 | -0.041 to -0.001 |
| last prior coin: >= 90% sold within 30 s | 46: +0.008 | 62: -0.035 | 10: +0.011 | 45: -0.004 | 92: -0.003 | 209 | 25.3 | -2.54 | -0.012 | -0.038 | 22% | -0.026 | -4.50 | -0.031 to +0.006 |
| last prior coin: < 50% sold within 30 s | 20: +0.040 | 43: -0.033 | 3: -0.042 | 34: -0.006 | 30: -0.032 | 110 | 13.3 | -2.69 | -0.024 | -0.049 | 19% | -0.030 | -3.26 | -0.034 to -0.012 |
| median over last 5 prior coins: first sell <= 75 slots | 56: +0.040 | 69: -0.018 | 10: +0.011 | 50: -0.010 | 96: -0.000 | 225 | 27.2 | -1.66 | -0.007 | -0.037 | 24% | -0.020 | -3.62 | -0.025 to +0.010 |
| median over last 5 prior coins: first sell > 75 slots / never | 18: +0.060 | 42: -0.035 | 6: -0.002 | 31: -0.000 | 31: -0.025 | 110 | 13.3 | -2.26 | -0.021 | -0.049 | 20% | -0.029 | -2.94 | -0.032 to -0.008 |

### 3b. The same inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| last prior coin: creator first sold <= 10 slots (4 s) | 3: +0.337 | - | - | 1: -0.049 | 4: -0.014 | 5 | 0.6 | -0.11 | -0.021 | -0.053 | 20% | -0.022 | -0.11 | -0.053 to +0.040 |
| last prior coin: first sold 11-75 slots (4-30 s) | 1: +0.044 | 4: -0.040 | - | 3: -0.003 | 2: -0.032 | 9 | 1.1 | -0.23 | -0.026 | -0.046 | 22% | -0.026 | -0.32 | -0.053 to +0.004 |
| last prior coin: first sold > 75 slots (> 30 s) | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| last prior coin: creator never sold (holder) | 1: -0.060 | 1: -0.039 | - | - | - | 1 | 0.1 | -0.04 | -0.039 | -0.039 | 0% | -0.053 | +0.00 | - |
| last prior coin: >= 90% sold within 30 s | 4: +0.264 | 4: -0.040 | - | 4: -0.015 | 6: -0.020 | 14 | 1.7 | -0.34 | -0.024 | -0.051 | 21% | -0.025 | -0.54 | -0.046 to +0.002 |
| last prior coin: < 50% sold within 30 s | 1: -0.060 | - | - | - | - | - | - | - | - | - | - | - | - | - |
| median over last 5 prior coins: first sell <= 75 slots | 5: +0.199 | 4: -0.040 | - | 4: -0.015 | 5: -0.013 | 13 | 1.6 | -0.29 | -0.022 | -0.049 | 23% | -0.022 | -0.49 | -0.046 to +0.006 |
| median over last 5 prior coins: first sell > 75 slots / never | - | 1: -0.039 | - | - | 1: -0.053 | 2 | 0.2 | -0.09 | -0.046 | -0.046 | 0% | -0.053 | +0.00 | - |

### 0e. Prior launches counted from OUR LOGS only (earlier watched launches by the creator, >= 550 slots earlier), all watched

Our logs are gapped (5.8 h before today + today's continuous paper log), so this counts only launches we happened to watch.

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 earlier watched launches | 231: -0.006 | 388: +0.014 | 40: +0.051 | 148: -0.009 | 123: +0.025 | 699 | 84.6 | +9.26 | +0.013 | -0.043 | 26% | -0.001 | +2.26 | +0.001 to +0.027 |
| exactly 1 | 43: +0.028 | 64: -0.002 | 5: +0.025 | 26: -0.043 | 26: -0.019 | 121 | 14.6 | -1.64 | -0.014 | -0.046 | 26% | -0.021 | -2.98 | -0.034 to +0.006 |
| 2-3 | 24: +0.033 | 63: -0.018 | 2: -0.051 | 25: -0.034 | 22: -0.034 | 112 | 13.6 | -2.85 | -0.025 | -0.044 | 21% | -0.032 | -3.51 | -0.039 to -0.012 |
| 4-10 | 25: -0.036 | 34: -0.042 | 7: +0.007 | 49: +0.030 | 37: -0.016 | 127 | 15.4 | -0.48 | -0.004 | -0.027 | 28% | -0.011 | -1.90 | -0.022 to +0.017 |
| 11+ | 2: +0.041 | 4: -0.022 | - | 4: +0.119 | 32: +0.016 | 40 | 4.8 | +0.89 | +0.022 | -0.014 | 32% | -0.012 | -0.34 | -0.024 to +0.080 |
| exactly 1, it made money on our model | 12: +0.156 | 16: +0.146 | 1: -0.020 | 3: -0.016 | 6: -0.121 | 26 | 3.1 | +1.55 | +0.059 | -0.003 | 50% | +0.037 | +0.37 | +0.004 to +0.120 |
| exactly 1, it lost on our model | 31: -0.021 | 48: -0.052 | 4: +0.037 | 23: -0.046 | 20: +0.011 | 95 | 11.5 | -3.18 | -0.034 | -0.050 | 19% | -0.037 | -4.08 | -0.051 to -0.017 |

### 0f. The same inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 0 earlier watched launches | 8: +0.189 | 16: +0.094 | - | 4: -0.016 | - | 20 | 2.4 | +1.43 | +0.072 | -0.039 | 35% | +0.062 | -0.20 | -0.009 to +0.170 |
| exactly 1 | 5: +0.052 | 5: +0.080 | - | 2: +0.121 | 2: -0.053 | 9 | 1.1 | +0.54 | +0.060 | +0.008 | 56% | +0.035 | -0.16 | -0.009 to +0.136 |
| 2-3 | 3: +0.373 | 6: +0.008 | - | 4: -0.100 | 1: -0.053 | 11 | 1.3 | -0.40 | -0.037 | -0.042 | 27% | -0.054 | -0.67 | -0.078 to +0.008 |
| 4-10 | 3: -0.124 | 4: -0.039 | 1: +0.080 | 6: +0.056 | 6: -0.002 | 17 | 2.1 | +0.25 | +0.014 | -0.011 | 29% | +0.009 | -0.28 | -0.031 to +0.072 |
| 11+ | - | - | - | - | 1: +0.102 | 1 | 0.1 | +0.10 | +0.102 | +0.102 | 100% | +0.102 | +0.00 | - |
| exactly 1, it made money on our model | 1: +0.053 | 2: +0.249 | - | - | - | 2 | 0.2 | +0.50 | +0.249 | +0.249 | 100% | +0.141 | +0.00 | - |
| exactly 1, it lost on our model | 4: +0.051 | 3: -0.033 | - | 2: +0.121 | 2: -0.053 | 7 | 0.8 | +0.04 | +0.005 | -0.050 | 43% | +0.005 | -0.21 | -0.043 to +0.065 |

### 3c. Creator + bundle selling within S..S+2 of the creator's last earlier WATCHED launch (block recordings), all watched

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| earlier watched launch: creator/bundle sold in S..S+2 (last one) | 4: +0.406 | 4: -0.055 | 2: -0.072 | 2: +0.069 | 2: -0.030 | 10 | 1.2 | -0.29 | -0.029 | -0.030 | 30% | -0.029 | -0.49 | -0.074 to +0.018 |
| earlier watched launch: no creator/bundle sell in S..S+2 (last one) | 90: -0.005 | 161: -0.016 | 12: +0.018 | 102: -0.001 | 115: -0.011 | 390 | 47.2 | -3.79 | -0.010 | -0.037 | 26% | -0.020 | -5.64 | -0.023 to +0.003 |

### 3d. The same inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| earlier watched launch: creator/bundle sold in S..S+2 (last one) | 1: +1.073 | - | - | 1: -0.011 | - | 1 | 0.1 | -0.01 | -0.011 | -0.011 | 0% | -0.011 | +0.00 | - |
| earlier watched launch: no creator/bundle sell in S..S+2 (last one) | 10: -0.006 | 15: +0.020 | 1: +0.080 | 11: +0.017 | 10: -0.007 | 37 | 4.5 | +0.49 | +0.013 | -0.011 | 38% | -0.001 | -0.36 | -0.022 to +0.046 |

Bundle wallets: 1752 distinct; 202 appear in bundles of >= 2 different creators; 788 launches have a glued bundle.

### 4a. Bundle wallets reused across launches, all watched launches

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| has bundle, no wallet seen in an earlier bundle | 103: -0.013 | 174: +0.021 | 19: +0.148 | 60: -0.031 | 43: +0.007 | 296 | 35.8 | +4.88 | +0.016 | -0.045 | 28% | +0.005 | +0.40 | -0.004 to +0.039 |
| bundle wallet seen in an earlier bundle | 80: -0.001 | 149: -0.017 | 13: +0.003 | 86: -0.003 | 61: -0.032 | 309 | 37.4 | -4.80 | -0.016 | -0.038 | 27% | -0.024 | -6.45 | -0.029 to -0.003 |
| ... in an earlier bundle of ANOTHER creator | 30: -0.007 | 50: -0.026 | 6: -0.033 | 42: -0.019 | 26: -0.032 | 124 | 15.0 | -3.13 | -0.025 | -0.039 | 23% | -0.033 | -4.02 | -0.045 to -0.005 |
| bundle-REP: earlier launches with these wallets net > 0 | 23: +0.031 | 41: +0.047 | 4: +0.036 | 37: +0.036 | 24: -0.028 | 106 | 12.8 | +2.73 | +0.026 | -0.011 | 45% | +0.009 | +1.08 | +0.001 to +0.052 |
| bundle-bad: earlier launches with these wallets net <= 0 | 55: -0.013 | 97: -0.043 | 9: -0.012 | 44: -0.033 | 37: -0.035 | 187 | 22.6 | -7.06 | -0.038 | -0.047 | 17% | -0.042 | -7.91 | -0.049 to -0.026 |
| bundle-REP from OTHER creators' launches only | 5: -0.044 | 10: -0.027 | 1: -0.053 | 14: +0.029 | 7: +0.011 | 32 | 3.9 | +0.17 | +0.005 | -0.018 | 44% | -0.020 | -0.61 | -0.052 to +0.048 |
| bundle-bad from OTHER creators' launches only | 24: +0.002 | 34: -0.023 | 5: -0.029 | 23: -0.046 | 19: -0.047 | 81 | 9.8 | -2.89 | -0.036 | -0.044 | 16% | -0.037 | -3.62 | -0.053 to -0.015 |

### 4c. Does bundle history add anything for creators WITHOUT their own history? (all watched)

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| first-time creator, bundle-REP (wallets' earlier launches net > 0) | 5: -0.044 | 9: -0.032 | 1: -0.053 | 6: +0.023 | 3: -0.007 | 19 | 2.3 | -0.23 | -0.012 | -0.050 | 32% | -0.046 | -0.86 | -0.055 to +0.034 |
| first-time creator, bundle-bad (net <= 0) | 17: -0.034 | 20: -0.009 | 4: -0.046 | 17: -0.046 | 12: -0.060 | 53 | 6.4 | -1.86 | -0.035 | -0.044 | 13% | -0.036 | -2.55 | -0.063 to -0.010 |
| first-time creator, bundle wallets all new | 103: -0.013 | 170: +0.023 | 19: +0.148 | 55: -0.030 | 36: +0.010 | 280 | 33.9 | +5.40 | +0.019 | -0.042 | 29% | +0.007 | +0.92 | -0.001 to +0.043 |

### 4b. The same inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| has bundle, no wallet seen in an earlier bundle | 7: +0.223 | 16: +0.094 | - | 4: -0.016 | - | 20 | 2.4 | +1.43 | +0.072 | -0.039 | 35% | +0.062 | -0.20 | -0.009 to +0.170 |
| bundle wallet seen in an earlier bundle | 12: +0.080 | 15: +0.020 | 1: +0.080 | 12: +0.015 | 10: -0.007 | 38 | 4.6 | +0.48 | +0.013 | -0.011 | 37% | -0.001 | -0.37 | -0.022 to +0.045 |
| ... in an earlier bundle of ANOTHER creator | 1: -0.053 | - | - | 4: +0.001 | 2: +0.025 | 6 | 0.7 | +0.05 | +0.009 | +0.045 | 50% | -0.002 | -0.47 | -0.179 to +0.143 |
| bundle-REP: earlier launches with these wallets net > 0 | 7: +0.116 | 8: +0.060 | 1: +0.080 | 9: -0.002 | 7: +0.013 | 25 | 3.0 | +0.63 | +0.025 | -0.011 | 40% | +0.007 | -0.18 | -0.022 to +0.078 |
| bundle-bad: earlier launches with these wallets net <= 0 | 5: +0.028 | 7: -0.027 | - | 3: +0.065 | 3: -0.053 | 13 | 1.6 | -0.15 | -0.011 | -0.050 | 31% | -0.017 | -0.46 | -0.040 to +0.026 |
| bundle-REP from OTHER creators' launches only | 1: -0.053 | - | - | 4: +0.001 | 1: +0.102 | 5 | 0.6 | +0.11 | +0.021 | +0.102 | 60% | +0.009 | -0.42 | - |
| bundle-bad from OTHER creators' launches only | - | - | - | - | 1: -0.053 | 1 | 0.1 | -0.05 | -0.053 | -0.053 | 0% | -0.053 | +0.00 | - |

Pro wallets seen buying in S..S+2 of watched launches: 9qz7cW 47, AHwJSn 46, dKMjeG 37, 3yrJE1 22, 4yFAz7 18, 9XPMCa 14, 2EsRia 7

### 5a. Pro snipers on the creator's EARLIER watched launches, all watched

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| creator has earlier watched launches, none bought by a pro in S..S+2 | 75: -0.005 | 127: -0.030 | 7: -0.029 | 59: -0.031 | 84: -0.026 | 277 | 33.5 | -8.09 | -0.029 | -0.046 | 19% | -0.034 | -8.99 | -0.039 to -0.019 |
| a pro bought one of the creator's earlier watched launches in S..S+2 | 19: +0.082 | 38: +0.027 | 7: +0.039 | 45: +0.041 | 33: +0.026 | 123 | 14.9 | +4.01 | +0.033 | -0.011 | 41% | +0.010 | +2.16 | +0.006 to +0.060 |
| ... and those launches were net > 0 on our model | 10: +0.128 | 20: +0.059 | 4: +0.025 | 38: +0.051 | 25: +0.020 | 87 | 10.5 | +3.72 | +0.043 | -0.011 | 44% | +0.017 | +1.90 | +0.009 to +0.074 |
| ... and those launches were net <= 0 | 9: +0.030 | 18: -0.008 | 3: +0.057 | 7: -0.015 | 8: +0.046 | 36 | 4.4 | +0.29 | +0.008 | -0.027 | 33% | -0.008 | -0.69 | -0.024 to +0.051 |

### 5b. The same inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| creator has earlier watched launches, none bought by a pro in S..S+2 | 7: -0.055 | 13: +0.019 | - | 3: +0.065 | 3: -0.053 | 19 | 2.3 | +0.28 | +0.015 | -0.039 | 32% | -0.001 | -0.42 | -0.022 to +0.058 |
| a pro bought one of the creator's earlier watched launches in S..S+2 | 4: +0.348 | 2: +0.027 | 1: +0.080 | 9: -0.002 | 7: +0.013 | 19 | 2.3 | +0.20 | +0.011 | -0.011 | 42% | -0.001 | -0.33 | -0.047 to +0.066 |
| ... and those launches were net > 0 on our model | 3: +0.373 | 2: +0.027 | 1: +0.080 | 8: -0.001 | 7: +0.013 | 18 | 2.2 | +0.21 | +0.012 | -0.010 | 44% | +0.000 | -0.32 | -0.051 to +0.067 |
| ... and those launches were net <= 0 | 1: +0.271 | - | - | 1: -0.011 | - | 1 | 0.1 | -0.01 | -0.011 | -0.011 | 0% | -0.011 | +0.00 | - |

### 5d. Overlap with creator reputation (REP), all watched

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| REP (FILTERS2, with a 550-slot lag) | 26: +0.112 | 39: +0.074 | 3: +0.065 | 45: +0.045 | 47: +0.001 | 134 | 16.2 | +5.18 | +0.039 | -0.011 | 46% | +0.018 | +3.36 | +0.014 to +0.063 |
| REP and a pro bought an earlier launch | 10: +0.128 | 19: +0.076 | 3: +0.065 | 36: +0.056 | 25: +0.020 | 83 | 10.0 | +4.15 | +0.050 | -0.011 | 45% | +0.023 | +2.34 | +0.017 to +0.081 |
| REP, no pro on any earlier launch | 16: +0.102 | 20: +0.073 | - | 9: +0.003 | 22: -0.021 | 51 | 6.2 | +1.02 | +0.020 | -0.011 | 49% | +0.010 | +0.12 | -0.012 to +0.050 |
| bad history, but a pro bought an earlier launch | 9: +0.030 | 19: -0.022 | 4: +0.019 | 9: -0.019 | 8: +0.046 | 40 | 4.8 | -0.14 | -0.004 | -0.032 | 32% | -0.018 | -1.11 | -0.030 to +0.032 |
| REP or pro bought an earlier launch | 35: +0.091 | 58: +0.043 | 7: +0.039 | 54: +0.034 | 55: +0.007 | 174 | 21.1 | +5.03 | +0.029 | -0.011 | 43% | +0.010 | +3.18 | +0.007 to +0.050 |
| REP or pro history, outside rule #2 (added launches) | 28: +0.073 | 50: +0.040 | 6: +0.032 | 45: +0.042 | 48: +0.007 | 149 | 18.0 | +4.40 | +0.030 | -0.011 | 44% | +0.010 | +2.55 | +0.006 to +0.053 |

### 5e. Skip signals beyond FILTERS2's bad history, all watched

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bad history (FILTERS2 skip) | 68: -0.025 | 126: -0.045 | 11: -0.011 | 59: -0.035 | 70: -0.020 | 266 | 32.2 | -9.25 | -0.035 | -0.048 | 16% | -0.040 | -10.24 | -0.043 to -0.027 |
| bundle-bad, creator NOT bad history | 18: -0.004 | 21: -0.011 | 4: -0.046 | 17: -0.046 | 13: -0.060 | 55 | 6.7 | -1.96 | -0.036 | -0.044 | 13% | -0.037 | -2.66 | -0.062 to -0.012 |
| early outside buy <= 5 ms, creator NOT bad history | 9: +0.017 | 9: -0.037 | - | 8: -0.002 | 2: -0.032 | 19 | 2.3 | -0.41 | -0.022 | -0.031 | 16% | -0.025 | -0.68 | -0.044 to +0.004 |
| any skip: bad history OR bundle-bad OR early buy <= 5 ms | 95: -0.017 | 156: -0.040 | 15: -0.020 | 84: -0.034 | 85: -0.026 | 340 | 41.2 | -11.63 | -0.034 | -0.047 | 15% | -0.038 | -12.72 | -0.042 to -0.027 |
| none of the skips | 230: +0.007 | 397: +0.022 | 39: +0.062 | 168: +0.009 | 155: +0.026 | 759 | 91.9 | +16.82 | +0.022 | -0.035 | 31% | +0.006 | +9.81 | +0.010 to +0.036 |

### 5f. The same skips inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| bad history (FILTERS2 skip) | 5: +0.028 | 7: -0.027 | - | 4: +0.046 | 3: -0.053 | 14 | 1.7 | -0.16 | -0.011 | -0.050 | 29% | -0.016 | -0.47 | -0.038 to +0.024 |
| bundle-bad, creator NOT bad history | - | - | - | - | - | - | - | - | - | - | - | - | - | - |
| early outside buy <= 5 ms, creator NOT bad history | - | 1: -0.053 | - | 1: -0.052 | - | 2 | 0.2 | -0.10 | -0.052 | -0.052 | 0% | -0.052 | +0.00 | - |
| any skip: bad history OR bundle-bad OR early buy <= 5 ms | 5: +0.028 | 8: -0.030 | - | 5: +0.026 | 3: -0.053 | 16 | 1.9 | -0.26 | -0.017 | -0.051 | 25% | -0.021 | -0.57 | -0.040 to +0.017 |
| none of the skips | 14: +0.170 | 23: +0.088 | 1: +0.080 | 11: -0.002 | 7: +0.013 | 42 | 5.1 | +2.18 | +0.052 | -0.011 | 40% | +0.037 | +0.48 | +0.001 to +0.115 |

### 5c. Context only (not usable at create): launches where a pro bought in S..S+2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| this launch: a pro buys in S..S+2 (OUTCOME, look-ahead; context only) | 37: +0.158 | 72: +0.104 | 4: +0.141 | 34: +0.076 | 21: +0.108 | 131 | 15.9 | +12.89 | +0.098 | +0.008 | 53% | +0.049 | +9.08 | +0.061 to +0.142 |
| this launch: no pro buys in S..S+2 (OUTCOME, context only) | 288: -0.021 | 481: -0.010 | 50: +0.031 | 218: -0.018 | 219: -0.002 | 968 | 117.2 | -7.71 | -0.008 | -0.045 | 23% | -0.016 | -13.98 | -0.017 to +0.002 |

### 6a. Outside buys already in our feed within 5 ms of the create (not creator/bundle wallets), all watched launches

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no outside buy in the feed <= 5 ms after the create | 313: -0.001 | 541: +0.006 | 54: +0.039 | 242: -0.004 | 238: +0.008 | 1075 | 130.1 | +6.08 | +0.006 | -0.040 | 27% | -0.007 | -0.92 | -0.004 to +0.016 |
| >= 1 outside buy <= 5 ms | 12: +0.003 | 12: -0.040 | - | 10: -0.036 | 2: -0.032 | 24 | 2.9 | -0.90 | -0.038 | -0.038 | 17% | -0.040 | -1.17 | -0.065 to -0.010 |
| >= 1 outside buy <= 3 ms | 10: +0.008 | 10: -0.043 | - | 6: -0.039 | - | 16 | 1.9 | -0.66 | -0.041 | -0.038 | 12% | -0.042 | -0.84 | -0.076 to -0.007 |
| >= 1 outside buy <= 5 ms with >= 0.5 SOL | 9: -0.012 | 10: -0.035 | - | 8: -0.035 | 1: -0.011 | 19 | 2.3 | -0.64 | -0.034 | -0.031 | 21% | -0.037 | -0.91 | -0.067 to -0.001 |

### 6b. The same inside rule #2

| variant | A (n: per launch) | B | C | D | E | OOS n | /h | total | per launch | median | win | per launch +20 ms | total w/o best 3 | 90% CI (creators) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| no outside buy in the feed <= 5 ms after the create | 19: +0.133 | 29: +0.063 | 1: +0.080 | 15: +0.011 | 10: -0.007 | 55 | 6.7 | +2.01 | +0.037 | -0.011 | 36% | +0.024 | +0.31 | -0.002 to +0.085 |
| >= 1 outside buy <= 5 ms | - | 2: -0.022 | - | 1: -0.052 | - | 3 | 0.4 | -0.10 | -0.032 | -0.052 | 33% | -0.032 | +0.00 | -0.052 to -0.012 |
| >= 1 outside buy <= 3 ms | - | 1: +0.008 | - | 1: -0.052 | - | 2 | 0.2 | -0.04 | -0.022 | -0.022 | 50% | -0.022 | +0.00 | - |
| >= 1 outside buy <= 5 ms with >= 0.5 SOL | - | 2: -0.022 | - | 1: -0.052 | - | 3 | 0.4 | -0.10 | -0.032 | -0.052 | 33% | -0.032 | +0.00 | -0.052 to -0.012 |

## How it was measured

- **Launches and model.** The same priced watched launches as FILTERS.md / FILTERS2.md (base filter + close leader; A, B, C, D) plus **240 new launches from the live paper engine after D** (group **E**, 10-21 12:37 → ~14:15 UTC, 1.62 h; `f3_rows_e.py`, priced from a read-only COPY of the paper_c6 loop's recordings, no RPC). The model is unchanged (`filters.py` `run()`: 1.5 SOL buy, landing T by leader class BAM 20 / Jito-client 35 / Harmonic 32 / other 35 ms, +20 ms pessimistic column, 15% cap, prio 0.011, tips by class, sell at the end of S+2).
- **Periods.** A = in-sample (10-20 evening). B, C, D, E out-of-sample. All signals below were fixed before looking at B–E. Thresholds are natural round numbers (0/1/2–3/4–10/11+, 30 s, 0.5 SOL, 5 ms); nothing was tuned. The "OOS" columns pool B+C+D+E.
- **No look-ahead.** Every history feature uses only (a) earlier watched launches whose create was ≥ 550 slots (~2 min) before this create (time for S+2 to settle and be priced), or (b) on-chain transactions with a slot before this create's slot.
- **Signals.**
  0. **Prior pump.fun creates (on-chain, `creator_creates.py`).** For each creator wallet: its signatures (publicnode; one api.mainnet-beta page further back when publicnode's list does not reach the creator's first watched launch), then the creator's successful transactions before its last watched launch, newest first, each fetched with `getTransaction` (publicnode) and classified by the instructions logged by the pump program itself (`Create*` = a launch; `Sell*`/`Buy*`). Prior creates = `Create*` transactions with slot < S. Also in-log counts (earlier watched launches only).
  1. **Dev buy:** exact amount (integer SOL / x.5 / one decimal / odd), each common integer amount, dev as a share of (dev + glued bundle), and the engine's dev / dev_sized / dev_cap fields.
  2. **Creator SOL at create:** the create tx's pre/post balance of the creator (from the same `getTransaction`).
  3. **Creator selling of its earlier coins:** for the creator's last ≤ 5 prior creates (on-chain): slots from the create to the creator's first sell of that mint, and the share of the creator's create-tx tokens sold within 75 slots (~30 s); only sells before this create count. Plus, from block recordings, whether the creator or its bundle wallets sold in S..S+2 of the creator's last earlier watched launch.
  4. **Bundle wallets reused:** the glued-bundle wallets (block recording) of this launch vs every earlier launch's bundle wallets; "bundle-REP"/"bundle-bad" = the earlier launches sharing a wallet are net >0 / ≤0 on the model (settled ones only).
  5. **Pro wallets on the creator's earlier launches:** did dKMjeG, 4yFAz7, 9XPMCa, 3yrJE1, AHwJSn, 2EsRia or 9qz7cW buy in S..S+2 of one of the creator's earlier WATCHED launches (block recordings), and how those launches did.
  6. **Early demand before we fire:** outside buys (not the creator, not its glued-bundle wallets, not us) already in our feed (`RACE obs outs`) ≤ 5 ms (and ≤ 3 ms) after the create. The engine decides at ~1–6 ms (median ~3.3 ms, `decide at_ms`, A–C), so only these could be used.
- **Columns.** n: S+2 PnL per launch per period; OOS pooled: n, launches/h, total S+2 SOL, per launch, median, win rate, per launch if we land 20 ms later, total without the 3 best launches, bootstrap 90% interval of the per-launch mean resampling **creators** (2000x).

## Caveats (labelled)

- **On-chain prior-create counts are partial (measured).** Public RPC limits: publicnode's address index keeps ~23 h and its transaction store about a day; api.mainnet-beta has full history but rate-limits hard (~25% errors), so it was used only for one signature page when publicnode's list did not reach the creator's first watched launch. Each creator's walk was capped at 60 classified transactions (newest first, from its last watched launch; the first 83 creators, mostly today's, were walked with a cap of 150–220). 914 of 915 creators were fetched (~18.6k calls). Consequences: for active wallets the visible history is short (median 0.5–2.3 h before the create); "0 prior" means "none in the visible window"; "exact" means the walk reached the oldest signature the RPC returned, which for older wallets can be publicnode's ~23 h edge rather than the wallet's first transaction; 516 launches have no usable count (walk never got behind the create) and 216 only a lower bound (reported separately in the "exact count only" rows).
- **In-sample coverage (measured).** A has counts for 231 of 325 launches (B 265/553, C 35/54, D 169/252, E 208/240), so the buckets were judged on A first; "exactly 1 prior" looked good on A (+0.045) and failed on B, D, E.
- **Selling speed is the creator wallet only (measured).** Bundle wallets' sells of earlier coins would need their own histories (not fetched). The in-log check (3c) uses creator + bundle sells within S..S+2 only.
- **Pro history only sees launches we watched (measured).** A pro buying a creator's coin that we did not watch is invisible; "pro history" therefore also implies "we watched an earlier launch of this creator", so it overlaps heavily with REP (table 5d).
- **Landing model (inference).** Same as FILTERS2: most of the added launches are not rule #2 shapes, and their landing time is the per-leader-type median, not a measurement.
- **Small n (measured).** Inside rule #2 almost every split has fewer than 10 out-of-sample launches per side; nothing inside rule #2 is distinguishable from noise.
- **REP itself weakened on the newest data (measured).** With a 550-slot settle lag, REP on E (12:37–14:15) is +0.001 SOL per launch over 47 launches (D +0.045, A +0.112). Any history-based trigger should be judged on fresh paper data, not on this table.

## Reproduce (host only; read-only; public RPC ≤ 3 threads)

```
W=/tmp/.../scratchpad                       # FILTERS/FILTERS2 work dirs (filt/, f2/) + f3/
cp $W/paper_c6/{launches_ready.json,leaders.json} $W/f3/paper/ && cp -r $W/paper_c6/rec $W/f3/paper/   # read-only COPY of the paper loop
python3 ops/research/f3_rows_e.py $W/f3/paper $W/run1/tipmap.json          # group E (12:37 UTC -> end of copy), no RPC
python3 ops/research/creator_creates.py $W/f3/cc.json $W/f3/creators_launches.json 28 $W/f3/prio.json   # ~26 min, ~18.6k calls
python3 ops/research/filters3.py > tables.md                               # all tables; also writes ops/research/filters3_rows.json
```

`creators_launches.json` = {creator: [create slots]} of every priced launch (A–E); `prio.json` = optional order (D/E creators first).

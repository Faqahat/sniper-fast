# REARM-CREATOR: skip a re-arm when the creator holds >= X% (11-04)

Verdict: DROP as a live flag. Fails DEV at every X. ann.cr_pct / cr_hold / cr_big already log on every re-arm arm (dip34), so a log-only version is already running.

Data: 1038 real re-arm fills r38-r51 (realized P&L joined by window w). cr_pct comes from ann.cr_pct; r38 (58 fills) was rebuilt from the raw recording (recon.py checked on 390 r39/r40 arms: 99% on the same side of 6%).
Days: DEV 2.33, VAL 0.86, HOLD ~1.25. Re-arm baseline: DEV +6.06 (451), VAL +0.03 (303), HOLD +0.29 (284).

SAVED = minus the real P&L of the blocked fills (positive = the filter helps). Units: SOL.

| rule | DEV n / saved / w/o top5 / per day | VAL n / saved / w/o5 / per day | HOLD n / saved / w/o5 / per day |
|---|---|---|---|
| cr>=3  | 184 / -0.88 / -2.01 / -0.38 | 126 / -0.05 / -0.45 / -0.06 | 103 / +0.51 / -0.01 / +0.41 |
| cr>=6  | 164 / -1.71 / -2.56 / -0.73 | 112 / +0.17 / -0.24 / +0.19 | 94 / +0.52 / -0.00 / +0.42 |
| cr>=10 | 95 / -0.81 / -1.34 / -0.35 | 60 / -0.34 / -0.70 / -0.40 | 64 / +0.52 / +0.00 / +0.42 |
| cr>=15 | 57 / -0.62 / -0.93 / -0.27 | 42 / -0.21 / -0.53 / -0.25 | 44 / +0.69 / +0.17 / +0.56 |
| cr>=20 | 30 / -0.24 / -0.45 / -0.10 | 21 / -0.06 / -0.35 / -0.07 | 22 / +0.16 / -0.19 / +0.13 |
| creator only >=6% holder | 130 / -0.90 / -1.52 / -0.39 | 100 / +0.11 / -0.29 / +0.13 | 77 / +0.53 / +0.01 / +0.42 |
| creator largest holder | 151 / -0.94 / -1.79 / -0.40 | 108 / +0.09 / -0.31 / +0.11 | 90 / +0.63 / +0.10 / +0.50 |

Per run, cr>=6 saved: r38 +0.32, r39 -0.82, r40 -0.59, r41 +0.03, r42dev -0.65 | r42val +0.17 | r43 +0.04, r44 +0.26, r45 +0.08, r46 +0.19, r47 0, r48 0, r49 -0.05, r50 +0.01, r51 -0.01.
HOLD's gain is r44 + r46 plus 2-3 big losses (HGKYev9W -0.137, 9rgBypb1 -0.126, HBgHrRgu -0.117); without the top 5 it is 0.

Loss tail (all periods): creator 6-15% fills lose big (<= -0.05) LESS often than creator <2% fills (3.5% vs 6.4%); 15%+ is 9.1% big losses but also 10.5% big wins. The filter does not cut a tail.
Drawdown (all live fills): DEV -1.11 -> -1.20 (cr>=6, worse), VAL -2.54 -> -2.45, HOLD -1.88 -> -1.43. Helps only in HOLD.
One-position effect (ESTIMATE): blocked fills hold the position only 30-56 s in total per period. 0-2 shadow T2 fills on other tokens fell inside those holds per period, worth about -0.05..+0.05 SOL shadow. Negligible.

Scripts: extract.py -> recon.py -> build.py -> score.py [--holdout] -> extras.py. Data: /home/it/sniper-data/filters3/rearmcr/.

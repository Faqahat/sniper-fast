# FILTERS-3 AUDIT — every live and log filter, runs 37–46, and QUIET (11-03, PKT)

(Saved by the coordinator from the AUDIT agent's final message; sub-agents could not write .md. Measurement only, no new
rules. "est" = paper shadow row c, calibrated to live per run like wide_report.py. Per-run tables: /home/moiz/sniper-data/
filters3/audit/tables.md; machine-readable: audit.json.)

## 1. Short answer
- 10 runs, 109 h, 2,701 live trades, real +18.66 SOL (DEV 74 h +19.9 | VAL 21 h −0.9 | HOLD r43–46 14 h −0.3).
- QUIET: quiet trades (label b: no other wallet buys in our slot or during our hold) = 369 (14%), −10.51 SOL, −28.5 mSOL each,
  22% of all loss SOL. Share rising: 11% DEV → 17% VAL/HOLD; 143 on 11-02 alone (−3.5).
  - 161 of them (−3.96) are RE-ARM trades: QUIET never checks re-arm windows (r5 skip off in every run).
  - 208 quiet T2 trades passed because one of four signals said busy: since_last = 0 (122), cohort wallet holds (106), whale's
    past dumps drew >= 4 (87). The follower-bot vote never fires (empty file, owner's choice).
  - The QUIET skip itself: +1.49 SOL est over 109 h (+0.33/day), +0.26 w/o top 5, ~0 in VAL and HOLD.
- Bigger money: big losses (< −40 mSOL) = 331 trades, −29.0 SOL = 61% of loss SOL; only 45 are quiet.
  Busy trades decay: +18.6 mSOL each DEV → +4.1 VAL → +3.7 HOLD. Quiet trades cost the same every day (−23..−31).
- Live filters: create-slot skip is by far the best, +11.8 est (+2.6/day), positive in DEV/VAL/HOLD, +10.3 w/o top 5.
  age-1 skip ≈ 0 (+0.01). lone whale +0.35 (−0.06 w/o top 5). deeper limit (r40) cost ≈ −1.1 est.
- Log-only (real P&L of flagged trades): bad creator +1.91 (+1.17 w/o top 5; DEV ≈0, VAL/HOLD +); group risk +1.76 (+0.74; +
  in all periods); safe timer +1.53 (DEV −0.21); holder clock +1.00 (+0.05); ctx85 +2.52 (+2.03 of it = 7 attack trades);
  QUIET v2 +0.29 (DEV −0.88); landing guard −0.31 (DEV −1.52); nb50 <= 2 −0.74. Safe timer / holder clock / group risk /
  landing guard mostly flag the same trades.
- Wide shadow (3–6% whales): est gain +3.55 / 68 h, but w/o top 5 VAL −1.70, HOLD −0.66. Not proven.

## 2. What was on in each run
| run | PKT span | T2 / re-arm size | QUIET skip | stop T2 / re-arm | re-arm | lone 50 | log fields | deep 0.85 | wide 3% | profit lock |
|---|---|---|---|---|---|---|---|---|---|---|
| r37 | 10-29 07:32→10-30 01:55 | 0.696 / – | on | 5:2 / – | off | off | off | off | off | 0.75→0.65 |
| r38 | 10-30 02:00→03:38 | 0.696 / 0.65 | on | 5:2 / 6:2 | on | off | off | off | off | 0.65 (fired) |
| r39 | 10-30 05:39→08:47 | 0.696 / 0.65 | on | 5:2 / 6:2 | on | on | on, no safe timer | off | off | 1.0 |
| r40 | 10-30 09:00→10-31 02:17 | 0.696 / 0.65 | on | 5:2 / 6:2 | on | on | + safe timer | ON | off | 1.0 |
| r41 | 10-31 02:25→03:45 | 0.696 / 0.65 | on | 5:2 / 6:2 | on | on | + landing guard | off | on | 1.0 (kill fired) |
| r42 | 10-31 03:52→11-02 08:35 | 0.696 / 0.65 | on | 5:2 / 6:2 | on | on | on | off | on | 1.0 |
| r43 | 11-02 09:06→17:19 | 0.15 / 0.35 | on | 5:2 / 6:2 | on | on | on | off | on | 1.0 |
| r44 | 11-02 17:24→22:09 | 0.55 / 0.65 | on | 5:2 / 6:2 | on | on | on | off | on | 1.0 (fired) |
| r45 | 11-02 22:21→23:05 | 0.55 / 0.65 | on | 5:2 / 6:2 | on | on | on | off | on | 1.0 (kill fired) |
| r46 | 11-03 01:31→01:41 | 0.55 / 0.65 | never active (60-min warm-up) | 5:2 / 6:2 | on | on | on | off | on | 1.0 |

QUIET fol 4, empty follower-bot file in every run. Always on: create-slot skip, min age 2, kill switch −0.5. Never on: breaker,
re-arm r5 skip. From r43 the whale history came from the journal (book file read 0 dumps). QUIET stop is 5:2 on T2 and 6:2 on
re-arm. Stops: r38 lock 10-30 03:38 (+0.307, peak +1.039); r41 kill 10-31 03:45 (−0.500); r44 lock 11-02 22:05 (+0.332, peak
+1.355); r45 kill 11-02 23:05 (−0.505).

## 3. Money method
Trades taken: live realized; blocking saves −P&L. Live T2 skips / T2 stop: shadow row c net_cheap on the same trigger, scaled
to live size, plus per-run gap (−5.5..+54.9 mSOL/window; pooled +1.73 over 1,686 pairs). Only shadow-filled triggers carry
money; live-only fills (467, +4.98 SOL) are invisible to skip estimates. Re-arm skips (no_holder 11,000+, age 7,700+): no
re-arm shadow → counted only. Busy-ness: run tape + landing record for all; raw recordings for 1,467 of 2,701 (agree 1,445).

## 4. Total table (saved = value of blocking/skipping)
| filter | type | DEV (n) | VAL (n) | HOLD (n) | ALL (n) | ALL w/o top 5 | /day |
|---|---|---:|---:|---:|---:|---:|---:|
| QUIET skip (T2) | live, est | +1.412 (156) | −0.020 (51) | +0.093 (28) | +1.485 (235) | +0.259 | +0.33 |
| create-slot skip | live, est | +5.387 (755) | +5.013 (316) | +1.411 (216) | +11.810 (1287) | +10.301 | +2.60 |
| age-1 skip | live, est | +0.702 (131) | −0.723 (51) | +0.029 (34) | +0.008 (216) | −1.215 | 0.00 |
| lone whale skip | live, est | +0.198 (11) | +0.010 (9) | +0.145 (8) | +0.354 (28) | −0.062 | +0.10 |
| QUIET stop T2 5:2 (live windows) | live, est | −0.365 (40) | −0.175 (15) | +0.278 (11) | −0.261 (66) | +0.371 | −0.06 |
| QUIET stop T2 5:2 (shadow, all) | info, est | −0.187 (123) | +0.163 (55) | +0.370 (37) | +0.345 (215) | −0.351 | +0.08 |
| deeper limit refused (r40) | live, est | −1.135 (59) | – | – | −1.135 | −0.105 | −1.56 |
| safe sell timer | log, real | −0.211 (65) | +1.413 (62) | +0.332 (22) | +1.534 (149) | +0.590 | +0.36 |
| holder clock | log, real | −0.265 (94) | +1.256 (68) | +0.010 (31) | +1.001 (193) | +0.046 | +0.27 |
| group risk | log, real | +0.245 (78) | +1.193 (72) | +0.324 (31) | +1.762 (181) | +0.737 | +0.48 |
| landing guard | log, real | −1.518 (54) | +1.081 (63) | +0.131 (26) | −0.306 (143) | +1.005 | −0.11 |
| ctx85 | log, real | −0.390 (69) | +2.847 (82) | +0.060 (49) | +2.517 (200) | +0.430 | +0.84 |
| bad creator | log, real | −0.116 (74) | +1.535 (83) | +0.494 (32) | +1.913 (189) | +1.166 | +0.52 |
| QUIET v2 | log, real | −0.875 (158) | +1.159 (61) | +0.006 (32) | +0.291 (251) | −0.531 | +0.06 |
| nb50 <= 2 (T2) | log, real | −0.911 | +0.398 | −0.228 | −0.741 (168) | −0.054 | −0.20 |
| any of 6 log rules | log, real | −1.169 (311) | +2.519 (189) | +0.558 (101) | +1.909 (601) | +0.799 | +0.42 |
| wide shadow 3–6% (adds) | add, est | +2.511 | +0.546 | +0.493 | +3.550 (2571) | +1.257 | +1.25 |

Raw paper (no calibration) gives the same picture. Overlap on our trades: no log rule 1,979 trades +22.67; one rule 481 −3.17;
two or more 241 −0.84. Of 7,176 create-slot skips, 5,399 also had all four QUIET signals true.

## 5. QUIET deep-dive
Labels: (a) no trade by others after our fill to N slots after our sell; (b) no BUY by others in our fill slot or after us to
K slots after our sell (main label; no (b)-quiet trade can win); (c) no known dip bot traded.

| run | trades | net | quiet (b) n / SOL / mSOL | busy (b) | quiet share of loss SOL |
|---|---:|---:|---:|---:|---:|
| r37 | 338 | +4.896 | 38 / −1.261 / −33.2 | 300 / +6.157 | 20% |
| r38 | 126 | +0.242 | 28 / −0.897 / −32.0 | 98 / +1.139 | 35% |
| r39 | 88 | +0.405 | 14 / −0.537 / −38.4 | 74 / +0.942 | 27% |
| r40 | 351 | +5.579 | 33 / −0.835 / −25.3 | 318 / +6.414 | 16% |
| r41 | 40 | −0.520 | 3 / −0.067 / −22.3 | 37 / −0.453 | 5% |
| r42 | 1328 | +8.386 | 181 / −5.248 / −29.0 | 1147 / +13.634 | 22% |
| r43 | 136 | +0.259 | 21 / −0.224 / −10.7 (size 0.15) | 115 / +0.483 | 33% |
| r44 | 242 | +0.160 | 44 / −1.306 / −29.7 | 198 / +1.466 | 30% |
| r45 | 38 | −0.523 | 6 / −0.112 / −18.6 | 32 / −0.411 | 13% |
| r46 | 14 | −0.227 | 1 / −0.020 / −19.6 | 13 / −0.207 | 4% |
| ALL | 2701 | +18.658 | 369 / −10.506 / −28.5 | 2332 / +29.163 | 22% |

By day (b): 10-29 quiet 32 −1.05 / busy +21.7 mSOL; 10-30 72 −2.26 / +17.9; 10-31 44 −1.27 / +16.2; 11-01 77 −2.41 / +13.6;
11-02 143 −3.51 / +3.1. Quiet trades are small losses (−20..−35 mSOL ≈ one round trip of costs); only 4 hit the stop-loss.

Why QUIET let quiet T2 trades through (one busy vote of four is enough):
| period | quiet T2 | SOL | since_last = 0 | cohort holds | whale dumps drew >= 4 | fbots >= 2 |
|---|---:|---:|---:|---:|---:|---:|
| DEV | 111 | −3.49 | 72 | 52 | 48 | 0 |
| VAL | 55 | −1.98 | 27 | 33 | 20 | 0 |
| HOLD | 42 | −1.08 | 23 | 21 | 19 | 0 |
since_last = 0 is also true on 1,117 of 1,580 busy T2 trades. Single-busy-vote groups were flat/positive in DEV and negative
later (edge fading, not a stable rule).

What QUIET skipped (raw, other buyers in 12 slots after trigger): QUIET-skipped 835 → 44% no other buyer, median 1; armed live
3,605 → 16%, median 5. Est value of the skips: DEV −1.41 (i.e. +1.41 saved), VAL ≈0, HOLD ≈0; of raw-checked skips 72 were not
quiet (winners lost +1.04) and 40 quiet (saved 1.54).

QUIET stop: T2 5:2 ≈ zero (−0.26 live windows / +0.35 shadow). Re-arm 6:2 (932 stops): a stand-in raw replay says the
stopped windows would lose (−1.82 raw / −3.45 adjusted on 514 covered windows) → keep; the stand-in is optimistic, sign trusted.

## 6. Verdicts
| filter | verdict | why |
|---|---|---|
| create-slot skip | KEEP | +11.8 est, + in all periods, +10.3 w/o top 5 |
| QUIET skip (T2) | CHANGE | +1.49 est, ≈0 in VAL/HOLD; 208 quiet T2 trades pass on one busy vote; fbots vote never fires |
| QUIET on re-arm | CHANGE (gap) | 161 quiet re-arm trades −3.96 never checked |
| QUIET stop T2 5:2 | no value | −0.26 / +0.35 |
| QUIET stop re-arm 6:2 | KEEP | est +1.8..+3.4 saved (weak model) |
| age-1 skip | no value | +0.01, −1.2 w/o top 5 |
| lone whale | keep (tiny) | +0.35, −0.06 w/o top 5 |
| deeper limit 0.85 | keep OFF | −1.14 est |
| re-arm skips | can't judge | needs a re-arm shadow |
| profit lock / kill | keep | |
| safe sell timer (log) | keep logging | +1.53, DEV −0.21 |
| holder clock (log) | drop (duplicate) | +0.05 w/o top 5 |
| group risk (log) | keep logging, best of holder family | + in all 3 periods |
| landing guard (log) | change/drop | DEV −1.52 |
| ctx85 (log) | drop | mostly the attack |
| bad creator (log) | promising | +1.91, +1.17 w/o top 5 |
| QUIET v2 (log) | drop | DEV −0.88 |
| wide shadow | not proven | w/o top 5 negative in VAL/HOLD |

## 7. Limits
Skip/stop values are paper estimates and miss live-only fills; calibration noisy on tiny runs; raw covers 1,467 of 2,701
trades (not r38, r39, r43, most of VAL); bad-creator seed built to r38 so scored from r39; r43 traded at 0.15 SOL.

Files: scripts ops/strategies/presend/filters3/audit/ (extract, audit, rawpass ×2, windows, quiet, report, survey); data
/home/moiz/sniper-data/filters3/audit/ (audit.json, tables.md, audit_tables.txt, quiet.json, *.pkl; raw/ + raw2/ = 8.4 GB of
intermediates, deletable since win.pkl holds what was used).

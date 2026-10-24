# Launch selection study (10-23 ~23:55 PKT) — pre-buy filters, entry 60 ms after the decision, 0.5 SOL, fees counted
Data: 79,066 launches (R1+R2+R3), decision points 0/1/3/10/30 s. TRAIN < 10-23 06:00 PKT (26.9 h), TEST after (16.1 h, incl. live run).
Buying every launch loses at every decision point and exit (TEST -59 to -459 SOL).
Positive rules mostly overfit (TRAIN PF 2-16, TEST PF < 1). Survivors on TEST (small edge):
- d=0: desc >= 35 chars AND website AND ipfs image AND symbol <= 6 chars, sell 5 s: 486 picks (30/h), win 32%, avg +1.2%, PF 1.28, +2.81 SOL, dump 5% (base 19%)
- d=0: desc >= 36 AND website AND ipfs image AND creator has no prior creates, sell 30 s: 526 picks, PF 1.14, +2.09
- d=3: create fee >= 0.0016 AND >= 6 insiders AND curve >= 38.6 SOL, sell 2 min: 87 picks, PF 1.14, +2.40, runner 39% / dump 47% (volatile)
- d=30: quiet balanced token (net flow <= 0, buys <= 12, sells <= 7.9 SOL), sell 5 s: 106 picks, PF 2.94, +1.96, DD 0.29
REJECT filters that hold on TEST: dev buy >= 5 SOL (54% instant dump); curve >= 40 SOL or net inflow >= 10 SOL by 1-3 s (54-59% dump);
creator >= 3 prior creates (86% dead); funder funded earlier launches (75% dump/dead); no Twitter (63% dead); < 0.04 SOL bought after 1-3 s (93-95% dead).
Files: launchsel/build.py, analyze.py, reject.py, strategies.txt, reject.txt

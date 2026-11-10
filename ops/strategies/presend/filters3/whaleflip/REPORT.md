# WHALEFLIP (11-03, PKT) — saved by the coordinator from the agent's final message
Verdict: lead NOT proven as a rule; regime-dependent. Do not build now; re-score frozen rule on new runs (~2 days); if it stays
positive w/o top 5, build OPTION (b) own check-only program.

Data: every live fill r39-r48 (r48 partial, copy 06:39), T2 replayed on raw tape (incl. run_20261029_1400 = 10-29 19:00 -> 10-30
19:16 PKT, which the BRIEF wrongly called unrecorded). Gap 11-01 19:06 -> 11-02 17:50 (most of VAL, all r43) -> engine ann.holders PROXY.

1. Exact dumper per T2 fill (tape):
| period | whale's own dump | another wallet's dump |
| DEV | 446, +7.12 (+15.9 mSOL, win 58%, w/o5 +5.98) | 221, +1.37 (+6.2, win 48%, w/o5 -0.11) |
| VAL (73 fills) | 40, +0.67 | 33, -0.81 (-24.6, win 33%) |
| HOLD | 125, +1.57 (+12.6, win 59%) | 74, -0.80 (-10.9, win 38%, w/o5 -1.46) |
Shadow label agrees 92% (625/682); engine's crossing-trade label 93.5% (878/939) — engine errors = whale sells signed by another fee
payer (INFERRED: engine tracks the signer; side effect: the 30 ms "whale sold" stop likely misses them). Other-wallet fills positive
10-31 18:00 -> 11-01 12:00, negative in every 6-h block from 11-01 18:00 except one (fits followers leaving). 66% of whale-own dumps
close the whale's token account.
2. Re-arm: no lead (still-holds DEV +0.68/124, VAL -0.31/88, HOLD +0.23/31; none-left +5.06/262, +0.34/215, -0.55/91).
3-4. Rule A0.5 (buy only if whale holds <= 0.5 of trigger balance or its account is closed), replay with re-fills (real tries + simulated
tries every 26.5 ms; baseline reproduces every live fill; modelled exit +7.94 vs +8.49 realized DEV):
| | blocked (losers) | direct | re-fills | replay | w/o5 | /day |
| DEV 52.8 h | 215 (53%) | -0.91 | 34 -> +1.31 | +0.47 | -0.76 | +0.21 (r39 +0.48, r40 +0.04, r41 +0.23, r42a -0.28) |
| VAL 3.5 h tape | 30 (69%) | +0.89 | -0.27 | +0.63 | +0.01 | +4.3 |
| VAL all fills proxy | | +3.77 (attack +2.24) | | | | ~+1.8 w/o attack |
| HOLD 7.4 h tape | 68 (64%) | +0.63 | +0.15 | +0.77 | +0.11 | +2.5 (r45 +0.62 of it; r48 -0.02) |
Thresholds 0.05-0.75 similar (DEV -0.32..+0.47; "fully sold out" -1.19). Engine-only stop (no on-chain check) FAILS (DEV -6.2 / -3.9 /
-1.2). 10-30 FAIL consistent: same answer on old data (~0); cause = market change after 11-01 ~18:00; big 10-30 losses were the
closed-account rows. Expected: ~+1..+2 SOL/day in the current regime, ~0..-0.4 if the old one returns.
5. Build: (a) Lighthouse AssertTokenAccount: +~48 bytes, ~1.5-3k CU, Token-2022 UNVERIFIED, closed account fails (-6.5 DEV) -> two
variants per try = +0.25..0.9 SOL/day extra failed fees + 2x send rate. (b) own check-only program: +~40-48 bytes, ~0.2-1k CU, closed =
0 in one tx, no extra fees, deploy rent ~0.05-0.15 SOL, no custody, can also carry the slot deadline. Recommend (b) if it holds.
Files: FROZEN.json (written before holdout), whaleflip.json, w1..w10 + wlib/wtape; data /home/it/sniper-data/filters3/whaleflip/.

# 9pQQ EXACT RULES (11-03, PKT) — saved by the coordinator from the agent's final message
Train 10-28 + 10-30, choose 10-31, test 11-02 (opened last). Files: exact.json + per-test JSONs here; data/sim in
/home/it/sniper-data/rivals/9pQQ/exact/.

## Exact (hold on 100% of trades, 4/4 days)
ONE code path: CU price 1,500,001; CU limit 130,000 buy / 80,000 sell (200,000 rare SellV2); tips Astralane 1,000,000 buy / 100,000 sell
+ Jito 17,500. BUY = BuyExactQuoteInV3 for exactly 700,000,000 lamports incl. pump fees (480,000,000 for 5,250 buys on 10-30), creates
the ATA if missing. SELL = SellV3 of the whole balance. One buy + one full sell per position; never 2 positions on one token. Never
mayhem (0/28,240). Never buy before token age 8 slots (most at 10-11). Never sell before buy slot + 2; never re-buy before own sell + 2.
Forced sell at the hold cap (300 s; 600 s since 10-31 14:03). Slippage ~10-15% (inferred). Reacts to trades: 98% of buys have an
outside trade on the token in the same/previous slot (random 37-38%); sells 79-92% (rest = time cap). Buys at curve 30-112 SOL; up to
25-32 open positions.

## Soft drivers (not exact)
Buys: recent own sell on the token (re-entry), price vs his last buy/sell there, trigger = a price-moving buy; trade count, trigger size,
age, trigger from a high-volume bot, trigger's program. Sells: outside buying dries up (3-10 slots), time since buy, 1-3 slot price drop.

## Hypotheses (11-02)
H1 leader wallets: REJECTED (3,054 trigger wallets; top 1 = 4%, top 10 = 21%; train list of 1,014 finds 9.1% of buys at 1.9% precision vs
base 0.42%; strict 9-wallet list 0.04%; sells 435-wallet list finds 10% at 7.2% vs base 2.9%; day-to-day rank corr 0.36 / 0.53).
H1b trigger program 41Pr4XqE (alone or with 6gY1osmP / L2TExMFK): 8-14x his buy rate on all 4 days but only 6-9% of his buys.
H2 several bots: REJECTED (one fingerprint). H3 simple exit rule: REJECTED (best "3% below peak since buy" hits his sell slot +-1 22%;
first outside sell >= X 16-18% and 72-78% too early). Sell rule list (13 rules, frozen 10-31): precision 16.9%, recall 17.2%.
H4 buy rule list (7 rules, frozen 10-31): precision 8.4%, recall 24.7%. ML ceiling (84 features): buys 16% precision at 5% recall,
11.6% at 25%; sells 31% / 20%.

## Rebuilt bot on the tape (replay checked: his real trades -> 18.91 / 63.70 / 52.78 vs real 18.84 / 63.66 / 52.76)
| day | role | bot/his buys | prec | recall | sell +-1 | his speed | our speed | ours -20% | his real |
| 10-28 | train | 9,711/4,248 | 7.6% | 17.4% | 26% | -90.5 | -128.7 | -167.2 | +19.6 |
| 10-30 | train | 9,150/8,870 | 18.6% | 19.2% | 30% | -61.7 | -104.7 | -139.9 | +87.3 |
| 10-31 | choose | 9,800/7,224 | 12.4% | 16.8% | 26% | -90.4 | -129.7 | -169.0 | +68.6 |
| 11-02 | TEST 16.5 h | 8,367/7,898 | 13.6% | 14.5% | 27% | -59.8 (-87/day) | -97.6 | -134.8 | +61.6 |
| 10-31 | pickier | 1,253 | 15.2% | 2.6% | 25% | -23.3 | -24.4 | -29.0 | |
| 11-02 | pickier | 1,218 | 20.3% | 3.1% | 29% | +4.1 (w/o top5 -5.6) | -3.6 | -9.1 | |
His own picks + own sells at +45 ms: +11.1/+79.9/+46.5/+28.8; at our +70 ms: -9.1/+18.3/+2.6/-12.5 (-20%: -32/-20/-28/-48).

## Proven / not
Proven: the hard rules. Not proven: any rule for WHICH trade he buys after or WHEN he sells. Inference: he reacts to information not in
landed trades (pending/failed txs early in the block stream, longer wallet histories, or a model with randomness). Next test: add failed
and pending pump.fun txs as events. Usable: never mayhem / no entries before ~8-10 slots age; his cheap single-copy send recipe (live A/B,
owner OK); "9pQQ traded this token before" (log-only); NEW lead: triggers routed through program 41Pr4XqE (log-only check vs our followers).

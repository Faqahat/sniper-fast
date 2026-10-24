# Selection round 3: exact conditions for strong launches (2026-10-22)

## Data
- **Launches:** 19,424 SOL-quoted launches with clean trade data:
  - run_20261021_2207: 17.6 h;
  - run_20261022_1543: first 2.8 h.
- **Time-split:**

  | Part | Data | Hours | Used for |
  |---|---|---|---|
  | TRAIN | run 1, first 60% | 8.2 h | building rules |
  | VAL | run 1, 60–80% | 3.7 h | choosing rules |
  | TEST1 | run 1, last 20% | 5.7 h | unseen test |
  | TEST2 | forward run | 2.8 h | unseen test |

- **Rule:** nothing in either TEST was used to build or choose a rule.
- **Measurement point:** everything is measured from the price right after the creator's glued bundle.
- **Scripts:** f_label.py (demand facts), r3_search.py (beam search over conjunctions; thresholds at train deciles; at most 3–4 conditions; at least about 90 launches per rule).

## Labels (what happened after the bundle)
| Label | Definition | Share of all launches |
|---|---|---|
| DUMP NOW | price ≤ 0.85x within 5 s | 26–31% |
| DEAD | < 5 outside buyers and < 1 SOL of outside buys in 60 s | 47–55% |
| REAL DEMAND | ≥ 10 distinct outside buyers and ≥ 5 SOL of outside buys in 60 s, no dump | 15–17% |
| GOOD | real demand AND ≥ 1.1x at 60 s AND ≥ 1.0x at 5 min (or curve filled) | 2.2–3.0% |
| STRICT STRONG | ≥ 20 buyers and ≥ 10 SOL in 60 s, ≥ 1.3x at 60 s and 5 min | 1.1–1.8% |

**Finding:** real demand is common and predictable. Demand that holds for minutes is rare: even the best filters keep only 9–38% of picks above our entry at 5 min.

## Filter A: strong launch (real demand + follow-through), known before we buy
```
dev buy in the create tx            <= 0.39 SOL
creator bundle (glued buy txs)      >= 3
bundle average per wallet           >= 2.3 SOL
```

| Unseen period | Picks | GOOD | Dump now | Dead | Real buyers in 60 s (median) |
|---|---|---|---|---|---|
| TEST1 | 16 (2.8/h) | 25% (base 2.2%) | 12.5% | 0% | 38 |
| TEST2 | 13 (4.6/h) | 38% (base 3.0%) | 23% | 8% | 52 |

**Caveat:** these are mega-bundled launches.
- The bundle already buys about 60 SOL of the curve, so we would enter at a market cap of about 260–300 SOL instead of 29.
- 59–62% fill the curve within 5 min, and 21% within 10 s.
- Little curve room is left. Selling on the curve, first in line after the bundle:
  - unseen: +0.035 SOL/trade, win 62% (n=21);
  - behind 2 or more outside buyers: negative.
- After the curve fills, trading moves to the pump AMM. Its price is not in our data yet; decoding the PumpSwap events is the next step.

## Filter B: best trade with exact conditions
```
launch tool (metadata uri host)          == meta.uxento.io
same symbol launched in the past hour    == none
```
| Unseen period | Picks | Real wins (> +5% net) | Dump now | Dead | First-sell trade |
|---|---|---|---|---|---|
| TEST1 | 34 (6/h) | 29% (base 9%) | 12% | 18% | +7.5% |
| TEST2 | 49 (17/h) | 29% (base 8%) | 14% | 20% | +3.2% |

**Variant:** uxento AND bundle ≥ 3 wallets. First-sell trade +4.9% on both tests, dump 17–22%.

## Comparison: the FINAL-2 model (not exact conditions; already running live in the shadow)
| Unseen period | Real demand | Dump now | Dead | GOOD | First-sell trade |
|---|---|---|---|---|---|
| TEST1 | 77% | 11% | 5% | 10% | +9.4% |
| TEST2 | 62% | 11% | 12% | 9% | +23% |

FINAL-2 makes 17–39 picks per hour.

## Recommendation
- **For trading:** implement the FINAL-2 model in the sniper. No exact-conditions filter matched it on dumps or on trade returns.
- **If exact conditions are required:** use Filter B, or Filter B with the bundle ≥ 3 wallets variant.
- **Filter A:** use it as a "strong launch" tag, not as a buy rule, until AMM prices are in the data.
- **Speed caveat:** every trade number above is for first in line right after the bundle. At our measured 74 ms landing, all of them are about 0 or negative (see h_real.py, real74.log).

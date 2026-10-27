# haqq's buy sizing (agent, 10-28 ~00:15 PKT)

Saved by the main session from the agent's reply (the harness blocked the agent's report write).

## His sizing rule (MEASURED, 25,641 buys, 10-23 → 10-27)
- Fixed SOL tiers. Mostly 0.40 (40%), 0.25, 0.30, 0.01 probes, 0.50 / 1.00 / 1.25.
- **Rule:** ~0.35 SOL normally (0.40 after a dump, 0.25 when nothing dumped in the last 3 slots), and ~0.94 SOL when the curve is back near its start (curve SOL ≤ 30.5, "dead curve").
- Held-out fit: R² 0.43, tier accuracy 75%. Curve SOL is 77% of the fit.
- Not Kelly-like: size doesn't follow his P&L, wins or open positions. The tier menu changes day to day.
- 47% of tokens get more than one buy; adds are smaller.

## Did it pay for him? No (before tx fees and tips)
| His buys | Average size | Return per SOL | Win rate | Median hold |
|---|---|---|---|---|
| Normal curve | 0.35 | +2.07% | 44% | 5 s |
| Dead curve | 0.92 | +0.46% | 25% | ~20 min |

His sizing cost him ~28 SOL over 4 days vs one flat size with the same SOL. Nearly all of his +160 SOL came from the 0.25–0.40 buys.

## On our engine (held-out day, run-28 config, same average size; SOL/day)
| Row | Flat 0.50 / 0.55 | His rule | Score terciles |
|---|---|---|---|
| Realistic | +8.61 | +7.78 (−0.83) | +8.93 (+0.31, CI includes 0) |
| Calibrated | +3.61 | +2.97 | +3.97 |
| 20% fewer followers (pre-send) | +1.89 | +1.26 | +2.25 |

## Verdict
- Keep flat size.
- His big dead-curve buys are our weakest chances (+0.25% per chance vs +2.8%).
- Side note: at 50 ms landing, M2 P&L kept rising with size up to 1.25 SOL; at 75 ms it peaks at 0.65–0.80. One day only.

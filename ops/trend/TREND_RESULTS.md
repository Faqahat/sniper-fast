# Rule 3 "trend" (exit-rule search), 2026-10-21 evening — read-only, chain data only

Entry is fixed at our real speed: we buy where our real buys landed. The question was whether any exit rule makes that entry profitable.

## Data
- **17 real buys.**
  - PROD wallet 2g7rYv7y: Run 1 + Run 2, 5 tokens.
  - FRZ wallet FRZh63L6: last 12 test buys of ~0.001 SOL.
  - Each one is simulated as a 0.5 SOL buy at the same pre-trade curve state, using Run 2's real costs (buy tx 0.516585 all-in, sell overhead 0.000091).
  - Every later trade is replayed by amount. The replay matches the chain to ~1e-10, and on our 3 single-sell trades the formula reproduces the real wallet result exactly.
- **62 recorded rule #2 launches** (exit_sim data), entry at our measured landing (Jito-client 75 ms, Harmonic 80 ms).

## Scripts and outputs
- `trend5.py` and `trend_w.py`: fetch the data.
- `analyze5.py` and `analyze_sim.py`: per-trade PnL.
- `combo.py` (17 tokens) and `combo73.py` (62 launches): rule searches.
- HTML and CSV outputs are in `out/` and `out_frz/`.

## Results (SOL, 0.5 SOL per trade)
Rule grid: take-profit, stop-loss, time stop, trailing stop, and "sell on dev / early wallet / any sell".

| Data | Rules tried | Rules positive | Best, picked in hindsight | Honest test | Sell at S+3 (now) |
|---|---|---|---|---|---|
| 17 real buys | 6,720 | **0** | −0.177 | leave-one-out −0.675; picked on PROD +0.354 → FRZ −0.900 | −0.437 |
| 62 recorded launches | 5,040 | **0** | −0.132 | best of the 62 applied to the 17: −0.362 | −0.337 |

Our 5 PROD trades alone made "+10% else sell at 10 s" look like +0.26. That was luck: the same rule gives −0.44 on 5 random FRZ trades and −1.28 on all 12.

## Facts behind it (17 real buys)
- **9 of 17** never rose enough after our buy to cover fees, at any moment within ~85 s.
- **The other 8** peaked at very different times, from S+6 to S+367.
- **The dev sold early:** first dev sell between S+3 and S+145.
- **No buy-time signal:** nothing known when we buy separates the 8 from the 9 (buys before us 2–7, SOL before us 4–12, dev buy 0.65–5 SOL, entry S+0/S+1 all overlap).

## Verdict
No exit rule makes this entry profitable in either dataset. A strategy would have to change which tokens we buy or when we buy.

# Exit / landing simulation (2026-10-20) — ops/comp/sim_ladder.py on 515 rule-#2 launches (10-18 18:16 -> 10-19 14:28 UTC)

Replays the engine's --exit-ladder slot by slot (sells land 1 slot after the decision; the engine waits for each leg),
our buy inserted at landing positions d8/d25/d100/d200 (txs after the create, same slot) or s1 (top of the next slot);
costs: pump fee per side from events, buy landing fee, 0.0005 SOL per sell leg, own price impact on every leg,
entry cap (revert costs the 0.0105 priority). Others' trades held fixed (buy SOL / sell tokens) — an approximation.
Folds = time thirds (172/172/171). Full grid: 2,268 exit settings x 3 sizes x 2 fees x 4 caps (sim_ladder_results.txt).

## Results (size 1.5 SOL, buy fee 0.025, entry cap 15%) — best robust exit, SOL per trade
| landing | mean | % of size | worst fold | win |
|---|---|---|---|---|
| d8 (+8 txs) | +0.084 | +5.6% | +0.081 | 50% |
| d25 | +0.065 | +4.3% | +0.065 | 47% |
| d100 | +0.024 | +1.6% | +0.024 | 39% |
| d200 | +0.005 | +0.3% | +0.004 | 27% |
| next slot (s1) | -0.007 | -0.5% | -0.009 | 31% |
With the old 0.006 fee the same rows are +0.103 / +0.084 / +0.042 / +0.022 / +0.009.

## Conclusions
- EXIT: sell everything ~3 slots (~650 ms) after the buy lands. Every ladder / ride / trail variant and every longer
  hold (2-20 s) is equal or worse at our landing positions. -> Run 1 uses --hold-ms 450 + one full sell (no ladder).
- LANDING decides the result: +8 -> +5.6%, +25 -> +4.3%, +100 -> +1.6%, +200 -> ~0, next slot -> slightly negative.
- FEE: 0.025 instead of 0.006 costs 0.019 SOL/trade; it pays only if it moves us from ~+200/next-slot to ~+100 or
  better (e.g. +200 -> +25 = +0.06 SOL/trade). Run 1 measures exactly that (landing position per buy).
- SIZE: % return ~flat from 1 to 2 SOL -> SOL/trade scales with size.
- ENTRY CAP 15% helps slightly at +100 and later (skips ~9-13% of trades).

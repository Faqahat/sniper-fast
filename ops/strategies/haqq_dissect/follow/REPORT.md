# Analyst H (follow): a "will this whale dump be followed" selector; KEY correction: live fills are adverse (10-28 ~03:45 PKT)
Saved by the main session from the agent's reply. Code: this folder (f1–f10, flib). Tables: /home/moiz/sniper-data/haqq_dissect/follow/ (f2b live vs model fill, f9 fill by value, f10 / f5_f10 final, f4 / f5 superseded, f6 haqq-follow target, f7, f8). Decision log: decisions.jsonl (429,109 lines).

## Universe (MEASURED)
- **Episodes:** 136,658 whale episodes (a wallet reaching ≥6% of supply, until its next sell), 18–27k per day; 75% are creation-slot whales.
- **Whale buy → next sell:** median 9–10 slots, p90 99–246.
- **haqq** buys within 2 slots of the dump on 10–16% of them.

## KEY: live pre-send fill is ADVERSE (MEASURED, 4,564 live windows)
- In windows with a qualifying drop, live filled 43.9% vs the model's 84.1%.
- Where we missed live, the drop was worth +31.2 mSOL; where we filled, −1.2.

| Model value of the drop (mSOL) | < −10 | −10..0 | 0..10 | 10..30 | 30..60 | > 60 |
|---|---|---|---|---|---|---|
| Live fill rate | 0.571 | 0.678 | 0.623 | 0.495 | 0.415 | **0.225** |

So paying dumps are crowded and others land first. A flat fill rate overstates any selector of paying dumps by ~4×. **Analyst E's +6.6..10.8 and analyst A's +5.4/day are likely overstated for this reason.**

## Walk-forward with the value-dependent fill rate (calibrated NOW, k=4, ≤5 armed, wave exit; SOL/day)

| Day | Total [90%] | **New fills** | 10% fewer followers | 20% fewer followers | S2 costs |
|---|---|---|---|---|---|
| D2 | +2.26 [+1.41..+3.09] | **+1.34** | +0.91 | −0.42 | +2.99 |
| D3 | +1.85 | **+1.31** | +0.38 | −1.07 | +2.65 |
| D4 | +1.89 | **+1.11** | +0.74 | −0.39 | +2.43 |
| D5 | +3.13 | **+2.26** | +2.00 | +0.89 | +3.60 |
| **Mean** | **+2.28** | **+1.51** | +1.01 | **−0.25** | +2.92 |

- With a flat fill rate the same pipeline gave +7.2..+13.2/day: superseded.
- Arming cost ~0.5–0.9 SOL/day is included. Rate caps are fine: 2+ tokens armed only 2–7% of the time.
- The value is in whales decided at their buy, especially creation-slot whales.

## What drives the score (gain share)
- **12.5%:** what buying this wallet's earlier dumps in the last 24 h made (2-slot exit). Wallets whose dumps got bought before get bought again.
- 7.3%: the largest other holder's share.
- 6.1%: mean buyers after this wallet's earlier dumps (QUIET's signal).
- 5.3%: hour of day.
- 4.7%: curve size.
- The rest: whale SOL, other ≥6% holders, outside buy flow, creator holding, market dump rate.

The "will haqq follow" target has AUC 0.81–0.84, but as a selector it is worse than targeting our own P&L.

## Engine spec (shadow first)
1. Track every ≥6% holder, including the creator and creation-slot buyers.
2. Score at the buy +50 ms and at +2 / 5 / 10 / 20 / 40 / 80 / 160 slots (GBDT f10.pkl, retrained daily).
3. **Arm when score ≥ threshold:**
   - window: until the whale's next sell, or a 25–50 slot cap;
   - ≤5 tokens at once, k=4, limit 0.88 × the latest price;
   - wave exit.
4. Extend the QUIET book with per-dump mint and 2-slot value, and whale episodes.
5. **The shadow must measure live fill rate by value bucket.**

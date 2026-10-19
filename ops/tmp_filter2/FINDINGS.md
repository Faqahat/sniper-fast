# 4yFAz filter-discovery — findings (read-only analysis, 2026-10-16)

Dataset: 401 of his buys with peak_r outcome (merged his_500 buy-time feats + his_tape realized P&L).
Overlap with realized P&L = 161 trades. Base rate: 22.9% RUNNERS (peak>=1.5), 27.2% DUMPS (peak<1.1).
Base mean realized P&L +0.1866 SOL/trade, sum +30.04 over 161.

## Dominant signal
n_trades_0_3 (trade count in first ~3 slots after create) = early demand. Monotonic with outcome.
vanilla==0 (token carries a pump feature: holder_reward / creator_fee / mayhem / cashback) is a
cheap runner-recovery override: non-vanilla launches run more (30% vs 21%) and barely add dumps.

## Top filters (constraint: runner-retention >= 95%)
FILTER                              keep  ret%  rej%  keptPeak  meanPnL   sumPnL  uplift
A n03>=4 OR vanilla==0              318   95.7  46.8  1.428     +0.2205   +29.10  +18%  <-- RECOMMENDED
B n03>=3 OR vanilla==0              338   96.7  35.8  1.411     +0.2137   +29.48  +15%
E van0 OR n03>=4 OR dev_buy>=3      326   95.7  43.1  1.421     +0.2164   +29.44  +16%
F van0|hr>0|cfee>0|n03>=4           319   95.7  45.9  1.426     +0.2205   +29.10  +18%
(baseline no filter)               401  100.0   0.0  1.366     +0.1866   +30.04    0%

## RECOMMENDED: A = keep if (n_trades_0_3 >= 4) OR (vanilla == 0)
- Rejects 46.8% of dumps, keeps 95.7% of runners, +18% per-trade P&L, keeps 318/401.
- Compute at buy-time / within 3 slots:
  * n_trades_0_3: count Buy/Sell txs on the mint in slots [create_slot .. create_slot+3]
    (exclude the create tx). Observable 3 slots (~1.2s) after our slot-0 fire; or gate the add/hold.
  * vanilla: parse create-tx logs; vanilla=0 if any of holder_reward / creator_fee_bps>0 /
    mayhem / cashback present (known AT create, slot 0).

## Validation (all correct under Filter A)
PASS1 6uQr (runner, dev 1.31): n_trades_0_3=39 -> PASS (demand branch)
PASS2 EYo9 (his snipe, dev~0): n_trades_0_3=13 -> PASS (demand branch; vanilla=1, no override needed)
REJECT HNwc (rug, 6 tx, 22s): n_trades_0_3=1, vanilla=1, dev 0.107 -> REJECT (no branch admits)

## Honest ceiling
His realized P&L decomposition (161 overlap):
  RUNNERS n=42  sum +23.85 (79% of all profit), mean +0.568
  MID     n=96  sum +8.52
  DUMPS   n=23  sum -2.33  (only -8% drag), mean -0.10  <- he exits dumps near flat
- A PERFECT dump filter saves him only ~2.33 SOL (~8%). Selection moves per-trade EV +15-18% max.
- 79% of his profit is RUNNER upside captured by fast exit near peak — selection cannot manufacture it.
- For a HOLD clone the calculus flips on the downside: a hold clone does NOT bail dumps at -0.10;
  it bleeds the full position as the curve decays. So 27%-of-launches dumps become the clone's main
  loss source, and rejecting ~47% of them (Filter A) is materially protective. But the clone's P&L
  ceiling is still set by EXIT quality on runners, not by selection. Filter A is a downside guard,
  not an alpha source: realistic lift to a hold clone is bounded to the dump-bleed it removes.

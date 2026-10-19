# Exit-Timing Hypothesis Test — Did our sniper cut too early? (n=8 live trades)

**Date:** 2026-10-14  **Env:** 77.223.215.155, constantk staked RPC
**Method:** For each of our 8 live trades, paginated the bonding curve's full trade history
(constantk `getSignaturesForAddress` + `getTransaction`, reusing `/root/profit_backtest/common.py`).
Price per trade = |SOL delta| / |token delta| on the bonding curve. Units reconciled to the given
entry (lamports/raw-token = px_common × 1000). r = price / our_entry. Working dir `/root/exit_timing/`.

**Hypothesis under test:** (A) EXIT-TOO-EARLY — tokens pump AFTER we sell, so the ladder is the
problem; vs (B) REGIME — tokens just never pumped, so holding longer loses the same or more.

## Per-token price path

| # | mint      | trades | exit_r | lifetime peak_r | **post-exit peak_r** | slots→peak | r@+10 | r@+30 | r@+60 | class |
|---|-----------|-------:|-------:|----------------:|---------------------:|-----------:|------:|------:|------:|-------|
| 1 | 883Xw2k39i|   41 | 0.96 | 1.00 | 0.95 |  45 | 0.90 | 0.92 | 0.80 | NEVER-PUMPED |
| 2 | 3nfCAA4emV|   10 | 0.98 | 1.00 | 0.95 | 468 | 0.98 | 0.98 | 0.98 | NEVER-PUMPED |
| 3 | CenpWbd7Yg|   16 | 0.98 | 1.00 | 0.96 |  64 | 0.98 | 0.98 | 0.95 | NEVER-PUMPED |
| 4 | 2mczEAedUh|   74 | 0.98 | 1.00 | 0.91 |   3 | 0.61 | 0.81 | 0.67 | NEVER-PUMPED |
| 5 | 7Cs9KCipGn|   55 | 0.98 | 1.26 | 1.26 |   5 | 1.21 | 1.05 | 0.76 | MARGINAL |
| 6 | FXUVymBHRS|  118 | 0.98 | 1.34 | 1.34 |   4 | 1.15 | 1.01 | 0.79 | PUMPED-AFTER-EXIT |
| 7 | BEms6yQdym|   51 | 0.87 | 1.33 | 1.33 |  79 | 0.87 | 0.87 | 0.87 | PUMPED-AFTER-EXIT |
| 8 | 8FYmQHVr33|  172 | 0.97 | 1.44 | 1.44 | 355 | 0.98 | 0.92 | 1.10 | PUMPED-AFTER-EXIT |

`exit_r` ≈ 0.87–0.98 matches the ground truth ("exited flat r≈0.98–1.04") — confirms units/reconstruction.

## Counts
- **NEVER-PUMPED (lifetime peak_r < 1.2): 4 / 8** — flat or declining from our entry; several died (#1,#4 down to 0.6–0.8).
- **MARGINAL: 1 / 8** (#5, 1.26x).
- **PUMPED-AFTER-EXIT (post-exit peak_r ≥ 1.3): 3 / 8** — but only to **1.33–1.44x**, and every one was a **1–5 slot wick that immediately reverted**.
- Max lifetime peak across all 8 = **1.44x**. Nothing ran.

## The key number: the "pumps" were un-catchable wicks
For the 3 "pumped" tokens, the move was gone almost instantly:
- #6: peak 1.34 at +4 slots → **r@+10 already 1.15, r@+30 1.01, r@+60 0.79**.
- #7: 1.33 was a single spike at +79; r@+10/+30/+60 all **0.87** (a loss at every realistic sell point).
- #8: 1.44 at +355 slots, but the path sat at/under entry the whole way (r@+10 0.98, r@+30 0.92).

## Counterfactual — would a looser / later / trail-only exit have done better?
Baseline (our exit) calibrated so the 8-trade total = actual **−0.021 SOL**. Same model, equal sizing.

| Strategy | mean mult | 8-trade total (SOL-equiv) |
|---|---:|---:|
| **Our exit (actual)** | 0.961 | **−0.021** |
| Fixed hold → sell @ +10 slots | 0.958 | −0.053 (net_r) |
| Fixed hold → sell @ +30 slots | 0.942 | −0.070 (net_r) |
| Fixed hold → sell @ +60 slots | 0.863 | −0.147 (net_r) |
| Trail-ride 85% / cut 80% / cap 300 | 0.830 | **−0.075** |
| Trail-ride 80% / cut 70% | 0.785 | **−0.094** |
| Trail-ride 70% / cut 60% | 0.773 | **−0.099** |
| ORACLE (sell at exact post-exit peak, perfect foresight) | 1.141 | +0.127 (net_r) |

**Every realistic looser exit loses 2.5×–4.7× MORE than we actually did.** A trailing stop gives back the
tiny wick gains and then rides the duds down to death. The only thing that beats our exit is an oracle that
sells into a 1-slot wick with perfect foresight — not a reproducible strategy.

## VERDICT: (B) REGIME — exit timing is NOT the problem
These 8 were duds. 4 never exceeded 1.0x, the best lifetime peak in the whole set was 1.44x, and the 3
"post-exit pumps" were instant wicks that reverted within ~10 slots. Holding longer, capping later, or
trailing would all have lost **more**, not less. The ladder exiting flat at ~0.96–0.98 in ~1–2s was close to
the best achievable outcome given the price paths.

The loss is an **entry/selection problem (which tokens we snipe) and micro-slippage**, not an exit-ladder
timing problem. To fix the P&L, filter for tokens that actually trend (none of these did) and tighten
entry cost — not loosen the exit.

**Honesty on n=8:** tiny sample, one ~2-minute slot window (456,975,817–456,977,932), all small losers by
construction. This rules out "exit-too-early" *for this cluster* strongly (the counterfactual is unambiguous),
but says nothing about trades that genuinely trended — we have none of those here to study.

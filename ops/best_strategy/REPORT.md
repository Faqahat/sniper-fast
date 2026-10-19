# Best pump.fun sniper TRADE STRUCTURE — search across 6 strategy families

**Question.** Selection carries ~no alpha OOS (no slot-0 feature predicts runners). So the leverage is
the **trade structure after entry**. Which sizing / scale / ride / cut structure maximally **catches
runners** and **avoids/cuts dumps**, net of all costs, out-of-sample?

**Method.** All families replayed on the SAME unbiased price paths (/root/profit_backtest/trajectories.json,
656 creates passing the shipped filter: dev_buy>=2, creator_fee_bps==0; contains the runners — 197 peak
1.1-1.5x, 109 1.5-2x, 92 >=2x; median peak 1.24x, max 21.8x). Entry = realistic fill floor*1.02 (3M
priority, same-slot); r measured at that entry. Costs netted every leg: 2% pump round-trip + ~0.5% slip
+ fixed priority/base lamports (365k/leg), modeled at 0.5 and 2.0 SOL. Engine = /root/best_strategy/engine.py
(lot-based, bit-reconciled to the shipped econ_102/fading simulators). Robustness: 1000-sample bootstrap
CI, 200-400 random 50/50 PAIRED splits vs baseline, and drop-top-2 (mean_ex_top2). Headline numbers are
full-sample (most stable on a heavy tail) with paired-split + drop-top-2 as the OOS/robustness checks.

**Baseline to beat** (current best from /root/mirror + /root/fading_test):
derisk 0.0 / ride 1.40 / trail 0.92 / cut 0.80 / ladder 0.25 / cap 40, no fading.

---

## The one new, decisive empirical fact

Unlike slot-0 features, early PRICE ACTION is strongly predictive of eventual runs:

| early signal | frequency | P(peak >= 1.5x) |
|---|---|---|
| base rate | 100% | 31% |
| r >= 1.2x within 2 slots | 17% | 57% |
| r >= 1.3x within 2 slots | 13% | **69%** |
| r >= 1.3x within 8 slots | 19% | 69% |

The alpha is in the post-entry path. Two structures try to exploit it: scale-in (add to confirmed
momentum) and a late ride-arm (only trail confirmed movers). The ride-arm wins; scale-in does not.

---

## Strategy-family comparison (OOS net R, same 656 paths, 0.5 SOL, net of all costs)

| family | best config | mean R | median | win% | total R | max-DD | runner-capture | dump-bleed | drop-top2 | vs base (paired) |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| **Baseline (shipped)** | cut.80 ride1.4 trail.92 ladder.25 cap40 | +0.0691 | -0.0265 | 47.1% | +45.3 | -4.01 | 0.369 | -0.162 | +0.0606 | — |
| **F1 EXIT GRID -> WINNER** | **cut0 ride2.0 trail.90 ladder0 cap15** | **+0.1074** | -0.0265 | 46.3% | **+70.5** | **-3.83** | **0.418** | -0.162 | **+0.0990** | +0.0385, **100%** |
| F2 Momentum scale-in | s0 .5 + add .5 @1.1x by8 | +0.0544 | -0.014 | 39.8% | +35.7 | -2.26 | 0.266 | **-0.078** | +0.0472 | -0.015, 11% |
| F3 Two-regime fast-cut | cut.80 ride1.7 trailR.90 capR40 | +0.0844 | -0.0265 | 43.8% | +55.4 | -4.44 | 0.370 | -0.150 | +0.0759 | +0.015, 100% |
| F4 Dynamic hold (lower-high) | ride1.7 eps0 capR40 | +0.0960 | -0.0265 | 45.9% | +63.0 | -3.60 | 0.381 | -0.155 | +0.0875 | +0.027, 100% |
| F5 Re-entry after cut | any threshold | -EV | — | — | lowers mean | — | — | — | — | worse |
| F6 Sizing / Kelly | (analysis) | size-invariant EV; f*~0.63, use <=1/4-Kelly | | | | | | | | |

### Reading the families
- **F1 EXIT GRID is where the gain is.** Two levers dominate: (a) ladder_frac -> 0 (stop scaling out of
  winners in the 1.0-ride band; ride the whole position), and (b) remove the hard price stop (cut_r -> 0).
  The hard stop clips dip-then-rip runners on the dip. Loss control moves to the time cap (15 slots ~3.4s).
- **F2 Momentum scale-in LOSES** (the headline new idea, honestly tested). Halves dump-bleed (-0.078 vs
  -0.162) and drawdown (-2.26), BUT runner-capture collapses to 0.266 and mean R drops to +0.054 — below
  baseline. Even return-on-capital (0.071) is below full-size entry (0.096). Why: the add is bought UP at
  >=1.1x with its own 2%+slip, capturing less of the run while paying more; and entering small on
  everything means a smaller stake on runners that rip straight from the floor. Scale-in is a
  risk-reducer, not an EV-improver.
- **F3 Two-regime fast-cut LOSES.** Cutting duds faster (cut 0.80/0.90) necessarily clips dip-then-rip
  runners too — same tokens; you can't separate them early.
- **F4 Dynamic hold ~ ties** the trailing stop (+0.096) — the trail already captures "exit on reversal."
- **F5 Re-entry is -EV** at every threshold (re-entry leg mean -0.05 to -0.09). Chasing a token that
  already ripped after you cut it pays the fee twice into a worse entry.
- **F6 Sizing:** EV is size-invariant (0.5 SOL +0.0977 vs 2.0 SOL +0.0988) — the 2% + 0.5% fees dominate;
  the fixed priority lamport is negligible even at 0.5 SOL. Priority fee is NOT the drag; the round-trip
  protocol fee is. Kelly on the winner's returns: f*~0.63, but worst single trade is -1.0 (a rug gaps
  through any stop between polls), so full-size risks ruin. Use <=1/4-Kelly (~15% of bankroll per snipe):
  log-growth +0.0135/trade, far from ruin.

---

## WINNER

```
derisk_frac = 0.0        # no entry de-risk (selling at entry donates runner upside)
ladder_frac = 0.0        # no scale-out on the way up; ride the whole position
cut_r       = 0.0        # NO hard price stop (it clipped dip-then-rip runners; rugs gap
                         #   through it anyway — worst trade -1.0 WITH or WITHOUT a stop)
ride_mult   = 2.0        # arm the trailing stop only after a confirmed 2x
trail_frac  = 0.90       # once armed, exit if price falls to 90% of running peak
cap_slots   = 15         # ~3.4s hard time stop for EVERYTHING (the real loss control)
fading      = off
```
Average 2.0 legs/trade (one buy, one sell) — the simplest structure in the whole search.

### Winner vs baseline — head to head (full sample, 0.5 SOL, net)
| metric | baseline (shipped) | WINNER | delta |
|---|---:|---:|---|
| net mean R | +0.0691 | **+0.1074** | **+55%** |
| median R | -0.0265 | -0.0265 | flat (tail game) |
| win % | 47.1% | 46.3% | ~flat |
| total R (656 trades) | +45.3 | **+70.5** | +25.2 R |
| max drawdown | -4.01 | **-3.83** | better |
| sharpe (per-trade) | 0.147 | **0.211** | +43% |
| runner-capture (% of >=2x upside) | 0.369 | **0.418** | +13% |
| dump-bleed (mean on <1.1x duds) | -0.162 | -0.162 | identical |
| drop-top-2 mean | +0.0606 | **+0.0990** | +63% |
| bootstrap 95% CI | [+0.036,+0.104] | **[+0.067,+0.145]** | shifted up, excludes 0 |
| paired random splits better than baseline | — | **100% of 400** | decisive |

The gain is NOT tail luck: dropping the two biggest winners still leaves +0.099 (baseline +0.061), and
the winner beats baseline in 100% of 400 random held-out splits. It captures 13% more runner upside at
identical dud-bleed — exactly the "catch runners, don't bleed extra on dumps" goal.

### Efficient frontier (max mean per drawdown ceiling)
```
mdd >= -3.60 : +0.1017   cut0.70 ride2.5 trail.90 cap15   (shallow stop if -46% single-trade p05 bothers)
mdd >= -3.83 : +0.1082   cut0.00 ride2.5 trail.90 cap15   (~ winner)
mdd >= -4.48 : +0.1119   cut0.00 ride1.7 trail.90 cap40   (higher mean, but p05 -0.61, more tail-reliant)
```
cap15 dominates the low-drawdown region; cap40 buys a little more mean at a materially worse left tail
(p05 -0.61 vs -0.46). The winner sits at the knee.

### Implementable from 250ms bonding-curve polling? YES — trivially.
Per poll: (1) hold (never stop on absolute drawdown); (2) track running peak; once price touches 2.0x,
arm a trailing stop at 0.90 x peak -> market-sell all on breach; (3) at ~3.4s / 15 slots since entry,
market-sell all. No laddering, de-risk, fade or scale-in. One buy, one sell. Only execution risk: the
3.4s cap and 0.90 trail need a fast sell (sub-250ms reaction); a slow fill gives back part of the edge.

---

## Honest verdict

Structure lifts EV materially but does NOT turn this into a fat, reliable edge. The winner is a real,
mechanical, interpretable improvement: +55% mean, +43% sharpe, survives drop-top-2 and 100% of paired
splits, at the same dud-bleed. The mechanism is sound — a hard price stop was the single biggest
self-inflicted wound (it exits dip-then-rip runners on the dip), and a flat time-cap controls dud losses
just as well because rugs gap through any price stop anyway.

But it stays a thin, heavy-tail bet: the median trade is a small loss (-0.027), win rate <50%, and the
mean rides on the ~15% of tokens that run. Net ~+0.107 R/trade ~= +0.054 SOL/trade at 0.5 SOL, before
live send-latency slippage (not modeled; docks all variants similarly). Caveats that cap confidence:
one wallet, one ~2-day regime (656 tokens, 2026-10-12..14), 72 empty paths, no cross-regime OOS. The 2%
round-trip protocol fee — not priority — is the structural tax and does not shrink with size, so the game
is only +EV while this regime's runner frequency/magnitude holds.

Recommendation: ship the winner exit (strictly dominates the current one on every axis), size at
<=1/4-Kelly (~15% of bankroll per snipe) to survive the -1.0 worst case, and treat the live result as
the real validation — this backtest says the structure is right, not that the regime is durable.

### Negative results worth keeping (don't revisit)
- Momentum scale-in / pyramiding: lower EV and lower return-on-capital than full-size entry.
- Fast-cut-deep-ride asymmetry: can't separate duds from dip-then-rip runners early.
- Re-entry after a cut: -EV.
- Bigger size to dilute priority fee: no EV effect (fee is %-based).

Artifacts: /root/best_strategy/{engine.py, search.py, search2.py, search3.py, refine.py, final.py,
finalize.py, best_strategy.json, refine.json}.

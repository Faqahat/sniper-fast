#!/usr/bin/env python3
"""pos step 9 (read-only): haqq's FIRST buy of a trip -- which CAUSAL context at that buy predicts a long, active trip (3+ buys) and
the first lot's own P&L? Buckets of features measured before the buy (p1). Code-matched P&L. Out: p9.txt"""
import sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
from plib import *
P = Out(f"{OUT}/p9.txt")
B, LO, T = load()
F = [l for l in LO if l["kbuy"] == 1 and not l["probe"] and not T[l["trip_ix"]]["mayhem"] and not T[l["trip_ix"]]["gap"] and l["code"] not in (234, None)]
P(f"# First lots of trips (dead-curve bot 234 and probes excluded): {len(F):,}; share of trips reaching 3+ buys {100 * np.mean([T[l['trip_ix']]['nb'] >= 3 for l in F]):.1f}%")
feats = [("outside dumps on the token before", lambda b: b["dumps_before"], (0, 1, 2, 4, 8, 16, 1e9)),
         ("his own earlier trades on the token", lambda b: b["hq_trades_before"], (0, 1, 2, 4, 8, 1e9)),
         ("k-th trip of his on the token", lambda b: b["ktrip"], (1, 2, 3, 5, 1e9)),
         ("dump drop (biggest single sell, 5 slots)", lambda b: b["d_drop"], (0, 0.05, 0.08, 0.12, 0.2, 0.35, 1.01)),
         ("dump SOL", lambda b: b["d_sol"], (0, 0.5, 1, 2, 4, 1e9)),
         ("token age s", lambda b: 0.212 * (b["age"] or 0), (0, 2, 5, 15, 60, 300, 1e9)),
         ("curve SOL before", lambda b: b["vsol_pre"], (30, 35, 40, 50, 70, 1e9)),
         ("drawdown vs 10-slot high", lambda b: b["dd10"], (0, 0.03, 0.1, 0.2, 0.35, 1.01)),
         ("outside net flow, 3 slots", lambda b: b["bo3"] - b["so3"], (-1e9, -3, -1, 0, 1, 3, 1e9))]
for nm, f, ed in feats:
    P(f"\n### {nm}")
    P("| bucket | first lots | 3+ buy trips | first-lot mean mSOL | first-lot net SOL | whole-trip mean mSOL | days first-lot > 0 (D0..D5) |"); P("|---|---|---|---|---|---|---|")
    for a, b_ in zip(ed[:-1], ed[1:]):
        v = [l for l in F if a <= f(B[l["b"]]) < b_]
        if len(v) < 50: continue
        pd = [sum(l["cnet"] for l in v if l["day"] == d) for d in range(6)]
        P(f"| [{a:g}, {b_:g}) | {len(v):,} | {100 * np.mean([T[l['trip_ix']]['nb'] >= 3 for l in v]):.0f}% | {1000 * np.mean([l['cnet'] for l in v]):+.2f} | "
          f"{sum(l['cnet'] for l in v):+.2f} | {1000 * np.mean([T[l['trip_ix']]['net'] for l in v]):+.2f} | {sum(p > 0 for p in pd)}/6 |")
P.save()

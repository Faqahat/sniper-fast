#!/usr/bin/env python3
# Where (if anywhere) is the bait lift big enough? lift = restored-dump px/p0 minus matched base, at w=4.
# Break-even position P* = (2.5% * X + 0.0015) / lift.
import statistics as st, collections
import b4_match as M   # reuses loaded data (prints its tables first)
rows = [r for k in M.rest for r in M.rest[k] if M.cell(r) in M.bm]
def lift(rs, w='4'): return st.mean(r['out'][w][6] - M.bm[M.cell(r)][w][0] for r in rs)
def show(name, key, bins):
    print(f"\n-- by {name}")
    for lo, hi in bins:
        rs = [r for r in rows if lo <= key(r) < hi]
        if len(rs) < 200: continue
        L = lift(rs); X = st.mean(r['sell'] for r in rs)
        h = len(rs) // 2; L1 = lift(rs[:h]); L2 = lift(rs[h:])
        pstar = (2 * M.FEE * X + 0.0015) / L if L > 0 else float('inf')
        print(f"  {lo:>6}-{hi:<6} n={len(rs):6d}  lift={100*L:+.2f}%  (halves {100*L1:+.2f}/{100*L2:+.2f})  bait X={X:.2f}  break-even pos={pstar:.1f} SOL")
show("bait size (SOL)", lambda r: r['sell'], [(0.5, 0.7), (0.7, 1), (1, 1.5), (1.5, 3), (3, 99)])
show("drop caused by the sell", lambda r: -r['drop'], [(0, 0.02), (0.02, 0.04), (0.04, 0.07), (0.07, 0.12), (0.12, 1)])
show("trades in last 20 slots", lambda r: r['n20'], [(0, 4), (4, 11), (11, 26), (26, 50), (50, 9999)])
show("run-up last 20 slots", lambda r: r['r20'], [(0, 0.9), (0.9, 1.0), (1.0, 1.15), (1.15, 1.4), (1.4, 99)])
show("token age (slots)", lambda r: r['age'], [(15, 150), (150, 600), (600, 2001)])
show("curve SOL", lambda r: r['vsol'], [(28, 40), (40, 55), (55, 75), (75, 101)])

#!/usr/bin/env python3
# OOS check of the promising slices: rules picked from R1+R2 slices, shown per run (R3 = test). P&L per bait at
# position P, bait X = event sell size, exit at w=4; vs JUST HOLD (bait's own value) and vs SELL NOW.
import statistics as st
import b4_match as M
rows = [r for k in M.rest for r in M.rest[k] if M.cell(r) in M.bm]
RULES = {
  "curve 28-40": lambda r: r['vsol'] < 40,
  "fell >10% in 20 slots": lambda r: r['r20'] < 0.9,
  "curve<40 AND fell": lambda r: r['vsol'] < 40 and r['r20'] < 0.9,
  "curve<55 AND fell AND bait 0.5-1": lambda r: r['vsol'] < 55 and r['r20'] < 0.9 and r['sell'] < 1,
}
for name, f in RULES.items():
    print(f"\n== {name}")
    for run in ["R1", "R2", "R3"]:
        rs = [r for r in rows if r['run'] == run and f(r)]
        if not rs: continue
        L = st.mean(r['out']['4'][6] - M.bm[M.cell(r)]['4'][0] for r in rs)
        line = f"  {run} n={len(rs):5d} lift {100*L:+.2f}% |"
        for P in [1, 2, 3]:
            h = [P * (r['out']['4'][6] - M.bm[M.cell(r)]['4'][0]) - 2 * M.FEE * r['sell'] - 0.0015 for r in rs]
            g = [P * (r['out']['4'][6] - 1) - 2 * M.FEE * r['sell'] - 0.0015 for r in rs]
            line += f" P={P}: hold {st.mean(h):+.4f} / now {st.mean(g):+.4f} (med {st.median(g):+.4f}) |"
        print(line)

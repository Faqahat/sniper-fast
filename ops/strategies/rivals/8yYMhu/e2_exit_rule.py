#!/usr/bin/env python3
"""8yYMhu e2 (read-only): the exit rule's shape from his lots (exitpath.pkl): checkpoints at slots 3 and 6, the 61-slot timeout, and
sell-probability vs the position return at the decision point (end of the previous slot). Then a fitted rule replayed on his lots.
Out: DATA/e2.txt"""
import sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
EP = pickle.load(open(f"{X.D}/exitpath.pkl", "rb"))
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
P(f"lots {len(EP)}")
def ret_at(e, x): return e["path"][min(x, len(e["path"]) - 1)][1]
B = [-9, -0.15, -0.08, -0.04, -0.02, 0, 0.02, 0.04, 0.08, 0.15, 9]
for x in (3, 4, 5, 6, 7, 8, 10, 15, 20, 30, 45, 61):
    alive = [e for e in EP if e["hold"] >= x]
    if not alive: continue
    sold = [e for e in alive if e["hold"] == x]
    row = []
    for lo, hi in zip(B[:-1], B[1:]):
        a = [e for e in alive if lo <= ret_at(e, x - 1) < hi]
        s = [e for e in a if e["hold"] == x]
        row.append(f"{100*len(s)/len(a):3.0f}%({len(a)})" if len(a) >= 20 else "   -   ")
    P(f"slot {x:2}: alive {len(alive):5} sold {len(sold):5} ({100*len(sold)/len(alive):4.1f}%) | P(sell) by ret at end of slot x-1 in " +
      " ".join(f"[{100*lo:+.0f},{100*hi:+.0f})" for lo, hi in zip(B[:-1], B[1:])))
    P("        " + "  ".join(row))
h = np.array([e["hold"] for e in EP]); re = np.array([e["ret_exit"] for e in EP]); pn = np.array([e["pnl"] for e in EP])
for lab, m in (("sold at slot 3", h == 3), ("sold at slot 6", h == 6), ("sold 7-59", (h >= 7) & (h <= 59)), ("sold 60-62 (timeout)", (h >= 60) & (h <= 62)), ("other", (h < 3) | (h == 4) | (h == 5) | (h > 62))):
    P(f"{lab:22} lots {m.sum():5} ({100*m.mean():4.1f}%)  ret at exit p25/50/75 {100*X.pct(re[m],25):+.1f}/{100*X.med(re[m]):+.1f}/{100*X.pct(re[m],75):+.1f}%  net P&L {pn[m].sum():+8.2f} SOL  win {100*np.mean(pn[m]>0):.0f}%")
open(f"{X.D}/e2.txt", "w").write("\n".join(out) + "\n")

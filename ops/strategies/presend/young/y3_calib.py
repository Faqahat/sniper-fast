#!/usr/bin/env python3
"""YOUNG step 3: calibrate the expected-value simulator (ysim.esim) on LIVE armed triggers: expected fills and P&L
(at the live size, fixed cost 3.52 mSOL per fill, failed tries excluded on both sides) vs live realized, by age and run."""
import collections, statistics as st, json
from ylib import *
from ysim import esim
meta, R, TP = load()
live = [r for r in R if r["live"] == "armed" and TP.get(r["sig"])]
A = collections.defaultdict(lambda: [0, 0.0, 0, 0.0, 0.0])
rows = []
for r in live:
    size = (r["spend"] or 0) / 1e9
    e = esim(r, TP[r["sig"]], size=size, tp=0.20, sl=0.50, cost_rt=0.00352)
    lp = sum(x for x in r["real"] if x is not None) / 1e9
    g = "age1" if r["age"] == 1 else "age2+"
    for key in (g, (g, r["reg"] + r["run"]), ("all",), ("T" if is_test(r) else "train", g)):
        a = A[key]; a[0] += len(r["lfill"]) > 0; a[1] += e["p_fill"]; a[3] += lp; a[4] += e["pnl"]
    rows.append({"sig": r["sig"], "age": r["age"], "run": r["reg"] + r["run"], "lf": len(r["lfill"]) > 0, "lp": lp, "ep": e["pnl"], "pf": e["p_fill"]})
json.dump(rows, open(f"{D}/calib_rows.json", "w"))
print("key | live fills | sim exp fills | live P&L | sim exp P&L (SOL, at live size, no failed-try fees)")
for k in sorted(A, key=str):
    a = A[k]
    if isinstance(k, tuple) and len(k) == 2 and k[0] in ("age1", "age2+"): continue
    print(k, a[0], round(a[1], 1), round(a[3], 3), round(a[4], 3))
print("per run age1: live vs sim")
for k in sorted(A, key=str):
    if isinstance(k, tuple) and len(k) == 2 and k[0] == "age1":
        a = A[k]; print(" ", k[1], a[0], round(a[1], 1), f"{a[3]:+.3f} {a[4]:+.3f}")
pr = collections.defaultdict(lambda: [0, 0])
for k in A:
    if isinstance(k, tuple) and len(k) == 2 and k[0] in ("age1", "age2+"):
        pr[k[1]][0] += A[k][3]; pr[k[1]][1] += A[k][4]
xs = [v[0] for v in pr.values()]; ys = [v[1] for v in pr.values()]
print("per-run corr live vs sim", round(st.correlation(xs, ys), 3))
for k, v in sorted(pr.items()): print(f"  {k} live {v[0]:+.3f} sim {v[1]:+.3f}")

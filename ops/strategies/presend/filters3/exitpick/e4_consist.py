#!/usr/bin/env python3
"""EXITPICK step 4: any one-feature rule that pays in DEV AND VAL (and then HOLD)?  + decile tables of t1000/t400 gain by feature."""
import sys, statistics
from elib import *
R = load(); DL = sys.argv[1] if len(sys.argv) > 1 else "15"
A = sorted(R[0]["A"].keys()); B = sorted(R[0]["B"]["15"].keys()); C = ["c_" + k[2:] for k in B]
ACT = ["t100"] + EXT
sp = {s: [r for r in R if r["split"] == s] for s in ("dev", "val", "hold")}
res = []
for f in A + B:
    xs = {s: [feat(r, f, DL) for r in rows] for s, rows in sp.items()}
    qs = sorted(set(statistics.quantiles(xs["dev"] + xs["val"], n=10, method="inclusive")))
    for th in qs:
        for op in (">=", "<"):
            m = {s: [(a >= th) == (op == ">=") for a in xs[s]] for s in sp}
            if sum(m["dev"]) < 30 or sum(m["val"]) < 30: continue
            for k in ACT:
                g = {s: sum(gain(r, k) for r, mm in zip(sp[s], m[s]) if mm) for s in sp}
                res.append((min(g["dev"], g["val"]), g["dev"], g["val"], g["hold"], f, op, th, k, sum(m["dev"]), sum(m["val"]), sum(m["hold"])))
res.sort(key=lambda z: -z[0])
print(f"rules {len(res)}; positive on both DEV and VAL: {sum(1 for z in res if z[0] > 0)}; of those positive on HOLD too: {sum(1 for z in res if z[0] > 0 and z[3] > 0)}")
print(" best by min(DEV,VAL):  dev | val | hold   rule   n")
for z in res[:25]:
    print(f"  {z[1]:+.3f} | {z[2]:+.3f} | {z[3]:+.3f}   {z[4]} {z[5]} {z[6]:.4g} -> {z[7]}   {z[8]}/{z[9]}/{z[10]}")

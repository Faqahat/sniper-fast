#!/usr/bin/env python3
"""EXITPICK step 5: gain vs t125 by bins of one feature, per split and per run (is the dump-size effect real and stable?)"""
import sys
from elib import *
R = load()
f = sys.argv[1]; edges = [float(a) for a in sys.argv[2].split(",")]; ks = sys.argv[3].split(",")
var = sys.argv[4] if len(sys.argv) > 4 else "y"
def b(v):
    for i, e in enumerate(edges):
        if v < e: return i
    return len(edges)
lab = [f"<{edges[0]}"] + [f"{edges[i]}-{edges[i+1]}" for i in range(len(edges) - 1)] + [f">={edges[-1]}"]
groups = [("dev", lambda r: r["split"] == "dev"), ("val", lambda r: r["split"] == "val"), ("hold", lambda r: r["split"] == "hold")] + \
         [(f"r{n}", (lambda n: lambda r: r["run"] == n)(n)) for n in (42, 43, 44, 48, 49, 50)] + [("r45-47", lambda r: r["run"] in (45, 46, 47))]
print(f"{f} bins {lab}  var {var}; cell = n / t125 SOL / gain of " + ",".join(ks))
for name, cond in groups:
    rows = [r for r in R if cond(r)]
    cells = []
    for i in range(len(lab)):
        rr = [r for r in rows if b(feat(r, f)) == i]
        cells.append(f"{len(rr):>4} {sum(y(r,'t125',var) for r in rr):+6.2f} " + " ".join(f"{sum(gain(r, k, var) for r in rr):+5.2f}" for k in ks))
    print(f"{name:>7} | " + " | ".join(cells))

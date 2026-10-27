#!/usr/bin/env python3
"""CLIENTS study: inside close pairs of reacting buys (<= 10 txs apart, same block), which fee metric predicts the order better:
CU price (fee per requested CU) or total priority fee (lamports = CU price x CU limit)? (MEASURED; tips not included)"""
import json, sys, collections
M = json.load(open(sys.argv[1]))
def cls(c):
    if c == "HarmonicAgave": return "harmonic"
    if c in ("HarmonicFiredancer", "HarmonicFrankendancer"): return "harmonicFD"
    return {"JitoLabs": "jito", "AgaveBam": "bam", "FireBAM": "firebam", "Firedancer": "fd", "Frankendancer": "fd", "Rakurai": "rakurai", "Agave": "agave"}.get(c, "other")
agg = collections.defaultdict(lambda: [0, 0, 0])   # pairs where metrics DISAGREE: n, cup right, total right
for d in M["dumps"]:
    rs = [r for r in d[4] if r[3] is not None and r[4]]
    k = cls(d[7])
    for a in range(len(rs)):
        for b in range(a + 1, len(rs)):
            x, y = rs[a], rs[b]
            if y[1] - x[1] > 10: continue
            cx, cy = x[3], y[3]; tx, ty = x[3] * x[4], y[3] * y[4]
            if cx == cy or tx == ty: continue
            if (cx > cy) == (tx > ty): continue     # metrics agree: no information
            agg[k][0] += 1; agg[k][1] += cx > cy; agg[k][2] += tx > ty
print("pairs where CU price and total priority fee disagree: share where the EARLIER tx is the higher one")
for k in ["bam", "firebam", "harmonic", "harmonicFD", "jito", "fd", "rakurai"]:
    n, c, t = agg[k]
    if n: print(f"{k:11s} n={n:5d}  by CU price {c/n:.2f}   by total priority fee {t/n:.2f}")

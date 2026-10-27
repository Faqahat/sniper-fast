#!/usr/bin/env python3
"""CLIENTS study: inside one block, among the first reacting buys after a dump, is the EARLIER one the higher CU price? (MEASURED)
Pairs of reacting buys (both set a CU price, different prices). 0.5 = order unrelated to price (arrival); >0.5 = price sorts them.
Split by index distance between the two (close pairs are more likely in the same scheduler batch / auction round)."""
import json, sys, collections
M = json.load(open(sys.argv[1]))
def cls(c):
    if c == "HarmonicAgave": return "harmonic"
    if c in ("HarmonicFiredancer", "HarmonicFrankendancer"): return "harmonicFD"
    return {"JitoLabs": "jito", "AgaveBam": "bam", "FireBAM": "firebam", "Firedancer": "fd", "Frankendancer": "fd", "Rakurai": "rakurai", "Agave": "agave"}.get(c, "other")
agg = collections.defaultdict(lambda: [0, 0])
for d in M["dumps"]:
    s, di, n, sol, reacts, nf, navail, c, tp = d
    rs = [r for r in reacts if r[3] is not None]
    k = cls(c)
    for a in range(len(rs)):
        for b in range(a + 1, len(rs)):
            x, y = rs[a], rs[b]
            if x[3] == y[3]: continue
            dist = y[1] - x[1]
            band = "<=5" if dist <= 5 else ("6-20" if dist <= 20 else ">20")
            agg[(k, band)][0] += 1; agg[(k, band)][1] += x[3] > y[3]
print("client      pairs<=5 idx apart     6-20 apart          >20 apart     (share where the earlier tx paid the higher CU price)")
for k in ["bam", "firebam", "harmonic", "harmonicFD", "jito", "agave", "fd", "rakurai"]:
    print(f"{k:11s} " + "   ".join(f"{agg[(k,b)][1]/max(1,agg[(k,b)][0]):.3f} (n={agg[(k,b)][0]:6d})" for b in ("<=5", "6-20", ">20")))

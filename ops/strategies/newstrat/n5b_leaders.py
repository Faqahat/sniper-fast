#!/usr/bin/env python3
"""inspect LEADFOL leaders (fit-day selection) and their 10-31 results"""
import sys, json
import numpy as np
import nlib as L
from n5_scan import ev, one_pos, day_stats, FIT, CH
k = int(sys.argv[1]) if len(sys.argv) > 1 else 25; NMIN = int(sys.argv[2]) if len(sys.argv) > 2 else 10
E = {r: ev(r) for r in FIT + [CH]}
key = f"d70k{k}"
per = {}
for r in FIT + [CH]:
    d = E[r]; names = d["users"][d["u"]]
    uu, inv = np.unique(names, return_inverse=True)
    n = np.bincount(inv); s = np.bincount(inv, weights=d[key].astype(np.float64))
    sp = np.bincount(inv, weights=d["spend"]); ag = np.bincount(inv, weights=np.minimum(d["age"], 1e5)); pcs = np.bincount(inv, weights=d["pc"])
    nmint = {}
    for j, u in enumerate(uu): pass
    per[r] = {u: (n[j], s[j], sp[j] / n[j], ag[j] / n[j]) for j, u in enumerate(uu)}
common = set.intersection(*[set(u for u, v in per[r].items() if v[0] >= NMIN and v[1] >= 0) for r in FIT])
print("leaders", len(common))
rows = []
for u in common:
    f = [per[r][u] for r in FIT]; c = per[CH].get(u, (0, 0, 0, 0))
    rows.append((sum(x[1] for x in f), u, [int(x[0]) for x in f], [round(x[1] / x[0] / 1e6, 1) for x in f], round(np.mean([x[2] for x in f]), 2), int(np.mean([x[3] for x in f])), int(c[0]), round(c[1] / 1e9, 2), round(c[1] / max(c[0], 1) / 1e6, 1)))
rows.sort(reverse=True)
print("fitSOL leader fit_n fit_mSOL avg_spend avg_age | 10-31 n SOL mSOL")
for x in rows[:40]: print(round(x[0] / 1e9, 1), x[1], x[2], x[3], x[4], x[5], "|", x[6], x[7], x[8])
oos = sorted([(x[7], x[1], x[6]) for x in rows], reverse=True)
print("10-31 contribution top 10:", oos[:10]); print("bottom 5:", oos[-5:])
print("10-31 leaders active:", sum(1 for x in rows if x[6] > 0), "positive:", sum(1 for x in rows if x[7] > 0))
json.dump([list(map(str, x)) for x in rows], open(f"{L.OUT}/leaders_k{k}_n{NMIN}.json", "w"))

#!/usr/bin/env python3
"""SELECT s7: who buys right after E2x1 (same slot after his row .. +2 slots)? Copy-trader test: wallets that follow him on many of
his buys relative to their total activity. Also: SOL these followers put in after his buys, and how his buys' 1 s forward return
depends on followers. Out: s7.txt"""
import sys, collections, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"]); MN, US = names()
sl = D["slot"].astype(np.int64); us = D["user"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9; mi = D["mint"]
mine = np.flatnonzero((us == w) & bu)
fol = collections.Counter(); folsol = collections.defaultdict(float); nb = len(mine)
per = []
for R in mine:
    a, e = span(D, int(mi[R])); s = sl[R]
    hi = a + int(np.searchsorted(sl[a:e], s + 2, side="right"))
    seen = set(); fs = 0.0
    for q in range(R + 1, hi):
        if bu[q] and us[q] != w:
            fs += so[q]
            if us[q] not in seen: seen.add(int(us[q])); fol[int(us[q])] += 1; folsol[int(us[q])] += so[q]
    per.append((len(seen), fs))
# activity: number of distinct (mint) buys per wallet in whole tape (for the top followers)
top = fol.most_common(40)
tot = collections.Counter()
ids_top = set(u for u, _ in top)
msk = np.isin(us, list(ids_top)) & bu
for u, m in set(zip(us[msk].tolist(), mi[msk].tolist())): tot[u] += 1
print(f"his buys {nb}")
print("wallet                                         follows  share_of_his  their_mints  frac_of_their_mints  sol")
for u, n in top[:30]:
    print(f"{US[u]:46s} {n:6d}  {n/nb:6.3f}  {tot[u]:8d}  {n/max(tot[u],1):6.3f}  {folsol[u]:8.1f}")
P = np.array(per)
print("followers within 2 slots: median n", np.median(P[:, 0]), "median SOL", np.median(P[:, 1]), "mean SOL", P[:, 1].mean())
json.dump({"top": [(US[u], n, tot[u]) for u, n in top]}, open(f"{OUT}/s7_top.json", "w"))
np.save(f"{OUT}/s7_per.npy", P)

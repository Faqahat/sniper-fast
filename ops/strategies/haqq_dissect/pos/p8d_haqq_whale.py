#!/usr/bin/env python3
"""pos step 8d (read-only): haqq's REAL lots (code-matched, his costs) on the p8 whale-dump groups (lots bought <= 2 slots after the dump).
Out: p8d.txt"""
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
from plib import Out, OUT
P = Out(f"{OUT}/p8d.txt")
Z = np.load(f"{L.D}/uni.npz"); X = Z["X"]; M = Z["M"]
P5 = np.load(f"{OUT}/p5.npz"); P8 = np.load(f"{OUT}/p8b.npz"); ideal2 = P8["ideal2"]
hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
bt = M["bt"].astype(np.int64); usable = np.isin((bt + 18000) // 3600 * 3600 - 18000, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
wh = np.flatnonzero(X[:, 2] >= 6.0)
o = wh[np.lexsort((M["cc"][wh], M["mint"][wh]))]
kw = {}; prevpay = {}; prevslot = {}; last = None
for i in o:
    m = int(M["mint"][i])
    if last is None or last[0] != m: kw[i] = 1; last = (m, i); continue
    kw[i] = kw[last[1]] + 1; prevpay[i] = ideal2[last[1]]; prevslot[i] = int(M["slot"][last[1]]); last = (m, i)
rows = [i for i in wh if usable[i] and np.isfinite(ideal2[i])]
G = {"first": lambda i: kw[i] == 1, "rearm_paid": lambda i: kw[i] >= 2 and prevpay.get(i, -1) >= 0.02 and M["slot"][i] > prevslot[i] + 2,
     "rearm_notpaid": lambda i: kw[i] >= 2 and prevpay.get(i, 1) < 0.02 and M["slot"][i] > prevslot[i] + 2, "within2": lambda i: kw[i] >= 2 and M["slot"][i] <= prevslot[i] + 2}
P("| group | whale dumps | haqq bought (share) | haqq lots | haqq mSOL/lot | haqq net SOL | haqq held the token at the dump |")
P("|---|---|---|---|---|---|---|")
for nm, f in G.items():
    v = np.array([i for i in rows if f(i)])
    n = P5["hq_n"][v]; h = P5["hq_net"][v]
    P(f"| {nm} | {len(v):,} | {100 * (n > 0).mean():.1f}% | {n.sum():,} | {1000 * h.sum() / max(n.sum(), 1):+.2f} | {h.sum():+.2f} | {100 * P5['hq_open'][v].mean():.0f}% |")
P.save()

#!/usr/bin/env python3
"""pos step 12 (read-only): robustness splits of the re-arm group (p8c values): same seller as the previous whale dump vs a different
whale; fill limit 0.88 vs 0.92 / 0.85 sensitivity is NOT recomputed here (values are p8c's 0.88). Out: p12.txt"""
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
from plib import Out, OUT
P = Out(f"{OUT}/p12.txt")
ids, idm = L.ids_map(); our = [idm[w] for w in L.WAL.values() if w in idm]
T = np.load(f"{L.TAB}/trades.npy", mmap_mode="r")
keep = ~np.isin(np.asarray(T["user"]), our); mi = np.asarray(T["mint"])[keep]; o = np.argsort(mi, kind="stable")
US = np.asarray(T["user"])[keep][o].astype(np.int64); del keep, mi, o
Z = np.load(f"{L.D}/uni.npz"); X = Z["X"]; M = Z["M"]
hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
bt = M["bt"].astype(np.int64); usable = np.isin((bt + 18000) // 3600 * 3600 - 18000, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
C = np.load(f"{OUT}/p8c.npz"); val = C["ps_val"]; fil = C["ps_fill"]; ideal2 = C["ideal2"]
wh = np.flatnonzero(X[:, 2] >= 6.0); o = wh[np.lexsort((M["cc"][wh], M["mint"][wh]))]
prev = {}; last = None
for i in o:
    m = int(M["mint"][i])
    if last is not None and last[0] == m: prev[i] = last[1]
    last = (m, i)
g = [i for i in wh if usable[i] and i in prev and ideal2[prev[i]] >= 0.02 and 3 <= M["slot"][i] - M["slot"][prev[i]] <= 52 and M["age"][prev[i]] * 0.212 <= 120]
same = [i for i in g if US[M["row"][i]] == US[M["row"][prev[i]]]]; diff = [i for i in g if US[M["row"][i]] != US[M["row"][prev[i]]]]
for nm, v in (("re-arm rule set (X 0.02, gap 3-52, age<=120 s)", g), ("same seller as the paid whale dump", same), ("a different whale", diff)):
    v = np.array(v); P(f"- {nm}: {len(v):,} dumps, fill {100 * fil[v].mean():.0f}%, per fill {1000 * val[v].sum() / max(fil[v].sum(), 1e-9):+.2f} mSOL, ideal {1000 * np.nanmean(ideal2[v]):+.2f}")
# previous paid dump size: was the previous whale dump itself bought by fast bots (rebound inside 2 slots)?
P.save()

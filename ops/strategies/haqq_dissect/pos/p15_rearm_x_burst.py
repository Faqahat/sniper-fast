#!/usr/bin/env python3
"""pos step 15 (read-only): the re-arm rule set (p12: whale dump >= 6% supply, previous whale dump on the token paid >= +5% in 2 slots,
gap 3-52 slots, age <= 120 s) split by prior burst slots / repeat burst wallets (p14). Pre-send-style values from p8c. Out: p15.txt"""
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
from plib import Out, OUT
P = Out(f"{OUT}/p15.txt")
Z = np.load(f"{L.D}/uni.npz"); X = Z["X"]; M = Z["M"]
hrs = json.load(open(f"{L.D}/hours.json")); good = {r["h"] for r in hrs["rows"] if r["usable"]}
bt = M["bt"].astype(np.int64); usable = np.isin((bt + 18000) // 3600 * 3600 - 18000, list(good)) & ~np.load(f"{L.D}/mayhem.npy")
C = np.load(f"{OUT}/p8c.npz"); val = C["ps_val"]; fil = C["ps_fill"]; ideal2 = C["ideal2"]
B14 = np.load(f"{OUT}/p14.npz"); nb = B14["nb"]; nr = B14["nr"]
wh = np.flatnonzero(X[:, 2] >= 6.0); o = wh[np.lexsort((M["cc"][wh], M["mint"][wh]))]
prev = {}; last = None
for i in o:
    m = int(M["mint"][i])
    if last is not None and last[0] == m: prev[i] = last[1]
    last = (m, i)
g = np.array([i for i in wh if usable[i] and i in prev and ideal2[prev[i]] >= 0.02 and 3 <= M["slot"][i] - M["slot"][prev[i]] <= 52 and M["age"][prev[i]] * 0.212 <= 120])
P(f"# re-arm rule set {len(g):,} dumps, split by prior bursts (pre-send-style per fill, mSOL)")
for nm, f in (("bursts 0", nb[g] == 0), ("1", nb[g] == 1), ("2-3", (nb[g] >= 2) & (nb[g] <= 3)), ("4+", nb[g] >= 4), ("repeat wallets 0", nr[g] == 0), ("repeat wallets 1+", nr[g] >= 1)):
    v = g[f]
    if len(v): P(f"- {nm}: {len(v):,} dumps, fill {100 * fil[v].mean():.0f}%, per fill {1000 * val[v].sum() / max(fil[v].sum(), 1e-9):+.2f}")
P.save()

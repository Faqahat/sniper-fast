#!/usr/bin/env python3
"""VERIFY v10: why do G2's rsim and my re-implementation diverge on the FRESH tape (+0.37 vs ~0) while agreeing in-sample?
Per re window (mint, dump slot): fill probability and mean fill P&L (after 2.015 mSOL) in each model; groups by who fills.
usage: v10_diverge.py RSIMPKL MINEPKL"""
import sys, pickle, collections
import numpy as np
COST = 5120 + 200_000 + 605_000 + 1_200_000 + 5020; FAIL = 5120
A = pickle.load(open(sys.argv[1], "rb")); name = A["cfg"]["name"]; B = pickle.load(open(sys.argv[2], "rb"))
RS = collections.defaultdict(lambda: [0, 0.0, 0, 0.0]); nd = len(A["out"][name])
for rows in A["out"][name]:
    for r in rows:
        k = r[0]
        if k[0] != "re" or not r[1]: continue
        key = (k[1], k[2] - 3); a = RS[key]; a[2] += 1; a[3] -= r[4] * FAIL / 1e9
        if r[3]: a[0] += 1; a[1] += (r[8][2]["base"][0] - COST) / 1e9
MI = collections.defaultdict(lambda: [0, 0.0, 0, 0.0])
for r in B["rows"]:
    a = MI[(r["mint"], r["s"])]; a[2] += 1; a[3] -= r["fees"] / 1e9
    if r["fill"] is not None and not r["base_has"]: a[0] += 1; a[1] += (r["fill"]["ex"]["live"] - COST) / 1e9
keys = set(RS) | set(MI)
G = collections.defaultdict(lambda: np.zeros(6))
for k in keys:
    a = RS.get(k); b = MI.get(k)
    pa = a[0] / nd if a else 0; pb = b[0] / B["seeds"] if b else 0
    va = a[1] / nd if a else 0; vb = b[1] / B["seeds"] if b else 0
    grp = ("both" if pa > 0 and pb > 0 else "rsim only" if pa > 0 else "mine only" if pb > 0 else "neither") + ("" if a and b else " (window in one model only)")
    G[grp] += [1, pa, va, pb, vb, (a[3] / nd if a else 0) - (b[3] / B["seeds"] if b else 0)]
print("| Group | Windows | rsim fills/draw | rsim fill P&L SOL | mine fills/seed | mine fill P&L SOL | fee diff rsim-mine |")
print("|---|---|---|---|---|---|---|")
for g, v in sorted(G.items()):
    print(f"| {g} | {v[0]:.0f} | {v[1]:.1f} | {v[2]:+.3f} | {v[3]:.1f} | {v[4]:+.3f} | {v[5]:+.3f} |")
# on windows both fill: per-window P&L when filled, paired
pa = []; pb = []
for k in keys:
    a = RS.get(k); b = MI.get(k)
    if a and b and a[0] and b[0]: pa.append(a[1] / a[0]); pb.append(b[1] / b[0])
pa = np.array(pa) * 1e3; pb = np.array(pb) * 1e3
print(f"windows filled in both: {len(pa)}; mean P&L per fill rsim {pa.mean():+.2f} vs mine {pb.mean():+.2f} mSOL; median diff {np.median(pa - pb):+.2f}; corr {np.corrcoef(pa, pb)[0, 1]:.2f}")

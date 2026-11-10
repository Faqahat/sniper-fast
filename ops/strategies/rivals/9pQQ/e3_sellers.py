#!/usr/bin/env python3
"""9pQQ exit trigger, seller side: for every outside SELL during its holds, P(9pQQ sells within 1 slot after it) by the seller's
share of supply sold, whether the seller exits fully, the seller's holding before, and the price drop it causes.  Read-only.
usage: e3_sellers.py"""
import pickle, numpy as np, collections, json
import tlib9 as L
rows = []
for r in L.RUNS:
    t = L.load_tape(r); wid = t.user_ix[L.W]
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x.get("tape_ok") and x["net"] is not None]
    for x in T:
        mi = t.mint_ix[x["mint"]]; a0 = t.mstart[mi]; a1 = t.mstart[mi + 1]
        S = t.s[a0:a1]; I = t.i[a0:a1]; U = t.u[a0:a1]; TK = t.tok[a0:a1]; CP = t.cpre[a0:a1]; CQ = t.cpost[a0:a1]
        key = S * 10000 + I
        jb = int(np.searchsorted(key, x["bs"] * 10000 + x["bi"])); js = int(np.searchsorted(key, x["ss"] * 10000 + x["si"]))
        if js >= len(S) or U[js] != wid: continue
        last = js - 1
        while last > jb and U[last] == wid: last -= 1
        # holdings before each trade (whole recorded history on this mint)
        uq, inv = np.unique(U[:js], return_inverse=True)
        bal = collections.defaultdict(float)
        for k in range(jb + 1):
            bal[U[k]] += TK[k]
        for k in range(jb + 1, js):
            u = U[k]; before = bal[u]; bal[u] += TK[k]
            if u == wid or TK[k] >= 0: continue
            share = -TK[k] / 1e15
            full = bal[u] <= max(1e9, 0.01 * before)
            drop = 1 - L.price(CQ[k]) / L.price(CP[k])
            rows.append((share, float(full), before / 1e15, drop, float(k == last and x["ss"] - S[k] <= 1), r == L.RUNS[-1]))
a = np.array(rows)
share, full, before, drop, y, last = a.T
def tab(name, v, bins):
    i = np.digitize(v, bins); s = []
    for k in range(len(bins) + 1):
        m = i == k
        if m.sum() > 200: s.append(f"[{bins[k-1] if k else '-inf'}: {y[m].mean():.3f} n{int(m.sum())}]")
    print(name, " ".join(s))
print("outside sells in holds", len(a), "trigger rate", round(y.mean(), 4))
tab("share of supply sold", share, [0.001, 0.003, 0.005, 0.01, 0.02, 0.03, 0.05])
tab("price drop", drop, [0.005, 0.01, 0.02, 0.03, 0.05, 0.08, 0.12])
tab("seller holding before (share)", before, [0.001, 0.005, 0.01, 0.02, 0.05])
print("full exit", round(y[full == 1].mean(), 4), int((full == 1).sum()), "partial", round(y[full == 0].mean(), 4))
for lo, hi in ((0.03, 0.05), (0.05, 0.08), (0.08, 1)):
    m = (drop >= lo) & (drop < hi)
    print(f"drop [{lo},{hi}) full {y[m & (full == 1)].mean():.3f} partial {y[m & (full == 0)].mean():.3f}")

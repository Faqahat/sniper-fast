#!/usr/bin/env python3
"""FLATSIG explore [DEV only]: the same causal trigger features on OUR live positions -> flat share / mean P&L per bin."""
import pickle, numpy as np, sys, os, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flib as L
T = pickle.load(open(f"{L.D}/trig.pkl", "rb")); X = T["X"]; M = T["meta"]; C = T["cols"]
ci = {c: i for i, c in enumerate(C)}
P = {p["id"]: p for p in L.all_positions()}
rows = []
for k, m in enumerate(M):
    for pid in m["ours"]: rows.append((pid, k))
per = sys.argv[1] if len(sys.argv) > 1 else "DEV"
kind = sys.argv[2] if len(sys.argv) > 2 else "T2"
sel = [(P[pid], k) for pid, k in rows if P[pid]["per"] == per and (kind == "all" or P[pid]["kind"] == kind)]
pnl = np.array([p["pnl"] for p, _ in sel]); fl = np.array([p["cls"] == "flat" for p, _ in sel]); win = np.array([p["cls"] == "win" for p, _ in sel])
XX = X[[k for _, k in sel]]
print(per, kind, "n", len(sel), "mean", round(pnl.mean() * 1000, 1), "flat", round(fl.mean(), 2))
for c in C:
    v = XX[:, ci[c]]
    qs = np.unique(np.quantile(v, [0, .2, .4, .6, .8, 1.0]))
    out = []
    for lo, hi in zip(qs[:-1], qs[1:]):
        mm = (v >= lo) & (v <= hi if hi == qs[-1] else v < hi)
        if mm.sum() < 20: continue
        out.append(f"[{lo:.3g},{hi:.3g}) n{mm.sum()} {pnl[mm].mean()*1000:+.1f} fl{fl[mm].mean():.2f} w{win[mm].mean():.2f}")
    print(f"{c:12s}", " | ".join(out))

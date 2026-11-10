#!/usr/bin/env python3
"""FLATSIG explore [DEV only]: on the chain-wide T2-like triggers (pump curve vsol>=28, >=1 SOL, age>=2 slots, in span, 12% dip within 10 slots),
how does each causal feature relate to 'a NAMED / COH bot bought within 2 slots after the dip' (bots' selection label)?
Quantile bins, rate per bin."""
import pickle, numpy as np, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flib as L
T = pickle.load(open(f"{L.D}/trig.pkl", "rb")); X = T["X"]; M = T["meta"]; C = T["cols"]
ci = {c: i for i, c in enumerate(C)}
bt = np.array([m["bt"] for m in M]); dip = np.array([m["dip"] for m in M]); span = np.array([m["in_span"] for m in M])
age = X[:, ci["age"]]
dN = np.array([m.get("dN2", 0) > 0 for m in M]); dC = np.array([m.get("dC2", 0) > 0 for m in M]); dA = np.array([m.get("dAll2", 0) > 0 for m in M])
base = span & dip & (age >= 2) & (bt < L.CUT / 1e9) & (X[:, ci["vsol_pre"]] >= 28) & (X[:, ci["sol"]] >= 1)
print("DEV triggers w/ dip", base.sum(), "named-bot-after-dip rate", dN[base].mean().round(3), "coh", dC[base].mean().round(3), "any", dA[base].mean().round(3))
for c in C:
    v = X[base, ci[c]]
    qs = np.unique(np.quantile(v, [0, .2, .4, .6, .8, 1.0]))
    out = []
    for lo, hi in zip(qs[:-1], qs[1:]):
        mm = (v >= lo) & (v <= hi if hi == qs[-1] else v < hi)
        if mm.sum() < 50: continue
        out.append(f"[{lo:.3g},{hi:.3g}) n{mm.sum()} N{dN[base][mm].mean():.2f} C{dC[base][mm].mean():.2f}")
    print(f"{c:12s}", " | ".join(out))

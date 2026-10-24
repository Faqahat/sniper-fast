#!/usr/bin/env python3
# Guard-aware dip model for slow landing: label = (filled under the price guard) AND (profitable). A refused (guarded) buy costs
# FAILC SOL. Six-block CV; report guarded totals for top 5/10/20%. Env: EVF, EXIT, LATS, GUARD (default 1.02), FAILC (0.0002).
import os, sys, json, gzip
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import gbdt_np as G
from dipcv import FK, fv
EVF = os.environ["EVF"]; EXIT = os.environ.get("EXIT", "2"); GD = float(os.environ.get("GUARD", "1.02")); FAILC = float(os.environ.get("FAILC", "0.0002")); K = 6
R = [json.loads(l) for l in gzip.open(EVF, "rt")]; R.sort(key=lambda r: r["bt"] + r["age"])
for LAT in os.environ.get("LATS", "75").split(","):
    rows = [r for r in R if LAT in r["pnl"] and EXIT in r["pnl"][LAT]]
    X = np.array([fv(r) for r in rows]); P = np.array([r["pnl"][LAT][EXIT] for r in rows])
    px = np.array([r.get("px", {}).get(LAT, 1.0) for r in rows]); fill = px <= GD
    V = np.where(fill, P, -FAILC); y = (fill & (P > 0)).astype(float)
    n = len(rows); blk = np.minimum((np.arange(n) * K) // n, K - 1); rng = np.random.default_rng(1)
    res = {q: [0.0, 0, 0, []] for q in (0.05, 0.10, 0.20)}
    for b in range(K):
        trall = blk != b; va = trall & (rng.random(n) < 0.15); tr = trall & ~va; te = blk == b
        Bm = G.binize(X, tr); trees, f = G.fit(Bm, y, tr, va, rounds=300, lr=0.05, depth=3)
        for q in res:
            st = te & (f >= np.quantile(f[va], 1 - q))
            res[q][0] += V[st].sum(); res[q][1] += int((st & fill).sum()); res[q][2] += int(st.sum()); res[q][3].append(round(float(V[st].sum()), 2))
    print(f"LAT {LAT} exit {EXIT} guard {GD}: " + " | ".join(f"top {q:.0%}: total {v[0]:+.2f} (fills {v[1]}/{v[2]}) blocks {v[3]}" for q, v in res.items()))

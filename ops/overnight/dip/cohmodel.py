#!/usr/bin/env python3
# Does knowing the bot cohort (defined on R1 only) improve dip selection on R2? R2 events only; time split: train first 60%
# (last 15% of it = early stop / threshold), test last 40%. Base 35 features vs + cohort features. Exit 4 slots.
import sys, os, json, gzip
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbdt_np as G
from dipcv import FK, fv
CF = ["coh_n", "coh_20", "coh_seller", "coh_sol", "coh_held"]
R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/dip/ev4_coh.jsonl.gz", "rt")]
R = [r for r in R if r["run"] == "R2"]; R.sort(key=lambda r: r["bt"] + r["age"])
for LAT in ("35", "50"):
    rows = [r for r in R if LAT in r["pnl"]]
    P = np.array([r["pnl"][LAT]["4"] for r in rows]); y = (P > 0).astype(float); n = len(rows)
    TRall = np.arange(n) < int(n * 0.6); TR = np.arange(n) < int(n * 0.51); VA = TRall & ~TR; TE = ~TRall
    for nm, extra in (("base", []), ("+cohort", CF)):
        X = np.array([fv(r) + [float(r["xf"].get(k, 0)) for k in extra] for r in rows])
        Bm = G.binize(X, TR); trees, f = G.fit(Bm, y, TR, VA, rounds=400, lr=0.05, depth=3)
        names = FK + extra; acc = np.zeros(len(names))
        for t in trees: G.imp(t, acc)
        out = []
        for q in (0.02, 0.05, 0.10):
            thr = np.quantile(f[VA], 1 - q); st = TE & (f >= thr)
            out.append(f"top{q:.0%} n {st.sum()} mean {P[st].mean() if st.sum() else 0:+.4f} total {P[st].sum():+.2f}")
        top = ", ".join(f"{names[j]} {acc[j] / acc.sum():.0%}" for j in np.argsort(-acc)[:5])
        print(f"L{LAT} {nm:8s} AUC test {G.auc(y[TE], f[TE]):.3f} | " + " | ".join(out) + f" | top feats: {top}")

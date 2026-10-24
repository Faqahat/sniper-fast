#!/usr/bin/env python3
# Freeze DIP4 models (sell 4 slots later, follower slippage imputed, our sell 75 ms into its slot; base + richer features) for
# the forward test. Train on all events up to the freeze (first 85% by time train, last 15% early stop + thresholds).
import sys, os, json, gzip, time, hashlib
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gbdt_np as G
from dipcv import FK, fv, PRO6, SN8
LAT = os.environ.get("LAT", "35"); EXIT = "4"
R = [json.loads(l) for l in gzip.open("/home/moiz/sniper/ops/overnight/dip/ev4_b05.jsonl.gz", "rt")]
R = [r for r in R if LAT in r["pnl"]]; R.sort(key=lambda r: r["bt"] + r["age"])
X = np.array([fv(r) for r in R]); P = np.array([r["pnl"][LAT][EXIT] for r in R]); y = (P > 0).astype(float)
n = len(R); TR = np.arange(n) < int(n * 0.85); VA = ~TR
edges = []
for j in range(X.shape[1]):
    xt = X[TR, j]; xt = xt[~np.isnan(xt)]; edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])).tolist())
Bm = np.zeros(X.shape, np.int16)
for j in range(X.shape[1]):
    b = np.searchsorted(np.array(edges[j]), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; Bm[:, j] = b
trees, f = G.fit(Bm, y, TR, VA, rounds=400, lr=0.05, depth=3)
p0 = y[TR].mean(); F0 = float(np.log(p0 / (1 - p0))); freeze = time.time()
thr = {f"{q:.0%}": float(np.quantile(f[VA], 1 - q)) for q in (0.02, 0.05, 0.10)}
val = {k: dict(n=int((VA & (f >= t)).sum()), mean=float(P[VA & (f >= t)].mean())) for k, t in thr.items()}
out = dict(name=f"FRZ-DIP4-L{LAT}", strategy="buy 0.5 SOL right after a >=1 SOL sell on a launch aged 1-120 s if score >= threshold; sell 4 slots later",
           label=f"pnl>0, entry {LAT} ms after the sell (block-position proxy), exit 4 slots (our sell 75 ms into its slot), follower slippage imputed, 0.0008 SOL/tx",
           features=FK, sn8=sorted(SN8), pro6=list(PRO6), edges=edges, trees=trees, F0=F0, lr=0.05, thresholds=thr, val=val,
           n_train=int(TR.sum()), n_val=int(VA.sum()), last_event_time=R[-1]["bt"] + R[-1]["age"], frozen_at=freeze,
           frozen_at_pkt=time.strftime("%Y-%m-%d %H:%M", time.gmtime(freeze + 18000)) + " PKT")
fn = f"/home/moiz/sniper/ops/overnight/dip/frozen_dip4_L{LAT}.json"; s = json.dumps(out); open(fn, "w").write(s)
h = hashlib.sha256(s.encode()).hexdigest(); open(fn + ".sha256", "w").write(h + "\n")
print(out["name"], out["frozen_at_pkt"], "sha256", h[:12], "trees", len(trees), "val", val)

#!/usr/bin/env python3
# Freeze the IMITATION selector (local only): GBDT trained on TRAIN hours (fit = first 80%, early stop on the last 20%) to
# predict "one of HkQ7hMjy / DYXDDrZC / haqqiUUX buys right after this dump", inside the watch envelope, dump-time features
# only. Saves trees + bin edges + feature list + envelope + thresholds for top 2% / 4% / 8% (of the last 20% of TRAIN) and
# the chosen exits -> sel/IMIT1.json (+ sha256). Re-scores all events and checks the scores match x2_score_they_buy.npy.
import sys, os, json, hashlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S
import gbdt_np as G
ENV = [("age", "<=", 343.67), ("drop_pct", ">=", 4.65), ("since_buy", "<=", 3.869), ("sell", ">=", 1.08)]
env = np.ones(len(S.EV), bool)
for k, op, v in ENV:
    j = S.FEATS.index(k); env &= (S.X[:, j] >= v) if op == ">=" else (S.X[:, j] <= v)
cut = np.quantile(S.T[S.TR], 0.8); FIT = S.TR & (S.T < cut) & env; VA = S.TR & (S.T >= cut) & env
y = S.LAB["ANY"].astype(float)
# bin edges exactly as gbdt_np.binize
edges = []
for j in range(S.X.shape[1]):
    x = S.X[:, j]; xt = x[FIT & ~np.isnan(x)]
    edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])).tolist() if len(xt) else [])
Bm = G.binize(S.X, FIT)
trees, f = G.fit(Bm, y, FIT, VA, rounds=400, lr=0.05, depth=3)
p0 = y[FIT].mean(); F0 = float(np.log(p0 / (1 - p0)))
old = np.load("/home/moiz/sniper/ops/overnight/sel/x2_score_they_buy.npy")
same = np.allclose(np.where(env, f, -1e9), old)
thr = {f"top{int(q * 100)}": float(np.quantile(f[VA], 1 - q)) for q in (0.02, 0.04, 0.08)}
model = dict(name="IMIT1", trained_on=f"TRAIN hours: dumps before {os.environ.get('SPLIT', '10-23 06:00')} PKT (fit first 80%, early stop last 20%)",
             label="HkQ7hMjy or DYXDDrZC or haqqiUUX buys within 1000 ms after the dump (before the next big sell)",
             features=S.FEATS, cohort_file="sel/cohort_train.json", envelope=ENV, edges=edges, F0=F0, lr=0.05, trees=trees, thresholds=thr,
             exits={"top2": ["T", 0.05, 0.1, 6, 1], "top4": ["T", 0.08, 0.05, 6, 1], "top8": ["T", 0.08, 0.1, 6, 1]})
txt = json.dumps(model); open("/home/moiz/sniper/ops/overnight/sel/IMIT1.json", "w").write(txt)
print(f"IMIT1 frozen: trees {len(trees)} | thresholds {thr} | sha256 {hashlib.sha256(txt.encode()).hexdigest()[:12]} | re-trained scores identical to the study run: {same}")

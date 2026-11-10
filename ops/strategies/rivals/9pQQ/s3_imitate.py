#!/usr/bin/env python3
"""9pQQ selection learnability: GBDT imitation of 'does 9pQQ react to this outside trade' from on-chain state at that moment.
Train 10-28 + 10-30 (all positives + 4 % of negatives), early-stop on 10-31, test 11-02 (all rows).  Reports AUC, precision /
recall at the top of the score, feature importance.  Read-only.  usage: s3_imitate.py"""
import json
import numpy as np
import tlib9 as L, gbdt_np as G

FEAT = ["side", "size", "age", "vsol", "may", "flow1", "flow10", "flow75", "flow150", "nbuy1", "nbuy10", "nbuy75", "ntr10", "ntr150",
        "dp10", "dp75", "dd450", "ntr_sofar", "trader_cnt", "dev_sold", "k_done", "since_sell", "hour"]
rng = np.random.default_rng(1)
Xs, ys, rs = [], [], []
for k, r in enumerate(L.RUNS):
    z = np.load(f"{L.OUT}/uni_{r}.npz")
    y = z["y"].astype(float)
    keep = (y == 1) | (rng.random(len(y)) < (0.04 if k < 3 else 1.0))
    Xs.append(np.stack([z[f][keep].astype(np.float64) for f in FEAT], 1)); ys.append(y[keep]); rs.append(np.full(keep.sum(), k))
X = np.concatenate(Xs); y = np.concatenate(ys); ri = np.concatenate(rs)
tr = ri <= 1; va = ri == 2; te = ri == 3
B = G.binize(X, tr)
trees, f = G.fit(B, y, tr, va, rounds=400, lr=0.08, depth=4)
imp = np.zeros(len(FEAT)); [G.imp(t_, imp) for t_ in trees]
out = dict(auc_train=G.auc(y[tr], f[tr]), auc_10_31=G.auc(y[va], f[va]), auc_11_02_all_rows=G.auc(y[te], f[te]),
           importance=sorted(zip(FEAT, (imp / imp.sum()).round(3).tolist()), key=lambda z: -z[1]))
ft = f[te]; yt = y[te]; o = np.argsort(-ft)
for q in (0.001, 0.003, 0.01, 0.03):
    n = int(len(o) * q); sel = o[:n]
    out[f"top{q * 100:g}%"] = dict(rows=n, precision=round(float(yt[sel].mean()), 3), recall=round(float(yt[sel].sum() / yt.sum()), 3))
print(json.dumps(out, indent=1))
json.dump(out, open("/home/it/sniper/ops/strategies/rivals/9pQQ/imitate.json", "w"), indent=1)

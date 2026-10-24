#!/usr/bin/env python3
# GDM step 3 (read-only, offline): train generic-demand selection models in STRICT TIME ORDER and choose the pick cut on
# VALIDATION only.  fwd: train R1 first 80% (by time), early-stop + cut choice on R1 last 20%, test R2.
#                   rev: train R2 first 80%, early-stop + cut on R2 last 20%, test R1.
# labels: ya  = market label a10 >= 1.05 (price at +10 s with every sniper+pro trade removed, vs post-bundle price)
#         ya10 = a10 >= 1.10
#         yb  = our 30 ms replay, pro buys after us removed + follower slippage (ps), 10 s hold, pnl > 0 (fills only)
#         yc  = >= 10 distinct generic (non-sniper / non-pro / non-insider) buyers 2-10 s after the create
# feature sets: L = liveh3 (no hour) + gdm history;  LM = + metadata;  LMR = + RPC creator lookups
# usage: python3 -I train.py -> gdm/models/<dir>_<label>_<fs>.json (trees, edges, scores) + gdm/train_summary.json
import sys, os, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
from common import binize, fit, imp, auc, pred
from multiprocessing import Pool
Z, M = common.load(); X = Z["X"]; bt = Z["bt"]; run = Z["run"]; names = M["names"]; G = M["groups"]; mints = M["mints"]
FS = {"L": G["live"] + G["gdm"], "LM": G["live"] + G["gdm"] + G["meta"], "LMR": G["live"] + G["gdm"] + G["meta"] + G["rpc"]}
OC = common.outcomes(mints)
st30, pn30 = OC["30"]
Y = {"ya": (Z["y_a10"] >= 1.05).astype(float), "ya10": (Z["y_a10"] >= 1.10).astype(float), "yc": (Z["y_c210"] >= 10).astype(float),
     "yb": np.nan_to_num((pn30["ps"][:, common.EXITS.index("t10")] > 0).astype(float))}
OKB = st30 == 1
os.makedirs(f"{common.OUT}/models", exist_ok=True)
def split(d):
    a, b = ("R1", "R2") if d == "fwd" else ("R2", "R1")
    tr_all = run == a; idx = np.where(tr_all)[0]; o = idx[np.argsort(bt[idx], kind="stable")]; cut = bt[o[int(len(o) * 0.8)]]
    return tr_all & (bt < cut), tr_all & (bt >= cut), run == b, cut
def job(cfg):
    d, lab, fs = cfg
    TR, VA, TE, cut = split(d)
    cols = [names.index(k) for k in FS[fs]]; Xs = X[:, cols]
    ok = OKB if lab == "yb" else np.ones(len(X), bool)
    Bm = binize(Xs, TR)
    trees, f = fit(Bm, Y[lab], TR & ok, VA & ok, rounds=600, lr=0.05, depth=3, seed=0)
    # store edges for freezing (same as binize)
    edges = []
    for j in range(Xs.shape[1]):
        x = Xs[:, j]; xt = x[TR & ~np.isnan(x)]
        edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])).tolist() if len(xt) else [])
    acc = np.zeros(len(cols))
    for t in trees: imp(t, acc)
    yv = Y[lab]
    out = dict(dir=d, label=lab, fs=fs, n_trees=len(trees), cut_bt=float(cut), auc_val=auc(yv[VA & ok], f[VA & ok]), auc_test=auc(yv[TE & ok], f[TE & ok]),
               auc_val_ya=auc(Y["ya"][VA], f[VA]), auc_test_ya=auc(Y["ya"][TE], f[TE]),
               importance=[(FS[fs][j], round(float(acc[j] / acc.sum()), 4)) for j in np.argsort(-acc)[:20] if acc[j] > 0])
    json.dump(dict(out, features=FS[fs], edges=edges, trees=trees, F0=float(np.log(Y[lab][TR & ok].mean() / (1 - Y[lab][TR & ok].mean()))), lr=0.05),
              open(f"{common.OUT}/models/{d}_{lab}_{fs}.json", "w"))
    np.save(f"{common.OUT}/models/{d}_{lab}_{fs}_score.npy", f)
    return out
if __name__ == "__main__":
    cfgs = [(d, l, f) for d in ("fwd", "rev") for l in ("ya", "ya10", "yb", "yc") for f in ("L", "LM", "LMR")]
    with Pool(6) as p: res = p.map(job, cfgs)
    json.dump(res, open(f"{common.OUT}/train_summary.json", "w"), indent=1)
    for r in res:
        print(f"{r['dir']} {r['label']:5s} {r['fs']:4s} trees {r['n_trees']:3d} | AUC own label val {r['auc_val']:.3f} test {r['auc_test']:.3f} | AUC vs ya val {r['auc_val_ya']:.3f} test {r['auc_test_ya']:.3f} | top: " +
              ", ".join(f"{k} {v:.0%}" for k, v in r["importance"][:6]))

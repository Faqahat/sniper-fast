#!/usr/bin/env python3
# GDM robustness (precomputed outcomes): (1) seed stability of yc/LM, (2) ablation without the label-derived history features
# (they use the sniper wallet list built on all data -> possible mild leakage), (3) no-metadata (L). fold2 models, top 3% cut
# from validation, test = other period; union with FINAL-2.
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
from common import binize, fit, auc
from multiprocessing import Pool
Z, M = common.load(); X = Z["X"]; bt = Z["bt"]; run = Z["run"]; names = M["names"]; G = M["groups"]; guard = Z["guard"] == 1
LABH = {"dep_ya_last", "dep_a10_last", "dep_ya_rate", "dep_a10_mean", "dep_c_mean", "bw_ya_rate", "bw_a10_mean", "bw_c_mean", "name_ya_rate", "name_c_mean",
        "fp_te", "uh_te", "heat_ya_60", "heat_c_60"}
FS = {"LM": G["live"] + G["gdm"] + G["meta"], "L": G["live"] + G["gdm"], "LM_noLabHist": [k for k in G["live"] + G["gdm"] + G["meta"] if k not in LABH],
      "liveh3_only": G["live"], "LM_noHistAtAll": G["live"] + G["meta"] + ["dev_plus_bundle", "dpb_2_20", "glued_1", "fresh_dep", "fp_fifaw", "relaunch_lt60", "dep_n_all", "dep_gap_s", "name_n1h"]}
y = (Z["y_c210"] >= 10).astype(float)
def masks(d):
    a = "R1" if d == "fwd" else "R2"; idx = np.where(run == a)[0]; o = idx[np.argsort(bt[idx], kind="stable")]; c8 = bt[o[int(len(o) * 0.8)]]
    return (run == a) & (bt < c8), (run == a) & (bt >= c8), run == ("R2" if d == "fwd" else "R1")
def job(cfg):
    d, fs, seed = cfg; TR, VA, TE = masks(d); cols = [names.index(k) for k in FS[fs]]
    Bm = binize(X[:, cols], TR); trees, f = fit(Bm, y, TR, VA, rounds=600, lr=0.05, depth=3, seed=seed)
    return cfg, f
if __name__ == "__main__":
    mints = M["mints"]; OC = common.outcomes(mints); f2p = np.load(f"{common.OUT}/f2.npz")["pick"]
    def crit(sel, vs=("ps", "ns")): return np.mean([common.book(sel, OC, L, v, ex)[0] for L in ("30", "45") for ex in ("t8", "t10") for v in vs])
    cfgs = [(d, "LM", s) for d in ("fwd", "rev") for s in (0, 1, 2, 3, 4)] + [(d, fs, 0) for d in ("fwd", "rev") for fs in ("L", "LM_noLabHist", "liveh3_only", "LM_noHistAtAll")]
    with Pool(6) as p: res = p.map(job, cfgs)
    for (d, fs, seed), f in res:
        TR, VA, TE = masks(d); thr = np.quantile(f[VA], 0.97); s = TE & (f >= thr) & guard
        print(f"{d} {fs:15s} seed {seed} | AUC(yc) test {auc(y[TE], f[TE]):.3f} | top3% n {s.sum():4d} crit ps+ns {crit(s):+6.2f} | union w/ FINAL-2 n {(s | (TE & f2p)).sum():4d} {crit(s | (TE & f2p)):+6.2f} (FINAL-2 alone {crit(TE & f2p):+6.2f})")

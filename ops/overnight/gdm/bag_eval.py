#!/usr/bin/env python3
# GDM: 5-seed bagged yc models (mean of the 5 raw scores), top-q cut from validation; precomputed outcomes. fold2 models.
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
from common import binize, fit, auc
from multiprocessing import Pool
Z, M = common.load(); X = Z["X"]; bt = Z["bt"]; run = Z["run"]; names = M["names"]; G = M["groups"]; guard = Z["guard"] == 1
FS = {"LM": G["live"] + G["gdm"] + G["meta"], "L": G["live"] + G["gdm"]}
y = (Z["y_c210"] >= 10).astype(float)
def masks(d):
    a = "R1" if d == "fwd" else "R2"; idx = np.where(run == a)[0]; o = idx[np.argsort(bt[idx], kind="stable")]; c8 = bt[o[int(len(o) * 0.8)]]
    return (run == a) & (bt < c8), (run == a) & (bt >= c8), run == ("R2" if d == "fwd" else "R1")
def job(cfg):
    d, fs, seed = cfg; TR, VA, TE = masks(d); cols = [names.index(k) for k in FS[fs]]
    Bm = binize(X[:, cols], TR); trees, f = fit(Bm, y, TR, VA, rounds=600, lr=0.05, depth=3, seed=seed)
    return cfg, f
if __name__ == "__main__":
    mints = np.array(M["mints"]); OC = common.outcomes(list(mints)); f2p = np.load(f"{common.OUT}/f2.npz")["pick"]
    def crit(sel, vs=("ps", "ns")): return np.mean([common.book(sel, OC, L, v, ex)[0] for L in ("30", "45") for ex in ("t8", "t10") for v in vs])
    cfgs = [(d, fs, s) for d in ("fwd", "rev") for fs in ("LM", "L") for s in range(5)]
    with Pool(6) as p: res = dict(p.map(job, cfgs))
    for d in ("fwd", "rev"):
        TR, VA, TE = masks(d)
        for fs in ("LM", "L"):
            f = np.mean([res[(d, fs, s)] for s in range(5)], 0); np.save(f"{common.OUT}/models/bag_{d}_yc_{fs}.npy", f)
            for q in (0.02, 0.03, 0.05):
                thr = np.quantile(f[VA], 1 - q); sv = VA & (f >= thr) & guard; s = TE & (f >= thr) & guard
                print(f"{d} bag5 yc {fs:2s} q {q:.2f} | VAL n {sv.sum():3d} {crit(sv):+5.2f} | TEST AUC {auc(y[TE], f[TE]):.3f} n {s.sum():4d} crit {crit(s):+6.2f} ps {crit(s, ('ps',)):+6.2f} ns {crit(s, ('ns',)):+6.2f} | union n {(s | (TE & f2p)).sum():4d} {crit(s | (TE & f2p)):+6.2f} (FINAL-2 {crit(TE & f2p):+6.2f})")
                if q == 0.03 and fs == "LM": json.dump(sorted(mints[s]), open(f"{common.OUT}/picks/bag_{d}_yc_LM_q0.03.json", "w"))

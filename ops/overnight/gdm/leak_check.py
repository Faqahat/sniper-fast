#!/usr/bin/env python3
# leakage check: labels + walk-forward history features rebuilt with the R1-ONLY sniper list (gdm/sniper_r1.json, 220 wallets
# instead of 321 found on R1+R2). fwd direction (train R1, test R2), bagged yc/LM and yc/L, top 3% cut from validation.
# Evaluation outcomes are unchanged (core/allres_bt.json + gdm/labels.json; their sniper list is part of the TEST definition).
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
from common import binize, fit, auc
from multiprocessing import Pool
Zs = np.load(f"{common.OUT}/feats_r1s.npz"); Ms = json.load(open(f"{common.OUT}/feats_meta_r1s.json"))
Z, M = common.load()
assert Ms["mints"] == M["mints"]
X = Zs["X"]; bt = Zs["bt"]; run = Zs["run"]; names = Ms["names"]; G = Ms["groups"]; guard = Zs["guard"] == 1
FS = {"LM": G["live"] + G["gdm"] + G["meta"], "L": G["live"] + G["gdm"]}
y = (Zs["y_c210"] >= 10).astype(float)
idx = np.where(run == "R1")[0]; o = idx[np.argsort(bt[idx], kind="stable")]; c8 = bt[o[int(len(o) * 0.8)]]
TR, VA, TE = (run == "R1") & (bt < c8), (run == "R1") & (bt >= c8), run == "R2"
def job(cfg):
    fs, seed = cfg; cols = [names.index(k) for k in FS[fs]]
    Bm = binize(X[:, cols], TR); trees, f = fit(Bm, y, TR, VA, rounds=600, lr=0.05, depth=3, seed=seed)
    return cfg, f
if __name__ == "__main__":
    OC = common.outcomes(M["mints"]); f2p = np.load(f"{common.OUT}/f2.npz")["pick"]; mints = np.array(M["mints"])
    def crit(sel, vs=("ps", "ns")): return np.mean([common.book(sel, OC, L, v, ex)[0] for L in ("30", "45") for ex in ("t8", "t10") for v in vs])
    with Pool(6) as p: res = dict(p.map(job, [(fs, s) for fs in ("LM", "L") for s in range(5)]))
    yfull = (Z["y_c210"] >= 10).astype(float)
    for fs in ("LM", "L"):
        f = np.mean([res[(fs, s)] for s in range(5)], 0)
        for q in (0.02, 0.03):
            thr = np.quantile(f[VA], 1 - q); s = TE & (f >= thr) & guard
            print(f"R1-only snipers: fwd bag5 yc {fs:2s} q {q:.2f} | TEST AUC(full-list yc) {auc(yfull[TE], f[TE]):.3f} n {s.sum():4d} crit {crit(s):+6.2f} ps {crit(s, ('ps',)):+6.2f} ns {crit(s, ('ns',)):+6.2f} | union n {(s | (TE & f2p)).sum():4d} {crit(s | (TE & f2p)):+6.2f} (FINAL-2 {crit(TE & f2p):+6.2f})")
            if q == 0.03 and fs == "LM": json.dump(sorted(mints[s]), open(f"{common.OUT}/picks/leak_fwd_yc_LM_q0.03.json", "w"))

#!/usr/bin/env python3
# GDM step 3b (read-only, offline): config + cut selection with TWO time-ordered validation folds inside the training period
# (more validation data than one 20% slice).  For direction fwd (train period R1) and rev (train period R2):
#   fold1: train on the first 60% of the period, validate on 60-80%;  fold2: train on the first 80%, validate on 80-100%.
# Configs: labels ya / ya10 / yb / yc and the ensemble E3 = mean validation-z of (ya10, yb, yc); feature sets L, LM.
# Criterion (validation only): mean over 30/45 ms x t8/t10 x {ps, ns} of total SOL at pro costs, summed over both folds,
# for the top q% of validation scores (q in 2/3/5/7.5/10%), guards applied. Test = fold2 model + fold2 threshold.
import sys, os, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
from common import binize, fit, imp, auc, pred
from multiprocessing import Pool
Z, M = common.load(); X = Z["X"]; bt = Z["bt"]; run = Z["run"]; names = M["names"]; G = M["groups"]; mints = M["mints"]; guard = Z["guard"] == 1
FS = {"L": G["live"] + G["gdm"], "LM": G["live"] + G["gdm"] + G["meta"]}
OC = common.outcomes(mints); st30, pn30 = OC["30"]
Y = {"ya": (Z["y_a10"] >= 1.05).astype(float), "ya10": (Z["y_a10"] >= 1.10).astype(float), "yc": (Z["y_c210"] >= 10).astype(float),
     "yb": np.nan_to_num((pn30["ps"][:, common.EXITS.index("t10")] > 0).astype(float))}
OKB = st30 == 1
def masks(d, fold):
    a = "R1" if d == "fwd" else "R2"; idx = np.where(run == a)[0]; o = idx[np.argsort(bt[idx], kind="stable")]
    c6, c8 = bt[o[int(len(o) * 0.6)]], bt[o[int(len(o) * 0.8)]]
    if fold == 1: return (run == a) & (bt < c6), (run == a) & (bt >= c6) & (bt < c8)
    return (run == a) & (bt < c8), (run == a) & (bt >= c8)
def job(cfg):
    d, fold, lab, fs = cfg; TR, VA = masks(d, fold)
    cols = [names.index(k) for k in FS[fs]]; Xs = X[:, cols]; ok = OKB if lab == "yb" else np.ones(len(X), bool)
    Bm = binize(Xs, TR); trees, f = fit(Bm, Y[lab], TR & ok, VA & ok, rounds=600, lr=0.05, depth=3, seed=0)
    np.save(f"{common.OUT}/models/cv_{d}_f{fold}_{lab}_{fs}.npy", f)
    return cfg, len(trees)
def crit(sel):
    return np.mean([common.book(sel, OC, L, v, ex)[0] for L in ("30", "45") for ex in ("t8", "t10") for v in ("ps", "ns")])
QS = (0.02, 0.03, 0.05, 0.075, 0.10)
if __name__ == "__main__":
    cfgs = [(d, fo, l, f) for d in ("fwd", "rev") for fo in (1, 2) for l in ("ya", "ya10", "yb", "yc") for f in ("L", "LM")]
    with Pool(6) as p: done = p.map(job, cfgs)
    res = []
    for d in ("fwd", "rev"):
        b = "R2" if d == "fwd" else "R1"; TE = run == b
        for fs in ("L", "LM"):
            for lab in ("ya", "ya10", "yb", "yc", "E3"):
                sc = {}
                for fo in (1, 2):
                    TR, VA = masks(d, fo)
                    if lab == "E3":
                        zs = []
                        for l in ("ya10", "yb", "yc"):
                            f = np.load(f"{common.OUT}/models/cv_{d}_f{fo}_{l}_{fs}.npy"); zs.append((f - f[VA].mean()) / f[VA].std())
                        sc[fo] = (np.mean(zs, 0), VA)
                    else: sc[fo] = (np.load(f"{common.OUT}/models/cv_{d}_f{fo}_{lab}_{fs}.npy"), VA)
                for q in QS:
                    v = []
                    for fo in (1, 2):
                        f, VA = sc[fo]; thr = np.quantile(f[VA], 1 - q); v.append(crit(VA & (f >= thr) & guard))
                    f2, VA2 = sc[2]; thr = np.quantile(f2[VA2], 1 - q); stt = TE & (f2 >= thr) & guard
                    res.append(dict(dir=d, fs=fs, label=lab, q=q, val1=v[0], val2=v[1], val=v[0] + v[1], thr=float(thr), n_test=int(stt.sum()), test=crit(stt),
                                    auc_test_ya=auc(Y["ya"][TE], f2[TE])))
                if lab == "E3": np.save(f"{common.OUT}/models/cv_{d}_f2_E3_{fs}.npy", sc[2][0])
    json.dump(res, open(f"{common.OUT}/cv_rows.json", "w"), indent=0)
    for d in ("fwd", "rev"):
        rs = sorted([r for r in res if r["dir"] == d], key=lambda r: -r["val"])
        print(f"== {d}: top configs by validation (2 folds); test shown for reference only")
        for r in rs[:12]: print(f"   {r['label']:5s} {r['fs']:3s} q {r['q']:.3f} | val {r['val1']:+5.2f} + {r['val2']:+5.2f} = {r['val']:+6.2f} | test n {r['n_test']:4d} crit {r['test']:+6.2f} | AUC(ya) test {r['auc_test_ya']:.3f}")

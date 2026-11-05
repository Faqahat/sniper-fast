#!/usr/bin/env python3
"""LANES step 12: exit imitation. (a) pooled GBDT, train 10-28..10-30, early-stop 10-31, test 11-02; (b) is the exit module shared?
model trained on NEW-trip rows vs TRK-trip rows, each scored on both modules' test rows (AUC). Saves scores -> xscore_<run>.npy"""
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import gbw, llib
RUNS = llib.RUNS
Z = [np.load(f"{llib.D}/xmom_{r}.npz") for r in RUNS]; fn = list(Z[0]["fn"])
X = np.concatenate([z["X"] for z in Z]); y = np.concatenate([z["y"] for z in Z]).astype(float); w = np.concatenate([z["w"] for z in Z]).astype(float)
part = np.concatenate([np.full(len(z["y"]), k) for k, z in enumerate(Z)])
mod = X[:, fn.index("mod")]
tr = part <= 2; va = part == 3; te = part == 4
Bm = gbw.binize(X, tr)
def evals(f, sel):
    ss, yy, ww = f[sel], y[sel], w[sel]; o = np.argsort(-ss); cy = np.cumsum((yy * ww)[o]); cw = np.cumsum(ww[o]); P = yy @ ww
    d = dict(base=round(float(P / ww.sum()), 4), auc=round(gbw.auc(yy, ss), 4))
    for rec in (0.05, 0.1, 0.25, 0.5):
        k = int(np.searchsorted(cy, rec * P)); d[f"prec@rec{rec}"] = round(float(cy[k] / cw[k]), 4)
    return d
res = {}
trees, f = gbw.fit(Bm, y, tr, va, rounds=500, lr=0.08, depth=4, w=w, min_n=80)
acc = np.zeros(X.shape[1])
for t_ in trees: gbw.imp(t_, acc)
res["pooled"] = dict(n_trees=len(trees), top=[(fn[j], round(float(acc[j] / acc.sum()), 3)) for j in np.argsort(-acc)[:12]],
                     test=evals(f, te), test_NEW=evals(f, te & (mod == 0)), test_TRK=evals(f, te & (mod == 1)), choose=evals(f, va))
for k, r in enumerate(RUNS): np.save(f"{llib.D}/xscore_{r}.npy", f[part == k].astype(np.float32))
print("pooled", json.dumps(res["pooled"]), flush=True)
for mm, nm in ((0, "NEW"), (1, "TRK")):
    t2, f2 = gbw.fit(Bm, y, tr & (mod == mm), va & (mod == mm), rounds=400, lr=0.08, depth=4, w=w, min_n=80)
    res[f"trained_on_{nm}"] = dict(on_NEW=evals(f2, te & (mod == 0)), on_TRK=evals(f2, te & (mod == 1)))
    print(nm, json.dumps(res[f"trained_on_{nm}"]), flush=True)
json.dump(res, open("/home/moiz/sniper/ops/strategies/rivals/9pQQ/lanes/exit_gbdt.json", "w"), indent=1)

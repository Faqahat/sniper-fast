#!/usr/bin/env python3
"""LANES step 9: per-module entry imitation (GBDT ceiling). Train 10-28+10-29+10-30, early-stop/threshold on 10-31, test 11-02.
Weighted (negatives sampled 4%). Reports AUC, precision at recall levels, top features. -> lanes/entry_gbdt.json + model pickle."""
import sys, json, pickle, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/code")
import gbw, llib
TR = ["run_20261028_1405", "run_20261029_1400", "run_20261030_1355"]; VA = "run_20261031_1350"; TE = "run_20261102_1250"
Z = {r: np.load(f"{llib.D}/mom_{r}.npz") for r in TR + [VA, TE]}
fn = list(Z[TE]["fn"]); res = {}
for mod, name in ((0, "NEW"), (1, "TRK")):
    Xs, ys, ws, part = [], [], [], []
    for k, r in enumerate(TR + [VA, TE]):
        z = Z[r]; s = (z["mod"] == mod) & np.load(f"{llib.D}/momon_{r}.npy")
        Xs.append(z["X"][s]); ys.append(z["y"][s]); ws.append(z["w"][s]); part.append(np.full(s.sum(), k))
    X = np.concatenate(Xs); y = np.concatenate(ys).astype(float); w = np.concatenate(ws).astype(float); part = np.concatenate(part)
    drop = [fn.index(c) for c in ("mod", "creator_sold")]
    keepf = [j for j in range(X.shape[1]) if j not in drop]
    tr = part <= 2; va = part == 3; te = part == 4
    Bm = gbw.binize(X[:, keepf], tr)
    trees, f = gbw.fit(Bm, y, tr, va, rounds=500, lr=0.08, depth=4, w=w, min_n=80)
    acc = np.zeros(len(keepf))
    for t_ in trees: gbw.imp(t_, acc)
    top = sorted(zip(acc, [fn[j] for j in keepf]), reverse=True)[:15]
    out = dict(n_trees=len(trees), top=[(n, round(float(a / acc.sum()), 3)) for a, n in top])
    for nm, sel in (("train", tr), ("choose_10-31", va), ("test_11-02", te)):
        ss, yy, ww = f[sel], y[sel], w[sel]
        o = np.argsort(-ss); cy = np.cumsum((yy * ww)[o]); cw = np.cumsum(ww[o]); P = yy @ ww
        rows = {}
        for rec in (0.05, 0.1, 0.25, 0.5):
            k = int(np.searchsorted(cy, rec * P)); rows[f"prec@rec{rec}"] = round(float(cy[k] / cw[k]), 4)
        out[nm] = dict(base=round(float(P / ww.sum()), 5), auc=round(gbw.auc(yy, ss), 4), **rows)
    res[name] = out
    for k, r in enumerate(TR + [VA, TE]):
        zz = Z[r]; sel_all = (zz["mod"] == mod) & np.load(f"{llib.D}/momon_{r}.npy")
        sc = np.full(len(zz["y"]), np.nan, np.float32); sc[sel_all] = f[part == k]
        np.save(f"{llib.D}/score_{name}_{r}.npy", sc)
    pickle.dump(dict(trees=trees, keepf=keepf, fn=fn, edges=None), open(f"{llib.D}/entry_gbdt_on_{name}.pkl", "wb"))
    print(name, json.dumps(out), flush=True)
json.dump(res, open("/home/it/sniper/ops/strategies/rivals/9pQQ/lanes/entry_gbdt_on.json", "w"), indent=1)

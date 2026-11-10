#!/usr/bin/env python3
"""Upper bound of on-chain predictability: numpy GBDT on decision moments. MODE b (flat, label yb_imm) or s (hold, label ys_imm).
Train 10-28+10-30 (all positives + FRAC negatives), early stop on 10-31; scores 10-31 (and 11-02 only with FINAL=1).
Reports precision at recall 10/25/50/75% and the best F1. Saves model -> exact/g1_<mode>.pkl.  usage: g1_bound.py b|s [FINAL]"""
import sys, json, pickle
import numpy as np
sys.path.insert(0, "..")
import xlib as X, gbdt_np as G
MODE = sys.argv[1]; FINAL = "final" in sys.argv[2:]; RT = "rt" in sys.argv[2:]; NOG = "noglobal" in sys.argv[2:]
TAG = MODE + ("_rt" if RT else "") + ("_nog" if NOG else "")
LAB = "yb_imm" if MODE == "b" else "ys_imm"
EXCL = {"yb_imm", "yb_any", "ys_imm", "ys_any", "hold", "s", "i", "m", "u", "row", "hour"}
if MODE == "b": EXCL |= {"peak_since_buy", "trough_since_buy", "dd_peak_buy", "sg_hold", "bsol_hold", "ssol_hold", "nb_hold", "ns_hold"}
else: EXCL |= {"last_trip_ret", "since_own_sell", "v_vs_ownsell"}
if NOG: EXCL |= {"open_pos", "own_buys25"}
FRAC = 0.03 if MODE == "b" else 0.25
rng = np.random.default_rng(0)
def load(run, frac):
    z = np.load(f"{X.XOUT}/dm_{run}.npz")
    st = ~z["hold"] if MODE == "b" else z["hold"]; y = z[LAB] & st
    keep = st & (y | (rng.random(len(y)) < frac))
    names = [k for k in z.files if k not in EXCL]
    cols = [z[k][keep] for k in names]
    if RT:
        q = np.load(f"{X.XOUT}/rt_{run}.npz"); names = names + list(q.files); cols += [q[k][keep] for k in q.files]
    return np.stack(cols, 1).astype(np.float32), y[keep].astype(float), names
parts = [load(r, FRAC) for r in X.RUNS[:2]] + [load(X.RUNS[2], 1.0)] + ([load(X.RUNS[3], 1.0)] if FINAL else [])
names = parts[0][2]
Xm = np.concatenate([p[0] for p in parts]); y = np.concatenate([p[1] for p in parts])
ri = np.concatenate([np.full(len(p[1]), k) for k, p in enumerate(parts)])
tr = ri <= 1; va = ri == 2
B = G.binize(Xm, tr)
trees, f = G.fit(B, y, tr, va, rounds=500, lr=0.08, depth=5)
imp = np.zeros(len(names)); [G.imp(t_, imp) for t_ in trees]
def pr(yy, ss):
    o = np.argsort(-ss); c = np.cumsum(yy[o]); P = yy.sum(); res = {}
    for rec in (0.05, 0.1, 0.25, 0.5, 0.75):
        k = int(np.searchsorted(c, rec * P)); res[f"prec@rec{int(rec*100)}"] = round(float(c[k] / (k + 1)), 4)
    f1 = 2 * c / (np.arange(1, len(c) + 1) + P); k = int(np.argmax(f1))
    res["best_f1"] = round(float(f1[k]), 4); res["best_f1_prec"] = round(float(c[k] / (k + 1)), 4); res["best_f1_rec"] = round(float(c[k] / P), 4)
    res["auc"] = round(G.auc(yy, ss), 4); res["pos"] = int(P); res["rows"] = len(yy)
    return res
out = dict(mode=MODE, label=LAB, trees=len(trees), val_10_31=pr(y[va], f[va]),
           importance=sorted(zip(names, (imp / imp.sum()).round(3).tolist()), key=lambda z: -z[1])[:20])
if FINAL: out["test_11_02"] = pr(y[ri == 3], f[ri == 3])
print(json.dumps({k: v for k, v in out.items() if k != "importance"}), out["importance"][:12])
json.dump(out, open(f"g1_{TAG}{'_final' if FINAL else ''}.json", "w"), indent=1)
edges = [np.unique(np.quantile(Xm[tr, j][~np.isnan(Xm[tr, j])], np.linspace(0, 1, 33)[1:-1])) for j in range(len(names))]
pickle.dump(dict(trees=trees, names=names, edges=edges, F0=float(np.log(y[tr].mean() / (1 - y[tr].mean()))), lr=0.08, frac=FRAC), open(f"{X.XOUT}/g1_{TAG}.pkl", "wb"))

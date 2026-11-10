#!/usr/bin/env python3
"""H4 entry rule induction: CART on BUY decision moments (9pQQ flat). Train 10-28+10-30 (all positives + 3% negatives, reweighted),
evaluate leaves on 10-31 (all rows). label = yb_imm. usage: b1_tree.py DEPTH [LABEL]"""
import sys, json
import numpy as np
import xlib as X, cart as C
D = int(sys.argv[1]) if len(sys.argv) > 1 else 6; LAB = sys.argv[2] if len(sys.argv) > 2 else "yb_imm"
EXCL = {"yb_imm", "yb_any", "ys_imm", "ys_any", "hold", "s", "i", "m", "u", "row", "peak_since_buy", "trough_since_buy", "dd_peak_buy",
        "sg_hold", "bsol_hold", "ssol_hold", "nb_hold", "ns_hold", "hour"}
rng = np.random.default_rng(0)
def load(run, frac):
    z = np.load(f"{X.XOUT}/dm_{run}.npz")
    flat = ~z["hold"]; y = z[LAB] & flat
    keep = flat & (y | (rng.random(len(y)) < frac))
    names = [k for k in z.files if k not in EXCL]
    Xm = np.stack([z[k][keep] for k in names], 1).astype(np.float32)
    return Xm, y[keep].astype(float), np.where(y[keep], 1.0, 1.0 / frac), names
Xa, ya, wa, names = zip(*[load(r, 0.03) for r in X.RUNS[:2]])
names = names[0]; Xt = np.concatenate(Xa); yt = np.concatenate(ya); wt = np.concatenate(wa)
Bt, edges = C.binize(Xt, np.ones(len(Xt), bool))
tree = C.build(Bt, yt, wt, np.arange(len(Bt)), D, min_w=wt.sum() * 0.0005, feats=range(len(names)))
Xv, yv, wv, _ = load(X.RUNS[2], 1.0)
Bv = np.stack([np.where(np.isnan(Xv[:, j]), 0, np.searchsorted(edges[j], Xv[:, j], side="right") + 1) for j in range(len(names))], 1)
lt, leaves = C.leaf_ids(tree, Bt); lv, _ = C.leaf_ids(tree, Bv)
rows = []
for lid, (path, n) in leaves.items():
    mt = lt == lid; mv = lv == lid
    rows.append(dict(rule=C.fmt_rule(path, names, edges), train_w=float(wt[mt].sum()), train_p=float((wt[mt] * yt[mt]).sum() / max(1e-9, wt[mt].sum())),
                     val_n=int(mv.sum()), val_pos=int(yv[mv].sum()), val_p=float(yv[mv].mean()) if mv.any() else 0.0))
Xs, ys_, ws_, _ = load(X.RUNS[3], 1.0)
Bs = np.stack([np.where(np.isnan(Xs[:, j]), 0, np.searchsorted(edges[j], Xs[:, j], side="right") + 1) for j in range(len(names))], 1)
ls_, _ = C.leaf_ids(tree, Bs)
for lid, rr in zip(leaves, rows):
    ms_ = ls_ == lid; rr["test_n"] = int(ms_.sum()); rr["test_pos"] = int(ys_[ms_].sum()); rr["lid"] = lid
rows.sort(key=lambda r: -r["val_p"])
tot = yv.sum(); cum = 0; cn = 0
print("val positives", int(tot), "val rows", len(yv), "base", round(tot / len(yv), 5))
# frozen rule list: leaves chosen on 10-31 by val precision >= SEL, scored on 11-02
import json as _j
SEL = float(sys.argv[3]) if len(sys.argv) > 3 else 0.05
pick = [r for r in rows if r["val_p"] >= SEL]
tp = sum(r["test_pos"] for r in pick); tn = sum(r["test_n"] for r in pick)
fro = dict(label=LAB, depth=D, select_val_p=SEL, n_rules=len(pick), val_precision=round(sum(r["val_pos"] for r in pick) / max(1, sum(r["val_n"] for r in pick)), 4),
           val_recall=round(sum(r["val_pos"] for r in pick) / tot, 4), test_precision=round(tp / max(1, tn), 4), test_recall=round(tp / max(1, ys_.sum()), 4),
           test_base=round(float(ys_.mean()), 5), rules=[(r["rule"], round(r["val_p"], 4), round(r["test_pos"] / max(1, r["test_n"]), 4), r["test_n"]) for r in pick])
print("FROZEN", _j.dumps({k: v for k, v in fro.items() if k != "rules"}))
_j.dump(fro, open(f"{sys.argv[0][:-3]}_frozen.json", "w"), indent=1)
for r in rows:
    cum += r["val_pos"]; cn += r["val_n"]
    print(f"p_val {r['val_p']:.4f} pos {r['val_pos']:5d} n {r['val_n']:8d} | cum prec {cum/max(1,cn):.4f} rec {cum/tot:.3f} | p_tr {r['train_p']:.4f} :: {r['rule']}")

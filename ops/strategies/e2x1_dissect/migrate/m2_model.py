#!/usr/bin/env python3
"""migrate agent, step 2: GRADUATION PREDICTOR. GBDT (depth 4) + a depth-4 decision tree (rules) on the entrable moments.
Train = 10-24..10-26 (probabilities for train rows are OUT-OF-FOLD, by day), test = 10-27/10-28 (model fit on all train).
Reports AUC / calibration / rules on TEST and saves p30/p120/p600 per row -> feat_p.pkl (aligned with feat.pkl rows)."""
import sys, pickle, numpy as np, collections
sys.path.insert(0, "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/e2x1_migrate/pylib")
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.tree import DecisionTreeClassifier, export_text
from sklearn.metrics import roc_auc_score
from sklearn.inspection import permutation_importance
from mlib import D, TRAIN, TEST

F = pickle.load(open(D + "/feat.pkl", "rb")); X = F["X"]; names = F["names"]; meta = F["meta"]
day = np.array([r["day"] for r in meta]); ent = np.array([r["ent"] for r in meta]) == 1; edge = np.array([r["edge"] for r in meta])
tc = np.array([r["t_complete"] for r in meta]); V = np.array([r["V"] for r in meta])
use = ent & ~edge
tr = use & np.isin(day, TRAIN); te = use & np.isin(day, TEST)
print(f"rows {len(X)}  entrable&clean {use.sum()}  train {tr.sum()}  test {te.sum()}")
print("entrable per V (train+test): " + ", ".join(f"V{v}: {(use & (V == v)).sum()} (first-cross {(use & (V == v) & (np.array([r['ncross'] for r in meta]) == 0)).sum()})" for v in sorted(set(V))))
HOR = {"p30": 30, "p120": 120, "p600": 600}
P = {k: np.full(len(X), np.nan) for k in HOR}
def gb(): return HistGradientBoostingClassifier(max_depth=4, learning_rate=0.04, max_iter=400, min_samples_leaf=40, l2_regularization=1.0, random_state=0)
out = []
for pk, H in HOR.items():
    y = (tc <= H).astype(int)
    # out-of-fold on train (leave one day out)
    for d in TRAIN:
        fit = tr & (day != d); pred = tr & (day == d)
        m = gb().fit(X[fit], y[fit]); P[pk][pred] = m.predict_proba(X[pred])[:, 1]
    m = gb().fit(X[tr], y[tr]); P[pk][te] = m.predict_proba(X[te])[:, 1]
    a_tr = roc_auc_score(y[tr], P[pk][tr]); a_te = roc_auc_score(y[te], P[pk][te])
    print(f"\n== label: completes within {H}s | base rate train {y[tr].mean():.3f} test {y[te].mean():.3f} | AUC train(OOF) {a_tr:.3f} test {a_te:.3f}")
    for v in sorted(set(V)):
        s = te & (V == v)
        if s.sum() > 50 and 0 < y[s].mean() < 1: print(f"   test V={v}: n {s.sum()} base {y[s].mean():.3f} AUC {roc_auc_score(y[s], P[pk][s]):.3f}")
    print("   calibration on test (decile of p): mean p -> realized rate (n)")
    q = np.quantile(P[pk][te], np.linspace(0, 1, 11)); pt = P[pk][te]; yt = y[te]
    for i in range(10):
        s = (pt >= q[i]) & (pt <= q[i + 1]) if i == 9 else (pt >= q[i]) & (pt < q[i + 1])
        print(f"     {pt[s].mean():.3f} -> {yt[s].mean():.3f} ({s.sum()})")
    if pk == "p120":
        print("   top-15 permutation importance (fit on 10-24/25, scored on 10-26 AUC):")
        fit = tr & (day != "10-26"); val = tr & (day == "10-26")
        m2 = gb().fit(X[fit], y[fit]); pi = permutation_importance(m2, X[val], y[val], scoring="roc_auc", n_repeats=3, random_state=0)
        for j in np.argsort(pi.importances_mean)[::-1][:15]: print(f"     {names[j]:18s} {pi.importances_mean[j]:+.4f}")
        print("   depth-4 RULES (fit on train, leaf rates shown = train; test rate per leaf below):")
        dt = DecisionTreeClassifier(max_depth=4, min_samples_leaf=150, random_state=0).fit(X[tr], y[tr])
        print(export_text(dt, feature_names=names, decimals=2, show_weights=True))
        leaf_tr = dt.apply(X[tr]); leaf_te = dt.apply(X[te])
        print("   leaf: train rate (n) | test rate (n)")
        for lf in sorted(set(leaf_tr)):
            a = y[tr][leaf_tr == lf]; b = y[te][leaf_te == lf]
            print(f"     leaf {lf:3d}: {a.mean():.3f} ({len(a)}) | {b.mean() if len(b) else float('nan'):.3f} ({len(b)})")
        print(f"   rules AUC test {roc_auc_score(y[te], dt.predict_proba(X[te])[:, 1]):.3f}")
pickle.dump(P, open(D + "/feat_p.pkl", "wb"))
print("saved feat_p.pkl")

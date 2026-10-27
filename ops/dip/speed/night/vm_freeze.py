#!/usr/bin/env python3
# FREEZE the value model (night 10-25 ~04:25 PKT): trained on 10-23 (7 h) + 10-24 (7 h, up to slot 461001668). Saves bin edges + trees +
# the score cutoff that gives ~52 picks/h on the training data -> vm_frozen.pkl. The morning forward test scores only data AFTER this.
import pickle, numpy as np, sys
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip"); import gbdt_np as G
from hq2 import load, dataset
A = load("rows_d23.json"); B = load("race_rows.json")
Xa, Va, Ta = dataset(A, 80, 0.002); Xb, Vb, Tb = dataset(B, 80, 0.002)
X = np.vstack([Xa, Xb]); V = np.concatenate([Va, Vb]); n = len(V)
TR = np.zeros(n, bool); TR[: int(n * .85)] = True; VA = ~TR
edges = []
for j in range(X.shape[1]):
    x = X[TR, j]; x = x[~np.isnan(x)]; edges.append(np.unique(np.quantile(x, np.linspace(0, 1, 33)[1:-1])))
Bm = G.binize(X, TR); y = (V > 0).astype(float)
trees, f = G.fit(Bm, y, TR, VA, rounds=400, lr=0.05, depth=3)
hours = ((Ta.max() - Ta.min()) + (Tb.max() - Tb.min())) * 0.2126 / 3600
cut = np.sort(f)[::-1][int(52 * hours)]
pickle.dump(dict(edges=edges, trees=trees, F0=None, cut=cut, lr=0.05, trained_until_slot=int(Tb.max()), note="value model v1, 16 feats (hq2.dataset), +80 txs / hold 6 / 0.3 SOL labels"), open("vm_frozen.pkl", "wb"))
print(f"frozen: {len(trees)} trees, cut {cut:.3f} (~52 picks/h on train), trained until slot {Tb.max()} | train hours {hours:.1f}")

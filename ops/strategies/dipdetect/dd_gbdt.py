#!/usr/bin/env python3
# Small numpy GBDT for the dipdetect study: histogram trees from sel/gbdt_np.py (build / pred), squared-loss regression or
# logistic loss, row + feature subsampling, early stopping on a held-out (later-in-time) slice. Bins = quantiles of the FIT rows.
import sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import gbdt_np as GB

def edges_of(X, fit, nb=32):
    E = []
    for j in range(X.shape[1]):
        x = X[fit, j]; x = x[np.isfinite(x)]
        E.append(np.unique(np.quantile(x, np.linspace(0, 1, nb + 1)[1:-1])) if len(x) else np.array([]))
    return E

def binize(X, E):
    B = np.zeros(X.shape, np.int16)
    for j, e in enumerate(E):
        b = np.searchsorted(e, X[:, j], side="right") + 1; b[~np.isfinite(X[:, j])] = 0; B[:, j] = b
    return B

def fit(B, y, fit_rows, val_rows, loss="l2", rounds=800, lr=0.05, depth=3, min_n=300, lam=10.0, sub=0.7, fsub=0.7, seed=0, patience=80, w=None):
    rng = np.random.default_rng(seed); fr = np.flatnonzero(fit_rows); vr = np.flatnonzero(val_rows)
    if loss == "l2": F0 = float(np.average(y[fr], weights=None if w is None else w[fr]))
    else:
        p0 = float(np.clip(y[fr].mean(), 1e-4, 1 - 1e-4)); F0 = float(np.log(p0 / (1 - p0)))
    f = np.full(len(y), F0); trees = []; best = (np.inf, 0); hist = []
    ww = np.ones(len(y)) if w is None else w
    for k in range(rounds):
        if loss == "l2": gr = (f - y) * ww; he = ww.copy()
        else:
            p = 1 / (1 + np.exp(-f)); gr = (p - y) * ww; he = p * (1 - p) * ww
        rows = np.sort(rng.choice(fr, int(len(fr) * sub), replace=False))
        fs = np.sort(rng.choice(B.shape[1], max(1, int(B.shape[1] * fsub)), replace=False))
        t = GB.build(B, gr, he, rows, depth, lam=lam, min_n=min_n, fsub=fs)
        f += lr * GB.pred(t, B); trees.append(t)
        if loss == "l2": v = float(np.mean((f[vr] - y[vr]) ** 2))
        else:
            pv = np.clip(1 / (1 + np.exp(-f[vr])), 1e-6, 1 - 1e-6); v = float(-np.mean(y[vr] * np.log(pv) + (1 - y[vr]) * np.log(1 - pv)))
        hist.append(v)
        if v < best[0] - 1e-9: best = (v, k + 1)
        elif k + 1 - best[1] > patience: break
    trees = trees[:best[1]]
    return dict(F0=F0, lr=lr, trees=trees, loss=loss, best_round=best[1], hist=hist)

def predict(model, B):
    f = np.full(len(B), model["F0"])
    for t in model["trees"]: f += model["lr"] * GB.pred(t, B)
    return f

def importance(model, nf):
    acc = np.zeros(nf)
    for t in model["trees"]: GB.imp(t, acc)
    return acc / max(acc.sum(), 1e-12)

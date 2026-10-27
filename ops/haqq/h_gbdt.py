#!/usr/bin/env python3
# numpy histogram GBDT (logistic) — copied from ops/overnight/dip/gbdt_np.py (originally ops/select/e_model.py) for the haqq study
import numpy as np
def binize(X, tr):
    B = np.zeros(X.shape, np.int16); edges = []
    for j in range(X.shape[1]):
        x = X[:, j]; xt = x[tr & ~np.isnan(x)]
        e = np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])) if len(xt) else np.array([])
        edges.append(e); b = np.searchsorted(e, x, side="right") + 1; b[np.isnan(x)] = 0; B[:, j] = b
    return B
NB = 34
def build(Bm, gr, he, rows, depth, lam=1.0, min_n=60, fsub=None):
    """returns tree as nested dict; histogram split search over all features at once"""
    G, H = gr[rows].sum(), he[rows].sum()
    if depth == 0 or len(rows) < 2 * min_n: return {"w": -G / (H + lam)}
    F = Bm.shape[1]; sub = Bm[rows][:, fsub]
    flat = (sub + NB * np.arange(len(fsub))).ravel()
    hg = np.bincount(flat, np.repeat(gr[rows], len(fsub)), NB * len(fsub)).reshape(len(fsub), NB)
    hh = np.bincount(flat, np.repeat(he[rows], len(fsub)), NB * len(fsub)).reshape(len(fsub), NB)
    hn = np.bincount(flat, None, NB * len(fsub)).reshape(len(fsub), NB)
    cg, ch, cn = hg.cumsum(1), hh.cumsum(1), hn.cumsum(1)
    gain = cg ** 2 / (ch + lam) + (G - cg) ** 2 / (H - ch + lam) - G ** 2 / (H + lam)
    gain[(cn < min_n) | (len(rows) - cn < min_n)] = -1; gain[:, -1] = -1
    j, b = np.unravel_index(np.argmax(gain), gain.shape)
    if gain[j, b] <= 0: return {"w": -G / (H + lam)}
    f = fsub[j]; left = rows[Bm[rows, f] <= b]; right = rows[Bm[rows, f] > b]
    return {"f": int(f), "b": int(b), "gain": float(gain[j, b]), "l": build(Bm, gr, he, left, depth - 1, lam, min_n, fsub), "r": build(Bm, gr, he, right, depth - 1, lam, min_n, fsub)}
def pred(t, Bm):
    out = np.zeros(len(Bm)); stack = [(t, np.arange(len(Bm)))]
    while stack:
        n, ix = stack.pop()
        if "w" in n: out[ix] = n["w"]; continue
        m = Bm[ix, n["f"]] <= n["b"]; stack.append((n["l"], ix[m])); stack.append((n["r"], ix[~m]))
    return out
def imp(t, acc):
    if "w" in t: return
    acc[t["f"]] += t["gain"]; imp(t["l"], acc); imp(t["r"], acc)
def auc(y, s):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1); p = y.sum(); n = len(y) - p
    return float((r[y == 1].sum() - p * (p + 1) / 2) / (p * n)) if p and n else float("nan")
def fit(Bm, y, tr, va, rounds=600, lr=0.05, depth=3, seed=0):
    rng = np.random.default_rng(seed); p0 = y[tr].mean(); F0 = np.log(p0 / (1 - p0)); f = np.full(len(y), F0); trees = []
    best = (1e9, 0); trn = np.where(tr)[0]
    for k in range(rounds):
        p = 1 / (1 + np.exp(-f)); gr = p - y; he = p * (1 - p)
        rows = rng.choice(trn, int(len(trn) * .8), replace=False); fsub = np.sort(rng.choice(Bm.shape[1], max(1, int(Bm.shape[1] * .8)), replace=False))
        t = build(Bm, gr, he, rows, depth, fsub=fsub); f += lr * pred(t, Bm); trees.append(t)
        pv = np.clip(1 / (1 + np.exp(-f[va])), 1e-6, 1 - 1e-6); ll = -np.mean(y[va] * np.log(pv) + (1 - y[va]) * np.log(1 - pv))
        if ll < best[0] - 1e-5: best = (ll, k + 1)
        elif k + 1 - best[1] > 50: break
    trees = trees[:best[1]]; f = np.full(len(y), F0)
    for t in trees: f += lr * pred(t, Bm)
    return trees, f

# ---- additions for the haqq study: bin edges you can re-apply, and sample weights
def binize_edges(X, tr):
    edges = []
    for j in range(X.shape[1]):
        x = X[:, j]; xt = x[tr & ~np.isnan(x)]
        edges.append(np.unique(np.quantile(xt, np.linspace(0, 1, 33)[1:-1])) if len(xt) else np.array([]))
    return edges
def apply_edges(X, edges):
    B = np.zeros(X.shape, np.int16)
    for j, e in enumerate(edges):
        b = np.searchsorted(e, X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
    return B
def fit_w(Bm, y, w, tr, va, rounds=600, lr=0.05, depth=3, seed=0, min_n=60, patience=50, verbose=False):
    rng = np.random.default_rng(seed); p0 = np.average(y[tr], weights=w[tr]); F0 = np.log(p0 / (1 - p0)); f = np.full(len(y), F0); trees = []
    best = (1e9, 0); trn = np.where(tr)[0]
    for k in range(rounds):
        p = 1 / (1 + np.exp(-f)); gr = w * (p - y); he = w * p * (1 - p)
        rows = rng.choice(trn, int(len(trn) * .8), replace=False); fsub = np.sort(rng.choice(Bm.shape[1], max(1, int(Bm.shape[1] * .8)), replace=False))
        t = build(Bm, gr, he, rows, depth, min_n=min_n, fsub=fsub); f += lr * pred(t, Bm); trees.append(t)
        pv = np.clip(1 / (1 + np.exp(-f[va])), 1e-6, 1 - 1e-6); ll = -np.average(y[va] * np.log(pv) + (1 - y[va]) * np.log(1 - pv), weights=w[va])
        if verbose and k % 50 == 0: print("round", k, round(float(ll), 5), flush=True)
        if ll < best[0] - 1e-5: best = (ll, k + 1)
        elif k + 1 - best[1] > patience: break
    return trees[:best[1]], F0
def predict(trees, F0, Bm, lr):
    f = np.full(len(Bm), F0)
    for t in trees: f += lr * pred(t, Bm)
    return 1 / (1 + np.exp(-f))

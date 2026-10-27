#!/usr/bin/env python3
"""EXPLORATION: is there ANY transferable signal in the ARM features? Diagnostic models (not a proposed rule):
  (1) logistic regression (numpy, L2) on dev fills, leave-one-run-out: train AMS r24 -> score AMS r25, and the reverse;
  (2) the same model trained on the chain-wide tuning events (proxy label: proxy net > 0) -> scored on the dev live fills.
Reports the held-out AUC (win vs not) and the held-out P&L of skipping the lowest-scored 10 / 20 / 30% of windows (ARM skip, sim.py)."""
import json
import numpy as np
import sim
B = "/home/moiz/sniper-data/presend_filter"
FEATS = ["age", "n_tr", "n_users", "vol", "n_tr_10", "n_tr_50", "cre_prev", "dev_hold", "wh_nf", "wh_dump_fol", "wh_n", "wh_tokens_before", "coh_n", "coh_hold",
         "fb_n", "fb_hold", "n_big", "top10", "pct", "whale_sol", "vsol", "tok_dumps", "since_last", "p_ret_20", "dd_peak", "trig_tip"]
LOG = {"age", "n_tr", "n_users", "vol", "n_tr_10", "n_tr_50", "cre_prev", "wh_n", "wh_tokens_before", "coh_n", "fb_n", "tok_dumps", "since_last", "trig_tip"}


def X_of(rows, mu=None, sd=None):
    X = np.array([[float(r.get(f)) if r.get(f) is not None else 0.0 for f in FEATS] for r in rows])
    for j, f in enumerate(FEATS):
        if f in LOG: X[:, j] = np.log1p(np.maximum(X[:, j], 0))
    if mu is None: mu, sd = X.mean(0), X.std(0) + 1e-9
    return (X - mu) / sd, mu, sd


def fit(X, y, lam=1.0, it=3000, lr=0.1):
    w = np.zeros(X.shape[1]); b = 0.0
    for _ in range(it):
        p = 1 / (1 + np.exp(-(X @ w + b)))
        g = X.T @ (p - y) / len(y) + lam * w / len(y); gb = (p - y).mean()
        w -= lr * g; b -= lr * gb
    return w, b


def auc(s, y):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    return (r[y == 1].sum() - (y == 1).sum() * ((y == 1).sum() + 1) / 2) / max((y == 1).sum() * (y == 0).sum(), 1)


W = [w for w in sim.load(("ams:r24", "ams:r25")) if w["chain_ok"]]
for tr, te in (("ams:r24", "ams:r25"), ("ams:r25", "ams:r24")):
    Ftr = [w for w in W if w["run"] == tr and w["filled"]]
    Xtr, mu, sd = X_of(Ftr); ytr = np.array([w["net"] > 0 for w in Ftr], float)
    wv, b = fit(Xtr, ytr, lam=5.0)
    Wte = [w for w in W if w["run"] == te]
    Xte, _, _ = X_of(Wte, mu, sd); s = Xte @ wv + b
    Fm = np.array([w["filled"] for w in Wte]); yte = np.array([w["filled"] and w["net"] > 0 for w in Wte], float)
    print(f"train {tr} -> test {te}: held-out AUC on fills {auc(s[Fm], yte[Fm]):.3f}")
    for q in (10, 20, 30):
        thr = np.percentile(s, q); sc = {id(w): v for w, v in zip(Wte, s)}
        r = sim.evaluate(Wte, arm=lambda w: sc[id(w)] >= thr)
        print(f"   skip lowest {q}%: " + sim.fmt(r, [te]).split("\n")[0])
# chain-wide -> dev
T_VAL0, T_VAL1 = 1792948200, 1793033220
E = [e for e in json.load(open(f"{B}/chain_events.json")) if e["fill"] and e["bt"] < T_VAL0]
Xe, mu, sd = X_of(E); ye = np.array([e["y_net"] > 0 for e in E], float)
wv, b = fit(Xe, ye, lam=5.0)
print("chain-wide (before 10-25 22:00, proxy label) -> dev live:")
print("   weights:", {f: round(v, 2) for f, v in sorted(zip(FEATS, wv), key=lambda t: -abs(t[1]))[:10]})
Xd, _, _ = X_of(W, mu, sd); s = Xd @ wv + b
Fm = np.array([w["filled"] for w in W]); yd = np.array([w["filled"] and w["net"] > 0 for w in W], float)
print(f"   AUC on dev fills {auc(s[Fm], yd[Fm]):.3f}")
sc = {id(w): v for w, v in zip(W, s)}
for q in (10, 20, 30):
    thr = np.percentile(s, q)
    print(f"   skip lowest {q}%:\n" + sim.fmt(sim.evaluate(W, arm=lambda w: sc[id(w)] >= thr), ["ams:r24", "ams:r25"]))

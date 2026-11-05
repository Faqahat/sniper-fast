"""FLATSIG BOTSEL model: logistic regression (numpy, L2) of 'a cohort bot (COH, DEV-fit) BUYS within 2 slots after the first 12% dip'
on chain-wide T2-like triggers (pump curve vsol>=28, whale >=1 SOL, age>=2 slots, dip within 10 slots), causal features only.
Fit on DEV chain rows (block time < 11-01 12:00 PKT). transform(): log1p on counts, history rates with a 'no history' flag."""
import numpy as np
FEATS = ["age", "vsol_pre", "pct", "sol", "n_prior", "n_60", "n_120", "n_10s", "buyers", "sellers", "buy_sol_60", "sell_sol_60",
         "nN_prior", "nN_dist", "nN_hold", "nC_prior", "nC_dist", "nC_hold", "wh_n", "wh_botN", "wh_botC", "wh_prev_age",
         "cr_n", "cr_botN", "nb_same_slot", "big_sells_60", "max_hold_pct", "nN_last_age"]
LOG = {"age", "n_prior", "n_60", "n_120", "n_10s", "buyers", "sellers", "buy_sol_60", "sell_sol_60", "nN_prior", "nN_dist", "nN_hold",
       "nC_prior", "nC_dist", "nC_hold", "wh_n", "wh_prev_age", "cr_n", "nb_same_slot", "big_sells_60", "nN_last_age", "sol"}
RATE = {"wh_botN", "wh_botC", "cr_botN"}

def transform(rows):
    """rows: list of feature dicts -> design matrix"""
    out = []
    for f in rows:
        x = []
        for c in FEATS:
            v = f[c]
            if c in RATE: x += [max(v, 0.0), 1.0 if v < 0 else 0.0]
            elif c in LOG: x.append(np.log1p(max(v, 0.0)))
            else: x.append(v)
        out.append(x)
    return np.array(out, dtype=float)

def fit(X, y, l2=1.0, it=3000, lr=0.5):
    mu, sd = X.mean(0), X.std(0) + 1e-9
    Z = (X - mu) / sd; Z = np.c_[np.ones(len(Z)), Z]
    w = np.zeros(Z.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-Z @ w))
        g = Z.T @ (p - y) / len(y) + l2 * np.r_[0, w[1:]] / len(y)
        w -= lr * g
    return {"mu": mu.tolist(), "sd": sd.tolist(), "w": w.tolist()}

def score(m, X):
    Z = (X - np.array(m["mu"])) / np.array(m["sd"]); Z = np.c_[np.ones(len(Z)), Z]
    return 1 / (1 + np.exp(-Z @ np.array(m["w"])))

def auc(s, y):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1)

#!/usr/bin/env python3
"""SL-REDFLAGS s8: small logistic model for big loss (< -0.08 or SL) on the trades no existing guard blocks; train on FIT
(r39..r42; rows with holder data), score VAL (r43..r49); block the top q% by score (q from FIT), money on realized P&L."""
import numpy as np
class LogisticRegression:
    def __init__(self, C=1.0, max_iter=2000): self.l2 = 1.0 / C; self.it = max_iter
    def fit(self, X, y):
        n, k = X.shape; w = np.zeros(k); b = 0.0
        for _ in range(self.it):
            p = 1 / (1 + np.exp(-(X @ w + b))); gw = X.T @ (p - y) / n + self.l2 * w / n; gb = (p - y).mean()
            w -= 0.5 * gw; b -= 0.5 * gb
        self.coef_ = np.array([w]); self.b = b; return self
    def predict_proba(self, X):
        p = 1 / (1 + np.exp(-(X @ self.coef_[0] + self.b))); return np.c_[1 - p, p]
def roc_auc_score(y, s):
    y = np.asarray(y); o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    P = y.sum(); N = len(y) - P; return (r[y == 1].sum() - P * (P + 1) / 2) / (P * N)
from slib import rows, g, mark_prior
R = rows(); mark_prior(R)
FE = ["rise", "w_pct", "trig_sol", "trig_vsol", "max_oth", "sum_oth", "n_oth6", "sum_fresh", "sum_bot", "co_whale", "whale_n", "nb50", "sign_after_trig"]
def X(d):
    v = [float(g(d, f, 0) or 0) for f in FE]
    v += [np.log1p(max(g(d, "age", 0), 0)), float(d["kind"] == "t2"), np.log1p(g(d, "n120", 0) or 0)]
    return v
U = [d for d in R if d["prior"] is None and d.get("holders") is not None]
fit = [d for d in U if d["grp"] == "FIT"]; val = [d for d in U if d["grp"] == "VAL"]
y = lambda xs: np.array([int(d["sl"] or d["pnl"] < -0.08) for d in xs])
Xf, Xv = np.array([X(d) for d in fit]), np.array([X(d) for d in val])
mu, sd = Xf.mean(0), Xf.std(0) + 1e-9
m = LogisticRegression(C=0.3, max_iter=2000).fit((Xf - mu) / sd, y(fit))
pf, pv = m.predict_proba((Xf - mu) / sd)[:, 1], m.predict_proba((Xv - mu) / sd)[:, 1]
print("n fit", len(fit), "pos", y(fit).sum(), "AUC", round(roc_auc_score(y(fit), pf), 3), "| n val", len(val), "pos", y(val).sum(), "AUC", round(roc_auc_score(y(val), pv), 3))
# chronological 2-fold inside FIT: train first half, test second half
h = len(fit) // 2
m2 = LogisticRegression(C=0.3, max_iter=2000).fit((Xf[:h] - mu) / sd, y(fit)[:h]); p2 = m2.predict_proba((Xf[h:] - mu) / sd)[:, 1]
print("FIT 2nd half (trained on 1st):", "AUC", round(roc_auc_score(y(fit)[h:], p2), 3))
for q in (0.02, 0.05, 0.10):
    thr = np.quantile(pf, 1 - q)
    for nm, xs, p in (("FIT(in-sample)", fit, pf), ("FIT 2nd half", fit[h:], p2), ("VAL", val, pv)):
        t = thr if nm != "FIT 2nd half" else np.quantile(m2.predict_proba((Xf[:h] - mu) / sd)[:, 1], 1 - q)
        b = [d for d, s in zip(xs, p) if s >= t]; pn = sorted(d["pnl"] for d in b)
        print(f"  q {q:.2f} {nm:15s} blocked {len(b):3d} SL {sum(d['sl'] for d in b)} saved {-sum(pn):+.2f} w/o5 {-sum(pn) + sum(pn[:5]):+.2f} winners {sum(x > 0 for x in pn)}")
print("coef", {f: round(c, 2) for f, c in zip(FE + ["log_age", "is_t2", "log_n120"], m.coef_[0])})

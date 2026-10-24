#!/usr/bin/env python3
# Consistency check of the selection finding across model variants (all reported, none chosen on test):
#  V1 logistic demand>=3 (= frozen recipe) | V2 logistic demand>=1 | V3 ridge on log1p(demand) | V4 logistic on
#  "strict L45 t5 PnL > 0" | V5 = V1 without the live-engine (t_*) features. Out-of-sample both directions. -> variants.txt
import sys, os, json, math
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/nonsol")
import io, contextlib
with contextlib.redirect_stdout(io.StringIO()):
    import ns_select as S
from ns_lib import *
rows = S.rows
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1])
def ridge(X, y, lam=10.0):
    mu = np.nanmean(X, 0); X = np.where(np.isnan(X), mu, X); sd = X.std(0); sd[sd == 0] = 1; Z = (X - mu) / sd
    A = Z.T @ Z + lam * np.eye(Z.shape[1]); w = np.linalg.solve(A, Z.T @ (y - y.mean()))
    return dict(mu=mu, sd=sd, w=w, b=y.mean())
def lab(name, r):
    d = S.demand(r)
    if name in ("V1", "V5"): return 1.0 if d >= 3 else 0.0
    if name == "V2": return 1.0 if d >= 1 else 0.0
    if name == "V3": return math.log1p(d)
    if name == "V4":
        p = pnl(r, 45, "strict", "5.0"); return 1.0 if (p is not None and p != FAIL and p > 0) else 0.0
FNa = S.FN; idx_not = [i for i, k in enumerate(FNa) if not k.startswith("t_")]
for V in ("V1", "V2", "V3", "V4", "V5"):
    for tr_run, te_run in (("R1", "R2"), ("R2", "R1")):
        TR_ = [r for r in rows if r["run"] == tr_run]; TE_ = [r for r in rows if r["run"] == te_run]
        Xtr, Xte = S.mat(TR_), S.mat(TE_)
        if V == "V5": Xtr, Xte = Xtr[:, idx_not], Xte[:, idx_not]
        y = np.array([lab(V, r) for r in TR_])
        m = ridge(Xtr, y) if V == "V3" else S.fit(Xtr, y)
        s_tr, s_te = S.score(m, Xtr), S.score(m, Xte)
        cells = []
        for qq in (0.02, 0.05):
            thr = np.quantile(s_tr, 1 - qq); se = [r for r, s in zip(TE_, s_te) if s >= thr]
            cells.append(f"top{int(qq*100)}% n={len(se):3d}: " + " ".join(f"L{Lm} t5 {summ(se,Lm,'strict','5.0')['tot']:+5.2f} t8 {summ(se,Lm,'strict','8.0')['tot']:+5.2f}" for Lm in (30, 45, 75)))
        P(f"{V} {tr_run}->{te_run} | " + " || ".join(cells))
open(os.path.join(HERE, "variants.txt"), "w").write("\n".join(out) + "\n")

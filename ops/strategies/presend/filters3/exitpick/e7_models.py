#!/usr/bin/env python3
"""EXITPICK step 7: (a) depth-2 tree on DEV (A+B features, leaf = best exit on DEV), (b) ridge per exit (gain vs t125), argmax policy,
(c) the 400 ms second decision (t400 vs t1000 from the tape up to 385 ms), (d) leave-one-run-out of the 'best one-feature rule' procedure."""
import statistics, math
import numpy as np
from elib import *
R = load()
A = sorted(R[0]["A"].keys()); Bf = sorted(R[0]["B"]["15"].keys()); FE = A + Bf
ACT = ["t125", "t100"] + EXT
sp = {s: [r for r in R if r["split"] == s] for s in ("dev", "val", "hold")}
def M(rows): return np.array([[feat(r, f) for f in FE] for r in rows], float)
def Y(rows, var="y"): return np.array([[gain(r, k, var) for k in ACT] for r in rows], float)
X = {s: M(v) for s, v in sp.items()}; G = {s: Y(v) for s, v in sp.items()}; Gf = {s: Y(v, "y_fc") for s, v in sp.items()}
def pol_val(acts, s, var=None):
    g = (Gf if var == "fc" else G)[s]
    return float(sum(g[i, a] for i, a in enumerate(acts)))
# (a) depth-2 tree
def best_leaf(idx, g): return int(np.argmax(g[idx].sum(0))) if len(idx) else 0
def grow(idx, x, g, depth, minleaf=40):
    a = best_leaf(idx, g); v = g[idx, a].sum() if len(idx) else 0
    if depth == 0: return ("leaf", a)
    best = None
    for j in range(x.shape[1]):
        qs = sorted(set(np.quantile(x[idx, j], np.linspace(0.1, 0.9, 9))))
        for th in qs:
            L = idx[x[idx, j] < th]; Rr = idx[x[idx, j] >= th]
            if len(L) < minleaf or len(Rr) < minleaf: continue
            vv = g[L].sum(0).max() + g[Rr].sum(0).max()
            if best is None or vv > best[0]: best = (vv, j, th, L, Rr)
    if best is None or best[0] <= v + 1e-9: return ("leaf", a)
    return ("split", best[1], best[2], grow(best[3], x, g, depth - 1, minleaf), grow(best[4], x, g, depth - 1, minleaf))
def apply(t, xrow):
    while t[0] == "split": t = t[3] if xrow[t[1]] < t[2] else t[4]
    return t[1]
def show(t, ind=""):
    if t[0] == "leaf": return f"{ind}-> {ACT[t[1]]}\n"
    return f"{ind}{FE[t[1]]} < {t[2]:.4g}:\n" + show(t[3], ind + "  ") + f"{ind}else:\n" + show(t[4], ind + "  ")
for depth in (1, 2):
    for ml in (40, 80):
        t = grow(np.arange(len(sp["dev"])), X["dev"], G["dev"], depth, ml)
        out = {s: pol_val([apply(t, xr) for xr in X[s]], s) for s in sp}
        outf = {s: pol_val([apply(t, xr) for xr in X[s]], s, "fc") for s in sp}
        ext = {s: sum(1 for xr in X[s] if apply(t, xr) != 0) for s in sp}
        print(f"(a) tree depth {depth} minleaf {ml}: gain vs t125 dev {out['dev']:+.3f} val {out['val']:+.3f} hold {out['hold']:+.3f} | fc20 dev {outf['dev']:+.3f} val {outf['val']:+.3f} hold {outf['hold']:+.3f} | changed exits {ext}")
        print("   " + show(t, "   ").strip().replace("\n", "\n   "))
# (b) ridge
mu = X["dev"].mean(0); sd = X["dev"].std(0) + 1e-9
Z = {s: (X[s] - mu) / sd for s in sp}
def ridge(z, g, lam):
    zz = np.hstack([z, np.ones((len(z), 1))]); I = np.eye(zz.shape[1]); I[-1, -1] = 0
    return np.linalg.solve(zz.T @ zz + lam * I, zz.T @ g)
def pred(w, z): return np.hstack([z, np.ones((len(z), 1))]) @ w
# choose lam & margin by time-ordered 2-fold inside DEV (first half -> second half and back)
n = len(Z["dev"]); h = n // 2
best = None
for lam in (10, 100, 1000, 10000):
    for marg in (0.0, 0.002, 0.005, 0.01):
        tot = 0
        for tr, te in ((slice(0, h), slice(h, n)), (slice(h, n), slice(0, h))):
            w = ridge(Z["dev"][tr], G["dev"][tr], lam); p = pred(w, Z["dev"][te]); p[:, 0] = 0
            acts = [int(np.argmax(r)) if r.max() > marg else 0 for r in p]
            tot += sum(G["dev"][te][i, a] for i, a in enumerate(acts))
        if best is None or tot > best[0]: best = (tot, lam, marg)
print(f"(b) ridge: inner-DEV CV best lam {best[1]} margin {best[2]} cv gain {best[0]:+.3f}")
w = ridge(Z["dev"], G["dev"], best[1])
for s in sp:
    p = pred(w, Z[s]); p[:, 0] = 0
    acts = [int(np.argmax(r)) if r.max() > best[2] else 0 for r in p]
    print(f"    {s}: gain {pol_val(acts, s):+.3f} fc20 {pol_val(acts, s, 'fc'):+.3f} changed {sum(1 for a in acts if a)}/{len(acts)}")
# (c) second decision at 400 ms: among all fills, t400 vs t1000 by the tape up to 385 ms (one-feature rules, DEV-picked)
Cf = sorted(k for k in R[0]["B400"].keys())
res = []
for f in Cf:
    xs = {s: [r["B400"][f] for r in v] for s, v in sp.items()}
    for th in sorted(set(statistics.quantiles(xs["dev"], n=10, method="inclusive"))):
        for op in (">=", "<"):
            m = {s: [(a >= th) == (op == ">=") for a in xs[s]] for s in sp}
            if sum(m["dev"]) < 30: continue
            g = {s: sum(y(r, "t1000") - y(r, "t400") for r, mm in zip(sp[s], m[s]) if mm) for s in sp}
            res.append((g["dev"], g["val"], g["hold"], f, op, th, sum(m["dev"])))
res.sort(key=lambda z: -z[0])
print("(c) at 400 ms: hold to 1000 if <rule> else sell at 400 (gain vs t400 sum):")
for z in res[:5]: print(f"    dev {z[0]:+.3f} val {z[1]:+.3f} hold {z[2]:+.3f}  {z[3]} {z[4]} {z[5]:.4g} n_dev {z[6]}")
dv = [z[0] for z in res]; vv = [z[1] for z in res]
print(f"    corr(dev, val) over {len(res)} rules: {np.corrcoef(dv, vv)[0, 1]:+.3f}")
# (d) LORO: pick the best one-feature rule (A+B, deciles, >=30 picks) on all other runs, apply to the left-out run
print("(d) leave-one-run-out of the best-one-feature-rule procedure (gain vs t125 on the left-out run):")
runs = sorted({r["run"] for r in R}); tot = 0; totf = 0
for lo in runs:
    trn = [r for r in R if r["run"] != lo]; tst = [r for r in R if r["run"] == lo]
    xt = M(trn); gt = Y(trn); xs = M(tst); gs = Y(tst); gsf = Y(tst, "y_fc")
    best = None
    for j in range(len(FE)):
        for th in sorted(set(np.quantile(xt[:, j], np.linspace(0.1, 0.9, 9)))):
            for op in (0, 1):
                m = (xt[:, j] >= th) if op == 0 else (xt[:, j] < th)
                if m.sum() < 30: continue
                v = gt[m].sum(0); v[0] = -9e9; a = int(np.argmax(v))
                if best is None or v[a] > best[0]: best = (v[a], j, th, op, a)
    _, j, th, op, a = best
    m = (xs[:, j] >= th) if op == 0 else (xs[:, j] < th)
    gg = gs[m, a].sum(); ggf = gsf[m, a].sum(); tot += gg; totf += ggf
    print(f"    r{lo}: rule {FE[j]} {'>=' if op == 0 else '<'} {th:.4g} -> {ACT[a]} (train gain {best[0]:+.2f}) | left-out gain {gg:+.3f} fc20 {ggf:+.3f} on {int(m.sum())}/{len(tst)}")
print(f"    LORO total {tot:+.3f} (fc20 {totf:+.3f})")

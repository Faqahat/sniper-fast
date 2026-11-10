#!/usr/bin/env python3
"""Landing-model variants, leave-one-out on the 81 live attempts."""
import json, numpy as np
D = json.load(open("/home/it/sniper-data/apex2/realism/landing_model.json"))
oc, rc, u, land = map(np.array, (D["our_clk"], D["rival_clk"], D["u"], D["land"])); land = land.astype(float); n = len(oc)
def ll(p): p = np.clip(p, .02, .98); return -np.mean(land * np.log(p) + (1 - land) * np.log(1 - p))
def rep(nm, p):
    print(f"{nm:34s} sum {p.sum():5.1f}/{int(land.sum())} Brier {np.mean((p - land) ** 2):.3f} logloss {ll(p):.3f}  by rival clk:",
          " ".join(f"[{lo}-{hi}: {p[(rc >= lo) & (rc < hi)].mean():.2f}/{land[(rc >= lo) & (rc < hi)].mean():.2f}]" for lo, hi in ((0, .05), (.05, .2), (.2, .5), (.5, 1), (1, 99))))
rep("V1 empirical our-clk CDF", np.array([np.mean(np.delete(oc, k) < rc[k]) for k in range(n)]))
for W in (20, 30, 40):
    p = []
    for k in range(n):
        o = np.delete(oc, k); uu = np.delete(u, k); nn = np.argsort(np.abs(uu - u[k]))[:W]; p.append(np.mean(o[nn] < rc[k]))
    rep(f"V2 u-conditional (nearest {W})", np.array(p))
# V3: our time in 'slot-relative' terms: our land offset = (slot boundary aware). rival same slot vs next
nxt = (rc + u >= 1)   # rival lands after the create slot ended
on = (oc + u >= 1)
p = []
for k in range(n):
    m = np.arange(n) != k
    p.append(np.mean(oc[m] < rc[k]) if not nxt[k] else np.mean((oc[m] + u[m] - 1)[on[m]] < rc[k] + u[k] - 1) * on[m].mean() + (~on[m]).mean())
rep("V3 slot-aware (next-slot pos)", np.array(p))
# V4 logistic on log(rc), next-slot flag
def fitlog(Xm, y, l2=0.1):
    w = np.zeros(Xm.shape[1])
    for _ in range(300):
        z = Xm @ w; pp = 1 / (1 + np.exp(-z)); g = Xm.T @ (pp - y) / len(y) + l2 * np.r_[0, w[1:]]
        H = (Xm.T * (pp * (1 - pp))) @ Xm / len(y) + l2 * np.diag(np.r_[0, np.ones(len(w) - 1)])
        w -= np.linalg.solve(H + 1e-9 * np.eye(len(w)), g)
    return w
Xf = np.c_[np.ones(n), np.log(np.minimum(rc, 3)), nxt.astype(float)]
p = []
for k in range(n):
    m = np.arange(n) != k; w = fitlog(Xf[m], land[m]); p.append(1 / (1 + np.exp(-Xf[k] @ w)))
rep("V4 logistic log(rival clk)+nextslot", np.array(p)); print("   full-fit w", fitlog(Xf, land).round(3))
Xf2 = Xf[:, :2]; p = []
for k in range(n):
    m = np.arange(n) != k; w = fitlog(Xf2[m], land[m]); p.append(1 / (1 + np.exp(-Xf2[k] @ w)))
rep("V5 logistic log(rival clk)", np.array(p)); print("   full-fit w", fitlog(Xf2, land).round(3))

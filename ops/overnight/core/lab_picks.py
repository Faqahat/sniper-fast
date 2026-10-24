#!/usr/bin/env python3
# Strategy lab, step 1: hybrid pick lists for the R2 window (launches with our engine's timelines), built only from
# information known at the create / bundle close.
#   F2        FINAL-2 live picks (shadow log)
#   F2_HOT    F2 minus CW's "cold dev" signs (MEASURED in its study on generic flow): relaunch < 60 s after the deployer's
#             previous launch, dev buy >= 4 SOL, or the deployer's previous launch fell by +10 s
#   DKs_k     dK-STYLE model: logistic on public create-time features (dK's own attempts on the deployer REMOVED),
#             trained on R1 to predict which launches dK attempts; R2 launches ranked by it, top k%
#   F2_DK     F2 picks that the dK-style model also ranks in its top 10% (agreement -> conviction)
#   F2uDK2    union of F2 and DKs_2
import json, math, sys
import numpy as np
CORE = "/home/moiz/sniper/ops/overnight/core"; DK = "/home/moiz/sniper/ops/overnight/dkmjeg"
F2 = set(json.load(open(f"{CORE}/final2_picks_v3.json")))
LS = json.load(open(f"{CORE}/gf_launches.json"))
R = json.load(open(f"{DK}/sel_rows.json"))
byd = {}
for m, v in LS.items(): byd.setdefault(v["dep"], []).append((v["bt"], m))
for d in byd: byd[d].sort()
def prev_launch(m):
    v = LS.get(m)
    if not v: return None
    p = [x for x in byd[v["dep"]] if x[0] < v["bt"] - 10]       # previous launch whose +10 s outcome is known
    return (v["bt"] - p[-1][0], LS[p[-1][1]]) if p else None
dev = {r["m"]: (r.get("dev_buy") or 0) for r in R}
def cold(m):
    pl = prev_launch(m)
    if dev.get(m, 0) >= 4: return True
    if pl and pl[0] < 60: return True
    if pl and pl[1]["m10"] < 1.0: return True
    return False
# dK-style model without its own attempts
def f(r):
    lg = lambda x: math.log1p(max(0.0, x or 0.0)); dv = r["dev_buy"] or 0; gs = r["glued_sol"] or 0; ms = r["cr_min_since_prev_create"]
    return [lg(dv), lg(gs), lg(dv + gs), min(r["glued_n"] or 0, 10) / 10, 1.0 if (r["glued_n"] or 0) > 0 else 0.0, r["has_tw"] or 0, r["has_web"] or 0,
            r["has_tg"] or 0, r["tw_status"] or 0, r["tw_community"] or 0, 1.0 if ms is None else 0.0, lg(ms) if ms is not None else 0.0,
            lg(r["dep_prev_n"]), 1.0 if r["dep_prev_n"] == 0 else 0.0, lg(r["cr_prior_n"]), lg(r["desc_len"]) / 6, 1.0 if r["quote_sol"] else 0.0,
            1.0 if (r["create_cup"] or 0) >= 1e6 else 0.0, 1.0 if r["create_cup"] is None else 0.0, 1.0 if r["uri_host"] == "ipfs.io" else 0.0,
            1.0 if "j7tracker" in (r["uri_host"] or "") else 0.0, 1.0 if "uxento" in (r["uri_host"] or "") else 0.0, 1.0 if "rapidlaunch" in (r["uri_host"] or "") else 0.0,
            1.0 if r["payer_is_creator"] else 0.0, math.sin(2 * math.pi * (r["hour_utc"] or 0) / 24), math.cos(2 * math.pi * (r["hour_utc"] or 0) / 24)]
X = np.array([f(r) for r in R]); y = np.array([r["att"] for r in R], float); run = np.array([r["run"] for r in R])
def fit(X, y, l2=1.0, it=100):
    mu = X.mean(0); sd = X.std(0) + 1e-9; Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))]); w = np.zeros(Z.shape[1])
    for _ in range(it):
        p = 1 / (1 + np.exp(-Z @ w)); g = Z.T @ (p - y) + l2 * np.r_[w[:-1], 0]
        H = (Z * (p * (1 - p))[:, None]).T @ Z + l2 * np.diag(np.r_[np.ones(len(w) - 1), 0]); st = np.linalg.solve(H, g); w -= st
        if np.abs(st).max() < 1e-6: break
    return w, mu, sd
tr = run == "R1"; te = run == "R2"
w, mu, sd = fit(X[tr], y[tr])
s = 1 / (1 + np.exp(-(np.hstack([(X - mu) / sd, np.ones((len(X), 1))]) @ w)))
o = np.argsort(s); rk = np.empty(len(s)); rk[o] = np.arange(len(s))
r2 = [i for i in range(len(R)) if te[i]]; s2 = np.array([s[i] for i in r2]); y2 = np.array([y[i] for i in r2])
oo = np.argsort(s2); rr = np.empty(len(s2)); rr[oo] = np.arange(1, len(s2) + 1); n1 = y2.sum()
print(f"dK-style model (no dK-attempt feature): test AUC on R2 for predicting dK's attempts: {(rr[y2 == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * (len(y2) - n1)):.3f}")
thr = {k: np.quantile(s2, 1 - k / 100) for k in (2, 5, 10)}
DKs = {k: {R[i]["m"] for i in r2 if s[i] >= thr[k]} for k in (2, 5, 10)}
out = dict(F2=sorted(F2), F2_HOT=sorted(m for m in F2 if not cold(m)), DKs_2=sorted(DKs[2]), DKs_5=sorted(DKs[5]),
           F2_DK=sorted(F2 & DKs[10]), F2uDK2=sorted(F2 | DKs[2]))
for k, v in out.items():
    json.dump(v, open(f"{CORE}/lab_{k}.json", "w")); print(f"  {k:8s} {len(v)} picks")
print(f"  cold-dev reasons among F2: dev>=4 {sum(1 for m in F2 if dev.get(m, 0) >= 4)}, relaunch<60s {sum(1 for m in F2 if (prev_launch(m) or (9e9,))[0] < 60)}, prev fell {sum(1 for m in F2 if prev_launch(m) and prev_launch(m)[1]['m10'] < 1)}")

#!/usr/bin/env python3
# READ-ONLY, offline: (1) multivariate logistic model of dK's attempts, train R1 -> test R2 (AUC, lift);
# (2) do its picks beat the average launch (market outcome vs P0 at +1/5/15/60 s, peak 60 s; our S4 replay result)?
import json, math, collections, statistics as S
import numpy as np
R = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/sel_rows.json"))
C = json.load(open("/home/moiz/sniper/ops/overnight/dkmjeg/coll.json"))
AR = json.load(open("/home/moiz/sniper/ops/overnight/core/allres.json"))
def f(r):
    lg = lambda x: math.log1p(max(0.0, x or 0.0))
    dv = r["dev_buy"] or 0; gs = r["glued_sol"] or 0
    ms = r["cr_min_since_prev_create"]
    return [lg(dv), lg(gs), lg(dv + gs), min(r["glued_n"] or 0, 10) / 10, 1.0 if (r["glued_n"] or 0) > 0 else 0.0,
            r["has_tw"] or 0, r["has_web"] or 0, r["has_tg"] or 0, r["tw_status"] or 0, r["tw_community"] or 0,
            1.0 if ms is None else 0.0, lg(ms) if ms is not None else 0.0,
            lg(r["dep_prev_n"]), lg(r["dep_prev_att"]), 1.0 if r["dep_prev_n"] == 0 else 0.0,
            lg(r["cr_prior_n"]), lg(r["desc_len"]) / 6, 1.0 if r["quote_sol"] else 0.0,
            1.0 if (r["create_cup"] or 0) >= 1e6 else 0.0, 1.0 if r["create_cup"] is None else 0.0,
            1.0 if r["uri_host"] == "ipfs.io" else 0.0, 1.0 if "j7tracker" in (r["uri_host"] or "") else 0.0, 1.0 if "uxento" in (r["uri_host"] or "") else 0.0,
            1.0 if "rapidlaunch" in (r["uri_host"] or "") else 0.0, 1.0 if r["payer_is_creator"] else 0.0,
            math.sin(2 * math.pi * (r["hour_utc"] or 0) / 24), math.cos(2 * math.pi * (r["hour_utc"] or 0) / 24)]
NAMES = ["log dev", "log bundle", "log dev+bundle", "glued_n/10", "has bundle", "tw", "web", "tg", "tw_status", "tw_comm", "no prev create", "log min since prev create",
         "log dep prev n", "log dep prev dK att", "dep new", "log creator prior", "desc", "SOL quote", "create cup>=1e6", "create cup none", "ipfs", "j7tracker", "uxento", "rapidlaunch", "payer=creator", "hour sin", "hour cos"]
X = np.array([f(r) for r in R]); y = np.array([r["att"] for r in R], dtype=float); run = np.array([r["run"] for r in R])
def fit(X, y, l2=1.0, it=300):
    mu = X.mean(0); sd = X.std(0) + 1e-9; Z = (X - mu) / sd; Z = np.hstack([Z, np.ones((len(Z), 1))]); w = np.zeros(Z.shape[1])
    for _ in range(it):   # Newton steps
        p = 1 / (1 + np.exp(-Z @ w)); g = Z.T @ (p - y) + l2 * np.r_[w[:-1], 0]
        H = (Z * (p * (1 - p))[:, None]).T @ Z + l2 * np.diag(np.r_[np.ones(len(w) - 1), 0])
        step = np.linalg.solve(H, g); w -= step
        if np.abs(step).max() < 1e-6: break
    return w, mu, sd
def pred(w, mu, sd, X):
    Z = np.hstack([(X - mu) / sd, np.ones((len(X), 1))]); return 1 / (1 + np.exp(-Z @ w))
def auc(s, y):
    o = np.argsort(s); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1); n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0)
tr = run == "R1"; te = run == "R2"
w, mu, sd = fit(X[tr], y[tr]); s = pred(w, mu, sd, X[te])
print(f"logistic model on {len(NAMES)} create-time features: train R1 n={tr.sum()} ({int(y[tr].sum())} attempts) -> test R2 n={te.sum()} ({int(y[te].sum())} attempts): AUC {auc(s, y[te]):.3f}")
o = np.argsort(-s); yt = y[te][o]
for q in (0.01, 0.02, 0.05, 0.10, 0.20):
    k = int(q * len(o)); print(f"   top {q:.0%} of R2 launches by score: {int(yt[:k].sum())}/{k} attempted ({yt[:k].mean():.1%}; base {y[te].mean():.1%}); recall {yt[:k].sum() / y[te].sum():.0%}")
wa, mua, sda = fit(X, y)
print("   standardized weights (all data):", ", ".join(f"{n} {v:+.2f}" for n, v in sorted(zip(NAMES, wa[:-1]), key=lambda kv: -abs(kv[1]))[:14]))
# (2) outcomes of its picks vs others (SOL-quoted launches with a P0)
def outcome(sel_fn, label):
    g = collections.defaultdict(list)
    for r in R:
        c = C[r["m"]]
        if not c.get("px"): continue
        g[sel_fn(r, c)].append(c)
    for k in sorted(g, key=str):
        v = g[k]
        pxs = {h: [x["px"][h] for x in v if x["px"].get(h)] for h in ("1s", "5s", "15s", "60s")}
        print(f"   {label}={k!s:6} n={len(v):5} | price vs P0 median at 1s {S.median(pxs['1s']):.3f} 5s {S.median(pxs['5s']):.3f} 15s {S.median(pxs['15s']):.3f} 60s {S.median(pxs['60s']):.3f} | "
              f"peak60 med {S.median(x['pk60'] for x in v):.3f} | P(15s > 1.2) {sum(1 for p in pxs['15s'] if p > 1.2) / max(1, len(pxs['15s'])):.1%} | graduated {sum(x['grad'] for x in v) / len(v):.1%}")
print("market outcome, all SOL-quoted non-mayhem launches with a bundle-close price:")
outcome(lambda r, c: r["att"], "attempted")
print("same, only launches with dev+bundle >= 2 SOL and a website (its preferred region):")
outcome(lambda r, c: r["att"] if ((r["dev_buy"] or 0) + (r["glued_sol"] or 0) >= 2 and r["has_web"]) else "other", "attempted")
# our S4 replay (1% guard, sell end of next slot, 0.5 SOL) on its picks vs all, R2 real placement
for Lm in ("45", "75"):
    for lab, fn in (("its attempts", lambda r: r["att"] == 1), ("not attempted", lambda r: r["att"] == 0)):
        v = [AR[r["m"]][Lm] for r in R if r["m"] in AR and AR[r["m"]]["run"] == "R2" and Lm in AR[r["m"]] and fn(r)]
        ok = [x for x in v if x["ok"] and x.get("0.5") is not None]
        tot = sum(x["0.5"] for x in ok) - 0.005 * sum(1 for x in v if not x["ok"])
        print(f"S4 replay R2 L{Lm} {lab:14}: launches {len(v)}, guarded fills {len(ok)}, total {tot:+.2f} SOL, mean per fill {S.mean(x['0.5'] for x in ok) if ok else 0:+.4f}")

#!/usr/bin/env python3
"""DV8 step 2g (read-only): reproduce the earlier DV8 number (haqq_strat s8 VALUE[timer 8], real landing, guard 1.05, no cap,
test day 10-26 23:15 -> 10-27 23:15 = +31.8 SOL) with s8's exact code path, then split its test P&L by mayhem tokens.
Out: dv8/c5.txt"""
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_gbdt as G
D = "/home/moiz/sniper-data/haqq_strat"; W0 = 1793038500; W1 = W0 + 86400
Z = np.load(f"{D}/uni.npz"); X = Z["X"].astype(np.float64); O = Z["O"].astype(np.float64); M = Z["M"]; LS = list(Z["LS"]); HS = list(Z["HS"])
ids = json.load(open("/home/moiz/sniper-data/haqq_model/tab/ids.json")); CR = json.load(open("/home/moiz/sniper-data/haqq_model/tab/creates.json"))
may = np.array([bool(CR.get(ids[int(m)], {}).get("mayhem")) for m in M["mint"]])
bt = M["bt"].astype(np.int64); tr = bt < W0 - 86400; va = (bt >= W0 - 86400) & (bt < W0); te = (bt >= W0) & (bt < W1)
li = LS.index("real"); col = 2 + 2 * HS.index(8)
E = G.edges_of(X, np.flatnonzero(tr)); B = G.binize(X, E)
tri = np.flatnonzero(tr); tri = tri[np.argsort(bt[tri])]; cut = int(0.8 * len(tri))
y = O[:, li, col].copy(); pr = O[:, li, 0]
y = np.where(np.isfinite(y) & np.isfinite(pr) & (pr <= 1.10), y, np.nan); ok = np.isfinite(y)
f_ = tri[:cut][ok[tri[:cut]]]; v_ = tri[cut:][ok[tri[cut:]]]
Mv = G.fit(B, np.clip(np.nan_to_num(y), -0.2, 0.2), f_, v_, loss="l2", rounds=600, lr=0.05, depth=4, min_n=300, lam=10.0, sub=0.8, fsub=0.8, seed=2, patience=60)
s = G.predict(Mv, B)
def pnl(mask):
    v = O[:, li, col]; okk = mask & np.isfinite(v) & np.isfinite(pr); fill = okk & (pr <= 1.05)
    r = np.full(len(v), np.nan); r[fill] = v[fill] - 0.00151 - 0.00160; r[okk & ~fill] = -0.00051
    return r
best = max((np.nansum(pnl((s >= th) & va)), th) for th in np.quantile(s[va], (0.5, 0.7, 0.8, 0.9, 0.95, 0.97, 0.98, 0.99, 0.995)))
th = best[1]; r = pnl((s >= th) & te)
L = [f"# earlier DV8 reproduced: VAL best {best[0]:+.2f} at th {th:.4f}; TEST {np.nansum(r):+.2f} SOL on {np.isfinite(r).sum()} trades",
     f"- mayhem picks {int((np.isfinite(r) & may).sum())}: {np.nansum(r[may]):+.2f} SOL; normal picks {int((np.isfinite(r) & ~may).sum())}: {np.nansum(r[~may]):+.2f} SOL",
     f"- share of picks on mayhem {100 * (np.isfinite(r) & may).sum() / np.isfinite(r).sum():.0f}% vs {100 * may[te].mean():.0f}% of all test candidates"]
print("\n".join(L)); open("/home/moiz/sniper-data/dv8/c5.txt", "w").write("\n".join(L) + "\n")

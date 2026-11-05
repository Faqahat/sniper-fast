#!/usr/bin/env python3
"""H1 formal test. Leader list = wallets whose trades (while 9pQQ flat) convert into its buy (immediate trigger, <=1 slot) at >= TH
with >= 20 trades on 10-28+10-30 combined (same for sells while it holds). On 10-31 / 11-02: recall = share of its buys/sells whose
trigger is a leader; precision = share of leader trades followed by its trade; lift = precision / base.  Also: stability of per-wallet
conversion (rank corr. train vs 10-31 among wallets with >= 50 trades each).  -> h1_test.json"""
import json, numpy as np, xlib as X
def per_run(r):
    z = np.load(f"{X.XOUT}/h1_{r}.npz"); u = z["users"]
    d = {}
    for kind, den in (("tb", ("flat_b", "flat_s")), ("ts", ("hold_b", "hold_s"))):
        k = z[f"{kind}_b"] + z[f"{kind}_s"]; n = z[den[0]] + z[den[1]]
        d[kind] = (u, k, n)
    return d
D = {r: per_run(r) for r in X.RUNS}
out = {}
for kind in ("tb", "ts"):
    agg = {}
    for r in X.RUNS[:2]:
        u, k, n = D[r][kind]; sel = n > 0
        for a, b, c in zip(u[sel].tolist(), k[sel].tolist(), n[sel].tolist()):
            x = agg.setdefault(a, [0, 0]); x[0] += b; x[1] += c
    base_tr = sum(v[0] for v in agg.values()) / sum(v[1] for v in agg.values())
    o = {"base_train": base_tr}
    for TH in (0.02, 0.05, 0.1):
        L_ = {a for a, (b, c) in agg.items() if c >= 20 and b / c >= TH}
        row = {"leaders": len(L_)}
        for r in X.RUNS[2:]:
            u, k, n = D[r][kind]; m = np.isin(u, list(L_))
            row[X.DAY[r]] = dict(recall=round(float(k[m].sum() / k.sum()), 4), precision=round(float(k[m].sum() / max(1, n[m].sum())), 4),
                                 base=round(float(k.sum() / n.sum()), 4))
        o[f"conv>={TH}"] = row
    # stability of per-wallet conversion
    u, k, n = D[X.RUNS[2]][kind]; mp = {a: (b, c) for a, b, c in zip(u.tolist(), k.tolist(), n.tolist()) if c >= 50}
    common = [a for a, (b, c) in agg.items() if c >= 50 and a in mp]
    x = np.array([agg[a][0] / agg[a][1] for a in common]); y = np.array([mp[a][0] / mp[a][1] for a in common])
    rk = lambda v: np.argsort(np.argsort(v))
    o["wallets_both"] = len(common); o["spearman_train_vs_10_31"] = round(float(np.corrcoef(rk(x), rk(y))[0, 1]), 3)
    o["top10_train_conv"] = sorted([(a[:8], agg[a][0], agg[a][1], round(agg[a][0] / agg[a][1], 3)) for a in agg if agg[a][1] >= 100], key=lambda z: -z[3])[:10]
    out["buys" if kind == "tb" else "sells"] = o
print(json.dumps(out, indent=1)); json.dump(out, open("h1_test.json", "w"), indent=1)

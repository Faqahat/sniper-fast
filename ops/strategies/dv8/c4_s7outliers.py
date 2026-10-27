#!/usr/bin/env python3
"""DV8 step 2f (read-only): where the old 'buy every dump, K=1 = +70 SOL/day' (haqq_strat s8, test day 10-26 23:15 -> 10-27 23:15)
came from. Re-runs s8's K=1 greedy on haqq_strat/uni.npz (ALL, 'real' landing, timer 30, guard 1.05) and splits the gross P&L by
the mint's mayhem flag (create event) and by the top 1% of trades. Out: dv8/c4.txt"""
import json, numpy as np
Z = np.load("/home/moiz/sniper-data/haqq_strat/uni.npz"); O = Z["O"]; M = Z["M"]; LS = list(Z["LS"]); HS = list(Z["HS"])
ids = json.load(open("/home/moiz/sniper-data/haqq_model/tab/ids.json")); CR = json.load(open("/home/moiz/sniper-data/haqq_model/tab/creates.json"))
W0 = 1793038500; W1 = W0 + 86400
te = (M["bt"] >= W0) & (M["bt"] < W1)
v = O[:, LS.index("real"), 2 + 2 * HS.index(30)].astype(float); pr = O[:, LS.index("real"), 0].astype(float)
ok = te & np.isfinite(v) & np.isfinite(pr); fill = ok & (pr <= 1.05)
idx = np.flatnonzero(ok); idx = idx[np.argsort(M["cc"][idx])]
open_ = []; busy = {}; keep = np.zeros(len(v), bool)
for i in idx:
    t = M["cc"][i]; open_ = [x for x in open_ if x > t]; m = int(M["mint"][i])
    if len(open_) >= 1 or busy.get(m, -1) > t: continue
    keep[i] = True
    if fill[i]: open_.append(t + 30 * 212.0 + 300.0); busy[m] = t + 30 * 212.0 + 300.0
may = np.array([bool(CR.get(ids[int(m)], {}).get("mayhem")) for m in M["mint"]])
k = keep & fill
cost = k.sum() * (0.00151 + 0.00160) + (keep & ~fill).sum() * 0.00051
L = [f"# s8 'ALL, K=1, timer 30' on its test day: {k.sum()} fills, gross {v[k].sum():+.1f} SOL, after s8 costs {v[k].sum() - cost:+.1f} SOL",
     f"- mayhem-token fills {int((k & may).sum())}: gross {v[k & may].sum():+.1f} SOL (mean {1000 * v[k & may].mean():+.1f} mSOL, max {v[k & may].max():+.2f} SOL on 0.40)",
     f"- normal-token fills {int((k & ~may).sum())}: gross {v[k & ~may].sum():+.1f} SOL (mean {1000 * v[k & ~may].mean():+.2f} mSOL)",
     f"- top 1% of fills: {np.sort(v[k])[::-1][:int(0.01 * k.sum())].sum():+.1f} SOL, of which mayhem {int(may[k][np.argsort(-v[k])[:int(0.01 * k.sum())]].sum())} of {int(0.01 * k.sum())}"]
print("\n".join(L)); open("/home/moiz/sniper-data/dv8/c4.txt", "w").write("\n".join(L) + "\n")

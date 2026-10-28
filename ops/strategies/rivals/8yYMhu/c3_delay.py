#!/usr/bin/env python3
"""8yYMhu c3 (read-only, INFERRED replay): HIS trades executed later. For every lot: same token, same size, same exit moment as his real
sell, but the buy lands later: at his real position (model check), +73 txs, +150 txs (same slot if the slot is that long), first in the next
slot, next slot +150 txs (~ our reactive 60-90 ms). Curve path with his own trades removed; constant product; 1.25 % fee each way.
Also: the same with OUR exit (sell 1-2 slots after the buy, ~200 ms). Out: DATA/c3.txt"""
import sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, tlib as T
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); wid = T.uid()[X.W]
FEE = 0.0125
def paper(k_, V0, V1, SZ):
    tok = k_ / V0 - k_ / (V0 + SZ); T1 = k_ / V1
    if T1 - tok <= 0: return np.nan
    return ((k_ / (T1 - tok) - V1) * (1 - FEE) - SZ * (1 + FEE)) / 1e9
res = collections.defaultdict(list)
bym = collections.defaultdict(list)
for l in L: bym[l["mint"]].append(l)
for m, ls in bym.items():
    tr = T.trades(m)
    if tr is None: continue
    key = tr["slot"].astype(np.int64) * 4096 + tr["idx"].astype(np.int64); slot = tr["slot"].astype(np.int64)
    vs = tr["vsol"].astype(np.float64); vt = tr["vtok"].astype(np.float64); sol = tr["sol"].astype(np.float64)
    me = tr["user"] == wid; buy = tr["buy"] == 1
    vfree = vs - np.cumsum(np.where(me, np.where(buy, sol, -sol), 0.0))
    for l in ls:
        kb = l["s"] * 4096 + l["i"]; pb = int(np.searchsorted(key, kb)); ks = l["close_s"] * 4096 + l["close_i"]; ps = int(np.searchsorted(key, ks))
        if not (pb < len(tr) and key[pb] == kb and ps < len(tr) and key[ps] == ks): continue
        k_ = vs[pb] * vt[pb]; SZ = l["sol_curve"] * 1e9
        def at(kk):          # his-free curve state after the last trade with key <= kk
            j = int(np.searchsorted(key, kk, side="right")) - 1
            return vfree[j] if j >= 0 else vfree[0]
        e = dict(real=vfree[pb - 1] if pb else vs[pb] - sol[pb], d73=at(kb + 73), d150=at(kb + 150), ns=at(l["s"] * 4096 + 4095), ns150=at((l["s"] + 1) * 4096 + 150))
        V1 = vfree[ps - 1]
        x1 = at((l["s"] + 1) * 4096 + 4095); x2 = at((l["s"] + 2) * 4096 + 4095)
        for nm, V0 in e.items():
            res[("his exit", nm)].append(paper(k_, V0, V1, SZ))
            res[("exit +1 slot", nm)].append(paper(k_, V0, x1, SZ))
            res[("exit +2 slots", nm)].append(paper(k_, V0, x2, SZ))
        res["realized_gross"].append(l["gross"]); res["realized_net"].append(l["pnl_cash"])
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
n = len(res["realized_net"]); days = 3.6
P(f"his lots replayed {n}; realized curve result after pump fees {np.sum(res['realized_gross']):+.2f} SOL, realized NET {np.sum(res['realized_net']):+.2f}")
P("| exit \\ his buy lands at | his real position | +73 txs (~37 ms) | +150 txs (~75 ms) | first in next slot | next slot +150 txs (~our reactive) |")
P("|---|---|---|---|---|---|")
for ex in ("his exit", "exit +1 slot", "exit +2 slots"):
    P(f"| {ex} | " + " | ".join(f"{np.nansum(res[(ex, nm)]):+.1f} SOL ({1000*np.nanmean(res[(ex, nm)]):+.1f} mSOL/lot)" for nm in ("real", "d73", "d150", "ns", "ns150")) + " |")
P("(curve result after pump fees, before his tx fees/tips/failed-tx costs of ~1.4 mSOL per lot)")
open(f"{X.D}/c3.txt", "w").write("\n".join(out) + "\n")

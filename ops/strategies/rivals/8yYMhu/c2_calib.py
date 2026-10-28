#!/usr/bin/env python3
"""8yYMhu c2 (read-only): calibration of the paper trade model on HIS OWN fills. For each landed lot:
 (a) model at his exact entry/exit with his size (curve path with his trades removed) vs his realized curve result after pump fees,
 (b) model e73-entry / +9-slot exit at 0.75 SOL (the selection study's paper unit) vs his realized result scaled to 0.75 SOL.
Out: DATA/c2.txt"""
import sys, os, pickle, collections
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X, tlib as T
L = pickle.load(open(f"{X.D}/lots.pkl", "rb")); wid = T.uid()[X.W]
U = dict(np.load(f"{X.D}/uni2.npz"))
mints = T.names()[0]; mid = T.mid()
FEE = 0.0125
def paper(k_, V0, V1, SZ):
    tok = k_ / V0 - k_ / (V0 + SZ); T1 = k_ / V1
    if T1 - tok <= 0: return np.nan
    return ((k_ / (T1 - tok) - V1) * (1 - FEE) - SZ * (1 + FEE)) / 1e9
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
rows = []
bym = collections.defaultdict(list)
for l in L: bym[l["mint"]].append(l)
for m, ls in bym.items():
    tr = T.trades(m)
    if tr is None: continue
    key = tr["slot"].astype(np.int64) * 4096 + tr["idx"].astype(np.int64)
    vs = tr["vsol"].astype(np.float64); vt = tr["vtok"].astype(np.float64); sol = tr["sol"].astype(np.float64)
    me = tr["user"] == wid; buy = tr["buy"] == 1
    vfree = vs - np.cumsum(np.where(me, np.where(buy, sol, -sol), 0.0))
    for l in ls:
        kb = l["s"] * 4096 + l["i"]; pb = int(np.searchsorted(key, kb)); ks = l["close_s"] * 4096 + l["close_i"]; ps = int(np.searchsorted(key, ks))
        if not (pb < len(tr) and key[pb] == kb and ps < len(tr) and key[ps] == ks): continue
        k_ = vs[pb] * vt[pb]
        V0 = vfree[pb - 1] if pb > 0 else vs[pb] - sol[pb]; V1 = vfree[ps - 1]
        exact = paper(k_, V0, V1, l["sol_curve"] * 1e9)
        rows.append((exact, l["gross"], l["pnl_cash"], l["cost"]))
a = np.array(rows)
P(f"lots {len(a)}: model at his exact entry/exit/size sum {np.nansum(a[:,0]):+.3f} SOL vs his realized curve result after pump fees {a[:,1].sum():+.3f} (diff {np.nansum(a[:,0])-a[:,1].sum():+.3f}); "
  f"per-lot |diff| p50 {1000*np.nanmedian(np.abs(a[:,0]-a[:,1])):.3f} mSOL p95 {1000*np.nanpercentile(np.abs(a[:,0]-a[:,1]),95):.3f}")
fl = U["filled"] > 0
for e in ("e0", "e73", "e150", "ens", "en2"):
    if f"r_{e}_9" not in U: continue
    P(f"his FILLED dumps, paper 0.75 SOL entry {e:4} exit +6/+9 slots: mean {1000*np.nanmean(U[f'r_{e}_6'][fl]):+6.2f} / {1000*np.nanmean(U[f'r_{e}_9'][fl]):+6.2f} mSOL;"
      f" his realized net {1000*np.nanmean(U['his_pnl'][fl]):+6.2f} mSOL/lot (size ~0.76)")
open(f"{X.D}/c2.txt", "w").write("\n".join(out) + "\n")

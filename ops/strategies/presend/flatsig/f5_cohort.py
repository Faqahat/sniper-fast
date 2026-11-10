#!/usr/bin/env python3
"""FLATSIG step 5 [MEASURED, DEV-only fit]: a data-driven cohort of profitable dip-buying bots, chosen ONLY from chain rows with
block time < 11-01 12:00 PKT (the DEV cut), so it can be used causally on VAL/HOLDOUT.
Per wallet (DEV rows): closed (wallet, mint) positions (|net tokens| < 1% of the bought), their SOL P&L minus 1.25%/side pump fee,
dip share = share of its buys landing <= 2 slots after an outside sell >= 1 SOL on the same mint.
Cohort = >= 150 closed positions, net >= +1.5 SOL, mean >= +1 mSOL/position, dip share >= 0.35, not us.
Out: /home/it/sniper-data/flatsig/cohort.json {ids (u64 as str), rows: per-wallet stats}"""
import numpy as np, json, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import flib as L
D = L.D
z = np.load(f"{D}/chain.npz")
S, M, U, B, SOL, TOK, BT = z["slot"], z["mint"], z["user"], z["buy"], z["sol"].astype(float), z["tok"].astype(float), z["bt"]
n = len(S)
gstart = np.r_[0, np.nonzero(M[1:] != M[:-1])[0] + 1]
gid = np.zeros(n, np.int64); gid[gstart[1:]] = 1; gid = np.cumsum(gid)
big = (B == 0) & (SOL >= 1e9)
OFF = np.int64(1) << 34
v = gid * OFF + np.where(big, S, 0)
acc = np.maximum.accumulate(v)
lastbig = np.r_[0, (acc - gid * OFF)[:-1]]
lastbig[gstart] = 0                                     # no carry into the next mint
dipbuy = (B == 1) & (lastbig > 0) & (S - lastbig <= 2)
dev = BT < L.CUT / 1e9
# per (user, mint) on DEV rows
sel = dev & (SOL > 0)
uu = U[sel]; mm = M[sel]; bb = B[sel]; ss = SOL[sel]; tt = TOK[sel]; db = dipbuy[sel]
key = np.stack([uu, mm], 1)
ukey, inv = np.unique(key, axis=0, return_inverse=True)
inv = inv.ravel()
bsol = np.bincount(inv, weights=np.where(bb == 1, ss, 0)); ssol = np.bincount(inv, weights=np.where(bb == 0, ss, 0))
btok = np.bincount(inv, weights=np.where(bb == 1, tt, 0)); stok = np.bincount(inv, weights=np.where(bb == 0, tt, 0))
nbuy = np.bincount(inv, weights=(bb == 1)); ndip = np.bincount(inv, weights=db.astype(float))
closed = (btok > 0) & (np.abs(btok - stok) <= 0.01 * btok)
pnl = ssol - bsol - 0.0125 * (ssol + bsol)
# per user
wu, winv = np.unique(ukey[:, 0], return_inverse=True)
winv = winv.ravel()
ncl = np.bincount(winv, weights=closed.astype(float))
npos = np.bincount(winv)
net = np.bincount(winv, weights=np.where(closed, pnl, 0))
vol = np.bincount(winv, weights=np.where(closed, bsol, 0))
dsh = np.bincount(winv, weights=ndip) / np.maximum(np.bincount(winv, weights=nbuy), 1)
ours = np.isin(wu, np.array(sorted(L.OURS64), dtype=np.uint64))
mean = net / np.maximum(ncl, 1)
cond = (ncl >= 150) & (net >= 1.5e9) & (mean >= 1e6) & (dsh >= 0.35) & ~ours
idx = np.nonzero(cond)[0]
rows = []
for i in idx[np.argsort(-net[idx])]:
    rows.append({"id": str(int(wu[i])), "name": L.NAMED64.get(int(wu[i]), ""), "closed": int(ncl[i]), "net": round(net[i] / 1e9, 2),
                 "mean_msol": round(mean[i] / 1e6, 2), "dip_share": round(float(dsh[i]), 3), "avg_buy": round(vol[i] / max(ncl[i], 1) / 1e9, 3)})
json.dump({"ids": [r["id"] for r in rows], "rows": rows, "rule": "DEV rows only; closed>=150, net>=1.5 SOL, mean>=1 mSOL, dip share>=0.35"},
          open(f"{D}/cohort.json", "w"), indent=1)
print("cohort", len(rows))
for r in rows[:40]: print(r)
# named wallets' DEV stats for reference
for k, nm in sorted(L.NAMED64.items(), key=lambda x: x[1]):
    i = np.searchsorted(wu, np.uint64(k))
    if i < len(wu) and wu[i] == k:
        print("NAMED", nm, int(ncl[i]), round(net[i] / 1e9, 2), round(mean[i] / 1e6, 2), round(float(dsh[i]), 3))

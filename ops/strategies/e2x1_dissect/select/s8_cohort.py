#!/usr/bin/env python3
"""SELECT s8: how much of E2x1's result is made by wallets that COPY him?
Cohort C (chosen on TRAIN only = before the newest 6 h): wallets that bought within 2 slots after >= 100 of his buys AND did so on
>= 35 % of all mints they ever bought (i.e. most of what they buy is right after him). Then for every E2x1 buy:
  - cohort SOL bought / sold between his buy row and his first sell row (and in the first 2 slots)
  - counterfactual (INFERRED, constant-product): remove the cohort's net SOL flow between his buy and each of his sells;
    px scales with vsol^2 at fixed k, so px_cf = px * ((vsol - net_cohort_sol) / vsol)^2. Lot return without the cohort.
Also the copy lag (slots / block idx after his row)."""
import sys, collections, json, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"]); MN, US = names()
sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64); us = D["user"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9
mi = D["mint"]; bt = D["bt"].astype(np.int64); vs = D["vsol"] / 1e9; tk = D["tok"].astype(np.float64)
TCUT = int(bt.max()) - 6 * 3600
mine_b = np.flatnonzero((us == w) & bu)
fol = collections.Counter(); lags = collections.defaultdict(list)
for R in mine_b:
    if bt[R] >= TCUT: continue
    a, e = span(D, int(mi[R])); hi = a + int(np.searchsorted(sl[a:e], sl[R] + 2, side="right")); seen = set()
    for q in range(R + 1, hi):
        if bu[q] and us[q] != w and us[q] not in seen: seen.add(int(us[q])); fol[int(us[q])] += 1
cand = [u for u, n in fol.items() if n >= 100]
trn = bu & (bt < TCUT) & np.isin(us, cand)
tot = collections.Counter(u for u, m in set(zip(us[trn].tolist(), mi[trn].tolist())))
C = {u for u in cand if fol[u] / max(tot[u], 1) >= 0.35 and so[(us == u) & bu].sum() > 1.0}
print(f"cohort ({len(C)} wallets, train-chosen):")
for u in sorted(C, key=lambda u: -fol[u]): print(f"  {US[u]}  follows {fol[u]}  mints {tot[u]}  frac {fol[u]/tot[u]:.2f}  sol_total {so[(us==u)&bu].sum():.0f}")
isC = np.isin(us, list(C))
res = []
for m in np.unique(mi[mine_b]):
    a, e = span(D, int(m))
    if D["cr_slot"][m] < 0: continue
    my = np.flatnonzero(us[a:e] == w) + a
    sells = [q for q in my if not bu[q]]
    ts = tk[sells].sum(); ss = so[sells].sum(); tb = tk[[q for q in my if bu[q]]].sum()
    if tb <= 0: continue
    netC = np.cumsum(np.where(isC[a:e], np.where(bu[a:e], so[a:e], -so[a:e]), 0.0))   # running cohort net SOL in
    for R in [q for q in my if bu[q]]:
        r0 = R - a
        # cohort flow first 2 slots after his buy
        hi2 = a + int(np.searchsorted(sl[a:e], sl[R] + 2, side="right"))
        cb2 = so[R + 1:hi2][isC[R + 1:hi2] & bu[R + 1:hi2]].sum()
        ob2 = so[R + 1:hi2][~isC[R + 1:hi2] & bu[R + 1:hi2] & (us[R + 1:hi2] != w)].sum()
        firstC = [q for q in range(R + 1, hi2) if isC[q] and bu[q]]
        lag = (int(sl[firstC[0]] - sl[R]), int(ix[firstC[0]] - ix[R]) if sl[firstC[0]] == sl[R] else -1) if firstC else None
        # lot value with / without cohort, proportional to his sells after this buy
        later = [q for q in sells if q > R]
        if ts > 0:
            val = tk[R] * ss / max(ts, tb)
            val_cf = 0.0
            for q in sells:
                # px_cf/px = ((vsol - dC)/vsol)^2, dC = cohort net SOL between this buy and the sell (only if sell after buy)
                dC = netC[q - a] - netC[r0] if q > R else 0.0
                f = ((vs[q] - dC) / vs[q]) ** 2 if vs[q] > 0 else 1.0
                val_cf += so[q] * max(f, 0) * tk[R] / max(ts, tb)
        else: val = val_cf = 0.0
        res.append(dict(row=int(R), bt=int(bt[R]), sol=float(so[R]), pnl=float(val - so[R]), pnl_cf=float(val_cf - so[R]), cb2=float(cb2), ob2=float(ob2),
                        lag=lag, test=bool(bt[R] >= TCUT)))
pickle.dump(dict(res=res, C=[US[u] for u in C]), open(f"{OUT}/s8.pkl", "wb"))
A = {k: np.array([r[k] for r in res]) for k in ("sol", "pnl", "pnl_cf", "cb2", "ob2", "test")}
for nm, m in (("TRAIN part", ~A["test"]), ("TEST 6 h", A["test"])):
    print(f"{nm}: buys {m.sum()}  P&L {A['pnl'][m].sum():.1f} SOL ({100*A['pnl'][m].sum()/A['sol'][m].sum():.2f}%/SOL)  "
          f"without cohort {A['pnl_cf'][m].sum():.1f} SOL ({100*A['pnl_cf'][m].sum()/A['sol'][m].sum():.2f}%)  "
          f"cohort SOL in 2 slots: mean {A['cb2'][m].mean():.2f} (non-cohort {A['ob2'][m].mean():.2f}); share of buys with cohort follow {np.mean(A['cb2'][m]>0):.2f}")
L = [r["lag"] for r in res if r["lag"]]
print("first cohort buy lag slots:", collections.Counter(l[0] for l in L).most_common(4), " same-slot idx gap median", np.median([l[1] for l in L if l[0] == 0]))

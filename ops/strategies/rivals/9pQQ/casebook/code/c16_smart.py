#!/usr/bin/env python3
"""HB24 smart-money follow: trigger wallet's realized SOL P&L on the PREVIOUS run (sum of signer SOL deltas on curve trades) vs 9pQQ's take rate.
usage: c16_smart.py PREVRUN RUN"""
import sys, numpy as np
D = "/home/it/sniper-data/rivals/9pQQ/casebook"; LT = "/home/it/sniper-data/rivals/9pQQ/lanes"
prev, run = sys.argv[1], sys.argv[2]
z = np.load(f"{LT}/tape_{prev}.npz")
u = z["u"]; sol = z["sol"]; fl = z["fl"]
k = (fl & 1) == 1
pnl = np.bincount(u[k], weights=sol[k] / 1e9, minlength=len(z["users"])); cnt = np.bincount(u[k], minlength=len(z["users"]))
P = dict(zip(z["users"].tolist(), zip(pnl.tolist(), cnt.tolist())))
s = np.load(f"{D}/scale_{run}.npz"); a = np.load(f"{D}/scale_aug_{run}.npz")
users = s["users"]
pp = np.array([P.get(x, (np.nan, 0))[0] for x in users.tolist()]); pc = np.array([P.get(x, (np.nan, 0))[1] for x in users.tolist()])
own = s["own"]; hold = s["holding"]; age = s["age"]; ss = s["since_sell"]; seg = s["seg"]; tb = s["tb"]; uu = s["u"]
tok = np.zeros(seg.max() + 1, bool); tok[seg[own]] = True
E = (~own) & (~hold) & (age >= 8) & ((ss < 0) | (ss >= 2)) & tok[seg]
x = pp[uu[E]]; c = pc[uu[E]]; t = tb[E]; base = t.mean()
print(f"{run} (prev {prev}) eligible {E.sum()} base {100*base:.2f}%")
for name, m in [("unseen prev day", np.isnan(x)), ("seen, <20 trades", (~np.isnan(x)) & (c < 20)),
                ("prev pnl <= -5", (c >= 20) & (x <= -5)), ("-5..-1", (c >= 20) & (x > -5) & (x <= -1)), ("-1..+1", (c >= 20) & (x > -1) & (x < 1)),
                ("+1..+5", (c >= 20) & (x >= 1) & (x < 5)), ("+5..+20", (c >= 20) & (x >= 5) & (x < 20)), (">= +20", (c >= 20) & (x >= 20))]:
    if m.sum(): print(f"   {name:18s} share {100*m.mean():5.1f}%  take {100*t[m].mean():5.2f}%  lift {t[m].mean()/base:4.2f}  recall {100*t[m].sum()/t.sum():5.1f}%")

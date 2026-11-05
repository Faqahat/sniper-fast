#!/usr/bin/env python3
"""HS15: is the sell trigger a wallet that BOUGHT during 9pQQ's hold (a follower leaving) / the buy-trigger wallet / a pre-entry holder?"""
import sys, numpy as np
D = "/home/moiz/sniper-data/rivals/9pQQ/casebook"
for run in sys.argv[1:]:
    z = np.load(f"{D}/scale_{run}.npz"); a = np.load(f"{D}/scale_aug_{run}.npz")
    own = z["own"]; hold = z["holding"]; sb = z["since_buy"]; ts = z["ts"]; tb = z["tb"]; buy = z["buy"]; u = z["u"]; seg = z["seg"]; era = a["era"]; sob = a["since_ob"]
    N = len(own); cat = np.zeros(N, np.int8)  # 1 follower sells, 2 buy-trigger wallet sells, 3 other seller, 0 buy/not hold
    k = 0; idx = np.where(own & buy)[0]
    for b in idx:
        g = seg[b]; foll = set(); trig = set()
        j = b - 1
        while j >= 0 and seg[j] == g and own[j]: j -= 1
        if j >= 0 and seg[j] == g and tb[j]: trig.add(u[j])
        k = b + 1
        while k < N and seg[k] == g and not own[k]:
            if buy[k]: foll.add(u[k])
            else: cat[k] = 1 if u[k] in foll else (2 if u[k] in trig else 3)
            k += 1
    H = (~own) & hold & (sb >= 2) & (~buy)
    for e in (2, 3):
        He = H & (era == e)
        if He.sum() < 1000: continue
        t = ts[He]; c = cat[He]; base = t.mean()
        print(f"{run} V{e} outside sells in hold {He.sum()} base {100*base:.2f}%")
        for v, name in ((1, "seller bought during the hold (follower leaving)"), (2, "seller = its buy-trigger wallet"), (3, "other seller")):
            m = c == v
            if m.sum(): print(f"   {name:48s} share {100*m.mean():5.1f}% hazard {100*t[m].mean():5.2f}% lift {t[m].mean()/base:.2f} recall {100*t[m].sum()/t.sum():.1f}%")
        m = (c == 1) & (sob[He] >= 15); print(f"   follower leaving & sob>=15 share {100*m.mean():.1f}% hazard {100*t[m].mean():.2f}% lift {t[m].mean()/base:.2f}")

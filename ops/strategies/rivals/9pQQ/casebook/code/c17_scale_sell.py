#!/usr/bin/env python3
"""scale test of sell hypotheses: outside trades while 9pQQ holds (>=2 slots after its buy); hazard = P(this trade is its sell trigger). per era."""
import sys, numpy as np
D = "/home/moiz/sniper-data/rivals/9pQQ/casebook"
for run in sys.argv[1:]:
    z = np.load(f"{D}/scale_{run}.npz"); a = np.load(f"{D}/scale_aug_{run}.npz")
    own = z["own"]; hold = z["holding"]; sb = z["since_buy"]; ts = z["ts"]; buy = z["buy"]; size = z["size"]; ret = z["ret"]; utot = z["utot"]
    sob = a["since_ob"]; b3 = a["bsol3"]; s3 = a["ssol3"]; era = a["era"]
    H = (~own) & hold & (sb >= 2)
    C = {"outside SELL": ~buy, "outside BUY": buy, "sell & sob>=5": (~buy) & (sob >= 5), "sell & sob>=15": (~buy) & (sob >= 15), "sell & sob>=60": (~buy) & (sob >= 60),
         "any & sob>=15": sob >= 15, "buy burst b3>=2 & ret>0": (b3 >= 2) & (ret > 0), "b3>=2": b3 >= 2, "sell size>=1": (~buy) & (size >= 1), "sell size<0.05": (~buy) & (size < 0.05),
         "ret>=+20%": ret >= 20, "ret<=-20%": ret <= -20, "-5<ret<5": np.abs(ret) < 5, "since_buy<=20": sb <= 20, "since_buy>=300": sb >= 300,
         "trigger bot (utot>=1k)": utot >= 1000, "sell & bot": (~buy) & (utot >= 1000), "s3>=1 (sells 3 slots)": s3 >= 1}
    for e in (1, 2, 3):
        He = H & (era == e)
        if He.sum() < 1000: continue
        t = ts[He]; base = t.mean()
        print(f"== {run} V{e}: hold events {He.sum()}, sells {t.sum()}, base hazard {100*base:.2f}%")
        for k, c in C.items():
            c = c[He]
            if c.sum(): print(f"   {k:28s} share {100*c.mean():5.1f}%  hazard {100*t[c].mean():5.2f}%  lift {t[c].mean()/base:4.2f}  recall {100*t[c].sum()/t.sum():5.1f}%")

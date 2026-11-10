#!/usr/bin/env python3
"""APEX-FEES step 5: S2 UNSEEN SOL/day at 0.4 SOL, exit h2, vs buy cost per landed buy (mSOL), for position A and R1,
split by picks with / without non-bundle create-slot snipers. Uses a2_eval.score (cost mode b<c>; revert = min(0.3c, 1 mSOL)).
Out: fees/apex_cost.json"""
import sys, json, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/apex2")
import a2_eval as E
L = E.load(); bt = np.array([r[2] for r in L])
cb, cs_, _, _ = E.costs(L)
sel = E.crep(L, "same")["A"]; U = sel & (bt >= E.UNSEEN)
hrs = sum((min(b, bt.max()) - max(a, bt.min())) / 3600 for nm, a, b in E.WIN if a >= E.UNSEEN and ((bt >= a) & (bt < b)).any())
per = 24 / hrs
ncs = np.array([r[5]["ncs"] if U[k] else -1 for k, r in enumerate(L)])
out = {"hours": hrs, "sell_cost": cs_, "rows": []}
for c in (0, 2, 3, 5, 8, 10, 12, 15, 20, 25, 30, 40, 50, 75, 100):
    for pos in ("A", "R1"):
        for nm, m in (("all", U), ("snipers", U & (ncs > 0)), ("nosnipers", U & (ncs == 0))):
            s = E.score(L, m, pos, 2, "h2", f"b{c}", cb, cs_)
            row = dict(c=c, pos=pos, sub=nm, n=int(m.sum()), perday=float(m.sum() * per),
                       sol=float(s[0.0].sum() * per), f20=float(s[0.2].sum() * per), f40=float(s[0.4].sum() * per),
                       wo5=float(np.sort(s[0.0])[::-1][int(np.ceil(len(s[0.0]) * 0.05)):].sum() * per))
            out["rows"].append(row)
            if nm == "all" or c in (3, 15): print(row, flush=True)
json.dump(out, open("/home/it/sniper-data/apex2/fees/apex_cost.json", "w"))

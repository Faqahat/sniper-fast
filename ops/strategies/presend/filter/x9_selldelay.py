#!/usr/bin/env python3
"""EXPLORATION (DEV ONLY, exact replay): what a slower TIME-EXIT sell costs. Time exits keep the live decision; the sell lands at the
median live delay + EXTRA ms (chain clock) instead of its live spot. TP / SL exits unchanged (live spots). Live size."""
import sys, json, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/real/r065")
import numpy as np
import core, positions as PO, pmath as PM
D = core.Data()
PS, RG, RF = pickle.load(open(f"{core.BASE}/pos_cal.pkl", "rb"))
delays = json.load(open(f"{core.BASE}/delays.json"))["median"]
for extra in (None, 0, 50, 100, 212, 424):
    tot = collections.defaultdict(float); n = 0
    for p in PS:
        if p.exit_why != "time-limit" or extra is None:
            tot[p.run] += p.realized / 1e9; continue
        n += 1
        W = core.walk(D, p.mint, p.pre, p.rows, p.spend, p.ours_buy["fbps"], p.ours_buy["cbps"], (10 ** 15, 0, 0), buy_slot=p.buy_pos[0])
        st = {k: (v, t, ap) for k, v, t, ap in W["states"]}
        sp = D.ck.inv((p.land_slot + 2) * core.SMS + delays["ps:time"] + extra)
        v, t = W["v_after"], W["t_after"]
        for k, row in enumerate(p.rows):
            if (row["s"], row["i"]) >= (sp[0], sp[1]): break
            if k in st: v, t = st[k][0], st[k][1]
        g = PM.sell_sol(v, t, W["q"]); sfb, scb = p.sell_tr["fbps"], p.sell_tr["cbps"]
        tot[p.run] += (g - PM.fees(g, sfb, scb) - p.spend - p.costs) / 1e9
    print(f"time-exit sell at median delay + {extra} ms ({n} time exits): r24 {tot['r24']:+.3f} r25 {tot['r25']:+.3f} sum {tot['r24'] + tot['r25']:+.3f}")

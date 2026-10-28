#!/usr/bin/env python3
"""Q3: event table for exit-rule fitting. Event = every outside (not his) trade during his hold, D0+D1 lots.
y = 1 when it is the last outside trade before his sell and his sell lands in the same or next slot.
Features after the event: side, SOL, price ratio vs entry r, vs peak dd, slots since entry, buy/sell SOL since entry,
slots since last outside buy, whether the trader is the sibling / trigger wallet / creator, whether the trader bought before in our hold.
Out: sniper-data/e2x1_dissect/exec/x5_ev.npz + printed hazard tables (x5.txt)"""
import sys, pickle, collections
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/exec")
import numpy as np, xlib as X
R = pickle.load(open(f"{X.X}/x4.pkl", "rb"))
E = collections.defaultdict(list)
for r in R:
    if not r["sells"] or r["swap"]: continue
    s0 = r["sells"][0]; v0 = r["v0"]; peak = v0; bsol = ssol = 0.0; last_buy_s = r["s"]; seen_buyers = set(); last_out = None
    for k, p in enumerate(r["path"]):
        if (p[0], p[1]) >= (s0["s"], s0["i"]): break
        if p[6]: continue
        if p[3]: bsol += p[4]; last_buy_s = p[0]; seen_buyers.add(p[2])
        else: ssol += p[4]
        peak = max(peak, p[5])
        last_out = len(E["lot"])
        for kk, vv in (("lot", r["lot"]), ("day", r["day"] == "D1"), ("bot", ["FRESH", "MINUTE", "OLD"].index(r["bot"])), ("buy", p[3]), ("sol", p[4]),
                       ("r", (p[5] / v0) ** 2), ("dd", (p[5] / peak) ** 2), ("rpk", (peak / v0) ** 2), ("ds", p[0] - r["s"]), ("bsol", bsol), ("ssol", ssol),
                       ("since_buy", p[0] - last_buy_s), ("sib", p[7]), ("trig", p[2] == r["trig_user"]), ("cre", p[2] == r["creator"]),
                       ("seller_bought_in_hold", (not p[3]) and p[2] in seen_buyers), ("slot", p[0]), ("cost", r["cost"]), ("v", p[5]), ("y", False)):
            E[kk].append(vv)
    if last_out is not None and s0["s"] - E["slot"][last_out] <= 1: E["y"][last_out] = True
E = {k: np.array(v) for k, v in E.items()}
np.savez(f"{X.X}/x5_ev.npz", **E)
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
d1 = E["day"]
P(f"events D1 {d1.sum()}  positives (his exit reacts to this trade within <=1 slot) {E['y'][d1].sum()} of {len(set(E['lot'][d1]))} lots")
def tab(name, mask, edges, key):
    P(f"-- P(exit | {name}) D1")
    x = E[key]
    for a, b in zip(edges[:-1], edges[1:]):
        m = mask & d1 & (x >= a) & (x < b)
        if m.sum() >= 20: P(f"   {key} [{a:g},{b:g}): n={m.sum():6} exit-rate {100*E['y'][m].mean():5.1f}%  share of exits {100*E['y'][m].sum()/E['y'][d1].sum():5.1f}%")
P(f"-- by side: sell events n={(d1&~E['buy']).sum()} exit-rate {100*E['y'][d1&~E['buy']].mean():.1f}% (share {100*E['y'][d1&~E['buy']].sum()/E['y'][d1].sum():.0f}%); buy events exit-rate {100*E['y'][d1&E['buy']].mean():.1f}%")
tab("sell size", ~E["buy"], [0, .05, .1, .2, .3, .5, 1, 2, 5, 1e9], "sol")
tab("buy size", E["buy"], [0, .05, .1, .2, .3, .5, 1, 2, 5, 1e9], "sol")
tab("price ratio vs entry, any trade", np.ones_like(d1), [0, .5, .7, .8, .9, .95, 1.0, 1.05, 1.1, 1.2, 1.3, 1.5, 2, 3, 1e9], "r")
tab("drawdown from peak, any trade", np.ones_like(d1), [0, .5, .7, .8, .9, .95, .99, 1.0001], "dd")
tab("slots since entry", np.ones_like(d1), [0, 2, 5, 10, 25, 50, 100, 200, 500, 1000, 3000, 9000, 1e9], "ds")
tab("slots since last outside buy", np.ones_like(d1), [0, 1, 2, 5, 10, 25, 50, 100, 1e9], "since_buy")
for k in ("sib", "trig", "cre", "seller_bought_in_hold"):
    m = d1 & E[k] & ~E["buy"]
    P(f"-- sell by {k}: n={m.sum()} exit-rate {100*E['y'][m].mean():.1f}%  share of exits {100*E['y'][m].sum()/E['y'][d1].sum():.1f}%")
open(f"{X.X}/x5.txt", "w").write("\n".join(out) + "\n")

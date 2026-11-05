#!/usr/bin/env python3
"""H1 copy-trader test. Per run: for every outside wallet count its trades while 9pQQ is flat (buy-conversion denominators) and
while 9pQQ holds (sell-conversion), and how often that trade is the immediate trigger (<=1 slot) of a 9pQQ buy / sell.
-> exact/h1_<run>.npz (per-wallet counts, by side). usage: h1_leaders.py"""
import numpy as np, collections
import xlib as X
for r in X.RUNS:
    t = X.load(r)
    oth = ~t.own
    U = len(t.users)
    def cnt(mask): return np.bincount(t.u[mask], minlength=U)
    res = {}
    for side, sm in (("b", t.tok > 0), ("s", t.tok < 0)):
        res[f"flat_{side}"] = cnt(oth & ~t.hold & sm)
        res[f"hold_{side}"] = cnt(oth & t.hold & sm)
        res[f"tb_{side}"] = cnt(oth & ~t.hold & sm & t.trig_b)
        res[f"ts_{side}"] = cnt(oth & t.hold & sm & t.trig_s)
    np.savez(f"{X.XOUT}/h1_{r}.npz", users=t.users, **res)
    nb = len(t.ob); ns = len(t.os)
    print(r, "buys", nb, "trig", (t.ob_trig >= 0).sum(), "sells", ns, "trig", (t.os_trig >= 0).sum())
    for kind, nall in (("tb", nb), ("ts", ns)):
        tot = res[f"{kind}_b"] + res[f"{kind}_s"]
        den = (res["flat_b"] + res["flat_s"]) if kind == "tb" else (res["hold_b"] + res["hold_s"])
        o = np.argsort(-tot)
        cum = np.cumsum(tot[o]) / max(1, nall)
        print(f"  {kind}: base conv {tot.sum()/den.sum():.4f}; trigger wallets {int((tot>0).sum())}; top1/10/100/1000 share",
              [round(float(cum[k-1]), 3) for k in (1, 10, 100, 1000)])
        for k in o[:12]:
            print(f"    {t.users[k][:8]} trig {tot[k]:5d} of {den[k]:7d} conv {tot[k]/max(1,den[k]):.3f} (b {res[kind+'_b'][k]}/{res['flat_b' if kind=='tb' else 'hold_b'][k]}, s {res[kind+'_s'][k]}/{res['flat_s' if kind=='tb' else 'hold_s'][k]})")
        # high-conversion wallets with enough volume
        conv = tot / np.maximum(den, 1)
        for th in (0.05, 0.1, 0.2, 0.4):
            sel = (conv >= th) & (den >= 20)
            print(f"   conv>={th} & n>=20: wallets {int(sel.sum())} explain {tot[sel].sum()/max(1,nall):.3f} of {kind}")

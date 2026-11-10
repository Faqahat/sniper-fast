#!/usr/bin/env python3
"""H1b: is the LEADER a class of transactions (router / bot program / tip pattern) instead of a wallet?
Per program-set class of the outside trade (and per 'extra program' = programs other than the standard pump/token/system/compute set):
count while flat, count as immediate trigger of its buy; conversion and lift vs base. Train runs -> pick classes; report on all runs.
usage: p3_route.py"""
import numpy as np, collections, json
import xlib as X
STD = {"11111111", "6EF8rrec", "ComputeB", "Tokenz", "TokenzQd", "TokenkegQ", "ATokenGP", "pfeeUxB6", "Tokenkeg", "MemoSq4g", "SysvarC1"}
res = {}
for r in X.RUNS:
    t = X.load(r); z = np.load(f"{X.XOUT}/tm_{r}.npz")
    ps = z["psets"]; pset = z["pset"]
    extra = np.array([",".join(sorted(p for p in s.split(",") if p and p not in STD)) or "-" for s in ps])
    exid_tab, exid = np.unique(extra, return_inverse=True)
    ex = np.where(pset >= 0, exid[np.maximum(pset, 0)], -1)
    flat = ~t.own & ~t.hold
    for side, sm in (("buy", t.tok > 0), ("sell", t.tok < 0)):
        base = flat & sm
        n = np.bincount(ex[base] + 1, minlength=len(exid_tab) + 1); k = np.bincount(ex[base & t.trig_b] + 1, minlength=len(exid_tab) + 1)
        tot = k.sum(); conv0 = tot / n.sum()
        rows = sorted([(int(k[j]), int(n[j]), (exid_tab[j - 1] if j else "?")) for j in range(len(n)) if n[j] >= 200], key=lambda x: -x[0])
        res.setdefault(r, {})[side] = dict(base=conv0, top=[(a, b, round(a / b / conv0, 2), c) for a, b, c in rows[:25]])
    tips = np.where(z["ntips"] >= 0, np.minimum(z["ntips"], 3), -1)
    n = np.bincount(tips[flat] + 1, minlength=5); k = np.bincount(tips[flat & t.trig_b] + 1, minlength=5)
    res[r]["ntips"] = [(j - 1, int(k[j]), int(n[j]), round(k[j] / max(n[j], 1) / (k.sum() / n.sum()), 2)) for j in range(5)]
    print("==", r)
    for side in ("buy", "sell"):
        print(" ", side, "base conv", round(res[r][side]["base"], 5))
        for a, b, l, c in res[r][side]["top"][:14]: print(f"    trig {a:5d} of {b:8d} lift {l:6.2f}  {c[:120]}")
    print("  ntips", res[r]["ntips"])
json.dump(res, open("p3_route.json", "w"), indent=1, default=str)

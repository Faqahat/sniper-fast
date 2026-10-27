#!/usr/bin/env python3
# Sensitivity: each R2-chosen config (ps6 best, chosen under ONE queue model) evaluated under EVERY queue model (k consistent
# with the row, cheap fees) on every day. Shows how much of a config's value depends on being first after the crossing trade.
import sys, json
import numpy as np
import ps5_lib as E, ps7_test as T
best = json.load(open(f"{E.C.OUT}/ps6_select.json"))["best"]
keys = sys.argv[1:] or ["T2|a", "T2|c", "T3|a", "T3|c", "T1t|c", "T1t|r4"]
res = {}
for day in ("R2", "R3", "R4", "R1"):
    D = E.load(day); h = D["hours"]
    print(f"\n=== {day} ({h:.1f} h)  SOL per 24 h [fills, net/fill] under queue rows a b c r20 r4 r1 (k = 20 20 20 20 4 1)")
    for key in keys:
        b = dict(best[key]); cells = []
        for dm in ("a", "b", "c", "r20", "r4", "r1"):
            b["dm"] = dm; o = T.one(D, b)
            cells.append(f"{dm} {o['pnl'] / h * 24:+6.2f} [{o['fill']:4d} {o['per_fill']:+.4f}]")
            res[f"{key}|{dm}|{day}"] = dict(pnl=o["pnl"], per24=o["pnl"] / h * 24, fill=o["fill"], per_fill=o["per_fill"])
        print(f"  {key:7s} " + " | ".join(cells), flush=True)
json.dump(res, open(f"{E.C.OUT}/ps7b_cross.json", "w"), indent=1)

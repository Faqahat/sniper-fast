#!/usr/bin/env python3
"""calibration: replay 9pQQ's own closed curve trips at its exact landing times with its own trades removed,
its size (0.7 / 0.48 SOL quote) and its cost 1.46 mSOL; compare to its realized net (+ rent credit 1.52 mSOL per ATA-creating buy)."""
import sys, json
import numpy as np
import nlib as L
for run in sys.argv[1:]:
    t = L.load(run); uid = t.uix[L.W9]
    tr = [x for x in json.load(open(f"{L.OUT}/trips_{run}.json"))["9pQQ"] if x.get("x") is not None and not x["may"] and x["nb"] == 1]
    by = {}
    for x in tr: by.setdefault(x["mint"], []).append(x)
    rp, rl, rent = 0.0, 0.0, 0
    for m, xs in by.items():
        M = L.Mint(t, t.mix[m], drop_uid=uid)
        tin = np.array([x["cc0"] for x in xs]) - 1e-6; tout = np.array([x["cc1"] for x in xs]) - 1e-6
        q = np.array([0.48e9 if x["spend"] < 0.6e9 else 0.7e9 for x in xs])
        for k in range(len(xs)):
            rp += L.trip(M, tin[k:k+1], tout[k:k+1], size=q[k], cost=1.46e6)[0]
        for x in xs:
            rl += x["net"]
            if x["spend"] - (0.7e9 if x["spend"] > 0.6e9 else 0.48e9) > 1.9e6: rent += 1
    print(run, "trips", len(tr), "realized", round(rl/1e9, 2), "+rent", round((rl + rent*1.52e6)/1e9, 2), "replay", round(rp/1e9, 2))

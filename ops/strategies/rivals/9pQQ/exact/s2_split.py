#!/usr/bin/env python3
"""Split a sim result: replica trips that coincide with a real 9pQQ buy (match) vs not; P&L at its speed (+45 ms, 0.7 SOL, 1.46 mSOL).
usage: s2_split.py SIMJSON RUN"""
import sys, json, numpy as np
import xlib as X, rlib9 as R
d = json.load(open(sys.argv[1])); run = sys.argv[2]; t = X.load(run); s0, bsz = R.blocksizes(run); CAP = d["CAP"]
cache = {}; out = {"match": [], "nomatch": []}
for x in d["trips"]:
    Mn = cache.get(x["m"]) or R.Mint(t, x["m"], s0, bsz, t.wid); cache[x["m"]] = Mn
    tin = Mn.CC[x["eb"] - t.mstart[x["m"]]] + 45
    tout = tin + CAP * 1000 if x["cap"] else Mn.CC[x["es"] - t.mstart[x["m"]]] + 45
    out["match" if x.get("match") else "nomatch"].append(R.trip(Mn, tin, tout, size=0.7e9, drop9=True, cost=1.46e6) / 1e9)
r = {k: dict(n=len(v), net=round(sum(v), 2), msol=round(1000 * np.mean(v), 2) if v else None, win=round(float(np.mean(np.array(v) > 0)), 3) if v else None) for k, v in out.items()}
print(json.dumps(r))

#!/usr/bin/env python3
"""Calibration of the sim P&L machinery: run 9pQQ's REAL trips (its trigger row -> its sell-trigger row) through the same paper
replay as sim.py (its speed +45 ms, 0.7 SOL, 1.46 mSOL; our speed +70 ms, 0.55 SOL, 4.5 mSOL; -20 % followers) and compare with its
real net.  Also its real trips at its EXACT times (calibration of the curve maths).  usage: c1_calib.py RUN"""
import sys, json, pickle
import numpy as np
import xlib as X, tlib9 as L, rlib9 as R
run = sys.argv[1]; t = X.load(run); s0, bsz = R.blocksizes(run); wid = t.wid
his = [x for x in pickle.load(open(f"{L.OUT}/trips_{run}.pkl", "rb")) if x.get("tape_ok") and x.get("net") is not None]
res = {k: [] for k in ("real", "exact_times", "his45", "our70", "our70_fol20")}
cache = {}
for x in his:
    mi = t.mint_ix[x["mint"]]; Mn = cache.get(mi) or R.Mint(t, mi, s0, bsz, wid); cache[mi] = Mn
    key = Mn.S * 10000 + Mn.I
    jb = int(np.searchsorted(key, x["bs"] * 10000 + x["bi"])); js = int(np.searchsorted(key, x["ss"] * 10000 + x["si"]))
    if js >= len(Mn.S) or Mn.U[js] != wid or Mn.U[jb] != wid: continue
    tb = jb - 1
    while tb >= 0 and Mn.U[tb] == wid: tb -= 1
    ts = js - 1
    while ts > jb and Mn.U[ts] == wid: ts -= 1
    ttb = Mn.CC[max(tb, 0)]; tts = Mn.CC[ts] if ts > jb else Mn.CC[js] - 45
    res["real"].append(x["net"] / 1e9)
    res["exact_times"].append(R.trip(Mn, Mn.CC[jb] - 1e-6, Mn.CC[js] - 1e-6, size=0.7e9, drop9=True, cost=1.46e6) / 1e9)
    res["his45"].append(R.trip(Mn, ttb + 45, tts + 45, size=0.7e9, drop9=True, cost=1.46e6) / 1e9)
    res["our70"].append(R.trip(Mn, ttb + 70, tts + 70, size=0.55e9, drop9=True, cost=4.5e6) / 1e9)
    res["our70_fol20"].append(R.trip(Mn, ttb + 70, tts + 70, size=0.55e9, drop9=True, cost=4.5e6, fol=0.2) / 1e9)
hrs = (t.bt.max() - t.bt.min()) / 3600
out = {k: dict(net=round(sum(v), 2), per_day=round(sum(v) / hrs * 24, 1)) for k, v in res.items()}
out["n"] = len(res["real"]); out["day"] = X.DAY[run]
print(json.dumps(out)); json.dump(out, open(f"c1_calib_{X.DAY[run]}.json", "w"))

#!/usr/bin/env python3
"""vs248 step 7 (read-only): hours per day with at least one trading engine of ours running (g2_engine run windows, probe-only runs
excluded), D2-D5, and our wallet P&L per running hour (MEASURED) -> INFERRED value of closing the run gaps at our current rate."""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
R = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/gap/g2_engine.pkl", "rb"))
W = pickle.load(open("/home/moiz/sniper-data/haqq_dissect/vs248/v2.pkl", "rb"))["wal"]
iv = sorted((X["start"], X["end"]) for X in R.values() if X["start"] and not X["probe_run"])
m = []
for a, b in iv:
    if m and a <= m[-1][1]: m[-1][1] = max(m[-1][1], b)
    else: m.append([a, b])
out = []
for d in (2, 3, 4, 5):
    s0 = L.DAY0 + d * 86400; s1 = s0 + 86400
    h = sum(max(0, min(b, s1) - max(a, s0)) for a, b in m) / 3600
    out.append((d, h, W.get(d, 0.0)))
    print(f"D{d}: engine running {h:.1f} h, wallet {W.get(d, 0):+.3f}, per running hour {W.get(d, 0) / max(h, 1e-9):+.4f}, gap {24 - h:.1f} h -> at that day's rate {W.get(d, 0) / max(h, 1e-9) * (24 - h):+.3f}")
H = sum(x[1] for x in out); Wt = sum(x[2] for x in out)
print(f"D2-D5: running {H / 4:.1f} h/day, wallet {Wt / 4:+.3f}/day, rate {Wt / H:+.4f}/h, gaps {24 - H / 4:.1f} h/day -> {Wt / H * (24 - H / 4):+.3f} SOL/day INFERRED")

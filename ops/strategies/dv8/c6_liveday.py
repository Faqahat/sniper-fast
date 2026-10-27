#!/usr/bin/env python3
"""DV8 step 2h (read-only): the replay pipeline on OUR actual regular fires, per day: live curve P&L (tape, MEASURED) vs modelled
(rank landing out-of-sample by server, exact followers) raw and calibrated (a x modelled + b per fire, c2 OLS). Tx costs excluded on
both sides. Out: dv8/c6.txt"""
import sys, pickle, collections, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
from g1_walkforward import calib_boot
(a, b), _ = calib_boot()
pf = pickle.load(open(f"{L.D}/c2_perfire.pkl", "rb"))
g = collections.defaultdict(list)
for p in pf: g[L.day_of(p["t"])].append(p)
out = ["# Our actual regular fires per day: live vs replay (curve P&L SOL, tx costs excluded)", "| day | fires | live fills | live | modelled (rank, OOS) | calibrated |", "|---|---|---|---|---|---|"]
for k in sorted(g):
    v = g[k]; m = sum(p["rank_oos"] for p in v)
    out.append(f"| {L.day_name(k)} | {len(v)} | {sum(p['fill'] for p in v)} | {sum(p['live'] for p in v):+.3f} | {m:+.3f} | {a * m + b * len(v):+.3f} |")
print("\n".join(out)); open(f"{L.D}/c6.txt", "w").write("\n".join(out) + "\n")

#!/usr/bin/env python3
# r09: LIVE result by our MEASURED landing position (block-position ms after the dump), next to the replay at that exact
# position and the replay at 35 / 50 ms on the same fires. Shows the speed effect directly in live data. MEASURED.
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R
P = json.load(open(f"{R.WORK}/pertrade.json"))
FAIL = 0.0005
def xp(o): return o["x_paper"]["pnl"] if o["x_st"] == 0 else (-FAIL if o["x_st"] == 1 else 0.0)
B = [(0, 20), (20, 35), (35, 50), (50, 75), (75, 100), (100, 150), (150, 10 ** 6)]
print(f"{'landing (ms)':14s} {'fires':>5s} {'live fills':>10s} {'LIVE SOL':>9s} {'per fire':>9s} | {'replay@ours':>11s} {'fills':>5s} | {'@35 ms':>7s} {'@50 ms':>7s} {'@0 ms':>7s}")
tot = np.zeros(6)
for lo, hi in B:
    rr = [o for o in P if o.get("L_meas") is not None and lo <= o["L_meas"] < hi]
    if not rr: continue
    lv = sum(o["chain_pnl"] for o in rr); nf = sum(o["live_fill"] for o in rr)
    xx = sum(xp(o) for o in rr); xf = sum(o["x_st"] == 0 for o in rr)
    a35 = sum(o["lat"]["35"]["pnl"] for o in rr); a50 = sum(o["lat"]["50"]["pnl"] for o in rr); a0 = sum(o["lat"]["0"]["pnl"] for o in rr)
    tot += [len(rr), lv, xx, a35, a50, a0]
    print(f"{lo:4d}-{hi if hi < 10**6 else 999:<4d} ms   {len(rr):5d} {nf:5d} ({100 * nf / len(rr):3.0f}%) {lv:+9.3f} {lv / len(rr):+9.4f} | {xx:+11.3f} {xf:5d} | {a35:+7.3f} {a50:+7.3f} {a0:+7.3f}")
print(f"{'ALL':14s} {int(tot[0]):5d} {'':10s} {tot[1]:+9.3f} {tot[1] / tot[0]:+9.4f} | {tot[2]:+11.3f} {'':5s} | {tot[3]:+7.3f} {tot[4]:+7.3f} {tot[5]:+7.3f}")
# fills only: live per-fill P&L by landing
print("\nFILLS only: live P&L per fill by landing (size-normalised to 0.35 SOL)")
for lo, hi in ((0, 35), (35, 75), (75, 10 ** 6)):
    rr = [o for o in P if o["live_fill"] and lo <= o["L_meas"] < hi]
    if rr:
        v = np.array([o["chain_pnl"] * 0.35 / o["size"] for o in rr])
        print(f"  {lo}-{hi if hi < 10**6 else 999} ms: n {len(rr)}, mean {v.mean():+.4f}, median {np.median(v):+.4f}, win {100 * np.mean(v > 0):.0f}%")

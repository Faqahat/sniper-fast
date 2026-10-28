#!/usr/bin/env python3
"""VERIFY v6b: time-clustered null for the forward test. G2's own in-sample per-hour ADDED (any:20:30:8:2 vs base, model, NOW costs,
draws of res_D<k>_dr3.pkl) on D1-D5 -> every contiguous block of N usable hours; share of blocks with ADDED <= the fresh result.
usage: v6b_blocks.py FRESH_ADDED N_HOURS"""
import sys, pickle, collections
import numpy as np
COST = 5120 + 200_000 + 605_000 + 1_200_000 + 5020; FAIL = 5120
R = "/home/moiz/sniper-data/haqq_dissect/rearm"; name = "any:20:30:8:2"
S = np.load("/home/moiz/sniper-data/dv8/tab/slots.npy"); sl = S["slot"].astype(np.int64); bt = S["bt"].astype(np.int64)
def hof(slot): return (int(bt[min(int(np.searchsorted(sl, slot)), len(sl) - 1)]) + 18000) // 3600 * 3600 - 18000
fresh = float(sys.argv[1]); N = float(sys.argv[2])
H = collections.defaultdict(float); nd = None
for d in range(1, 6):
    out = pickle.load(open(f"{R}/res_D{d}_dr3.pkl", "rb"))["out"]; nd = len(out["base"])
    for i in range(nd):
        for sgn, rows in ((-1, out["base"][i]), (1, out[name][i])):
            for r in rows:
                if not r[1]: continue
                v = -r[4] * FAIL + ((r[8][2]["base"][0] - COST) if r[3] else 0)
                H[hof(r[0][2])] += sgn * v / 1e9 / nd
hs = sorted(H); arr = np.array([H[h] for h in hs])
print(f"in-sample usable hours with windows: {len(hs)}; ADDED per hour mean {arr.mean():+.3f} SOL (sd {arr.std():.3f}); total {arr.sum():+.2f}")
n = int(np.floor(N)); fr = N - n
blocks = []
for i in range(len(hs) - n):
    if hs[i + n] - hs[i] != 3600 * n: continue          # contiguous only
    blocks.append(arr[i:i + n].sum() + fr * arr[i + n])
b = np.array(blocks)
print(f"{len(b)} contiguous {N:.2f}-hour blocks: mean {b.mean():+.3f}, 5/50/95% {np.percentile(b, [5, 50, 95]).round(3)}; share <= fresh {fresh:+.3f}: {np.mean(b <= fresh):.3f}; share <= 0: {np.mean(b <= 0):.3f}")

#!/usr/bin/env python3
"""VERIFY v6c: the same time-clustered block null for MY re-implementation (D2-D5, seed-averaged per hour).
usage: v6c_blocks_mine.py PKL FRESH N_HOURS"""
import sys, pickle, collections
import numpy as np
COST = 5120 + 200_000 + 605_000 + 1_200_000 + 5020
Z = pickle.load(open(sys.argv[1], "rb")); fresh = float(sys.argv[2]); N = float(sys.argv[3])
H = collections.defaultdict(float)
for r in Z["rows"]:
    h = (r["bt"] + 18000) // 3600 * 3600 - 18000
    v = -r["fees"] / 1e9
    if r["fill"] is not None and not r["base_has"]: v += (r["fill"]["ex"]["live"] - COST) / 1e9
    H[h] += v / Z["seeds"]
hs = sorted(H); arr = np.array([H[h] for h in hs]); n = int(N); fr = N - n
b = np.array([arr[i:i + n].sum() + fr * arr[i + n] for i in range(len(hs) - n) if hs[i + n] - hs[i] == 3600 * n])
print(f"{sys.argv[1].split('/')[-1]}: hours {len(hs)}, mean/h {arr.mean():+.3f}; {len(b)} blocks of {N} h: mean {b.mean():+.3f}, 5/50/95% {np.percentile(b, [5, 50, 95]).round(3)}; "
      f"share <= fresh {fresh:+.3f}: {np.mean(b <= fresh):.3f}; share <= 0: {np.mean(b <= 0):.3f}")

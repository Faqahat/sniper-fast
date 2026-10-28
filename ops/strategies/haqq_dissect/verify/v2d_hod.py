#!/usr/bin/env python3
"""VERIFY v2d: in-sample (D2-D5) hour-of-day profile (PKT) of the independent replay net, and the per-fill P&L spread
(to size the fresh-data test). usage: v2d_hod.py PKL [FRESHPKL]"""
import sys, pickle, collections
import numpy as np
COST = 5120 + 200_000 + 605_000 + 1_200_000 + 5020
Z = pickle.load(open(sys.argv[1], "rb")); ns = Z["seeds"]
H = collections.defaultdict(lambda: np.zeros(3)); pf = []
for r in Z["rows"]:
    h = ((r["bt"] + 18000) // 3600) % 24
    H[h][0] -= r["fees"] / 1e9 / ns
    f = r["fill"]
    if f is not None and not r["base_has"]:
        v = (f["ex"]["live"] - COST) / 1e9; H[h][0] += v / ns; H[h][1] += 1 / ns; pf.append(v)
print("hour PKT | net SOL over 4 days | added fills | per day")
for h in range(24): print(f"{h:02d} | {H[h][0]:+.2f} | {H[h][1]:.0f} | {H[h][0] / 4:+.3f}")
pf = np.array(pf) * 1e3
print(f"in-sample added fill P&L mSOL: n {len(pf)} mean {pf.mean():+.2f} sd {pf.std():.1f} median {np.median(pf):+.2f}; pctl 5/25/75/95 {np.percentile(pf, [5, 25, 75, 95]).round(1)}")
m = np.array([((r['bt'] + 18000) // 3600) % 24 in (1, 2, 3) for r in Z['rows'] if r['fill'] is not None and not r['base_has']])
print(f"in-sample 01-03 PKT fills: mean {pf[m].mean():+.2f} mSOL (n {m.sum()})")
if len(sys.argv) > 2:
    F = pickle.load(open(sys.argv[2], "rb"))
    q = np.array([(r["fill"]["ex"]["live"] - COST) / 1e6 for r in F["rows"] if r["fill"] is not None and not r["base_has"]])
    rng = np.random.default_rng(1)
    # how often does a random in-sample set of the same size have a mean <= the fresh mean?
    sims = np.array([pf[rng.integers(0, len(pf), len(q))].mean() for _ in range(20000)])
    print(f"fresh added fill P&L: n {len(q)} (all seeds) mean {q.mean():+.2f} mSOL; P(in-sample mean of {len(q)//F['seeds']} fills <= fresh) = "
          f"{np.mean(np.array([pf[rng.integers(0, len(pf), len(q)//F['seeds'])].mean() for _ in range(20000)]) <= q.mean()):.3f}")

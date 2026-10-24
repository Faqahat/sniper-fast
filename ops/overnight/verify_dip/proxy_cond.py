#!/usr/bin/env python3
"""verify_dip / proxy_cond: from the matched real-arrival anchors (vx_proxy), pairs (A, B) in the same launch with B AFTER A in
block order: given the PROXY gap, how often was the REAL gap below L (B really ahead of a buy sent L ms after A)?"""
import os, json, collections
HERE = os.path.dirname(os.path.abspath(__file__))
an = json.load(open(os.path.join(HERE, "out", "proxy_anchors_mine.json")))["anchors"]
by = collections.defaultdict(list)
for a in an: by[a[0]].append(a)
pairs = []
for m, v in by.items():
    v.sort(key=lambda a: (a[1], a[2]))            # block order
    for x in range(len(v)):
        for y in range(x + 1, len(v)):
            pg = v[y][4] - v[x][4]
            if pg > 300: break
            pairs.append((pg, v[y][3] - v[x][3]))
print(f"pairs in block order (B after A), proxy gap <= 300 ms: {len(pairs)}; real gap < 0 (B seen before A): {sum(1 for p in pairs if p[1] < 0) / len(pairs):.1%}")
for L in (20, 35, 50, 75):
    cells = []
    for lo, hi in ((0, 10), (10, 20), (20, 35), (35, 50), (50, 75), (75, 100), (100, 150), (150, 300)):
        v = [p for p in pairs if lo <= p[0] < hi]
        if v: cells.append(f"proxy [{lo},{hi}) n {len(v)}: {sum(1 for p in v if p[1] < L) / len(v):.0%}")
    print(f"L={L}: share with REAL gap < L -> " + " | ".join(cells))

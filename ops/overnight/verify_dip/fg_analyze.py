#!/usr/bin/env python3
"""verify_dip / fg_analyze: (1) PnL of the claim's selected trades vs the entry delay L in proxy units (fine grid);
(2) expected PnL at a REAL delay L when the proxy is off by d = proxy gap - real gap, with d drawn from the measured
pairs (vx_proxy anchors, real gap within +-7.5 ms of L): E_d[PnL(L + d)]; (3) competitor-reaction stress (fast
backrunners' / HkQ7hMjy's buys after our entry removed). TXC 0.0008 per tx.
usage: python3 -I -B fg_analyze.py"""
import os, json, collections, random, statistics
HERE = os.path.dirname(os.path.abspath(__file__)); O = os.path.join(HERE, "out")
TXC = 0.0016
an = json.load(open(os.path.join(O, "proxy_anchors_mine.json")))["anchors"]
by = collections.defaultdict(list)
for a in an: by[a[0]].append(a)
pairs = []
for m, v in by.items():
    v.sort(key=lambda a: a[3])
    for x in range(len(v)):
        for y in range(x + 1, len(v)):
            dr = v[y][3] - v[x][3]
            if dr > 320: break
            pairs.append((dr, v[y][4] - v[x][4]))
def dsample(Lr):
    return [p[1] - p[0] for p in pairs if abs(p[0] - Lr) <= 7.5]
RT = -0.5 * 0.0125 * 2 - TXC          # round trip with nobody else trading (missing grid points)
def total(fg, keys, Lp, idx=0):
    s = 0.0
    for k in keys:
        v = fg.get(k, {}).get(str(Lp))
        s += (v[idx] - TXC) if (v is not None and v[idx] is not None) else RT
    return s
for Lsel in ("20", "35", "50", "75"):
    fg = json.load(open(os.path.join(O, f"fg_L{Lsel}_dropfast.json")))
    keys = list(fg)
    print(f"\n== claim's L{Lsel} CV selection ({len(keys)} trades): PnL vs proxy delay (claim spec c | own-slot t | fast backrunners' later buys removed)")
    print("   " + " ".join(f"L{L}:{total(fg, keys, L):+.1f}/{total(fg, keys, L, 1):+.1f}/{total(fg, keys, L, 3):+.1f}" for L in (0, 10, 20, 25, 30, 35, 40, 45, 50, 60, 75, 100, 150)))
    rng = random.Random(3)
    for Lr in (20, 35, 50, 75):
        ds = dsample(Lr); ds.sort(); n = len(ds)
        # expectation over d: weight each grid point by the share of d mapping to it
        w = collections.Counter(min(300, max(0, int(round((Lr + d) / 5.0)) * 5)) for d in ds)
        ev = sum(c * total(fg, keys, L) for L, c in w.items()) / n
        evd = sum(c * total(fg, keys, L, 3) for L, c in w.items()) / n
        print(f"   real delay {Lr:3d} ms: d (proxy - real gap) n {n} p10 {ds[n // 10]:+.0f} median {ds[n // 2]:+.0f} p90 {ds[9 * n // 10]:+.0f} -> "
              f"E[PnL] {ev:+.2f} (claim at proxy L{Lr}: {total(fg, keys, Lr):+.2f}); with fast backrunners removed {evd:+.2f}")
fh = json.load(open(os.path.join(O, "fg_L35_drophk.json")))
print(f"\nL35 selection, HkQ7hMjy's buys after our entry removed: " + " ".join(f"L{L}:{total(fh, list(fh), L, 3):+.2f}" for L in (20, 35, 50, 75)))

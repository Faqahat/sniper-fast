#!/usr/bin/env python3
"""INSIDER step 2: census tables (paper, zero latency, no costs) per run and class; insider splits."""
import sys, pickle, collections, datetime
import numpy as np
D = "/home/it/sniper-data/insider"
def pkt(t): return datetime.datetime.utcfromtimestamp(t / 1e9 + 5 * 3600)
def summ(rows):
    f = [r for r in rows if r["paper"] is not None]
    v = np.array([r["paper"] for r in f]) if f else np.zeros(0)
    return {"n": len(rows), "fills": len(f), "sol": round(v.sum() / 1e3, 2), "per_fill": round(v.mean(), 1) if len(v) else None, "win": round((v > 0).mean() * 100) if len(v) else None,
            "big_loss": int((v < -50).sum())}
for run in sys.argv[1:]:
    R = pickle.load(open(f"{D}/cen_{run}.pkl", "rb"))
    ts = [r["t"] for r in R]
    h = (max(ts) - min(ts)) / 3.6e12
    print(f"== {run}: {len(R)} cands, {pkt(min(ts)):%m-%d %H:%M} -> {pkt(max(ts)):%m-%d %H:%M} PKT ({h:.2f} h)")
    by = collections.defaultdict(list)
    for r in R: by[r["class"]].append(r)
    for c, rows in sorted(by.items()): print(f"  {c:10s}", summ(rows), "live_arms", sum(r['live'] for r in rows))
    ins = by["insider"]
    print("  insider by pct_after:")
    for lo, hi in ((3, 6), (6, 8), (8, 10), (10, 15), (15, 101)):
        print(f"    {lo}-{hi}%", summ([r for r in ins if lo <= r["pct"] < hi]))
    print("  insider by age at crossing:")
    for lo, hi in ((0, 1), (1, 2), (2, 5), (5, 10**9)):
        print(f"    age {lo}-{hi}", summ([r for r in ins if lo <= (r["age"] or 0) < hi]))
    print("  insider by dump gap (FUTURE):")
    for lo, hi in ((0, 5), (5, 10), (10, 20), (20, 51)):
        print(f"    gap {lo}-{hi}", summ([r for r in ins if r["gap"] is not None and lo <= r["gap"] < hi]))
    print("  insider >=10% & age 0:", summ([r for r in ins if r["pct"] >= 10 and r["age"] == 0]))

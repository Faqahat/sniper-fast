#!/usr/bin/env python3
"""SL-REDFLAGS s5: candidate flags, per run, FIT vs VAL, w/o top 5, and ADDED value beyond QA/G1/G3/G4."""
import sys, collections
from slib import rows, g, mark_prior
R = rows(); mark_prior(R)
RK = ["r37", "r38", "r39", "r40", "r41", "r42a", "r42b", "r43", "r44", "r45", "r46", "r47", "r48", "r49"]
HRS = {"FIT": 74.35 + 20.61, "VAL": None}
import json
FL = {
 "A whale_n>=10": lambda d: d["kind"] == "t2" and g(d, "whale_n", -1) >= 10,
 "B whale_n<=1": lambda d: d["kind"] == "t2" and 0 <= g(d, "whale_n", -1) <= 1,
 "C n_oth6>=2": lambda d: g(d, "n_oth6") >= 2,
 "D max_oth>=12": lambda d: g(d, "max_oth") >= 12,
 "E sum_oth>=30": lambda d: g(d, "sum_oth") >= 30,
 "F age>=300&n120<=3": lambda d: g(d, "age") >= 300 and g(d, "n120", 99) <= 3,
 "G co_whale>=10": lambda d: g(d, "co_whale") >= 10,
}
if len(sys.argv) > 1: FL = {k: v for k, v in FL.items() if k[0] in sys.argv[1]}
def stat(xs):
    n = len(xs); p = sum(d["pnl"] for d in xs); s = sorted((d["pnl"] for d in xs))
    w5 = -(p - sum(s[:5])) if n else 0.0
    return n, sum(d["sl"] for d in xs), sum(d["pnl"] > 0 for d in xs), sum(d["pnl"] for d in xs if d["pnl"] > 0), -p, w5
for name, fn in FL.items():
    print(f"== {name}")
    for lab, sel in (("all", lambda d: True), ("ADDED", lambda d: d["prior"] is None)):
        line = []
        for G in ("FIT", "VAL"):
            xs = [d for d in R if d["grp"] == G and fn(d) and sel(d)]
            n, sl, wn, wp, sv, w5 = stat(xs)
            line.append(f"{G} blk {n:4d} SL {sl:2d} win {wn:3d} (+{wp:.2f}) saved {sv:+.2f} w/o5 {w5:+.2f}")
        print(f"  {lab:5s} " + " | ".join(line))
    pr = []
    for rk in RK:
        xs = [d for d in R if d["rk"] == rk and fn(d) and d["prior"] is None]
        pr.append(f"{rk} {-sum(d['pnl'] for d in xs):+.2f}/{len(xs)}")
    print("  ADDED per run: " + " ".join(pr))

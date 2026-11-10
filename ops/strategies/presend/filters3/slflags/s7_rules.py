#!/usr/bin/env python3
"""SL-REDFLAGS s7: candidate T2 rules + neighbours; ADDED value (trades no existing guard QA/G1/G3/G4 blocks), per run, w/o top 5."""
import sys
from slib import rows, g, mark_prior
R = rows(); mark_prior(R)
RK = ["r39", "r40", "r41", "r42a", "r42b", "r43", "r44", "r45", "r46", "r47", "r48", "r49"]
def noth(d, thr):
    wa = d.get("whale")
    return sum(1 for h in d.get("holders") or [] if h["pct"] >= thr and not (wa and h["w"][:8] == wa[:8]))
T2 = lambda d: d["kind"] == "t2" and d.get("holders") is not None
RULES = {
 "n_oth6>=2": lambda d: T2(d) and noth(d, 6) >= 2,
 "n_oth5>=2": lambda d: T2(d) and noth(d, 5) >= 2,
 "n_oth7>=2": lambda d: T2(d) and noth(d, 7) >= 2,
 "n_oth8>=2": lambda d: T2(d) and noth(d, 8) >= 2,
 "n_oth6>=3": lambda d: T2(d) and noth(d, 6) >= 3,
 "n_oth4>=3": lambda d: T2(d) and noth(d, 4) >= 3,
 "sum_oth>=30": lambda d: T2(d) and g(d, "sum_oth") >= 30,
 "sum_oth>=25": lambda d: T2(d) and g(d, "sum_oth") >= 25,
 "max_oth>=11": lambda d: T2(d) and g(d, "max_oth") >= 11,
 "rise>=0.34": lambda d: d["kind"] == "t2" and g(d, "rise") >= 0.34,
 "n_oth6>=2|rearm": lambda d: d.get("holders") is not None and noth(d, 6) >= 2,
}
if len(sys.argv) > 1: RULES = {k: v for k, v in RULES.items() if k in sys.argv[1].split(",")}
def S(xs):
    p = sorted(d["pnl"] for d in xs); sv = -sum(p)
    return len(xs), sum(d["sl"] for d in xs), sum(x > 0 for x in p), sum(x for x in p if x > 0), sv, sv + sum(p[:5])
for k, fn in RULES.items():
    print(f"== {k}")
    for lab, sel in (("all", lambda d: True), ("ADDED", lambda d: d["prior"] is None)):
        out = []
        for G in ("FIT", "VAL"):
            n, sl, w, wp, sv, w5 = S([d for d in R if d["grp"] == G and fn(d) and sel(d)])
            nsl = sum(d["sl"] for d in R if d["grp"] == G and sel(d))
            out.append(f"{G} blk {n:3d} SL {sl:2d}/{nsl:2d} winners {w:3d} (+{wp:.2f}) saved {sv:+.2f} w/o5 {w5:+.2f}")
        print(f"  {lab:5s} " + " | ".join(out))
    print("  ADDED per run: " + " ".join(f"{rk} {-sum(d['pnl'] for d in R if d['rk']==rk and fn(d) and d['prior'] is None):+.2f}/{sum(1 for d in R if d['rk']==rk and fn(d) and d['prior'] is None)}" for rk in RK))

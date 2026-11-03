#!/usr/bin/env python3
"""INSIDER step 10: do the live T2 windows (the base replay, T2 armed as live) already trade the census insider dumps?
For each census insider paper fill (>= X%, age 0): is a T2 window of the base armed on the token when the insider dumps, and did it fill
on that dump (fill slot = dump slot or +1)? usage: in10_t2cover.py RUNDIR CENSUS.pkl X"""
import sys, pickle, glob, collections
rundir, cenp, X = sys.argv[1], sys.argv[2], float(sys.argv[3])
C = [r for r in pickle.load(open(cenp, "rb")) if r["class"] == "insider" and r["pct"] >= X and r["age"] == 0 and r["paper"] is not None]
fate = collections.defaultdict(lambda: [0, 0.0, 0.0]); nrep = 0
for f in sorted(glob.glob(f"{rundir}/BASE__*.pkl")):
    d = pickle.load(open(f, "rb")); nrep += 1
    t0, t1 = d["meta"]["t_start"], d["meta"]["t_end"]
    W = collections.defaultdict(list)
    for r in d["rows"]: W[r["mint"]].append(r)
    for c in C:
        if not (t0 <= c["t"] / 1e6 <= t1): continue
        ds = c["slot"] + c["gap"]; tdump = c["t"] / 1e6 + c["dms"]
        ws = sorted((r for r in W.get(c["mint"], []) if r["kind"] in ("t2", "rearm") and r["t_arm"] <= tdump), key=lambda r: r["t_arm"])
        if not ws: k = "no T2/R0 window armed before the dump"; cash = 0.0
        else:
            r = ws[-1]
            if r["filled"] and ds <= r["fs"] <= ds + 1: k = f"{r['kind']} window FILLED on this insider dump"
            elif r["filled"] and r["fs"] < ds: k = f"{r['kind']} window filled earlier (another dump)"
            elif r["filled"]: k = f"{r['kind']} window filled later"
            else: k = f"{r['kind']} window armed before, no fill ({r['end_why']})"
            cash = r["cash"]
        fate[k][0] += 1; fate[k][1] += c["paper"] / 1e3; fate[k][2] += cash
print(f"census insider paper fills >= {X}% age 0, per rep (base replay = live T2 + R0):")
for k, (n, p, c) in sorted(fate.items(), key=lambda z: -z[1][1]):
    print(f"  {k:58s} {n / nrep:6.1f} fills  paper {p / nrep:+7.2f}  replay of that window {c / nrep:+7.3f}")

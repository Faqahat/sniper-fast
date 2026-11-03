#!/usr/bin/env python3
"""INSIDER step 9: the fate, in the replay, of every census insider paper fill (>= X%, age 0): where did the paper's SOL go?
usage: in9_fate.py RUNDIR CENSUS.pkl VARIANT X"""
import sys, pickle, glob, collections
rundir, cenp, v, X = sys.argv[1], sys.argv[2], sys.argv[3], float(sys.argv[4])
C = [r for r in pickle.load(open(cenp, "rb")) if r["class"] == "insider" and r["pct"] >= X and r["age"] == 0 and r["paper"] is not None]
fate = collections.defaultdict(lambda: [0, 0.0, 0.0]); nrep = 0
for f in sorted(glob.glob(f"{rundir}/{v}__*.pkl")):
    d = pickle.load(open(f, "rb")); nrep += 1
    t0, t1 = d["meta"]["t_start"], d["meta"]["t_end"]
    W = collections.defaultdict(list)
    for r in d["rows"]: W[r["mint"]].append(r)
    for c in C:
        if not (t0 <= c["t"] / 1e6 <= t1): continue
        ds = c["slot"] + c["gap"]
        ws = [r for r in W.get(c["mint"], []) if r["kind"] == "ins"]
        if not ws:
            other = [r for r in W.get(c["mint"], [])]
            k = "no insider window (skipped: armed / blocked / curve / launch)" if not other else "no insider window (token busy with T2/R0)"
            fate[k][0] += 1; fate[k][1] += c["paper"] / 1e3; continue
        r = ws[0]
        if r["filled"] and r["fs"] < ds: k = "we filled EARLIER on another dump (window used up)"
        elif r["filled"] and r["fs"] <= ds + 1: k = "we filled on THIS dump"
        elif r["filled"]: k = "we filled LATER (another dump)"
        elif r["end_why"] == "superseded": k = "not filled: T2 took the token"
        elif r["ins_u"] is not None and r["isell_slot"] is not None and r["isell_slot"] < ds: k = "not filled: stopped at an earlier sell"
        elif r["paused"] > 0 and r["sent"] == 0: k = "not filled: paused all window (one position)"
        else: k = f"not filled: {r['end_why']}" + (" (tries paused part)" if r["paused"] > 0 else "")
        fate[k][0] += 1; fate[k][1] += c["paper"] / 1e3; fate[k][2] += r["cash"]
print(f"{v}: census paper fills (>= {X}% age 0) per rep, paper SOL, replay SOL of that window")
for k, (n, p, c) in sorted(fate.items(), key=lambda z: -z[1][1]):
    print(f"  {k:62s} {n / nrep:6.1f} fills  paper {p / nrep:+7.2f}  replay {c / nrep:+7.3f}")

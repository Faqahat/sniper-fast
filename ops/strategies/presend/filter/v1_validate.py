#!/usr/bin/env python3
"""PRESEND FILTER: the frozen candidates (rules.py) on DEV and on VALIDATION (first look at validation outcomes: 10-27 ~07:55 PKT).
MEASURED windows, live size. FRA r22 window w51 (double fill, engine P&L wrong) is flagged: its realized is the engine's."""
import collections
import numpy as np
import sim, rules

DEV = ["ams:r24", "ams:r25"]
VP = ["fra:r23", "fra:r24"]
VS = ["ams:r19", "ams:r20", "fra:r21", "fra:r22"]
W = sim.load()


def grp(res, runs):
    d = collections.defaultdict(float)
    for r in runs:
        for k, v in res.get(r, {}).items(): d[k] += v
    return d


def line(name, d):
    d = collections.defaultdict(float, d)
    return (f"{name:10s} {d['before']:+.3f} -> {d['after']:+.3f} ({d['after'] - d['before']:+.3f}) fills {int(d['fills_kept'])}/{int(d['fills'])} "
            f"win_rm {int(d['win_rm'])} ({d['win_rm_sol']:+.3f}) lose_rm {int(d['lose_rm'])} ({d['lose_rm_sol']:+.3f}) notrade_rm {int(d['notrade_rm'])}/{int(d['notrade'])}")


print("BASE per run (live config, MEASURED: fills net incl. rent back - failed-try fees):")
r0 = sim.evaluate(W)
for r in DEV + VP + VS: print("  " + line(r, r0[r]))
for name, kind, arm, send in rules.CANDIDATES:
    res = sim.evaluate(W, arm=arm, send=send)
    print(f"\n=== {name} [{kind}]")
    for r in DEV + VP + VS: print("  " + line(r, res[r]))
    for g, runs in (("DEV", DEV), ("VAL-prim", VP), ("VAL-all", VP + VS)): print("  " + line(g, grp(res, runs)))

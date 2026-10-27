#!/usr/bin/env python3
"""PRESEND FILTER: the per-run table of the three final configs (MEASURED windows, live size)."""
import sim, rules
W = sim.load()
RUNS = ["ams:r24", "ams:r25", "fra:r23", "fra:r24", "ams:r19", "ams:r20", "fra:r21", "fra:r22"]
CF = [("C5a", None, rules.POSTHOC[0][3]), ("C5", None, rules.CANDIDATES[3][3]), ("QUIET", rules.quiet_arm, rules.c5_send)]
for name, arm, send in CF:
    res = sim.evaluate(W, arm=arm, send=send)
    print(f"| {name} | run | before | after | gain | fills kept | winners removed (SOL) | losers removed (SOL) | no-trade removed |")
    for g, runs in [(r, [r]) for r in RUNS] + [("DEV", RUNS[:2]), ("VAL-prim", RUNS[2:4]), ("VAL-all", RUNS[2:])]:
        d = {k: sum(res[r].get(k, 0) for r in runs) for k in ("before", "after", "fills", "fills_kept", "win_rm", "win_rm_sol", "lose_rm", "lose_rm_sol", "notrade_rm", "notrade")}
        print(f"| | {g} | {d['before']:+.3f} | {d['after']:+.3f} | {d['after'] - d['before']:+.3f} | {int(d['fills_kept'])}/{int(d['fills'])} | {int(d['win_rm'])} ({d['win_rm_sol']:+.3f}) | {int(d['lose_rm'])} ({d['lose_rm_sol']:+.3f}) | {int(d['notrade_rm'])}/{int(d['notrade'])} |")

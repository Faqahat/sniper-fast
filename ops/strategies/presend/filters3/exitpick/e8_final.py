#!/usr/bin/env python3
"""EXITPICK step 8: the final table. Policies (frozen): baseline fixed t125; P1 = the DEV-best one-feature rule (A+B);
P2 = depth-2 tree minleaf 80 (DEV); P3 = the 'small dump' lead (picked with VAL in view: dump_sol < 3.3 -> t1000) - NOT a clean test.
Per split: SOL, SOL/day, gain vs t125, w/o top-5 trades, followers -20%, resampled lag, extend share, bootstrap CI (hold)."""
import json
from elib import *
R = load()
def P1(r): return "t1500" if feat(r, "dump_drop") < 15.69 else "t125"
def P2(r):
    if feat(r, "dump_sol") < 3.805: return "s4" if feat(r, "b_buy_sol") < 0.76 else "t1500"
    return "t150" if feat(r, "ms_send_to_rx") < 114.5 else "t2000"
def P3(r): return "t1000" if feat(r, "dump_sol") < 3.3 else "t125"
POL = [("fixed t125", lambda r: "t125"), ("fixed t1000", lambda r: "t1000"), ("P1 DEV-best rule", P1), ("P2 tree d2", P2), ("P3 small-dump lead", P3)]
def row(rows, h, pol, var="y"):
    v = [y(r, pol(r), var) for r in rows]; b = [y(r, "t125", var) for r in rows]
    s = sorted(v); sb = sorted(b)
    return dict(sol=sum(v), day=sum(v) / h * 24, gain=sum(v) - sum(b), no5=sum(s[:-5]) - sum(sb[:-5]), ext=sum(1 for r in rows if pol(r) != "t125") / len(rows),
                ci=boot_ci([a - c for a, c in zip(v, b)]))
out = {}
for sp in ("dev", "val", "hold"):
    rows = [r for r in R if r["split"] == sp]; h = SPLIT_H[sp]
    print(f"\n== {sp.upper()} ({len(rows)} fills, {h:.1f} h)")
    print(f"  {'policy':<20} {'SOL':>7} {'/day':>6} {'vs125':>7} {'95%CI':>15} {'w/o top5 vs125':>14} {'fc20 vs125':>10} {'rs vs125':>8} {'changed':>7}")
    for name, pol in POL:
        a = row(rows, h, pol); f = row(rows, h, pol, "y_fc"); s = row(rows, h, pol, "y_rs")
        out[(sp, name)] = a
        print(f"  {name:<20} {a['sol']:+7.3f} {a['day']:+6.2f} {a['gain']:+7.3f} [{a['ci'][0]:+.2f},{a['ci'][1]:+.2f}] {a['no5']:+14.3f} {f['gain']:+10.3f} {s['gain']:+8.3f} {a['ext']:7.0%}")
print("\nPER RUN gain vs t125 (P1 / P2 / P3):")
for run in range(42, 51):
    rows = [r for r in R if r["run"] == run]
    print(f"  r{run} n{len(rows)} t125 {sum(y(r, 't125') for r in rows):+.3f}: " + " / ".join(f"{sum(y(r, p(r)) - y(r, 't125') for r in rows):+.3f}" for _, p in POL[2:]))
json.dump({f"{a}|{b}": v for (a, b), v in out.items()}, open(f"{O}/final.json", "w"))

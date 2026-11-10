#!/usr/bin/env python3
"""REPLAY4 step 4: every knob alone vs the live config, over r37 (recorder tape) and r38/r39/r40 (collector tape).
Per run: the paired delta (refused fills AND the fills the knob creates), at 0% and -20% followers, without the top 5
windows, and SOL/day. Out: stdout + /home/it/sniper-data/replay4/knobs4.txt"""
import sys, pickle, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/custom37")
import c37lib as L

RUNS = ["r37", "r38", "r39", "r40"]
G = pickle.load(open(f"{L.D}/grid4.pkl", "rb"))
H = {}
for run in RUNS:
    m = pickle.load(open(f"{L.D}/win_{run}.pkl", "rb"))["meta"]
    H[run] = (m["t1"] - m["t0"]) / 3.6e12
OUT = []


def p(s=""):
    print(s); OUT.append(s)


def deltas(run, name, cut=0.0):
    b = G["runs"][run]["res"]["base"][cut]; k = G["runs"][run]["res"][name][cut]
    return (k[:, 1] + k[:, 2]) - (b[:, 1] + b[:, 2])          # net = position P&L + failed-try fees


def summary(name):
    r = {}
    for run in RUNS:
        d = deltas(run, name)
        top = np.argsort(-np.abs(d))[:5]
        mask = np.ones(len(d), bool); mask[top] = False
        r[run] = (d.sum() / 1e9, d[mask].sum() / 1e9, deltas(run, name, 0.2).sum() / 1e9)
    tot = sum(r[x][0] for x in RUNS)
    nt5 = sum(r[x][1] for x in RUNS)
    c20 = sum(r[x][2] for x in RUNS)
    npos = sum(1 for x in RUNS if r[x][0] > 0)
    perday = tot / sum(H[x] for x in RUNS) * 24
    return r, tot, nt5, c20, npos, perday


names = [n for n in G["cfgs"] if n != "base"]
rows = [(n,) + summary(n) for n in names]
rows.sort(key=lambda x: -x[2])

p("REPLAY4: every knob alone vs the live config (paired try-level replay, REPS=%d)" % G["reps"])
p("runs: " + ", ".join(f"{x} {H[x]:.1f}h" for x in RUNS) + "   (r37 recorder tape; r38/r39/r40 collector tape, reserves 100% matched)")
p("delta = SOL vs base. no-top5 = without each run's 5 biggest-moving windows. -20% = followers cut.")
p()
p(f"{'knob':<22} {'r37':>8} {'r38':>8} {'r39':>8} {'r40':>8} | {'total':>8} {'no-top5':>8} {'-20%':>8} {'runs+':>5} {'SOL/day':>8}")
p("-" * 110)
for n, r, tot, nt5, c20, npos, perday in rows:
    p(f"{n:<22} {r['r37'][0]:>+8.3f} {r['r38'][0]:>+8.3f} {r['r39'][0]:>+8.3f} {r['r40'][0]:>+8.3f} | "
      f"{tot:>+8.3f} {nt5:>+8.3f} {c20:>+8.3f} {npos:>4}/4 {perday:>+8.2f}")
open("/home/it/sniper-data/replay4/knobs4.txt", "w").write("\n".join(OUT) + "\n")

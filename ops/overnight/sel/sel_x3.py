#!/usr/bin/env python3
# Exits for the IMITATION picks (local only): for model picks (score file + top share q of the last 20% of TRAIN, spacing 5),
# choose the TP / SL / time-limit exit on TRAIN hours (total at 35+50+75 ms), show the top exits and fixed holds on TEST,
# and the hold time our trades actually get under the chosen exit (slots from buy to the sell landing, at 50 ms).
# usage: python3 -I sel_x3.py score.npy Q [Q ...]     env: SELV=3
import sys, os, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S
sc = np.load(sys.argv[1]); E = len(S.GRID)
cut = np.quantile(S.T[S.TR], 0.8); VA = S.TR & (S.T >= cut) & (sc > -1e8)
def tot(mask, Ls=(35, 50, 75)): return np.array([sum(S.pnl(L, e)[mask].sum() for L in Ls) for e in range(E)])
for q in [float(x) for x in sys.argv[2:]]:
    thr = float(np.quantile(sc[VA], 1 - q)); pick = S.spaced(sc >= thr)
    t_tr = tot(pick & S.TR); t_te = tot(pick & S.TE)
    tpsl = [e for e, g in enumerate(S.GRID) if g[0] == "T" and (g[1] < 5 or g[2] < 5)]       # real TP and/or SL (not a pure timer)
    best = sorted(tpsl, key=lambda e: -t_tr[e])[:6]; fixed = [e for e, g in enumerate(S.GRID) if g[0] == "H"]
    print(f"\n=== top {q:.0%} (score >= {thr:+.3f}): TRAIN {int((pick & S.TR).sum())} picks, TEST {int((pick & S.TE).sum())} picks")
    print("  TP / SL / time-limit exits, best 6 by TRAIN (35+50+75):")
    for e in best:
        a = S.summary(pick, S.TR, e, S.HTR); b = S.summary(pick, S.TE, e, S.HTE)
        print(f"   {S.ename(e):62s} TRAIN 35 {a[35][0]:+6.2f} w{a[35][2]:.0%} 50 {a[50][0]:+6.2f} w{a[50][2]:.0%} 75 {a[75][0]:+6.2f} w{a[75][2]:.0%} | "
              f"TEST 35 {b[35][0]:+6.2f} w{b[35][2]:.0%} 50 {b[50][0]:+6.2f} w{b[50][2]:.0%} 75 {b[75][0]:+6.2f} w{b[75][2]:.0%}")
    print("  fixed holds (reference):")
    for e in fixed:
        a = S.summary(pick, S.TR, e, S.HTR); b = S.summary(pick, S.TE, e, S.HTE)
        print(f"   {S.ename(e):62s} TRAIN 35 {a[35][0]:+6.2f} w{a[35][2]:.0%} 50 {a[50][0]:+6.2f} w{a[50][2]:.0%} 75 {a[75][0]:+6.2f} w{a[75][2]:.0%} | "
              f"TEST 35 {b[35][0]:+6.2f} w{b[35][2]:.0%} 50 {b[50][0]:+6.2f} w{b[50][2]:.0%} 75 {b[75][0]:+6.2f} w{b[75][2]:.0%}")
    json.dump({"q": q, "thr": thr, "best_tpsl": [int(e) for e in best]}, open(f"/home/moiz/sniper/ops/overnight/sel/x3_q{q:g}.json", "w"))

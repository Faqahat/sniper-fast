#!/usr/bin/env python3
# GDM step 4b: ensembles. Each model's raw score is z-scored with the mean/sd of its VALIDATION scores; the ensemble is the
# mean z of ya10 + yb + yc (per feature set). Cut (top q% of validation) chosen on validation only, as in select_cut.py.
import sys, os, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
Z, M = common.load(); bt = Z["bt"]; run = Z["run"]; mints = M["mints"]; guard = Z["guard"] == 1
OC = common.outcomes(mints); f2p = np.load(f"{common.OUT}/f2.npz")["pick"]
TS = {(r["dir"], r["label"], r["fs"]): r for r in json.load(open(f"{common.OUT}/train_summary.json"))}
QS = (0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15)
def crit(sel, var="ps"): return np.mean([common.book(sel, OC, L, var, ex)[0] for L in ("30", "45") for ex in ("t8", "t10")])
def line(sel):
    c = []
    for L in ("30", "45", "75"):
        tot, nf, ng, v = common.book(sel, OC, L, "ps", "t10"); c.append(f"L{L} {tot:+6.2f} ({nf:3d}f/{ng:3d}g)")
    c.append(f"ns45 {common.book(sel, OC, '45', 'ns', 't10')[0]:+6.2f}")
    return " ".join(c)
ENS = {"E3": ("ya10", "yb", "yc"), "E2": ("ya10", "yc"), "E4": ("ya", "ya10", "yb", "yc")}
for d in ("fwd", "rev"):
    a, b = ("R1", "R2") if d == "fwd" else ("R2", "R1"); cut = TS[(d, "ya", "L")]["cut_bt"]; VA = (run == a) & (bt >= cut); TE = run == b
    for fs in ("L", "LM", "LMR"):
        for en, labs in ENS.items():
            zs = []
            for lab in labs:
                f = np.load(f"{common.OUT}/models/{d}_{lab}_{fs}_score.npy"); zs.append((f - f[VA].mean()) / f[VA].std())
            e = np.mean(zs, 0); np.save(f"{common.OUT}/models/{d}_{en}_{fs}_score.npy", e)
            vals = []
            for q in QS:
                thr = np.quantile(e[VA], 1 - q); vals.append((crit(VA & (e >= thr) & guard), q, thr))
            cv, q, thr = max(vals); stt = TE & (e >= thr) & guard
            print(f"{d} {en} {fs:4s} val crit by q: " + " ".join(f"{x[1]:.3f}:{x[0]:+.2f}" for x in vals) + f" | best q {q} -> TEST n {int(stt.sum()):4d} crit {crit(stt):+6.2f} | {line(stt)}")
            # fixed 3% for an apples-to-apples look at FINAL-2's pick rate
            thr3 = np.quantile(e[VA], 0.97); s3 = TE & (e >= thr3) & guard
            print(f"{' ' * 14}fixed q 0.03 -> TEST n {int(s3.sum()):4d} crit {crit(s3):+6.2f} | {line(s3)}")
    print(f"{d} FINAL-2 TEST n {int((TE & f2p).sum())} crit {crit(TE & f2p):+6.2f} | {line(TE & f2p)}")

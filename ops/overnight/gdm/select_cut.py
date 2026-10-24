#!/usr/bin/env python3
# GDM step 4a (read-only, offline): per model, choose the pick cut (top q% of VALIDATION scores) on validation only, using
# precomputed replay outcomes (core/allres_bt.json 45/75 ms, gdm/labels.json 30 ms); criterion = mean over 30/45 ms x
# t8/t10 of the total SOL with pro buys after us removed + follower slippage (ps), pro costs (+0.007 per fill, -0.003 per
# failed guarded buy). Then the SAME score threshold on the test period. FINAL-2 (offline, same rows) for reference.
import sys, os, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
Z, M = common.load(); bt = Z["bt"]; run = Z["run"]; mints = M["mints"]; guard = Z["guard"] == 1
OC = common.outcomes(mints); F2 = np.load(f"{common.OUT}/f2.npz"); f2p = F2["pick"]
TS = json.load(open(f"{common.OUT}/train_summary.json"))
QS = (0.01, 0.02, 0.03, 0.05, 0.075, 0.10, 0.15)
def crit(sel, var="ps"):
    return np.mean([common.book(sel, OC, L, var, ex)[0] for L in ("30", "45") for ex in ("t8", "t10")])
def line(sel):
    c = []
    for L in ("30", "45", "75"):
        tot, nf, ng, v = common.book(sel, OC, L, "ps", "t10"); c.append(f"L{L} {tot:+6.2f} ({nf:3d}f/{ng:3d}g)")
    tot, nf, ng, v = common.book(sel, OC, "45", "ns", "t10"); c.append(f"ns45 {tot:+6.2f}")
    return " ".join(c)
rows = []
for r in TS:
    d, lab, fs = r["dir"], r["label"], r["fs"]; f = np.load(f"{common.OUT}/models/{d}_{lab}_{fs}_score.npy")
    a, b = ("R1", "R2") if d == "fwd" else ("R2", "R1"); cut = r["cut_bt"]
    VA = (run == a) & (bt >= cut); TE = run == b
    best = None
    for q in QS:
        thr = np.quantile(f[VA], 1 - q); sv = VA & (f >= thr) & guard; stt = TE & (f >= thr) & guard
        cv = crit(sv); ct = crit(stt)
        rows.append(dict(dir=d, label=lab, fs=fs, q=q, thr=float(thr), val=cv, test=ct, n_val=int(sv.sum()), n_test=int(stt.sum())))
        if best is None or cv > best[1]: best = (q, cv, thr)
    q, cv, thr = best; stt = TE & (f >= thr) & guard
    print(f"{d} {lab:5s} {fs:4s} best q {q:5.3f} val {cv:+6.2f} (n {int((VA & (f >= thr) & guard).sum())}) | TEST n {int(stt.sum()):4d} crit {crit(stt):+6.2f} | {line(stt)}")
json.dump(rows, open(f"{common.OUT}/select_rows.json", "w"))
print()
for d in ("fwd", "rev"):
    a, b = ("R1", "R2") if d == "fwd" else ("R2", "R1"); TE = run == b
    cut = next(r["cut_bt"] for r in TS if r["dir"] == d); VA = (run == a) & (bt >= cut)
    print(f"{d}: FINAL-2 offline picks  VAL n {int((VA & f2p).sum()):4d} crit {crit(VA & f2p):+6.2f} | TEST n {int((TE & f2p).sum()):4d} crit {crit(TE & f2p):+6.2f} | {line(TE & f2p)}")
    print(f"{d}: all guarded launches   VAL n {int((VA & guard).sum()):4d} crit {crit(VA & guard):+7.2f} | TEST n {int((TE & guard).sum()):4d} crit {crit(TE & guard):+7.2f}")

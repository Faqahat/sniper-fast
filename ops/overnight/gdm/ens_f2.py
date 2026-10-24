#!/usr/bin/env python3
# GDM step 4c: ensembles with FINAL-2 (precomputed outcomes). union = FINAL-2 picks + our top q*; intersection = FINAL-2 picks
# whose GDM score is in our top k% of validation scores (k chosen on validation). Validation = fold2 slice of the training period.
import sys, json
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
Z, M = common.load(); bt = Z["bt"]; run = Z["run"]; mints = M["mints"]; guard = Z["guard"] == 1
OC = common.outcomes(mints); f2p = np.load(f"{common.OUT}/f2.npz")["pick"]
def crit(sel, vs=("ps", "ns")): return np.mean([common.book(sel, OC, L, v, ex)[0] for L in ("30", "45") for ex in ("t8", "t10") for v in vs])
def masks(d):
    a = "R1" if d == "fwd" else "R2"; idx = np.where(run == a)[0]; o = idx[np.argsort(bt[idx], kind="stable")]; c8 = bt[o[int(len(o) * 0.8)]]
    return (run == a) & (bt >= c8), run == ("R2" if d == "fwd" else "R1")
H = 1792663118
def show(nm, s, VA, TE):
    sv, st = s & VA, s & TE
    x = f"{nm:34s} VAL n {sv.sum():3d} {crit(sv):+5.2f} | TEST n {st.sum():4d} ps+ns {crit(st):+6.2f} ps {crit(st, ('ps',)):+6.2f} ns {crit(st, ('ns',)):+6.2f}"
    if TE[run == 'R1'].all() if False else (TE & (run == "R1")).any():
        a = st & (bt >= H); x += f" | R1>=14:58 n {a.sum():3d} {crit(a):+5.2f}"
    print(x)
for d, lab, fs, q in (("fwd", "yc", "LM", 0.02), ("rev", "E3", "LM", 0.075), ("fwd", "E3", "LM", 0.05), ("rev", "yc", "LM", 0.03), ("fwd", "ya", "LM", 0.03), ("rev", "ya", "LM", 0.03)):
    VA, TE = masks(d); f = np.load(f"{common.OUT}/models/cv_{d}_f2_{lab}_{fs}.npy")
    print(f"== {d} {lab} {fs} q {q}")
    thr = np.quantile(f[VA], 1 - q); mine = (f >= thr) & guard
    show("FINAL-2", f2p, VA, TE); show(f"GDM top {q:.1%}", mine, VA, TE); show("union", f2p | mine, VA, TE)
    for k in (0.1, 0.2, 0.3, 0.5):
        t = np.quantile(f[VA], 1 - k); show(f"FINAL-2 & GDM top {k:.0%}", f2p & (f >= t), VA, TE)
    t = np.quantile(f[VA], 0.5); show("FINAL-2 & GDM bottom 50% (control)", f2p & (f < t), VA, TE)

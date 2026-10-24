#!/usr/bin/env python3
# Frozen IMIT1 tiers priced with REAL follower limits (sel3r: core + sel/slip_args_sel.jsonl) vs imputed (sel3), aligned by
# (mint, age). TEST hours are the honest numbers; TRAIN shown for reference. Also writes TEST pick lists for the timing check.
import sys, json, gzip, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S
M = json.load(open("IMIT1.json")); sc = np.load("x4_score_imit1.npy")
EVr = [json.loads(l) for l in gzip.open("sel3r_events.jsonl.gz", "rt")]; XGr = np.load("sel3r_exits.npy", mmap_mode="r")
idx = {(r["m"], r["age"]): i for i, r in enumerate(EVr)}; amap = np.array([idx.get((r["m"], r["age"]), -1) for r in S.EV]); assert (amap >= 0).all()
FILLr = np.array([[str(L) in r["px"] and r["px"][str(L)] <= 1.02 for L in S.LATS] for r in EVr])
def pnl_r(L, e):
    j = S.LATS.index(L); v = np.nan_to_num(np.where(FILLr[:, j], np.asarray(XGr[:, j, e]), -0.0002)); return v[amap]
G = {tuple(g): i for i, g in enumerate(S.GRID)}
for tier in ("top2", "top4", "top8"):
    e = G[tuple(M["exits"][tier])]; pick = S.spaced(sc >= M["thresholds"][tier])
    print(f"{tier}: exit '{S.ename(e)}'")
    for part, nm, hrs in ((S.TR, "TRAIN", S.HTR), (S.TE, "TEST ", S.HTE)):
        m = pick & part; seg = []
        for L in S.LATS:
            j = S.LATS.index(L); a = S.pnl(L, e)[m]; b = pnl_r(L, e)[m]; fl = m & FILLr[amap, j]
            w = (pnl_r(L, e)[fl] > 0).mean() if fl.any() else 0
            seg.append(f"{L} ms imputed {a.sum():+6.2f} -> REAL limits {b.sum():+6.2f} (win {w:.0%}, {b.sum() / hrs * 24:+5.1f}/day)")
        print(f"   {nm} {int(m.sum())} picks | " + " | ".join(seg))
    if tier in ("top2", "top4"):
        with open(f"picks_imit1_{tier}_test.jsonl", "w") as f:
            for i in np.where(pick & S.TE)[0]: f.write(json.dumps({"m": S.EV[i]["m"], "age": S.EV[i]["age"]}) + "\n")

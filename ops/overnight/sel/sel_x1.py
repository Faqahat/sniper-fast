#!/usr/bin/env python3
# Selection study with TP / SL / time-limit exits (local only). TRAIN = before SPLIT (default 10-23 06:00 PKT), TEST = after.
#  A) which exit makes the most for us on THEIR picks (chosen on TRAIN, shown on TEST), vs fixed holds
#  B) GBDT score (numpy) trained on TRAIN to predict "we win at 50 ms" under exit A; top-q picks (q set on the last 20% of TRAIN);
#     spacing 5 slots per token
#  C) exit re-chosen on TRAIN for those picks; everything judged on TEST
# usage: python3 -I sel_x1.py            env: SPLIT, QS (comma list of top shares)
import sys, os, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S
import gbdt_np as G
E = len(S.GRID)
def totals(mask, Ls=(35, 50, 75)):
    return np.array([sum(S.pnl(L, e)[mask].sum() for L in Ls) for e in range(E)])
print(f"TRAIN {S.TR.sum()} dumps / {S.HTR:.1f} h | TEST {S.TE.sum()} dumps / {S.HTE:.1f} h | exits in grid {E}")
print("\nA) best exits for us on THEIR picks (chosen by TRAIN total at 35+50+75 ms):")
EREF = {}
for w in ("HkQ7hMjy", "DYXDDrZC", "haqqiUUX", "ANY"):
    tot = totals(S.LAB[w] & S.TR); top = np.argsort(-tot)[:4]; EREF[w] = int(top[0])
    print(f"  {w}: TRAIN picks {int((S.LAB[w] & S.TR).sum())}, TEST picks {int((S.LAB[w] & S.TE).sum())}")
    for e in list(top) + [S.GRID.index(("H", 4)), S.GRID.index(("H", 10))]:
        print(f"     {S.ename(e):58s} TRAIN {S.fmt(S.summary(S.LAB[w], S.TR, e, S.HTR))}")
        print(f"     {'':58s} TEST  {S.fmt(S.summary(S.LAB[w], S.TE, e, S.HTE))}")
e0 = EREF["ANY"]
print(f"\nB) GBDT under exit '{S.ename(e0)}' (target: win at 50 ms)")
tr_t = S.T[S.TR]; cut = np.quantile(tr_t, 0.8)
FIT = S.TR & (S.T < cut); VA = S.TR & (S.T >= cut)
y = ((S.pnl(50, e0) > 0) & S.FILL[:, 1]).astype(float)
Bm = G.binize(S.X, FIT); trees, f = G.fit(Bm, y, FIT, VA, rounds=400, lr=0.05, depth=3)
print(f"  trees {len(trees)} | AUC fit {G.auc(y[FIT], f[FIT]):.3f} val {G.auc(y[VA], f[VA]):.3f} TEST {G.auc(y[S.TE], f[S.TE]):.3f}")
acc = np.zeros(len(S.FEATS))
for t in trees: G.imp(t, acc)
print("  top features: " + ", ".join(f"{S.FEATS[j]} {acc[j] / acc.sum():.0%}" for j in np.argsort(-acc)[:12]))
np.save("/home/moiz/sniper/ops/overnight/sel/x1_score.npy", f)
for q in [float(x) for x in os.environ.get("QS", "0.003,0.006,0.01,0.02,0.03,0.05").split(",")]:
    thr = np.quantile(f[VA], 1 - q); pick = S.spaced(f >= thr)
    tot = totals(pick & S.TR); eb = int(np.argmax(tot))
    print(f"\n  top {q:.1%} (score >= {thr:.3f}) — exit A '{S.ename(e0)}':")
    print(f"     TRAIN {S.fmt(S.summary(pick, S.TR, e0, S.HTR))}\n     TEST  {S.fmt(S.summary(pick, S.TE, e0, S.HTE))}")
    print(f"   C) exit re-chosen on TRAIN for these picks: '{S.ename(eb)}'")
    print(f"     TRAIN {S.fmt(S.summary(pick, S.TR, eb, S.HTR))}\n     TEST  {S.fmt(S.summary(pick, S.TE, eb, S.HTE))}")
    tm = pick & S.TE
    print(f"     TEST overlap: {int((tm & S.LAB['ANY']).sum()) / max(int(tm.sum()), 1):.0%} of ours were also bought by the three; we caught "
          f"HkQ7 {int((tm & S.LAB['HkQ7hMjy']).sum()) / max(int((S.LAB['HkQ7hMjy'] & S.TE).sum()), 1):.0%}, DYX {int((tm & S.LAB['DYXDDrZC']).sum()) / max(int((S.LAB['DYXDDrZC'] & S.TE).sum()), 1):.0%}, "
          f"haq {int((tm & S.LAB['haqqiUUX']).sum()) / max(int((S.LAB['haqqiUUX'] & S.TE).sum()), 1):.0%} of theirs")

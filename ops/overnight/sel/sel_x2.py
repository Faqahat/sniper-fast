#!/usr/bin/env python3
# Selection study v3 (local only): watch envelope from the three wallets' TRAIN picks, then GBDT selection inside it with
# HkQ7-style exits (TP / SL / time limit, min hold), every choice made on TRAIN hours, judged on TEST hours.
#   envelope = ranges that hold ~90% of their TRAIN picks on a few dump-time facts (token age, price drop, last buy, dump size)
#   exits    = the best TP/SL/time-limit exit for us on their TRAIN picks, time limit <= 10 slots (2.1 s) as the bots hold ~1-2 s
#   targets  = (a) we win at 50 ms under that exit  (b) one of the three buys after the dump (imitation)  (c) both
#   picks    = top-q score inside the envelope, q set on the last 20% of TRAIN for >= 65% wins at 50 ms; spacing 5 slots
# env: SELV=3, SPLIT
import sys, os, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S
import gbdt_np as G
E = len(S.GRID)
def tot(mask, Ls=(35, 50, 75)): return np.array([sum(S.pnl(L, e)[mask].sum() for L in Ls) for e in range(E)])
# 1) envelope
K = {"age": ("<=", 0.95), "drop_pct": (">=", 0.05), "since_buy": ("<=", 0.95), "sell": (">=", 0.05)}
their = S.LAB["ANY"] & S.TR; env = np.ones(len(S.EV), bool); envcfg = []
for k, (op, q) in K.items():
    j = S.FEATS.index(k); v = float(np.quantile(S.X[their, j], q)); envcfg.append((k, op, round(v, 3)))
    env &= (S.X[:, j] >= v) if op == ">=" else (S.X[:, j] <= v)
print("watch envelope (from their TRAIN picks): " + " AND ".join(f"{k} {op} {v}" for k, op, v in envcfg))
for part, nm, hrs in ((S.TR, "TRAIN", S.HTR), (S.TE, "TEST", S.HTE)):
    print(f"  {nm}: dumps inside {int((env & part).sum()) / hrs:.0f}/h of {int(part.sum()) / hrs:.0f}/h ({(env & part).sum() / part.sum():.0%}); "
          f"their picks kept {int((env & S.LAB['ANY'] & part).sum()) / max(int((S.LAB['ANY'] & part).sum()), 1):.0%}; "
          f"tokens inside {len(set(S.M[env & part])) / hrs:.0f}/h vs their tokens {len(set(S.M[S.LAB['ANY'] & part])) / hrs:.0f}/h")
# 2) exit for us on their TRAIN picks, bot-like (time limit <= 10 slots, TP/SL family) and the fixed holds for reference
fam = [e for e, g in enumerate(S.GRID) if g[0] == "T" and g[3] <= 10]
t_any = tot(their); e_bot = max(fam, key=lambda e: t_any[e]); e_fix = S.GRID.index(("H", 4))
print(f"exit chosen on their TRAIN picks: '{S.ename(e_bot)}' (train total {t_any[e_bot]:+.2f}) | fixed 4 slots {t_any[e_fix]:+.2f} | "
      f"best fixed {S.ename(int(np.argmax([t_any[e] if S.GRID[e][0] == 'H' else -1e9 for e in range(E)])))}")
# 3) GBDT variants inside the envelope
cut = np.quantile(S.T[S.TR], 0.8); FIT = S.TR & (S.T < cut) & env; VA = S.TR & (S.T >= cut) & env
Bm = G.binize(S.X, FIT)
win50 = ((S.pnl(50, e_bot) > 0) & S.FILL[:, 1]).astype(float)
TGT = {"win_for_us": win50, "they_buy": S.LAB["ANY"].astype(float), "they_buy_and_we_win": (S.LAB["ANY"] & (win50 > 0)).astype(float)}
for name, y in TGT.items():
    trees, f = G.fit(Bm, y, FIT, VA, rounds=400, lr=0.05, depth=3)
    acc = np.zeros(len(S.FEATS))
    for t in trees: G.imp(t, acc)
    np.save(f"/home/moiz/sniper/ops/overnight/sel/x2_score_{name}.npy", np.where(env, f, -1e9))
    print(f"\n=== target {name}: trees {len(trees)}, AUC val {G.auc(y[VA], f[VA]):.3f} TEST {G.auc(y[S.TE & env], f[S.TE & env]):.3f} | top features: "
          + ", ".join(f"{S.FEATS[j]} {acc[j] / acc.sum():.0%}" for j in np.argsort(-acc)[:8]))
    for q in (0.01, 0.02, 0.04, 0.08, 0.15):
        thr = np.quantile(f[VA], 1 - q); pick = S.spaced(env & (f >= thr))
        va_w = S.summary(pick, VA, e_bot, 1.0)[50][2]
        for e, en in ((e_bot, "bot-like exit"), (e_fix, "fixed 4 slots")):
            te = S.summary(pick, S.TE, e, S.HTE); tr = S.summary(pick, S.TR, e, S.HTR)
            print(f"  top {q:4.0%} thr {thr:+.3f} [{en:13s}] val win50 {va_w:.0%} | TRAIN {tr['ph']:5.1f}/h 35 {tr[35][0]:+6.2f} w{tr[35][2]:.0%} 50 {tr[50][0]:+6.2f} w{tr[50][2]:.0%} "
                  f"75 {tr[75][0]:+6.2f} w{tr[75][2]:.0%} | TEST {te['ph']:5.1f}/h 35 {te[35][0]:+6.2f} w{te[35][2]:.0%} 50 {te[50][0]:+6.2f} w{te[50][2]:.0%} 75 {te[75][0]:+6.2f} w{te[75][2]:.0%}"
                  f" | test ours also theirs {int((pick & S.TE & S.LAB['ANY']).sum()) / max(int((pick & S.TE).sum()), 1):.0%}")

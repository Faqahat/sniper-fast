#!/usr/bin/env python3
# Score every event with a frozen selector JSON (IMIT1) exactly as live would: envelope, bin with the saved edges, sum trees.
# -> score npy aligned with sel_lib's events. Then per tier (top2/4/8 + its exit): TRAIN / TEST totals at 35/50/75 ms.
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S
import gbdt_np as G
M = json.load(open(sys.argv[1])); out = sys.argv[2]
assert M["features"] == S.FEATS
X = S.X; env = np.ones(len(S.EV), bool)
for k, op, v in M["envelope"]:
    j = S.FEATS.index(k); env &= (X[:, j] >= v) if op == ">=" else (X[:, j] <= v)
B = np.zeros(X.shape, np.int16)
for j, e in enumerate(M["edges"]):
    b = np.searchsorted(np.array(e), X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
f = np.full(len(S.EV), M["F0"])
for t in M["trees"]: f += M["lr"] * G.pred(t, B)
sc = np.where(env, f, -1e9); np.save(out, sc)
G2 = {tuple(g): i for i, g in enumerate(S.GRID)}
for tier, thr in M["thresholds"].items():
    e = G2[tuple(M["exits"][tier])]; pick = S.spaced(sc >= thr)
    print(f"{M['name']} {tier} (score >= {thr:+.3f}) exit '{S.ename(e)}'\n   TRAIN {S.fmt(S.summary(pick, S.TR, e, S.HTR))}\n   TEST  {S.fmt(S.summary(pick, S.TE, e, S.HTE))}")

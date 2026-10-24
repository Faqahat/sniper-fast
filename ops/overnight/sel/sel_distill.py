#!/usr/bin/env python3
# Readable rules from a GBDT selection (local only): inside the watch envelope, a small decision tree (Gini, depth DEPTH, min
# leaf MINLEAF) learns on TRAIN hours which dumps the model picks; leaves where most dumps are picks become AND-rules; the
# OR of those rules is then judged on TRAIN and TEST with the chosen exit, like the model itself.
# usage: python3 -I sel_distill.py score.npy THR EXIT_INDEX     env: SELV, DEPTH (3), MINLEAF (40), PREC (0.5)
import sys, os, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import sel_lib as S
sc = np.load(sys.argv[1]); thr = float(sys.argv[2]); e = int(sys.argv[3])
DEPTH = int(os.environ.get("DEPTH", "3")); MINLEAF = int(os.environ.get("MINLEAF", "40")); PREC = float(os.environ.get("PREC", "0.5"))
env = sc > -1e8; z = sc >= thr
rows = np.where(env & S.TR)[0]
Q = {j: np.unique(np.quantile(S.X[rows, j][S.X[rows, j] < 1e8], np.linspace(0.05, 0.95, 19))) for j in range(len(S.FEATS))}
def gini(p): return 2 * p * (1 - p)
def grow(ix, depth, path, out):
    p = z[ix].mean() if len(ix) else 0
    if depth == 0 or len(ix) < 2 * MINLEAF or p in (0.0, 1.0):
        out.append((path, len(ix), p)); return
    best = (0, None)
    base = gini(p) * len(ix)
    for j in range(len(S.FEATS)):
        x = S.X[ix, j]
        for v in Q[j]:
            l = x <= v; nl = l.sum(); nr = len(ix) - nl
            if nl < MINLEAF or nr < MINLEAF: continue
            g = base - gini(z[ix][l].mean()) * nl - gini(z[ix][~l].mean()) * nr
            if g > best[0]: best = (g, (j, v))
    if best[1] is None: out.append((path, len(ix), p)); return
    j, v = best[1]; l = S.X[ix, j] <= v
    grow(ix[l], depth - 1, path + [(S.FEATS[j], "<=", float(v))], out)
    grow(ix[~l], depth - 1, path + [(S.FEATS[j], ">", float(v))], out)
leaves = []; grow(rows, DEPTH, [], leaves)
rules = [p for p, n, pr in leaves if pr >= PREC and n >= MINLEAF]
print(f"model picks on TRAIN inside the envelope: {int(z[rows].sum())} of {len(rows)}")
for p, n, pr in sorted(leaves, key=lambda x: -x[2]):
    print(f"  leaf {pr:5.0%} picks of {n:5d}: " + " AND ".join(f"{k} {op} {v:.4g}" for k, op, v in p))
sel = np.zeros(len(S.EV), bool)
for p in rules:
    m = env.copy()
    for k, op, v in p:
        j = S.FEATS.index(k); m &= (S.X[:, j] <= v) if op == "<=" else (S.X[:, j] > v)
    sel |= m
pick = S.spaced(sel)
np.save(os.environ.get("MASK_OUT", "/home/moiz/sniper/ops/overnight/sel/distilled.mask.npy"), sel)
print(f"\nRULES (OR of {len(rules)} leaves with >= {PREC:.0%} model picks), exit '{S.ename(e)}':")
print(f"  TRAIN {S.fmt(S.summary(pick, S.TR, e, S.HTR))}\n  TEST  {S.fmt(S.summary(pick, S.TE, e, S.HTE))}")
mp = S.spaced(z)
print(f"MODEL itself:\n  TRAIN {S.fmt(S.summary(mp, S.TR, e, S.HTR))}\n  TEST  {S.fmt(S.summary(mp, S.TE, e, S.HTE))}")
json.dump([[[k, ">=" if op == ">" else "<=", v + (1e-9 if op == ">" else 0)] for k, op, v in p] for p in rules], open(os.environ.get("OUT", "/home/moiz/sniper/ops/overnight/sel/distilled_rules.json"), "w"))

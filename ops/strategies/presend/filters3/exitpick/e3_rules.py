#!/usr/bin/env python3
"""EXITPICK step 3: one-feature threshold rules  'if f op th -> exit X, else t125'.  Thresholds from DEV deciles.
Picks on DEV; shows VAL for the DEV top; DEV-vs-VAL rank agreement over all rules; a label-shuffle null for the DEV best."""
import sys, random, statistics
from elib import *
R = load()
DL = sys.argv[1] if len(sys.argv) > 1 else "15"
STAGE = sys.argv[2] if len(sys.argv) > 2 else "AB"
A = sorted(R[0]["A"].keys()); B = sorted(R[0]["B"]["15"].keys())
FE = (A if "A" in STAGE else []) + (B if "B" in STAGE else [])
ACT = ["t100"] + EXT
dev = [r for r in R if r["split"] == "dev"]; val = [r for r in R if r["split"] == "val"]; hold = [r for r in R if r["split"] == "hold"]
G = {sp: {k: [gain(r, k) for r in rows] for k in ACT} for sp, rows in (("dev", dev), ("val", val), ("hold", hold))}
def fv(rows, f): return [feat(r, f, DL) for r in rows]
rules = []
for f in FE:
    xd = fv(dev, f); xv = fv(val, f); xh = fv(hold, f)
    qs = sorted(set(statistics.quantiles(xd, n=10, method="inclusive")))
    for th in qs:
        for op in (">=", "<"):
            md = [(a >= th) == (op == ">=") for a in xd]
            nd = sum(md)
            if nd < 30 or nd > len(dev) - 30: continue
            mv = [(a >= th) == (op == ">=") for a in xv]; mh = [(a >= th) == (op == ">=") for a in xh]
            for k in ACT:
                gd = sum(g for g, m in zip(G["dev"][k], md) if m)
                gv = sum(g for g, m in zip(G["val"][k], mv) if m)
                gh = sum(g for g, m in zip(G["hold"][k], mh) if m)
                rules.append((gd, gv, gh, f, op, th, k, nd, sum(mv), sum(mh)))
rules.sort(key=lambda z: -z[0])
print(f"stage {STAGE} delay {DL}: rules {len(rules)}")
print(" top 15 on DEV (gain vs t125, SOL):  dev | val | hold   rule   n_dev n_val n_hold")
for z in rules[:15]:
    print(f"  {z[0]:+.3f} | {z[1]:+.3f} | {z[2]:+.3f}   {z[3]} {z[4]} {z[5]:.4g} -> {z[6]}   {z[7]} {z[8]} {z[9]}")
for top in (10, 50, 200, 1000):
    tv = [z[1] for z in rules[:top]]
    print(f" DEV top {top}: VAL gain >0 in {sum(1 for a in tv if a > 0)}/{top}, mean VAL gain {sum(tv) / top:+.3f}")
# rank agreement
def rank(v):
    o = sorted(range(len(v)), key=lambda i: v[i]); rk = [0] * len(v)
    for i, j in enumerate(o): rk[j] = i
    return rk
rd, rv = rank([z[0] for z in rules]), rank([z[1] for z in rules])
n = len(rules); md, mv = sum(rd) / n, sum(rv) / n
cov = sum((a - md) * (b - mv) for a, b in zip(rd, rv)); sd = (sum((a - md) ** 2 for a in rd) * sum((b - mv) ** 2 for b in rv)) ** 0.5
print(f" Spearman(DEV gain, VAL gain) over all rules: {cov / sd:+.3f}")
# null: shuffle the gain rows (whole action vector per fill) vs features on DEV, best DEV gain
rnd = random.Random(3); best_null = []
idx = list(range(len(dev)))
for it in range(20):
    rnd.shuffle(idx)
    Gs = {k: [G["dev"][k][i] for i in idx] for k in ACT}
    b = -9
    for f in FE:
        xd = fv(dev, f); qs = sorted(set(statistics.quantiles(xd, n=10, method="inclusive")))
        for th in qs:
            for op in (">=", "<"):
                md = [(a >= th) == (op == ">=") for a in xd]
                if sum(md) < 30 or sum(md) > len(dev) - 30: continue
                for k in ACT:
                    b = max(b, sum(g for g, m in zip(Gs[k], md) if m))
    best_null.append(b)
best_null.sort()
print(f" NULL (shuffled labels, 20x): best DEV gain median {best_null[10]:+.3f}, 90th pct {best_null[17]:+.3f}, max {best_null[-1]:+.3f}  vs real best {rules[0][0]:+.3f}")

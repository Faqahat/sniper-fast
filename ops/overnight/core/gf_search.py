#!/usr/bin/env python3
# Generic-flow study, stage 3: selection search over decision points (gf_points.jsonl.gz).
# Rules = 1 or 2 threshold conditions on features known AT the decision time (no look-ahead: slip_lat / a10 / outcomes
# excluded). A rule is scored per (entry time T, exit) on BOTH periods (R1, R2) and also with every sniper/pro buy after
# our entry removed ("nosnip"). Graduated outcomes (curve completed during the hold: no AMM price) are dropped.
# Output: the best rules by min(R1 mean, R2 mean) with n >= NMIN in each; they still need the forward test.
import json, gzip, sys, itertools
import numpy as np
CORE = "/home/moiz/sniper/ops/overnight/core"
NMIN = int(sys.argv[1]) if len(sys.argv) > 1 else 40
PERM = int(sys.argv[2]) if len(sys.argv) > 2 else -1     # >= 0: shuffle outcomes within (T, period) with this seed = null run
R = [json.loads(l) for l in gzip.open(f"{CORE}/gf_points.jsonl.gz", "rt")]
RN = list(R[0]["o"].keys())
FN = list(R[0]["f"].keys()) + ["dev", "gl", "gls", "mcb", "hr", "rec_n", "rec_nb60", "rec_pk", "rec_f2x", "rec_m60", "rec_sb60"]
def fv(r): return [r["f"][k] for k in R[0]["f"]] + [r["dev"], r["gl"], r["gls"], r["mcb"], r["hr"]] + r["rec"]
out = []
for T in sorted({r["T"] for r in R}):
    rr = [r for r in R if r["T"] == T]
    if PERM >= 0:                                          # null: outcomes shuffled across decision points of the same period
        rng = np.random.default_rng(PERM * 1000 + T)
        for runv in ("R1", "R2"):
            idx = [i for i, r in enumerate(rr) if r["run"] == runv]; perm = rng.permutation(idx)
            outs = [rr[i]["o"] for i in perm]
            rr = list(rr)
            for i, o in zip(idx, outs): rr[i] = dict(rr[i], o=o)
    X = np.array([fv(r) for r in rr], dtype=float); run = np.array([r["run"] == "R1" for r in rr])
    for ex in RN:
        y = np.array([r["o"][ex][0] for r in rr]); y2 = np.array([r["o"][ex][1] if r["o"][ex][1] is not None else r["o"][ex][0] for r in rr])
        ok = np.array([not r["o"][ex][2] for r in rr])
        # depth-1 conditions: feature >= q or <= q at deciles of the pooled data
        conds = []
        for j in range(X.shape[1]):
            qs = np.unique(np.quantile(X[:, j], np.linspace(0.1, 0.9, 9)))
            for q in qs:
                conds.append((j, ">=", q, X[:, j] >= q)); conds.append((j, "<=", q, X[:, j] <= q))
        def score(mask):
            m1 = mask & ok & run; m2 = mask & ok & ~run
            n1, n2 = m1.sum(), m2.sum()
            if n1 < NMIN or n2 < NMIN: return None
            return (min(y[m1].mean(), y[m2].mean()), y[m1].mean(), y[m2].mean(), n1, n2, y2[m1].mean(), y2[m2].mean())
        sc1 = []
        for c in conds:
            s = score(c[3])
            if s: sc1.append((s, [c]))
        sc1.sort(key=lambda z: -z[0][0])
        best = sc1[:3]
        for s0, cs in sc1[:40]:                                        # extend the 40 best single conditions by one more
            for c in conds:
                if c[0] == cs[0][0]: continue
                s = score(cs[0][3] & c[3])
                if s and s[0] > s0[0]: best.append((s, cs + [c]))
        best.sort(key=lambda z: -z[0][0])
        seen = set()
        for s, cs in best[:6]:
            key = tuple((FN[c[0]], c[1], round(float(c[2]), 4)) for c in cs)
            if key in seen: continue
            seen.add(key)
            out.append(dict(T=T, ex=ex, rule=[f"{FN[c[0]]} {c[1]} {c[2]:.4g}" for c in cs], minmean=round(float(s[0]) * 100, 2), r1=round(float(s[1]) * 100, 2),
                            r2=round(float(s[2]) * 100, 2), n1=int(s[3]), n2=int(s[4]), r1_nosnip=round(float(s[5]) * 100, 2), r2_nosnip=round(float(s[6]) * 100, 2)))
out.sort(key=lambda z: -z["minmean"])
json.dump(out, open(f"{CORE}/gf_rules_n{NMIN}" + (f"_perm{PERM}" if PERM >= 0 else "") + ".json", "w"))
print(f"rules scored; top 30 by the worse of the two periods (mean % per trade), n >= {NMIN} per period:")
for o in out[:30]:
    print(f"  T={o['T']:3d} {o['ex']:16s} {' & '.join(o['rule']):60s} R1 {o['r1']:+6.2f}% (n {o['n1']:4d}) R2 {o['r2']:+6.2f}% (n {o['n2']:4d}) | nosnip {o['r1_nosnip']:+6.2f} / {o['r2_nosnip']:+6.2f}")

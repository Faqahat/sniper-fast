#!/usr/bin/env python3
# search simple create-time rules on first-time-dev launches: entry one slot late (B), exits 1 s / 5 s / 30 s; TRAIN before
# 10-23 06:00 PKT, TEST after. Beam search over AND-rules (min 2 trades/h on TRAIN); report TRAIN vs TEST.
import json, itertools, time, calendar
import numpy as np
import os; R = [r for r in json.load(open(os.environ.get("FD_FOUT", "/home/moiz/sniper/ops/overnight/firstdev/firstdev_f.json"))) if r["B"]]
SPLIT = calendar.timegm(time.strptime("2026-10-23 06:00", "%Y-%m-%d %H:%M")) - 18000
F = ["dev_buy", "bundle_n", "bundle_sol", "vsol_entry", "create_fee", "tw", "tg", "web", "desc_len", "prior_n", "funder", "jito", "name_len"]
X = np.array([[float(r.get(k) or 0) for k in F] for r in R]); T = np.array([r["bt"] for r in R]); tr = T < SPLIT; te = ~tr
HTR = (T[tr].max() - T[tr].min()) / 3600; HTE = (T[te].max() - T[te].min()) / 3600
print(f"first-time-dev launches: TRAIN {tr.sum()} ({HTR:.1f} h), TEST {te.sum()} ({HTE:.1f} h)")
GR = {k: sorted(set(float(np.quantile(X[tr, j], q)) for q in np.linspace(0.05, 0.95, 19))) for j, k in enumerate(F)}
for ex in ("1s", "5s", "30s"):
    P = np.array([r["B"][ex] for r in R]); PA = np.array([r["A"][ex] for r in R])
    def mask(c):
        m = np.ones(len(R), bool)
        for k, op, v in c: j = F.index(k); m &= (X[:, j] >= v) if op == ">=" else (X[:, j] <= v)
        return m
    def obj(c):
        m = mask(c) & tr
        return P[m].sum() if m.sum() / HTR >= 2 else -1e9
    beam = [(obj([]), [])]; best = beam[0]
    for d in range(4):
        cand = []
        for sc, c in beam:
            used = {(k, op) for k, op, _ in c}
            for k in F:
                for op in (">=", "<="):
                    if (k, op) in used: continue
                    for v in GR[k]: cc = c + [(k, op, v)]; cand.append((obj(cc), cc))
        cand.sort(key=lambda x: -x[0]); beam = cand[:6]
        if beam[0][0] <= best[0]: break
        best = beam[0]
    c = best[1]; m = mask(c)
    f = lambda mm, PP: f"{mm.sum():5d} trades ({mm.sum() / (HTR if mm is not None and (mm & tr).sum() == mm.sum() else HTE):5.1f}/h) {PP[mm].sum():+7.2f} SOL win {(PP[mm] > 0).mean() if mm.any() else 0:.0%}"
    print(f"\nexit {ex}: ALL first-time devs one slot late: TRAIN {P[tr].sum():+.2f} | TEST {P[te].sum():+.2f}")
    print("  best rule on TRAIN: " + (" AND ".join(f"{k} {op} {v:.4g}" for k, op, v in c) or "(none)"))
    print(f"  TRAIN {f(m & tr, P)} | TEST {f(m & te, P)} | (first in line, same rule: TEST {PA[m & te].sum():+.2f})")

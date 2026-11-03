#!/usr/bin/env python3
"""YOUNG step 7: the plain grid (no filter, QUIET on) for age 0 and age 1, train vs test, + how well train rank carries to test."""
import pickle, statistics as st
from yan import *
import y6_search as S
T = S.T; HTR, HTE = S.HTR, S.HTE
for ages, lab in (((0,), "AGE 0"), ((1,), "AGE 1")):
    A = [r for r in T if r["age"] in ages and not r["q_all4"]]
    TR = [r for r in A if not r["test"]]; TE = [r for r in A if r["test"]]
    print(f"== {lab} (QUIET on, no filter): recipe | train fills P&L /day per-fill | test fills P&L /day per-fill")
    for key in sorted(A[0]["res"].keys(), key=str):
        s1, f1, _ = S.score(TR, key); s2, f2, _ = S.score(TE, key)
        print(f"  {key[0]:9s} {key[1]:12s} {key[2]:.3f} | {f1:5.0f} {s1:+.3f} {s1/HTR*24:+.2f}/d {1e3*s1/max(f1,1e-9):+6.1f} | {f2:5.0f} {s2:+.3f} {s2/HTE*24:+.2f}/d {1e3*s2/max(f2,1e-9):+6.1f}")
    out = S.main(set(ages), lab + " (rank carry)") if False else None
# rank carry: all recipes (with filters) train vs test
for ages, lab in (((0,), "AGE 0"), ((1,), "AGE 1"), ((0, 1), "AGE 0+1")):
    A = [r for r in T if r["age"] in ages]
    TR = [r for r in A if not r["test"]]; TE = [r for r in A if r["test"]]
    pairs = []
    for key in A[0]["res"]:
        for qn in ("Q", "noQ"):
            for fn, f in S.F.items():
                a = [r for r in TR if f(r) and (qn == "noQ" or not r["q_all4"])]; b = [r for r in TE if f(r) and (qn == "noQ" or not r["q_all4"])]
                s1, f1, _ = S.score(a, key)
                if f1 < 25: continue
                s2, f2, _ = S.score(b, key); pairs.append((s1 / HTR, s2 / HTE))
    pairs.sort(key=lambda x: -x[0])
    top = pairs[:50]
    print(f"{lab}: {len(pairs)} recipes; train-vs-test corr {st.correlation([p[0] for p in pairs],[p[1] for p in pairs]):+.2f}; top-50 by train: test positive {sum(1 for p in top if p[1]>0)}/50; all recipes test positive {sum(1 for p in pairs if p[1]>0)}/{len(pairs)}; best test /day {max(p[1] for p in pairs)*24:+.2f}")

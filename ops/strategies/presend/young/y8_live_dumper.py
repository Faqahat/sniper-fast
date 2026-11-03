#!/usr/bin/env python3
"""YOUNG step 8 (LIVE check of the mechanism): realized P&L of live fills split by who made the dump before our fill
(the whale itself vs another wallet) and by age; dump = last other-wallet sell before our fill on the chain tape."""
import collections
from ylib import *
meta, R, TP = load()
A = collections.defaultdict(lambda: [0, 0.0, 0])
for r in R:
    if r["live"] != "armed" or len(r["lfill"]) != 1 or not r["real"] or r["real"][0] is None or not TP.get(r["sig"]): continue
    f = r["lfill"][0]; tp = TP[r["sig"]]
    pre = [x for x in tp if x[8] not in OURS and not x[3] and (r["slot"], r["idx"]) < (x[0], x[1]) < (f["slot"], f["idx"])]
    if not pre: continue
    d = pre[-1]; who = "whale" if d[8] == r["wallet"] else "other"
    g = "age1" if r["age"] == 1 else "age2+"
    p = r["real"][0] / 1e9
    for k in ((g, who), (g, who, "test" if is_test(r) else "train")):
        A[k][0] += 1; A[k][1] += p; A[k][2] += p > 0
for k in sorted(A):
    n, s, w = A[k]; print(k, n, f"{s:+.3f} SOL, {1e3*s/n:+.1f} mSOL/fill, win {w/n:.0%}")

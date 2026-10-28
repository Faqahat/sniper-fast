#!/usr/bin/env python3
"""FOLLOW step 6 (read-only): the AUX target "will haqq follow this whale's dump" (haqq bought within 2 slots after the whale's next
sell, MEASURED) as a selector. Same walk-forward as f4 (train <= d-2, cap + threshold chosen on d-1 by the replay's calibrated NOW net,
test d), same features, GBDT on the 0/1 label. Tells whether imitating his selection beats predicting our P&L directly.
Out: f6.txt"""
import sys, time, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/follow")
import flib as FL
from f4_wf import load, account, boot_mint, CI_FIT, QS
OUT = FL.OUT
P_ = []


def P(*x):
    s = " ".join(str(y) for y in x); print(s, flush=True); P_.append(s)


def main():
    t0 = time.time()
    F, meta, names, CAPS, labs, CV, ccr, U, day = load()
    y = meta["hqf"].astype(float)
    P("# AUX selector: predicted P(haqq follows the whale's dump); walk-forward, calibrated NOW net SOL per test day (k 4, <= 5 tokens)")
    P("| Day | AUC (test, all checkpoints) | cap / thr | fills | calibrated NOW | fol 0.9 |")
    P("|---|---|---|---|---|---|")
    for d in range(2, 7):
        tr = day <= d - 2; vd = day == d - 1; te = day == d
        Bm, edges = FL.binize(F, tr)
        idx = np.flatnonzero(tr); cut = idx[int(len(idx) * 0.8)]
        M = FL.fit(Bm, y, tr & (np.arange(len(F)) < cut), tr & (np.arange(len(F)) >= cut), seed=77 + d)
        s = FL.predict(M, Bm)
        best = None
        for ci in CI_FIT:
            for thr in sorted(set(float(np.quantile(s[vd], 1 - q)) for q in QS)):
                v = account(FL.replay(np.flatnonzero(vd & (s >= thr)), meta, labs, ci, CV, ccr, U, conc=5))
                if best is None or v[0] > best[0]: best = (v[0], ci, thr)
        _, ci, thr = best
        res = FL.replay(np.flatnonzero(te & (s >= thr)), meta, labs, ci, CV, ccr, U, conc=5)
        a = account(res); a9 = account(FL.replay(np.flatnonzero(te & (s >= thr)), meta, labs, ci, CV, ccr, U, conc=5, fol=1))
        P(f"| D{d} | {FL.auc(y[te] > 0, s[te]):.3f} | {CAPS[ci]} / {thr:.3f} | {a[2]:.0f} | {a[0]:+.2f} | {a9[0]:+.2f} |  ({time.time() - t0:.0f}s)")
    open(f"{OUT}/f6.txt", "w").write("\n".join(P_) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""FOLLOW step 8 (read-only): universe statistics per day for the report: usable episodes (whale buy-start / after its partial sell),
creation-slot whales, gap whale start -> its next sell (slots), the N = 0 label (cap 100, calibrated NOW) mean and the share > 0
(= 'followed' base rate in money terms), haqq-follow base rate. Out: f8.txt"""
import sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/follow")
import flib as FL
from f4_wf import load
OUT = FL.OUT


def main():
    F, meta, names, CAPS, labs, CV, ccr, U, day = load()
    n0 = meta["N"] == 0
    V, Pf, A = FL.labels(labs, CV, ccr, meta["t_c"], 3)
    y = 1000 * FL.net(V, Pf, A, cal=True); yg = 1000 * V / np.maximum(Pf, 1e-9)
    fi = {n: i for i, n in enumerate(names)}
    R = np.load(f"{OUT}/tape.npy", mmap_mode="r"); E = np.load(f"{OUT}/episodes.npz")
    out = ["| Day | episodes (N=0 rows) | buy-start / after-sell | creation-slot whale | gap to next sell p50 / p90 slots (closed) | P(fill) | label > 0 | mean label mSOL | haqq follows |",
           "|---|---|---|---|---|---|---|---|---|"]
    sl = np.asarray(R["slot"])
    for d in range(7):
        m = n0 & (day == d)
        if not m.any(): continue
        e = meta["e"][m]; r1 = E["r1"][e]; r0 = E["r0"][e]; cl = r1 >= 0
        gap = sl[r1[cl]].astype(np.int64) - sl[r0[cl]].astype(np.int64)
        out.append(f"| D{d} | {int(m.sum()):,} | {int((F[m, fi['kind']] == 0).sum()):,} / {int((F[m, fi['kind']] == 1).sum()):,} | {int(F[m, fi['w_cs']].sum()):,} | "
                   f"{np.percentile(gap, 50):.0f} / {np.percentile(gap, 90):.0f} | {Pf[m].mean():.3f} | {(y[m] > 0).mean():.3f} | {y[m].mean():+.2f} | {meta['hqf'][m].mean():.3f} |")
    print("\n".join(out)); open(f"{OUT}/f8.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

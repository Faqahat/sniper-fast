#!/usr/bin/env python3
"""SELECT step 11 (read-only): is the gain of each feature set over MKT real and stable? Per test day: rate-matched precision (top K = number
of y1 positives that day) and precision at the top 0.5 % of sells, for MKT and each other set; the difference with a 90 % bootstrap over
MINTS (resample mints, recompute both on the same resample). Out: select/s11.txt"""
import sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
from s4_wf import load_scores
OUT = "/home/moiz/sniper-data/haqq_dissect/select"


def prec_top(s, y, k):
    o = np.argsort(-s)[:k]; return float(y[o].mean())


def main():
    Z = np.load(f"{OUT}/env.npz"); y = (Z["y247"] | Z["y248"]).astype(bool); day = Z["day"].astype(int); m = Z["m"].astype(np.int64)
    SC = load_scores()
    base = SC["MKT"]
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
    rng = np.random.default_rng(4)
    for nm in [k for k in SC if k != "MKT" and not k.endswith(("_y247", "_y248"))]:
        S = SC[nm]
        P(f"\n## {nm} minus MKT (label y1 = 247 or 248)")
        P("| test day | rate-matched prec MKT | set | diff [90% over mints] | top 0.5 % prec MKT | set | diff [90%] |"); P("|---|---|---|---|---|---|---|")
        for D in range(2, 7):
            te = np.flatnonzero((day == D) & np.isfinite(S) & np.isfinite(base))
            yy = y[te]; k = int(yy.sum()); k2 = max(1, int(0.005 * len(te)))
            a1, b1 = prec_top(base[te], yy, k), prec_top(S[te], yy, k); a2, b2 = prec_top(base[te], yy, k2), prec_top(S[te], yy, k2)
            um, inv = np.unique(m[te], return_inverse=True)
            d1, d2 = [], []
            groups = np.split(np.argsort(inv), np.cumsum(np.bincount(inv))[:-1])
            for _ in range(100):
                pick = np.concatenate([groups[g] for g in rng.integers(0, len(um), len(um))])
                yb = yy[pick]; kb = int(yb.sum()); kb2 = max(1, int(0.005 * len(pick)))
                d1.append(prec_top(S[te][pick], yb, kb) - prec_top(base[te][pick], yb, kb))
                d2.append(prec_top(S[te][pick], yb, kb2) - prec_top(base[te][pick], yb, kb2))
            P(f"| D{D} | {a1:.3f} | {b1:.3f} | {b1 - a1:+.3f} [{np.percentile(d1, 5):+.3f}..{np.percentile(d1, 95):+.3f}] | {a2:.3f} | {b2:.3f} | "
              f"{b2 - a2:+.3f} [{np.percentile(d2, 5):+.3f}..{np.percentile(d2, 95):+.3f}] |")
    open(f"{OUT}/s11.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

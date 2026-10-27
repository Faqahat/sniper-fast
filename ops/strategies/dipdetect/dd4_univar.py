#!/usr/bin/env python3
# Univariate scan over the WHOLE universe: for every feature, P&L per attempt (35 ms, 1.3 s/SL10 and 4 s/SL20, costs incl.) by
# R2-quantile bins, per day; rank by how consistently the best bin beats the universe on all 4 days. MEASURED.
import numpy as np
import dd_lib as L
def y_of(d, e, lat=0):
    st = d["st"][:, lat]
    return np.where(st == 0, d["pnl"][:, lat, e] - L.FIX, np.where(st == 1, -L.FAIL, np.nan))
if __name__ == "__main__":
    D = {day: L.load(day) for day in ("R2", "R3", "R1", "R4")}
    res = []
    for fn in L.FN:
        j = L.FNI[fn]; x2 = D["R2"]["Xall"][:, j]; xv = x2[np.isfinite(x2)]
        if len(np.unique(xv)) < 2: continue
        qs = np.unique(np.quantile(xv, np.linspace(0, 1, 11)[1:-1]))
        line = []; best = None
        for e, en in ((L.E_13, "1.3"), (L.E_4S, "4s")):
            per = {}
            for day, d in D.items():
                y = y_of(d, e); x = d["Xall"][:, j]; b = np.where(np.isfinite(x), np.searchsorted(qs, x, side="right"), -1)
                per[day] = [(np.nanmean(y[b == q]) if (b == q).sum() > 30 else np.nan, (b == q).sum()) for q in range(-1, len(qs) + 1)]
            # bin with best R2 mean; how it does on other days
            r2 = [m for m, n in per["R2"]]; qb = int(np.nanargmax(r2))
            score = min(per[dy][qb][0] for dy in D)
            line.append((en, qb - 1, [per[dy][qb] for dy in D], score))
        res.append((max(l[3] for l in line), fn, qs, line))
    res.sort(key=lambda r: -r[0] if np.isfinite(r[0]) else 1e9)
    print("feature | exit | best R2 bin (lo..hi] | mean mSOL per attempt (n) on R2 / R3 / R1 / R4")
    for sc, fn, qs, line in res[:45]:
        for en, qb, cells, s in line:
            lo = qs[qb - 1] if qb >= 1 else -np.inf; hi = qs[qb] if qb < len(qs) else np.inf
            lab = "NaN" if qb == -1 else f"({lo:.3g}..{hi:.3g}]"
            print(f"{fn:15s} {en:4s} {lab:22s} " + " ".join(f"{1000 * m:+6.1f}({n:5d})" for m, n in cells))

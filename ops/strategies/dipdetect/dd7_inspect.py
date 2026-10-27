#!/usr/bin/env python3
# What does a trained detector pick? composition of its picks (engine-replayed fills) vs the baseline, per day.
import sys, json
import numpy as np
import dd_lib as L
DAYS = ("R2", "R3", "R1", "R4")
def preds(name):
    P = np.load(f"{L.OUT}/pred_{name}.npy"); out = {}; o = 0
    for day in DAYS:
        n = len(L.load(day)["k"]); out[day] = P[o:o + n]; o += n
    return out
if __name__ == "__main__":
    name = sys.argv[1]; thr = float(sys.argv[2])
    P = preds(name)
    for day in DAYS[1:]:
        d = L.load(day); f = lambda k: L.feat(d, k); p = P[day]
        sel = p >= thr; base = np.isfinite(d["f1"]) & (d["f1"] >= L.THR["top4"])
        o = L.sim(d, sel, 0, L.E_13, detail=True); b = L.sim(d, base, 0, L.E_13, detail=True)
        rows = np.array([r for r, sv, pn, fl in o["rows"]]); pnl = np.array([pn for r, sv, pn, fl in o["rows"]]); fl = np.array([x[3] for x in o["rows"]])
        print(f"\n=== {day}: NEW {L.fmt(o, L.hours(d))}\n         BASE {L.fmt(b, L.hours(d))}")
        def grp(nm, m):
            if m.sum() == 0: return
            print(f"   {nm:34s} att {m.sum():5d}  fill {fl[m].mean():.2f}  pnl {pnl[m].sum():+7.2f}  per att {1000 * pnl[m].mean():+6.1f} mSOL")
        env = d["env"][rows]; sc = np.isfinite(d["f1"][rows]); t4 = sc & (d["f1"][rows] >= L.THR["top4"]); t8 = sc & (d["f1"][rows] >= L.THR["top8"])
        grp("in env & IMIT1>=top4", t4); grp("in env & IMIT1 top8..top4", t8 & ~t4); grp("in env & IMIT1 < top8", sc & ~t8); grp("env unscored", env & ~sc); grp("out of env", ~env & ~sc)
        a = f("age_s")[rows]; dr = f("drop_pct")[rows]; sb = f("since_buy_s")[rows]; so = f("sol")[rows]
        grp("  out: age > 343 s", ~env & (a > 343.67)); grp("  out: drop < 4.65%", ~env & (dr < 4.65)); grp("  out: since_buy > 3.87", ~env & (sb > 3.869)); grp("  out: sell < 1.08", ~env & (so < 1.08))
        for lo, hi in ((0, 10), (10, 60), (60, 343.67), (343.67, 1e9)): grp(f"age {lo}-{hi} s", (a > lo) & (a <= hi))
        for lo, hi in ((2, 4.65), (4.65, 8), (8, 15), (15, 100)): grp(f"drop {lo}-{hi}%", (dr >= lo) & (dr < hi))
        for lo, hi in ((0, 0.5), (0.5, 1.08), (1.08, 2), (2, 5), (5, 1e9)): grp(f"sell {lo}-{hi} SOL", (so >= lo) & (so < hi))
        cu = f("curve")[rows]
        for lo, hi in ((0, 32), (32, 40), (40, 60), (60, 100)): grp(f"curve {lo}-{hi} SOL", (cu >= lo) & (cu < hi))

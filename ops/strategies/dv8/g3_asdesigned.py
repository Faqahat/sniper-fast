#!/usr/bin/env python3
"""DV8 step 4b (read-only): DV8 AS DESIGNED (haqq_strat REPORT: VALUE gate, timer 8, ~8,000 picks/day, K=3, all leaders, guard 1.05),
walk-forward like g1 (gate trained on days < D-1; threshold = the score that gives 8,000 picks per 24 h on day D-1), scored with
  old  = the earlier replay method (independent ms landing, vshift followers, no calibration), no position cap and K=3
  ours / calibrated / conservative = rank landing, exact followers (g1)
Also the old gate target (VALUE regression on ms-landing vshift P&L of fills, s8) vs our target; both scored the same way.
Out: dv8/g3.txt"""
import sys, json, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8"); sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
import dd_gbdt as G
import dv8lib as L
from g1_walkforward import load, Rep, calib_boot, COST
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)


def main():
    d = load(); R = Rep(d); M = d["M"]; X = d["X"].astype(np.float64); day = d["day"]; us = d["usable"]
    (A0, B0), BS = calib_boot(); HS = list(d["HS"]); hi = HS.index(8)
    rk = R.ranks
    v = np.where(d["FILL"][:, rk], d["PN"][:, rk, hi, 0], 0.0)
    Y_new = np.where(np.isfinite(d["PN"][:, 0, hi, 0]), np.nanmean(np.where(np.isfinite(v), v, 0), 1), np.nan)
    Y_old = np.where(d["FILL"][:, 1] & (d["PR"][:, 1] <= 1.10), d["VS7"][:, hi], np.nan)
    cb, cs, cf = COST["NOW"]
    def old_money(res):
        t = []
        for r in res:
            f = r["fill"]; pn = np.where(f, d["VS7"][r["idx"], hi], 0.0)
            t.append(np.nansum(pn) - f.sum() * (cb + cs) - (~f).sum() * cf)
        return np.mean(t)
    def cal(res, q=None):
        if q is None: return R.money(res, "NOW", A0, B0, True)
        return float(np.percentile([R.money(res, "NOW", a, b, True) for a, b in BS[::10]], q))
    P("# DV8 as designed (timer 8, ~8,000 picks/day from VAL, K=3, all leaders, 0.40 SOL, guard 1.05), walk-forward, SOL per day window, NOW costs")
    P("| day | gate target | picks | old method no cap | old method K=3 | ours K=3 | calibrated K=3 [5-95%] | calibrated CHEAP K=3 | fires K=3 |"); P("|---|---|---|---|---|---|---|---|---|")
    for D in (2, 3, 4, 5):
        tr = us & (day < D - 1); va = us & (day == D - 1); te = us & (day == D)
        E = G.edges_of(X, np.flatnonzero(tr)); B = G.binize(X, E)
        tri = np.flatnonzero(tr); tri = tri[np.argsort(M["bt"][tri])]; cut = int(0.8 * len(tri))
        for nm, Y in (("old (s8)", Y_old), ("ours", Y_new)):
            ok = np.isfinite(Y); f_ = tri[:cut][ok[tri[:cut]]]; v_ = tri[cut:][ok[tri[cut:]]]
            mdl = G.fit(B, np.clip(np.nan_to_num(Y), -0.2, 0.2), f_, v_, loss="l2", rounds=600, lr=0.05, depth=4, min_n=300, lam=10.0, sub=0.8, fsub=0.8, seed=2, patience=60)
            sc = G.predict(mdl, B)
            nval = va.sum(); want = 8000 * d["uh"].get(D - 1, 24) / 24
            th = float(np.quantile(sc[va], max(0.0, 1 - want / nval)))
            pk = te & (sc >= th)
            r0 = R.run(pk, hi, K=None, model="ms"); r3m = R.run(pk, hi, K=3, model="ms"); r3 = R.run(pk, hi, K=3)
            P(f"| D{D} | {nm} | {pk.sum():,} | {old_money(r0):+.2f} | {old_money(r3m):+.2f} | {R.money(r3, 'NOW'):+.2f} | {cal(r3):+.2f} [{cal(r3, 5):+.2f}..{cal(r3, 95):+.2f}] | "
              f"{R.money(r3, 'CHEAP', A0, B0, True):+.2f} | {R.counts(r3)['fires']:,.0f} |")
    open(f"{L.D}/g3.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

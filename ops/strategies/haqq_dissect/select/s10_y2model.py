#!/usr/bin/env python3
"""SELECT step 10 (read-only): skip the imitation - predict OUR money directly. Walk-forward GBDT regression of y2 = the pre-send-style
WAVE P&L per armed dump at NOW costs (s3 + s5 conventions, INFERRED replay) on the y2 sample (all y1 + 30 % of the rest, weights 1/0.30),
feature sets MKT / ALLX (+ creator, seller, create-tx, structure, time; no haqq memory) / PRE (ALLX minus the dump's own size and drop).
Test day D: fit on days < D; pick the dumps with predicted value > T, T chosen on day D-1's OOS predictions (best NOW sum) from a grid.
Money per day: NOW / S2 / CHEAP / NOW -10 % followers / NOW without haqq's rows / NOW minus the arming lower bound; and the same
selection's REGULAR-landing value (calibrated). Out: select/s10.txt"""
import sys, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dipdetect")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
import dd_gbdt as G
from s4_wf import load, MKT, CRE, SEL, STR, TIM, HQMEM, DUMP_ONLY
from s5_pnl import money
OUT = "/home/moiz/sniper-data/haqq_dissect/select"
TS = [-0.002, 0.0, 0.001, 0.002, 0.004, 0.006, 0.01, 0.015, 0.02]


def main():
    t0 = time.time()
    A, ccols = load(); Y = dict(np.load(f"{OUT}/y2.npz"))
    ok = Y["pick"] & np.isfinite(Y["PSF"]); n = np.flatnonzero(ok)
    w = Y["w"].astype(np.float64)[n]; day = A["day"].astype(int)[n]; m = A["m"].astype(np.int64)[n]
    v = money(Y, n, "ps"); vc = np.clip(v, -0.2, 0.2)
    ALLX = [f for f in MKT + CRE + SEL + ccols + STR + TIM if f not in HQMEM]
    sets = {"MKT": MKT, "ALLX": ALLX, "PRE": [f for f in ALLX if f not in DUMP_ONLY] + ["vpre"]}
    mval = (np.random.default_rng(6).random(int(m.max()) + 1) < 0.2)[m]
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
    P(f"# Direct y2 model (pre-send-style WAVE, NOW, mSOL per armed dump): {len(n):,} sampled dumps (weighted {w.sum():,.0f})")
    for nm, fs in sets.items():
        Xf = np.column_stack([A["f_" + f][n].astype(np.float64) for f in fs])
        S = np.full(len(n), np.nan)
        for D in range(2, 7):
            tr = day < D; fit = tr & ~mval; val = tr & mval; te = day == D
            E = G.edges_of(Xf, fit, nb=32); rows = np.flatnonzero(fit | val)
            mod = G.fit(G.binize(Xf[rows], E), vc[rows], fit[rows], val[rows], loss="l2", rounds=400, lr=0.08, depth=4, min_n=300, lam=20.0,
                        sub=0.6, fsub=0.5, seed=D, patience=40, w=w[rows])
            S[te] = G.predict(mod, G.binize(Xf[te], E))
        P(f"\n## {nm} ({len(fs)} features) ({time.time() - t0:.0f}s)")
        P("| test day | T (chosen D-1) | picks/day (weighted) | y1 share | NOW | S2 | CHEAP | NOW -10% fol | NOW no-haqq rows | NOW minus ARM | REG cal NOW | NOW adverse fill (H) |")
        P("|---|---|---|---|---|---|---|---|---|---|---|---|")
        tot = np.zeros(8)
        y1 = (A["y247"] | A["y248"])[n]
        for D in range(2, 7):
            def ssum(D_, T, **kw):
                k = (day == D_) & (S > T)
                return float((money(Y, n[k], kw.pop("model", "ps"), A=A, **kw) * w[k]).sum())
            T = max(TS, key=lambda t: ssum(D - 1, t)) if D > 2 else 0.004
            k = (day == D) & (S > T)
            vals = [ssum(D, T), ssum(D, T, cost="S2"), ssum(D, T, cost="CHEAP"), ssum(D, T, fol=1), ssum(D, T, nohq=True), ssum(D, T, arm=True), ssum(D, T, model="reg"), ssum(D, T, adv=True)]
            tot += vals
            P(f"| D{D} | {T} | {w[k].sum():,.0f} | {float((y1[k] * w[k]).sum() / max(w[k].sum(), 1)):.3f} | " + " | ".join(f"{x:+.2f}" for x in vals) + " |")
        P("| sum D2-D6 | | | | " + " | ".join(f"{x:+.2f}" for x in tot) + " |")
        # rank quality: top-decile realized mean by day
        P("top 1 % / 5 % of each test day by prediction: realized NOW mSOL per armed dump (weighted): " +
          "; ".join(f"D{D} " + "/".join(f"{1000 * float((v[(day == D) & (S >= np.nanpercentile(S[day == D], 100 - q))] * w[(day == D) & (S >= np.nanpercentile(S[day == D], 100 - q))]).sum() / w[(day == D) & (S >= np.nanpercentile(S[day == D], 100 - q))].sum()):+.1f}" for q in (1, 5)) for D in range(2, 7)))
    open(f"{OUT}/s10.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

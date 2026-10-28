#!/usr/bin/env python3
"""SELECT step 5 (read-only): walk-forward P&L for US of a selector built on the s4 OOS scores (INFERRED replay, s3 y2).
Per test day D: pick the top q of the day's envelope sells by score; q chosen on day D-1 (best calibrated NOW P&L on D-1's OOS scores,
grid below); also fixed q. y2 is known for every y1 positive + a 30 % sample of the rest (weight 1/0.30): sums are weighted.
Entries and money per picked dump (mSOL, per the gap analyst's g11b conventions):
  ps  : 0.45 x curve P&L - f x FILL - (1 - f) x 0.198, f = 0.45 x fill share (MEASURED P(fill | armed, whale sold) = 0.45); FILL = NOW 2.51 /
        S2 0.98 (sell 1.805 -> 0.276) / CHEAP 0.79 (haqq's measured cost per lot). ARM = lower-bound arming cost: slots since the seller's first buy x 0.0205 mSOL
        (4 tries/slot x 5,120 lamports); whales that never dump are NOT charged (so ARM is optimistic).
  reg : calibrated 0.61 x curve - 1.17 mSOL/fire - f x FILL - (1 - f) x FAIL; NOW 3.52 / 0.53, S2 1.86 / 0.36, CHEAP 0.79 / 0.04 (as bots/b6).
  exits: ps WAVE_PS (RIDE 150/150/1000) ; reg WAVE_REG (RIDE 150/300/2000). Followers x1.0 and x0.9.
Out: select/s5.txt"""
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
from s4_wf import load_scores
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/select"
PSF = 0.45; XC = 0.000198; ARM = 4 * 5120 / 1e9
FILL_PS = dict(NOW=0.00251, S2=0.00251 - 0.001529, CHEAP=0.00079)
FILL_RG = dict(NOW=(0.00352, 0.00053), S2=(0.00186, 0.00036), CHEAP=(0.00079, 0.00004))
CA, CB = 0.61, -0.00117
QS = [0.0005, 0.001, 0.002, 0.005, 0.01, 0.02, 0.05]


ADV_E = np.array([-1e9, -0.010, 0.0, 0.010, 0.030, 0.060, 1e9]); ADV_PF = np.array([0.571, 0.678, 0.623, 0.495, 0.415, 0.225])


def money(Y, n, model, cost="NOW", fol=0, pol=0, nohq=False, arm=False, A=None, adv=False):
    if model == "ps":
        c = Y["PS"][n, 1 if nohq else 0, fol, pol].astype(np.float64); f = Y["PSF"][n] * PSF
        if adv:     # analyst H's MEASURED value-dependent live fill (f9: PF_b by the fill's gross WAVE value) instead of the flat 0.45
            psf = Y["PSF"][n].astype(np.float64); vf = np.where(psf > 0, Y["PS"][n, 0, 0, 0] / np.maximum(psf, 1e-9), 0.0)
            pf = ADV_PF[np.clip(np.searchsorted(ADV_E, vf, side="right") - 1, 0, 5)]
            v = pf * c - pf * psf * FILL_PS[cost] - (1 - pf * psf) * XC
            if arm: v = v - np.clip(A["f_sel_arm"][n], 0, None) * ARM
            return v
        v = PSF * c - f * FILL_PS[cost] - (1 - f) * XC
        if arm: v = v - np.clip(A["f_sel_arm"][n], 0, None) * ARM
    else:
        c = Y["RG"][n, fol, pol].astype(np.float64); f = Y["RGF"][n]
        v = CA * c + CB - f * FILL_RG[cost][0] - (1 - f) * FILL_RG[cost][1]
    return v


def main():
    A = dict(np.load(f"{OUT}/env.npz")); Y = dict(np.load(f"{OUT}/y2.npz")); SC = load_scores()
    y = (A["y247"] | A["y248"]).astype(bool); day = A["day"].astype(int); pick = Y["pick"] & np.isfinite(Y["PSF"]); w = Y["w"].astype(np.float64)
    lines = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); lines.append(s)
    # --- y2 sanity: by y1
    P("# y2 (INFERRED replay) by the y1 label, all days, per armed/fired dump (mSOL; weighted)")
    P("| set | dumps (weighted) | ps fill | ps WAVE NOW | ps WAVE NOW no-haqq-rows | ps NOW -10% fol | ps T2 NOW | reg fill | reg WAVE NOW cal | reg T5 NOW cal |"); P("|---|---|---|---|---|---|---|---|---|---|")
    for nm, msk in (("247/248 bought (y1)", y), ("not bought", ~y), ("all", np.ones_like(y))):
        n = np.flatnonzero(pick & msk); ww = w[n]
        mw = lambda v: 1000 * float((v * ww).sum() / ww.sum())
        P(f"| {nm} | {ww.sum():,.0f} | {float((Y['PSF'][n] * ww).sum() / ww.sum()):.2f} | {mw(money(Y, n, 'ps')):+.2f} | {mw(money(Y, n, 'ps', nohq=True)):+.2f} | "
          f"{mw(money(Y, n, 'ps', fol=1)):+.2f} | {mw(money(Y, n, 'ps', pol=1)):+.2f} | {float((Y['RGF'][n] * ww).sum() / ww.sum()):.2f} | "
          f"{mw(money(Y, n, 'reg')):+.2f} | {mw(money(Y, n, 'reg', pol=1)):+.2f} |")
    # --- per score set: fixed q and walk-forward q
    for nm, S in SC.items():
        P(f"\n## selector {nm}: SOL/day of the picked dumps (weighted sums), walk-forward")
        for model in ("ps", "reg"):
            def daysum(D, q, **kw):
                te = np.flatnonzero((day == D) & np.isfinite(S))
                if not len(te): return 0.0, 0
                k = max(1, int(q * len(te))); top = te[np.argsort(-S[te])[:k]]
                n = top[pick[top]]
                return float((money(Y, n, model, A=A, **kw) * w[n]).sum()), k
            days = [d for d in range(1, 7) if np.isfinite(S[day == d]).any()]
            P(f"\n### entry {model}: fixed top-q per day, calibrated NOW (SOL)")
            P("| q | " + " | ".join(f"D{d}" for d in days) + " | sum D2-D6 | picks/day |"); P("|---|" + "---|" * len(days) + "---|---|")
            for q in QS:
                v = [daysum(d, q) for d in days]
                P(f"| {q:.4f} | " + " | ".join(f"{x[0]:+.2f}" for x in v) + f" | {sum(x[0] for x in v if True) - v[0][0]:+.2f} | {np.mean([x[1] for x in v]):,.0f} |")
            P(f"\n### entry {model}: q chosen on the previous day (best NOW), test day results")
            hdr = "| test day | q | picks | y1 precision | NOW | S2 | CHEAP | NOW -10% fol |" + (" NOW minus ARM | NOW no-haqq rows | NOW adverse fill (H) | S2 adverse fill |" if model == "ps" else "")
            P(hdr); P("|---" * (hdr.count("|") - 1) + "|")
            tot = np.zeros(8)
            for D in days[1:]:
                q = max(QS, key=lambda qq: daysum(D - 1, qq)[0])
                te = np.flatnonzero((day == D) & np.isfinite(S)); k = max(1, int(q * len(te))); top = te[np.argsort(-S[te])[:k]]
                vals = [daysum(D, q)[0], daysum(D, q, cost="S2")[0], daysum(D, q, cost="CHEAP")[0], daysum(D, q, fol=1)[0]]
                if model == "ps": vals += [daysum(D, q, arm=True)[0], daysum(D, q, nohq=True)[0], daysum(D, q, adv=True)[0], daysum(D, q, adv=True, cost="S2")[0]]
                tot[:len(vals)] += vals
                P(f"| D{D} | {q} | {k:,} | {y[top].mean():.3f} | " + " | ".join(f"{v:+.2f}" for v in vals) + " |")
            nd = len(days) - 1
            P(f"| mean/day D2-D6 | | | | " + " | ".join(f"{v / nd:+.2f}" for v in tot[:4 + (4 if model == 'ps' else 0)]) + " |")
    open(f"{OUT}/s5.txt", "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()

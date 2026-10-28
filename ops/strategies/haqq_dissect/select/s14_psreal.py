#!/usr/bin/env python3
"""SELECT step 14 (read-only): the pre-send-style selector made realistic. Only dumps a pre-send limit could fill (single-sell drop >= 12 %
= the engine's 0.88 x pre-dump limit; variant >= 8 %), value with analyst H's MEASURED adverse live fill (f9 PF_b by value) instead of the
flat 0.45, top-K picks per day by each score set (K chosen on the previous day by NOW money from a grid), K up to 1,600/day; D6 is a 2-hour stub (K scaled x 2/24).
Money as s5 (INFERRED replay, WAVE_PS exit). Out: select/s14.txt"""
import sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
from s4_wf import load_scores
from s5_pnl import money
OUT = "/home/moiz/sniper-data/haqq_dissect/select"
KS = [25, 50, 100, 200, 400, 800, 1600]


def main():
    Z = np.load(f"{OUT}/env.npz"); A = {k: Z[k] for k in ("y247", "y248", "day", "f_drop", "f_sel_arm")}
    Y = dict(np.load(f"{OUT}/y2.npz")); SC = load_scores()
    y = (A["y247"] | A["y248"]).astype(bool); day = A["day"].astype(int); w = Y["w"].astype(np.float64)
    ok = Y["pick"] & np.isfinite(Y["PSF"])
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
    for dmin in (0.12, 0.08):
        elig = ok & (A["f_drop"] >= dmin)
        P(f"\n# Eligible: drop >= {dmin:.0%} ({int((elig & (day >= 2)).sum()):,} sampled dumps D2-D6, weighted {w[elig & (day >= 2)].sum() / 5:,.0f}/day); y1 rate {float((y[elig] * w[elig]).sum() / w[elig].sum()):.3f}")
        P("| selector | test-day results D3..D6: K / picks y1 precision / ADV NOW | mean/day D3-D6 (D6 = 2 h) ADV NOW | ADV S2 | ADV CHEAP | ADV -10% fol | ADV no-haqq rows | ADV NOW minus ARM | flat-fill NOW |")
        P("|---|---|---|---|---|---|---|---|---|")
        R = {}
        for nm in ("MKT", "ALLX", "ALL", "PRE", "HQ", "ORACLE y1"):
            S = SC[nm] if nm in SC else y.astype(float) + 1e-3 * np.random.default_rng(0).random(len(y))
            def run(D, K, **kw):
                te = np.flatnonzero(elig & (day == D) & np.isfinite(S))
                # K = picks per day in TRUE count: sampled negatives carry weight 1/0.3; take top until the weighted count reaches K
                o = te[np.argsort(-S[te])]; cw = np.cumsum(w[o]); top = o[:int(np.searchsorted(cw, K)) + 1]
                return float((money(Y, top, "ps", A=A, adv=kw.pop("adv", True), **kw) * w[top]).sum()), top
            cells = []; tot = np.zeros(7)
            for D in range(3, 7):
                K = max(KS, key=lambda k: run(D - 1, k)[0]) if nm != "ORACLE y1" else 400
                if D == 6: K = max(1, int(K * 2 / 24))
                v, top = run(D, K)
                vals = [v, run(D, K, cost="S2")[0], run(D, K, cost="CHEAP")[0], run(D, K, fol=1)[0], run(D, K, nohq=True)[0], run(D, K, arm=True)[0], run(D, K, adv=False)[0]]
                tot += vals
                cells.append(f"D{D} K{K} {float((y[top] * w[top]).sum() / w[top].sum()):.2f} {v:+.2f}")
            P(f"| {nm} | " + "; ".join(cells) + " | " + " | ".join(f"{x / 4:+.2f}" for x in tot[:6]) + f" | {tot[6] / 4:+.2f} |")
            R[nm] = tot
    open(f"{OUT}/s14.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

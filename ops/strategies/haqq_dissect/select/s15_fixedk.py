#!/usr/bin/env python3
"""SELECT step 15 (read-only): fixed-K comparison of the pre-send-style selectors (s14 setting: drop >= 12 % / >= 8 %, H's adverse fill,
WAVE_PS, NOW costs), full test days D3-D5: SOL/day per selector at K = 400 / 800 / 1,600 picks/day, and the ALLX - MKT and PRE - MKT
differences with a 90 % bootstrap over picked dumps (resampling each set's picks). INFERRED replay. Out: select/s15.txt"""
import sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/select")
from s4_wf import load_scores
from s5_pnl import money
OUT = "/home/moiz/sniper-data/haqq_dissect/select"


def main():
    Z = np.load(f"{OUT}/env.npz"); A = {k: Z[k] for k in ("y247", "y248", "day", "f_drop", "f_sel_arm")}
    Y = dict(np.load(f"{OUT}/y2.npz")); SC = load_scores()
    y = (A["y247"] | A["y248"]).astype(bool); day = A["day"].astype(int); w = Y["w"].astype(np.float64); ok = Y["pick"] & np.isfinite(Y["PSF"])
    out = []
    def P(*a):
        s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)
    g = np.random.default_rng(3)
    for dmin in (0.12, 0.08):
        elig = ok & (A["f_drop"] >= dmin)
        P(f"\n# drop >= {dmin:.0%}: SOL/day (D3 / D4 / D5) at fixed K, ADV fill, NOW; [y1 precision of picks]")
        P("| K/day | MKT | ALLX | PRE | ALL | HQ | ALLX - MKT, 3-day mean [90%] | PRE - MKT [90%] | ALLX -10% fol | ALLX no-haqq rows | ALLX S2 |"); P("|---|---|---|---|---|---|---|---|---|---|---|")
        for K in (400, 800, 1600):
            res = {}; per = {}
            for nm in ("MKT", "ALLX", "PRE", "ALL", "HQ"):
                S = SC[nm]; vs = []; pk = []
                for D in (3, 4, 5):
                    te = np.flatnonzero(elig & (day == D) & np.isfinite(S)); o = te[np.argsort(-S[te])]; top = o[:int(np.searchsorted(np.cumsum(w[o]), K)) + 1]
                    vs.append(float((money(Y, top, "ps", adv=True) * w[top]).sum())); pk.append(top)
                res[nm] = (vs, float(np.mean([(y[t] * w[t]).sum() / w[t].sum() for t in pk])), pk)
                per[nm] = np.concatenate([money(Y, t, "ps", adv=True) * w[t] for t in pk])
            def dif(a, b):
                bs = [(per[a][g.integers(0, len(per[a]), len(per[a]))].sum() - per[b][g.integers(0, len(per[b]), len(per[b]))].sum()) / 3 for _ in range(1000)]
                return f"{(per[a].sum() - per[b].sum()) / 3:+.2f} [{np.percentile(bs, 5):+.2f}..{np.percentile(bs, 95):+.2f}]"
            pkA = res["ALLX"][2]
            ex = [sum(float((money(Y, t, "ps", adv=True, **kw) * w[t]).sum()) for t in pkA) / 3 for kw in (dict(fol=1), dict(nohq=True), dict(cost="S2"))]
            P(f"| {K} | " + " | ".join(f"{' / '.join(f'{v:+.1f}' for v in res[nm][0])} [{res[nm][1]:.2f}]" for nm in ("MKT", "ALLX", "PRE", "ALL", "HQ")) +
              f" | {dif('ALLX', 'MKT')} | {dif('PRE', 'MKT')} | {ex[0]:+.2f} | {ex[1]:+.2f} | {ex[2]:+.2f} |")
    open(f"{OUT}/s15.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

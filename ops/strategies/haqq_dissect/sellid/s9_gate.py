#!/usr/bin/env python3
"""SELLID step 9 (read-only):
(1) Fast winners vs 4-8 s holds (bots 247/248, s7_rows.pkl): per-day AUC of single early features (first 400 ms after his buy) and a
    walk-forward logistic model (numpy, standardised, trained on days < d).
(2) The causal rule this suggests, on OUR fills (exact replay, MEASURED delays): GATE(t1, X, s, tmax) = at t1 ms after our fill, if
    outside buy SOL since the fill >= X -> ride (sell at the first s-ms gap with no outside buy after t1, cap tmax), else sell at t1.
    GATEV(t1, y, s, tmax) = same with 'our value at t1 >= 1 + y'. Walk-forward: parameters chosen on earlier days, vs the wave exit
    (pre-send RIDE(150,150,1000), regular RIDE(150,300,2000)), full and 10% fewer followers.
Out: sellid/s9.txt"""
import pickle, sys, itertools
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev as ev12
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)


def auc(y, s):
    y = np.asarray(y, bool); s = np.asarray(s, float)
    o = np.argsort(s, kind="mergesort"); r = np.empty(len(s)); r[o] = np.arange(1, len(s) + 1)
    # average ties
    _, inv, cnt = np.unique(s, return_inverse=True, return_counts=True)
    sums = np.bincount(inv, r); r = (sums / cnt)[inv]
    n1 = y.sum(); n0 = (~y).sum()
    return (r[y].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1)


def logit_fit(Xm, y, it=300, lr=0.1, l2=1e-3):
    w = np.zeros(Xm.shape[1]); b = 0.0
    for _ in range(it):
        p = 1 / (1 + np.exp(-(Xm @ w + b)))
        g = p - y; w -= lr * (Xm.T @ g / len(y) + l2 * w); b -= lr * g.mean()
    return w, b


def ride_from(S, t1, s, tmax):
    bt = S.dcc[S.bu]; later = bt[bt > t1 - s]
    if not len(later): return t1
    gaps = np.diff(np.concatenate([later, [np.inf]]))
    j = np.argmax(gaps >= s); return min(max(later[j] + s, t1), tmax)


def main():
    rows = pickle.load(open(f"{OUT}/s7_rows.pkl", "rb"))
    F = ["v400", "vmax400", "bsol400", "maxb400", "nb400", "nbw400", "nfol400", "nfb400", "ns400", "ssol400", "gap400", "hq400", "drop", "dsol", "ahead", "vsol"]
    P("# (1) Fast winners (< 2 s) vs 4-8 s holds: what is visible in the first 400 ms (MEASURED)")
    for code in (247, 248):
        R = [r for r in rows if r["code"] == code and (r["hold"] < 2000 or 4000 <= r["hold"] < 8000)]
        y = np.array([r["hold"] < 2000 for r in R]); d = np.array([r["day"] for r in R])
        P(f"\n## bot {code}: {y.sum():,} fast vs {(~y).sum():,} slow")
        P("| feature | AUC all | " + " | ".join(f"D{k}" for k in range(7)) + " |"); P("|---|---|" + "---|" * 7)
        for f in F:
            s = np.nan_to_num(np.array([r[f] for r in R], float), nan=-1)
            P(f"| {f} | {auc(y, s):.3f} | " + " | ".join(f"{auc(y[d == k], s[d == k]):.2f}" if (d == k).sum() > 30 else "·" for k in range(7)) + " |")
        Xm = np.nan_to_num(np.array([[r[f] for f in F] for r in R], float), nan=0.0)
        Xm[:, F.index("bsol400")] = np.log1p(Xm[:, F.index("bsol400")]); Xm[:, F.index("ssol400")] = np.log1p(Xm[:, F.index("ssol400")])
        res = []
        for k in range(2, 7):
            tr = d < k; te = d == k
            if te.sum() < 30: continue
            mu = Xm[tr].mean(0); sd = Xm[tr].std(0) + 1e-9
            w, b = logit_fit((Xm[tr] - mu) / sd, y[tr].astype(float))
            sc = (Xm[te] - mu) / sd @ w + b
            res.append(f"D{k} {auc(y[te], sc):.3f} (n {te.sum()})")
        P(f"- walk-forward logistic (all features): " + ", ".join(res))
        P(f"- for reference, outcome: fast lots {1000 * np.mean([r['net'] for r in R if r['hold'] < 2000]):+.1f} mSOL/lot, slow {1000 * np.mean([r['net'] for r in R if r['hold'] >= 4000]):+.1f}")
    # ---------------- (2) gate rules on OUR fills
    O = pickle.load(open(f"{OUT}/ourpaths_us.pkl", "rb"))
    DR, DT, _ = delays()
    grid = [("WAVEPS",), ("WAVEREG",)]
    for t1, x, s, tm in itertools.product((100, 150, 200, 300), (0.5, 1.0, 2.0, 3.0), (150, 300, 500), (1000, 2000, 4000)):
        grid.append(("GATE", t1, x, s, tm))
    for t1, yv, s, tm in itertools.product((100, 150, 200, 300), (0.0, 0.03, 0.06, 0.10), (150, 300, 500), (1000, 2000, 4000)):
        grid.append(("GATEV", t1, yv, s, tm))
    G = {}
    for fol in (1.0, 0.9):
        M = np.zeros((len(grid), len(O)))
        for b, p in enumerate(O):
            S = Pos(p, fol)
            if S.n == 0:
                M[:, b] = (S.v_pre - 1) * S.cost; continue
            for a, pol in enumerate(grid):
                k = pol[0]
                if k == "WAVEPS": v = ev12(S, ("RIDE", 150, 150, 1000), DR, DT)
                elif k == "WAVEREG": v = ev12(S, ("RIDE", 150, 300, 2000), DR, DT)
                else:
                    _, t1, x, s, tm = pol
                    if k == "GATE": go = S.sol[S.bu & (S.dcc <= t1)].sum() >= x
                    else: go = float(S.val_q(S.q_at(t1))) >= 1 + x
                    t = ride_from(S, t1, s, tm) if go else t1
                    v = S.land_val(t, DR)
                M[a, b] = (v - 1) * S.cost
        G[fol] = M
    kinds = np.array([p["kind"] for p in O]); days = np.array([p["day"] for p in O])
    P("\n# (2) Early-flow gate exits on OUR fills (exact replay, MEASURED delays, curve P&L SOL)")
    for kind, base in (("ps", 0), ("reg", 1)):
        mk = kinds == kind; dl = sorted(set(days[mk].tolist()))
        tot = G[1.0][:, mk].sum(1); o = np.argsort(-tot)
        P(f"\n## {kind} ({mk.sum()} fills): wave baseline {grid[base]} {tot[base]:+.3f} (0.9 fol {G[0.9][base, mk].sum():+.3f}); top 8 in-sample:")
        for a in o[:8]: P(f"- {grid[a]} {tot[a]:+.3f} (0.9 fol {G[0.9][a, mk].sum():+.3f}); per day " + " ".join(f"D{d} {G[1.0][a, mk & (days == d)].sum():+.3f}" for d in dl))
        P(f"\n### {kind}: WALK-FORWARD (gate parameters chosen on all earlier days; full followers)")
        P("| test day | fills | chosen | test | wave | gain | test 0.9 fol | wave 0.9 fol |"); P("|---|---|---|---|---|---|---|---|")
        W = np.zeros(4)
        for d in dl:
            tr = mk & (days < d); te = mk & (days == d)
            if tr.sum() < 40: continue
            cand = [a for a, g in enumerate(grid) if g[0] in ("GATE", "GATEV")]
            a = max(cand, key=lambda i: G[1.0][i, tr].sum())
            r = (G[1.0][a, te].sum(), G[1.0][base, te].sum(), G[0.9][a, te].sum(), G[0.9][base, te].sum()); W += r
            P(f"| D{d} | {te.sum()} | {grid[a]} | {r[0]:+.3f} | {r[1]:+.3f} | {r[0] - r[1]:+.3f} | {r[2]:+.3f} | {r[3]:+.3f} |")
        P(f"| total | | | {W[0]:+.3f} | {W[1]:+.3f} | {W[0] - W[1]:+.3f} | {W[2]:+.3f} | {W[3]:+.3f} |")
    open(f"{OUT}/s9.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

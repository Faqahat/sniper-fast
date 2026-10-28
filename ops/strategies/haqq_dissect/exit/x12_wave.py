#!/usr/bin/env python3
"""EXIT step 12 (read-only): 'wave' exits on OUR live fills (exact replay from actual entries, xsim, MEASURED delays), vs MS200/T1/CUR:
  STALL S tmax   after the first outside buy following our buy, sell once no outside buy has landed for S ms (decision at last
                 buy + S, our clock; lands after the reactive delay); else at tmax (MS)
  NTH k tmax     sell on the k-th outside buy after ours (reactive); else at tmax
  RIDE t1 S tmax at t1 ms after our buy: if an outside buy landed in the last S ms keep holding until a gap of S ms or tmax;
                 else sell at t1 (haqq-like 'ride the wave to its end')
  MSTP t tp      MS t, but sell at once if value >= 1+tp before (reactive)
  MSSL t sl      MS t, but sell at once if value <= 1-sl before
Out: haqq_dissect/exit/x12.txt"""
import pickle, sys, itertools
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
from xsim import Pos
from x7_ourexits import delays, evaluate as ev7
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def pols():
    L = [("CUR",), ("T", 1), ("MS", 150), ("MS", 200), ("MS", 250), ("MS", 300)]
    L += [("STALL", s, t) for s in (50, 100, 150, 200, 300) for t in (200, 300, 500, 1000)]
    L += [("NTH", k, t) for k in (1, 2, 3, 5) for t in (200, 300, 500)]
    L += [("RIDE", t1, s, t) for t1 in (150, 200) for s in (50, 100, 150) for t in (400, 700, 1000)]
    L += [("MSTP", t, tp) for t in (200, 300) for tp in (0.03, 0.05, 0.10)]
    L += [("MSSL", t, sl) for t in (200, 300) for sl in (0.03, 0.05, 0.10)]
    return L


def ev(S, pol, DR, DT):
    k = pol[0]
    if S.n == 0: return S.v_pre
    if k in ("CUR", "T"): return ev7(S, pol, DR, DT)[0]
    if k == "MS": return S.land_val(pol[1], DR)
    bt = S.dcc[S.bu]
    if k == "STALL":
        _, s, t = pol
        if len(bt) == 0: return S.land_val(t, DR)
        gaps = np.diff(np.concatenate([bt, [np.inf]]))
        j = np.argmax(gaps >= s); tt = bt[j] + s
        return S.land_val(min(tt, t), DR)
    if k == "NTH":
        _, n, t = pol
        if len(bt) >= n and bt[n - 1] < t: return S.land_val(bt[n - 1], DR)
        return S.land_val(t, DR)
    if k == "RIDE":
        _, t1, s, t = pol
        rec = bt[(bt <= t1) & (bt > t1 - s)]
        if not len(rec): return S.land_val(t1, DR)
        later = bt[bt > t1 - s]
        gaps = np.diff(np.concatenate([later, [np.inf]]))
        j = np.argmax(gaps >= s); tt = max(later[j] + s, t1)
        return S.land_val(min(tt, t), DR)
    if k in ("MSTP", "MSSL"):
        _, t, x = pol
        m = (S.v >= 1 + x) if k == "MSTP" else (S.v <= 1 - x)
        j = S.first(m)
        if j is not None and S.dcc[j] < t: return S.land_val(S.dcc[j], DR)
        return S.land_val(t, DR)
    raise ValueError(pol)


def main():
    O = pickle.load(open(f"{X.OUT}/ourpaths.pkl", "rb"))
    DR, DT, nd = delays()
    PL = pols(); G = {}
    for fol in (1.0, 0.9):
        M = np.zeros((len(PL), len(O)))
        for b, p in enumerate(O):
            S = Pos(p, fol)
            for a, pol in enumerate(PL): M[a, b] = (ev(S, pol, DR, DT) - 1) * S.cost
        G[fol] = M
    kinds = np.array([p["kind"] for p in O]); days = np.array([p["day"] for p in O])
    P("# Wave exits on OUR live fills (exact replay, actual entries, MEASURED delays), curve P&L SOL: full followers / 10% fewer")
    for kind in ("ps", "reg"):
        mk = kinds == kind; dl = sorted(set(days[mk].tolist()))
        P(f"\n## {kind} ({mk.sum()} fills)")
        P("| policy | all | all 0.9 | " + " | ".join(f"D{d}" for d in dl) + " |"); P("|---|---|---|" + "---|" * len(dl))
        o = np.argsort(-G[1.0][:, mk].sum(1))
        for a in list(o[:25]) + [PL.index(("CUR",))]:
            P(f"| {PL[a]} | {G[1.0][a, mk].sum():+.3f} | {G[0.9][a, mk].sum():+.3f} | " + " | ".join(f"{G[1.0][a, mk & (days == d)].sum():+.3f}" for d in dl) + " |")
    open(f"{X.OUT}/x12.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""EXIT step 17 (read-only): 'hold longer while the wave runs / sell into strength' on OUR live fills (exact replay from actual
entries, MEASURED delays), including haqq-scale gaps and caps:
  RIDE t1 S tmax [tp]  at t1 ms after our buy: if an outside buy landed in the last S ms, hold until a gap of S ms with no outside
                       buy, or tmax; else sell at t1. Optional tp: sell at once (reactive) when value >= 1+tp.
  RIDEP t1 S tmax x    as RIDE, but keep holding past t1 only if value >= 1+x at t1 (hold winners only)
Out: haqq_dissect/exit/x17.txt"""
import pickle, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev as ev12
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def ride_t(S, t1, s, tmax):
    bt = S.dcc[S.bu]
    rec = bt[(bt <= t1) & (bt > t1 - s)]
    if not len(rec): return t1
    later = bt[bt > t1 - s]; gaps = np.diff(np.concatenate([later, [np.inf]])); j = int(np.argmax(gaps >= s))
    return min(max(later[j] + s, t1), tmax)


def ev(S, pol, DR, DT):
    if pol[0] not in ("RIDE2", "RIDEP"): return ev12(S, pol, DR, DT)
    if S.n == 0: return S.v_pre
    if pol[0] == "RIDE2":
        _, t1, s, tmax, tp = pol; tt = ride_t(S, t1, s, tmax)
    else:
        _, t1, s, tmax, x = pol; tp = None
        q = S.q_at(t1); v1 = float(S.val_q(q))
        tt = ride_t(S, t1, s, tmax) if v1 >= 1 + x else t1
    if tp is not None:
        j = S.first(S.v >= 1 + tp)
        if j is not None and S.dcc[j] < tt: return S.land_val(S.dcc[j], DR)
    return S.land_val(tt, DR)


def main():
    O = pickle.load(open(f"{X.OUT}/ourpaths.pkl", "rb"))
    DR, DT, nd = delays()
    PL = [("CUR",), ("MS", 200), ("RIDE", 150, 150, 700)]
    PL += [("RIDE2", t1, s, tm, tp) for t1 in (150, 200, 400) for s in (150, 300, 500, 1000) for tm in (1000, 2000, 5000, 10000, 20000) for tp in (None, 0.25)]
    PL += [("RIDEP", t1, s, tm, x) for t1 in (150, 200) for s in (150, 300, 1000) for tm in (1000, 5000) for x in (0.0, 0.03, 0.05, 0.10)]
    G = {}
    for fol in (1.0, 0.9):
        M = np.zeros((len(PL), len(O)))
        for b, p in enumerate(O):
            S = Pos(p, fol)
            for a, pol in enumerate(PL): M[a, b] = (ev(S, pol, DR, DT) - 1) * S.cost
        G[fol] = M
    kinds = np.array([p["kind"] for p in O]); days = np.array([p["day"] for p in O])
    P("# Hold-longer / sell-into-strength exits on OUR live fills (exact replay, actual entries, MEASURED delays), curve P&L SOL")
    for kind in ("ps", "reg"):
        mk = kinds == kind; dl = sorted(set(days[mk].tolist()))
        P(f"\n## {kind} ({mk.sum()} fills): top 15 + reference rows (full followers; 0.9 = 10% fewer followers)")
        P("| policy | all | all 0.9 | " + " | ".join(f"D{d}" for d in dl) + " |"); P("|---|---|---|" + "---|" * len(dl))
        o = list(np.argsort(-G[1.0][:, mk].sum(1))[:15])
        ref = [PL.index(x) for x in (("CUR",), ("MS", 200), ("RIDE", 150, 150, 700), ("RIDE2", 200, 1000, 20000, None), ("RIDE2", 200, 1000, 20000, 0.25), ("RIDE2", 200, 500, 5000, None), ("RIDE2", 400, 300, 5000, None))]
        for a in o + [r for r in ref if r not in o]:
            P(f"| {PL[a]} | {G[1.0][a, mk].sum():+.3f} | {G[0.9][a, mk].sum():+.3f} | " + " | ".join(f"{G[1.0][a, mk & (days == d)].sum():+.3f}" for d in dl) + " |")
    open(f"{X.OUT}/x17.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

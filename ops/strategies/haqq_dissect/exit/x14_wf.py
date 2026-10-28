#!/usr/bin/env python3
"""EXIT step 14 (read-only): final walk-forward of exit policies on OUR live fills (exact replay from actual entries, MEASURED
delays). Candidate set: CUR, T1, T2, MS t, STALL, RIDE (x9/x12 definitions). The policy for test day D is chosen on ALL our fills
(both kinds) of days < D at full followers; reported per kind on D at full and 10% fewer followers, with a 90% bootstrap of the
gain vs CUR. Also the fixed RIDE(150,150,700) / MS200 vs CUR per day and per server.
Out: haqq_dissect/exit/x14.txt"""
import pickle, sys
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
from xsim import Pos
from x7_ourexits import delays
from x12_wave import ev
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def boot(d, n=2000, seed=3):
    d = np.asarray(d); g = np.random.default_rng(seed)
    s = np.array([d[g.integers(0, len(d), len(d))].sum() for _ in range(n)]) if len(d) else np.zeros(1)
    return d.sum(), np.percentile(s, 5), np.percentile(s, 95)


def main():
    O = pickle.load(open(f"{X.OUT}/ourpaths.pkl", "rb"))
    DR, DT, nd = delays()
    PL = [("CUR",), ("T", 1), ("T", 2)] + [("MS", t) for t in (100, 150, 200, 250, 300, 400)]
    PL += [("STALL", s, t) for s in (100, 150, 200, 300) for t in (300, 500, 1000)]
    PL += [("RIDE", t1, s, t) for t1 in (150, 200) for s in (100, 150) for t in (400, 700, 1000)]
    G = {}
    for fol in (1.0, 0.9):
        M = np.zeros((len(PL), len(O)))
        for b, p in enumerate(O):
            S = Pos(p, fol)
            for a, pol in enumerate(PL): M[a, b] = (ev(S, pol, DR, DT) - 1) * S.cost
        G[fol] = M
    kinds = np.array([p["kind"] for p in O]); days = np.array([p["day"] for p in O]); srv = np.array([p["srv"] for p in O])
    real = np.array([p["realized"] for p in O]); ci = 0
    P("# Exit policy walk-forward on OUR live fills (curve P&L SOL; buy/sell tx costs identical across policies, excluded)")
    P("Chosen on all our fills (both kinds) of earlier days at full followers; tested per kind. Gain = chosen - CUR, 90% bootstrap over fills.")
    P("| test day | chosen | kind | fills | realized | CUR full | chosen full | gain full [90%] | CUR 0.9 | chosen 0.9 | gain 0.9 [90%] |")
    P("|---|---|---|---|---|---|---|---|---|---|---|")
    T = {k: [[], []] for k in ("ps", "reg")}
    for d in sorted(set(days.tolist())):
        tr = days < d
        if tr.sum() < 100: continue
        a = int(np.argmax(G[1.0][:, tr].sum(1)))
        for kind in ("ps", "reg"):
            te = (days == d) & (kinds == kind)
            if te.sum() == 0: continue
            g1 = G[1.0][a, te] - G[1.0][ci, te]; g9 = G[0.9][a, te] - G[0.9][ci, te]
            T[kind][0] += list(g1); T[kind][1] += list(g9)
            s1, l1, h1 = boot(g1); s9, l9, h9 = boot(g9)
            P(f"| D{d} | {PL[a]} | {kind} | {te.sum()} | {real[te].sum():+.3f} | {G[1.0][ci, te].sum():+.3f} | {G[1.0][a, te].sum():+.3f} | {s1:+.3f} [{l1:+.3f}..{h1:+.3f}] | {G[0.9][ci, te].sum():+.3f} | {G[0.9][a, te].sum():+.3f} | {s9:+.3f} [{l9:+.3f}..{h9:+.3f}] |")
    for kind in ("ps", "reg"):
        s1, l1, h1 = boot(T[kind][0]); s9, l9, h9 = boot(T[kind][1])
        P(f"- {kind} walk-forward total gain vs CUR: full {s1:+.3f} [{l1:+.3f}..{h1:+.3f}] over {len(T[kind][0])} test fills ({1000 * s1 / max(len(T[kind][0]), 1):+.2f} mSOL/fill); 0.9 followers {s9:+.3f} [{l9:+.3f}..{h9:+.3f}]")
    P("\n## Fixed policies vs CUR per day (no selection; RIDE(150,150,700) and MS200 picked on x9/x12 pooled results - in-sample for orientation)")
    for pol in (("MS", 200), ("RIDE", 150, 150, 700), ("T", 1)):
        a = PL.index(pol)
        for kind in ("ps", "reg"):
            mk = kinds == kind; dl = sorted(set(days[mk].tolist()))
            cells = []
            for d in dl:
                te = mk & (days == d); s, lo, hi = boot(G[1.0][a, te] - G[1.0][ci, te])
                cells.append(f"D{d} {s:+.3f} [{lo:+.2f}..{hi:+.2f}]")
            s9 = (G[0.9][a, mk] - G[0.9][ci, mk]).sum()
            P(f"- {pol} {kind}: " + "; ".join(cells) + f"; all 0.9 fol {s9:+.3f}")
        for s_ in ("FRA", "AMS"):
            for kind in ("ps", "reg"):
                m = (srv == s_) & (kinds == kind)
                if m.sum() < 30: continue
                P(f"  - {s_} {kind} ({m.sum()} fills): CUR {G[1.0][ci, m].sum():+.3f}, {pol} {G[1.0][a, m].sum():+.3f}")
    open(f"{X.OUT}/x14.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

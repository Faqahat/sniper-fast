#!/usr/bin/env python3
"""EXIT step 9 (read-only): fine exit timing on OUR live fills (exact replay from the actual entries, xsim) - the hold that
maximises curve P&L, with bootstrap ranges, per day, per server, walk-forward, 10% fewer followers.
New policies:
  MS t     the sell is decided t ms after our buy landed (chain clock) and lands after our MEASURED reactive delay
           (decision at our buy's landing + t, as a reactive sell triggered by our own fill)
  FBMS     first outside buy >= X SOL after our buy (reactive), else MS t
  HQ*      haqq-like, from x5/x8: nothing before slot entry+2; then TP +x (reactive), else a timer N (his menu centre)
Profile: mean value / cost if sold at exactly t ms after our buy (no delay), per kind - where the bounce peaks.
Out: haqq_dissect/exit/x9.txt, x9_grid.pkl"""
import pickle, sys, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
from xsim import Pos, QS
from x7_ourexits import delays, evaluate as ev7
SELL_TX = 0.0018
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def policies():
    L = [("CUR",), ("T", 1), ("T", 2), ("T", 3), ("T", 5)]
    L += [("MS", t) for t in (0, 25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500, 700, 1000, 1500)]
    L += [("FBMS", x, t) for x in (0.25, 0.5, 1.0, 2.0) for t in (100, 200, 300, 500)]
    L += [("HQ2", x, n) for x in (0.05, 0.10, 0.20) for n in (8, 15, 25)]
    return L


def evaluate(S, pol, DR, DT):
    k = pol[0]
    if S.n == 0: return S.v_pre, 0
    if k in ("CUR", "T"): return ev7(S, pol, DR, DT)
    if k == "MS": return S.land_val(pol[1], DR), 0
    if k == "FBMS":
        _, x, t = pol; j = S.first(S.bu & (S.sol >= x))
        if j is not None and S.dcc[j] < t: return S.land_val(S.dcc[j], DR), 0
        return S.land_val(t, DR), 0
    if k == "HQ2":
        _, x, n = pol; t2 = S.slot_start(2); tn = S.slot_start(n)
        j = S.first(S.v >= 1 + x)
        if j is not None and S.dcc[j] < tn: return S.land_val(max(S.dcc[j], t2 - 60), DR), 0
        return S.timer_val(n, DT[S.p["kind"]]), 0
    raise ValueError(pol)


def boot_diff(a, b, n=2000, seed=3):
    d = np.asarray(a) - np.asarray(b); g = np.random.default_rng(seed)
    s = np.array([d[g.integers(0, len(d), len(d))].sum() for _ in range(n)])
    return d.sum(), np.percentile(s, 5), np.percentile(s, 95)


def main():
    t0 = time.time()
    O = pickle.load(open(f"{X.OUT}/ourpaths.pkl", "rb"))
    DR, DT, nd = delays()
    pols = policies()
    G = {}
    prof = {k: collections.defaultdict(list) for k in ("ps", "reg")}
    TT = (0, 25, 50, 75, 100, 150, 200, 250, 300, 400, 500, 700, 1000, 1500, 2000, 3000)
    for fol in (1.0, 0.9):
        M = np.zeros((len(pols), len(O)))
        for b, p in enumerate(O):
            S = Pos(p, fol)
            for a, pol in enumerate(pols):
                v, extra = evaluate(S, pol, DR, DT)
                M[a, b] = (v - 1) * S.cost - extra * SELL_TX
            if fol == 1.0:
                for t in TT: prof[p["kind"]][t].append(float(S.val_q(S.q_at(t))) - 1)
        G[fol] = M
    print(f"grid done ({time.time() - t0:.0f}s)", flush=True)
    kinds = np.array([p["kind"] for p in O]); days = np.array([p["day"] for p in O]); srv = np.array([p["srv"] for p in O])
    real = np.array([p["realized"] for p in O])
    pickle.dump(dict(pols=pols, G=G, kinds=kinds, days=days, srv=srv, real=real), open(f"{X.OUT}/x9_grid.pkl", "wb"))
    P("# Fine exit timing on OUR live fills (exact replay, actual entries, MEASURED delays), curve P&L SOL (tx costs equal across rows)")
    P("\n## Value profile: mean (value/cost - 1) if sold exactly t ms after our buy landed (no delay), MEASURED tape, full followers")
    P("| t ms | " + " | ".join(str(t) for t in TT) + " |"); P("|---|" + "---|" * len(TT))
    for k in ("ps", "reg"):
        P(f"| {k} | " + " | ".join(f"{100 * np.mean(prof[k][t]):+.2f}%" for t in TT) + " |")
    ci = pols.index(("CUR",))
    for kind in ("ps", "reg"):
        mk = kinds == kind; dl = sorted(set(days[mk].tolist()))
        P(f"\n## {kind} ({mk.sum()} fills): policy x day, SOL (full followers / 10% fewer)")
        P("| policy | all | all 0.9 | " + " | ".join(f"D{d} ({(mk & (days == d)).sum()})" for d in dl) + " |"); P("|---|---|---|" + "---|" * len(dl))
        for a, pol in enumerate(pols):
            P(f"| {pol} | {G[1.0][a, mk].sum():+.3f} | {G[0.9][a, mk].sum():+.3f} | " + " | ".join(f"{G[1.0][a, mk & (days == d)].sum():+.3f} / {G[0.9][a, mk & (days == d)].sum():+.3f}" for d in dl) + " |")
        P(f"\n### {kind}: best fixed policies vs CUR, gain with 90% bootstrap range, per day")
        for pol in (("T", 1), ("MS", 150), ("MS", 200), ("MS", 250)):
            a = pols.index(pol)
            s, lo, hi = boot_diff(G[1.0][a, mk], G[1.0][ci, mk]); s9, lo9, hi9 = boot_diff(G[0.9][a, mk], G[0.9][ci, mk])
            P(f"- {pol} - CUR: all {s:+.3f} [{lo:+.3f}..{hi:+.3f}]; 0.9 fol {s9:+.3f} [{lo9:+.3f}..{hi9:+.3f}]; per day " +
              ", ".join(f"D{d} {boot_diff(G[1.0][a, mk & (days == d)], G[1.0][ci, mk & (days == d)])[0]:+.3f}" for d in dl) +
              f"; days positive {sum(boot_diff(G[1.0][a, mk & (days == d)], G[1.0][ci, mk & (days == d)])[0] > 0 for d in dl)}/{len(dl)}")
        for s_ in ("FRA", "AMS"):
            m = mk & (srv == s_)
            if m.sum() < 30: continue
            a = pols.index(("T", 1)); b = pols.index(("MS", 200))
            P(f"- server {s_} ({m.sum()} fills): CUR {G[1.0][ci, m].sum():+.3f}, T1 {G[1.0][a, m].sum():+.3f}, MS200 {G[1.0][b, m].sum():+.3f}")
    # walk-forward, training on BOTH kinds (exit dynamics shared), earlier days; families T / MS / FBMS / HQ2
    P("\n## WALK-FORWARD: policy chosen on ALL our earlier fills (both kinds, days < D, full followers), tested on day D per kind")
    P("| test day | chosen | ps test full / 0.9 | ps CUR full / 0.9 | reg test full / 0.9 | reg CUR full / 0.9 |"); P("|---|---|---|---|---|---|")
    tot = np.zeros(8)
    for d in sorted(set(days.tolist())):
        tr = days < d
        if tr.sum() < 100: continue
        a = int(np.argmax(G[1.0][:, tr].sum(1)))
        r = []
        for kind in ("ps", "reg"):
            te = (days == d) & (kinds == kind)
            r += [G[1.0][a, te].sum(), G[0.9][a, te].sum(), G[1.0][ci, te].sum(), G[0.9][ci, te].sum()]
        tot += np.array(r)
        P(f"| D{d} | {pols[a]} | {r[0]:+.3f} / {r[1]:+.3f} | {r[2]:+.3f} / {r[3]:+.3f} | {r[4]:+.3f} / {r[5]:+.3f} | {r[6]:+.3f} / {r[7]:+.3f} |")
    P(f"| total | | {tot[0]:+.3f} / {tot[1]:+.3f} | {tot[2]:+.3f} / {tot[3]:+.3f} | {tot[4]:+.3f} / {tot[5]:+.3f} | {tot[6]:+.3f} / {tot[7]:+.3f} |")
    open(f"{X.OUT}/x9.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

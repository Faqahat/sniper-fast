#!/usr/bin/env python3
"""EXIT step 7 (read-only): alternative exits replayed on OUR live fills from their ACTUAL entries (ourpaths.pkl), exact curve
model (xsim), our MEASURED sell landing delays (x3), per day, walk-forward, and with 10% fewer followers.
Policies (N = timer: the sell is decided at the start of slot entry+N, as the pre-send time limit):
  CUR    the live exit (pre-send: TP +10% / SL -20% / N=2; regular: the run's hold (decided at slot entry+hold-1) and SL)
  T      timer N
  TS     take-profit tp / stop-loss sl (reactive, on the replayed value) / timer N
  FB     sell at the first outside buy >= X SOL after our buy (reactive) / timer N
  FBP    first outside buy >= X SOL that leaves our value >= 1+x / timer N
  FBTS   earliest of FB(X), TP tp, SL sl, timer N
  HALF   half at FB(X) (else at timer N1), the rest at timer N2 (exact sequential, +1 sell tx)
  TR     trailing: once value >= 1+a, sell when value <= best - z / timer N
  HQ     haqq-like: no sell before slot entry+2; sell when value >= 1+x (x decays: x0 until slot 5, x1 until slot 10) / timer N
P&L per fill = (exit value - 1) x cost - extra sell txs x 1.8 mSOL (MEASURED sell tx cost); buy and first-sell tx costs are the
same for every policy and are NOT included (curve P&L, as the dv8 calibration rows).
Out: haqq_dissect/exit/x7.txt, x7_grid.pkl"""
import pickle, sys, itertools, collections, time
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
from xsim import Pos, QS
SELL_TX = 0.0018
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)


def delays():
    S = pickle.load(open(f"{X.OUT}/sellland.pkl", "rb"))
    dr = [r["react_ms"] for r in S if r.get("react_ms") is not None]
    dps = [r["timer_ms"] for r in S if r["kind"] == "ps" and r.get("timer_ms") is not None and 0 <= (r.get("timer_slots") or -1) <= 3]
    dreg = [r["timer_ms"] for r in S if r["kind"] == "reg" and r.get("timer_ms") is not None and 0 <= (r.get("timer_slots") or -1) <= 3]
    return np.percentile(dr, QS), {"ps": np.percentile(dps, QS), "reg": np.percentile(dreg, QS)}, (len(dr), len(dps), len(dreg))


def policies():
    L = [("CUR",)]
    L += [("T", n) for n in (1, 2, 3, 4, 5, 6, 8, 10, 12, 15, 20, 30)]
    for tp, sl, n in itertools.product((0.03, 0.05, 0.075, 0.10, 0.15, 0.20, 0.30, None), (0.05, 0.10, 0.20, None), (1, 2, 3, 4, 5, 6, 8, 10, 15, 20)):
        if tp is None and sl is None: continue
        L.append(("TS", tp, sl, n))
    for x, n in itertools.product((0.1, 0.25, 0.5, 1.0, 2.0, 3.0), (2, 3, 5, 8, 10, 15, 20)): L.append(("FB", x, n))
    for x, r, n in itertools.product((0.25, 0.5, 1.0, 2.0), (0.0, 0.03, 0.05, 0.10), (2, 3, 5, 8, 10, 15)): L.append(("FBP", x, r, n))
    for x, tp, sl, n in itertools.product((0.5, 1.0, 2.0), (0.10, 0.20, None), (0.10, 0.20, None), (2, 3, 5, 8, 10)): L.append(("FBTS", x, tp, sl, n))
    for x, n1, n2 in itertools.product((0.25, 0.5, 1.0, 2.0), (2, 3, 5), (5, 8, 10, 15, 20)):
        if n2 > n1: L.append(("HALF", x, n1, n2))
    for a, z, n in itertools.product((0.05, 0.10, 0.20), (0.03, 0.05, 0.10), (3, 5, 8, 10, 15)): L.append(("TR", a, z, n))
    for x0, x1, n in itertools.product((0.05, 0.10, 0.20), (0.03, 0.05, 0.10), (8, 10, 15, 20, 30)): L.append(("HQ", x0, x1, n))
    return L


def evaluate(S, pol, DR, DT):
    """exit value ratio and extra sells for position S (Pos) under policy pol"""
    p = S.p; k = pol[0]; dt = DT[p["kind"]]
    if S.n == 0: return S.v_pre, 0
    def react_or_timer(j, N):
        tN = S.slot_start(N)
        if j is not None and S.dcc[j] < tN: return S.land_val(S.dcc[j], DR)
        return S.timer_val(N, dt)
    if k == "CUR":
        if p["kind"] == "ps": tp, sl, N = p["tp"] or 0.10, p["sl"] or 0.20, p["hold"] or 2
        else: tp, sl, N = (p["tp"] if p["tp"] and p["tp"] < 9 else None), p["sl"], (p["hold"] or 5) - 1
        m = np.zeros(S.n, bool)
        if tp: m |= S.v >= 1 + tp
        if sl: m |= S.v <= 1 - sl
        return react_or_timer(S.first(m), N), 0
    if k == "T": return S.timer_val(pol[1], dt), 0
    if k == "TS":
        _, tp, sl, N = pol; m = np.zeros(S.n, bool)
        if tp is not None: m |= S.v >= 1 + tp
        if sl is not None: m |= S.v <= 1 - sl
        return react_or_timer(S.first(m), N), 0
    if k == "FB":
        _, x, N = pol; return react_or_timer(S.first(S.bu & (S.sol >= x)), N), 0
    if k == "FBP":
        _, x, r, N = pol; return react_or_timer(S.first(S.bu & (S.sol >= x) & (S.v >= 1 + r)), N), 0
    if k == "FBTS":
        _, x, tp, sl, N = pol; m = S.bu & (S.sol >= x)
        if tp is not None: m |= S.v >= 1 + tp
        if sl is not None: m |= S.v <= 1 - sl
        return react_or_timer(S.first(m), N), 0
    if k == "HALF":
        _, x, n1, n2 = pol; j = S.first(S.bu & (S.sol >= x)); t1 = S.slot_start(n1); t2 = S.slot_start(n2)
        vals = []
        for i in range(len(DR)):
            a = S.dcc[j] + DR[i] if (j is not None and S.dcc[j] < t1) else t1 + dt[i]
            b = max(t2 + dt[i], a + 1)
            vals.append(S.partial_exact([(a, 0.5), (b, 0.5)]))
        return float(np.mean(vals)), 1
    if k == "TR":
        _, a, z, N = pol; m = (S.vmax >= 1 + a) & (S.v <= S.vmax - z)
        return react_or_timer(S.first(m), N), 0
    if k == "HQ":
        _, x0, x1, N = pol
        t2 = S.slot_start(2); t5 = S.slot_start(5); t10 = S.slot_start(10)
        thr = np.where(S.dcc < t5, 1 + x0, np.where(S.dcc < t10, 1 + x1, 1 + x1 / 2))
        j = S.first(S.v >= thr)
        if j is not None and S.dcc[j] < t2:
            # signal before the minimum hold: sell at slot entry+2 if the value is still above the threshold there
            return S.timer_val(2, dt), 0
        return react_or_timer(j, N), 0
    raise ValueError(pol)


def main():
    t0 = time.time()
    O = pickle.load(open(f"{X.OUT}/ourpaths.pkl", "rb"))
    DR, DT, nd = delays()
    P("# Alternative exits on OUR live fills (exact replay from the actual entries), MEASURED delays, curve P&L")
    P(f"reactive sell delay quantiles {QS} (ms, n={nd[0]}): " + " ".join(f"{x:.0f}" for x in DR))
    P(f"timer sell: ms after the decision slot's start, pre-send (n={nd[1]}): " + " ".join(f"{x:.0f}" for x in DT['ps']) + f"; regular (n={nd[2]}): " + " ".join(f"{x:.0f}" for x in DT['reg']))
    pols = policies()
    G = {}
    for fol in (1.0, 0.9):
        M = np.zeros((len(pols), len(O)))
        for b, p in enumerate(O):
            S = Pos(p, fol)
            for a, pol in enumerate(pols):
                v, extra = evaluate(S, pol, DR, DT)
                M[a, b] = (v - 1) * S.cost - extra * SELL_TX
        G[fol] = M
        print(f"fol {fol} done ({time.time() - t0:.0f}s)", flush=True)
    # validation: actual exit position replay vs realized
    act = []
    for p in O:
        S = Pos(p, 1.0)
        if p["nsell"] == 1:
            q = p["sell_rows_before"] - 1; act.append((p["kind"], p["day"], p["realized"], (float(S.val_q(q)) - 1) * S.cost))
    pickle.dump(dict(pols=pols, G=G, meta=[dict(kind=p["kind"], day=p["day"], run=p["run"], realized=p["realized"], cost=p["cost"], why=p["why"]) for p in O]), open(f"{X.OUT}/x7_grid.pkl", "wb"))
    P("\n## Validation (single-sell fills): replay with the sell at its ACTUAL tape position vs realized (MEASURED)")
    for kind in ("ps", "reg"):
        v = [x for x in act if x[0] == kind]
        P(f"- {kind}: n {len(v)}, realized {sum(x[2] for x in v):+.3f} SOL, replay {sum(x[3] for x in v):+.3f}, mean gap {1000 * np.mean([x[2] - x[3] for x in v]):+.3f} mSOL/fill")
    meta = [(p["kind"], p["day"]) for p in O]
    kinds = np.array([m[0] for m in meta]); days = np.array([m[1] for m in meta]); real = np.array([p["realized"] for p in O])
    ci = pols.index(("CUR",))
    for kind in ("ps", "reg"):
        mk = kinds == kind; dl = sorted(set(days[mk].tolist()))
        P(f"\n## {kind}: CUR modelled (our measured delays) vs realized, SOL per day (curve P&L, tx costs excluded)")
        P("| day | fills | realized | CUR modelled | CUR at 0.9 followers |"); P("|---|---|---|---|---|")
        for d in dl:
            m = mk & (days == d)
            P(f"| D{d} {X.pkt(X.DAY0 + d * 86400)[:5]} | {m.sum()} | {real[m].sum():+.3f} | {G[1.0][ci, m].sum():+.3f} | {G[0.9][ci, m].sum():+.3f} |")
        # in-sample ranking
        tot = G[1.0][:, mk].sum(1); tot9 = G[0.9][:, mk].sum(1)
        o = np.argsort(-tot)
        P(f"\n### {kind}: top 15 policies, all days pooled (IN-SAMPLE, for orientation only), SOL; CUR = {tot[ci]:+.3f} (0.9: {tot9[ci]:+.3f})")
        P("| policy | all days | 0.9 followers | " + " | ".join(f"D{d}" for d in dl) + " |"); P("|---|---|---|" + "---|" * len(dl))
        for a in o[:15]:
            P(f"| {pols[a]} | {tot[a]:+.3f} | {tot9[a]:+.3f} | " + " | ".join(f"{G[1.0][a, mk & (days == d)].sum():+.3f}" for d in dl) + " |")
        # best per family
        P(f"\n### {kind}: best policy per family (in-sample)")
        fam = collections.defaultdict(list)
        for a, pol in enumerate(pols): fam[pol[0]].append(a)
        for f, idx in fam.items():
            a = max(idx, key=lambda i: tot[i])
            P(f"- {f}: {pols[a]} {tot[a]:+.3f} (0.9: {tot9[a]:+.3f}); per day " + ", ".join(f"D{d} {G[1.0][a, mk & (days == d)].sum():+.3f}" for d in dl))
        # walk-forward: choose on all earlier days (fol 1.0), test on day d
        P(f"\n### {kind}: WALK-FORWARD (policy chosen on all earlier days at full followers; tested on the day), SOL")
        P("| test day | fills | chosen policy | test full | test 0.9 fol | CUR full | CUR 0.9 | realized | gain vs CUR (full / 0.9) |"); P("|---|---|---|---|---|---|---|---|---|")
        wf = []
        for d in dl[1:]:
            tr = mk & (days < d); te = mk & (days == d)
            if tr.sum() < 40: continue
            a = int(np.argmax(G[1.0][:, tr].sum(1)))
            r = (G[1.0][a, te].sum(), G[0.9][a, te].sum(), G[1.0][ci, te].sum(), G[0.9][ci, te].sum())
            wf.append(r)
            P(f"| D{d} | {te.sum()} | {pols[a]} | {r[0]:+.3f} | {r[1]:+.3f} | {r[2]:+.3f} | {r[3]:+.3f} | {real[te].sum():+.3f} | {r[0] - r[2]:+.3f} / {r[1] - r[3]:+.3f} |")
        if wf:
            w = np.array(wf).sum(0); P(f"| total | | | {w[0]:+.3f} | {w[1]:+.3f} | {w[2]:+.3f} | {w[3]:+.3f} | | {w[0] - w[2]:+.3f} / {w[1] - w[3]:+.3f} |")
    open(f"{X.OUT}/x7.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

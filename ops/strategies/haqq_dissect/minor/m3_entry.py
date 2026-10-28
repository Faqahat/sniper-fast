#!/usr/bin/env python3
"""MINOR step 3 (read-only): explicit entry rules for the dump-reactive minor bots on the dv8 dump universe
(dv8/uni.npz: outside sell drop >= 5 %, sell >= 0.5 SOL, curve > 30.52, age <= 30 min; usable hours; non-mayhem), features from
analyst F's bots/b2.npz (28 causal market features + leader client + haqq's own open lots per code = SIBLING state).
Label y_c = code c bought this dump (a code-c lot whose biggest preceding outside drop is this dump, <= LAG slots after it).
Rule = greedy conjunction of <= 4 thresholds (feature >= t or <= t, t on train quantiles) maximising F1 on TRAIN days D0-D2;
evaluated once on held-out D3-D5 (precision, recall per day). Two feature sets: MARKET (what we can see) and +SIB (adds his own open
lots per code; known to his system, visible to us only after his buys land).
Also: his real P&L on rule hits vs misses (MEASURED, code-matched lots).
Out: minor/m3.txt, minor/m3.pkl (labels + rule masks)"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/pos")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from plib import Out
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/minor"
BOTS = {226: 5, 231: 5, 244: 3, 251: 3, 249: 3, 252: 3}
TRAIN = (0, 1, 2); TEST = (3, 4, 5)


def f1(y, m):
    tp = (y & m).sum(); p = tp / max(m.sum(), 1); r = tp / max(y.sum(), 1)
    return 2 * p * r / max(p + r, 1e-9), p, r


def apply(X, names, conds):
    m = np.ones(len(X), bool)
    for n, t, s in conds:
        j = names.index(n); m &= (X[:, j] >= t) if s == ">=" else (X[:, j] <= t)
    return m


def search(X, y, names, allowed, tr, maxk=4):
    """greedy conjunction fitted on TRAIN rows only; returns (conds, rule mask over ALL rows, (F1, P, R) on train)"""
    Xt = X[tr]; yt = y[tr]
    conds = []; m = np.ones(len(Xt), bool)
    best = (0, 0, 0)
    thr = {}
    for j in allowed:
        v = Xt[:, j]; v = v[np.isfinite(v)]
        thr[j] = np.unique(np.percentile(v, np.linspace(2, 98, 25))) if len(v) else []
    for step in range(maxk):
        cand = None
        for j in allowed:
            col = Xt[:, j]
            for t in thr[j]:
                for sgn in (1, -1):
                    mm = m & ((col >= t) if sgn > 0 else (col <= t))
                    s, p, r = f1(yt, mm)
                    if s > best[0] + 0.003: best = (s, p, r); cand = (j, t, sgn, mm)
        if cand is None: break
        j, t, sgn, mm = cand; conds.append((names[j], float(t), ">=" if sgn > 0 else "<=")); m = mm
    return conds, apply(X, names, conds), best


def main():
    P = Out(f"{OUT}/m3.txt")
    Z = np.load("/home/moiz/sniper-data/haqq_dissect/bots/b2.npz")
    XF = Z["XF"].astype(np.float64); names = [str(x) for x in Z["fnames"]]; use = Z["use"]; day = Z["day"]
    U = np.load(f"{L.D}/uni.npz"); M = U["M"]
    key = {(int(m), int(s), int(i)): k for k, (m, s, i) in enumerate(zip(M["mint"], M["slot"], M["idx"]))}
    ids, idm = L.ids_map()
    lots = pickle.load(open(f"{OUT}/m2_lots.pkl", "rb"))
    N = len(M); Y = {}; YN = {}; inuni = collections.Counter(); ntot = collections.Counter()
    for l in lots:
        c = l["code"]
        if c not in BOTS or l["mayhem"]: continue
        x = l["ctx"]; ntot[c] += 1
        if not x or x.get("d_slot") is None or (x.get("d_drop") or 0) < 0.05 or x["d_slots"] > BOTS[c]: continue
        u = key.get((idm.get(l["ms"]), x["d_slot"], x["d_idx"]))
        if u is None: continue
        inuni[c] += 1
        Y.setdefault(c, np.zeros(N, bool))[u] = True
        YN.setdefault(c, np.zeros(N))[u] += l["net"]
    mk = [i for i, n in enumerate(names) if not n.startswith(("open", "prev")) and n not in ("hq_prev", "hq_open")]
    sib = list(range(len(names)))
    P("# Minor bots: explicit entry rules on the dv8 dump universe (train D0-D2, held-out test D3-D5)")
    P(f"universe usable non-mayhem dumps: {use.sum():,}; per day " + ", ".join(f"D{d} {int((use & (day == d)).sum()):,}" for d in range(7)))
    res = {}
    tr = use & np.isin(day, TRAIN); te = use & np.isin(day, TEST)
    for c in BOTS:
        if c not in Y: continue
        y = Y[c] & use
        P(f"\n## code {c}: {ntot[c]:,} lots; {inuni[c]:,} are dump-reactive lots inside the universe (<= {BOTS[c]} slots after a >=5 % dump); "
          f"bought dumps {y.sum():,} ({100 * y.sum() / use.sum():.2f}% of dumps); his net on them {YN[c][y].sum():+.2f} SOL")
        P("per day bought: " + ", ".join(f"D{d} {int((y & (day == d)).sum())}" for d in range(7)))
        for tag, allowed in (("MARKET", mk), ("+SIB", sib)):
            if y[tr].sum() < 30:
                P(f"- {tag}: too few train positives ({y[tr].sum()})"); continue
            conds, m, best = search(XF, y, names, allowed, tr)
            m = m & use
            P(f"- {tag} rule: " + " AND ".join(f"{n} {s} {t:.3g}" for n, t, s in conds))
            P(f"  train D0-D2: F1 {best[0]:.2f}, precision {100 * best[1]:.0f}%, recall {100 * best[2]:.0f}%")
            row = []
            for d in TEST:
                dd = use & (day == d)
                _, p, r = f1(y[dd], m[dd]); row.append(f"D{d} P {100 * p:.0f}% R {100 * r:.0f}% (hits {int(m[dd].sum())}, bought {int(y[dd].sum())})")
            _, p, r = f1(y[te], m[te])
            P(f"  TEST D3-D5: precision {100 * p:.0f}%, recall {100 * r:.0f}% | " + "; ".join(row))
            hit = y & m; miss = y & ~m
            P(f"  his net on bought dumps the rule catches {YN[c][hit].sum():+.2f} SOL ({int(hit.sum())}, {1000 * YN[c][hit].sum() / max(hit.sum(), 1):+.1f} mSOL) vs misses {YN[c][miss].sum():+.2f} ({int(miss.sum())}, {1000 * YN[c][miss].sum() / max(miss.sum(), 1):+.1f})")
            res[(c, tag)] = dict(conds=conds, mask=m)
    pickle.dump(dict(Y=Y, YN=YN, res=res), open(f"{OUT}/m3.pkl", "wb"))
    P.save()


if __name__ == "__main__":
    main()

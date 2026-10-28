#!/usr/bin/env python3
"""SELLID step 11 (read-only): uncertainty + per-day checks for the headline numbers.
(a) per day: share of 247/248 sells with an outside buy in the 212 ms before vs matched random moments (10/lot), and 'no outside buy
    in the last 1 s'; 90% bootstrap over lots of the ratio.
(b) known follower bots (fbots_frozen) and cohort: per-trade lift (time x size matched, s2 units) per day with a 90% bootstrap over lots.
(c) our fills: best wallet rule minus the wave exit, paired per fill, 90% bootstrap (s6_grid.pkl); his lots: timer T8 for reference.
Out: sellid/s11.txt"""
import pickle, json, sys
import numpy as np
OUT = "/home/moiz/sniper-data/haqq_dissect/sellid"
SMS = 212.0
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s, flush=True); out.append(s)


def boot_ratio(a, b, grp, n=1000, seed=3):
    """ratio of means a/b, bootstrap over groups (lots)"""
    g = np.random.default_rng(seed); ug, inv = np.unique(grp, return_inverse=True)
    A = np.bincount(inv, a); B = np.bincount(inv, b); r = []
    for _ in range(n):
        s = g.integers(0, len(ug), len(ug)); r.append(A[s].sum() / max(B[s].sum(), 1e-12))
    return np.percentile(r, 5), np.percentile(r, 95)


def main():
    Z = pickle.load(open(f"{OUT}/s1.pkl", "rb")); LOTS = Z["lots"]
    g = np.random.default_rng(7)
    rec = []
    for l in LOTS:
        if l["first_sell_k"] is None: continue
        T = l["sell_dcc"]; t0 = 2 * SMS - l["off_in_slot"]
        if T <= t0: continue
        d = l["p_dcc"].astype(np.float64); bd = d[l["p_bu"]]
        def f(t):
            pb = bd[bd < t]; return (bool(((pb >= t - 212)).any()), (t - pb[-1] if len(pb) else 1e9) > 1000)
        a = f(T); rr = [f(t) for t in g.uniform(t0, T, 10)]
        rec.append((l["code"], l["day"], l["id"], a[0], a[1], np.mean([x[0] for x in rr]), np.mean([x[1] for x in rr])))
    R = np.array(rec, dtype=float)
    P("# (a) Sell moments vs matched random moments, per day (MEASURED; ratio = share at his sells / share at random moments, 90% bootstrap over lots)")
    for code in (247, 248):
        P(f"\n## bot {code}")
        P("| day | lots | buy in last 212 ms: sell / random (ratio [90%]) | no outside buy in last 1 s: sell / random (ratio [90%]) |"); P("|---|---|---|---|")
        for d in list(range(7)) + [-1]:
            m = (R[:, 0] == code) & ((R[:, 1] == d) if d >= 0 else True)
            if m.sum() < 30: continue
            lo1, hi1 = boot_ratio(R[m, 3], R[m, 5], R[m, 2]); lo2, hi2 = boot_ratio(R[m, 4], R[m, 6], R[m, 2])
            P(f"| {'D' + str(d) if d >= 0 else 'ALL'} | {m.sum():,} | {R[m, 3].mean():.3f} / {R[m, 5].mean():.3f} ({R[m, 3].mean() / R[m, 5].mean():.2f} [{lo1:.2f}..{hi1:.2f}]) | "
              f"{R[m, 4].mean():.3f} / {R[m, 6].mean():.3f} ({R[m, 4].mean() / R[m, 6].mean():.2f} [{lo2:.2f}..{hi2:.2f}]) |")
    # (b)
    U = dict(np.load(f"{OUT}/s2_units.npz"))
    ids = json.load(open("/home/moiz/sniper-data/dv8/tab/ids.json")); idm = {k: i for i, k in enumerate(ids)}
    fb = np.array(sorted(idm[w] for w in json.load(open("/home/moiz/sniper/ops/strategies/presend/filter/fbots_frozen.json")) if w in idm))
    co = np.array(sorted(idm[w] for w in json.load(open("/home/moiz/sniper/ops/overnight/sel/cohort_train.json")) if w in idm))
    y = (U["gap"] <= 212).astype(float)
    strat = ((U["code"] - 247).astype(np.int64) * 2 + U["bu"]) * 100 + U["tb"].astype(np.int64) * 10 + U["sb"]
    _, inv = np.unique(strat, return_inverse=True); E = (np.bincount(inv, y) / np.bincount(inv))[inv]
    P("\n# (b) Known follower bots' BUYS -> his sell within 212 ms: lift vs time x size matched chance (90% bootstrap over lots)")
    P("| bot | list | " + " | ".join(f"D{d}" for d in range(6)) + " | ALL [90%] |"); P("|---|---|" + "---|" * 6 + "---|")
    for code in (247, 248):
        for name, L in (("fbots_frozen", fb), ("cohort_train", co)):
            m0 = (U["code"] == code) & U["bu"].astype(bool) & np.isin(U["us"], L)
            cells = []
            for d in range(6):
                m = m0 & (U["day"] == d); cells.append(f"{y[m].sum() / max(E[m].sum(), 1e-9):.2f}")
            lo, hi = boot_ratio(y[m0], E[m0], U["lot"][m0])
            P(f"| {code} | {name} | " + " | ".join(cells) + f" | {y[m0].sum() / E[m0].sum():.2f} [{lo:.2f}..{hi:.2f}] |")
    # (c)
    G = pickle.load(open(f"{OUT}/s6_grid.pkl", "rb"))
    PO = G["PO"]; M = G["G"][("ours", 1.0)]; om = G["ometa"]
    kinds = np.array([m[0] for m in om]); days = np.array([m[1] for m in om])
    P("\n# (c) OUR fills: wallet rule minus wave exit, paired per fill (curve mSOL/fill, 90% bootstrap), test days D2-D6")
    for kind, wv in (("ps", ("RIDE", 150, 150, 1000)), ("reg", ("RIDE", 150, 300, 2000))):
        mk = (kinds == kind) & (days >= 2); w = PO.index(wv)
        cand = [a for a, p in enumerate(PO) if p[0] in ("WL", "WLW")]
        best = sorted(cand, key=lambda a: -M[a, mk].sum())[:3]
        for a in best:
            dlt = (M[a, mk] - M[w, mk]) * 1000
            gg = np.random.default_rng(5); bs = [dlt[gg.integers(0, len(dlt), len(dlt))].mean() for _ in range(2000)]
            P(f"- {kind}: {PO[a]} - wave = {dlt.mean():+.2f} mSOL/fill [{np.percentile(bs, 5):+.2f}..{np.percentile(bs, 95):+.2f}] (in-sample BEST of {len(cand)} wallet rules), n {mk.sum()}")
    open(f"{OUT}/s11.txt", "w").write("\n".join(out) + "\n")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# Readable view of what a trained detector picks: (1) pick rate and per-attempt P&L (dump taken alone, near leaders, 35 ms,
# 1.3 s / SL -10%, costs incl.) by feature bins on the TEST days pooled (R3 + R1 + R4); (2) a depth-3 distilled tree fit on R2
# to "detector picks this dump" (readable rules, weaker than the model).
# usage: python3 dd10_explain.py <pred name> <threshold>
import sys
import numpy as np
import dd_lib as L
import dd_gbdt as GT
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/sel")
import gbdt_np as GB
DAYS = ("R2", "R3", "R1", "R4")
def preds(name):
    P = np.load(f"{L.OUT}/pred_{name}.npy"); out = {}; o = 0
    for day in DAYS:
        n = len(L.load(day)["k"]); out[day] = P[o:o + n]; o += n
    return out
def y_att(d, lat=0, e=L.E_13):
    st = d["st"][:, lat]
    return np.where(st == 0, d["pnl"][:, lat, e] - L.FIX, np.where(st == 1, -L.FAIL, np.nan))
if __name__ == "__main__":
    name, thr = sys.argv[1], float(sys.argv[2]); P = preds(name)
    D = {day: L.load(day) for day in DAYS}
    T = [D[x] for x in ("R3", "R1", "R4")]
    pick = np.concatenate([P[x] >= thr for x in ("R3", "R1", "R4")]); y = np.concatenate([y_att(d) for d in T])
    near = np.concatenate([d["near_f"] | d["near_a"] for d in T]); X = np.concatenate([d["Xall"] for d in T]); wt = np.concatenate([d["wt"] for d in T])
    f = lambda k: X[:, L.FNI[k]]
    print(f"{name} >= {thr}: test days pooled (R3+R1+R4), near-leader dumps {near.sum()}, picked {(pick & near).sum()} ({100 * (pick & near).mean() / max(near.mean(), 1e-9):.2f}%)")
    def show(nm, m):
        m = m & near & np.isfinite(y); a = m & pick; b = m & ~pick
        if m.sum() < 50: return
        print(f"  {nm:30s} dumps {m.sum():6d} picked {a.sum():5d} ({100 * a.sum() / m.sum():5.1f}%)  picked {1000 * np.nanmean(y[a]) if a.any() else 0:+6.1f}  not picked {1000 * np.nanmean(y[b]):+6.1f} mSOL/att")
    print(" seller type:")
    for nm, m in (("creator", wt == 1), ("create-slot insider", wt == 2), ("fresh wallet", wt == 3), ("bot (R2 list)", wt == 4), ("family F1-F10", wt >= 11), ("other", wt == 0), ("cohort seller", f("coh_seller") == 1)): show(nm, m)
    for k, bins in (("drop_pct", (2, 4.65, 6, 8, 10, 15, 25, 100)), ("age_s", (0, 3, 10, 30, 60, 120, 343.67, 1e9)), ("since_buy_s", (0, 0.2, 0.5, 1, 2, 3.869, 6, 10, 1e9)),
                    ("sol", (0, 0.5, 0.8, 1.08, 1.5, 2, 3, 5, 1e9)), ("curve", (0, 31, 33, 36, 40, 50, 60, 100)), ("s_frac", (0, 0.3, 0.6, 0.9, 1.01, 3)),
                    ("coh_held", (0, 1, 2, 4, 8, 1e9)), ("n_big", (0, 1, 2, 4, 8, 1e9)), ("hour", (0, 3, 6, 9, 12, 15, 18, 21, 24))):
        print(f" {k}:")
        x = f(k)
        for lo, hi in zip(bins, bins[1:]): show(f"{lo:g} <= {k} < {hi:g}", (x >= lo) & (x < hi))
    # distilled tree on R2 (all rows): label = detector pick
    d2 = D["R2"]; lab = (P["R2"] >= thr).astype(float); cols = [L.FNI[k] for k in L.FN if k not in ("ev_buy", "theme", "x", "eff", "fun", "rw", "cpy", "red", "bid", "top_n", "top_hold", "f1")]
    E = GT.edges_of(d2["Xall"][:, cols], np.ones(len(lab), bool)); B = GT.binize(d2["Xall"][:, cols], E)
    p0 = lab.mean(); F0 = np.log(p0 / (1 - p0)); gr = (p0 - lab); he = np.full(len(lab), p0 * (1 - p0))
    t = GB.build(B, gr, he, np.arange(len(lab)), 3, lam=1.0, min_n=200, fsub=np.arange(len(cols)))
    names = [L.FN[c] for c in cols]
    print("\n distilled depth-3 tree (R2), leaves with pick share; then precision on TEST days:")
    BT = {x: GT.binize(D[x]["Xall"][:, cols], E) for x in ("R3", "R1", "R4")}
    def walk(n, path, rows, rows_t):
        if "w" in n:
            sh = lab[rows].mean() if len(rows) else 0
            tl = {x: (P[x][r] >= thr).mean() if len(r) else 0 for x, r in rows_t.items()}
            yt = np.concatenate([y_att(D[x])[r] for x, r in rows_t.items()]); nt = np.concatenate([(D[x]["near_f"] | D[x]["near_a"])[r] for x, r in rows_t.items()])
            print(f"   {' & '.join(path) or 'all'}: R2 n {len(rows)} picked {100 * sh:.1f}% | test n {sum(len(r) for r in rows_t.values())} picked {100 * np.mean(list(tl.values())):.1f}%, all dumps here {1000 * np.nanmean(yt[nt]) if nt.any() else 0:+.1f} mSOL/att")
            return
        j = n["f"]; e = E[j]; b = n["b"]; thv = e[b - 1] if 1 <= b <= len(e) else (-np.inf if b < 1 else np.inf)
        lm = B[rows, j] <= b; walk(n["l"], path + [f"{names[j]} <= {thv:.4g}"], rows[lm], {x: r[BT[x][r, j] <= b] for x, r in rows_t.items()})
        walk(n["r"], path + [f"{names[j]} > {thv:.4g}"], rows[~lm], {x: r[BT[x][r, j] > b] for x, r in rows_t.items()})
    walk(t, [], np.arange(len(lab)), {x: np.arange(len(D[x]["k"])) for x in ("R3", "R1", "R4")})

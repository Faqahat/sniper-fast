#!/usr/bin/env python3
"""TIMING step 5: how predictable are the in-hold sells of visible holders? (pairs.pkl, online features)
AUC / precision / recall of each exit-rule signal for y = 'this holder sold inside our hold'; profile tables; big-loss main sellers."""
import pickle, collections, json
import numpy as np
D = "/home/moiz/sniper-data/prevent/timing"
R = pickle.load(open(f"{D}/pairs.pkl", "rb"))
FC = pickle.load(open(f"{D}/fillctx.pkl", "rb"))


def auc(p, y):
    p = np.asarray(p, float); y = np.asarray(y, int); o = np.argsort(p, kind="mergesort"); r = np.empty(len(p)); r[o] = np.arange(1, len(p) + 1)
    # ties -> average ranks
    _, inv, cnt = np.unique(p, return_inverse=True, return_counts=True); s = np.bincount(inv, r); r = (s / cnt)[inv]
    n1 = y.sum(); n0 = len(y) - n1
    return (r[y == 1].sum() - n1 * (n1 + 1) / 2) / max(n1 * n0, 1)


def pr(sel, y):
    sel = np.asarray(sel, bool); y = np.asarray(y, bool)
    tp = (sel & y).sum(); return tp, sel.sum(), (tp / max(sel.sum(), 1)), (tp / max(y.sum(), 1))


g = lambda r, k, d=np.nan: r.get(k, d) if r.get(k) is not None else d
y = np.array([r["y_hold"] for r in R]); yb = np.array([r["y_hold"] and r["sell_sol"] >= 0.5 for r in R])
print(f"pairs {len(R)}  base rate sold-in-hold {y.mean():.3f}  (>=0.5 SOL {yb.mean():.3f})")
for name, sel in [("all", np.ones(len(R), bool)), ("pct>=3", np.array([r["pct"] >= 3 for r in R])), ("pct>=6", np.array([r["pct"] >= 6 for r in R])),
                  ("creator", np.array([r["creator"] for r in R])), ("whale(T2 trigger)", np.array([r["whale"] for r in R])),
                  ("same-slot cluster", np.array([r["clu"] > 0 for r in R])), ("no history", np.array([r["n"] == 0 for r in R]))]:
    print(f"  {name:20s} n={sel.sum():5d} sold-in-hold {y[sel].mean():.3f}  >=0.5 SOL {yb[sel].mean():.3f}")
H = np.array([r["n"] > 0 for r in R])
print("\nAUC for sold-in-hold (pairs with history):")
for k in ("hz1", "hz2", "hz4", "le2", "le10", "full", "mnow", "pct", "clu"):
    v = np.array([g(r, k) for r in R]); m = H & np.isfinite(v)
    print(f"  {k:6s} n={m.sum():5d} AUC {auc(v[m], y[m]):.3f}  AUC(>=0.5 SOL) {auc(v[m], yb[m]):.3f}")
# timer due: tight past holds and the current hold sits at the timer
print("\nTIMER-like holders (n_done>=5): IQR of past first-sell holds")
tight = np.array([r.get("n_done", 0) >= 5 and g(r, "iqr", 1e9) <= 2 for r in R])
tight4 = np.array([r.get("n_done", 0) >= 5 and g(r, "iqr", 1e9) <= 4 for r in R])
print(f"  IQR<=2 slots: {tight.sum()} pairs ({tight.mean():.3f}); IQR<=4: {tight4.sum()}")
due = np.array([tight4[n] and r["hold"] is not None and (g(r, "q25") - 1 <= r["hold"] + 1 <= g(r, "q75") + 1) for n, r in enumerate(R)])
print("  timer due (IQR<=4 & hold+1 in [q25-1, q75+1]): tp/sel/prec/rec", pr(due, y))
for thr in (0.1, 0.2, 0.3, 0.5):
    s = np.array([g(r, "hz2", 0) >= thr and g(r, "hzn2", 0) >= 5 for r in R])
    print(f"  hz2>={thr} (>=5 at risk): tp/sel/prec/rec", pr(s, y), " >=0.5SOL", pr(s, yb))
print("\nTP-like: current multiple vs its past first-sell multiples")
for lab, f in [("mnow>=m25", lambda r: g(r, "mnow") >= g(r, "m25")), ("mnow>=m50", lambda r: g(r, "mnow") >= g(r, "m50")),
               ("mnow*1.2>=m50", lambda r: g(r, "mnow") * 1.2 >= g(r, "m50")), ("mnow<0.8 (SL zone)", lambda r: g(r, "mnow") < 0.8)]:
    s = np.array([r["n"] > 0 and bool(f(r)) for r in R]); print(f"  {lab:20s} tp/sel/prec/rec", pr(s, y))
# multiples distribution of actual in-hold sells vs non
mn = np.array([g(r, "mnow") for r in R])
print("  mnow quantiles sold-in-hold:", np.nanpercentile(mn[y], [10, 25, 50, 75, 90]).round(2), " not:", np.nanpercentile(mn[~y], [10, 25, 50, 75, 90]).round(2))
# big losses: main seller
print("\nBIG LOSSES (raw pnl <= -0.05): main in-hold seller (largest SOL)")
big = [f for f in FC if f["pnl"] is not None and f["pnl"] <= -0.05]
cnt = collections.Counter(); ex = []
idx = {(r["run"], r["ses"], r["kind"], r["w"], r["wallet"]): r for r in R}
for f in big:
    if not f["inhold"]: cnt["no in-hold seller"] += 1; continue
    w, v = max(f["inhold"].items(), key=lambda kv: kv[1][0])
    r = idx.get((f["run"], f["ses"], f["kind"], f["w"], w))
    if r is None: cnt["main seller NOT a >=2% holder at our buy"] += 1; continue
    cnt["main seller visible >=2%"] += 1
    if r["n"] == 0: cnt["  .. no history"] += 1; continue
    if g(r, "hz2", 0) >= 0.3: cnt["  .. hz2>=0.3 (timer predicted)"] += 1
    if g(r, "n_done", 0) >= 5 and g(r, "iqr", 1e9) <= 4: cnt["  .. tight timer IQR<=4"] += 1
    if g(r, "mnow") >= g(r, "m25"): cnt["  .. TP zone (mnow>=m25)"] += 1
    if r["creator"]: cnt["  .. creator"] += 1
    if r["whale"]: cnt["  .. T2 whale"] += 1
for k, v in cnt.items(): print(f"  {k:45s} {v}")

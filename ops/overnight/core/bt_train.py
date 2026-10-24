#!/usr/bin/env python3
# "Become them" selection model: which launches, bought at OUR landing with the price guard and held ~10 s, make money
# WITHOUT the pro bots' buys after us (and with followers' slippage limits)? Same 61 live features as FINAL-2 (known at
# bundle close), same histogram GBDT code (ops/select/e_model.py), label = PnL > 0 under variant VAR at exit EX.
# Strict time order: train = R1 (proxy placement), validation = R2 first half (choose the cut), test = R2 second half.
# usage: python3 -I bt_train.py [VAR=ps] [EX=t10] [LAND=75]
import sys, json, gzip, re
import numpy as np
CORE = "/home/moiz/sniper/ops/overnight/core"
VAR = sys.argv[1] if len(sys.argv) > 1 else "ps"; EXN = sys.argv[2] if len(sys.argv) > 2 else "t10"; LAND = sys.argv[3] if len(sys.argv) > 3 else "75"
src = open("/home/moiz/sniper/ops/select/e_model.py").read()
exec(src[src.index("def binize"):src.index("def stats")])
FEATS = json.load(open("/home/moiz/sniper-data/collect/paper/frozen_live3_fsell.json"))["features"]
A = json.load(open(f"{CORE}/allres_bt.json")); XN = A["exits"]; A = A["res"]; xi = XN.index(EXN)
T = {}
for l in gzip.open("/home/moiz/sniper-data/collect/paper/table_dump.jsonl.gz", "rt"):
    r = json.loads(l)
    if r.get("mint") in A: T[r["mint"]] = r
ms = sorted((m for m in A if m in T and LAND in A[m]), key=lambda m: A[m]["bt"])
def fval(r, k):
    if "==" in k: c, v = k.split("==", 1); return float(str(r.get(c) if r.get(c) is not None else "None") == v) if c != "fp" else float(str(r.get(c)) == v)
    x = r.get(k); return np.nan if x is None else float(x)
X = np.array([[fval(T[m], k) for k in FEATS] for m in ms]); run = np.array([A[m]["run"] for m in ms]); bt = np.array([A[m]["bt"] for m in ms], float)
fill = np.array([A[m][LAND] is not None and VAR in (A[m][LAND] or {}) for m in ms])
pnl = np.array([A[m][LAND][VAR][xi] if fill[i] else -0.005 for i, m in enumerate(ms)])
r2 = run == "R2"; mid = np.median(bt[r2]); TR = (run == "R1") & fill; VA = r2 & (bt < mid); TE = r2 & (bt >= mid)
y = (pnl > 0).astype(float)
Bm = binize(X, TR)
trees, f = fit(Bm, y, TR, VA & fill, rounds=400, lr=0.05, depth=3)
print(f"label: {VAR} {EXN} pnl > 0 at {LAND} ms | train R1 fills {TR.sum()} (pos {y[TR].mean():.1%}) | val R2a {VA.sum()} | test R2b {TE.sum()} | trees {len(trees)}")
print(f"AUC on fills: val {auc(y[VA & fill], f[VA & fill]):.3f} test {auc(y[TE & fill], f[TE & fill]):.3f}")
def book(sel):
    v = pnl[sel]; fl = fill[sel]
    return f"n {sel.sum():4d} fills {fl.sum():4d} total {v.sum():+6.2f} SOL | per fill {v[fl].mean() if fl.any() else 0:+.4f} med {np.median(v[fl]) if fl.any() else 0:+.4f} win {(v[fl] > 0).sum()}/{fl.sum()} | w/o top5 {v.sum() - np.sort(v)[-5:].sum():+6.2f}"
print("all launches:  val " + book(VA) + "\n               test " + book(TE))
for q in (0.99, 0.98, 0.95, 0.9, 0.8):
    cut = np.quantile(f[VA], q)                 # cut chosen on validation launches, applied unchanged to test
    print(f"top {100 * (1 - q):4.1f}% (score >= {cut:+.3f}): val " + book(VA & (f >= cut)) + "\n" + " " * 29 + "test " + book(TE & (f >= cut)))
json.dump(dict(features=FEATS, trees=trees, var=VAR, exit=EXN, land=LAND, F0=float(np.log(y[TR].mean() / (1 - y[TR].mean())))),
          open(f"{CORE}/bt_model_{VAR}_{EXN}_{LAND}.json", "w"))

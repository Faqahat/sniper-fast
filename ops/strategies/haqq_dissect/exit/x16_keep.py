#!/usr/bin/env python3
"""EXIT step 16 (read-only): which lots does haqq KEEP (hold >= 15 s / add to) vs CUT, from information AFTER entry and BEFORE
the exit only, and does that information predict the forward value of holding? (MEASURED tape; forward values = exact replay vx)
At tau = 500 / 1000 / 2000 ms after his buy, for his non-DEAD FIRST lots still held at tau (his exit later than tau):
  features (outside trades landed before tau): ret (real tape), best ret so far, outside buy SOL in (tau-300, tau], buy SOL and
  number of buys since his buy, sell SOL since his buy, ms since the last outside buy
  labels: kept = his hold >= 15 s; added = the position got a later add (a buy while lot 1 is open)
  forward: replayed value change from tau to tau+2 s and tau+5 s (mSOL per lot, his later trades removed), and to his own exit
Single-feature AUC for 'kept' and 'added', and tables by bins. Then the causal rule RIDE (x13) on the kept / cut groups.
Out: haqq_dissect/exit/x16.txt"""
import pickle, sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/exit")
import xlib as X
out = []
def P(*a):
    s = " ".join(str(x) for x in a); print(s); out.append(s)
Z = pickle.load(open(f"{X.OUT}/haqq.pkl", "rb")); L = Z["lots"]; POS = Z["pos"]
A = np.load(f"{X.OUT}/paths.npz"); off = A["off"]; ex = A["lot_exit"]; DCC = A["dcc"]; BU = A["buy"]; SO = A["sol"]; VA = A["va"]; VX = A["vx"]


def auc(x, y):
    x = np.asarray(x, float); y = np.asarray(y, bool); ok = np.isfinite(x); x = x[ok]; y = y[ok]
    r = np.argsort(np.argsort(x, kind="stable"), kind="stable") + 1.0
    n1 = y.sum(); n0 = (~y).sum()
    return (r[y].sum() - n1 * (n1 + 1) / 2) / (n1 * n0) if n1 and n0 else np.nan


rows = {t: [] for t in (500, 1000, 2000)}
for p in POS:
    if p["close_cc"] is None: continue
    i = p["lots"][0]; l = L[i]
    if l["t"] == "DEAD" or l["close_cc"] is None: continue
    a, b = off[i], off[i + 1]; n = b - a
    if n == 0: continue
    dc = DCC[a:b].astype(np.float64); bu = BU[a:b]; so = SO[a:b].astype(np.float64); va = VA[a:b].astype(np.float64); vx = VX[a:b].astype(np.float64)
    xt = l["close_cc"] - l["cc"]; e = ex[i]
    added = p["nb"] > 1
    for tau in rows:
        if xt <= tau or dc[-1] < tau + 5000: continue
        q = np.searchsorted(dc, tau, side="right") - 1
        if q < 0: continue
        w = dc[:q + 1]; bb = bu[:q + 1]; ss = so[:q + 1]
        bt = w[bb]
        f = dict(ret=va[q] - 1, best=np.max(va[:q + 1]) - 1, b300=ss[bb & (w > tau - 300)].sum(), bsum=ss[bb].sum(), nb=int(bb.sum()),
                 ssum=ss[~bb].sum(), since_buy=(tau - bt[-1]) if len(bt) else 99999.0, net=ss[bb].sum() - ss[~bb].sum())
        v0 = vx[q]
        def vat(t): return vx[np.searchsorted(dc, t, side="right") - 1]
        f.update(fw2=(vat(tau + 2000) - v0) * l["cost"], fw5=(vat(tau + 5000) - v0) * l["cost"],
                 fwx=((vx[e - 1] if 0 < e < n else vx[-1]) - v0) * l["cost"], kept=xt >= 15000, added=added, day=l["day"], cost=l["cost"])
        rows[tau].append(f)
for tau, R in rows.items():
    P(f"\n## tau = {tau} ms after his buy: {len(R):,} first lots still held (kept >= 15 s: {100 * np.mean([r['kept'] for r in R]):.0f}%, added later: {100 * np.mean([r['added'] for r in R]):.0f}%)")
    P(f"forward replayed value from tau, mean mSOL/lot: +2 s {1000 * np.mean([r['fw2'] for r in R]):+.1f}, +5 s {1000 * np.mean([r['fw5'] for r in R]):+.1f}, to his exit {1000 * np.mean([r['fwx'] for r in R]):+.1f}")
    P("| feature | AUC kept | AUC added | corr with fwd +5 s (Spearman) |"); P("|---|---|---|---|")
    fw = np.array([r["fw5"] for r in R])
    for k in ("ret", "best", "b300", "bsum", "nb", "ssum", "net", "since_buy"):
        x = np.array([r[k] for r in R], float)
        rx = np.argsort(np.argsort(x)); rf = np.argsort(np.argsort(fw))
        P(f"| {k} | {auc(x, [r['kept'] for r in R]):.3f} | {auc(x, [r['added'] for r in R]):.3f} | {np.corrcoef(rx, rf)[0, 1]:+.3f} |")
    for k, bins in (("b300", (0, 1e-9, 0.3, 1, 3, 1e9)), ("ret", (-9, -0.1, -0.03, 0.03, 0.1, 0.25, 9)), ("since_buy", (0, 100, 300, 1000, 3000, 1e9)), ("net", (-1e9, -2, -0.5, 0.5, 2, 1e9))):
        P(f"\n{k} bins at tau={tau}: | bin | lots | kept % | added % | fwd +2 s mSOL | fwd +5 s mSOL | fwd to his exit mSOL |")
        x = np.array([r[k] for r in R], float)
        for lo, hi in zip(bins[:-1], bins[1:]):
            m = (x >= lo) & (x < hi)
            if m.sum() < 100: continue
            v = [r for r, mm in zip(R, m) if mm]
            P(f"| {lo:g}..{hi:g} | {m.sum():,} | {100 * np.mean([r['kept'] for r in v]):.0f} | {100 * np.mean([r['added'] for r in v]):.0f} | {1000 * np.mean([r['fw2'] for r in v]):+.1f} | {1000 * np.mean([r['fw5'] for r in v]):+.1f} | {1000 * np.mean([r['fwx'] for r in v]):+.1f} |")
    # per day: 'buys still coming' (b300 > 0) vs not, forward +5 s
    P(f"\nper day at tau={tau}, fwd +5 s mSOL/lot: buys in last 300 ms (b300>0) vs none:")
    for d in range(7):
        v = [r for r in R if r["day"] == d]
        if len(v) < 200: continue
        a1 = [r["fw5"] for r in v if r["b300"] > 0]; a0 = [r["fw5"] for r in v if r["b300"] == 0]
        P(f"- D{d}: buys {1000 * np.mean(a1):+.1f} (n {len(a1)}, 90% {1000 * X.boot_mean(a1)[0]:+.1f}..{1000 * X.boot_mean(a1)[1]:+.1f}), none {1000 * np.mean(a0):+.1f} (n {len(a0)}, 90% {1000 * X.boot_mean(a0)[0]:+.1f}..{1000 * X.boot_mean(a0)[1]:+.1f})")
open(f"{X.OUT}/x16.txt", "w").write("\n".join(out) + "\n")

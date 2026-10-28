#!/usr/bin/env python3
"""SELECT s17: can a SIMPLE rule reproduce >= 50 % of his first-buy picks? Per family envelope (s9 definitions), on TRAIN: greedy
search of up to 3 threshold conditions (feature >= q or <= q at train quantiles 10..90 %) maximising precision subject to
recall >= 50 % of his picks. Then TEST (newest 6 h, untouched): recall, precision, and forward g24 / g141 (entry one slot later,
market px, no fees) of rule picks that are NOT his vs his picks."""
import sys, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from s4_model import MKT
OUT = "/home/moiz/sniper-data/e2x1_dissect/select"
U = dict(np.load(f"{OUT}/U.npz"))
tmax = U["bt"].max(); TE = U["bt"] >= tmax - 6 * 3600
y = U["y3"].astype(bool) & (U["my_buys"] == 0); ok = (U["my_buys"] == 0) & (U["samp"] | y); wt = np.where(y, 1.0, 25.0)
age = U["age_s"]; imp = U["imp"]; isb = U["is_buy"] > 0
FAM = {"LDUMP": (age < 10) & ~isb & (imp <= -0.05), "LPUMP": (age < 10) & isb & (imp >= 0.05),
       "EDUMP": (age >= 10) & (age < 120) & ~isb & (imp <= -0.05), "EPUMP": (age >= 10) & (age < 120) & isb & (imp >= 0.05),
       "MFLOW": (age >= 120) & (np.abs(imp) >= 0.02)}
FE = [f for f in MKT if f not in ("hour",)]
def m_(x, w):
    k = np.isfinite(x); return 100 * np.average(np.clip(x[k], -1, 5), weights=w[k]) if k.any() else np.nan
for nm, fm in FAM.items():
    R = fm & ok; tr = R & ~TE; te = R & TE
    conds = []; cur = tr.copy()
    for step in range(3):
        best = None
        for f in FE:
            x = U[f]
            qs = np.unique(np.nanquantile(x[cur & y], np.linspace(0.05, 0.5, 10)))      # lower cuts keeping >= 50 % of his remaining
            for q in qs:
                for op in (">=",):
                    sel = cur & (x >= q)
                    rec = (sel & y & tr).sum() / (tr & y).sum()
                    if rec < 0.5: continue
                    prec = (sel & y).sum() / wt[sel].sum()
                    if best is None or prec > best[0]: best = (prec, rec, f, op, q, sel)
            qs2 = np.unique(np.nanquantile(x[cur & y], np.linspace(0.5, 0.95, 10)))
            for q in qs2:
                sel = cur & (x <= q); rec = (sel & y & tr).sum() / (tr & y).sum()
                if rec < 0.5: continue
                prec = (sel & y).sum() / wt[sel].sum()
                if best is None or prec > best[0]: best = (prec, rec, f, "<=", q, sel)
        if best is None: break
        conds.append((best[2], best[3], float(best[4]))); cur = best[5]
    sel_te = te.copy()
    for f, op, q in conds: sel_te &= (U[f] >= q) if op == ">=" else (U[f] <= q)
    sel_tr = cur
    base_te = (te & y).sum() / wt[te].sum()
    rec_te = (sel_te & y).sum() / max((te & y).sum(), 1); prec_te = (sel_te & y).sum() / max(wt[sel_te].sum(), 1)
    nh = sel_te & ~y; hy = te & y
    print(f"\n=== {nm}: rule {' & '.join(f'{f} {op} {q:.3g}' for f, op, q in conds)}")
    print(f"  TRAIN recall {(sel_tr & y).sum()/(tr & y).sum():.2f} precision {(sel_tr & y).sum()/wt[sel_tr].sum():.4f} (base {(tr & y).sum()/wt[tr].sum():.4f})")
    print(f"  TEST  recall {rec_te:.2f} precision {prec_te:.4f} (base {base_te:.4f}, lift {prec_te/max(base_te,1e-9):.1f}x); rule picks/day ~{wt[sel_te].sum()*4:.0f}")
    print(f"  TEST fwd: his picks g24 {m_(U['g24'][hy], wt[hy]):+.2f} g141 {m_(U['g141'][hy], wt[hy]):+.2f} | rule-not-his g24 {m_(U['g24'][nh], wt[nh]):+.2f} g141 {m_(U['g141'][nh], wt[nh]):+.2f}"
          f" | whole TRAIN rule-not-his g24 {m_(U['g24'][sel_tr & ~y], wt[sel_tr & ~y]):+.2f} g141 {m_(U['g141'][sel_tr & ~y], wt[sel_tr & ~y]):+.2f}")

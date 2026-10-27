#!/usr/bin/env python3
# PRE-SEND V2 step c9: compact tables for the report (TEST = R3 + R4): (e) attempt rate -> landing, fills, attempt cost per fill, margin;
# (b) size -> per-fill move after pump fees (% of size), fixed-cost share, net.
import sys, os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V, v2eng as E, v2run as R
R.G["DD"] = {d: E.load(d) for d in V.DAYS}
M = json.load(open(f"{V.OUT}/c3_model.json"))
def landing(k, x=False):
    g = M["grid"][f"dl1|{float(k)}|1000"]; none = g["none"]; sc = 0.85
    if x: none = 1 - (1 - none) * 0.9; sc = 1.0
    return 100 * none, sc * g["q"][50]
out = {}
print("(e) attempt rate, T2, 0.55 SOL, y 12%, c2_tp10_sl20, TEST R3+R4")
for row in ("L2", "L4", "L8", "L12", "L20", "L4x", "L8x", "L12x", "L20x"):
    r = R.ev(R.mod(row=row), R.TEST); a = R.agg(r, R.TEST); k = E.KROW[row]
    n, d50 = landing(k, row.endswith("x"))
    cost_att = sum(r[d]["cost_att"] for d in R.TEST) / max(a["fills"], 1)
    print(f"  {row:5s} k {k:4.0f}: landing p50 {d50:5.1f} ms, no attempt could fill {n:4.1f}% | fills {a['fills24']:5.0f}/d (rate {100 * a['fill_rate']:4.1f}%) | "
          f"after pump fees {a['gross_fill']:+.4f}/fill | attempts {a['att_fill']:4.0f}/fill = {cost_att:.4f} SOL | net {a['per_fill']:+.4f}/fill | {a['per24']:+6.2f} SOL/d")
    out[row] = dict(k=k, d50=d50, none=n, **a, cost_att_fill=cost_att)
print("(b) size, T2, L4 and L8, TEST R3+R4")
for row in ("L4", "L8"):
    for sz in (0.2, 0.35, 0.55, 1.0, 1.5):
        r = R.ev(R.mod(row=row, size=sz), R.TEST); a = R.agg(r, R.TEST)
        print(f"  {row} {sz:4.2f} SOL: after pump fees {a['gross_fill']:+.4f}/fill ({100 * a['gross_fill'] / sz:+.2f}% of size) | fixed {E.COST['real']['fill']:.4f} ({100 * E.COST['real']['fill'] / sz:.2f}%) | "
              f"net {a['per_fill']:+.4f}/fill | {a['per24']:+6.2f} SOL/d | min day {a['min_day']:+.2f}")
        out[f"{row}_{sz}"] = a
json.dump(out, open(f"{V.OUT}/c9_tables.json", "w"), default=float)

#!/usr/bin/env python3
"""EXITPICK step 2: the size of the prize (oracle) and fixed exits per split."""
import collections
from elib import *
R = load()
print("hours", {k: round(v, 2) for k, v in SPLIT_H.items()})
for sp in ("dev", "val", "hold"):
    rows = [r for r in R if r["split"] == sp]; h = SPLIT_H[sp]
    b = sum(y(r, "t125") for r in rows)
    print(f"\n== {sp}: fills {len(rows)}, {h:.1f} h, fixed t125 {b:+.3f} SOL ({b / h * 24:+.2f}/day), real {sum(r['real'] for r in rows):+.3f}")
    print("  fixed:", " ".join(f"{k}:{sum(y(r, k) for r in rows) - b:+.2f}" for k in KEYS))
    orc = sum(max(y(r, k) for k in KEYS) for r in rows) - b
    orc_t = sum(max(y(r, k) for k in KEYS if k.startswith("t")) for r in rows) - b
    print(f"  ORACLE all 17 exits: +{orc:.3f} SOL ({orc / h * 24:+.2f}/day) | timers only +{orc_t:.3f}")
    print("  ORACLE {t125, X}:", " ".join(f"{k}:+{sum(max(0, gain(r, k)) for r in rows):.2f}" for k in EXT))
    for var in ("y_rs", "y_fc"):
        bb = sum(y(r, "t125", var) for r in rows)
        print(f"  [{var}] t125 {bb:+.3f}; oracle +{sum(max(y(r, k, var) for k in KEYS) for r in rows) - bb:.3f}; fixed t1000 {sum(y(r,'t1000',var) for r in rows) - bb:+.3f}")
    # how much of the gain is TP/SL-before-125 (no choice possible)
    pre = sum(1 for r in rows if r["why125"] in ("tp", "sl"))
    print(f"  t125 exit was TP/SL (decided before 125, no choice): {pre}")
    # concentration of the oracle gain t1000
    g = sorted((gain(r, "t1000") for r in rows), reverse=True)
    print(f"  t1000-t125 gains: top5 {sum(g[:5]):+.3f} top20 {sum(g[:20]):+.3f} bottom20 {sum(g[-20:]):+.3f}  n>0 {sum(1 for a in g if a > 1e-6)} n<0 {sum(1 for a in g if a < -1e-6)}")

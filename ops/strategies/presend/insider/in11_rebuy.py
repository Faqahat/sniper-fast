#!/usr/bin/env python3
"""INSIDER step 11: the census insider dumps (paper fill, >= X%, age 0): how fast is the dump re-bought? price after the next 1 / 2 trades
of the same block and at the block's end vs the pre-dump price (a pre-sent try signed before the dump fills only while the price is
<= 0.88x its signing price). usage: in11_rebuy.py TAB CENSUS.pkl X"""
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/multiarm")
import ma_lib as M
tape = M.Tape(sys.argv[1]); X = float(sys.argv[3])
R = [r for r in pickle.load(open(sys.argv[2], "rb")) if r["class"] == "insider" and r["pct"] >= X and r["age"] == 0 and r["paper"] is not None]
B = collections.defaultdict(lambda: [0, 0.0])
for r in R:
    t = tape.trades(r["mint"])
    if t is None: continue
    ds = r["slot"] + r["gap"]; k = None
    for q in np.nonzero((t["slot"] == ds) & (t["buy"] == 0))[0]:
        if tape.ids[int(t["user"][q])].startswith(r["w"]): k = int(q); break
    if k is None or k == 0: continue
    pr = lambda q: t["vsol"][q] / t["vtok"][q]
    p_pre = pr(k - 1)
    same = [q for q in range(k + 1, len(t)) if t["slot"][q] == ds]
    p1 = pr(same[0]) / p_pre if same else pr(k) / p_pre
    p_end = pr(same[-1]) / p_pre if same else pr(k) / p_pre
    if p1 > 0.88: cls = "a) the NEXT tx re-buys it above 0.88x"
    elif p_end > 0.88: cls = "b) re-bought above 0.88x later in the same block"
    else: cls = "c) still <= 0.88x at the block's end"
    B[cls][0] += 1; B[cls][1] += r["paper"] / 1e3
n = sum(v[0] for v in B.values()); p = sum(v[1] for v in B.values())
print(f"census insider paper fills >= {X}% age 0: {n} fills, paper {p:+.2f} SOL")
for k in sorted(B): print(f"  {k:52s} {B[k][0]:4d} fills ({B[k][0] / n:.0%})  paper {B[k][1]:+7.2f} SOL")

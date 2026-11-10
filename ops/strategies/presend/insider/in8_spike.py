#!/usr/bin/env python3
"""INSIDER step 8: is the census paper's dip a real dip for a pre-sent try? For each census insider paper fill (>= 10%, age 0): the price
right after the insider's dump vs the price at the end of the slot BEFORE the dump's slot (what a try signed ~1 slot earlier sees).
A pre-sent try (min-out 0.88x of its signing price) can fill only if post-dump price <= 0.88 x that price.
usage: in8_spike.py TAB CENSUS.pkl"""
import sys, pickle
import numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/presend/multiarm")
import ma_lib as M
tape = M.Tape(sys.argv[1])
R = [r for r in pickle.load(open(sys.argv[2], "rb")) if r["class"] == "insider" and r["pct"] >= 10 and r["age"] == 0 and r["paper"] is not None]
ok = [0, 0.0]; no = [0, 0.0]; miss = 0
for r in R:
    t = tape.trades(r["mint"])
    if t is None: miss += 1; continue
    ds = r["slot"] + r["gap"]
    k = None
    for q in np.nonzero((t["slot"] == ds) & (t["buy"] == 0))[0]:
        if tape.ids[int(t["user"][q])].startswith(r["w"]): k = int(q); break
    if k is None: miss += 1; continue
    p_post = t["vsol"][k] / t["vtok"][k]
    prev = np.nonzero(t["slot"] < ds)[0]
    if len(prev) == 0: miss += 1; continue
    kp = int(prev[-1]); p_prev = t["vsol"][kp] / t["vtok"][kp]
    if p_post <= 0.88 * p_prev: ok[0] += 1; ok[1] += r["paper"] / 1e3
    else: no[0] += 1; no[1] += r["paper"] / 1e3
print(f"paper fills {len(R)} (unmatched {miss}); dump is >= 12% below the previous slot's close: {ok[0]} fills {ok[1]:+.2f} SOL paper | "
      f"NOT (spike inside the dump slot, a pre-sent try can't fill): {no[0]} fills {no[1]:+.2f} SOL paper")

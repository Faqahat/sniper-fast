#!/usr/bin/env python3
"""APEX-FEES step 0: S2 pick list (walk-forward CREP at position A, same as c3_compet.py) -> picks.json {mint: [creator, bt, unseen]}"""
import sys, json, numpy as np
sys.path.insert(0, "/home/it/sniper/ops/strategies/apex2")
import a2_eval as E
L = E.load(strings=False); bt = np.array([r[2] for r in L])
sel = E.crep(L, "same")["A"]
out = {L[i][0]: [L[i][1], int(L[i][2]), bool(bt[i] >= E.UNSEEN)] for i in np.flatnonzero(sel)}
json.dump(out, open("/home/it/sniper-data/apex2/fees/picks.json", "w"))
print("picks", len(out), "unseen", sum(v[2] for v in out.values()), "simulated launches", len(L))

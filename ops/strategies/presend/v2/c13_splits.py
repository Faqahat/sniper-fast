#!/usr/bin/env python3
# PRE-SEND V2 step c13: where B's money comes from (TRAIN vs TEST, net per fill and SOL/day by one feature at a time).
# Window features at the trigger (holding %, token age, curve SOL, the whale's buy SOL) and fill features (the crossing is the
# whale's own sell; the crossing's own drop). Descriptive: nothing here was used to choose the finalists.
import sys, os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V, v2eng as E, v2run as R
R.G["DD"] = {d: E.load(d) for d in V.DAYS}
cfg = json.load(open(f"{V.OUT}/finalists.json"))["B_k8_0.55"]
r = R.ev(cfg, V.DAYS, detail=True)
def grab(days):
    rows = []
    for d in days:
        o = r[d]; D = R.G["DD"][d]; idx = o["idx"]; acc = o["acc"]
        w = idx[acc]; fr = o["acc_fr"]
        for q, (wi, f_, net) in enumerate(zip(w.tolist(), fr.tolist(), o["acc_net"].tolist())):
            rows.append(dict(hpct=D["w_f"][wi, E.FI["hpct"]], age=D["w_f"][wi, E.FI["age_s"]], curve=D["w_f"][wi, E.FI["curve"]], wsol=D["w_f"][wi, E.FI["wsol"]],
                             xwhale=D["f_f"][f_, E.FFI["x_whale"]], xdrop=D["f_f"][f_, E.FFI["xdrop"]], el=D["f_f"][f_, E.FFI["el"]], net=net))
    return rows
TR = grab(R.TRAIN); TE = grab(R.TEST)
hTR = sum(R.G["DD"][d]["hours"] for d in R.TRAIN); hTE = sum(R.G["DD"][d]["hours"] for d in R.TEST)
SPL = {"hpct": [5, 6, 8, 12, 100], "age": [0, 5, 10, 30, 120, 1e9], "curve": [0, 35, 45, 60, 100], "wsol": [0, 1, 2, 4, 1e9],
       "xwhale": [-0.5, 0.5, 1.5], "xdrop": [0, 5, 10, 15, 25, 100], "el": [0, 212, 636, 1272, 1e9]}
for k, edges in SPL.items():
    print(f"{k}:")
    for lo, hi in zip(edges, edges[1:]):
        a = [x["net"] for x in TR if lo <= x[k] < hi]; b = [x["net"] for x in TE if lo <= x[k] < hi]
        print(f"   [{lo:g}, {hi:g}): TRAIN {len(a):5d} fills {np.mean(a) if a else 0:+.4f}/fill {sum(a) / hTR * 24:+6.2f}/d | TEST {len(b):5d} fills {np.mean(b) if b else 0:+.4f}/fill {sum(b) / hTE * 24:+6.2f}/d")

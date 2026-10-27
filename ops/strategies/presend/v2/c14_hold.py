#!/usr/bin/env python3
# PRE-SEND V2 step c14: the whale-holding threshold on a finer grid, chosen on TRAIN (R1 + R2), shown on TEST.
# (c13 showed fills on 5-6% holders are ~break-even and > 12% holders lose, on train and test alike.)
import sys, os, json
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V, v2eng as E, v2run as R
R.G["DD"] = {d: E.load(d) for d in V.DAYS}
res = {}
for row, sz in (("L4", 0.55), ("L8", 0.55), ("L8x", 0.55), ("L8", 1.0), ("L12", 1.0), ("L4", 1.0)):
    print(f"== {row} {sz} SOL")
    for hmin in (5.0, 5.5, 6.0, 6.5, 7.0, 8.0):
        for hmax in (None, 12.0):
            sp = dict(fam="T2", hmin=hmin); 
            if hmax: sp["hmax"] = hmax
            r = R.ev(R.mod(spec=sp, row=row, size=sz), V.DAYS); tr = R.agg(r, R.TRAIN); te = R.agg(r, R.TEST)
            res[f"{row}|{sz}|{hmin}|{hmax}"] = dict(train=tr, test=te, days={d: r[d]["per24"] for d in V.DAYS})
            print(f"   hold {hmin:4.1f}-{hmax or 100:4.0f}%: TRAIN {tr['per24']:+6.2f}/d | TEST {te['per24']:+6.2f}/d ({te['fills24']:4.0f} f/d, {te['per_fill']:+.4f}/fill) | "
                  + " ".join(f"{d} {r[d]['per24']:+6.2f}" for d in V.DAYS))
json.dump(res, open(f"{V.OUT}/c14_hold.json", "w"), default=float)

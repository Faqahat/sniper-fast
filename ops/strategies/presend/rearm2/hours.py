#!/usr/bin/env python3
"""per PKT hour slot coverage of a tab (present slots / expected slots from the block-time -> slot interpolation)"""
import sys, json, time
import numpy as np
tab, out = sys.argv[1], sys.argv[2]
S = np.load(f"{tab}/slots.npy"); S = S[S["bt"] > 0]
sl = S["slot"].astype(np.int64); bt = S["bt"].astype(np.int64)
o = np.argsort(sl); sl = sl[o]; bt = bt[o]
bt = np.maximum.accumulate(bt)
h0 = (bt[0] // 3600 + 1) * 3600; h1 = bt[-1] // 3600 * 3600
rows = []
for h in range(h0, h1, 3600):
    a = np.interp(h, bt, sl); b = np.interp(h + 3600, bt, sl)
    n = int(((sl >= a) & (sl < b)).sum()); exp = b - a
    rows.append(dict(h=int(h), exp=float(exp), present=n, cov=n / max(exp, 1), usable=bool(n / max(exp, 1) >= 0.95)))
    print(time.strftime("%m-%d %H", time.gmtime(h + 18000)), f"{n / max(exp, 1):.3f}", rows[-1]["usable"])
json.dump(dict(rows=rows), open(out, "w"))

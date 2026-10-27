#!/usr/bin/env python3
# r06: completeness check of the recording around our trades: every trade the live engine logged in its "tape" records
# (trades near our buys, from the engine's own feed) must be in the recording's day arrays (same mint, slot, tx index, side, size).
import sys, os, json, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
c = collections.Counter(); ex = []
for srv, rn, base in R.RUN_FILES:
    for l in open(f"{R.LIVE}/{base}.jsonl"):
        if '"tape"' not in l[:60]: continue
        o = json.loads(l)
        if o.get("ev") != "tape": continue
        hit = None
        for tag, TP in TPS.items():
            t = TP.mint2t.get(o["mint"])
            if t is None: continue
            tp = TP.token(t)
            m = np.flatnonzero((tp["s"] == o["slot"]) & (tp["i"] == o["idx"]))
            if len(m):
                ok = any(bool(tp["buy"][x]) == bool(o["buy"]) and abs(tp["sol"][x] - o["sol"]) <= 2 for x in m)
                hit = (tag, ok); break
            else:
                hit = (tag, None)
        key = (srv, rn, "token not in recording" if hit is None else (hit[0] + (": trade found" if hit[1] else (": trade MISSING" if hit[1] is None else ": size differs"))))
        c[key] += 1
        if hit and hit[1] is None and len(ex) < 8: ex.append((srv, rn, o["mint"], o["slot"], o["idx"], R.pkt(o["t"])))
for k in sorted(c, key=str): print(k, c[k])
print("examples of missing:", ex)

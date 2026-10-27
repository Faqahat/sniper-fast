#!/usr/bin/env python3
# r10: how much did leaving OUR OWN trades in the tape inflate the paper? Same fires, same size/exit, replay at fixed
# latencies with our real buy/sell kept in the tape (= how dd20/dd1 replays of live hours were built) vs removed.
import sys, os, json
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rlib as R, rsim as S
FIX = 0.0051; FAIL = 0.0005
P = json.load(open(f"{R.WORK}/pertrade.json"))
TPS = {tag: S.Tapes(tag) for tag in ("NEW", "OLD")}
tot = {}
for o in P:
    TP = TPS[o["tape"]]; t, j0 = TP.find(o["mint"], o["dump_slot"], o["dump_idx"], o.get("sell"))
    tp = TP.token(t); cap, sl = o["exit_paper"]
    for L in (0, 20, 35, 50, 75):
        for keep in (False, True):
            res = S.run_path(tp, j0, o["size"], L=L, drop_ours=not keep)
            p = (S.exits(res, cap, sl=sl)[0] - o["size"] - FIX) if res["st"] == 0 else (-FAIL if res["st"] == 1 else 0)
            k = (L, keep, o["live_fill"]); tot[k] = tot.get(k, 0) + p
for L in (0, 20, 35, 50, 75):
    a = tot[(L, False, True)] + tot[(L, False, False)]; b = tot[(L, True, True)] + tot[(L, True, False)]
    print(f"{L:3d} ms: ours removed {a:+.3f} | ours LEFT in the tape {b:+.3f} | inflation {b - a:+.3f} (on live fills {tot[(L, True, True)] - tot[(L, False, True)]:+.3f})")

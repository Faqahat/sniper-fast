#!/usr/bin/env python3
"""NEWSTRAT step 1: round trips (curve only) of the watched wallets, per run -> OUT/trips_<run>.json
A position opens when the wallet's token balance on a mint goes from ~0 to > 0 and closes when it returns to <= 0.5% of its peak.
net = sum of the wallet's lamport deltas over the position's txs (fees, tips, ATA rent outflow included; rent refunds are separate
CloseAccount txs and NOT counted -> net is slightly conservative; 'net_rent' adds back 1.52 mSOL when the first buy paid > 1.9 mSOL
more than its quote, as a rough rent credit)."""
import sys, json
import numpy as np
import nlib as L

WATCH = {"9pQQ": L.W9, "8PgC": L.W8, "OURS": L.OURS,
         "E2x1": "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"}

def trips_for(t, uid, may):
    rows = np.nonzero(t.u == uid)[0]
    out = []
    if len(rows) == 0: return out
    ms = t.m[rows]
    for mi in np.unique(ms):
        rr = rows[ms == mi]
        rr = rr[np.lexsort((t.i[rr], t.s[rr]))]
        bal, peak, cur = 0, 0, None
        for r in rr:
            tk = int(t.tok[r])
            if cur is None:
                if tk <= 0: continue
                cur = dict(mint=str(t.mints[mi]), may=bool(may.get(str(t.mints[mi]), False)), b=int(r), s0=int(t.s[r]), cc0=float(t.cc[r]),
                           nb=0, ns=0, spend=0, net=0, cp0=int(t.cpre[r]))
                bal, peak = 0, 0
            bal += tk; peak = max(peak, bal)
            cur["net"] += int(t.sol[r])
            if tk > 0: cur["nb"] += 1; cur["spend"] += -int(t.sol[r])
            else: cur["ns"] += 1
            if bal <= 0.005 * peak:
                cur.update(x=int(r), s1=int(t.s[r]), cc1=float(t.cc[r]), cq1=int(t.cpost[r]))
                out.append(cur); cur = None; bal = 0
        if cur is not None:
            cur.update(x=None, open=True); out.append(cur)
    return out

if __name__ == "__main__":
    runs = sys.argv[1:] or L.RUNS
    for run in runs:
        t = L.load(run)
        la = L.launches(run)
        may = {m: v["may"] for m, v in la.items()}
        res = {}
        for name, w in WATCH.items():
            uid = t.uix.get(w)
            res[name] = trips_for(t, uid, may) if uid is not None else []
            cl = [x for x in res[name] if x.get("x") is not None]
            print(run, name, "trips", len(cl), "open", len(res[name]) - len(cl), "net SOL", round(sum(x["net"] for x in cl) / 1e9, 2), flush=True)
        json.dump(res, open(f"{L.OUT}/trips_{run}.json", "w"))

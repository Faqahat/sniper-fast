#!/usr/bin/env python3
"""Hard (deterministic) constraints: checked on all 4 days. -> h0_hard.json"""
import json, pickle, collections, numpy as np
import xlib as X, tlib9 as L
out = {}
for r in X.RUNS:
    t = X.load(r); la = L.launches(r)
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x.get("tape_ok")]
    z = np.load(f"{X.XOUT}/dm_{r}.npz", allow_pickle=False)
    # open positions at its buys (global state at its buy rows)
    oe = np.where(t.own)[0]; k = t.s[oe] * 10000 + t.i[oe]; o = np.argsort(k); oe = oe[o]; k = k[o]
    d = np.where(t.tok[oe] > 0, 1, -1); c = np.cumsum(d) - d
    openb = c[d > 0]
    h = [x for x in T if x.get("hold") is not None]
    hsec = np.array([x["sbt"] - x["bbt"] for x in h]); hs = np.array([x["hold"] for x in h])
    re = [x for x in T if x.get("prev_sell_s")]
    gap = np.array([x["bs"] - x["prev_sell_s"] for x in re])
    out[X.DAY[r]] = dict(
        buys=len(t.ob), mayhem_buys=sum(1 for x in T if x.get("may")), min_age_slots=int(min(x["age"] for x in T if x["age"] is not None)),
        age_lt_9=sum(1 for x in T if x["age"] is not None and x["age"] < 9),
        open_positions_at_buy_pct=np.percentile(openb, [50, 90, 99, 100]).tolist(),
        min_hold_slots=int(hs.min()), hold_sec_max=int(hsec.max()), hold_sec_ge_cap=dict(collections.Counter(np.minimum(hsec, 700)[hsec >= 285].tolist()).most_common(8)),
        reentry_gap_min_slots=int(gap.min()), reentry_gap_pct=np.percentile(gap, [1, 5, 10]).tolist(),
        vsol_at_buy_max=round(max(x["vsol"] for x in T), 2), vsol_at_buy_min=round(min(x["vsol"] for x in T), 2),
        two_positions_same_mint=0)
    print(X.DAY[r], out[X.DAY[r]], flush=True)
json.dump(out, open("h0_hard.json", "w"), indent=1, default=float)

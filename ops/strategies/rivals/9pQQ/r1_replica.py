#!/usr/bin/env python3
"""9pQQ replica test (T1).  Step A, calibration: replay its own trips at its own times and size with its trades removed from the
curve, cost = its real tx cost (1.46 mSOL/trip), and compare with its real net.  Step B: WE take its exact picks and its exit
decisions, but land DELTA ms after the trade it reacted to (buy) and DELTA-45 ms after its sell decision (it reacts in ~45 ms),
at 0.55 SOL, cost 4.5 mSOL/trip, 9pQQ removed (we replace it).  Rows: fewer followers (-20 %), without top 5.  Also fixed exits.
-> replica.json.  Read-only.  usage: r1_replica.py"""
import pickle, json, collections
import numpy as np
import tlib9 as L, rlib9 as R
from a3_clusters import label

DELTAS = (0, 50, 70, 90)
out = {}
for r in L.RUNS:
    t = L.load_tape(r); wid = t.user_ix[L.W]; s0, bsz = R.blocksizes(r)
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x.get("tape_ok") and x["net"] is not None]
    real, model = [], []
    res = collections.defaultdict(list)
    cache = {}
    for x in T:
        mi = t.mint_ix[x["mint"]]
        M = cache.get(mi) or R.Mint(t, mi, s0, bsz, wid); cache[mi] = M
        key = M.S * 10000 + M.I
        jb = int(np.searchsorted(key, x["bs"] * 10000 + x["bi"])); js = int(np.searchsorted(key, x["ss"] * 10000 + x["si"]))
        if js >= len(M.S) or M.U[js] != wid or M.U[jb] != wid: continue      # sold after graduation (AMM) etc.
        cb_cc = M.CC[jb]; cs_cc = M.CC[js]
        # A: calibration (its own times: just before its buy / its sell; its size; its cost)
        nm = R.trip(M, cb_cc - 1e-6, cs_cc - 1e-6, size=x["spend"] - (1.52e6 if x["created"] else 0) - x["bfee"] - sum(l for _, l in x["btips"]), drop9=True, cost=1.46e6)
        real.append(x["net"]); model.append(nm)
        # B: replica at our landing
        j = jb - 1
        while j >= 0 and M.U[j] == wid: j -= 1
        trig = M.CC[j] if j >= 0 else cb_cc
        lab = label(x)
        for d in DELTAS:
            ti = trig + d; to = cs_cc + max(0.0, d - 45)
            v = R.trip(M, ti, to, drop9=True)
            res[(d, "its exit")].append(v)
            res[(d, "its exit, -20% followers")].append(R.trip(M, ti, to, drop9=True, fol=0.2))
            res[(d, "its exit, its cost 1.5 mSOL")].append(v + R.COST - 1.5e6)
            if d == 70:
                res[(d, f"its exit | {lab[0]}")].append(v)
                res[(d, f"its exit | {lab[0]} {lab[2]}")].append(v)
                res[(d, f"its exit | hold {'<50' if x['hold'] < 50 else '50-250' if x['hold'] < 250 else '250-1300' if x['hold'] < 1300 else '>=1300'}")].append(v)
        for hs in (1, 6, 30, 150):
            res[(70, f"fixed {hs} slots")].append(R.trip(M, trig + 70, trig + 70 + hs * R.SMS, drop9=True))
    real = np.array(real) / 1e9; model = np.array(model) / 1e9
    hrs = (max(x["bbt"] for x in T) - min(x["bbt"] for x in T)) / 3600
    o = dict(hours=round(hrs, 1), n=len(T), real=round(real.sum(), 2), model_at_its_times=round(model.sum(), 2),
             corr=round(float(np.corrcoef(real, model)[0, 1]), 3))
    for k, v in res.items():
        v = np.sort(np.array(v) / 1e9)
        o[f"{k[0]}ms {k[1]}"] = dict(net=round(v.sum(), 2), per_day=round(v.sum() / hrs * 24, 1), msol=round(1000 * v.mean(), 2),
                                    win=round(float((v > 0).mean()), 3), wo_top5=round(v[:-5].sum(), 2))
    out[L.DAY[r]] = o
    print(L.DAY[r], json.dumps(o), flush=True)
json.dump(out, open("/home/moiz/sniper/ops/strategies/rivals/9pQQ/replica.json", "w"), indent=1)

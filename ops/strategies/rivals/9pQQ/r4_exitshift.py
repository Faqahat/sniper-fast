#!/usr/bin/env python3
"""9pQQ exit timing sensitivity: on its picks (entered by us 70 ms after its trigger, 9pQQ removed), sell at its real sell time
shifted by -5 s .. +5 s.  A sharp peak at shift 0 means its sell moment carries information (e.g. it sells right before dumps).
Also: the curve move in the 25 / 150 slots after its sells vs after random outside trades in its holds.  Read-only.
usage: r4_exitshift.py"""
import pickle, json
import numpy as np
import tlib9 as L, rlib9 as R
SH = (-5000, -2000, -1000, -424, -212, -100, 0, 50, 100, 212, 424, 1000, 2000, 5000)
out = {}
for r in L.RUNS:
    t = L.load_tape(r); wid = t.user_ix[L.W]; s0, bsz = R.blocksizes(r)
    T = [x for x in pickle.load(open(f"{L.OUT}/trips_{r}.pkl", "rb")) if x.get("tape_ok") and x["net"] is not None]
    acc = {s: [] for s in SH}; cache = {}
    for x in T:
        mi = t.mint_ix[x["mint"]]
        M = cache.get(mi) or R.Mint(t, mi, s0, bsz, wid); cache[mi] = M
        key = M.S * 10000 + M.I
        jb = int(np.searchsorted(key, x["bs"] * 10000 + x["bi"])); js = int(np.searchsorted(key, x["ss"] * 10000 + x["si"]))
        if js >= len(M.S) or M.U[js] != wid or M.U[jb] != wid: continue
        j = jb - 1
        while j >= 0 and M.U[j] == wid: j -= 1
        ti = (M.CC[j] if j >= 0 else M.CC[jb]) + 70
        for s in SH: acc[s].append(R.trip(M, ti, max(ti, M.CC[js] - 1e-6 + s), drop9=True))
    o = {str(s): round(np.sum(v) / 1e9, 2) for s, v in acc.items()}
    a25 = np.array([x["after25"] for x in T if "after25" in x]); a150 = np.array([x["after150"] for x in T if "after150" in x])
    o["after_its_sell_25_slots_mean"] = round(float(np.mean(np.clip(a25, -1, 3))), 4); o["after_150_mean"] = round(float(np.mean(np.clip(a150, -1, 3))), 4)
    o["after25_median"] = round(float(np.median(a25)), 4); o["after150_median"] = round(float(np.median(a150)), 4)
    out[L.DAY[r]] = o; print(L.DAY[r], json.dumps(o), flush=True)
json.dump(out, open("/home/moiz/sniper/ops/strategies/rivals/9pQQ/exitshift.json", "w"), indent=1)

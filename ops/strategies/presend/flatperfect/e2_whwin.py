#!/usr/bin/env python3
"""whale-history inputs with a limited look-back (live engine cannot see the multi-day recorded chain): W slots before the trigger.
Out: /home/moiz/sniper-data/flatperfect/dev_wh_{W}.pkl  {key: {wh_*}}  (for the ENGINE_SPEC impact estimate; FROZEN untouched)"""
import os, sys, pickle
os.environ.setdefault("CHAIN_DIR", "/home/moiz/sniper-data/flatperfect/chain")
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/presend/flatperfect")
import numpy as np
import fp1_chain as C
from multiprocessing import Pool
W = int(sys.argv[1])
def wh(u, s, mint64):
    r = C.user_rows(u); r = r[(C.S[r] < s) & (C.S[r] >= s - W)]
    out = {"wh_n": len(r), "wh_mints": 0, "wh_big": 0, "wh_q10": np.nan, "wh_q50": np.nan, "wh_sold_frac": np.nan}
    if not len(r): return out
    mm = C.M[r]; out["wh_mints"] = len(np.unique(mm))
    out["wh_big"] = int(((C.B[r] == 1) & (C.TOK[r] >= 0.06 * C.SUP) & (mm != mint64)).sum())
    holds = []; nb = 0
    for mint in np.unique(mm[(C.B[r] == 1) & (mm != mint64)])[:400]:
        rr = r[mm == mint]; bs = C.S[rr][C.B[rr] == 1]; ss_ = C.S[rr][C.B[rr] == 0]
        if not len(bs): continue
        nb += 1; fb = bs.min(); after = ss_[ss_ >= fb]
        if len(after): holds.append(after.min() - fb)
    if nb:
        out["wh_sold_frac"] = len(holds) / nb
        if holds: h = np.array(holds); out["wh_q10"] = float((h <= 10).mean()); out["wh_q50"] = float((h <= 50).mean())
    return out
def one(p):
    if not p.get("whale") or p.get("trig_slot") is None: return p["key"], None
    return p["key"], wh(C.L.pk64(p["whale"]), p["trig_slot"], C.L.pk64(p["mint"]))
if __name__ == "__main__":
    P = pickle.load(open(sys.argv[2], "rb"))
    with Pool(10) as pool: out = dict(pool.map(one, P, chunksize=50))
    pickle.dump(out, open(sys.argv[3], "wb")); print("done", len(out))

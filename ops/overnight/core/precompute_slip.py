#!/usr/bin/env python3
# Slippage-aware outcome table (same launches and mechanics as precompute_all.py, plus followers' real slippage limits):
# every launch with a guarded fill at 45 / 60 / 75 ms, sizes 0.25 / 0.5 / 1.0 SOL, exits
#   eos1 = after every trade of the slot after our buy (engine --hold-slots 2), t1 / t2 = ~1 s / ~2 s after our buy,
# each WITHOUT ("n") and WITH ("s") the slippage check (a follower our buy pushes past its own min-out / max-cost fails).
# Also per landing: outside buys between our buy and the eos1 sell (real path) and how many our buy would price out.
# Slippage limits are known for follower buys up to buy slot + 10 (~2.1 s); later buys are kept as always-fill.
# usage: python3 -I precompute_slip.py [allres_in] [out]
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
AIN = sys.argv[1] if len(sys.argv) > 1 else "/home/moiz/sniper/ops/overnight/core/allres_static_0034.json"
OUT = sys.argv[2] if len(sys.argv) > 2 else "/home/moiz/sniper/ops/overnight/core/allres_slip.json"
L = rp.load_launches(); O = rp.load_obs(); A = json.load(open(AIN))
todo = [m for m, r in A.items() if any(r.get(k, {}).get("ok") for k in ("45", "75"))]
byb = collections.defaultdict(set)
for m in todo: byb[(A[m]["run"], rp.bucket(m))].add(m)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5), rp.R("t1", [(1.0, ("t", 1.0))], 2), rp.R("t2", [(1.0, ("t", 2.0))], 3)]
SL = None
def init():
    global SL
    SL = rp.load_slip()
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
        r = dict(A[m])
        for Lm in (45, 60, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, [])) if run == "R2" else rp.place_proxy(tr, c, st, Lm)
            if ib < 1: r[str(Lm)] = dict(ok=False); continue
            ok = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01
            d = dict(ok=ok)
            if ok:
                bs = max(c["slot"], tr[ib - 1]["s"])
                win = [t for t in tr[ib:] if t["s"] <= bs + 1]
                d["nb"] = sum(1 for t in win if t["buy"]); d["nb_sol"] = round(sum(t["sol"] for t in win if t["buy"]) / 1e9, 3)
                d["nb_known"] = sum(1 for t in win if t["buy"] and t["sig"] in SL)
                for B in (0.25, 0.5, 1.0):
                    o_n = rp.sim(tr, c, st, ib, B, EX, fill_pen=0.015)
                    o_s = rp.sim(tr, c, st, ib, B, EX, fill_pen=0.015, slip=SL)
                    if not o_n or not o_s: continue
                    d[str(B)] = {ex: [round(o_n[ex]["pnl"], 6), round(o_s[ex]["pnl"], 6)] for ex in ("eos1", "t1", "t2")}
                    d[str(B)]["px"] = [o_s["eos1"]["slipped"], o_s["eos1"]["slipped_sol"]]      # priced out inside the eos1 hold
            r[str(Lm)] = d
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(10, initializer=init) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(res, open(OUT, "w"))
    print("launches:", len(res), dict(collections.Counter(v["run"] for v in res.values())))

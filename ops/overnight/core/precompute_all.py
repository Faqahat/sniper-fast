#!/usr/bin/env python3
# One outcome table for fast strategy experiments: every launch (both runs), the S4 mechanics (1% guard vs post-bundle
# price, sell at the end of the next slot) at 45 / 75 ms for sizes 0.25 / 0.5 / 1.0 SOL. R2 launches with our engine's
# timelines use block-order placement (verifier-matched); R1 (no timelines) uses the block-position proxy.
import sys, json, gzip, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches(); O = rp.load_obs()
todo = [m for m, c in L.items() if c.get("bt") and "InitializeMayhemState" not in (c.get("ixn") or []) and (c["run"] == "R1" or m in O)]
byb = collections.defaultdict(set)
for m in todo: byb[(L[m]["run"], rp.bucket(m))].add(m)
EX = [rp.R("eos1", [(1.0, ("slot", 1))], 5)]
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        if min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]
        r = dict(run=run, bt=c["bt"], dep=c["user"], dev=round(sum(t["sol"] for t in tr if t["sig"] == c.get("sig") and t["buy"]) / 1e9, 3),
                 glued=len(st["glued"]), mc_b=round(p_b * 1e6, 2))
        for Lm in (45, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, [])) if run == "R2" else rp.place_proxy(tr, c, st, Lm)
            if ib < 1: continue
            ok = (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01
            d = dict(ok=ok)
            if ok:
                for B in (0.25, 0.5, 1.0):
                    o = rp.sim(tr, c, st, ib, B, EX, fill_pen=0.015); d[str(B)] = round(o["eos1"]["pnl"], 6) if o else None
            r[str(Lm)] = d
        out[m] = r
    return out
if __name__ == "__main__":
    res = {}
    with Pool(14) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(res, open("allres.json", "w"))
    print("launches:", len(res), dict(collections.Counter(v["run"] for v in res.values())))

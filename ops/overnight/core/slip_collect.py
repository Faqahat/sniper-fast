#!/usr/bin/env python3
# Slippage-aware replay, step 1: the outside BUYS that our replayed buy lands ahead of. For every launch where our
# guarded buy fills at 45, 60 or 75 ms (both runs), list the signatures of the outside buys from our earliest insert
# position to the end of slot (buy slot + SLOTS). Their decoded slippage limits (slip_fetch.py) decide whether each
# would still go through after our buy moved the price.
# usage: python3 -I slip_collect.py [slots=10]  -> slip_sigs.json {mint: [sig, ...]}
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
SLOTS = int(sys.argv[1]) if len(sys.argv) > 1 else 10
L = rp.load_launches(); O = rp.load_obs()
A = json.load(open("/home/moiz/sniper/ops/overnight/core/allres_static_0034.json"))
todo = [m for m, r in A.items() if any(r.get(k, {}).get("ok") for k in ("45", "75"))]
byb = collections.defaultdict(set)
for m in todo: byb[(A[m]["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fa = rp.read_failed(run, b, byb[key]) if run == "R2" else {}; out = {}
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; first = None
        for Lm in (45, 60, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, [])) if run == "R2" else rp.place_proxy(tr, c, st, Lm)
            if ib >= 1 and (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01: first = ib if first is None else min(first, ib)
        if first is None: continue
        bs = max(c["slot"], tr[first - 1]["s"])
        out[m] = [t["sig"] for t in tr[first:] if t["s"] <= bs + SLOTS and t["buy"]]
    return out
if __name__ == "__main__":
    res = {}
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)): res.update(o)
    json.dump(res, open(f"/home/moiz/sniper/ops/overnight/core/slip_sigs_{SLOTS}.json", "w"))
    n = sum(len(v) for v in res.values())
    print(f"launches with a guarded fill: {len(res)}; outside buys after our earliest insert, to buy slot + {SLOTS}: {n} "
          f"({len({s for v in res.values() for s in v})} distinct txs)")

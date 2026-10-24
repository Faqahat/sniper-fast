#!/usr/bin/env python3
# READ-ONLY, offline: how many follower buys (non-insider, after our guarded entry, within 10 s) of our CWiNFA-copy fills
# have a decoded slippage limit in core/slip_args.jsonl (rp.load_slip) - i.e. how complete the slip re-score is.
import os, sys, json, collections
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches(); SL = rp.load_slip(); G = json.load(open(os.path.join(HERE, "walk10.json")))
ms = [m for m, r in G.items() if r["run"] == "R2" and r.get("45")]
byb = collections.defaultdict(set)
for m in ms: byb[rp.bucket(m)].add(m)
n = cov = 0; ncw = 0
for b, mm in byb.items():
    tra = rp.read_bucket("R2", b, mm)
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c); S = c["slot"]
        for t in tr[st["g_end"]:]:
            if t["s"] - S > 50: break
            if t["buy"] and t["user"] not in st["insiders"]:
                n += 1; cov += t["sig"] in SL
print(f"slip map: {len(SL)} decoded follower buys; coverage on these R2 launches (non-insider buys in the first ~10 s): {cov}/{n} = {cov / max(1, n):.0%}")

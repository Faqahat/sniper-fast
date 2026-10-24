#!/usr/bin/env python3
# Follower buys that our replayed buy would land ahead of, for a given pick list (R2 data, RP_PHASEA_R2 decides the
# phase-A copy): every outside buy from our earliest guarded insert (45/60/75 ms) to buy slot + SLOTS, on picks where
# the guard passes at some landing. Output slip_sigs_picks.json for slip_fetch.py (resumable).
# usage: RP_PHASEA_R2=phaseA_dry python3 -I slip_collect_picks.py picks.json [slots=50]
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
PICKS = json.load(open(sys.argv[1])); SLOTS = int(sys.argv[2]) if len(sys.argv) > 2 else 50
L = rp.load_launches(); O = rp.load_obs()
byb = collections.defaultdict(set)
for m in PICKS:
    if m in L and m in O: byb[rp.bucket(m)].add(m)
res = {}
for b, ms in byb.items():
    tra = rp.read_bucket("R2", b, ms); fa = rp.read_failed("R2", b, ms)
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c)
        if st["g_end"] < 1: continue
        ge = tr[st["g_end"] - 1]; p_b = ge["vsol"] / ge["vtok"]; first = None
        for Lm in (45, 60, 75):
            ib, _ = rp.place_bo2(tr, c, st, O[m]["outs"], Lm, fa.get(m, []))
            if ib >= 1 and (tr[ib - 1]["vsol"] / tr[ib - 1]["vtok"]) / p_b <= 1.01: first = ib if first is None else min(first, ib)
        if first is None: continue
        bs = max(c["slot"], tr[first - 1]["s"])
        res[m] = [t["sig"] for t in tr[first:] if t["s"] <= bs + SLOTS and t["buy"]]
json.dump(res, open("/home/moiz/sniper/ops/overnight/core/slip_sigs_picks.json", "w"))
print(f"picks with a guarded fill: {len(res)}; follower buys to buy slot + {SLOTS}: {sum(len(v) for v in res.values())}")

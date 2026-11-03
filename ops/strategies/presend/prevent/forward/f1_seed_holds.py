#!/usr/bin/env python3
"""FORWARD step 1: the hold-clock seed for engine dip28 (--presend-live-holds-state): every wallet of TIMING's history (the holders seen
at our fills, 10-24 19:25 -> 10-30 03:55 PKT, decoded market tapes) with >= 3 completed holds (first buy -> first sell on a mint, slots),
its newest 16, oldest first. The engine's own clock has the same definition. Read-only on TIMING's data.
Out: /home/moiz/sniper-data/prevent/forward/holds_seed.json {"v": 1, "slot": newest first-sell slot, "w": {wallet: [holds]}}"""
import json, numpy as np
D = "/home/moiz/sniper-data/prevent/timing"
P = np.load(f"{D}/pos.npy"); I = json.load(open(f"{D}/hist_ids.json"))
done = P[(P["s1"] >= 0) & (P["s1"] >= P["b0"])]
o = np.lexsort((done["b0"], done["u"])); done = done[o]
ub = np.searchsorted(done["u"], np.arange(len(I["user"]) + 1))
w = {}
for u in range(len(I["user"])):
    a, e = ub[u], ub[u + 1]
    if e - a < 3: continue
    h = (done["s1"][a:e] - done["b0"][a:e]).astype(np.int64)[-16:]
    w[I["user"][u]] = [int(x) for x in h]
out = {"v": 1, "slot": int(done["s1"].max()), "w": w}
json.dump(out, open("/home/moiz/sniper-data/prevent/forward/holds_seed.json", "w"))
print(f"{len(w)} wallets with >= 3 holds (of {len(I['user'])}); newest slot {out['slot']}")

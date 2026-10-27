#!/usr/bin/env python3
# PRE-SEND V2 step c16: the RANDOM CONTROL for the cohort test. 541 random non-cohort wallets, each matched to one cohort wallet by
# its number of buys on the 4 tapes (+-20%, seeded). Writes their tape uids -> presend_v2/control_uids.json.
import sys, os, json, zlib, collections, random
import numpy as np
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import v2data as V
coh = {zlib.crc32(w.encode()) for w in json.load(open("/home/moiz/sniper/ops/overnight/dip/drop_cw.json"))}
cnt = collections.Counter()
for d in V.DAYS:
    t = V.load_day(d, cols=("tok", "buy", "uid", "s", "sol", "tokn", "vsol", "vtok"))
    u = t["uid"][t["buy"].astype(bool)]
    for k, v in zip(*np.unique(u, return_counts=True)): cnt[int(k)] += int(v)
cc = sorted((cnt.get(u, 0), u) for u in coh)
pool = sorted((v, u) for u, v in cnt.items() if u not in coh and v >= 5)
rng = random.Random(7); used = set(); out = []
vals = [v for v, _ in pool]
import bisect
for c, u in cc:
    lo = bisect.bisect_left(vals, max(5, int(c * 0.8))); hi = bisect.bisect_right(vals, max(5, int(c * 1.2)) + 1)
    cand = [pool[i][1] for i in range(lo, hi) if pool[i][1] not in used]
    if not cand: cand = [x for _, x in pool if x not in used][-50:]
    pick = rng.choice(cand); used.add(pick); out.append(pick)
json.dump(out, open(f"{V.OUT}/control_uids.json", "w"))
print(f"cohort wallets on the tapes: {sum(1 for c, _ in cc if c > 0)} of {len(cc)} (buys: total {sum(c for c, _ in cc)}, median {cc[len(cc)//2][0]}); "
      f"control {len(out)} wallets, buys total {sum(cnt[u] for u in out)}")

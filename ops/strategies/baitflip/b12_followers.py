#!/usr/bin/env python3
# For the top bait wallets: who buys within 1 slot after their bait? Same followers every time = own cluster (not organic).
import json, collections, sys
from multiprocessing import Pool
import b1_scan as B
B.RUNS = {**B.RUNS, "R4": ["phaseA_r4"]}
E = json.load(open("/home/moiz/sniper-data/strategies/baitflip/who_trips.json"))
TOP = sys.argv[1].split(",")
EV = collections.defaultdict(list)
for e in E:
    if e[1] in TOP: EV[(e[0], e[3])].append(e)
import zlib
def job(a):
    run, b = a; out = []
    for m, tr in B.read(run, b).items():
        for e in EV.get((run, m), []):
            k = next(i for i, t in enumerate(tr) if t[3] == e[9])
            t = tr[k]
            f = [(z[7], z[1] - t[1] if z[0] == t[0] else 1000 + z[0] - t[0], round(z[9] / 1e9, 2), z[5], z[6]) for z in tr[k + 1:k + 40] if z[7] != t[7] and z[8] and z[0] <= t[0] + 1]
            out.append((e[1], run, m, f))
    return out
if __name__ == "__main__":
    R = []
    with Pool(12) as p:
        for o in p.imap_unordered(job, [(r, b) for r in B.RUNS for b in range(256)]): R += o
    for u in TOP:
        rs = [r for r in R if r[0] == u]
        c = collections.Counter(w for r in rs for w in {x[0] for x in r[3]})
        gaps = [x[1] for r in rs for x in r[3][:1]]
        print(f"\n{u}  baits={len(rs)}  distinct followers={len(c)}  share of baits followed by its top-3 followers: "
              + ", ".join(f"{w[:8]} {100*n/len(rs):.0f}%" for w, n in c.most_common(3)))
        print("   first follower position (tx after bait; 1000+ = next slot):", sorted(gaps)[:20])
        for r in rs[:4]: print("   ", r[1], r[2][:10], [(x[0][:8], x[1], x[2]) for x in r[3][:4]])

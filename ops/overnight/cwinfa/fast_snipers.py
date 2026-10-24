#!/usr/bin/env python3
# READ-ONLY, offline: define FAST SNIPER wallets from our collector data (both runs). Per launch, every non-insider buyer's
# FIRST buy slot relative to the create (insiders = creator, create signer, glued bundle wallets). A wallet is a fast sniper
# if it bought within 2 slots of the create on >= 5 launches AND on >= 50% of the launches it bought at all (first buys).
# Output: fast_snipers.json {wallet: [n_fast, n_launches]} for the qualifying wallets, plus the counts for everyone (gz).
import os, sys, json, gzip, collections
from multiprocessing import Pool
HERE = os.path.dirname(os.path.abspath(__file__))
os.environ["RP_PHASEA_R2"] = os.path.join(HERE, "phaseA_snap")
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
L = rp.load_launches()
byb = collections.defaultdict(set)
for m, c in L.items():
    if c.get("bt") and "InitializeMayhemState" not in (c.get("ixn") or []): byb[(c["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); cnt = collections.defaultdict(lambda: [0, 0])
    for m, tr in tra.items():
        c = L[m]; st = rp.structure(tr, c); S = c["slot"]; first = {}
        for t in tr:
            if not t["buy"] or t["user"] in st["insiders"] or t["user"] in first: continue
            first[t["user"]] = t["s"] - S
        for u, d in first.items():
            x = cnt[u]; x[1] += 1
            if d <= 2: x[0] += 1
    return dict(cnt)
if __name__ == "__main__":
    tot = collections.defaultdict(lambda: [0, 0])
    with Pool(8) as p:
        for o in p.imap_unordered(work, sorted(byb)):
            for u, (a, n) in o.items(): tot[u][0] += a; tot[u][1] += n
    fast = {u: v for u, v in tot.items() if v[0] >= 5 and v[0] / v[1] >= 0.5}
    json.dump(fast, open(os.path.join(HERE, "fast_snipers.json"), "w"))
    with gzip.open(os.path.join(HERE, "buyer_counts.json.gz"), "wt") as f: json.dump(dict(tot), f)
    print(f"buyers: {len(tot)}; fast snipers (>= 5 launches within 2 slots and >= 50% of their launches): {len(fast)}; "
          f"CWiNFA in set: {'CWiNFAEk4M1y6SjvnZkmxWDmhqSmnKFcnop1WoDW3S2J' in fast}")

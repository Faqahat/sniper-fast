#!/usr/bin/env python3
# READ-ONLY, offline: define FAST SNIPER wallets from the collector data (R1 + R2 phase-A rows, SOL-quoted, non-mayhem):
# a wallet's first buy per launch, outside the creator / glued bundle; fast = >= 5 launches with a first buy within 2 slots
# of the create AND >= 50% of its launches bought within 2 slots. -> fast_snipers.json {wallet: [n_fast, n_launches]}
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
from multiprocessing import Pool
L = rp.load_launches()
byb = collections.defaultdict(set)
for m, c in L.items():
    if c.get("bt") and "InitializeMayhemState" not in (c.get("ixn") or []): byb[(c["run"], rp.bucket(m))].add(m)
def work(key):
    run, b = key; tra = rp.read_bucket(run, b, byb[key]); fast = collections.Counter(); tot = collections.Counter()
    for m, tr in tra.items():
        if not tr or min(t["vsol"] for t in tr) < 25e9 or max(t["vsol"] for t in tr[:50]) > 200e9: continue
        c = L[m]; st = rp.structure(tr, c); seen = set()
        for t in tr[st["g_end"]:]:
            if not t["buy"] or t["user"] in st["insiders"] or t["user"] in seen: continue
            seen.add(t["user"]); tot[t["user"]] += 1
            if t["s"] - c["slot"] <= 2: fast[t["user"]] += 1
    return fast, tot
if __name__ == "__main__":
    F = collections.Counter(); N = collections.Counter()
    with Pool(12) as p:
        for f, t in p.imap_unordered(work, sorted(byb)): F.update(f); N.update(t)
    FAST = {w: [F[w], N[w]] for w in F if F[w] >= 5 and F[w] / N[w] >= 0.5}
    json.dump(FAST, open("/home/moiz/sniper/ops/overnight/dkmjeg/fast_snipers.json", "w"))
    print(f"wallets with a first buy on >= 1 launch: {len(N)}; FAST snipers (>= 5 launches within 2 slots and >= 50% of their launches): {len(FAST)}; "
          f"they made {sum(v[0] for v in FAST.values())} fast first-buys; dKMjeG included: {'dKMjeGJ4Mk9S3hxdfTThvZ7exks2xMwWqSM5NvN2CTK' in FAST}")

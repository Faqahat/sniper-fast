#!/usr/bin/env python3
# Stable short IDs for the most active bot wallets, so Haiku can follow the same bot across many tokens ("B17(F4)").
# Pool: the 300 carded 48-h winners (family from s5_families) + R2-only family wallets (p0_lists.py) + the most active
# wallets (>= 50 round trips ~ >= 100 trades in R2+R3). Ranked: carded families first, then by activity. Cap 500 (300 carded + 200 most active others).
# Family label: 48-h family if carded, else R2-only family, else "bot". -> patterns/botids.json {wallet: [id, label]}
import json, gzip, glob, collections
OUT = "/home/moiz/sniper-data/strategies"
fam48 = json.load(open(f"{OUT}/families.json"))["fam_of"]
lr2 = json.load(open(f"{OUT}/patterns/lists_r2.json"))
cnt = collections.Counter()
for f in glob.glob(f"{OUT}/trips/*.jsonl.gz"):
    for l in gzip.open(f, "rt"): cnt[l[2:l.index('"', 2)]] += 1
pool = []
for u in sorted(fam48, key=lambda u: -cnt[u]): pool.append((u, fam48[u]))
seen = {u for u, _ in pool}
for u, c in cnt.most_common():                      # the most active wallets, winners or not (followers are counterparties)
    if c < 50 or len(pool) >= 500: break
    if u not in seen: pool.append((u, lr2[u] if lr2.get(u, "").startswith("F") else "bot")); seen.add(u)
pool = pool[:500]
ids = {u: [k + 1, lab] for k, (u, lab) in enumerate(pool)}
json.dump(ids, open(f"{OUT}/patterns/botids.json", "w"))
print("bot ids", len(ids), collections.Counter(lab for _, lab in ids.values()).most_common())
for k in ("HkQ7hMjy", "haqqiUUX", "DYXDDrZC", "9qz7cWBq", "pXGQ6J2z", "71eD3bS2"):
    print(" ", k, next((v for u, v in ids.items() if u.startswith(k)), None))

#!/usr/bin/env python3
# READ-ONLY, offline: inside each followed dev, launches the 3 wallets bought vs skipped, by the dev's bundle (creator-side buys
# glued after the create, Jito-verified in bundlestudy) and by the other snipers present in the create block.
import json, collections, statistics
D = json.load(open("devs3.json")); BS = {x["mint"]: x for x in json.load(open("bs_devs3.json")) if x}
for dev, L in D.items():
    rows = []
    for x in L:
        b = BS.get(x["mint"])
        if not b: continue
        r = [r for r in b["rows"] if r["buy"] and r["ok"]]
        legs = [q for q in r if q["cls"] in ("glued", "creator-bundle")]
        sn = [q for q in r if q["cls"] == "sniper" and not set(q["users"]) & {"9Sh2fdqMQcec7W9LzzfvkYphrdyR3S8aUBsKdv9xNYa1", "D24ipYXuDt6PXEPV6rZqfWb35WJaTJW3gDoXwt7yJCwQ", "DGmspiBs2ePJ7WgN1pyX5RJDpzhyxYrBN1P4bXNC1NR3"}]
        rows.append(dict(bought=bool(x["bought"]), legs=len(legs), bsol=sum(q["sol"] for q in legs), dev=x["dev_sol"], others=len(sn), osol=sum(q["sol"] for q in sn), cidx=b["cidx"]))
    if not rows: continue
    B = [r for r in rows if r["bought"]]; K = [r for r in rows if not r["bought"]]
    print(f"\ndev {dev[:8]}: {len(rows)} launches with block data ({len(B)} bought, {len(K)} skipped); dev buy median {statistics.median(r['dev'] for r in rows):.2f} SOL")
    def dist(name, fx, bins):
        print(f"   {name}:")
        for lo, hi, lab in bins:
            nb = sum(1 for r in B if lo <= fx(r) < hi); nk = sum(1 for r in K if lo <= fx(r) < hi)
            if nb + nk: print(f"      {lab:14} bought {nb:3} / {nb + nk:3} launches = {nb / (nb + nk):5.0%}")
    dist("dev bundle SOL (creator's glued buys)", lambda r: r["bsol"], ((0, 0.01, "none"), (0.01, 1, "<1"), (1, 2, "1-2"), (2, 3, "2-3"), (3, 4, "3-4"), (4, 5, "4-5"), (5, 7, "5-7"), (7, 1e9, "7+")))
    dist("bundle legs", lambda r: r["legs"], ((0, 1, "0"), (1, 2, "1"), (2, 3, "2"), (3, 4, "3"), (4, 6, "4-5"), (6, 99, "6+")))
    dist("other snipers in the create block", lambda r: r["others"], ((0, 1, "0"), (1, 2, "1"), (2, 4, "2-3"), (4, 99, "4+")))

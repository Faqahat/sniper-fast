#!/usr/bin/env python3
"""CLIENTS study: our landed buys vs the same-token txs right around them in the block (MEASURED, chain_txs.json).
For each client: among same-mint txs within +-6 index of ours that set a CU price, share of those BEFORE us that paid MORE than us
and share of those AFTER us that paid LESS. Price-sorted rounds (BAM) -> both high; arrival order -> both ~ the base rate."""
import json, csv, collections
C = json.load(open("/home/moiz/sniper-data/speed_truth/chain_txs.json"))
A = {r["our_sig"]: r for r in csv.DictReader(open("/home/moiz/sniper-data/speed_truth/attempts.csv"))}
by = collections.defaultdict(list)
for t in C: by[t["s"]].append(t)
agg = collections.defaultdict(lambda: [0, 0, 0, 0])
for t in C:
    if not t.get("ours") or t["sig"] not in A: continue
    r = A[t["sig"]]; mint = r["mint"]; mine = t.get("cup") or 0
    k = r["client"]
    for u in by[t["s"]]:
        if u is t or u.get("cup") is None or mint not in (u.get("mints") or []) or abs(u["i"] - t["i"]) > 6: continue
        if u["i"] < t["i"]:
            agg[k][0] += 1; agg[k][1] += u["cup"] > mine
        else:
            agg[k][2] += 1; agg[k][3] += u["cup"] < mine
for k, (nb, hb, na, la) in sorted(agg.items()):
    print(f"{k:20s} before us: {hb}/{nb} paid more ({hb/max(1,nb):.0%})   after us: {la}/{na} paid less ({la/max(1,na):.0%})")

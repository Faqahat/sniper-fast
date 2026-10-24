#!/usr/bin/env python3
# How many of the claim's dip events / CV-selected trades are on mayhem launches? (launches.jsonl ixn has InitializeMayhemState)
import json, gzip, collections, sys
D = "/home/moiz/sniper-data/collect"
MAY = {}; Q = {}
for run in ("run_20261021_2207", "run_20261022_1543"):
    for l in open(f"{D}/{run}/launches.jsonl"):
        try: c = json.loads(l)
        except Exception: continue
        MAY.setdefault(c["mint"], "InitializeMayhemState" in (c.get("ixn") or []))
print("launches", len(MAY), "mayhem by ixn", sum(MAY.values()))
R = [json.loads(l) for l in gzip.open("snap/ev4_b05.jsonl.gz", "rt")]
c = collections.Counter(MAY.get(r["m"]) for r in R); print("claim events by mayhem flag", c)
for LAT in ("20", "35"):
    v = collections.defaultdict(list)
    for r in R:
        if LAT in r["pnl"]: v[MAY.get(r["m"])].append(r["pnl"][LAT]["4"])
    for k, x in v.items(): print(f"  L{LAT} all events mayhem={k}: n {len(x)} mean {sum(x)/len(x):+.4f} total {sum(x):+.1f}")
for fn in ("out/cv_claim_b05.json", "out/cv_claim_slow.json"):
    S = json.load(open(fn))
    for LAT, d in S.items():
        v = collections.defaultdict(list)
        for s in d["sel"]: v[MAY.get(s["m"])].append(s["pnl"])
        print(f"CV-selected L{LAT}:", {k: (len(x), round(sum(x), 2), round(sum(x)/len(x), 4)) for k, x in v.items()})

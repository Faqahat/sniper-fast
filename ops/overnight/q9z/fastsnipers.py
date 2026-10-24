#!/usr/bin/env python3
# READ-ONLY, offline: the set of FAST SNIPER wallets, defined from the data (owner's rule, 2026-10-23): wallets that bought
# within 2 slots of the create on >= 5 launches AND made >= 50% of their launch buys within 2 slots (creator / dev-bundle
# roles excluded). Source: w1_pairs.py outputs of both runs (pairs = first buy <= 10 slots, other = later / sell-only).
# -> fast_snipers.json [wallets]
import os, json, gzip, glob, collections
HERE = os.path.dirname(os.path.abspath(__file__)); WK = "/home/moiz/sniper-data/work/wallets"
fast = collections.Counter(); early = collections.Counter(); other = collections.Counter()
for run in ("R1", "R2"):
    for f in glob.glob(os.path.join(WK, run, "pairs", "*.jsonl.gz")):
        for l in gzip.open(f, "rt"):
            p = json.loads(l)
            if p.get("role") or p.get("failed_only") or not p.get("nb"): continue
            early[p["w"]] += 1
            if p.get("fs") is not None and p["fs"] <= 2: fast[p["w"]] += 1
    for f in glob.glob(os.path.join(WK, run, "other", "*.jsonl.gz")):
        for l in gzip.open(f, "rt"):
            r = json.loads(l)
            if r[2] > 0: other[r[0]] += r[1]          # launches with a later first buy (bsol > 0)
FS = sorted(w for w, n in fast.items() if n >= 5 and n / (early[w] + other[w]) >= 0.5)
json.dump(FS, open(os.path.join(HERE, "fast_snipers.json"), "w"))
print("wallets with >= 5 fast launches:", sum(1 for n in fast.values() if n >= 5), "| fast snipers (>= 50% of launch buys within 2 slots):", len(FS),
      "| 9qz7cW in set:", "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw" in FS,
      "| its fast/early/other:", fast["9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"], early["9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"], other["9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"])

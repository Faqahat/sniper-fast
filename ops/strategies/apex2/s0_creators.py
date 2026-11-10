#!/usr/bin/env python3
"""APEX2: count standard launches per creator over all built tabs (only decides which launches get simulated; the
history used for decisions is rebuilt walk-forward in a2_eval.py). Out: tab/creator_counts.json"""
import json, glob, collections
C = collections.Counter(); seen = set()
for f in sorted(glob.glob("/home/it/sniper-data/apex2/tab/run_*/creates.json")):
    for m, c in json.load(open(f)).items():
        if c.get("std") and m not in seen: seen.add(m); C[c["creator"]] += 1
json.dump(C, open("/home/it/sniper-data/apex2/tab/creator_counts.json", "w"))
print("creators", len(C), ">=2:", sum(1 for v in C.values() if v >= 2), "launches of >=2:", sum(v for v in C.values() if v >= 2), "all", sum(C.values()))

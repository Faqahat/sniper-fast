#!/usr/bin/env python3
"""Merge seed pool lists (run ON CHERRY): the top bots' pools first, then the fresh multi-venue tokens, then the
current list; dedupe by pool, cap. usage: merge_seeds.py [cap] -> data/seed-pools-w3.csv + counts"""
import csv, sys, os, collections
os.chdir("/root/arb-lab")
CAP = int(sys.argv[1]) if len(sys.argv) > 1 else 1400
VENUES = {"PumpSwap", "DLMM", "DAMMv2", "RayCPMM", "RayAMMv4"}
rows, seen, n = [], set(), collections.Counter()
for name, path in (("bots", "data/seed-pools-bots.csv"), ("fresh", "data/seed-pools-w2.csv"), ("current", "data/seed-pools-w.csv")):
    if not os.path.exists(path): print(f"{path}: missing"); continue
    for r in csv.DictReader(open(path)):
        v, p = (r.get("venue") or "").strip(), (r.get("pool") or "").strip()
        if v not in VENUES or not p or p in seen: continue
        seen.add(p); rows.append((v, p, (r.get("source") or name).strip())); n[name] += 1
rows = rows[:CAP]
with open("data/seed-pools-w3.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["venue", "pool", "source"]); w.writerows(rows)
print(f"seed-pools-w3.csv: {len(rows)} pools (cap {CAP}); taken from: {dict(n)}; by venue: {dict(collections.Counter(r[0] for r in rows))}")

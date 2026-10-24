#!/usr/bin/env python3
# S4G deployer list for the engine's --deployer-list gate: the S4 list minus deployers whose OWN simulated guarded flips
# (0.5 SOL, 1% guard, end-of-next-slot exit, real place in line at 75 ms) average below 0 over >= 3 fills.
# History: the replay table (core/allres.json, both collector runs) + the dry run's trades since 00:35.
import sys, os, json, collections, statistics
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
HERE = os.path.dirname(os.path.abspath(__file__))
L = rp.load_launches()
hist = collections.defaultdict(list); seen = set()
for m, r in json.load(open("/home/moiz/sniper/ops/overnight/core/allres.json")).items():
    o = r.get("75")
    if o and o.get("ok") and o.get("0.5") is not None: hist[r["dep"]].append(o["0.5"]); seen.add(m)
for l in open(os.path.join(HERE, "dryrun_trades.jsonl")):
    t = json.loads(l)
    if t["mint"] in seen: continue
    x = t["land"].get("75")
    if x and x.get("guard_ratio") is not None and x["guard_ratio"] <= 1.01: hist[t["deployer"]].append(x["pnl"]["eos1"])
base = [d.strip() for d in open(os.path.join(HERE, "deployer_list.txt")) if d.strip()]
keep, drop = [], []
for d in base:
    h = hist.get(d, [])
    (drop if (len(h) >= 3 and statistics.mean(h) < 0) else keep).append(d)
open(os.path.join(HERE, "deployer_list_gated.txt"), "w").write("\n".join(keep) + "\n")
print(f"S4 list {len(base)} -> gated {len(keep)} (dropped {len(drop)} deployers with >= 3 losing-on-average fills)")

#!/usr/bin/env python3
# READ-ONLY: every signature of the wallet back to MIN_SLOT (owner's RPC history is ~2 days). -> sigs.json
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from rpcq import rpc
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"; MIN_SLOT = int(sys.argv[1]) if len(sys.argv) > 1 else 459_300_000
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sigs.json")
sigs, before = [], None
while True:
    p = {"limit": 1000}
    if before: p["before"] = before
    r = rpc("getSignaturesForAddress", [W, p])
    if not r: print("empty/none at", len(sigs), flush=True); break
    sigs += r; before = r[-1]["signature"]
    if len(sigs) % 5000 < 1000: print(len(sigs), r[-1]["slot"], r[-1].get("blockTime"), flush=True)
    if r[-1]["slot"] < MIN_SLOT or len(r) < 1000: break
json.dump(sigs, open(OUT, "w"))
print("total", len(sigs), "failed", sum(1 for s in sigs if s.get("err") is not None), "oldest slot", sigs[-1]["slot"] if sigs else None, sigs[-1].get("blockTime") if sigs else None, flush=True)

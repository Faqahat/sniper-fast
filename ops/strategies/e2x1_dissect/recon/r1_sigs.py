#!/usr/bin/env python3
"""recon step 1 (read-only, public RPC): every signature of E2x1 from now back to before W0-24h (getSignaturesForAddress, 1000/page, finalized).
Out: sigs.json (newest first)."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpc
H = "E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb"
W0 = 1793113200; STOP = W0 - 86400 - 1800
OUT = "/home/moiz/sniper-data/e2x1_dissect/recon"
allsigs = []; before = None; page = 0
while True:
    p = {"limit": 1000, "commitment": "finalized"}
    if before: p["before"] = before
    j = rpc.call("getSignaturesForAddress", [H, p]); res = j.get("result")
    if res is None: print("ERR", j); sys.exit(1)
    if not res: break
    allsigs += res; page += 1; before = res[-1]["signature"]; bt = res[-1].get("blockTime")
    print(f"page {page}: {len(res)} slots {res[0]['slot']}..{res[-1]['slot']} last {time.strftime('%m-%d %H:%M:%S', time.gmtime(bt + 18000))} PKT", flush=True)
    if bt is not None and bt < STOP: break
json.dump(allsigs, open(f"{OUT}/sigs.json", "w"))
print("total", len(allsigs), "failed", sum(1 for s in allsigs if s.get("err")))

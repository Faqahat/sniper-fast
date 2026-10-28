#!/usr/bin/env python3
"""8yYMhu step 1 (read-only, public RPC): every signature of the wallet back to its first tx (getSignaturesForAddress, 1000/page,
finalized). Resumable: appends pages to sigs.jsonl; re-run continues from the oldest fetched signature. Out: DATA/sigs.json (newest first)."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rpc
W = "8yYMhuYo1LzgCmeeg3vRkhRtJ8xFC7v7S4ufABtQXjS3"
D = "/home/moiz/sniper-data/rivals/8yYMhu"
STOP = 1792800000          # 10-24 ~13:00 PKT: before the wallet's first tx (10-25 11:28 PKT per devsell/fund.json)
fn = f"{D}/sigs_pages.jsonl"
allsigs = []
if os.path.exists(fn):
    for l in open(fn): allsigs += json.loads(l)
before = allsigs[-1]["signature"] if allsigs else None
page = 0
f = open(fn, "a")
while True:
    p = {"limit": 1000, "commitment": "finalized"}
    if before: p["before"] = before
    j = rpc.call("getSignaturesForAddress", [W, p]); res = j.get("result")
    if res is None: print("ERR", j); sys.exit(1)
    if not res: break
    f.write(json.dumps(res) + "\n"); f.flush()
    allsigs += res; page += 1; before = res[-1]["signature"]; bt = res[-1].get("blockTime")
    print(f"page {page}: {len(res)} slots {res[0]['slot']}..{res[-1]['slot']} last {time.strftime('%m-%d %H:%M:%S', time.gmtime((bt or 0) + 18000))} PKT total {len(allsigs)}", flush=True)
    if len(res) < 1000 or (bt is not None and bt < STOP): break
json.dump(allsigs, open(f"{D}/sigs.json", "w"))
print("total", len(allsigs), "failed", sum(1 for s in allsigs if s.get("err")))

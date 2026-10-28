#!/usr/bin/env python3
"""recon step 1 (read-only, public RPC): every signature of haqq's wallet from just after W1 back to before W0 via
getSignaturesForAddress paging (1000/page, 'finalized'). Raw pages saved. Out: recon/sigs.json (list, newest first)."""
import json, pickle, os, sys, time
sys.path.insert(0, os.path.dirname(__file__))
import rpc
H = "haqqiUUXB5gp7gDbSjpEkw3phAjQb25r86uXJsZQgWq"
W0, W1 = 1793038500, 1793124900
OUT = "/home/moiz/sniper-data/haqq_dissect/recon"
rec = pickle.load(open(f"{OUT}/rec.pkl", "rb"))
after = sorted((d["s"], d["i"], d["sig"]) for d in rec.values() if d["bt"] >= W1 + 120 and d["err"] is None)
before = after[0][2]
print("start before sig", before[:16], "slot", after[0][0], flush=True)
allsigs = []; page = 0
while True:
    j = rpc.call("getSignaturesForAddress", [H, {"limit": 1000, "before": before, "commitment": "finalized"}])
    res = j.get("result")
    if res is None: print("ERR", j); sys.exit(1)
    if not res: break
    allsigs += res; page += 1
    bt_last = res[-1].get("blockTime")
    print(f"page {page}: {len(res)} sigs, slots {res[0]['slot']}..{res[-1]['slot']}, bt_last {time.strftime('%m-%d %H:%M:%S', time.gmtime(bt_last + 18000))} PKT", flush=True)
    before = res[-1]["signature"]
    if bt_last is not None and bt_last < W0 - 300: break
json.dump(allsigs, open(f"{OUT}/sigs.json", "w"))
inw = [s for s in allsigs if s.get("blockTime") is not None and W0 <= s["blockTime"] < W1]
print(f"total {len(allsigs):,}; in window {len(inw):,}; failed in window {sum(1 for s in inw if s.get('err'))}; no blockTime {sum(1 for s in allsigs if s.get('blockTime') is None)}")

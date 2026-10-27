#!/usr/bin/env python3
"""HAQQ_SEL step 0 (read-only, public RPC, 1 call per epoch): leader schedules for epochs 1068 and 1069 in the schedule_cur.json
format (start, ids, slot_leader) -> /home/moiz/sniper-data/haqq_sel/schedule_<epoch>.json (needed by the M2 replay's near-leader flags)."""
import json, urllib.request, time
URL = "https://api.mainnet-beta.solana.com"
def rpc(m, p):
    r = urllib.request.Request(URL, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120))
LEN = 432000
for ep in (1068, 1069):
    START = ep * LEN
    j = rpc("getLeaderSchedule", [START + 10]); sch = j.get("result")
    if not sch: print(ep, "no schedule", str(j)[:200]); continue
    ids = sorted(sch); idx = {k: i for i, k in enumerate(ids)}
    sl = [-1] * LEN
    for k, v in sch.items():
        for o in v: sl[o] = idx[k]
    print(ep, "leaders", len(ids), "missing", sum(1 for x in sl if x < 0))
    json.dump(dict(epoch=ep, start=START, ids=ids, slot_leader=sl), open(f"/home/moiz/sniper-data/haqq_sel/schedule_{ep}.json", "w"))
    time.sleep(1)

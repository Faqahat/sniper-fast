#!/usr/bin/env python3
# Fetch the epoch-1067 leader schedule (read-only public RPC) into the same format as leaders/schedule_cur.json
# (start, ids, slot_leader index list). Out: /home/moiz/sniper-data/competitors2/schedule_1067.json
import json, urllib.request
URL = "https://api.mainnet-beta.solana.com"
def rpc(m, p):
    r = urllib.request.Request(URL, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(),
                               headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=120))["result"]
START = 460944000; LEN = 432000
sch = rpc("getLeaderSchedule", [START + 10])
ids = sorted(sch); idx = {k: i for i, k in enumerate(ids)}
sl = [-1] * LEN
for k, v in sch.items():
    for o in v: sl[o] = idx[k]
assert min(sl) >= 0
json.dump(dict(epoch=1067, start=START, ids=ids, slot_leader=sl), open("/home/moiz/sniper-data/competitors2/schedule_1067.json", "w"))
print("ok", len(ids), "leaders")

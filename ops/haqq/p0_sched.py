#!/usr/bin/env python3
# READ-ONLY, 1 RPC call: leader schedule of epoch 1065 (slots 460,080,000-460,511,999; covers the R2 recording) -> sniper-data/haqq/schedule_1065.json
# in the same format as competitors2/schedule_1067.json (ids + slot_leader index per slot offset). URL read from the config file, never printed.
import json, os, urllib.request
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": "getLeaderSchedule", "params": [460080000]}).encode(), headers={"content-type": "application/json"}), timeout=120))
sched = r["result"]; ids = sorted(sched); idx = {k: n for n, k in enumerate(ids)}
sl = [None] * 432000
for k, v in sched.items():
    for o in v: sl[o] = idx[k]
json.dump(dict(epoch=1065, start=460080000, ids=ids, slot_leader=sl), open("/home/moiz/sniper-data/haqq/schedule_1065.json", "w"))
print("ok", len(ids), sum(1 for x in sl if x is None))

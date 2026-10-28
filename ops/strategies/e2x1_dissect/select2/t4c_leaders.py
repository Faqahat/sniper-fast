#!/usr/bin/env python3
"""select2 t4c: leader schedule for the tape's epochs via public RPC (getLeaderSchedule, one call per epoch) + validator client /
region from sniper-data/leader_geo.json. Out: OUT/leaders.npz (slot4 -> leader id), OUT/leader_meta.json"""
import sys, json, time, urllib.request, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
RPC = "https://api.mainnet-beta.solana.com"
def call(method, params):
    for k in range(6):
        try:
            req = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": method, "params": params}).encode(), headers={"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(req, timeout=120))["result"]
        except Exception as e:
            print("retry", k, e); time.sleep(3 * (k + 1))
S_LO, S_HI = 459790000, 462540000
E0, E1 = S_LO // 432000, S_HI // 432000
leaders = {}; LID = {}
win = np.full((S_HI - S_LO) // 4 + 2, -1, np.int32)
for ep in range(E0, E1 + 1):
    res = call("getLeaderSchedule", [ep * 432000, {"commitment": "finalized"}])
    if not res: print("no schedule for epoch", ep); continue
    n = 0
    for pk, idxs in res.items():
        lid = LID.setdefault(pk, len(LID))
        a = np.asarray(idxs, np.int64) + ep * 432000; a = a[(a >= S_LO) & (a < S_HI)]
        a = a[a % 4 == 0]; win[(a - S_LO) // 4] = lid; n += len(a)
    print("epoch", ep, "leaders", len(res), "windows", n, flush=True); time.sleep(1)
geo = json.load(open("/home/moiz/sniper-data/leader_geo.json"))["rows"]; G = {r["pk"]: r for r in geo}
meta = [None] * len(LID)
for pk, i in LID.items():
    g = G.get(pk, {}); meta[i] = dict(pk=pk, client=g.get("client", "?"), cc=g.get("cc", "?"), rtt=g.get("rtt"), city=g.get("city"))
np.savez(f"{OUT}/leaders.npz", win=win, s_lo=S_LO)
json.dump(meta, open(f"{OUT}/leader_meta.json", "w"))
print("saved", len(LID), "leaders; unknown-geo", sum(m["client"] == "?" for m in meta))

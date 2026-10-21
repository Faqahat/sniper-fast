# READ-ONLY (host; public RPC): the leader of each launch's create slot S (and S+1) + that leader's client (getClusterNodes
# clientId, the same source the engine's --route-by-client uses), for the launches in parse_logs.py's output.
# usage: python3 leaders.py <launches.json> <out leaders.json>
import sys, json, urllib.request

EP = "https://api.mainnet-beta.solana.com"


def rpc(meth, params, ep=EP):
    data = json.dumps({"jsonrpc": "2.0", "id": 1, "method": meth, "params": params}).encode()
    req = urllib.request.Request(ep, data=data, headers={"content-type": "application/json", "user-agent": "curl/8.5.0"})
    return json.load(urllib.request.urlopen(req, timeout=120))["result"]


L = json.load(open(sys.argv[1]))["launches"]
slots = sorted({r["S"] + d for r in L for d in (0, 1)})
ei = rpc("getEpochInfo", [])
start = ei["absoluteSlot"] - ei["slotIndex"]
print(f"epoch {ei['epoch']} start {start}; launch slots {slots[0]}..{slots[-1]}")
assert slots[0] >= start, "a launch is from the previous epoch: extend with getSlotLeaders"
sched = rpc("getLeaderSchedule", [None])
by = {}
for leader, idx in sched.items():
    for i in idx: by[start + i] = leader
nodes = rpc("getClusterNodes", [])
client = {n["pubkey"]: n.get("clientId") for n in nodes}
out = {str(s): [by.get(s), client.get(by.get(s))] for s in slots}
json.dump(out, open(sys.argv[2], "w"))
from collections import Counter
print(Counter(v[1] for k, v in out.items()).most_common())

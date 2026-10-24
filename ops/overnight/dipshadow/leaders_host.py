#!/usr/bin/env python3
# READ-ONLY RPC: leader book for the data period (epochs of the given slots): slot -> leader -> client class (getClusterNodes
# clientId/version, as ops/gap/leaders.py). RPC = owner's endpoint (~/.config/sniper/ck_rpc_url, never printed).
# usage: python3 -I leaders_host.py OUT.json slot1 [slot2 ...]
import sys, os, json, urllib.request
EP = open(os.path.expanduser("~/.config/sniper/ck_rpc_url")).read().strip()
def rpc(m, p=None):
    r = json.load(urllib.request.urlopen(urllib.request.Request(EP, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p or []}).encode(),
                                                                headers={"content-type": "application/json"}), timeout=120))
    if "error" in r: print(m, "error:", r["error"].get("message")); return None
    return r["result"]
def klass(c, ver):
    c = c or ""
    if "Bam" in c or "BAM" in c: return "bam"
    if "Harmonic" in c: return "harmonic"
    if c == "JitoLabs": return "jito"
    if "dancer" in c: return "fd"
    if c == "Agave": return "agave"
    if not c and ver:
        try:
            m = int(ver.split(".")[0]); return "fd" if (m == 0 or m >= 26) else "agave?"
        except Exception: pass
    return "other" if c else "unknown"
out = sys.argv[1]; sched = {}
for s in sorted({int(x) // 432000 * 432000 for x in sys.argv[2:]}):
    r = rpc("getLeaderSchedule", [s])
    print("epoch first slot", s, "schedule", "ok" if r else "missing")
    if r:
        for ident, idxs in r.items():
            for i in idxs: sched[s + i] = ident
nodes = {}
for n in rpc("getClusterNodes") or []:
    nodes[n["pubkey"]] = {"ver": n.get("version"), "client": n.get("clientId"), "class": klass(n.get("clientId"), n.get("version"))}
json.dump({"leaders": {str(k): v for k, v in sched.items()}, "nodes": nodes}, open(out, "w"))
import collections
c = collections.Counter(nodes.get(i, {}).get("class", "unknown") for i in sched.values())
print(len(sched), "slots,", len(nodes), "nodes; slot share:", {k: round(v / len(sched), 3) for k, v in c.most_common()})

# READ-ONLY: launches by create-slot leader RTT from our Frankfurt box (geo_rtt.json, ICMP): share of launches, and how
# often any outsider lands d<=25 / in slot S at all.
import sys, json, os
g = json.load(open("/root/lat/geo_rtt.json"))
n = {x["pubkey"]: x for x in json.load(open("/root/stakepaths/clusternodes.json"))["result"]}
def rtt(slot):
    p = f"/root/jitolate/cache/ldr_{slot}.json"
    if not os.path.exists(p): return None
    pk = json.load(open(p))[0]
    ip = (n.get(pk, {}).get("gossip") or "").split(":")[0]
    return g.get(ip)
R = [json.loads(l) for f in sys.argv[1:] for l in open(f)]
B = [("<5", 0, 5), ("5-40", 5, 40), ("40-100", 40, 100), (">100", 100, 1e9)]
tot = len(R)
for name, lo, hi in B + [("unknown", None, None)]:
    gg = [r for r in R if (rtt(r["slot"]) is None if lo is None else (rtt(r["slot"]) is not None and lo <= rtt(r["slot"]) < hi))]
    if not gg: continue
    a = sum(1 for r in gg if any(w["ok"] and w["d"] <= 25 for w in r["out"]))
    print(f"  leader RTT {name:8} ms: launches {len(gg):3} ({len(gg)/tot:.0%})  outsider d<=25: {a} ({a/len(gg):.0%})")

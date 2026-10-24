#!/usr/bin/env python3
"""verify2 / a6: the shadow engine's own RACE decide / obs lines for the picks (old_bundle_n/_sol = txs the engine absorbed as
'bundle' by decision time via its 3 ms / creator-signer rule; these never appear in outs)."""
import sys, os, json, re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import v2core as V
P = set(V.load_picks()); KV = re.compile(r"(\w+)=(\S*)"); out = {}
for line in open("/home/moiz/sniper-data/collect/shadow/engine_v3.log", errors="replace"):
    if "RACE decide" not in line and "RACE obs" not in line: continue
    i = line.find("mint=")
    if i < 0: continue
    m = line[i + 5:i + 5 + 50].split()[0]
    if m not in P: continue
    d = dict(KV.findall(line.split(" outs=")[0]))
    out.setdefault(m, {})["decide" if "RACE decide" in line else "obs"] = d
json.dump(out, open(os.path.join(V.WORK, "a6_engine.json"), "w"))
n = sum(1 for v in out.values() if "decide" in v); print("picks with decide line", n, "obs line", sum(1 for v in out.values() if "obs" in v))
ex = [(m, v["decide"].get("bundle_n"), v["decide"].get("old_bundle_n"), v["decide"].get("bundle_sol"), v["decide"].get("old_bundle_sol"), v.get("obs", {}).get("bundle_n"))
      for m, v in out.items() if "decide" in v and int(v["decide"].get("old_bundle_n", 0) or 0) > int(v["decide"].get("bundle_n", 0) or 0)]
print("picks where the engine absorbed more txs than the glued bundle (old_bundle_n > bundle_n):", len(ex))
for e in ex[:60]: print("  ", e[0][:10], "glued", e[1], e[3], "| absorbed", e[2], e[4], "| obs bundle_n", e[5])
later = [(m, v["decide"].get("bundle_n"), v["obs"].get("bundle_n")) for m, v in out.items() if "decide" in v and "obs" in v and v["obs"].get("bundle_n") != v["decide"].get("bundle_n")]
print("picks with more absorbed txs after the decision (obs bundle_n > decide bundle_n):", len(later), later[:20])

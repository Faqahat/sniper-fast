#!/usr/bin/env python3
"""Our live same-slot buys (race/live_fires.jsonl): time after the create from position (d x slot_ms / non-vote txs),
the create's position in the slot, leader identity/client/RTT (getSlotLeaders + leaders.json nodes + geo_rtt)."""
import json, sys, urllib.request, os
sys.path.insert(0, "/root/gap")
from leaders import rpc
ME = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
SLOT_MS = float(sys.argv[1]) if len(sys.argv) > 1 else 203.5
L = json.load(open("/root/gap/leaders.json")); nodes = L["nodes"]
rows = []
for l in open("/root/race/live_fires.jsonl"):
    r = json.loads(l); b = r["b"]
    for t in b.get("later") or []:
        if t.get("payer") == ME and t.get("ok"):
            rows.append((b["slot"], b["nnv"], b["cnv"], t["d"], [x[0] for x in t.get("tips") or []] or ["none"]))
            break
out = []
for slot, nnv, cnv, d, tips in rows:
    try: lid = rpc("getSlotLeaders", [slot, 1])[0]
    except Exception as e: lid = None
    n = nodes.get(lid, {})
    ms = d * SLOT_MS / nnv; cpos = cnv * SLOT_MS / nnv
    out.append({"slot": slot, "d": d, "nnv": nnv, "ms_after_create": round(ms, 1), "create_at_ms": round(cpos, 1),
                "leader": (lid or "?")[:8], "client": n.get("client"), "class": n.get("class"), "rtt_ms": n.get("rtt_ms"), "city": n.get("city"), "paths": tips})
json.dump(out, open("/root/gap/livebuys.json", "w"), indent=1)
for o in sorted(out, key=lambda o: o["ms_after_create"]):
    print(f"{o['slot']} d={o['d']:4d}/{o['nnv']:5d} -> {o['ms_after_create']:6.1f} ms after create (create at {o['create_at_ms']:5.1f} ms) leader {o['leader']} {o['client']} rtt {o['rtt_ms']} {o['city']} via {','.join(o['paths'])}")

#!/usr/bin/env python3
# "if our buy executed D ms earlier": place it before every chain trade our feed saw after (our_seen - D)
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from sim import *
TP = load_tapes("/home/moiz/sniper/ops/agents/freshaudit/out/tapes_live.json.gz")
FC = [x for x in json.load(open("/home/moiz/sniper/ops/agents/freshaudit/out/fire_chain.json")) if "dump" in x and "ours" in x]
TT = json.load(open("/home/moiz/sniper/ops/agents/freshaudit/out/tape_timing.json"))
out = collections.defaultdict(lambda: [0, 0, 0.0, 0.0])
rows = []
for r in TT:
    f = [x for x in FC if x["mint"] == r["mint"] and x["dump"]["i"] == r["di"]]
    if not f: continue
    f = f[0]; d = f["dump"]; o = f["ours"]
    tr = trades(TP[r["mint"]], drop_user=OURS)
    dst = None
    for t in trades(TP[r["mint"]]):
        if (t[0], t[1]) == (d["s"], d["i"]) and t[3] == 0: dst = (t[7], t[8]); fr = (t[9] + t[10]) / 1e4
    seen = {(c["s"] + d["s"], c["i"]): c["ms"] for c in r["comp"]}
    B = f["spend"] / 1e9
    rec = dict(mint=r["mint"], res=f["result"], rtt=r["rtt"], client=r["client"])
    for D in (0, 5, 10, 15, 20, 25, 30, 40):
        cut = r["seen_ms"] - D
        pos = (o["s"], o["i"])
        for t in tr:
            p = (t[0], t[1])
            if p <= (d["s"], d["i"]) or p >= (o["s"], o["i"]): continue
            ms = seen.get(p)
            if ms is not None and ms >= cut: pos = (p[0], p[1]); break
        x = simulate(tr, pos, dst, B, guard=1.05, exit_mode=("time", 5, 100), fr=fr, tip=f["tips"])
        y = simulate(tr, pos, dst, B, guard=1.15, exit_mode=("time", 5, 100), fr=fr, tip=f["tips"])
        o_ = out[D]; o_[0] += 1; o_[1] += x["fill"]; o_[2] += x["pnl_net"]; o_[3] += y["pnl_net"]
        rec[D] = (x["fill"], round(x["pnl_net"], 4))
    rows.append(rec)
print("fires with feed timing:", len(rows))
print("D_ms  fires  fills(g5%)  net_SOL(g5%)  net_SOL(g15%)")
for D, v in sorted(out.items()):
    print(f"{D:>4} {v[0]:>6} {v[1]:>8} {v[2]:>+12.4f} {v[3]:>+12.4f}")
json.dump(rows, open("/home/moiz/sniper/ops/agents/freshaudit/out/cf_speed.json", "w"))

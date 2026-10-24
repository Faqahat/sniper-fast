#!/usr/bin/env python3
# size sensitivity: replay our 68 fires at their actual landing positions (and first-in-line) with different buy sizes
import sys, json, collections
sys.path.insert(0, "/home/moiz/sniper/ops/agents/freshaudit")
from sim import *
A = "/home/moiz/sniper/ops/agents/freshaudit"
TP = load_tapes(f"{A}/out/tapes_live.json.gz")
FC = [x for x in json.load(open(f"{A}/out/fire_chain.json")) if "dump" in x and "ours" in x]
SIZES = [0.1, 0.25, 0.35, 0.5, 0.75, 1.0, 1.5, 2.0]
tot = collections.defaultdict(float); fills = collections.Counter()
per = []
for f in FC:
    rows = TP[f["mint"]]; tr = trades(rows, drop_user=OURS); d = f["dump"]; o = f["ours"]
    for t in trades(rows):
        if (t[0], t[1]) == (d["s"], d["i"]) and t[3] == 0: dst = (t[7], t[8]); fr = (t[9] + t[10]) / 1e4
    rec = dict(mint=f["mint"], res=f["result"])
    for B in SIZES:
        for nm, pos in (("act", (o["s"], o["i"])), ("first", (d["s"], d["i"] + 1))):
            r = simulate(tr, pos, dst, B, guard=1.05, exit_mode=("time", 5, 100), fr=fr, tip=3_000_000)
            tot[(nm, B)] += r["pnl_net"]; fills[(nm, B)] += r["fill"]
            rec[f"{nm}_{B}"] = round(r["pnl_net"], 5)
    per.append(rec)
print("68 fires, time exit (land+5 slots), tips 0.003+0.001, SOL totals over 3.68 h")
for nm in ("act", "first"):
    print(nm, "  ".join(f"B={B}: {tot[(nm,B)]:+.3f} ({fills[(nm,B)]}f, {tot[(nm,B)]/max(1,fills[(nm,B)])/B*100:+.1f}%/fill)" for B in SIZES))
json.dump(per, open(f"{A}/out/cf_size.json", "w"))

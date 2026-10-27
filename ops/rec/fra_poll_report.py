#!/usr/bin/env python3
# per-minute deltas of FRA collector counters from state/fra_poll.jsonl (read-only poller samples)
import json, time, sys
rows = [json.loads(l) for l in open(sys.argv[1] if len(sys.argv) > 1 else "/home/moiz/sniper-data/rec/state/fra_poll.jsonl")]
prev = None
for r in rows:
    t = time.strftime("%H:%M", time.gmtime(r["t"] + 18000)); out = []
    for run, v in sorted(r["runs"].items()):
        s = v["stats"]
        if prev and run in prev["runs"]:
            p = prev["runs"][run]["stats"]; d = lambda k: s.get(k, 0) - p.get(k, 0)
            out.append(f"{run[-9:]} {str(v['phase'])[:16]:16s} ck_getBlock {d('blk_ep2'):4d} 429 {d('blk_http429_ep2'):3d} | rpc {d('rpc_calls'):4d} 429 {d('rpc_429'):3d} | shyft429 {d('blk_http429_ep0')}")
        else: out.append(f"{run[-9:]} {str(v['phase'])[:16]:16s} (first sample)")
    print(t, " || ".join(out)); prev = r

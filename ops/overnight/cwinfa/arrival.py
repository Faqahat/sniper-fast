#!/usr/bin/env python3
# READ-ONLY, offline: CWiNFA's arrival time in OUR engine's clock (shadow "obs" timelines, ms after the create). Its buys go
# through its own router, so our engine logs them undecoded ("0.000:0"); its first logged tx on a launch is its buy.
import os, sys, json, statistics, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/core")
import rp
SH = "/home/moiz/sniper-data/collect/shadow"
O = rp.load_obs([os.path.join(SH, "scores_v1.jsonl"), os.path.join(SH, "scores_v2.jsonl"), os.path.join(HERE, "scores_v3_snap.jsonl")])
C = json.load(open(os.path.join(HERE, "coll_cw.json")))
rows = []
for m, v in C.items():
    if m not in O or not v.get("buy"): continue
    outs = sorted(O[m]["outs"]); mine = [o for o in outs if o[3] == "CWiNFA"]
    if not mine: continue
    a = mine[0][0]
    rows.append(dict(m=m, ms=a, ds=v["buy"]["ds"], ahead=v["buy"]["ahead_tx"], seen_before=sum(1 for o in outs if o[0] < a and o[3] != "CWiNFA" and (o[2] or o[1] == 0))))
fails = []
for m, v in C.items():
    if m in O and not v.get("buy") and v.get("failed"):
        mine = [o for o in sorted(O[m]["outs"]) if o[3] == "CWiNFA"]
        if mine: fails.append(mine[0][0])
q = lambda xs, p: sorted(xs)[int(p * (len(xs) - 1))]
ms = [r["ms"] for r in rows]
L = [f"filled buys in R2 with our engine's timeline: {sum(1 for m, v in C.items() if m in O and v.get('buy'))}; CWiNFA logged by our engine on {len(rows)}",
     f"arrival ms (our clock): p10 {q(ms, .1):.1f} | p25 {q(ms, .25):.1f} | median {statistics.median(ms):.1f} | p75 {q(ms, .75):.1f} | p90 {q(ms, .9):.1f}",
     f"share arriving before 45 ms {sum(x < 45 for x in ms) / len(ms):.0%}, before 75 ms {sum(x < 75 for x in ms) / len(ms):.0%}"]
for ds in (0, 1, 2):
    xs = [r["ms"] for r in rows if min(r["ds"], 2) == ds]
    if xs: L.append(f"  slot delta {ds}{'+' if ds == 2 else ''}: n {len(xs)}, median {statistics.median(xs):.1f} ms")
for a in (0, 1, 2, 3):
    xs = [r["ms"] for r in rows if min(r["ahead"], 3) == a]
    if xs: L.append(f"  outside buys ahead {a}{'+' if a == 3 else ''}: n {len(xs)}, median {statistics.median(xs):.1f} ms")
if fails: L.append(f"failed-only attempts logged by our engine: n {len(fails)}, median arrival {statistics.median(fails):.1f} ms")
open(os.path.join(HERE, "arrival.txt"), "w").write("\n".join(L) + "\n"); print("\n".join(L))
json.dump(rows, open(os.path.join(HERE, "arrival_ms.json"), "w"))

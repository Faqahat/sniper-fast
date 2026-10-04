#!/usr/bin/env python3
"""Validate the anchor: in the slots of our trades, every transaction's lateness (first arrival - (slot offset + PoH
ms)) vs the triggers'. Also per feed: lateness of the first copy per feed, and how lateness grows with PoH ms in the
slot (shreds delivered in bursts?). usage: latency2.py <seg>"""
import json, sys, os, subprocess, collections
HERE = os.path.dirname(os.path.abspath(__file__))
exec(open(os.path.join(HERE, "latency.py")).read().split("rows = []")[0])
seg = sys.argv[1]
A = {x["attempt"]: x for x in map(json.loads, lines(seg, "attempts.jsonl"))}
O = {x["attempt"]: x for x in map(json.loads, lines(seg, "outcomes.jsonl"))}
meta = json.load(open(os.path.join(seg, "meta.json"))); F = meta["feeds"]
slots = {o["poh"]["trigger"]["slot"] for o in O.values() if (o.get("poh") or {}).get("trigger")}
trig8 = {sig8(a["trigger"]): i for i, a in A.items()}
pohms = {}
for l in lines(seg, "poh.log"):
    p = l.split()
    if len(p) == 3 and int(p[1]) in slots and p[0] not in pohms: pohms[p[0]] = (int(p[1]), float(p[2]))
per = collections.defaultdict(list)
for l in lines(seg, "txarr.log"):
    p = l.split()
    if len(p) < 3 + len(F) or p[0] not in pohms: continue
    slot, ms = pohms[p[0]]
    per[slot].append((ms, int(p[2]) / 1e6, p[3:3 + len(F)], p[0]))
late_all, late_trig, by_pos = [], [], collections.defaultdict(list)
feed_late = collections.defaultdict(list)
for slot, xs in per.items():
    off = min(t - ms for ms, t, _, _ in xs)
    for ms, t, d, s8 in xs:
        x = t - off - ms
        late_all.append(x); by_pos[int(ms // 50) * 50].append(x)
        for i, v in enumerate(d):
            if v != "-": feed_late[F[i]].append(x + int(v) / 1000)
        if s8 in trig8: late_trig.append(x)
print(seg, "slots", len(per), "txs", len(late_all))
print("  lateness ALL txs   p10/p50/p90", q(late_all, .1), q(late_all, .5), q(late_all, .9))
print("  lateness TRIGGERS  p10/p50/p90", q(late_trig, .1), q(late_trig, .5), q(late_trig, .9), "n", len(late_trig))
print("  lateness by PoH position in slot:", {k: (len(v), q(v, .5)) for k, v in sorted(by_pos.items())})
print("  lateness by feed (each feed's own copy):", {f: q(v, .5) for f, v in feed_late.items()})

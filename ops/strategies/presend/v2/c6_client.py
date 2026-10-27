#!/usr/bin/env python3
# PRE-SEND V2 step c6 (c): does landing differ by leader client? MEASURED on the probe (AMS r16): per >= 2% dump in an armed window,
# the first attempt that could fill it (signed before we saw the dump, not a deadline failure), by the client of the dump's slot;
# and the probe's per-attempt results by client (6042 / deadline / unseen).
import json, collections
import numpy as np
F = "/home/moiz/sniper-data/runs/ams/runs/dip_ams_r16.jsonl"
att = {}; land = {}
for l in open(F):
    if '"presend_attempt' not in l: continue
    o = json.loads(l)
    if o["ev"] == "presend_attempt": att[o["sig"]] = o
    else: land[o["sig"]] = o
byw = collections.defaultdict(list); slot_client = {}
for s, a in att.items():
    l = land.get(s); byw[a["w"]].append((a, l))
    if l and l.get("slot") is not None and l.get("client"): slot_client[l["slot"]] = l["client"]
dumps = {}
for l in land.values():
    d = l.get("d")
    if d and d.get("a"): dumps[(l["w"], d["slot"], d["idx"])] = d
res = collections.defaultdict(list)
for (w, s, i), d in dumps.items():
    seen = d.get("first_rx", d["t"]) / 1e6; X = d["a"]
    c = [l["a"] for a, l in byw[w] if l and l.get("res") not in ("unseen", "deadline") and l.get("a") and l["a"] > X and a["t"] / 1e6 < seen]
    cl = slot_client.get(s, "?")
    res[cl].append(min(c) - X if c else None)
out = {}
for cl, v in sorted(res.items(), key=lambda kv: -len(kv[1])):
    fin = [x for x in v if x is not None]
    out[cl] = dict(n=len(v), none=1 - len(fin) / len(v), p50=float(np.median(fin)) if fin else None)
    print(f"{cl:20s} dumps {len(v):3d} | no attempt could fill {100 * (1 - len(fin) / len(v)):4.0f}% | first landing p25 {np.percentile(fin, 25) if fin else 0:5.1f} p50 {np.median(fin) if fin else 0:5.1f} p75 {np.percentile(fin, 75) if fin else 0:5.1f} ms")
rc = collections.defaultdict(collections.Counter)
for s, a in att.items():
    l = land.get(s); rc[a.get("client") or "?"][(l or {}).get("res", "none")] += 1
for cl, c in sorted(rc.items(), key=lambda kv: -sum(kv[1].values())):
    n = sum(c.values()); print(f"  attempts {cl:20s} {n:5d}: deadline {100 * c['deadline'] / n:4.1f}% unseen {100 * c['unseen'] / n:4.1f}%")
json.dump(out, open("/home/moiz/sniper-data/presend_v2/c6_client.json", "w"))

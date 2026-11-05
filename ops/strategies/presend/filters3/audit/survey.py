#!/usr/bin/env python3
"""survey one run's presend records: event counts, skip/disarm reasons, config per run_start, annotation keys. read-only."""
import sys, json, collections
p = sys.argv[1]; out = sys.argv[2]
ev = collections.Counter(); skip = collections.Counter(); dis = collections.Counter(); ex = collections.Counter()
keys = collections.defaultdict(collections.Counter); starts = []; other = collections.Counter(); samples = {}
for line in open(p, errors="replace"):
    try: d = json.loads(line)
    except Exception: other["badjson"] += 1; continue
    e = d.get("ev"); ev[e] += 1
    if e not in samples: samples[e] = line[:3000]
    if e == "run_start" or e == "run_end": starts.append(d)
    elif e == "presend_live_skip": skip[(d.get("kind", "t2"), d.get("why"))] += 1
    elif e == "presend_live_disarm": dis[(d.get("kind", "t2"), d.get("why"))] += 1
    elif e == "presend_live_exit": ex[d.get("why")] += 1
    if e in ("presend_live_fill", "presend_live_arm", "presend_live_skip", "presend_arm", "presend_live_realized", "presend_live_tape", "presend_live_close", "presend_disarm", "presend_exit", "presend_fill", "presend_wide_arm", "presend_wide_exit"):
        for k, v in d.items():
            keys[e][k] += 1
            if isinstance(v, dict):
                for k2 in v: keys[e][k + "." + k2] += 1
json.dump({"ev": ev, "skip": {f"{a}|{b}": n for (a, b), n in skip.items()}, "disarm": {f"{a}|{b}": n for (a, b), n in dis.items()}, "exit": ex,
           "keys": keys, "starts": starts, "samples": samples}, open(out, "w"), indent=1, default=str)

#!/usr/bin/env python3
"""EXIT-125v200 step 3: first-seen rx time of each slot around every fill (fill slot .. +7), from the engine's own race_tx samples
(obs files) + dump events (jsonl). Used for slot-N exits (decision = the engine seeing slot fill+N) and slot timing stats.
Out: slotmap.json {slot: [first_t_ns, first_idx, n_samples]}"""
import json, re, glob, sys
D = "/home/moiz/sniper-data/filters3/exit125"
R = "/home/moiz/sniper-data/runs"
F = json.load(open(f"{D}/fills.json"))["fills"]
need = set()
for x in F:
    for k in range(-1, 9): need.add(x["slot"] + k)
pat = re.compile(rb'"slot":(\d+)')
pt = re.compile(rb'"t":(\d{19})')
pi = re.compile(rb'"idx":(\d+)')
M = {}
files = []
for r in [42, 43, 44, 45, 46, 47, 48]:
    files += sorted(glob.glob(f"{R}/ams/runs/dip_ams_r{r}.obs.jsonl*")) + [f"{R}/ams/runs/dip_ams_r{r}.jsonl"]
files += sorted(glob.glob(f"{R}/ams_r49/dip_ams_r49.obs.jsonl*")) + [f"{R}/ams_r49/dip_ams_r49.jsonl", f"{R}/ams_r50/dip_ams_r50.jsonl"]
for fn in files:
    n = 0
    with open(fn, "rb") as f:
        for line in f:
            if b'"ev":"race_tx"' not in line and b'"ev":"dump"' not in line: continue
            m = pat.search(line)
            if not m: continue
            s = int(m.group(1))
            if s not in need: continue
            mt = pt.search(line)
            if not mt: continue
            t = int(mt.group(1)); mi = pi.search(line); i = int(mi.group(1)) if mi else -1
            c = M.get(s)
            if c is None: M[s] = [t, i, 1]
            else:
                c[2] += 1
                if t < c[0]: c[0], c[1] = t, i
            n += 1
    print(fn.split("/")[-1], n, flush=True)
json.dump(M, open(f"{D}/slotmap.json", "w"))
print("slots", len(M), "of needed", len(need))

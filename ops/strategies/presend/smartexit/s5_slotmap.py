#!/usr/bin/env python3
"""SMARTEXIT step 5: first-seen rx time of each slot fill-1 .. fill+16 for every fill, from race_tx / dump samples in the run's
jsonl + obs files (same method as filters3/exit125/x3_slotmap.py, which is reused for runs it already covered).
Out: /home/it/sniper-data/smartexit/slotmap.json {slot: [first_t_ns, first_idx, n]}"""
import json, re, glob, sys, os
O = "/home/it/sniper-data/smartexit"; R = "/home/it/sniper-data/runs"
S = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad"
F = json.load(open(f"{O}/fills.json"))["fills"]
need = set()
for x in F:
    for k in range(-1, 17): need.add(x["slot"] + k)
pat = re.compile(rb'"slot":(\d+)'); pt = re.compile(rb'"t":(\d{19})'); pi = re.compile(rb'"idx":(\d+)')
M = {}
def files(r):
    if r <= 48: b = f"{R}/ams/runs/dip_ams_r{r}"
    elif r <= 54: b = f"{R}/ams_r{r}/dip_ams_r{r}"
    else: return sorted(glob.glob(f"{S}/r55/dip_ams_r55.obs.jsonl*")) + [f"{R}/ams_r55_snap/dip_ams_r55.obs.jsonl", f"{S}/r55/dip_ams_r55.jsonl"]
    return sorted(glob.glob(b + ".obs.jsonl*")) + [b + ".jsonl"]
for r in range(37, 56):
    for fn in files(r):
        n = 0
        with open(fn, "rb") as f:
            for line in f:
                if b'"ev":"race_tx"' not in line and b'"ev":"dump"' not in line and b'"ev":"hold_tape"' not in line: continue
                if b'"ev":"hold_tape"' in line:
                    # every tape trade carries its own slot + rx t
                    for m in re.finditer(rb'"slot":(\d+),"sol":\d+,"t":(\d{19})', line):
                        s = int(m.group(1)); t = int(m.group(2))
                        if s in need:
                            c = M.get(s)
                            if c is None: M[s] = [t, -1, 1]
                            else:
                                c[2] += 1
                                if t < c[0]: c[0] = t
                    continue
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
        print(r, fn.split("/")[-1], n, flush=True)
json.dump(M, open(f"{O}/slotmap.json", "w"))
print("slots", len(M), "of needed", len(need))

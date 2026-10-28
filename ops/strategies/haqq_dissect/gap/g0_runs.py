#!/usr/bin/env python3
"""GAP step 0 (read-only): inventory of every live run record: start/end (PKT), config, event counts. Out: gap/g0_runs.json, g0_runs.txt"""
import json, glob, re, collections, sys, time
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
from runs import run_files
OUT = "/home/moiz/sniper-data/haqq_dissect/gap"
pkt = lambda t: time.strftime("%m-%d %H:%M", time.gmtime(int(t) + 18000))
def tsec(t): return t / 1e9 if t and t > 1e15 else t
R = {}
for run, f in run_files().items():
    c = collections.Counter(); st = en = None; cfg = None; keys = {}
    for l in open(f):
        try: d = json.loads(l)
        except Exception: continue
        e = d.get("ev"); c[e] += 1; t = tsec(d.get("t"))
        if t and t > 1.7e9:
            st = st or t; en = t
        if e == "run_start" and cfg is None: cfg = d
        if e not in keys: keys[e] = sorted(d.keys())
    R[run] = dict(file=f, start=st, end=en, cfg=cfg, counts=dict(c), keys=keys)
    print(run, pkt(st) if st else None, pkt(en) if en else None, f"{(en-st)/3600:.1f}h" if st else "", dict(c.most_common(12)), flush=True)
json.dump(R, open(f"{OUT}/g0_runs.json", "w"), indent=0, default=str)

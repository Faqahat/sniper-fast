#!/usr/bin/env python3
"""APEX-GAP step 2: rebuild run_20261103_1245 through the probes with the study's OWN b1_build / s1_sim code, paths redirected
to sniper-data/apex2/gap (study outputs untouched). Creator counts = study tabs (other runs) + the extended 11-03 tab.
usage: g2_build.py [--procs 3]"""
import sys, os, json, glob, collections
sys.path.insert(0, "/home/it/sniper/ops/strategies/apex2")
GAP = "/home/it/sniper-data/apex2/gap"; RUN = "run_20261103_1245"
os.environ["APEX2_RES"] = f"{GAP}/res"
import b1_build as B, s1_sim as S
B.X = f"{GAP}/x"; B.OUT = f"{GAP}/tab"
procs = int(sys.argv[sys.argv.index("--procs") + 1]) if "--procs" in sys.argv else 3
if not os.path.exists(f"{GAP}/tab/{RUN}/trades.npy"): B.main(RUN, 3000)
C = collections.Counter(); seen = set()
tabs = [f for f in sorted(glob.glob("/home/it/sniper-data/apex2/tab/run_*/creates.json")) if RUN not in f] + [f"{GAP}/tab/{RUN}/creates.json"]
for f in tabs:
    for m, c in json.load(open(f)).items():
        if c.get("std") and m not in seen: seen.add(m); C[c["creator"]] += 1
json.dump(C, open(f"{GAP}/tab/creator_counts.json", "w"))
S.TAB = f"{GAP}/tab"; S.RES = f"{GAP}/res"
S.main(RUN, procs)

#!/usr/bin/env python3
# FINAL-2 offline scores for every row of gdm/feats (same model / veto / threshold / guards as core/f2_offline.py) -> gdm/f2.npz
import sys, json, gzip
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/gdm")
import numpy as np, common
Z, M = common.load(); mints = M["mints"]; ms = set(mints)
score, MM, MV, THR, VC = common.f2_scorer()
T = {}
for l in gzip.open(common.P + "/table_dump.jsonl.gz", "rt"):
    r = json.loads(l)
    if r["mint"] in ms: T[r["mint"]] = r
s = np.array([score(T[m]) for m in mints]); sv = np.array([score(T[m], MV) for m in mints])
pick = (s >= THR) & (sv < VC) & (Z["guard"] == 1)
np.savez_compressed(f"{common.OUT}/f2.npz", s=s, sv=sv, pick=pick, thr=THR, vcut=VC)
off = set(json.load(open(f"{common.CORE}/f2_off_R1_tail.json"))) | set(json.load(open(f"{common.CORE}/f2_off_R2.json")))
mine = {m for m, p in zip(mints, pick) if p}
print("rows", len(mints), "FINAL-2 picks", pick.sum(), "| core offline picks", len(off), "both", len(mine & off), "only mine", len(mine - off), "only core", len(off - mine))

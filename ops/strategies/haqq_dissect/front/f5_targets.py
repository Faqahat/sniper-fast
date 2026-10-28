#!/usr/bin/env python3
"""FRONT step 5a (read-only): for every paying dump in S, EVERY recorded tx touching its mint in slots [dump-2, dump+1]
(landed AND failed), so we can see pre-senders' failed tries, our tries, bundles and the full order around the dump.
Out: scratch hd_front/win/<chunk>.mints (grep -F patterns) and <chunk>.json (mint -> [[lo, hi], ...] slot windows)"""
import pickle, json, os, collections
import numpy as np
import sys
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/dv8")
import dv8lib as L
OUT = "/home/moiz/sniper-data/haqq_dissect/front"
SCR = "/tmp/claude-1000/-home-moiz/b89fe85a-a34a-424b-a07d-ff4f59af6472/scratchpad/hd_front/win"
os.makedirs(SCR, exist_ok=True)
R = pickle.load(open(f"{OUT}/f1.pkl", "rb")); SE = pickle.load(open(f"{OUT}/f2_sets.pkl", "rb"))
ids, _ = L.ids_map()
F = json.load(open("/home/moiz/sniper-data/dv8/tab/files.json"))
F = [f for f in F if f["slot_hi"] >= 460541261 - 100]
lo = np.array([f["slot_lo"] for f in F]); hi = np.array([f["slot_hi"] for f in F])
o = np.argsort(lo); F = [F[k] for k in o]; lo = lo[o]; hi = hi[o]
per = collections.defaultdict(lambda: collections.defaultdict(list))
for i in SE["S"]:
    r = R[i]; m = ids[r["mint"]]; a, b = r["ds"] - 2, r["ds"] + 1
    for k in range(max(int(np.searchsorted(lo, a, side="right")) - 1, 0), int(np.searchsorted(lo, b, side="right"))):
        if lo[k] <= b and hi[k] >= a: per[F[k]["npz"][:-4]][m].append([a, b])
for name, v in per.items():
    open(f"{SCR}/{name}.mints", "w").write("\n".join(sorted(v)) + "\n")
    json.dump(v, open(f"{SCR}/{name}.json", "w"))
print(f"chunks {len(per)}, mint-windows {sum(len(x) for v in per.values() for x in v.values()):,}")

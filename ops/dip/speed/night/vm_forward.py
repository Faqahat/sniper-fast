#!/usr/bin/env python3
# FORWARD test of the frozen value model on raw data recorded AFTER it was frozen (slots > trained_until_slot). Pure offline.
import pickle, numpy as np, json, glob, os, subprocess, sys
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip"); import gbdt_np as G
from hq2 import load, dataset
d = pickle.load(open("vm_frozen.pkl", "rb"))
os.makedirs("rawfwd", exist_ok=True)
for f in sorted(glob.glob("/home/moiz/sniper-data/collect/run_20261024_1425/txs/txs_*.jsonl.gz")):
    b = os.path.basename(f)
    if int(b[4:14]) >= 1792877000 and not os.path.exists("rawfwd/" + b): os.symlink(f, "rawfwd/" + b)
subprocess.run(["python3", "race_extract.py", "rawfwd", "rows_fwd.json"], check=True)
T = load("rows_fwd.json")
for off, cost in ((80, 0.002), (80, 0.0006), (40, 0.002)):
    X, V, TS = dataset(T, off, cost)
    keep = TS > d["trained_until_slot"]; X, V, TS = X[keep], V[keep], TS[keep]
    B = np.zeros(X.shape, np.int16)
    for j, e in enumerate(d["edges"]):
        b = np.searchsorted(e, X[:, j], side="right") + 1; b[np.isnan(X[:, j])] = 0; B[:, j] = b
    f = np.full(len(V), d["F0"])
    for t in d["trees"]: f += d["lr"] * G.pred(t, B)
    hours = (TS.max() - TS.min()) * 0.2126 / 3600
    pick = f >= d["cut"]; half = np.median(TS[pick])
    print(f"FORWARD {hours:.1f} h after the freeze ({len(V)} dumps) | entry +{off} txs cost {cost} | picks {pick.sum()} ({pick.sum()/hours:.0f}/h) | total {V[pick].sum():+.2f} SOL | per trade {V[pick].mean():+.4f} | {V[pick].sum()/hours*24:+.1f} SOL/day | halves {V[pick & (TS < half)].sum():+.2f} / {V[pick & (TS >= half)].sum():+.2f} | all dumps per trade {V.mean():+.4f}")

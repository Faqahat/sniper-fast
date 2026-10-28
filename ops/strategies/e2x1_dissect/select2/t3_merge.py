#!/usr/bin/env python3
"""select2 t3: merge the per-file tx-shape scans -> SCR/shape.npz (records sorted by sigh, global route ids), SCR/blocks.npy."""
import sys, os, glob, numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select2"); from lib import *
files = sorted(glob.glob(f"{SCR}/shape/*.npz")); print(len(files))
A = []; R = {}; B = {}
for f in files:
    Z = np.load(f, allow_pickle=True); a = Z["a"].copy(); rl = Z["routes"]
    gid = np.array([R.setdefault(r, len(R)) for r in rl], dtype=np.uint16) if len(rl) else np.zeros(0, np.uint16)
    if len(a): a["route"] = gid[a["route"]]
    A.append(a)
    for s, i in Z["blocks"]:
        if s not in B or i > B[s]: B[s] = i
A = np.concatenate(A); A.sort(order="sigh"); u = np.r_[True, A["sigh"][1:] != A["sigh"][:-1]]; print("rows", len(A), "unique sigh", u.sum())
A = A[u]
rl = [None] * len(R)
for k, v in R.items(): rl[v] = k
np.savez(f"{SCR}/shape.npz", a=A, routes=np.array(rl, dtype=object))
b = np.array(sorted(B.items()), dtype=np.int64); np.save(f"{SCR}/blocks.npy", b); print("blocks", len(b), b[0], b[-1], "routes", len(rl))

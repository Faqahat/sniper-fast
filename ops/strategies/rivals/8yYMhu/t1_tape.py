#!/usr/bin/env python3
"""8yYMhu t1 (read-only): market tape subset from the haqqml fresh tape (all pump.fun curve trades built from the recorder),
rows with block time >= 10-24 20:00 PKT, sorted by (mint, slot, idx, j). Out: DATA/mtape.npy (+ mspan.npz: mint -> row span)."""
import numpy as np, time
TP = "/home/moiz/sniper-data/haqqml/fresh/tape"; D = "/home/moiz/sniper-data/rivals/8yYMhu"
t0 = time.time()
T = np.load(f"{TP}/trades.npy", mmap_mode="r")
bt = np.asarray(T["bt"]); sel = np.nonzero(bt >= 1792854000)[0]; del bt
dt = np.dtype([("slot", "<u8"), ("idx", "<u4"), ("j", "u1"), ("mint", "<u4"), ("user", "<u4"), ("buy", "u1"), ("sol", "<u8"), ("tok", "<u8"),
               ("vsol", "<u8"), ("vtok", "<u8"), ("bt", "<u4")])
M = np.empty(len(sel), dt)
for k in dt.names: M[k] = np.asarray(T[k][sel[0]:sel[-1] + 1])[sel - sel[0]]
print("rows", len(M), time.time() - t0, flush=True)
o = np.lexsort((M["j"], M["idx"], M["slot"], M["mint"])); M = M[o]
np.save(f"{D}/mtape.npy", M)
um, st = np.unique(M["mint"], return_index=True); en = np.append(st[1:], len(M))
np.savez(f"{D}/mspan.npz", m=um, a=st, b=en)
print("saved", len(M), "mints", len(um), time.time() - t0)

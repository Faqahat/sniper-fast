#!/usr/bin/env python3
"""LANES step 3: merge per-file tape npz into one per run, compact dtypes, sorted by (mint, s, i).
-> lanes/tape_<run>.npz with columns as separate arrays: s i bt u m tok sol cpre cpost cup tip fl ps nt ; failed: fs fi fu fm fside fcode
own raw lines -> lanes/own_<run>.jsonl. usage: l3_merge.py RUN"""
import sys, glob, numpy as np
D = "/home/it/sniper-data/rivals/9pQQ/lanes"
r = sys.argv[1]
fs = sorted(glob.glob(f"{D}/tape/{r}/*.npz"))
US, MS, PS = [], [], []
for fn in fs:
    z = np.load(fn); US.append(z["users"]); MS.append(z["mints"]); PS.append(z["psets"])
allu = np.unique(np.concatenate(US)); allm = np.unique(np.concatenate(MS)); allp = np.unique(np.concatenate(PS))
del US, MS, PS
C = dict(s=np.int64, i=np.int32, bt=np.int64, u=np.int32, m=np.int32, tok=np.int64, sol=np.int64, cpre=np.int64, cpost=np.int64, cup=np.int64, tip=np.int64, fl=np.int8, ps=np.int16, nt=np.int8)
FC = dict(fs=(0, np.int64), fi=(1, np.int32), fu=(2, np.int32), fm=(3, np.int32), fside=(4, np.int8), fcode=(5, np.int16))
cols = {k: [] for k in C}; fcols = {k: [] for k in FC}
for fn in fs:
    z = np.load(fn); a = z["a"]; f = z["f"]
    um = np.searchsorted(allu, z["users"]).astype(np.int32); mm = np.searchsorted(allm, z["mints"]).astype(np.int32); pm = np.searchsorted(allp, z["psets"]).astype(np.int16)
    if len(a):
        for k, (name, dt) in enumerate(C.items()):
            col = a[:, k]
            if name == "u": col = um[col]
            elif name == "m": col = mm[col]
            elif name == "ps": col = pm[col]
            cols[name].append(col.astype(dt))
    if len(f):
        for name, (k, dt) in FC.items():
            col = f[:, k]
            if name == "fu": col = um[col]
            elif name == "fm": col = mm[col]
            fcols[name].append(col.astype(dt))
    del a, f, z
out = {k: np.concatenate(v) for k, v in cols.items()}; del cols
o = np.lexsort((out["i"], out["s"], out["m"]))
for k in out: out[k] = out[k][o]
del o
fo = {k: np.concatenate(v) for k, v in fcols.items()}; del fcols
o = np.lexsort((fo["fi"], fo["fs"], fo["fm"]))
for k in fo: fo[k] = fo[k][o]
np.savez(f"{D}/tape_{r}.npz", users=allu, mints=allm, psets=allp, **out, **fo)
with open(f"{D}/own_{r}.jsonl", "w") as fw:
    for fn in sorted(glob.glob(f"{D}/tape/{r}/own/*.jsonl")): fw.write(open(fn).read())
print(r, len(out["s"]), len(fo["fs"]), len(allu), len(allm), len(allp), flush=True)

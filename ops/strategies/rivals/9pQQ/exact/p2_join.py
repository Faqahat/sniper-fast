#!/usr/bin/env python3
"""Join tx metadata to the tape rows (by slot, index) -> exact/tm_<run>.npz with per-tape-row: pset (global id), ixset id, ntips, tipsum,
cup, nsig; plus global string tables.  usage: p2_join.py [run ...]"""
import sys, glob
import numpy as np
import xlib as X
for r in (sys.argv[1:] or X.RUNS):
    t = X.load(r)
    A, PS, IS = [], {}, {}
    for fn in sorted(glob.glob(f"{X.XOUT}/txmeta/{r}/*.npz")):
        z = np.load(fn); a = z["a"].copy()
        if not len(a): continue
        pm = np.array([PS.setdefault(p, len(PS)) for p in z["psets"]]); im = np.array([IS.setdefault(p, len(IS)) for p in z["ixsets"]])
        a[:, 2] = pm[a[:, 2]]; a[:, 3] = im[a[:, 3]]; A.append(a)
    a = np.concatenate(A); k = a[:, 0] * 10000 + a[:, 1]; o = np.argsort(k); a = a[o]; k = k[o]
    tk = t.s * 10000 + t.i; j = np.searchsorted(k, tk); j = np.minimum(j, len(k) - 1); ok = k[j] == tk
    out = {nm: np.where(ok, a[j, c], -1) for c, nm in ((2, "pset"), (3, "ixset"), (4, "ntips"), (5, "tipsum"), (6, "cup"), (7, "nsig"))}
    np.savez(f"{X.XOUT}/tm_{r}.npz", psets=np.array(list(PS), dtype="U400"), ixsets=np.array(list(IS), dtype="U600"), **out)
    print(r, "matched", ok.mean().round(4), "psets", len(PS), "ixsets", len(IS), flush=True)

#!/usr/bin/env python3
"""Route features of each decision row's own tx (the outside trade): extra programs (router / bot program classes), tips, CU price.
-> exact/rt_<run>.npz aligned with dm_<run>.npz rows.  usage: dm_route.py"""
import numpy as np, xlib as X
CL = ["41Pr4XqE", "6gY1osmP", "L2TExMFK", "FLASHX8D", "6Vo3245e", "GMgnVFR8", "term9YPb", "haqqqMGN", "7xdwTaV5", "JUP6LkbZ",
      "4DvQwk6W", "J7pourVw", "XTbotxFE", "AKbotMAG", "2eFuLSK4", "tRunsb6N"]
STD = {"11111111", "6EF8rrec", "ComputeB", "TokenzQd", "ATokenGP", "pfeeUxB6", "Tokenkeg", "MemoSq4g", "SysvarC1"}
for r in X.RUNS:
    z = np.load(f"{X.XOUT}/tm_{r}.npz"); d = np.load(f"{X.XOUT}/dm_{r}.npz"); row = d["row"]
    ps = z["psets"]; pset = z["pset"][row]
    out = {}
    for c in CL:
        has = np.array([c in s for s in ps]); out["rt_" + c[:6]] = has[np.maximum(pset, 0)].astype(np.float32)
    nextra = np.array([sum(1 for p in s.split(",") if p and p not in STD) for s in ps])
    out["rt_nextra"] = nextra[np.maximum(pset, 0)].astype(np.float32)
    out["rt_ntips"] = z["ntips"][row].astype(np.float32); out["rt_tip"] = (z["tipsum"][row] / 1e9).astype(np.float32)
    out["rt_cup"] = z["cup"][row].astype(np.float32); out["rt_nsig"] = z["nsig"][row].astype(np.float32)
    np.savez(f"{X.XOUT}/rt_{r}.npz", **out); print(r, len(row), flush=True)

"""load the hourly per-wallet counters (x1 output) into one table with an hour column 'h'; optional hour filter"""
import os, glob
import numpy as np
import common as C
GKEYS = ("g_our_fills", "g_dumps", "g_trades", "g_dip_sol", "g_dip_n", "g_fails")


def load(h0=None, h1=None):
    T = {}; G = {}
    for p in sorted(glob.glob(f"{C.DATA}/hourly/*.npz")):
        h = int(os.path.basename(p)[:-4])
        if (h0 is not None and h < h0) or (h1 is not None and h >= h1): continue
        z = np.load(p)
        n = len(z["u"])
        for k in z.files:
            if k in GKEYS: G.setdefault(k, []).append(float(z[k]))
            else: T.setdefault(k, []).append(z[k])
        T.setdefault("h", []).append(np.full(n, h, np.int64)); G.setdefault("h", []).append(h)
    T = {k: np.concatenate(v) for k, v in T.items()}
    G = {k: np.array(v) for k, v in G.items()}
    T["_G"] = G
    return T

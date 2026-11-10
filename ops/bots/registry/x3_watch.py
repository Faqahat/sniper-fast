#!/usr/bin/env python3
"""BOTREG step 3: the fingerprint WATCH set = every wallet that could ever reach the registry's loose bar, plus the seed names.
Per PKT calendar day from the hourly files: dip buys >= 5 and closed trips >= 8, or >= 3 of our fills followed.
(The loose bar itself is >= 10 dip buys and >= 15 trips/day in 24 h, so this set is a superset; being in it is not a decision.)
In live use update.py adds new loose-bar wallets and back-fills their last 72 h.
Out: /home/it/sniper-data/botreg/watch.txt (u64 per line)"""
import sys, os, glob, collections
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import hourly_table as HT
if __name__ == "__main__":
    T = HT.load()
    day = (T["h"] + 5 * 3600) // 86400
    key = np.stack([T["u"], day.astype(np.uint64)], 1)
    uk, inv = np.unique(key, axis=0, return_inverse=True); inv = inv.ravel()
    s = lambda c: np.bincount(inv, weights=T[c].astype(np.float64))
    ok = ((s("n_dip") >= 5) & (s("n_trip") >= 8)) | (s("n_fol_fills") >= 3)
    W = set(int(x) for x in uk[ok, 0]) | set(C.SEED64)
    W -= set(C.OURS64)
    open(f"{C.DATA}/watch.txt", "w").write("\n".join(str(x) for x in sorted(W)) + "\n")
    print("watch", len(W))

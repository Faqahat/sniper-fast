#!/usr/bin/env python3
"""DF7e replay: shared helpers (read-only). Uses the VM1 data model (ops/dip/vm1/core.py) on the 48 h table
/home/moiz/sniper-data/df7e_replay (run_20261023_1426 + run_20261024_1425, 10-23 19:26 -> 10-25 ~19:47 PKT).
Per-trade features at the trigger event k (only information up to and including k):
  pre/post price, drop, age (slots since the token's first trade = creation), gap (slots since the previous trade),
  post-trade real SOL in the curve (vsol - 30)."""
import sys, json, hashlib
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/dip/vm1")
import core
DD = "/home/moiz/sniper-data/df7e_replay"
W = "DF7eRXHnvRQ9QeVCrdfS56a7RpBD6se6mgPvzApHPNr9"
SIB = ["EprLoV21"]   # prefix of his sibling wallet (for info only)
def sigh(sig): return int.from_bytes(hashlib.blake2b(sig.encode(), digest_size=8).digest(), "little")
def load():
    D = core.Data(DD)
    T = D.T
    first = np.zeros(len(T), bool); first[D.mstart[D.mstart < D.mend]] = True
    st = D.mstart[T["mint"]]
    D.age = (T["slot"].astype(np.int64) - T["slot"][st].astype(np.int64))           # slots since creation (first trade)
    prev_slot = np.empty(len(T), np.int64); prev_slot[1:] = T["slot"][:-1]; prev_slot[0] = -1
    gap = T["slot"].astype(np.int64) - prev_slot; gap[first] = 10**6
    D.gap = gap
    V = T["vsol"].astype(np.float64); s = T["sol"].astype(np.float64)
    pre = np.where(T["buy"] == 1, V - s, V + s)
    D.drop = 1 - (V / pre) ** 2                                                    # >0 for sells (price fall), <0 for buys
    D.curve = V / 1e9 - 30.0
    return D

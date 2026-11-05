#!/usr/bin/env python3
"""augment scale table: since_ob (slots since last outside buy on the mint, -1 none), bsol3/ssol3 (outside buy/sell SOL in last 3 slots incl. this row),
gap75 (slots since previous outside trade), era label by bt. usage: c13_aug.py RUN"""
import sys, numpy as np
D = "/home/moiz/sniper-data/rivals/9pQQ/casebook"; run = sys.argv[1]
z = np.load(f"{D}/scale_{run}.npz")
s = z["s"]; seg = z["seg"]; own = z["own"]; buy = z["buy"]; size = z["size"].astype(np.float64)
N = len(s); idx = np.arange(N)
ob = (~own) & buy
last = np.where(ob, idx, -1); last = np.maximum.accumulate(last)
# reset across mints
segstart = np.r_[0, np.where(np.diff(seg) != 0)[0] + 1]; st = np.repeat(segstart, np.diff(np.r_[segstart, N]))
prev_ob = np.r_[-1, last[:-1]]  # last outside buy strictly before this row
valid = prev_ob >= st
since_ob = np.where(valid, s - s[np.maximum(prev_ob, 0)], -1)
key = seg.astype(np.int64) * (1 << 32) + s
cb = np.r_[0, np.cumsum(np.where(ob, size, 0))]; cs = np.r_[0, np.cumsum(np.where((~own) & (~buy), size, 0))]
j = np.searchsorted(key, key - 2, "left")
bsol3 = cb[idx + 1] - cb[j]; ssol3 = cs[idx + 1] - cs[j]
out_ = ~own; lo = np.where(out_, idx, -1); lo = np.maximum.accumulate(lo); plo = np.r_[-1, lo[:-1]]
gapo = np.where(plo >= st, s - s[np.maximum(plo, 0)], -1)
bt = z["bt"]; era = np.where(bt < 1793268000, 1, np.where(bt < 1793388600, 2, 3))  # V1 < 10-29 15:00 PKT; V2 < 10-31 00:30 PKT; V3 after
np.savez(f"{D}/scale_aug_{run}.npz", since_ob=since_ob.astype(np.int32), bsol3=bsol3.astype(np.float32), ssol3=ssol3.astype(np.float32), gapo=gapo.astype(np.int32), era=era.astype(np.int8))
print(run, "ok", np.bincount(era))

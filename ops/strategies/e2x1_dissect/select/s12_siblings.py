#!/usr/bin/env python3
"""SELECT s12: wallets that trade the same moments as E2x1 (before AND after him). For each candidate: mints in common, signed
first-buy gap (slots, + = they buy after him), who is first, their buy size, their own trip P&L, and their sell timing vs his.
Same operator / same signal source / copier is INFERRED from these patterns (no funding data in the recordings)."""
import sys, collections, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"]); MN, US = names(); uid = {u: i for i, u in enumerate(US)}
sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64); us = D["user"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9; mi = D["mint"]
CANDS = ["Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ", "3iawEZGfWF3H7q6HLxHjSfeZHjCvPr8U9xjXpMgtobDN", "4mYySb7Z74EK9c6AzSmRRbsd5NjRKeU2yjMF6nfz8ctD",
         "Hj4uACn8Jp2QvbMFhkhWWCdHPzC2SEXg7fhpZayYVcyL", "2QGfyorLu58GgSPvHrHhdX7WjP9TEt9xdBmpNsYaHBfz", "3qZ3RTQs5rYz8Gqxqt8cE5qBLCXX9hVB7wMeEwEhUffQ",
         "GS7brwSxsgCnLoSYCHjEv9ecg88zz7bcq2qjWq8P8B8B", "8T4XXALtGjvJytQ2zvFSBaZYexxqd1fzpC1n8ATSbkWc", "6nH3jMhHyfEvRsdy39B3BGkhQyATXzhifu4KnvV13CZ1",
         "HLU8QbLdvHDSWiQtyc8SGsTTdSdwZ3UKt8cEkG2wv4qk", "3Vggwn3LPougvnGa8zpYJMEN9L38tSRa45gv9odiSVF1", "ssssswdk4RR8HqkE3uwUWzDbd6mXFTTPjcXBKNzQ57E"]
def firsts(u):
    r = np.flatnonzero((us == u) & bu); f = {}
    for R in r:
        m = int(mi[R])
        if m not in f: f[m] = R
    return f
def trip(u, m):
    a, e = span(D, m); q = np.arange(a, e); q = q[us[q] == u]
    return so[q][~bu[q]].sum() - so[q][bu[q]].sum()
FE = firsts(w)
print(f"E2x1 tokens {len(FE)}")
print("wallet        tokens  common  share_of_his  they_first  same_slot  gap_med(sl)  size_med  their_pnl_common  their_pnl_all")
for W in CANDS:
    u = uid[W]; FU = firsts(u); com = set(FE) & set(FU)
    gaps = []; tf = 0; ss = 0
    for m in com:
        A, B = FE[m], FU[m]
        g = int(sl[B] - sl[A]); gaps.append(g)
        tf += (sl[B], ix[B]) < (sl[A], ix[A]); ss += sl[B] == sl[A]
    gaps = np.array(gaps) if gaps else np.zeros(1)
    near = np.abs(gaps) <= 5
    pc = sum(trip(u, m) for m in list(com)[:3000]); pa = so[(us == u) & ~bu].sum() - so[(us == u) & bu].sum()
    print(f"{W[:12]}  {len(FU):6d}  {len(com):6d}  {len(com)/len(FE):6.3f}  {tf/max(len(com),1):6.2f}  {ss/max(len(com),1):6.2f}  {np.median(gaps):6.0f} (|gap|<=5: {near.mean():.2f})"
          f"  {np.median(so[list(FU.values())]):6.3f}  {pc:8.1f}  {pa:8.1f}")

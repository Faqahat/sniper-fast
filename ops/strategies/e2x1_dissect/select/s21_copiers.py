#!/usr/bin/env python3
"""SELECT s21: what do REAL copiers of E2x1 earn? (MEASURED on the tape, 10-22 03:13 -> 10-28 18:41 PKT.) For each cluster wallet:
buys, SOL in, gross curve P&L (sells - buys, curve SOL), est. pump fees (fee_bps + cfee_bps per row), net of pump fees (tx fees/tips
not included), share of their tokens that E2x1 also bought, entry relative to him, and P&L on tokens where they entered AFTER him."""
import sys, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"]); MN, US = names(); uid = {u: i for i, u in enumerate(US)}
us = D["user"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9; mi = D["mint"]; sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64)
fee = so * (D["fee_bps"].astype(float) + D["cfee_bps"].astype(float)) / 1e4
days = (D["bt"].max() - D["bt"].min()) / 86400
W = ["E2x1ewwXUwxABtFcssgxQLY6PrcRQuhLJRWPCR3WyeJb", "Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ", "4mYySb7Z74EK9c6AzSmRRbsd5NjRKeU2yjMF6nfz8ctD",
     "Hj4uACn8Jp2QvbMFhkhWWCdHPzC2SEXg7fhpZayYVcyL", "3iawEZGfWF3H7q6HLxHjSfeZHjCvPr8U9xjXpMgtobDN", "2QGfyorLu58GgSPvHrHhdX7WjP9TEt9xdBmpNsYaHBfz",
     "FiYZPbS4wi7CSEBerzvyHEAzQkT7qj1apB2mZob3R3zj", "6nH3jMhHyfEvRsdy39B3BGkhQyATXzhifu4KnvV13CZ1", "8T4XXALtGjvJytQ2zvFSBaZYexxqd1fzpC1n8ATSbkWc"]
hf = {}
for R in np.flatnonzero((us == w) & bu):
    hf.setdefault(int(mi[R]), (sl[R], ix[R]))
print(f"{'wallet':12s} {'buys':>5s} {'SOLin':>7s} {'gross':>7s} {'fees':>6s} {'net':>7s} {'net/day':>7s} {'%tok w/ E2x1':>12s} {'after him':>9s} {'net on after-him tokens':>10s}")
for x in W:
    u = uid[x]; r = np.flatnonzero(us == u)
    g = so[r][~bu[r]].sum() - so[r][bu[r]].sum(); f = fee[r].sum()
    toks = collections.defaultdict(list)
    for q in r: toks[int(mi[q])].append(q)
    com = [m for m in toks if m in hf]
    after = [m for m in com if (sl[min(toks[m])], ix[min(toks[m])]) > hf[m]]
    na = sum(so[q] * (-1 if bu[q] else 1) - fee[q] for m in after for q in toks[m])
    print(f"{x[:12]} {int(bu[r].sum()):5d} {so[r][bu[r]].sum():7.1f} {g:+7.1f} {f:6.1f} {g - f:+7.1f} {(g - f)/days:+7.2f} {len(com)/max(len(toks),1):12.2f} {len(after)/max(len(com),1):9.2f} {na:+10.1f}")

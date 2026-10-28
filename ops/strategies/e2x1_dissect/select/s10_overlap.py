#!/usr/bin/env python3
"""SELECT s10 (his P&L = s2 lot P&L of his buys within +-60 s of our buy): overlap with OUR live wallets (FRA 2g7r..., AMS Egxf...) on the same tape. Per our buy: did E2x1 trade that mint
within +-60 s? who bought first, slot gap, and both sides' trip P&L on that mint episode (episode = trades within 60 s of our buy)."""
import sys, collections, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"]); MN, US = names(); uid = {u: i for i, u in enumerate(US)}
OURS = {"FRA": "2g7rYv7yCQuNsxUfr5B61LBfkhYzHMhYTZkcZ6e2iTLE", "AMS": "EgxfYgEbruk94yjiWrMa9ex8fS3jeQFLwkrkHg3BtdtR"}
sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64); us = D["user"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9
mi = D["mint"]; bt = D["bt"].astype(np.int64)
LOT = {b["row"]: b["lot_pnl"] for b in pickle.load(open(f"{OUT}/buys.pkl", "rb"))}
for reg, W in OURS.items():
    o = uid.get(W)
    if o is None: print(reg, "not in tape"); continue
    ob = np.flatnonzero((us == o) & bu)
    print(f"\n== {reg}: our buys in tape {len(ob)} ({pkt(bt[ob].min())} .. {pkt(bt[ob].max())})")
    n_ov = 0; rows = []
    done = set()
    for R in ob:
        m = int(mi[R]); a, e = span(D, m)
        win = (np.abs(bt[a:e] - bt[R]) <= 60)
        his = np.flatnonzero(win & (us[a:e] == w)) + a
        if not len(his): continue
        key = (m, int(bt[R]) // 120)
        if key in done: continue
        done.add(key)
        hb = [q for q in his if bu[q]]
        ours_ep = np.flatnonzero(win & (us[a:e] == o)) + a
        op = so[[q for q in ours_ep if not bu[q]]].sum() - so[[q for q in ours_ep if bu[q]]].sum()
        hp = sum(LOT.get(int(q), 0.0) for q in hb)          # his lots bought in the window, valued at his realised sells (s2)
        first = "his" if hb and (sl[hb[0]], ix[hb[0]]) < (sl[R], ix[R]) else ("ours" if hb else "he only sold")
        gap = int(sl[R] - sl[hb[0]]) if hb else None
        rows.append((MN[m], pkt(bt[R]), first, gap, round(op, 4), round(hp, 4), round(so[R], 3), round(so[hb].sum(), 3)))
    c = collections.Counter(r[2] for r in rows)
    print(f"episodes with E2x1 within 60 s: {len(rows)}  first: {dict(c)}")
    print(f"our P&L on them {sum(r[4] for r in rows):+.3f} SOL; his {sum(r[5] for r in rows):+.3f} SOL")
    for r in rows[:40]: print("  ", r)

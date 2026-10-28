#!/usr/bin/env python3
"""SELECT s11: is he copying specific wallets? For his FIRST buy on each token: the outside BUYERS (and sellers) in slots [s-3, s]
before his row. Baseline: the same window before sampled envelope moments (U samp rows, my_buys==0, age<=30 min) on mints
he did not touch at that time. Lift per wallet = his-window rate / baseline-window rate. Leader list chosen on TRAIN (before the
newest 6 h), tested on TEST: share of his first buys preceded by a leader buy, and the take rate / forward of leader-buy moments."""
import sys, collections, pickle, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"]); MN, US = names()
sl = D["slot"].astype(np.int64); us = D["user"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9; mi = D["mint"]; bt = D["bt"].astype(np.int64)
TCUT = int(bt.max()) - 6 * 3600
U = np.load(f"{OUT}/U.npz")
def window_users(R, incl=False):
    a, e = span(D, int(mi[R])); lo = a + int(np.searchsorted(sl[a:R], sl[R] - 3))
    hi = R + 1 if incl else R
    q = np.arange(lo, hi); q = q[us[q] != w]
    return set(us[q][bu[q]].tolist()), set(us[q][~bu[q]].tolist())
first = {}
for R in np.flatnonzero((us == w) & bu):
    m = int(mi[R])
    if m not in first and D["cr_slot"][m] >= 0: first[m] = R
F = sorted(first.values())
his_tr = [R for R in F if bt[R] < TCUT]; his_te = [R for R in F if bt[R] >= TCUT]
# baseline: sampled moments (rows) with my_buys==0, not followed by him within 3 slots
bm = (U["samp"]) & (U["my_buys"] == 0) & (~U["y3"]) & (U["age_s"] <= 1800)
base_rows = U["row"][bm]; base_bt = U["bt"][bm]
rng = np.random.default_rng(0)
base_tr = rng.choice(base_rows[base_bt < TCUT], 60000, replace=False); base_te = base_rows[base_bt >= TCUT]
def counts(rows, incl):
    cb = collections.Counter(); cs = collections.Counter()
    for R in rows:
        b, s = window_users(R, incl); cb.update(b); cs.update(s)
    return cb, cs
hb, hs = counts(his_tr, False); bb, bs = counts(base_tr, True)
nh, nb = len(his_tr), len(base_tr)
lead = []
for u, c in hb.items():
    if c < 25: continue
    lift = (c / nh) / ((bb.get(u, 0) + 1) / nb)
    lead.append((lift, c, u))
lead.sort(reverse=True)
print(f"his first buys: train {nh}, test {len(his_te)}; baseline moments train {nb}, test {len(base_te)}")
print("top wallets BUYING in the 3 slots before his first buy (train), lift vs baseline:")
for lift, c, u in lead[:30]: print(f"  {US[u]}  in {c:5d} of his ({c/nh:.3f})  baseline {bb.get(u,0)/nb:.4f}  lift {lift:6.1f}")
L = {u for lift, c, u in lead if lift >= 5}
print(f"leader set (lift>=5, >=25 hits, TRAIN): {len(L)} wallets")
def share(rows, incl):
    return np.mean([len(window_users(R, incl)[0] & L) > 0 for R in rows])
print(f"share preceded by a leader buy: his TRAIN {share(his_tr, False):.3f}  his TEST {share(his_te, False):.3f}  | baseline TRAIN {share(base_tr[:20000], True):.4f}  TEST {share(base_te, True):.4f}")
json.dump({"leaders": [US[u] for u in L], "top": [(US[u], c, lift) for lift, c, u in lead[:100]]}, open(f"{OUT}/s11_leaders.json", "w"))

#!/usr/bin/env python3
"""SELECT s13: the E2x1 CLUSTER = E2x1 + wallets that buy the same tokens within 0-5 slots on most of their tokens (s8 cohort + Grozoe2L).
Anchor = the cluster's FIRST buy on each token E2x1 traded. Who buys (outside the cluster) in the 3 slots before the anchor? Lift vs
baseline moments (as s11). If the cluster copies an outside wallet list, those wallets show huge lift and high coverage."""
import sys, collections, pickle, json
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
D = load(); w = int(D["wid"]); MN, US = names(); uid = {u: i for i, u in enumerate(US)}
sl = D["slot"].astype(np.int64); ix = D["idx"].astype(np.int64); us = D["user"].astype(np.int64); bu = D["buy"].astype(bool); mi = D["mint"]; bt = D["bt"].astype(np.int64)
so = D["sol"] / 1e9
coh = pickle.load(open(f"{OUT}/s8.pkl", "rb"))["C"]
CL = {uid[x] for x in coh} | {w, uid["Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"]}
TCUT = int(bt.max()) - 6 * 3600
isCL = np.isin(us, list(CL))
anch = {}
for m in np.unique(mi[(us == w) & bu]):
    a, e = span(D, int(m))
    q = np.flatnonzero(isCL[a:e] & bu[a:e])
    if len(q) and D["cr_slot"][m] >= 0: anch[int(m)] = a + int(q[0])
A = sorted(anch.values())
who = collections.Counter(US[us[R]][:8] for R in A)
print("cluster first buyer per token:", who.most_common(8))
U = np.load(f"{OUT}/U.npz")
bm = (U["samp"]) & (U["my_buys"] == 0) & (~U["y3"]) & (U["age_s"] <= 1800)
rng = np.random.default_rng(0); base = rng.choice(U["row"][bm & (U["bt"] < TCUT)], 60000, replace=False)
def wu(R, incl):
    a, e = span(D, int(mi[R])); lo = a + int(np.searchsorted(sl[a:R], sl[R] - 3)); q = np.arange(lo, R + 1 if incl else R)
    q = q[~isCL[q] & bu[q]]; return set(us[q].tolist())
tr = [R for R in A if bt[R] < TCUT]; te = [R for R in A if bt[R] >= TCUT]
hc = collections.Counter(); [hc.update(wu(R, False)) for R in tr]
bc = collections.Counter(); [bc.update(wu(R, True)) for R in base]
lead = sorted(((c / len(tr)) / ((bc.get(u, 0) + 1) / len(base)), c, u) for u, c in hc.items() if c >= 25)[::-1]
print(f"anchors train {len(tr)} test {len(te)}")
for lift, c, u in lead[:20]: print(f"  {US[u]}  {c:5d} ({c/len(tr):.3f})  base {bc.get(u,0)/len(base):.4f}  lift {lift:6.1f}  (ever bought {int(((us==u)&bu).sum())} times)")
L = {u for lift, c, u in lead if lift >= 5}
sh = lambda rows, incl: np.mean([len(wu(R, incl) & L) > 0 for R in rows])
print(f"outside leader set {len(L)}: share before cluster anchor TRAIN {sh(tr, False):.3f} TEST {sh(te, False):.3f} | baseline {sh(base[:20000], True):.3f}")
# anchor trigger: nothing outside before? gap to previous outside trade
gaps = [int(sl[R] - sl[R - 1]) for R in A if mi[R - 1] == mi[R]]
print("anchor lag to previous trade (slots):", collections.Counter(min(g, 5) for g in gaps).most_common())

#!/usr/bin/env python3
"""SELECT s14: (a) adds: add fill px vs his previous fill on the token (dip-add vs strength-add), time since previous buy, the add lot's
own return (lot attribution = his average realised sell px on the token; adds share exits with the first lot).
(b) exits: per his sell: hold since first buy, his unrealised return at the sell (px before his sell vs his avg cost), the trade(s)
right before it (outside buy into which he sells? cluster/copier buy? a big sell?), and whether it closes the position."""
import sys, collections, pickle
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/e2x1_dissect/select")
from lib import *
from tl import cols, tab, bucket
D = load(); w = int(D["wid"]); MN, US = names(); uid = {u: i for i, u in enumerate(US)}
sl = D["slot"].astype(np.int64); us = D["user"].astype(np.int64); bu = D["buy"].astype(bool); so = D["sol"] / 1e9; mi = D["mint"]; bt = D["bt"].astype(np.int64)
tk = D["tok"].astype(np.float64); lp = np.log(D["vsol"] / np.maximum(D["vtok"].astype(np.float64), 1))
coh = set(uid[x] for x in pickle.load(open(f"{OUT}/s8.pkl", "rb"))["C"]) | {uid["Grozoe2Lk9yu7kWPcCMuWEbrnuBYseBExkYAuHPRJUdJ"]}
X = cols(pickle.load(open(f"{OUT}/buys.pkl", "rb"))); X["ret"] = X["lot_pnl"] / X["sol"]
# (a) adds
prevpx = {}; ratio = np.full(len(X["row"]), np.nan); dt = np.full(len(X["row"]), np.nan)
for k, R in enumerate(X["row"]):
    m = int(mi[R]); px = so[R] / tk[R]
    if m in prevpx: ratio[k] = px / prevpx[m][0] - 1; dt[k] = bt[R] - prevpx[m][1]
    prevpx[m] = (px, bt[R])
A = {k: v[X["add"] > 0] for k, v in X.items()}; A["ratio"] = ratio[X["add"] > 0]; A["dt"] = dt[X["add"] > 0]
print(f"adds {len(A['ratio'])}: into dip (px < prev fill) {np.mean(A['ratio'] < 0):.2f}; median px vs prev fill {100*np.median(A['ratio']):+.1f}%; median gap {np.median(A['dt']):.0f} s")
tab("adds by px vs his previous fill", bucket(A["ratio"], [-0.3, -0.15, -0.05, 0, 0.05, 0.15, 0.3]), A, ("dt", "dd_peak", "ret_5s", "age_s"))
tab("adds by gap since previous buy (s)", bucket(A["dt"], [1, 3, 10, 30, 120]), A, ("ratio", "dd_peak"))
# (b) exits
rows = []
for m in np.unique(mi[(us == w)]):
    a, e = span(D, int(m)); q = np.flatnonzero(us[a:e] == w) + a
    held = 0.0; cost = 0.0; t0 = None
    for r in q:
        if bu[r]:
            held += tk[r]; cost += so[r]; t0 = t0 if t0 is not None else bt[r]
        else:
            if held <= 0 or t0 is None: continue
            avgc = cost / held; pxb = np.exp(lp[r - 1]) if mi[r - 1] == m else np.nan
            unreal = (so[r] / tk[r]) / avgc - 1        # realised sell px vs avg cost
            p = r - 1; pt = "none"
            if mi[p] == m and sl[r] - sl[p] <= 1:
                pt = ("cluster-buy" if us[p] in coh else ("buy>=1" if so[p] >= 1 else "buy<1")) if bu[p] else ("sell>=1" if so[p] >= 1 else "sell<1")
            frac = min(tk[r] / held, 1.0)
            rows.append(dict(hold=float(bt[r] - t0), ret=float(unreal), prev=pt, frac=float(frac), sol=float(so[r]), lot_pnl=float(so[r] - frac * cost)))
            cost *= (1 - frac); held = max(held - tk[r], 0); t0 = t0 if held > 1e3 else None
S = cols(rows)
print(f"\nsells {len(S['ret'])}: full closes {np.mean(S['frac'] > 0.98):.2f}; hold median {np.median(S['hold']):.0f} s")
S["lot_pnl"] = S["lot_pnl"]; S["sol"] = S["sol"]
print("-- sells by return at the sell (vs avg cost): share")
for lo, hi in [(-1, -0.3), (-0.3, -0.1), (-0.1, -0.02), (-0.02, 0.02), (0.02, 0.1), (0.1, 0.3), (0.3, 10)]:
    mm = (S["ret"] >= lo) & (S["ret"] < hi); print(f"  {lo:+.2f}..{hi:+.2f}: {mm.mean():.3f}  hold med {np.median(S['hold'][mm]) if mm.any() else 0:.0f}s")
print("-- trade right before his sell (<=1 slot):", collections.Counter(S["prev"]).most_common())
base = collections.Counter()
for k in ("prev",): pass
print("-- hold buckets: share / median ret")
for lo, hi in [(0, 2), (2, 5), (5, 15), (15, 60), (60, 300), (300, 1e9)]:
    mm = (S["hold"] >= lo) & (S["hold"] < hi); print(f"  {lo}-{hi}s: {mm.mean():.3f}  ret med {100*np.median(S['ret'][mm]):+.1f}%  win {np.mean(S['ret'][mm] > 0):.2f}")
# (c) add-while-holding vs re-entry after a full exit; exit baseline for "previous trade is a sell"
held_at = np.zeros(len(X["row"]), bool); hold = {}
order = np.argsort(X["row"])
pos = collections.defaultdict(float)
myrows = np.flatnonzero(us == w); k_of = {int(r): k for k, r in enumerate(X["row"])}
for r in myrows:
    m = int(mi[r])
    if bu[r]:
        if r in k_of: held_at[k_of[r]] = pos[m] > 1e3
        pos[m] += tk[r]
    else: pos[m] = max(pos[m] - tk[r], 0)
kind = np.where(X["add"] == 0, "first", np.where(held_at, "add-holding", "re-entry"))
tab("buy kind", kind, X, ("age_s", "dd_peak", "hold_s"))
B = {k: v[kind != "first"] for k, v in X.items()}; B["ratio"] = ratio[kind != "first"]; kk = kind[kind != "first"]
for nm in ("add-holding", "re-entry"):
    mm = kk == nm; Bm = {k: v[mm] for k, v in B.items()}
    tab(f"{nm} by px vs previous fill", bucket(Bm["ratio"], [-0.3, -0.1, 0, 0.1, 0.3]), Bm, ("dd_peak", "age_s"))
# baseline for exits: all outside trades on his tokens during his holds -> share whose previous trade (<=1 slot) is an outside sell
tot = 0; sel = 0
for m in np.unique(mi[myrows])[:1500]:
    a, e = span(D, int(m)); q = np.flatnonzero(us[a:e] == w) + a
    if not len(q): continue
    lo, hi = q[0], q[-1]
    for r in range(lo + 1, hi):
        if us[r] == w or us[r - 1] == w or sl[r] - sl[r - 1] > 1: continue
        tot += 1; sel += not bu[r - 1]
print(f"baseline: outside trades during his holding windows whose previous trade (<=1 slot) is a sell: {sel/max(tot,1):.3f} (n={tot})")

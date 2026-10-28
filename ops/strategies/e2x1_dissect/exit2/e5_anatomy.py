#!/usr/bin/env python3
"""exit2 step 5: descriptive exit anatomy over all closed trips (6.6 days, MEASURED from the tape).
(a) the last outside trade before his sell: gap, side, who; (b) sibling (Grozoe) co-exits: same slot? who is first by index?
(c) univariate comparison: feature medians at exit events (y1=1) vs other open moments. Out: e5.txt"""
import pickle, collections, numpy as np
OUT = "/home/moiz/sniper-data/e2x1_dissect/exit2"
Z = np.load(f"{OUT}/tape_his.npz"); wid = int(Z["wid"]); sid = int(Z["sid"])
slot = Z["slot"].astype(np.int64); idx = Z["idx"].astype(np.int64); user = Z["user"]; buy = Z["buy"].astype(bool); sol = Z["sol"].astype(np.float64) / 1e9; bt = Z["bt"].astype(np.int64)
mint = Z["mint"]; um, st = np.unique(mint, return_index=True); en = np.append(st[1:], len(mint)); span = {int(m): (int(a), int(b)) for m, a, b in zip(um, st, en)}
TR = pickle.load(open(f"{OUT}/trips.pkl", "rb")); EV = np.load(f"{OUT}/ev.npz"); X = EV["X"]; y = EV["y1"]; F = list(EV["feats"]); FI = {f: k for k, f in enumerate(F)}
TEST0 = 1793113200 - 79 * 60
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
gap = []; side = []; sibc = collections.Counter(); sib_order = collections.Counter(); sib_gap = []; n = 0; nosib = 0
sib_hold_at_sell = 0; sib_sell_lead = []
for t in TR:
    if t["close"] is None: continue
    n += 1; a, b = span[t["mint"]]; ks = t["sells"][0]; s, i = slot[ks], idx[ks]
    pre = [k for k in range(a, ks) if user[k] != wid]
    if pre:
        k = pre[-1]; gap.append(s - slot[k]); side.append(("sell" if not buy[k] else "buy", s - slot[k] <= 1))
    # sibling sells on this mint near his sell
    sk = [k for k in range(a, b) if user[k] == sid and not buy[k] and abs(slot[k] - s) <= 5]
    if sk:
        d = min(sk, key=lambda k: abs(slot[k] - s)); dg = slot[d] - s; sib_gap.append(dg)
        if dg == 0: sib_order["sib first (lower idx)" if idx[d] < i else "E2x1 first (lower idx)"] += 1; sibc["same slot"] += 1
        elif dg < 0: sibc["sib earlier slot"] += 1
        else: sibc["sib later slot"] += 1
    else:
        sibh = any(user[k] == sid and buy[k] and slot[k] <= s for k in range(a, b))
        sibc["no sib sell within 5 slots" + (" (sib was in)" if sibh else " (sib never bought)")] += 1
gap = np.array(gap)
P(f"closed trips {n}; last outside trade before his sell: gap <=1 slot {100*np.mean(gap<=1):.1f}%  (0: {100*np.mean(gap==0):.1f}%, 1: {100*np.mean(gap==1):.1f}%, 2-5: {100*np.mean((gap>=2)&(gap<=5)):.1f}%, >5: {100*np.mean(gap>5):.1f}%)")
c = collections.Counter(side); tot = sum(c.values())
P("  last outside trade within <=1 slot is a SELL: {:.1f}%  a BUY: {:.1f}%  (no trade within 1 slot: {:.1f}%)".format(100*c[("sell", True)]/tot, 100*c[("buy", True)]/tot, 100*(c[("sell", False)]+c[("buy", False)])/tot))
P("sibling co-exit:", dict(sibc)); P("  same-slot index order:", dict(sib_order)); sg = np.array(sib_gap); P(f"  sib gap slots p10/50/90 {np.percentile(sg,[10,50,90]) if len(sg) else '-'}")
# univariate
P("\nfeature medians: exit events (he sells in this/next slot) vs other open moments; and P(exit) in the top/bottom decile of the feature")
P(f"  {'feature':24} {'median@exit':>12} {'median@other':>13} {'P(exit)|top10%':>15} {'P(exit)|bot10%':>15}")
pos = y == 1
for f in F:
    x = X[:, FI[f]]; q1, q9 = np.quantile(x, [0.1, 0.9])
    top = x >= q9; bot = x <= q1
    if q9 == q1: continue
    P(f"  {f:24} {np.median(x[pos]):12.4g} {np.median(x[~pos]):13.4g} {100*y[top].mean():14.2f}% {100*y[bot].mean():14.2f}%")
open(f"{OUT}/e5.txt", "w").write("\n".join(out) + "\n")

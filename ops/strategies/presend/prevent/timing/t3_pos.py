#!/usr/bin/env python3
"""TIMING step 3 [MEASURED]: per (wallet, mint) POSITION from the wallet set's full trade history (t2 hist.npz):
first buy (slot, bt), buys before the first sell (n, tokens, SOL cost), the FIRST SELL after it (slot, bt, tokens, SOL, fraction of the
balance, exec-price multiple vs the average buy price, curve SOL before the sell), number of sells, last trade slot, creator flag,
the mint's create slot.  hold = first sell slot - first buy slot (slots).  Also every sell of the position (for ladders): dt, frac, mult.
Out: /home/it/sniper-data/prevent/timing/pos.npz + sells.npz"""
import json, pickle
import numpy as np
D = "/home/it/sniper-data/prevent/timing"
A = dict(np.load(f"{D}/hist.npz")); I = json.load(open(f"{D}/hist_ids.json")); MN = I["mint"]; UN = I["user"]
CR = pickle.load(open(f"{D}/creates_all.pkl", "rb"))
o = np.lexsort((A["j"], A["idx"], A["slot"], A["mint"], A["user"]))
A = {k: v[o] for k, v in A.items()}
u = A["user"]; m = A["mint"]; n = len(u)
brk = np.nonzero((u[1:] != u[:-1]) | (m[1:] != m[:-1]))[0] + 1
st = np.concatenate([[0], brk]); en = np.concatenate([brk, [n]])
S = A["slot"].tolist(); BT = A["bt"].tolist(); B = A["buy"].tolist(); SOL = A["sol"].tolist(); TOK = A["tok"].tolist(); V = A["vsol"].tolist()
cslot = np.full(len(MN), -1, np.int64); ccre = np.full(len(MN), -1, np.int64); Ui = {x: k for k, x in enumerate(UN)}
for k, x in enumerate(MN):
    c = CR.get(x)
    if c:
        cslot[k] = c[1] if c[1] is not None else -1
        ccre[k] = Ui.get(c[0], -1)
P = []; SL = []
for a, e in zip(st.tolist(), en.tolist()):
    uu = int(u[a]); mm = int(m[a])
    # first buy
    k = a
    while k < e and not B[k]: k += 1
    if k == e: continue
    b0 = k; nb = 0; tb = 0; cb = 0; bal = 0; s1 = -1; nsell = 0; last = S[e - 1]
    q = b0
    while q < e:
        if B[q]:
            if s1 < 0: nb += 1; tb += TOK[q]; cb += SOL[q]
            bal += TOK[q]
        else:
            if s1 < 0 and q > b0: s1 = q; bal1 = bal
            nsell += 1
            fr = TOK[q] / bal if bal > 0 else 1.0
            mult = (SOL[q] / TOK[q]) / (cb / tb) if TOK[q] and tb and cb else np.nan
            SL.append((uu, mm, S[q] - S[b0], fr, mult, SOL[q], BT[q] - BT[b0]))
            bal -= TOK[q]
        q += 1
    if s1 >= 0:
        P.append((uu, mm, S[b0], BT[b0], nb, tb, cb, S[s1], BT[s1], TOK[s1], SOL[s1], TOK[s1] / bal1 if bal1 > 0 else 1.0,
                  (SOL[s1] / TOK[s1]) / (cb / tb) if TOK[s1] and tb and cb else np.nan, V[s1] + SOL[s1], nsell, last, int(ccre[mm] == uu), cslot[mm]))
    else:
        P.append((uu, mm, S[b0], BT[b0], nb, tb, cb, -1, -1, 0, 0, 0.0, np.nan, 0, 0, last, int(ccre[mm] == uu), cslot[mm]))
dt = [("u", "i4"), ("m", "i4"), ("b0", "i8"), ("b0t", "i8"), ("nb", "i4"), ("tb", "i8"), ("cb", "i8"), ("s1", "i8"), ("s1t", "i8"), ("s1tok", "i8"),
      ("s1sol", "i8"), ("frac", "f8"), ("mult", "f8"), ("vpre", "i8"), ("nsell", "i4"), ("last", "i8"), ("cre", "i1"), ("cslot", "i8")]
Pa = np.array(P, dtype=dt)
np.save(f"{D}/pos.npy", Pa)
Sa = np.array(SL, dtype=[("u", "i4"), ("m", "i4"), ("dt", "i8"), ("frac", "f8"), ("mult", "f8"), ("sol", "i8"), ("dtt", "i8")])
np.save(f"{D}/sells.npy", Sa)
sold = Pa["s1"] >= 0
print("positions", len(Pa), "with a sell", sold.sum(), "creator positions", Pa["cre"].sum(), "sells", len(Sa))
h = Pa["s1"][sold] - Pa["b0"][sold]
print("hold slots quantiles 10/25/50/75/90:", np.percentile(h, [10, 25, 50, 75, 90]))

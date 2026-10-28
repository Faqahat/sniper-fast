#!/usr/bin/env python3
"""8yYMhu s4 (read-only): how much of the selection result survives OUR landing speed? Paper P&L (0.75 SOL, after pump fees, before
tx costs) by entry delay for: his takes, his fills, imitation-model top 1-2 %, profit-model top 1-2 % (scores from s3, threshold from
train), on the TEST window. Entries: e0 = right after the sell, e73 ~ his 37 ms, e150 ~ 75 ms same slot, ens = first in next slot,
en2 = next slot +150 txs (~our reactive 60-90 ms). Exits: end of slot sell+{3,6,9,20}. Out: DATA/s4.txt"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, rlib as X
U = dict(np.load(f"{X.D}/uni2.npz")); S = np.load(f"{X.D}/s3_scores.npz")
tk = U["taken"] > 0; fl = U["filled"] > 0; tr = U["bt"] < X.W0; te = ~tr; ok = ~U["mayhem"]
days_te = (1793220600 - X.W0) / 86400
out = []
def P(*a): out.append(" ".join(str(x) for x in a)); print(out[-1], flush=True)
sets = [("his takes (all attempts)", tk), ("his fills", fl)]
for nm, sc in (("imitation", S["imit"]), ("profit", S["prof"])):
    for q in (0.99, 0.98):
        th = np.quantile(sc[tr & ok], q); sets.append((f"{nm} model top {100*(1-q):.0f}%", sc >= th))
        sets.append((f"{nm} model top {100*(1-q):.0f}% NOT his", (sc >= th) & ~tk))
P(f"TEST window {X.pkt(X.W0)} -> 10-29 00:50 PKT ({days_te:.2f} d); mSOL per trade (n/day)")
P(f"{'set':40} " + " ".join(f"{e+'/+'+str(x):>10}" for e in ("e0", "e73", "e150", "ens", "en2") for x in (6, 9)))
for nm, m in sets:
    s = m & te & ok
    P(f"{nm:40} " + " ".join(f"{1000*np.nanmean(U[f'r_{e}_{x}'][s]):+10.1f}" for e in ("e0", "e73", "e150", "ens", "en2") for x in (6, 9)) + f"   n/day {s.sum()/days_te:.0f}")
P("same, TRAIN window:")
for nm, m in sets:
    s = m & tr & ok
    P(f"{nm:40} " + " ".join(f"{1000*np.nanmean(U[f'r_{e}_{x}'][s]):+10.1f}" for e in ("e0", "e73", "e150", "ens", "en2") for x in (6, 9)))
open(f"{X.D}/s4.txt", "w").write("\n".join(out) + "\n")

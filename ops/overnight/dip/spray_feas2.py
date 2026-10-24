#!/usr/bin/env python3
# Feasibility of a guarded "spray" dip buy (latency -> fee cost): our buy executes right at the dip (entry 0 ms), but the choice
# can use ONLY what is known BEFORE the dump (pre-sell features) plus a price condition (the dump's size, checkable on chain as
# a min-tokens-out guard). Six-block CV, top-k by a model on pre-sell features, among dips deeper than a threshold.
import os, sys, json, gzip
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/overnight/dip")
import gbdt_np as G
from dipcv import FK, fv
PRE = ["age", "vsol", "nb", "ns", "pb", "dd", "b20", "s20", "u20", "dev", "glued", "first_big", "n_big", "since_big", "ret5", "ret20", "peak_mult",
       "b3", "nb3", "sellers20", "uniq_buyers", "ins_sold", "net_flow"]            # no sell-specific features (sell size, seller, drop...)
EVF = os.environ.get("EVF"); EXIT = os.environ.get("EXIT", "2"); K = 6
R = [json.loads(l) for l in gzip.open(EVF, "rt")]; R.sort(key=lambda r: r["bt"] + r["age"])
idx = [FK.index(k) for k in PRE]
for dmax in (1.0, 0.95, 0.92, 0.9):                     # dump depth condition: price after the dump / before <= dmax
    LL = os.environ.get("LL", "0")
    rows = [r for r in R if LL in r["pnl"] and EXIT in r["pnl"][LL] and r["drop"] <= dmax]
    X = np.array([[fv(r)[j] for j in idx] for r in rows]); P = np.array([r["pnl"][LL][EXIT] for r in rows]); y = (P > 0).astype(float)
    n = len(rows); blk = np.minimum((np.arange(n) * K) // n, K - 1); rng = np.random.default_rng(1)
    tot = {q: 0.0 for q in (0.05, 0.10, 0.20, 1.0)}; cnt = {q: 0 for q in tot}; pos = {q: 0 for q in tot}
    for b in range(K):
        trall = blk != b; va = trall & (rng.random(n) < 0.15); tr = trall & ~va; te = blk == b
        Bm = G.binize(X, tr); trees, f = G.fit(Bm, y, tr, va, rounds=300, lr=0.05, depth=3)
        for q in tot:
            st = te & (f >= (np.quantile(f[va], 1 - q) if q < 1 else -1e9))
            tot[q] += P[st].sum(); cnt[q] += int(st.sum()); pos[q] += int(P[st].sum() > 0)
    print(f"L{LL} exit {EXIT} dump depth <= {dmax}: {n} dips | " + " | ".join(f"top {q:.0%}: n {cnt[q]} total {tot[q]:+.2f} ({tot[q] / max(cnt[q], 1):+.4f}/trade) blocks+ {pos[q]}/6" for q in tot))

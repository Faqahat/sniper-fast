#!/usr/bin/env python3
"""VERIFY v7 (MEASURED): follower activity after re-arm fills, in-sample vs fresh. From v2b pickles: per added fill, the outside
buys (count and SOL) in the 1 s after our modelled landing, and the fill's P&L; grouped by PKT hour-of-day band. usage: v7 TAB PKL [TAB PKL]"""
import sys, pickle, collections
import numpy as np
sys.path.insert(0, "/home/moiz/sniper/ops/strategies/haqq_dissect/verify")
import vlib as V
COST = 5120 + 200_000 + 605_000 + 1_200_000 + 5020
for tab, pkl in zip(sys.argv[1::2], sys.argv[2::2]):
    Z = pickle.load(open(pkl, "rb"))
    F = [r for r in Z["rows"] if r["fill"] is not None and not r["base_has"] and r["seed"] == 0]
    tp = V.Tape(tab, {r["mint"] for r in F})
    out = collections.defaultdict(list)
    for r in F:
        X = tp.rows(r["mint"]); ours = np.isin(X["signer"], list(tp.our)); X = X[~ours]
        cc = np.array([tp.cc(int(a), int(b)) for a, b in zip(X["slot"], X["idx"])])
        L = r["fill"]["L"]; m = (cc > L) & (cc <= L + 1000) & (X["buy"] == 1)
        ms = (cc > L) & (cc <= L + 1000) & (X["buy"] == 0)
        h = ((r["bt"] + 18000) // 3600) % 24
        band = "01-04" if 1 <= h < 4 else "other"
        out[band].append((m.sum(), X["sol"][m].sum() / 1e9, X["sol"][ms].sum() / 1e9, (r["fill"]["ex"]["live"] - COST) / 1e6))
    for b, v in sorted(out.items()):
        a = np.array(v)
        print(f"{pkl.split('/')[-1]} band {b}: fills {len(a)}; outside buys in 1 s after our fill: mean n {a[:, 0].mean():.2f}, SOL {a[:, 1].mean():.3f} (median {np.median(a[:, 1]):.3f}); outside sell SOL {a[:, 2].mean():.3f}; fill P&L {a[:, 3].mean():+.2f} mSOL")

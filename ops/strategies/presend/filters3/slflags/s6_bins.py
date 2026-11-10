#!/usr/bin/env python3
"""SL-REDFLAGS s6: per feature, FIT-quintile bins: SL rate and mean realized P&L, FIT vs VAL (T2 and re-arm apart)."""
import sys
from slib import rows, g
R = rows()
FE = sys.argv[1].split(",") if len(sys.argv) > 1 else ["rise", "whale_n", "wh_p50", "max_oth", "sum_oth", "n_oth6", "age", "n120", "nb50", "w_pct",
      "trig_sol", "trig_vsol", "sign_after_trig", "co_whale", "sum_fresh", "sum_bot", "dd120", "wh_dumps", "coh_hold", "n_hold", "since_last"]
for kind in ("t2", "rearm"):
    for fe in FE:
        fit = sorted(d[fe] for d in R if d["kind"] == kind and d["grp"] == "FIT" and d.get(fe) is not None)
        if len(fit) < 50: continue
        qs = sorted(set(fit[int(len(fit) * q)] for q in (0.2, 0.4, 0.6, 0.8, 0.9)))
        edges = [-1e18] + qs + [1e18]
        out = []
        for i in range(len(edges) - 1):
            cell = []
            for G in ("FIT", "VAL"):
                xs = [d for d in R if d["kind"] == kind and d["grp"] == G and d.get(fe) is not None and edges[i] <= d[fe] < edges[i + 1]]
                n = len(xs)
                cell.append(f"{n:4d} SL{sum(d['sl'] for d in xs):2d} {1000*sum(d['pnl'] for d in xs)/max(n,1):+6.1f}")
            out.append(f"  >={edges[i]:<9.4g} " + " | ".join(cell))
        print(f"{kind} {fe}  (n SL mSOL/trade: FIT | VAL)"); print("\n".join(out))

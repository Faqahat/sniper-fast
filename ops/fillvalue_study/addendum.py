#!/usr/bin/env python3
import sys, os, json
os.environ.setdefault("SLIP","0.08"); os.environ.setdefault("FEE_LEG","0.0008")
os.environ.setdefault("SIZE","2.0"); os.environ.setdefault("ENTRY_MULT","1.0")
sys.path.insert(0,"/root/profit_backtest"); import backtest as B
import fillvalue as F  # reuse loaders + helpers

# curve restricted to the co-sniped subset (where the edge lives)
for label, pred in [("ALL (656)", lambda c: True),
                    ("co-sniped >=1 (104)", lambda c: c["traj"]["cosnipers"]>=1),
                    ("0 co-snipers (552)", lambda c: c["traj"]["cosnipers"]==0)]:
    sub=[c for c in F.SAMPLE if pred(c)]
    row={}
    for lab,k in F.OFFSETS:
        if lab=="floor": rs=[F.pnl_floor(c) for c in sub]
        elif lab=="observed-late": rs=[F.pnl_observed(c) for c in sub]
        else: rs=[F.pnl_offset(c,k) for c in sub]
        row[lab]=sum(rs)/len(rs)
    print(f"{label:22s} " + "  ".join(f"{lab}={row[lab]:+.4f}" for lab,_ in F.OFFSETS)
          + f"  | prize(floor-obs)={row['floor']-row['observed-late']:+.4f}")

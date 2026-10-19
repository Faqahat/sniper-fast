#!/usr/bin/env python3
"""Reconcile his-500 econ outcome: use SAME floor convention as econ102 (create-tx entry_px),
and split by the favorable 13h window vs the rest to separate REGIME from ladder."""
import sys, json, statistics as st
sys.path.insert(0,"/root/econ_102"); import econ102 as E
F=json.load(open("/root/last500/feat_500.json"))
def mean(xs): return sum(xs)/len(xs) if xs else float('nan')
def winr(xs): return sum(1 for x in xs if x>0)/len(xs) if xs else float('nan')
LO,HI=456604917,456820114  # favorable window (creates.json span)
def econ(row, floormode):
    ser=row.get("series")
    if not ser: return None
    s=[(a,c) for (a,b,c) in ser]
    if floormode=="create":
        floor=row.get("entry_px")
    else:
        floor=row.get("floor_px")
    if not floor or floor<=0: return None
    entry=floor*E.ENTRY_MULT
    net,_,_=E.simulate(entry,row["create_slot"],s,E.SHIP,0.5)
    g=E.gross_only(entry,row["create_slot"],s,E.SHIP)
    return net,g,row["create_slot"]
for fm in ["create","minpath"]:
    rows=[econ(r,fm) for r in F if r.get("create_found")]
    rows=[r for r in rows if r]
    nets=[r[0] for r in rows]
    inw=[r[0] for r in rows if LO<=r[2]<=HI]
    outw=[r[0] for r in rows if not(LO<=r[2]<=HI)]
    print(f"floor={fm:8} ALL n={len(nets)} mean={mean(nets):+.4f} win={100*winr(nets):.0f}% tot={sum(nets):+.1f} | "
          f"IN-WINDOW n={len(inw)} mean={mean(inw):+.4f} win={100*winr(inw):.0f}% | OUT n={len(outw)} mean={mean(outw):+.4f} win={100*winr(outw):.0f}%")

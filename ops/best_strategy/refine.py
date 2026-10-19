#!/usr/bin/env python3
"""Refinement grid around BEXIT to confirm it's a true optimum (not a boundary artifact):
push cut deeper, ride higher, cap wider. Also the efficient frontier (mean vs mdd)."""
import json, random, sys
sys.path.insert(0,"/root/best_strategy")
from engine import simulate, FEATS, stats, run

random.seed(7); SIZE=0.5
BASE=dict(s0=1.0,add_units=0.0,derisk_frac=0.0,ride_mult=1.70,trail_frac=0.90,
          cut_r=0.70,ladder_frac=0.0,cap_slots=15,fade=False)
def mk(**kw): p=dict(BASE); p.update(kw); return p
def pn(P): return [r["net"] for r in run(FEATS,P,SIZE)]
def boot(vals,B=800):
    n=len(vals); m=[sum(vals[random.randrange(n)] for _ in range(n))/n for _ in range(B)]; m.sort()
    return m[int(.025*B)],m[int(.975*B)]
rows=[]
for cut in [0.0,0.50,0.60,0.65,0.70,0.75,0.80]:
 for ride in [1.4,1.5,1.7,2.0,2.5]:
  for trail in [0.88,0.90,0.92]:
   for cap in [10,15,20,40]:
     P=mk(cut_r=cut,ride_mult=ride,trail_frac=trail,cap_slots=cap)
     s=stats(run(FEATS,P,SIZE),FEATS)
     rows.append((s["mean"],s["mean_ex_top2"],s,P,"cut%.2f ride%.1f trl%.2f cap%d"%(cut,ride,trail,cap)))
rows.sort(key=lambda r:(r[0]+r[1])/2,reverse=True)
print("TOP 15 refinement (by (mean+exT2)/2):")
for mean,ex2,s,P,nm in rows[:15]:
    lo,hi=boot(pn(P))
    print("%-30s mean %+.4f [%+.4f,%+.4f] med %+.4f win %4.1f%% tot %6.2f mdd %6.2f exT2 %+.4f rcap %.3f bleed %+.4f"%(
        nm,s["mean"],lo,hi,s["median"],s["win"]*100,s["tot"],s["mdd"],s["mean_ex_top2"],s["runner_capture"],s["dump_bleed"]))
# efficient frontier: for each mdd bucket, best mean
print("\nEFFICIENT FRONTIER (lowest |mdd| for each mean tier):")
ff=sorted(rows,key=lambda r:r[0],reverse=True)
seen=[]
for mean,ex2,s,P,nm in ff:
    if all(abs(s["mdd"])<abs(x[2]["mdd"]) or x[0]>mean+1e-9 for x in seen) or not seen:
        pass
# simpler: print pareto points (max mean for each mdd<=threshold)
import math
pts=[(s["mdd"],s["mean"],nm) for _,_,s,_,_ in rows]
for thr in [-2.0,-2.5,-3.0,-3.6,-4.5,-6.0]:
    cand=[p for p in pts if p[0]>=thr]
    if cand:
        best=max(cand,key=lambda p:p[1])
        print("  mdd>=%-5.1f : best mean %+.4f  (%s)"%(thr,best[1],best[2]))
json.dump([{"name":nm,"mean":s["mean"],"mdd":s["mdd"],"exT2":s["mean_ex_top2"],
            "median":s["median"],"win":s["win"],"tot":s["tot"],"rcap":s["runner_capture"],
            "bleed":s["dump_bleed"],"P":P} for _,_,s,P,nm in rows[:40]],
          open("/root/best_strategy/refine.json","w"),indent=1)
print("\nsaved refine.json")

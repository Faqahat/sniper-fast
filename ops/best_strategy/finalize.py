#!/usr/bin/env python3
import json,sys
sys.path.insert(0,"/root/best_strategy")
from engine import FEATS, stats, run
WIN=dict(s0=1.0,add_units=0.0,derisk_frac=0.0,ride_mult=2.0,trail_frac=0.90,
         cut_r=0.0,ladder_frac=0.0,cap_slots=15,fade=False)
BASE=dict(s0=1.0,add_units=0.0,derisk_frac=0.0,ride_mult=1.40,trail_frac=0.92,
          cut_r=0.80,ladder_frac=0.25,cap_slots=40,fade=False)
sw=stats(run(FEATS,WIN,0.5),FEATS); sb=stats(run(FEATS,BASE,0.5),FEATS)
# efficient frontier from refine.json: pareto max-mean per mdd ceiling
ref=json.load(open("/root/best_strategy/refine.json"))
pts=sorted(ref,key=lambda r:r["mdd"],reverse=True)  # mdd closest to 0 first
front=[]; bestmean=-9
for r in sorted(ref,key=lambda r:r["mdd"],reverse=True):
    if r["mean"]>bestmean: bestmean=r["mean"]; front.append(r)
OUT=json.load(open("/root/best_strategy/best_strategy.json"))
OUT["WINNER"]={"config":WIN,"stats":sw,"snipe_engine_params":{
  "derisk_frac":0.0,"ride_mult":2.0,"trail_frac":0.90,"cut_r":0.0,
  "ladder_frac":0.0,"exit_cap_slots":15,"exit_cap_ms":3400,"fading":"off"}}
OUT["efficient_frontier"]=[{"mdd":r["mdd"],"mean":r["mean"],"name":r["name"]} for r in front]
json.dump(OUT,open("/root/best_strategy/best_strategy.json","w"),indent=1,default=str)
print("WINNER:",{k:round(v,4) for k,v in sw.items() if isinstance(v,float)})
print("BASE  :",{k:round(v,4) for k,v in sb.items() if isinstance(v,float)})
print("FRONTIER:")
for r in front: print("  mdd %6.2f  mean %+.4f  %s"%(r["mdd"],r["mean"],r["name"]))

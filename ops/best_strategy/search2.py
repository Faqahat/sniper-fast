#!/usr/bin/env python3
"""Families 2-6. Reuses engine; BEXIT = family-1 best exit. Appends to best_strategy.json."""
import json, random, sys, statistics as st
sys.path.insert(0,"/root/best_strategy")
from engine import simulate, FEATS, stats, run, HAIRCUT

random.seed(7); SIZE=0.5
BASE=dict(s0=1.0,add_units=0.0,derisk_frac=0.0,ride_mult=1.40,trail_frac=0.92,
          cut_r=0.80,ladder_frac=0.25,cap_slots=40,fade=False)
# family-1 best exit (deep cut, no ladder, high ride, tight trail, short cap)
BEXIT=dict(s0=1.0,add_units=0.0,derisk_frac=0.0,ride_mult=1.70,trail_frac=0.90,
           cut_r=0.70,ladder_frac=0.0,cap_slots=15,fade=False)

def pn(feats,P): return [r["net"] for r in run(feats,P,SIZE)]
BASE_FULL=pn(FEATS,BASE)
N=len(FEATS); IDX=list(range(N)); SPLITS=[]
for _ in range(200):
    perm=IDX[:]; random.shuffle(perm); SPLITS.append(set(perm[N//2:]))
def bootstrap_ci(vals,B=800):
    n=len(vals); m=[]
    for _ in range(B): m.append(sum(vals[random.randrange(n)] for _ in range(n))/n)
    m.sort(); return m[int(.025*B)],m[int(.975*B)]
def robust(P,name,boot=True):
    res=run(FEATS,P,SIZE); S=stats(res,FEATS); vals=[r["net"] for r in res]
    lo,hi=(bootstrap_ci(vals) if boot else (float('nan'),)*2)
    pb=0; ds=[]
    for va in SPLITS:
        cv=sum(vals[i] for i in va)/len(va); bv=sum(BASE_FULL[i] for i in va)/len(va)
        ds.append(cv-bv); pb+= cv>bv
    S.update(name=name,P=P,ci_lo=lo,ci_hi=hi,split_delta_mean=sum(ds)/len(ds),split_pbetter=pb/len(SPLITS),
             avg_cap_R=S["avg_cap"])
    # return-on-capital: mean net / mean capital deployed (efficiency)
    S["roc"]=S["mean"]/S["avg_cap"] if S["avg_cap"] else 0.0
    return S
def line(S):
    return ("%-40s mean %+.4f [%+.4f,%+.4f] med %+.4f win %4.1f%% tot %6.2f mdd %6.2f exT2 %+.4f "
            "cap$%.2f roc %+.4f rcap %.3f bleed %+.4f | d%+.4f p%4.1f%%"%(
        S["name"][:40],S["mean"],S["ci_lo"],S["ci_hi"],S["median"],S["win"]*100,S["tot"],S["mdd"],
        S["mean_ex_top2"],S["avg_cap"],S["roc"],S["runner_capture"],S["dump_bleed"],
        S["split_delta_mean"],S["split_pbetter"]*100))
def mk(b,**kw):
    p=dict(b); p.update(kw); return p

OUT=json.load(open("/root/best_strategy/best_strategy.json"))
def save(): json.dump(OUT,open("/root/best_strategy/best_strategy.json","w"),indent=1,default=str)

print("REF baseline:",line(robust(BASE,"BASELINE",boot=True)))
print("REF fam1-best:",line(robust(BEXIT,"FAM1-BEXIT",boot=True)))

def fam(key,cfgs,topn=8,rankkey=lambda s:(s["mean"]+s["mean_ex_top2"])/2):
    R=[robust(P,nm) for nm,P in cfgs]; R.sort(key=rankkey,reverse=True)
    print("\n##### %s (%d cfgs) #####"%(key,len(cfgs)))
    for S in R[:topn]: print(line(S))
    OUT["families"][key]=[{k:v for k,v in s.items() if k!="P"}|{"P":s["P"]} for s in R[:topn]]
    save(); return R

# ---- FAMILY 2: MOMENTUM SCALE-IN (equal-budget: s0+add=1.0, and pyramid variants) ----
cfgs=[]
for s0 in [0.3,0.4,0.5]:
 for tot in [1.0,1.5]:
  add=round(tot-s0,3)
  for thr in [1.1,1.2,1.3]:
   for by in [2,4,8]:
    for cs in [0.70,0.85,0.90]:
      nm="SI s0%.1f add%.2f thr%.1f by%d cutS%.2f"%(s0,add,thr,by,cs)
      cfgs.append((nm,mk(BEXIT,s0=s0,add_units=add,add_thresh=thr,add_by=by,cut_small=cs)))
# also scale-in on baseline exit for apples-to-apples vs BASE
F2=fam("2_scalein",cfgs,topn=12)

# ---- FAMILY 3: TWO-REGIME fast-cut-deep-ride ----
cfgs=[]
for cut in [0.80,0.85,0.90]:
 for ride in [1.3,1.4,1.5,1.7]:
  for tr in [0.90,0.85,0.80]:
   for capr in [40,70,120]:
     nm="2REG cut%.2f ride%.1f trailR%.2f capR%d"%(cut,ride,tr,capr)
     cfgs.append((nm,mk(BEXIT,cut_r=cut,ride_mult=ride,trail_ride=tr,cap_ride=capr,trail_frac=0.90,cap_slots=15)))
F3=fam("3_tworegime",cfgs,topn=10)

# ---- FAMILY 4: DYNAMIC HOLD ----
cfgs=[]
for ride in [1.3,1.4,1.7]:
 for eps in [0.0,0.02,0.05,0.10]:
  for capr in [40,70,120]:
    nm="DYN ride%.1f eps%.2f capR%d"%(ride,eps,capr)
    cfgs.append((nm,mk(BEXIT,ride_mult=ride,dynhold=True,dyn_eps=eps,cap_ride=capr,cap_slots=15)))
F4=fam("4_dynhold",cfgs,topn=8)

save()
print("\nDONE families 2-4. saved.")

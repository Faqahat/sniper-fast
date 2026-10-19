#!/usr/bin/env python3
"""best_strategy search across families 1-6. Robust OOS eval: full-sample + bootstrap CI +
200 random 50/50 paired splits vs baseline + drop-top-2. Saves best_strategy.json incrementally."""
import json, itertools, random, sys, statistics as st
sys.path.insert(0,"/root/best_strategy")
from engine import simulate, FEATS, stats, run, HAIRCUT

random.seed(7)
SIZE=0.5
BASE=dict(s0=1.0,add_units=0.0,derisk_frac=0.0,ride_mult=1.40,trail_frac=0.92,
          cut_r=0.80,ladder_frac=0.25,cap_slots=40,fade=False)

def pnls(feats,P): return [r["net"] for r in run(feats,P,SIZE)]
BASE_FULL=pnls(FEATS,BASE)

# 200 random index splits precomputed
N=len(FEATS); IDX=list(range(N))
SPLITS=[]
for _ in range(200):
    perm=IDX[:]; random.shuffle(perm)
    SPLITS.append((set(perm[:N//2]), set(perm[N//2:])))

def bootstrap_ci(vals,B=1000):
    n=len(vals); means=[]
    for _ in range(B):
        s=sum(vals[random.randrange(n)] for _ in range(n))/n
        means.append(s)
    means.sort()
    return means[int(.025*B)], means[int(.975*B)]

def robust(P, name, boot=False):
    res=run(FEATS,P,SIZE); S=stats(res,FEATS)
    vals=[r["net"] for r in res]
    lo,hi=(bootstrap_ci(vals) if boot else (float('nan'),float('nan')))
    # paired random split: config's VAL-half mean vs baseline's VAL-half mean, same split
    pbetter=0; deltas=[]
    for tr,va in SPLITS:
        cv=sum(vals[i] for i in va)/len(va)
        bv=sum(BASE_FULL[i] for i in va)/len(va)
        deltas.append(cv-bv)
        if cv>bv: pbetter+=1
    S.update({"name":name,"P":P,"ci_lo":lo,"ci_hi":hi,
              "split_delta_mean":sum(deltas)/len(deltas),
              "split_pbetter":pbetter/len(SPLITS)})
    return S

def line(S):
    return ("%-34s mean %+.4f [%+.4f,%+.4f] med %+.4f win %4.1f%% tot %6.2f mdd %6.2f "
            "exT2 %+.4f cap %.3f bleed %+.4f sharpe %.3f | vs base d%+.4f p%4.1f%%"%(
        S["name"][:34],S["mean"],S["ci_lo"],S["ci_hi"],S["median"],S["win"]*100,S["tot"],
        S["mdd"],S["mean_ex_top2"],S["runner_capture"],S["dump_bleed"],S["sharpe"],
        S["split_delta_mean"],S["split_pbetter"]*100))

OUT={"baseline":None,"families":{}}
def save(): json.dump(OUT,open("/root/best_strategy/best_strategy.json","w"),indent=1,default=str)

BL=robust(BASE,"BASELINE(derisk0 nofade cut.80 ride1.4)",boot=True)
OUT["baseline"]=BL
print("="*180); print("BASELINE:"); print(line(BL)); print("="*180)
save()

def search_family(key, configs, topn=8):
    results=[robust(P,nm) for nm,P in configs]
    results.sort(key=lambda s:(s["mean_ex_top2"]+s["mean"])/2, reverse=True)  # rank by tail-robust blend
    print("\n##### FAMILY %s  (%d configs, ranked by (mean+mean_ex_top2)/2) #####"%(key,len(configs)))
    for S in results[:topn]:
        lo,hi=bootstrap_ci([r["net"] for r in run(FEATS,S["P"],SIZE)]); S["ci_lo"],S["ci_hi"]=lo,hi
        print(line(S))
    OUT["families"][key]=[{k:v for k,v in s.items() if k!="P"}|{"P":s["P"]} for s in results[:topn]]
    save()
    return results

def mk(**kw):
    p=dict(BASE); p.update(kw); return p

# ---------------- FAMILY 1: EXIT GRID ----------------
cfgs=[]
for derisk in [0.0,0.1]:
 for ride in [1.2,1.3,1.4,1.5,1.7]:
  for trail in [0.85,0.88,0.90,0.92,0.95]:
   for cut in [0.70,0.75,0.80,0.85,0.90]:
    for ladder in [0.0,0.25,0.5]:
     for cap in [15,25,40,70]:
       nm="d%.1f r%.1f t%.2f c%.2f l%.2f cap%d"%(derisk,ride,trail,cut,ladder,cap)
       cfgs.append((nm,mk(derisk_frac=derisk,ride_mult=ride,trail_frac=trail,cut_r=cut,ladder_frac=ladder,cap_slots=cap)))
F1=search_family("1_exitgrid",cfgs,topn=10)
BEST1=F1[0]
print("\nFAMILY1 BEST:",line(BEST1))

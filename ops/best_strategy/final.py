#!/usr/bin/env python3
"""Final confirmation: left-tail/worst-trade for candidates, cap_ride (let winners run past cap),
paired-split tests vs baseline AND vs BEXIT, Kelly per candidate. Pick winner."""
import json, random, sys, math, statistics as st
sys.path.insert(0,"/root/best_strategy")
from engine import simulate, FEATS, stats, run

random.seed(7); SIZE=0.5
def P(**kw):
    d=dict(s0=1.0,add_units=0.0,derisk_frac=0.0,ride_mult=1.70,trail_frac=0.90,
           cut_r=0.70,ladder_frac=0.0,cap_slots=15,fade=False); d.update(kw); return d
def pn(cfg): return [r["net"] for r in run(FEATS,cfg,SIZE)]

CAND={
 "BASELINE(cut.80 ride1.4 ladder.25)": P(cut_r=0.80,ride_mult=1.4,ladder_frac=0.25,cap_slots=40),
 "BEXIT(cut.70 ride1.7 cap15)":        P(cut_r=0.70,ride_mult=1.7,cap_slots=15),
 "W-nocut cap15 ride2.0":              P(cut_r=0.0,ride_mult=2.0,trail_frac=0.90,cap_slots=15),
 "W-nocut cap15 ride2.0 capR70":       P(cut_r=0.0,ride_mult=2.0,trail_frac=0.90,cap_slots=15,cap_ride=70),
 "W-nocut cap15 ride2.0 capR120":      P(cut_r=0.0,ride_mult=2.0,trail_frac=0.90,cap_slots=15,cap_ride=120),
 "W-nocut cap40 ride1.7":              P(cut_r=0.0,ride_mult=1.7,trail_frac=0.90,cap_slots=40),
 "W-cut.50 cap15 ride2.0 capR70":      P(cut_r=0.50,ride_mult=2.0,trail_frac=0.90,cap_slots=15,cap_ride=70),
}
NETS={k:pn(v) for k,v in CAND.items()}
BL=NETS["BASELINE(cut.80 ride1.4 ladder.25)"]; BE=NETS["BEXIT(cut.70 ride1.7 cap15)"]

# random 50/50 splits (paired)
N=len(FEATS); IDX=list(range(N)); SPL=[]
for _ in range(400):
    perm=IDX[:]; random.shuffle(perm); SPL.append(set(perm[N//2:]))
def paired(a,b):
    pb=0; ds=[]
    for va in SPL:
        av=sum(a[i] for i in va)/len(va); bv=sum(b[i] for i in va)/len(va)
        ds.append(av-bv); pb+=av>bv
    return sum(ds)/len(ds), pb/len(SPL)
def tail(v):
    s=sorted(v); n=len(s)
    return {"worst":s[0],"p01":s[int(.01*n)],"p05":s[int(.05*n)],"p10":s[int(.10*n)]}
def kelly(v):
    def lg(f):
        t=0.0
        for g in v:
            x=1+f*g
            if x<=1e-9: return -1e9
            t+=math.log(x)
        return t/len(v)
    bf,bl=0,-1e9; f=0.02
    while f<=1.0001:
        l=lg(f)
        if l>bl: bl,bf=l,f
        f+=0.02
    return bf,lg(0.15),lg(0.25)

print("%-38s mean    med     win   tot    mdd    exT2    worst   p05    | dVSbase p%%  | dVSbexit p%%  | f* hK(.15)"%"candidate")
RES={}
for k,cfg in CAND.items():
    v=NETS[k]
    s=stats(run(FEATS,cfg,SIZE),FEATS); t=tail(v)
    db,pb=paired(v,BL); de,pe=paired(v,BE); fs,l15,l25=kelly(v)
    RES[k]={"stats":s,"tail":t,"vs_base":[db,pb],"vs_bexit":[de,pe],"kelly":[fs,l15]}
    print("%-38s %+.4f %+.4f %4.1f%% %6.2f %6.2f %+.4f %+.4f %+.4f | %+.4f %4.0f%% | %+.4f %4.0f%% | %.2f %+.4f"%(
        k,s["mean"],s["median"],s["win"]*100,s["tot"],s["mdd"],s["mean_ex_top2"],
        t["worst"],t["p05"],db,pb*100,de,pe*100,fs,l15))

OUT=json.load(open("/root/best_strategy/best_strategy.json"))
OUT["final_candidates"]={k:{"P":CAND[k],"mean":RES[k]["stats"]["mean"],"median":RES[k]["stats"]["median"],
    "win":RES[k]["stats"]["win"],"tot":RES[k]["stats"]["tot"],"mdd":RES[k]["stats"]["mdd"],
    "mean_ex_top2":RES[k]["stats"]["mean_ex_top2"],"runner_capture":RES[k]["stats"]["runner_capture"],
    "dump_bleed":RES[k]["stats"]["dump_bleed"],"worst_trade":RES[k]["tail"]["worst"],
    "p05":RES[k]["tail"]["p05"],"vs_base_delta":RES[k]["vs_base"][0],"vs_base_pbetter":RES[k]["vs_base"][1],
    "vs_bexit_delta":RES[k]["vs_bexit"][0],"vs_bexit_pbetter":RES[k]["vs_bexit"][1],
    "kelly_fstar":RES[k]["kelly"][0]} for k in CAND}
json.dump(OUT,open("/root/best_strategy/best_strategy.json","w"),indent=1,default=str)
print("\nsaved final_candidates.")

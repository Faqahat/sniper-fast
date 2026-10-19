#!/usr/bin/env python3
"""Family 5 (re-entry) + Family 6 (size/Kelly) + size-drag at 0.5 vs 2.0 SOL.
Operates on the chosen best strategy (set BEST below after fams 1-4)."""
import json, random, sys, statistics as st, math
sys.path.insert(0,"/root/best_strategy")
from engine import simulate, FEATS, stats, run, HAIRCUT

random.seed(7)
BEXIT=dict(s0=1.0,add_units=0.0,derisk_frac=0.0,ride_mult=1.70,trail_frac=0.90,
           cut_r=0.70,ladder_frac=0.0,cap_slots=15,fade=False)

# ---------------- FAMILY 5: RE-ENTRY ----------------
# After the primary trade exits (cut/trail/cap), if the token later makes a NEW HIGH above
# reentry_mult * entry, re-enter at that price and run BEXIT again (fresh cost basis). Measure the
# EV of the re-entry leg alone and combined.
def primary_exit_slot(f,P):
    """replay to find the slot at which the primary position is fully closed (approx: last sell)."""
    # cheap: rerun simulate but capture last poll index used. We re-implement lightly.
    e=f["entry"]; es=f["entry_slot"]; ser=f["path"]
    remaining=1.0; peak=1.0; riding=False; first=True; last=es
    polls=[(es,e)]+[(s,p) for s,p in ser]
    for i,(slot,px) in enumerate(polls):
        if remaining<=1e-9: return slot,i
        r=px/e
        if r>peak: peak=r
        if not riding and r>=P["ride_mult"]: riding=True
        age=slot-es
        if first: first=False; continue
        if r<=P["cut_r"] or (riding and r<=peak*P["trail_frac"]) or age>=P["cap_slots"]:
            return slot,i
    return (ser[-1][0] if ser else es), len(polls)-1

def reentry_eval(reentry_mult):
    base_nets=[]; combo_nets=[]; nre=0; re_nets=[]
    for f in FEATS:
        res=simulate(f["entry"],f["entry_slot"],f["path"],BEXIT,0.5)
        base_nets.append(res["net"])
        exslot,exi=primary_exit_slot(f,BEXIT)
        # look for new high above reentry_mult*entry AFTER exit
        e=f["entry"]; ser=f["path"]
        tail=[(s,p) for s,p in ser if s>exslot]
        combo=res["net"]
        for j,(s,p) in enumerate(tail):
            if p/e>=reentry_mult:
                # re-enter here with remaining tail as its path
                subpath=tail[j:]
                rentry_px=p
                sub=[(ss,pp) for ss,pp in subpath[1:]]
                rr=simulate(rentry_px,s,sub,BEXIT,0.5)
                combo+=rr["net"]; re_nets.append(rr["net"]); nre+=1
                break
        combo_nets.append(combo)
    def m(x): return sum(x)/len(x) if x else 0.0
    return {"reentry_mult":reentry_mult,"n_reentries":nre,
            "base_mean":m(base_nets),"combo_mean":m(combo_nets),
            "reentry_leg_mean":m(re_nets),"reentry_leg_tot":sum(re_nets),
            "base_tot":sum(base_nets),"combo_tot":sum(combo_nets)}

print("##### FAMILY 5: RE-ENTRY #####")
re_results=[]
for rm in [1.0,1.2,1.5,2.0]:
    r=reentry_eval(rm); re_results.append(r)
    print("reentry>=%.1fx: n_re=%d  base_mean %+.4f -> combo_mean %+.4f  (reentry-leg mean %+.4f over %d, tot %+.2f)"%(
        rm,r["n_reentries"],r["base_mean"],r["combo_mean"],r["reentry_leg_mean"],r["n_reentries"],r["reentry_leg_tot"]))

# ---------------- FAMILY 6: SIZE / KELLY ----------------
print("\n##### FAMILY 6: SIZE / KELLY #####")
def size_stats(SIZE):
    res=run(FEATS,BEXIT,SIZE); return stats(res,FEATS)
for SZ in [0.5,2.0]:
    s=size_stats(SZ)
    print("SIZE %.1f SOL: mean %+.4f med %+.4f win %4.1f%% tot %6.2f sharpe %.3f (lamport drag scales with size)"%(
        SZ,s["mean"],s["median"],s["win"]*100,s["tot"],s["sharpe"]))

# Kelly on the per-trade net-R distribution (SIZE=2.0, lower fixed drag). R is multiplicative
# return per unit of capital deployed on that trade. Treat each trade as iid draw of return g=net
# (fraction gained/lost on the position). Growth-optimal fraction f* maximizes E[log(1+f*g)].
nets=[r["net"] for r in run(FEATS,BEXIT,2.0)]
def logg(frac):
    tot=0.0
    for g in nets:
        v=1+frac*g
        if v<=1e-9: return -1e9
        tot+=math.log(v)
    return tot/len(nets)
# scan fraction
best_f=0;best_lg=-1e9;curve=[]
fr=0.01
while fr<=1.0001:
    lg=logg(fr); curve.append((round(fr,2),lg))
    if lg>best_lg: best_lg,best_f=lg,fr
    fr+=0.01
print("Kelly-optimal fraction of bankroll per trade f* = %.2f  (E[log] growth/trade = %+.5f)"%(best_f,best_lg))
print("  log-growth at f=0.05: %+.5f  f=0.10: %+.5f  f=0.25: %+.5f  f=0.50: %+.5f  f=1.0: %+.5f"%(
    logg(0.05),logg(0.10),logg(0.25),logg(0.50),logg(1.0)))
# prob of ruin-ish: worst single trade
print("  worst single-trade net R: %+.4f  (so full-size f=1.0 loses %.1f%% on worst trade)"%(min(nets),-min(nets)*100))
frac_kelly=round(best_f*0.5,2)
print("  RECOMMEND fractional-Kelly f ~ %.2f (half-Kelly) -> log-growth %+.5f, far from ruin"%(frac_kelly,logg(frac_kelly)))

OUT=json.load(open("/root/best_strategy/best_strategy.json"))
OUT["family5_reentry"]=re_results
OUT["family6_kelly"]={"f_star":best_f,"log_growth":best_lg,"worst_trade":min(nets),
                      "half_kelly":frac_kelly,"size_drag":{"0.5":size_stats(0.5)["mean"],"2.0":size_stats(2.0)["mean"]}}
json.dump(OUT,open("/root/best_strategy/best_strategy.json","w"),indent=1,default=str)
print("\nsaved families 5-6.")

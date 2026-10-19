#!/usr/bin/env python3
"""THESIS 1 v2 - NO LOOK-AHEAD. The early-inflow/buyer signal is measured over [create, create+Wobs].
A trader who uses that signal can only ENTER at create+Wobs (after observing it), NOT at create+1.
So entry_px = price at create+Wobs; forward return measured from there. This removes the look-ahead
that inflated the create+1 cells. Compare: (A) naive create+1 entry (look-ahead for gated sels),
(B) honest gated entry at signal-window end. NET of 1%/leg + 0.5% slip."""
import sys, os, json, glob, statistics as st
LT="/root/edge_hunt/long_traj"; SPS=2.5; FEE=0.01; SLIP=0.005
def net(g): return g*(1-FEE-SLIP/2)/(1+FEE+SLIP/2)-1
HOR={"10s":25,"30s":75,"1m":150,"5m":750,"15m":2250}
def load():
    recs=[]
    for f in glob.glob(LT+"/*.json"):
        try: d=json.load(open(f))
        except: continue
        recs.append(d)
    return recs
def px_floor_at(series,t):
    v=None
    for sl,bt,px,ds in series:
        if sl<=t: v=px
        else: break
    return v
def px_first_from(series,t):
    for sl,bt,px,ds in series:
        if sl>=t: return px,sl
    return None,None
def flow(d,k):
    cs=d["create_slot"]; nb=0; infl=0.0
    for sl,bt,px,ds in d["series"]:
        if sl<=cs+k:
            if ds>0: nb+=1
            infl+=ds
        else: break
    return nb,infl
recs=load()
have=[r for r in recs if r.get("series")]
from collections import Counter
cc=Counter(r.get("creator") for r in have)
for r in have:
    r["_van"]=(r.get("creator_fee_bps")==0 and not r.get("mayhem") and not r.get("holder_reward") and not r.get("cashback"))
    r["_crl"]=cc[r.get("creator")]
recs_s=sorted(have,key=lambda r:r["create_slot"]); split=recs_s[len(recs_s)//2]["create_slot"]
for r in have: r["_grp"]="train" if r["create_slot"]<split else "val"
print(f"{len(have)} trajectories w/ trades. split slot {split}. breakeven gross ~{1/((1-FEE-SLIP/2)/(1+FEE+SLIP/2)):.4f}")

def summ(rs):
    rs=sorted(rs); n=len(rs)
    if n==0: return None
    return dict(n=n,mean=sum(rs)/n,med=rs[n//2],win=sum(1 for x in rs if x>0)/n,drop2=(sum(rs[:-2])/(n-2) if n>2 else sum(rs)/n))

# GATED HONEST: observe inflow/buyers over [create, create+Wobs]; enter at first trade >= create+Wobs; hold +hor
def run(sel_name, Wobs, min_inflow, min_buyers, vanilla_only, hor_slots, grp):
    rs=[]
    for r in have:
        if r["_grp"]!=grp: continue
        if vanilla_only and not r["_van"]: continue
        nb,infl=flow(r,Wobs)
        if infl<min_inflow or nb<min_buyers: continue
        cs=r["create_slot"]
        ent,es=px_first_from(r["series"], cs+Wobs)   # entry AFTER observing the window (no look-ahead)
        if ent is None: 
            # no trade after window -> would exit at last known ~ entry; treat as flat (skip, rare)
            continue
        xpx=px_floor_at(r["series"], es+hor_slots)
        if xpx is None: xpx=ent
        rs.append(net(xpx/ent))
    return summ(rs)

print("\n=== HONEST GATED ENTRY (observe Wobs=10s inflow, ENTER at window end, hold horizon) ===")
print("selection                         hor   TRAIN mean/med/win/n       VAL mean/med/win/drop2/n")
configs=[
 ("van, no inflow gate", 25, -1e9, 0, True),
 ("van+inflow>=2@10s", 25, 2.0, 0, True),
 ("van+inflow>=5@10s", 25, 5.0, 0, True),
 ("van+buyers>=5+infl>=2@10s", 25, 2.0, 5, True),
 ("van+inflow>=10@10s", 25, 10.0, 0, True),
 ("van+inflow>=2@30s(obs)", 75, 2.0, 0, True),
 ("van+inflow>=5@30s(obs)", 75, 5.0, 0, True),
]
for nm,Wobs,mi,mb,vo in configs:
    for h,hs in HOR.items():
        tr=run(nm,Wobs,mi,mb,vo,hs,"train"); va=run(nm,Wobs,mi,mb,vo,hs,"val")
        if not va or va["n"]<15: continue
        ts="%+.4f/%+.4f/%.0f%%/%d"%(tr["mean"],tr["med"],tr["win"]*100,tr["n"]) if tr else "n/a"
        vs="%+.4f/%+.4f/%.0f%%/%+.4f/%d"%(va["mean"],va["med"],va["win"]*100,va["drop2"],va["n"])
        flag=" <===" if (va["mean"]>0 and va["drop2"]>0 and va["n"]>=20) else ""
        print(f"{nm:30s} {h:4s}  {ts:26s} {vs}{flag}")

# Also: the NAIVE create+1 entry version of the same gated sels (to SHOW the look-ahead inflation)
print("\n=== NAIVE create+1 entry w/ same inflow gate (LOOK-AHEAD - for comparison only) ===")
def run_naive(Wobs,mi,vo,hor_slots,grp):
    rs=[]
    for r in have:
        if r["_grp"]!=grp: continue
        if vo and not r["_van"]: continue
        nb,infl=flow(r,Wobs)
        if infl<mi: continue
        cs=r["create_slot"]; ent,es=px_first_from(r["series"],cs+1)
        if ent is None: continue
        xpx=px_floor_at(r["series"], es+hor_slots) or ent
        rs.append(net(xpx/ent))
    return summ(rs)
for mi in [2.0,5.0]:
    for h,hs in [("10s",25),("30s",75)]:
        va=run_naive(25,mi,True,hs,"val")
        if va: print(f"van+inflow>={mi}@10s (create+1 entry) {h}: VAL mean={va['mean']:+.4f} med={va['med']:+.4f} n={va['n']}")

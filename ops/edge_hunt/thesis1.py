#!/usr/bin/env python3
"""THESIS 1 - longer-horizon hold/trend from a create+1 entry.
Forward-return distribution at 10s/30s/1m/5m/15m/grad, with selection filters, OOS train/val split.
NET of cost: 1%/leg pump fee (2% round trip) + 0.5% round-trip curve slippage at small size.
Breakeven gross multiple ~ (1.0125)/(0.9875) ~ 1.0253 (need +2.53% gross to clear)."""
import sys, os, json, glob, statistics as st

LT = "/root/edge_hunt/long_traj"
SLOTS_PER_S = 2.5
FEE_LEG = 0.01; SLIP_RT = 0.005
# net multiple from gross g: buy basis g up by fee+half-slip, sell proceeds down by fee+half-slip
def net_R(g):
    return g * (1-FEE_LEG-SLIP_RT/2) / (1+FEE_LEG+SLIP_RT/2) - 1

HOR = {"10s":int(10*SLOTS_PER_S), "30s":int(30*SLOTS_PER_S), "1m":int(60*SLOTS_PER_S),
       "5m":int(300*SLOTS_PER_S), "15m":int(900*SLOTS_PER_S)}

def load():
    recs=[]
    for f in glob.glob(LT+"/*.json"):
        try: d=json.load(open(f))
        except Exception: continue
        s=d.get("series") or []
        if not s: 
            d["_entry"]=None; recs.append(d); continue
        cs=d["create_slot"]
        # entry = first trade at slot >= cs+1 (our create+1 fill proxy)
        entry=None; entry_slot=None
        for (slot,bt,px,ds) in s:
            if slot >= cs+1:
                entry=px; entry_slot=slot; break
        if entry is None:  # only create-slot trades exist -> use last create-slot px as fill
            entry=s[-1][2]; entry_slot=s[-1][0]
        d["_entry"]=entry; d["_entry_slot"]=entry_slot
        # floor = create-slot dev-buy price (entry_px field) for congestion ratio
        recs.append(d)
    return recs

def px_at(series, t):
    """last trade px at or before slot t (hold-last); None if no trade <= t."""
    v=None
    for (slot,bt,px,ds) in series:
        if slot<=t: v=px
        else: break
    return v

def early_flow(d, k=25):
    """buyers (buy count) and net sol inflow in first k slots after create."""
    cs=d["create_slot"]; nb=0; inflow=0.0
    for (slot,bt,px,ds) in d["series"]:
        if slot<=cs+k:
            if ds>0: nb+=1
            inflow+=ds
        else: break
    return nb, inflow

def forward(d, hor_slots):
    e=d["_entry"]; 
    if not e: return None
    t=d["_entry_slot"]+hor_slots
    p=px_at(d["series"], t)
    if p is None: p=d["_entry"]  # no later trade -> flat
    return p/e

def main():
    recs=load()
    have=[r for r in recs if r["_entry"]]
    print(f"loaded {len(recs)} trajectories, {len(have)} with a create+1 entry")
    # slot split train/val
    recs_s=sorted(have, key=lambda r:r["create_slot"])
    split=recs_s[len(recs_s)//2]["create_slot"]
    for r in have:
        r["_grp"]="train" if r["create_slot"]<split else "val"
        r["_van"]= (r.get("creator_fee_bps")==0 and not r.get("mayhem") and not r.get("holder_reward") and not r.get("cashback"))
        r["_nb5"], r["_inflow5"] = early_flow(r,12)   # ~5s
        r["_nb10"], r["_inflow10"] = early_flow(r,25)  # ~10s
    # creator launch counts in window (anti-factory)
    from collections import Counter
    cc=Counter(r.get("creator") for r in have)
    for r in have: r["_crlaunch"]=cc[r.get("creator")]

    def cell(subset, hor_slots):
        rs=[net_R(forward(r,hor_slots)) for r in subset if forward(r,hor_slots) is not None]
        if not rs: return None
        rs.sort()
        n=len(rs); mean=sum(rs)/n; med=rs[n//2]; win=sum(1 for x in rs if x>0)/n
        # drop top 2 for tail-robustness
        d2=sum(rs[:-2])/(n-2) if n>2 else mean
        return dict(n=n, mean=mean, med=med, win=win, drop2=d2, p90=rs[int(n*.9)])

    SEL = {
      "ALL":         lambda r: True,
      "vanilla":     lambda r: r["_van"],
      "van+dev>=0.5":lambda r: r["_van"] and r.get("dev_buy",0)>=0.5,
      "van+dev>=1":  lambda r: r["_van"] and r.get("dev_buy",0)>=1.0,
      "van+dev2-10": lambda r: r["_van"] and 2.0<=r.get("dev_buy",0)<=10.0,
      "van+antifac": lambda r: r["_van"] and r.get("_crlaunch",1)<=2,
      "van+buyers>=5@10s": lambda r: r["_van"] and r["_nb10"]>=5,
      "van+buyers>=10@10s":lambda r: r["_van"] and r["_nb10"]>=10,
      "van+inflow>=2@10s": lambda r: r["_van"] and r["_inflow10"]>=2.0,
      "van+inflow>=5@10s": lambda r: r["_van"] and r["_inflow10"]>=5.0,
      "van+buyers>=5+inflow>=2":lambda r: r["_van"] and r["_nb10"]>=5 and r["_inflow10"]>=2.0,
    }
    print(f"\nTrain/Val split at slot {split}.  breakeven gross ~ {1/((1-FEE_LEG-SLIP_RT/2)/(1+FEE_LEG+SLIP_RT/2)):.4f}")
    print("NET-of-fee mean R per horizon x selection (TRAIN mean | VAL mean/med/win/drop2/n):\n")
    hdr="%-24s"%"selection" + "".join("%12s"%h for h in HOR)
    print(hdr)
    results=[]
    for name,fn in SEL.items():
        tr=[r for r in have if r["_grp"]=="train" and fn(r)]
        va=[r for r in have if r["_grp"]=="val" and fn(r)]
        row="%-24s"%name
        for h,hs in HOR.items():
            c=cell(va,hs)
            row+= ("%+11.4f"%c["mean"]) if c else "        n/a "
        print(row+"  (val n=%d)"%len(va))
    # Detailed best cells: scan all sel x hor, rank by VAL drop2 with n>=20
    print("\nFULL CELL DETAIL (VAL, n>=20), ranked by net mean:")
    rows=[]
    for name,fn in SEL.items():
        tr=[r for r in have if r["_grp"]=="train" and fn(r)]
        va=[r for r in have if r["_grp"]=="val" and fn(r)]
        for h,hs in HOR.items():
            ctr=cell(tr,hs); cva=cell(va,hs)
            if cva and cva["n"]>=20:
                rows.append((name,h,ctr,cva))
    rows.sort(key=lambda x:-x[3]["mean"])
    print("%-24s %-5s | %-28s | %-40s"%("selection","hor","TRAIN mean/med/win/n","VAL mean/med/win/drop2/n"))
    for name,h,ctr,cva in rows[:18]:
        ts="%+.4f/%+.4f/%.0f%%/%d"%(ctr["mean"],ctr["med"],ctr["win"]*100,ctr["n"]) if ctr else "n/a"
        vs="%+.4f/%+.4f/%.0f%%/%+.4f/%d"%(cva["mean"],cva["med"],cva["win"]*100,cva["drop2"],cva["n"])
        print("%-24s %-5s | %-28s | %s"%(name,h,ts,vs))

if __name__=="__main__": main()

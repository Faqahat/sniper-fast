#!/usr/bin/env python3
"""Lag-tolerant entry test: buy at first trade >= create_slot+K (market px), ride trailing ladder, net costs.
Tests whether a NON-floor, lag-tolerant momentum entry is +EV (our warm-send fits this; no intra-slot race)."""
import json,statistics
t=json.load(open("/root/profit_backtest/trajectories.json"))
FEE=0.01   # pump 1%/leg
SLIP=0.004 # ~0.4%/leg market taker slippage (worse than floor snipe)
PRIO=0.00037  # fixed SOL/leg priority
def sim(entry_px, fwd, size, derisk=0.0, ride=1.4, trail=0.92, cut=0.95, cap=40):
    # fwd = list of (slot,px) strictly after entry; r relative to entry_px (net of entry cost baked into R)
    if not fwd: 
        # sold immediately at entry -> lose round-trip cost
        rt_cost = 2*FEE+2*SLIP + 2*PRIO/size
        return -rt_cost
    peak=entry_px; sold_frac=0.0; proceeds=0.0; armed=False
    legs=1  # buy leg
    for i,(slot,px) in enumerate(fwd[:cap]):
        r=px/entry_px
        if r>peak/entry_px: peak=px
        # ride trigger: once r>=ride, arm trailing
        if r>=ride: armed=True
        # trailing stop
        stop = (peak/entry_px)*trail
        do_exit=False; frac=1.0
        if r<=cut and not armed:    # hard cut below entry
            do_exit=True
        elif armed and r<=stop:
            do_exit=True
        elif i==min(cap,len(fwd))-1:
            do_exit=True
        if do_exit:
            proceeds += (1.0-sold_frac)*r
            legs+=1
            sold_frac=1.0
            break
    if sold_frac<1.0:
        proceeds += (1.0-sold_frac)*(fwd[min(cap,len(fwd))-1][1]/entry_px)
        legs+=1
    # gross R = proceeds-1 (fraction); apply costs: fee+slip per leg on notional, prio fixed per leg
    gross=proceeds-1.0
    pct_cost=(FEE+SLIP)*legs
    fixed=PRIO*legs/size
    return gross-pct_cost-fixed

def run(K,size=0.5):
    Rs=[]
    for x in t:
        s=x.get("series") or []
        cs=x["create_slot"]
        # entry = first trade at slot>=cs+K
        ent=None;idx=None
        for i,(slot,px) in enumerate(s):
            if slot>=cs+K and px>0:
                ent=px; idx=i; break
        if ent is None: continue
        fwd=[(sl,p) for (sl,p) in s[idx+1:] if p>0]
        Rs.append(sim(ent,fwd,size))
    if not Rs: return None
    Rs.sort()
    n=len(Rs); mean=statistics.mean(Rs); med=statistics.median(Rs)
    win=sum(1 for r in Rs if r>0)/n
    tot=sum(Rs)
    ex2=statistics.mean(sorted(Rs)[:-2]) if n>2 else mean
    return dict(K=K,n=n,mean=round(mean,4),med=round(med,4),win=round(win,3),tot=round(tot,2),meanex2=round(ex2,4),p90=round(Rs[int(.9*n)],3),p99=round(Rs[min(n-1,int(.99*n))],3))

print("size=0.5 SOL, exit derisk0/ride1.4/trail.92/cut.95/cap40")
rows=[]
for K in [0,1,2,3,5,10,20]:
    r=run(K)
    rows.append(r)
    if r:
        print("K=%2d n=%4d mean=%+.4f med=%+.4f win=%.0f%% tot=%+.1f meanEx2=%+.4f p90=%+.2f p99=%+.1f"%(r["K"],r["n"],r["mean"],r["med"],r["win"]*100,r["tot"],r["meanex2"],r["p90"],r["p99"]))
json.dump(rows,open("/root/landscape/lagentry.json","w"))

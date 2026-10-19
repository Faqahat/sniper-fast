#!/usr/bin/env python3
"""THESIS 3 - copy/ride the proven sniper 4yFAz. We detect his buy and enter LAG slots later at the
then-current market price (worse than his fill), then exit on a rule. NET of 1%/leg + 0.5% slip.
Data: exit_study/rows2.json (his bslot, px_entry=his fill, sells, r5/r10/r20, peak_r, last_dslot)
      exit_study/paths.json (market price path per mint: pts=[slot,px])."""
import json, statistics as st
R = json.load(open("/root/exit_study/rows2.json"))
P = json.load(open("/root/exit_study/paths.json"))
FEE_LEG=0.01; SLIP_RT=0.005
def net_from_gross(g):
    return g*(1-FEE_LEG-SLIP_RT/2)/(1+FEE_LEG+SLIP_RT/2)-1
paths={m:P[m]["pts"] for m in P if isinstance(P[m],dict) and P[m].get("pts")}

def px_at(pts, t):
    v=None
    for slot,px in pts:
        if slot<=t: v=px
        else: break
    return v
def px_from(pts, t):
    """first px at slot>=t (what we'd fill entering at/after t); fallback last<=t."""
    for slot,px in pts:
        if slot>=t: return px
    return px_at(pts,t)

def sim(lag, exit_rule, ride_gate=None):
    """exit_rule: 'his_exit' uses his weighted exit path; 'tgt_X' fixed target; 'orderflow' ride/cut by r@+10.
       Returns net R list."""
    out=[]
    for row in R:
        m=row["mint"]; pts=paths.get(m)
        if not pts: continue
        he=row["px_entry"]; bslot=row["bslot"]
        our_entry=px_from(pts, bslot+lag)
        if not our_entry or our_entry<=0: continue
        # exit price selection
        if exit_rule=="his_exit":
            # exit at his last sell slot's market px (we follow him out)
            ls=bslot+row["last_dslot"]
            ex=px_at(pts, ls) or pts[-1][1]
        elif exit_rule.startswith("tgt_"):
            tgt=float(exit_rule.split("_")[1])  # multiple on OUR entry
            ex=None
            for slot,px in pts:
                if slot>=bslot+lag and px>=our_entry*tgt: ex=px; break
            if ex is None:  # never hit -> exit at his last-sell market px (fallback)
                ex=px_at(pts, bslot+row["last_dslot"]) or pts[-1][1]
        elif exit_rule=="orderflow":
            # decide at +10 slots from OUR entry: if market r@+10 (vs our entry) >=1.05 ride to his last sell, else cut now
            p10=px_at(pts, bslot+lag+10) or our_entry
            if p10/our_entry>=1.05:
                ex=px_at(pts, bslot+row["last_dslot"]) or pts[-1][1]
            else:
                ex=p10
        else:
            ex=pts[-1][1]
        g=ex/our_entry
        out.append(net_from_gross(g))
    return out

def summ(rs):
    if not rs: return "n=0"
    rs2=sorted(rs); n=len(rs2); mean=sum(rs2)/n; med=rs2[n//2]; win=sum(1 for x in rs2 if x>0)/n
    d2=sum(rs2[:-2])/(n-2) if n>2 else mean
    return f"n={n} mean={mean:+.4f} med={med:+.4f} win={win*100:.0f}% drop2={d2:+.4f}"

print("breakeven gross ~ %.4f (need +%.2f%% gross)"%(1/((1-FEE_LEG-SLIP_RT/2)/(1+FEE_LEG+SLIP_RT/2)), (1/((1-FEE_LEG-SLIP_RT/2)/(1+FEE_LEG+SLIP_RT/2))-1)*100))
print("\n--- baseline: his ACTUAL realized (from rows) ---")
real=[r["realized"]/max(r["sol_in"],1e-9) for r in R]
print("his realized R:", summ(real))

print("\n--- our LAGGED copy, NET of fee, by lag x exit rule ---")
for lag in [1,2,3,4,6]:
    print(f"\nLAG={lag} slots (~{lag*0.2:.1f}s behind him):")
    for rule in ["his_exit","orderflow","tgt_1.10","tgt_1.20","tgt_1.30"]:
        print(f"  {rule:12s}: {summ(sim(lag,rule))}")

# ride only his WINNERS (he held >N slots) -- note: look-ahead unless gated by order-flow
print("\n--- subset: ride only positions where HE held > 10 slots (his winners proxy; LOOK-AHEAD) ---")
for lag in [1,2,4]:
    rs=[]
    for row in R:
        if row["last_dslot"]<=10: continue
        m=row["mint"]; pts=paths.get(m)
        if not pts: continue
        oe=px_from(pts,row["bslot"]+lag); 
        if not oe: continue
        ex=px_at(pts,row["bslot"]+row["last_dslot"]) or pts[-1][1]
        rs.append(net_from_gross(ex/oe))
    print(f"  lag={lag} his_exit on held>10: {summ(rs)}")

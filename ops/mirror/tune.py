#!/usr/bin/env python3
"""STEP 4 — validate harness vs exit_study, then tune exit config to best mirror his tape.
Entry = his fill (r=1.0). Compare shipped vs derived vs grid. Cost sweep."""
import json, statistics as st
TAPE=[t for t in json.load(open("/root/mirror/his_tape.json")) if t["has_path"]]
PUMP_FEE=0.01; CURVE_SLIP=0.0025; PRIO_LAM=360_000; BASE_LAM=5_000; LSOL=1e9

def seqof(t):
    pts=sorted(t["path"],key=lambda x:x[0]); b=t["buy_slot"]; pe=t["his_fill_px"]
    seq=[(0,1.0)]
    for s,px in pts:
        r=px/pe; d=s-b
        # PREBUY-RAMP FIX: drop same-slot points below his fill (create-slot ramp printed BEFORE his buy)
        if d>=1 and 0.3<=r<=200: seq.append((d,r))
        elif d==0 and r>=1.0 and r<=200: seq.append((d,r))
    seq.sort(); return seq

def ladder(seq,P,fade=False):
    remaining=1.0;peak=1.0;riding=False;first=True;last=0;legs=[]
    for d,rr in seq:
        if remaining<=1e-9:break
        if rr>peak:peak=rr
        if not riding and rr>=P["ride"]:riding=True
        if first:
            first=False;q=min(P["derisk"],remaining);legs.append((rr,q));remaining-=q;last=d;continue
        if rr<=P["cut"]:legs.append((rr,remaining));remaining=0;break
        if riding and rr<=peak*P["trail"]:legs.append((rr,remaining));remaining=0;break
        if d>=P["cap"]:legs.append((rr,remaining));remaining=0;break
        if fade and (not riding) and rr<1.0 and d>last:legs.append((rr,remaining));remaining=0;break
        if (not riding) and 1.0<=rr<P["ride"] and (d-last)>=4:
            q=min(remaining*P["ladder"],remaining);legs.append((rr,q));remaining-=q;last=d
    if remaining>1e-9:legs.append((seq[-1][1],remaining));remaining=0
    return legs

def netR(legs,size,costs=True):
    if costs:
        hair=PUMP_FEE+CURVE_SLIP
        proc=sum(f*rr*(1-hair) for rr,f in legs)
        gross=proc-(1.0+PUMP_FEE+CURVE_SLIP)
        fixed=(1+len(legs))*(PRIO_LAM+BASE_LAM)/LSOL/size
        return gross-fixed
    else:
        return sum(f*rr for rr,f in legs)-1.0

def run(P,fade=False,size=0.5,costs=True,slip_extra=0.0):
    vals=[]
    for t in TAPE:
        legs=ladder(seqof(t),P,fade)
        if slip_extra:  # exit_study style: flat haircut on proceeds, no fixed prio
            proc=sum(f*rr*(1-0.012-slip_extra) for rr,f in legs)
            vals.append((proc-1.0)*t["sol_in"])  # SOL
        else:
            vals.append(netR(legs,size,costs))
    return vals

his=[t["realized_sol"] for t in TAPE]
hisR=[t["realized_R"] for t in TAPE]
print(f"HIS: totSOL={sum(his):+.2f} meanR={sum(hisR)/len(hisR):+.4f} win={sum(1 for x in his if x>0)/len(his):.3f} n={len(TAPE)}")

print("\n--- HARNESS VALIDATION vs exit_study (SOL, exit_study cost style: 1.2%/leg+slip, his sizes) ---")
derived=dict(derisk=0.30,ride=1.40,trail=0.92,cut=0.95,ladder=0.25,cap=42)
for slip,label in [(0.0,"no drag"),(0.01,"+1%"),(0.02,"+2%"),(0.03,"+3%")]:
    v=run(derived,fade=True,slip_extra=slip)
    print(f"  derived+fade {label:7s}: totSOL={sum(v):+.2f} mean={sum(v)/len(v):+.4f} win={sum(1 for x in v if x>0)/len(v):.3f}  (exit_study: +42.7/+37.4/+32.2/+26.9)")

print("\n--- CONFIG COMPARISON on his tape (net R @0.5 SOL, econ_102 cost model) ---")
def rpt(name,P,fade=False):
    v=run(P,fade=fade,size=0.5,costs=True)
    vg=run(P,fade=fade,size=0.5,costs=False)
    tot=sum(v);n=len(v)
    # correlation with his R
    pairs=list(zip(hisR,[netR(ladder(seqof(t),P,fade),0.5) for t in TAPE]))
    mx=sum(hisR)/n;my=sum(p[1] for p in pairs)/n
    num=sum((a-mx)*(b-my) for a,b in pairs)
    dx=sum((a-mx)**2 for a in hisR)**.5;dy=sum((b-my)**2 for _,b in pairs)**.5
    c=num/(dx*dy) if dx and dy else 0
    sign=sum(1 for a,b in pairs if (a>0)==(b>0))/n
    print(f"  {name:34s} netR_tot={tot:+6.2f} mean={tot/n:+.4f} win={sum(1 for x in v if x>0)/n:.3f} "
          f"grossR_mean={sum(vg)/n:+.4f} corr={c:+.3f} sign={sign:.3f}")
    return tot
rpt("SHIPPED (cut.80 no-fade)",dict(derisk=0.30,ride=1.40,trail=0.92,cut=0.80,ladder=0.25,cap=40))
rpt("derived (cut.95)+fade",derived,fade=True)
rpt("derived (cut.95) no-fade",derived)
rpt("derived cut.95 no-fade +fade?",dict(derisk=0.30,ride=1.40,trail=0.92,cut=0.95,ladder=0.25,cap=40))
rpt("econ102-bestOOS d0 ride2 cut.98",dict(derisk=0.0,ride=2.0,trail=0.92,cut=0.98,ladder=0.25,cap=20))
rpt("shipped+fade",dict(derisk=0.30,ride=1.40,trail=0.92,cut=0.80,ladder=0.25,cap=40),fade=True)

print("\n--- GRID SEARCH best mirror config (max net totR @0.5, his tape) ---")
best=[]
for derisk in (0.0,0.15,0.30):
    for ride in (1.2,1.3,1.4,1.6,2.0):
        for trail in (0.85,0.92):
            for cut in (0.80,0.90,0.95,0.98):
                for cap in (20,40,80):
                    for fade in (False,True):
                        P=dict(derisk=derisk,ride=ride,trail=trail,cut=cut,ladder=0.25,cap=cap)
                        v=run(P,fade=fade,size=0.5,costs=True)
                        best.append((sum(v),P,fade,sum(1 for x in v if x>0)/len(v)))
best.sort(key=lambda x:-x[0])
for tot,P,fade,win in best[:6]:
    print(f"  totR={tot:+.2f} win={win:.3f} fade={fade} {P}")

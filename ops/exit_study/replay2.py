import json,statistics as st
rows=json.load(open("rows2.json"))
paths=json.load(open("paths.json"))
SLOT_MS=215.0; FEE=0.012
def pct(xs,p):
    xs=sorted(xs); return xs[min(len(xs)-1,int(round(p*(len(xs)-1))))]
def getseq(r):
    m=r["mint"]; p=paths.get(m,{}); pts=p.get("pts",[])
    pe=r["px_entry"]; b=r["bslot"]
    seq=[(s-b,px/pe) for s,px in pts if s>=b and 0.5<=px/pe<=100]
    seq=[(0,1.0)]+seq  # seed entry
    seq.sort()
    return seq
def sim_one(r,derisk,ride,trail,cut,ladder,cap_ms):
    seq=getseq(r)
    cap_slots=cap_ms/SLOT_MS
    remaining=1.0; peak=1.0; riding=False; first=True; last_sell=0; legs=[]
    for (d,rr) in seq:
        if remaining<=1e-9: break
        if rr>peak: peak=rr
        if (not riding) and rr>=ride: riding=True
        if first:
            first=False; qty=min(derisk,remaining); legs.append((rr,qty,"derisk")); remaining-=qty; last_sell=d; continue
        if rr<=cut: legs.append((rr,remaining,"cut")); remaining=0; break
        if riding and rr<=peak*trail: legs.append((rr,remaining,"trail")); remaining=0; break
        if d>=cap_slots: legs.append((rr,remaining,"cap")); remaining=0; break
        if (not riding) and rr<1.0 and d>last_sell: legs.append((rr,remaining,"fade")); remaining=0; break
        if (not riding) and 1.0<=rr<ride and (d-last_sell)>=4:
            qty=min(remaining*ladder,remaining); legs.append((rr,qty,"ladder")); remaining-=qty; last_sell=d
    if remaining>1e-9: legs.append((seq[-1][1],remaining,"end")); remaining=0
    proceeds=sum(f*rr*(1-FEE) for rr,f,_ in legs)
    return (proceeds-1.0)*r["sol_in"], legs
def sim(cfg):
    out=[]
    for r in rows:
        if not paths.get(r["mint"],{}).get("pts") or not r["px_entry"]: out.append(None); continue
        pnl,_=sim_one(r,*cfg); out.append(pnl)
    return out
his=[r["realized"] for r in rows]; his_sum=sum(his)
print(f"HIS actual (all 200): sum={his_sum:.3f} mean={his_sum/200:.4f} win={sum(1 for x in his if x>0)/200:.3f}")
cfgs={
 "default":(0.40,1.6,0.85,0.85,0.30,8000),
 "derived":(0.30,1.40,0.92,0.95,0.25,9000),
 "derived-ride15":(0.30,1.50,0.92,0.95,0.25,9000),
 "derived-cut97":(0.30,1.40,0.92,0.97,0.25,9000),
 "derived-cut90":(0.30,1.40,0.92,0.90,0.25,9000),
 "derived-ride13-cap12":(0.30,1.30,0.90,0.96,0.25,12000),
}
best=None
for name,cfg in cfgs.items():
    s=sim(cfg); v=[x for x in s if x is not None]; tot=sum(v); win=sum(1 for x in v if x>0)/len(v)
    print(f"{name:22s} sum={tot:7.3f} mean={tot/len(v):.4f} win={win:.3f} n={len(v)}")
json.dump({"rows":rows},open("/dev/null","w"))

print("\n=== DIAGNOSIS (derived cfg) ===")
cfg=(0.30,1.40,0.92,0.95,0.25,9000)
from collections import Counter
reasons=Counter(); 
bad=[]  # his winner but sim loss
for r in rows:
    if not paths.get(r["mint"],{}).get("pts") or not r["px_entry"]: continue
    pnl,legs=sim_one(r,*cfg)
    term=legs[-1][2] if legs else "none"
    reasons[term]+=1
    if r["realized"]>0.1 and pnl<0:
        bad.append((r["realized"],pnl,r["mint"],[(round(l[0],2),round(l[1],2),l[2]) for l in legs],r["peak_r"]))
print("terminal exit reasons:",dict(reasons))
print("\nHis BIG winners that sim turned into losses (n=%d):"%len(bad))
for hr,sp,m,legs,pk in sorted(bad,key=lambda x:x[0],reverse=True)[:8]:
    print(f"  {m[:8]} his+{hr:.2f} sim{sp:+.2f} peak_r={pk and round(pk,2)} legs={legs}")

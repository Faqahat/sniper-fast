import json,statistics as st
rows=json.load(open("rows2.json")); paths=json.load(open("paths.json"))
SLOT_MS=215.0
def getseq(r):
    pts=paths.get(r["mint"],{}).get("pts",[]); pe=r["px_entry"]; b=r["bslot"]
    seq=[(s-b,px/pe) for s,px in pts if s>b and 0.5<=px/pe<=100]; seq.sort(); return seq
def sim_one(r,cfg,lag_pen=0.0):
    derisk,ride,trail,cut,ladder,cap_ms=cfg
    seq=getseq(r)
    if not seq: return 0.0,[]
    cap=cap_ms/SLOT_MS; rem=1.0;peak=1.0;riding=False;first=True;ls=0;legs=[]
    for d,rr in seq:
        if rem<=1e-9: break
        if rr>peak:peak=rr
        if (not riding) and rr>=ride: riding=True
        if first: first=False;q=min(derisk,rem);legs.append((rr,q,"derisk"));rem-=q;ls=d;continue
        if rr<=cut: legs.append((rr,rem,"cut"));rem=0;break
        if riding and rr<=peak*trail: legs.append((rr,rem,"trail"));rem=0;break
        if d>=cap: legs.append((rr,rem,"cap"));rem=0;break
        if (not riding) and rr<1.0 and d>ls: legs.append((rr,rem,"fade"));rem=0;break
        if (not riding) and 1.0<=rr<ride and (d-ls)>=4: q=min(rem*ladder,rem);legs.append((rr,q,"ladder"));rem-=q;ls=d
    if rem>1e-9: legs.append((seq[-1][1],rem,"end"));rem=0
    FEE=0.012+lag_pen
    proceeds=sum(f*rr*(1-FEE) for rr,f,_ in legs)
    return (proceeds-1.0)*r["sol_in"],legs
cfg=(0.30,1.40,0.92,0.95,0.25,9000)
# slot-lag sensitivity
for lp in [0.0,0.01,0.02,0.03]:
    v=[sim_one(r,cfg,lp)[0] for r in rows if paths.get(r["mint"],{}).get("pts")]
    print(f"lag_pen={lp:.2f}: sum={sum(v):7.3f} mean={sum(v)/len(v):.4f} win={sum(1 for x in v if x>0)/len(v):.3f}")
# per-position correlation
import statistics
pairs=[(r["realized"],sim_one(r,cfg,0.0)[0]) for r in rows if paths.get(r["mint"],{}).get("pts")]
h=[a for a,b in pairs]; s=[b for a,b in pairs]
mh=sum(h)/len(h); ms=sum(s)/len(s)
cov=sum((a-mh)*(b-ms) for a,b in pairs); sh=sum((a-mh)**2 for a in h)**.5; ss=sum((b-ms)**2 for b in s)**.5
print("per-position corr(his,sim)=",round(cov/((sum((a-mh)**2 for a in h)**.5)*(sum((b-ms)**2 for b in s)**.5)),3))
agree=sum(1 for a,b in pairs if (a>0)==(b>0))/len(pairs)
print("sign agreement his/sim:",round(agree,3))
print("\nExamples (his vs sim, lag0.02):")
ex=sorted(rows,key=lambda r:-r["realized"])
for r in ex[:4]+ex[-3:]:
    if not paths.get(r["mint"],{}).get("pts"): continue
    sp,legs=sim_one(r,cfg,0.02)
    mm=r["mint"][:8]; rz=r["realized"]; pk=r["peak_r"]
    print("  ",mm,"his%+.3f"%rz,"sim%+.3f"%sp,"peak_r",pk and round(pk,2),"legs",[(round(l[0],2),round(l[1],2),l[2]) for l in legs])

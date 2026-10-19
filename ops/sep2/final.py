import json
from collections import Counter
rows=json.load(open("/root/sep2/rows_enriched.json"))
WL=[r for r in rows if r["label"] in ("WIN","LOSE")]; WL.sort(key=lambda r:r["slot"])
def g(r,k,d=0):
    v=r.get(k); return d if v is None else v
def ev(keep,sub):
    kw=sum(1 for r in sub if keep(r) and r["label"]=="WIN"); kl=sum(1 for r in sub if keep(r) and r["label"]=="LOSE")
    rw=sum(1 for r in sub if not keep(r) and r["label"]=="WIN"); rl=sum(1 for r in sub if not keep(r) and r["label"]=="LOSE")
    W=kw+rw;L=kl+rl
    return kw,kl,rw,rl,(kw/(kw+kl) if kw+kl else float("nan")),(kw/W if W else 0),(rl/L if L else 0)
half=len(WL)//2; tr=WL[:half]; te=WL[half:]
print("=== THRESHOLD SENSITIVITY: slot01 total co-buy SOL (keep if >= thr) ===")
print("thr | full: kW kL rejL winP rec Lrem | TRAIN winP/rec/Lrem | TEST winP/rec/Lrem")
for thr in [0.5,1.0,1.5,2.0,2.5,3.0]:
    kf=lambda r,t=thr: g(r,"sol_cobuy_slot01")>=t
    a=ev(kf,WL); b=ev(kf,tr); c=ev(kf,te)
    print("%.1f | %d %d %d %.2f %.2f %.2f | %.2f/%.2f/%.2f | %.2f/%.2f/%.2f"%(thr,a[0],a[1],a[3],a[4],a[5],a[6],b[4],b[5],b[6],c[4],c[5],c[6]))
print("\n=== SLOT0-ONLY (strictly observable if you confirm after creation slot) ===")
for thr in [0.5,1.0,1.5,2.0,2.5]:
    kf=lambda r,t=thr: g(r,"sol_cobuy_slot0")>=t
    a=ev(kf,WL); b=ev(kf,tr); c=ev(kf,te)
    print("slot0 sol>=%.1f | full kW%d kL%d winP%.2f rec%.2f Lrem%.2f | TRAIN %.2f/%.2f/%.2f | TEST %.2f/%.2f/%.2f"%(thr,a[0],a[1],a[4],a[5],a[6],b[4],b[5],b[6],c[4],c[5],c[6]))
print("\n=== n_cobuy_slot0 count-only (observable, no SOL parse) ===")
for thr in [1,2,3,4]:
    kf=lambda r,t=thr: g(r,"n_cobuy_slot0")>=t
    a=ev(kf,WL); b=ev(kf,tr); c=ev(kf,te)
    print("n_cobuy0>=%d | full kW%d kL%d winP%.2f rec%.2f Lrem%.2f | TRAIN %.2f/%.2f/%.2f | TEST %.2f/%.2f/%.2f"%(thr,a[0],a[1],a[4],a[5],a[6],b[4],b[5],b[6],c[4],c[5],c[6]))
print("\n=== WINNERS SACRIFICED by sol_cobuy_slot01>=2.0 (false negatives) ===")
kf=lambda r: g(r,"sol_cobuy_slot01")>=2.0
fn=[(r["mint"][:8],round(r["peak"],2),round(r["floor"],3),round(g(r,"sol_cobuy_slot01"),2),r.get("n_cobuy_slot01"),r.get("uri_host")) for r in WL if not kf(r) and r["label"]=="WIN"]
for x in sorted(fn,key=lambda z:z[1]): print("  ",x)
print("peak_r of sacrificed winners:",sorted(x[1] for x in fn))
print("\n=== FULL POPULATION (incl 21 MID) applying sol_cobuy_slot01>=2.0 ===")
allk=[r for r in rows if g(r,"sol_cobuy_slot01")>=2.0]; allr=[r for r in rows if not (g(r,"sol_cobuy_slot01")>=2.0)]
print("KEEP:",Counter(r["label"] for r in allk)," REJECT:",Counter(r["label"] for r in allr))
print("\n=== LOSER PROFILE (all 19) ===")
L=[r for r in rows if r["label"]=="LOSE"]
import statistics as st
print("dev_share median=%.2f  sol_cobuy01 median=%.2f  n_cobuy01 median=%d"%(st.median(g(r,"dev_share_slot01",1) for r in L),st.median(g(r,"sol_cobuy_slot01") for r in L),st.median(g(r,"n_cobuy_slot01") for r in L)))
W=[r for r in rows if r["label"]=="WIN"]
print("WIN dev_share median=%.2f  sol_cobuy01 median=%.2f  n_cobuy01 median=%d"%(st.median(g(r,"dev_share_slot01",1) for r in W),st.median(g(r,"sol_cobuy_slot01") for r in W),st.median(g(r,"n_cobuy_slot01") for r in W)))
# serial rug cluster
print("\n=== md.sdfgsdfsdf.uk / creator bwamJz cluster ===")
cl=[r for r in rows if r.get("uri_host")=="md.sdfgsdfsdf.uk"]
print("host md.sdfgsdfsdf.uk:",Counter(r["label"] for r in cl)," creators:",Counter((r.get("creator") or "")[:6] for r in cl))
print("their sol_cobuy01:",sorted(round(g(r,"sol_cobuy_slot01"),2) for r in cl))

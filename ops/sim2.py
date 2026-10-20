import json, random, statistics as st
PATHS="/root/sniper-fast/paths.jsonl"
FEE=0.0125; FIXED=0.000365; CAP=3200.0; RCAP=20.0
kept=[]; raw=corrupt=misread=0
for line in open(PATHS):
    raw+=1
    try: d=json.loads(line)
    except: corrupt+=1; continue
    if not isinstance(d,dict): corrupt+=1; continue
    p=d.get("path"); pk=d.get("peak")
    if not isinstance(p,list) or not isinstance(pk,(int,float)) or len(p)<2: corrupt+=1; continue
    if not all(isinstance(pt,list) and len(pt)==2 and all(isinstance(x,(int,float)) for x in pt) for pt in p): corrupt+=1; continue
    r0=p[0][1]
    if r0>=2.0 or pk>=RCAP-1e-6: misread+=1; continue
    kept.append((float(pk),[(float(a),float(b)) for a,b in p]))
N=len(kept)
R2=[k for k in kept if k[0]>=2.0]; R3=[k for k in kept if k[0]>=3.0]
nr2=len(R2); nr3=len(R3)

def ride_exit(path,ride=1.3,trail=0.95):
    peak=1.0; riding=False; last=path[0][1]
    for ms,r in path:
        last=r
        if r>peak:peak=r
        if not riding and r>=ride:riding=True
        if (riding and r<=peak*trail) or ms>=CAP: return r
    return last
def r_at(path,t):
    for ms,r in path:
        if ms>=t: return r
    return None

def base_net(path,size=1.0):
    exr=ride_exit(path); gross=(size/1.0)*exr
    return gross*(1-FEE)-size-FEE*size-FIXED*2

def scout_net(path,scout,add_thr,add_t,add_sz,slot=250):
    tokens=scout/1.0; cost=scout; buyn=scout; legs=1; added=False
    rp=r_at(path,add_t); r_add=r_at(path,add_t+slot)
    peak=1.0; riding=False; last=path[0][1]; exr=None
    for ms,r in path:
        last=r
        if r>peak:peak=r
        if (not added) and ms>=add_t and rp is not None and rp>=add_thr and r_add is not None:
            tokens+=add_sz/r_add; cost+=add_sz; buyn+=add_sz; legs+=1; added=True
        if not riding and r>=ride_r:riding=True
        if (riding and r<=peak*0.95) or ms>=CAP: exr=r; break
    if exr is None: exr=last
    legs+=1
    return gross_calc(tokens,exr,cost,buyn,legs),added,cost
ride_r=1.3
def gross_calc(tokens,exr,cost,buyn,legs):
    return tokens*exr*(1-FEE)-cost-FEE*buyn-FIXED*legs

def stats(nets,cap_total,cap_t0_per,label,captured_r2=None,captured_r3=None):
    tot=sum(nets); n=len(nets); s=sorted(nets)
    nps_cap=tot/cap_total if cap_total else 0
    e10=(tot-sum(s[-max(1,n//10):]))/(n-max(1,n//10))  # ex top decile mean
    win=100*sum(1 for x in nets if x>0)/n
    print(f"{label:38} tot={tot:+8.2f} mean/l={tot/n:+.4f} med={s[n//2]:+.4f} win={win:4.1f}% "
          f"net/SOL={nps_cap:+.4f} exTopDecile_mean={e10:+.4f} totCap={cap_total:7.0f} capT0/l={cap_t0_per:.3f}"
          + (f" R2cap={captured_r2:.0f}% R3cap={captured_r3:.0f}%" if captured_r2 is not None else ""))
    return tot

print(f"CLEAN N={N} (raw={raw} corrupt={corrupt} misread={misread}) | runners>=2:{nr2}({100*nr2/N:.1f}%) >=3:{nr3}")
print()
# A: baseline full 1.0 on all
bnets=[base_net(p) for pk,p in kept]
stats(bnets,N*1.0,1.0,"A) FULL 1.0 on ALL (floor)",100.0,100.0)
# A-tiny: uniform tiny 0.2 on all (raise max-inflight, no add) -- the skeptic alternative
for sz in [0.1,0.2]:
    tn=[base_net(p,sz) for pk,p in kept]
    stats(tn,N*sz,sz,f"A') UNIFORM TINY {sz} on ALL (no add)",100.0,100.0)
print()
# B: scout-then-add best candidates
for (scout,thr,addt,addsz) in [(0.2,1.2,250,1.0),(0.2,1.2,400,1.0),(0.15,1.2,250,1.0),(0.1,1.2,250,1.0),(0.2,1.2,250,3.0)]:
    nets=[]; cap=0; r2c=0; r3c=0; added=0
    for pk,p in kept:
        net,ad,cost=scout_net(p,scout,thr,addt,addsz); nets.append(net); cap+=cost
        if ad: added+=1
        if pk>=2.0: r2c+=1  # scouted always -> captured
        if pk>=3.0: r3c+=1
    stats(nets,cap,scout,f"B) SCOUT{scout}+ADD{addsz}@thr{thr}/t{addt}",100.0,100.0)
print()
# C: blind subset -- full 1.0 on random X% to match scout t=0 capital (0.2 -> buy 20%)
random.seed(1)
for frac in [0.2,0.1]:
    runs=[]
    for _ in range(200):
        idx=[i for i in range(N) if random.random()<frac]
        nets=[base_net(kept[i][1]) for i in idx]
        tot=sum(nets)
        r2=sum(1 for i in idx if kept[i][0]>=2.0); r3=sum(1 for i in idx if kept[i][0]>=3.0)
        runs.append((tot,r2,r3,len(idx)))
    mt=st.mean(r[0] for r in runs); mr2=st.mean(r[1] for r in runs); mr3=st.mean(r[2] for r in runs); mn=st.mean(r[3] for r in runs)
    print(f"C) BLIND SUBSET full on {frac*100:.0f}% random  avg tot={mt:+8.2f} capT0/l(avg)={frac:.2f} totCap={mn:.0f} "
          f"R2captured={100*mr2/nr2:.0f}%({mr2:.0f}/{nr2}) R3captured={100*mr3/nr3:.0f}%({mr3:.0f}/{nr3})")

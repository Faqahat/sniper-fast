import json, math, statistics as st

PATHS="/root/gs_clean/paths.jsonl"
FEE0=0.0125; FIXED0=0.000365; CAP_MS=3200.0; RCAP=20.0; CAPFILL=1.12
LAG=250.0; WAIT=300.0  # +1 slot landing observed ~300ms; exit lag 250ms

# ---------- load & clean ----------
kept=[]
for ln in open(PATHS):
    try: d=json.loads(ln)
    except: continue
    if not isinstance(d,dict): continue
    p=d.get("path"); pk=d.get("peak")
    if not isinstance(p,list) or not isinstance(pk,(int,float)) or len(p)<2: continue
    if not all(isinstance(pt,list) and len(pt)==2 and all(isinstance(x,(int,float)) for x in pt) for pt in p): continue
    r0=p[0][1]
    if r0>=2.0 or r0>=RCAP-1e-6 or pk>=RCAP-1e-6: continue
    kept.append((float(d.get("dev",0.0)), float(pk), [(float(a),float(b)) for a,b in p]))
N=len(kept)
RUN2=[i for i,(dv,pk,p) in enumerate(kept) if pk>=2.0]
RUN3=[i for i,(dv,pk,p) in enumerate(kept) if pk>=3.0]

def r_at(path,t):
    last=path[0][1]
    for ms,r in path:
        if ms>=t: return r
        last=r
    return last
def last_within(path,cap):
    v=[r for ms,r in path if ms<=cap]
    return v[-1] if v else path[-1][1]

def trailed_exit_r(path, entry_r, ride=1.3, trail=0.95):
    """return exit_r applying one-slot (LAG) execution lag after trigger."""
    peak=entry_r; riding=False
    for ms,r in path:
        if ms>CAP_MS: break
        if r>peak: peak=r
        if not riding and r/entry_r>=ride: riding=True
        if riding and r<=peak*trail:
            return r_at(path, ms+LAG)   # sell lands +1 slot later
    return last_within(path,CAP_MS)     # no trigger -> exit at cap

def depth(r,dev): return 30.0*math.sqrt(max(r,1.0))+dev

def fill_net(entry_r, exit_r, dev, S, FEE, FIXED, impact):
    if impact:
        bs=S/depth(entry_r,dev); ss=S/depth(exit_r,dev)
    else:
        bs=ss=0.0
    p_b=entry_r*(1+bs); p_s=exit_r*(1-ss)
    return S*((p_s/p_b)*(1-FEE)**2 - 1.0) - 2*FIXED

def run(p_floor, S, impact, p_fail, cap_on, fee_mult=1.0, exit_lag=True):
    FEE=FEE0*fee_mult; FIXED=FIXED0*fee_mult
    global LAG
    saveLAG=LAG
    if not exit_lag: LAG=0.0
    per_launch_ev=[]       # EV net per launch (for mean/med-of-EV/ex-decile/split-half)
    scen=[]                # (net, weight) weighted scenarios for win%/revert%/median
    revert_w=0.0; tot_w=0.0
    r2_cap=0.0; r3_cap=0.0
    for i,(dv,pk,path) in enumerate(kept):
        entryB=r_at(path,WAIT)
        ev=0.0
        # Branch A: floor, weight p_floor
        def add_fill(entry_r, w):
            nonlocal ev
            ex_tr=trailed_exit_r(path,entry_r)
            ex_dl=last_within(path,CAP_MS)
            n_tr=fill_net(entry_r,ex_tr,dv,S,FEE,FIXED,impact)
            n_dl=fill_net(entry_r,ex_dl,dv,S,FEE,FIXED,impact)
            ev+=w*((1-p_fail)*n_tr + p_fail*n_dl)
            scen.append((n_tr, w*(1-p_fail))); scen.append((n_dl, w*p_fail))
        # floor branch
        wF=p_floor
        if wF>0: add_fill(1.0, wF)
        # +1 branch
        wP=1-p_floor
        if wP>0:
            if cap_on and entryB>CAPFILL:
                nr=-FIXED
                ev+=wP*nr; scen.append((nr,wP)); revert_w+=wP
            else:
                add_fill(entryB, wP)
        tot_w+=1.0
        per_launch_ev.append(ev)
        # runner capture prob
        capprob = p_floor + (1-p_floor)*(0.0 if (cap_on and entryB>CAPFILL) else 1.0)
        if pk>=2.0: r2_cap+=capprob
        if pk>=3.0: r3_cap+=capprob
    if not exit_lag: LAG=saveLAG
    # aggregate
    tot_ev=sum(per_launch_ev)
    mean_l=tot_ev/N
    nps=tot_ev/(N*S)
    # weighted median & win over scenarios
    scen.sort(key=lambda x:x[0]); W=sum(w for _,w in scen)
    c=0.0; med=scen[-1][0]
    for v,w in scen:
        c+=w
        if c>=W/2: med=v; break
    win=100*sum(w for v,w in scen if v>0)/W
    revpct=100*revert_w/N  # expected reverts per launch (weight sums to (1-p_floor)*frac over cap)
    # ex-top-decile mean on per-launch EV
    s=sorted(per_launch_ev); k=max(1,N//10)
    exdec=sum(s[:N-k])/(N-k)
    # split-half (even/odd)
    ev_e=[per_launch_ev[i] for i in range(0,N,2)]; ev_o=[per_launch_ev[i] for i in range(1,N,2)]
    sh=(sum(ev_e)/len(ev_e), sum(ev_o)/len(ev_o))
    r2c=100*r2_cap/len(RUN2); r3c=100*r3_cap/len(RUN3)
    return dict(mean=mean_l,med=med,nps=nps,win=win,revpct=revpct,exdec=exdec,
                tot=tot_ev,r2cap=r2c,r3cap=r3c,sh=sh)

if __name__=="__main__":
    print(f"CLEAN N={N}  runners peak>=2: {len(RUN2)} ({100*len(RUN2)/N:.1f}%)  peak>=3: {len(RUN3)} ({100*len(RUN3)/N:.2f}%)")
    def show(label,cfg):
        r=run(**cfg)
        print(f"\n== {label} ==  "+" ".join(f"{k}={v}" for k,v in cfg.items()))
        print(f"  mean/launch={r['mean']:+.5f}  median={r['med']:+.5f}  net/SOL={r['nps']:+.5f}  win={r['win']:.1f}%  revert={r['revpct']:.1f}%")
        print(f"  runnersCap peak>=2:{r['r2cap']:.0f}%  peak>=3:{r['r3cap']:.0f}%  ex-top-decile mean={r['exdec']:+.5f}  split-half={r['sh'][0]:+.5f}/{r['sh'][1]:+.5f}")
        return r
    # PAPER anchor
    show("PAPER anchor (floor-always,no cap,no impact,no fail,no lag)",
         dict(p_floor=1.0,S=1.0,impact=False,p_fail=0.0,cap_on=False,exit_lag=False))
    show("OPTIMISTIC", dict(p_floor=0.72,S=1.0,impact=False,p_fail=0.0,cap_on=False))
    show("REALISTIC",  dict(p_floor=0.50,S=0.1,impact=True,p_fail=0.03,cap_on=True))
    show("PESSIMISTIC",dict(p_floor=0.35,S=0.2,impact=True,p_fail=0.05,cap_on=True))
    show("WORST-CASE", dict(p_floor=0.20,S=0.5,impact=True,p_fail=0.05,cap_on=True,fee_mult=1.25))

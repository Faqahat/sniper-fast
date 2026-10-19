import sys; sys.path.insert(0,"/root")
import math
from stress import run, N, RUN2, kept, r_at, trailed_exit_r, last_within, fill_net, FEE0, FIXED0, CAPFILL

# concentration of EV net across launches at REALISTIC and PAPER-ish
def per_launch(p_floor,S,impact,p_fail,cap_on,fee=1.0):
    FEE=FEE0*fee; FIXED=FIXED0*fee; out=[]
    for dv,pk,path in kept:
        eb=r_at(path,300.0); ev=0.0
        def fill(er,w):
            nonlocal ev
            tr=trailed_exit_r(path,er); dl=last_within(path,3200.0)
            ntr=fill_net(er,tr,dv,S,FEE,FIXED,impact); ndl=fill_net(er,dl,dv,S,FEE,FIXED,impact)
            ev+=w*((1-p_fail)*ntr+p_fail*ndl)
        if p_floor>0: fill(1.0,p_floor)
        wP=1-p_floor
        if wP>0:
            if cap_on and eb>CAPFILL: ev+=wP*(-FIXED)
            else: fill(eb,wP)
        out.append(ev)
    return out

for lbl,cfg in [("PAPER",dict(p_floor=1.0,S=1.0,impact=False,p_fail=0.0,cap_on=False)),
                ("REALISTIC",dict(p_floor=0.5,S=0.1,impact=True,p_fail=0.03,cap_on=True))]:
    v=sorted(per_launch(**cfg),reverse=True); tot=sum(v)
    print(f"{lbl}: total EV net={tot:+.4f}")
    for k in [1,5,10,20,50,237]:
        print(f"   top {k:>3} launches = {sum(v[:k]):+.4f}  ({100*sum(v[:k])/tot:5.1f}% of total)")
    print(f"   positive launches: {sum(1 for x in v if x>0)} / {N}")

# Selection ceiling: model on hindsight-selected subsets at high landing (p_floor=0.8)
print("\nSELECTION CEILING (p_floor=0.8, size 0.1, impact+fail+cap on) mean/TRADE on subsets:")
def subset_mean(idxs,p_floor,S):
    FEE=FEE0;FIXED=FIXED0;tot=0
    for i in idxs:
        dv,pk,path=kept[i]; eb=r_at(path,300.0); ev=0.0
        def fill(er,w):
            nonlocal ev
            tr=trailed_exit_r(path,er);dl=last_within(path,3200.0)
            ev+=w*(0.97*fill_net(er,tr,dv,S,FEE,FIXED,True)+0.03*fill_net(er,dl,dv,S,FEE,FIXED,True))
        fill(1.0,p_floor); wP=1-p_floor
        if eb>CAPFILL: ev+=wP*(-FIXED)
        else: fill(eb,wP)
        tot+=ev
    return tot/len(idxs)
allidx=list(range(N))
print(f"   buy-ALL         n={N}: {subset_mean(allidx,0.8,0.1):+.5f}/trade")
print(f"   peak>=2 only    n={len(RUN2)}: {subset_mean(RUN2,0.8,0.1):+.5f}/trade (perfect-hindsight ceiling)")
# early-momentum proxy gate: r at 300ms >= 1.05 (shows demand) -- but this moves entry; keep floor-entry assumption
gate=[i for i,(dv,pk,p) in enumerate(kept) if r_at(p,300.0)>=1.05 and dv<=8]
gr2=sum(1 for i in gate if kept[i][1]>=2.0)
print(f"   early-demand proxy (r@300>=1.05,dev<=8) n={len(gate)} ({100*len(gate)/N:.0f}% of launches, {gr2} runners): {subset_mean(gate,0.8,0.1):+.5f}/trade")

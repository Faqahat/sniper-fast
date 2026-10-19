#!/usr/bin/env python3
"""Analyze create_cu>0 vs ==0 on disjoint window(s). Bootstrap 95% CIs on mean net-R, Wilson CI on win%.
Collinearity check: create_cu>0 vs dev_buy size."""
import json, sys, statistics as st, random, math

def wilson(k,n,z=1.96):
    if n==0: return (0,0)
    p=k/n; d=1+z*z/n
    c=(p+z*z/(2*n))/d; h=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/d
    return (c-h,c+h)

def summ(fs,label):
    nets=[f["net"] for f in fs]; n=len(nets)
    if n==0: return {"label":label,"n":0}
    win=sum(1 for x in nets if x>0)/n; mean=sum(nets)/n; tot=sum(nets); med=st.median(nets)
    random.seed(1); bs=sorted(sum(nets[random.randrange(n)] for _ in range(n))/n for _ in range(5000))
    lo=bs[int(.025*5000)]; hi=bs[int(.975*5000)]
    wk=sum(1 for x in nets if x>0); wlo,whi=wilson(wk,n)
    gwin=sum(1 for f in fs if f["gross"]>0)/n; gmean=sum(f["gross"] for f in fs)/n
    return {"label":label,"n":n,"win":win,"win_lo":wlo,"win_hi":whi,"mean":mean,"ci_lo":lo,"ci_hi":hi,
            "med":med,"tot":tot,"gwin":gwin,"gmean":gmean}

def line(S):
    if S["n"]==0: print(f"  {S['label']:22s} n=0"); return
    print(f"  {S['label']:22s} n={S['n']:4d}  win={S['win']*100:5.1f}% [{S['win_lo']*100:4.1f},{S['win_hi']*100:4.1f}]  "
          f"netR={S['mean']:+.4f} [95%CI {S['ci_lo']:+.3f},{S['ci_hi']:+.3f}]  med={S['med']:+.4f}  totR={S['tot']:+6.2f}  "
          f"grossWin={S['gwin']*100:4.1f}%")

def report(F,title):
    print(f"\n===== {title} (n={len(F)}) =====")
    pos=[f for f in F if f["create_cu"]>0]; zer=[f for f in F if f["create_cu"]==0]
    frac=len(pos)/len(F) if F else 0
    print(f"  fraction create_cu>0 = {frac*100:.1f}%  ({len(pos)}/{len(F)})")
    Sp=summ(pos,"create_cu>0"); Sz=summ(zer,"create_cu==0")
    line(Sp); line(Sz)
    # collinearity: dev_buy size by bucket
    def devstats(fs):
        dv=sorted(f["dev_buy"] for f in fs); wv=sorted(f["dev_buy_wire"] for f in fs)
        if not dv: return None
        return (st.median(dv), st.mean(dv), st.median(wv), st.mean(wv))
    dp=devstats(pos); dz=devstats(zer)
    print("  -- collinearity: dev_buy (curve SOL) & dev_buy_wire by create_cu bucket --")
    if dp: print(f"     create_cu>0 : dev_buy med={dp[0]:.3f} mean={dp[1]:.3f} | wire med={dp[2]:.3f} mean={dp[3]:.3f}")
    if dz: print(f"     create_cu==0: dev_buy med={dz[0]:.3f} mean={dz[1]:.3f} | wire med={dz[2]:.3f} mean={dz[3]:.3f}")
    # within large-dev subset, does create_cu still separate?
    med_dev=st.median([f["dev_buy"] for f in F])
    big=[f for f in F if f["dev_buy"]>=med_dev]; small=[f for f in F if f["dev_buy"]<med_dev]
    print(f"  -- create_cu effect CONTROLLING for dev_buy (split at median dev_buy={med_dev:.3f} SOL) --")
    for sub,nm in [(big,"BIG dev"),(small,"SMALL dev")]:
        sp=[f for f in sub if f["create_cu"]>0]; sz=[f for f in sub if f["create_cu"]==0]
        a=summ(sp,f"{nm}/cu>0"); b=summ(sz,f"{nm}/cu==0"); line(a); line(b)
    return {"frac":frac,"pos":Sp,"zer":Sz}

if __name__=="__main__":
    files=sys.argv[1:] or ["/root/create_cu_reval/paper_feat.json"]
    allF=[]
    res={}
    for fp in files:
        F=json.load(open(fp))
        allF+=F
        res[fp]=report(F, fp.split("/")[-1])
    if len(files)>1:
        res["COMBINED"]=report(allF,"COMBINED DISJOINT")
    json.dump(res,open("/root/create_cu_reval/analysis.json","w"),indent=2,default=str)
    print("\nwrote analysis.json")

#!/usr/bin/env python3
"""Fix his_500 econ (create-tx floor), compute his variance/drawdown, emit corrected
Step 1 + clean verdict numbers. Merge into analysis.json."""
import sys, json, statistics as st
sys.path.insert(0,"/root/econ_102"); import econ102 as E
F=json.load(open("/root/last500/feat_500.json"))
OUT=json.load(open("/root/last500/analysis.json"))
def mean(xs): return sum(xs)/len(xs) if xs else float('nan')
def winr(xs): return sum(1 for x in xs if x>0)/len(xs) if xs else float('nan')
def mdd(seq):
    peak=cum=m=0.0
    for x in seq:
        cum+=x; peak=max(peak,cum); m=min(m,cum-peak)
    return m
his=[]
for r in F:
    if not r.get("create_found"): continue
    ser=r.get("series"); floor=r.get("entry_px")
    rr=dict(r); rr.pop("series",None)
    if ser and floor and floor>0:
        s=[(a,c) for (a,b,c) in ser]; entry=floor*E.ENTRY_MULT
        net,_,_=E.simulate(entry,r["create_slot"],s,E.SHIP,0.5)
        g=E.gross_only(entry,r["create_slot"],s,E.SHIP)
        rr["net_R"],rr["gross_R"]=net,g
    else:
        rr["net_R"],rr["gross_R"]=None,None
    his.append(rr)
json.dump(his,open("/root/last500/his_500.json","w"),default=str)
wo=sorted([r for r in his if r["net_R"] is not None],key=lambda r:r["create_slot"])
nets=[r["net_R"] for r in wo]
print(f"HIS LAST-500 (create-tx floor, our ladder, 0.5SOL): n={len(nets)} mean={mean(nets):+.4f} win={100*winr(nets):.0f}% "
      f"sd={st.pstdev(nets):.3f} totR={sum(nets):+.1f} mDD={mdd(nets):+.2f}")
OUT["step1"]["net_mean_fixed"]=mean(nets); OUT["step1"]["win_fixed"]=winr(nets)
OUT["step1"]["sd"]=st.pstdev(nets); OUT["step1"]["totR"]=sum(nets); OUT["step1"]["mdd"]=mdd(nets); OUT["step1"]["n_out"]=len(nets)
# his dev distribution for verdict
import statistics
devs=sorted(r["dev_buy"] for r in his if r.get("dev_buy") is not None)
def q(p): return devs[min(len(devs)-1,int(p*(len(devs)-1)))]
OUT["step1"]["dev_p25"],OUT["step1"]["dev_med"],OUT["step1"]["dev_p75"]=q(.25),q(.5),q(.75)
print(f"his dev_buy p25/med/p75 = {q(.25):.2f}/{q(.5):.2f}/{q(.75):.2f}  -> he attempts plenty of LOW-dev launches")
# fraction of his attempts a dev>=X rule would KEEP (recall on his own landed set)
for thr in [0.5,1,2,3,5]:
    k=sum(1 for d in devs if d>=thr); print(f"  his landed with dev>={thr}: {100*k/len(devs):.0f}%")
json.dump(OUT,open("/root/last500/analysis.json","w"),indent=2,default=str)
print("merged -> analysis.json")

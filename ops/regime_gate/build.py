#!/usr/bin/env python3
import json,sys,statistics as st
sys.path.insert(0,"/root/econ_102")
import econ102 as E
SIZE=0.5
SOURCES=[("backtest","/root/profit_backtest/trajectories.json"),
         ("paper","/root/profit_ourfill/paper_traj.json"),
         ("fresh","/root/create_cu_reval/fresh_traj.json")]
rows=[]; seen=set()
for name,path in SOURCES:
    for t in json.load(open(path)):
        m=t.get("mint")
        if not t.get("entry_px"): continue
        if m in seen: continue
        seen.add(m)
        cs=t["create_slot"]; entry=t["entry_px"]*E.ENTRY_MULT
        series=[(s,p) for s,p in (t.get("series") or [])]
        net,gross,legs=E.simulate(entry,cs,series,E.SHIP,SIZE)
        peak12=1.0; peakall=1.0
        for s,p in series:
            r=p/entry
            if r>peakall: peakall=r
            if s-cs<=12 and r>peak12: peak12=r
        rows.append({"mint":m,"slot":cs,"window":name,"entry":entry,
                     "net":net,"gross":gross,"peak12":peak12,"peakall":peakall,
                     "nseries":len(series)})
rows.sort(key=lambda r:r["slot"])
json.dump(rows,open("/root/regime_gate/timeline.json","w"))
print("total launches",len(rows))
for name,_ in SOURCES:
    sub=[r for r in rows if r["window"]==name]
    nets=[r["net"] for r in sub]
    pr12=sum(1 for r in sub if r["peak12"]>=1.2)/len(sub)
    pr14=sum(1 for r in sub if r["peak12"]>=1.4)/len(sub)
    win=sum(1 for n in nets if n>0)/len(nets)
    empty=sum(1 for r in sub if r["nseries"]==0)
    print("%-9s n=%4d meanNet=%+.4f totNet=%+.3f win%%=%4.1f pump1.2=%4.1f%% pump1.4=%4.1f%% empty=%d"%(
        name,len(sub),st.mean(nets),sum(nets),win*100,pr12*100,pr14*100,empty))
nets=[r["net"] for r in rows]
print("OVERALL   n=%d meanNet=%+.4f totNet=%+.3f win%%=%.1f"%(
    len(rows),st.mean(nets),sum(nets),sum(1 for n in nets if n>0)/len(nets)*100))

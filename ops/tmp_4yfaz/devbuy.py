import json, statistics as st
t=json.load(open("/root/mirror/his_tape.json"))
recs=[(r["dev_buy_sol"], r["realized_sol"]) for r in t if r.get("dev_buy_sol") is not None and r.get("realized_sol") is not None]
n=len(recs)
devs=sorted(d for d,_ in recs)
def q(v,p): i=p*(len(v)-1); lo=int(i); hi=min(lo+1,len(v)-1); return v[lo]+(v[hi]-v[lo])*(i-lo)
print("N with dev_buy & pnl = %d (of %d)"%(n,len(t)))
print()
print("1. DEV-BUY (SOL): median=%.3f p10=%.3f p25=%.3f p50=%.3f p75=%.3f p90=%.3f min=%.3f max=%.3f"%(
    st.median(devs),q(devs,.1),q(devs,.25),q(devs,.5),q(devs,.75),q(devs,.9),devs[0],devs[-1]))
print()
buckets=[("<1",0,1),("1-2",1,2),("2-3",2,3),("3-5",3,5),("5-8",5,8),("8-12",8,12),(">12",12,1e9)]
print("2/3. BUCKET  count  %%trades  meanPnL  winrate  totalPnL")
for lbl,lo,hi in buckets:
    b=[(d,p) for d,p in recs if lo<=d<hi]
    if not b: 
        print("  %-6s  %3d   %5.1f%%   --"%(lbl,0,0)); continue
    pn=len(b); pnls=[p for _,p in b]; w=sum(1 for p in pnls if p>0)
    print("  %-6s  %3d   %5.1f%%   %+.4f   %4.1f%%   %+.3f"%(lbl,pn,100*pn/n,st.mean(pnls),100*w/pn,sum(pnls)))
print()
# min dev he touches
print("2. Smallest dev-buys he touched:", [round(x,3) for x in devs[:8]])
print("   trades with dev<1 SOL: %d (%.1f%%); dev<0.5: %d; dev<0.2: %d"%(
    sum(1 for d in devs if d<1),100*sum(1 for d in devs if d<1)/n,sum(1 for d in devs if d<0.5),sum(1 for d in devs if d<0.2)))
print()
# 4. correlation
import math
xs=[d for d,_ in recs]; ys=[p for _,p in recs]
mx=st.mean(xs); my=st.mean(ys)
cov=sum((x-mx)*(y-my) for x,y in recs)/n
sx=st.pstdev(xs); sy=st.pstdev(ys)
pear=cov/(sx*sy)
# spearman (rank)
rx={v:i for i,v in enumerate(sorted(range(n),key=lambda i:xs[i]))}
ry={v:i for i,v in enumerate(sorted(range(n),key=lambda i:ys[i]))}
dsq=sum((rx[i]-ry[i])**2 for i in range(n))
spear=1-6*dsq/(n*(n*n-1))
print("4. CORRELATION dev-buy vs pnl: Pearson=%.3f  Spearman=%.3f"%(pear,spear))
# profit concentration: where does total +38 come from
print()
big=[(d,p) for d,p in recs if d>=8]; mid=[(d,p) for d,p in recs if 2<=d<8]; sm=[(d,p) for d,p in recs if d<2]
for lbl,g in [("dev>=8",big),("dev2-8",mid),("dev<2",sm)]:
    if g: print("   %s: n=%d  totalPnL=%+.3f (%.0f%% of total)  mean=%+.4f"%(lbl,len(g),sum(p for _,p in g),100*sum(p for _,p in g)/sum(ys),st.mean([p for _,p in g])))

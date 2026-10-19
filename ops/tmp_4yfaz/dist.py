import json, statistics as st
t=json.load(open("/root/mirror/his_tape.json"))
# all 200 fully closed (sold>=95%); confirm & build pnl list
closed=[r for r in t if r.get("sells") and sum(s.get("frac",0) for s in r["sells"])>=0.95]
openp=[r for r in t if r not in closed]
pnl=sorted(r["realized_sol"] for r in closed)
n=len(pnl)
def q(p): 
    i=p*(n-1); lo=int(i); hi=min(lo+1,n-1); return pnl[lo]+(pnl[hi]-pnl[lo])*(i-lo)
tot=sum(pnl); mean=tot/n
wins=sum(1 for x in pnl if x>0)
print("N closed=%d  open=%d"%(n,len(openp)))
# timespan via create_slot range (slots ~0.4s). min/max slot
cs=[r["create_slot"] for r in closed if r.get("create_slot")]
print("create_slot range: %d .. %d (%d slots ~%.1f hrs)"%(min(cs),max(cs),max(cs)-min(cs),(max(cs)-min(cs))*0.4/3600))
print()
print("TOTAL realized P&L = %.3f SOL   MEAN/trade = %.4f SOL"%(tot,mean))
print("WIN RATE = %.1f%% (%d/%d)   median P&L = %.4f SOL"%(100*wins/n,wins,n,st.median(pnl)))
print()
print("DISTRIBUTION (SOL): p10=%.4f p25=%.4f p50=%.4f p75=%.4f p90=%.4f p99=%.4f"%(q(.10),q(.25),q(.50),q(.75),q(.90),q(.99)))
print("  worst=%.4f  best=%.4f"%(pnl[0],pnl[-1]))
print()
# fat tail
top5n=max(1,round(0.05*n))
top5=sorted(pnl,reverse=True)[:top5n]
pos_total=sum(x for x in pnl if x>0)
print("FAT TAIL: top 5%% = top %d trades, their profit=%.3f SOL = %.1f%% of TOTAL pnl, %.1f%% of GROSS wins"%(
    top5n,sum(top5),100*sum(top5)/tot,100*sum(top5)/pos_total))
ex2=sorted(pnl,reverse=True)[2:]
print("  ex-top2: mean/trade=%.4f SOL over %d trades (total %.3f); total-of-top2=%.3f"%(st.mean(ex2),len(ex2),sum(ex2),tot-sum(ex2)))
# how much if remove all losers? just context
print()
# hold time: dslot of last sell (full exit)
holds=[]
for r in closed:
    ds=[s.get("dslot") for s in r["sells"] if s.get("dslot") is not None]
    if ds: holds.append(max(ds))
holds.sort()
if holds:
    print("HOLD TIME (slots buy->full exit): median=%d p25=%d p75=%d p90=%d min=%d max=%d  (~0.4s/slot -> median %.1fs)"%(
        st.median(holds),holds[int(.25*len(holds))],holds[int(.75*len(holds))],holds[int(.9*len(holds))],holds[0],holds[-1],st.median(holds)*0.4))

import json, statistics as st, datetime as dt
def floor_task(dev_sol): dl=dev_sol*1e9; return (30e9+dl)**2/(30e9*1.073e15)
def q(v,p):
    v=sorted(v); i=p*(len(v)-1); lo=int(i); hi=min(lo+1,len(v)-1); return v[lo]+(v[hi]-v[lo])*(i-lo)
def rep(name, recs):
    n=len(recs); fills=[x[0] for x in recs]; deltas=[x[1] for x in recs]
    bt=[x[2] for x in recs if x[2]]
    print("=== %s  N=%d ==="%(name,n))
    if bt:
        a=dt.datetime.utcfromtimestamp(min(bt)).strftime("%Y-%m-%d")
        b=dt.datetime.utcfromtimestamp(max(bt)).strftime("%Y-%m-%d")
        print("timespan: %s .. %s (%.1f days)"%(a,b,(max(bt)-min(bt))/86400))
    sf=sorted(fills)
    print("FILL median=%.3f p25=%.3f p75=%.3f min=%.3f max=%.3f"%(st.median(sf),q(sf,.25),q(sf,.75),sf[0],sf[-1]))
    for thr in (1.02,1.05,1.10): print("   <=%.2fx: %.1f%%"%(thr,100*sum(1 for f in sf if f<=thr)/n))
    print("   >1.25x: %.1f%%"%(100*sum(1 for f in sf if f>1.25)/n))
    d0=sum(1 for x in deltas if x==0);d1=sum(1 for x in deltas if x==1);d2=sum(1 for x in deltas if x>=2)
    print("DELTA same-slot(0)=%.1f%%  +1=%.1f%%  +2more=%.1f%%"%(100*d0/n,100*d1/n,100*d2/n))
    for dd,lbl in [(0,"delta0"),(1,"delta1")]:
        fb=[x[0] for x in recs if x[1]==dd]
        if fb: print("   %s: n=%d medfill=%.3f  <=1.05x=%.0f%%  <=1.10x=%.0f%%"%(lbl,len(fb),st.median(fb),100*sum(1 for f in fb if f<=1.05)/len(fb),100*sum(1 for f in fb if f<=1.10)/len(fb)))
    print()

t=json.load(open("/root/mirror/his_tape.json"))
recs=[]
for r in t:
    dev=r.get("dev_buy_sol"); fp=r.get("his_fill_px"); dl=r.get("delta")
    if dev and fp and dl is not None and dev>0:
        recs.append((fp/floor_task(dev), dl, None))
rep("his_tape.json (fill_px / task-floor)", recs)

d=json.load(open("/root/last500/his_500.json"))
recs=[]
for r in d:
    dev=r.get("dev_buy"); ep=r.get("entry_px"); dl=r.get("buy_delta")
    if r.get("create_found") and dev and ep and dl is not None and dev>0:
        recs.append((ep*1e3/floor_task(dev), dl, r.get("blockTime")))
rep("his_500.json (entry_px*1e3 / task-floor)", recs)

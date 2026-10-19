import json,sys,statistics as st; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx
res=json.load(open("/root/tmp_filter/our_outcomes.json"))
def page_to_oldest(mint,maxpages=4):
    out=[];before=None
    for _ in range(maxpages):
        b=sigs(mint,1000,before=before)
        if not b: break
        out+=b
        if len(b)<1000: break
        before=b[-1]["signature"]
    return out[::-1]
for r in res:
    mint=r["mint"]; ss=page_to_oldest(mint)
    if not ss: r["peak_r25"]=None; continue
    cslot=ss[0]["slot"]
    t0=tx(ss[0]["signature"]); curve=None
    if t0:
        tbs=t0["meta"].get("postTokenBalances") or []
        if tbs: curve=max(tbs,key=lambda b:b["uiTokenAmount"]["uiAmount"] or 0).get("owner")
    win=[s for s in ss if s["slot"]-cslot<=25][:45]
    sols=[]
    for s in win:
        t=tx(s["signature"])
        if not t: continue
        keys=[k["pubkey"] for k in t["transaction"]["message"]["accountKeys"]]
        if curve in keys:
            sols.append(t["meta"]["postBalances"][keys.index(curve)]/1e9)
    if len(sols)<2: r["peak_r25"]=None; continue
    base=min(sols); entry=sols[0]-base; peak=max(sols)-base
    r["peak_r25"]=round(((30+peak)/(30+entry))**2,3)
    sys.stdout.write("%-44s n03=%-3s peakSOL=%.2f peak_r25=%.2f [%s]\n"%(mint[:44],str(r.get("n03")),peak,r["peak_r25"],r.get("state"))); sys.stdout.flush()
json.dump(res,open("/root/tmp_filter/our_outcomes.json","w"))
prs=[r["peak_r25"] for r in res if r.get("peak_r25")]
sys.stdout.write("\nOUR peak_r25 n=%d runner>=1.5=%d(%.0f%%) dump<1.1=%d(%.0f%%) med=%.2f\n"%(
    len(prs),sum(x>=1.5 for x in prs),100*sum(x>=1.5 for x in prs)/len(prs),
    sum(x<1.1 for x in prs),100*sum(x<1.1 for x in prs)/len(prs),st.median(prs))); sys.stdout.flush()

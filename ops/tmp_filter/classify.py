import sys,json,statistics as st; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx,parse_curve
res=json.load(open("/root/tmp_filter/our_outcomes.json"))
def oldest(mint):
    out=[]; before=None
    while True:
        b=sigs(mint,1000,before=before)
        if not b: break
        out+=b
        if len(b)<1000: break
        before=b[-1]["signature"]
        if len(out)>2000: break
    return out
for r in res:
    mint=r["mint"]; alls=oldest(mint); r["ntx"]=len(alls)
    # find curve from create tx accounts, read CURRENT state
    curve=None
    if alls:
        t=tx(alls[-1]["signature"])
        if t:
            # curve = owner of biggest token bal in create tx
            tbs=t["meta"].get("postTokenBalances") or []
            if tbs:
                big=max(tbs,key=lambda b:b["uiTokenAmount"]["uiAmount"] or 0)
                curve=big.get("owner")
    cv=parse_curve(curve) if curve else None
    if cv is None:
        r["state"]="GRADUATED/closed" if r["ntx"]>100 else "dead(closed)"
        r["real_sol_now"]=None; r["complete_now"]=None
    else:
        r["real_sol_now"]=round(cv["real_sol"],3); r["complete_now"]=cv["complete"]
        if cv["complete"]: r["state"]="GRADUATED"
        elif cv["real_sol"]>=5: r["state"]="alive-high"
        elif r["ntx"]<=15: r["state"]="DEAD"
        elif cv["real_sol"]<=0.1: r["state"]="dumped-to-floor"
        else: r["state"]="alive-low"
    print("%-44s dev=%-4s ntx=%-4d n03=%-3d real_sol=%s complete=%s -> %s"%(
        mint[:44],str(r.get("dev_buy")),r["ntx"],r.get("n03"),r.get("real_sol_now"),r.get("complete_now"),r["state"]))
json.dump(res,open("/root/tmp_filter/our_outcomes.json","w"))
print()
from collections import Counter
print(Counter(r["state"] for r in res))

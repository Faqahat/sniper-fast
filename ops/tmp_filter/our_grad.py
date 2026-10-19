import sys,json; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx,parse_curve,acct,PUMP
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
    mint=r["mint"]
    ss=sigs(mint,1)  # newest
    alls=oldest(mint); 
    r["ntx"]=len(alls)
    create=alls[-1]["signature"] if alls else None
    t=tx(create) if create else None
    curve=None
    if t:
        for k in t["transaction"]["message"]["accountKeys"]:
            pk=k.get("pubkey")
            if not pk or pk==mint: continue
            cv=parse_curve(pk)
            if cv and cv.get("supply",0)>0 and cv.get("virt_tok",0)>0:
                curve=pk; r["curve"]=pk; r["real_sol_create"]=round(cv["real_sol"],4); break
    # now read CURRENT state of that curve
    cvnow=parse_curve(curve) if curve else None
    if cvnow:
        r["complete_now"]=cvnow["complete"]; r["real_sol_now"]=round(cvnow["real_sol"],3)
    else:
        r["complete_now"]=None; r["real_sol_now"]=None
    print("%-44s dev=%-4s ntx=%-4d n03=%-3d real_sol_now=%s complete=%s"%(
        mint[:44],str(r.get("dev_buy")),r["ntx"],r.get("n03"),r.get("real_sol_now"),r.get("complete_now")))
json.dump(res,open("/root/tmp_filter/our_outcomes.json","w"))

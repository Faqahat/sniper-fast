import sys,json; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx,parse_curve,acct
res=json.load(open("/root/tmp_filter/our_outcomes.json"))
def first_sig(mint):
    out=[]; before=None
    while True:
        b=sigs(mint,1000,before=before)
        if not b: break
        out+=b
        if len(b)<1000: break
        before=b[-1]["signature"]
        if len(out)>2000: break
    return out[::-1]
for r in res:
    mint=r["mint"]; ss=first_sig(mint)
    r["ntx"]=len(ss)
    if not ss: r["real_sol"]=None; continue
    # find curve from create tx: owner of the largest token balance
    t=tx(ss[0]["signature"])
    curve=None
    if t:
        tbs=(t["meta"].get("postTokenBalances") or [])
        if tbs:
            big=max(tbs,key=lambda b:b["uiTokenAmount"]["uiAmount"] or 0)
            curve=big.get("owner")
    cv=parse_curve(curve) if curve else None
    if cv:
        r["real_sol"]=round(cv["real_sol"],3); r["complete"]=cv["complete"]; r["curve_closed"]=False
    else:
        # account closed => graduated (if lots of tx) ; recheck acct existence
        a=acct(curve) if curve else None
        r["real_sol"]=None; r["complete"]=None; r["curve_closed"]=(a is None or not a.get("value"))
    print("%-44s dev=%s ntx=%-4d n03=%-3d real_sol=%s complete=%s closed=%s"%(
        mint[:44],r.get("dev_buy"),r["ntx"],r.get("n03"),r["real_sol"],r.get("complete"),r.get("curve_closed")))
json.dump(res,open("/root/tmp_filter/our_outcomes.json","w"))

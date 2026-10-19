import sys,json; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx
res=json.load(open("/root/tmp_filter/our_outcomes.json"))
def all_sigs(mint):
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
    mint=r["mint"]; ss=all_sigs(mint)
    if not ss: r["peak_r"]=None; continue
    cslot=ss[0]["slot"]
    prices=[]
    for s in ss[:150]:
        t=tx(s["signature"])
        if not t: continue
        meta=t["meta"]; msg=t["transaction"]["message"]
        keys=[k["pubkey"] for k in msg["accountKeys"]]
        pre=meta["preBalances"]; post=meta["postBalances"]
        preT={b["accountIndex"]:(b["uiTokenAmount"]["uiAmount"] or 0) for b in (meta.get("preTokenBalances") or [])}
        postT={b["accountIndex"]:(b["uiTokenAmount"]["uiAmount"] or 0) for b in (meta.get("postTokenBalances") or [])}
        # find account with largest |token delta| that is a trader (has owner, not curve-side big holder)
        best=None;bestd=0
        idxs=set(preT)|set(postT)
        for i in idxs:
            d=postT.get(i,0)-preT.get(i,0)
            if abs(d)>abs(bestd): bestd=d; best=i
        if best is None or bestd==0: continue
        # price from SOL side: use signer(0) lamport delta magnitude vs token delta
        soldelta=abs(post[0]-pre[0])/1e9
        if soldelta<1e-6: continue
        px=soldelta/abs(bestd)
        prices.append((s["slot"],px))
    if not prices: r["peak_r"]=None; continue
    early=[p for sl,p in prices if sl-cslot<=1]
    entry=min(early) if early else prices[0][1]
    peak=max(p for _,p in prices)
    r["peak_r"]=peak/entry if entry>0 else None
    r["entry_px"]=entry; r["peak_px"]=peak
    print("%-44s ntx=%-4d n03=%-3d peak_r=%.2f"%(mint[:44],r["ntx"],r["n03"],r["peak_r"] or 0))
json.dump(res,open("/root/tmp_filter/our_outcomes.json","w"))

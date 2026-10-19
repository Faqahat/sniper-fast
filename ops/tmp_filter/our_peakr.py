import json,sys,statistics as st; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx
res=json.load(open("/root/tmp_filter/our_outcomes.json"))
def oldest(mint):
    out=[];before=None
    while True:
        b=sigs(mint,1000,before=before)
        if not b: break
        out+=b
        if len(b)<1000: break
        before=b[-1]["signature"]
        if len(out)>2000: break
    return out[::-1]
WIN=25
for r in res:
    mint=r["mint"]; ss=oldest(mint)
    if not ss: r["peak_r25"]=None; continue
    cslot=ss[0]["slot"]
    # curve PDA = owner of biggest token bal in create tx
    t0=tx(ss[0]["signature"]); curve=None
    if t0:
        tbs=t0["meta"].get("postTokenBalances") or []
        if tbs: curve=max(tbs,key=lambda b:b["uiTokenAmount"]["uiAmount"] or 0).get("owner")
    # walk txs in window, read curve lamports (real_sol)
    sols=[]
    for s in ss:
        if s["slot"]-cslot>WIN: break
        t=tx(s["signature"])
        if not t: continue
        keys=[k["pubkey"] for k in t["transaction"]["message"]["accountKeys"]]
        if curve in keys:
            idx=keys.index(curve)
            lam=t["meta"]["postBalances"][idx]/1e9
            sols.append((s["slot"],lam))
    if len(sols)<2: r["peak_r25"]=None; continue
    # rent baseline: min lamports ~ initial. real_sol = lam - rent. use first as entry
    base=min(l for _,l in sols)  # approx rent/initial
    entry=sols[0][1]-base
    peak=max(l for _,l in sols)-base
    # virt_sol = 30 + real_sol ; price ~ virt_sol^2
    pr=((30+peak)/(30+entry))**2 if (30+entry)>0 else None
    r["peak_r25"]=pr; r["peak_real_sol25"]=round(peak,3)
    print("%-44s dev=%-4s n03=%-3d peak_real_sol=%.2f peak_r25=%.2f  [%s]"%(
        mint[:44],str(r.get("dev_buy")),r.get("n03"),peak,pr,r.get("state")))
json.dump(res,open("/root/tmp_filter/our_outcomes.json","w"))
prs=[r["peak_r25"] for r in res if r.get("peak_r25")]
print()
print("OUR peak_r25: n=%d  runner(>=1.5)=%d(%.0f%%)  dump(<1.1)=%d(%.0f%%)  med=%.2f"%(
    len(prs),sum(1 for x in prs if x>=1.5),100*sum(1 for x in prs if x>=1.5)/len(prs),
    sum(1 for x in prs if x<1.1),100*sum(1 for x in prs if x<1.1)/len(prs),st.median(prs)))

import sys,json,time; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx,parse_curve
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
fills=json.load(open("/root/tmp_filter/our_fills.json"))
def all_sigs(mint):
    out=[]; before=None
    while True:
        b=sigs(mint,1000,before=before)
        if not b: break
        out+=b
        if len(b)<1000: break
        before=b[-1]["signature"]
        if len(out)>4000: break
    return out[::-1]  # oldest first
res=[]
for f in fills:
    mint=f["mint"]
    ss=all_sigs(mint)
    if not ss: 
        res.append({**f,"ntx":0}); continue
    cslot=ss[0]["slot"]; lastslot=ss[-1]["slot"]
    bt0=ss[0].get("blockTime") or 0; bt1=ss[-1].get("blockTime") or 0
    n03=sum(1 for s in ss if s["slot"]-cslot<=3)
    # peak price via executed price per tx; also final curve state
    peakpx=0.0; entry=None; curve_addr=None
    # limit tx parsing to first 120 txs for cost
    for s in ss[:120]:
        t=tx(s["signature"])
        if not t: continue
        meta=t["meta"]; msg=t["transaction"]["message"]
        keys=[k["pubkey"] for k in msg["accountKeys"]]
        # find curve: pump-owned account with token balance change
        tbs=(meta.get("postTokenBalances") or [])+(meta.get("preTokenBalances") or [])
        # identify curve as account owned by PUMP among keys
        # simpler: curve token balance = largest; use pre/post token for the curve ata
        # executed price = |curve lamport delta| / |curve token delta|
        # curve = account whose owner(program) is PUMP
        cidx=None
        for i,k in enumerate(msg["accountKeys"]):
            if k.get("owner")==PUMP: cidx=i; curve_addr=keys[i]
        if cidx is None: continue
        lam=(meta["postBalances"][cidx]-meta["preBalances"][cidx])/1e9
        # token delta of curve
        def tokbal(bals):
            for b in bals:
                if b["accountIndex"]==None: pass
            return None
        pre={b["accountIndex"]:b["uiTokenAmount"]["uiAmount"] for b in (meta.get("preTokenBalances") or [])}
        post={b["accountIndex"]:b["uiTokenAmount"]["uiAmount"] for b in (meta.get("postTokenBalances") or [])}
        # curve ATA index: token balance whose owner is curve_addr
        cta=None
        for b in (meta.get("postTokenBalances") or []):
            if b.get("owner")==curve_addr: cta=b["accountIndex"]
        if cta is None: continue
        dt=(post.get(cta,0) or 0)-(pre.get(cta,0) or 0)
        if abs(dt)<1: continue
        px=abs(lam)/abs(dt)  # SOL per token
        if px>peakpx: peakpx=px
    cv=parse_curve(curve_addr) if curve_addr else None
    real_sol=cv["real_sol"] if cv else None
    complete=cv["complete"] if cv else None
    res.append({**f,"ntx":len(ss),"cslot":cslot,"lifespan_slots":lastslot-cslot,
                "lifespan_s":bt1-bt0,"n03":n03,"peakpx":peakpx,"real_sol":real_sol,
                "complete":complete,"curve_closed":cv is None})
    print("%-44s ntx=%-3d n03=%-2d life_s=%-4d peakpx=%.2e real_sol=%s complete=%s closed=%s"%(
        mint[:44],len(ss),n03,bt1-bt0,peakpx,
        round(real_sol,3) if real_sol is not None else None,complete,cv is None))
json.dump(res,open("/root/tmp_filter/our_outcomes.json","w"))

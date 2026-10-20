import re,json,sys; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx,parse_curve
logs=["floor_test.log","floor112_test.log","floor_ride.log","floor_ride20.log","concurrent_live.log"]
rev=set(); filled=set()
for lg in logs:
    lines=open("/root/sniper-fast/"+lg,errors="replace").read().splitlines()
    cur=None
    for ln in lines:
        m=re.search(r"ROUND-TRIP \(LIVE\): mint=([1-9A-HJ-NP-Za-km-z]{32,44})",ln)
        if m: cur=m.group(1)
        mf=re.search(r"FIRE slot=\d+ mint=([1-9A-HJ-NP-Za-km-z]{32,44})",ln)
        if mf: cur=mf.group(1)
        if "ok=false" in ln and "BUY" in ln: pass
        if "FILL-CAP REVERT" in ln and cur: rev.add(cur)
        if "tokens received:" in ln and "(ATA" in ln and cur: filled.add(cur)
rev-=filled
print("reverted(missed) unique:",len(rev),"  filled unique:",len(filled))
def ntx_grad(mint):
    out=[];before=None
    while True:
        b=sigs(mint,1000,before=before)
        if not b: break
        out+=b
        if len(b)<1000: break
        before=b[-1]["signature"]
        if len(out)>2000: break
    n=len(out)
    curve=None
    if out:
        t=tx(out[-1]["signature"])
        if t:
            tbs=t["meta"].get("postTokenBalances") or []
            if tbs:
                big=max(tbs,key=lambda b:b["uiTokenAmount"]["uiAmount"] or 0); curve=big.get("owner")
    cv=parse_curve(curve) if curve else None
    if cv is None: state="GRAD/closed" if n>100 else "dead(closed)"
    elif cv["complete"]: state="GRADUATED"
    elif n<=15: state="DEAD"
    elif cv["real_sol"]<=0.1: state="dumped-floor"
    elif cv["real_sol"]>=5: state="alive-high"
    else: state="alive-low"
    return n,state
print("=== REVERTED (contested, we MISSED) ===")
from collections import Counter
c=Counter()
for mint in sorted(rev):
    n,s=ntx_grad(mint); c[s]+=1
    print("  %-44s ntx=%-4d %s"%(mint[:44],n,s))
print("REVERTED outcomes:",dict(c))
json.dump({"reverted":list(rev),"filled":list(filled)},open("/root/tmp_filter/rev_fill.json","w"))

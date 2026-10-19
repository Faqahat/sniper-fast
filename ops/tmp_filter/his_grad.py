import json,sys,random; sys.path.insert(0,"/root/tmp_filter")
from rpc import sigs,tx,parse_curve
d500=json.load(open("/root/last500/his_500.json"))
mints=[r["mint"] for r in d500]
random.seed(7); random.shuffle(mints); sample=mints[:70]
def classify(mint):
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
    if cv is None: s="GRAD/closed" if n>100 else "dead(closed)"
    elif cv["complete"]: s="GRADUATED"
    elif n<=15: s="DEAD"
    elif cv["real_sol"]<=0.1: s="dumped-floor"
    elif cv["real_sol"]>=5: s="alive-high"
    else: s="alive-low"
    return n,s
from collections import Counter
c=Counter()
for i,m in enumerate(sample):
    n,s=classify(m); c[s]+=1
print("HIS sample n=%d outcomes: %s"%(len(sample),dict(c)))
grad=c["GRAD/closed"]+c["GRADUATED"]
print("HIS graduation rate: %.1f%% (%d/%d)"%(100*grad/len(sample),grad,len(sample)))
print("HIS dead rate: %.1f%%"%(100*(c["DEAD"]+c["dead(closed)"])/len(sample)))
json.dump(dict(c),open("/root/tmp_filter/his_grad.json","w"))

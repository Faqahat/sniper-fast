#!/usr/bin/env python3
import json, sys
from collections import Counter
sys.path.insert(0,"/root/profit_backtest")
his=[r for r in json.load(open("/root/source/his_src.json")) if r.get("ok")]
pop=[r for r in json.load(open("/root/source/pop_src.json")) if r.get("ok")]
feath={r["mint"]:r for r in json.load(open("/root/last500/feat_500.json"))}
cren={c["mint"]:c for c in json.load(open("/root/profit_backtest/creates.json"))}
def enrich(rows,src):
    for r in rows:
        f=src.get(r["mint"],{})
        if src is feath:
            r["vanilla"]=f.get("vanilla"); r["dev_buy"]=f.get("dev_buy")
        else:
            mh=f.get("mayhem");hr=f.get("holder_reward");cb=f.get("cashback")
            r["vanilla"]=int(mh==0 and hr==0 and cb==0) if mh is not None else 0
            r["dev_buy"]=f.get("dev_buy") or 0.0
enrich(his,feath); enrich(pop,cren)
def tool(h):
    if not h:return "none"
    h=h.lower()
    for t in ["j7tracker","uxento","rapidlaunch","quicknode","extraction","violasnipe"]:
        if t in h:return t
    if "ipfs.io" in h:return "ipfs.io"
    if "pinata" in h:return "pinata"
    return "other"
for r in his+pop: r["tool"]=tool(r.get("uri_host"))
PRO={"j7tracker","uxento","rapidlaunch","quicknode","extraction","violasnipe"}
NH=len(his); NP=len(pop)
HIS_RATE=0.01  # he fires ~1% of launches
def rule(name, fn):
    rh=sum(1 for x in his if fn(x)); rp=sum(1 for x in pop if fn(x))
    rec=rh/NH; cov=rp/NP
    print(f"{name:48s} recall_his={rec:5.3f}({rh:3d})  cov_pop={cov:5.3f}({rp:4d})  lift={rec/cov if cov else 0:4.2f}")
print("=== CAN SOURCE TIGHTEN THE FILTER TOWARD 1%? (vanilla ~ 50% baseline) ===")
rule("vanilla", lambda x:x["vanilla"]==1)
rule("vanilla & dev>=0.5", lambda x:x["vanilla"]==1 and (x["dev_buy"] or 0)>=0.5)
rule("vanilla & tool in PRO", lambda x:x["vanilla"]==1 and x["tool"] in PRO)
rule("vanilla & tool==uxento", lambda x:x["vanilla"]==1 and x["tool"]=="uxento")
rule("vanilla & has compute-budget ix (n_cb>=1)", lambda x:x["vanilla"]==1 and (x.get("n_cb_ix") or 0)>=1)
rule("vanilla & dev>=0.5 & tool in PRO", lambda x:x["vanilla"]==1 and (x["dev_buy"] or 0)>=0.5 and x["tool"] in PRO)
rule("vanilla & dev>=2.0", lambda x:x["vanilla"]==1 and (x["dev_buy"] or 0)>=2.0)
rule("vanilla & dev>=2.0 & tool in PRO", lambda x:x["vanilla"]==1 and (x["dev_buy"] or 0)>=2.0 and x["tool"] in PRO)
rule("tool in PRO (alone)", lambda x:x["tool"] in PRO)
rule("tool==uxento (alone)", lambda x:x["tool"]=="uxento")
print()
print("=== SOURCE DIST: his vs population RESTRICTED to vanilla&dev>=0.5 (the 24% pool) ===")
pool=[x for x in pop if x["vanilla"]==1 and (x["dev_buy"] or 0)>=0.5]
hh=[x for x in his if x["vanilla"]==1 and (x["dev_buy"] or 0)>=0.5]
ch=Counter(x["tool"] for x in hh); cp=Counter(x["tool"] for x in pool)
print(f"his-in-pool n={len(hh)}  pop-pool n={len(pool)}")
for k in sorted(set(ch)|set(cp),key=lambda z:-(cp[z])):
    ph=ch[k]/len(hh) if hh else 0; pp=cp[k]/len(pool) if pool else 0
    print(f"  {k:12s} his|pool={ph:5.3f}  pop|pool={pp:5.3f}  lift={ph/pp if pp else float('inf'):4.2f}")

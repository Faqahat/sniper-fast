import sys,json
sys.path.insert(0,"/root/profit_backtest"); import common as C
from concurrent.futures import ThreadPoolExecutor
from collections import Counter
raw=json.load(open("/root/attempt_filter/attempted_feat.json"))
att=[r for r in raw if r.get("create_found") and r.get("creator")]
def oldest(mint):
    before=None;last=None
    for _ in range(4):
        pr=[mint,{"limit":1000}]
        if before: pr[1]["before"]=before
        r=C.rpc("getSignaturesForAddress",pr)
        if not r: break
        last=r[-1];before=r[-1]["signature"]
        if len(r)<1000: break
    return last
def work(c):
    s=oldest(c["mint"])
    if not s: return (c["mint"],None)
    tx=C.gettx(s["signature"])
    try:
        keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
        return (c["mint"],keys[0])
    except: return (c["mint"],None)
dep={}
with ThreadPoolExecutor(max_workers=20) as ex:
    for m,p in ex.map(work,att): dep[m]=p
payers=[dep[c["mint"]] for c in att if dep.get(c["mint"])]
eq=sum(1 for c in att if dep.get(c["mint"])==c.get("creator"))
dc=Counter(payers)
print(f"resolved deployer for {len(payers)}/{len(att)}")
print(f"create fee-payer == creator arg: {eq}/{len(payers)} ({100*eq/len(payers):.0f}%)")
rep={d:n for d,n in dc.items() if n>1}
print(f"distinct deployers={len(dc)}  repeat deployers={len(rep)} covering {sum(rep.values())}/{len(payers)} ({100*sum(rep.values())/len(payers):.0f}%)")
print("top deployers:",[(d[:8],n) for d,n in dc.most_common(8)])

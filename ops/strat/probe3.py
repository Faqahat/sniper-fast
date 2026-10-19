import sys, time, json, urllib.request
sys.path.insert(0, "/root/indep")
from common import rpc, RPC, MINT_AUTH
from concurrent.futures import ThreadPoolExecutor
# old sigs: ~4 days ago
s=rpc("getSlot",[{"commitment":"confirmed"}])
old=s-int(4.0*86400/0.216)
blk_sig=None
r=rpc("getSignaturesForAddress",[MINT_AUTH,{"limit":1000}])
# find anchor around old slot: use getBlock signatures only
t=time.time(); b=rpc("getBlock",[old,{"encoding":"json","transactionDetails":"signatures","rewards":False,"maxSupportedTransactionVersion":1}]); print("getBlock sigs", time.time()-t, type(b), (b or {}).get("blockTime") if isinstance(b,dict) else b)
anc=b["signatures"][0] if isinstance(b,dict) and "signatures" in b else None
t=time.time(); r2=rpc("getSignaturesForAddress",[MINT_AUTH,{"limit":1000,"before":anc}]); print("old page", time.time()-t, len(r2), r2[0]["slot"], r2[-1]["slot"])
sigs=[x["signature"] for x in r2[:200]]
def g(sg):
    t=time.time(); x=rpc("getTransaction",[sg,{"encoding":"json","maxSupportedTransactionVersion":1,"commitment":"confirmed"}]); return time.time()-t, isinstance(x,dict) and "meta" in x
for nw in (8,24):
    t=time.time()
    with ThreadPoolExecutor(nw) as ex: res=list(ex.map(g,sigs[:100] if nw==8 else sigs[100:200]))
    print(nw,"workers old 100 tx", time.time()-t, sum(ok for _,ok in res), sorted(a for a,_ in res)[::10])
# batch
def batch(sgs):
    data=json.dumps([{"jsonrpc":"2.0","id":i,"method":"getTransaction","params":[sg,{"encoding":"json","maxSupportedTransactionVersion":1,"commitment":"confirmed"}]} for i,sg in enumerate(sgs)]).encode()
    req=urllib.request.Request(RPC,data=data,headers={"content-type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=120))
t=time.time()
try:
    out=batch([x["signature"] for x in r[200:250]]); print("batch50 recent", time.time()-t, type(out), len(out) if isinstance(out,list) else str(out)[:200], sum(1 for o in out if o.get("result")) if isinstance(out,list) else None)
except Exception as e: print("batch err", e)

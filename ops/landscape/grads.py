#!/usr/bin/env python3
import os,json,urllib.request,time,threading
tok=[l.split("=",1)[1].strip() for l in open("/root/arbx/deploy/.env") if l.startswith("CONSTANTK_TOKEN")][0]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={tok}"
CACHE="/root/landscape/gcache"; os.makedirs(CACHE,exist_ok=True)
MIG="9C4nRvhhVquCKATjDCx5FKvNS9PNgNqgyWy9AcoDjYv5"
PUMPSWAP="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
WSOL="So11111111111111111111111111111111111111112"
def rpc(m,p,timeout=60):
    b=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for a in range(6):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(RPC,data=b,headers={"Content-Type":"application/json"}),timeout=timeout))
            if "result" in r: return r["result"]
            return None
        except Exception: time.sleep(0.4*(a+1))
    return None
def gettx(sig):
    f=f"{CACHE}/{sig}.json"
    if os.path.exists(f):
        try: return json.load(open(f))
        except: pass
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":1,"encoding":"jsonParsed"}])
    try: json.dump(tx,open(f,"w"))
    except: pass
    return tx
# pull recent migration signatures
sigs=[]; before=None
while len(sigs)<260:
    pr=[MIG,{"limit":1000}]
    if before: pr[1]["before"]=before
    ch=rpc("getSignaturesForAddress",pr)
    if not ch: break
    sigs+=ch; before=ch[-1]["signature"]
    if len(ch)<1000: break
sigs=[s for s in sigs if not s.get("err")]
print("migration sigs pulled:",len(sigs),"slot range",sigs[-1]["slot"] if sigs else None,"->",sigs[0]["slot"] if sigs else None)
# parse each migration -> mint + pool + slot
def parse_mig(sig,slot):
    tx=gettx(sig)
    if not tx or not tx.get("meta"): return None
    msg=tx["transaction"]["message"]
    # mint = a non-wsol mint appearing in postTokenBalances
    mints=set()
    for t in (tx["meta"].get("postTokenBalances") or []):
        if t.get("mint") and t["mint"]!=WSOL: mints.add(t["mint"])
    mint=None
    for m in mints:
        if m.endswith("pump") or True: mint=m; break
    return {"sig":sig,"slot":slot,"mint":mint}
grads=[]
lk=threading.Lock()
def w(s):
    r=parse_mig(s["signature"],s["slot"])
    if r and r["mint"]:
        with lk: grads.append(r)
ths=[]
for s in sigs[:260]:
    t=threading.Thread(target=w,args=(s,));t.start();ths.append(t)
    if len(ths)>=16:
        for t in ths:t.join()
        ths=[]
for t in ths:t.join()
grads.sort(key=lambda x:x["slot"])
json.dump(grads,open("/root/landscape/grads.json","w"))
print("parsed graduations with mint:",len(grads))
print("sample:",grads[:3])

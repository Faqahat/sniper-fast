import json,urllib.request,time,threading
from concurrent.futures import ThreadPoolExecutor
tok=[l.split("=",1)[1].strip().strip("\"").strip("'") for l in open("/root/arbx/deploy/.env") if l.startswith("CONSTANTK_TOKEN")][0]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={tok}"
def rpc(m,p):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for a in range(7):
        try:
            r=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            return json.loads(urllib.request.urlopen(r,timeout=90).read())
        except Exception as e:
            time.sleep(0.4*(a+1))
    return {"error":"x"}
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+_A.index(c)
    o=bytearray()
    while n>0: o.append(n&0xff); n>>=8
    o.reverse(); return bytes(len(s)-len(s.lstrip("1")))+bytes(o)
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
CB="ComputeBudget111111111111111111111111111111"
BUYS={"e1f7501ed5b38488","c2ab1c46684d5b2f","38fc74089edfcd5f","66063d1201daebea","b817ee6167c5d33d","07051dc4f5176550"}
LO,HI=456604900,456820120
# 1. paginate sigs
sigs=[]; before=None
while True:
    p=[WALLET,{"limit":1000}]
    if before: p[1]["before"]=before
    res=rpc("getSignaturesForAddress",p).get("result")
    if not res: break
    sigs.extend(res)
    mn=min(s["slot"] for s in res)
    before=res[-1]["signature"]
    if mn<LO: break
    if len(res)<1000: break
inwin=[s for s in sigs if LO<=s["slot"]<=HI]
print(f"listed {len(sigs)} sigs, in-window {len(inwin)} succ={sum(1 for s in inwin if s.get('err') is None)} err={sum(1 for s in inwin if s.get('err') is not None)}",flush=True)
# 2. decode each tx (jsonParsed)
def decode(s):
    sig=s["signature"]
    tx=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}]).get("result")
    if not tx: return None
    meta=tx.get("meta") or {}
    msg=tx["transaction"]["message"]
    # all instructions (top + inner)
    allix=list(msg.get("instructions",[]))
    for inn in meta.get("innerInstructions",[]):
        allix.extend(inn.get("instructions",[]))
    cu_price=0
    for ix in msg.get("instructions",[]):
        if ix.get("programId")==CB:
            d=ix.get("data")
            try: raw=b58d(d)
            except: continue
            if raw and raw[0]==3: cu_price=int.from_bytes(raw[1:9],"little")
    for ix in allix:
        if ix.get("programId")!=PUMP: continue
        data=ix.get("data")
        if not data: continue
        try: raw=b58d(data)
        except: continue
        if raw[:8].hex() not in BUYS: continue
        accs=ix.get("accounts",[])
        if len(accs)<17: continue
        if accs[8]!=WALLET: continue
        mint=accs[1]
        return {"sig":sig,"slot":tx["slot"],"mint":mint,"failed":meta.get("err") is not None,
                "disc":raw[:8].hex(),"cu_price":cu_price,"buy_lamports":int.from_bytes(raw[8:16],"little")}
    return None
out=[]
with ThreadPoolExecutor(max_workers=20) as ex:
    for i,r in enumerate(ex.map(decode,inwin)):
        if r: out.append(r)
        if (i+1)%500==0: print(f"  decoded {i+1}/{len(inwin)} buys={len(out)}",flush=True)
json.dump({"attempts":out,"n_inwin":len(inwin),"lo":LO,"hi":HI},open("attempts.json","w"))
nland=sum(1 for r in out if not r["failed"]); nfail=sum(1 for r in out if r["failed"])
print(f"BUY attempts: {len(out)} (landed={nland} failed={nfail})  distinct mints={len(set(r['mint'] for r in out))}",flush=True)

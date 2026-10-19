import json,urllib.request,time,os
from concurrent.futures import ThreadPoolExecutor
tok=[l.split("=",1)[1].strip().strip('"').strip("'") for l in open("/root/arbx/deploy/.env") if l.startswith("CONSTANTK_TOKEN")][0]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={tok}"
def rpc(m,p):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for a in range(7):
        try:
            r=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            return json.loads(urllib.request.urlopen(r,timeout=90).read())
        except Exception: time.sleep(0.4*(a+1))
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
BUYS={"e1f7501ed5b38488","c2ab1c46684d5b2f","38fc74089edfcd5f","66063d1201daebea","b817ee6167c5d33d","07051dc4f5176550"}
# paginate ALL his sigs (up to 16k cap)
sigs=[]; before=None
while len(sigs)<16000:
    p=[WALLET,{"limit":1000}]
    if before: p[1]["before"]=before
    res=rpc("getSignaturesForAddress",p).get("result")
    if not res: break
    sigs.extend(res); before=res[-1]["signature"]
    if len(res)<1000: break
print(f"listed {len(sigs)} sigs slot {min(s['slot'] for s in sigs)}..{max(s['slot'] for s in sigs)}",flush=True)
def decode(s):
    tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}]).get("result")
    if not tx: return None
    meta=tx.get("meta") or {}; msg=tx["transaction"]["message"]
    allix=list(msg.get("instructions",[]))
    for inn in meta.get("innerInstructions",[]): allix.extend(inn.get("instructions",[]))
    for ix in allix:
        if ix.get("programId")!=PUMP: continue
        d=ix.get("data")
        if not d: continue
        try: raw=b58d(d)
        except: continue
        if raw[:8].hex() not in BUYS: continue
        accs=ix.get("accounts",[])
        if len(accs)<17 or accs[8]!=WALLET: continue
        return {"sig":s["signature"],"slot":tx["slot"],"mint":accs[1],"failed":meta.get("err") is not None}
    return None
buys=[]
with ThreadPoolExecutor(max_workers=24) as ex:
    for i,r in enumerate(ex.map(decode,sigs)):
        if r: buys.append(r)
        if (i+1)%2000==0: print(f"  {i+1}/{len(sigs)} buys={len(buys)}",flush=True)
mints=sorted(set(b["mint"] for b in buys))
print(f"buys={len(buys)} distinct mints={len(mints)}",flush=True)
# resolve creator per mint via oldest sig -> create tx
import sys; sys.path.insert(0,"/root/profit_backtest"); import common as C
def creator_of(mint):
    before=None; last=None
    for _ in range(4):
        pr=[mint,{"limit":1000}]
        if before: pr[1]["before"]=before
        r=C.rpc("getSignaturesForAddress",pr)
        if not r: break
        last=r[-1]; before=r[-1]["signature"]
        if len(r)<1000: break
    if not last: return None
    tx=C.gettx(last["signature"]); f=C.parse_create(tx)
    return (mint,(f.get("creator"),f.get("create_slot"),f.get("dev_buy")) if f else None)
mc={}
with ThreadPoolExecutor(max_workers=20) as ex:
    for i,res in enumerate(ex.map(creator_of,mints)):
        if res: mc[res[0]]=res[1]
        if (i+1)%200==0: print(f"  creator {i+1}/{len(mints)}",flush=True)
# attach
for b in buys:
    cr=mc.get(b["mint"]); b["creator"]=cr[0] if cr else None; b["create_slot"]=cr[1] if cr else None; b["dev_buy"]=cr[2] if cr else None
json.dump({"buys":buys},open("/root/attempt_filter/ext_buys.json","w"))
print("done -> ext_buys.json",flush=True)

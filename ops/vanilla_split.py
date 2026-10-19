import json, urllib.request, os, time, random
from concurrent.futures import ThreadPoolExecutor
TOK=os.environ["CONSTANTK_TOKEN"]; RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=20)).get("result")
        except: time.sleep(0.3)
    return None
d=json.load(open("/root/expanded_raw.json"))
items=[(mint,v) for mint,v in d.items() if v.get("status")=="ok" and v.get("create_sig")]
random.seed(1); random.shuffle(items); items=items[:250]
NONVAN=["CreatorFee","creator_fee","Holder","holder_reward","Mayhem","mayhem","Cashback","cashback","Reward"]
def classify(it):
    mint,v=it
    tx=rpc("getTransaction",[v["create_sig"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: return (mint, None, v.get("dev_buy_sol",0))
    logs=tx["meta"].get("logMessages",[])
    nonvan=any(w in l for l in logs for w in NONVAN)
    return (mint, nonvan, v.get("dev_buy_sol",0))
res=list(ThreadPoolExecutor(40).map(classify, items))
res=[r for r in res if r[1] is not None]
n=len(res); nonvan=sum(1 for r in res if r[1]); van=n-nonvan
print(f"his tokens checked: {n}")
print(f"  NON-vanilla: {nonvan} ({100*nonvan/n:.0f}%)")
print(f"  vanilla:     {van} ({100*van/n:.0f}%)")
# split by dev tier
for lo,hi,t in [(0,0.5,"dev<0.5"),(0.5,99,"dev>=0.5")]:
    sub=[r for r in res if lo<=r[2]<hi]
    if sub:
        nv=sum(1 for r in sub if r[1])
        print(f"  {t}: n={len(sub)} non-vanilla={100*nv/len(sub):.0f}%")

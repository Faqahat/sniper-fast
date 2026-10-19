import os,json,urllib.request,time
RPC=os.environ["RPC"]; WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"; PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
_A="123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s:n=n*58+_A.index(c)
    return b"\x00"*(len(s)-len(s.lstrip("1")))+(n.to_bytes((n.bit_length()+7)//8,"big") if n else b"")
def rpc(m,p):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for _ in range(6):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"}),timeout=40))
            if "result" in r: return r["result"]
        except: time.sleep(0.5)
    return None
sigs=rpc("getSignaturesForAddress",[WALLET,{"limit":1000}])
err=[s for s in sigs if s.get("err")]
def tx(s): return rpc("getTransaction",[s,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
from collections import Counter
disc_c=Counter()
for s in err[:6]:
    t=tx(s["signature"])
    msg=t["transaction"]["message"]
    for ix in msg.get("instructions",[]):
        if ix.get("programId")!=PUMP: continue
        d=b58d(ix.get("data","")); disc=d[:8].hex(); accs=ix.get("accounts",[])
        disc_c[disc]+=1
        print(s["signature"][:8],"disc",disc,"nacc",len(accs))
        for i,a in enumerate(accs): print("   ",i,a,"<<WALLET" if a==WALLET else ("<<pump" if a.endswith("pump") else ""))
        print("    data_sol@8",int.from_bytes(d[8:16],"little")/1e9 if len(d)>=16 else None,"@16",int.from_bytes(d[16:24],"little")/1e9 if len(d)>=24 else None)
        break
print("discs:",dict(disc_c))

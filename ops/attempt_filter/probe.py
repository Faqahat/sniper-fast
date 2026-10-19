import json,urllib.request,time,os
tok=[l.split("=",1)[1].strip().strip("\"").strip("'") for l in open("/root/arbx/deploy/.env") if l.startswith("CONSTANTK_TOKEN")][0]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={tok}"
def rpc(m,p):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for a in range(6):
        try:
            r=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
            return json.loads(urllib.request.urlopen(r,timeout=60).read())
        except Exception as e:
            time.sleep(0.5*(a+1))
    return {"error":"x"}
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
r=rpc("getSignaturesForAddress",[WALLET,{"limit":1000}])["result"]
err=[s for s in r if s.get("err") is not None]
succ=[s for s in r if s.get("err") is None]
print("batch of",len(r),"succ",len(succ),"err",len(err))
print("slot range",min(s["slot"] for s in r),max(s["slot"] for s in r))
# sample one error tx
for s in err[:2]:
    tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])["result"]
    msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
    print("--- ERR sig",s["signature"][:12],"slot",tx["slot"],"err",meta.get("err"))
    for ix in msg.get("instructions",[]):
        print("  toplevel prog",ix.get("programId"), "naccs",len(ix.get("accounts",[]) or []))
    inner=meta.get("innerInstructions",[])
    print("  has innerInstructions:",len(inner))

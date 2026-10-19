import os,json,urllib.request,time
RPC=os.environ["RPC"]
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
FCDY="FCdY3UTqSrbKab7ba3V6LDVSwYue2GD1xyq8tPY6Yr3o"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
def rpc(m,p):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    for _ in range(6):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"}),timeout=40))
            if "result" in r: return r["result"]
        except Exception as e: time.sleep(0.5)
    return None
sigs=rpc("getSignaturesForAddress",[WALLET,{"limit":1000}])
succ=[s for s in sigs if not s.get("err")]; err=[s for s in sigs if s.get("err")]
print("page sigs",len(sigs),"succ",len(succ),"err",len(err))
def tx(s): return rpc("getTransaction",[s,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
# examine one failed tx structure
for s in err[:3]:
    t=tx(s["signature"])
    if not t: print("no tx"); continue
    msg=t["transaction"]["message"]; meta=t.get("meta") or {}
    print("=== FAILED",s["signature"][:8],"err=",json.dumps(s.get("err"))[:60])
    tops=[(ix.get("programId"),ix.get("accounts",[])[:4],ix.get("data","")[:12]) for ix in msg.get("instructions",[])]
    for p,a,d in tops: print("  top prog",p[:10],"naccts",len(ix) if 0 else "", "accs0..3",[x[:6] for x in a])
    print("  inner groups:",len(meta.get("innerInstructions",[])))
    # list programIds used
    progs=set(ix.get("programId") for ix in msg.get("instructions",[]))
    print("  top progs:",[p[:12] for p in progs])

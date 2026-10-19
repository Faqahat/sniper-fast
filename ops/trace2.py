import json,urllib.request,os,time
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W="CUQqcZZGr8QLjEzMpxUZyiZirBujE2Y9yZDyfCRw1CAB"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(5):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
# re-open the known sell tx, get W-owned token account pubkey
tx=rpc("getTransaction",["4MiVUnhY5CeGPe",{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}]) or \
   rpc("getTransaction",[rpc("getSignaturesForAddress",[W,{"limit":3}])[1]["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
wtok=None;mint=None
for b in tx["meta"].get("preTokenBalances",[]):
    if b.get("owner")==W:
        wtok=keys[b["accountIndex"]]; mint=b["mint"]
print("W token account:",wtok,"mint:",mint[:12] if mint else None)
if wtok:
    sgs=rpc("getSignaturesForAddress",[wtok,{"limit":40}])
    print("token-acct sigs:",len(sgs) if sgs else 0)
    for s in (sgs[::-1][:8] if sgs else []):
        t=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
        if not t: continue
        kk=[k["pubkey"] for k in t["transaction"]["message"]["accountKeys"]]
        signers=[k["pubkey"] for k in t["transaction"]["message"]["accountKeys"] if k.get("signer")]
        logs=t["meta"].get("logMessages",[])
        kind="BUY" if any("Instruction: Buy" in l for l in logs) else ("SELL" if any("Instruction: Sell" in l for l in logs) else "xfer")
        fp=signers[0] if signers else "?"
        fpsol=(t["meta"]["postBalances"][kk.index(fp)]-t["meta"]["preBalances"][kk.index(fp)])/1e9 if fp in kk else 0
        pre=next((float(b["uiTokenAmount"]["uiAmount"] or 0) for b in t["meta"].get("preTokenBalances",[]) if b.get("owner")==W),0)
        post=next((float(b["uiTokenAmount"]["uiAmount"] or 0) for b in t["meta"].get("postTokenBalances",[]) if b.get("owner")==W),0)
        print(f"  {s['signature'][:12]} {kind:4} payer={fp[:10]} payerSOLΔ={fpsol:+.3f} W_tokΔ={post-pre:+.0f}")

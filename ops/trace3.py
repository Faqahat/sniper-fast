import json,urllib.request,os,time
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W="CUQqcZZGr8QLjEzMpxUZyiZirBujE2Y9yZDyfCRw1CAB"
ACCT="GY9kbQap695groJ3kUagkNE3y3uYTsSWgFUq1CmcQmyD"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(6):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.5*(i+1))
    return None
# paginate to oldest
allsig=[];before=None
while True:
    prm=[ACCT,{"limit":1000}] if before is None else [ACCT,{"limit":1000,"before":before}]
    r=rpc("getSignaturesForAddress",prm)
    if not r: break
    allsig+=r
    if len(r)<1000: break
    before=r[-1]["signature"]
print("total token-acct sigs:",len(allsig))
# oldest first
for s in allsig[::-1][:10]:
    t=None
    for _ in range(4):
        t=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
        if t: break
        time.sleep(0.6)
    if not t: print("  (fetch fail)",s["signature"][:12]); continue
    kk=[k["pubkey"] for k in t["transaction"]["message"]["accountKeys"]]
    signers=[k["pubkey"] for k in t["transaction"]["message"]["accountKeys"] if k.get("signer")]
    logs=t["meta"].get("logMessages",[])
    kind="BUY" if any("Instruction: Buy" in l for l in logs) else ("SELL" if any("Instruction: Sell" in l for l in logs) else "xfer")
    fp=signers[0] if signers else "?"
    fpsol=(t["meta"]["postBalances"][kk.index(fp)]-t["meta"]["preBalances"][kk.index(fp)])/1e9 if fp in kk else 0
    wsol=(t["meta"]["postBalances"][kk.index(W)]-t["meta"]["preBalances"][kk.index(W)])/1e9 if W in kk else None
    pre=next((float(b["uiTokenAmount"]["uiAmount"] or 0) for b in t["meta"].get("preTokenBalances",[]) if b.get("owner")==W),0)
    post=next((float(b["uiTokenAmount"]["uiAmount"] or 0) for b in t["meta"].get("postTokenBalances",[]) if b.get("owner")==W),0)
    print(f"  {kind:4} payer={fp[:11]} payerSOLΔ={fpsol:+.3f} Winkeys={W in kk} W_SOLΔ={wsol} W_tokΔ={post-pre:+.0f}")

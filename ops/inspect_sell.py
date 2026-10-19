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
# find a sell tx: scan recent for SOL in + Instruction: Sell
sigs=rpc("getSignaturesForAddress",[W,{"limit":40}])
for s in sigs:
    tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: continue
    logs=tx["meta"].get("logMessages",[])
    kind="BUY" if any("Instruction: Buy" in l for l in logs) else ("SELL" if any("Instruction: Sell" in l for l in logs) else "")
    if not kind: continue
    keys=[k["pubkey"] for k in tx["transaction"]["message"]["accountKeys"]]
    wi=keys.index(W); sold=(tx["meta"]["postBalances"][wi]-tx["meta"]["preBalances"][wi])/1e9
    print(f"=== {s['signature'][:14]} kind={kind} W_SOLΔ={sold:+.3f} ===")
    print("  preTokenBalances:")
    for b in tx["meta"].get("preTokenBalances",[]):
        print(f"    mint={b['mint'][:10]} owner={b.get('owner','?')[:10]} amt={b['uiTokenAmount']['uiAmount']}")
    print("  postTokenBalances:")
    for b in tx["meta"].get("postTokenBalances",[]):
        print(f"    mint={b['mint'][:10]} owner={b.get('owner','?')[:10]} amt={b['uiTokenAmount']['uiAmount']}")
    # programs
    progs=set()
    for ix in tx["transaction"]["message"]["instructions"]:
        if "programId" in ix: progs.add(ix["programId"])
    print("  top progs:", [p[:12] for p in progs])
    break

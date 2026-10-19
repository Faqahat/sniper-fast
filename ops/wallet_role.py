import json,urllib.request,os,time
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W="CUQqcZZGr8QLjEzMpxUZyiZirBujE2Y9yZDyfCRw1CAB"
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PUMPAMM="pAMMBay6oceH9fJKBRHGP5D4bD4sWpmSwMn52FMfXEA"
SYS="11111111111111111111111111111111"
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for i in range(5):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.4*(i+1))
    return None
sigs=rpc("getSignaturesForAddress",[W,{"limit":12}])
for s in sigs[:8]:
    tx=rpc("getTransaction",[s["signature"],{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: continue
    msg=tx["transaction"]["message"]; meta=tx["meta"]
    keys=msg["accountKeys"]
    signers=[k["pubkey"] for k in keys if k.get("signer")]
    kl=[k["pubkey"] for k in keys]
    wi=kl.index(W) if W in kl else None
    sold=(meta["postBalances"][wi]-meta["preBalances"][wi])/1e9 if wi is not None else None
    w_signer = W in signers
    # top-level programs + instruction names
    ixnames=[]
    for ix in msg["instructions"]:
        pid=ix.get("programId","")
        tag = "PUMP" if pid==PUMP else ("PUMPAMM" if pid==PUMPAMM else ("SYS" if pid==SYS else pid[:6]))
        ixnames.append(tag)
    # detect pump inner buy/sell via logs
    logs=meta.get("logMessages",[])
    kind=""
    for lg in logs:
        if "Instruction: Buy" in lg: kind="BUY"
        if "Instruction: Sell" in lg: kind="SELL"
    print(f"sig {s['signature'][:10]} | W_signer={w_signer} | W_SOLΔ={sold:+.3f} | kind={kind} | fee_payer={signers[0][:8] if signers else '?'} | ix={ixnames[:6]}")

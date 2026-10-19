import json, urllib.request, os, time
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
JITO_TIPS={"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5","HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe","Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY","ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49","DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh","ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt","DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL","3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    for _ in range(3):
        try: return json.load(urllib.request.urlopen(req,timeout=25)).get("result")
        except: time.sleep(0.5)
    return None
# paginate signatures
allsigs=[]; before=None
for _ in range(6):
    p=[WALLET,{"limit":1000}]; 
    if before: p[1]["before"]=before
    r=rpc("getSignaturesForAddress",p)
    if not r: break
    allsigs+=r; before=r[-1]["signature"]
    if len(r)<1000: break
landed=[s["signature"] for s in allsigs if not s["err"]]
failed=sum(1 for s in allsigs if s["err"])
print(f"sigs total={len(allsigs)} landed={len(landed)} failed={failed} ({100*failed/max(1,len(allsigs)):.0f}% fail)")
buys=0; buy_tipped=0; tip_amts=[]; checked=0
for sg in landed:
    if buys>=50: break
    tx=rpc("getTransaction",[sg,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    checked+=1
    if not tx: continue
    logs=tx["meta"].get("logMessages",[])
    if not any("BuyExactQuote" in l or "Instruction: Buy" in l for l in logs): continue
    buys+=1
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in tx["transaction"]["message"]["accountKeys"]]
    hit=JITO_TIPS.intersection(keys)
    if hit:
        buy_tipped+=1
        idx=keys.index(list(hit)[0]); d=(tx["meta"]["postBalances"][idx]-tx["meta"]["preBalances"][idx])/1e9
        tip_amts.append(d)
    time.sleep(0.02)
print(f"checked_txs={checked} BUYS_found={buys} buys_with_Jito_tip={buy_tipped} ({100*buy_tipped/max(1,buys):.0f}%)")
if tip_amts:
    import statistics
    tip_amts.sort()
    print(f"buy tip SOL: median={statistics.median(tip_amts):.5f} p10={tip_amts[len(tip_amts)//10]:.5f} max={max(tip_amts):.5f}")
else: print("NO Jito tips on any buy")

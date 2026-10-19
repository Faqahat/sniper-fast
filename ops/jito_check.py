import json, urllib.request, os, time
TOK=os.environ["CONSTANTK_TOKEN"]
RPC=f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
JITO_TIPS={
"96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5","HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
"Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY","ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
"DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh","ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
"DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL","3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT"}
def rpc(m,p):
    req=urllib.request.Request(RPC,data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={"content-type":"application/json"})
    return json.load(urllib.request.urlopen(req,timeout=20)).get("result")
sigs=[s["signature"] for s in rpc("getSignaturesForAddress",[WALLET,{"limit":80}]) if not s["err"]]
print(f"checking {len(sigs)} landed txs for Jito tips...")
tipped=0; checked=0; buys=0; tip_amts=[]
for sg in sigs:
    tx=rpc("getTransaction",[sg,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
    if not tx: continue
    checked+=1
    msg=tx["transaction"]["message"]
    keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
    # is it a pump buy? look for BuyExactQuote in logs
    logs=tx["meta"].get("logMessages",[])
    isbuy=any("Buy" in l for l in logs)
    if isbuy: buys+=1
    hit=JITO_TIPS.intersection(keys)
    if hit:
        tipped+=1
        # find tip amount: balance delta on the tip account
        idx=keys.index(list(hit)[0])
        pre=tx["meta"]["preBalances"][idx]; post=tx["meta"]["postBalances"][idx]
        tip_amts.append((post-pre)/1e9)
    time.sleep(0.03)
print(f"checked={checked} buys={buys} tipped(Jito)={tipped} ({100*tipped/max(1,checked):.0f}%)")
if tip_amts:
    import statistics
    print(f"tip SOL: median={statistics.median(tip_amts):.5f} min={min(tip_amts):.5f} max={max(tip_amts):.5f} n={len(tip_amts)}")
else:
    print("NO Jito tips found in any landed tx")

import json, urllib.request, os, time
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
def rpc(method, params):
    body = json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req = urllib.request.Request(RPC, data=body, headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read())["result"]
sigs=json.load(open("/root/wallet_sigs.json"))
good=[s for s in sigs if not s["err"]]
print("good sigs:", len(good))
s=good[0]["sig"]
tx=rpc("getTransaction",[s,{"maxSupportedTransactionVersion":0,"encoding":"jsonParsed"}])
meta=tx["meta"]
print("fee",meta["fee"])
print("logs sample:", [l for l in meta.get("logMessages",[]) if "Program log" in l or "Instruction" in l][:15])
msg=tx["transaction"]["message"]
accts=[a["pubkey"] for a in msg["accountKeys"]]
print("signer0:", accts[0])
print("preToken owners:", [(b["owner"],b["mint"],b["uiTokenAmount"]["amount"]) for b in meta.get("preTokenBalances",[])])
print("postToken owners:", [(b["owner"],b["mint"],b["uiTokenAmount"]["amount"]) for b in meta.get("postTokenBalances",[])])

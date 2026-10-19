#!/usr/bin/env python3
# READ-ONLY: SOL + every token balance of the trading wallet (both token programs). usage: wallet.py <out.json>
import json, os, sys, urllib.request, time
TOK = os.environ["CONSTANTK_TOKEN"]; RPC = f"https://rpc-frankfurt.constant-k.com/?api-key={TOK}"
W = "FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
def rpc(m, p):
    r = urllib.request.Request(RPC, data=json.dumps({"jsonrpc": "2.0", "id": 1, "method": m, "params": p}).encode(), headers={"content-type": "application/json"})
    return json.load(urllib.request.urlopen(r, timeout=30))["result"]
sol = rpc("getBalance", [W, {"commitment": "confirmed"}])["value"]
toks = {}
for prog in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
    for a in rpc("getTokenAccountsByOwner", [W, {"programId": prog}, {"encoding": "jsonParsed", "commitment": "confirmed"}])["value"]:
        i = a["account"]["data"]["parsed"]["info"]
        toks[a["pubkey"]] = {"mint": i["mint"], "amount": i["tokenAmount"]["uiAmountString"], "lamports": a["account"]["lamports"]}
out = {"t": time.time(), "sol_lamports": sol, "tokens": toks}
json.dump(out, open(sys.argv[1], "w"), indent=1)
print(f"SOL {sol/1e9:.9f}; token accounts {len(toks)}: " + ", ".join(f"{v['mint'][:6]}={v['amount']}" for v in toks.values()))

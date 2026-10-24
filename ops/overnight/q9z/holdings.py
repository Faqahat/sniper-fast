#!/usr/bin/env python3
# READ-ONLY: 9qz7cW's SOL balance and token holdings right now (both token programs) -> holdings_now.json
import sys, os, json, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from rpcq import rpc
W = "9qz7cWBqYBP2TnGfzMmxX64G4PQip7HtogjPBBnMhWpw"
bal = rpc("getBalance", [W])["value"] / 1e9; hold = []
for prog in ("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA", "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"):
    r = rpc("getTokenAccountsByOwner", [W, {"programId": prog}, {"encoding": "jsonParsed"}])
    for a in r["value"]:
        i = a["account"]["data"]["parsed"]["info"]
        hold.append(dict(acc=a["pubkey"], prog=prog[:5], mint=i["mint"], ui=i["tokenAmount"]["uiAmount"], dec=i["tokenAmount"]["decimals"], lamports=a["account"]["lamports"]))
json.dump(dict(t=time.time(), sol=bal, tokens=hold), open(os.path.join(HERE, "holdings_now.json"), "w"), indent=1)
print("SOL", bal, "token accounts", len(hold), "non-zero", sum(1 for h in hold if h["ui"]))
for h in sorted(hold, key=lambda h: -(h["ui"] or 0))[:30]: print(h["mint"], h["prog"], h["ui"], h["lamports"] / 1e9)

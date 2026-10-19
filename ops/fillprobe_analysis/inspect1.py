import json
d=json.load(open("buy_1.json"))
m=d["meta"]
tx=d["transaction"]
msg=tx["message"]
OUR="FRZh63L6L8m3MEPwHVimRkWPzwSgizr22Z6wvpWTyTWS"
MINT="A8FjoUQXDywuGTrBaeLvDPHtyVq3LaM6YCH4Prfhpump"
print("=== account keys (first signers) ===")
keys=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
print("payer:",keys[0])
# native balance delta for our wallet
idx = keys.index(OUR) if OUR in keys else None
print("our idx:",idx)
if idx is not None:
    print("preSOL",m["preBalances"][idx],"postSOL",m["postBalances"][idx],"delta",m["postBalances"][idx]-m["preBalances"][idx])
print("fee",m["fee"])
print("=== token balances ===")
for tb in m.get("postTokenBalances",[]):
    if tb["mint"]==MINT:
        print("POST owner",tb["owner"],"amt",tb["uiTokenAmount"]["amount"])
for tb in m.get("preTokenBalances",[]):
    if tb["mint"]==MINT:
        print("PRE owner",tb["owner"],"amt",tb["uiTokenAmount"]["amount"])
print("=== top-level instructions programs ===")
for i,ins in enumerate(msg["instructions"]):
    print(i, ins.get("programId"), "data_len" , len(ins.get("data","")) if "data" in ins else "parsed")

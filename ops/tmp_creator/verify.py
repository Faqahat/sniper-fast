import sys, json, hashlib
sys.path.insert(0,"/root/tmp_creator")
from analyze import rpc, b58decode, PUMP
CREATE_DISC=hashlib.sha256(b"global:create").digest()[:8]
mint="3Ci5HwoT71pY9GmEtKJEzNEuFFWtfE5FW7X6wKsrbGvG"
sigs=rpc("getSignaturesForAddress",[mint,{"limit":1000}])
print("mint sigs:",len(sigs))
createsig=sigs[-1]["signature"]  # oldest
print("oldest sig:",createsig)
tx=rpc("getTransaction",[createsig,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
msg=tx["transaction"]["message"]
instrs=list(msg.get("instructions",[]))
for inner in tx.get("meta",{}).get("innerInstructions",[]) or []:
    instrs+=inner.get("instructions",[])
print("signer/feepayer:", msg["accountKeys"][0].get("pubkey") if isinstance(msg["accountKeys"][0],dict) else msg["accountKeys"][0])
for ix in instrs:
    if ix.get("programId")==PUMP and "data" in ix:
        data=b58decode(ix["data"])
        print("pump ix disc:", data[:8].hex(), "== create?", data[:8]==CREATE_DISC, "naccts", len(ix.get("accounts",[])))
        if data[:8]==CREATE_DISC:
            print("  acct0(mint):", ix["accounts"][0])

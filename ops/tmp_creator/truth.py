import sys, json, hashlib, base64
sys.path.insert(0,"/root/tmp_creator")
from analyze import rpc, bonding_curve, b58encode, b58decode, CREATOR, PUMP
CREATE_DISC=hashlib.sha256(b"global:create").digest()[:8]
cb=b58decode(CREATOR)

# locate bwamJz bytes in a curve raw
m="9bzW2gMmA193QuNsxn6xuUiuPPe7sPXFy5oTFS8wV5xG"
bc=bonding_curve(m)
ai=rpc("getAccountInfo",[bc,{"encoding":"base64","commitment":"confirmed"}])
raw=base64.b64decode(ai["value"]["data"][0])
print("curve len",len(raw))
idx=raw.find(cb)
print("bwamJz byte offset in curve:", idx)
# print candidate pubkeys at each 32-window offset 49 and 81
for off in [49,81,113,145]:
    if off+32<=len(raw): print("  off",off,"=",b58encode(raw[off:off+32]))

print("\n=== find true create for each seed mint ===")
seeds=["3Ci5HwoT71pY9GmEtKJEzNEuFFWtfE5FW7X6wKsrbGvG","9bzW2gMmA193QuNsxn6xuUiuPPe7sPXFy5oTFS8wV5xG","Cw9e9ZceFpVvEucufJyvX3YpC9gyyHnPBspha6hEmiiG","2mczEAedUhHRP5GQ43gP2qTVWCij9NgfidmNJpya4YKU"]
for m in seeds:
    before=None; last=None; pages=0
    while pages<15:
        p=[m,{"limit":1000}]
        if before: p[1]["before"]=before
        r=rpc("getSignaturesForAddress",p)
        if not r: break
        last=r[-1]["signature"]; before=last; pages+=1
        if len(r)<1000: break
    tx=rpc("getTransaction",[last,{"encoding":"jsonParsed","maxSupportedTransactionVersion":0}])
    msg=tx["transaction"]["message"]
    fp=msg["accountKeys"][0]; fp=fp.get("pubkey") if isinstance(fp,dict) else fp
    instrs=list(msg.get("instructions",[]))
    iscreate=False; createuser=None
    for ix in instrs:
        if ix.get("programId")==PUMP and "data" in ix:
            d=b58decode(ix["data"])
            if d[:8]==CREATE_DISC:
                iscreate=True
                accs=ix.get("accounts",[])
                createuser=accs[7] if len(accs)>7 else None
    print(f"{m[:8]} pages={pages} oldest_fp={fp[:8]} is_create={iscreate} create_user={createuser} fp_is_bwam={fp==CREATOR}")

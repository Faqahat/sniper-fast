import os, json, time, urllib.request
RPC = "https://rpc-frankfurt.constant-k.com/?api-key=" + os.environ["CONSTANTK_TOKEN"]
PUMP = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
ALPH = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
def b58d(s):
    n=0
    for c in s: n=n*58+ALPH.index(c)
    full=n.to_bytes((n.bit_length()+7)//8,"big") if n else b""
    return b"\x00"*(len(s)-len(s.lstrip("1")))+full
def rpc(m,p):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode()
    req=urllib.request.Request(RPC,data=body,headers={"Content-Type":"application/json"})
    return json.loads(urllib.request.urlopen(req,timeout=45).read()).get("result")
def get_tx(sig):
    for v in (0,1,2):
        r=rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":v,"encoding":"jsonParsed"}])
        if r: return r
    return None
res=json.load(open("/root/creators_resolved.json"))
exp=json.load(open("/root/expanded_raw.json"))
mints=[m for m,c in res["picks"].items() if c][:4]
for mint in mints:
    cs=exp[mint]["create_sig"]
    tx=get_tx(cs)
    msg=tx["transaction"]["message"]
    static=[k["pubkey"] if isinstance(k,dict) else k for k in msg["accountKeys"]]
    la=tx.get("meta",{}).get("loadedAddresses") or {"writable":[],"readonly":[]}
    keys=static+la.get("writable",[])+la.get("readonly",[])
    print("==== mint", mint, "feepayer", keys[0])
    def dump(ixs, where):
        for ix in ixs:
            pidx=ix.get("programIdIndex")
            prog=keys[pidx] if pidx is not None and pidx<len(keys) else ix.get("programId")
            if prog!=PUMP: continue
            data=ix.get("data","")
            try: raw=b58d(data); disc=raw[:8].hex()
            except Exception: disc="?"
            accs=ix.get("accounts",[])
            n=len(accs)
            acc7=None
            if accs:
                if isinstance(accs[0],int): acc7=keys[accs[7]] if n>7 and accs[7]<len(keys) else None
                else: acc7=accs[7] if n>7 else None
            print(f"  [{where}] disc={disc} naccts={n} acc[7]={acc7}")
    dump(msg.get("instructions",[]),"top")
    for inner in tx.get("meta",{}).get("innerInstructions",[]) or []:
        dump(inner.get("instructions",[]),"inner")

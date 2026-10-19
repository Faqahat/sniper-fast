import os, json, urllib.request, time
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
mint=[m for m,c in res["picks"].items() if c][0]
cs=exp[mint]["create_sig"]
tx=get_tx(cs)
msg=tx["transaction"]["message"]
ak=msg["accountKeys"]
static=[k["pubkey"] if isinstance(k,dict) else k for k in ak]
signers={}
for k in ak:
    if isinstance(k,dict): signers[k["pubkey"]]=k.get("signer")
la=tx.get("meta",{}).get("loadedAddresses") or {"writable":[],"readonly":[]}
keys=static+la.get("writable",[])+la.get("readonly",[])
print("mint",mint,"feepayer",keys[0])
for ix in msg.get("instructions",[]):
    pidx=ix.get("programIdIndex"); prog=keys[pidx] if pidx is not None else ix.get("programId")
    if prog!=PUMP: continue
    raw=b58d(ix["data"]); disc=raw[:8].hex()
    accs=ix.get("accounts",[])
    if accs and isinstance(accs[0],int): accs=[keys[a] for a in accs]
    if disc=="07051dc4f5176550":
        print("CREATE ix disc",disc,"naccts",len(accs))
        for i,a in enumerate(accs):
            print(f"  acc[{i}] {a} signer={signers.get(a)}")
# count prior sigs for acc indices 0..8
def prior(c,before):
    r=rpc("getSignaturesForAddress",[c,{"limit":100,"before":before}])
    return len(r) if r is not None else -1
for ix in msg.get("instructions",[]):
    pidx=ix.get("programIdIndex"); prog=keys[pidx] if pidx is not None else ix.get("programId")
    if prog!=PUMP: continue
    raw=b58d(ix["data"]); disc=raw[:8].hex()
    accs=ix.get("accounts",[])
    if accs and isinstance(accs[0],int): accs=[keys[a] for a in accs]
    if disc=="07051dc4f5176550":
        for i in (6,7,8):
            if i<len(accs): print(f"prior-at-launch acc[{i}] {accs[i]} = {prior(accs[i],cs)}")
        break

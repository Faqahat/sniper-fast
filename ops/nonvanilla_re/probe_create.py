import requests, json, sys, time
sys.path.insert(0,"/root/nonvanilla_re")
from pda import find_pda, b58d, b58e
RPC=open("/root/snipe_study50/rpc_url.txt").read().strip()
PUMP="6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"
PFEE="pfeeUxB6jkeY1Hxd7CsFCAjcbHA9rWtchMGdZ6VojVZ"
WALLET="4yFAz7dp5WwuZs3vbWKedbRiUmSFxTVGCdsLAxfEQrG3"
CREATEDISC="d6904cec5f8b31b4"
def rpc(m,p,tries=6):
    for i in range(tries):
        try:
            j=requests.post(RPC,json={"jsonrpc":"2.0","id":1,"method":m,"params":p},timeout=35).json()
            if "result" in j: return j["result"]
            time.sleep(0.4)
        except: time.sleep(0.5)
    return None
def gt(sig,ver): return rpc("getTransaction",[sig,{"maxSupportedTransactionVersion":ver,"encoding":"jsonParsed"}])
def allkeys(tx):
    msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
    keys=[a["pubkey"] for a in msg["accountKeys"]]
    la=meta.get("loadedAddresses") or {}
    keys+=la.get("writable",[])+la.get("readonly",[])
    return keys
def allix(tx):
    msg=tx["transaction"]["message"]; meta=tx.get("meta") or {}
    out=list(msg.get("instructions",[]))
    for inr in meta.get("innerInstructions",[]): out+=inr.get("instructions",[])
    return out
def get_create_sig(mint):
    r=rpc("getSignaturesForAddress",[mint,{"limit":1000}])
    if not r: return None
    ms=min(s["slot"] for s in r)
    for s in [x for x in r if x["slot"]==ms]:
        t=gt(s["signature"],1)
        if not t: continue
        for ix in allix(t):
            if ix.get("programId")==PUMP and ix.get("data"):
                try: raw=b58d(ix["data"])
                except: continue
                if raw[:8].hex()==CREATEDISC: return s["signature"],t,ix
    return None
# samples: mint, creator, buyback13
CASES=json.loads(sys.argv[1])
for name,(mint,creator,bb13) in CASES.items():
    print("###",name,mint,"bb13",bb13)
    gc=get_create_sig(mint)
    if not gc: print("  no create"); continue
    csig,ctx,cix=gc
    ck=allkeys(ctx)
    print("  create sig",csig)
    print("  bb13 in create accountKeys?", bb13 in ck, ("idx="+str(ck.index(bb13))) if bb13 in ck else "")
    # Is bb13 a PDA under pfee from creator? try seeds
    tests=[("[creator]@PFEE",[b58d(creator)],PFEE),
           ("creator-vault[creator]@PFEE",[b"creator-vault",b58d(creator)],PFEE),
           ("fee-recipient[creator]@PFEE",[b"fee-recipient",b58d(creator)],PFEE),
           ("buyback[creator]@PFEE",[b"buyback",b58d(creator)],PFEE),
           ("creator-vault[creator]@PUMP",[b"creator-vault",b58d(creator)],PUMP)]
    for nm,seeds,prog in tests:
        d,b=find_pda(seeds,prog)
        if d==bb13: print("   == MATCH bb13 =",nm,"bump",b)
    # dump the create pump ix full account list
    print("  create ix accounts (n=%d):"%len(cix.get("accounts",[])))
    for i,a in enumerate(cix.get("accounts",[])):
        print("    c[%d] %s%s"%(i,a," <==bb13" if a==bb13 else ""))
